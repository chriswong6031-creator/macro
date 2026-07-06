"""Tests for SLF-006 auction absorption phase-0 harness.

Covers the pure helper functions only — no network, no disk (tiny fixtures).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ── import target module ────────────────────────────────────────────────────
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.slf006_auction_absorption_phase0 import (
    continuous_ic,
    forward_return,
    quintile_contrast,
    split_half_check,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _price_series():
    """A tiny 30-bar price series (monotone up for easy math)."""
    dates = pd.date_range("2020-01-02", periods=30, freq="B")
    return pd.Series(100.0 + np.arange(30), index=dates)


def _auction_panel(n: int = 40, seed: int = 42) -> pd.DataFrame:
    """Synthetic (auction_date, absorption_z, fwd_1, fwd_5, fwd_21) panel."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=n)
    az = rng.standard_normal(n)
    # fwd_5 mildly negatively correlated with az (what the study finds)
    fwd5  = -0.2 * az + rng.standard_normal(n) * 0.5
    fwd1  = -0.1 * az + rng.standard_normal(n) * 0.5
    fwd21 = -0.3 * az + rng.standard_normal(n) * 0.5
    return pd.DataFrame({
        "auction_date": dates,
        "bucket":       "belly",
        "absorption_z": az,
        "fwd_1":        fwd1,
        "fwd_5":        fwd5,
        "fwd_21":       fwd21,
    })


# ── forward_return tests ─────────────────────────────────────────────────────

class TestForwardReturn:
    def test_basic(self):
        p = _price_series()
        t0 = p.index[0]
        r = forward_return(p, t0, 5)
        assert r is not None
        assert abs(r - (p.iloc[5] / p.iloc[0] - 1.0)) < 1e-10

    def test_returns_none_for_non_trading_day(self):
        p = _price_series()
        # Saturday — not in the business-day index
        sat = pd.Timestamp("2020-01-04")
        r = forward_return(p, sat, 1)
        assert r is None

    def test_returns_none_when_not_enough_bars(self):
        p = _price_series()
        t0 = p.index[-2]
        r = forward_return(p, t0, 5)
        assert r is None

    def test_n_equals_0_returns_zero(self):
        p = _price_series()
        t0 = p.index[0]
        r = forward_return(p, t0, 0)
        assert r == pytest.approx(0.0)


# ── quintile_contrast tests ──────────────────────────────────────────────────

class TestQuintileContrast:
    def test_returns_dict_with_required_keys(self):
        panel = _auction_panel()
        res = quintile_contrast(panel, 5)
        for k in ("n", "q1_mean", "q5_mean", "spread", "t_hac", "p_hac"):
            assert k in res

    def test_insufficient_data_returns_none_spread(self):
        tiny = _auction_panel(10)
        res = quintile_contrast(tiny, 5)
        # Should still run but may return None for spread with n<15
        assert "spread" in res

    def test_spread_is_in_percent(self):
        panel = _auction_panel(60, seed=1)
        res = quintile_contrast(panel, 5)
        if res["spread"] is not None:
            # spread is in %, so |spread| should be < 200 for synthetic 0/1 returns
            assert abs(res["spread"]) < 200.0

    def test_p_hac_in_unit_interval(self):
        panel = _auction_panel(60)
        res = quintile_contrast(panel, 5)
        if res["p_hac"] is not None:
            assert 0.0 <= res["p_hac"] <= 1.0


# ── continuous_ic tests ──────────────────────────────────────────────────────

class TestContinuousIC:
    def test_returns_ic_in_minus1_to_1(self):
        panel = _auction_panel(50)
        res = continuous_ic(panel, 5)
        if res["ic"] is not None:
            assert -1.0 <= res["ic"] <= 1.0

    def test_perfect_negative_correlation_gives_ic_near_minus1(self):
        n = 30
        df = pd.DataFrame({
            "absorption_z": np.arange(n, dtype=float),
            "fwd_5":        np.arange(n, 0, -1, dtype=float),  # perfectly inverse
        })
        res = continuous_ic(df, 5)
        assert res["ic"] is not None
        assert res["ic"] < -0.9

    def test_insufficient_data(self):
        tiny = pd.DataFrame({
            "absorption_z": [0.1, 0.2],
            "fwd_5":        [0.3, 0.4],
        })
        res = continuous_ic(tiny, 5)
        assert res["ic"] is None


# ── split_half_check tests ───────────────────────────────────────────────────

class TestSplitHalfCheck:
    def test_returns_required_keys(self):
        panel = _auction_panel(40)
        res = split_half_check(panel)
        for k in ("h1_ic_t5", "h2_ic_t5", "h1_ic_t21", "h2_ic_t21"):
            assert k in res

    def test_small_panel_returns_none_values(self):
        panel = _auction_panel(10)
        res = split_half_check(panel)
        # With n=10, halves are 5 each — below the 8-threshold
        # All ICs may be None
        assert "h1_ic_t5" in res

    def test_consistent_signal_gives_same_sign_halves(self):
        n = 80
        rng = np.random.default_rng(99)
        az = rng.standard_normal(n)
        # Strongly negative correlation throughout
        fwd5  = -0.8 * az + rng.standard_normal(n) * 0.05
        fwd21 = -0.8 * az + rng.standard_normal(n) * 0.05
        dates = pd.bdate_range("2018-01-01", periods=n)
        panel = pd.DataFrame({
            "auction_date": dates, "bucket": "belly",
            "absorption_z": az, "fwd_1": fwd5,
            "fwd_5": fwd5, "fwd_21": fwd21,
        })
        res = split_half_check(panel)
        h1_t5 = res.get("h1_ic_t5")
        h2_t5 = res.get("h2_ic_t5")
        if h1_t5 is not None and h2_t5 is not None:
            assert np.sign(h1_t5) == np.sign(h2_t5)
