#!/usr/bin/env python3
"""Offline transport and validation helpers for S1F's seven model batches.

No function in this module calls a model or a network.  Source bytes come only
from the canonical-owner packet tree and are bound to its manifest before any
transport is produced.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research.dislocation_p0_a1_lib import canonical_json, forbidden_market_fields  # noqa: E402
from scripts.research.dislocation_p0_a1r_evidence_catalog import evidence_segments  # noqa: E402
from scripts.research.dislocation_p0_a1r_semantic_contract import (  # noqa: E402
    RELATIONSHIPS,
    SEMANTIC_FIELDS,
)
from scripts.research.dislocation_p0_s1f_semantic_contract import (  # noqa: E402
    REQUIRED_BATCH_COUNT,
    REQUIRED_BATCH_SIZE,
    REQUIRED_PACKET_COUNT,
    validate_s1f_audit,
    validate_s1f_proposals,
)

PACKET_INDEX_SCHEMA = "mastermind.dislocation_p0.s1f_model_packet_index.v1"
SOURCE_MANIFEST_SCHEMA = "mastermind.dislocation_p0.s1f_canonical_source_packets.v1"
GROK_INPUT_SCHEMA = "mastermind.dislocation_p0.s1f_grok_input_batch.v1"
GROK_RESULT_SCHEMA = "mastermind.dislocation_p0.s1f_grok_proposal_batch.v1"
PROPOSAL_SCHEMA = "mastermind.dislocation_p0.s1f_grok_proposals.v1"
OPUS_INPUT_SCHEMA = "mastermind.dislocation_p0.s1f_opus_audit_input_batch.v1"
OPUS_RESULT_SCHEMA = "mastermind.dislocation_p0.s1f_opus_audit_batch.v1"
AUDIT_SCHEMA = "mastermind.dislocation_p0.s1f_opus_audit.v1"
RELATION_INPUT_SCHEMA = "mastermind.dislocation_p0.s1f_all70_relationship_input.v1"
RELATION_SCHEMA = "mastermind.dislocation_p0.s1f_all70_relationship_reconciliation.v1"
EVIDENCE_CATALOG_SCHEMA = "mastermind.dislocation_p0.s1f_evidence_catalog.v1"
MAX_MODEL_BATCH_BYTES = 30_000_000


class S1FModelBlocked(RuntimeError):
    """A source-only model transport or result failed closed."""


def _is_opus_5_max(value: Any) -> bool:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ") == "opus 5 max"


def logical_sha(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise S1FModelBlocked(f"JSON root is not an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def _source_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise S1FModelBlocked("source_path missing")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise S1FModelBlocked("source_path escapes canonical packet root") from exc
    return candidate


def _load_document(root: Path, document: Mapping[str, Any], role: str) -> tuple[dict[str, Any], bytes]:
    digest = document.get("document_sha256")
    byte_length = document.get("byte_length")
    if (
        not isinstance(document.get("document_id"), str)
        or not isinstance(document.get("document_name"), str)
        or not isinstance(digest, str)
        or len(digest) != 64
        or not isinstance(byte_length, int)
        or byte_length < 0
    ):
        raise S1FModelBlocked("canonical document identity invalid")
    try:
        source = _source_path(root, document.get("source_path")).read_bytes()
    except OSError as exc:
        raise S1FModelBlocked(f"canonical document unavailable: {document.get('document_id')}") from exc
    if len(source) != byte_length or sha256(source).hexdigest() != digest:
        raise S1FModelBlocked(f"canonical document bytes mismatch: {document.get('document_id')}")
    normalized = {
        key: document.get(key)
        for key in ("document_id", "document_name", "document_sha256", "byte_length", "source_path")
    }
    normalized["source_role"] = role
    return normalized, source


def load_packets(packet_index_path: Path, source_root: Path) -> list[dict[str, Any]]:
    index = _read_json(packet_index_path)
    if index.get("schema") != PACKET_INDEX_SCHEMA:
        raise S1FModelBlocked("S1F model packet index schema mismatch")
    rows = index.get("packets")
    if not isinstance(rows, list) or len(rows) != REQUIRED_PACKET_COUNT:
        raise S1FModelBlocked("S1F model packet index requires exactly seventy packets")
    packets: list[dict[str, Any]] = []
    for expected_slot, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or row.get("slot") != expected_slot:
            raise S1FModelBlocked("S1F packet index order is not exact slots 1..70")
        exact = row.get("documents")
        if not isinstance(exact, list) or not exact:
            raise S1FModelBlocked(f"exact FTS-matched documents missing: {row.get('packet_id')}")
        documents: list[dict[str, Any]] = []
        sources: dict[str, bytes] = {}
        exact_hashes: set[str] = set()
        for raw in exact:
            if not isinstance(raw, Mapping):
                raise S1FModelBlocked("exact FTS-matched document invalid")
            document, source = _load_document(source_root, raw, "EXACT_FTS_MATCHED")
            digest = str(document["document_sha256"])
            if digest in exact_hashes:
                raise S1FModelBlocked(f"duplicate exact matched document: {row.get('packet_id')}")
            exact_hashes.add(digest)
            documents.append(document)
            sources[digest] = source
        primary = row.get("primary_context")
        if not isinstance(primary, Mapping):
            raise S1FModelBlocked(f"additive primary context missing: {row.get('packet_id')}")
        primary_doc, primary_source = _load_document(source_root, primary, "ADDITIVE_PRIMARY_CONTEXT")
        primary_digest = str(primary_doc["document_sha256"])
        if primary_digest in exact_hashes:
            for document in documents:
                if document["document_sha256"] == primary_digest:
                    document["source_role"] = "EXACT_FTS_MATCHED_AND_PRIMARY_CONTEXT"
                    break
        else:
            documents.append(primary_doc)
            sources[primary_digest] = primary_source
        if row.get("primary_document_substitution") is not False:
            raise S1FModelBlocked(f"primary document substitution is not false: {row.get('packet_id')}")
        packets.append(dict(row) | {
            "documents": documents,
            "exact_matched_document_hashes": sorted(exact_hashes),
            "additive_primary_context_hash": primary_digest,
            "source_documents": sources,
        })
    if len({str(row.get("packet_id")) for row in packets}) != REQUIRED_PACKET_COUNT:
        raise S1FModelBlocked("S1F packet IDs are not unique")
    return packets


def validate_source_manifest_binding(
    source_manifest: Mapping[str, Any], packets: Sequence[Mapping[str, Any]]
) -> str:
    if (
        source_manifest.get("schema") != SOURCE_MANIFEST_SCHEMA
        or source_manifest.get("status") != "COMPLETE"
        or source_manifest.get("n") != REQUIRED_PACKET_COUNT
    ):
        raise S1FModelBlocked("canonical S1F source manifest state/cardinality mismatch")
    body = dict(source_manifest)
    claimed = body.pop("manifest_sha256", None)
    computed = logical_sha(body)
    if claimed != computed:
        raise S1FModelBlocked("canonical S1F source manifest logical SHA mismatch")
    rows = source_manifest.get("packets")
    if not isinstance(rows, list) or len(rows) != REQUIRED_PACKET_COUNT:
        raise S1FModelBlocked("canonical S1F source manifest packets missing")
    for manifest_row, packet in zip(rows, packets):
        if not isinstance(manifest_row, Mapping):
            raise S1FModelBlocked("canonical S1F source manifest row invalid")
        issuer, filing, clocks = (manifest_row.get(key) for key in ("issuer", "filing", "clocks"))
        matched, primary = manifest_row.get("matched_documents"), manifest_row.get("primary_context")
        if not all(isinstance(value, Mapping) for value in (issuer, filing, clocks, primary)) or not isinstance(matched, list):
            raise S1FModelBlocked("canonical S1F source manifest projection missing")
        expected_exact = [
            {
                "document_id": row.get("document_id"),
                "document_name": row.get("document_name"),
                "document_sha256": row.get("content_sha256"),
                "byte_length": row.get("byte_length"),
            }
            for row in matched if isinstance(row, Mapping)
        ]
        actual_exact = [
            {key: row.get(key) for key in ("document_id", "document_name", "document_sha256", "byte_length")}
            for row in packet.get("documents") or []
            if isinstance(row, Mapping) and str(row.get("document_sha256")) in set(packet.get("exact_matched_document_hashes") or [])
        ]
        expected_primary = {
            "document_id": primary.get("document_id"),
            "document_name": primary.get("document_name"),
            "document_sha256": primary.get("document_sha256"),
            "byte_length": primary.get("byte_length"),
        }
        actual_primary = next((
            {key: row.get(key) for key in ("document_id", "document_name", "document_sha256", "byte_length")}
            for row in packet.get("documents") or []
            if isinstance(row, Mapping) and row.get("document_sha256") == packet.get("additive_primary_context_hash")
        ), None)
        actual_identity = (
            packet.get("slot"), packet.get("packet_id"), packet.get("cik"), packet.get("accession"),
            packet.get("accepted_at"), packet.get("filed_on"), packet.get("primary_document_substitution"),
        )
        expected_identity = (
            manifest_row.get("slot"), manifest_row.get("packet_id"), issuer.get("cik"), filing.get("accession"),
            clocks.get("accepted_at"), clocks.get("filed_on"), manifest_row.get("primary_document_substitution"),
        )
        if actual_identity != expected_identity or actual_exact != expected_exact or actual_primary != expected_primary:
            raise S1FModelBlocked(f"packet index not bound to source manifest: {packet.get('packet_id')}")
    return computed


def enrich_packets_from_source_manifest(
    source_manifest: Mapping[str, Any], packets: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Project only hash-verified canonical-owner metadata into model packets."""
    rows = source_manifest.get("packets")
    if not isinstance(rows, list) or len(rows) != len(packets):
        raise S1FModelBlocked("canonical S1F enrichment rows missing")
    enriched: list[dict[str, Any]] = []
    for manifest_row, packet in zip(rows, packets):
        if not isinstance(manifest_row, Mapping) or manifest_row.get("packet_id") != packet.get("packet_id"):
            raise S1FModelBlocked("canonical S1F enrichment identity crosswire")
        matched = manifest_row.get("matched_documents")
        role_by_hash = {
            str(row.get("content_sha256")): row.get("role")
            for row in matched or [] if isinstance(row, Mapping)
        }
        documents = []
        for document in packet.get("documents") or []:
            digest = str(document.get("document_sha256"))
            value = dict(document)
            value["canonical_document_role"] = role_by_hash.get(digest) if digest in role_by_hash else "primary_context"
            documents.append(value)
        enriched.append(dict(packet) | {
            "documents": documents,
            "issuer": dict(manifest_row.get("issuer") or {}),
            "filing": dict(manifest_row.get("filing") or {}),
            "clocks": dict(manifest_row.get("clocks") or {}),
            "lineage": dict(manifest_row.get("lineage") or {}),
            "retrieval_stratum": manifest_row.get("retrieval_stratum"),
            "selection_key": manifest_row.get("selection_key"),
            "retrieval_provenance": {
                "semantic_authority": "NONE",
                "query_edges": [dict(row) for row in manifest_row.get("query_edges") or [] if isinstance(row, Mapping)],
            },
        })
    return enriched


