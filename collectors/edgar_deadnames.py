"""Dead-name fundamentals recovery — the survivorship de-bias (Phase 1B of
research/INSTITUTIONAL_ROADMAP.md).

THE BIAS. `collectors/edgar.fetch_panel` already fetches every filer per fiscal
year from the frames API — including since-delisted ones — but DROPS them
(edgar.py:423) because the current `company_tickers.json` can't map a delisted
CIK back to its old ticker. Result, verified: of the 1,083 dead-only tickers in
`data/breadth/sp1500_pit_membership.parquet`, 0 carry any fundamentals. Every
factor IC / percentile in the stack is therefore computed on survivors only — a
textbook upward bias (the failures are exactly the names you most want in the
cross-section).

THE FIX, two independent halves.
  1. RESOLVE  dead ticker -> CIK (`resolve_dead_ciks`). The ticker<->CIK bridge
     lives only in SEC's `company_tickers.json` (www.sec.gov) or a vendor
     (Polygon). Both are IP-gated and unavailable from some build IPs, so this
     half is resumable and CACHED to data/edgar/dead_name_cik.json — resolve once
     where the sources are reachable (CI), consume the cache everywhere. A curated
     `_KNOWN_DEAD_CIK` seed of high-confidence M&A/renames resolves a verified
     core immediately AND guards against ticker-reuse mis-resolution (e.g. the old
     `ABX`/Barrick symbol now points at an unrelated filer).
     1b. The long tail (`resolve_via_fulltext`). company_tickers.json only carries
     names STILL trading under their symbol; the ~half that delisted/renamed fall
     out of it. The literal "formerNames crawl" the roadmap imagined is a dead end
     here: the SEC submissions doc carries `tickers` (CURRENT only — empty for every
     acquired name) and `formerNames` (former *names*, never former *tickers*), and
     the dead universe is bare tickers with no company name to match a former name
     against. What DOES work is EDGAR full-text search (efts.sec.gov — an SEC host
     distinct from the 403-prone www.sec.gov), which indexes the cover-page trading
     symbol of every annual report since 2001: a phrase search WINDOWED to the dead
     name's S&P membership era (the ticker-reuse guard) and gated by a doc-count
     DOMINANCE threshold returns the filer that actually traded under it, CONFIRMED
     against its data.sec.gov submissions doc. Honest, measured yield is partial —
     pre-2001 delistings are out of range and the conservative gate forgoes many
     real-but-ambiguous names because a wrong CIK is worse than none.
  2. PULL    fundamentals per resolved CIK (`build_dead_panel`) from the
     companyfacts API on data.sec.gov — keyless, reachable everywhere, and it
     carries the TRUE SEC `filed` timestamp. We stamp `asof_date = filed` (the
     date the report actually became public), NOT period_end and NOT the
     period_end+120d proxy the survivor panel uses. Stamping period_end would
     inject look-ahead; the real filed date is strictly leak-free.

Output `data/edgar/dead_name_panel.parquet` is schema-identical to
`fundamentals_panel.parquet` so `merged_panel()` simply concatenates the two.
`coverage()` writes the honest `dead_name_coverage` ratio every consumer should
display. KEYLESS · resumable · drip-capped (companyfacts is 3.5-7.5 MB/filer).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
REFRESH_DAYS = 30
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_CY_RE = re.compile(r"CY(\d{4})")

# Panel schema we must match (collectors/edgar.PANEL_NUMERIC) + period_end/asof_date.
PANEL_NUMERIC = ["assets", "equity", "debt_lt", "shares", "ni", "gross_profit",
                 "cfo", "dividends", "repurchases", "revenue", "assets_prior", "ni_prior"]

# companyfacts concept fallback chains (first populated wins per fiscal year).
# Mirrors collectors/edgar_facts so the dead panel and the survivor panel measure
# the same line items; adds dividends/repurchases the survivor flow set carries.
_FLOW = {
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "gross_profit": ["GrossProfit"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "repurchases": ["PaymentsForRepurchaseOfCommonStock",
                    "PaymentsForRepurchaseOfCommonStockAndPreferredStock"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
}
_BALANCE = {
    "assets": ["Assets"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "debt_lt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "shares": ["CommonStockSharesOutstanding"],
}

# Curated, audited dead ticker -> CIK seed (S&P members removed by M&A / rename).
# Verified against companyfacts entityName. This is the ticker-reuse-immune
# override AND the offline proof set (resolves without www.sec.gov / a vendor).
_KNOWN_DEAD_CIK: dict[str, int] = {
    "ATVI": 718877,    # Activision Blizzard -> MSFT (2023)
    "AET": 1122304,    # Aetna -> CVS (2018)
    "ABMD": 815094,    # Abiomed -> JNJ (2022)
    "ANTM": 1156039,   # Anthem -> Elevance (rename 2022)
    "XLNX": 743988,    # Xilinx -> AMD (2022)
    "CERN": 804753,    # Cerner -> Oracle (2022)
    "RTN": 1047122,    # Raytheon -> RTX (2020)
    "WLTW": 1140536,   # Willis Towers Watson -> WTW (rename 2022)
    "FLIR": 354908,    # FLIR Systems -> Teledyne (2021)
    "MXIM": 743316,    # Maxim Integrated -> ADI (2021)
    "TIF": 98246,      # Tiffany -> LVMH (2021)
    "CTL": 18926,      # CenturyLink -> Lumen (rename 2020)
    "NBL": 72207,      # Noble Energy -> Chevron (2020)
    "VAR": 203527,     # Varian Medical -> Siemens (2021)
    "ETFC": 1015780,   # E*TRADE -> Morgan Stanley (2020)
}


def _cfg() -> dict:
    return config.load()["edgar"]


def _headers() -> dict:
    return {"User-Agent": _cfg()["user_agent"], "Accept-Encoding": "gzip, deflate"}


def _get_json(url: str, retries: int = 3):
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), timeout=40)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — tolerate per-filer failure
            if attempt == retries - 1:
                log.debug("companyfacts GET failed %s: %s", url[-28:], e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


# --------------------------------------------------------------------------- #
# Half 1 — dead ticker -> CIK resolution (resumable, cached)
# --------------------------------------------------------------------------- #
def _cik_cache_path():
    p = config.data_dir() / "edgar" / "dead_name_cik.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_cik_cache() -> dict:
    p = _cik_cache_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _company_tickers() -> dict[str, int]:
    """{TICKER -> cik} from SEC's cached company_tickers.json (www.sec.gov; may be
    empty/absent on a blocked IP — then this strategy simply yields nothing)."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if not cache.exists():
        return {}
    try:
        data = json.loads(cache.read_text())
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, int] = {}
    for row in (data.values() if isinstance(data, dict) else data):
        try:
            out[str(row["ticker"]).upper()] = int(row["cik_str"])
        except Exception:  # noqa: BLE001
            continue
    return out


