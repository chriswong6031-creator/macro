#!/usr/bin/env python3
"""Build and publish MSC R2.2-A Light U-CHAIN packets.

Private inputs remain under ``data/chain_snapshots``. Publication writes and
verifies every immutable root/bucket packet first, then monotonically commits
the complete ``index.json`` manifest as the sole authoritative discovery
object. Per-root ``current.json`` pointers are derivative conveniences repaired
only after that commit. No publication path rolls back or deletes remote data.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import fcntl
from hashlib import sha256
import io
import json
import logging
import os
from pathlib import Path
from numbers import Integral
import re
import sys
import tempfile
from typing import Any, Mapping, Sequence

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.options_structure_intraday import (
    CURRENT_SCHEMA,
    INDEX_SCHEMA,
    OptionsStructureIntradayError,
    build_current_pointer,
    build_index,
    build_packet,
    canonical_json_bytes,
    current_key,
    index_key,
    object_receipt,
    packet_key,
    strict_json_object,
)
from lib import config


log = logging.getLogger("build_options_structure_intraday")
_PACKET_SCHEMA_PATH = (
    _REPO_ROOT / "contracts" / "options" / "options.contract_eligibility.v1.schema.json"
)
_PACKET_VALIDATOR: Any | None = None
_AWARE_CLOCK_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)
_BUCKET_RE = re.compile(r"^(?:0\d|1\d|2[0-3]):(?:00|15|30|45)$")


class PublicationError(RuntimeError):
    """R2 publication could not preserve or prove the discovery contract."""


class ImmutableCollisionError(PublicationError):
    """A dated R2 address already carries different bytes."""


class EpochRegressionError(PublicationError):
    """A mutable discovery target is older than the already published epoch."""


class EpochCollisionError(PublicationError):
    """One epoch already exists with different immutable bindings."""


class PublicationCommitUncertainError(PublicationError):
    """The global commit may have landed, but its exact remote state is unproved."""


class PublicationRepairNeededError(PublicationError):
    """The global index committed while derivative current repair was incomplete."""

    def __init__(self, failures: Sequence[str]) -> None:
        self.index_committed = True
        self.failures = tuple(failures)
        super().__init__(
            "global index committed; derivative current repair needed: "
            + "; ".join(self.failures)
        )


class LocalCommitUncertainError(PublicationError):
    """A local mirror mutation could not prove crash-durable completion."""


@dataclass(frozen=True)
class Artifact:
    key: str
    body: bytes
    sha256: str

    @classmethod
    def from_payload(cls, key: str, payload: Mapping[str, Any]) -> "Artifact":
        body = canonical_json_bytes(payload)
        # Decode what will actually be published.  This catches duplicate keys,
        # NaN and non-object roots before any filesystem or R2 mutation.
        strict_json_object(body)
        return cls(key=key, body=body, sha256=sha256(body).hexdigest())


@dataclass(frozen=True)
class PublicationBundle:
    packets: Mapping[str, Mapping[str, Any]]
    immutable: Mapping[str, Artifact]
    currents: Mapping[str, Artifact]
    index: Artifact


@dataclass(frozen=True)
class PublicationResult:
    index_status: str
    currents_repaired: tuple[str, ...]
    currents_idempotent: tuple[str, ...]
    currents_superseded: tuple[str, ...]


@dataclass(frozen=True)
class RemoteObject:
    body: bytes
    metadata: Mapping[str, str]
    content_length: int
    etag: str | None


def _safe_root(value: object) -> str:
    # The core owns the authoritative validation; packet_key is a dependency-
    # free way to invoke it without importing a private helper.
    if (
        not isinstance(value, str)
        or value != value.strip()
        or value != value.upper()
    ):
        raise OptionsStructureIntradayError(f"unsafe root: {value!r}")
    root = value
    packet_key(root, "2000-01-03", "09:30")
    return root


def _control_integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise OptionsStructureIntradayError(f"{field} must be an integer")
    return int(value)


def _canonical_aware_clock(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _AWARE_CLOCK_RE.fullmatch(value):
        raise OptionsStructureIntradayError(f"{field} must be a canonical aware timestamp")
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise OptionsStructureIntradayError(f"{field} is not a timestamp") from exc
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise OptionsStructureIntradayError(f"{field} must be timezone-aware")
    return value


def _read_stable_parquet(path: Path) -> pd.DataFrame:
    """Read one atomically-written Parquet object or fail on a concurrent swap."""
    try:
        before = path.stat()
    except OSError as exc:
        raise OptionsStructureIntradayError(f"source missing or unreadable: {path}") from exc
    if not path.is_file() or before.st_size <= 0:
        raise OptionsStructureIntradayError(f"source is not a non-empty file: {path}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - any malformed source fails the bucket
        raise OptionsStructureIntradayError(f"malformed parquet source: {path}: {exc}") from exc
    try:
        after = path.stat()
    except OSError as exc:
        raise OptionsStructureIntradayError(f"source disappeared while reading: {path}") from exc
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise OptionsStructureIntradayError(f"source changed while reading: {path}")
    return frame


def _strict_json_path(path: Path) -> dict[str, Any]:
    try:
        return strict_json_object(path.read_bytes())
    except OSError as exc:
        raise OptionsStructureIntradayError(f"JSON source missing or unreadable: {path}") from exc


def _validate_packet_schema(packet: Mapping[str, Any]) -> None:
    global _PACKET_VALIDATOR
    if _PACKET_VALIDATOR is None:
        try:
            from jsonschema import Draft202012Validator, FormatChecker  # noqa: PLC0415
            schema = strict_json_object(_PACKET_SCHEMA_PATH.read_bytes())
            _PACKET_VALIDATOR = Draft202012Validator(schema, format_checker=FormatChecker())
        except Exception as exc:  # noqa: BLE001
            raise OptionsStructureIntradayError(f"packet schema could not be loaded: {exc}") from exc
    errors = sorted(_PACKET_VALIDATOR.iter_errors(packet), key=lambda error: list(error.path))
    if errors:
        summary = "; ".join(error.message for error in errors[:5])
        raise OptionsStructureIntradayError(f"packet schema validation failed: {summary}")


def validate_complete_meta(
    meta: Mapping[str, Any],
    *,
    session_date: str,
    snapshot_bucket: str,
    roots: Sequence[str],
) -> int:
    """Require the poller's latest cycle to attest one complete root universe."""
    requested_roots = [_safe_root(root) for root in roots]
    packet_key("META", session_date, snapshot_bucket)
    if meta.get("schema") != "chain_snapshots.meta/v1":
        raise OptionsStructureIntradayError("_meta.json schema mismatch")
    if meta.get("session_date") != session_date or meta.get("bucket") != snapshot_bucket:
        raise OptionsStructureIntradayError("_meta.json does not describe the requested session bucket")
    try:
        universe_n = _control_integer(meta["universe_n"], field="_meta.json universe_n")
        roots_ok = _control_integer(meta["roots_ok"], field="_meta.json roots_ok")
        roots_failed = _control_integer(meta["roots_failed"], field="_meta.json roots_failed")
        cadence = _control_integer(meta["cadence_min"], field="_meta.json cadence_min")
    except KeyError as exc:
        raise OptionsStructureIntradayError("_meta.json completeness counters are malformed") from exc
    if universe_n <= 0 or roots_failed != 0 or roots_ok != universe_n:
        raise OptionsStructureIntradayError(
            f"incomplete U-CHAIN bucket: ok={roots_ok} failed={roots_failed} universe={universe_n}"
        )
    if len(requested_roots) != universe_n or len(set(requested_roots)) != universe_n:
        raise OptionsStructureIntradayError(
            f"root set does not bind complete meta universe: roots={len(set(requested_roots))} universe={universe_n}"
        )
    raw_meta_roots = meta.get("roots")
    if not isinstance(raw_meta_roots, list):
        raise OptionsStructureIntradayError("_meta.json roots must bind the exact root identities")
    meta_roots = [_safe_root(value) for value in raw_meta_roots]
    if len(meta_roots) != len(set(meta_roots)) or sorted(meta_roots) != sorted(requested_roots):
        raise OptionsStructureIntradayError("_meta.json roots do not match the exact requested root set")
    if cadence != 15:
        raise OptionsStructureIntradayError("_meta.json cadence_min must be 15 for MSC R2.2-A")
    _canonical_aware_clock(meta.get("asof"), field="_meta.json asof")
    return cadence


