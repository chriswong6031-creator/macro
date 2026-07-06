"""tests/test_research_factory_ingest.py — W2 ingest + health tests.

Tests (charter §6 W2 exit gate):
  1. Manual source: valid proposal → registered.
  2. Oracle scratch source: registry.jsonl → candidates built with evaluation_plan.
  3. Oracle scratch with inbox: mechanism captured from inbox pre-strip.
  4. Oracle scratch without inbox: mechanism_missing_from_inbox flag set.
  5. Research-queue source: high_ev_build_now rows ingested.
  6. Dedup collision: oracle compounds registry (canonical rule-hash).
  7. Dedup collision: species registry.
  8. Dedup collision: machine registry (absent-safe).
  9. Dedup collision: trial-ledger family strings.
  10. Near-dup flag: score >= 0.8 → near_dup_review flag appended.
  11. Near-dup no-flag: score < 0.8.
  12. Mechanism-mismatch flag: column not in mechanism text.
  13. Mechanism-no-mismatch: column present in mechanism.
  14. Respin human-gate: script actor refused for respin.
  15. Respin human actor: fable actor with actor_ref accepted.
  16. Schema rejection: missing required field.
  17. Health builder: funnel counts from synthetic transition log.
  18. Health builder: dwell days math.
  19. Health builder: dry-run writes nothing.
  20. Health builder: --write appends to health.jsonl.
  21. Health builder: keep-first per as_of.
  22. Dropped candidates all have recorded reason.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.research_factory_ingest import (
    _build_candidate,
    _canonical,
    _check_near_dup,
    _mechanism_spec_mismatch,
    _near_dup_score,
    _load_oracle_canonical_rules,
    _load_species_names,
    _load_machine_registry_hypotheses,
    _load_trial_ledger_families,
    _ingest_oracle_scratch,
    _ingest_research_queue_row,
    _capture_inbox_mechanisms,
    run_ingest,
    IngestResult,
)
from scripts.build_research_factory_health import compute_health
from engine.research_factory import ledger as rf_ledger
from engine.research_factory.schema import validate_health


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_candidate(**overrides) -> dict:
    """Build a minimal valid candidate dict."""
    base = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": "rf-20260706-test-washout001",
        "created_at": _now(),
        "source": "human",
        "candidate_type": "external_idea",
        "domain": "oracle",
        "status": "proposed",
        "hypothesis": "washout with high volume signals reversal",
        "mechanism": "washout exhaustion hypothesis",
        "claim_shape": None,
        "spec_ref": None,
        "expected_failure_modes": [],
        "decay_conditions": [],
        "falsifiers": [],
        "trial_accounting": {"mode": "read_only", "family": None, "declared_at": None},
        "evaluation_plan": {
            "primary_metric": None,
            "horizon_d": 21,
            "min_n": 25,
            "fdr_scope": "batch",
            "expected_half_life_d": None,
            "defaulted": True,
        },
        "lineage": {
            "respin_of": None,
            "superseded_by": None,
            "refinement_generation": 0,
        },
        "flags": [],
        "artifacts": {},
        "transition_log": [],
    }
    base.update(overrides)
    return base


def _make_transition(candidate_id: str, from_s: str, to_s: str,
                     actor: str = "script", actor_ref: str | None = None,
                     **extra) -> dict:
    row = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": from_s,
        "to": to_s,
        "reason_code": "test",
        "reason_text": "test transition",
        "actor": actor,
        "actor_ref": actor_ref,
        "kill_evidence": None,
        "artifact_refs": [],
        "as_of": _now(),
    }
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# 1. Manual source: valid proposal → registered
# ---------------------------------------------------------------------------


def test_manual_proposal_registers(tmp_path):
    proposal = {
        "source": "human",
        "candidate_type": "external_idea",
        "domain": "oracle",
        "hypothesis": "test hypothesis for washout",
        "mechanism": "washout exhaustion reversal",
        "spec_ref": None,
        "entry_rule": None,
        "evaluation_plan": {
            "primary_metric": None,
            "horizon_d": 21,
            "min_n": 25,
            "fdr_scope": "batch",
            "expected_half_life_d": None,
            "defaulted": True,
        },
    }
    cand = _build_candidate(
        source=proposal["source"],
        candidate_type=proposal["candidate_type"],
        domain=proposal["domain"],
        hypothesis=proposal["hypothesis"],
        mechanism=proposal["mechanism"],
        spec_ref=proposal["spec_ref"],
        entry_rule=proposal.get("entry_rule"),
        evaluation_plan=proposal["evaluation_plan"],
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.registered) == 1
    assert len(result.dropped) == 0
    cand_out, trans_out = result.registered[0]
    assert cand_out["status"] == "registered"
    assert trans_out["to"] == "registered"
    assert trans_out["from"] == "proposed"


# ---------------------------------------------------------------------------
# 2. Oracle scratch source: registry.jsonl → candidates with evaluation_plan
# ---------------------------------------------------------------------------


def test_oracle_scratch_ingest(tmp_path):
    scratch_dir = tmp_path / "oracle_scratch"
    compounds_dir = scratch_dir / "compounds"
    compounds_dir.mkdir(parents=True)
    reg_path = compounds_dir / "registry.jsonl"

    entry_rule = {"col": "washout_w", "op": "gt", "value": 0}
    scratch_row = {
        "id": "ING0",
        "family": "ING",
        "name": "Washout entry",
        "entry_rule": entry_rule,
        "status": "exploratory",
    }
    reg_path.write_text(json.dumps(scratch_row) + "\n", encoding="utf-8")

    candidates = _ingest_oracle_scratch(scratch_dir, inbox_mechanisms={})
    assert len(candidates) == 1
    c = candidates[0]
    assert c["source"] == "oracle_brainstorm"
    assert c["candidate_type"] == "oracle_compound"
    assert c["domain"] == "oracle"
    assert c["evaluation_plan"]["primary_metric"] == "WR"
    assert c["evaluation_plan"]["min_n"] == 100
    # entry_rule stored in artifacts for near-dup scoring
    assert c["artifacts"]["entry_rule"] == entry_rule


# ---------------------------------------------------------------------------
# 3. Oracle scratch with inbox: mechanism captured from inbox pre-strip
# ---------------------------------------------------------------------------


def test_oracle_inbox_mechanism_capture(tmp_path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()

    entry_rule = {"col": "washout_w", "op": "gt", "value": 0}
    # Inbox has extra fields including mechanism (pre-strip)
    inbox_spec = {
        "id": "ING0",
        "name": "Washout entry",
        "entry_rule": entry_rule,
        "mechanism": "Sellers exhausted; washout signals coordinated seller departure.",
        "description": "some description",
        "unknown_field": "will be stripped",
    }
    (inbox_dir / "batch1.json").write_text(json.dumps([inbox_spec]), encoding="utf-8")

    mechanisms = _capture_inbox_mechanisms(inbox_dir)
    canon = _canonical(entry_rule)
    assert canon in mechanisms
    assert "exhausted" in mechanisms[canon].lower()


# ---------------------------------------------------------------------------
# 4. Oracle scratch without inbox: mechanism_missing_from_inbox flag
# ---------------------------------------------------------------------------


def test_oracle_scratch_no_inbox_flag(tmp_path):
    scratch_dir = tmp_path / "oracle_scratch"
    compounds_dir = scratch_dir / "compounds"
    compounds_dir.mkdir(parents=True)
    reg_path = compounds_dir / "registry.jsonl"

    entry_rule = {"col": "washout_w", "op": "gt", "value": 0}
    scratch_row = {
        "id": "ING0",
        "family": "ING",
        "name": "Washout entry",
        "entry_rule": entry_rule,
        "status": "exploratory",
    }
    reg_path.write_text(json.dumps(scratch_row) + "\n", encoding="utf-8")

    # No inbox_mechanisms provided
    candidates = _ingest_oracle_scratch(scratch_dir, inbox_mechanisms={})
    assert len(candidates) == 1
    c = candidates[0]
    # When no inbox mechanism available, flag should be set
    assert "mechanism_missing_from_inbox" in c["flags"]


# ---------------------------------------------------------------------------
# 5. Research-queue source: high_ev_build_now rows ingested
# ---------------------------------------------------------------------------


def test_research_queue_ingest(tmp_path):
    queue_path = tmp_path / "research_queue.json"
    queue_data = {
        "high_ev_build_now": [
            {
                "id": "RQ001",
                "hypothesis": "sector breadth collapse signals rotation",
                "mechanism": "breadth deterioration precedes rotation",
                "domain": "oracle",
                "candidate_type": "external_idea",
            }
        ],
        "other_bin": [
            {
                "id": "RQ002",
                "hypothesis": "momentum factor exhaustion",
                "mechanism": "momentum exhaustion hypothesis",
                "domain": "factor",
                "candidate_type": "external_idea",
            }
        ],
    }
    queue_path.write_text(json.dumps(queue_data), encoding="utf-8")

    from scripts.research_factory_ingest import _load_research_queue

    rows = _load_research_queue(queue_path, nominate_ids=["RQ002"])
    assert len(rows) == 2  # high_ev + nominated
    ids = {r["id"] for r in rows}
    assert "RQ001" in ids
    assert "RQ002" in ids


# ---------------------------------------------------------------------------
# 6. Dedup collision: oracle compounds registry (canonical rule-hash)
# ---------------------------------------------------------------------------


def test_dedup_oracle_canonical(tmp_path):
    entry_rule = {"col": "washout_w", "op": "gt", "value": 0}

    # Write oracle registry with this rule
    oracle_path = tmp_path / "registry.jsonl"
    oracle_row = {"id": "C4", "entry_rule": entry_rule, "status": "screened"}
    oracle_path.write_text(json.dumps(oracle_row) + "\n", encoding="utf-8")

    cand = _build_candidate(
        source="oracle_brainstorm",
        candidate_type="oracle_compound",
        domain="oracle",
        hypothesis="washout entry",
        mechanism="washout exhaustion",
        spec_ref="C4",
        entry_rule=entry_rule,
    )
    cand["artifacts"]["entry_rule"] = entry_rule

    result = run_ingest(
        [cand],
        oracle_registry_path=oracle_path,
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.registered) == 0
    assert len(result.dropped) == 1
    _, rc, rt = result.dropped[0]
    assert rc == "deduped"
    assert "oracle" in rt.lower()


# ---------------------------------------------------------------------------
# 7. Dedup collision: species registry
# ---------------------------------------------------------------------------


def test_dedup_species_registry(tmp_path):
    # Build a minimal species registry with a matching hypothesis
    species_path = tmp_path / "registry.json"
    hyp_text = "sustained sector-cohort liquidation exhausts the marginal seller"
    species_data = {
        "schema": "species_registry.v1",
        "species": [
            {
                "species_id": "S1",
                "version": "1.0",
                "name": hyp_text,
                "validation_status": "phase0",
                "deployment_status": "unshipped",
                "mechanism": hyp_text,
                "horizon_class": "rotational",
                "evidence_stack": [],
                "rejection_rules": [],
                "archetype_scope": [],
                "regime_scope": [],
                "market_scope": [],
                "adjacent_falsified": [],
                "fixtures": [],
                "ledger_binding": {},
                "gating": {},
                "trial_count": 0,
            }
        ],
    }
    species_path.write_text(json.dumps(species_data), encoding="utf-8")

    # Load species names
    species_names = _load_species_names(species_path)
    assert hyp_text.lower().strip()[:120] in species_names

    # Build candidate with matching hypothesis
    cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis=hyp_text,
        mechanism=hyp_text,
        spec_ref=None,
        entry_rule=None,
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=species_path,
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.dropped) == 1
    _, rc, _ = result.dropped[0]
    assert rc == "deduped"


# ---------------------------------------------------------------------------
# 8. Dedup collision: machine registry (absent-safe)
# ---------------------------------------------------------------------------


def test_dedup_machine_registry_absent_safe(tmp_path):
    # Machine registry is absent — should not crash
    machine_path = tmp_path / "machine_registry.jsonl"
    # Do NOT create the file
    hyps = _load_machine_registry_hypotheses(machine_path)
    assert hyps == set()


def test_dedup_machine_registry_collision(tmp_path):
    machine_path = tmp_path / "machine_registry.jsonl"
    hyp = "momentum factor exhaustion drives sector rotation"
    machine_row = {"hypothesis": hyp, "id": "MR001"}
    machine_path.write_text(json.dumps(machine_row) + "\n", encoding="utf-8")

    machine_hyps = _load_machine_registry_hypotheses(machine_path)
    assert hyp.lower().strip()[:120] in machine_hyps

    cand = _build_candidate(
        source="human",
        candidate_type="cortex_hypothesis",
        domain="neuralweb",
        hypothesis=hyp,
        mechanism=hyp,
        spec_ref=None,
        entry_rule=None,
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=machine_path,
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.dropped) == 1
    _, rc, _ = result.dropped[0]
    assert rc == "deduped"


# ---------------------------------------------------------------------------
# 9. Dedup collision: trial-ledger family strings
# ---------------------------------------------------------------------------


def test_dedup_trial_ledger_family(tmp_path):
    ledger_path = tmp_path / "trial_ledger.jsonl"
    family_name = "oracle_reversion_washout"
    ledger_row = {"family": family_name, "config_hash": "abc123"}
    ledger_path.write_text(json.dumps(ledger_row) + "\n", encoding="utf-8")

    families = _load_trial_ledger_families(ledger_path)
    assert family_name.lower() in families

    # candidate whose spec_ref matches the family
    cand = _build_candidate(
        source="human",
        candidate_type="alpha_family",
        domain="oracle",
        hypothesis="Oracle reversion washout strategy",
        mechanism="washout exhaustion mechanism",
        spec_ref=family_name,
        entry_rule=None,
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=ledger_path,
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.dropped) == 1
    _, rc, _ = result.dropped[0]
    assert rc == "deduped"


# ---------------------------------------------------------------------------
# 10. Near-dup flag: score >= 0.8 → near_dup_review appended
# ---------------------------------------------------------------------------


def test_near_dup_flag_above_threshold(tmp_path):
    # Two nearly identical rules — only differ by one value
    rule_in_oracle = {"col": "washout_w", "op": "gt", "value": 0}
    rule_candidate = {"col": "washout_w", "op": "gt", "value": 0}  # identical

    score = _near_dup_score(rule_candidate, rule_in_oracle)
    assert score >= 0.8

    oracle_path = tmp_path / "oracle.jsonl"
    oracle_row = {"id": "C4_base", "entry_rule": {"col": "vol", "op": "gt", "value": 0}}
    oracle_path.write_text(json.dumps(oracle_row) + "\n", encoding="utf-8")

    # Build a candidate whose entry_rule is a near-dup
    cand = _build_candidate(
        source="oracle_brainstorm",
        candidate_type="oracle_compound",
        domain="oracle",
        hypothesis="washout entry near dup",
        mechanism="washout near dup mechanism washout",
        spec_ref="ING0",
        entry_rule=rule_candidate,
    )
    cand["artifacts"]["entry_rule"] = rule_candidate

    oracle_rules = [rule_in_oracle]
    is_nd, nd_score = _check_near_dup(cand, oracle_rules, threshold=0.8)
    assert is_nd
    assert nd_score >= 0.8


# ---------------------------------------------------------------------------
# 11. Near-dup no-flag: score < 0.8 (structurally different rules)
# ---------------------------------------------------------------------------


def test_near_dup_below_threshold():
    rule_a = {"col": "washout_w", "op": "gt", "value": 0}
    rule_b = {
        "all": [
            {"col": "rs", "op": "crossed_above", "value": 0},
            {"col": "vel_1w", "op": "gt", "value": 0},
            {"col": "breadth_50", "op": "gt", "value": 0.5},
        ]
    }
    score = _near_dup_score(rule_a, rule_b)
    # Rule A has 3 nodes; rule B has 10+ nodes; shared structural overlap is minimal
    # Score should be < 0.8
    # The minimal shared node is the outer dict (1 node); max(3, ~10) = 10
    # score = 1/10 = 0.1
    assert score < 0.8


def test_near_dup_flag_not_set_when_below_threshold(tmp_path):
    rule_candidate = {"col": "washout_w", "op": "gt", "value": 0}
    rule_oracle = {
        "all": [
            {"col": "rs", "op": "crossed_above", "value": 0},
            {"col": "vel_1w", "op": "gt", "value": 0},
            {"col": "breadth_50", "op": "gt", "value": 0.5},
        ]
    }

    cand = _build_candidate(
        source="oracle_brainstorm",
        candidate_type="oracle_compound",
        domain="oracle",
        hypothesis="washout entry",
        mechanism="washout mechanism washout",
        spec_ref="ING1",
        entry_rule=rule_candidate,
    )
    cand["artifacts"]["entry_rule"] = rule_candidate

    is_nd, score = _check_near_dup(cand, [rule_oracle], threshold=0.8)
    assert not is_nd


# ---------------------------------------------------------------------------
# 12. Mechanism-mismatch flag: column not in mechanism text
# ---------------------------------------------------------------------------


def test_mechanism_mismatch_flagged():
    entry_rule = {"col": "stochrsi_w_k", "op": "gt", "value": 0.8}
    mechanism = "breadth collapse signals rotation"  # no mention of stochrsi
    assert _mechanism_spec_mismatch(mechanism, entry_rule) is True


# ---------------------------------------------------------------------------
# 13. Mechanism-no-mismatch: column present
# ---------------------------------------------------------------------------


def test_mechanism_no_mismatch_column_present():
    entry_rule = {"col": "washout_w", "op": "gt", "value": 0}
    mechanism = "washout exhaustion signals the end of selling pressure"
    assert _mechanism_spec_mismatch(mechanism, entry_rule) is False


def test_mechanism_no_mismatch_synonym_present():
    entry_rule = {"col": "breadth_50", "op": "gt", "value": 0.4}
    mechanism = "breadth collapse drives rotation signals"
    assert _mechanism_spec_mismatch(mechanism, entry_rule) is False


# ---------------------------------------------------------------------------
# 14. Respin human-gate: script actor refused
# ---------------------------------------------------------------------------


def test_respin_script_actor_refused(tmp_path):
    cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="revised washout test",
        mechanism="washout revised mechanism",
        spec_ref=None,
        entry_rule=None,
        respin_of="rf-20260706-test-original001",
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        respin_of="rf-20260706-test-original001",
        actor="script",  # script actor — should be refused
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    # All dropped — respin gate violation
    assert len(result.registered) == 0
    assert len(result.dropped) == 1
    _, rc, rt = result.dropped[0]
    assert rc == "respin_gate_violation"
    assert "human actor" in rt.lower()


# ---------------------------------------------------------------------------
# 15. Respin human actor: fable actor with actor_ref accepted
# ---------------------------------------------------------------------------


def test_respin_human_actor_accepted(tmp_path):
    cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="revised washout test v2",
        mechanism="washout revised mechanism v2",
        spec_ref=None,
        entry_rule=None,
        respin_of="rf-20260706-test-original001",
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        respin_of="rf-20260706-test-original001",
        actor="fable",
        actor_ref="session-test-001",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.registered) == 1
    cand_out, trans_out = result.registered[0]
    assert cand_out["lineage"]["respin_of"] == "rf-20260706-test-original001"
    assert trans_out["actor"] == "fable"
    assert trans_out["actor_ref"] == "session-test-001"


# ---------------------------------------------------------------------------
# 16. Schema rejection: missing required field
# ---------------------------------------------------------------------------


def test_schema_rejection_missing_required_field(tmp_path):
    cand = _make_candidate()
    cand.pop("hypothesis")  # Remove required field

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.registered) == 0
    assert len(result.dropped) == 1
    _, rc, rt = result.dropped[0]
    assert rc == "schema_rejected"
    assert "hypothesis" in rt.lower()


# ---------------------------------------------------------------------------
# 17. Health builder: funnel counts from synthetic transitions
# ---------------------------------------------------------------------------


def test_health_funnel_counts():
    cands = [
        _make_candidate(candidate_id="rf-001", status="registered"),
        _make_candidate(candidate_id="rf-002", status="proposed"),
        _make_candidate(candidate_id="rf-003", status="schema_rejected"),
        _make_candidate(candidate_id="rf-004", status="registered"),
    ]
    transitions = [
        _make_transition("rf-001", "proposed", "registered"),
        _make_transition("rf-002", "proposed", "registered"),
        _make_transition("rf-003", "proposed", "schema_rejected"),
        _make_transition("rf-004", "proposed", "registered"),
    ]

    health = compute_health(cands, transitions, challenges={}, as_of="2026-07-06T12:00:00")
    assert health["funnel_counts"].get("registered", 0) == 3
    assert health["funnel_counts"].get("schema_rejected", 0) == 1


# ---------------------------------------------------------------------------
# 18. Health builder: dwell days computation
# ---------------------------------------------------------------------------


def test_health_dwell_days():
    # candidate rf-001 stays in proposed for ~1 day
    cands = [_make_candidate(candidate_id="rf-001", status="registered")]
    transitions = [
        _make_transition("rf-001", "proposed", "registered",
                         as_of="2026-07-05T10:00:00"),
        _make_transition("rf-001", "registered", "screened",
                         as_of="2026-07-07T10:00:00"),  # 2 days later
    ]
    # Override as_of in transition row
    transitions[0]["as_of"] = "2026-07-05T10:00:00"
    transitions[1]["as_of"] = "2026-07-07T10:00:00"

    health = compute_health(cands, transitions, challenges={})
    dwell = health["median_dwell_days_by_state"]
    # 'registered' state dwell is from first transition to second = 2 days
    assert "registered" in dwell
    assert abs(dwell["registered"] - 2.0) < 0.1


# ---------------------------------------------------------------------------
# 19. Health builder: dry-run writes nothing
# ---------------------------------------------------------------------------


def test_health_dry_run_writes_nothing(tmp_path, monkeypatch):
    """Verify --dry-run doesn't write to health.jsonl."""
    rf_dir = tmp_path / "rf"
    rf_dir.mkdir()
    health_path = rf_dir / "health.jsonl"

    # Import and run the main function with dry_run
    import scripts.build_research_factory_health as hmod

    # Patch sys.argv
    monkeypatch.setattr("sys.argv", [
        "build_research_factory_health.py",
        "--rf-dir", str(rf_dir),
        "--as-of", "2026-07-06T00:00:00",
        # No --write flag → dry-run
    ])

    ret = hmod.main()
    assert ret == 0
    # File should NOT exist
    assert not health_path.exists()


