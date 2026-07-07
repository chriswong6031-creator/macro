"""engine/prophet_management.py — Prophet Management-Confidence Engine (V2 port).

Faithful Python port of the reverse-engineered MomoEdge V2 confidence model
(oracle_spec.md §4).  All section-number citations reference that document.

Output schema: prophet.management_state/v1
Public API:    compute_management_state(plan, price_history, asof, macro_stance,
                                         futures_chg, prev_state) -> dict

EPISTEMIC LAWS (binding on this module):
  • "validated" MUST NOT appear in any user-facing string.
  • This is a TRADE-MANAGEMENT score, NOT a pick-rank score.
  • LLMs may only narrate/de-escalate — never originate signals or escalations.
  • Confidence ceiling = 92.  Uncertainty is honest; certainty is forbidden.
  • PIT-SAFE: no wall-clock reads anywhere; every temporal value derived from
    the explicit `asof` parameter and the provided price history.

NIGHTLY-CADENCE DEVIATIONS FROM BROWSER-LIVE SEMANTICS:
  Wherever the browser model uses real-time tick data (e.g. intra-session
  momentum pulse from live last-print-to-last-print), this port substitutes the
  closest PIT-safe daily value.  Each deviation is marked with an 'OURS:' block.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd

from engine.options_structure import (
    AUTHORITY_DISPLAY,
    MANAGEMENT_CONFIDENCE_CEILING,
    validate_management_state,
)

# ── module-level constant (§4 step 6) ────────────────────────────────────────
CONFIDENCE_CEILING: int = MANAGEMENT_CONFIDENCE_CEILING   # 92

# ── valid phase strings (matches options_structure._PHASE_VALUES) ─────────────
_VALID_PHASES = frozenset({
    "pre_trigger", "triggered_pre_t1", "at_t1", "between_t1_t2",
    "at_t2", "overtime", "invalidated",
})

# ── oracle_spec §4 internal detection phases (superset of schema phases) ──────
# oracle_spec §4 step 3 defines 7 detection states including post_t1_failed_hold
# and post_t2.  The OPTIONS_SENSOR_CONTRACT.md §6 schema uses a different 7-phase
# lifecycle (at_t1 / between_t1_t2 instead of post_t1_failed_hold / post_t2).
# This mapping converts internal detection phases → schema-valid output phases.
# Internal logic (weights, bounds, actions) always uses the detection phase.
_DETECTION_TO_SCHEMA_PHASE: dict[str, str] = {
    "pre_trigger":          "pre_trigger",
    "triggered_pre_t1":     "triggered_pre_t1",
    "at_t1":                "at_t1",
    "between_t1_t2":        "between_t1_t2",
    "post_t1_failed_hold":  "between_t1_t2",   # giveback from T1 zone = still between T1/T2
    "at_t2":                "at_t2",
    "post_t2":              "at_t2",             # extended past T2
    "overtime":             "overtime",
    "invalidated":          "invalidated",
}

# ── PHASE_WEIGHTS (§4 step 4) ─────────────────────────────────────────────────
# Exact copy of the table in oracle_spec.md §4:
#   base, trigger, validity, objective, pace, retention, overlay
# Weights sum to 1.00 for every phase (verified in tests).
PHASE_WEIGHTS: dict[str, dict[str, float]] = {
    "pre_trigger": {
        "base": 0.28, "trigger": 0.18, "validity": 0.26,
        "objective": 0.10, "pace": 0.12, "retention": 0.00, "overlay": 0.06,
    },
    "triggered_pre_t1": {
        "base": 0.10, "trigger": 0.10, "validity": 0.24,
        "objective": 0.28, "pace": 0.22, "retention": 0.00, "overlay": 0.06,
    },
    # post_t1_pre_t2 covers both at_t1 / between_t1_t2 lifecycle phases
    # (oracle_spec uses "post_t1_pre_t2" as the weight-table key)
    "post_t1_pre_t2": {
        "base": 0.08, "trigger": 0.04, "validity": 0.18,
        "objective": 0.26, "pace": 0.16, "retention": 0.22, "overlay": 0.06,
    },
    "post_t1_failed_hold": {
        "base": 0.10, "trigger": 0.02, "validity": 0.22,
        "objective": 0.20, "pace": 0.14, "retention": 0.26, "overlay": 0.06,
    },
    "post_t2": {
        "base": 0.04, "trigger": 0.00, "validity": 0.14,
        "objective": 0.20, "pace": 0.10, "retention": 0.38, "overlay": 0.14,
    },
    "overtime": {
        "base": 0.16, "trigger": 0.04, "validity": 0.32,
        "objective": 0.14, "pace": 0.28, "retention": 0.00, "overlay": 0.06,
    },
    "invalidated": {
        "base": 0.00, "trigger": 0.00, "validity": 1.00,
        "objective": 0.00, "pace": 0.00, "retention": 0.00, "overlay": 0.00,
    },
}

# ── weight-table key for each lifecycle phase ─────────────────────────────────
# oracle_spec §4 uses 7 phase-detection strings but 7 weight-table rows.
# at_t1 and between_t1_t2 both use the "post_t1_pre_t2" weight row unless
# T1 was hit but price fell back below the 50% midpoint (→ post_t1_failed_hold).
def _weight_key(phase: str) -> str:
    if phase in ("at_t1", "between_t1_t2"):
        return "post_t1_pre_t2"
    if phase == "at_t2":
        return "post_t2"
    return phase  # pre_trigger, triggered_pre_t1, post_t1_failed_hold, overtime, invalidated


# ── smoothstep helper (§4 step 5, pace component) ────────────────────────────
def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite interpolation between edge0 and edge1."""
    if edge1 <= edge0:
        return 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ===========================================================================
# Public API
# ===========================================================================

