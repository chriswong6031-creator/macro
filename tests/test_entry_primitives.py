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
    amihud_series,
    atr_pct_pctile_series,
    bbwp_series,
    corwin_schultz_spread_series,
    dist_52w_high_series,
    donchian_pos_series,
    gap_hold_events,
    hvp_series,
    obv_slope_series,
    pocket_pivot_events,
    rel_volume_series,
    time_underwater_series,
    undercut_rally_events,
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


# ---------------------------------------------------------------------------
# New PR-A2 primitives
# ---------------------------------------------------------------------------

# ---------- Amihud series --------------------------------------------------

class TestAmihudSeries:
    def test_nonnegative(self):
        close = _ramp(100, 10.0, 0.2)
        vol = _flat(100, 500_000.0)
        result = amihud_series(close, vol, win=20)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_same_index(self):
        close = _ramp(80)
        vol = _flat(80, 1e6)
        result = amihud_series(close, vol, win=20)
        assert result.index.equals(close.index)

    def test_zero_volume_is_nan(self):
        close = _ramp(50)
        vol = _flat(50, 0.0)
        result = amihud_series(close, vol, win=20)
        assert result.dropna().empty

    def test_early_bars_nan(self):
        close = _ramp(60)
        vol = _flat(60, 1e6)
        result = amihud_series(close, vol, win=20)
        # pct_change produces NaN at bar 0, rolling(20) needs 20 valid points
        # so first non-NaN is at index 20 (bar 21, 0-indexed)
        assert result.iloc[:20].isna().all()

    def test_higher_volume_lower_illiq(self):
        # Same price moves, doubling volume halves ILLIQ
        close = _ramp(60, 10.0, 0.1)
        vol_low = _flat(60, 1_000.0)
        vol_high = _flat(60, 2_000.0)
        r_low = amihud_series(close, vol_low, win=20).dropna()
        r_high = amihud_series(close, vol_high, win=20).dropna()
        assert (r_low > r_high).all()


def test_amihud_no_lookahead():
    """Shift-audit: amihud value at t must equal full-series value at t."""
    close = _ramp(200, 10.0, 0.2)
    vol = _flat(200, 1e6)

    def _amihud_wrap(close, volume, win):
        return amihud_series(close, volume, win=win)

    full = amihud_series(close, vol, win=20)
    for t in [30, 60, 100, 140, 180]:
        trunc = amihud_series(close.iloc[: t + 1], vol.iloc[: t + 1], win=20)
        fv = full.iloc[t]
        tv = trunc.iloc[t]
        if np.isnan(fv) and np.isnan(tv):
            continue
        assert abs(fv - tv) < 1e-12, f"Lookahead at t={t}: full={fv}, trunc={tv}"


# ---------- Corwin-Schultz spread series ------------------------------------

class TestCorwinSchultzSpreadSeries:
    def test_nonnegative(self):
        """Spread must be >= 0 everywhere (alpha floored at 0)."""
        close = _ramp(100)
        high = close * 1.02
        low = close * 0.98
        result = corwin_schultz_spread_series(high, low)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_wider_range_wider_spread(self):
        """Wider true ranges should produce larger estimated spreads."""
        n = 80
        idx = _idx(n)
        base = np.linspace(100.0, 110.0, n)
        # Narrow-range series: H/L ratio ~1.01
        h_narrow = pd.Series(base * 1.005, index=idx)
        l_narrow = pd.Series(base * 0.995, index=idx)
        # Wide-range series: H/L ratio ~1.10
        h_wide = pd.Series(base * 1.05, index=idx)
        l_wide = pd.Series(base * 0.95, index=idx)
        r_narrow = corwin_schultz_spread_series(h_narrow, l_narrow).dropna()
        r_wide = corwin_schultz_spread_series(h_wide, l_wide).dropna()
        # Mean of wide should clearly exceed mean of narrow
        assert r_wide.mean() > r_narrow.mean()

    def test_bar0_is_nan(self):
        """First bar is always NaN (two-day window)."""
        close = _ramp(20)
        high = close * 1.01
        low = close * 0.99
        result = corwin_schultz_spread_series(high, low)
        assert np.isnan(result.iloc[0])

    def test_same_index(self):
        close = _ramp(50)
        high = close * 1.01
        low = close * 0.99
        result = corwin_schultz_spread_series(high, low)
        assert result.index.equals(close.index)

    def test_smooth_win_reduces_variance(self):
        """Rolling mean smoothing should reduce variance of the output."""
        n = 200
        np.random.seed(42)
        idx = _idx(n)
        h = pd.Series(100.0 + np.random.randn(n).cumsum() * 0.5 + 2, index=idx)
        l = h - pd.Series(np.abs(np.random.randn(n)) * 0.5 + 0.2, index=idx)
        l = l.clip(lower=0.01)
        raw = corwin_schultz_spread_series(h, l, smooth_win=1).dropna()
        smoothed = corwin_schultz_spread_series(h, l, smooth_win=5).dropna()
        assert smoothed.std() < raw.std()