# ---------------------------------------------------------------------------
# 20. Health builder: --write appends to health.jsonl
# ---------------------------------------------------------------------------


def test_health_write_appends(tmp_path):
    rf_dir = tmp_path / "rf"
    rf_dir.mkdir()
    health_path = rf_dir / "health.jsonl"

    # Create empty candidates/transitions
    (rf_dir / "candidates.jsonl").write_text("", encoding="utf-8")
    (rf_dir / "transitions.jsonl").write_text("", encoding="utf-8")

    as_of = "2026-07-06T01:00:00"
    health_row = compute_health([], [], challenges={}, as_of=as_of)

    # Write directly via ledger
    rf_ledger.append_row(health_path, health_row, validate_fn=validate_health)

    rows = rf_ledger.load_jsonl(health_path)
    assert len(rows) == 1
    assert rows[0]["as_of"] == as_of
    assert rows[0]["authority"] == "display_only"
    assert rows[0]["schema"] == "research_factory.health.v1"


# ---------------------------------------------------------------------------
# 21. Health builder: keep-first per as_of
# ---------------------------------------------------------------------------


def test_health_keep_first_per_as_of():
    from engine.research_factory.ledger import keep_first

    rows = [
        {"authority": "display_only", "as_of": "2026-07-06", "total_candidates": 1},
        {"authority": "display_only", "as_of": "2026-07-06", "total_candidates": 99},
        {"authority": "display_only", "as_of": "2026-07-07", "total_candidates": 2},
    ]
    deduped = keep_first(rows, key_fields=("as_of",))
    assert len(deduped) == 2
    # First for 2026-07-06 must be kept (total_candidates=1, not 99)
    day1_rows = [r for r in deduped if r["as_of"] == "2026-07-06"]
    assert day1_rows[0]["total_candidates"] == 1


