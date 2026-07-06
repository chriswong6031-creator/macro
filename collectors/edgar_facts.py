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

Each row carries `period_end` (the winning filing's TRUE fiscal period-end date)
so consumers can gate not-yet-filed fiscal rows point-in-time (availability ≈
period_end + reporting-lag). Rows written before this column existed have
period_end=NaN until their next drip re-fetch re-stamps it (consumers keep
un-stamped rows ungated — display-only, self-heals within the ~monthly refresh).

BUG FIX NOTES (LT-1a, 2026-07-06):
  shares: us-gaap:CommonStockSharesOutstanding lives in the "shares" XBRL unit, NOT
    "USD". The BALANCE loop previously called _concept() with the default unit="USD",
    returning an empty dict → all shares values were None. Fixed by extracting shares
    separately with unit="shares", instant=True.  dei:EntityCommonStockSharesOutstanding
    was considered as fallback but is only in the dei namespace (not us-gaap) and
    contains cover-page counts (post-period-end), so it was NOT added.
    WeightedAverageNumberOfDilutedSharesOutstanding is a FLOW concept (per-period
    average) and should not mix with the point-in-time balance sheet count.
  future-FY guard: rows whose period_end is in the future relative to run date are
    dropped at the end of _statements_for(). This is the canonical PIT gate — the fy
    XBRL field alone is unreliable (e.g. STX encodes their fiscal year count as fy=2027
    when the actual period ends in June 2025). period_end (the 'end' date from the
    winning filing entry) is the correct signal.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

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
    # Coverage note: large-cap filers (AAPL, MSFT) stopped tagging standalone InterestExpense
    # in recent filings; InterestAndDebtExpense fallback is also empty for them. This means
    # interest_exp is NaN on the LATEST fiscal-year row for ~73% of tickers in the universe
    # (statements.parquet latest-FY coverage ≈27%). The PANEL path (collectors/edgar.py,
    # PIT-lagged fundamentals_panel.parquet) has broader multi-year coverage; interest_coverage
    # via the statements consumer (_leverage latest-FY path) stays None for most large caps.
    "interest_exp": ["InterestExpense", "InterestAndDebtExpense"],
    # Primary two are cash-flow-statement D&A add-backs (depletion + amortization included).
    # Third fallback "Depreciation" is P&L depreciation only (no amortization, no depletion);
    # a filer that tags DD&A in some years and only "Depreciation" in others will have a
    # mixed D&A basis year-to-year (EBITDA denominator understated in fallback years).
    # Coverage note: AAPL/MSFT/NVDA all use DepreciationDepletionAndAmortization; the third
    # fallback is exercised only by non-standard filers and carries a basis caveat.
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                     "Depreciation"],
    # --- W2 PR-H additions (Long-Hold Thesis Layer, 2026-07-06) ---
    # SBC: share-based compensation (non-cash; needed for EBITDA proxy and FCF conversion).
    # Only two fallbacks: ShareBasedCompensation (IS/CF SBC expense) and
    # AllocatedShareBasedCompensationExpense (alternative label for the same P&L line).
    # NOTE: ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstruments
    # OtherThanOptionsVestedInPeriodTotalFairValue was intentionally excluded — that
    # concept reports total fair-value-of-awards-VESTED (a footnote disclosure quantity),
    # NOT the SBC expense charged to the income statement; merging them would silently
    # corrupt the EBITDA proxy and FCF add-back for any filer that tags it without the
    # primary concepts.
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
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
    # NOTE: 'shares' is intentionally absent — shares live in the "shares" XBRL unit,
    # not "USD". They are extracted separately in _statements_for() via BALANCE_SHARES.
}
# Concepts reported in the "shares" XBRL unit (not USD). Extracted with unit="shares".
# Primary: us-gaap:CommonStockSharesOutstanding — the fiscal-year-end balance-sheet
# share count, reported as an instant (point-in-time) concept.
# dei:EntityCommonStockSharesOutstanding is NOT used: it is cover-page count (slightly
# post-period-end), lives in the dei namespace (not us-gaap), and would require a
# separate namespace lookup path.
BALANCE_SHARES = {
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


def _annual(entries: list, instant: bool = False) -> dict[int, tuple[float, str]]:
    """{fiscal_year: (value, period_end)} from a concept's unit list. Apple (and
    others) tag quarterly figures with fp="FY" too, so for FLOW concepts we keep
    only the FULL-YEAR period (start→end ≈ 365 days); for INSTANT balances we take
    the fiscal year-end value. Keyed by the period's own fiscal year (the `fy` field
    is correct on the full-year/year-end entry), latest-filed wins on restatement.

    `period_end` (the winning entry's `end` date) is carried out so consumers can
    gate not-yet-filed fiscal rows: statements.parquet previously kept no filing/
    period column, so a row for a fiscal year whose 10-K is not yet filed was
    indistinguishable from a filed one (point-in-time leak — engine/moat_falsifiers).

    Instant-concept guard (LT-1b bug fix): some filers (e.g. PMT) tag debt maturity
    schedules using XBRL instant concepts like LongTermDebt with fy=<current_fy> but
    end=<future_maturity_year> (up to fy+6). These are NOT balance-sheet period-end
    values; they corrupt the period_end accumulator and trigger the future-FY guard
    to silently drop valid fiscal rows. We reject instant entries where end year >
    fy+1 — all valid balance-sheet dates (current period or prior-year comparative)
    satisfy end_year ≤ fy+1 (January-FYE filers use fy+1, e.g. DPZ FY2020 ends
    2021-01-03; all other filers use fy or fy-1)."""
    best: dict[int, tuple[tuple, float, str]] = {}
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
        else:
            # Reject debt-maturity-schedule entries: end year must be ≤ fy+1.
            # Valid balance-sheet dates: end_year = fy (Dec-FYE), fy+1 (Jan-FYE),
            # or fy-1 (prior-year comparative). end_year > fy+1 → maturity projection
            # (e.g. PMT LongTermDebt files future maturities with fy=current_fy but
            # end=maturity_year up to fy+6, corrupting the period_end accumulator).
            try:
                end_year = int(end[:4])
            except (ValueError, TypeError):
                end_year = fy
            if end_year > fy + 1:
                continue
        # Rank: (filed desc, end desc) — latest restatement wins; for identical
        # filings, prefer the current-period entry (end closest to fy) over a
        # prior-year comparative. For instant concepts we clip end to fy+1 above;
        # within that window, the entry whose end_year ≤ fy should win over fy+1
        # (current period-end vs Jan-carry-forward; the Jan-FYE comparatives use
        # end_year=fy+1 so we can't simply exclude them — they ARE the primary entry
        # for January-fiscal-year-end filers like DPZ). Since both filed values are
        # equal for the same 10-K accession, end lexicographic order still picks
        # end_year=fy+1 over fy — that is acceptable for Jan-FYE filers (their
        # true period_end is in January of fy+1) and for Dec-FYE filers there is no
        # fy+1 entry in window after the maturity-schedule clip above.
        rank = (e.get("filed", ""), end)       # latest filing, then latest period-end
        if fy not in best or rank > best[fy][0]:
            best[fy] = (rank, float(val), end)
    return {fy: (v, end) for fy, (_r, v, end) in best.items()}


def _concept(usgaap: dict, names: list[str], unit: str = "USD",
             instant: bool = False) -> tuple[dict[int, float], dict[int, str]]:
    """Merge a fallback chain ACROSS fiscal years — a filer often migrates tags
    over time (e.g. AAPL: Revenues pre-2019, RevenueFromContractWithCustomer after),
    so taking the first non-empty concept would only cover one era. Earlier names
    in the chain win on a year both report.

    Returns ``({fy: value}, {fy: period_end})``. The fiscal-year-end is identical
    across a filing's annual concepts, so the latest (max) `end` seen per fy is kept."""
    combined: dict[int, float] = {}
    ends: dict[int, str] = {}
    for nm in names:
        node = usgaap.get(nm)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        for fy, (val, end) in _annual(entries, instant=instant).items():
            combined.setdefault(fy, val)
            if end and (fy not in ends or end > ends[fy]):
                ends[fy] = end
    return combined, ends


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
    period_ends: dict[int, str] = {}
    # Separate accumulator for balance-concept ends (fallback only — see note below).
    _balance_ends: dict[int, str] = {}

    def _absorb(ends: dict[int, str], balance: bool = False) -> None:
        """Accumulate period_end per fiscal year.

        FLOW concepts (balance=False) use their ``end`` date as the authoritative
        period-end; these are the true fiscal year-end dates and are preferred.
        BALANCE/instant concepts (balance=True) contribute to a separate fallback
        accumulator: their ``end`` values are only used when a fiscal year has no
        flow-concept data at all.  This prevents debt-maturity-schedule XBRL entries
        (e.g. PMT's LongTermDebt with fy=2021 but end=2022-12-31 representing the
        1-year maturity bucket) from overriding the correct period_end that was set
        by the ni/cfo/etc. flow series.  The _annual instant-guard above already
        clips out_year > fy+1; this layered accumulator handles the remaining fy+1
        false-positive (maturity bucket at fy+1) for December-FYE filers."""
        target = _balance_ends if balance else period_ends
        for fy, end in ends.items():
            if end and (fy not in target or end > target[fy]):
                target[fy] = end

    for key, names in FLOW.items():
        series[key], _ends = _concept(usgaap, names, instant=False)
        _absorb(_ends)
    for key, names in BALANCE.items():
        series[key], _ends = _concept(usgaap, names, instant=True)
        _absorb(_ends, balance=True)
    # Shares are in the "shares" XBRL unit (not USD) — must be extracted separately.
    # us-gaap:CommonStockSharesOutstanding is the fiscal-year-end balance-sheet share
    # count (instant concept). The BALANCE loop above uses unit="USD" (default) so
    # it returns an empty dict for shares → was always None before this fix.
    for key, names in BALANCE_SHARES.items():
        series[key], _ends = _concept(usgaap, names, unit="shares", instant=True)
        _absorb(_ends, balance=True)
    series["eps_diluted"], _ends = _concept(usgaap, EPS, unit="USD/shares", instant=False)
    _absorb(_ends)
    # Merge balance fallback: years with no flow period_end get the balance-concept end.
    for fy, end in _balance_ends.items():
        if fy not in period_ends:
            period_ends[fy] = end

    years = sorted({fy for s in series.values() for fy in s}, reverse=True)[:KEEP_YEARS]
    today_iso = date.today().isoformat()
    rows = []
    for fy in sorted(years):
        rec = {"fy": fy}
        for key, s in series.items():
            rec[key] = s.get(fy)
        # PIT: fiscal period-end of this FY (the winning filing's `end`), so consumers
        # can drop rows whose 10-K was not yet filed at a given as-of date.
        rec["period_end"] = period_ends.get(fy)
        # Future-FY guard: drop rows whose fiscal period has not yet closed.
        # The XBRL fy field is unreliable (e.g. STX tags their FY ending June 2025 as
        # fy=2027). period_end (the winning entry's 'end' date) is the canonical signal.
        # A row is only dropped when period_end IS set and is strictly in the future;
        # rows with period_end=None are kept (display-only — they self-heal on next drip).
        pe = rec.get("period_end")
        if pe and pe > today_iso:
            log.debug("edgar_facts: dropping future-period row fy=%s period_end=%s", fy, pe)
            continue
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
    # Usage: python -m collectors.edgar_facts [TICKER ...] [--limit N]
    # --limit N: cap max_new to N (smoke-test path; default = len(tickers))
    args = sys.argv[1:]
    limit: int | None = None
    if "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
    ts = args or ["AAPL"]
    max_new = limit if limit is not None else len(ts)
    df = fetch_statements(force=True, max_new=max_new, tickers=ts)
    for t in ts:
        sub = df[df["ticker"] == t].sort_values("fy") if "ticker" in df else df
        print(f"\n=== {t} ===")
        cols = [c for c in ("fy", "period_end", "revenue", "gross_profit", "op_income", "ni",
                            "eps_diluted", "cfo", "capex", "interest_exp", "depreciation",
                            "sbc", "research_dev", "assets", "equity", "shares",
                            "cur_assets", "cur_liab", "debt_lt", "cash") if c in sub.columns]
        print(sub[cols].to_string(index=False))
