"""Durable private receipts for exact options/Market Memory coverage audits.

This store is deliberately not a context writer.  It persists the complete
set of exact requested-as-of references produced from owner ledgers and pins
the two Market Memory generations used to resolve them.  Immutable objects are
published before one atomic ``HEAD.json`` pointer, so a failed run cannot make
an incomplete receipt visible to a consumer.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, NoReturn

from engine import options_market_memory_context as context_bridge
from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_pit

REFERENCE_SET_SCHEMA = "options.market_memory_context_reference_set/v1"
HEAD_SCHEMA = "options.market_memory_context_receipt_head/v1"
PUBLICATION_PREFIX = "omctxpub_"

_MAX_REFERENCE_SET_OBJECT_BYTES = 8 * 1024 * 1024 + 16 * 1024
_MAX_AUDIT_OBJECT_BYTES = 64 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_COMMIT = re.compile(r"[a-f0-9]{40,64}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_AUDIT_ID = re.compile(r"omctxaudit_[a-f0-9]{64}\Z")
_PUBLICATION_ID = re.compile(r"omctxpub_[a-f0-9]{64}\Z")
_RFC3339_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)


class OptionsMarketMemoryReceiptStoreError(market_memory_pit.MarketMemoryStoreError):
    """A private receipt publication is unsafe, corrupt, or inconsistent."""


def _fail(message: str) -> NoReturn:
    raise OptionsMarketMemoryReceiptStoreError(message)


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
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt store value must be finite canonical JSON"
        ) from exc


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + hashlib.sha256(_canonical_bytes(core)).hexdigest()


def _utc_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        _fail(f"{label} is not a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            f"{label} is not a canonical UTC timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        _fail(f"{label} is not UTC")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        _fail(f"{label} is not a canonical UTC timestamp")
    return parsed


def _absolute_without_symlinked_ancestor(root: str | Path) -> Path:
    absolute = Path(os.path.abspath(Path(root).expanduser()))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor /= part
        try:
            metadata = os.lstat(cursor)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise OptionsMarketMemoryReceiptStoreError(
                "receipt store path cannot be inspected safely"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            _fail("receipt store path contains a symlinked ancestor")
    return absolute


def validate_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    """Return one private, non-public, non-symlinked receipt-store root."""

    absolute = _absolute_without_symlinked_ancestor(root)
    candidate = market_memory_pit.validate_store_root(
        absolute, repository_root=repository_root
    )
    if candidate != absolute:
        _fail("receipt store path changed during validation")
    return candidate


def _require_directory(path: Path, *, owner: tuple[int, int] | None = None) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt store directory is unavailable"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("receipt store directory is not a regular directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        _fail("receipt store directory mode is not 0700")
    if owner is not None and (metadata.st_uid, metadata.st_gid) != owner:
        _fail("receipt store directory ownership drifted")


def _require_file(path: Path, *, owner: tuple[int, int], label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise OptionsMarketMemoryReceiptStoreError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail(f"{label} is not a regular non-symlink")
    if metadata.st_nlink != 1:
        _fail(f"{label} is hardlinked")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail(f"{label} mode is not 0600")
    if (metadata.st_uid, metadata.st_gid) != owner:
        _fail(f"{label} ownership differs from the receipt store")


def _require_path_directories(root: Path, path: Path) -> tuple[int, int]:
    root_metadata = root.lstat()
    owner = (root_metadata.st_uid, root_metadata.st_gid)
    _require_directory(root, owner=owner)
    relatives = path.parent.relative_to(root).parts
    cursor = root
    for part in relatives:
        cursor /= part
        _require_directory(cursor, owner=owner)
    return owner


def _require_existing_path_directories(root: Path, path: Path) -> tuple[int, int]:
    root_metadata = root.lstat()
    owner = (root_metadata.st_uid, root_metadata.st_gid)
    _require_directory(root, owner=owner)
    cursor = root
    for part in path.parent.relative_to(root).parts:
        cursor /= part
        try:
            cursor.lstat()
        except FileNotFoundError:
            break
        _require_directory(cursor, owner=owner)
    return owner


def _safe_path(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts)
    cursor = root
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            _fail("receipt store contains a symlink")
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        _fail("receipt store path escaped its root")
    return candidate


def _object_path(root: Path, namespace: str, digest: str) -> Path:
    if namespace not in {"audits", "reference_sets"}:
        _fail("receipt object namespace is malformed")
    if not _SHA256.fullmatch(digest):
        _fail("receipt object SHA-256 is malformed")
    return _safe_path(root, namespace, digest[:2], f"{digest}.json")


def _read_object(
    root: Path, path: Path, *, limit: int, label: str
) -> tuple[dict[str, Any], bytes]:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt object read escaped its root"
        ) from exc
    owner = _require_path_directories(root, path)
    _require_file(path, owner=owner, label=label)
    payload, body = market_memory_pit._read_canonical_object(
        path, limit=limit, label=label
    )
    _require_file(path, owner=owner, label=label)
    return payload, body


def _write_object(
    root: Path, path: Path, body: bytes, *, label: str
) -> bool:
    _require_existing_path_directories(root, path)
    created = market_memory_pit._write_create_once(root, path, body, label=label)
    owner = _require_path_directories(root, path)
    _require_file(path, owner=owner, label=label)
    return created


@contextmanager
def _publication_lock(root: Path) -> Iterator[None]:
    path = _safe_path(root, ".publish.lock")
    if path.is_symlink():
        _fail("receipt publication lock is a symlink")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt publication lock cannot be opened safely"
        ) from exc
    try:
        owner = (root.stat().st_uid, root.stat().st_gid)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (metadata.st_uid, metadata.st_gid) != owner
        ):
            _fail("receipt publication lock metadata is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt publication lock failed"
        ) from exc
    finally:
        os.close(descriptor)


def _reference_set_object(
    references: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], bytes]:
    reference_body = context_bridge.canonical_reference_set_bytes(references)
    clean = json.loads(reference_body.decode("utf-8"))
    payload = {
        "schema": REFERENCE_SET_SCHEMA,
        "reference_set_sha256": hashlib.sha256(reference_body).hexdigest(),
        "reference_count": len(clean),
        "references": clean,
    }
    body = _canonical_bytes(payload)
    if len(body) > _MAX_REFERENCE_SET_OBJECT_BYTES:
        _fail("reference-set object exceeds its aggregate byte bound")
    return payload, body


def _validate_reference_set_object(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema",
        "reference_set_sha256",
        "reference_count",
        "references",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        _fail("reference-set object fields are not canonical")
    if value.get("schema") != REFERENCE_SET_SCHEMA:
        _fail("reference-set object schema drift")
    references = value.get("references")
    if not isinstance(references, list):
        _fail("reference-set object references must be a list")
    body = context_bridge.canonical_reference_set_bytes(references)
    digest = value.get("reference_set_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        _fail("reference-set object SHA-256 is malformed")
    if hashlib.sha256(body).hexdigest() != digest:
        _fail("reference-set object SHA-256 differs from its references")
    count = value.get("reference_count")
    if type(count) is not int or count != len(references):
        _fail("reference-set object count differs from its references")
    clean, canonical = _reference_set_object(references)
    if _canonical_bytes(value) != canonical:
        _fail("reference-set object is not canonical")
    return clean


def _head(
    *,
    deployed_commit: str,
    audit: Mapping[str, Any],
    audit_sha256: str,
    audit_object_key: str,
    reference_set: Mapping[str, Any],
    reference_set_object_sha256: str,
    reference_set_object_key: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": HEAD_SCHEMA,
        "publication_id": "",
        "deployed_commit": deployed_commit,
        "published_at": audit["audited_at"],
        "audit_id": audit["audit_id"],
        "audit_sha256": audit_sha256,
        "audit_object_key": audit_object_key,
        "reference_set_sha256": reference_set["reference_set_sha256"],
        "reference_set_object_sha256": reference_set_object_sha256,
        "reference_set_object_key": reference_set_object_key,
        "reference_count": reference_set["reference_count"],
        "evidence_policy": dict(context_bridge.EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    payload["publication_id"] = _content_id(
        PUBLICATION_PREFIX, payload, field="publication_id"
    )
    return validate_head(payload)


def _audit_basis(audit: Mapping[str, Any]) -> dict[str, Any]:
    basis = copy.deepcopy(dict(audit))
    basis.pop("audit_id", None)
    basis.pop("audited_at", None)
    return basis


def validate_head(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one complete immutable-object pointer without reading the store."""

    expected = {
        "schema",
        "publication_id",
        "deployed_commit",
        "published_at",
        "audit_id",
        "audit_sha256",
        "audit_object_key",
        "reference_set_sha256",
        "reference_set_object_sha256",
        "reference_set_object_key",
        "reference_count",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        _fail("receipt HEAD fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != HEAD_SCHEMA:
        _fail("receipt HEAD schema drift")
    publication_id = clean.get("publication_id")
    if not isinstance(publication_id, str) or not _PUBLICATION_ID.fullmatch(
        publication_id
    ):
        _fail("receipt HEAD publication_id is malformed")
    commit = clean.get("deployed_commit")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        _fail("receipt HEAD deployed commit is malformed")
    audit_id = clean.get("audit_id")
    if not isinstance(audit_id, str) or not _AUDIT_ID.fullmatch(audit_id):
        _fail("receipt HEAD audit_id is malformed")
    _utc_time(clean.get("published_at"), label="receipt HEAD published_at")
    for field in (
        "audit_sha256",
        "reference_set_sha256",
        "reference_set_object_sha256",
    ):
        digest = clean.get(field)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            _fail(f"receipt HEAD {field} is malformed")
    expected_audit_key = (
        f"audits/{clean['audit_sha256'][:2]}/{clean['audit_sha256']}.json"
    )
    expected_reference_key = (
        "reference_sets/"
        f"{clean['reference_set_object_sha256'][:2]}/"
        f"{clean['reference_set_object_sha256']}.json"
    )
    if clean.get("audit_object_key") != expected_audit_key:
        _fail("receipt HEAD audit object key is not content addressed")
    if clean.get("reference_set_object_key") != expected_reference_key:
        _fail("receipt HEAD reference-set object key is not content addressed")
    count = clean.get("reference_count")
    if type(count) is not int or not 0 <= count <= 4096:
        _fail("receipt HEAD reference count is malformed")
    if clean.get("evidence_policy") != dict(context_bridge.EVIDENCE_POLICY):
        _fail("receipt HEAD evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        _fail("receipt HEAD authority drift")
    expected_id = _content_id(
        PUBLICATION_PREFIX, clean, field="publication_id"
    )
    if expected_id != publication_id:
        _fail("receipt HEAD publication_id does not bind its content")
    if len(_canonical_bytes(clean)) > _MAX_HEAD_BYTES:
        _fail("receipt HEAD exceeds its byte bound")
    return clean


def _read_head(root: Path) -> tuple[dict[str, Any], bytes]:
    head_path = _safe_path(root, "HEAD.json")
    payload, body = _read_object(
        root, head_path, limit=_MAX_HEAD_BYTES, label="receipt HEAD"
    )
    return validate_head(payload), body


def _authenticate_publication(
    root: Path, head: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    audit_path = _safe_path(root, *str(head["audit_object_key"]).split("/"))
    audit_payload, audit_body = _read_object(
        root, audit_path, limit=_MAX_AUDIT_OBJECT_BYTES, label="receipt audit object"
    )
    if hashlib.sha256(audit_body).hexdigest() != head["audit_sha256"]:
        _fail("receipt audit object differs from HEAD")
    reference_path = _safe_path(
        root, *str(head["reference_set_object_key"]).split("/")
    )
    reference_payload, reference_body = _read_object(
        root,
        reference_path,
        limit=_MAX_REFERENCE_SET_OBJECT_BYTES,
        label="receipt reference-set object",
    )
    if hashlib.sha256(reference_body).hexdigest() != head[
        "reference_set_object_sha256"
    ]:
        _fail("receipt reference-set object differs from HEAD")
    try:
        clean_reference = _validate_reference_set_object(reference_payload)
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt reference-set object fails its frozen contract"
        ) from exc
    references = clean_reference["references"]
    try:
        clean_audit = context_bridge.validate_audit_receipt(
            audit_payload, references=references
        )
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise OptionsMarketMemoryReceiptStoreError(
            "receipt audit object fails its frozen contract"
        ) from exc
    if clean_audit["audit_id"] != head["audit_id"]:
        _fail("receipt audit identity differs from HEAD")
    if clean_audit["audited_at"] != head["published_at"]:
        _fail("receipt audit clock differs from HEAD")
    if clean_audit["reference_set_sha256"] != head["reference_set_sha256"]:
        _fail("receipt reference-set identity differs from HEAD")
    if len(references) != head["reference_count"]:
        _fail("receipt reference count differs from HEAD")
    return clean_audit, references


def publish_receipt_set(
    store_root: str | Path,
    *,
    deployed_commit: str,
    references: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Publish complete immutable receipt objects, then atomically advance HEAD."""

    if not isinstance(deployed_commit, str) or not _COMMIT.fullmatch(deployed_commit):
        _fail("deployed commit is malformed")
    reference_set, reference_body = _reference_set_object(references)
    clean_audit = context_bridge.validate_audit_receipt(
        audit, references=reference_set["references"]
    )
    audit_body = _canonical_bytes(clean_audit)
    if len(audit_body) > _MAX_AUDIT_OBJECT_BYTES:
        _fail("audit object exceeds its byte bound")
    reference_object_sha256 = hashlib.sha256(reference_body).hexdigest()
    audit_sha256 = hashlib.sha256(audit_body).hexdigest()

    root = validate_store_root(store_root, repository_root=repository_root)
    market_memory_pit._mkdir_durable(root)
    _require_directory(root)
    reference_path = _object_path(root, "reference_sets", reference_object_sha256)
    audit_path = _object_path(root, "audits", audit_sha256)
    head = _head(
        deployed_commit=deployed_commit,
        audit=clean_audit,
        audit_sha256=audit_sha256,
        audit_object_key=audit_path.relative_to(root).as_posix(),
        reference_set=reference_set,
        reference_set_object_sha256=reference_object_sha256,
        reference_set_object_key=reference_path.relative_to(root).as_posix(),
    )

    with _publication_lock(root):
        head_path = _safe_path(root, "HEAD.json")
        if head_path.exists() or head_path.is_symlink():
            previous, _previous_body = _read_head(root)
            previous_audit, _previous_references = _authenticate_publication(
                root, previous
            )
            if (
                previous["deployed_commit"] == deployed_commit
                and previous["reference_set_object_sha256"]
                == reference_object_sha256
                and _audit_basis(previous_audit) == _audit_basis(clean_audit)
            ):
                return previous
            previous_clock = _utc_time(
                previous["published_at"], label="previous receipt HEAD published_at"
            )
            next_clock = _utc_time(
                head["published_at"], label="next receipt HEAD published_at"
            )
            if next_clock < previous_clock:
                _fail("receipt publication would move its audit clock backward")
            if next_clock == previous_clock and head != previous:
                _fail("receipt publication conflicts at an existing audit clock")
        _write_object(
            root,
            reference_path,
            reference_body,
            label="immutable reference-set object",
        )
        _write_object(root, audit_path, audit_body, label="immutable audit object")
        _authenticate_publication(root, head)
        market_memory_pit._replace_head(root, head)
        published, published_body = _read_head(root)
        if published != head or published_body != _canonical_bytes(head):
            _fail("receipt HEAD differs after atomic publication")
        _authenticate_publication(root, published)
    return head


def read_current_publication(
    store_root: str | Path, *, repository_root: str | Path | None = None
) -> dict[str, Any]:
    """Read and fully authenticate the current private receipt publication."""

    root = validate_store_root(store_root, repository_root=repository_root)
    _require_directory(root)
    head, _body = _read_head(root)
    audit, references = _authenticate_publication(root, head)
    return {
        "head": head,
        "audit": audit,
        "references": references,
    }


__all__ = [
    "HEAD_SCHEMA",
    "OptionsMarketMemoryReceiptStoreError",
    "REFERENCE_SET_SCHEMA",
    "publish_receipt_set",
    "read_current_publication",
    "validate_head",
    "validate_store_root",
]
