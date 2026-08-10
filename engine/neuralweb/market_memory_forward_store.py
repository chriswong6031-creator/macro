"""Temp-only immutable ledger for synthetic Market Memory forward contracts.

This module is deliberately a storage primitive, not a producer.  It has no
default root, environment-variable lookup, command line, scheduler, service,
API, or production call site.  A caller must supply an explicit directory
inside the operating system's temporary tree and already-built records from
``market_memory_forward``.

Each admitted record is canonical JSON in one of four disjoint content-
addressed namespaces.  A cumulative immutable generation is written and
fsynced before ``HEAD.json`` is atomically advanced.  Readers authenticate the
entire reachable generation chain and every named record; they never scan for
"the latest" generation or skip malformed bytes.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Final, Literal
from uuid import uuid4

from engine.neuralweb import market_memory_forward as forward

RecordKind = Literal["state", "trial", "forecast", "outcome"]

STORE_MANIFEST_SCHEMA = "market_memory.forward_store_manifest.v1"
STORE_GENERATION_SCHEMA = "market_memory.forward_store_generation.v1"
STORE_HEAD_SCHEMA = "market_memory.forward_store_head.v1"
STORE_PROFILE = "market_memory.private.synthetic_forward_research.v1"

_KINDS: Final[tuple[RecordKind, ...]] = (
    "state",
    "trial",
    "forecast",
    "outcome",
)
_SCHEMA_BY_KIND: Final[dict[RecordKind, str]] = {
    "state": "market_memory.state_snapshot.v1",
    "trial": "market_memory.trial_registration.v1",
    "forecast": "market_memory.forecast_record.v1",
    "outcome": "market_memory.outcome_record.v1",
}
_ID_FIELD_BY_KIND: Final[dict[RecordKind, str]] = {
    "state": "state_snapshot_id",
    "trial": "trial_registration_id",
    "forecast": "forecast_id",
    "outcome": "outcome_record_id",
}
_SEMANTIC_FIELD_BY_KIND: Final[dict[RecordKind, str]] = {
    "state": "context_id",
    "trial": "trial_key",
    "forecast": "forecast_key",
    "outcome": "outcome_event_id",
}
_ID_PATTERN_BY_KIND: Final[dict[RecordKind, re.Pattern[str]]] = {
    "state": re.compile(r"mmstate_[a-f0-9]{64}\Z"),
    "trial": re.compile(r"mmtrial_[a-f0-9]{64}\Z"),
    "forecast": re.compile(r"mmforecast_[a-f0-9]{64}\Z"),
    "outcome": re.compile(r"mmoutcome_[a-f0-9]{64}\Z"),
}
_VALIDATOR_NAME_BY_KIND: Final[dict[RecordKind, str]] = {
    "state": "validate_state_snapshot_record",
    "trial": "validate_trial_registration",
    "forecast": "validate_forecast_record",
    "outcome": "validate_outcome_record",
}

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmforwardstore_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmforwardgeneration_[a-f0-9]{64}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_HEAD_BYTES = 32 * 1024
_MAX_RECORD_BYTES = 256 * 1024
_MAX_GENERATION_BYTES = 256 * 1024
_MAX_RECORDS = 256
_MAX_GENERATION_DEPTH = _MAX_RECORDS
_MAX_SEMANTIC_KEY_BYTES = 512
_MAX_ORPHAN_TEMPS = 64

_STORE_POLICY: Final[dict[str, Any]] = {
    "emission_enabled": False,
    "synthetic_only": True,
    "private": True,
    "research_only": True,
    "live_inputs_allowed": False,
    "public_serving_allowed": False,
    "training_eligible": False,
    "promotion_eligible": False,
    "authority": "none",
}
_EMPTY_COUNTS: Final[dict[str, int]] = {kind: 0 for kind in _KINDS}

_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "nonce",
        "record_schemas",
        "record_kinds",
        "limits",
        "policy",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "kind",
        "record_id",
        "semantic_key",
        "sha256",
        "bytes",
        "object_key",
        "outcome_event_id",
        "revision_number",
        "revision_of",
    }
)
_GENERATION_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "generation_id",
        "previous_generation_id",
        "depth",
        "entries",
        "counts",
        "replay_digest",
    }
)
_HEAD_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "generation_id",
        "generation_sha256",
        "depth",
        "record_count",
        "counts",
        "replay_digest",
    }
)


class MarketMemoryForwardStoreError(RuntimeError):
    """The synthetic forward store is unavailable, unsafe, or corrupt."""


class MarketMemoryForwardConflictError(MarketMemoryForwardStoreError):
    """An append conflicts with immutable or semantic-key history."""


class MarketMemoryForwardMaturityError(MarketMemoryForwardStoreError):
    """An outcome is not yet observable or does not match its forecast clock."""


@dataclass(frozen=True)
class ForwardAppendResult:
    """Detached result of one idempotent or newly published append."""

    appended: bool
    kind: RecordKind
    record_id: str
    generation_id: str
    replay_digest: str


@dataclass(frozen=True)
class _LoadedState:
    manifest: dict[str, Any]
    head: dict[str, Any]
    chain: tuple[dict[str, Any], ...]
    records: dict[tuple[RecordKind, str], dict[str, Any]]

    @property
    def generation(self) -> dict[str, Any]:
        return self.chain[-1]


def _canonical_bytes(value: object) -> bytes:
    """Use the contract module's canonical encoder for every stored object."""

    try:
        body = forward.canonical_json_bytes(value)
    except Exception as exc:  # contract errors are normalized at this boundary
        raise MarketMemoryForwardStoreError(
            "forward store value is not finite canonical JSON"
        ) from exc
    if type(body) is not bytes:
        raise MarketMemoryForwardStoreError(
            "forward canonical encoder did not return bytes"
        )
    return body


def _digest(body: bytes) -> str:
    return sha256(body).hexdigest()


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + _digest(_canonical_bytes(core))


def _require_exact_int(
    value: object, *, field: str, minimum: int = 0, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MarketMemoryForwardStoreError(
            f"forward store {field} is outside its integer bound"
        )
    return value


def _require_string(
    value: object, *, field: str, maximum_bytes: int = _MAX_SEMANTIC_KEY_BYTES
) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > maximum_bytes
    ):
        raise MarketMemoryForwardStoreError(
            f"forward store {field} is not a bounded non-empty string"
        )
    return value


