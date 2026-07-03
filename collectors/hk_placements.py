"""HKEX placement / rights-issue / open-offer announcement collector (H-PLC).

W1c of the HK/Canada masterplan (§3 H-PLC, §8 W1, PR "w1c(h-plc)").

WHY
---
HK's highest-frequency idiosyncratic run-killer is the discounted top-up placement /
rights issue: an issuer sells a block of new shares at a discount (often 10-20%) under
a general or specific mandate, diluting holders and hanging discounted stock over the
market. The masterplan ships this as a validation-free RISK GATE on the §5.0 ripe-list
contract ("not placement-flagged [HK]") — a demote + bilingual warning chip in
scripts/build_hk_library.py — plus a post-placement drift EVENT STUDY accrual in the
experiments registry.

SOURCE — HKEX headline-category feed (primary route; proxy NOT needed)
----------------------------------------------------------------------
The masterplan allowed a yfinance shares-outstanding-delta proxy if no reliable free
feed existed. One does (verified by direct fetch 2026-07-03): the HKEX news title
search servlet, keyless JSON, filtered by official headline category:

  https://www1.hkexnews.hk/search/titleSearchServlet.do
    ?sortDir=0&sortByOptions=DateTime&category=0&market=SEHK&stockId=-1
    &documentType=-1&fromDate=YYYYMMDD&toDate=YYYYMMDD&title=&searchType=1
    &t1code=10000&t2Gcode=8&t2code=<CATEGORY>&rowRange=<N>&lang=E

Categories (tier-2 codes from /ncms/script/eds/tiertwo_e.json, verified 2026-07-03):
  18480 = Placing          (~100 announcements/month across SEHK)
  18500 = Rights Issue     (~30/month)
  18460 = Open Offer       (rare; the third dilutive follow-on structure)
"Consideration Issue" (18240) is deliberately EXCLUDED — share-paid M&A is a different
mechanism from a discounted cash raise.

Headline categories exist from 2007-06-25 (titlesearch config.js HeadlineCategoryStart),
so --full-history backfills ~19 years of dateable dilution events — deep enough that
the drift event study has an archive leg as well as the forward accrual.

Servlet mechanics (all verified by probe):
  * one category per request (comma-joined t2code returns a non-JSON error page);
  * response JSON: {result: <stringified list>|"null", recordCnt, loadedRecord,
    hasNextRow, ...}; rows carry NEWS_ID, STOCK_CODE (zero-padded), STOCK_NAME,
    TITLE, SHORT_TEXT (headline-category breadcrumb), DATE_TIME (DD/MM/YYYY HH:MM),
    FILE_TYPE, DOD_WEB_PATH;
  * pagination via rowRange (page size, UI cap 1000/query — windows are split
    recursively if a window ever exceeds the cap);
  * date ranges longer than 1 month are allowed once a headline category is selected
    (config.js SearchDocAllMaxMonthRange applies to category-less queries only).

STORE (GIT-TRACKED, NOT R2)
---------------------------
  data/hk_placements/events.parquet
    columns: news_id (str), stock_code (str, servlet zero-padded), ticker (str,
             '0388.HK' 4-digit zero-padded — hk_stocks/hk_stocks_ext key format;
             None for non-numeric codes), category ('placing'|'rights_issue'|
             'open_offer'), announced_at (Timestamp, HKT), date (normalized day),
             title (str), subcats (str, cleaned SHORT_TEXT breadcrumb)
    append-only, deduped on (news_id, stock_code)
  data/hk_placements/coverage.json — freshness stamp
    {fetched_at, n_events, earliest, latest, n_new, by_category}

Store decision: ~1.5k events/year × 19y ≈ 30k rows — tiny; git-tracked (the nightly
lane's `git add data/` sweeps it; same treatment as data/hk_shorts/, see .gitignore).

FAIL-CLOSED / NAMED TRIPWIRE
----------------------------
  * HTTP failure or non-JSON reply after retries -> raises (never writes empty).
  * "hk_placements TRIPWIRE": the union of all three categories returning ZERO events
    over the trailing incremental window raises RuntimeError — SEHK has never gone a
    month without a single placing since 2007, so a zero read means the feed or the
    parameter contract regressed, not a quiet market.
  * stale_after_days=7 on the adapter: the runner marks the source stale when the
    newest stored announcement falls a week behind (placings print near-daily).

LANE CONTRACT
-------------
Network I/O lives here (collect lane ONLY). The render lane reads back via
``flag_map()`` / ``store_status()`` — pure parquet/JSON reads, no network.

RESUME / FULL HISTORY
---------------------
  python -m scripts.collect --only hk_placements                # trailing 35d top-up
  python -m scripts.collect --only hk_placements --full-history # 2007-06-25 -> today
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVLET = "https://www1.hkexnews.hk/search/titleSearchServlet.do"

# The servlet 404s/blank-pages library UAs; the browser UA below is the one the
# feasibility probe verified (2026-07-03).
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Tier-1 "Announcements and Notices" (10000) / tier-2 group 8 / tier-2 category codes.
_T1_CODE = "10000"
_T2G_CODE = "8"
_CATEGORIES = {
    "placing": "18480",
    "rights_issue": "18500",
    "open_offer": "18460",
}

# Headline categories exist from this date (titlesearch config.js HeadlineCategoryStart).
_HEADLINE_START = date(2007, 6, 25)

# UI row cap per query (config.js ViewMoreRecords) — windows split below this.
_ROW_CAP = 1000

# Incremental top-up window. 35d over-covers the daily/nightly cadence by a month so a
# few missed runs self-heal, and is short enough that a zero-union read is impossible
# in a functioning feed (the named tripwire).
_INCR_WINDOW_D = 35

# Trailing window inside which a placement/rights event demotes a name off the
# ripe-list entry groups (build_hk_library imports this — single source of truth).
# 90d covers the announcement -> record date -> dealing timeline of a rights issue
# and the post-placement overhang period of a top-up placing.
FLAG_WINDOW_D = 90

# A FRESH (empty) store bootstraps with a window that over-covers FLAG_WINDOW_D, so
# the demote gate is never silently under-covered on day one.
_BOOTSTRAP_WINDOW_D = 120

# Stores
_STORE = Path(config.data_dir()) / "hk_placements" / "events.parquet"
_COVERAGE = Path(config.data_dir()) / "hk_placements" / "coverage.json"

# Placings print near-daily across SEHK; a week-old newest event means the collector
# (or the feed) is broken.
_STALE_DAYS = 7

_EVENT_COLS = ["news_id", "stock_code", "ticker", "category",
               "announced_at", "date", "title", "subcats"]


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def code_to_ticker(code: str) -> str | None:
    """Servlet STOCK_CODE ('01323', '00139') -> panel ticker ('1323.HK', '0139.HK').

    The hk_stocks / hk_stocks_ext stores key names as 4-digit zero-padded '.HK'
    tickers. Non-numeric or out-of-range codes (debt/structured products) -> None.
    """
    try:
        n = int(str(code).strip())
    except (TypeError, ValueError):
        return None
    if not 1 <= n <= 99999:
        return None
    return f"{n:04d}.HK"


def _clean_text(s: str) -> str:
    """Unescape servlet HTML entities (&#x2f; etc.), strip tags and fold whitespace."""
    s = html.unescape(html.unescape(str(s or "")))   # servlet double-escapes some rows
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _rows_to_frame(rows: list[dict], category: str) -> pd.DataFrame:
    """Normalise raw servlet result rows into the canonical event-store frame."""
    out: list[dict] = []
    for r in rows:
        news_id = str(r.get("NEWS_ID") or "").strip()
        code = str(r.get("STOCK_CODE") or "").strip()
        if not news_id or not code:
            continue
        try:
            announced = pd.to_datetime(str(r.get("DATE_TIME") or "").strip(),
                                       format="%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            continue
        out.append({
            "news_id": news_id,
            "stock_code": code,
            "ticker": code_to_ticker(code),
            "category": category,
            "announced_at": announced,
            "date": announced.normalize(),
            "title": _clean_text(r.get("TITLE"))[:300],
            "subcats": _clean_text(r.get("SHORT_TEXT"))[:200],
        })
    return pd.DataFrame(out, columns=_EVENT_COLS)


def merge_events(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append-only merge deduped on (news_id, stock_code); keep-FIRST (immutable rows).

    A joint announcement lists one servlet row per stock code, so the pair — not
    news_id alone — is the event identity.
    """
    if existing is None or existing.empty:
        combined = new.copy()
    else:
        combined = pd.concat([existing, new], ignore_index=True)
    combined = (combined
                .drop_duplicates(subset=["news_id", "stock_code"], keep="first")
                .sort_values("announced_at")
                .reset_index(drop=True))
    return combined


# ---------------------------------------------------------------------------
# Servlet fetch
# ---------------------------------------------------------------------------

def _query(t2code: str, from_d: date, to_d: date, row_range: int,
           timeout: int = 60, retries: int = 3) -> dict:
    """One servlet GET -> parsed JSON dict. Raises on HTTP error / non-JSON reply."""
    params = {
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0",
        "market": "SEHK", "stockId": "-1", "documentType": "-1",
        "fromDate": from_d.strftime("%Y%m%d"), "toDate": to_d.strftime("%Y%m%d"),
        "title": "", "searchType": "1",
        "t1code": _T1_CODE, "t2Gcode": _T2G_CODE, "t2code": t2code,
        "rowRange": str(row_range), "lang": "E",
    }
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(_SERVLET, params=params, timeout=timeout,
                             headers={"User-Agent": _BROWSER_UA})
            r.raise_for_status()
            return json.loads(r.text)   # non-JSON (error page) raises -> retried
        except Exception as e:  # noqa: BLE001 — retried, then surfaced fail-closed
            last = e
            if attempt < retries - 1:
                wait = 3.0 * (2 ** attempt)
                log.warning("hk_placements: query t2=%s %s..%s attempt %d/%d failed "
                            "(%s); retry in %.0fs", t2code, from_d, to_d,
                            attempt + 1, retries, e, wait)
                time.sleep(wait)
    assert last is not None
    raise last


def _result_rows(payload: dict) -> list[dict]:
    res = payload.get("result")
    if not res or res == "null":
        return []
    return json.loads(res)


def _fetch_window(category: str, from_d: date, to_d: date) -> list[dict]:
    """All rows for one category over [from_d, to_d], splitting past the row cap.

    First request asks for the full cap; if the servlet still reports more rows
    than it returned (recordCnt > loadedRecord) the window is bisected — never
    silently truncated (house rule: no silent caps).
    """
    t2 = _CATEGORIES[category]
    payload = _query(t2, from_d, to_d, _ROW_CAP)
    rows = _result_rows(payload)
    record_cnt = int(payload.get("recordCnt") or 0)
    if record_cnt > len(rows) and from_d < to_d:
        mid = from_d + (to_d - from_d) / 2
        log.info("hk_placements: %s %s..%s over row cap (%d) — bisecting",
                 category, from_d, to_d, record_cnt)
        time.sleep(0.3)
        left = _fetch_window(category, from_d, mid)
        time.sleep(0.3)
        right = _fetch_window(category, mid + timedelta(days=1), to_d)
        return left + right
    if record_cnt > len(rows):   # single-day window over cap — has never happened
        log.warning("hk_placements: %s single-day %s exceeds row cap "
                    "(%d > %d rows returned)", category, from_d, record_cnt, len(rows))
    return rows


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Calendar-month windows covering [start, end] (backfill unit; ~30-150 rows each)."""
    out: list[tuple[date, date]] = []
    d = date(start.year, start.month, 1)
    while d <= end:
        nxt = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
        out.append((max(d, start), min(nxt - timedelta(days=1), end)))
        d = nxt
    return out


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

def _load_store() -> pd.DataFrame:
    if _STORE.exists():
        try:
            return pd.read_parquet(_STORE)
        except Exception as e:  # noqa: BLE001
            log.warning("hk_placements: store read failed (%s), starting fresh", e)
    return pd.DataFrame(columns=_EVENT_COLS)


def _save_store(df: pd.DataFrame) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_STORE, index=False)


def _write_coverage(df: pd.DataFrame, n_new: int) -> None:
    by_cat = (df["category"].value_counts().to_dict()) if not df.empty else {}
    _COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    _COVERAGE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "n_events": int(len(df)),
        "earliest": str(pd.Timestamp(df["date"].min()).date()) if not df.empty else "",
        "latest": str(pd.Timestamp(df["date"].max()).date()) if not df.empty else "",
        "n_new": int(n_new),
        "by_category": {str(k): int(v) for k, v in by_cat.items()},
    }, indent=2))


