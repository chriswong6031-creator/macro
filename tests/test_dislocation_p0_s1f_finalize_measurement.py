from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.research.dislocation_p0_a1_lib import canonical_json
from scripts.research.dislocation_p0_a1r_semantic_contract import RELATIONSHIPS
from scripts.research.dislocation_p0_s1f_finalize_measurement import (
    AUTHORITY,
    FinalMeasurementBlocked,
    build_rows,
    run,
)
from scripts.research.dislocation_p0_s1f_measurement import measure
from scripts.research.dislocation_p0_s1f_model_transport import (
    AUDIT_INPUT_SCHEMA,
    AUDIT_RESULT_SCHEMA,
    AUDIT_SCHEMA,
    AUDITOR_MODEL,
    AUDITOR_PROVIDER,
    AUDITOR_ROLE,
    GROK_INPUT_SCHEMA,
    GROK_RESULT_SCHEMA,
    PROPOSAL_SCHEMA,
    RELATION_SCHEMA,
    finalize_all70,
    logical_sha,
)
from scripts.research.dislocation_p0_s1f_selection import STRATA


REPO_ROOT = Path(__file__).resolve().parents[1]
S1F_ARTIFACT_ROOT = REPO_ROOT / "research" / "dislocation_intelligence" / "p0_s1f"


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> dict[str, object]:
    # The established transport test factories provide source-only, span-valid
    # packets/proposals/audits; this fixture adds only final-measurement bindings.
    from tests import test_dislocation_p0_s1f_model_transport as transport

    packets = transport._packets()
    source_root = tmp_path / "sources"
    index_rows = []
    for packet in packets:
        doc = packet["documents"][0]
        source = packet["source_documents"][doc["document_sha256"]]
        rel = doc["source_path"]
        (source_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (source_root / rel).write_bytes(source)
        index_rows.append({
            "slot": packet["slot"], "packet_id": packet["packet_id"], "cik": packet["cik"],
            "accession": packet["accession"], "accepted_at": packet["accepted_at"], "filed_on": packet["filed_on"],
            "documents": [dict(doc)], "primary_context": dict(doc), "primary_document_substitution": False,
        })
    index = _write(tmp_path / "packet_index.json", {"schema": "mastermind.dislocation_p0.s1f_model_packet_index.v1", "packets": index_rows})

    canonical = transport._source_manifest(packets)
    canonical["authority"] = AUTHORITY
    selected = []
    for index_number, row in enumerate(canonical["packets"]):
        stratum = STRATA[index_number // 10]
        row["retrieval_stratum"] = stratum
        selected.append({
            "cik": row["issuer"]["cik"], "accession": row["filing"]["accession"], "stratum": stratum,
            "era": "modern" if index_number % 10 < 7 else "development",
            "base_form": "8-K" if index_number % 10 < 7 else "6-K", "selection_key": row["selection_key"],
        })
    selection = {"schema": "mastermind.dislocation_p0.s1f_exact70_source_manifest.v1", "authority": AUTHORITY, "n": 70, "candidates": selected}
    selection["manifest_sha256"] = logical_sha(selection)
    selection_path = _write(tmp_path / "selection.json", selection)
    canonical["selection_manifest_sha256"] = selection["manifest_sha256"]
    canonical.pop("manifest_sha256")
    canonical["manifest_sha256"] = logical_sha(canonical)
    canonical_path = _write(tmp_path / "canonical.json", canonical)
    owner_replay = {
        "schema": "mastermind.dislocation_p0.s1f_canonical_owner_replay_proof.v1",
        "status": "COMPLETE_BYTE_IDENTICAL",
        "packet_count": 70,
        "document_count": 70,
        "frozen_manifest_sha256": canonical["manifest_sha256"],
        "replayed_manifest_sha256": canonical["manifest_sha256"],
        "network_access": "NONE",
        "official_sec_hosts": ["data.sec.gov", "www.sec.gov"],
        "forbidden_dirs_present": [],
    }
    owner_replay_path = _write(tmp_path / "owner_replay.json", owner_replay)
    selection_receipt = {"schema": "mastermind.dislocation_p0.s1f_exact70_selection_receipt.v1", "status": "COMPLETE", "authority": AUTHORITY, "selection_manifest_sha256": selection["manifest_sha256"]}
    selection_receipt["receipt_sha256"] = logical_sha(selection_receipt)
    selection_receipt_path = _write(tmp_path / "selection_receipt.json", selection_receipt)
    ruleset = {
        "schema": "mastermind.dislocation_p0.s1f_triage_ruleset.v1",
        "version": "fixture",
        "authority": AUTHORITY,
        "rules": [],
    }
    ruleset_path = _write(tmp_path / "triage_ruleset.json", ruleset)
    triage_rows = [{"packet_id": packet["packet_id"], "shadow_disposition": "RETAIN", "rule_ids": ["S1F-REALIZED-CURRENT-CONTEXT"]} for packet in packets]
    triage = {"schema": "mastermind.dislocation_p0.s1f_frozen_shadow_triage.v1", "status": "COMPLETE_BYTE_IDENTICAL_SOURCE_ONLY", "authority": AUTHORITY, "packet_count": 70, "canonical_source_manifest_sha256": canonical["manifest_sha256"], "exact70_selection_manifest_sha256": selection["manifest_sha256"], "exact70_selection_receipt_sha256": selection_receipt["receipt_sha256"], "triage_ruleset_sha256": logical_sha(ruleset), "triage": triage_rows}
    triage["shadow_triage_sha256"] = logical_sha(triage)
    triage_path = _write(tmp_path / "triage.json", triage)

    proposals = transport._proposals(packets)
    audits = transport._audits(packets)
    edge = transport._episode(packets[0], audits[0])
    batch_values = []
    for schema, prefix in ((GROK_INPUT_SCHEMA, "grok_input"), (GROK_RESULT_SCHEMA, "grok_result"), (AUDIT_INPUT_SCHEMA, "audit_input"), (AUDIT_RESULT_SCHEMA, "audit_result")):
        batch_values.append([_write(tmp_path / f"{prefix}_{number}.json", {"schema": schema, "batch_number": number, "batch_id": f"B{number}", "input_bundle_sha256": ""}) for number in range(1, 8)])
    for input_paths, result_paths in ((batch_values[0], batch_values[1]), (batch_values[2], batch_values[3])):
        for input_path, result_path in zip(input_paths, result_paths):
            result = json.loads(result_path.read_text())
            result["input_bundle_sha256"] = __import__("hashlib").sha256(input_path.read_bytes()).hexdigest()
            _write(result_path, result)
    proposal = {"schema": PROPOSAL_SCHEMA, "source_manifest_sha256": canonical["manifest_sha256"], "batch_plan_sha256": "b" * 64, "proposal_count": 70, "relationship_hypotheses": [], "proposals": proposals, "batch_result_logical_sha256s": [logical_sha(json.loads(path.read_text())) for path in batch_values[1]]}
    proposal_path = _write(tmp_path / "proposal.json", proposal)
    audit = {"schema": AUDIT_SCHEMA, "source_manifest_sha256": canonical["manifest_sha256"], "batch_plan_sha256": "b" * 64, "proposal_bundle_sha256": "", "audit_count": 70, "audits": audits, "batch_result_logical_sha256s": [logical_sha(json.loads(path.read_text())) for path in batch_values[3]]}
    audit["proposal_bundle_sha256"] = __import__("hashlib").sha256(proposal_path.read_bytes()).hexdigest()
    audit_path = _write(tmp_path / "audit.json", audit)
    proposal_sha, audit_sha = __import__("hashlib").sha256(proposal_path.read_bytes()).hexdigest(), __import__("hashlib").sha256(audit_path.read_bytes()).hexdigest()
    reconciliation = {"schema": RELATION_SCHEMA, "source_manifest_sha256": canonical["manifest_sha256"], "batch_plan_sha256": "b" * 64, "proposal_bundle_sha256": proposal_sha, "audit_bundle_sha256": audit_sha, "reconciler": {"provider": AUDITOR_PROVIDER, "model": AUDITOR_MODEL, "role": AUDITOR_ROLE, "independent_source_only": True}, "reviewed_packet_ids": [packet["packet_id"] for packet in packets], "all70_complete": True, "unresolved_count": 0, "resolution_matrix": [{"packet_id": packet["packet_id"], "resolution": "RESOLVED"} for packet in packets], "final_relationship_assessments": [{"packet_id": packet["packet_id"], "relationship_assessment": deepcopy(audit_row["relationship_assessment"])} for packet, audit_row in zip(packets, audits)], "relationships": [edge]}
    reconciliation_path = _write(tmp_path / "reconciliation.json", reconciliation)
    summary, matrix = finalize_all70(packets=packets, proposal_bundle=proposal, audit_bundle=audit, reconciliation=reconciliation, proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha)
    linkage = {"schema": "mastermind.dislocation_p0.s1f_episode_linkage.v1", "source_manifest_sha256": canonical["manifest_sha256"], "proposal_bundle_sha256": proposal_sha, "audit_bundle_sha256": audit_sha, "relationship_reconciliation_file_sha256": __import__("hashlib").sha256(reconciliation_path.read_bytes()).hexdigest(), "economic_episode_count": 1, "episode_ids": ["episode-one"], "relationships": [edge], "final_relationship_assessments": reconciliation["final_relationship_assessments"]}
    linkage_path = _write(tmp_path / "linkage.json", linkage)
    matrix_path = _write(tmp_path / "matrix.json", matrix)
    semantic = {"status": "EXACT70_SOURCE_ONLY_SEMANTIC_AUDIT_LINKAGE_COMPLETE", "source_manifest_sha256": canonical["manifest_sha256"], "grok_proposal_bundle_file_sha256": proposal_sha, "independent_audit_bundle_file_sha256": audit_sha, "relationship_reconciliation_file_sha256": __import__("hashlib").sha256(reconciliation_path.read_bytes()).hexdigest(), "episode_linkage_file_sha256": __import__("hashlib").sha256(linkage_path.read_bytes()).hexdigest(), "disagreement_matrix_file_sha256": __import__("hashlib").sha256(matrix_path.read_bytes()).hexdigest(), "summary": summary}
    semantic_path = _write(tmp_path / "semantic.json", semantic)
    audit_access = {
        "schema": "mastermind.dislocation_p0.s1f_warp_grok46_audit_access_receipt.v1",
        "status": "COMPLETE_SOURCE_ONLY_WARP_GROK46",
        "source_manifest_sha256": canonical["manifest_sha256"],
        "batch_plan_sha256": "b" * 64,
        "proposal_bundle_file_sha256": proposal_sha,
        "independent_audit_bundle_file_sha256": audit_sha,
        "relationship_reconciliation_file_sha256": __import__("hashlib").sha256(reconciliation_path.read_bytes()).hexdigest(),
        "transport": {
            "application": "Warp", "claude_web_used": False, "client": "Oz",
            "declared_model": "Grok 4.6", "execution_location": "LOCAL",
            "github_connection_used": False, "provider": "xAI",
            "repository_read_scope": "COMMISSION_AND_DECLARED_SOURCE_ONLY_INPUT",
            "runtime_model_id": "grok-4-6-high",
        },
        "audit_summary": {"packet_count": 70, "unresolved_disagreements": 0},
        "all70_reconciliation": {"reviewed_packet_count": 70, "unresolved_count": 0},
        "authority": AUTHORITY,
        "stop_before": "P0-S2",
    }
    audit_access_path = _write(tmp_path / "audit_access.json", audit_access)
    return {"packet_index": index, "source_root": source_root, "canonical_manifest": canonical_path, "owner_replay_proof": owner_replay_path, "selection_manifest": selection_path, "selection_receipt": selection_receipt_path, "triage_ruleset": ruleset_path, "shadow_triage": triage_path, "proposal": proposal_path, "audit": audit_path, "reconciliation": reconciliation_path, "episode_linkage": linkage_path, "disagreement_matrix": matrix_path, "semantic_receipt": semantic_path, "audit_access_receipt": audit_access_path, "grok_inputs": batch_values[0], "grok_results": batch_values[1], "audit_inputs": batch_values[2], "audit_results": batch_values[3], "out_dir": tmp_path / "out"}


def test_final_measurement_emits_hash_bound_source_only_evidence(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = run(**paths)
    measurement = json.loads(result["measurement"].read_text())
    receipt = json.loads(result["receipt"].read_text())
    bundle = json.loads(result["bundle"].read_text())
    k_packet = json.loads(result["k_packet"].read_text())
    assert measurement["authority"] == AUTHORITY
    assert measurement["network"] == "NONE" and measurement["stop_before"] == "P0-S2"
    assert len(measurement["rows"]) == 70
    assert measurement["report"]["overall_origin_yield"]["successes"] == 1
    assert receipt["measurement_file_sha256"] == __import__("hashlib").sha256(result["measurement"].read_bytes()).hexdigest()
    assert len(bundle["batch_artifacts"]["grok_result_file_sha256s"]) == 7
    assert len(bundle["batch_artifacts"]["independent_audit_result_file_sha256s"]) == 7
    assert k_packet["triage_contract_sha256"] == logical_sha(json.loads(paths["triage_ruleset"].read_text()))
    assert k_packet["independent_audit_bundle_file_sha256"] == __import__("hashlib").sha256(paths["audit"].read_bytes()).hexdigest()
    assert k_packet["auditor_runtime_access_receipt_file_sha256"] == __import__("hashlib").sha256(
        paths["audit_access_receipt"].read_bytes()
    ).hexdigest()
    assert bundle["artifacts"]["auditor_runtime_access_receipt_file_sha256"] == (
        k_packet["auditor_runtime_access_receipt_file_sha256"]
    )
    assert bundle["published_artifact_paths"]["k_packet"].endswith("/S1F_K_PACKET.json")
    assert k_packet["honest_feasibility"] == measurement["report"]


def test_final_measurement_rejects_forbidden_field_before_emission(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    proposal = json.loads(paths["proposal"].read_text())
    proposal["proposals"][0]["semantic"]["market_data"] = {"state": "UNKNOWN"}
    _write(paths["proposal"], proposal)
    with pytest.raises(FinalMeasurementBlocked, match="FORBIDDEN_MARKET_OUTCOME_FIELD"):
        run(**paths)


def test_final_measurement_rejects_wrong_or_forbidden_auditor_runtime_receipt(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    access = json.loads(paths["audit_access_receipt"].read_text())
    access["transport"]["claude_web_used"] = True
    _write(paths["audit_access_receipt"], access)
    with pytest.raises(FinalMeasurementBlocked, match="AUDIT_ACCESS_RECEIPT_INVALID"):
        run(**paths)

    paths = _fixture(tmp_path / "forbidden")
    access = json.loads(paths["audit_access_receipt"].read_text())
    access["access_boundary"] = {"market_data_access": "NONE"}
    _write(paths["audit_access_receipt"], access)
    with pytest.raises(FinalMeasurementBlocked, match="FORBIDDEN_MARKET_OUTCOME_FIELD"):
        run(**paths)


def test_final_measurement_recomputes_matrix_despite_co_mutated_receipt(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    matrix = json.loads(paths["disagreement_matrix"].read_text())
    matrix["items"].append({"packet_id": "forged", "field": "forged"})
    _write(paths["disagreement_matrix"], matrix)
    semantic = json.loads(paths["semantic_receipt"].read_text())
    semantic["disagreement_matrix_file_sha256"] = __import__("hashlib").sha256(
        paths["disagreement_matrix"].read_bytes()
    ).hexdigest()
    _write(paths["semantic_receipt"], semantic)
    with pytest.raises(FinalMeasurementBlocked, match="MATRIX_NOT_RECOMPUTED"):
        run(**paths)


def test_measurement_preserves_audited_origin_and_mechanism_despite_triage_mutation(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    canonical = json.loads(paths["canonical_manifest"].read_text())
    selection = json.loads(paths["selection_manifest"].read_text())
    receipt = json.loads(paths["selection_receipt"].read_text())
    triage = json.loads(paths["shadow_triage"].read_text())
    proposal = json.loads(paths["proposal"].read_text())
    audit = json.loads(paths["audit"].read_text())
    linkage = json.loads(paths["episode_linkage"].read_text())
    packets = __import__("scripts.research.dislocation_p0_s1f_model_transport", fromlist=["load_packets"]).load_packets(paths["packet_index"], paths["source_root"])
    first, later = packets[10], packets[0]
    linkage["relationships"][0]["packet_ids"] = [first["packet_id"], later["packet_id"]]
    audit_by_id = {row["packet_id"]: row for row in audit["audits"]}
    audit_by_id[first["packet_id"]]["relationship_assessment"]["episode"] = {"value": "episode-one", "evidence": deepcopy(audit_by_id[later["packet_id"]]["relationship_assessment"]["episode"]["evidence"])}
    audit_by_id[later["packet_id"]]["relationship_assessment"]["episode"] = {"value": "episode-one", "evidence": deepcopy(audit_by_id[later["packet_id"]]["relationship_assessment"]["episode"]["evidence"])}
    audit_by_id[later["packet_id"]]["audited_false_positive_mechanism"] = {"value": "CERTIFICATION_ONLY", "evidence": deepcopy(audit_by_id[later["packet_id"]]["relationship_assessment"]["episode"]["evidence"])}
    rows = build_rows(packets=packets, canonical=canonical, selection=selection, selection_receipt=receipt, triage=triage, proposal=proposal, audit=audit, linkage=linkage)
    origin = next(row for row in rows if row["audited_episode_origin"])
    assert origin["packet_id"] == first["packet_id"]
    report = measure(rows)
    assert report["dominant_false_positive_mechanisms"] == [{"mechanism": "CERTIFICATION_ONLY", "count": 1, "proportion_of_false_positives": "1.000000000000"}]
    changed_triangulation = deepcopy(triage)
    changed_triangulation["triage"][0]["source_context_category"] = "HYPOTHETICAL_RISK_ONLY"
    changed_rows = build_rows(packets=packets, canonical=canonical, selection=selection, selection_receipt=receipt, triage=changed_triangulation, proposal=proposal, audit=audit, linkage=linkage)
    assert measure(changed_rows)["dominant_false_positive_mechanisms"] == report["dominant_false_positive_mechanisms"]


def test_committed_s1f_k_packet_is_exact70_warp_grok46_source_only_evidence() -> None:
    def load(name: str) -> dict[str, object]:
        return json.loads((S1F_ARTIFACT_ROOT / name).read_text(encoding="utf-8"))

    def file_sha(name: str) -> str:
        return __import__("hashlib").sha256((S1F_ARTIFACT_ROOT / name).read_bytes()).hexdigest()

    proposal = load("S1F_GROK_SOURCE_PROPOSALS.json")
    audit = load("S1F_GROK46_INDEPENDENT_AUDIT.json")
    reconciliation = load("S1F_GROK46_ALL70_RELATIONSHIP_RECONCILIATION.json")
    linkage = load("S1F_EPISODE_LINKAGE.json")
    semantic = load("S1F_SEMANTIC_COMPLETION_RECEIPT.json")
    measurement = load("S1F_MEASUREMENT.json")
    k_packet = load("S1F_K_PACKET.json")
    final_bundle = load("S1F_FINAL_RECEIPT_BUNDLE.json")
    access = load("S1F_WARP_GROK46_AUDIT_ACCESS_RECEIPT.json")

    assert file_sha("S1F_GROK_SOURCE_PROPOSALS.json") == (
        "02d55bcba5f1d259bb543c58e888137872cde7274dfff22a7fb599305c302532"
    )
    assert file_sha("S1F_GROK46_INDEPENDENT_AUDIT.json") == (
        "f6d9cc77cadca7d7086564acd710aa8a82c0b0b9a5e199cd11f16c1ec016eaad"
    )
    assert file_sha("S1F_GROK46_ALL70_RELATIONSHIP_RECONCILIATION.json") == (
        "2b5c6e3d624fd6d7514fed1e6bb54178f3ad12adc64b54efc46780f286713711"
    )
    assert file_sha("S1F_K_PACKET.json") == (
        "572fab916e3505a05896a76784c3084af71619c88a7e39a6b4fdff1b96577b99"
    )
    assert proposal["proposal_count"] == audit["audit_count"] == 70
    assert reconciliation["reviewed_packet_ids"] == k_packet["packet_ids"]
    assert len(reconciliation["resolution_matrix"]) == 70
    assert len(reconciliation["final_relationship_assessments"]) == 70
    assert reconciliation["unresolved_count"] == 0
    assert linkage["economic_episode_count"] == 0
    assert linkage["relationships"] == []
    assert semantic["summary"]["economic_episode_count"] == 0
    assert semantic["summary"]["unresolved_disagreement_count"] == 0
    assert measurement["packet_count"] == 70
    assert measurement["report"]["overall_origin_yield"]["successes"] == 0
    assert measurement["report"]["source_feasibility"] == "SOURCE_PRECISION_NOT_PROVEN"
    assert measurement["report"]["sector_partition_status"] == "SECTOR_PARTITION_UNRESOLVED"
    assert k_packet["authority"] == AUTHORITY
    assert k_packet["network"] == "NONE" and k_packet["stop_before"] == "P0-S2"
    assert k_packet["firewall"]["forbidden_directories_present"] == []
    assert final_bundle["artifacts"]["proposal_file_sha256"] == file_sha("S1F_GROK_SOURCE_PROPOSALS.json")
    assert final_bundle["artifacts"]["audit_file_sha256"] == file_sha("S1F_GROK46_INDEPENDENT_AUDIT.json")
    assert final_bundle["artifacts"]["reconciliation_file_sha256"] == file_sha("S1F_GROK46_ALL70_RELATIONSHIP_RECONCILIATION.json")
    assert final_bundle["artifacts"]["k_packet_file_sha256"] == file_sha("S1F_K_PACKET.json")
    assert access["transport"] == {
        "application": "Warp",
        "claude_web_used": False,
        "client": "Oz",
        "declared_model": "Grok 4.6",
        "execution_location": "LOCAL",
        "github_connection_used": False,
        "provider": "xAI",
        "repository_read_scope": "COMMISSION_AND_DECLARED_SOURCE_ONLY_INPUT",
        "runtime_model_id": "grok-4-6-high",
    }
    assert len(access["audit_batches"]) == 7
    assert access["audit_summary"]["packet_count"] == 70
    assert access["all70_reconciliation"]["reviewed_packet_count"] == 70
    assert access["access_boundary"]["browser_actions"] == []
    assert access["access_boundary"]["restricted_data_access"] == "NONE"
