"""scripts/build_cycle_pattern_live.py — state_daily_live adapter driver.

Reads the three forward logs (data/{sector_cycles,country_cycles,
china_sector_cycles}/forward_log.parquet) and writes a unified daily view
at the path registered in config.yml under cycle_pattern_intelligence:
  state_daily_live_path = data/cycle_pattern/state_daily_live.parquet

Full deterministic rebuild from source each run (idempotent).
The forward logs are the append-only source of truth; this artifact is a
derived view — rebuilding from scratch is safer than a second append ledger.

Run:
    cd <repo> && python3 -m scripts.build_cycle_pattern_live

The driver registers the output path via config.yml; wiring agents add the
DAG step (daily.yml) after the three cycle builders so today's stamps are in
the logs before this view rebuilds.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Support both `python3 scripts/build_cycle_pattern_live.py` and
# `python3 -m scripts.build_cycle_pattern_live`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycle_pattern import live, registry
from lib import config

log = logging.getLogger("build_cycle_pattern_live")


def _live_path() -> Path:
    cfg = config.load()["cycle_pattern_intelligence"]
    return config.ROOT / cfg["state_daily_live_path"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load entity registry from disk (must be built first by build_cycle_pattern_lake.py).
    ep = config.ROOT / config.load()["cycle_pattern_intelligence"]["entities_path"]
    if not ep.exists():
        log.error("entities.parquet not found at %s — run build_cycle_pattern_lake.py first.", ep)
        sys.exit(1)

    import pandas as pd
    entities = pd.read_parquet(ep)

    state = live.build_state_daily_live(entities=entities)

    out_path = _live_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    state.to_parquet(out_path, index=False)

    unmapped_count = int(state["unmapped_id"].sum()) if "unmapped_id" in state.columns else 0
    log.info(
        "state_daily_live.parquet: %d rows, %d cols, %d unmapped -> %s",
        len(state), state.shape[1], unmapped_count, out_path,
    )

    expected = live.total_forward_log_rows()
    if len(state) != expected:
        log.warning(
            "Row count mismatch: output %d rows, sum-of-forward-logs %d rows.",
            len(state), expected,
        )
    else:
        log.info("Row count cross-check: %d == sum of forward logs.", len(state))


if __name__ == "__main__":
    main()
