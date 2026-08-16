"""Read-only verifier for future Mac-local W1A receipt replicas.

W1A-B, not this module, will own replication.  The reader requires a
caller-created private root, opens it through no-follow directory descriptors,
walks the complete immutable publication-descriptor chain, and authenticates
one exact historical upstream publication.  It has no write, repair,
migration, selector, publication, or authority-enabling API.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn

from engine import options_market_memory_context as context_bridge
from engine import options_market_memory_receipt_store as upstream_store


DEFAULT_STORE_ROOT = Path(
    "/Users/chriswong/.mastermind_private/options_market_memory_context_local_v1"
)
ROOT_MARKER = ".options_market_memory_context_local_root.json"
ROOT_SCHEMA = "options.market_memory_context_local_root/v1"
HEAD_SCHEMA = "options.market_memory_context_local_receipt_head/v1"
DESCRIPTOR_SCHEMA = "options.market_memory_context_local_publication_descriptor/v1"
HIGH_WATER_SCHEMA = "options.market_memory_context_local_high_water/v1"

_MAX_MARKER_BYTES = 16 * 1024
_MAX_LOCAL_HEAD_BYTES = 16 * 1024
_MAX_DESCRIPTOR_BYTES = 32 * 1024
_MAX_UPSTREAM_HEAD_BYTES = 16 * 1024
_MAX_AUDIT_BYTES = 64 * 1024
_MAX_REFERENCE_SET_BYTES = 8 * 1024 * 1024 + 16 * 1024
_MAX_PUBLICATIONS = 1_000_000

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"omctxlocal_[a-f0-9]{64}\Z")
_PUBLICATION_ID = re.compile(r"omctxpub_[a-f0-9]{64}\Z")
_AUDIT_ID = re.compile(r"omctxaudit_[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40,64}\Z")
_RFC3339_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)

AUTHORITY: Mapping[str, Any] = MappingProxyType(
    {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
        "proposal_weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_originate": False,
        "may_select_options_candidate": False,
        "may_execute": False,
        "may_write_options_episode": False,
        "may_append_outcome": False,
        "may_train_prophet": False,
    }
)


class LocalReceiptError(ValueError):
    """The local W1A receipt root or publication failed closed."""


def _fail(message: str) -> NoReturn:
    raise LocalReceiptError(message)


def _freeze(value: object) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


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
        raise LocalReceiptError("receipt object is not finite canonical JSON") from exc


def _mapping(value: object, fields: set[str], *, label: str) -> dict[str, Any]:
    thawed = _thaw(value) if isinstance(value, Mapping) else value
    if type(thawed) is not dict or set(thawed) != fields:
        _fail(f"{label} fields are not canonical")
    return copy.deepcopy(thawed)


def _digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(f"{label} SHA-256 is malformed")
    return value


def _utc(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        _fail(f"{label} is not a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LocalReceiptError(f"{label} is not a canonical UTC timestamp") from exc
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        _fail(f"{label} is not a canonical UTC timestamp")
    return parsed


def _content_key(namespace: str, digest: str) -> str:
    return f"{namespace}/{digest[:2]}/{digest}.json"


def _authority(value: object, *, label: str) -> dict[str, Any]:
    expected = dict(AUTHORITY)
    if value != expected:
        _fail(f"{label} authority changed or became non-false")
    return expected


@dataclass(frozen=True)
class RootIdentity:
    """Caller-persisted identity for one already-created private root."""

    path: str
    device: int
    inode: int
    uid: int
    gid: int
    marker_sha256: str
    store_id: str


@dataclass(frozen=True)
class VerifiedPublication:
    """One authenticated historical publication and current monotone fence."""

    root_identity: RootIdentity
    high_water: Mapping[str, Any]
    descriptor: Mapping[str, Any]
    head: Mapping[str, Any]
    audit: Mapping[str, Any]
    references: tuple[Mapping[str, Any], ...]


_AUTHENTICATED_IDS: set[int] = set()
_HEAD_MIRRORS = (
    "publication_id",
    "published_at",
    "deployed_commit",
    "audit_id",
    "audit_sha256",
    "audit_object_key",
    "reference_set_sha256",
    "reference_set_object_sha256",
    "reference_set_object_key",
    "reference_count",
    "evidence_policy",
    "authority",
)
_FILE_IDENTITY = (
    "st_dev",
    "st_ino",
    "st_nlink",
    "st_uid",
    "st_gid",
    "st_size",
    "st_mtime_ns",
)


def _file_identity(metadata: os.stat_result) -> tuple[Any, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


class _RootReader:
    def __init__(self, root: str | Path, *, expected_uid: int, expected_gid: int):
        raw = os.fspath(root)
        absolute = os.path.abspath(raw)
        if raw != absolute:
            _fail("receipt root must be a normalized absolute path")
        if type(expected_uid) is not int or type(expected_gid) is not int:
            _fail("receipt root owner must be explicit numeric uid/gid")
        self.path = absolute
        self.expected_owner = (expected_uid, expected_gid)
        self.fd = self._open_absolute_directory(absolute)
        try:
            metadata = os.fstat(self.fd)
            self._require_directory(metadata, label="receipt root")
            self.metadata = metadata
        except BaseException:
            os.close(self.fd)
            raise

    @staticmethod
    def _open_absolute_directory(path: str) -> int:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(os.path.sep, flags)
        try:
            for part in Path(path).parts[1:]:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except OSError as exc:
            os.close(descriptor)
            raise LocalReceiptError(
                "receipt root contains a symlink or unavailable directory"
            ) from exc

    def _require_directory(self, metadata: os.stat_result, *, label: str) -> None:
        if not stat.S_ISDIR(metadata.st_mode):
            _fail(f"{label} is not a directory")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            _fail(f"{label} mode is not exactly 0700")
        if (metadata.st_uid, metadata.st_gid) != self.expected_owner:
            _fail(f"{label} owner does not match the explicit caller owner")

    @staticmethod
    def _relative_parts(relative: str) -> tuple[str, ...]:
        if not isinstance(relative, str) or not relative or relative.startswith("/"):
            _fail("receipt object path is not normalized and relative")
        parts = tuple(relative.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            _fail("receipt object path is not normalized and relative")
        return parts

    def _open_relative_file(self, relative: str, *, label: str) -> int:
        parts = self._relative_parts(relative)
        directory = os.dup(self.fd)
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            for part in parts[:-1]:
                try:
                    next_directory = os.open(part, directory_flags, dir_fd=directory)
                except OSError as exc:
                    raise LocalReceiptError(
                        f"{label} has a missing or symlink-substituted directory"
                    ) from exc
                os.close(directory)
                directory = next_directory
                self._require_directory(os.fstat(directory), label=f"{label} directory")
            file_flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                return os.open(parts[-1], file_flags, dir_fd=directory)
            except OSError as exc:
                raise LocalReceiptError(
                    f"{label} is missing or symlink-substituted"
                ) from exc
        finally:
            os.close(directory)

    def _require_regular_file(self, metadata: os.stat_result, *, label: str) -> None:
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _fail(f"{label} is not a single-link regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            _fail(f"{label} mode is not exactly 0600")
        if (metadata.st_uid, metadata.st_gid) != self.expected_owner:
            _fail(f"{label} owner differs from the receipt root")

    def read_bytes(self, relative: str, *, limit: int, label: str) -> bytes:
        descriptor = self._open_relative_file(relative, label=label)
        try:
            before = os.fstat(descriptor)
            self._require_regular_file(before, label=label)
            if before.st_size > limit:
                _fail(f"{label} exceeds its byte bound")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(descriptor, min(128 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            body = b"".join(chunks)
            if len(body) > limit:
                _fail(f"{label} exceeds its byte bound")
            after = os.fstat(descriptor)
            self._require_regular_file(after, label=label)
            if any(
                getattr(before, field) != getattr(after, field)
                for field in (*_FILE_IDENTITY, "st_mode")
            ):
                _fail(f"{label} changed during verification")
            resolved = self._open_relative_file(relative, label=label)
            try:
                path_stat = os.fstat(resolved)
                self._require_regular_file(path_stat, label=label)
                if _file_identity(path_stat) != _file_identity(after):
                    _fail(f"{label} path identity changed during verification")
            finally:
                os.close(resolved)
            return body
        finally:
            os.close(descriptor)

    def read_json(
        self, relative: str, *, limit: int, label: str
    ) -> tuple[dict[str, Any], bytes]:
        body = self.read_bytes(relative, limit=limit, label=label)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalReceiptError(f"{label} is not canonical JSON") from exc
        if not isinstance(payload, dict) or _canonical_bytes(payload) != body:
            _fail(f"{label} is not canonical JSON")
        return payload, body

    def assert_root_unchanged(self) -> None:
        current = os.fstat(self.fd)
        for field in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode"):
            if getattr(current, field) != getattr(self.metadata, field):
                _fail("receipt root identity changed during verification")

    def assert_configured_path_is_this_root(self) -> None:
        self.assert_root_unchanged()
        reopened = self._open_absolute_directory(self.path)
        try:
            current = os.fstat(reopened)
            self._require_directory(current, label="receipt root")
            for field in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode"):
                if getattr(current, field) != getattr(self.metadata, field):
                    _fail("receipt root path no longer resolves to the attested directory")
        finally:
            os.close(reopened)

    def close(self) -> None:
        os.close(self.fd)


def _validate_marker(payload: object) -> dict[str, Any]:
    marker = _mapping(
        payload,
        {
            "schema",
            "store_id",
            "upstream_head_schema",
            "upstream_reference_set_schema",
            "upstream_reference_schema",
            "authority",
        },
        label="receipt root marker",
    )
    if marker["schema"] != ROOT_SCHEMA:
        _fail("receipt root marker schema drift")
    if not isinstance(marker["store_id"], str) or not _STORE_ID.fullmatch(
        marker["store_id"]
    ):
        _fail("receipt root marker store_id is malformed")
    if marker["upstream_head_schema"] != upstream_store.HEAD_SCHEMA:
        _fail("receipt root marker upstream HEAD schema drift")
    if marker["upstream_reference_set_schema"] != upstream_store.REFERENCE_SET_SCHEMA:
        _fail("receipt root marker upstream reference-set schema drift")
    if marker["upstream_reference_schema"] != context_bridge.REFERENCE_SCHEMA:
        _fail("receipt root marker upstream reference schema drift")
    marker["authority"] = _authority(marker["authority"], label="receipt root marker")
    return marker


def _open_and_attest(
    root: str | Path, *, expected_uid: int, expected_gid: int
) -> tuple[_RootReader, RootIdentity, bytes]:
    reader = _RootReader(root, expected_uid=expected_uid, expected_gid=expected_gid)
    try:
        marker, marker_body = reader.read_json(
            ROOT_MARKER, limit=_MAX_MARKER_BYTES, label="receipt root marker"
        )
        clean = _validate_marker(marker)
        identity = RootIdentity(
            path=reader.path,
            device=reader.metadata.st_dev,
            inode=reader.metadata.st_ino,
            uid=reader.metadata.st_uid,
            gid=reader.metadata.st_gid,
            marker_sha256=hashlib.sha256(marker_body).hexdigest(),
            store_id=clean["store_id"],
        )
        return reader, identity, marker_body
    except BaseException:
        reader.close()
        raise


def attest_root(
    root: str | Path, *, expected_uid: int, expected_gid: int
) -> RootIdentity:
    """Attest one caller-created 0700 root with same-owner 0700/0600 children."""

    reader, identity, _marker_body = _open_and_attest(
        root, expected_uid=expected_uid, expected_gid=expected_gid
    )
    try:
        reader.assert_configured_path_is_this_root()
        return identity
    finally:
        reader.close()


def _validate_local_head(payload: object, *, store_id: str) -> dict[str, Any]:
    head = _mapping(
        payload,
        {
            "schema",
            "store_id",
            "descriptor_count",
            "current_descriptor_sha256",
            "current_descriptor_object_key",
            "current_publication_id",
            "current_published_at",
            "authority",
        },
        label="local receipt HEAD",
    )
    if head["schema"] != HEAD_SCHEMA or head["store_id"] != store_id:
        _fail("local receipt HEAD schema or store identity drift")
    count = head["descriptor_count"]
    if type(count) is not int or not 1 <= count <= _MAX_PUBLICATIONS:
        _fail("local receipt HEAD descriptor count is malformed")
    digest = _digest(
        head["current_descriptor_sha256"], label="local receipt HEAD descriptor"
    )
    if head["current_descriptor_object_key"] != _content_key("descriptors", digest):
        _fail("local receipt HEAD descriptor key is not content addressed")
    if not isinstance(head["current_publication_id"], str) or not _PUBLICATION_ID.fullmatch(
        head["current_publication_id"]
    ):
        _fail("local receipt HEAD publication identity is malformed")
    _utc(head["current_published_at"], label="local receipt HEAD published_at")
    head["authority"] = _authority(head["authority"], label="local receipt HEAD")
    return head


def _validate_descriptor(payload: object) -> dict[str, Any]:
    descriptor = _mapping(
        payload,
        {
            "schema",
            "sequence",
            "previous_descriptor_sha256",
            "publication_id",
            "published_at",
            "deployed_commit",
            "upstream_head_sha256",
            "upstream_head_object_key",
            "audit_id",
            "audit_sha256",
            "audit_object_key",
            "reference_set_sha256",
            "reference_set_object_sha256",
            "reference_set_object_key",
            "reference_count",
            "evidence_policy",
            "authority",
        },
        label="local publication descriptor",
    )
    if descriptor["schema"] != DESCRIPTOR_SCHEMA:
        _fail("local publication descriptor schema drift")
    sequence = descriptor["sequence"]
    if type(sequence) is not int or not 0 <= sequence < _MAX_PUBLICATIONS:
        _fail("local publication descriptor sequence is malformed")
    previous = descriptor["previous_descriptor_sha256"]
    if sequence == 0:
        if previous is not None:
            _fail("genesis descriptor has a predecessor")
    else:
        _digest(previous, label="previous descriptor")
    publication_id = descriptor["publication_id"]
    if not isinstance(publication_id, str) or not _PUBLICATION_ID.fullmatch(
        publication_id
    ):
        _fail("local publication descriptor publication_id is malformed")
    _utc(descriptor["published_at"], label="local descriptor published_at")
    if not isinstance(descriptor["deployed_commit"], str) or not _COMMIT.fullmatch(
        descriptor["deployed_commit"]
    ):
        _fail("local publication descriptor deployed commit is malformed")
    head_digest = _digest(
        descriptor["upstream_head_sha256"], label="upstream historical HEAD"
    )
    if descriptor["upstream_head_object_key"] != _content_key("heads", head_digest):
        _fail("historical HEAD key is not content addressed")
    if not isinstance(descriptor["audit_id"], str) or not _AUDIT_ID.fullmatch(
        descriptor["audit_id"]
    ):
        _fail("local publication descriptor audit_id is malformed")
    for field, namespace, key_field in (
        ("audit_sha256", "audits", "audit_object_key"),
        (
            "reference_set_object_sha256",
            "reference_sets",
            "reference_set_object_key",
        ),
    ):
        digest = _digest(descriptor[field], label=field)
        if descriptor[key_field] != _content_key(namespace, digest):
            _fail(f"{key_field} is not content addressed")
    _digest(descriptor["reference_set_sha256"], label="reference set")
    count = descriptor["reference_count"]
    if type(count) is not int or not 0 <= count <= 4096:
        _fail("local publication descriptor reference count is malformed")
    if descriptor["evidence_policy"] != dict(context_bridge.EVIDENCE_POLICY):
        _fail("local publication descriptor evidence policy drift")
    descriptor["authority"] = _authority(
        descriptor["authority"], label="local publication descriptor"
    )
    return descriptor


def _walk_descriptors(
    reader: _RootReader, head: Mapping[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    reverse: list[tuple[str, dict[str, Any]]] = []
    digest = str(head["current_descriptor_sha256"])
    for expected_sequence in range(head["descriptor_count"] - 1, -1, -1):
        key = _content_key("descriptors", digest)
        payload, body = reader.read_json(
            key, limit=_MAX_DESCRIPTOR_BYTES, label="publication descriptor"
        )
        if hashlib.sha256(body).hexdigest() != digest:
            _fail("publication descriptor differs from its content address")
        descriptor = _validate_descriptor(payload)
        if descriptor["sequence"] != expected_sequence:
            _fail("publication descriptor was omitted or reordered")
        reverse.append((digest, descriptor))
        previous = descriptor["previous_descriptor_sha256"]
        if expected_sequence == 0:
            if previous is not None:
                _fail("publication descriptor chain has a conflicting genesis")
        else:
            digest = str(previous)
    chain = list(reversed(reverse))
    publications: set[str] = set()
    previous_clock: datetime | None = None
    for _digest_value, descriptor in chain:
        if descriptor["publication_id"] in publications:
            _fail("publication descriptor identity was duplicated")
        publications.add(descriptor["publication_id"])
        clock = _utc(descriptor["published_at"], label="descriptor published_at")
        if previous_clock is not None and clock <= previous_clock:
            _fail("publication descriptor clock did not advance monotonically")
        previous_clock = clock
    tip_digest, tip = chain[-1]
    if (
        head["descriptor_count"] != tip["sequence"] + 1
        or head["current_descriptor_sha256"] != tip_digest
        or head["current_publication_id"] != tip["publication_id"]
        or head["current_published_at"] != tip["published_at"]
        or head["authority"] != tip["authority"]
    ):
        _fail("local receipt HEAD conflicts with its current descriptor")
    return chain


def _validate_previous_high_water(
    previous: Mapping[str, Any],
    *,
    identity: RootIdentity,
    chain: list[tuple[str, dict[str, Any]]],
) -> None:
    high_water = _mapping(
        previous,
        {
            "schema",
            "store_id",
            "root_marker_sha256",
            "descriptor_count",
            "sequence",
            "descriptor_sha256",
            "publication_id",
            "published_at",
            "upstream_head_sha256",
        },
        label="previous publication high-water",
    )
    if high_water["schema"] != HIGH_WATER_SCHEMA:
        _fail("previous publication high-water schema drift")
    if (
        high_water["store_id"] != identity.store_id
        or high_water["root_marker_sha256"] != identity.marker_sha256
    ):
        _fail("previous publication high-water belongs to another root")
    count = high_water["descriptor_count"]
    sequence = high_water["sequence"]
    if (
        type(count) is not int
        or type(sequence) is not int
        or not 1 <= count <= _MAX_PUBLICATIONS
        or not 0 <= sequence < _MAX_PUBLICATIONS
        or count != sequence + 1
    ):
        _fail("previous publication high-water is malformed")
    if count > len(chain):
        _fail("local W1A publication rolled back below its high-water")
    digest, descriptor = chain[sequence]
    if (
        high_water["descriptor_sha256"] != digest
        or high_water["publication_id"] != descriptor["publication_id"]
        or high_water["published_at"] != descriptor["published_at"]
        or high_water["upstream_head_sha256"] != descriptor["upstream_head_sha256"]
    ):
        _fail("local W1A history conflicts with its publication high-water")


def _reference_set(payload: object) -> tuple[dict[str, Any], ...]:
    reference_set = _mapping(
        payload,
        {"schema", "reference_set_sha256", "reference_count", "references"},
        label="historical reference-set object",
    )
    if reference_set["schema"] != upstream_store.REFERENCE_SET_SCHEMA:
        _fail("historical reference-set schema drift")
    references = reference_set["references"]
    if not isinstance(references, list):
        _fail("historical reference-set references are malformed")
    try:
        reference_body = context_bridge.canonical_reference_set_bytes(references)
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise LocalReceiptError("historical reference-set contract failed") from exc
    digest = _digest(
        reference_set["reference_set_sha256"], label="historical reference set"
    )
    if hashlib.sha256(reference_body).hexdigest() != digest:
        _fail("historical reference-set identity differs from its references")
    if (
        type(reference_set["reference_count"]) is not int
        or reference_set["reference_count"] != len(references)
    ):
        _fail("historical reference-set count differs from its references")
    return tuple(copy.deepcopy(references))


def _bind_authenticated_objects(
    descriptor: Mapping[str, Any],
    head: Mapping[str, Any],
    audit: Mapping[str, Any],
    references: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    clean_descriptor = _validate_descriptor(descriptor)
    try:
        clean_head = upstream_store.validate_head(_thaw(head))
    except upstream_store.OptionsMarketMemoryReceiptStoreError as exc:
        raise LocalReceiptError("historical upstream HEAD is malformed") from exc
    if any(clean_descriptor[field] != clean_head[field] for field in _HEAD_MIRRORS):
        _fail("publication descriptor conflicts with historical upstream HEAD")
    thawed_references = _thaw(list(references))
    if type(thawed_references) is not list:
        _fail("historical reference-set references are malformed")
    try:
        reference_body = context_bridge.canonical_reference_set_bytes(thawed_references)
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise LocalReceiptError("historical reference-set contract failed") from exc
    if hashlib.sha256(reference_body).hexdigest() != clean_descriptor["reference_set_sha256"]:
        _fail("historical reference-set identity differs from its references")
    if len(thawed_references) != clean_descriptor["reference_count"]:
        _fail("historical reference-set count differs from its references")
    try:
        clean_audit = context_bridge.validate_audit_receipt(
            _thaw(audit), references=thawed_references
        )
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise LocalReceiptError("historical audit contract failed") from exc
    if (
        clean_audit["audit_id"] != clean_head["audit_id"]
        or clean_audit["audited_at"] != clean_head["published_at"]
        or clean_audit["reference_set_sha256"] != clean_head["reference_set_sha256"]
        or len(thawed_references) != clean_head["reference_count"]
    ):
        _fail("historical audit/reference objects conflict with upstream HEAD")
    _authority(clean_head["authority"], label="historical upstream HEAD")
    _authority(clean_audit["authority"], label="historical audit")
    for reference in thawed_references:
        _authority(reference["authority"], label="historical reference")
    return clean_head, clean_audit, tuple(copy.deepcopy(thawed_references))


def _authenticate_publication(
    reader: _RootReader, descriptor: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    head_payload, head_body = reader.read_json(
        descriptor["upstream_head_object_key"],
        limit=_MAX_UPSTREAM_HEAD_BYTES,
        label="historical upstream HEAD",
    )
    if hashlib.sha256(head_body).hexdigest() != descriptor["upstream_head_sha256"]:
        _fail("historical upstream HEAD was rewritten")
    reference_payload, reference_body = reader.read_json(
        descriptor["reference_set_object_key"],
        limit=_MAX_REFERENCE_SET_BYTES,
        label="historical reference-set object",
    )
    if hashlib.sha256(reference_body).hexdigest() != descriptor[
        "reference_set_object_sha256"
    ]:
        _fail("historical reference-set object was rewritten")
    references = _reference_set(reference_payload)
    audit_payload, audit_body = reader.read_json(
        descriptor["audit_object_key"],
        limit=_MAX_AUDIT_BYTES,
        label="historical audit object",
    )
    if hashlib.sha256(audit_body).hexdigest() != descriptor["audit_sha256"]:
        _fail("historical audit object was rewritten")
    return _bind_authenticated_objects(
        descriptor, head_payload, audit_payload, references
    )


def read_publication(
    root: str | Path,
    *,
    expected_root: RootIdentity,
    previous_high_water: Mapping[str, Any] | None = None,
    publication_id: str | None = None,
) -> VerifiedPublication:
    """Authenticate current continuity and read one exact historical publication."""

    if not isinstance(expected_root, RootIdentity):
        _fail("an exact caller-persisted root identity is required")
    reader, identity, marker_body = _open_and_attest(
        root, expected_uid=expected_root.uid, expected_gid=expected_root.gid
    )
    try:
        if identity != expected_root:
            _fail("receipt root was substituted")
        local_head, local_head_body = reader.read_json(
            "HEAD.json", limit=_MAX_LOCAL_HEAD_BYTES, label="local receipt HEAD"
        )
        head = _validate_local_head(local_head, store_id=identity.store_id)
        chain = _walk_descriptors(reader, head)
        if previous_high_water is not None:
            _validate_previous_high_water(
                previous_high_water, identity=identity, chain=chain
            )
        target_id = publication_id or head["current_publication_id"]
        matches = [item for item in chain if item[1]["publication_id"] == target_id]
        if len(matches) != 1:
            _fail("requested historical publication is missing or conflicting")
        _target_digest, descriptor = matches[0]
        upstream_head, audit, references = _authenticate_publication(reader, descriptor)
        tip_digest, tip = chain[-1]
        high_water = {
            "schema": HIGH_WATER_SCHEMA,
            "store_id": identity.store_id,
            "root_marker_sha256": identity.marker_sha256,
            "descriptor_count": len(chain),
            "sequence": tip["sequence"],
            "descriptor_sha256": tip_digest,
            "publication_id": tip["publication_id"],
            "published_at": tip["published_at"],
            "upstream_head_sha256": tip["upstream_head_sha256"],
        }
        if reader.read_bytes(
            ROOT_MARKER, limit=_MAX_MARKER_BYTES, label="receipt root marker"
        ) != marker_body:
            _fail("receipt root marker changed during verification")
        if reader.read_bytes(
            "HEAD.json", limit=_MAX_LOCAL_HEAD_BYTES, label="local receipt HEAD"
        ) != local_head_body:
            _fail("local receipt HEAD changed during verification")
        reader.assert_configured_path_is_this_root()
        publication = VerifiedPublication(
            root_identity=identity,
            high_water=_freeze(high_water),
            descriptor=_freeze(descriptor),
            head=_freeze(upstream_head),
            audit=_freeze(audit),
            references=_freeze(references),
        )
        ident = id(publication)
        _AUTHENTICATED_IDS.add(ident)
        weakref.finalize(publication, _AUTHENTICATED_IDS.discard, ident)
        return publication
    finally:
        reader.close()


def _require_authenticated_publication(publication: object) -> VerifiedPublication:
    if (
        type(publication) is not VerifiedPublication
        or id(publication) not in _AUTHENTICATED_IDS
    ):
        _fail("an authenticated historical publication is required")
    return publication


def read_exact_reference(
    publication: object,
    *,
    owner_schema: str,
    owner_id: str,
    requested_as_of: str,
    source_record_sha256: str,
) -> Mapping[str, Any]:
    """Return one exact owner/as-of/source-hash reference with no fallback."""

    authenticated = _require_authenticated_publication(publication)
    _head, _audit, references = _bind_authenticated_objects(
        authenticated.descriptor,
        authenticated.head,
        authenticated.audit,
        authenticated.references,
    )
    matches = [
        row
        for row in references
        if row["owner"]["schema"] == owner_schema and row["owner"]["id"] == owner_id
    ]
    if len(matches) != 1:
        _fail("exact owner reference is missing or conflicting")
    reference = matches[0]
    if (
        reference["owner"]["requested_as_of"] != requested_as_of
        or reference["query"]["as_known_at"] != requested_as_of
    ):
        _fail("exact requested-as-of binding failed")
    if reference["owner"]["record_sha256"] != source_record_sha256:
        _fail("exact owner source hash binding failed")
    return _freeze(reference)


__all__ = [
    "AUTHORITY",
    "DEFAULT_STORE_ROOT",
    "DESCRIPTOR_SCHEMA",
    "HEAD_SCHEMA",
    "HIGH_WATER_SCHEMA",
    "LocalReceiptError",
    "ROOT_MARKER",
    "ROOT_SCHEMA",
    "RootIdentity",
    "VerifiedPublication",
    "attest_root",
    "read_exact_reference",
    "read_publication",
]
