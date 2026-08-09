"""Deterministic quarter catalogs and monotone publication for universal 13F data."""
from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from engine.research_vault.r2_store import (
    StrictBoundedReadStore,
    StrictConditionalWriteStore,
    VersionedBytes,
)

from .models import (
    CATALOG_ARTIFACT_ROLES,
    CATALOG_POINTER_SCHEMA,
    COVERAGE_SCHEMA,
    HOLDING_BUCKET_COUNT,
    HOLDING_BUCKET_ROLES,
    SOURCE_RECEIPTS_SCHEMA,
    CatalogClocks,
    CatalogCounts,
    CatalogGenerationManifest,
    CatalogPointer,
    Institutional13FError,
    StoredObject,
    canonical_json_bytes,
    catalog_manifest_key,
    catalog_pointer_key,
    content_object_key,
    decode_canonical_json,
    normalize_accession,
    normalize_cik,
    normalize_form,
    normalize_report_period,
    normalize_utc,
    utc_datetime,
    validate_identity,
    validate_sha256,
)
from .storage import (
    Institutional13FStorageError,
    create_verified_immutable,
    read_verified_object,
)

FILINGS_PARQUET_SCHEMA = "institutional_13f.filings_projection/v1"
HOLDINGS_PARQUET_SCHEMA = "institutional_13f.holdings_projection/v1"
MANAGER_RELATIONSHIPS_PARQUET_SCHEMA = (
    "institutional_13f.manager_relationships_projection/v1"
)
CATALOG_CORRECTION_SCHEMA = "institutional_13f.catalog_correction/v1"

HARD_MAX_CATALOG_MANIFEST_BYTES = 1024 * 1024
HARD_MAX_CATALOG_POINTER_BYTES = 16 * 1024
HARD_MAX_CATALOG_PARQUET_BYTES = 512 * 1024 * 1024
HARD_MAX_CATALOG_JSON_ARTIFACT_BYTES = 64 * 1024 * 1024
HARD_MAX_CATALOG_CELL_CHARS = 1024 * 1024

# name, logical type, nullable.  String clocks and decimal source tokens are
# deliberate: their exact normalized representation is portable across Arrow
# versions and does not silently round as-filed evidence.
_FILINGS_FIELDS = (
    ("accession", "string", False),
    ("filer_cik", "string", False),
    ("filer_name", "string", True),
    ("form", "string", False),
    ("filing_date", "string", True),
    ("accepted_at", "string", False),
    ("report_period", "string", False),
    ("report_type", "string", True),
    ("form13f_file_number", "string", True),
    ("is_amendment", "bool", False),
    ("amendment_number", "int32", True),
    ("amendment_type", "string", True),
    ("amends_accession", "string", True),
    ("lineage_state", "string", False),
    ("confidential_omitted", "bool", True),
    ("table_entry_total", "int64", True),
    ("table_value_total_usd", "int64", True),
    ("other_manager_count", "int64", True),
    ("source_receipt_id", "string", False),
    ("normalization_id", "string", True),
    ("raw_sha256", "string", False),
    ("first_seen_at", "string", False),
    ("retained_at", "string", False),
    ("parser_version", "string", False),
    ("quality_state", "string", False),
)

_HOLDINGS_FIELDS = (
    ("accession", "string", False),
    ("infotable_sk", "int64", False),
    ("name_of_issuer", "string", True),
    ("title_of_class", "string", True),
    ("cusip", "string", True),
    ("figi", "string", True),
    ("value_reported", "string", True),
    ("value_unit", "string", True),
    ("value_usd", "int64", True),
    ("ssh_prn_amt", "string", True),
    ("ssh_prn_type", "string", True),
    ("put_call", "string", True),
    ("investment_discretion", "string", True),
    ("other_manager", "string", True),
    ("voting_authority_sole", "int64", True),
    ("voting_authority_shared", "int64", True),
    ("voting_authority_none", "int64", True),
    ("row_hash", "string", False),
)

_MANAGER_FIELDS = (
    ("accession", "string", False),
    ("relationship_kind", "string", False),
    ("source_table", "string", False),
    ("manager_sequence", "int64", True),
    ("other_manager_sk", "int64", True),
    ("manager_cik", "string", True),
    ("manager_name", "string", True),
    ("form13f_file_number", "string", True),
    ("crd_number", "string", True),
    ("sec_file_number", "string", True),
)

FILINGS_COLUMNS = tuple(item[0] for item in _FILINGS_FIELDS)
HOLDINGS_COLUMNS = tuple(item[0] for item in _HOLDINGS_FIELDS)
MANAGER_RELATIONSHIP_COLUMNS = tuple(item[0] for item in _MANAGER_FIELDS)

