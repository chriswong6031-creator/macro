#!/usr/bin/env python3
"""Deterministically close the source-only S1F semantic audit into honest-N evidence.

This module consumes only frozen S1F source/selection/triage artifacts, completed
source-only model artifacts, and a passive runtime-access receipt.  It has no
transport client, model client, market, or outcome path.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.research.dislocation_p0_a1_lib import canonical_json, forbidden_market_fields
from scripts.research.dislocation_p0_a1r_semantic_contract import _is_p0_episode_eligible
from scripts.research.dislocation_p0_s1f_measurement import measure
from scripts.research.dislocation_p0_s1f_model_transport import (
    AUDIT_INPUT_SCHEMA,
    AUDIT_RESULT_SCHEMA,
    AUDIT_SCHEMA,
    GROK_INPUT_SCHEMA,
    GROK_RESULT_SCHEMA,
    REQUIRED_BATCH_COUNT,
    REQUIRED_PACKET_COUNT,
    SOURCE_MANIFEST_SCHEMA,
    file_sha,
    finalize_all70,
    load_packets,
    logical_sha,
    validate_source_manifest_binding,
)

AUTHORITY = {"can_escalate": False, "can_gate": False, "can_originate_signal": False, "can_rank": False, "can_size": False}
SECTOR_UNRESOLVED = "SECTOR_PARTITION_UNRESOLVED"
AUDIT_ACCESS_SCHEMA = "mastermind.dislocation_p0.s1f_warp_grok46_audit_access_receipt.v1"


class FinalMeasurementBlocked(RuntimeError):
    """A required frozen/final source-only binding is absent or inconsistent."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FinalMeasurementBlocked(code)