# ---------------------------------------------------------------------------
# Main fetch
# ---------------------------------------------------------------------------

def fetch_hk_placements(full_history: bool = False,
                        checkpoint_every: int = 12) -> int:
    """Pull placement/rights/open-offer announcements into the event store.

    Incremental (default): trailing ``_INCR_WINDOW_D`` days, one request per category.
    Full history: calendar-month windows per category from 2007-06-25 (~690 requests,
    checkpoint-saved so an interrupted backfill resumes losslessly — already-stored
    (news_id, stock_code) rows dedupe away).

    Returns the number of NEW event rows stored.

    Raises RuntimeError (the named "hk_placements TRIPWIRE") when the fetch yields
    zero events across ALL categories — a functioning feed cannot produce that over
    any month-scale window, so zero means the feed or parameter contract regressed.
    Never writes an empty store as success.
    """
    existing = _load_store()
    today = date.today()

    if full_history:
        windows = _month_windows(_HEADLINE_START, today)
    else:
        back = _BOOTSTRAP_WINDOW_D if existing.empty else _INCR_WINDOW_D
        windows = [(today - timedelta(days=back), today)]

    n_before = len(existing)
    n_fetched_rows = 0
    combined = existing
    since_checkpoint = 0
    for w_from, w_to in windows:
        for category in _CATEGORIES:
            rows = _fetch_window(category, w_from, w_to)
            n_fetched_rows += len(rows)
            frame = _rows_to_frame(rows, category)
            if not frame.empty:
                combined = merge_events(combined, frame)
            since_checkpoint += 1
            if full_history and since_checkpoint >= checkpoint_every:
                _save_store(combined)   # resumable backfill checkpoint
                since_checkpoint = 0
            time.sleep(0.3)   # polite pacing (keyless official endpoint)

    if n_fetched_rows == 0:
        raise RuntimeError(
            "hk_placements TRIPWIRE: 0 placement/rights/open-offer announcements "
            f"returned across all categories over {windows[0][0]}..{windows[-1][1]} — "
            "SEHK never goes a month without a placing; the feed or the parameter "
            "contract has regressed. Store NOT updated."
        )

    n_new = len(combined) - n_before
    _save_store(combined)
    _write_coverage(combined, n_new)
    log.info("hk_placements: %d fetched rows -> %d new events (store %d total, "
             "latest %s)", n_fetched_rows, n_new, len(combined),
             pd.Timestamp(combined["date"].max()).date() if not combined.empty else "-")
    return n_new