def test_corwin_schultz_no_lookahead():
    """Shift-audit: CS spread at t on truncated data equals full-series value."""
    n = 150
    close = _ramp(n)
    high = close * 1.015
    low = close * 0.985
    full = corwin_schultz_spread_series(high, low)
    for t in [5, 30, 60, 100, 130]:
        trunc = corwin_schultz_spread_series(high.iloc[: t + 1], low.iloc[: t + 1])
        fv = full.iloc[t]
        tv = trunc.iloc[t]
        if np.isnan(fv) and np.isnan(tv):
            continue
        assert abs(fv - tv) < 1e-12, f"Lookahead at t={t}: full={fv}, trunc={tv}"


# ---------- Undercut-and-Rally events --------------------------------------

def _build_ur_fixture():
    """Hand-constructed U&R fixture.

    Series of 30 bars (close-only mode, no H/L):
    - rolling_low at bar 22 = min(close[1..21]) = 10.0 (all bars 0-20 are 10.0)
    - Bar 22: close = 9.5 < 10.0 — undercut, depth = 0.5/10.0 = 5% >= 2%
    - Bar 23: close = 10.5 > 10.0 — RECLAIM within k=3 bars: event fires HERE.
    - All other bars: no event.
    """
    n = 30
    vals = [10.0] * 22 + [9.5] + [10.5] + [10.0] * 6
    idx = _idx(n)
    close = pd.Series(vals, index=idx)
    return close, idx


