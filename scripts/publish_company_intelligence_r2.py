"""Publish immutable Company Intelligence generations to R2.

Generation objects are uploaded before the single mutable manifest marker.  A
manifest conditional write makes concurrent publishers fail closed instead of
silently moving a consumer to a partial or stale generation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.company_intelligence.contracts import bytes_sha256, canonical_json_bytes
from engine.company_intelligence.health import enforce_shrink_floor, validate_generation


log = logging.getLogger("publish_company_intelligence_r2")
_PREFIX = "company_intelligence"
PUBLISH_CONFLICT = 2
UPLOAD_WORKERS = 8


class ImmutableAddressIntegrityError(RuntimeError):
    """A generation-addressed key already exists but is not byte-identical."""


def _client():
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
        kwargs: dict[str, Any] = {
            "region_name": "auto", "signature_version": "s3v4",
            "max_pool_connections": 8, "retries": {"max_attempts": 4, "mode": "standard"},
        }
        try:
            config = Config(**kwargs, request_checksum_calculation="when_required", response_checksum_validation="when_required")
        except TypeError:
            config = Config(**kwargs)
        return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=config)
    except ImportError:
        log.warning("boto3 not installed — cannot publish company intelligence")
        return None


def _read_manifest(out_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _remote_manifest_snapshot(s3: Any, bucket: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = s3.get_object(Bucket=bucket, Key=f"{_PREFIX}/manifest.json")
        payload = json.loads(response["Body"].read())
        return (payload if isinstance(payload, dict) else None, str(response.get("ETag") or "") or None)
    except Exception:  # noqa: BLE001 - absent first marker is normal
        return None, None


def _is_precondition_failed(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    meta = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    return str(error.get("Code") or "") in {"412", "PreconditionFailed"} or int(meta.get("HTTPStatusCode") or 0) == 412


def _is_not_found(exc: Exception) -> bool:
    """Recognise only explicit absent-object responses; auth errors are fatal."""
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    meta = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    code = str(error.get("Code") or "").lower()
    status = int(meta.get("HTTPStatusCode") or 0)
    if code in {"404", "nosuchkey", "notfound", "no_such_key"} or status == 404:
        return True
    # The dependency-free fake used by unit tests represents an absent key this
    # way.  Production SDK exceptions above remain the authoritative path.
    return type(exc) is RuntimeError and str(exc).strip().lower() in {"missing", "not found"}


def _read_remote_immutable(s3: Any, bucket: str, key: str) -> tuple[bytes, Mapping[str, Any], int | None] | None:
    """Read an immutable object only when it already exists.

    A missing metadata checksum is *not* treated as a missing key.  We read
    bytes as well because metadata alone can be stale or maliciously wrong.
    """
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        raise ImmutableAddressIntegrityError(f"cannot determine whether immutable key exists: {key}") from exc
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        stream = response["Body"]
        body = stream.read()
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"cannot read existing immutable key: {key}") from exc
    if not isinstance(body, bytes):
        raise ImmutableAddressIntegrityError(f"existing immutable key did not return bytes: {key}")
    metadata = head.get("Metadata") or {}
    if not isinstance(metadata, Mapping):
        raise ImmutableAddressIntegrityError(f"existing immutable key has invalid metadata: {key}")
    content_length = head.get("ContentLength")
    if content_length is not None and (isinstance(content_length, bool) or not isinstance(content_length, int)):
        raise ImmutableAddressIntegrityError(f"existing immutable key has invalid byte metadata: {key}")
    return body, metadata, content_length


def _immutable_remote_matches(
    s3: Any,
    bucket: str,
    key: str,
    expected_body: bytes,
    expected_sha256: str,
) -> bool:
    """Return true for an exact immutable no-op; reject every collision."""
    remote = _read_remote_immutable(s3, bucket, key)
    if remote is None:
        return False
    body, metadata, declared_bytes = remote
    remote_sha = metadata.get("sha256")
    if (
        remote_sha != expected_sha256
        or declared_bytes != len(expected_body)
        or len(body) != len(expected_body)
        or sha256(body).hexdigest() != expected_sha256
        or body != expected_body
    ):
        raise ImmutableAddressIntegrityError(f"immutable key collision: {key}")
    return True


def _publish_immutable_object(
    s3: Any,
    bucket: str,
    key: str,
    body: bytes,
    expected_sha256: str,
    *,
    dry_run: bool,
) -> None:
    """Create an immutable key once, or prove its existing exact identity."""
    if _immutable_remote_matches(s3, bucket, key, body, expected_sha256):
        return
    if dry_run:
        return
    args = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": "application/json",
        "Metadata": {"sha256": expected_sha256},
        # R2/S3 conditional create prevents a race from turning this write
        # into an overwrite.  An endpoint that cannot honour it fails closed.
        "IfNoneMatch": "*",
    }
    try:
        s3.put_object(**args)
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            # A competing publisher won between our head and put.  Only an
            # exact byte/metadata match is a safe retry/no-op.
            if _immutable_remote_matches(s3, bucket, key, body, expected_sha256):
                return
        raise ImmutableAddressIntegrityError(f"immutable key create failed: {key}") from exc


def publish(
    out_dir: Path,
    *,
    dry_run: bool = False,
    expected_manifest_etag: str | None = None,
    s3: Any | None = None,
    bucket: str | None = None,
) -> int:
    """Publish a validated tree; no credentials is a deliberate no-op."""
    client = s3 if s3 is not None else _client()
    if client is None:
        log.info("no R2 credentials — skip company intelligence publish")
        return 0
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        log.error("R2_BUCKET not set")
        return 1
    manifest = _read_manifest(out_dir)
    health = validate_generation(out_dir, manifest)
    if health["status"] != "ready" or manifest is None:
        log.error("refusing invalid company intelligence generation: %s", ", ".join(health["warnings"]))
        return 1
    remote_manifest, remote_etag = _remote_manifest_snapshot(client, target_bucket)
    # A retry after a successful promotion is common in the scheduled refresh
    # loop.  Do not rewrite immutable objects or advance the marker when the
    # remote root already names the byte-equivalent semantic generation.
    if remote_manifest is not None and canonical_json_bytes(remote_manifest) == canonical_json_bytes(manifest):
        log.info("company intelligence generation %s already promoted", manifest.get("generation_id"))
        return 0
    allowed, reason = enforce_shrink_floor(manifest, remote_manifest)
    if not allowed:
        log.error("refusing company intelligence publish: %s", reason)
        return 1
    generation_id = str(manifest["generation_id"])
    errors = 0
    # Every per-company immutable object is written before either generation or
    # root manifest; a consumer can therefore only discover a complete tree.
    def upload_company(item: tuple[str, Mapping[str, Any]]) -> tuple[str, Exception | None]:
        relative, block = item
        path = out_dir / "generations" / generation_id / relative
        key = f"{_PREFIX}/generations/{generation_id}/{relative}"
        expected_sha = str(block["sha256"])
        try:
            _publish_immutable_object(
                client,
                target_bucket,
                key,
                path.read_bytes(),
                expected_sha,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            return key, exc
        return key, None

    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS, thread_name_prefix="company-intelligence-r2") as pool:
        futures = [pool.submit(upload_company, item) for item in sorted(manifest["files"].items())]
        for future in as_completed(futures):
            key, exc = future.result()
            if exc is not None:
                log.error("payload upload failed: %s (%s)", key, exc)
                errors += 1
    generation_manifest = out_dir / "generations" / generation_id / "manifest.json"
    generation_key = f"{_PREFIX}/generations/{generation_id}/manifest.json"
    if not errors:
        try:
            _publish_immutable_object(
                client,
                target_bucket,
                generation_key,
                generation_manifest.read_bytes(),
                bytes_sha256(generation_manifest),
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("generation manifest upload failed: %s", exc)
            errors += 1
    if errors:
        log.error("payload publish incomplete; root manifest not promoted")
        return 1
    if dry_run:
        return 0
    marker = out_dir / "manifest.json"
    marker_sha = bytes_sha256(marker)
    put_args: dict[str, Any] = {
        "Bucket": target_bucket, "Key": f"{_PREFIX}/manifest.json", "Body": marker.read_bytes(),
        "ContentType": "application/json", "Metadata": {"sha256": marker_sha, "generation-id": generation_id},
    }
    condition = expected_manifest_etag if expected_manifest_etag is not None else remote_etag
    if condition:
        put_args["IfMatch"] = condition
    else:
        put_args["IfNoneMatch"] = "*"
    try:
        client.put_object(**put_args)
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            log.warning("manifest promotion lost compare-and-swap for %s", generation_id)
            return PUBLISH_CONFLICT
        log.error("manifest promotion failed: %s", exc)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("data/company_intelligence"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return publish(args.out_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
