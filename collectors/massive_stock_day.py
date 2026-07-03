"""Massive.com whole-market daily OHLCV store — derived per-ticker parquets.

The massive.com flat-file entitlement includes us_stocks_sip/day_aggs_v1/ — a
ROLLING ~2025-→present window of whole-market daily bars.  Today fetch_aggs() in
massive_flatfiles.py fetches individual days but NEVER persists the stock_day
product into a durable store: the transient download cache (data/massive_flat/)
holds universe-filtered frames keyed by (date, underlyings_hash) and is gitignored.

This module builds and maintains a DERIVED per-ticker store:
  data/massive_stock_day/<TICKER>.parquet  — append-only, index=date (UTC midnight)
  data/massive_stock_day/_manifest.json   — freshness anchor (committed; rest gitignored)

The store is published to Cloudflare R2 under the key prefix `massive_stock_day/`
via scripts/publish_r2 --dirs massive_stock_day (publish_r2 falls back to data/<dir>
when site/<dir> is absent — see the data-dir fallback added in that module).  The
R2 _manifest.json is the audit_r2 freshness anchor.

URGENCY / BACKFILL DESIGN
--------------------------
Each month of delay permanently loses a month of whole-market history because the
entitlement is a ROLLING window (earliest days age out once the window moves forward).
The backfill loop therefore processes days in EARLIEST-FIRST order, stopping only on
S3 errors or an explicit date ceiling.

Each raw daily CSV (~12,000 rows, ~0.8 MB compressed) is:
1. Downloaded via fetch_aggs() (the existing S3 reader with day-level caching).
2. Pivoted to per-ticker rows and APPENDED (upsert by date) to each ticker's parquet.

Tickers without a parquet file yet get one created.  Re-runs are idempotent: a day
already in the parquet (index already contains that date) is skipped.

NIGHTLY INCREMENTAL
-------------------
For the nightly collect lane, run_incremental() fetches only the most-recent N
trading days not yet in the store (default: look back 5 days, write what's missing).
This is wired in scripts/collect.py under "massive_stock_day".

STORE CONTRACT
--------------
Schema per-ticker parquet:
  index: date (datetime64[ns], UTC midnight, named "date")
  columns: open, high, low, close (float64), volume (int64), transactions (int64)
  sorted ascending by date
  dedup: latest write wins on a date tie (idempotent)

Ordering: a ticker with no data (404 / 0-volume bar) on a given date simply has no
row for that date; gaps are legitimate (halted names, ETF launches).

GIT / R2 BOUNDARY
-----------------
data/massive_stock_day/*.parquet  → gitignored (multi-GB total)
data/massive_stock_day/_manifest.json → COMMITTED (freshness anchor for audit_r2)
data/massive_stock_day/_backfill_state.json → COMMITTED (resume state: last_date_captured)

The manifest is written by publish_massive_stock_day() after every successful batch.

CREDENTIALS
-----------
Uses MASSIVE_S3_* credentials (same as collectors/massive_flatfiles.py), NOT R2_*.
The store is hosted on R2 (R2_* creds for upload) but downloaded from Massive S3.
See scripts/publish_r2.py for the R2 upload path.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

from collectors.massive_flatfiles import fetch_aggs, latest_available, enabled
from lib import config

log = logging.getLogger(__name__)

# ── store paths ─────────────────────────────────────────────────────────────
def _store_dir() -> Path:
    p = config.data_dir() / "massive_stock_day"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ticker_path(ticker: str) -> Path:
    return _store_dir() / f"{ticker}.parquet"


def _manifest_path() -> Path:
    return _store_dir() / "_manifest.json"


def _backfill_state_path() -> Path:
    return _store_dir() / "_backfill_state.json"


# ── internal helpers ─────────────────────────────────────────────────────────
def _trading_days(start: date, end: date) -> Iterator[date]:
    """Yield calendar days from start→end inclusive; skips weekends only.
    Holidays produce empty frames from S3 (NoSuchKey) and are handled gracefully."""
    d = start
    while d <= end:
        if d.weekday() < 5:   # Mon–Fri
            yield d
        d += timedelta(days=1)


def _parse_day(df: pd.DataFrame, d: date) -> pd.DataFrame:
    """Convert one raw day-frame to the canonical schema with a date index."""
    if df.empty:
        return df
    out = df[["ticker", "open", "high", "low", "close", "volume", "transactions"]].copy()
    out["date"] = pd.Timestamp(d)
    out = out.set_index("date")
    out["volume"] = out["volume"].fillna(0).astype("int64")
    out["transactions"] = out["transactions"].fillna(0).astype("int64")
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _upsert_ticker(ticker: str, new_rows: pd.DataFrame) -> None:
    """Append new_rows (index=date) to the ticker's parquet; dedup on date."""
    if new_rows.empty:
        return
    path = _ticker_path(ticker)
    if path.exists():
        try:
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, new_rows])
        except Exception:   # noqa: BLE001 — corrupt parquet: overwrite
            combined = new_rows
    else:
        combined = new_rows
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined.to_parquet(path)


