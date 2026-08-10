"""Private immutable store for bounded SPY listing observations.

The identity-v1 lane is independent of the W1A/W1B.1 packet stores and has no
public/API reader.  It first persists a create-once prepared clock record, then
exact source parquet bytes and the label-free listing object, the capture
receipt, a cumulative hash-bound generation, and finally ``HEAD.json``.  The
prepared record is not visible through HEAD; writing it first is what preserves
the original post-read clock if any later CAS write crashes.  Readers trust only
captures reachable from HEAD and validate the entire generation ancestry plus
every referenced byte object.

The prepared record is keyed by the upstream ``mmidobs_`` occurrence.  It
preserves the first Market Memory post-read clock across crashes and later
retries, while a store-specific ``mmidscan_`` receipt keeps capture/run identity
separate from both the semantic ``mmidobj_`` content and source observation.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import uuid4

from engine.neuralweb import market_memory, market_memory_pit
from engine.neuralweb import market_memory_identity_observation as identity_observation

STORE_MANIFEST_SCHEMA = "market_memory.identity_observation_store_manifest.v1"
PREPARED_RECORD_SCHEMA = "market_memory.identity_observation_prepared.v1"
CAPTURE_RECEIPT_SCHEMA = "market_memory.identity_observation_capture_receipt.v1"
STORE_GENERATION_SCHEMA = "market_memory.identity_observation_store_generation.v1"
STORE_HEAD_SCHEMA = "market_memory.identity_observation_store_head.v1"
STORE_PROFILE = "market_memory.private.spy_listing_observation.v1"

MarketMemoryIdentityStoreError = market_memory_pit.MarketMemoryStoreError
MarketMemoryIdentityCaptureError = market_memory_pit.MarketMemoryCaptureError

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PREPARED_BYTES = 256 * 1024
_MAX_CAPTURE_BYTES = 384 * 1024
_MAX_GENERATION_BYTES = 4 * 1024 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_LISTING_OBJECT_BYTES = 64 * 1024
_MAX_UPSTREAM_RECEIPT_BYTES = 512 * 1024
_MAX_CAPTURES = 4_096

_PRODUCTION_NAMESPACE = Path("/var/lib/macro-market-memory").resolve()
_PRODUCTION_STORE_ROOT = Path(
    "/var/lib/macro-market-memory/state/identity-v1"
).resolve()

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmidstore_[a-f0-9]{64}\Z")
_OBJECT_ID = re.compile(r"mmidobj_[a-f0-9]{64}\Z")
_OBSERVATION_ID = re.compile(r"mmidobs_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmidscan_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmidgen_[a-f0-9]{64}\Z")
_RECEIPT_ID = re.compile(r"sdreceipt_[a-f0-9]{64}\Z")

_STORE_POLICY = {
    "actual_output_only": True,
    "accepted_pit_basis": ["live_captured", "public_reconstruction"],
    "private_store": True,
    "historical_resolver": False,
    "training_eligible": False,
    "promotion_eligible": False,
    "role": "context_only",
}

_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "nonce",
        "listing_object_schema",
        "observation_schema",
        "prepared_record_schema",
        "capture_receipt_schema",
        "generation_schema",
        "evidence_policy",
        "authority",
    }
)
_PREPARED_FIELDS = frozenset(
    {
        "schema",
        "source_observation_id",
        "first_observed_at",
        "listing_object_id",
        "source_artifact_sha256",
        "completion_receipt_id",
        "observation",
        "evidence_policy",
        "authority",
    }
)
_CAPTURE_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "capture_id",
        "source_observation_id",
        "listing_object",
        "source_artifact",
        "upstream_receipt",
        "prepared_record",
        "observation",
        "captured_at",
        "evidence_policy",
        "authority",
    }
)
_OBJECT_REFERENCE_FIELDS = frozenset(
    {"listing_object_id", "sha256", "bytes", "object_key"}
)
_SOURCE_REFERENCE_FIELDS = frozenset({"sha256", "bytes", "rows", "object_key"})
_UPSTREAM_REFERENCE_FIELDS = frozenset({"receipt_id", "sha256", "bytes", "object_key"})
_PREPARED_REFERENCE_FIELDS = frozenset({"sha256", "bytes", "object_key"})
_GENERATION_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "generation_id",
        "previous_generation_id",
        "captures",
    }
)
_GENERATION_ENTRY_FIELDS = frozenset(
    {
        "date_partition",
        "source_observation_id",
        "capture_id",
        "listing_object_id",
        "listing_state",
        "pit_basis",
        "operational",
    }
)
_HEAD_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "generation_id",
        "generation_sha256",
        "capture_count",
    }
)


@dataclass(frozen=True)
class StoredIdentityCapture:
    """One fully revalidated visible private identity capture."""

    observation: dict[str, Any]
    capture_receipt: dict[str, Any]
    listing_object: dict[str, Any]
    source_artifact_bytes: bytes
    completion_receipt: dict[str, Any] | None
    completion_receipt_bytes: bytes | None

    def detached(self) -> StoredIdentityCapture:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class IdentityStoreSnapshot:
    """One immutable HEAD view and all exact captures it names."""

    manifest: dict[str, Any]
    head: dict[str, Any]
    generation: dict[str, Any]
    captures: tuple[StoredIdentityCapture, ...]

    def detached(self) -> IdentityStoreSnapshot:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class IdentityCaptureResult:
    """Result of an idempotent source-observation admission attempt."""

    published: bool
    observation: dict[str, Any]
    capture_receipt: dict[str, Any]
    generation: dict[str, Any]
    head: dict[str, Any]

    def detached(self) -> IdentityCaptureResult:
        return copy.deepcopy(self)


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
        raise MarketMemoryIdentityStoreError(
            "identity store value is not finite canonical JSON"
        ) from exc


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


def _require_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MarketMemoryIdentityStoreError(f"{field} is not lowercase SHA-256")
    return value


def _require_exact_int(
    value: object, *, field: str, minimum: int = 0, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MarketMemoryIdentityStoreError(f"{field} is outside its integer bound")
    return value


def validate_identity_observation_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    """Resolve a private narrow root and reject symlink/public/unsafe targets."""

    lexical = Path(root).expanduser()
    if lexical.is_symlink():
        raise MarketMemoryIdentityStoreError(
            "identity observation store root cannot be a symlink"
        )
    try:
        candidate = market_memory_pit.validate_store_root(
            lexical, repository_root=repository_root
        )
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryIdentityStoreError(str(exc)) from exc
    if (
        candidate == _PRODUCTION_NAMESPACE or _PRODUCTION_NAMESPACE in candidate.parents
    ) and candidate != _PRODUCTION_STORE_ROOT:
        raise MarketMemoryIdentityStoreError(
            "identity observation store must use the exact private production "
            "root /var/lib/macro-market-memory/state/identity-v1"
        )
    if repository_root is not None:
        repository = Path(repository_root).expanduser().resolve()
        if candidate == repository or repository in candidate.parents:
            raise MarketMemoryIdentityStoreError(
                "identity observation store cannot live inside the repository"
            )
    if candidate.exists():
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise MarketMemoryIdentityStoreError(
                "identity observation store root is unavailable"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise MarketMemoryIdentityStoreError(
                "identity observation store root must be a non-symlink directory"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MarketMemoryIdentityStoreError(
                "identity observation store root must not grant group/other access"
            )
    return candidate


def _safe_path(root: Path, *parts: str) -> Path:
    return market_memory_pit._safe_store_path(root, *parts)


def _manifest_path(root: Path) -> Path:
    return _safe_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return _safe_path(root, "HEAD.json")


def _source_path(root: Path, digest: str) -> Path:
    digest = _require_digest(digest, field="source artifact digest")
    return _safe_path(root, "source_artifacts", digest[:2], f"{digest}.parquet")


def _listing_object_path(root: Path, object_id: str) -> Path:
    if not isinstance(object_id, str) or not _OBJECT_ID.fullmatch(object_id):
        raise MarketMemoryIdentityStoreError("listing_object_id is malformed")
    digest = object_id.removeprefix("mmidobj_")
    return _safe_path(root, "listing_objects", digest[:2], f"{object_id}.json")


def _upstream_receipt_path(root: Path, digest: str) -> Path:
    digest = _require_digest(digest, field="upstream receipt digest")
    return _safe_path(root, "upstream_receipts", digest[:2], f"{digest}.json")


def _prepared_path(root: Path, observation_id: str) -> Path:
    if not isinstance(observation_id, str) or not _OBSERVATION_ID.fullmatch(
        observation_id
    ):
        raise MarketMemoryIdentityStoreError("source_observation_id is malformed")
    digest = observation_id.removeprefix("mmidobs_")
    return _safe_path(root, "prepared", digest[:2], f"{observation_id}.json")


def _capture_path(root: Path, capture_id: str) -> Path:
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryIdentityStoreError("identity capture_id is malformed")
    digest = capture_id.removeprefix("mmidscan_")
    return _safe_path(root, "captures", digest[:2], f"{capture_id}.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(
        generation_id
    ):
        raise MarketMemoryIdentityStoreError("identity generation_id is malformed")
    digest = generation_id.removeprefix("mmidgen_")
    return _safe_path(root, "generations", digest[:2], f"{generation_id}.json")


def _read_canonical(
    path: Path, *, limit: int, label: str
) -> tuple[dict[str, Any], bytes]:
    return market_memory_pit._read_canonical_object(path, limit=limit, label=label)


def _read_exact_bytes(
    path: Path, *, limit: int, expected_bytes: int, digest: str, label: str
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryIdentityStoreError(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise MarketMemoryIdentityStoreError(f"{label} is not a regular file")
        if before.st_size <= 0 or before.st_size > limit:
            raise MarketMemoryIdentityStoreError(f"{label} exceeds its byte bound")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise MarketMemoryIdentityStoreError(f"{label} could not be read") from exc
    finally:
        os.close(descriptor)
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(body) != after.st_size
        or len(body) != expected_bytes
        or len(body) > limit
        or sha256(body).hexdigest() != digest
    ):
        raise MarketMemoryIdentityStoreError(f"{label} differs from its receipt")
    return body


def _write_exact_bytes_create_once(
    root: Path, path: Path, body: bytes, *, label: str, limit: int
) -> bool:
    if not isinstance(body, bytes) or not body or len(body) > limit:
        raise MarketMemoryIdentityCaptureError(
            f"{label} is empty or exceeds its byte bound"
        )
    try:
        path.parent.relative_to(root)
    except ValueError as exc:
        raise MarketMemoryIdentityStoreError(
            "identity immutable write escaped its root"
        ) from exc
    market_memory_pit._mkdir_durable(path.parent)
    if path.exists() or path.is_symlink():
        existing = _read_exact_bytes(
            path,
            limit=limit,
            expected_bytes=len(body),
            digest=sha256(body).hexdigest(),
            label=f"existing {label}",
        )
        if existing != body:
            raise MarketMemoryIdentityCaptureError(f"immutable {label} collision")
        return False
    temporary = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(temporary, path, follow_symlinks=False)
            market_memory_pit._directory_fsync(path.parent)
            return True
        except FileExistsError:
            existing = _read_exact_bytes(
                path,
                limit=limit,
                expected_bytes=len(body),
                digest=sha256(body).hexdigest(),
                label=f"raced {label}",
            )
            if existing != body:
                raise MarketMemoryIdentityCaptureError(
                    f"immutable {label} collision"
                ) from None
            return False
    except (MarketMemoryIdentityCaptureError, MarketMemoryIdentityStoreError):
        raise
    except OSError as exc:
        raise MarketMemoryIdentityStoreError(
            f"cannot publish immutable {label}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _new_manifest() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": STORE_MANIFEST_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": "",
        "nonce": uuid4().hex,
        "listing_object_schema": identity_observation.LISTING_OBJECT_SCHEMA,
        "observation_schema": identity_observation.LISTING_OBSERVATION_SCHEMA,
        "prepared_record_schema": PREPARED_RECORD_SCHEMA,
        "capture_receipt_schema": CAPTURE_RECEIPT_SCHEMA,
        "generation_schema": STORE_GENERATION_SCHEMA,
        "evidence_policy": copy.deepcopy(_STORE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["store_id"] = _content_id("mmidstore_", value, field="store_id")
    return value


def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_FIELDS:
        raise MarketMemoryIdentityStoreError(
            "identity store manifest fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    store_id = clean.get("store_id")
    if (
        clean.get("schema") != STORE_MANIFEST_SCHEMA
        or clean.get("profile") != STORE_PROFILE
    ):
        raise MarketMemoryIdentityStoreError("identity store manifest profile drift")
    if not isinstance(store_id, str) or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryIdentityStoreError("identity store_id is malformed")
    if not isinstance(clean.get("nonce"), str) or not re.fullmatch(
        r"[a-f0-9]{32}", clean["nonce"]
    ):
        raise MarketMemoryIdentityStoreError("identity store nonce is malformed")
    expected = {
        "listing_object_schema": identity_observation.LISTING_OBJECT_SCHEMA,
        "observation_schema": identity_observation.LISTING_OBSERVATION_SCHEMA,
        "prepared_record_schema": PREPARED_RECORD_SCHEMA,
        "capture_receipt_schema": CAPTURE_RECEIPT_SCHEMA,
        "generation_schema": STORE_GENERATION_SCHEMA,
        "evidence_policy": _STORE_POLICY,
        "authority": dict(market_memory.AUTHORITY),
    }
    for field, wanted in expected.items():
        if clean.get(field) != wanted:
            raise MarketMemoryIdentityStoreError(
                f"identity store manifest {field} drift"
            )
    if _content_id("mmidstore_", clean, field="store_id") != store_id:
        raise MarketMemoryIdentityStoreError("identity store_id does not bind manifest")
    return clean


def _new_generation(
    *,
    store_id: str,
    previous_generation_id: str | None,
    captures: list[Mapping[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": STORE_GENERATION_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": store_id,
        "generation_id": "",
        "previous_generation_id": previous_generation_id,
        "captures": [copy.deepcopy(dict(row)) for row in captures],
    }
    value["generation_id"] = _content_id("mmidgen_", value, field="generation_id")
    return value


def _validate_generation(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _GENERATION_FIELDS:
        raise MarketMemoryIdentityStoreError(
            "identity generation fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    generation_id = clean.get("generation_id")
    if (
        clean.get("schema") != STORE_GENERATION_SCHEMA
        or clean.get("profile") != STORE_PROFILE
    ):
        raise MarketMemoryIdentityStoreError("identity generation profile drift")
    if clean.get("store_id") != store_id:
        raise MarketMemoryIdentityStoreError(
            "identity generation belongs to another store"
        )
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(
        generation_id
    ):
        raise MarketMemoryIdentityStoreError("identity generation_id is malformed")
    previous = clean.get("previous_generation_id")
    if previous is not None and (
        not isinstance(previous, str) or not _GENERATION_ID.fullmatch(previous)
    ):
        raise MarketMemoryIdentityStoreError(
            "previous identity generation_id is malformed"
        )
    captures = clean.get("captures")
    if not isinstance(captures, list) or len(captures) > _MAX_CAPTURES:
        raise MarketMemoryIdentityStoreError(
            "identity generation captures exceed their bound"
        )
    dates: list[str] = []
    observation_ids: list[str] = []
    capture_ids: list[str] = []
    for row in captures:
        if not isinstance(row, Mapping) or set(row) != _GENERATION_ENTRY_FIELDS:
            raise MarketMemoryIdentityStoreError(
                "identity generation entry fields are not canonical"
            )
        date_partition = row.get("date_partition")
        try:
            parsed_date = date.fromisoformat(date_partition)
        except (TypeError, ValueError) as exc:
            raise MarketMemoryIdentityStoreError(
                "identity generation date partition is malformed"
            ) from exc
        if parsed_date.isoformat() != date_partition:
            raise MarketMemoryIdentityStoreError(
                "identity generation date partition is not canonical"
            )
        observation_id = row.get("source_observation_id")
        capture_id = row.get("capture_id")
        object_id = row.get("listing_object_id")
        if not isinstance(observation_id, str) or not _OBSERVATION_ID.fullmatch(
            observation_id
        ):
            raise MarketMemoryIdentityStoreError(
                "identity generation source_observation_id is malformed"
            )
        if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
            raise MarketMemoryIdentityStoreError(
                "identity generation capture_id is malformed"
            )
        if not isinstance(object_id, str) or not _OBJECT_ID.fullmatch(object_id):
            raise MarketMemoryIdentityStoreError(
                "identity generation listing_object_id is malformed"
            )
        if row.get("listing_state") not in {
            "present_in_snapshot",
            "symbol_absent_from_complete_snapshot",
        }:
            raise MarketMemoryIdentityStoreError(
                "identity generation listing state is malformed"
            )
        if (
            row.get("pit_basis")
            not in {
                "live_captured",
                "public_reconstruction",
            }
            or type(row.get("operational")) is not bool
        ):
            raise MarketMemoryIdentityStoreError(
                "identity generation provenance is malformed"
            )
        if (row["pit_basis"] == "live_captured") is not row["operational"]:
            raise MarketMemoryIdentityStoreError(
                "identity generation operational provenance disagrees"
            )
        dates.append(date_partition)
        observation_ids.append(observation_id)
        capture_ids.append(capture_id)
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise MarketMemoryIdentityStoreError(
            "identity generation date index is not strictly increasing"
        )
    if len(observation_ids) != len(set(observation_ids)) or len(capture_ids) != len(
        set(capture_ids)
    ):
        raise MarketMemoryIdentityStoreError(
            "identity generation contains duplicate identities"
        )
    if _content_id("mmidgen_", clean, field="generation_id") != generation_id:
        raise MarketMemoryIdentityStoreError(
            "identity generation_id does not bind generation"
        )
    return clean


def _new_head(generation: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    return {
        "schema": STORE_HEAD_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": sha256(body).hexdigest(),
        "capture_count": len(generation["captures"]),
    }


def _validate_head(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _HEAD_FIELDS:
        raise MarketMemoryIdentityStoreError("identity HEAD fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if (
        clean.get("schema") != STORE_HEAD_SCHEMA
        or clean.get("profile") != STORE_PROFILE
    ):
        raise MarketMemoryIdentityStoreError("identity HEAD profile drift")
    if clean.get("store_id") != store_id:
        raise MarketMemoryIdentityStoreError("identity HEAD belongs to another store")
    generation_id = clean.get("generation_id")
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(
        generation_id
    ):
        raise MarketMemoryIdentityStoreError("identity HEAD generation_id is malformed")
    _require_digest(clean.get("generation_sha256"), field="HEAD generation digest")
    _require_exact_int(
        clean.get("capture_count"),
        field="HEAD capture_count",
        maximum=_MAX_CAPTURES,
    )
    return clean


def _replace_head(root: Path, head: Mapping[str, Any]) -> None:
    body = _canonical_bytes(head)
    if len(body) > _MAX_HEAD_BYTES:
        raise MarketMemoryIdentityStoreError("identity HEAD exceeds its byte bound")
    path = _head_path(root)
    if path.is_symlink():
        raise MarketMemoryIdentityStoreError("identity HEAD cannot be a symlink")
    temporary = root / f".HEAD.json.tmp.{os.getpid()}.{uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
        market_memory_pit._directory_fsync(root)
    except OSError as exc:
        raise MarketMemoryIdentityStoreError("cannot advance identity HEAD") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


@contextmanager
def _writer_lock(root: Path) -> Iterator[None]:
    path = _safe_path(root, ".writer.lock")
    if path.is_symlink():
        raise MarketMemoryIdentityStoreError("identity writer lock is a symlink")
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise MarketMemoryIdentityStoreError(
            "identity writer lock could not be opened safely"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MarketMemoryIdentityStoreError("identity writer lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _ensure_root(root: str | Path, *, repository_root: str | Path | None) -> Path:
    candidate = validate_identity_observation_store_root(
        root, repository_root=repository_root
    )
    market_memory_pit._mkdir_durable(candidate)
    metadata = candidate.lstat()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise MarketMemoryIdentityStoreError(
            "identity observation store root must remain private"
        )
    return candidate


def _initialize(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = _manifest_path(root)
    head_path = _head_path(root)
    generation_root = _safe_path(root, "generations")
    if (
        manifest_path.exists()
        or manifest_path.is_symlink()
        or head_path.exists()
        or head_path.is_symlink()
        or generation_root.exists()
        or generation_root.is_symlink()
    ):
        raise MarketMemoryIdentityStoreError(
            "identity store initialization is already partial"
        )
    manifest = _new_manifest()
    generation = _new_generation(
        store_id=manifest["store_id"], previous_generation_id=None, captures=[]
    )
    generation_body = _canonical_bytes(generation)
    market_memory_pit._write_create_once(
        root,
        manifest_path,
        _canonical_bytes(manifest),
        label="identity store manifest",
    )
    market_memory_pit._write_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="empty identity generation",
    )
    head = _new_head(generation, body=generation_body)
    _replace_head(root, head)
    return manifest, head, generation


def _initialize_or_load(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    head_path = _head_path(root)
    manifest_path = _manifest_path(root)
    if head_path.exists() or head_path.is_symlink():
        manifest, head, generation, _chain = _load_metadata(root)
        return manifest, head, generation
    if not (manifest_path.exists() or manifest_path.is_symlink()):
        for name in (
            "generations",
            "source_artifacts",
            "listing_objects",
            "upstream_receipts",
            "prepared",
            "captures",
        ):
            candidate = _safe_path(root, name)
            if candidate.exists() or candidate.is_symlink():
                raise MarketMemoryIdentityStoreError(
                    "identity store has data without a manifest/HEAD"
                )
        return _initialize(root)
    manifest, _manifest_body = _read_canonical(
        manifest_path, limit=_MAX_MANIFEST_BYTES, label="identity store manifest"
    )
    clean_manifest = _validate_manifest(manifest)
    for name in (
        "source_artifacts",
        "listing_objects",
        "upstream_receipts",
        "prepared",
        "captures",
    ):
        candidate = _safe_path(root, name)
        if candidate.exists() or candidate.is_symlink():
            raise MarketMemoryIdentityStoreError(
                "identity store has captures without an active HEAD"
            )
    generation = _new_generation(
        store_id=clean_manifest["store_id"],
        previous_generation_id=None,
        captures=[],
    )
    generation_body = _canonical_bytes(generation)
    market_memory_pit._write_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="empty identity generation",
    )
    head = _new_head(generation, body=generation_body)
    _replace_head(root, head)
    return clean_manifest, head, generation


def _load_metadata(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    manifest, _manifest_body = _read_canonical(
        _manifest_path(root),
        limit=_MAX_MANIFEST_BYTES,
        label="identity store manifest",
    )
    clean_manifest = _validate_manifest(manifest)
    head, _head_body = _read_canonical(
        _head_path(root), limit=_MAX_HEAD_BYTES, label="identity store HEAD"
    )
    clean_head = _validate_head(head, store_id=clean_manifest["store_id"])

    chain_reversed: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_id: str | None = clean_head["generation_id"]
    current_body: bytes | None = None
    while current_id is not None:
        if current_id in seen or len(seen) > _MAX_CAPTURES:
            raise MarketMemoryIdentityStoreError(
                "identity generation ancestry is cyclic or unbounded"
            )
        seen.add(current_id)
        generation, body = _read_canonical(
            _generation_path(root, current_id),
            limit=_MAX_GENERATION_BYTES,
            label="identity store generation",
        )
        clean_generation = _validate_generation(
            generation, store_id=clean_manifest["store_id"]
        )
        if clean_generation["generation_id"] != current_id:
            raise MarketMemoryIdentityStoreError(
                "identity generation path and identity disagree"
            )
        if current_body is None:
            current_body = body
            if sha256(body).hexdigest() != clean_head["generation_sha256"]:
                raise MarketMemoryIdentityStoreError(
                    "identity HEAD generation digest mismatch"
                )
        chain_reversed.append(clean_generation)
        current_id = clean_generation["previous_generation_id"]
    chain = list(reversed(chain_reversed))
    if (
        not chain
        or chain[0]["captures"]
        or chain[0]["previous_generation_id"] is not None
    ):
        raise MarketMemoryIdentityStoreError(
            "identity generation ancestry has no empty genesis"
        )
    if len(chain) != len(chain[-1]["captures"]) + 1:
        raise MarketMemoryIdentityStoreError(
            "identity generation ancestry length is not exact"
        )
    for previous, current in pairwise(chain):
        if (
            current["previous_generation_id"] != previous["generation_id"]
            or current["captures"][:-1] != previous["captures"]
            or len(current["captures"]) != len(previous["captures"]) + 1
        ):
            raise MarketMemoryIdentityStoreError(
                "identity generation ancestry is not append-only"
            )
    current = chain[-1]
    if clean_head["capture_count"] != len(current["captures"]):
        raise MarketMemoryIdentityStoreError(
            "identity HEAD capture count disagrees with generation"
        )
    return clean_manifest, clean_head, current, chain


def _prepared_policy(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "first_market_memory_clock_persisted": True,
        "completion_receipt_authenticated": observation["operational"],
        "training_eligible": False,
        "promotion_eligible": False,
        "role": "context_only",
    }


def _new_prepared(bundle: identity_observation.SpyListingObservation) -> dict[str, Any]:
    observation = copy.deepcopy(bundle.observation)
    completion_id = (
        bundle.completion_receipt["receipt_id"]
        if bundle.completion_receipt is not None
        else None
    )
    return {
        "schema": PREPARED_RECORD_SCHEMA,
        "source_observation_id": observation["source_observation_id"],
        "first_observed_at": observation["observed_at"],
        "listing_object_id": observation["listing_object_id"],
        "source_artifact_sha256": observation["source_artifact"]["sha256"],
        "completion_receipt_id": completion_id,
        "observation": observation,
        "evidence_policy": _prepared_policy(observation),
        "authority": dict(market_memory.AUTHORITY),
    }


def _validate_prepared(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PREPARED_FIELDS:
        raise MarketMemoryIdentityStoreError(
            "identity prepared record fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    observation = clean.get("observation")
    if clean.get("schema") != PREPARED_RECORD_SCHEMA or not isinstance(
        observation, Mapping
    ):
        raise MarketMemoryIdentityStoreError("identity prepared record schema drift")
    if (
        clean.get("source_observation_id") != observation.get("source_observation_id")
        or clean.get("listing_object_id") != observation.get("listing_object_id")
        or clean.get("source_artifact_sha256")
        != observation.get("source_artifact", {}).get("sha256")
        or clean.get("first_observed_at") != observation.get("observed_at")
        or observation.get("available_at") != observation.get("observed_at")
    ):
        raise MarketMemoryIdentityStoreError(
            "identity prepared record differs from its observation"
        )
    observation_id = clean.get("source_observation_id")
    if not isinstance(observation_id, str) or not _OBSERVATION_ID.fullmatch(
        observation_id
    ):
        raise MarketMemoryIdentityStoreError(
            "identity prepared source_observation_id is malformed"
        )
    object_id = clean.get("listing_object_id")
    if not isinstance(object_id, str) or not _OBJECT_ID.fullmatch(object_id):
        raise MarketMemoryIdentityStoreError(
            "identity prepared listing_object_id is malformed"
        )
    _require_digest(
        clean.get("source_artifact_sha256"), field="prepared source artifact digest"
    )
    completion_id = clean.get("completion_receipt_id")
    if completion_id is not None and (
        not isinstance(completion_id, str) or not _RECEIPT_ID.fullmatch(completion_id)
    ):
        raise MarketMemoryIdentityStoreError(
            "prepared completion receipt_id is malformed"
        )
    if (completion_id is not None) is not bool(observation.get("operational")):
        raise MarketMemoryIdentityStoreError(
            "prepared completion receipt provenance disagrees"
        )
    if clean.get("evidence_policy") != _prepared_policy(observation):
        raise MarketMemoryIdentityStoreError("prepared evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryIdentityStoreError("prepared authority drift")
    return clean


def _capture_policy(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_artifact_bytes_bound": True,
        "listing_object_content_addressed": True,
        "first_market_memory_clock_persisted": True,
        "completion_receipt_authenticated": observation["operational"],
        "training_eligible": False,
        "promotion_eligible": False,
        "role": "context_only",
    }


def _new_capture_receipt(
    *,
    store_id: str,
    bundle: identity_observation.SpyListingObservation,
    prepared: Mapping[str, Any],
    prepared_body: bytes,
) -> dict[str, Any]:
    observation = copy.deepcopy(dict(prepared["observation"]))
    object_digest = sha256(bundle.listing_object_bytes).hexdigest()
    source = observation["source_artifact"]
    upstream = observation["completion_receipt"]
    value: dict[str, Any] = {
        "schema": CAPTURE_RECEIPT_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": store_id,
        "capture_id": "",
        "source_observation_id": observation["source_observation_id"],
        "listing_object": {
            "listing_object_id": observation["listing_object_id"],
            "sha256": object_digest,
            "bytes": len(bundle.listing_object_bytes),
            "object_key": (
                "listing_objects/"
                f"{observation['listing_object_id'].removeprefix('mmidobj_')[:2]}/"
                f"{observation['listing_object_id']}.json"
            ),
        },
        "source_artifact": {
            "sha256": source["sha256"],
            "bytes": source["bytes"],
            "rows": source["rows"],
            "object_key": (
                f"source_artifacts/{source['sha256'][:2]}/{source['sha256']}.parquet"
            ),
        },
        "upstream_receipt": (
            None
            if upstream is None
            else {
                "receipt_id": upstream["receipt_id"],
                "sha256": upstream["sha256"],
                "bytes": upstream["bytes"],
                "object_key": (
                    f"upstream_receipts/{upstream['sha256'][:2]}/"
                    f"{upstream['sha256']}.json"
                ),
            }
        ),
        "prepared_record": {
            "sha256": sha256(prepared_body).hexdigest(),
            "bytes": len(prepared_body),
            "object_key": (
                "prepared/"
                f"{observation['source_observation_id'].removeprefix('mmidobs_')[:2]}/"
                f"{observation['source_observation_id']}.json"
            ),
        },
        "observation": observation,
        "captured_at": observation["observed_at"],
        "evidence_policy": _capture_policy(observation),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["capture_id"] = _content_id("mmidscan_", value, field="capture_id")
    return value


def _validate_reference_path(actual: object, expected: str, *, label: str) -> None:
    if actual != expected:
        raise MarketMemoryIdentityStoreError(f"{label} object key drift")


def _validate_capture_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CAPTURE_FIELDS:
        raise MarketMemoryIdentityStoreError(
            "identity capture receipt fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    observation = clean.get("observation")
    if (
        clean.get("schema") != CAPTURE_RECEIPT_SCHEMA
        or clean.get("profile") != STORE_PROFILE
        or not isinstance(observation, Mapping)
    ):
        raise MarketMemoryIdentityStoreError("identity capture receipt profile drift")
    store_id = clean.get("store_id")
    capture_id = clean.get("capture_id")
    observation_id = clean.get("source_observation_id")
    if not isinstance(store_id, str) or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryIdentityStoreError("identity capture store_id is malformed")
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryIdentityStoreError("identity capture_id is malformed")
    if not isinstance(observation_id, str) or not _OBSERVATION_ID.fullmatch(
        observation_id
    ):
        raise MarketMemoryIdentityStoreError(
            "identity capture source_observation_id is malformed"
        )
    if observation_id != observation.get("source_observation_id"):
        raise MarketMemoryIdentityStoreError(
            "identity capture differs from its observation identity"
        )
    object_ref = clean.get("listing_object")
    source_ref = clean.get("source_artifact")
    prepared_ref = clean.get("prepared_record")
    upstream_ref = clean.get("upstream_receipt")
    if (
        not isinstance(object_ref, Mapping)
        or set(object_ref) != _OBJECT_REFERENCE_FIELDS
    ):
        raise MarketMemoryIdentityStoreError(
            "identity listing object reference is malformed"
        )
    if (
        not isinstance(source_ref, Mapping)
        or set(source_ref) != _SOURCE_REFERENCE_FIELDS
    ):
        raise MarketMemoryIdentityStoreError(
            "identity source artifact reference is malformed"
        )
    if (
        not isinstance(prepared_ref, Mapping)
        or set(prepared_ref) != _PREPARED_REFERENCE_FIELDS
    ):
        raise MarketMemoryIdentityStoreError("identity prepared reference is malformed")
    if upstream_ref is not None and (
        not isinstance(upstream_ref, Mapping)
        or set(upstream_ref) != _UPSTREAM_REFERENCE_FIELDS
    ):
        raise MarketMemoryIdentityStoreError(
            "identity upstream receipt reference is malformed"
        )
    object_id = object_ref.get("listing_object_id")
    if (
        object_id != observation.get("listing_object_id")
        or not isinstance(object_id, str)
        or not _OBJECT_ID.fullmatch(object_id)
    ):
        raise MarketMemoryIdentityStoreError(
            "identity capture listing_object_id mismatch"
        )
    object_digest = _require_digest(
        object_ref.get("sha256"), field="listing object digest"
    )
    _require_exact_int(
        object_ref.get("bytes"),
        field="listing object bytes",
        minimum=1,
        maximum=_MAX_LISTING_OBJECT_BYTES,
    )
    _validate_reference_path(
        object_ref.get("object_key"),
        f"listing_objects/{object_id.removeprefix('mmidobj_')[:2]}/{object_id}.json",
        label="listing object",
    )
    source_digest = _require_digest(
        source_ref.get("sha256"), field="source artifact digest"
    )
    _require_exact_int(
        source_ref.get("bytes"),
        field="source artifact bytes",
        minimum=1,
        maximum=_MAX_SOURCE_BYTES,
    )
    _require_exact_int(
        source_ref.get("rows"),
        field="source artifact rows",
        minimum=1,
        maximum=30_000,
    )
    if (
        source_digest != observation.get("source_artifact", {}).get("sha256")
        or source_ref.get("bytes")
        != observation.get("source_artifact", {}).get("bytes")
        or source_ref.get("rows") != observation.get("source_artifact", {}).get("rows")
    ):
        raise MarketMemoryIdentityStoreError(
            "identity source reference differs from observation"
        )
    _validate_reference_path(
        source_ref.get("object_key"),
        f"source_artifacts/{source_digest[:2]}/{source_digest}.parquet",
        label="source artifact",
    )
    prepared_digest = _require_digest(
        prepared_ref.get("sha256"), field="prepared record digest"
    )
    _require_exact_int(
        prepared_ref.get("bytes"),
        field="prepared record bytes",
        minimum=1,
        maximum=_MAX_PREPARED_BYTES,
    )
    _validate_reference_path(
        prepared_ref.get("object_key"),
        f"prepared/{observation_id.removeprefix('mmidobs_')[:2]}/{observation_id}.json",
        label="prepared record",
    )
    completion = observation.get("completion_receipt")
    if completion is None:
        if upstream_ref is not None:
            raise MarketMemoryIdentityStoreError(
                "reconstruction capture cannot reference an upstream receipt"
            )
    else:
        if not isinstance(upstream_ref, Mapping):
            raise MarketMemoryIdentityStoreError(
                "operational capture is missing its upstream receipt"
            )
        receipt_id = upstream_ref.get("receipt_id")
        receipt_digest = _require_digest(
            upstream_ref.get("sha256"), field="upstream receipt digest"
        )
        _require_exact_int(
            upstream_ref.get("bytes"),
            field="upstream receipt bytes",
            minimum=1,
            maximum=_MAX_UPSTREAM_RECEIPT_BYTES,
        )
        if (
            receipt_id != completion.get("receipt_id")
            or receipt_digest != completion.get("sha256")
            or upstream_ref.get("bytes") != completion.get("bytes")
        ):
            raise MarketMemoryIdentityStoreError(
                "upstream receipt reference differs from observation"
            )
        _validate_reference_path(
            upstream_ref.get("object_key"),
            f"upstream_receipts/{receipt_digest[:2]}/{receipt_digest}.json",
            label="upstream receipt",
        )
    if clean.get("captured_at") != observation.get("observed_at"):
        raise MarketMemoryIdentityStoreError(
            "identity captured_at differs from first observation clock"
        )
    if clean.get("evidence_policy") != _capture_policy(observation):
        raise MarketMemoryIdentityStoreError("identity capture evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryIdentityStoreError("identity capture authority drift")
    if _content_id("mmidscan_", clean, field="capture_id") != capture_id:
        raise MarketMemoryIdentityStoreError(
            "identity capture_id does not bind receipt"
        )
    # Keep locals referenced after validation so accidental removals are caught by lint.
    if not object_digest or not prepared_digest:  # pragma: no cover
        raise MarketMemoryIdentityStoreError("identity capture digest is empty")
    return clean


def _generation_entry(receipt: Mapping[str, Any]) -> dict[str, Any]:
    observation = receipt["observation"]
    return {
        "date_partition": observation["date_partition"],
        "source_observation_id": observation["source_observation_id"],
        "capture_id": receipt["capture_id"],
        "listing_object_id": observation["listing_object_id"],
        "listing_state": observation["listing_state"],
        "pit_basis": observation["pit_basis"],
        "operational": observation["operational"],
    }


def _load_visible_capture(
    root: Path, *, entry: Mapping[str, Any], store_id: str
) -> StoredIdentityCapture:
    capture, capture_body = _read_canonical(
        _capture_path(root, entry["capture_id"]),
        limit=_MAX_CAPTURE_BYTES,
        label="identity capture receipt",
    )
    clean_capture = _validate_capture_receipt(capture)
    if clean_capture["store_id"] != store_id or _generation_entry(
        clean_capture
    ) != dict(entry):
        raise MarketMemoryIdentityStoreError(
            "identity generation entry differs from capture receipt"
        )
    if len(capture_body) > _MAX_CAPTURE_BYTES:
        raise MarketMemoryIdentityStoreError("identity capture exceeds byte bound")

    object_ref = clean_capture["listing_object"]
    listing, listing_body = _read_canonical(
        _listing_object_path(root, object_ref["listing_object_id"]),
        limit=_MAX_LISTING_OBJECT_BYTES,
        label="identity listing object",
    )
    if (
        len(listing_body) != object_ref["bytes"]
        or sha256(listing_body).hexdigest() != object_ref["sha256"]
    ):
        raise MarketMemoryIdentityStoreError(
            "identity listing object differs from capture receipt"
        )

    source_ref = clean_capture["source_artifact"]
    source_body = _read_exact_bytes(
        _source_path(root, source_ref["sha256"]),
        limit=_MAX_SOURCE_BYTES,
        expected_bytes=source_ref["bytes"],
        digest=source_ref["sha256"],
        label="identity source artifact",
    )

    completion_payload: dict[str, Any] | None = None
    completion_body: bytes | None = None
    upstream_ref = clean_capture["upstream_receipt"]
    if upstream_ref is not None:
        completion_body = _read_exact_bytes(
            _upstream_receipt_path(root, upstream_ref["sha256"]),
            limit=_MAX_UPSTREAM_RECEIPT_BYTES,
            expected_bytes=upstream_ref["bytes"],
            digest=upstream_ref["sha256"],
            label="identity upstream receipt",
        )
        try:
            completion_payload = json.loads(completion_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MarketMemoryIdentityStoreError(
                "identity upstream receipt is not JSON"
            ) from exc
        if not isinstance(completion_payload, dict):
            raise MarketMemoryIdentityStoreError(
                "identity upstream receipt must be an object"
            )

    prepared_ref = clean_capture["prepared_record"]
    prepared, prepared_body = _read_canonical(
        _prepared_path(root, clean_capture["source_observation_id"]),
        limit=_MAX_PREPARED_BYTES,
        label="identity prepared record",
    )
    clean_prepared = _validate_prepared(prepared)
    if (
        len(prepared_body) != prepared_ref["bytes"]
        or sha256(prepared_body).hexdigest() != prepared_ref["sha256"]
        or clean_prepared["observation"] != clean_capture["observation"]
    ):
        raise MarketMemoryIdentityStoreError(
            "identity prepared record differs from capture receipt"
        )

    observation = clean_capture["observation"]
    synthetic_path = Path("snapshots") / f"{observation['date_partition']}.parquet"
    bundle = identity_observation.SpyListingObservation(
        snapshot_path=synthetic_path,
        snapshot_bytes=source_body,
        listing_object=listing,
        listing_object_bytes=listing_body,
        observation=copy.deepcopy(observation),
        observation_bytes=_canonical_bytes(observation),
        completion_receipt=completion_payload,
        completion_receipt_bytes=completion_body,
    )
    try:
        validated_bundle = identity_observation.validate_spy_listing_observation(bundle)
    except identity_observation.MarketMemoryIdentityObservationError as exc:
        raise MarketMemoryIdentityStoreError(
            "stored identity observation fails its source contract"
        ) from exc
    return StoredIdentityCapture(
        observation=copy.deepcopy(validated_bundle.observation),
        capture_receipt=clean_capture,
        listing_object=copy.deepcopy(validated_bundle.listing_object),
        source_artifact_bytes=source_body,
        completion_receipt=copy.deepcopy(completion_payload),
        completion_receipt_bytes=completion_body,
    )


def _load_snapshot(root: Path) -> IdentityStoreSnapshot:
    manifest, head, generation, _chain = _load_metadata(root)
    captures = tuple(
        _load_visible_capture(root, entry=entry, store_id=manifest["store_id"])
        for entry in generation["captures"]
    )
    return IdentityStoreSnapshot(
        manifest=manifest,
        head=head,
        generation=generation,
        captures=captures,
    )


def initialize_identity_observation_store(
    root: str | Path, *, repository_root: str | Path | None = None
) -> dict[str, Any]:
    """Create or validate the private identity-v1 store and return its manifest."""

    candidate = _ensure_root(root, repository_root=repository_root)
    with _writer_lock(candidate):
        manifest, _head, _generation = _initialize_or_load(candidate)
        loaded_manifest, _loaded_head, _loaded_generation, _chain = _load_metadata(
            candidate
        )
    if loaded_manifest != manifest:
        raise MarketMemoryIdentityStoreError(
            "identity store changed during initialization"
        )
    return copy.deepcopy(loaded_manifest)


def load_identity_observation_store(
    root: str | Path, *, repository_root: str | Path | None = None
) -> IdentityStoreSnapshot:
    """Load the exact HEAD view; never skip around corruption or use orphans."""

    candidate = validate_identity_observation_store_root(
        root, repository_root=repository_root
    )
    if not candidate.exists():
        raise MarketMemoryIdentityStoreError("identity observation store is missing")
    return _load_snapshot(candidate).detached()


def _fault_injection_point(_step: str) -> None:
    """Test seam for proving crash prefixes; production intentionally does nothing."""


def _candidate_matches_prepared(
    bundle: identity_observation.SpyListingObservation,
    prepared: Mapping[str, Any],
) -> None:
    candidate = bundle.observation
    stored = prepared["observation"]
    if (
        candidate["source_observation_id"] != stored["source_observation_id"]
        or candidate["listing_object_id"] != stored["listing_object_id"]
        or candidate["source_artifact"] != stored["source_artifact"]
        or candidate["completion_receipt"] != stored["completion_receipt"]
        or bundle.listing_object["listing_object_id"] != stored["listing_object_id"]
    ):
        raise MarketMemoryIdentityCaptureError(
            "retry candidate differs from its prepared source observation"
        )
    candidate_without_clocks = copy.deepcopy(candidate)
    stored_without_clocks = copy.deepcopy(stored)
    for value in (candidate_without_clocks, stored_without_clocks):
        value["available_at"] = ""
        value["observed_at"] = ""
    if candidate_without_clocks != stored_without_clocks:
        raise MarketMemoryIdentityCaptureError(
            "retry candidate changed outside its local observation clock"
        )


def _result(
    *,
    published: bool,
    stored: StoredIdentityCapture,
    generation: Mapping[str, Any],
    head: Mapping[str, Any],
) -> IdentityCaptureResult:
    return IdentityCaptureResult(
        published=published,
        observation=copy.deepcopy(stored.observation),
        capture_receipt=copy.deepcopy(stored.capture_receipt),
        generation=copy.deepcopy(dict(generation)),
        head=copy.deepcopy(dict(head)),
    )


def capture_spy_listing_observation(
    root: str | Path,
    bundle: identity_observation.SpyListingObservation,
    *,
    repository_root: str | Path | None = None,
) -> IdentityCaptureResult:
    """Idempotently admit one exact observation and advance HEAD only when complete."""

    try:
        candidate_bundle = identity_observation.validate_spy_listing_observation(bundle)
    except identity_observation.MarketMemoryIdentityObservationError as exc:
        raise MarketMemoryIdentityCaptureError(
            "candidate SPY listing observation is invalid"
        ) from exc
    candidate = _ensure_root(root, repository_root=repository_root)
    observation_id = candidate_bundle.observation["source_observation_id"]
    date_partition = candidate_bundle.observation["date_partition"]

    with _writer_lock(candidate):
        manifest, _head, generation = _initialize_or_load(candidate)
        existing_entry = next(
            (
                entry
                for entry in generation["captures"]
                if entry["source_observation_id"] == observation_id
            ),
            None,
        )
        if existing_entry is not None:
            existing = _load_visible_capture(
                candidate, entry=existing_entry, store_id=manifest["store_id"]
            )
            if (
                existing.source_artifact_bytes != candidate_bundle.snapshot_bytes
                or existing.listing_object != candidate_bundle.listing_object
                or existing.completion_receipt_bytes
                != candidate_bundle.completion_receipt_bytes
            ):
                raise MarketMemoryIdentityCaptureError(
                    "visible source observation collides with different exact bytes"
                )
            prepared, _body = _read_canonical(
                _prepared_path(candidate, observation_id),
                limit=_MAX_PREPARED_BYTES,
                label="identity prepared record",
            )
            _candidate_matches_prepared(candidate_bundle, _validate_prepared(prepared))
            return _result(
                published=False,
                stored=existing,
                generation=generation,
                head=_head,
            ).detached()
        for entry in generation["captures"]:
            if entry["date_partition"] == date_partition:
                raise MarketMemoryIdentityCaptureError(
                    "identity store already has a different observation for this date"
                )
        if (
            generation["captures"]
            and date_partition <= generation["captures"][-1]["date_partition"]
        ):
            raise MarketMemoryIdentityCaptureError(
                "identity observations must accrue in strictly increasing date order"
            )
        if len(generation["captures"]) >= _MAX_CAPTURES:
            raise MarketMemoryIdentityCaptureError(
                "identity observation pilot reached its capture bound"
            )

        # Freeze the first post-read Market Memory clock before any later write
        # can fault.  The record is not visible through HEAD, but every retry of
        # this exact upstream occurrence must reuse it.
        prepared_path = _prepared_path(candidate, observation_id)
        if prepared_path.exists() or prepared_path.is_symlink():
            prepared, prepared_body = _read_canonical(
                prepared_path,
                limit=_MAX_PREPARED_BYTES,
                label="identity prepared record",
            )
            clean_prepared = _validate_prepared(prepared)
            _candidate_matches_prepared(candidate_bundle, clean_prepared)
        else:
            clean_prepared = _new_prepared(candidate_bundle)
            prepared_body = _canonical_bytes(clean_prepared)
            if len(prepared_body) > _MAX_PREPARED_BYTES:
                raise MarketMemoryIdentityCaptureError(
                    "identity prepared record exceeds its byte bound"
                )
            market_memory_pit._write_create_once(
                candidate,
                prepared_path,
                prepared_body,
                label="identity prepared record",
            )
        _fault_injection_point("prepared")

        source = candidate_bundle.observation["source_artifact"]
        _write_exact_bytes_create_once(
            candidate,
            _source_path(candidate, source["sha256"]),
            candidate_bundle.snapshot_bytes,
            label="identity source artifact",
            limit=_MAX_SOURCE_BYTES,
        )
        _fault_injection_point("source_artifact")

        market_memory_pit._write_create_once(
            candidate,
            _listing_object_path(
                candidate, candidate_bundle.listing_object["listing_object_id"]
            ),
            candidate_bundle.listing_object_bytes,
            label="identity listing object",
        )
        _fault_injection_point("listing_object")

        if candidate_bundle.completion_receipt_bytes is not None:
            completion_digest = sha256(
                candidate_bundle.completion_receipt_bytes
            ).hexdigest()
            _write_exact_bytes_create_once(
                candidate,
                _upstream_receipt_path(candidate, completion_digest),
                candidate_bundle.completion_receipt_bytes,
                label="identity upstream receipt",
                limit=_MAX_UPSTREAM_RECEIPT_BYTES,
            )
        _fault_injection_point("upstream_receipt")

        receipt = _new_capture_receipt(
            store_id=manifest["store_id"],
            bundle=candidate_bundle,
            prepared=clean_prepared,
            prepared_body=prepared_body,
        )
        receipt = _validate_capture_receipt(receipt)
        receipt_body = _canonical_bytes(receipt)
        if len(receipt_body) > _MAX_CAPTURE_BYTES:
            raise MarketMemoryIdentityCaptureError(
                "identity capture receipt exceeds its byte bound"
            )
        market_memory_pit._write_create_once(
            candidate,
            _capture_path(candidate, receipt["capture_id"]),
            receipt_body,
            label="identity capture receipt",
        )
        _fault_injection_point("capture_receipt")

        captures = [copy.deepcopy(dict(row)) for row in generation["captures"]]
        captures.append(_generation_entry(receipt))
        next_generation = _new_generation(
            store_id=manifest["store_id"],
            previous_generation_id=generation["generation_id"],
            captures=captures,
        )
        next_generation = _validate_generation(
            next_generation, store_id=manifest["store_id"]
        )
        generation_body = _canonical_bytes(next_generation)
        if len(generation_body) > _MAX_GENERATION_BYTES:
            raise MarketMemoryIdentityCaptureError(
                "identity generation exceeds its byte bound"
            )
        market_memory_pit._write_create_once(
            candidate,
            _generation_path(candidate, next_generation["generation_id"]),
            generation_body,
            label="identity store generation",
        )
        _fault_injection_point("generation")

        next_head = _new_head(next_generation, body=generation_body)
        _replace_head(candidate, next_head)
        _fault_injection_point("head")

        final_manifest, final_head, final_generation, _chain = _load_metadata(candidate)
        final_entry = next(
            entry
            for entry in final_generation["captures"]
            if entry["source_observation_id"] == observation_id
        )
        stored = _load_visible_capture(
            candidate, entry=final_entry, store_id=final_manifest["store_id"]
        )
        return _result(
            published=True,
            stored=stored,
            generation=final_generation,
            head=final_head,
        ).detached()


def default_identity_observation_store_root(
    repository_root: str | Path,
) -> Path:
    """Return the fixed API-inaccessible production state root."""

    repository = Path(repository_root).expanduser().resolve()
    if not repository.is_dir():
        raise MarketMemoryIdentityStoreError("repository root is unavailable")
    return Path("/var/lib/macro-market-memory/state/identity-v1")


__all__ = [
    "CAPTURE_RECEIPT_SCHEMA",
    "PREPARED_RECORD_SCHEMA",
    "STORE_GENERATION_SCHEMA",
    "STORE_HEAD_SCHEMA",
    "STORE_MANIFEST_SCHEMA",
    "STORE_PROFILE",
    "IdentityCaptureResult",
    "IdentityStoreSnapshot",
    "MarketMemoryIdentityCaptureError",
    "MarketMemoryIdentityStoreError",
    "StoredIdentityCapture",
    "capture_spy_listing_observation",
    "default_identity_observation_store_root",
    "initialize_identity_observation_store",
    "load_identity_observation_store",
    "validate_identity_observation_store_root",
]
