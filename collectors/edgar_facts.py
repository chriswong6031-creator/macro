"""SEC EDGAR companyfacts → multi-year financial statements per stock (Phase 2 of
research/STOCK_FUNDAMENTALS_PLAN.md).

The frames API (collectors/edgar.py) gives ONE latest-FY cross-section. To draw the
analyzer's Financials TRENDS (revenue/margins/EPS/FCF over ~5 years) and the health
scores (Piotroski F, Altman Z), we need per-filer HISTORY — that's the companyfacts
API: data.sec.gov/api/xbrl/companyfacts/CIK{10}.json returns a filer's full XBRL
history in one keyless call. We pull a small concept set, keep the last ~5 fiscal
years, and write a slim LONG-format table data/edgar/statements.parquet
(one row per ticker-fiscal-year). engine/stock_fundamentals consumes it.

KEYLESS but PAYLOAD-bound (3.5-7.5 MB/filer) — so this is a WEEKLY, resumable,
capped drip (skip filers fetched within refresh_days), never a per-build fetch.
Honest caveats (shown on the page): values are lagged to the filing date; some
concepts are sparse on smaller filers (custom tags) — those years simply omit them.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
REFRESH_DAYS = 30
KEEP_YEARS = 6

# concept fallback chains (first populated wins). USD unless noted.
FLOW = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "op_income": ["OperatingIncomeLoss"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "interest_exp": ["InterestExpense", "InterestAndDebtExpense"],
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                     "Depreciation"],
    # --- W2 PR-H additions (Long-Hold Thesis Layer, 2026-07-06) ---
    # SBC: share-based compensation (non-cash; needed for EBITDA proxy and FCF conversion)
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
            "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsVestedInPeriodTotalFairValue"],
    # R&D: research and development expense (capital-allocation and moat-falsifier work)
    "research_dev": ["ResearchAndDevelopmentExpense",
                     "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
}
BALANCE = {
    "assets": ["Assets"],
    "cur_assets": ["AssetsCurrent"],
    "cur_liab": ["LiabilitiesCurrent"],
    "inventory": ["InventoryNet"],
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "debt_lt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "debt_cur": ["LongTermDebtCurrent", "DebtCurrent"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "shares": ["CommonStockSharesOutstanding"],
}
EPS = ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _cache_path():
    p = config.data_dir() / "edgar" / "statements.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _get_json(url: str, retries: int = 3):
    import requests
    ua = config.load()["edgar"]["user_agent"]
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=40)
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


def _annual(entries: list, instant: bool = False) -> dict[int, float]:
    """{fiscal_year: value} from a concept's unit list. Apple (and others) tag
    quarterly figures with fp="FY" too, so for FLOW concepts we keep only the
    FULL-YEAR period (start→end ≈ 365 days); for INSTANT balances we take the
    fiscal year-end value. Keyed by the period's own fiscal year (the `fy` field
    is correct on the full-year/year-end entry), latest-filed wins on restatement."""
    best: dict[int, tuple[tuple, float]] = {}
    for e in entries or []:
        if e.get("fp") != "FY" or e.get("form") not in ANNUAL_FORMS:
            continue
        fy, val, end = e.get("fy"), e.get("val"), e.get("end")
        if fy is None or val is None or not end:
            continue
        if not instant:
            start = e.get("start")
            if not start:
                continue
            try:
                days = (pd.to_datetime(end) - pd.to_datetime(start)).days
            except Exception:  # noqa: BLE001
                continue
            if not (300 <= days <= 400):       # full fiscal year only (skip quarters)
                continue
        rank = (e.get("filed", ""), end)       # latest filing, then latest period-end
        if fy not in best or rank > best[fy][0]:
            best[fy] = (rank, float(val))
    return {fy: v for fy, (_r, v) in best.items()}


def _concept(usgaap: dict, names: list[str], unit: str = "USD",
             instant: bool = False) -> dict[int, float]:
    """Merge a fallback chain ACROSS fiscal years — a filer often migrates tags
    over time (e.g. AAPL: Revenues pre-2019, RevenueFromContractWithCustomer after),
    so taking the first non-empty concept would only cover one era. Earlier names
    in the chain win on a year both report."""
    combined: dict[int, float] = {}
    for nm in names:
        node = usgaap.get(nm)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        for fy, val in _annual(entries, instant=instant).items():
            combined.setdefault(fy, val)
    return combined


def _statements_for(cik: int) -> list[dict]:
    """Per-fiscal-year rows of the raw concepts for one filer (last KEEP_YEARS)."""
    data = _get_json(FACTS_URL.format(cik))
    time.sleep(0.12)                       # SEC fair-access pacing (<10 req/s)
    if not data:
        return []
    usgaap = (data.get("facts") or {}).get("us-gaap") or {}
    if not usgaap:
        return []
    series: dict[str, dict[int, float]] = {}
    for key, names in FLOW.items():
        series[key] = _concept(usgaap, names, instant=False)
    for key, names in BALANCE.items():
        series[key] = _concept(usgaap, names, instant=True)
    series["eps_diluted"] = _concept(usgaap, EPS, unit="USD/shares", instant=False)

    years = sorted({fy for s in series.values() for fy in s}, reverse=True)[:KEEP_YEARS]
    rows = []
    for fy in sorted(years):
        rec = {"fy": fy}
        for key, s in series.items():
            rec[key] = s.get(fy)
        # derive revenue from gross profit + COGS when the revenue tag is absent
        # for that year (common when a filer only tags GrossProfit + COGS)
        if rec.get("revenue") is None and rec.get("gross_profit") is not None and rec.get("cogs") is not None:
            rec["revenue"] = rec["gross_profit"] + rec["cogs"]
        # derive gross profit from revenue − COGS when GrossProfit isn't tagged
        if rec.get("gross_profit") is None and rec.get("revenue") is not None and rec.get("cogs") is not None:
            rec["gross_profit"] = rec["revenue"] - rec["cogs"]
        rows.append(rec)
    return rows


def _cik_map() -> dict[str, int]:
    fp = config.data_dir() / "edgar" / "fundamentals.parquet"
    if not fp.exists():
        return {}
    try:
        df = pd.read_parquet(fp, columns=["cik"])
    except Exception:  # noqa: BLE001
        return {}
    return {str(t): int(r["cik"]) for t, r in df.iterrows() if pd.notna(r.get("cik"))}


def fetch_statements(force: bool = False, max_new: int = 200,
                     tickers: list[str] | None = None) -> pd.DataFrame:
    """Resumably fetch multi-year statements for the universe; merge into the
    long-format cache (ticker, fy, <concepts>, as_of) and return it. Best-effort."""
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    cik = _cik_map()
    universe = tickers or list(cik)

    def as_of(t: str):
        if existing.empty or "as_of" not in existing or t not in set(existing.get("ticker", [])):
            return None
        sub = existing[existing["ticker"] == t]
        return sub["as_of"].max() if len(sub) else None

    def stale(t: str) -> bool:
        if force:
            return True
        ts = as_of(t)
        if ts is None:
            return True
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days > REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in universe if t in cik and stale(t)][:max_new]
    log.info("edgar_facts: %d universe, fetching %d (cap %d)", len(universe), len(todo), max_new)

    now = datetime.now(timezone.utc).isoformat()
    new_rows = []
    for t in todo:
        for rec in _statements_for(cik[t]):
            rec["ticker"] = t
            rec["as_of"] = now
            new_rows.append(rec)

    fresh = pd.DataFrame(new_rows)
    if not existing.empty and not fresh.empty:
        existing = existing[~existing["ticker"].isin(fresh["ticker"].unique())]
        out = pd.concat([existing, fresh], ignore_index=True)
    else:
        out = fresh if not fresh.empty else existing
    if not out.empty:
        out.to_parquet(cache, index=False)
    n_t = out["ticker"].nunique() if "ticker" in out else 0
    log.info("edgar_facts: cache now %d tickers, %d ticker-years", n_t, len(out))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    ts = sys.argv[1:] or ["AAPL"]
    df = fetch_statements(force=True, max_new=len(ts), tickers=ts)
    for t in ts:
        sub = df[df["ticker"] == t].sort_values("fy") if "ticker" in df else df
        print(f"\n=== {t} ===")
        cols = [c for c in ("fy", "revenue", "gross_profit", "op_income", "ni",
                            "eps_diluted", "cfo", "capex", "interest_exp", "depreciation",
                            "sbc", "research_dev", "assets", "equity",
                            "cur_assets", "cur_liab", "debt_lt", "cash") if c in sub.columns]
        print(sub[cols].to_string(index=False))
