"""tests/test_research_factory_state.py — State machine tests for engine.research_factory.state.

Tests (per W1 charter §6):
  1. Every §4 illegal transition raises IllegalTransition.
  2. Actor law: script actors into human-gate target states raise.
  3. Actor law: human actor without actor_ref raises.
  4. screened-without-trial-accounting refused.
  5. screened with trial_accounting set and non-rf_family mode passes.
  6. screened with rf_family mode and no declared family in ledger raises.
  7. Terminal states have no outgoing transitions.
  8. All allowed transitions in the matrix pass (smoke test).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from engine.research_factory.state import (
    ALLOWED_TRANSITIONS,
    MODEL_ADJUDICATORS,
    IllegalTransition,
    transition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transition_row(**kwargs) -> dict:
    """Build a minimal valid transition row, overridable via kwargs."""
    row = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": "rf-test-001",
        "from": "proposed",
        "to": "registered",
        "reason_code": "valid_schema",
        "actor": "script",
        "actor_ref": None,
        "as_of": "2026-07-06T00:00:00Z",
        "artifact_refs": [],
        "kill_evidence": None,
    }
    row.update(kwargs)
    return row


def _make_candidate(**kwargs) -> dict:
    """Build a minimal candidate dict."""
    c = {
        "candidate_id": "rf-test-001",
        "trial_accounting": {"mode": "read_only", "family": None},
        "status": "proposed",
    }
    c.update(kwargs)
    return c


def _write_ledger_with_declared(family: str) -> str:
    """Write a temp trial_ledger.jsonl with a declared_budget row for family."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps({
            "family": family,
            "kind": "declared_budget",
            "n": 10,
            "config_hash": "abc123",
        }) + "\n")
    return path


# ---------------------------------------------------------------------------
# 1. Illegal pairs raise IllegalTransition
# ---------------------------------------------------------------------------

class TestIllegalTransitions:
    """Every pair NOT in the allowed matrix must raise."""

    def test_proposed_to_paper_raises(self):
        row = _make_transition_row(**{
            "from": "proposed", "to": "paper",
            "actor": "fable", "actor_ref": "session/PR-test",
        })
        with pytest.raises(IllegalTransition, match="not in the allowed-transition matrix"):
            transition("proposed", "paper", "fable", row)

    def test_screened_to_paper_raises(self):
        row = _make_transition_row(**{
            "from": "screened", "to": "paper", "actor": "fable",
            "actor_ref": "session/PR-test",
        })
        with pytest.raises(IllegalTransition, match="not in the allowed-transition matrix"):
            transition("screened", "paper", "fable", row)

    def test_registered_to_challenged_raises(self):
        row = _make_transition_row(**{"from": "registered", "to": "challenged"})
        with pytest.raises(IllegalTransition, match="not in the allowed-transition matrix"):
            transition("registered", "challenged", "script", row)

    def test_rejected_to_proposed_raises(self):
        """Terminal state rejected has no outgoing transitions."""
        row = _make_transition_row(**{"from": "rejected", "to": "proposed"})
        with pytest.raises(IllegalTransition):
            transition("rejected", "proposed", "script", row)

    def test_paper_to_registered_raises(self):
        row = _make_transition_row(**{
            "from": "paper", "to": "registered",
            "actor": "fable", "actor_ref": "session/PR-test",
        })
        with pytest.raises(IllegalTransition, match="not in the allowed-transition matrix"):
            transition("paper", "registered", "fable", row)

    def test_human_review_to_screened_raises(self):
        row = _make_transition_row(**{
            "from": "human_review", "to": "screened",
            "actor": "fable", "actor_ref": "session/PR-test",
        })
        with pytest.raises(IllegalTransition, match="not in the allowed-transition matrix"):
            transition("human_review", "screened", "fable", row)

    def test_unknown_from_state_raises(self):
        row = _make_transition_row(**{"from": "nonexistent", "to": "registered"})
        with pytest.raises(IllegalTransition, match="unknown from_state"):
            transition("nonexistent", "registered", "script", row)

    def test_unknown_to_state_raises(self):
        row = _make_transition_row(**{"from": "proposed", "to": "flying"})
        with pytest.raises(IllegalTransition, match="unknown to_state"):
            transition("proposed", "flying", "script", row)


