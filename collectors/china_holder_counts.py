"""股东户数 (shareholder count) — the A-share retail-concentration tape (W1 CNH).

Chinese listed companies disclose their REGISTERED SHAREHOLDER COUNT each quarter (and
some names more often). A falling count with a flat float means the same shares sit in
fewer hands — 筹码集中, the native A-share concentration read that has no US analogue.
The vendor serves the latest disclosed period per name plus the prior period, so the
change tape accrues from the snapshot itself.

NAMING: deliberately NOT ``china_holders``. collectors/cn_holder_sale_calendar.py is the
减持 (insider SALE window) calendar — a completely unrelated dataset about who is selling,
not about how many holders there are. The two must never be conflated.

CONTEXT / INPUT TIER ONLY. Nothing here is scored, ranked, promoted, or surfaced on
site/; the leg registers as tier="pending" in engine/china_signal_lab.py (collected +
accruing).

VERIFIED ENDPOINT (live 2026-07-25, this runner):
  GET https://datacenter-web.eastmoney.com/api/data/v1/get
      ?sortColumns=HOLD_NOTICE_DATE,SECURITY_CODE&sortTypes=-1,-1&pageSize=500
      &pageNumber=<n>&reportName=RPT_HOLDERNUMLATEST&columns=…&source=WEB&client=WEB
  Envelope {result: {pages, count, data}} — ~5,535 names / 12 pages at pageSize=500.
  HOST NOTE: datacenter-web.eastmoney.com is SHARED with the serial-phase akshare/EM
  adapters, which is exactly why this collector is deliberately ABSENT from
  scripts/collect.py:_CONCURRENT_HOSTS — it stays in the serial lane.

Store contract: APPEND-ONLY point-in-time. data/china_holder_counts/holder_counts.parquet
dedups on (code, end_date) keep-LAST after ordering by notice_date, so a later notice
CORRECTS an earlier one for the same reporting period and a same-day re-collect never
duplicates. Every row carries fetched_at (UTC ISO). Vendor nulls are coerced to NaN and
LEFT as NaN — never zero-filled — so a missing disclosure stays visibly missing.

Politeness + budget: ≥1.0 s + jitter before EVERY request, page-1-descending by notice
date with an early stop as soon as a page contributes no new (code, end_date) key, a
12-page cap, and a ~100 s in-collector wall-clock guard. The first run seeds the full
snapshot (~12 pages ≈ 25 s at pace). A 0-new-row night is a success, never a crash.
"""
from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger("china_holder_counts")

# ------------------------------------------------------------------ constants --

GROUP = "china_holder_counts"
_ENDPOINT = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REFERER = "https://data.eastmoney.com/"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_REPORT_NAME = "RPT_HOLDERNUMLATEST"
_FIELDS = (
    "SECURITY_CODE,SECURITY_NAME_ABBR,END_DATE,INTERVAL_CHRATE,AVG_MARKET_CAP,"
    "AVG_HOLD_NUM,TOTAL_MARKET_CAP,TOTAL_A_SHARES,HOLD_NOTICE_DATE,HOLDER_NUM,"
    "PRE_HOLDER_NUM,HOLDER_NUM_CHANGE,HOLDER_NUM_RATIO,PRE_END_DATE"
)
_PAGE_SIZE = 500
_PAGE_CAP = 12          # ~5,535 names today; the cap bounds a full seed run
_PACE_S = 1.0
_JITTER_S = 0.3
_TIMEOUT = (10, 20)
_BUDGET_S = 100.0

_COLUMNS = (
    "code",
    "name",
    "end_date",           # reporting period end (YYYY-MM-DD) — half of the PIT key
    "pre_end_date",
    "notice_date",        # HOLD_NOTICE_DATE (YYYY-MM-DD) — a later notice corrects
    "holder_num",
    "pre_holder_num",
    "holder_num_change",
    "holder_num_ratio",   # QoQ % change in holder count
    "avg_hold_num",
    "avg_market_cap",
    "total_market_cap",
    "total_a_shares",
    "interval_chrate",    # price change over the interval, %
    "fetched_at",
)
_NUMERIC_COLUMNS = (
    "holder_num", "pre_holder_num", "holder_num_change", "holder_num_ratio",
    "avg_hold_num", "avg_market_cap", "total_market_cap", "total_a_shares",
    "interval_chrate",
)
_KEY = ["code", "end_date"]


# ------------------------------------------------------------------ paths / store --

def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _store_path() -> Path:
    return _dir() / "holder_counts.parquet"