def _polygon_cik(ticker: str) -> int | None:
    """Polygon ticker reference -> CIK (resolves delisted names). Returns None when
    no key is configured or the call fails."""
    key = None
    try:
        cfg = config.load()
        key = (cfg.get("polygon") or {}).get("api_key") or (cfg.get("keys") or {}).get("polygon")
    except Exception:  # noqa: BLE001
        key = None
    import os
    key = key or os.environ.get("POLYGON_API_KEY")
    if not key:
        return None
    import requests
    try:
        r = requests.get(f"https://api.polygon.io/v3/reference/tickers/{ticker}",
                          params={"apiKey": key}, timeout=20)
        if r.status_code != 200:
            return None
        cik = (r.json().get("results") or {}).get("cik")
        return int(cik) if cik else None
    except Exception:  # noqa: BLE001
        return None


def resolve_dead_ciks(dead_tickers: list[str], force: bool = False,
                      use_polygon: bool = True) -> dict[str, dict]:
    """Resolve dead ticker -> CIK, resumably, caching to dead_name_cik.json.

    Strategy chain per unresolved ticker (stop at first hit): curated seed ->
    cached company_tickers.json (exact + dash/dot variants) -> Polygon reference.
    Records `method` per hit and persists misses (method="unresolved") so the
    unresolved set is auditable and not re-attempted needlessly. Returns the full
    {ticker: {cik, method}} map (resolved entries only have an int cik)."""
    cache = _load_cik_cache()
    ct = _company_tickers()
    resolved_now = 0
    for t in dead_tickers:
        prev = cache.get(t)
        if prev and prev.get("cik") and not force:
            continue
        cik, method = None, "unresolved"
        # 1. curated seed (audited; ticker-reuse-immune)
        if t in _KNOWN_DEAD_CIK:
            cik, method = _KNOWN_DEAD_CIK[t], "seed"
        # 2. SEC company_tickers.json (current map + symbol variants)
        if cik is None and ct:
            u = t.upper()
            for cand in (u, u.replace("-", "."), u.replace(".", "-"),
                         u.split("-")[0], u.split(".")[0]):
                if cand in ct:
                    cik, method = ct[cand], "company_tickers"
                    break
        # 3. Polygon reference (delisted-aware vendor)
        if cik is None and use_polygon:
            pc = _polygon_cik(t)
            if pc:
                cik, method = pc, "polygon"
                time.sleep(0.05)
        cache[t] = {"cik": int(cik), "method": method} if cik else {"cik": None, "method": "unresolved"}
        if cik:
            resolved_now += 1
    _cik_cache_path().write_text(json.dumps(cache, indent=0, sort_keys=True))
    n_res = sum(1 for v in cache.values() if v.get("cik"))
    log.info("dead-name CIK: %d/%d resolved (+%d this run)", n_res, len(cache), resolved_now)
    return cache


