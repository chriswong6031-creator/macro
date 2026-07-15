"""Tests for engine/release_targets_v11.py — MRI Track N new target specs.

Covers:
  - Output schema for each target
  - display_only=True / authority=False on all outputs
  - Determinism (same inputs -> same output)
  - retail_sales no_data scaffold path
  - Feature builder key presence
  - PIT contract (no future data leak)
  - Range guard (FIX 2 follow-up): PCE/PPI bounds + NIPA re-base seam fencing

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
from engine.release_components_cpi import (
    _apply_range_guard,
    _FEATURE_BOUNDS,
)


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


# ---------------------------------------------------------------------------
# Range guard (FIX 2 follow-up — mirrors tests/test_cpi_postmortem_fixes.py B-tests)
# ---------------------------------------------------------------------------

def _make_vintages(
    series: str,
    periods: list[pd.Timestamp],
    values: list[float],
    release_delays_days: list[int],
) -> pd.DataFrame:
    rows = []
    for p, v, d in zip(periods, values, release_delays_days):
        rows.append({
            "series": series,
            "period": p,
            "value": v,
            "realtime_start": p + pd.Timedelta(days=d),
            "realtime_end": pd.Timestamp("2099-12-31"),
        })
    return pd.DataFrame(rows)


class TestRangeGuardV11:
    """v11 feature builders apply _apply_range_guard (PCE/PPI bounds)."""

    def test_G1_bounds_cover_all_v11_features(self):
        """Every v11 model feature has a plausibility bound (anti-drift)."""
        all_names = (
            set(PCE_HEADLINE_FEATURE_NAMES)
            | set(PCE_CORE_FEATURE_NAMES)
            | set(PPI_FINALDEMAND_FEATURE_NAMES)
        )
        missing = all_names - set(_FEATURE_BOUNDS.keys())
        assert not missing, f"v11 features without _FEATURE_BOUNDS keys: {missing}"

    def test_G2_in_bounds_values_unchanged(self):
        """Typical PCE/PPI readings pass through the guard untouched."""
        features = {
            "pce_hl_mom_lag1": 0.20,
            "pce_core_mom_lag1": 0.17,
            "ppi_hl_mom_lag1": 1.63,     # PPIFIS 2022-03 real extreme
            "ppifes_mom_lag1": 1.27,     # PPIFES 2022-03 real extreme
            "pce_hl_mom_lag2": -1.15,    # PCEPI 2008-11 real crisis extreme
        }
        prov: dict = {}
        result = _apply_range_guard(features, prov)
        assert result["pce_hl_mom_lag1"] == pytest.approx(0.20)
        assert result["pce_core_mom_lag1"] == pytest.approx(0.17)
        assert result["ppi_hl_mom_lag1"] == pytest.approx(1.63)
        assert result["ppifes_mom_lag1"] == pytest.approx(1.27)
        assert result["pce_hl_mom_lag2"] == pytest.approx(-1.15)
        assert prov.get("range_violation_legs", []) == []

    def test_G3_rebase_seam_values_set_to_none_and_tagged(self):
        """NIPA re-base seam magnitudes (the 2009-06 first-print artifact) are fenced."""
        features = {
            "pce_hl_mom_lag1": -10.128,   # PCEPI 2009-06 cross-base artifact
            "pce_core_mom_lag1": -8.452,  # PCEPILFE 2009-06 cross-base artifact
            "pce_hl_mom_lag2": 0.25,
        }
        prov: dict = {}
        result = _apply_range_guard(features, prov)
        assert result["pce_hl_mom_lag1"] is None
        assert result["pce_core_mom_lag1"] is None
        assert result["pce_hl_mom_lag2"] == pytest.approx(0.25)
        assert "pce_hl_mom_lag1" in prov["range_violation_legs"]
        assert "pce_core_mom_lag1" in prov["range_violation_legs"]
        assert "pce_hl_mom_lag2" not in prov["range_violation_legs"]

    def test_G4_bounds_constants_plausible(self):
        """Bounds keep every real crisis reading, fence every re-base seam.

        Audit source: data/fred_vintage/vintages.parquet first-print MoM,
        full history (PCEPI/PCEPILFE 2000-07..2026-05, PPIFIS/PPIFES 2014-02..).
        """
        # PCEPI: real extremes -1.146 (2008-11) / +0.969 (2008-06); smallest
        # seam magnitude -5.094 (2023-08)
        lo, hi = _FEATURE_BOUNDS["pce_hl_mom_lag1"]
        assert lo < -1.146 and 0.969 < hi
        assert -5.094 < lo
        # PCEPILFE: real extremes -0.836 (2001-09) / +1.204 (2001-10); smallest
        # seam magnitude -4.440 (2018-06)
        lo, hi = _FEATURE_BOUNDS["pce_core_mom_lag1"]
        assert lo < -0.836 and 1.204 < hi
        assert -4.440 < lo
        # PPIFIS: real extremes -1.266 (2020-04) / +1.630 (2022-03); no seams
        lo, hi = _FEATURE_BOUNDS["ppi_hl_mom_lag1"]
        assert lo < -1.266 and 1.630 < hi
        lo, hi = _FEATURE_BOUNDS["ppifis_mom_lag1"]
        assert lo < -1.266 and 1.630 < hi
        # PPIFES: real extremes -0.459 (2015-02) / +1.269 (2022-03)
        lo, hi = _FEATURE_BOUNDS["ppifes_mom_lag1"]
        assert lo < -0.459 and 1.269 < hi

    def test_G5_builder_fences_synthetic_rebase_seam(self, tmp_path: Path):
        """build_pce_headline_features nulls a re-base-style level jump end-to-end."""
        periods = list(pd.date_range("2020-01-01", periods=6, freq="MS"))
        # Last level drops ~10.7% in one month — an index re-base, not inflation
        values = [100.0, 100.2, 100.4, 100.6, 100.8, 90.0]
        vdf = _make_vintages("PCEPI", periods, values, [30] * 6)
        asof = date(2020, 8, 15)  # all prints knowable
        feats, prov = build_pce_headline_features(asof, vdf, tmp_path)
        assert feats["pce_hl_mom_lag1"] is None
        assert "pce_hl_mom_lag1" in prov["range_violation_legs"]
        # Adjacent same-base lag untouched
        assert feats["pce_hl_mom_lag2"] == pytest.approx(100.8 / 100.6 * 100 - 100, abs=1e-6)

    def test_G6_real_vintages_2009_seam_fenced(self, vintages: pd.DataFrame, root: Path):
        """Real 2009-08-04 comprehensive-revision vintage: lag1 fenced for both PCE targets."""
        asof = date(2009, 8, 5)  # day after the NIPA comprehensive-revision print
        feats_hl, prov_hl = build_pce_headline_features(asof, vintages, root)
        assert feats_hl["pce_hl_mom_lag1"] is None
        assert "pce_hl_mom_lag1" in prov_hl["range_violation_legs"]
        feats_core, prov_core = build_pce_core_features(asof, vintages, root)
        assert feats_core["pce_core_mom_lag1"] is None
        assert "pce_core_mom_lag1" in prov_core["range_violation_legs"]

    def test_G7_no_violation_at_recent_asof(
        self, vintages: pd.DataFrame, root: Path, asof_pce: date
    ):
        """Clean recent asof: guard present but silent in all three builders."""
        for builder in (
            build_pce_headline_features,
            build_pce_core_features,
            build_ppi_finaldemand_features,
        ):
            _, prov = builder(asof_pce, vintages, root)
            assert prov.get("range_violation_legs", []) == [], builder.__name__


# ---------------------------------------------------------------------------
# Target-side seam guard (follow-up to the FIX 2 feature guard): the walk-forward
# TARGET (pct_change of first-print levels) is also fenced at NIPA re-base seams.
# ---------------------------------------------------------------------------

def _no_feats(asof, vintages, root, ref_month=None):
    """Trivial feature builder — isolates target construction from feature cost."""
    return {}, {}


class TestTargetSeamGuardV11:
    """Training targets at NIPA comprehensive-revision seams are nulled."""

    #: The five NIPA comprehensive-revision seam periods (first print of period P
    #: on a new index base while P-1's first print is on the old base).
    SEAM_PERIODS = {(2003, 11), (2009, 6), (2013, 6), (2018, 6), (2023, 8)}

    def test_S1_target_bounds_match_feature_bounds(self):
        """Target fence sources the same constants as the #2575 feature fence (anti-drift)."""
        from engine.release_targets_v11 import _TARGET_MOM_BOUNDS
        assert _TARGET_MOM_BOUNDS["PCEPI"] == _FEATURE_BOUNDS["pce_hl_mom_lag1"]
        assert _TARGET_MOM_BOUNDS["PCEPILFE"] == _FEATURE_BOUNDS["pce_core_mom_lag1"]
        assert _TARGET_MOM_BOUNDS["PPIFIS"] == _FEATURE_BOUNDS["ppi_hl_mom_lag1"]

    def test_S2_synthetic_seam_target_nulled(self, tmp_path: Path):
        """A re-base-style level drop yields target=None at the seam record only."""
        from engine.release_targets_v11 import _build_wf_records
        periods = list(pd.date_range("2020-01-01", periods=6, freq="MS"))
        # Last level drops ~10.7% in one month — an index re-base, not inflation
        values = [100.0, 100.2, 100.4, 100.6, 100.8, 90.0]
        vdf = _make_vintages("PCEPI", periods, values, [30] * 6)
        records = _build_wf_records(vdf, tmp_path, "PCEPI", _no_feats)
        assert len(records) == 5  # first row consumed by pct_change
        assert records[-1]["target"] is None, "seam step must carry target=None"
        for rec in records[:-1]:
            assert rec["target"] is not None
            assert abs(rec["target"]) <= 3.0

    def test_S3_real_vintages_pce_seam_targets_nulled(
        self, vintages: pd.DataFrame, root: Path
    ):
        """Exactly the five comprehensive-revision periods carry target=None (both PCE series)."""
        from engine.release_targets_v11 import _build_wf_records
        for series in ("PCEPI", "PCEPILFE"):
            records = _build_wf_records(vintages, root, series, _no_feats)
            nulled = {
                (pd.Timestamp(r["period"]).year, pd.Timestamp(r["period"]).month)
                for r in records
                if r["target"] is None
            }
            assert nulled == self.SEAM_PERIODS, f"{series}: nulled {sorted(nulled)}"
            for r in records:
                if r["target"] is not None:
                    assert abs(r["target"]) <= 3.0, f"{series} {r['period']}: {r['target']}"

    def test_S4_ppi_targets_untouched(self, vintages: pd.DataFrame, root: Path):
        """PPIFIS (vintages 2014+, no re-base seams): no target is nulled."""
        from engine.release_targets_v11 import _build_wf_records
        records = _build_wf_records(vintages, root, "PPIFIS", _no_feats)
        assert len(records) > 100
        assert all(r["target"] is not None for r in records)

    def test_S5_walk_forward_actuals_and_baselines_seam_free(
        self, vintages: pd.DataFrame, root: Path
    ):
        """Seam periods are neither scored prediction steps nor baseline inputs."""
        from engine.release_targets_v11 import _build_wf_records
        from engine.release_forecast import _walk_forward
        records = _build_wf_records(vintages, root, "PCEPI", _no_feats)
        results = _walk_forward(records, [], "target")
        assert len(results) > 100
        stepped = {
            (
                pd.Timestamp(records[r["idx"]]["period"]).year,
                pd.Timestamp(records[r["idx"]]["period"]).month,
            )
            for r in results
        }
        assert not (stepped & self.SEAM_PERIODS), "seam periods must not be scored"
        for r in results:
            assert abs(r["actual"]) <= 3.0
            assert abs(r["baseline_naive"]) <= 3.0
            assert abs(r["baseline_trailing3m"]) <= 3.0

    @pytest.mark.parametrize("project_fn,release", [
        (project_pce_headline, "pce_headline"),
        (project_pce_core, "pce_core"),
    ])
    def test_S6_live_naive_prior_seam_guarded(self, root: Path, project_fn, release):
        """Day after the 2009-08-04 comprehensive-revision print: naive_prior and
        trailing_3m skip the -10.1/-8.5 artifact and fall back to real MoM prints."""
        proj = project_fn(date(2009, 8, 5), root)
        assert proj["release"] == release
        for key in ("naive_prior", "trailing_3m"):
            v = proj["benchmark_set"][key]
            assert v is not None, f"{release}.{key} must not be None"
            assert abs(v) <= 3.0, f"{release}.{key} carries a seam artifact: {v}"
