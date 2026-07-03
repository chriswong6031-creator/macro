"""Backfill the 龙虎榜 (Dragon-Tiger Board) historical event tape.

akshare's ``stock_lhb_detail_em(start_date, end_date)`` serves a ranged
history going back to ~2024-07, covering ~21k events per the repo inventory.
This script fetches that range in 30-day chunks and appends to the
append-only historical store.

Output store
------------
data/china_lhb/history.parquet — append-only, dedup-keyed on (date, ticker, reason).
  Schema:
    date       str   YYYY-MM-DD  the 上榜日 (board-appearance date)
    ticker     str   e.g. 600000.SS / 000001.SZ
    name       str   stock short name (Chinese)
    net_buy_yi float 龙虎榜净买额 ÷ 1e8 (亿; positive = net buy)
    reason     str   上榜原因 (board-trigger reason string)

This is the raw per-appearance tape (one row per name×date×reason); the
rolling aggregate (collectors/china_lhb.py EVENTS / detail) stays separate.
Consumers that need the inst-seat split should read collectors.china_lhb.EVENTS
(the rolling collect is already running that path; this backfill builds the full
historical depth for that same store under a ``history.parquet`` alias).

NOTE: The script calls collectors.china_lhb.backfill() which writes to
data/china_lhb/events.parquet (the canonical raw-event tape).  We then copy
the result to history.parquet as a permanent historical alias so downstream
phase-0 harnesses can read from a stable path name (``history.parquet``) that
will not be overwritten by rolling collect refreshes.

Network / GFW caveat
--------------------
The akshare call hits Eastmoney servers.  A hard 10-minute timeout is applied
(--timeout-s flag; default 600).  If the connection is blocked by GFW or rate-
limited the script exits cleanly and reports the failure — the script itself is
the deliverable; the run is best-effort.

Usage
-----
  python3 scripts/backfill_china_lhb.py
  python3 scripts/backfill_china_lhb.py --start 2024-07-01 --end 2026-07-01
  python3 scripts/backfill_china_lhb.py --dry-run
  python3 scripts/backfill_china_lhb.py --timeout-s 300
"""
from __future__ import annotations

import argparse
import logging
import shutil
import signal
import sys
import time
from pathlib import Path

import pandas as pd

# repo root so this runs from any cwd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

_DATA_DIR = ROOT / "data" / "china_lhb"
# Canonical raw-event tape written by the daily collect (collectors.china_lhb.backfill)
_EVENTS_PATH = _DATA_DIR / "events.parquet"
# Stable historical alias for phase-0 harnesses
_HISTORY_PATH = _DATA_DIR / "history.parquet"

# Size threshold above which the file is documented as R2-plane rather than in-tree
_R2_SIZE_MB = 20.0

# Default date range: the confirmed available range from the repo inventory
_DEFAULT_START = "2024-07-01"
_DEFAULT_END = "2026-07-01"


def _load_existing_dates(path: Path) -> set[str]:
    """Return YYYY-MM-DD strings already stored in the parquet at ``path``."""
    if not path.exists():
        return set()
    try:
        df = pd.read_parquet(path, columns=["date"])
        return set(df["date"].dropna().astype(str).unique())
    except Exception as e:  # noqa: BLE001
        log.warning("could not read existing store %s: %s", path, e)
        return set()


def _sync_history(events_path: Path, history_path: Path) -> int:
    """Copy events.parquet -> history.parquet (atomic via temp file) and return row count."""
    if not events_path.exists():
        return 0
    history_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = history_path.with_suffix(".tmp.parquet")
    shutil.copy2(events_path, tmp)
    tmp.rename(history_path)
    try:
        return len(pd.read_parquet(history_path))
    except Exception:  # noqa: BLE001
        return 0


def _size_mb(path: Path) -> float:
    return path.stat().st_size / 1e6 if path.exists() else 0.0


