"""Hermetic tests for the opus RF gate in research_factory_decide.py (M3).

Tests the packet_ref resolution logic directly by importing the resolver
functions via importlib, without running the full CLI end-to-end (which
requires live RF data and transitions.jsonl).

Covers:
  (i)  unknown packet_id → _resolve_packet_ref returns (False, error)
  (ii) packet with mismatched outcome → (False, error)
  (iii) valid decided packet + clean queue → passes the gate (True, "")
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DECIDE_SCRIPT = ROOT / "scripts" / "research_factory_decide.py"


def _load_decide_module():
    """Import research_factory_decide as a module via importlib (avoids sys.argv side-effects)."""
    spec = importlib.util.spec_from_file_location("research_factory_decide", DECIDE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Insert ROOT so engine.* imports work
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_queue(packets: list[dict]) -> dict:
    return {
        "schema": "neuralweb.adjudication_queue.v1",
        "updated_at": "2026-07-06",
        "law": "test queue",
        "packets": packets,
    }


def _decided_packet(packet_id: str, outcome: str, decided_by: str = "opus") -> dict:
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": packet_id,
        "tier": 1,
        "created_at": "2026-07-06T00:00:00Z",
        "created_by": "operator",
        "request": {
            "title": "Test packet",
            "requested_decision": outcome,
            "decision_class": "scoped_build",
            "source_doc": None,
            "source_pr": None,
        },
        "scope": {
            "owner_program": "test-program",
            "proposed_classification": "study",
            "touched_artifacts": [],
            "touched_paths": [],
        },
        "case_law": {
            "ruling_hits": ["RUL-SUCC-1"],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "opus",
            "requested_ceiling": "opus",
            "article2_surfaces_touched": [],
            "nondelegable": False,
            "article_citation": None,
            "article3_evidence": {"n": None, "hits": None, "wilson_lb": None, "staleness_days": None},
        },
        "privacy": {
            "privacy_class": "public_research",
            "public_paths_touched": [],
            "private_fields": [],
            "mastermind_booleans_unchanged": None,
        },
        "statistics": {
            "fdr_family": "test-family",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": None,
            "due_status": "not_clocked",
        },
        "build_collision": {
            "open_prs_touching_paths": [],
            "owner_conflicts": [],
        },
        "review": {
            "required_lenses": ["opus"],
            "opus_findings": [],
            "panel": [],
        },
        "allowed_outcomes": [outcome, "defer", "reject"],
        "blocked_outcomes": [],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": outcome,
            "decided_by": decided_by,
            "actor_ref": "opus-session-test",
            "rationale": "Test decision.",
            "decided_on": "2026-07-06",
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolvePacketRef:
    """Tests for _resolve_packet_ref — the resolver function imported directly."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _load_decide_module()

    def test_unknown_packet_id_fails(self, tmp_path: Path):
        """(i) Unknown packet_id → (False, descriptive error)."""
        queue = _make_queue([_decided_packet("adj-known-001", "paper")])
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")

        ok, err = self.mod._resolve_packet_ref("adj-UNKNOWN-xyz", "paper", queue_path)

        assert not ok, "unknown packet_ref should return ok=False"
        assert "adj-UNKNOWN-xyz" in err, f"error should name the unknown ref, got: {err}"
        assert "RF-5b" in err or "RUL-SUCC-7" in err, (
            f"error should cite RF-5b/RUL-SUCC-7, got: {err}"
        )

    def test_mismatched_outcome_fails(self, tmp_path: Path):
        """(ii) Packet outcome != CLI decision → (False, error)."""
        queue = _make_queue([_decided_packet("adj-mismatch-001", "paper")])
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")

        ok, err = self.mod._resolve_packet_ref("adj-mismatch-001", "rejected", queue_path)

        assert not ok, "mismatched outcome should return ok=False"
        assert "paper" in err or "rejected" in err, (
            f"error should mention the outcome mismatch, got: {err}"
        )

    def test_valid_decided_packet_passes(self, tmp_path: Path):
        """(iii) Valid decided packet + matching outcome + opus decided_by → (True, '')."""
        queue = _make_queue([_decided_packet("adj-valid-001", "paper", decided_by="opus")])
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")

        ok, err = self.mod._resolve_packet_ref("adj-valid-001", "paper", queue_path)

        assert ok, f"valid packet should return ok=True, got err={err!r}"
        assert err == "", f"no error expected for valid packet, got: {err!r}"

    def test_operator_decided_by_also_valid(self, tmp_path: Path):
        """decided_by=operator is also a valid decider for the opus gate."""
        queue = _make_queue([_decided_packet("adj-op-001", "paper", decided_by="operator")])
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")

        ok, err = self.mod._resolve_packet_ref("adj-op-001", "paper", queue_path)

        assert ok, f"operator decided_by should pass gate, got err={err!r}"

    def test_invalid_decided_by_fails(self, tmp_path: Path):
        """decided_by=fable is not in {opus, operator} → (False, error)."""
        queue = _make_queue([_decided_packet("adj-fable-001", "paper", decided_by="fable")])
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")

        ok, err = self.mod._resolve_packet_ref("adj-fable-001", "paper", queue_path)

        assert not ok, "decided_by=fable should fail gate"
        assert "fable" in err or "decided_by" in err, (
            f"error should mention the invalid decided_by, got: {err}"
        )

    def test_missing_queue_file_fails(self, tmp_path: Path):
        """Queue file does not exist → (False, error)."""
        nonexistent = tmp_path / "no_queue.json"

        ok, err = self.mod._resolve_packet_ref("adj-001", "paper", nonexistent)

        assert not ok, "missing queue should return ok=False"
        assert "not found" in err.lower() or "RF-5b" in err, f"unexpected error: {err}"

    def test_multiple_packets_resolves_correct_one(self, tmp_path: Path):
        """Queue with multiple packets — only the matching id is checked."""
        queue = _make_queue([
            _decided_packet("adj-other-001", "rejected"),
            _decided_packet("adj-target-001", "paper"),
        ])
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")

        ok, err = self.mod._resolve_packet_ref("adj-target-001", "paper", queue_path)

        assert ok, f"correct target packet should pass, got err={err!r}"


