"""Massive.com whole-market daily OHLCV store — derived per-ticker parquets.

The massive.com flat-file entitlement includes us_stocks_sip/day_aggs_v1/ — a
ROLLING ~5-year→present window of whole-market daily bars (probe-verified
2026-07-03: earliest available day 2021-07-06 = first trading day on/after
today−5y; days before the floor 403).  Today fetch_aggs() in massive_flatfiles.py
fetches individual days but NEVER persists the stock_day product into a durable
store: the transient download cache (data/massive_flat/) holds universe-filtered
frames keyed by (date, underlyings_hash) and is gitignored.

This module builds and maintains a DERIVED per-ticker store:
  data/massive_stock_day/<TICKER>.parquet  — append-only, index=date (UTC midnight)
  data/massive_stock_day/_manifest.json   — freshness anchor (committed; rest gitignored)

The store is published to Cloudflare R2 under the key prefix `massive_stock_day/`
via scripts/publish_r2 --dirs massive_stock_day (publish_r2 falls back to data/<dir>
when site/<dir> is absent — see the data-dir fallback added in that module).  The
R2 _manifest.json is the audit_r2 freshness anchor.  NOTE: publishing requires the
FULL store on local disk (publish_r2 refuses data-dir trees with under ~100 files),
so it can only run on the store host (the Mac main checkout) — a CI runner checkout
holds just the two committed JSON files and must never sync this dir.

URGENCY / BACKFILL DESIGN
--------------------------
Each month of delay permanently loses a month of whole-market history because the
entitlement is a ROLLING window (earliest days age out once the window moves forward).
The backfill loop therefore processes days in EARLIEST-FIRST order, stopping only on
S3 errors or an explicit date ceiling.

Each raw daily CSV (~12,000 rows, ~0.8 MB compressed) is:
1. Downloaded via fetch_aggs() (the existing S3 reader).
2. Pivoted to per-ticker rows and APPENDED (upsert by date) to each ticker's parquet.

Tickers without a parquet file yet get one created.  Re-runs are idempotent: a day
already recorded as processed is skipped.

RESUME STATE — data/massive_stock_day/_backfill_state.json (COMMITTED)
----------------------------------------------------------------------
v2 schema: {"version": 2, "processed_days": [ISO date, ...], "last_captured_date": ISO}

`processed_days` is the AUTHORITATIVE per-day coverage record: every weekday that was
either fetched-and-written or confirmed empty upstream (holiday) is listed.  Resume /
incremental target selection is the SET DIFFERENCE trading_days(window) − processed —
never a scalar high-water mark.

WHY: the v1 state was a single `last_captured_date`, monotonically clobbered by ANY
capture.  On 2026-07-03 the W0.6 smoke test (3 most-recent days) left the committed
state at 2026-06-30 while only 2025-01-02→(mid-backfill) existed on disk — a resumed
backfill would have restarted at 2026-07-01 and PERMANENTLY skipped
2026-03-13→2026-06-30, with the manifest still claiming freshness (this is exactly
the 110-day "coverage gap" the Options-Alpha W1.1 agent tripped over).  A v1 state
file is therefore treated as untrustworthy and migrated by scanning the actual
parquets (union of dates) once.

A day whose fetch ERRORS (S3 exception / entitlement 403) is NOT recorded — it is
retried on the next run.  Days that age out below the rolling floor keep 403ing and
keep being skipped; they never enter processed_days and sit below min(processed), so
the incremental window never widens onto them.

NIGHTLY INCREMENTAL
-------------------
run_incremental() computes the missing trading days over the FULL window
[min(processed_days) … latest_available()] — so an interior hole (a failed day, a
killed run) SELF-HEALS on the next nightly pass instead of hiding behind the tip.
Capped at `max_days` per run (default 40) so a large discovered hole chips away
across nights without blowing the collect lane's time budget; the remainder is
logged loudly and the audit (scripts/audit_massive_store.py) trips on the hole.

STORE CONTRACT
--------------
Schema per-ticker parquet:
  index: date (datetime64[ns], UTC midnight, named "date")
  columns: open, high, low, close (float64), volume (int64), transactions (int64)
  sorted ascending by date
  dedup: latest write wins on a date tie (idempotent)

Ordering: a ticker with no data (404 / 0-volume bar) on a given date simply has no
row for that date; per-TICKER gaps are legitimate (halted names, ETF launches).
Whole-STORE day gaps are NOT legitimate — that is what processed_days + the
massive_store audit guard.

GIT / R2 BOUNDARY
-----------------
data/massive_stock_day/*.parquet  → gitignored (multi-GB total)
data/massive_stock_day/_manifest.json → COMMITTED (freshness anchor for audit_r2)
data/massive_stock_day/_backfill_state.json → COMMITTED (resume state, v2)

The manifest is written by _write_manifest() after every successful batch and now
carries `coverage` (derived from processed_days) plus an independent `anchor` block
read straight from the SPY parquet — so a manifest whose claims diverge from the
actual store is detectable (scripts/audit_massive_store.py checks exactly that).

CREDENTIALS
-----------
Uses MASSIVE_S3_* credentials (same as collectors/massive_flatfiles.py), NOT R2_*.
The store is hosted on R2 (R2_* creds for upload) but downloaded from Massive S3.
See scripts/publish_r2.py for the R2 upload path.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

from collectors.massive_flatfiles import fetch_aggs, latest_available, enabled
from lib import config

log = logging.getLogger(__name__)

# Earliest day of the rolling entitlement window at the time of the last probe
# (2026-07-03: binary-searched floor = 2021-07-06 ≈ today−5y, first trading day
# after the observed July-4th holiday).  The floor ROLLS forward — days below it
# 403 and are harmlessly skipped (never recorded as processed).
EARLIEST_ENTITLED = date(2021, 7, 6)

# The anchor ticker used for manifest self-verification: maximally liquid, trades
# every US session, guaranteed present in any healthy capture.
_ANCHOR_TICKER = "SPY"

STATE_VERSION = 2


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
    Holidays produce empty frames from S3 (NoSuchKey), are recorded as processed
    once confirmed empty, and so are only ever probed once."""
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


