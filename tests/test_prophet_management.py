"""tests/test_prophet_management.py — Prophet Management-Confidence Engine tests.

Package 6 — engine/prophet_management.py (oracle_spec.md §4 V2 port).

Coverage (≥40 tests):
  1.  PHASE_WEIGHTS sum to 1.00 for every phase.
  2.  Phase transitions: pre_trigger → triggered_pre_t1 → at_t1 → at_t2.
  3.  Phase: invalidated on stop breach.
  4.  Phase: overtime on horizon lapse without T1.
  5.  Phase: post_t1_failed_hold on giveback > 50%.
  6.  Bounds enforcement: floor respected in every phase.
  7.  Bounds enforcement: ceiling 92 never exceeded in any scenario.
  8.  EMA smoothing: alpha 0.85 on phase change, 0.45 same phase.
  9.  EMA freeze: |raw - prev_raw| < 0.03 → display_conf unchanged.
  10. mfe/mae accumulation across sequential calls.
  11. Determinism: same inputs twice → identical output.
  12. PIT assertion: future-dated price row → AssertionError.
  13. Validator round-trip via validate_management_state.
  14. Static R/R grade thresholds (§13).
  15. Recommended action mapping per phase.
  16. Validity component: danger zone (< 0.25 ratio) steeper curve.
  17. Objective component: pre-T1 curve, T1-hit with T2, post-T2.
  18. Pace component: horizon-scaled schedule (< 14d, < 60d, else).
  19. Retention neutral at 0.5 for pre_trigger / triggered_pre_t1.
  20. Trigger zone score: approaching vs. past trigger.
  21. Overlay: macro tailwind / headwind adjustments.
  22. Path quality penalty: deep MAE adds penalty.
  23. Overtime guard: tau > 1 AND p1 < 0.75 caps ceiling.
  24. Pre-trigger stall guard: tau > 0.3 AND p1 < 0.05 caps ceiling.
  25. Output dict contains all required prophet.management_state/v1 fields.
  26. Schema field = "prophet.management_state/v1".
  27. Confidence ceiling constant = 92.
  28. First call (prev_state=None) returns valid raw result without EMA drift.
  29. BEAR direction geometry: move is positive when price falls.
  30. Human state strings correct for each phase.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from engine.options_structure import validate_management_state, MANAGEMENT_CONFIDENCE_CEILING
from engine.prophet_management import (
    CONFIDENCE_CEILING,
    PHASE_WEIGHTS,
    _apply_ema,
    _clamp,
    _compute_objective,
    _compute_pace,
    _compute_path_penalty,
    _compute_retention,
    _compute_trigger_score,
    _compute_validity,
    _detect_phase,
    _human_state,
    _phase_bounds,
    _recommended_action,
    _rr_grade,
    _smoothstep,
    compute_management_state,
)


# ===========================================================================
# Helpers
# ===========================================================================

_ENTRY   = 100.0
_T1      = 115.0
_T2      = 130.0
_INVAL   = 90.0
_HORIZ   = 60
_SIGNAL_DATE = "2026-01-01"


def _make_plan(
    direction: str = "BULL",
    entry: float = _ENTRY,
    t1: float = _T1,
    t2: float | None = _T2,
    inval: float = _INVAL,
    horizon_days: int = _HORIZ,
    trigger: float | None = None,
    confidence: float = 60.0,
    signal_date: str = _SIGNAL_DATE,
) -> dict:
    targets = [t1]
    if t2 is not None:
        targets.append(t2)
    return {
        "id":            "test-plan-001",
        "schema":        "prophet.trade_plan/v1",
        "asof":          signal_date + "T00:00:00Z",
        "asset":         "TEST",
        "direction":     direction,
        "entry":         entry,
        "invalidation":  inval,
        "targets":       targets,
        "horizon_days":  horizon_days,
        "trigger":       trigger,
        "confidence":    confidence,
        "signal_date":   signal_date,
        "source_engines": ["neural_web"],
    }


def _make_prices(
    start: str,
    closes: list[float],
) -> pd.DataFrame:
    """Build a price DataFrame from a list of closes starting at `start`."""
    dates = pd.date_range(start=start, periods=len(closes), freq="B")
    return pd.DataFrame({"close": closes}, index=dates)


def _prices_flat(asof: str, days: int, price: float = 100.0) -> pd.DataFrame:
    """Flat price history ending at asof."""
    closes = [price] * days
    start  = (date.fromisoformat(asof) - timedelta(days=days - 1)).isoformat()
    return _make_prices(start, closes)


def _run(
    plan: dict,
    price: float = 100.0,
    asof_delta_days: int = 10,
    macro_stance: str | None = None,
    futures_chg: dict | None = None,
    prev_state: dict | None = None,
) -> dict:
    """Quick wrapper: build price history and call compute_management_state."""
    signal_date = plan.get("signal_date", _SIGNAL_DATE)
    asof_d = date.fromisoformat(signal_date) + timedelta(days=asof_delta_days)
    asof   = asof_d.isoformat()
    prices = _make_prices(signal_date, [price] * (asof_delta_days + 1))
    prices = prices[prices.index.date <= asof_d]
    return compute_management_state(
        plan=plan,
        price_history=prices,
        asof=asof,
        macro_stance=macro_stance,
        futures_chg=futures_chg,
        prev_state=prev_state,
    )


# ===========================================================================
# 1. PHASE_WEIGHTS integrity
# ===========================================================================

class TestPhaseWeightsIntegrity:
    def test_all_phases_present(self):
        expected = {
            "pre_trigger", "triggered_pre_t1", "post_t1_pre_t2",
            "post_t1_failed_hold", "post_t2", "overtime", "invalidated",
        }
        assert set(PHASE_WEIGHTS.keys()) == expected

    @pytest.mark.parametrize("phase", list(PHASE_WEIGHTS.keys()))
    def test_weights_sum_to_one(self, phase: str):
        total = sum(PHASE_WEIGHTS[phase].values())
        assert abs(total - 1.0) < 1e-9, f"Phase {phase!r} weights sum to {total}"

    @pytest.mark.parametrize("phase", list(PHASE_WEIGHTS.keys()))
    def test_all_weights_non_negative(self, phase: str):
        for k, v in PHASE_WEIGHTS[phase].items():
            assert v >= 0.0, f"Phase {phase!r}, component {k!r} has negative weight {v}"


# ===========================================================================
# 2. Phase detection transitions
# ===========================================================================

class TestPhaseDetection:
    def _detect(self, **kw) -> str:
        defaults = dict(
            dist_from_stop=5.0,
            tau=0.2,
            t1_hit=False, t2_hit=False,
            p1=0.0, p2=None,
            trigger_hit=False,
            first_t1_ts=None,
            first_t2_ts=None,
        )
        defaults.update(kw)
        return _detect_phase(**defaults)

    def test_pre_trigger_default(self):
        assert self._detect() == "pre_trigger"

    def test_triggered_pre_t1_on_trigger_hit(self):
        assert self._detect(trigger_hit=True) == "triggered_pre_t1"

    def test_at_t1_when_t1_hit_and_p1_sufficient(self):
        assert self._detect(t1_hit=True, p1=1.0) == "at_t1"

    def test_between_t1_t2_when_has_t2(self):
        assert self._detect(t1_hit=True, p1=1.0, p2=0.4) == "between_t1_t2"

    def test_post_t1_failed_hold_on_deep_giveback(self):
        assert self._detect(t1_hit=True, p1=0.4) == "post_t1_failed_hold"

    def test_at_t2_priority_over_t1(self):
        phase = self._detect(t1_hit=True, t2_hit=True, p1=1.2, p2=1.1,
                              first_t2_ts="2026-01-10")
        assert phase == "at_t2"

    def test_overtime_when_tau_exceeds_1_and_no_t1(self):
        assert self._detect(tau=1.1) == "overtime"

    def test_overtime_deferred_when_t1_hit(self):
        # T1 already hit → not overtime even if tau > 1
        phase = self._detect(tau=1.1, t1_hit=True, p1=1.0)
        assert phase != "overtime"

    def test_invalidated_overrides_everything(self):
        assert self._detect(dist_from_stop=-1.0, tau=1.5, t1_hit=True, p1=1.0) == "invalidated"

    def test_at_t1_no_t2_when_p2_is_none(self):
        assert self._detect(t1_hit=True, p1=1.0, p2=None) == "at_t1"


# ===========================================================================
# 3. Full compute_management_state — phase surfacing
# ===========================================================================

class TestComputePhases:
    def test_pre_trigger(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0, trigger=105.0)
        result = _run(plan, price=100.0, asof_delta_days=5)
        assert result["phase"] == "pre_trigger"

    def test_triggered_pre_t1(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0, trigger=102.0)
        # Price is past trigger
        result = _run(plan, price=103.0, asof_delta_days=5)
        assert result["phase"] == "triggered_pre_t1"

    def test_at_t1(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0, t2=None)
        # Price is AT T1 (exactly)
        result = _run(plan, price=115.0, asof_delta_days=5)
        assert result["phase"] == "at_t1"

    def test_between_t1_t2(self):
        plan = _make_plan(entry=100.0, t1=115.0, t2=130.0, inval=90.0)
        # Price above T1, below T2
        result = _run(plan, price=120.0, asof_delta_days=5)
        assert result["phase"] == "between_t1_t2"

    def test_at_t2(self):
        plan = _make_plan(entry=100.0, t1=115.0, t2=130.0, inval=90.0)
        result = _run(plan, price=130.0, asof_delta_days=5)
        assert result["phase"] == "at_t2"

    def test_invalidated_stop_breach(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        result = _run(plan, price=88.0, asof_delta_days=5)
        assert result["phase"] == "invalidated"

    def test_overtime_horizon_lapse(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0, horizon_days=10)
        # Days elapsed = 20 → tau = 2.0; price still below T1
        result = _run(plan, price=100.0, asof_delta_days=20)
        assert result["phase"] == "overtime"

    def test_post_t1_failed_hold_from_prev_state(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        # Simulate prior state with T1 hit, then price falls back
        prev = {
            "phase": "at_t1",
            "_first_t1_ts": "2026-01-06",
            "_mfe": 15.0,
            "_mae": 0.0,
            "_max_p1": 1.0,
            "management_confidence": 72.0,
            "raw_confidence": 72.0,
        }
        # Price at 107 → p1 = (107-100)/(115-100) = 0.467 < 0.50 → failed_hold
        # Internal detection_phase = post_t1_failed_hold;
        # schema phase = between_t1_t2 (giveback in T1 zone)
        result = _run(plan, price=107.0, asof_delta_days=15, prev_state=prev)
        assert result["detection_phase"] == "post_t1_failed_hold"
        assert result["phase"] == "between_t1_t2"   # schema-mapped

    def test_bear_invalidated_price_rises(self):
        plan = _make_plan(
            direction="BEAR", entry=100.0, t1=85.0, t2=None, inval=110.0,
        )
        # For BEAR: invalidation is ABOVE entry; stop breach when price > inval
        result = _run(plan, price=112.0, asof_delta_days=5)
        assert result["phase"] == "invalidated"


# ===========================================================================
# 4. Confidence ceiling — never exceeds 92
# ===========================================================================

class TestConfidenceCeiling:
    def test_ceiling_constant(self):
        assert CONFIDENCE_CEILING == 92
        assert MANAGEMENT_CONFIDENCE_CEILING == 92

    def test_management_confidence_never_exceeds_92_at_t2(self):
        plan = _make_plan(entry=100.0, t1=115.0, t2=130.0, inval=90.0)
        result = _run(plan, price=135.0, asof_delta_days=5,
                      macro_stance="bull", futures_chg={"SPY": 0.02, "QQQ": 0.025})
        assert result["management_confidence"] <= 92.0

    def test_raw_confidence_never_exceeds_92(self):
        plan = _make_plan(entry=100.0, t1=115.0, t2=130.0, inval=90.0, confidence=85.0)
        result = _run(plan, price=130.0, asof_delta_days=3,
                      macro_stance="bull", futures_chg={"SPY": 0.03, "QQQ": 0.04})
        assert result["raw_confidence"] <= 92.0

    def test_invalidated_ceiling_enforced(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        result = _run(plan, price=85.0, asof_delta_days=5)
        assert result["management_confidence"] <= 16.0
        assert result["management_confidence"] >= 8.0


# ===========================================================================
# 5. Bounds: floors respected
# ===========================================================================

class TestBoundsFloor:
    def test_pre_trigger_floor_respected(self):
        plan = _make_plan(confidence=60.0, entry=100.0, t1=115.0, inval=90.0)
        result = _run(plan, price=100.0, asof_delta_days=5,
                      macro_stance="bear", futures_chg={"SPY": -0.03})
        # floor = max(25, 60-30) = 30
        assert result["management_confidence"] >= 30.0

    def test_overtime_floor_respected(self):
        plan = _make_plan(confidence=60.0, entry=100.0, t1=115.0, inval=90.0, horizon_days=10)
        result = _run(plan, price=100.0, asof_delta_days=25,
                      macro_stance="bear", futures_chg={"SPY": -0.04})
        # floor = max(20, 60-40) = 20
        assert result["management_confidence"] >= 20.0

    def test_invalidated_floor_8(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        result = _run(plan, price=80.0, asof_delta_days=5)
        assert result["management_confidence"] >= 8.0


# ===========================================================================
# 6. EMA smoothing behaviour
# ===========================================================================

class TestEMASmoothing:
    def test_first_call_no_ema_applied(self):
        result = _apply_ema(
            raw_live_conf=70.0,
            prev_raw=None,
            prev_display=None,
            prev_phase=None,
            phase="pre_trigger",
        )
        assert result == 70.0

    def test_same_phase_alpha_045(self):
        prev_display = 60.0
        raw = 80.0
        result = _apply_ema(
            raw_live_conf=raw,
            prev_raw=65.0,
            prev_display=prev_display,
            prev_phase="pre_trigger",
            phase="pre_trigger",
        )
        expected = (1 - 0.45) * prev_display + 0.45 * raw
        assert abs(result - expected) < 1e-9

    def test_phase_change_alpha_085(self):
        prev_display = 60.0
        raw = 80.0
        result = _apply_ema(
            raw_live_conf=raw,
            prev_raw=60.5,       # |80-60.5| >> 0.03
            prev_display=prev_display,
            prev_phase="pre_trigger",
            phase="triggered_pre_t1",
        )
        expected = (1 - 0.85) * prev_display + 0.85 * raw
        assert abs(result - expected) < 1e-9

    def test_ema_freeze_when_tiny_change(self):
        prev_display = 65.0
        result = _apply_ema(
            raw_live_conf=65.01,   # |65.01 - 65.00| = 0.01 < 0.03
            prev_raw=65.00,
            prev_display=prev_display,
            prev_phase="pre_trigger",
            phase="pre_trigger",
        )
        assert result == prev_display

    def test_sequential_calls_propagate_ema(self):
        plan = _make_plan()
        # First call
        r1 = _run(plan, price=100.0, asof_delta_days=5)
        # Second call — prev_state = r1
        r2 = _run(plan, price=105.0, asof_delta_days=10, prev_state=r1)
        # Raw scores are different, EMA must propagate
        assert r2["management_confidence"] != r1["management_confidence"]


# ===========================================================================
# 7. MFE / MAE accumulation across sequential calls
# ===========================================================================

class TestMfeMaeAccumulation:
    def test_mfe_accumulates_across_calls(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        # High price → large mfe
        r1 = _run(plan, price=110.0, asof_delta_days=5)
        assert r1["_mfe"] == pytest.approx(10.0, abs=0.01)
        # Price drops but prev_state carries mfe
        r2 = _run(plan, price=105.0, asof_delta_days=10, prev_state=r1)
        assert r2["_mfe"] == pytest.approx(10.0, abs=0.01)

    def test_mae_accumulates_across_calls(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        # Price drops to 95 → move = -5
        r1 = _run(plan, price=95.0, asof_delta_days=5)
        assert r1["_mae"] <= -5.0
        # Price rises to 102 but prev_state carries mae
        r2 = _run(plan, price=102.0, asof_delta_days=10, prev_state=r1)
        assert r2["_mae"] <= -5.0

    def test_geometry_mfe_r_and_mae_r(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        r1 = _run(plan, price=108.0, asof_delta_days=5)
        # risk = |100-90| = 10; mfe = 8
        assert r1["geometry"]["mfe_r"] == pytest.approx(0.8, abs=0.05)


# ===========================================================================
# 8. Determinism
# ===========================================================================

class TestDeterminism:
    def test_same_inputs_same_output(self):
        plan = _make_plan()
        r1 = _run(plan, price=108.0, asof_delta_days=10, macro_stance="bull")
        r2 = _run(plan, price=108.0, asof_delta_days=10, macro_stance="bull")
        assert r1["management_confidence"] == r2["management_confidence"]
        assert r1["raw_confidence"] == r2["raw_confidence"]
        assert r1["phase"] == r2["phase"]

    def test_determinism_with_prev_state(self):
        plan = _make_plan()
        r1 = _run(plan, price=105.0, asof_delta_days=8)
        ra = _run(plan, price=108.0, asof_delta_days=12, prev_state=r1)
        rb = _run(plan, price=108.0, asof_delta_days=12, prev_state=r1)
        assert ra["management_confidence"] == rb["management_confidence"]


# ===========================================================================
# 9. PIT assertion
# ===========================================================================

class TestPITAssertion:
    def test_future_dated_price_row_raises(self):
        plan = _make_plan(signal_date="2026-01-01")
        # Build prices with a row dated AFTER asof
        asof = "2026-01-10"
        prices = _make_prices("2026-01-01", [100.0] * 15)  # goes to 2026-01-20+
        with pytest.raises(AssertionError, match="PIT violation"):
            compute_management_state(
                plan=plan,
                price_history=prices,
                asof=asof,
            )

    def test_price_on_asof_date_is_allowed(self):
        plan = _make_plan(signal_date="2026-01-01")
        asof = "2026-01-10"
        # 7 business days: 2026-01-01 through 2026-01-09 (Mon-Fri), all <= asof
        prices = _make_prices("2026-01-01", [100.0] * 7)
        result = compute_management_state(plan=plan, price_history=prices, asof=asof)
        assert result["phase"] in {"pre_trigger", "triggered_pre_t1"}


# ===========================================================================
# 10. Validator round-trip
# ===========================================================================

class TestValidatorRoundTrip:
    def test_output_passes_validate_management_state(self):
        plan = _make_plan()
        result = _run(plan, price=108.0, asof_delta_days=10)
        errors = validate_management_state(result)
        assert errors == [], f"Validation errors: {errors}"

    def test_all_phases_produce_valid_output(self):
        configs = [
            ("pre_trigger",  100.0, 5),
            ("triggered",    103.0, 5),   # past trigger=102
            ("at_t1",        115.0, 5),
            ("at_t2",        130.0, 5),
            ("overtime",     100.0, 20),  # horizon=10, so tau > 1
            ("invalidated",  85.0,  5),
        ]
        for label, price, days in configs:
            horizon = 10 if label == "overtime" else 60
            plan = _make_plan(horizon_days=horizon, trigger=102.0 if label == "triggered" else None)
            result = _run(plan, price=price, asof_delta_days=days)
            errs = validate_management_state(result)
            assert errs == [], f"Phase {label}: {errs}"

    def test_schema_field_correct(self):
        result = _run(_make_plan())
        assert result["schema"] == "prophet.management_state/v1"

    def test_id_matches_plan(self):
        plan = _make_plan()
        plan["id"] = "unique-id-123"
        result = _run(plan)
        assert result["id"] == "unique-id-123"

    def test_required_fields_present(self):
        result = _run(_make_plan())
        required = {
            "schema", "id", "asof", "phase", "management_confidence",
            "raw_confidence", "delta_vs_base", "recommended_action",
            "components", "geometry", "change_reason", "confidence_ceiling",
            "authority", "authority_tier", "reliability",
        }
        for f in required:
            assert f in result, f"Missing required field: {f}"


# ===========================================================================
# 11. Component unit tests
# ===========================================================================

class TestValidityComponent:
    def test_above_danger_zone_uses_power_135(self):
        v = _compute_validity(dist_from_stop=5.0, risk=10.0)  # ratio = 0.5
        expected = math.pow(0.5, 1.35)
        assert abs(v - expected) < 1e-9

    def test_danger_zone_below_025_steeper_curve(self):
        # ratio = 0.2 < 0.25
        v_danger = _compute_validity(dist_from_stop=2.0, risk=10.0)
        # At ratio=0.2: base_danger * (0.2/0.25)^2.2
        base_danger = math.pow(0.25, 1.35)
        expected = base_danger * math.pow(0.8, 2.2)
        assert abs(v_danger - expected) < 1e-9

    def test_at_stop_is_zero(self):
        assert _compute_validity(dist_from_stop=0.0, risk=10.0) == 0.0

    def test_ratio_1_is_near_one(self):
        v = _compute_validity(dist_from_stop=10.0, risk=10.0)
        assert v == pytest.approx(1.0, abs=0.01)

    def test_zero_risk_returns_zero(self):
        assert _compute_validity(dist_from_stop=5.0, risk=0.0) == 0.0


class TestObjectiveComponent:
    def test_pre_t1_zero_p1(self):
        assert _compute_objective(p1=0.0, p2=None, t1_hit=False, t2_hit=False, has_t2=False) == 0.0

    def test_pre_t1_half(self):
        v = _compute_objective(p1=0.5, p2=None, t1_hit=False, t2_hit=False, has_t2=False)
        expected = 0.68 * math.pow(0.5, 0.75)
        assert abs(v - expected) < 1e-6

    def test_t1_hit_no_t2_returns_mid_range(self):
        v = _compute_objective(p1=1.0, p2=None, t1_hit=True, t2_hit=False, has_t2=False)
        assert 0.35 <= v <= 0.65

    def test_t2_hit_returns_high_range(self):
        v = _compute_objective(p1=1.5, p2=1.2, t1_hit=True, t2_hit=True, has_t2=True)
        assert v >= 0.60


class TestPaceComponent:
    def test_short_horizon_schedule(self):
        # horizonDays < 14: t1ExpectedBy=0.45
        v = _compute_pace(tau=0.2, p1=0.0, p2=None, t1_hit=False, t2_hit=False,
                          horizon_days=7, phase="pre_trigger")
        assert 0.0 <= v <= 1.0

    def test_overtime_phase_decays(self):
        v = _compute_pace(tau=1.3, p1=0.0, p2=None, t1_hit=False, t2_hit=False,
                          horizon_days=10, phase="overtime")
        assert v < 0.3

    def test_invalidated_returns_zero(self):
        assert _compute_pace(tau=0.5, p1=0.0, p2=None, t1_hit=False, t2_hit=False,
                             horizon_days=60, phase="invalidated") == 0.0

    def test_on_schedule_at_half_horizon_half_p1(self):
        # If tau=0.5 and p1=0.5, should be roughly on pace
        v = _compute_pace(tau=0.5, p1=0.5, p2=None, t1_hit=False, t2_hit=False,
                          horizon_days=60, phase="triggered_pre_t1")
        assert v >= 0.6, f"Expected on-pace score >= 0.6, got {v}"


class TestRetentionComponent:
    def test_neutral_05_pre_trigger(self):
        assert _compute_retention(move=10.0, mfe=15.0, p1=0.5, phase="pre_trigger") == 0.5

    def test_neutral_05_triggered_pre_t1(self):
        assert _compute_retention(move=10.0, mfe=15.0, p1=0.5, phase="triggered_pre_t1") == 0.5

    def test_full_retention_when_at_mfe(self):
        v = _compute_retention(move=15.0, mfe=15.0, p1=1.0, phase="at_t1")
        assert v == pytest.approx(1.0, abs=0.01)

    def test_zero_retention_when_all_mfe_given_back(self):
        v = _compute_retention(move=0.0, mfe=15.0, p1=0.0, phase="post_t1_failed_hold")
        assert v == pytest.approx(0.0, abs=0.01)

    def test_amplification_failed_hold_p1_lt_05(self):
        # p1 < 0.50 → amp = 1.6
        base = _compute_retention(move=8.0, mfe=15.0, p1=0.4, phase="at_t1")
        amped = _compute_retention(move=8.0, mfe=15.0, p1=0.4, phase="post_t1_failed_hold")
        # Amplified version should be clamped but shows the amp logic
        assert amped >= base or amped == 1.0  # clamped to [0,1]


class TestTriggerScoreComponent:
    def test_no_trigger_returns_05(self):
        assert _compute_trigger_score(100.0, None, 1, None, False) == pytest.approx(0.5)

    def test_past_trigger_base_is_065(self):
        # depth_frac = 0 → score = 0.65
        score = _compute_trigger_score(
            price=102.0, trigger_price=102.0, dir_int=1, d1=15.0, trigger_hit=True
        )
        assert score == pytest.approx(0.65, abs=0.01)

    def test_past_trigger_deep_approaches_088(self):
        # depth = 15*0.15 = 2.25; depth_frac = 1.0 → score = 0.65+0.23=0.88
        score = _compute_trigger_score(
            price=104.25, trigger_price=102.0, dir_int=1, d1=15.0, trigger_hit=True
        )
        assert score == pytest.approx(0.88, abs=0.01)

    def test_approaching_trigger_range_040_055(self):
        # Far from trigger → low approach frac → score near 0.40
        score = _compute_trigger_score(
            price=95.0, trigger_price=102.0, dir_int=1, d1=15.0, trigger_hit=False
        )
        assert 0.40 <= score <= 0.55


class TestPathPenalty:
    def test_no_penalty_when_move_zero(self):
        assert _compute_path_penalty(mae=0.0, risk=10.0, move=0.0) == 0.0

    def test_penalty_when_winning_with_mae(self):
        p = _compute_path_penalty(mae=-5.0, risk=10.0, move=3.0)
        # mae_frac = 0.5; penalty = 4 * 0.5^1.2 / 100
        expected = 4.0 * math.pow(0.5, 1.2) / 100.0
        assert abs(p - expected) < 1e-6

    def test_deep_recovery_adds_extra(self):
        # mae_frac > 0.8 → deep recovery term
        p_shallow = _compute_path_penalty(mae=-7.5, risk=10.0, move=5.0)  # frac=0.75, no deep
        p_deep    = _compute_path_penalty(mae=-9.0, risk=10.0, move=5.0)  # frac=0.9, has deep
        assert p_deep > p_shallow


# ===========================================================================
# 12. Phase bounds unit tests
# ===========================================================================

class TestPhaseBounds:
    def test_invalidated_narrow_band(self):
        fl, ce = _phase_bounds("invalidated", 60.0, 0.0, None, 0.2, CONFIDENCE_CEILING)
        assert fl == 8.0
        assert ce == 16.0

    def test_pre_trigger_floor(self):
        fl, _ = _phase_bounds("pre_trigger", 60.0, 0.0, None, 0.1, CONFIDENCE_CEILING)
        assert fl == max(25.0, 60.0 - 30.0)

    def test_overtime_guard_tau_gt_1_p1_lt_075(self):
        # tau=1.2, p1=0.5 → overtime guard applies
        _, ce = _phase_bounds("overtime", 60.0, 0.5, None, 1.2, CONFIDENCE_CEILING)
        assert ce <= max(45.0, 60.0 - 12.0)

    def test_stall_guard_applied_to_pre_trigger(self):
        # tau=0.4, p1=0.02 → stall guard
        _, ce_stall = _phase_bounds("pre_trigger", 60.0, 0.02, None, 0.4, CONFIDENCE_CEILING)
        _, ce_normal = _phase_bounds("pre_trigger", 60.0, 0.50, None, 0.4, CONFIDENCE_CEILING)
        assert ce_stall <= ce_normal

    def test_at_t2_ceiling_is_cap(self):
        _, ce = _phase_bounds("at_t2", 60.0, 1.5, 1.2, 0.8, CONFIDENCE_CEILING)
        assert ce == float(CONFIDENCE_CEILING)


# ===========================================================================
# 13. R/R grade thresholds (§13)
# ===========================================================================

class TestRRGrade:
    @pytest.mark.parametrize("rr,expected", [
        (4.0, "EXCEPTIONAL"),
        (3.0, "EXCELLENT"),
        (2.0, "FAVORABLE"),
        (1.0, "ACCEPTABLE"),
        (0.5, "UNFAVORABLE"),
        (0.4, "POOR"),
    ])
    def test_grade_thresholds(self, rr: float, expected: str):
        assert _rr_grade(rr) == expected

    def test_rr_in_output(self):
        plan = _make_plan(entry=100.0, t1=115.0, inval=90.0)
        result = _run(plan)
        # risk=10, reward=15, rr=1.5
        assert result["rr_ratio"] == pytest.approx(1.5, abs=0.01)
        assert result["rr_grade"] == "ACCEPTABLE"


# ===========================================================================
# 14. Recommended actions
# ===========================================================================

class TestRecommendedActions:
    @pytest.mark.parametrize("phase,trigger_hit,expected", [
        ("pre_trigger",          False, "wait"),
        ("pre_trigger",          True,  "enter"),
        ("triggered_pre_t1",     True,  "hold"),
        ("at_t1",                True,  "hold"),
        ("between_t1_t2",        True,  "hold"),
        ("post_t1_failed_hold",  True,  "trim"),
        ("at_t2",                True,  "trail"),
        ("overtime",             False, "trim"),
        ("invalidated",          False, "invalidated"),
    ])
    def test_action_mapping(self, phase: str, trigger_hit: bool, expected: str):
        assert _recommended_action(phase, trigger_hit) == expected


# ===========================================================================
# 15. Human state strings
# ===========================================================================

class TestHumanState:
    def test_invalidated_string(self):
        assert _human_state("invalidated", 0.0, False, 0.5) == "Invalidated"

    def test_overtime_string(self):
        assert _human_state("overtime", 0.0, False, 1.2) == "Overtime Stall"

    def test_pre_trigger_awaiting(self):
        assert _human_state("pre_trigger", 0.0, False, 0.05) == "Awaiting Trigger"

    def test_pre_trigger_approaching(self):
        assert _human_state("pre_trigger", 0.0, False, 0.3) == "Approaching Trigger"

    def test_triggered_advancing(self):
        assert _human_state("triggered_pre_t1", 0.7, True, 0.4) == "Advancing Cleanly"

    def test_at_t2_high_conviction(self):
        assert _human_state("at_t2", 1.2, True, 0.7) == "High Conviction"


# ===========================================================================
# 16. BEAR direction geometry
# ===========================================================================

class TestBearDirection:
    def test_bear_move_positive_when_price_falls(self):
        plan = _make_plan(
            direction="BEAR", entry=100.0, t1=85.0, t2=None,
            inval=110.0, horizon_days=60
        )
        result = _run(plan, price=90.0, asof_delta_days=5)
        # move = -1 * (90 - 100) = 10 (positive = favorable)
        assert result["geometry"]["move_r"] > 0

    def test_bear_invalidated_when_price_rises(self):
        plan = _make_plan(
            direction="BEAR", entry=100.0, t1=85.0, t2=None,
            inval=110.0, horizon_days=60
        )
        result = _run(plan, price=112.0, asof_delta_days=5)
        assert result["phase"] == "invalidated"

    def test_bear_at_t1(self):
        plan = _make_plan(
            direction="BEAR", entry=100.0, t1=85.0, t2=None,
            inval=110.0, horizon_days=60
        )
        result = _run(plan, price=85.0, asof_delta_days=5)
        assert result["phase"] == "at_t1"


# ===========================================================================
# 17. Overlay / macro effects
# ===========================================================================

class TestOverlayEffects:
    def test_macro_bull_aligned_with_bull_plan_raises_overlay(self):
        plan = _make_plan()
        r_aligned = _run(plan, price=105.0, asof_delta_days=10, macro_stance="bull")
        r_opposed  = _run(plan, price=105.0, asof_delta_days=10, macro_stance="bear")
        # Aligned macro should produce higher management_confidence
        assert r_aligned["management_confidence"] > r_opposed["management_confidence"]

    def test_futures_adverse_suppresses_confidence(self):
        plan = _make_plan()
        # Use strong futures signals and check raw_confidence (pre-EMA) for directional effect
        r_good = _run(plan, price=105.0, asof_delta_days=10,
                      futures_chg={"SPY": 0.05, "QQQ": 0.06})
        r_bad  = _run(plan, price=105.0, asof_delta_days=10,
                      futures_chg={"SPY": -0.05, "QQQ": -0.06})
        assert r_good["raw_confidence"] >= r_bad["raw_confidence"]


# ===========================================================================
# 18. Smoothstep helper sanity
# ===========================================================================

class TestSmoothstep:
    def test_at_edge0_returns_0(self):
        assert _smoothstep(0.05, 0.65, 0.05) == pytest.approx(0.0)

    def test_at_edge1_returns_1(self):
        assert _smoothstep(0.05, 0.65, 0.65) == pytest.approx(1.0)

    def test_midpoint_returns_05(self):
        assert _smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5)

    def test_below_edge0_clamps_to_0(self):
        assert _smoothstep(0.1, 0.9, 0.0) == pytest.approx(0.0)

    def test_above_edge1_clamps_to_1(self):
        assert _smoothstep(0.1, 0.9, 1.0) == pytest.approx(1.0)


# ===========================================================================
# 19. Full pipeline edge cases
# ===========================================================================

class TestEdgeCases:
    def test_empty_price_history_raises(self):
        plan = _make_plan()
        empty = pd.DataFrame({"close": []}, index=pd.DatetimeIndex([]))
        with pytest.raises((ValueError, AssertionError)):
            compute_management_state(plan=plan, price_history=empty, asof="2026-01-10")

    def test_no_targets_fallback_risk(self):
        plan = _make_plan(signal_date="2026-01-01")
        plan["targets"] = []
        plan["invalidation"] = 90.0
        plan["entry"] = 100.0
        # Should not crash; uses 5% fallback risk
        # 5 business days: 2026-01-01 (Thu), 2026-01-02 (Fri), 2026-01-05..07 = all <= 2026-01-07
        prices = _make_prices("2026-01-01", [100.0] * 5)
        result = compute_management_state(plan=plan, price_history=prices, asof="2026-01-07")
        assert result["schema"] == "prophet.management_state/v1"

    def test_confidence_ceiling_field_in_output(self):
        result = _run(_make_plan())
        assert result["confidence_ceiling"] == 92

    def test_components_all_present(self):
        result = _run(_make_plan())
        for key in ("validity", "progress", "pace", "retention", "overlay"):
            assert key in result["components"], f"Missing component: {key}"

    def test_geometry_all_present(self):
        result = _run(_make_plan())
        geo = result["geometry"]
        for key in ("dist_to_stop_r", "dist_to_t1_r", "horizon_pct_used", "p1", "move_r"):
            assert key in geo, f"Missing geometry key: {key}"
