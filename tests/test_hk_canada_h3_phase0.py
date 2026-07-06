"""
Minimal pytest for hk_canada_h3_phase0.py pure-function logic.
No network, no large data loads — tiny synthetic fixtures only.
"""

import numpy as np
import pandas as pd
import pytest

# ── Import the logic under test ────────────────────────────────────────────
from scripts.hk_canada_h3_phase0 import (
    build_d1y,
    build_own_history_pctile,
    next_valid_print,
    split_half_sign,
    tercile_ls_excess,
    top5_rank_weighted_excess,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def tiny_premium():
    """A 3-pair premium panel spanning 600 trading days with deliberate patterns."""
    idx = pd.date_range("2010-01-04", periods=600, freq="B")
    rng = np.random.default_rng(42)
    data = {
        "A.HK": np.cumsum(rng.normal(0, 0.01, 600)) + 0.2,
        "B.HK": np.cumsum(rng.normal(0, 0.01, 600)) + 0.5,
        "C.HK": np.cumsum(rng.normal(0, 0.01, 600)) + 0.1,
    }
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def tiny_signal():
    """A tiny 5-element signal Series."""
    return pd.Series({"A": 0.9, "B": 0.1, "C": 0.5, "D": 0.8, "E": 0.2})


@pytest.fixture
def tiny_fwd():
    """Matching forward return series: high-signal names have higher returns."""
    return pd.Series({"A": 0.05, "B": -0.02, "C": 0.01, "D": 0.04, "E": -0.01})


# ── Tests: build_own_history_pctile ────────────────────────────────────────

def test_pctile_returns_float_in_01(tiny_premium):
    result = build_own_history_pctile(tiny_premium, window=252, min_obs=126)
    # All non-NaN values should be in [0, 1]
    vals = result.values.flatten()
    valid = vals[~np.isnan(vals)]
    assert len(valid) > 0, "Expected at least some valid pctile values"
    assert (valid >= 0).all(), "pctile should be >= 0"
    assert (valid <= 1).all(), "pctile should be <= 1"


def test_pctile_nan_before_min_obs(tiny_premium):
    """Rows before min_obs of history should be NaN."""
    result = build_own_history_pctile(tiny_premium, window=252, min_obs=126)
    # First 125 rows should be NaN for all pairs (window < min_obs)
    early = result.iloc[:125]
    assert early.isna().all().all(), "Expected NaN before min_obs window"


def test_pctile_no_lookahead(tiny_premium):
    """The pctile at row i should only use data through row i."""
    # Build pctile for a simple monotonically increasing series
    idx = pd.date_range("2010-01-04", periods=300, freq="B")
    df = pd.DataFrame({"A.HK": np.arange(300, dtype=float)}, index=idx)
    result = build_own_history_pctile(df, window=100, min_obs=50)
    # For a monotonically increasing series, pctile at any t should be 1.0
    # (current value is always the highest in trailing window)
    valid = result["A.HK"].dropna()
    assert (valid > 0.95).all(), "Monotone series should have pctile ~1.0 throughout"


# ── Tests: build_d1y ───────────────────────────────────────────────────────

def test_d1y_basic(tiny_premium):
    d1y = build_d1y(tiny_premium)
    assert d1y.shape == tiny_premium.shape
    # First 252 rows should be NaN (shift fills with NaN)
    assert d1y.iloc[:252].isna().all().all()
    # After 252 rows, should be non-NaN where premium is non-NaN
    assert d1y.iloc[252:].notna().any().any()


def test_d1y_direction():
    """Positive d1y = premium widened (H got cheaper)."""
    idx = pd.date_range("2010-01-04", periods=300, freq="B")
    # Monotonically increasing premium (A gets more expensive vs H over time)
    df = pd.DataFrame({"A.HK": np.arange(300, dtype=float) * 0.01}, index=idx)
    d1y = build_d1y(df)
    # d1y should be positive (premium increased = H got cheaper)
    valid = d1y["A.HK"].dropna()
    assert (valid > 0).all(), "Increasing premium → positive d1y"


# ── Tests: next_valid_print ────────────────────────────────────────────────

def test_next_valid_print_basic():
    idx = pd.date_range("2020-01-02", periods=10, freq="B")
    s = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], index=idx)
    val, date = next_valid_print(s, pd.Timestamp("2020-01-01"), max_lag=5)
    assert val == 1.0
    assert date == idx[0]


