"""Append-only Mac-local replica of one already-local receipt publication.

W1A-B copies exact canonical bytes from one authenticated upstream
``options.market_memory_context_receipt_head/v1`` publication into a
caller-owned W1A root.  It is network-dark and credential-free: it does not
SSH, HTTP, speak to GitHub/R2, obtain secrets, rebuild Market Memory, or
regenerate an audit.  The destination root must already exist with a valid
marker; this module never creates, chmod's, or repairs the reviewed
production path.

Immutable objects are create-once.  Local ``HEAD.json`` is replaced only after
those objects exist, and success requires the merged W1A-A verifier to accept
the result.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, NoReturn
from uuid import uuid4

from engine import options_market_memory_context as context_bridge
from engine import options_market_memory_local_receipts as local_receipts
from engine import options_market_memory_receipt_store as upstream_store


_NAMESPACES = ("heads", "audits", "reference_sets", "descriptors")
_MAX_HEAD_BYTES = 16 * 1024
_MAX_AUDIT_BYTES = 64 * 1024
_MAX_REFERENCE_SET_BYTES = 8 * 1024 * 1024 + 16 * 1024
_MAX_DESCRIPTOR_BYTES = 32 * 1024
_MAX_LOCAL_HEAD_BYTES = 16 * 1024
_PRODUCER_TMP = re.compile(r"\A\.(?P<final>.+)\.tmp\.\d+\.[0-9a-f]{32}\Z")

# Tests assign a fault name to inject a crash at a protocol boundary.
_FAULT: str | None = None


class LocalReplicaError(ValueError):
    """Replication of one local W1A publication failed closed."""


def _fail(message: str) -> NoReturn:
    raise LocalReplicaError(message)


def _trip(point: str) -> None:
    if _FAULT == point:
        _fail(f"injected fault: {point}")


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
        raise LocalReplicaError("replica object is not finite canonical JSON") from exc


def _content_key(namespace: str, digest: str) -> str:
    return f"{namespace}/{digest[:2]}/{digest}.json"


def _open_nofollow_file(path: Path, *, flags: int, mode: int = 0o600) -> int:
    return os.open(
        path,
        flags | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )


def _open_directory(path: Path) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise LocalReplicaError(f"cannot open directory without following links: {path}") from exc


def _fsync_dir(path: Path) -> None:
    descriptor = _open_directory(path)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_dir(path: Path, *, owner: tuple[int, int], label: str) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise LocalReplicaError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail(f"{label} is not a regular directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        _fail(f"{label} mode is not exactly 0700")
    if (metadata.st_uid, metadata.st_gid) != owner:
        _fail(f"{label} owner does not match the destination root")


def _owned_regular_file(path: Path, *, owner: tuple[int, int], label: str) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise LocalReplicaError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail(f"{label} is not a regular non-symlink")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail(f"{label} mode is not exactly 0600")
    if (metadata.st_uid, metadata.st_gid) != owner:
        _fail(f"{label} owner does not match the destination root")
    return metadata


def _require_file(path: Path, *, owner: tuple[int, int], label: str) -> os.stat_result:
    metadata = _owned_regular_file(path, owner=owner, label=label)
    if metadata.st_nlink != 1:
        _fail(f"{label} is hardlinked")
    return metadata


def _read_exact(path: Path, *, limit: int, owner: tuple[int, int], label: str) -> bytes:
    _require_file(path, owner=owner, label=label)
    descriptor = _open_nofollow_file(path, flags=os.O_RDONLY)
    try:
        before = os.fstat(descriptor)
        if before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600:
            _fail(f"{label} is not a single-link 0600 file")
        if (before.st_uid, before.st_gid) != owner:
            _fail(f"{label} owner drifted during read")
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
        after = os.fstat(descriptor)
        if (
            after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or len(body) != after.st_size
            or len(body) > limit
        ):
            _fail(f"{label} changed during the exact read")
        return body
    finally:
        os.close(descriptor)


def _load_canonical(body: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalReplicaError(f"{label} is not canonical JSON") from exc
    if not isinstance(payload, dict) or _canonical_bytes(payload) != body:
        _fail(f"{label} is not canonical JSON")
    return payload


def _source_owner(root: Path) -> tuple[int, int]:
    try:
        metadata = os.lstat(root)
    except OSError as exc:
        raise LocalReplicaError("upstream receipt root is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("upstream receipt root is not a regular directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        _fail("upstream receipt root mode is not exactly 0700")
    return (metadata.st_uid, metadata.st_gid)


def _authenticate_source(source_root: str | Path) -> dict[str, Any]:
    """Pin exact upstream HEAD bytes, then authenticate that captured publication."""

    try:
        root = upstream_store.validate_store_root(source_root)
    except upstream_store.OptionsMarketMemoryReceiptStoreError as exc:
        raise LocalReplicaError("upstream receipt root failed its store contract") from exc
    owner = _source_owner(root)
    head_body = _read_exact(
        root / "HEAD.json", limit=_MAX_HEAD_BYTES, owner=owner, label="upstream HEAD"
    )
    head_payload = _load_canonical(head_body, label="upstream HEAD")
    try:
        head = upstream_store.validate_head(head_payload)
    except upstream_store.OptionsMarketMemoryReceiptStoreError as exc:
        raise LocalReplicaError("upstream HEAD failed its receipt contract") from exc
    if _canonical_bytes(head) != head_body:
        _fail("upstream HEAD bytes are not the authenticated canonical HEAD")

    audit_rel = str(head["audit_object_key"])
    reference_rel = str(head["reference_set_object_key"])
    if not audit_rel.startswith("audits/"):
        _fail("upstream audit object key escaped its namespace")
    if not reference_rel.startswith("reference_sets/"):
        _fail("upstream reference-set object key escaped its namespace")
    audit_body = _read_exact(
        root / audit_rel,
        limit=_MAX_AUDIT_BYTES,
        owner=owner,
        label="upstream audit object",
    )
    reference_body = _read_exact(
        root / reference_rel,
        limit=_MAX_REFERENCE_SET_BYTES,
        owner=owner,
        label="upstream reference-set object",
    )
    if hashlib.sha256(audit_body).hexdigest() != head["audit_sha256"]:
        _fail("upstream audit object does not match the captured HEAD")
    if hashlib.sha256(reference_body).hexdigest() != head["reference_set_object_sha256"]:
        _fail("upstream reference-set object does not match the captured HEAD")

    audit_payload = _load_canonical(audit_body, label="upstream audit object")
    reference_payload = _load_canonical(
        reference_body, label="upstream reference-set object"
    )
    if reference_payload.get("schema") != upstream_store.REFERENCE_SET_SCHEMA:
        _fail("upstream reference-set schema drift")
    references = reference_payload.get("references")
    if not isinstance(references, list):
        _fail("upstream reference-set references are malformed")
    try:
        reference_identity = context_bridge.canonical_reference_set_bytes(references)
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise LocalReplicaError("upstream reference-set contract failed") from exc
    if hashlib.sha256(reference_identity).hexdigest() != head["reference_set_sha256"]:
        _fail("upstream reference-set identity differs from the captured HEAD")
    if (
        type(reference_payload.get("reference_count")) is not int
        or reference_payload["reference_count"] != len(references)
        or len(references) != head["reference_count"]
    ):
        _fail("upstream reference count differs from the captured HEAD")
    try:
        clean_audit = context_bridge.validate_audit_receipt(
            audit_payload, references=references
        )
    except context_bridge.OptionsMarketMemoryContextError as exc:
        raise LocalReplicaError("upstream audit contract failed") from exc
    if (
        clean_audit["audit_id"] != head["audit_id"]
        or clean_audit["audited_at"] != head["published_at"]
        or clean_audit["reference_set_sha256"] != head["reference_set_sha256"]
    ):
        _fail("upstream audit conflicts with the captured HEAD")
    if dict(head["authority"]) != dict(local_receipts.AUTHORITY):
        _fail("upstream HEAD authority is not display/context with proposal weight zero")
    return {
        "root": root,
        "head": head,
        "head_body": head_body,
        "head_sha256": hashlib.sha256(head_body).hexdigest(),
        "audit_body": audit_body,
        "reference_body": reference_body,
    }


def _ensure_descendant_dir(root: Path, relative: str, *, owner: tuple[int, int]) -> None:
    cursor = root
    for part in Path(relative).parts:
        cursor = cursor / part
        try:
            metadata = os.lstat(cursor)
        except FileNotFoundError:
            try:
                os.mkdir(cursor, 0o700)
            except FileExistsError:
                _require_dir(cursor, owner=owner, label=f"replica directory {cursor.name}")
                continue
            created = os.lstat(cursor)
            if stat.S_IMODE(created.st_mode) != 0o700:
                os.chmod(cursor, 0o700)
            _require_dir(cursor, owner=owner, label=f"replica directory {cursor.name}")
            _fsync_dir(cursor.parent)
            continue
        if stat.S_ISLNK(metadata.st_mode):
            _fail(f"replica directory {cursor.name} is a symlink")
        _require_dir(cursor, owner=owner, label=f"replica directory {cursor.name}")


def _is_producer_temp_name(final_name: str, candidate_name: str) -> bool:
    matched = _PRODUCER_TMP.fullmatch(candidate_name)
    return matched is not None and matched.group("final") == final_name


def _reclaim_stranded_producer_link(
    path: Path, *, owner: tuple[int, int], label: str
) -> None:
    """Drop this protocol's post-link temp so the final object can return to nlink 1.

    External hardlinks are not producer temps and remain fail-closed.
    """

    metadata = _owned_regular_file(path, owner=owner, label=label)
    if metadata.st_nlink == 1:
        return
    try:
        names = os.listdir(path.parent)
    except OSError as exc:
        raise LocalReplicaError(f"cannot inspect stranded producer temps for {label}") from exc
    reclaimed = False
    for name in names:
        if not _is_producer_temp_name(path.name, name):
            continue
        candidate = path.parent / name
        try:
            other = os.lstat(candidate)
        except OSError:
            continue
        if stat.S_ISLNK(other.st_mode) or not stat.S_ISREG(other.st_mode):
            continue
        if (other.st_dev, other.st_ino) != (metadata.st_dev, metadata.st_ino):
            continue
        if stat.S_IMODE(other.st_mode) != 0o600:
            continue
        if (other.st_uid, other.st_gid) != owner:
            continue
        try:
            os.unlink(candidate)
        except OSError as exc:
            raise LocalReplicaError(
                f"cannot reclaim stranded producer temp for {label}"
            ) from exc
        reclaimed = True
    if reclaimed:
        _fsync_dir(path.parent)
    _require_file(path, owner=owner, label=label)


def _create_once(
    root: Path,
    relative: str,
    body: bytes,
    *,
    owner: tuple[int, int],
    label: str,
) -> bool:
    if any(part in {"", ".", ".."} for part in relative.split("/")):
        _fail(f"{label} path is not a normalized relative object key")
    path = root.joinpath(*relative.split("/"))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise LocalReplicaError(f"{label} escaped the destination root") from exc
    _ensure_descendant_dir(root, str(Path(relative).parent), owner=owner)
    if path.exists() or path.is_symlink():
        _reclaim_stranded_producer_link(
            path, owner=owner, label=f"existing {label}"
        )
        existing = _read_exact(path, limit=len(body), owner=owner, label=f"existing {label}")
        if existing != body:
            _fail(f"immutable {label} already exists with conflicting bytes")
        return False
    temporary = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    descriptor: int | None = None
    try:
        descriptor = _open_nofollow_file(
            temporary, flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL
        )
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail(f"short write publishing {label}")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            _reclaim_stranded_producer_link(
                path, owner=owner, label=f"raced {label}"
            )
            existing = _read_exact(
                path, limit=len(body), owner=owner, label=f"raced {label}"
            )
            if existing != body:
                _fail(f"immutable {label} already exists with conflicting bytes")
            return False
        _fsync_dir(path.parent)
        os.unlink(temporary)
        _fsync_dir(path.parent)
        _require_file(path, owner=owner, label=label)
        return True
    except LocalReplicaError:
        raise
    except OSError as exc:
        raise LocalReplicaError(f"cannot publish immutable {label}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            try:
                os.unlink(temporary)
                _fsync_dir(path.parent)
            except OSError as exc:
                raise LocalReplicaError(f"cannot clean temporary {label}") from exc


def _replace_local_head(root: Path, payload: Mapping[str, Any], *, owner: tuple[int, int]) -> None:
    body = _canonical_bytes(payload)
    if len(body) > _MAX_LOCAL_HEAD_BYTES:
        _fail("local receipt HEAD exceeds its byte bound")
    path = root / "HEAD.json"
    if path.is_symlink():
        _fail("local receipt HEAD is a symlink")
    temporary = root / f".HEAD.json.tmp.{os.getpid()}.{uuid4().hex}"
    descriptor: int | None = None
    try:
        descriptor = _open_nofollow_file(
            temporary, flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL
        )
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("short write publishing local receipt HEAD")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.chmod(temporary, 0o600)
        _trip("during_head")
        os.replace(temporary, path)
        _fsync_dir(root)
        _require_file(path, owner=owner, label="local receipt HEAD")
    except LocalReplicaError:
        raise
    except OSError as exc:
        raise LocalReplicaError("cannot atomically replace local receipt HEAD") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            try:
                os.unlink(temporary)
                _fsync_dir(root)
            except OSError:
                pass


def _local_head_path(root: Path) -> Path:
    return root / "HEAD.json"


def _classify_from_current(
    current: local_receipts.VerifiedPublication,
    captured: Mapping[str, Any],
) -> dict[str, Any]:
    descriptor = dict(current.descriptor)
    captured_head = captured["head"]
    if (
        descriptor["publication_id"] == captured_head["publication_id"]
        and descriptor["upstream_head_sha256"] == captured["head_sha256"]
        and descriptor["published_at"] == captured_head["published_at"]
        and descriptor["audit_sha256"] == captured_head["audit_sha256"]
        and descriptor["reference_set_object_sha256"]
        == captured_head["reference_set_object_sha256"]
    ):
        return {"unchanged": True, "publication": current}
    if captured_head["published_at"] <= descriptor["published_at"]:
        _fail("source publication cannot move the local W1A HEAD backward")
    if captured_head["publication_id"] == descriptor["publication_id"]:
        _fail("source publication conflicts with the current local publication identity")
    return {
        "unchanged": False,
        "previous_descriptor_sha256": current.high_water["descriptor_sha256"],
        "sequence": int(descriptor["sequence"]) + 1,
        "previous_publication": current,
    }


def _read_current_publication(
    dest: Path,
    *,
    expected_root: local_receipts.RootIdentity,
    previous_high_water: Mapping[str, Any] | None,
) -> local_receipts.VerifiedPublication:
    try:
        return local_receipts.read_publication(
            dest,
            expected_root=expected_root,
            previous_high_water=previous_high_water,
        )
    except local_receipts.LocalReceiptError as exc:
        raise LocalReplicaError(
            "existing local W1A publication failed verification"
        ) from exc


def _descriptor_for(
    captured: Mapping[str, Any],
    *,
    sequence: int,
    previous_descriptor_sha256: str | None,
) -> tuple[dict[str, Any], bytes, str, str]:
    head = captured["head"]
    head_sha256 = captured["head_sha256"]
    descriptor = {
        "schema": local_receipts.DESCRIPTOR_SCHEMA,
        "sequence": sequence,
        "previous_descriptor_sha256": previous_descriptor_sha256,
        "publication_id": head["publication_id"],
        "published_at": head["published_at"],
        "deployed_commit": head["deployed_commit"],
        "upstream_head_sha256": head_sha256,
        "upstream_head_object_key": _content_key("heads", head_sha256),
        "audit_id": head["audit_id"],
        "audit_sha256": head["audit_sha256"],
        "audit_object_key": head["audit_object_key"],
        "reference_set_sha256": head["reference_set_sha256"],
        "reference_set_object_sha256": head["reference_set_object_sha256"],
        "reference_set_object_key": head["reference_set_object_key"],
        "reference_count": head["reference_count"],
        "evidence_policy": copy.deepcopy(head["evidence_policy"]),
        "authority": copy.deepcopy(dict(local_receipts.AUTHORITY)),
    }
    body = _canonical_bytes(descriptor)
    if len(body) > _MAX_DESCRIPTOR_BYTES:
        _fail("local publication descriptor exceeds its byte bound")
    digest = hashlib.sha256(body).hexdigest()
    return descriptor, body, digest, _content_key("descriptors", digest)


def _local_head_payload(
    *,
    store_id: str,
    sequence: int,
    descriptor_sha256: str,
    descriptor_key: str,
    captured: Mapping[str, Any],
) -> dict[str, Any]:
    head = captured["head"]
    return {
        "schema": local_receipts.HEAD_SCHEMA,
        "store_id": store_id,
        "descriptor_count": sequence + 1,
        "current_descriptor_sha256": descriptor_sha256,
        "current_descriptor_object_key": descriptor_key,
        "current_publication_id": head["publication_id"],
        "current_published_at": head["published_at"],
        "authority": copy.deepcopy(dict(local_receipts.AUTHORITY)),
    }


def _seal_namespaces(root: Path, *, owner: tuple[int, int]) -> None:
    for namespace in _NAMESPACES:
        top = root / namespace
        if not top.exists():
            continue
        _require_dir(top, owner=owner, label=f"{namespace} namespace")
        _fsync_dir(top)
        try:
            children = list(top.iterdir())
        except OSError as exc:
            raise LocalReplicaError(f"{namespace} namespace cannot be inspected") from exc
        for child in children:
            if child.name.startswith("."):
                continue
            _require_dir(child, owner=owner, label=f"{namespace} shard")
            _fsync_dir(child)


@contextmanager
def _single_writer(root: Path) -> Iterator[None]:
    descriptor = _open_directory(root)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise LocalReplicaError("local replica single-writer lock failed") from exc
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class ReplicaResult:
    """Outcome of one replication attempt against a caller-owned W1A root."""

    unchanged: bool
    publication: local_receipts.VerifiedPublication


def replicate_publication(
    source_root: str | Path,
    destination_root: str | Path,
    *,
    expected_root: local_receipts.RootIdentity,
    previous_high_water: Mapping[str, Any] | None = None,
) -> ReplicaResult:
    """Copy one authenticated upstream publication into an admitted W1A root."""

    if not isinstance(expected_root, local_receipts.RootIdentity):
        _fail("an exact caller-persisted destination root identity is required")
    dest = Path(os.path.abspath(os.fspath(destination_root)))
    if os.fspath(destination_root) != str(dest):
        _fail("destination root must be a normalized absolute path")
    if dest == local_receipts.DEFAULT_STORE_ROOT.resolve():
        _fail("W1A-B will not write the reviewed production W1A root")
    source = Path(os.path.abspath(os.fspath(source_root)))
    if dest == source:
        _fail("source and destination receipt roots must be distinct")
    if dest != Path(expected_root.path):
        _fail("destination root does not match the attested root identity")

    with _single_writer(dest):
        try:
            identity = local_receipts.attest_root(
                dest,
                expected_uid=expected_root.uid,
                expected_gid=expected_root.gid,
            )
        except local_receipts.LocalReceiptError as exc:
            raise LocalReplicaError("destination root failed W1A-A attestation") from exc
        if identity != expected_root:
            _fail("destination root was substituted")
        owner = (expected_root.uid, expected_root.gid)
        head_path = _local_head_path(dest)
        try:
            head_metadata = os.lstat(head_path)
        except FileNotFoundError:
            if previous_high_water is not None:
                _fail("previous high-water is impossible without a local HEAD")
            captured = _authenticate_source(source)
            classified: dict[str, Any] | None = None
        else:
            if stat.S_ISLNK(head_metadata.st_mode):
                _fail("local receipt HEAD is a symlink")
            _require_file(head_path, owner=owner, label="local receipt HEAD")
            current = _read_current_publication(
                dest,
                expected_root=expected_root,
                previous_high_water=previous_high_water,
            )
            captured = _authenticate_source(source)
            classified = _classify_from_current(current, captured)
            if classified.get("unchanged") is True:
                return ReplicaResult(
                    unchanged=True, publication=classified["publication"]
                )

        if classified is None:
            sequence = 0
            previous = None
        else:
            sequence = int(classified["sequence"])
            previous = classified["previous_descriptor_sha256"]

        _trip("before_first_immutable")
        head_key = _content_key("heads", captured["head_sha256"])
        _create_once(
            dest, head_key, captured["head_body"], owner=owner, label="historical upstream HEAD"
        )
        _trip("between_immutable")
        _create_once(
            dest,
            str(captured["head"]["audit_object_key"]),
            captured["audit_body"],
            owner=owner,
            label="historical audit object",
        )
        _create_once(
            dest,
            str(captured["head"]["reference_set_object_key"]),
            captured["reference_body"],
            owner=owner,
            label="historical reference-set object",
        )
        _trip("before_descriptor")
        _descriptor, descriptor_body, descriptor_sha256, descriptor_key = _descriptor_for(
            captured, sequence=sequence, previous_descriptor_sha256=previous
        )
        _create_once(
            dest,
            descriptor_key,
            descriptor_body,
            owner=owner,
            label="local publication descriptor",
        )
        _trip("after_descriptor_before_head")
        _seal_namespaces(dest, owner=owner)
        persisted_head = _read_exact(
            dest.joinpath(*head_key.split("/")),
            limit=_MAX_HEAD_BYTES,
            owner=owner,
            label="sealed historical upstream HEAD",
        )
        if persisted_head != captured["head_body"]:
            _fail("historical upstream HEAD bytes changed before HEAD publication")
        local_head = _local_head_payload(
            store_id=expected_root.store_id,
            sequence=sequence,
            descriptor_sha256=descriptor_sha256,
            descriptor_key=descriptor_key,
            captured=captured,
        )
        _replace_local_head(dest, local_head, owner=owner)
        try:
            publication = local_receipts.read_publication(
                dest,
                expected_root=expected_root,
                previous_high_water=previous_high_water,
                publication_id=captured["head"]["publication_id"],
            )
        except local_receipts.LocalReceiptError as exc:
            raise LocalReplicaError(
                "replicated publication failed W1A-A verification"
            ) from exc
        if publication.descriptor["upstream_head_sha256"] != captured["head_sha256"]:
            _fail("W1A-A verification did not bind the captured upstream HEAD")
        return ReplicaResult(unchanged=False, publication=publication)


__all__ = [
    "LocalReplicaError",
    "ReplicaResult",
    "replicate_publication",
]