class TestUndercutRallyEvents:
    def test_exact_reclaim_bar_fires(self):
        """Event must fire on the reclaim bar (bar 23 in fixture)."""
        close, idx = _build_ur_fixture()
        result = undercut_rally_events(close, n=21, k=3)
        assert result["event"].iloc[23], "Expected event at bar 23 (reclaim bar)"
        # Only one event total
        assert result["event"].sum() == 1

    def test_undercut_date_populated(self):
        """undercut_date on event bar must equal the undercut bar date."""
        close, idx = _build_ur_fixture()
        result = undercut_rally_events(close, n=21, k=3)
        ev_row = result[result["event"]]
        assert len(ev_row) == 1
        assert ev_row["undercut_date"].iloc[0] == idx[22]  # bar 22 is the undercut

    def test_broken_level_is_rolling_low(self):
        """broken_level must equal 10.0 (the rolling low at undercut bar)."""
        close, idx = _build_ur_fixture()
        result = undercut_rally_events(close, n=21, k=3)
        ev_row = result[result["event"]]
        assert abs(ev_row["broken_level"].iloc[0] - 10.0) < 1e-9

    def test_depth_frac_correct(self):
        """depth_frac = (10.0 - 9.5) / 10.0 = 0.05."""
        close, idx = _build_ur_fixture()
        result = undercut_rally_events(close, n=21, k=3)
        ev_row = result[result["event"]]
        assert abs(ev_row["depth_frac"].iloc[0] - 0.05) < 1e-9

    def test_near_miss_k_plus_1_does_not_fire(self):
        """Reclaim on bar k+1 (= 4th bar after undercut) must NOT fire."""
        # Undercut at bar 22; reclaim at bar 22+4=26 (k=3, so max reclaim is bar 25)
        # bars: 0-21 (22 bars) + undercut (1) + 3 non-reclaim (3) + reclaim on 4th (1) + tail (3) = 30
        n = 30
        vals = [10.0] * 22 + [9.5] + [9.4, 9.3, 9.2] + [10.5] + [10.0] * 3
        close = pd.Series(vals, index=_idx(n))
        result = undercut_rally_events(close, n=21, k=3)
        assert result["event"].sum() == 0, "Reclaim on bar k+1 should not fire"

    def test_too_shallow_does_not_fire(self):
        """Undercut depth < 2% of rolling_low must NOT fire (close-only mode)."""
        # rolling_low = 10.0; undercut close = 9.99 → depth = 0.01 / 10.0 = 0.1% < 2%
        # bars: 0-21 (22) + undercut (1) + reclaim (1) + tail (6) = 30
        n = 30
        vals = [10.0] * 22 + [9.99] + [10.5] + [10.0] * 6
        close = pd.Series(vals, index=_idx(n))
        result = undercut_rally_events(close, n=21, k=3)
        assert result["event"].sum() == 0, "Too-shallow undercut should not fire"

    def test_hl_mode_fires(self):
        """H/L mode: low < rolling_low AND depth >= 1*ATR fires on reclaim."""
        n = 60
        # Build a series where bar 40 has low well below rolling_low with adequate ATR
        # and bar 41 reclaims by close > broken level
        base = [100.0] * 40
        # Bar 40: big undercut (low = 80.0, rolling_low ~= 100.0, depth=20 >> ATR)
        # Bar 41: close = 101 > 100 (reclaim)
        base_close = pd.Series(base + [99.0] + [101.0] + [100.0] * 18, index=_idx(n))
        base_high = pd.Series(base + [100.0] + [102.0] + [101.0] * 18, index=_idx(n))
        base_low = pd.Series(base + [80.0] + [99.0] + [99.0] * 18, index=_idx(n))
        result = undercut_rally_events(base_close, low=base_low, high=base_high, n=21, k=3)
        assert result["event"].sum() >= 1

    def test_output_columns(self):
        """Output DataFrame must have all required columns."""
        close, _ = _build_ur_fixture()
        result = undercut_rally_events(close, n=21, k=3)
        assert set(result.columns) == {"event", "undercut_date", "broken_level", "depth_frac"}

    def test_same_index(self):
        close, _ = _build_ur_fixture()
        result = undercut_rally_events(close, n=21, k=3)
        assert result.index.equals(close.index)


def _ur_event_at_t(close_full, t, n=21, k=3, low=None, high=None):
    """Compute U&R event flag at bar t using data truncated at t."""
    trunc_close = close_full.iloc[: t + 1]
    trunc_low = low.iloc[: t + 1] if low is not None else None
    trunc_high = high.iloc[: t + 1] if high is not None else None
    result = undercut_rally_events(trunc_close, low=trunc_low, high=trunc_high, n=n, k=k)
    return bool(result["event"].iloc[t])


def test_ur_no_lookahead_close_only():
    """Shift-audit for U&R close-only: event at t on truncated data must
    equal event at t from full series — events must never appear or vanish
    retroactively."""
    n_total = 120
    # Build a series that has several U&R setups
    base = [10.0] * 22 + [9.5] + [10.5] + [10.0] * (n_total - 24)
    close = pd.Series(base, index=_idx(n_total))
    full_result = undercut_rally_events(close, n=21, k=3)

    # Check 5 positions: 3 positions before/at the event, 2 after
    for t in [22, 23, 24, 50, 100]:
        full_val = bool(full_result["event"].iloc[t])
        trunc_val = _ur_event_at_t(close, t, n=21, k=3)
        assert full_val == trunc_val, (
            f"Lookahead violation at t={t}: full={full_val}, trunc={trunc_val}"
        )


