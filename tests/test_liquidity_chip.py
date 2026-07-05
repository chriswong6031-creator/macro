"""Unit tests for engine.liquidity_chip (W5b days-to-build liquidity chip).

Tests mirror the REAL call shape: pandas Series of close prices and volume
from data/stocks/*.parquet (schema: index=Date, close float, volume float).
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from engine import liquidity_chip as lc


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _series(values: list[float], freq: str = "B") -> pd.Series:
    """Return a business-day-indexed Series matching the real store schema."""
    idx = pd.date_range("2026-01-01", periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


# --------------------------------------------------------------------------- #
#  Tier classification                                                          #
# --------------------------------------------------------------------------- #

class TestTier:
    def test_deep(self):
        assert lc._tier(lc.TIER_DEEP_THRESHOLD) == "deep"
        assert lc._tier(lc.TIER_DEEP_THRESHOLD * 2) == "deep"

    def test_ok_boundary(self):
        assert lc._tier(lc.TIER_OK_THRESHOLD) == "ok"
        assert lc._tier(lc.TIER_DEEP_THRESHOLD - 1) == "ok"

    def test_thin_boundary(self):
        assert lc._tier(lc.TIER_THIN_THRESHOLD) == "thin"
        assert lc._tier(lc.TIER_OK_THRESHOLD - 1) == "thin"

    def test_illiquid(self):
        assert lc._tier(lc.TIER_THIN_THRESHOLD - 1) == "illiquid"
        assert lc._tier(0.0) == "illiquid"


# --------------------------------------------------------------------------- #
#  Days-to-build helper                                                        #
# --------------------------------------------------------------------------- #

class TestDaysToBuild:
    def test_basic_formula(self):
        # $100k clip at $1M/day ADV: 100k / (1M * 10%) = 1.0 day
        result = lc._days_to_build(lc.CLIP_100K, 1_000_000.0)
        assert math.isclose(result, 1.0, rel_tol=1e-9)

    def test_1m_clip(self):
        # $1M clip at $1M/day ADV: 1M / (1M * 10%) = 10 days
        result = lc._days_to_build(lc.CLIP_1M, 1_000_000.0)
        assert math.isclose(result, 10.0, rel_tol=1e-9)

    def test_zero_adv_returns_none(self):
        assert lc._days_to_build(lc.CLIP_100K, 0.0) is None

    def test_negative_adv_returns_none(self):
        assert lc._days_to_build(lc.CLIP_100K, -1.0) is None


# --------------------------------------------------------------------------- #
#  compute() — main entry point                                                #
# --------------------------------------------------------------------------- #

class TestCompute:
    def _make_deep_stock(self, n: int = 25) -> tuple[pd.Series, pd.Series]:
        """A large-cap stock with >$50M median ADV (e.g. ~$300/share × 200k shares = $60M)."""
        close = _series([300.0] * n)
        volume = _series([200_000.0] * n)
        return close, volume

    def _make_thin_stock(self, n: int = 25) -> tuple[pd.Series, pd.Series]:
        """A thin stock with ~$2M ADV (e.g. $20/share × 100k shares = $2M)."""
        close = _series([20.0] * n)
        volume = _series([100_000.0] * n)
        return close, volume

    def test_returns_dict_with_required_keys(self):
        close, volume = self._make_deep_stock()
        result = lc.compute(close, volume)
        assert result is not None
        assert "adv_dollar_20d_median" in result
        assert "tier" in result
        assert "days_to_build_100k" in result
        assert "days_to_build_1m" in result

    def test_deep_tier_large_cap(self):
        close, volume = self._make_deep_stock()
        result = lc.compute(close, volume)
        assert result is not None
        assert result["tier"] == "deep"
        # ADV = 300 * 200_000 = $60M  -->  tier deep
        assert result["adv_dollar_20d_median"] == pytest.approx(60_000_000.0, rel=0.01)

    def test_thin_tier(self):
        close, volume = self._make_thin_stock()
        result = lc.compute(close, volume)
        assert result is not None
        assert result["tier"] == "thin"

    def test_days_to_build_100k_deep(self):
        # ADV = 60M, capacity_per_day = 6M; 100k / 6M = 0.0167 day
        # After round(..., 1) that becomes 0.0 -- the chip still emits a valid float.
        close, volume = self._make_deep_stock()
        result = lc.compute(close, volume)
        assert result is not None
        raw = lc.CLIP_100K / (60_000_000.0 * lc.MAX_ADV_PCT)
        assert result["days_to_build_100k"] == pytest.approx(round(raw, 1), abs=0.05)

    def test_days_to_build_1m_deep(self):
        # ADV = 60M; $1M / (60M * 10%) = 0.1667 day -> rounds to 0.2
        close, volume = self._make_deep_stock()
        result = lc.compute(close, volume)
        assert result is not None
        raw = lc.CLIP_1M / (60_000_000.0 * lc.MAX_ADV_PCT)
        assert result["days_to_build_1m"] == pytest.approx(round(raw, 1), abs=0.05)

    def test_uses_median_not_mean(self):
        """Median must resist an outlier session whereas mean would shift."""
        # 19 sessions at $10M ADV + 1 spike at $500M
        close_vals = [100.0] * 20
        volume_vals = [100_000.0] * 19 + [5_000_000.0]
        close = _series(close_vals)
        volume = _series(volume_vals)
        result = lc.compute(close, volume)
        assert result is not None
        # median = 100 * 100_000 = $10M (spike doesn't dominate)
        assert result["adv_dollar_20d_median"] == pytest.approx(10_000_000.0, rel=0.01)

    def test_returns_none_when_insufficient_data(self):
        # Fewer than MIN_SESSIONS usable rows
        close = _series([100.0] * 3)
        volume = _series([50_000.0] * 3)
        result = lc.compute(close, volume)
        assert result is None

    def test_returns_none_when_volume_is_all_nan(self):
        close = _series([100.0] * 25)
        volume = _series([float("nan")] * 25)
        result = lc.compute(close, volume)
        assert result is None

    def test_handles_nan_in_volume_gracefully(self):
        """A few NaN sessions in the 20-window should not crash; result is still valid."""
        close_vals = [100.0] * 25
        volume_vals = [float("nan")] * 5 + [100_000.0] * 20
        close = _series(close_vals)
        volume = _series(volume_vals)
        result = lc.compute(close, volume)
        # Only the tail(20) is used, and it overlaps the non-NaN region,
        # so result should exist.
        assert result is not None
        assert result["tier"] in ("deep", "ok", "thin", "illiquid")

    def test_only_uses_last_window_sessions(self):
        """Historical outliers beyond WINDOW sessions must not affect the median."""
        # First 10 sessions: extreme $500M ADV; last WINDOW sessions: $10M ADV
        spike_n = 10
        normal_n = lc.WINDOW
        close = _series([500.0] * spike_n + [100.0] * normal_n)
        volume = _series([1_000_000.0] * spike_n + [100_000.0] * normal_n)
        result = lc.compute(close, volume)
        assert result is not None
        # tail(WINDOW) sees only the $10M sessions
        assert result["adv_dollar_20d_median"] == pytest.approx(10_000_000.0, rel=0.01)

    def test_output_values_are_python_natives_for_json(self):
        """All returned values must be Python float or str, not numpy scalars."""
        import numpy as np
        close, volume = self._make_deep_stock()
        result = lc.compute(close, volume)
        assert result is not None
        for key, val in result.items():
            if val is not None:
                assert not isinstance(val, np.generic), (
                    f"{key}={val!r} is a numpy scalar — json.dumps would fail silently"
                )
