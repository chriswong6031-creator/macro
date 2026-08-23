"""Propose/curate admission-script tests for the D5 program ontology.

Covers the curate-tier half of the freeze SS3.2 two-tier refusal semantics
(the loader-tier half lives in ``tests/test_government_program_ontology.py``),
plus T6's propose-script forbidden-provenance rejection and T17's curate
output-path/producer guard.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.government_revenue import program_ontology as po
from scripts import curate_government_program_ontology as curate_mod
from scripts import propose_government_program_ontology as propose_mod
from tests.fixtures.government_program_ontology import builders as b


# ---------------------------------------------------------------------------
# T6 -- propose script rejects forbidden provenance at the door
# ---------------------------------------------------------------------------


def test_t6_propose_rejects_forbidden_input_keys():
    raw_input = {
        "programs": [
            {
                **b.program_row(),
                "discovery_query_ticker": "AAA",
            }
        ]
    }
    proposal = propose_mod.propose_candidates(raw_input)
    assert proposal["candidates"]["programs"] == []
    assert len(proposal["rejection_ledger"]) == 1
    assert proposal["rejection_ledger"][0]["reason"] == "forbidden_provenance_key_present"


def test_t6_propose_rejects_forbidden_association_method():
    raw_input = {
        "role_assertions": [
            {**b.role_assertion_row(), "association_method": "llm_assertion"},
        ]
    }
    proposal = propose_mod.propose_candidates(raw_input)
    assert proposal["candidates"]["role_assertions"] == []
    assert proposal["rejection_ledger"][0]["reason"] == "forbidden_provenance_key_present"


def test_t6_propose_stamps_every_admitted_row_proposed():
    raw_input = {"programs": [b.program_row()]}
    proposal = propose_mod.propose_candidates(raw_input)
    assert proposal["candidates"]["programs"][0]["verification_state"] == po.PROPOSED_STATE


def test_t6_propose_never_writes_the_canonical_path(tmp_path):
    with pytest.raises(ValueError):
        propose_mod.guard_output_path(curate_mod.DEFAULT_TARGET)
    # A same-named file elsewhere is refused too (name equality, not only path identity).
    with pytest.raises(ValueError):
        propose_mod.guard_output_path(tmp_path / curate_mod.DEFAULT_TARGET.name)


# ---------------------------------------------------------------------------
# T17 -- curate is the ONLY producer of review_coverage rows
# ---------------------------------------------------------------------------


def test_t17_propose_refuses_to_emit_review_coverage():
    raw_input = {
        "review_coverage": [
            b.review_coverage_row(scope="program_identity", subject_type="program", subject_id="acq-program:x"),
        ]
    }
    with pytest.raises(propose_mod.ProposalAuthorityError):
        propose_mod.propose_candidates(raw_input)


def test_t17_curate_is_the_only_producer_of_coverage_rows(tmp_path):
    target = tmp_path / "program_ontology.json"
    prog = b.program_row()
    ev = b.evidence_row(
        "curate-coverage-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog["evidence_refs"] = [ev["evidence_id"]]
    graph = b.empty_graph()
    graph["evidence"] = [ev]

    worksheet_dict = b.worksheet(
        coverage=[{"scope": "program_identity", "subject_type": "program", "subject_id": prog["id"]}],
        rows=[{
            "action": "admit", "target_kind": "program", "candidate_row": prog,
            "identity_disposition": "new_identity",
        }],
    )
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")

    target.write_text(json.dumps(graph), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 1
    assert report["coverage_rows_minted"] == 1

    published = json.loads(target.read_text(encoding="utf-8"))
    assert len(published["review_coverage"]) == 1
    assert published["review_coverage"][0]["scope"] == "program_identity"
    assert published["review_coverage"][0]["subject_id"] == prog["id"]
    assert published["review_coverage"][0]["admitted_count"] == 1


# ---------------------------------------------------------------------------
# Curate-tier refusals mirroring the loader-tier T-tests
# ---------------------------------------------------------------------------


def _fresh_target(tmp_path: Path) -> Path:
    target = tmp_path / "program_ontology.json"
    target.write_text(json.dumps(b.empty_graph()), encoding="utf-8")
    return target


def test_t6_curate_refuses_forbidden_provenance_row(tmp_path):
    target = _fresh_target(tmp_path)
    prog = b.program_row()
    prog["discovery_query_ticker"] = "AAA"
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "program", "candidate_row": prog,
        "identity_disposition": "new_identity",
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "forbidden_provenance_key_present"


def test_t2c_curate_refuses_rename_smuggled_as_new_identity(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "rename-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    existing = b.program_row(id_="acq-program:x", revision=1, evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [existing]
    target.write_text(json.dumps(graph), encoding="utf-8")

    renamed = b.program_row(
        id_="acq-program:x", revision=1, name="Smuggled Rename", evidence_refs=[ev["evidence_id"]],
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "program", "candidate_row": renamed,
        "identity_disposition": "new_identity",
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "worksheet_inconsistent"


def test_t2c_curate_refuses_same_object_revision_row_missing_from_artifact(tmp_path):
    target = _fresh_target(tmp_path)
    ev = b.evidence_row(
        "same-object-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph = json.loads(target.read_text(encoding="utf-8"))
    graph["evidence"] = [ev]
    target.write_text(json.dumps(graph), encoding="utf-8")

    row = b.program_row(id_="acq-program:absent", evidence_refs=[ev["evidence_id"]])
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "program", "candidate_row": row,
        "identity_disposition": "same_object_revision",
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "rename_as_new_identity"


def test_t11_curate_refuses_dual_scope_predicate_mismatch(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev_identity = b.evidence_row(
        "t11curate-identity", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    ev_role = b.evidence_row(
        "t11curate-role", claim_scopes=["role"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev_identity["evidence_id"]])
    graph["evidence"] = [ev_identity, ev_role]
    graph["programs"] = [prog]
    target.write_text(json.dumps(graph), encoding="utf-8")

    # Two DISTINCT refs independently supply the two scopes -> the predicate
    # computes False; a worksheet claiming True is refused at curate.
    role = b.role_assertion_row(
        program_id=prog["id"], single_document_dual_scope=True,
        evidence_refs=[ev_identity["evidence_id"], ev_role["evidence_id"]],
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "role_assertion", "candidate_row": role,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "dual_scope_predicate_mismatch"


def test_t11_curate_requires_scope_statement_for_true_single_ref_dual_scope(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t11curate-dual", claim_scopes=["program_identity", "role"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    target.write_text(json.dumps(graph), encoding="utf-8")

    role = b.role_assertion_row(
        program_id=prog["id"], single_document_dual_scope=True, evidence_refs=[ev["evidence_id"]],
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "role_assertion", "candidate_row": role,
        # scope_statement deliberately omitted
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "missing_scope_statement"

    worksheet_dict["rows"][0]["scope_statement"] = "The document names both facts in one sentence."
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report2 = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report2["admitted_count"] == 1


# ---------------------------------------------------------------------------
# T15 -- event link is exact-identity or nothing (curate-time verification)
# ---------------------------------------------------------------------------


def _live_workspace_event(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "award_change": {
            "generated_award_id": "CONT_AWD_EXAMPLE",
            "award_key": None,
            "piid": None,
            "source_identity": {"id": "action:live-example", "version": "v1", "content_sha256": "e" * 64},
        },
    }


def test_t15a_curate_refuses_event_not_found(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t15a-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    target.write_text(json.dumps(graph), encoding="utf-8")

    link = b.program_event_link_row(
        program_id=prog["id"], event_id="govws-does-not-exist", evidence_refs=[ev["evidence_id"]],
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "program_event_link", "candidate_row": link,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target, workspace_events={})
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "event_not_found"


def test_t15b_curate_refuses_event_identity_mismatch(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t15b-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    target.write_text(json.dumps(graph), encoding="utf-8")

    live_event = _live_workspace_event("govws-live-example")
    link = b.program_event_link_row(
        program_id=prog["id"], event_id="govws-live-example", evidence_refs=[ev["evidence_id"]],
        event_source_identity_id="action:WRONG",  # disagrees with the live event
        event_source_identity_content_sha256="e" * 64,
        canonical_award_identity="generated:CONT_AWD_EXAMPLE",
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "program_event_link", "candidate_row": link,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(
        worksheet_path, target_path=target, workspace_events={"govws-live-example": live_event},
    )
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "event_identity_mismatch"


def test_t15_curate_admits_a_matching_event_link(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t15good-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    target.write_text(json.dumps(graph), encoding="utf-8")

    live_event = _live_workspace_event("govws-live-good")
    link = b.program_event_link_row(
        program_id=prog["id"], event_id="govws-live-good", evidence_refs=[ev["evidence_id"]],
        event_source_identity_id="action:live-example",
        event_source_identity_content_sha256="e" * 64,
        canonical_award_identity="generated:CONT_AWD_EXAMPLE",
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "program_event_link", "candidate_row": link,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(
        worksheet_path, target_path=target, workspace_events={"govws-live-good": live_event},
    )
    assert report["admitted_count"] == 1


# ---------------------------------------------------------------------------
# Orphan capability + rejection ledger + reject-action rows
# ---------------------------------------------------------------------------


def test_orphan_capability_refused_without_a_citing_link_in_the_same_act(tmp_path):
    target = _fresh_target(tmp_path)
    ev = b.evidence_row(
        "orphan-cap-doc", claim_scopes=["capability_need"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph = json.loads(target.read_text(encoding="utf-8"))
    graph["evidence"] = [ev]
    target.write_text(json.dumps(graph), encoding="utf-8")

    cap = b.capability_row(evidence_refs=[ev["evidence_id"]])
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "capability", "candidate_row": cap,
        "identity_disposition": "new_identity",
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "orphan_capability"


def test_reject_action_rows_recorded_in_ledger_without_being_admitted(tmp_path):
    target = _fresh_target(tmp_path)
    worksheet_dict = b.worksheet(rows=[{
        "action": "reject", "target_kind": "program",
        "candidate_row": b.program_row(),
        "rejection_reason": "search-synthesis evidence, not admissible",
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["admitted_count"] == 0
    assert report["rejected_count"] == 1
    published = json.loads(target.read_text(encoding="utf-8"))
    assert published["programs"] == []
