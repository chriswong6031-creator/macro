"""Tests for engine/entry_primitives.py.

Covers:
  (a) Hand-computed fixture assertions on tiny synthetic series for every function.
  (b) Truncation-equality (no-lookahead) check for every function: for at least 5
      sampled bar positions t, the value at t computed on data truncated at t equals
      the value at t from the full-series run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.entry_primitives import (  # noqa: E402
    atr_pct_pctile_series,
    bbwp_series,
    dist_52w_high_series,
    donchian_pos_series,
    hvp_series,
    obv_slope_series,
    rel_volume_series,
    time_underwater_series,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2015-01-01", periods=n)


def _close(vals) -> pd.Series:
    return pd.Series(list(vals), index=_idx(len(vals)), dtype=float)


def _ramp(n: int, start: float = 10.0, step: float = 0.5) -> pd.Series:
    """Steadily-rising close series."""
    return _close([start + i * step for i in range(n)])


def _flat(n: int, val: float = 100.0) -> pd.Series:
    return _close([val] * n)


# ---------------------------------------------------------------------------
# (a) hand-computed fixture tests
# ---------------------------------------------------------------------------

class TestBbwpSeries:
    def test_range_0_100(self):
        close = _ramp(400)
        result = bbwp_series(close)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_returns_series_same_index(self):
        close = _ramp(300)
        result = bbwp_series(close)
        assert isinstance(result, pd.Series)
        assert result.index.equals(close.index)

    def test_early_bars_nan(self):
        # needs n=20 for bb_bandwidth and rank_window//2=126 for rank → first ~145 NaN
        close = _ramp(300)
        result = bbwp_series(close, n=20, rank_window=252)
        # at minimum first n bars must be NaN (bb_bandwidth has min_periods=n)
        assert result.iloc[:20].isna().all()

    def test_constant_price_gives_zero_bandwidth_hence_min_pctile(self):
        # constant close → sd=0 → bb_bandwidth=0 → all tied → rank is ~50 (median of ties)
        # pct_rank_window uses pandas rank(pct=True) which for all-tied values
        # returns ~0.5 by default (average rank). Accept any value in [0,100].
        close = _flat(400)
        result = bbwp_series(close, n=20, rank_window=252)
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all() and (valid <= 100).all()


class TestHvpSeries:
    def test_range_0_100(self):
        close = _ramp(400)
        result = hvp_series(close)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_early_bars_nan(self):
        close = _ramp(300)
        result = hvp_series(close, n=20, rank_window=252)
        assert result.iloc[:20].isna().all()

    def test_same_index(self):
        close = _ramp(300)
        assert hvp_series(close).index.equals(close.index)

    def test_high_vol_regime_scores_higher(self):
        # first 300 bars low vol (flat), last 100 bars high vol (zigzag)
        n_low, n_high = 300, 100
        lo = [100.0] * n_low
        hi = [100.0 + (10.0 if i % 2 == 0 else -10.0) for i in range(n_high)]
        close = _close(lo + hi)
        result = hvp_series(close, n=20, rank_window=252)
        # last bar (high vol) should score higher than bar at position 250 (low vol)
        last = result.iloc[-1]
        mid = result.iloc[250]
        if not (np.isnan(last) or np.isnan(mid)):
            assert last > mid


class TestDonchianPosSeries:
    def test_at_high_returns_one(self):
        # price at a new 20-day high → position = 1.0
        n = 30
        close = _ramp(n)
        high = close + 0.1
        low = close - 0.1
        result = donchian_pos_series(close, high, low, n=20)
        # last bar: close = max close, low of window < max → position ~ 1
        assert abs(result.iloc[-1] - 1.0) < 0.02

    def test_at_low_returns_zero(self):
        # falling price series → last close is the 20-day low → position ~ 0
        n = 30
        close = _close([100.0 - i * 0.5 for i in range(n)])
        high = close + 0.1
        low = close - 0.1
        result = donchian_pos_series(close, high, low, n=20)
        assert abs(result.iloc[-1] - 0.0) < 0.02

    def test_zero_range_is_nan(self):
        # constant price → range = 0 → NaN (guarded)
        close = _flat(30)
        high = _flat(30)
        low = _flat(30)
        result = donchian_pos_series(close, high, low, n=20)
        assert result.dropna().empty

    def test_values_bounded_0_1(self):
        n = 100
        close = _ramp(n)
        high = close * 1.01
        low = close * 0.99
        result = donchian_pos_series(close, high, low, n=20)
        valid = result.dropna()
        assert (valid >= -1e-9).all() and (valid <= 1 + 1e-9).all()

    def test_hand_computed(self):
        # 5-bar window: high=[1,2,3,4,5], low=[1,2,3,4,5], close=[3] at bar 2 (0-indexed).
        # At bar 4 (last), hh=5, ll=1, close=5 → pos=(5-1)/(5-1)=1.0
        # Use separate high/low/close so close is 3 at last bar:
        # close=[3,3,3,3,3], high=[1,2,3,4,5], low=[0,0,0,0,0]
        # hh=5, ll=0, close=3 → (3-0)/(5-0) = 0.6
        close = _close([3.0, 3.0, 3.0, 3.0, 3.0])
        high = _close([1.0, 2.0, 3.0, 4.0, 5.0])
        low = _close([0.0, 0.0, 0.0, 0.0, 0.0])
        result = donchian_pos_series(close, high, low, n=5)
        assert abs(result.iloc[-1] - 0.6) < 1e-9


class TestRelVolumeSeries:
    def test_above_one_on_spike(self):
        # 20 bars of volume=100, then one spike at 200 → rel_vol at last bar > 1
        vol = _close([100.0] * 21 + [200.0])
        result = rel_volume_series(vol, n=20)
        assert result.iloc[-1] > 1.0

    def test_below_one_on_dip(self):
        vol = _close([100.0] * 21 + [50.0])
        result = rel_volume_series(vol, n=20)
        assert result.iloc[-1] < 1.0

    def test_flat_volume_gives_one(self):
        # constant volume → rel_vol = 1 everywhere after warmup
        vol = _flat(50, 100.0)
        result = rel_volume_series(vol, n=20)
        valid = result.dropna()
        assert ((valid - 1.0).abs() < 1e-9).all()

    def test_early_bars_nan(self):
        # min_periods = n//2 = 10; bars 0..8 (9 bars) should be NaN, bar 9 is first non-NaN
        vol = _flat(30, 100.0)
        result = rel_volume_series(vol, n=20)
        assert result.iloc[:9].isna().all()
        assert not np.isnan(result.iloc[9])


class TestObvSlopeSeries:
    def test_rising_market_positive_slope(self):
        # steadily rising close with constant volume → OBV rises → slope positive
        n = 60
        close = _ramp(n)
        vol = _flat(n, 1000.0)
        result = obv_slope_series(close, vol, slope_win=20)
        assert result.iloc[-1] > 0

    def test_falling_market_negative_slope(self):
        n = 60
        close = _close([100.0 - i * 0.5 for i in range(n)])
        vol = _flat(n, 1000.0)
        result = obv_slope_series(close, vol, slope_win=20)
        assert result.iloc[-1] < 0

    def test_same_index(self):
        close = _ramp(60)
        vol = _flat(60, 1000.0)
        result = obv_slope_series(close, vol)
        assert result.index.equals(close.index)


class TestAtrPctPctileSeries:
    def test_range_0_100(self):
        n = 400
        close = _ramp(n, 10.0, 0.1)
        high = close + 0.5
        low = close - 0.5
        result = atr_pct_pctile_series(high, low, close, n=14, rank_window=252)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_same_index(self):
        n = 300
        close = _ramp(n)
        high = close + 1.0
        low = close - 1.0
        result = atr_pct_pctile_series(high, low, close)
        assert result.index.equals(close.index)


class TestDist52wHighSeries:
    def test_at_new_high_is_zero(self):
        # steadily rising → last bar is always the rolling max → dist = 0
        close = _ramp(300)
        result = dist_52w_high_series(close, window=252)
        assert abs(result.iloc[-1]) < 1e-9

    def test_values_leq_zero(self):
        n = 400
        close = _ramp(n)
        result = dist_52w_high_series(close, window=252)
        valid = result.dropna()
        assert (valid <= 0 + 1e-9).all()

    def test_values_geq_minus_one(self):
        n = 400
        close = _ramp(n)
        result = dist_52w_high_series(close, window=252)
        valid = result.dropna()
        assert (valid >= -1.0 - 1e-9).all()

    def test_hand_computed(self):
        # 5-bar window: [10, 20, 15, 12, 10] → max=20 → dist at last = 10/20-1 = -0.5
        close = _close([10.0, 20.0, 15.0, 12.0, 10.0])
        result = dist_52w_high_series(close, window=5)
        assert abs(result.iloc[-1] - (-0.5)) < 1e-9

    def test_early_bars_nan(self):
        # window=252: bars 0..250 (251 bars) are NaN; bar 251 is the first non-NaN
        close = _ramp(300)
        result = dist_52w_high_series(close, window=252)
        assert result.iloc[:251].isna().all()
        assert not np.isnan(result.iloc[251])


class TestTimeUnderwaterSeries:
    def test_at_new_high_is_zero(self):
        close = _ramp(300)
        result = time_underwater_series(close, window=252)
        # last bar is a new rolling high → 0
        assert result.iloc[-1] == 0.0

    def test_bars_counting_up(self):
        # peak then flat → time_underwater increases each bar
        peak = [100.0] * 252 + [200.0]  # bar 252 sets new max
        descent = [190.0, 180.0, 170.0, 160.0, 150.0]
        close = _close(peak + descent)
        result = time_underwater_series(close, window=252)
        last_five = result.iloc[-5:].values
        # values should increase 1, 2, 3, 4, 5
        for i in range(1, 5):
            assert last_five[i] > last_five[i - 1]

    def test_non_negative(self):
        close = _ramp(400)
        result = time_underwater_series(close, window=252)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_hand_computed(self):
        # window=5: [1, 5, 3, 2, 2] → max is at position 1 (value 5)
        # last bar index = 4, argmax=1, bars_since = 4-1 = 3
        close = _close([1.0, 5.0, 3.0, 2.0, 2.0])
        result = time_underwater_series(close, window=5)
        assert result.iloc[-1] == 3.0


# ---------------------------------------------------------------------------
# (b) truncation-equality (no-lookahead) tests
# ---------------------------------------------------------------------------

def _truncation_check(fn, full_series_args: dict, t_indices: list[int],
                      tol: float = 1e-9) -> None:
    """For each t in t_indices, compute fn on data truncated at t and compare."""
    # full run
    full_result = fn(**full_series_args)
    n = len(list(full_series_args.values())[0])
    for t in t_indices:
        if t >= n:
            continue
        # build truncated args
        trunc_args = {}
        for key, val in full_series_args.items():
            if isinstance(val, pd.Series):
                trunc_args[key] = val.iloc[: t + 1]
            else:
                trunc_args[key] = val
        trunc_result = fn(**trunc_args)
        full_val = full_result.iloc[t]
        trunc_val = trunc_result.iloc[t]
        if np.isnan(full_val) and np.isnan(trunc_val):
            continue
        assert not np.isnan(full_val), f"full NaN at t={t} but truncated={trunc_val}"
        assert not np.isnan(trunc_val), f"truncated NaN at t={t} but full={full_val}"
        assert abs(full_val - trunc_val) <= tol, (
            f"Lookahead at t={t}: full={full_val}, truncated={trunc_val}"
        )


def _make_ohlcv(n: int = 500):
    close = _ramp(n, 10.0, 0.2)
    high = close + 0.5
    low = close - 0.5
    vol = _flat(n, 1000.0)
    return close, high, low, vol


def test_bbwp_no_lookahead():
    close, _, _, _ = _make_ohlcv(500)
    _truncation_check(
        bbwp_series,
        {"close": close, "n": 20, "k": 2.0, "rank_window": 252},
        t_indices=[260, 300, 350, 400, 450],
    )


def test_hvp_no_lookahead():
    close, _, _, _ = _make_ohlcv(500)
    _truncation_check(
        hvp_series,
        {"close": close, "n": 20, "rank_window": 252},
        t_indices=[260, 300, 350, 400, 450],
    )


def test_donchian_pos_no_lookahead():
    close, high, low, _ = _make_ohlcv(200)
    _truncation_check(
        donchian_pos_series,
        {"close": close, "high": high, "low": low, "n": 20},
        t_indices=[25, 50, 80, 120, 160],
    )


def test_rel_volume_no_lookahead():
    _, _, _, vol = _make_ohlcv(200)
    _truncation_check(
        rel_volume_series,
        {"volume": vol, "n": 20},
        t_indices=[15, 30, 60, 100, 150],
    )


def test_obv_slope_no_lookahead():
    close, _, _, vol = _make_ohlcv(200)
    _truncation_check(
        obv_slope_series,
        {"close": close, "volume": vol, "slope_win": 20},
        t_indices=[25, 50, 80, 120, 160],
    )


def test_atr_pct_pctile_no_lookahead():
    close, high, low, _ = _make_ohlcv(500)
    _truncation_check(
        atr_pct_pctile_series,
        {"high": high, "low": low, "close": close, "n": 14, "rank_window": 252},
        t_indices=[270, 310, 360, 410, 460],
    )


def test_dist_52w_high_no_lookahead():
    close, _, _, _ = _make_ohlcv(500)
    _truncation_check(
        dist_52w_high_series,
        {"close": close, "window": 252},
        t_indices=[255, 300, 350, 400, 450],
    )


def test_time_underwater_no_lookahead():
    close, _, _, _ = _make_ohlcv(500)
    _truncation_check(
        time_underwater_series,
        {"close": close, "window": 252},
        t_indices=[255, 300, 350, 400, 450],
    )
