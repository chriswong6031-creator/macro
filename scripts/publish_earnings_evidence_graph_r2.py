"""Publish a verified immutable earnings-evidence tree to R2.

All generation-addressed objects are conditionally created and byte-checked
before the one mutable root marker moves.  Coverage warnings remain explicit
without suppressing healthy peers; only an empty or invalid tree is ineligible.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import (
    TERMINAL_TRANSCRIPT_SCHEMA,
    canonical_json_bytes,
    canonical_transcript_body_bytes,
    sha256_bytes,
    validate_manifest,
)
from engine.earnings_narrative.health import validate_generation


log = logging.getLogger("publish_earnings_evidence_graph_r2")
PREFIX = "earnings_evidence"
PUBLISH_CONFLICT = 2


class ImmutableAddressIntegrityError(RuntimeError):
    """An immutable address exists with bytes other than its claimed hash."""


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
        log.warning("boto3 not installed — cannot publish earnings evidence")
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(region_name="auto", signature_version="s3v4", max_pool_connections=8, retries={"max_attempts": 4, "mode": "standard"}),
    )


def _read_manifest(out_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((Path(out_dir) / "manifest.json").read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


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


def _remote_marker(s3: Any, bucket: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = s3.get_object(Bucket=bucket, Key=f"{PREFIX}/manifest.json")
        raw = response["Body"].read()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
            raise ImmutableAddressIntegrityError("current earnings evidence marker is not canonical")
        return payload, str(response.get("ETag") or "") or None
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None, None
        raise ImmutableAddressIntegrityError("cannot read current earnings evidence marker") from exc


def load_remote_root_marker(*, s3: Any | None = None, bucket: str | None = None) -> dict[str, Any] | None:
    """Read the last-good public marker for correction lineage hydration.

    A worker cache is only an optimization.  When a runner starts empty, this
    keeps a corrected retained event linked to the actual R2 public revision.
    ``None`` means credentials are absent or the public marker does not exist.
    """
    marker, _etag, _digest = load_remote_root_state(s3=s3, bucket=bucket)
    return marker


def load_remote_root_state(*, s3: Any | None = None, bucket: str | None = None) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Return the validated public root plus its conditional-write identity."""
    client = s3 if s3 is not None else _client()
    if client is None:
        return None, None, None
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set for marker hydration")
    marker, etag = _remote_marker(client, target_bucket)
    if marker is not None:
        try:
            validate_manifest(marker)
        except Exception as exc:  # noqa: BLE001 - invalid public state cannot grant lineage.
            raise ImmutableAddressIntegrityError("current earnings evidence marker fails its contract") from exc
    return marker, etag, sha256_bytes(canonical_json_bytes(marker)) if marker is not None else None


