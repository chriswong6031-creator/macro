"""Build the Nasdaq-100 archetype-group internals artifact.

Emits site/marketdata/nasdaq_internals.json — a descriptive rotation-state snapshot
over the 7 tech-archetype groups defined in data/baskets_nasdaq/membership.json.

DISPLAY-ONLY / DESCRIPTIVE. No forecast. Pure deterministic computation; no LLM.
Rulings: TI-R1..R7 (adjudication PR #1805, program nasdaq-internals).

Key properties:
  - Null-honest: missing prices → valid all-null artifact; never raises.
  - Prior artifact read for 2-day hysteresis state machine.
  - Additive: does not touch any existing oracle, engine/oracle, or scripts/oracle_*.

Run:
    python -m scripts.build_nasdaq_internals
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import nasdaq_internals  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_nasdaq_internals")

_OUT_PATH_REL = "site/marketdata/nasdaq_internals.json"


def build_and_write(root: Path | None = None) -> dict:
    """Build the artifact and write to disk. Returns the artifact dict.

    Writes are atomic: the prior artifact is preserved on any failure that
    prevents a valid payload from being produced (engine.nasdaq_internals.build
    returns a valid dict even on null path; only write is skipped on exception).
    """
    t0 = time.perf_counter()
    repo_root = root or config.data_dir().parent
    out_path = repo_root / _OUT_PATH_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        artifact = nasdaq_internals.build(root=repo_root)
    except Exception as e:  # noqa: BLE001
        # Should never reach here (build() catches internally), but defensive gate.
        log.error("nasdaq_internals.build() raised unexpectedly: %s", e)
        raise

    # Validate required schema keys before write (null-honest gate)
    _validate_payload(artifact)

    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
    elapsed = time.perf_counter() - t0

    n_groups = len(artifact.get("groups", []))
    null_reasons = artifact.get("null_reasons", [])
    n_nulls = len(null_reasons)

    log.info(
        "nasdaq_internals: %d groups, %d null_reasons, asof=%s → %s in %.2fs",
        n_groups, n_nulls, artifact.get("asof", "?"), out_path, elapsed,
    )
    if null_reasons:
        log.warning("nasdaq_internals null_reasons: %s", null_reasons)

    return artifact


def _validate_payload(artifact: dict) -> None:
    """Assert the artifact has all required top-level keys.

    Raises ValueError with detail if any key is missing.
    """
    required = {"schema", "asof", "benchmark", "watermark_en", "watermark_zh",
                "ew_vs_qqq", "groups", "divergences", "null_reasons"}
    missing = required - set(artifact.keys())
    if missing:
        raise ValueError(f"nasdaq_internals artifact missing keys: {missing}")
    if artifact.get("schema") != "nasdaq_internals.v1":
        raise ValueError(
            f"nasdaq_internals schema mismatch: {artifact.get('schema')!r} != 'nasdaq_internals.v1'"
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    build_and_write()


if __name__ == "__main__":
    main()
