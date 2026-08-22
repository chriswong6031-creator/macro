"""Family-agnostic O→R→G→HEAD storage kernel for Market Memory source evidence.

This module owns the immutable, parameterised append-only store primitives used
by every source family (CPI ALFRED, SPY REST, and any future family).  It does
NOT carry any family-specific schema strings, network logic, intake business
rules, or content projection.  Callers supply a :class:`SourceFamily` instance
that binds the schema identities; the kernel's lock-and-publish path is then
fully determined by those identities and the store root.

Public surface:
- :class:`SourceFamily` — schema identities for one source family
- Error classes, dataclasses, size constants, IO primitives
- Path helpers, store management (parameterised by SourceFamily)
- :class:`SourceArtifactReader` — generation-pinned read-only reader
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Size and pattern constants
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class MarketMemorySourceError(RuntimeError):
    """Base class for the private Market Memory source boundary."""


class SourceIntakeError(MarketMemorySourceError):
    """The supplied collector artifact cannot be admitted safely."""


class SourceStoreError(MarketMemorySourceError):
    """The private immutable source store is unavailable or corrupt."""


class SourceNotFound(MarketMemorySourceError):
    """The requested receipt is absent from the complete pinned generation."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Family identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceFamily:
    """Schema identity constants for one source family.

    All string values are validated at construction time to be non-empty.
    Two :class:`SourceFamily` instances with identical fields compare equal
    (frozen dataclass default).
    """

    source_id: str
    source_schema: str
    receipt_schema: str
    generation_schema: str
    head_schema: str
    store_schema: str
    capture_schema: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_id",
            "source_schema",
            "receipt_schema",
            "generation_schema",
            "head_schema",
            "store_schema",
            "capture_schema",
        ):
            value = object.__getattribute__(self, field_name)
            if not isinstance(value, str) or not value:
                raise SourceStoreError(
                    f"SourceFamily.{field_name} must be a non-empty string"
                )


# ---------------------------------------------------------------------------
# JSON / crypto utilities
# ---------------------------------------------------------------------------


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


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


# ---------------------------------------------------------------------------
# Store root validation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Low-level file system IO
# ---------------------------------------------------------------------------


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
                raise SourceStoreError(
                    "Market Memory source directory race was unsafe"
                )
        _directory_fsync(directory.parent)


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


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Parameterised store management
# ---------------------------------------------------------------------------


def _new_store_manifest(family: SourceFamily, authority: dict[str, Any]) -> dict[str, Any]:
    from engine.neuralweb import market_memory  # noqa: PLC0415

    manifest: dict[str, Any] = {
        "schema": family.store_schema,
        "store_id": "",
        "nonce": uuid4().hex,
        "source_id": family.source_id,
        "source_schema": family.source_schema,
        "receipt_schema": family.receipt_schema,
        "generation_schema": family.generation_schema,
        "evidence_policy": {
            "feature_projection": "separate_authenticated_adapter_required",
            "training_eligible": False,
            "promotion_eligible": False,
            "role": "context_only",
        },
        "authority": dict(authority or market_memory.AUTHORITY),
    }
    manifest["store_id"] = _content_id("mmsstore_", manifest, field="store_id")
    return manifest


def _validate_store_manifest(
    value: Mapping[str, Any], family: SourceFamily, authority: dict[str, Any]
) -> dict[str, Any]:
    from engine.neuralweb import market_memory  # noqa: PLC0415

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
    if clean.get("schema") != family.store_schema:
        raise SourceStoreError("source store schema mismatch")
    if not isinstance(clean.get("store_id"), str) or not _STORE_ID.fullmatch(
        clean["store_id"]
    ):
        raise SourceStoreError("source store_id is malformed")
    import re as _re  # noqa: PLC0415
    if not isinstance(clean.get("nonce"), str) or not _re.fullmatch(
        r"[a-f0-9]{32}", clean["nonce"]
    ):
        raise SourceStoreError("source store nonce is malformed")
    if (
        clean.get("source_id") != family.source_id
        or clean.get("source_schema") != family.source_schema
        or clean.get("receipt_schema") != family.receipt_schema
        or clean.get("generation_schema") != family.generation_schema
    ):
        raise SourceStoreError("source store contract drift")
    if clean.get("evidence_policy") != {
        "feature_projection": "separate_authenticated_adapter_required",
        "training_eligible": False,
        "promotion_eligible": False,
        "role": "context_only",
    }:
        raise SourceStoreError("source store evidence policy drift")
    _auth = dict(authority or market_memory.AUTHORITY)
    if clean.get("authority") != _auth:
        raise SourceStoreError("source store authority drift")
    if _content_id("mmsstore_", clean, field="store_id") != clean["store_id"]:
        raise SourceStoreError("source store_id does not bind its manifest")
    return clean


