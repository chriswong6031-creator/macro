"""Immutable private snapshots for governed Fundamental Forensics queries.

Wave 3A makes a bounded :class:`MetricMatrix` receipt self-validating, but a
receipt only binds the fact the evaluator selected.  This module persists the
complete raw-ledger and filing-metadata input that produced that receipt so an
operator can later replay the selection without consulting mutable source,
registry, or API state.

The JSON matrix receipt is authoritative.  The Parquet file is a deliberately
flat convenience projection for future private scanners; it is never a second
receipt format.  All objects live in the existing private Research Store and
the mutable latest pointer advances only after every immutable object and the
manifest have been read back byte-for-byte.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import io
import json
import re
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from engine.research_vault.r2_store import StrictReadStore

from .query import (
    BitemporalPolicy,
    BitemporalMetricQueryEngine,
    FilingMetadata,
    HARD_MAX_TICKERS,
    MetricMatrix,
    QueryEntity,
    QueryValidationError,
)
from .raw_ledger import (
    HARD_MAX_RAW_LEDGER_EVENTS,
    RAW_LEDGER_SCHEMA,
    RawFactLedger,
    canonical_json,
    decimal_text,
    parse_utc,
    utc_text,
)


QUERY_SNAPSHOT_SCHEMA = "fundamental_forensics.query_snapshot/v1"
QUERY_SNAPSHOT_POINTER_SCHEMA = "fundamental_forensics.query_snapshot_pointer/v1"
QUERY_SNAPSHOT_METADATA_SCHEMA = "fundamental_forensics.query_snapshot_filing_metadata/v1"
QUERY_SNAPSHOT_PARQUET_SCHEMA = "fundamental_forensics.query_snapshot_cells/v1"
QUERY_SNAPSHOT_PREFIX = "fundamental_forensics/query-snapshots/v1"
# The generic private Store contract intentionally has no CAS/lease primitive.
# Wave 3B-A therefore admits a local operator lane only. A future distributed
# publisher must obtain an external R2/scheduler lease or conditional-write
# primitive before it calls this module; the process-local lock below cannot
# make cross-process publication monotonic.
QUERY_SNAPSHOT_PUBLICATION_CONTRACT = "single_writer_operator_only"

_SNAPSHOT_RE = re.compile(r"^ffqs_[a-f0-9]{64}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_OBJECT_ROLES = (
    "matrix_json",
    "ledger_json",
    "filing_metadata_json",
    "cells_parquet",
)
_CONTENT_TYPES_BY_ROLE = {
    "matrix_json": "application/json",
    "ledger_json": "application/json",
    "filing_metadata_json": "application/json",
    "cells_parquet": "application/vnd.apache.parquet",
}
_METADATA_KEYS = frozenset(
    {
        "schema",
        "accession",
        "document_id",
        "source_body_sha256",
        "available_at",
        "form",
        "filed_at",
        "content_sha256",
    }
)

# These are snapshot-admission ceilings, not product quotas.  They keep a
# single operator action bounded even when it is handed an otherwise valid
# raw-ledger object with unusually large text facts.
HARD_MAX_SNAPSHOT_LEDGER_EVENTS = HARD_MAX_RAW_LEDGER_EVENTS
HARD_MAX_SNAPSHOT_MATRIX_BYTES = 128 * 1024 * 1024
HARD_MAX_SNAPSHOT_LEDGER_BYTES = 512 * 1024 * 1024
HARD_MAX_SNAPSHOT_METADATA_BYTES = 128 * 1024 * 1024
HARD_MAX_SNAPSHOT_PARQUET_BYTES = 256 * 1024 * 1024
HARD_MAX_SNAPSHOT_TOTAL_BYTES = 1024 * 1024 * 1024
HARD_MAX_SNAPSHOT_METADATA_ENTRIES = HARD_MAX_RAW_LEDGER_EVENTS
HARD_MAX_SNAPSHOT_MANIFEST_BYTES = 1024 * 1024
HARD_MAX_SNAPSHOT_PARQUET_DECODED_BYTES = 128 * 1024 * 1024

_ROLE_BYTE_LIMITS = {
    "matrix_json": HARD_MAX_SNAPSHOT_MATRIX_BYTES,
    "ledger_json": HARD_MAX_SNAPSHOT_LEDGER_BYTES,
    "filing_metadata_json": HARD_MAX_SNAPSHOT_METADATA_BYTES,
    "cells_parquet": HARD_MAX_SNAPSHOT_PARQUET_BYTES,
}
_PUBLISH_LOCK = RLock()


class QuerySnapshotError(RuntimeError):
    """A private query snapshot cannot be prepared, published, or trusted."""


@dataclass(frozen=True)
class QuerySnapshotPointer:
    """The only mutable snapshot object, strictly bound to one manifest."""

    snapshot_id: str
    manifest_key: str
    query_hash: str
    published_at: datetime | str
    schema: str = QUERY_SNAPSHOT_POINTER_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != QUERY_SNAPSHOT_POINTER_SCHEMA:
            raise QuerySnapshotError("unsupported query snapshot pointer")
        snapshot_id = _validate_snapshot_id(self.snapshot_id)
        if self.manifest_key != _manifest_key(snapshot_id):
            raise QuerySnapshotError("query snapshot pointer manifest key is invalid")
        if not isinstance(self.query_hash, str) or not _SHA256_RE.fullmatch(self.query_hash):
            raise QuerySnapshotError("query snapshot pointer query_hash is invalid")
        object.__setattr__(self, "published_at", _utc(self.published_at, field="pointer.published_at"))

    @classmethod
    def from_snapshot(cls, snapshot: "QuerySnapshot") -> "QuerySnapshotPointer":
        if not isinstance(snapshot, QuerySnapshot):
            raise TypeError("snapshot must be QuerySnapshot")
        return cls(
            snapshot_id=snapshot.snapshot_id,
            manifest_key=snapshot.manifest_key,
            query_hash=snapshot.query_hash,
            published_at=snapshot.published_at,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QuerySnapshotPointer":
        raw = _strict_json_object(
            value,
            field="query snapshot pointer",
            required=frozenset({"schema", "snapshot_id", "manifest_key", "query_hash", "published_at"}),
        )
        return cls(**raw)

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": self.schema,
            "snapshot_id": self.snapshot_id,
            "manifest_key": self.manifest_key,
            "query_hash": self.query_hash,
            "published_at": utc_text(self.published_at) or "",
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")


@dataclass(frozen=True)
class QuerySnapshotArtifact:
    """One immutable content-addressed object bound by a snapshot manifest."""

    role: str
    object_key: str
    sha256: str
    byte_length: int
    content_type: str

    def __post_init__(self) -> None:
        if self.role not in _OBJECT_ROLES:
            raise QuerySnapshotError("unsupported snapshot artifact role")
        _validate_key(self.object_key)
        if not _SHA256_RE.fullmatch(self.sha256):
            raise QuerySnapshotError("snapshot artifact digest is invalid")
        if self.object_key != _object_key(self.sha256):
            raise QuerySnapshotError("snapshot artifact key does not bind digest")
        if isinstance(self.byte_length, bool) or not isinstance(self.byte_length, int) or self.byte_length < 0:
            raise QuerySnapshotError("snapshot artifact byte_length is invalid")
        if self.content_type != _CONTENT_TYPES_BY_ROLE[self.role]:
            raise QuerySnapshotError("snapshot artifact content_type does not match its role")
        if self.byte_length > _ROLE_BYTE_LIMITS[self.role]:
            raise QuerySnapshotError("snapshot artifact exceeds its role byte safety limit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "object_key": self.object_key,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "content_type": self.content_type,
        }


@dataclass(frozen=True)
class PreparedQuerySnapshot:
    """Fully validated snapshot bytes awaiting private-store publication."""

    snapshot_id: str
    manifest_key: str
    manifest: Mapping[str, Any]
    artifacts: tuple[QuerySnapshotArtifact, ...]
    payloads: Mapping[str, bytes]
    matrix: MetricMatrix
    ledger: RawFactLedger
    filing_metadata: Mapping[str, FilingMetadata]

    def __post_init__(self) -> None:
        _validate_snapshot_id(self.snapshot_id)
        if self.manifest_key != _manifest_key(self.snapshot_id):
            raise QuerySnapshotError("prepared snapshot manifest key is invalid")
        if not isinstance(self.matrix, MetricMatrix):
            raise TypeError("prepared snapshot matrix must be MetricMatrix")
        if not isinstance(self.ledger, RawFactLedger):
            raise TypeError("prepared snapshot ledger must be RawFactLedger")
        if not isinstance(self.artifacts, tuple) or tuple(item.role for item in self.artifacts) != _OBJECT_ROLES:
            raise QuerySnapshotError("prepared snapshot artifacts are not canonical")
        if not isinstance(self.payloads, Mapping):
            raise TypeError("prepared snapshot payloads must be a mapping")
        for artifact in self.artifacts:
            payload = self.payloads.get(artifact.role)
            if not isinstance(payload, bytes):
                raise QuerySnapshotError("prepared snapshot artifact payload is missing")
            if len(payload) != artifact.byte_length or sha256(payload).hexdigest() != artifact.sha256:
                raise QuerySnapshotError("prepared snapshot artifact payload mismatch")
        _validate_manifest(self.manifest)
        if self.manifest.get("snapshot_id") != self.snapshot_id:
            raise QuerySnapshotError("prepared snapshot id does not match manifest")
        if self.manifest.get("objects") != [item.to_dict() for item in self.artifacts]:
            raise QuerySnapshotError("prepared snapshot manifest objects do not match artifact payloads")
        _validate_manifest_matrix_binding(self.manifest, self.matrix)
        if self.payloads["matrix_json"] != self.matrix.to_json_bytes():
            raise QuerySnapshotError("prepared snapshot matrix payload does not match matrix")
        if self.payloads["ledger_json"] != canonical_json(self.ledger.to_dict()).encode("utf-8"):
            raise QuerySnapshotError("prepared snapshot ledger payload does not match ledger")
        if _decode_frozen_metadata(self.payloads["filing_metadata_json"], self.ledger) != self.filing_metadata:
            raise QuerySnapshotError("prepared snapshot filing metadata payload does not match metadata")


@dataclass(frozen=True)
class QuerySnapshot:
    """A verified immutable query snapshot loaded from the private store."""

    snapshot_id: str
    manifest_key: str
    manifest: Mapping[str, Any]
    matrix: MetricMatrix
    ledger: RawFactLedger
    filing_metadata: Mapping[str, FilingMetadata]
    cells: tuple[Mapping[str, Any], ...]

    @property
    def query_hash(self) -> str:
        return self.matrix.query_hash

    @property
    def published_at(self) -> datetime:
        parsed = parse_utc(self.manifest["clocks"]["published_at"], field_name="snapshot.published_at")
        if parsed is None:  # pragma: no cover - manifest validation requires it.
            raise QuerySnapshotError("snapshot published_at is missing")
        return parsed


def _utc(value: str | datetime, *, field: str) -> datetime:
    try:
        parsed = parse_utc(value, field_name=field)
    except ValueError as exc:
        raise QuerySnapshotError(str(exc)) from exc
    if parsed is None:
        raise QuerySnapshotError(f"{field} is required")
    return parsed


def _validate_snapshot_id(value: str) -> str:
    if not isinstance(value, str) or not _SNAPSHOT_RE.fullmatch(value):
        raise QuerySnapshotError("invalid query snapshot id")
    return value


def _relative_key(value: str) -> str:
    if not isinstance(value, str) or not value or not value.startswith(QUERY_SNAPSHOT_PREFIX + "/"):
        raise QuerySnapshotError("snapshot key is outside the owned prefix")
    if len(value) > 1024 or "\\" in value or "\x00" in value or "?" in value or "#" in value:
        raise QuerySnapshotError("snapshot key is unsafe")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise QuerySnapshotError("snapshot key is unsafe")
    return value


def _validate_key(value: str) -> str:
    return _relative_key(value)


def _object_key(digest: str) -> str:
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise QuerySnapshotError("content digest must be lowercase SHA-256 hex")
    return f"{QUERY_SNAPSHOT_PREFIX}/objects/sha256/{digest[:2]}/{digest}.bin"


def _manifest_key(snapshot_id: str) -> str:
    return f"{QUERY_SNAPSHOT_PREFIX}/manifests/{_validate_snapshot_id(snapshot_id)}.json"


def _latest_key() -> str:
    return f"{QUERY_SNAPSHOT_PREFIX}/latest.json"


def _artifact(role: str, payload: bytes, *, content_type: str) -> QuerySnapshotArtifact:
    digest = sha256(payload).hexdigest()
    return QuerySnapshotArtifact(
        role=role,
        object_key=_object_key(digest),
        sha256=digest,
        byte_length=len(payload),
        content_type=content_type,
    )


def _bounded_bytes(payload: bytes, *, maximum: int, field: str) -> bytes:
    if not isinstance(payload, bytes):
        raise QuerySnapshotError(f"{field} must be bytes")
    if len(payload) > maximum:
        raise QuerySnapshotError(f"{field} exceeds snapshot byte safety limit")
    return payload


def _strict_json_object(value: Any, *, field: str, required: frozenset[str]) -> dict[str, Any]:
    """Bound one exact-shape Mapping without materializing hostile input."""
    if not isinstance(value, Mapping):
        raise QuerySnapshotError(f"{field} must be an object")
    try:
        iterator = iter(value.items())
    except Exception as exc:  # noqa: BLE001 - hostile Mapping implementations.
        raise QuerySnapshotError(f"{field} cannot be iterated") from exc
    result: dict[str, Any] = {}
    for index in range(len(required) + 1):
        try:
            pair = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 - hostile Mapping implementations.
            raise QuerySnapshotError(f"{field} iterator failed") from exc
        if index == len(required):
            raise QuerySnapshotError(f"{field} shape is invalid")
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise QuerySnapshotError(f"{field} iterator yielded an invalid entry")
        key, item = pair
        if not isinstance(key, str) or key not in required or key in result:
            raise QuerySnapshotError(f"{field} shape is invalid")
        result[key] = item
    if len(result) != len(required):
        raise QuerySnapshotError(f"{field} shape is invalid")
    return result


def _frozen_metadata(
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]] | None,
) -> tuple[Mapping[str, FilingMetadata], bytes]:
    if filing_metadata is None:
        source: Mapping[str, FilingMetadata | Mapping[str, Any]] = {}
    elif isinstance(filing_metadata, Mapping):
        source = filing_metadata
    else:
        raise QuerySnapshotError("filing_metadata must be a mapping when supplied")
    event_by_id = {item.occurrence_id: item for item in ledger.events}
    entries: list[dict[str, Any]] = []
    try:
        iterator = iter(source.items())
    except Exception as exc:  # pragma: no cover - defensive hostile Mapping guard.
        raise QuerySnapshotError("filing_metadata cannot be iterated") from exc
    while True:
        try:
            pair = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            raise QuerySnapshotError("filing_metadata iterator failed") from exc
        if len(entries) >= HARD_MAX_SNAPSHOT_METADATA_ENTRIES:
            raise QuerySnapshotError("filing_metadata exceeds entry safety limit")
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise QuerySnapshotError("filing_metadata iterator yielded an invalid entry")
        occurrence_id, raw = pair
        if not isinstance(occurrence_id, str) or occurrence_id not in event_by_id:
            raise QuerySnapshotError("filing_metadata contains an unknown occurrence_id")
        if isinstance(raw, FilingMetadata):
            metadata = raw
        else:
            normalized = _strict_json_object(raw, field="filing_metadata entry", required=_METADATA_KEYS)
            try:
                metadata = FilingMetadata(**normalized)
            except (TypeError, ValueError, QueryValidationError) as exc:
                raise QuerySnapshotError(f"invalid filing_metadata entry: {exc}") from exc
        event = event_by_id[occurrence_id]
        if (
            metadata.accession != event.source.accession
            or metadata.document_id != event.source.document_id
            or metadata.source_body_sha256 != event.source.body_sha256
        ):
            raise QuerySnapshotError("filing_metadata does not bind its raw occurrence")
        entries.append({"occurrence_id": occurrence_id, "metadata": metadata.to_dict()})
    entries.sort(key=lambda item: item["occurrence_id"])
    if len({item["occurrence_id"] for item in entries}) != len(entries):
        raise QuerySnapshotError("filing_metadata contains duplicate occurrence_id entries")
    payload = {
        "schema": QUERY_SNAPSHOT_METADATA_SCHEMA,
        "entries": entries,
    }
    encoded = _bounded_bytes(
        canonical_json(payload).encode("utf-8"),
        maximum=HARD_MAX_SNAPSHOT_METADATA_BYTES,
        field="filing_metadata JSON",
    )
    frozen = MappingProxyType(
        {item["occurrence_id"]: FilingMetadata(**item["metadata"]) for item in entries}
    )
    return frozen, encoded


def _decode_frozen_metadata(payload: bytes, ledger: RawFactLedger) -> Mapping[str, FilingMetadata]:
    _bounded_bytes(payload, maximum=HARD_MAX_SNAPSHOT_METADATA_BYTES, field="filing_metadata JSON")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise QuerySnapshotError("filing_metadata snapshot is not UTF-8 JSON") from exc
    if not isinstance(raw, Mapping) or set(raw) != {"schema", "entries"} or raw.get("schema") != QUERY_SNAPSHOT_METADATA_SCHEMA:
        raise QuerySnapshotError("filing_metadata snapshot shape is invalid")
    entries = raw.get("entries")
    if not isinstance(entries, list) or len(entries) > HARD_MAX_SNAPSHOT_METADATA_ENTRIES:
        raise QuerySnapshotError("filing_metadata snapshot entries are invalid")
    event_by_id = {item.occurrence_id: item for item in ledger.events}
    decoded: dict[str, FilingMetadata] = {}
    canonical_entries: list[dict[str, Any]] = []
    for item in entries:
        parsed = _strict_json_object(
            item,
            field="filing_metadata snapshot entry",
            required=frozenset({"occurrence_id", "metadata"}),
        )
        occurrence_id = parsed["occurrence_id"]
        if not isinstance(occurrence_id, str) or occurrence_id not in event_by_id or occurrence_id in decoded:
            raise QuerySnapshotError("filing_metadata snapshot occurrence binding is invalid")
        metadata_raw = _strict_json_object(
            parsed["metadata"],
            field="filing_metadata snapshot metadata",
            required=_METADATA_KEYS,
        )
        try:
            metadata = FilingMetadata(**metadata_raw)
        except (TypeError, ValueError, QueryValidationError) as exc:
            raise QuerySnapshotError(f"invalid filing_metadata snapshot entry: {exc}") from exc
        event = event_by_id[occurrence_id]
        if (
            metadata.accession != event.source.accession
            or metadata.document_id != event.source.document_id
            or metadata.source_body_sha256 != event.source.body_sha256
        ):
            raise QuerySnapshotError("filing_metadata snapshot does not bind raw occurrence")
        decoded[occurrence_id] = metadata
        canonical_entries.append({"occurrence_id": occurrence_id, "metadata": metadata.to_dict()})
    canonical_entries.sort(key=lambda item: item["occurrence_id"])
    canonical = {
        "schema": QUERY_SNAPSHOT_METADATA_SCHEMA,
        "entries": canonical_entries,
    }
    if canonical_json(canonical).encode("utf-8") != payload:
        raise QuerySnapshotError("filing_metadata snapshot is not canonical")
    return MappingProxyType(decoded)


def _projection_row(matrix: MetricMatrix, cell: Any) -> dict[str, str | None]:
    provenance = cell.provenance
    period = cell.period.normalized
    return {
        "query_hash": matrix.query_hash,
        "root_cell_id": cell.cell_id,
        "ticker": cell.ticker,
        "entity_id": cell.entity_id,
        "metric_id": cell.metric_id,
        "period_kind": period.kind.value,
        "period_start": period.start.isoformat() if period.start else None,
        "period_end": period.end.isoformat(),
        "period_fiscal_year": str(period.fiscal_year) if period.fiscal_year is not None else None,
        "period_fiscal_quarter": str(period.fiscal_quarter) if period.fiscal_quarter is not None else None,
        "state": cell.state.value,
        "value": decimal_text(cell.value),
        "unit": cell.unit,
        "reason": cell.reason,
        "provenance_kind": provenance.kind.value,
        "accession": provenance.accession,
        "document_id": provenance.document_id,
        "concept_qname": provenance.concept_qname,
        "mapping_rule_id": provenance.mapping_rule_id,
        "mapping_rule_version": provenance.mapping_rule_version,
        "formula_rule_id": provenance.formula_rule_id,
        "formula_rule_version": provenance.formula_rule_version,
        "accepted_at": utc_text(provenance.accepted_at),
        "recorded_at": utc_text(provenance.recorded_at),
        "source_ready_at": utc_text(provenance.source_ready_at),
        "system_ready_at": utc_text(provenance.system_ready_at),
        "source_occurrence_ids_json": canonical_json(list(provenance.source_occurrence_ids)).rstrip("\n"),
        "dependency_cell_ids_json": canonical_json(list(provenance.dependency_cell_ids)).rstrip("\n"),
    }


def _projection_rows(matrix: MetricMatrix) -> tuple[dict[str, str | None], ...]:
    return tuple(_projection_row(matrix, cell) for cell in matrix.cells)


def _parquet_schema():
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover - dependency is pinned by requirements.
        raise QuerySnapshotError("pyarrow is required for query snapshots") from exc
    fields = (
        "query_hash",
        "root_cell_id",
        "ticker",
        "entity_id",
        "metric_id",
        "period_kind",
        "period_start",
        "period_end",
        "period_fiscal_year",
        "period_fiscal_quarter",
        "state",
        "value",
        "unit",
        "reason",
        "provenance_kind",
        "accession",
        "document_id",
        "concept_qname",
        "mapping_rule_id",
        "mapping_rule_version",
        "formula_rule_id",
        "formula_rule_version",
        "accepted_at",
        "recorded_at",
        "source_ready_at",
        "system_ready_at",
        "source_occurrence_ids_json",
        "dependency_cell_ids_json",
    )
    return pa.schema(
        [pa.field(name, pa.string(), nullable=True) for name in fields],
        metadata={b"schema": QUERY_SNAPSHOT_PARQUET_SCHEMA},
    )


def _encode_cells_parquet(matrix: MetricMatrix) -> tuple[bytes, tuple[dict[str, str | None], ...]]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - dependency is pinned by requirements.
        raise QuerySnapshotError("pyarrow is required for query snapshots") from exc
    rows = _projection_rows(matrix)
    schema = _parquet_schema()
    table = pa.Table.from_pylist(list(rows), schema=schema)
    buffer = io.BytesIO()
    pq.write_table(
        table,
        buffer,
        compression="zstd",
        use_dictionary=False,
        write_statistics=False,
        version="2.6",
        data_page_version="1.0",
    )
    return (
        _bounded_bytes(
            buffer.getvalue(),
            maximum=HARD_MAX_SNAPSHOT_PARQUET_BYTES,
            field="cells Parquet",
        ),
        rows,
    )


def _decode_cells_parquet(payload: bytes, matrix: MetricMatrix) -> tuple[Mapping[str, Any], ...]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - dependency is pinned by requirements.
        raise QuerySnapshotError("pyarrow is required for query snapshots") from exc
    _bounded_bytes(payload, maximum=HARD_MAX_SNAPSHOT_PARQUET_BYTES, field="cells Parquet")
    try:
        reader = pq.ParquetFile(io.BytesIO(payload))
        metadata = reader.metadata
        if metadata is None or metadata.num_row_groups != 1:
            raise QuerySnapshotError("cells Parquet must contain exactly one row group")
        if metadata.num_rows != len(matrix.cells):
            raise QuerySnapshotError("cells Parquet row count does not match matrix")
        decoded_bytes = sum(
            column.total_uncompressed_size
            for row_group in range(metadata.num_row_groups)
            for column in (
                metadata.row_group(row_group).column(index)
                for index in range(metadata.row_group(row_group).num_columns)
            )
        )
        if decoded_bytes < 0 or decoded_bytes > HARD_MAX_SNAPSHOT_PARQUET_DECODED_BYTES:
            raise QuerySnapshotError("cells Parquet decoded payload exceeds safety limit")
        if reader.schema_arrow != _parquet_schema():
            raise QuerySnapshotError("cells Parquet schema is invalid")
        table = reader.read()
    except QuerySnapshotError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize pyarrow parsing failures.
        raise QuerySnapshotError("cells Parquet cannot be decoded") from exc
    if table.schema != _parquet_schema():
        raise QuerySnapshotError("cells Parquet schema is invalid")
    if table.num_rows != len(matrix.cells):
        raise QuerySnapshotError("cells Parquet row count does not match matrix")
    rows = tuple(dict(item) for item in table.to_pylist())
    expected = _projection_rows(matrix)
    if rows != expected:
        raise QuerySnapshotError("cells Parquet rows do not match authoritative matrix")
    return tuple(MappingProxyType(dict(item)) for item in rows)


def _manifest_body(
    *,
    matrix: MetricMatrix,
    ledger: RawFactLedger,
    artifacts: Sequence[QuerySnapshotArtifact],
    computed_at: str,
    published_at: str,
) -> dict[str, Any]:
    return {
        "schema": QUERY_SNAPSHOT_SCHEMA,
        "prefix": QUERY_SNAPSHOT_PREFIX,
        "query_hash": matrix.query_hash,
        "governance_bundle_id": matrix.governance_bundle.content_id,
        "query_binding": {
            "selection": matrix.policy.selection.value,
            "entities": [item.to_dict() for item in matrix.entities],
        },
        "input_scope": {
            "ledger_scope": "committed_ledger_only",
            "sec_source_completeness_attested": False,
            "publication_contract": QUERY_SNAPSHOT_PUBLICATION_CONTRACT,
        },
        "ledger_schema": ledger.schema,
        "ledger_event_count": len(ledger.events),
        "clocks": {
            "source_snapshot_at": utc_text(matrix.policy.source_snapshot_at),
            "recorded_at": utc_text(matrix.policy.recorded_at),
            "computed_at": computed_at,
            "published_at": published_at,
        },
        "objects": [item.to_dict() for item in artifacts],
    }


def _snapshot_id(body: Mapping[str, Any]) -> str:
    return "ffqs_" + sha256(canonical_json(dict(body)).encode("utf-8")).hexdigest()


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    _validate_manifest(manifest)
    return _bounded_bytes(
        canonical_json(dict(manifest)).encode("utf-8"),
        maximum=HARD_MAX_SNAPSHOT_MANIFEST_BYTES,
        field="query snapshot manifest",
    )


def _validate_manifest(value: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "prefix",
        "snapshot_id",
        "query_hash",
        "governance_bundle_id",
        "query_binding",
        "input_scope",
        "ledger_schema",
        "ledger_event_count",
        "clocks",
        "objects",
    }
    manifest = _strict_json_object(value, field="query snapshot manifest", required=frozenset(required))
    if manifest["schema"] != QUERY_SNAPSHOT_SCHEMA or manifest["prefix"] != QUERY_SNAPSHOT_PREFIX:
        raise QuerySnapshotError("unsupported query snapshot manifest")
    snapshot_id = _validate_snapshot_id(manifest["snapshot_id"])
    if not isinstance(manifest["query_hash"], str) or not _SHA256_RE.fullmatch(manifest["query_hash"]):
        raise QuerySnapshotError("query snapshot manifest query_hash is invalid")
    if not isinstance(manifest["governance_bundle_id"], str) or not _SHA256_RE.fullmatch(manifest["governance_bundle_id"]):
        raise QuerySnapshotError("query snapshot manifest governance bundle id is invalid")
    query_binding = _strict_json_object(
        manifest["query_binding"],
        field="query snapshot manifest query_binding",
        required=frozenset({"selection", "entities"}),
    )
    try:
        BitemporalPolicy(query_binding["selection"])
    except (TypeError, ValueError) as exc:
        raise QuerySnapshotError("query snapshot manifest selection policy is invalid") from exc
    raw_entities = query_binding["entities"]
    if (
        not isinstance(raw_entities, list)
        or not raw_entities
        or len(raw_entities) > HARD_MAX_TICKERS
    ):
        raise QuerySnapshotError("query snapshot manifest entity membership is invalid")
    parsed_entities: list[QueryEntity] = []
    for raw_entity in raw_entities:
        entity = _strict_json_object(
            raw_entity,
            field="query snapshot manifest entity",
            required=frozenset({"ticker", "entity_id"}),
        )
        try:
            parsed_entities.append(QueryEntity(**entity))
        except (TypeError, ValueError, QueryValidationError) as exc:
            raise QuerySnapshotError("query snapshot manifest entity membership is invalid") from exc
    if [item.to_dict() for item in sorted(parsed_entities, key=lambda item: (item.ticker, item.entity_id))] != raw_entities:
        raise QuerySnapshotError("query snapshot manifest entity membership is not canonical")
    if len({item.ticker for item in parsed_entities}) != len(parsed_entities) or len(
        {item.entity_id for item in parsed_entities}
    ) != len(parsed_entities):
        raise QuerySnapshotError("query snapshot manifest entity membership is not unique")
    scope = _strict_json_object(
        manifest["input_scope"],
        field="query snapshot manifest input_scope",
        required=frozenset(
            {"ledger_scope", "sec_source_completeness_attested", "publication_contract"}
        ),
    )
    if (
        scope["ledger_scope"] != "committed_ledger_only"
        or scope["sec_source_completeness_attested"] is not False
        or scope["publication_contract"] != QUERY_SNAPSHOT_PUBLICATION_CONTRACT
    ):
        raise QuerySnapshotError("query snapshot manifest input scope is unsupported")
    if manifest["ledger_schema"] != RAW_LEDGER_SCHEMA:
        raise QuerySnapshotError("query snapshot manifest raw ledger schema is invalid")
    count = manifest["ledger_event_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > HARD_MAX_SNAPSHOT_LEDGER_EVENTS:
        raise QuerySnapshotError("query snapshot manifest ledger event count is invalid")
    clocks = _strict_json_object(
        manifest["clocks"],
        field="query snapshot manifest clocks",
        required=frozenset({"source_snapshot_at", "recorded_at", "computed_at", "published_at"}),
    )
    parsed_clocks = {name: _utc(value, field=f"snapshot.{name}") for name, value in clocks.items()}
    if any(clocks[name] != utc_text(value) for name, value in parsed_clocks.items()):
        raise QuerySnapshotError("query snapshot manifest clocks are not UTC-normalized")
    if parsed_clocks["computed_at"] < max(parsed_clocks["source_snapshot_at"], parsed_clocks["recorded_at"]):
        raise QuerySnapshotError("query snapshot computed_at predates its query cutoffs")
    if parsed_clocks["published_at"] < parsed_clocks["computed_at"]:
        raise QuerySnapshotError("query snapshot published_at predates computed_at")
    raw_objects = manifest["objects"]
    if not isinstance(raw_objects, list) or len(raw_objects) != len(_OBJECT_ROLES):
        raise QuerySnapshotError("query snapshot manifest object count is invalid")
    artifacts: list[QuerySnapshotArtifact] = []
    for item in raw_objects:
        parsed = _strict_json_object(
            item,
            field="query snapshot manifest object",
            required=frozenset({"role", "object_key", "sha256", "byte_length", "content_type"}),
        )
        artifacts.append(QuerySnapshotArtifact(**parsed))
    if tuple(item.role for item in artifacts) != _OBJECT_ROLES:
        raise QuerySnapshotError("query snapshot manifest object order is not canonical")
    if len({item.object_key for item in artifacts}) != len(artifacts):
        raise QuerySnapshotError("query snapshot manifest objects must use unique keys")
    total = sum(item.byte_length for item in artifacts)
    if total > HARD_MAX_SNAPSHOT_TOTAL_BYTES:
        raise QuerySnapshotError("query snapshot manifest exceeds aggregate byte limit")
    body = dict(manifest)
    body.pop("snapshot_id")
    expected = _snapshot_id(body)
    if snapshot_id != expected:
        raise QuerySnapshotError("query snapshot manifest identity mismatch")


def _decode_manifest(payload: bytes) -> dict[str, Any]:
    _bounded_bytes(payload, maximum=HARD_MAX_SNAPSHOT_MANIFEST_BYTES, field="query snapshot manifest")
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise QuerySnapshotError("query snapshot manifest is not UTF-8 JSON") from exc
    if not isinstance(manifest, Mapping):
        raise QuerySnapshotError("query snapshot manifest must be an object")
    _validate_manifest(manifest)
    if _manifest_bytes(manifest) != payload:
        raise QuerySnapshotError("query snapshot manifest is not canonical")
    return dict(manifest)


def _validate_manifest_matrix_binding(manifest: Mapping[str, Any], matrix: MetricMatrix) -> None:
    """Bind the compact manifest query declaration to the authoritative receipt."""
    binding = manifest["query_binding"]
    if binding["selection"] != matrix.policy.selection.value:
        raise QuerySnapshotError("query snapshot manifest selection does not match matrix")
    if binding["entities"] != [item.to_dict() for item in matrix.entities]:
        raise QuerySnapshotError("query snapshot manifest entity membership does not match matrix")
    clocks = manifest["clocks"]
    if clocks["source_snapshot_at"] != utc_text(matrix.policy.source_snapshot_at):
        raise QuerySnapshotError("query snapshot manifest source cutoff does not match matrix")
    if clocks["recorded_at"] != utc_text(matrix.policy.recorded_at):
        raise QuerySnapshotError("query snapshot manifest recorded cutoff does not match matrix")
    scope = manifest["input_scope"]
    if (
        scope["ledger_scope"] != "committed_ledger_only"
        or scope["sec_source_completeness_attested"] is not False
        or scope["publication_contract"] != QUERY_SNAPSHOT_PUBLICATION_CONTRACT
    ):
        raise QuerySnapshotError("query snapshot manifest input scope is unsupported")


def _pointer_bytes(snapshot: QuerySnapshot) -> bytes:
    return QuerySnapshotPointer.from_snapshot(snapshot).to_json_bytes()


def _decode_pointer(payload: bytes) -> QuerySnapshotPointer:
    _bounded_bytes(payload, maximum=16 * 1024, field="query snapshot pointer")
    try:
        pointer = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise QuerySnapshotError("query snapshot pointer is not UTF-8 JSON") from exc
    try:
        result = QuerySnapshotPointer.from_dict(pointer)
    except (TypeError, ValueError, QuerySnapshotError) as exc:
        raise QuerySnapshotError(f"query snapshot pointer is invalid: {exc}") from exc
    if result.to_json_bytes() != payload:
        raise QuerySnapshotError("query snapshot pointer is not canonical")
    return result


def _read_required(store: StrictReadStore, key: str) -> bytes:
    _validate_key(key)
    try:
        payload = store.get_bytes_strict(key)
    except Exception as exc:  # noqa: BLE001 - normalize strict adapter failures.
        raise QuerySnapshotError(f"private snapshot read failed for {key}") from exc
    if not isinstance(payload, bytes):
        raise QuerySnapshotError(f"private snapshot object unavailable: {key}")
    return payload


def _put_verified_immutable(store: StrictReadStore, artifact: QuerySnapshotArtifact, payload: bytes) -> None:
    existing = _read_optional(store, artifact.object_key)
    if existing is not None:
        if existing != payload:
            raise QuerySnapshotError("immutable snapshot object collision")
    else:
        try:
            written = store.put_bytes(artifact.object_key, payload, content_type=artifact.content_type)
        except Exception as exc:  # noqa: BLE001 - normalize store failures.
            raise QuerySnapshotError(f"private snapshot write failed for {artifact.object_key}") from exc
        if written is not True:
            raise QuerySnapshotError(f"private snapshot write failed for {artifact.object_key}")
    echoed = _read_required(store, artifact.object_key)
    if echoed != payload or sha256(echoed).hexdigest() != artifact.sha256:
        raise QuerySnapshotError("private snapshot object read-back mismatch")


def _read_optional(store: StrictReadStore, key: str) -> bytes | None:
    _validate_key(key)
    try:
        payload = store.get_bytes_strict(key)
    except Exception as exc:  # noqa: BLE001 - normalize store failures.
        raise QuerySnapshotError(f"private snapshot read failed for {key}") from exc
    if payload is not None and not isinstance(payload, bytes):
        raise QuerySnapshotError("private snapshot store returned non-bytes")
    return payload


def _publish_pointer(store: StrictReadStore, snapshot: QuerySnapshot) -> None:
    pointer_key = _latest_key()
    prior = _read_optional(store, pointer_key)
    payload = _pointer_bytes(snapshot)
    if prior is not None:
        prior_pointer = _decode_pointer(prior)
        if prior_pointer.snapshot_id == snapshot.snapshot_id:
            if prior != payload:
                raise QuerySnapshotError("latest pointer disagrees with immutable snapshot")
            return
        if snapshot.published_at <= prior_pointer.published_at:
            raise QuerySnapshotError("stale snapshot cannot rewind latest pointer")
    try:
        written = store.put_bytes(pointer_key, payload, content_type="application/json")
    except Exception as exc:  # noqa: BLE001
        raise QuerySnapshotError("private snapshot latest pointer write failed") from exc
    if written is not True:
        raise QuerySnapshotError("private snapshot latest pointer write failed")
    echoed = _read_optional(store, pointer_key)
    if echoed == payload:
        return
    # Best-effort rollback is safe in the single-writer operator lane.  If it
    # fails, callers still receive an error and must treat latest as uncertain.
    if prior is not None:
        try:
            store.put_bytes(pointer_key, prior, content_type="application/json")
        except Exception:  # pragma: no cover - failure remains surfaced below.
            pass
    raise QuerySnapshotError("private snapshot latest pointer read-back mismatch")


def _snapshot_readiness(matrix: MetricMatrix) -> datetime:
    values = [matrix.policy.source_snapshot_at, matrix.policy.recorded_at]
    seen: set[str] = set()
    for cell in matrix.cells:
        for node in cell.nodes:
            if node.cell_id in seen:
                continue
            seen.add(node.cell_id)
            values.extend(
                value
                for value in (node.provenance.source_ready_at, node.provenance.system_ready_at)
                if value is not None
            )
    return max(values)


def _replay_matrix(
    *,
    matrix: MetricMatrix,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata],
) -> MetricMatrix:
    """Re-run one receipt exclusively from its committed selection inputs."""
    try:
        engine = BitemporalMetricQueryEngine(
            ledger,
            matrix.governance_bundle,
            entities=matrix.entities,
            filing_metadata=filing_metadata,
        )
        replayed = engine.query_matrix(
            tickers=matrix.entities,
            metrics=matrix.metric_ids,
            periods=matrix.periods,
            policy=matrix.policy,
        )
    except (TypeError, ValueError, QueryValidationError) as exc:
        raise QuerySnapshotError(f"query snapshot replay failed: {exc}") from exc
    if replayed.to_json_bytes() != matrix.to_json_bytes():
        raise QuerySnapshotError("query snapshot replay does not match authoritative matrix")
    return replayed


def prepare_query_snapshot(
    *,
    matrix: MetricMatrix,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]] | None = None,
    computed_at: str | datetime,
    published_at: str | datetime,
) -> PreparedQuerySnapshot:
    """Prepare one self-contained, bounded, immutable query snapshot.

    The caller supplies the *complete* ledger loaded by the query engine, not
    a selected-fact subset.  This is the boundary that makes selection replay
    possible.  SEC-source attestation is deliberately a later Wave 3B lane.
    """
    if not isinstance(matrix, MetricMatrix):
        raise TypeError("matrix must be MetricMatrix")
    if not isinstance(ledger, RawFactLedger):
        raise TypeError("ledger must be RawFactLedger")
    if len(ledger.events) > HARD_MAX_SNAPSHOT_LEDGER_EVENTS:
        raise QuerySnapshotError("raw ledger exceeds snapshot event safety limit")
    normalized_computed = _utc(computed_at, field="computed_at")
    normalized_published = _utc(published_at, field="published_at")
    readiness = _snapshot_readiness(matrix)
    if normalized_computed < readiness:
        raise QuerySnapshotError("computed_at predates matrix source/system readiness")
    if normalized_published < normalized_computed:
        raise QuerySnapshotError("published_at predates computed_at")
    matrix_payload = _bounded_bytes(
        matrix.to_json_bytes(), maximum=HARD_MAX_SNAPSHOT_MATRIX_BYTES, field="matrix JSON"
    )
    try:
        decoded_matrix = MetricMatrix.from_dict(json.loads(matrix_payload.decode("utf-8")))
    except (UnicodeDecodeError, ValueError, QueryValidationError) as exc:
        raise QuerySnapshotError(f"matrix receipt cannot be snapshotted: {exc}") from exc
    if decoded_matrix.to_json_bytes() != matrix_payload:
        raise QuerySnapshotError("matrix receipt is not canonical")
    ledger_payload = _bounded_bytes(
        canonical_json(ledger.to_dict()).encode("utf-8"),
        maximum=HARD_MAX_SNAPSHOT_LEDGER_BYTES,
        field="raw ledger JSON",
    )
    frozen_metadata, metadata_payload = _frozen_metadata(ledger, filing_metadata)
    # Selection is proven against the full committed ledger before any object
    # is published.  This is intentionally separate from the Wave 3A receipt
    # graph check: a graph could be internally valid yet not be reproducible
    # from a caller-supplied ledger.
    _replay_matrix(matrix=matrix, ledger=ledger, filing_metadata=frozen_metadata)
    parquet_payload, _ = _encode_cells_parquet(matrix)
    artifacts = (
        _artifact("matrix_json", matrix_payload, content_type="application/json"),
        _artifact("ledger_json", ledger_payload, content_type="application/json"),
        _artifact("filing_metadata_json", metadata_payload, content_type="application/json"),
        _artifact("cells_parquet", parquet_payload, content_type="application/vnd.apache.parquet"),
    )
    computed_text = utc_text(normalized_computed) or ""
    published_text = utc_text(normalized_published) or ""
    body = _manifest_body(
        matrix=matrix,
        ledger=ledger,
        artifacts=artifacts,
        computed_at=computed_text,
        published_at=published_text,
    )
    snapshot_id = _snapshot_id(body)
    manifest = {"snapshot_id": snapshot_id, **body}
    manifest_bytes = _manifest_bytes(manifest)
    # Force an immediate local decode before any private-store write.  This
    # catches a malformed canonical object before it can create an orphan.
    if _decode_manifest(manifest_bytes) != manifest:
        raise QuerySnapshotError("query snapshot manifest local verification failed")
    return PreparedQuerySnapshot(
        snapshot_id=snapshot_id,
        manifest_key=_manifest_key(snapshot_id),
        manifest=MappingProxyType(manifest),
        artifacts=artifacts,
        payloads=MappingProxyType(
            {
                "matrix_json": matrix_payload,
                "ledger_json": ledger_payload,
                "filing_metadata_json": metadata_payload,
                "cells_parquet": parquet_payload,
            }
        ),
        matrix=matrix,
        ledger=ledger,
        filing_metadata=frozen_metadata,
    )


def _snapshot_from_manifest(store: StrictReadStore, *, snapshot_id: str) -> QuerySnapshot:
    manifest_key = _manifest_key(snapshot_id)
    manifest = _decode_manifest(_read_required(store, manifest_key))
    if manifest["snapshot_id"] != snapshot_id:
        raise QuerySnapshotError("query snapshot manifest does not match requested id")
    artifacts = tuple(QuerySnapshotArtifact(**item) for item in manifest["objects"])
    payload_by_role: dict[str, bytes] = {}
    for artifact in artifacts:
        payload = _bounded_bytes(
            _read_required(store, artifact.object_key),
            maximum=_ROLE_BYTE_LIMITS[artifact.role],
            field=f"snapshot {artifact.role}",
        )
        if len(payload) != artifact.byte_length or sha256(payload).hexdigest() != artifact.sha256:
            raise QuerySnapshotError("query snapshot object digest or byte length mismatch")
        payload_by_role[artifact.role] = payload
    try:
        matrix = MetricMatrix.from_dict(json.loads(payload_by_role["matrix_json"].decode("utf-8")))
    except (UnicodeDecodeError, ValueError, QueryValidationError) as exc:
        raise QuerySnapshotError(f"query snapshot matrix receipt is invalid: {exc}") from exc
    if matrix.to_json_bytes() != payload_by_role["matrix_json"]:
        raise QuerySnapshotError("query snapshot matrix receipt is not canonical")
    if matrix.query_hash != manifest["query_hash"] or matrix.governance_bundle.content_id != manifest["governance_bundle_id"]:
        raise QuerySnapshotError("query snapshot matrix does not match manifest")
    _validate_manifest_matrix_binding(manifest, matrix)
    try:
        ledger = RawFactLedger.from_json_bytes(payload_by_role["ledger_json"])
    except (ValueError, TypeError) as exc:
        raise QuerySnapshotError(f"query snapshot raw ledger is invalid: {exc}") from exc
    if ledger.schema != manifest["ledger_schema"] or len(ledger.events) != manifest["ledger_event_count"]:
        raise QuerySnapshotError("query snapshot raw ledger does not match manifest")
    metadata = _decode_frozen_metadata(payload_by_role["filing_metadata_json"], ledger)
    cells = _decode_cells_parquet(payload_by_role["cells_parquet"], matrix)
    readiness = _snapshot_readiness(matrix)
    computed = _utc(manifest["clocks"]["computed_at"], field="snapshot.computed_at")
    if computed < readiness:
        raise QuerySnapshotError("query snapshot computed_at predates matrix readiness")
    return QuerySnapshot(
        snapshot_id=snapshot_id,
        manifest_key=manifest_key,
        manifest=MappingProxyType(manifest),
        matrix=matrix,
        ledger=ledger,
        filing_metadata=metadata,
        cells=cells,
    )


def publish_query_snapshot(store: StrictReadStore, prepared: PreparedQuerySnapshot) -> QuerySnapshot:
    """Publish verified objects under the single-writer operator contract.

    Publication is serialized only within this Python process.  A scheduled or
    multi-process R2 writer must hold an external lease/CAS before entering;
    the generic strict-read store API cannot provide distributed monotonicity.
    """
    if not isinstance(prepared, PreparedQuerySnapshot):
        raise TypeError("prepared must be PreparedQuerySnapshot")
    if not isinstance(store, StrictReadStore):
        raise QuerySnapshotError("query snapshot publication requires a StrictReadStore adapter")
    with _PUBLISH_LOCK:
        for artifact in prepared.artifacts:
            _put_verified_immutable(store, artifact, prepared.payloads[artifact.role])
        manifest_payload = _manifest_bytes(prepared.manifest)
        # The manifest is not a role-bearing data artifact, but it uses the same
        # private immutable readback discipline.  Its key is intentionally bound
        # to snapshot identity rather than its own hash.
        existing = _read_optional(store, prepared.manifest_key)
        if existing is not None:
            if existing != manifest_payload:
                raise QuerySnapshotError("immutable query snapshot manifest collision")
        else:
            try:
                written = store.put_bytes(
                    prepared.manifest_key,
                    manifest_payload,
                    content_type="application/json",
                )
            except Exception as exc:  # noqa: BLE001
                raise QuerySnapshotError("private query snapshot manifest write failed") from exc
            if written is not True:
                raise QuerySnapshotError("private query snapshot manifest write failed")
        if _read_required(store, prepared.manifest_key) != manifest_payload:
            raise QuerySnapshotError("private query snapshot manifest read-back mismatch")
        snapshot = verify_query_snapshot(store, snapshot_id=prepared.snapshot_id)
        _publish_pointer(store, snapshot)
        return snapshot


def load_query_snapshot(store: StrictReadStore, *, snapshot_id: str | None = None) -> QuerySnapshot:
    """Load and validate one immutable snapshot by ID or the private latest pointer."""
    if not isinstance(store, StrictReadStore):
        raise QuerySnapshotError("query snapshot load requires a StrictReadStore adapter")
    if snapshot_id is None:
        pointer = _decode_pointer(_read_required(store, _latest_key()))
        requested_id = pointer.snapshot_id
        snapshot = _snapshot_from_manifest(store, snapshot_id=requested_id)
        if (
            snapshot.manifest_key != pointer.manifest_key
            or snapshot.query_hash != pointer.query_hash
            or snapshot.published_at != pointer.published_at
        ):
            raise QuerySnapshotError("query snapshot latest pointer does not bind manifest")
        return snapshot
    return _snapshot_from_manifest(store, snapshot_id=_validate_snapshot_id(snapshot_id))


def verify_query_snapshot(store: StrictReadStore, *, snapshot_id: str | None = None) -> QuerySnapshot:
    """Verify objects and the frozen-engine replay against the matrix receipt."""
    snapshot = load_query_snapshot(store, snapshot_id=snapshot_id)
    replay_query_snapshot(snapshot)
    return snapshot


def replay_query_snapshot(snapshot: QuerySnapshot) -> MetricMatrix:
    """Re-evaluate a snapshot using only its committed ledger and governance.

    ``BitemporalMetricQueryEngine`` accepts a frozen ``GovernanceBundle`` in
    Wave 3B.  That support is intentionally required here: replaying against a
    current registry could make a later mapping mutation rewrite the past.
    """
    if not isinstance(snapshot, QuerySnapshot):
        raise TypeError("snapshot must be QuerySnapshot")
    return _replay_matrix(
        matrix=snapshot.matrix,
        ledger=snapshot.ledger,
        filing_metadata=snapshot.filing_metadata,
    )


__all__ = [
    "HARD_MAX_SNAPSHOT_LEDGER_BYTES",
    "HARD_MAX_SNAPSHOT_LEDGER_EVENTS",
    "HARD_MAX_SNAPSHOT_MANIFEST_BYTES",
    "HARD_MAX_SNAPSHOT_MATRIX_BYTES",
    "HARD_MAX_SNAPSHOT_METADATA_BYTES",
    "HARD_MAX_SNAPSHOT_METADATA_ENTRIES",
    "HARD_MAX_SNAPSHOT_PARQUET_BYTES",
    "HARD_MAX_SNAPSHOT_PARQUET_DECODED_BYTES",
    "HARD_MAX_SNAPSHOT_TOTAL_BYTES",
    "PreparedQuerySnapshot",
    "QUERY_SNAPSHOT_METADATA_SCHEMA",
    "QUERY_SNAPSHOT_PARQUET_SCHEMA",
    "QUERY_SNAPSHOT_POINTER_SCHEMA",
    "QUERY_SNAPSHOT_PREFIX",
    "QUERY_SNAPSHOT_PUBLICATION_CONTRACT",
    "QUERY_SNAPSHOT_SCHEMA",
    "QuerySnapshot",
    "QuerySnapshotArtifact",
    "QuerySnapshotError",
    "QuerySnapshotPointer",
    "load_query_snapshot",
    "prepare_query_snapshot",
    "publish_query_snapshot",
    "replay_query_snapshot",
    "verify_query_snapshot",
]
