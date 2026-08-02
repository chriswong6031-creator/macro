"""Fail-closed, dark-by-default acquisition of the official Drugs@FDA ZIP.

The FDA data page says the compressed data file is updated each morning Monday
through Friday and contains twelve tab-delimited tables.  That is release
cadence metadata, not a promise of a unique daily release or a publication
time.  The exact archive SHA-256 is the only release identity here.

No live ingestion is enabled by this module.  Its network entry point exists
solely for an explicitly reviewed, separately provisioned B4A worker.  It
stores exact ZIP/page bytes privately; the public projection never carries a
raw key, filesystem path, request credential, or a private receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import csv
import binascii
import fcntl
import hashlib
from html import unescape
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urljoin, urlsplit
import zipfile

import requests
import yaml

from engine.biocatalyst.regulatory import PARSER_VERSION
from engine.biocatalyst.storage import BinaryObjectStore, MirrorReceipt, StorageError, mirror_bytes_verified
from engine.sector_intelligence import (
    canonical_json_bytes, canonical_json_sha256, validate_drugs_at_fda_release_receipt,
    validate_drugs_at_fda_table_manifest,
)
from engine.sector_intelligence.contracts import ContractError


SOURCE_ID = "drugs_at_fda"
FDA_DATA_PAGE_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files"
FDA_ARCHIVE_URL = "https://www.fda.gov/media/89850/download?attachment="
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "content-encoding", "content-disposition", "date", "etag", "last-modified"}
)
EXPECTED_HEADERS: dict[str, tuple[str, ...]] = {
    "ActionTypes_Lookup.txt": ("ActionTypes_LookupID", "ActionTypes_LookupDescription", "SupplCategoryLevel1Code", "SupplCategoryLevel2Code"),
    "ApplicationDocs.txt": ("ApplicationDocsID", "ApplicationDocsTypeID", "ApplNo", "SubmissionType", "SubmissionNo", "ApplicationDocsTitle", "ApplicationDocsURL", "ApplicationDocsDate"),
    "Applications.txt": ("ApplNo", "ApplType", "ApplPublicNotes", "SponsorName"),
    "ApplicationsDocsType_Lookup.txt": ("ApplicationDocsType_Lookup_ID", "ApplicationDocsType_Lookup_Description"),
    "Join_Submission_ActionTypes_Lookup.txt": ("SubmissionType", "j_submissionActionTypeID", "ApplNo", "SubmissionNo", "ActionTypes_LookupID"),
    "MarketingStatus.txt": ("MarketingStatusID", "ApplNo", "ProductNo"),
    "MarketingStatus_Lookup.txt": ("MarketingStatusID", "MarketingStatusDescription"),
    "Products.txt": ("ApplNo", "ProductNo", "Form", "Strength", "ReferenceDrug", "DrugName", "ActiveIngredient", "ReferenceStandard"),
    "SubmissionClass_Lookup.txt": ("SubmissionClassCodeID", "SubmissionClassCode", "SubmissionClassCodeDescription"),
    "SubmissionPropertyType.txt": ("ApplNo", "SubmissionType", "SubmissionNo", "SubmissionPropertyTypeCode", "SubmissionPropertyTypeID"),
    "Submissions.txt": ("ApplNo", "SubmissionClassCodeID", "SubmissionType", "SubmissionNo", "SubmissionStatus", "SubmissionStatusDate", "SubmissionsPublicNotes", "ReviewPriority"),
    "TE.txt": ("ApplNo", "ProductNo", "MarketingStatusID", "TECode"),
}
PRIMARY_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "ActionTypes_Lookup.txt": ("ActionTypes_LookupID",),
    "ApplicationDocs.txt": ("ApplicationDocsID",),
    "Applications.txt": ("ApplNo",),
    "ApplicationsDocsType_Lookup.txt": ("ApplicationDocsType_Lookup_ID",),
    "Join_Submission_ActionTypes_Lookup.txt": ("j_submissionActionTypeID",),
    "MarketingStatus.txt": ("MarketingStatusID", "ApplNo", "ProductNo"),
    "MarketingStatus_Lookup.txt": ("MarketingStatusID",),
    "Products.txt": ("ApplNo", "ProductNo"),
    "SubmissionClass_Lookup.txt": ("SubmissionClassCodeID",),
    "SubmissionPropertyType.txt": ("ApplNo", "SubmissionType", "SubmissionNo", "SubmissionPropertyTypeID"),
    "Submissions.txt": ("ApplNo", "SubmissionType", "SubmissionNo"),
    "TE.txt": ("ApplNo", "ProductNo", "MarketingStatusID", "TECode"),
}
ROW_IDENTITY_FIELDS = {
    **PRIMARY_KEY_FIELDS,
    # Blank TECode is source data in the live archive.  Its physical-line hash
    # gives the raw row a stable private identity without rewriting that blank.
    "TE.txt": ("ApplNo", "ProductNo", "MarketingStatusID", "__fda_physical_line_sha256"),
}

# Static, allowlisted identifiers for the release-local SQLite query index.
# They are never derived from an upstream filename at runtime.
SQLITE_TABLE_NAMES: dict[str, str] = {
    "ActionTypes_Lookup.txt": "fda_action_types_lookup",
    "ApplicationDocs.txt": "fda_application_docs",
    "Applications.txt": "fda_applications",
    "ApplicationsDocsType_Lookup.txt": "fda_application_docs_type_lookup",
    "Join_Submission_ActionTypes_Lookup.txt": "fda_submission_action_join",
    "MarketingStatus.txt": "fda_marketing_status",
    "MarketingStatus_Lookup.txt": "fda_marketing_status_lookup",
    "Products.txt": "fda_products",
    "SubmissionClass_Lookup.txt": "fda_submission_class_lookup",
    "SubmissionPropertyType.txt": "fda_submission_property_type",
    "Submissions.txt": "fda_submissions",
    "TE.txt": "fda_therapeutic_equivalence",
}


def _quote_identifier(identifier: str) -> str:
    """Quote a static SQLite identifier after a strict local allowlist check."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise DrugsAtFdaCollectionError("UNSAFE_SQL_IDENTIFIER", identifier)
    return f'"{identifier}"'


def _sqlite_schema_spec() -> dict[str, Any]:
    """Return the deterministic typed-table contract, including derived joins."""
    tables: dict[str, Any] = {}
    for source_name, sqlite_name in SQLITE_TABLE_NAMES.items():
        source_columns = list(EXPECTED_HEADERS[source_name])
        derived = ["SubmissionType_join"] if "SubmissionType" in source_columns else []
        tables[source_name] = {
            "sqlite_table": sqlite_name,
            "columns": ["physical_line", "physical_line_sha256", *source_columns, *derived],
            "source_columns": source_columns,
            "derived_columns": derived,
            "column_types": {
                "physical_line": "INTEGER",
                "physical_line_sha256": "TEXT",
                **{column: "TEXT" for column in [*source_columns, *derived]},
            },
            "not_null_columns": ["physical_line", "physical_line_sha256", *source_columns, *derived],
            "primary_key": ["physical_line"],
            "without_rowid": True,
        }
    return {
        "version": "drugs_at_fda_typed_sqlite_v1",
        "tables": tables,
        "indexes": [
            {"table": "fda_applications", "name": "idx_applications_appl", "columns": ["ApplNo"]},
            {"table": "fda_products", "name": "idx_products_appl_product", "columns": ["ApplNo", "ProductNo"]},
            {"table": "fda_submissions", "name": "idx_submissions_relation", "columns": ["ApplNo", "SubmissionType_join", "SubmissionNo"]},
            {"table": "fda_application_docs", "name": "idx_docs_appl", "columns": ["ApplNo"]},
            {"table": "fda_application_docs", "name": "idx_docs_submission", "columns": ["ApplNo", "SubmissionType_join", "SubmissionNo"]},
            {"table": "fda_submission_action_join", "name": "idx_join_submission", "columns": ["ApplNo", "SubmissionType_join", "SubmissionNo"]},
            {"table": "fda_submission_action_join", "name": "idx_join_action_lookup", "columns": ["ActionTypes_LookupID"]},
            {"table": "fda_action_types_lookup", "name": "idx_action_lookup", "columns": ["ActionTypes_LookupID"]},
            {"table": "fda_marketing_status", "name": "idx_marketing_product", "columns": ["ApplNo", "ProductNo"]},
            {"table": "fda_submission_property_type", "name": "idx_properties_submission", "columns": ["ApplNo", "SubmissionType_join", "SubmissionNo"]},
            {"table": "fda_therapeutic_equivalence", "name": "idx_te_product", "columns": ["ApplNo", "ProductNo"]},
        ],
    }


SQLITE_SCHEMA_SPEC = _sqlite_schema_spec()
SQLITE_SCHEMA_SPEC_SHA256 = canonical_json_sha256(SQLITE_SCHEMA_SPEC)

SQLITE_ORPHAN_QUERIES: dict[str, str] = {
    "products_missing_application": "SELECT count(*) FROM fda_products p WHERE NOT EXISTS (SELECT 1 FROM fda_applications a WHERE a.ApplNo=p.ApplNo)",
    "submissions_missing_application": "SELECT count(*) FROM fda_submissions s WHERE NOT EXISTS (SELECT 1 FROM fda_applications a WHERE a.ApplNo=s.ApplNo)",
    "application_docs_missing_application": "SELECT count(*) FROM fda_application_docs d WHERE NOT EXISTS (SELECT 1 FROM fda_applications a WHERE a.ApplNo=d.ApplNo)",
    "application_docs_missing_submission": "SELECT count(*) FROM fda_application_docs d WHERE NOT EXISTS (SELECT 1 FROM fda_submissions s WHERE s.ApplNo=d.ApplNo AND s.SubmissionType_join=d.SubmissionType_join AND s.SubmissionNo=d.SubmissionNo)",
    "join_actions_missing_submission": "SELECT count(*) FROM fda_submission_action_join j WHERE NOT EXISTS (SELECT 1 FROM fda_submissions s WHERE s.ApplNo=j.ApplNo AND s.SubmissionType_join=j.SubmissionType_join AND s.SubmissionNo=j.SubmissionNo)",
    "join_actions_missing_action_lookup": "SELECT count(*) FROM fda_submission_action_join j WHERE NOT EXISTS (SELECT 1 FROM fda_action_types_lookup a WHERE a.ActionTypes_LookupID=j.ActionTypes_LookupID)",
    "marketing_status_missing_product": "SELECT count(*) FROM fda_marketing_status m WHERE NOT EXISTS (SELECT 1 FROM fda_products p WHERE p.ApplNo=m.ApplNo AND p.ProductNo=m.ProductNo)",
    "submission_properties_missing_submission": "SELECT count(*) FROM fda_submission_property_type p WHERE NOT EXISTS (SELECT 1 FROM fda_submissions s WHERE s.ApplNo=p.ApplNo AND s.SubmissionType_join=p.SubmissionType_join AND s.SubmissionNo=p.SubmissionNo)",
    "te_missing_product": "SELECT count(*) FROM fda_therapeutic_equivalence t WHERE NOT EXISTS (SELECT 1 FROM fda_products p WHERE p.ApplNo=t.ApplNo AND p.ProductNo=t.ProductNo)",
}

