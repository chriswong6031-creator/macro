"""FR Y-9C bank stress panel collector — W3 family data plane.

Pulls bank-level call-report data from the FDIC BankFind API
(https://banks.data.fdic.gov/api/financials) for all member banks whose
parent holding company maps to one of the regional_banks basket tickers.
Aggregates subsidiary-level figures up to BHC level using the RSSDHCR
(parent HC RSSD) crosswalk embedded in each FDIC institution record.

Data source: FDIC BankFind Suite (public, keyless, JSON API)
  URL: https://banks.data.fdic.gov/api/financials
  Coverage: Q1 1984 to ~2 quarters ago (5–6 week release lag)
  Granularity: per-quarter per-bank-charter (CERT), then aggregated to BHC

PIT lag: FDIC bulk release is approximately 45–60 days after quarter-end
  (call report filing deadline = 30–45 days after quarter-end; bulk
  data publication adds ~1 additional week). We enforce this by
  restricting signal date to report_date + PIT_LAG_DAYS = 60 — the
  observed worst case (Q1-2023 bulk data appeared 2023-05-30, 60 days
  after quarter-end, per the FDIC SDI release calendar). Amended
  2026-07-08 from 45d, which was insufficiently conservative for
  large-bank late filers and contradicted the 60d lag enforced by
  scripts/w3_bank_callreport_stress_phase0.py.

Pre-registered gaps (before computing, per house rules):
  GAP-1: FDIC carries BANK-LEVEL (subsidiary) data, not BHC-level.
         We aggregate to BHC via RSSDHCR linkage. For banks with a
         single large subsidiary (the regional_banks universe) this is
         near-identical to BHC-level. Basis risk: multi-charter BHCs
         (e.g., PNC has regional subsidiaries) may undercount if FDIC
         mapping misses sub-charters — see per-ticker coverage log.

  GAP-2: CRE MATURITY SCHEDULE not available from FDIC call reports
         (maturity breakdown is in FR Y-9C Schedule HC-C Part II, not
         filed at individual bank level on Call Report). We proxy the
         "maturity wall roll-through" dimension with:
           V1a: NCRENRER delta (rising nonfarm nonres CRE delinquency =
                loans hitting reset wall and defaulting)
           V1b: CRE concentration trend (CRE/total-capital change =
                growing exposure to the roll)
           V1c: [NOT COMPUTABLE] exact maturity bucket gap — pre-registered
                as a known null; a future FR Y-9C pull would enable it.

  GAP-3: AOCI/HTM unrealized loss not directly available in FDIC financials
         (SC = total securities but breakdown into AFS/HTM not in FDIC).
         V3 canonical-ratio composite will exclude AOCI and use available
         items: CRE concentration, uninsured deposit share, brokered dep
         share (LNNDEPC/DEP), noncurrent CRE rate.

  GAP-4: FHLB advances not in FDIC financials in a standalone line item.
         Excluded from V3 composite.

Fields used (from FDIC /api/financials, all verified against live API):
  CERT      bank charter number (primary key)
  REPDTE    report date (YYYYMMDD)
  ASSET     total assets ($K)
  EQ        total equity ($K)
  DEP       total deposits ($K)
  DEPINS    FDIC-insured deposits ($K)
  DEPUNINS  estimated uninsured deposits ($K)  ← V2/V3
  COREDEP   core deposits ($K)
  LNNDEPC   brokered deposits ($K)             ← V2
  LNLSNET   net loans & leases ($K)
  LNRECONS  C&D (construction) CRE loans ($K)
  LNRENRES  nonfarm nonresidential CRE loans ($K)  ← V1/V3
  LNREMULT  multifamily CRE loans ($K)
  NCRENRER  nonfarm nonres CRE noncurrent rate (%)  ← V1
  NCRECONR  C&D CRE noncurrent rate (%)             ← V1
  SC        total securities ($K)
  RSSDHCR   parent HC RSSD ID (aggregation key)

Universe: 20 surviving regional_banks basket tickers + 3 failed banks
          (SIVB, SBNY, FRC — retained for survivorship-bias correction per
          the FRC/SIVB-era rule), 2018-Q1 to 2026-Q1. Span covers 33 quarters
          including the Mar-2023 stress episode. Failed banks stop reporting
          after their operational end date; missing quarters after
          last_repdte are expected, not collection errors.

Run (standalone):
  python3 -m scripts.collect_ffiec_y9c [--start 2018-Q1] [--end 2026-Q1]
                                        [--resume] [--dry-run]
Output:
  data/ffiec_y9c/bhc_panel.parquet   — quarterly BHC-level panel
  data/ffiec_y9c/bhc_ticker_map.csv  — BHC ticker→RSSDHCR crosswalk

Nightly wiring (for consolidation):
  Add to daily.yml as a separate pre-analysis step.
  No engine dependencies; runs standalone in <5 minutes.
  Command: python3 -m scripts.collect_ffiec_y9c --resume
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (verified against FDIC API live)
# ---------------------------------------------------------------------------
FDIC_BASE = "https://banks.data.fdic.gov/api"
PIT_LAG_DAYS = 60          # signal date = report_date + 60d (worst-case FDIC bulk lag; 45d pre-2026-07-08)
RATE_LIMIT_SEC = 0.4       # stay well inside FDIC rate limits
MAX_RETRIES = 3
TIMEOUT = 30

FIELDS = [
    "CERT", "REPDTE", "ASSET", "EQ", "DEP", "DEPINS", "DEPUNINS", "COREDEP",
    "LNNDEPC", "LNLSNET", "LNRECONS", "LNRENRES", "LNREMULT",
    "NCRENRER", "NCRECONR", "SC", "RSSDHCR", "NAME", "NAMEHCR",
]

# Ticker -> (primary CERT, parent RSSDHCR, BHC name)
# Verified via FDIC BankFind API institutions endpoint, 2026-07-07.
# RSSDHCR is the parent holding company RSSD — used to aggregate all bank
# subsidiaries under the same BHC. Primary CERT is the largest-asset sub.
TICKER_CERT_MAP: dict[str, tuple[int, int, str]] = {
    "RF":    (12368,  3242838, "REGIONS FINANCIAL CORP"),
    "KEY":   (17534,  1068025, "KEYCORP"),
    "CFG":   (57957,  1132449, "CITIZENS FINANCIAL GROUP INC"),
    "HBAN":  (6560,   1068191, "HUNTINGTON BANCSHARES INC"),
    "FITB":  (6672,   1070345, "FIFTH THIRD BCORP"),
    "MTB":   (588,    1037003, "M&T BANK CORP"),
    "TFC":   (9846,   1074156, "TRUIST FINANCIAL CORP"),
    "USB":   (6548,   1119794, "U S BCORP"),
    "PNC":   (6384,   1069778, "PNC FINL SERVICES GROUP INC"),
    "WAL":   (57512,  2349815, "WESTERN ALLIANCE BCORP"),
    "EWBC":  (31628,  2734233, "EAST WEST BCORP INC"),
    "CFR":   (5510,   1102367, "CULLEN FROST BANKERS INC"),
    "FHN":   (4977,   1094640, "FIRST HORIZON CORP"),
    "WTFC":  (33935,  2260406, "WINTRUST FINANCIAL CORP"),
    "WBS":   (18221,  1145476, "WEBSTER FINANCIAL CORP"),
    "SSB":   (33555,  1133437, "SOUTHSTATE BANK CORP"),
    "UMBF":  (8273,   1049828, "UMB FINANCIAL CORP"),
    "BPOP":  (34968,  1129382, "POPULAR INC"),
    "COLB":  (17266,  2078816, "COLUMBIA BANKING SYSTEM INC"),
    "FCNCA": (11063,  1075612, "FIRST CITIZENS BANCSHARES INC"),
}

# Failed banks retained for survivorship-bias correction (FRC/SIVB-era rule).
# All three failed in 2023 and stop reporting after their last quarter —
# missing quarters after last_repdte are EXPECTED, not collection errors.
# CERTs verified against the live FDIC institutions API 2026-07-08:
#   SIVB -> Silicon Valley Bank, CERT 24735, RSSDHCR 1031449 (SVB FINANCIAL GROUP)
#   SBNY -> Signature Bank,      CERT 57053, no holding company (RSSDHCR empty)
#   FRC  -> First Republic Bank, CERT 59017, no holding company (RSSDHCR empty)
# Fetched per-CERT (each was effectively a single-charter BHC) rather than via
# the RSSDHCR sweep — SBNY/FRC have no RSSDHCR to filter on.
# Ticker -> (primary CERT, RSSDHCR or None, name, fail/delisting date,
#            last FDIC report quarter)
FAILED_TICKER_CERT_MAP: dict[str, tuple[int, int | None, str, str, str]] = {
    "SIVB": (24735, 1031449, "SVB FINANCIAL GROUP",  "2023-03-10", "20221231"),
    "SBNY": (57053, None,    "SIGNATURE BANK NY",    "2023-03-12", "20221231"),
    "FRC":  (59017, None,    "FIRST REPUBLIC BANK",  "2023-05-01", "20230331"),
}

# Quarter-end dates to fetch (2018-Q1 to 2026-Q1)
def _quarter_dates(start_yq: str = "2018-Q1", end_yq: str = "2026-Q1") -> list[str]:
    """Return list of YYYYMMDD quarter-end dates."""
    quarters = {"Q1": "0331", "Q2": "0630", "Q3": "0930", "Q4": "1231"}
    out = []
    sy, sq = start_yq.split("-")
    ey, eq = end_yq.split("-")
    q_order = ["Q1", "Q2", "Q3", "Q4"]
    y, qi = int(sy), q_order.index(sq)
    ey_int, eq_i = int(ey), q_order.index(eq)
    while (y < ey_int) or (y == ey_int and qi <= eq_i):
        q = q_order[qi]
        out.append(f"{y}{quarters[q]}")
        qi += 1
        if qi == 4:
            qi = 0
            y += 1
    return out


def _fdic_get(endpoint: str, params: dict, retries: int = MAX_RETRIES) -> dict:
    url = f"{FDIC_BASE}/{endpoint}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                raise
            log.warning("FDIC API retry %d: %s", attempt + 1, e)
            time.sleep(2 ** attempt)
    return {}


def _fetch_quarter(repdte: str, rssd_ids: list[int]) -> list[dict]:
    """Fetch FDIC financials for all subsidiary CERTs linked to our BHCs
    for a given quarter. Uses RSSDHCR filter to get all subsidiaries."""
    # Build the filter: all known RSSDHCR values
    rssd_filter = " OR ".join(f"RSSDHCR:{r}" for r in rssd_ids)
    params = {
        "filters": f"REPDTE:{repdte} AND ({rssd_filter})",
        "fields": ",".join(FIELDS),
        "limit": 500,
        "offset": 0,
        "output": "json",
    }
    all_rows = []
    while True:
        data = _fdic_get("financials", params)
        rows = data.get("data", [])
        all_rows.extend(r["data"] for r in rows)
        total = data.get("meta", {}).get("total", 0)
        params["offset"] += len(rows)
        if params["offset"] >= total or not rows:
            break
        time.sleep(RATE_LIMIT_SEC)
    return all_rows


def _fetch_failed_bank(cert: int, start_repdte: str, last_repdte: str) -> list[dict]:
    """Fetch all quarters for a single failed bank by CERT in one request.
    Failed banks have frozen historical data and (for SBNY/FRC) no RSSDHCR,
    so the survivor RSSDHCR sweep cannot reach them."""
    params = {
        "filters": f"CERT:{cert} AND REPDTE:[{start_repdte} TO {last_repdte}]",
        "fields": ",".join(FIELDS),
        "limit": 200,
        "sort_by": "REPDTE",
        "sort_order": "ASC",
    }
    data = _fdic_get("financials", params)
    return [r["data"] for r in data.get("data", [])]


def _failed_bank_rows(ticker: str, name: str, fail_date: str,
                      raw_rows: list[dict]) -> list[dict]:
    """Build panel rows for a single-charter failed bank. Mirrors
    _aggregate_to_bhc for n_charters=1 (verified equivalent construction to
    w3_bank_callreport_stress_phase0._build_failed_bank_rows), plus failure
    metadata columns."""
    numeric = [c for c in FIELDS if c not in ("CERT", "REPDTE", "NAME", "NAMEHCR", "RSSDHCR")]
    out = []
    for d in raw_rows:
        row: dict = {
            "ticker": ticker,
            "repdte": str(d.get("REPDTE")),
            "n_charters": 1,
            "namehcr": name,
            "is_failed_bank": True,
            "fail_date": fail_date,
        }
        for col in numeric:
            v = pd.to_numeric(d.get(col), errors="coerce")
            row[col.lower()] = 0.0 if pd.isna(v) else float(v)
        if row.get("asset", 0) > 0:
            row["unins_dep_share"] = row.get("depunins", 0) / row["asset"]
            row["brkd_dep_share"] = (row.get("lnndepc", 0) / row["dep"]
                                     if row.get("dep", 0) > 0 else float("nan"))
            row["cre_total"] = (row.get("lnrecons", 0) +
                                row.get("lnrenres", 0) +
                                row.get("lnremult", 0))
            row["cre_to_equity"] = row["cre_total"] / max(row.get("eq", 1), 1)
            row["cre_to_asset"] = row["cre_total"] / row["asset"]
            row["nonfarm_nres_cre"] = row.get("lnrenres", 0)
            row["cnd_cre"] = row.get("lnrecons", 0)
        row["ncrenrer_wavg"] = row.get("ncrenrer", 0.0)
        out.append(row)
    return out


def _resolve_rssd_ids(tickers: list[str]) -> dict[str, int]:
    """Return ticker -> RSSDHCR map from the pre-verified crosswalk.
    Falls back to a live FDIC institutions API call if the RSSDHCR stored in
    TICKER_CERT_MAP is 0 (not yet verified)."""
    ticker_rssdhcr = {}
    for ticker, (cert, rssdhcr, _name) in TICKER_CERT_MAP.items():
        if ticker not in tickers:
            continue
        if rssdhcr:
            ticker_rssdhcr[ticker] = rssdhcr
            log.info("  %s -> CERT %d -> RSSDHCR %d (pre-verified)", ticker, cert, rssdhcr)
        else:
            # Fallback: live lookup
            params = {"filters": f"CERT:{cert}", "fields": "CERT,RSSDHCR,NAME,NAMEHCR", "limit": 1}
            try:
                data = _fdic_get("institutions", params)
                rows = data.get("data", [])
                if rows:
                    live_rssd = rows[0]["data"].get("RSSDHCR")
                    if live_rssd:
                        ticker_rssdhcr[ticker] = int(live_rssd)
                        log.info("  %s -> CERT %d -> RSSDHCR %d (live lookup)", ticker, cert, live_rssd)
                    else:
                        log.warning("  %s: RSSDHCR None, using CERT %d as key", ticker, cert)
                        ticker_rssdhcr[ticker] = cert
            except Exception as e:
                log.error("  %s resolution failed: %s", ticker, e)
            time.sleep(RATE_LIMIT_SEC)
    return ticker_rssdhcr


def _aggregate_to_bhc(rows: list[dict], rssd_to_ticker: dict[int, str]) -> list[dict]:
    """Aggregate bank-subsidiary rows to BHC level by RSSDHCR."""
    if not rows:
        return []
    df = pd.DataFrame(rows)
    numeric = [c for c in FIELDS if c not in ("CERT", "REPDTE", "NAME", "NAMEHCR", "RSSDHCR")]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    # Group by RSSDHCR (parent BHC) and REPDTE
    grp = df.groupby(["RSSDHCR", "REPDTE"])
    out = []
    for (rssdhcr, repdte), g in grp:
        ticker = rssd_to_ticker.get(int(rssdhcr))
        if ticker is None:
            continue
        row = {
            "ticker": ticker,
            "repdte": str(repdte),
            "n_charters": len(g),
            "namehcr": g["NAMEHCR"].iloc[0] if "NAMEHCR" in g else "",
        }
        for col in numeric:
            if col in g.columns:
                row[col.lower()] = g[col].sum()
        # Compute ratio fields AFTER summing (not sum-of-ratios)
        if row.get("asset", 0) > 0:
            row["unins_dep_share"] = row.get("depunins", 0) / row["asset"]
            row["brkd_dep_share"] = row.get("lnndepc", 0) / row.get("dep", 1)
            row["cre_total"] = (row.get("lnrecons", 0) +
                                 row.get("lnrenres", 0) +
                                 row.get("lnremult", 0))
            row["cre_to_equity"] = row["cre_total"] / max(row.get("eq", 1), 1)
            row["cre_to_asset"] = row["cre_total"] / row["asset"]
            row["nonfarm_nres_cre"] = row.get("lnrenres", 0)
            row["cnd_cre"] = row.get("lnrecons", 0)
        # Weighted-average NC rate (by LNRENRES)
        if "NCRENRER" in g.columns and "LNRENRES" in g.columns:
            weights = g["LNRENRES"].fillna(0)
            wsum = weights.sum()
            if wsum > 0:
                row["ncrenrer_wavg"] = (g["NCRENRER"].fillna(0) * weights).sum() / wsum
            else:
                row["ncrenrer_wavg"] = g["NCRENRER"].mean()
        out.append(row)
    return out


def collect(
    start_yq: str = "2018-Q1",
    end_yq: str = "2026-Q1",
    resume: bool = True,
    dry_run: bool = False,
) -> pd.DataFrame:
    out_dir = ROOT / "data" / "ffiec_y9c"
    out_dir.mkdir(parents=True, exist_ok=True)
    panel_path = out_dir / "bhc_panel.parquet"
    map_path = out_dir / "bhc_ticker_map.csv"

    tickers = list(TICKER_CERT_MAP.keys())
    quarters = _quarter_dates(start_yq, end_yq)
    log.info("Collecting %d quarters × %d tickers", len(quarters), len(tickers))

    # Step 1: resolve RSSD IDs
    log.info("Resolving RSSDHCR IDs via FDIC institutions API...")
    ticker_rssdhcr = _resolve_rssd_ids(tickers)
    rssd_to_ticker = {v: k for k, v in ticker_rssdhcr.items()}

    # Build and save crosswalk map CSV
    map_rows = []
    for t in tickers:
        cert, rssdhcr_stored, name = TICKER_CERT_MAP[t]
        rssd = ticker_rssdhcr.get(t, rssdhcr_stored)
        map_rows.append({
            "ticker": t, "bhc_name": name,
            "primary_cert": cert, "rssdhcr": rssd,
            "fail_date": "",
        })
    for t, (cert, rssdhcr, name, fail_date, _last) in FAILED_TICKER_CERT_MAP.items():
        map_rows.append({
            "ticker": t, "bhc_name": name,
            "primary_cert": cert,
            "rssdhcr": rssdhcr if rssdhcr is not None else "",
            "fail_date": fail_date,
        })
    map_df = pd.DataFrame(map_rows)
    map_df.to_csv(map_path, index=False)
    log.info("Crosswalk saved -> %s (%d rows)", map_path, len(map_df))

    if dry_run:
        log.info("[DRY-RUN] Stopping after crosswalk resolution.")
        return map_df

    # Step 2: determine which quarters to skip (resume logic)
    existing: pd.DataFrame | None = None
    done_quarters: set[str] = set()
    if resume and panel_path.exists():
        existing = pd.read_parquet(panel_path)
        done_quarters = set(existing["repdte"].unique()) if "repdte" in existing.columns else set()
        log.info("Resuming: %d quarters already in panel", len(done_quarters))

    # Step 3: fetch each quarter
    rssd_ids = [v for v in ticker_rssdhcr.values() if v]
    all_bhc_rows: list[dict] = []
    for i, repdte in enumerate(quarters):
        if repdte in done_quarters:
            log.info("  SKIP %s (already fetched)", repdte)
            continue
        log.info("  [%d/%d] fetching %s ...", i + 1, len(quarters), repdte)
        try:
            raw_rows = _fetch_quarter(repdte, rssd_ids)
            bhc_rows = _aggregate_to_bhc(raw_rows, rssd_to_ticker)
            all_bhc_rows.extend(bhc_rows)
            log.info("    -> %d sub-charters -> %d BHC rows", len(raw_rows), len(bhc_rows))
        except Exception as e:
            log.error("    FAILED %s: %s", repdte, e)
        time.sleep(RATE_LIMIT_SEC)

    # Step 3b: failed-bank backfill (per-CERT — outside the RSSDHCR sweep).
    # Resume is per (ticker, quarter): only quarters up to each bank's
    # last_repdte are expected; later quarters are missing by construction.
    existing_pairs: set[tuple[str, str]] = set()
    if existing is not None and {"ticker", "repdte"} <= set(existing.columns):
        existing_pairs = set(zip(existing["ticker"], existing["repdte"].astype(str)))
    for ticker, (cert, _rssdhcr, name, fail_date, last_repdte) in FAILED_TICKER_CERT_MAP.items():
        expected_q = [q for q in quarters if q <= last_repdte]
        if not expected_q:
            continue
        missing_q = [q for q in expected_q if (ticker, q) not in existing_pairs]
        if not missing_q:
            log.info("  SKIP %s (all %d pre-failure quarters already in panel)",
                     ticker, len(expected_q))
            continue
        log.info("  fetching failed bank %s (CERT %d, failed %s): %d missing quarters",
                 ticker, cert, fail_date, len(missing_q))
        try:
            raw = _fetch_failed_bank(cert, quarters[0], last_repdte)
            rows = [r for r in _failed_bank_rows(ticker, name, fail_date, raw)
                    if r["repdte"] in missing_q]
            all_bhc_rows.extend(rows)
            log.info("    -> %d rows (reporting ends %s; later quarters expected missing)",
                     len(rows), last_repdte)
        except Exception as e:
            log.error("    FAILED %s: %s", ticker, e)
        time.sleep(RATE_LIMIT_SEC)

    # Step 4: combine with existing and save
    new_df = pd.DataFrame(all_bhc_rows) if all_bhc_rows else pd.DataFrame()
    if existing is not None and not new_df.empty:
        panel = pd.concat([existing, new_df], ignore_index=True)
    elif existing is not None:
        panel = existing
    else:
        panel = new_df

    if panel.empty:
        log.error("Panel is empty — no data collected.")
        return panel

    # Parse and add PIT-enforced signal date
    panel["report_date"] = pd.to_datetime(panel["repdte"], format="%Y%m%d")
    panel["signal_date"] = panel["report_date"] + pd.Timedelta(days=PIT_LAG_DAYS)
    # Failure metadata (False/None for survivors, incl. pre-backfill panels)
    if "is_failed_bank" not in panel.columns:
        panel["is_failed_bank"] = False
    panel["is_failed_bank"] = panel["is_failed_bank"].fillna(False).astype(bool)
    if "fail_date" not in panel.columns:
        panel["fail_date"] = None
    panel["fail_date"] = panel["fail_date"].where(panel["fail_date"].notna(), None)
    panel = panel.sort_values(["ticker", "report_date"]).reset_index(drop=True)
    # Deduplicate
    panel = panel.drop_duplicates(subset=["ticker", "repdte"]).reset_index(drop=True)

    panel.to_parquet(panel_path, index=False)
    log.info("Panel saved -> %s (%d rows, %d quarters, %d tickers)",
             panel_path, len(panel),
             panel["repdte"].nunique(), panel["ticker"].nunique())

    # Coverage report — expected-quarter aware: failed banks stop reporting
    # after their operational end date, so their expected count is truncated.
    cov = panel.groupby("ticker")["repdte"].count()
    log.info("Per-ticker quarter coverage:\n%s", cov.to_string())
    expected_by_ticker = {t: len(quarters) for t in tickers}
    for t, (_c, _r, _n, fail_date, last_repdte) in FAILED_TICKER_CERT_MAP.items():
        expected_by_ticker[t] = len([q for q in quarters if q <= last_repdte])
        log.info("  %s: failed %s — expects %d/%d quarters (reporting ends %s)",
                 t, fail_date, expected_by_ticker[t], len(quarters), last_repdte)
    short = {t: (int(cov.get(t, 0)), n_exp)
             for t, n_exp in expected_by_ticker.items()
             if int(cov.get(t, 0)) < n_exp}
    if short:
        log.warning("UNDER-COVERED tickers (have/expected): %s", short)

    return panel


def main() -> None:
    parser = argparse.ArgumentParser(description="FR Y-9C (FDIC) bank panel collector")
    parser.add_argument("--start", default="2018-Q1", help="Start quarter e.g. 2018-Q1")
    parser.add_argument("--end", default="2026-Q1", help="End quarter e.g. 2026-Q1")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Skip already-fetched quarters")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only resolve crosswalk, do not fetch financials")
    args = parser.parse_args()
    collect(start_yq=args.start, end_yq=args.end,
            resume=args.resume, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
