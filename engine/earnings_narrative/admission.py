"""Closed receipt for admitting one verified earnings story to Press staging.

This module is intentionally narrow and token-free.  It does not fetch R2,
choose a candidate, accept a writer slot, or authorize publication.  The
transport layer first proves a *current* immutable story-packet root, then this
module derives the one legal ``stage_only`` receipt from the exact packet named
by that root.  A mutable staging JSON is never an approval credential.

The staging orchestrator accepts only immutable IDs, not a local path, a
caller-built slot, or an envelope to trust.  It must hydrate the current R2
root itself, fetch the exact indexed packet itself, and call
``validate_press_admission`` with both replay inputs.  The validator then
derives the receipt and slot again; a detached envelope is intentionally not a
successful admission path.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from engine.press.earnings_adapter import story_to_press_slot

from .contracts import (
    AUTHORITY,
    EXECUTION_RECEIPT,
    MANIFEST_SCHEMA,
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    event_key,
    safe_ticker,
    sha256_bytes,
    transcript_id,
)
from .story_packets import (
    STORY_PACKET_MANIFEST_SCHEMA,
    STORY_PACKET_SCHEMA,
    validate_story_packet,
    validate_story_packet_manifest,
)
from .promotion import PROMOTION_POLICY_SCHEMA


ROOT_AUDIT_SCHEMA = "earnings.story_root_audit/v1"
PRESS_ADMISSION_SCHEMA = "earnings.press_admission/v1"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_GENERATION = re.compile(r"^[0-9a-f]{32}$")
_PACKET = re.compile(r"^storypacket_[0-9a-f]{32}$")
_STORY = re.compile(r"^story_[0-9a-f]{32}$")
_REVISION = re.compile(r"^storyrev_[0-9a-f]{32}$")

_ROOT_AUDIT_KEYS = frozenset({
    "schema", "authority", "generation_id", "marker_sha256", "marker_etag",
    "manifest", "execution",
})
_ADMISSION_KEYS = frozenset({
    "schema", "authority", "operation", "allow_emit", "limits", "story_root",
    "packet", "story", "evidence_root", "policy", "press_slot", "execution",
})
_LIMIT_KEYS = frozenset({"max_candidates", "max_model_calls", "max_tokens"})
_STORY_ROOT_KEYS = frozenset({"schema", "generation_id", "manifest_sha256", "marker_etag"})
_PACKET_RECEIPT_KEYS = frozenset({
    "schema", "event_key", "packet_id", "source_sha256", "object_key", "sha256", "bytes",
})
_STORY_KEYS = frozenset({"story_id", "story_revision_id"})
_ROOT_RECEIPT_KEYS = frozenset({"schema", "generation_id", "manifest_sha256"})
_POLICY_KEYS = frozenset({"schema", "sha256"})
_PRESS_SLOT_KEYS = frozenset({"schema", "sha256"})

_LIMITS = {"max_candidates": 1, "max_model_calls": 1, "max_tokens": 12_000}


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


def _generation(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _GENERATION.fullmatch(value):
        raise ContractError(f"{field} invalid")
    return value


def _etag(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > 512:
        raise ContractError(f"{field} invalid")
    return value


def _event_key(value: object, *, field: str) -> str:
    if not isinstance(value, str) or value.count("/") != 1:
        raise ContractError(f"{field} invalid")
    ticker, tx_id = value.split("/", 1)
    normalized = f"{safe_ticker(ticker)}/{transcript_id(tx_id)}"
    if value != normalized:
        raise ContractError(f"{field} invalid")
    return value


def build_story_root_audit_binding(
    manifest: object,
    *,
    marker_etag: str,
) -> dict[str, Any]:
    """Freeze the exact current R2 marker after a transport-side full audit.

    This is pure on purpose: the R2 transport owns fetching/replay, while this
    contract owns the address later presented to the staging admission path.
    """
    validate_story_packet_manifest(manifest)
    assert isinstance(manifest, Mapping)
    binding = {
        "schema": ROOT_AUDIT_SCHEMA,
        "authority": AUTHORITY,
        "generation_id": str(manifest["generation_id"]),
        "marker_sha256": canonical_json_sha256(manifest),
        "marker_etag": marker_etag,
        "manifest": dict(manifest),
        "execution": dict(EXECUTION_RECEIPT),
    }
    validate_story_root_audit_binding(binding)
    return binding


def validate_story_root_audit_binding(payload: object) -> None:
    """Validate the closed current-root receipt emitted by the R2 audit helper."""
    row = _mapping(payload, name="earnings_story_root_audit")
    _keys(row, _ROOT_AUDIT_KEYS, name="earnings_story_root_audit")
    if row.get("schema") != ROOT_AUDIT_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("earnings_story_root_audit schema or authority mismatch")
    generation = _generation(row.get("generation_id"), field="earnings_story_root_audit.generation_id")
    marker_sha = _sha(row.get("marker_sha256"), field="earnings_story_root_audit.marker_sha256")
    _etag(row.get("marker_etag"), field="earnings_story_root_audit.marker_etag")
    manifest = row.get("manifest")
    validate_story_packet_manifest(manifest)
    assert isinstance(manifest, Mapping)
    if generation != manifest["generation_id"] or marker_sha != canonical_json_sha256(manifest):
        raise ContractError("earnings_story_root_audit does not bind its exact marker")
    if dict(row.get("execution") or {}) != EXECUTION_RECEIPT:
        raise ContractError("earnings_story_root_audit execution must remain token-free")


def _expected_admission(audit_binding: object, packet: object) -> dict[str, Any]:
    validate_story_root_audit_binding(audit_binding)
    audit = _mapping(audit_binding, name="earnings_story_root_audit")
    manifest = _mapping(audit["manifest"], name="earnings_story_root_audit.manifest")
    policy = manifest["policy"]["snapshot"]
    validate_story_packet(packet, policy=policy)
    row = _mapping(packet, name="earnings_story_packet")

    story = _mapping(row["story"], name="earnings_story_packet.story")
    promotion = _mapping(row["promotion"], name="earnings_story_packet.promotion")
    if (
        promotion.get("tier") != "B"
        or story.get("promotion", {}).get("tier") != "B"
        or promotion.get("article_eligible") is not True
        or story.get("promotion", {}).get("article_eligible") is not True
    ):
        raise ContractError("Press admission accepts current Tier B packets only")
    if story.get("status") != "source_ready":
        raise ContractError("Press admission requires a source-ready canonical story")
    slot = row.get("press_slot")
    if not isinstance(slot, Mapping) or slot.get("canonical_emit_allowed") is not False:
        raise ContractError("Press admission requires a non-emittable canonical Press slot")

    prior = row.get("prior")
    prior_story = prior.get("story") if isinstance(prior, Mapping) else None
    replayed_slot = story_to_press_slot(story, row["digest"], prior_story=prior_story)
    if canonical_json_bytes(slot) != canonical_json_bytes(replayed_slot):
        raise ContractError("Press admission slot differs from canonical adapter replay")

    key = event_key(row["digest"]["event"])
    index = manifest["packets"].get(key)
    if not isinstance(index, Mapping):
        raise ContractError("Press admission packet is not present in the current story root")
    object_key = index.get("object_key")
    if not isinstance(object_key, str):
        raise ContractError("Press admission packet index has no object key")
    receipt = manifest["files"].get(object_key)
    if not isinstance(receipt, Mapping):
        raise ContractError("Press admission packet file receipt is absent from current root")
    body = canonical_json_bytes(row)
    if (
        index.get("packet_id") != row.get("packet_id")
        or index.get("source_sha256") != row["digest"]["source"]["body_sha256"]
        or index.get("story_id") != story.get("story_id")
        or index.get("story_revision_id") != story.get("story_revision_id")
        or receipt.get("schema") != STORY_PACKET_SCHEMA
        or receipt.get("object_key") != object_key
        or receipt.get("sha256") != sha256_bytes(body)
        or receipt.get("bytes") != len(body)
    ):
        raise ContractError("Press admission packet differs from current root receipt")

    return {
        "schema": PRESS_ADMISSION_SCHEMA,
        "authority": AUTHORITY,
        "operation": "stage_only",
        "allow_emit": False,
        "limits": dict(_LIMITS),
        "story_root": {
            "schema": STORY_PACKET_MANIFEST_SCHEMA,
            "generation_id": str(audit["generation_id"]),
            "manifest_sha256": str(audit["marker_sha256"]),
            "marker_etag": audit["marker_etag"],
        },
        "packet": {
            "schema": STORY_PACKET_SCHEMA,
            "event_key": key,
            "packet_id": str(row["packet_id"]),
            "source_sha256": str(row["digest"]["source"]["body_sha256"]),
            "object_key": object_key,
            "sha256": str(receipt["sha256"]),
            "bytes": int(receipt["bytes"]),
        },
        "story": {
            "story_id": str(story["story_id"]),
            "story_revision_id": str(story["story_revision_id"]),
        },
        "evidence_root": dict(manifest["evidence_root"]),
        "policy": {
            "schema": str(manifest["policy"]["schema"]),
            "sha256": str(manifest["policy"]["sha256"]),
        },
        "press_slot": {
            "schema": "press.canonical_slot/v1",
            "sha256": canonical_json_sha256(replayed_slot),
        },
        "execution": dict(EXECUTION_RECEIPT),
    }


def build_press_admission(audit_binding: object, packet: object) -> dict[str, Any]:
    """Build the only legal one-candidate, one-call, stage-only admission."""
    admission = _expected_admission(audit_binding, packet)
    validate_press_admission(admission, audit_binding=audit_binding, packet=packet)
    return admission


def validate_press_admission(
    payload: object,
    *,
    audit_binding: object,
    packet: object,
) -> None:
    """Replay and validate the sole legal stage-only receipt for one packet.

    Both replay inputs are mandatory.  A staging caller must first use the
    transport helper to hydrate a stable, current R2 root and then fetch the
    exact packet indexed by that root; this function never admits a detached
    envelope based only on its own well-formed fields.
    """
    row = _mapping(payload, name="earnings_press_admission")
    _keys(row, _ADMISSION_KEYS, name="earnings_press_admission")
    if row.get("schema") != PRESS_ADMISSION_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("earnings_press_admission schema or authority mismatch")
    if row.get("operation") != "stage_only" or row.get("allow_emit") is not False:
        raise ContractError("earnings_press_admission is stage-only and never emits")
    limits = _mapping(row.get("limits"), name="earnings_press_admission.limits")
    _keys(limits, _LIMIT_KEYS, name="earnings_press_admission.limits")
    if dict(limits) != _LIMITS:
        raise ContractError("earnings_press_admission limits are closed")

    root = _mapping(row.get("story_root"), name="earnings_press_admission.story_root")
    _keys(root, _STORY_ROOT_KEYS, name="earnings_press_admission.story_root")
    if root.get("schema") != STORY_PACKET_MANIFEST_SCHEMA:
        raise ContractError("earnings_press_admission story root schema mismatch")
    _generation(root.get("generation_id"), field="earnings_press_admission.story_root.generation_id")
    _sha(root.get("manifest_sha256"), field="earnings_press_admission.story_root.manifest_sha256")
    _etag(root.get("marker_etag"), field="earnings_press_admission.story_root.marker_etag")

    receipt = _mapping(row.get("packet"), name="earnings_press_admission.packet")
    _keys(receipt, _PACKET_RECEIPT_KEYS, name="earnings_press_admission.packet")
    if receipt.get("schema") != STORY_PACKET_SCHEMA:
        raise ContractError("earnings_press_admission packet schema mismatch")
    _event_key(receipt.get("event_key"), field="earnings_press_admission.packet.event_key")
    if not isinstance(receipt.get("packet_id"), str) or not _PACKET.fullmatch(receipt["packet_id"]):
        raise ContractError("earnings_press_admission packet id invalid")
    _sha(receipt.get("source_sha256"), field="earnings_press_admission.packet.source_sha256")
    object_key = receipt.get("object_key")
    if not isinstance(object_key, str) or object_key != f"objects/{receipt.get('sha256')}.json":
        raise ContractError("earnings_press_admission packet object key invalid")
    _sha(receipt.get("sha256"), field="earnings_press_admission.packet.sha256")
    if isinstance(receipt.get("bytes"), bool) or not isinstance(receipt.get("bytes"), int) or receipt["bytes"] <= 0:
        raise ContractError("earnings_press_admission packet bytes invalid")

    story = _mapping(row.get("story"), name="earnings_press_admission.story")
    _keys(story, _STORY_KEYS, name="earnings_press_admission.story")
    if not isinstance(story.get("story_id"), str) or not _STORY.fullmatch(story["story_id"]):
        raise ContractError("earnings_press_admission story id invalid")
    if not isinstance(story.get("story_revision_id"), str) or not _REVISION.fullmatch(story["story_revision_id"]):
        raise ContractError("earnings_press_admission story revision id invalid")

    evidence_root = _mapping(row.get("evidence_root"), name="earnings_press_admission.evidence_root")
    _keys(evidence_root, _ROOT_RECEIPT_KEYS, name="earnings_press_admission.evidence_root")
    if evidence_root.get("schema") != MANIFEST_SCHEMA:
        raise ContractError("earnings_press_admission evidence root schema mismatch")
    _generation(evidence_root.get("generation_id"), field="earnings_press_admission.evidence_root.generation_id")
    _sha(evidence_root.get("manifest_sha256"), field="earnings_press_admission.evidence_root.manifest_sha256")

    policy = _mapping(row.get("policy"), name="earnings_press_admission.policy")
    _keys(policy, _POLICY_KEYS, name="earnings_press_admission.policy")
    if policy.get("schema") != PROMOTION_POLICY_SCHEMA:
        raise ContractError("earnings_press_admission policy schema mismatch")
    _sha(policy.get("sha256"), field="earnings_press_admission.policy.sha256")

    slot = _mapping(row.get("press_slot"), name="earnings_press_admission.press_slot")
    _keys(slot, _PRESS_SLOT_KEYS, name="earnings_press_admission.press_slot")
    if slot.get("schema") != "press.canonical_slot/v1":
        raise ContractError("earnings_press_admission press slot schema mismatch")
    _sha(slot.get("sha256"), field="earnings_press_admission.press_slot.sha256")
    if dict(row.get("execution") or {}) != EXECUTION_RECEIPT:
        raise ContractError("earnings_press_admission execution must remain token-free")

    expected = _expected_admission(audit_binding, packet)
    if canonical_json_bytes(row) != canonical_json_bytes(expected):
        raise ContractError("earnings_press_admission differs from canonical packet admission")
