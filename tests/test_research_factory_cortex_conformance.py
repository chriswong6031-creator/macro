"""tests/test_research_factory_cortex_conformance.py — Batch-B conformance tests.

Covers the three gaps fixed before first Batch-B rows arrive:
  (a) Task 1: cortex-sourced queue row auto-types to cortex_hypothesis +
              cortex_shared; non-metabolism id → refusal + warn; non-cortex rows
              unchanged.
  (b) Task 2: RF-2 projection map — full metabolism vocabulary coverage incl.
              unknown-status fallback.
  (c) Task 3: RF-13 timestamp violation flag fires / stays clear.
  (d) Absent-file safety throughout.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ===========================================================================
# Helper
# ===========================================================================

def _write_registry(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# ===========================================================================
# Task 1a — cortex-sourced queue row auto-types correctly
# ===========================================================================

class TestCortexQueueAutoTyping:
    """_ingest_research_queue_row detects cortex source and applies RF-3/RF-6 fixes."""

    def _make_cortex_row(self, **overrides) -> dict:
        base = {
            "id": "cortex-2026-07-06-test-lead-lag",
            "kind": "cortex_hypothesis",
            "hypothesis": "breadth leads sector rotation by 5 days",
            "mechanism": "leading indicator exhaustion",
            "claim_shape": "lead_lag",
            "horizon_d": 21,
        }
        base.update(overrides)
        return base

    def test_kind_field_auto_types_to_cortex_hypothesis(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row()
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "cortex_hypothesis"

    def test_cortex_id_prefix_auto_types(self):
        """Rows with id starting 'cortex-' are recognised even without kind field."""
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row()
        del row["kind"]
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "cortex_hypothesis"

    def test_source_cortex_auto_types(self):
        """Rows with source='cortex' are recognised."""
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": "cortex-2026-07-06-breadth-sentinel",
            "source": "cortex",
            "hypothesis": "some hypothesis",
            "mechanism": "some mechanism",
        }
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "cortex_hypothesis"

    def test_domain_neuralweb_auto_types(self):
        """Rows with domain='neuralweb' are recognised."""
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": "cortex-2026-07-06-regime-sentinel",
            "domain": "neuralweb",
            "hypothesis": "some hypothesis",
            "mechanism": "some mechanism",
        }
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "cortex_hypothesis"

    def test_trial_accounting_is_cortex_shared(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row()
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        ta = cand["trial_accounting"]
        assert ta["mode"] == "cortex_shared"
        assert ta["family"] is None

    def test_spec_ref_carries_metabolism_id(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row()
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["spec_ref"] == "cortex-2026-07-06-test-lead-lag"

    def test_claim_shape_copied_verbatim(self):
        """RF-3: claim_shape must be taken from the row, never synthesised."""
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row(claim_shape="entry_quality")
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["claim_shape"] == "entry_quality"

    def test_claim_shape_absent_leaves_none(self):
        """RF-3: if row has no claim_shape, candidate claim_shape stays None."""
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row()
        del row["claim_shape"]
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["claim_shape"] is None

    def test_explicit_candidate_type_preserved(self):
        """If the row already carries an explicit candidate_type, honour it."""
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = self._make_cortex_row(candidate_type="cortex_hypothesis")
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "cortex_hypothesis"


# ===========================================================================
# Task 1b — refusal path: cortex row without metabolism id warns and returns None
# ===========================================================================

class TestCortexRefusalNoId:
    """Cortex-sourced row with no id must be refused (metabolism chokepoint)."""

    def test_no_id_returns_none(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "kind": "cortex_hypothesis",
            "hypothesis": "some hypothesis without id",
            "mechanism": "some mechanism",
        }
        result = _ingest_research_queue_row(row)
        assert result is None

    def test_no_id_emits_warning(self, capsys):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "kind": "cortex_hypothesis",
            "hypothesis": "orphan hypothesis",
            "mechanism": "orphan mechanism",
        }
        _ingest_research_queue_row(row)
        captured = capsys.readouterr()
        assert "WARN" in captured.err
        assert "metabolism" in captured.err.lower() or "chokepoint" in captured.err.lower()

    def test_null_id_also_refused(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": None,
            "kind": "cortex_hypothesis",
            "hypothesis": "hypothesis with null id",
            "mechanism": "mechanism",
        }
        result = _ingest_research_queue_row(row)
        assert result is None


# ===========================================================================
# Task 1c — non-cortex rows unchanged
# ===========================================================================

class TestNonCortexRowsUnchanged:
    """Non-cortex rows must default to external_idea and read_only accounting."""

    def test_plain_row_defaults_to_external_idea(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": "species-001",
            "hypothesis": "momentum factor hypothesis",
            "mechanism": "momentum exhaustion",
        }
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "external_idea"

    def test_plain_row_trial_accounting_read_only(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": "oracle-C4",
            "hypothesis": "washout reversal",
            "mechanism": "sellers exhausted",
        }
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["trial_accounting"]["mode"] == "read_only"

    def test_oracle_domain_is_not_cortex(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": "ING0",
            "domain": "oracle",
            "hypothesis": "oracle hypothesis",
            "mechanism": "oracle mechanism",
        }
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "external_idea"

    def test_explicit_candidate_type_on_non_cortex_row(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {
            "id": "A1",
            "candidate_type": "oracle_compound",
            "hypothesis": "oracle compound hypothesis",
            "mechanism": "oracle mechanism",
        }
        cand = _ingest_research_queue_row(row)
        assert cand is not None
        assert cand["candidate_type"] == "oracle_compound"


# ===========================================================================
# Task 2 — RF-2 projection map coverage
# ===========================================================================

class TestMetabolismStatusProjection:
    """project_metabolism_status covers full metabolism vocabulary."""

    def test_registered_maps_to_screened(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("registered") == "screened"

    def test_insufficient_n_hyphen_maps_to_awaiting_data(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("insufficient-n") == "awaiting_data"

    def test_insufficient_n_underscore_maps_to_awaiting_data(self):
        """Guard against alternate spelling."""
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("insufficient_n") == "awaiting_data"

    def test_failed_maps_to_numeric_rejected(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("failed") == "numeric_rejected"

    def test_passed_maps_to_screened(self):
        """passed → screened; factory's own transitions handle further promotion."""
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("passed") == "screened"

    def test_budget_rejected_maps_to_numeric_rejected(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("budget-rejected") == "numeric_rejected"

    def test_invalid_maps_to_numeric_rejected(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("invalid") == "numeric_rejected"

    def test_retired_maps_to_numeric_rejected(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("retired") == "numeric_rejected"

    def test_invalid_self_reference_maps_to_numeric_rejected(self):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        assert project_metabolism_status("invalid-self-reference") == "numeric_rejected"

    def test_unknown_status_falls_through_verbatim(self):
        """Unknown statuses must pass through verbatim (not crash)."""
        from engine.research_factory.adapter_cortex import project_metabolism_status
        result = project_metabolism_status("some_future_status_not_in_map")
        assert result == "some_future_status_not_in_map"

    def test_unknown_status_logs_warning(self, caplog):
        from engine.research_factory.adapter_cortex import project_metabolism_status
        with caplog.at_level(logging.WARNING, logger="engine.research_factory.adapter_cortex"):
            project_metabolism_status("mystery_status")
        assert any("unknown metabolism status" in r.message for r in caplog.records)

    def test_route_hypothesis_returns_both_domain_status_fields(self, tmp_path):
        """route_hypothesis must return domain_status (projected) AND domain_status_raw."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = {
            "id": "cortex-2026-07-06-proj-test",
            "registered_at": "2026-07-06T10:00:00Z",
            "status": "registered",
            "spine_query": {"family": "breadth"},
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert "domain_status" in result
        assert "domain_status_raw" in result
        assert result["domain_status"] == "screened"        # projected
        assert result["domain_status_raw"] == "registered"  # verbatim

    def test_route_hypothesis_projects_passed_to_screened(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = {
            "id": "cortex-2026-07-06-passed",
            "registered_at": "2026-07-06T10:00:00Z",
            "status": "passed",
            "spine_query": {"family": "breadth"},
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["domain_status"] == "screened"
        assert result["domain_status_raw"] == "passed"

    def test_route_hypothesis_projects_insufficient_n_to_awaiting_data(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = {
            "id": "cortex-2026-07-06-insufficient",
            "registered_at": "2026-07-06T10:00:00Z",
            "status": "insufficient-n",
            "spine_query": {"family": "breadth"},
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["domain_status"] == "awaiting_data"
        assert result["domain_status_raw"] == "insufficient-n"

    def test_projection_map_covers_all_metabolism_schema_statuses(self):
        """Verify the projection map includes every status named in metabolism.py schema."""
        from engine.research_factory.adapter_cortex import METABOLISM_STATUS_PROJECTION
        # From metabolism.py REGISTRATION SCHEMA docs + _update_row_status usage:
        # registered | budget-rejected | invalid | passed | failed | insufficient-n | retired
        # Plus: invalid-self-reference (evaluator verdict)
        required = {
            "registered",
            "budget-rejected",
            "invalid",
            "passed",
            "failed",
            "insufficient-n",
            "retired",
            "invalid-self-reference",
        }
        for s in required:
            assert s in METABOLISM_STATUS_PROJECTION, f"Missing projection for status {s!r}"


# ===========================================================================
# Task 3 — RF-13 timestamp violation flag
# ===========================================================================

class TestRF13TimestampViolation:
    """route_hypothesis sets rf13_timestamp_violation correctly."""

    def _write_registry_row(self, tmp_path: Path, row: dict) -> None:
        _write_registry(tmp_path / "neuralweb" / "machine_registry.jsonl", [row])

    def test_violation_fires_when_candidate_precedes_registered_at(self, tmp_path):
        """Candidate timestamp BEFORE registry registered_at → violation=True."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        reg_row = {
            "id": "cortex-2026-07-06-test-ts",
            "kind": "cortex_hypothesis",
            "registered_at": "2026-07-06T12:00:00Z",
            "status": "registered",
        }
        self._write_registry_row(tmp_path, reg_row)
        # Candidate claims it was created BEFORE metabolism registered it
        hyp = {
            "id": "cortex-2026-07-06-test-ts",
            "registered_at": "2026-07-06T08:00:00Z",  # 4 hours before registry
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["rf13_timestamp_violation"] is True

    def test_no_violation_when_candidate_matches_registered_at(self, tmp_path):
        """Candidate timestamp equal to registry registered_at → violation=False."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        ts = "2026-07-06T12:00:00Z"
        reg_row = {
            "id": "cortex-2026-07-06-eq-ts",
            "kind": "cortex_hypothesis",
            "registered_at": ts,
            "status": "registered",
        }
        self._write_registry_row(tmp_path, reg_row)
        hyp = {
            "id": "cortex-2026-07-06-eq-ts",
            "registered_at": ts,
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["rf13_timestamp_violation"] is False

    def test_no_violation_when_candidate_timestamp_after_registered_at(self, tmp_path):
        """Candidate timestamp AFTER registry registered_at → no violation."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        reg_row = {
            "id": "cortex-2026-07-06-after-ts",
            "kind": "cortex_hypothesis",
            "registered_at": "2026-07-06T08:00:00Z",
            "status": "registered",
        }
        self._write_registry_row(tmp_path, reg_row)
        hyp = {
            "id": "cortex-2026-07-06-after-ts",
            "registered_at": "2026-07-06T12:00:00Z",  # later than registry
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["rf13_timestamp_violation"] is False

    def test_violation_logs_warning(self, tmp_path, caplog):
        from engine.research_factory.adapter_cortex import route_hypothesis
        reg_row = {
            "id": "cortex-2026-07-06-warn-test",
            "registered_at": "2026-07-06T12:00:00Z",
            "status": "registered",
        }
        self._write_registry_row(tmp_path, reg_row)
        hyp = {
            "id": "cortex-2026-07-06-warn-test",
            "registered_at": "2026-07-05T00:00:00Z",
            "status": "registered",
        }
        with caplog.at_level(logging.WARNING, logger="engine.research_factory.adapter_cortex"):
            route_hypothesis(hyp, data_dir=tmp_path)
        assert any("RF-13" in r.message and "timestamp" in r.message for r in caplog.records)

    def test_no_violation_when_registry_absent(self, tmp_path):
        """Absent registry → no violation (absent-file-safe)."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = {
            "id": "cortex-2026-07-06-absent-reg",
            "registered_at": "2026-07-01T00:00:00Z",
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["rf13_timestamp_violation"] is False

    def test_no_violation_when_id_not_in_registry(self, tmp_path):
        """Hypothesis id not found in registry → no violation."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        reg_row = {
            "id": "cortex-2026-07-06-other-id",
            "registered_at": "2026-07-06T12:00:00Z",
            "status": "registered",
        }
        self._write_registry_row(tmp_path, reg_row)
        hyp = {
            "id": "cortex-2026-07-06-different-id",
            "registered_at": "2026-07-01T00:00:00Z",
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["rf13_timestamp_violation"] is False

    def test_no_violation_when_timestamps_unparseable(self, tmp_path):
        """Unparseable timestamps → no violation (fail-safe, not crash)."""
        from engine.research_factory.adapter_cortex import route_hypothesis
        reg_row = {
            "id": "cortex-2026-07-06-bad-ts",
            "registered_at": "NOT_A_TIMESTAMP",
            "status": "registered",
        }
        self._write_registry_row(tmp_path, reg_row)
        hyp = {
            "id": "cortex-2026-07-06-bad-ts",
            "registered_at": "ALSO_NOT_A_TIMESTAMP",
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert result["rf13_timestamp_violation"] is False


# ===========================================================================
# Absent-file safety integration
# ===========================================================================

class TestAbsentFileSafety:
    """Everything must survive with no data files present."""

    def test_load_machine_registry_absent(self, tmp_path):
        from engine.research_factory.adapter_cortex import load_machine_registry
        assert load_machine_registry(tmp_path) == []

    def test_route_all_absent(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_all
        assert route_all(tmp_path) == []

    def test_route_hypothesis_absent_registry_no_crash(self, tmp_path):
        from engine.research_factory.adapter_cortex import route_hypothesis
        hyp = {
            "id": "cortex-2026-07-06-absent-safe",
            "registered_at": "2026-07-06T00:00:00Z",
            "status": "registered",
        }
        result = route_hypothesis(hyp, data_dir=tmp_path)
        assert isinstance(result, dict)
        assert result["hypothesis_id"] == "cortex-2026-07-06-absent-safe"
        assert result["rf13_timestamp_violation"] is False

    def test_is_cortex_sourced_row_no_crash_on_empty(self):
        from scripts.research_factory_ingest import _is_cortex_sourced_row
        assert _is_cortex_sourced_row({}) is False

    def test_ingest_queue_row_non_cortex_empty_id_no_crash(self):
        from scripts.research_factory_ingest import _ingest_research_queue_row
        row = {"hypothesis": "some hypothesis", "mechanism": "some mechanism"}
        result = _ingest_research_queue_row(row)
        assert result is not None
        assert result["candidate_type"] == "external_idea"
