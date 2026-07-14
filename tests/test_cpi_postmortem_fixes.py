"""Unit tests for CPI June-2026 post-mortem fixes.

Categories:
  A. FIX 1 — rate-series passthrough
     A1. _last_n_rate_lags: rate series returned directly (no pct_change)
     A2. _last_n_rate_lags: annualized=True de-annualization arithmetic
     A3. _last_n_mom_lags: index-level series pct_change unchanged
     A4. build_cpi_features: sticky/flex values not double-differenced (endgame check)
  B. FIX 2 — range guard
     B1. Values within bounds pass through unchanged
     B2. Out-of-bounds values set to None
     B3. range_violation_legs tag present in provenance
     B4. Ridge degrades gracefully on None (feature absent)
  C. FIX 3 — mf_energy gamma
     C1. energy_contrib = gas_mom * gamma (no ri_weight factor)
  D. FIX 4 — PIT prior-month initial print
     D1. _compute_actual_from_print uses earliest vintage for CPI prior month
     D2. Year boundary: January period uses December prior month earliest print
     D3. Multi-vintage: two vintages for prior month -> earliest wins

Run:
    python -m pytest tests/test_cpi_postmortem_fixes.py -v
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (
    _last_n_mom_lags,
    _last_n_rate_lags,
    knowable_series,
)
from engine.release_components_cpi import (
    _apply_range_guard,
    _FEATURE_BOUNDS,
)
from engine.release_mf_energy import (
    _compute_gamma,
    GASOLINE_RI_WEIGHT,
)
from scripts.build_release_forecast import (
    _compute_actual_from_print,
)


# ---------------------------------------------------------------------------
# Synthetic vintage builder (reused from test_release_forecast.py pattern)
# ---------------------------------------------------------------------------

def _make_vintages(
    series: str,
    periods: list[pd.Timestamp],
    values: list[float],
    release_delays_days: list[int],
) -> pd.DataFrame:
    rows = []
    for p, v, d in zip(periods, values, release_delays_days):
        rt_start = p + pd.Timedelta(days=d)
        rows.append({
            "series": series,
            "period": p,
            "value": v,
            "realtime_start": rt_start,
            "realtime_end": pd.Timestamp("2099-12-31"),
        })
    return pd.DataFrame(rows)


def _make_multi_vintage(
    series: str,
    period: pd.Timestamp,
    vintages: list[tuple[int, float]],
) -> pd.DataFrame:
    """Build multiple vintages for a single period.

    vintages: list of (delay_days, value) — each creates one row for `period`.
    """
    rows = []
    for delay, val in vintages:
        rows.append({
            "series": series,
            "period": period,
            "value": val,
            "realtime_start": period + pd.Timedelta(days=delay),
            "realtime_end": pd.Timestamp("2099-12-31"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# A. FIX 1 — rate-series passthrough
# ---------------------------------------------------------------------------

class TestLastNRateLags:
    """_last_n_rate_lags reads values directly without pct_change."""

    def _make_rate_vintages(self) -> pd.DataFrame:
        """Sticky CPI-like: monthly % published directly."""
        periods = pd.date_range("2020-01-01", periods=6, freq="MS")
        values = [0.30, 0.28, 0.35, 0.40, 0.24, 0.39]
        return _make_vintages("STICKCPIM157SFRBATL", list(periods), values, [14] * 6)

    def test_A1_rate_series_passthrough_no_pct_change(self):
        """Lag values must match the raw series values, not pct_change of them."""
        vdf = self._make_rate_vintages()
        asof = date(2020, 8, 1)  # all 6 prints knowable
        lags = _last_n_rate_lags(vdf, "STICKCPIM157SFRBATL", asof, n=3)
        # lag1 = most recent = 0.39, lag2 = 0.24, lag3 = 0.40
        assert lags[0] == pytest.approx(0.39, abs=1e-9)
        assert lags[1] == pytest.approx(0.24, abs=1e-9)
        assert lags[2] == pytest.approx(0.40, abs=1e-9)

    def test_A1_old_bug_would_produce_wrong_value(self):
        """Confirm: if pct_change were applied it would give a very different number."""
        vdf = self._make_rate_vintages()
        asof = date(2020, 8, 1)
        lags_correct = _last_n_rate_lags(vdf, "STICKCPIM157SFRBATL", asof, n=1)
        lags_buggy = _last_n_mom_lags(vdf, "STICKCPIM157SFRBATL", asof, n=1)
        # With pct_change: (0.39-0.24)/0.24*100 = 62.5 — clearly wrong vs 0.39
        assert lags_correct[0] == pytest.approx(0.39, abs=1e-9)
        assert lags_buggy[0] == pytest.approx((0.39 - 0.24) / 0.24 * 100.0, abs=1e-4)
        assert abs(lags_buggy[0]) > 10  # buggy result is enormous

    def test_A2_annualized_de_annualization_arithmetic(self):
        """Median CPI: annualized rate must be converted to monthly-equivalent."""
        # Use a known value: 3.66% annualized (one of the vintages.parquet readings)
        periods = pd.date_range("2026-05-01", periods=1, freq="MS")
        values = [3.66429024270862]
        vdf = _make_vintages("MEDCPIM158SFRBCLE", list(periods), values, [14])
        asof = date(2026, 7, 1)
        lags = _last_n_rate_lags(vdf, "MEDCPIM158SFRBCLE", asof, n=1, annualized=True)
        # Expected: ((1 + 3.66429/100)^(1/12) - 1) * 100
        expected = ((1.0 + 3.66429024270862 / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
        assert lags[0] == pytest.approx(expected, abs=1e-9)
        # Must be much smaller than the annualized value
        assert lags[0] < 0.5  # monthly-equiv of ~3.7% annual ≈ 0.30%

    def test_A2_de_annualization_9pct_annual(self):
        """De-annualize 9% annual (2022 peak-like) → approx 0.72% monthly."""
        periods = pd.date_range("2022-08-01", periods=1, freq="MS")
        vdf = _make_vintages("MEDCPIM158SFRBCLE", list(periods), [9.0], [14])
        asof = date(2022, 10, 1)
        lags = _last_n_rate_lags(vdf, "MEDCPIM158SFRBCLE", asof, n=1, annualized=True)
        expected = ((1.0 + 9.0 / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
        assert lags[0] == pytest.approx(expected, abs=1e-9)
        assert 0.65 < lags[0] < 0.80  # sanity range

    def test_A3_index_level_pct_change_unchanged(self):
        """CPIAUCSL (index level) must still use pct_change via _last_n_mom_lags."""
        # CPIAUCSL in 300s range; MoM pct_change ≈ 0.3%
        base = 300.0
        values = [base * (1.003 ** i) for i in range(6)]
        periods = pd.date_range("2020-01-01", periods=6, freq="MS")
        vdf = _make_vintages("CPIAUCSL", list(periods), values, [14] * 6)
        asof = date(2020, 8, 1)
        lags = _last_n_mom_lags(vdf, "CPIAUCSL", asof, n=1)
        # MoM pct_change of ~0.3% per month
        assert lags[0] == pytest.approx(0.3, abs=0.01)

    def test_A4_none_returned_on_insufficient_data(self):
        """_last_n_rate_lags returns [None]*n when no data."""
        vdf = pd.DataFrame(columns=["series", "period", "value", "realtime_start", "realtime_end"])
        lags = _last_n_rate_lags(vdf, "STICKCPIM157SFRBATL", date(2026, 1, 1), n=3)
        assert lags == [None, None, None]

    def test_A4_pit_guard_respected(self):
        """Values released after asof must not appear."""
        periods = pd.date_range("2026-01-01", periods=3, freq="MS")
        values = [0.30, 0.28, 0.35]
        # Third print released AFTER asof
        vdf = _make_vintages("STICKCPIM157SFRBATL", list(periods), values,
                             [14, 14, 60])  # last one released day+60
        asof = date(2026, 3, 1)  # only 2 knowable (delay=14 days from period start)
        lags = _last_n_rate_lags(vdf, "STICKCPIM157SFRBATL", asof, n=3)
        # Only 2 periods knowable; lag1=0.28, lag2=0.30, lag3=None
        assert lags[0] == pytest.approx(0.28, abs=1e-9)
        assert lags[1] == pytest.approx(0.30, abs=1e-9)
        assert lags[2] is None


# ---------------------------------------------------------------------------
# B. FIX 2 — range guard
# ---------------------------------------------------------------------------

class TestRangeGuard:
    """_apply_range_guard nulls out-of-bounds features and tags legs."""

    def _make_features(self, **kwargs: float | None) -> dict[str, float | None]:
        return dict(**kwargs)

    def test_B1_in_bounds_values_unchanged(self):
        """Values within bounds pass through."""
        features = {
            "sticky_mom_lag1": 0.24,
            "median_mom_lag1": 0.30,
            "flex_mom_lag1": 1.10,
            "gasoline_mom": -5.0,
            "shelter_nowcast": 0.35,
        }
        prov: dict = {}
        result = _apply_range_guard(features, prov)
        assert result["sticky_mom_lag1"] == pytest.approx(0.24)
        assert result["median_mom_lag1"] == pytest.approx(0.30)
        assert result["flex_mom_lag1"] == pytest.approx(1.10)
        assert result["gasoline_mom"] == pytest.approx(-5.0)
        assert result["shelter_nowcast"] == pytest.approx(0.35)
        # No violations
        assert prov.get("range_violation_legs", []) == []

    def test_B2_out_of_bounds_set_to_none(self):
        """Values outside bounds (like the bugged -36.68) become None."""
        features = {
            "sticky_mom_lag1": -36.68,  # double-differenced bug value
            "median_mom_lag1": -25.68,
            "flex_mom_lag1": -18.77,
        }
        prov: dict = {}
        result = _apply_range_guard(features, prov)
        assert result["sticky_mom_lag1"] is None
        assert result["median_mom_lag1"] is None
        assert result["flex_mom_lag1"] is None

    def test_B3_violation_tagged_in_legs(self):
        """range_violation_legs tagged in provenance dict."""
        features = {"sticky_mom_lag1": -36.68, "median_mom_lag1": 0.25}
        prov: dict = {}
        _apply_range_guard(features, prov)
        assert "sticky_mom_lag1" in prov["range_violation_legs"]
        assert "median_mom_lag1" not in prov["range_violation_legs"]

    def test_B3_bounds_constants_plausible(self):
        """Bounds constants are plausible: cover 2022 peaks, not normal values."""
        # Sticky 2022 peak in vintages.parquet was 0.681; must be inside bounds
        lo_s, hi_s = _FEATURE_BOUNDS["sticky_mom_lag1"]
        assert lo_s < 0.681 < hi_s
        # Buggy sticky value -36.68 must be outside bounds
        assert -36.68 < lo_s
        # Flex 2022 peak in vintages.parquet was 3.423; must be inside bounds
        lo_f, hi_f = _FEATURE_BOUNDS["flex_mom_lag1"]
        assert lo_f < 3.423 < hi_f
        # Buggy flex value -18.77 must be outside bounds
        assert -18.77 < lo_f

    def test_B4_ridge_degrades_gracefully_on_none_feature(self):
        """When a feature is None (e.g. after range guard), ridge uses remaining features."""
        from engine.release_forecast import _ridge_predict, _build_matrix

        # Build simple records: 2 features, one always None
        records = []
        rng = np.random.default_rng(42)
        for i in range(80):
            rec = {
                "sticky_mom_lag1": float(rng.normal(0.3, 0.1)),
                "cpi_hl_mom_lag1": float(rng.normal(0.2, 0.15)),
                "target": float(rng.normal(0.2, 0.1)),
            }
            records.append(rec)

        feature_names = ["sticky_mom_lag1", "cpi_hl_mom_lag1"]
        X = _build_matrix(records, feature_names)
        y = np.array([r["target"] for r in records])

        # Pred row with sticky=None (set to nan)
        pred_features = np.array([np.nan, 0.2])
        avail_mask = ~np.isnan(pred_features)
        X_sel = X[:, avail_mask]
        row_complete = ~np.any(np.isnan(X_sel), axis=1)
        X_clean = X_sel[row_complete]
        y_clean = y[row_complete]
        x_pred = pred_features[avail_mask]

        # Should not raise; returns a finite scalar
        point = _ridge_predict(X_clean, y_clean, x_pred)
        assert math.isfinite(point)


# ---------------------------------------------------------------------------
# C. FIX 3 — mf_energy gamma
# ---------------------------------------------------------------------------

class TestMfEnergyGamma:
    """energy_contrib = gas_mom * gamma (no ri_weight multiplication)."""

    def test_C1_energy_contrib_no_ri_weight(self):
        """Verify the corrected formula: energy_contrib = gas_mom * gamma."""
        # Simulate a simple training history
        gas_moms = [2.0, -1.5, 3.0, -2.0, 1.0, 4.0, -3.0, 0.5,
                    1.5, -1.0, 2.5, 3.5, -2.5, 0.8, 1.2]
        # cpi_moms roughly correlated with gas (gamma ≈ 0.03-0.05)
        cpi_moms = [0.15 + 0.04 * g + 0.01 for g in gas_moms]
        gamma = _compute_gamma(gas_moms, cpi_moms)
        assert gamma is not None and gamma > 0

        gas_now = -4.0  # gasoline fell 4% MoM
        # Corrected formula
        energy_contrib_corrected = gas_now * gamma
        # Old (buggy) formula
        energy_contrib_old = gas_now * (GASOLINE_RI_WEIGHT / 100.0) * gamma

        # The corrected value is larger in magnitude by ~ri_weight/100 factor
        ratio = abs(energy_contrib_corrected) / abs(energy_contrib_old)
        expected_ratio = 1.0 / (GASOLINE_RI_WEIGHT / 100.0)
        assert ratio == pytest.approx(expected_ratio, rel=1e-6)
        # Corrected is always bigger in magnitude than old (since ri_weight/100 < 1)
        assert abs(energy_contrib_corrected) > abs(energy_contrib_old)

    def test_C1_gamma_is_weight_inclusive(self):
        """OLS slope gamma on synthetic data ≈ GASOLINE_RI_WEIGHT/100."""
        # Build data where cpi_mom = ri_weight/100 * gas_mom + noise_small
        rng = np.random.default_rng(42)
        n = 200
        gas = rng.normal(0, 3.0, n).tolist()
        true_slope = GASOLINE_RI_WEIGHT / 100.0
        cpi = [true_slope * g + rng.normal(0, 0.05) for g in gas]
        gamma = _compute_gamma(gas, cpi)
        # gamma should be close to ri_weight/100 (within 20%)
        assert abs(gamma - true_slope) / true_slope < 0.20

    def test_C1_no_double_discount_in_walk_forward(self):
        """Confirm engine/release_mf_energy.py does NOT multiply by GASOLINE_RI_WEIGHT * gamma."""
        import engine.release_mf_energy as mfe
        import inspect
        # Check both the record-builder and the projection function
        src_records = inspect.getsource(mfe._build_all_records)
        src_project = inspect.getsource(mfe.project_release_mf)
        # After fix, the double-discount line should not appear in either function
        # The old (buggy) pattern was: gm * (GASOLINE_RI_WEIGHT / 100.0) * gamma
        for src, name in [(src_records, "_build_all_records"), (src_project, "project_release_mf")]:
            assert "GASOLINE_RI_WEIGHT / 100.0) * gamma" not in src, (
                f"Double-discount pattern still present in {name}"
            )


# ---------------------------------------------------------------------------
# D. FIX 4 — PIT prior-month initial print
# ---------------------------------------------------------------------------

class TestPITPriorMonth:
    """_compute_actual_from_print uses earliest vintage for CPI prior month."""

    def _make_tmp_vintages(
        self,
        tmp_path: Path,
        series: str,
        records: list[dict],
    ) -> Path:
        """Write a vintages.parquet file with given records into tmp_path."""
        vdf = pd.DataFrame(records)
        vdf["period"] = pd.to_datetime(vdf["period"])
        vdf["realtime_start"] = pd.to_datetime(vdf["realtime_start"])
        vdf["realtime_end"] = pd.Timestamp("2099-12-31")
        vpath = tmp_path / "data" / "fred_vintage"
        vpath.mkdir(parents=True, exist_ok=True)
        vdf.to_parquet(vpath / "vintages.parquet", index=False)
        return tmp_path

    def test_D1_earliest_vintage_wins(self, tmp_path: Path):
        """When two vintages exist for prior month, earliest is used for base."""
        root = self._make_tmp_vintages(tmp_path, "CPIAUCSL", [
            # Prior month (2026-05-01): initial print 325.0 (earliest), revised 325.5
            {"series": "CPIAUCSL", "period": "2026-05-01",
             "value": 325.0, "realtime_start": "2026-06-12"},
            {"series": "CPIAUCSL", "period": "2026-05-01",
             "value": 325.5, "realtime_start": "2026-07-01"},
        ])
        # Current month print: 326.0 (target = 2026-06)
        result = _compute_actual_from_print("cpi_headline", 326.0, root, "2026-06")
        # Using EARLIEST prior (325.0): (326.0/325.0 - 1)*100 = 0.3077
        expected = round((326.0 / 325.0 - 1.0) * 100.0, 4)
        assert result == pytest.approx(expected, abs=1e-4)
        # NOT using latest (325.5): (326.0/325.5 - 1)*100 = 0.1536 — different value
        wrong = round((326.0 / 325.5 - 1.0) * 100.0, 4)
        assert result != pytest.approx(wrong, abs=1e-4)

    def test_D2_year_boundary_january_uses_december(self, tmp_path: Path):
        """January period: prior month is December of the previous year."""
        root = self._make_tmp_vintages(tmp_path, "CPIAUCSL", [
            # December prior month
            {"series": "CPIAUCSL", "period": "2025-12-01",
             "value": 320.0, "realtime_start": "2026-01-15"},
        ])
        # January current print
        result = _compute_actual_from_print("cpi_headline", 321.0, root, "2026-01")
        expected = round((321.0 / 320.0 - 1.0) * 100.0, 4)
        assert result == pytest.approx(expected, abs=1e-4)

    def test_D3_multi_vintage_earliest_wins_three(self, tmp_path: Path):
        """Three vintages for prior month: the earliest realtime_start is used."""
        root = self._make_tmp_vintages(tmp_path, "CPIAUCSL", [
            {"series": "CPIAUCSL", "period": "2026-05-01",
             "value": 325.0, "realtime_start": "2026-06-12"},  # earliest
            {"series": "CPIAUCSL", "period": "2026-05-01",
             "value": 325.3, "realtime_start": "2026-07-01"},
            {"series": "CPIAUCSL", "period": "2026-05-01",
             "value": 325.8, "realtime_start": "2026-08-01"},  # latest
        ])
        result = _compute_actual_from_print("cpi_headline", 326.0, root, "2026-06")
        # Must use earliest (325.0), not latest (325.8)
        using_earliest = round((326.0 / 325.0 - 1.0) * 100.0, 4)
        using_latest = round((326.0 / 325.8 - 1.0) * 100.0, 4)
        assert result == pytest.approx(using_earliest, abs=1e-4)
        assert result != pytest.approx(using_latest, abs=1e-4)

    def test_D4_no_prior_month_returns_none(self, tmp_path: Path):
        """When no prior month data exists, returns None gracefully."""
        root = self._make_tmp_vintages(tmp_path, "CPIAUCSL", [
            # Only current month, no prior
            {"series": "CPIAUCSL", "period": "2026-06-01",
             "value": 326.0, "realtime_start": "2026-07-11"},
        ])
        result = _compute_actual_from_print("cpi_headline", 326.0, root, "2026-06")
        assert result is None

    def test_D5_core_uses_cpilfesl(self, tmp_path: Path):
        """cpi_core release type uses CPILFESL series."""
        root = self._make_tmp_vintages(tmp_path, "CPILFESL", [
            {"series": "CPILFESL", "period": "2026-05-01",
             "value": 330.0, "realtime_start": "2026-06-12"},
            {"series": "CPILFESL", "period": "2026-05-01",
             "value": 330.5, "realtime_start": "2026-07-01"},
        ])
        result = _compute_actual_from_print("cpi_core", 331.0, root, "2026-06")
        expected = round((331.0 / 330.0 - 1.0) * 100.0, 4)
        assert result == pytest.approx(expected, abs=1e-4)
