"""Nightly entry point for the W3 prospective evidence ledger (PR-3C).

Accrues paired C1 + v2-shadow observations and the PR-3B structural receipt
into ``data/us_prophet_rank/w3/``. All logic lives in :mod:`engine.us_prophet_w3`;
this file is the CLI + DAG surface.

NIGHTLY IS THE SOLE ADVANCER. ``--nightly`` is the only path that writes, and
the engine's appenders additionally gate on
``ledger_lane.nightly_advance_enabled()`` (COLLECT_LANE=nightly).

ZERO AUTHORITY. No rank, gate, size, board, featured, or plan consumer.
No comparative W3 statistic is computed or printed.

Run (nightly / DAG):  python -m scripts.accrue_us_prophet_w3 --nightly
Run (safe preview):   python -m scripts.accrue_us_prophet_w3 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import us_prophet_w3 as w3  # noqa: E402
from engine.us_prophet_w3 import (  # noqa: E402
    W3ConflictError,
    W3IntegrityError,
    W3SchemaError,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance the W3 store (the SOLE advancer; DAG entry)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build rows and print; writes nothing")
    ap.add_argument("--json", action="store_true", help="dump the run document as JSON")
    ap.add_argument("--require-stamp", default=None,
                    help="fail closed if this stamp_date is not in the durable "
                         "candidates store (never fetch Pages)")
    ap.add_argument("--require-board-as-of", action="store_true",
                    help="resolve the required stamp from the committed board "
                         "as_of (never wall-clock / run id / Pages)")
    args = ap.parse_args()

    try:
        # --nightly is the production advancer: observation identity is the
        # committed board as_of, never wall-clock / run id. The explicit flag
        # remains for daily.yml documentation; DAG args stay [--nightly] so
        # this file is not a global CI invalidator.
        doc = w3.accrue(
            dry_run=bool(args.dry_run or not args.nightly),
            require_stamp=args.require_stamp,
            require_board_as_of=bool(args.require_board_as_of or args.nightly),
        )
    except (W3ConflictError, W3IntegrityError, W3SchemaError) as exc:
        print(f"::error title=w3-ledger::{exc}", flush=True)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
        return
    print(w3.summary_line(doc))
    if doc.get("note"):
        print(f"  {doc['note']}")
    for row in doc.get("degraded") or []:
        print(f"  degraded: {row}")
    for session in doc.get("sessions") or []:
        print(
            f"  {session.get('stamp_date')}  {session.get('liveness')}  "
            f"paired={session.get('n_paired')} pending={session.get('n_pending_outcome')}"
        )


if __name__ == "__main__":
    main()
