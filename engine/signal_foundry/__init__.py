"""engine.signal_foundry — deterministic spine of the Signal Foundry (SF-R1..SF-R12).

Public API re-exports.  NO LLM calls here (that is PR-C).  NO writes to engine/,
config/, scripts/, workflows/ — Foundry writes only data/signal_foundry/** (SF-R10).
"""
from __future__ import annotations

from engine.signal_foundry.spec import (
    load_spec,
    validate_spec,
    construction_hash,
)
from engine.signal_foundry.harness import run_spec
from engine.signal_foundry.screen import screen_candidate
from engine.signal_foundry.seeds import harvest_seeds
from engine.signal_foundry.results import (
    load_results,
    promotion_docket,
    accrue_forward,
)

__all__ = [
    "load_spec",
    "validate_spec",
    "construction_hash",
    "run_spec",
    "screen_candidate",
    "harvest_seeds",
    "load_results",
    "promotion_docket",
    "accrue_forward",
]
