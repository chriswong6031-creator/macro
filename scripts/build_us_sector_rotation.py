"""XSR W1 — build US sector fast-rotation artifact.

Thin wrapper around engine.us_sector_rotation.compute_and_write().  Runs AFTER
the parallel band barrier (reads sector_cycles forward_log.parquet which is
written by build_sector_cycles in the band) and BEFORE build_sector_central
(which reads the artifact to re-order the board).

Non-fatal on any error — logs and exits 0 so it can never break the daily deploy.

Run: python -m scripts.build_us_sector_rotation
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_us_sector_rotation")


def main() -> int:
    try:
        from engine.us_sector_rotation import compute_and_write
        scored = compute_and_write()
        log.info("build_us_sector_rotation: wrote %d instruments", len(scored))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.exception("build_us_sector_rotation: failed (non-fatal): %s", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