def audit_remote_generation(*, s3: Any | None = None, bucket: str | None = None) -> dict[str, Any]:
    """Fetch and fully replay the public root marker and every CAS object.

    This intentionally performs the expensive end-to-end read.  It is the
    verification command for deployments and incident checks, not the normal
    six-hour no-change path.
    """
    client = s3 if s3 is not None else _client()
    if client is None:
        raise ImmutableAddressIntegrityError("R2 credentials are required for a public evidence audit")
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set for public evidence audit")
    try:
        marker_response = client.get_object(Bucket=target_bucket, Key=f"{PREFIX}/manifest.json")
        marker_raw = marker_response["Body"].read()
        marker = json.loads(marker_raw.decode("utf-8"))
        if not isinstance(marker, dict):
            raise ValueError("marker is not an object")
        validate_manifest(marker)
        if marker_raw != canonical_json_bytes(marker):
            raise ValueError("marker is not canonical")
        generation_id = str(marker["generation_id"])
        immutable = client.get_object(Bucket=target_bucket, Key=f"{PREFIX}/generations/{generation_id}/manifest.json")["Body"].read()
        if immutable != marker_raw:
            raise ValueError("immutable generation manifest differs from root marker")
        # The root is a compact, append-only catalog chain. Validate every
        # parent manifest before trusting the current snapshot's ancestry.
        seen_generations = {generation_id}
        parent_generation = marker["parent_generation_id"]
        while parent_generation is not None:
            if parent_generation in seen_generations:
                raise ValueError("generation parent chain has a cycle")
            seen_generations.add(parent_generation)
            parent_raw = client.get_object(
                Bucket=target_bucket,
                Key=f"{PREFIX}/generations/{parent_generation}/manifest.json",
            )["Body"].read()
            parent = json.loads(parent_raw.decode("utf-8"))
            if not isinstance(parent, dict):
                raise ValueError("generation parent is not an object")
            validate_manifest(parent)
            if parent_raw != canonical_json_bytes(parent) or parent["generation_id"] != parent_generation:
                raise ValueError("generation parent receipt mismatch")
            parent_generation = parent["parent_generation_id"]
        with tempfile.TemporaryDirectory(prefix="earnings-evidence-audit-") as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_bytes(marker_raw)
            generation = root / "generations" / generation_id
            generation.mkdir(parents=True)
            (generation / "manifest.json").write_bytes(immutable)
            for receipt in marker["files"].values():
                object_key = str(receipt["object_key"])
                body = client.get_object(Bucket=target_bucket, Key=f"{PREFIX}/{object_key}")["Body"].read()
                path = root / object_key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            health = validate_generation(root, marker)
        if health["status"] != "ready":
            raise ValueError("full public replay failed: " + ", ".join(health["warnings"]))
        return health
    except ImmutableAddressIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError("public earnings evidence audit failed") from exc


def _existing_immutable_matches(s3: Any, bucket: str, key: str, body: bytes) -> bool:
    """Check an existing global content-addressed object without reuploading it."""
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
    # Objects written by this publisher have a receipt-bearing metadata hash.
    # Read older/unreceipted objects once before accepting them as the same CAS
    # address; normal retained evidence never downloads its 400 MB corpus.
    if metadata_sha == digest:
        return True
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        existing = response["Body"].read()
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
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={"sha256": sha256_bytes(body)},
            IfNoneMatch="*",
        )
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            if _existing_immutable_matches(s3, bucket, key, body):
                return
        raise ImmutableAddressIntegrityError(f"immutable create failed: {key}") from exc


def _shrink_allowed(local: Mapping[str, Any], remote: Mapping[str, Any] | None) -> bool:
    if not isinstance(remote, Mapping) or remote.get("status") != "ready":
        return True
    remote_events = remote.get("events")
    local_events = local.get("events")
    if not isinstance(remote_events, Mapping) or not isinstance(local_events, Mapping):
        return False
    # Corrections may change a retained event's source revision, but a later
    # root may never drop a historical event key or replace it with another.
    return set(remote_events).issubset(local_events)


def _validate_staging(out_dir: Path, manifest: Mapping[str, Any]) -> None:
    """Validate root/immutable marker bytes and every locally staged CAS object.

    A runner may intentionally contain only this batch's three new objects;
    retained objects live at their verified public content addresses.  The full
    local health checker still validates a hydrated complete tree, while this
    gate makes a partial staging directory safe to publish as an append.
    """
    root = Path(out_dir)
    marker = canonical_json_bytes(manifest)
    if (root / "manifest.json").read_bytes() != marker:
        raise ImmutableAddressIntegrityError("local root marker bytes are not canonical")
    generation = root / "generations" / str(manifest["generation_id"])
    if (generation / "manifest.json").read_bytes() != marker:
        raise ImmutableAddressIntegrityError("local immutable manifest does not match root marker")
    for receipt in manifest["files"].values():
        path = root / str(receipt["object_key"])
        if not path.exists():
            continue
        body = path.read_bytes()
        if len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
            raise ImmutableAddressIntegrityError(f"local immutable object receipt mismatch: {path}")
        payload = json.loads(body.decode("utf-8"))
        expected = canonical_transcript_body_bytes(payload) if receipt["schema"] == TERMINAL_TRANSCRIPT_SCHEMA else canonical_json_bytes(payload)
        if body != expected:
            raise ImmutableAddressIntegrityError(f"local immutable object is not canonical: {path}")


