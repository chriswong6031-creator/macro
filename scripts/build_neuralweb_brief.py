"""CLI wrapper: build the NW daily brief artifact (PR-D).

Usage
-----
    python -m scripts.build_neuralweb_brief [--root REPO_ROOT]
    python -m scripts.build_neuralweb_brief --finalize [--root REPO_ROOT]

Modes
-----
Engine phase (default):
    Builds data/neuralweb/daily_brief.json + site/neuralwebdata/daily_brief.json
    with phase='engine'. Does NOT touch the history file.

Finalize phase (--finalize):
    Rebuilds the brief with phase='final' using current health.json
    (post --refresh-cortex), rewrites both copies, and upserts one compact
    history row into data/neuralweb/daily_brief_history.jsonl keyed by as_of
    (same as_of → replace row; file stays chronologically sorted).

Exit codes
----------
0 — artifact written (always; fail-open contract).
0 — any input error → brief with explicit gap notes, still exit 0.

Resilient: intended to be called as:
    python -m scripts.build_neuralweb_brief || echo "::warning::..."
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.daily_brief import build, upsert_history, write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_neuralweb_brief")


def _repo_root(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build data/neuralweb/daily_brief.json — NW daily brief surface."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help=(
            "Cortex phase: rebuild with phase='final', rewrite both copies, "
            "and upsert one compact history row keyed by as_of."
        ),
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    try:
        phase = "final" if args.finalize else "engine"
        payload = build(root=root, phase=phase)
        write(payload, root=root)

        if args.finalize:
            upsert_history(payload, root=root)
            log.info(
                "build_neuralweb_brief: --finalize done — status=%s as_of=%s",
                payload.get("status"),
                payload.get("as_of"),
            )
        else:
            log.info(
                "build_neuralweb_brief: engine phase done — status=%s as_of=%s",
                payload.get("status"),
                payload.get("as_of"),
            )

        gaps = payload.get("_gaps", [])
        if gaps:
            log.warning("build_neuralweb_brief: %d gap(s): %s", len(gaps), "; ".join(gaps))

        return 0

    except Exception as exc:  # noqa: BLE001
        log.error("build_neuralweb_brief: FAILED — %s", exc)
        # Still exit 0 — fail-open contract
        return 0


if __name__ == "__main__":
    sys.exit(main())