_FIELDS_BY_ROLE = {
    "filings_parquet": _FILINGS_FIELDS,
    "holdings_parquet": _HOLDINGS_FIELDS,
    "manager_relationships_parquet": _MANAGER_FIELDS,
}
_PARQUET_SCHEMA_NAMES = {
    "filings_parquet": FILINGS_PARQUET_SCHEMA,
    "holdings_parquet": HOLDINGS_PARQUET_SCHEMA,
    "manager_relationships_parquet": MANAGER_RELATIONSHIPS_PARQUET_SCHEMA,
}
_PRIMARY_KEYS = {
    "filings_parquet": ("accession",),
    "holdings_parquet": ("accession", "infotable_sk"),
    "manager_relationships_parquet": (
        "accession", "source_table", "relationship_kind", "manager_sequence", "other_manager_sk"
    ),
}
_ROLE_BYTE_LIMITS = {
    "filings_parquet": HARD_MAX_CATALOG_PARQUET_BYTES,
    **{role: HARD_MAX_CATALOG_PARQUET_BYTES for role in HOLDING_BUCKET_ROLES},
    "manager_relationships_parquet": HARD_MAX_CATALOG_PARQUET_BYTES,
    "source_receipts_json": HARD_MAX_CATALOG_JSON_ARTIFACT_BYTES,
    "coverage_json": HARD_MAX_CATALOG_JSON_ARTIFACT_BYTES,
}


class Institutional13FCatalogError(Institutional13FError):
    """A quarter catalog failed validation, publication, or restoration."""


def _role_family(role: str) -> str:
    if role in HOLDING_BUCKET_ROLES:
        return "holdings_parquet"
    if role in _FIELDS_BY_ROLE:
        return role
    raise Institutional13FCatalogError(f"unsupported Parquet role: {role}")


def holding_bucket_for_accession(accession: str) -> int:
    """Return the stable 0..63 shard for all rows in one SEC accession."""
    normalized = normalize_accession(accession)
    return sha256(normalized.encode("ascii")).digest()[0] % HOLDING_BUCKET_COUNT


def holding_bucket_role(accession: str) -> str:
    return HOLDING_BUCKET_ROLES[holding_bucket_for_accession(accession)]


@dataclass(frozen=True)
class PreparedCatalogGeneration:
    manifest: CatalogGenerationManifest
    manifest_payload: bytes
    payloads: Mapping[str, bytes]
    filings: tuple[Mapping[str, Any], ...]
    holdings: tuple[Mapping[str, Any], ...]
    manager_relationships: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, CatalogGenerationManifest):
            raise Institutional13FCatalogError("prepared catalog manifest is invalid")
        if self.manifest_payload != self.manifest.to_json_bytes():
            raise Institutional13FCatalogError("prepared catalog manifest bytes are invalid")
        if tuple(self.payloads) != CATALOG_ARTIFACT_ROLES:
            raise Institutional13FCatalogError("prepared catalog artifact roles are invalid")
        for descriptor in self.manifest.artifacts:
            payload = self.payloads.get(descriptor.role)
            if (
                type(payload) is not bytes
                or len(payload) != descriptor.byte_length
                or sha256(payload).hexdigest() != descriptor.sha256
            ):
                raise Institutional13FCatalogError("prepared catalog artifact binding is invalid")

    @property
    def generation_id(self) -> str:
        return self.manifest.generation_id


@dataclass(frozen=True)
class PublishedCatalogGeneration:
    manifest: CatalogGenerationManifest
    payloads: Mapping[str, bytes]
    filings: tuple[Mapping[str, Any], ...]
    holdings: tuple[Mapping[str, Any], ...]
    manager_relationships: tuple[Mapping[str, Any], ...]
    pointer_updated: bool = False
    current_generation_id: str | None = None
    superseded: bool = False

    def __post_init__(self) -> None:
        current = self.current_generation_id or self.manifest.generation_id
        object.__setattr__(self, "current_generation_id", current)
        if self.superseded == (current == self.manifest.generation_id):
            raise Institutional13FCatalogError("published catalog successor state is invalid")
        if self.pointer_updated and self.superseded:
            raise Institutional13FCatalogError("a superseded catalog cannot update current")

    @property
    def generation_id(self) -> str:
        return self.manifest.generation_id


def _pyarrow_type(name: str):
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover - requirements pins pyarrow.
        raise Institutional13FCatalogError("pyarrow is required for 13F catalogs") from exc
    return {
        "string": pa.string(),
        "bool": pa.bool_(),
        "int32": pa.int32(),
        "int64": pa.int64(),
    }[name]


def parquet_schema(role: str):
    """Return the fixed Arrow schema for one projection role."""
    family = _role_family(role)
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover
        raise Institutional13FCatalogError("pyarrow is required for 13F catalogs") from exc
    return pa.schema(
        [
            pa.field(name, _pyarrow_type(kind), nullable=nullable)
            for name, kind, nullable in _FIELDS_BY_ROLE[family]
        ],
        metadata={
            b"schema": _PARQUET_SCHEMA_NAMES[family].encode("ascii"),
            b"authority": b"projection-only; canonical JSON manifest governs",
        },
    )


def _date_text(value: Any, *, field: str) -> str:
    try:
        normalized = normalize_report_period(str(value or ""))
    except Institutional13FError as exc:
        raise Institutional13FCatalogError(f"{field} is invalid") from exc
    return normalized


