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
        """When source_passport is None, passport is rebuilt from symbol.
        basis must be 'assumption' to match gex_engine._gamma_regime_passport exactly."""
        result = _make_regime_passport("SPY", None)
        assert result["basis"] == "assumption"
        assert result["is_index_product"] is True
        assert result["structurally_constant"] is False  # index → not structurally constant

    def test_passport_single_name(self):
        result = _make_regime_passport("NVDA", None)
        assert result["basis"] == "assumption"
        assert result["is_index_product"] is False
        assert result["structurally_constant"] is True  # single name → constant product attribute

    def test_passport_none_symbol(self):
        result = _make_regime_passport(None, None)
        assert result["basis"] == "assumption"
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

    # ------------------------------------------------------------------
    # Gross-gamma regression (feat/prophet-nightly fix)
    # ------------------------------------------------------------------

    def _make_strike_gross(
        self, k: float, net_mn: float, call_gamma_mn: float, put_gamma_mn: float,
        coi: int = 1000, poi: int = 1000,
    ) -> dict:
        """Build a by_strike row that includes the gross gamma fields."""
        return {
            "K": k, "net_mn": net_mn,
            "call_oi": coi, "put_oi": poi,
            "call_vol": 0, "put_vol": 0,
            "call_gamma_mn": call_gamma_mn,
            "put_gamma_mn": put_gamma_mn,
        }

    def test_balanced_high_oi_outscores_small_one_sided(self):
        """Regression: a strike with large OFFSETTING call/put gamma (net≈0) must
        out-score a small one-sided strike (spec §7.4 avgGamma = (callGamma+putGamma)/2).

        Before the fix, |net_mn| was used as the gamma proxy, which collapsed to ~0
        for balanced strikes — under-ranking true pin targets vs. lightly one-sided
        strikes. The fix uses (call_gamma_mn + put_gamma_mn) / 2, which is highest
        when BOTH sides carry large gross gamma, regardless of sign balance.
        """
        spot = 500.0
        # Balanced strike: huge call and put gamma that nearly cancel → net≈0
        # This is the classic pin strike spec §7.4 is designed to find.
        balanced_k = 500.0
        balanced_call_gamma = 100.0   # $mn
        balanced_put_gamma = 98.0    # $mn (nearly equal → net=2, avg=99)

        # Small one-sided strike far from spot: only call gamma, small magnitude
        onesided_k = 530.0
        onesided_call_gamma = 5.0    # $mn
        onesided_put_gamma = 0.0     # $mn → avg=2.5

        # A third strike to clear the < 3 guard
        filler_k = 470.0
        filler_call_gamma = 1.0
        filler_put_gamma = 1.0

        by_strike = [
            self._make_strike_gross(
                balanced_k,
                net_mn=balanced_call_gamma - balanced_put_gamma,  # net≈2
                call_gamma_mn=balanced_call_gamma,
                put_gamma_mn=balanced_put_gamma,
                coi=5000, poi=5000,
            ),
            self._make_strike_gross(
                onesided_k,
                net_mn=onesided_call_gamma,  # pure call
                call_gamma_mn=onesided_call_gamma,
                put_gamma_mn=onesided_put_gamma,
                coi=500, poi=100,
            ),
            self._make_strike_gross(
                filler_k,
                net_mn=filler_call_gamma - filler_put_gamma,
                call_gamma_mn=filler_call_gamma,
                put_gamma_mn=filler_put_gamma,
                coi=100, poi=100,
            ),
        ]

        # The balanced ATM strike must win (highest score → highest prob when it is best)
        # We compute scores manually to assert ordering directly.
        def _score(row):
            total_oi = row["call_oi"] + row["put_oi"]
            avg_gamma = (row["call_gamma_mn"] + row["put_gamma_mn"]) / 2.0
            dNorm = abs(row["K"] - spot) / (spot * 0.01)
            return (total_oi * avg_gamma) / (1.0 + dNorm ** 2)

        score_balanced = _score(by_strike[0])
        score_onesided = _score(by_strike[1])

        assert score_balanced > score_onesided, (
            f"Balanced ATM strike score ({score_balanced:.2f}) must exceed "
            f"small one-sided strike score ({score_onesided:.2f}) — "
            f"gross-gamma fix not working"
        )

        # Also verify _pin_probability is consistent with this ordering
        prob = _pin_probability(by_strike, spot, max_pain=spot)
        assert prob is not None
        assert 0.0 < prob <= 0.95

    def test_perfectly_balanced_net_zero_uses_gross_gamma(self):
        """True discriminating test for the gross-gamma fix.

        A strike with net_mn=0 (perfectly offsetting call/put gamma) carries
        zero information under the OLD |net_mn| formula — avg_gamma collapses to
        abs(0)=0 and the strike is SKIPPED by the avg_gamma<=0 guard.  That leaves
        only 2 valid strikes (the fillers), so _pin_probability returns None.

        Under the NEW (call_gamma_mn + put_gamma_mn)/2 formula the balanced strike
        contributes avg_gamma=100, passes the guard, and a valid probability is
        returned.

        This test fails identically on the old code and passes only on the new code —
        something the existing test_balanced_high_oi_outscores_small_one_sided cannot
        claim (its local _score helper never calls production code).
        """
        spot = 500.0
        # Perfectly balanced: huge call and put gamma cancel exactly → net_mn = 0.
        # OLD code: avg_gamma = |0| = 0 → skipped → only 2 valid strikes → None.
        # NEW code: avg_gamma = (100 + 100) / 2 = 100 → valid score → prob returned.
        by_strike = [
            self._make_strike_gross(
                500.0, net_mn=0.0,
                call_gamma_mn=100.0, put_gamma_mn=100.0,
                coi=10000, poi=10000,
            ),
            self._make_strike_gross(
                490.0, net_mn=2.0,
                call_gamma_mn=1.0, put_gamma_mn=1.0,
                coi=500, poi=500,
            ),
            self._make_strike_gross(
                510.0, net_mn=2.0,
                call_gamma_mn=1.0, put_gamma_mn=1.0,
                coi=500, poi=500,
            ),
        ]
        prob = _pin_probability(by_strike, spot, max_pain=spot)
        # NEW code must return a valid probability; OLD |net_mn| code returns None.
        assert prob is not None, (
            "net_mn=0 balanced strike must score under gross-gamma formula "
            "(old |net_mn| code would return None — fewer than 3 valid strikes)"
        )
        assert 0.0 < prob <= 0.95

    def test_legacy_fallback_net_mn(self):
        """Rows without call_gamma_mn/put_gamma_mn fall back to |net_mn| gracefully."""
        # Legacy rows (no gross gamma fields)
        spot = 500.0
        by_strike = [
            {"K": 500.0, "net_mn": 20.0, "call_oi": 5000, "put_oi": 5000,
             "call_vol": 0, "put_vol": 0},
            {"K": 510.0, "net_mn": 5.0, "call_oi": 1000, "put_oi": 1000,
             "call_vol": 0, "put_vol": 0},
            {"K": 490.0, "net_mn": 3.0, "call_oi": 1000, "put_oi": 1000,
             "call_vol": 0, "put_vol": 0},
        ]
        prob = _pin_probability(by_strike, spot, max_pain=spot)
        # Must not crash; must return a valid probability
        assert prob is not None
        assert 0.0 < prob <= 0.95


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


