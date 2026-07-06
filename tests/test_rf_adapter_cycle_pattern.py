"""tests/test_rf_adapter_cycle_pattern.py — CPI (cycle_pattern) domain adapter (P2).

Coverage:
  1. route_all absent-safe: [] when pattern_candidates.jsonl is missing.
  2. Status projection: candidate/registered/screened/numeric_rejected map
     correctly; unknown falls back to proposed.
  3. Synthetic candidates file routes with correct state projection AND the
     routed states replay through state.transition WITHOUT IllegalTransition.
  4. numeric_rejected route carries kill_evidence sourced from the kill block.
  5. trial_accounting mode='rf_family', family='rf.cycle_pattern.<trial_family>'.
  6. Artifact evidence dict pass-through.
  7. truth_guard flags a candidate colliding with the CPI-001 position->return
     promoted_null; flag-only (candidate not mutated, no reject).
  8. truth_guard does NOT flag a non-colliding candidate.
  9. Schema pins: cycle_pattern in DOMAINS, cycle_pattern_scan in SOURCES,
     cycle_pattern_rule in CANDIDATE_TYPES; a full candidate row validates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory import adapter_cycle_pattern as adp
from engine.research_factory import state as rf_state
from engine.research_factory.schema import (
    CANDIDATE_TYPES,
    DOMAINS,
    SOURCES,
    validate_candidate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_candidates(data_dir: Path, rows: list[dict]) -> Path:
    cp = data_dir / "cycle_pattern"
    cp.mkdir(parents=True, exist_ok=True)
    path = cp / "pattern_candidates.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def _candidate(**kw) -> dict:
    row = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "domain": "cycle_pattern",
        "source": "cycle_pattern_scan",
        "candidate_type": "cycle_pattern_rule",
        "candidate_id": "rf-20260706-cycle_pattern-001",
        "created_at": "2026-07-06T00:00:00Z",
        "status": "candidate",
        "hypothesis": "A falsifiable cycle-pattern hypothesis.",
        "mechanism": "Why the cell might persist out of sample.",
        "statement": "Phase persistence in fresh up-legs.",
        "target": "P(current phase survives 3m)",
        "scope": {"families": ["us_sector"], "regions": ["US"], "sample": "monthly"},
        "trial_family": "phase_persistence",
        "artifacts": {},
    }
    row.update(kw)
    return row


# ===========================================================================
# 1. Absent-safe
# ===========================================================================

def test_route_all_absent_safe(tmp_path):
    """No pattern_candidates.jsonl → [] (never raises)."""
    assert adp.route_all(data_dir=tmp_path) == []
    # default (cwd/data) path also must not raise even if absent
    # (load_candidates is absent-file-safe)
    assert isinstance(adp.load_candidates(tmp_path), list)


# ===========================================================================
# 2. Status projection (exhaustive + fallback)
# ===========================================================================

@pytest.mark.parametrize("status,expected", [
    ("candidate", "proposed"),
    ("registered", "registered"),
    ("screened", "screened"),
    ("numeric_rejected", "numeric_rejected"),
    ("something_unknown", "proposed"),
])
def test_status_projection(status, expected):
    assert adp.project_cycle_pattern_status(status) == expected


# ===========================================================================
# 3. Synthetic file routes + state.transition replay (no IllegalTransition)
# ===========================================================================

def test_route_all_projection_and_transition_replay(tmp_path):
    _write_candidates(tmp_path, [
        _candidate(candidate_id="c-cand", status="candidate"),
        _candidate(candidate_id="c-reg", status="registered"),
        _candidate(candidate_id="c-scr", status="screened"),
    ])
    routed = adp.route_all(data_dir=tmp_path)
    by_id = {r["candidate_id"]: r for r in routed}
    assert by_id["c-cand"]["projected_state"] == "proposed"
    assert by_id["c-reg"]["projected_state"] == "registered"
    assert by_id["c-scr"]["projected_state"] == "screened"

    # Replay proposed→registered→screened through the real state machine.
    # Declare the trial family in a temp ledger so the RF-6 screened gate passes.
    family = by_id["c-scr"]["trial_accounting"]["family"]
    assert family == "rf.cycle_pattern.phase_persistence"
    ledger = tmp_path / "trial_ledger.jsonl"
    ledger.write_text(
        json.dumps({"family": family, "kind": "declared_budget"}) + "\n",
        encoding="utf-8",
    )

    cand_ctx = {"trial_accounting": {"mode": "rf_family", "family": family},
                "transition_log": []}

    # proposed → registered (script actor, mechanical)
    rf_state.transition(
        "proposed", "registered", "sonnet",
        {"schema": "research_factory.transition.v1", "authority": "display_only",
         "as_of": "2026-07-06T00:00:00Z"},
        candidate=cand_ctx, ledger_path=ledger,
    )
    # registered → screened (needs artifact_refs + declared family)
    rf_state.transition(
        "registered", "screened", "sonnet",
        {"schema": "research_factory.transition.v1", "authority": "display_only",
         "as_of": "2026-07-06T00:00:01Z",
         "artifact_refs": ["data/cycle_pattern/pattern_candidates.jsonl"]},
        candidate=cand_ctx, ledger_path=ledger,
    )
    # If either were illegal, IllegalTransition would have raised above.


# ===========================================================================
# 4. Kill evidence on numeric_rejected (RF-10)
# ===========================================================================

def test_numeric_rejected_carries_kill_evidence(tmp_path):
    _write_candidates(tmp_path, [
        _candidate(
            candidate_id="c-rej",
            status="numeric_rejected",
            kill={"n_at_kill": 42, "kill_class": "underpowered_accruing",
                  "gate_ref": "data/cycle_pattern/foo_gate.json"},
        ),
    ])
    routed = adp.route_all(data_dir=tmp_path)
    r = routed[0]
    assert r["projected_state"] == "numeric_rejected"
    assert r["kill_evidence"] is not None
    assert r["kill_evidence"]["n_at_kill"] == 42
    assert r["kill_evidence"]["kill_class"] == "underpowered_accruing"
    assert r["kill_evidence"]["gate_ref"] == "data/cycle_pattern/foo_gate.json"
    assert r["kill_evidence"]["source"] == "cycle_pattern_candidate_kill_block"


def test_non_rejected_has_no_kill_evidence(tmp_path):
    _write_candidates(tmp_path, [_candidate(status="candidate")])
    assert adp.route_all(data_dir=tmp_path)[0]["kill_evidence"] is None


# ===========================================================================
# 5. Trial accounting rf_family + family name
# ===========================================================================

def test_trial_accounting_rf_family(tmp_path):
    _write_candidates(tmp_path, [_candidate(trial_family="breadth_ft")])
    r = adp.route_all(data_dir=tmp_path)[0]
    assert r["trial_accounting"]["mode"] == "rf_family"
    assert r["trial_accounting"]["family"] == "rf.cycle_pattern.breadth_ft"
    assert r["trial_accounting"]["declared_at"] is None


def test_missing_trial_family_leaves_family_none(tmp_path):
    row = _candidate()
    row.pop("trial_family")
    _write_candidates(tmp_path, [row])
    r = adp.route_all(data_dir=tmp_path)[0]
    assert r["trial_accounting"]["family"] is None


# ===========================================================================
# 6. Artifact evidence pass-through
# ===========================================================================

def test_artifact_passthrough(tmp_path):
    ev = {"n_eff": 51, "delta_brier_ci": [-0.01, 0.03], "gate": "TR-1"}
    _write_candidates(tmp_path, [_candidate(artifacts=ev)])
    r = adp.route_all(data_dir=tmp_path)[0]
    assert r["artifact"] == ev


# ===========================================================================
# 7 & 8. truth_guard collision (flag-only) / non-collision
# ===========================================================================

def test_truth_guard_flags_promoted_null_collision():
    """A candidate colliding with the CPI-001 position->return promoted_null
    is flagged (flag-only; candidate untouched)."""
    # CPI-001 (promoted_null): target = "forward_ret at 21/63/126d conditioned
    # on position decile", families = ['us_sector', 'country'].
    colliding = _candidate(
        candidate_id="c-collide",
        target="forward_ret at 21/63/126d conditioned on position decile",
        scope={"families": ["us_sector"], "regions": ["US"], "sample": "monthly"},
    )
    non_colliding = _candidate(
        candidate_id="c-clean",
        target="P(current phase survives 3m)",
        scope={"families": ["us_sector"], "regions": ["US"], "sample": "monthly"},
    )
    flags = adp.truth_guard([colliding, non_colliding])
    flagged_ids = {f["candidate_id"] for f in flags}
    assert "c-collide" in flagged_ids
    assert "c-clean" not in flagged_ids
    flag = next(f for f in flags if f["candidate_id"] == "c-collide")
    assert flag["flag"] == "promoted_null_collision"
    assert flag["colliding_truth_id"] == "CPI-001"
    assert flag["shared_families"] == ["us_sector"]
    # flag-only: original candidate dict was not mutated / rejected
    assert colliding["status"] == "candidate"


def test_truth_guard_no_collision_when_families_disjoint():
    """Same target but disjoint families → NOT flagged (collision needs both)."""
    cand = _candidate(
        candidate_id="c-disjoint",
        target="forward_ret at 21/63/126d conditioned on position decile",
        scope={"families": ["cn_sector"], "regions": ["CN"], "sample": "monthly"},
    )
    assert adp.truth_guard([cand]) == []


# ===========================================================================
# 9. Schema pins
# ===========================================================================

def test_schema_pins_additive():
    assert "cycle_pattern" in DOMAINS
    assert "cycle_pattern_scan" in SOURCES
    assert "cycle_pattern_rule" in CANDIDATE_TYPES


def test_projected_factory_candidate_row_validates_clean():
    """A factory candidate.v1 row for the cycle_pattern domain validates clean
    once the CPI domain status is PROJECTED to a factory state (RF-2).

    The CPI file's own 'status' vocabulary (candidate/registered/...) is NOT a
    factory STATES value; the ingest writes the projected state into the factory
    row.  This test proves the new DOMAINS/SOURCES/CANDIDATE_TYPES values pass
    the factory validator with a legal projected status.
    """
    cpi_row = _candidate(status="candidate")
    factory_row = _candidate(
        status=adp.project_cycle_pattern_status(cpi_row["status"]),  # -> 'proposed'
        claim_shape=None,
        trial_accounting={"mode": "rf_family",
                          "family": "rf.cycle_pattern.phase_persistence",
                          "declared_at": None},
        lineage={"respin_of": None, "superseded_by": None,
                 "refinement_generation": 0},
    )
    assert factory_row["status"] == "proposed"
    errs = validate_candidate(factory_row)
    assert errs == [], errs