def _max_missing_run(processed: set[date]) -> tuple[int, list[str]]:
    """Longest run of consecutive missing WEEKDAYS inside [min, max] of processed,
    plus a sample of the missing days (≤10).  (0, []) when nothing is missing."""
    if len(processed) < 2:
        return 0, []
    missing = [d for d in _trading_days(min(processed), max(processed))
               if d not in processed]
    if not missing:
        return 0, []
    longest = run = 1
    for prev, cur in zip(missing, missing[1:]):
        # consecutive on the weekday calendar = no processed weekday between them
        adjacent = not any(True for _ in _trading_days(prev + timedelta(days=1),
                                                       cur - timedelta(days=1)))
        run = run + 1 if adjacent else 1
        longest = max(longest, run)
    return longest, [d.isoformat() for d in missing[:10]]


def _anchor_summary() -> dict | None:
    """Coverage of the anchor ticker read STRAIGHT FROM ITS PARQUET — independent of
    processed_days, so a state/manifest that drifts from the actual store is visible."""
    p = _ticker_path(_ANCHOR_TICKER)
    if not p.exists():
        return None
    try:
        idx = pd.to_datetime(pd.read_parquet(p, columns=[]).index).sort_values()
    except Exception:   # noqa: BLE001
        return None
    if len(idx) == 0:
        return None
    max_gap = int((idx[1:] - idx[:-1]).days.max()) if len(idx) > 1 else 0
    return {"ticker": _ANCHOR_TICKER,
            "first": idx[0].date().isoformat(),
            "last": idx[-1].date().isoformat(),
            "n_rows": int(len(idx)),
            "max_gap_calendar_days": max_gap}


def _write_manifest(n_tickers: int, latest_date: date | None,
                    processed: set[date] | None = None) -> None:
    """Write/update the git-committed freshness anchor.  Besides the legacy top-level
    keys, embeds `coverage` (from processed_days) and `anchor` (from the SPY parquet)
    so freshness claims are verifiable — see scripts/audit_massive_store.py."""
    manifest = {
        "store": "massive_stock_day",
        "n_tickers": n_tickers,
        "latest_date": latest_date.isoformat() if latest_date else None,
        "updated_at": pd.Timestamp.now("UTC").isoformat(),
    }
    if processed:
        max_run, missing_sample = _max_missing_run(processed)
        manifest["coverage"] = {
            "first_day": min(processed).isoformat(),
            "last_day": max(processed).isoformat(),
            "n_processed_days": len(processed),
            "max_missing_run_weekdays": max_run,
            "missing_sample": missing_sample,
        }
    anchor = _anchor_summary()
    if anchor:
        manifest["anchor"] = anchor
    _manifest_path().write_text(json.dumps(manifest, indent=2))
    log.info("massive_stock_day: manifest updated — %d tickers, latest %s",
             n_tickers, latest_date)


