"""Publish immutable Company Institutional Context sidecars to R2.

The mutable root marker advances only after each exact object and immutable
generation manifest has either been created or byte-for-byte re-proven.
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

from engine.company_institutional_context.contracts import bytes_sha256, canonical_json_bytes
from engine.company_institutional_context.health import validate_generation


log = logging.getLogger("publish_company_institutional_context_r2")
PREFIX = "company_institutional_context"
PUBLISH_CONFLICT = 2
UPLOAD_WORKERS = 8


class ImmutableAddressIntegrityError(RuntimeError):
    """A content-addressed remote object exists with different bytes."""


def _client():
    endpoint, key, secret = os.environ.get("R2_ENDPOINT"), os.environ.get("R2_ACCESS_KEY_ID"), os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and key and secret):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
        kwargs: dict[str, Any] = {"region_name": "auto", "signature_version": "s3v4", "max_pool_connections": UPLOAD_WORKERS, "retries": {"max_attempts": 4, "mode": "standard"}}
        try:
            config = Config(**kwargs, request_checksum_calculation="when_required", response_checksum_validation="when_required")
        except TypeError:
            config = Config(**kwargs)
        return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=key, aws_secret_access_key=secret, config=config)
    except ImportError:
        log.warning("boto3 not installed — cannot publish company institutional context")
        return None


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    return str(error.get("Code") or "").lower() in {"404", "nosuchkey", "notfound", "no_such_key"} or int(metadata.get("HTTPStatusCode") or 0) == 404 or (type(exc) is RuntimeError and str(exc).strip().lower() in {"missing", "not found"})


def _is_precondition_failed(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    return str(error.get("Code") or "") in {"412", "PreconditionFailed"} or int(metadata.get("HTTPStatusCode") or 0) == 412


def _read_manifest(out_dir: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _remote_marker(s3: Any, bucket: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = s3.get_object(Bucket=bucket, Key=f"{PREFIX}/manifest.json")
        value = json.loads(response["Body"].read())
        return (value if isinstance(value, dict) else None, str(response.get("ETag") or "") or None)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None, None
        raise ImmutableAddressIntegrityError("cannot read root marker") from exc


def _read_immutable(s3: Any, bucket: str, key: str) -> tuple[bytes, Mapping[str, Any], int | None] | None:
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        raise ImmutableAddressIntegrityError(f"cannot check immutable key: {key}") from exc
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        stream = response["Body"]
        body = stream.read()
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"cannot read immutable key: {key}") from exc
    metadata = head.get("Metadata") or {}
    if not isinstance(body, bytes) or not isinstance(metadata, Mapping):
        raise ImmutableAddressIntegrityError(f"immutable key response invalid: {key}")
    return body, metadata, head.get("ContentLength")


def _publish_immutable(s3: Any, bucket: str, key: str, body: bytes, expected_sha: str, *, dry_run: bool) -> None:
    remote = _read_immutable(s3, bucket, key)
    if remote is not None:
        found, metadata, declared_bytes = remote
        if metadata.get("sha256") != expected_sha or declared_bytes != len(body) or found != body or sha256(found).hexdigest() != expected_sha:
            raise ImmutableAddressIntegrityError(f"immutable key collision: {key}")
        return
    if dry_run:
        return
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json", Metadata={"sha256": expected_sha}, IfNoneMatch="*")
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            _publish_immutable(s3, bucket, key, body, expected_sha, dry_run=dry_run)
            return
        raise ImmutableAddressIntegrityError(f"immutable key create failed: {key}") from exc


def publish(out_dir: Path, *, dry_run: bool = False, s3: Any | None = None, bucket: str | None = None) -> int:
    client = s3 if s3 is not None else _client()
    if client is None:
        log.info("no R2 credentials — skip company institutional context publish")
        return 0
    target = bucket or os.environ.get("R2_BUCKET", "")
    if not target:
        log.error("R2_BUCKET not set")
        return 1
    marker = _read_manifest(out_dir)
    health = validate_generation(out_dir, marker)
    if marker is None or health["status"] not in {"ready", "partial"}:
        log.error("refusing invalid company institutional context generation: %s", ", ".join(health["warnings"]))
        return 1
    remote, etag = _remote_marker(client, target)
    same_root = remote is not None and canonical_json_bytes(remote) == canonical_json_bytes(marker)
    generation = str(marker["generation_id"])

    def upload(item: tuple[str, Mapping[str, Any]]) -> Exception | None:
        relative, receipt = item
        try:
            _publish_immutable(client, target, f"{PREFIX}/generations/{generation}/{relative}", (out_dir / "generations" / generation / relative).read_bytes(), str(receipt["sha256"]), dry_run=dry_run)
            return None
        except Exception as exc:  # noqa: BLE001
            return exc

    failures = 0
    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as pool:
        futures = [pool.submit(upload, item) for item in sorted(marker["files"].items())]
        for future in as_completed(futures):
            if future.result() is not None:
                failures += 1
    if not failures:
        try:
            generation_manifest = out_dir / "generations" / generation / "manifest.json"
            _publish_immutable(client, target, f"{PREFIX}/generations/{generation}/manifest.json", generation_manifest.read_bytes(), bytes_sha256(generation_manifest), dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            log.error("generation manifest publish failed: %s", exc)
            failures += 1
    if failures:
        log.error("payload publish incomplete; root marker not promoted")
        return 1
    if dry_run or same_root:
        return 0
    args: dict[str, Any] = {
        "Bucket": target, "Key": f"{PREFIX}/manifest.json", "Body": (out_dir / "manifest.json").read_bytes(),
        "ContentType": "application/json", "Metadata": {"sha256": bytes_sha256(out_dir / "manifest.json"), "generation-id": generation},
    }
    if etag:
        args["IfMatch"] = etag
    else:
        args["IfNoneMatch"] = "*"
    try:
        client.put_object(**args)
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            return PUBLISH_CONFLICT
        log.error("root marker publish failed: %s", exc)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("data/company_institutional_context"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return publish(args.out_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
