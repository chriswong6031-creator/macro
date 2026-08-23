#!/usr/bin/env python3
"""Validate and freeze the source-only A1R proposal/audit K-packet.

The runner is deliberately offline.  It loads only the canonical-owner model
packet index, the corresponding SEC document bytes, and the two model bundles.
It never imports a market, outcome, ranking, or execution module.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research.dislocation_p0_a1_lib import (  # noqa: E402
    canonical_json,
    forbidden_market_fields,
)
from scripts.research.dislocation_p0_a1r_semantic_contract import (  # noqa: E402
    REQUIRED_PACKET_COUNT,
    RELATIONSHIPS,
    SEMANTIC_FIELDS,
    TYPED_STATES,
    validate_p0_a1r_proposals,
    validate_p0_a1r_semantic_audit,
)


PROPOSAL_SCHEMA = "mastermind.dislocation_p0.a1r_grok_proposals.v2"
AUDIT_SCHEMA = "mastermind.dislocation_p0.a1r_opus_audit.v2"
K_PACKET_SCHEMA = "mastermind.dislocation_p0.a1r_k_packet.v2"


class SemanticRunBlocked(RuntimeError):
    """A model bundle failed the frozen source-only contract."""


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SemanticRunBlocked(f"JSON root is not an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def _source_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise SemanticRunBlocked("matched document source_path missing")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise SemanticRunBlocked("matched document source_path escapes source root") from exc
    return candidate


def _load_packet_documents(
    row: Mapping[str, Any], source_root: Path
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    """Load all and only the FTS-matched document receipts for one packet."""
    documents = row.get("documents")
    packet_id = row.get("packet_id")
    if not isinstance(documents, list) or not documents:
        raise SemanticRunBlocked(f"matched documents missing: {packet_id}")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    source_documents: dict[str, bytes] = {}
    for document in documents:
        if not isinstance(document, Mapping):
            raise SemanticRunBlocked(f"matched document invalid: {packet_id}")
        document_id = document.get("document_id")
        document_name = document.get("document_name")
        document_sha256 = document.get("document_sha256")
        byte_length = document.get("byte_length")
        source_path = document.get("source_path")
        if (
            not isinstance(document_id, str)
            or not document_id
            or not isinstance(document_name, str)
            or not document_name
            or not isinstance(document_sha256, str)
            or len(document_sha256) != 64
            or not isinstance(byte_length, int)
            or byte_length < 0
        ):
            raise SemanticRunBlocked(f"matched document identity invalid: {packet_id}")
        if (
            document_id in seen_ids
            or document_name in seen_names
            or document_sha256 in seen_hashes
            or source_path in seen_paths
        ):
            raise SemanticRunBlocked(f"matched document duplicate: {packet_id}")
        try:
            source = _source_path(source_root, source_path).read_bytes()
        except OSError as exc:
            raise SemanticRunBlocked(
                f"matched document unavailable: {packet_id}:{document_id}"
            ) from exc
        if len(source) != byte_length:
            raise SemanticRunBlocked(f"matched document length mismatch: {packet_id}:{document_id}")
        if sha256(source).hexdigest() != document_sha256:
            raise SemanticRunBlocked(f"matched document hash mismatch: {packet_id}:{document_id}")
        seen_ids.add(document_id)
        seen_names.add(document_name)
        seen_hashes.add(document_sha256)
        seen_paths.add(str(source_path))
        normalized.append({
            "document_id": document_id,
            "document_name": document_name,
            "document_sha256": document_sha256,
            "byte_length": byte_length,
            "source_path": source_path,
        })
        source_documents[document_sha256] = source
    return normalized, source_documents


def load_packets(packet_index_path: Path, source_root: Path) -> list[dict[str, Any]]:
    index = _read_json(packet_index_path)
    if index.get("schema") != "mastermind.dislocation_p0.a1r_model_packet_index.v2":
        raise SemanticRunBlocked("model packet index schema mismatch")
    rows = index.get("packets")
    if not isinstance(rows, list) or len(rows) != REQUIRED_PACKET_COUNT:
        raise SemanticRunBlocked(
            f"model packet index requires exactly twenty rows; got {len(rows or [])}"
        )
    packets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SemanticRunBlocked("model packet index row is not an object")
        documents, source_documents = _load_packet_documents(row, source_root)
        packets.append(dict(row) | {
            "documents": documents,
            "source_documents": source_documents,
        })
    if [int(row["slot"]) for row in packets] != list(range(1, 21)):
        raise SemanticRunBlocked("model packet slots are not the frozen 1..20 order")
    if len({str(row["packet_id"]) for row in packets}) != REQUIRED_PACKET_COUNT:
        raise SemanticRunBlocked("model packet IDs are not unique")
    return packets


def validate_source_manifest_binding(
    source_manifest: Mapping[str, Any],
    packets: Sequence[Mapping[str, Any]],
) -> str:
    """Bind the model packet index to the exact canonical-owner manifest."""
    if (
        source_manifest.get("schema")
        != "mastermind.dislocation_p0.a1r_canonical_source_packets.v2"
        or source_manifest.get("status") != "COMPLETE"
        or source_manifest.get("n") != REQUIRED_PACKET_COUNT
    ):
        raise SemanticRunBlocked("canonical source manifest state/cardinality mismatch")
    body = dict(source_manifest)
    claimed_sha256 = body.pop("manifest_sha256", None)
    computed_sha256 = sha256(canonical_json(body).encode("utf-8")).hexdigest()
    if claimed_sha256 != computed_sha256:
        raise SemanticRunBlocked("canonical source manifest logical SHA mismatch")
    manifest_packets = source_manifest.get("packets")
    if not isinstance(manifest_packets, list) or len(manifest_packets) != REQUIRED_PACKET_COUNT:
        raise SemanticRunBlocked("canonical source manifest packets missing")
    expected: list[dict[str, Any]] = []
    for row in manifest_packets:
        if not isinstance(row, Mapping):
            raise SemanticRunBlocked("canonical source manifest packet is not an object")
        issuer = row.get("issuer")
        filing = row.get("filing")
        clocks = row.get("clocks")
        documents = row.get("matched_documents")
        if (
            not all(isinstance(value, Mapping) for value in (issuer, filing, clocks))
            or not isinstance(documents, list)
            or not documents
        ):
            raise SemanticRunBlocked("canonical source manifest packet projection missing")
        slot = row.get("slot")
        if not isinstance(slot, int):
            raise SemanticRunBlocked("canonical source manifest slot missing")
        expected_documents: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        seen_hashes: set[str] = set()
        for document in documents:
            if not isinstance(document, Mapping):
                raise SemanticRunBlocked("canonical source manifest matched document invalid")
            document_id = document.get("document_id")
            document_name = document.get("document_name")
            document_sha256 = document.get("content_sha256")
            byte_length = document.get("byte_length")
            if (
                not isinstance(document_id, str)
                or not document_id
                or not isinstance(document_name, str)
                or not document_name
                or not isinstance(document_sha256, str)
                or len(document_sha256) != 64
                or not isinstance(byte_length, int)
                or byte_length < 0
                or document_id in seen_ids
                or document_name in seen_names
                or document_sha256 in seen_hashes
            ):
                raise SemanticRunBlocked("canonical source manifest matched document identity invalid")
            seen_ids.add(document_id)
            seen_names.add(document_name)
            seen_hashes.add(document_sha256)
            expected_documents.append({
                "document_id": document_id,
                "document_name": document_name,
                "document_sha256": document_sha256,
                "byte_length": byte_length,
                "source_path": f"packets/{slot:02d}_{document_id}.source",
            })
        expected.append({
            "slot": slot,
            "packet_id": row.get("packet_id"),
            "cik": issuer.get("cik"),
            "accession": filing.get("accession"),
            "accepted_at": clocks.get("accepted_at"),
            "filed_on": clocks.get("filed_on"),
            "documents": expected_documents,
        })
    actual = [
        {
            key: row.get(key)
            for key in (
                "slot",
                "packet_id",
                "cik",
                "accession",
                "accepted_at",
                "filed_on",
                "documents",
            )
        }
        for row in packets
    ]
    if actual != expected:
        raise SemanticRunBlocked("model packet index is not bound to canonical source manifest")
    return computed_sha256


def validate_proposal_bundle(
    *,
    packets: Sequence[Mapping[str, Any]],
    proposal_bundle: Mapping[str, Any],
    source_manifest_sha256: str,
) -> dict[str, Any]:
    if proposal_bundle.get("schema") != PROPOSAL_SCHEMA:
        raise SemanticRunBlocked("Grok proposal schema mismatch")
    proposer = proposal_bundle.get("proposer")
    if not isinstance(proposer, Mapping) or (
        proposer.get("provider") != "xAI"
        or proposer.get("model") != "grok-4.6"
        or proposer.get("role") != "GROK_SOURCE_ONLY"
        or proposer.get("fresh_source_only") is not True
    ):
        raise SemanticRunBlocked("Grok proposer identity/source-only role mismatch")
    if proposal_bundle.get("source_manifest_sha256") != source_manifest_sha256:
        raise SemanticRunBlocked("Grok proposal source manifest mismatch")
    proposals = proposal_bundle.get("proposals")
    if not isinstance(proposals, list) or len(proposals) != REQUIRED_PACKET_COUNT:
        raise SemanticRunBlocked("Grok proposal cardinality mismatch")
    expected_ids = [str(row["packet_id"]) for row in packets]
    actual_ids = [str(row.get("packet_id") or "") for row in proposals if isinstance(row, Mapping)]
    if actual_ids != expected_ids:
        raise SemanticRunBlocked("Grok proposals are not in exact frozen packet order")
    for proposal in proposals:
        semantic = proposal.get("semantic") if isinstance(proposal, Mapping) else None
        if not isinstance(semantic, Mapping) or set(semantic) != SEMANTIC_FIELDS:
            raise SemanticRunBlocked(
                f"Grok proposal semantic field set mismatch: {proposal.get('packet_id') if isinstance(proposal, Mapping) else None}"
            )
    result = validate_p0_a1r_proposals(packets, proposals)
    if not result.ok:
        raise SemanticRunBlocked(canonical_json({"proposal_refusals": result.refusals}))
    if proposal_bundle.get("relationship_hypotheses") != []:
        raise SemanticRunBlocked("Grok relationship hypotheses must remain proposal-only and empty")
    return {
        "packet_count": len(proposals),
        "typed_states": result.typed_states,
    }


def build_audit_input(
    *,
    packets: Sequence[Mapping[str, Any]],
    proposal_bundle: Mapping[str, Any],
    catalog_root: Path,
) -> dict[str, Any]:
    """Assemble one transport file without changing packet/source identities."""
    proposal_by_id = {
        str(row["packet_id"]): row
        for row in proposal_bundle.get("proposals") or []
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for packet in packets:
        slot = int(packet["slot"])
        catalog = _read_json(Path(catalog_root) / f"{slot:02d}_evidence.json")
        catalog_packet = catalog.get("packet")
        expected_documents = packet.get("documents")
        if not isinstance(catalog_packet, Mapping) or (
            catalog_packet.get("packet_id") != packet["packet_id"]
            or catalog_packet.get("documents") != expected_documents
        ):
            raise SemanticRunBlocked(f"evidence catalog identity mismatch: slot {slot}")
        source_documents = packet.get("source_documents")
        if not isinstance(expected_documents, list) or not isinstance(source_documents, Mapping):
            raise SemanticRunBlocked(f"packet document transport missing: {packet['packet_id']}")
        source_utf8_documents: list[dict[str, Any]] = []
        for document in expected_documents:
            if not isinstance(document, Mapping):
                raise SemanticRunBlocked(f"packet document transport invalid: {packet['packet_id']}")
            document_sha256 = document.get("document_sha256")
            source = source_documents.get(document_sha256)
            if not isinstance(document_sha256, str) or not isinstance(source, bytes):
                raise SemanticRunBlocked(f"packet document bytes missing: {packet['packet_id']}")
            try:
                source_utf8 = source.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SemanticRunBlocked(
                    f"audit transport requires UTF-8 SEC bytes: {packet['packet_id']}:{document.get('document_id')}"
                ) from exc
            source_utf8_documents.append(dict(document) | {"source_utf8": source_utf8})
        segments = catalog_packet.get("segments")
        if not isinstance(segments, list):
            raise SemanticRunBlocked(f"evidence catalog segments missing: slot {slot}")
        allowed_hashes = {str(document["document_sha256"]) for document in expected_documents}
        for segment in segments:
            evidence = segment.get("evidence") if isinstance(segment, Mapping) else None
            if not isinstance(evidence, Mapping) or evidence.get("document_sha256") not in allowed_hashes:
                raise SemanticRunBlocked(f"evidence catalog document crosswire: slot {slot}")
        rows.append({
            "packet": {
                key: value for key, value in packet.items() if key != "source_documents"
            },
            "source_utf8_documents": source_utf8_documents,
            "evidence_catalog": segments,
            "grok_proposal": proposal_by_id[str(packet["packet_id"])],
        })
    return {
        "schema": "mastermind.dislocation_p0.a1r_opus_audit_input.v2",
        "source_manifest_sha256": proposal_bundle["source_manifest_sha256"],
        "proposal_bundle_sha256": None,
        "packets": rows,
    }


def finalize_audit(
    *,
    packets: Sequence[Mapping[str, Any]],
    proposal_bundle: Mapping[str, Any],
    proposal_bundle_sha256: str,
    audit_bundle: Mapping[str, Any],
    source_manifest_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if audit_bundle.get("schema") != AUDIT_SCHEMA:
        raise SemanticRunBlocked("Opus audit schema mismatch")
    auditor = audit_bundle.get("auditor")
    if not isinstance(auditor, Mapping) or (
        auditor.get("provider") != "Anthropic"
        or auditor.get("model") != "opus"
        or auditor.get("role") != "OPUS"
        or auditor.get("independent_source_only") is not True
    ):
        raise SemanticRunBlocked("Opus independent source-only identity mismatch")
    if audit_bundle.get("source_manifest_sha256") != source_manifest_sha256:
        raise SemanticRunBlocked("Opus audit source manifest mismatch")
    if audit_bundle.get("proposal_bundle_sha256") != proposal_bundle_sha256:
        raise SemanticRunBlocked("Opus audit proposal bundle mismatch")
    audits = audit_bundle.get("audits")
    relationships = audit_bundle.get("relationships")
    if not isinstance(audits, list) or not isinstance(relationships, list):
        raise SemanticRunBlocked("Opus audit rows/relationships missing")
    proposals = proposal_bundle.get("proposals")
    if not isinstance(proposals, list):
        raise SemanticRunBlocked("proposal rows missing")
    expected_order = [str(row["packet_id"]) for row in packets]
    audit_order = [
        str(row.get("packet_id") or "") for row in audits if isinstance(row, Mapping)
    ]
    if audit_order != expected_order:
        raise SemanticRunBlocked("Opus audits are not in exact frozen packet order")
    for audit in audits:
        assessment = audit.get("relationship_assessment")
        if not isinstance(assessment, Mapping) or set(assessment) != RELATIONSHIPS:
            raise SemanticRunBlocked(
                f"Opus relationship assessment incomplete: {audit.get('packet_id')}"
            )
    result = validate_p0_a1r_semantic_audit(
        packets, proposals, audits, relationships
    )
    if not result.ok:
        raise SemanticRunBlocked(canonical_json({"audit_refusals": result.refusals}))

    verdicts = Counter(str(row.get("verdict")) for row in audits if isinstance(row, Mapping))
    proposal_by_id = {
        str(row["packet_id"]): row
        for row in proposals
        if isinstance(row, Mapping)
    }
    final_typed_states: Counter[str] = Counter()
    typed_refusals: Counter[str] = Counter()
    for audit in audits:
        packet_id = str(audit["packet_id"])
        if audit["verdict"] == "REJECT":
            typed_refusals[str(audit.get("typed_refusal"))] += 1
            continue
        final_semantic = (
            audit.get("final_semantic")
            if audit["verdict"] == "REPAIR"
            else proposal_by_id[packet_id].get("semantic")
        )
        if not isinstance(final_semantic, Mapping):
            raise SemanticRunBlocked(f"final semantic missing: {packet_id}")
        for assertion in final_semantic.values():
            if isinstance(assertion, Mapping) and assertion.get("state") in TYPED_STATES:
                final_typed_states[str(assertion["state"])] += 1
    disagreements = [
        {"packet_id": row.get("packet_id"), **dict(item)}
        for row in audits
        if isinstance(row, Mapping)
        for item in row.get("disagreements") or []
        if isinstance(item, Mapping)
    ]
    matrix = {
        "schema": "mastermind.dislocation_p0.a1r_disagreement_matrix.v2",
        "source_manifest_sha256": source_manifest_sha256,
        "proposal_bundle_sha256": proposal_bundle_sha256,
        "items": disagreements,
        "unresolved_count": 0,
    }
    summary = {
        "packet_count": len(packets),
        "audit_verdicts": dict(sorted(verdicts.items())),
        "final_typed_states": dict(sorted(final_typed_states.items())),
        "typed_refusals": dict(sorted(typed_refusals.items())),
        "disagreement_count": len(disagreements),
        "unresolved_disagreement_count": 0,
        "economic_episode_count": len(result.episodes),
        "episode_ids": list(result.episodes),
        "relationship_counts": dict(sorted(Counter(
            str(edge.get("kind"))
            for edge in relationships
            if isinstance(edge, Mapping)
        ).items())),
    }
    return summary, matrix


def build_k_packet(
    *,
    source_manifest_sha256: str,
    source_manifest_file_sha256: str,
    proposal_bundle_sha256: str,
    audit_bundle_sha256: str,
    packet_index_sha256: str,
    audit_summary: Mapping[str, Any],
    proposal_summary: Mapping[str, Any],
    audit_bundle: Mapping[str, Any],
    matched_document_count: int,
) -> dict[str, Any]:
    packet = {
        "schema": K_PACKET_SCHEMA,
        "status": "AUDITED_TWENTY_SOURCE_ONLY_COMPLETE",
        "admissibility": "P0_S0_S1_K_PACKET_ONLY",
        "stop_before": "P0-S2",
        "source_law": {
            "decision": "DEC:DISLOCATION-P0-A1R-SOURCE-LAW-RECONCILIATION",
            "allocation": [3, 3, 3, 3, 3, 3, 2],
            "logical_query_cells_complete": 146,
            "selection_price_blind": True,
            "selection_identity": "(CIK, accession)",
            "same_cik_different_accession_allowed": True,
            "duplicate_cik_accession_forbidden": True,
            "exact_fts_matched_document_transport": True,
            "matched_document_count": matched_document_count,
            "primary_document_fallback": False,
        },
        "quarantine": {
            "draft_canonical_json_sha256": "832ac650cf18bd31b593fbb0214d9f3ac1b85ccdda6d417e12e5d81a35b76d32",
            "status": "QUARANTINED_UNAUDITED",
            "p0_r1_admissible": False,
        },
        "source_manifest_sha256": source_manifest_sha256,
        "source_manifest_file_sha256": source_manifest_file_sha256,
        "model_packet_index_sha256": packet_index_sha256,
        "grok_proposal_bundle_sha256": proposal_bundle_sha256,
        "opus_audit_bundle_sha256": audit_bundle_sha256,
        "proposal_summary": dict(proposal_summary),
        "audit_summary": dict(audit_summary),
        "audited_packet_ids": [
            str(row.get("packet_id")) for row in audit_bundle.get("audits") or []
        ],
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
        "firewall": {
            "source_only_workspace_verified": True,
            "forbidden_mounts_present": [],
        },
    }
    if forbidden_market_fields(packet):
        raise SemanticRunBlocked("K-packet contains a forbidden source-only field")
    return packet


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-index", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path)
    parser.add_argument("--audit-input-out", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--k-packet-out", type=Path)
    parser.add_argument("--disagreement-out", type=Path)
    parser.add_argument("--relationship-out", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source_manifest = _read_json(args.source_manifest)
        packets = load_packets(args.packet_index, args.source_root)
        source_manifest_sha256 = validate_source_manifest_binding(
            source_manifest, packets
        )
        proposal = _read_json(args.proposal)
        proposal_summary = validate_proposal_bundle(
            packets=packets,
            proposal_bundle=proposal,
            source_manifest_sha256=source_manifest_sha256,
        )
        output: dict[str, Any] = {
            "status": "PROPOSALS_VALID",
            "proposal_bundle_sha256": _file_sha256(args.proposal),
            "proposal_summary": proposal_summary,
        }
        if args.audit_input_out is not None:
            if args.catalog_root is None:
                raise SemanticRunBlocked("--audit-input-out requires --catalog-root")
            audit_input = build_audit_input(
                packets=packets,
                proposal_bundle=proposal,
                catalog_root=args.catalog_root,
            )
            audit_input["proposal_bundle_sha256"] = output["proposal_bundle_sha256"]
            _write_json(args.audit_input_out, audit_input)
            output["audit_input_sha256"] = _file_sha256(args.audit_input_out)
        if args.audit is not None:
            audit = _read_json(args.audit)
            audit_summary, matrix = finalize_audit(
                packets=packets,
                proposal_bundle=proposal,
                proposal_bundle_sha256=output["proposal_bundle_sha256"],
                audit_bundle=audit,
                source_manifest_sha256=source_manifest_sha256,
            )
            output.update({
                "status": "AUDIT_VALID",
                "audit_bundle_sha256": _file_sha256(args.audit),
                "audit_summary": audit_summary,
            })
            if args.disagreement_out is not None:
                _write_json(args.disagreement_out, matrix)
            if args.relationship_out is not None:
                _write_json(args.relationship_out, {
                    "schema": "mastermind.dislocation_p0.a1r_episode_linkage.v2",
                    "source_manifest_sha256": source_manifest_sha256,
                    "proposal_bundle_sha256": output["proposal_bundle_sha256"],
                    "audit_bundle_sha256": output["audit_bundle_sha256"],
                    "economic_episode_count": audit_summary["economic_episode_count"],
                    "relationships": audit.get("relationships") or [],
                })
            if args.k_packet_out is not None:
                k_packet = build_k_packet(
                    source_manifest_sha256=source_manifest_sha256,
                    source_manifest_file_sha256=_file_sha256(args.source_manifest),
                    proposal_bundle_sha256=output["proposal_bundle_sha256"],
                    audit_bundle_sha256=output["audit_bundle_sha256"],
                    packet_index_sha256=_file_sha256(args.packet_index),
                    audit_summary=audit_summary,
                    proposal_summary=proposal_summary,
                    audit_bundle=audit,
                    matched_document_count=sum(
                        len(row.get("documents") or []) for row in packets
                    ),
                )
                _write_json(args.k_packet_out, k_packet)
        print(canonical_json(output))
        return 0
    except Exception as exc:  # noqa: BLE001 - emit one typed CLI blocker.
        print(canonical_json({
            "status": "BLOCKED",
            "blocker": type(exc).__name__,
            "detail": str(exc),
        }))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
