"""One-time (resumable) paced batch re-crawl of SEC EDGAR companyfacts to extract
QUARTERLY financial statement data for the ~1,334-name fundamentals universe.

Deliverable: data/edgar/statements_quarterly.parquet
  Schema: ticker, fiscal_year (int), fiscal_quarter (int 1-4), period_end (date),
          filed (date), revenue, cogs, gross_profit, op_income, ni, cfo, capex,
          shares (CommonStockSharesOutstanding), repurchases (PaymentsForRepurchaseOfCommonStock),
          long_term_debt (LongTermDebtNoncurrent), current_debt (DebtCurrent→LongTermDebtCurrent),
          cash (CashAndCashEquivalentsAtCarryingValue),
          net_debt (= long_term_debt + current_debt − cash; None when no debt tags present),
          receivables (AccountsReceivableNetCurrent → ReceivablesNetCurrent),
          inventory (InventoryNet),
          payables (AccountsPayableCurrent → AccountsPayableAndAccruedLiabilitiesCurrent
                    → AccountsPayableTradeCurrent),
          contract_liabilities (ContractWithCustomerLiabilityCurrent →
                                ContractWithCustomerLiability → DeferredRevenueCurrent
                                → DeferredRevenue),
          as_of (ISO timestamp)

  LHB-R6 additions (2026-07-12): receivables, inventory, payables, contract_liabilities.
    receivables and inventory chains are kept tag-consistent with collectors/edgar_facts.py
    BALANCE dict (annual store); the annual chains are authoritative for those two fields.
    Gates: A2 receivables leg, A5 accrual, B2 working-capital exclusion.

  Dedup rule: for each (ticker, fiscal_year, fiscal_quarter) key, the LATEST-FILED row wins
              on re-runs (idempotent; restatements update the stored value).

PACING
------
SEC fair-access policy: <= 10 requests/second; we target ~8 req/s (0.12 s sleep between
calls — same as the existing edgar_facts.py).  Total crawl time at 0.12 s/filer × 1,334
filers ≈ 160 s for the pure HTTP time plus JSON parsing, realistically ~5–8 minutes.

USAGE
-----
  # Full crawl (resumable; picks up where it left off):
  python -m scripts.backfill_edgar_quarterly

  # First 100 names only (validation / partial run):
  python -m scripts.backfill_edgar_quarterly --max 100

  # Force re-fetch even recently fetched names:
  python -m scripts.backfill_edgar_quarterly --force

  # Target specific tickers:
  python -m scripts.backfill_edgar_quarterly --tickers AAPL MSFT GOOGL

  IMPORTANT — enriching an existing store: if the store was built before LHB-R6
  (2026-07-12), the four new columns (receivables, inventory, payables,
  contract_liabilities) will be NaN for all already-fetched rows because the
  REFRESH_DAYS skip logic will bypass them.  Run --force to re-fetch the full
  universe and populate the new columns:
    python -m scripts.backfill_edgar_quarterly --force

DOWNSTREAM
----------
Wire nothing downstream yet (§7 W0.6c: "Wire nothing downstream.").
S10 (Margin-Inflection Reclaim) and S11 (Buyback-Floor Washout) gate on this store
existing — their gating.come_back_on date should be set to the projected completion date
of this crawl.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("backfill_edgar_quarterly")

import pandas as pd

from lib import config

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
REFRESH_DAYS = 30
PACE_S = 0.12

# ── concept fallback chains ──────────────────────────────────────────────────
# FLOW: extracted as full-quarter periods (fp="Q1"/"Q2"/"Q3"/"Q4" or quarterly slices
# by period length: 80-100 days).  For quarterly P&L we prefer the dedicated quarterly
# filings (10-Q), but many filers tag cumulative YTD on 10-Qs; we detect full-quarter
# entries by keeping fp in {"Q1","Q2","Q3","Q4"} only.
FLOW_Q = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "op_income": ["OperatingIncomeLoss"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"],
}
# BALANCE / INSTANT: as-of the fiscal quarter-end date.
BALANCE_Q = {
    "shares": ["CommonStockSharesOutstanding"],
}
# FLOW concept added per spec (PaymentsForRepurchaseOfCommonStock → repurchases).
REPURCHASE_Q = {
    "repurchases": ["PaymentsForRepurchaseOfCommonStock",
                    "PaymentsForRepurchaseOfEquity"],
}
# BALANCE / INSTANT (USD): debt + cash, as-of the fiscal quarter-end date.  Needed
# for the S11 (Buyback-Floor Washout) rejection rule "net-debt rising concurrent with
# buyback → demote to context" — the debt-funded-buyback failure mode.  net_debt is
# derived per row (long_term_debt + current_debt − cash).  current_debt prefers the
# total DebtCurrent tag and falls back to LongTermDebtCurrent (current portion of LTD
# only) when DebtCurrent is untagged — a documented undercount for names with untagged
# short-term borrowings, acceptable for the QoQ *direction* the rule keys on.
BALANCE_USD_Q = {
    "long_term_debt": ["LongTermDebtNoncurrent"],
    "current_debt": ["DebtCurrent", "LongTermDebtCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
}
# BALANCE / INSTANT (USD): working-capital receivables, inventory, payables,
# and deferred revenue.  Added per LHB-R6 (2026-07-12) to gate A2 receivables
# leg, A5 accrual, and B2 working-capital exclusion.
#
# receivables and inventory chains are tag-consistent with the annual collector
# (collectors/edgar_facts.py BALANCE dict) — the annual chains are authoritative
# for those two fields so both stores can be compared without tag mismatch.
#
# SCOPE CAVEAT (mirrors the current_debt disclosure above): the payables fallback
# AccountsPayableAndAccruedLiabilitiesCurrent bundles accrued liabilities (a
# superset of trade payables), and contract_liabilities falls back to TOTAL-scope
# tags (ContractWithCustomerLiability, DeferredRevenue = current + noncurrent)
# when the *Current tags are absent. First-non-null resolves per (fy, fq), so a
# filer migrating tags can switch scope BETWEEN quarters — a spurious QoQ jump at
# the migration boundary. Acceptable for the direction-reads these gate (A2/B2);
# any consumer computing levels must check which concept served each quarter.
# Also: balance instants tagged fp="FY" (not fp="Q4") on some 10-Ks are excluded
# by the QUARTERLY_FP filter (same as cash/debt/shares) — those filers carry Q4
# holes in all instant fields; a false-negative, never a contaminated value.
BALANCE_WORKINGCAP_Q = {
    # Chains match collectors/edgar_facts.py BALANCE["receivables"] exactly.
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    # Chains match collectors/edgar_facts.py BALANCE["inventory"] exactly.
    "inventory": ["InventoryNet"],
    "payables": ["AccountsPayableCurrent",
                 "AccountsPayableAndAccruedLiabilitiesCurrent",
                 "AccountsPayableTradeCurrent"],
    "contract_liabilities": ["ContractWithCustomerLiabilityCurrent",
                              "ContractWithCustomerLiability",
                              "DeferredRevenueCurrent",
                              "DeferredRevenue"],
}
QUARTERLY_FP = {"Q1", "Q2", "Q3", "Q4"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A"}  # 10-K includes Q4 quarterly data


def _get_json(url: str, ua: str, retries: int = 3):
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": ua,
                                           "Accept-Encoding": "gzip, deflate"}, timeout=40)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                log.debug("companyfacts GET failed %s: %s", url[-24:], e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def _quarterly(entries: list, instant: bool = False) -> list[dict]:
    """Extract quarterly entries → list of {fy, fq, period_end, filed, val}.

    For FLOW (income statement / cash flow) concepts: keep only entries with
    fp ∈ {Q1,Q2,Q3,Q4} (single-quarter, not cumulative YTD).  Additionally
    filter to ~80-100 day periods as a robustness check for mislabeled entries.

    For INSTANT (balance sheet) concepts: keep fp ∈ {Q1,Q2,Q3,Q4}, any duration.
    Latest-filed wins on (fy, fq) key.
    """
    best: dict[tuple, tuple] = {}   # (fy, fq) → (rank, val, period_end, filed)
    for e in entries or []:
        fp = e.get("fp", "")
        if fp not in QUARTERLY_FP:
            continue
        form = e.get("form", "")
        if form not in QUARTERLY_FORMS:
            continue
        fy = e.get("fy")
        val = e.get("val")
        end = e.get("end")
        filed = e.get("filed", "")
        if fy is None or val is None or not end:
            continue

        # Map fp → fiscal quarter integer
        fq = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}[fp]

        if not instant:
            start = e.get("start")
            if not start:
                continue
            try:
                days = (pd.to_datetime(end) - pd.to_datetime(start)).days
            except Exception:  # noqa: BLE001
                continue
            if not (75 <= days <= 105):   # single quarter ± tolerance
                continue

        key = (int(fy), fq)
        rank = (filed, end)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, float(val), end, filed)

    result = []
    for (fy, fq), (_, val, end, filed) in sorted(best.items()):
        result.append({"fy": fy, "fq": fq, "period_end": end, "filed": filed, "val": val})
    return result


def _concept_q(usgaap: dict, names: list[str], unit: str = "USD",
               instant: bool = False) -> dict[tuple, dict]:
    """Merge fallback chain → {(fy, fq): {val, period_end, filed}}."""
    combined: dict[tuple, dict] = {}
    for nm in names:
        node = usgaap.get(nm)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        for rec in _quarterly(entries, instant=instant):
            key = (rec["fy"], rec["fq"])
            combined.setdefault(key, {"val": rec["val"],
                                      "period_end": rec["period_end"],
                                      "filed": rec["filed"]})
    return combined


def _statements_quarterly(cik: int, ua: str) -> list[dict]:
    """Per-fiscal-quarter rows for one filer."""
    data = _get_json(FACTS_URL.format(cik), ua)
    time.sleep(PACE_S)
    if not data:
        return []
    usgaap = (data.get("facts") or {}).get("us-gaap") or {}
    if not usgaap:
        return []

    # Extract each concept group
    series: dict[str, dict[tuple, dict]] = {}
    for key, names in FLOW_Q.items():
        series[key] = _concept_q(usgaap, names, instant=False)
    for key, names in BALANCE_Q.items():
        series[key] = _concept_q(usgaap, names, unit="shares", instant=True)
    for key, names in BALANCE_USD_Q.items():
        series[key] = _concept_q(usgaap, names, unit="USD", instant=True)
    for key, names in REPURCHASE_Q.items():
        series[key] = _concept_q(usgaap, names, instant=False)
    # LHB-R6 (2026-07-12): working-capital balance sheet fields
    for key, names in BALANCE_WORKINGCAP_Q.items():
        series[key] = _concept_q(usgaap, names, unit="USD", instant=True)

    # Collect all (fy, fq) keys across all concepts
    all_keys: set[tuple] = set()
    for s in series.values():
        all_keys.update(s.keys())

    rows = []
    for (fy, fq) in sorted(all_keys):
        row: dict = {"fiscal_year": fy, "fiscal_quarter": fq}
        period_end = None
        filed = None
        for key, s in series.items():
            entry = s.get((fy, fq))
            if entry:
                row[key] = entry["val"]
                if period_end is None:
                    period_end = entry["period_end"]
                if filed is None:
                    filed = entry["filed"]
            else:
                row[key] = None
        # Derive missing combos
        if row.get("gross_profit") is None and row.get("revenue") is not None and row.get("cogs") is not None:
            row["gross_profit"] = row["revenue"] - row["cogs"]
        if row.get("revenue") is None and row.get("gross_profit") is not None and row.get("cogs") is not None:
            row["revenue"] = row["gross_profit"] + row["cogs"]
        # Derive net_debt = total debt − cash.  None only when NO debt tag is present
        # (a missing single component is treated as 0; missing cash is treated as 0 —
        # documented in BALANCE_USD_Q: the QoQ direction, not the absolute level, binds).
        ltd, cur, csh = row.get("long_term_debt"), row.get("current_debt"), row.get("cash")
        if ltd is None and cur is None:
            row["net_debt"] = None
        else:
            row["net_debt"] = (ltd or 0.0) + (cur or 0.0) - (csh or 0.0)
        row["period_end"] = period_end
        row["filed"] = filed
        rows.append(row)
    return rows


def _cik_map() -> dict[str, int]:
    fp = config.data_dir() / "edgar" / "fundamentals.parquet"
    if not fp.exists():
        log.error("edgar/fundamentals.parquet missing — run the edgar_facts collector first")
        return {}
    try:
        df = pd.read_parquet(fp, columns=["cik"])
    except Exception:  # noqa: BLE001
        return {}
    return {str(t): int(r["cik"]) for t, r in df.iterrows() if pd.notna(r.get("cik"))}


def _out_path() -> Path:
    p = config.data_dir() / "edgar" / "statements_quarterly.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run(
    max_tickers: int | None = None,
    force: bool = False,
    tickers: list[str] | None = None,
) -> dict:
    """Crawl EDGAR quarterly statements; write/update statements_quarterly.parquet.

    Args:
        max_tickers: stop after N tickers (for partial / validation runs).
        force: re-fetch even recently fetched tickers.
        tickers: restrict to specific tickers (skip the rest of the universe).

    Returns progress dict.
    """
    ua = config.load().get("edgar", {}).get("user_agent",
                           "macro-dashboard-research bot@example.com")
    cik_map = _cik_map()
    if not cik_map:
        return {"error": "no_cik_map"}

    universe = tickers or list(cik_map)
    out_p = _out_path()
    now = datetime.now(timezone.utc).isoformat()

    # Load existing to check staleness / skip
    existing = pd.read_parquet(out_p) if out_p.exists() else pd.DataFrame()

    def _recently_fetched(t: str) -> bool:
        if force or existing.empty or "ticker" not in existing.columns:
            return False
        sub = existing[existing["ticker"] == t]
        if sub.empty or "as_of" not in sub.columns:
            return False
        try:
            age_days = (datetime.now(timezone.utc) -
                        pd.to_datetime(sub["as_of"].max(), utc=True)).days
            return age_days < REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return False

    todo = [t for t in universe if t in cik_map and not _recently_fetched(t)]
    if max_tickers:
        todo = todo[:max_tickers]

    log.info("edgar_quarterly: %d universe, %d to fetch (max=%s, force=%s)",
             len(universe), len(todo), max_tickers, force)

    new_rows: list[dict] = []
    ok = failed = 0

    t0 = time.time()
    for i, ticker in enumerate(todo, 1):
        rows = _statements_quarterly(cik_map[ticker], ua)
        if rows:
            for r in rows:
                r["ticker"] = ticker
                r["as_of"] = now
            new_rows.extend(rows)
            ok += 1
        else:
            failed += 1
            log.debug("edgar_quarterly: no data for %s", ticker)

        if i % 50 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            remaining = (len(todo) - i) / rate / 60
            log.info(
                "edgar_quarterly: %d/%d done (%.0f/min, ~%.0f min remaining)",
                i, len(todo), rate * 60, remaining,
            )

    if not new_rows:
        log.info("edgar_quarterly: no new rows fetched")
        return {"ok": ok, "failed": failed, "rows_added": 0}

    fresh = pd.DataFrame(new_rows)
    # Dedup within the new batch: latest-filed wins per (ticker, fy, fq)
    fresh = (fresh
             .sort_values("filed", na_position="first")
             .drop_duplicates(subset=["ticker", "fiscal_year", "fiscal_quarter"],
                              keep="last"))

    if not existing.empty:
        # Remove existing rows for tickers we just re-fetched, then append fresh.
        # Column-superset safety (LHB-R6): if fresh has new columns (e.g. receivables,
        # inventory, payables, contract_liabilities) that existing lacks, pd.concat fills
        # the missing columns in the existing slice with NaN — no KeyError, no data loss.
        # Old rows for non-refreshed tickers remain with NaN for the new columns until
        # those tickers are re-fetched (use --force to refresh the full universe).
        refreshed_tickers = fresh["ticker"].unique()
        existing = existing[~existing["ticker"].isin(refreshed_tickers)]
        combined = pd.concat([existing, fresh], ignore_index=True)
    else:
        combined = fresh

    # Final dedup (belt-and-suspenders): latest-filed wins per (ticker, fy, fq)
    combined = (combined
                .sort_values("filed", na_position="first")
                .drop_duplicates(subset=["ticker", "fiscal_year", "fiscal_quarter"],
                                 keep="last")
                .reset_index(drop=True))

    # A batch whose new working-capital columns are all-None would otherwise be
    # inferred object → written as an Arrow null-typed column, which strict
    # schema-union readers choke on. Coerce to float64 before write.
    for _wc in BALANCE_WORKINGCAP_Q:
        if _wc in combined.columns:
            combined[_wc] = pd.to_numeric(combined[_wc], errors="coerce")

    combined.to_parquet(out_p, index=False)
    n_t = combined["ticker"].nunique()
    log.info("edgar_quarterly: wrote %d ticker-quarters for %d tickers → %s",
             len(combined), n_t, out_p)

    return {
        "ok": ok,
        "failed": failed,
        "rows_added": len(fresh),
        "total_rows": len(combined),
        "total_tickers": n_t,
        "store": str(out_p),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=None,
                    help="stop after N tickers (default: full universe of ~1,334)")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch tickers fetched within REFRESH_DAYS")
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="restrict to specific ticker(s)")
    ap.add_argument("--estimate", action="store_true",
                    help="print projected completion time without fetching")
    args = ap.parse_args()

    if args.estimate:
        cik_map = _cik_map()
        n = len(cik_map)
        mins = n * (PACE_S + 0.3) / 60  # 0.3s for JSON parse + write
        log.info("Projected completion: %d filers × %.2fs ≈ %.0f minutes",
                 n, PACE_S + 0.3, mins)
        return 0

    result = run(max_tickers=args.max, force=args.force, tickers=args.tickers)
    import json
    print(json.dumps(result, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
