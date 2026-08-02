"""Immutable local store for deterministic earnings story packets.

``earnings_evidence`` owns source intake and evidence history.  This separate
projection owns only content-addressed packet objects and an aggregate marker.
Its marker binds a precise evidence-root generation/hash while unchanged source
revisions reuse their old packet byte-for-byte.  No store operation deletes or
rewrites an object.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    EXECUTION_RECEIPT,
    MANIFEST_SCHEMA,
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    event_key,
    sha256_bytes,
    validate_manifest,
)
from .promotion import PROMOTION_POLICY_SCHEMA, load_promotion_policy, promotion_policy_sha256, validate_promotion_policy
from .story_packets import (
    STORY_PACKET_MANIFEST_SCHEMA,
    STORY_PACKET_SCHEMA,
    build_story_packet,
    evidence_receipts_from_manifest,
    load_evidence_event,
    validate_story_packet,
    validate_story_packet_manifest,
)


def _read_json_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        body = path.read_bytes()
        payload = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{label} must contain an object")
    return payload, body


def _canonical_marker(path: Path, *, label: str) -> dict[str, Any]:
    payload, body = _read_json_bytes(path, label=label)
    if body != canonical_json_bytes(payload):
        raise ContractError(f"{label} is not canonical bytes")
    return payload


def _packet_body(
    root: Path,
    receipt: Mapping[str, Any],
    *,
    policy: object,
) -> tuple[dict[str, Any], bytes]:
    object_key = str(receipt["object_key"])
    if object_key.startswith("/") or ".." in Path(object_key).parts:
        raise ContractError("unsafe story packet object key")
    payload, body = _read_json_bytes(root / object_key, label=f"story packet {object_key}")
    if body != canonical_json_bytes(payload):
        raise ContractError(f"story packet {object_key} is not canonical bytes")
    if len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
        raise ContractError(f"story packet object receipt mismatch: {object_key}")
    validate_story_packet(payload, policy=policy)
    return payload, body


def _prior_catalog(root: Path, prior_manifest: object | None) -> tuple[dict[str, Mapping[str, Any]], dict[str, tuple[dict[str, Any], bytes]], dict[str, Any] | None]:
    if prior_manifest is None:
        marker_path = root / "manifest.json"
        if not marker_path.exists():
            return {}, {}, None
        prior_manifest = _canonical_marker(marker_path, label="prior story packet marker")
    validate_story_packet_manifest(prior_manifest)
    assert isinstance(prior_manifest, Mapping)
    prior_policy = prior_manifest["policy"]["snapshot"]
    packets: dict[str, Mapping[str, Any]] = {}
    bodies: dict[str, tuple[dict[str, Any], bytes]] = {}
    for key, index in prior_manifest["packets"].items():
        assert isinstance(index, Mapping)
        receipt = prior_manifest["files"].get(index["object_key"])
        if not isinstance(receipt, Mapping):
            raise ContractError("prior story packet receipt missing")
        packet, body = _packet_body(root, receipt, policy=prior_policy)
        if packet["packet_id"] != index["packet_id"]:
            raise ContractError("prior story packet index id mismatch")
        packets[str(key)] = index
        bodies[str(key)] = (packet, body)
    return packets, bodies, dict(prior_manifest)


def _evidence_root_receipt(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    return {
        "schema": MANIFEST_SCHEMA,
        "generation_id": str(manifest["generation_id"]),
        "manifest_sha256": canonical_json_sha256(manifest),
    }


def _packet_file_receipt(packet: Mapping[str, Any], body: bytes) -> dict[str, Any]:
    digest = sha256_bytes(body)
    return {
        "sha256": digest,
        "bytes": len(body),
        "schema": STORY_PACKET_SCHEMA,
        "object_key": f"objects/{digest}.json",
    }


def _index_packet(packet: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet_id": str(packet["packet_id"]),
        "source_sha256": str(packet["digest"]["source"]["body_sha256"]),
        "story_id": str(packet["story"]["story_id"]),
        "story_revision_id": str(packet["story"]["story_revision_id"]),
        "object_key": str(receipt["object_key"]),
    }


def _packets_for_manifest(root: Path, manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Load and index-check every packet named by one immutable marker."""
    packets: dict[str, dict[str, Any]] = {}
    for key, index in manifest["packets"].items():
        receipt = manifest["files"][index["object_key"]]
        packet, _body = _packet_body(root, receipt, policy=manifest["policy"]["snapshot"])
        if (
            packet["packet_id"] != index["packet_id"]
            or event_key(packet["digest"]["event"]) != key
            or packet["digest"]["source"]["body_sha256"] != index["source_sha256"]
            or packet["story"]["story_id"] != index["story_id"]
            or packet["story"]["story_revision_id"] != index["story_revision_id"]
        ):
            raise ContractError(f"story packet index mismatch for {key}")
        packets[str(key)] = packet
    return packets