# ---------------------------------------------------------------------------
# 2. Script actor into human-gate targets raises
# ---------------------------------------------------------------------------

class TestActorLaw:
    """Script actors must not drive human-gate target states (RF-5)."""

    @pytest.mark.parametrize("to_state", [
        "paper", "deferred", "rejected", "scoped_build", "retired",
    ])
    def test_script_actor_into_human_target_raises(self, to_state):
        # Find a valid from_state for each human-gate target
        from_map = {
            "paper": "human_review",
            "deferred": "human_review",
            "rejected": "human_review",
            "scoped_build": "human_review",
            "retired": "paper",
        }
        from_state = from_map[to_state]
        row = _make_transition_row(**{
            "from": from_state,
            "to": to_state,
            "actor": "script",
            # supply mandatory fields to not confound with missing-field errors
            "kill_evidence": {"n_at_kill": 5, "kill_class": "falsified"},
            "come_back_on": "2027-01-01",
            "program_doc_ref": "research/foo.md",
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        with pytest.raises(IllegalTransition, match="script class.*not permitted"):
            transition(from_state, to_state, "script", row)

    @pytest.mark.parametrize("to_state", ["paper", "deferred", "rejected"])
    def test_sonnet_actor_into_human_target_raises(self, to_state):
        """codex/sonnet also count as script class."""
        from_map = {
            "paper": "human_review",
            "deferred": "human_review",
            "rejected": "human_review",
        }
        from_state = from_map[to_state]
        row = _make_transition_row(**{
            "from": from_state,
            "to": to_state,
            "actor": "sonnet",
            "kill_evidence": {"n_at_kill": 5, "kill_class": "falsified"},
            "come_back_on": "2027-01-01",
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        with pytest.raises(IllegalTransition, match="script class.*not permitted"):
            transition(from_state, to_state, "sonnet", row)

    def test_human_actor_paper_without_actor_ref_raises(self):
        """Human actors require actor_ref (RF-5)."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "paper",
            "actor": "fable",
            "actor_ref": None,   # missing!
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        with pytest.raises(IllegalTransition, match="actor_ref.*required"):
            transition("human_review", "paper", "fable", row)

    def test_operator_actor_rejected_without_actor_ref_raises(self):
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "rejected",
            "actor": "operator",
            "actor_ref": "",   # empty = missing
            "kill_evidence": {"n_at_kill": 5, "kill_class": "falsified"},
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        with pytest.raises(IllegalTransition, match="actor_ref.*required"):
            transition("human_review", "rejected", "operator", row)

    def test_unknown_actor_raises(self):
        row = _make_transition_row(**{"actor": "robot"})
        with pytest.raises(IllegalTransition, match="not a known actor class"):
            transition("proposed", "registered", "robot", row)

    def test_human_actor_with_actor_ref_passes(self):
        """Valid human gate: fable + actor_ref + correct to-state."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "rejected",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            "kill_evidence": {"n_at_kill": 10, "kill_class": "duplicate"},
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        # Should not raise
        transition("human_review", "rejected", "fable", row)


# ---------------------------------------------------------------------------
# 3. screened-without-trial-accounting refused (RF-6)
# ---------------------------------------------------------------------------

class TestScreenedGate:

    def test_screened_refused_without_trial_accounting(self):
        """Candidate with no trial_accounting must be refused for screened."""
        candidate = _make_candidate(trial_accounting=None)
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
        })
        with pytest.raises(IllegalTransition, match="trial_accounting must be set"):
            transition("registered", "screened", "script", row, candidate=candidate)

    def test_screened_refused_without_mode(self):
        """trial_accounting without mode is refused."""
        candidate = _make_candidate(trial_accounting={"mode": None, "family": None})
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["x"],
        })
        with pytest.raises(IllegalTransition, match="trial_accounting.mode.*must be set"):
            transition("registered", "screened", "script", row, candidate=candidate)

    def test_screened_passes_with_read_only(self):
        """read_only mode requires no ledger entry."""
        candidate = _make_candidate(trial_accounting={"mode": "read_only", "family": None})
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
        })
        # Should not raise
        transition("registered", "screened", "script", row, candidate=candidate)

    def test_screened_rf_family_no_declared_budget_raises(self, tmp_path):
        """rf_family mode with no declaration in ledger is refused.

        A row with neither kind=='declared_budget' nor a config_hash does NOT
        satisfy the RF-6 gate (it is e.g. a metadata/comment row, not a
        grid/trial or declared-budget row).
        """
        ledger = tmp_path / "trial_ledger.jsonl"
        # Write a row with NO config_hash and no kind=='declared_budget' —
        # must not satisfy the gate.
        ledger.write_text(
            json.dumps({"family": "rf.test.foo", "note": "metadata only"}) + "\n"
        )
        candidate = _make_candidate(trial_accounting={
            "mode": "rf_family",
            "family": "rf.test.foo",
            "declared_at": None,
        })
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["x"],
        })
        with pytest.raises(IllegalTransition, match="no declared-budget/grid row"):
            transition("registered", "screened", "script", row,
                       candidate=candidate, ledger_path=ledger)

    def test_screened_rf_family_grid_row_passes(self, tmp_path):
        """rf_family mode passes when a log_grid()/log_trial() row exists.

        RF-6 permits declaration via log_grid()/log_trial() (rows carry
        config_hash but no kind=='declared_budget').  A candidate whose
        budget was declared by logging the actual grid must be accepted.
        """
        ledger = tmp_path / "trial_ledger.jsonl"
        # Write a row as log_trial() would — family + config_hash, no 'kind' field
        ledger.write_text(
            json.dumps({"family": "rf.test.foo", "config_hash": "abc123",
                        "config": {"window": 20}}) + "\n"
        )
        candidate = _make_candidate(trial_accounting={
            "mode": "rf_family",
            "family": "rf.test.foo",
            "declared_at": None,
        })
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["x"],
        })
        # Should not raise — grid row satisfies the RF-6 gate
        transition("registered", "screened", "script", row,
                   candidate=candidate, ledger_path=ledger)

    def test_screened_rf_family_with_declared_budget_passes(self, tmp_path):
        """rf_family mode passes when declared_budget row exists."""
        ledger_path = _write_ledger_with_declared("rf.test.foo")
        try:
            candidate = _make_candidate(trial_accounting={
                "mode": "rf_family",
                "family": "rf.test.foo",
                "declared_at": "2026-07-06",
            })
            row = _make_transition_row(**{
                "from": "registered",
                "to": "screened",
                "actor": "script",
                "artifact_refs": ["x"],
            })
            # Should not raise
            transition("registered", "screened", "script", row,
                       candidate=candidate, ledger_path=ledger_path)
        finally:
            os.unlink(ledger_path)

    def test_screened_rf_family_absent_ledger_raises(self, tmp_path):
        """Absent trial ledger + rf_family mode = refused (no declared families)."""
        ledger = tmp_path / "nonexistent_ledger.jsonl"
        candidate = _make_candidate(trial_accounting={
            "mode": "rf_family",
            "family": "rf.test.bar",
            "declared_at": None,
        })
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["x"],
        })
        with pytest.raises(IllegalTransition, match="no declared-budget/grid row"):
            transition("registered", "screened", "script", row,
                       candidate=candidate, ledger_path=ledger)