def _string(value: Any, *, field: str, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > HARD_MAX_CATALOG_CELL_CHARS:
        raise Institutional13FCatalogError(f"{field} must be a bounded non-empty string")
    return value


def _integer(value: Any, *, field: str, nullable: bool, bits: int) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Institutional13FCatalogError(f"{field} must be a non-negative integer")
    maximum = (1 << (bits - 1)) - 1
    if value > maximum:
        raise Institutional13FCatalogError(f"{field} exceeds signed int{bits}")
    return value


def _normalize_row(
    role: str,
    raw: Mapping[str, Any],
    *,
    report_period: str,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise Institutional13FCatalogError(f"{role} row must be a mapping")
    family = _role_family(role)
    fields = _FIELDS_BY_ROLE[family]
    allowed = {item[0] for item in fields}
    unknown = set(raw) - allowed
    if unknown:
        raise Institutional13FCatalogError(
            f"{role} row has unknown columns: {', '.join(sorted(unknown))}"
        )
    row: dict[str, Any] = {}
    for name, kind, nullable in fields:
        value = raw.get(name)
        if kind == "string":
            row[name] = _string(value, field=f"{role}.{name}", nullable=nullable)
        elif kind == "bool":
            if value is None and nullable:
                row[name] = None
            elif type(value) is not bool:
                raise Institutional13FCatalogError(f"{role}.{name} must be a boolean")
            else:
                row[name] = value
        else:
            row[name] = _integer(
                value, field=f"{role}.{name}", nullable=nullable, bits=int(kind[3:])
            )

    try:
        row["accession"] = normalize_accession(row["accession"])
        if family == "filings_parquet":
            row["filer_cik"] = normalize_cik(row["filer_cik"])
            row["form"] = normalize_form(row["form"])
            row["accepted_at"] = normalize_utc(row["accepted_at"], field="accepted_at")
            row["report_period"] = normalize_report_period(row["report_period"])
            if row["report_period"] != report_period:
                raise Institutional13FCatalogError("filing row belongs to another report period")
            if row["filing_date"] is not None:
                row["filing_date"] = _date_text(row["filing_date"], field="filing_date")
            if row["amends_accession"] is not None:
                row["amends_accession"] = normalize_accession(row["amends_accession"])
            validate_identity(row["source_receipt_id"], field="source_receipt_id")
            validate_sha256(row["raw_sha256"], field="raw_sha256")
            row["first_seen_at"] = normalize_utc(row["first_seen_at"], field="first_seen_at")
            row["retained_at"] = normalize_utc(row["retained_at"], field="retained_at")
            if utc_datetime(row["retained_at"], field="retained_at") < utc_datetime(
                row["accepted_at"], field="accepted_at"
            ):
                raise Institutional13FCatalogError("filing retained_at predates accepted_at")
        elif family == "holdings_parquet":
            validate_sha256(row["row_hash"], field="holdings.row_hash")
        elif row["manager_cik"] is not None:
            row["manager_cik"] = normalize_cik(row["manager_cik"])
    except Institutional13FError as exc:
        if isinstance(exc, Institutional13FCatalogError):
            raise
        raise Institutional13FCatalogError(f"invalid {role} row: {exc}") from exc
    return row


def _sortable(value: Any) -> tuple[int, Any]:
    return (0, "") if value is None else (1, value)


def _normalize_rows(
    role: str,
    values: Sequence[Mapping[str, Any]],
    *,
    report_period: str,
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise Institutional13FCatalogError(f"{role} rows must be a sequence")
    rows = [_normalize_row(role, item, report_period=report_period) for item in values]
    primary = _PRIMARY_KEYS[_role_family(role)]
    rows.sort(key=lambda item: tuple(_sortable(item[name]) for name in primary))
    prior: tuple[Any, ...] | None = None
    for row in rows:
        key = tuple(row[name] for name in primary)
        if key == prior:
            raise Institutional13FCatalogError(f"duplicate {role} primary key: {key!r}")
        prior = key
    return tuple(MappingProxyType(row) for row in rows)


def _encode_parquet(role: str, rows: Sequence[Mapping[str, Any]]) -> bytes:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise Institutional13FCatalogError("pyarrow is required for 13F catalogs") from exc
    schema = parquet_schema(role)
    try:
        table = pa.Table.from_pylist([dict(item) for item in rows], schema=schema)
        output = io.BytesIO()
        pq.write_table(
            table,
            output,
            compression="zstd",
            use_dictionary=False,
            write_statistics=False,
            version="2.6",
            data_page_version="1.0",
            row_group_size=max(1, len(rows)),
        )
        payload = output.getvalue()
    except Exception as exc:
        raise Institutional13FCatalogError(f"could not encode {role}") from exc
    if len(payload) > HARD_MAX_CATALOG_PARQUET_BYTES:
        raise Institutional13FCatalogError(f"{role} exceeds its byte ceiling")
    return payload


def _decode_parquet(
    role: str,
    payload: bytes,
    *,
    expected_rows: int,
    report_period: str,
) -> tuple[Mapping[str, Any], ...]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise Institutional13FCatalogError("pyarrow is required for 13F catalogs") from exc
    if len(payload) > HARD_MAX_CATALOG_PARQUET_BYTES:
        raise Institutional13FCatalogError(f"{role} exceeds its byte ceiling")
    try:
        reader = pq.ParquetFile(io.BytesIO(payload))
        if reader.schema_arrow != parquet_schema(role):
            raise Institutional13FCatalogError(f"{role} Arrow schema is invalid")
        if reader.metadata is None or reader.metadata.num_rows != expected_rows:
            raise Institutional13FCatalogError(f"{role} row count is invalid")
        if reader.metadata.num_row_groups not in {0, 1}:
            raise Institutional13FCatalogError(f"{role} must contain at most one row group")
        table = reader.read()
    except Institutional13FCatalogError:
        raise
    except Exception as exc:
        raise Institutional13FCatalogError(f"could not decode {role}") from exc
    if table.schema != parquet_schema(role) or table.num_rows != expected_rows:
        raise Institutional13FCatalogError(f"{role} decoded shape is invalid")
    # Re-normalization proves canonical ordering, types, and primary-key uniqueness.
    normalized = _normalize_rows(role, table.to_pylist(), report_period=report_period)
    if [dict(item) for item in normalized] != table.to_pylist():
        raise Institutional13FCatalogError(f"{role} rows are not canonically ordered")
    return normalized


def _artifact(role: str, payload: bytes, *, row_count: int | None) -> StoredObject:
    content_type = (
        "application/vnd.apache.parquet" if role.endswith("_parquet") else "application/json"
    )
    digest = sha256(payload).hexdigest()
    return StoredObject(
        role=role,
        object_key=content_object_key(digest, content_type=content_type),
        sha256=digest,
        byte_length=len(payload),
        content_type=content_type,
        row_count=row_count,
    )


def _normalized_source_receipts(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise Institutional13FCatalogError("source_receipt_ids must be a sequence")
    normalized = tuple(
        sorted(validate_identity(item, field="source_receipt_id") for item in values)
    )
    if len(set(normalized)) != len(normalized):
        raise Institutional13FCatalogError("source_receipt_ids contains a duplicate")
    return normalized


def _normalized_correction_accessions(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise Institutional13FCatalogError(f"catalog correction {field} must be an array")
    try:
        normalized = [normalize_accession(item) for item in value]
    except Institutional13FError as exc:
        raise Institutional13FCatalogError(
            f"catalog correction {field} contains an invalid accession"
        ) from exc
    if normalized != sorted(set(normalized)):
        raise Institutional13FCatalogError(
            f"catalog correction {field} must be unique and sorted"
        )
    return normalized


def _normalize_correction_declaration(value: Any) -> dict[str, Any]:
    """Validate the hash-bound declaration required for non-append catalog changes."""
    expected = {
        "schema",
        "supersedes_generation_id",
        "reason",
        "removed_accessions",
        "replaced_accessions",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise Institutional13FCatalogError("catalog correction declaration shape is invalid")
    if value.get("schema") != CATALOG_CORRECTION_SCHEMA:
        raise Institutional13FCatalogError("catalog correction schema is invalid")
    predecessor = value.get("supersedes_generation_id")
    try:
        validate_identity(predecessor, field="supersedes_generation_id")
    except Institutional13FError as exc:
        raise Institutional13FCatalogError(
            "catalog correction predecessor generation is invalid"
        ) from exc
    if not str(predecessor).startswith("i13fgen_"):
        raise Institutional13FCatalogError(
            "catalog correction predecessor generation is invalid"
        )
    reason = value.get("reason")
    if (
        not isinstance(reason, str)
        or not reason
        or reason != reason.strip()
        or len(reason) > 1024
    ):
        raise Institutional13FCatalogError(
            "catalog correction reason must be a bounded non-empty string"
        )
    removed = _normalized_correction_accessions(
        value.get("removed_accessions"), field="removed_accessions"
    )
    replaced = _normalized_correction_accessions(
        value.get("replaced_accessions"), field="replaced_accessions"
    )
    if set(removed) & set(replaced):
        raise Institutional13FCatalogError(
            "catalog correction removed and replaced accessions overlap"
        )
    if not removed and not replaced:
        raise Institutional13FCatalogError("catalog correction declares no row changes")
    return {
        "schema": CATALOG_CORRECTION_SCHEMA,
        "supersedes_generation_id": predecessor,
        "reason": reason,
        "removed_accessions": removed,
        "replaced_accessions": replaced,
    }


def prepare_catalog_generation(
    *,
    report_period: str,
    source_cutoff_at: str,
    published_at: str,
    producer_version: str,
    filings: Sequence[Mapping[str, Any]],
    holdings: Sequence[Mapping[str, Any]],
    manager_relationships: Sequence[Mapping[str, Any]] = (),
    source_receipt_ids: Sequence[str],
    coverage: Mapping[str, Any],
) -> PreparedCatalogGeneration:
    """Prepare a complete deterministic quarter generation without store I/O."""
    period = normalize_report_period(report_period)
    clocks = CatalogClocks(
        report_period=period,
        source_cutoff_at=source_cutoff_at,
        published_at=published_at,
    )
    filing_rows = _normalize_rows("filings_parquet", filings, report_period=period)
    holding_rows = _normalize_rows("holdings_parquet", holdings, report_period=period)
    manager_rows = _normalize_rows(
        "manager_relationships_parquet", manager_relationships, report_period=period
    )
    accessions = {str(item["accession"]) for item in filing_rows}
    if any(str(item["accession"]) not in accessions for item in holding_rows):
        raise Institutional13FCatalogError("holding row has no filing in this generation")
    if any(str(item["accession"]) not in accessions for item in manager_rows):
        raise Institutional13FCatalogError("manager relationship has no filing in this generation")
    if filing_rows:
        max_accepted = max(
            utc_datetime(str(item["accepted_at"]), field="accepted_at")
            for item in filing_rows
        )
        if utc_datetime(
            str(clocks.source_cutoff_at), field="source_cutoff_at"
        ) < max_accepted:
            raise Institutional13FCatalogError("source_cutoff_at predates a filing acceptance")
        if any(
            utc_datetime(str(item["retained_at"]), field="retained_at")
            > utc_datetime(str(clocks.published_at), field="published_at")
            for item in filing_rows
        ):
            raise Institutional13FCatalogError("published_at predates a retained filing")

    receipts = _normalized_source_receipts(source_receipt_ids)
    filing_receipts = {str(item["source_receipt_id"]) for item in filing_rows}
    if filing_receipts != set(receipts):
        raise Institutional13FCatalogError(
            "source_receipt_ids must exactly match filing provenance"
        )
    if not isinstance(coverage, Mapping):
        raise Institutional13FCatalogError("coverage must be a mapping")
    if set(coverage) & {"schema", "report_period"}:
        raise Institutional13FCatalogError("coverage uses a reserved key")
    coverage_body = dict(coverage)
    if "correction" in coverage_body:
        coverage_body["correction"] = _normalize_correction_declaration(
            coverage_body["correction"]
        )

    holdings_by_bucket: dict[str, list[Mapping[str, Any]]] = {
        role: [] for role in HOLDING_BUCKET_ROLES
    }
    for row in holding_rows:
        holdings_by_bucket[holding_bucket_role(str(row["accession"]))].append(row)

    payloads: dict[str, bytes] = {
        "filings_parquet": _encode_parquet("filings_parquet", filing_rows),
        **{
            role: _encode_parquet(role, holdings_by_bucket[role])
            for role in HOLDING_BUCKET_ROLES
        },
        "manager_relationships_parquet": _encode_parquet(
            "manager_relationships_parquet", manager_rows
        ),
        "source_receipts_json": canonical_json_bytes(
            {
                "schema": SOURCE_RECEIPTS_SCHEMA,
                "report_period": period,
                "source_receipt_ids": list(receipts),
            }
        ),
        "coverage_json": canonical_json_bytes(
            {"schema": COVERAGE_SCHEMA, "report_period": period, **coverage_body}
        ),
    }
    for role, payload in payloads.items():
        if len(payload) > _ROLE_BYTE_LIMITS[role]:
            raise Institutional13FCatalogError(f"{role} exceeds its byte ceiling")
    counts = CatalogCounts(
        filing_rows=len(filing_rows),
        holding_rows=len(holding_rows),
        manager_relationship_rows=len(manager_rows),
        source_receipts=len(receipts),
    )
    row_counts = {
        "filings_parquet": counts.filing_rows,
        **{role: len(holdings_by_bucket[role]) for role in HOLDING_BUCKET_ROLES},
        "manager_relationships_parquet": counts.manager_relationship_rows,
        "source_receipts_json": counts.source_receipts,
        "coverage_json": None,
    }
    artifacts = tuple(
        _artifact(role, payloads[role], row_count=row_counts[role])
        for role in CATALOG_ARTIFACT_ROLES
    )
    manifest = CatalogGenerationManifest.build(
        producer_version=producer_version,
        clocks=clocks,
        counts=counts,
        artifacts=artifacts,
    )
    manifest_payload = manifest.to_json_bytes()
    if len(manifest_payload) > HARD_MAX_CATALOG_MANIFEST_BYTES:
        raise Institutional13FCatalogError("catalog manifest exceeds its byte ceiling")
    # Immediate strict decode catches malformed identity construction before I/O.
    if CatalogGenerationManifest.from_json_bytes(manifest_payload) != manifest:
        raise Institutional13FCatalogError("catalog manifest local verification failed")
    return PreparedCatalogGeneration(
        manifest=manifest,
        manifest_payload=manifest_payload,
        payloads=MappingProxyType(dict(payloads)),
        filings=filing_rows,
        holdings=holding_rows,
        manager_relationships=manager_rows,
    )


def _read_required(
    store: StrictBoundedReadStore,
    key: str,
    *,
    maximum_bytes: int,
) -> bytes:
    try:
        payload = store.get_bytes_strict_bounded(key, maximum_bytes)
    except Exception as exc:
        raise Institutional13FCatalogError(f"catalog bounded read failed for {key}") from exc
    if payload is None:
        raise Institutional13FCatalogError(f"catalog object is missing: {key}")
    if type(payload) is not bytes or len(payload) > maximum_bytes:
        raise Institutional13FCatalogError(f"catalog bounded read is invalid for {key}")
    return payload


def _decode_json_artifacts(
    *,
    report_period: str,
    source_payload: bytes,
    coverage_payload: bytes,
    expected_receipts: int,
) -> tuple[str, ...]:
    source = decode_canonical_json(source_payload, label="catalog source receipts")
    if set(source) != {"schema", "report_period", "source_receipt_ids"}:
        raise Institutional13FCatalogError("catalog source receipts shape is invalid")
    if (
        source.get("schema") != SOURCE_RECEIPTS_SCHEMA
        or source.get("report_period") != report_period
    ):
        raise Institutional13FCatalogError("catalog source receipts binding is invalid")
    receipts = source.get("source_receipt_ids")
    if not isinstance(receipts, list):
        raise Institutional13FCatalogError("catalog source receipts list is invalid")
    normalized = _normalized_source_receipts(receipts)
    if list(normalized) != receipts or len(normalized) != expected_receipts:
        raise Institutional13FCatalogError("catalog source receipts count or order is invalid")

    coverage = decode_canonical_json(coverage_payload, label="catalog coverage")
    if coverage.get("schema") != COVERAGE_SCHEMA or coverage.get("report_period") != report_period:
        raise Institutional13FCatalogError("catalog coverage binding is invalid")
    return normalized


def _coverage_document(generation: PublishedCatalogGeneration) -> dict[str, Any]:
    payload = generation.payloads.get("coverage_json")
    if type(payload) is not bytes:
        raise Institutional13FCatalogError("catalog coverage artifact is missing")
    coverage = decode_canonical_json(payload, label="catalog coverage")
    if (
        coverage.get("schema") != COVERAGE_SCHEMA
        or coverage.get("report_period") != generation.manifest.clocks.report_period
    ):
        raise Institutional13FCatalogError("catalog coverage binding is invalid")
    if "correction" in coverage:
        normalized = _normalize_correction_declaration(coverage["correction"])
        if normalized != coverage["correction"]:
            raise Institutional13FCatalogError(
                "catalog correction declaration is not canonical"
            )
    return coverage


def _rows_grouped_by_accession(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["accession"]), []).append(dict(row))
    return {accession: tuple(values) for accession, values in grouped.items()}


def _assert_catalog_successor(
    current: PublishedCatalogGeneration,
    successor: PublishedCatalogGeneration,
) -> None:
    """Reject clock rewind and silent loss/mutation across a pointer advance.

    The normal rolling contract is append-only.  A completed reconciliation may
    remove or replace accession rows only through an exact, manifest-bound
    correction declaration that names the predecessor and every affected
    accession.  This keeps a later wall-clock publication from silently winning
    with an older or smaller snapshot.
    """
    current_cutoff = utc_datetime(
        current.manifest.clocks.source_cutoff_at, field="source_cutoff_at"
    )
    successor_cutoff = utc_datetime(
        successor.manifest.clocks.source_cutoff_at, field="source_cutoff_at"
    )
    if successor_cutoff < current_cutoff:
        raise Institutional13FCatalogError(
            "catalog source_cutoff_at cannot rewind current pointer"
        )

    current_filings = {str(row["accession"]): dict(row) for row in current.filings}
    successor_filings = {
        str(row["accession"]): dict(row) for row in successor.filings
    }
    current_accessions = set(current_filings)
    successor_accessions = set(successor_filings)
    removed = current_accessions - successor_accessions

    current_holdings = _rows_grouped_by_accession(current.holdings)
    successor_holdings = _rows_grouped_by_accession(successor.holdings)
    current_managers = _rows_grouped_by_accession(current.manager_relationships)
    successor_managers = _rows_grouped_by_accession(successor.manager_relationships)
    replaced = {
        accession
        for accession in current_accessions & successor_accessions
        if (
            current_filings[accession] != successor_filings[accession]
            or current_holdings.get(accession, ())
            != successor_holdings.get(accession, ())
            or current_managers.get(accession, ())
            != successor_managers.get(accession, ())
        )
    }

    correction = _coverage_document(successor).get("correction")
    if not removed and not replaced:
        if correction is not None:
            raise Institutional13FCatalogError(
                "catalog correction declaration has no matching row changes"
            )
        return
    if correction is None:
        raise Institutional13FCatalogError(
            "catalog successor drops or changes accessions without an explicit correction"
        )
    if correction["supersedes_generation_id"] != current.generation_id:
        raise Institutional13FCatalogError(
            "catalog correction does not bind the current generation"
        )
    if correction["removed_accessions"] != sorted(removed):
        raise Institutional13FCatalogError(
            "catalog correction removed_accessions does not match row loss"
        )
    if correction["replaced_accessions"] != sorted(replaced):
        raise Institutional13FCatalogError(
            "catalog correction replaced_accessions does not match row changes"
        )


def _load_generation(
    store: StrictBoundedReadStore,
    *,
    report_period: str,
    generation_id: str,
) -> PublishedCatalogGeneration:
    key = catalog_manifest_key(report_period, generation_id)
    manifest_payload = _read_required(
        store, key, maximum_bytes=HARD_MAX_CATALOG_MANIFEST_BYTES
    )
    manifest = CatalogGenerationManifest.from_json_bytes(manifest_payload)
    if manifest.generation_id != generation_id or manifest.manifest_key != key:
        raise Institutional13FCatalogError("catalog manifest does not bind requested generation")
    if manifest.clocks.report_period != report_period:
        raise Institutional13FCatalogError("catalog manifest belongs to another report period")

    payloads: dict[str, bytes] = {}
    for descriptor in manifest.artifacts:
        try:
            payloads[descriptor.role] = read_verified_object(
                store, descriptor, maximum_bytes=_ROLE_BYTE_LIMITS[descriptor.role]
            )
        except Institutional13FStorageError as exc:
            raise Institutional13FCatalogError(str(exc)) from exc
    filings = _decode_parquet(
        "filings_parquet",
        payloads["filings_parquet"],
        expected_rows=manifest.counts.filing_rows,
        report_period=report_period,
    )
    holding_rows: list[Mapping[str, Any]] = []
    descriptors_by_role = {item.role: item for item in manifest.artifacts}
    for role in HOLDING_BUCKET_ROLES:
        bucket_rows = _decode_parquet(
            role,
            payloads[role],
            expected_rows=descriptors_by_role[role].row_count or 0,
            report_period=report_period,
        )
        if any(holding_bucket_role(str(item["accession"])) != role for item in bucket_rows):
            raise Institutional13FCatalogError("holding row is stored in the wrong bucket")
        holding_rows.extend(bucket_rows)
    holdings = _normalize_rows(
        "holdings_parquet", holding_rows, report_period=report_period
    )
    if len(holdings) != manifest.counts.holding_rows:
        raise Institutional13FCatalogError("holding bucket row total is invalid")
    managers = _decode_parquet(
        "manager_relationships_parquet",
        payloads["manager_relationships_parquet"],
        expected_rows=manifest.counts.manager_relationship_rows,
        report_period=report_period,
    )
    receipts = _decode_json_artifacts(
        report_period=report_period,
        source_payload=payloads["source_receipts_json"],
        coverage_payload=payloads["coverage_json"],
        expected_receipts=manifest.counts.source_receipts,
    )
    if {str(item["source_receipt_id"]) for item in filings} != set(receipts):
        raise Institutional13FCatalogError("catalog filing provenance does not match receipts")
    filing_accessions = {str(item["accession"]) for item in filings}
    if any(str(item["accession"]) not in filing_accessions for item in holdings + managers):
        raise Institutional13FCatalogError("catalog child row has no filing")
    return PublishedCatalogGeneration(
        manifest=manifest,
        payloads=MappingProxyType(payloads),
        filings=filings,
        holdings=holdings,
        manager_relationships=managers,
        current_generation_id=generation_id,
    )


def _pointer_binds_generation(
    store: StrictBoundedReadStore,
    pointer: CatalogPointer,
) -> PublishedCatalogGeneration:
    manifest_payload = _read_required(
        store, pointer.manifest_key, maximum_bytes=HARD_MAX_CATALOG_MANIFEST_BYTES
    )
    if (
        len(manifest_payload) != pointer.manifest_byte_length
        or sha256(manifest_payload).hexdigest() != pointer.manifest_sha256
    ):
        raise Institutional13FCatalogError("catalog pointer manifest hash or length is invalid")
    loaded = _load_generation(
        store,
        report_period=str(pointer.report_period),
        generation_id=pointer.generation_id,
    )
    if loaded.manifest.clocks.published_at != pointer.published_at:
        raise Institutional13FCatalogError("catalog pointer clock does not bind its manifest")
    return loaded


def load_catalog_generation(
    store: StrictBoundedReadStore,
    *,
    report_period: str,
    generation_id: str | None = None,
) -> PublishedCatalogGeneration:
    """Load and fully verify one generation or the quarter's current pointer."""
    if not isinstance(store, StrictBoundedReadStore):
        raise Institutional13FCatalogError(
            "catalog load requires a StrictBoundedReadStore"
        )
    period = normalize_report_period(report_period)
    if generation_id is not None:
        return _load_generation(store, report_period=period, generation_id=generation_id)
    pointer_payload = _read_required(
        store, catalog_pointer_key(period), maximum_bytes=HARD_MAX_CATALOG_POINTER_BYTES
    )
    pointer = CatalogPointer.from_json_bytes(pointer_payload)
    if pointer.report_period != period:
        raise Institutional13FCatalogError("catalog pointer belongs to another report period")
    return _pointer_binds_generation(store, pointer)


def _read_versioned_pointer(
    store: StrictConditionalWriteStore,
    *,
    report_period: str,
) -> VersionedBytes:
    try:
        observed = store.get_bytes_strict_bounded_versioned(
            catalog_pointer_key(report_period), HARD_MAX_CATALOG_POINTER_BYTES
        )
    except Exception as exc:
        raise Institutional13FCatalogError("catalog pointer versioned read failed") from exc
    if type(observed) is not VersionedBytes:
        raise Institutional13FCatalogError("catalog pointer versioned read is invalid")
    return observed


def _decode_bound_pointer(
    store: StrictBoundedReadStore,
    payload: bytes,
    *,
    report_period: str,
) -> tuple[CatalogPointer, PublishedCatalogGeneration]:
    pointer = CatalogPointer.from_json_bytes(payload)
    if pointer.schema != CATALOG_POINTER_SCHEMA or pointer.report_period != report_period:
        raise Institutional13FCatalogError("catalog pointer report period is invalid")
    return pointer, _pointer_binds_generation(store, pointer)


def _publication_result(
    loaded: PublishedCatalogGeneration,
    *,
    pointer_updated: bool,
    current_generation_id: str,
) -> PublishedCatalogGeneration:
    return replace(
        loaded,
        pointer_updated=pointer_updated,
        current_generation_id=current_generation_id,
        superseded=current_generation_id != loaded.generation_id,
    )


def _reconcile_pointer_outcome(
    store: StrictConditionalWriteStore,
    *,
    loaded: PublishedCatalogGeneration,
    desired: CatalogPointer,
    desired_payload: bytes,
    pointer_updated: bool,
    cause: BaseException | None,
) -> PublishedCatalogGeneration:
    observed = _read_versioned_pointer(store, report_period=str(desired.report_period))
    if observed.data == desired_payload:
        return _publication_result(
            loaded,
            pointer_updated=pointer_updated,
            current_generation_id=desired.generation_id,
        )
    if observed.data is not None:
        successor, successor_generation = _decode_bound_pointer(
            store, observed.data, report_period=str(desired.report_period)
        )
        if utc_datetime(successor.published_at, field="published_at") > utc_datetime(
            desired.published_at, field="published_at"
        ):
            try:
                _assert_catalog_successor(loaded, successor_generation)
            except Institutional13FCatalogError as exc:
                conflict = Institutional13FCatalogError(
                    "catalog pointer winner does not preserve the desired generation"
                )
                if cause is not None:
                    raise conflict from cause
                raise conflict from exc
            return _publication_result(
                loaded,
                pointer_updated=False,
                current_generation_id=successor.generation_id,
            )
    error = Institutional13FCatalogError("catalog current pointer compare-and-swap conflict")
    if cause is not None:
        raise error from cause
    raise error


def publish_catalog_generation(
    store: StrictConditionalWriteStore,
    prepared: PreparedCatalogGeneration,
) -> PublishedCatalogGeneration:
    """Publish immutable artifacts/manifest, then CAS-advance quarter current."""
    if not isinstance(prepared, PreparedCatalogGeneration):
        raise TypeError("prepared must be PreparedCatalogGeneration")
    if not isinstance(store, StrictConditionalWriteStore):
        raise Institutional13FCatalogError(
            "catalog publication requires a StrictConditionalWriteStore"
        )
    try:
        store.validate_strict_conditional_write_capability()
    except Exception as exc:
        raise Institutional13FCatalogError(
            "catalog conditional-write capability validation failed"
        ) from exc

    for descriptor in prepared.manifest.artifacts:
        create_verified_immutable(
            store,
            key=descriptor.object_key,
            payload=prepared.payloads[descriptor.role],
            content_type=descriptor.content_type,
            maximum_bytes=_ROLE_BYTE_LIMITS[descriptor.role],
            expected_sha256=descriptor.sha256,
        )
    create_verified_immutable(
        store,
        key=prepared.manifest.manifest_key,
        payload=prepared.manifest_payload,
        content_type="application/json",
        maximum_bytes=HARD_MAX_CATALOG_MANIFEST_BYTES,
        expected_sha256=sha256(prepared.manifest_payload).hexdigest(),
    )
    loaded = load_catalog_generation(
        store,
        report_period=str(prepared.manifest.clocks.report_period),
        generation_id=prepared.generation_id,
    )
    pointer = CatalogPointer.from_manifest(prepared.manifest)
    pointer_payload = pointer.to_json_bytes()
    if len(pointer_payload) > HARD_MAX_CATALOG_POINTER_BYTES:  # pragma: no cover - fixed shape.
        raise Institutional13FCatalogError("catalog pointer exceeds its byte ceiling")
    prior = _read_versioned_pointer(store, report_period=str(pointer.report_period))
    if prior.data is not None:
        current, current_generation = _decode_bound_pointer(
            store, prior.data, report_period=str(pointer.report_period)
        )
        if current.generation_id == pointer.generation_id:
            if prior.data != pointer_payload:
                raise Institutional13FCatalogError(
                    "catalog pointer disagrees with its immutable generation"
                )
            return _publication_result(
                loaded, pointer_updated=False, current_generation_id=pointer.generation_id
            )
        _assert_catalog_successor(current_generation, loaded)
        if utc_datetime(current.published_at, field="published_at") >= utc_datetime(
            pointer.published_at, field="published_at"
        ):
            raise Institutional13FCatalogError(
                "stale catalog generation cannot rewind current pointer"
            )

    try:
        written = store.put_bytes_strict_conditional(
            pointer.object_key,
            pointer_payload,
            expected_version=prior.version,
            content_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001 -- provider may commit before connection loss.
        return _reconcile_pointer_outcome(
            store,
            loaded=loaded,
            desired=pointer,
            desired_payload=pointer_payload,
            pointer_updated=True,
            cause=exc,
        )
    if written is not True:
        return _reconcile_pointer_outcome(
            store,
            loaded=loaded,
            desired=pointer,
            desired_payload=pointer_payload,
            pointer_updated=False,
            cause=None,
        )
    return _reconcile_pointer_outcome(
        store,
        loaded=loaded,
        desired=pointer,
        desired_payload=pointer_payload,
        pointer_updated=True,
        cause=None,
    )