def _scan_store_days() -> set[date]:
    """Union of dates present across ALL parquets (index-only reads).  Expensive on a
    large store (~2-3 min at 15k files) — used ONCE to migrate a v1 state file whose
    scalar high-water mark cannot be trusted as a coverage record."""
    days: set[date] = set()
    for p in _store_dir().glob("*.parquet"):
        try:
            idx = pd.read_parquet(p, columns=[]).index
            days.update(d.date() for d in pd.to_datetime(idx).normalize())
        except Exception:   # noqa: BLE001 — unreadable member: contributes nothing
            continue
    return days


def _load_backfill_state() -> dict:
    p = _backfill_state_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:   # noqa: BLE001
            pass
    return {}


def _save_backfill_state(processed: set[date]) -> None:
    state = {
        "version": STATE_VERSION,
        "last_captured_date": max(processed).isoformat() if processed else None,
        "processed_days": sorted(d.isoformat() for d in processed),
    }
    _backfill_state_path().write_text(json.dumps(state, indent=2))


def _processed_days(state: dict | None = None) -> set[date]:
    """The authoritative set of already-processed days.  Migrates a legacy v1 state
    (scalar `last_captured_date` — the field that hid the 2026-07-03 hole) by scanning
    the actual parquets; the migrated set is persisted so the scan runs once."""
    state = _load_backfill_state() if state is None else state
    if "processed_days" in state:
        out: set[date] = set()
        for s in state["processed_days"]:
            try:
                out.add(date.fromisoformat(s))
            except ValueError:
                continue
        return out
    if state.get("last_captured_date"):
        log.warning(
            "massive_stock_day: legacy v1 resume state found (last_captured_date=%s) — "
            "rebuilding processed_days from the actual parquets (one-time scan)",
            state["last_captured_date"])
        days = _scan_store_days()
        _save_backfill_state(days)
        log.info("massive_stock_day: state migrated to v2 — %d processed days%s",
                 len(days),
                 f" ({min(days)} → {max(days)})" if days else "")
        return days
    return set()


# ── public API ───────────────────────────────────────────────────────────────
def backfill(
    start: date | None = None,
    end: date | None = None,
    *,
    max_days: int | None = None,
    pace_s: float = 0.05,
) -> dict:
    """Download and persist the entitled window, EARLIEST-FIRST, fetching ONLY the
    trading days not already in processed_days (gap-aware: interior holes are
    targeted the same as the leading edge).

    Args:
        start: first date to consider (default: EARLIEST_ENTITLED)
        end:   last date to consider (default: latest_available())
        max_days: stop after this many FETCHED days (smoke-tests / partial runs)
        pace_s: sleep between day fetches (S3 is self-throttled but be polite)

    Returns dict with keys: days_fetched, days_skipped, days_failed, days_remaining,
    tickers_written, earliest_date, latest_date, store_tickers.
    """
    if not enabled():
        log.warning("massive_stock_day backfill: MASSIVE_S3_* creds absent — skipping")
        return {"blocked": "no_creds"}

    start = start or EARLIEST_ENTITLED
    if end is None:
        end = latest_available("stock_day", lookback=7) or date.today()

    processed = _processed_days()
    targets = [d for d in _trading_days(start, end) if d not in processed]
    log.info("massive_stock_day backfill: %s → %s — %d missing day(s) to fetch "
             "(max_days=%s, %d already processed)",
             start, end, len(targets), max_days, len(processed))

    days_fetched = days_skipped = days_failed = 0
    tickers_written: set[str] = set()
    earliest_date_written: date | None = None
    latest_date_written: date | None = None
    dirty = 0   # state/manifest checkpoint counter (counts all processed, not just fetched)

    for i, d in enumerate(targets):
        if max_days is not None and days_fetched >= max_days:
            log.info("massive_stock_day: max_days=%d reached, stopping (%d targets left)",
                     max_days, len(targets) - i)
            break
        try:
            raw = fetch_aggs(d, product="stock_day", underlyings=None, use_cache=True)
        except Exception as e:   # noqa: BLE001
            # NOT recorded as processed — retried on the next run.
            log.warning("massive_stock_day: fetch failed %s: %s", d, e)
            days_failed += 1
            continue

        if raw.empty:
            # Holiday / below the rolling floor: confirmed empty upstream.  Recorded
            # as processed so it is never re-probed.
            log.debug("massive_stock_day: empty frame for %s (holiday/missing)", d)
            days_skipped += 1
            processed.add(d)
            dirty += 1
        else:
            parsed = _parse_day(raw, d)
            for ticker, grp in parsed.groupby("ticker"):
                _upsert_ticker(ticker, grp.drop(columns=["ticker"]))
                tickers_written.add(ticker)
            if earliest_date_written is None:
                earliest_date_written = d
            latest_date_written = d
            days_fetched += 1
            processed.add(d)
            dirty += 1

        if dirty >= 20:
            _save_backfill_state(processed)
            n_t = len(list(_store_dir().glob("*.parquet")))
            _write_manifest(n_t, max(processed), processed)
            log.info("massive_stock_day: %d fetched / %d skipped, %d tickers in store, "
                     "latest=%s", days_fetched, days_skipped, n_t, latest_date_written)
            dirty = 0
        if pace_s > 0:
            time.sleep(pace_s)

    # Still-missing days in the requested window: failed fetches AND targets never
    # attempted (max_days cut).  Both retry on the next run.
    days_remaining = sum(1 for d in targets if d not in processed)
    _save_backfill_state(processed)
    n_tickers = len(list(_store_dir().glob("*.parquet")))
    if processed:
        _write_manifest(n_tickers, max(processed), processed)

    result = {
        "days_fetched": days_fetched,
        "days_skipped": days_skipped,
        "days_failed": days_failed,
        "days_remaining": days_remaining,
        "tickers_written": len(tickers_written),
        "earliest_date": earliest_date_written.isoformat() if earliest_date_written else None,
        "latest_date": latest_date_written.isoformat() if latest_date_written else None,
        "store_tickers": n_tickers,
    }
    log.info("massive_stock_day backfill complete: %s", result)
    return result


