"""scripts.build_surface_map — regenerate the V12 site-surface census.

Deterministic, no LLM, no network (R-V12-2).  Runs in the metabolism AGENDA
stage (best-effort, mirrors the criticality step) and on demand:

    python -m scripts.build_surface_map [--root PATH]

Writes data/metabolism/site_surface_map.json and prints a one-line summary.
Exit 0 always (NEVER-RAISE — the census must never block a stage).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.metabolism.surface_map import build_surface_map  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the site-surface census (V12).")
    ap.add_argument("--root", default=None, help="Repo root override (tests).")
    try:
        args = ap.parse_args(argv)
        root = Path(args.root) if args.root else None
        result = build_surface_map(root=root, write=True)
        counts = result.get("counts") or {}
        print(
            f"surface_map: {counts.get('pages', 0)} pages censused, "
            f"{counts.get('saturated', 0)} saturated"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"surface_map: degraded ({exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