def load_holder_counts() -> pd.DataFrame:
    path = _store_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_holder_counts: could not read holder_counts.parquet: %s", e)
    return pd.DataFrame(columns=list(_COLUMNS))


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """pd.to_numeric(errors='coerce') over the numeric columns. Vendor nulls stay NaN.

    Deliberately NOT fillna(0): a name that did not disclose is MISSING, and a zero
    would read as "no shareholders", which is a different and false claim.
    """
    out = df.copy()
    for col in _NUMERIC_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def write_holder_counts(rows: list[dict]) -> int:
    """Append rows, dedup (code, end_date) keep-LAST ordered by notice_date.

    Returns the count of net-new (code, end_date) keys. Never raises — a store
    failure is logged and the night degrades to 0 net-new.
    """
    if not rows:
        return 0
    try:
        new_df = coerce_numeric(pd.DataFrame(rows).reindex(columns=list(_COLUMNS)))
        existing = load_holder_counts()
        if existing.empty:
            merged, pre = new_df, 0
        else:
            pre = len(existing.drop_duplicates(subset=_KEY))
            merged = pd.concat([existing, new_df], ignore_index=True)
        # Order by notice_date so keep-LAST resolves to the LATEST notice for a period;
        # ties fall to the freshly fetched row (stable sort, new rows appended last).
        merged = merged.sort_values(["code", "end_date", "notice_date"],
                                    kind="stable", na_position="first")
        merged = merged.drop_duplicates(subset=_KEY, keep="last")
        merged = merged.sort_values(["notice_date", "code"],
                                    na_position="last").reset_index(drop=True)
        merged.to_parquet(_store_path(), index=False)
        return int(len(merged) - pre)
    except Exception as e:  # noqa: BLE001
        log.error("china_holder_counts.write_holder_counts failed: %s", e)
        return 0


# ------------------------------------------------------------------ pure parsers --

def _text(value) -> str:
    """None-safe text (keeps a literal 0, which `or ''` would silently blank)."""
    return "" if value is None else str(value)


def _date_part(value) -> str:
    """'2026-06-30 00:00:00' → '2026-06-30'; '' when unparseable. Pure."""
    s = _text(value).strip()
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else ""


def parse_holder_row(raw: dict, fetched_at: str) -> dict:
    """One RPT_HOLDERNUMLATEST row → one canonical store row. Pure (no I/O).

    Numeric fields are passed through as the vendor sent them; coerce_numeric()
    applies pd.to_numeric(errors='coerce') when the frame is built, so a vendor
    null survives as NaN rather than being invented as 0.
    """
    return {
        "code": _text(raw.get("SECURITY_CODE")),
        "name": _text(raw.get("SECURITY_NAME_ABBR")),
        "end_date": _date_part(raw.get("END_DATE")),
        "pre_end_date": _date_part(raw.get("PRE_END_DATE")),
        "notice_date": _date_part(raw.get("HOLD_NOTICE_DATE")),
        "holder_num": raw.get("HOLDER_NUM"),
        "pre_holder_num": raw.get("PRE_HOLDER_NUM"),
        "holder_num_change": raw.get("HOLDER_NUM_CHANGE"),
        "holder_num_ratio": raw.get("HOLDER_NUM_RATIO"),
        "avg_hold_num": raw.get("AVG_HOLD_NUM"),
        "avg_market_cap": raw.get("AVG_MARKET_CAP"),
        "total_market_cap": raw.get("TOTAL_MARKET_CAP"),
        "total_a_shares": raw.get("TOTAL_A_SHARES"),
        "interval_chrate": raw.get("INTERVAL_CHRATE"),
        "fetched_at": fetched_at,
    }