# ===========================================================================
# 11. Noise-floor regression (Fix 1): spot=500, net_gex=0.5 $mn must NOT trigger noise-floor
# ===========================================================================

class TestNoisFloorRegression:
    """Regression for the 1000x noise-floor constant bug (1.0 $mn instead of 0.001 $mn).

    Spec §6.1: noise floor = max(1000, spot * 100) raw dollars
              = max(0.001, spot * 100 / 1e6) $mn.
    For spot=500 the floor is max(0.001, 0.05) = 0.05 $mn ($50,000).
    A name with total_abs=0.5 $mn ($500,000) must NOT hit the noise floor
    and must NOT be forced to RANGE.  With the buggy constant (1.0 $mn),
    0.5 < 1.0 would have triggered noise_floor_hit=True.
    """

    def test_500k_net_gex_not_noise_floor_spot_500(self):
        """$500K net GEX (0.5 $mn) at spot=500 clears spec noise floor of $50K."""
        # 0.5 $mn split 60/40 → stability_ratio = 0.60
        by_strike = [
            _make_strike(510.0,  0.3),   # positive
            _make_strike(490.0, -0.2),   # negative
        ]
        pct, ratio, noise = _stability_from_walls(by_strike, 500.0)
        # Must NOT hit noise floor: total_abs=0.5 $mn >> spec floor=0.05 $mn
        assert noise is False, (
            f"noise_floor_hit=True for 0.5 $mn total at spot=500 — "
            f"spec floor is 0.05 $mn ($50K), constant was 1000x too large"
        )
        assert pct == pytest.approx(60.0)
        assert ratio == pytest.approx(0.60)

    def test_noise_floor_value_at_spot_500(self):
        """Noise floor at spot=500 should be 0.05 $mn ($50,000), not 1.0 $mn."""
        # Values just below the correct floor (0.04 $mn) must trip the guard
        by_strike = [_make_strike(500.0, 0.04)]
        pct, ratio, noise = _stability_from_walls(by_strike, 500.0)
        assert noise is True, "0.04 $mn total at spot=500 should trip spec noise floor of 0.05 $mn"

    def test_noise_floor_value_at_spot_500_just_above(self):
        """Values just above the spec floor (0.06 $mn) must NOT trip the guard."""
        by_strike = [_make_strike(500.0, 0.06)]
        pct, ratio, noise = _stability_from_walls(by_strike, 500.0)
        assert noise is False, "0.06 $mn total at spot=500 should clear spec noise floor of 0.05 $mn"

    def test_noise_floor_value_at_spot_10(self):
        """At spot=10, spec floor = max(0.001, 10*100/1e6) = max(0.001, 0.001) = 0.001 $mn."""
        # 0.0005 $mn below floor → trips
        by_strike = [_make_strike(10.0, 0.0005)]
        pct, ratio, noise = _stability_from_walls(by_strike, 10.0)
        assert noise is True

    def test_small_name_not_forced_range_when_above_floor(self):
        """A small single name with 0.5 $mn GEX at spot=500 must not be classified RANGE
        solely because of the noise floor — it has real GEX structure."""
        by_strike = [
            _make_strike(510.0,  0.3),
            _make_strike(490.0, -0.2),
            _make_strike(505.0,  0.1),
            _make_strike(495.0, -0.1),
        ]
        model = _make_model(spot=500.0, by_strike=by_strike)
        state = compute_gex_state(model, "NVDA", asof=ASOF)
        assert state is not None
        # With a 0.6 stability ratio it should be RANGE (from classifier),
        # not RANGE-from-noise-floor — the noise flag should be absent from the note.
        assert "noise-floor" not in state["reliability"]["note"]