def validate_batch_plan(
    batch_plan: Mapping[str, Any], packets: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    body = dict(batch_plan)
    claimed = body.pop("batch_plan_sha256", None)
    if claimed != logical_sha(body):
        raise S1FModelBlocked("exact70 batch plan logical SHA mismatch")
    batches = batch_plan.get("batches")
    order = batch_plan.get("batch_order")
    if not isinstance(batches, list) or len(batches) != REQUIRED_BATCH_COUNT or not isinstance(order, list):
        raise S1FModelBlocked("exact70 batch plan requires seven batches")
    if [row.get("batch_id") for row in batches if isinstance(row, Mapping)] != order:
        raise S1FModelBlocked("exact70 batch plan order mismatch")
    packet_by_id = {str(row["packet_id"]): row for row in packets}
    seen: list[str] = []
    normalized: list[dict[str, Any]] = []
    for batch in batches:
        rows = batch.get("packets") if isinstance(batch, Mapping) else None
        if not isinstance(rows, list) or len(rows) != REQUIRED_BATCH_SIZE:
            raise S1FModelBlocked(f"batch requires exactly ten packets: {batch.get('batch_id') if isinstance(batch, Mapping) else None}")
        ids = [str(row.get("packet_id")) for row in rows if isinstance(row, Mapping)]
        if len(ids) != REQUIRED_BATCH_SIZE or ids != [str(row.get("packet_id")) for row in sorted(rows, key=lambda item: str(item.get("selection_key")))]:
            raise S1FModelBlocked(f"batch packet order changed: {batch.get('batch_id')}")
        if any(packet_id not in packet_by_id for packet_id in ids):
            raise S1FModelBlocked(f"batch packet unknown: {batch.get('batch_id')}")
        for planned in rows:
            packet = packet_by_id[str(planned["packet_id"])]
            if any(str(planned.get(key)) != str(packet.get(key)) for key in ("cik", "accession")):
                raise S1FModelBlocked(f"batch identity crosswire: {planned.get('packet_id')}")
        seen.extend(ids)
        normalized.append({"batch_id": batch["batch_id"], "packet_ids": ids})
    if len(seen) != REQUIRED_PACKET_COUNT or set(seen) != set(packet_by_id):
        raise S1FModelBlocked("batch plan does not cover exact70 exactly once")
    return normalized


def build_evidence_catalog(packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: list[dict[str, Any]] = []
    for packet in packets:
        segments: list[dict[str, Any]] = []
        sources = packet.get("source_documents")
        for document in packet.get("documents") or []:
            digest = str(document["document_sha256"])
            source = sources.get(digest) if isinstance(sources, Mapping) else None
            if not isinstance(source, bytes):
                raise S1FModelBlocked(f"catalog source missing: {packet.get('packet_id')}:{digest}")
            for segment in evidence_segments(packet_id=str(packet["packet_id"]), document_sha256=digest, source=source):
                segment["source_role"] = document.get("source_role")
                # `evidence.excerpt` is the exact readable raw-byte slice. The
                # normalized display duplicate is unnecessary transport weight.
                segment.pop("display_text", None)
                segments.append(segment)
        output.append({
            "slot": packet["slot"],
            "packet_id": packet["packet_id"],
            "documents": packet["documents"],
            "segments": segments,
        })
    if len(output) != REQUIRED_PACKET_COUNT:
        raise S1FModelBlocked("evidence catalog is not exact70")
    return {"schema": EVIDENCE_CATALOG_SCHEMA, "packet_count": REQUIRED_PACKET_COUNT, "packets": output}


def _model_packet(packet: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    sources = packet.get("source_documents")
    documents: list[dict[str, Any]] = []
    for document in packet.get("documents") or []:
        digest = str(document["document_sha256"])
        source = sources.get(digest) if isinstance(sources, Mapping) else None
        if not isinstance(source, bytes):
            raise S1FModelBlocked(f"transport source missing: {packet.get('packet_id')}:{digest}")
        documents.append(dict(document))
    return {
        "packet": {key: value for key, value in packet.items() if key not in {"source_documents", "documents", "primary_context"}},
        "source_documents": documents,
        "evidence_catalog": catalog.get("segments"),
        "source_transport": "EXACT_BATCH_DOCUMENT_STORE_PLUS_RAW_BYTE_REPLAYABLE_EVIDENCE_CATALOG",
        "document_bytes_attached": True,
    }


def _batch_document_store(rows: Sequence[Mapping[str, Any]], packet_by_id: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for row in rows:
        packet = row.get("packet") if isinstance(row, Mapping) else None
        packet_id = str(packet.get("packet_id")) if isinstance(packet, Mapping) else ""
        source_packet = packet_by_id.get(packet_id)
        if not isinstance(source_packet, Mapping):
            raise S1FModelBlocked(f"batch document store packet crosswire: {packet_id}")
        sources = source_packet.get("source_documents")
        for document in row.get("source_documents") or []:
            digest = str(document.get("document_sha256")) if isinstance(document, Mapping) else ""
            source = sources.get(digest) if isinstance(sources, Mapping) else None
            if not isinstance(source, bytes) or sha256(source).hexdigest() != digest:
                raise S1FModelBlocked(f"batch document store bytes missing: {packet_id}:{digest}")
            if digest in store:
                continue
            payload: dict[str, Any]
            try:
                payload = {"source_utf8": source.decode("utf-8"), "source_encoding": "UTF-8_EXACT"}
            except UnicodeDecodeError:
                payload = {
                    "source_base64": base64.b64encode(source).decode("ascii"),
                    "source_encoding": "BINARY_EXACT_BASE64",
                }
            store[digest] = {
                "document_sha256": digest,
                "byte_length": len(source),
                **payload,
            }
    return [store[digest] for digest in sorted(store)]


def _assert_no_transport_leak(value: Mapping[str, Any]) -> None:
    if forbidden_market_fields(value):
        raise S1FModelBlocked("source-only transport contains forbidden market/outcome field")
    forbidden_keys = {"triage", "triage_category", "triage_disposition", "shadow_triage", "a1r_semantics", "prior_k_packet"}
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                if str(key).lower() in forbidden_keys or str(key).lower().startswith("a1r_"):
                    raise S1FModelBlocked(f"independent transport leakage: {key}")
                stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)


def build_grok_inputs(
    *, packets: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
    catalog: Mapping[str, Any], source_manifest_sha256: str, batch_plan_sha256: str,
) -> list[dict[str, Any]]:
    packet_by_id = {str(row["packet_id"]): row for row in packets}
    catalog_by_id = {str(row["packet_id"]): row for row in catalog.get("packets") or [] if isinstance(row, Mapping)}
    output: list[dict[str, Any]] = []
    for batch_number, batch in enumerate(batches, 1):
        rows = [_model_packet(packet_by_id[packet_id], catalog_by_id[packet_id]) for packet_id in batch["packet_ids"]]
        document_store = _batch_document_store(rows, packet_by_id)
        value = {
            "schema": GROK_INPUT_SCHEMA,
            "batch_number": batch_number,
            "batch_id": batch["batch_id"],
            "packet_count": REQUIRED_BATCH_SIZE,
            "source_manifest_sha256": source_manifest_sha256,
            "batch_plan_sha256": batch_plan_sha256,
            "source_only": True,
            "relationship_hypotheses": "DEFER_TO_FINAL_ALL70_RECONCILIATION",
            "document_store": document_store,
            "packets": rows,
        }
        _assert_no_transport_leak(value)
        byte_length = len((canonical_json(value) + "\n").encode("utf-8"))
        if byte_length >= MAX_MODEL_BATCH_BYTES:
            raise S1FModelBlocked(
                f"Grok input batch exceeds {MAX_MODEL_BATCH_BYTES} bytes: {batch['batch_id']}:{byte_length}"
            )
        output.append(value)
    return output


def merge_grok_results(
    *, packets: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]], input_bundle_sha256s: Sequence[str],
    source_manifest_sha256: str, batch_plan_sha256: str,
) -> dict[str, Any]:
    if len(results) != REQUIRED_BATCH_COUNT or len(input_bundle_sha256s) != REQUIRED_BATCH_COUNT:
        raise S1FModelBlocked("all seven Grok result batches are required")
    proposal_by_id: dict[str, Mapping[str, Any]] = {}
    result_hashes: list[str] = []
    for number, (batch, result, input_sha) in enumerate(zip(batches, results, input_bundle_sha256s), 1):
        proposer = result.get("proposer")
        if (
            result.get("schema") != GROK_RESULT_SCHEMA
            or result.get("batch_number") != number
            or result.get("batch_id") != batch["batch_id"]
            or result.get("source_manifest_sha256") != source_manifest_sha256
            or result.get("batch_plan_sha256") != batch_plan_sha256
            or result.get("input_bundle_sha256") != input_sha
            or not isinstance(proposer, Mapping)
            or proposer.get("provider") != "xAI"
            or not isinstance(proposer.get("model"), str)
            or proposer.get("role") != "GROK_SOURCE_ONLY"
            or proposer.get("fresh_source_only") is not True
        ):
            raise S1FModelBlocked(f"Grok result batch binding/identity invalid: {batch['batch_id']}")
        proposals = result.get("proposals")
        actual_ids = [str(row.get("packet_id")) for row in proposals or [] if isinstance(row, Mapping)]
        if not isinstance(proposals, list) or actual_ids != batch["packet_ids"]:
            raise S1FModelBlocked(f"Grok result packet order changed: {batch['batch_id']}")
        for row in proposals:
            if (
                row.get("proposer_role") != "GROK_SOURCE_ONLY"
                or not isinstance(row.get("semantic"), Mapping)
                or set(row["semantic"]) != SEMANTIC_FIELDS
                or row["packet_id"] in proposal_by_id
            ):
                raise S1FModelBlocked(f"Grok proposal shape/identity invalid: {row.get('packet_id')}")
            proposal_by_id[str(row["packet_id"])] = row
        if result.get("relationship_hypotheses") not in (None, []):
            raise S1FModelBlocked("Grok batch relationship hypotheses must be empty")
        result_hashes.append(logical_sha(result))
    proposals = [proposal_by_id[str(packet["packet_id"])] for packet in packets]
    validation = validate_s1f_proposals(packets, proposals)
    if not validation.ok:
        raise S1FModelBlocked(canonical_json({"proposal_refusals": validation.refusals}))
    merged = {
        "schema": PROPOSAL_SCHEMA,
        "source_manifest_sha256": source_manifest_sha256,
        "batch_plan_sha256": batch_plan_sha256,
        "batch_result_logical_sha256s": result_hashes,
        "proposal_count": REQUIRED_PACKET_COUNT,
        "proposals": proposals,
        "relationship_hypotheses": [],
    }
    _assert_no_transport_leak(merged)
    return merged


def build_opus_inputs(
    *, grok_inputs: Sequence[Mapping[str, Any]], proposal_bundle: Mapping[str, Any],
    proposal_bundle_sha256: str,
) -> list[dict[str, Any]]:
    proposal_by_id = {str(row["packet_id"]): row for row in proposal_bundle.get("proposals") or [] if isinstance(row, Mapping)}
    output: list[dict[str, Any]] = []
    for grok_input in grok_inputs:
        rows: list[dict[str, Any]] = []
        for row in grok_input.get("packets") or []:
            packet = row.get("packet") if isinstance(row, Mapping) else None
            if not isinstance(packet, Mapping) or str(packet.get("packet_id")) not in proposal_by_id:
                raise S1FModelBlocked("Opus input packet/proposal crosswire")
            rows.append(dict(row) | {"grok_proposal": proposal_by_id[str(packet["packet_id"])]})
        value = {
            "schema": OPUS_INPUT_SCHEMA,
            "batch_number": grok_input["batch_number"],
            "batch_id": grok_input["batch_id"],
            "packet_count": REQUIRED_BATCH_SIZE,
            "source_manifest_sha256": grok_input["source_manifest_sha256"],
            "batch_plan_sha256": grok_input["batch_plan_sha256"],
            "proposal_bundle_sha256": proposal_bundle_sha256,
            "independent_source_only": True,
            "shadow_triage_included": False,
            "prior_a1r_semantics_included": False,
            "document_store": grok_input.get("document_store"),
            "packets": rows,
        }
        _assert_no_transport_leak(value)
        byte_length = len((canonical_json(value) + "\n").encode("utf-8"))
        if byte_length >= MAX_MODEL_BATCH_BYTES:
            raise S1FModelBlocked(
                f"Opus input batch exceeds {MAX_MODEL_BATCH_BYTES} bytes: {grok_input['batch_id']}:{byte_length}"
            )
        output.append(value)
    return output


def merge_opus_results(
    *, packets: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]], input_bundle_sha256s: Sequence[str],
    source_manifest_sha256: str, batch_plan_sha256: str, proposal_bundle_sha256: str,
) -> dict[str, Any]:
    if len(results) != REQUIRED_BATCH_COUNT or len(input_bundle_sha256s) != REQUIRED_BATCH_COUNT:
        raise S1FModelBlocked("all seven Opus result batches are required")
    audit_by_id: dict[str, Mapping[str, Any]] = {}
    result_hashes: list[str] = []
    for number, (batch, result, input_sha) in enumerate(zip(batches, results, input_bundle_sha256s), 1):
        auditor = result.get("auditor")
        if (
            result.get("schema") != OPUS_RESULT_SCHEMA
            or result.get("batch_number") != number
            or result.get("batch_id") != batch["batch_id"]
            or result.get("source_manifest_sha256") != source_manifest_sha256
            or result.get("batch_plan_sha256") != batch_plan_sha256
            or result.get("proposal_bundle_sha256") != proposal_bundle_sha256
            or result.get("input_bundle_sha256") != input_sha
            or not isinstance(auditor, Mapping)
            or auditor.get("provider") != "Anthropic"
            or not _is_opus_5_max(auditor.get("model"))
            or auditor.get("role") != "OPUS"
            or auditor.get("independent_source_only") is not True
        ):
            raise S1FModelBlocked(f"Opus result batch binding/identity invalid: {batch['batch_id']}")
        audits = result.get("audits")
        actual_ids = [str(row.get("packet_id")) for row in audits or [] if isinstance(row, Mapping)]
        if not isinstance(audits, list) or actual_ids != batch["packet_ids"]:
            raise S1FModelBlocked(f"Opus result packet order changed: {batch['batch_id']}")
        for row in audits:
            assessment = row.get("relationship_assessment") if isinstance(row, Mapping) else None
            if (
                row.get("auditor_role") != "OPUS"
                or not isinstance(assessment, Mapping)
                or set(assessment) != RELATIONSHIPS
                or row["packet_id"] in audit_by_id
            ):
                raise S1FModelBlocked(f"Opus audit shape/identity invalid: {row.get('packet_id')}")
            audit_by_id[str(row["packet_id"])] = row
        if result.get("relationships") not in (None, []):
            raise S1FModelBlocked("batch-local relationship edges forbidden before all70 reconciliation")
        result_hashes.append(logical_sha(result))
    audits = [audit_by_id[str(packet["packet_id"])] for packet in packets]
    merged = {
        "schema": AUDIT_SCHEMA,
        "source_manifest_sha256": source_manifest_sha256,
        "batch_plan_sha256": batch_plan_sha256,
        "proposal_bundle_sha256": proposal_bundle_sha256,
        "batch_result_logical_sha256s": result_hashes,
        "audit_count": REQUIRED_PACKET_COUNT,
        "audits": audits,
        "relationships_pending": "REQUIRED_FINAL_ALL70_RECONCILIATION",
    }
    _assert_no_transport_leak(merged)
    return merged


