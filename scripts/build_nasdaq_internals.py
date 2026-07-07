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
    """Build the artifact and write to disk. Returns the artifact dict (written or prior).

    Prior-artifact preservation rule (total-outage guard):
      - A freshly built payload is DEGRADED when every group has rs_20d == null
        (indicates a total price-data outage, not a per-group gap).
      - If the fresh payload is DEGRADED AND a prior artifact exists at the output
        path that (a) passes schema validation and (b) is itself NOT degraded
        (at least one group has rs_20d != null), then the prior file is left
        untouched and this function returns the prior artifact.  The prior file's
        unchanged asof timestamp correctly triggers the synapse freshness SLA,
        providing honest staleness signaling without data loss.
      - The all-null (degraded) payload is written only when no valid non-degraded
        prior exists.
      - A ``::error::``-prefixed log line is emitted whenever the preservation rule
        fires so CI/monitoring surfaces the outage.

    On any exception from build(): re-raises after logging (should not occur since
    build() catches internally).
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

    # Validate required schema keys (null-honest gate — raises on schema fault)
    _validate_payload(artifact)

    # Prior-payload preservation: do not overwrite a good prior with a total-outage null
    if _is_degraded(artifact):
        prior_artifact = _load_prior_artifact(out_path)
        if prior_artifact is not None and not _is_degraded(prior_artifact):
            log.error(
                "::error:: nasdaq_internals: fresh payload is DEGRADED (total price outage); "
                "prior artifact at %s is valid and non-degraded — leaving prior file unchanged. "
                "null_reasons=%s",
                out_path,
                artifact.get("null_reasons", []),
            )
            return prior_artifact

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


def _is_degraded(artifact: dict) -> bool:
    """Return True if every group in the artifact has rs_20d == null.

    This is the total-outage sentinel: a partial outage (some groups null, some non-null)
    is NOT considered degraded and WILL overwrite the prior artifact normally.
    """
    groups = artifact.get("groups", [])
    if not groups:
        return True
    return all(g.get("rs_20d") is None for g in groups)


def _load_prior_artifact(out_path: Path) -> dict | None:
    """Load and validate the prior artifact from disk.

    Returns the parsed dict if the file exists, parses successfully, and passes
    schema validation.  Returns None on any read/parse/schema failure.
    """
    if not out_path.exists():
        return None
    try:
        data = json.loads(out_path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("nasdaq_internals: could not parse prior artifact (%s)", e)
        return None
    try:
        _validate_payload(data)
    except ValueError as e:
        log.warning("nasdaq_internals: prior artifact failed schema validation (%s)", e)
        return None
    return data


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    build_and_write()


if __name__ == "__main__":
    main()