def discover_roots(data_root: Path, session_date: str) -> list[str]:
    roots: list[str] = []
    if not data_root.is_dir():
        raise OptionsStructureIntradayError(f"chain snapshot directory absent: {data_root}")
    for child in sorted(data_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        root = _safe_root(child.name)
        if (child / f"{session_date}.parquet").is_file():
            roots.append(root)
    if not roots:
        raise OptionsStructureIntradayError(f"no roots discovered for {session_date}")
    if len(roots) != len(set(roots)):
        raise OptionsStructureIntradayError("duplicate normalized roots discovered")
    return roots


def load_prophet_context(path: Path | None) -> dict[str, Mapping[str, Any]]:
    if path is None:
        return {}
    payload = _strict_json_path(path)
    out: dict[str, Mapping[str, Any]] = {}
    for raw_root, request in payload.items():
        root = _safe_root(raw_root)
        if root in out:
            raise OptionsStructureIntradayError(f"duplicate normalized Prophet root: {root}")
        if not isinstance(request, Mapping):
            raise OptionsStructureIntradayError(f"Prophet context for {root} must be an object")
        out[root] = request
    return out


def prepare_bundle(
    data_root: Path,
    *,
    roots: Sequence[str],
    session_date: str,
    snapshot_bucket: str,
    observed_at: str | datetime,
    available_at: str | datetime | None = None,
    cadence_minutes: int = 15,
    prophet_context: Mapping[str, Mapping[str, Any]] | None = None,
) -> PublicationBundle:
    """Read every root first and produce a complete, mutation-free bundle."""
    normalized_roots = sorted(_safe_root(root) for root in roots)
    if not normalized_roots or len(normalized_roots) != len(set(normalized_roots)):
        raise OptionsStructureIntradayError("roots must be a non-empty unique set")
    contexts = prophet_context or {}
    unknown_context = sorted(set(contexts).difference(normalized_roots))
    if unknown_context:
        raise OptionsStructureIntradayError(
            f"Prophet context contains roots outside the bucket: {', '.join(unknown_context)}"
        )

    packets: dict[str, Mapping[str, Any]] = {}
    immutable: dict[str, Artifact] = {}
    receipts: dict[str, Mapping[str, Any]] = {}
    for root in normalized_roots:
        root_dir = data_root / root
        chain = _read_stable_parquet(root_dir / f"{session_date}.parquet")
        oi = _read_stable_parquet(root_dir / f"{session_date}_oi.parquet")
        packet = build_packet(
            chain,
            oi,
            root=root,
            session_date=session_date,
            snapshot_bucket=snapshot_bucket,
            observed_at=observed_at,
            available_at=available_at,
            cadence_minutes=cadence_minutes,
            prophet_request=contexts.get(root),
        )
        _validate_packet_schema(packet)
        key = packet_key(root, session_date, snapshot_bucket)
        artifact = Artifact.from_payload(key, packet)
        packets[root] = packet
        immutable[root] = artifact
        receipts[root] = object_receipt(key, artifact.body, packet)

    index_payload = build_index(list(packets.values()), receipts)
    index_artifact = Artifact.from_payload(index_key(), index_payload)
    currents: dict[str, Artifact] = {}
    for root in normalized_roots:
        pointer = build_current_pointer(
            packets[root], receipts[root], index_id=index_payload["index_id"]
        )
        currents[root] = Artifact.from_payload(current_key(root), pointer)
    return PublicationBundle(
        packets=packets,
        immutable=immutable,
        currents=currents,
        index=index_artifact,
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"cannot open local directory for durability proof: {path}"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"local directory durability is uncertain: {path}"
        ) from exc
    finally:
        os.close(descriptor)


def _ensure_durable_directory(path: Path) -> None:
    """Create each missing component and persist every parent entry."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise LocalCommitUncertainError(
                f"cannot locate an existing ancestor for local directory: {path}"
            )
        cursor = parent
    if not cursor.is_dir():
        raise LocalCommitUncertainError(
            f"local directory ancestor is not a directory: {cursor}"
        )

    # If a prior attempt created ``cursor`` but failed while syncing its parent,
    # this first fence turns an exact retry into a durability proof.
    if cursor.parent != cursor:
        _fsync_directory(cursor.parent)
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            if not directory.is_dir():
                raise LocalCommitUncertainError(
                    f"local directory path is not a directory: {directory}"
                )
        except OSError as exc:
            raise LocalCommitUncertainError(
                f"cannot create local directory: {directory}"
            ) from exc
        _fsync_directory(directory.parent)


def _durable_read(path: Path) -> bytes:
    """Read and re-fsync one exact local artifact plus its parent entry."""
    try:
        with path.open("rb") as handle:
            body = handle.read()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return body
    except LocalCommitUncertainError:
        raise
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"local artifact durability is uncertain: {path}"
        ) from exc


def _atomic_write(path: Path, body: bytes) -> None:
    """Atomically replace one local artifact and make the rename durable."""
    _ensure_durable_directory(path.parent)
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.tmp-",
            delete=False,
        ) as handle:
            tmp = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = None
        _fsync_directory(path.parent)
    except LocalCommitUncertainError:
        raise
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"local atomic commit is uncertain: {path}"
        ) from exc
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def write_local_bundle(bundle: PublicationBundle, out_dir: Path) -> None:
    """Write immutable objects, the authoritative index, then derivative currents."""
    lock_path = out_dir / "options_structure" / "msc_intraday" / ".publish.lock"
    _ensure_durable_directory(lock_path.parent)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        for root in sorted(bundle.immutable):
            artifact = bundle.immutable[root]
            target = out_dir / artifact.key
            if target.exists():
                existing = _durable_read(target)
                if existing != artifact.body:
                    raise ImmutableCollisionError(
                        f"immutable local key collision: {artifact.key}"
                    )
            else:
                _atomic_write(target, artifact.body)

        index_target = out_dir / bundle.index.key
        index_status = _classify_local(index_target, bundle.index, schema=INDEX_SCHEMA)
        if index_status == "superseded":
            raise EpochRegressionError(
                f"local authoritative index already has a newer epoch: {bundle.index.key}"
            )
        if index_status == "advance":
            _atomic_write(index_target, bundle.index.body)

        for root in sorted(bundle.currents):
            artifact = bundle.currents[root]
            target = out_dir / artifact.key
            status = _classify_local(target, artifact, schema=CURRENT_SCHEMA)
            if status == "advance":
                _atomic_write(target, artifact.body)


def _classify_local(path: Path, artifact: Artifact, *, schema: str) -> str:
    if not path.exists():
        return "advance"
    body = _durable_read(path)
    current = _epoch(strict_json_object(body), schema=schema, key=str(path))
    desired = _desired_epoch(artifact, schema=schema)
    if current > desired:
        return "superseded"
    if current == desired:
        if body == artifact.body:
            return "idempotent"
        raise EpochCollisionError(f"same local discovery epoch has different bytes: {path}")
    return "advance"


def _r2_client() -> Any | None:
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except ImportError:
        return None
    kwargs: dict[str, Any] = {
        "region_name": "auto",
        "signature_version": "s3v4",
        "retries": {"max_attempts": 4, "mode": "standard"},
    }
    try:
        client_config = Config(
            **kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        client_config = Config(**kwargs)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=client_config,
    )


def _error_code(exc: Exception) -> tuple[str, int]:
    response = getattr(exc, "response", {})
    if not isinstance(response, Mapping):
        return "", 0
    error = response.get("Error") or {}
    metadata = response.get("ResponseMetadata") or {}
    code = str(error.get("Code") or "") if isinstance(error, Mapping) else ""
    try:
        status = int(metadata.get("HTTPStatusCode") or 0) if isinstance(metadata, Mapping) else 0
    except (TypeError, ValueError):
        status = 0
    return code, status


def _is_not_found(exc: Exception) -> bool:
    code, status = _error_code(exc)
    return (
        code.lower() in {"404", "nosuchkey", "notfound", "no_such_key"}
        or status == 404
        or (type(exc) is RuntimeError and str(exc).strip().lower() in {"missing", "not found"})
    )


def _is_precondition_failed(exc: Exception) -> bool:
    code, status = _error_code(exc)
    return code.lower() in {"412", "preconditionfailed"} or status == 412


def _read_body(response: Mapping[str, Any], *, key: str) -> bytes:
    stream = response.get("Body")
    try:
        body = stream.read() if hasattr(stream, "read") else stream
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if not isinstance(body, bytes):
        raise PublicationError(f"R2 object did not return bytes: {key}")
    return body


def _remote_object(client: Any, bucket: str, key: str) -> RemoteObject | None:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = _read_body(response, key=key)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        if isinstance(exc, PublicationError):
            raise
        raise PublicationError(f"cannot read R2 key: {key}") from exc
    # One coherent GET response owns body, metadata, length, and version token.
    # Never combine a stale HEAD with a newer body from an unconditional GET.
    metadata = response.get("Metadata") or {}
    length = response.get("ContentLength")
    if not isinstance(metadata, Mapping) or isinstance(length, bool) or not isinstance(length, int):
        raise PublicationError(f"invalid R2 GET response: {key}")
    if length != len(body):
        raise PublicationError(f"R2 GET body/length mismatch: {key}")
    etag = response.get("ETag")
    return RemoteObject(
        body=body,
        metadata={str(k): str(v) for k, v in metadata.items()},
        content_length=length,
        etag=str(etag) if etag else None,
    )


def _remote_matches(remote: RemoteObject, artifact: Artifact) -> bool:
    return (
        remote.content_length == len(artifact.body)
        and remote.metadata.get("sha256") == artifact.sha256
        and sha256(remote.body).hexdigest() == artifact.sha256
        and remote.body == artifact.body
    )


def _verify_remote(client: Any, bucket: str, artifact: Artifact) -> RemoteObject:
    remote = _remote_object(client, bucket, artifact.key)
    if remote is None or not _remote_matches(remote, artifact):
        raise PublicationError(f"R2 verification failed: {artifact.key}")
    return remote


def _put_immutable(client: Any, bucket: str, artifact: Artifact) -> None:
    remote = _remote_object(client, bucket, artifact.key)
    if remote is not None:
        if not _remote_matches(remote, artifact):
            raise ImmutableCollisionError(f"immutable R2 key collision: {artifact.key}")
        return
    try:
        client.put_object(
            Bucket=bucket,
            Key=artifact.key,
            Body=artifact.body,
            ContentType="application/json",
            CacheControl="public, max-age=31536000, immutable",
            Metadata={"sha256": artifact.sha256},
            IfNoneMatch="*",
        )
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            raced = _remote_object(client, bucket, artifact.key)
            if raced is not None and _remote_matches(raced, artifact):
                return
        raise PublicationError(f"immutable R2 write failed: {artifact.key}") from exc
    _verify_remote(client, bucket, artifact)


def _epoch(payload: Mapping[str, Any], *, schema: str, key: str) -> tuple[date, int]:
    if payload.get("schema") != schema:
        raise PublicationError(f"mutable discovery schema mismatch: {key}")
    session_raw = payload.get("session_date")
    bucket_raw = payload.get("snapshot_bucket")
    if not isinstance(session_raw, str) or not isinstance(bucket_raw, str):
        raise PublicationError(f"mutable discovery epoch fields missing: {key}")
    try:
        session = date.fromisoformat(session_raw)
    except ValueError as exc:
        raise PublicationError(f"mutable discovery date malformed: {key}") from exc
    if session.isoformat() != session_raw or not _BUCKET_RE.fullmatch(bucket_raw):
        raise PublicationError(f"mutable discovery epoch non-canonical: {key}")
    expected_label = f"{session_raw}/{bucket_raw}"
    if payload.get("epoch") != expected_label:
        raise PublicationError(f"mutable discovery epoch label mismatch: {key}")
    hour, minute = (int(part) for part in bucket_raw.split(":"))
    return session, hour * 60 + minute


def _remote_epoch(
    remote: RemoteObject,
    *,
    schema: str,
    key: str,
) -> tuple[tuple[date, int], Mapping[str, Any]]:
    body_sha = sha256(remote.body).hexdigest()
    if remote.metadata.get("sha256") != body_sha:
        raise PublicationError(f"mutable discovery receipt hash mismatch: {key}")
    payload = strict_json_object(remote.body)
    return _epoch(payload, schema=schema, key=key), payload


def _desired_epoch(artifact: Artifact, *, schema: str) -> tuple[date, int]:
    return _epoch(strict_json_object(artifact.body), schema=schema, key=artifact.key)


def _mutable_put_arguments(
    artifact: Artifact,
    prior: RemoteObject | None,
    *,
    bucket: str,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "Bucket": bucket,
        "Key": artifact.key,
        "Body": artifact.body,
        "ContentType": "application/json",
        "CacheControl": "no-cache",
        "Metadata": {"sha256": artifact.sha256},
    }
    if prior is None:
        arguments["IfNoneMatch"] = "*"
    elif prior.etag:
        arguments["IfMatch"] = prior.etag
    else:
        raise PublicationError(
            f"mutable discovery key lacks ETag for compare-and-swap: {artifact.key}"
        )
    return arguments


def _classify_existing(
    remote: RemoteObject,
    artifact: Artifact,
    *,
    schema: str,
) -> str:
    desired = _desired_epoch(artifact, schema=schema)
    current, _payload = _remote_epoch(remote, schema=schema, key=artifact.key)
    if current > desired:
        return "superseded"
    if current == desired:
        if _remote_matches(remote, artifact):
            return "idempotent"
        raise EpochCollisionError(f"same discovery epoch has different bytes: {artifact.key}")
    return "advance"


def _commit_index(client: Any, bucket: str, artifact: Artifact) -> str:
    """Commit the sole authoritative discovery object with monotonic CAS."""
    for _attempt in range(2):
        prior = _remote_object(client, bucket, artifact.key)
        if prior is not None:
            classification = _classify_existing(prior, artifact, schema=INDEX_SCHEMA)
            if classification == "idempotent":
                return classification
            if classification == "superseded":
                raise EpochRegressionError(
                    f"authoritative index already has a newer epoch: {artifact.key}"
                )
        arguments = _mutable_put_arguments(artifact, prior, bucket=bucket)
        try:
            response = client.put_object(**arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_precondition_failed(exc):
                continue
            raise PublicationCommitUncertainError(
                f"global index commit outcome is uncertain: {artifact.key}: {exc}"
            ) from exc
        etag = response.get("ETag") if isinstance(response, Mapping) else None
        if not etag:
            raise PublicationCommitUncertainError(
                f"global index commit returned no ETag: {artifact.key}"
            )
        try:
            verified = _verify_remote(client, bucket, artifact)
        except Exception as exc:  # noqa: BLE001
            raise PublicationCommitUncertainError(
                f"global index commit could not be verified: {artifact.key}: {exc}"
            ) from exc
        if verified.etag != str(etag):
            raise PublicationCommitUncertainError(
                f"global index version changed during verification: {artifact.key}"
            )
        return "committed"
    raced = _remote_object(client, bucket, artifact.key)
    if raced is None:
        raise PublicationError(f"global index CAS lost without a visible winner: {artifact.key}")
    classification = _classify_existing(raced, artifact, schema=INDEX_SCHEMA)
    if classification == "idempotent":
        return classification
    if classification == "superseded":
        raise EpochRegressionError(
            f"global index CAS lost to a newer epoch: {artifact.key}"
        )
    raise PublicationError(f"global index CAS repeatedly lost to an older epoch: {artifact.key}")


def _repair_current(client: Any, bucket: str, artifact: Artifact) -> str:
    """Repair one non-authoritative convenience pointer without regression."""
    for _attempt in range(2):
        prior = _remote_object(client, bucket, artifact.key)
        if prior is not None:
            classification = _classify_existing(prior, artifact, schema=CURRENT_SCHEMA)
            if classification in {"idempotent", "superseded"}:
                return classification
        arguments = _mutable_put_arguments(artifact, prior, bucket=bucket)
        try:
            response = client.put_object(**arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_precondition_failed(exc):
                continue
            raise PublicationError(f"derivative current repair failed: {artifact.key}") from exc
        etag = response.get("ETag") if isinstance(response, Mapping) else None
        if not etag:
            raise PublicationError(f"derivative current repair returned no ETag: {artifact.key}")
        verified = _verify_remote(client, bucket, artifact)
        if verified.etag != str(etag):
            raise PublicationError(
                f"derivative current changed during verification: {artifact.key}"
            )
        return "repaired"
    raced = _remote_object(client, bucket, artifact.key)
    if raced is None:
        raise PublicationError(f"derivative current CAS lost without a winner: {artifact.key}")
    classification = _classify_existing(raced, artifact, schema=CURRENT_SCHEMA)
    if classification in {"idempotent", "superseded"}:
        return classification
    raise PublicationError(f"derivative current CAS repeatedly lost: {artifact.key}")


def publish_bundle(
    bundle: PublicationBundle,
    *,
    client: Any,
    bucket: str,
) -> PublicationResult:
    """Commit one monotonic global index, then repair derivative root currents."""
    if not bucket:
        raise PublicationError("R2 bucket is required")
    # Immutable packet orphans are safe until the global index directly binds
    # their key/hash/size receipts.
    for root in sorted(bundle.immutable):
        _put_immutable(client, bucket, bundle.immutable[root])

    index_status = _commit_index(client, bucket, bundle.index)
    repaired: list[str] = []
    idempotent: list[str] = []
    superseded: list[str] = []
    failures: list[str] = []
    for root in sorted(bundle.currents):
        artifact = bundle.currents[root]
        try:
            status = _repair_current(client, bucket, artifact)
        except PublicationError as exc:
            failures.append(f"{artifact.key}: {exc}")
            continue
        if status == "repaired":
            repaired.append(root)
        elif status == "idempotent":
            idempotent.append(root)
        else:
            superseded.append(root)
    if failures:
        raise PublicationRepairNeededError(failures)
    return PublicationResult(
        index_status=index_status,
        currents_repaired=tuple(repaired),
        currents_idempotent=tuple(idempotent),
        currents_superseded=tuple(superseded),
    )


def _resolve_clock(value: str | None) -> str:
    if not value:
        raise OptionsStructureIntradayError(
            "a durable logical-run clock is required (pass --observed-at or use _meta.json asof)"
        )
    return _canonical_aware_clock(value, field="logical-run clock")


def _parse_session(value: str | None) -> str:
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise OptionsStructureIntradayError(f"invalid --session: {value!r}") from exc
        if parsed.isoformat() != value:
            raise OptionsStructureIntradayError(f"non-canonical --session: {value!r}")
        return value
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=config.data_dir() / "chain_snapshots",
        help="Private chain_snapshots directory",
    )
    parser.add_argument("--session", help="NYSE session date (YYYY-MM-DD)")
    parser.add_argument("--bucket", help="15-minute ET bucket (HH:MM); default: _meta.json")
    parser.add_argument("--roots", nargs="+", help="Exact complete root universe; default: discover session files")
    parser.add_argument("--meta", type=Path, help="Poller _meta.json; default: DATA_ROOT/_meta.json")
    parser.add_argument("--prophet-context", type=Path, help="Optional strict JSON object keyed by root")
    parser.add_argument("--observed-at", help="UTC builder clock override for deterministic replay")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=config.data_dir() / "options_structure_intraday_r2",
        help="Local light-projection mirror root",
    )
    parser.add_argument("--no-local", action="store_true", help="Skip local mirror write")
    parser.add_argument("--publish", action="store_true", help="Publish the verified bundle to R2")
    parser.add_argument("--r2-bucket", help="R2 bucket override; default: R2_BUCKET")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        meta_path = args.meta or args.data_root / "_meta.json"
        meta = _strict_json_path(meta_path)
        session_date = _parse_session(args.session or str(meta.get("session_date") or ""))
        snapshot_bucket = args.bucket or str(meta.get("bucket") or "")
        roots = (
            sorted(_safe_root(root) for root in args.roots)
            if args.roots
            else discover_roots(args.data_root, session_date)
        )
        cadence = validate_complete_meta(
            meta,
            session_date=session_date,
            snapshot_bucket=snapshot_bucket,
            roots=roots,
        )
        # The logical clock must ultimately come from the producer-owned,
        # append-once bucket completion receipt. Mutable _meta.asof is accepted
        # only by this unwired core; an immutable-key collision still fails
        # closed rather than rewriting dated evidence.
        observed_at = _resolve_clock(args.observed_at or str(meta.get("asof") or ""))
        bundle = prepare_bundle(
            args.data_root,
            roots=roots,
            session_date=session_date,
            snapshot_bucket=snapshot_bucket,
            observed_at=observed_at,
            available_at=observed_at,
            cadence_minutes=cadence,
            prophet_context=load_prophet_context(args.prophet_context),
        )
        repair_error: PublicationRepairNeededError | None = None
        if args.publish:
            client = _r2_client()
            if client is None:
                raise PublicationError("R2 credentials or boto3 unavailable")
            bucket = args.r2_bucket or os.environ.get("R2_BUCKET", "")
            try:
                publish_bundle(bundle, client=client, bucket=bucket)
            except PublicationRepairNeededError as exc:
                # The authoritative index is already committed. Mirror it
                # locally, then return the honest repair-needed failure.
                repair_error = exc
        if not args.no_local:
            write_local_bundle(bundle, args.out_dir)
        if repair_error is not None:
            raise repair_error
        log.info(
            "Light U-CHAIN ready: session=%s bucket=%s roots=%d packet_rows=%d publish=%s",
            session_date,
            snapshot_bucket,
            len(bundle.packets),
            sum(len(packet["contracts"]) for packet in bundle.packets.values()),
            args.publish,
        )
        return 0
    except (OptionsStructureIntradayError, PublicationError) as exc:
        log.error("Light U-CHAIN failed closed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
