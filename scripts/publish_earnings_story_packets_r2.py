"""Publish verified immutable earnings-story packet generations to R2.

The deterministic packet compiler is the only producer of this projection.
This transport never picks a promotion tier, invokes a model, or stages Press
content.  It verifies the local catalog, creates every content-addressed
object with ``If-None-Match: *``, writes the immutable generation manifest,
reserves the exact parent in an append-only publication journal, moves the sole
mutable root marker with compare-and-swap, and only then commits that journal
transition.  Auditors trust the finalized journal tip, not orphaned CAS losers.

Operational trust boundary: audit/read principals must be able to list the
entire journal prefix, while the publisher principal must have no DeleteObject
authority over journal or generation objects.  Application code can fail a
denied list call closed; it cannot detect an IAM policy that silently hides a
subset of otherwise valid keys.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import (
    AUTHORITY,
    EXECUTION_RECEIPT,
    TERMINAL_TRANSCRIPT_SCHEMA,
    canonical_json_bytes,
    canonical_transcript_body_bytes,
    sha256_bytes,
    validate_manifest as validate_evidence_manifest,
)
from engine.earnings_narrative.admission import (
    ROOT_AUDIT_SCHEMA,
    validate_story_root_audit_binding,
)


log = logging.getLogger("publish_earnings_story_packets_r2")
PREFIX = "earnings_story_packets"
EVIDENCE_PREFIX = "earnings_evidence"
JOURNAL_PREFIX = f"{PREFIX}/journal"
JOURNAL_ANCHOR_KEY = f"{JOURNAL_PREFIX}/anchor.json"
PUBLISH_CONFLICT = 2
ANCHOR_SCHEMA = "earnings.story_packet_publish_anchor/v1"
TRANSITION_SCHEMA = "earnings.story_packet_publish_transition/v1"
COMMIT_SCHEMA = "earnings.story_packet_publish_commit/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_ID = re.compile(r"^[0-9a-f]{32}$")
_PACKET_ID = re.compile(r"^storypacket_[0-9a-f]{32}$")
_STORY_REVISION_ID = re.compile(r"^storyrev_[0-9a-f]{32}$")


class ImmutableAddressIntegrityError(RuntimeError):
    """An immutable address or the public catalog has invalid receipts."""


class ImmutableCreateConflict(ImmutableAddressIntegrityError):
    """A conditional immutable create lost to different stored bytes."""


def _story_contracts() -> tuple[Callable[[object], None], Callable[..., Mapping[str, Any]]]:
    """Load the story-plane contract only when publication is requested.

    Keeping this import narrow lets the safe credential-less path run before
    the companion projection lands.  The companion implementation must expose
    these two deterministic functions; this transport intentionally owns no
    duplicate manifest schema or store verifier.
    """
    try:
        from engine.earnings_narrative.story_packets import validate_story_packet_manifest
        from engine.earnings_narrative.story_store import verify_story_packet_store
    except ImportError as exc:  # pragma: no cover - exercised until core lands.
        raise ImmutableAddressIntegrityError(
            "earnings story packet projection contracts are unavailable "
            "(expected story_packets.validate_story_packet_manifest and "
            "story_store.verify_story_packet_store)"
        ) from exc
    return validate_story_packet_manifest, verify_story_packet_store


def _validate_manifest(payload: object) -> None:
    validator, _verify = _story_contracts()
    validator(payload)


def _verify_store(out_dir: Path, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    _validator, verifier = _story_contracts()
    result = verifier(Path(out_dir), manifest=manifest)
    if not isinstance(result, Mapping):
        raise ImmutableAddressIntegrityError("story packet store verifier did not return health")
    return result


def _audit_bound_evidence(
    s3: Any,
    bucket: str,
    *,
    story_root: Path,
    story_manifests: list[Mapping[str, Any]],
) -> None:
    """Replay every unique packet in the lineage against its bound evidence.

    Story generations grow append-only, so naively replaying every historical
    catalog would fetch and validate the same unchanged event once per hour of
    ancestry.  This audit still checks every generation's catalog/evidence
    mapping, but deduplicates immutable objects and packet replays by their
    content ids.  Corrections remain distinct packet ids and therefore retain
    full historical source provenance.
    """
    from engine.earnings_narrative.story_packets import (  # noqa: PLC0415
        evidence_receipts_from_manifest,
        load_evidence_event,
        validate_story_packet,
    )

    evidence_root = story_root / "_bound_evidence"
    evidence_root.mkdir()
    evidence_objects = evidence_root / "objects_cache"
    evidence_objects.mkdir()
    evidence_manifests: dict[str, tuple[dict[str, Any], bytes]] = {}
    replay_tasks: dict[str, tuple[str, Mapping[str, Any], str, Mapping[str, Any]]] = {}
    receipts: dict[str, Mapping[str, Any]] = {}
    for story_manifest in story_manifests:
        evidence_ref = story_manifest.get("evidence_root")
        if not isinstance(evidence_ref, Mapping):
            raise ImmutableAddressIntegrityError("story packet marker lacks an evidence root receipt")
        evidence_generation = str(evidence_ref.get("generation_id") or "")
        cached = evidence_manifests.get(evidence_generation)
        if cached is None:
            try:
                evidence_raw = s3.get_object(
                    Bucket=bucket,
                    Key=f"{EVIDENCE_PREFIX}/generations/{evidence_generation}/manifest.json",
                )["Body"].read()
                evidence_manifest = _canonical_object(evidence_raw, label="bound earnings evidence manifest")
                validate_evidence_manifest(evidence_manifest)
            except Exception as exc:  # noqa: BLE001
                raise ImmutableAddressIntegrityError("cannot verify bound earnings evidence manifest") from exc
            evidence_manifests[evidence_generation] = (evidence_manifest, evidence_raw)
            manifest_dir = evidence_root / "manifests" / evidence_generation
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_bytes(evidence_raw)
        else:
            evidence_manifest, evidence_raw = cached
        if (
            evidence_manifest.get("generation_id") != evidence_generation
            or sha256_bytes(evidence_raw) != evidence_ref.get("manifest_sha256")
        ):
            raise ImmutableAddressIntegrityError("bound earnings evidence manifest receipt mismatch")
        if set(evidence_manifest["events"]) != set(story_manifest["packets"]):
            raise ImmutableAddressIntegrityError("story packet catalog does not exactly project its evidence root")

        policy = story_manifest["policy"]["snapshot"]
        for key, index in story_manifest["packets"].items():
            packet_receipt = story_manifest["files"][index["object_key"]]
            packet = _canonical_object(
                (story_root / packet_receipt["object_key"]).read_bytes(),
                label=f"story packet {key}",
            )
            expected = evidence_receipts_from_manifest(evidence_manifest, key=key)
            if canonical_json_bytes(packet.get("evidence")) != canonical_json_bytes(expected):
                raise ImmutableAddressIntegrityError(f"story packet evidence receipt differs from bound root: {key}")
            packet_id = str(packet["packet_id"])
            prior_task = replay_tasks.get(packet_id)
            if prior_task is not None:
                prior_key, prior_packet, _prior_generation, prior_policy = prior_task
                if (
                    prior_key != key
                    or canonical_json_bytes(prior_packet) != canonical_json_bytes(packet)
                    or canonical_json_bytes(prior_policy) != canonical_json_bytes(policy)
                ):
                    raise ImmutableAddressIntegrityError(f"packet id maps to inconsistent lineage content: {packet_id}")
            else:
                replay_tasks[packet_id] = (str(key), packet, evidence_generation, policy)
            for receipt_name in ("fact_pack", "claim_graph", "source_body"):
                receipt = expected[receipt_name]
                object_key = str(receipt["object_key"])
                prior = receipts.get(object_key)
                if prior is not None and dict(prior) != dict(receipt):
                    raise ImmutableAddressIntegrityError(f"bound evidence object receipt collision: {object_key}")
                receipts[object_key] = receipt

    for object_key, receipt in receipts.items():
        try:
            body = s3.get_object(Bucket=bucket, Key=f"{EVIDENCE_PREFIX}/{object_key}")["Body"].read()
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise ImmutableAddressIntegrityError(f"cannot read bound evidence object: {object_key}") from exc
        expected_body = (
            canonical_transcript_body_bytes(payload)
            if receipt["schema"] == TERMINAL_TRANSCRIPT_SCHEMA
            else canonical_json_bytes(payload)
        )
        if (
            body != expected_body
            or len(body) != receipt["bytes"]
            or sha256_bytes(body) != receipt["sha256"]
        ):
            raise ImmutableAddressIntegrityError(f"bound evidence object receipt mismatch: {object_key}")
        path = evidence_objects / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    for key, packet, evidence_generation, policy in replay_tasks.values():
        evidence_manifest = evidence_manifests[evidence_generation][0]
        manifest_dir = evidence_root / "manifests" / evidence_generation
        _manifest, fact_pack, claim_graph, transcript = load_evidence_event(
            manifest_dir,
            key=key,
            manifest=evidence_manifest,
            object_dir=evidence_objects,
        )
        validate_story_packet(
            packet,
            fact_pack=fact_pack,
            claim_graph=claim_graph,
            transcript=transcript,
            policy=policy,
        )


def _client() -> Any | None:
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except ImportError:
        log.warning("boto3 not installed — cannot publish earnings story packets")
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            region_name="auto", signature_version="s3v4", max_pool_connections=8,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    return (
        str(error.get("Code") or "").lower() in {"404", "nosuchkey", "notfound", "no_such_key"}
        or int(metadata.get("HTTPStatusCode") or 0) == 404
        or (type(exc) is RuntimeError and str(exc).strip().lower() in {"missing", "not found"})
    )


def _is_precondition_failed(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    return str(error.get("Code") or "") in {"412", "PreconditionFailed"} or int(metadata.get("HTTPStatusCode") or 0) == 412


def _canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImmutableAddressIntegrityError(f"{label} is not UTF-8 canonical JSON") from exc
    if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
        raise ImmutableAddressIntegrityError(f"{label} is not canonical JSON")
    return payload


def _read_local_manifest(out_dir: Path) -> dict[str, Any] | None:
    try:
        return _canonical_object((Path(out_dir) / "manifest.json").read_bytes(), label="local root marker")
    except (OSError, ImmutableAddressIntegrityError):
        return None


def _remote_marker(s3: Any, bucket: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = s3.get_object(Bucket=bucket, Key=f"{PREFIX}/manifest.json")
        payload = _canonical_object(response["Body"].read(), label="current story packet marker")
        return payload, str(response.get("ETag") or "") or None
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None, None
        if isinstance(exc, ImmutableAddressIntegrityError):
            raise
        raise ImmutableAddressIntegrityError("cannot read current story packet marker") from exc


def _listed_keys(s3: Any, bucket: str, *, prefix: str) -> list[str]:
    """Return a complete, strictly paginated object listing."""
    continuation: str | None = None
    seen_tokens: set[str] = set()
    rows: list[str] = []
    seen_keys: set[str] = set()
    while True:
        args: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation is not None:
            args["ContinuationToken"] = continuation
        try:
            response = s3.list_objects_v2(**args)
        except Exception as exc:  # noqa: BLE001
            raise ImmutableAddressIntegrityError(
                "cannot list immutable story packet publication journal; ListObjects permission is required"
            ) from exc
        if not isinstance(response, Mapping):
            raise ImmutableAddressIntegrityError("story packet publication journal listing is invalid")
        truncated = response.get("IsTruncated")
        if not isinstance(truncated, bool):
            raise ImmutableAddressIntegrityError("story packet publication journal pagination flag is invalid")
        contents = response.get("Contents") or []
        if not isinstance(contents, list):
            raise ImmutableAddressIntegrityError("story packet publication journal listing has invalid contents")
        for item in contents:
            key = item.get("Key") if isinstance(item, Mapping) else None
            if not isinstance(key, str) or not key.startswith(prefix):
                raise ImmutableAddressIntegrityError("story packet publication journal listing has invalid key")
            if key in seen_keys:
                raise ImmutableAddressIntegrityError("story packet publication journal listing repeated a key")
            seen_keys.add(key)
            rows.append(key)
        next_token = response.get("NextContinuationToken")
        if not truncated:
            if next_token not in (None, ""):
                raise ImmutableAddressIntegrityError("terminal journal listing exposed a continuation token")
            break
        if not isinstance(next_token, str) or not next_token or next_token in seen_tokens:
            raise ImmutableAddressIntegrityError("story packet publication journal pagination is invalid")
        seen_tokens.add(next_token)
        continuation = next_token
    return sorted(rows)


def _manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(manifest))


def _anchor_receipt(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ANCHOR_SCHEMA,
        "generation_id": _generation_id(manifest),
        "generation_manifest_sha256": _manifest_sha256(manifest),
    }


def _transition_receipt(manifest: Mapping[str, Any]) -> dict[str, Any]:
    parent = manifest.get("parent_generation_id")
    if not isinstance(parent, str):
        raise ImmutableAddressIntegrityError("a journal transition requires a parent generation")
    return {
        "schema": TRANSITION_SCHEMA,
        "parent_generation_id": parent,
        "generation_id": _generation_id(manifest),
        "generation_manifest_sha256": _manifest_sha256(manifest),
    }


def _commit_receipt(transition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": COMMIT_SCHEMA,
        "generation_id": str(transition["generation_id"]),
        "transition_sha256": sha256_bytes(canonical_json_bytes(transition)),
    }


def _journal_key(kind: str, generation_id: str) -> str:
    if kind == "anchors":
        # One fixed If-None-Match reservation prevents concurrent first-root
        # candidates from creating multiple permanent anchors before root CAS.
        return JOURNAL_ANCHOR_KEY
    return f"{JOURNAL_PREFIX}/{kind}/{generation_id}.json"


def _generation_manifest_from_r2(s3: Any, bucket: str, generation_id: str) -> dict[str, Any]:
    try:
        raw = s3.get_object(
            Bucket=bucket,
            Key=f"{PREFIX}/generations/{generation_id}/manifest.json",
        )["Body"].read()
        manifest = _canonical_object(raw, label=f"journal-bound generation {generation_id}")
        _validate_manifest(manifest)
    except ImmutableAddressIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(
            f"cannot verify journal-bound generation: {generation_id}"
        ) from exc
    if _generation_id(manifest) != generation_id:
        raise ImmutableAddressIntegrityError("journal generation key differs from manifest identity")
    return manifest


def _load_publication_journal(
    s3: Any,
    bucket: str,
    *,
    current_manifest: Mapping[str, Any] | None,
    require_resolved: bool,
    allow_empty: bool = False,
) -> dict[str, Any] | None:
    """Validate the append-only, parent-reserved publication journal.

    Generation objects are written before the mutable root and may therefore
    include harmless CAS losers.  Only a journaled transition that reserved its
    exact parent and received a post-CAS commit is a durable high-water mark.
    An unresolved transition fails staging closed: it can mean either a pending
    exact retry or a root move whose commit was interrupted.
    """
    prefix = f"{JOURNAL_PREFIX}/"
    keys = _listed_keys(s3, bucket, prefix=prefix)
    if not keys:
        if allow_empty:
            return None
        raise ImmutableAddressIntegrityError("story packet publication journal is absent")

    anchors: dict[str, dict[str, Any]] = {}
    transitions: dict[str, dict[str, Any]] = {}
    commits: dict[str, dict[str, Any]] = {}
    for key in keys:
        if key == JOURNAL_ANCHOR_KEY:
            kind = "anchors"
            key_id = ""
        else:
            relative = key[len(prefix):]
            parts = relative.split("/")
            if len(parts) != 2 or not parts[1].endswith(".json"):
                raise ImmutableAddressIntegrityError(f"unexpected publication journal object: {key}")
            kind, filename = parts
            if kind == "anchors":
                raise ImmutableAddressIntegrityError(f"unexpected publication journal object: {key}")
            key_id = filename[:-5]
            _generation_id({"generation_id": key_id})
        try:
            raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            receipt = _canonical_object(raw, label=f"story packet publication {kind} receipt")
        except ImmutableAddressIntegrityError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ImmutableAddressIntegrityError(f"cannot read publication journal object: {key}") from exc

        if kind == "anchors":
            if set(receipt) != {"schema", "generation_id", "generation_manifest_sha256"}:
                raise ImmutableAddressIntegrityError("publication anchor fields mismatch")
            if receipt.get("schema") != ANCHOR_SCHEMA:
                raise ImmutableAddressIntegrityError("publication anchor identity mismatch")
            anchor_id = _generation_id(receipt)
            if not isinstance(receipt.get("generation_manifest_sha256"), str) or not _SHA256.fullmatch(
                receipt["generation_manifest_sha256"]
            ):
                raise ImmutableAddressIntegrityError("publication anchor manifest digest invalid")
            anchors[anchor_id] = receipt
        elif kind == "transitions":
            if set(receipt) != {
                "schema", "parent_generation_id", "generation_id", "generation_manifest_sha256",
            }:
                raise ImmutableAddressIntegrityError("publication transition fields mismatch")
            if receipt.get("schema") != TRANSITION_SCHEMA or receipt.get("parent_generation_id") != key_id:
                raise ImmutableAddressIntegrityError("publication transition parent reservation mismatch")
            generation_id = _generation_id(receipt)
            if generation_id == key_id:
                raise ImmutableAddressIntegrityError("publication transition cannot point to itself")
            if not isinstance(receipt.get("generation_manifest_sha256"), str) or not _SHA256.fullmatch(
                receipt["generation_manifest_sha256"]
            ):
                raise ImmutableAddressIntegrityError("publication transition manifest digest invalid")
            transitions[key_id] = receipt
        elif kind == "commits":
            if set(receipt) != {"schema", "generation_id", "transition_sha256"}:
                raise ImmutableAddressIntegrityError("publication commit fields mismatch")
            if receipt.get("schema") != COMMIT_SCHEMA or receipt.get("generation_id") != key_id:
                raise ImmutableAddressIntegrityError("publication commit identity mismatch")
            if not isinstance(receipt.get("transition_sha256"), str) or not _SHA256.fullmatch(
                receipt["transition_sha256"]
            ):
                raise ImmutableAddressIntegrityError("publication commit transition digest invalid")
            commits[key_id] = receipt
        else:
            raise ImmutableAddressIntegrityError(f"unexpected publication journal kind: {kind}")

    if len(anchors) != 1:
        raise ImmutableAddressIntegrityError("publication journal must contain exactly one immutable anchor")
    anchor_id, anchor = next(iter(anchors.items()))
    anchor_manifest = _generation_manifest_from_r2(s3, bucket, anchor_id)
    if _manifest_sha256(anchor_manifest) != anchor["generation_manifest_sha256"]:
        raise ImmutableAddressIntegrityError("publication anchor differs from generation manifest")

    transition_by_generation: dict[str, dict[str, Any]] = {}
    for parent_id, transition in transitions.items():
        generation_id = str(transition["generation_id"])
        if generation_id in transition_by_generation:
            raise ImmutableAddressIntegrityError("publication journal generation has multiple parents")
        manifest = _generation_manifest_from_r2(s3, bucket, generation_id)
        if (
            manifest.get("parent_generation_id") != parent_id
            or _manifest_sha256(manifest) != transition["generation_manifest_sha256"]
        ):
            raise ImmutableAddressIntegrityError("publication transition differs from generation manifest")
        transition_by_generation[generation_id] = transition
    for generation_id, commit in commits.items():
        transition = transition_by_generation.get(generation_id)
        if transition is None or commit["transition_sha256"] != sha256_bytes(canonical_json_bytes(transition)):
            raise ImmutableAddressIntegrityError("publication commit lacks its exact transition")

    tip = anchor_id
    visited_parents: set[str] = set()
    visited_commits: set[str] = set()
    unresolved: dict[str, Any] | None = None
    while tip in transitions:
        if tip in visited_parents:
            raise ImmutableAddressIntegrityError("publication journal contains a cycle")
        visited_parents.add(tip)
        transition = transitions[tip]
        candidate = str(transition["generation_id"])
        if candidate not in commits:
            unresolved = transition
            break
        visited_commits.add(candidate)
        tip = candidate
    if visited_parents != set(transitions) or visited_commits != set(commits):
        raise ImmutableAddressIntegrityError("publication journal is forked or disconnected")
    if require_resolved and unresolved is not None:
        raise ImmutableAddressIntegrityError("story packet publication transition is unresolved")

    if current_manifest is not None:
        current_generation = _generation_id(current_manifest)
        allowed_current = {tip}
        if unresolved is not None:
            allowed_current.add(str(unresolved["generation_id"]))
        if current_generation not in allowed_current:
            raise ImmutableAddressIntegrityError(
                "current story packet marker is behind or outside the finalized publication journal"
            )
        if require_resolved and current_generation != tip:
            raise ImmutableAddressIntegrityError(
                "current story packet marker is not the finalized publication journal tip"
            )
    return {
        "anchor_generation_id": anchor_id,
        "tip_generation_id": tip,
        "unresolved_transition": unresolved,
        "transition_count": len(transitions),
        "commit_count": len(commits),
    }


def _assert_current_generation_is_finalized(
    marker: Mapping[str, Any],
    *,
    s3: Any,
    bucket: str,
) -> None:
    _load_publication_journal(
        s3,
        bucket,
        current_manifest=marker,
        require_resolved=True,
    )


def load_remote_root_marker(*, s3: Any | None = None, bucket: str | None = None) -> dict[str, Any] | None:
    """Return the validated last-good public marker, if credentials exist."""
    marker, _etag, _digest = load_remote_root_state(s3=s3, bucket=bucket)
    return marker


def load_remote_root_state(
    *, s3: Any | None = None, bucket: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Return the root marker plus the only safe conditional-write identity."""
    client = s3 if s3 is not None else _client()
    if client is None:
        return None, None, None
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set for story packet marker hydration")
    marker, etag = _remote_marker(client, target_bucket)
    if marker is not None:
        try:
            _validate_manifest(marker)
        except Exception as exc:  # noqa: BLE001
            raise ImmutableAddressIntegrityError("current story packet marker fails its contract") from exc
    return marker, etag, sha256_bytes(canonical_json_bytes(marker)) if marker is not None else None