# --------------------------------------------------------------------------- #
# Half 1b — EDGAR full-text crawl for the still-`unresolved` long tail
#
# WHY NOT a literal formerNames reverse-index. The SEC submissions doc
# (data.sec.gov/submissions/CIK*.json) carries `tickers` (CURRENT only — verified
# empty for every acquired/delisted name: ATVI/AET/FLIR all return []) and
# `formerNames` (former *names*, never former *tickers*). The dead universe is bare
# tickers with NO company name (sp1500_pit_membership has ticker/start/end only),
# so there is nothing to match a former *name* against and no former-*ticker* field
# to match a ticker against — a blind enumerate-and-reverse-index crawl cannot
# bridge a bare dead ticker.
#
# WHAT WORKS. EDGAR full-text search (efts.sec.gov) indexes the cover-page trading
# symbol of every 10-K/20-F/40-F since 2001. A phrase search for the dead ticker,
# WINDOWED to that ticker's S&P membership era (a later reuse of the symbol files in
# a different era → excluded) and gated by a doc-count DOMINANCE threshold (a wrong
# CIK is worse than none), surfaces the filer that actually traded under it as the
# dominant entity bucket. Each hit is CONFIRMED against its data.sec.gov submissions
# doc — the "pull the submissions doc" step — which rejects (i) a still-listed entity
# under a DIFFERENT symbol (APPS→'Cyber Apps World'), (ii) an entity still filing
# years past the index exit, and (iii) an acquired filer whose name does not
# corroborate the symbol as an in-order subsequence (ANDV is not a subsequence of
# 'American National Insurance'), and records `formerNames` for the audit trail.
# Tagged method="edgar_fts".
#
# Honest yield. Names still listed under their symbol are already resolved by
# company_tickers.json and never reach this leg; the net-new population is the
# acquired/renamed tail, of which a measured ~1-in-5 clears the conservative
# dominance+confirmation gate. Pre-2001 delistings (~144 names) are out of EDGAR FTS
# range; `Q`-suffix bankruptcy symbols (LEHMQ…) filed under the pre-bankruptcy
# symbol and miss. Partial by design — every accept is logged with its evidence and
# broken out by method so a consumer can exclude it for a maximally-pure panel.
# --------------------------------------------------------------------------- #
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
EFTS_MIN_DATE = "2001-01-01"        # EDGAR full-text search coverage floor
FTS_FORMS = "10-K,20-F,40-F"        # annual reports carry the cover-page trading symbol
FTS_MIN_DOCS = 4                    # the dominant entity must have >= this many hits...
FTS_DOMINANCE = 2.5                 # ...and >= this multiple of the runner-up entity
FTS_RECENCY_GRACE_DAYS = 365 * 3    # latest annual filing must be within this of the index exit
FTS_REFRESH_DAYS = 45               # re-attempt a soft-miss / transient error after this long
FTS_PACE_S = 0.15                   # SEC fair-access pacing (efts is rate-limited)
_CIK_IN_KEY = re.compile(r"\(CIK\s*(\d{10})\)")


