"""tests/test_research_factory_review.py — W5 review queue + decide tests.

Tests (charter §6 W5 exit gate):
  1. Queue builds from fixture ledger incl. challenge files.
  2. search_width_at_scan MISSING marker for oracle candidates without it.
  3. crowds_with computed from column overlap.
  4. crowds_with computed from alpha cluster overlap.
  5. No numeric composite anywhere in the queue JSON.
  6. Queue ordering: category bins then created_at (never numeric).
  7. paper decision: transition recorded, governance event written,
     seed entry created, track file created (all four effects).
  8. deferred decision: transition + seed entry + track file + come_back_on.
  9. rejected decision: transition + kill_evidence recorded.
  10. rejected with underpowered_accruing: requeue pointer written.
  11. scoped_build decision: transition + program_doc_ref recorded.
  12. Actor law violation: script actor for human-gate state refused.
  13. Missing actor_ref for human actor refused.
  14. Double-decision refused (already terminal state).
  15. Double-decision refused (already paper → paper again).
  16. Non-human_review candidate refused.
  17. Seed entry matches real registry_seed.json key set (validate key schema).
  18. Queue has no candidates when ledger is empty.
  19. Paper candidates flagged for decay review appear in queue.
  20. Oracle candidate without search_width: MISSING string in packet.
  21. Oracle candidate with search_width: value present in packet.
  22. Non-oracle candidate: search_width_at_scan=None (not MISSING).
  23. Queue packet carries authority='display_only'.
  24. Decide dry-run writes nothing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory import ledger as rf_ledger
from engine.research_factory.review_queue import build_queue, _compute_crowds_with
from engine.research_factory.state import IllegalTransition

# ---------------------------------------------------------------------------
# REAL registry_seed.json key schema (copied from 2-3 live entries for fixture validation)
# Test 17 validates our seed entries carry these keys.
# ---------------------------------------------------------------------------

# Keys present in track_record entries (index-leadership, subsector-rotation, hub-track-record)
_REAL_TRACK_RECORD_KEYS = frozenset({
    "id", "name", "kind", "priority", "cadence", "what",
    "source", "storage", "track_json", "hook",
    "started", "come_back_on", "maturation", "status",
    "state", "next_step",
})

# Keys present in data_collection entries (dislocation-accrual, revisions-breadth)
_REAL_DATA_COLLECTION_KEYS = frozenset({
    "id", "name", "kind", "priority", "cadence", "what",
    "source", "storage", "started", "come_back_on",
    "maturation", "status", "state", "next_step",
})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_candidate(
    candidate_id: str = "rf-test-001",
    candidate_type: str = "oracle_compound",
    domain: str = "oracle",
    status: str = "human_review",
    hypothesis: str = "H1: washout flow predicts reversal",
    mechanism: str = "Supply shock absorption via wr column",
    source: str = "oracle_brainstorm",
    created_at: str | None = None,
    **overrides,
) -> dict:
    row = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "created_at": created_at or _now(),
        "source": source,
        "candidate_type": candidate_type,
        "domain": domain,
        "status": status,
        "hypothesis": hypothesis,
        "mechanism": mechanism,
        "claim_shape": None,
        "spec_ref": candidate_id,
        "trial_accounting": {"mode": "read_only", "family": None},
        "evaluation_plan": {
            "primary_metric": "wr",
            "horizon_d": 21,
            "min_n": 25,
            "expected_half_life_d": None,
            "defaulted": True,
        },
        "lineage": {"respin_of": None, "superseded_by": None, "refinement_generation": 0},
        "flags": [],
        "artifacts": {},
        "transition_log": [],
    }
    row.update(overrides)
    return row


def _make_challenge(
    candidate_id: str,
    human_review_question: str = "Should this candidate proceed to paper accrual?",
    recommendation: str = "ADVISORY_REVIEW",
    blockers: list | None = None,
    best_counterargument: str = "Small sample; regime-specific",
) -> dict:
    return {
        "schema": "research_factory.challenge.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "challenged_at": _now(),
        "mechanical_probes": {
            "input_insensitive": False,
            "near_dup": {"score": 0.1, "nearest": None},
            "mechanism_spec_mismatch": False,
            "gauntlet_legs": [],
        },
        "reviewer": {
            "agent_type": "reviewer",
            "recommendation": recommendation,
            "blockers": blockers or [],
            "non_blocking_concerns": [],
            "best_counterargument": best_counterargument,
            "minimum_fix_to_reconsider": None,
            "falsifier_spec": None,
            "human_review_question": human_review_question,
        },
    }


def _make_transition(
    candidate_id: str,
    from_state: str,
    to_state: str,
    actor: str = "script",
    actor_ref: str | None = None,
    **kwargs,
) -> dict:
    row = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": from_state,
        "to": to_state,
        "reason_code": "test",
        "reason_text": "test transition",
        "actor": actor,
        "actor_ref": actor_ref,
        "as_of": _now(),
        "artifact_refs": [],
        "kill_evidence": None,
    }
    row.update(kwargs)
    return row


# ---------------------------------------------------------------------------
# Fixture setup helpers
# ---------------------------------------------------------------------------


def _setup_rf_dir(
    tmp_path: Path,
    candidates: list[dict] | None = None,
    transitions: list[dict] | None = None,
    challenges: dict[str, dict] | None = None,
    paper_monitor: list[dict] | None = None,
) -> Path:
    """Set up a minimal research_factory directory with fixture data."""
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)
    (rf_dir / "challenges").mkdir()
    (rf_dir / "review").mkdir()

    # Write candidates.jsonl
    if candidates:
        cand_path = rf_dir / "candidates.jsonl"
        with cand_path.open("w") as fh:
            for c in candidates:
                fh.write(json.dumps(c) + "\n")

    # Write transitions.jsonl
    if transitions:
        trans_path = rf_dir / "transitions.jsonl"
        with trans_path.open("w") as fh:
            for t in transitions:
                fh.write(json.dumps(t) + "\n")

    # Write challenge files
    if challenges:
        for cid, challenge_data in challenges.items():
            (rf_dir / "challenges" / f"{cid}.json").write_text(
                json.dumps(challenge_data)
            )

    # Write paper_monitor.jsonl
    if paper_monitor:
        pm_path = rf_dir / "paper_monitor.jsonl"
        with pm_path.open("w") as fh:
            for row in paper_monitor:
                fh.write(json.dumps(row) + "\n")

    return rf_dir


# ---------------------------------------------------------------------------
# Test 1: Queue builds from fixture ledger
# ---------------------------------------------------------------------------


def test_queue_builds_from_fixture(tmp_path):
    cand = _make_candidate(candidate_id="rf-001", status="human_review")
    challenge = _make_challenge("rf-001")

    rf_dir = _setup_rf_dir(
        tmp_path,
        candidates=[cand],
        challenges={"rf-001": challenge},
    )

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    pkt = packets[0]
    assert pkt["candidate_id"] == "rf-001"
    assert pkt["hypothesis"] == cand["hypothesis"]
    assert pkt["mechanism"] == cand["mechanism"]
    assert pkt["current_status"] == "human_review"
    assert pkt["human_review_question"] == challenge["reviewer"]["human_review_question"]
    assert pkt["best_counterargument"] == challenge["reviewer"]["best_counterargument"]
    assert "allowed_decisions" in pkt
    assert set(pkt["allowed_decisions"]) == {"paper", "deferred", "rejected", "scoped_build"}


# ---------------------------------------------------------------------------
# Test 2: search_width MISSING marker for oracle without it
# ---------------------------------------------------------------------------


def test_search_width_missing_for_oracle(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-oracle-no-sw",
        domain="oracle",
        candidate_type="oracle_compound",
        status="human_review",
        # No search_width_at_scan in artifacts
        artifacts={},
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["search_width_at_scan"] == "MISSING"


# ---------------------------------------------------------------------------
# Test 21: Oracle candidate with search_width: value present
# ---------------------------------------------------------------------------


def test_search_width_present_for_oracle(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-oracle-with-sw",
        domain="oracle",
        candidate_type="oracle_compound",
        status="human_review",
        artifacts={"search_width_at_scan": 142},
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["search_width_at_scan"] == 142


# ---------------------------------------------------------------------------
# Test 22: Non-oracle candidate: search_width_at_scan=None
# ---------------------------------------------------------------------------


def test_search_width_none_for_non_oracle(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-alpha-001",
        domain="entry",
        candidate_type="alpha_family",
        status="human_review",
        artifacts={},
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["search_width_at_scan"] is None


# ---------------------------------------------------------------------------
# Test 3: crowds_with from column overlap
# ---------------------------------------------------------------------------


def test_crowds_with_column_overlap(tmp_path):
    # Two candidates with shared entry_rule_columns
    cand_a = _make_candidate(
        candidate_id="rf-a",
        status="human_review",
        evaluation_plan={
            "primary_metric": "wr",
            "horizon_d": 21,
            "min_n": 25,
            "entry_rule_columns": ["wr", "asym"],
        },
    )
    cand_b = _make_candidate(
        candidate_id="rf-b",
        status="registered",   # non-terminal, non-queue
        evaluation_plan={
            "primary_metric": "wr",
            "horizon_d": 21,
            "min_n": 25,
            "entry_rule_columns": ["wr", "ret_exit"],  # 'wr' shared
        },
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand_a, cand_b])

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    cw = packets[0]["crowds_with"]
    assert len(cw) == 1
    assert cw[0]["candidate_id"] == "rf-b"
    assert "wr" in cw[0]["overlap_columns"]


# ---------------------------------------------------------------------------
# Test 4: crowds_with from alpha cluster overlap
# ---------------------------------------------------------------------------


def test_crowds_with_alpha_cluster(tmp_path):
    cand_a = _make_candidate(
        candidate_id="rf-alpha-a",
        candidate_type="alpha_family",
        domain="entry",
        status="human_review",
        artifacts={"cluster": "momentum_reversion"},
    )
    cand_b = _make_candidate(
        candidate_id="rf-alpha-b",
        candidate_type="alpha_family",
        domain="entry",
        status="screened",
        artifacts={"cluster": "momentum_reversion"},
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand_a, cand_b])

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    cw = packets[0]["crowds_with"]
    assert any(c["candidate_id"] == "rf-alpha-b" for c in cw)
    match = next(c for c in cw if c["candidate_id"] == "rf-alpha-b")
    assert match["same_alpha_cluster"] is True


# ---------------------------------------------------------------------------
# Test 5: No numeric composite anywhere in queue JSON
# ---------------------------------------------------------------------------


def test_no_numeric_composite_in_queue(tmp_path):
    """RF-16: queue JSON must not contain any composite numeric score field."""
    cands = [
        _make_candidate(candidate_id=f"rf-{i}", status="human_review")
        for i in range(3)
    ]
    rf_dir = _setup_rf_dir(tmp_path, candidates=cands)
    packets = build_queue(rf_dir=rf_dir)

    # Serialize and scan for forbidden composite fields
    queue_str = json.dumps(packets)
    FORBIDDEN_COMPOSITE_FIELDS = [
        "composite_score", "fused_score", "factory_score",
        "rank_score", "utility_score", "aggregate_score",
        "weighted_score", "combined_score",
    ]
    for field in FORBIDDEN_COMPOSITE_FIELDS:
        assert f'"{field}"' not in queue_str, (
            f"Forbidden composite field {field!r} found in queue JSON (RF-16)"
        )


# ---------------------------------------------------------------------------
# Test 6: Queue ordering — category bins then created_at
# ---------------------------------------------------------------------------


def test_queue_ordering(tmp_path):
    # Oracle should come before alpha_family; within type, earlier created_at first
    cand_alpha = _make_candidate(
        candidate_id="rf-alpha",
        candidate_type="alpha_family",
        status="human_review",
        created_at="2026-07-06T00:00:00Z",
    )
    cand_oracle_later = _make_candidate(
        candidate_id="rf-oracle-late",
        candidate_type="oracle_compound",
        domain="oracle",
        status="human_review",
        created_at="2026-07-06T01:00:00Z",
    )
    cand_oracle_early = _make_candidate(
        candidate_id="rf-oracle-early",
        candidate_type="oracle_compound",
        domain="oracle",
        status="human_review",
        created_at="2026-07-05T00:00:00Z",
    )
    rf_dir = _setup_rf_dir(
        tmp_path,
        candidates=[cand_alpha, cand_oracle_later, cand_oracle_early],
    )

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 3
    ids = [p["candidate_id"] for p in packets]
    # Oracle before alpha
    assert ids.index("rf-oracle-early") < ids.index("rf-alpha")
    assert ids.index("rf-oracle-late") < ids.index("rf-alpha")
    # Earlier oracle before later oracle
    assert ids.index("rf-oracle-early") < ids.index("rf-oracle-late")


# ---------------------------------------------------------------------------
# Test 23: Queue packet carries authority='display_only'
# ---------------------------------------------------------------------------


def test_packet_authority(tmp_path):
    cand = _make_candidate()
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["authority"] == "display_only"


# ---------------------------------------------------------------------------
# Test 18: Empty queue when ledger is empty
# ---------------------------------------------------------------------------


def test_empty_queue_no_candidates(tmp_path):
    rf_dir = _setup_rf_dir(tmp_path)
    packets = build_queue(rf_dir=rf_dir)
    assert packets == []


# ---------------------------------------------------------------------------
# Test 19: Paper candidates flagged for decay review appear in queue
# ---------------------------------------------------------------------------


def test_paper_decay_review_in_queue(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-paper-decay",
        status="paper",
    )
    # paper_monitor row flagging decay review
    pm_row = {
        "schema": "research_factory.paper_monitor.v1",
        "authority": "display_only",
        "candidate_id": "rf-paper-decay",
        "as_of": "2026-07-06",
        "paper_status": "review",
        "action": "review",
    }
    rf_dir = _setup_rf_dir(
        tmp_path,
        candidates=[cand],
        paper_monitor=[pm_row],
    )
    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["candidate_id"] == "rf-paper-decay"


# ---------------------------------------------------------------------------
# Decide tests: setup helpers
# ---------------------------------------------------------------------------


def _setup_decide_env(
    tmp_path: Path,
    candidate: dict | None = None,
    transitions: list[dict] | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    """Set up dirs and return (rf_dir, seed_path, regime_path, requeue_path, governance_path)."""
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)
    (rf_dir / "challenges").mkdir()
    (rf_dir / "track").mkdir()

    # Write candidate
    if candidate:
        cand_path = rf_dir / "candidates.jsonl"
        with cand_path.open("w") as fh:
            fh.write(json.dumps(candidate) + "\n")

    if transitions:
        trans_path = rf_dir / "transitions.jsonl"
        with trans_path.open("w") as fh:
            for t in transitions:
                fh.write(json.dumps(t) + "\n")

    # Experiments seed
    seed_dir = tmp_path / "experiments"
    seed_dir.mkdir()
    seed_path = seed_dir / "registry_seed.json"
    seed_path.write_text(
        json.dumps({"schema": "experiments_registry_seed.v1", "experiments": []})
    )

    # Regime path
    regime_dir = tmp_path / "regime"
    regime_dir.mkdir()
    regime_path = regime_dir / "latest.json"
    regime_path.write_text(
        json.dumps({
            "schema_version": 1,
            "asof": "2026-07-06",
            "quad": "Q1",
            "label": "Q1",
        })
    )

    # Requeue path
    requeue_path = tmp_path / "requeue.jsonl"

    # Governance path (under data/neuralweb/)
    gov_dir = tmp_path / "data" / "neuralweb"
    gov_dir.mkdir(parents=True)

    return rf_dir, seed_path, regime_path, requeue_path, tmp_path


def _run_decide(
    tmp_path: Path,
    rf_dir: Path,
    seed_path: Path,
    regime_path: Path,
    requeue_path: Path,
    args_extra: list[str] | None = None,
    candidate_id: str = "rf-test-001",
    decision: str = "paper",
    actor: str = "fable",
    actor_ref: str = "session-test-001",
) -> int:
    """Run the decide script main() with the given args."""
    import scripts.research_factory_decide as decide_mod
    from unittest.mock import patch

    argv = [
        "research_factory_decide.py",
        "--candidate", candidate_id,
        "--decision", decision,
        "--actor", actor,
        "--actor-ref", actor_ref,
        "--rf-dir", str(rf_dir),
        "--experiments-seed", str(seed_path),
        "--regime-path", str(regime_path),
        "--requeue-path", str(requeue_path),
    ]
    if args_extra:
        argv.extend(args_extra)

    with patch.object(sys, "argv", argv):
        # Patch governance to write to our tmp dir
        with patch.object(
            decide_mod,
            "_append_governance_event",
            wraps=lambda **kw: _fake_governance(tmp_path, **kw),
        ):
            return decide_mod.main()


def _fake_governance(tmp_path: Path, *, candidate_id, decision, actor, actor_ref, root, dry_run=False):
    """Write a fake governance event to our tmp dir for testing."""
    if dry_run:
        return
    gov_path = tmp_path / "data" / "neuralweb" / "governance.jsonl"
    gov_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "event_type": "research_factory_gate",
        "target": f"research_factory/{candidate_id}",
        "article": None,
        "decision": decision,
        "actor": actor,
        "actor_ref": actor_ref,
    }
    with gov_path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Test 7: paper decision — all four effects
# ---------------------------------------------------------------------------


def test_paper_decision_four_effects(tmp_path):
    """paper decision: transition + governance event + seed entry + track file."""
    cand = _make_candidate(
        candidate_id="rf-paper-001",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-paper-001",
        decision="paper",
        args_extra=["--expected-half-life-d", "250"],
    )
    assert rc == 0, "paper decision should succeed"

    # Effect (a): transition written
    transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    paper_transitions = [t for t in transitions if t.get("to") == "paper"]
    assert len(paper_transitions) == 1
    assert paper_transitions[0]["actor"] == "fable"
    assert paper_transitions[0]["actor_ref"] == "session-test-001"
    assert paper_transitions[0]["expected_half_life_d"] == 250

    # Effect (b): governance event written
    gov_path = tmp_path / "data" / "neuralweb" / "governance.jsonl"
    assert gov_path.exists(), "Governance file should exist"
    gov_rows = rf_ledger.load_jsonl(gov_path)
    assert len(gov_rows) >= 1
    assert any(r.get("article") is None for r in gov_rows), "article must be null (RF-12)"
    assert any(r.get("event_type") == "research_factory_gate" for r in gov_rows)

    # Effect (c): seed entry
    seed = json.loads(seed_path.read_text())
    seed_ids = [e["id"] for e in seed.get("experiments", [])]
    assert "rf-rf-paper-001" in seed_ids, f"Seed entry missing; found: {seed_ids}"
    seed_entry = next(e for e in seed["experiments"] if e["id"] == "rf-rf-paper-001")
    assert seed_entry["kind"] == "track_record"
    assert seed_entry["hook"] == "track_record"
    assert "rf-paper-001" in seed_entry["track_json"]
    assert seed_entry["come_back_on"] is not None
    # Validate key coverage against real seed schema
    assert _REAL_TRACK_RECORD_KEYS.issubset(set(seed_entry.keys())), (
        f"Seed entry missing required keys: "
        f"{_REAL_TRACK_RECORD_KEYS - set(seed_entry.keys())}"
    )

    # Effect (d): track file written
    track_path = rf_dir / "track" / "rf-paper-001.json"
    assert track_path.exists(), "Track skeleton file should exist"
    track = json.loads(track_path.read_text())
    assert track["authority"] == "display_only"
    assert track["verdict"] == "accruing"
    assert track["candidate_id"] == "rf-paper-001"
    assert "horizons" in track


# ---------------------------------------------------------------------------
# Test 8: deferred decision
# ---------------------------------------------------------------------------


def test_deferred_decision(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-deferred-001",
        status="human_review",
        domain="entry",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-deferred-001",
        decision="deferred",
        args_extra=["--come-back-on", "2027-01-01"],
    )
    assert rc == 0

    # Transition written
    transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    deferred_t = [t for t in transitions if t.get("to") == "deferred"]
    assert len(deferred_t) == 1
    assert deferred_t[0]["come_back_on"] == "2027-01-01"

    # Seed entry written
    seed = json.loads(seed_path.read_text())
    seed_ids = [e["id"] for e in seed.get("experiments", [])]
    assert "rf-rf-deferred-001" in seed_ids

    # Track file written
    track_path = rf_dir / "track" / "rf-deferred-001.json"
    assert track_path.exists()


# ---------------------------------------------------------------------------
# Test 9: rejected decision
# ---------------------------------------------------------------------------


def test_rejected_decision(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-rejected-001",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-rejected-001",
        decision="rejected",
        args_extra=["--kill-class", "falsified", "--n-at-kill", "45"],
    )
    assert rc == 0

    transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    rej_t = [t for t in transitions if t.get("to") == "rejected"]
    assert len(rej_t) == 1
    ke = rej_t[0].get("kill_evidence") or {}
    assert ke["kill_class"] == "falsified"
    assert ke["n_at_kill"] == 45


# ---------------------------------------------------------------------------
# Test 10: rejected underpowered_accruing → requeue pointer written
# ---------------------------------------------------------------------------


def test_rejected_underpowered_writes_requeue(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-underpowered-001",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-underpowered-001",
        decision="rejected",
        args_extra=["--kill-class", "underpowered_accruing", "--n-at-kill", "10"],
    )
    assert rc == 0

    # Requeue pointer written
    assert requeue_path.exists(), "Requeue file should exist"
    requeue_rows = rf_ledger.load_jsonl(requeue_path)
    assert len(requeue_rows) == 1
    row = requeue_rows[0]
    assert row["candidate_id"] == "rf-underpowered-001"
    assert row["kill_class"] == "underpowered_accruing"
    assert row["n_at_kill"] == 10
    assert row["requeue_at_n"] == 20  # 2x n_at_kill
    assert row["authority"] == "display_only"


# ---------------------------------------------------------------------------
# Test 11: scoped_build decision
# ---------------------------------------------------------------------------


def test_scoped_build_decision(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-scoped-001",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-scoped-001",
        decision="scoped_build",
        args_extra=["--program-doc", "research/TEST_PROGRAM_BY_FABLE.md"],
    )
    assert rc == 0

    transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    sb_t = [t for t in transitions if t.get("to") == "scoped_build"]
    assert len(sb_t) == 1
    assert sb_t[0]["program_doc_ref"] == "research/TEST_PROGRAM_BY_FABLE.md"


# ---------------------------------------------------------------------------
# Test 12: Actor law violation — script actor refused
# ---------------------------------------------------------------------------


def test_actor_law_script_refused(tmp_path):
    """Script actor cannot make human-gate decisions (RF-5).

    The CLI enforces actor choices = {fable, operator}, so we test actor law
    directly via state.py's transition() for completeness, and verify the CLI
    limits --actor to human actors only.
    """
    from engine.research_factory.state import transition, IllegalTransition

    cand = _make_candidate(
        candidate_id="rf-actor-law-001",
        status="human_review",
    )

    # Direct state.py check: script cannot drive paper
    row = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": "rf-actor-law-001",
        "from": "human_review",
        "to": "paper",
        "reason_code": "test",
        "actor": "script",
        "actor_ref": None,
        "as_of": _now(),
        "seed_entry_ref": "rf-rf-actor-law-001",
        "regime_at_entry": {"regime": "unknown"},
        "expected_half_life_d": 250,
    }
    with pytest.raises(IllegalTransition, match="script class"):
        transition("human_review", "paper", "script", row, candidate=cand)

    # CLI enforces {fable, operator} choices — script would be argparse error (exit 2)
    # This is the correct enforcement: the CLI never accepts script actors.
    # We verify by calling the parser directly.
    import scripts.research_factory_decide as decide_mod
    parser = decide_mod._build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([
            "--candidate", "rf-actor-law-001",
            "--decision", "paper",
            "--actor", "script",
            "--actor-ref", "session-test",
        ])
    assert exc.value.code == 2, "CLI should exit 2 for invalid --actor=script"


# ---------------------------------------------------------------------------
# Test 13: Missing actor_ref for human actor refused
# ---------------------------------------------------------------------------


def test_missing_actor_ref_refused(tmp_path):
    """actor_ref is required for human actors (RF-5)."""
    cand = _make_candidate(
        candidate_id="rf-no-ref-001",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    # We test by directly calling state_transition with missing actor_ref
    from engine.research_factory.state import transition, IllegalTransition

    row = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": "rf-no-ref-001",
        "from": "human_review",
        "to": "paper",
        "reason_code": "human_decision_paper",
        "actor": "fable",
        "actor_ref": None,   # ← missing
        "as_of": _now(),
        "seed_entry_ref": "rf-rf-no-ref-001",
        "regime_at_entry": {"regime": "unknown"},
        "expected_half_life_d": 250,
    }
    with pytest.raises(IllegalTransition, match="actor_ref"):
        transition("human_review", "paper", "fable", row, candidate=cand)


# ---------------------------------------------------------------------------
# Test 14: Double-decision refused — already terminal
# ---------------------------------------------------------------------------


def test_double_decision_terminal_refused(tmp_path):
    """Already-terminal candidates cannot be re-decided."""
    cand = _make_candidate(
        candidate_id="rf-terminal-001",
        status="rejected",  # already terminal
    )
    # Add a transition that sets status to rejected
    t = _make_transition("rf-terminal-001", "human_review", "rejected",
                         actor="fable", actor_ref="session-abc",
                         kill_evidence={"n_at_kill": 10, "kill_class": "falsified"})
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand, transitions=[t]
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-terminal-001",
        decision="paper",
        args_extra=["--expected-half-life-d", "250"],
    )
    assert rc != 0, "Terminal candidate should be refused"


# ---------------------------------------------------------------------------
# Test 15: Double-decision refused — already paper
# ---------------------------------------------------------------------------


def test_double_decision_paper_refused(tmp_path):
    """Candidate already in 'paper' state cannot be re-decided as paper."""
    cand = _make_candidate(
        candidate_id="rf-already-paper",
        status="paper",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-already-paper",
        decision="paper",
        args_extra=["--expected-half-life-d", "250"],
    )
    assert rc != 0, "Paper-on-paper should be refused"


# ---------------------------------------------------------------------------
# Test 16: Non-human_review candidate refused
# ---------------------------------------------------------------------------


def test_non_human_review_refused(tmp_path):
    """A candidate not in human_review cannot be decided."""
    cand = _make_candidate(
        candidate_id="rf-registered-001",
        status="registered",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-registered-001",
        decision="paper",
        args_extra=["--expected-half-life-d", "250"],
    )
    assert rc != 0, "Non-human_review candidate should be refused"


# ---------------------------------------------------------------------------
# Test 17: Seed entry matches real registry_seed.json key set
# ---------------------------------------------------------------------------


def test_seed_entry_key_schema(tmp_path):
    """Verify seed entries from paper/deferred decisions carry the real seed key set."""
    cand = _make_candidate(
        candidate_id="rf-schema-check",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-schema-check",
        decision="paper",
        args_extra=["--expected-half-life-d", "300"],
    )
    assert rc == 0

    seed = json.loads(seed_path.read_text())
    entry = next(
        (e for e in seed["experiments"] if e.get("id") == "rf-rf-schema-check"),
        None,
    )
    assert entry is not None, "Seed entry not found"

    # Must have at minimum the real track_record keys
    missing = _REAL_TRACK_RECORD_KEYS - set(entry.keys())
    assert not missing, f"Seed entry missing real-key-schema fields: {missing}"

    # Must not have 'validated' in any emitted text (house law)
    entry_text = json.dumps(entry)
    assert "validated" not in entry_text.lower(), (
        "Word 'validated' must not appear in any emitted seed entry text"
    )


# ---------------------------------------------------------------------------
# Test 24: Decide dry-run writes nothing
# ---------------------------------------------------------------------------


def test_decide_dry_run_writes_nothing(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-dry-run-001",
        status="human_review",
    )
    rf_dir, seed_path, regime_path, requeue_path, root = _setup_decide_env(
        tmp_path, candidate=cand
    )

    # Note initial state of seed
    seed_before = seed_path.read_text()
    transitions_before = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")

    rc = _run_decide(
        tmp_path, rf_dir, seed_path, regime_path, requeue_path,
        candidate_id="rf-dry-run-001",
        decision="paper",
        args_extra=["--expected-half-life-d", "250", "--dry-run"],
    )
    assert rc == 0, "Dry-run should succeed"

    # Nothing written
    seed_after = seed_path.read_text()
    assert seed_before == seed_after, "Dry-run must not modify seed"

    transitions_after = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    assert transitions_before == transitions_after, "Dry-run must not write transitions"

    track_dir = rf_dir / "track"
    assert not any(track_dir.glob("*.json")), "Dry-run must not write track files"


# ---------------------------------------------------------------------------
# Test: queue.md renders for fixture with 2 candidates
# ---------------------------------------------------------------------------


def test_queue_md_renders(tmp_path):
    """W5 exit gate: queue.md renders for a fixture with 2 candidates."""
    from scripts.build_research_factory_review_queue import render_markdown

    cand1 = _make_candidate(candidate_id="rf-md-001", status="human_review")
    cand2 = _make_candidate(
        candidate_id="rf-md-002",
        status="human_review",
        candidate_type="alpha_family",
        domain="entry",
    )
    challenges = {
        "rf-md-001": _make_challenge("rf-md-001"),
    }
    rf_dir = _setup_rf_dir(
        tmp_path,
        candidates=[cand1, cand2],
        challenges=challenges,
    )

    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 2

    md = render_markdown(packets, "2026-07-06T00:00:00+00:00")
    assert "rf-md-001" in md
    assert "rf-md-002" in md
    # Display-only wording
    assert "validated" not in md.lower(), "queue.md must not contain 'validated'"
    # Decision block present
    assert "Decision block" in md
    assert "paper" in md
    assert "deferred" in md
    assert "rejected" in md
    assert "scoped_build" in md
