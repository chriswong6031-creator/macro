"""Backfill the HK Southbound Connect holdings panel.

Eastmoney RPT_MUTUAL_STOCK_HOLDRANKS enforces a strict 2-year rolling window.
Earliest confirmed date: 2024-07-03 (verified by red-team probe).

Design
------
- Pages ascending (sortTypes=1) so earliest dates come first.
- Accumulates all new-date DataFrames IN MEMORY (no per-date parquet I/O).
- Single combine_first write at the end: O(1) vs O(n^2) for per-date writes.
- Idempotent: loads existing dates on startup, skips already-captured dates.
- Rate-limited at >= 0.45 s / page to avoid hammering Eastmoney.
- Writes gap-detection audit JSON after every batch write.

Usage
-----
    python3 scripts/backfill_hk_southbound.py
    python3 scripts/backfill_hk_southbound.py --dry-run          # no writes
    python3 scripts/backfill_hk_southbound.py --max-dates 10     # quick test
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# Absolute root: scripts/ -> repo root, independent of CWD
ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────
_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_H = {"User-Agent": _UA, "Referer": "https://data.eastmoney.com/"}
_SB_TYPES = ("003", "004")   # 港股通(沪) + 港股通(深)
_RATE_LIMIT_S = 0.45         # min gap between page fetches
_PAGE_SIZE = 500
_RETRIES = 4
_TIMEOUT = 30

_STORE_DIR = ROOT / "data" / "hk_southbound"
_STORE_PATH = _STORE_DIR / "holdings.parquet"
_AUDIT_PATH = _STORE_DIR / "backfill_gap_audit.json"


# ── helpers ────────────────────────────────────────────────────────────────────
def _normalize(secucode: str) -> str | None:
    """Eastmoney ``00700.HK`` -> our universe ``0700.HK``."""
    if not secucode or "." not in secucode:
        return None
    num = secucode.split(".")[0].lstrip("0") or "0"
    if not num.isdigit():
        return None
    return f"{int(num):04d}.HK"


def _load_existing_dates() -> set[str]:
    """Return set of YYYY-MM-DD strings already in the parquet store."""
    if not _STORE_PATH.exists():
        return set()
    try:
        df = pd.read_parquet(_STORE_PATH)
        if isinstance(df.index, pd.MultiIndex):
            return {str(d)[:10] for d in df.index.get_level_values("date").unique()}
        return set()
    except Exception as e:  # noqa: BLE001
        log.warning("Could not read existing store: %s", e)
        return set()


def _write_gap_audit(all_dates: list[str]) -> None:
    """Write backfill_gap_audit.json with gap-detection tripwire."""
    dates_sorted = sorted(d[:10] for d in all_dates if d)
    gaps = []
    for i in range(1, len(dates_sorted)):
        d0 = dates_sorted[i - 1]
        d1 = dates_sorted[i]
        bd = int(np.busday_count(d0, d1))
        if bd > 3:
            gaps.append({"from": d0, "to": d1, "bdays": bd})
    audit = {
        "updated": str(date.today()),
        "n_dates": len(dates_sorted),
        "earliest": dates_sorted[0] if dates_sorted else None,
        "latest": dates_sorted[-1] if dates_sorted else None,
        "n_gaps": len(gaps),
        "gaps": gaps,
        "verdict": "GAPS_DETECTED" if gaps else "OK",
    }
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    _AUDIT_PATH.write_text(json.dumps(audit, indent=2))
    log.info("Gap audit: %s (%d dates, %d gaps)", audit["verdict"],
             len(dates_sorted), len(gaps))


def _fetch_page(page: int) -> list[dict]:
    """Fetch one page ascending by HOLD_DATE (sortTypes=1 = ascending)."""
    import requests
    flt = '(MUTUAL_TYPE in ("%s"))(INTERVAL_TYPE="1")' % '","'.join(_SB_TYPES)
    params = {
        "reportName": "RPT_MUTUAL_STOCK_HOLDRANKS",
        "columns": "ALL",
        "pageSize": _PAGE_SIZE,
        "pageNumber": page,
        "sortColumns": "HOLD_DATE",
        "sortTypes": 1,   # ascending — earliest dates first
        "filter": flt,
    }
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            r = requests.get(_DC, params=params, headers=_H, timeout=_TIMEOUT)
            data = (r.json().get("result") or {}).get("data") or []
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            sleep_s = 1.5 * (attempt + 1)
            log.warning("page %d attempt %d failed (%s) — retry in %.1fs", page, attempt + 1, e, sleep_s)
            time.sleep(sleep_s)
    log.error("page %d failed after %d tries: %s", page, _RETRIES, last)
    return []


def _rows_to_df(rows: list[dict], hold_date: str) -> pd.DataFrame | None:
    """Convert raw API rows for a single date into a (date, ticker) indexed DataFrame."""
    def f(x, k):
        v = x.get(k)
        try:
            return float(v) if v is not None else np.nan
        except (TypeError, ValueError):
            return np.nan

    recs = {}
    for x in rows:
        t = _normalize(x.get("SECUCODE") or "")
        if not t or t in recs:
            continue
        recs[t] = {
            "name": x.get("SECURITY_NAME"),
            "hold_mktcap": f(x, "HOLD_MARKET_CAP"),
            "hold_shares": f(x, "HOLD_SHARES"),
            "own_pct": f(x, "HOLD_SHARES_RATIO"),
            "free_pct": f(x, "FREE_SHARES_RATIO"),
            "chg5_v": f(x, "HOLD_MARKETCAP_CHG5"),
            "chg10_v": f(x, "HOLD_MARKETCAP_CHG10"),
            "add_amp": f(x, "ADD_SHARES_AMP"),
            "close": f(x, "CLOSE_PRICE"),
        }
    if not recs:
        return None
    df = pd.DataFrame.from_dict(recs, orient="index")
    df.index.name = "ticker"
    df.insert(0, "date", pd.Timestamp(hold_date[:10]))
    df = df.reset_index().set_index(["date", "ticker"]).sort_index()
    return df


def backfill(dry_run: bool = False, max_dates: int | None = None) -> dict:
    """Page through the full 2-year rolling window and populate the holdings store.

    Returns a summary dict with keys: n_new, n_skipped, n_total, earliest, latest,
    store_bytes, gap_verdict.
    """
    existing = _load_existing_dates()
    log.info("Existing store: %d dates already captured", len(existing))

    new_frames: list[pd.DataFrame] = []
    n_new = 0
    n_skipped = 0
    page = 1
    last_fetch_time = 0.0

    # Probe page 1 to get total_count for progress logging
    time.sleep(max(0.0, _RATE_LIMIT_S - (time.monotonic() - last_fetch_time)))
    import requests
    flt = '(MUTUAL_TYPE in ("%s"))(INTERVAL_TYPE="1")' % '","'.join(_SB_TYPES)
    try:
        r = requests.get(_DC, params={
            "reportName": "RPT_MUTUAL_STOCK_HOLDRANKS", "columns": "ALL",
            "pageSize": _PAGE_SIZE, "pageNumber": 1, "sortColumns": "HOLD_DATE",
            "sortTypes": 1, "filter": flt,
        }, headers=_H, timeout=_TIMEOUT)
        result = r.json().get("result") or {}
        total_count = result.get("count") or 0
        total_pages = (total_count + _PAGE_SIZE - 1) // _PAGE_SIZE if total_count else 999
    except Exception as e:  # noqa: BLE001
        log.warning("Could not get total count: %s", e)
        total_count = 0
        total_pages = 999
    last_fetch_time = time.monotonic()

    log.info("Total API rows: %d -> ~%d pages", total_count, total_pages)

    current_date: str | None = None
    current_rows: list[dict] = []

    while True:
        # Rate limit
        elapsed = time.monotonic() - last_fetch_time
        if elapsed < _RATE_LIMIT_S:
            time.sleep(_RATE_LIMIT_S - elapsed)

        data = _fetch_page(page)
        last_fetch_time = time.monotonic()

        if not data:
            # Flush any buffered rows for the last date
            if current_rows and current_date:
                if current_date not in existing:
                    df = _rows_to_df(current_rows, current_date)
                    if df is not None:
                        new_frames.append(df)
                        n_new += 1
                        log.info("  collected %s — %d tickers (in-memory)", current_date, len(df))
                else:
                    n_skipped += 1
            break

        # Group rows by date (ascending API means each page is mostly one date,
        # but date boundaries can fall mid-page)
        for row in data:
            row_date = (row.get("HOLD_DATE") or "")[:10]
            if not row_date:
                continue

            if row_date != current_date:
                # Flush previous date
                if current_rows and current_date:
                    if current_date not in existing:
                        df = _rows_to_df(current_rows, current_date)
                        if df is not None:
                            new_frames.append(df)
                            n_new += 1
                            log.info("  collected %s — %d tickers (in-memory)",
                                     current_date, len(df))
                    else:
                        n_skipped += 1
                current_date = row_date
                current_rows = [row]
            else:
                current_rows.append(row)

        log.info("page %d/%d — %d new dates collected, pending=%s",
                 page, total_pages, n_new, current_date or "?")

        if max_dates is not None and n_new >= max_dates:
            log.info("max_dates=%d reached — stopping early", max_dates)
            break

        if not data or len(data) < _PAGE_SIZE:
            # Last page
            if current_rows and current_date and current_date not in existing:
                df = _rows_to_df(current_rows, current_date)
                if df is not None:
                    new_frames.append(df)
                    n_new += 1
                    log.info("  collected %s — %d tickers (in-memory)", current_date, len(df))
            break

        page += 1

    # Batch write: ONE parquet write for all new data
    store_bytes = 0
    if new_frames and not dry_run:
        log.info("Writing %d new date cross-sections to store...", len(new_frames))
        new_all = pd.concat(new_frames).sort_index()
        new_all = new_all[~new_all.index.duplicated(keep="first")]
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        if _STORE_PATH.exists():
            old = pd.read_parquet(_STORE_PATH)
            if isinstance(old.index, pd.MultiIndex):
                merged = new_all.combine_first(old)
            else:
                merged = new_all
            merged = merged[~merged.index.duplicated(keep="first")].sort_index()
            merged.to_parquet(_STORE_PATH)
        else:
            new_all.to_parquet(_STORE_PATH)
        store_bytes = _STORE_PATH.stat().st_size
        log.info("Store written: %.1f MB", store_bytes / 1e6)
    elif new_frames and dry_run:
        log.info("DRY RUN: would write %d new date cross-sections", len(new_frames))

    # Read final date list for audit
    all_dates = list(_load_existing_dates())
    if new_frames and not dry_run:
        _write_gap_audit(all_dates)

    return {
        "n_new": n_new,
        "n_skipped": n_skipped,
        "n_total": len(all_dates),
        "earliest": min(all_dates) if all_dates else None,
        "latest": max(all_dates) if all_dates else None,
        "store_bytes": store_bytes,
        "gap_verdict": json.loads(_AUDIT_PATH.read_text())["verdict"] if _AUDIT_PATH.exists() else "N/A",
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler()],
    )
    parser = argparse.ArgumentParser(description="Backfill HK Southbound Holdings 2y panel")
    parser.add_argument("--dry-run", action="store_true", help="No writes, just count")
    parser.add_argument("--max-dates", type=int, default=None,
                        help="Stop after collecting this many NEW dates (test mode)")
    args = parser.parse_args()

    result = backfill(dry_run=args.dry_run, max_dates=args.max_dates)

    print("\n=== BACKFILL SUMMARY ===")
    print(f"  New dates collected : {result['n_new']}")
    print(f"  Dates already present: {result['n_skipped']}")
    print(f"  Total dates in store: {result['n_total']}")
    print(f"  Earliest date       : {result['earliest']}")
    print(f"  Latest date         : {result['latest']}")
    print(f"  Store size          : {result['store_bytes'] / 1e6:.1f} MB")
    print(f"  Gap verdict         : {result['gap_verdict']}")
    print("========================\n")