FORBIDDEN_DERIVED_CLAIMS = (
    "pending_application", "pdufa_date", "ind", "clinical_hold",
    "complete_response_letter", "approval_odds", "medical_claim",
    "company_or_ticker_identity", "trial_or_asset_identity",
    "prophet_or_trade_authority",
)

# This is an FDA-source anomaly, not a generic parser heuristic.  The only
# permitted repair is one *empty* ninth field in the specified physical line of
# the exact observed archive.  Every future release must match the published
# eight-field header with no tolerance until it earns its own reviewed policy.
_APPDOCS_EMPTY_FIELD_EXCEPTION = {
    "archive_sha256": "5ff17b3eeb88c1d0e5338cdc2a24caf687aed82dc0fbde7aec46810fb8092c53",
    "table": "ApplicationDocs.txt",
    "row_number": 78723,
    "raw_row_sha256": "ba089d86d6982a8d5ab35eecd3c15c3efd8777235b52cab84591cd87cd76d8e0",
    "application_docs_id": "84630",
}

# Regression witness for the one archive with the narrowly-scoped physical-row
# repair above.  It is an acceptance assertion, never a completeness rule for
# future FDA releases (which may legitimately change these source gaps).
_KNOWN_20260731_ARCHIVE_GAPS = {
    "products_missing_application": 11,
    "submissions_missing_application": 5378,
    "application_docs_missing_application": 3,
    "application_docs_missing_submission": 152,
    "join_actions_missing_submission": 494,
    "join_actions_missing_action_lookup": 296,
    "marketing_status_missing_product": 599,
    "submission_properties_missing_submission": 256,
    "te_missing_product": 12,
}
_KNOWN_20260731_TOTAL_ROWS = 959_263
DEFAULT_MAX_ROWS_PER_MEMBER = 1_000_000
DEFAULT_MAX_TOTAL_ROWS = 2_000_000


