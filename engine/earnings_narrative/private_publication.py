"""Private, receipt-bound publication for member earnings evidence.

The public Earnings Wire builder writes redacted HTML into ``site/`` and writes
the member continuation into an operator-selected staging directory outside the
repository.  This module validates that staging tree, publishes immutable
content-addressed objects to the existing private Research Vault store, and
moves one small private pointer only after every object has been read back.

No object key or payload produced here is a browser URL.  Browser reads go
through the authenticated ``/api/earnings/v1/records/{slug}`` route, which uses
server-side Research Vault credentials and enforces ``site_full`` first.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Mapping

from engine.earnings_narrative.context_packets import (
    canonical_json_bytes,
    validate_context_manifest,
    validate_context_packet_at_cutoff,
)
from engine.research_vault.r2_store import StrictBoundedReadStore, Store


PRIVATE_PREFIX = "earnings_wire_private/v1"
POINTER_KEY = f"{PRIVATE_PREFIX}/current.json"
POINTER_SCHEMA = "earnings.private_pointer/v1"
MANIFEST_SCHEMA = "earnings.private_manifest/v1"
RECORD_SCHEMA = "earnings.tier_payload/v1"
RECORD_STAGE_DIR = "records"
CONTEXT_STAGE_DIR = "context"
CONTEXT_MANIFEST_NAME = "latest.json"

MAX_POINTER_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_CONTEXT_PACKET_BYTES = 512 * 1024
MAX_RECORDS = 10_000
MAX_CONTEXT_PACKETS = 10_000
IDEMPOTENT_READ_WORKERS = 8

_SLUG_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,120}\Z")
_TICKER_RE = re.compile(r"\A[A-Z0-9.\-]{1,16}\Z")
_GENERATION_RE = re.compile(r"\Aearnpriv_[a-f0-9]{32}\Z")
_SHA_RE = re.compile(r"\A[a-f0-9]{64}\Z")
_OBJECT_KEY_RE = re.compile(
    rf"\A{re.escape(PRIVATE_PREFIX)}/objects/sha256/[a-f0-9]{{2}}/[a-f0-9]{{64}}\.json\Z"
)
_MANIFEST_KEY_RE = re.compile(
    rf"\A{re.escape(PRIVATE_PREFIX)}/manifests/earnpriv_[a-f0-9]{{32}}\.json\Z"
)
_UNSAFE_HTML_RE = re.compile(
    r"<(?:script|iframe|object|embed|link|meta)\b|\bon[a-z]+\s*=|javascript\s*:",
    re.IGNORECASE,
)
_PUBLISH_LOCK = threading.Lock()


class EarningsPrivatePublicationError(RuntimeError):
    """Private staging, publication, or read verification failed closed."""


class EarningsPrivateRecordNotFound(EarningsPrivatePublicationError):
    """A syntactically valid slug is not present in the current generation."""


@dataclass(frozen=True)
class PrivateArtifact:
    """One immutable object and the receipt advertised by the manifest."""

    role: str
    identity: str
    object_key: str
    sha256: str
    byte_length: int
    maximum_bytes: int

    def receipt(self) -> dict[str, Any]:
        return {
            "object_key": self.object_key,
            "sha256": self.sha256,
            "bytes": self.byte_length,
        }


@dataclass(frozen=True)
class PreparedPrivatePublication:
    """Locally verified immutable generation ready for private-store publish."""

    generation_id: str
    manifest_key: str
    manifest: Mapping[str, Any]
    manifest_bytes: bytes
    artifacts: tuple[PrivateArtifact, ...]
    payloads: Mapping[str, bytes]


def _strict_object(value: Any, *, keys: frozenset[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise EarningsPrivatePublicationError(f"{name} fields mismatch")
    return value


def _json_object(body: bytes, *, maximum: int, name: str) -> dict[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > maximum:
        raise EarningsPrivatePublicationError(f"{name} exceeds its safe size bound")
    try:
        value = json.loads(
            body.decode("utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EarningsPrivatePublicationError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != body:
        raise EarningsPrivatePublicationError(f"{name} is not canonical JSON")
    return value


def validate_slug(value: str) -> str:
    if not isinstance(value, str) or not _SLUG_RE.fullmatch(value):
        raise EarningsPrivatePublicationError("invalid earnings record slug")
    return value


def validate_ticker(value: str) -> str:
    if not isinstance(value, str) or not _TICKER_RE.fullmatch(value):
        raise EarningsPrivatePublicationError("invalid earnings context ticker")
    return value


def _safe_fragment(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_RECORD_BYTES:
        raise EarningsPrivatePublicationError(f"private record {field} is invalid")
    if _UNSAFE_HTML_RE.search(value):
        raise EarningsPrivatePublicationError(f"private record {field} contains active content")
    return value


def validate_private_record(value: object, *, expected_slug: str | None = None) -> dict[str, Any]:
    record = _strict_object(
        value,
        keys=frozenset(
            {
                "schema",
                "page",
                "slug",
                "required_tier",
                "public_facts",
                "locked_facts",
                "facts_html",
                "receipt_rows_html",
            }
        ),
        name="private earnings record",
    )
    slug = validate_slug(record.get("slug"))
    if expected_slug is not None and slug != validate_slug(expected_slug):
        raise EarningsPrivatePublicationError("private record slug does not match its identity")
    if (
        record.get("schema") != RECORD_SCHEMA
        or record.get("page") != "earnings_wire_article"
        or record.get("required_tier") != "essential"
    ):
        raise EarningsPrivatePublicationError("private record contract is invalid")
    for field in ("public_facts", "locked_facts"):
        count = record.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > 10_000:
            raise EarningsPrivatePublicationError(f"private record {field} is invalid")
    if record["locked_facts"] < 1:
        raise EarningsPrivatePublicationError("private record must contain a member continuation")
    _safe_fragment(record.get("facts_html"), field="facts_html")
    _safe_fragment(record.get("receipt_rows_html"), field="receipt_rows_html")
    return dict(record)


def _stage_file(root: Path, relative: Path, *, maximum: int, name: str) -> bytes:
    root = root.resolve()
    path = root / relative
    # The staging tree is produced locally, but a no-symlink boundary prevents a
    # caller from turning the publisher into an arbitrary-file reader.
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise EarningsPrivatePublicationError(f"{name} cannot traverse a symlink")
        cursor = cursor.parent
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        size = resolved.stat().st_size
        if not resolved.is_file() or size <= 0 or size > maximum:
            raise EarningsPrivatePublicationError(f"{name} exceeds its safe size bound")
        body = resolved.read_bytes()
    except EarningsPrivatePublicationError:
        raise
    except (OSError, ValueError) as exc:
        raise EarningsPrivatePublicationError(f"{name} is unavailable") from exc
    if len(body) != size:
        raise EarningsPrivatePublicationError(f"{name} changed during read")
    return body


def _artifact(role: str, identity: str, body: bytes, *, maximum: int) -> PrivateArtifact:
    digest = sha256(body).hexdigest()
    return PrivateArtifact(
        role=role,
        identity=identity,
        object_key=f"{PRIVATE_PREFIX}/objects/sha256/{digest[:2]}/{digest}.json",
        sha256=digest,
        byte_length=len(body),
        maximum_bytes=maximum,
    )


def _generation_id(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned["generation_id"] = "earnpriv_" + ("0" * 32)
    return "earnpriv_" + sha256(canonical_json_bytes(unsigned)).hexdigest()[:32]


def _validate_receipt(value: Any, *, name: str) -> Mapping[str, Any]:
    receipt = _strict_object(
        value,
        keys=frozenset({"object_key", "sha256", "bytes"}),
        name=name,
    )
    if (
        not isinstance(receipt.get("object_key"), str)
        or not _OBJECT_KEY_RE.fullmatch(receipt["object_key"])
        or not isinstance(receipt.get("sha256"), str)
        or not _SHA_RE.fullmatch(receipt["sha256"])
        or receipt["object_key"].split("/")[-1] != f"{receipt['sha256']}.json"
        or isinstance(receipt.get("bytes"), bool)
        or not isinstance(receipt.get("bytes"), int)
        or receipt["bytes"] <= 0
    ):
        raise EarningsPrivatePublicationError(f"{name} is invalid")
    return receipt


def validate_private_manifest(value: object) -> dict[str, Any]:
    manifest = _strict_object(
        value,
        keys=frozenset(
            {
                "schema",
                "generation_id",
                "published_at",
                "source",
                "record_count",
                "ticker_count",
                "records",
                "context",
            }
        ),
        name="private earnings manifest",
    )
    generation_id = manifest.get("generation_id")
    if (
        manifest.get("schema") != MANIFEST_SCHEMA
        or not isinstance(generation_id, str)
        or not _GENERATION_RE.fullmatch(generation_id)
        or generation_id != _generation_id(manifest)
    ):
        raise EarningsPrivatePublicationError("private earnings generation identity is invalid")
    if not isinstance(manifest.get("published_at"), str) or len(manifest["published_at"]) > 64:
        raise EarningsPrivatePublicationError("private earnings publication clock is invalid")
    source = _strict_object(
        manifest.get("source"),
        keys=frozenset({"wire_manifest_id", "source_generation_id", "source_manifest_sha256"}),
        name="private earnings source",
    )
    if any(not isinstance(source.get(key), str) or not source[key] for key in source):
        raise EarningsPrivatePublicationError("private earnings source binding is invalid")
    if not _SHA_RE.fullmatch(source["source_manifest_sha256"]):
        raise EarningsPrivatePublicationError("private earnings source digest is invalid")
    records = manifest.get("records")
    context = manifest.get("context")
    if not isinstance(records, Mapping) or not 0 <= len(records) <= MAX_RECORDS:
        raise EarningsPrivatePublicationError("private earnings record catalog is invalid")
    if (
        isinstance(manifest.get("record_count"), bool)
        or manifest.get("record_count") != len(records)
    ):
        raise EarningsPrivatePublicationError("private earnings record count is invalid")
    for slug, receipt in records.items():
        validate_slug(slug)
        _validate_receipt(receipt, name=f"private record receipt {slug}")
    context = _strict_object(
        context,
        keys=frozenset({"manifest", "objects"}),
        name="private earnings context catalog",
    )
    context_objects = context.get("objects")
    if not isinstance(context_objects, Mapping) or len(context_objects) > MAX_CONTEXT_PACKETS:
        raise EarningsPrivatePublicationError("private earnings context objects are invalid")
    if (
        isinstance(manifest.get("ticker_count"), bool)
        or manifest.get("ticker_count") != len(context_objects)
    ):
        raise EarningsPrivatePublicationError("private earnings ticker count is invalid")
    _validate_receipt(context.get("manifest"), name="private context manifest receipt")
    for ticker, receipt in context_objects.items():
        validate_ticker(ticker)
        _validate_receipt(receipt, name=f"private context receipt {ticker}")
    return dict(manifest)


def prepare_private_publication(stage_dir: str | Path) -> PreparedPrivatePublication:
    """Validate a complete off-repo staging tree and freeze one generation."""
    root = Path(stage_dir).resolve()
    records_dir = root / RECORD_STAGE_DIR
    context_dir = root / CONTEXT_STAGE_DIR
    if not records_dir.is_dir() or not context_dir.is_dir():
        raise EarningsPrivatePublicationError("private earnings staging tree is incomplete")

    record_paths = sorted(records_dir.glob("*.json"))
    if not 0 <= len(record_paths) <= MAX_RECORDS:
        raise EarningsPrivatePublicationError("private earnings staging record count is invalid")
    artifacts: list[PrivateArtifact] = []
    payloads: dict[str, bytes] = {}
    record_receipts: dict[str, dict[str, Any]] = {}
    expected_paths: set[Path] = set()
    for path in record_paths:
        slug = validate_slug(path.stem)
        relative = Path(RECORD_STAGE_DIR) / path.name
        body = _stage_file(root, relative, maximum=MAX_RECORD_BYTES, name=f"record {slug}")
        record = _json_object(body, maximum=MAX_RECORD_BYTES, name=f"record {slug}")
        validate_private_record(record, expected_slug=slug)
        artifact = _artifact("record", slug, body, maximum=MAX_RECORD_BYTES)
        artifacts.append(artifact)
        payloads[artifact.object_key] = body
        record_receipts[slug] = artifact.receipt()
        expected_paths.add((root / relative).resolve())

    context_manifest_relative = Path(CONTEXT_STAGE_DIR) / CONTEXT_MANIFEST_NAME
    context_manifest_body = _stage_file(
        root,
        context_manifest_relative,
        maximum=MAX_CONTEXT_MANIFEST_BYTES,
        name="context manifest",
    )
    context_manifest = _json_object(
        context_manifest_body,
        maximum=MAX_CONTEXT_MANIFEST_BYTES,
        name="context manifest",
    )
    try:
        validate_context_manifest(context_manifest)
    except Exception as exc:  # noqa: BLE001 - normalize contract boundary
        raise EarningsPrivatePublicationError("private context manifest contract is invalid") from exc
    context_manifest_artifact = _artifact(
        "context_manifest",
        "latest",
        context_manifest_body,
        maximum=MAX_CONTEXT_MANIFEST_BYTES,
    )
    artifacts.append(context_manifest_artifact)
    payloads[context_manifest_artifact.object_key] = context_manifest_body
    expected_paths.add((root / context_manifest_relative).resolve())

    context_receipts: dict[str, dict[str, Any]] = {}
    context_objects = context_manifest.get("objects")
    if not isinstance(context_objects, Mapping) or len(context_objects) > MAX_CONTEXT_PACKETS:
        raise EarningsPrivatePublicationError("private context manifest object catalog is invalid")
    for ticker, advertised in sorted(context_objects.items()):
        validate_ticker(ticker)
        if not isinstance(advertised, Mapping):
            raise EarningsPrivatePublicationError(f"context receipt {ticker} is invalid")
        relative_name = advertised.get("path")
        if not isinstance(relative_name, str) or relative_name != f"{ticker.lower()}.json":
            raise EarningsPrivatePublicationError(f"context path {ticker} is unsafe")
        relative = Path(CONTEXT_STAGE_DIR) / relative_name
        body = _stage_file(
            root,
            relative,
            maximum=MAX_CONTEXT_PACKET_BYTES,
            name=f"context packet {ticker}",
        )
        if (
            isinstance(advertised.get("bytes"), bool)
            or advertised.get("bytes") != len(body)
            or advertised.get("sha256") != sha256(body).hexdigest()
        ):
            raise EarningsPrivatePublicationError(f"context receipt {ticker} mismatch")
        packet = _json_object(
            body,
            maximum=MAX_CONTEXT_PACKET_BYTES,
            name=f"context packet {ticker}",
        )
        try:
            validate_context_packet_at_cutoff(
                packet,
                knowledge_cutoff=context_manifest["knowledge_cutoff"],
            )
        except Exception as exc:  # noqa: BLE001
            raise EarningsPrivatePublicationError(f"context packet {ticker} is invalid") from exc
        if packet.get("context_id") != advertised.get("context_id") or (
            not isinstance(packet.get("event"), Mapping)
            or packet["event"].get("ticker") != ticker
        ):
            raise EarningsPrivatePublicationError(f"context packet {ticker} identity mismatch")
        artifact = _artifact("context_packet", ticker, body, maximum=MAX_CONTEXT_PACKET_BYTES)
        artifacts.append(artifact)
        payloads[artifact.object_key] = body
        context_receipts[ticker] = artifact.receipt()
        expected_paths.add((root / relative).resolve())

    actual_paths = {path.resolve() for path in root.rglob("*") if path.is_file()}
    if actual_paths != expected_paths:
        raise EarningsPrivatePublicationError("private earnings staging tree contains unexpected files")

    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "generation_id": "earnpriv_" + ("0" * 32),
        "published_at": str(context_manifest["knowledge_cutoff"]),
        "source": {
            "wire_manifest_id": str(context_manifest["source"]["wire_manifest_id"]),
            "source_generation_id": str(context_manifest["source"]["generation_id"]),
            "source_manifest_sha256": str(context_manifest["source"]["manifest_sha256"]),
        },
        "record_count": len(record_receipts),
        "ticker_count": len(context_receipts),
        "records": {slug: record_receipts[slug] for slug in sorted(record_receipts)},
        "context": {
            "manifest": context_manifest_artifact.receipt(),
            "objects": {ticker: context_receipts[ticker] for ticker in sorted(context_receipts)},
        },
    }
    manifest["generation_id"] = _generation_id(manifest)
    validate_private_manifest(manifest)
    manifest_bytes = canonical_json_bytes(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise EarningsPrivatePublicationError("private earnings manifest exceeds its safe size bound")
    manifest_key = f"{PRIVATE_PREFIX}/manifests/{manifest['generation_id']}.json"
    return PreparedPrivatePublication(
        generation_id=str(manifest["generation_id"]),
        manifest_key=manifest_key,
        manifest=MappingProxyType(manifest),
        manifest_bytes=manifest_bytes,
        artifacts=tuple(artifacts),
        payloads=MappingProxyType(payloads),
    )


def _bounded_read(store: Store, key: str, *, maximum: int) -> bytes | None:
    if not isinstance(store, StrictBoundedReadStore):
        raise EarningsPrivatePublicationError("private earnings store lacks bounded strict reads")
    try:
        body = store.get_bytes_strict_bounded(key, maximum)
    except Exception as exc:  # noqa: BLE001
        raise EarningsPrivatePublicationError("private earnings object read failed") from exc
    if body is not None and not isinstance(body, bytes):
        raise EarningsPrivatePublicationError("private earnings store returned non-bytes")
    return body


def _put_verified(store: Store, *, key: str, body: bytes, maximum: int) -> None:
    existing = _bounded_read(store, key, maximum=maximum)
    if existing is not None and existing != body:
        raise EarningsPrivatePublicationError("immutable private earnings object collision")
    if existing is None:
        try:
            written = store.put_bytes(key, body, content_type="application/json")
        except Exception as exc:  # noqa: BLE001
            raise EarningsPrivatePublicationError("private earnings object write failed") from exc
        if written is not True:
            raise EarningsPrivatePublicationError("private earnings object write failed")
    echoed = _bounded_read(store, key, maximum=maximum)
    if echoed != body or sha256(echoed or b"").hexdigest() != sha256(body).hexdigest():
        raise EarningsPrivatePublicationError("private earnings object read-back mismatch")


def _pointer_for(prepared: PreparedPrivatePublication) -> dict[str, Any]:
    return {
        "schema": POINTER_SCHEMA,
        "generation_id": prepared.generation_id,
        "manifest_key": prepared.manifest_key,
        "manifest_sha256": sha256(prepared.manifest_bytes).hexdigest(),
        "manifest_bytes": len(prepared.manifest_bytes),
        "published_at": str(prepared.manifest["published_at"]),
    }


def validate_private_pointer(value: object) -> dict[str, Any]:
    pointer = _strict_object(
        value,
        keys=frozenset(
            {
                "schema",
                "generation_id",
                "manifest_key",
                "manifest_sha256",
                "manifest_bytes",
                "published_at",
            }
        ),
        name="private earnings pointer",
    )
    generation_id = pointer.get("generation_id")
    if (
        pointer.get("schema") != POINTER_SCHEMA
        or not isinstance(generation_id, str)
        or not _GENERATION_RE.fullmatch(generation_id)
        or pointer.get("manifest_key") != f"{PRIVATE_PREFIX}/manifests/{generation_id}.json"
        or not _MANIFEST_KEY_RE.fullmatch(str(pointer.get("manifest_key") or ""))
        or not isinstance(pointer.get("manifest_sha256"), str)
        or not _SHA_RE.fullmatch(pointer["manifest_sha256"])
        or isinstance(pointer.get("manifest_bytes"), bool)
        or not isinstance(pointer.get("manifest_bytes"), int)
        or not 1 <= pointer["manifest_bytes"] <= MAX_MANIFEST_BYTES
        or not isinstance(pointer.get("published_at"), str)
    ):
        raise EarningsPrivatePublicationError("private earnings pointer is invalid")
    return dict(pointer)


def _validated_prepared_payloads(
    prepared: PreparedPrivatePublication,
) -> tuple[tuple[PrivateArtifact, bytes], ...]:
    """Return the frozen payloads after rechecking their immutable receipts.

    ``PreparedPrivatePublication`` is normally only made by
    :func:`prepare_private_publication`, but publication is a security boundary
    and must not trust a caller-provided dataclass merely because it has the
    right type.  The same validation feeds both the normal promotion path and
    the idempotent replay path below.
    """
    verified: list[tuple[PrivateArtifact, bytes]] = []
    for artifact in prepared.artifacts:
        body = prepared.payloads.get(artifact.object_key)
        if not isinstance(body, bytes):
            raise EarningsPrivatePublicationError("prepared private payload is missing")
        if len(body) != artifact.byte_length or sha256(body).hexdigest() != artifact.sha256:
            raise EarningsPrivatePublicationError("prepared private payload receipt mismatch")
        verified.append((artifact, body))
    return tuple(verified)


def _bounded_artifact_read(store: Store, artifact: PrivateArtifact) -> bytes | None:
    """One immutable-object replay read, kept separate for ordered executor.map."""
    return _bounded_read(store, artifact.object_key, maximum=artifact.maximum_bytes)


def _existing_exact_publication(
    store: Store,
    prepared: PreparedPrivatePublication,
    *,
    verified_payloads: tuple[tuple[PrivateArtifact, bytes], ...],
) -> dict[str, Any] | None:
    """Prove that *prepared* is already the complete current generation.

    A matching pointer is intentionally insufficient: it can reference a
    partial or corrupt immutable closure after an interrupted operator run.
    The fast path therefore requires canonical exact bytes for the pointer and
    manifest, a complete bounded read of every immutable artifact, and a final
    pointer reread to catch a concurrent promotion.  ``None`` means an object
    is authoritatively absent and permits the normal pointer-last repair path;
    a mismatched immutable byte string fails closed rather than overwriting it.
    """
    expected_pointer = _pointer_for(prepared)
    expected_pointer_bytes = canonical_json_bytes(expected_pointer)
    pointer_body = _bounded_read(store, POINTER_KEY, maximum=MAX_POINTER_BYTES)
    if pointer_body is None:
        return None
    pointer = validate_private_pointer(
        _json_object(pointer_body, maximum=MAX_POINTER_BYTES, name="prior private pointer")
    )
    if pointer["generation_id"] != prepared.generation_id:
        return None
    if pointer_body != expected_pointer_bytes or pointer != expected_pointer:
        raise EarningsPrivatePublicationError("private pointer disagrees with generation")

    manifest_body = _bounded_read(store, prepared.manifest_key, maximum=MAX_MANIFEST_BYTES)
    if manifest_body is None:
        return None
    if manifest_body != prepared.manifest_bytes:
        raise EarningsPrivatePublicationError("immutable private earnings manifest differs")
    manifest = validate_private_manifest(
        _json_object(manifest_body, maximum=MAX_MANIFEST_BYTES, name="private earnings manifest")
    )
    if manifest != dict(prepared.manifest):
        raise EarningsPrivatePublicationError("private earnings manifest replay mismatch")

    # Content addressing makes identical payloads share a key.  Read each key
    # only once while still requiring that every artifact advertised by this
    # generation is present and exact.  ``executor.map`` yields ordered
    # results, so a missing/mismatched receipt remains deterministic while the
    # remote IO is conservatively capped rather than serializing ~900 GETs.
    checked_keys: set[str] = set()
    unique_payloads: list[tuple[PrivateArtifact, bytes]] = []
    for artifact, expected_body in verified_payloads:
        if artifact.object_key in checked_keys:
            continue
        checked_keys.add(artifact.object_key)
        unique_payloads.append((artifact, expected_body))
    remote_bodies: tuple[bytes | None, ...] = ()
    if unique_payloads:
        worker_count = min(IDEMPOTENT_READ_WORKERS, len(unique_payloads))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="earnings-private-read") as pool:
            remote_bodies = tuple(
                pool.map(
                    _bounded_artifact_read,
                    (store for _artifact, _body in unique_payloads),
                    (artifact for artifact, _body in unique_payloads),
                )
            )
    for (_artifact, expected_body), remote_body in zip(unique_payloads, remote_bodies, strict=True):
        if remote_body is None:
            return None
        if remote_body != expected_body:
            raise EarningsPrivatePublicationError("immutable private earnings object differs")

    # The local mutex does not coordinate another runner/process.  A second
    # exact bounded read prevents a stale snapshot from being reported ready.
    if _bounded_read(store, POINTER_KEY, maximum=MAX_POINTER_BYTES) != expected_pointer_bytes:
        raise EarningsPrivatePublicationError("private pointer changed during idempotent replay")
    return expected_pointer


def publish_private_publication(
    store: Store,
    prepared: PreparedPrivatePublication,
) -> dict[str, Any]:
    """Publish objects and manifest, then advance the private pointer last."""
    if not isinstance(prepared, PreparedPrivatePublication):
        raise TypeError("prepared must be PreparedPrivatePublication")
    if not isinstance(store, Store) or not isinstance(store, StrictBoundedReadStore):
        raise EarningsPrivatePublicationError("private earnings publication requires a strict store")
    with _PUBLISH_LOCK:
        verified_payloads = _validated_prepared_payloads(prepared)
        ready = _existing_exact_publication(
            store,
            prepared,
            verified_payloads=verified_payloads,
        )
        if ready is not None:
            return ready
        for artifact, body in verified_payloads:
            _put_verified(
                store,
                key=artifact.object_key,
                body=body,
                maximum=artifact.maximum_bytes,
            )
        _put_verified(
            store,
            key=prepared.manifest_key,
            body=prepared.manifest_bytes,
            maximum=MAX_MANIFEST_BYTES,
        )
        pointer = _pointer_for(prepared)
        pointer_bytes = canonical_json_bytes(pointer)
        prior = _bounded_read(store, POINTER_KEY, maximum=MAX_POINTER_BYTES)
        if prior is not None:
            prior_pointer = validate_private_pointer(
                _json_object(prior, maximum=MAX_POINTER_BYTES, name="prior private pointer")
            )
            if prior_pointer["generation_id"] == prepared.generation_id:
                if prior != pointer_bytes:
                    raise EarningsPrivatePublicationError("private pointer disagrees with generation")
                return pointer
            if str(pointer["published_at"]) < str(prior_pointer["published_at"]):
                raise EarningsPrivatePublicationError("stale private publication cannot rewind current")
        try:
            written = store.put_bytes(POINTER_KEY, pointer_bytes, content_type="application/json")
        except Exception as exc:  # noqa: BLE001
            raise EarningsPrivatePublicationError("private earnings pointer write failed") from exc
        if written is not True:
            raise EarningsPrivatePublicationError("private earnings pointer write failed")
        echoed = _bounded_read(store, POINTER_KEY, maximum=MAX_POINTER_BYTES)
        if echoed != pointer_bytes:
            if prior is not None:
                try:
                    store.put_bytes(POINTER_KEY, prior, content_type="application/json")
                except Exception:  # pragma: no cover - original error remains authoritative
                    pass
            raise EarningsPrivatePublicationError("private earnings pointer read-back mismatch")
        # Replay the complete current closure after promotion.  This catches a
        # pointer/object mismatch before the workflow is allowed to publish its
        # corresponding public shells.
        loaded = load_private_manifest(store)
        if loaded != dict(prepared.manifest):
            raise EarningsPrivatePublicationError("private earnings publication replay mismatch")
        return pointer


def load_private_manifest(store: Store) -> dict[str, Any]:
    """Load the current private manifest through its pointer and exact receipt."""
    pointer_body = _bounded_read(store, POINTER_KEY, maximum=MAX_POINTER_BYTES)
    if pointer_body is None:
        raise EarningsPrivatePublicationError("private earnings pointer is unavailable")
    pointer = validate_private_pointer(
        _json_object(pointer_body, maximum=MAX_POINTER_BYTES, name="private earnings pointer")
    )
    manifest_body = _bounded_read(store, pointer["manifest_key"], maximum=MAX_MANIFEST_BYTES)
    if manifest_body is None:
        raise EarningsPrivatePublicationError("private earnings manifest is unavailable")
    if (
        len(manifest_body) != pointer["manifest_bytes"]
        or sha256(manifest_body).hexdigest() != pointer["manifest_sha256"]
    ):
        raise EarningsPrivatePublicationError("private earnings manifest receipt mismatch")
    manifest = validate_private_manifest(
        _json_object(manifest_body, maximum=MAX_MANIFEST_BYTES, name="private earnings manifest")
    )
    if (
        manifest["generation_id"] != pointer["generation_id"]
        or manifest["published_at"] != pointer["published_at"]
    ):
        raise EarningsPrivatePublicationError("private pointer does not bind its manifest")
    return manifest


def _load_receipted_object(
    store: Store,
    receipt: Mapping[str, Any],
    *,
    maximum: int,
    name: str,
) -> bytes:
    normalized = _validate_receipt(receipt, name=f"{name} receipt")
    if normalized["bytes"] > maximum:
        raise EarningsPrivatePublicationError(f"{name} exceeds its safe size bound")
    body = _bounded_read(store, normalized["object_key"], maximum=maximum)
    if body is None:
        raise EarningsPrivatePublicationError(f"{name} is unavailable")
    if len(body) != normalized["bytes"] or sha256(body).hexdigest() != normalized["sha256"]:
        raise EarningsPrivatePublicationError(f"{name} receipt mismatch")
    return body


def load_private_record(
    store: Store,
    slug: str,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one member record from the current private generation."""
    slug = validate_slug(slug)
    current = validate_private_manifest(manifest) if manifest is not None else load_private_manifest(store)
    receipt = current["records"].get(slug)
    if not isinstance(receipt, Mapping):
        raise EarningsPrivateRecordNotFound("earnings record is not covered")
    body = _load_receipted_object(
        store,
        receipt,
        maximum=MAX_RECORD_BYTES,
        name="private earnings record",
    )
    return validate_private_record(
        _json_object(body, maximum=MAX_RECORD_BYTES, name="private earnings record"),
        expected_slug=slug,
    )


