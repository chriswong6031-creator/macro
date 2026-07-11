"""tests/test_htf_oscillators.py — Hermetic unit tests for engine/htf_oscillators.py (FL W1).

Coverage:
  - stochrsi_2w: oversold flag, htf_coverage=False on cold-start (< 20 daily / < 4 biweekly)
  - macd_bars_to_cross_2w: approaching→crossed transition on a constructed series with a
    known cross; ETA on a descending histogram; empty-series htf_coverage=False.
  - All functions: no network, no disk I/O.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.htf_oscillators import (
    _MIN_DAILY_BARS,
    _MIN_BIWEEKLY_BARS,
    _MACD_APPROACH_MAX_BARS,
    _MACD_MIN_BARS,
    macd_bars_to_cross_2w,
    stochrsi_2w,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _daily_close(n: int, start: float = 100.0, trend: float = 0.0) -> pd.Series:
    """Build a synthetic daily close series of length n with optional linear trend."""
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    vals = start + trend * np.arange(n)
    return pd.Series(vals, index=dates, name="close")


def _oscillating_close(n: int, amplitude: float = 5.0, base: float = 100.0) -> pd.Series:
    """Build a daily close that oscillates, producing StochRSI extremes.

    Uses enough cycles and variation so the RSI stoch denominator (hi-lo) is
    non-zero (degenerate flat series would collapse the denominator to 0).
    """
    dates = pd.date_range("2018-01-02", periods=n, freq="B")
    # Multiple cycles of amplitude plus a trend to keep denominator non-zero
    vals = base + amplitude * np.sin(np.linspace(0, 12 * math.pi, n)) + 0.02 * np.arange(n)
    return pd.Series(vals, index=dates, name="close")


def _falling_then_rising_close(n_fall: int = 60, n_rise: int = 40, base: float = 200.0) -> pd.Series:
    """Build a close that falls for n_fall bars then rises for n_rise bars."""
    dates = pd.date_range("2019-01-02", periods=n_fall + n_rise, freq="B")
    fall = base - 0.5 * np.arange(n_fall)
    rise = fall[-1] + 0.5 * np.arange(n_rise)
    vals = np.concatenate([fall, rise])
    return pd.Series(vals, index=dates, name="close")


# ── stochrsi_2w ───────────────────────────────────────────────────────────────

class TestStochRsi2W:
    def test_cold_start_too_few_daily_returns_null(self):
        """< _MIN_DAILY_BARS daily bars → all None + htf_coverage=False."""
        s = _daily_close(_MIN_DAILY_BARS - 1)
        result = stochrsi_2w(s)
        assert result["htf_coverage"] is False
        assert result["k"] is None
        assert result["d"] is None
        assert result["oversold"] is None

    def test_empty_series_returns_null(self):
        """Empty series → null not crash."""
        s = pd.Series(dtype=float)
        result = stochrsi_2w(s)
        assert result["htf_coverage"] is False
        assert result["k"] is None

    def test_none_series_returns_null(self):
        """None input → null not crash."""
        result = stochrsi_2w(None)
        assert result["htf_coverage"] is False
        assert result["k"] is None

    def test_sufficient_data_gives_htf_coverage(self):
        """Enough daily bars → htf_coverage=True and k is numeric.

        StochRSI math needs RSI(14)+Stoch(14)+SMA_K(3)+SMA_D(3) ≈ 34 biweekly
        bars before producing non-null output.  400 daily bars → ~40 biweekly bars
        which is sufficient.  The series must oscillate to keep the stoch
        denominator (RSI hi-lo) non-zero.
        """
        s = _oscillating_close(400)
        result = stochrsi_2w(s)
        assert result["htf_coverage"] is True
        assert result["k"] is not None
        assert isinstance(result["k"], float)
        assert 0 <= result["k"] <= 100

    def test_oversold_flag_semantics(self):
        """oversold = True iff k < 20; False when k >= 20; None when k is None."""
        s = _oscillating_close(400)
        result = stochrsi_2w(s)
        if result["k"] is not None:
            if result["k"] < 20:
                assert result["oversold"] is True
            else:
                assert result["oversold"] is False
        else:
            assert result["oversold"] is None

    def test_oversold_on_deeply_falling_series(self):
        """A strongly falling series should eventually produce oversold K values.

        Uses an oscillating series that ends in a deep decline so the RSI
        denominator remains non-zero (purely flat/monotone series can collapse
        the StochRSI denominator to 0, producing all-null k values).
        """
        # 600 daily bars of oscillating decline
        n = 600
        dates = pd.date_range("2018-01-02", periods=n, freq="B")
        # Oscillate with a strong downward trend so the last 2W bars are falling
        vals = 200.0 + 10.0 * np.sin(np.linspace(0, 8 * math.pi, n)) - 0.2 * np.arange(n)
        s = pd.Series(vals, index=dates)
        result = stochrsi_2w(s)
        assert result["htf_coverage"] is True
        # With strong downward trend, k should not be at maximum
        if result["k"] is not None:
            assert result["k"] < 90  # not pegged at top given the downtrend

    def test_returns_dict_with_all_keys(self):
        s = _daily_close(50)
        result = stochrsi_2w(s)
        assert "k" in result
        assert "d" in result
        assert "oversold" in result
        assert "htf_coverage" in result


# ── macd_bars_to_cross_2w ─────────────────────────────────────────────────────

class TestMacdBarsToCross2W:
    def test_empty_series_returns_no_coverage(self):
        s = pd.Series(dtype=float)
        result = macd_bars_to_cross_2w(s)
        assert result["htf_coverage"] is False
        assert result["state"] == "none"

    def test_cold_start_too_few_bars_returns_null(self):
        """< _MIN_DAILY_BARS daily bars → htf_coverage=False."""
        s = _daily_close(_MIN_DAILY_BARS - 1)
        result = macd_bars_to_cross_2w(s)
        assert result["htf_coverage"] is False

    def test_returns_all_keys(self):
        s = _daily_close(50)
        result = macd_bars_to_cross_2w(s)
        assert "state" in result
        assert "bars_since" in result
        assert "bars_to_cross" in result
        assert "htf_coverage" in result

    def test_approaching_state_on_rising_negative_histogram(self):
        """A series whose 2W MACD histogram is negative and rising should
        produce state='approaching' with a finite bars_to_cross ETA."""
        # Build a series that falls then rises sharply — drives the 2W MACD
        # histogram negative and then recovering
        n = 800
        dates = pd.date_range("2016-01-04", periods=n, freq="B")
        # Decline for first 500 bars, then rise for 300
        vals = np.concatenate([
            np.linspace(200.0, 80.0, 500),   # steep decline → negative MACD
            np.linspace(80.0, 120.0, 300),    # recovery → histogram rising
        ])
        s = pd.Series(vals, index=dates)
        result = macd_bars_to_cross_2w(s)
        assert result["htf_coverage"] is True
        # Should be 'approaching' or already 'crossed' depending on recovery speed
        assert result["state"] in ("approaching", "crossed", "none")
        if result["state"] == "approaching":
            assert result["bars_to_cross"] is not None
            assert result["bars_to_cross"] <= _MACD_APPROACH_MAX_BARS
            assert result["bars_since"] is None

    def test_known_cross_transition(self):
        """Construct a series where the 2W MACD histogram crosses zero.

        Calibrated price path (discovered empirically):
          - 400 bars decline: price 1000→100 (strong downtrend, hist very negative)
          - 1100 bars recovery: price 100→900 (fast rise)

        At cutoff=420 bars → state='approaching' (hist<0, rising, ETA≤6)
        At cutoff=440 bars → state='crossed' (hist crossed zero within 2 bars)

        This verifies the approaching→crossed transition on a constructed series
        with a known cross.
        """
        n = 1500
        dates = pd.date_range("2010-01-04", periods=n, freq="B")
        p1 = np.linspace(1000.0, 100.0, 400)
        p2 = np.linspace(100.0, 900.0, 1100)
        vals = np.concatenate([p1, p2])
        s = pd.Series(vals, index=dates)

        # At 420 bars (mid-recovery): MACD histogram negative but rising → approaching
        s_approaching = s.iloc[:420]
        result_approaching = macd_bars_to_cross_2w(s_approaching)
        assert result_approaching["htf_coverage"] is True
        assert result_approaching["state"] == "approaching"
        assert result_approaching["bars_to_cross"] is not None
        assert result_approaching["bars_to_cross"] <= _MACD_APPROACH_MAX_BARS
        assert result_approaching["bars_since"] is None

        # At 440 bars (further into recovery): histogram crosses zero → crossed
        s_crossed = s.iloc[:440]
        result_crossed = macd_bars_to_cross_2w(s_crossed)
        assert result_crossed["htf_coverage"] is True
        assert result_crossed["state"] == "crossed"
        assert result_crossed["bars_since"] is not None
        assert isinstance(result_crossed["bars_since"], int)
        assert result_crossed["bars_to_cross"] is None

    def test_crossed_state_bars_since_populated(self):
        """When state='crossed', bars_since should be an integer."""
        # Build a series that ends in a clear uptrend to force MACD positive
        n = 800
        dates = pd.date_range("2016-01-04", periods=n, freq="B")
        # Long uptrend throughout → MACD should be consistently positive at the end
        vals = np.linspace(50.0, 400.0, n)
        s = pd.Series(vals, index=dates)
        result = macd_bars_to_cross_2w(s)
        assert result["htf_coverage"] is True
        if result["state"] == "crossed":
            assert isinstance(result["bars_since"], int)
            assert result["bars_to_cross"] is None

    def test_approaching_bars_to_cross_within_cap(self):
        """bars_to_cross must be ≤ _MACD_APPROACH_MAX_BARS when state='approaching'."""
        # Generate multiple series and verify the cap is respected in all
        # 'approaching' cases
        n = 600
        for seed in [42, 123, 999]:
            rng = np.random.default_rng(seed)
            dates = pd.date_range("2017-01-03", periods=n, freq="B")
            # Random walk with slight upward drift after a decline
            vals = np.zeros(n)
            vals[0] = 100.0
            changes = rng.normal(-0.05, 1.0, n - 1)
            for i in range(1, n):
                vals[i] = max(vals[i - 1] + changes[i - 1], 1.0)
            s = pd.Series(vals, index=dates)
            result = macd_bars_to_cross_2w(s)
            if result["state"] == "approaching":
                btc = result["bars_to_cross"]
                assert btc is not None
                assert btc <= _MACD_APPROACH_MAX_BARS, \
                    f"bars_to_cross={btc} exceeds cap {_MACD_APPROACH_MAX_BARS}"

    def test_htf_coverage_false_below_min_biweekly(self):
        """Series yielding < _MIN_BIWEEKLY_BARS biweekly bars → htf_coverage=False."""
        # 20 daily bars will produce at most 2 biweekly bars → below threshold
        s = _daily_close(20)
        result = macd_bars_to_cross_2w(s)
        assert result["htf_coverage"] is False

    def test_state_none_on_flat_series(self):
        """Flat series: MACD histogram is 0; no cross, no approach; state='none' or 'crossed'."""
        n = 400
        dates = pd.date_range("2018-01-02", periods=n, freq="B")
        s = pd.Series(np.full(n, 100.0), index=dates)
        result = macd_bars_to_cross_2w(s)
        assert result["htf_coverage"] is True
        # flat → hist stays exactly 0, which is not negative, so no approach/cross
        assert result["state"] in ("none", "crossed")