def _verify_lineage_transition(
    current: Mapping[str, Any],
    current_packets: Mapping[str, Mapping[str, Any]],
    parent: Mapping[str, Any],
    parent_packets: Mapping[str, Mapping[str, Any]],
) -> None:
    """Bind each retained correction to the exact packet in its direct parent."""
    if not set(parent["packets"]) <= set(current["packets"]):
        raise ContractError("story packet lineage shrank a packet catalog")
    for key, old_index in parent["packets"].items():
        current_index = current["packets"][key]
        if old_index["source_sha256"] == current_index["source_sha256"]:
            if old_index["packet_id"] != current_index["packet_id"]:
                raise ContractError("unchanged source revision churned a story packet")
            continue
        corrected = current_packets[key]
        prior = corrected.get("prior")
        if not isinstance(prior, Mapping):
            raise ContractError("changed source revision lacks prior packet lineage")
        if prior.get("packet_id") != old_index["packet_id"]:
            raise ContractError("corrected packet does not bind its direct parent packet id")
        old_packet = parent_packets[key]
        if canonical_json_bytes(prior.get("story")) != canonical_json_bytes(old_packet["story"]):
            raise ContractError("corrected packet prior story differs from direct parent")


def build_story_packet_generation(
    evidence_dir: str | Path,
    *,
    policy: object | None = None,
    prior_manifest: object | None = None,
    prior_store_dir: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build an immutable aggregate marker plus only newly needed packet bytes.

    A current evidence catalog is required to be non-shrinking versus the prior
    catalog.  Same event + same transcript-source SHA + same policy hash reuses
    the packet exactly; a changed transcript source receives the prior packet as
    correction lineage and therefore retains its logical story id.
    """
    evidence_root = Path(evidence_dir)
    evidence_manifest = _canonical_marker(evidence_root / "manifest.json", label="evidence root marker")
    validate_manifest(evidence_manifest)
    assert isinstance(evidence_manifest, Mapping)
    resolved_policy = load_promotion_policy() if policy is None else validate_promotion_policy(policy)
    policy_ref = {
        "schema": PROMOTION_POLICY_SCHEMA,
        "sha256": promotion_policy_sha256(resolved_policy),
        "snapshot": resolved_policy,
    }
    store_root = Path(prior_store_dir) if prior_store_dir is not None else evidence_root
    prior_index, prior_bodies, prior = _prior_catalog(store_root, prior_manifest)
    current_keys = set(evidence_manifest["events"])
    if not set(prior_index) <= current_keys:
        missing = sorted(set(prior_index) - current_keys)
        raise ContractError(f"earnings evidence root shrank; refusing story packet catalog loss: {missing[:3]}")

    packets: dict[str, dict[str, Any]] = {}
    files: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, bytes] = {}
    for key in sorted(current_keys):
        event = evidence_manifest["events"][key]
        assert isinstance(event, Mapping)
        source_sha = str(event["source_sha256"])
        prior_entry = prior_index.get(key)
        prior_packet: Mapping[str, Any] | None = None
        packet: dict[str, Any]
        body: bytes
        can_reuse = (
            prior_entry is not None
            and str(prior_entry["source_sha256"]) == source_sha
            and prior is not None
            and dict(prior["policy"]) == policy_ref
        )
        if can_reuse:
            packet, body = prior_bodies[key]
            # A packet's source receipts remain sufficient even when this
            # aggregate marker advances because unrelated evidence arrived.
            validate_story_packet(packet, policy=resolved_policy)
        else:
            _manifest, fact_pack, claim_graph, transcript = load_evidence_event(evidence_root, key=key, manifest=evidence_manifest)
            if prior_entry is not None:
                candidate = prior_bodies[key][0]
                if str(prior_entry["source_sha256"]) != source_sha:
                    prior_packet = candidate
            packet = build_story_packet(
                fact_pack,
                claim_graph,
                transcript,
                evidence=evidence_receipts_from_manifest(evidence_manifest, key=key),
                policy=resolved_policy,
                prior_packet=prior_packet,
                prior_policy=(
                    prior["policy"]["snapshot"]
                    if prior_packet is not None and prior is not None
                    else None
                ),
            )
            body = canonical_json_bytes(packet)
        receipt = _packet_file_receipt(packet, body)
        object_key = str(receipt["object_key"])
        previous_body = artifacts.get(object_key)
        if previous_body is not None and previous_body != body:
            raise ContractError(f"story packet object hash collision: {object_key}")
        artifacts[object_key] = body
        files[object_key] = receipt
        packets[key] = _index_packet(packet, receipt)

    root_receipt = _evidence_root_receipt(evidence_manifest)
    core = {
        "schema": STORY_PACKET_MANIFEST_SCHEMA,
        "authority": "context_only",
        "status": "ready",
        "evidence_root": root_receipt,
        "policy": policy_ref,
        "packets": {key: packets[key] for key in sorted(packets)},
        "files": {key: files[key] for key in sorted(files)},
        "execution": dict(EXECUTION_RECEIPT),
    }
    # An exact replay is a pure no-op: it returns the already addressable
    # generation instead of inventing a self-parented manifest.
    if prior is not None:
        prior_core = {key: value for key, value in prior.items() if key not in {"generation_id", "parent_generation_id"}}
        if canonical_json_bytes(prior_core) == canonical_json_bytes(core):
            return prior, {}
    payload: dict[str, Any] = {
        "schema": STORY_PACKET_MANIFEST_SCHEMA,
        "authority": "context_only",
        "generation_id": "0" * 32,
        "parent_generation_id": str(prior["generation_id"]) if prior is not None else None,
        "status": "ready",
        "evidence_root": root_receipt,
        "policy": policy_ref,
        "packets": {key: packets[key] for key in sorted(packets)},
        "files": {key: files[key] for key in sorted(files)},
        "execution": dict(EXECUTION_RECEIPT),
    }
    payload["generation_id"] = canonical_json_sha256({**payload, "generation_id": "0" * 32})[:32]
    validate_story_packet_manifest(payload)
    return payload, artifacts


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_bytes(body)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable_object(root: Path, object_key: str, body: bytes) -> None:
    path = root / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ContractError(f"immutable story packet object collision: {object_key}")
        return
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_bytes(body)
        try:
            os.replace(temporary, path)
        except FileExistsError:
            if path.read_bytes() != body:
                raise ContractError(f"immutable story packet object collision: {object_key}")
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable_generation(root: Path, manifest: Mapping[str, Any]) -> None:
    generation = root / "generations" / str(manifest["generation_id"])
    body = canonical_json_bytes(manifest)
    if generation.exists():
        try:
            existing = (generation / "manifest.json").read_bytes()
        except OSError as exc:
            raise ContractError(f"immutable story packet generation is incomplete: {generation}") from exc
        if existing != body:
            raise ContractError(f"immutable story packet generation collision: {generation}")
        return
    temporary = generation.with_name(f".{generation.name}.tmp.{os.getpid()}")
    try:
        temporary.mkdir(parents=True, exist_ok=False)
        (temporary / "manifest.json").write_bytes(body)
        generation.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(temporary, generation)
        except FileExistsError:
            existing = (generation / "manifest.json").read_bytes()
            if existing != body:
                raise ContractError(f"immutable story packet generation collision: {generation}")
    finally:
        if temporary.exists():
            (temporary / "manifest.json").unlink(missing_ok=True)
            temporary.rmdir()


def write_story_packet_generation(
    out_dir: str | Path,
    evidence_dir: str | Path,
    *,
    policy: object | None = None,
    prior_manifest: object | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write immutable objects/generation, then atomically advance the marker."""
    root = Path(out_dir)
    prior = prior_manifest
    if prior is None and (root / "manifest.json").exists():
        prior = _canonical_marker(root / "manifest.json", label="prior story packet marker")
    manifest, artifacts = build_story_packet_generation(
        evidence_dir,
        policy=policy,
        prior_manifest=prior,
        prior_store_dir=root,
    )
    for object_key, body in sorted(artifacts.items()):
        _write_immutable_object(root, object_key, body)
    _write_immutable_generation(root, manifest)
    _atomic_bytes(root / "manifest.json", canonical_json_bytes(manifest))
    return root / "generations" / str(manifest["generation_id"]), manifest


def verify_story_packet_store(out_dir: str | Path, manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read every current object and parent marker before reporting readiness."""
    root = Path(out_dir)
    try:
        marker, marker_raw = _read_json_bytes(root / "manifest.json", label="story packet marker")
        if marker_raw != canonical_json_bytes(marker):
            raise ContractError("story packet marker is not canonical bytes")
        if manifest is not None and dict(manifest) != marker:
            raise ContractError("provided story packet manifest differs from marker")
        validate_story_packet_manifest(marker)
        generation_id = str(marker["generation_id"])
        immutable = (root / "generations" / generation_id / "manifest.json").read_bytes()
        if immutable != marker_raw:
            raise ContractError("immutable story packet manifest differs from marker")
        # Verify every packet and its index.  ``_packet_body`` also verifies
        # canonical bytes and the content-addressed receipt.
        cursor_packets = _packets_for_manifest(root, marker)
        # Every ancestor must be exact/canonical and catalog non-shrinking.
        cursor = marker
        seen: set[str] = set()
        while cursor["parent_generation_id"] is not None:
            parent_id = str(cursor["parent_generation_id"])
            if parent_id in seen:
                raise ContractError("story packet parent lineage cycle")
            seen.add(parent_id)
            parent, parent_body = _read_json_bytes(root / "generations" / parent_id / "manifest.json", label="story packet parent manifest")
            if parent_body != canonical_json_bytes(parent):
                raise ContractError("story packet parent manifest is not canonical bytes")
            validate_story_packet_manifest(parent)
            if parent["generation_id"] != parent_id:
                raise ContractError("story packet parent generation identity mismatch")
            parent_packets = _packets_for_manifest(root, parent)
            _verify_lineage_transition(cursor, cursor_packets, parent, parent_packets)
            cursor = parent
            cursor_packets = parent_packets
        return {
            "status": "ready",
            "warnings": [],
            "generation_id": generation_id,
            "packet_count": len(marker["packets"]),
            "evidence_generation_id": marker["evidence_root"]["generation_id"],
        }
    except Exception as exc:  # noqa: BLE001 - health is a non-throwing boundary.
        return {
            "status": "invalid",
            "warnings": [f"story_packet_store:{type(exc).__name__}:{exc}"],
            "generation_id": None,
            "packet_count": 0,
            "evidence_generation_id": None,
        }