def compute_management_state(
    plan: dict,
    price_history: pd.DataFrame,
    asof: str,
    macro_stance: str | None = None,
    futures_chg: dict | None = None,
    prev_state: dict | None = None,
) -> dict:
    """Compute prophet.management_state/v1 for one trade plan.

    Parameters
    ----------
    plan : dict
        prophet.trade_plan/v1 artifact.  Required fields:
            id, direction, entry, invalidation, targets (list[float]),
            horizon_days, signal_date (ISO-8601 date of plan issuance).
        Optional: trigger (float), min_hold_days.
    price_history : pd.DataFrame
        OHLCV-style frame with at least a 'close' column and a DatetimeIndex
        (or 'date' column parseable to dates).  MUST be PIT-safe: all rows must
        be <= asof date.  Raises AssertionError if any future-dated row is found.
    asof : str
        Computation date as ISO-8601 string (YYYY-MM-DD or full ISO datetime).
        Defines "today" for all temporal calculations.  No wall-clock reads.
    macro_stance : str | None
        'bull' | 'bear' | 'neutral' | None — Oracle stance from app_settings.
    futures_chg : dict | None
        Intraday or prior-session % changes for index proxies.
        Keys: 'SPY', 'QQQ' (floats, e.g. 0.012 = +1.2%).
        OURS: nightly cadence — use prior close-to-close % changes (not live futures).
    prev_state : dict | None
        Previous call's output dict (prophet.management_state/v1).  Used to
        accumulate mfe/mae, persist first_*_ts, and apply EMA smoothing.
        On the first call for a trade, pass None.

    Returns
    -------
    dict
        prophet.management_state/v1 artifact.  Validated before return; raises
        ValueError if schema violations are found.

    Notes
    -----
    PIT guarantee: this function never calls datetime.now() or date.today().
    The `asof` parameter is the sole time anchor.
    """
    # ── 0. Resolve asof date ──────────────────────────────────────────────────
    asof_date = _parse_date(asof)

    # ── 0a. PIT assertion — reject any future-dated price rows ───────────────
    price_history = _prepare_price_history(price_history, asof_date)

    # ── 0b. Extract plan fields ───────────────────────────────────────────────
    plan_id        = str(plan.get("id", ""))
    direction_str  = str(plan.get("direction", "BULL")).upper()
    entry          = float(plan.get("entry") or 0.0)
    invalidation   = float(plan.get("invalidation") or 0.0)
    targets_raw    = plan.get("targets") or []
    targets        = [float(t) for t in targets_raw if t is not None]
    horizon_days   = int(plan.get("horizon_days") or 0)
    signal_date    = _parse_date(str(plan.get("signal_date") or plan.get("asof") or asof))
    trigger_price  = plan.get("trigger")
    if trigger_price is not None:
        trigger_price = float(trigger_price)

    # Base confidence: stored plan confidence or 60 if absent
    base_conf = float(plan.get("confidence") or 60.0)

    # ── 0c. Unpack prev_state accumulator fields ──────────────────────────────
    prev: dict[str, Any] = prev_state or {}
    prev_mfe: float = float(prev.get("_mfe", 0.0))
    prev_mae: float = float(prev.get("_mae", 0.0))
    first_trigger_ts: str | None = prev.get("_first_trigger_ts")
    first_t1_ts: str | None      = prev.get("_first_t1_ts")
    first_t2_ts: str | None      = prev.get("_first_t2_ts")
    prev_raw_conf: float | None  = prev.get("raw_confidence")
    prev_display_conf: float | None = prev.get("management_confidence")
    prev_phase: str | None       = prev.get("phase")

    # ── 1. Days elapsed ───────────────────────────────────────────────────────
    days_elapsed = max(0, (asof_date - signal_date).days)

    # ── 2. Geometry (§4 step 2) ───────────────────────────────────────────────
    dir_int = 1 if direction_str == "BULL" else -1

    # Current price = last available close at or before asof
    if price_history.empty:
        raise ValueError("price_history is empty — cannot compute geometry")
    price = float(price_history["close"].iloc[-1])

    t1 = targets[0] if len(targets) >= 1 else None
    t2 = targets[1] if len(targets) >= 2 else None
    t3 = targets[2] if len(targets) >= 3 else None

    # signed move: positive = favorable
    move = dir_int * (price - entry)

    # distance from stop (positive = still valid)
    dist_from_stop = dir_int * (price - invalidation)

    # risk = |entry - invalidation| (fall back to |t1 - entry| if no invalidation)
    if invalidation != 0.0 and t1 is not None:
        risk = abs(entry - invalidation)
    elif t1 is not None:
        risk = abs(t1 - entry)
    else:
        risk = max(abs(entry * 0.05), 1.0)   # 5% fallback

    d1 = abs(t1 - entry) if t1 is not None else None
    d2 = abs(t2 - entry) if t2 is not None else None
    d3 = abs(t3 - entry) if t3 is not None else None

    p1 = (move / d1) if (d1 and d1 > 0) else 0.0
    p2 = (move / d2) if (d2 and d2 > 0) else None
    p3 = (move / d3) if (d3 and d3 > 0) else None

    move_r        = move / risk if risk > 0 else 0.0
    dist_to_stop_r = dist_from_stop / risk if risk > 0 else 0.0
    dist_to_t1_r  = ((d1 - max(0.0, move)) / risk) if (d1 and risk > 0) else None
    dist_to_t2_r  = ((d2 - max(0.0, move)) / risk) if (d2 and risk > 0) else None

    # horizon fraction
    tau = (days_elapsed / horizon_days) if horizon_days > 0 else 0.0

    # ── 2a. Accumulate MFE / MAE across calls (prev_state cadence) ───────────
    # OURS: nightly cadence — mfe/mae accumulate call-over-call via prev_state,
    # not via browser in-memory tick state.  prev_state is the sole accumulator.
    mfe = max(prev_mfe, move)   # max favorable excursion (signed, positive = good)
    mae = min(prev_mae, move)   # max adverse excursion (signed, most negative)

    # Also accumulate max_progress_to_t1 for trigger detection
    max_p1: float = float(prev.get("_max_p1", 0.0))
    max_p1 = max(max_p1, p1)

    # ── 2b. Trigger state ────────────────────────────────────────────────────
    # Trigger is "hit" when price crosses the trigger level, or when p1 >= 0
    # (price is in the expected direction of travel past entry / trigger zone).
    trigger_hit = _evaluate_trigger(
        price, trigger_price, dir_int, p1,
        first_trigger_ts, asof_date,
    )
    if trigger_hit and first_trigger_ts is None:
        first_trigger_ts = asof

    # T1 / T2 hit detection
    t1_hit = (first_t1_ts is not None) or (p1 >= 1.0 and t1 is not None)
    t2_hit = (first_t2_ts is not None) or (p2 is not None and p2 >= 1.0 and t2 is not None)

    if t1_hit and first_t1_ts is None:
        first_t1_ts = asof
    if t2_hit and first_t2_ts is None:
        first_t2_ts = asof

    # ── 3. Phase detection (§4 step 3, priority order) ───────────────────────
    phase = _detect_phase(
        dist_from_stop=dist_from_stop,
        tau=tau,
        t1_hit=t1_hit,
        t2_hit=t2_hit,
        p1=p1,
        p2=p2,
        trigger_hit=trigger_hit,
        first_t1_ts=first_t1_ts,
        first_t2_ts=first_t2_ts,
    )

    # ── 4. Weights ────────────────────────────────────────────────────────────
    w = PHASE_WEIGHTS[_weight_key(phase)]

    # ── 5. Component scores — all normalized 0-1 ─────────────────────────────

    # 5a. Base norm: ratio of base_conf to ceiling (stable anchor)
    base_norm = _clamp(base_conf / 100.0, 0.0, 1.0)

    # 5b. Validity (§4 step 5) ─────────────────────────────────────────────────
    validity_01 = _compute_validity(dist_from_stop, risk)

    # 5c. Objective / Progress (§4 step 5) ────────────────────────────────────
    objective_01 = _compute_objective(
        p1=p1, p2=p2, t1_hit=t1_hit, t2_hit=t2_hit,
        has_t2=(t2 is not None),
    )

    # 5d. Pace (§4 step 5) ────────────────────────────────────────────────────
    pace_01 = _compute_pace(
        tau=tau, p1=p1, p2=p2, t1_hit=t1_hit, t2_hit=t2_hit,
        horizon_days=horizon_days, phase=phase,
    )

    # 5e. Retention (§4 step 5) ───────────────────────────────────────────────
    retention_01 = _compute_retention(
        move=move, mfe=mfe, p1=p1, phase=phase,
    )

    # 5f. Trigger zone score (§4 step 5) ──────────────────────────────────────
    trigger_score_01 = _compute_trigger_score(
        price=price, trigger_price=trigger_price,
        dir_int=dir_int, d1=d1, trigger_hit=trigger_hit,
    )

    # 5g. Overlay (§4 step 5) ─────────────────────────────────────────────────
    overlay_01 = _compute_overlay(
        trigger_hit=trigger_hit,
        direction_str=direction_str,
        macro_stance=macro_stance,
        futures_chg=futures_chg,
        price_history=price_history,
    )

    # 5h. Path quality penalty (§4 step 5) ────────────────────────────────────
    path_penalty = _compute_path_penalty(mae=mae, risk=risk, move=move)

    # ── 6. Weighted sum, bounds, EMA (§4 steps 6) ────────────────────────────
    raw_01 = (
        w["base"]      * base_norm
        + w["trigger"]   * trigger_score_01
        + w["validity"]  * validity_01
        + w["objective"] * objective_01
        + w["pace"]      * pace_01
        + w["retention"] * retention_01
        + w["overlay"]   * overlay_01
    )
    raw_score = (raw_01 - path_penalty) * 100.0

    # Phase-aware bounds (§4 step 6 table)
    floor_, ceil_ = _phase_bounds(
        phase=phase, base_conf=base_conf, p1=p1, p2=p2,
        tau=tau, ceiling=CONFIDENCE_CEILING,
    )

    raw_live_conf = _clamp(raw_score, floor_, ceil_)

    # Absolute ceiling guard
    raw_live_conf = min(raw_live_conf, CONFIDENCE_CEILING)

    # ── EMA smoothing (§4 step 6) ─────────────────────────────────────────────
    # OURS: nightly cadence — prev values come from prev_state dict, not browser
    # in-memory state.  The EMA chain is maintained across nightly calls.
    display_conf = _apply_ema(
        raw_live_conf=raw_live_conf,
        prev_raw=prev_raw_conf,
        prev_display=prev_display_conf,
        prev_phase=prev_phase,
        phase=phase,
    )

    # Absolute ceiling on display conf too
    display_conf = min(display_conf, float(CONFIDENCE_CEILING))

    # ── 7. Change reason (§4 diagnostics) ────────────────────────────────────
    change_reason = _build_change_reason(
        phase=phase, prev_phase=prev_phase,
        raw_live_conf=raw_live_conf, prev_raw=prev_raw_conf,
        validity=validity_01, pace=pace_01, retention=retention_01, overlay=overlay_01,
        p1=p1,
    )

    # ── 8. Human-readable state (§7 map) ─────────────────────────────────────
    human_state = _human_state(phase=phase, p1=p1, trigger_hit=trigger_hit, tau=tau)

    # ── 9. Recommended action ─────────────────────────────────────────────────
    recommended_action = _recommended_action(
        phase=phase, trigger_hit=trigger_hit,
    )

    # ── 10. Static R/R at issuance + grade (§13) ─────────────────────────────
    rr_grade = None
    rr_ratio = None
    if t1 is not None and entry != 0.0:
        reward = dir_int * (t1 - entry)
        risk_rr = dir_int * (entry - invalidation) if invalidation != 0.0 else None
        if risk_rr and risk_rr > 0:
            rr_ratio = round(reward / risk_rr, 3)
            rr_grade = _rr_grade(rr_ratio)

    # ── 11. Build output dict ─────────────────────────────────────────────────
    # Map internal detection phase → contract schema phase (OPTIONS_SENSOR_CONTRACT §6).
    # The detection phase drives all internal logic; the schema phase is for consumers.
    schema_phase = _DETECTION_TO_SCHEMA_PHASE.get(phase, phase)

    out: dict = {
        "schema":                "prophet.management_state/v1",
        "id":                    plan_id,
        "asof":                  asof,
        "phase":                 schema_phase,
        "detection_phase":       phase,         # internal; not in schema validation
        "management_confidence": round(display_conf, 1),
        "raw_confidence":        round(raw_live_conf, 1),
        "delta_vs_base":         round(display_conf - base_conf, 1),
        "recommended_action":    recommended_action,
        "human_state":           human_state,
        "components": {
            "validity":  round(validity_01  * 100, 1),
            "progress":  round(objective_01 * 100, 1),
            "pace":      round(pace_01      * 100, 1),
            "retention": round(retention_01 * 100, 1),
            "overlay":   round(overlay_01   * 100, 1),
        },
        "geometry": {
            "dist_to_stop_r":  round(dist_to_stop_r, 3)       if dist_to_stop_r is not None else None,
            "dist_to_t1_r":    round(dist_to_t1_r, 3)         if dist_to_t1_r   is not None else None,
            "dist_to_t2_r":    round(dist_to_t2_r, 3)         if dist_to_t2_r   is not None else None,
            "horizon_pct_used": round(tau * 100, 1),
            "p1":               round(p1, 4),
            "p2":               round(p2, 4)  if p2 is not None else None,
            "p3":               round(p3, 4)  if p3 is not None else None,
            "move_r":           round(move_r, 3),
            "mfe_r":            round(mfe / risk, 3) if risk > 0 else 0.0,
            "mae_r":            round(mae / risk, 3) if risk > 0 else 0.0,
        },
        "rr_ratio":       rr_ratio,
        "rr_grade":       rr_grade,
        "change_reason":  change_reason,
        "confidence_ceiling": CONFIDENCE_CEILING,
        "authority":           "trade-management-only-NOT-pick-rank",
        "authority_tier":      AUTHORITY_DISPLAY,
        "reliability": {
            "management_confidence": "display — no forward ledger has passed yet",
            "recommended_action":    "display — narrate, not authoritative order",
            "ceiling":               f"hard cap at {CONFIDENCE_CEILING} — uncertainty is honest",
        },
        # ── accumulator fields (persisted in state, consumed on next call) ────
        "_mfe":               mfe,
        "_mae":               mae,
        "_max_p1":            max_p1,
        "_first_trigger_ts":  first_trigger_ts,
        "_first_t1_ts":       first_t1_ts,
        "_first_t2_ts":       first_t2_ts,
        "days_elapsed":       days_elapsed,
        "tau":                round(tau, 4),
    }

    # Validate before returning
    errs = validate_management_state(out)
    if errs:
        raise ValueError(f"compute_management_state: schema violations: {errs}")

    return out