def _fts_cache_path():
    p = config.data_dir() / "edgar" / "_dead_name_fts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_fts_cache() -> dict:
    p = _fts_cache_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _efts_search(ticker: str, startdt: str, enddt: str | None,
                 forms: str = FTS_FORMS) -> dict | None:
    """EDGAR full-text search for an exact ticker phrase, date-windowed. Returns the
    parsed response, or None on any TRANSIENT failure (5xx/timeout) so the caller
    retries on a later run rather than caching a false miss; a real empty result
    comes back as a well-formed zero-hit payload."""
    import requests
    params = {"q": f'"{ticker}"', "forms": forms}
    if startdt:
        params["startdt"] = startdt
    if enddt:
        params["enddt"] = enddt
    for attempt in range(3):
        try:
            r = requests.get(EFTS_URL, params=params, headers=_headers(), timeout=40)
            if r.status_code == 404:
                return {"hits": {"total": {"value": 0}}, "aggregations": {}}
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — tolerate per-ticker failure (efts 5xx are common)
            if attempt == 2:
                log.debug("efts GET failed %s: %s", ticker, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _entity_buckets(data: dict | None) -> list[tuple[int, str, int]]:
    """[(cik, display_name, doc_count)] for the FULL result set (the entity_filter
    aggregation is complete — not just the first hits page), sorted doc_count-desc."""
    buckets = (((data or {}).get("aggregations") or {}).get("entity_filter") or {}).get("buckets") or []
    out: list[tuple[int, str, int]] = []
    for b in buckets:
        m = _CIK_IN_KEY.search(str(b.get("key", "")))
        if m:
            out.append((int(m.group(1)), str(b.get("key", "")), int(b.get("doc_count", 0))))
    out.sort(key=lambda x: -x[2])
    return out


def _dominant_cik(buckets: list[tuple[int, str, int]]) -> tuple[int | None, dict]:
    """The single filer that dominates the result set, or (None, meta) when no entity
    clears the threshold (ambiguous → resolve nothing). meta carries the evidence."""
    if not buckets:
        return None, {"top_docs": 0, "runner_docs": 0, "n_entities": 0}
    cik, name, top = buckets[0]
    runner = buckets[1][2] if len(buckets) > 1 else 0
    meta = {"top_docs": top, "runner_docs": runner, "top_name": name, "n_entities": len(buckets)}
    if top >= FTS_MIN_DOCS and (runner == 0 or top >= FTS_DOMINANCE * runner):
        return cik, meta
    return None, meta


def _ticker_in_name(ticker: str, names: list) -> bool:
    """True if the dead ticker's alphanumerics appear IN ORDER within any of the
    entity's current/former names — a cheap corroboration that the symbol plausibly
    derives from the company (ATW⊂A·T·Woods, XLNX⊂Xi·L·i·NX, SPLS⊂S·ta·PL·e·S). It
    defeats coincidental cover-page string hits to an UNRELATED filer: 'ANDV' is not
    a subsequence of 'American National Insurance' (no D), so Andeavor's symbol can
    no longer mis-resolve onto that filer."""
    tk = re.sub(r"[^A-Z0-9]", "", ticker.upper())
    if not tk:
        return False
    for nm in names:
        s = re.sub(r"[^A-Z0-9]", "", str(nm).upper())
        i = 0
        for ch in s:
            if i < len(tk) and ch == tk[i]:
                i += 1
        if i == len(tk):
            return True
    return False


def _confirm_filer(cik: int, ticker: str, member_end: str | None) -> tuple[bool, dict]:
    """Confirm an FTS-dominant CIK actually traded under `ticker`, via its
    data.sec.gov submissions doc. Rejects, in order: (a) a LIVE entity currently
    listed under a DIFFERENT symbol (a cover-page name coincidence, e.g. APPS→'Cyber
    Apps World'); (b) an entity still filing annual reports years past the dead name's
    index exit (not the delisted company); (c) an acquired/delisted filer whose name
    does NOT corroborate the symbol (the ticker isn't an in-order subsequence of any
    current/former name — kills coincidental string hits like ANDV→'American National
    Insurance'). An unreachable submissions doc is NOT accepted — precision over
    recall. Returns (accept, evidence)."""
    sub = _get_json(SUBMISSIONS_URL.format(cik))
    time.sleep(FTS_PACE_S)
    if not sub:
        return False, {"confirm": "unreachable"}
    cur = [str(t).upper() for t in (sub.get("tickers") or [])]
    ev = {"confirm_name": sub.get("name", ""),
          "former_names": [f.get("name") for f in (sub.get("formerNames") or [])],
          "current_tickers": cur}
    if cur and ticker.upper() not in cur:
        ev["confirm"] = "reject_live_mismatch"
        return False, ev
    rec = (sub.get("filings") or {}).get("recent") or {}
    annual = [d for f, d in zip(rec.get("form", []), rec.get("filingDate", []))
              if f in ANNUAL_FORMS]
    last = max(annual) if annual else None
    if last and member_end:
        try:
            cutoff = (pd.to_datetime(member_end) +
                      pd.Timedelta(days=FTS_RECENCY_GRACE_DAYS)).strftime("%Y-%m-%d")
            if last > cutoff:
                ev["confirm"], ev["last_annual"] = "reject_still_active", last
                return False, ev
        except Exception:  # noqa: BLE001
            pass
    # name corroboration — required for an acquired/delisted filer (empty current
    # tickers); a still-current symbol (ticker in cur) is already self-corroborating.
    if ticker.upper() not in cur and not _ticker_in_name(ticker, [ev["confirm_name"], *ev["former_names"]]):
        ev["confirm"] = "reject_no_name_corroboration"
        return False, ev
    ev["confirm"] = "accept"
    return True, ev


def _dead_windows() -> dict[str, tuple[str, str | None]]:
    """{dead ticker: (startdt, enddt)} — the S&P membership era per dead-only ticker
    (union of stints), clamped to the EDGAR FTS coverage floor and padded one year
    past the index exit (the final annual report files after the delisting)."""
    m = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
    dead = set(m[m["end_date"].notna()]["ticker"]) - set(m[m["end_date"].isna()]["ticker"])
    dm = m[m["ticker"].isin(dead)]
    g = dm.groupby("ticker").agg(start=("start_date", "min"), end=("end_date", "max"))
    floor = pd.Timestamp(EFTS_MIN_DATE)
    out: dict[str, tuple[str, str | None]] = {}
    for t, row in g.iterrows():
        start = max(pd.Timestamp(row["start"]), floor) if pd.notna(row["start"]) else floor
        end = (pd.Timestamp(row["end"]) + pd.Timedelta(days=365)) if pd.notna(row["end"]) else None
        out[str(t)] = (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d") if end is not None else None)
    return out


def _fts_stale(rec: dict | None) -> bool:
    """Due for a (re)attempt if never tried, or a soft-miss / transient error older
    than FTS_REFRESH_DAYS. A `resolved` or definitive `out_of_range` is never retried."""
    if rec is None:
        return True
    if rec.get("status") in ("resolved", "out_of_range"):
        return False
    ts = rec.get("attempted_utc")
    if not ts:
        return True
    try:
        return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days > FTS_REFRESH_DAYS
    except Exception:  # noqa: BLE001
        return True


def resolve_via_fulltext(tickers: list[str] | None = None, max_new: int = 150,
                         force: bool = False, forms: str = FTS_FORMS) -> dict:
    """Lift still-`unresolved` dead tickers -> CIK via the windowed EDGAR full-text
    crawl (see the section header). Resumable (per-ticker attempt cache in
    `_dead_name_fts.json`), drip-capped (`max_new`), SEC-paced, and resilient
    (transient efts/submissions failures retry on a later run). NEVER overwrites an
    existing CIK (seed / company_tickers / polygon precedence is preserved) and NEVER
    accepts an unconfirmed hit. Writes accepts into dead_name_cik.json as
    method="edgar_fts". Returns the FTS attempt cache."""
    cik_cache = _load_cik_cache()
    fts = _load_fts_cache()
    windows = _dead_windows()
    universe = tickers if tickers is not None else list(windows)
    # only the genuinely-unresolved tail (seed / company_tickers / polygon already won)
    unresolved = [t for t in universe if not (cik_cache.get(t) or {}).get("cik") and t in windows]

    def _prio(t: str):
        rec = fts.get(t)
        if rec is None:
            return (0, "")                         # never attempted — first
        return (1, rec.get("attempted_utc", ""))   # then the stalest retry
    todo = sorted([t for t in unresolved if force or _fts_stale(fts.get(t))], key=_prio)[:max_new]
    log.info("dead-name FTS crawl: %d unresolved, attempting %d (cap %d)",
             len(unresolved), len(todo), max_new)

    now = datetime.now(timezone.utc).isoformat()
    n_res = 0
    for t in todo:
        start, end = windows[t]
        if end is not None and end < EFTS_MIN_DATE:
            fts[t] = {"status": "out_of_range", "attempted_utc": now,
                      "note": "delisted before EDGAR full-text coverage (2001)"}
            continue
        data = _efts_search(t, start, end, forms)
        time.sleep(FTS_PACE_S)
        if data is None:
            fts[t] = {"status": "error", "attempted_utc": now}     # transient — retry later
            continue
        total = (((data.get("hits") or {}).get("total") or {}).get("value")) or 0
        cik, meta = _dominant_cik(_entity_buckets(data))
        if cik is None:
            fts[t] = {"status": "no_dominant", "attempted_utc": now, "total": total, **meta}
            continue
        ok, ev = _confirm_filer(cik, t, end)
        if not ok:
            fts[t] = {"status": ev.get("confirm", "rejected"), "attempted_utc": now,
                      "candidate_cik": cik, "total": total, **meta, **ev}
            continue
        fts[t] = {"status": "resolved", "attempted_utc": now, "cik": int(cik),
                  "total": total, **meta, **ev}
        if not (cik_cache.get(t) or {}).get("cik"):     # never clobber a higher-precedence hit
            cik_cache[t] = {"cik": int(cik), "method": "edgar_fts"}
            n_res += 1
    _fts_cache_path().write_text(json.dumps(fts, indent=0, sort_keys=True))
    _cik_cache_path().write_text(json.dumps(cik_cache, indent=0, sort_keys=True))
    log.info("dead-name FTS crawl: +%d resolved this run (method=edgar_fts)", n_res)
    return fts


# --------------------------------------------------------------------------- #
# Half 2 — companyfacts -> dead-name panel (leak-free, filed-stamped)
# --------------------------------------------------------------------------- #
def _frame_year(frame) -> int | None:
    """Fiscal-year label from an SEC frame tag ('CY2019' / 'CY2019Q4I' -> 2019)."""
    if not frame:
        return None
    m = _CY_RE.match(str(frame))
    return int(m.group(1)) if m else None


def _annual_dated(entries: list, instant: bool) -> dict[int, tuple[float, str, str]]:
    """{fiscal_year: (val, filed, period_end)} — the ORIGINAL annual disclosure of
    each fiscal year.

    Two companyfacts traps handled here:
      1. The SAME period is repeated across every filing that shows it as a
         comparative, each tagged with the *filing's* `fy` (not the period's) — so
         keying on `e["fy"]` grabs prior-year comparatives (ATVI's FY2009 10-K
         carries 2007/2008 rows all tagged fy=2009). We key by the reporting
         PERIOD (`end`) and keep the EARLIEST-filed entry (the value first
         knowable, stamped with its real filed date → leak-free `asof`).
      2. 52/53-week filers (Cerner, etc.) end a fiscal year on the Saturday near
         Dec 31, so the period end can fall in an ADJACENT calendar year and two
         fiscal years can share a calendar year — `year(end)` then mislabels and
         collides. We therefore label the fiscal year from the SEC `CY{year}`
         FRAME tag (the same canonical label the survivor frames panel uses),
         falling back to the entry's `fy` field, then to `year(end)`.
    Flows are restricted to a full-year period (~365d); balances take the
    period-end (instant) value."""
    by_period: dict[str, dict] = {}            # end -> {val, filed, label}
    for e in entries or []:
        if e.get("fp") != "FY" or e.get("form") not in ANNUAL_FORMS:
            continue
        val, end, filed = e.get("val"), e.get("end"), e.get("filed", "")
        if val is None or not end or not filed:
            continue
        if not instant:
            start = e.get("start")
            if not start:
                continue
            try:
                days = (pd.to_datetime(end) - pd.to_datetime(start)).days
            except Exception:  # noqa: BLE001
                continue
            if not (300 <= days <= 400):       # full fiscal year only
                continue
        # Label from the SEC frame when present (canonical; handles off-calendar
        # filers). When ABSENT, fall back to year(end) at collapse time — NOT the
        # entry's `fy`, which is the *filing's* year and so mislabels comparatives.
        lbl = _frame_year(e.get("frame"))
        rec = by_period.get(end)
        if rec is None:
            by_period[end] = {"val": float(val), "filed": filed, "label": lbl}
        else:
            if filed < rec["filed"]:           # earliest disclosure of this period
                rec["val"], rec["filed"] = float(val), filed
            if lbl is not None:                # a frame label is canonical — prefer it
                rec["label"] = lbl
    # collapse to fiscal-year label (latest period-end wins a label collision)
    best: dict[int, tuple[float, str, str]] = {}
    for end, rec in sorted(by_period.items()):
        lbl = rec["label"] if rec["label"] is not None else int(end[:4])
        best[int(lbl)] = (rec["val"], rec["filed"], end)
    return best


def _concept_dated(usgaap: dict, names: list[str], instant: bool,
                   unit: str = "USD") -> dict[int, tuple[float, str, str]]:
    """Merge a fallback chain across fiscal years (a filer migrates tags over time);
    earlier names in the chain win on a year both report."""
    out: dict[int, tuple[float, str, str]] = {}
    for nm in names:
        node = usgaap.get(nm)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        for fy, triple in _annual_dated(entries, instant=instant).items():
            out.setdefault(fy, triple)
    return out


def _panel_rows_for(ticker: str, cik: int) -> list[dict]:
    """Per-(ticker, fiscal_year) panel rows from one filer's companyfacts, schema-
    matched to fundamentals_panel and stamped with the true filed date."""
    data = _get_json(FACTS_URL.format(cik))
    time.sleep(0.12)                        # SEC fair-access pacing (<10 req/s)
    if not data:
        return []
    usgaap = (data.get("facts") or {}).get("us-gaap") or {}
    if not usgaap:
        return []
    series: dict[str, dict[int, tuple[float, str, str]]] = {}
    for key, names in _BALANCE.items():
        series[key] = _concept_dated(usgaap, names, instant=True,
                                     unit="shares" if key == "shares" else "USD")
    for key, names in _FLOW.items():
        series[key] = _concept_dated(usgaap, names, instant=False)

    fys = sorted({fy for s in series.values() for fy in s})
    rows = []
    for fy in fys:
        assets = series["assets"].get(fy)
        equity = series["equity"].get(fy)
        if assets is None and equity is None:
            continue                        # mirror panel dropna(assets, equity)
        # period_end / filed: take the assets (or equity) balance entry's stamps
        anchor = assets or equity
        period_end, filed = anchor[2], anchor[1]
        # asof = LATEST filed across this year's concepts (so the whole row is
        # knowable; still strictly > period_end, never a look-ahead)
        filed_dates = [v[1] for k in series for v in [series[k].get(fy)] if v]
        asof = max(filed_dates) if filed_dates else filed
        row = {"ticker": ticker, "cik": int(cik), "fy": int(fy)}
        for key in _BALANCE:
            v = series[key].get(fy)
            row[key] = v[0] if v else None
        for key in _FLOW:
            v = series[key].get(fy)
            row[key] = v[0] if v else None
        ap = series["assets"].get(fy - 1)
        npr = series["ni"].get(fy - 1)
        row["assets_prior"] = ap[0] if ap else None
        row["ni_prior"] = npr[0] if npr else None
        row["period_end"] = period_end
        row["asof_date"] = asof
        rows.append(row)
    return rows


def _dead_panel_path():
    p = config.data_dir() / "edgar" / "dead_name_panel.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def build_dead_panel(force: bool = False, max_new: int = 200,
                     tickers: list[str] | None = None) -> pd.DataFrame:
    """Resumably pull companyfacts for resolved dead names and write the leak-free,
    filed-stamped dead-name panel (schema-identical to fundamentals_panel). Drip-
    capped (`max_new`); skips filers already fetched within REFRESH_DAYS."""
    cache = _load_cik_cache()
    resolved = {t: v["cik"] for t, v in cache.items() if v.get("cik")}
    if tickers is not None:
        resolved = {t: c for t, c in resolved.items() if t in tickers}
    if not resolved:
        log.warning("build_dead_panel: no resolved CIKs — run resolve_dead_ciks first")
        return pd.DataFrame()

    out_p = _dead_panel_path()
    existing = pd.read_parquet(out_p) if out_p.exists() else pd.DataFrame()
    fetched_at = config.data_dir() / "edgar" / "_dead_name_fetched.json"
    seen = json.loads(fetched_at.read_text()) if fetched_at.exists() else {}

    def stale(t: str) -> bool:
        if force:
            return True
        ts = seen.get(t)
        if not ts:
            return True
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days > REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in resolved if stale(t)][:max_new]
    log.info("dead panel: %d resolved, fetching %d (cap %d)", len(resolved), len(todo), max_new)

    now = datetime.now(timezone.utc).isoformat()
    new_rows = []
    for t in todo:
        rows = _panel_rows_for(t, resolved[t])
        new_rows.extend(rows)
        seen[t] = now

    fresh = pd.DataFrame(new_rows)
    if not fresh.empty:
        fresh["period_end"] = pd.to_datetime(fresh["period_end"], errors="coerce")
        fresh["asof_date"] = pd.to_datetime(fresh["asof_date"], errors="coerce")
        fresh = fresh.dropna(subset=["period_end", "asof_date"])
        # leak guard: a report is filed AFTER its period closes, never before/at.
        fresh = fresh[fresh["asof_date"] > fresh["period_end"]]
    if not existing.empty and not fresh.empty:
        existing = existing[~existing["ticker"].isin(fresh["ticker"].unique())]
        panel = pd.concat([existing, fresh], ignore_index=True)
    else:
        panel = fresh if not fresh.empty else existing
    if not panel.empty:
        panel = panel.sort_values(["ticker", "fy"]).reset_index(drop=True)
        panel.to_parquet(out_p)
        fetched_at.write_text(json.dumps(seen, indent=0, sort_keys=True))
    log.info("dead panel: %d rows, %d tickers", len(panel),
             panel["ticker"].nunique() if "ticker" in panel else 0)
    return panel