def _file_receipts(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Read the closed receipt map without independently defining its schema."""
    files = manifest.get("files")
    if not isinstance(files, Mapping) or not files:
        raise ImmutableAddressIntegrityError("story packet manifest has no immutable file receipts")
    output: dict[str, Mapping[str, Any]] = {}
    for path, receipt in files.items():
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
            raise ImmutableAddressIntegrityError("story packet manifest has an unsafe receipt path")
        if not isinstance(receipt, Mapping):
            raise ImmutableAddressIntegrityError(f"story packet receipt is not an object: {path}")
        object_key = receipt.get("object_key")
        digest = receipt.get("sha256")
        size = receipt.get("bytes")
        if (
            not isinstance(object_key, str) or not object_key or object_key.startswith("/") or ".." in Path(object_key).parts
            or not isinstance(digest, str) or not _SHA256.fullmatch(digest)
            or isinstance(size, bool) or not isinstance(size, int) or size < 0
        ):
            raise ImmutableAddressIntegrityError(f"story packet receipt invalid: {path}")
        output[path] = receipt
    return output


def _catalog_keys(manifest: Mapping[str, Any]) -> set[str]:
    """Stable packet keys make root shrink mechanically impossible."""
    packets = manifest.get("packets")
    if not isinstance(packets, Mapping) or not packets:
        raise ImmutableAddressIntegrityError("story packet manifest has no packet catalog")
    if any(not isinstance(key, str) or not key for key in packets):
        raise ImmutableAddressIntegrityError("story packet manifest has an invalid packet catalog key")
    return set(packets)


def _generation_id(manifest: Mapping[str, Any]) -> str:
    generation_id = manifest.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id or "/" in generation_id or ".." in generation_id:
        raise ImmutableAddressIntegrityError("story packet generation id invalid")
    return generation_id


def _validate_staging(out_dir: Path, manifest: Mapping[str, Any]) -> None:
    root = Path(out_dir)
    marker = canonical_json_bytes(manifest)
    try:
        if (root / "manifest.json").read_bytes() != marker:
            raise ImmutableAddressIntegrityError("local story packet marker bytes are not canonical")
        generation = root / "generations" / _generation_id(manifest)
        if (generation / "manifest.json").read_bytes() != marker:
            raise ImmutableAddressIntegrityError("local immutable story packet manifest differs from root")
        for relative, receipt in _file_receipts(manifest).items():
            object_key = str(receipt["object_key"])
            body = (root / object_key).read_bytes()
            if len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
                raise ImmutableAddressIntegrityError(f"local story packet receipt mismatch: {relative}")
            _canonical_object(body, label=f"local story packet object {relative}")
        health = _verify_store(root, manifest)
        if health.get("status") != "ready":
            raise ImmutableAddressIntegrityError("local story packet store is not ready")
    except ImmutableAddressIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError("local story packet store validation failed") from exc


def _existing_immutable_matches(s3: Any, bucket: str, key: str, body: bytes) -> bool:
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return False
        raise ImmutableAddressIntegrityError(f"cannot determine immutable object state: {key}") from exc
    digest = sha256_bytes(body)
    if int(head.get("ContentLength", -1)) != len(body):
        raise ImmutableCreateConflict(f"immutable object byte receipt mismatch: {key}")
    metadata = head.get("Metadata", {})
    metadata_sha = metadata.get("sha256") if isinstance(metadata, Mapping) else None
    if metadata_sha == digest:
        return True
    try:
        existing = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"cannot read immutable object: {key}") from exc
    if not isinstance(existing, bytes) or existing != body or sha256_bytes(existing) != digest:
        raise ImmutableCreateConflict(f"immutable object byte receipt mismatch: {key}")
    return True


def _put_immutable(s3: Any, bucket: str, key: str, body: bytes, *, dry_run: bool) -> None:
    if _existing_immutable_matches(s3, bucket, key, body):
        return
    if dry_run:
        return
    try:
        s3.put_object(
            Bucket=bucket, Key=key, Body=body, ContentType="application/json",
            Metadata={"sha256": sha256_bytes(body)}, IfNoneMatch="*",
        )
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            try:
                if _existing_immutable_matches(s3, bucket, key, body):
                    return
            except ImmutableCreateConflict:
                raise
        raise ImmutableAddressIntegrityError(f"immutable create failed: {key}") from exc


def _changed_receipts(manifest: Mapping[str, Any], remote: Mapping[str, Any] | None) -> list[tuple[str, Mapping[str, Any]]]:
    local = _file_receipts(manifest)
    remote_files = remote.get("files") if isinstance(remote, Mapping) else None
    if not isinstance(remote_files, Mapping):
        return sorted(local.items())
    return [(path, receipt) for path, receipt in sorted(local.items()) if remote_files.get(path) != receipt]


def _shrink_allowed(local: Mapping[str, Any], remote: Mapping[str, Any] | None) -> bool:
    if not isinstance(remote, Mapping) or remote.get("status") != "ready":
        return True
    return _catalog_keys(remote).issubset(_catalog_keys(local))


def _hydrate_and_verify_current_story_root(
    *,
    s3: Any | None = None,
    bucket: str | None = None,
    require_publication_journal: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a sealed binding plus the original detailed audit health."""
    client = s3 if s3 is not None else _client()
    if client is None:
        raise ImmutableAddressIntegrityError("R2 credentials are required for a public story packet audit")
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set for public story packet audit")
    try:
        marker, marker_etag = _remote_marker(client, target_bucket)
        if marker is None:
            raise ValueError("public story packet marker is absent")
        if marker_etag is None:
            raise ValueError("public story packet root ETag is absent before audit")
        marker_raw = canonical_json_bytes(marker)
        _validate_manifest(marker)
        generation_id = _generation_id(marker)
        if require_publication_journal:
            _assert_current_generation_is_finalized(
                marker,
                s3=client,
                bucket=target_bucket,
            )
        immutable = client.get_object(
            Bucket=target_bucket, Key=f"{PREFIX}/generations/{generation_id}/manifest.json",
        )["Body"].read()
        if immutable != marker_raw:
            raise ValueError("immutable generation manifest differs from root marker")
        seen = {generation_id}
        parent_manifests: dict[str, bytes] = {}
        parent = marker.get("parent_generation_id")
        while parent is not None:
            if not isinstance(parent, str) or parent in seen:
                raise ValueError("generation parent chain is invalid")
            seen.add(parent)
            parent_raw = client.get_object(
                Bucket=target_bucket, Key=f"{PREFIX}/generations/{parent}/manifest.json",
            )["Body"].read()
            parent_manifest = _canonical_object(parent_raw, label="public story packet parent manifest")
            _validate_manifest(parent_manifest)
            if _generation_id(parent_manifest) != parent:
                raise ValueError("generation parent receipt mismatch")
            parent_manifests[parent] = parent_raw
            parent = parent_manifest.get("parent_generation_id")
        with tempfile.TemporaryDirectory(prefix="earnings-story-packets-audit-") as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_bytes(marker_raw)
            generation = root / "generations" / generation_id
            generation.mkdir(parents=True)
            (generation / "manifest.json").write_bytes(immutable)
            for parent_id, parent_raw in parent_manifests.items():
                parent_path = root / "generations" / parent_id
                parent_path.mkdir(parents=True)
                (parent_path / "manifest.json").write_bytes(parent_raw)
            receipts: dict[str, Mapping[str, Any]] = {}
            for receipt in _file_receipts(marker).values():
                receipts[str(receipt["object_key"])] = receipt
            for parent_raw in parent_manifests.values():
                parent_manifest = _canonical_object(parent_raw, label="public story packet parent manifest")
                for receipt in _file_receipts(parent_manifest).values():
                    object_key = str(receipt["object_key"])
                    prior = receipts.get(object_key)
                    if prior is not None and dict(prior) != dict(receipt):
                        raise ValueError(f"lineage object receipt collision: {object_key}")
                    receipts[object_key] = receipt
            for object_key, receipt in receipts.items():
                body = client.get_object(Bucket=target_bucket, Key=f"{PREFIX}/{object_key}")["Body"].read()
                if len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
                    raise ValueError(f"public object receipt mismatch: {object_key}")
                _canonical_object(body, label=f"public story packet object {object_key}")
                path = root / object_key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            health = _verify_store(root, marker)
            story_chain = [marker] + [
                _canonical_object(parent_raw, label="public story packet parent manifest")
                for parent_raw in parent_manifests.values()
            ]
            _audit_bound_evidence(
                client,
                target_bucket,
                story_root=root,
                story_manifests=story_chain,
            )
        if health.get("status") != "ready":
            raise ValueError("full public story packet replay is not ready")
        current, current_etag = _remote_marker(client, target_bucket)
        if current is None:
            raise ValueError("public story packet root changed during audit")
        if current_etag is None:
            raise ValueError("public story packet root ETag is absent after audit")
        if current_etag != marker_etag or canonical_json_bytes(current) != marker_raw:
            raise ValueError("public story packet root changed during audit")
        if require_publication_journal:
            _assert_current_generation_is_finalized(
                current,
                s3=client,
                bucket=target_bucket,
            )
        final, final_etag = _remote_marker(client, target_bucket)
        if (
            final is None
            or final_etag != current_etag
            or canonical_json_bytes(final) != canonical_json_bytes(current)
        ):
            raise ValueError("public story packet root moved during journal proof")
        return {
            "schema": ROOT_AUDIT_SCHEMA,
            "authority": AUTHORITY,
            "generation_id": generation_id,
            "marker_sha256": sha256_bytes(marker_raw),
            # Bind the second read: it is the identity proven current after
            # every immutable object and evidence receipt was replayed.
            "marker_etag": final_etag,
            "manifest": dict(marker),
            "execution": dict(EXECUTION_RECEIPT),
        }, dict(health)
    except ImmutableAddressIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"public earnings story packet audit failed: {exc}") from exc


