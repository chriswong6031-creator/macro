"""CCTV 新闻联播 daily transcript backfill — W1.2 of CHINA_INTEL_CYCLES_MASTERPLAN.

Iterates 2016-02-03 → today NEWEST-FIRST so recent (decision-relevant) history
lands first if the run is interrupted.  Stores one parquet per month under
data/cctv_daily/ (gitignored; R2 mirror via --dirs cctv_daily).

This script is MAC-LOCAL / MANUAL LANE ONLY.  It is NOT on the render path and
NEVER runs inside the nightly pipeline.  See RUL-3 and RUL-9.

Usage
-----
  # Full backfill, newest→oldest, resumable:
  python scripts/backfill_cctv_daily.py

  # Limit to N dates (smoke / partial run):
  python scripts/backfill_cctv_daily.py --max-days 6

  # Custom date window (inclusive, YYYY-MM-DD):
  python scripts/backfill_cctv_daily.py --start 2023-01-01 --end 2023-12-31

  # Audit gaps (how many dates missing per year):
  python scripts/backfill_cctv_daily.py --gap-audit

After completion, publish to R2:
  python scripts/publish_r2.py --dirs cctv_daily --no-manifest

Storage layout
--------------
  data/cctv_daily/YYYY-MM.parquet  — monthly shards (zstd)
  data/cctv_daily/backfill.log     — append-only progress log

Shard schema
------------
  date           : str  "YYYY-MM-DD"
  seq            : int  broadcast order (0 = 联播头条 / lead item)
  title          : str
  content        : str
  content_sha256 : str  hex digest of (title + content) — empty-day sentinel = ""
  _fetched_at    : str  ISO-8601 UTC

Empty-day vs failed-day distinction
-------------------------------------
Empty days (weekends, holidays, not-yet-published) are stored with seq=0, title="",
content="", content_sha256="" and a special sentinel marker in the title field:
"__EMPTY__".  Failed days (network error after retries) are stored similarly with
title="__ERROR__" and the exception message in content.  Both are skipped on
subsequent runs (already-present check includes them), but --repair re-fetches any
date whose only rows have title in ("__EMPTY__", "__ERROR__", "__STUB__").

SIGTERM handling
-----------------
The script installs a SIGTERM handler.  On receipt, it finishes the current date,
flushes the shard to disk, logs a SIGTERM-STOP line, and exits cleanly.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import random
import signal
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = REPO_ROOT / "data" / "cctv_daily"

HISTORY_START = date(2016, 2, 3)   # akshare docstring: reliable from this date

SENTINEL_EMPTY = "__EMPTY__"
SENTINEL_ERROR = "__ERROR__"
SENTINEL_STUB  = "__STUB__"

STUB_SIGNATURES = (
    "对不起",
    "可能是网络原因",
    "无此页面",
    "404",
    "页面不存在",
)

_SIGTERM_RECEIVED = False

log = logging.getLogger("backfill_cctv_daily")


# ---------------------------------------------------------------------------
# SIGTERM handler
# ---------------------------------------------------------------------------

def _install_sigterm_handler() -> None:
    def _handler(signum, frame):  # noqa: ANN001
        global _SIGTERM_RECEIVED
        _SIGTERM_RECEIVED = True
        log.warning("SIGTERM received — will finish current date then exit cleanly")
    signal.signal(signal.SIGTERM, _handler)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_stub(title: str, content: str) -> bool:
    combined = title + content
    return any(sig in combined for sig in STUB_SIGNATURES)


def _shard_path(store: Path, dt: date) -> Path:
    return store / f"{dt.strftime('%Y-%m')}.parquet"


def _load_shard(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=["date", "seq", "title", "content",
                                  "content_sha256", "_fetched_at"])


def _save_shard(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="zstd", index=False)


def _already_present(store: Path, dt: date) -> bool:
    """True if this date has ANY rows in its shard (including sentinel rows)."""
    shard_p = _shard_path(store, dt)
    if not shard_p.exists():
        return False
    df = _load_shard(shard_p)
    return dt.strftime("%Y-%m-%d") in df["date"].values


def _is_retriable(store: Path, dt: date) -> bool:
    """True if the date is present but all rows are sentinel/error/stub (retriable)."""
    shard_p = _shard_path(store, dt)
    if not shard_p.exists():
        return False
    df = _load_shard(shard_p)
    ds = dt.strftime("%Y-%m-%d")
    day_rows = df[df["date"] == ds]
    if day_rows.empty:
        return False
    sentinels = {SENTINEL_EMPTY, SENTINEL_ERROR, SENTINEL_STUB}
    return day_rows["title"].isin(sentinels).all()


def _upsert_day(store: Path, dt: date, rows: list[dict]) -> None:
    """Remove any existing rows for dt then append the new ones."""
    shard_p = _shard_path(store, dt)
    existing = _load_shard(shard_p)
    ds = dt.strftime("%Y-%m-%d")
    existing = existing[existing["date"] != ds]
    new_df = pd.DataFrame(rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.sort_values(["date", "seq"]).reset_index(drop=True)
    _save_shard(combined, shard_p)


def _log_line(store: Path, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}  {msg}"
    print(line, flush=True)
    log_path = store / "backfill.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _sentinel_row(dt: date, kind: str, detail: str = "") -> dict:
    """Build a sentinel row for empty/error/stub days."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "date": dt.strftime("%Y-%m-%d"),
        "seq": 0,
        "title": kind,
        "content": detail,
        "content_sha256": "",
        "_fetched_at": fetched_at,
    }


