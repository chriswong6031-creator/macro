"""Tests for MRI Track M v3_factor challenger.

Covers:
  - Output schema: all required keys present, display_only=True, authority=False.
  - model tag: always 'v3_factor'.
  - Determinism: calling twice returns identical results.
  - No authority: output never sets authority=True.
  - PCA-ridge: _pca_ridge_fit_predict returns a finite scalar.
  - Walk-forward: results are monotone in idx (expanding window).

These tests use synthetic fixtures — no live data required.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

# Add repo root to sys.path
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_forecast_v3 import (
    _pca_ridge_fit_predict,
    _walk_forward_v3,
    _empty_v3,
    _CPI_HL_FEATURES,
    _CPI_CORE_FEATURES,
    _NFP_FEATURES,
    RIDGE_LAMBDA,
    MIN_TRAIN_OBS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_synthetic_records(n: int, feature_names: list[str], target_scale: float = 0.1) -> list[dict]:
    """Make synthetic walk-forward records with deterministic random data."""
    rng = np.random.default_rng(42)
    records = []
    for i in range(n):
        rec: dict = {}
        for fn in feature_names:
            rec[fn] = float(rng.normal(0, 1))
        rec["target"] = float(rng.normal(0, target_scale))
        records.append(rec)
    return records


def _make_sparse_records(n: int, feature_names: list[str], null_frac: float = 0.3) -> list[dict]:
    """Records with some None values to test complete-case handling."""
    rng = np.random.default_rng(7)
    records = []
    for i in range(n):
        rec: dict = {}
        for fn in feature_names:
            if rng.random() < null_frac:
                rec[fn] = None
            else:
                rec[fn] = float(rng.normal(0, 1))
        rec["target"] = float(rng.normal(0, 0.1))
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Tests: _pca_ridge_fit_predict
# ---------------------------------------------------------------------------

class TestPcaRidgeFitPredict:
    def test_returns_finite_scalar(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(100, 5))
        y = rng.normal(size=100)
        x_pred = rng.normal(size=5)
        result = _pca_ridge_fit_predict(X, y, x_pred, n_components=3)
        assert isinstance(result, float)
        assert np.isfinite(result), f"Expected finite, got {result}"

    def test_single_feature(self):
        """With a single feature, PCA reduces to 1 factor."""
        rng = np.random.default_rng(1)
        X = rng.normal(size=(80, 1))
        y = rng.normal(size=80)
        x_pred = rng.normal(size=1)
        result = _pca_ridge_fit_predict(X, y, x_pred, n_components=3)
        assert np.isfinite(result)

    def test_deterministic(self):
        """Same inputs produce same output."""
        rng = np.random.default_rng(99)
        X = rng.normal(size=(70, 4))
        y = rng.normal(size=70)
        x_pred = rng.normal(size=4)
        r1 = _pca_ridge_fit_predict(X, y, x_pred)
        r2 = _pca_ridge_fit_predict(X, y, x_pred)
        assert r1 == r2

    def test_fewer_samples_than_features(self):
        """Should not crash when m < p."""
        rng = np.random.default_rng(3)
        X = rng.normal(size=(10, 20))
        y = rng.normal(size=10)
        x_pred = rng.normal(size=20)
        result = _pca_ridge_fit_predict(X, y, x_pred, n_components=3)
        assert np.isfinite(result)

    def test_lambda_positive(self):
        """Verify RIDGE_LAMBDA constant is positive (frozen)."""
        assert RIDGE_LAMBDA == 1.0


# ---------------------------------------------------------------------------
# Tests: _walk_forward_v3
# ---------------------------------------------------------------------------

class TestWalkForwardV3:
    def test_min_train_obs_respected(self):
        """No predictions before MIN_TRAIN_OBS."""
        feature_names = ["f1", "f2", "f3"]
        records = _make_synthetic_records(80, feature_names)
        results = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        # First prediction should be at idx >= 60
        for r in results:
            assert r["idx"] >= 60, f"Prediction at idx={r['idx']} before min_obs=60"

    def test_expanding_window_monotone(self):
        """idx values should be strictly increasing."""
        feature_names = ["f1", "f2", "f3", "f4"]
        records = _make_synthetic_records(100, feature_names)
        results = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        idxs = [r["idx"] for r in results]
        assert idxs == sorted(idxs), "idx not monotone increasing"

    def test_result_pos_sequential(self):
        """result_pos values should be 0, 1, 2, ..."""
        feature_names = ["f1", "f2"]
        records = _make_synthetic_records(90, feature_names)
        results = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        for expected_pos, r in enumerate(results):
            assert r["result_pos"] == expected_pos

    def test_sparse_features_no_crash(self):
        """Complete-case with nulls should not crash."""
        feature_names = ["f1", "f2", "f3", "f4"]
        records = _make_sparse_records(120, feature_names, null_frac=0.4)
        results = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        # Should produce some predictions (exact n depends on complete-case)
        assert isinstance(results, list)
        for r in results:
            assert np.isfinite(r["predicted"]), f"Non-finite prediction: {r['predicted']}"
            assert np.isfinite(r["actual"])

    def test_all_keys_present(self):
        """Each result dict has required keys."""
        required_keys = {
            "idx", "result_pos", "predicted", "actual",
            "baseline_naive", "baseline_trailing3m", "baseline_ar3",
            "n_train", "n_features_used", "input_completeness",
        }
        feature_names = ["f1", "f2", "f3"]
        records = _make_synthetic_records(80, feature_names)
        results = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        assert len(results) > 0, "Expected at least one prediction"
        for r in results:
            missing = required_keys - set(r.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_deterministic(self):
        """Same records produce same results."""
        feature_names = ["f1", "f2", "f3"]
        records = _make_synthetic_records(80, feature_names)
        r1 = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        r2 = _walk_forward_v3(records, feature_names, "target", min_obs=60)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a["predicted"] == b["predicted"]


# ---------------------------------------------------------------------------
# Tests: _empty_v3 schema
# ---------------------------------------------------------------------------

class TestEmptyV3Schema:
    def _check_schema(self, result: dict, release: str):
        assert result["display_only"] is True
        assert result["authority"] is False
        assert result["model"] == "v3_factor"
        assert result["release"] == release
        assert result["point"] is None
        for k in ("p10", "p25", "p50", "p75", "p90"):
            assert result[k] is None
        assert "benchmark_set" in result
        assert "surprise_skew" in result
        assert "pit_provenance" in result
        assert result["pit_provenance"]["display_only"] is True
        assert result["pit_provenance"]["authority"] is False

    def test_cpi_headline_schema(self):
        r = _empty_v3("cpi_headline", date(2026, 7, 1), "test_reason")
        self._check_schema(r, "cpi_headline")

    def test_cpi_core_schema(self):
        r = _empty_v3("cpi_core", date(2026, 7, 1), "test_reason")
        self._check_schema(r, "cpi_core")

    def test_nfp_schema(self):
        r = _empty_v3("nfp", date(2026, 7, 1), "test_reason")
        self._check_schema(r, "nfp")


# ---------------------------------------------------------------------------
# Tests: feature name lists (frozen spec verification)
# ---------------------------------------------------------------------------

class TestFeatureNameLists:
    def test_cpi_hl_own_lags_first(self):
        """First 3 features must be own CPI headline lags (AR3 baseline contract)."""
        assert _CPI_HL_FEATURES[0] == "cpi_hl_mom_lag1"
        assert _CPI_HL_FEATURES[1] == "cpi_hl_mom_lag2"
        assert _CPI_HL_FEATURES[2] == "cpi_hl_mom_lag3"

    def test_cpi_core_own_lags_first(self):
        assert _CPI_CORE_FEATURES[0] == "cpi_core_mom_lag1"
        assert _CPI_CORE_FEATURES[1] == "cpi_core_mom_lag2"
        assert _CPI_CORE_FEATURES[2] == "cpi_core_mom_lag3"

    def test_nfp_own_lags_first(self):
        assert _NFP_FEATURES[0] == "nfp_change_lag1"
        assert _NFP_FEATURES[1] == "nfp_change_lag2"
        assert _NFP_FEATURES[2] == "nfp_change_lag3"

    def test_cpi_hl_has_gasoline_not_core(self):
        """Gasoline in headline, not in core (per spec)."""
        assert "gasoline_mom" in _CPI_HL_FEATURES
        assert "gasoline_mom" not in _CPI_CORE_FEATURES

    def test_cpi_hl_has_v3_legs(self):
        """v3-specific legs present in CPI headline."""
        assert "ppi_fes_mom_lag1" in _CPI_HL_FEATURES
        assert "dollar_mom" in _CPI_HL_FEATURES

    def test_cpi_core_has_v3_legs(self):
        assert "ppi_fes_mom_lag1" in _CPI_CORE_FEATURES
        assert "dollar_mom" in _CPI_CORE_FEATURES

    def test_nfp_has_v3_legs(self):
        assert "adp_change" in _NFP_FEATURES
        assert "dollar_mom" in _NFP_FEATURES

    def test_expinf_excluded(self):
        """EXPINF / breakeven series must be excluded."""
        for name_list in (_CPI_HL_FEATURES, _CPI_CORE_FEATURES, _NFP_FEATURES):
            for fn in name_list:
                fn_lower = fn.lower()
                assert "expinf" not in fn_lower, f"EXPINF found in features: {fn}"
                assert "breakeven" not in fn_lower, f"Breakeven found: {fn}"
                assert "t5y" not in fn_lower
                assert "t10y" not in fn_lower
                assert "mich" not in fn_lower


# ---------------------------------------------------------------------------
# Tests: authority/display_only contract
# ---------------------------------------------------------------------------

class TestAuthorityContract:
    def test_empty_v3_never_authority(self):
        """Empty projection must never set authority=True."""
        for release in ("cpi_headline", "cpi_core", "nfp"):
            r = _empty_v3(release, date(2026, 1, 1), "test")
            assert r.get("authority") is False
            assert r.get("display_only") is True

    def test_constants_frozen(self):
        """Verify key constants match prereg spec."""
        assert MIN_TRAIN_OBS == 60
        assert RIDGE_LAMBDA == 1.0
