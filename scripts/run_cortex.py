"""scripts/run_cortex.py — Thin CLI wrapper for the cortex deliberation runtime.

Usage:
    python scripts/run_cortex.py [--root PATH] [--force]
    python -m engine.neuralweb.cortex [--root PATH] [--force]

Both invocations are equivalent.  This script exists as a convenience
entrypoint for the Actions job (``python scripts/run_cortex.py``); the
module can also be run directly via ``python -m engine.neuralweb.cortex``.

The cortex is on shadow probation (W7b PR1).  It always exits 0 — failures
produce a degraded memo but never abort the job.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [cortex] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Cortex deliberation runtime (Neural Web W7b PR1)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root override (default: auto-detected from module location)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip staleness gate and run regardless of input changes",
    )
    args = parser.parse_args()

    from engine.neuralweb.cortex import run  # noqa: PLC0415
    return run(root=args.root, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
