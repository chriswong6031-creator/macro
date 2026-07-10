"""tests/test_clinicaltrials_themes.py — Tests for collectors/clinicaltrials_themes.py (TIL W10).

Coverage:
  - config/clinical_modalities.yml schema validation
  - crosswalk id validity (all theme_ids exist in theme_crosswalk.yml)
  - query-precision documentation (live_hit_count_verified field present)
  - normalizer: _parse_study on synthetic API fixtures
  - INDUSTRY filter regression: mixed-sponsor fixture → only INDUSTRY counted
  - per-modality isolation: one bad modality never voids others
  - compute_monthly_aggregates: monthly aggregation math
  - missing-month / newest-window fall-through
  - deduplication by (modality_id, nct_id)
  - state file save/load round-trip
  - banned words (no 'validated' in outputs)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest import mock

import pandas as pd
import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers: synthetic study fixtures
# ---------------------------------------------------------------------------

def _make_study(
    nct_id: str = "NCT12345678",
    sponsor_class: str = "INDUSTRY",
    phases: Optional[list] = None,
    first_post_date: str = "2023-06-15",
    enrollment_count: Optional[int] = 100,
) -> dict:
    """Build a synthetic v2 API study object."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id},
            "statusModule": {
                "studyFirstPostDateStruct": {"date": first_post_date},
            },
            "designModule": {
                "phases": phases or [],
                "enrollmentInfo": {"count": enrollment_count} if enrollment_count is not None else {},
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {
                    "class": sponsor_class,
                    "name": "Test Pharma Inc",
                }
            },
        }
    }


def _make_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a modality_monthly.parquet to tmp_path."""
    from collectors.clinicaltrials_themes import STORE_COLS
    df = pd.DataFrame(rows, columns=STORE_COLS)
    path = tmp_path / "modality_monthly.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_row(
    modality_id: str = "glp1_named_agents",
    theme_id: str = "glp1_obesity",
    nct_id: str = "NCT12345678",
    study_first_post_date: str = "2023-06-15",
    year_month: str = "2023-06",
    phase1: bool = False,
    phase2: bool = False,
    phase3: bool = True,
    enrollment_target: Optional[int] = 100,
) -> dict:
    """Build a synthetic parquet row."""
    return {
        "modality_id": modality_id,
        "theme_id": theme_id,
        "nct_id": nct_id,
        "study_first_post_date": study_first_post_date,
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


# ---------------------------------------------------------------------------
# Config schema validation
# ---------------------------------------------------------------------------

class TestConfigSchema:

    def test_clinical_modalities_config_loads(self):
        """config/clinical_modalities.yml must load without error."""
        repo_root = Path(__file__).resolve().parent.parent
        cfg_path = repo_root / "config" / "clinical_modalities.yml"
        assert cfg_path.exists(), "config/clinical_modalities.yml must exist"
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        assert isinstance(cfg, dict), "Config must parse as a dict"
        assert "modalities" in cfg, "Config must have 'modalities' key"
        assert isinstance(cfg["modalities"], list), "'modalities' must be a list"

    def test_config_has_required_fields(self):
        """Each modality row must have required fields."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        required = {"modality_id", "theme_id", "expected_read", "live_hit_count_verified", "verified_date"}
        for m in cfg["modalities"]:
            missing = required - set(m.keys())
            assert not missing, (
                f"Modality {m.get('modality_id', '?')} missing required fields: {missing}"
            )

    def test_config_modality_ids_unique(self):
        """modality_id must be unique."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        ids = [m["modality_id"] for m in cfg["modalities"]]
        assert len(ids) == len(set(ids)), f"Duplicate modality_ids: {set(i for i in ids if ids.count(i) > 1)}"

    def test_config_count_in_bounds(self):
        """Must have 8-15 modality rows (spec requirement)."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        n = len(cfg["modalities"])
        assert 8 <= n <= 15, f"Expected 8-15 modality rows; got {n}"

    def test_config_hit_counts_reasonable(self):
        """Each modality must have live_hit_count_verified <= 1000 (precision check)."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        for m in cfg["modalities"]:
            count = m.get("live_hit_count_verified", 0)
            assert count <= 1000, (
                f"Modality {m['modality_id']}: live_hit_count_verified={count} exceeds "
                f"precision threshold of 1000 (query too broad)"
            )
            assert count > 0, (
                f"Modality {m['modality_id']}: live_hit_count_verified must be > 0 "
                "(must verify live before adding)"
            )

    def test_has_vocabulary_version(self):
        """Config must have vocabulary_version for PIT law compliance."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        assert "vocabulary_version" in cfg, "Config must have vocabulary_version (PIT law)"
        assert cfg["vocabulary_version"], "vocabulary_version must be non-empty"