def _changed_receipts(manifest: Mapping[str, Any], remote: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    remote_files = remote.get("files") if isinstance(remote, Mapping) else None
    if not isinstance(remote_files, Mapping):
        return [receipt for _path, receipt in sorted(manifest["files"].items())]
    return [
        receipt
        for path, receipt in sorted(manifest["files"].items())
        if remote_files.get(path) != receipt
    ]


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
    """Publish only a fully verified ready tree; absent credentials is a no-op."""
    client = s3 if s3 is not None else _client()
    if client is None:
        log.info("no R2 credentials — skip earnings evidence publication")
        return 0
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        log.error("R2_BUCKET not set")
        return 1
    manifest = _read_manifest(out_dir)
    if manifest is None:
        log.error("refusing unreadable earnings evidence tree")
        return 1
    try:
        validate_manifest(manifest)
        if manifest["status"] != "ready":
            raise ImmutableAddressIntegrityError("only ready catalogs may advance the public root")
        _validate_staging(out_dir, manifest)
        remote, remote_etag = _remote_marker(client, target_bucket)
        if remote is not None:
            validate_manifest(remote)
        remote_digest = sha256_bytes(canonical_json_bytes(remote)) if remote is not None else None
        if remote is not None and canonical_json_bytes(remote) == canonical_json_bytes(manifest):
            return 0
        if remote is None:
            if manifest["parent_generation_id"] is not None:
                return PUBLISH_CONFLICT
        elif manifest["parent_generation_id"] != remote["generation_id"]:
            return PUBLISH_CONFLICT
        if expected_base_marker_sha256 is not None and remote_digest != expected_base_marker_sha256:
            return PUBLISH_CONFLICT
        if require_absent_root and remote is not None:
            return PUBLISH_CONFLICT
        if not _shrink_allowed(manifest, remote):
            log.error("refusing root marker shrink below last-good ready event count")
            return 1
        generation_id = str(manifest["generation_id"])
        errors: list[Exception] = []
        objects: dict[str, bytes] = {}
        for receipt in _changed_receipts(manifest, remote):
            object_key = str(receipt["object_key"])
            body = (Path(out_dir) / object_key).read_bytes()
            prior = objects.get(object_key)
            if prior is not None and prior != body:
                raise ImmutableAddressIntegrityError(f"content-addressed object collision: {object_key}")
            objects[object_key] = body
        def upload(item: tuple[str, bytes]) -> None:
            object_key, body = item
            _put_immutable(client, target_bucket, f"{PREFIX}/{object_key}", body, dry_run=dry_run)
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="earnings-evidence-r2") as pool:
            futures = [pool.submit(upload, item) for item in sorted(objects.items())]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        if errors:
            raise errors[0]
        generation_manifest = (Path(out_dir) / "generations" / generation_id / "manifest.json").read_bytes()
        _put_immutable(client, target_bucket, f"{PREFIX}/generations/{generation_id}/manifest.json", generation_manifest, dry_run=dry_run)
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
        log.error("earnings evidence publication failed: %s", exc)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-remote", action="store_true", help="Read and replay the complete public CAS catalog")
    args = parser.parse_args(argv)
    if args.audit_remote:
        try:
            health = audit_remote_generation()
        except ImmutableAddressIntegrityError as exc:
            print(f"earnings evidence: public audit failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(health, sort_keys=True))
        return 0
    if args.out_dir is None:
        parser.error("--out-dir is required unless --audit-remote is used")
    return publish(args.out_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
