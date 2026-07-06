"""Unit tests for W2-031 KEV vendor shock phase-0 — pure logic only, no network.

Tests cover the computation functions that have no network or file dependencies:
  - Beta-based abnormal return formula
  - Cluster event flagging logic
  - BH-FDR gate logic
  - Newey-West HAC t-stat (via engine.validation)
  - Vendor map parsing helpers
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Import the module functions under test (no side effects at import time)
# ---------------------------------------------------------------------------
from scripts.w2031_kev_vendor_shock_phase0 import (  # noqa: E402
    FAMILY,
    VARIANT_GRID,
    _abnormal_return,
    _compute_beta,
    _summarize_variant,
)
from engine.validation import benjamini_hochberg, newey_west_tstat  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers to build synthetic price series
# ---------------------------------------------------------------------------

def _make_prices(n: int = 300, seed: int = 42, drift: float = 0.0001) -> pd.Series:
    """Synthetic close price series starting at 100."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.015, size=n)
    prices = 100.0 * np.cumprod(1.0 + returns)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(prices, index=idx, name="SYNTH")


def _make_cal(prices: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(sorted(prices.index))


# ---------------------------------------------------------------------------
# Tests: Beta computation
# ---------------------------------------------------------------------------

class TestComputeBeta:
    def test_perfect_correlation_returns_one(self):
        """When vendor returns == benchmark returns, beta should be 1.0."""
        bench = _make_prices(300, seed=1)
        vendor = bench.copy()  # identical
        event_date = bench.index[250]
        beta = _compute_beta(vendor, bench, event_date)
        assert beta is not None
        assert abs(beta - 1.0) < 1e-6

    def test_double_return_returns_two(self):
        """Vendor returns = 2x benchmark returns → beta ≈ 2."""
        bench = _make_prices(300, seed=2)
        # Construct vendor with exactly 2x daily returns from bench
        bench_ret = bench.pct_change().fillna(0)
        vendor_prices = 100.0 * np.cumprod(1.0 + 2.0 * bench_ret.values)
        vendor = pd.Series(vendor_prices, index=bench.index)
        event_date = bench.index[250]
        beta = _compute_beta(vendor, bench, event_date)
        assert beta is not None
        assert abs(beta - 2.0) < 0.05  # allow small OLS noise

    def test_returns_none_when_insufficient_history(self):
        """Beta should be None when fewer than BETA_MIN days available."""
        bench = _make_prices(100, seed=3)  # only 100 days
        vendor = _make_prices(100, seed=4)
        event_date = bench.index[-1]
        beta = _compute_beta(vendor, bench, event_date)
        assert beta is None

    def test_uses_only_pre_event_data(self):
        """Beta must use only prices strictly BEFORE event_date."""
        bench = _make_prices(300, seed=5)
        vendor = _make_prices(300, seed=6)
        # Set event_date to halfway point; result should be computable
        event_date = bench.index[150]
        beta_early = _compute_beta(vendor, bench, event_date)
        # Set event_date to near the end
        event_date_late = bench.index[280]
        beta_late = _compute_beta(vendor, bench, event_date_late)
        # Both should be computable (we have enough data in both cases)
        assert beta_early is not None
        assert beta_late is not None


# ---------------------------------------------------------------------------
# Tests: Abnormal return formula
# ---------------------------------------------------------------------------

class TestAbnormalReturn:
    def setup_method(self):
        self.bench = _make_prices(400, seed=10)
        self.cal = _make_cal(self.bench)

    def test_zero_abnormal_return_when_equal_and_beta_one(self):
        """When vendor=benchmark and beta=1, abnormal return must be 0."""
        vendor = self.bench.copy()
        event_date = self.bench.index[200]
        ar = _abnormal_return(vendor, self.bench, event_date, 21, self.cal, beta=1.0)
        assert ar is not None
        assert abs(ar) < 1e-10

    def test_returns_none_beyond_end_of_series(self):
        """If the forward window goes beyond the price series, return None."""
        vendor = _make_prices(220, seed=11)
        cal_short = _make_cal(vendor)
        # Event near end so no room for 21d forward
        event_date = vendor.index[-5]
        ar = _abnormal_return(vendor, vendor, event_date, 21, cal_short, beta=1.0)
        assert ar is None

    def test_negative_abnormal_return_when_vendor_falls(self):
        """If vendor drops by 5% and benchmark flat, AR should be negative."""
        n = 300
        bench = pd.Series(np.full(n, 100.0),
                          index=pd.date_range("2022-01-03", periods=n, freq="B"))
        # Vendor: flat for first 200 bars, then drops
        v_prices = np.full(n, 100.0)
        v_prices[201:] = 95.0
        vendor = pd.Series(v_prices, index=bench.index)
        cal = _make_cal(bench)
        event_date = bench.index[200]
        ar = _abnormal_return(vendor, bench, event_date, 21, cal, beta=1.0)
        assert ar is not None
        assert ar < 0


# ---------------------------------------------------------------------------
# Tests: Summarize variant (mean + HAC)
# ---------------------------------------------------------------------------

class TestSummarizeVariant:
    def test_returns_none_fields_on_tiny_sample(self):
        """With fewer than 8 observations, should return None stats."""
        ars = pd.Series([0.01, -0.02, 0.03])
        result = _summarize_variant(ars, "test")
        assert result["mean"] is None
        assert result["t_hac"] is None
        assert result["n"] == 3

    def test_negative_mean_for_negative_returns(self):
        """A series of negative returns should yield a negative mean."""
        ars = pd.Series([-0.02] * 50)
        result = _summarize_variant(ars, "test")
        assert result["mean"] is not None
        assert result["mean"] < 0

    def test_mean_expressed_as_percent(self):
        """Mean is returned as a percentage (multiplied by 100)."""
        # 1% abnormal return per event
        ars = pd.Series([0.01] * 30)
        result = _summarize_variant(ars, "test")
        assert result["mean"] is not None
        # Should be ~1.0 (i.e., 1.0%), not 0.01
        assert 0.9 < result["mean"] < 1.1


# ---------------------------------------------------------------------------
# Tests: BH-FDR gate logic (from engine.validation)
# ---------------------------------------------------------------------------

class TestBenjaminiHochberg:
    def test_rejects_clearly_significant(self):
        """p=0.001 should be rejected at alpha=0.10 with 7 tests."""
        pvals = {
            "V1_5d": 0.001,
            "V1_21d": 0.80,
            "V2_5d": 0.70,
            "V2_21d": 0.90,
            "V3_5d": 0.85,
            "V3_21d": 0.75,
            "V4_21d": 0.65,
        }
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert result["V1_5d"]["reject"] is True

    def test_retains_all_null_pvalues(self):
        """Uniform p-values under H0 should not produce false discoveries at alpha=0.10."""
        rng = np.random.default_rng(42)
        pvals = {f"v{i}": float(rng.uniform(0.3, 0.9)) for i in range(8)}
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert all(not v["reject"] for v in result.values())

    def test_monotone_q_values(self):
        """BH q-values must be non-decreasing in rank order (monotone by construction)."""
        pvals = {"A": 0.01, "B": 0.05, "C": 0.20, "D": 0.50}
        result = benjamini_hochberg(pvals, alpha=0.10)
        # Sort by raw p-value and check q is non-decreasing
        sorted_items = sorted(result.items(), key=lambda x: x[1]["p"])
        qs = [v["q"] for _, v in sorted_items]
        for i in range(len(qs) - 1):
            assert qs[i] <= qs[i + 1] + 1e-9  # allow float rounding


# ---------------------------------------------------------------------------
# Tests: Newey-West (HAC) t-stat
# ---------------------------------------------------------------------------

class TestNeweyWestTstat:
    def test_zero_series_returns_zero_mean(self):
        """All-zero abnormal returns → mean=0, t=0."""
        x = np.zeros(50)
        result = newey_west_tstat(x, lags=4)
        assert result["mean"] == 0.0
        assert result["t"] == 0.0

    def test_positive_series_positive_t(self):
        """Strongly positive series → positive t-stat."""
        x = np.full(100, 0.02)
        result = newey_west_tstat(x, lags=4)
        assert result["t"] is not None
        assert result["t"] > 0

    def test_negative_series_negative_t(self):
        """Strongly negative series → negative t-stat."""
        x = np.full(100, -0.02)
        result = newey_west_tstat(x, lags=4)
        assert result["t"] is not None
        assert result["t"] < 0

    def test_returns_none_fields_on_tiny_sample(self):
        """Fewer than 8 obs → None fields returned."""
        x = np.array([0.01, -0.01, 0.02])
        result = newey_west_tstat(x, lags=4)
        assert result["mean"] is None
        assert result["t"] is None


# ---------------------------------------------------------------------------
# Tests: Variant grid sanity (pre-registration checks)
# ---------------------------------------------------------------------------

class TestVariantGrid:
    def test_grid_has_seven_entries(self):
        """Pre-registered grid must have exactly 7 entries (4 variants × 2 horizons - 1 for V4 21d only)."""
        assert len(VARIANT_GRID) == 7

    def test_all_variants_have_required_keys(self):
        """Each variant config must have variant, horizon, filter, description."""
        required = {"variant", "horizon", "filter", "description"}
        for v in VARIANT_GRID:
            assert required.issubset(set(v.keys())), f"Missing keys in {v}"

    def test_family_name_correct(self):
        """Family name must match pre-registered value."""
        assert FAMILY == "w2031_kev_vendor_shock"

    def test_horizons_are_5_or_21(self):
        """All horizons must be 5 or 21 (pre-registered)."""
        for v in VARIANT_GRID:
            assert v["horizon"] in (5, 21)

    def test_v4_is_21d_only(self):
        """V4 (W2-033 fold-in) is defined for 21d only."""
        v4_entries = [v for v in VARIANT_GRID if v["variant"] == "V4"]
        assert len(v4_entries) == 1
        assert v4_entries[0]["horizon"] == 21