# ---------------------------------------------------------------------------
# Integration tests: full main() end-to-end CLI
# ---------------------------------------------------------------------------


def _make_candidate_row(candidate_id: str) -> dict:
    """Minimal candidates.jsonl row with status=human_review."""
    return {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "created_at": "2026-07-06T00:00:00Z",
        "hypothesis": "Test hypothesis for integration test",
        "mechanism": "Test mechanism",
        "source": "human",
        "candidate_type": "external_idea",
        "domain": "oracle",
        "status": "human_review",
        "trial_accounting": {"mode": "read_only", "family": None},
    }


def _make_transition_row_to_human_review(candidate_id: str) -> dict:
    """A transitions.jsonl row putting the candidate into human_review state."""
    return {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": "challenged",
        "to": "human_review",
        "reason_code": "script_challenge",
        "reason_text": "Script moved candidate into human_review for testing",
        "actor": "script",
        "actor_ref": None,
        "as_of": "2026-07-06T00:00:00Z",
        "artifact_refs": [],
        "kill_evidence": None,
        "review_packet_ref": "rp-test-001",
    }


def _make_clean_t1_queue_packet(packet_id: str, outcome: str = "paper") -> dict:
    """A well-formed, decided tier-1 packet that passes check_adjudication_packet.py."""
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": packet_id,
        "tier": 1,
        "created_at": "2026-07-06T10:00:00Z",
        "created_by": "opus",
        "request": {
            "title": "Integration test: paper decision for RF candidate",
            "requested_decision": outcome,
            "decision_class": "scoped_build",
            "source_doc": None,
            "source_pr": None,
        },
        "scope": {
            "owner_program": "test_program",
            "proposed_classification": "study",
            "touched_artifacts": [],
            "touched_paths": [],
        },
        "case_law": {
            "ruling_hits": ["RUL-SUCC-1"],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": [],
            "nondelegable": False,
        },
        "statistics": {
            "fdr_family": "test_family",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-10-06",
            "due_status": "accruing",
        },
        "allowed_outcomes": [outcome, "defer", "reject"],
        "blocked_outcomes": [],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": outcome,
            "decided_by": "opus",
            "actor_ref": "opus-integration-test",
            "rationale": "Integration test: approving for paper accrual.",
            "decided_on": "2026-07-06",
        },
    }