def _write_manifest(n_tickers: int, latest_date: date | None) -> None:
    """Write/update the git-committed freshness anchor."""
    manifest = {
        "store": "massive_stock_day",
        "n_tickers": n_tickers,
        "latest_date": latest_date.isoformat() if latest_date else None,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    _manifest_path().write_text(json.dumps(manifest, indent=2))
    log.info("massive_stock_day: manifest updated — %d tickers, latest %s",
             n_tickers, latest_date)


def _load_backfill_state() -> dict:
    p = _backfill_state_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:   # noqa: BLE001
            pass
    return {}


def _save_backfill_state(state: dict) -> None:
    _backfill_state_path().write_text(json.dumps(state, indent=2))


def _existing_ticker_dates() -> dict[str, set]:
    """Map ticker→set of dates already in store (read all parquets).  Expensive on a
    large store — only called from backfill; incremental skips it."""
    out: dict[str, set] = {}
    for p in _store_dir().glob("*.parquet"):
        t = p.stem
        try:
            df = pd.read_parquet(p, columns=[])   # index only
            out[t] = set(df.index.normalize())
        except Exception:   # noqa: BLE001
            out[t] = set()
    return out


def _store_max_date() -> date | None:
    """Cheapest way to find the most recent date across all tickers: scan manifests
    if present, else check a sample of parquets."""
    mf = _manifest_path()
    if mf.exists():
        try:
            d = json.loads(mf.read_text()).get("latest_date")
            if d:
                return date.fromisoformat(d)
        except Exception:   # noqa: BLE001
            pass
    # fall back: sample SPY (very likely to exist once any data is captured)
    spy_p = _ticker_path("SPY")
    if spy_p.exists():
        try:
            df = pd.read_parquet(spy_p, columns=[])
            return df.index.max().date()
        except Exception:   # noqa: BLE001
            pass
    return None


# ── public API ───────────────────────────────────────────────────────────────
def backfill(
    start: date | None = None,
    end: date | None = None,
    *,
    max_days: int | None = None,
    pace_s: float = 0.05,
) -> dict:
    """Download and persist the entire entitled window, EARLIEST-FIRST.

    Args:
        start: first date to capture (default: 2025-01-02 — earliest observed)
        end:   last date to capture (default: today or latest_available())
        max_days: stop after this many days (for smoke-tests / partial runs)
        pace_s: sleep between day fetches (S3 is self-throttled but be polite)

    Returns dict with keys: days_fetched, days_skipped, days_failed, tickers_written,
    earliest_date, latest_date.
    """
    if not enabled():
        log.warning("massive_stock_day backfill: MASSIVE_S3_* creds absent — skipping")
        return {"blocked": "no_creds"}

    start = start or date(2025, 1, 2)    # earliest observed available date
    if end is None:
        end = latest_available("stock_day", lookback=7) or date.today()

    log.info("massive_stock_day backfill: %s → %s (max_days=%s)", start, end, max_days)

    state = _load_backfill_state()
    # Resume from where we left off (if state records a last_captured day)
    resume_after = state.get("last_captured_date")
    if resume_after:
        resume_dt = date.fromisoformat(resume_after)
        if resume_dt >= start:
            log.info("massive_stock_day: resuming from %s (skipping earlier days)", resume_dt)
            start = resume_dt + timedelta(days=1)

    days_fetched = days_skipped = days_failed = 0
    tickers_written: set[str] = set()
    earliest_date_written: date | None = None
    latest_date_written: date | None = None

    for d in _trading_days(start, end):
        if max_days is not None and days_fetched >= max_days:
            log.info("massive_stock_day: max_days=%d reached, stopping", max_days)
            break
        try:
            # Use the per-day "all tickers" fetch (underlyings=None) from the transient
            # download cache.  The cache stores the raw CSV-derived frame, NOT the per-ticker
            # store — so this is fine: raw cache key = (product, date, 'all').
            raw = fetch_aggs(d, product="stock_day", underlyings=None, use_cache=True)
        except Exception as e:   # noqa: BLE001
            log.warning("massive_stock_day: fetch failed %s: %s", d, e)
            days_failed += 1
            continue

        if raw.empty:
            log.debug("massive_stock_day: empty frame for %s (weekend/holiday/missing)", d)
            days_skipped += 1
            # Save state even on skips so we don't re-probe missing days on resume
            state["last_captured_date"] = d.isoformat()
            _save_backfill_state(state)
            continue

        parsed = _parse_day(raw, d)
        # Group by ticker and upsert
        for ticker, grp in parsed.groupby("ticker"):
            rows = grp.drop(columns=["ticker"])
            _upsert_ticker(ticker, rows)
            tickers_written.add(ticker)

        if earliest_date_written is None:
            earliest_date_written = d
        latest_date_written = d
        days_fetched += 1
        state["last_captured_date"] = d.isoformat()

        if days_fetched % 20 == 0:
            _save_backfill_state(state)
            n_t = len(list(_store_dir().glob("*.parquet")))
            _write_manifest(n_t, latest_date_written)
            log.info("massive_stock_day: %d days done, %d tickers in store, latest=%s",
                     days_fetched, n_t, latest_date_written)
        if pace_s > 0:
            time.sleep(pace_s)

    _save_backfill_state(state)
    n_tickers = len(list(_store_dir().glob("*.parquet")))
    if latest_date_written:
        _write_manifest(n_tickers, latest_date_written)

    result = {
        "days_fetched": days_fetched,
        "days_skipped": days_skipped,
        "days_failed": days_failed,
        "tickers_written": len(tickers_written),
        "earliest_date": earliest_date_written.isoformat() if earliest_date_written else None,
        "latest_date": latest_date_written.isoformat() if latest_date_written else None,
        "store_tickers": n_tickers,
    }
    log.info("massive_stock_day backfill complete: %s", result)
    return result


def run_incremental(lookback_days: int = 5, pace_s: float = 0.05) -> dict:
    """Nightly incremental fetch: capture any trading days not yet in the store.

    Checks the store's latest date against the entitled window and fetches any
    missing trading days up to latest_available().  This is the function wired in
    the nightly collect lane via MassiveStockDayAdapter.
    """
    if not enabled():
        log.info("massive_stock_day incremental: MASSIVE_S3_* absent — skip")
        return {"blocked": "no_creds"}

    latest_ent = latest_available("stock_day", lookback=7)
    if latest_ent is None:
        log.warning("massive_stock_day: cannot determine latest entitled date")
        return {"blocked": "no_entitled_date"}

    current_max = _store_max_date()
    if current_max is None:
        # Store empty or brand-new: run a 5-day smoke capture to prime it, then
        # the scheduled backfill job (scripts/backfill_massive_stock_day.py) fills history.
        start = latest_ent - timedelta(days=lookback_days + 2)
        log.info("massive_stock_day: store empty, priming with last %d days", lookback_days)
    else:
        start = current_max + timedelta(days=1)

    if start > latest_ent:
        log.info("massive_stock_day: already up to date (store=%s, entitled=%s)",
                 current_max, latest_ent)
        return {"days_fetched": 0, "already_current": True}

    return backfill(start=start, end=latest_ent, pace_s=pace_s)


def load_ticker(ticker: str) -> pd.DataFrame:
    """Read the stored OHLCV history for one ticker.  Returns empty DataFrame if
    not yet captured."""
    path = _ticker_path(ticker)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:   # noqa: BLE001
        return pd.DataFrame()


# ── Adapter for scripts/collect.py ──────────────────────────────────────────
from collectors.base import Adapter   # noqa: E402


class MassiveStockDayAdapter(Adapter):
    """Nightly incremental refresh of data/massive_stock_day/ per-ticker parquets."""

    name = "massive_stock_day"
    group = "massive_stock_day"
    stale_after_days = 2     # flag stale if no update in 2 days (trading days only)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if full_history:
            result = backfill(start=date(2025, 1, 2))
        else:
            result = run_incremental(lookback_days=5)

        if result.get("blocked"):
            raise RuntimeError(f"massive_stock_day: {result['blocked']}")

        n = result.get("days_fetched", 0)
        store_t = result.get("store_tickers", 0)
        # Return a summary ingest frame for run_status.json
        summary = pd.DataFrame(
            {"days_fetched": [n], "store_tickers": [store_t]},
            index=[pd.Timestamp.utcnow().normalize()],
        )
        return {"massive_stock_day__ingest": summary}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = sys.argv[1:]
    if "--incremental" in args:
        r = run_incremental()
    elif "--smoke" in args:
        # 3-day smoke test: capture the most recent 3 trading days
        ent = latest_available("stock_day", lookback=7)
        if ent:
            sm_start = ent - timedelta(days=5)
            r = backfill(start=sm_start, end=ent, max_days=3)
        else:
            r = {"blocked": "no_entitled_date"}
    else:
        r = backfill(start=date(2025, 1, 2))
    print(json.dumps(r, indent=2))
