"""Verified private object-store transport for Filing Forensics SEC sources.

The raw SEC Submissions cache and the accession archive are deliberately kept
outside git.  This module gives them a small, immutable snapshot protocol over
the repository's private Research R2 Store.  It is intentionally stricter than
the store's normal fail-open API:

* every local path and object key is validated before use;
* every uploaded object is immediately read back and hash-checked;
* a snapshot manifest is written only after every source object is verified;
* the mutable ``latest`` pointer is committed last; and
* restore validates the manifest, every object key, every hash and every local
  atomic write before reporting success.

The public site and normal render path must never import or invoke this module.
It is an explicit operator/collect-lane tool only.  The owned versioned prefix
is ``fundamental_forensics/sec-source/v1``; changing that layout is a storage
migration, not an implementation detail.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import re
import time
from typing import Any, Iterable, Mapping

from engine.research_vault.r2_store import Store, build_store

from .models import canonical_json, parse_utc, utc_text


SOURCE_SYNC_SCHEMA = "fundamental_forensics.sec_source_snapshot/v1"
SOURCE_SYNC_LATEST_SCHEMA = "fundamental_forensics.sec_source_latest/v1"
SOURCE_SYNC_PREFIX = "fundamental_forensics/sec-source/v1"
SOURCE_KINDS = ("raw", "archive")

# These are deliberately hard ceilings, not suggestions.  The operator may
# lower them for a small recovery run but cannot accidentally turn this into an
# unbounded universe archive through a CLI flag.
HARD_MAX_FILES = 50_000
HARD_MAX_FILE_BYTES = 64 * 1024 * 1024
HARD_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_PATH_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SNAPSHOT_RE = re.compile(r"^ffsecsrc_[a-f0-9]{64}$")


class SourceSyncError(RuntimeError):
    """A source snapshot cannot be safely synchronized or restored."""


@dataclass(frozen=True)
class SourceSnapshot:
    """Verified source snapshot metadata returned by sync and restore."""

    snapshot_id: str
    manifest_key: str
    snapshot_at: str
    file_count: int
    total_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "manifest_key": self.manifest_key,
            "snapshot_at": self.snapshot_at,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True)
class RestoreResult:
    """Verified restore result, including files already matching the snapshot."""

    snapshot: SourceSnapshot
    restored_files: int
    current_files: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "restored_files": self.restored_files,
            "current_files": self.current_files,
        }


def _normalized_clock(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise SourceSyncError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - signature requires a value
        raise SourceSyncError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def _validate_limits(
    *, max_files: int, max_file_bytes: int, max_total_bytes: int
) -> tuple[int, int, int]:
    values = {
        "max_files": (max_files, HARD_MAX_FILES),
        "max_file_bytes": (max_file_bytes, HARD_MAX_FILE_BYTES),
        "max_total_bytes": (max_total_bytes, HARD_MAX_TOTAL_BYTES),
    }
    for name, (value, ceiling) in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SourceSyncError(f"{name} must be a positive integer")
        if value > ceiling:
            raise SourceSyncError(f"{name} exceeds hard safety ceiling {ceiling}")
    if max_total_bytes < max_file_bytes:
        raise SourceSyncError("max_total_bytes must be at least max_file_bytes")
    return max_files, max_file_bytes, max_total_bytes


def _relative_path(value: str | PurePosixPath) -> str:
    """Return a conservative portable relative path or reject it.

    We intentionally do not accept spaces, escapes, URL syntax, or hidden path
    components.  The SEC cache layout only requires simple content-addressed
    names, JSON sidecars, and CIK/accession directories.
    """
    text = str(value)
    if not text or "\\" in text or "\x00" in text or text.startswith("/"):
        raise SourceSyncError(f"unsafe relative path: {value!r}")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(
        part in {"", ".", ".."} or not _PATH_PART_RE.fullmatch(part)
        for part in path.parts
    ):
        raise SourceSyncError(f"unsafe relative path: {value!r}")
    normalized = path.as_posix()
    if len(normalized) > 700:
        raise SourceSyncError("relative path exceeds object-key safety limit")
    return normalized


def _object_key_for_sha256(digest: str) -> str:
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise SourceSyncError("content digest must be lowercase SHA-256 hex")
    return f"{SOURCE_SYNC_PREFIX}/objects/sha256/{digest[:2]}/{digest}.bin"


def _manifest_key(snapshot_id: str) -> str:
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_RE.fullmatch(snapshot_id):
        raise SourceSyncError("invalid source snapshot id")
    return f"{SOURCE_SYNC_PREFIX}/manifests/{snapshot_id}.json"


def _latest_key() -> str:
    return f"{SOURCE_SYNC_PREFIX}/latest.json"


def _validate_key(key: str) -> str:
    """Validate an R2 key before passing it to a fail-open generic store."""
    if not isinstance(key, str) or not key.startswith(SOURCE_SYNC_PREFIX + "/"):
        raise SourceSyncError("object key is outside the owned source prefix")
    if len(key) > 1024 or "\\" in key or "\x00" in key or "?" in key or "#" in key:
        raise SourceSyncError("unsafe object key")
    _relative_path(key)
    return key


def _root_path(root: Path, *, name: str, create: bool = False) -> Path:
    candidate = Path(root)
    if candidate.is_symlink():
        raise SourceSyncError(f"{name} root cannot be a symlink")
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    if not candidate.is_dir():
        raise SourceSyncError(f"{name} root is not a directory: {candidate}")
    return candidate.resolve()


def _safe_child(root: Path, relative: str, *, create_parent: bool = False) -> Path:
    rel = _relative_path(relative)
    root = root.resolve()
    output = root.joinpath(*PurePosixPath(rel).parts)
    if create_parent:
        output.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved_parent = output.parent.resolve()
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise SourceSyncError(f"path escapes destination root: {relative!r}") from exc
    if output.exists() and output.is_symlink():
        raise SourceSyncError(f"destination file cannot be a symlink: {relative!r}")
    return output


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temp_sibling(path)
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def _content_type(relative: str) -> str:
    if relative.endswith(".json"):
        return "application/json"
    if relative.endswith(".gz"):
        return "application/gzip"
    return "application/octet-stream"


def _walk_tree(
    root: Path,
    *,
    kind: str,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> tuple[list[dict[str, Any]], int]:
    if kind not in SOURCE_KINDS:
        raise SourceSyncError(f"unsupported source tree: {kind!r}")
    checked_root = _root_path(root, name=kind)
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(checked_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise SourceSyncError(f"{kind} source tree contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SourceSyncError(f"{kind} source tree contains a non-file: {path}")
        try:
            relative = _relative_path(path.relative_to(checked_root).as_posix())
            size = path.stat().st_size
        except OSError as exc:
            raise SourceSyncError(f"cannot inspect {kind} source file: {path}") from exc
        if size < 0 or size > max_file_bytes:
            raise SourceSyncError(
                f"{kind} source file exceeds per-file limit ({size} > {max_file_bytes}): {relative}"
            )
        if len(entries) + 1 > max_files:
            raise SourceSyncError(f"{kind} source tree exceeds file limit {max_files}")
        if total_bytes + size > max_total_bytes:
            raise SourceSyncError(
                f"{kind} source tree exceeds byte limit {max_total_bytes}"
            )
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise SourceSyncError(f"cannot read {kind} source file: {relative}") from exc
        if len(content) != size:
            raise SourceSyncError(f"source file changed while being snapshotted: {relative}")
        digest = sha256(content).hexdigest()
        entries.append(
            {
                "relative_path": relative,
                "object_key": _object_key_for_sha256(digest),
                "sha256": digest,
                "byte_length": size,
                "content_type": _content_type(relative),
            }
        )
        total_bytes += size
    return entries, total_bytes


def _snapshot_body(
    *, snapshot_at: str, trees: Mapping[str, Iterable[Mapping[str, Any]]]
) -> dict[str, Any]:
    normalized_trees: list[dict[str, Any]] = []
    for kind in SOURCE_KINDS:
        raw_entries = trees.get(kind)
        if raw_entries is None:
            raise SourceSyncError(f"source snapshot missing {kind} tree")
        entries = [dict(item) for item in raw_entries]
        entries.sort(key=lambda item: str(item.get("relative_path") or ""))
        normalized_trees.append({"kind": kind, "entries": entries})
    return {
        "schema": SOURCE_SYNC_SCHEMA,
        "prefix": SOURCE_SYNC_PREFIX,
        "snapshot_at": _normalized_clock(snapshot_at, field="snapshot_at"),
        "trees": normalized_trees,
    }


def _snapshot_from_body(body: Mapping[str, Any]) -> tuple[dict[str, Any], SourceSnapshot]:
    normalized_body = _snapshot_body(
        snapshot_at=str(body.get("snapshot_at") or ""),
        trees={
            str(tree.get("kind")): tree.get("entries")
            for tree in list(body.get("trees") or [])
            if isinstance(tree, Mapping)
        },
    )
    if body.get("schema") != SOURCE_SYNC_SCHEMA or body.get("prefix") != SOURCE_SYNC_PREFIX:
        raise SourceSyncError("unsupported source snapshot manifest")
    identity = sha256(canonical_json(normalized_body).encode("utf-8")).hexdigest()
    snapshot_id = f"ffsecsrc_{identity}"
    manifest = dict(normalized_body)
    manifest["snapshot_id"] = snapshot_id
    _validate_manifest(manifest)
    entries = _manifest_entries(manifest)
    snapshot = SourceSnapshot(
        snapshot_id=snapshot_id,
        manifest_key=_manifest_key(snapshot_id),
        snapshot_at=str(manifest["snapshot_at"]),
        file_count=len(entries),
        total_bytes=sum(int(item["byte_length"]) for _, item in entries),
    )
    return manifest, snapshot


def _manifest_entries(manifest: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    trees = manifest.get("trees")
    if not isinstance(trees, list) or len(trees) != len(SOURCE_KINDS):
        raise SourceSyncError("source snapshot must contain exactly raw and archive trees")
    names: list[str] = []
    for tree in trees:
        if not isinstance(tree, Mapping):
            raise SourceSyncError("source snapshot tree must be an object")
        kind = tree.get("kind")
        if kind not in SOURCE_KINDS:
            raise SourceSyncError("source snapshot contains unknown tree kind")
        names.append(str(kind))
        entries = tree.get("entries")
        if not isinstance(entries, list):
            raise SourceSyncError("source snapshot tree entries must be an array")
        ordered: list[str] = []
        for raw in entries:
            if not isinstance(raw, Mapping):
                raise SourceSyncError("source snapshot entry must be an object")
            entry = dict(raw)
            if set(entry) != {
                "relative_path", "object_key", "sha256", "byte_length", "content_type"
            }:
                raise SourceSyncError("source snapshot entry shape is invalid")
            relative = _relative_path(str(entry["relative_path"]))
            key = _validate_key(str(entry["object_key"]))
            digest = str(entry["sha256"])
            if not _SHA256_RE.fullmatch(digest) or key != _object_key_for_sha256(digest):
                raise SourceSyncError("source snapshot object key does not bind digest")
            length = entry["byte_length"]
            if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                raise SourceSyncError("source snapshot entry has invalid byte length")
            if not isinstance(entry["content_type"], str) or not entry["content_type"]:
                raise SourceSyncError("source snapshot entry has invalid content type")
            marker = (str(kind), relative)
            if marker in seen:
                raise SourceSyncError("source snapshot contains duplicate path")
            seen.add(marker)
            ordered.append(relative)
            result.append((str(kind), entry))
        if ordered != sorted(ordered):
            raise SourceSyncError("source snapshot entries are not canonically ordered")
    if tuple(names) != SOURCE_KINDS:
        raise SourceSyncError("source snapshot tree order is not canonical")
    return result


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    required = {"schema", "prefix", "snapshot_at", "trees", "snapshot_id"}
    if set(manifest) != required:
        raise SourceSyncError("source snapshot manifest shape is invalid")
    if manifest.get("schema") != SOURCE_SYNC_SCHEMA or manifest.get("prefix") != SOURCE_SYNC_PREFIX:
        raise SourceSyncError("unsupported source snapshot manifest")
    normalized_clock = _normalized_clock(str(manifest.get("snapshot_at") or ""), field="snapshot_at")
    if manifest.get("snapshot_at") != normalized_clock:
        raise SourceSyncError("source snapshot clock is not UTC-normalized")
    snapshot_id = manifest.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_RE.fullmatch(snapshot_id):
        raise SourceSyncError("source snapshot id is invalid")
    body = dict(manifest)
    body.pop("snapshot_id")
    normalized_body = _snapshot_body(
        snapshot_at=str(body["snapshot_at"]),
        trees={
            str(tree.get("kind")): tree.get("entries")
            for tree in list(body.get("trees") or [])
            if isinstance(tree, Mapping)
        },
    )
    expected = "ffsecsrc_" + sha256(canonical_json(normalized_body).encode("utf-8")).hexdigest()
    if snapshot_id != expected or body != normalized_body:
        raise SourceSyncError("source snapshot identity or canonical body is invalid")
    _manifest_entries(manifest)


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    _validate_manifest(manifest)
    return canonical_json(dict(manifest)).encode("utf-8")


def _decode_manifest(content: bytes) -> tuple[dict[str, Any], SourceSnapshot]:
    try:
        import json

        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceSyncError("source snapshot manifest is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SourceSyncError("source snapshot manifest must be an object")
    _validate_manifest(value)
    if _manifest_bytes(value) != content:
        raise SourceSyncError("source snapshot manifest is not canonically encoded")
    entries = _manifest_entries(value)
    snapshot_id = str(value["snapshot_id"])
    return value, SourceSnapshot(
        snapshot_id=snapshot_id,
        manifest_key=_manifest_key(snapshot_id),
        snapshot_at=str(value["snapshot_at"]),
        file_count=len(entries),
        total_bytes=sum(int(item["byte_length"]) for _, item in entries),
    )


def _put_readback(store: Store, key: str, content: bytes, *, content_type: str) -> None:
    key = _validate_key(key)
    if not store.put_bytes(key, content, content_type=content_type):
        raise SourceSyncError(f"private source-store put failed for {key}")
    readback = store.get_bytes(key)
    if readback != content:
        raise SourceSyncError(f"private source-store read-back mismatch for {key}")


def _read_required(store: Store, key: str) -> bytes:
    key = _validate_key(key)
    result = store.get_bytes(key)
    if result is None:
        raise SourceSyncError(f"private source-store object unavailable: {key}")
    if not isinstance(result, bytes):  # protocol guard for custom adapters
        raise SourceSyncError(f"private source-store returned non-bytes for {key}")
    return result


def sync_source_roots(
    *,
    raw_root: Path,
    archive_root: Path,
    store: Store,
    snapshot_at: str | datetime,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> SourceSnapshot:
    """Synchronize both SEC roots into a verified immutable private snapshot.

    No remote deletion or local pruning occurs.  A failed object read-back leaves
    no new ``latest`` pointer, so consumers keep their prior complete snapshot.
    """
    limits = _validate_limits(
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    if not isinstance(store, Store):
        # ``@runtime_checkable`` verifies the explicit minimal Store protocol.
        raise SourceSyncError("source sync requires a repository Store adapter")
    raw_entries, raw_bytes = _walk_tree(
        Path(raw_root),
        kind="raw",
        max_files=limits[0],
        max_file_bytes=limits[1],
        max_total_bytes=limits[2],
    )
    remaining_files = limits[0] - len(raw_entries)
    remaining_bytes = limits[2] - raw_bytes
    if remaining_files < 0 or remaining_bytes < 0:  # defensive; _walk_tree caps itself
        raise SourceSyncError("raw source tree exhausted snapshot budget")
    archive_entries, _ = _walk_tree(
        Path(archive_root),
        kind="archive",
        max_files=remaining_files,
        max_file_bytes=limits[1],
        max_total_bytes=remaining_bytes,
    )
    all_entries = raw_entries + archive_entries
    if len(all_entries) > limits[0]:
        raise SourceSyncError("combined SEC source trees exceed file limit")
    total_bytes = sum(int(item["byte_length"]) for item in all_entries)
    if total_bytes > limits[2]:
        raise SourceSyncError("combined SEC source trees exceed byte limit")
    manifest, snapshot = _snapshot_from_body(
        _snapshot_body(
            snapshot_at=_normalized_clock(snapshot_at, field="snapshot_at"),
            trees={"raw": raw_entries, "archive": archive_entries},
        )
    )
    # Content objects are immutable and content-addressed.  We still perform a
    # PUT+GET when the object exists: the Store protocol cannot distinguish an
    # R2 transient from an object that merely happens to be listed elsewhere.
    for kind, root, entries in (
        ("raw", Path(raw_root), raw_entries),
        ("archive", Path(archive_root), archive_entries),
    ):
        checked_root = _root_path(root, name=kind)
        for entry in entries:
            path = _safe_child(checked_root, str(entry["relative_path"]))
            content = path.read_bytes()
            digest = sha256(content).hexdigest()
            if digest != entry["sha256"] or len(content) != entry["byte_length"]:
                raise SourceSyncError("source file changed after snapshot enumeration")
            _put_readback(
                store,
                str(entry["object_key"]),
                content,
                content_type=str(entry["content_type"]),
            )
    manifest_bytes = _manifest_bytes(manifest)
    _put_readback(store, snapshot.manifest_key, manifest_bytes, content_type="application/json")
    pointer = {
        "schema": SOURCE_SYNC_LATEST_SCHEMA,
        "snapshot_id": snapshot.snapshot_id,
        "manifest_key": snapshot.manifest_key,
        "snapshot_at": snapshot.snapshot_at,
    }
    pointer_bytes = canonical_json(pointer).encode("utf-8")
    _put_readback(store, _latest_key(), pointer_bytes, content_type="application/json")
    return SourceSnapshot(
        snapshot_id=snapshot.snapshot_id,
        manifest_key=snapshot.manifest_key,
        snapshot_at=snapshot.snapshot_at,
        file_count=snapshot.file_count,
        total_bytes=snapshot.total_bytes,
    )


def _decode_pointer(content: bytes) -> dict[str, Any]:
    try:
        import json

        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceSyncError("source snapshot pointer is not UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema", "snapshot_id", "manifest_key", "snapshot_at"
    }:
        raise SourceSyncError("source snapshot pointer shape is invalid")
    if value.get("schema") != SOURCE_SYNC_LATEST_SCHEMA:
        raise SourceSyncError("unsupported source snapshot pointer")
    snapshot_id = value.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_RE.fullmatch(snapshot_id):
        raise SourceSyncError("source snapshot pointer id is invalid")
    if value.get("manifest_key") != _manifest_key(snapshot_id):
        raise SourceSyncError("source snapshot pointer manifest key is invalid")
    normalized_clock = _normalized_clock(str(value.get("snapshot_at") or ""), field="snapshot_at")
    if value.get("snapshot_at") != normalized_clock:
        raise SourceSyncError("source snapshot pointer clock is invalid")
    if canonical_json(value).encode("utf-8") != content:
        raise SourceSyncError("source snapshot pointer is not canonically encoded")
    return value


def _load_snapshot(store: Store, *, snapshot_id: str | None) -> tuple[dict[str, Any], SourceSnapshot]:
    if snapshot_id is None:
        pointer = _decode_pointer(_read_required(store, _latest_key()))
        requested_key = str(pointer["manifest_key"])
        requested_id = str(pointer["snapshot_id"])
    else:
        if not _SNAPSHOT_RE.fullmatch(str(snapshot_id)):
            raise SourceSyncError("invalid requested source snapshot id")
        requested_id = str(snapshot_id)
        requested_key = _manifest_key(requested_id)
    manifest, snapshot = _decode_manifest(_read_required(store, requested_key))
    if snapshot.snapshot_id != requested_id or snapshot.manifest_key != requested_key:
        raise SourceSyncError("source snapshot does not match requested manifest identity")
    return manifest, snapshot


def restore_source_roots(
    *,
    raw_root: Path,
    archive_root: Path,
    store: Store,
    snapshot_id: str | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> RestoreResult:
    """Restore a complete verified private source snapshot without pruning local files."""
    limits = _validate_limits(
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    if not isinstance(store, Store):
        raise SourceSyncError("source restore requires a repository Store adapter")
    manifest, snapshot = _load_snapshot(store, snapshot_id=snapshot_id)
    entries = _manifest_entries(manifest)
    if len(entries) > limits[0]:
        raise SourceSyncError("source snapshot exceeds local restore file limit")
    total_bytes = 0
    roots = {
        "raw": _root_path(Path(raw_root), name="raw", create=True),
        "archive": _root_path(Path(archive_root), name="archive", create=True),
    }
    restored = 0
    current = 0
    for kind, entry in entries:
        length = int(entry["byte_length"])
        if length > limits[1] or total_bytes + length > limits[2]:
            raise SourceSyncError("source snapshot exceeds local restore byte limits")
        total_bytes += length
        key = str(entry["object_key"])
        content = _read_required(store, key)
        if len(content) != length or sha256(content).hexdigest() != entry["sha256"]:
            raise SourceSyncError(f"source snapshot object failed checksum: {key}")
        destination = _safe_child(
            roots[kind], str(entry["relative_path"]), create_parent=True
        )
        try:
            existing = destination.read_bytes() if destination.is_file() else None
        except OSError as exc:
            raise SourceSyncError(f"cannot read local restore target: {destination}") from exc
        if existing == content:
            current += 1
            continue
        _atomic_write(destination, content)
        try:
            readback = destination.read_bytes()
        except OSError as exc:
            raise SourceSyncError(f"cannot read back local restore target: {destination}") from exc
        if readback != content or sha256(readback).hexdigest() != entry["sha256"]:
            raise SourceSyncError(f"local restore read-back mismatch: {destination}")
        restored += 1
    return RestoreResult(snapshot=snapshot, restored_files=restored, current_files=current)


def build_private_source_store(*, local_dir: str | Path | None = None) -> Store:
    """Return the existing private Research R2 Store or fail before any transfer.

    ``local_dir`` selects the repository's :class:`LocalStore` for dry-runs and
    tests.  Without it, ``R2_RESEARCH_BUCKET`` and the usual private R2
    credentials must be present; no shared public data-plane fallback exists.
    """
    store = build_store(local_dir)
    if store is None:
        raise SourceSyncError(
            "private Research R2 Store unavailable; set R2_RESEARCH_BUCKET and private R2 credentials, "
            "or pass an explicit local store directory"
        )
    return store


__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_TOTAL_BYTES",
    "HARD_MAX_FILE_BYTES",
    "HARD_MAX_FILES",
    "HARD_MAX_TOTAL_BYTES",
    "RestoreResult",
    "SOURCE_SYNC_LATEST_SCHEMA",
    "SOURCE_SYNC_PREFIX",
    "SOURCE_SYNC_SCHEMA",
    "SourceSnapshot",
    "SourceSyncError",
    "build_private_source_store",
    "restore_source_roots",
    "sync_source_roots",
]
