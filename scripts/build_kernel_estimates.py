"""scripts/build_kernel_estimates.py — CLI wrapper for engine.neuralweb.kernel.

Thin wrapper: calls write_estimates() and prints a one-line summary.
Part of the Neural Web W3 PR1 daily pipeline step.

Usage:
    python -m scripts.build_kernel_estimates [--root /path/to/repo]

Exit codes:
    0 — success (even if some cells are empty due to sparse data)
    1 — write failure (parquet write or critical internal error)
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
        description="Build reliability kernel estimates (neural-web W3)."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root (defaults to auto-detect via lib.config).",
    )
    args = parser.parse_args()

    root: Path | None = Path(args.root) if args.root else None

    try:
        from engine.neuralweb.kernel import write_estimates  # noqa: PLC0415
        stats = write_estimates(root)
    except Exception as e:  # noqa: BLE001
        log.error("build_kernel_estimates: FAILED — %s", e)
        return 1

    n_cells = stats.get("n_cells", 0)
    n_engines = stats.get("n_engines", 0)
    n_rows = stats.get("n_graded_rows_input", 0)
    families = stats.get("families", {})
    n_armed = sum(1 for f in families.values() if f.get("armed"))
    n_families = len(families)

    # One-line summary for CI log
    print(
        f"kernel-estimates: {n_cells} cells | {n_engines} engines | "
        f"{n_rows} graded input rows | "
        f"{n_armed}/{n_families} families armed | "
        f"→ {stats.get('output_path', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