def _setup_hermetic_rf_dir(
    tmp_path: Path,
    candidate_id: str,
    packet_id: str,
    packet_outcome: str = "paper",
) -> dict[str, Path]:
    """Create the minimal hermetic RF directory structure for a full CLI run.

    Returns a dict of named paths:
      rf_dir, candidates_jsonl, transitions_jsonl, adj_queue,
      regime_path, seed_path, requeue_path, fake_root
    """
    # RF dir structure
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir()

    # candidates.jsonl — one candidate in human_review
    candidates_path = rf_dir / "candidates.jsonl"
    cand_row = _make_candidate_row(candidate_id)
    candidates_path.write_text(json.dumps(cand_row) + "\n", encoding="utf-8")

    # transitions.jsonl — one transition putting the candidate in human_review
    transitions_path = rf_dir / "transitions.jsonl"
    trans_row = _make_transition_row_to_human_review(candidate_id)
    transitions_path.write_text(json.dumps(trans_row) + "\n", encoding="utf-8")

    # Adjudication queue — one clean decided tier-1 packet
    adj_dir = tmp_path / "neuralweb"
    adj_dir.mkdir()
    adj_queue = adj_dir / "adjudication_queue.json"
    queue_payload = {
        "schema": "neuralweb.adjudication_queue.v1",
        "updated_at": "2026-07-06",
        "packets": [_make_clean_t1_queue_packet(packet_id, outcome=packet_outcome)],
    }
    adj_queue.write_text(json.dumps(queue_payload), encoding="utf-8")

    # Regime file (absent-safe — code handles missing gracefully)
    regime_dir = tmp_path / "regime"
    regime_dir.mkdir()
    regime_path = regime_dir / "latest.json"
    regime_path.write_text(
        json.dumps({"label": "risk_on", "quad": "GE", "asof": "2026-07-06"}),
        encoding="utf-8",
    )

    # Experiments seed (absent = code creates empty structure)
    seed_path = tmp_path / "registry_seed.json"

    # Requeue path
    requeue_path = rf_dir / "requeue.jsonl"

    # fake_root: the governance writer uses root/data/neuralweb/governance.jsonl
    # We point it at tmp_path so writes land in tmp_path/data/neuralweb/
    fake_root = tmp_path

    return {
        "rf_dir": rf_dir,
        "candidates_jsonl": candidates_path,
        "transitions_jsonl": transitions_path,
        "adj_queue": adj_queue,
        "regime_path": regime_path,
        "seed_path": seed_path,
        "requeue_path": requeue_path,
        "fake_root": fake_root,
    }