def hydrate_and_verify_current_story_root(
    *, s3: Any | None = None, bucket: str | None = None,
) -> dict[str, Any]:
    """Return a sealed binding for a fully replayed, still-current R2 root.

    The helper deliberately rereads the sole mutable root marker after every
    lineage/evidence replay.  A root move during the audit is a race, not a
    harmless refresh: callers must start over rather than stage a packet from a
    root that is no longer current.
    """
    binding, _health = _hydrate_and_verify_current_story_root(s3=s3, bucket=bucket)
    return binding


def assert_story_root_binding_current(
    binding: object,
    *,
    s3: Any | None = None,
    bucket: str | None = None,
) -> None:
    """Re-prove that an audited root is still the sole mutable R2 marker.

    Admission uses this immediately before a writer call and again after the
    staged artifact is produced.  Canonical bytes and the transport identity
    must both match; a same-body ETag change is a race, not permission to keep
    working from a detached audit.
    """
    validate_story_root_audit_binding(binding)
    assert isinstance(binding, Mapping)
    client = s3 if s3 is not None else _client()
    if client is None:
        raise ImmutableAddressIntegrityError("R2 credentials are required for a story root currentness check")
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set for a story root currentness check")
    current, current_etag = _remote_marker(client, target_bucket)
    if (
        current is None
        or current_etag is None
        or current_etag != binding["marker_etag"]
        or canonical_json_bytes(current) != canonical_json_bytes(binding["manifest"])
    ):
        raise ImmutableAddressIntegrityError("public earnings story packet root no longer matches admission audit")
    _assert_current_generation_is_finalized(
        current,
        s3=client,
        bucket=target_bucket,
    )
    # Close the root/List TOCTOU as far as a multi-object store permits.
    final, final_etag = _remote_marker(client, target_bucket)
    if (
        final is None
        or final_etag != current_etag
        or canonical_json_bytes(final) != canonical_json_bytes(current)
    ):
        raise ImmutableAddressIntegrityError("public earnings story packet root moved during currentness proof")