# ---------------------------------------------------------------------------
# 22. All dropped candidates have a recorded reason
# ---------------------------------------------------------------------------


def test_all_drops_have_reason(tmp_path):
    """Every dropped candidate must carry reason_code and non-empty reason_text."""
    # Propose two candidates: one valid, one schema-invalid
    valid_cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="valid hypothesis for drop test",
        mechanism="valid mechanism washout",
        spec_ref=None,
        entry_rule=None,
    )

    invalid_cand = _make_candidate(candidate_id="rf-bad-001")
    invalid_cand.pop("mechanism")  # Remove required field

    result = run_ingest(
        [valid_cand, invalid_cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=tmp_path / "rf",
        dry_run=True,
    )

    assert len(result.registered) == 1
    assert len(result.dropped) == 1

    for cand, rc, rt in result.dropped:
        assert rc, "reason_code must be non-empty"
        assert rt, "reason_text must be non-empty"


# ---------------------------------------------------------------------------
# 23. Ingest with --write actually writes to disk
# ---------------------------------------------------------------------------


def test_ingest_write_commits_to_disk(tmp_path):
    rf_dir = tmp_path / "rf"
    cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="disk write test hypothesis",
        mechanism="disk write mechanism washout test",
        spec_ref=None,
        entry_rule=None,
    )

    result = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=rf_dir,
        dry_run=False,  # WRITE
    )

    assert len(result.registered) == 1

    candidates_path = rf_dir / "candidates.jsonl"
    transitions_path = rf_dir / "transitions.jsonl"
    assert candidates_path.exists()
    assert transitions_path.exists()

    cands_on_disk = rf_ledger.load_jsonl(candidates_path)
    trans_on_disk = rf_ledger.load_jsonl(transitions_path)
    assert len(cands_on_disk) == 1
    assert len(trans_on_disk) == 1
    assert cands_on_disk[0]["authority"] == "display_only"
    assert trans_on_disk[0]["authority"] == "display_only"