# ===========================================================================
# Phase detection (§4 step 3)
# ===========================================================================

def _detect_phase(
    dist_from_stop: float,
    tau: float,
    t1_hit: bool,
    t2_hit: bool,
    p1: float,
    p2: float | None,
    trigger_hit: bool,
    first_t1_ts: str | None,
    first_t2_ts: str | None,
) -> str:
    """Priority-ordered phase detection per oracle_spec §4 step 3.

    Priority:
    1. invalidated   — stop breached (dist_from_stop <= 0)
    2. overtime      — tau > 1.0 AND T1 never hit
    3. at_t2         — T2 hit (first_t2_ts set, p2 >= 1.0)
    4. post_t1_failed_hold — T1 was hit but p1 < 0.50 (gave back >50% of T1 move)
    5. at_t1 / between_t1_t2 — T1 hit, p1 >= 0.50
    6. triggered_pre_t1 — trigger confirmed, T1 not yet hit
    7. pre_trigger   — default
    """
    if dist_from_stop <= 0:
        return "invalidated"
    if tau > 1.0 and not t1_hit:
        return "overtime"
    if t2_hit and p2 is not None and p2 >= 1.0:
        return "at_t2"
    if t1_hit and p1 < 0.50:
        return "post_t1_failed_hold"
    if t1_hit:
        # at_t1: p1 >= 1.0 (holding at or above T1)
        # between_t1_t2: T1 hit, advanced past T1, heading to T2
        if p2 is not None and p1 >= 1.0:
            return "between_t1_t2"
        return "at_t1"
    if trigger_hit:
        return "triggered_pre_t1"
    return "pre_trigger"


