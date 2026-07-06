"""scripts/build_cycle_pattern_outcomes.py — CPI outcome-spine driver.

Builds data/cycle_pattern/outcomes.parquet (path read from
config.yml['cycle_pattern_intelligence']['outcomes_path']): one label-side row per
state_monthly (entity_id, date) with forward returns / drawdowns / benchmark-excess
returns (china-grader bar-i+1 convention), turn-event labels (hazard left-join), and
within-entity phase transitions. See engine/cycle_pattern/outcomes.py for the binding
conventions.

Pure numpy/pandas over committed tapes + the hazard panel; no engine recompute.
Deterministic (sorted rows, stable dtypes) so a rebuild is frame-equal to the prior run.

Run:  cd <repo> && python3 -m scripts.build_cycle_pattern_outcomes
"""
from __future__ import annotations

import logging
from pathlib import Path

from engine.cycle_pattern import outcomes
from lib import config

log = logging.getLogger("build_cycle_pattern_outcomes")


def _p(cfg_key: str) -> Path:
    cfg = config.load()["cycle_pattern_intelligence"]
    return config.ROOT / cfg[cfg_key]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    out = outcomes.build_outcomes()
    op = _p("outcomes_path")
    op.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(op, index=False)
    log.info("outcomes.parquet: %d rows, %d cols -> %s", len(out), out.shape[1], op)

    matured = int(out["ret_fwd_63d"].notna().sum())
    turns = int(out["turn_event_1m"].notna().sum())
    log.info("matured 63d windows: %d/%d (%.1f%%)",
            matured, len(out), 100.0 * matured / len(out))
    log.info("turn-event join: %d/%d rows (%.1f%%)",
            turns, len(out), 100.0 * turns / len(out))


if __name__ == "__main__":
    main()