# ---------------------------------------------------------------------------
# Core fetch (akshare)
# ---------------------------------------------------------------------------

def fetch_day(dt: date, retries: int = 3) -> tuple[list[dict], str]:
    """Fetch one day from akshare.

    Returns (rows, status) where status in {"ok", "empty", "stub", "error"}.
    On "empty": rows = [] (caller supplies the sentinel row).
    On "error": rows = [one sentinel error row].
    On "stub": rows = [all items, each with title=SENTINEL_STUB].
    On "ok": rows = real items.
    """
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError(f"akshare unavailable: {exc}") from exc

    ds = dt.strftime("%Y%m%d")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    last_exc: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            raw = ak.news_cctv(date=ds)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                wait = 2 ** attempt + random.uniform(0, 1)
                log.debug("  retry %d/%d for %s after %.1fs (%s)", attempt, retries, ds, wait, exc)
                time.sleep(wait)
    else:
        return [_sentinel_row(dt, SENTINEL_ERROR, str(last_exc))], "error"

    if raw is None or len(raw) == 0:
        return [], "empty"

    rows: list[dict] = []
    all_stub = True
    for idx, row in enumerate(raw.itertuples(index=False)):
        title = str(getattr(row, "title", "") or "")
        content = str(getattr(row, "content", "") or "")
        is_stub = _is_stub(title, content)
        if not is_stub:
            all_stub = False
        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "seq": idx,
            "title": SENTINEL_STUB if is_stub else title,
            "content": content,
            "content_sha256": _sha256(title + content) if not is_stub else "",
            "_fetched_at": fetched_at,
        })

    if all_stub and rows:
        return rows, "stub"
    return rows, "ok"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _date_range(start: Optional[date], end: Optional[date]) -> list[date]:
    """All dates from start to end (inclusive), NEWEST FIRST."""
    s = start or HISTORY_START
    e = end or date.today()
    out: list[date] = []
    cur = e
    while cur >= s:
        out.append(cur)
        cur -= timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Main backfill loop
# ---------------------------------------------------------------------------