def load_exact_current_story_packet(
    binding: object,
    *,
    generation_id: str,
    packet_id: str,
    story_revision_id: str,
    s3: Any | None = None,
    bucket: str | None = None,
) -> dict[str, Any]:
    """Fetch one exact packet named by the still-current audited root.

    The caller supplies immutable identities only.  The packet path, policy,
    tier, Press slot, and receipts all come from the audited catalog.  This
    function performs a second current-root check after the object read so a
    root move between audit and packet hydration cannot reach the model rail.
    """
    validate_story_root_audit_binding(binding)
    assert isinstance(binding, Mapping)
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(generation_id):
        raise ImmutableAddressIntegrityError("requested story generation id is invalid")
    if not isinstance(packet_id, str) or not _PACKET_ID.fullmatch(packet_id):
        raise ImmutableAddressIntegrityError("requested story packet id is invalid")
    if not isinstance(story_revision_id, str) or not _STORY_REVISION_ID.fullmatch(story_revision_id):
        raise ImmutableAddressIntegrityError("requested story revision id is invalid")
    if generation_id != binding["generation_id"]:
        raise ImmutableAddressIntegrityError("requested story generation is not the current audited root")

    manifest = binding["manifest"]
    assert isinstance(manifest, Mapping)
    matches = [
        (str(key), index)
        for key, index in manifest["packets"].items()
        if isinstance(index, Mapping)
        and index.get("packet_id") == packet_id
        and index.get("story_revision_id") == story_revision_id
    ]
    if len(matches) != 1:
        raise ImmutableAddressIntegrityError("requested packet and story revision do not identify one current packet")
    _event_key, index = matches[0]
    object_key = index.get("object_key")
    receipt = manifest["files"].get(object_key) if isinstance(object_key, str) else None
    if not isinstance(receipt, Mapping) or receipt.get("object_key") != object_key:
        raise ImmutableAddressIntegrityError("current packet object receipt is absent")

    client = s3 if s3 is not None else _client()
    if client is None:
        raise ImmutableAddressIntegrityError("R2 credentials are required to read a current story packet")
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set to read a current story packet")
    try:
        body = client.get_object(Bucket=target_bucket, Key=f"{PREFIX}/{object_key}")["Body"].read()
        packet = _canonical_object(body, label="current admitted story packet")
        if len(body) != receipt.get("bytes") or sha256_bytes(body) != receipt.get("sha256"):
            raise ValueError("packet bytes differ from the current root receipt")
        from engine.earnings_narrative.story_packets import validate_story_packet  # noqa: PLC0415

        validate_story_packet(packet, policy=manifest["policy"]["snapshot"])
        if (
            packet.get("packet_id") != packet_id
            or packet.get("story", {}).get("story_revision_id") != story_revision_id
        ):
            raise ValueError("packet body differs from requested immutable identities")
    except ImmutableAddressIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"cannot hydrate exact current story packet: {exc}") from exc

    assert_story_root_binding_current(binding, s3=client, bucket=target_bucket)
    return packet