# --------------------------------------------------------------------------- #
# Merge + honest coverage
# --------------------------------------------------------------------------- #
def merged_panel(survivor: pd.DataFrame | None = None) -> pd.DataFrame:
    """Survivor panel + dead-name panel, schema-aligned, deduped on (ticker, fy)
    with survivor rows winning a collision. This is the de-biased cross-section the
    factor scorecard and the shadow book should grade on."""
    if survivor is None:
        sp = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
        survivor = pd.read_parquet(sp) if sp.exists() else pd.DataFrame()
    dead_p = _dead_panel_path()
    dead = pd.read_parquet(dead_p) if dead_p.exists() else pd.DataFrame()
    if dead.empty:
        return survivor
    cols = list(survivor.columns) if not survivor.empty else list(dead.columns)
    dead = dead.reindex(columns=cols)
    both = pd.concat([survivor, dead], ignore_index=True) if not survivor.empty else dead
    both = both.drop_duplicates(subset=["ticker", "fy"], keep="first").reset_index(drop=True)
    return both


def coverage(dead_universe: list[str] | None = None) -> dict:
    """Honest dead-name coverage ratio every output should display. Writes
    data/edgar/_dead_name_coverage.json."""
    if dead_universe is None:
        m = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
        dead_universe = sorted(set(m[m["end_date"].notna()]["ticker"]) -
                               set(m[m["end_date"].isna()]["ticker"]))
    cache = _load_cik_cache()
    resolved = {t for t, v in cache.items() if v.get("cik")}
    by_method: dict[str, int] = {}
    for v in cache.values():
        if v.get("cik"):
            by_method[v.get("method", "?")] = by_method.get(v.get("method", "?"), 0) + 1
    # full-text crawl funnel — the honest record of what the long-tail leg could and
    # could NOT resolve (no_dominant / reject_* / out_of_range / error), so a reader
    # sees exactly how partial the bridge is rather than only the accepts.
    fts_funnel: dict[str, int] = {}
    for v in _load_fts_cache().values():
        s = v.get("status", "?")
        fts_funnel[s] = fts_funnel.get(s, 0) + 1
    dead_p = _dead_panel_path()
    with_funda = set()
    if dead_p.exists():
        with_funda = set(pd.read_parquet(dead_p, columns=["ticker"])["ticker"])
    n = len(dead_universe)
    out = {
        "schema": "dead_name_coverage.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_dead_universe": n,
        "n_cik_resolved": len(resolved & set(dead_universe)),
        "n_with_fundamentals": len(with_funda & set(dead_universe)),
        "coverage_frac": round(len(with_funda & set(dead_universe)) / n, 4) if n else 0.0,
        "resolved_by_method": by_method,
        "fts_funnel": fts_funnel,
        "note": "OPTIMISTIC de-bias bound — dead-name PRICES are still ~absent "
                "(yfinance survivor-only), so factor ICs over the merged panel are "
                "fundamentals-de-biased but price-join-limited. Stamp on every output.",
    }
    p = config.data_dir() / "edgar" / "_dead_name_coverage.json"
    p.write_text(json.dumps(out, indent=1))
    return out


def dead_universe() -> list[str]:
    """The 1,083-name dead-only S&P PIT universe (closed membership, never re-listed
    live)."""
    m = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
    return sorted(set(m[m["end_date"].notna()]["ticker"]) -
                  set(m[m["end_date"].isna()]["ticker"]))
