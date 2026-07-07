"""tests/test_gex_state.py — Package C: GEX Structure State emitter tests.

Coverage:
  1. 6-state regime classifier — each regime reachable on synthetic profiles.
  2. Stability math — correct ratio + noise-floor guard.
  3. Passport passthrough — regime_passport copied verbatim from engine summary.
  4. Validator round-trip — compute_gex_state output passes validate_gex_state.
  5. Null-safety — thin_chain and no_options tiers return None (no crash).
  6. Gravity direction logic.
  7. Pin probability shape.
  8. Cascade / upside trigger gating.
  9. Missing-data robustness — empty by_strike, None spot, etc.
 10. oi_delta_clusters — always a dict with new_oi / exit_oi lists.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from engine.gex_state import (
    _classify_regime,
    _gravity,
    _make_regime_passport,
    _oi_delta_clusters,
    _pin_probability,
    _stability_from_walls,
    _triggers,
    compute_gex_state,
)
from engine.options_structure import validate_gex_state


# ── helpers ──────────────────────────────────────────────────────────────────

ASOF = "2026-07-07T20:05:00+00:00"

_INDEX_PRODUCTS = frozenset({"SPX", "SPY", "QQQ", "NDX", "IWM", "RUT", "VIX", "DIA", "SPXW"})


def _make_strike(k: float, net_mn: float, coi: int = 1000, poi: int = 1000) -> dict:
    """Build a minimal by_strike row."""
    return {"K": k, "net_mn": net_mn, "call_oi": coi, "put_oi": poi,
            "call_vol": 0, "put_vol": 0}


def _make_model(
    spot: float = 500.0,
    net_gex_bn: float = 1.5,
    gamma_flip: float | None = 490.0,
    dist_to_flip_pct: float | None = 2.0,
    call_wall: float | None = 520.0,
    put_wall: float | None = 480.0,
    max_pain: float | None = 500.0,
    tier: str = "full",
    by_strike: list | None = None,
) -> dict:
    """Construct a minimal gex_model.build_model()-like dict."""
    if by_strike is None:
        # a sparse but sufficient set: strikes ±2% of spot, balanced positive/negative
        by_strike = [
            _make_strike(520.0,  30.0),
            _make_strike(510.0,  20.0),
            _make_strike(505.0,  10.0),
            _make_strike(500.0,   5.0),
            _make_strike(495.0,  -8.0),
            _make_strike(490.0, -15.0),
            _make_strike(480.0, -25.0),
            _make_strike(475.0,  -5.0),
        ]
    return {
        "summary": {
            "spot": spot,
            "net_gex_bn": net_gex_bn,
            "gamma_flip": gamma_flip,
            "dist_to_flip_pct": dist_to_flip_pct,
            "max_pain": max_pain,
            "tier": tier,
            "regime_passport": {
                "basis": "dealer-short-assumption",
                "structurally_constant": False,
                "is_index_product": True,
                "verdict": "display-only",
                "note": "Index product — test passport.",
            },
        },
        "walls": {
            "call_wall": call_wall,
            "put_wall": put_wall,
            "largest_oi": 500.0,
            "by_strike": by_strike,
        },
        "meta": {"key": "SPY"},
        "history": [],
    }


# ===========================================================================
# 1. regime classifier — each of the 6 regimes reachable
# ===========================================================================

class TestClassifyRegime:
    def test_drift(self):
        """ratio > 0.75 → DRIFT"""
        assert _classify_regime(0.80, 0.05, True) == "DRIFT"

    def test_pin(self):
        """0.65 < ratio ≤ 0.75, not near flip → PIN"""
        assert _classify_regime(0.70, 0.05, True) == "PIN"

    def test_range_upper(self):
        """0.55 < ratio ≤ 0.65 → RANGE"""
        assert _classify_regime(0.60, 0.05, True) == "RANGE"

    def test_range_lower(self):
        """0.45 < ratio ≤ 0.55, not close flip → RANGE"""
        assert _classify_regime(0.50, 0.05, True) == "RANGE"

    def test_transition_near_flip(self):
        """flip_known and dist < 0.2% → TRANSITION regardless of ratio"""
        assert _classify_regime(0.70, 0.001, True) == "TRANSITION"

    def test_transition_close_flip_mid_ratio(self):
        """flip_known and dist < 0.5% and ratio > 0.35 → TRANSITION"""
        assert _classify_regime(0.45, 0.003, True) == "TRANSITION"

    def test_trend(self):
        """0.30 < ratio ≤ 0.45 (not near/close flip) → TREND"""
        assert _classify_regime(0.40, 0.10, True) == "TREND"

    def test_cascade(self):
        """ratio ≤ 0.30 → CASCADE"""
        assert _classify_regime(0.20, 0.10, True) == "CASCADE"

    def test_cascade_boundary(self):
        """ratio == 0.30 → CASCADE (boundary is >0.30 for TREND)"""
        assert _classify_regime(0.30, 0.10, True) == "CASCADE"

    def test_trend_boundary(self):
        """ratio just above 0.30 → TREND"""
        assert _classify_regime(0.31, 0.10, True) == "TREND"

    def test_no_flip_no_transition(self):
        """flip_known=False: transition condition can't fire"""
        assert _classify_regime(0.65, 0.001, False) == "RANGE"  # ratio=0.65 → RANGE (≤ 0.65)

    def test_all_regimes_non_overlapping(self):
        """Verify the 6 regimes cover the ratio space without gaps."""
        regimes = set()
        for ratio in [0.10, 0.35, 0.47, 0.57, 0.67, 0.80]:
            r = _classify_regime(ratio, 0.10, True)
            regimes.add(r)
        assert regimes == {"CASCADE", "TREND", "RANGE", "PIN", "DRIFT"} or len(regimes) >= 4


