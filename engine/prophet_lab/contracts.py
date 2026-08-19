"""engine/prophet_lab/contracts.py — frozen shapes for the Prophet Operator Lab.

Everything here is DATA, pinned against ``research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md``
§3-§5 (the "LAB-0" doc, ``DEC:PROPHET-LAB-B5A-RECUT``).  Board ids, board
definitions, the observation-class vocabulary, and the all-false authority
block are FROZEN at that doc — this module restates them as importable
constants so the API and its tests share exactly one copy.

This package is a **presentation/projection layer over canonical Radar
output** (LAB-0 §1): read / filter / join / decorate only.  No detector
formula execution, no forward-outcome reads, no Prophet-store writes, no
second StochRSI, no second market-data plane, no second Radar scheduler.
"""
from __future__ import annotations

SCHEMA_LAB_BOARD = "prophet.lab_board/v1"

# ---------------------------------------------------------------------------
# Radar detector identities the Lab boards project (LAB-0 §3, frozen strings —
# these are Radar's own ``detector_id`` values, restated here so the six board
# filters have exactly one source of truth for "which detector" they read).
# ---------------------------------------------------------------------------
G0_DETECTOR_ID = "G0_GREY_DOT@1"
C1_DETECTOR_ID = "C1_1D_LIVE_WASHOUT@1"
C2_DETECTOR_ID = "C2_1D_TURN@1"
C3_DETECTOR_ID = "C3_1D_4H_RECOVERY@1"
C5_DETECTOR_ID = "C5_BOTTOM_WATCH@1"

#: The six C2 variant subtypes, in the contract's own order (mirrors
#: ``engine.entry_radar.entry_events.RADAR_1D_TURN_SUBTYPES`` — restated
#: rather than imported so this display-tier package never needs the full
#: Radar detector stack to load, matching the "read only" law).
C2_SUBTYPES: tuple[str, ...] = (
    "c2a_kd_cross",
    "c2b_k_slope",
    "c2c_higher_k_low",
    "c2d_hist_trough",
    "c2e_hist_curvature",
    "c2f_rebound_atr",
)
C2A_SUBTYPE = "c2a_kd_cross"

# ---------------------------------------------------------------------------
# Board ids (LAB-0 §3, frozen — exactly these six, in this order)
# ---------------------------------------------------------------------------
BOARD_G0 = "lab-g0-v1"
BOARD_C1 = "lab-c1-v1"
BOARD_C2A = "lab-c2a-v1"
BOARD_C2_VARIANTS = "lab-c2-variants-v1"
BOARD_G0_C2A_INTERSECTION = "lab-g0-c2a-v1"
BOARD_ALL_EARLY = "lab-all-early-v1"

BOARD_IDS: tuple[str, ...] = (
    BOARD_G0,
    BOARD_C1,
    BOARD_C2A,
    BOARD_C2_VARIANTS,
    BOARD_G0_C2A_INTERSECTION,
    BOARD_ALL_EARLY,
)

BOARD_DEFINITIONS: dict[str, str] = {
    BOARD_G0: "exact G0_GREY_DOT@1",
    BOARD_C1: "C1_1D_LIVE_WASHOUT@1, current nonterminal episode",
    BOARD_C2A: "C2_1D_TURN@1 / c2a_kd_cross",
    BOARD_C2_VARIANTS: (
        "C2_1D_TURN@1, all six subtypes (c2a_kd_cross, c2b_k_slope, "
        "c2c_higher_k_low, c2d_hist_trough, c2e_hist_curvature, "
        "c2f_rebound_atr) — expert identities remain separate"
    ),
    BOARD_G0_C2A_INTERSECTION: (
        "display set intersection of lab-g0-v1 and lab-c2a-v1 only; "
        "view detector_id=null; mints zero events/episodes/scores"
    ),
    BOARD_ALL_EARLY: (
        "union of lab-g0-v1 + lab-c1-v1 + lab-c2-variants-v1; one ticker "
        "card may carry multiple experts[]; EXCLUDES C3/C5"
    ),
}

# ---------------------------------------------------------------------------
# Observation-class contract (LAB-0 §4, frozen)
# ---------------------------------------------------------------------------
OBSERVATION_RETROSPECTIVE_SEED = "retrospective_seed"
OBSERVATION_LIVE_FORWARD = "live_forward"
OBSERVATION_CLASSES: tuple[str, ...] = (
    OBSERVATION_RETROSPECTIVE_SEED,
    OBSERVATION_LIVE_FORWARD,
)

# ---------------------------------------------------------------------------
# The all-false authority block (LAB-0 §1/§5, frozen).  The Lab has ZERO
# ranking, gating, sizing, plan-origination, signal-origination, or
# Prophet-mutation authority — literally in the payload, on every response.
# ---------------------------------------------------------------------------
ALL_FALSE_AUTHORITY: dict[str, bool] = {
    "ranking": False,
    "gating": False,
    "sizing": False,
    "plan_origination": False,
    "signal_origination": False,
    "prophet_mutation": False,
}

#: Env var kill switch (LAB-0 §5/§7) — stands the API down independently of
#: Radar's own ``ENTRY_RADAR_LIVE_ENABLE``/``ENTRY_RADAR_LIVE_DISABLED``.
KILL_SWITCH_ENV = "PROPHET_LAB_DISABLED"

__all__ = [
    "SCHEMA_LAB_BOARD",
    "G0_DETECTOR_ID",
    "C1_DETECTOR_ID",
    "C2_DETECTOR_ID",
    "C3_DETECTOR_ID",
    "C5_DETECTOR_ID",
    "C2_SUBTYPES",
    "C2A_SUBTYPE",
    "BOARD_G0",
    "BOARD_C1",
    "BOARD_C2A",
    "BOARD_C2_VARIANTS",
    "BOARD_G0_C2A_INTERSECTION",
    "BOARD_ALL_EARLY",
    "BOARD_IDS",
    "BOARD_DEFINITIONS",
    "OBSERVATION_RETROSPECTIVE_SEED",
    "OBSERVATION_LIVE_FORWARD",
    "OBSERVATION_CLASSES",
    "ALL_FALSE_AUTHORITY",
    "KILL_SWITCH_ENV",
]
