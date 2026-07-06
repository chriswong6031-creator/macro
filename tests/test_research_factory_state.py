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
        """rf_family mode with no declared budget in ledger is refused."""
        ledger = tmp_path / "trial_ledger.jsonl"
        # Write a non-declared-budget row — should not satisfy the gate
        ledger.write_text(
            json.dumps({"family": "rf.test.foo", "kind": "trial", "config_hash": "abc"}) + "\n"
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
            # Provide all potentially-mandatory fields
            "come_back_on": "2027-01-01",
            "kill_evidence": {"n_at_kill": 5, "kill_class": "falsified"},
            "program_doc_ref": "research/FOO_PROGRAM.md",
            "artifact_refs": ["data/oracle/compounds/registry.jsonl"],
            "challenge_packet_ref": "data/research_factory/challenges/rf-smoke-001.json",
            "review_packet_ref": "data/research_factory/review/rf-smoke-001.json",
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