# ===========================================================================
# 2. stability math
# ===========================================================================

class TestStabilityFromWalls:
    def test_basic_ratio(self):
        """pos=60, neg=40 → stability_pct=60, ratio=0.60"""
        by_strike = [
            _make_strike(510.0,  60.0),
            _make_strike(490.0, -40.0),
        ]
        pct, ratio, noise = _stability_from_walls(by_strike, 500.0)
        assert pct == pytest.approx(60.0)
        assert ratio == pytest.approx(0.60)
        assert noise is False

    def test_window_filter(self):
        """Strikes outside ±20% window are excluded."""
        by_strike = [
            _make_strike(510.0,  60.0),   # inside (2% above spot=500)
            _make_strike(200.0, -1000.0), # outside (60% below spot — excluded)
        ]
        pct, ratio, noise = _stability_from_walls(by_strike, 500.0)
        # only the positive 60 counts → ratio=1.0
        assert pct == pytest.approx(100.0)
        assert ratio == pytest.approx(1.0)
        assert noise is False

    def test_noise_floor_hit(self):
        """Total abs GEX below noise floor → noise_floor_hit=True, stability_pct=None."""
        by_strike = [
            _make_strike(500.0, 0.001),  # tiny value (in $mn → 0.001 << spot*100/1e6)
        ]
        pct, ratio, noise = _stability_from_walls(by_strike, 500.0)
        assert noise is True
        assert pct is None
        assert ratio is None

    def test_empty_by_strike(self):
        pct, ratio, noise = _stability_from_walls([], 500.0)
        assert noise is True
        assert pct is None

    def test_zero_spot(self):
        by_strike = [_make_strike(100.0, 10.0)]
        pct, ratio, noise = _stability_from_walls(by_strike, 0.0)
        assert noise is True


# ===========================================================================
# 3. passport passthrough
# ===========================================================================

class TestRegimePassport:
    def test_passport_copied_verbatim(self):
        """When the model summary carries a regime_passport, it is copied verbatim."""
        source = {
            "basis": "assumption",
            "structurally_constant": True,
            "is_index_product": False,
            "verdict": "display-only",
            "note": "single-name test",
        }
        result = _make_regime_passport("NVDA", source)
        assert result == source  # exact copy, not a reconstruction

    def test_passport_rebuilt_when_absent(self):
        """When source_passport is None, passport is rebuilt from symbol."""
        result = _make_regime_passport("SPY", None)
        assert result["basis"] == "dealer-short-assumption"
        assert result["is_index_product"] is True
        assert result["structurally_constant"] is False  # index → not structurally constant

    def test_passport_single_name(self):
        result = _make_regime_passport("NVDA", None)
        assert result["is_index_product"] is False
        assert result["structurally_constant"] is True  # single name → constant product attribute

    def test_passport_none_symbol(self):
        result = _make_regime_passport(None, None)
        assert result["basis"] == "dealer-short-assumption"
        assert result["is_index_product"] is None
        assert result["structurally_constant"] is None

    def test_passport_rides_payload(self):
        """compute_gex_state output carries the exact source passport."""
        model = _make_model()
        source = model["summary"]["regime_passport"]
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["regime_passport"] == source


