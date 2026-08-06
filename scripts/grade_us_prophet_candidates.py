"""Nightly entry point for the full-population US candidate grader (PROPHET US §W7).

Grades every matured row of the US Context Vector store
(``data/us_prophet_rank/candidates/YYYY-MM.parquet``) at H=10 and H=21 sessions,
excess vs SPY, into ``data/us_prophet_rank/grades/YYYY-MM.parquet``.  All logic lives in
:mod:`engine.us_prophet_grades`; this file is the CLI + DAG surface.

WHY (operator order 2026-08-05): the board admits ~12 plans a night, so the graded record
grew at ~12 rows a night while the system formed an opinion about ~1,579 names.  This
grades all of them — "more data to train on" — without changing which names are picked.

NIGHTLY IS THE SOLE ADVANCER.  ``--nightly`` is the only path that writes, and the engine's
``append_grades`` additionally gates on ``ledger_lane.nightly_advance_enabled()``
(COLLECT_LANE=nightly), so an intraday or render lane writes nothing even if invoked with
the flag.  Re-running on the same night appends nothing (one-grader law: a graded
``(stamp_date, ticker, board_definition, horizon)`` is frozen).

ZERO AUTHORITY.  No rank, gate, size, board or plan consumer.  The record is measured by
the miss-audit's ``priority_score_scorecard`` block and read by nothing else.

Run (nightly / DAG):  python -m scripts.grade_us_prophet_candidates --nightly
Run (safe preview):   python -m scripts.grade_us_prophet_candidates --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import us_prophet_grades as upg  # noqa: E402

log = logging.getLogger("grade_us_prophet_candidates")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance the grade store (the SOLE advancer; DAG entry)")
    ap.add_argument("--dry-run", action="store_true",
                    help="grade and print; writes nothing")
    ap.add_argument("--json", action="store_true", help="dump the run document as JSON")
    ap.add_argument("--limit", type=int, default=25,
                    help="rows printed in the human summary (default 25)")
    args = ap.parse_args()

    doc = upg.run(dry_run=bool(args.dry_run or not args.nightly))
    if args.json:
        # rows can be tens of thousands on a catch-up night; the document stays the
        # machine surface, so it keeps them, but nothing else prints them.
        print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
        return

    print(upg.summary_line(doc))
    if doc.get("note"):
        print(f"  {doc['note']}")
    for row in doc.get("degraded") or []:
        print(f"  degraded: {row.get('input')} — {row.get('reason')}")
    by_h = doc.get("by_horizon") or {}
    if by_h:
        print("  new rows by horizon: "
              + ", ".join(f"H={h}: {n}" for h, n in sorted(by_h.items())))
    for row in (doc.get("rows") or [])[:max(0, args.limit)]:
        excess = row.get("excess_spy")
        print(f"    {row['stamp_date']} {row['ticker']:<6} H={row['horizon']:<3} "
              f"ret={row['fwd_ret']:+.4f} spy={row.get('bench_ret')} "
              f"excess={excess if excess is None else f'{excess:+.4f}'}")


if __name__ == "__main__":
    main()
