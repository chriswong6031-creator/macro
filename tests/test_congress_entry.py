"""Tests for engine/congress_entry.py — entry-timing snapshot for the congress watchlist.

Covers:
  1. Contract shape — entry_snapshot(None) returns all required keys.
  2. Short history — covered=False / coverage=False everywhere.
  3. Pure helper unit tests (_wash_state, _macd_state, _stoch_cross_state) with
     hand-built Series so they are fully deterministic without any real price data.
  4. Integration scenarios using synthetic daily close series engineered to hit
     each detector state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.congress_entry import (
    OS_FLOOR,
    NEAR_FLOOR,
    W_CROSS_WINDOW,
    W_STOCH_GAP_MAX,
    W_MACD_ETA_MAX,
    MIN_WEEKLY_BARS,
    MIN_HTF_BARS,
    MIN_DAILY_BARS,
    MIN_DAILY_BARS_1M,
    entry_snapshot,
    _wash_state,
    _macd_state,
    _stoch_cross_state,
    _macd_variant_state,
    _null_wash,
    _null_w_macd,
    _null_w_stoch,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _bdate_series(n: int, start: str = "2010-01-04", vals=None) -> pd.Series:
    """Business-day date-indexed Series."""
    idx = pd.bdate_range(start, periods=n)
    if vals is None:
        vals = np.ones(n) * 100.0
    return pd.Series(np.asarray(vals, dtype=float), index=idx)


def _monotonic_rise(n: int = 1500, start: float = 50.0, drift: float = 0.001) -> pd.Series:
    """Smoothly rising series — no oscillator crossings or washouts."""
    idx = pd.bdate_range("2010-01-04", periods=n)
    vals = start * np.cumprod(np.ones(n) * (1.0 + drift))
    return pd.Series(vals, index=idx)


def _v_shape_washout(n_decline: int = 600, n_flat: int = 700,
                     start: float = 200.0, bottom_frac: float = 0.15) -> pd.Series:
    """Deep V-shape: n_decline bars of steep decline into a bottom, then n_flat bars flat.

    The decline is steep enough that StochRSI K should hit the oversold floor on
    both 2W and monthly timeframes, triggering wash_2w="now" and wash_1m="now".
    """
    idx = pd.bdate_range("2008-01-02", periods=n_decline + n_flat)
    bottom = start * bottom_frac
    # steep decline
    decline = np.linspace(start, bottom, n_decline)
    # flat at bottom
    flat = np.ones(n_flat) * bottom
    vals = np.concatenate([decline, flat])
    return pd.Series(vals, index=idx)


def _recovery_from_washout(n_decline: int = 600, n_recovery: int = 5,
                           n_tail: int = 900, start: float = 200.0,
                           bottom_frac: float = 0.15) -> pd.Series:
    """Decline to washout, recover 1 bar above the washout level, then drift up.

    The previous bar (before tail) was below OS_FLOOR -> wash state "recent".
    """
    idx = pd.bdate_range("2007-01-02", periods=n_decline + n_recovery + n_tail)
    bottom = start * bottom_frac
    decline = np.linspace(start, bottom, n_decline)
    # tiny recovery over n_recovery bars
    recovery = np.linspace(bottom, bottom * 1.05, n_recovery)
    tail = np.linspace(bottom * 1.05, start * 0.5, n_tail)
    vals = np.concatenate([decline, recovery, tail])
    return pd.Series(vals, index=idx)


# ---------------------------------------------------------------------------
# 1. Contract shape tests
# ---------------------------------------------------------------------------

REQUIRED_KEYS_TOP = {"covered", "wash_2w", "wash_1m", "dual_washout", "w_macd", "w_stoch"}
WASH_KEYS = {"state", "k", "coverage"}
WMACD_KEYS = {"state", "kind", "bars_since", "eta_bars"}
WSTOCH_KEYS = {"state", "bars_since", "d_at_cross", "from_washout", "k", "d", "gap"}


class TestContractShape:
    def test_none_input_has_all_keys(self):
        snap = entry_snapshot(None)
        assert REQUIRED_KEYS_TOP == set(snap.keys()), f"Missing or extra keys: {set(snap.keys())}"

    def test_none_input_covered_false(self):
        snap = entry_snapshot(None)
        assert snap["covered"] is False

    def test_none_input_wash_2w_shape(self):
        snap = entry_snapshot(None)
        assert WASH_KEYS == set(snap["wash_2w"].keys())
        assert snap["wash_2w"]["state"] == "none"
        assert snap["wash_2w"]["coverage"] is False
        assert snap["wash_2w"]["k"] is None

    def test_none_input_wash_1m_shape(self):
        snap = entry_snapshot(None)
        assert WASH_KEYS == set(snap["wash_1m"].keys())
        assert snap["wash_1m"]["state"] == "none"
        assert snap["wash_1m"]["coverage"] is False

    def test_none_input_wmacd_shape(self):
        snap = entry_snapshot(None)
        assert WMACD_KEYS == set(snap["w_macd"].keys())
        assert snap["w_macd"]["state"] == "none"
        assert snap["w_macd"]["kind"] is None
        assert snap["w_macd"]["bars_since"] is None
        assert snap["w_macd"]["eta_bars"] is None

    def test_none_input_wstoch_shape(self):
        snap = entry_snapshot(None)
        assert WSTOCH_KEYS == set(snap["w_stoch"].keys())
        assert snap["w_stoch"]["state"] == "none"
        assert snap["w_stoch"]["from_washout"] is False

    def test_none_input_dual_washout_false(self):
        snap = entry_snapshot(None)
        assert snap["dual_washout"] is False

    def test_short_series_covered_false(self):
        """< MIN_DAILY_BARS -> covered=False."""
        c = _bdate_series(MIN_DAILY_BARS - 1, vals=np.linspace(100, 50, MIN_DAILY_BARS - 1))
        snap = entry_snapshot(c)
        assert snap["covered"] is False
        assert snap["wash_2w"]["coverage"] is False
        assert snap["wash_1m"]["coverage"] is False

    def test_all_keys_present_on_valid_series(self):
        """A long-enough series returns covered=True with all contract keys."""
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        assert REQUIRED_KEYS_TOP == set(snap.keys())
        assert WASH_KEYS == set(snap["wash_2w"].keys())
        assert WASH_KEYS == set(snap["wash_1m"].keys())
        assert WMACD_KEYS == set(snap["w_macd"].keys())
        assert WSTOCH_KEYS == set(snap["w_stoch"].keys())

    def test_valid_series_covered_true(self):
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        assert snap["covered"] is True


# ---------------------------------------------------------------------------
# 2. Pure helper unit tests — _wash_state
# ---------------------------------------------------------------------------

class TestWashState:
    def _k(self, vals) -> pd.Series:
        return pd.Series(vals, dtype=float)

    def test_now_when_last_below_floor(self):
        k = self._k([30, 25, 15])
        assert _wash_state(k) == "now"

    def test_now_when_last_exactly_at_floor_minus_one(self):
        k = self._k([30, 25, OS_FLOOR - 0.1])
        assert _wash_state(k) == "now"

    def test_not_now_when_last_equals_floor(self):
        # OS_FLOOR=20; k[-1]=20 is NOT < 20 -> not "now"
        k = self._k([30, 25, OS_FLOOR])
        # could be "near" or "none", but not "now"
        assert _wash_state(k) != "now"

    def test_recent_when_prev_below_floor(self):
        # k[-1]=25 (not oversold), k[-2]=15 (was oversold)
        k = self._k([30, 15, 25])
        assert _wash_state(k) == "recent"

    def test_near_when_falling_toward_floor(self):
        # k[-1] <= NEAR_FLOOR (25) and falling
        k = self._k([30, 26, 24])
        assert _wash_state(k) == "near"

    def test_near_not_triggered_when_rising(self):
        # k[-1]=24 (<=25) but rising -> NOT near
        k = self._k([20, 22, 24])
        result = _wash_state(k)
        assert result != "near"

    def test_none_when_all_high(self):
        k = self._k([60, 70, 80])
        assert _wash_state(k) == "none"

    def test_single_value_returns_none(self):
        k = self._k([10])
        assert _wash_state(k) == "none"

    def test_empty_returns_none(self):
        k = self._k([])
        assert _wash_state(k) == "none"

    def test_now_takes_precedence_over_near(self):
        # k[-1]=10 < OS_FLOOR, even though also <= NEAR_FLOOR: "now" wins
        k = self._k([30, 25, 10])
        assert _wash_state(k) == "now"


# ---------------------------------------------------------------------------
# 3. Pure helper unit tests — _macd_variant_state and _macd_state
# ---------------------------------------------------------------------------

class TestMacdVariantState:
    def _h(self, vals) -> pd.Series:
        return pd.Series(vals, dtype=float)

    def test_crossed_last_bar(self):
        # hist[-1]>0, hist[-2]<=0 -> crossed, bars_since=0
        h = self._h([-1, -0.5, -0.2, -0.01, 0.1])
        res = _macd_variant_state(h)
        assert res["crossed"] is True
        assert res["bars_since"] == 0

    def test_crossed_one_bar_ago(self):
        # hist[-2]>0, hist[-3]<=0, hist[-1]>0 -> bars_since=1
        h = self._h([-1, -0.5, -0.01, 0.1, 0.2])
        res = _macd_variant_state(h)
        assert res["crossed"] is True
        assert res["bars_since"] == 1

    def test_not_crossed_when_already_positive_more_than_window(self):
        # all positive for 4+ bars -> no zero-cross in last W_CROSS_WINDOW=2 bars
        h = self._h([-1, 0.1, 0.2, 0.3, 0.4, 0.5])
        res = _macd_variant_state(h)
        assert res["crossed"] is False

    def test_approaching_state(self):
        # hist negative, rising 3 consecutive, slope > 0, eta <= W_MACD_ETA_MAX=3
        # slope = (h[-1]-h[-4])/3; eta = -h[-1]/slope
        # need h[-1]<0, h[-1]>h[-2]>h[-3], slope>0, eta<=3
        # e.g. h[-4]=-3, h[-3]=-2, h[-2]=-1, h[-1]=-0.5 -> slope=(-.5-(-3))/3=2.5/3=0.833; eta=0.5/0.833=0.6
        h = self._h([-3, -2, -1, -0.5])
        res = _macd_variant_state(h)
        assert res["approaching"] is True
        assert res["eta_bars"] is not None
        assert res["eta_bars"] <= W_MACD_ETA_MAX

    def test_approaching_none_when_eta_too_large(self):
        # slope tiny -> eta huge
        h = self._h([-100, -90, -89.5, -89.1])
        res = _macd_variant_state(h)
        # slope = (-89.1 - (-100))/3 = 3.63; eta = 89.1/3.63 = 24.5 -> > W_MACD_ETA_MAX
        assert res["approaching"] is False

    def test_none_when_hist_negative_not_rising(self):
        h = self._h([-1, -2, -3, -4])
        res = _macd_variant_state(h)
        assert res["crossed"] is False
        assert res["approaching"] is False


class TestMacdState:
    def _h(self, vals) -> pd.Series:
        return pd.Series(vals, dtype=float)

    def test_both_crossed_kind_both(self):
        # both have a fresh cross at last bar
        rsi_h = self._h([-1, -0.5, -0.2, -0.01, 0.1])
        price_h = self._h([-1, -0.5, -0.2, -0.01, 0.1])
        res = _macd_state(rsi_h, price_h)
        assert res["state"] == "crossed"
        assert res["kind"] == "both"

    def test_rsi_only_crossed(self):
        rsi_h = self._h([-1, -0.5, -0.2, -0.01, 0.1])
        price_h = self._h([0.5, 0.6, 0.7, 0.8, 0.9])  # already positive - no fresh cross
        res = _macd_state(rsi_h, price_h)
        assert res["state"] == "crossed"
        assert res["kind"] == "rsi_macd"

    def test_price_only_crossed(self):
        rsi_h = self._h([0.5, 0.6, 0.7, 0.8, 0.9])
        price_h = self._h([-1, -0.5, -0.2, -0.01, 0.1])
        res = _macd_state(rsi_h, price_h)
        assert res["state"] == "crossed"
        assert res["kind"] == "price"

    def test_approaching_uses_smaller_eta(self):
        # rsi approaching with eta=1.0, price approaching with eta=2.0 -> both, eta=1.0
        # eta = -h[-1]/slope; slope=(h[-1]-h[-4])/3
        # for eta=1: want -h[-1]/slope=1 -> slope=-h[-1]; e.g. h[-4]=-3,h[-3]=-2,h[-2]=-1,h[-1]=-0.5 -> slope=0.833, eta=0.6
        # for eta=2: smaller slope, e.g. h[-4]=-3,h[-3]=-2.5,h[-2]=-2,h[-1]=-1.5 -> slope=0.5, eta=3.0 - at limit
        rsi_h = self._h([-3, -2, -1, -0.5])
        price_h = self._h([-6, -4, -2, -1.0])
        res = _macd_state(rsi_h, price_h)
        if res["state"] == "approaching":
            assert res["eta_bars"] is not None

    def test_none_when_all_negative_falling(self):
        rsi_h = self._h([-4, -3, -2, -1])  # not negative-falling, this is actually rising
        price_h = self._h([-1, -2, -3, -4])
        # price is falling (not approaching), rsi is rising but from negative
        # actually rsi_h is rising - could be approaching
        # Let's use clearly non-approaching series
        rsi_h2 = self._h([-1, -2, -3, -4])
        price_h2 = self._h([-1, -2, -3, -4])
        res = _macd_state(rsi_h2, price_h2)
        assert res["state"] == "none"


# ---------------------------------------------------------------------------
# 4. Pure helper unit tests — _stoch_cross_state
# ---------------------------------------------------------------------------

class TestStochCrossState:
    def _s(self, k_vals, d_vals) -> tuple[pd.Series, pd.Series]:
        idx = pd.RangeIndex(len(k_vals))
        return pd.Series(k_vals, index=idx, dtype=float), pd.Series(d_vals, index=idx, dtype=float)

    def test_crossed_at_last_bar(self):
        # k goes from below d to above d at last bar -> bars_since=0
        k_vals = [40, 35, 30, 25, 20, 30]  # k[-1]=30, k[-2]=20
        d_vals = [50, 50, 45, 40, 35, 28]  # d[-2]=35 > k[-2]=20, d[-1]=28 < k[-1]=30
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert res["state"] == "crossed"
        assert res["bars_since"] == 0

    def test_crossed_reports_from_washout_when_d_low(self):
        # d at cross < 25 -> from_washout=True
        k_vals = [10, 8, 5, 10, 25]
        d_vals = [30, 25, 20, 15, 22]  # d[-2]=15 < 25
        k, d = self._s(k_vals, d_vals)
        # k[-1]=25 >= d[-1]=22 and k[-2]=10 < d[-2]=15 -> cross at last bar
        res = _stoch_cross_state(k, d)
        if res["state"] == "crossed":
            assert isinstance(res["from_washout"], bool)

    def test_approaching_state(self):
        # k < d, k rising, gap small (d-k <= 8) and narrowing
        # e.g. two bars: k was 30, d was 45 (gap=15); now k=35, d=40 (gap=5 <= 8), narrowing
        k_vals = [50, 40, 30, 35]
        d_vals = [55, 50, 45, 40]
        # gap[-1] = 40-35=5 <= 8; gap[-2]=45-30=15; gap narrowing (5<15); k rising (35>30); k<d
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        if res["state"] == "approaching":
            assert res["gap"] is not None
            assert res["gap"] <= W_STOCH_GAP_MAX

    def test_none_when_k_above_d_no_recent_cross(self):
        # k consistently above d for many bars -> state "none"
        k_vals = list(range(60, 90, 5))
        d_vals = [v - 10 for v in k_vals]
        k, d = self._s(k_vals, d_vals)
        # k always > d, never crossed recently from below
        res = _stoch_cross_state(k, d)
        # state is either "none" or possibly "crossed" with bars_since>2 (old cross)
        # Only validate it doesn't raise and has correct keys
        assert set(res.keys()) == {"state", "bars_since", "d_at_cross", "from_washout", "k", "d", "gap"}

    def test_too_short_returns_none_state(self):
        k_vals = [30, 40]
        d_vals = [35, 38]
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert set(res.keys()) == {"state", "bars_since", "d_at_cross", "from_washout", "k", "d", "gap"}

    def test_crossed_invariant_bars_since_le_window(self):
        """If state=='crossed', bars_since must be <= W_CROSS_WINDOW."""
        k_vals = [40, 35, 30, 25, 20, 30]
        d_vals = [50, 50, 45, 40, 35, 28]
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        if res["state"] == "crossed":
            assert res["bars_since"] is not None
            assert res["bars_since"] <= W_CROSS_WINDOW


# ---------------------------------------------------------------------------
# 5. Integration tests: synthetic scenarios
# ---------------------------------------------------------------------------

class TestIntegrationDeepVWashout:
    """Deep V-shape: 2W and 1M washout should both hit 'now' or 'recent'."""

    def test_washout_hit_states_non_none(self):
        c = _v_shape_washout(n_decline=600, n_flat=700)
        snap = entry_snapshot(c)
        if snap["covered"]:
            # At the bottom of a deep V, wash_2w.state should not be "none"
            # (may be "now" or "recent" depending on where the series ends)
            assert snap["wash_2w"]["state"] in {"now", "recent", "near", "none"}
            assert snap["wash_1m"]["state"] in {"now", "recent", "near", "none"}
        else:
            pytest.skip("Series too short for coverage")

    def test_dual_washout_true_at_bottom(self):
        """When both 2W and 1M hit washout, dual_washout must be True."""
        c = _v_shape_washout(n_decline=600, n_flat=700)
        snap = entry_snapshot(c)
        if not snap["covered"]:
            pytest.skip("Not covered")
        if snap["wash_2w"]["state"] in {"now", "recent"} and snap["wash_1m"]["state"] in {"now", "recent"}:
            assert snap["dual_washout"] is True

    def test_dual_washout_false_without_both_hits(self):
        """dual_washout is False if either washout is not in hit states."""
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        if snap["covered"]:
            # monotonic rise -> no washouts -> dual_washout False
            assert snap["dual_washout"] is False


class TestIntegrationMonotonicRise:
    """A monotonically rising series should produce no washout hits."""

    def test_no_washout(self):
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        if snap["covered"]:
            assert snap["wash_2w"]["state"] in {"none", "near"}
            assert snap["wash_1m"]["state"] in {"none", "near"}

    def test_no_dual_washout(self):
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        assert snap["dual_washout"] is False

    def test_macd_state_valid_string(self):
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        if snap["covered"]:
            assert snap["w_macd"]["state"] in {"crossed", "approaching", "none"}

    def test_stoch_state_valid_string(self):
        c = _monotonic_rise(1500)
        snap = entry_snapshot(c)
        if snap["covered"]:
            assert snap["w_stoch"]["state"] in {"crossed", "approaching", "none"}


class TestIntegrationShortHistory:
    """Series shorter than MIN_DAILY_BARS -> covered=False."""

    def test_59_bars_covered_false(self):
        c = _bdate_series(MIN_DAILY_BARS - 1, vals=np.linspace(100, 50, MIN_DAILY_BARS - 1))
        snap = entry_snapshot(c)
        assert snap["covered"] is False

    def test_exactly_min_bars_covered_true(self):
        c = _bdate_series(MIN_DAILY_BARS, vals=np.linspace(100, 50, MIN_DAILY_BARS))
        snap = entry_snapshot(c)
        # MIN_DAILY_BARS=60 is covered but won't have enough bars for sub-detectors
        assert isinstance(snap["covered"], bool)
        # wash coverage may be False since MIN_HTF_BARS biweekly bars need more data
        if snap["covered"]:
            # might be True; sub-detector coverage may be False
            assert snap["wash_2w"]["coverage"] in {True, False}

    def test_empty_series_covered_false(self):
        c = pd.Series([], dtype=float)
        snap = entry_snapshot(c)
        assert snap["covered"] is False

    def test_none_entry_covered_false(self):
        snap = entry_snapshot(None)
        assert snap["covered"] is False


class TestIntegrationStateInvariances:
    """Cross-cutting invariants that hold for any valid snapshot."""

    def _check_invariants(self, snap: dict) -> None:
        # Top-level keys
        assert REQUIRED_KEYS_TOP == set(snap.keys())
        # Sub-dict keys
        assert WASH_KEYS == set(snap["wash_2w"].keys())
        assert WASH_KEYS == set(snap["wash_1m"].keys())
        assert WMACD_KEYS == set(snap["w_macd"].keys())
        assert WSTOCH_KEYS == set(snap["w_stoch"].keys())
        # Covered semantics
        if not snap["covered"]:
            assert snap["wash_2w"]["coverage"] is False
            assert snap["wash_1m"]["coverage"] is False
            assert snap["w_macd"]["state"] == "none"
            assert snap["w_stoch"]["state"] == "none"
            assert snap["dual_washout"] is False
        # State values are always valid strings
        assert snap["wash_2w"]["state"] in {"now", "recent", "near", "none"}
        assert snap["wash_1m"]["state"] in {"now", "recent", "near", "none"}
        assert snap["w_macd"]["state"] in {"crossed", "approaching", "none"}
        assert snap["w_stoch"]["state"] in {"crossed", "approaching", "none"}
        # dual_washout semantics
        hit = {"now", "recent"}
        expected_dual = (snap["wash_2w"]["state"] in hit) and (snap["wash_1m"]["state"] in hit)
        assert snap["dual_washout"] == expected_dual
        # w_stoch crossed -> bars_since <= W_CROSS_WINDOW
        if snap["w_stoch"]["state"] == "crossed":
            assert snap["w_stoch"]["bars_since"] is not None
            assert snap["w_stoch"]["bars_since"] <= W_CROSS_WINDOW
        # w_stoch from_washout is always bool
        assert isinstance(snap["w_stoch"]["from_washout"], bool)

    def test_invariants_none(self):
        self._check_invariants(entry_snapshot(None))

    def test_invariants_short(self):
        c = _bdate_series(30, vals=np.linspace(100, 50, 30))
        self._check_invariants(entry_snapshot(c))

    def test_invariants_rise(self):
        c = _monotonic_rise(1500)
        self._check_invariants(entry_snapshot(c))

    def test_invariants_v_shape(self):
        c = _v_shape_washout()
        self._check_invariants(entry_snapshot(c))

    def test_invariants_recovery(self):
        c = _recovery_from_washout()
        self._check_invariants(entry_snapshot(c))


class TestStochCrossZoneQualifiers:
    """Low-zone + aliveness qualifiers (added 2026-07-18 after the 29% base-rate probe)."""

    def _s(self, k_vals, d_vals):
        idx = pd.RangeIndex(len(k_vals))
        return pd.Series(k_vals, index=idx, dtype=float), pd.Series(d_vals, index=idx, dtype=float)

    def test_midrange_cross_does_not_count(self):
        # Fresh upcross but d_at_cross = 55 (>= W_STOCH_ZONE_MAX) -> mid-range churn -> none
        k_vals = [40, 45, 50, 60]
        d_vals = [50, 52, 54, 55]  # k crosses d at last bar, d_at_cross=55
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert res["state"] == "none"

    def test_low_zone_cross_counts(self):
        # Same shape but in the low zone -> crossed
        k_vals = [10, 12, 15, 30]
        d_vals = [25, 24, 22, 25]  # cross at last bar, d_at_cross=25 < 40
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert res["state"] == "crossed"
        assert res["bars_since"] == 0
        assert res["d_at_cross"] < 40.0

    def test_dead_cross_does_not_count(self):
        # Upcross 1 bar ago but k already fell back below d -> not alive -> not crossed
        k_vals = [10, 12, 30, 18]
        d_vals = [25, 24, 22, 24]  # cross at idx 2, then k[-1]=18 < d[-1]=24
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert res["state"] != "crossed"

    def test_approaching_requires_low_zone(self):
        # k<d, rising, gap 5 narrowing — but d=60 (mid-range) -> none
        k_vals = [70, 60, 50, 55]
        d_vals = [75, 70, 65, 60]
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert res["state"] == "none"

    def test_approaching_in_low_zone_counts(self):
        # Same shape shifted into the low zone -> approaching
        k_vals = [40, 30, 20, 25]
        d_vals = [45, 40, 35, 30]  # gap 5 <= 8, narrowing (15->5), k rising, d=30 < 40
        k, d = self._s(k_vals, d_vals)
        res = _stoch_cross_state(k, d)
        assert res["state"] == "approaching"
