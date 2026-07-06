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
  23. Ingest with --write actually writes to disk.
  24. Idempotent re-ingest: same candidate_id → exactly one disk row.
  25. RF-15 generation cap: respin of a gen-2 parent → rf15_generation_cap.
  26. Health builder: mixed tz as_of values do not raise TypeError.
  27. RF-15 fail-closed: respin parent absent from non-empty ledger → rf15_parent_not_found.
  28. Dedup ordering: oracle-colliding re-ingested candidate → exactly one disk row.
  29. Divergence: ADVISORY_REVIEW + reject not counted; ADVISORY_PASS/REJECT divergences counted.
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


# ---------------------------------------------------------------------------
# 24. Idempotent re-ingest: same candidate_id produces exactly one row (Fix finding 1)
# ---------------------------------------------------------------------------


def test_idempotent_reingest_dedup(tmp_path):
    """Running --write ingest twice with the same candidate_id must not produce
    duplicate candidate rows or duplicate proposed→registered transitions.
    The second run must drop the candidate with reason_code 'deduped' and the
    factory-ledger drop reason, leaving exactly one candidate and one transition
    on disk."""
    rf_dir = tmp_path / "rf"

    cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="idempotent reingest hypothesis washout",
        mechanism="washout idempotent reingest mechanism",
        spec_ref=None,
        entry_rule=None,
    )
    # Pin the candidate_id so both runs collide
    cand["candidate_id"] = "rf-idem-test-001"

    common_kwargs = dict(
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=rf_dir,
    )

    # First ingest: should register
    result1 = run_ingest([cand], dry_run=False, **common_kwargs)
    assert len(result1.registered) == 1
    assert len(result1.dropped) == 0

    # Load existing_ids from disk (as main() does)
    existing_ids: set[str] = set()
    for ec in rf_ledger.load_jsonl(rf_dir / "candidates.jsonl"):
        cid = ec.get("candidate_id")
        if cid:
            existing_ids.add(cid)
    assert "rf-idem-test-001" in existing_ids

    # Second ingest: same candidate_id — must be deduped, not registered again
    result2 = run_ingest(
        [cand],
        dry_run=False,
        existing_candidate_ids=existing_ids,
        **common_kwargs,
    )
    assert len(result2.registered) == 0, "second run must NOT register a duplicate"
    assert len(result2.dropped) == 1
    _, rc2, rt2 = result2.dropped[0]
    assert rc2 == "deduped"
    assert "factory ledger" in rt2.lower() or "idempotent" in rt2.lower()

    # Disk must still have exactly one candidate row and one registered transition
    cands_on_disk = rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
    trans_on_disk = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    reg_trans = [t for t in trans_on_disk if t.get("to") == "registered"]
    assert len(cands_on_disk) == 1, f"expected 1 candidate on disk, got {len(cands_on_disk)}"
    assert len(reg_trans) == 1, f"expected 1 registered transition, got {len(reg_trans)}"


# ---------------------------------------------------------------------------
# 25. RF-15 generation cap: respin of a gen-2 parent → rejected, not gen-1 (Fix finding 2)
# ---------------------------------------------------------------------------


