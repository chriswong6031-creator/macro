#!/usr/bin/env python3
"""Build one durable W0b focused vendor-snapshot quote attempt.

The script is deliberately explicit: callers provide an ordered JSON array of
one to twelve W0a ``{root, profile_id, contract_id}`` identities, the exact W0a
index bytes, the exact producer completion-ledger bytes, and a local mirror from
which every indexed immutable packet key resolves. It writes a durable decision
before any provider call, then calls the existing ThetaData first-order
full-chain snapshot exactly once per unique requested root.

Publishing is optional and create-only.  When enabled, only the decision and
receipt immutable attempt keys are written to private R2; there is no current or
discovery pointer.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import options_focused_quote as focused  # noqa: E402
from lib import config  # noqa: E402


SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "options" / "options.focused_quote_attempt.v1.schema.json"
)
MAX_REMOTE_OBJECT_BYTES = 2 * 1024 * 1024
MAX_LOCAL_ARTIFACT_BYTES = 2 * 1024 * 1024
REMOTE_METADATA_FIELDS = frozenset({
    "sha256",
    "schema",
    "record-type",
    "attempt-id",
    "visibility",
    "immutable",
})


class FocusedQuoteRuntimeError(RuntimeError):
    """A durability, publication, or orchestration boundary failed."""


class AttemptPendingError(FocusedQuoteRuntimeError):
    """A durable decision exists and its recovery deadline has not elapsed."""


class LocalImmutableCollisionError(FocusedQuoteRuntimeError):
    """A local semantic attempt key already contains different bytes."""


class RemoteImmutableCollisionError(FocusedQuoteRuntimeError):
    """A private R2 semantic attempt key already contains different bytes."""


class RemotePublicationUncertainError(FocusedQuoteRuntimeError):
    """A create or coherent verification did not produce durable certainty."""


@dataclass(frozen=True)
class Artifact:
    key: str
    body: bytes
    sha256: str
    schema: str
    record_type: str
    attempt_id: str

    @classmethod
    def from_record(cls, key: str, record: Mapping[str, Any]) -> "Artifact":
        body = focused.canonical_json_bytes(record)
        return cls(
            key=key,
            body=body,
            sha256=sha256(body).hexdigest(),
            schema=str(record["schema"]),
            record_type=str(record["record_type"]),
            attempt_id=str(record["attempt_id"]),
        )


@dataclass(frozen=True)
class RemoteObject:
    body: bytes
    content_length: int
    metadata: Mapping[str, str]


@dataclass(frozen=True)
class PrivateR2Config:
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str


@dataclass(frozen=True)
class AttemptDirectory:
    root_path: Path
    attempt_path: Path
    digest: str
    root_fd: int
    directory_fd: int
    lock_fd: int
    root_identity: tuple[int, int]
    directory_identity: tuple[int, int]
    lock_identity: tuple[int, int]


_VALIDATOR: Any | None = None


def _validator() -> Any:
    global _VALIDATOR
    if _VALIDATOR is not None:
        return _VALIDATOR
    try:
        from jsonschema import Draft202012Validator, FormatChecker  # noqa: PLC0415

        schema = json.loads(SCHEMA_PATH.read_text())
        Draft202012Validator.check_schema(schema)
        _VALIDATOR = Draft202012Validator(schema, format_checker=FormatChecker())
    except Exception as exc:  # noqa: BLE001 - schema availability is a hard boundary
        raise FocusedQuoteRuntimeError(f"focused quote schema unavailable: {exc}") from exc
    return _VALIDATOR


def validate_record(record: Mapping[str, Any]) -> None:
    errors = sorted(_validator().iter_errors(record), key=lambda error: list(error.path))
    if errors:
        summary = "; ".join(error.message for error in errors[:8])
        raise FocusedQuoteRuntimeError(f"focused quote schema validation failed: {summary}")
    if record.get("record_type") == "decision":
        focused.validate_decision(record)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FocusedQuoteRuntimeError(f"cannot open directory for durability: {path}") from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise FocusedQuoteRuntimeError(f"cannot prove directory durability: {path}") from exc
    finally:
        os.close(descriptor)


def _ensure_durable_directory(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise FocusedQuoteRuntimeError(f"no existing ancestor for directory: {path}")
        cursor = parent
    if not cursor.is_dir():
        raise FocusedQuoteRuntimeError(f"directory ancestor is not a directory: {cursor}")
    if cursor.parent != cursor:
        _fsync_directory(cursor.parent)
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            if not directory.is_dir():
                raise FocusedQuoteRuntimeError(f"directory path is not a directory: {directory}")
        except OSError as exc:
            raise FocusedQuoteRuntimeError(f"cannot create durable directory: {directory}") from exc
        _fsync_directory(directory.parent)


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _require_regular_single_link(value: os.stat_result, *, label: str) -> None:
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise FocusedQuoteRuntimeError(f"{label} is a symlink, special file, or hard link")


def _require_private_directory(value: os.stat_result, *, label: str) -> None:
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o700
    ):
        raise FocusedQuoteRuntimeError(
            f"{label} must be an owner-controlled 0700 directory"
        )


def _require_private_regular(value: os.stat_result, *, label: str) -> None:
    _require_regular_single_link(value, label=label)
    if value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) != 0o600:
        raise FocusedQuoteRuntimeError(
            f"{label} must be an owner-controlled 0600 regular file"
        )


def _safe_local_name(name: str) -> str:
    if not re.fullmatch(r"(?:decision|receipt)\.json", name):
        raise FocusedQuoteRuntimeError(f"unsafe local artifact name: {name!r}")
    return name


def _stat_at(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FocusedQuoteRuntimeError(f"cannot stat confined local entry: {name}") from exc


def _artifact_exists_at(directory_fd: int, directory: Path, name: str) -> bool:
    name = _safe_local_name(name)
    value = _stat_at(directory_fd, name)
    if value is None:
        return False
    _require_private_regular(value, label=f"local artifact {directory / name}")
    return True


def _durable_read_at(directory_fd: int, directory: Path, name: str) -> bytes:
    name = _safe_local_name(name)
    named = _stat_at(directory_fd, name)
    if named is None:
        raise FocusedQuoteRuntimeError(f"local artifact is absent: {directory / name}")
    _require_private_regular(named, label=f"local artifact {directory / name}")
    if not 1 <= named.st_size <= MAX_LOCAL_ARTIFACT_BYTES:
        raise FocusedQuoteRuntimeError(f"local artifact size is unsafe: {directory / name}")
    flags = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise FocusedQuoteRuntimeError(
            f"cannot open confined local artifact: {directory / name}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        _require_private_regular(opened, label=f"local artifact {directory / name}")
        if _identity(opened) != _identity(named) or opened.st_size != named.st_size:
            raise FocusedQuoteRuntimeError(f"local artifact changed while opening: {directory / name}")
        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise FocusedQuoteRuntimeError(
                    f"local artifact ended before its stat size: {directory / name}"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise FocusedQuoteRuntimeError(
                f"local artifact exceeded its stat size: {directory / name}"
            )
        final_named = _stat_at(directory_fd, name)
        final_opened = os.fstat(descriptor)
        if (
            final_named is None
            or _identity(final_named) != _identity(opened)
            or _identity(final_opened) != _identity(opened)
            or final_opened.st_size != opened.st_size
        ):
            raise FocusedQuoteRuntimeError(f"local artifact changed while reading: {directory / name}")
        os.fsync(descriptor)
        os.fsync(directory_fd)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_immutable_at(
    directory_fd: int,
    directory: Path,
    name: str,
    body: bytes,
) -> bool:
    """Create one exact confined artifact without following or overwriting."""
    name = _safe_local_name(name)
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_LOCAL_ARTIFACT_BYTES:
        raise FocusedQuoteRuntimeError(f"local artifact body size is unsafe: {directory / name}")
    if _artifact_exists_at(directory_fd, directory, name):
        if _durable_read_at(directory_fd, directory, name) != body:
            raise LocalImmutableCollisionError(f"local immutable collision: {directory / name}")
        return False
    temporary_name = f".{name}.tmp-{os.urandom(16).hex()}"
    descriptor: int | None = None
    temporary_exists = False
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        temporary_exists = True
        view = memoryview(body)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise FocusedQuoteRuntimeError(
                    f"local immutable temp write stalled: {directory / name}"
                )
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _durable_read_at(directory_fd, directory, name) != body:
                raise LocalImmutableCollisionError(
                    f"local immutable collision: {directory / name}"
                )
            return False
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_exists = False
        os.fsync(directory_fd)
        if _durable_read_at(directory_fd, directory, name) != body:
            raise FocusedQuoteRuntimeError(
                f"local immutable verification failed: {directory / name}"
            )
        return True
    except FocusedQuoteRuntimeError:
        raise
    except OSError as exc:
        raise FocusedQuoteRuntimeError(
            f"local immutable write uncertain: {directory / name}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except OSError:
                pass


def _durable_read(path: Path) -> bytes:
    try:
        descriptor = os.open(
            path.parent,
            os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
        )
    except OSError as exc:
        raise FocusedQuoteRuntimeError(f"cannot open confined parent: {path.parent}") from exc
    try:
        return _durable_read_at(descriptor, path.parent, path.name)
    finally:
        os.close(descriptor)


def _write_immutable(path: Path, body: bytes) -> bool:
    _ensure_durable_directory(path.parent)
    try:
        descriptor = os.open(
            path.parent,
            os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
        )
    except OSError as exc:
        raise FocusedQuoteRuntimeError(f"cannot open confined parent: {path.parent}") from exc
    try:
        return _write_immutable_at(descriptor, path.parent, path.name, body)
    finally:
        os.close(descriptor)


def _verify_attempt_state(attempt: AttemptDirectory) -> None:
    try:
        named_root = os.stat(attempt.root_path, follow_symlinks=False)
    except OSError as exc:
        raise FocusedQuoteRuntimeError(
            "state root path disappeared or escaped confinement"
        ) from exc
    _require_private_directory(named_root, label="state root")
    opened_root = os.fstat(attempt.root_fd)
    _require_private_directory(opened_root, label="state root")
    if (
        _identity(named_root) != attempt.root_identity
        or _identity(opened_root) != attempt.root_identity
    ):
        raise FocusedQuoteRuntimeError("state root inode changed or escaped confinement")
    named_directory = _stat_at(attempt.root_fd, attempt.digest)
    if named_directory is not None:
        _require_private_directory(named_directory, label="attempt directory")
    opened_directory = os.fstat(attempt.directory_fd)
    _require_private_directory(opened_directory, label="attempt directory")
    if (
        named_directory is None
        or _identity(named_directory) != attempt.directory_identity
        or _identity(opened_directory) != attempt.directory_identity
    ):
        raise FocusedQuoteRuntimeError("attempt directory inode changed or escaped confinement")
    named_lock = _stat_at(attempt.directory_fd, ".attempt.lock")
    if named_lock is None:
        raise FocusedQuoteRuntimeError("per-attempt lock inode disappeared")
    _require_private_regular(named_lock, label="per-attempt lock")
    opened_lock = os.fstat(attempt.lock_fd)
    _require_private_regular(opened_lock, label="per-attempt lock")
    if (
        _identity(named_lock) != attempt.lock_identity
        or _identity(opened_lock) != attempt.lock_identity
    ):
        raise FocusedQuoteRuntimeError("per-attempt lock inode changed")


def _attempt_exists(attempt: AttemptDirectory, name: str) -> bool:
    _verify_attempt_state(attempt)
    return _artifact_exists_at(attempt.directory_fd, attempt.attempt_path, name)


def _attempt_read(attempt: AttemptDirectory, name: str) -> bytes:
    _verify_attempt_state(attempt)
    return _durable_read_at(attempt.directory_fd, attempt.attempt_path, name)


def _attempt_write(attempt: AttemptDirectory, name: str, body: bytes) -> bool:
    _verify_attempt_state(attempt)
    created = _write_immutable_at(
        attempt.directory_fd,
        attempt.attempt_path,
        name,
        body,
    )
    _verify_attempt_state(attempt)
    return created


@contextmanager
def _attempt_lock(state_root: Path, attempt_digest: str) -> Iterator[AttemptDirectory]:
    if not re.fullmatch(r"[a-f0-9]{64}", attempt_digest):
        raise FocusedQuoteRuntimeError("unsafe semantic attempt directory name")
    _ensure_durable_directory(state_root)
    root_fd: int | None = None
    directory_fd: int | None = None
    lock_fd: int | None = None
    root_locked = False
    directory_locked = False
    lock_locked = False
    attempt_path = state_root / attempt_digest
    try:
        root_fd = os.open(
            state_root,
            os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
        )
        root_stat = os.fstat(root_fd)
        _require_private_directory(root_stat, label="state root")
        try:
            named_root = os.stat(state_root, follow_symlinks=False)
        except OSError as exc:
            raise FocusedQuoteRuntimeError("cannot revalidate state root path") from exc
        _require_private_directory(named_root, label="state root")
        root_identity = _identity(root_stat)
        if _identity(named_root) != root_identity:
            raise FocusedQuoteRuntimeError("state root changed while opening")
        # Stabilize the child namespace for every compliant local contender.
        # Private R2 decision CAS remains the production exactly-once boundary
        # against wholesale replacement of the state-root pathname itself.
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        root_locked = True
        named_root = os.stat(state_root, follow_symlinks=False)
        if _identity(named_root) != root_identity:
            raise FocusedQuoteRuntimeError("state root changed while locking")
        try:
            os.mkdir(attempt_digest, 0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        except FileExistsError:
            pass
        named_directory = _stat_at(root_fd, attempt_digest)
        if named_directory is None or not stat.S_ISDIR(named_directory.st_mode):
            raise FocusedQuoteRuntimeError("attempt directory is a symlink or special file")
        _require_private_directory(named_directory, label="attempt directory")
        directory_fd = os.open(
            attempt_digest,
            os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
            dir_fd=root_fd,
        )
        opened_directory = os.fstat(directory_fd)
        _require_private_directory(opened_directory, label="attempt directory")
        directory_identity = _identity(opened_directory)
        if directory_identity != _identity(named_directory):
            raise FocusedQuoteRuntimeError("attempt directory changed while opening")
        # The directory inode is the non-replaceable serialization primitive;
        # replacing the diagnostic child lock file cannot create a second holder.
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        directory_locked = True
        named_directory = _stat_at(root_fd, attempt_digest)
        if named_directory is None or _identity(named_directory) != directory_identity:
            raise FocusedQuoteRuntimeError("attempt directory changed while locking")
        lock_fd = os.open(
            ".attempt.lock",
            os.O_RDWR | os.O_CREAT | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        lock_stat = os.fstat(lock_fd)
        _require_private_regular(lock_stat, label="per-attempt lock")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        lock_locked = True
        os.fsync(lock_fd)
        os.fsync(directory_fd)
        attempt = AttemptDirectory(
            root_path=state_root,
            attempt_path=attempt_path,
            digest=attempt_digest,
            root_fd=root_fd,
            directory_fd=directory_fd,
            lock_fd=lock_fd,
            root_identity=root_identity,
            directory_identity=directory_identity,
            lock_identity=_identity(lock_stat),
        )
        _verify_attempt_state(attempt)
        yield attempt
    except FocusedQuoteRuntimeError:
        raise
    except OSError as exc:
        raise FocusedQuoteRuntimeError(
            f"cannot establish confined per-attempt state: {attempt_path}"
        ) from exc
    finally:
        if lock_fd is not None:
            if lock_locked:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if directory_fd is not None:
            if directory_locked:
                fcntl.flock(directory_fd, fcntl.LOCK_UN)
            os.close(directory_fd)
        if root_fd is not None:
            if root_locked:
                fcntl.flock(root_fd, fcntl.LOCK_UN)
            os.close(root_fd)


def _record_from_bytes(body: bytes, *, label: str) -> dict[str, Any]:
    record = focused.strict_json_object(body)
    if focused.canonical_json_bytes(record) != body:
        raise FocusedQuoteRuntimeError(f"{label} is not canonical JSON")
    validate_record(record)
    return record


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
    return code.lower() in {"404", "nosuchkey", "notfound", "no_such_key"} or status == 404


def _is_precondition_failed(exc: Exception) -> bool:
    code, status = _error_code(exc)
    return code.lower() in {"412", "preconditionfailed"} or status == 412


def _response_body(
    response: Mapping[str, Any],
    *,
    key: str,
    expected_length: int,
) -> bytes:
    stream = response.get("Body")
    try:
        if isinstance(stream, bytes):
            body = stream
        elif hasattr(stream, "read"):
            chunks: list[bytes] = []
            remaining = expected_length
            while remaining:
                chunk = stream.read(min(64 * 1024, remaining))
                if not isinstance(chunk, bytes) or not chunk:
                    raise RemotePublicationUncertainError(
                        f"R2 object body ended before ContentLength: {key}"
                    )
                if len(chunk) > remaining:
                    raise RemotePublicationUncertainError(
                        f"R2 object body exceeded ContentLength: {key}"
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            extra = stream.read(1)
            if extra not in {b"", None}:
                raise RemotePublicationUncertainError(
                    f"R2 object body exceeded ContentLength: {key}"
                )
            body = b"".join(chunks)
        else:
            body = stream
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if not isinstance(body, bytes):
        raise RemotePublicationUncertainError(f"R2 object body is not bytes: {key}")
    if len(body) != expected_length:
        raise RemotePublicationUncertainError(f"R2 GET length/body mismatch: {key}")
    return body


def _remote_object(client: Any, bucket: str, key: str) -> RemoteObject | None:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001 - S3-compatible client boundary
        if _is_not_found(exc):
            return None
        raise RemotePublicationUncertainError(f"R2 read uncertain: {key}") from exc
    if not isinstance(response, Mapping):
        raise RemotePublicationUncertainError(f"R2 GET response malformed: {key}")
    length = response.get("ContentLength")
    metadata = response.get("Metadata")
    content_type = response.get("ContentType")
    cache_control = response.get("CacheControl")
    if (
        isinstance(length, bool)
        or not isinstance(length, int)
        or not 1 <= length <= MAX_REMOTE_OBJECT_BYTES
    ):
        close = getattr(response.get("Body"), "close", None)
        if callable(close):
            close()
        raise RemotePublicationUncertainError(f"R2 GET length is unsafe: {key}")
    if content_type != "application/json" or cache_control != "private, no-store":
        close = getattr(response.get("Body"), "close", None)
        if callable(close):
            close()
        raise RemotePublicationUncertainError(f"R2 GET privacy headers malformed: {key}")
    if (
        not isinstance(metadata, Mapping)
        or set(metadata) != REMOTE_METADATA_FIELDS
        or any(not isinstance(name, str) or not isinstance(value, str) for name, value in metadata.items())
        or not re.fullmatch(r"[a-f0-9]{64}", metadata.get("sha256", ""))
        or metadata.get("schema") != focused.SCHEMA
        or metadata.get("record-type") not in {"decision", "receipt"}
        or not re.fullmatch(
            r"attempt:focused_quote:[a-f0-9]{64}",
            metadata.get("attempt-id", ""),
        )
        or metadata.get("visibility") != "private"
        or metadata.get("immutable") != "true"
    ):
        close = getattr(response.get("Body"), "close", None)
        if callable(close):
            close()
        raise RemotePublicationUncertainError(f"R2 GET immutable metadata malformed: {key}")
    body = _response_body(response, key=key, expected_length=length)
    return RemoteObject(
        body=body,
        content_length=length,
        metadata=dict(metadata),
    )


def _remote_matches(remote: RemoteObject, artifact: Artifact) -> bool:
    return (
        remote.content_length == len(artifact.body)
        and remote.metadata.get("sha256") == artifact.sha256
        and remote.metadata.get("schema") == artifact.schema
        and remote.metadata.get("record-type") == artifact.record_type
        and remote.metadata.get("attempt-id") == artifact.attempt_id
        and remote.metadata.get("visibility") == "private"
        and remote.metadata.get("immutable") == "true"
        and sha256(remote.body).hexdigest() == artifact.sha256
        and remote.body == artifact.body
    )


def _put_remote_immutable(
    client: Any,
    bucket: str,
    artifact: Artifact,
    *,
    record: Mapping[str, Any],
) -> bool:
    existing = _remote_object(client, bucket, artifact.key)
    if existing is not None:
        if not _remote_matches(existing, artifact):
            raise RemoteImmutableCollisionError(f"remote immutable collision: {artifact.key}")
        return False
    try:
        client.put_object(
            Bucket=bucket,
            Key=artifact.key,
            Body=artifact.body,
            ContentType="application/json",
            CacheControl="private, no-store",
            Metadata={
                "sha256": artifact.sha256,
                "schema": artifact.schema,
                "record-type": artifact.record_type,
                "attempt-id": artifact.attempt_id,
                "visibility": "private",
                "immutable": "true",
            },
            IfNoneMatch="*",
        )
    except Exception as exc:  # noqa: BLE001 - conditional create boundary
        if _is_precondition_failed(exc):
            raced = _remote_object(client, bucket, artifact.key)
            if raced is not None and _remote_matches(raced, artifact):
                return False
            if raced is not None:
                raise RemoteImmutableCollisionError(
                    f"remote immutable collision after CAS race: {artifact.key}"
                ) from exc
        raise RemotePublicationUncertainError(f"remote immutable create uncertain: {artifact.key}") from exc
    verified = _remote_object(client, bucket, artifact.key)
    if verified is None or not _remote_matches(verified, artifact):
        raise RemotePublicationUncertainError(f"remote coherent verification failed: {artifact.key}")
    return True


def _publish_record(
    client: Any | None,
    bucket: str | None,
    record: Mapping[str, Any],
) -> bool | None:
    if client is None:
        return None
    if not bucket:
        raise FocusedQuoteRuntimeError("private R2 bucket is required")
    publication = record["publication"]
    key = publication[f"{record['record_type']}_key"]
    artifact = Artifact.from_record(key, record)
    return _put_remote_immutable(client, bucket, artifact, record=record)


def _load_remote_record(
    client: Any,
    bucket: str,
    key: str,
) -> dict[str, Any] | None:
    remote = _remote_object(client, bucket, key)
    if remote is None:
        return None
    if remote.metadata.get("sha256") != sha256(remote.body).hexdigest():
        raise RemotePublicationUncertainError(
            f"remote focused quote record body/digest mismatch: {key}"
        )
    try:
        record = _record_from_bytes(
            remote.body, label=f"remote focused quote record {key}"
        )
    except (focused.FocusedQuoteError, FocusedQuoteRuntimeError) as exc:
        raise RemoteImmutableCollisionError(
            f"remote focused quote key contains an invalid record: {key}"
        ) from exc
    artifact = Artifact.from_record(key, record)
    if not _remote_matches(remote, artifact):
        raise RemoteImmutableCollisionError(
            f"remote focused quote record metadata/body mismatch: {key}"
        )
    return record


def _require_matching_decision(
    record: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    if (
        record.get("record_type") != "decision"
        or not focused.decision_matches_plan(record, plan)
    ):
        raise RemoteImmutableCollisionError(
            "remote decision does not match the semantic attempt"
        )


def _publish_or_adopt_receipt(
    client: Any,
    bucket: str,
    candidate: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the global receipt or adopt a valid concurrent winner."""
    try:
        published = _publish_record(client, bucket, candidate)
    except RemoteImmutableCollisionError:
        winner = _load_remote_record(
            client, bucket, decision["publication"]["receipt_key"]
        )
        if winner is None:
            raise RemotePublicationUncertainError(
                "receipt CAS lost but winner is not coherently visible"
            )
        try:
            focused.validate_receipt(winner, decision)
        except focused.FocusedQuoteError as exc:
            raise RemoteImmutableCollisionError(
                "remote receipt winner does not bind the authoritative decision"
            ) from exc
        return winner
    if published is None:
        raise FocusedQuoteRuntimeError("R2 receipt publication returned no result")
    return dict(candidate)


