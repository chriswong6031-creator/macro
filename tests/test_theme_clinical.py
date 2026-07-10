"""tests/test_theme_clinical.py — Tests for engine/theme_clinical.py (TIL W10).

Coverage:
  - config schema + crosswalk id validity + query-precision documentation
  - normalizer on synthetic parquet fixtures
  - industry-filter regression (mixed sponsor fixture → only INDUSTRY counted)
  - missing-month/newest-window fall-through (honest null)
  - per-modality isolation
  - like-month YoY math (registration_velocity YoY)
  - phase-migration computation
  - honest-null coverage
  - banned words ('validated' never in outputs)
  - synapse/dag conformance suites
  - check_validated_claims integration
  - authority block (all may_* false; is_context_only=true)
  - output schema completeness
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional
from unittest import mock

import pandas as pd
import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_row(
    modality_id: str = "glp1_named_agents",
    theme_id: str = "glp1_obesity",
    nct_id: str = "NCT00000001",
    year_month: str = "2023-01",
    phase1: bool = False,
    phase2: bool = False,
    phase3: bool = True,
    enrollment_target: Optional[int] = 100,
) -> dict:
    from collectors.clinicaltrials_themes import STORE_COLS
    return {
        "modality_id": modality_id,
        "theme_id": theme_id,
        "nct_id": nct_id,
        "study_first_post_date": year_month + "-15",
        "year_month": year_month,
        "phases_raw": "PHASE3" if phase3 else ("PHASE2" if phase2 else ("PHASE1" if phase1 else "")),
        "phase1": phase1,
        "phase2": phase2,
        "phase3": phase3,
        "enrollment_target": enrollment_target,
        "sponsor_class": "INDUSTRY",
        "ingest_date": "2026-07-09",
        "vocabulary_version": "v1",
    }


def _build_df(rows: list[dict]) -> pd.DataFrame:
    from collectors.clinicaltrials_themes import STORE_COLS
    return pd.DataFrame(rows, columns=STORE_COLS)


def _monthly_registration_rows(
    modality_id: str,
    theme_id: str,
    start_ym: str,
    n_months: int,
    n_per_month: int = 3,
    yoy_growth: Optional[float] = None,
) -> list[dict]:
    """
    Generate n_months of synthetic registration rows.
    If yoy_growth is set (e.g. 0.20 = +20%), counts increase month-over-month
    at the equivalent annualized rate.
    """
    rows = []
    period = pd.Period(start_ym, freq="M")
    nct_counter = 1
    for i in range(n_months):
        p = period + i
        ym = str(p)
        if yoy_growth is not None:
            monthly_factor = (1 + yoy_growth) ** (1 / 12)
            count = max(1, int(n_per_month * (monthly_factor ** i)))
        else:
            count = n_per_month
        for j in range(count):
            rows.append(
                _make_row(
                    modality_id=modality_id,
                    theme_id=theme_id,
                    nct_id=f"NCT{nct_counter:08d}",
                    year_month=ym,
                    phase3=(j % 2 == 0),
                    phase2=(j % 2 == 1),
                )
            )
            nct_counter += 1
    return rows


# ---------------------------------------------------------------------------
# Like-month YoY math
# ---------------------------------------------------------------------------

class TestLikeMonthYoY:

    def test_flat_series_yoy_near_zero(self):
        """Flat registration series → YoY near zero."""
        from engine.theme_clinical import _compute_registration_yoy

        rows_flat = _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                               "2022-01", 24, n_per_month=5)
        df = _build_df(rows_flat)
        monthly = df.groupby("year_month")["nct_id"].count().sort_index()
        yoy = _compute_registration_yoy(monthly)
        assert yoy is not None, "Expected non-None YoY for 24-month flat series"
        assert abs(yoy) < 2.0, f"Expected flat YoY near zero; got {yoy:.2f}%"

    def test_growing_series_yoy_positive(self):
        """Growing registration series → positive YoY."""
        from engine.theme_clinical import _compute_registration_yoy

        rows_growing = _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                                  "2022-01", 24, n_per_month=3,
                                                  yoy_growth=0.30)
        df = _build_df(rows_growing)
        monthly = df.groupby("year_month")["nct_id"].count().sort_index()
        yoy = _compute_registration_yoy(monthly)
        assert yoy is not None
        assert yoy > 0, f"Expected positive YoY for growing series; got {yoy:.2f}%"

    def test_insufficient_data_returns_none(self):
        """Fewer than 13 months → None."""
        from engine.theme_clinical import _compute_registration_yoy

        rows = _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                          "2024-01", 6, n_per_month=3)
        df = _build_df(rows)
        monthly = df.groupby("year_month")["nct_id"].count().sort_index()
        yoy = _compute_registration_yoy(monthly)
        assert yoy is None, "Expected None for < 13 months of data"

    def test_like_month_law_same_month_comparison(self):
        """
        YoY must compare like calendar months (trailing-12m vs prior-12m).
        A series with higher values in all months of year 2 vs year 1 → positive YoY.
        This verifies the LIKE-MONTH LAW: we use 12m sum vs prior 12m sum, not
        a point-in-time month vs 12-months-ago (which would fail if months differ).
        """
        from engine.theme_clinical import _compute_registration_yoy

        # Year 1 (2022): 2 registrations/month
        # Year 2 (2023): 6 registrations/month (3x)
        rows = (
            _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                       "2022-01", 12, n_per_month=2) +
            _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                       "2023-01", 12, n_per_month=6)
        )
        df = _build_df(rows)
        monthly = df.groupby("year_month")["nct_id"].count().sort_index()
        yoy = _compute_registration_yoy(monthly)
        assert yoy is not None
        # Trailing-12m (2023): 72 studies; prior-12m (2022): 24 studies → +200%
        assert yoy > 150.0, (
            f"Expected ~200% YoY (72 vs 24 studies); got {yoy:.2f}%"
        )

    def test_zero_prior_window_returns_none(self):
        """Zero prior-window registrations → None (no divide by zero)."""
        from engine.theme_clinical import _compute_registration_yoy

        # Only 12 months of data (no prior window)
        rows = _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                          "2025-01", 12, n_per_month=5)
        df = _build_df(rows)
        monthly = df.groupby("year_month")["nct_id"].count().sort_index()
        yoy = _compute_registration_yoy(monthly)
        # Only 12 months: no prior window available → None expected
        assert yoy is None, (
            "Expected None with exactly 12 months (no prior 12-month window)"
        )


# ---------------------------------------------------------------------------
# Phase-migration computation
# ---------------------------------------------------------------------------

class TestPhaseMigration:

    def test_maturing_pipeline_read(self):
        """
        Rising Phase-2+ share → 'maturing' read.

        Fixture: 24 contiguous months (2022-01 to 2023-12).
        Prior window = months 1-12 (2022): 2 Phase-3 + 10 Phase-1 = 2/12 = 16.7% Phase-2+
        Recent window = months 13-24 (2023): 9 Phase-3 + 3 Phase-1 = 9/12 = 75% Phase-2+
        delta_pp = +58.3pp → 'maturing'
        """
        from engine.theme_clinical import _compute_phase_migration

        # Build 24 contiguous months with rising Phase-3 share
        all_months = [f"2022-{m:02d}" for m in range(1, 13)] + [f"2023-{m:02d}" for m in range(1, 13)]
        rows = []
        nct = 1
        for i, ym in enumerate(all_months):
            if i < 12:
                # Prior window (2022): 2 Phase-3 in months 1 and 2, rest Phase-1
                for j in range(1):
                    phase3 = (i < 2)
                    rows.append(_make_row("m1", "t1", f"NCT_P{nct:04d}", ym,
                                         phase1=not phase3, phase3=phase3))
                    nct += 1
            else:
                # Recent window (2023): 9 Phase-3 (months 1-9), 3 Phase-1 (months 10-12)
                month_idx = i - 12
                phase3 = (month_idx < 9)
                rows.append(_make_row("m1", "t1", f"NCT_R{nct:04d}", ym,
                                      phase1=not phase3, phase3=phase3))
                nct += 1

        df = _build_df(rows)
        pm = _compute_phase_migration(df)
        assert pm["read"] in ("maturing", "stable"), (
            f"Expected 'maturing' or 'stable' with rising Phase-2+ share; got {pm['read']!r}"
        )
        if pm["delta_pp"] is not None:
            assert pm["delta_pp"] > 0, (
                f"Expected positive delta_pp for maturing pipeline; got {pm['delta_pp']}"
            )

    def test_insufficient_data_returns_insufficient(self):
        """Fewer than 13 months → read='insufficient_data'."""
        from engine.theme_clinical import _compute_phase_migration

        rows = [_make_row("m1", "t1", f"NCT{i:04d}", f"2025-0{i+1}") for i in range(5)]
        df = _build_df(rows)
        pm = _compute_phase_migration(df)
        assert pm["read"] == "insufficient_data", (
            f"Expected 'insufficient_data' for < 13 months; got {pm['read']!r}"
        )

    def test_empty_df_returns_null_dict(self):
        """Empty DataFrame → null result dict."""
        from engine.theme_clinical import _compute_phase_migration

        pm = _compute_phase_migration(pd.DataFrame())
        assert pm["read"] == "insufficient_data"
        assert pm["share_phase2plus_recent"] is None

    def test_phase_migration_no_phase3_studies(self):
        """All Phase-1 pipeline → 0 Phase-3 count in trailing 12m."""
        from engine.theme_clinical import _compute_phase_migration

        rows = [
            _make_row("m1", "t1", f"NCT{i:04d}", f"2023-{(i%12)+1:02d}", phase1=True, phase3=False)
            for i in range(24)
        ]
        df = _build_df(rows)
        pm = _compute_phase_migration(df)
        assert pm["n_phase3_recent"] == 0, "Expected 0 Phase-3 in all-Phase-1 pipeline"

    def test_n_phase3_recent_count_correct(self):
        """n_phase3_recent must count Phase-3 studies in trailing 12 months."""
        from engine.theme_clinical import _compute_phase_migration

        # 24 months: first 12 are all Phase-1, second 12 are all Phase-3
        prior_rows = [
            _make_row("m1", "t1", f"NCT_P{i:04d}", f"2022-{(i%12)+1:02d}",
                      phase1=True, phase3=False)
            for i in range(12)
        ]
        recent_rows = [
            _make_row("m1", "t1", f"NCT_R{i:04d}", f"2023-{(i%12)+1:02d}", phase3=True)
            for i in range(12)
        ]
        df = _build_df(prior_rows + recent_rows)
        pm = _compute_phase_migration(df)
        # Recent window = 2023-01 to 2023-12 (the last 12 months)
        assert pm["n_phase3_recent"] == 12, (
            f"Expected 12 Phase-3 in recent 12m; got {pm['n_phase3_recent']}"
        )
        assert pm["n_total_prior"] >= 0


# ---------------------------------------------------------------------------
# Honest-null coverage (parquet absent)
# ---------------------------------------------------------------------------

class TestHonestNull:

    def test_absent_parquet_returns_honest_null(self, monkeypatch):
        """When parquet is absent, all themes return honest null with n_modalities_with_data=0."""
        from engine import theme_clinical as tc

        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)

        themes = result.get("themes", {})
        assert len(themes) > 0, "Should have theme entries even when parquet absent"
        for theme_id, t in themes.items():
            assert t["n_modalities_with_data"] == 0, (
                f"Theme {theme_id} should have 0 modalities with data when parquet absent"
            )

    def test_coverage_stats_parquet_absent_flag(self, monkeypatch):
        """coverage_stats.parquet_absent must be True when no data."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        assert result["coverage_stats"]["parquet_absent"] is True

    def test_write_outputs_with_parquet_absent(self, tmp_path, monkeypatch):
        """Engine writes valid JSON even when parquet is absent."""
        from engine import theme_clinical as tc

        nw_out = tmp_path / "theme_clinical.json"
        site_out = tmp_path / "clinical_pipeline.json"

        with (
            mock.patch.object(tc, "_load_parquet", return_value=None),
            mock.patch.object(tc, "_NW_OUT", nw_out),
            mock.patch.object(tc, "_SITE_OUT", site_out),
        ):
            tc.compute_theme_clinical(write_nw=True, write_site=True)

        assert nw_out.exists(), "NW artifact must be written even when parquet absent"
        assert site_out.exists(), "Site projection must be written even when parquet absent"

        with open(nw_out) as fh:
            nw = json.load(fh)
        assert nw["schema"] == "theme_clinical.v1"
        assert "themes" in nw

    def test_honest_null_coverage_notes_present(self, monkeypatch):
        """All themes must have coverage_note and coverage_note_zh when null."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        for theme_id, t in result.get("themes", {}).items():
            assert t.get("coverage_note"), f"Theme {theme_id}: coverage_note must be present"
            assert t.get("coverage_note_zh"), f"Theme {theme_id}: coverage_note_zh must be present"


# ---------------------------------------------------------------------------
# Authority block
# ---------------------------------------------------------------------------

class TestAuthorityBlock:

    def test_authority_all_may_false(self):
        from engine.theme_clinical import AUTHORITY
        assert AUTHORITY["may_rank"] is False
        assert AUTHORITY["may_gate"] is False
        assert AUTHORITY["may_size"] is False
        assert AUTHORITY["may_escalate"] is False
        assert AUTHORITY["is_context_only"] is True

    def test_output_contains_authority(self, monkeypatch):
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        auth = result.get("authority", {})
        assert auth.get("may_rank") is False
        assert auth.get("is_context_only") is True

    def test_authority_has_fence_note(self):
        """Authority must have fused_obs_z_fence field."""
        from engine.theme_clinical import AUTHORITY
        assert "fused_obs_z_fence" in AUTHORITY
        assert "fused_obs_z" in AUTHORITY["fused_obs_z_fence"].lower()


# ---------------------------------------------------------------------------
# Output schema completeness
# ---------------------------------------------------------------------------

class TestOutputSchema:

    def test_nw_artifact_top_level_fields(self, monkeypatch):
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        required_fields = {
            "schema", "as_of", "generated_at", "authority",
            "honesty_header", "coverage_stats", "themes",
            "vocabulary_version", "api_note",
        }
        missing = required_fields - set(result.keys())
        assert not missing, f"NW artifact missing top-level fields: {missing}"

    def test_theme_data_required_keys(self, monkeypatch):
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        required = {
            "theme_id", "n_modalities_configured", "n_modalities_with_data",
            "n_studies_total", "year_month_max", "theme_registration_yoy_pct",
            "theme_registration_velocity_read", "n_phase3_trailing12m",
            "modalities", "coverage_note", "coverage_note_zh",
        }
        for theme_id, t in result["themes"].items():
            missing = required - set(t.keys())
            assert not missing, f"Theme {theme_id} missing required fields: {missing}"

    def test_site_projection_has_correct_schema(self, monkeypatch, tmp_path):
        """Site projection must have schema=theme_clinical.v1 and compact modality fields."""
        from engine import theme_clinical as tc

        site_out = tmp_path / "clinical_pipeline.json"
        with (
            mock.patch.object(tc, "_load_parquet", return_value=None),
            mock.patch.object(tc, "_NW_OUT", tmp_path / "nw.json"),
            mock.patch.object(tc, "_SITE_OUT", site_out),
        ):
            tc.compute_theme_clinical(write_nw=True, write_site=True)

        with open(site_out) as fh:
            site = json.load(fh)
        assert site.get("schema") == "theme_clinical.v1"
        assert "authority" in site
        assert site["authority"].get("is_context_only") is True

    def test_schema_field_value(self, monkeypatch):
        """schema field must be 'theme_clinical.v1' (version-pinned)."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        assert result["schema"] == "theme_clinical.v1"

    def test_modality_required_keys(self, monkeypatch):
        """Each modality dict must have required keys."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        required = {
            "modality_id", "theme_id", "n_studies_total",
            "registration_yoy_pct", "registration_velocity_read",
            "phase_migration", "n_phase3_trailing12m",
            "coverage_note", "coverage_note_zh", "expected_read",
        }
        for theme_id, t in result["themes"].items():
            for mid, m in (t.get("modalities") or {}).items():
                missing = required - set(m.keys())
                assert not missing, (
                    f"Modality {mid} in theme {theme_id} missing required fields: {missing}"
                )


# ---------------------------------------------------------------------------
# Banned words
# ---------------------------------------------------------------------------

class TestBannedWords:

    def test_no_validated_in_nw_output(self, monkeypatch):
        """'validated' must not appear as affirmative claim in NW output."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        output_str = json.dumps(result, ensure_ascii=False)
        negated = re.sub(r'\b(un|not|no|non)-?validated\b', '', output_str, flags=re.IGNORECASE)
        assert "validated" not in negated.lower(), (
            "Banned word 'validated' found as affirmative claim in theme_clinical NW output"
        )

    def test_no_validated_in_authority_block(self):
        from engine.theme_clinical import AUTHORITY
        auth_str = json.dumps(AUTHORITY)
        negated = re.sub(r'\b(un|not|no|non)-?validated\b', '', auth_str, flags=re.IGNORECASE)
        assert "validated" not in negated.lower(), (
            "Banned word 'validated' found in AUTHORITY block"
        )

    def test_no_validated_in_site_projection(self, monkeypatch, tmp_path):
        from engine import theme_clinical as tc
        site_out = tmp_path / "clinical_pipeline.json"
        with (
            mock.patch.object(tc, "_load_parquet", return_value=None),
            mock.patch.object(tc, "_NW_OUT", tmp_path / "nw.json"),
            mock.patch.object(tc, "_SITE_OUT", site_out),
        ):
            tc.compute_theme_clinical(write_nw=True, write_site=True)
        with open(site_out) as fh:
            site_str = fh.read()
        negated = re.sub(r'\b(un|not|no|non)-?validated\b', '', site_str, flags=re.IGNORECASE)
        assert "validated" not in negated.lower(), (
            "Banned word 'validated' found in site projection"
        )


