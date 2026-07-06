"""tests/test_research_factory_schema.py — Schema validator tests.

Tests (per W1 charter §6):
  1. authority field required on every schema (all five).
  2. rf.* regex accepts/rejects correctly incl. production-family collision.
  3. Schema round-trips for all five schemas (valid row → no violations).
  4. Invalid candidate_type rejected.
  5. claim_shape passthrough: null passes; illegal value rejected; legal values pass.
  6. keep_first semantics (ledger.py).
  7. Planted-violation fixture proving check_research_factory_authority.py
     detects a forbidden read (Article-2 module).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from engine.research_factory.schema import (
    validate_candidate,
    validate_challenge,
    validate_health,
    validate_paper_monitor,
    validate_transition,
    validate_rf_family,
    is_valid_rf_family_name,
    CANDIDATE_TYPES,
    CLAIM_SHAPES,
    SOURCES,
    STATES,
)
from engine.research_factory.ledger import (
    append_row,
    keep_first,
    load_jsonl,
    write_jsonl,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_candidate(**kwargs) -> dict:
    row = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": "rf-20260706-oracle-test-001",
        "created_at": "2026-07-06T00:00:00Z",
        "source": "oracle_brainstorm",
        "candidate_type": "oracle_compound",
        "domain": "oracle",
        "status": "proposed",
        "hypothesis": "This is a falsifiable test hypothesis.",
        "mechanism": "The underlying reason it might persist.",
        "claim_shape": None,
        "spec_ref": None,
        "trial_accounting": {"mode": "read_only", "family": None, "declared_at": None},
        "evaluation_plan": {},
        "lineage": {"respin_of": None, "superseded_by": None, "refinement_generation": 0},
        "flags": [],
        "artifacts": {},
        "transition_log": [],
    }
    row.update(kwargs)
    return row


def _base_transition(**kwargs) -> dict:
    row = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": "rf-20260706-oracle-test-001",
        "from": "proposed",
        "to": "registered",
        "reason_code": "valid_schema",
        "reason_text": "Schema validated.",
        "actor": "script",
        "actor_ref": None,
        "kill_evidence": None,
        "artifact_refs": [],
        "as_of": "2026-07-06T00:00:00Z",
    }
    row.update(kwargs)
    return row


def _base_challenge(**kwargs) -> dict:
    row = {
        "schema": "research_factory.challenge.v1",
        "authority": "display_only",
        "candidate_id": "rf-20260706-oracle-test-001",
        "challenged_at": "2026-07-06T00:00:00Z",
        "mechanical_probes": {
            "input_insensitive": False,
            "near_dup": {"score": 0.0, "nearest": None},
            "mechanism_spec_mismatch": False,
            "gauntlet_legs": [],
        },
        "reviewer": {
            "agent_type": "reviewer",
            "recommendation": "ADVISORY_REVIEW",
            "blockers": [],
            "non_blocking_concerns": [],
            "best_counterargument": "No strong counterargument.",
            "minimum_fix_to_reconsider": None,
            "falsifier_spec": None,
            "human_review_question": "Should this proceed to paper phase?",
        },
    }
    row.update(kwargs)
    return row


def _base_paper_monitor(**kwargs) -> dict:
    row = {
        "schema": "research_factory.paper_monitor.v1",
        "authority": "display_only",
        "candidate_id": "rf-20260706-oracle-test-001",
        "as_of": "2026-07-06",
        "paper_status": "warmup",
        "expected_metric": {"name": "win_rate", "value": 0.58, "source": "domain_gate"},
        "observed_metric": {"name": "win_rate", "value": 0.55, "n": 10},
        "expected_fire_rate_pm": "not_applicable",
        "observed_fire_rate_pm": None,
        "regime_at_entry": {"regime": "risk_on", "vix_pctile": 34, "launched_hot": False},
        "falsifier_ref": None,
        "falsifier_verdict": None,
        "data_health_flags": [],
        "decay_flags": [],
        "action": "continue",
        "note": "display-only; no scored-path authority",
    }
    row.update(kwargs)
    return row


def _base_health(**kwargs) -> dict:
    row = {
        "schema": "research_factory.health.v1",
        "authority": "display_only",
        "as_of": "2026-07-06",
        "funnel_counts": {},
        "kill_reason_histogram": {},
        "challenger_advisory_vs_human": {},
        "median_dwell_days": {},
        "respin_generation_histogram": {},
        "per_source_acceptance_rates": {},
    }
    row.update(kwargs)
    return row


# ---------------------------------------------------------------------------
# 1. Authority field required on every schema
# ---------------------------------------------------------------------------

class TestAuthorityRequired:

    def test_candidate_missing_authority(self):
        row = _base_candidate()
        del row["authority"]
        errs = validate_candidate(row)
        assert any("authority" in e for e in errs), (
            f"Expected authority violation, got: {errs}"
        )

    def test_candidate_wrong_authority(self):
        row = _base_candidate(authority="scored")
        errs = validate_candidate(row)
        assert any("display_only" in e for e in errs)

    def test_transition_missing_authority(self):
        row = _base_transition()
        del row["authority"]
        errs = validate_transition(row)
        assert any("authority" in e for e in errs)

    def test_challenge_missing_authority(self):
        row = _base_challenge()
        del row["authority"]
        errs = validate_challenge(row)
        assert any("authority" in e for e in errs)

    def test_paper_monitor_missing_authority(self):
        row = _base_paper_monitor()
        del row["authority"]
        errs = validate_paper_monitor(row)
        assert any("authority" in e for e in errs)

    def test_health_missing_authority(self):
        row = _base_health()
        del row["authority"]
        errs = validate_health(row)
        assert any("authority" in e for e in errs)


# ---------------------------------------------------------------------------
# 2. rf.* family regex
# ---------------------------------------------------------------------------

class TestRfFamilyRegex:

    @pytest.mark.parametrize("name,should_pass", [
        ("rf.oracle.washout_flow",     True),
        ("rf.entry.momentum_v1",       True),
        ("rf.alpha.reversal_alpha",    True),
        ("rf.factor.sector_rot",       True),
        # Invalid: no rf. prefix
        ("oracle.washout_flow",        False),
        # Invalid: too short (only one dot-segment)
        ("rf.oracle",                  False),
        # Invalid: uppercase
        ("rf.Oracle.washout_flow",     False),
        # Invalid: special chars
        ("rf.oracle.washout-flow",     False),
        # Invalid: >=40 chars
        ("rf.oracle." + "a" * 32,      False),
        # Valid boundary: exactly 39 chars
        ("rf.aa." + "b" * 33,          True),
    ])
    def test_regex(self, name, should_pass):
        result = is_valid_rf_family_name(name)
        assert result == should_pass, (
            f"is_valid_rf_family_name({name!r}) returned {result}, expected {should_pass}"
        )

    def test_production_family_collision(self, tmp_path):
        """An rf.* name that matches a production family in trial_ledger.jsonl raises."""
        ledger = tmp_path / "trial_ledger.jsonl"
        ledger.write_text(
            json.dumps({"family": "rf.oracle.existing_prod", "config_hash": "abc"}) + "\n"
        )
        errs = validate_rf_family("rf.oracle.existing_prod", ledger_path=ledger)
        assert any("collides" in e for e in errs), (
            f"Expected collision error, got: {errs}"
        )

    def test_no_collision_when_absent(self, tmp_path):
        """Absent ledger should not produce collision error."""
        ledger = tmp_path / "no_such_file.jsonl"
        errs = validate_rf_family("rf.oracle.new_family", ledger_path=ledger)
        assert not any("collides" in e for e in errs)

    def test_new_rf_family_passes(self, tmp_path):
        """A valid rf.* name not in the ledger passes."""
        ledger = tmp_path / "trial_ledger.jsonl"
        ledger.write_text(
            json.dumps({"family": "oracle.compound_a", "config_hash": "abc"}) + "\n"
        )
        errs = validate_rf_family("rf.entry.new_idea", ledger_path=ledger)
        assert errs == [], f"Expected no errors, got: {errs}"


# ---------------------------------------------------------------------------
# 3. Schema round-trips (valid rows produce no violations)
# ---------------------------------------------------------------------------

class TestSchemaRoundTrips:

    def test_candidate_valid(self):
        row = _base_candidate()
        assert validate_candidate(row) == []

    def test_transition_valid(self):
        row = _base_transition()
        assert validate_transition(row) == []

    def test_transition_human_actor_valid(self):
        row = _base_transition(actor="fable", actor_ref="session/PR-9999")
        assert validate_transition(row) == []

    def test_challenge_valid(self):
        row = _base_challenge()
        assert validate_challenge(row) == []

    def test_paper_monitor_valid(self):
        row = _base_paper_monitor()
        assert validate_paper_monitor(row) == []

    def test_health_valid(self):
        row = _base_health()
        assert validate_health(row) == []


# ---------------------------------------------------------------------------
# 4. Invalid candidate_type rejected
# ---------------------------------------------------------------------------

class TestCandidateTypeEnum:

    def test_invalid_candidate_type(self):
        row = _base_candidate(candidate_type="magic_signal")
        errs = validate_candidate(row)
        assert any("candidate_type" in e for e in errs)

    @pytest.mark.parametrize("ctype", sorted(CANDIDATE_TYPES))
    def test_all_valid_candidate_types_pass(self, ctype):
        row = _base_candidate(candidate_type=ctype)
        errs = validate_candidate(row)
        assert not any("candidate_type" in e for e in errs), (
            f"candidate_type={ctype!r} unexpectedly flagged: {errs}"
        )


# ---------------------------------------------------------------------------
# 5. claim_shape passthrough (nullable; metabolism-only values allowed)
# ---------------------------------------------------------------------------

class TestClaimShape:

    def test_null_claim_shape_passes(self):
        row = _base_candidate(claim_shape=None)
        assert validate_candidate(row) == []

    @pytest.mark.parametrize("shape", sorted(CLAIM_SHAPES))
    def test_valid_claim_shapes_pass(self, shape):
        row = _base_candidate(claim_shape=shape)
        errs = validate_candidate(row)
        assert not any("claim_shape" in e for e in errs), (
            f"claim_shape={shape!r} unexpectedly flagged: {errs}"
        )

    def test_invented_claim_shape_rejected(self):
        row = _base_candidate(claim_shape="oracle_compound")
        errs = validate_candidate(row)
        assert any("claim_shape" in e for e in errs), (
            "Expected claim_shape error for invented value 'oracle_compound'"
        )

    def test_arbitrary_claim_shape_rejected(self):
        row = _base_candidate(claim_shape="my_custom_shape")
        errs = validate_candidate(row)
        assert any("claim_shape" in e for e in errs)


# ---------------------------------------------------------------------------
# 6. keep_first semantics (ledger.py)
# ---------------------------------------------------------------------------

class TestKeepFirst:

    def test_keep_first_basic(self):
        rows = [
            {"candidate_id": "A", "as_of": "2026-01-01", "val": 1},
            {"candidate_id": "A", "as_of": "2026-01-01", "val": 2},  # dup — dropped
            {"candidate_id": "A", "as_of": "2026-01-02", "val": 3},
        ]
        result = keep_first(rows, ("candidate_id", "as_of"))
        assert len(result) == 2
        assert result[0]["val"] == 1
        assert result[1]["val"] == 3

    def test_keep_first_preserves_order(self):
        rows = [
            {"k": "x", "n": 0},
            {"k": "y", "n": 1},
            {"k": "x", "n": 2},  # dup — dropped
            {"k": "z", "n": 3},
        ]
        result = keep_first(rows, ("k",))
        assert [r["n"] for r in result] == [0, 1, 3]

    def test_keep_first_empty_input(self):
        assert keep_first([], ("k",)) == []

    def test_keep_first_all_unique(self):
        rows = [{"k": i, "v": i} for i in range(5)]
        assert keep_first(rows, ("k",)) == rows


# ---------------------------------------------------------------------------
# 7. append_row and write_jsonl authority enforcement
# ---------------------------------------------------------------------------

class TestLedgerAuthority:

    def test_append_row_requires_display_only(self, tmp_path):
        path = tmp_path / "test.jsonl"
        row = {"authority": "scored", "candidate_id": "x"}
        with pytest.raises(ValueError, match="display_only"):
            append_row(path, row)

    def test_append_row_missing_authority(self, tmp_path):
        path = tmp_path / "test.jsonl"
        row = {"candidate_id": "x"}
        with pytest.raises(ValueError, match="display_only"):
            append_row(path, row)

    def test_append_row_success(self, tmp_path):
        path = tmp_path / "test.jsonl"
        row = {"authority": "display_only", "candidate_id": "x", "data": 1}
        append_row(path, row)
        loaded = load_jsonl(path)
        assert len(loaded) == 1
        assert loaded[0]["candidate_id"] == "x"

    def test_write_jsonl_wrong_authority_raises(self, tmp_path):
        path = tmp_path / "test.jsonl"
        rows = [{"authority": "display_only", "k": 1},
                {"authority": "scored",       "k": 2}]
        with pytest.raises(ValueError, match="display_only"):
            write_jsonl(path, rows)

    def test_write_jsonl_atomic(self, tmp_path):
        path = tmp_path / "out.jsonl"
        rows = [{"authority": "display_only", "k": i} for i in range(3)]
        write_jsonl(path, rows)
        loaded = load_jsonl(path)
        assert [r["k"] for r in loaded] == [0, 1, 2]

    def test_load_jsonl_absent_file(self, tmp_path):
        assert load_jsonl(tmp_path / "ghost.jsonl") == []

    def test_load_jsonl_tolerates_torn_line(self, tmp_path):
        path = tmp_path / "torn.jsonl"
        path.write_text('{"a":1}\n{BROKEN\n{"b":2}\n')
        rows = load_jsonl(path)
        assert len(rows) == 2
        assert rows[0]["a"] == 1
        assert rows[1]["b"] == 2


# ---------------------------------------------------------------------------
# 8. Planted violation: check_research_factory_authority.py detects forbidden read
# ---------------------------------------------------------------------------

class TestAuthorityGuardPlantedViolation:
    """Prove the authority guard script detects a forbidden read in a fixture."""

    def test_article2_forbidden_read_detected(self, tmp_path):
        """A planted Article-2 module reading factory data must be detected as HARD."""
        # Import the scan function directly (no subprocess needed)
        from scripts.check_research_factory_authority import scan

        # Plant: an Article-2 module (alert_triage) reads factory data
        synthetic = {
            "engine/alert_triage.py": (
                "import json\n"
                'path = "data/research_factory/candidates.jsonl"\n'
                "data = json.load(open(path))\n"
            ),
        }
        findings = scan(tmp_path, extra_files=synthetic)
        hard = [f for f in findings if f["severity"] == "HARD"]
        assert hard, (
            "Expected HARD finding for Article-2 module reading factory data; "
            f"got findings: {findings}"
        )
        assert any(f["module"] == "engine/alert_triage.py" for f in hard)

    def test_non_article2_forbidden_read_detected_as_warn(self, tmp_path):
        """A non-Article-2 module reading factory data is WARN, not HARD."""
        from scripts.check_research_factory_authority import scan

        synthetic = {
            "engine/some_display_module.py": (
                "import json\n"
                'path = "data/research_factory/transitions.jsonl"\n'
                "data = json.load(open(path))\n"
            ),
        }
        findings = scan(tmp_path, extra_files=synthetic)
        warn = [f for f in findings if f["severity"] == "WARN"]
        hard = [f for f in findings if f["severity"] == "HARD"]
        assert warn, f"Expected WARN finding; got: {findings}"
        assert not hard, f"Expected no HARD finding; got: {hard}"

    def test_clean_module_not_detected(self, tmp_path):
        """A module with no factory reference produces no findings."""
        from scripts.check_research_factory_authority import scan

        synthetic = {
            "engine/alert_triage.py": (
                "import json\n"
                'path = "data/regime/latest.json"\n'
                "data = json.load(open(path))\n"
            ),
        }
        findings = scan(tmp_path, extra_files=synthetic)
        assert not findings, f"Expected no findings; got: {findings}"

    def test_import_token_detected(self, tmp_path):
        """The import token 'engine.research_factory' is also detected."""
        from scripts.check_research_factory_authority import scan

        synthetic = {
            "engine/alert_triage.py": (
                "from engine.research_factory import load_jsonl\n"
                "data = load_jsonl('data/research_factory/candidates.jsonl')\n"
            ),
        }
        findings = scan(tmp_path, extra_files=synthetic)
        hard = [f for f in findings if f["severity"] == "HARD"]
        assert hard, (
            "Expected HARD finding for import of engine.research_factory in Article-2 module"
        )

    def test_allowlisted_module_skipped(self, tmp_path):
        """A module in the allowlist is exempted from findings."""
        from scripts.check_research_factory_authority import scan

        # Write an allowlist that exempts engine/alert_triage.py
        allowlist_path = tmp_path / "data" / "research_factory" / "authority_allowlist.json"
        allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        allowlist_path.write_text(
            json.dumps({"allow": [{"module": "engine/alert_triage.py", "reason": "test"}]})
        )

        synthetic = {
            "engine/alert_triage.py": (
                "import json\n"
                'path = "data/research_factory/candidates.jsonl"\n'
                "data = json.load(open(path))\n"
            ),
        }
        findings = scan(tmp_path, extra_files=synthetic)
        assert not findings, f"Expected no findings for allowlisted module; got: {findings}"


# ---------------------------------------------------------------------------
# 9. Transition actor_ref validation
# ---------------------------------------------------------------------------

class TestTransitionActorRef:

    def test_human_actor_without_actor_ref_fails(self):
        row = _base_transition(actor="fable", actor_ref=None)
        errs = validate_transition(row)
        assert any("actor_ref" in e for e in errs)

    def test_human_actor_with_actor_ref_passes(self):
        row = _base_transition(actor="fable", actor_ref="session/PR-9999")
        errs = validate_transition(row)
        assert not any("actor_ref" in e for e in errs)

    def test_script_actor_no_actor_ref_required(self):
        row = _base_transition(actor="script", actor_ref=None)
        errs = validate_transition(row)
        assert not any("actor_ref" in e for e in errs)


# ---------------------------------------------------------------------------
# 10. RF-15: lineage generation cap
# ---------------------------------------------------------------------------

class TestLineageGenerationCap:

    def test_generation_2_passes(self):
        row = _base_candidate(lineage={"refinement_generation": 2, "respin_of": None, "superseded_by": None})
        errs = validate_candidate(row)
        assert not any("refinement_generation" in e for e in errs)

    def test_generation_3_rejected(self):
        row = _base_candidate(lineage={"refinement_generation": 3, "respin_of": None, "superseded_by": None})
        errs = validate_candidate(row)
        assert any("generation" in e.lower() or "cap" in e.lower() for e in errs), (
            f"Expected generation cap error, got: {errs}"
        )

    def test_generation_0_passes(self):
        row = _base_candidate(lineage={"refinement_generation": 0, "respin_of": None, "superseded_by": None})
        assert validate_candidate(row) == []


# ---------------------------------------------------------------------------
# 11. Challenge reviewer: no confidence scores
# ---------------------------------------------------------------------------

class TestChallengeReviewerNoConfidenceScore:

    def test_confidence_score_rejected(self):
        row = _base_challenge()
        row["reviewer"]["confidence_score"] = 0.85
        errs = validate_challenge(row)
        assert any("confidence_score" in e for e in errs)

    def test_invalid_recommendation_rejected(self):
        row = _base_challenge()
        row["reviewer"]["recommendation"] = "REJECT"
        errs = validate_challenge(row)
        assert any("recommendation" in e for e in errs)

    def test_invalid_blocker_severity_rejected(self):
        row = _base_challenge()
        row["reviewer"]["blockers"] = [{"severity": "critical", "category": "lookahead", "finding": "x"}]
        errs = validate_challenge(row)
        assert any("severity" in e for e in errs)