# ---------------------------------------------------------------------------
# Dilutive-title classifier (applied on READ; the store keeps every raw event)
# ---------------------------------------------------------------------------
# The headline categories over-capture (verified on the 2026 live feed): "Placing"
# also tags AT1/perpetual capital and convertible-BOND issues (HSBC 0005 AT1s,
# 0300 zero-coupon CBs), and "Rights Issue" tags plain AGM/EGM meeting notices for
# issuers with a program in flight. The run-killer mechanism is DISCOUNTED COMMON-
# EQUITY dilution, so a title must look like an actual share placing / rights issue /
# open offer to demote. Kept on the read path (not baked into the store) so the
# taxonomy can evolve without a store migration, and the drift event study can test
# both the raw and the filtered cut.

# Unambiguous equity-dilution phrases.
_STRONG_RE = re.compile(
    r"RIGHTS ISSUE|RIGHTS SHARES|OPEN OFFER|SHARE ISSUANCE|"
    r"ISSUE OF (NEW )?SHARES|ISSUANCE OF [A-Z\- ]*SHARES|"
    r"PLACING OF (NEW )?SHARES|TOP-?UP PLACING", re.I)
# Placing-ish tokens that qualify only when no debt instrument is named.
_WEAK_RE = re.compile(r"\bPLACING\b|\bSUBSCRIPTION\b", re.I)
_DEBT_RE = re.compile(
    r"\bBONDS?\b|\bNOTES?\b|CONVERTIBLE SECURITIES|PERPETUAL|CAPITAL SECURITIES",
    re.I)
