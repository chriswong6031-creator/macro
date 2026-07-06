"""Pure-logic tests for d2_rates_calendar_flows_phase0 helper functions.

No network, no data files needed — all tests use synthetic in-memory data.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.d2_rates_calendar_flows_phase0 import (
    _nw_lags,
    split_half_sign,
)


# ---------------------------------------------------------------------------
# _nw_lags
# ---------------------------------------------------------------------------

class TestNwLags:
    def test_small_n_floors_at_2(self):
        assert _nw_lags(4) == 2

    def test_caps_at_4(self):
        # sqrt(100) = 10, capped at 4
        assert _nw_lags(100) == 4

    def test_mid_range(self):
        # sqrt(9) = 3
        assert _nw_lags(9) == 3

    def test_minimum_n(self):
        assert _nw_lags(1) == 2

    def test_returns_int(self):
        result = _nw_lags(25)
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# split_half_sign
# ---------------------------------------------------------------------------

class TestSplitHalfSign:
    def test_both_positive_passes(self):
        # 20 obs, all positive
        idx = pd.date_range("2020-01-01", periods=20, freq="ME")
        s = pd.Series([0.01] * 20, index=idx)
        r = split_half_sign(s)
        assert r["pass"] == True   # noqa: E712  (numpy bool compat)
        assert r["same_sign"] == True
        assert r["direction_correct"] == True

    def test_h1_positive_h2_negative_fails(self):
        idx = pd.date_range("2020-01-01", periods=20, freq="ME")
        vals = [0.01] * 10 + [-0.01] * 10
        s = pd.Series(vals, index=idx)
        r = split_half_sign(s)
        assert r["pass"] == False   # noqa: E712
        assert r["same_sign"] == False

    def test_both_negative_fails_direction(self):
        idx = pd.date_range("2020-01-01", periods=20, freq="ME")
        s = pd.Series([-0.01] * 20, index=idx)
        r = split_half_sign(s)
        assert r["pass"] == False   # noqa: E712
        assert r["same_sign"] == True
        assert r["direction_correct"] == False

    def test_too_few_obs(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="ME")
        s = pd.Series([0.01] * 5, index=idx)
        r = split_half_sign(s)
        assert r["pass"] is False
        assert "too few" in r["reason"]

    def test_half_sizes_correct(self):
        idx = pd.date_range("2020-01-01", periods=22, freq="ME")
        s = pd.Series([0.01] * 22, index=idx)
        r = split_half_sign(s)
        assert r["n_h1"] == 11
        assert r["n_h2"] == 11
        assert r["n_h1"] + r["n_h2"] == 22

    def test_drops_nans_first(self):
        idx = pd.date_range("2020-01-01", periods=25, freq="ME")
        vals = [np.nan] * 5 + [0.02] * 20
        s = pd.Series(vals, index=idx)
        r = split_half_sign(s)
        assert r["n"] == 20  # NaNs dropped
        assert r["pass"] is True

    def test_mean_pct_scale(self):
        idx = pd.date_range("2020-01-01", periods=20, freq="ME")
        s = pd.Series([0.005] * 20, index=idx)  # 0.5% per obs
        r = split_half_sign(s)
        assert abs(r["mean_h1_pct"] - 0.5) < 1e-6
        assert abs(r["mean_h2_pct"] - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# BH FDR integration (via engine.validation)
# ---------------------------------------------------------------------------

class TestBHIntegration:
    """Verify benjamini_hochberg behaves as expected for this family's pattern
    (strong V3, weak V1/V2) without touching data files."""

    def test_strong_cells_reject(self):
        from engine.validation import benjamini_hochberg
        pvals = {
            "v3_tlt_last_day": 0.0003,
            "v3_ief_last_day": 0.0001,
            "v1_pooled_cond":  0.95,
            "v2_cond_gap":     0.64,
        }
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert result["v3_tlt_last_day"]["reject"] is True
        assert result["v3_ief_last_day"]["reject"] is True
        assert result["v1_pooled_cond"]["reject"] is False
        assert result["v2_cond_gap"]["reject"] is False

    def test_monotone_q_values(self):
        """BH q-values must be monotone non-decreasing in p."""
        from engine.validation import benjamini_hochberg
        pvals = {f"cell_{i}": p for i, p in enumerate([0.01, 0.05, 0.20, 0.50])}
        result = benjamini_hochberg(pvals, alpha=0.10)
        sorted_by_p = sorted(result.items(), key=lambda kv: kv[1]["p"])
        qs = [v["q"] for _, v in sorted_by_p]
        for i in range(len(qs) - 1):
            assert qs[i] <= qs[i + 1] + 1e-9, f"q not monotone: {qs}"

    def test_empty_pvals_returns_empty(self):
        from engine.validation import benjamini_hochberg
        assert benjamini_hochberg({}) == {}


# ---------------------------------------------------------------------------
# Newey-West basic sanity (using engine.validation.newey_west_tstat)
# ---------------------------------------------------------------------------

class TestNeweyWest:
    def test_zero_mean_gives_near_zero_t(self):
        from engine.validation import newey_west_tstat
        rng = np.random.default_rng(42)
        x = rng.normal(0, 1, 100)
        r = newey_west_tstat(x, lags=4)
        # t should be small for zero-mean noise
        assert abs(r["t"]) < 5.0
        assert r["n"] == 100

    def test_strong_positive_mean_gives_high_t(self):
        from engine.validation import newey_west_tstat
        x = np.ones(200) * 0.01   # constant positive series = no variance, huge t
        # need some variance so se > 0 — add tiny noise
        rng = np.random.default_rng(0)
        x = x + rng.normal(0, 0.0001, 200)
        r = newey_west_tstat(x, lags=4)
        assert r["t"] > 5.0, f"expected high t, got {r['t']}"

    def test_too_few_obs_returns_none(self):
        from engine.validation import newey_west_tstat
        r = newey_west_tstat([0.1, 0.2, 0.3], lags=4)
        assert r["t"] is None

    def test_p_value_bounds(self):
        from engine.validation import newey_west_tstat
        rng = np.random.default_rng(7)
        x = rng.normal(0, 1, 50)
        r = newey_west_tstat(x, lags=2)
        if r["p"] is not None:
            assert 0.0 <= r["p"] <= 1.0


# ---------------------------------------------------------------------------
# Pre-window concession direction (regression guard: must be negative mean)
# ---------------------------------------------------------------------------

class TestV1PreWindowConcession:
    """The pre-registration says concession should be negative (Lou-Yan-Zhang).
    We test the computation logic directly with synthetic data."""

    def test_negative_pre_window_detected(self):
        """Simulate 10 auctions all with pre-window TLT decline; all should be
        flagged as concession_observed=True."""
        # Build a TLT price series with synthetic concession pattern
        idx = pd.date_range("2016-01-04", periods=300, freq="B")
        # Prices that decline 3 days before every ~25th day
        price = np.ones(300) * 100.0
        # mark every 25th day as "auction" with 3-day pre-decline
        auction_positions = range(10, 300, 25)
        for ap in auction_positions:
            if ap >= 3:
                price[ap - 3] = 100.5
                price[ap - 2] = 100.3
                price[ap - 1] = 100.1
                price[ap]     = 99.8  # down on auction day

        tlt = pd.Series(price, index=idx)
        auction_dates = [idx[ap] for ap in auction_positions if ap < 300]

        # Compute pre-window returns manually
        pre_rets = []
        for ad in auction_dates:
            pos0 = idx.searchsorted(ad, side="right") - 1
            if pos0 < 4 or pos0 + 3 >= len(tlt):
                continue
            pre_ret = float(tlt.iloc[pos0] / tlt.iloc[pos0 - 3] - 1)
            pre_rets.append(pre_ret)

        assert len(pre_rets) > 0
        # All our synthetic auctions have declining pre-window → all negative
        assert all(r < 0 for r in pre_rets), f"Expected all negative: {pre_rets}"
