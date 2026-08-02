"""Receipt-bound earnings story packets and their aggregate manifest contract.

Packets deliberately sit beside, rather than inside, ``earnings_evidence``.
The evidence graph remains an append-only first-party source projection.  This
module turns one of its verified event triples into a deterministic digest,
promotion decision, canonical story, and (only for Tier B) a Press staging
slot.  It never calls a model, writes prose, fetches a source, or emits a post.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping

from engine.press.earnings_adapter import story_to_press_slot

from .contracts import (
    AUTHORITY,
    CLAIM_GRAPH_SCHEMA,
    EXECUTION_RECEIPT,
    FACT_PACK_SCHEMA,
    MANIFEST_SCHEMA,
    TERMINAL_TRANSCRIPT_SCHEMA,
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    canonical_transcript_body_bytes,
    event_key,
    sha256_bytes,
    validate_evidence_pair,
    validate_manifest,
    validate_terminal_transcript,
    verify_fact_pack_against_transcript,
)
from .digest import build_event_digest, validate_event_digest, validate_event_digest_against_evidence
from .promotion import (
    PROMOTION_POLICY_SCHEMA,
    build_promoted_story,
    promotion_policy_sha256,
    validate_promotion_decision,
    validate_promotion_policy,
)
from .story import validate_canonical_story, validate_correction_against_prior, validate_story_against_digest


STORY_PACKET_SCHEMA = "earnings.story_packet/v1"
STORY_PACKET_MANIFEST_SCHEMA = "earnings.story_packet_manifest/v1"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_GENERATION = re.compile(r"^[0-9a-f]{32}$")
_PACKET = re.compile(r"^storypacket_[0-9a-f]{32}$")
_STORY = re.compile(r"^story_[0-9a-f]{32}$")
_REVISION = re.compile(r"^storyrev_[0-9a-f]{32}$")

_PACKET_KEYS = frozenset({
    "schema", "authority", "packet_id", "evidence", "policy", "promotion",
    "digest", "story", "prior", "press_slot", "execution",
})
_EVIDENCE_KEYS = frozenset({"event_key", "source_sha256", "fact_pack", "claim_graph", "source_body"})
_FILE_RECEIPT_KEYS = frozenset({"sha256", "bytes", "schema", "object_key"})
_POLICY_REF_KEYS = frozenset({"schema", "sha256"})
_PRIOR_KEYS = frozenset({"packet_id", "story"})
_MANIFEST_KEYS = frozenset({
    "schema", "authority", "generation_id", "parent_generation_id", "status",
    "evidence_root", "policy", "packets", "files", "execution",
})
_ROOT_KEYS = frozenset({"schema", "generation_id", "manifest_sha256"})
_MANIFEST_POLICY_KEYS = frozenset({"schema", "sha256", "snapshot"})
_PACKET_INDEX_KEYS = frozenset({"packet_id", "source_sha256", "story_id", "story_revision_id", "object_key"})


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    if set(value) != expected:
        raise ContractError(
            f"{name} fields mismatch (missing={sorted(expected - set(value))}, "
            f"unsupported={sorted(set(value) - expected)})"
        )


def _sha(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{field} must be sha256 hex")
    return value


def _generation_id(value: object, *, field: str, allow_null: bool = False) -> str | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not _GENERATION.fullmatch(value):
        raise ContractError(f"{field} invalid")
    return value


def _canonical_file_receipt(value: object, *, schema: str, name: str) -> dict[str, Any]:
    row = _mapping(value, name=name)
    _keys(row, _FILE_RECEIPT_KEYS, name=name)
    digest = _sha(row.get("sha256"), field=f"{name}.sha256")
    size = row.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ContractError(f"{name}.bytes invalid")
    if row.get("schema") != schema or row.get("object_key") != f"objects/{digest}.json":
        raise ContractError(f"{name} schema or object key invalid")
    return dict(row)


def _packet_unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(payload)
    unsigned["packet_id"] = "storypacket_" + ("0" * 32)
    return unsigned


def _manifest_unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(payload)
    unsigned["generation_id"] = "0" * 32
    return unsigned


def _safe_relative(path: object, *, name: str) -> str:
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        raise ContractError(f"{name} unsafe")
    parts = Path(path).parts
    if ".." in parts or Path(path).is_absolute():
        raise ContractError(f"{name} unsafe")
    return path


def evidence_receipts_from_manifest(manifest: object, *, key: str) -> dict[str, Any]:
    """Extract the exact source/fact/claim/body receipts for one event."""
    validate_manifest(manifest)
    assert isinstance(manifest, Mapping)
    event = manifest["events"].get(key)
    if not isinstance(event, Mapping):
        raise ContractError(f"evidence manifest lacks event {key}")
    files = manifest["files"]
    fact_path = str(event["fact_pack"])
    graph_path = str(event["claim_graph"])
    body_path = str(event["source_body"])
    return {
        "event_key": key,
        "source_sha256": str(event["source_sha256"]),
        "fact_pack": dict(files[fact_path]),
        "claim_graph": dict(files[graph_path]),
        "source_body": dict(files[body_path]),
    }


def _validate_evidence_receipts(value: object, *, event: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    row = _mapping(value, name="earnings_story_packet.evidence")
    _keys(row, _EVIDENCE_KEYS, name="earnings_story_packet.evidence")
    key = event_key(event)
    if row.get("event_key") != key or row.get("source_sha256") != source["body_sha256"]:
        raise ContractError("earnings_story_packet evidence identity mismatch")
    fact = _canonical_file_receipt(row.get("fact_pack"), schema=FACT_PACK_SCHEMA, name="earnings_story_packet.evidence.fact_pack")
    graph = _canonical_file_receipt(row.get("claim_graph"), schema=CLAIM_GRAPH_SCHEMA, name="earnings_story_packet.evidence.claim_graph")
    body = _canonical_file_receipt(row.get("source_body"), schema=TERMINAL_TRANSCRIPT_SCHEMA, name="earnings_story_packet.evidence.source_body")
    if body["sha256"] != source["body_sha256"]:
        raise ContractError("earnings_story_packet source body receipt differs from source")
    return {
        "event_key": key,
        "source_sha256": str(source["body_sha256"]),
        "fact_pack": fact,
        "claim_graph": graph,
        "source_body": body,
    }


def _validate_policy_ref(value: object, *, policy: object | None = None) -> dict[str, Any]:
    row = _mapping(value, name="earnings_story_packet.policy")
    _keys(row, _POLICY_REF_KEYS, name="earnings_story_packet.policy")
    if row.get("schema") != PROMOTION_POLICY_SCHEMA:
        raise ContractError("earnings_story_packet policy schema mismatch")
    receipt = _sha(row.get("sha256"), field="earnings_story_packet.policy.sha256")
    if policy is not None and receipt != promotion_policy_sha256(policy):
        raise ContractError("earnings_story_packet policy hash differs from supplied policy")
    return {"schema": PROMOTION_POLICY_SCHEMA, "sha256": receipt}


def _validate_prior(value: object, *, story: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if value is None:
        if story["correction"]["status"] != "current":
            raise ContractError("corrected earnings_story_packet requires prior story")
        return None
    row = _mapping(value, name="earnings_story_packet.prior")
    _keys(row, _PRIOR_KEYS, name="earnings_story_packet.prior")
    packet_id = row.get("packet_id")
    if not isinstance(packet_id, str) or not _PACKET.fullmatch(packet_id):
        raise ContractError("earnings_story_packet prior packet_id invalid")
    prior_story = row.get("story")
    validate_correction_against_prior(story, prior_story)
    assert isinstance(prior_story, Mapping)
    return row


def validate_story_packet(
    payload: object,
    *,
    fact_pack: object | None = None,
    claim_graph: object | None = None,
    transcript: object | None = None,
    policy: object | None = None,
) -> None:
    """Validate a packet; passed evidence inputs enable full deterministic replay."""
    row = _mapping(payload, name="earnings_story_packet")
    _keys(row, _PACKET_KEYS, name="earnings_story_packet")
    if row.get("schema") != STORY_PACKET_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("earnings_story_packet schema or authority mismatch")
    packet_id = row.get("packet_id")
    if not isinstance(packet_id, str) or not _PACKET.fullmatch(packet_id):
        raise ContractError("earnings_story_packet packet_id invalid")
    digest = row.get("digest")
    story = row.get("story")
    validate_event_digest(digest)
    validate_canonical_story(story)
    assert isinstance(digest, Mapping) and isinstance(story, Mapping)
    validate_story_against_digest(story, digest)
    evidence = _validate_evidence_receipts(row.get("evidence"), event=digest["event"], source=digest["source"])
    policy_ref = _validate_policy_ref(row.get("policy"), policy=policy)
    promotion = row.get("promotion")
    validate_promotion_decision(promotion, digest=digest if policy is not None else None, policy=policy)
    assert isinstance(promotion, Mapping)
    if promotion["event_key"] != event_key(digest["event"]) or promotion["digest_id"] != digest["digest_id"]:
        raise ContractError("earnings_story_packet promotion identity mismatch")
    if promotion["policy_sha256"] != policy_ref["sha256"]:
        raise ContractError("earnings_story_packet promotion policy hash mismatch")
    if story["promotion"]["tier"] != promotion["tier"] or story["promotion"]["reasons"] != promotion["reasons"]:
        raise ContractError("earnings_story_packet story promotion mismatch")
    prior = _validate_prior(row.get("prior"), story=story)
    slot = row.get("press_slot")
    if story["promotion"]["tier"] == "B":
        if not isinstance(slot, Mapping):
            raise ContractError("Tier B earnings_story_packet requires a Press staging slot")
        expected_slot = story_to_press_slot(story, digest, prior_story=(prior or {}).get("story") if prior else None)
        if canonical_json_bytes(slot) != canonical_json_bytes(expected_slot):
            raise ContractError("earnings_story_packet Press slot differs from canonical adapter output")
    elif slot is not None:
        raise ContractError("Tier C earnings_story_packet cannot carry a Press slot")
    if dict(row.get("execution") or {}) != EXECUTION_RECEIPT:
        raise ContractError("earnings_story_packet execution must remain token-free")
    expected_id = "storypacket_" + sha256(canonical_json_bytes(_packet_unsigned(row))).hexdigest()[:32]
    if packet_id != expected_id:
        raise ContractError("earnings_story_packet packet_id does not match canonical content")

    supplied = (fact_pack, claim_graph, transcript)
    if any(item is not None for item in supplied):
        if any(item is None for item in supplied):
            raise ContractError("packet replay requires fact_pack, claim_graph, and transcript together")
        validate_evidence_pair(fact_pack, claim_graph)
        verify_fact_pack_against_transcript(fact_pack, transcript)
        assert isinstance(fact_pack, Mapping) and isinstance(claim_graph, Mapping)
        validate_event_digest_against_evidence(digest, fact_pack, claim_graph, transcript)
        if digest["event"] != fact_pack["event"] or digest["source"] != fact_pack["source"]:
            raise ContractError("earnings_story_packet digest does not bind supplied evidence")


def build_story_packet(
    fact_pack: object,
    claim_graph: object,
    transcript: object,
    *,
    evidence: object,
    policy: object,
    prior_packet: object | None = None,
    prior_policy: object | None = None,
) -> dict[str, Any]:
    """Compile one immutable token-free packet from one verified evidence event."""
    validate_evidence_pair(fact_pack, claim_graph)
    verify_fact_pack_against_transcript(fact_pack, transcript)
    validate_terminal_transcript(transcript)
    resolved_policy = validate_promotion_policy(policy)
    assert isinstance(fact_pack, Mapping) and isinstance(claim_graph, Mapping) and isinstance(transcript, Mapping)
    digest = build_event_digest(fact_pack, claim_graph, transcript)
    prior_story: object | None = None
    prior_ref: dict[str, Any] | None = None
    if prior_packet is not None:
        if prior_policy is None:
            raise ContractError("prior packet correction requires its immutable historical policy snapshot")
        historical_policy = validate_promotion_policy(prior_policy)
        validate_story_packet(prior_packet, policy=historical_policy)
        assert isinstance(prior_packet, Mapping)
        prior_story = prior_packet["story"]
        if prior_story["source"]["body_sha256"] == digest["source"]["body_sha256"]:
            raise ContractError("prior packet cannot be used without an evidence source correction")
        prior_ref = {"packet_id": prior_packet["packet_id"], "story": prior_story}
    decision, story = build_promoted_story(digest, policy=resolved_policy, prior_story=prior_story)
    evidence_receipts = _validate_evidence_receipts(evidence, event=digest["event"], source=digest["source"])
    slot: dict[str, Any] | None = None
    if story["promotion"]["tier"] == "B":
        slot = story_to_press_slot(story, digest, prior_story=prior_story)
    payload: dict[str, Any] = {
        "schema": STORY_PACKET_SCHEMA,
        "authority": AUTHORITY,
        "packet_id": "storypacket_" + ("0" * 32),
        "evidence": evidence_receipts,
        "policy": {"schema": PROMOTION_POLICY_SCHEMA, "sha256": promotion_policy_sha256(resolved_policy)},
        "promotion": decision,
        "digest": digest,
        "story": story,
        "prior": prior_ref,
        "press_slot": slot,
        "execution": dict(EXECUTION_RECEIPT),
    }
    payload["packet_id"] = "storypacket_" + sha256(canonical_json_bytes(_packet_unsigned(payload))).hexdigest()[:32]
    validate_story_packet(payload, fact_pack=fact_pack, claim_graph=claim_graph, transcript=transcript, policy=resolved_policy)
    return payload


def validate_story_packet_manifest(payload: object) -> None:
    """Validate the closed aggregate catalog for immutable packet objects."""
    row = _mapping(payload, name="earnings_story_packet_manifest")
    _keys(row, _MANIFEST_KEYS, name="earnings_story_packet_manifest")
    if row.get("schema") != STORY_PACKET_MANIFEST_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("earnings_story_packet_manifest schema or authority mismatch")
    generation_id = _generation_id(row.get("generation_id"), field="earnings_story_packet_manifest.generation_id")
    parent = _generation_id(row.get("parent_generation_id"), field="earnings_story_packet_manifest.parent_generation_id", allow_null=True)
    if parent == generation_id:
        raise ContractError("earnings_story_packet_manifest cannot parent itself")
    if row.get("status") != "ready":
        raise ContractError("earnings_story_packet_manifest status must be ready")
    root = _mapping(row.get("evidence_root"), name="earnings_story_packet_manifest.evidence_root")
    _keys(root, _ROOT_KEYS, name="earnings_story_packet_manifest.evidence_root")
    if root.get("schema") != MANIFEST_SCHEMA:
        raise ContractError("earnings_story_packet_manifest evidence root schema mismatch")
    _generation_id(root.get("generation_id"), field="earnings_story_packet_manifest.evidence_root.generation_id")
    _sha(root.get("manifest_sha256"), field="earnings_story_packet_manifest.evidence_root.manifest_sha256")
    policy = _mapping(row.get("policy"), name="earnings_story_packet_manifest.policy")
    _keys(policy, _MANIFEST_POLICY_KEYS, name="earnings_story_packet_manifest.policy")
    if policy.get("schema") != PROMOTION_POLICY_SCHEMA:
        raise ContractError("earnings_story_packet_manifest policy schema mismatch")
    policy_sha = _sha(policy.get("sha256"), field="earnings_story_packet_manifest.policy.sha256")
    snapshot = validate_promotion_policy(policy.get("snapshot"))
    if promotion_policy_sha256(snapshot) != policy_sha:
        raise ContractError("earnings_story_packet_manifest policy snapshot hash mismatch")
    packets = _mapping(row.get("packets"), name="earnings_story_packet_manifest.packets")
    files = _mapping(row.get("files"), name="earnings_story_packet_manifest.files")
    expected_paths: set[str] = set()
    for key, index in packets.items():
        if not isinstance(key, str) or "/" not in key:
            raise ContractError("earnings_story_packet_manifest packet key invalid")
        index_row = _mapping(index, name=f"earnings_story_packet_manifest.packets[{key}]")
        _keys(index_row, _PACKET_INDEX_KEYS, name=f"earnings_story_packet_manifest.packets[{key}]")
        packet_id = index_row.get("packet_id")
        if not isinstance(packet_id, str) or not _PACKET.fullmatch(packet_id):
            raise ContractError("earnings_story_packet_manifest packet id invalid")
        _sha(index_row.get("source_sha256"), field="earnings_story_packet_manifest source sha")
        if not isinstance(index_row.get("story_id"), str) or not _STORY.fullmatch(index_row["story_id"]):
            raise ContractError("earnings_story_packet_manifest story id invalid")
        if not isinstance(index_row.get("story_revision_id"), str) or not _REVISION.fullmatch(index_row["story_revision_id"]):
            raise ContractError("earnings_story_packet_manifest story revision invalid")
        object_key = _safe_relative(index_row.get("object_key"), name="earnings_story_packet_manifest object key")
        expected_paths.add(object_key)
        receipt = _canonical_file_receipt(files.get(object_key), schema=STORY_PACKET_SCHEMA, name=f"earnings_story_packet_manifest.files[{object_key}]")
        if object_key != receipt["object_key"]:
            raise ContractError("earnings_story_packet_manifest packet object receipt mismatch")
    if set(files) != expected_paths:
        raise ContractError("earnings_story_packet_manifest files must exactly cover packets")
    if list(packets) != sorted(packets) or list(files) != sorted(files):
        raise ContractError("earnings_story_packet_manifest catalogs must remain sorted")
    if dict(row.get("execution") or {}) != EXECUTION_RECEIPT:
        raise ContractError("earnings_story_packet_manifest execution must remain token-free")
    expected_id = canonical_json_sha256(_manifest_unsigned(row))[:32]
    if generation_id != expected_id:
        raise ContractError("earnings_story_packet_manifest generation_id does not match canonical content")


def load_evidence_event(
    evidence_dir: str | Path,
    *,
    key: str,
    manifest: object | None = None,
    object_dir: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load and receipt-check the exact evidence triple for one catalog event.

    ``object_dir`` lets a full lineage audit keep generation markers separate
    while deduplicating their shared content-addressed evidence objects.
    """
    root = Path(evidence_dir)
    object_root = Path(object_dir) if object_dir is not None else root
    if manifest is None:
        try:
            raw = (root / "manifest.json").read_bytes()
            manifest = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot read evidence root marker: {exc}") from exc
    validate_manifest(manifest)
    assert isinstance(manifest, Mapping)
    marker_raw = canonical_json_bytes(manifest)
    marker_path = root / "manifest.json"
    if marker_path.exists() and marker_path.read_bytes() != marker_raw:
        raise ContractError("evidence root marker is not canonical bytes")
    receipts = evidence_receipts_from_manifest(manifest, key=key)
    loaded: list[dict[str, Any]] = []
    for receipt_key in ("fact_pack", "claim_graph", "source_body"):
        receipt = receipts[receipt_key]
        path = object_root / str(receipt["object_key"])
        try:
            body = path.read_bytes()
            payload = json.loads(body.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot read evidence object {receipt['object_key']}: {exc}") from exc
        expected = canonical_transcript_body_bytes(payload) if receipt_key == "source_body" else canonical_json_bytes(payload)
        if body != expected or len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
            raise ContractError(f"evidence object receipt mismatch: {receipt['object_key']}")
        loaded.append(payload)
    fact_pack, claim_graph, transcript = loaded
    validate_evidence_pair(fact_pack, claim_graph)
    validate_terminal_transcript(transcript)
    verify_fact_pack_against_transcript(fact_pack, transcript)
    if event_key(fact_pack["event"]) != key or fact_pack["source"]["body_sha256"] != receipts["source_sha256"]:
        raise ContractError("evidence root event does not bind loaded triple")
    return dict(manifest), fact_pack, claim_graph, transcript