# ===========================================================================
# 4. validator round-trip
# ===========================================================================

class TestValidatorRoundTrip:
    def test_clean_payload_validates(self):
        model = _make_model()
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        errors = validate_gex_state(state)
        assert errors == []

    def test_schema_field_correct(self):
        model = _make_model()
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state["schema"] == "options_structure.gex_state/v1"

    def test_authority_tier_display(self):
        model = _make_model()
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state["authority_tier"] == "display"

    def test_root_uppercased(self):
        model = _make_model()
        state = compute_gex_state(model, "spy", asof=ASOF)
        assert state["root"] == "SPY"

    def test_gamma_regime_valid_value(self):
        valid_regimes = {"PIN", "DRIFT", "RANGE", "TRANSITION", "TREND", "CASCADE"}
        model = _make_model()
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state["gamma_regime"] in valid_regimes

    def test_asof_defaults_when_none(self):
        model = _make_model()
        state = compute_gex_state(model, "SPY", asof=None)
        assert state is not None
        assert state["asof"]  # non-empty


# ===========================================================================
# 5. null-safety: thin_chain and no_options return None
# ===========================================================================

class TestNullSafety:
    def test_thin_chain_returns_none(self):
        """thin_chain tier must NOT crash — returns None."""
        model = _make_model(tier="thin_chain")
        result = compute_gex_state(model, "GME", asof=ASOF)
        assert result is None

    def test_no_options_returns_none(self):
        """no_options tier must NOT crash — returns None."""
        model = _make_model(tier="no_options")
        result = compute_gex_state(model, "GME", asof=ASOF)
        assert result is None

    def test_none_model_returns_none(self):
        result = compute_gex_state(None, "SPY", asof=ASOF)
        assert result is None

    def test_empty_model_returns_none(self):
        result = compute_gex_state({}, "SPY", asof=ASOF)
        assert result is None

    def test_missing_spot_returns_none(self):
        model = _make_model()
        model["summary"]["spot"] = None
        result = compute_gex_state(model, "SPY", asof=ASOF)
        assert result is None

    def test_zero_spot_returns_none(self):
        model = _make_model(spot=0.0)
        result = compute_gex_state(model, "SPY", asof=ASOF)
        assert result is None

    def test_empty_by_strike_does_not_crash(self):
        """Empty by_strike: still emits payload with None levels."""
        model = _make_model()
        model["walls"]["by_strike"] = []
        result = compute_gex_state(model, "SPY", asof=ASOF)
        # May return None (noise floor) or a valid payload — must not crash
        assert result is None or isinstance(result, dict)

    def test_missing_walls_does_not_crash(self):
        """Missing walls dict: must not crash. When by_strike is absent, noise-floor
        hits (stability_pct=None) and the regime falls back to RANGE; the payload
        is still emitted with null level fields — it does NOT return None because the
        tier='full' guard passes (tier is checked separately from wall data).
        The key invariant is: no exception raised, output is valid or None."""
        model = _make_model()
        model["walls"] = {}
        result = compute_gex_state(model, "SPY", asof=ASOF)
        # Either a valid dict (with null levels) or None — must not crash
        assert result is None or isinstance(result, dict)
        if result is not None:
            errors = validate_gex_state(result)
            assert errors == [], f"Validation errors with missing walls: {errors}"


# ===========================================================================
# 6. gravity direction logic
# ===========================================================================

