"""scripts/build_organism_state.py — CLI driver for organism_state (V2-A §1).

Writes data/metabolism/organism_state.json.

INERTNESS: this script ONLY reads + computes + writes the artifact.
It dispatches nothing, grants nothing, opens no PR, touches no lobe roster.

KILL SWITCH: respects AUTONOMY_PAUSED (is_paused() from metabolism_guard).
An unset or non-'false' AUTONOMY_PAUSED → clean journaled no-op (exit 0).

Usage:
    python -m scripts.build_organism_state
    python -m scripts.build_organism_state --root /path/to/repo
    python -m scripts.build_organism_state --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from scripts.metabolism_guard import is_paused, pause_reason  # noqa: E402
from engine.metabolism.organism_state import build_organism_state  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_organism_state")

OUTPUT_PATH = Path("data") / "metabolism" / "organism_state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build organism_state.json (V2-A)")
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--dry-run", action="store_true", help="Print artifact without writing")
    args = parser.parse_args(argv)

    # KILL SWITCH — double-gated: env var check
    if is_paused():
        log.info("AUTONOMY_PAUSED — %s — clean no-op.", pause_reason())
        return 0

    root = Path(args.root) if args.root else _ROOT_DIR

    log.info("Building organism_state …")
    state = build_organism_state(root=root)

    out_str = json.dumps(state, indent=2, ensure_ascii=False)

    if args.dry_run:
        print(out_str)
        log.info("DRY RUN — not written.")
        return 0

    out_path = root / OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_str, encoding="utf-8")
    log.info("Wrote %s (lobes=%d, gaps=%d)", out_path, state.get("whole_organism", {}).get("n_lobes", 0), len(state.get("gaps", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