def load_private_context_packet(
    store: Store,
    ticker: str,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Mapping[str, Any]]:
    """Return one exact-evidence context packet and both bound manifests.

    This is the server-side seam for Neural Web, Mastermind AI, and display-only
    Prophet annotations.  It never grants decision authority; the packet's own
    closed context contract is revalidated here.
    """
    ticker = validate_ticker(ticker)
    current = validate_private_manifest(manifest) if manifest is not None else load_private_manifest(store)
    context = current["context"]
    catalog_body = _load_receipted_object(
        store,
        context["manifest"],
        maximum=MAX_CONTEXT_MANIFEST_BYTES,
        name="private context manifest",
    )
    catalog = _json_object(
        catalog_body,
        maximum=MAX_CONTEXT_MANIFEST_BYTES,
        name="private context manifest",
    )
    try:
        validate_context_manifest(catalog)
    except Exception as exc:  # noqa: BLE001
        raise EarningsPrivatePublicationError("private context manifest contract is invalid") from exc
    catalog_source = catalog["source"]
    expected_source = {
        "wire_manifest_id": catalog_source["wire_manifest_id"],
        "source_generation_id": catalog_source["generation_id"],
        "source_manifest_sha256": catalog_source["manifest_sha256"],
    }
    if (
        current["published_at"] != catalog["knowledge_cutoff"]
        or current["source"] != expected_source
    ):
        raise EarningsPrivatePublicationError("private context catalogs disagree")
    advertised = catalog["objects"].get(ticker)
    receipt = context["objects"].get(ticker)
    if not isinstance(advertised, Mapping) or not isinstance(receipt, Mapping):
        raise EarningsPrivateRecordNotFound("earnings context ticker is not covered")
    body = _load_receipted_object(
        store,
        receipt,
        maximum=MAX_CONTEXT_PACKET_BYTES,
        name="private context packet",
    )
    if len(body) != advertised.get("bytes") or sha256(body).hexdigest() != advertised.get("sha256"):
        raise EarningsPrivatePublicationError("private context catalogs disagree")
    packet = _json_object(
        body,
        maximum=MAX_CONTEXT_PACKET_BYTES,
        name="private context packet",
    )
    try:
        validate_context_packet_at_cutoff(
            packet,
            knowledge_cutoff=catalog["knowledge_cutoff"],
        )
    except Exception as exc:  # noqa: BLE001
        raise EarningsPrivatePublicationError("private context packet contract is invalid") from exc
    if (
        packet.get("context_id") != advertised.get("context_id")
        or not isinstance(packet.get("event"), Mapping)
        or packet["event"].get("ticker") != ticker
    ):
        raise EarningsPrivatePublicationError("private context packet identity mismatch")
    return packet, catalog, receipt


__all__ = [
    "CONTEXT_STAGE_DIR",
    "EarningsPrivatePublicationError",
    "EarningsPrivateRecordNotFound",
    "MANIFEST_SCHEMA",
    "POINTER_KEY",
    "POINTER_SCHEMA",
    "PreparedPrivatePublication",
    "RECORD_SCHEMA",
    "RECORD_STAGE_DIR",
    "load_private_context_packet",
    "load_private_manifest",
    "load_private_record",
    "prepare_private_publication",
    "publish_private_publication",
    "validate_private_manifest",
    "validate_private_pointer",
    "validate_private_record",
    "validate_slug",
    "validate_ticker",
]
