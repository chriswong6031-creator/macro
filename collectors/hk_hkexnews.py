"""HKEX News company-catalyst filing collector (H-FBus).

Builds a deterministic per-name catalyst event tape from HKEXnews headline
categories: buybacks, results, general-mandate/dilution, and major-shareholder
changes. Display-only context layer — answers "what corporate event is behind
this move?" — not a buy/sell signal.

SCOPE
-----
Four NEW headline categories (Placement/Rights/OpenOffer already live in
hk_placements.py — this collector deliberately EXCLUDES them to avoid
duplication; they are read/joined at the engine layer):

  Category   t2code  t2Gcode  Vol/90d  Notes
  ─────────────────────────────────────────────────────────────────────────────
  Buyback      18100    8       ~16     "Announcement pursuant to Code on
                                        Share Buy-backs" — includes off-mkt
                                        offers AND on-mkt scheme announcements.
                                        Volume is thin; substantive events only.
  Final Res    13300    3      ~526     Annual/full-year results
  Interim Res  13400    3       ~53     Half-year results
  Gen Mandate  18380    8      ~374     "Issue of Shares under a General Mandate"
                                        — directly dilutive (the equity-issuance
                                        channel parallel to hk_placements 18480)
  Shareholder  17200    7       ~68     "Change in Shareholding" — captures
                                        substantial-shareholder build-ups
                                        (national team, activist, strategic).

SOURCE
------
Same endpoint as hk_placements.py and hk_cbbc.py (verified 2026-07-08):
  https://www1.hkexnews.hk/search/titleSearchServlet.do
Keyless JSON; browser UA required; one category per request.

Category codes verified 2026-07-08 via tiertwo_e.json + live probes:
  18100 = "Announcement pursuant to Code on Share Buy-backs"  (t2Gcode=8)
  13300 = "Final Results"                                     (t2Gcode=3)
  13400 = "Interim Results"                                   (t2Gcode=3)
  18380 = "Issue of Shares under a General Mandate"           (t2Gcode=8)
  17200 = "Change in Shareholding"                            (t2Gcode=7)

Live probe results (90-day window ending 2026-07-08):
  buyback:        16 announcements
  final_results: 526 announcements
  interim_results: 53 announcements
  general_mandate: 374 announcements
  shareholder:     68 announcements

STORE (git-tracked, same pattern as hk_placements)
-----
  data/hk_filings/events.parquet
    columns: news_id, stock_code, ticker, category, announced_at, date,
             title, subcats
  data/hk_filings/coverage.json — freshness stamp

FAIL-OPEN DESIGN
----------------
  * Every HTTP failure logs a warning and degrades gracefully; no crash.
  * Zero-event fetches are logged (not raised) — the 90-day tape starts fresh
    on day 1 and grows forward; zero is possible for rare categories.
  * Missing store returns empty DataFrame (render lane degrades to '—').

LANE CONTRACT
-------------
  Network I/O: collect lane ONLY.
  Render lane reads back via load_store() / store_status() — pure parquet reads.

TOsS COMPLIANCE
---------------
  Trailing 90-day window only; no deep bulk archive scrape. Polite pacing
  (0.3s between requests).
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

# Same browser UA as hk_placements (verified endpoint requirement 2026-07-03/07-08)
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Tier-1 "Announcements and Notices" (10000) t2 codes (verified 2026-07-08)
# Format: category_key -> (t2code, t2Gcode)
_CATEGORIES: dict[str, tuple[str, str]] = {
    "buyback":          ("18100", "8"),   # Announcement pursuant to Code on Share Buy-backs
    "final_results":    ("13300", "3"),   # Final Results
    "interim_results":  ("13400", "3"),   # Interim Results
    "general_mandate":  ("18380", "8"),   # Issue of Shares under a General Mandate
    "shareholder":      ("17200", "7"),   # Change in Shareholding
}

_T1_CODE = "10000"

# Row cap (same as hk_placements — UI enforced 1000/query; windows bisect above)
_ROW_CAP = 1000

# Trailing window (ToS: no deep bulk archive; 90d covers one results season)
_WINDOW_D = 90

# Staleness threshold: results print ~twice/year (250d max), shareholder/buyback
# near-weekly during active periods. Use 14d as a soft flag — two missed sessions.
_STALE_DAYS = 14

_EVENT_COLS = ["news_id", "stock_code", "ticker", "category",
               "announced_at", "date", "title", "subcats"]

# Store
def _store_path(data_root: Path | None = None) -> Path:
    root = data_root or Path(config.data_dir())
    return root / "hk_filings" / "events.parquet"

def _coverage_path(data_root: Path | None = None) -> Path:
    root = data_root or Path(config.data_dir())
    return root / "hk_filings" / "coverage.json"


# ---------------------------------------------------------------------------
# Normalisation helpers (shared pattern with hk_placements)
# ---------------------------------------------------------------------------

def code_to_ticker(code: str) -> str | None:
    """Servlet STOCK_CODE ('01323') → panel ticker ('1323.HK').

    Handles multi-stock joint announcement codes (comma-separated) by
    returning the FIRST numeric code only. Non-numeric → None.
    """
    if not code:
        return None
    # Joint announcement: "01024<br/>81024" — take first numeric segment
    first = re.split(r"[<,\s]+", str(code).strip())[0]
    try:
        n = int(first)
    except (TypeError, ValueError):
        return None
    if not 1 <= n <= 99999:
        return None
    return f"{n:04d}.HK"


def _clean_text(s: str) -> str:
    """Unescape double-escaped HTML entities, strip tags, fold whitespace."""
    s = html.unescape(html.unescape(str(s or "")))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _rows_to_frame(rows: list[dict], category: str) -> pd.DataFrame:
    """Normalise raw servlet rows into the canonical event frame."""
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


def _merge(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append-only merge deduped on (news_id, stock_code); keep-FIRST."""
    if existing is None or existing.empty:
        combined = new.copy()
    else:
        combined = pd.concat([existing, new], ignore_index=True)
    return (combined
            .drop_duplicates(subset=["news_id", "stock_code"], keep="first")
            .sort_values("announced_at")
            .reset_index(drop=True))


