"""SEC EDGAR XBRL fundamentals collector for the cross-sectional factor engine.

The EDGAR "frames" API returns ONE us-gaap concept across EVERY filer for a
calendar period in a single keyless call (data.sec.gov/api/xbrl/frames/...).
That makes a genuine fundamentals cross-section buildable for free — no
Compustat/I-B-E-S vendor — which we join to the S&P 1500 price universe already
in the breadth close caches.

We pull a small set of concepts for the latest complete fiscal year (+ the prior
year where a factor needs a change), filter to our universe, and write a wide
ticker-indexed table to data/edgar/fundamentals.parquet. Fundamentals move
quarterly, so the fetch is cached (refreshed weekly); the factor RANKS recompute
daily from this cache + fresh prices (market cap = price x shares).

Honesty: free fundamentals are sparse for some tags (dividends/buybacks/gross
profit), fiscal-year-ends differ (we scan the 4 quarterly instantaneous frames
and keep each filer's most recent balance), and values are lagged to the filing
period (no look-ahead). Factors are ranks/context, not a backtested alpha.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# instantaneous (balance-sheet) concepts — scanned across the 4 quarter frames
BALANCE = {
    "assets": "Assets",
    "equity": "StockholdersEquity",
    "debt_lt": "LongTermDebtNoncurrent",
}
SHARES_USGAAP = "CommonStockSharesOutstanding"
SHARES_DEI = "EntityCommonStockSharesOutstanding"
# duration (flow) concepts — single annual frame CY{fy}
FLOW = {
    "ni": "NetIncomeLoss",
    "gross_profit": "GrossProfit",
    "cfo": "NetCashProvidedByUsedInOperatingActivities",
    "dividends": "PaymentsOfDividendsCommonStock",
    "repurchases": "PaymentsForRepurchaseOfCommonStock",
}
REVENUE_CONCEPTS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]


def _cfg() -> dict:
    return config.load()["edgar"]


def _headers() -> dict:
    return {"User-Agent": _cfg()["user_agent"], "Accept-Encoding": "gzip, deflate"}


def _get_json(url: str, retries: int = 3) -> dict | None:
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — tolerate per-frame failure
            if attempt == retries - 1:
                log.warning("edgar GET failed %s: %s", url.split("/api/")[-1], e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def _frame(base: str, concept: str, period: str, unit: str) -> dict[int, tuple[float, str]]:
    """{cik: (val, end_date)} for one concept/period frame (empty on miss)."""
    url = f"{base}/{concept}/{unit}/{period}.json"
    data = _get_json(url, _cfg()["retries"])
    time.sleep(0.12)                       # SEC fair-access pacing (<10 req/s)
    if not data or "data" not in data:
        return {}
    return {int(r["cik"]): (float(r["val"]), r.get("end", "")) for r in data["data"]
            if r.get("val") is not None}


_SUFFIX = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
           "HOLDINGS", "HOLDING", "GROUP", "THE", "CLASS", "COM", "NEW", "LP",
           "LLC", "TRUST", "INCORPORATED", "INTERNATIONAL", "INTL", "&"}


def _norm_name(s: str) -> str:
    s = s.upper()
    for ch in ".,&/'-()":
        s = s.replace(ch, " ")
    toks = [t for t in s.split() if t and t not in _SUFFIX and not (len(t) == 1)]
    return " ".join(toks)


def _frame_names(base: str, concept: str, period: str, unit: str) -> dict[int, str]:
    """{cik: entityName} for one frame (used by the name-matching fallback)."""
    data = _get_json(f"{base}/{concept}/{unit}/{period}.json", _cfg()["retries"])
    time.sleep(0.12)
    if not data or "data" not in data:
        return {}
    return {int(r["cik"]): r.get("entityName", "") for r in data["data"]}


def _universe_names() -> dict[str, str]:
    """{ticker: company name} from the breadth constituents tables."""
    out: dict[str, str] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            meta = pd.read_parquet(p)
            for t, row in meta.iterrows():
                out.setdefault(str(t), str(row.get("name", t)))
    return out


def _latest_balance(concept: str, year: int) -> dict[int, float]:
    """Most recent instantaneous value per CIK across the 4 quarter frames of a
    year — covers all fiscal-year-ends (a Sep-FY firm lands in Q3I, a Dec-FY in
    Q4I)."""
    base = _cfg()["base_url"]
    best: dict[int, tuple[float, str]] = {}
    for q in ("Q4I", "Q3I", "Q2I", "Q1I"):
        for cik, (val, end) in _frame(base, concept, f"CY{year}{q}", "USD").items():
            if cik not in best or end > best[cik][1]:
                best[cik] = (val, end)
    return {cik: v for cik, (v, _e) in best.items()}


def _annual(concept: str, year: int, unit: str = "USD") -> dict[int, float]:
    return {cik: v for cik, (v, _e) in _frame(_cfg()["base_url"], concept, f"CY{year}", unit).items()}


def _shares(year: int) -> dict[int, float]:
    """Shares outstanding: us-gaap balance scan, dei cover-page fallback."""
    out = _latest_balance_shares(SHARES_USGAAP, year, _cfg()["base_url"])
    dei_base = _cfg()["shares_url"]
    best: dict[int, tuple[float, str]] = {}
    for q in ("Q4I", "Q3I", "Q2I", "Q1I"):
        for cik, (val, end) in _frame(dei_base, SHARES_DEI, f"CY{year}{q}", "shares").items():
            if cik not in best or end > best[cik][1]:
                best[cik] = (val, end)
    for cik, (val, _e) in best.items():
        out.setdefault(cik, val)           # only fill gaps us-gaap missed
    return out


def _latest_balance_shares(concept: str, year: int, base: str) -> dict[int, float]:
    best: dict[int, tuple[float, str]] = {}
    for q in ("Q4I", "Q3I", "Q2I", "Q1I"):
        for cik, (val, end) in _frame(base, concept, f"CY{year}{q}", "shares").items():
            if cik not in best or end > best[cik][1]:
                best[cik] = (val, end)
    return {cik: v for cik, (v, _e) in best.items()}


def _universe_tickers() -> list[str]:
    """All S&P 1500 tickers present in the breadth close caches."""
    tickers: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            tickers.update(pd.read_parquet(p, columns=None).columns)
    return sorted(tickers)


def _load_company_tickers() -> dict | None:
    """SEC's ticker->CIK file, cached locally (it rarely changes and www.sec.gov
    rate-limits hard). Fetch only if the cache is missing/stale; fall back to the
    cache on any fetch failure."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    fresh = False
    if cache.exists():
        try:
            age_d = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) / 86400.0
            fresh = age_d < 30
        except Exception:  # noqa: BLE001
            fresh = True
    if not fresh:
        data = _get_json(_cfg()["tickers_url"], _cfg()["retries"])
        if data:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data))
            return data
    if cache.exists():
        return json.loads(cache.read_text())
    return None