def audit_remote_generation(*, s3: Any | None = None, bucket: str | None = None) -> dict[str, Any]:
    """Replay every public root receipt and all immutable objects it cites."""
    _binding, health = _hydrate_and_verify_current_story_root(s3=s3, bucket=bucket)
    return health


def initialize_publication_journal(
    *,
    expected_generation_id: str,
    expected_manifest_sha256: str,
    s3: Any | None = None,
    bucket: str | None = None,
) -> dict[str, Any]:
    """Explicitly establish the immutable high-water anchor for a legacy root.

    This is a one-time trust ceremony, not part of routine publication.  The
    operator supplies the generation and canonical manifest digest observed on
    the already-audited public release.  Before anchoring, the complete packet,
    ancestry, and evidence closure is replayed without assuming a journal.
    """
    if not isinstance(expected_generation_id, str) or not _GENERATION_ID.fullmatch(expected_generation_id):
        raise ImmutableAddressIntegrityError("expected journal anchor generation id is invalid")
    if not isinstance(expected_manifest_sha256, str) or not _SHA256.fullmatch(expected_manifest_sha256):
        raise ImmutableAddressIntegrityError("expected journal anchor manifest sha256 is invalid")
    client = s3 if s3 is not None else _client()
    if client is None:
        raise ImmutableAddressIntegrityError("R2 credentials are required to initialize publication journal")
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set to initialize publication journal")

    existing = _load_publication_journal(
        client,
        target_bucket,
        current_manifest=None,
        require_resolved=True,
        allow_empty=True,
    )
    binding, health = _hydrate_and_verify_current_story_root(
        s3=client,
        bucket=target_bucket,
        require_publication_journal=False,
    )
    if (
        binding["generation_id"] != expected_generation_id
        or binding["marker_sha256"] != expected_manifest_sha256
    ):
        raise ImmutableAddressIntegrityError("public story packet root differs from requested journal anchor")
    manifest = binding["manifest"]
    assert isinstance(manifest, Mapping)
    if existing is not None:
        _load_publication_journal(
            client,
            target_bucket,
            current_manifest=manifest,
            require_resolved=True,
        )
        if existing["anchor_generation_id"] != expected_generation_id:
            raise ImmutableAddressIntegrityError("publication journal already has a different anchor")
        return {**dict(health), "journal": "already_initialized"}

    current, current_etag = _remote_marker(client, target_bucket)
    if (
        current is None
        or current_etag != binding["marker_etag"]
        or canonical_json_bytes(current) != canonical_json_bytes(manifest)
    ):
        raise ImmutableAddressIntegrityError("public story packet root moved before journal initialization")
    anchor = _anchor_receipt(manifest)
    _put_immutable(
        client,
        target_bucket,
        _journal_key("anchors", expected_generation_id),
        canonical_json_bytes(anchor),
        dry_run=False,
    )
    final, final_etag = _remote_marker(client, target_bucket)
    if (
        final is None
        or final_etag != current_etag
        or canonical_json_bytes(final) != canonical_json_bytes(current)
    ):
        raise ImmutableAddressIntegrityError("public story packet root moved during journal initialization")
    _load_publication_journal(
        client,
        target_bucket,
        current_manifest=final,
        require_resolved=True,
    )
    return {**dict(health), "journal": "initialized"}