# ---------------------------------------------------------------------------
# Servlet fetch helpers (verbatim pattern from hk_placements._query)
# ---------------------------------------------------------------------------

def _query(t2code: str, t2gcode: str,
           from_d: date, to_d: date,
           row_range: int, timeout: int = 60, retries: int = 3) -> dict:
    """One servlet GET → parsed JSON dict. Fails open: returns {} on persistent error."""
    params = {
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0",
        "market": "SEHK", "stockId": "-1", "documentType": "-1",
        "fromDate": from_d.strftime("%Y%m%d"), "toDate": to_d.strftime("%Y%m%d"),
        "title": "", "searchType": "1",
        "t1code": _T1_CODE, "t2Gcode": t2gcode, "t2code": t2code,
        "rowRange": str(row_range), "lang": "E",
    }
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(_SERVLET, params=params, timeout=timeout,
                             headers={"User-Agent": _BROWSER_UA})
            r.raise_for_status()
            return json.loads(r.text)
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                wait = 3.0 * (2 ** attempt)
                log.warning("hk_hkexnews: query t2=%s %s..%s attempt %d/%d "
                            "failed (%s); retry in %.0fs",
                            t2code, from_d, to_d, attempt + 1, retries, e, wait)
                time.sleep(wait)
    log.warning("hk_hkexnews: query t2=%s %s..%s failed after %d attempts: %s",
                t2code, from_d, to_d, retries, last)
    return {}


def _result_rows(payload: dict) -> list[dict]:
    res = payload.get("result")
    if not res or res == "null":
        return []
    try:
        return json.loads(res)
    except (json.JSONDecodeError, TypeError):
        return []


def _fetch_window(category: str, from_d: date, to_d: date) -> list[dict]:
    """All rows for one category over [from_d, to_d], bisecting past the row cap."""
    t2code, t2gcode = _CATEGORIES[category]
    payload = _query(t2code, t2gcode, from_d, to_d, _ROW_CAP)
    if not payload:
        return []
    rows = _result_rows(payload)
    record_cnt = int(payload.get("recordCnt") or 0)
    if record_cnt > len(rows) and from_d < to_d:
        mid = from_d + (to_d - from_d) / 2
        log.info("hk_hkexnews: %s %s..%s over row cap (%d) — bisecting",
                 category, from_d, to_d, record_cnt)
        time.sleep(0.3)
        left = _fetch_window(category, from_d, mid)
        time.sleep(0.3)
        right = _fetch_window(category, mid + timedelta(days=1), to_d)
        return left + right
    if record_cnt > len(rows):
        log.warning("hk_hkexnews: %s single-day %s exceeds row cap "
                    "(%d > %d)", category, from_d, record_cnt, len(rows))
    return rows


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