def _evaluate_trigger(
    price: float,
    trigger_price: float | None,
    dir_int: int,
    p1: float,
    first_trigger_ts: str | None,
    asof_date: date,
) -> bool:
    """Return True if the trigger zone has been entered (or was entered previously)."""
    if first_trigger_ts is not None:
        return True
    if trigger_price is not None:
        # BULL: trigger hit when price >= trigger_price
        # BEAR: trigger hit when price <= trigger_price
        if dir_int == 1:
            return price >= trigger_price
        else:
            return price <= trigger_price
    # No explicit trigger: use p1 >= 0 (price has not pulled back from entry)
    return p1 >= 0.0


# ===========================================================================
# Component: Validity (§4 step 5)
# ===========================================================================

def _compute_validity(dist_from_stop: float, risk: float) -> float:
    """Validity score 0-1: how far from stop.

    §4 step 5 — steeper curve near the danger zone.
    ratio = clamp(dist_from_stop / risk, 0, 1)
    if ratio > 0.25: validity = ratio^1.35
    else (danger):   validity = base_danger * (ratio / 0.25)^2.2
    where base_danger = 0.25^1.35
    """
    if risk <= 0:
        return 0.0
    ratio = _clamp(dist_from_stop / risk, 0.0, 1.0)
    if ratio > 0.25:
        return math.pow(ratio, 1.35)
    else:
        base_danger = math.pow(0.25, 1.35)   # ≈ 0.146
        danger_ratio = ratio / 0.25
        return base_danger * math.pow(danger_ratio, 2.2)