def build_relationship_input(
    *, grok_inputs: Sequence[Mapping[str, Any]], proposal_bundle: Mapping[str, Any],
    audit_bundle: Mapping[str, Any], proposal_bundle_sha256: str, audit_bundle_sha256: str,
) -> dict[str, Any]:
    proposals = {str(row["packet_id"]): row for row in proposal_bundle.get("proposals") or [] if isinstance(row, Mapping)}
    audits = {str(row["packet_id"]): row for row in audit_bundle.get("audits") or [] if isinstance(row, Mapping)}
    rows: list[dict[str, Any]] = []
    for grok_input in grok_inputs:
        for row in grok_input.get("packets") or []:
            packet = row.get("packet") if isinstance(row, Mapping) else None
            packet_id = str(packet.get("packet_id")) if isinstance(packet, Mapping) else ""
            if packet_id not in proposals or packet_id not in audits:
                raise S1FModelBlocked(f"all70 reconciliation input missing packet: {packet_id}")
            source_documents = row.get("source_documents") if isinstance(row, Mapping) else None
            if not isinstance(source_documents, list):
                raise S1FModelBlocked(f"all70 document inventory missing: {packet_id}")
            inventory = [
                {key: document.get(key) for key in (
                    "document_id", "document_name", "document_sha256", "byte_length",
                    "source_role", "canonical_document_role",
                )}
                for document in source_documents if isinstance(document, Mapping)
            ]
            compact_packet = {
                key: packet.get(key) for key in (
                    "slot", "packet_id", "cik", "accession", "accepted_at", "filed_on",
                    "issuer", "filing", "clocks", "lineage", "retrieval_stratum", "selection_key",
                )
            }
            rows.append({
                "packet": compact_packet,
                "document_inventory": inventory,
                "grok_proposal": proposals[packet_id],
                "opus_audit": audits[packet_id],
            })
    rows.sort(key=lambda row: int(row["packet"]["slot"]))
    if len(rows) != REQUIRED_PACKET_COUNT or [int(row["packet"]["slot"]) for row in rows] != list(range(1, 71)):
        raise S1FModelBlocked("all70 relationship input order/cardinality mismatch")
    value = {
        "schema": RELATION_INPUT_SCHEMA,
        "source_manifest_sha256": audit_bundle["source_manifest_sha256"],
        "batch_plan_sha256": audit_bundle["batch_plan_sha256"],
        "proposal_bundle_sha256": proposal_bundle_sha256,
        "audit_bundle_sha256": audit_bundle_sha256,
        "packet_count": REQUIRED_PACKET_COUNT,
        "required_scope": ["amendment", "duplicate", "pulse", "mitigation", "resolution", "episode"],
        "required_output": {
            "reviewed_packet_ids": "EXACT_GLOBAL_SLOT_ORDER_1_TO_70",
            "resolution_matrix": "EVERY_PACKET_RESOLVED",
            "final_relationship_assessments": "EXACTLY_ONE_TERMINAL_SIX-KIND_ASSESSMENT_PER_PACKET",
            "semantic_repairs": "FORBIDDEN",
            "unresolved_count": 0,
            "edge_evidence": "EXACT_ALREADY_CITED_SPAN_ONLY",
        },
        "packets": rows,
    }
    _assert_no_transport_leak(value)
    return value