def test_next_valid_print_skips_nan():
    idx = pd.date_range("2020-01-02", periods=10, freq="B")
    s = pd.Series([np.nan, np.nan, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], index=idx)
    val, date = next_valid_print(s, pd.Timestamp("2020-01-01"), max_lag=5)
    assert val == 3.0  # first non-NaN within 5 lags
    assert date == idx[2]


def test_next_valid_print_returns_none_when_all_nan():
    idx = pd.date_range("2020-01-02", periods=3, freq="B")
    s = pd.Series([np.nan, np.nan, np.nan], index=idx)
    val, date = next_valid_print(s, pd.Timestamp("2020-01-01"), max_lag=3)
    assert val is None
    assert date is None


def test_next_valid_print_strictly_after():
    """Entry must be STRICTLY after the reference date."""
    idx = pd.date_range("2020-01-02", periods=5, freq="B")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx)
    # Reference date = idx[0] (2020-01-02), so next valid is idx[1]
    val, date = next_valid_print(s, idx[0], max_lag=5)
    assert date == idx[1]
    assert val == 2.0


# ── Tests: top5_rank_weighted_excess ──────────────────────────────────────

def test_top5_selects_highest_signal(tiny_signal, tiny_fwd):
    """Top-5 should select high-signal names (A=0.9, D=0.8, C=0.5, E=0.2, B=0.1)."""
    result = top5_rank_weighted_excess(tiny_signal, tiny_fwd, k=5)
    # All 5 names are included; result should be positive (high-signal names have higher returns)
    assert np.isfinite(result)
    assert result > 0


def test_top5_rank_weights_sum_to_1():
    """Internal weights must sum to 1 (returns is weighted mean)."""
    sig = pd.Series({"A": 1.0, "B": 0.0})
    fwd = pd.Series({"A": 0.10, "B": 0.00})
    result = top5_rank_weighted_excess(sig, fwd, k=2)
    # With 2 names, ranks are [2, 1], weights = [2/3, 1/3]
    # Expected = 2/3 * 0.10 + 1/3 * 0.00 = 0.0667
    assert abs(result - 2 / 3 * 0.10) < 1e-6


def test_top5_returns_nan_with_too_few_valid():
    """Should return NaN if fewer than 2 valid pairs."""
    sig = pd.Series({"A": 0.9, "B": np.nan})
    fwd = pd.Series({"A": 0.05, "B": 0.02})
    result = top5_rank_weighted_excess(sig, fwd, k=5)
    # Only 1 valid overlap (B has signal=NaN → excluded); < 2 → NaN
    assert np.isnan(result)


# ── Tests: tercile_ls_excess ───────────────────────────────────────────────

def test_tercile_ls_sign(tiny_signal, tiny_fwd):
    """L/S should be positive when high-signal names outperform."""
    result = tercile_ls_excess(tiny_signal, tiny_fwd)
    assert np.isfinite(result)
    assert result > 0  # top tercile (A, D) > bottom tercile (B, E)


def test_tercile_ls_nan_with_too_few():
    sig = pd.Series({"A": 0.9, "B": 0.1})
    fwd = pd.Series({"A": 0.05, "B": -0.01})
    result = tercile_ls_excess(sig, fwd)
    assert np.isnan(result)  # < 3 valid names


# ── Tests: split_half_sign ────────────────────────────────────────────────

def test_split_half_same_sign_stable():
    """If H1 and H2 have the same sign, split_half should report True."""
    n = 40
    series = np.full(n, 0.05)  # all positive
    dates = np.array(pd.date_range("2010-01-01", periods=n, freq="MS"), dtype="datetime64[D]")
    result = split_half_sign(series, dates)
    assert result["h1h2_same_sign"] is True
    assert result["h1_mean"] > 0
    assert result["h2_mean"] > 0


def test_split_half_date_split():
    """Pre/post split on 2015-01-01 should correctly partition."""
    n = 100
    dates = pd.date_range("2010-01-01", periods=n, freq="MS")
    # Pre-2015: positive; post-2015: also positive
    series = np.where(dates < pd.Timestamp("2015-01-01"), 0.05, 0.03)
    dates_arr = np.array(dates, dtype="datetime64[D]")
    result = split_half_sign(series, dates_arr, split_date="2015-01-01")
    assert result["presplit_same_sign"] is True
    assert result["pre_mean"] > result["post_mean"]


def test_split_half_insufficient_data():
    """With < 4 valid values, should return safe defaults."""
    series = np.array([0.1, 0.2, np.nan])
    dates = np.array(pd.date_range("2020-01-01", periods=3, freq="MS"), dtype="datetime64[D]")
    result = split_half_sign(series, dates)
    assert result["h1h2_same_sign"] is False