# ---------------------------------------------------------------------------
# Crosswalk ID validity
# ---------------------------------------------------------------------------

class TestCrosswalkIdValidity:

    def test_all_theme_ids_in_crosswalk(self):
        """All theme_ids in clinical_modalities.yml must exist in theme_crosswalk.yml."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            clinical_cfg = yaml.safe_load(fh)
        with open(repo_root / "config" / "theme_crosswalk.yml", encoding="utf-8") as fh:
            crosswalk = yaml.safe_load(fh)
        valid_ids = {t["id"] for t in crosswalk.get("themes", [])}
        for m in clinical_cfg["modalities"]:
            assert m["theme_id"] in valid_ids, (
                f"Modality {m['modality_id']}: theme_id {m['theme_id']!r} "
                f"not found in theme_crosswalk.yml"
            )

    def test_covered_themes_are_health_adjacent(self):
        """Only health-adjacent themes should appear (per spec)."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            clinical_cfg = yaml.safe_load(fh)
        allowed_themes = {"glp1_obesity", "diagnostics_lifesci", "medical_devices"}
        for m in clinical_cfg["modalities"]:
            assert m["theme_id"] in allowed_themes, (
                f"Modality {m['modality_id']}: theme_id {m['theme_id']!r} "
                f"is not a health-adjacent theme (allowed: {allowed_themes})"
            )


# ---------------------------------------------------------------------------
# _parse_study normalizer on synthetic API fixtures
# ---------------------------------------------------------------------------