# ===========================================================================
# Component: Objective / Progress (§4 step 5)
# ===========================================================================

def _compute_objective(
    p1: float,
    p2: float | None,
    t1_hit: bool,
    t2_hit: bool,
    has_t2: bool,
) -> float:
    """Progress-to-target score 0-1.

    §4 step 5:
    • Before T1: 0.68 * clamp(p1,0,1)^0.75
    • T1 hit (no T2): 0.35-0.65 range minus giveback penalty
    • T1-to-T2 leg: 0.40-0.90 based on leg progress
    • T2 hit: 0.60-1.00
    Giveback penalty: if giveback_frac > 0.4: penalty = (giveback_frac - 0.4) * 0.3
    """
    if t2_hit:
        # Post T2 region: 0.60-1.00 based on p2
        p2c = _clamp(p2 or 1.0, 1.0, 2.0)
        leg = _clamp((p2c - 1.0), 0.0, 1.0)
        return 0.60 + 0.40 * leg

    if t1_hit and has_t2:
        # T1-to-T2 leg: 0.40-0.90 based on p2 progress
        p2_val = _clamp(p2 or 0.0, 0.0, 1.0)
        base = 0.40 + 0.50 * p2_val

        # Giveback penalty: fraction of T2 leg given back
        giveback_frac = _clamp(1.0 - (p2 or 0.0), 0.0, 1.0) if p2 is not None else 0.0
        # Giveback here is relative to T1 base
        t1_giveback = _clamp(1.0 - p1, 0.0, 1.0) if p1 < 1.0 else 0.0
        if t1_giveback > 0.4:
            penalty = (t1_giveback - 0.4) * 0.3
            base = base * (1.0 - penalty)
        return _clamp(base, 0.0, 1.0)

    if t1_hit and not has_t2:
        # T1 hit, no T2: 0.35-0.65 based on how firmly held
        hold_quality = _clamp(p1, 0.5, 1.2)
        base = 0.35 + 0.30 * _clamp((hold_quality - 0.5) / 0.7, 0.0, 1.0)

        # Giveback penalty
        giveback_frac = _clamp(1.0 - p1, 0.0, 1.0)
        if giveback_frac > 0.4:
            penalty = (giveback_frac - 0.4) * 0.3
            base = base * (1.0 - penalty)
        return _clamp(base, 0.0, 1.0)

    # Before T1
    p1c = _clamp(p1, 0.0, 1.0)
    return 0.68 * math.pow(p1c, 0.75) if p1c > 0 else 0.0


# ===========================================================================
# Component: Pace (§4 step 5)
# ===========================================================================

def _compute_pace(
    tau: float,
    p1: float,
    p2: float | None,
    t1_hit: bool,
    t2_hit: bool,
    horizon_days: int,
    phase: str,
) -> float:
    """Pace score 0-1: progress vs. expected schedule.

    §4 step 5:
    Schedule benchmarks (horizon-length dependent):
      horizonDays < 14:  t1ExpectedBy=0.45, t2ExpectedBy=0.80
      horizonDays < 60:  t1ExpectedBy=0.55, t2ExpectedBy=0.90
      else:              t1ExpectedBy=0.65, t2ExpectedBy=0.95

    expectedT1 = smoothstep(0.05, t1ExpectedBy, tau)
    paceT1 = clamp(1 - max(0, expectedT1 - clamp(p1,0,1)), 0, 1.0)
    Before T1: pace = 0.80*paceT1 + 0.20*paceT2
    After T1:  pace = 0.40*paceT1 + 0.60*paceT2
    Overtime: max(0, 0.3 - shortfall*0.6)
    """
    if phase == "overtime":
        shortfall = _clamp(tau - 1.0, 0.0, 1.0)
        return max(0.0, 0.3 - shortfall * 0.6)

    if phase == "invalidated":
        return 0.0

    # Horizon-length schedule
    if horizon_days < 14:
        t1_exp, t2_exp = 0.45, 0.80
    elif horizon_days < 60:
        t1_exp, t2_exp = 0.55, 0.90
    else:
        t1_exp, t2_exp = 0.65, 0.95

    expected_t1 = _smoothstep(0.05, t1_exp, tau)
    p1c = _clamp(p1, 0.0, 1.0)
    pace_t1 = _clamp(1.0 - max(0.0, expected_t1 - p1c), 0.0, 1.0)

    expected_t2 = _smoothstep(0.05, t2_exp, tau)
    p2c = _clamp(p2 or 0.0, 0.0, 1.0)
    pace_t2 = _clamp(1.0 - max(0.0, expected_t2 - p2c), 0.0, 1.0)

    # Blend depends on whether T1 hit
    if t1_hit:
        return 0.40 * pace_t1 + 0.60 * pace_t2
    else:
        return 0.80 * pace_t1 + 0.20 * pace_t2


# ===========================================================================
# Component: Retention (§4 step 5)
# ===========================================================================

def _compute_retention(
    move: float,
    mfe: float,
    p1: float,
    phase: str,
) -> float:
    """Retention score 0-1: how much of MFE is retained.

    §4 step 5:
    retained = clamp(move / mfe, 0, 1)
    post_t1_failed_hold amplification:
      if p1 < 0.50: ampFactor = 1.6
      elif p1 < 0.70: ampFactor = 1.3
    pre_trigger / triggered_pre_t1: return 0.5 (neutral)
    """
    if phase in ("pre_trigger", "triggered_pre_t1"):
        return 0.5   # neutral

    if mfe <= 0:
        # No positive excursion recorded yet
        return 0.5 if move >= 0 else _clamp(0.5 + move / 100.0, 0.0, 0.5)

    retained = _clamp(move / mfe, 0.0, 1.0)

    # Amplification for failed-hold (steeper degradation below 0.5)
    if phase == "post_t1_failed_hold":
        if p1 < 0.50:
            amp = 1.6
        elif p1 < 0.70:
            amp = 1.3
        else:
            amp = 1.0
        retained = _clamp(retained * amp, 0.0, 1.0)

    return retained