def _new_generation(
    *,
    store_id: str,
    previous_generation_id: str | None,
    receipts: list[dict[str, Any]],
    family: SourceFamily,
) -> dict[str, Any]:
    generation: dict[str, Any] = {
        "schema": family.generation_schema,
        "generation_id": "",
        "store_id": store_id,
        "previous_generation_id": previous_generation_id,
        "receipts": sorted(copy.deepcopy(receipts), key=lambda row: row["receipt_id"]),
    }
    generation["generation_id"] = _content_id(
        "mmsgen_", generation, field="generation_id"
    )
    return generation


def _validate_generation(
    value: Mapping[str, Any], *, store_id: str, family: SourceFamily
) -> dict[str, Any]:
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
    if clean.get("schema") != family.generation_schema:
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


def _new_head(generation: Mapping[str, Any], body: bytes, family: SourceFamily) -> dict[str, Any]:
    return {
        "schema": family.head_schema,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": sha256(body).hexdigest(),
    }


def _validate_head(
    value: Mapping[str, Any], *, store_id: str, family: SourceFamily
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "store_id",
        "generation_id",
        "generation_sha256",
    }:
        raise SourceStoreError("source HEAD fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != family.head_schema or clean.get("store_id") != store_id:
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


def _ensure_store(root: Path, family: SourceFamily, authority: dict[str, Any]) -> _StoreState:
    _mkdir_durable(root)
    manifest_path = _store_manifest_path(root)
    if manifest_path.exists():
        manifest, _body = _read_store_object(
            manifest_path, limit=_MAX_STORE_BYTES, label="source store manifest"
        )
        clean_manifest = _validate_store_manifest(manifest, family, authority)
    else:
        if _head_path(root).exists():
            raise SourceStoreError("source HEAD exists without a store manifest")
        clean_manifest = _new_store_manifest(family, authority)
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
        family=family,
    )
    empty_body = _canonical_bytes(empty)
    _write_create_once(
        root,
        _generation_path(root, empty["generation_id"]),
        empty_body,
        label="empty source generation",
    )
    if not _head_path(root).exists():
        _replace_head(root, _new_head(empty, empty_body, family))
    return _load_store_state(root, family=family, authority=authority)


def _load_store_state(
    root: Path,
    generation_id: str | None = None,
    *,
    family: SourceFamily,
    authority: dict[str, Any],
) -> _StoreState:
    manifest, _manifest_body = _read_store_object(
        _store_manifest_path(root),
        limit=_MAX_STORE_BYTES,
        label="source store manifest",
    )
    clean_manifest = _validate_store_manifest(manifest, family, authority)
    head, _head_body = _read_store_object(
        _head_path(root), limit=_MAX_HEAD_BYTES, label="source HEAD"
    )
    clean_head = _validate_head(head, store_id=clean_manifest["store_id"], family=family)
    head_generation, head_generation_body = _read_store_object(
        _generation_path(root, clean_head["generation_id"]),
        limit=_MAX_GENERATION_BYTES,
        label="source generation",
    )
    clean_head_generation = _validate_generation(
        head_generation, store_id=clean_manifest["store_id"], family=family
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
            prior, store_id=clean_manifest["store_id"], family=family
        )
    return _StoreState(clean_manifest, clean_head, clean_generation)


def _find_entry(
    generation: Mapping[str, Any], *, capture_id: str
) -> dict[str, Any] | None:
    for row in generation["receipts"]:
        if row["capture_id"] == capture_id:
            return dict(row)
    return None


def _entry(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capture_id": receipt["capture_id"],
        "receipt_id": receipt["receipt_id"],
        "artifact_sha256": receipt["artifact_sha256"],
        "vintage_id": receipt["vintage_id"],
        "revision_id": receipt["revision_id"],
    }


def _validate_receipt_minimal(
    value: Mapping[str, Any], *, store_id: str, family: SourceFamily
) -> dict[str, Any]:
    """Validate the family-agnostic envelope of a receipt (ids, schema, store)."""
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != family.receipt_schema:
        raise SourceStoreError("source receipt schema mismatch")
    if clean.get("store_id") != store_id:
        raise SourceStoreError("source receipt store_id mismatch")
    if not _RECEIPT_ID.fullmatch(str(clean.get("receipt_id", ""))):
        raise SourceStoreError("source receipt_id is malformed")
    if not _CAPTURE_ID.fullmatch(str(clean.get("capture_id", ""))):
        raise SourceStoreError("source receipt capture_id is malformed")
    artifact_sha = clean.get("artifact_sha256", "")
    if not isinstance(artifact_sha, str) or not _SHA256.fullmatch(artifact_sha):
        raise SourceStoreError("source receipt artifact SHA-256 is malformed")
    if _content_id("mmsrc_", clean, field="receipt_id") != clean["receipt_id"]:
        raise SourceStoreError("source receipt_id does not bind its bytes")
    return clean