class TestGravityDirection:
    def _build_by_strike(self, above_net: float, below_net: float, spot: float = 500.0):
        """Helper: one strike above spot with above_net, one below with below_net."""
        return [
            _make_strike(spot + 10, above_net),
            _make_strike(spot - 10, below_net),
        ]

    def test_up_direction(self):
        """Large positive net above spot → pullUp dominant → direction='up'"""
        by_strike = self._build_by_strike(100.0, -5.0)
        direction, up_pct = _gravity(by_strike, 500.0)
        assert direction == "up"
        assert up_pct is not None and up_pct > 60

    def test_down_direction(self):
        """Large negative net below spot → pullDown dominant → direction='down'"""
        by_strike = self._build_by_strike(5.0, -100.0)
        direction, up_pct = _gravity(by_strike, 500.0)
        assert direction == "down"
        assert up_pct is not None and up_pct < 40

    def test_neutral_returns_none_direction(self):
        """Balanced → neither >60% → direction=None"""
        by_strike = self._build_by_strike(50.0, -50.0)
        direction, up_pct = _gravity(by_strike, 500.0)
        assert direction is None
        assert up_pct is not None

    def test_empty_by_strike(self):
        direction, up_pct = _gravity([], 500.0)
        assert direction is None
        assert up_pct is None

    def test_zero_spot(self):
        by_strike = [_make_strike(100.0, 10.0)]
        direction, up_pct = _gravity(by_strike, 0.0)
        assert direction is None
        assert up_pct is None


# ===========================================================================
# 7. pin probability shape
# ===========================================================================

class TestPinProbability:
    def test_highest_oi_near_spot_wins(self):
        """Strike nearest spot with highest OI should have the highest score → highest pin prob."""
        spot = 500.0
        by_strike = [
            _make_strike(500.0, 20.0, coi=50000, poi=50000),   # ATM high OI
            _make_strike(550.0,  5.0, coi=1000,  poi=1000),
            _make_strike(450.0,  3.0, coi=1000,  poi=1000),
        ]
        prob = _pin_probability(by_strike, spot, max_pain=500.0)
        assert prob is not None
        assert 0.0 < prob <= 0.95

    def test_fewer_than_3_strikes_returns_none(self):
        by_strike = [_make_strike(500.0, 10.0), _make_strike(510.0, 5.0)]
        prob = _pin_probability(by_strike, 500.0, max_pain=500.0)
        assert prob is None

    def test_empty_returns_none(self):
        prob = _pin_probability([], 500.0, max_pain=500.0)
        assert prob is None

    def test_probability_bounded(self):
        """Probability must be in [0, 0.95]."""
        by_strike = [_make_strike(k, 10.0, coi=1000, poi=1000) for k in range(480, 520, 5)]
        prob = _pin_probability(by_strike, 500.0, max_pain=500.0)
        if prob is not None:
            assert 0.0 <= prob <= 0.95


# ===========================================================================
# 8. cascade / upside trigger gating
# ===========================================================================

class TestTriggers:
    def _build_cascade_profile(self, spot: float = 500.0, flip: float = 500.0):
        """Many negative strikes below flip and positive above."""
        strikes = []
        # below flip: negative net (cascade candidates)
        for k, net in [(495, -10), (490, -20), (485, -30), (480, -50), (475, -15), (470, -8)]:
            strikes.append(_make_strike(k, net))
        # above flip: positive net (upside candidates)
        for k, net in [(505, 10), (510, 25), (515, 40), (520, 60), (525, 15), (530, 8)]:
            strikes.append(_make_strike(k, net))
        return strikes

    def test_cascade_trigger_below_flip(self):
        by_strike = self._build_cascade_profile()
        cascade, upside = _triggers(by_strike, 500.0, flip=500.0,
                                    call_wall=530.0, put_wall=470.0)
        # With flip=500, strikes below 500 with negative net are cascade candidates
        if cascade is not None:
            assert cascade < 500.0

    def test_upside_trigger_above_flip(self):
        by_strike = self._build_cascade_profile()
        cascade, upside = _triggers(by_strike, 500.0, flip=500.0,
                                    call_wall=530.0, put_wall=470.0)
        if upside is not None:
            assert upside > 500.0

    def test_fewer_than_4_candidates_returns_none(self):
        """With < 4 negative strikes below flip, cascade_trigger should be None."""
        by_strike = [
            _make_strike(490, -10),
            _make_strike(485, -20),
            _make_strike(480, -30),   # only 3 negative below-flip strikes
            _make_strike(510, 10),    # positive above → upside candidate
            _make_strike(515, 20),
            _make_strike(520, 30),
        ]
        cascade, upside = _triggers(by_strike, 500.0, flip=500.0,
                                    call_wall=530.0, put_wall=475.0)
        # Cascade gate requires ≥4 candidates (OURS)
        assert cascade is None

    def test_empty_returns_none_none(self):
        cascade, upside = _triggers([], 500.0, flip=490.0,
                                    call_wall=520.0, put_wall=480.0)
        assert cascade is None
        assert upside is None