def run_attempt(
    *,
    inputs: Sequence[Mapping[str, object]],
    index_key: str,
    index_bytes: bytes,
    completion_ledger_bytes: bytes,
    packet_loader: Callable[[str], bytes],
    state_root: Path,
    snapshot_greeks: Callable[..., object],
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    r2_client: Any | None = None,
    r2_bucket: str | None = None,
) -> dict[str, Any]:
    """Execute or recover one semantic attempt without ever re-polling."""
    if r2_client is not None and not r2_bucket:
        raise FocusedQuoteRuntimeError("private R2 bucket is required")
    plan = focused.prepare_attempt(
        inputs,
        index_key=index_key,
        index_bytes=index_bytes,
        completion_ledger_bytes=completion_ledger_bytes,
        packet_loader=packet_loader,
    )
    attempt_digest = str(plan["attempt_id"]).rsplit(":", 1)[1]
    attempt_dir = state_root / attempt_digest

    with _attempt_lock(state_root, attempt_digest) as attempt:
        created = False
        remote_decision_created: bool | None = None
        if _attempt_exists(attempt, "decision.json"):
            decision = _record_from_bytes(
                _attempt_read(attempt, "decision.json"),
                label="durable focused quote decision",
            )
            if not focused.decision_matches_plan(decision, plan):
                raise LocalImmutableCollisionError(
                    f"durable decision does not match semantic attempt: {attempt_dir / 'decision.json'}"
                )
            remote_decision_created = _publish_record(
                r2_client, r2_bucket, decision
            )
        else:
            if r2_client is None:
                decision = focused.build_decision(plan, decided_at=clock())
                validate_record(decision)
                created = _attempt_write(
                    attempt,
                    "decision.json",
                    focused.canonical_json_bytes(decision),
                )
                if not created:
                    raise FocusedQuoteRuntimeError(
                        "decision creation lost an unexpected local race"
                    )
            else:
                assert r2_bucket is not None
                remote_decision = _load_remote_record(
                    r2_client, r2_bucket, plan["publication"]["decision_key"]
                )
                if remote_decision is not None:
                    _require_matching_decision(remote_decision, plan)
                    decision = remote_decision
                    remote_decision_created = False
                else:
                    candidate = focused.build_decision(plan, decided_at=clock())
                    validate_record(candidate)
                    try:
                        published = _publish_record(
                            r2_client, r2_bucket, candidate
                        )
                    except RemoteImmutableCollisionError:
                        # Both hosts can coherently observe absence and then race
                        # conditional create with different durable clocks.  The
                        # loser adopts the valid semantic winner and never polls.
                        winner = _load_remote_record(
                            r2_client,
                            r2_bucket,
                            plan["publication"]["decision_key"],
                        )
                        if winner is None:
                            raise RemotePublicationUncertainError(
                                "decision CAS lost but winner is not coherently visible"
                            )
                        _require_matching_decision(winner, plan)
                        decision = winner
                        remote_decision_created = False
                    else:
                        if published is None:
                            raise FocusedQuoteRuntimeError(
                                "R2 decision publication returned no result"
                            )
                        decision = candidate
                        remote_decision_created = published
                local_created = _attempt_write(
                    attempt,
                    "decision.json",
                    focused.canonical_json_bytes(decision),
                )
                if not local_created:
                    raise FocusedQuoteRuntimeError(
                        "decision creation lost an unexpected local race"
                    )
                created = remote_decision_created is True

        # The create-only decision is coherently durable before any source
        # call.  An R2-enabled attempt resolves the global CAS winner first and
        # stores those exact bytes locally; uncertainty exits before polling.

        if _attempt_exists(attempt, "receipt.json"):
            local_receipt = _record_from_bytes(
                _attempt_read(attempt, "receipt.json"),
                label="durable focused quote receipt",
            )
            focused.validate_receipt(local_receipt, decision)
            if r2_client is None:
                return local_receipt
            assert r2_bucket is not None
            # The global private receipt is authoritative in R2 mode.  This
            # also repairs a legacy divergent local loser without letting it
            # preempt an already-valid remote winner.
            authoritative = _publish_or_adopt_receipt(
                r2_client, r2_bucket, local_receipt, decision
            )
            _verify_attempt_state(attempt)
            return authoritative

        # A globally pre-existing exact decision is already the point of no
        # return even when this machine had no local state.  Recover an exact
        # remote receipt if one exists; otherwise enter the same pending/300s
        # no-repoll path as a locally pre-existing decision.
        if r2_client is not None and remote_decision_created is False:
            assert r2_bucket is not None
            remote_receipt = _load_remote_record(
                r2_client, r2_bucket, decision["publication"]["receipt_key"]
            )
            if remote_receipt is not None:
                focused.validate_receipt(remote_receipt, decision)
                _attempt_write(
                    attempt,
                    "receipt.json",
                    focused.canonical_json_bytes(remote_receipt),
                )
                return remote_receipt
            created = False

        if not created:
            recovery_clock = clock()
            age = focused.decision_age_microseconds(decision, now=recovery_clock)
            if age < focused.RECOVERY_DEADLINE_SECONDS * 1_000_000:
                raise AttemptPendingError(
                    "durable decision exists without receipt; recovery deadline not elapsed"
                )
            receipt = focused.build_recovery_receipt(
                decision, verified_at=recovery_clock
            )
        elif decision["preflight"]["status"] == "abstain":
            receipt = focused.build_preflight_receipt(
                decision, verified_at=clock()
            )
        else:
            frames: dict[str, object] = {}
            for root in decision["preflight"]["unique_roots"]:
                _verify_attempt_state(attempt)
                try:
                    frames[root] = snapshot_greeks(root, order="first")
                except Exception:  # noqa: BLE001 - provider uncertainty is an abstention
                    frames[root] = None
                _verify_attempt_state(attempt)
            receipt = focused.build_source_receipt(
                decision, frames, verified_at=clock
            )

        validate_record(receipt)
        focused.validate_receipt(receipt, decision)
        if r2_client is not None:
            assert r2_bucket is not None
            receipt = _publish_or_adopt_receipt(
                r2_client, r2_bucket, receipt, decision
            )
            validate_record(receipt)
            focused.validate_receipt(receipt, decision)
        _attempt_write(
            attempt,
            "receipt.json",
            focused.canonical_json_bytes(receipt),
        )
        return receipt


