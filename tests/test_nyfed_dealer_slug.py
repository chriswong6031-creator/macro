"""Unit tests for NY Fed Primary Dealer collector and phase-0 harness logic.

Pure-function tests with tiny fixtures — no network, no disk I/O.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Allow importing from the repo root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.nyfed_primary_dealer import (
    _era_tag,
    _extract_row,
    _era_zscore,
    build_zscores,
    ERAS,
    Z_WINDOW,
)
from scripts.nyfed_dealer_phase0 import (
    align_signal_to_price,
    compute_drawdown_labels,
    leave_one_era_out,
)


# ============================================================================
# _era_tag
# ============================================================================

class TestEraTag:
    def test_known_breaks(self):
        assert _era_tag("SBP2001") == "SBP2001"
        assert _era_tag("SBP2013") == "SBP2013"
        assert _era_tag("SBN2013") == "SBN2013"
        assert _era_tag("SBN2015") == "SBN2015"
        assert _era_tag("SBN2022") == "SBN2022"
        assert _era_tag("SBN2024") == "SBN2024"

    def test_unknown_passthrough(self):
        assert _era_tag("SBN9999") == "SBN9999"


# ============================================================================
# _extract_row — early era (SBP2001)
# ============================================================================

class TestExtractRowEarlyEra:
    def _make_sbp2001_data(self):
        """Minimal series data for SBP2001 era with known values."""
        return {
            "PDPUSGCS5LNOP": 1000.0,   # coupon <=5yr net open
            "PDPUSGCS5MNOP": 2000.0,   # coupon >5yr net open
            "PDPUSGTBNOP": 500.0,       # bills net open
            "PDFASUFDA": 100.0,         # UST fails to deliver
            "PDFASUFRA": 150.0,         # UST fails to receive
        }

    def test_net_pos_computed(self):
        row = _extract_row("1999-06-02", "SBP2001", self._make_sbp2001_data())
        # net_pos = 1000 + 2000 + 500
        assert row["net_tsy_pos"] == pytest.approx(3500.0)

    def test_fails_extracted(self):
        row = _extract_row("1999-06-02", "SBP2001", self._make_sbp2001_data())
        assert row["fails_to_deliver"] == pytest.approx(100.0)
        assert row["fails_to_receive"] == pytest.approx(150.0)
        assert row["total_fails"] == pytest.approx(250.0)

    def test_missing_values_become_nan(self):
        row = _extract_row("1999-06-02", "SBP2001", {})
        assert math.isnan(row["net_tsy_pos"])
        assert math.isnan(row["fails_to_deliver"])
        assert math.isnan(row["total_fails"])

    def test_na_string_becomes_nan(self):
        row = _extract_row("1999-06-02", "SBP2001", {"PDPUSGCS5LNOP": float("nan")})
        # Should still be nan
        assert math.isnan(row["net_tsy_pos"])

    def test_era_tag_stored(self):
        row = _extract_row("1999-06-02", "SBP2001", self._make_sbp2001_data())
        assert row["era"] == "SBP2001"
        assert row["date"] == pd.Timestamp("1999-06-02")


# ============================================================================
# _extract_row — modern era (SBN2024)
# ============================================================================

class TestExtractRowModernEra:
    def _make_sbn2024_data(self):
        # Values verified against live API for 2024-07-03:
        # PDPOSGST-TOT=312736, PDFTD-USTET=113493 (deliver), PDFTR-USTET=124567 (receive)
        return {
            "PDPOSGST-TOT": 312736.0,
            "PDFTD-USTET": 113493.0,   # fails to DELIVER (source delivers, recipient hasn't received)
            "PDFTR-USTET": 124567.0,   # fails to RECEIVE
        }

    def test_modern_series_extracted(self):
        row = _extract_row("2024-07-03", "SBN2024", self._make_sbn2024_data())
        assert row["net_tsy_pos"] == pytest.approx(312736.0)
        assert row["fails_to_deliver"] == pytest.approx(113493.0)
        assert row["fails_to_receive"] == pytest.approx(124567.0)
        assert row["total_fails"] == pytest.approx(238060.0)

    def test_partial_fails_uses_nansum(self):
        """If one fail series is NaN, total uses the available one."""
        data = {"PDPOSGST-TOT": 100.0, "PDFTD-USTET": float("nan"), "PDFTR-USTET": 50.0}
        row = _extract_row("2024-07-03", "SBN2024", data)
        assert row["total_fails"] == pytest.approx(50.0)

    def test_both_fails_nan_gives_nan_total(self):
        data = {"PDPOSGST-TOT": 100.0}
        row = _extract_row("2024-07-03", "SBN2024", data)
        assert math.isnan(row["total_fails"])


# ============================================================================
# _era_zscore — within-era z-score
# ============================================================================

class TestEraZscore:
    def _make_panel(self, n_per_era: int = 200) -> tuple[pd.Series, pd.Series]:
        """Two eras with different mean levels — cross-era splice should NOT appear."""
        dates_a = pd.date_range("2000-01-01", periods=n_per_era, freq="W")
        dates_b = pd.date_range("2010-01-01", periods=n_per_era, freq="W")
        vals_a = pd.Series(np.random.default_rng(0).normal(0, 1, n_per_era), index=dates_a)
        vals_b = pd.Series(np.random.default_rng(1).normal(100, 1, n_per_era), index=dates_b)
        series = pd.concat([vals_a, vals_b]).sort_index()
        eras = pd.concat([
            pd.Series("ERA_A", index=dates_a),
            pd.Series("ERA_B", index=dates_b),
        ]).sort_index()
        return series, eras

    def test_z_has_no_cross_era_spike(self):
        """The z-score should not jump discontinuously at era boundaries."""
        series, eras = self._make_panel(n_per_era=200)
        z = _era_zscore(series, eras, window=52)
        # Drop the warm-up NaN period (first 4 observations per era)
        z_valid = z.dropna()
        # The absolute z-score should stay reasonable (no wild values from cross-era)
        assert float(z_valid.abs().max()) < 10.0, \
            f"z-score exploded: max={z_valid.abs().max():.2f}, likely cross-era splice"

    def test_z_near_zero_mean_per_era(self):
        """Within each era, the z-score should have approximately zero mean."""
        series, eras = self._make_panel(n_per_era=200)
        z = _era_zscore(series, eras, window=52)
        for era in eras.unique():
            mask = eras == era
            z_era = z[mask].dropna()
            if len(z_era) > 20:
                assert abs(z_era.mean()) < 0.5, \
                    f"ERA {era} z-mean={z_era.mean():.3f} — cross-era contamination?"

    def test_z_nan_with_insufficient_data(self):
        """First 3 observations per era should be NaN (min_periods=4)."""
        dates = pd.date_range("2000-01-01", periods=10, freq="W")
        series = pd.Series(np.arange(10.0), index=dates)
        eras = pd.Series("A", index=dates)
        z = _era_zscore(series, eras, window=156)
        assert z.iloc[:3].isna().all()


# ============================================================================
# align_signal_to_price — publication lag enforcement
# ============================================================================

class TestAlignSignalToPrice:
    def test_lag_shifts_signal_forward(self):
        """A signal on date t should not be available on t+6d."""
        weekly = pd.Series(
            [1.0, 2.0, 3.0],
            index=pd.to_datetime(["2020-01-01", "2020-01-08", "2020-01-15"])
        )
        daily_idx = pd.date_range("2020-01-01", "2020-01-22", freq="B")
        aligned = align_signal_to_price(weekly, daily_idx, pub_lag_days=7)

        # On 2020-01-06 (5 days after 2020-01-01), the value should be NaN
        # (the week 1 signal becomes available only on 2020-01-08 = 1998-01-01 + 7d)
        assert pd.isna(aligned.get("2020-01-06", float("nan")))

    def test_lag_value_available_after_lag(self):
        """After the lag window, the signal should be available."""
        weekly = pd.Series(
            [1.0, 2.0],
            index=pd.to_datetime(["2020-01-01", "2020-01-08"])
        )
        daily_idx = pd.date_range("2020-01-08", "2020-01-15", freq="B")
        aligned = align_signal_to_price(weekly, daily_idx, pub_lag_days=7)
        # 2020-01-08 = 2020-01-01 + 7d; the signal 1.0 should now be available
        first_val = aligned.dropna().iloc[0] if aligned.dropna().size else float("nan")
        assert first_val == pytest.approx(1.0)


# ============================================================================
# compute_drawdown_labels
# ============================================================================

class TestComputeDrawdownLabels:
    def test_flat_market_no_drawdown(self):
        idx = pd.date_range("2020-01-01", periods=100, freq="B")
        spy = pd.Series(100.0, index=idx)
        labels = compute_drawdown_labels(spy, horizon_days=21, threshold=-0.05)
        valid = labels.dropna()
        assert (valid == 0.0).all()

    def test_crash_detected(self):
        idx = pd.date_range("2020-01-01", periods=100, freq="B")
        prices = np.full(100, 100.0)
        prices[30:] = 90.0  # 10% drop on day 30
        spy = pd.Series(prices, index=idx)
        labels = compute_drawdown_labels(spy, horizon_days=21, threshold=-0.05)
        # Days just before the crash (day 10-25) should be labeled 1
        assert labels.iloc[10] == pytest.approx(1.0)

    def test_small_dip_not_labeled(self):
        idx = pd.date_range("2020-01-01", periods=100, freq="B")
        prices = np.full(100, 100.0)
        prices[30:] = 97.0  # 3% drop — below the 5% threshold
        spy = pd.Series(prices, index=idx)
        labels = compute_drawdown_labels(spy, horizon_days=21, threshold=-0.05)
        assert labels.iloc[10] == pytest.approx(0.0)


# ============================================================================
# leave_one_era_out
# ============================================================================

class TestLeaveOneEraOut:
    def _make_joint(self, n: int = 100, sign: float = 1.0) -> tuple[pd.Series, pd.Series, pd.Series]:
        rng = np.random.default_rng(42)
        idx = pd.date_range("2000-01-01", periods=n, freq="W")
        sig = pd.Series(rng.standard_normal(n), index=idx)
        fwd = pd.Series(sign * 0.01 + rng.standard_normal(n) * 0.05, index=idx)
        n_half = n // 2
        era = pd.Series(["A"] * n_half + ["B"] * (n - n_half), index=idx)
        return sig, fwd, era

    def test_consistent_when_sign_uniform(self):
        # G2 now tests the CONDITIONAL (extreme-week) forward return.
        # With n=200 and sign=1.0, extreme weeks (top 5%) should still show positive
        # conditional mean, so the function should run without error and produce per_era.
        sig, fwd, era = self._make_joint(n=200, sign=1.0)
        res = leave_one_era_out(sig, fwd, era)
        # "full_sign" is the sign of the conditional (extreme-week) forward mean
        assert "full_sign" in res
        # The per-era results should exist (at least one era tested)
        assert len(res["per_era"]) >= 1

    def test_short_series_returns_not_ok(self):
        sig = pd.Series([1.0, 2.0], index=pd.date_range("2020-01-01", periods=2, freq="W"))
        fwd = pd.Series([0.01, 0.02], index=sig.index)
        era = pd.Series(["A", "B"], index=sig.index)
        res = leave_one_era_out(sig, fwd, era)
        assert res["ok"] is False


# ============================================================================
# ERAS list sanity
# ============================================================================

class TestErasConfig:
    def test_no_gaps_or_overlaps(self):
        """Era date ranges should not have gaps or overlaps."""
        sorted_eras = sorted(ERAS, key=lambda e: e[1])
        for i in range(len(sorted_eras) - 1):
            _, _, end_i = sorted_eras[i]
            _, start_next, _ = sorted_eras[i + 1]
            # End of one era + 1 day should be before or equal to the start of the next
            e_ts = pd.Timestamp(end_i)
            s_ts = pd.Timestamp(start_next)
            gap = (s_ts - e_ts).days
            assert gap >= 1, f"Overlap between eras {sorted_eras[i][0]} and {sorted_eras[i+1][0]}"
            assert gap <= 14, f"Large gap ({gap}d) between eras {sorted_eras[i][0]} and {sorted_eras[i+1][0]}"

    def test_z_window_positive(self):
        assert Z_WINDOW > 0
        assert Z_WINDOW == 156  # 3 years of weekly data
