"""engine.pick_lab — Pick Lab candidate stock-pick engines (display-tier).

Adjudicated spec: research/PICK_LAB_MASTERPLAN_BY_FABLE.md
Authority: display_only. Gauntlet = PROMOTION gate, NOT build gate.
PL-R1: this package ranks and gates NOTHING in production.
"""
from engine.pick_lab.registry import REGISTRY, BY_ID
from engine.pick_lab.signals_1d import compute_grids
from engine.pick_lab.candidates import run_book
from engine.pick_lab.snapshot import (
    SNAPSHOT_COLUMNS,
    write_snapshot,
    latest_snapshot,
    build_core_rows,
)

__all__ = [
    "REGISTRY",
    "BY_ID",
    "compute_grids",
    "run_book",
    "SNAPSHOT_COLUMNS",
    "write_snapshot",
    "latest_snapshot",
    "build_core_rows",
]