def _stable_file(path: Path) -> bytes:
    try:
        before = path.stat()
        body = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise FocusedQuoteRuntimeError(f"source file unavailable: {path}") from exc
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or before.st_size != len(body) or not path.is_file():
        raise FocusedQuoteRuntimeError(f"source file changed while reading: {path}")
    return body


def packet_loader_from_root(root: Path) -> Callable[[str], bytes]:
    base = root.resolve(strict=True)
    if not base.is_dir():
        raise FocusedQuoteRuntimeError(f"W0a object root is not a directory: {root}")

    def load(key: str) -> bytes:
        if not isinstance(key, str) or key.startswith("/") or ".." in Path(key).parts:
            raise FocusedQuoteRuntimeError(f"unsafe W0a object key: {key!r}")
        candidate = (base / key).resolve(strict=True)
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise FocusedQuoteRuntimeError(f"W0a object key escapes mirror root: {key}") from exc
        return _stable_file(candidate)

    return load


def _private_r2_config() -> PrivateR2Config | None:
    names = {
        "endpoint": "OPTIONS_FOCUSED_QUOTE_R2_ENDPOINT",
        "access_key_id": "OPTIONS_FOCUSED_QUOTE_R2_ACCESS_KEY_ID",
        "secret_access_key": "OPTIONS_FOCUSED_QUOTE_R2_SECRET_ACCESS_KEY",
        "bucket": "OPTIONS_FOCUSED_QUOTE_R2_BUCKET",
    }
    values = {field: os.environ.get(name) for field, name in names.items()}
    present = {field for field, value in values.items() if value}
    if not present:
        return None
    if present != set(names):
        missing = ", ".join(names[field] for field in names if field not in present)
        raise FocusedQuoteRuntimeError(
            f"incomplete focused-quote private R2 configuration; missing {missing}"
        )
    return PrivateR2Config(**{field: str(value) for field, value in values.items()})


