"""Immutable private source evidence for Market Memory W1B.0.

This module is deliberately below the Market Memory feature layer.  It admits
one bounded ALFRED ``CPIAUCSL`` full-vintage artifact, preserves the newest
source vintage as canonical immutable evidence, and exposes generation-pinned
internal reads.  It does not create an ``as_known_at`` packet, populate
``macro.regime_state``, expose an HTTP route, or write any options, board, or
Prophet ledger.

Publication order is object -> two identical receipt copies -> cumulative
generation -> ``SOURCE_HEAD.json``.  Readers trust only entries named by a
complete generation.  A later source revision appends a generation and cannot
change a reader that already pinned an older generation.
"""

from __future__ import annotations

import copy
import fcntl
import io
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from engine.neuralweb import market_memory
from engine.release_target_truth import normalize_full_vintage_frame

SOURCE_ID = "fred_alfred:CPIAUCSL"
SOURCE_SCHEMA = "market_memory.source.alfred_cpiaucsl.v1"
SOURCE_RECEIPT_SCHEMA = "market_memory.source_artifact_receipt.v1"
SOURCE_STORE_SCHEMA = "market_memory.source_store.v1"
SOURCE_GENERATION_SCHEMA = "market_memory.source_generation.v1"
SOURCE_HEAD_SCHEMA = "market_memory.source_head.v1"
SOURCE_CAPTURE_SCHEMA = "market_memory.source_capture.v1"
COLLECTOR_SCHEMA = "release_target_vintage_collection.v1"
COLLECTOR_INTEGRITY_PROFILE = "release_target_artifact_sha256_bytes.v1"

_SERIES_ID = "CPIAUCSL"
_OUTPUT_TYPE = 2
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmsstore_[a-f0-9]{64}\Z")
_RECEIPT_ID = re.compile(r"mmsrc_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmscapture_[a-f0-9]{64}\Z")
_VINTAGE_ID = re.compile(r"mmsvintage_[a-f0-9]{64}\Z")
_REVISION_ID = re.compile(r"mmsrevision_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmsgen_[a-f0-9]{64}\Z")
_RFC3339_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z"
)
_MAX_MANIFEST_BYTES = 512 * 1024
_MAX_UPSTREAM_BYTES = 32 * 1024 * 1024
_MAX_OBJECT_BYTES = 1024 * 1024
_MAX_OBJECT_ROWS = 4_096
_MAX_RECEIPT_BYTES = 64 * 1024
_MAX_STORE_BYTES = 64 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_MAX_GENERATION_BYTES = 4 * 1024 * 1024
_MAX_GENERATION_RECEIPTS = 4_096
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class MarketMemorySourceError(RuntimeError):
    """Base class for the private Market Memory source boundary."""


class SourceIntakeError(MarketMemorySourceError):
    """The supplied collector artifact cannot be admitted safely."""


class SourceStoreError(MarketMemorySourceError):
    """The private immutable source store is unavailable or corrupt."""


class SourceNotFound(MarketMemorySourceError):
    """The requested receipt is absent from the complete pinned generation."""


@dataclass(frozen=True)
class StoredSourceArtifact:
    """One source object and receipt admitted to a complete generation."""

    artifact: dict[str, Any]
    receipt: dict[str, Any]
    generation_id: str
    created: bool


@dataclass(frozen=True)
class _StoreState:
    manifest: dict[str, Any]
    head: dict[str, Any]
    generation: dict[str, Any]