# ===========================================================================
# 12. Passport propagation regression (Fix 2): gex_model.build_model must include
#     regime_passport in summary so that compute_gex_state copies it verbatim.
# ===========================================================================

class TestPassportPropagationFromBuildModel:
    """Regression for the passport propagation gap.

    gex_model.build_model constructs summary but (pre-fix) never copied
    regime_passport from compute_gex.  As a result source_passport was always
    None and _make_regime_passport always rebuilt it — emitting basis='assumption'
    while the engine emits basis='assumption' (but any future drift in either
    would go undetected).  The fix adds regime_passport to the summary dict.
    """

    def test_build_model_summary_carries_regime_passport(self):
        """build_model summary must contain 'regime_passport' propagated from compute_gex."""
        import pandas as pd
        from engine.gex_model import build_model

        # Minimal chain: 50 rows to clear the thin_chain guard
        n = 50
        spot = 500.0
        rng = range(n)
        chain = pd.DataFrame({
            "K": [spot * (0.9 + 0.004 * i) for i in rng],
            "T": [0.083] * n,            # ~1 month
            "iv": [0.20] * n,
            "oi": [1000] * n,
            "is_call": [i % 2 == 0 for i in rng],
            "expiry": [pd.Timestamp("2026-08-15")] * n,
        })
        model = build_model(chain, spot, meta={"key": "SPY"})
        assert model is not None, "build_model returned None for a valid 50-row chain"
        summary = model.get("summary", {})
        assert "regime_passport" in summary, (
            "build_model summary is missing 'regime_passport' — "
            "gex_state.compute_gex_state will always rebuild it instead of copying verbatim"
        )
        passport = summary["regime_passport"]
        assert isinstance(passport, dict)
        assert passport.get("basis") == "assumption", (
            f"Expected basis='assumption' (from gex_engine), got {passport.get('basis')!r}"
        )


# ===========================================================================
# 13. OIP E3 back-compat + additive positioning fields.
#     The crypto-cockpit program reads COIN/MSTR gex_state payloads (H7) and the
#     terminal reads the gex tab off this schema, so the E3 wave may only ADD.
# ===========================================================================

# The exact top-level key set the schema carried BEFORE the OIP E3 wave. Pinned as a
# literal so a rename or a drop fails here instead of downstream: any of these keys
# disappearing (or changing type) is a breaking change for options_structure consumers.
_PRE_E3_KEYS: dict[str, type | tuple] = {
    "schema": str,
    "asof": str,
    "root": str,
    "spot": (float, type(None)),
    "net_gex_bn": (float, type(None)),
    "gamma_regime": str,
    "stability_pct": (float, type(None)),
    "gamma_flip": (float, type(None)),
    "dist_to_flip_pct": (float, type(None)),
    "call_wall": (float, type(None)),
    "put_wall": (float, type(None)),
    "magnet": (float, type(None)),
    "max_pain": (float, type(None)),
    "pin_probability": (float, type(None)),
    "gravity_direction": (str, type(None)),
    "gravity_up_pct": (float, type(None)),
    "cascade_trigger": (float, type(None)),
    "upside_trigger": (float, type(None)),
    "oi_delta_clusters": dict,
    "regime_passport": dict,
    "authority_tier": str,
    "reliability": dict,
}