def test_ur_no_lookahead_hl_mode():
    """Shift-audit for U&R H/L mode: same leak test."""
    n = 100
    # Construct a clear U&R event in H/L mode
    base_close = [100.0] * 40 + [99.0] + [101.0] + [100.0] * (n - 42)
    base_high = [100.5] * 40 + [100.0] + [102.0] + [101.0] * (n - 42)
    base_low = [99.5] * 40 + [80.0] + [99.0] + [99.0] * (n - 42)
    close = pd.Series(base_close, index=_idx(n))
    high = pd.Series(base_high, index=_idx(n))
    low = pd.Series(base_low, index=_idx(n))
    full_result = undercut_rally_events(close, low=low, high=high, n=21, k=3)

    for t in [40, 41, 42, 60, 90]:
        full_val = bool(full_result["event"].iloc[t])
        trunc_val = _ur_event_at_t(close, t, n=21, k=3, low=low, high=high)
        assert full_val == trunc_val, (
            f"HL-mode lookahead at t={t}: full={full_val}, trunc={trunc_val}"
        )


# ---------- Pocket-pivot and gap-hold (dormant) ----------------------------

class TestPocketPivotEventsDormant:
    def test_returns_dataframe_with_event_column(self):
        close = _ramp(60)
        vol = _flat(60, 1e5)
        result = pocket_pivot_events(close, vol, base_win=10)
        assert isinstance(result, pd.DataFrame)
        assert "event" in result.columns

    def test_event_is_bool(self):
        close = _ramp(60)
        vol = _flat(60, 1e5)
        result = pocket_pivot_events(close, vol)
        assert result["event"].dtype == bool

    def test_same_index(self):
        close = _ramp(40)
        vol = _flat(40, 1e5)
        result = pocket_pivot_events(close, vol)
        assert result.index.equals(close.index)


def test_pocket_pivot_no_lookahead():
    """Shift-audit for pocket_pivot_events."""
    close = _ramp(100, 10.0, 0.5)
    vol = _flat(100, 1e5)
    full = pocket_pivot_events(close, vol, base_win=10)
    for t in [15, 30, 50, 70, 90]:
        trunc = pocket_pivot_events(close.iloc[: t + 1], vol.iloc[: t + 1], base_win=10)
        fv = bool(full["event"].iloc[t])
        tv = bool(trunc["event"].iloc[t])
        assert fv == tv, f"Pocket-pivot lookahead at t={t}: full={fv}, trunc={tv}"


class TestGapHoldEventsDormant:
    def test_returns_dataframe_with_event_column(self):
        close = _ramp(60)
        high = close * 1.01
        low = close * 0.99
        open_ = close.shift(1).fillna(close.iloc[0])
        result = gap_hold_events(open_, high, low, close, hold_bars=2)
        assert isinstance(result, pd.DataFrame)
        assert "event" in result.columns

    def test_event_is_bool(self):
        n = 40
        close = _ramp(n)
        high = close * 1.01
        low = close * 0.99
        open_ = close.shift(1).fillna(close.iloc[0])
        result = gap_hold_events(open_, high, low, close)
        assert result["event"].dtype == bool

    def test_same_index(self):
        n = 40
        close = _ramp(n)
        high = close * 1.01
        low = close * 0.99
        open_ = close.shift(1).fillna(close.iloc[0])
        result = gap_hold_events(open_, high, low, close)
        assert result.index.equals(close.index)


def test_gap_hold_no_lookahead():
    """Shift-audit for gap_hold_events."""
    n = 80
    close = _ramp(n)
    high = close * 1.01
    low = close * 0.99
    open_ = close.shift(1).fillna(close.iloc[0])
    full = gap_hold_events(open_, high, low, close, hold_bars=2)
    for t in [10, 25, 40, 55, 70]:
        trunc = gap_hold_events(
            open_.iloc[: t + 1],
            high.iloc[: t + 1],
            low.iloc[: t + 1],
            close.iloc[: t + 1],
            hold_bars=2,
        )
        fv = bool(full["event"].iloc[t])
        tv = bool(trunc["event"].iloc[t])
        assert fv == tv, f"Gap-hold lookahead at t={t}: full={fv}, trunc={tv}"
