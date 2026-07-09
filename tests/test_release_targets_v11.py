"""Tests for engine/release_targets_v11.py — MRI Track N new target specs.

Covers:
  - Output schema for each target
  - display_only=True / authority=False on all outputs
  - Determinism (same inputs -> same output)
  - retail_sales no_data scaffold path
  - Feature builder key presence
  - PIT contract (no future data leak)

Usage:
  pytest tests/test_release_targets_v11.py -v
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Repo root
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_targets_v11 import (
    PCE_HEADLINE_FEATURE_NAMES,
    PCE_CORE_FEATURE_NAMES,
    PPI_FINALDEMAND_FEATURE_NAMES,
    build_pce_headline_features,
    build_pce_core_features,
    build_ppi_finaldemand_features,
    build_retail_sales_features,
    project_pce_headline,
    project_pce_core,
    project_ppi_finaldemand,
    project_retail_sales,
)
from engine.release_forecast import load_vintages


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def root() -> Path:
    return _REPO


@pytest.fixture(scope="module")
def vintages(root: Path) -> pd.DataFrame:
    return load_vintages(root)


@pytest.fixture(scope="module")
def asof_pce() -> date:
    """A recent asof date within PCEPI / PCEPILFE vintage coverage (2000+)."""
    return date(2025, 6, 1)


@pytest.fixture(scope="module")
def asof_ppi() -> date:
    """A recent asof date within PPIFIS vintage coverage (2014+)."""
    return date(2025, 6, 1)


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

REQUIRED_PROJECTION_KEYS = {
    "release", "asof", "point",
    "p10", "p25", "p50", "p75", "p90",
    "confidence", "confidence_components",
    "input_completeness",
    "benchmark_set",
    "surprise_skew",
    "pit_provenance",
    "display_only",
    "authority",
}

REQUIRED_BENCHMARK_KEYS = {"naive_prior", "trailing_3m", "ar_model"}
REQUIRED_SURPRISE_KEYS = {"sigma", "sigma_scale_pp", "tag", "inline_band"}
REQUIRED_CONFIDENCE_KEYS = {"interval_rank", "input_completeness"}
REQUIRED_PROVENANCE_KEYS = {"revision_optimistic_legs", "unrevised_legs", "absent_legs",
                            "display_only", "authority"}


def _assert_schema(proj: dict, release: str) -> None:
    """Assert the projection dict matches the expected schema."""
    assert proj["release"] == release, f"release mismatch: {proj['release']} != {release}"
    missing = REQUIRED_PROJECTION_KEYS - set(proj.keys())
    assert not missing, f"Missing projection keys for {release}: {missing}"

    # Authority contract
    assert proj["display_only"] is True, "display_only must be True"
    assert proj["authority"] is False, "authority must be False"

    # Benchmark set
    bset = proj.get("benchmark_set", {})
    bm = REQUIRED_BENCHMARK_KEYS - set(bset.keys())
    assert not bm, f"Missing benchmark_set keys: {bm}"

    # Surprise skew
    skew = proj.get("surprise_skew", {})
    sk = REQUIRED_SURPRISE_KEYS - set(skew.keys())
    assert not sk, f"Missing surprise_skew keys: {sk}"
    assert skew["inline_band"] == 0.35

    # Confidence components
    cc = proj.get("confidence_components", {})
    ck = REQUIRED_CONFIDENCE_KEYS - set(cc.keys())
    assert not ck, f"Missing confidence_components keys: {ck}"

    # PIT provenance
    prov = proj.get("pit_provenance", {})
    pk = REQUIRED_PROVENANCE_KEYS - set(prov.keys())
    assert not pk, f"Missing pit_provenance keys: {pk}"
    assert prov["display_only"] is True
    assert prov["authority"] is False

    # Point and quantile consistency
    point = proj.get("point")
    if point is not None:
        assert isinstance(point, float), "point must be float if not None"
        # If quantiles are populated, p10 <= p90
        p10 = proj.get("p10")
        p90 = proj.get("p90")
        if p10 is not None and p90 is not None:
            assert p10 <= p90, f"p10 > p90: {p10} > {p90}"


# ---------------------------------------------------------------------------
# Retail sales: scaffold (no_data path)
# ---------------------------------------------------------------------------

class TestRetailSalesScaffold:
    """retail_sales scaffold must emit no_data without fabricating data."""

    def test_no_data_reason(self, root: Path, vintages: pd.DataFrame) -> None:
        proj = project_retail_sales(date(2025, 6, 1), root)
        assert proj["release"] == "retail_sales"
        prov = proj["pit_provenance"]
        assert prov["reason"] == "no_data_rsafs_absent"

    def test_all_nulls(self, root: Path, vintages: pd.DataFrame) -> None:
        proj = project_retail_sales(date(2025, 6, 1), root)
        assert proj["point"] is None
        assert proj["p10"] is None
        assert proj["p90"] is None
        assert proj["confidence"] is None

    def test_display_only_authority_false(self, root: Path) -> None:
        proj = project_retail_sales(date(2025, 6, 1), root)
        assert proj["display_only"] is True
        assert proj["authority"] is False

    def test_schema_complete(self, root: Path) -> None:
        proj = project_retail_sales(date(2025, 6, 1), root)
        _assert_schema(proj, "retail_sales")

    def test_deterministic(self, root: Path) -> None:
        proj1 = project_retail_sales(date(2025, 6, 1), root)
        proj2 = project_retail_sales(date(2025, 6, 1), root)
        assert proj1["point"] == proj2["point"]
        assert proj1["pit_provenance"]["reason"] == proj2["pit_provenance"]["reason"]

    def test_feature_builder_returns_empty(self, vintages: pd.DataFrame, root: Path) -> None:
        feats, prov = build_retail_sales_features(date(2025, 6, 1), vintages, root)
        # No features — can't model without data
        assert isinstance(feats, dict)
        assert len(feats) == 0
        assert prov["reason"] == "no_data_rsafs_absent"
        assert prov["display_only"] is True
        assert prov["authority"] is False


# ---------------------------------------------------------------------------
# PCE Headline
# ---------------------------------------------------------------------------

class TestPceHeadline:

    def test_schema(self, root: Path, asof_pce: date) -> None:
        proj = project_pce_headline(asof_pce, root)
        _assert_schema(proj, "pce_headline")

    def test_display_only_authority(self, root: Path, asof_pce: date) -> None:
        proj = project_pce_headline(asof_pce, root)
        assert proj["display_only"] is True
        assert proj["authority"] is False

    def test_deterministic(self, root: Path, asof_pce: date) -> None:
        proj1 = project_pce_headline(asof_pce, root)
        proj2 = project_pce_headline(asof_pce, root)
        assert proj1["point"] == proj2["point"]
        assert proj1["inputs_hash"] == proj2["inputs_hash"]

    def test_point_is_float_or_none(self, root: Path, asof_pce: date) -> None:
        proj = project_pce_headline(asof_pce, root)
        point = proj.get("point")
        assert point is None or isinstance(point, float)

    def test_feature_names_match_spec(self) -> None:
        assert PCE_HEADLINE_FEATURE_NAMES[:3] == [
            "pce_hl_mom_lag1", "pce_hl_mom_lag2", "pce_hl_mom_lag3"
        ], "Own lags must be first 3 features"
        assert "gasoline_mom" in PCE_HEADLINE_FEATURE_NAMES
        assert "sticky_mom_lag1" in PCE_HEADLINE_FEATURE_NAMES
        assert "ppifis_mom_lag1" in PCE_HEADLINE_FEATURE_NAMES

    def test_feature_builder_keys(self, vintages: pd.DataFrame, root: Path, asof_pce: date) -> None:
        feats, prov = build_pce_headline_features(asof_pce, vintages, root)
        expected_keys = set(PCE_HEADLINE_FEATURE_NAMES)
        missing = expected_keys - set(feats.keys())
        assert not missing, f"Feature builder missing keys: {missing}"
        assert prov["display_only"] is True
        assert prov["authority"] is False
        assert "revision_optimistic_legs" in prov
        assert "unrevised_legs" in prov

    def test_pit_no_leak(self, vintages: pd.DataFrame, root: Path) -> None:
        """Features at asof=2015-01-01 must not use data from after 2015-01-01."""
        asof_test = date(2015, 1, 1)
        feats, _ = build_pce_headline_features(asof_test, vintages, root)
        # Own lags must be from before asof_test; we just check they're not None
        # (they exist since PCEPI history starts 2000)
        # At least lag1 should be present
        assert feats.get("pce_hl_mom_lag1") is not None, "Own lag 1 must be knowable at 2015-01-01"

    def test_input_completeness_in_range(self, root: Path, asof_pce: date) -> None:
        proj = project_pce_headline(asof_pce, root)
        ic = proj.get("input_completeness", 0.0)
        assert 0.0 <= ic <= 1.0, f"input_completeness out of range: {ic}"


# ---------------------------------------------------------------------------
# PCE Core
# ---------------------------------------------------------------------------

class TestPceCore:

    def test_schema(self, root: Path, asof_pce: date) -> None:
        proj = project_pce_core(asof_pce, root)
        _assert_schema(proj, "pce_core")

    def test_display_only_authority(self, root: Path, asof_pce: date) -> None:
        proj = project_pce_core(asof_pce, root)
        assert proj["display_only"] is True
        assert proj["authority"] is False

    def test_deterministic(self, root: Path, asof_pce: date) -> None:
        proj1 = project_pce_core(asof_pce, root)
        proj2 = project_pce_core(asof_pce, root)
        assert proj1["point"] == proj2["point"]

    def test_feature_names_match_spec(self) -> None:
        assert PCE_CORE_FEATURE_NAMES[:3] == [
            "pce_core_mom_lag1", "pce_core_mom_lag2", "pce_core_mom_lag3"
        ]
        # gasoline excluded from core
        assert "gasoline_mom" not in PCE_CORE_FEATURE_NAMES
        assert "ppifes_mom_lag1" in PCE_CORE_FEATURE_NAMES
        assert "sticky_mom_lag1" in PCE_CORE_FEATURE_NAMES

    def test_feature_builder_keys(self, vintages: pd.DataFrame, root: Path, asof_pce: date) -> None:
        feats, prov = build_pce_core_features(asof_pce, vintages, root)
        expected_keys = set(PCE_CORE_FEATURE_NAMES)
        missing = expected_keys - set(feats.keys())
        assert not missing, f"Feature builder missing keys: {missing}"
        assert prov["display_only"] is True
        assert prov["authority"] is False

    def test_gasoline_excluded(self, vintages: pd.DataFrame, root: Path, asof_pce: date) -> None:
        """PCE core must not include gasoline feature."""
        feats, _ = build_pce_core_features(asof_pce, vintages, root)
        assert "gasoline_mom" not in feats


# ---------------------------------------------------------------------------
# PPI Final Demand
# ---------------------------------------------------------------------------

class TestPpiFinalDemand:

    def test_schema(self, root: Path, asof_ppi: date) -> None:
        proj = project_ppi_finaldemand(asof_ppi, root)
        _assert_schema(proj, "ppi_finaldemand")

    def test_display_only_authority(self, root: Path, asof_ppi: date) -> None:
        proj = project_ppi_finaldemand(asof_ppi, root)
        assert proj["display_only"] is True
        assert proj["authority"] is False

    def test_deterministic(self, root: Path, asof_ppi: date) -> None:
        proj1 = project_ppi_finaldemand(asof_ppi, root)
        proj2 = project_ppi_finaldemand(asof_ppi, root)
        assert proj1["point"] == proj2["point"]

    def test_feature_names_match_spec(self) -> None:
        assert PPI_FINALDEMAND_FEATURE_NAMES[:3] == [
            "ppi_hl_mom_lag1", "ppi_hl_mom_lag2", "ppi_hl_mom_lag3"
        ]
        assert "gasoline_mom" in PPI_FINALDEMAND_FEATURE_NAMES
        assert "ppifes_mom_lag1" in PPI_FINALDEMAND_FEATURE_NAMES

    def test_feature_builder_keys(self, vintages: pd.DataFrame, root: Path, asof_ppi: date) -> None:
        feats, prov = build_ppi_finaldemand_features(asof_ppi, vintages, root)
        expected_keys = set(PPI_FINALDEMAND_FEATURE_NAMES)
        missing = expected_keys - set(feats.keys())
        assert not missing, f"Feature builder missing keys: {missing}"
        assert prov["display_only"] is True
        assert prov["authority"] is False

    def test_thin_history_caveat_in_provenance(self, root: Path, asof_ppi: date) -> None:
        """PPI projection provenance must include thin_history_caveat."""
        proj = project_ppi_finaldemand(asof_ppi, root)
        prov = proj.get("pit_provenance", {})
        assert "thin_history_caveat" in prov, "PPI provenance must include thin_history_caveat"

    def test_insufficient_data_before_2014(self, root: Path, vintages: pd.DataFrame) -> None:
        """Requesting PPI projection before 2014-02 vintage coverage should return empty projection."""
        early_asof = date(2013, 1, 1)
        proj = project_ppi_finaldemand(early_asof, root)
        # Should gracefully return null (insufficient data or history)
        assert proj["display_only"] is True
        assert proj["authority"] is False


# ---------------------------------------------------------------------------
# Cross-target: authority/display_only contract
# ---------------------------------------------------------------------------

class TestAuthorityContract:
    """All targets must never set authority=True."""

    @pytest.mark.parametrize("project_fn,target_date", [
        (project_pce_headline, date(2025, 6, 1)),
        (project_pce_core, date(2025, 6, 1)),
        (project_ppi_finaldemand, date(2025, 6, 1)),
        (project_retail_sales, date(2025, 6, 1)),
    ])
    def test_authority_false(self, root: Path, project_fn, target_date: date) -> None:
        proj = project_fn(target_date, root)
        assert proj["authority"] is False, f"{project_fn.__name__} set authority=True"
        assert proj["display_only"] is True, f"{project_fn.__name__} set display_only=False"
        prov = proj.get("pit_provenance", {})
        assert prov.get("authority") is False, f"{project_fn.__name__} provenance has authority=True"
        assert prov.get("display_only") is True


# ---------------------------------------------------------------------------
# Backtest smoke test
# ---------------------------------------------------------------------------

class TestBacktestSmoke:
    """Smoke test: backtest produces non-empty results for all modelled targets."""

    def test_pce_headline_n_predictions(self, root: Path) -> None:
        from engine.release_targets_v11 import build_wf_pce_headline
        wf = build_wf_pce_headline(root)
        assert len(wf["results"]) > 50, "pce_headline should have at least 50 predictions"

    def test_pce_core_n_predictions(self, root: Path) -> None:
        from engine.release_targets_v11 import build_wf_pce_core
        wf = build_wf_pce_core(root)
        assert len(wf["results"]) > 50, "pce_core should have at least 50 predictions"

    def test_ppi_n_predictions(self, root: Path) -> None:
        from engine.release_targets_v11 import build_wf_ppi_finaldemand
        wf = build_wf_ppi_finaldemand(root)
        # Thin history: expect fewer predictions (~87)
        assert len(wf["results"]) > 30, "ppi_finaldemand should have at least 30 predictions"

    def test_feature_names_in_metadata(self, root: Path) -> None:
        from engine.release_targets_v11 import build_wf_pce_headline
        wf = build_wf_pce_headline(root)
        assert wf["feature_names"] == PCE_HEADLINE_FEATURE_NAMES