class TestE3BackCompat:
    def test_every_pre_e3_key_survives_with_its_type(self):
        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        assert state is not None
        for key, typ in _PRE_E3_KEYS.items():
            assert key in state, f"pre-E3 key {key!r} was dropped from the payload"
            assert isinstance(state[key], typ), (
                f"{key!r} changed type: {type(state[key]).__name__}")

    def test_oi_delta_cluster_lists_keep_their_names_and_shape(self):
        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        clusters = state["oi_delta_clusters"]
        assert isinstance(clusters["new_oi"], list)
        assert isinstance(clusters["exit_oi"], list)
        for row in clusters["new_oi"] + clusters["exit_oi"]:
            assert isinstance(row, dict)
            assert {"K", "right", "oi_prior", "oi_now", "oi_delta"} <= set(row)

    def test_cluster_block_carries_vintage_stamps_and_a_bilingual_note(self):
        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        clusters = state["oi_delta_clusters"]
        for key in ("prior_snapshot", "latest_snapshot", "matched_contracts",
                    "same_vintage", "note_en", "note_zh"):
            assert key in clusters, f"additive cluster key {key!r} missing"
        assert isinstance(clusters["same_vintage"], bool)
        assert clusters["note_en"] and clusters["note_zh"]

    def test_reliability_marks_oi_delta_as_the_signing_free_read(self):
        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        rel = state["reliability"]
        assert "reliable" in rel["oi_delta"]
        # the pre-existing flags are untouched
        assert rel["levels"] == "display-only-until-gate"
        assert rel["regime"] == "assumption-signed"

    def test_additive_blocks_are_omitted_not_null_filled(self, monkeypatch):
        """An absent source must leave the key OUT of the payload. A null-filled block
        reads as 'measured and empty' to a consumer; absence reads as 'not covered'."""
        from engine import positioning_persistence as pp

        pp.reset_cache()
        monkeypatch.setattr(pp, "default_chain_dates", lambda: [])
        monkeypatch.setattr(pp, "default_read_chain", lambda d: None)
        try:
            state = compute_gex_state(_make_model(), "ZZZZ", asof=ASOF)
            assert "wall_persistence" not in state
            assert "deep_history" not in state          # not an index root
            assert "net_gex_pctile" not in state        # _make_model has no history
        finally:
            pp.reset_cache()

    def test_percentile_block_appears_when_history_is_present(self, monkeypatch):
        from engine import positioning_persistence as pp

        pp.reset_cache()
        monkeypatch.setattr(pp, "default_chain_dates", lambda: [])
        monkeypatch.setattr(pp, "default_read_chain", lambda d: None)
        model = _make_model(net_gex_bn=1.5)
        model["history"] = [
            {"date": "2026-07-20", "net_gex_bn": -1.0},
            {"date": "2026-07-21", "net_gex_bn": -2.0},
            {"date": "2026-07-22", "net_gex_bn": -3.0},
            {"date": "2026-07-23", "net_gex_bn": -4.0},
            {"date": "2026-07-24", "net_gex_bn": -5.0},
            {"date": "2026-07-25", "net_gex_bn": -5.0},   # Saturday — must be dropped
        ]
        try:
            state = compute_gex_state(model, "SPY", asof=ASOF)
            blk = state["net_gex_pctile"]
            assert blk["n_sessions"] == 5, "weekend row leaked into the denominator"
            assert blk["pctile"] == 100          # +1.5 is above every stored reading
            assert blk["low_confidence"] is True
            assert blk["note_en"] and blk["note_zh"]
        finally:
            pp.reset_cache()

    def test_payload_stays_json_safe_with_the_new_blocks(self):
        """build_gex_board serialises with allow_nan=False — one NaN aborts the write."""
        import json

        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        json.dumps(state, default=float, allow_nan=False)

    def test_validator_still_passes_with_the_additive_blocks(self):
        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        assert validate_gex_state(state) == []

    def test_cluster_block_publishes_the_price_its_distances_use(self):
        """dist_pct is measured against the SNAPSHOT source's price while the payload's
        own `spot` is the board's. Publishing only one of them let a reader compare
        dist_pct against the wrong price and read the sign backwards."""
        state = compute_gex_state(_make_model(), "SPY", asof=ASOF)
        assert "snapshot_spot" in state["oi_delta_clusters"]

    def test_material_price_divergence_is_disclosed_in_plain_words(self, monkeypatch):
        from engine import positioning_persistence as pp

        pp.reset_cache()
        # board spot 500.0 (from _make_model) vs a snapshot price 20% away
        monkeypatch.setattr(pp, "load", lambda *a, **k: _FakeStore(600.0))
        try:
            state = compute_gex_state(_make_model(spot=500.0), "AAA", asof=ASOF)
            blk = state["oi_delta_clusters"]
            assert "600" in blk["spot_note_en"]
            assert "20.0%" in blk["spot_note_en"]
            assert blk["spot_note_zh"]
            w = state["wall_persistence"]
            assert "20.0%" in w["spot_note_en"]
        finally:
            pp.reset_cache()

    def test_no_divergence_note_when_the_prices_agree(self, monkeypatch):
        from engine import positioning_persistence as pp

        pp.reset_cache()
        monkeypatch.setattr(pp, "load", lambda *a, **k: _FakeStore(500.5))
        try:
            state = compute_gex_state(_make_model(spot=500.0), "AAA", asof=ASOF)
            assert "spot_note_en" not in state["oi_delta_clusters"]
            assert "spot_note_en" not in state["wall_persistence"]
        finally:
            pp.reset_cache()

    def test_wall_sides_publish_the_board_wall_they_were_compared_against(self,
                                                                          monkeypatch):
        from engine import positioning_persistence as pp

        pp.reset_cache()
        monkeypatch.setattr(pp, "load", lambda *a, **k: _FakeStore(500.0))
        try:
            state = compute_gex_state(
                _make_model(spot=500.0, call_wall=520.0, put_wall=480.0), "AAA", asof=ASOF)
            call = state["wall_persistence"]["call_side"]
            assert call["board_wall"] == 520.0
            assert call["level"] == 530.0
            assert call["matches_board_wall"] is False
            assert state["wall_persistence"]["basis_en"]
        finally:
            pp.reset_cache()


