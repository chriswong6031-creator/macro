"""scripts/build_cycle_pattern_lake.py — CPI substrate v0 driver.

Builds three committed artifacts under data/cycle_pattern/ (paths read from
config.yml['cycle_pattern_intelligence']):
  - entities.parquet          — one row per cycle entity across all engines
  - state_monthly.parquet     — unified monthly PIT research panel
  - state_monthly_meta.json   — column-level PIT metadata sidecar

Pure joins over committed backfills + the hazard feature panel; no engine
recompute. Deterministic (sorted rows, stable dtypes) so a rebuild is
frame-equal to the prior run.

Run:  cd <repo> && python3 -m scripts.build_cycle_pattern_lake
"""
from __future__ import annotations

import logging
from pathlib import Path

from engine.cycle_pattern import lake, registry
from lib import config

log = logging.getLogger("build_cycle_pattern_lake")


def _p(cfg_key: str) -> Path:
    cfg = config.load()["cycle_pattern_intelligence"]
    return config.ROOT / cfg[cfg_key]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    entities = registry.build_entities()
    ep = _p("entities_path")
    ep.parent.mkdir(parents=True, exist_ok=True)
    entities.to_parquet(ep, index=False)
    log.info("entities.parquet: %d rows -> %s", len(entities), ep)

    state = lake.build_state_monthly()
    sp = _p("state_monthly_path")
    state.to_parquet(sp, index=False)
    log.info("state_monthly.parquet: %d rows, %d cols -> %s",
            len(state), state.shape[1], sp)

    mp = _p("state_monthly_meta_path")
    lake.write_meta(mp)
    log.info("state_monthly_meta.json -> %s", mp)

    joined = int(state["hazard_epoch"].notna().sum())
    log.info("hazard feature join: %d/%d rows (%.1f%%)",
            joined, len(state), 100.0 * joined / len(state))


if __name__ == "__main__":
    main()