class TestParseStudy:

    def _get_modality_cfg(self) -> dict:
        return {
            "modality_id": "glp1_named_agents",
            "theme_id": "glp1_obesity",
            "expected_read": "rising registrations = capital commitment",
        }

    def test_parse_industry_study(self):
        """INDUSTRY-sponsored study parses to a complete row."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999001", "INDUSTRY", ["PHASE3"], "2023-11-10", 250)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is not None
        assert row["nct_id"] == "NCT99999001"
        assert row["study_first_post_date"] == "2023-11-10"
        assert row["year_month"] == "2023-11"
        assert row["phase3"] is True
        assert row["phase1"] is False
        assert row["phase2"] is False
        assert row["enrollment_target"] == 250
        assert row["sponsor_class"] == "INDUSTRY"
        assert row["modality_id"] == "glp1_named_agents"
        assert row["theme_id"] == "glp1_obesity"

    def test_parse_non_industry_returns_none(self):
        """Non-INDUSTRY sponsor → None (filtered out)."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999002", "NIH", ["PHASE2"], "2023-05-01", 50)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is None, "Non-INDUSTRY study must return None"

    def test_parse_other_sponsor_returns_none(self):
        """OTHER class sponsor → None."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999003", "OTHER", ["PHASE1"], "2022-01-01", 30)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is None, "OTHER-class study must return None"

    def test_parse_missing_nct_id_returns_none(self):
        """Study without NCT ID → None."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("", "INDUSTRY", ["PHASE3"], "2023-01-01", 100)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is None, "Study without NCT ID must return None"

    def test_parse_missing_first_post_returns_none(self):
        """Study without studyFirstPostDate → None (PIT key required)."""
        from collectors.clinicaltrials_themes import _parse_study
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT99999005"},
                "statusModule": {"studyFirstPostDateStruct": {}},
                "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": 100}},
                "sponsorCollaboratorsModule": {"leadSponsor": {"class": "INDUSTRY"}},
            }
        }
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is None, "Study without first post date must return None (PIT law)"

    def test_parse_phase_flags_correct(self):
        """Phase flags set correctly for multi-phase studies."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999006", "INDUSTRY", ["PHASE1", "PHASE2"], "2022-03-15", 45)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is not None
        assert row["phase1"] is True
        assert row["phase2"] is True
        assert row["phase3"] is False

    def test_parse_missing_enrollment_sets_none(self):
        """Missing enrollment → enrollment_target=None (not zero)."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999007", "INDUSTRY", ["PHASE2"], "2023-01-01", None)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is not None
        assert row["enrollment_target"] is None

    def test_parse_vocabulary_version_stamped(self):
        """vocabulary_version must be stamped on each row (PIT law)."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999008", "INDUSTRY", ["PHASE3"], "2024-01-15", 200)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v2-test")
        assert row is not None
        assert row["vocabulary_version"] == "v2-test"

    def test_parse_ingest_date_stamped(self):
        """ingest_date must be stored separately from study_first_post_date (PIT law)."""
        from collectors.clinicaltrials_themes import _parse_study
        study = _make_study("NCT99999009", "INDUSTRY", ["PHASE2"], "2020-05-01", 80)
        row = _parse_study(study, self._get_modality_cfg(), "2026-07-09", "v1")
        assert row is not None
        assert row["ingest_date"] == "2026-07-09"
        assert row["study_first_post_date"] == "2020-05-01"
        assert row["ingest_date"] != row["study_first_post_date"], (
            "PIT law: ingest_date must differ from study_first_post_date"
        )


# ---------------------------------------------------------------------------
# INDUSTRY filter regression (mixed sponsor fixture)
# ---------------------------------------------------------------------------

class TestIndustryFilterRegression:

    def test_mixed_sponsor_fixture_only_industry_counted(self, tmp_path):
        """Mixed-sponsor page: only INDUSTRY studies produce rows."""
        from collectors.clinicaltrials_themes import _parse_study

        modality_cfg = {
            "modality_id": "glp1_named_agents",
            "theme_id": "glp1_obesity",
            "expected_read": "rising",
        }
        studies = [
            _make_study("NCT10001", "INDUSTRY", ["PHASE3"], "2023-01-15", 200),
            _make_study("NCT10002", "NIH", ["PHASE2"], "2022-06-01", 50),    # academic
            _make_study("NCT10003", "FED", ["PHASE1"], "2021-03-10", 30),    # federal
            _make_study("NCT10004", "INDUSTRY", ["PHASE1"], "2023-09-20", 100),
            _make_study("NCT10005", "OTHER", ["PHASE3"], "2023-11-01", 300), # other
        ]
        rows = []
        for s in studies:
            r = _parse_study(s, modality_cfg, "2026-07-09", "v1")
            if r is not None:
                rows.append(r)

        assert len(rows) == 2, (
            f"Expected exactly 2 INDUSTRY rows from 5-study mixed fixture; got {len(rows)}"
        )
        nct_ids = {r["nct_id"] for r in rows}
        assert "NCT10001" in nct_ids, "INDUSTRY study NCT10001 must be included"
        assert "NCT10004" in nct_ids, "INDUSTRY study NCT10004 must be included"
        assert "NCT10002" not in nct_ids, "NIH study NCT10002 must be excluded"
        assert "NCT10003" not in nct_ids, "FED study NCT10003 must be excluded"
        assert "NCT10005" not in nct_ids, "OTHER study NCT10005 must be excluded"


# ---------------------------------------------------------------------------
# compute_monthly_aggregates
# ---------------------------------------------------------------------------

class TestComputeMonthlyAggregates:

    def test_monthly_aggregation_counts(self, tmp_path):
        """Monthly aggregation: counts per (modality_id, theme_id, year_month)."""
        from collectors.clinicaltrials_themes import compute_monthly_aggregates, STORE_COLS

        rows = [
            _make_row("glp1_named_agents", "glp1_obesity", "NCT001", "2023-03-10", "2023-03", phase3=True, enrollment_target=100),
            _make_row("glp1_named_agents", "glp1_obesity", "NCT002", "2023-03-15", "2023-03", phase3=True, enrollment_target=200),
            _make_row("glp1_named_agents", "glp1_obesity", "NCT003", "2023-04-01", "2023-04", phase1=True, phase3=False, enrollment_target=50),
        ]
        df = pd.DataFrame(rows, columns=STORE_COLS)
        agg = compute_monthly_aggregates(df)

        # 2023-03 should have 2 studies
        mar = agg[(agg["modality_id"] == "glp1_named_agents") & (agg["year_month"] == "2023-03")]
        assert len(mar) == 1, "Expected 1 aggregated row for 2023-03"
        assert mar.iloc[0]["n_new_registrations"] == 2
        assert mar.iloc[0]["n_phase3_new"] == 2
        assert mar.iloc[0]["n_phase1_new"] == 0
        assert mar.iloc[0]["enrollment_sum"] == 300

        # 2023-04 should have 1 study
        apr = agg[(agg["modality_id"] == "glp1_named_agents") & (agg["year_month"] == "2023-04")]
        assert len(apr) == 1
        assert apr.iloc[0]["n_new_registrations"] == 1
        assert apr.iloc[0]["n_phase1_new"] == 1
        assert apr.iloc[0]["n_phase3_new"] == 0

    def test_monthly_aggregation_no_phase_count(self, tmp_path):
        """n_no_phase counts studies where no Phase-1/2/3 flag is set."""
        from collectors.clinicaltrials_themes import compute_monthly_aggregates, STORE_COLS
        rows = [
            _make_row("glp1_named_agents", "glp1_obesity", "NCT010", "2023-05-01", "2023-05",
                      phase1=False, phase2=False, phase3=False),  # no phase
            _make_row("glp1_named_agents", "glp1_obesity", "NCT011", "2023-05-10", "2023-05",
                      phase3=True),  # has phase
        ]
        df = pd.DataFrame(rows, columns=STORE_COLS)
        agg = compute_monthly_aggregates(df)
        row = agg[agg["year_month"] == "2023-05"].iloc[0]
        assert row["n_no_phase"] == 1
        assert row["n_phase3_new"] == 1

    def test_empty_input_returns_empty_df(self):
        """Empty input → empty DataFrame with correct columns."""
        from collectors.clinicaltrials_themes import compute_monthly_aggregates
        agg = compute_monthly_aggregates(pd.DataFrame())
        assert len(agg) == 0
        assert "n_new_registrations" in agg.columns

    def test_none_input_returns_empty_df(self):
        """None input → empty DataFrame."""
        from collectors.clinicaltrials_themes import compute_monthly_aggregates
        agg = compute_monthly_aggregates(None)
        assert len(agg) == 0


# ---------------------------------------------------------------------------
# Missing-month / newest-window fall-through
# ---------------------------------------------------------------------------

class TestMissingMonthFallThrough:

    def test_missing_months_in_series_handled(self, tmp_path):
        """Gaps in monthly registration data must not crash aggregation."""
        from collectors.clinicaltrials_themes import compute_monthly_aggregates, STORE_COLS

        # Create rows with a gap: 2023-01, 2023-03 (skipping 2023-02)
        rows = [
            _make_row("glp1_named_agents", "glp1_obesity", "NCT020", "2023-01-15", "2023-01"),
            _make_row("glp1_named_agents", "glp1_obesity", "NCT021", "2023-03-10", "2023-03"),
        ]
        df = pd.DataFrame(rows, columns=STORE_COLS)
        agg = compute_monthly_aggregates(df)
        # Should have exactly 2 rows (one per month with data)
        assert len(agg) == 2
        months = set(agg["year_month"])
        assert "2023-01" in months
        assert "2023-03" in months

    def test_deduplication_by_modality_nct(self, tmp_path):
        """(modality_id, nct_id) deduplication: second ingestion does not double-count."""
        from collectors.clinicaltrials_themes import _merge_rows, STORE_COLS

        existing_rows = [
            _make_row("glp1_named_agents", "glp1_obesity", "NCT030", "2023-01-01", "2023-01"),
        ]
        existing = pd.DataFrame(existing_rows, columns=STORE_COLS)

        new_rows = [
            _make_row("glp1_named_agents", "glp1_obesity", "NCT030", "2023-01-01", "2023-01"),  # dup
            _make_row("glp1_named_agents", "glp1_obesity", "NCT031", "2023-02-01", "2023-02"),  # new
        ]
        merged = _merge_rows(existing, new_rows)
        assert len(merged) == 2, (
            f"Expected 2 rows after dedup (NCT030 kept once, NCT031 added); got {len(merged)}"
        )
        assert set(merged["nct_id"]) == {"NCT030", "NCT031"}


# ---------------------------------------------------------------------------
# Per-modality isolation
# ---------------------------------------------------------------------------

class TestPerModalityIsolation:

    def test_isolation_one_bad_modality_does_not_void_run(self, tmp_path):
        """
        Per-modality isolation: simulated HTTP error for one modality
        does not prevent other modalities from being collected.
        """
        from collectors.clinicaltrials_themes import _fetch_modality
        import requests

        # Create a mock session that returns None for first call, valid for second
        call_count = [0]

        def mock_get_side_effect(url, params, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                raise requests.ConnectionError("Simulated network error")
            resp = mock.Mock()
            resp.status_code = 200
            resp.json.return_value = {
                "totalCount": 1,
                "studies": [
                    _make_study("NCT040", "INDUSTRY", ["PHASE2"], "2023-06-01", 80),
                ]
            }
            return resp

        session = mock.Mock()
        session.get.side_effect = mock_get_side_effect

        modality1 = {
            "modality_id": "glp1_named_agents",
            "theme_id": "glp1_obesity",
            "query_type": "query.intr",
            "query": "semaglutide",
            "expected_read": "rising",
        }

        # First modality: simulated error
        rows1, total1, err1 = _fetch_modality(
            session, modality1, "2026-07-09", "v1", backfill=False, state={}
        )
        assert err1 is not None, "Error modality should report an error"
        assert len(rows1) == 0, "Error modality should return 0 rows"

        modality2 = {
            "modality_id": "liquid_biopsy",
            "theme_id": "diagnostics_lifesci",
            "query_type": "query.intr",
            "query": "liquid biopsy",
            "expected_read": "rising",
        }

        # Second modality: success
        rows2, total2, err2 = _fetch_modality(
            session, modality2, "2026-07-09", "v1", backfill=False, state={}
        )
        assert err2 is None, f"Second modality should succeed; got error: {err2}"
        assert len(rows2) == 1, "Second modality should return 1 row"


# ---------------------------------------------------------------------------
# State file round-trip
# ---------------------------------------------------------------------------

class TestStateFileRoundTrip:

    def test_save_load_state_round_trip(self, tmp_path):
        """State file save and load must be consistent."""
        from collectors.clinicaltrials_themes import _save_state, _load_state

        state = {
            "glp1_named_agents": {"last_ingest": "2026-07-09", "api_total": 692},
            "liquid_biopsy": {"last_ingest": "2026-07-08", "api_total": 113},
        }
        _save_state(tmp_path, state)
        loaded = _load_state(tmp_path)
        assert loaded == state

    def test_load_state_missing_returns_empty(self, tmp_path):
        """Missing state file → empty dict (no crash)."""
        from collectors.clinicaltrials_themes import _load_state
        state = _load_state(tmp_path)
        assert state == {}


# ---------------------------------------------------------------------------
# Banned words
# ---------------------------------------------------------------------------

class TestBannedWords:

    def test_no_validated_in_store_cols(self):
        """'validated' must not appear in any STORE_COLS column name."""
        from collectors.clinicaltrials_themes import STORE_COLS
        for col in STORE_COLS:
            assert "validated" not in col.lower(), (
                f"Banned word 'validated' found in STORE_COLS column: {col}"
            )

    def test_no_validated_in_config(self):
        """'validated' must not appear as an affirmative claim in config."""
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config" / "clinical_modalities.yml", encoding="utf-8") as fh:
            content = fh.read()
        import re
        negated = re.sub(r'\b(un|not|no|non)-?validated\b', '', content, flags=re.IGNORECASE)
        assert "validated" not in negated.lower(), (
            "Banned word 'validated' found as affirmative claim in clinical_modalities.yml"
        )


# ---------------------------------------------------------------------------
# STORE_COLS completeness
# ---------------------------------------------------------------------------

class TestStoreColsCompleteness:

    def test_store_cols_contains_pit_fields(self):
        """STORE_COLS must have both study_first_post_date and ingest_date (PIT law)."""
        from collectors.clinicaltrials_themes import STORE_COLS
        assert "study_first_post_date" in STORE_COLS, "PIT law: study_first_post_date required"
        assert "ingest_date" in STORE_COLS, "PIT law: ingest_date required"
        assert "vocabulary_version" in STORE_COLS, "PIT law: vocabulary_version required"

    def test_store_cols_has_phase_flags(self):
        """STORE_COLS must have individual phase boolean columns."""
        from collectors.clinicaltrials_themes import STORE_COLS
        for col in ("phase1", "phase2", "phase3"):
            assert col in STORE_COLS, f"STORE_COLS missing phase flag: {col}"

    def test_store_cols_has_enrollment(self):
        """STORE_COLS must have enrollment_target column."""
        from collectors.clinicaltrials_themes import STORE_COLS
        assert "enrollment_target" in STORE_COLS
