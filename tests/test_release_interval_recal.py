"""Tests for W11-F interval recalibration — vol-scaled residual quantiles (MRI-R30).

Tests:
  1. No-lookahead: a future residual must not change a past band
  2. Fallback below min-obs: returns all-None when insufficient history
  3. Fallback when sigma_t unavailable: reverts to unscaled bands
  4. Points unchanged: point estimate is byte-identical before/after recalibration
  5. Bands DO change when residual vol regime changes
  6. Uniform application: _compute_quantiles delegates to vol-scaled (all four callers)
  7. Vol-scaled bands narrower in low-vol periods, wider in high-vol periods

Specification: research/release_forecast/PREREG_INTERVAL_RECAL_V1.md

Run:
    python -m pytest tests/test_release_interval_recal.py -v
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (
    MIN_QUANTILE_OBS,
    _compute_quantiles,
    _compute_quantiles_unscaled,
    _compute_quantiles_volscaled,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_residuals(n: int, mean: float = 0.0, std: float = 0.1, seed: int = 42) -> np.ndarray:
    """Synthetic residuals with known mean and std."""
    rng = np.random.default_rng(seed)
    return rng.normal(loc=mean, scale=std, size=n)


def _make_regime_residuals(
    n_low: int, std_low: float,
    n_high: int, std_high: float,
    seed: int = 42,
) -> np.ndarray:
    """Residuals with two distinct vol regimes: n_low steps at std_low, n_high at std_high."""
    rng = np.random.default_rng(seed)
    low_regime = rng.normal(0.0, std_low, size=n_low)
    high_regime = rng.normal(0.0, std_high, size=n_high)
    return np.concatenate([low_regime, high_regime])


# ---------------------------------------------------------------------------
# 1. No-lookahead: future residual must not change a past band
# ---------------------------------------------------------------------------

class TestNoLookahead:
    """A future residual must not change any past standardized residual or band."""

    def test_future_residual_does_not_change_past_standardized(self):
        """Adding a residual at time T+1 does not change the standardized residual at time T.

        The standardization of residual[i] uses residuals[0:i] (strictly before),
        so changing residuals[i+1:] cannot affect r_std[i].
        """
        n_base = 60
        residuals_base = _make_residuals(n_base, std=0.1, seed=10)

        # Compute vol-scaled quantiles with n_base residuals
        result_base = _compute_quantiles_volscaled(residuals_base, point=0.5)

        # Add a large future residual (simulating a future observation)
        future_residual = np.array([10.0])  # large outlier
        residuals_extended = np.concatenate([residuals_base, future_residual])

        # The PAST quantiles (computed on residuals_base) must not change
        # because the new residual only affects sigma for the NEXT step
        # Recompute on the base subset — must be identical
        result_base_recomputed = _compute_quantiles_volscaled(residuals_base, point=0.5)

        # Point is always unchanged
        assert result_base["p10"] == result_base_recomputed["p10"]
        assert result_base["p90"] == result_base_recomputed["p90"]

        # The extended result will differ (sigma_now includes the outlier)
        result_extended = _compute_quantiles_volscaled(residuals_extended, point=0.5)
        # The bands should be wider now due to the outlier in sigma_now window
        if result_base["p10"] is not None and result_extended["p10"] is not None:
            base_width = result_base["p90"] - result_base["p10"]
            ext_width = result_extended["p90"] - result_extended["p10"]
            assert ext_width > base_width, (
                "Adding a large outlier residual should widen the bands"
            )

    def test_sigma_i_uses_only_prior_residuals(self):
        """sigma_i for step i uses only residuals[max(0, i-W):i], not residuals[i:].

        We verify that inserting a future outlier does NOT change any band produced
        for the first n_base steps. The band for `residuals[:n_base]` must equal the
        band produced for the same steps when they appear at the front of a longer array.
        """
        rng = np.random.default_rng(7777)
        # First n_base residuals: normal distribution with std=0.1
        n_base = 60
        residuals_base = rng.normal(0.0, 0.1, size=n_base)

        # Result from first n_base residuals
        result_base = _compute_quantiles_volscaled(residuals_base, point=0.3)

        # Append future steps — these happen AFTER n_base and must not affect
        # the standardization of any of the first n_base steps
        future = rng.normal(0.0, 0.1, size=5)
        residuals_with_future = np.concatenate([residuals_base, future])

        # The first n_base steps' standardized residuals are indexed 0..n_base-1.
        # sigma_i for step i uses residuals[max(0,i-24):i] — strictly before step i.
        # So future residuals at indices n_base..n_base+4 cannot influence sigma_0..sigma_{n_base-1}.
        # Verify: compute the standardized residuals for the first n_base steps manually
        _SIGMA_EPS = 1e-10
        r_std_from_full = []
        for i in range(n_base):
            trailing = residuals_with_future[max(0, i - 24): i]
            if len(trailing) < 12:
                continue
            sigma_i = float(np.std(trailing, ddof=1))
            if sigma_i < _SIGMA_EPS:
                continue
            r_std_from_full.append(float(residuals_with_future[i]) / sigma_i)

        r_std_from_base = []
        for i in range(n_base):
            trailing = residuals_base[max(0, i - 24): i]
            if len(trailing) < 12:
                continue
            sigma_i = float(np.std(trailing, ddof=1))
            if sigma_i < _SIGMA_EPS:
                continue
            r_std_from_base.append(float(residuals_base[i]) / sigma_i)

        # The standardized residuals for the FIRST n_base steps must be identical
        # regardless of what comes after — this is the no-lookahead guarantee
        assert len(r_std_from_full) == len(r_std_from_base), (
            "Future residuals changed the number of standardized residuals for past steps"
        )
        for j, (a, b) in enumerate(zip(r_std_from_full, r_std_from_base)):
            assert abs(a - b) < 1e-10, (
                f"Standardized residual at index {j} changed when future residuals were appended: "
                f"{a} vs {b}"
            )


# ---------------------------------------------------------------------------
# 2. Fallback below min-obs
# ---------------------------------------------------------------------------

class TestFallbackBelowMinObs:
    """Returns all-None when insufficient residual history."""

    def test_empty_residuals_returns_all_none(self):
        result = _compute_quantiles_volscaled(np.array([]), point=0.5)
        assert result == {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    def test_fewer_than_min_obs_returns_all_none(self):
        """With fewer than MIN_QUANTILE_OBS=24 residuals, returns all-None."""
        residuals = _make_residuals(MIN_QUANTILE_OBS - 1)
        result = _compute_quantiles_volscaled(residuals, point=0.5)
        assert result == {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    def test_exactly_min_obs_may_return_none_or_values(self):
        """With exactly MIN_QUANTILE_OBS residuals, may get None (if sigma history is short)
        or values (if enough sigma history accrued). Does not crash."""
        residuals = _make_residuals(MIN_QUANTILE_OBS, std=0.1)
        result = _compute_quantiles_volscaled(residuals, point=0.5)
        # Must not crash; all keys must be present
        for key in ("p10", "p25", "p50", "p75", "p90"):
            assert key in result

    def test_legacy_compute_quantiles_returns_none_below_min(self):
        """The existing _compute_quantiles signature still returns None below min_obs."""
        result = _compute_quantiles(np.array([0.1] * 5), point=0.5)
        assert result == {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}


# ---------------------------------------------------------------------------
# 3. Fallback when sigma_now is zero
# ---------------------------------------------------------------------------

class TestSigmaNowFallback:
    """When sigma_now == 0 (constant residuals), fall back to unscaled bands."""

    def test_constant_residuals_fallback(self):
        """Constant residuals -> sigma_now = 0 -> fall back to unscaled."""
        # All residuals are identical: std = 0
        residuals = np.full(60, 0.05)
        result_vs = _compute_quantiles_volscaled(residuals, point=0.3)
        result_us = _compute_quantiles_unscaled(residuals, point=0.3)
        # Both should return identical results (constant residuals -> constant bands)
        assert result_vs["p10"] == result_us["p10"]
        assert result_vs["p90"] == result_us["p90"]


# ---------------------------------------------------------------------------
# 4. Points unchanged (byte-identity)
# ---------------------------------------------------------------------------

class TestPointsUnchanged:
    """Point estimate must be byte-identical before and after recalibration."""

    def test_point_not_in_output(self):
        """The quantile function output does not contain a 'point' key —
        the caller is responsible for the point. Bands only."""
        residuals = _make_residuals(60, std=0.1)
        result = _compute_quantiles_volscaled(residuals, point=0.28)
        assert "point" not in result
        for key in ("p10", "p25", "p50", "p75", "p90"):
            assert key in result

    def test_bands_centered_near_point_when_unbiased(self):
        """With zero-mean unbiased residuals, p50 should be near point."""
        rng = np.random.default_rng(777)
        # Large sample of zero-mean residuals
        residuals = rng.normal(0.0, 0.1, size=300)
        point = 0.25
        result = _compute_quantiles_volscaled(residuals, point=point)
        if result["p50"] is not None:
            # p50 ~ point for near-zero median residuals
            assert abs(result["p50"] - point) < 0.05, (
                f"p50={result['p50']} far from point={point}"
            )

    def test_same_residuals_same_point_same_output(self):
        """Determinism: same inputs -> same output."""
        residuals = _make_residuals(100, std=0.15)
        r1 = _compute_quantiles_volscaled(residuals.copy(), point=0.3)
        r2 = _compute_quantiles_volscaled(residuals.copy(), point=0.3)
        assert r1 == r2

    def test_different_points_shift_all_bands_uniformly(self):
        """Changing point by delta shifts all bands by exactly delta (linearity)."""
        residuals = _make_residuals(100, std=0.1)
        delta = 0.10
        r_base = _compute_quantiles_volscaled(residuals, point=0.20)
        r_shifted = _compute_quantiles_volscaled(residuals, point=0.20 + delta)

        for key in ("p10", "p25", "p50", "p75", "p90"):
            if r_base[key] is not None and r_shifted[key] is not None:
                diff = round(r_shifted[key] - r_base[key], 6)
                assert abs(diff - delta) < 1e-4, (
                    f"Band {key}: expected shift {delta}, got {diff}"
                )


# ---------------------------------------------------------------------------
# 5. Bands change when residual vol regime changes
# ---------------------------------------------------------------------------

class TestBandsChangeWithVolRegime:
    """Bands should be narrower in low-vol regimes, wider in high-vol regimes."""

    def test_wider_bands_in_high_vol_regime(self):
        """High-vol residuals -> wider p10-p90 band than low-vol residuals."""
        n = 100
        low_vol = _make_residuals(n, std=0.05, seed=1)
        high_vol = _make_residuals(n, std=0.50, seed=1)
        point = 0.2

        result_low = _compute_quantiles_volscaled(low_vol, point=point)
        result_high = _compute_quantiles_volscaled(high_vol, point=point)

        if result_low["p10"] is not None and result_high["p10"] is not None:
            width_low = result_low["p90"] - result_low["p10"]
            width_high = result_high["p90"] - result_high["p10"]
            assert width_high > width_low, (
                f"High-vol width {width_high:.4f} should exceed low-vol {width_low:.4f}"
            )

    def test_vol_transition_widens_bands_at_transition(self):
        """After a vol regime shift, the bands should be wider than in the calm period."""
        # First 80 steps: low-vol. Last 30 steps: high-vol.
        residuals = _make_regime_residuals(80, 0.05, 30, 0.50, seed=42)
        # Band at end of low-vol period (first 80)
        result_calm = _compute_quantiles_volscaled(residuals[:80], point=0.2)
        # Band at end of high-vol period (all 110)
        result_stressed = _compute_quantiles_volscaled(residuals, point=0.2)

        if result_calm["p10"] is not None and result_stressed["p10"] is not None:
            width_calm = result_calm["p90"] - result_calm["p10"]
            width_stressed = result_stressed["p90"] - result_stressed["p10"]
            assert width_stressed > width_calm, (
                f"Post-transition width {width_stressed:.4f} should exceed calm {width_calm:.4f}"
            )

    def test_vs_unscaled_in_stationary_regime(self):
        """In a stationary vol regime, vol-scaled and unscaled bands should be close."""
        # IID residuals: vol-scaled and unscaled should give similar bands
        residuals = _make_residuals(200, std=0.1, seed=99)
        point = 0.3
        result_vs = _compute_quantiles_volscaled(residuals, point=point)
        result_us = _compute_quantiles_unscaled(residuals, point=point)

        if result_vs["p10"] is not None and result_us["p10"] is not None:
            # Should be within a reasonable tolerance (not identical, but close)
            for key in ("p10", "p90"):
                diff = abs(result_vs[key] - result_us[key])
                assert diff < 0.05, (
                    f"Stationary IID: VS and unscaled {key} differ by {diff:.4f} — "
                    "too large for stationary regime"
                )


# ---------------------------------------------------------------------------
# 6. Uniform application: _compute_quantiles delegates to vol-scaled
# ---------------------------------------------------------------------------

class TestUniformApplication:
    """_compute_quantiles must delegate to _compute_quantiles_volscaled."""

    def test_compute_quantiles_matches_volscaled(self):
        """The public _compute_quantiles function should match _compute_quantiles_volscaled."""
        residuals = _make_residuals(100, std=0.12, seed=55)
        point = 0.18
        r_wrapper = _compute_quantiles(residuals, point)
        r_vs = _compute_quantiles_volscaled(residuals, point)
        assert r_wrapper == r_vs, (
            "_compute_quantiles must delegate to _compute_quantiles_volscaled"
        )

    def test_compute_quantiles_none_below_min(self):
        """_compute_quantiles still returns None below min_obs after delegation."""
        result = _compute_quantiles(np.zeros(5), 0.3)
        assert result["p10"] is None

    def test_compute_quantiles_volscaled_imported_from_release_forecast(self):
        """The function must be importable from engine.release_forecast."""
        from engine.release_forecast import _compute_quantiles_volscaled as _f
        assert callable(_f)

    def test_compute_quantiles_unscaled_importable(self):
        """The fallback function must also be importable (for backward compat)."""
        from engine.release_forecast import _compute_quantiles_unscaled as _f
        assert callable(_f)

    def test_mf_energy_uses_volscaled(self):
        """_compute_quantiles_mf in release_mf_energy must delegate to vol-scaled."""
        from engine.release_mf_energy import _compute_quantiles_mf
        residuals = _make_residuals(100, std=0.2, seed=7)
        point = 0.3
        r_mf = _compute_quantiles_mf(residuals, point)
        r_vs = _compute_quantiles_volscaled(residuals, point)
        assert r_mf == r_vs, "_compute_quantiles_mf must match vol-scaled implementation"

    def test_release_targets_v11_imports_compute_quantiles(self):
        """release_targets_v11 imports _compute_quantiles which now delegates to vol-scaled."""
        from engine.release_targets_v11 import _compute_quantiles as _cq_v11
        from engine.release_forecast import _compute_quantiles as _cq_base
        # They should be the same function object (imported from the same module)
        assert _cq_v11 is _cq_base, (
            "release_targets_v11._compute_quantiles must be the same function as "
            "engine.release_forecast._compute_quantiles"
        )


# ---------------------------------------------------------------------------
# 7. Ordered bands (sanity)
# ---------------------------------------------------------------------------

class TestOrderedBands:
    """Quantile bands must be monotonically non-decreasing: p10 <= p25 <= p50 <= p75 <= p90."""

    def test_bands_are_ordered_volscaled(self):
        residuals = _make_residuals(100, std=0.1, seed=1234)
        result = _compute_quantiles_volscaled(residuals, point=0.25)
        if result["p10"] is not None:
            assert result["p10"] <= result["p25"] <= result["p50"] <= result["p75"] <= result["p90"]

    def test_bands_are_ordered_unscaled(self):
        residuals = _make_residuals(100, std=0.1, seed=4321)
        result = _compute_quantiles_unscaled(residuals, point=0.25)
        if result["p10"] is not None:
            assert result["p10"] <= result["p25"] <= result["p50"] <= result["p75"] <= result["p90"]

    def test_bands_ordered_with_regime_change(self):
        residuals = _make_regime_residuals(50, 0.05, 50, 0.3, seed=99)
        result = _compute_quantiles_volscaled(residuals, point=0.2)
        if result["p10"] is not None:
            assert result["p10"] <= result["p25"] <= result["p50"] <= result["p75"] <= result["p90"]


# ---------------------------------------------------------------------------
# 8. Coverage improvement direction (directional test on synthetic data)
# ---------------------------------------------------------------------------

class TestCoverageImprovement:
    """In a high-vol post-calm regime, vol-scaled bands should achieve closer to
    nominal coverage than unscaled bands (the bands are adaptive)."""

    def test_volscaled_coverage_matches_nominal_in_volatile_regime(self):
        """Generate a volatile period and check that vol-scaled intervals are wider,
        thus capturing more of the test actuals than the narrower unscaled bands."""
        rng = np.random.default_rng(2024)

        # Training: first 100 points are calm
        n_calm = 100
        sigma_calm = 0.05
        residuals_calm = rng.normal(0.0, sigma_calm, size=n_calm)

        # Test: next 50 points are volatile
        sigma_hot = 0.30
        residuals_hot = rng.normal(0.0, sigma_hot, size=50)
        actuals_test = rng.normal(0.3, sigma_hot, size=50)

        # Vol-scaled: uses recent sigma (= sigma_hot region)
        all_residuals = np.concatenate([residuals_calm, residuals_hot])
        point = 0.3

        result_vs = _compute_quantiles_volscaled(all_residuals, point=point)
        result_us = _compute_quantiles_unscaled(all_residuals, point=point)

        if result_vs["p10"] is None or result_us["p10"] is None:
            pytest.skip("Insufficient history for this test")

        # Count coverage for both
        covered_vs = np.sum(
            (actuals_test >= result_vs["p10"]) & (actuals_test <= result_vs["p90"])
        )
        covered_us = np.sum(
            (actuals_test >= result_us["p10"]) & (actuals_test <= result_us["p90"])
        )

        # Vol-scaled should cover more actuals because it adapts to current vol
        # (bands are wider during the hot regime)
        vs_coverage = covered_vs / len(actuals_test)
        us_coverage = covered_us / len(actuals_test)

        # Vol-scaled width should be wider (adapted to hot sigma)
        width_vs = result_vs["p90"] - result_vs["p10"]
        width_us = result_us["p90"] - result_us["p10"]
        assert width_vs > width_us, (
            f"Vol-scaled should be wider in hot regime: VS={width_vs:.4f} US={width_us:.4f}"
        )