def _run_decide_cli(*extra_args: str) -> subprocess.CompletedProcess:
    """Run the research_factory_decide.py CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, str(DECIDE_SCRIPT)] + list(extra_args),
        capture_output=True,
        text=True,
    )


class TestDecideCLIIntegration:
    """Full main() end-to-end integration tests.

    These tests exercise the complete CLI path — including the packet_ref
    clobber fix (FIX 1) — by running the script via subprocess against a
    hermetic temp RF directory.
    """

    CANDIDATE_ID = "rf-20260706-oracle-integration-001"
    PACKET_ID = "adj-2026-07-06-integration-t1"

    def _build_paths(self, tmp_path: Path) -> dict[str, Path]:
        return _setup_hermetic_rf_dir(
            tmp_path,
            candidate_id=self.CANDIDATE_ID,
            packet_id=self.PACKET_ID,
            packet_outcome="paper",
        )

    def test_positive_exit0_and_packet_ref_in_transition(self, tmp_path: Path):
        """Full CLI: opus+packet_ref+paper → exit 0 AND transition row has packet_ref.

        This is the critical regression test for FIX 1: the transition row
        must carry packet_ref == PACKET_ID even though the 'paper' branch
        reassigns extra_fields = {...}, which previously clobbered packet_ref.
        """
        paths = self._build_paths(tmp_path)

        result = _run_decide_cli(
            "--rf-dir", str(paths["rf_dir"]),
            "--experiments-seed", str(paths["seed_path"]),
            "--regime-path", str(paths["regime_path"]),
            "--requeue-path", str(paths["requeue_path"]),
            "--adjudication-queue", str(paths["adj_queue"]),
            "--candidate", self.CANDIDATE_ID,
            "--decision", "paper",
            "--actor", "opus",
            "--actor-ref", "opus-integration-test",
            "--packet-ref", self.PACKET_ID,
            "--expected-half-life-d", "100",
        )

        combined = result.stdout + result.stderr
        assert result.returncode == 0, (
            f"Expected exit 0 but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        # Read back the written transitions.jsonl and verify packet_ref is present
        transitions_path = paths["transitions_jsonl"]
        rows = [
            json.loads(line)
            for line in transitions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        # The last row is the newly appended one (first row is the setup transition)
        assert len(rows) >= 2, (
            f"Expected at least 2 rows in transitions.jsonl (setup + new), got {len(rows)}"
        )
        new_row = rows[-1]
        assert new_row.get("to") == "paper", (
            f"Expected transition to 'paper', got to={new_row.get('to')!r}"
        )
        assert new_row.get("packet_ref") == self.PACKET_ID, (
            f"FIX 1 regression: transition row missing packet_ref. "
            f"Expected packet_ref={self.PACKET_ID!r}, got {new_row.get('packet_ref')!r}. "
            f"Full row: {new_row}"
        )
        assert new_row.get("actor") == "opus", (
            f"Expected actor='opus', got actor={new_row.get('actor')!r}"
        )

    def test_negative_outcome_mismatch_exit2_no_row_appended(self, tmp_path: Path):
        """CLI with mismatched packet decision.outcome → exit 2, no transition appended.

        The queue packet records outcome='paper' but --decision=rejected →
        the resolve gate catches the mismatch and exits rc=2 before any write.
        """
        paths = _setup_hermetic_rf_dir(
            tmp_path,
            candidate_id=self.CANDIDATE_ID,
            packet_id=self.PACKET_ID,
            packet_outcome="paper",  # packet says 'paper'
        )

        # Read the starting transition count
        transitions_path = paths["transitions_jsonl"]
        rows_before = transitions_path.read_text(encoding="utf-8").splitlines()

        result = _run_decide_cli(
            "--rf-dir", str(paths["rf_dir"]),
            "--experiments-seed", str(paths["seed_path"]),
            "--regime-path", str(paths["regime_path"]),
            "--requeue-path", str(paths["requeue_path"]),
            "--adjudication-queue", str(paths["adj_queue"]),
            "--candidate", self.CANDIDATE_ID,
            "--decision", "rejected",  # mismatches packet outcome='paper'
            "--actor", "opus",
            "--actor-ref", "opus-integration-test",
            "--packet-ref", self.PACKET_ID,
            "--kill-class", "falsified",
            "--n-at-kill", "5",
        )

        assert result.returncode == 2, (
            f"Expected exit 2 (outcome mismatch) but got rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        # No new row should have been appended
        rows_after = transitions_path.read_text(encoding="utf-8").splitlines()
        assert len(rows_after) == len(rows_before), (
            f"Mismatch exit must not append any transition row. "
            f"Before: {len(rows_before)} lines, after: {len(rows_after)} lines."
        )
