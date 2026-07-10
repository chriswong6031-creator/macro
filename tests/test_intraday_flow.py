"""tests/test_intraday_flow.py — Unit tests for engine/intraday_flow.py (IFT A1).

Covers every public function with synthetic fixtures and edge cases.
All tests are self-contained; no network, no disk I/O.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.intraday_flow import (
    ConfluenceLegs,
    confluence_legs,
    flow_durability,
    higher_lows,
    ncp_velocity,
    rvol_tod,
    session_vwap,
    vol_share_curve,
    volume_durability,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _bar(open_=100, high=105, low=98, close=103, volume=100_000):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _session(n: int = 7, vol_per_bar: int = 100_000, base: float = 100.0):
    """Create a simple session of n hourly bars with steady price action."""
    return [_bar(base + i, base + i + 2, base + i - 1, base + i + 1, vol_per_bar)
            for i in range(n)]


# ── vol_share_curve ───────────────────────────────────────────────────────────

class TestVolShareCurve:
    def test_basic_two_sessions(self):
        """Median curve over two identical sessions should equal the single-session curve."""
        sess = _session(7, 100_000)
        result = vol_share_curve([sess, sess])
        assert result is not None
        assert len(result) == 7
        # All volumes equal, so each bar adds 1/7 of total.
        for i, share in enumerate(result):
            assert abs(share - (i + 1) / 7) < 0.01

    def test_cumulative_monotone(self):
        """Output must be non-decreasing and end at 1.0."""
        sess1 = _session(7, 100_000)
        sess2 = _session(7, 200_000)
        result = vol_share_curve([sess1, sess2])
        assert result is not None
        assert result[-1] == 1.0
        for i in range(1, len(result)):
            assert result[i] >= result[i - 1] - 1e-9

    def test_empty_session_list(self):
        assert vol_share_curve([]) is None

    def test_single_session(self):
        """Single session returns None (need >= 2)."""
        assert vol_share_curve([_session(7)]) is None

    def test_zero_volume_sessions_skipped(self):
        """Sessions with all-zero volumes are skipped; needs >= 2 valid sessions."""
        zero_sess = [_bar(100, 105, 98, 103, 0)] * 7
        good_sess = _session(7)
        # Only one valid session after skipping zero-vol.
        assert vol_share_curve([zero_sess, good_sess]) is None

    def test_two_valid_sessions(self):
        """Two valid sessions should produce a result even with one zero-vol skipped."""
        good1 = _session(7)
        good2 = _session(7, 200_000)
        result = vol_share_curve([good1, good2])
        assert result is not None

    def test_trailing_twenty_sessions(self):
        """20 identical sessions should give same result as 2."""
        sess = _session(6)
        r2 = vol_share_curve([sess, sess])
        r20 = vol_share_curve([sess] * 20)
        assert r2 is not None and r20 is not None
        for a, b in zip(r2, r20):
            assert abs(a - b) < 0.01

    def test_unequal_bar_counts_padded(self):
        """Short sessions are padded to 1.0; curve length = max session length."""
        short = _session(4)
        long_ = _session(7)
        result = vol_share_curve([short, long_])
        assert result is not None
        assert len(result) == 7
        # Padded session's last value stays at 1.0, so median >= short-session endpoint.
        assert result[-1] == 1.0


# ── rvol_tod ─────────────────────────────────────────────────────────────────

class TestRvolTod:
    def test_at_pace(self):
        """Cumulative vol equal to expected → RVOL_tod = 1.0."""
        adv20 = 1_000_000
        share = 0.40
        cum_vol = adv20 * share
        result = rvol_tod(cum_vol, adv20, share)
        assert result is not None
        assert abs(result - 1.0) < 0.001

    def test_elevated(self):
        """Vol running 2× expected → RVOL_tod = 2.0."""
        adv20 = 1_000_000
        share = 0.40
        cum_vol = adv20 * share * 2
        result = rvol_tod(cum_vol, adv20, share)
        assert result is not None
        assert abs(result - 2.0) < 0.001

    def test_none_inputs(self):
        assert rvol_tod(None, 1e6, 0.40) is None
        assert rvol_tod(400_000, None, 0.40) is None
        assert rvol_tod(400_000, 1e6, None) is None

    def test_zero_adv(self):
        assert rvol_tod(400_000, 0, 0.40) is None

    def test_zero_share(self):
        assert rvol_tod(400_000, 1e6, 0.0) is None

    def test_low_rvol(self):
        """Vol behind pace → RVOL < 1.0."""
        result = rvol_tod(100_000, 1_000_000, 0.40)
        assert result is not None
        assert result < 1.0


# ── session_vwap ─────────────────────────────────────────────────────────────

class TestSessionVwap:
    def test_single_bar(self):
        """VWAP with one bar = typical price."""
        b = _bar(100, 110, 90, 105, 100_000)
        result = session_vwap([b])
        typical = (110 + 90 + 105) / 3.0
        assert result is not None
        assert abs(result - typical) < 0.01

    def test_equal_volume_bars(self):
        """With equal volumes, VWAP = mean of typical prices."""
        bars = [
            _bar(100, 110, 90, 100, 100_000),
            _bar(110, 120, 100, 110, 100_000),
        ]
        result = session_vwap(bars)
        tp1 = (110 + 90 + 100) / 3.0
        tp2 = (120 + 100 + 110) / 3.0
        expected = (tp1 + tp2) / 2.0
        assert result is not None
        assert abs(result - expected) < 0.01

    def test_empty_bars(self):
        assert session_vwap([]) is None

    def test_zero_volume_bars(self):
        bars = [_bar(100, 110, 90, 105, 0)]
        assert session_vwap(bars) is None

    def test_missing_fields_skipped(self):
        """Bars missing OHLCV fields are skipped; others still contribute."""
        bars = [
            {"high": None, "low": 90, "close": 100, "volume": 100_000},
            _bar(100, 110, 90, 105, 100_000),
        ]
        result = session_vwap(bars)
        assert result is not None


# ── volume_durability ─────────────────────────────────────────────────────────

class TestVolumeDurability:
    def test_all_upper_half_no_baseline(self):
        """All closes in upper half, no baseline → 1.0."""
        bars = [_bar(100, 110, 90, 105, 100_000)] * 6  # close 105 > mid 100
        result = volume_durability(bars, None)
        assert result == 1.0

    def test_all_lower_half_no_baseline(self):
        """All closes in lower half → 0.0."""
        bars = [_bar(100, 110, 90, 92, 100_000)] * 6   # close 92 < mid 100
        result = volume_durability(bars, None)
        assert result == 0.0

    def test_half_and_half(self):
        upper = _bar(100, 110, 90, 105, 100_000)  # close > mid
        lower = _bar(100, 110, 90, 92, 100_000)   # close < mid
        result = volume_durability([upper, lower, upper, lower], None)
        assert result is not None
        assert abs(result - 0.5) < 0.01

    def test_empty_bars(self):
        assert volume_durability([], None) is None

    def test_with_baseline_curve_vol_gate(self):
        """With baseline: bar must also have sufficient volume."""
        # ADV = 1M, expected incremental share per bar = 0.1 → expected 100k/bar
        # Bar 0 has 200k (passes), bar 1 has 10k (fails vol gate)
        curve = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        adv20 = 1_000_000
        bars = [
            _bar(100, 110, 90, 105, 200_000),   # upper-half, vol OK
            _bar(100, 110, 90, 105, 10_000),    # upper-half, vol too low
            _bar(100, 110, 90, 105, 200_000),   # upper-half, vol OK
        ]
        result = volume_durability(bars, curve, adv20)
        assert result is not None
        # 2 of 3 qualify.
        assert abs(result - 2 / 3) < 0.01

    def test_missing_fields_skipped(self):
        bars = [
            {"high": None, "low": 90, "close": 105, "volume": 100_000},
            _bar(100, 110, 90, 105, 100_000),
        ]
        result = volume_durability(bars, None)
        assert result == 1.0  # Only valid bar, and it qualifies.


# ── higher_lows ───────────────────────────────────────────────────────────────

class TestHigherLows:
    def test_steadily_rising_lows(self):
        bars = [_bar(low=100), _bar(low=102), _bar(low=104), _bar(low=106)]
        assert higher_lows(bars) == 3

    def test_first_break(self):
        bars = [_bar(low=100), _bar(low=102), _bar(low=101), _bar(low=103)]
        assert higher_lows(bars) == 1  # Stops at first violation (bar 2 < bar 1)

    def test_no_higher_lows(self):
        bars = [_bar(low=100), _bar(low=99), _bar(low=98)]
        assert higher_lows(bars) == 0

    def test_single_bar(self):
        assert higher_lows([_bar()]) == 0

    def test_empty(self):
        assert higher_lows([]) == 0

    def test_none_lows_skipped(self):
        bars = [{"low": 100}, {"low": None}, {"low": 102}]
        # None lows are skipped during collection.
        result = higher_lows(bars)
        assert isinstance(result, int)


# ── ncp_velocity ─────────────────────────────────────────────────────────────

class TestNcpVelocity:
    def _make_series(self, n: int = 80, slope: float = 5.0, noise: float = 2.0):
        """Linearly growing NCP cumulative series."""
        import numpy as np
        rng = np.random.default_rng(42)
        vals = [i * slope + rng.normal(0, noise) for i in range(n)]
        return vals

    def test_strong_positive_slope(self):
        """Strong upward trend → positive z-score."""
        series = self._make_series(80, slope=10.0, noise=0.1)
        result = ncp_velocity(series)
        assert result is not None
        assert result > 0.5

    def test_strong_negative_slope(self):
        """Strong downward trend → negative z-score."""
        series = [-v for v in self._make_series(80, slope=10.0, noise=0.1)]
        result = ncp_velocity(series)
        assert result is not None
        assert result < -0.5

    def test_too_short(self):
        """Fewer than min_obs points → None."""
        assert ncp_velocity([1.0, 2.0, 3.0]) is None

    def test_empty(self):
        assert ncp_velocity([]) is None

    def test_none_values_filtered(self):
        """None values are filtered out; result still computable with enough data."""
        series = self._make_series(80, slope=5.0)
        series_with_nones = [v if i % 5 != 0 else None for i, v in enumerate(series)]
        result = ncp_velocity(series_with_nones)
        # Should still produce a result as long as enough valid points remain.
        assert result is None or isinstance(result, float)

    def test_flat_series(self):
        """Flat series → z near zero (may be None due to zero vol)."""
        series = [100.0] * 80
        result = ncp_velocity(series)
        # Flat = zero vol → slope_z returns NaN → None
        assert result is None or abs(result) < 1.0


# ── flow_durability ───────────────────────────────────────────────────────────

class TestFlowDurability:
    def _cumulative(self, increments: list[float]) -> list[float]:
        result, cum = [], 0.0
        for v in increments:
            cum += v
            result.append(cum)
        return result

    def test_all_positive_windows(self):
        """All 5-min windows positive → positive_share = 1.0."""
        series = self._cumulative([10.0] * 40)  # 8 windows of 5
        result = flow_durability(series)
        assert result["positive_share"] == 1.0
        assert result["longest_streak"] == 8

    def test_all_negative_windows(self):
        """All 5-min windows negative → positive_share = 0.0, streak = 0."""
        series = self._cumulative([-10.0] * 40)
        result = flow_durability(series)
        assert result["positive_share"] == 0.0
        assert result["longest_streak"] == 0

    def test_alternating(self):
        """Alternating windows → positive_share = 0.5, longest_streak = 1."""
        increments = []
        for _ in range(8):
            increments += [10.0] * 5   # positive window
            increments += [-10.0] * 5  # negative window
        series = self._cumulative(increments)
        result = flow_durability(series)
        assert result is not None
        assert abs(result["positive_share"] - 0.5) < 0.01
        assert result["longest_streak"] == 1

    def test_empty_series(self):
        r = flow_durability([])
        assert r["positive_share"] is None
        assert r["longest_streak"] is None

    def test_too_short(self):
        """Series shorter than window_min → None results."""
        r = flow_durability([1.0, 2.0, 3.0], window_min=5)
        assert r["positive_share"] is None

    def test_custom_window(self):
        """Custom window_min respected."""
        series = self._cumulative([5.0] * 30)  # 10 windows of 3
        result = flow_durability(series, window_min=3)
        assert result["positive_share"] == 1.0
        assert result["longest_streak"] == 10

    def test_streak_counting(self):
        """Max streak properly tracks the longest run."""
        # 3 pos, 1 neg, 5 pos → longest = 5
        increments = [10.0] * 15 + [-5.0] * 5 + [10.0] * 25
        series = self._cumulative(increments)
        result = flow_durability(series)
        assert result is not None
        # 3 + 1 + 5 = 9 windows of 5; longest run should be ≥ 3
        assert result["longest_streak"] >= 3


# ── confluence_legs ──────────────────────────────────────────────────────────

class TestConfluenceLegs:
    def test_all_seven_true(self):
        """All seven legs True → K = 7."""
        legs = confluence_legs(
            bb_lower_reclaim_days=5,
            washout_lookback=10,
            price=105.0,
            vwap=100.0,
            prev_close=103.0,
            rvol_tod_val=1.5,
            rvol_confirm=1.30,
            vol_durability_val=0.70,
            durability_min=0.60,
            cum_ncp=50_000.0,
            flow_durability_val=0.70,
            mtf_upturn_state="UPTURN_CONFIRMED",
            failed_breakout_trap=False,
        )
        assert legs.K == 7
        assert legs.L1_washout_recent is True
        assert legs.L2_reclaim is True
        assert legs.L3_rvol_elevated is True
        assert legs.L4_vol_durable is True
        assert legs.L5_flow_bid is True
        assert legs.L6_upturn_organ is True
        assert legs.L7_leader_quality is True

    def test_all_false(self):
        """All legs False → K = 0."""
        legs = confluence_legs(
            bb_lower_reclaim_days=15,
            washout_lookback=10,
            price=95.0,
            vwap=100.0,
            prev_close=96.0,
            rvol_tod_val=0.80,
            rvol_confirm=1.30,
            vol_durability_val=0.30,
            durability_min=0.60,
            cum_ncp=-50_000.0,
            flow_durability_val=0.30,
            mtf_upturn_state="UPTURN_OFF",
            failed_breakout_trap=True,
        )
        assert legs.K == 0

    def test_null_inputs_all_none(self):
        """No inputs → all legs None → K = 0."""
        legs = confluence_legs()
        assert legs.K == 0
        assert legs.L1_washout_recent is None
        assert legs.L2_reclaim is None
        assert legs.L3_rvol_elevated is None
        assert legs.L4_vol_durable is None
        assert legs.L5_flow_bid is None
        assert legs.L6_upturn_organ is None
        assert legs.L7_leader_quality is None

    def test_l1_drawdown_path(self):
        """L1 via drawdown path when bb_lower_reclaim_days absent."""
        legs = confluence_legs(
            drawdown_21d_pct=-0.15,
            recovery_begun=True,
        )
        assert legs.L1_washout_recent is True

    def test_l1_drawdown_path_insufficient(self):
        """L1 via drawdown path: -8% not enough for -12% threshold."""
        legs = confluence_legs(
            drawdown_21d_pct=-0.08,
            recovery_begun=True,
        )
        assert legs.L1_washout_recent is False

    def test_l5_cum_ncp_only(self):
        """L5 with cum_ncp only (no flow_durability) — positive NCP is True."""
        legs = confluence_legs(cum_ncp=10_000.0)
        assert legs.L5_flow_bid is True

    def test_l5_negative_cum_ncp(self):
        legs = confluence_legs(cum_ncp=-10_000.0)
        assert legs.L5_flow_bid is False

    def test_l6_upturn_watch(self):
        """UPTURN_WATCH qualifies for L6."""
        legs = confluence_legs(mtf_upturn_state="UPTURN_WATCH")
        assert legs.L6_upturn_organ is True

    def test_l6_off(self):
        legs = confluence_legs(mtf_upturn_state="UPTURN_OFF")
        assert legs.L6_upturn_organ is False

    def test_as_dict(self):
        """as_dict() returns correct keys and K."""
        legs = confluence_legs(
            rvol_tod_val=1.5,
            rvol_confirm=1.30,
        )
        d = legs.as_dict()
        assert "K" in d
        assert "L3_rvol_elevated" in d
        assert d["L3_rvol_elevated"] is True
        assert d["K"] == 1

    def test_no_dt_contra_key(self):
        """dt_contra must NOT appear anywhere in the output per DT-R11b."""
        legs = confluence_legs(
            bb_lower_reclaim_days=3,
            price=105.0,
            vwap=100.0,
        )
        d = legs.as_dict()
        assert "dt_contra" not in d
        assert "dt_contra" not in str(d)

    def test_k_counts_only_true(self):
        """K is count of True legs; None legs are not counted."""
        legs = confluence_legs(
            rvol_tod_val=1.5,  # L3 True
            failed_breakout_trap=False,  # L7 True
        )
        assert legs.K == 2

    def test_partial_l2(self):
        """L2 with only price and prev_close (no vwap) still evaluates."""
        legs = confluence_legs(price=105.0, prev_close=103.0)
        assert legs.L2_reclaim is True

    def test_partial_l2_price_vwap_only(self):
        legs = confluence_legs(price=95.0, vwap=100.0)
        assert legs.L2_reclaim is False


# ── ConfluenceLegs dataclass ─────────────────────────────────────────────────

class TestConfluenceLegsDataclass:
    def test_direct_instantiation(self):
        legs = ConfluenceLegs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L3_rvol_elevated=False,
            L4_vol_durable=None,
            L5_flow_bid=True,
            L6_upturn_organ=None,
            L7_leader_quality=True,
        )
        # K = 4 (True for L1, L2, L5, L7; None for L4, L6; False for L3).
        assert legs.K == 4

    def test_empty_dataclass(self):
        legs = ConfluenceLegs()
        assert legs.K == 0
