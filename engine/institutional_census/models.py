"""Canonical identities and receipts for the institutional 13F evidence plane.

JSON receipts and manifests are the authority.  Parquet objects are immutable,
hash-bound query projections; their rows are never used to derive receipt
identity after publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


EVIDENCE_PREFIX = "smart-money/13f/evidence/v1"
RAW_RECEIPT_SCHEMA = "institutional_13f.raw_evidence_receipt/v1"
CATALOG_MANIFEST_SCHEMA = "institutional_13f.catalog_generation_manifest/v1"
CATALOG_POINTER_SCHEMA = "institutional_13f.catalog_current_pointer/v1"
SOURCE_RECEIPTS_SCHEMA = "institutional_13f.catalog_source_receipts/v1"
COVERAGE_SCHEMA = "institutional_13f.catalog_coverage/v1"

RAW_RECEIPT_ID_PREFIX = "i13fraw_"
GENERATION_ID_PREFIX = "i13fgen_"

HOLDING_BUCKET_COUNT = 64
HOLDING_BUCKET_ROLES = tuple(
    f"holdings_bucket_{index:02d}_parquet" for index in range(HOLDING_BUCKET_COUNT)
)
CATALOG_ARTIFACT_ROLES = (
    "filings_parquet",
    *HOLDING_BUCKET_ROLES,
    "manager_relationships_parquet",
    "source_receipts_json",
    "coverage_json",
)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$")
_IDENTITY_RE = re.compile(r"^i13f(?:raw|gen)_[a-f0-9]{64}$")
_KEY_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._=-]*$")
_ALLOWED_FORMS = frozenset({"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"})
_CONTENT_TYPE_EXTENSIONS = {
    "application/octet-stream": "bin",
    "application/json": "json",
    "application/vnd.apache.parquet": "parquet",
}


class Institutional13FError(RuntimeError):
    """An institutional 13F object cannot be safely trusted or published."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the sole authoritative JSON encoding used by this package."""
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise Institutional13FError("value is not canonical-JSON encodable") from exc
    return (rendered + "\n").encode("utf-8")


def decode_canonical_json(payload: bytes, *, label: str) -> dict[str, Any]:
    """Decode strict UTF-8 JSON, rejecting duplicates and non-canonical bytes."""
    if type(payload) is not bytes:
        raise Institutional13FError(f"{label} must be exact bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite constant: {value}")

    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise Institutional13FError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise Institutional13FError(f"{label} must be a JSON object")
    if canonical_json_bytes(decoded) != payload:
        raise Institutional13FError(f"{label} is not canonically encoded")
    return decoded


def normalize_report_period(value: str | date) -> str:
    if isinstance(value, datetime):
        raise Institutional13FError("report_period must be a calendar date")
    text = value.isoformat() if isinstance(value, date) else str(value or "")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise Institutional13FError("report_period must be an ISO calendar date") from exc
    if parsed.isoformat() != text:
        raise Institutional13FError("report_period must be normalized as YYYY-MM-DD")
    return text


