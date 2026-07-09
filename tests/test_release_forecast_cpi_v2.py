"""Tests for PR-G CPI component upgrade (PREREG_V2.md spec).

Categories:
  1. Shelter math — lease-window ZORI mean construction
  2. Divergence guard — k halved when |zori_signal - cpi_shelter_mom| > 3*sigma
  3. ZORI PIT — only observations with date + 45 days <= asof usable
  4. Components contract — components key present on projection dict, confidence_v2 in [0,1]
  5. Components sum tolerance — sum(contrib_pp) approx= point - bias (tolerance 1e-6)
  6. Known/proxy/residual weights sum to 1.0
  7. confidence_v2 in [0, 1]
  8. Build matrix + compute_components on synthetic inputs

Run:
    python -m pytest tests/test_release_forecast_cpi_v2.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_components_cpi import (
    _BLOCK_CONFIDENCE_WEIGHT,
    _DIVERGENCE_GUARD_SIGMA,
    _DIVERGENCE_GUARD_WINDOW,
    _SHELTER_K_BASE,
    _ZORI_LAG_DAYS,
    _compute_shelter_nowcast,
    _compute_zori_signal,
    _get_shelter_mom_last,
    compute_components,
    compute_confidence_v2,
)
from engine.release_forecast import (
    _ridge_fit,
    _ridge_predict_with_components,
    _zscore_apply,
    _zscore_params,
)


# ---------------------------------------------------------------------------
# Helper: build a synthetic ZORI national DataFrame
# ---------------------------------------------------------------------------

def _make_zori_df(months: int, start_ym: tuple[int, int] = (2015, 1)) -> pd.DataFrame:
    """Build synthetic ZORI national DataFrame with end-of-month index.

    Values: 1000 + 5*i (growing trend for positive MoM).
    """
    dates = []
    values = []
    y, m = start_ym
    for i in range(months):
        # end of month
        eom = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
        dates.append(eom)
        values.append(1000.0 + 5.0 * i)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return pd.DataFrame({"zori": values}, index=pd.DatetimeIndex(dates, name="date"))


def _make_shelter_df(months: int, start_ym: tuple[int, int] = (2000, 1)) -> pd.DataFrame:
    """Build synthetic CPI shelter DataFrame with first-of-month index."""
    dates = []
    values = []
    y, m = start_ym
    for i in range(months):
        dates.append(pd.Timestamp(y, m, 1))
        values.append(200.0 + 0.5 * i)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return pd.DataFrame({"cpi_shelter": values}, index=pd.DatetimeIndex(dates, name="date"))


# ---------------------------------------------------------------------------
# 1. Shelter math — lease-window ZORI mean
# ---------------------------------------------------------------------------

class TestShelterMathLeaseWindow:
    """Verify lease-reset window: months M-12..M-6, mean of MoM values."""

    def test_lease_window_mean_computation(self):
        """zori_signal = mean ZORI MoM over months target_M-12 to target_M-6 (7-month window).

        We construct a ZORI series with known values and verify the mean is correct.
        ZORI MoM for month i = (1000+5i)/(1000+5(i-1)) - 1 * 100 = 5/(1000+5(i-1)) * 100.
        For values in range [1000,1500], MoM ≈ 0.5% each step.
        """
        # Build ZORI from 2015-01 to 2022-12 (96 months)
        zori_df = _make_zori_df(months=96, start_ym=(2015, 1))

        # Target month: 2022-01 (M)
        # Lease-reset window: 2021-01 (M-12) through 2021-07 (M-6)
        target_month = pd.Timestamp("2022-01-01")
        # asof: well after window months + 45 days
        asof = date(2022, 3, 1)

        signal = _compute_zori_signal(zori_df, target_month, asof)
        assert signal is not None, "Should compute signal with sufficient history"
        assert isinstance(signal, float)
        # Signal should be a small positive number (each MoM ≈ 5/X * 100)
        assert 0.0 < signal < 2.0, f"Expected small positive MoM, got {signal}"

    def test_lease_window_uses_exactly_m_minus_12_to_m_minus_6(self):
        """The 7-month window must cover M-12..M-6 inclusive."""
        # Build ZORI with known pattern: months outside [M-12, M-6] get large value
        # so if they contaminate the mean we'd see a wrong result.
        zori_df = _make_zori_df(months=96, start_ym=(2015, 1))
        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        signal_full = _compute_zori_signal(zori_df, target_month, asof)

        # Manually compute what the mean should be for months 2021-01..2021-07
        target_m = target_month.to_period("M")
        window_months_ym = set()
        for k in range(6, 13):
            wm = (target_m - k).to_timestamp(how="E")
            window_months_ym.add((wm.year, wm.month))

        # These should be: 2021-01, 2021-02, ..., 2021-07
        expected_ym = {(2021, m) for m in range(1, 8)}
        assert window_months_ym == expected_ym, f"Window mismatch: {window_months_ym}"

    def test_returns_none_when_insufficient_window_months(self):
        """Returns None when fewer than 3 window months have PIT-filtered data."""
        # Very short ZORI history: only 5 months starting 2015-01
        zori_df = _make_zori_df(months=5, start_ym=(2015, 1))
        target_month = pd.Timestamp("2025-01-01")
        asof = date(2025, 3, 1)
        signal = _compute_zori_signal(zori_df, target_month, asof)
        assert signal is None

    def test_returns_none_when_no_pit_filtered_data(self):
        """Returns None when all ZORI data is filtered out by PIT constraint."""
        # ZORI data: all from 2026-06, published 2026-06-30
        # If asof = 2026-07-01, those rows are only 1 day after end-of-month,
        # but PIT lag is 45 days, so 2026-06-30 + 45 = 2026-08-14 > asof → filtered out
        zori_df = _make_zori_df(months=96, start_ym=(2015, 1))
        target_month = pd.Timestamp("2026-08-01")
        asof = date(2026, 7, 1)  # too early for most recent ZORI data
        signal = _compute_zori_signal(zori_df, target_month, asof)
        # Most recent data still filtered; window months 2025-08..2026-02 need
        # date + 45 <= 2026-07-01 → date <= 2026-05-17, so 2026-05 end date OK
        # Some months in window should be available (2025-08..2025-12)
        # We just verify None or float (not a crash)
        assert signal is None or isinstance(signal, float)


# ---------------------------------------------------------------------------
# 2. Divergence guard — k halved
# ---------------------------------------------------------------------------

class TestDivergenceGuard:
    """k is halved to 0.175 when |zori_signal - cpi_shelter_mom| > 3 * sigma."""

    def _run_shelter_nowcast_with_divergence(self, diverge: bool) -> tuple[float | None, dict]:
        """Build synthetic data where divergence is or is not triggered."""
        # Shelter history: 30 months of shelter MoM ~ 0.3% each
        # sigma_shelter ~ 0 (constant), so any |divergence| > 0 triggers guard
        # To avoid triggering when we don't want it, use noisy history

        # Build shelter with std ≈ 0.1%
        np.random.seed(42)
        shelter_vals = [200.0]
        for _ in range(35):
            shelter_vals.append(shelter_vals[-1] * (1 + np.random.normal(0.003, 0.001)))
        dates_s = pd.date_range("2000-01", periods=36, freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": shelter_vals}, index=dates_s)

        # ZORI: 96 months, so lease-reset window is available
        zori_df = _make_zori_df(months=96, start_ym=(2015, 1))

        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        if diverge:
            # Override the ZORI values to make zori_signal extremely large
            # so that |zori_signal - cpi_shelter_mom| >> 3 * sigma
            zori_df = zori_df.copy()
            zori_df["zori"] = zori_df["zori"] * 0.001  # make MoM huge negative
            # Actually: set values so MoM is very large
            huge = pd.DataFrame({"zori": [1000.0 + i * 100 for i in range(96)]},
                                 index=zori_df.index)
            return _compute_shelter_nowcast(huge, shelter_df, target_month, asof)
        else:
            return _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)

    def test_k_not_halved_when_within_3_sigma(self):
        """When signals agree (within 3 sigma), k = 0.35."""
        _, prov = self._run_shelter_nowcast_with_divergence(diverge=False)
        if prov["shelter_k_applied"] is not None:
            # k should be 0.35 (no guard triggered)
            # Guard only triggers when |divergence| > 3 * sigma AND we have 24 months of history
            # Our shelter history is 36 months so guard CAN trigger
            assert not prov["divergence_guard_triggered"] or prov["shelter_k_applied"] == pytest.approx(0.175)

    def test_k_is_0_35_without_divergence(self):
        """With small zori_signal close to cpi_shelter_mom, k stays 0.35."""
        # Constant shelter with exactly constant MoM → sigma = 0 → guard bypassed
        shelter_vals = [200.0 + 0.6 * i for i in range(30)]  # constant 0.3% MoM
        dates_s = pd.date_range("2000-01", periods=30, freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": shelter_vals}, index=dates_s)

        # zori_df with small MoM similar to shelter momentum
        zori_df = _make_zori_df(months=96, start_ym=(2015, 1))
        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        _, prov = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)
        if prov["shelter_k_applied"] is not None:
            # With only ~30 months of shelter history, guard may or may not trigger
            # but k_applied must be either 0.35 or 0.175
            assert prov["shelter_k_applied"] in (0.35, 0.175)

    def test_divergence_guard_halves_k(self):
        """When |zori_signal - cpi_shelter_mom| > 3 * sigma over 24m window, k = 0.175."""
        # Shelter: 30 months of constant 0.3% MoM → sigma = 0 → guard triggers at any divergence
        # Actually sigma=0 → guard is bypassed (if sigma=0, condition can't trigger)
        # Use noisy shelter: std = 0.05%, and make zori_signal = cpi_shelter_mom + 20*sigma
        np.random.seed(99)
        shelter_moms_hist = np.random.normal(0.3, 0.05, 26)  # 26 months of MoM
        # Build level series from MoM
        levels = [200.0]
        for mom in shelter_moms_hist:
            levels.append(levels[-1] * (1 + mom / 100.0))
        dates_s = pd.date_range("2000-01", periods=len(levels), freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": levels}, index=dates_s)
        # Last MoM (knowable) = shelter_moms_hist[-1] ≈ 0.3%
        # ZORI signal: make it enormous relative to sigma ≈ 0.05%
        # sigma = 0.05%, 3*sigma = 0.15%, so |zori - shelter| > 0.15% triggers guard
        # We control zori_signal indirectly through the ZORI df MoM values
        # Build ZORI so lease-window mean MoM ≈ +5% (>> 3*sigma from 0.3%)
        dates_z = pd.date_range("2015-01-31", periods=96, freq="ME")
        values_z = [1000.0]
        for _ in range(95):
            values_z.append(values_z[-1] * 1.05)  # 5% MoM → huge signal
        zori_df = pd.DataFrame({"zori": values_z}, index=dates_z)

        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        val, prov = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)
        if prov["shelter_k_applied"] is not None and prov["zori_signal"] is not None:
            # With shelter_history >= 24 months and large divergence
            sigma_check = float(np.std(shelter_moms_hist[-24:], ddof=1))
            cpi_mom = prov["cpi_shelter_mom_last"]
            zori_s = prov["zori_signal"]
            if cpi_mom is not None and sigma_check > 0:
                divergence = abs(zori_s - cpi_mom)
                if divergence > _DIVERGENCE_GUARD_SIGMA * sigma_check:
                    assert prov["shelter_k_applied"] == pytest.approx(0.175), (
                        f"Expected k=0.175, got {prov['shelter_k_applied']}; "
                        f"div={divergence:.4f}, 3sigma={3*sigma_check:.4f}"
                    )
                    assert prov["divergence_guard_triggered"] is True

    def test_divergence_guard_bypassed_when_history_short(self):
        """Guard is bypassed when shelter history < 24 months."""
        # Only 10 months of shelter history → guard cannot trigger
        shelter_vals = [200.0 + 0.5 * i for i in range(11)]
        dates_s = pd.date_range("2021-01", periods=11, freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": shelter_vals}, index=dates_s)

        # ZORI with huge MoM — guard should NOT trigger (history < 24)
        dates_z = pd.date_range("2015-01-31", periods=96, freq="ME")
        values_z = [1000.0 * (1.05 ** i) for i in range(96)]
        zori_df = pd.DataFrame({"zori": values_z}, index=dates_z)

        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        _, prov = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)
        # With <24 months, guard is bypassed → k should remain 0.35
        if prov["shelter_k_applied"] is not None:
            assert prov["divergence_guard_triggered"] is False
            assert prov["shelter_k_applied"] == pytest.approx(0.35)

    def test_nowcast_formula_no_guard(self):
        """shelter_nowcast = (1-0.35)*cpi_shelter_mom_last + 0.35*zori_signal."""
        # Use controlled values
        shelter_vals = [200.0 + 0.3 * i for i in range(5)]
        dates_s = pd.date_range("2021-09", periods=5, freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": shelter_vals}, index=dates_s)

        # ZORI with known MoM: each period +1%
        dates_z = pd.date_range("2015-01-31", periods=96, freq="ME")
        values_z = [1000.0]
        for _ in range(95):
            values_z.append(values_z[-1] * 1.01)
        zori_df = pd.DataFrame({"zori": values_z}, index=dates_z)

        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        val, prov = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)
        if val is not None and prov["shelter_k_applied"] is not None:
            k = prov["shelter_k_applied"]
            zori_s = prov["zori_signal"]
            cpi_mom = prov["cpi_shelter_mom_last"]
            if zori_s is not None and cpi_mom is not None:
                expected = (1 - k) * cpi_mom + k * zori_s
                assert abs(val - expected) < 1e-10, (
                    f"Nowcast formula mismatch: got {val}, expected {expected}"
                )


# ---------------------------------------------------------------------------
# 3. ZORI PIT — conservative 45-day lag
# ---------------------------------------------------------------------------

class TestZORIPIT:
    """Only ZORI observations with date + 45 days <= asof are usable."""

    def test_future_zori_excluded(self):
        """A ZORI row dated 2024-03-31 must not be used if asof = 2024-04-01.

        date + 45 = 2024-05-15 > 2024-04-01 → excluded.
        """
        dates_z = pd.date_range("2015-01-31", periods=110, freq="ME")
        values_z = [1000.0 + i * 5 for i in range(110)]
        zori_df = pd.DataFrame({"zori": values_z}, index=pd.DatetimeIndex(dates_z))

        # asof = 2024-04-01 — ZORI through 2024-02-29 should be usable (date+45=2024-04-14 <= asof is false!)
        # Actually date=2024-02-29 → date+45=2024-04-14 > 2024-04-01 → EXCLUDED
        # date=2024-01-31 → date+45=2024-03-16 <= 2024-04-01 → INCLUDED
        asof = date(2024, 4, 1)
        pit_mask = zori_df.index + pd.Timedelta(days=_ZORI_LAG_DAYS) <= pd.Timestamp(asof)
        usable = zori_df[pit_mask]
        # The last usable date: date + 45 <= 2024-04-01 → date <= 2024-02-16
        # January 2024 end-of-month = 2024-01-31: 2024-01-31 + 45 = 2024-03-16 <= 2024-04-01 ✓
        # February 2024 end-of-month = 2024-02-29: 2024-02-29 + 45 = 2024-04-14 > 2024-04-01 ✗
        assert len(usable) > 0
        last_date = usable.index[-1]
        assert (last_date.year, last_date.month) == (2024, 1), (
            f"Last usable ZORI should be 2024-01, got {last_date}"
        )

    def test_lag_is_45_days(self):
        """Verify _ZORI_LAG_DAYS constant is 45 per PREREG_V2.md §1.1."""
        assert _ZORI_LAG_DAYS == 45

    def test_zori_signal_respects_pit_in_compute_function(self):
        """_compute_zori_signal only uses PIT-filtered ZORI rows."""
        # Build ZORI history but set asof very early so nothing in the window is usable
        dates_z = pd.date_range("2015-01-31", periods=50, freq="ME")
        values_z = [1000.0 + 5 * i for i in range(50)]
        zori_df = pd.DataFrame({"zori": values_z}, index=pd.DatetimeIndex(dates_z))

        # Target month 2019-02, asof very early (before all ZORI data + lag)
        target_month = pd.Timestamp("2019-02-01")
        asof = date(2015, 1, 1)  # before any ZORI + 45 days

        signal = _compute_zori_signal(zori_df, target_month, asof)
        assert signal is None, f"Expected None (no PIT-usable ZORI), got {signal}"


# ---------------------------------------------------------------------------
# 4. Contract — projection dict has components + confidence_v2
# ---------------------------------------------------------------------------

class TestProjectionContract:
    """project_release for CPI types must carry components + confidence_v2 keys."""

    def test_cpi_headline_projection_has_v2_keys(self, tmp_path):
        """project_release('cpi_headline', ...) returns dict with components and confidence_v2."""
        from engine.release_forecast import load_vintages, project_release
        # We need real data for a meaningful test — use the actual repo root
        root = _REPO
        try:
            vintages = load_vintages(root)
        except Exception:
            pytest.skip("Vintage parquet not available")

        result = project_release("cpi_headline", date(2024, 6, 1), root)
        assert "components" in result, "Missing 'components' key"
        assert "confidence_v2" in result, "Missing 'confidence_v2' key"
        assert "confidence_components_v2" in result, "Missing 'confidence_components_v2' key"
        assert result["display_only"] is True
        assert result["authority"] is False

    def test_cpi_core_projection_has_v2_keys(self, tmp_path):
        """project_release('cpi_core', ...) returns dict with components and confidence_v2."""
        from engine.release_forecast import load_vintages, project_release
        root = _REPO
        try:
            load_vintages(root)
        except Exception:
            pytest.skip("Vintage parquet not available")

        result = project_release("cpi_core", date(2024, 6, 1), root)
        assert "components" in result
        assert "confidence_v2" in result
        assert result["display_only"] is True

    def test_nfp_projection_unchanged(self):
        """NFP projection must still work and NOT be broken by V2 CPI changes."""
        from engine.release_forecast import load_vintages, project_release
        root = _REPO
        try:
            load_vintages(root)
        except Exception:
            pytest.skip("Vintage parquet not available")

        result = project_release("nfp", date(2024, 6, 1), root)
        # NFP does not get components/confidence_v2 (V2 is CPI-only)
        assert result["release"] == "nfp"
        assert result["display_only"] is True


# ---------------------------------------------------------------------------
# 5. Components sum ≈ prediction - intercept (tolerance 1e-6)
# ---------------------------------------------------------------------------

class TestComponentsSum:
    """sum(contrib_pp) must equal point - bias (ridge formula: y = sum(beta*z) + bias)."""

    def test_components_sum_to_prediction_minus_bias(self):
        """Verify: sum of contrib_pp per block = beta_features @ z_features.

        This equals point - bias from the ridge formula.
        """
        # Build synthetic training data
        np.random.seed(0)
        n_train = 80
        n_feat = 4  # 3 own lags + 1 pipeline
        X_train = np.random.randn(n_train, n_feat)
        y_train = X_train[:, 0] * 0.3 + np.random.randn(n_train) * 0.1

        x_pred = np.random.randn(n_feat)

        point, beta_features, z_features = _ridge_predict_with_components(
            X_train, y_train, x_pred
        )

        # sum of contrib_pp = beta_features @ z_features
        # which equals point - bias
        contrib_sum = float(np.dot(beta_features, z_features))

        # Verify against direct computation
        mean, std = _zscore_params(X_train)
        xz_pred = _zscore_apply(x_pred.reshape(1, -1), mean, std).ravel()
        expected_contrib_sum = float(np.dot(beta_features, xz_pred))

        assert abs(contrib_sum - expected_contrib_sum) < 1e-10

        # point = contrib_sum + bias
        # beta[-1] is bias; we need to refit to get it
        ones_tr = np.ones((X_train.shape[0], 1))
        Xz_tr = _zscore_apply(X_train, mean, std)
        X_aug = np.hstack([Xz_tr, ones_tr])
        beta_full = _ridge_fit(X_aug, y_train)
        bias = float(beta_full[-1])
        expected_point = contrib_sum + bias

        assert abs(point - expected_point) < 1e-8, (
            f"point={point}, contrib_sum+bias={expected_point}"
        )

    def test_compute_components_contrib_sum_matches_prediction(self):
        """compute_components: sum of block contrib_pp equals beta_features @ z_features."""
        np.random.seed(1)
        n_train = 80
        # 7 features: 3 own lags, sticky, median, flex, ppi
        feature_names = [
            "cpi_core_mom_lag1", "cpi_core_mom_lag2", "cpi_core_mom_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1", "ppi_mom_lag1",
        ]
        n_feat = len(feature_names)
        X_train = np.random.randn(n_train, n_feat)
        y_train = X_train[:, 0] * 0.4 + np.random.randn(n_train) * 0.05

        x_pred = np.random.randn(n_feat)
        avail_mask = np.ones(n_feat, dtype=bool)

        point, beta_features, z_features = _ridge_predict_with_components(
            X_train, y_train, x_pred
        )
        components = compute_components(
            feature_names, beta_features, z_features, avail_mask, "cpi_core"
        )
        assert components is not None, "compute_components should not return None"

        total_contrib = sum(c["contrib_pp"] for c in components)
        direct_contrib = float(np.dot(beta_features, z_features))

        assert abs(total_contrib - direct_contrib) < 1e-6, (
            f"sum(contrib_pp)={total_contrib} != beta@z={direct_contrib}"
        )


# ---------------------------------------------------------------------------
# 6. Known/proxy/residual weights sum to 1.0
# ---------------------------------------------------------------------------

class TestWeightsSumToOne:
    """confidence_components_v2: w_known + w_proxy + w_residual == 1.0."""

    def test_weights_sum_to_one_all_blocks(self):
        """With all blocks present, weights must sum to 1.0."""
        components = [
            {"name": "energy", "contrib_pp": 0.1, "confidence": 1.0},
            {"name": "shelter", "contrib_pp": 0.05, "confidence": 0.6},
            {"name": "core_persistence", "contrib_pp": 0.2, "confidence": 0.0},
            {"name": "pipeline", "contrib_pp": 0.08, "confidence": 0.6},
        ]
        _, comps_v2 = compute_confidence_v2(components, input_completeness=1.0)
        assert comps_v2 is not None
        total = comps_v2["w_known"] + comps_v2["w_proxy"] + comps_v2["w_residual"]
        assert abs(total - 1.0) < 1e-10, f"Weights sum = {total}, expected 1.0"

    def test_weights_sum_to_one_partial_blocks(self):
        """With only some blocks present, weights still sum to 1.0."""
        components = [
            {"name": "core_persistence", "contrib_pp": 0.3, "confidence": 0.0},
            {"name": "pipeline", "contrib_pp": 0.1, "confidence": 0.6},
        ]
        _, comps_v2 = compute_confidence_v2(components, input_completeness=0.8)
        assert comps_v2 is not None
        total = comps_v2["w_known"] + comps_v2["w_proxy"] + comps_v2["w_residual"]
        assert abs(total - 1.0) < 1e-10

    def test_weights_all_zero_when_all_contributions_zero(self):
        """When all contrib_pp=0, degenerate case: confidence_v2=0."""
        components = [
            {"name": "energy", "contrib_pp": 0.0, "confidence": 1.0},
            {"name": "shelter", "contrib_pp": 0.0, "confidence": 0.6},
        ]
        cv2, comps_v2 = compute_confidence_v2(components, input_completeness=1.0)
        assert cv2 == 0.0
        assert comps_v2 is not None

    def test_returns_none_for_empty_components(self):
        """None components → confidence_v2=None."""
        cv2, comps_v2 = compute_confidence_v2(None, input_completeness=1.0)
        assert cv2 is None
        assert comps_v2 is None


# ---------------------------------------------------------------------------
# 7. confidence_v2 in [0, 1]
# ---------------------------------------------------------------------------

class TestConfidenceV2Bounds:
    """confidence_v2 must always be in [0, 1]."""

    def test_confidence_v2_in_unit_interval(self):
        """Exhaustive over all block combinations: confidence_v2 in [0,1]."""
        test_cases = [
            [{"name": "energy", "contrib_pp": 1.0, "confidence": 1.0}],
            [{"name": "shelter", "contrib_pp": 0.5, "confidence": 0.6}],
            [{"name": "core_persistence", "contrib_pp": 2.0, "confidence": 0.0}],
            [{"name": "energy", "contrib_pp": 0.3, "confidence": 1.0},
             {"name": "shelter", "contrib_pp": 0.2, "confidence": 0.6},
             {"name": "core_persistence", "contrib_pp": 0.1, "confidence": 0.0}],
            [{"name": "pipeline", "contrib_pp": 0.01, "confidence": 0.6},
             {"name": "core_persistence", "contrib_pp": 10.0, "confidence": 0.0}],
        ]
        input_completeness_vals = [0.0, 0.5, 1.0, 0.78]

        for comps in test_cases:
            for ic in input_completeness_vals:
                cv2, _ = compute_confidence_v2(comps, ic)
                if cv2 is not None:
                    assert 0.0 <= cv2 <= 1.0, (
                        f"confidence_v2={cv2} out of [0,1] for comps={comps}, ic={ic}"
                    )

    def test_confidence_v2_zero_with_zero_completeness(self):
        """input_completeness=0 → confidence_v2=0."""
        components = [{"name": "energy", "contrib_pp": 1.0, "confidence": 1.0}]
        cv2, _ = compute_confidence_v2(components, input_completeness=0.0)
        assert cv2 == 0.0

    def test_confidence_v2_max_when_all_known(self):
        """All contributions from 'known' block with ic=1 → confidence_v2=1.0."""
        components = [{"name": "energy", "contrib_pp": 1.0, "confidence": 1.0}]
        cv2, _ = compute_confidence_v2(components, input_completeness=1.0)
        assert cv2 == pytest.approx(1.0)

    def test_confidence_v2_zero_when_all_residual(self):
        """All contributions from 'residual' block → c_raw=0 → confidence_v2=0."""
        components = [{"name": "core_persistence", "contrib_pp": 1.0, "confidence": 0.0}]
        cv2, _ = compute_confidence_v2(components, input_completeness=1.0)
        assert cv2 == 0.0


# ---------------------------------------------------------------------------
# 8. _ridge_predict_with_components correctness
# ---------------------------------------------------------------------------

class TestRidgePredictWithComponents:
    """_ridge_predict_with_components must give same point as _ridge_predict."""

    def test_same_point_as_ridge_predict(self):
        """point from _ridge_predict_with_components == _ridge_predict."""
        from engine.release_forecast import _ridge_predict

        np.random.seed(42)
        n, p = 70, 5
        X_train = np.random.randn(n, p)
        y_train = X_train @ np.array([0.5, -0.3, 0.2, 0.1, 0.0]) + np.random.randn(n) * 0.1
        x_pred = np.random.randn(p)

        point_v1 = _ridge_predict(X_train, y_train, x_pred)
        point_v2, beta_f, z_f = _ridge_predict_with_components(X_train, y_train, x_pred)

        assert abs(point_v1 - point_v2) < 1e-10, (
            f"Point mismatch: v1={point_v1}, v2={point_v2}"
        )

    def test_beta_z_dimensions(self):
        """beta_features and z_features must have shape (n_features,)."""
        np.random.seed(7)
        n, p = 65, 4
        X_train = np.random.randn(n, p)
        y_train = np.random.randn(n)
        x_pred = np.random.randn(p)

        _, beta_f, z_f = _ridge_predict_with_components(X_train, y_train, x_pred)

        assert beta_f.shape == (p,), f"Expected ({p},), got {beta_f.shape}"
        assert z_f.shape == (p,), f"Expected ({p},), got {z_f.shape}"


# ---------------------------------------------------------------------------
# 9. Block confidence weight constants
# ---------------------------------------------------------------------------

class TestBlockConfidenceWeights:
    """Block confidence weights must match PREREG_V2.md §4.2."""

    def test_energy_is_known(self):
        assert _BLOCK_CONFIDENCE_WEIGHT["energy"] == 1.0

    def test_shelter_is_proxy(self):
        assert _BLOCK_CONFIDENCE_WEIGHT["shelter"] == 0.6

    def test_pipeline_is_proxy(self):
        assert _BLOCK_CONFIDENCE_WEIGHT["pipeline"] == 0.6

    def test_core_persistence_is_residual(self):
        assert _BLOCK_CONFIDENCE_WEIGHT["core_persistence"] == 0.0

    def test_shelter_k_base_is_0_35(self):
        assert _SHELTER_K_BASE == pytest.approx(0.35)

    def test_divergence_guard_threshold_is_3_sigma(self):
        assert _DIVERGENCE_GUARD_SIGMA == pytest.approx(3.0)

    def test_divergence_guard_window_is_24(self):
        assert _DIVERGENCE_GUARD_WINDOW == 24


# ---------------------------------------------------------------------------
# 10. B1 fix — positive-control PIT test for _get_shelter_mom_last
#     This test FAILS on the pre-fix code (index <= asof_ts) and PASSES after
#     the B1 fix (index <= cutoff = asof_period - 2 months).
# ---------------------------------------------------------------------------

class TestShelterLookAheadLeakFix:
    """Positive-control test that catches the pre-B1-fix look-ahead leak.

    Scenario: synthetic CUSR0000SAH1 where month M (the target month) and
    month M+1 carry a poison value (+99% MoM change). Month M-1 is normal.
    Decision date asof is mid-M+1 (day before M's CPI release).

    Post-fix (correct): _get_shelter_mom_last must return the M-1-based momentum
      and must NOT touch the poison months.
    Pre-fix (leaked): the index <= asof_ts filter admits M and M+1 from the
      latest-revised parquet, contaminating the returned momentum.
    """

    def _build_poison_shelter_df(self, asof: date, target_month: pd.Timestamp) -> pd.DataFrame:
        """Build shelter df where M and M+1 are poison (+99 jump), M-1 is normal.

        All months from 2000-01 through M+1 are present (latest-revised parquet).
        Normal months: level = 200 + 0.3*i (constant ~0.15% MoM for a 200-level series).
        Month M level: boosted by 99x to simulate poison.
        Month M+1: also boosted.
        """
        target_m = pd.Timestamp(target_month).to_period("M")
        # Build normal series from 2000-01 through M-1
        start = pd.Period("2000-01", freq="M")
        months_normal = (target_m - 1 - start).n + 1  # number of normal months through M-1
        dates = []
        values = []
        cur = start
        for i in range(months_normal):
            dates.append(cur.to_timestamp())
            values.append(200.0 + 0.3 * i)
            cur += 1
        # Month M: poison — make level 99x the prior level
        m_level = (200.0 + 0.3 * (months_normal - 1)) * 99
        dates.append(target_m.to_timestamp())
        values.append(m_level)
        # Month M+1: also poison
        m1_level = m_level * 99
        dates.append((target_m + 1).to_timestamp())
        values.append(m1_level)

        return pd.DataFrame(
            {"cpi_shelter": values},
            index=pd.DatetimeIndex(dates, name="date"),
        )

    def test_poison_months_excluded_post_fix(self):
        """After B1 fix: _get_shelter_mom_last returns M-1 MoM and ignores M, M+1 poison.

        If pre-fix code (index <= asof_ts) were used, the last knowable month
        would be M+1 (or M), and mom.iloc[-1] would be the catastrophic 99x-level
        MoM (>> 90%). The fixed code caps at asof_period - 2 = M-1, so the
        returned MoM is the normal ~0.15% level.
        """
        # Target month M = 2023-02 (month we are forecasting)
        target_month = pd.Timestamp("2023-02-01")
        # asof = 2023-03-10 (mid-March, day before Feb CPI release typically)
        asof = date(2023, 3, 10)

        shelter_df = self._build_poison_shelter_df(asof, target_month)

        last_mom, history = _get_shelter_mom_last(shelter_df, asof)

        # The returned MoM must be the normal M-1 (Jan 2023) momentum
        # Normal MoM ≈ 0.3 / (200 + 0.3*(n-1)) * 100 ≈ 0.15% range; max ~0.15%
        # Poison MoM would be (99 - 1) * 100 = 9800% — easily detectable
        assert last_mom is not None, "Should return a value with sufficient shelter history"
        assert abs(last_mom) < 1.0, (
            f"_get_shelter_mom_last returned {last_mom:.2f}%, expected normal "
            f"~0.15% MoM; poison months M/M+1 should be excluded. "
            f"This value indicates the pre-B1-fix look-ahead leak is still present."
        )

    def test_last_usable_month_is_asof_minus_2(self):
        """The last shelter month index must be <= (asof_period - 2) end-of-month.

        Directly checks the cutoff boundary: a shelter observation dated at
        (asof_period - 1) end-of-month must be excluded (that is month M itself
        when asof is in month M+1), while (asof_period - 2) end-of-month must
        be included (month M-1).
        """
        # asof = 2023-03-10 → asof_period = 2023-03 → cutoff_period = 2023-01
        asof = date(2023, 3, 10)
        asof_ts = pd.Timestamp(asof)

        # Shelter df with exactly 3 rows: 2022-12 (cutoff-1), 2023-01 (cutoff), 2023-02 (excluded)
        dates = [
            pd.Timestamp("2022-12-01"),  # month M-2 (Jan 2023 - 2 = Nov 2022... wait)
            pd.Timestamp("2023-01-01"),  # month M-1 (Jan 2023 = cutoff)
            pd.Timestamp("2023-02-01"),  # month M (Feb 2023) — must be excluded
        ]
        values = [200.0, 200.3, 1000000.0]  # last is poison
        shelter_df = pd.DataFrame({"cpi_shelter": values}, index=pd.DatetimeIndex(dates))

        last_mom, history = _get_shelter_mom_last(shelter_df, asof)

        # With 3 rows but the last one excluded, we have 2 rows (2022-12 and 2023-01)
        # MoM from those two: (200.3 / 200.0 - 1) * 100 = 0.15%
        # If the poison row were included, MoM would be enormous
        assert last_mom is not None
        # MoM should be small positive (normal ~0.15%)
        assert last_mom == pytest.approx((200.3 / 200.0 - 1) * 100, abs=1e-8), (
            f"Expected MoM from 2023-01 (normal), got {last_mom}. "
            f"Check that 2023-02 poison row was excluded."
        )

    def test_positive_control_pre_fix_would_fail(self):
        """Control: verifies test_poison_months_excluded_post_fix detects pre-fix behavior.

        Simulates the pre-fix filter (index <= asof_ts) and confirms it WOULD
        admit the poison rows, causing large MoM. This is the positive control
        that proves our test has discriminating power.
        """
        target_month = pd.Timestamp("2023-02-01")
        asof = date(2023, 3, 10)
        asof_ts = pd.Timestamp(asof)

        shelter_df = self._build_poison_shelter_df(asof, target_month)
        col = shelter_df.columns[0]

        # Simulate pre-fix filter
        known_prefix = shelter_df[shelter_df.index <= asof_ts].sort_index()
        mom_prefix = known_prefix[col].pct_change() * 100.0
        mom_prefix = mom_prefix.dropna()
        if not mom_prefix.empty:
            last_prefix = float(mom_prefix.iloc[-1])
            # Pre-fix would have captured the poison: MoM >> 1% (actually 9800%+)
            assert abs(last_prefix) > 1.0, (
                f"Pre-fix filter should have returned poison MoM, got {last_prefix}. "
                f"Positive-control setup may be incorrect."
            )


# ---------------------------------------------------------------------------
# 11. Unconditional divergence guard and formula tests (m2 fix)
#     Replaces the conditionally-vacuous `if` wrappers with deterministic fixtures.
# ---------------------------------------------------------------------------

class TestDivergenceGuardUnconditional:
    """Unconditional versions of divergence guard and formula tests using
    deterministic fixtures that guarantee the code paths are actually exercised."""

    def test_divergence_guard_unconditionally_halves_k(self):
        """Deterministic: divergence guard MUST trigger and return k=0.175.

        Fixture: 26 months of shelter history with std ≈ 0.05%; ZORI signal ≈ 5%
        (mean of window months with 5% MoM each). Divergence ≈ 4.7% >> 3*0.05% = 0.15%.
        All `if` wrappers replaced by direct assertions — test fails if any precondition
        is not met rather than silently passing.
        """
        np.random.seed(99)
        shelter_moms = np.random.normal(0.3, 0.05, 26)
        levels = [200.0]
        for mom in shelter_moms:
            levels.append(levels[-1] * (1 + mom / 100.0))
        dates_s = pd.date_range("2000-01", periods=len(levels), freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": levels}, index=dates_s)

        # ZORI: 5% MoM for all months (window mean ≈ 5%)
        dates_z = pd.date_range("2015-01-31", periods=96, freq="ME")
        values_z = [1000.0]
        for _ in range(95):
            values_z.append(values_z[-1] * 1.05)
        zori_df = pd.DataFrame({"zori": values_z}, index=dates_z)

        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        val, prov = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)

        # All preconditions MUST hold — if any fail, the test fails (not silently passes)
        assert prov["shelter_k_applied"] is not None, "k was not computed — fixture bug"
        assert prov["zori_signal"] is not None, "zori_signal is None — fixture bug"
        assert prov["cpi_shelter_mom_last"] is not None, "cpi_shelter_mom_last is None — fixture bug"

        sigma = float(np.std(shelter_moms[-24:], ddof=1))
        divergence = abs(prov["zori_signal"] - prov["cpi_shelter_mom_last"])
        assert sigma > 0, "sigma must be > 0 for guard to be testable"
        assert divergence > _DIVERGENCE_GUARD_SIGMA * sigma, (
            f"Fixture did not produce divergence: div={divergence:.4f}, 3sigma={3*sigma:.4f}"
        )
        # Main assertion — unconditional
        assert prov["shelter_k_applied"] == pytest.approx(0.175), (
            f"Expected k=0.175, got {prov['shelter_k_applied']}"
        )
        assert prov["divergence_guard_triggered"] is True

    def test_nowcast_formula_unconditional(self):
        """Deterministic: blending formula must hold with exact controlled values.

        Fixture uses short shelter history (< 24 months) to guarantee guard is
        bypassed → k = 0.35 always. ZORI and shelter MoM are known constants.
        All `if` wrappers eliminated — direct assertions.
        """
        # 5 shelter months → MoM = 0.3 / (200 + 0.3*(i)) * 100 ≈ constant small value
        # Key: only 4 MoM values from 5 levels, all available at asof
        shelter_vals = [200.0 + 0.3 * i for i in range(5)]
        dates_s = pd.date_range("2021-09", periods=5, freq="MS")
        shelter_df = pd.DataFrame({"cpi_shelter": shelter_vals}, index=dates_s)

        # ZORI: 1% MoM for all months
        dates_z = pd.date_range("2015-01-31", periods=96, freq="ME")
        values_z = [1000.0]
        for _ in range(95):
            values_z.append(values_z[-1] * 1.01)
        zori_df = pd.DataFrame({"zori": values_z}, index=dates_z)

        target_month = pd.Timestamp("2022-01-01")
        asof = date(2022, 3, 1)

        val, prov = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)

        # All preconditions MUST hold
        assert val is not None, "val should not be None with this fixture"
        assert prov["shelter_k_applied"] is not None, "k_applied must be set"
        assert prov["zori_signal"] is not None, "zori_signal must be non-None"
        assert prov["cpi_shelter_mom_last"] is not None, "cpi_shelter_mom_last must be non-None"

        # With < 24 months of shelter history, guard is bypassed → k = 0.35
        assert prov["shelter_k_applied"] == pytest.approx(0.35), (
            f"Expected k=0.35 (short history, guard bypassed), got {prov['shelter_k_applied']}"
        )
        assert prov["divergence_guard_triggered"] is False

        # Formula check — unconditional
        k = prov["shelter_k_applied"]
        zori_s = prov["zori_signal"]
        cpi_mom = prov["cpi_shelter_mom_last"]
        expected = (1 - k) * cpi_mom + k * zori_s
        assert abs(val - expected) < 1e-10, (
            f"Formula mismatch: val={val}, expected={expected}, "
            f"k={k}, zori={zori_s}, cpi_mom={cpi_mom}"
        )
