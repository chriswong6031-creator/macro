"""Thin CLI wrapper: compose world_state.json and write it to data/neuralweb/.

Usage
-----
    python -m scripts.build_world_state [--root REPO_ROOT] [--out OUT_PATH]

Exit codes
----------
0 — artifact written (partial gaps are printed but do not cause non-zero exit).
1 — total failure to write the artifact.

Designed to be inserted in .github/workflows/daily.yml AFTER the oracle_nightly
step and BEFORE 'commit engine outputs'.  Resilient: the caller wraps with
    || echo "::warning::build_world_state failed (non-fatal)"
so CI continues even if this step fails.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running as a module from the repo root (python -m scripts.build_world_state)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.world_state import build_and_write  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_world_state")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compose data/neuralweb/world_state.json from existing stores."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: data/neuralweb/world_state.json under root).",
    )
    args = parser.parse_args(argv)

    try:
        payload = build_and_write(root=args.root, out_path=args.out)
    except OSError as exc:
        log.error("world_state: FAILED to write artifact — %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("world_state: unexpected error — %s", exc)
        return 1

    gaps: list[str] = payload.get("gaps") or []
    if gaps:
        print(f"world_state: PARTIAL — {len(gaps)} gap(s):")
        for g in gaps:
            print(f"  - {g}")
    else:
        print("world_state: all sources read OK — no gaps")

    # One-line summary: verdict, regime quad, gaps count
    verdict_block = payload.get("verdict") or {}
    regime_block = payload.get("regime") or {}
    verdict = verdict_block.get("verdict") or "?"
    quad = regime_block.get("quad_name") or regime_block.get("quad") or "?"
    produced_at = payload.get("produced_at") or "?"
    print(
        f"world_state OK — verdict={verdict} quad={quad} "
        f"gaps={len(gaps)} produced_at={produced_at}"
    )

    # Also print out_path for CI log visibility
    if args.out:
        dest = args.out
    else:
        root = args.root
        if root is None:
            root = Path(__file__).resolve().parent.parent
        dest = root / "data" / "neuralweb" / "world_state.json"
    print(f"written: {dest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
