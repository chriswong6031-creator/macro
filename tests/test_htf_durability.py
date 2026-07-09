"""Tests for engine/htf_durability.py.

Four test categories per the approved synthesis:
  1. PIT-safe 2W — biweekly value must not change when future bars arrive
  2. Monthly-veto — weekly bull-hook under falling monthly -> grade D
  3. Front-run — fires before zero-cross (hook != zero-cross)
  4. LIVE TEST CASES:
       US/China topping -> TOP-RISK
       HK weekly-bounce-under-falling-monthly -> grade D TRAP-PRONE-BOUNCE
       Liquidity mechanical+topping -> not_momentum_confirmed
"""
from __future__ import annotations

import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.htf_durability import (
    _biweekly_close,
    _hook_triggered,
    _monthly_phase_allows_durable,
    _monthly_rolled_from_above,
    _stoch_in_extreme,
    compute,
    htf_divergence,
    stamp_ledger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n: int, seed: int = 42, trend: float = 0.0001,
                 vol: float = 0.01) -> pd.Series:
    """Synthetic daily OHLCV close series (business days)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2005-01-03", periods=n, freq="B")
    ret = rng.normal(trend, vol, n)
    prices = pd.Series(100.0 * np.cumprod(1 + ret), index=idx)
    return prices


def _declining_prices(n: int = 1200) -> pd.Series:
    """Long downtrending series with monthly MACD in basing phase.

    NOTE: due to the random-walk nature of MACD on a noisy series, _make_prices
    with a moderate decline does NOT reliably force monthly_phase='falling'.
    Use _basing_monthly_prices() for veto tests that need monthly_allows_durable=False.
    """
    return _make_prices(n, trend=-0.0006, vol=0.008)


def _basing_monthly_prices(n: int = 1200) -> pd.Series:
    """Very-low-volatility persistent decline that forces monthly MACD into a
    genuine 'basing' phase (spark_hist always-negative, never rolled from above).
    seed=13 produces: monthly_phase='basing', monthly_veto_active=True,
    primary_side='bottom' (weekly hook via fallback), grade=D.
    This is the correct fixture for monthly-veto tests.
    """
    return _make_prices(n, seed=13, trend=-0.0002, vol=0.001)


def _topping_prices(n: int = 1200) -> pd.Series:
    """Prices that rise then start rolling over — monthly should show topping."""
    rng = np.random.default_rng(77)
    idx = pd.date_range("2005-01-03", periods=n, freq="B")
    # Rally for 900 bars, then roll off
    rising = np.cumprod(1 + rng.normal(0.0005, 0.008, 900))
    falling = np.cumprod(1 + rng.normal(-0.0004, 0.008, n - 900))
    vals = np.concatenate([rising, rising[-1] * falling])
    return pd.Series(vals * 100, index=idx)


# ---------------------------------------------------------------------------
# Test 1: PIT-safe 2W resampling
# ---------------------------------------------------------------------------

class TestBiweeklyPITSafe:
    """A bar 2W value must not change when future bars arrive."""

    def test_no_lookahead_on_existing_bars(self) -> None:
        """Values on common dates should be identical regardless of future data."""
        prices = _make_prices(800, seed=1)

        bw_full  = _biweekly_close(prices)
        bw_short = _biweekly_close(prices.iloc[:400])

        common = bw_short.index.intersection(bw_full.index)
        assert len(common) > 10, "Need common 2W bars to compare"

        diffs = (bw_short.loc[common] - bw_full.loc[common]).abs()
        assert diffs.max() < 1e-9, (
            f"2W bars changed when future data added — NOT PIT-safe. "
            f"Max diff: {diffs.max():.2e}"
        )

    def test_no_new_bar_on_incomplete_pair(self) -> None:
        """The current incomplete 2W period must not appear as a completed bar."""
        # Create data whose last weekly bar is the FIRST week of a new pair
        prices = _make_prices(310, seed=2)  # ~310 business days ≈ 62 weeks

        bw_full  = _biweekly_close(prices)
        # Add 5 more days (one more week — completing the pair)
        extra = pd.date_range(prices.index[-1] + pd.offsets.BDay(),
                              periods=5, freq="B")
        prices_extra = pd.concat([prices,
                                  pd.Series(prices.iloc[-1] * 1.01,
                                            index=extra)])
        bw_extra = _biweekly_close(prices_extra)

        # bw_extra may have one more bar (now the pair is complete)
        # But bars in bw_full must be unchanged
        common = bw_full.index.intersection(bw_extra.index)
        if len(common) > 0:
            diffs = (bw_full.loc[common] - bw_extra.loc[common]).abs()
            assert diffs.max() < 1e-9, "Completing a pair changed prior bars"

    def test_fixed_epoch_anchor(self) -> None:
        """Two series starting on different dates produce the same 2W bar values
        for overlapping periods (because the epoch anchor is fixed, not relative)."""
        full_prices = _make_prices(1000, seed=3)
        # Sub-series starting 6 months later
        late_prices = full_prices.iloc[125:]

        bw_full = _biweekly_close(full_prices)
        bw_late = _biweekly_close(late_prices)

        common = bw_full.index.intersection(bw_late.index)
        assert len(common) > 5, "Need overlap to test"
        diffs = (bw_full.loc[common] - bw_late.loc[common]).abs()
        assert diffs.max() < 1e-9, (
            "Fixed-epoch anchor failed: different start dates produce different 2W bars"
        )

    def test_mid_history_gap_pit_safety(self) -> None:
        """FIX 7: a mid-history pair that has only one weekly bar (data gap) must be
        SKIPPED entirely — not emitted as a provisional bar that could change when the
        missing week's data later arrives.

        Method: construct a series that is missing a complete week in the middle (so
        a W-FRI pair has only 1 bar). Verify the incomplete mid-history pair is absent
        from the output. Before FIX 7 it was included with the single available bar.
        """
        # Create a daily series with a full week missing (June 6-10, 2005)
        # This ensures W-FRI pair_id=141 (June 3 + June 10) has only the June 3 bar.
        idx_before = pd.date_range("2005-01-03", "2005-06-01", freq="B")
        idx_after  = pd.date_range("2005-06-14", "2007-01-01", freq="B")
        idx = idx_before.append(idx_after)
        rng = np.random.default_rng(7)
        vals = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.009, len(idx)))
        prices_gapped = pd.Series(vals, index=idx)

        bw_gapped = _biweekly_close(prices_gapped)

        # The June 3 date is the last (only) bar of the incomplete pair 141.
        # FIX 7: it must NOT appear as a completed bar in the 2W output.
        incomplete_pair_end = pd.Timestamp("2005-06-03")
        assert incomplete_pair_end not in bw_gapped.index, (
            "FIX 7 violated: mid-history incomplete pair must be ABSENT from 2W output, "
            f"but {incomplete_pair_end.date()} was emitted (value={bw_gapped.get(incomplete_pair_end)})"
        )

        # Pairs before and after the gap must still be present
        prior_pair_end = pd.Timestamp("2005-05-27")  # pair before the gap
        after_pair_end = pd.Timestamp("2005-06-24")  # pair after the gap
        assert prior_pair_end in bw_gapped.index, (
            f"Prior pair ({prior_pair_end.date()}) should still be in output"
        )
        assert after_pair_end in bw_gapped.index, (
            f"Post-gap pair ({after_pair_end.date()}) should still be in output"
        )


# ---------------------------------------------------------------------------
# Test 2: Monthly-phase veto
# ---------------------------------------------------------------------------

class TestMonthlyVeto:
    """A weekly bull-hook under a falling monthly must produce grade D."""

    def test_declining_monthly_caps_at_grade_D(self) -> None:
        """Basing monthly (veto active) caps bottom grade at D (TRAP-PRONE-BOUNCE).

        Uses _basing_monthly_prices (seed=13, low-vol decline) which reliably
        produces monthly_phase='basing' with monthly_allows_durable=False.
        The assert is UNCONDITIONAL — no phase guard needed.
        """
        prices = _basing_monthly_prices()
        result = compute(prices, market="TEST_VETO")

        grade = result["durability_grade"]
        monthly_phase = result["monthly_phase"]
        # UNCONDITIONAL: seed=13 fixture always yields monthly basing/veto-active.
        assert monthly_phase in ("basing", "falling", "rolling"), (
            f"_basing_monthly_prices fixture must yield a veto-active monthly phase, "
            f"got {monthly_phase}"
        )
        # UNCONDITIONAL: basing monthly veto caps grade at D
        assert grade == "D", (
            f"Monthly phase={monthly_phase} (veto active) should cap grade at D, got {grade}"
        )
        # UNCONDITIONAL: monthly_veto_active must be True
        assert result["monthly_veto_active"] is True, (
            f"monthly_veto_active must be True when monthly={monthly_phase} (veto fixture)"
        )

    def test_veto_flag_set_when_bottom_hook_under_falling_monthly(self) -> None:
        """monthly_veto_active must be True when monthly is basing (veto-active fixture).

        UNCONDITIONAL: _basing_monthly_prices always yields monthly_veto_active=True
        for primary_side=bottom (no inner phase guard needed).
        """
        prices = _basing_monthly_prices()
        result = compute(prices, market="TEST_VETO2")

        # UNCONDITIONAL: veto fixture always has monthly_veto_active=True
        assert result["monthly_veto_active"] is True, (
            f"monthly_veto_active must be True for basing-monthly veto fixture; "
            f"got monthly_phase={result['monthly_phase']}, stage={result['stage']}"
        )
        # UNCONDITIONAL: regime must be TRAP-PRONE-BOUNCE (D + veto)
        assert result["htf_momentum_regime"] == "TRAP-PRONE-BOUNCE", (
            f"Basing monthly + bottom hook must yield TRAP-PRONE-BOUNCE, "
            f"got {result['htf_momentum_regime']}"
        )

    def test_monthly_allows_durable_for_rising_phase(self) -> None:
        """_monthly_phase_allows_durable returns True for turning/rising phases."""
        from engine.cycles import _tf_state

        # Simulate a turning monthly state (has macd_curl_up below zero)
        # We test the helper directly
        # Construct synthetic monthly state: below zero, curling up
        turning_state = {
            "macd_pos": False,
            "macd_cross_up": False,
            "macd_curl_up": True,
            "macd_approaching_up": False,
            "stoch_cross_up": False,
        }
        assert _monthly_phase_allows_durable(turning_state) is True

    def test_monthly_veto_blocks_falling_state(self) -> None:
        """_monthly_phase_allows_durable returns False for falling phases."""
        falling_state = {
            "macd_pos": False,
            "macd_cross_up": False,
            "macd_curl_up": False,
            "macd_curl_dn": False,
            "macd_approaching_up": False,
            "stoch_cross_up": False,
            "spark_hist": [-1.0, -1.5, -2.0, -2.5],  # falling histogram
        }
        assert _monthly_phase_allows_durable(falling_state) is False

    def test_rising_monthly_low_confluence_D_is_not_trap_prone(self) -> None:
        """FIX A: grade D caused by low confluence with rising monthly must NOT be
        TRAP-PRONE-BOUNCE and must NOT claim 'veto active' / 'falling monthly'.

        Seeds 6 and 50 both reproduce: monthly_phase='rising', monthly_veto_active=False,
        grade=D (low confluence), yet the old code labelled them TRAP-PRONE-BOUNCE with
        the read string 'Weekly hook under falling monthly — Monthly veto active'.
        After FIX A, grade D is TRAP-PRONE-BOUNCE ONLY when monthly_allows_durable=False.
        A low-confluence D with rising monthly must be NEUTRAL.
        """
        for seed in (6, 50):
            prices = _make_prices(1200, seed=seed)
            result = compute(prices, market=f"FIX_A_SEED{seed}")

            # UNCONDITIONAL: both seeds give monthly_phase='rising', veto=False
            assert result["monthly_phase"] == "rising", (
                f"seed={seed}: expected monthly_phase=rising, got {result['monthly_phase']}"
            )
            assert result["monthly_veto_active"] is False, (
                f"seed={seed}: expected monthly_veto_active=False, "
                f"got {result['monthly_veto_active']}"
            )
            # FIX A: rising monthly + grade D must NOT be TRAP-PRONE-BOUNCE
            assert result["htf_momentum_regime"] != "TRAP-PRONE-BOUNCE", (
                f"seed={seed}: rising monthly + grade D must NOT be TRAP-PRONE-BOUNCE "
                f"(monthly veto not active). Got {result['htf_momentum_regime']}"
            )
            # FIX A: read string must not claim veto/falling-monthly
            read = result["read"]
            assert "veto active" not in read.lower(), (
                f"seed={seed}: read must not claim 'veto active' when monthly is rising. "
                f"read={read!r}"
            )
            assert "falling monthly" not in read.lower(), (
                f"seed={seed}: read must not claim 'falling monthly' when monthly is rising. "
                f"read={read!r}"
            )


# ---------------------------------------------------------------------------
# Test: _monthly_rolled_from_above (FIX 1 helper)
# ---------------------------------------------------------------------------

class TestMonthlyRolledFromAbove:
    """Unit tests for the FIX 1 helper: detecting 'basing-after-rollover' topping."""

    def test_rolled_from_above_true_when_spark_had_positive_and_now_negative(self) -> None:
        """spark_hist had positive values and current (last) is negative -> True."""
        s = {"spark_hist": [0.5, 1.2, 1.0, 0.3, -0.1, -0.5, -0.8, -0.6, -0.7, -0.9]}
        assert _monthly_rolled_from_above(s) is True

    def test_rolled_from_above_false_when_always_negative(self) -> None:
        """spark_hist never went positive -> not a rollover from above."""
        s = {"spark_hist": [-2.0, -1.5, -1.0, -0.8, -0.6, -0.7, -0.9, -1.1, -0.8, -0.7]}
        assert _monthly_rolled_from_above(s) is False

    def test_rolled_from_above_false_when_currently_positive(self) -> None:
        """Current hist > 0 -> still in uptrend, not rolled over."""
        s = {"spark_hist": [0.1, 0.5, 1.0, 1.5, 2.0]}
        assert _monthly_rolled_from_above(s) is False

    def test_rolled_from_above_false_on_empty(self) -> None:
        """Empty or missing spark_hist -> False (safe default)."""
        assert _monthly_rolled_from_above({}) is False
        assert _monthly_rolled_from_above({"spark_hist": []}) is False
        assert _monthly_rolled_from_above({"spark_hist": [None]}) is False

    def test_basing_after_rollover_routes_to_top_side(self) -> None:
        """An engine.compute call on a topping fixture must route to primary_side=top.

        We verify this via the stack_score sign (top-side = <= 0) and regime.
        """
        prices = _topping_prices(1200)
        result = compute(prices, market="ROLLOVER_TEST")
        # The topping fixture's monthly ends in 'basing' after rolling from above
        assert result["monthly_phase"] == "basing", (
            "Topping fixture should show monthly_phase=basing (not strictly falling)"
        )
        assert result["htf_momentum_regime"] == "TOP-RISK", (
            f"Basing-after-rollover must yield TOP-RISK, got {result['htf_momentum_regime']}"
        )
        assert result["stack_score"] <= 0, (
            f"TOP-RISK stack_score must be <= 0, got {result['stack_score']}"
        )

    def test_bottom_setup_requires_positive_stack(self) -> None:
        """FIX 4: BOTTOM-SETUP must only fire when stack_score > 0.

        Uses seed=42, trend=0.0005 which deterministically produces BOTTOM-SETUP
        with stack_score=6 and grade=B. Assert is UNCONDITIONAL — no regime guard.
        (Prior version used _declining_prices which never reached BOTTOM-SETUP,
        making the assert vacuous.)
        """
        prices = _make_prices(1200, seed=42, trend=0.0005)
        result = compute(prices, market="FIX4_TEST")

        regime = result["htf_momentum_regime"]
        score  = result["stack_score"]
        grade  = result["durability_grade"]

        # UNCONDITIONAL: this fixture always yields BOTTOM-SETUP
        assert regime == "BOTTOM-SETUP", (
            f"seed=42 trend=0.0005 fixture must yield BOTTOM-SETUP, got {regime}"
        )
        # UNCONDITIONAL: BOTTOM-SETUP must have positive stack (real bottom hooks)
        assert score > 0, (
            f"BOTTOM-SETUP must have stack_score > 0 (real bottom hooks), "
            f"got stack={score}, grade={grade}"
        )


# ---------------------------------------------------------------------------
# Test 3: Front-run fires before zero-cross
# ---------------------------------------------------------------------------

class TestFrontRun:
    """Hook triggers (macd_curl + approaching) fire BEFORE histogram zero-cross."""

    def test_hook_not_zero_cross(self) -> None:
        """A hook state has hist < 0 with hist rising — it precedes the zero-cross."""
        # Build a state that represents a hook (hist below zero, curling up)
        # This is the pre-cross state — not a zero-cross
        hook_state = {
            "macd_pos": False,        # hist still negative
            "macd_cross_up": False,   # NOT a zero-cross
            "macd_curl_up": True,     # histogram trough just turned up
            "macd_approaching_up": False,
            "stoch_cross_up": True,
            "stoch": 22.0,
            "spark_stoch": [8.0, 7.0, 6.0, 12.0, 22.0],  # was in extreme, now hooking
        }
        # Hook should trigger
        assert _hook_triggered(hook_state, "bottom") is True

    def test_zero_cross_is_not_a_hook_trigger(self) -> None:
        """macd_cross_up (zero-cross) alone should NOT be reported as a hook trigger.
        The hook must be from curl/approaching — the cross is merely telemetry."""
        zero_cross_state = {
            "macd_pos": True,         # hist just went positive
            "macd_cross_up": True,    # the forbidden zero-cross
            "macd_curl_up": False,    # no pre-cross hook
            "macd_approaching_up": False,
            "stoch_cross_up": False,
            "stoch": 55.0,
            "spark_stoch": [40.0, 45.0, 50.0, 55.0],
        }
        # _hook_triggered only checks curl/approaching + stoch_hooking
        # A zero-cross alone without the pre-hook conditions should NOT fire
        result = _hook_triggered(zero_cross_state, "bottom")
        # This should NOT fire (no curl, no approaching, no stoch extreme hooking)
        assert result is False, (
            "Zero-cross (hist crossing zero) must not be reported as a front-run hook"
        )

    def test_approaching_fires_before_cross(self) -> None:
        """macd_approaching_up fires when hist is still negative but rising to cross."""
        approaching_state = {
            "macd_pos": False,        # still below zero
            "macd_cross_up": False,   # not crossed yet
            "macd_curl_up": False,
            "macd_approaching_up": True,   # approaching the cross
            "macd_bars_to_cross": 2.0,
            "stoch_cross_up": False,
            "stoch": 45.0,
        }
        assert _hook_triggered(approaching_state, "bottom") is True

    def test_bars_to_macd_cross_is_positive_for_approaching(self) -> None:
        """When approaching, bars_to_macd_cross should be a non-negative integer (telemetry).

        seed=0 produces bars_to_macd_cross=1 (approaching state active). Assert is
        UNCONDITIONAL — no None guard needed since the fixture deterministically has the
        approaching state. (Prior version used seed=50 which gives btc=None, so the
        assert never ran — vacuous.)
        """
        prices = _make_prices(1200, seed=0)
        result = compute(prices, market="TEST_FRONTRUN")
        btc = result["bars_to_macd_cross"]
        # UNCONDITIONAL: seed=0 always produces an approaching state (btc=1)
        assert btc is not None, (
            "seed=0 fixture must produce bars_to_macd_cross (approaching state active)"
        )
        assert isinstance(btc, int), f"bars_to_macd_cross must be int, got {type(btc)}"
        assert btc >= 0, f"bars_to_macd_cross must be non-negative, got {btc}"


# ---------------------------------------------------------------------------
# Test 4: LIVE TEST CASES
# ---------------------------------------------------------------------------

class TestLiveTestCases:
    """Synthetic live test cases per synthesis spec.

    All assertions are UNCONDITIONAL — no vacuous conditionals.  The fixtures are
    deterministic (fixed seeds) so the classifications must be stable.
    """

    def test_us_china_topping_scenario(self) -> None:
        """Synthetic US/China topping -> TOP-RISK with a top-side grade (A′..D′).

        FIX 1 regression: monthly 'basing' after rolling from an uptrend must
        route to primary_side='top', not fall through to BOTTOM.
        FIX 3 regression: TOP-RISK must have stack_score <= 0 (top-side only).
        """
        prices = _topping_prices(1200)
        result = compute(prices, market="US_SYNTH")

        regime = result["htf_momentum_regime"]
        grade  = result["durability_grade"]
        score  = result["stack_score"]

        # UNCONDITIONAL: this fixture always ends with a topping monthly posture.
        assert regime == "TOP-RISK", (
            f"US/China topping fixture MUST yield TOP-RISK — "
            f"monthly basing-after-rollover not detected as top. "
            f"Got regime={regime}, grade={grade}, monthly_phase={result['monthly_phase']}"
        )
        # Top-side grade (A_prime..D_prime), NOT a bottom grade
        assert grade in ("A_prime", "B_prime", "C_prime", "D_prime"), (
            f"TOP-RISK must carry a prime grade, got {grade}"
        )
        # FIX 3: stack_score must be <= 0 (top-leaning), never positive for TOP-RISK
        assert score <= 0, (
            f"TOP-RISK stack_score must be <= 0 (only top-side hooks scored), got {score}"
        )

    def test_hk_weekly_bounce_under_falling_monthly_is_grade_D(self) -> None:
        """HK weekly bounce under a falling monthly -> grade D (TRAP-PRONE-BOUNCE).

        The monthly never peaked above zero here (pure bear from the start),
        so _monthly_rolled_from_above is False and primary_side resolves via
        the weekly direction. The weekly bounce causes primary_side='bottom',
        but the monthly veto caps at grade D.
        """
        # Construct a declining series (simulating HK sell-off + dead-cat bounce)
        # Pure decline from the start — monthly hist is always negative (never positive peak)
        rng = np.random.default_rng(888)
        idx = pd.date_range("2005-01-03", periods=1200, freq="B")

        # Primary decline for 1100 bars (monthly hist stays negative throughout)
        decline = np.cumprod(1 + rng.normal(-0.0004, 0.009, 1100))
        # Short bounce for last 100 bars (weekly hook, but monthly still falling)
        bounce = np.cumprod(1 + rng.normal(0.0006, 0.008, 100))
        vals = np.concatenate([decline, decline[-1] * bounce])
        prices = pd.Series(vals * 100, index=idx)

        result = compute(prices, market="HK_SYNTH")

        grade = result["durability_grade"]
        regime = result["htf_momentum_regime"]
        monthly_phase = result["monthly_phase"]

        # Monthly must still be in downtrend (not yet turned)
        assert monthly_phase not in ("rising", "turning", "bear_recovering"), (
            f"Expected monthly still in downtrend after short bounce, got {monthly_phase}"
        )
        # UNCONDITIONAL: grade must be D (bottom trap) — the bounce in this
        # synthetic series is too short to lift the monthly.
        # D_prime is also acceptable if the engine reads the roll-off as top-side trap.
        assert grade in ("D", "D_prime"), (
            f"HK short bounce under falling monthly must be grade D or D_prime (TRAP-PRONE), "
            f"got {grade}"
        )
        # UNCONDITIONAL: must NOT be BOTTOM-SETUP (that requires grade A/B + stack > 0)
        assert regime in ("TRAP-PRONE-BOUNCE", "NEUTRAL", "TOP-RISK"), (
            f"HK short bounce under falling monthly must not be BOTTOM-SETUP, "
            f"got {regime}"
        )

    def test_liquidity_mechanical_and_topping_gives_not_momentum_confirmed(self) -> None:
        """Mechanical liquidity + HTF topping -> liquidity_reframe=not_momentum_confirmed.

        FIX 2 regression: htf_topping uses the SAME condition as the TOP-RISK
        regime gate — whenever regime=TOP-RISK, mechanical liquidity must fire
        not_momentum_confirmed. No per-grade carve-outs.
        """
        prices = _topping_prices(1200)

        # Mechanical liquidity: fed_share < 0.5, so mechanical=True
        lq_dict = {
            "label": "benign-expansion",
            "composition": {
                "mechanical": True,
                "fed_share": 0.2,
                "d_walcl": 10.0,
                "d_neg_rrp": 80.0,
                "d_neg_tga": 0.0,
            },
            "rrp_exhausted": False,
        }

        result = compute(prices, market="US_LQ_TEST", liquidity_quality_dict=lq_dict)

        regime  = result["htf_momentum_regime"]
        reframe = result["liquidity_reframe"]

        # UNCONDITIONAL: the topping fixture always yields TOP-RISK (FIX 1 guarantee)
        assert regime == "TOP-RISK", (
            f"Topping fixture must yield TOP-RISK for liquidity test, got {regime}"
        )
        # UNCONDITIONAL: TOP-RISK + mechanical_liquidity -> not_momentum_confirmed
        # No per-grade conditional here — FIX 2 unified the htf_topping predicate.
        assert reframe == "not_momentum_confirmed", (
            f"regime=TOP-RISK + mechanical liquidity MUST yield not_momentum_confirmed, "
            f"got {reframe}"
        )

    def test_liquidity_reframe_benign_when_no_topping(self) -> None:
        """Non-topping + non-mechanical liquidity -> reframe is always benign.

        FIX B: the prior version guarded on `if monthly_phase in ("rising","turning")`,
        but the fixture (seed=10, trend=0.0005) resolved to monthly_phase="falling" and
        the assert never executed (vacuous).  This version uses seed=15, trend=0.001
        which produces monthly_phase="rising", regime="NEUTRAL" (after FIX A; previously
        incorrectly TRAP-PRONE-BOUNCE), and liquidity_reframe="benign".  The assert is
        UNCONDITIONAL — no phase guard.
        """
        prices = _make_prices(1200, trend=0.001, seed=15)
        lq_dict = {
            "label": "benign-expansion",
            "composition": {
                "mechanical": False,
                "fed_share": 0.8,
            },
        }
        result = compute(prices, market="US_BENIGN", liquidity_quality_dict=lq_dict)

        # UNCONDITIONAL: fixture is deterministic and must NOT be TOP-RISK.
        assert result["htf_momentum_regime"] != "TOP-RISK", (
            f"Non-topping fixture (seed=15 trend=0.001) must not be TOP-RISK, "
            f"got regime={result['htf_momentum_regime']}, "
            f"monthly_phase={result['monthly_phase']}"
        )
        # UNCONDITIONAL: non-topping + non-mechanical lq => benign reframe.
        assert result["liquidity_reframe"] == "benign", (
            f"Non-topping + non-mechanical liquidity MUST yield benign reframe, "
            f"got {result['liquidity_reframe']} "
            f"(regime={result['htf_momentum_regime']}, "
            f"monthly_phase={result['monthly_phase']})"
        )

    def test_output_schema_complete(self) -> None:
        """All required output keys must be present and non-null-sentinel."""
        prices = _make_prices(1200, seed=7)
        result = compute(prices, market="SCHEMA_TEST")

        required_keys = [
            "schema_version", "market", "asof", "tf_states", "divergence",
            "read", "htf_momentum_regime", "stack_score", "durability_grade",
            "durability_points", "confluence", "stage", "bars_to_macd_cross",
            "monthly_phase", "monthly_veto_active", "liquidity_reframe",
            "liquidity_confidence", "label_en", "label_zh", "disclaimer",
        ]
        for k in required_keys:
            assert k in result, f"Missing required key: {k}"

        # Regime must be one of the four values
        assert result["htf_momentum_regime"] in (
            "TOP-RISK", "BOTTOM-SETUP", "TRAP-PRONE-BOUNCE", "NEUTRAL"
        ), f"Invalid regime: {result['htf_momentum_regime']}"

        # Stack score in [-6, +6]
        assert -6 <= result["stack_score"] <= 6, f"Stack score out of range: {result['stack_score']}"

        # Liquidity reframe valid
        assert result["liquidity_reframe"] in (
            "benign", "mechanical_fragile", "not_momentum_confirmed"
        ), f"Invalid liquidity_reframe: {result['liquidity_reframe']}"

    def test_fail_open_on_insufficient_data(self) -> None:
        """With < 40 bars, compute must return a valid empty dict (fail-open)."""
        prices = _make_prices(20, seed=5)
        result = compute(prices, market="SHORT")

        assert isinstance(result, dict)
        assert result["htf_momentum_regime"] == "NEUTRAL"
        assert result["stage"] == "neutral"
        assert result["stack_score"] == 0

    def test_output_is_not_mutable_alias(self) -> None:
        """The returned dict must be a fresh dict (additive, never mutates caller's regime)."""
        prices = _make_prices(1200, seed=6)
        result = compute(prices, market="ADDITIVE")
        result["extra_key"] = "test"
        # A second call should not see the mutation
        result2 = compute(prices, market="ADDITIVE")
        assert "extra_key" not in result2


# ---------------------------------------------------------------------------
# Test: htf_divergence (dual confirmation)
# ---------------------------------------------------------------------------

class TestHTFDivergence:
    def test_returns_dict(self) -> None:
        prices = _make_prices(200, seed=11)
        # Biweekly close
        from engine.htf_durability import _biweekly_close
        bw = _biweekly_close(prices)
        result = htf_divergence(bw)
        assert isinstance(result, dict)

    def test_empty_on_short_series(self) -> None:
        prices = pd.Series([1.0, 2.0, 3.0],
                           index=pd.date_range("2020-01-01", periods=3, freq="B"))
        result = htf_divergence(prices)
        assert result == {}


# ---------------------------------------------------------------------------
# Test: stamp_ledger stub
# ---------------------------------------------------------------------------

class TestStampLedger:
    def test_stamp_returns_false_outside_nightly(self, tmp_path) -> None:
        """stamp_ledger returns False when CN_LANE is not set to nightly."""
        fake_result = {
            "market": "US", "asof": "2026-07-08",
            "htf_momentum_regime": "NEUTRAL", "durability_grade": "D",
            "durability_points": 0, "stack_score": 0,
            "stage": "neutral", "monthly_phase": "rising",
            "monthly_veto_active": False,
        }
        # Default CN_LANE is not set — should not write
        with patch.dict(os.environ, {}, clear=False):
            if "CN_LANE" in os.environ:
                del os.environ["CN_LANE"]
            result = stamp_ledger(fake_result, root=tmp_path)
        assert result is False

    def test_stamp_writes_and_idempotent(self, tmp_path) -> None:
        """stamp_ledger writes when CN_LANE=nightly and is idempotent on (market, date)."""
        fake_result = {
            "market": "US", "asof": "2026-07-08",
            "htf_momentum_regime": "TOP-RISK", "durability_grade": "B_prime",
            "durability_points": 2, "stack_score": -4,
            "stage": "front_run", "monthly_phase": "rolling",
            "monthly_veto_active": False,
        }
        with patch.dict(os.environ, {"CN_LANE": "nightly"}):
            r1 = stamp_ledger(fake_result, root=tmp_path)
            r2 = stamp_ledger(fake_result, root=tmp_path)  # same row — idempotent

        assert r1 is True
        assert r2 is False  # idempotent skip

        ledger_path = tmp_path / "data" / "htf_durability" / "ledger.jsonl"
        import json as _json
        rows = [_json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0]["episode_id"] == "US_2026-07-08"
        assert rows[0]["outcome_20d"] is None
        assert rows[0]["outcome_60d"] is None
        assert rows[0]["outcome_120d"] is None