def publish(
    out_dir: Path,
    *,
    dry_run: bool = False,
    expected_manifest_etag: str | None = None,
    expected_base_marker_sha256: str | None = None,
    require_absent_root: bool = False,
    s3: Any | None = None,
    bucket: str | None = None,
) -> int:
    """Publish one ready deterministic packet catalog; no credentials is a no-op."""
    client = s3 if s3 is not None else _client()
    if client is None:
        log.info("no R2 credentials — skip earnings story packet publication")
        return 0
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        log.error("R2_BUCKET not set")
        return 1
    manifest = _read_local_manifest(Path(out_dir))
    if manifest is None:
        log.error("refusing unreadable earnings story packet tree")
        return 1
    try:
        _validate_manifest(manifest)
        if manifest.get("status") != "ready":
            raise ImmutableAddressIntegrityError("only ready story packet catalogs may advance the public root")
        _catalog_keys(manifest)
        _validate_staging(Path(out_dir), manifest)
        remote, remote_etag = _remote_marker(client, target_bucket)
        if remote is not None and remote_etag is None:
            raise ImmutableAddressIntegrityError(
                "current story packet root ETag is required before publication"
            )
        generation_id = _generation_id(manifest)
        journal = _load_publication_journal(
            client,
            target_bucket,
            current_manifest=remote,
            require_resolved=False,
            allow_empty=True,
        )
        if remote is not None:
            _validate_manifest(remote)
            _catalog_keys(remote)
            if journal is None and not dry_run:
                raise ImmutableAddressIntegrityError(
                    "existing story packet root has no publication journal; "
                    "run the explicit expected-generation/manifest initialization first"
                )
            elif journal is not None:
                unresolved = journal.get("unresolved_transition")
                if isinstance(unresolved, Mapping):
                    pending_generation = str(unresolved["generation_id"])
                    current_generation = _generation_id(remote)
                    if current_generation == pending_generation and not dry_run:
                        # The root CAS succeeded but the worker stopped before
                        # its commit receipt.  Current==candidate makes this
                        # repair unambiguous and idempotent.
                        commit = _commit_receipt(unresolved)
                        _put_immutable(
                            client,
                            target_bucket,
                            _journal_key("commits", pending_generation),
                            canonical_json_bytes(commit),
                            dry_run=False,
                        )
                        confirmed, confirmed_etag = _remote_marker(client, target_bucket)
                        if (
                            confirmed is None
                            or confirmed_etag != remote_etag
                            or canonical_json_bytes(confirmed) != canonical_json_bytes(remote)
                        ):
                            raise ImmutableAddressIntegrityError(
                                "story packet root moved while repairing publication commit"
                            )
                        journal = _load_publication_journal(
                            client,
                            target_bucket,
                            current_manifest=remote,
                            require_resolved=True,
                        )
                    elif (
                        current_generation != str(journal["tip_generation_id"])
                        or pending_generation != generation_id
                        or canonical_json_bytes(unresolved) != canonical_json_bytes(_transition_receipt(manifest))
                    ):
                        return PUBLISH_CONFLICT
                else:
                    _load_publication_journal(
                        client,
                        target_bucket,
                        current_manifest=remote,
                        require_resolved=True,
                    )
        elif journal is not None:
            # A first-root anchor is written before If-None-Match.  Only the
            # exact same generation may retry that interrupted first publish.
            if (
                journal.get("transition_count") != 0
                or journal.get("commit_count") != 0
                or journal.get("anchor_generation_id") != generation_id
                or manifest.get("parent_generation_id") is not None
            ):
                return PUBLISH_CONFLICT
        remote_digest = sha256_bytes(canonical_json_bytes(remote)) if remote is not None else None
        if remote is not None and canonical_json_bytes(remote) == canonical_json_bytes(manifest):
            return 0
        if remote is None:
            if manifest.get("parent_generation_id") is not None:
                return PUBLISH_CONFLICT
        elif manifest.get("parent_generation_id") != remote.get("generation_id"):
            return PUBLISH_CONFLICT
        if expected_base_marker_sha256 is not None and remote_digest != expected_base_marker_sha256:
            return PUBLISH_CONFLICT
        if require_absent_root and remote is not None:
            return PUBLISH_CONFLICT
        if not _shrink_allowed(manifest, remote):
            log.error("refusing story packet root shrink below last-good ready packet set")
            return 1
        objects: dict[str, bytes] = {}
        for relative, receipt in _changed_receipts(manifest, remote):
            object_key = str(receipt["object_key"])
            body = (Path(out_dir) / object_key).read_bytes()
            prior = objects.get(object_key)
            if prior is not None and prior != body:
                raise ImmutableAddressIntegrityError(f"content-addressed object collision: {object_key}")
            objects[object_key] = body
        errors: list[Exception] = []
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="earnings-story-packets-r2") as pool:
            futures = [
                pool.submit(_put_immutable, client, target_bucket, f"{PREFIX}/{key}", body, dry_run=dry_run)
                for key, body in sorted(objects.items())
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        if errors:
            raise errors[0]
        generation_manifest = (Path(out_dir) / "generations" / generation_id / "manifest.json").read_bytes()
        _put_immutable(
            client, target_bucket, f"{PREFIX}/generations/{generation_id}/manifest.json",
            generation_manifest, dry_run=dry_run,
        )
        if dry_run:
            return 0
        transition: dict[str, Any] | None = None
        if remote is None:
            anchor = _anchor_receipt(manifest)
            try:
                _put_immutable(
                    client,
                    target_bucket,
                    _journal_key("anchors", generation_id),
                    canonical_json_bytes(anchor),
                    dry_run=False,
                )
            except ImmutableCreateConflict:
                return PUBLISH_CONFLICT
            confirmed, confirmed_etag = _remote_marker(client, target_bucket)
            if confirmed is not None or confirmed_etag is not None:
                return PUBLISH_CONFLICT
        else:
            transition = _transition_receipt(manifest)
            try:
                _put_immutable(
                    client,
                    target_bucket,
                    _journal_key("transitions", str(transition["parent_generation_id"])),
                    canonical_json_bytes(transition),
                    dry_run=False,
                )
            except ImmutableCreateConflict:
                return PUBLISH_CONFLICT
            confirmed, confirmed_etag = _remote_marker(client, target_bucket)
            if (
                confirmed is None
                or confirmed_etag != remote_etag
                or canonical_json_bytes(confirmed) != canonical_json_bytes(remote)
            ):
                return PUBLISH_CONFLICT
            pending = _load_publication_journal(
                client,
                target_bucket,
                current_manifest=remote,
                require_resolved=False,
            )
            if (
                not isinstance(pending.get("unresolved_transition"), Mapping)
                or canonical_json_bytes(pending["unresolved_transition"]) != canonical_json_bytes(transition)
                or pending.get("tip_generation_id") != remote.get("generation_id")
            ):
                return PUBLISH_CONFLICT
        marker = (Path(out_dir) / "manifest.json").read_bytes()
        args: dict[str, Any] = {
            "Bucket": target_bucket,
            "Key": f"{PREFIX}/manifest.json",
            "Body": marker,
            "ContentType": "application/json",
            "Metadata": {"sha256": sha256_bytes(marker), "generation-id": generation_id},
        }
        condition = expected_manifest_etag if expected_manifest_etag is not None else remote_etag
        if condition:
            args["IfMatch"] = condition
        else:
            args["IfNoneMatch"] = "*"
        try:
            client.put_object(**args)
        except Exception as exc:  # noqa: BLE001
            if _is_precondition_failed(exc):
                return PUBLISH_CONFLICT
            raise
        if transition is not None:
            commit = _commit_receipt(transition)
            _put_immutable(
                client,
                target_bucket,
                _journal_key("commits", generation_id),
                canonical_json_bytes(commit),
                dry_run=False,
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("earnings story packet publication failed: %s", exc)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-remote", action="store_true", help="Read and replay the complete public packet catalog")
    parser.add_argument("--initialize-journal", action="store_true", help="Explicitly anchor one already-audited legacy root")
    parser.add_argument("--expected-generation-id")
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    if args.audit_remote and args.initialize_journal:
        parser.error("--audit-remote and --initialize-journal are mutually exclusive")
    if args.initialize_journal:
        if not args.expected_generation_id or not args.expected_manifest_sha256:
            parser.error("journal initialization requires both expected immutable root values")
        try:
            health = initialize_publication_journal(
                expected_generation_id=args.expected_generation_id,
                expected_manifest_sha256=args.expected_manifest_sha256,
            )
        except ImmutableAddressIntegrityError as exc:
            print(f"earnings story packets: journal initialization failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(health, sort_keys=True))
        return 0
    if args.audit_remote:
        try:
            health = audit_remote_generation()
        except ImmutableAddressIntegrityError as exc:
            print(f"earnings story packets: public audit failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(health, sort_keys=True))
        return 0
    if args.out_dir is None:
        parser.error("--out-dir is required unless --audit-remote is used")
    return publish(args.out_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