def normalize_utc(value: str | datetime, *, field: str) -> str:
    """Normalize an explicit aware timestamp without consulting the system clock."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "")
        if not text:
            raise Institutional13FError(f"{field} is required")
        try:
            parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        except ValueError as exc:
            raise Institutional13FError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Institutional13FError(f"{field} must carry an explicit UTC offset")
    normalized = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if normalized.microsecond else "seconds"
    return normalized.isoformat(timespec=timespec).replace("+00:00", "Z")


def utc_datetime(value: str | datetime, *, field: str) -> datetime:
    """Return a normalized UTC datetime for ordering explicit evidence clocks."""
    normalized = normalize_utc(value, field=field)
    return datetime.fromisoformat(normalized[:-1] + "+00:00")


def normalize_accession(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9]{18}", text):
        text = f"{text[:10]}-{text[10:12]}-{text[12:]}"
    if not _ACCESSION_RE.fullmatch(text):
        raise Institutional13FError("accession must use ##########-##-###### form")
    return text


def normalize_cik(value: str | int) -> str:
    if isinstance(value, bool):
        raise Institutional13FError("CIK must be decimal digits")
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise Institutional13FError("CIK must contain at most ten decimal digits")
    normalized = text.zfill(10)
    if not _CIK_RE.fullmatch(normalized):  # pragma: no cover - guarded above
        raise Institutional13FError("CIK is invalid")
    return normalized


def normalize_form(value: str) -> str:
    form = str(value or "").strip().upper()
    if form not in _ALLOWED_FORMS:
        raise Institutional13FError(f"unsupported institutional 13F form: {value!r}")
    return form


def validate_sha256(value: str, *, field: str = "sha256") -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise Institutional13FError(f"{field} must be a lowercase SHA-256 digest")
    return value


def validate_version(value: str, *, field: str = "producer_version") -> str:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise Institutional13FError(f"{field} is invalid")
    return value


def validate_source_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise Institutional13FError("source_url is invalid")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not (host == "sec.gov" or host.endswith(".sec.gov"))
    ):
        raise Institutional13FError("source_url must be an HTTPS SEC URL")
    return value


def validate_owned_key(key: str) -> str:
    if not isinstance(key, str) or not key.startswith(EVIDENCE_PREFIX + "/"):
        raise Institutional13FError("object key is outside the institutional 13F prefix")
    if len(key) > 1024 or "\\" in key or "\x00" in key or "?" in key or "#" in key:
        raise Institutional13FError("object key is unsafe")
    path = PurePosixPath(key)
    if path.is_absolute() or any(
        part in {"", ".", ".."} or not _KEY_PART_RE.fullmatch(part)
        for part in path.parts
    ):
        raise Institutional13FError("object key is unsafe")
    return key


def content_object_key(digest: str, *, content_type: str) -> str:
    digest = validate_sha256(digest)
    extension = _CONTENT_TYPE_EXTENSIONS.get(content_type)
    if extension is None:
        raise Institutional13FError("unsupported institutional 13F content type")
    return f"{EVIDENCE_PREFIX}/objects/sha256/{digest[:2]}/{digest}.{extension}"


def raw_receipt_key(filer_cik: str | int, accession: str, receipt_id: str) -> str:
    cik = normalize_cik(filer_cik)
    normalized_accession = normalize_accession(accession)
    if not isinstance(receipt_id, str) or not re.fullmatch(r"i13fraw_[a-f0-9]{64}", receipt_id):
        raise Institutional13FError("raw receipt id is invalid")
    return validate_owned_key(
        f"{EVIDENCE_PREFIX}/filings/{cik}/{normalized_accession}/{receipt_id}.json"
    )


def catalog_manifest_key(report_period: str | date, generation_id: str) -> str:
    period = normalize_report_period(report_period)
    if not isinstance(generation_id, str) or not re.fullmatch(
        r"i13fgen_[a-f0-9]{64}", generation_id
    ):
        raise Institutional13FError("catalog generation id is invalid")
    return validate_owned_key(
        f"{EVIDENCE_PREFIX}/quarters/report_period={period}/generations/"
        f"{generation_id}/manifest.json"
    )


def catalog_pointer_key(report_period: str | date) -> str:
    period = normalize_report_period(report_period)
    return validate_owned_key(
        f"{EVIDENCE_PREFIX}/quarters/report_period={period}/current.json"
    )


@dataclass(frozen=True)
class EvidenceClocks:
    """The valid, public-transaction, and system-retention clocks."""

    report_period: str | date
    accepted_at: str | datetime
    retained_at: str | datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_period", normalize_report_period(self.report_period))
        object.__setattr__(
            self, "accepted_at", normalize_utc(self.accepted_at, field="accepted_at")
        )
        object.__setattr__(
            self, "retained_at", normalize_utc(self.retained_at, field="retained_at")
        )
        if utc_datetime(self.retained_at, field="retained_at") < utc_datetime(
            self.accepted_at, field="accepted_at"
        ):
            raise Institutional13FError("retained_at cannot predate accepted_at")

    def to_dict(self) -> dict[str, str]:
        return {
            "report_period": str(self.report_period),
            "accepted_at": str(self.accepted_at),
            "retained_at": str(self.retained_at),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceClocks":
        if not isinstance(value, Mapping) or set(value) != {
            "report_period", "accepted_at", "retained_at"
        }:
            raise Institutional13FError("raw receipt clocks are invalid")
        return cls(**dict(value))


@dataclass(frozen=True)
class CatalogClocks:
    """The quarter validity, source-cutoff, and publication clocks."""

    report_period: str | date
    source_cutoff_at: str | datetime
    published_at: str | datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_period", normalize_report_period(self.report_period))
        object.__setattr__(
            self, "source_cutoff_at", normalize_utc(self.source_cutoff_at, field="source_cutoff_at")
        )
        object.__setattr__(
            self, "published_at", normalize_utc(self.published_at, field="published_at")
        )
        if utc_datetime(self.published_at, field="published_at") < utc_datetime(
            self.source_cutoff_at, field="source_cutoff_at"
        ):
            raise Institutional13FError("published_at cannot predate source_cutoff_at")

    def to_dict(self) -> dict[str, str]:
        return {
            "report_period": str(self.report_period),
            "source_cutoff_at": str(self.source_cutoff_at),
            "published_at": str(self.published_at),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CatalogClocks":
        if not isinstance(value, Mapping) or set(value) != {
            "report_period", "source_cutoff_at", "published_at"
        }:
            raise Institutional13FError("catalog clocks are invalid")
        return cls(**dict(value))


@dataclass(frozen=True)
class StoredObject:
    role: str
    object_key: str
    sha256: str
    byte_length: int
    content_type: str
    row_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or not self.role or len(self.role) > 128:
            raise Institutional13FError("stored object role is invalid")
        validate_owned_key(self.object_key)
        validate_sha256(self.sha256)
        if self.object_key != content_object_key(self.sha256, content_type=self.content_type):
            raise Institutional13FError("stored object key does not bind its digest and type")
        if (
            isinstance(self.byte_length, bool)
            or not isinstance(self.byte_length, int)
            or self.byte_length < 0
        ):
            raise Institutional13FError("stored object byte_length is invalid")
        if self.row_count is not None and (
            isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count < 0
        ):
            raise Institutional13FError("stored object row_count is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "object_key": self.object_key,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "content_type": self.content_type,
            "row_count": self.row_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StoredObject":
        if not isinstance(value, Mapping) or set(value) != {
            "role", "object_key", "sha256", "byte_length", "content_type", "row_count"
        }:
            raise Institutional13FError("stored object descriptor is invalid")
        return cls(**dict(value))


@dataclass(frozen=True)
class RawEvidenceReceipt:
    receipt_id: str
    accession: str
    filer_cik: str | int
    form: str
    source_url: str
    producer_version: str
    clocks: EvidenceClocks | Mapping[str, Any]
    raw_object: StoredObject | Mapping[str, Any]
    schema: str = RAW_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != RAW_RECEIPT_SCHEMA:
            raise Institutional13FError("unsupported raw receipt schema")
        object.__setattr__(self, "accession", normalize_accession(self.accession))
        object.__setattr__(self, "filer_cik", normalize_cik(self.filer_cik))
        object.__setattr__(self, "form", normalize_form(self.form))
        object.__setattr__(self, "source_url", validate_source_url(self.source_url))
        object.__setattr__(self, "producer_version", validate_version(self.producer_version))
        if not isinstance(self.clocks, EvidenceClocks):
            object.__setattr__(self, "clocks", EvidenceClocks.from_dict(self.clocks))
        if not isinstance(self.raw_object, StoredObject):
            object.__setattr__(self, "raw_object", StoredObject.from_dict(self.raw_object))
        if self.raw_object.role != "raw_submission" or self.raw_object.row_count is not None:
            raise Institutional13FError("raw receipt object descriptor is invalid")
        expected = RAW_RECEIPT_ID_PREFIX + sha256(
            canonical_json_bytes(self._identity_body())
        ).hexdigest()
        if self.receipt_id != expected:
            raise Institutional13FError("raw receipt identity is invalid")

    @classmethod
    def build(
        cls,
        *,
        accession: str,
        filer_cik: str | int,
        form: str,
        source_url: str,
        producer_version: str,
        clocks: EvidenceClocks,
        raw_object: StoredObject,
    ) -> "RawEvidenceReceipt":
        body = {
            "schema": RAW_RECEIPT_SCHEMA,
            "receipt_id": "",
            "accession": normalize_accession(accession),
            "filer_cik": normalize_cik(filer_cik),
            "form": normalize_form(form),
            "source_url": validate_source_url(source_url),
            "producer_version": validate_version(producer_version),
            "clocks": clocks.to_dict(),
            "raw_object": raw_object.to_dict(),
        }
        receipt_id = RAW_RECEIPT_ID_PREFIX + sha256(canonical_json_bytes(body)).hexdigest()
        return cls(
            receipt_id=receipt_id,
            **{
                key: value
                for key, value in body.items()
                if key not in {"schema", "receipt_id"}
            },
        )

    def _identity_body(self) -> dict[str, Any]:
        value = self.to_dict()
        value["receipt_id"] = ""
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "accession": self.accession,
            "filer_cik": self.filer_cik,
            "form": self.form,
            "source_url": self.source_url,
            "producer_version": self.producer_version,
            "clocks": self.clocks.to_dict(),
            "raw_object": self.raw_object.to_dict(),
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> "RawEvidenceReceipt":
        value = decode_canonical_json(payload, label="institutional 13F raw receipt")
        if set(value) != {
            "schema", "receipt_id", "accession", "filer_cik", "form", "source_url",
            "producer_version", "clocks", "raw_object"
        }:
            raise Institutional13FError("raw receipt shape is invalid")
        return cls(**value)

    @property
    def object_key(self) -> str:
        return raw_receipt_key(self.filer_cik, self.accession, self.receipt_id)


@dataclass(frozen=True)
class CatalogCounts:
    filing_rows: int
    holding_rows: int
    manager_relationship_rows: int
    source_receipts: int

    def __post_init__(self) -> None:
        for field, value in self.to_dict().items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise Institutional13FError(f"catalog count {field} is invalid")

    def to_dict(self) -> dict[str, int]:
        return {
            "filing_rows": self.filing_rows,
            "holding_rows": self.holding_rows,
            "manager_relationship_rows": self.manager_relationship_rows,
            "source_receipts": self.source_receipts,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CatalogCounts":
        if not isinstance(value, Mapping) or set(value) != {
            "filing_rows", "holding_rows", "manager_relationship_rows", "source_receipts"
        }:
            raise Institutional13FError("catalog counts are invalid")
        return cls(**dict(value))


@dataclass(frozen=True)
class CatalogGenerationManifest:
    generation_id: str
    producer_version: str
    clocks: CatalogClocks | Mapping[str, Any]
    counts: CatalogCounts | Mapping[str, Any]
    artifacts: Sequence[StoredObject | Mapping[str, Any]]
    schema: str = CATALOG_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CATALOG_MANIFEST_SCHEMA:
            raise Institutional13FError("unsupported catalog manifest schema")
        object.__setattr__(self, "producer_version", validate_version(self.producer_version))
        if not isinstance(self.clocks, CatalogClocks):
            object.__setattr__(self, "clocks", CatalogClocks.from_dict(self.clocks))
        if not isinstance(self.counts, CatalogCounts):
            object.__setattr__(self, "counts", CatalogCounts.from_dict(self.counts))
        artifacts = tuple(
            item if isinstance(item, StoredObject) else StoredObject.from_dict(item)
            for item in self.artifacts
        )
        object.__setattr__(self, "artifacts", artifacts)
        if tuple(item.role for item in artifacts) != CATALOG_ARTIFACT_ROLES:
            raise Institutional13FError("catalog artifact roles or order are invalid")
        expected_rows = {
            "filings_parquet": self.counts.filing_rows,
            "manager_relationships_parquet": self.counts.manager_relationship_rows,
            "source_receipts_json": self.counts.source_receipts,
            "coverage_json": None,
        }
        holding_rows = 0
        for artifact in artifacts:
            if artifact.role in HOLDING_BUCKET_ROLES:
                if artifact.row_count is None:
                    raise Institutional13FError("holding bucket row_count is required")
                holding_rows += artifact.row_count
            elif artifact.row_count != expected_rows[artifact.role]:
                raise Institutional13FError("catalog artifact row_count does not match counts")
        if holding_rows != self.counts.holding_rows:
            raise Institutional13FError("holding bucket row counts do not match catalog count")
        expected = GENERATION_ID_PREFIX + sha256(
            canonical_json_bytes(self._identity_body())
        ).hexdigest()
        if self.generation_id != expected:
            raise Institutional13FError("catalog generation identity is invalid")

    @classmethod
    def build(
        cls,
        *,
        producer_version: str,
        clocks: CatalogClocks,
        counts: CatalogCounts,
        artifacts: Sequence[StoredObject],
    ) -> "CatalogGenerationManifest":
        body = {
            "schema": CATALOG_MANIFEST_SCHEMA,
            "generation_id": "",
            "producer_version": validate_version(producer_version),
            "clocks": clocks.to_dict(),
            "counts": counts.to_dict(),
            "artifacts": [item.to_dict() for item in artifacts],
        }
        generation_id = GENERATION_ID_PREFIX + sha256(canonical_json_bytes(body)).hexdigest()
        return cls(
            generation_id=generation_id,
            producer_version=body["producer_version"],
            clocks=clocks,
            counts=counts,
            artifacts=tuple(artifacts),
        )

    def _identity_body(self) -> dict[str, Any]:
        value = self.to_dict()
        value["generation_id"] = ""
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generation_id": self.generation_id,
            "producer_version": self.producer_version,
            "clocks": self.clocks.to_dict(),
            "counts": self.counts.to_dict(),
            "artifacts": [item.to_dict() for item in self.artifacts],
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> "CatalogGenerationManifest":
        value = decode_canonical_json(payload, label="institutional 13F catalog manifest")
        if set(value) != {
            "schema", "generation_id", "producer_version", "clocks", "counts", "artifacts"
        }:
            raise Institutional13FError("catalog manifest shape is invalid")
        return cls(**value)

    @property
    def manifest_key(self) -> str:
        return catalog_manifest_key(self.clocks.report_period, self.generation_id)


@dataclass(frozen=True)
class CatalogPointer:
    generation_id: str
    manifest_key: str
    manifest_sha256: str
    manifest_byte_length: int
    report_period: str | date
    published_at: str | datetime
    schema: str = CATALOG_POINTER_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CATALOG_POINTER_SCHEMA:
            raise Institutional13FError("unsupported catalog pointer schema")
        if not isinstance(self.generation_id, str) or not re.fullmatch(
            r"i13fgen_[a-f0-9]{64}", self.generation_id
        ):
            raise Institutional13FError("catalog pointer generation id is invalid")
        object.__setattr__(self, "report_period", normalize_report_period(self.report_period))
        object.__setattr__(
            self, "published_at", normalize_utc(self.published_at, field="published_at")
        )
        if self.manifest_key != catalog_manifest_key(self.report_period, self.generation_id):
            raise Institutional13FError("catalog pointer manifest key is invalid")
        validate_sha256(self.manifest_sha256, field="manifest_sha256")
        if (
            isinstance(self.manifest_byte_length, bool)
            or not isinstance(self.manifest_byte_length, int)
            or self.manifest_byte_length <= 0
        ):
            raise Institutional13FError("catalog pointer manifest_byte_length is invalid")

    @classmethod
    def from_manifest(cls, manifest: CatalogGenerationManifest) -> "CatalogPointer":
        payload = manifest.to_json_bytes()
        return cls(
            generation_id=manifest.generation_id,
            manifest_key=manifest.manifest_key,
            manifest_sha256=sha256(payload).hexdigest(),
            manifest_byte_length=len(payload),
            report_period=manifest.clocks.report_period,
            published_at=manifest.clocks.published_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generation_id": self.generation_id,
            "manifest_key": self.manifest_key,
            "manifest_sha256": self.manifest_sha256,
            "manifest_byte_length": self.manifest_byte_length,
            "report_period": self.report_period,
            "published_at": self.published_at,
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> "CatalogPointer":
        value = decode_canonical_json(payload, label="institutional 13F catalog pointer")
        if set(value) != {
            "schema", "generation_id", "manifest_key", "manifest_sha256",
            "manifest_byte_length", "report_period", "published_at"
        }:
            raise Institutional13FError("catalog pointer shape is invalid")
        return cls(**value)

    @property
    def object_key(self) -> str:
        return catalog_pointer_key(self.report_period)


def validate_identity(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _IDENTITY_RE.fullmatch(value):
        raise Institutional13FError(f"{field} is invalid")
    return value