def _read(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise FinalMeasurementBlocked(f"S1F_{label}_UNREADABLE") from exc
    _require(isinstance(value, Mapping), f"S1F_{label}_NOT_OBJECT")
    _require(not _forbidden(value), f"S1F_{label}_FORBIDDEN_MARKET_OUTCOME_FIELD")
    return value


def _forbidden(value: Any) -> bool:
    """Reject both the shared source-law list and any price/market/outcome key."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(token in normalized for token in ("price", "market", "outcome")):
                return True
            if _forbidden(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_forbidden(child) for child in value)
    return bool(forbidden_market_fields(value)) if isinstance(value, Mapping) else False


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(canonical_json(value) + "\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _authority(value: Mapping[str, Any], label: str) -> None:
    _require(value.get("authority") == AUTHORITY, f"S1F_{label}_AUTHORITY_NOT_ALL_FALSE")


def _sha_bound(value: Mapping[str, Any], key: str, path: Path, label: str) -> None:
    _require(value.get(key) == file_sha(path), f"S1F_{label}_FILE_HASH_MISMATCH")


def _logical_bound(value: Mapping[str, Any], key: str, label: str) -> None:
    body = dict(value)
    claimed = body.pop(key, None)
    _require(isinstance(claimed, str) and claimed == logical_sha(body), f"S1F_{label}_LOGICAL_HASH_MISMATCH")


def _index_by_id(rows: Any, label: str) -> dict[str, Mapping[str, Any]]:
    _require(isinstance(rows, list) and len(rows) == REQUIRED_PACKET_COUNT, f"S1F_{label}_CARDINALITY")
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        _require(isinstance(row, Mapping) and isinstance(row.get("packet_id"), str), f"S1F_{label}_IDENTITY")
        packet_id = str(row["packet_id"])
        _require(packet_id not in out, f"S1F_{label}_DUPLICATE")
        out[packet_id] = row
    return out


def _batch_artifacts(paths: Sequence[Path], *, schema: str, label: str) -> list[Mapping[str, Any]]:
    _require(len(paths) == REQUIRED_BATCH_COUNT, f"S1F_{label}_CARDINALITY")
    values = [_read(path, label) for path in paths]
    for number, value in enumerate(values, 1):
        _require(value.get("schema") == schema and value.get("batch_number") == number, f"S1F_{label}_ORDER_OR_SCHEMA")
    return values


def _final_semantic(proposal: Mapping[str, Any], audit: Mapping[str, Any]) -> Mapping[str, Any] | None:
    verdict = audit.get("verdict")
    if verdict == "ACCEPT":
        value = proposal.get("semantic")
    elif verdict == "REPAIR":
        value = audit.get("final_semantic")
    else:
        return None
    return value if isinstance(value, Mapping) else None


def _documents(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    matched = source.get("matched_documents")
    primary = source.get("primary_context")
    _require(isinstance(matched, list) and matched, "S1F_SOURCE_MATCHED_DOCUMENTS_MISSING")
    _require(isinstance(primary, Mapping), "S1F_SOURCE_PRIMARY_CONTEXT_MISSING")
    rows: list[dict[str, Any]] = []
    for document in matched:
        _require(isinstance(document, Mapping), "S1F_SOURCE_DOCUMENT_INVALID")
        digest, length, role = document.get("content_sha256"), document.get("byte_length"), document.get("role")
        _require(isinstance(digest, str) and isinstance(length, int) and role in {"primary", "archive"}, "S1F_SOURCE_DOCUMENT_BINDING")
        rows.append({"exact_fts_matched": True, "canonical_owner_role": role, "sha256": digest, "byte_length": length})
    digest, length = primary.get("document_sha256"), primary.get("byte_length")
    _require(isinstance(digest, str) and isinstance(length, int), "S1F_SOURCE_PRIMARY_BINDING")
    rows.append({"exact_fts_matched": False, "canonical_owner_role": "primary", "sha256": digest, "byte_length": length})
    return rows


def build_rows(*, packets: Sequence[Mapping[str, Any]], canonical: Mapping[str, Any], selection: Mapping[str, Any], selection_receipt: Mapping[str, Any], triage: Mapping[str, Any], proposal: Mapping[str, Any], audit: Mapping[str, Any], linkage: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Produce the sole 70-row contract accepted by ``measure``.

    For a multi-packet final episode edge, the final independent reconciliation designates
    its origin as ``packet_ids[0]``.  The emitter preserves that audited identity;
    it never substitutes selection order or a local tie-break.
    """
    _require(len(packets) == REQUIRED_PACKET_COUNT, "S1F_PACKET_CARDINALITY")
    _authority(canonical, "CANONICAL")
    _authority(selection, "SELECTION")
    _authority(selection_receipt, "SELECTION_RECEIPT")
    _authority(triage, "TRIAGE")
    _require(canonical.get("schema") == SOURCE_MANIFEST_SCHEMA and canonical.get("status") == "COMPLETE" and canonical.get("n") == REQUIRED_PACKET_COUNT, "S1F_CANONICAL_SCHEMA")
    source_sha = str(canonical.get("manifest_sha256") or "")
    _require(len(source_sha) == 64, "S1F_CANONICAL_HASH_MISSING")
    _require(selection.get("schema") == "mastermind.dislocation_p0.s1f_exact70_source_manifest.v1" and selection.get("n") == REQUIRED_PACKET_COUNT, "S1F_SELECTION_SCHEMA")
    _require(selection_receipt.get("schema") == "mastermind.dislocation_p0.s1f_exact70_selection_receipt.v1" and selection_receipt.get("status") == "COMPLETE", "S1F_SELECTION_RECEIPT_SCHEMA")
    _require(selection_receipt.get("selection_manifest_sha256") == selection.get("manifest_sha256"), "S1F_SELECTION_RECEIPT_BINDING")
    _require(canonical.get("selection_manifest_sha256") == selection.get("manifest_sha256"), "S1F_CANONICAL_SELECTION_BINDING")
    _require(triage.get("schema") == "mastermind.dislocation_p0.s1f_frozen_shadow_triage.v1" and triage.get("status") == "COMPLETE_BYTE_IDENTICAL_SOURCE_ONLY" and triage.get("packet_count") == REQUIRED_PACKET_COUNT, "S1F_TRIAGE_SCHEMA")
    _require(triage.get("canonical_source_manifest_sha256") == source_sha and triage.get("exact70_selection_manifest_sha256") == selection.get("manifest_sha256") and triage.get("exact70_selection_receipt_sha256") == selection_receipt.get("receipt_sha256"), "S1F_TRIAGE_BINDING")

    source_by_id = _index_by_id(canonical.get("packets"), "CANONICAL_PACKETS")
    selection_by_identity = {(str(row.get("cik")), str(row.get("accession"))): row for row in selection.get("candidates", []) if isinstance(row, Mapping)}
    _require(len(selection_by_identity) == REQUIRED_PACKET_COUNT, "S1F_SELECTION_IDENTITIES")
    triage_by_id = _index_by_id(triage.get("triage"), "TRIAGE")
    proposal_by_id = _index_by_id(proposal.get("proposals"), "PROPOSALS")
    audit_by_id = _index_by_id(audit.get("audits"), "AUDITS")
    packet_ids = [str(packet.get("packet_id")) for packet in packets]
    _require(packet_ids == list(source_by_id), "S1F_PACKET_CANONICAL_ORDER")
    _require(set(packet_ids) == set(triage_by_id) == set(proposal_by_id) == set(audit_by_id), "S1F_FINAL_PACKET_SET")

    episode_origin: dict[str, str] = {}
    relationships = linkage.get("relationships")
    _require(isinstance(relationships, list), "S1F_LINKAGE_RELATIONSHIPS_MISSING")
    packet_id_set = set(packet_ids)
    for edge in relationships:
        if not isinstance(edge, Mapping) or edge.get("kind") != "episode" or edge.get("resolution") != "RESOLVED":
            continue
        episode_id, members = edge.get("episode_id"), edge.get("packet_ids")
        _require(isinstance(episode_id, str) and isinstance(members, list) and members, "S1F_EPISODE_LINKAGE_INVALID")
        _require(episode_id not in episode_origin and all(isinstance(item, str) and item in packet_id_set for item in members), "S1F_EPISODE_LINKAGE_DUPLICATE")
        eligible = [packet_id for packet_id in members if _is_p0_episode_eligible(_final_semantic(proposal_by_id[packet_id], audit_by_id[packet_id])) and audit_by_id[packet_id].get("verdict") in {"ACCEPT", "REPAIR"}]
        _require(eligible and str(members[0]) in eligible, "S1F_EPISODE_ORIGIN_FIRST_NOT_ELIGIBLE")
        episode_origin[episode_id] = str(members[0])

    assigned = set(episode_origin.values())
    _require(len(assigned) == len(episode_origin), "S1F_EPISODE_ORIGIN_DUPLICATE")
    rows: list[dict[str, Any]] = []
    for packet in packets:
        packet_id, identity = str(packet["packet_id"]), (str(packet["cik"]), str(packet["accession"]))
        source, selected, shadow, proposal_row, audit_row = source_by_id[packet_id], selection_by_identity.get(identity), triage_by_id[packet_id], proposal_by_id[packet_id], audit_by_id[packet_id]
        _require(isinstance(selected, Mapping), "S1F_SELECTION_PACKET_MISSING")
        _require(source.get("retrieval_stratum") == selected.get("stratum") and source.get("selection_key") == selected.get("selection_key"), "S1F_SELECTION_SOURCE_CROSSWIRE")
        verdict = str(audit_row.get("verdict") or "")
        _require(verdict in {"ACCEPT", "REPAIR", "REJECT"}, "S1F_AUDIT_VERDICT_INVALID")
        final = _final_semantic(proposal_row, audit_row)
        origin_ids = [episode_id for episode_id, origin in episode_origin.items() if origin == packet_id]
        _require(len(origin_ids) <= 1, "S1F_PACKET_EPISODE_ORIGIN_DUPLICATE")
        if origin_ids:
            _require(final is not None and _is_p0_episode_eligible(final) and verdict in {"ACCEPT", "REPAIR"}, "S1F_EPISODE_ORIGIN_NONADMISSIBLE")
        rows.append({
            "packet_id": packet_id, "cik": identity[0], "accession": identity[1],
            "stratum": selected.get("stratum"), "era": selected.get("era"), "form": selected.get("base_form"),
            "audit_verdict": verdict, "unresolved_audit_disagreement": False,
            "audited_episode_origin": bool(origin_ids), "economic_episode_id": origin_ids[0] if origin_ids else None,
            "shadow_disposition": shadow.get("shadow_disposition"), "triage_rule_ids": shadow.get("rule_ids"),
            "reviewed_documents": _documents(source), "canonical_sector_partition": SECTOR_UNRESOLVED,
            "audited_false_positive_mechanism": audit_row.get("audited_false_positive_mechanism"),
        })
    _require(not _forbidden({"rows": rows}), "S1F_MEASUREMENT_ROWS_FORBIDDEN_FIELD")
    return rows


def run(*, packet_index: Path, source_root: Path, canonical_manifest: Path, owner_replay_proof: Path, selection_manifest: Path, selection_receipt: Path, triage_ruleset: Path, shadow_triage: Path, proposal: Path, audit: Path, reconciliation: Path, episode_linkage: Path, disagreement_matrix: Path, semantic_receipt: Path, audit_access_receipt: Path, grok_inputs: Sequence[Path], grok_results: Sequence[Path], audit_inputs: Sequence[Path], audit_results: Sequence[Path], out_dir: Path) -> dict[str, Any]:
    grok_input_values = _batch_artifacts(grok_inputs, schema=GROK_INPUT_SCHEMA, label="GROK_INPUT")
    grok_result_values = _batch_artifacts(grok_results, schema=GROK_RESULT_SCHEMA, label="GROK_RESULT")
    audit_input_values = _batch_artifacts(audit_inputs, schema=AUDIT_INPUT_SCHEMA, label="AUDIT_INPUT")
    audit_result_values = _batch_artifacts(audit_results, schema=AUDIT_RESULT_SCHEMA, label="AUDIT_RESULT")
    for input_value, result_value, input_path in zip(grok_input_values, grok_result_values, grok_inputs):
        _require(result_value.get("batch_id") == input_value.get("batch_id") and result_value.get("input_bundle_sha256") == file_sha(input_path), "S1F_GROK_RESULT_INPUT_CROSSWIRE")
    for input_value, result_value, input_path in zip(audit_input_values, audit_result_values, audit_inputs):
        _require(result_value.get("batch_id") == input_value.get("batch_id") and result_value.get("input_bundle_sha256") == file_sha(input_path), "S1F_AUDIT_RESULT_INPUT_CROSSWIRE")
    packets = load_packets(packet_index, source_root)
    packet_ids = [str(packet["packet_id"]) for packet in packets]
    canonical = _read(canonical_manifest, "CANONICAL")
    source_sha = validate_source_manifest_binding(canonical, packets)
    _require(source_sha == canonical.get("manifest_sha256"), "S1F_CANONICAL_LOGICAL_HASH")
    owner_replay = _read(owner_replay_proof, "OWNER_REPLAY")
    selection, receipt = _read(selection_manifest, "SELECTION"), _read(selection_receipt, "SELECTION_RECEIPT")
    ruleset, triage = _read(triage_ruleset, "TRIAGE_RULESET"), _read(shadow_triage, "TRIAGE")
    _logical_bound(selection, "manifest_sha256", "SELECTION")
    _logical_bound(receipt, "receipt_sha256", "SELECTION_RECEIPT")
    _logical_bound(triage, "shadow_triage_sha256", "TRIAGE")
    _require(logical_sha(ruleset) == triage.get("triage_ruleset_sha256"), "S1F_TRIAGE_RULESET_HASH_MISMATCH")
    _require(
        owner_replay.get("schema") == "mastermind.dislocation_p0.s1f_canonical_owner_replay_proof.v1"
        and owner_replay.get("status") == "COMPLETE_BYTE_IDENTICAL"
        and owner_replay.get("packet_count") == REQUIRED_PACKET_COUNT
        and owner_replay.get("frozen_manifest_sha256") == source_sha
        and owner_replay.get("replayed_manifest_sha256") == source_sha
        and owner_replay.get("network_access") == "NONE"
        and owner_replay.get("forbidden_dirs_present") == [],
        "S1F_OWNER_REPLAY_PROOF_INVALID",
    )
    proposal_value, audit_value, reconciliation_value = _read(proposal, "PROPOSAL"), _read(audit, "AUDIT"), _read(reconciliation, "RECONCILIATION")
    audit_access = _read(audit_access_receipt, "AUDIT_ACCESS_RECEIPT")
    linkage, matrix, semantic = _read(episode_linkage, "LINKAGE"), _read(disagreement_matrix, "MATRIX"), _read(semantic_receipt, "SEMANTIC_RECEIPT")
    proposal_sha, audit_sha, reconciliation_sha = file_sha(proposal), file_sha(audit), file_sha(reconciliation)
    _require(proposal_value.get("schema") == "mastermind.dislocation_p0.s1f_grok_proposals.v1" and proposal_value.get("source_manifest_sha256") == source_sha and proposal_value.get("proposal_count") == REQUIRED_PACKET_COUNT and proposal_value.get("batch_result_logical_sha256s") == [logical_sha(value) for value in grok_result_values], "S1F_PROPOSAL_BATCH_BINDING")
    _require(audit_value.get("schema") == AUDIT_SCHEMA and audit_value.get("source_manifest_sha256") == source_sha and audit_value.get("proposal_bundle_sha256") == proposal_sha and audit_value.get("audit_count") == REQUIRED_PACKET_COUNT and audit_value.get("batch_result_logical_sha256s") == [logical_sha(value) for value in audit_result_values], "S1F_AUDIT_BATCH_BINDING")
    _require(
        audit_access.get("schema") == AUDIT_ACCESS_SCHEMA
        and audit_access.get("status") == "COMPLETE_SOURCE_ONLY_WARP_GROK46"
        and audit_access.get("source_manifest_sha256") == source_sha
        and audit_access.get("batch_plan_sha256") == proposal_value.get("batch_plan_sha256")
        and audit_access.get("proposal_bundle_file_sha256") == proposal_sha
        and audit_access.get("independent_audit_bundle_file_sha256") == audit_sha
        and audit_access.get("relationship_reconciliation_file_sha256") == reconciliation_sha
        and audit_access.get("authority") == AUTHORITY
        and audit_access.get("stop_before") == "P0-S2"
        and audit_access.get("transport") == {
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
        and audit_access.get("audit_summary", {}).get("packet_count") == REQUIRED_PACKET_COUNT
        and audit_access.get("audit_summary", {}).get("unresolved_disagreements") == 0
        and audit_access.get("all70_reconciliation", {}).get("reviewed_packet_count") == REQUIRED_PACKET_COUNT
        and audit_access.get("all70_reconciliation", {}).get("unresolved_count") == 0,
        "S1F_AUDIT_ACCESS_RECEIPT_INVALID",
    )
    _require(semantic.get("status") == "EXACT70_SOURCE_ONLY_SEMANTIC_AUDIT_LINKAGE_COMPLETE" and semantic.get("source_manifest_sha256") == source_sha and semantic.get("grok_proposal_bundle_file_sha256") == proposal_sha and semantic.get("independent_audit_bundle_file_sha256") == audit_sha and semantic.get("relationship_reconciliation_file_sha256") == reconciliation_sha, "S1F_SEMANTIC_RECEIPT_BINDING")
    _sha_bound(semantic, "episode_linkage_file_sha256", episode_linkage, "SEMANTIC_LINKAGE")
    _sha_bound(semantic, "disagreement_matrix_file_sha256", disagreement_matrix, "SEMANTIC_MATRIX")
    summary, recomputed_matrix = finalize_all70(packets=packets, proposal_bundle=proposal_value, audit_bundle=audit_value, reconciliation=reconciliation_value, proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha)
    expected_linkage = {
        "schema": "mastermind.dislocation_p0.s1f_episode_linkage.v1",
        "source_manifest_sha256": source_sha,
        "proposal_bundle_sha256": proposal_sha,
        "audit_bundle_sha256": audit_sha,
        "relationship_reconciliation_file_sha256": reconciliation_sha,
        "economic_episode_count": summary["economic_episode_count"],
        "episode_ids": summary["episode_ids"],
        "relationships": reconciliation_value.get("relationships") or [],
        "final_relationship_assessments": reconciliation_value.get("final_relationship_assessments") or [],
    }
    _require(matrix == recomputed_matrix, "S1F_DISAGREEMENT_MATRIX_NOT_RECOMPUTED")
    _require(linkage == expected_linkage, "S1F_EPISODE_LINKAGE_NOT_RECOMPUTED")
    _require(semantic.get("summary") == summary, "S1F_FINALIZATION_CROSSWIRE")
    rows = build_rows(packets=packets, canonical=canonical, selection=selection, selection_receipt=receipt, triage=triage, proposal=proposal_value, audit=audit_value, linkage=linkage)
    report = measure(rows)
    authority = AUTHORITY
    measurement = {"schema": "mastermind.dislocation_p0.s1f_measurement.v1", "status": "HONEST_SOURCE_ONLY_OBSERVED", "authority": authority, "network": "NONE", "stop_before": "P0-S2", "source_manifest_sha256": source_sha, "semantic_completion_receipt_file_sha256": file_sha(semantic_receipt), "measurement_contract": "mastermind.dislocation_p0.s1f_measurement_contract.v1", "packet_count": REQUIRED_PACKET_COUNT, "rows": rows, "report": report}
    _require(not _forbidden(measurement), "S1F_MEASUREMENT_FORBIDDEN_FIELD")
    out_dir.mkdir(parents=True, exist_ok=True)
    measurement_path = out_dir / "S1F_MEASUREMENT.json"
    _write(measurement_path, measurement)
    k_packet = {
        "schema": "mastermind.dislocation_p0.s1f_k_packet.v1",
        "status": "HONEST_SOURCE_ONLY_EVIDENCE",
        "authority": authority,
        "network": "NONE",
        "stop_before": "P0-S2",
        "source_manifest_sha256": source_sha,
        "canonical_owner_replay_proof_file_sha256": file_sha(owner_replay_proof),
        "triage_contract_sha256": triage["triage_ruleset_sha256"],
        "fresh_70_selection_sha256": selection["manifest_sha256"],
        "grok_proposal_bundle_file_sha256": proposal_sha,
        "independent_audit_bundle_file_sha256": audit_sha,
        "auditor_runtime_access_receipt_file_sha256": file_sha(audit_access_receipt),
        "semantic_completion_receipt_file_sha256": file_sha(semantic_receipt),
        "measurement_file_sha256": file_sha(measurement_path),
        "packet_ids": packet_ids,
        "honest_feasibility": report,
        "firewall": {
            "canonical_owner_replay": owner_replay["status"],
            "network_access": owner_replay["network_access"],
            "forbidden_directories_present": owner_replay["forbidden_dirs_present"],
            "source_only_field_scan": "PASS",
        },
    }
    _require(not _forbidden(k_packet), "S1F_K_PACKET_FORBIDDEN_FIELD")
    k_path = out_dir / "S1F_K_PACKET.json"
    _write(k_path, k_packet)
    published_root = "research/dislocation_intelligence/p0_s1f"
    published_paths = {
        "proposal": f"{published_root}/S1F_GROK_SOURCE_PROPOSALS.json",
        "audit": f"{published_root}/S1F_GROK46_INDEPENDENT_AUDIT.json",
        "reconciliation": f"{published_root}/S1F_GROK46_ALL70_RELATIONSHIP_RECONCILIATION.json",
        "episode_linkage": f"{published_root}/S1F_EPISODE_LINKAGE.json",
        "disagreement_matrix": f"{published_root}/S1F_DISAGREEMENT_MATRIX.json",
        "semantic_completion_receipt": f"{published_root}/S1F_SEMANTIC_COMPLETION_RECEIPT.json",
        "auditor_runtime_access_receipt": f"{published_root}/S1F_WARP_GROK46_AUDIT_ACCESS_RECEIPT.json",
        "measurement": f"{published_root}/S1F_MEASUREMENT.json",
        "k_packet": f"{published_root}/S1F_K_PACKET.json",
        "final_receipt_bundle": f"{published_root}/S1F_FINAL_RECEIPT_BUNDLE.json",
        "measurement_receipt": f"{published_root}/S1F_MEASUREMENT_RECEIPT.json",
    }
    bundle = {
        "schema": "mastermind.dislocation_p0.s1f_final_receipt_bundle.v1",
        "status": "HONEST_SOURCE_ONLY_FINAL_EVIDENCE_READY",
        "authority": authority,
        "network": "NONE",
        "stop_before": "P0-S2",
        "source_manifest_sha256": source_sha,
        "published_artifact_paths": published_paths,
        "batch_artifacts": {
            "grok_input_file_sha256s": [file_sha(path) for path in grok_inputs],
            "grok_result_file_sha256s": [file_sha(path) for path in grok_results],
            "independent_audit_input_file_sha256s": [file_sha(path) for path in audit_inputs],
            "independent_audit_result_file_sha256s": [file_sha(path) for path in audit_results],
        },
        "artifacts": {
            "canonical_manifest_file_sha256": file_sha(canonical_manifest),
            "canonical_owner_replay_proof_file_sha256": file_sha(owner_replay_proof),
            "selection_manifest_file_sha256": file_sha(selection_manifest),
            "selection_receipt_file_sha256": file_sha(selection_receipt),
            "triage_ruleset_file_sha256": file_sha(triage_ruleset),
            "shadow_triage_file_sha256": file_sha(shadow_triage),
            "proposal_file_sha256": proposal_sha,
            "audit_file_sha256": audit_sha,
            "reconciliation_file_sha256": reconciliation_sha,
            "episode_linkage_file_sha256": file_sha(episode_linkage),
            "disagreement_matrix_file_sha256": file_sha(disagreement_matrix),
            "semantic_completion_receipt_file_sha256": file_sha(semantic_receipt),
            "auditor_runtime_access_receipt_file_sha256": file_sha(audit_access_receipt),
            "measurement_file_sha256": file_sha(measurement_path),
            "k_packet_file_sha256": file_sha(k_path),
        },
    }
    _require(not _forbidden(bundle), "S1F_FINAL_RECEIPT_BUNDLE_FORBIDDEN_FIELD")
    bundle_path = out_dir / "S1F_FINAL_RECEIPT_BUNDLE.json"
    _write(bundle_path, bundle)
    receipt_value = {"schema": "mastermind.dislocation_p0.s1f_measurement_receipt.v1", "status": "HONEST_SOURCE_ONLY_MEASUREMENT_COMPLETE", "authority": authority, "network": "NONE", "stop_before": "P0-S2", "measurement_file_sha256": file_sha(measurement_path), "k_packet_file_sha256": file_sha(k_path), "final_receipt_bundle_file_sha256": file_sha(bundle_path), "overall_origin_yield": report["overall_origin_yield"], "economic_episode_count": report["overall_origin_yield"]["successes"]}
    receipt_path = out_dir / "S1F_MEASUREMENT_RECEIPT.json"
    _write(receipt_path, receipt_value)
    return {"measurement": measurement_path, "receipt": receipt_path, "k_packet": k_path, "bundle": bundle_path}


def _paths(parser: argparse.ArgumentParser, name: str) -> None:
    parser.add_argument(name, type=Path, action="append", required=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("--packet-index", "--source-root", "--canonical-manifest", "--owner-replay-proof", "--selection-manifest", "--selection-receipt", "--triage-ruleset", "--shadow-triage", "--proposal", "--audit", "--reconciliation", "--episode-linkage", "--disagreement-matrix", "--semantic-receipt", "--audit-access-receipt", "--out-dir"):
        parser.add_argument(name, type=Path, required=True)
    _paths(parser, "--grok-input"); _paths(parser, "--grok-result"); _paths(parser, "--audit-input"); _paths(parser, "--audit-result")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        result = run(packet_index=args.packet_index, source_root=args.source_root, canonical_manifest=args.canonical_manifest, owner_replay_proof=args.owner_replay_proof, selection_manifest=args.selection_manifest, selection_receipt=args.selection_receipt, triage_ruleset=args.triage_ruleset, shadow_triage=args.shadow_triage, proposal=args.proposal, audit=args.audit, reconciliation=args.reconciliation, episode_linkage=args.episode_linkage, disagreement_matrix=args.disagreement_matrix, semantic_receipt=args.semantic_receipt, audit_access_receipt=args.audit_access_receipt, grok_inputs=args.grok_input, grok_results=args.grok_result, audit_inputs=args.audit_input, audit_results=args.audit_result, out_dir=args.out_dir)
        print(canonical_json({key: str(value) for key, value in result.items()}))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(canonical_json({"status": "BLOCKED", "blocker": type(exc).__name__, "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