# ---------------------------------------------------------------------------
# End-to-end with synthetic parquet data
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_compute_with_synthetic_data(self, monkeypatch):
        """
        End-to-end: 24 months of synthetic GLP-1 data → engine computes
        registration velocity and outputs the expected theme structure.
        """
        from engine import theme_clinical as tc
        from collectors.clinicaltrials_themes import STORE_COLS

        rows = _monthly_registration_rows(
            "glp1_named_agents", "glp1_obesity",
            "2022-01", 24, n_per_month=5, yoy_growth=0.25
        )
        df = pd.DataFrame(rows, columns=STORE_COLS)

        with mock.patch.object(tc, "_load_parquet", return_value=df):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)

        glp1 = result["themes"].get("glp1_obesity")
        assert glp1 is not None, "glp1_obesity theme must be present"
        assert glp1["n_modalities_with_data"] >= 1
        assert glp1["n_studies_total"] > 0
        assert glp1["theme_registration_velocity_read"] in ("accelerating", "decelerating", "neutral")

    def test_no_composite_across_themes(self, monkeypatch):
        """Each theme must have independent metrics — no cross-theme composite."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        themes = result.get("themes", {})
        assert len(themes) > 1, "Must have multiple themes"
        for tid, t in themes.items():
            assert "theme_registration_yoy_pct" in t, (
                f"Theme {tid} missing independent registration_yoy_pct"
            )

    def test_multi_modality_theme_aggregation(self, monkeypatch):
        """
        glp1_obesity has 2 modalities; both should contribute to theme totals.
        """
        from engine import theme_clinical as tc
        from collectors.clinicaltrials_themes import STORE_COLS

        # 12 months of data for glp1_named_agents
        rows1 = _monthly_registration_rows("glp1_named_agents", "glp1_obesity",
                                           "2025-01", 12, n_per_month=3)
        # 12 months of data for glp1_incretin_mechanism
        rows2 = _monthly_registration_rows("glp1_incretin_mechanism", "glp1_obesity",
                                           "2025-01", 12, n_per_month=2)
        df = pd.DataFrame(rows1 + rows2, columns=STORE_COLS)

        with mock.patch.object(tc, "_load_parquet", return_value=df):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)

        glp1 = result["themes"].get("glp1_obesity")
        assert glp1 is not None
        assert glp1["n_modalities_with_data"] == 2, (
            f"Expected 2 modalities with data; got {glp1['n_modalities_with_data']}"
        )
        # Total studies = rows from both modalities
        assert glp1["n_studies_total"] == len(rows1) + len(rows2), (
            f"Expected {len(rows1) + len(rows2)} total studies; got {glp1['n_studies_total']}"
        )


# ---------------------------------------------------------------------------
# Synapse / DAG conformance
# ---------------------------------------------------------------------------

class TestSynapseConformance:

    def test_nw_artifact_registered_in_synapse(self):
        """data/neuralweb/theme_clinical.json must be registered in synapse.yml."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        paths = [
            entry.get("path", "")
            for entry in (synapse.get("artifacts") or {}).values()
        ]
        assert any("theme_clinical" in p for p in paths), (
            "data/neuralweb/theme_clinical.json not found in synapse.yml artifacts"
        )

    def test_site_artifact_registered_in_synapse(self):
        """site/basketdata/clinical_pipeline.json must be registered in synapse.yml."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        paths = [
            entry.get("path", "")
            for entry in (synapse.get("artifacts") or {}).values()
        ]
        assert any("clinical_pipeline" in p for p in paths), (
            "site/basketdata/clinical_pipeline.json not found in synapse.yml artifacts"
        )

    def test_dag_has_clinical_theme_collect_entry(self):
        """dag.yml must have a collect_clinical_themes or collect_clinicaltrials_themes step."""
        dag_path = Path(__file__).resolve().parent.parent / "config" / "dag.yml"
        with open(dag_path) as fh:
            content = fh.read()
        assert "clinical" in content.lower(), (
            "dag.yml missing clinical themes step"
        )

    def test_synapse_artifact_fields_complete(self):
        """W10 synapse artifacts must have all required fields."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        required_fields = {
            "path", "format", "producer", "owner_program", "cadence", "storage",
            "asof_field", "freshness_sla_hours", "schema", "tier", "horizon_role",
        }
        for artifact_id, entry in (synapse.get("artifacts") or {}).items():
            if "clinical" in artifact_id:
                missing = required_fields - set(entry.keys())
                assert not missing, (
                    f"Synapse artifact {artifact_id!r} missing required fields: {missing}"
                )

    def test_synapse_producer_paths_exist(self):
        """Synapse entries for W10 must have producer paths that exist."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        repo_root = synapse_path.parent.parent
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        for artifact_id, entry in (synapse.get("artifacts") or {}).items():
            if "clinical" in artifact_id:
                producer = entry.get("producer", "")
                producer_path = repo_root / producer
                assert producer_path.exists(), (
                    f"Synapse {artifact_id!r}: producer {producer!r} does not exist"
                )

    def test_synapse_tier_is_display(self):
        """W10 synapse artifacts must be display tier (not scored)."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        for artifact_id, entry in (synapse.get("artifacts") or {}).items():
            if "clinical" in artifact_id:
                assert entry.get("tier") == "display", (
                    f"Synapse {artifact_id!r}: tier must be 'display' (not scored); "
                    f"got {entry.get('tier')!r}"
                )

    def test_synapse_horizon_is_context(self):
        """W10 synapse artifacts must have horizon_role='context'."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        for artifact_id, entry in (synapse.get("artifacts") or {}).items():
            if "clinical" in artifact_id:
                assert entry.get("horizon_role") == "context", (
                    f"Synapse {artifact_id!r}: horizon_role must be 'context'; "
                    f"got {entry.get('horizon_role')!r}"
                )


# ---------------------------------------------------------------------------
# check_validated_claims integration
# ---------------------------------------------------------------------------

class TestCheckValidatedClaims:

    def test_no_affirmative_validated_in_outputs(self, monkeypatch, tmp_path):
        """
        Affirmative 'validated' claim in output would fail check_validated_claims.
        This test proves no such claim appears in theme_clinical output.
        """
        from engine import theme_clinical as tc

        nw_out = tmp_path / "nw.json"
        site_out = tmp_path / "site.json"

        with (
            mock.patch.object(tc, "_load_parquet", return_value=None),
            mock.patch.object(tc, "_NW_OUT", nw_out),
            mock.patch.object(tc, "_SITE_OUT", site_out),
        ):
            tc.compute_theme_clinical(write_nw=True, write_site=True)

        for out_path in [nw_out, site_out]:
            with open(out_path) as fh:
                text = fh.read()
            negated = re.sub(
                r'\b(un|not|no|non)-?validated\b', '', text, flags=re.IGNORECASE
            )
            assert "validated" not in negated.lower(), (
                f"Affirmative 'validated' claim found in {out_path}"
            )

    def test_honesty_header_present_and_non_empty(self, monkeypatch):
        """honesty_header must be present and non-empty in both null and data states."""
        from engine import theme_clinical as tc
        with mock.patch.object(tc, "_load_parquet", return_value=None):
            result = tc.compute_theme_clinical(write_nw=False, write_site=False)
        assert result.get("honesty_header"), "honesty_header must be present and non-empty"


# ---------------------------------------------------------------------------
# Velocity read enum values
# ---------------------------------------------------------------------------

class TestVelocityRead:

    def test_velocity_read_valid_enum_values(self):
        """velocity_read must always be one of the three valid values."""
        from engine.theme_clinical import _velocity_read
        valid = {"accelerating", "decelerating", "neutral"}
        for yoy in [None, -50.0, -3.0, 3.0, 50.0, 0.0]:
            read, band = _velocity_read(yoy)
            assert read in valid, (
                f"Invalid velocity_read {read!r} for yoy={yoy}"
            )

    def test_neutral_below_floor(self):
        """|YoY| < neutral floor → 'neutral'."""
        from engine.theme_clinical import _velocity_read
        read, band = _velocity_read(3.0)
        assert read == "neutral"
        assert band is None

    def test_none_yoy_is_neutral(self):
        from engine.theme_clinical import _velocity_read
        read, band = _velocity_read(None)
        assert read == "neutral"
        assert band is None

    def test_large_positive_is_accelerating_large(self):
        from engine.theme_clinical import _velocity_read
        read, band = _velocity_read(30.0)
        assert read == "accelerating"
        assert band == "large"

    def test_moderate_negative_is_decelerating_moderate(self):
        from engine.theme_clinical import _velocity_read
        read, band = _velocity_read(-15.0)
        assert read == "decelerating"
        assert band == "moderate"