# Procedural corporate-calendar rows (notices/poll results merely TAGGED with the
# category) and un-events (a cancelled/terminated raise is dilution NOT happening) —
# excluded unless the title itself carries a strong phrase.
_MEETING_RE = re.compile(
    r"SHAREHOLDERS' MEETING|GENERAL MEETING|\bAGM\b|\bEGM\b|\bSGM\b|"
    r"\bPROXY\b|\bCIRCULAR\b|\bCANCELLATION\b|\bTERMINATION\b", re.I)


def is_dilutive(title: str) -> bool:
    """True when an announcement title reads as a common-equity dilution event."""
    t = str(title or "")
    strong = bool(_STRONG_RE.search(t))
    if _MEETING_RE.search(t) and not strong:
        return False
    if strong:
        return True
    return bool(_WEAK_RE.search(t)) and not _DEBT_RE.search(t)


# ---------------------------------------------------------------------------
# Read-only API for the render lane (pure store reads — no network)
# ---------------------------------------------------------------------------

def store_status() -> dict:
    """Freshness stamp for render-lane health gating.

    Returns {available, n_events, latest, fetched_at}; ``available`` is False when
    the store is missing/empty (the caller shows a health row, never a silent
    fail-open gate).
    """
    df = _load_store()
    if df.empty:
        return {"available": False, "n_events": 0, "latest": None, "fetched_at": None}
    fetched_at = None
    try:
        fetched_at = json.loads(_COVERAGE.read_text()).get("fetched_at")
    except Exception:  # noqa: BLE001 — stamp is advisory; the event dates decide
        pass
    return {
        "available": True,
        "n_events": int(len(df)),
        "latest": str(pd.Timestamp(df["date"].max()).date()),
        "fetched_at": fetched_at,
    }