def parse_page(payload: dict, fetched_at: str) -> tuple[list[dict], int]:
    """One envelope → (rows, total_names). Pure; a shape drift degrades to ([], 0)."""
    result = (payload or {}).get("result") or {}
    data = [r for r in (result.get("data") or []) if isinstance(r, dict)]
    try:
        count = int(result.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    return [parse_holder_row(r, fetched_at) for r in data], count


def row_key(row: dict) -> tuple[str, str]:
    """The natural PIT key of one row. Pure."""
    return (str(row.get("code") or ""), str(row.get("end_date") or ""))


def known_keys(store: pd.DataFrame) -> set[tuple[str, str]]:
    """Every (code, end_date) already on disk. Pure over the passed frame."""
    if store.empty or not set(_KEY).issubset(store.columns):
        return set()
    return {(str(c), str(d)) for c, d in zip(store["code"], store["end_date"])}


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {"User-Agent": _UA, "Referer": _REFERER}


def _pace() -> None:
    """Politeness sleep before EVERY request: ≥1.0 s to the single upstream host."""
    time.sleep(_PACE_S + random.uniform(0.0, _JITTER_S))  # noqa: S311


def _clock() -> float:
    """Monotonic seconds. Indirected so the wall-clock guard is unit-testable."""
    return time.monotonic()


def _page_url(page: int) -> str:
    return (f"{_ENDPOINT}?sortColumns=HOLD_NOTICE_DATE,SECURITY_CODE&sortTypes=-1,-1"
            f"&pageSize={_PAGE_SIZE}&pageNumber={page}&reportName={_REPORT_NAME}"
            f"&columns={_FIELDS}&source=WEB&client=WEB")


def _fetch_page(session, page: int) -> dict:
    """Paced GET of one page → parsed JSON. Raises on transport/HTTP failure."""
    _pace()
    r = session.get(_page_url(page), headers=_headers(), timeout=_TIMEOUT)
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from datacenter-web.eastmoney.com")
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ nightly refresh --

def refresh() -> dict:
    """Page the notice-date-descending snapshot until a page adds nothing new.

    The stop rule is the point of the sort: rows are served newest-notice-first, so
    the first page whose (code, end_date) keys are ALL already on disk means every
    later page is older still. The first run has an empty store and therefore seeds
    the full ~12-page snapshot.

    Raises RuntimeError only when NO page fetched successfully. A night where every
    page was already known is a success with n_new=0.

    Returns the sentinel counters written to data/china_holder_counts/refresh.parquet.
    """
    import requests  # lazy

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()
    session = requests.Session()

    seen = known_keys(load_holder_counts())
    rows: list[dict] = []
    ok_pages = failed_pages = 0
    total_names = 0
    page = 1
    while page <= _PAGE_CAP:
        if _clock() - t0 > _BUDGET_S:
            log.warning("china_holder_counts: %.0fs wall-clock guard hit at page %d — "
                        "keeping %d rows (tomorrow re-pages from the top)",
                        _BUDGET_S, page, len(rows))
            break
        try:
            page_rows, count = parse_page(_fetch_page(session, page), fetched_at)
        except Exception as e:  # noqa: BLE001 — per-page isolation
            failed_pages += 1
            log.warning("china_holder_counts: page %d failed: %s", page, e)
            break
        ok_pages += 1
        total_names = max(total_names, count)
        if not page_rows:
            log.info("china_holder_counts: page %d empty — end of snapshot", page)
            break
        fresh = [r for r in page_rows if row_key(r) not in seen]
        rows.extend(page_rows)
        seen.update(row_key(r) for r in page_rows)
        if not fresh:
            log.info("china_holder_counts: page %d contributed 0 new (code, end_date) "
                     "keys — stopping (later pages are older still)", page)
            break
        if page >= _PAGE_CAP:
            log.warning("china_holder_counts: hit the %d-page cap with new keys still "
                        "arriving — tomorrow's run continues from the top", _PAGE_CAP)
            break
        page += 1

    if ok_pages == 0:
        raise RuntimeError("china_holder_counts: every page failed at transport level")

    n_new = write_holder_counts(rows)
    log.info("china_holder_counts: pages_ok=%d pages_failed=%d rows=%d net_new=%d "
             "universe=%d", ok_pages, failed_pages, len(rows), n_new, total_names)
    return {"n_new": n_new, "n_fetched": len(rows), "n_failed": failed_pages,
            "universe": total_names, "shard": ok_pages}


# ------------------------------------------------------------------ adapter --

class ChinaHolderCountsAdapter(Adapter):
    """股东户数 quarterly retail-concentration tape (W1 CNH) — context tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_holder_counts`` starts with ``china`` so it is auto-assigned to the asia
    lane. Deliberately NOT registered in scripts/collect.py:_CONCURRENT_HOSTS —
    datacenter-web.eastmoney.com is shared with the serial akshare/EM adapters.
    fetch() returns a COVERAGE sentinel — not a bare count — so
    data/china_holder_counts/refresh.parquet is a readable run ledger.

    stale_after_days=10: disclosure is quarterly per name but the whole-market notice
    tape advances most trading days; 10 days of silence is a real outage.
    """

    name = "china_holder_counts"
    group = GROUP
    stale_after_days = 10

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent).
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame(
            {k: [float(s[k])] for k in ("n_new", "n_fetched", "n_failed", "universe", "shard")},
            index=[idx],
        )
        sentinel.index.name = "collected_at"
        return {"refresh": sentinel}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    s = refresh()
    print(f"china_holder_counts: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