def finalize_all70(
    *, packets: Sequence[Mapping[str, Any]], proposal_bundle: Mapping[str, Any],
    audit_bundle: Mapping[str, Any], reconciliation: Mapping[str, Any],
    proposal_bundle_sha256: str, audit_bundle_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reconciler = reconciliation.get("reconciler")
    expected_ids = [str(row["packet_id"]) for row in packets]
    allowed_reconciliation_keys = {
        "schema", "source_manifest_sha256", "batch_plan_sha256",
        "proposal_bundle_sha256", "audit_bundle_sha256", "reconciler",
        "reviewed_packet_ids", "all70_complete", "unresolved_count",
        "resolution_matrix", "final_relationship_assessments", "relationships",
    }
    if set(reconciliation) != allowed_reconciliation_keys:
        raise S1FModelBlocked("final all70 relationship reconciliation fields invalid")
    resolution_matrix = reconciliation.get("resolution_matrix")
    resolution_ids = [
        str(row.get("packet_id")) for row in resolution_matrix or []
        if isinstance(row, Mapping) and row.get("resolution") == "RESOLVED"
    ]
    resolution_rows_valid = all(
        isinstance(row, Mapping)
        and set(row) == {"packet_id", "resolution"}
        and row.get("resolution") == "RESOLVED"
        for row in resolution_matrix or []
    )
    final_assessments = reconciliation.get("final_relationship_assessments")
    final_assessment_ids = [
        str(row.get("packet_id")) for row in final_assessments or []
        if isinstance(row, Mapping)
    ]
    if (
        reconciliation.get("schema") != RELATION_SCHEMA
        or reconciliation.get("source_manifest_sha256") != audit_bundle.get("source_manifest_sha256")
        or reconciliation.get("batch_plan_sha256") != audit_bundle.get("batch_plan_sha256")
        or reconciliation.get("proposal_bundle_sha256") != proposal_bundle_sha256
        or reconciliation.get("audit_bundle_sha256") != audit_bundle_sha256
        or reconciliation.get("reviewed_packet_ids") != expected_ids
        or reconciliation.get("all70_complete") is not True
        or reconciliation.get("unresolved_count") != 0
        or not isinstance(resolution_matrix, list)
        or len(resolution_matrix) != REQUIRED_PACKET_COUNT
        or not resolution_rows_valid
        or resolution_ids != expected_ids
        or not isinstance(final_assessments, list)
        or len(final_assessments) != REQUIRED_PACKET_COUNT
        or final_assessment_ids != expected_ids
        or not isinstance(reconciler, Mapping)
        or reconciler.get("provider") != "Anthropic"
        or not _is_opus_5_max(reconciler.get("model"))
        or reconciler.get("role") != "OPUS"
        or reconciler.get("independent_source_only") is not True
    ):
        raise S1FModelBlocked("final all70 relationship reconciliation binding/identity invalid")
    proposals, audits, relationships = (
        proposal_bundle.get("proposals"), audit_bundle.get("audits"), reconciliation.get("relationships")
    )
    if not all(isinstance(value, list) for value in (proposals, audits, relationships)):
        raise S1FModelBlocked("final all70 proposal/audit/relationship rows missing")
    assessment_by_id: dict[str, Mapping[str, Any]] = {}
    for row in final_assessments:
        assessment = row.get("relationship_assessment") if isinstance(row, Mapping) else None
        if (
            not isinstance(row, Mapping)
            or set(row) != {"packet_id", "relationship_assessment"}
            or not isinstance(assessment, Mapping)
            or set(assessment) != RELATIONSHIPS
        ):
            raise S1FModelBlocked(f"final relationship assessment incomplete: {row.get('packet_id') if isinstance(row, Mapping) else None}")
        assessment_by_id[str(row["packet_id"])] = assessment
    reconciled_audits = [
        dict(row) | {"relationship_assessment": assessment_by_id[str(row["packet_id"])]}
        for row in audits
    ]
    result = validate_s1f_audit(packets, proposals, reconciled_audits, relationships)
    if not result.ok:
        raise S1FModelBlocked(canonical_json({"audit_refusals": result.refusals}))
    verdicts = Counter(str(row.get("verdict")) for row in audits if isinstance(row, Mapping))
    disagreements = [
        {"packet_id": row.get("packet_id"), **dict(item)}
        for row in audits if isinstance(row, Mapping)
        for item in row.get("disagreements") or [] if isinstance(item, Mapping)
    ]
    summary = {
        "packet_count": REQUIRED_PACKET_COUNT,
        "audit_verdicts": dict(sorted(verdicts.items())),
        "typed_states": result.typed_states,
        "disagreement_count": len(disagreements),
        "unresolved_disagreement_count": 0,
        "economic_episode_count": len(result.episodes),
        "episode_ids": list(result.episodes),
        "relationship_counts": dict(sorted(Counter(str(row.get("kind")) for row in relationships if isinstance(row, Mapping)).items())),
    }
    matrix = {
        "schema": "mastermind.dislocation_p0.s1f_disagreement_matrix.v1",
        "source_manifest_sha256": audit_bundle["source_manifest_sha256"],
        "proposal_bundle_sha256": proposal_bundle_sha256,
        "audit_bundle_sha256": audit_bundle_sha256,
        "relationship_reconciliation_sha256": logical_sha(reconciliation),
        "items": disagreements,
        "unresolved_count": 0,
    }
    return summary, matrix


def prepare(argv: argparse.Namespace) -> dict[str, Any]:
    packets = load_packets(argv.packet_index, argv.source_root)
    source_manifest = _read_json(argv.source_manifest)
    source_sha = validate_source_manifest_binding(source_manifest, packets)
    packets = enrich_packets_from_source_manifest(source_manifest, packets)
    batch_plan = _read_json(argv.batch_plan)
    batches = validate_batch_plan(batch_plan, packets)
    catalog = build_evidence_catalog(packets)
    inputs = build_grok_inputs(
        packets=packets, batches=batches, catalog=catalog,
        source_manifest_sha256=source_sha, batch_plan_sha256=str(batch_plan["batch_plan_sha256"]),
    )
    _write_json(argv.out_dir / "S1F_EVIDENCE_CATALOG.json", catalog)
    bundle_hashes: list[str] = []
    bundle_lengths: list[int] = []
    for row in inputs:
        target = argv.out_dir / f"S1F_GROK_INPUT_B{int(row['batch_number']):02d}.json"
        _write_json(target, row)
        bundle_hashes.append(file_sha(target))
        bundle_lengths.append(target.stat().st_size)
    receipt = {
        "status": "EXACT70_SOURCE_ONLY_GROK_INPUTS_READY",
        "source_manifest_sha256": source_sha,
        "batch_plan_sha256": batch_plan["batch_plan_sha256"],
        "evidence_catalog_sha256": logical_sha(catalog),
        "grok_input_bundle_file_sha256s": bundle_hashes,
        "grok_input_bundle_byte_lengths": bundle_lengths,
        "grok_input_batch_document_counts": [len(row["document_store"]) for row in inputs],
        "grok_input_utf8_document_counts": [sum("source_utf8" in document for document in row["document_store"]) for row in inputs],
        "grok_input_binary_base64_document_counts": [sum("source_base64" in document for document in row["document_store"]) for row in inputs],
        "max_model_batch_bytes_exclusive": MAX_MODEL_BATCH_BYTES,
        "packet_count": REQUIRED_PACKET_COUNT,
        "batch_count": REQUIRED_BATCH_COUNT,
        "network": "NONE",
    }
    _write_json(argv.out_dir / "S1F_MODEL_TRANSPORT_RECEIPT.json", receipt)
    return receipt


def _load_common(argv: argparse.Namespace) -> tuple[list[dict[str, Any]], Mapping[str, Any], str, Mapping[str, Any], list[dict[str, Any]]]:
    packets = load_packets(argv.packet_index, argv.source_root)
    source_manifest = _read_json(argv.source_manifest)
    source_sha = validate_source_manifest_binding(source_manifest, packets)
    packets = enrich_packets_from_source_manifest(source_manifest, packets)
    batch_plan = _read_json(argv.batch_plan)
    batches = validate_batch_plan(batch_plan, packets)
    return packets, source_manifest, source_sha, batch_plan, batches


def _exact_inputs(paths: Sequence[Path], expected: Sequence[Mapping[str, Any]], label: str) -> tuple[list[Mapping[str, Any]], list[str]]:
    if len(paths) != REQUIRED_BATCH_COUNT:
        raise S1FModelBlocked(f"{label} requires exactly seven input files")
    actual = [_read_json(path) for path in paths]
    if actual != list(expected):
        raise S1FModelBlocked(f"{label} files do not reproduce frozen transport")
    return actual, [file_sha(path) for path in paths]


def _validate_merged_proposal(
    proposal: Mapping[str, Any], packets: Sequence[Mapping[str, Any]], source_sha: str,
    batch_plan_sha: str,
) -> None:
    if (
        proposal.get("schema") != PROPOSAL_SCHEMA
        or proposal.get("source_manifest_sha256") != source_sha
        or proposal.get("batch_plan_sha256") != batch_plan_sha
        or proposal.get("proposal_count") != REQUIRED_PACKET_COUNT
        or proposal.get("relationship_hypotheses") != []
    ):
        raise S1FModelBlocked("merged Grok proposal bundle binding invalid")
    rows = proposal.get("proposals")
    if not isinstance(rows, list) or [str(row.get("packet_id")) for row in rows if isinstance(row, Mapping)] != [str(row["packet_id"]) for row in packets]:
        raise S1FModelBlocked("merged Grok proposal order/cardinality invalid")
    result = validate_s1f_proposals(packets, rows)
    if not result.ok:
        raise S1FModelBlocked(canonical_json({"proposal_refusals": result.refusals}))
    _assert_no_transport_leak(proposal)


def merge_grok_stage(argv: argparse.Namespace) -> dict[str, Any]:
    packets, _manifest, source_sha, plan, batches = _load_common(argv)
    catalog = build_evidence_catalog(packets)
    expected_inputs = build_grok_inputs(
        packets=packets, batches=batches, catalog=catalog,
        source_manifest_sha256=source_sha, batch_plan_sha256=str(plan["batch_plan_sha256"]),
    )
    grok_inputs, input_hashes = _exact_inputs(argv.grok_input, expected_inputs, "Grok")
    results = [_read_json(path) for path in argv.grok_result]
    proposal = merge_grok_results(
        packets=packets, batches=batches, results=results,
        input_bundle_sha256s=input_hashes, source_manifest_sha256=source_sha,
        batch_plan_sha256=str(plan["batch_plan_sha256"]),
    )
    argv.out_dir.mkdir(parents=True, exist_ok=True)
    proposal_path = argv.out_dir / "S1F_GROK_SOURCE_PROPOSALS.json"
    _write_json(proposal_path, proposal)
    proposal_sha = file_sha(proposal_path)
    opus_inputs = build_opus_inputs(
        grok_inputs=grok_inputs, proposal_bundle=proposal,
        proposal_bundle_sha256=proposal_sha,
    )
    opus_hashes: list[str] = []
    for row in opus_inputs:
        target = argv.out_dir / f"S1F_OPUS_INPUT_B{int(row['batch_number']):02d}.json"
        _write_json(target, row)
        opus_hashes.append(file_sha(target))
    receipt = {
        "status": "EXACT70_GROK_VALID_OPUS_INPUTS_READY",
        "source_manifest_sha256": source_sha,
        "batch_plan_sha256": plan["batch_plan_sha256"],
        "grok_proposal_bundle_file_sha256": proposal_sha,
        "grok_result_batch_file_sha256s": [file_sha(path) for path in argv.grok_result],
        "opus_input_bundle_file_sha256s": opus_hashes,
        "packet_count": REQUIRED_PACKET_COUNT,
        "network": "NONE",
    }
    _write_json(argv.out_dir / "S1F_GROK_MERGE_RECEIPT.json", receipt)
    return receipt


def merge_opus_stage(argv: argparse.Namespace) -> dict[str, Any]:
    packets, _manifest, source_sha, plan, batches = _load_common(argv)
    catalog = build_evidence_catalog(packets)
    expected_grok_inputs = build_grok_inputs(
        packets=packets, batches=batches, catalog=catalog,
        source_manifest_sha256=source_sha, batch_plan_sha256=str(plan["batch_plan_sha256"]),
    )
    grok_inputs, _grok_hashes = _exact_inputs(argv.grok_input, expected_grok_inputs, "Grok")
    proposal = _read_json(argv.proposal)
    proposal_sha = file_sha(argv.proposal)
    _validate_merged_proposal(proposal, packets, source_sha, str(plan["batch_plan_sha256"]))
    expected_opus_inputs = build_opus_inputs(
        grok_inputs=grok_inputs, proposal_bundle=proposal,
        proposal_bundle_sha256=proposal_sha,
    )
    _opus_inputs, opus_input_hashes = _exact_inputs(argv.opus_input, expected_opus_inputs, "Opus")
    results = [_read_json(path) for path in argv.opus_result]
    audit = merge_opus_results(
        packets=packets, batches=batches, results=results,
        input_bundle_sha256s=opus_input_hashes, source_manifest_sha256=source_sha,
        batch_plan_sha256=str(plan["batch_plan_sha256"]), proposal_bundle_sha256=proposal_sha,
    )
    argv.out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = argv.out_dir / "S1F_OPUS_INDEPENDENT_AUDIT.json"
    _write_json(audit_path, audit)
    audit_sha = file_sha(audit_path)
    relation_input = build_relationship_input(
        grok_inputs=grok_inputs, proposal_bundle=proposal, audit_bundle=audit,
        proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
    )
    relation_path = argv.out_dir / "S1F_ALL70_RELATIONSHIP_INPUT.json"
    _write_json(relation_path, relation_input)
    receipt = {
        "status": "EXACT70_OPUS_AUDIT_VALID_ALL70_RECONCILIATION_READY",
        "source_manifest_sha256": source_sha,
        "grok_proposal_bundle_file_sha256": proposal_sha,
        "opus_audit_bundle_file_sha256": audit_sha,
        "opus_result_batch_file_sha256s": [file_sha(path) for path in argv.opus_result],
        "all70_relationship_input_file_sha256": file_sha(relation_path),
        "packet_count": REQUIRED_PACKET_COUNT,
        "network": "NONE",
    }
    _write_json(argv.out_dir / "S1F_OPUS_MERGE_RECEIPT.json", receipt)
    return receipt


def finalize_stage(argv: argparse.Namespace) -> dict[str, Any]:
    packets, _manifest, source_sha, plan, _batches = _load_common(argv)
    proposal, audit, reconciliation = (_read_json(path) for path in (argv.proposal, argv.audit, argv.reconciliation))
    proposal_sha, audit_sha, reconciliation_sha = (file_sha(path) for path in (argv.proposal, argv.audit, argv.reconciliation))
    _validate_merged_proposal(proposal, packets, source_sha, str(plan["batch_plan_sha256"]))
    if (
        audit.get("schema") != AUDIT_SCHEMA
        or audit.get("source_manifest_sha256") != source_sha
        or audit.get("batch_plan_sha256") != plan["batch_plan_sha256"]
        or audit.get("proposal_bundle_sha256") != proposal_sha
        or audit.get("audit_count") != REQUIRED_PACKET_COUNT
    ):
        raise S1FModelBlocked("merged Opus audit bundle binding invalid")
    summary, matrix = finalize_all70(
        packets=packets, proposal_bundle=proposal, audit_bundle=audit,
        reconciliation=reconciliation, proposal_bundle_sha256=proposal_sha,
        audit_bundle_sha256=audit_sha,
    )
    argv.out_dir.mkdir(parents=True, exist_ok=True)
    linkage = {
        "schema": "mastermind.dislocation_p0.s1f_episode_linkage.v1",
        "source_manifest_sha256": source_sha,
        "proposal_bundle_sha256": proposal_sha,
        "audit_bundle_sha256": audit_sha,
        "relationship_reconciliation_file_sha256": reconciliation_sha,
        "economic_episode_count": summary["economic_episode_count"],
        "episode_ids": summary["episode_ids"],
        "relationships": reconciliation.get("relationships") or [],
        "final_relationship_assessments": reconciliation.get("final_relationship_assessments") or [],
    }
    disagreement_path = argv.out_dir / "S1F_DISAGREEMENT_MATRIX.json"
    linkage_path = argv.out_dir / "S1F_EPISODE_LINKAGE.json"
    _write_json(disagreement_path, matrix)
    _write_json(linkage_path, linkage)
    receipt = {
        "status": "EXACT70_SOURCE_ONLY_SEMANTIC_AUDIT_LINKAGE_COMPLETE",
        "source_manifest_sha256": source_sha,
        "grok_proposal_bundle_file_sha256": proposal_sha,
        "opus_audit_bundle_file_sha256": audit_sha,
        "relationship_reconciliation_file_sha256": reconciliation_sha,
        "episode_linkage_file_sha256": file_sha(linkage_path),
        "disagreement_matrix_file_sha256": file_sha(disagreement_path),
        "summary": summary,
        "stop_before": "P0-S2",
        "network": "NONE",
    }
    _write_json(argv.out_dir / "S1F_SEMANTIC_COMPLETION_RECEIPT.json", receipt)
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="stage", required=True)
    for stage in ("prepare", "merge-grok", "merge-opus", "finalize"):
        child = subparsers.add_parser(stage)
        child.add_argument("--packet-index", type=Path, required=True)
        child.add_argument("--source-root", type=Path, required=True)
        child.add_argument("--source-manifest", type=Path, required=True)
        child.add_argument("--batch-plan", type=Path, required=True)
        child.add_argument("--out-dir", type=Path, required=True)
        if stage in {"merge-grok", "merge-opus"}:
            child.add_argument("--grok-input", type=Path, action="append", required=True)
        if stage == "merge-grok":
            child.add_argument("--grok-result", type=Path, action="append", required=True)
        if stage in {"merge-opus", "finalize"}:
            child.add_argument("--proposal", type=Path, required=True)
        if stage == "merge-opus":
            child.add_argument("--opus-input", type=Path, action="append", required=True)
            child.add_argument("--opus-result", type=Path, action="append", required=True)
        if stage == "finalize":
            child.add_argument("--audit", type=Path, required=True)
            child.add_argument("--reconciliation", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        handler = {
            "prepare": prepare,
            "merge-grok": merge_grok_stage,
            "merge-opus": merge_opus_stage,
            "finalize": finalize_stage,
        }[args.stage]
        print(canonical_json(handler(args)))
        return 0
    except Exception as exc:  # noqa: BLE001 - one typed, fail-closed CLI receipt.
        print(canonical_json({"status": "BLOCKED", "blocker": type(exc).__name__, "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