# ---------------------------------------------------------------------------
# 4. Terminal states
# ---------------------------------------------------------------------------

_TERMINAL_STATES = [
    "schema_rejected", "deduped", "numeric_rejected",
    "scoped_build", "rejected", "retired",
]


class TestTerminalStates:
    @pytest.mark.parametrize("state", _TERMINAL_STATES)
    def test_terminal_state_has_no_allowed_next(self, state):
        """Terminal states have an empty allowed-transition set."""
        assert ALLOWED_TRANSITIONS[state] == frozenset(), (
            f"{state} should be terminal (empty allowed set)"
        )


# ---------------------------------------------------------------------------
# 5. Mandatory-field enforcement
# ---------------------------------------------------------------------------

class TestMandatoryFields:

    def test_awaiting_data_without_come_back_on_raises(self):
        row = _make_transition_row(**{
            "from": "registered",
            "to": "awaiting_data",
            "actor": "script",
            # come_back_on intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("registered", "awaiting_data", "script", row)

    def test_awaiting_data_with_come_back_on_passes(self):
        row = _make_transition_row(**{
            "from": "registered",
            "to": "awaiting_data",
            "actor": "script",
            "come_back_on": "2027-01-01",
        })
        transition("registered", "awaiting_data", "script", row)

    def test_numeric_rejected_without_kill_evidence_raises(self):
        row = _make_transition_row(**{
            "from": "screened",
            "to": "numeric_rejected",
            "actor": "script",
            # kill_evidence intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("screened", "numeric_rejected", "script", row)

    def test_scoped_build_without_program_doc_ref_raises(self):
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "scoped_build",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            "review_packet_ref": "data/research_factory/review/test.json",
            # program_doc_ref intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("human_review", "scoped_build", "fable", row)

    def test_screened_without_artifact_refs_raises(self):
        """screened requires artifact_refs in the transition row."""
        candidate = _make_candidate(trial_accounting={"mode": "read_only", "family": None})
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            # artifact_refs intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("registered", "screened", "script", row, candidate=candidate)

    def test_deferred_without_come_back_on_raises(self):
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "deferred",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            "review_packet_ref": "data/research_factory/review/test.json",
            # come_back_on intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("human_review", "deferred", "fable", row)

    def test_paper_without_seed_entry_ref_raises(self):
        """paper requires seed_entry_ref, regime_at_entry, expected_half_life_d (§4)."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "paper",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            "review_packet_ref": "data/research_factory/review/test.json",
            # seed_entry_ref / regime_at_entry / expected_half_life_d intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("human_review", "paper", "fable", row)

    def test_paper_with_all_mandatory_fields_passes(self):
        """paper with all §4-mandatory fields present must not raise."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "paper",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            "review_packet_ref": "data/research_factory/review/test.json",
            "seed_entry_ref": "data/research_factory/seeds/rf-test-001.json",
            "regime_at_entry": "bull",
            "expected_half_life_d": 90,
        })
        # Should not raise
        transition("human_review", "paper", "fable", row)

    def test_promote_eligible_without_promotion_gate_ref_raises(self):
        """promote_eligible requires promotion_gate_ref (§4)."""
        row = _make_transition_row(**{
            "from": "paper",
            "to": "promote_eligible",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            # promotion_gate_ref intentionally absent
        })
        with pytest.raises(IllegalTransition, match="missing mandatory field"):
            transition("paper", "promote_eligible", "fable", row)

    def test_promote_eligible_with_promotion_gate_ref_passes(self):
        """promote_eligible with promotion_gate_ref present must not raise."""
        row = _make_transition_row(**{
            "from": "paper",
            "to": "promote_eligible",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
            "promotion_gate_ref": "data/research_factory/gates/rf-test-001.json",
        })
        # Should not raise
        transition("paper", "promote_eligible", "fable", row)


# ---------------------------------------------------------------------------
# 4b. Monotonic as_of enforcement
# ---------------------------------------------------------------------------

class TestMonotonicAsOf:

    def test_non_monotonic_as_of_raises(self):
        """A transition as_of earlier than the last log entry must raise."""
        candidate = _make_candidate(transition_log=[
            {"as_of": "2026-07-06T12:00:00Z", "from": "proposed", "to": "registered"},
        ])
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
            "as_of": "2026-07-06T10:00:00Z",  # earlier than last log
        })
        with pytest.raises(IllegalTransition, match="non-monotonic as_of"):
            transition("registered", "screened", "script", row,
                       candidate=candidate)

    def test_same_as_of_passes(self):
        """Same as_of as last log entry is allowed (>=)."""
        candidate = _make_candidate(trial_accounting={"mode": "read_only", "family": None},
                                    transition_log=[
                                        {"as_of": "2026-07-06T12:00:00Z"},
                                    ])
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
            "as_of": "2026-07-06T12:00:00Z",  # same — allowed
        })
        transition("registered", "screened", "script", row, candidate=candidate)

    def test_later_as_of_passes(self):
        """A later as_of is always allowed."""
        candidate = _make_candidate(trial_accounting={"mode": "read_only", "family": None},
                                    transition_log=[
                                        {"as_of": "2026-07-06T00:00:00Z"},
                                    ])
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
            "as_of": "2026-07-07T00:00:00Z",  # later — allowed
        })
        transition("registered", "screened", "script", row, candidate=candidate)

    def test_empty_transition_log_skips_check(self):
        """Empty transition_log means no monotonic constraint."""
        candidate = _make_candidate(trial_accounting={"mode": "read_only", "family": None},
                                    transition_log=[])
        row = _make_transition_row(**{
            "from": "registered",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["x"],
            "as_of": "2020-01-01T00:00:00Z",  # very old — no prior log to compare
        })
        transition("registered", "screened", "script", row, candidate=candidate)