@dataclass(frozen=True)
class _BoundedRead:
    body: bytes
    device: int
    inode: int
    size: int
    mtime_ns: int

    @property
    def identity(self) -> tuple[int, int, int, int]:
        return (self.device, self.inode, self.size, self.mtime_ns)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise SourceStoreError("value is not canonical finite JSON") from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON token {value}")

    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=reject_nonfinite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise SourceIntakeError(f"{label} is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise SourceIntakeError(f"{label} must be a JSON object")
    return payload


def _read_bounded(path: Path, *, limit: int, label: str) -> _BoundedRead:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SourceIntakeError(f"{label} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SourceIntakeError(f"{label} is not a regular file")
        if before.st_size <= 0 or before.st_size > limit:
            raise SourceIntakeError(f"{label} exceeds its safe size bound")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise SourceIntakeError(f"{label} cannot be read safely") from exc
    finally:
        os.close(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(body) != before.st_size:
        raise SourceIntakeError(f"{label} changed while it was read")
    if len(body) > limit:
        raise SourceIntakeError(f"{label} exceeds its safe size bound")
    return _BoundedRead(
        body=body,
        device=before.st_dev,
        inode=before.st_ino,
        size=before.st_size,
        mtime_ns=before.st_mtime_ns,
    )


def _parse_utc(value: object, *, field: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        raise SourceIntakeError(f"{field} must be an exact RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceIntakeError(f"{field} is not a valid timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise SourceIntakeError(f"{field} must be UTC")
    parsed = parsed.astimezone(timezone.utc)
    return parsed, parsed.isoformat().replace("+00:00", "Z")


def _observation_clock() -> tuple[datetime, str]:
    """Return the process-owned observation clock for trusted intake."""

    parsed = _utc_now()
    return parsed, parsed.isoformat().replace("+00:00", "Z")


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


def validate_source_store_root(root: str | Path) -> Path:
    """Resolve a private writer root and reject public or dangerously broad paths."""

    supplied = Path(root).expanduser()
    if supplied.is_symlink():
        raise SourceStoreError("Market Memory source store root is a symlink")
    candidate = supplied.resolve()
    if candidate == Path(candidate.anchor) or candidate == Path.home().resolve():
        raise SourceStoreError("Market Memory source store root is too broad")
    if candidate == _REPOSITORY_ROOT or _REPOSITORY_ROOT in candidate.parents:
        raise SourceStoreError("Market Memory source store cannot use the repository")
    if {"site", "site.served"}.intersection(candidate.parts):
        raise SourceStoreError(
            "Market Memory source store cannot use a public site root"
        )
    return candidate


def _safe_path(root: Path, *parts: str) -> Path:
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise SourceStoreError("Market Memory source store contains a symlink")
    resolved = cursor.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise SourceStoreError("Market Memory source path escaped its root")
    return cursor


def _directory_fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise SourceStoreError("Market Memory source path is a symlink")
        missing.append(cursor)
        if cursor == cursor.parent:
            raise SourceStoreError("Market Memory source store has no safe parent")
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise SourceStoreError("Market Memory source store parent is unsafe")
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise SourceStoreError("Market Memory source directory race was unsafe")
        _directory_fsync(directory.parent)


def _store_manifest_path(root: Path) -> Path:
    return _safe_path(root, "SOURCE_STORE.json")


def _head_path(root: Path) -> Path:
    return _safe_path(root, "SOURCE_HEAD.json")


def _object_path(root: Path, digest: str) -> Path:
    if not _SHA256.fullmatch(digest):
        raise SourceStoreError("source object SHA-256 is malformed")
    return _safe_path(root, "source_objects", digest[:2], f"{digest}.json")


def _receipt_path(root: Path, receipt_id: str) -> Path:
    if not _RECEIPT_ID.fullmatch(receipt_id):
        raise SourceStoreError("source receipt_id is malformed")
    digest = receipt_id.removeprefix("mmsrc_")
    return _safe_path(root, "source_receipts", digest[:2], f"{receipt_id}.json")


def _capture_path(root: Path, capture_id: str) -> Path:
    if not _CAPTURE_ID.fullmatch(capture_id):
        raise SourceStoreError("source capture_id is malformed")
    digest = capture_id.removeprefix("mmscapture_")
    return _safe_path(root, "source_captures", digest[:2], f"{capture_id}.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if not _GENERATION_ID.fullmatch(generation_id):
        raise SourceStoreError("source generation_id is malformed")
    digest = generation_id.removeprefix("mmsgen_")
    return _safe_path(root, "source_generations", digest[:2], f"{generation_id}.json")


def _read_store_object(
    path: Path, *, limit: int, label: str, not_found: bool = False
) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        if not_found:
            raise SourceNotFound(f"{label} is not in the pinned generation") from exc
        raise SourceStoreError(f"{label} is unavailable") from exc
    except OSError as exc:
        raise SourceStoreError(f"{label} cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SourceStoreError(f"{label} is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > limit:
            raise SourceStoreError(f"{label} exceeds its safe size bound")
        body = b""
        while len(body) <= limit:
            chunk = os.read(descriptor, min(65_536, limit + 1 - len(body)))
            if not chunk:
                break
            body += chunk
        after = os.fstat(descriptor)
    except OSError as exc:
        raise SourceStoreError(f"{label} cannot be read") from exc
    finally:
        os.close(descriptor)
    if (
        (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or len(body) != metadata.st_size
        or len(body) > limit
    ):
        raise SourceStoreError(f"{label} changed or exceeded its safe bound")
    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON token {value}")
            ),
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise SourceStoreError(f"{label} is not strict JSON") from exc
    if not isinstance(payload, dict) or body != _canonical_bytes(payload):
        raise SourceStoreError(f"{label} is not canonical JSON bytes")
    return payload, body


def _write_create_once(root: Path, path: Path, body: bytes, *, label: str) -> bool:
    _mkdir_durable(path.parent)
    if path.exists() or path.is_symlink():
        _payload, existing = _read_store_object(path, limit=len(body), label=label)
        if existing != body:
            raise SourceStoreError(f"immutable {label} collision")
        return False
    temporary = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(temporary, path, follow_symlinks=False)
            _directory_fsync(path.parent)
            return True
        except FileExistsError:
            _payload, existing = _read_store_object(path, limit=len(body), label=label)
            if existing != body:
                raise SourceStoreError(f"immutable {label} collision")
            return False
    except SourceStoreError:
        raise
    except OSError as exc:
        raise SourceStoreError(f"cannot publish immutable {label}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _replace_head(root: Path, head: Mapping[str, Any]) -> None:
    body = _canonical_bytes(head)
    if len(body) > _MAX_HEAD_BYTES:
        raise SourceStoreError("source HEAD exceeds its safe size bound")
    path = _head_path(root)
    if path.is_symlink():
        raise SourceStoreError("source HEAD is a symlink")
    temporary = root / f".SOURCE_HEAD.tmp.{os.getpid()}.{uuid4().hex}"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
        _directory_fsync(root)
    except OSError as exc:
        raise SourceStoreError("cannot advance source HEAD") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _new_store_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": SOURCE_STORE_SCHEMA,
        "store_id": "",
        "nonce": uuid4().hex,
        "source_id": SOURCE_ID,
        "source_schema": SOURCE_SCHEMA,
        "receipt_schema": SOURCE_RECEIPT_SCHEMA,
        "generation_schema": SOURCE_GENERATION_SCHEMA,
        "evidence_policy": {
            "feature_projection": "separate_authenticated_adapter_required",
            "training_eligible": False,
            "promotion_eligible": False,
            "role": "context_only",
        },
        "authority": dict(market_memory.AUTHORITY),
    }
    manifest["store_id"] = _content_id("mmsstore_", manifest, field="store_id")
    return manifest


def _validate_store_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema",
        "store_id",
        "nonce",
        "source_id",
        "source_schema",
        "receipt_schema",
        "generation_schema",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SourceStoreError("source store manifest fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != SOURCE_STORE_SCHEMA:
        raise SourceStoreError("source store schema mismatch")
    if not isinstance(clean.get("store_id"), str) or not _STORE_ID.fullmatch(
        clean["store_id"]
    ):
        raise SourceStoreError("source store_id is malformed")
    if not isinstance(clean.get("nonce"), str) or not re.fullmatch(
        r"[a-f0-9]{32}", clean["nonce"]
    ):
        raise SourceStoreError("source store nonce is malformed")
    if (
        clean.get("source_id") != SOURCE_ID
        or clean.get("source_schema") != SOURCE_SCHEMA
        or clean.get("receipt_schema") != SOURCE_RECEIPT_SCHEMA
        or clean.get("generation_schema") != SOURCE_GENERATION_SCHEMA
    ):
        raise SourceStoreError("source store contract drift")
    if clean.get("evidence_policy") != {
        "feature_projection": "separate_authenticated_adapter_required",
        "training_eligible": False,
        "promotion_eligible": False,
        "role": "context_only",
    }:
        raise SourceStoreError("source store evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise SourceStoreError("source store authority drift")
    if _content_id("mmsstore_", clean, field="store_id") != clean["store_id"]:
        raise SourceStoreError("source store_id does not bind its manifest")
    return clean


def _new_generation(
    *, store_id: str, previous_generation_id: str | None, receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    generation: dict[str, Any] = {
        "schema": SOURCE_GENERATION_SCHEMA,
        "generation_id": "",
        "store_id": store_id,
        "previous_generation_id": previous_generation_id,
        "receipts": sorted(copy.deepcopy(receipts), key=lambda row: row["receipt_id"]),
    }
    generation["generation_id"] = _content_id(
        "mmsgen_", generation, field="generation_id"
    )
    return generation


def _validate_generation(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    expected = {
        "schema",
        "generation_id",
        "store_id",
        "previous_generation_id",
        "receipts",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SourceStoreError("source generation fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != SOURCE_GENERATION_SCHEMA:
        raise SourceStoreError("source generation schema mismatch")
    if not isinstance(clean.get("generation_id"), str) or not _GENERATION_ID.fullmatch(
        clean["generation_id"]
    ):
        raise SourceStoreError("source generation_id is malformed")
    if clean.get("store_id") != store_id:
        raise SourceStoreError("source generation belongs to another store")
    previous = clean.get("previous_generation_id")
    if previous is not None and (
        not isinstance(previous, str) or not _GENERATION_ID.fullmatch(previous)
    ):
        raise SourceStoreError("previous source generation_id is malformed")
    rows = clean.get("receipts")
    if not isinstance(rows, list) or len(rows) > _MAX_GENERATION_RECEIPTS:
        raise SourceStoreError("source generation receipt index is invalid")
    fields = {
        "capture_id",
        "receipt_id",
        "artifact_sha256",
        "vintage_id",
        "revision_id",
    }
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != fields:
            raise SourceStoreError("source generation entry is not canonical")
        if not _CAPTURE_ID.fullmatch(str(row.get("capture_id"))):
            raise SourceStoreError("source generation capture_id is malformed")
        if not _RECEIPT_ID.fullmatch(str(row.get("receipt_id"))):
            raise SourceStoreError("source generation receipt_id is malformed")
        if not _SHA256.fullmatch(str(row.get("artifact_sha256"))):
            raise SourceStoreError("source generation artifact hash is malformed")
        if not _VINTAGE_ID.fullmatch(str(row.get("vintage_id"))):
            raise SourceStoreError("source generation vintage_id is malformed")
        if not _REVISION_ID.fullmatch(str(row.get("revision_id"))):
            raise SourceStoreError("source generation revision_id is malformed")
    receipt_ids = [row["receipt_id"] for row in rows]
    capture_ids = [row["capture_id"] for row in rows]
    if receipt_ids != sorted(receipt_ids) or len(receipt_ids) != len(set(receipt_ids)):
        raise SourceStoreError("source generation receipt index is not canonical")
    if len(capture_ids) != len(set(capture_ids)):
        raise SourceStoreError("source generation capture index is ambiguous")
    if _content_id("mmsgen_", clean, field="generation_id") != clean["generation_id"]:
        raise SourceStoreError("source generation_id does not bind its bytes")
    return clean


def _new_head(generation: Mapping[str, Any], body: bytes) -> dict[str, Any]:
    return {
        "schema": SOURCE_HEAD_SCHEMA,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": sha256(body).hexdigest(),
    }


def _validate_head(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "store_id",
        "generation_id",
        "generation_sha256",
    }:
        raise SourceStoreError("source HEAD fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != SOURCE_HEAD_SCHEMA or clean.get("store_id") != store_id:
        raise SourceStoreError("source HEAD contract mismatch")
    if not isinstance(clean.get("generation_id"), str) or not _GENERATION_ID.fullmatch(
        clean["generation_id"]
    ):
        raise SourceStoreError("source HEAD generation_id is malformed")
    if not isinstance(clean.get("generation_sha256"), str) or not _SHA256.fullmatch(
        clean["generation_sha256"]
    ):
        raise SourceStoreError("source HEAD generation hash is malformed")
    return clean


def _ensure_store(root: Path) -> _StoreState:
    _mkdir_durable(root)
    manifest_path = _store_manifest_path(root)
    if manifest_path.exists():
        manifest, _body = _read_store_object(
            manifest_path, limit=_MAX_STORE_BYTES, label="source store manifest"
        )
        clean_manifest = _validate_store_manifest(manifest)
    else:
        if _head_path(root).exists():
            raise SourceStoreError("source HEAD exists without a store manifest")
        clean_manifest = _new_store_manifest()
        _write_create_once(
            root,
            manifest_path,
            _canonical_bytes(clean_manifest),
            label="source store manifest",
        )

    empty = _new_generation(
        store_id=clean_manifest["store_id"],
        previous_generation_id=None,
        receipts=[],
    )
    empty_body = _canonical_bytes(empty)
    _write_create_once(
        root,
        _generation_path(root, empty["generation_id"]),
        empty_body,
        label="empty source generation",
    )
    if not _head_path(root).exists():
        _replace_head(root, _new_head(empty, empty_body))
    return _load_store_state(root)


def _load_store_state(root: Path, generation_id: str | None = None) -> _StoreState:
    manifest, _manifest_body = _read_store_object(
        _store_manifest_path(root),
        limit=_MAX_STORE_BYTES,
        label="source store manifest",
    )
    clean_manifest = _validate_store_manifest(manifest)
    head, _head_body = _read_store_object(
        _head_path(root), limit=_MAX_HEAD_BYTES, label="source HEAD"
    )
    clean_head = _validate_head(head, store_id=clean_manifest["store_id"])
    head_generation, head_generation_body = _read_store_object(
        _generation_path(root, clean_head["generation_id"]),
        limit=_MAX_GENERATION_BYTES,
        label="source generation",
    )
    clean_head_generation = _validate_generation(
        head_generation, store_id=clean_manifest["store_id"]
    )
    if sha256(head_generation_body).hexdigest() != clean_head["generation_sha256"]:
        raise SourceStoreError("source HEAD does not bind its generation bytes")
    selected = generation_id or clean_head["generation_id"]
    clean_generation = clean_head_generation
    seen: set[str] = set()
    while clean_generation["generation_id"] != selected:
        current_id = clean_generation["generation_id"]
        if current_id in seen or len(seen) > _MAX_GENERATION_RECEIPTS:
            raise SourceStoreError("source generation ancestry is cyclic or unbounded")
        seen.add(current_id)
        previous = clean_generation["previous_generation_id"]
        if previous is None:
            raise SourceNotFound(
                "source generation is not published in current ancestry"
            )
        prior, _prior_body = _read_store_object(
            _generation_path(root, previous),
            limit=_MAX_GENERATION_BYTES,
            label="prior source generation",
            not_found=True,
        )
        clean_generation = _validate_generation(
            prior, store_id=clean_manifest["store_id"]
        )
    return _StoreState(clean_manifest, clean_head, clean_generation)


def _collector_evidence(
    manifest: Mapping[str, Any], *, artifact: _BoundedRead, observed_at: datetime
) -> dict[str, Any]:
    if manifest.get("schema") != COLLECTOR_SCHEMA:
        raise SourceIntakeError("release-target collector schema mismatch")
    if (
        manifest.get("source") != "FRED/ALFRED"
        or manifest.get("source_output_type") != _OUTPUT_TYPE
    ):
        raise SourceIntakeError("release-target collector source contract mismatch")
    if manifest.get("dry_run") is not False or manifest.get("status") not in {
        "ok",
        "partial",
    }:
        raise SourceIntakeError("release-target collector did not publish usable bytes")
    series = manifest.get("series")
    if not isinstance(series, Mapping) or not isinstance(
        series.get(_SERIES_ID), Mapping
    ):
        raise SourceIntakeError("collector manifest has no CPIAUCSL receipt")
    row = dict(series[_SERIES_ID])
    row_status = row.get("status")
    if row_status not in {"written", "sealed"}:
        raise SourceIntakeError("collector did not durably publish CPIAUCSL")
    seal_mode = manifest.get("mode") == "seal_existing"
    if row_status == "sealed":
        if not seal_mode:
            raise SourceIntakeError("sealed collector receipt has no canonical mode")
        if manifest.get("status") != "ok":
            raise SourceIntakeError("sealed collector manifest is not complete")
    elif seal_mode or "sealed_at" in manifest:
        raise SourceIntakeError("written collector receipt claims sealed provenance")
    for field in ("rows", "periods", "release_dates"):
        count = row.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise SourceIntakeError(
                f"collector manifest {field} is not a positive integer"
            )
    for field in ("period_min", "period_max"):
        value = row.get(field)
        if not isinstance(value, str):
            raise SourceIntakeError(f"collector manifest {field} is not a date")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise SourceIntakeError(
                f"collector manifest {field} is not a date"
            ) from exc
    started_dt, started = _parse_utc(manifest.get("collected_at"), field="collected_at")

    hardening_fields_present = (
        "integrity_profile" in manifest,
        "completed_at" in manifest,
        "artifact_sha256" in row,
        "artifact_bytes" in row,
    )
    # A legacy receipt has none of these fields.  Presence of even one field,
    # including an explicit JSON null, claims the hardened profile and must
    # therefore satisfy the complete integrity contract instead of silently
    # downgrading to reconstruction evidence.
    hardened = any(hardening_fields_present)
    if row_status == "sealed" and not all(hardening_fields_present):
        raise SourceIntakeError(
            "sealed collector receipt lacks the complete hardened profile"
        )
    completed: str | None = None
    if hardened:
        if manifest.get("integrity_profile") != COLLECTOR_INTEGRITY_PROFILE:
            raise SourceIntakeError("collector integrity profile is missing or unknown")
        completed_dt, completed = _parse_utc(
            manifest.get("completed_at"), field="completed_at"
        )
        if completed_dt < started_dt or observed_at < completed_dt:
            raise SourceIntakeError(
                "collector completion/observation clocks are impossible"
            )
        if row_status == "sealed":
            sealed_dt, _sealed = _parse_utc(
                manifest.get("sealed_at"), field="sealed_at"
            )
            if sealed_dt < completed_dt or observed_at < sealed_dt:
                raise SourceIntakeError(
                    "collector seal/completion/observation clocks are impossible"
                )
        expected_hash = row.get("artifact_sha256")
        expected_bytes = row.get("artifact_bytes")
        if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
            raise SourceIntakeError("collector artifact SHA-256 is malformed")
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes <= 0
            or expected_bytes > _MAX_UPSTREAM_BYTES
        ):
            raise SourceIntakeError("collector artifact byte count is malformed")
        if (
            expected_bytes != artifact.size
            or expected_hash != sha256(artifact.body).hexdigest()
        ):
            raise SourceIntakeError(
                "collector manifest does not bind exact artifact bytes"
            )
        evidence_basis = "live_captured_source_vintage"
    else:
        if observed_at < started_dt:
            raise SourceIntakeError("legacy collector observation predates collection")
        evidence_basis = "public_reconstruction"

    return {
        "row": row,
        "collector_entry_status": row_status,
        "collector_started_at": started,
        "collector_completed_at": completed,
        "integrity_profile": (
            COLLECTOR_INTEGRITY_PROFILE if hardened else "legacy_unbound_manifest.v1"
        ),
        "evidence_basis": evidence_basis,
        "hardened": hardened,
    }


def _validate_and_project_matrix(
    body: bytes, *, manifest_row: Mapping[str, Any]
) -> tuple[dict[str, Any], date, datetime]:
    try:
        raw = pd.read_parquet(io.BytesIO(body))
        normalized = normalize_full_vintage_frame(raw, series_id=_SERIES_ID)
    except Exception as exc:
        raise SourceIntakeError(
            "CPIAUCSL artifact is not a valid full-vintage matrix"
        ) from exc
    if normalized.empty or len(normalized) != len(raw):
        raise SourceIntakeError("CPIAUCSL normalization dropped or deduplicated rows")
    if set(normalized["series"]) != {_SERIES_ID}:
        raise SourceIntakeError("CPIAUCSL artifact contains another series")
    if "source_output_type" not in normalized or set(
        normalized["source_output_type"]
    ) != {_OUTPUT_TYPE}:
        raise SourceIntakeError("CPIAUCSL artifact is not ALFRED output_type=2")
    if not normalized["value"].map(lambda value: math.isfinite(float(value))).all():
        raise SourceIntakeError("CPIAUCSL artifact contains a non-finite value")
    if not normalized["realtime_end"].map(lambda value: isinstance(value, date)).all():
        raise SourceIntakeError("CPIAUCSL artifact contains an invalid realtime_end")
    for row in normalized.itertuples(index=False):
        realtime_start = row.realtime_start.date()
        if row.realtime_end < realtime_start:
            raise SourceIntakeError("CPIAUCSL realtime interval ends before it starts")
        if row.period.date() >= realtime_start:
            raise SourceIntakeError(
                "CPIAUCSL period is not earlier than its source vintage"
            )
    for _period, rows in normalized.groupby("period", sort=False):
        ordered = rows.sort_values("realtime_start")
        prior_end: date | None = None
        for row in ordered.itertuples(index=False):
            current_start = row.realtime_start.date()
            if prior_end is not None and prior_end >= current_start:
                raise SourceIntakeError("CPIAUCSL realtime intervals overlap")
            prior_end = row.realtime_end

    expected_counts = {
        "rows": len(normalized),
        "periods": int(normalized["period"].nunique()),
        "release_dates": int(normalized["realtime_start"].nunique()),
        "period_min": normalized["period"].min().date().isoformat(),
        "period_max": normalized["period"].max().date().isoformat(),
    }
    for field, expected in expected_counts.items():
        if manifest_row.get(field) != expected:
            raise SourceIntakeError(
                f"collector manifest {field} does not match CPI bytes"
            )

    newest_stamp = normalized["realtime_start"].max()
    newest_date = newest_stamp.date()
    slice_frame = normalized[normalized["realtime_start"] == newest_stamp].copy()
    if slice_frame.empty or len(slice_frame) > _MAX_OBJECT_ROWS:
        raise SourceIntakeError("newest CPI vintage slice exceeds its safe row bound")
    if len(slice_frame) != expected_counts["periods"]:
        raise SourceIntakeError(
            "newest CPI vintage slice is not a complete period matrix"
        )
    if slice_frame["period"].duplicated().any():
        raise SourceIntakeError("newest CPI vintage contains duplicate periods")
    slice_frame = slice_frame.sort_values("period")
    rows: list[dict[str, Any]] = []
    for row in slice_frame.itertuples(index=False):
        rows.append(
            {
                "period": row.period.date().isoformat(),
                "realtime_start": row.realtime_start.date().isoformat(),
                "realtime_end": row.realtime_end.isoformat(),
                "value": float(row.value),
            }
        )
    measurement_start = slice_frame["period"].min().date()
    measurement_max = slice_frame["period"].max().date()
    if measurement_max.month == 12:
        measurement_end = date(measurement_max.year + 1, 1, 1)
    else:
        measurement_end = date(measurement_max.year, measurement_max.month + 1, 1)
    artifact = {
        "schema": SOURCE_SCHEMA,
        "source_id": SOURCE_ID,
        "series_id": _SERIES_ID,
        "source_output_type": _OUTPUT_TYPE,
        "vintage_date": newest_date.isoformat(),
        "measurement_start": measurement_start.isoformat(),
        "measurement_end_exclusive": measurement_end.isoformat(),
        "rows": rows,
    }
    if len(_canonical_bytes(artifact)) > _MAX_OBJECT_BYTES:
        raise SourceIntakeError("derived CPI source object exceeds its safe size bound")
    upper = datetime.combine(newest_date + timedelta(days=1), time.min, timezone.utc)
    return artifact, newest_date, upper


def _validate_receipt(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    expected = {
        "schema",
        "store_id",
        "receipt_id",
        "capture_id",
        "source_id",
        "source_schema",
        "source_system",
        "series_id",
        "source_output_type",
        "vintage_id",
        "revision_id",
        "artifact_sha256",
        "object_key",
        "clocks",
        "availability_evidence",
        "provenance",
        "quality",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SourceStoreError("source receipt fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if (
        clean.get("schema") != SOURCE_RECEIPT_SCHEMA
        or clean.get("store_id") != store_id
    ):
        raise SourceStoreError("source receipt contract mismatch")
    if not _RECEIPT_ID.fullmatch(str(clean.get("receipt_id"))):
        raise SourceStoreError("source receipt_id is malformed")
    if not _CAPTURE_ID.fullmatch(str(clean.get("capture_id"))):
        raise SourceStoreError("source capture_id is malformed")
    if (
        clean.get("source_id") != SOURCE_ID
        or clean.get("source_schema") != SOURCE_SCHEMA
        or clean.get("source_system") != "FRED/ALFRED"
        or clean.get("series_id") != _SERIES_ID
        or clean.get("source_output_type") != _OUTPUT_TYPE
    ):
        raise SourceStoreError("source receipt identity drift")
    if not _VINTAGE_ID.fullmatch(str(clean.get("vintage_id"))):
        raise SourceStoreError("source vintage_id is malformed")
    if not _REVISION_ID.fullmatch(str(clean.get("revision_id"))):
        raise SourceStoreError("source revision_id is malformed")
    artifact_sha = clean.get("artifact_sha256")
    if not isinstance(artifact_sha, str) or not _SHA256.fullmatch(artifact_sha):
        raise SourceStoreError("source receipt artifact SHA-256 is malformed")
    if (
        clean.get("object_key")
        != f"source_objects/{artifact_sha[:2]}/{artifact_sha}.json"
    ):
        raise SourceStoreError("source receipt object key drift")
    clocks = clean.get("clocks")
    if not isinstance(clocks, Mapping) or set(clocks) != {
        "source_date",
        "availability_lower_bound",
        "availability_upper_bound",
        "available_at",
        "observed_at",
        "collector_started_at",
        "collector_completed_at",
    }:
        raise SourceStoreError("source receipt clocks are not canonical")
    lower_dt, _ = _parse_utc_for_store(
        clocks.get("availability_lower_bound"), "availability_lower_bound"
    )
    upper_dt, _ = _parse_utc_for_store(
        clocks.get("availability_upper_bound"), "availability_upper_bound"
    )
    available_dt, _ = _parse_utc_for_store(clocks.get("available_at"), "available_at")
    observed_dt, _ = _parse_utc_for_store(clocks.get("observed_at"), "observed_at")
    started_dt, _ = _parse_utc_for_store(
        clocks.get("collector_started_at"), "collector_started_at"
    )
    try:
        source_date = date.fromisoformat(str(clocks.get("source_date")))
    except ValueError as exc:
        raise SourceStoreError("source receipt source_date is invalid") from exc
    expected_lower = datetime.combine(source_date, time.min, timezone.utc)
    if (
        lower_dt != expected_lower
        or upper_dt - lower_dt != timedelta(days=1)
        or available_dt != upper_dt
    ):
        raise SourceStoreError("source date-precision availability envelope drift")
    if observed_dt < available_dt or observed_dt < started_dt:
        raise SourceStoreError("source receipt was observed before safe availability")
    evidence = clean.get("availability_evidence")
    if evidence != {
        "precision": "date",
        "timestamp_inferred": False,
        "rule": "source_date_upper_bound.v1",
        "operational_cutoff_uses": "observed_at",
    }:
        raise SourceStoreError("source availability evidence drift")
    provenance = clean.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != {
        "evidence_basis",
        "integrity_profile",
        "manifest_sha256",
        "manifest_bytes",
        "upstream_artifact_sha256",
        "upstream_artifact_bytes",
        "matrix_rows",
        "matrix_periods",
        "matrix_release_dates",
        "object_rows",
    }:
        raise SourceStoreError("source receipt provenance is not canonical")
    if provenance.get("evidence_basis") not in {
        "public_reconstruction",
        "live_captured_source_vintage",
    }:
        raise SourceStoreError("source receipt evidence basis is invalid")
    for field in ("manifest_sha256", "upstream_artifact_sha256"):
        if not _SHA256.fullmatch(str(provenance.get(field))):
            raise SourceStoreError(f"source receipt {field} is malformed")
    for field, maximum in (
        ("manifest_bytes", _MAX_MANIFEST_BYTES),
        ("upstream_artifact_bytes", _MAX_UPSTREAM_BYTES),
        ("matrix_rows", None),
        ("matrix_periods", None),
        ("matrix_release_dates", None),
        ("object_rows", _MAX_OBJECT_ROWS),
    ):
        count = provenance.get(field)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            or (maximum is not None and count > maximum)
        ):
            raise SourceStoreError(f"source receipt {field} is invalid")
    quality = clean.get("quality")
    reconstruction = provenance["evidence_basis"] == "public_reconstruction"
    if quality != {
        "status": "complete",
        "reconstruction_only": reconstruction,
        "source_evidence_eligible": not reconstruction,
        "feature_projection_eligible": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }:
        raise SourceStoreError("source receipt quality/eligibility drift")
    completed_value = clocks.get("collector_completed_at")
    if reconstruction:
        if (
            provenance.get("integrity_profile") != "legacy_unbound_manifest.v1"
            or completed_value is not None
        ):
            raise SourceStoreError(
                "reconstructed source receipt claims hardened evidence"
            )
    else:
        if provenance.get("integrity_profile") != COLLECTOR_INTEGRITY_PROFILE:
            raise SourceStoreError(
                "live source receipt lacks hardened integrity evidence"
            )
        completed_dt, _ = _parse_utc_for_store(
            completed_value, "collector_completed_at"
        )
        if completed_dt < started_dt or observed_dt < completed_dt:
            raise SourceStoreError(
                "live source receipt collector clocks are impossible"
            )
    expected_vintage_id = (
        "mmsvintage_"
        + sha256(
            _canonical_bytes(
                {"source_id": SOURCE_ID, "vintage_date": source_date.isoformat()}
            )
        ).hexdigest()
    )
    if clean["vintage_id"] != expected_vintage_id:
        raise SourceStoreError("source vintage_id does not bind its source date")
    expected_revision_id = (
        "mmsrevision_"
        + sha256(
            _canonical_bytes(
                {
                    "vintage_id": clean["vintage_id"],
                    "artifact_sha256": artifact_sha,
                    "upstream_artifact_sha256": provenance["upstream_artifact_sha256"],
                }
            )
        ).hexdigest()
    )
    if clean["revision_id"] != expected_revision_id:
        raise SourceStoreError("source revision_id does not bind its artifacts")
    expected_capture_id = (
        "mmscapture_"
        + sha256(
            _canonical_bytes(
                {
                    "schema": SOURCE_CAPTURE_SCHEMA,
                    "source_id": SOURCE_ID,
                    "vintage_date": source_date.isoformat(),
                    "artifact_sha256": artifact_sha,
                    "upstream_artifact_sha256": provenance["upstream_artifact_sha256"],
                    "integrity_profile": provenance["integrity_profile"],
                }
            )
        ).hexdigest()
    )
    if clean["capture_id"] != expected_capture_id:
        raise SourceStoreError("source capture_id does not bind its revision")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise SourceStoreError("source receipt authority drift")
    if _content_id("mmsrc_", clean, field="receipt_id") != clean["receipt_id"]:
        raise SourceStoreError("source receipt_id does not bind its bytes")
    return clean


def _parse_utc_for_store(value: object, field: str) -> tuple[datetime, str]:
    try:
        return _parse_utc(value, field=field)
    except SourceIntakeError as exc:
        raise SourceStoreError(str(exc)) from exc


def _new_receipt(
    *,
    store_id: str,
    capture_id: str,
    artifact: Mapping[str, Any],
    artifact_sha256: str,
    vintage_date: date,
    safe_available_at: datetime,
    observed_at: str,
    evidence: Mapping[str, Any],
    manifest_sha256: str,
    manifest_bytes: int,
    upstream_sha256: str,
    upstream_bytes: int,
) -> dict[str, Any]:
    vintage_core = {"source_id": SOURCE_ID, "vintage_date": vintage_date.isoformat()}
    vintage_id = "mmsvintage_" + sha256(_canonical_bytes(vintage_core)).hexdigest()
    revision_core = {
        "vintage_id": vintage_id,
        "artifact_sha256": artifact_sha256,
        "upstream_artifact_sha256": upstream_sha256,
    }
    revision_id = "mmsrevision_" + sha256(_canonical_bytes(revision_core)).hexdigest()
    lower = datetime.combine(vintage_date, time.min, timezone.utc)
    receipt: dict[str, Any] = {
        "schema": SOURCE_RECEIPT_SCHEMA,
        "store_id": store_id,
        "receipt_id": "",
        "capture_id": capture_id,
        "source_id": SOURCE_ID,
        "source_schema": SOURCE_SCHEMA,
        "source_system": "FRED/ALFRED",
        "series_id": _SERIES_ID,
        "source_output_type": _OUTPUT_TYPE,
        "vintage_id": vintage_id,
        "revision_id": revision_id,
        "artifact_sha256": artifact_sha256,
        "object_key": f"source_objects/{artifact_sha256[:2]}/{artifact_sha256}.json",
        "clocks": {
            "source_date": vintage_date.isoformat(),
            "availability_lower_bound": lower.isoformat().replace("+00:00", "Z"),
            "availability_upper_bound": safe_available_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "available_at": safe_available_at.isoformat().replace("+00:00", "Z"),
            "observed_at": observed_at,
            "collector_started_at": evidence["collector_started_at"],
            "collector_completed_at": evidence["collector_completed_at"],
        },
        "availability_evidence": {
            "precision": "date",
            "timestamp_inferred": False,
            "rule": "source_date_upper_bound.v1",
            "operational_cutoff_uses": "observed_at",
        },
        "provenance": {
            "evidence_basis": evidence["evidence_basis"],
            "integrity_profile": evidence["integrity_profile"],
            "manifest_sha256": manifest_sha256,
            "manifest_bytes": manifest_bytes,
            "upstream_artifact_sha256": upstream_sha256,
            "upstream_artifact_bytes": upstream_bytes,
            "matrix_rows": evidence["row"]["rows"],
            "matrix_periods": evidence["row"]["periods"],
            "matrix_release_dates": evidence["row"]["release_dates"],
            "object_rows": len(artifact["rows"]),
        },
        "quality": {
            "status": "complete",
            "reconstruction_only": not evidence["hardened"],
            "source_evidence_eligible": bool(evidence["hardened"]),
            "feature_projection_eligible": False,
            "training_eligible": False,
            "promotion_eligible": False,
        },
        "authority": dict(market_memory.AUTHORITY),
    }
    receipt["receipt_id"] = _content_id("mmsrc_", receipt, field="receipt_id")
    return receipt


def _entry(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capture_id": receipt["capture_id"],
        "receipt_id": receipt["receipt_id"],
        "artifact_sha256": receipt["artifact_sha256"],
        "vintage_id": receipt["vintage_id"],
        "revision_id": receipt["revision_id"],
    }


def _find_entry(
    generation: Mapping[str, Any], *, capture_id: str
) -> dict[str, Any] | None:
    for row in generation["receipts"]:
        if row["capture_id"] == capture_id:
            return dict(row)
    return None


def _read_receipt_copies(
    root: Path, entry: Mapping[str, Any], *, store_id: str
) -> tuple[dict[str, Any], bytes]:
    receipt, receipt_body = _read_store_object(
        _receipt_path(root, entry["receipt_id"]),
        limit=_MAX_RECEIPT_BYTES,
        label="source receipt",
    )
    _capture, capture_body = _read_store_object(
        _capture_path(root, entry["capture_id"]),
        limit=_MAX_RECEIPT_BYTES,
        label="source capture receipt",
    )
    if receipt_body != capture_body:
        raise SourceStoreError("source receipt copies disagree")
    clean = _validate_receipt(receipt, store_id=store_id)
    if _entry(clean) != dict(entry):
        raise SourceStoreError("source generation entry does not bind its receipt")
    return clean, receipt_body


def intake_alfred_cpiaucsl(
    store_root: str | Path,
    *,
    manifest_path: str | Path,
    artifact_path: str | Path,
) -> StoredSourceArtifact:
    """Admit one stable CPIAUCSL source revision into the private source store."""

    manifest_file = Path(os.path.abspath(Path(manifest_path).expanduser()))
    artifact_file = Path(os.path.abspath(Path(artifact_path).expanduser()))
    if artifact_file.name != "CPIAUCSL_all_vintages.parquet":
        raise SourceIntakeError("artifact filename is not canonical CPIAUCSL input")
    manifest_before = _read_bounded(
        manifest_file, limit=_MAX_MANIFEST_BYTES, label="collector manifest"
    )
    manifest = _strict_json_object(manifest_before.body, label="collector manifest")
    upstream = _read_bounded(
        artifact_file, limit=_MAX_UPSTREAM_BYTES, label="CPIAUCSL artifact"
    )
    manifest_after = _read_bounded(
        manifest_file, limit=_MAX_MANIFEST_BYTES, label="collector manifest"
    )
    if (
        manifest_before.body != manifest_after.body
        or manifest_before.identity != manifest_after.identity
    ):
        raise SourceIntakeError("collector manifest changed during stable intake")
    # The default observation clock is established only after the complete
    # manifest -> artifact -> manifest stable read.  Stamping before those
    # bytes are actually observed would manufacture an earlier PIT boundary.
    observed_dt, observed_stamp = _observation_clock()
    evidence = _collector_evidence(manifest, artifact=upstream, observed_at=observed_dt)
    artifact, vintage_date, safe_available_at = _validate_and_project_matrix(
        upstream.body, manifest_row=evidence["row"]
    )
    if observed_dt < safe_available_at:
        raise SourceIntakeError(
            "CPI source date has not reached its conservative availability upper bound"
        )
    object_body = _canonical_bytes(artifact)
    object_sha = sha256(object_body).hexdigest()
    upstream_sha = sha256(upstream.body).hexdigest()
    capture_core = {
        "schema": SOURCE_CAPTURE_SCHEMA,
        "source_id": SOURCE_ID,
        "vintage_date": vintage_date.isoformat(),
        "artifact_sha256": object_sha,
        "upstream_artifact_sha256": upstream_sha,
        "integrity_profile": evidence["integrity_profile"],
    }
    capture_id = "mmscapture_" + sha256(_canonical_bytes(capture_core)).hexdigest()
    vintage_id = (
        "mmsvintage_"
        + sha256(
            _canonical_bytes(
                {"source_id": SOURCE_ID, "vintage_date": vintage_date.isoformat()}
            )
        ).hexdigest()
    )
    revision_id = (
        "mmsrevision_"
        + sha256(
            _canonical_bytes(
                {
                    "vintage_id": vintage_id,
                    "artifact_sha256": object_sha,
                    "upstream_artifact_sha256": upstream_sha,
                }
            )
        ).hexdigest()
    )

    sealed_replay = evidence["collector_entry_status"] == "sealed"
    root = validate_source_store_root(store_root)
    lock_path = _safe_path(root, ".writer.lock")
    if sealed_replay:
        if not lock_path.is_file():
            raise SourceIntakeError(
                "sealed collector receipt has no unique published matching revision"
            )
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        )
    else:
        _mkdir_durable(root)
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        state = _load_store_state(root) if sealed_replay else _ensure_store(root)
        existing_entry = _find_entry(state.generation, capture_id=capture_id)
        if existing_entry is not None:
            receipt, _body = _read_receipt_copies(
                root, existing_entry, store_id=state.manifest["store_id"]
            )
            stored_artifact = _read_artifact_for_receipt(root, receipt)
            return StoredSourceArtifact(
                stored_artifact, receipt, state.generation["generation_id"], False
            )
        if evidence["collector_entry_status"] == "sealed":
            # ``seal_existing`` authenticates already persisted collector bytes,
            # but it is explicitly not a fresh upstream capture.  A prior
            # legacy receipt can bind the same immutable source revision under
            # its honest reconstruction provenance, so replay that receipt
            # without rewriting or upgrading it.  A sealed receipt must never
            # mint the first live-evidence receipt.
            revision_entries = [
                dict(entry)
                for entry in state.generation["receipts"]
                if entry["revision_id"] == revision_id
                and entry["artifact_sha256"] == object_sha
            ]
            if len(revision_entries) != 1:
                raise SourceIntakeError(
                    "sealed collector receipt has no unique published matching revision"
                )
            receipt, _body = _read_receipt_copies(
                root,
                revision_entries[0],
                store_id=state.manifest["store_id"],
            )
            if receipt["provenance"]["upstream_artifact_sha256"] != upstream_sha:
                raise SourceIntakeError(
                    "sealed collector receipt does not match published source bytes"
                )
            if receipt["vintage_id"] != vintage_id:
                raise SourceIntakeError(
                    "sealed collector receipt does not match published source vintage"
                )
            stored_artifact = _read_artifact_for_receipt(root, receipt)
            return StoredSourceArtifact(
                stored_artifact, receipt, state.generation["generation_id"], False
            )

        capture_path = _capture_path(root, capture_id)
        if capture_path.exists():
            orphan, orphan_body = _read_store_object(
                capture_path,
                limit=_MAX_RECEIPT_BYTES,
                label="orphan source capture receipt",
            )
            receipt = _validate_receipt(orphan, store_id=state.manifest["store_id"])
            if receipt["capture_id"] != capture_id:
                raise SourceStoreError("orphan source capture identity drift")
            if (
                receipt["artifact_sha256"] != object_sha
                or receipt["provenance"]["upstream_artifact_sha256"] != upstream_sha
            ):
                raise SourceStoreError(
                    "orphan source capture does not match retry bytes"
                )
            receipt_body = orphan_body
        else:
            receipt = _new_receipt(
                store_id=state.manifest["store_id"],
                capture_id=capture_id,
                artifact=artifact,
                artifact_sha256=object_sha,
                vintage_date=vintage_date,
                safe_available_at=safe_available_at,
                observed_at=observed_stamp,
                evidence=evidence,
                manifest_sha256=sha256(manifest_before.body).hexdigest(),
                manifest_bytes=len(manifest_before.body),
                upstream_sha256=upstream_sha,
                upstream_bytes=len(upstream.body),
            )
            receipt_body = _canonical_bytes(receipt)
            _validate_receipt(receipt, store_id=state.manifest["store_id"])
            if len(receipt_body) > _MAX_RECEIPT_BYTES:
                raise SourceIntakeError("source receipt exceeds its safe size bound")

        if len(state.generation["receipts"]) >= _MAX_GENERATION_RECEIPTS:
            raise SourceStoreError("source store generation capacity is exhausted")
        _write_create_once(
            root, _object_path(root, object_sha), object_body, label="source object"
        )
        _write_create_once(
            root, capture_path, receipt_body, label="source capture receipt"
        )
        _write_create_once(
            root,
            _receipt_path(root, receipt["receipt_id"]),
            receipt_body,
            label="source receipt",
        )
        rows = [dict(row) for row in state.generation["receipts"]] + [_entry(receipt)]
        generation = _new_generation(
            store_id=state.manifest["store_id"],
            previous_generation_id=state.generation["generation_id"],
            receipts=rows,
        )
        generation_body = _canonical_bytes(generation)
        if len(generation_body) > _MAX_GENERATION_BYTES:
            raise SourceStoreError("source generation exceeds its safe size bound")
        _write_create_once(
            root,
            _generation_path(root, generation["generation_id"]),
            generation_body,
            label="source generation",
        )
        _replace_head(root, _new_head(generation, generation_body))
        return StoredSourceArtifact(
            artifact, receipt, generation["generation_id"], True
        )
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)


def _read_artifact_for_receipt(
    root: Path, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    artifact, body = _read_store_object(
        _object_path(root, receipt["artifact_sha256"]),
        limit=_MAX_OBJECT_BYTES,
        label="source object",
    )
    if sha256(body).hexdigest() != receipt["artifact_sha256"]:
        raise SourceStoreError("source object SHA-256 mismatch")
    if set(artifact) != {
        "schema",
        "source_id",
        "series_id",
        "source_output_type",
        "vintage_date",
        "measurement_start",
        "measurement_end_exclusive",
        "rows",
    }:
        raise SourceStoreError("source object fields are not canonical")
    if (
        artifact.get("schema") != SOURCE_SCHEMA
        or artifact.get("source_id") != SOURCE_ID
        or artifact.get("series_id") != _SERIES_ID
        or artifact.get("source_output_type") != _OUTPUT_TYPE
    ):
        raise SourceStoreError("source object contract mismatch")
    if artifact.get("vintage_date") != receipt["clocks"]["source_date"]:
        raise SourceStoreError("source object vintage disagrees with receipt")
    rows = artifact.get("rows")
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) > _MAX_OBJECT_ROWS
        or len(rows) != receipt["provenance"]["object_rows"]
    ):
        raise SourceStoreError("source object row count disagrees with receipt")
    periods: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "period",
            "realtime_start",
            "realtime_end",
            "value",
        }:
            raise SourceStoreError("source object row is not canonical")
        try:
            date.fromisoformat(str(row["period"]))
            date.fromisoformat(str(row["realtime_start"]))
            date.fromisoformat(str(row["realtime_end"]))
        except ValueError as exc:
            raise SourceStoreError("source object row date is invalid") from exc
        if row["realtime_start"] != artifact["vintage_date"]:
            raise SourceStoreError("source object mixes source vintages")
        if (
            not isinstance(row["value"], (int, float))
            or isinstance(row["value"], bool)
            or not math.isfinite(float(row["value"]))
        ):
            raise SourceStoreError("source object row value is invalid")
        periods.append(row["period"])
    if periods != sorted(periods) or len(periods) != len(set(periods)):
        raise SourceStoreError("source object periods are not unique and sorted")
    try:
        measurement_start = date.fromisoformat(str(artifact["measurement_start"]))
        measurement_end = date.fromisoformat(str(artifact["measurement_end_exclusive"]))
    except ValueError as exc:
        raise SourceStoreError("source object measurement range is invalid") from exc
    if measurement_start != date.fromisoformat(
        periods[0]
    ) or measurement_end <= date.fromisoformat(periods[-1]):
        raise SourceStoreError("source object measurement range does not bind its rows")
    return artifact


class SourceArtifactReader:
    """Generation-pinned internal reader for immutable source evidence."""

    def __init__(
        self, store_root: str | Path, generation_id: str | None = None
    ) -> None:
        self._root = validate_source_store_root(store_root)
        if generation_id is not None and not _GENERATION_ID.fullmatch(generation_id):
            raise SourceStoreError("source generation_id is malformed")
        self._pinned_generation_id = generation_id

    @property
    def pinned_generation_id(self) -> str | None:
        return self._pinned_generation_id

    def head_generation_id(self) -> str:
        return _load_store_state(self._root).generation["generation_id"]

    def pin(self, generation_id: str | None = None) -> str:
        selected = generation_id or self.head_generation_id()
        _load_store_state(self._root, selected)
        self._pinned_generation_id = selected
        return selected

    def _state(self, generation_id: str | None = None) -> _StoreState:
        selected = generation_id or self._pinned_generation_id
        if selected is None:
            selected = self.pin()
        return _load_store_state(self._root, selected)

    def receipts(self, generation_id: str | None = None) -> list[dict[str, Any]]:
        state = self._state(generation_id)
        return [
            self.read_receipt(
                row["receipt_id"], generation_id=state.generation["generation_id"]
            )
            for row in state.generation["receipts"]
        ]

    def read_receipt(
        self, receipt_id: str, generation_id: str | None = None
    ) -> dict[str, Any]:
        if not isinstance(receipt_id, str) or not _RECEIPT_ID.fullmatch(receipt_id):
            raise SourceNotFound("source receipt_id is not captured")
        state = self._state(generation_id)
        entry = next(
            (
                dict(row)
                for row in state.generation["receipts"]
                if row["receipt_id"] == receipt_id
            ),
            None,
        )
        if entry is None:
            raise SourceNotFound("source receipt is absent from the pinned generation")
        receipt, _body = _read_receipt_copies(
            self._root, entry, store_id=state.manifest["store_id"]
        )
        return copy.deepcopy(receipt)

    def read_object(
        self, receipt_id: str, generation_id: str | None = None
    ) -> dict[str, Any]:
        receipt = self.read_receipt(receipt_id, generation_id=generation_id)
        return copy.deepcopy(_read_artifact_for_receipt(self._root, receipt))


__all__ = [
    "COLLECTOR_INTEGRITY_PROFILE",
    "SOURCE_ID",
    "SOURCE_RECEIPT_SCHEMA",
    "SOURCE_SCHEMA",
    "MarketMemorySourceError",
    "SourceArtifactReader",
    "SourceIntakeError",
    "SourceNotFound",
    "SourceStoreError",
    "StoredSourceArtifact",
    "intake_alfred_cpiaucsl",
    "validate_source_store_root",
]
