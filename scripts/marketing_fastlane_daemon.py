"""scripts/marketing_fastlane_daemon.py — Thin runner for the earnings fast lane.

Usage:
    python scripts/marketing_fastlane_daemon.py [--once] [--dry-run] [--interval N]

Flags:
    --once       Run exactly one tick then exit (useful for cron / one-shot jobs).
    --dry-run    Compute the full tick (fetch, dedupe, copy, card) but write
                 nothing to disk.  Prints a summary to stdout.
    --interval N Poll interval in seconds (default: 120).  Ignored with --once.

Kill-switch:
    If the environment variable MARKETING_FASTLANE_ENABLED is not exactly "1",
    the daemon prints a note and exits 0 immediately.  This prevents accidental
    publication during development and CI runs.

Heartbeat:
    Each successful tick touches data/marketing/fastlane_heartbeat.txt with the
    current UTC timestamp.  The W1 launchd integration can alert when this file
    goes stale during market windows (>15 min gap).  --dry-run skips the
    heartbeat write.

Structured log format (one line per tick):
    [fastlane] tick | emitted=N skipped=N quarantined=N | <ISO-UTC>

No git writes.  No ledger advances.  The daemon is a fully intraday lane.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Repo root resolution (same pattern as test helpers)
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate repo root from {p}")


ROOT = _repo_root()

# Add repo root to sys.path so engine.marketing imports work when the script is
# called directly (e.g., python scripts/marketing_fastlane_daemon.py).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("fastlane_daemon")

_HEARTBEAT_PATH = ROOT / "data" / "marketing" / "fastlane_heartbeat.txt"
_KILL_SWITCH_ENV = "MARKETING_FASTLANE_ENABLED"
_DEFAULT_INTERVAL_S = 120


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────────────────────────────────────

def _touch_heartbeat(now: datetime) -> None:
    """Update the heartbeat file with current UTC timestamp."""
    try:
        _HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HEARTBEAT_PATH.write_text(now.strftime("%Y-%m-%dT%H:%M:%SZ\n"), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane_daemon] heartbeat write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Single tick
# ─────────────────────────────────────────────────────────────────────────────

def _run_one_tick(*, dry_run: bool) -> dict:
    """Run one fetch-and-process tick.  Returns the TickResult dict."""
    from engine.marketing.earnings_feed import fetch_events
    from engine.marketing.fastlane import run_tick

    now = datetime.now(timezone.utc)
    # Fetch events since a lookback window (last 30 minutes) — the seen-ledger
    # handles deduplication so overlap is safe.
    from datetime import timedelta
    since = now - timedelta(minutes=30)

    events = fetch_events(since)
    result = run_tick(events, root=ROOT, now=now, dry_run=dry_run)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Log line formatter
# ─────────────────────────────────────────────────────────────────────────────

def _log_tick(result: dict, now: datetime, *, dry_run: bool) -> None:
    dry_tag = " [DRY-RUN]" if dry_run else ""
    emitted_n = len(result.get("emitted", []))
    skipped_n = len(result.get("skipped", []))
    quarantined_n = len(result.get("quarantined", []))
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(
        "[fastlane] tick%s | emitted=%d skipped=%d quarantined=%d | %s",
        dry_tag,
        emitted_n,
        skipped_n,
        quarantined_n,
        ts,
    )
    if dry_run and emitted_n:
        for item in result["emitted"]:
            logger.info(
                "[fastlane] [DRY-RUN] would emit %s | %s | %s",
                item.get("id", "?"),
                item.get("provenance", {}).get("ticker", "?"),
                (item.get("text") or {}).get("headline", "")[:60],
            )


# ─────────────────────────────────────────────────────────────────────────────
# main()
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns exit code."""
    # Kill-switch: check before any imports that might fail
    if os.environ.get(_KILL_SWITCH_ENV) != "1":
        print(
            f"[fastlane_daemon] {_KILL_SWITCH_ENV} != '1' — fast lane disabled. "
            "Set the env var to enable. Exiting 0.",
            file=sys.stdout,
        )
        return 0

    parser = argparse.ArgumentParser(
        description="Marketing real-time earnings fast lane daemon."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick and exit.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Compute but write nothing to disk.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=_DEFAULT_INTERVAL_S,
        help=f"Poll interval in seconds (default: {_DEFAULT_INTERVAL_S}).",
    )
    args = parser.parse_args(argv)

    logger.info(
        "[fastlane_daemon] starting | once=%s dry_run=%s interval=%ds",
        args.once,
        args.dry_run,
        args.interval,
    )

    while True:
        now = datetime.now(timezone.utc)
        try:
            result = _run_one_tick(dry_run=args.dry_run)
            _log_tick(result, now, dry_run=args.dry_run)
            if not args.dry_run:
                _touch_heartbeat(now)
        except Exception as exc:  # noqa: BLE001
            logger.error("[fastlane_daemon] tick error (continuing): %s", exc)

        if args.once:
            break

        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