# ---------------------------------------------------------------------------
# 4c. Respin human-gate (RF-5/RF-15)
# ---------------------------------------------------------------------------

class TestRespinHumanGate:

    def test_script_actor_respin_registration_raises(self):
        """A script actor may not register a respin candidate (lineage.respin_of set)."""
        candidate = _make_candidate(
            lineage={"respin_of": "rf-test-parent-001", "superseded_by": None,
                     "refinement_generation": 1},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": "script",
        })
        with pytest.raises(IllegalTransition, match="respin"):
            transition("proposed", "registered", "script", row, candidate=candidate)

    @pytest.mark.parametrize("script_actor", ["codex", "sonnet"])
    def test_codex_sonnet_respin_registration_raises(self, script_actor):
        """codex/sonnet are also script-class and must not register respins."""
        candidate = _make_candidate(
            lineage={"respin_of": "rf-test-parent-001", "superseded_by": None,
                     "refinement_generation": 1},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": script_actor,
        })
        with pytest.raises(IllegalTransition, match="respin"):
            transition("proposed", "registered", script_actor, row, candidate=candidate)

    def test_human_actor_respin_registration_with_actor_ref_passes(self):
        """fable actor with actor_ref may register a respin candidate."""
        candidate = _make_candidate(
            lineage={"respin_of": "rf-test-parent-001", "superseded_by": None,
                     "refinement_generation": 1},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": "fable",
            "actor_ref": "session/PR-9999",
        })
        # Should not raise
        transition("proposed", "registered", "fable", row, candidate=candidate)

    def test_operator_actor_respin_registration_with_actor_ref_passes(self):
        """operator actor with actor_ref may register a respin candidate."""
        candidate = _make_candidate(
            lineage={"respin_of": "rf-test-parent-001", "superseded_by": None,
                     "refinement_generation": 1},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": "operator",
            "actor_ref": "PR-8888",
        })
        transition("proposed", "registered", "operator", row, candidate=candidate)

    def test_script_non_respin_registration_passes(self):
        """A script actor may register a non-respin candidate (respin_of=None)."""
        candidate = _make_candidate(
            lineage={"respin_of": None, "superseded_by": None, "refinement_generation": 0},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": "script",
        })
        # Should not raise
        transition("proposed", "registered", "script", row, candidate=candidate)

    def test_deferred_to_human_review_script_allowed(self):
        """deferred→human_review is clock resurfacing — script is allowed."""
        row = _make_transition_row(**{
            "from": "deferred",
            "to": "human_review",
            "actor": "script",
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        # Should not raise — clock resurfacing is mechanical A2 attention-routing
        transition("deferred", "human_review", "script", row)

    def test_awaiting_data_to_registered_script_allowed(self):
        """awaiting_data→registered is clock resurfacing — script is allowed."""
        row = _make_transition_row(**{
            "from": "awaiting_data",
            "to": "registered",
            "actor": "script",
        })
        # Should not raise — clock resurfacing is mechanical
        transition("awaiting_data", "registered", "script", row)

    def test_awaiting_data_to_screened_script_allowed(self):
        """awaiting_data→screened is clock resurfacing — script is allowed."""
        candidate = _make_candidate(trial_accounting={"mode": "read_only", "family": None})
        row = _make_transition_row(**{
            "from": "awaiting_data",
            "to": "screened",
            "actor": "script",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
        })
        transition("awaiting_data", "screened", "script", row, candidate=candidate)


# ---------------------------------------------------------------------------
# 6. Smoke: all allowed transitions in the matrix pass validation (no false positives)
# ---------------------------------------------------------------------------

class TestAllowedTransitionsSmoke:
    """Every pair in ALLOWED_TRANSITIONS must pass (not raise) with a valid row."""

    def _row_for(self, from_state: str, to_state: str) -> dict:
        """Build the minimum valid transition row for a given pair."""
        actor = "fable"
        actor_ref = "session/PR-smoke"
        if to_state not in {"paper", "deferred", "rejected", "scoped_build", "retired"}:
            actor = "script"
            actor_ref = None

        return {
            "schema": "research_factory.transition.v1",
            "authority": "display_only",
            "candidate_id": "rf-smoke-001",
            "from": from_state,
            "to": to_state,
            "actor": actor,
            "actor_ref": actor_ref,
            "as_of": "2026-07-06T00:00:00Z",
            # Provide all potentially-mandatory fields (§4 table)
            "come_back_on": "2027-01-01",
            "kill_evidence": {"n_at_kill": 5, "kill_class": "falsified"},
            "program_doc_ref": "research/FOO_PROGRAM.md",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
            "challenge_packet_ref": "data/research_factory/challenges/rf-smoke-001.json",
            "review_packet_ref": "data/research_factory/review/rf-smoke-001.json",
            # paper mandatory fields (§4)
            "seed_entry_ref": "data/research_factory/seeds/rf-smoke-001.json",
            "regime_at_entry": "bull",
            "expected_half_life_d": 90,
            # promote_eligible mandatory fields (§4)
            "promotion_gate_ref": "data/research_factory/gates/rf-smoke-001.json",
        }

    @pytest.mark.parametrize("from_state,to_states", [
        (fs, list(ts)) for fs, ts in ALLOWED_TRANSITIONS.items() if ts
    ])
    def test_allowed_pair_does_not_raise(self, from_state, to_states, tmp_path):
        """Each allowed (from, to) pair must not raise IllegalTransition."""
        for to_state in to_states:
            row = self._row_for(from_state, to_state)
            actor = row["actor"]
            # For screened transitions, supply a candidate with trial_accounting
            candidate = None
            if to_state == "screened":
                candidate = _make_candidate(
                    trial_accounting={"mode": "read_only", "family": None}
                )
            try:
                transition(from_state, to_state, actor, row, candidate=candidate)
            except IllegalTransition as exc:
                pytest.fail(
                    f"Allowed transition {from_state!r} → {to_state!r} raised "
                    f"IllegalTransition: {exc}"
                )


# ---------------------------------------------------------------------------
# 7. Model adjudicator (opus) — RF-5b / RUL-SUCC-7
# ---------------------------------------------------------------------------

class TestModelAdjudicatorRF5b:
    """Model adjudicator (opus) gate — RF-5b/RUL-SUCC-7 semantics."""

    def test_opus_to_paper_with_actor_ref_and_packet_ref_accepted(self):
        """opus with actor_ref + packet_ref may transition to a human-gate target."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "paper",
            "actor": "opus",
            "actor_ref": "opus-session-20260706",
            "packet_ref": "adj-2026-07-06-example",
            "review_packet_ref": "data/research_factory/review/test.json",
            "seed_entry_ref": "data/research_factory/seeds/rf-test-001.json",
            "regime_at_entry": "bull",
            "expected_half_life_d": 90,
        })
        # Should not raise — opus with both refs satisfies RF-5b
        transition("human_review", "paper", "opus", row)

    def test_opus_to_paper_missing_packet_ref_rejected(self):
        """opus without packet_ref must be rejected from human-gate targets (RF-5b)."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "paper",
            "actor": "opus",
            "actor_ref": "opus-session-20260706",
            # packet_ref intentionally absent
            "review_packet_ref": "data/research_factory/review/test.json",
            "seed_entry_ref": "data/research_factory/seeds/rf-test-001.json",
            "regime_at_entry": "bull",
            "expected_half_life_d": 90,
        })
        with pytest.raises(IllegalTransition, match="packet_ref"):
            transition("human_review", "paper", "opus", row)

    def test_opus_to_rejected_with_actor_ref_and_packet_ref_accepted(self):
        """opus may reject a candidate when both actor_ref and packet_ref are present."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "rejected",
            "actor": "opus",
            "actor_ref": "opus-session-20260706",
            "packet_ref": "adj-2026-07-06-example",
            "kill_evidence": {"n_at_kill": 12, "kill_class": "falsified"},
            "review_packet_ref": "data/research_factory/review/test.json",
        })
        # Should not raise
        transition("human_review", "rejected", "opus", row)

    def test_sonnet_with_packet_ref_still_rejected_from_human_gate(self):
        """packet_ref is NOT a loophole for script actors (sonnet must remain barred)."""
        row = _make_transition_row(**{
            "from": "human_review",
            "to": "paper",
            "actor": "sonnet",
            "actor_ref": "some-session",
            "packet_ref": "adj-2026-07-06-example",  # packet_ref does not help scripts
            "review_packet_ref": "data/research_factory/review/test.json",
            "seed_entry_ref": "data/research_factory/seeds/rf-test-001.json",
            "regime_at_entry": "bull",
            "expected_half_life_d": 90,
        })
        with pytest.raises(IllegalTransition, match="script class.*not permitted"):
            transition("human_review", "paper", "sonnet", row)

    def test_opus_respin_registration_rejected(self):
        """opus (model adjudicator) may NOT register a respin — respin remains human-only
        (RUL-SUCC-7 ruling: trial-spending commitment requires full human accountability)."""
        candidate = _make_candidate(
            lineage={"respin_of": "rf-test-parent-001", "superseded_by": None,
                     "refinement_generation": 1},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": "opus",
            "actor_ref": "opus-session-20260706",
            "packet_ref": "adj-2026-07-06-example",
        })
        with pytest.raises(IllegalTransition, match="respin"):
            transition("proposed", "registered", "opus", row, candidate=candidate)

    def test_opus_non_gate_transition_accepted_without_packet_ref(self):
        """For non-human-gate transitions, opus is treated like a script actor
        and needs no packet_ref (RF-5b: packet_ref only applies at human-gate targets)."""
        # proposed→registered is a non-human-gate transition; opus should be accepted
        # without packet_ref (just like script actors)
        candidate = _make_candidate(
            lineage={"respin_of": None, "superseded_by": None, "refinement_generation": 0},
        )
        row = _make_transition_row(**{
            "from": "proposed",
            "to": "registered",
            "actor": "opus",
            "actor_ref": None,   # not required for non-gate transitions
            # no packet_ref either
        })
        # Should not raise — non-gate transition with opus is unrestricted
        transition("proposed", "registered", "opus", row, candidate=candidate)

    def test_model_adjudicators_set_contains_opus(self):
        """Sanity: MODEL_ADJUDICATORS exports as expected."""
        assert "opus" in MODEL_ADJUDICATORS
        assert "fable" not in MODEL_ADJUDICATORS
        assert "script" not in MODEL_ADJUDICATORS