def run_incremental(lookback_days: int = 5, pace_s: float = 0.05,
                    max_days: int | None = 40) -> dict:
    """Nightly incremental fetch: capture every trading day not yet processed over the
    FULL window [min(processed) … latest_available()] — the leading edge AND any
    interior hole (self-healing).  Wired in the nightly collect lane via
    MassiveStockDayAdapter.

    `max_days` caps the per-run work so a large discovered hole chips away across
    nights instead of blowing the collect lane's time budget; the remainder is logged
    loudly and scripts/audit_massive_store.py trips on the hole until it closes.
    """
    if not enabled():
        log.info("massive_stock_day incremental: MASSIVE_S3_* absent — skip")
        return {"blocked": "no_creds"}

    latest_ent = latest_available("stock_day", lookback=7)
    if latest_ent is None:
        log.warning("massive_stock_day: cannot determine latest entitled date")
        return {"blocked": "no_entitled_date"}

    processed = _processed_days()
    if processed:
        start = min(processed)     # gap-aware: backfill() targets only missing days
    else:
        # Store empty or brand-new: prime with the last few days; the scheduled
        # backfill job (scripts/backfill_massive_stock_day.py) fills history.
        start = latest_ent - timedelta(days=lookback_days + 2)
        log.info("massive_stock_day: store empty, priming with last %d days", lookback_days)

    if not any(d not in processed for d in _trading_days(start, latest_ent)):
        log.info("massive_stock_day: already up to date (%d processed, entitled=%s)",
                 len(processed), latest_ent)
        return {"days_fetched": 0, "already_current": True}

    result = backfill(start=start, end=latest_ent, max_days=max_days, pace_s=pace_s)
    if result.get("days_remaining"):
        log.warning(
            "massive_stock_day: %d missing day(s) REMAIN after this capped run "
            "(max_days=%s) — will continue next run; the massive_store audit stays "
            "red until the hole closes", result["days_remaining"], max_days)
    return result


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
            result = backfill(start=EARLIEST_ENTITLED)
        else:
            result = run_incremental()

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
        # 3-day smoke test: capture the most recent 3 trading days.  Safe under the
        # v2 state: smoke days land in processed_days like any others; a later full
        # backfill still targets everything else (no high-water-mark poisoning).
        ent = latest_available("stock_day", lookback=7)
        if ent:
            sm_start = ent - timedelta(days=5)
            r = backfill(start=sm_start, end=ent, max_days=3)
        else:
            r = {"blocked": "no_entitled_date"}
    elif "--rebuild-state" in args:
        # Force a truth rebuild of processed_days from the actual parquets (recovery
        # tool: use when the state file is suspected to diverge from the store).
        days = _scan_store_days()
        _save_backfill_state(days)
        r = {"rebuilt": True, "n_processed_days": len(days),
             "first": min(days).isoformat() if days else None,
             "last": max(days).isoformat() if days else None}
    else:
        r = backfill(start=EARLIEST_ENTITLED)
    print(json.dumps(r, indent=2))
