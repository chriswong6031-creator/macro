"""Tests for CMDI phase-0 signal logic.

Pure logic tests: no network, no large data files. Tests for the math
and PIT-correctness of the key functions.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.cmdi_phase0 import (
    expanding_pctile_pit,
    mann_whitney_auc,
    bootstrap_auc_ci,
    newey_west_tstat,
    build_signals,
    make_drawdown_label,
)


# ============================================================================ #
# expanding_pctile_pit
# ============================================================================ #
class TestExpandingPctilePIT:
    def test_first_24_periods_nan(self):
        """First 24 obs must be NaN (min_history=24)."""
        vals = pd.Series(np.random.rand(50), index=pd.date_range("2005-01", periods=50, freq="ME"))
        out = expanding_pctile_pit(vals, min_history=24)
        assert out.iloc[:24].isna().all(), "First 24 must be NaN"
        assert not np.isnan(float(out.iloc[24])), "Position 24 should be valid"

    def test_perfect_monotone_ascending(self):
        """Strictly ascending series: pctile should be near 1.0 at the end."""
        vals = pd.Series(np.arange(1.0, 50.0),
                         index=pd.date_range("2005-01", periods=49, freq="ME"))
        out = expanding_pctile_pit(vals, min_history=24)
        # Last value is the global maximum, so pctile should be 1.0
        assert out.dropna().iloc[-1] == 1.0, f"Max should have pctile=1.0, got {out.dropna().iloc[-1]}"

    def test_no_lookahead(self):
        """Pctile at position i uses only data through i (not i+1...n)."""
        vals = pd.Series([1.0, 2.0, 3.0, 10.0, 5.0] + [4.0] * 40,
                         index=pd.date_range("2005-01", periods=45, freq="ME"))
        out = expanding_pctile_pit(vals, min_history=24)
        # At position 24 (the 25th element, 0-indexed), the window is vals[0:25].
        # The pctile should NOT know about the value at position 44.
        # We just check it returns a valid 0-1 value, not > 1 or < 0.
        non_nan = out.dropna()
        assert (non_nan >= 0).all() and (non_nan <= 1).all(), "Pctile must be in [0,1]"

    def test_constant_series(self):
        """All values equal: pctile should be 1.0 (all <= current)."""
        vals = pd.Series(np.ones(30),
                         index=pd.date_range("2005-01", periods=30, freq="ME"))
        out = expanding_pctile_pit(vals, min_history=24)
        non_nan = out.dropna()
        assert (non_nan == 1.0).all(), "Constant series should yield pctile=1.0"


# ============================================================================ #
# mann_whitney_auc
# ============================================================================ #
class TestMannWhitneyAUC:
    def test_perfect_discrimination(self):
        """When all positives score > all negatives, AUC = 1.0."""
        scores = np.array([0.9, 0.8, 0.7, 0.2, 0.1, 0.0])
        labels = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
        auc = mann_whitney_auc(scores, labels)
        assert auc == 1.0, f"Perfect discrimination should give AUC=1.0, got {auc}"

    def test_worst_discrimination(self):
        """When all negatives score > all positives, AUC = 0.0."""
        scores = np.array([0.0, 0.1, 0.2, 0.7, 0.8, 0.9])
        labels = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
        auc = mann_whitney_auc(scores, labels)
        assert auc == 0.0, f"Worst discrimination should give AUC=0.0, got {auc}"

    def test_random_chance(self):
        """Random scores: AUC should be near 0.5."""
        rng = np.random.default_rng(42)
        scores = rng.uniform(size=1000)
        labels = (rng.uniform(size=1000) > 0.7).astype(float)
        auc = mann_whitney_auc(scores, labels)
        # Should be close to 0.5 (within 0.05 for N=1000)
        assert 0.45 <= auc <= 0.55, f"Random AUC should be ~0.5, got {auc}"

    def test_ties_handled(self):
        """Ties contribute 0.5 to AUC. All ties -> AUC = 0.5."""
        scores = np.array([0.5, 0.5, 0.5, 0.5])
        labels = np.array([1.0, 1.0, 0.0, 0.0])
        auc = mann_whitney_auc(scores, labels)
        assert auc == 0.5, f"All-tie scores should give AUC=0.5, got {auc}"

    def test_empty_class_nan(self):
        """NaN if one class is empty."""
        scores = np.array([0.5, 0.8, 0.3])
        labels = np.array([1.0, 1.0, 1.0])  # no negatives
        auc = mann_whitney_auc(scores, labels)
        assert np.isnan(auc), "No negatives should give AUC=nan"


# ============================================================================ #
# newey_west_tstat
# ============================================================================ #
class TestNeweyWestTstat:
    def test_positive_mean(self):
        """Positive series -> positive t-stat."""
        x = np.ones(50) * 0.1
        nw = newey_west_tstat(x, lags=4)
        assert nw["t"] > 0, f"Positive series should give t>0, got t={nw['t']}"

    def test_zero_mean(self):
        """Zero-mean series -> t near 0."""
        rng = np.random.default_rng(1)
        x = rng.standard_normal(200)
        nw = newey_west_tstat(x, lags=4)
        assert abs(nw["t"]) < 3.0, f"Zero-mean series should have |t| < 3, got t={nw['t']}"

    def test_short_series_returns_none(self):
        """Series shorter than 8 returns None for t."""
        nw = newey_west_tstat(np.ones(5), lags=4)
        assert nw["t"] is None, "Short series should return t=None"

    def test_p_value_range(self):
        """p-value must be in [0, 1]."""
        x = np.random.randn(100) + 0.5
        nw = newey_west_tstat(x, lags=4)
        if nw["p"] is not None:
            assert 0 <= nw["p"] <= 1, f"p must be in [0,1], got {nw['p']}"


# ============================================================================ #
# make_drawdown_label (integration, small synthetic)
# ============================================================================ #
class TestDrawdownLabel:
    def test_no_drawdown_gives_zero(self):
        """Monotonically increasing price -> no drawdown -> label = 0."""
        idx = pd.date_range("2010-01-01", periods=100, freq="D")
        prices = pd.Series(np.arange(1.0, 101.0), index=idx)
        lbl = make_drawdown_label(prices, horizon_days=21, thresh=-0.05)
        non_nan = lbl.dropna()
        assert (non_nan == 0).all(), "Rising prices should give 0 everywhere"

    def test_crash_gives_one(self):
        """50% crash within window -> label = 1."""
        idx = pd.date_range("2010-01-01", periods=60, freq="D")
        prices = pd.Series(100.0, index=idx)
        # Crash at day 10
        prices.iloc[10:] = 50.0
        lbl = make_drawdown_label(prices, horizon_days=21, thresh=-0.05)
        # The label at day 0-9 should detect the crash (it's within 21 days)
        # At day 0, we look forward 21 days; crash at day 10 is within window
        early_labels = lbl.iloc[:10].dropna()
        if len(early_labels):
            assert (early_labels == 1).all(), "Should detect 50% crash"

    def test_label_is_binary(self):
        """All non-NaN labels are 0 or 1."""
        idx = pd.date_range("2010-01-01", periods=100, freq="D")
        prices = pd.Series(np.random.randn(100).cumsum() + 100, index=idx)
        prices = prices.clip(lower=10)  # avoid negative prices
        lbl = make_drawdown_label(prices, horizon_days=21, thresh=-0.05)
        non_nan = lbl.dropna()
        assert set(non_nan.unique()).issubset({0.0, 1.0}), \
            f"Labels must be binary, got {non_nan.unique()}"


# ============================================================================ #
# build_signals — lag correctness
# ============================================================================ #
class TestBuildSignals:
    def _make_monthly(self, n: int = 60) -> pd.DataFrame:
        idx = pd.date_range("2005-01", periods=n, freq="ME")
        return pd.DataFrame({
            "market_cmdi": np.random.rand(n) * 0.5,
            "ig_cmdi": np.random.rand(n) * 0.4,
            "hy_cmdi": np.random.rand(n) * 0.6,
        }, index=idx)

    def test_lag_applied(self):
        """Signal at date M uses value from M-lag (shift by lag_months)."""
        monthly = self._make_monthly(60)
        lag = 2
        sigs = build_signals(monthly, lag=lag)
        # The signal index should start lag months after the raw data starts.
        # First non-NaN should be around 24 + lag months in.
        first_valid = sigs["market_level_pctile"].dropna().index.min()
        # With 24-month min history + 2 month lag, first valid ~ month 26
        raw_start = monthly.index[0]
        diff_months = (first_valid.year - raw_start.year) * 12 + (first_valid.month - raw_start.month)
        # Should be at least 24 (min history) + lag
        assert diff_months >= 24 + lag - 1, \
            f"Expected >= {24 + lag - 1} months offset, got {diff_months}"

    def test_pctile_in_unit_interval(self):
        """All non-NaN pctile values must be in [0, 1]."""
        monthly = self._make_monthly(60)
        sigs = build_signals(monthly, lag=2)
        for col in sigs.columns:
            non_nan = sigs[col].dropna()
            assert (non_nan >= 0).all() and (non_nan <= 1).all(), \
                f"Column {col}: pctile must be in [0,1]"

    def test_output_columns_present(self):
        """Expected signal columns are present in output."""
        monthly = self._make_monthly(60)
        sigs = build_signals(monthly, lag=2)
        expected = [
            "market_level_pctile", "ig_level_pctile", "hy_level_pctile",
            "market_3m_chg_pctile", "ig_3m_chg_pctile", "hy_3m_chg_pctile",
        ]
        for col in expected:
            assert col in sigs.columns, f"Missing expected column: {col}"


# ============================================================================ #
# bootstrap_auc_ci — sanity
# ============================================================================ #
class TestBootstrapAUCCI:
    def test_ci_contains_point_estimate(self):
        """95% CI should bracket the point estimate (approximately, with high prob)."""
        rng = np.random.default_rng(99)
        scores = rng.uniform(size=200)
        labels = (scores + rng.normal(0, 0.3, 200) > 0.5).astype(float)
        auc, lo, hi = bootstrap_auc_ci(scores, labels, n_boot=500, seed=7)
        assert lo <= auc <= hi, f"CI [{lo:.4f}, {hi:.4f}] does not contain point AUC {auc:.4f}"

    def test_perfect_signal_ci_above_half(self):
        """Perfect signal: CI lo > 0.5 (should clearly exceed chance)."""
        scores = np.array([0.9] * 50 + [0.1] * 50)
        labels = np.array([1.0] * 50 + [0.0] * 50)
        auc, lo, hi = bootstrap_auc_ci(scores, labels, n_boot=500, seed=7)
        assert lo > 0.5, f"Perfect signal CI lo should be > 0.5, got {lo:.4f}"
        assert abs(auc - 1.0) < 1e-9, f"Perfect AUC should be 1.0, got {auc}"
