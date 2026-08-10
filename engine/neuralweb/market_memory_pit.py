"""Immutable go-forward capture and exact reader for Market Memory W1A.

This module deliberately does less than the full Historical Experience
Simulator.  It persists only already-built ``market_memory.as_known_at.v1``
packets captured contemporaneously in ``operational_pit`` mode.  It never
recomputes a missing packet, chooses a nearest date, falls back to current
identity, or mutates any domain-owned source ledger.

The store has three create-once capture layers plus one bounded generation
index:

``objects/<sha-prefix>/<packet_sha256>.json``
    Canonical packet bytes, addressed by the SHA-256 of the exact stored bytes.
``contexts/<id-prefix>/<context_id>.json``
    A capture receipt for direct context-id retrieval.
``queries/<id-prefix>/<query_id>.json``
    One exact subject/event/cutoff/mode receipt.
``generations/<sha-prefix>/<generation_id>.json`` and ``HEAD.json``
    A hash-bound complete index.  ``HEAD.json`` is atomically replaced last, so
    readers can distinguish a proven exact miss from an unavailable or partial
    store.

An orphaned object or context receipt is harmless after a crash: readers trust
only captures named by the active generation and require both receipt copies to
match byte-for-byte.  Writes are create-only and directory-locked, so an
identical retry is a no-op while a different packet for the same operational
query is a hard conflict.
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

from engine.neuralweb import market_memory

CAPTURE_RECEIPT_SCHEMA = "market_memory.capture_receipt.v1"
_STORED_CONTEXT_SCHEMA = "market_memory.stored_context.v1"
_STORE_MANIFEST_SCHEMA = "market_memory.store_manifest.v1"
_STORE_HEAD_SCHEMA = "market_memory.store_head.v1"
_STORE_GENERATION_SCHEMA = "market_memory.store_generation.v1"
_SECURITY_ID = re.compile(r"mmsecurity_[a-f0-9]{64}\Z")
_CONTEXT_ID = re.compile(r"mmctx_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmcapture_[a-f0-9]{64}\Z")
_QUERY_ID = re.compile(r"mmquery_[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmstore_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmgeneration_[a-f0-9]{64}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_VERSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
_RFC3339_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z"
)
_MAX_PACKET_BYTES = 512 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024
_MAX_STORE_MANIFEST_BYTES = 64 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_MAX_GENERATION_BYTES = 2 * 1024 * 1024
_MAX_GENERATION_CAPTURES = 4_096
_MAX_CAPTURE_LAG = timedelta(minutes=15)
_MAX_CLOCK_SKEW = timedelta(seconds=5)
_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "store_id",
        "capture_id",
        "query_id",
        "context_id",
        "packet_sha256",
        "object_key",
        "subject",
        "clocks",
        "mode",
        "captured_at",
        "feature_registry_version",
        "source_registry_version",
        "source_receipt_ids",
        "source_artifact_sha256s",
        "missing_feature_ids",
        "domain_coverage_sha256",
        "evidence_policy",
        "authority",
    }
)
_QUERY_FIELDS = frozenset({"subject", "event_time", "as_known_at", "mode"})
_EVIDENCE_POLICY = {
    "contract_validated": True,
    "source_artifacts_authenticated": False,
    "identity_artifacts_authenticated": False,
    "allowed_feature_status": "missing_only",
    "training_eligible": False,
    "promotion_eligible": False,
    "role": "context_only",
}


class MarketMemoryPITError(RuntimeError):
    """Base class for the W1A capture/read boundary."""


class MarketMemoryQueryError(MarketMemoryPITError):
    """A requested-as-of query is malformed or outside W1A scope."""


class MarketMemoryContextNotFound(MarketMemoryPITError):
    """No exact immutable capture exists for the requested query."""


class MarketMemoryStoreError(MarketMemoryPITError):
    """The immutable store is unavailable, corrupt, or receipt-inconsistent."""


class MarketMemoryCaptureError(MarketMemoryPITError):
    """A packet cannot be admitted to the go-forward operational store."""


@dataclass(frozen=True)
class StoredMarketMemoryContext:
    """One validated packet plus its independent exact-byte capture receipt."""

    packet: market_memory.AsKnownAtContext
    capture_receipt: dict[str, Any]

    def response_payload(self) -> dict[str, Any]:
        """Return a detached private-API envelope with no authority upgrade."""

        return {
            "schema": _STORED_CONTEXT_SCHEMA,
            "capture_receipt": copy.deepcopy(self.capture_receipt),
            "context": copy.deepcopy(self.packet),
        }


@dataclass(frozen=True)
class _StoreState:
    manifest: dict[str, Any]
    head: dict[str, Any]
    generation: dict[str, Any]


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
        raise MarketMemoryStoreError("value is not canonical finite JSON") from exc


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
        raise MarketMemoryStoreError(f"{label} is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise MarketMemoryStoreError(f"{label} must be a JSON object")
    return payload


def _read_canonical_object(
    path: Path,
    *,
    limit: int,
    label: str,
    missing_is_not_found: bool = False,
) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        if missing_is_not_found:
            raise MarketMemoryContextNotFound(f"{label} is not captured") from exc
        raise MarketMemoryStoreError(f"{label} is unavailable") from exc
    except OSError as exc:
        raise MarketMemoryStoreError(f"{label} cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MarketMemoryStoreError(f"{label} is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > limit:
            raise MarketMemoryStoreError(f"{label} exceeds its safe size bound")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
    except OSError as exc:
        raise MarketMemoryStoreError(f"{label} cannot be read") from exc
    finally:
        os.close(descriptor)
    if len(body) != metadata.st_size or len(body) > limit:
        raise MarketMemoryStoreError(f"{label} changed or exceeded its safe bound")
    payload = _strict_json_object(body, label=label)
    if body != _canonical_bytes(payload):
        raise MarketMemoryStoreError(f"{label} is not canonical JSON bytes")
    return payload, body


def load_packet_file(path: str | Path) -> dict[str, Any]:
    """Read one bounded strict JSON packet file for the sole capture CLI."""

    payload, _body = _read_canonical_or_normalizable_packet(Path(path))
    return payload


def _read_canonical_or_normalizable_packet(path: Path) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryCaptureError("input packet cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MarketMemoryCaptureError("input packet is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > _MAX_PACKET_BYTES:
            raise MarketMemoryCaptureError("input packet exceeds its safe size bound")
        body = b""
        while len(body) <= _MAX_PACKET_BYTES:
            chunk = os.read(descriptor, min(65_536, _MAX_PACKET_BYTES + 1 - len(body)))
            if not chunk:
                break
            body += chunk
    except OSError as exc:
        raise MarketMemoryCaptureError("input packet cannot be read") from exc
    finally:
        os.close(descriptor)
    if len(body) != metadata.st_size or len(body) > _MAX_PACKET_BYTES:
        raise MarketMemoryCaptureError(
            "input packet changed or exceeded its safe bound"
        )
    try:
        payload = _strict_json_object(body, label="input packet")
    except MarketMemoryStoreError as exc:
        raise MarketMemoryCaptureError(str(exc)) from exc
    return payload, _canonical_bytes(payload)


def _parse_exact_utc(value: object, *, field: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        raise MarketMemoryQueryError(
            f"{field} must be an exact RFC3339 UTC timestamp, not a date-only value"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryQueryError(f"{field} is not a valid timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise MarketMemoryQueryError(f"{field} must be UTC")
    parsed = parsed.astimezone(timezone.utc)
    return parsed, parsed.isoformat().replace("+00:00", "Z")


def _security_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SECURITY_ID.fullmatch(value):
        raise MarketMemoryQueryError(
            f"{field} must be an opaque mmsecurity_<sha256> identifier"
        )
    return value


def _normalize_query(
    *,
    subject: Mapping[str, str],
    event_time: str,
    as_known_at: str,
    mode: str,
    reject_future_cutoff: bool,
) -> tuple[dict[str, Any], datetime, datetime]:
    if not isinstance(subject, Mapping) or set(subject) != {
        "subject_id",
        "instrument_id",
    }:
        raise MarketMemoryQueryError(
            "subject must contain exactly subject_id and instrument_id"
        )
    clean_subject = {
        "subject_id": _security_id(subject.get("subject_id"), field="subject_id"),
        "instrument_id": _security_id(
            subject.get("instrument_id"), field="instrument_id"
        ),
    }
    event_dt, clean_event = _parse_exact_utc(event_time, field="event_time")
    cutoff_dt, clean_cutoff = _parse_exact_utc(as_known_at, field="as_known_at")
    if event_dt > cutoff_dt:
        raise MarketMemoryQueryError("event_time cannot follow as_known_at")
    if mode != "operational_pit":
        raise MarketMemoryQueryError(
            "W1A stores only operational_pit captures; reconstruction is not implemented"
        )
    if reject_future_cutoff and cutoff_dt > _utc_now() + _MAX_CLOCK_SKEW:
        raise MarketMemoryQueryError("as_known_at cannot be in the future")
    return (
        {
            "subject": clean_subject,
            "event_time": clean_event,
            "as_known_at": clean_cutoff,
            "mode": mode,
        },
        event_dt,
        cutoff_dt,
    )


def _query_id(query: Mapping[str, Any]) -> str:
    if set(query) != _QUERY_FIELDS:
        raise MarketMemoryStoreError("capture query fields are not canonical")
    return "mmquery_" + sha256(_canonical_bytes(query)).hexdigest()


def _capture_id(receipt: Mapping[str, Any]) -> str:
    core = dict(receipt)
    core["capture_id"] = ""
    return "mmcapture_" + sha256(_canonical_bytes(core)).hexdigest()


def _packet_sha256(packet: Mapping[str, Any]) -> tuple[str, bytes]:
    body = _canonical_bytes(packet)
    if len(body) > _MAX_PACKET_BYTES:
        raise MarketMemoryCaptureError("context packet exceeds its safe size bound")
    return sha256(body).hexdigest(), body


def validate_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    """Resolve one private store root and reject public or dangerously broad paths."""

    candidate = Path(root).expanduser().resolve()
    if candidate == Path(candidate.anchor) or candidate == Path.home().resolve():
        raise MarketMemoryStoreError("Market Memory PIT store root is too broad")
    if {"site", "site.served"}.intersection(candidate.parts):
        raise MarketMemoryStoreError(
            "Market Memory PIT store cannot use site/ or site.served/"
        )
    if repository_root is not None:
        repository = Path(repository_root).expanduser().resolve()
        if candidate == repository:
            raise MarketMemoryStoreError(
                "Market Memory PIT store cannot use the repository root"
            )
        for public_name in ("site", "site.served"):
            public_root = repository / public_name
            if candidate == public_root or public_root in candidate.parents:
                raise MarketMemoryStoreError(
                    "Market Memory PIT store cannot use a public site root"
                )
    return candidate


def _safe_store_path(root: Path, *parts: str) -> Path:
    """Build one contract-owned path without following a store-internal symlink."""

    candidate = root.joinpath(*parts)
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise MarketMemoryStoreError("Market Memory store contains a symlink")
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise MarketMemoryStoreError("Market Memory store path escaped its root")
    return candidate


def _object_path(root: Path, digest: str) -> Path:
    if not _SHA256.fullmatch(digest):
        raise MarketMemoryStoreError("packet SHA-256 is malformed")
    return _safe_store_path(root, "objects", digest[:2], f"{digest}.json")


def _context_path(root: Path, context_id: str) -> Path:
    if not _CONTEXT_ID.fullmatch(context_id):
        raise MarketMemoryQueryError("context_id must be mmctx_<sha256>")
    digest = context_id.removeprefix("mmctx_")
    return _safe_store_path(root, "contexts", digest[:2], f"{context_id}.json")


def _query_path(root: Path, query_id: str) -> Path:
    if not _QUERY_ID.fullmatch(query_id):
        raise MarketMemoryStoreError("query_id is malformed")
    digest = query_id.removeprefix("mmquery_")
    return _safe_store_path(root, "queries", digest[:2], f"{query_id}.json")


def _store_manifest_path(root: Path) -> Path:
    return _safe_store_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return _safe_store_path(root, "HEAD.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(
        generation_id
    ):
        raise MarketMemoryStoreError("store generation_id is malformed")
    digest = generation_id.removeprefix("mmgeneration_")
    return _safe_store_path(root, "generations", digest[:2], f"{generation_id}.json")


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


def _new_store_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": _STORE_MANIFEST_SCHEMA,
        "store_id": "",
        "nonce": uuid4().hex,
        "packet_schema": market_memory.AS_KNOWN_AT_SCHEMA,
        "capture_receipt_schema": CAPTURE_RECEIPT_SCHEMA,
        "generation_schema": _STORE_GENERATION_SCHEMA,
        "mode": "operational_pit",
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    manifest["store_id"] = _content_id("mmstore_", manifest, field="store_id")
    return manifest


def _validate_store_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema",
        "store_id",
        "nonce",
        "packet_schema",
        "capture_receipt_schema",
        "generation_schema",
        "mode",
        "evidence_policy",
        "authority",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected:
        raise MarketMemoryStoreError("store manifest fields are not canonical")
    clean = copy.deepcopy(dict(manifest))
    if clean.get("schema") != _STORE_MANIFEST_SCHEMA:
        raise MarketMemoryStoreError("store manifest schema mismatch")
    store_id = clean.get("store_id")
    if not isinstance(store_id, str) or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryStoreError("store_id is malformed")
    nonce = clean.get("nonce")
    if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise MarketMemoryStoreError("store manifest nonce is malformed")
    if clean.get("packet_schema") != market_memory.AS_KNOWN_AT_SCHEMA:
        raise MarketMemoryStoreError("store packet schema mismatch")
    if clean.get("capture_receipt_schema") != CAPTURE_RECEIPT_SCHEMA:
        raise MarketMemoryStoreError("store capture receipt schema mismatch")
    if clean.get("generation_schema") != _STORE_GENERATION_SCHEMA:
        raise MarketMemoryStoreError("store generation schema mismatch")
    if clean.get("mode") != "operational_pit":
        raise MarketMemoryStoreError("store mode mismatch")
    if clean.get("evidence_policy") != _EVIDENCE_POLICY:
        raise MarketMemoryStoreError("store evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryStoreError("store authority drift")
    if _content_id("mmstore_", clean, field="store_id") != store_id:
        raise MarketMemoryStoreError("store_id does not bind the manifest")
    return clean


def _new_generation(
    *,
    store_id: str,
    previous_generation_id: str | None,
    captures: list[Mapping[str, str]],
) -> dict[str, Any]:
    generation: dict[str, Any] = {
        "schema": _STORE_GENERATION_SCHEMA,
        "generation_id": "",
        "store_id": store_id,
        "previous_generation_id": previous_generation_id,
        "captures": sorted(
            (dict(row) for row in captures), key=lambda row: row["query_id"]
        ),
    }
    generation["generation_id"] = _content_id(
        "mmgeneration_", generation, field="generation_id"
    )
    return generation


def _validate_generation(
    generation: Mapping[str, Any], *, store_id: str
) -> dict[str, Any]:
    expected = {
        "schema",
        "generation_id",
        "store_id",
        "previous_generation_id",
        "captures",
    }
    if not isinstance(generation, Mapping) or set(generation) != expected:
        raise MarketMemoryStoreError("store generation fields are not canonical")
    clean = copy.deepcopy(dict(generation))
    if clean.get("schema") != _STORE_GENERATION_SCHEMA:
        raise MarketMemoryStoreError("store generation schema mismatch")
    generation_id = clean.get("generation_id")
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(
        generation_id
    ):
        raise MarketMemoryStoreError("store generation_id is malformed")
    if clean.get("store_id") != store_id:
        raise MarketMemoryStoreError("store generation belongs to another store")
    previous = clean.get("previous_generation_id")
    if previous is not None and (
        not isinstance(previous, str) or not _GENERATION_ID.fullmatch(previous)
    ):
        raise MarketMemoryStoreError("previous store generation_id is malformed")
    captures = clean.get("captures")
    if not isinstance(captures, list):
        raise MarketMemoryStoreError("store generation captures must be a list")
    if len(captures) > _MAX_GENERATION_CAPTURES:
        raise MarketMemoryStoreError("store generation exceeds its capture bound")
    capture_fields = {"query_id", "context_id", "capture_id", "packet_sha256"}
    for row in captures:
        if not isinstance(row, Mapping) or set(row) != capture_fields:
            raise MarketMemoryStoreError("store generation entry is not canonical")
        if not isinstance(row.get("query_id"), str) or not _QUERY_ID.fullmatch(
            row["query_id"]
        ):
            raise MarketMemoryStoreError("store generation query_id is malformed")
        if not isinstance(row.get("context_id"), str) or not _CONTEXT_ID.fullmatch(
            row["context_id"]
        ):
            raise MarketMemoryStoreError("store generation context_id is malformed")
        if not isinstance(row.get("capture_id"), str) or not _CAPTURE_ID.fullmatch(
            row["capture_id"]
        ):
            raise MarketMemoryStoreError("store generation capture_id is malformed")
        if not isinstance(row.get("packet_sha256"), str) or not _SHA256.fullmatch(
            row["packet_sha256"]
        ):
            raise MarketMemoryStoreError("store generation packet SHA-256 is malformed")
    query_ids = [row["query_id"] for row in captures]
    context_ids = [row["context_id"] for row in captures]
    if query_ids != sorted(query_ids) or len(query_ids) != len(set(query_ids)):
        raise MarketMemoryStoreError("store generation query index is not canonical")
    if len(context_ids) != len(set(context_ids)):
        raise MarketMemoryStoreError("store generation context index is ambiguous")
    if _content_id("mmgeneration_", clean, field="generation_id") != generation_id:
        raise MarketMemoryStoreError("generation_id does not bind the generation")
    return clean


def _new_head(
    generation: Mapping[str, Any], *, generation_body: bytes
) -> dict[str, Any]:
    return {
        "schema": _STORE_HEAD_SCHEMA,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": sha256(generation_body).hexdigest(),
    }


def _validate_head(head: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    expected = {"schema", "store_id", "generation_id", "generation_sha256"}
    if not isinstance(head, Mapping) or set(head) != expected:
        raise MarketMemoryStoreError("store HEAD fields are not canonical")
    clean = copy.deepcopy(dict(head))
    if clean.get("schema") != _STORE_HEAD_SCHEMA:
        raise MarketMemoryStoreError("store HEAD schema mismatch")
    if clean.get("store_id") != store_id:
        raise MarketMemoryStoreError("store HEAD belongs to another store")
    generation_id = clean.get("generation_id")
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(
        generation_id
    ):
        raise MarketMemoryStoreError("store HEAD generation_id is malformed")
    digest = clean.get("generation_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise MarketMemoryStoreError("store HEAD generation SHA-256 is malformed")
    return clean


def _directory_fsync(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    """Create a directory chain and fsync every newly linked parent entry."""

    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise MarketMemoryStoreError("Market Memory store path is a symlink")
        missing.append(cursor)
        if cursor == cursor.parent:
            raise MarketMemoryStoreError("Market Memory store has no safe parent")
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise MarketMemoryStoreError("Market Memory store parent is not a directory")
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise MarketMemoryStoreError(
                    "Market Memory store directory race was unsafe"
                ) from None
        _directory_fsync(directory.parent)


def _write_create_once(root: Path, path: Path, body: bytes, *, label: str) -> bool:
    """Atomically link canonical bytes into a create-once final path."""

    try:
        path.parent.relative_to(root)
    except ValueError as exc:
        raise MarketMemoryStoreError("immutable write escaped the store root") from exc
    _mkdir_durable(path.parent)
    if path.exists() or path.is_symlink():
        _payload, existing = _read_canonical_object(
            path,
            limit=len(body),
            label=f"existing {label}",
        )
        if existing != body:
            raise MarketMemoryCaptureError(f"immutable {label} collision")
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
            _directory_fsync(path.parent)
            return True
        except FileExistsError:
            _payload, existing = _read_canonical_object(
                path,
                limit=len(body),
                label=f"raced {label}",
            )
            if existing != body:
                raise MarketMemoryCaptureError(f"immutable {label} collision")
            return False
    except (MarketMemoryCaptureError, MarketMemoryStoreError):
        raise
    except OSError as exc:
        raise MarketMemoryStoreError(f"cannot publish immutable {label}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _replace_head(root: Path, head: Mapping[str, Any]) -> None:
    """Atomically advance the only mutable pointer after all immutable bytes exist."""

    body = _canonical_bytes(head)
    if len(body) > _MAX_HEAD_BYTES:
        raise MarketMemoryStoreError("store HEAD exceeds its safe size bound")
    path = _head_path(root)
    if path.is_symlink():
        raise MarketMemoryStoreError("Market Memory store HEAD is a symlink")
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
        _directory_fsync(root)
    except OSError as exc:
        raise MarketMemoryStoreError("cannot advance Market Memory store HEAD") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _initialize_store(root: Path) -> _StoreState:
    manifest_path = _store_manifest_path(root)
    head_path = _head_path(root)
    generation_root = _safe_store_path(root, "generations")
    if manifest_path.exists() or head_path.exists() or generation_root.exists():
        raise MarketMemoryStoreError("Market Memory store initialization is partial")
    manifest = _new_store_manifest()
    manifest_body = _canonical_bytes(manifest)
    generation = _new_generation(
        store_id=manifest["store_id"],
        previous_generation_id=None,
        captures=[],
    )
    generation_body = _canonical_bytes(generation)
    _write_create_once(root, manifest_path, manifest_body, label="store manifest")
    _write_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="empty store generation",
    )
    head = _new_head(generation, generation_body=generation_body)
    _replace_head(root, head)
    return _StoreState(manifest=manifest, head=head, generation=generation)


def _initialize_or_load_store(root: Path) -> _StoreState:
    """Load a complete store or repair only the deterministic empty-init prefix."""

    manifest_path = _store_manifest_path(root)
    head_path = _head_path(root)
    generation_root = _safe_store_path(root, "generations")
    if head_path.exists() or head_path.is_symlink():
        return _load_store_state(root)
    if not (manifest_path.exists() or manifest_path.is_symlink()):
        if generation_root.exists() or generation_root.is_symlink():
            raise MarketMemoryStoreError(
                "Market Memory store initialization is partial"
            )
        return _initialize_store(root)

    for capture_root in ("objects", "contexts", "queries"):
        path = _safe_store_path(root, capture_root)
        if path.exists() or path.is_symlink():
            raise MarketMemoryStoreError(
                "Market Memory store has captures without an active HEAD"
            )
    manifest, _manifest_body = _read_canonical_object(
        manifest_path,
        limit=_MAX_STORE_MANIFEST_BYTES,
        label="Market Memory store manifest",
    )
    clean_manifest = _validate_store_manifest(manifest)
    generation = _new_generation(
        store_id=clean_manifest["store_id"],
        previous_generation_id=None,
        captures=[],
    )
    generation_body = _canonical_bytes(generation)
    _write_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="empty store generation",
    )
    head = _new_head(generation, generation_body=generation_body)
    _replace_head(root, head)
    return _StoreState(manifest=clean_manifest, head=head, generation=generation)


def _load_store_state(root: Path) -> _StoreState:
    manifest, _manifest_body = _read_canonical_object(
        _store_manifest_path(root),
        limit=_MAX_STORE_MANIFEST_BYTES,
        label="Market Memory store manifest",
    )
    clean_manifest = _validate_store_manifest(manifest)
    head, _head_body = _read_canonical_object(
        _head_path(root), limit=_MAX_HEAD_BYTES, label="Market Memory store HEAD"
    )
    clean_head = _validate_head(head, store_id=clean_manifest["store_id"])
    generation, generation_body = _read_canonical_object(
        _generation_path(root, clean_head["generation_id"]),
        limit=_MAX_GENERATION_BYTES,
        label="Market Memory store generation",
    )
    if sha256(generation_body).hexdigest() != clean_head["generation_sha256"]:
        raise MarketMemoryStoreError("store HEAD generation SHA-256 mismatch")
    clean_generation = _validate_generation(
        generation, store_id=clean_manifest["store_id"]
    )
    if clean_generation["generation_id"] != clean_head["generation_id"]:
        raise MarketMemoryStoreError("store HEAD generation identity mismatch")
    return _StoreState(
        manifest=clean_manifest,
        head=clean_head,
        generation=clean_generation,
    )


def _capture_entry(receipt: Mapping[str, Any]) -> dict[str, str]:
    return {
        "query_id": str(receipt["query_id"]),
        "context_id": str(receipt["context_id"]),
        "capture_id": str(receipt["capture_id"]),
        "packet_sha256": str(receipt["packet_sha256"]),
    }


def _generation_entry(
    generation: Mapping[str, Any], *, field: str, value: str
) -> dict[str, str] | None:
    matches = [
        dict(row)
        for row in generation["captures"]
        if isinstance(row, Mapping) and row.get(field) == value
    ]
    if len(matches) > 1:  # pragma: no cover - validator already rejects this
        raise MarketMemoryStoreError("store generation index is ambiguous")
    return matches[0] if matches else None


def _publish_generation(
    root: Path, *, state: _StoreState, receipt: Mapping[str, Any]
) -> _StoreState:
    captures = [dict(row) for row in state.generation["captures"]]
    if len(captures) >= _MAX_GENERATION_CAPTURES:
        raise MarketMemoryCaptureError("W1A store generation is at its pilot bound")
    captures.append(_capture_entry(receipt))
    generation = _new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=state.generation["generation_id"],
        captures=captures,
    )
    generation_body = _canonical_bytes(generation)
    if len(generation_body) > _MAX_GENERATION_BYTES:
        raise MarketMemoryCaptureError("W1A store generation exceeds its byte bound")
    _write_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="store generation",
    )
    head = _new_head(generation, generation_body=generation_body)
    _replace_head(root, head)
    return _StoreState(manifest=state.manifest, head=head, generation=generation)


def _validate_capture_candidate(
    packet: Mapping[str, Any], *, admit_new: bool
) -> market_memory.AsKnownAtContext:
    try:
        validated = market_memory.validate_as_known_at_context(packet)
    except market_memory.TemporalContractError as exc:
        raise MarketMemoryCaptureError("packet fails the frozen W0 contract") from exc
    if validated["mode"] != "operational_pit":
        raise MarketMemoryCaptureError(
            "W1A capture accepts operational_pit packets only"
        )
    _query, _event_dt, _cutoff_dt = _normalize_query(
        subject=validated["subject"],
        event_time=validated["clocks"]["event_time"],
        as_known_at=validated["clocks"]["as_known_at"],
        mode=validated["mode"],
        reject_future_cutoff=False,
    )
    if admit_new and (
        validated["feature_registry_version"] != market_memory.FEATURE_REGISTRY_VERSION
        or validated["source_registry_version"] != market_memory.SOURCE_REGISTRY_VERSION
    ):
        raise MarketMemoryCaptureError(
            "new captures must use the current frozen registry versions"
        )
    for feature in validated["feature_receipts"]:
        if feature["status"] == "observed":
            raise MarketMemoryCaptureError(
                "W1A cannot capture observed features until trusted source adapters authenticate their component receipts"
            )
    return validated


def _require_contemporaneous_capture(
    packet: market_memory.AsKnownAtContext, *, captured_at: datetime
) -> None:
    _query, _event_dt, cutoff_dt = _normalize_query(
        subject=packet["subject"],
        event_time=packet["clocks"]["event_time"],
        as_known_at=packet["clocks"]["as_known_at"],
        mode=packet["mode"],
        reject_future_cutoff=False,
    )
    if captured_at.tzinfo is None or captured_at.utcoffset() != timedelta(0):
        raise MarketMemoryCaptureError("capture clock must be UTC")
    captured_at = captured_at.astimezone(timezone.utc)
    if captured_at + _MAX_CLOCK_SKEW < cutoff_dt:
        raise MarketMemoryCaptureError(
            "operational packet was captured before its cutoff"
        )
    if captured_at - cutoff_dt > _MAX_CAPTURE_LAG:
        raise MarketMemoryCaptureError(
            "operational packet was not captured contemporaneously with its cutoff"
        )
    for feature in packet["feature_receipts"]:
        if feature["status"] != "missing":
            continue
        feature_observed, _ = _parse_exact_utc(
            feature["observed_at"], field=f"{feature['feature_id']}.observed_at"
        )
        if captured_at - feature_observed > _MAX_CAPTURE_LAG:
            raise MarketMemoryCaptureError(
                "operational missingness was not checked contemporaneously"
            )


def _build_capture_receipt(
    packet: market_memory.AsKnownAtContext,
    *,
    store_id: str,
    packet_sha256: str,
    captured_at: datetime,
) -> dict[str, Any]:
    query = {
        "subject": dict(packet["subject"]),
        "event_time": packet["clocks"]["event_time"],
        "as_known_at": packet["clocks"]["as_known_at"],
        "mode": packet["mode"],
    }
    query_id = _query_id(query)
    receipt: dict[str, Any] = {
        "schema": CAPTURE_RECEIPT_SCHEMA,
        "store_id": store_id,
        "capture_id": "",
        "query_id": query_id,
        "context_id": packet["context_id"],
        "packet_sha256": packet_sha256,
        "object_key": f"objects/{packet_sha256[:2]}/{packet_sha256}.json",
        "subject": dict(packet["subject"]),
        "clocks": {
            "event_time": packet["clocks"]["event_time"],
            "as_known_at": packet["clocks"]["as_known_at"],
            "knowledge_cutoff": packet["clocks"]["knowledge_cutoff"],
        },
        "mode": packet["mode"],
        "captured_at": captured_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "feature_registry_version": packet["feature_registry_version"],
        "source_registry_version": packet["source_registry_version"],
        "source_receipt_ids": sorted(
            {source["receipt_id"] for source in packet["source_receipts"]}
        ),
        "source_artifact_sha256s": sorted(
            {source["artifact_sha256"] for source in packet["source_receipts"]}
        ),
        "missing_feature_ids": sorted(
            feature["feature_id"]
            for feature in packet["feature_receipts"]
            if feature["status"] == "missing"
        ),
        "domain_coverage_sha256": sha256(
            _canonical_bytes(packet["domain_coverage"])
        ).hexdigest(),
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    receipt["capture_id"] = _capture_id(receipt)
    return receipt


def _validate_capture_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_FIELDS:
        raise MarketMemoryStoreError("capture receipt fields are not canonical")
    if receipt.get("schema") != CAPTURE_RECEIPT_SCHEMA:
        raise MarketMemoryStoreError("capture receipt schema mismatch")
    store_id = receipt.get("store_id")
    capture_id = receipt.get("capture_id")
    query_id = receipt.get("query_id")
    context_id = receipt.get("context_id")
    packet_digest = receipt.get("packet_sha256")
    if not isinstance(store_id, str) or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryStoreError("capture receipt store_id is malformed")
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryStoreError("capture_id is malformed")
    if not isinstance(query_id, str) or not _QUERY_ID.fullmatch(query_id):
        raise MarketMemoryStoreError("query_id is malformed")
    if not isinstance(context_id, str) or not _CONTEXT_ID.fullmatch(context_id):
        raise MarketMemoryStoreError("context_id is malformed")
    if not isinstance(packet_digest, str) or not _SHA256.fullmatch(packet_digest):
        raise MarketMemoryStoreError("packet_sha256 is malformed")
    expected_object_key = f"objects/{packet_digest[:2]}/{packet_digest}.json"
    if receipt.get("object_key") != expected_object_key:
        raise MarketMemoryStoreError("capture receipt object key mismatch")
    subject = receipt.get("subject")
    clocks = receipt.get("clocks")
    if not isinstance(subject, Mapping) or not isinstance(clocks, Mapping):
        raise MarketMemoryStoreError("capture receipt query identity is malformed")
    if set(clocks) != {"event_time", "as_known_at", "knowledge_cutoff"}:
        raise MarketMemoryStoreError("capture receipt clocks are not canonical")
    if clocks.get("as_known_at") != clocks.get("knowledge_cutoff"):
        raise MarketMemoryStoreError("capture receipt cutoff clocks disagree")
    try:
        query, _event_dt, cutoff_dt = _normalize_query(
            subject=subject,
            event_time=clocks.get("event_time"),
            as_known_at=clocks.get("as_known_at"),
            mode=str(receipt.get("mode") or ""),
            reject_future_cutoff=False,
        )
    except MarketMemoryQueryError as exc:
        raise MarketMemoryStoreError("capture receipt query is malformed") from exc
    if _query_id(query) != query_id:
        raise MarketMemoryStoreError("capture receipt query_id mismatch")
    try:
        captured_dt, _captured = _parse_exact_utc(
            receipt.get("captured_at"), field="captured_at"
        )
    except MarketMemoryQueryError as exc:
        raise MarketMemoryStoreError("capture receipt clock is malformed") from exc
    if captured_dt + _MAX_CLOCK_SKEW < cutoff_dt:
        raise MarketMemoryStoreError("capture receipt precedes its cutoff")
    if captured_dt - cutoff_dt > _MAX_CAPTURE_LAG:
        raise MarketMemoryStoreError("capture receipt is not contemporaneous")
    for field in (
        "source_receipt_ids",
        "source_artifact_sha256s",
        "missing_feature_ids",
    ):
        values = receipt.get(field)
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or not all(isinstance(value, str) for value in values)
        ):
            raise MarketMemoryStoreError(f"capture receipt {field} is not canonical")
    domain_digest = receipt.get("domain_coverage_sha256")
    if not isinstance(domain_digest, str) or not _SHA256.fullmatch(domain_digest):
        raise MarketMemoryStoreError("domain coverage digest is malformed")
    if receipt.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryStoreError("capture receipt authority drift")
    if receipt.get("evidence_policy") != _EVIDENCE_POLICY:
        raise MarketMemoryStoreError("capture receipt evidence policy drift")
    for field in ("feature_registry_version", "source_registry_version"):
        version = receipt.get(field)
        if not isinstance(version, str) or not _VERSION_ID.fullmatch(version):
            raise MarketMemoryStoreError(f"capture receipt {field} is malformed")
    if _capture_id(receipt) != capture_id:
        raise MarketMemoryStoreError("capture_id does not bind the exact receipt")
    return copy.deepcopy(dict(receipt))


def _load_stored_from_receipt(
    root: Path, receipt: Mapping[str, Any], *, store_id: str
) -> StoredMarketMemoryContext:
    clean_receipt = _validate_capture_receipt(receipt)
    if clean_receipt["store_id"] != store_id:
        raise MarketMemoryStoreError("capture receipt belongs to another store")
    packet_path = _object_path(root, clean_receipt["packet_sha256"])
    packet, body = _read_canonical_object(
        packet_path,
        limit=_MAX_PACKET_BYTES,
        label="Market Memory packet object",
    )
    if sha256(body).hexdigest() != clean_receipt["packet_sha256"]:
        raise MarketMemoryStoreError("packet object SHA-256 mismatch")
    try:
        validated = _validate_capture_candidate(packet, admit_new=False)
        captured_dt, _captured_at = _parse_exact_utc(
            clean_receipt["captured_at"], field="captured_at"
        )
        _require_contemporaneous_capture(validated, captured_at=captured_dt)
    except (MarketMemoryCaptureError, MarketMemoryQueryError) as exc:
        raise MarketMemoryStoreError(
            "stored packet fails the W1A capture policy"
        ) from exc
    if validated["context_id"] != clean_receipt["context_id"]:
        raise MarketMemoryStoreError("packet context_id differs from capture receipt")
    if validated["subject"] != clean_receipt["subject"]:
        raise MarketMemoryStoreError("packet subject differs from capture receipt")
    if validated["mode"] != clean_receipt["mode"]:
        raise MarketMemoryStoreError("packet mode differs from capture receipt")
    if validated["clocks"] != clean_receipt["clocks"]:
        raise MarketMemoryStoreError("packet clocks differ from capture receipt")
    if (
        validated["feature_registry_version"]
        != clean_receipt["feature_registry_version"]
    ):
        raise MarketMemoryStoreError("packet feature registry differs from receipt")
    if validated["source_registry_version"] != clean_receipt["source_registry_version"]:
        raise MarketMemoryStoreError("packet source registry differs from receipt")
    source_ids = sorted(
        {source["receipt_id"] for source in validated["source_receipts"]}
    )
    artifact_hashes = sorted(
        {source["artifact_sha256"] for source in validated["source_receipts"]}
    )
    missing_ids = sorted(
        feature["feature_id"]
        for feature in validated["feature_receipts"]
        if feature["status"] == "missing"
    )
    if source_ids != clean_receipt["source_receipt_ids"]:
        raise MarketMemoryStoreError("source receipt index differs from packet")
    if artifact_hashes != clean_receipt["source_artifact_sha256s"]:
        raise MarketMemoryStoreError("source artifact index differs from packet")
    if missing_ids != clean_receipt["missing_feature_ids"]:
        raise MarketMemoryStoreError("missingness index differs from packet")
    domain_hash = sha256(_canonical_bytes(validated["domain_coverage"])).hexdigest()
    if domain_hash != clean_receipt["domain_coverage_sha256"]:
        raise MarketMemoryStoreError("domain coverage digest differs from packet")
    return StoredMarketMemoryContext(validated, clean_receipt)


class FileAsKnownAtReader(market_memory.AsKnownAtReader):
    """Concrete exact reader over one immutable W1A file-store prefix."""

    def __init__(self, root: str | Path, *, mode: str = "operational_pit") -> None:
        self.root = validate_store_root(root)
        if mode != "operational_pit":
            raise MarketMemoryQueryError(
                "W1A reader supports operational_pit captures only"
            )
        self.mode = mode

    def read_stored_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> StoredMarketMemoryContext:
        query, _event_dt, _cutoff_dt = _normalize_query(
            subject=subject,
            event_time=event_time,
            as_known_at=as_known_at,
            mode=self.mode,
            reject_future_cutoff=True,
        )
        query_id = _query_id(query)
        state = _load_store_state(self.root)
        entry = _generation_entry(state.generation, field="query_id", value=query_id)
        if entry is None:
            raise MarketMemoryContextNotFound(
                "exact query is absent from the complete active generation"
            )
        receipt, receipt_body = _read_canonical_object(
            _query_path(self.root, query_id),
            limit=_MAX_RECEIPT_BYTES,
            label="Market Memory exact-query receipt",
        )
        clean_receipt = _validate_capture_receipt(receipt)
        if clean_receipt["query_id"] != query_id:
            raise MarketMemoryStoreError("query receipt identity mismatch")
        if _capture_entry(clean_receipt) != entry:
            raise MarketMemoryStoreError("query receipt differs from generation index")
        context_receipt, context_body = _read_canonical_object(
            _context_path(self.root, clean_receipt["context_id"]),
            limit=_MAX_RECEIPT_BYTES,
            label="Market Memory context receipt",
        )
        if context_body != receipt_body or context_receipt != receipt:
            raise MarketMemoryStoreError("context and query receipts disagree")
        return _load_stored_from_receipt(
            self.root, clean_receipt, store_id=state.manifest["store_id"]
        )

    def read_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory.AsKnownAtContext:
        return self.read_stored_as_known_at(
            subject=subject,
            event_time=event_time,
            as_known_at=as_known_at,
        ).packet

    def read_stored_context_id(self, context_id: str) -> StoredMarketMemoryContext:
        # Validate the identifier before consulting the store so malformed input
        # is a 400 while a well-formed absence can be proven against HEAD.
        _context_path(self.root, context_id)
        state = _load_store_state(self.root)
        entry = _generation_entry(
            state.generation, field="context_id", value=context_id
        )
        if entry is None:
            raise MarketMemoryContextNotFound(
                "context is absent from the complete active generation"
            )
        context_receipt, context_body = _read_canonical_object(
            _context_path(self.root, context_id),
            limit=_MAX_RECEIPT_BYTES,
            label="Market Memory context receipt",
        )
        clean_receipt = _validate_capture_receipt(context_receipt)
        if _capture_entry(clean_receipt) != entry:
            raise MarketMemoryStoreError(
                "context receipt differs from generation index"
            )
        query_receipt, query_body = _read_canonical_object(
            _query_path(self.root, clean_receipt["query_id"]),
            limit=_MAX_RECEIPT_BYTES,
            label="Market Memory exact-query receipt",
        )
        if query_body != context_body or query_receipt != context_receipt:
            raise MarketMemoryStoreError(
                "context is not published by its query receipt"
            )
        if clean_receipt["context_id"] != context_id:
            raise MarketMemoryStoreError("context receipt identity mismatch")
        return _load_stored_from_receipt(
            self.root, clean_receipt, store_id=state.manifest["store_id"]
        )


def capture_context(
    root: str | Path, packet: Mapping[str, Any]
) -> StoredMarketMemoryContext:
    """Persist one contemporaneous operational packet through the sole writer.

    ``captured_at`` is deliberately sourced from the process clock and has no
    caller override.  This prevents a later historical job from laundering
    source-free missingness into an apparently operational packet.
    """

    captured_at = _utc_now().astimezone(timezone.utc)
    validated = _validate_capture_candidate(packet, admit_new=True)
    packet_digest, packet_body = _packet_sha256(validated)
    store = validate_store_root(root)
    uninitialized = not (
        _store_manifest_path(store).exists()
        or _head_path(store).exists()
        or _safe_store_path(store, "generations").exists()
    )
    if uninitialized:
        _require_contemporaneous_capture(validated, captured_at=captured_at)
    _mkdir_durable(store)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    lock_descriptor = os.open(store, directory_flags)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load_store(store)
        receipt = _build_capture_receipt(
            validated,
            store_id=state.manifest["store_id"],
            packet_sha256=packet_digest,
            captured_at=captured_at,
        )
        receipt_body = _canonical_bytes(receipt)
        if len(receipt_body) > _MAX_RECEIPT_BYTES:
            raise MarketMemoryCaptureError(
                "capture receipt exceeds its safe size bound"
            )
        active_entry = _generation_entry(
            state.generation, field="query_id", value=receipt["query_id"]
        )
        if active_entry is not None:
            if (
                active_entry["packet_sha256"] != packet_digest
                or active_entry["context_id"] != validated["context_id"]
            ):
                raise MarketMemoryCaptureError(
                    "operational query already has a different immutable capture"
                )
            return FileAsKnownAtReader(store).read_stored_as_known_at(
                subject=validated["subject"],
                event_time=validated["clocks"]["event_time"],
                as_known_at=validated["clocks"]["as_known_at"],
            )

        query_path = _query_path(store, receipt["query_id"])
        if query_path.exists() or query_path.is_symlink():
            existing, _existing_body = _read_canonical_object(
                query_path,
                limit=_MAX_RECEIPT_BYTES,
                label="existing exact-query receipt",
            )
            clean_existing = _validate_capture_receipt(existing)
            if (
                clean_existing["packet_sha256"] != packet_digest
                or clean_existing["context_id"] != validated["context_id"]
                or clean_existing["query_id"] != receipt["query_id"]
                or clean_existing["store_id"] != state.manifest["store_id"]
            ):
                raise MarketMemoryCaptureError(
                    "operational query already has a different immutable capture"
                )
            receipt = clean_existing
            receipt_body = _canonical_bytes(clean_existing)

        context_path = _context_path(store, validated["context_id"])
        if context_path.exists() or context_path.is_symlink():
            existing_context, existing_context_body = _read_canonical_object(
                context_path,
                limit=_MAX_RECEIPT_BYTES,
                label="existing context receipt",
            )
            clean_existing = _validate_capture_receipt(existing_context)
            if (
                clean_existing["packet_sha256"] != packet_digest
                or clean_existing["context_id"] != validated["context_id"]
                or clean_existing["query_id"] != receipt["query_id"]
                or clean_existing["store_id"] != state.manifest["store_id"]
            ):
                raise MarketMemoryCaptureError("immutable context receipt collision")
            _load_stored_from_receipt(
                store,
                clean_existing,
                store_id=state.manifest["store_id"],
            )
            # Recover a crash after object/context publication by committing the
            # original receipt as the query marker.  Its system capture clock is
            # retained instead of being rewritten by this retry.
            receipt = clean_existing
            receipt_body = existing_context_body
        else:
            _require_contemporaneous_capture(validated, captured_at=captured_at)

        if len(state.generation["captures"]) >= _MAX_GENERATION_CAPTURES:
            raise MarketMemoryCaptureError("W1A store generation is at its pilot bound")
        preview = _new_generation(
            store_id=state.manifest["store_id"],
            previous_generation_id=state.generation["generation_id"],
            captures=[
                *[dict(row) for row in state.generation["captures"]],
                _capture_entry(receipt),
            ],
        )
        if len(_canonical_bytes(preview)) > _MAX_GENERATION_BYTES:
            raise MarketMemoryCaptureError(
                "W1A store generation exceeds its byte bound"
            )

        _write_create_once(
            store,
            _object_path(store, packet_digest),
            packet_body,
            label="packet object",
        )
        _write_create_once(
            store,
            context_path,
            receipt_body,
            label="context receipt",
        )
        # Receipts remain invisible until the complete generation becomes HEAD.
        _write_create_once(
            store,
            query_path,
            receipt_body,
            label="exact-query receipt",
        )
        _publish_generation(store, state=state, receipt=receipt)
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)
    return FileAsKnownAtReader(store).read_stored_as_known_at(
        subject=validated["subject"],
        event_time=validated["clocks"]["event_time"],
        as_known_at=validated["clocks"]["as_known_at"],
    )


def default_store_root(repository_root: str | Path) -> Path:
    """Resolve the private/tracked W1A store, never a public ``site/`` path."""

    repository = Path(repository_root).expanduser().resolve()
    override = os.environ.get("MARKET_MEMORY_CONTEXT_STORE_DIR", "").strip()
    candidate = (
        Path(override).expanduser().resolve()
        if override
        else (
            Path("/var/lib/macro-market-memory/public")
            if repository == Path("/opt/macro")
            else repository / "data" / "neuralweb" / "market_memory" / "contexts"
        )
    )
    return validate_store_root(candidate, repository_root=repository)