# ===========================================================================
# Component: Trigger Zone Score (§4 step 5)
# ===========================================================================

def _compute_trigger_score(
    price: float,
    trigger_price: float | None,
    dir_int: int,
    d1: float | None,
    trigger_hit: bool,
) -> float:
    """Continuous trigger zone score 0-1.

    §4 step 5:
    If past trigger:  score = 0.65 + 0.23 * depthFrac  (0.65-0.88)
    If approaching:   score = 0.40 + 0.15 * approachFrac  (0.40-0.55)
    No trigger:       0.5
    """
    if trigger_price is None or d1 is None or d1 <= 0:
        return 0.5

    if trigger_hit:
        # depth past trigger as fraction of 15% of d1
        past_trigger = dir_int * (price - trigger_price)
        if past_trigger < 0:
            past_trigger = 0.0
        depth_frac = _clamp(past_trigger / (d1 * 0.15), 0.0, 1.0)
        return 0.65 + 0.23 * depth_frac

    # Approaching
    dist_to_trigger = dir_int * (trigger_price - price)
    if dist_to_trigger < 0:
        dist_to_trigger = 0.0
    approach_frac = _clamp(1.0 - (dist_to_trigger / d1), 0.0, 1.0)
    return 0.40 + 0.15 * approach_frac


# ===========================================================================
# Component: Overlay (§4 step 5)
# ===========================================================================

def _compute_overlay(
    trigger_hit: bool,
    direction_str: str,
    macro_stance: str | None,
    futures_chg: dict | None,
    price_history: pd.DataFrame,
) -> float:
    """Macro + market conditions composite 0-1.

    §4 step 5:
    overlay = 0.5 base
    + 0.06 trigger confirmed
    ± 0.03 momentum pulse (aligned daily move)
    + 0.08 / -0.20 macro regime aligned / opposed
    futures adverse: max(-0.14, alignedFut * 0.04)
    futures tailwind: min(0.05, alignedFut * 0.015)

    OURS: momentum pulse — the spec uses live last-print-to-last-print within a
    session.  Nightly cadence substitutes last close-to-close daily % change from
    the price_history DataFrame.  The sign interpretation (aligned vs. opposing)
    is identical to the browser version.
    """
    overlay = 0.5

    if trigger_hit:
        overlay += 0.06

    # Momentum pulse from daily close-to-close
    # OURS: nightly cadence — last row close vs second-to-last row close
    daily_chg_pct = 0.0
    if len(price_history) >= 2:
        c_now  = float(price_history["close"].iloc[-1])
        c_prev = float(price_history["close"].iloc[-2])
        if c_prev != 0:
            daily_chg_pct = (c_now - c_prev) / abs(c_prev)

    dir_int = 1 if direction_str == "BULL" else -1
    aligned_move = dir_int * daily_chg_pct
    if abs(daily_chg_pct) > 0.003:   # 0.3% threshold (same as spec's 0.3)
        overlay += 0.03 if aligned_move > 0 else -0.03

    # Macro stance alignment
    if macro_stance is not None:
        stance_lower = macro_stance.lower()
        is_bull = (direction_str == "BULL")
        if (is_bull and stance_lower == "bull") or (not is_bull and stance_lower == "bear"):
            overlay += 0.08
        elif (is_bull and stance_lower == "bear") or (not is_bull and stance_lower == "bull"):
            overlay -= 0.20

    # Futures / index overlay (§4 step 5, V1 F9 adaptation)
    # OURS: nightly — uses prior close-to-close % changes from futures_chg dict.
    if futures_chg:
        values = [v for v in futures_chg.values() if v is not None]
        if values:
            avg_fut_chg = sum(values) / len(values)
            aligned_fut = dir_int * avg_fut_chg
            if aligned_fut < 0:
                overlay += max(-0.14, aligned_fut * 0.04)
            elif aligned_fut > 0:
                overlay += min(0.05, aligned_fut * 0.015)

    return _clamp(overlay, 0.0, 1.0)


# ===========================================================================
# Component: Path Quality Penalty (§4 step 5)
# ===========================================================================

def _compute_path_penalty(mae: float, risk: float, move: float) -> float:
    """Path quality penalty subtracted from raw_01 before multiplying by 100.

    §4 step 5:
    maeFrac = clamp(|mae| / risk, 0, 1.25)
    if move > 0: penalty = 4 * maeFrac^1.2
    Deep recovery extra: +3 * clamp((|mae|/risk - 0.8)/0.2, 0, 1) if |mae|/risk > 0.8
    pathPenalty /= 100 (normalized for subtraction from raw_01)
    """
    if risk <= 0:
        return 0.0
    mae_abs = abs(mae)
    mae_frac = _clamp(mae_abs / risk, 0.0, 1.25)

    penalty = 0.0
    if move > 0:
        penalty = 4.0 * math.pow(mae_frac, 1.2)
        # Deep recovery extra term
        if mae_frac > 0.8:
            deep = _clamp((mae_frac - 0.8) / 0.2, 0.0, 1.0)
            penalty += 3.0 * deep

    return penalty / 100.0  # normalize to 0-1 range for subtraction from raw_01


# ===========================================================================
# Phase-aware bounds (§4 step 6)
# ===========================================================================