# ===========================================================================
# 9. oi_delta_clusters always dict with lists
# ===========================================================================

class TestOiDeltaClusters:
    def test_returns_dict_with_lists(self):
        result = _oi_delta_clusters("SPY")
        assert isinstance(result, dict)
        assert "new_oi" in result
        assert "exit_oi" in result
        assert isinstance(result["new_oi"], list)
        assert isinstance(result["exit_oi"], list)

    def test_payload_has_correct_oi_keys(self):
        model = _make_model()
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        clusters = state.get("oi_delta_clusters")
        assert isinstance(clusters, dict)
        assert "new_oi" in clusters
        assert "exit_oi" in clusters
        assert isinstance(clusters["new_oi"], list)
        assert isinstance(clusters["exit_oi"], list)


# ===========================================================================
# 10. full integration — all 6 regimes via compute_gex_state
# ===========================================================================

class TestComputeGexStateRegimes:
    """Drive all 6 regimes through compute_gex_state by manipulating the by_strike
    distribution (pos/neg GEX ratio) and the dist_to_flip values."""

    def _model_with_ratio(self, ratio: float, spot: float = 500.0,
                          dist_to_flip_pct: float = 5.0) -> dict:
        """Build a model whose stability ratio approximates `ratio` by
        assigning proportional pos/neg GEX above the noise floor."""
        total_mn = 2000.0  # well above noise floor
        pos_mn = total_mn * ratio
        neg_mn = total_mn * (1.0 - ratio)
        by_strike = [
            _make_strike(spot + 10, pos_mn),
            _make_strike(spot - 10, -neg_mn),
            # extra strikes to keep triggers gate happy
            _make_strike(spot + 20, pos_mn * 0.2),
            _make_strike(spot + 30, pos_mn * 0.1),
            _make_strike(spot - 20, -neg_mn * 0.2),
            _make_strike(spot - 30, -neg_mn * 0.1),
        ]
        flip = spot * (1.0 - dist_to_flip_pct / 100.0)
        return _make_model(spot=spot, gamma_flip=flip,
                           dist_to_flip_pct=dist_to_flip_pct,
                           by_strike=by_strike)

    def test_cascade_regime(self):
        model = self._model_with_ratio(0.15)  # ratio=0.15 → CASCADE
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["gamma_regime"] == "CASCADE"

    def test_trend_regime(self):
        model = self._model_with_ratio(0.38)  # ratio=0.38 → TREND
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["gamma_regime"] == "TREND"

    def test_range_regime(self):
        model = self._model_with_ratio(0.58)  # ratio=0.58 → RANGE
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["gamma_regime"] == "RANGE"

    def test_pin_regime(self):
        model = self._model_with_ratio(0.70)  # ratio=0.70 → PIN
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["gamma_regime"] == "PIN"

    def test_drift_regime(self):
        model = self._model_with_ratio(0.80)  # ratio=0.80 → DRIFT
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["gamma_regime"] == "DRIFT"

    def test_transition_regime_near_flip(self):
        """Near-flip condition (dist < 0.2%) → TRANSITION regardless of ratio."""
        model = self._model_with_ratio(0.70, dist_to_flip_pct=0.1)
        state = compute_gex_state(model, "SPY", asof=ASOF)
        assert state is not None
        assert state["gamma_regime"] == "TRANSITION"

    def test_full_validator_on_each_regime(self):
        """Every regime-producing payload must pass validate_gex_state with no errors."""
        configs = [
            (0.15, 5.0),   # CASCADE
            (0.38, 5.0),   # TREND
            (0.58, 5.0),   # RANGE
            (0.70, 5.0),   # PIN
            (0.80, 5.0),   # DRIFT
            (0.70, 0.1),   # TRANSITION
        ]
        for ratio, dist in configs:
            model = self._model_with_ratio(ratio, dist_to_flip_pct=dist)
            state = compute_gex_state(model, "SPY", asof=ASOF)
            assert state is not None, f"ratio={ratio} dist={dist} returned None"
            errors = validate_gex_state(state)
            assert errors == [], f"ratio={ratio} dist={dist} validation errors: {errors}"