def flag_map(tickers: list[str], window_days: int = FLAG_WINDOW_D,
             asof: str | None = None) -> dict[str, dict]:
    """{ticker: latest DILUTIVE placement/rights event inside the trailing window}.

    Only titles passing ``is_dilutive`` count (AT1/CB issuance and meeting notices
    over-captured by the headline categories are screened out — see classifier
    block above). ``asof`` (panel date, 'YYYY-MM-DD') anchors the window so a render
    against an older panel never flags future announcements; defaults to the newest
    event date. Each value: {category, date, days_ago, title, n_events}. Pure
    parquet read.
    """
    df = _load_store()
    if df.empty:
        return {}
    want = {t for t in tickers if t}
    df = df[df["ticker"].isin(want) & df["title"].map(is_dilutive)]
    if df.empty:
        return {}
    anchor = pd.Timestamp(asof) if asof else pd.Timestamp(df["date"].max())
    d = df[(df["date"] <= anchor)
           & (df["date"] >= anchor - pd.Timedelta(days=window_days))]
    out: dict[str, dict] = {}
    for tk, grp in d.groupby("ticker"):
        last = grp.sort_values("announced_at").iloc[-1]
        out[str(tk)] = {
            "category": str(last["category"]),
            "date": str(pd.Timestamp(last["date"]).date()),
            "days_ago": int((anchor - pd.Timestamp(last["date"])).days),
            "title": str(last["title"]),
            "n_events": int(len(grp)),
        }
    return out


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class HkPlacementsAdapter(Adapter):
    """Plugs the H-PLC event fetch into the scripts/collect.py pipeline.

    Manages its own parquet store (data/hk_placements/) directly, like
    CiroShortAdapter / HkShortsPositionsAdapter; returns a summary frame indexed at
    the newest announcement date so run_adapter's staleness machinery (the
    stale_after_days tripwire surface) still works.
    """

    name = "hk_placements"
    group = "hk_placements"
    stale_after_days = _STALE_DAYS

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        n_new = fetch_hk_placements(full_history=full_history)
        df = _load_store()
        if df.empty:   # unreachable (fetch raises first) — belt for the runner
            raise RuntimeError("hk_placements: store empty after fetch")
        latest = pd.Timestamp(df["date"].max())
        summary = pd.DataFrame({"n_new": [n_new], "n_events_total": [len(df)]},
                               index=[latest])
        return {"events__summary": summary}


# ---------------------------------------------------------------------------
# CLI / manual run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="HKEX placement/rights announcement collector (H-PLC)")
    ap.add_argument("--full-history", action="store_true",
                    help=f"Backfill from {_HEADLINE_START} (headline-category epoch)")
    args = ap.parse_args()
    n = fetch_hk_placements(full_history=args.full_history)
    print(f"Done: {n} new events")
    if _COVERAGE.exists():
        print(_COVERAGE.read_text())
