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
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import canonical_json_bytes, sha256_bytes, validate_manifest
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
        payload = json.loads(response["Body"].read())
        return (payload if isinstance(payload, dict) else None, str(response.get("ETag") or "") or None)
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
    client = s3 if s3 is not None else _client()
    if client is None:
        return None
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise ImmutableAddressIntegrityError("R2_BUCKET not set for marker hydration")
    marker, _etag = _remote_marker(client, target_bucket)
    if marker is not None:
        try:
            validate_manifest(marker)
        except Exception as exc:  # noqa: BLE001 - invalid public state cannot grant lineage.
            raise ImmutableAddressIntegrityError("current earnings evidence marker fails its contract") from exc
    return marker


def _existing_immutable(s3: Any, bucket: str, key: str) -> bytes | None:
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        raise ImmutableAddressIntegrityError(f"cannot determine immutable object state: {key}") from exc
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
    except Exception as exc:  # noqa: BLE001
        raise ImmutableAddressIntegrityError(f"cannot read immutable object: {key}") from exc
    if not isinstance(body, bytes) or int(head.get("ContentLength", -1)) != len(body):
        raise ImmutableAddressIntegrityError(f"immutable object byte receipt mismatch: {key}")
    return body


def _put_immutable(s3: Any, bucket: str, key: str, body: bytes, *, dry_run: bool) -> None:
    existing = _existing_immutable(s3, bucket, key)
    if existing is not None:
        if existing != body or sha256_bytes(existing) != sha256_bytes(body):
            raise ImmutableAddressIntegrityError(f"immutable key collision: {key}")
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
            existing = _existing_immutable(s3, bucket, key)
            if existing == body:
                return
        raise ImmutableAddressIntegrityError(f"immutable create failed: {key}") from exc


def _shrink_allowed(local: Mapping[str, Any], remote: Mapping[str, Any] | None) -> bool:
    if not isinstance(remote, Mapping) or remote.get("status") != "ready":
        return True
    remote_events = remote.get("events")
    return not isinstance(remote_events, Mapping) or len(local["events"]) >= len(remote_events)


def publish(
    out_dir: Path,
    *,
    dry_run: bool = False,
    expected_manifest_etag: str | None = None,
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
    health = validate_generation(out_dir, manifest)
    if manifest is None or health["status"] != "ready":
        log.error("refusing non-ready earnings evidence tree: %s", ", ".join(health["warnings"]))
        return 1
    try:
        remote, remote_etag = _remote_marker(client, target_bucket)
        if remote is not None and canonical_json_bytes(remote) == canonical_json_bytes(manifest):
            return 0
        if not _shrink_allowed(manifest, remote):
            log.error("refusing root marker shrink below last-good ready event count")
            return 1
        generation_id = str(manifest["generation_id"])
        generation = Path(out_dir) / "generations" / generation_id
        errors: list[Exception] = []
        def upload(item: tuple[str, Mapping[str, Any]]) -> None:
            relative, _receipt = item
            _put_immutable(client, target_bucket, f"{PREFIX}/generations/{generation_id}/{relative}", (generation / relative).read_bytes(), dry_run=dry_run)
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="earnings-evidence-r2") as pool:
            futures = [pool.submit(upload, item) for item in sorted(manifest["files"].items())]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        if errors:
            raise errors[0]
        generation_manifest = (generation / "manifest.json").read_bytes()
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
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return publish(args.out_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