def run_backfill(
    store: Path,
    repair: bool = False,
    start: Optional[date] = None,
    end: Optional[date] = None,
    max_days: Optional[int] = None,
    pace_min: float = 2.0,
    pace_max: float = 4.0,
) -> None:
    _install_sigterm_handler()
    all_dates = _date_range(start, end)
    total = len(all_dates)

    _log_line(
        store,
        f"BACKFILL START: window={all_dates[-1]}→{all_dates[0]}  "
        f"dates={total}  repair={repair}  max_days={max_days}",
    )

    done = skipped = errors = stubs = empties = 0
    t0 = time.time()

    for i, dt in enumerate(all_dates):
        if _SIGTERM_RECEIVED:
            _log_line(store, f"SIGTERM-STOP after {done} done, {skipped} skipped")
            break

        if max_days is not None and done >= max_days:
            _log_line(store, f"MAX-DAYS-STOP: reached {max_days} fetched dates")
            break

        # Skip already-present dates unless repair mode and they are retriable
        if _already_present(store, dt):
            if repair and _is_retriable(store, dt):
                pass  # fall through to re-fetch
            else:
                skipped += 1
                continue

        rows, status = fetch_day(dt)

        if status == "empty":
            rows = [_sentinel_row(dt, SENTINEL_EMPTY)]
            empties += 1
        elif status == "error":
            errors += 1
        elif status == "stub":
            stubs += 1

        _upsert_day(store, dt, rows)
        done += 1

        # Checkpoint log every 20 days fetched (not skipped)
        if done % 20 == 0 or done <= 3:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            remaining_dates = total - i - 1
            eta_str = (
                str(timedelta(seconds=int(remaining_dates / rate)))
                if rate > 0 else "?"
            )
            _log_line(
                store,
                f"  [{i+1}/{total}] date={dt}  done={done} skip={skipped} "
                f"err={errors} stub={stubs} empty={empties}  "
                f"rate={rate:.2f}d/s  ETA={eta_str}",
            )

        # Politeness sleep
        if i < len(all_dates) - 1 and not _SIGTERM_RECEIVED:
            time.sleep(random.uniform(pace_min, pace_max))

    elapsed = time.time() - t0
    _log_line(
        store,
        f"BACKFILL END: done={done} skipped={skipped} errors={errors} "
        f"stubs={stubs} empties={empties}  elapsed={timedelta(seconds=int(elapsed))}",
    )


# ---------------------------------------------------------------------------
# Gap audit
# ---------------------------------------------------------------------------

def run_gap_audit(store: Path) -> None:
    """Print per-year coverage stats to stdout."""
    from collections import defaultdict
    all_dates = _date_range(None, None)
    stats: dict[int, dict] = defaultdict(
        lambda: {"total": 0, "missing": 0, "ok": 0, "empty": 0, "stub": 0, "error": 0}
    )
    for dt in all_dates:
        yr = dt.year
        stats[yr]["total"] += 1
        ds = dt.strftime("%Y-%m-%d")
        shard_p = _shard_path(store, dt)
        if not shard_p.exists():
            stats[yr]["missing"] += 1
            continue
        df = _load_shard(shard_p)
        day_rows = df[df["date"] == ds]
        if day_rows.empty:
            stats[yr]["missing"] += 1
            continue
        if (day_rows["title"] == SENTINEL_EMPTY).all():
            stats[yr]["empty"] += 1
        elif (day_rows["title"].isin({SENTINEL_ERROR, SENTINEL_STUB})).all():
            stats[yr]["error"] += 1
        else:
            stats[yr]["ok"] += 1

    print("\n=== CCTV Daily Gap Audit ===")
    print(f"{'Year':<6} {'Total':<8} {'Missing':<9} {'OK':<8} {'Empty':<8} {'Err+Stub':<8}")
    for yr in sorted(stats.keys()):
        s = stats[yr]
        err_stub = s["error"] + s["stub"]
        print(f"{yr:<6} {s['total']:<8} {s['missing']:<9} {s['ok']:<8} {s['empty']:<8} {err_stub:<8}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logging.basicConfig(level=level, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CCTV 新闻联播 daily backfill (W1.2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--store", default=str(DEFAULT_STORE),
                        help=f"Store directory (default: {DEFAULT_STORE})")
    parser.add_argument("--start", default=None,
                        help="Start date YYYY-MM-DD (default: 2016-02-03)")
    parser.add_argument("--end", default=None,
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--max-days", type=int, default=None,
                        help="Stop after N dates fetched (not skipped)")
    parser.add_argument("--repair", action="store_true",
                        help="Re-fetch dates whose rows are all sentinels/errors/stubs")
    parser.add_argument("--gap-audit", action="store_true",
                        help="Print per-year coverage stats and exit")
    parser.add_argument("--pace-min", type=float, default=2.0,
                        help="Min sleep between dates in seconds (default: 2.0)")
    parser.add_argument("--pace-max", type=float, default=4.0,
                        help="Max sleep between dates in seconds (default: 4.0)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    store = Path(args.store).expanduser().resolve()
    store.mkdir(parents=True, exist_ok=True)

    start_dt = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    end_dt = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else None

    if args.gap_audit:
        run_gap_audit(store)
        return

    run_backfill(
        store=store,
        repair=args.repair,
        start=start_dt,
        end=end_dt,
        max_days=args.max_days,
        pace_min=args.pace_min,
        pace_max=args.pace_max,
    )


if __name__ == "__main__":
    main()
