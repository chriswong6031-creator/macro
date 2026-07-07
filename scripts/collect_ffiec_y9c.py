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
  restricting signal date to report_date + PIT_LAG_DAYS = 45.

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

Universe: 20 regional_banks basket tickers, 2018-Q1 to 2026-Q1.
          Span covers ~32 quarters including the Mar-2023 stress episode.

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
PIT_LAG_DAYS = 45          # signal date = report_date + 45d
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
    panel = panel.sort_values(["ticker", "report_date"]).reset_index(drop=True)
    # Deduplicate
    panel = panel.drop_duplicates(subset=["ticker", "repdte"]).reset_index(drop=True)

    panel.to_parquet(panel_path, index=False)
    log.info("Panel saved -> %s (%d rows, %d quarters, %d tickers)",
             panel_path, len(panel),
             panel["repdte"].nunique(), panel["ticker"].nunique())

    # Coverage report
    cov = panel.groupby("ticker")["repdte"].count()
    log.info("Per-ticker quarter coverage:\n%s", cov.to_string())
    missing = [t for t in tickers if t not in cov.index]
    if missing:
        log.warning("MISSING tickers (no data found): %s", missing)

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
