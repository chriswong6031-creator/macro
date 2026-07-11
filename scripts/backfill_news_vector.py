"""One-shot, date-ranged GDELT re-pull to repair a news_vector accrual gap.

Usage:
    python -m scripts.backfill_news_vector --start 2026-06-20 [--end YYYY-MM-DD]
                                           [--window-days 2] [--max-records 250]
                                           [--dry-run]

Why this exists: the daily ingest window is only ``window_days`` (2) long, so
any stall longer than that loses coverage the daily retry can never recover
(the 2026-06-20..07-10 outage: GDELT's server-side max query length dropped
below the old single 288-char query and every daily fetch was rejected).
GDELT's DOC API accepts explicit startdatetime/enddatetime, so this tool
re-pulls the gap in window-sized slices through the SAME sub-query split, pace
gate, source/theme gating and keep-FIRST accrual as the daily path
(news_vector.fetch_range -> build_records -> accrue).

PIT honesty: keep-FIRST semantics are preserved — events already in the store
keep their original first_seen_utc, and backfilled rows are stamped with the
CRAWL time (now), because that IS when we first saw them; first-seen may never
be backdated. The article's own date rides in ``seendate``.

Exit code is non-zero when any window hard-failed (rate_limited/fetch_error
with zero articles), so an operator/agent knows to re-run for the missing
slices. Never partial-writes: the merged store is written once at the end.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("backfill_news_vector")


def run(start: date, end: date, window_days: int = 2, max_records: int = 250,
        dry_run: bool = False) -> dict:
    """Backfill [start, end] into the news_vector event store. Returns a summary
    dict {windows: [...], n_raw, n_gated, n_new, n_total, failed_windows}."""
    import pandas as pd

    from engine import news_vector as nv

    cfg = nv._cfg()
    if not cfg.get("enabled", False):
        log.warning("news_vector.enabled is FALSE in config — backfilling anyway "
                    "(explicit operator invocation), but the daily ingest will "
                    "not accrue until it is re-enabled")

    # One scheduled-release map spanning the whole gap (±3d edges) for the
    # "explainable by the calendar?" stamp on backfilled rows.
    scheduled = nv._scheduled_map(end, back=(end - start).days + 3, fwd=3,
                                  use_fred=cfg.get("use_fred", True))

    windows: list[dict] = []
    raw_all: list[dict] = []
    cursor = start
    while cursor <= end:
        win_end = min(cursor + timedelta(days=window_days), end)
        s_dt = datetime(cursor.year, cursor.month, cursor.day)
        e_dt = datetime(win_end.year, win_end.month, win_end.day, 23, 59, 59)
        articles, reason = nv.fetch_range(cfg, s_dt, e_dt, max_records=max_records)
        windows.append({"start": cursor.isoformat(), "end": win_end.isoformat(),
                        "n_articles": len(articles), "degraded_reason": reason})
        log.info("window %s..%s: %d articles%s", cursor, win_end, len(articles),
                 f" (degraded: {reason})" if reason else "")
        raw_all.extend(articles)
        cursor = win_end + timedelta(days=1)

    now_iso = datetime.now(timezone.utc).isoformat()
    records = nv.build_records(raw_all, scheduled, nv._allowlist(cfg), now_iso)

    path = nv._events_path()
    existing = pd.read_parquet(path) if path.exists() else None
    before = 0 if existing is None else len(existing)
    merged = nv.accrue(existing, records)
    n_new = len(merged) - before

    if dry_run:
        log.info("DRY RUN: would add %d new events (%d -> %d)", n_new, before, len(merged))
    else:
        merged.to_parquet(path, index=False)
        log.info("wrote %s: +%d new events (%d -> %d)", path, n_new, before, len(merged))

    failed = [w for w in windows
              if w["n_articles"] == 0 and w["degraded_reason"] not in (None, "no_headlines")]
    for w in failed:
        log.error("window %s..%s hard-failed (%s) — re-run for this slice",
                  w["start"], w["end"], w["degraded_reason"])
    return {"windows": windows, "n_raw": len(raw_all), "n_gated": len(records),
            "n_new": n_new, "n_total": int(len(merged)), "failed_windows": len(failed),
            "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--start", required=True, type=date.fromisoformat,
                    help="first day of the gap (typically the stale newest_event date)")
    ap.add_argument("--end", type=date.fromisoformat, default=date.today(),
                    help="last day of the gap (default: today)")
    ap.add_argument("--window-days", type=int, default=2,
                    help="slice size per GDELT pull (default 2, mirrors the daily window)")
    ap.add_argument("--max-records", type=int, default=250,
                    help="maxrecords per sub-query per slice (GDELT caps at 250)")
    ap.add_argument("--dry-run", action="store_true", help="fetch + gate but do not write")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    summary = run(args.start, args.end, window_days=args.window_days,
                  max_records=args.max_records, dry_run=args.dry_run)
    import json
    print(json.dumps(summary, indent=2))
    return 1 if summary["failed_windows"] else 0


if __name__ == "__main__":
    rc = main()
    # pyarrow one-shots can deadlock in Arrow's ThreadPool static destructor at
    # interpreter exit — leave via hard_exit, never a plain return (see lib.procutil).
    from lib.procutil import hard_exit
    hard_exit(rc)