def run(
    start: str = _DEFAULT_START,
    end: str = _DEFAULT_END,
    dry_run: bool = False,
    timeout_s: int = 600,
) -> dict:
    """Backfill the 龙虎榜 historical tape.

    Returns a summary dict:
      ok: bool
      events_appended: int
      total_events: int
      date_range: [earliest, latest] or [None, None]
      store_mb: float
      r2_needed: bool
      error: str | None
    """
    from collectors.china_lhb import backfill as lhb_backfill

    result: dict = {
        "ok": False,
        "events_appended": 0,
        "total_events": 0,
        "date_range": [None, None],
        "store_mb": 0.0,
        "r2_needed": False,
        "error": None,
    }

    if dry_run:
        existing = _load_existing_dates(_EVENTS_PATH)
        log.info("DRY-RUN: events.parquet has %d dates; would backfill %s..%s",
                 len(existing), start, end)
        result["ok"] = True
        return result

    # Set a hard timeout using SIGALRM (POSIX only) or a threading fallback
    timed_out = False

    def _timeout_handler(signum, frame):
        nonlocal timed_out
        timed_out = True
        raise TimeoutError(f"backfill timed out after {timeout_s}s")

    have_sigalrm = hasattr(signal, "SIGALRM")
    if have_sigalrm:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout_s)

    t0 = time.monotonic()
    try:
        log.info("starting LHB backfill %s..%s (timeout %ds)", start, end, timeout_s)
        n_events = lhb_backfill(start, end)
        elapsed = time.monotonic() - t0
        log.info("backfill completed in %.1fs: %d events written to %s",
                 elapsed, n_events, _EVENTS_PATH)
        result["events_appended"] = n_events
    except TimeoutError as e:
        result["error"] = str(e)
        log.error("LHB backfill TIMED OUT: %s", e)
        if have_sigalrm:
            signal.alarm(0)
        # Partial data is still useful — fall through to sync
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
        log.error("LHB backfill FAILED: %s", e)
        if have_sigalrm:
            signal.alarm(0)
        return result
    finally:
        if have_sigalrm:
            signal.alarm(0)

    # Sync events.parquet -> history.parquet
    try:
        total = _sync_history(_EVENTS_PATH, _HISTORY_PATH)
        result["total_events"] = total
        result["store_mb"] = _size_mb(_HISTORY_PATH)
        result["r2_needed"] = result["store_mb"] >= _R2_SIZE_MB
        # Date range
        if _HISTORY_PATH.exists():
            try:
                df = pd.read_parquet(_HISTORY_PATH, columns=["date"])
                dates = df["date"].dropna().astype(str)
                if not dates.empty:
                    result["date_range"] = [dates.min(), dates.max()]
            except Exception:  # noqa: BLE001
                pass
        result["ok"] = result["error"] is None
    except Exception as e:  # noqa: BLE001
        result["error"] = f"sync failed: {e}"
        log.error("sync events->history failed: %s", e)

    return result


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler()],
    )
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=_DEFAULT_START,
                    help="Start date YYYY-MM-DD (default: %(default)s)")
    ap.add_argument("--end", default=_DEFAULT_END,
                    help="End date YYYY-MM-DD (default: %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be fetched, make no writes")
    ap.add_argument("--timeout-s", type=int, default=600,
                    help="Hard timeout in seconds (default: %(default)s)")
    a = ap.parse_args()

    result = run(start=a.start, end=a.end, dry_run=a.dry_run, timeout_s=a.timeout_s)

    print("\n=== LHB BACKFILL SUMMARY ===")
    print(f"  Status              : {'OK' if result['ok'] else 'FAILED'}")
    print(f"  Error               : {result.get('error') or 'none'}")
    print(f"  Events appended     : {result['events_appended']}")
    print(f"  Total events in store: {result['total_events']}")
    print(f"  Date range          : {result['date_range'][0]} .. {result['date_range'][1]}")
    print(f"  history.parquet size: {result['store_mb']:.1f} MB")
    if result["r2_needed"]:
        print(f"  R2-PLANE NOTE: store >= {_R2_SIZE_MB:.0f} MB — consider moving to R2 "
              "per the data-plane convention (r2 memory note / scripts/audit_r2).")
    else:
        print(f"  R2-PLANE NOTE: store < {_R2_SIZE_MB:.0f} MB — safe to commit in-tree.")
    print("============================\n")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