def _r2_client(settings: PrivateR2Config) -> Any:
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except ImportError as exc:
        raise FocusedQuoteRuntimeError(
            "boto3 unavailable for focused-quote private R2 publication"
        ) from exc
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
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        config=client_config,
    )


def _fixed_or_live_clock(value: str | None) -> Callable[[], datetime]:
    if not value:
        return lambda: datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise FocusedQuoteRuntimeError("--clock-at must be timezone-aware")
    normalized = parsed.astimezone(timezone.utc)
    return lambda: normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True, help="Ordered 1..12 JSON input array")
    parser.add_argument("--w0a-index", type=Path, required=True, help="Exact W0a index bytes")
    parser.add_argument(
        "--w0a-completion-ledger",
        type=Path,
        required=True,
        help="Exact W0a-B producer completion-ledger bytes for the index session",
    )
    parser.add_argument(
        "--w0a-index-key", default=focused.W0A_INDEX_KEY,
        help="Exact W0a index logical key",
    )
    parser.add_argument(
        "--w0a-object-root", type=Path, required=True,
        help="Local mirror root resolving immutable W0a object keys",
    )
    parser.add_argument(
        "--state-root", type=Path,
        default=config.data_dir() / "options_focused_quote_attempts",
        help="Private local durable attempt root",
    )
    parser.add_argument("--clock-at", help="Fixed aware clock for hermetic replay")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Use only the dedicated OPTIONS_FOCUSED_QUOTE_R2_* private plane",
    )
    parser.add_argument(
        "--execute-provider-poll",
        action="store_true",
        help="Acknowledge one provider call per unique root; requires --publish/private R2",
    )
    args = parser.parse_args(argv)

    try:
        if not args.execute_provider_poll:
            raise FocusedQuoteRuntimeError(
                "--execute-provider-poll acknowledgement is required"
            )
        if not args.publish:
            raise FocusedQuoteRuntimeError(
                "--execute-provider-poll requires --publish to the dedicated private R2 plane"
            )
        private_settings = _private_r2_config()
        if private_settings is None:
            raise FocusedQuoteRuntimeError(
                "OPTIONS_FOCUSED_QUOTE_R2_* private settings are required"
            )
        raw_inputs = focused.strict_json_value(_stable_file(args.inputs))
        if not isinstance(raw_inputs, list):
            raise focused.FocusedQuoteError("--inputs JSON root must be an array")
        client = _r2_client(private_settings)
        def provider(root: str, *, order: str) -> object:
            # Lazy by design: malformed W0a bytes and preflight abstentions fail
            # before importing the network collector, let alone calling it.
            from collectors import thetadata  # noqa: PLC0415

            return thetadata.snapshot_greeks(root, order=order)

        receipt = run_attempt(
            inputs=raw_inputs,
            index_key=args.w0a_index_key,
            index_bytes=_stable_file(args.w0a_index),
            completion_ledger_bytes=_stable_file(args.w0a_completion_ledger),
            packet_loader=packet_loader_from_root(args.w0a_object_root),
            state_root=args.state_root,
            snapshot_greeks=provider,
            clock=_fixed_or_live_clock(args.clock_at),
            r2_client=client,
            r2_bucket=private_settings.bucket,
        )
    except AttemptPendingError as exc:
        print(f"PENDING: {exc}", file=sys.stderr)
        return 3
    except (focused.FocusedQuoteError, FocusedQuoteRuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(focused.canonical_json_bytes(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
