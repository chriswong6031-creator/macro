#!/usr/bin/env python3
"""Replay frozen S1F source packets through deterministic shadow triage only.

This runner consumes the complete owner-replay packet bytes, validates every
frozen selection/owner/ruleset binding, and calls the already-frozen
``triage_packet`` for every one of the exact 70 source packets.  It creates no
model, audit, semantic proposal, economic episode, or market-data input.

The emitted shadow result is deliberately not an input to the separate
source-only review bundle.  A future independent reviewer can receive the
bundle plan and exact owner bytes without receiving this triage's conclusion.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research.dislocation_p0_a1_lib import canonical_json
from scripts.research.dislocation_p0_s1f_selection import AUTHORITY, STRATA
from scripts.research.dislocation_p0_s1f_triage import (
    FORBIDDEN,
    FROZEN_RULESET_CANONICAL_SHA256,
    TriageBlocked,
    load_ruleset,
    triage_packet,
)


ROOT = Path(__file__).resolve().parents[2]
PACKET_COUNT = 70
EXACT_FTS_DOCUMENT_COUNT = 129
MANIFEST_LOGICAL_SHA256 = "98740d5aeee8e0e3ae3bb8408498b72db839cdc3686b8b3994b416c99cd7a3e4"
MANIFEST_FILE_SHA256 = "25d3c0482959c150ce676bac7051cc51073f63bd67e367254eb5b7d59ce0f947"
RULESET_FILE_SHA256 = "fda0746260e1d6faa3d96164032a6f6ae7d97e3d222e28a2c3ca9c432035b0af"
FORBIDDEN_SOURCE_MOUNT_NAMES = frozenset({
    "price", "prices", "market", "markets", "outcome", "outcomes", "ranking",
    "rank", "score", "sizing", "execution", "trade", "trades", "episode", "episodes",
})


class ShadowTriageBlocked(RuntimeError):
    """A frozen source-only shadow triage binding was not proven."""


def _digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShadowTriageBlocked(f"S1F_SHADOW_{label}_UNREADABLE") from exc
    if not isinstance(value, Mapping):
        raise ShadowTriageBlocked(f"S1F_SHADOW_{label}_NOT_OBJECT")
    return value


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ShadowTriageBlocked(code)


def _hash_bound(value: Mapping[str, Any], field: str, code: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    _require(isinstance(claimed, str) and claimed == _digest(body), code)


def _safe_relative(value: Any, code: str) -> Path:
    _require(isinstance(value, str) and value.endswith(".source"), code)
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts, code)
    return path


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in FORBIDDEN or _contains_forbidden(child) for key, child in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden(child) for child in value)
    return False


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((canonical_json(value) + "\n").encode("utf-8"))


def _validate_authority(*values: Mapping[str, Any]) -> None:
    for value in values:
        _require(value.get("authority") == AUTHORITY, "S1F_SHADOW_AUTHORITY_NOT_ALL_FALSE")


def _validate_frozen_artifacts(
    *, manifest_path: Path, selection_path: Path, receipt_path: Path,
    batch_path: Path, replay_path: Path, ruleset_path: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], str]:
    manifest = _read_json(manifest_path, "MANIFEST")
    selection = _read_json(selection_path, "SELECTION")
    receipt = _read_json(receipt_path, "RECEIPT")
    batch = _read_json(batch_path, "BATCH")
    replay = _read_json(replay_path, "REPLAY")
    ruleset = _read_json(ruleset_path, "RULESET")
    _require(_file_sha256(manifest_path) == MANIFEST_FILE_SHA256, "S1F_SHADOW_MANIFEST_FILE_HASH_MISMATCH")
    _hash_bound(manifest, "manifest_sha256", "S1F_SHADOW_MANIFEST_LOGICAL_HASH_MISMATCH")
    _require(manifest.get("manifest_sha256") == MANIFEST_LOGICAL_SHA256, "S1F_SHADOW_MANIFEST_LOGICAL_HASH_MISMATCH")
    _require(manifest.get("schema") == "mastermind.dislocation_p0.s1f_canonical_source_packets.v1", "S1F_SHADOW_MANIFEST_SCHEMA_MISMATCH")
    _require(manifest.get("status") == "COMPLETE" and manifest.get("n") == PACKET_COUNT, "S1F_SHADOW_MANIFEST_CARDINALITY_MISMATCH")
    _hash_bound(selection, "manifest_sha256", "S1F_SHADOW_SELECTION_HASH_MISMATCH")
    _hash_bound(receipt, "receipt_sha256", "S1F_SHADOW_RECEIPT_HASH_MISMATCH")
    _hash_bound(batch, "batch_plan_sha256", "S1F_SHADOW_BATCH_HASH_MISMATCH")
    _require(selection.get("schema") == "mastermind.dislocation_p0.s1f_exact70_source_manifest.v1", "S1F_SHADOW_SELECTION_SCHEMA_MISMATCH")
    _require(selection.get("n") == PACKET_COUNT and isinstance(selection.get("candidates"), list) and len(selection["candidates"]) == PACKET_COUNT, "S1F_SHADOW_SELECTION_CARDINALITY_MISMATCH")
    _require(selection.get("selection_identity") == ["cik", "accession"] and selection.get("strata") == list(STRATA), "S1F_SHADOW_SELECTION_IDENTITY_BINDING_MISMATCH")
    _require(receipt.get("status") == "COMPLETE" and receipt.get("selection_count") == PACKET_COUNT and receipt.get("selection_identity_count") == PACKET_COUNT, "S1F_SHADOW_RECEIPT_CARDINALITY_MISMATCH")
    _require(receipt.get("selection_manifest_sha256") == selection.get("manifest_sha256"), "S1F_SHADOW_RECEIPT_SELECTION_BINDING_MISMATCH")
    _require(receipt.get("batch_plan_sha256") == batch.get("batch_plan_sha256"), "S1F_SHADOW_RECEIPT_BATCH_BINDING_MISMATCH")
    _require(manifest.get("selection_manifest_sha256") == selection.get("manifest_sha256") and manifest.get("selection_receipt_sha256") == receipt.get("receipt_sha256") and manifest.get("batch_plan_sha256") == batch.get("batch_plan_sha256"), "S1F_SHADOW_OWNER_SELECTION_BINDING_MISMATCH")
    _require(batch.get("schema") == "mastermind.dislocation_p0.s1f_exact70_audit_batch_plan.v1" and batch.get("batch_order") == [entry.get("batch_id") for entry in batch.get("batches", []) if isinstance(entry, Mapping)], "S1F_SHADOW_BATCH_SCHEMA_OR_ORDER_MISMATCH")
    _require(isinstance(batch.get("batches"), list) and len(batch["batches"]) == len(STRATA), "S1F_SHADOW_BATCH_CARDINALITY_MISMATCH")
    _require(replay.get("schema") == "mastermind.dislocation_p0.s1f_canonical_owner_replay_proof.v1" and replay.get("status") == "COMPLETE_BYTE_IDENTICAL", "S1F_SHADOW_REPLAY_STATUS_MISMATCH")
    _require(replay.get("packet_count") == PACKET_COUNT and replay.get("document_count") == 183 and replay.get("network_access") == "NONE", "S1F_SHADOW_REPLAY_CARDINALITY_MISMATCH")
    _require(replay.get("frozen_manifest_sha256") == MANIFEST_LOGICAL_SHA256 and replay.get("replayed_manifest_sha256") == MANIFEST_LOGICAL_SHA256, "S1F_SHADOW_REPLAY_MANIFEST_BINDING_MISMATCH")
    _require(manifest.get("firewall") == {"forbidden_dirs_present": [], "official_sec_hosts": ["data.sec.gov", "www.sec.gov"]}, "S1F_SHADOW_MANIFEST_FIREWALL_MISMATCH")
    _require(replay.get("forbidden_dirs_present") == [] and replay.get("official_sec_hosts") == ["data.sec.gov", "www.sec.gov"], "S1F_SHADOW_REPLAY_FIREWALL_MISMATCH")
    _validate_authority(manifest, selection, receipt, batch, ruleset)
    _require(_file_sha256(ruleset_path) == RULESET_FILE_SHA256, "S1F_SHADOW_RULESET_FILE_HASH_MISMATCH")
    loaded, ruleset_sha = load_ruleset(ruleset)
    _require(ruleset_sha == FROZEN_RULESET_CANONICAL_SHA256 and ruleset_sha == _digest(ruleset), "S1F_SHADOW_RULESET_LOGICAL_HASH_MISMATCH")
    _require(loaded == ruleset, "S1F_SHADOW_RULESET_LOAD_DRIFT")
    return manifest, selection, receipt, batch, replay, ruleset_sha


def _validate_batch_identities(batch: Mapping[str, Any], expected: Sequence[tuple[str, str]]) -> None:
    flattened: list[tuple[str, str]] = []
    for expected_stratum, group in zip(STRATA, batch.get("batches", ()), strict=True):
        _require(isinstance(group, Mapping) and group.get("retrieval_stratum") == expected_stratum and group.get("packet_count") == 10, "S1F_SHADOW_BATCH_GROUP_MISMATCH")
        packets = group.get("packets")
        _require(isinstance(packets, list) and len(packets) == 10, "S1F_SHADOW_BATCH_GROUP_CARDINALITY_MISMATCH")
        flattened.extend((str(item.get("cik") or ""), str(item.get("accession") or "")) for item in packets if isinstance(item, Mapping))
    _require(len(flattened) == PACKET_COUNT and len(set(flattened)) == PACKET_COUNT and set(flattened) == set(expected), "S1F_SHADOW_BATCH_EXACT70_IDENTITY_MISMATCH")


def _validate_source_firewall(source_root: Path) -> None:
    _require(source_root.is_dir(), "S1F_SHADOW_SOURCE_ROOT_MISSING")
    forbidden = sorted({path.name.lower() for path in source_root.rglob("*") if path.is_dir()} & FORBIDDEN_SOURCE_MOUNT_NAMES)
    _require(not forbidden, "S1F_SHADOW_SOURCE_FIREWALL_FORBIDDEN_MOUNT")


def _load_triage_packets(
    *, manifest: Mapping[str, Any], selection: Mapping[str, Any], batch: Mapping[str, Any], source_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_source_firewall(source_root)
    index = _read_json(source_root / "packet_index.json", "PACKET_INDEX")
    _require(index.get("schema") == "mastermind.dislocation_p0.s1f_model_packet_index.v1", "S1F_SHADOW_PACKET_INDEX_SCHEMA_MISMATCH")
    rows = index.get("packets")
    public = manifest.get("packets")
    selected = selection.get("candidates")
    _require(isinstance(rows, list) and isinstance(public, list) and isinstance(selected, list) and len(rows) == len(public) == len(selected) == PACKET_COUNT, "S1F_SHADOW_PACKET_INDEX_CARDINALITY_MISMATCH")
    expected_ids = [f"s1f_packet_{item.get('selection_key')}" for item in selected]
    expected_identity = [(str(item.get("cik") or ""), str(item.get("accession") or "")) for item in selected]
    _require(len(set(expected_ids)) == PACKET_COUNT and len(set(expected_identity)) == PACKET_COUNT and all(all(item) for item in expected_identity), "S1F_SHADOW_SELECTION_EXACT70_IDENTITY_MISMATCH")
    _validate_batch_identities(batch, expected_identity)
    triage_packets: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []
    expected_paths: set[Path] = set()
    exact_document_count = 0
    primary_count = 0
    for slot, (model, packet, candidate, expected_id, identity) in enumerate(zip(rows, public, selected, expected_ids, expected_identity, strict=True), start=1):
        _require(isinstance(model, Mapping) and isinstance(packet, Mapping) and isinstance(candidate, Mapping), "S1F_SHADOW_PACKET_ROW_MALFORMED")
        _require(model.get("slot") == packet.get("slot") == slot and model.get("packet_id") == packet.get("packet_id") == expected_id, "S1F_SHADOW_PACKET_ORDER_MISMATCH")
        filing = packet.get("filing"); issuer = packet.get("issuer"); clocks = packet.get("clocks")
        _require(isinstance(filing, Mapping) and isinstance(issuer, Mapping) and isinstance(clocks, Mapping), "S1F_SHADOW_PACKET_METADATA_MALFORMED")
        _require((str(issuer.get("cik") or ""), str(filing.get("accession") or "")) == identity == (str(model.get("cik") or ""), str(model.get("accession") or "")), "S1F_SHADOW_PACKET_IDENTITY_MISMATCH")
        accepted_at = clocks.get("accepted_at")
        _require(isinstance(accepted_at, str) and accepted_at == model.get("accepted_at"), "S1F_SHADOW_ACCEPTED_AT_MISMATCH")
        try:
            parsed = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ShadowTriageBlocked("S1F_SHADOW_ACCEPTED_AT_INVALID") from exc
        _require(parsed.tzinfo is not None, "S1F_SHADOW_ACCEPTED_AT_INVALID")
        _require(packet.get("primary_document_substitution") is False and model.get("primary_document_substitution") is False, "S1F_SHADOW_PRIMARY_SUBSTITUTION")
        query_edges = packet.get("query_edges")
        matched = packet.get("matched_documents")
        model_docs = model.get("documents")
        _require(isinstance(query_edges, list) and query_edges and isinstance(matched, list) and matched and isinstance(model_docs, list) and len(matched) == len(model_docs), "S1F_SHADOW_EXACT_FTS_BINDING_MALFORMED")
        by_id = {str(doc.get("document_id") or ""): doc for doc in matched if isinstance(doc, Mapping)}
        _require(len(by_id) == len(matched), "S1F_SHADOW_DUPLICATE_MATCHED_DOCUMENT")
        docs: dict[str, bytes] = {}
        exact: list[dict[str, Any]] = []
        names: set[str] = set()
        for listed in model_docs:
            _require(isinstance(listed, Mapping), "S1F_SHADOW_PACKET_INDEX_DOCUMENT_MALFORMED")
            doc_id = str(listed.get("document_id") or "")
            declared = by_id.get(doc_id)
            _require(declared is not None and all(listed.get(key) == declared.get({"document_sha256": "content_sha256", "document_name": "document_name", "byte_length": "byte_length"}[key]) for key in ("document_sha256", "document_name", "byte_length")), "S1F_SHADOW_PACKET_INDEX_DOCUMENT_BINDING_MISMATCH")
            relative = _safe_relative(listed.get("source_path"), "S1F_SHADOW_PACKET_SOURCE_PATH_INVALID")
            path = source_root / relative
            _require(path.is_file(), "S1F_SHADOW_PACKET_SOURCE_PATH_MISSING")
            content = path.read_bytes()
            digest = sha256(content).hexdigest()
            _require(len(content) == listed.get("byte_length") and digest == listed.get("document_sha256"), "S1F_SHADOW_PACKET_SOURCE_BYTE_HASH_MISMATCH")
            expected_paths.add(relative); docs[digest] = content; names.add(str(listed["document_name"])); exact_document_count += 1
            phrases = sorted({str(edge.get("phrase") or "") for edge in query_edges if isinstance(edge, Mapping) and edge.get("filename") == listed.get("document_name")})
            _require(phrases and all(phrase.isascii() for phrase in phrases), "S1F_SHADOW_EXACT_FTS_QUERY_BINDING_MISMATCH")
            exact.append({"filename": listed["document_name"], "document_sha256": digest, "query_phrases": phrases})
        _require(all(isinstance(edge, Mapping) and edge.get("filename") in names and isinstance(edge.get("phrase"), str) and edge["phrase"].isascii() for edge in query_edges), "S1F_SHADOW_EXACT_FTS_QUERY_BINDING_MISMATCH")
        primary = model.get("primary_context")
        public_primary = packet.get("primary_context")
        _require(isinstance(primary, Mapping) and isinstance(public_primary, Mapping) and primary == public_primary, "S1F_SHADOW_PRIMARY_CONTEXT_BINDING_MISMATCH")
        primary_relative = _safe_relative(primary.get("source_path"), "S1F_SHADOW_PRIMARY_SOURCE_PATH_INVALID")
        primary_path = source_root / primary_relative
        _require(primary_path.is_file(), "S1F_SHADOW_PRIMARY_SOURCE_PATH_MISSING")
        primary_bytes = primary_path.read_bytes(); primary_sha = sha256(primary_bytes).hexdigest()
        _require(len(primary_bytes) == primary.get("byte_length") and primary_sha == primary.get("document_sha256"), "S1F_SHADOW_PRIMARY_SOURCE_BYTE_HASH_MISMATCH")
        expected_paths.add(primary_relative); docs[primary_sha] = primary_bytes; primary_count += 1
        additive = [{"role": "CANONICAL_PRIMARY_CURRENT_REPORT", "document_sha256": primary_sha}]
        triage_packets.append({
            "packet_id": expected_id, "form": filing.get("base_form"), "item_codes": filing.get("items") or [],
            "accepted_at": accepted_at, "query_edges": query_edges, "exact_matched_documents": exact,
            "source_documents": docs, "additive_context_documents": additive,
        })
        source_entries.append({
            "slot": slot, "packet_id": expected_id, "cik": identity[0], "accession": identity[1],
            "accepted_at": accepted_at, "exact_matched_documents": [
                {"document_id": item["document_id"], "document_name": item["document_name"], "document_sha256": item["document_sha256"], "byte_length": item["byte_length"], "source_path": item["source_path"]}
                for item in model_docs
            ],
            "additive_primary_context": {key: primary[key] for key in ("document_id", "document_name", "document_sha256", "byte_length", "source_path", "document_type", "document_type_status")},
            "primary_document_substitution": False,
        })
    _require(exact_document_count == EXACT_FTS_DOCUMENT_COUNT, "S1F_SHADOW_EXACT_FTS_DOCUMENT_COUNT_MISMATCH")
    _require(primary_count == PACKET_COUNT, "S1F_SHADOW_PRIMARY_CONTEXT_COUNT_MISMATCH")
    actual_paths = {path.relative_to(source_root) for path in source_root.rglob("*.source")}
    _require(actual_paths == expected_paths, "S1F_SHADOW_PACKET_SOURCE_PATH_COVERAGE_MISMATCH")
    return triage_packets, source_entries


def run(
    *, manifest_path: Path, selection_path: Path, receipt_path: Path, batch_path: Path,
    replay_path: Path, ruleset_path: Path, source_root: Path, output_dir: Path,
) -> dict[str, Any]:
    """Validate and execute all frozen packets; output is byte-stable."""
    manifest, selection, receipt, batch, replay, ruleset_sha = _validate_frozen_artifacts(
        manifest_path=manifest_path, selection_path=selection_path, receipt_path=receipt_path,
        batch_path=batch_path, replay_path=replay_path, ruleset_path=ruleset_path,
    )
    triage_inputs, source_entries = _load_triage_packets(
        manifest=manifest, selection=selection, batch=batch, source_root=source_root,
    )
    results: list[dict[str, Any]] = []
    for packet in triage_inputs:
        try:
            result = triage_packet(packet)
        except TriageBlocked as exc:
            raise ShadowTriageBlocked(f"S1F_SHADOW_TRIAGE_BLOCKED:{packet['packet_id']}:{exc}") from exc
        _require(result.get("packet_id") == packet["packet_id"] and result.get("authority") == AUTHORITY and not _contains_forbidden(result), "S1F_SHADOW_TRIAGE_OUTPUT_FORBIDDEN_OR_UNBOUND")
        results.append(result)
    _require(len(results) == PACKET_COUNT and [item["packet_id"] for item in results] == [item["packet_id"] for item in triage_inputs], "S1F_SHADOW_TRIAGE_ALL70_COVERAGE_OR_ORDER_MISMATCH")
    categories = dict(sorted(Counter(item["source_context_category"] for item in results).items()))
    dispositions = dict(sorted(Counter(item["shadow_disposition"] for item in results).items()))
    rule_ids = dict(sorted(Counter(rule for item in results for rule in item["rule_ids"]).items()))
    bundle = {
        "schema": "mastermind.dislocation_p0.s1f_source_only_review_bundle_plan.v1",
        "status": "SOURCE_ONLY_REVIEW_PENDING",
        "canonical_source_manifest_sha256": manifest["manifest_sha256"],
        "canonical_source_manifest_file_sha256": _file_sha256(manifest_path),
        "exact70_selection_manifest_sha256": selection["manifest_sha256"],
        "exact70_selection_receipt_sha256": receipt["receipt_sha256"],
        "exact70_batch_plan_sha256": batch["batch_plan_sha256"],
        "owner_replay_manifest_sha256": replay["replayed_manifest_sha256"],
        "packet_count": PACKET_COUNT,
        "exact_fts_matched_document_count": EXACT_FTS_DOCUMENT_COUNT,
        "packets": source_entries,
        "shadow_triage_included": False,
        "authority": dict(AUTHORITY),
    }
    _require(not _contains_forbidden(bundle), "S1F_SHADOW_BUNDLE_FORBIDDEN_FIELD")
    bundle["bundle_plan_sha256"] = _digest(bundle)
    output = {
        "schema": "mastermind.dislocation_p0.s1f_frozen_shadow_triage.v1",
        "status": "COMPLETE_BYTE_IDENTICAL_SOURCE_ONLY",
        "canonical_source_manifest_sha256": manifest["manifest_sha256"],
        "canonical_source_manifest_file_sha256": _file_sha256(manifest_path),
        "triage_ruleset_sha256": ruleset_sha,
        "triage_ruleset_file_sha256": _file_sha256(ruleset_path),
        "exact70_selection_manifest_sha256": selection["manifest_sha256"],
        "exact70_selection_receipt_sha256": receipt["receipt_sha256"],
        "exact70_batch_plan_sha256": batch["batch_plan_sha256"],
        "owner_replay_manifest_sha256": replay["replayed_manifest_sha256"],
        "packet_count": PACKET_COUNT,
        "exact_fts_matched_document_count": EXACT_FTS_DOCUMENT_COUNT,
        "additive_primary_context_count": PACKET_COUNT,
        "primary_document_substitution": False,
        "category_counts": categories,
        "shadow_disposition_counts": dispositions,
        "rule_id_counts": rule_ids,
        "authority": dict(AUTHORITY),
        "triage": results,
    }
    _require(not _contains_forbidden(output), "S1F_SHADOW_TRIAGE_FORBIDDEN_FIELD")
    output["shadow_triage_sha256"] = _digest(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    triage_path = output_dir / "S1F_FROZEN_SHADOW_TRIAGE.json"
    bundle_path = output_dir / "S1F_SOURCE_ONLY_REVIEW_PACKET_BUNDLE_PLAN.json"
    _write_json(triage_path, output)
    _write_json(bundle_path, bundle)
    return {"triage": output, "bundle": bundle, "triage_path": triage_path, "bundle_path": bundle_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    base = ROOT / "research/dislocation_intelligence/p0_s1f"
    parser.add_argument("--manifest", type=Path, default=base / "S1F_CANONICAL_SOURCE_PACKET_MANIFEST.json")
    parser.add_argument("--selection", type=Path, default=base / "S1F_EXACT70_SOURCE_MANIFEST.json")
    parser.add_argument("--receipt", type=Path, default=base / "S1F_EXACT70_SELECTION_RECEIPT.json")
    parser.add_argument("--batch", type=Path, default=base / "S1F_EXACT70_AUDIT_BATCH_PLAN.json")
    parser.add_argument("--replay", type=Path, default=base / "S1F_CANONICAL_OWNER_REPLAY_PROOF.json")
    parser.add_argument("--ruleset", type=Path, default=base / "S1F_TRIAGE_RULESET.json")
    parser.add_argument("--source-root", type=Path, default=base / "work/source_owner_attempt2/source_packets")
    parser.add_argument("--output-dir", type=Path, default=base)
    args = parser.parse_args()
    try:
        result = run(
            manifest_path=args.manifest, selection_path=args.selection, receipt_path=args.receipt,
            batch_path=args.batch, replay_path=args.replay, ruleset_path=args.ruleset,
            source_root=args.source_root, output_dir=args.output_dir,
        )
    except ShadowTriageBlocked as exc:
        print(f"S1F_SHADOW_TRIAGE_BLOCKED:{exc}")
        return 2
    print(canonical_json({
        "status": result["triage"]["status"], "shadow_triage_sha256": result["triage"]["shadow_triage_sha256"],
        "bundle_plan_sha256": result["bundle"]["bundle_plan_sha256"], "category_counts": result["triage"]["category_counts"],
        "shadow_disposition_counts": result["triage"]["shadow_disposition_counts"], "rule_id_counts": result["triage"]["rule_id_counts"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
