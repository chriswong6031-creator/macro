"""Build the explanation-memory display artifact.

Grades all 8 desk theses ledgers and writes
site/qledger/explanation_memory.json with attribution-verdict tallies,
per-desk matured counts, and Brier calibration.

This is a display/meta-only step — it never writes to names/scores/rank
surfaces (§5.3 of research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md).

Usage:
    python -m scripts.build_explanation_memory [--root PATH]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.explanation_memory import build_explanation_memory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_explanation_memory")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root override (default: auto-detect via lib.config.ROOT)",
    )
    args = parser.parse_args()

    payload = build_explanation_memory(root=args.root)

    log.info(
        "explanation_memory: total_theses=%d  total_matured=%d  status=%r",
        payload.get("total_theses", 0),
        payload.get("total_matured", 0),
        payload.get("status", ""),
    )

    overall = payload.get("overall_verdicts", {})
    if any(v > 0 for v in overall.values()):
        log.info("verdict tallies: %s", overall)
    else:
        log.info("verdict tallies: all zero (no matured theses yet)")

    brier = payload.get("brier", {})
    brier_val = brier.get("brier") if isinstance(brier, dict) else None
    if brier_val is None:
        note = brier.get("note", "") if isinstance(brier, dict) else ""
        log.info("brier: N/A — %s", note)
    else:
        log.info("brier: %.4f  skill_score=%s", brier_val, brier.get("skill_score"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
