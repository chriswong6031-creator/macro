"""Publish verified immutable earnings-story packet generations to R2.

The deterministic packet compiler is the only producer of this projection.
This transport never picks a promotion tier, invokes a model, or stages Press
content.  It verifies the local catalog, creates every content-addressed
object with ``If-None-Match: *``, writes the immutable generation manifest,
and only then moves the sole mutable root marker with compare-and-swap.
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
from engine.earnings_narrative.admission import ROOT_AUDIT_SCHEMA


log = logging.getLogger("publish_earnings_story_packets_r2")
PREFIX = "earnings_story_packets"
EVIDENCE_PREFIX = "earnings_evidence"
PUBLISH_CONFLICT = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ImmutableAddressIntegrityError(RuntimeError):
    """An immutable address or the public catalog has invalid receipts."""


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
        raise ImmutableAddressIntegrityError(f"immutable object byte receipt mismatch: {key}")
    metadata = head.get("Metadata", {})
    metadata_sha = metadata.get("sha256") if isinstance(metadata, Mapping) else None
    if metadata_sha == digest:
        return True
    try:
        existing = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"cannot read immutable object: {key}") from exc
    if not isinstance(existing, bytes) or existing != body or sha256_bytes(existing) != digest:
        raise ImmutableAddressIntegrityError(f"immutable object byte receipt mismatch: {key}")
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
        if _is_precondition_failed(exc) and _existing_immutable_matches(s3, bucket, key, body):
            return
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
    *, s3: Any | None = None, bucket: str | None = None,
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
        return {
            "schema": ROOT_AUDIT_SCHEMA,
            "authority": AUTHORITY,
            "generation_id": generation_id,
            "marker_sha256": sha256_bytes(marker_raw),
            # Bind the second read: it is the identity proven current after
            # every immutable object and evidence receipt was replayed.
            "marker_etag": current_etag,
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


def audit_remote_generation(*, s3: Any | None = None, bucket: str | None = None) -> dict[str, Any]:
    """Replay every public root receipt and all immutable objects it cites."""
    _binding, health = _hydrate_and_verify_current_story_root(s3=s3, bucket=bucket)
    return health


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
        if remote is not None:
            _validate_manifest(remote)
            _catalog_keys(remote)
        remote_digest = sha256_bytes(canonical_json_bytes(remote)) if remote is not None else None
        if remote is not None and canonical_json_bytes(remote) == canonical_json_bytes(manifest):
            return 0
        generation_id = _generation_id(manifest)
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
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("earnings story packet publication failed: %s", exc)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-remote", action="store_true", help="Read and replay the complete public packet catalog")
    args = parser.parse_args(argv)
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