def _ticker_cik_map(universe: list[str], fy: int) -> dict[str, int]:
    """ticker -> CIK. Primary: SEC company_tickers.json (exact, cached). Fallback
    when that endpoint is blocked: match the frame entityName against our universe
    company names (normalized)."""
    data = _load_company_tickers()
    if data:
        sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
        out: dict[str, int] = {}
        for t in universe:
            u = t.upper()
            for cand in (u, u.replace("-", "."), u.replace(".", "-"),
                         u.split("-")[0], u.split(".")[0]):
                if cand in sec:
                    out[t] = sec[cand]
                    break
        if len(out) >= 0.5 * len(universe):
            return out
        log.warning("company_tickers mapped only %d/%d — augmenting with name match",
                    len(out), len(universe))
    else:
        out = {}
        log.warning("company_tickers.json unavailable — using entityName fallback map")

    # name-matching fallback (or augmentation)
    base = _cfg()["base_url"]
    cik_name: dict[int, str] = {}
    for q in ("Q4I", "Q3I", "Q2I"):
        cik_name.update(_frame_names(base, "Assets", f"CY{fy}{q}", "USD"))
    name_cik: dict[str, int] = {}
    for cik, nm in cik_name.items():
        name_cik.setdefault(_norm_name(nm), cik)
    for t, nm in _universe_names().items():
        if t in out:
            continue
        cik = name_cik.get(_norm_name(nm))
        if cik:
            out[t] = cik
    return out


def _cache_path():
    p = config.data_dir() / "edgar" / "fundamentals.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _cache_age_days() -> float | None:
    p = _cache_path()
    if not p.exists():
        return None
    meta = config.data_dir() / "edgar" / "_meta.json"
    if meta.exists():
        try:
            built = datetime.fromisoformat(json.loads(meta.read_text())["built"])
            return (datetime.now(timezone.utc) - built).total_seconds() / 86400.0
        except Exception:  # noqa: BLE001
            pass
    return 999.0


def fetch_fundamentals(force: bool = False, max_age_days: int = 7) -> pd.DataFrame:
    """Fetch (or load cached) the wide ticker-indexed fundamentals table."""
    cache = _cache_path()
    age = _cache_age_days()
    if not force and age is not None and age < max_age_days:
        log.info("edgar fundamentals cache fresh (%.1fd) — skip fetch", age)
        return pd.read_parquet(cache)

    cfg = _cfg()
    universe = _universe_tickers()
    if not universe:
        raise RuntimeError("no breadth close caches — run breadth collectors first")

    # resolve the latest fiscal year that is actually populated
    fy = int(cfg["latest_fy"])
    for cand in (fy, fy - 1):
        if len(_annual("NetIncomeLoss", cand)) >= cfg["min_filers_ok"]:
            fy = cand
            break

    tcik = _ticker_cik_map(universe, fy)
    cik_t = {c: t for t, c in tcik.items()}        # first ticker wins on dup CIK
    log.info("edgar: %d universe tickers, %d mapped to CIK, FY%d", len(universe), len(tcik), fy)

    cols: dict[str, dict[int, float]] = {}
    for key, concept in BALANCE.items():
        cols[key] = _latest_balance(concept, fy)
    cols["assets_prior"] = _latest_balance("Assets", fy - 1)
    cols["shares"] = _shares(fy)
    for key, concept in FLOW.items():
        cols[key] = _annual(concept, fy)
    cols["ni_prior"] = _annual("NetIncomeLoss", fy - 1)
    rev: dict[int, float] = {}
    for c in REVENUE_CONCEPTS:
        for cik, v in _annual(c, fy).items():
            rev.setdefault(cik, v)
    cols["revenue"] = rev

    # assemble wide table keyed by ticker
    rows = []
    for cik, t in cik_t.items():
        rec = {"ticker": t, "cik": cik}
        for key, m in cols.items():
            rec[key] = m.get(cik)
        rows.append(rec)
    df = pd.DataFrame(rows).set_index("ticker")
    df = df.dropna(subset=["assets", "equity"], how="all")
    df.to_parquet(cache)
    (config.data_dir() / "edgar" / "_meta.json").write_text(
        json.dumps({"built": datetime.now(timezone.utc).isoformat(), "fy": fy,
                    "n_tickers": int(len(df)), "n_universe": len(universe)}))
    log.info("edgar fundamentals: %d tickers, FY%d, %d cols", len(df), fy, df.shape[1])
    return df
