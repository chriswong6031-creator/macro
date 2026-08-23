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
# Worksheet evidence admission (freeze SS3.1a) -- append-only-with-widening,
# processed FIRST in the curate act so a same-act role/link/milestone sees
# the evidence's post-update claim_scopes (2026-08-23 orchestrator defect
# repair, verified against research/government_revenue/
# PROGRAM_ONTOLOGY_REVIEW_2026-08-23_virginia_pilot.json).
# ---------------------------------------------------------------------------


def test_curate_admits_a_new_evidence_row(tmp_path):
    target = _fresh_target(tmp_path)
    ev = b.evidence_row(
        "new-evidence-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "evidence", "candidate_row": ev,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["evidence_admitted_count"] == 1
    assert report["admitted_count"] == 1
    published = json.loads(target.read_text(encoding="utf-8"))
    assert published["evidence"] == [ev]


def test_curate_widens_an_existing_evidence_rows_claim_scopes(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "widen-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [ev]
    target.write_text(json.dumps(graph), encoding="utf-8")

    widened_candidate = {**ev, "claim_scopes": sorted({"program_identity", "role"})}
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "evidence", "candidate_row": widened_candidate,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["evidence_admitted_count"] == 1
    published = json.loads(target.read_text(encoding="utf-8"))
    assert len(published["evidence"]) == 1
    row = published["evidence"][0]
    assert sorted(row["claim_scopes"]) == sorted({"program_identity", "role"})
    # First receipt wins: every OTHER field stays byte-identical to the
    # original stored row (retrieved_at/known_at never move on a widening).
    assert row["known_at"] == ev["known_at"]
    assert row["retrieved_at"] == ev["retrieved_at"]
    assert row["sha256"] == ev["sha256"]


def test_curate_refuses_evidence_receipt_mismatch_on_a_non_scope_field_change(tmp_path):
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    ev = b.evidence_row(
        "mismatch-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [ev]
    target.write_text(json.dumps(graph), encoding="utf-8")

    mismatched = {**ev, "source_url": "https://www.defense.gov/a-different-page/"}
    worksheet_dict = b.worksheet(rows=[{
        "action": "admit", "target_kind": "evidence", "candidate_row": mismatched,
    }])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["evidence_admitted_count"] == 0
    assert report["rejected"][0]["reason"] == "evidence_receipt_mismatch"
    # The stored row is untouched by the refused candidate.
    published = json.loads(target.read_text(encoding="utf-8"))
    assert published["evidence"] == [ev]


def test_curate_evidence_admitted_in_the_same_act_is_visible_to_a_dependent_role(tmp_path):
    """The freeze SS3.1 ordering property: 'within one curate act, evidence-row
    updates ... apply FIRST and row admissions are then predicated on the
    post-update scopes.' A role_assertion admitted in the SAME act as the
    evidence that supplies its program_identity+role coverage must see that
    evidence -- not be refused claim_scope_coverage_missing/dual-scope for a
    dependency that exists only earlier in this same worksheet."""
    target = tmp_path / "program_ontology.json"
    graph = b.empty_graph()
    prog_ev = b.evidence_row(
        "same-act-prog-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [prog_ev]
    prog = b.program_row(evidence_refs=[prog_ev["evidence_id"]])
    graph["programs"] = [prog]
    target.write_text(json.dumps(graph), encoding="utf-8")

    dual_ev = b.evidence_row(
        "same-act-dual-doc", claim_scopes=["program_identity", "role"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    role = b.role_assertion_row(
        program_id=prog["id"], single_document_dual_scope=True, evidence_refs=[dual_ev["evidence_id"]],
    )
    worksheet_dict = b.worksheet(rows=[
        {"action": "admit", "target_kind": "evidence", "candidate_row": dual_ev},
        {
            "action": "admit", "target_kind": "role_assertion", "candidate_row": role,
            "scope_statement": "The document names both facts in one sentence.",
        },
    ])
    worksheet_path = tmp_path / "worksheet.json"
    worksheet_path.write_text(json.dumps(worksheet_dict), encoding="utf-8")
    report = curate_mod.curate_worksheet(worksheet_path, target_path=target)
    assert report["evidence_admitted_count"] == 1
    assert report["admitted_count"] == 2
    assert report["rejected_count"] == 0
    published = json.loads(target.read_text(encoding="utf-8"))
    assert any(r["id"] == role["id"] for r in published["role_assertions"])


def test_curate_pilot_worksheet_matches_the_ratified_acceptance_check(tmp_path):
    """End-to-end regression pinning the 2026-08-23 orchestrator adjudication:
    the real Virginia-class SSN pilot worksheet must admit 14, reject exactly
    the one deliberate program_event_link reject row, and mint 6 coverage
    rows -- never weakening any freeze law to get there."""
    repo_root = Path(__file__).parents[1]
    worksheet_path = repo_root / "research" / "government_revenue" / "PROGRAM_ONTOLOGY_REVIEW_2026-08-23_virginia_pilot.json"
    if not worksheet_path.exists():
        pytest.skip("pilot worksheet not present in this checkout")
    workspace_path = repo_root / "data" / "government_revenue" / "workspace.json"
    workspace_events: dict[str, dict] = {}
    if workspace_path.exists():
        workspace_data = json.loads(workspace_path.read_text(encoding="utf-8"))
        for event in workspace_data.get("events", []):
            if isinstance(event, dict) and event.get("event_id"):
                workspace_events[event["event_id"]] = event

    report = curate_mod.curate_worksheet(
        worksheet_path,
        target_path=tmp_path / "program_ontology.json",
        graph_id="program-ontology:reviewed:2026-08-23:virginia-pilot",
        graph_known_at="2026-08-23T07:50:00+00:00",
        graph_effective_at="2026-08-23T07:50:00+00:00",
        workspace_events=workspace_events,
        check_only=True,
    )
    assert report["admitted_count"] == 14
    assert report["rejected_count"] == 1
    assert report["coverage_rows_minted"] == 6
    assert report["rejected"][0]["row"]["action"] == "reject"
    assert report["rejected"][0]["row"]["target_kind"] == "program_event_link"


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