def _phase_bounds(
    phase: str,
    base_conf: float,
    p1: float,
    p2: float | None,
    tau: float,
    ceiling: int,
) -> tuple[float, float]:
    """Return (floor, ceiling) for the given phase.

    §4 step 6 phase-aware bounds table (faithfully ported):

    invalidated:          floor=8, ceil=16
    pre_trigger:          floor=max(25, base-30), ceil=min(CAP, base+8)
    triggered_pre_t1:     floor=max(22, base-36), ceil=min(CAP, max(base+16, 82))
                          +4 if p1>0.85; +2 if p1>0.65
    post_t1_pre_t2 (no T2): floor=max(52, base-10), ceil=min(CAP, base+10)
    post_t1_pre_t2 (T2):    floor=max(36, base-20), ceil=min(CAP, max(base+18, 86))
                             +2 if p2>0.5
    post_t2:              floor=max(48, base-10), ceil=CAP
    post_t1_failed_hold:  floor=max(28, base-28), ceil=min(82, base+4) minus phase-deductions
    overtime (p1<0.3):    floor=max(20, base-40), ceil=min(CAP, max(35, base-20))
    overtime (p1 0.3-0.6):floor=max(20, base-40), ceil=min(CAP, max(42, base-14))
    overtime (p1>0.6):    floor=max(20, base-40), ceil=min(CAP, max(50, base-8))

    Additional guards:
    if tau > 1 AND p1 < 0.75: ceil = min(ceil, max(45, base-12))  [overtime guard]
    if tau > 0.3 AND p1 < 0.05: ceil = min(ceil, max(50, base-8)) [pre_trigger stall guard]
    """
    cap = float(ceiling)

    if phase == "invalidated":
        return (8.0, 16.0)

    if phase == "pre_trigger":
        fl = max(25.0, base_conf - 30.0)
        ce = min(cap, base_conf + 8.0)
        ce = _apply_stall_guard(ce, tau, p1, base_conf)
        return (fl, ce)

    if phase == "triggered_pre_t1":
        fl = max(22.0, base_conf - 36.0)
        ce = min(cap, max(base_conf + 16.0, 82.0))
        if p1 > 0.85:
            ce = min(cap, ce + 4.0)
        elif p1 > 0.65:
            ce = min(cap, ce + 2.0)
        return (fl, ce)

    if phase in ("at_t1", "between_t1_t2"):
        has_t2 = (p2 is not None)
        if not has_t2:
            fl = max(52.0, base_conf - 10.0)
            ce = min(cap, base_conf + 10.0)
        else:
            fl = max(36.0, base_conf - 20.0)
            ce = min(cap, max(base_conf + 18.0, 86.0))
            if p2 is not None and p2 > 0.5:
                ce = min(cap, ce + 2.0)
        return (fl, ce)

    if phase == "post_t1_failed_hold":
        fl = max(28.0, base_conf - 28.0)
        ce = min(82.0, base_conf + 4.0)
        # Phase-deductions by p1 level (deeper giveback = tighter ceiling)
        if p1 < 0.0:
            ce -= 10.0
        elif p1 < 0.25:
            ce -= 6.0
        elif p1 < 0.50:
            ce -= 3.0
        ce = max(fl, ce)
        return (fl, ce)

    if phase == "at_t2":
        fl = max(48.0, base_conf - 10.0)
        ce = cap
        return (fl, ce)

    if phase == "overtime":
        fl = max(20.0, base_conf - 40.0)
        if p1 < 0.3:
            ce = min(cap, max(35.0, base_conf - 20.0))
        elif p1 < 0.6:
            ce = min(cap, max(42.0, base_conf - 14.0))
        else:
            ce = min(cap, max(50.0, base_conf - 8.0))
        ce = _apply_overtime_guard(ce, tau, p1, base_conf)
        return (fl, ce)

    # Fallback (should not happen)
    return (0.0, cap)


def _apply_overtime_guard(ceil_: float, tau: float, p1: float, base_conf: float) -> float:
    """§4 step 6: if tau > 1 AND p1 < 0.75: ceil = min(ceil, max(45, base-12))."""
    if tau > 1.0 and p1 < 0.75:
        return min(ceil_, max(45.0, base_conf - 12.0))
    return ceil_


def _apply_stall_guard(ceil_: float, tau: float, p1: float, base_conf: float) -> float:
    """§4 step 6: if tau > 0.3 AND p1 < 0.05: ceil = min(ceil, max(50, base-8))."""
    if tau > 0.3 and p1 < 0.05:
        return min(ceil_, max(50.0, base_conf - 8.0))
    return ceil_


# ===========================================================================
# EMA smoothing (§4 step 6)
# ===========================================================================

def _apply_ema(
    raw_live_conf: float,
    prev_raw: float | None,
    prev_display: float | None,
    prev_phase: str | None,
    phase: str,
) -> float:
    """EMA smoothing of display confidence.

    §4 step 6:
    Phase changed: alpha = 0.85 (fast response to phase transitions)
    Same phase:    alpha = 0.45 (gradual)
    Freeze if |raw - prev_raw| < 0.03 (3 points = negligible shift)

    OURS: nightly cadence — prev values come from prev_state dict (not browser
    memory).  On first call (prev_display is None), return raw_live_conf directly.
    """
    if prev_display is None:
        return raw_live_conf

    # Freeze check
    if prev_raw is not None and abs(raw_live_conf - prev_raw) < 0.03:
        return prev_display

    alpha = 0.85 if (phase != prev_phase) else 0.45
    return (1.0 - alpha) * prev_display + alpha * raw_live_conf


# ===========================================================================
# Change reason (§4 diagnostics)
# ===========================================================================

