"""scripts/build_til_fitness.py — TIL fitness card writer (A3, SENSE stage).

Assembles the TIL fitness card from immutable sensors and writes it atomically
to data/metabolism/fitness/til.json.

Sensors read (IMMUTABLE — this script must never edit them):
  - data/foresight/earliness_grades.json  (written by grade_thematic Stage 1)
  - data/foresight/theme_placebo_tape.jsonl (written by grade_thematic Stage 2)
  - data/qledger/falsifier_evaluations.jsonl (written by grade_thematic Stage 3)
  - data/qledger/claims.jsonl

All fitness metrics are labelled "accruing" until ~2026-10-15 (the first real
check_by in the TIL pre-registered trial contracts).

Registered in config/synapse.yml as 'metabolism-til-fitness'.

Usage:
    python -m scripts.build_til_fitness [--root /path/to/repo] [--dry-run]

Exit 0 always (tolerant; errors are logged and honest null values are emitted).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("build_til_fitness")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from engine.metabolism.til_fitness import build_fitness_card, OUTPUT_PATH  # noqa: E402


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def run(root: Path, dry_run: bool = False) -> dict:
    """Build and optionally write the TIL fitness card.

    Returns the card dict (for testing; never raises).
    """
    try:
        card = build_fitness_card(root)

        if dry_run:
            log.info("[build_til_fitness] dry-run — not writing artifact")
        else:
            out_path = root.joinpath(*OUTPUT_PATH)
            _atomic_write_json(out_path, card)
            log.info("[build_til_fitness] wrote %s (maturity=%s)", out_path, card.get("maturity"))

        # Log per-sensor summary
        for name, sensor in card.get("sensors", {}).items():
            log.info(
                "  sensor %-20s value=%s n=%s maturity=%s",
                name,
                sensor.get("value"),
                sensor.get("n"),
                sensor.get("maturity"),
            )
        return card
    except Exception as exc:  # noqa: BLE001
        log.error("[build_til_fitness] unexpected error: %s", exc)
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TIL fitness card (A3)")
    parser.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    parser.add_argument("--dry-run", action="store_true", help="Build but do not write")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT
    run(root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