def load_store(data_root: Path | None = None) -> pd.DataFrame:
    """Load event store. Returns empty DataFrame if missing/corrupt (fail-open)."""
    p = _store_path(data_root)
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("hk_hkexnews: store read failed (%s), starting fresh", e)
    return pd.DataFrame(columns=_EVENT_COLS)


def _save_store(df: pd.DataFrame, data_root: Path | None = None) -> None:
    p = _store_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def _write_coverage(df: pd.DataFrame, n_new: int,
                    data_root: Path | None = None) -> None:
    by_cat = df["category"].value_counts().to_dict() if not df.empty else {}
    p = _coverage_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
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

def fetch_hk_filings(window_days: int = _WINDOW_D,
                     data_root: Path | None = None) -> int:
    """Pull filing events for the new categories into the event store.

    Fetches each category over the trailing ``window_days`` window.
    Fail-open: individual category failures log and continue; the store is
    updated with whatever was successfully fetched.

    Does NOT fetch placements/rights/open-offers — those live in
    hk_placements.py; the engine layer joins them at render time.

    Returns number of new event rows stored.
    """
    existing = load_store(data_root)
    today = date.today()
    from_d = today - timedelta(days=window_days)
    n_before = len(existing)
    combined = existing

    for category in _CATEGORIES:
        try:
            rows = _fetch_window(category, from_d, today)
            frame = _rows_to_frame(rows, category)
            if not frame.empty:
                combined = _merge(combined, frame)
            log.info("hk_hkexnews: %s → %d rows", category, len(rows))
        except Exception as e:  # noqa: BLE001
            log.warning("hk_hkexnews: %s fetch failed (%s); continuing", category, e)
        time.sleep(0.3)

    n_new = len(combined) - n_before
    try:
        _save_store(combined, data_root)
        _write_coverage(combined, n_new, data_root)
    except Exception as e:  # noqa: BLE001
        log.error("hk_hkexnews: store write failed (%s)", e)

    log.info("hk_hkexnews: fetch complete — %d new rows (store %d total)",
             n_new, len(combined))
    return n_new


# ---------------------------------------------------------------------------
# Read-only API for the render lane
# ---------------------------------------------------------------------------

def store_status(data_root: Path | None = None) -> dict:
    """Freshness stamp for render-lane health gating.

    Returns {available, n_events, latest, fetched_at}.
    ``available`` is False when the store is missing/empty.
    """
    p = _coverage_path(data_root)
    if not p.exists():
        return {"available": False, "n_events": 0, "latest": None, "fetched_at": None}
    try:
        d = json.loads(p.read_text())
        d["available"] = bool(d.get("n_events", 0))
        return d
    except Exception:  # noqa: BLE001
        return {"available": False, "n_events": 0, "latest": None, "fetched_at": None}


# ---------------------------------------------------------------------------
# Adapter (mirrors HkPlacementsAdapter / HkCbbcAdapter pattern)
# ---------------------------------------------------------------------------

class HkHkexnewsAdapter(Adapter):
    """Plugs the HKEXnews filing bus into the scripts/collect.py pipeline.

    Collects buyback / results / general-mandate / shareholder events.
    Placement/rights/open-offer categories are NOT collected here (hk_placements
    handles them) — the engine joins them at render time.
    """

    name = "hk_hkexnews"
    group = "hk_hkexnews"   # asia prefix match → runs in the asia-close lane
    stale_after_days = _STALE_DAYS

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # full_history is ignored for this collector (ToS: recent window only)
        n_new = fetch_hk_filings()
        df = load_store()
        if df.empty:
            today = pd.Timestamp.today().normalize()
            summary = pd.DataFrame({"n_new": [0], "n_events_total": [0]},
                                   index=[today])
            return {"filings__summary": summary}
        latest = pd.Timestamp(df["date"].max())
        summary = pd.DataFrame({"n_new": [n_new], "n_events_total": [len(df)]},
                               index=[latest])
        return {"filings__summary": summary}


# ---------------------------------------------------------------------------
# CLI / manual run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO,
                         format="%(levelname)s %(name)s %(message)s")
    n = fetch_hk_filings()
    print(f"Done: {n} new events")
    p = _coverage_path()
    if p.exists():
        print(p.read_text())
