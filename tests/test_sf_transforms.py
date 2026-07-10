"""tests/test_sf_transforms.py — property tests for the transform vocabulary.

Key property: NO-LOOKAHEAD — mutating future values of the input must not
change past output values for any rolling/causal transform.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.signal_foundry.transforms import (
    TRANSFORMS,
    apply_pipeline,
    _zscore,
    _pctile_rank,
    _diff,
    _pct_change,
    _sma,
    _ema,
    _lag,
    _sign,
    _clip,
    _rolling_vol,
    _rolling_corr,
    _ratio,
    _spread,
    _drawdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_series(n: int = 300, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-01", periods=n, freq="B")
    return pd.Series(rng.standard_normal(n) + 10, index=idx)


def _assert_no_lookahead(transform_fn, s: pd.Series, corrupt_after: int = 100) -> None:
    """Mutate all values after `corrupt_after` and assert past outputs unchanged."""
    out_before = transform_fn(s.copy())

    s_corrupt = s.copy()
    rng = np.random.default_rng(999)
    s_corrupt.iloc[corrupt_after:] = rng.standard_normal(len(s) - corrupt_after) * 1000

    out_after = transform_fn(s_corrupt)

    # Past outputs must be identical (or both NaN)
    past_before = out_before.iloc[:corrupt_after]
    past_after = out_after.iloc[:corrupt_after]

    np.testing.assert_array_equal(
        np.isnan(past_before.to_numpy(float)),
        np.isnan(past_after.to_numpy(float)),
        err_msg="NaN pattern changed for past values after future corruption",
    )
    valid_mask = ~np.isnan(past_before.to_numpy(float))
    np.testing.assert_allclose(
        past_before.to_numpy(float)[valid_mask],
        past_after.to_numpy(float)[valid_mask],
        rtol=1e-10,
        err_msg=f"Past outputs changed after corrupting future values in {transform_fn.__name__}",
    )


# ---------------------------------------------------------------------------
# NO-LOOKAHEAD property tests
# ---------------------------------------------------------------------------

class TestNoLookahead:
    """Mutate future values → past outputs must be unchanged."""

    def test_zscore_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _zscore(x, window=63), s, corrupt_after=120)

    def test_pctile_rank_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _pctile_rank(x, window=63), s, corrupt_after=100)

    def test_diff_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _diff(x, n=5), s, corrupt_after=100)

    def test_pct_change_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _pct_change(x, n=5), s, corrupt_after=100)

    def test_sma_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _sma(x, window=20), s, corrupt_after=100)

    def test_ema_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _ema(x, span=20), s, corrupt_after=100)

    def test_lag_no_lookahead(self):
        s = _make_series(300)
        # lag(n=5) shifts backwards — past outputs change if source values change,
        # but the SHIFTED outputs should only be affected starting at corrupt_after-5
        # We test with n=0 (identity) which is trivially no-lookahead
        _assert_no_lookahead(lambda x: _lag(x, n=1), s, corrupt_after=150)

    def test_sign_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(_sign, s, corrupt_after=100)

    def test_clip_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _clip(x, lo=-1.0, hi=1.0), s, corrupt_after=100)

    def test_rolling_vol_no_lookahead(self):
        s = _make_series(300)
        _assert_no_lookahead(lambda x: _rolling_vol(x, window=21), s, corrupt_after=100)

    def test_drawdown_no_lookahead(self):
        # Price series (must be positive)
        s = _make_series(300) + 100
        _assert_no_lookahead(lambda x: _drawdown(x, window=63), s, corrupt_after=100)

    def test_rolling_corr_no_lookahead(self):
        """Corrupting future values of leg-1 must not change past rolling_corr outputs.

        rolling_corr uses right-aligned rolling().corr() so it is causal, but the
        strongest guarantee (no-lookahead) must be empirically confirmed.
        """
        s1 = _make_series(300, seed=1)
        s2 = _make_series(300, seed=2)
        corrupt_after = 100
        window = 30

        out_before = _rolling_corr(s1.copy(), s2.copy(), window=window)

        # Corrupt future of leg-1 only; leg-2 unchanged
        s1_corrupt = s1.copy()
        rng = np.random.default_rng(999)
        s1_corrupt.iloc[corrupt_after:] = rng.standard_normal(len(s1) - corrupt_after) * 1000

        out_after = _rolling_corr(s1_corrupt, s2.copy(), window=window)

        past_before = out_before.iloc[:corrupt_after]
        past_after = out_after.iloc[:corrupt_after]

        np.testing.assert_array_equal(
            np.isnan(past_before.to_numpy(float)),
            np.isnan(past_after.to_numpy(float)),
            err_msg="NaN pattern changed for past rolling_corr values after future corruption",
        )
        valid_mask = ~np.isnan(past_before.to_numpy(float))
        np.testing.assert_allclose(
            past_before.to_numpy(float)[valid_mask],
            past_after.to_numpy(float)[valid_mask],
            rtol=1e-10,
            err_msg="Past rolling_corr outputs changed after corrupting future values of leg-1",
        )


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------

class TestNaNHandling:
    """Transforms must propagate NaN sensibly (not raise exceptions)."""

    def test_zscore_nan_safe(self):
        s = _make_series(100)
        s.iloc[10:20] = np.nan
        result = _zscore(s, window=30)
        # Should not raise, and should have NaN where data is missing
        assert result.notna().sum() > 0

    def test_diff_nan_output_at_start(self):
        s = _make_series(50)
        result = _diff(s, n=3)
        # First 3 values must be NaN
        assert pd.isna(result.iloc[:3]).all()

    def test_rolling_vol_nan_at_start(self):
        s = _make_series(100)
        result = _rolling_vol(s, window=21)
        # First few values NaN (min_periods = window // 4)
        assert pd.isna(result.iloc[0])

    def test_lag_nan_at_start(self):
        s = _make_series(50)
        result = _lag(s, n=5)
        assert pd.isna(result.iloc[:5]).all()

    def test_lag_negative_raises(self):
        s = _make_series(50)
        with pytest.raises(ValueError, match="must be >= 0"):
            _lag(s, n=-1)

    def test_ratio_zero_denom_nan(self):
        s1 = _make_series(50)
        s2 = pd.Series([0.0] * 50)
        result = _ratio(s1, s2)
        assert result.isna().all()

    def test_pctile_rank_range(self):
        s = _make_series(200)
        result = _pctile_rank(s, window=50)
        valid = result.dropna()
        assert (valid >= 0.0).all() and (valid <= 1.0).all()


# ---------------------------------------------------------------------------
# Window sanity
# ---------------------------------------------------------------------------

class TestWindowSanity:
    """Larger windows produce more initial NaNs."""

    def test_zscore_window_larger_more_nans(self):
        s = _make_series(200)
        r50 = _zscore(s, window=50)
        r100 = _zscore(s, window=100)
        assert r100.isna().sum() >= r50.isna().sum()

    def test_sma_window_larger_more_nans(self):
        s = _make_series(200)
        r10 = _sma(s, window=10)
        r50 = _sma(s, window=50)
        assert r50.isna().sum() >= r10.isna().sum()

    def test_rolling_corr_produces_values(self):
        s1 = _make_series(200, seed=1)
        s2 = _make_series(200, seed=2)
        result = _rolling_corr(s1, s2, window=30)
        assert result.dropna().__len__() > 50

    def test_drawdown_non_positive(self):
        s = _make_series(200) + 100  # all positive
        result = _drawdown(s, window=63)
        valid = result.dropna()
        assert (valid <= 0.0).all()


# ---------------------------------------------------------------------------
# apply_pipeline tests
# ---------------------------------------------------------------------------

class TestApplyPipeline:
    """Test the pipeline executor."""

    def test_single_step_zscore(self):
        s = _make_series(200)
        result = apply_pipeline(s, [["zscore", {"window": 63}]])
        expected = _zscore(s, window=63)
        pd.testing.assert_series_equal(result, expected)

    def test_chained_steps(self):
        s = _make_series(200)
        result = apply_pipeline(s, [
            ["zscore", {"window": 63}],
            ["clip", {"lo": -2.0, "hi": 2.0}],
        ])
        # Should be a clipped zscore
        assert result.dropna().abs().max() <= 2.0 + 1e-10

    def test_binary_spread(self):
        s1 = _make_series(200, seed=1)
        s2 = _make_series(200, seed=2)
        result = apply_pipeline((s1, s2), [["spread", {}]])
        expected = _spread(s1, s2)
        pd.testing.assert_series_equal(result, expected)

    def test_binary_ratio(self):
        s1 = _make_series(200, seed=1) + 10
        s2 = _make_series(200, seed=2) + 10
        result = apply_pipeline((s1, s2), [["ratio", {}]])
        assert isinstance(result, pd.Series)
        assert result.dropna().__len__() > 100

    def test_empty_pipeline_returns_input(self):
        s = _make_series(100)
        result = apply_pipeline(s, [])
        # Empty pipeline returns the input as-is (as Series)
        assert isinstance(result, pd.Series)
        assert len(result) == len(s)

    def test_unknown_transform_raises(self):
        s = _make_series(100)
        with pytest.raises(ValueError, match="Unknown transform"):
            apply_pipeline(s, [["nonexistent_transform", {}]])

    def test_transforms_registry_coverage(self):
        """Every name in TRANSFORMS can be dispatched."""
        s = _make_series(100)
        s2 = _make_series(100, seed=2)
        for name, (fn, arity, defaults) in TRANSFORMS.items():
            if arity == 1:
                result = apply_pipeline(s, [[name, {}]])
            else:
                result = apply_pipeline((s, s2), [[name, {}]])
            assert isinstance(result, pd.Series), f"Transform {name!r} did not return Series"
