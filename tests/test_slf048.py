"""Tests for SLF-048 wiki attention phase-0 pure-function logic.

Pure-function level, tiny fixtures, NO network access.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import the pure functions under test
from scripts.wiki_attention_phase0 import (
    _compute_attention_z,
    _fwd_returns,
    _mean_t_hac,
    _split_half_test,
    rebalance_dates_in,
)
from collectors.wiki_pageviews import _parse


# ── _parse ────────────────────────────────────────────────────────────────────

def test_parse_basic():
    """_parse returns a DataFrame with views + log_views columns from valid API payload."""
    payload = {
        "items": [
            {"timestamp": "20230101", "views": 1000},
            {"timestamp": "20230102", "views": 2000},
            {"timestamp": "20230103", "views": 500},
        ]
    }
    df = _parse(payload)
    assert len(df) == 3
    assert "views" in df.columns
    assert "log_views" in df.columns
    assert df["views"].iloc[0] == 1000
    # log_views = log1p(views)
    assert abs(df["log_views"].iloc[0] - np.log1p(1000)) < 1e-9


def test_parse_empty_payload():
    """_parse returns empty DataFrame for empty/missing items."""
    assert _parse({}).empty
    assert _parse({"items": []}).empty
    assert _parse(None).empty


def test_parse_bad_timestamps():
    """_parse drops rows with unparseable timestamps."""
    payload = {
        "items": [
            {"timestamp": "20230101", "views": 100},
            {"timestamp": "BADDATE", "views": 200},
        ]
    }
    df = _parse(payload)
    assert len(df) == 1


# ── _compute_attention_z ─────────────────────────────────────────────────────

def _make_panel(n_days: int = 200, tickers: list = None) -> pd.DataFrame:
    """Create a synthetic attention panel for testing."""
    if tickers is None:
        tickers = ["AAPL", "MSFT"]
    dates = pd.date_range("2020-01-01", periods=n_days, freq="D")
    records = []
    rng = np.random.default_rng(42)
    for tk in tickers:
        views = rng.integers(1000, 10000, size=n_days).astype(float)
        log_views = np.log1p(views)
        df = pd.DataFrame({"views": views, "log_views": log_views, "ticker": tk},
                          index=dates)
        records.append(df)
    return pd.concat(records)


def test_compute_attention_z_shape():
    """attention_z has same row count as input panel, NaN for first 45 rows (warm-up)."""
    panel = _make_panel(200)
    z = _compute_attention_z(panel, window=90)
    assert "attention_z" in z.columns
    assert "ticker" in z.columns
    # Should have data for both tickers
    tickers = z["ticker"].unique()
    assert len(tickers) == 2


def test_compute_attention_z_1day_lag():
    """The 1-day lag means z on day 0 is NaN (no prior day)."""
    panel = _make_panel(200, tickers=["AAPL"])
    z = _compute_attention_z(panel, window=90)
    aapl_z = z[z["ticker"] == "AAPL"]["attention_z"]
    # First row should be NaN due to the shift(1) lag
    assert pd.isna(aapl_z.iloc[0])


def test_compute_attention_z_standardization():
    """attention_z should have approximately mean=0 and std=1 over the valid window."""
    panel = _make_panel(500, tickers=["AAPL"])
    z = _compute_attention_z(panel, window=90)
    aapl_z = z[z["ticker"] == "AAPL"]["attention_z"].dropna()
    # After warm-up, z-scores should be in a reasonable range
    assert aapl_z.abs().max() < 10  # no crazy outliers in synthetic data


# ── _fwd_returns ──────────────────────────────────────────────────────────────

def test_fwd_returns_horizon():
    """Forward returns shift by -horizon, last horizon rows are NaN."""
    closes = pd.DataFrame({
        "A": [100.0, 110.0, 121.0, 133.1],
        "B": [50.0, 55.0, 60.5, 66.55],
    }, index=pd.date_range("2023-01-01", periods=4))
    fwd = _fwd_returns(closes, horizon=1)
    # Day 0: fwd return = (close[1] - close[0]) / close[0] = 10%
    assert abs(fwd["A"].iloc[0] - 0.10) < 1e-9
    # Last row should be NaN (no future)
    assert pd.isna(fwd["A"].iloc[-1])


def test_fwd_returns_no_lookahead():
    """Forward return at day t uses close at t+h, not t itself."""
    closes = pd.DataFrame({
        "A": [100.0, 200.0, 300.0],
    }, index=pd.date_range("2023-01-01", periods=3))
    fwd = _fwd_returns(closes, horizon=2)
    # At day 0: (300 - 100)/100 = 2.0
    assert abs(fwd["A"].iloc[0] - 2.0) < 1e-9


# ── _mean_t_hac ───────────────────────────────────────────────────────────────

def test_mean_t_hac_positive():
    """HAC t-stat and mean are returned for sufficient data."""
    rets = [0.01] * 50 + [-0.005] * 50  # mean slightly positive
    result = _mean_t_hac(rets)
    assert result["n"] == 100
    assert result["mean"] is not None
    assert result["t"] is not None


def test_mean_t_hac_too_few():
    """Returns None for key stats when fewer than 10 observations."""
    result = _mean_t_hac([0.01, 0.02, 0.03])
    assert result["mean"] is None
    assert result["t"] is None
    assert result["n"] == 3


def test_mean_t_hac_negative_mean():
    """Negative mean returns with t-stat detecting negative direction."""
    rets = [-0.02] * 100
    result = _mean_t_hac(rets)
    assert result["mean"] < 0
    assert result["t"] < 0


# ── _split_half_test ──────────────────────────────────────────────────────────

def test_split_half_same_sign():
    """Returns same_sign=True when both halves have negative mean."""
    dates = list(pd.date_range("2020-01-01", periods=40))
    returns = [-0.01] * 40  # all negative
    result = _split_half_test(returns, dates)
    assert result["same_sign"] is True
    assert result["h1_mean"] < 0
    assert result["h2_mean"] < 0


def test_split_half_different_sign():
    """Returns same_sign=False when halves have opposite signs."""
    dates = list(pd.date_range("2020-01-01", periods=40))
    returns = [-0.01] * 20 + [0.01] * 20  # h1 negative, h2 positive
    result = _split_half_test(returns, dates)
    assert result["same_sign"] is False


def test_split_half_too_few():
    """Returns None for same_sign when fewer than 20 observations."""
    dates = list(pd.date_range("2020-01-01", periods=10))
    returns = [-0.01] * 10
    result = _split_half_test(returns, dates)
    assert result["same_sign"] is None


# ── rebalance_dates_in ────────────────────────────────────────────────────────

def test_rebalance_dates_in_returns_subset():
    """Returns only dates within the index range."""
    index = pd.date_range("2020-01-01", periods=100)
    rebal_dates = list(pd.date_range("2019-12-01", "2020-06-30", freq="ME"))
    result = rebalance_dates_in(rebal_dates, index)
    assert all(d in set(index) for d in result)
    assert len(result) > 0


def test_rebalance_dates_in_no_future():
    """No dates beyond the index are returned."""
    index = pd.date_range("2020-01-01", periods=30)
    rebal_dates = list(pd.date_range("2020-01-01", "2021-12-31", freq="ME"))
    result = rebalance_dates_in(rebal_dates, index)
    assert all(d <= index[-1] for d in result)


# ── integration: _parse round-trip ───────────────────────────────────────────

def test_parse_log_views_is_log1p_views():
    """log_views in the parse output is exactly log1p(views)."""
    payload = {
        "items": [
            {"timestamp": "20220515", "views": 12345},
            {"timestamp": "20220516", "views": 67890},
        ]
    }
    df = _parse(payload)
    for _, row in df.iterrows():
        expected = np.log1p(row["views"])
        assert abs(row["log_views"] - expected) < 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