def _read_receipt_copies_by_validate(
    root: Path,
    entry: Mapping[str, Any],
    *,
    store_id: str,
    validate_fn: Any,  # Callable[[Mapping, str], dict]
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
    clean = validate_fn(receipt, store_id)
    if _entry(clean) != dict(entry):
        raise SourceStoreError("source generation entry does not bind its receipt")
    return clean, receipt_body


# ---------------------------------------------------------------------------
# Generic SourceArtifactReader
# ---------------------------------------------------------------------------


class GenericSourceArtifactReader:
    """Generation-pinned internal reader for any family's immutable source evidence.

    Family-specific receipt and artifact validation is delegated to the
    ``validate_receipt_fn`` and ``validate_artifact_fn`` callables supplied at
    construction time.
    """

    def __init__(
        self,
        store_root: str | Path,
        family: SourceFamily,
        authority: dict[str, Any],
        *,
        generation_id: str | None = None,
        validate_receipt_fn: Any = None,
        validate_artifact_fn: Any = None,
    ) -> None:
        self._root = validate_source_store_root(store_root)
        self._family = family
        self._authority = authority
        if generation_id is not None and not _GENERATION_ID.fullmatch(generation_id):
            raise SourceStoreError("source generation_id is malformed")
        self._pinned_generation_id = generation_id
        self._validate_receipt_fn = validate_receipt_fn or (
            lambda v, sid: _validate_receipt_minimal(v, store_id=sid, family=family)
        )
        self._validate_artifact_fn = validate_artifact_fn

    @property
    def pinned_generation_id(self) -> str | None:
        return self._pinned_generation_id

    def head_generation_id(self) -> str:
        return _load_store_state(
            self._root,
            family=self._family,
            authority=self._authority,
        ).generation["generation_id"]

    def pin(self, generation_id: str | None = None) -> str:
        selected = generation_id or self.head_generation_id()
        _load_store_state(
            self._root,
            selected,
            family=self._family,
            authority=self._authority,
        )
        self._pinned_generation_id = selected
        return selected

    def _state(self, generation_id: str | None = None) -> _StoreState:
        selected = generation_id or self._pinned_generation_id
        if selected is None:
            selected = self.pin()
        return _load_store_state(
            self._root,
            selected,
            family=self._family,
            authority=self._authority,
        )

    def receipts(self, generation_id: str | None = None) -> list[dict[str, Any]]:
        state = self._state(generation_id)
        return [
            self.read_receipt(
                row["receipt_id"],
                generation_id=state.generation["generation_id"],
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
        receipt, _body = _read_receipt_copies_by_validate(
            self._root,
            entry,
            store_id=state.manifest["store_id"],
            validate_fn=self._validate_receipt_fn,
        )
        return copy.deepcopy(receipt)


__all__ = [
    "SourceFamily",
    "MarketMemorySourceError",
    "SourceIntakeError",
    "SourceStoreError",
    "SourceNotFound",
    "StoredSourceArtifact",
    "GenericSourceArtifactReader",
    "validate_source_store_root",
    # IO primitives — exported so family modules can import them
    "_BoundedRead",
    "_StoreState",
    "_SHA256",
    "_STORE_ID",
    "_RECEIPT_ID",
    "_CAPTURE_ID",
    "_VINTAGE_ID",
    "_REVISION_ID",
    "_GENERATION_ID",
    "_RFC3339_UTC",
    "_MAX_OBJECT_BYTES",
    "_MAX_OBJECT_ROWS",
    "_MAX_RECEIPT_BYTES",
    "_MAX_STORE_BYTES",
    "_MAX_HEAD_BYTES",
    "_MAX_GENERATION_BYTES",
    "_MAX_GENERATION_RECEIPTS",
    "_REPOSITORY_ROOT",
    "_canonical_bytes",
    "_reject_duplicate_pairs",
    "_strict_json_object",
    "_parse_utc",
    "_content_id",
    "_safe_path",
    "_directory_fsync",
    "_mkdir_durable",
    "_read_bounded",
    "_read_store_object",
    "_write_create_once",
    "_replace_head",
    "_store_manifest_path",
    "_head_path",
    "_object_path",
    "_receipt_path",
    "_capture_path",
    "_generation_path",
    "_new_store_manifest",
    "_validate_store_manifest",
    "_new_generation",
    "_validate_generation",
    "_new_head",
    "_validate_head",
    "_ensure_store",
    "_load_store_state",
    "_find_entry",
    "_entry",
    "_validate_receipt_minimal",
    "_read_receipt_copies_by_validate",
]