def test_rf15_generation_cap_rejects_gen3(tmp_path):
    """A respin of a generation-2 parent must be dropped as rf15_generation_cap,
    not registered as generation 1.  This closes the anti-p-hacking rail (RF-15)."""
    rf_dir = tmp_path / "rf"
    rf_dir.mkdir()

    # Write a gen-2 parent candidate to the factory ledger
    parent_id = "rf-gen2-parent-001"
    parent_cand = _make_candidate(
        candidate_id=parent_id,
        status="registered",
        lineage={
            "respin_of": "rf-gen1-parent-000",
            "superseded_by": None,
            "refinement_generation": 2,
        },
    )
    candidates_path = rf_dir / "candidates.jsonl"
    candidates_path.write_text(
        json.dumps(parent_cand) + "\n", encoding="utf-8"
    )

    # Attempt respin of the gen-2 parent
    child_cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="rf15 cap test child hypothesis washout",
        mechanism="washout rf15 cap child mechanism",
        spec_ref=None,
        entry_rule=None,
        respin_of=parent_id,
    )

    result = run_ingest(
        [child_cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        respin_of=parent_id,
        actor="fable",
        actor_ref="session-rf15-cap-test",
        rf_dir=rf_dir,
        dry_run=True,
    )

    assert len(result.registered) == 0, "gen-3 respin must NOT be registered"
    assert len(result.dropped) == 1
    _, rc, rt = result.dropped[0]
    assert rc == "rf15_generation_cap", f"expected rf15_generation_cap, got {rc!r}"
    assert "3" in rt or "cap" in rt.lower()


# ---------------------------------------------------------------------------
# 26. Health builder: mixed tz as_of values do not raise TypeError (Fix finding 3)
# ---------------------------------------------------------------------------


def test_health_dwell_mixed_tz_offsets():
    """Dwell-day math must not raise TypeError when transition as_of values carry
    different timezone offsets (+00:00 vs -05:00 vs bare Z)."""
    from scripts.build_research_factory_health import _days_between, compute_health

    # Verify the helper itself handles all three formats without raising
    d1 = _days_between("2026-07-05T10:00:00+00:00", "2026-07-06T10:00:00-05:00")
    # +00:00 10:00 vs -05:00 10:00 → the -05:00 is actually 15:00 UTC → diff = 29h = 1.208d
    assert d1 is not None, "_days_between must not return None for valid tz-aware timestamps"
    assert 1.0 < d1 < 2.0, f"expected ~1.2d, got {d1}"

    d2 = _days_between("2026-07-05T00:00:00Z", "2026-07-06T00:00:00+00:00")
    assert d2 is not None
    assert abs(d2 - 1.0) < 0.01, f"Z vs +00:00 should be 1.0 day, got {d2}"

    # Full compute_health must not raise with mixed-tz transitions
    cands = [_make_candidate(candidate_id="rf-tz-001", status="registered")]
    transitions = [
        _make_transition("rf-tz-001", "proposed", "registered",
                         as_of="2026-07-05T10:00:00+00:00"),
        _make_transition("rf-tz-001", "registered", "screened",
                         as_of="2026-07-06T10:00:00-05:00"),
    ]
    # Should not raise
    health = compute_health(cands, transitions, challenges={})
    assert "median_dwell_days_by_state" in health
    assert health["median_dwell_days_by_state"].get("registered") is not None


def test_dwell_days_tz_ordering_lexical_vs_chronological():
    """Dwell must be attributed to the correct from-state when two transitions have
    different UTC offsets such that lexical and chronological order disagree.

    Scenario
    --------
    trans A: '2026-07-05T10:00:00-05:00'  →  UTC 2026-07-05T15:00:00Z  (15:00 UTC)
    trans B: '2026-07-05T12:00:00+00:00'  →  UTC 2026-07-05T12:00:00Z  (12:00 UTC)

    Lexically A < B (strings compare as '…10:00…' < '…12:00…'), but chronologically
    B (12:00 UTC) < A (15:00 UTC).  The _parse_iso-based sort in compute_health must
    use chronological order, so dwell for 'registered' state is attributed to B→A
    (3 hours = 0.125 days), not A→B (which would be negative and nonsensical).

    Transition sequence under correct chronological sort:
      B (12:00Z): proposed → registered   (entering 'registered' state)
      A (15:00Z): registered → screened   (leaving 'registered' state)
    Dwell in 'registered' = 15:00Z − 12:00Z = 3h = 0.125d

    Under wrong lexical sort:
      A (string '10:00') would be placed first → proposed → registered at 15:00Z,
      then B (string '12:00') → registered → screened at 12:00Z,
      giving a negative time difference that would either return None or produce
      an incorrect dwell attribution.
    """
    from scripts.build_research_factory_health import compute_health

    # B is chronologically first (12:00 UTC), A is chronologically second (15:00 UTC).
    # Lexically A's string sorts before B's string.
    ts_A = "2026-07-05T10:00:00-05:00"  # = 15:00 UTC
    ts_B = "2026-07-05T12:00:00+00:00"  # = 12:00 UTC

    cands = [_make_candidate(candidate_id="rf-tzorder-001", status="screened")]
    # B fires first (chronologically), A fires second
    transitions = [
        _make_transition("rf-tzorder-001", "proposed", "registered", as_of=ts_B),
        _make_transition("rf-tzorder-001", "registered", "screened", as_of=ts_A),
    ]

    health = compute_health(cands, transitions, challenges={})
    dwell = health["median_dwell_days_by_state"]

    # 'registered' dwell must be ~3h = 0.125d (chronological: B→A)
    assert "registered" in dwell, "registered state must appear in dwell map"
    registered_dwell = dwell["registered"]
    assert registered_dwell is not None, "_parse_iso sort must yield a valid dwell"
    # Under correct chronological sort: 3h / 24 = 0.125d
    # Allow a small float tolerance
    assert abs(registered_dwell - 0.125) < 0.01, (
        f"dwell in 'registered' must be ~0.125d (3h, chronological B→A); "
        f"got {registered_dwell}d — possible lexical-sort bug"
    )


# ---------------------------------------------------------------------------
# 27. RF-15 fail-closed: respin with parent absent from non-empty ledger → dropped
# ---------------------------------------------------------------------------


def test_rf15_parent_not_found_fails_closed(tmp_path):
    """When respin_of is set and the factory ledger exists but the parent
    candidate_id is not in it, the child must be dropped as 'rf15_parent_not_found'
    rather than silently registering as generation-1 (RF-15 fail-closed rule)."""
    rf_dir = tmp_path / "rf"
    rf_dir.mkdir()

    # Write a *different* candidate to the ledger so the ledger is non-empty
    unrelated_cand = _make_candidate(
        candidate_id="rf-unrelated-001",
        status="registered",
        lineage={"respin_of": None, "superseded_by": None, "refinement_generation": 0},
    )
    candidates_path = rf_dir / "candidates.jsonl"
    candidates_path.write_text(json.dumps(unrelated_cand) + "\n", encoding="utf-8")

    # Attempt respin of a parent that does NOT exist in the ledger
    missing_parent_id = "rf-gen2-parent-XYZ"
    child_cand = _build_candidate(
        source="human",
        candidate_type="external_idea",
        domain="oracle",
        hypothesis="rf15 fail-closed test child hypothesis washout",
        mechanism="washout rf15 fail-closed child mechanism",
        spec_ref=None,
        entry_rule=None,
        respin_of=missing_parent_id,
    )

    result = run_ingest(
        [child_cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        respin_of=missing_parent_id,
        actor="fable",
        actor_ref="session-rf15-failclosed-test",
        rf_dir=rf_dir,
        dry_run=True,
    )

    assert len(result.registered) == 0, (
        "child whose parent is absent from ledger must NOT be registered as gen-1"
    )
    assert len(result.dropped) == 1
    _, rc, rt = result.dropped[0]
    assert rc == "rf15_parent_not_found", (
        f"expected 'rf15_parent_not_found', got {rc!r}; "
        f"fail-closed rule prevents silent gen-1 registration"
    )
    assert missing_parent_id in rt, "drop reason must name the missing parent_id"


# ---------------------------------------------------------------------------
# 28. Dedup ordering: oracle-colliding candidate re-ingested leaves one disk row
# ---------------------------------------------------------------------------


def test_dedup_oracle_collision_reingest_no_duplicate_rows(tmp_path):
    """A candidate whose candidate_id is already on disk AND whose entry_rule also
    collides with the oracle registry must not accumulate extra rows on re-ingest.
    The factory_ledger check (step 0) must fire before the oracle check (step 1)
    so the disk-write skip applies and candidates.jsonl stays at exactly one row."""
    rf_dir = tmp_path / "rf"

    entry_rule = {"col": "reingest_oracle_col", "op": "gt", "value": 0}

    # Oracle registry contains the same entry_rule
    oracle_path = tmp_path / "oracle_registry.jsonl"
    oracle_path.write_text(
        json.dumps({"id": "C-REINGEST", "entry_rule": entry_rule, "status": "screened"}) + "\n",
        encoding="utf-8",
    )

    cand = _build_candidate(
        source="oracle_brainstorm",
        candidate_type="oracle_compound",
        domain="oracle",
        hypothesis="reingest oracle collision test hypothesis washout",
        mechanism="washout reingest oracle collision mechanism",
        spec_ref="C-REINGEST",
        entry_rule=entry_rule,
    )
    cand["artifacts"]["entry_rule"] = entry_rule
    cand["candidate_id"] = "rf-reingest-oracle-001"

    common_kwargs = dict(
        oracle_registry_path=oracle_path,
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=rf_dir,
    )

    # First ingest with the oracle registry ABSENT (no oracle path) so it registers.
    # Use a clean oracle path to let the first run succeed.
    result1 = run_ingest(
        [cand],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=rf_dir,
        dry_run=False,
    )
    assert len(result1.registered) == 1, "first run must register the candidate"

    # Load the existing candidate_ids from disk
    existing_ids: set[str] = set()
    for ec in rf_ledger.load_jsonl(rf_dir / "candidates.jsonl"):
        eid = ec.get("candidate_id")
        if eid:
            existing_ids.add(eid)
    assert "rf-reingest-oracle-001" in existing_ids

    # Second run: same candidate, now also collides with oracle registry.
    # The factory_ledger check must fire first → skip disk write.
    result2 = run_ingest(
        [cand],
        existing_candidate_ids=existing_ids,
        dry_run=False,
        **common_kwargs,
    )
    assert len(result2.registered) == 0, "second run must NOT register a duplicate"
    assert len(result2.dropped) == 1
    _, rc2, _ = result2.dropped[0]
    assert rc2 == "deduped", f"expected 'deduped', got {rc2!r}"

    # Disk must have exactly one candidate row regardless of oracle collision
    cands_on_disk = rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
    reg_trans_on_disk = [
        t for t in rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
        if t.get("to") == "registered"
    ]
    assert len(cands_on_disk) == 1, (
        f"expected exactly 1 candidate on disk after re-ingest, got {len(cands_on_disk)}"
    )
    assert len(reg_trans_on_disk) == 1, (
        f"expected exactly 1 registered transition, got {len(reg_trans_on_disk)}"
    )


# ---------------------------------------------------------------------------
# 28b. Re-ingest idempotency when candidate_id is date-stamped (not pinned)
# ---------------------------------------------------------------------------


def test_oracle_reingest_idempotent_with_date_stamped_id(tmp_path, monkeypatch):
    """The same Oracle compound re-ingested on two different calendar dates must
    not accumulate unbounded rows in candidates.jsonl even though
    _make_candidate_id() embeds datetime.now() and produces a NEW candidate_id
    on each run.

    Root cause: when candidate_id changes between runs the factory_ledger step-0
    guard (keyed on candidate_id) misses, and the oracle_canonical_rules step-1
    guard fires instead.  With RF-8 keep-first drop persistence, step-1 writes
    exactly ONE deduped candidate + ONE deduped transition on first sight of the
    oracle collision, then skips on all subsequent re-ingests (keyed by entry_rule
    hash).  After two runs candidates.jsonl has exactly 2 rows (1 registered +
    1 deduped) and transitions.jsonl has 2 rows (1 registered + 1 deduped).
    A hypothetical run 3 with the same entry_rule would leave counts unchanged.
    """
    import scripts.research_factory_ingest as _ingest_mod

    rf_dir = tmp_path / "rf"

    entry_rule = {"col": "date_stamped_oracle_col", "op": "gt", "value": 0}

    # Oracle registry already contains this entry_rule.
    oracle_path = tmp_path / "oracle_registry.jsonl"
    oracle_path.write_text(
        json.dumps({"id": "C-DATESTAMP", "entry_rule": entry_rule, "status": "screened"}) + "\n",
        encoding="utf-8",
    )

    def _make_proposal_with_id(candidate_id_suffix: str) -> dict:
        """Build a candidate with a specific date-stamped candidate_id,
        simulating what _make_candidate_id produces on different calendar days.
        The id is NOT pinned via the external caller — it is injected via
        monkeypatching _make_candidate_id so _build_candidate mints it."""
        _original = _ingest_mod._make_candidate_id

        def _patched(source_tag: str, slug: str) -> str:
            return f"rf-{candidate_id_suffix}-{source_tag}-datestamptest"

        monkeypatch.setattr(_ingest_mod, "_make_candidate_id", _patched)
        cand = _build_candidate(
            source="oracle_brainstorm",
            candidate_type="oracle_compound",
            domain="oracle",
            hypothesis="date-stamped oracle reingest idempotency test hypothesis",
            mechanism="date-stamped oracle reingest idempotency mechanism",
            spec_ref="C-DATESTAMP",
            entry_rule=entry_rule,
        )
        monkeypatch.setattr(_ingest_mod, "_make_candidate_id", _original)
        cand["artifacts"]["entry_rule"] = entry_rule
        return cand

    # Run 1: day 1 — no oracle registry, so it registers normally.
    cand_day1 = _make_proposal_with_id("20260705")
    assert "20260705" in cand_day1["candidate_id"], "day-1 id must embed the date"

    result1 = run_ingest(
        [cand_day1],
        oracle_registry_path=tmp_path / "no_oracle.jsonl",
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=rf_dir,
        dry_run=False,
    )
    assert len(result1.registered) == 1, "day-1 ingest must register the candidate"

    # Collect existing ids from disk (as the CLI does between runs)
    existing_ids: set[str] = set()
    for ec in rf_ledger.load_jsonl(rf_dir / "candidates.jsonl"):
        eid = ec.get("candidate_id")
        if eid:
            existing_ids.add(eid)
    assert any("20260705" in cid for cid in existing_ids)

    # Run 2: day 2 — a new date-stamped id ("20260706-…") but same entry_rule.
    # oracle_canonical_rules step-1 should fire and dedup it without writing.
    cand_day2 = _make_proposal_with_id("20260706")
    assert "20260706" in cand_day2["candidate_id"], "day-2 id must embed the new date"
    assert cand_day2["candidate_id"] not in existing_ids, (
        "day-2 candidate_id must differ from day-1 (date-stamped ids change daily)"
    )

    result2 = run_ingest(
        [cand_day2],
        oracle_registry_path=oracle_path,
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        existing_candidate_ids=existing_ids,
        rf_dir=rf_dir,
        dry_run=False,
    )
    assert len(result2.registered) == 0, "day-2 re-ingest must not register a duplicate"
    assert len(result2.dropped) == 1, "day-2 re-ingest must drop the candidate as deduped"
    _, rc2, _ = result2.dropped[0]
    assert rc2 == "deduped", f"expected 'deduped', got {rc2!r}"

    # Key invariants after two runs:
    #   candidates.jsonl: 2 rows (1 registered day-1 + 1 deduped day-2)
    #   transitions.jsonl: 2 rows (1 registered + 1 deduped)
    # A run 3 with the same entry_rule would leave counts unchanged (idempotent).
    cands_on_disk = rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
    assert len(cands_on_disk) == 2, (
        f"expected exactly 2 candidate rows on disk after re-ingest across two dates "
        f"(1 registered + 1 deduped), got {len(cands_on_disk)}"
    )
    registered_cands = [c for c in cands_on_disk if c.get("status") == "registered"]
    assert len(registered_cands) == 1, (
        f"expected 1 registered candidate, got {len(registered_cands)}"
    )
    reg_trans_on_disk = [
        t for t in rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
        if t.get("to") == "registered"
    ]
    assert len(reg_trans_on_disk) == 1, (
        f"expected exactly 1 registered transition, got {len(reg_trans_on_disk)}"
    )
    # After run 2 the oracle collision must have persisted exactly ONE deduped
    # transition row (RF-8 keep-first audit).  The count must be STABLE: a
    # hypothetical run 3 with the same entry_rule would find the key already
    # on disk and skip writing, leaving the total at 1.
    deduped_trans_on_disk = [
        t for t in rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
        if t.get("to") == "deduped"
    ]
    assert len(deduped_trans_on_disk) == 1, (
        f"exactly 1 deduped transition row must be written to disk for the first "
        f"external-registry collision (RF-8 keep-first audit); "
        f"got {len(deduped_trans_on_disk)}"
    )
    # Also verify a deduped candidate row was written
    deduped_cands_on_disk = [
        c for c in rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
        if c.get("status") == "deduped"
    ]
    assert len(deduped_cands_on_disk) == 1, (
        f"exactly 1 deduped candidate row must be on disk; "
        f"got {len(deduped_cands_on_disk)}"
    )


# ---------------------------------------------------------------------------
# 29. Divergence: ADVISORY_REVIEW + human reject does NOT count as divergence
# ---------------------------------------------------------------------------


def test_advisory_review_rejected_not_divergence():
    """ADVISORY_REVIEW is a neutral recommendation (no directional expectation).
    A human 'rejected' after ADVISORY_REVIEW is an intended human-authored kill, not
    rubber-stamp divergence.  divergence_rate must be None or 0.0 for this pair."""
    cand = _make_candidate(candidate_id="rf-div-test-001", status="human_review")
    transitions = [
        _make_transition("rf-div-test-001", "human_review", "rejected"),
    ]
    challenges = {
        "rf-div-test-001": {
            "reviewer": {"recommendation": "ADVISORY_REVIEW"},
        }
    }
    health = compute_health([cand], transitions, challenges=challenges)
    chd = health["challenger_divergence"]
    # ADVISORY_REVIEW is excluded from numerator and denominator — total_adjudicated=0
    assert chd["total_adjudicated"] == 0, (
        f"ADVISORY_REVIEW must be excluded from adjudicated count; "
        f"got total_adjudicated={chd['total_adjudicated']}"
    )
    assert chd["divergence_rate"] is None or chd["divergence_rate"] == 0.0, (
        f"ADVISORY_REVIEW → rejected must NOT be divergence; "
        f"got divergence_rate={chd['divergence_rate']}"
    )


def test_advisory_pass_rejected_is_divergence():
    """ADVISORY_PASS + human 'rejected' IS a divergence (directional mismatch)."""
    cand = _make_candidate(candidate_id="rf-div-test-002", status="human_review")
    transitions = [
        _make_transition("rf-div-test-002", "human_review", "rejected"),
    ]
    challenges = {
        "rf-div-test-002": {
            "reviewer": {"recommendation": "ADVISORY_PASS"},
        }
    }
    health = compute_health([cand], transitions, challenges=challenges)
    chd = health["challenger_divergence"]
    assert chd["total_adjudicated"] == 1
    assert chd["divergence_rate"] == 1.0, (
        f"ADVISORY_PASS → rejected must count as divergence; "
        f"got divergence_rate={chd['divergence_rate']}"
    )


def test_advisory_reject_not_rejected_is_divergence():
    """ADVISORY_REJECT + human non-reject IS a divergence (directional mismatch)."""
    cand = _make_candidate(candidate_id="rf-div-test-003", status="human_review")
    transitions = [
        _make_transition("rf-div-test-003", "human_review", "paper"),
    ]
    challenges = {
        "rf-div-test-003": {
            "reviewer": {"recommendation": "ADVISORY_REJECT"},
        }
    }
    health = compute_health([cand], transitions, challenges=challenges)
    chd = health["challenger_divergence"]
    assert chd["total_adjudicated"] == 1
    assert chd["divergence_rate"] == 1.0, (
        f"ADVISORY_REJECT → paper must count as divergence; "
        f"got divergence_rate={chd['divergence_rate']}"
    )


# ===========================================================================
# W7 / A2 amendment tests — domain_registry adoption (RF-2, A2)
# ===========================================================================

from scripts.research_factory_ingest import (
    adopt_oracle_compounds,
    _load_existing_adopted_spec_refs,
    _build_adoption_candidate,
    _oracle_track_for_registry_row,
    _trial_accounting_for_oracle_adoption,
    _load_oracle_registry_indexed,
    _load_promotion_queue_json,
)


def _make_oracle_registry_row(
    compound_id: str = "TEST_COMPOUND_01",
    name: str = "Test Compound",
    status: str = "screened",
    with_reversion_pass: bool = True,
    mechanism_en: str = "test mechanism",
) -> dict:
    """Build a minimal oracle registry row for test fixtures."""
    row: dict = {
        "id": compound_id,
        "family": "TEST",
        "name": name,
        "mechanism_en": mechanism_en,
        "mechanism_zh": "",
        "entry_rule": {"col": "washout_w", "op": "gt", "value": 0},
        "condition_rule": None,
        "universe": {"tier": "s"},
        "horizons": [21, 63],
        "status": status,
        "created": "2026-07-06",
        "lineage": "test",
        "live_n": 0,
        "live_effect": None,
    }
    if with_reversion_pass:
        row["reversion"] = {
            "gauntlet": "PASS",
            "n": 500,
            "wr": 0.65,
            "asym": 1.8,
            "ret_exit": 0.025,
            "asof": "2026-07-06",
        }
    return row


def _make_oracle_registry_jsonl(path: Path, rows: list[dict]) -> None:
    """Write a list of registry rows to a JSONL file."""
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _make_promotion_queue_json(path: Path, candidates: list[dict],
                               search_width: int = 110) -> None:
    """Write a promotion_queue.json file."""
    data = {
        "schema": "oracle.promotion_queue.v1",
        "generated_at": "2026-07-06T00:00:00Z",
        "search_width": search_width,
        "n_candidates": len(candidates),
        "candidates": candidates,
        "note": "test fixture",
    }
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# 30. Adoption round-trip: domain_registry source, correct fields
# ---------------------------------------------------------------------------


def test_adoption_round_trip(tmp_path):
    """Adopting a known compound_id produces a registered candidate with
    source='domain_registry', candidate_type='oracle_compound', spec_ref set."""
    oracle_reg = tmp_path / "registry.jsonl"
    registry_row = _make_oracle_registry_row("A15_WASHOUT_OPP_OUT_2NODE")
    _make_oracle_registry_jsonl(oracle_reg, [registry_row])

    pq_path = tmp_path / "promotion_queue.json"
    pq_candidate = {
        "compound_id": "A15_WASHOUT_OPP_OUT_2NODE",
        "compound_name": "Washout two-node",
        "n": 2357,
        "effect_63d": 0.013,
        "hit_63d": 0.571,
        "era_consistent_63d": 4,
        "search_width_at_scan": 110,
        "floor_passed": {"n_ge_100": True, "abs_effect63_ge_1pct": True,
                         "hit63_ge_55pct": True, "era_consistent_ge_3": True},
        "current_status": "screened",
    }
    _make_promotion_queue_json(pq_path, [pq_candidate])

    rf_dir = tmp_path / "rf"
    result = adopt_oracle_compounds(
        ["A15_WASHOUT_OPP_OUT_2NODE"],
        oracle_registry_path=oracle_reg,
        promotion_queue_path=pq_path,
        rf_dir=rf_dir,
        dry_run=True,
    )

    assert len(result.registered) == 1, f"expected 1 registered, got {len(result.registered)}"
    assert len(result.dropped) == 0
    cand_out, trans_out = result.registered[0]

    assert cand_out["source"] == "domain_registry"
    assert cand_out["candidate_type"] == "oracle_compound"
    assert cand_out["spec_ref"] == "A15_WASHOUT_OPP_OUT_2NODE"
    assert cand_out["domain"] == "oracle"
    assert cand_out["status"] == "registered"
    assert cand_out["authority"] == "display_only"
    assert trans_out["to"] == "registered"
    assert trans_out["from"] == "proposed"
    assert trans_out["actor"] == "script"
    # trial_accounting: reversion track → read_only
    ta = cand_out["trial_accounting"]
    assert ta["mode"] == "read_only", f"expected read_only for reversion track, got {ta['mode']}"


# ---------------------------------------------------------------------------
# 31. Unknown compound_id fails loudly
# ---------------------------------------------------------------------------


def test_adoption_unknown_compound_id_fails(tmp_path):
    """Adopting a compound_id that does not exist in the oracle registry must fail
    loudly: dropped with reason_code='adopt_unknown_compound_id'."""
    oracle_reg = tmp_path / "registry.jsonl"
    _make_oracle_registry_jsonl(oracle_reg, [_make_oracle_registry_row("KNOWN_001")])

    rf_dir = tmp_path / "rf"
    result = adopt_oracle_compounds(
        ["UNKNOWN_XYZ_NOT_IN_REGISTRY"],
        oracle_registry_path=oracle_reg,
        promotion_queue_path=tmp_path / "no_pq.json",
        rf_dir=rf_dir,
        dry_run=True,
    )

    assert len(result.registered) == 0
    assert len(result.dropped) == 1
    _, rc, rt = result.dropped[0]
    assert rc == "adopt_unknown_compound_id", f"expected adopt_unknown_compound_id, got {rc!r}"
    assert "UNKNOWN_XYZ_NOT_IN_REGISTRY" in rt


# ---------------------------------------------------------------------------
# 32. Idempotent re-adoption: same spec_ref skipped on second call
# ---------------------------------------------------------------------------


def test_adoption_idempotent_readoption(tmp_path):
    """Re-adopting an already-adopted spec_ref must be silently skipped (keep-first).
    The factory ledger must not accumulate a second row."""
    oracle_reg = tmp_path / "registry.jsonl"
    registry_row = _make_oracle_registry_row("IDEM_TEST_01")
    _make_oracle_registry_jsonl(oracle_reg, [registry_row])

    rf_dir = tmp_path / "rf"
    common_kwargs = dict(
        oracle_registry_path=oracle_reg,
        promotion_queue_path=tmp_path / "no_pq.json",
        rf_dir=rf_dir,
    )

    # First adoption: should register
    result1 = adopt_oracle_compounds(["IDEM_TEST_01"], dry_run=False, **common_kwargs)
    assert len(result1.registered) == 1

    # Second adoption of same spec_ref: must be skipped (idempotent)
    result2 = adopt_oracle_compounds(["IDEM_TEST_01"], dry_run=False, **common_kwargs)
    assert len(result2.registered) == 0, "re-adoption must not add a second row"

    # Factory ledger must still have exactly one candidate
    from engine.research_factory.ledger import load_jsonl
    cands_on_disk = [c for c in load_jsonl(rf_dir / "candidates.jsonl")
                     if c.get("status") == "registered"]
    assert len(cands_on_disk) == 1, (
        f"idempotent re-adoption must leave exactly 1 registered row; "
        f"got {len(cands_on_disk)}"
    )


# ---------------------------------------------------------------------------
# 33. Dedup waiver scoped to the declared spec_ref only
# ---------------------------------------------------------------------------


def test_adoption_dedup_waiver_scoped_to_declared_spec_ref(tmp_path):
    """The dedup rule-1 waiver applies ONLY to the explicitly declared spec_ref.
    A different candidate whose entry_rule collides with the oracle registry
    (but is not a declared adoption target) must still be deduped normally."""
    entry_rule = {"col": "washout_w", "op": "gt", "value": 0}

    oracle_reg = tmp_path / "registry.jsonl"
    # ADOPT_TARGET: the compound being adopted
    adopt_target = _make_oracle_registry_row("ADOPT_TARGET_01", mechanism_en="washout mechanism")
    adopt_target["entry_rule"] = entry_rule
    # COLLIDER: NOT an adoption target, but has the same entry_rule
    collider = _make_oracle_registry_row("COLLIDER_001", mechanism_en="collider mechanism")
    collider["entry_rule"] = entry_rule
    _make_oracle_registry_jsonl(oracle_reg, [adopt_target, collider])

    rf_dir = tmp_path / "rf"
    # Adopt only ADOPT_TARGET_01 — waiver scoped to it
    result = adopt_oracle_compounds(
        ["ADOPT_TARGET_01"],
        oracle_registry_path=oracle_reg,
        promotion_queue_path=tmp_path / "no_pq.json",
        rf_dir=rf_dir,
        dry_run=True,
    )
    assert len(result.registered) == 1
    assert result.registered[0][0]["spec_ref"] == "ADOPT_TARGET_01"

    # Now try to ingest COLLIDER_001 via normal run_ingest (NOT adoption mode)
    # It should be deduped by oracle_compounds_registry canonical hash
    cand_collider = _build_candidate(
        source="oracle_brainstorm",
        candidate_type="oracle_compound",
        domain="oracle",
        hypothesis="collider hypothesis washout",
        mechanism="collider washout mechanism",
        spec_ref="COLLIDER_001",
        entry_rule=entry_rule,
    )
    cand_collider["artifacts"]["entry_rule"] = entry_rule

    dedup_result = run_ingest(
        [cand_collider],
        oracle_registry_path=oracle_reg,  # oracle registry has COLLIDER_001 entry_rule
        species_registry_path=tmp_path / "no_species.json",
        machine_registry_path=tmp_path / "no_machine.jsonl",
        trial_ledger_path=tmp_path / "no_ledger.jsonl",
        rf_dir=rf_dir,
        dry_run=True,
    )
    # Must be deduped (rule 1 not waived for COLLIDER_001)
    assert len(dedup_result.registered) == 0, (
        "COLLIDER_001 must be deduped via normal rule-1 (oracle canonical hash); "
        "the waiver only applies to the declared adoption target ADOPT_TARGET_01"
    )
    assert len(dedup_result.dropped) == 1
    _, rc, _ = dedup_result.dropped[0]
    assert rc == "deduped"


# ---------------------------------------------------------------------------
# 34. Reversion vs 63d trial_accounting modes
# ---------------------------------------------------------------------------


def test_adoption_trial_accounting_reversion_track(tmp_path):
    """A compound with reversion.gauntlet='PASS' gets mode='read_only'."""
    reversion_row = _make_oracle_registry_row("REV_COMPOUND", with_reversion_pass=True)
    assert _oracle_track_for_registry_row(reversion_row) == "reversion"
    ta = _trial_accounting_for_oracle_adoption("reversion")
    assert ta["mode"] == "read_only"
    assert ta["family"] is None


def test_adoption_trial_accounting_63d_track(tmp_path):
    """A compound WITHOUT reversion.gauntlet='PASS' gets mode='oracle_screen'."""
    non_rev_row = _make_oracle_registry_row("SIXTYTHREE_COMPOUND", with_reversion_pass=False)
    assert _oracle_track_for_registry_row(non_rev_row) == "63d"
    ta = _trial_accounting_for_oracle_adoption("63d")
    assert ta["mode"] == "oracle_screen"
    assert ta["family"] is None


def test_adoption_reversion_track_compound_end_to_end(tmp_path):
    """Full adoption of a reversion-track compound: trial_accounting.mode='read_only'."""
    oracle_reg = tmp_path / "registry.jsonl"
    reversion_row = _make_oracle_registry_row("REV_E2E", with_reversion_pass=True)
    _make_oracle_registry_jsonl(oracle_reg, [reversion_row])

    rf_dir = tmp_path / "rf"
    result = adopt_oracle_compounds(
        ["REV_E2E"],
        oracle_registry_path=oracle_reg,
        promotion_queue_path=tmp_path / "no_pq.json",
        rf_dir=rf_dir,
        dry_run=True,
    )
    assert len(result.registered) == 1
    cand_out, _ = result.registered[0]
    assert cand_out["trial_accounting"]["mode"] == "read_only"
    assert cand_out["artifacts"]["oracle_track"] == "reversion"


def test_adoption_63d_track_compound_end_to_end(tmp_path):
    """Full adoption of a 63d-track compound: trial_accounting.mode='oracle_screen'."""
    oracle_reg = tmp_path / "registry.jsonl"
    sixty3_row = _make_oracle_registry_row("SIXTYTHREE_E2E", with_reversion_pass=False)
    _make_oracle_registry_jsonl(oracle_reg, [sixty3_row])

    rf_dir = tmp_path / "rf"
    result = adopt_oracle_compounds(
        ["SIXTYTHREE_E2E"],
        oracle_registry_path=oracle_reg,
        promotion_queue_path=tmp_path / "no_pq.json",
        rf_dir=rf_dir,
        dry_run=True,
    )
    assert len(result.registered) == 1
    cand_out, _ = result.registered[0]
    assert cand_out["trial_accounting"]["mode"] == "oracle_screen"
    assert cand_out["artifacts"]["oracle_track"] == "63d"


# ---------------------------------------------------------------------------
# 35. domain_registry source is valid in schema
# ---------------------------------------------------------------------------


def test_domain_registry_source_is_valid_in_schema():
    """schema.SOURCES must include 'domain_registry' after the A2 amendment."""
    from engine.research_factory.schema import SOURCES
    assert "domain_registry" in SOURCES, (
        "'domain_registry' must be in SOURCES after A2 amendment"
    )