class DrugsAtFdaCollectionError(RuntimeError):
    """A bounded source/archive/publication failure that never advances a pointer."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class DrugsAtFdaConfig:
    user_agent: str
    landing_url: str = FDA_DATA_PAGE_URL
    archive_url: str = FDA_ARCHIVE_URL
    max_archive_bytes: int = 128 * 1024 * 1024
    max_landing_bytes: int = 4 * 1024 * 1024
    max_member_count: int = 12
    max_member_uncompressed_bytes: int = 64 * 1024 * 1024
    max_total_uncompressed_bytes: int = 256 * 1024 * 1024
    max_in_memory_parse_uncompressed_bytes: int = 8 * 1024 * 1024
    max_rows_per_member: int = DEFAULT_MAX_ROWS_PER_MEMBER
    max_total_rows: int = DEFAULT_MAX_TOTAL_ROWS
    max_compression_ratio: float = 100.0
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 120.0
    max_redirects: int = 4
    source_registry_path: Path | None = None
    require_private_mirror: bool = False

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("a descriptive user_agent is required")
        if min(self.max_archive_bytes, self.max_landing_bytes) <= 0 or self.max_member_count != len(EXPECTED_HEADERS):
            raise ValueError("archive limits must preserve the exact 12-table contract")
        if min(self.max_member_uncompressed_bytes, self.max_total_uncompressed_bytes, self.max_in_memory_parse_uncompressed_bytes) <= 0:
            raise ValueError("uncompressed limits must be positive")
        if not (0 < self.max_rows_per_member <= DEFAULT_MAX_ROWS_PER_MEMBER):
            raise ValueError("per-member row ceiling may only be tightened")
        if not (self.max_rows_per_member <= self.max_total_rows <= DEFAULT_MAX_TOTAL_ROWS):
            raise ValueError("total row ceiling may only be tightened and must cover one member")
        if self.max_compression_ratio <= 1:
            raise ValueError("max_compression_ratio must exceed one")
        if min(self.connect_timeout_seconds, self.read_timeout_seconds) <= 0 or self.max_redirects < 0:
            raise ValueError("timeouts must be positive")


@dataclass(frozen=True)
class ParsedDrugsAtFdaRelease:
    archive_sha256: str
    tables: dict[str, tuple[dict[str, str], ...]]
    table_manifests: tuple[dict[str, Any], ...]
    member_bytes_by_name: dict[str, bytes]


@dataclass(frozen=True)
class StreamedDrugsAtFdaRelease:
    archive_sha256: str
    table_manifests: tuple[dict[str, Any], ...]
    table_row_counts: dict[str, int]
    sqlite_table_semantic_row_digests: dict[str, str]


@dataclass(frozen=True)
class DrugsAtFdaPublicationResult:
    release_id: str
    archive_sha256: str
    generation_path: Path
    pointer_path: Path
    application_count: int
    integrity: Mapping[str, Any]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ascii_right_trim(value: str) -> str:
    """Normalize only fixed-width ASCII trailing padding for relational joins."""
    return value.rstrip(" ")


def _join_value(field: str, value: str) -> str:
    # Application/product identifiers are source-native ASCII fixed fields.  Do
    # not broad-strip source text: it would rewrite source meaning.  FDA's
    # SubmissionType has fixed-width right spaces and is the only value normalised.
    return _ascii_right_trim(value) if field == "SubmissionType" else value


def _safe_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for name, value in headers.items():
        normalized = str(name).lower()
        if normalized in SAFE_RESPONSE_HEADERS:
            output[normalized] = str(value)
    return dict(sorted(output.items()))


def _validate_fda_https_url(url: str) -> str:
    """Accept only a reviewed absolute FDA HTTPS URL, never a proxy/userinfo URL."""
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise DrugsAtFdaCollectionError("UNAPPROVED_FDA_URL", url) from exc
    if (
        parsed.scheme != "https"
        or hostname not in {"www.fda.gov", "www.accessdata.fda.gov"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
    ):
        raise DrugsAtFdaCollectionError("UNAPPROVED_FDA_URL", url)
    return url


def _response_header_length(response: Any) -> int | None:
    raw = getattr(response, "headers", {}).get("content-length")
    if raw in {None, ""}:
        return None
    try:
        value = int(str(raw))
    except ValueError as exc:
        raise DrugsAtFdaCollectionError("HTTP_CONTENT_LENGTH_INVALID", str(raw)) from exc
    if value < 0:
        raise DrugsAtFdaCollectionError("HTTP_CONTENT_LENGTH_INVALID", str(raw))
    return value


def _buffer_bounded_response(response: Any, *, max_bytes: int) -> None:
    """Read one final 200 response exactly once while enforcing a hard cap."""
    declared = _response_header_length(response)
    if declared is not None and declared > max_bytes:
        raise DrugsAtFdaCollectionError("HTTP_BODY_TOO_LARGE", str(declared))
    iterator = getattr(response, "iter_content", None)
    try:
        chunks = iterator(chunk_size=64 * 1024) if callable(iterator) else (bytes(response.content),)
        output = bytearray()
        for chunk in chunks:
            if not chunk:
                continue
            if not isinstance(chunk, (bytes, bytearray)):
                raise DrugsAtFdaCollectionError("HTTP_STREAM_INVALID", type(chunk).__name__)
            output.extend(chunk)
            if len(output) > max_bytes:
                raise DrugsAtFdaCollectionError("HTTP_BODY_TOO_LARGE", str(len(output)))
    except DrugsAtFdaCollectionError:
        raise
    except Exception as exc:
        raise DrugsAtFdaCollectionError("HTTP_STREAM_FAILURE", type(exc).__name__) from exc
    payload = bytes(output)
    if declared is not None and len(payload) != declared:
        raise DrugsAtFdaCollectionError("HTTP_CONTENT_LENGTH_MISMATCH", f"{declared}/{len(payload)}")
    # Requests' ``content`` property becomes safe to consume after this point;
    # tests use a small namespace object and support the same replacement.
    try:
        response._content = payload
        response._content_consumed = True
    except Exception:
        pass
    try:
        response.content = payload
    except Exception:
        pass


def _safe_child(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise DrugsAtFdaCollectionError("UNSAFE_PATH", relative)
    root = root.resolve()
    candidate = (root / Path(*path.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DrugsAtFdaCollectionError("UNSAFE_PATH", relative) from exc
    return candidate


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_pointer_write(path: Path, payload: bytes) -> None:
    """Advance a private current pointer or restore the last good pointer."""
    previous = path.read_bytes() if path.exists() else None
    try:
        _atomic_write(path, payload)
        if path.read_bytes() != payload:
            raise OSError("pointer readback mismatch")
    except Exception as original:
        try:
            if previous is None:
                path.unlink(missing_ok=True)
                _fsync_directory(path.parent)
            else:
                _atomic_write(path, previous)
                if path.read_bytes() != previous:
                    raise OSError("prior pointer readback mismatch")
        except Exception as rollback_error:
            raise DrugsAtFdaCollectionError("POINTER_STATE_UNCERTAIN", type(rollback_error).__name__) from original
        raise DrugsAtFdaCollectionError("POINTER_ADVANCE_FAILED", type(original).__name__) from original


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise DrugsAtFdaCollectionError("IMMUTABLE_OBJECT_COLLISION", str(path))
        return
    _atomic_write(path, payload)
    if path.read_bytes() != payload:
        raise DrugsAtFdaCollectionError("ARCHIVE_READBACK_MISMATCH", str(path))


def _require_crlf(payload: bytes, table_name: str) -> None:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise DrugsAtFdaCollectionError("UNEXPECTED_BOM", table_name)
    without_crlf = payload.replace(b"\r\n", b"")
    if b"\n" in without_crlf or b"\r" in without_crlf:
        raise DrugsAtFdaCollectionError("UNEXPECTED_LINE_ENDING", table_name)
    if not payload.endswith(b"\r\n"):
        raise DrugsAtFdaCollectionError("UNTERMINATED_TABLE", table_name)


def _reject_nul(payload: bytes, table_name: str) -> None:
    if b"\x00" in payload:
        raise DrugsAtFdaCollectionError("UNEXPECTED_NUL", table_name)


def _validate_zip_envelope(raw_archive: bytes, archive: zipfile.ZipFile) -> None:
    """Reject polyglot/padded ZIPs; source bytes must be one plain archive."""
    if not raw_archive.startswith(b"PK\x03\x04") or archive.comment:
        raise DrugsAtFdaCollectionError("ZIP_ENVELOPE_MISMATCH", "prefix_or_comment")
    members = archive.infolist()
    if not members or min(member.header_offset for member in members) != 0:
        raise DrugsAtFdaCollectionError("ZIP_ENVELOPE_MISMATCH", "first_local_header")
    eocd = raw_archive.rfind(b"PK\x05\x06")
    if eocd < 0 or eocd + 22 > len(raw_archive):
        raise DrugsAtFdaCollectionError("ZIP_ENVELOPE_MISMATCH", "eocd")
    comment_length = int.from_bytes(raw_archive[eocd + 20:eocd + 22], "little")
    if eocd + 22 + comment_length != len(raw_archive):
        raise DrugsAtFdaCollectionError("ZIP_ENVELOPE_MISMATCH", "trailing")


def _parse_tsv(
    *, table_name: str, payload: bytes, archive_sha256: str, compressed_byte_count: int,
    uncompressed_byte_count: int, crc32: int,
    row_sink: Callable[[str, int, str, Mapping[str, str]], None] | None = None,
    retain_rows: bool = True,
    max_rows: int = DEFAULT_MAX_ROWS_PER_MEMBER,
) -> tuple[tuple[dict[str, str], ...], dict[str, Any]]:
    _require_crlf(payload, table_name)
    _reject_nul(payload, table_name)
    expected_header = EXPECTED_HEADERS[table_name]
    rows: list[dict[str, str]] = []
    repairs: list[dict[str, Any]] = []
    profile: dict[str, int] = {}
    row_count = 0
    seen_keys: set[tuple[str, ...]] = set()
    ordered_row_digest = hashlib.sha256()
    typed_row_semantic_digest = hashlib.sha256()
    # BytesIO iteration is bounded to one physical line.  ``splitlines`` would
    # duplicate every row object for the 300k-row source members.
    for row_number, physical in enumerate(BytesIO(payload), start=1):
        try:
            parsed = next(csv.reader([physical.decode("cp1252")], delimiter="\t", strict=True))
        except UnicodeDecodeError as exc:
            raise DrugsAtFdaCollectionError("INVALID_CP1252", f"{table_name}:{row_number}") from exc
        except (csv.Error, StopIteration) as exc:
            raise DrugsAtFdaCollectionError("INVALID_TSV", f"{table_name}:{row_number}") from exc
        if row_number == 1:
            if tuple(parsed) != expected_header:
                raise DrugsAtFdaCollectionError("HEADER_MISMATCH", table_name)
            continue
        actual_field_count = len(parsed)
        row_count += 1
        if row_count > max_rows:
            raise DrugsAtFdaCollectionError("MEMBER_ROW_LIMIT", table_name)
        profile[str(actual_field_count)] = profile.get(str(actual_field_count), 0) + 1
        raw_line_sha256 = _sha256(physical)
        ordered_row_digest.update(raw_line_sha256.encode("ascii"))
        ordered_row_digest.update(b"\n")
        if actual_field_count != len(expected_header):
            exception = _APPDOCS_EMPTY_FIELD_EXCEPTION
            if not (
                table_name == exception["table"]
                and archive_sha256 == exception["archive_sha256"]
                and row_number == exception["row_number"]
                and raw_line_sha256 == exception["raw_row_sha256"]
                and actual_field_count == len(expected_header) + 1
                and parsed[-2] == ""
                and parsed[0] == exception["application_docs_id"]
            ):
                raise DrugsAtFdaCollectionError("ROW_SHAPE_MISMATCH", f"{table_name}:{row_number}")
            parsed.pop(-2)
            repairs.append({
                "rule": "application_docs_empty_field_before_date", "row_number": row_number,
                "raw_row_sha256": raw_line_sha256, "expected_field_count": len(expected_header),
                "observed_field_count": actual_field_count,
            })
        row = dict(zip(expected_header, parsed, strict=True))
        row["__fda_physical_line_sha256"] = raw_line_sha256
        key = tuple(_join_value(field, row[field]) for field in ROW_IDENTITY_FIELDS[table_name])
        if any(value == "" for value in key):
            raise DrugsAtFdaCollectionError("MISSING_PRIMARY_KEY", f"{table_name}:{row_number}")
        if key in seen_keys:
            raise DrugsAtFdaCollectionError("DUPLICATE_PRIMARY_KEY", f"{table_name}:{row_number}")
        seen_keys.add(key)
        sqlite_spec = SQLITE_SCHEMA_SPEC["tables"][table_name]
        typed_values: list[Any] = [
            row_number,
            raw_line_sha256,
            *(row[column] for column in sqlite_spec["source_columns"]),
        ]
        if "SubmissionType_join" in sqlite_spec["derived_columns"]:
            typed_values.append(_ascii_right_trim(row["SubmissionType"]))
        typed_row_semantic_digest.update(canonical_json_bytes(typed_values))
        typed_row_semantic_digest.update(b"\n")
        if row_sink is not None:
            row_sink(table_name, row_number, raw_line_sha256, row)
        if retain_rows:
            rows.append(row)
    manifest_payload = {
        "contract_id": "drugs_at_fda_table_manifest.v1", "schema_version": "1.0.0",
        "table_manifest_id": f"drugs_at_fda_table_{canonical_json_sha256({'archive': archive_sha256, 'table': table_name})[:24]}",
        "release_id": f"drugs_at_fda_release_{archive_sha256[:24]}", "archive_sha256": archive_sha256,
        "table_name": table_name, "member_sha256": _sha256(payload), "compressed_byte_count": compressed_byte_count,
        "uncompressed_byte_count": uncompressed_byte_count, "zip_crc32": f"{crc32:08x}", "row_count": row_count,
        "header": list(expected_header), "primary_key_fields": list(PRIMARY_KEY_FIELDS[table_name]),
        "encoding": "cp1252", "field_count_profile": profile, "ordered_row_digest_sha256": ordered_row_digest.hexdigest(),
        "typed_row_semantic_digest_sha256": typed_row_semantic_digest.hexdigest(),
        "row_shape_repairs": repairs,
        "parser_version": PARSER_VERSION,
        "hash_scope": "canonical_payload_excluding_manifest_payload_sha256",
    }
    manifest = dict(manifest_payload)
    manifest["manifest_payload_sha256"] = canonical_json_sha256(manifest_payload)
    return tuple(rows), manifest


def parse_drugs_at_fda_zip(raw_archive: bytes, *, config: DrugsAtFdaConfig) -> ParsedDrugsAtFdaRelease:
    """Parse exact official ZIP bytes with archive and relational hardening."""
    if not isinstance(raw_archive, bytes) or not raw_archive:
        raise DrugsAtFdaCollectionError("INVALID_ARCHIVE_BYTES", "archive must be non-empty bytes")
    if len(raw_archive) > config.max_archive_bytes:
        raise DrugsAtFdaCollectionError("ARCHIVE_TOO_LARGE", str(len(raw_archive)))
    archive_sha256 = _sha256(raw_archive)
    try:
        archive = zipfile.ZipFile(BytesIO(raw_archive))
    except (OSError, zipfile.BadZipFile) as exc:
        raise DrugsAtFdaCollectionError("INVALID_ZIP", "cannot read ZIP central directory") from exc
    with archive:
        _validate_zip_envelope(raw_archive, archive)
        members = archive.infolist()
        if len(members) != config.max_member_count:
            raise DrugsAtFdaCollectionError("MEMBER_COUNT_MISMATCH", str(len(members)))
        names = [member.filename for member in members]
        if len(set(names)) != len(names):
            raise DrugsAtFdaCollectionError("DUPLICATE_ZIP_MEMBER", "duplicate member filename")
        if set(names) != set(EXPECTED_HEADERS):
            raise DrugsAtFdaCollectionError("ZIP_MEMBER_SET_MISMATCH", ",".join(sorted(names)))
        if sum(member.file_size for member in members) > config.max_in_memory_parse_uncompressed_bytes:
            raise DrugsAtFdaCollectionError("FULL_RELEASE_REQUIRES_SQLITE_STREAM", str(config.max_in_memory_parse_uncompressed_bytes))
        total_uncompressed = 0
        parsed_tables: dict[str, tuple[dict[str, str], ...]] = {}
        member_bytes: dict[str, bytes] = {}
        manifests: list[dict[str, Any]] = []
        total_rows = 0
        for member in sorted(members, key=lambda item: item.filename):
            member_path = PurePosixPath(member.filename)
            mode = (member.external_attr >> 16) & 0o170000
            if member_path.is_absolute() or ".." in member_path.parts or len(member_path.parts) != 1:
                raise DrugsAtFdaCollectionError("ZIP_SLIP", member.filename)
            if member.is_dir() or mode not in {0, stat.S_IFREG}:
                raise DrugsAtFdaCollectionError("UNSAFE_ZIP_MEMBER", member.filename)
            if member.flag_bits & 0x41:
                raise DrugsAtFdaCollectionError("ENCRYPTED_ZIP_MEMBER", member.filename)
            if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise DrugsAtFdaCollectionError("UNEXPECTED_ZIP_COMPRESSION", member.filename)
            if member.file_size <= 0 or member.file_size > config.max_member_uncompressed_bytes:
                raise DrugsAtFdaCollectionError("MEMBER_SIZE_LIMIT", member.filename)
            if member.compress_size <= 0 or member.file_size / member.compress_size > config.max_compression_ratio:
                raise DrugsAtFdaCollectionError("COMPRESSION_RATIO_LIMIT", member.filename)
            total_uncompressed += member.file_size
            if total_uncompressed > config.max_total_uncompressed_bytes:
                raise DrugsAtFdaCollectionError("TOTAL_UNCOMPRESSED_LIMIT", str(total_uncompressed))
            try:
                payload = archive.read(member)
            except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                raise DrugsAtFdaCollectionError("ZIP_READ_FAILURE", member.filename) from exc
            if len(payload) != member.file_size or (binascii.crc32(payload) & 0xffffffff) != member.CRC:
                raise DrugsAtFdaCollectionError("ZIP_MEMBER_INTEGRITY", member.filename)
            rows, manifest = _parse_tsv(
                table_name=member.filename, payload=payload, archive_sha256=archive_sha256,
                compressed_byte_count=member.compress_size, uncompressed_byte_count=member.file_size, crc32=member.CRC,
                max_rows=config.max_rows_per_member,
            )
            total_rows += int(manifest["row_count"])
            if total_rows > config.max_total_rows:
                raise DrugsAtFdaCollectionError("TOTAL_ROW_LIMIT", str(total_rows))
            parsed_tables[member.filename] = rows
            member_bytes[member.filename] = payload
            manifests.append(manifest)
    return ParsedDrugsAtFdaRelease(archive_sha256, parsed_tables, tuple(manifests), member_bytes)


def stream_drugs_at_fda_zip_to_sqlite(
    raw_archive: bytes, *, sqlite_path: Path, config: DrugsAtFdaConfig,
) -> StreamedDrugsAtFdaRelease:
    """Persist exact rows into twelve typed, release-local SQLite tables.

    The ZIP remains replay truth.  This is a compact typed query sidecar: all
    FDA values are source TEXT, with a physical row coordinate/digest and a
    single explicit right-trimmed join companion for ``SubmissionType``.  No
    foreign key is enforced because source-native orphans are facts to retain.
    """
    if not isinstance(raw_archive, bytes) or not raw_archive or len(raw_archive) > config.max_archive_bytes:
        raise DrugsAtFdaCollectionError("INVALID_ARCHIVE_BYTES", "stream archive exceeds byte policy")
    archive_sha256 = _sha256(raw_archive)
    try:
        archive = zipfile.ZipFile(BytesIO(raw_archive))
    except (OSError, zipfile.BadZipFile) as exc:
        raise DrugsAtFdaCollectionError("INVALID_ZIP", "cannot read ZIP central directory") from exc
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=OFF")
        for source_name, spec in SQLITE_SCHEMA_SPEC["tables"].items():
            sqlite_name = _quote_identifier(str(spec["sqlite_table"]))
            typed_columns = [
                *(f"{_quote_identifier(column)} {spec['column_types'][column]} NOT NULL" for column in spec["columns"]),
                f"PRIMARY KEY ({_quote_identifier('physical_line')})",
            ]
            connection.execute(f"CREATE TABLE {sqlite_name} ({', '.join(typed_columns)}) WITHOUT ROWID")
        connection.execute("CREATE TABLE table_manifests (table_name TEXT PRIMARY KEY, manifest_json TEXT NOT NULL) WITHOUT ROWID")
        # Cover every retained relationship used by the nine orphan metrics.
        for index_spec in SQLITE_SCHEMA_SPEC["indexes"]:
            connection.execute(
                f"CREATE INDEX {_quote_identifier(index_spec['name'])} ON {_quote_identifier(index_spec['table'])} ({', '.join(_quote_identifier(column) for column in index_spec['columns'])})"
            )
        manifests: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        total_rows = 0
        with archive:
            _validate_zip_envelope(raw_archive, archive)
            members = archive.infolist()
            if len(members) != config.max_member_count:
                raise DrugsAtFdaCollectionError("MEMBER_COUNT_MISMATCH", str(len(members)))
            names = [member.filename for member in members]
            if len(set(names)) != len(names):
                raise DrugsAtFdaCollectionError("DUPLICATE_ZIP_MEMBER", "duplicate member filename")
            if set(names) != set(EXPECTED_HEADERS):
                raise DrugsAtFdaCollectionError("ZIP_MEMBER_SET_MISMATCH", ",".join(sorted(names)))
            total_uncompressed = 0
            for member in sorted(members, key=lambda item: item.filename):
                member_path = PurePosixPath(member.filename)
                mode = (member.external_attr >> 16) & 0o170000
                if member_path.is_absolute() or ".." in member_path.parts or len(member_path.parts) != 1:
                    raise DrugsAtFdaCollectionError("ZIP_SLIP", member.filename)
                if member.is_dir() or mode not in {0, stat.S_IFREG}:
                    raise DrugsAtFdaCollectionError("UNSAFE_ZIP_MEMBER", member.filename)
                if member.flag_bits & 0x41:
                    raise DrugsAtFdaCollectionError("ENCRYPTED_ZIP_MEMBER", member.filename)
                if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise DrugsAtFdaCollectionError("UNEXPECTED_ZIP_COMPRESSION", member.filename)
                if member.file_size <= 0 or member.file_size > config.max_member_uncompressed_bytes:
                    raise DrugsAtFdaCollectionError("MEMBER_SIZE_LIMIT", member.filename)
                if member.compress_size <= 0 or member.file_size / member.compress_size > config.max_compression_ratio:
                    raise DrugsAtFdaCollectionError("COMPRESSION_RATIO_LIMIT", member.filename)
                total_uncompressed += member.file_size
                if total_uncompressed > config.max_total_uncompressed_bytes:
                    raise DrugsAtFdaCollectionError("TOTAL_UNCOMPRESSED_LIMIT", str(total_uncompressed))
                try:
                    payload = archive.read(member)
                except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                    raise DrugsAtFdaCollectionError("ZIP_READ_FAILURE", member.filename) from exc
                if len(payload) != member.file_size or (binascii.crc32(payload) & 0xffffffff) != member.CRC:
                    raise DrugsAtFdaCollectionError("ZIP_MEMBER_INTEGRITY", member.filename)

                def sink(table_name: str, physical_line: int, row_sha: str, row: Mapping[str, str]) -> None:
                    spec = SQLITE_SCHEMA_SPEC["tables"][table_name]
                    values = [physical_line, row_sha, *(row[column] for column in spec["source_columns"])]
                    if "SubmissionType_join" in spec["derived_columns"]:
                        values.append(_ascii_right_trim(row["SubmissionType"]))
                    columns = spec["columns"]
                    placeholders = ", ".join("?" for _ in columns)
                    connection.execute(
                        f"INSERT INTO {_quote_identifier(str(spec['sqlite_table']))} ({', '.join(_quote_identifier(column) for column in columns)}) VALUES ({placeholders})",
                        values,
                    )

                rows, manifest = _parse_tsv(
                    table_name=member.filename, payload=payload, archive_sha256=archive_sha256,
                    compressed_byte_count=member.compress_size, uncompressed_byte_count=member.file_size,
                    crc32=member.CRC, row_sink=sink, retain_rows=False,
                    max_rows=config.max_rows_per_member,
                )
                if rows:
                    raise DrugsAtFdaCollectionError("STREAM_RETAINED_ROWS", member.filename)
                counts[member.filename] = int(manifest["row_count"])
                total_rows += counts[member.filename]
                if total_rows > config.max_total_rows:
                    raise DrugsAtFdaCollectionError("TOTAL_ROW_LIMIT", str(total_rows))
                connection.execute("INSERT INTO table_manifests VALUES (?, ?)", (member.filename, canonical_json_bytes(manifest).decode("utf-8")))
                manifests.append(manifest)
        _validate_typed_sqlite_index(connection, table_row_counts=counts)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise DrugsAtFdaCollectionError("SQLITE_INTEGRITY", str(integrity))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    sqlite_semantic_digests = _typed_sqlite_semantic_digests(sqlite_path)
    source_semantic_digests = {
        str(manifest["table_name"]): str(manifest["typed_row_semantic_digest_sha256"])
        for manifest in manifests
    }
    if sqlite_semantic_digests != source_semantic_digests:
        raise DrugsAtFdaCollectionError(
            "SQLITE_SOURCE_SEMANTIC_BINDING", str(sqlite_path)
        )
    return StreamedDrugsAtFdaRelease(
        archive_sha256,
        tuple(manifests),
        counts,
        sqlite_semantic_digests,
    )


def _validate_typed_sqlite_index(
    connection: sqlite3.Connection, *, table_row_counts: Mapping[str, Any],
) -> None:
    """Check the local query sidecar against its hashed static schema contract."""
    expected_tables = set(SQLITE_TABLE_NAMES.values()) | {"table_manifests"}
    actual_tables = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    if actual_tables != expected_tables:
        raise DrugsAtFdaCollectionError("SQLITE_TABLE_SET_MISMATCH", ",".join(sorted(actual_tables)))
    for source_name, spec in SQLITE_SCHEMA_SPEC["tables"].items():
        table = str(spec["sqlite_table"])
        table_sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        if not table_sql_row or "WITHOUT ROWID" not in str(table_sql_row[0]).upper():
            raise DrugsAtFdaCollectionError("SQLITE_TABLE_LAYOUT_MISMATCH", source_name)
        columns = {
            str(row[1]): (str(row[2]).upper(), int(row[3]), int(row[5]))
            for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")
        }
        expected_columns = set(spec["columns"])
        if set(columns) != expected_columns:
            raise DrugsAtFdaCollectionError("SQLITE_COLUMN_SET_MISMATCH", source_name)
        for column in expected_columns:
            expected_type = str(spec["column_types"][column]).upper()
            expected_pk = 1 if column == "physical_line" else 0
            if columns[column] != (expected_type, 1, expected_pk):
                raise DrugsAtFdaCollectionError("SQLITE_COLUMN_CONTRACT_MISMATCH", f"{source_name}:{column}")
        expected_count = table_row_counts.get(source_name)
        actual_count = int(connection.execute(f"SELECT count(*) FROM {_quote_identifier(table)}").fetchone()[0])
        if not isinstance(expected_count, int) or actual_count != expected_count:
            raise DrugsAtFdaCollectionError("SQLITE_ROW_COUNT_MISMATCH", source_name)
    manifest_columns = {
        str(row[1]): (str(row[2]).upper(), int(row[3]), int(row[5]))
        for row in connection.execute("PRAGMA table_info(table_manifests)")
    }
    if manifest_columns != {
        "table_name": ("TEXT", 1, 1),
        "manifest_json": ("TEXT", 1, 0),
    }:
        raise DrugsAtFdaCollectionError("SQLITE_TABLE_MANIFEST_LAYOUT", "table_manifests")
    expected_indexes = {str(item["name"]): tuple(str(column) for column in item["columns"]) for item in SQLITE_SCHEMA_SPEC["indexes"]}
    found_indexes: dict[str, tuple[str, ...]] = {}
    for table in SQLITE_TABLE_NAMES.values():
        for row in connection.execute(f"PRAGMA index_list({_quote_identifier(table)})"):
            index_name = str(row[1])
            # origin ``c`` means an explicitly created index.  Primary-key
            # indexes are part of the table contract and are not duplicated.
            if len(row) > 3 and str(row[3]) == "c":
                found_indexes[index_name] = tuple(
                    str(info[2]) for info in connection.execute(f"PRAGMA index_info({_quote_identifier(index_name)})")
                )
    if found_indexes != expected_indexes:
        raise DrugsAtFdaCollectionError("SQLITE_INDEX_CONTRACT_MISMATCH", "typed index set")


def _typed_sqlite_semantic_digests(sqlite_path: Path) -> dict[str, str]:
    """Digest every persisted typed cell in deterministic physical-line order."""
    output: dict[str, str] = {}
    try:
        with sqlite3.connect(sqlite_path) as connection:
            for source_name, spec in SQLITE_SCHEMA_SPEC["tables"].items():
                columns = list(spec["columns"])
                sql = (
                    f"SELECT {', '.join(_quote_identifier(column) for column in columns)} "
                    f"FROM {_quote_identifier(str(spec['sqlite_table']))} "
                    f"ORDER BY {_quote_identifier('physical_line')}"
                )
                digest = hashlib.sha256()
                for row in connection.execute(sql):
                    digest.update(canonical_json_bytes(list(row)))
                    digest.update(b"\n")
                output[source_name] = digest.hexdigest()
    except (sqlite3.Error, ContractError) as exc:
        raise DrugsAtFdaCollectionError("SQLITE_SEMANTIC_DIGEST_FAILED", str(sqlite_path)) from exc
    return output


def _typed_sqlite_release_integrity(
    connection: sqlite3.Connection,
) -> tuple[int, dict[str, int]]:
    """Recompute release totals and every declared source-native orphan gap."""
    applications = int(
        connection.execute("SELECT count(*) FROM fda_applications").fetchone()[0]
    )
    gap_counts = {
        name: int(connection.execute(query).fetchone()[0])
        for name, query in SQLITE_ORPHAN_QUERIES.items()
    }
    plan = connection.execute(
        "EXPLAIN QUERY PLAN "
        + SQLITE_ORPHAN_QUERIES["join_actions_missing_action_lookup"]
    ).fetchall()
    if not any("idx_action_lookup" in str(row) for row in plan):
        raise DrugsAtFdaCollectionError(
            "SQLITE_QUERY_PLAN_UNINDEXED", "join action lookup"
        )
    return applications, gap_counts


def _landing_metadata(payload: bytes, expected_archive_url: str) -> tuple[date, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DrugsAtFdaCollectionError("INVALID_LANDING_ENCODING", "FDA landing page must be UTF-8") from exc
    if "<html" not in text.casefold() or expected_archive_url not in unescape(text):
        raise DrugsAtFdaCollectionError("LANDING_SHAPE_MISMATCH", "expected archive link missing")
    match = re.search(
        r"Data\s+Last\s+Updated:\s*([A-Za-z]+\s+[0-9]{1,2}(?:st|nd|rd|th)?\s*,?\s*[0-9]{4})",
        unescape(text), flags=re.IGNORECASE,
    )
    if match is None:
        raise DrugsAtFdaCollectionError("LANDING_DATE_MISSING", "Data Last Updated missing")
    raw_date = re.sub(r"(st|nd|rd|th)\b", "", match.group(1).strip(), flags=re.IGNORECASE)
    try:
        parsed = datetime.strptime(raw_date, "%B %d, %Y").date()
    except ValueError as exc:
        raise DrugsAtFdaCollectionError("LANDING_DATE_INVALID", raw_date) from exc
    return parsed, raw_date


def _archive_transport_metadata(headers: Mapping[str, str], archive: bytes, expected_date: date) -> None:
    content_type = headers.get("content-type", "").casefold()
    if not content_type.startswith("application/zip"):
        raise DrugsAtFdaCollectionError("ARCHIVE_CONTENT_TYPE", content_type)
    if headers.get("content-encoding", "").strip().casefold() not in {"", "identity"}:
        raise DrugsAtFdaCollectionError("ARCHIVE_CONTENT_ENCODING", headers.get("content-encoding", ""))
    try:
        if int(headers["content-length"]) != len(archive):
            raise DrugsAtFdaCollectionError("ARCHIVE_CONTENT_LENGTH", headers["content-length"])
    except KeyError as exc:
        raise DrugsAtFdaCollectionError("ARCHIVE_CONTENT_LENGTH_MISSING", "content-length") from exc
    except ValueError as exc:
        raise DrugsAtFdaCollectionError("ARCHIVE_CONTENT_LENGTH", headers.get("content-length", "")) from exc
    disposition = headers.get("content-disposition", "")
    token = re.search(r"filename=(?:\"?)(dafdata([0-9]{8})\.zip)", disposition, flags=re.IGNORECASE)
    if token is None:
        raise DrugsAtFdaCollectionError("ARCHIVE_RELEASE_TOKEN", disposition)
    token_date = datetime.strptime(token.group(2), "%Y%m%d").date()
    if token_date != expected_date:
        raise DrugsAtFdaCollectionError("LANDING_ARCHIVE_DATE_MISMATCH", f"{expected_date}/{token_date}")
    if "last-modified" in headers:
        try:
            parsedate_to_datetime(headers["last-modified"])
        except (TypeError, ValueError) as exc:
            raise DrugsAtFdaCollectionError("ARCHIVE_LAST_MODIFIED_INVALID", headers["last-modified"]) from exc


def _http_receipt(kind: str, source_uri: str, response: Any, received_at: str, raw_key: str) -> dict[str, Any]:
    payload = bytes(response.content)
    return {
        "kind": kind, "source_uri": source_uri, "final_url": str(getattr(response, "url", source_uri)), "status_code": int(response.status_code),
        "response_headers": _safe_headers(response.headers), "exact_response_sha256": _sha256(payload),
        "byte_count": len(payload), "raw_object_key": raw_key, "received_at": received_at,
    }


def build_release_receipt(
    *, landing_before: Any, archive_response: Any, landing_after: Any, config: DrugsAtFdaConfig,
    observed_at: str, received_at_by_kind: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], bytes, tuple[bytes, bytes]]:
    """Build one three-observation transport receipt, never using timestamps as identity."""
    for response in (landing_before, archive_response, landing_after):
        if int(response.status_code) != 200:
            raise DrugsAtFdaCollectionError("HTTP_STATUS", str(response.status_code))
    before_bytes, archive_bytes, after_bytes = bytes(landing_before.content), bytes(archive_response.content), bytes(landing_after.content)
    before_date, _ = _landing_metadata(before_bytes, config.archive_url)
    after_date, _ = _landing_metadata(after_bytes, config.archive_url)
    if before_date != after_date:
        raise DrugsAtFdaCollectionError("LANDING_RELEASE_RACED", f"{before_date}/{after_date}")
    archive_headers = _safe_headers(archive_response.headers)
    _archive_transport_metadata(archive_headers, archive_bytes, before_date)
    archive_sha256 = _sha256(archive_bytes)
    received = dict(received_at_by_kind or {})
    received.setdefault("landing_before", observed_at)
    received.setdefault("archive", observed_at)
    received.setdefault("landing_after", observed_at)
    receipt_payload = {
        "contract_id": "drugs_at_fda_release_receipt.v1", "schema_version": "1.0.0",
        "release_id": f"drugs_at_fda_release_{archive_sha256[:24]}", "source_id": SOURCE_ID,
        "source_url": config.landing_url, "archive_sha256": archive_sha256, "archive_byte_count": len(archive_bytes),
        "source_release_date": before_date.isoformat(), "source_release_time": None, "observed_at": observed_at,
        "http_receipts": [
            _http_receipt("landing_before", config.landing_url, landing_before, received["landing_before"], f"biocatalyst/raw/drugs_at_fda/landing/{_sha256(before_bytes)}.html"),
            _http_receipt("archive", config.archive_url, archive_response, received["archive"], f"biocatalyst/raw/drugs_at_fda/archive/{archive_sha256}.zip"),
            _http_receipt("landing_after", config.landing_url, landing_after, received["landing_after"], f"biocatalyst/raw/drugs_at_fda/landing/{_sha256(after_bytes)}.html"),
        ],
        "parser_version": PARSER_VERSION, "license_class": "us_government_source_facts",
        "hash_scope": "canonical_payload_excluding_receipt_payload_sha256",
    }
    receipt = dict(receipt_payload)
    receipt["receipt_payload_sha256"] = canonical_json_sha256(receipt_payload)
    validate_drugs_at_fda_release_receipt(
        receipt,
        raw_bodies_by_kind={"landing_before": before_bytes, "archive": archive_bytes, "landing_after": after_bytes},
    )
    return receipt, archive_bytes, (before_bytes, after_bytes)


class DrugsAtFdaCollector:
    """Separate dark B4A transaction with private raw archive and state pointer."""

    def __init__(self, *, private_root: Path, state_root: Path, config: DrugsAtFdaConfig,
                 session: requests.Session | None = None, now_fn: Callable[[], datetime] = _utc_now,
                 private_store: BinaryObjectStore | None = None) -> None:
        self.private_root = Path(private_root).resolve()
        self.state_root = Path(state_root).resolve()
        if self.private_root == self.state_root or self.private_root in self.state_root.parents or self.state_root in self.private_root.parents:
            raise ValueError("private_root and state_root must be disjoint non-ancestor paths")
        self.config = config
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.now_fn = now_fn
        self.private_store = private_store

    def _get(self, url: str, accept: str) -> Any:
        """Follow only reviewed FDA redirects and stream a bounded final body.

        ``requests`` automatic redirect handling would fetch an arbitrary next
        hop before this collector can vet it.  Manual redirect handling makes
        every request URL and every response-reported final URL part of the
        acceptance boundary.
        """
        current = _validate_fda_https_url(url)
        headers = {"Accept": accept, "Accept-Encoding": "identity", "User-Agent": self.config.user_agent}
        maximum = self.config.max_archive_bytes if accept == "application/zip" else self.config.max_landing_bytes
        for redirect_count in range(self.config.max_redirects + 1):
            try:
                response = self.session.get(
                    current,
                    headers=headers,
                    timeout=(self.config.connect_timeout_seconds, self.config.read_timeout_seconds),
                    allow_redirects=False,
                    stream=True,
                )
            except requests.RequestException as exc:
                raise DrugsAtFdaCollectionError("HTTP_REQUEST_FAILURE", current) from exc
            close = getattr(response, "close", None)
            try:
                response_url = str(getattr(response, "url", current) or current)
                _validate_fda_https_url(response_url)
                status = int(getattr(response, "status_code", 0))
                if status in {301, 302, 303, 307, 308}:
                    if redirect_count >= self.config.max_redirects:
                        raise DrugsAtFdaCollectionError("HTTP_REDIRECT_LIMIT", current)
                    location = getattr(response, "headers", {}).get("location")
                    if not isinstance(location, str) or not location:
                        raise DrugsAtFdaCollectionError("HTTP_REDIRECT_LOCATION_MISSING", current)
                    current = _validate_fda_https_url(urljoin(response_url, location))
                    continue
                if status != 200:
                    raise DrugsAtFdaCollectionError("HTTP_STATUS", str(status))
                content_encoding = str(getattr(response, "headers", {}).get("content-encoding", "")).strip().casefold()
                if content_encoding not in {"", "identity"}:
                    raise DrugsAtFdaCollectionError("HTTP_CONTENT_ENCODING", content_encoding)
                _buffer_bounded_response(response, max_bytes=maximum)
                return response
            finally:
                if callable(close):
                    close()
        raise DrugsAtFdaCollectionError("HTTP_REDIRECT_LIMIT", current)

    def _require_network_authorization(self) -> None:
        registry_path = self.config.source_registry_path or (Path(__file__).resolve().parents[2] / "config/biocatalyst_sources.yml")
        try:
            registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            source = registry["sources"][SOURCE_ID]
        except (OSError, TypeError, KeyError, yaml.YAMLError) as exc:
            raise DrugsAtFdaCollectionError("SOURCE_REGISTRY_UNAVAILABLE", str(registry_path)) from exc
        if source.get("source_id") != SOURCE_ID or source.get("production_ingest_allowed") is not True:
            raise DrugsAtFdaCollectionError("SOURCE_INGEST_BLOCKED", "Drugs@FDA registry does not permit production collection")
        if not self.config.require_private_mirror or self.private_store is None:
            raise DrugsAtFdaCollectionError("PRIVATE_MIRROR_REQUIRED", "armed collection requires a dedicated verified private mirror")

    def collect(self) -> DrugsAtFdaPublicationResult:
        """Acquire landing-before/archive/landing-after under the reviewed seam."""
        self._require_network_authorization()
        before = self._get(self.config.landing_url, "text/html")
        before_at = _iso(self.now_fn())
        archive = self._get(self.config.archive_url, "application/zip")
        archive_at = _iso(self.now_fn())
        after = self._get(self.config.landing_url, "text/html")
        after_at = _iso(self.now_fn())
        return self.publish_responses(before, archive, after, received_at_by_kind={"landing_before": before_at, "archive": archive_at, "landing_after": after_at})

    def publish_responses(self, landing_before: Any, archive: Any, landing_after: Any, *, received_at_by_kind: Mapping[str, str] | None = None) -> DrugsAtFdaPublicationResult:
        """Serialize same-state publications across workers before staging."""
        try:
            self.state_root.mkdir(parents=True, exist_ok=True)
            lock_handle = (self.state_root / "publication.lock").open("a+b")
        except OSError as exc:
            raise DrugsAtFdaCollectionError("PUBLICATION_LOCK_FAILED", str(self.state_root)) from exc
        with lock_handle:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                raise DrugsAtFdaCollectionError("PUBLICATION_LOCK_FAILED", str(self.state_root)) from exc
            return self._publish_responses_locked(
                landing_before,
                archive,
                landing_after,
                received_at_by_kind=received_at_by_kind,
            )

    def _publish_responses_locked(
        self,
        landing_before: Any,
        archive: Any,
        landing_after: Any,
        *,
        received_at_by_kind: Mapping[str, str] | None = None,
    ) -> DrugsAtFdaPublicationResult:
        observed_at = _iso(self.now_fn())
        candidate_receipt, raw_archive, landing_bytes = build_release_receipt(
            landing_before=landing_before, archive_response=archive, landing_after=landing_after,
            config=self.config, observed_at=observed_at, received_at_by_kind=received_at_by_kind,
        )
        # Retain exact transport evidence before ZIP parsing.  A malformed or
        # newly-shaped archive is therefore quarantinable evidence, never an
        # invisible failed fetch and never a successful release receipt.
        self._archive_transport_attempt(candidate_receipt, raw_archive, landing_bytes)
        receipt = self._canonical_release_receipt(candidate_receipt)
        generation = self.state_root / "generations" / str(receipt["release_id"])
        if generation.exists():
            return self._repair_existing_generation_pointer(receipt, generation)
        stage = self.state_root / ".staging" / str(receipt["release_id"])
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=False)
        streamed = stream_drugs_at_fda_zip_to_sqlite(raw_archive, sqlite_path=stage / "release.sqlite", config=self.config)
        if streamed.archive_sha256 != receipt["archive_sha256"]:
            raise DrugsAtFdaCollectionError("ARCHIVE_RECEIPT_BINDING", "streamed archive hash mismatch")
        for manifest in streamed.table_manifests:
            validate_drugs_at_fda_table_manifest(manifest, receipt)
        canonical_mirrors = self._ensure_canonical_private_artifacts(
            receipt, raw_archive, landing_bytes, streamed.table_manifests,
        )
        # A crash may leave the first observation's canonical receipt/raw bytes
        # but no derived generation.  A later same-archive retry can observe a
        # different landing page; validate the immutable canonical bodies, not
        # those later transport-attempt bytes, before completing the release.
        canonical_bodies = {
            str(item["kind"]): _safe_child(
                self.private_root, str(item["raw_object_key"])
            ).read_bytes()
            for item in receipt["http_receipts"]
        }
        validate_drugs_at_fda_release_receipt(
            receipt,
            raw_bodies_by_kind=canonical_bodies,
        )
        return self._commit_private_sqlite(receipt, streamed, stage, canonical_mirrors)

    def _archive_transport_attempt(self, receipt: Mapping[str, Any], archive: bytes, landing_bytes: Sequence[bytes]) -> None:
        for http_receipt, body in zip(receipt["http_receipts"], (landing_bytes[0], archive, landing_bytes[1]), strict=True):
            _write_immutable(_safe_child(self.private_root, str(http_receipt["raw_object_key"])), body)
            self._mirror_bytes(str(http_receipt["raw_object_key"]), body)
        observation_id = canonical_json_sha256(receipt)[:24]
        path = _safe_child(
            self.private_root,
            f"biocatalyst/attempts/drugs_at_fda/{receipt['archive_sha256']}/{observation_id}.json",
        )
        _write_immutable(path, canonical_json_bytes(receipt) + b"\n")
        self._mirror_bytes(
            f"biocatalyst/attempts/drugs_at_fda/{receipt['archive_sha256']}/{observation_id}.json",
            canonical_json_bytes(receipt) + b"\n",
        )

    def _canonical_release_receipt(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        path = _safe_child(self.private_root, f"biocatalyst/receipts/drugs_at_fda/{candidate['release_id']}.json")
        if not path.exists():
            return dict(candidate)
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DrugsAtFdaCollectionError("CANONICAL_RECEIPT_UNREADABLE", str(path)) from exc
        validate_drugs_at_fda_release_receipt(prior)
        if prior.get("archive_sha256") != candidate.get("archive_sha256"):
            raise DrugsAtFdaCollectionError("CANONICAL_RECEIPT_COLLISION", str(candidate["release_id"]))
        return prior

    def _mirror_bytes(self, object_key: str, payload: bytes, *, content_type: str = "application/octet-stream") -> MirrorReceipt | None:
        if self.private_store is None:
            if self.config.require_private_mirror:
                raise DrugsAtFdaCollectionError("PRIVATE_MIRROR_REQUIRED", object_key)
            return None
        try:
            return mirror_bytes_verified(self.private_store, object_key=object_key, payload=payload, content_type=content_type)
        except StorageError as exc:
            raise DrugsAtFdaCollectionError("PRIVATE_MIRROR_READBACK_FAILED", exc.code) from exc

    def _ensure_canonical_private_artifacts(
        self,
        receipt: Mapping[str, Any],
        archive: bytes,
        landing_bytes: Sequence[bytes],
        manifests: Sequence[Mapping[str, Any]],
    ) -> list[MirrorReceipt]:
        """Repair/check immutable canonical evidence before a generation commit."""
        candidates = dict(zip(
            (str(item["raw_object_key"]) for item in receipt["http_receipts"]),
            (landing_bytes[0], archive, landing_bytes[1]),
            strict=True,
        ))
        mirrors: list[MirrorReceipt] = []
        for item in receipt["http_receipts"]:
            key = str(item["raw_object_key"])
            path = _safe_child(self.private_root, key)
            payload = path.read_bytes() if path.exists() else candidates.get(key)
            if not isinstance(payload, bytes) or _sha256(payload) != item["exact_response_sha256"]:
                raise DrugsAtFdaCollectionError("CANONICAL_RAW_UNAVAILABLE", key)
            _write_immutable(path, payload)
            mirrored = self._mirror_bytes(key, payload)
            if mirrored is not None:
                mirrors.append(mirrored)
        receipt_key = f"biocatalyst/receipts/drugs_at_fda/{receipt['release_id']}.json"
        receipt_bytes = canonical_json_bytes(receipt) + b"\n"
        _write_immutable(_safe_child(self.private_root, receipt_key), receipt_bytes)
        mirrored = self._mirror_bytes(receipt_key, receipt_bytes, content_type="application/json")
        if mirrored is not None:
            mirrors.append(mirrored)
        for manifest in manifests:
            key = f"biocatalyst/manifests/drugs_at_fda/{receipt['release_id']}/{manifest['table_name']}.json"
            payload = canonical_json_bytes(manifest) + b"\n"
            _write_immutable(_safe_child(self.private_root, key), payload)
            mirrored = self._mirror_bytes(key, payload, content_type="application/json")
            if mirrored is not None:
                mirrors.append(mirrored)
        return mirrors

    @staticmethod
    def _remote_commit_document(
        receipt: Mapping[str, Any], mirrors: Sequence[MirrorReceipt], logical_inventory: Mapping[str, Any],
    ) -> tuple[str, bytes]:
        objects: dict[str, dict[str, Any]] = {}
        for item in mirrors:
            row = {"object_key": item.object_key, "sha256": item.sha256, "byte_count": item.byte_count}
            prior = objects.setdefault(item.object_key, row)
            if prior != row:
                raise DrugsAtFdaCollectionError("PRIVATE_MIRROR_RECEIPT_COLLISION", str(receipt["release_id"]))
        expected_keys = {
            *(str(item["raw_object_key"]) for item in receipt["http_receipts"]),
            f"biocatalyst/receipts/drugs_at_fda/{receipt['release_id']}.json",
            *(f"biocatalyst/manifests/drugs_at_fda/{receipt['release_id']}/{table_name}.json" for table_name in EXPECTED_HEADERS),
        }
        if set(objects) != expected_keys:
            raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_COMMIT_OBJECT_SET", str(receipt["release_id"]))
        payload = {
            "schema_version": "1.0.0", "kind": "drugs_at_fda_private_remote_commit",
            "release_id": receipt["release_id"], "archive_sha256": receipt["archive_sha256"],
            "required_objects": [objects[key] for key in sorted(objects)],
            "logical_inventory": dict(logical_inventory),
            "logical_inventory_sha256": canonical_json_sha256(logical_inventory),
            "parser_version": PARSER_VERSION,
            "source_schema_version": "drugs_at_fda_12_tab_tables_2025_01_10",
        }
        digest = canonical_json_sha256(payload)
        document = dict(payload)
        document["commit_payload_sha256"] = digest
        return f"biocatalyst/commits/drugs_at_fda/{receipt['release_id']}/{digest}.json", canonical_json_bytes(document) + b"\n"

    def _commit_private_sqlite(
        self,
        receipt: Mapping[str, Any],
        streamed: StreamedDrugsAtFdaRelease,
        stage: Path,
        canonical_mirrors: Sequence[MirrorReceipt],
    ) -> DrugsAtFdaPublicationResult:
        release_id = str(receipt["release_id"])
        generation_root = self.state_root / "generations"
        generation = generation_root / release_id
        connection = sqlite3.connect(stage / "release.sqlite")
        try:
            applications, gap_counts = _typed_sqlite_release_integrity(connection)
        finally:
            connection.close()
        if receipt["archive_sha256"] == _APPDOCS_EMPTY_FIELD_EXCEPTION["archive_sha256"]:
            if sum(streamed.table_row_counts.values()) != _KNOWN_20260731_TOTAL_ROWS or gap_counts != _KNOWN_20260731_ARCHIVE_GAPS:
                raise DrugsAtFdaCollectionError("KNOWN_RELEASE_RECONCILIATION_FAILED", str(receipt["release_id"]))
        integrity = {"policy": "retain_and_quantify_source_native_orphans_never_invent_parents", "source_quality_gaps": gap_counts}
        manifest_payload = {
            "schema_version": "1.0.0", "release_id": release_id, "source_id": SOURCE_ID,
            "archive_sha256": receipt["archive_sha256"], "source_release_date": receipt["source_release_date"],
            "source_release_time": None, "observed_at": receipt["observed_at"],
            "coverage_class": "fda_cder_approved_product_release", "application_count": applications,
            "table_row_counts": streamed.table_row_counts, "table_manifests": list(streamed.table_manifests),
            "sqlite_schema_spec_sha256": SQLITE_SCHEMA_SPEC_SHA256,
            "sqlite_table_semantic_row_digests": streamed.sqlite_table_semantic_row_digests,
            "integrity": integrity, "storage": "private_release_local_sqlite_query_index",
            "forbidden_claims": list(FORBIDDEN_DERIVED_CLAIMS),
        }
        manifest = dict(manifest_payload)
        manifest["manifest_payload_sha256"] = canonical_json_sha256(manifest_payload)
        _atomic_write(stage / "manifest.json", canonical_json_bytes(manifest) + b"\n")
        _atomic_write(stage / "index.json", canonical_json_bytes({
            "release_id": release_id, "archive_sha256": receipt["archive_sha256"],
            "applications": applications, "query_backend": "private_release_local_sqlite",
            "generation_manifest_payload_sha256": manifest["manifest_payload_sha256"],
            "sqlite_schema_spec_sha256": SQLITE_SCHEMA_SPEC_SHA256,
            "sqlite_table_semantic_row_digests": streamed.sqlite_table_semantic_row_digests,
        }) + b"\n")
        remote_commit_key: str | None = None
        remote_commit_sha: str | None = None
        if self.config.require_private_mirror:
            # The exact source archive, canonical receipt, and per-table
            # manifests are mirrored/read back.  SQLite is a rebuildable local
            # query index and intentionally never copied through a bytes-only
            # R2 interface that would break the release memory budget.
            logical_inventory = {
                "generation_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "application_count": applications,
                "source_quality_gaps": gap_counts,
                "table_row_counts": streamed.table_row_counts,
                "table_manifest_payload_sha256": {
                    str(item["table_name"]): str(item["manifest_payload_sha256"])
                    for item in streamed.table_manifests
                },
                "sqlite_query_index": "local_rebuildable_from_exact_remote_archive",
                "sqlite_schema_spec_sha256": SQLITE_SCHEMA_SPEC_SHA256,
                "sqlite_table_semantic_row_digests": streamed.sqlite_table_semantic_row_digests,
            }
            remote_commit_key, commit_bytes = self._remote_commit_document(receipt, canonical_mirrors, logical_inventory)
            commit_receipt = self._mirror_bytes(remote_commit_key, commit_bytes, content_type="application/json")
            if commit_receipt is None:
                raise DrugsAtFdaCollectionError("PRIVATE_MIRROR_REQUIRED", remote_commit_key)
            _atomic_write(stage / "remote_commit.json", commit_bytes)
            remote_commit_sha = commit_receipt.sha256
        generation_root.mkdir(parents=True, exist_ok=True)
        if generation.exists():
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_COLLISION", release_id)
        os.replace(stage, generation)
        _fsync_directory(generation_root)
        pointer = {"release_id": release_id, "archive_sha256": receipt["archive_sha256"], "manifest_sha256": _sha256((generation / "manifest.json").read_bytes())}
        if remote_commit_key is not None and remote_commit_sha is not None:
            pointer.update({"private_remote_commit_object_key": remote_commit_key, "private_remote_commit_sha256": remote_commit_sha})
        _atomic_pointer_write(self.state_root / "current.json", canonical_json_bytes(pointer) + b"\n")
        return DrugsAtFdaPublicationResult(release_id, str(receipt["archive_sha256"]), generation, self.state_root / "current.json", applications, integrity)

    def _repair_existing_generation_pointer(
        self, receipt: Mapping[str, Any], generation: Path,
    ) -> DrugsAtFdaPublicationResult:
        """Recover safely from a crash after immutable generation rename."""
        required = ("release.sqlite", "manifest.json", "index.json")
        if any(not (generation / name).is_file() for name in required):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_INCOMPLETE", str(generation))
        try:
            manifest = json.loads((generation / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_UNREADABLE", str(generation)) from exc
        manifest_payload = {
            key: value for key, value in manifest.items()
            if key != "manifest_payload_sha256"
        }
        if manifest.get("manifest_payload_sha256") != canonical_json_sha256(manifest_payload):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_MANIFEST_HASH", str(generation))
        if manifest.get("release_id") != receipt.get("release_id") or manifest.get("archive_sha256") != receipt.get("archive_sha256"):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_BINDING", str(generation))
        expected_manifest_fields = {
            "source_id": SOURCE_ID,
            "source_release_date": receipt.get("source_release_date"),
            "source_release_time": receipt.get("source_release_time"),
            "observed_at": receipt.get("observed_at"),
            "coverage_class": "fda_cder_approved_product_release",
            "storage": "private_release_local_sqlite_query_index",
            "forbidden_claims": list(FORBIDDEN_DERIVED_CLAIMS),
        }
        if any(manifest.get(key) != value for key, value in expected_manifest_fields.items()):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_METADATA_BINDING", str(generation))
        if manifest.get("sqlite_schema_spec_sha256") != SQLITE_SCHEMA_SPEC_SHA256:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_SCHEMA_BINDING", str(generation))
        counts = manifest.get("table_row_counts")
        if not isinstance(counts, Mapping) or set(counts) != set(EXPECTED_HEADERS):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_ROW_COUNTS", str(generation))
        semantic_digests = manifest.get("sqlite_table_semantic_row_digests")
        if not isinstance(semantic_digests, Mapping) or set(semantic_digests) != set(EXPECTED_HEADERS):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_SEMANTIC_DIGESTS", str(generation))
        try:
            index = json.loads((generation / "index.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_INDEX_UNREADABLE", str(generation)) from exc
        if (
            index.get("release_id") != receipt.get("release_id")
            or index.get("archive_sha256") != receipt.get("archive_sha256")
            or index.get("applications") != manifest.get("application_count")
            or index.get("query_backend") != "private_release_local_sqlite"
            or index.get("generation_manifest_payload_sha256") != manifest.get("manifest_payload_sha256")
            or index.get("sqlite_schema_spec_sha256") != SQLITE_SCHEMA_SPEC_SHA256
            or index.get("sqlite_table_semantic_row_digests") != semantic_digests
        ):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_INDEX_BINDING", str(generation))
        try:
            with sqlite3.connect(generation / "release.sqlite") as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DrugsAtFdaCollectionError("SQLITE_INTEGRITY", str(generation))
                _validate_typed_sqlite_index(connection, table_row_counts=counts)
                applications, gap_counts = _typed_sqlite_release_integrity(connection)
        except sqlite3.Error as exc:
            raise DrugsAtFdaCollectionError("SQLITE_INTEGRITY", str(generation)) from exc
        expected_integrity = {
            "policy": "retain_and_quantify_source_native_orphans_never_invent_parents",
            "source_quality_gaps": gap_counts,
        }
        if (
            manifest.get("application_count") != applications
            or manifest.get("integrity") != expected_integrity
        ):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_INTEGRITY_BINDING", str(generation))
        if _typed_sqlite_semantic_digests(generation / "release.sqlite") != semantic_digests:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_SEMANTIC_DIGEST_MISMATCH", str(generation))
        manifest_rows = manifest.get("table_manifests")
        if (
            not isinstance(manifest_rows, list)
            or len(manifest_rows) != len(EXPECTED_HEADERS)
            or any(not isinstance(item, Mapping) for item in manifest_rows)
        ):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_TABLE_MANIFESTS", str(generation))
        table_manifest_by_name = {
            str(item.get("table_name")): item for item in manifest_rows
        }
        if len(table_manifest_by_name) != len(manifest_rows) or set(table_manifest_by_name) != set(EXPECTED_HEADERS):
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_TABLE_MANIFESTS", str(generation))
        source_semantic_digests = {
            table_name: table_manifest.get("typed_row_semantic_digest_sha256")
            for table_name, table_manifest in table_manifest_by_name.items()
        }
        if semantic_digests != source_semantic_digests:
            raise DrugsAtFdaCollectionError(
                "PRIVATE_GENERATION_SOURCE_SEMANTIC_BINDING", str(generation)
            )
        expected_manifests = {
            str(item["table_name"]): canonical_json_bytes(item).decode("utf-8")
            for item in manifest_rows
        }
        try:
            with sqlite3.connect(generation / "release.sqlite") as connection:
                stored_manifests = {str(row[0]): str(row[1]) for row in connection.execute("SELECT table_name, manifest_json FROM table_manifests")}
        except sqlite3.Error as exc:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_TABLE_MANIFESTS", str(generation)) from exc
        if set(expected_manifests) != set(EXPECTED_HEADERS) or stored_manifests != expected_manifests:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_TABLE_MANIFESTS", str(generation))
        # Mutually-consistent local JSON/SQLite forgeries are not evidence.
        # Rebind the canonical receipt and every table manifest to the exact
        # immutable landing/archive bytes before repairing visibility.
        try:
            raw_bodies = {
                str(item["kind"]): _safe_child(
                    self.private_root, str(item["raw_object_key"])
                ).read_bytes()
                for item in receipt["http_receipts"]
            }
            validate_drugs_at_fda_release_receipt(
                receipt,
                raw_bodies_by_kind=raw_bodies,
            )
            archive_bytes = raw_bodies["archive"]
            with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
                _validate_zip_envelope(archive_bytes, archive)
                members = archive.infolist()
                names = [member.filename for member in members]
                if (
                    len(members) != len(EXPECTED_HEADERS)
                    or len(set(names)) != len(names)
                    or set(names) != set(EXPECTED_HEADERS)
                ):
                    raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_SOURCE_MEMBER_SET", str(generation))
                member_by_name = {member.filename: member for member in members}
                for table_name, table_manifest in table_manifest_by_name.items():
                    member = member_by_name[table_name]
                    if (
                        table_manifest.get("compressed_byte_count") != member.compress_size
                        or table_manifest.get("uncompressed_byte_count") != member.file_size
                        or table_manifest.get("zip_crc32") != f"{member.CRC:08x}"
                        or table_manifest.get("row_count") != counts.get(table_name)
                    ):
                        raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_TABLE_MANIFEST_BINDING", table_name)
                    validate_drugs_at_fda_table_manifest(
                        table_manifest,
                        receipt,
                        exact_member_bytes=archive.read(member),
                    )
        except (
            OSError,
            UnicodeDecodeError,
            zipfile.BadZipFile,
            RuntimeError,
            NotImplementedError,
            KeyError,
            ContractError,
        ) as exc:
            raise DrugsAtFdaCollectionError("PRIVATE_GENERATION_SOURCE_BINDING", str(generation)) from exc
        current_path = self.state_root / "current.json"
        current: Mapping[str, Any] | None = None
        if current_path.exists():
            try:
                current = json.loads(current_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DrugsAtFdaCollectionError("CURRENT_POINTER_UNREADABLE", str(current_path)) from exc
            # An idempotent replay of an older exact archive may repair only
            # its own missing pointer.  It can never roll a visible pointer
            # back from a different release merely because its generation is
            # still present locally.
            if current.get("release_id") != receipt.get("release_id"):
                return DrugsAtFdaPublicationResult(
                    str(receipt["release_id"]), str(receipt["archive_sha256"]), generation,
                    current_path, int(manifest["application_count"]), manifest["integrity"],
                )
        pointer = {"release_id": receipt["release_id"], "archive_sha256": receipt["archive_sha256"], "manifest_sha256": _sha256((generation / "manifest.json").read_bytes())}
        commit = generation / "remote_commit.json"
        if self.config.require_private_mirror:
            if self.private_store is None or not commit.is_file():
                raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_COMMIT_REQUIRED", str(generation))
            try:
                document = json.loads(commit.read_text(encoding="utf-8"))
                expected_manifest_hashes = {
                    str(item["table_name"]): str(item["manifest_payload_sha256"])
                    for item in manifest.get("table_manifests", [])
                    if isinstance(item, Mapping)
                }
                expected_remote_keys = {
                    *(str(item["raw_object_key"]) for item in receipt["http_receipts"]),
                    f"biocatalyst/receipts/drugs_at_fda/{receipt['release_id']}.json",
                    *(f"biocatalyst/manifests/drugs_at_fda/{receipt['release_id']}/{table_name}.json" for table_name in EXPECTED_HEADERS),
                }
                remote_objects = document.get("required_objects", [])
                remote_keys = {str(item.get("object_key")) for item in remote_objects if isinstance(item, Mapping)}
                logical_inventory = document.get("logical_inventory")
                if not isinstance(logical_inventory, Mapping) or not isinstance(remote_objects, list):
                    raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_COMMIT_READBACK_FAILED", str(generation))
                key = f"biocatalyst/commits/drugs_at_fda/{receipt['release_id']}/{document['commit_payload_sha256']}.json"
                payload = {name: value for name, value in document.items() if name != "commit_payload_sha256"}
                if (
                    document.get("commit_payload_sha256") != canonical_json_sha256(payload)
                    or document.get("release_id") != receipt["release_id"]
                    or document.get("archive_sha256") != receipt["archive_sha256"]
                    or document.get("logical_inventory_sha256") != canonical_json_sha256(logical_inventory)
                    or logical_inventory.get("generation_manifest_payload_sha256") != manifest.get("manifest_payload_sha256")
                    or logical_inventory.get("application_count") != applications
                    or logical_inventory.get("source_quality_gaps") != gap_counts
                    or logical_inventory.get("table_row_counts") != counts
                    or logical_inventory.get("sqlite_schema_spec_sha256") != SQLITE_SCHEMA_SPEC_SHA256
                    or logical_inventory.get("sqlite_table_semantic_row_digests") != semantic_digests
                    or logical_inventory.get("table_manifest_payload_sha256") != expected_manifest_hashes
                    or remote_keys != expected_remote_keys
                    or len(remote_objects) != len(expected_remote_keys)
                    or self.private_store.get_bytes(key) != commit.read_bytes()
                ):
                    raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_COMMIT_READBACK_FAILED", key)
                for remote_object in remote_objects:
                    if not isinstance(remote_object, Mapping):
                        raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_COMMIT_READBACK_FAILED", key)
                    object_key = str(remote_object["object_key"])
                    body = self.private_store.get_bytes(object_key)
                    if (
                        not isinstance(body, bytes)
                        or _sha256(body) != remote_object.get("sha256")
                        or len(body) != remote_object.get("byte_count")
                    ):
                        raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_OBJECT_READBACK_FAILED", object_key)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, StorageError) as exc:
                raise DrugsAtFdaCollectionError("PRIVATE_REMOTE_COMMIT_READBACK_FAILED", str(generation)) from exc
            pointer.update({"private_remote_commit_object_key": key, "private_remote_commit_sha256": _sha256(commit.read_bytes())})
        if current is not None:
            if dict(current) != pointer:
                raise DrugsAtFdaCollectionError("CURRENT_POINTER_BINDING", str(current_path))
            return DrugsAtFdaPublicationResult(str(receipt["release_id"]), str(receipt["archive_sha256"]), generation, current_path, int(manifest["application_count"]), manifest["integrity"])
        _atomic_pointer_write(current_path, canonical_json_bytes(pointer) + b"\n")
        return DrugsAtFdaPublicationResult(str(receipt["release_id"]), str(receipt["archive_sha256"]), generation, current_path, int(manifest["application_count"]), manifest["integrity"])
