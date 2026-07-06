"""scripts/build_research_queue.py — CLI runner for the research-queue EV-ranker.

Thin wrapper: calls engine.neuralweb.research_queue.write_queue() and prints a
one-line summary.

NOT registered in collect.py.  NOT on the render path.
Run manually or via future nightly opt-in.

Usage:
    python -m scripts.build_research_queue [--root /path/to/repo]

Exit codes:
    0 — success
    1 — failure
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the research-queue EV-ranker artifact (nw-quant-synthesis B)."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root (defaults to auto-detect).",
    )
    args = parser.parse_args()

    root: Path | None = Path(args.root) if args.root else None

    try:
        from engine.neuralweb.research_queue import write_queue  # noqa: PLC0415
        payload = write_queue(root=root)
    except Exception as e:  # noqa: BLE001
        log.error("build_research_queue: FAILED — %s", e, exc_info=True)
        return 1

    summary = payload.get("summary", {})
    budget = payload.get("trial_budget", {})
    next_best = payload.get("next_best_experiment")
    out_path = (Path(args.root) if args.root else Path(".")) / "data" / "neuralweb" / "research_queue.json"

    print(
        f"research-queue: {summary.get('total_candidates', 0)} candidates | "
        f"high_ev={summary.get('high_ev', 0)} "
        f"blocked={summary.get('blocked', 0)} "
        f"sparse={summary.get('sparse', 0)} "
        f"dup={summary.get('duplicate', 0)} "
        f"invalid={summary.get('invalid', 0)} | "
        f"next_best={next_best!r} | "
        f"week_remaining={budget.get('week_remaining', '?')} | "
        f"→ {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