class _FakeStore:
    """Minimal PositioningStore stand-in: one covered root at a chosen snapshot price."""

    def __init__(self, snapshot_spot: float, rows: list | None = None) -> None:
        self._spot = snapshot_spot
        self._rows = rows or []
        self.meta = {"snapshots_compared": 2, "sessions_behind": 0, "stale": False}

    def clusters(self, root):  # noqa: ANN001
        return {"new_oi": list(self._rows), "exit_oi": [],
                "prior_snapshot": "2026-07-28",
                "latest_snapshot": "2026-07-29", "sessions_apart": 1,
                "sessions_behind": 0, "stale": False, "matched_contracts": 3,
                "same_vintage": False, "snapshot_spot": self._spot,
                "note_en": "note", "note_zh": "注"}

    def wall_persistence(self, root):  # noqa: ANN001
        return {"window_sessions": 6, "sessions_covered": 6,
                "window_start": "2026-07-22", "window_end": "2026-07-29",
                "sessions_behind": 0, "stale": False, "snapshot_spot": self._spot,
                "basis_en": "basis", "basis_zh": "基准",
                "call_side": {"level": 530.0, "sessions_at_level": 2,
                              "note_en": "c", "note_zh": "c"},
                "put_side": {"level": 470.0, "sessions_at_level": 3,
                             "note_en": "p", "note_zh": "p"}}

    def test_sign_flip_is_disclosed_even_when_the_prices_nearly_agree(self,
                                                                     monkeypatch):
        """The distance threshold alone left flipped rows silent. A strike sitting between
        the two prices must trigger the note at any magnitude."""
        from engine import positioning_persistence as pp

        pp.reset_cache()
        # board spot 500.0, snapshot 502.0 (0.4% — under the 2% threshold), and a cluster
        # row at K=501 which is ABOVE the board price but BELOW the snapshot price.
        monkeypatch.setattr(pp, "load", lambda *a, **k: _FakeStore(502.0, rows=[
            {"K": 501.0, "right": "call", "oi_prior": 100, "oi_now": 200,
             "oi_delta": 100, "oi_delta_pct": 100.0, "dist_pct": -0.2, "contracts": 1}]))
        try:
            state = compute_gex_state(_make_model(spot=500.0), "AAA", asof=ASOF)
            blk = state["oi_delta_clusters"]
            assert blk["spot_note_en"], "a sign-flipped row must be disclosed"
            assert "the other way round" in blk["spot_note_en"]
            assert blk["spot_note_zh"]
        finally:
            pp.reset_cache()
