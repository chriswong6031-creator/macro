"""scripts/backfill_regime_stamps.py — Thin wrapper for qledger regime stamp backfill.

Calls engine.qledger.backfill_regime_stamps() which has NO CLI. Near-term yield
≈ 2 rows (only rows with as_of >= 2026-07-01 can be stamped from regime_vector.parquet).

This script is a resilient daily.yml step. It is a WRAPPER ONLY — all logic lives
in engine/qledger.py:backfill_regime_stamps().
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main() -> int:
    """Call engine.qledger.backfill_regime_stamps() and log the honest yield."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        from engine import qledger  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        log.error("backfill_regime_stamps: cannot import engine.qledger (%s) — skipping", e)
        return 0  # non-fatal; new runner may not have engine in path

    fn = getattr(qledger, "backfill_regime_stamps", None)
    if fn is None:
        log.warning(
            "backfill_regime_stamps: engine.qledger has no backfill_regime_stamps() — "
            "function may not yet exist; skipping (non-fatal)"
        )
        return 0

    try:
        result = fn()
        # engine.qledger.backfill_regime_stamps() returns a dict or count
        if isinstance(result, dict):
            stamped = result.get("stamped", 0)
            skipped = result.get("skipped", 0)
            print(
                f"backfill_regime_stamps: {stamped} row(s) stamped, "
                f"{skipped} skipped (near-term yield ≈ 2 rows from "
                f"regime_vector.parquet coverage 2026-07-01/02)"
            )
        elif isinstance(result, int):
            print(f"backfill_regime_stamps: {result} row(s) stamped")
        else:
            print(f"backfill_regime_stamps: complete (result={result!r})")
    except Exception as e:  # noqa: BLE001
        # Non-fatal: backfill failure never blocks the nightly render
        log.warning("backfill_regime_stamps: backfill_regime_stamps() failed (%s) — non-fatal", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