def _build_change_reason(
    phase: str,
    prev_phase: str | None,
    raw_live_conf: float,
    prev_raw: float | None,
    validity: float,
    pace: float,
    retention: float,
    overlay: float,
    p1: float,
) -> str:
    """Build a human-readable change reason string.

    §4 diagnostics:
    Phase transitions take priority.
    Then component-delta reasons (thresholds ~5-8 pts).
    Fallback: "Improving" | "Weakening"
    """
    # Phase transitions
    if prev_phase is not None and phase != prev_phase:
        transition_map = {
            ("pre_trigger",   "triggered_pre_t1"):    "Trigger Confirmed",
            ("triggered_pre_t1", "at_t1"):             "T1 Target Hit",
            ("triggered_pre_t1", "between_t1_t2"):     "T1 Target Hit",
            ("at_t1",         "at_t2"):                "T2 Target Hit",
            ("between_t1_t2", "at_t2"):                "T2 Target Hit",
            ("triggered_pre_t1", "overtime"):           "Overtime — Horizon Exceeded",
            ("pre_trigger",   "overtime"):              "Overtime — Horizon Exceeded",
            ("at_t1",         "post_t1_failed_hold"):  "Giving Back Gains",
            ("between_t1_t2", "post_t1_failed_hold"):  "Giving Back Gains",
            ("triggered_pre_t1", "invalidated"):        "Stop Level Breached",
            ("pre_trigger",   "invalidated"):           "Stop Level Breached",
            ("at_t1",         "invalidated"):           "Stop Level Breached",
        }
        key = (prev_phase, phase)
        if key in transition_map:
            return transition_map[key]
        return f"Phase: {prev_phase} → {phase}"

    if prev_raw is None:
        return ""

    delta = raw_live_conf - prev_raw
    if abs(delta) < 2.0:
        return ""

    # Component-based reasons
    if validity < 0.25:
        return "Nearing Invalidation"
    if validity > 0.75:
        return "Moving Away from Stop"
    if pace < 0.35:
        return "Falling Behind Schedule"
    if pace > 0.75:
        return "Ahead of Schedule"
    if retention < 0.30:
        return "Giving Back Gains"
    if p1 > 0.85:
        return "Extending Gains"
    if overlay < 0.35:
        return "Macro Headwind"
    if overlay > 0.65:
        return "Macro Tailwind"

    return "Improving" if delta > 0 else "Weakening"


# ===========================================================================
# Human state (§7 map)
# ===========================================================================

def _human_state(phase: str, p1: float, trigger_hit: bool, tau: float) -> str:
    """Map phase + context to a human-readable state string (§7).

    Based on the phase map in oracle_spec §7:
    pre_trigger       → "Awaiting Trigger" / "Approaching Trigger"
    triggered_pre_t1  → "Advancing Cleanly" / "On Track" / "Needs Follow-Through" / "Stalling"
    at_t1 / between   → "T1 Hit — Holding" / "Advancing to T2" / "Giveback Warning"
    post_t1_failed_hold → (drawdown zone)
    at_t2             → "High Conviction" / "Extended — Watch Giveback"
    overtime          → "Overtime Stall"
    invalidated       → "Invalidated"
    """
    if phase == "invalidated":
        return "Invalidated"
    if phase == "overtime":
        return "Overtime Stall"
    if phase == "at_t2":
        return "High Conviction" if p1 < 1.5 else "Extended — Watch Giveback"
    if phase == "post_t1_failed_hold":
        if p1 < 0.25:
            return "Deep Giveback — Reassess"
        return "T1 Giveback Warning"
    if phase in ("at_t1", "between_t1_t2"):
        if p1 > 1.0:
            return "Advancing to T2"
        return "T1 Hit — Holding"
    if phase == "triggered_pre_t1":
        if p1 > 0.65:
            return "Advancing Cleanly"
        elif p1 > 0.30:
            return "On Track"
        elif tau > 0.3 and p1 < 0.1:
            return "Stalling"
        return "Needs Follow-Through"
    # pre_trigger
    if tau > 0.15:
        return "Approaching Trigger"
    return "Awaiting Trigger"


# ===========================================================================
# Recommended action
# ===========================================================================

def _recommended_action(phase: str, trigger_hit: bool) -> str:
    """Map phase to recommended_action string.

    pre_trigger → wait / enter (when trigger confirmed)
    advancing   → hold
    giveback / failed_hold → trim
    post_t2     → trail
    invalidated → invalidated
    """
    if phase == "invalidated":
        return "invalidated"
    if phase == "pre_trigger":
        return "enter" if trigger_hit else "wait"
    if phase in ("triggered_pre_t1", "at_t1", "between_t1_t2"):
        return "hold"
    if phase == "post_t1_failed_hold":
        return "trim"
    if phase == "at_t2":
        return "trail"
    if phase == "overtime":
        return "trim"
    return "hold"


# ===========================================================================
# Static R/R grade (§13)
# ===========================================================================

def _rr_grade(rr: float) -> str:
    """Grade thresholds from oracle_spec §13."""
    if rr >= 4.0:
        return "EXCEPTIONAL"
    if rr >= 3.0:
        return "EXCELLENT"
    if rr >= 2.0:
        return "FAVORABLE"
    if rr >= 1.0:
        return "ACCEPTABLE"
    if rr >= 0.5:
        return "UNFAVORABLE"
    return "POOR"


# ===========================================================================
# Helpers: date parsing + price history preparation
# ===========================================================================

def _parse_date(s: str) -> date:
    """Parse ISO-8601 date string to date.  No wall-clock reads."""
    if not s:
        raise ValueError("empty date string")
    # Accept YYYY-MM-DD or full ISO datetime
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        raise ValueError(f"Cannot parse date from {s!r}")


def _prepare_price_history(df: pd.DataFrame, asof_date: date) -> pd.DataFrame:
    """Normalise and PIT-assert the price history DataFrame.

    Requirements:
    - Must have a 'close' column.
    - Index or 'date' column must be parseable to dates.
    - All rows must be <= asof_date (PIT guarantee).

    Returns a DataFrame with a DatetimeIndex sorted ascending, filtered to asof_date.
    """
    df = df.copy()

    # Normalise index
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df.index = pd.to_datetime(df["date"])
        elif "Date" in df.columns:
            df.index = pd.to_datetime(df["Date"])
        else:
            # Try coercing the existing index
            df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    # Rename column for consistent access
    col_map = {c: c.lower() for c in df.columns}
    df = df.rename(columns=col_map)

    if "close" not in df.columns:
        raise ValueError("price_history must contain a 'close' column")

    # PIT assertion — all rows must be <= asof_date
    future_rows = df[df.index.date > asof_date]
    assert future_rows.empty, (
        f"PIT violation: price_history contains {len(future_rows)} row(s) dated "
        f"after asof={asof_date}.  First offender: {future_rows.index[0].date()}"
    )

    # Filter to rows on or before asof
    df = df[df.index.date <= asof_date]
    return df