def _require_digest(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise MarketMemoryForwardStoreError(
            f"forward store {field} is not lowercase SHA-256"
        )
    return value


def _parse_exact_utc(value: object, *, field: str) -> datetime:
    if type(value) is not str or not _RFC3339_UTC.fullmatch(value):
        raise MarketMemoryForwardStoreError(
            f"forward store {field} is not exact RFC3339 UTC"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryForwardStoreError(
            f"forward store {field} is not a real timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        raise MarketMemoryForwardStoreError(f"forward store {field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _require_kind(kind: object) -> RecordKind:
    if type(kind) is not str or kind not in _KINDS:
        raise MarketMemoryForwardStoreError("forward record kind is not recognized")
    return kind  # type: ignore[return-value]


def _validate_record(kind: RecordKind, value: Mapping[str, Any]) -> dict[str, Any]:
    validator = getattr(forward, _VALIDATOR_NAME_BY_KIND[kind], None)
    if not callable(validator):
        raise MarketMemoryForwardStoreError(
            f"forward contract validator for {kind} is unavailable"
        )
    candidate = copy.deepcopy(dict(value))
    try:
        validated = validator(candidate)
    except Exception as exc:
        raise MarketMemoryForwardStoreError(
            f"forward {kind} record fails its frozen contract"
        ) from exc
    if validated is None:
        validated = candidate
    if not isinstance(validated, Mapping):
        raise MarketMemoryForwardStoreError(
            f"forward {kind} validator did not return a record"
        )
    record = copy.deepcopy(dict(validated))
    if record.get("schema") != _SCHEMA_BY_KIND[kind]:
        raise MarketMemoryForwardStoreError(f"forward {kind} schema is not frozen v1")
    id_field = _ID_FIELD_BY_KIND[kind]
    record_id = record.get(id_field)
    if type(record_id) is not str or not _ID_PATTERN_BY_KIND[kind].fullmatch(record_id):
        raise MarketMemoryForwardStoreError(f"forward {kind} record id is malformed")
    semantic_field = _SEMANTIC_FIELD_BY_KIND[kind]
    _require_string(record.get(semantic_field), field=semantic_field)
    body = _canonical_bytes(record)
    if len(body) <= 0 or len(body) > _MAX_RECORD_BYTES:
        raise MarketMemoryForwardStoreError(
            f"forward {kind} record exceeds its safe byte bound"
        )
    return record


def validate_forward_store_root(root: str | Path) -> Path:
    """Require an absolute, non-symlink root beneath the OS temporary tree."""

    if not isinstance(root, (str, Path)) or not os.fspath(root):
        raise MarketMemoryForwardStoreError("forward store root must be explicit")
    lexical = Path(root).expanduser()
    if not lexical.is_absolute():
        raise MarketMemoryForwardStoreError("forward store root must be absolute")
    candidate = Path(os.path.abspath(os.fspath(lexical)))
    lexical_temporary_root = Path(os.path.abspath(tempfile.gettempdir()))
    temporary_root = lexical_temporary_root.resolve(strict=False)
    if (
        candidate != lexical_temporary_root
        and lexical_temporary_root in candidate.parents
    ):
        normalized_candidate = temporary_root / candidate.relative_to(
            lexical_temporary_root
        )
    elif candidate != temporary_root and temporary_root in candidate.parents:
        normalized_candidate = candidate
    else:
        raise MarketMemoryForwardStoreError(
            "forward store root must be a child of the temporary directory"
        )
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate != normalized_candidate:
        raise MarketMemoryForwardStoreError(
            "forward store root and parents cannot traverse symlinks"
        )
    candidate = normalized_candidate
    cursor = candidate
    while cursor != temporary_root:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MarketMemoryForwardStoreError(
                "forward store root components cannot be inspected"
            ) from exc
        else:
            if stat.S_ISLNK(metadata.st_mode):
                raise MarketMemoryForwardStoreError(
                    "forward store root and parents cannot be symlinks"
                )
        if cursor == cursor.parent:
            raise MarketMemoryForwardStoreError(
                "forward store root escaped the temporary directory"
            )
        cursor = cursor.parent
    return candidate


def _safe_path(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store object path escaped its root"
        ) from exc
    return path


def _manifest_path(root: Path) -> Path:
    return _safe_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return _safe_path(root, "HEAD.json")


def _lock_path(root: Path) -> Path:
    return _safe_path(root, ".lock")


def _record_path(root: Path, kind: RecordKind, record_id: str) -> Path:
    if not _ID_PATTERN_BY_KIND[kind].fullmatch(record_id):
        raise MarketMemoryForwardStoreError(f"forward {kind} record id is unsafe")
    return _safe_path(root, "objects", kind, record_id[-64:-62], f"{record_id}.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryForwardStoreError("forward generation id is unsafe")
    return _safe_path(
        root, "generations", generation_id[-64:-62], f"{generation_id}.json"
    )


def _object_key(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store object is outside its root"
        ) from exc


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store directory cannot be opened safely"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store directory cannot be fsynced"
        ) from exc
    finally:
        os.close(descriptor)


def _validate_private_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise MarketMemoryForwardStoreError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MarketMemoryForwardStoreError(f"{label} is not a safe directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
        raise MarketMemoryForwardStoreError(f"{label} is not private to this user")


def _mkdir_private(path: Path) -> None:
    if path.exists():
        _validate_private_directory(path, label="forward store directory")
        return
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store directory cannot be created"
        ) from exc
    _validate_private_directory(path, label="forward store directory")
    _fsync_directory(path.parent)


def _validate_private_file_metadata(metadata: os.stat_result, *, label: str) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise MarketMemoryForwardStoreError(f"{label} is not a regular file")
    if (
        stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
    ):
        raise MarketMemoryForwardStoreError(f"{label} is not private to this user")


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite token {value}")

    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_nonfinite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryForwardStoreError(f"{label} is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise MarketMemoryForwardStoreError(f"{label} is not a JSON object")
    if body != _canonical_bytes(payload):
        raise MarketMemoryForwardStoreError(f"{label} is not canonical JSON bytes")
    return payload


def _read_bytes(path: Path, *, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryForwardStoreError(f"{label} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        _validate_private_file_metadata(before, label=label)
        if before.st_size <= 0 or before.st_size > limit:
            raise MarketMemoryForwardStoreError(f"{label} exceeds its safe size bound")
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
        raise MarketMemoryForwardStoreError(f"{label} cannot be read") from exc
    finally:
        os.close(descriptor)
    if (
        len(body) != before.st_size
        or len(body) > limit
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        raise MarketMemoryForwardStoreError(f"{label} changed while it was read")
    return body


def _read_json(path: Path, *, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    body = _read_bytes(path, limit=limit, label=label)
    return _strict_json_object(body, label=label), body


def _temp_path_for(path: Path) -> Path:
    return path.parent / f".{path.name}.{uuid4().hex}.tmp"


def _recover_published_temp_link(path: Path, *, label: str) -> None:
    """Finish the unlink half of a prior atomic hard-link publication."""

    try:
        target = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise MarketMemoryForwardStoreError(f"{label} cannot be inspected") from exc
    if target.st_nlink == 1:
        return
    if (
        not stat.S_ISREG(target.st_mode)
        or stat.S_IMODE(target.st_mode) != 0o600
        or target.st_uid != os.geteuid()
        or target.st_nlink != 2
    ):
        raise MarketMemoryForwardStoreError(
            f"{label} has unsafe interrupted-publication metadata"
        )
    candidates = list(path.parent.glob(f".{path.name}.*.tmp"))
    if len(candidates) > _MAX_ORPHAN_TEMPS:
        raise MarketMemoryForwardStoreError(f"{label} temp-orphan bound is exhausted")
    linked = []
    for candidate in candidates:
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MarketMemoryForwardStoreError(
                f"{label} temp publication cannot be inspected"
            ) from exc
        if metadata.st_dev == target.st_dev and metadata.st_ino == target.st_ino:
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 2
            ):
                raise MarketMemoryForwardStoreError(
                    f"{label} temp publication metadata is unsafe"
                )
            linked.append(candidate)
    if len(linked) != 1:
        raise MarketMemoryForwardStoreError(
            f"{label} interrupted publication cannot be recovered safely"
        )
    try:
        linked[0].unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            f"{label} interrupted publication cannot be recovered"
        ) from exc
    _fsync_directory(path.parent)
    _validate_private_file_metadata(path.lstat(), label=label)


def _cleanup_orphan_temps(root: Path) -> None:
    """Bound and remove same-store temp files while the store lock is held."""

    candidates: list[Path] = []
    try:
        for candidate in root.rglob(".*.tmp"):
            candidates.append(candidate)
            if len(candidates) > _MAX_ORPHAN_TEMPS:
                raise MarketMemoryForwardStoreError(
                    "forward store temp-orphan bound is exhausted"
                )
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store temp orphans cannot be enumerated"
        ) from exc
    synced_parents: set[Path] = set()
    for candidate in candidates:
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MarketMemoryForwardStoreError(
                "forward store temp orphan cannot be inspected"
            ) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink not in {1, 2}
        ):
            raise MarketMemoryForwardStoreError(
                "forward store temp orphan metadata is unsafe"
            )
        _validate_private_directory(candidate.parent, label="forward store temp parent")
        try:
            candidate.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MarketMemoryForwardStoreError(
                "forward store temp orphan cannot be removed"
            ) from exc
        synced_parents.add(candidate.parent)
    for parent in sorted(synced_parents):
        _fsync_directory(parent)


def _write_create_once(path: Path, body: bytes, *, label: str) -> bool:
    if not body:
        raise MarketMemoryForwardStoreError(f"{label} cannot be empty")
    _mkdir_private(path.parent)
    _recover_published_temp_link(path, label=label)
    if path.exists():
        existing = _read_bytes(
            path, limit=max(len(body), _MAX_RECORD_BYTES), label=label
        )
        if existing != body:
            raise MarketMemoryForwardConflictError(
                f"{label} already exists with different canonical bytes"
            )
        return False

    temp_path = _temp_path_for(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(temp_path, flags, 0o600)
        offset = 0
        while offset < len(body):
            written = os.write(descriptor, body[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
        _validate_private_file_metadata(os.fstat(descriptor), label=f"{label} temp")
        os.close(descriptor)
        descriptor = None
        try:
            os.link(temp_path, path, follow_symlinks=False)
            created = True
        except FileExistsError:
            _recover_published_temp_link(path, label=label)
        except FileNotFoundError:
            if not path.exists():
                raise
            _recover_published_temp_link(path, label=label)
    except MarketMemoryForwardStoreError:
        raise
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            f"{label} cannot be durably created"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as exc:
            raise MarketMemoryForwardStoreError(
                f"{label} temp file cannot be removed"
            ) from exc
        _fsync_directory(path.parent)

    existing = _read_bytes(path, limit=max(len(body), _MAX_RECORD_BYTES), label=label)
    if existing != body:
        raise MarketMemoryForwardConflictError(
            f"{label} already exists with different canonical bytes"
        )
    return created


def _write_json_create_once(
    path: Path, value: Mapping[str, Any], *, label: str
) -> tuple[bytes, bool]:
    body = _canonical_bytes(value)
    return body, _write_create_once(path, body, label=label)


def _replace_head(root: Path, value: Mapping[str, Any]) -> None:
    body = _canonical_bytes(value)
    if not body or len(body) > _MAX_HEAD_BYTES:
        raise MarketMemoryForwardStoreError("forward store head exceeds its byte bound")
    temp_path = _safe_path(root, f".HEAD.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temp_path, flags, 0o600)
        offset = 0
        while offset < len(body):
            written = os.write(descriptor, body[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
        _validate_private_file_metadata(os.fstat(descriptor), label="forward head temp")
        os.close(descriptor)
        descriptor = None
        os.replace(temp_path, _head_path(root))
        _fsync_directory(root)
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store head cannot be atomically replaced"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def _locked(root: Path, *, exclusive: bool) -> Iterator[None]:
    lock_path = _lock_path(root)
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags)
    except OSError as exc:
        raise MarketMemoryForwardStoreError(
            "forward store lock cannot be opened safely"
        ) from exc
    try:
        _validate_private_file_metadata(
            os.fstat(descriptor), label="forward store lock"
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.read(descriptor, 64) != b"forward-store-lock-v1\n":
            raise MarketMemoryForwardStoreError("forward store lock identity drifted")
        yield
    except OSError as exc:
        raise MarketMemoryForwardStoreError("forward store lock failed") from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _new_manifest() -> dict[str, Any]:
    nonce = uuid4().hex
    manifest: dict[str, Any] = {
        "schema": STORE_MANIFEST_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": "",
        "nonce": nonce,
        "record_schemas": dict(_SCHEMA_BY_KIND),
        "record_kinds": list(_KINDS),
        "limits": {
            "max_record_bytes": _MAX_RECORD_BYTES,
            "max_generation_bytes": _MAX_GENERATION_BYTES,
            "max_records": _MAX_RECORDS,
            "max_generation_depth": _MAX_GENERATION_DEPTH,
        },
        "policy": copy.deepcopy(_STORE_POLICY),
    }
    manifest["store_id"] = _content_id("mmforwardstore_", manifest, field="store_id")
    return manifest


def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(dict(value))
    if set(manifest) != _MANIFEST_FIELDS:
        raise MarketMemoryForwardStoreError("forward store manifest fields drifted")
    if manifest.get("schema") != STORE_MANIFEST_SCHEMA:
        raise MarketMemoryForwardStoreError("forward store manifest schema drifted")
    if manifest.get("profile") != STORE_PROFILE:
        raise MarketMemoryForwardStoreError("forward store profile drifted")
    if manifest.get("record_schemas") != _SCHEMA_BY_KIND:
        raise MarketMemoryForwardStoreError("forward record schemas drifted")
    if manifest.get("record_kinds") != list(_KINDS):
        raise MarketMemoryForwardStoreError("forward record namespaces drifted")
    if manifest.get("policy") != _STORE_POLICY:
        raise MarketMemoryForwardStoreError("forward store policy drifted")
    if manifest.get("limits") != {
        "max_record_bytes": _MAX_RECORD_BYTES,
        "max_generation_bytes": _MAX_GENERATION_BYTES,
        "max_records": _MAX_RECORDS,
        "max_generation_depth": _MAX_GENERATION_DEPTH,
    }:
        raise MarketMemoryForwardStoreError("forward store limits drifted")
    nonce = manifest.get("nonce")
    if type(nonce) is not str or not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise MarketMemoryForwardStoreError("forward store nonce is malformed")
    store_id = manifest.get("store_id")
    if type(store_id) is not str or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryForwardStoreError("forward store id is malformed")
    if store_id != _content_id("mmforwardstore_", manifest, field="store_id"):
        raise MarketMemoryForwardStoreError("forward store id is not content-bound")
    return manifest


def _counts(entries: list[Mapping[str, Any]]) -> dict[str, int]:
    result = dict(_EMPTY_COUNTS)
    for entry in entries:
        kind = _require_kind(entry.get("kind"))
        result[kind] += 1
    return result


def _replay_digest_from_entries(entries: list[Mapping[str, Any]]) -> str:
    replay = [
        {
            "kind": entry["kind"],
            "record_id": entry["record_id"],
            "semantic_key": entry["semantic_key"],
            "sha256": entry["sha256"],
            "outcome_event_id": entry["outcome_event_id"],
            "revision_number": entry["revision_number"],
            "revision_of": entry["revision_of"],
        }
        for entry in entries
    ]
    return _digest(_canonical_bytes(replay))


def _new_generation(
    *,
    store_id: str,
    previous_generation_id: str | None,
    depth: int,
    entries: list[Mapping[str, Any]],
) -> dict[str, Any]:
    generation: dict[str, Any] = {
        "schema": STORE_GENERATION_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": store_id,
        "generation_id": "",
        "previous_generation_id": previous_generation_id,
        "depth": depth,
        "entries": copy.deepcopy(entries),
        "counts": _counts(entries),
        "replay_digest": _replay_digest_from_entries(entries),
    }
    generation["generation_id"] = _content_id(
        "mmforwardgeneration_", generation, field="generation_id"
    )
    return generation


def _validate_entry(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MarketMemoryForwardStoreError("forward generation entry is not an object")
    entry = copy.deepcopy(dict(value))
    if set(entry) != _ENTRY_FIELDS:
        raise MarketMemoryForwardStoreError("forward generation entry fields drifted")
    kind = _require_kind(entry.get("kind"))
    record_id = entry.get("record_id")
    if type(record_id) is not str or not _ID_PATTERN_BY_KIND[kind].fullmatch(record_id):
        raise MarketMemoryForwardStoreError("forward generation record id is malformed")
    _require_string(entry.get("semantic_key"), field="entry semantic_key")
    _require_digest(entry.get("sha256"), field="entry sha256")
    _require_exact_int(
        entry.get("bytes"), field="entry bytes", minimum=1, maximum=_MAX_RECORD_BYTES
    )
    expected_key = Path(
        "objects", kind, record_id[-64:-62], f"{record_id}.json"
    ).as_posix()
    if entry.get("object_key") != expected_key:
        raise MarketMemoryForwardStoreError("forward generation object key drifted")
    if kind == "outcome":
        if entry.get("outcome_event_id") != entry.get("semantic_key"):
            raise MarketMemoryForwardStoreError(
                "forward outcome event identity drifted"
            )
        _require_exact_int(
            entry.get("revision_number"),
            field="outcome revision_number",
            minimum=1,
            maximum=_MAX_RECORDS,
        )
        revision_of = entry.get("revision_of")
        if revision_of is not None and (
            type(revision_of) is not str
            or not _ID_PATTERN_BY_KIND["outcome"].fullmatch(revision_of)
        ):
            raise MarketMemoryForwardStoreError(
                "forward outcome revision predecessor is malformed"
            )
    elif any(
        entry.get(field) is not None
        for field in ("outcome_event_id", "revision_number", "revision_of")
    ):
        raise MarketMemoryForwardStoreError(
            "non-outcome generation entry carries outcome revision fields"
        )
    return entry


def _validate_generation(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    generation = copy.deepcopy(dict(value))
    if set(generation) != _GENERATION_FIELDS:
        raise MarketMemoryForwardStoreError("forward generation fields drifted")
    if generation.get("schema") != STORE_GENERATION_SCHEMA:
        raise MarketMemoryForwardStoreError("forward generation schema drifted")
    if generation.get("profile") != STORE_PROFILE:
        raise MarketMemoryForwardStoreError("forward generation profile drifted")
    if generation.get("store_id") != store_id:
        raise MarketMemoryForwardStoreError("forward generation store binding drifted")
    generation_id = generation.get("generation_id")
    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryForwardStoreError("forward generation id is malformed")
    previous = generation.get("previous_generation_id")
    if previous is not None and (
        type(previous) is not str or not _GENERATION_ID.fullmatch(previous)
    ):
        raise MarketMemoryForwardStoreError(
            "forward previous generation id is malformed"
        )
    depth = _require_exact_int(
        generation.get("depth"),
        field="generation depth",
        maximum=_MAX_GENERATION_DEPTH,
    )
    entries_value = generation.get("entries")
    if not isinstance(entries_value, list) or len(entries_value) > _MAX_RECORDS:
        raise MarketMemoryForwardStoreError("forward generation entries exceed bounds")
    entries = [_validate_entry(entry) for entry in entries_value]
    if depth != len(entries):
        raise MarketMemoryForwardStoreError(
            "forward generation depth does not equal append count"
        )
    if (depth == 0) != (previous is None):
        raise MarketMemoryForwardStoreError(
            "forward generation predecessor shape is inconsistent"
        )
    if generation.get("counts") != _counts(entries):
        raise MarketMemoryForwardStoreError("forward generation counts drifted")
    if generation.get("replay_digest") != _replay_digest_from_entries(entries):
        raise MarketMemoryForwardStoreError("forward generation replay digest drifted")
    generation["entries"] = entries
    if generation_id != _content_id(
        "mmforwardgeneration_", generation, field="generation_id"
    ):
        raise MarketMemoryForwardStoreError(
            "forward generation id is not content-bound"
        )
    body = _canonical_bytes(generation)
    if not body or len(body) > _MAX_GENERATION_BYTES:
        raise MarketMemoryForwardStoreError("forward generation exceeds its byte bound")
    return generation


def _new_head(generation: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    return {
        "schema": STORE_HEAD_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": _digest(body),
        "depth": generation["depth"],
        "record_count": len(generation["entries"]),
        "counts": copy.deepcopy(generation["counts"]),
        "replay_digest": generation["replay_digest"],
    }


def _validate_head(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    head = copy.deepcopy(dict(value))
    if set(head) != _HEAD_FIELDS:
        raise MarketMemoryForwardStoreError("forward store head fields drifted")
    if head.get("schema") != STORE_HEAD_SCHEMA or head.get("profile") != STORE_PROFILE:
        raise MarketMemoryForwardStoreError("forward store head schema drifted")
    if head.get("store_id") != store_id:
        raise MarketMemoryForwardStoreError("forward store head binding drifted")
    generation_id = head.get("generation_id")
    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryForwardStoreError(
            "forward store head generation is malformed"
        )
    _require_digest(head.get("generation_sha256"), field="head generation_sha256")
    depth = _require_exact_int(
        head.get("depth"), field="head depth", maximum=_MAX_GENERATION_DEPTH
    )
    count = _require_exact_int(
        head.get("record_count"), field="head record_count", maximum=_MAX_RECORDS
    )
    if count != depth:
        raise MarketMemoryForwardStoreError("forward head count and depth diverged")
    counts = head.get("counts")
    if not isinstance(counts, Mapping) or set(counts) != set(_KINDS):
        raise MarketMemoryForwardStoreError("forward head counts are malformed")
    for kind in _KINDS:
        _require_exact_int(
            counts.get(kind), field=f"head {kind} count", maximum=_MAX_RECORDS
        )
    if sum(counts.values()) != count:
        raise MarketMemoryForwardStoreError("forward head counts do not sum")
    _require_digest(head.get("replay_digest"), field="head replay_digest")
    return head


def _validate_record_entry(
    *, root: Path, entry: Mapping[str, Any]
) -> tuple[dict[str, Any], bytes]:
    kind = _require_kind(entry["kind"])
    record_id = entry["record_id"]
    path = _record_path(root, kind, record_id)
    _validate_private_directory(path.parent, label=f"forward {kind} CAS prefix")
    if entry["object_key"] != _object_key(path, root=root):
        raise MarketMemoryForwardStoreError("forward record object key is inconsistent")
    payload, body = _read_json(
        path, limit=_MAX_RECORD_BYTES, label=f"forward {kind} record"
    )
    if len(body) != entry["bytes"] or _digest(body) != entry["sha256"]:
        raise MarketMemoryForwardStoreError(
            f"forward {kind} record bytes do not match generation"
        )
    record = _validate_record(kind, payload)
    if record[_ID_FIELD_BY_KIND[kind]] != record_id:
        raise MarketMemoryForwardStoreError(
            f"forward {kind} record id does not match generation"
        )
    semantic_key = record[_SEMANTIC_FIELD_BY_KIND[kind]]
    if semantic_key != entry["semantic_key"]:
        raise MarketMemoryForwardStoreError(
            f"forward {kind} semantic key does not match generation"
        )
    if kind == "outcome" and (
        record["outcome_event_id"] != entry["outcome_event_id"]
        or record["revision_number"] != entry["revision_number"]
        or record["revision_of"] != entry["revision_of"]
    ):
        raise MarketMemoryForwardStoreError(
            "forward outcome revision metadata does not match generation"
        )
    return record, body


def _validate_semantic_history(
    entries: list[Mapping[str, Any]],
    records: Mapping[tuple[RecordKind, str], Mapping[str, Any]],
) -> None:
    immutable_keys: dict[tuple[RecordKind, str], str] = {}
    active_outcomes: dict[str, tuple[str, int]] = {}
    seen_ids: set[tuple[RecordKind, str]] = set()
    for entry in entries:
        kind = _require_kind(entry["kind"])
        record_id = entry["record_id"]
        identity = (kind, record_id)
        if identity in seen_ids:
            raise MarketMemoryForwardStoreError(
                "forward generation repeats a record identity"
            )
        seen_ids.add(identity)
        if identity not in records:
            raise MarketMemoryForwardStoreError(
                "forward generation record was not authenticated"
            )
        semantic_key = entry["semantic_key"]
        if kind != "outcome":
            semantic_identity = (kind, semantic_key)
            previous_id = immutable_keys.get(semantic_identity)
            if previous_id is not None and previous_id != record_id:
                raise MarketMemoryForwardStoreError(
                    f"forward {kind} semantic key has divergent records"
                )
            immutable_keys[semantic_identity] = record_id
            continue
        revision_number = entry["revision_number"]
        revision_of = entry["revision_of"]
        active = active_outcomes.get(semantic_key)
        previous = records.get(("outcome", active[0])) if active is not None else None
        if active is None:
            if revision_number != 1 or revision_of is not None:
                raise MarketMemoryForwardStoreError(
                    "first forward outcome revision is not 1/null"
                )
        elif revision_of != active[0] or revision_number != active[1] + 1:
            raise MarketMemoryForwardStoreError(
                "forward outcome correction does not extend the active revision"
            )
        try:
            joined = forward.validate_outcome_record_revision(
                records[identity], previous_outcome=previous
            )
        except Exception as exc:
            raise MarketMemoryForwardStoreError(
                "forward outcome revision lineage or clocks drifted"
            ) from exc
        if _canonical_bytes(joined) != _canonical_bytes(records[identity]):
            raise MarketMemoryForwardStoreError(
                "forward outcome revision validator changed canonical bytes"
            )
        active_outcomes[semantic_key] = (record_id, revision_number)


def _validate_stored_joins(
    records: Mapping[tuple[RecordKind, str], Mapping[str, Any]],
) -> None:
    """Recheck every dependency that is provable without the external W1 bytes."""

    forecasts: list[Mapping[str, Any]] = []
    for (kind, _record_id), record in records.items():
        if kind != "forecast":
            continue
        forecasts.append(record)
        trial_id = record["trial_registration_id"]
        state_id = record["state_snapshot_id"]
        trial = records.get(("trial", trial_id))
        state_record = records.get(("state", state_id))
        if trial is None or state_record is None:
            raise MarketMemoryForwardStoreError(
                "stored forward forecast has an unavailable trial or state"
            )
        if (
            record["trial_key"] != trial["trial_key"]
            or record["context_id"] != state_record["context_id"]
            or record["as_known_at"] != state_record["as_known_at"]
            or record["decision_cutoff"] != state_record["as_known_at"]
            or record["target_sha256"] != trial["target"]["target_sha256"]
            or record["outcome_definition_sha256"] != trial["outcome_definition_sha256"]
            or record["baseline_refs"] != trial["baselines"]
            or record["plan_sha256"] != _digest(_canonical_bytes(trial))
            or any(
                record[field] != trial["implementation"][field]
                for field in ("model_sha256", "code_sha256", "config_sha256")
            )
        ):
            raise MarketMemoryForwardStoreError(
                "stored forward forecast dependency binding drifted"
            )
        decision = _parse_exact_utc(
            record["decision_cutoff"], field="stored forecast decision_cutoff"
        )
        expected_start = decision + timedelta(
            seconds=trial["horizon"]["start_offset_seconds"]
        )
        expected_end = decision + timedelta(
            seconds=trial["horizon"]["end_offset_seconds"]
        )
        if (
            _parse_exact_utc(
                record["horizon_start"], field="stored forecast horizon_start"
            )
            != expected_start
            or _parse_exact_utc(
                record["horizon_end"], field="stored forecast horizon_end"
            )
            != expected_end
            or _parse_exact_utc(
                record["evaluation_at"], field="stored forecast evaluation_at"
            )
            != expected_end
            or _parse_exact_utc(
                trial["registered_at"], field="stored trial registered_at"
            )
            > decision
            or decision
            < _parse_exact_utc(
                trial["splits"]["live_forward_start"],
                field="stored trial live_forward_start",
            )
        ):
            raise MarketMemoryForwardStoreError(
                "stored forward forecast temporal join drifted"
            )
        expired = _parse_exact_utc(
            record["sealed_at"], field="stored forecast sealed_at"
        ) >= _parse_exact_utc(
            trial["expiry"]["expires_at"], field="stored trial expires_at"
        )
        if expired != (
            record["disposition"] == "abstained"
            and record["abstention_reason"] == "policy_expired"
        ):
            raise MarketMemoryForwardStoreError(
                "stored forward forecast expiry join drifted"
            )
        domain_status = {
            row["domain"]: row["status"] for row in state_record["domain_states"]
        }
        observed_count = state_record["coverage"]["n_observed_domains"]
        state_requirements = trial["state_requirements"]
        requirements_met = observed_count >= state_requirements[
            "minimum_observed_domains"
        ] and all(
            domain_status[domain] == "observed"
            for domain in state_requirements["required_observed_domains"]
        )
        if record["disposition"] == "issued" and not requirements_met:
            raise MarketMemoryForwardStoreError(
                "stored forward forecast bypassed state requirements"
            )
        if record["disposition"] == "issued":
            distribution = record["predictive_distribution"]
            spec = trial["distribution"]
            if distribution["kind"] != spec["kind"]:
                raise MarketMemoryForwardStoreError(
                    "stored forward forecast distribution kind drifted"
                )
            if (
                distribution["kind"] == "quantiles"
                and [row["level"] for row in distribution["quantiles"]]
                != spec["quantile_levels"]
            ):
                raise MarketMemoryForwardStoreError(
                    "stored forward forecast quantile grid drifted"
                )
            if (
                distribution["kind"] == "categorical"
                and [row["category"] for row in distribution["probabilities"]]
                != spec["categories"]
            ):
                raise MarketMemoryForwardStoreError(
                    "stored forward forecast category grid drifted"
                )
        elif record["abstention_reason"] not in trial["abstention"]["allowed_reasons"]:
            raise MarketMemoryForwardStoreError(
                "stored forward forecast used an unregistered abstention"
            )

    for (kind, _record_id), record in records.items():
        if kind != "outcome":
            continue
        matching = [
            forecast
            for forecast in forecasts
            if forecast["outcome_event_id"] == record["outcome_event_id"]
        ]
        if not matching:
            raise MarketMemoryForwardStoreError(
                "stored forward outcome has no forecast event"
            )
        for forecast in matching:
            trial = records.get(("trial", forecast["trial_registration_id"]))
            if trial is None:
                raise MarketMemoryForwardStoreError(
                    "stored forward outcome forecast has no trial"
                )
            try:
                joined = forward.validate_outcome_record_join(
                    record,
                    forecast_record=forecast,
                    trial_registration=trial,
                )
            except Exception as exc:
                raise MarketMemoryForwardStoreError(
                    "stored forward outcome event binding drifted"
                ) from exc
            if _canonical_bytes(joined) != _canonical_bytes(record):
                raise MarketMemoryForwardStoreError(
                    "stored outcome join validator changed canonical bytes"
                )


def _load_generation_chain(
    *, root: Path, head: Mapping[str, Any], store_id: str
) -> tuple[dict[str, Any], ...]:
    reverse_chain: list[tuple[dict[str, Any], bytes]] = []
    generation_id = head["generation_id"]
    expected_depth = head["depth"]
    visited: set[str] = set()
    while True:
        if generation_id in visited or len(reverse_chain) > _MAX_GENERATION_DEPTH:
            raise MarketMemoryForwardStoreError(
                "forward generation ancestry loops or exceeds bounds"
            )
        visited.add(generation_id)
        generation_path = _generation_path(root, generation_id)
        _validate_private_directory(
            generation_path.parent, label="forward generation CAS prefix"
        )
        payload, body = _read_json(
            generation_path,
            limit=_MAX_GENERATION_BYTES,
            label="forward generation",
        )
        generation = _validate_generation(payload, store_id=store_id)
        if generation["generation_id"] != generation_id:
            raise MarketMemoryForwardStoreError(
                "forward generation path and id diverged"
            )
        if generation["depth"] != expected_depth:
            raise MarketMemoryForwardStoreError(
                "forward generation ancestry depth drifted"
            )
        reverse_chain.append((generation, body))
        previous = generation["previous_generation_id"]
        if previous is None:
            break
        generation_id = previous
        expected_depth -= 1
    chain_with_bodies = list(reversed(reverse_chain))
    if len(chain_with_bodies) != head["depth"] + 1:
        raise MarketMemoryForwardStoreError(
            "forward generation ancestry is not contiguous"
        )
    for index, (generation, _body) in enumerate(chain_with_bodies):
        if generation["depth"] != index:
            raise MarketMemoryForwardStoreError(
                "forward generation depth sequence is not contiguous"
            )
        if index == 0:
            if generation["entries"]:
                raise MarketMemoryForwardStoreError(
                    "forward genesis generation is not empty"
                )
            continue
        previous = chain_with_bodies[index - 1][0]
        if generation["previous_generation_id"] != previous["generation_id"]:
            raise MarketMemoryForwardStoreError(
                "forward generation predecessor binding drifted"
            )
        if generation["entries"][:-1] != previous["entries"]:
            raise MarketMemoryForwardStoreError(
                "forward generation is not a cumulative one-record append"
            )
    active, active_body = chain_with_bodies[-1]
    if _digest(active_body) != head["generation_sha256"]:
        raise MarketMemoryForwardStoreError(
            "forward head generation digest does not match bytes"
        )
    if (
        active["counts"] != head["counts"]
        or len(active["entries"]) != head["record_count"]
        or active["replay_digest"] != head["replay_digest"]
    ):
        raise MarketMemoryForwardStoreError(
            "forward head and generation summaries diverged"
        )
    return tuple(generation for generation, _body in chain_with_bodies)


def _load_state_locked(root: Path) -> _LoadedState:
    _validate_private_directory(root, label="forward store root")
    for anchor in (
        _safe_path(root, "objects"),
        *(_safe_path(root, "objects", kind) for kind in _KINDS),
        _safe_path(root, "generations"),
    ):
        _validate_private_directory(anchor, label="forward store namespace")
    manifest_payload, _manifest_body = _read_json(
        _manifest_path(root), limit=_MAX_MANIFEST_BYTES, label="forward store manifest"
    )
    manifest = _validate_manifest(manifest_payload)
    head_payload, _head_body = _read_json(
        _head_path(root), limit=_MAX_HEAD_BYTES, label="forward store head"
    )
    head = _validate_head(head_payload, store_id=manifest["store_id"])
    chain = _load_generation_chain(root=root, head=head, store_id=manifest["store_id"])
    records: dict[tuple[RecordKind, str], dict[str, Any]] = {}
    for entry in chain[-1]["entries"]:
        kind = _require_kind(entry["kind"])
        record, _body = _validate_record_entry(root=root, entry=entry)
        records[(kind, entry["record_id"])] = record
    _validate_semantic_history(chain[-1]["entries"], records)
    _validate_stored_joins(records)
    return _LoadedState(
        manifest=manifest,
        head=head,
        chain=chain,
        records=records,
    )


def _ensure_layout(root: Path) -> None:
    _mkdir_private(root)
    for path in (
        _safe_path(root, "objects"),
        *(_safe_path(root, "objects", kind) for kind in _KINDS),
        _safe_path(root, "generations"),
    ):
        _mkdir_private(path)
    lock_path = _lock_path(root)
    if not lock_path.exists():
        _write_create_once(
            lock_path, b"forward-store-lock-v1\n", label="forward store lock"
        )
    else:
        _recover_published_temp_link(lock_path, label="forward store lock")
        body = _read_bytes(lock_path, limit=64, label="forward store lock")
        if body != b"forward-store-lock-v1\n":
            raise MarketMemoryForwardStoreError("forward store lock identity drifted")


def _initialize_locked(root: Path) -> _LoadedState:
    _cleanup_orphan_temps(root)
    manifest_path = _manifest_path(root)
    manifest_was_present = manifest_path.exists()
    if manifest_was_present:
        manifest_payload, _body = _read_json(
            manifest_path, limit=_MAX_MANIFEST_BYTES, label="forward store manifest"
        )
        manifest = _validate_manifest(manifest_payload)
    else:
        candidate = _new_manifest()
        _write_json_create_once(
            manifest_path, candidate, label="forward store manifest"
        )
        manifest = candidate
    head_path = _head_path(root)
    if not head_path.exists():
        genesis = _new_generation(
            store_id=manifest["store_id"],
            previous_generation_id=None,
            depth=0,
            entries=[],
        )
        expected_genesis_path = _generation_path(root, genesis["generation_id"])
        record_files = [
            path
            for kind in _KINDS
            for path in _safe_path(root, "objects", kind).glob("*/*.json")
        ]
        generation_files = list(_safe_path(root, "generations").glob("*/*.json"))
        if manifest_was_present and (
            record_files
            or any(path != expected_genesis_path for path in generation_files)
        ):
            raise MarketMemoryForwardStoreError(
                "forward store HEAD is missing with published or orphaned history"
            )
        generation_body, _created = _write_json_create_once(
            expected_genesis_path,
            genesis,
            label="forward genesis generation",
        )
        _replace_head(root, _new_head(genesis, body=generation_body))
    return _load_state_locked(root)


def initialize_forward_store(root: str | Path) -> dict[str, Any]:
    """Create or authenticate one explicit temporary private store."""

    candidate = validate_forward_store_root(root)
    _ensure_layout(candidate)
    with _locked(candidate, exclusive=True):
        state = _initialize_locked(candidate)
    return copy.deepcopy(state.manifest)


def _record_entry(
    *, root: Path, kind: RecordKind, record: Mapping[str, Any], body: bytes
) -> dict[str, Any]:
    record_id = record[_ID_FIELD_BY_KIND[kind]]
    semantic_key = record[_SEMANTIC_FIELD_BY_KIND[kind]]
    path = _record_path(root, kind, record_id)
    return {
        "kind": kind,
        "record_id": record_id,
        "semantic_key": semantic_key,
        "sha256": _digest(body),
        "bytes": len(body),
        "object_key": _object_key(path, root=root),
        "outcome_event_id": record["outcome_event_id"] if kind == "outcome" else None,
        "revision_number": record["revision_number"] if kind == "outcome" else None,
        "revision_of": record["revision_of"] if kind == "outcome" else None,
    }


def _find_entry_by_id(
    entries: list[Mapping[str, Any]], *, kind: RecordKind, record_id: str
) -> Mapping[str, Any] | None:
    return next(
        (
            entry
            for entry in entries
            if entry["kind"] == kind and entry["record_id"] == record_id
        ),
        None,
    )


def _require_dependency(
    state: _LoadedState, *, kind: RecordKind, record_id: object, field: str
) -> dict[str, Any]:
    if type(record_id) is not str or not _ID_PATTERN_BY_KIND[kind].fullmatch(record_id):
        raise MarketMemoryForwardConflictError(
            f"forward {field} does not name a valid {kind} record"
        )
    record = state.records.get((kind, record_id))
    if record is None:
        raise MarketMemoryForwardConflictError(
            f"forward {field} is not present in this generation"
        )
    return record


def _validate_dependencies(
    state: _LoadedState,
    *,
    kind: RecordKind,
    record: Mapping[str, Any],
    exact_context_bytes: bytes | None,
) -> None:
    if kind == "forecast":
        trial = _require_dependency(
            state,
            kind="trial",
            record_id=record.get("trial_registration_id"),
            field="forecast trial_registration_id",
        )
        state_record = _require_dependency(
            state,
            kind="state",
            record_id=record.get("state_snapshot_id"),
            field="forecast state_snapshot_id",
        )
        if "trial_key" in record and record["trial_key"] != trial["trial_key"]:
            raise MarketMemoryForwardConflictError(
                "forward forecast trial key does not match its registration"
            )
        if (
            "context_id" in record
            and record["context_id"] != state_record["context_id"]
        ):
            raise MarketMemoryForwardConflictError(
                "forward forecast context does not match its state snapshot"
            )
        if type(exact_context_bytes) is not bytes:
            raise MarketMemoryForwardConflictError(
                "forward forecast append requires exact W1 context bytes"
            )
        join_validator = getattr(forward, "validate_forecast_record_join", None)
        if not callable(join_validator):
            raise MarketMemoryForwardStoreError(
                "forward forecast join validator is unavailable"
            )
        try:
            joined = join_validator(
                record,
                trial_registration=trial,
                state_snapshot=state_record,
                exact_context_bytes=exact_context_bytes,
            )
        except Exception as exc:
            raise MarketMemoryForwardConflictError(
                "forward forecast does not join its trial, state, and exact context"
            ) from exc
        if _canonical_bytes(joined) != _canonical_bytes(record):
            raise MarketMemoryForwardConflictError(
                "forward forecast join validator changed canonical bytes"
            )
    if kind == "outcome":
        matching_forecasts = [
            candidate
            for (candidate_kind, _record_id), candidate in state.records.items()
            if candidate_kind == "forecast"
            and candidate.get("outcome_event_id") == record["outcome_event_id"]
        ]
        if not matching_forecasts:
            raise MarketMemoryForwardConflictError(
                "forward outcome must resolve a stored forecast event"
            )
        for forecast in matching_forecasts:
            trial = _require_dependency(
                state,
                kind="trial",
                record_id=forecast.get("trial_registration_id"),
                field="outcome forecast trial_registration_id",
            )
            try:
                joined = forward.validate_outcome_record_join(
                    record,
                    forecast_record=forecast,
                    trial_registration=trial,
                )
            except Exception as exc:
                raise MarketMemoryForwardConflictError(
                    "forward outcome does not join its forecast event and trial"
                ) from exc
            if _canonical_bytes(joined) != _canonical_bytes(record):
                raise MarketMemoryForwardConflictError(
                    "forward outcome join validator changed canonical bytes"
                )


def _validate_outcome_maturity(record: Mapping[str, Any], *, observed_now: str) -> None:
    now = _parse_exact_utc(observed_now, field="observed_now")
    ordered_fields = (
        "effective_at",
        "source_available_at",
        "known_at",
        "observed_at",
        "recorded_at",
    )
    clocks = [
        _parse_exact_utc(record.get(field), field=field) for field in ordered_fields
    ]
    if clocks != sorted(clocks):
        raise MarketMemoryForwardMaturityError(
            "forward outcome clocks are not monotone"
        )
    if now < clocks[-1]:
        raise MarketMemoryForwardMaturityError(
            "forward outcome was appended before its recorded_at clock"
        )


def _append_locked(
    *,
    root: Path,
    state: _LoadedState,
    kind: RecordKind,
    record: Mapping[str, Any],
    exact_context_bytes: bytes | None,
) -> ForwardAppendResult:
    body = _canonical_bytes(record)
    record_id = record[_ID_FIELD_BY_KIND[kind]]
    entries = state.generation["entries"]
    _validate_dependencies(
        state,
        kind=kind,
        record=record,
        exact_context_bytes=exact_context_bytes,
    )
    existing = _find_entry_by_id(entries, kind=kind, record_id=record_id)
    if existing is not None:
        stored = state.records[(kind, record_id)]
        if _canonical_bytes(stored) != body:
            raise MarketMemoryForwardConflictError(
                f"forward {kind} id already has different canonical bytes"
            )
        return ForwardAppendResult(
            appended=False,
            kind=kind,
            record_id=record_id,
            generation_id=state.generation["generation_id"],
            replay_digest=state.generation["replay_digest"],
        )

    semantic_key = record[_SEMANTIC_FIELD_BY_KIND[kind]]
    same_semantic = [
        entry
        for entry in entries
        if entry["kind"] == kind and entry["semantic_key"] == semantic_key
    ]
    if kind != "outcome" and same_semantic:
        raise MarketMemoryForwardConflictError(
            f"forward {kind} semantic key already has different canonical bytes"
        )
    if kind == "outcome":
        active = same_semantic[-1] if same_semantic else None
        if active is None:
            if record["revision_number"] != 1 or record["revision_of"] is not None:
                raise MarketMemoryForwardConflictError(
                    "first forward outcome must be revision 1 with no predecessor"
                )
        elif (
            record["revision_of"] != active["record_id"]
            or record["revision_number"] != active["revision_number"] + 1
        ):
            raise MarketMemoryForwardConflictError(
                "forward outcome correction must extend the active revision"
            )
        previous = (
            state.records[("outcome", active["record_id"])]
            if active is not None
            else None
        )
        try:
            joined = forward.validate_outcome_record_revision(
                record, previous_outcome=previous
            )
        except Exception as exc:
            raise MarketMemoryForwardConflictError(
                "forward outcome does not validly extend the active revision"
            ) from exc
        if _canonical_bytes(joined) != body:
            raise MarketMemoryForwardConflictError(
                "forward outcome revision validator changed canonical bytes"
            )
    if len(entries) >= _MAX_RECORDS:
        raise MarketMemoryForwardStoreError("forward store record bound is exhausted")
    path = _record_path(root, kind, record_id)
    _write_create_once(path, body, label=f"forward {kind} record")
    entry = _record_entry(root=root, kind=kind, record=record, body=body)
    next_entries = [*entries, entry]
    next_generation = _new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=state.generation["generation_id"],
        depth=state.generation["depth"] + 1,
        entries=next_entries,
    )
    generation_body, _created = _write_json_create_once(
        _generation_path(root, next_generation["generation_id"]),
        next_generation,
        label="forward generation",
    )
    _replace_head(root, _new_head(next_generation, body=generation_body))
    return ForwardAppendResult(
        appended=True,
        kind=kind,
        record_id=record_id,
        generation_id=next_generation["generation_id"],
        replay_digest=next_generation["replay_digest"],
    )


def _append(
    root: str | Path,
    *,
    kind: RecordKind,
    value: Mapping[str, Any],
    observed_now: str | None = None,
    exact_context_bytes: bytes | None = None,
) -> ForwardAppendResult:
    if not isinstance(value, Mapping):
        raise MarketMemoryForwardStoreError(f"forward {kind} record must be an object")
    record = _validate_record(kind, value)
    if kind == "state":
        if type(exact_context_bytes) is not bytes:
            raise MarketMemoryForwardConflictError(
                "forward state append requires exact W1 context bytes"
            )
        try:
            strongly_validated = forward.validate_state_snapshot(
                record, exact_context_bytes=exact_context_bytes
            )
        except Exception as exc:
            raise MarketMemoryForwardConflictError(
                "forward state does not bind the supplied exact W1 context bytes"
            ) from exc
        if _canonical_bytes(strongly_validated) != _canonical_bytes(record):
            raise MarketMemoryForwardConflictError(
                "forward state join validator changed canonical bytes"
            )
    elif kind not in {"forecast"} and exact_context_bytes is not None:
        raise MarketMemoryForwardStoreError(
            "exact_context_bytes are accepted only for state and forecast append"
        )
    if kind == "outcome":
        if observed_now is None:
            raise MarketMemoryForwardMaturityError(
                "forward outcome append requires explicit observed_now"
            )
        _validate_outcome_maturity(record, observed_now=observed_now)
    elif observed_now is not None:
        raise MarketMemoryForwardStoreError(
            "observed_now is accepted only for outcome append"
        )
    candidate = validate_forward_store_root(root)
    _ensure_layout(candidate)
    with _locked(candidate, exclusive=True):
        state = _initialize_locked(candidate)
        # Dependency and maturity checks run before any record or generation write.
        return _append_locked(
            root=candidate,
            state=state,
            kind=kind,
            record=record,
            exact_context_bytes=exact_context_bytes,
        )


def append_state(
    root: str | Path,
    record: Mapping[str, Any],
    *,
    exact_context_bytes: bytes,
) -> ForwardAppendResult:
    """Append one immutable state snapshot or return an exact idempotent hit."""

    return _append(
        root,
        kind="state",
        value=record,
        exact_context_bytes=exact_context_bytes,
    )


def append_trial(root: str | Path, record: Mapping[str, Any]) -> ForwardAppendResult:
    """Append one immutable trial registration or hard-conflict on trial_key."""

    return _append(root, kind="trial", value=record)


def append_forecast(
    root: str | Path,
    record: Mapping[str, Any],
    *,
    exact_context_bytes: bytes,
) -> ForwardAppendResult:
    """Append one sealed forecast or hard-conflict on forecast_key."""

    return _append(
        root,
        kind="forecast",
        value=record,
        exact_context_bytes=exact_context_bytes,
    )


def append_outcome(
    root: str | Path,
    record: Mapping[str, Any],
    *,
    observed_now: str,
) -> ForwardAppendResult:
    """Append a mature outcome revision; corrections never overwrite history."""

    return _append(
        root,
        kind="outcome",
        value=record,
        observed_now=observed_now,
    )


def load_record(
    root: str | Path, *, kind: RecordKind, record_id: str
) -> dict[str, Any]:
    """Load one exact record only when it is reachable from authenticated HEAD."""

    checked_kind = _require_kind(kind)
    if type(record_id) is not str or not _ID_PATTERN_BY_KIND[checked_kind].fullmatch(
        record_id
    ):
        raise MarketMemoryForwardStoreError("forward load record id is malformed")
    candidate = validate_forward_store_root(root)
    if not candidate.exists():
        raise MarketMemoryForwardStoreError("forward store is not initialized")
    with _locked(candidate, exclusive=False):
        state = _load_state_locked(candidate)
        record = state.records.get((checked_kind, record_id))
        if record is None:
            raise MarketMemoryForwardStoreError(
                "forward record is not reachable from the active generation"
            )
        return copy.deepcopy(record)


def load_generation(root: str | Path, generation_id: str) -> dict[str, Any]:
    """Load one exact generation from the active authenticated ancestry."""

    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryForwardStoreError("forward generation id is malformed")
    candidate = validate_forward_store_root(root)
    if not candidate.exists():
        raise MarketMemoryForwardStoreError("forward store is not initialized")
    with _locked(candidate, exclusive=False):
        state = _load_state_locked(candidate)
        for generation in state.chain:
            if generation["generation_id"] == generation_id:
                return copy.deepcopy(generation)
    raise MarketMemoryForwardStoreError(
        "forward generation is not reachable from active HEAD"
    )


def replay_digest(root: str | Path, generation_id: str) -> str:
    """Return the deterministic, store-nonce-independent digest of exact history."""

    generation = load_generation(root, generation_id)
    expected = _replay_digest_from_entries(generation["entries"])
    if generation["replay_digest"] != expected:
        raise MarketMemoryForwardStoreError("forward replay digest is inconsistent")
    return expected


__all__ = [
    "STORE_GENERATION_SCHEMA",
    "STORE_HEAD_SCHEMA",
    "STORE_MANIFEST_SCHEMA",
    "STORE_PROFILE",
    "ForwardAppendResult",
    "MarketMemoryForwardConflictError",
    "MarketMemoryForwardMaturityError",
    "MarketMemoryForwardStoreError",
    "RecordKind",
    "append_forecast",
    "append_outcome",
    "append_state",
    "append_trial",
    "initialize_forward_store",
    "load_generation",
    "load_record",
    "replay_digest",
    "validate_forward_store_root",
]
