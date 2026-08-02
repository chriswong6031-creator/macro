"""Sealed, source-read filing attestations for Fundamental Forensics.

``ffatt_`` is deliberately a narrow authority boundary.  It does *not* say a
filing is complete, a taxonomy is valid, a calculation is correct, or that the
SEC has no other fact.  It says that a pinned private source snapshot contained
the exact receipt-sidecar and gzip archive objects used by one ``ffpkg_`` /
``ffxbrl_`` pair, that the parser replayed from those bytes, and, when supplied,
that a dimension-known-empty numeric iXBRL fact has one exact projection in a
specific captured Company Facts response.

The source store itself is injected into :class:`PinnedSourceAuthority`, while
the sealing boundary accepts only that exact authority class.  This keeps the
artifact independent of a mutable ``latest`` pointer without letting a custom
protocol lookalike claim internal-pinned-source authority.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, localcontext
import gzip
from hashlib import sha256
import hmac
import io
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .filing_package import FilingPackage, FilingPackageError, HARD_MAX_MEMBER_BYTES, build_filing_package
from .ixbrl_extraction import IxbrlExtraction, IxbrlExtractionError, verify_ixbrl_extraction_source
from .models import canonical_json, parse_utc, stable_id, utc_text
from .sec_document_spine import canonical_cik, manifest_from_json_bytes


FILING_ATTESTATION_SCHEMA = "fundamental_forensics.filing_attestation/v1"
FILING_ATTESTATION_ID_PREFIX = "ffatt_"
ATTESTATION_POLICY_VERSION = "1"
HARD_MAX_FILING_ATTESTATION_BYTES = 64 * 1024 * 1024
HARD_MAX_COMPANYFACTS_RESPONSE_BYTES = 64 * 1024 * 1024
HARD_MAX_MATCHES = 10_000
HARD_MAX_CANDIDATES = 100_000
HARD_MAX_JSON_DEPTH = 64
HARD_MAX_JSON_NODES = 1_200_000
MAX_TEXT_BYTES = 16 * 1024
HARD_MAX_ARCHIVE_RECEIPT_BYTES = 64 * 1024
MAX_DECIMAL_TEXT_BYTES = 4_096

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_ATTESTATION_ID_RE = re.compile(r"^ffatt_[a-f0-9]{64}$")
_SNAPSHOT_ID_RE = re.compile(r"^ffsecsrc_[a-f0-9]{64}$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,699}$")

# Closed, explicit namespace policy.  The finite table avoids all local-name
# or suffix matching.  A future policy change is a schema/policy migration,
# not a permissive fallback for unknown issuer extensions.
_US_GAAP_NAMESPACES = frozenset(
    f"http://fasb.org/us-gaap/{year}" for year in range(2009, 2027)
)
_DEI_NAMESPACES = frozenset(
    f"http://xbrl.sec.gov/dei/{year}" for year in range(2009, 2027)
)
TAXONOMY_NAMESPACE_POLICY = MappingProxyType(
    {**{uri: "us-gaap" for uri in _US_GAAP_NAMESPACES}, **{uri: "dei" for uri in _DEI_NAMESPACES}}
)
UNIT_POLICY = MappingProxyType(
    {
        (("{http://www.xbrl.org/2003/iso4217}USD",), ()): "USD",
        (("{http://www.xbrl.org/2003/instance}shares",), ()): "shares",
        (("{http://www.xbrl.org/2003/instance}pure",), ()): "pure",
        (("{http://www.xbrl.org/2003/iso4217}USD",), ("{http://www.xbrl.org/2003/instance}shares",)): "USD/shares",
    }
)
ATTESTATION_MATCH_POLICY_FINGERPRINT = sha256(
    canonical_json(
        {
            "version": ATTESTATION_POLICY_VERSION,
            "taxonomy_namespaces": sorted(TAXONOMY_NAMESPACE_POLICY.items()),
            "units": [
                {"numerator": list(numerator), "denominator": list(denominator), "companyfacts_unit": unit}
                for (numerator, denominator), unit in sorted(UNIT_POLICY.items())
            ],
        }
    ).encode("utf-8")
).hexdigest()


class FilingAttestationError(ValueError):
    """An attestation input cannot safely make the narrow ``ffatt_`` claim."""


def _utc_now() -> datetime:
    """Internal clock seam for deterministic tests; never a public build argument."""
    return datetime.now(timezone.utc)


def _text(value: Any, *, field: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FilingAttestationError(f"{field} must be non-empty normalized text")
    try:
        if len(value.encode("utf-8")) > maximum:
            raise FilingAttestationError(f"{field} exceeds bounded text length")
    except UnicodeError as exc:
        raise FilingAttestationError(f"{field} is not valid UTF-8 text") from exc
    return value


def _clock(value: Any, *, field: str) -> str:
    if not isinstance(value, (str, datetime)):
        raise FilingAttestationError(f"{field} must be a UTC timestamp")
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise FilingAttestationError(str(exc)) from exc
    if parsed is None:
        raise FilingAttestationError(f"{field} is required")
    return utc_text(parsed) or ""


def _sha(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FilingAttestationError(f"{field} must be lowercase SHA-256 hex")
    return value


def _strict_mapping(value: Any, *, field: str, required: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FilingAttestationError(f"{field} must be an object")
    try:
        iterator = iter(value.items())
    except Exception as exc:  # noqa: BLE001 - untrusted mapping boundary.
        raise FilingAttestationError(f"{field} cannot be iterated") from exc
    out: dict[str, Any] = {}
    for index in range(len(required) + 1):
        try:
            pair = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001
            raise FilingAttestationError(f"{field} iterator failed") from exc
        if index == len(required) or not isinstance(pair, tuple) or len(pair) != 2:
            raise FilingAttestationError(f"{field} shape is invalid")
        key, item = pair
        if not isinstance(key, str) or key not in required or key in out:
            raise FilingAttestationError(f"{field} shape is invalid")
        out[key] = item
    if len(out) != len(required):
        raise FilingAttestationError(f"{field} shape is invalid")
    return out


def _copy_json(value: Any, *, field: str, budget: list[int], depth: int = 0) -> Any:
    if depth > HARD_MAX_JSON_DEPTH:
        raise FilingAttestationError(f"{field} exceeds JSON depth limit")
    budget[0] -= 1
    if budget[0] < 0:
        raise FilingAttestationError(f"{field} exceeds JSON node limit")
    if value is None or isinstance(value, (bool, str, int)):
        if isinstance(value, str):
            _text(value, field=field, maximum=HARD_MAX_FILING_ATTESTATION_BYTES)
        if isinstance(value, int) and not (-(1 << 63) <= value <= (1 << 63) - 1):
            raise FilingAttestationError(f"{field} integer is outside signed 64-bit range")
        return value
    if isinstance(value, float):
        raise FilingAttestationError(f"{field} cannot contain a binary float")
    if isinstance(value, Mapping):
        try:
            iterator = iter(value.items())
        except Exception as exc:  # noqa: BLE001
            raise FilingAttestationError(f"{field} mapping cannot be read") from exc
        out: dict[str, Any] = {}
        for _ in range(HARD_MAX_JSON_NODES + 1):
            try:
                pair = next(iterator)
            except StopIteration:
                break
            except Exception as exc:  # noqa: BLE001
                raise FilingAttestationError(f"{field} mapping iterator failed") from exc
            if _ == HARD_MAX_JSON_NODES or not isinstance(pair, tuple) or len(pair) != 2:
                raise FilingAttestationError(f"{field} has too many or invalid object fields")
            key, item = pair
            if not isinstance(key, str) or key in out:
                raise FilingAttestationError(f"{field} contains invalid object keys")
            out[key] = _copy_json(item, field=field, budget=budget, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        if type(value) not in {list, tuple}:
            raise FilingAttestationError(f"{field} array subclass is not accepted")
        if len(value) > HARD_MAX_JSON_NODES:
            raise FilingAttestationError(f"{field} has too many array values")
        return [_copy_json(item, field=field, budget=budget, depth=depth + 1) for item in value]
    raise FilingAttestationError(f"{field} is not JSON-compatible")


@dataclass(frozen=True)
class SourceWitness:
    """One immutable source-snapshot entry, not a mutable object-store alias."""

    snapshot_id: str
    snapshot_at: str
    kind: str
    relative_path: str
    object_key: str
    sha256: str
    byte_length: int
    content_type: str

    def __post_init__(self) -> None:
        from .source_sync import (
            SourceSyncError,
            canonical_source_relative_path,
            source_content_type_for_path,
            source_object_key_for_sha256,
        )

        if not isinstance(self.snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(self.snapshot_id):
            raise FilingAttestationError("source witness snapshot_id is invalid")
        object.__setattr__(self, "snapshot_at", _clock(self.snapshot_at, field="source witness snapshot_at"))
        if self.kind not in {"raw", "archive"}:
            raise FilingAttestationError("source witness kind is invalid")
        digest = _sha(self.sha256, field="source witness sha256")
        try:
            relative_path = canonical_source_relative_path(self.relative_path)
            expected_key = source_object_key_for_sha256(digest)
            expected_content_type = source_content_type_for_path(relative_path)
        except SourceSyncError as exc:
            raise FilingAttestationError("source witness is not a possible source-snapshot entry") from exc
        if relative_path != self.relative_path:
            raise FilingAttestationError("source witness relative path is not canonical")
        if self.object_key != expected_key:
            raise FilingAttestationError("source witness object key does not bind its digest")
        if isinstance(self.byte_length, bool) or not isinstance(self.byte_length, int) or self.byte_length < 0 or self.byte_length > HARD_MAX_COMPANYFACTS_RESPONSE_BYTES:
            raise FilingAttestationError("source witness byte_length is invalid")
        if self.content_type != expected_content_type:
            raise FilingAttestationError("source witness content type does not bind its relative path")

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_at": self.snapshot_at,
            "kind": self.kind,
            "relative_path": self.relative_path,
            "object_key": self.object_key,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "content_type": self.content_type,
        }


@dataclass(frozen=True)
class SourceFileRead:
    """Verified outer source bytes and the pinned manifest witness that named them."""

    content: bytes
    witness: SourceWitness

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise FilingAttestationError("source read content must be bytes")
        if type(self.witness) is not SourceWitness:
            raise FilingAttestationError("source read requires an exact SourceWitness")
        if len(self.content) != self.witness.byte_length or sha256(self.content).hexdigest() != self.witness.sha256:
            raise FilingAttestationError("source read content does not match pinned source witness")


@dataclass(frozen=True)
class ArchiveDocumentRead:
    """A bounded, raw archive member plus both verified source sidecars."""

    content: bytes
    object_read: SourceFileRead
    receipt_read: SourceFileRead
    receipt_sidecar_verified: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise FilingAttestationError("archive document content must be bytes")
        if type(self.object_read) is not SourceFileRead or type(self.receipt_read) is not SourceFileRead:
            raise FilingAttestationError("archive document read requires exact source read records")
        if not isinstance(self.receipt_sidecar_verified, bool):
            raise FilingAttestationError("archive document receipt-sidecar state is invalid")


@runtime_checkable
class SourceAuthority(Protocol):
    """Internal read shape implemented by :class:`PinnedSourceAuthority`.

    ``read_archive_document`` must source-read *both* the canonical receipt
    sidecar and the gzip object, prove their relation to ``expected_receipt``,
    and bounded-inflate / hash-check the raw returned bytes.  The attestation
    does not accept an authority that merely returns a guessed object key. This
    protocol is not a public sealing extension point: ``build_filing_attestation``
    requires the exact concrete authority and reconstructs it before reads.
    """

    snapshot_id: str
    snapshot_at: str

    def read_file(self, *, kind: str, relative_path: str, maximum_bytes: int) -> SourceFileRead: ...

    def read_gzip_file(
        self,
        *,
        kind: str,
        relative_path: str,
        expected_sha256: str,
        expected_length: int,
        maximum_bytes: int,
    ) -> ArchiveDocumentRead: ...

    def read_archive_document(
        self,
        *,
        storage_key: str,
        expected_receipt: Mapping[str, Any],
        maximum_bytes: int,
    ) -> ArchiveDocumentRead: ...


class PinnedSourceAuthority:
    """Production adapter over explicit, strict ``ffsecsrc_`` snapshot reads."""

    def __init__(self, *, store: Any, snapshot_id: str) -> None:
        from .source_sync import load_pinned_source_snapshot_strict

        snapshot = load_pinned_source_snapshot_strict(store=store, snapshot_id=snapshot_id)
        self._store = store
        self._snapshot = snapshot
        self.snapshot_id = str(snapshot.snapshot_id)
        self.snapshot_at = _clock(snapshot.snapshot.snapshot_at, field="pinned source snapshot_at")

    def _read(self, *, kind: str, relative_path: str, maximum_bytes: int) -> SourceFileRead:
        from .source_sync import read_pinned_source_snapshot_file_strict

        if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or maximum_bytes < 0:
            raise FilingAttestationError("source read maximum_bytes is invalid")
        raw = read_pinned_source_snapshot_file_strict(
            store=self._store,
            snapshot=self._snapshot,
            kind=kind,
            relative_path=relative_path,
            max_bytes=maximum_bytes,
        )
        witness = raw.witness
        return SourceFileRead(
            content=raw.content,
            witness=SourceWitness(
                snapshot_id=str(witness.snapshot_id),
                snapshot_at=self.snapshot_at,
                kind=str(witness.kind),
                relative_path=str(witness.relative_path),
                object_key=str(witness.object_key),
                sha256=str(witness.sha256),
                byte_length=int(witness.byte_length),
                content_type=str(witness.content_type),
            ),
        )

    def read_file(self, *, kind: str, relative_path: str, maximum_bytes: int) -> SourceFileRead:
        return self._read(kind=kind, relative_path=relative_path, maximum_bytes=maximum_bytes)

    @staticmethod
    def _inflate(content: bytes, *, expected_sha256: str, expected_length: int, maximum_bytes: int) -> bytes:
        _sha(expected_sha256, field="expected archive raw sha256")
        if (
            isinstance(expected_length, bool)
            or not isinstance(expected_length, int)
            or expected_length < 0
            or expected_length > maximum_bytes
        ):
            raise FilingAttestationError("expected archive raw byte length is outside bounded range")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content), mode="rb") as handle:
                raw = handle.read(expected_length + 1)
        except (OSError, EOFError, OverflowError, ValueError) as exc:
            raise FilingAttestationError("source archive gzip object is corrupt") from exc
        if len(raw) != expected_length or sha256(raw).hexdigest() != expected_sha256:
            raise FilingAttestationError("source archive gzip object does not match expected raw receipt")
        return raw

    def read_gzip_file(
        self,
        *,
        kind: str,
        relative_path: str,
        expected_sha256: str,
        expected_length: int,
        maximum_bytes: int,
    ) -> ArchiveDocumentRead:
        obj = self._read(kind=kind, relative_path=relative_path, maximum_bytes=HARD_MAX_COMPANYFACTS_RESPONSE_BYTES)
        raw = self._inflate(obj.content, expected_sha256=expected_sha256, expected_length=expected_length, maximum_bytes=maximum_bytes)
        # CF gzip files deliberately have no SEC archive-receipt sidecar.
        return ArchiveDocumentRead(
            content=raw,
            object_read=obj,
            receipt_read=obj,
            receipt_sidecar_verified=False,
        )

    def read_archive_document(
        self,
        *,
        storage_key: str,
        expected_receipt: Mapping[str, Any],
        maximum_bytes: int,
    ) -> ArchiveDocumentRead:
        expected = _copy_json(expected_receipt, field="expected archive receipt", budget=[10_000])
        if not isinstance(expected, dict):
            raise FilingAttestationError("expected archive receipt must be an object")
        receipt_id = expected.get("receipt_id")
        if not isinstance(receipt_id, str):
            raise FilingAttestationError("expected archive receipt id is invalid")
        # These collector wrappers are intentionally imported at use time:
        # collectors depend on the engine package, so importing them while
        # this module is exposed from ``engine.fundamental_forensics.__init__``
        # would create a package-initialization cycle.
        from collectors.sec_document_spine import (
            archive_receipt_from_json_bytes,
            read_archive_object_bytes,
            receipt_storage_key,
        )
        sidecar_key = receipt_storage_key(receipt_id)
        receipt_read = self._read(kind="archive", relative_path=sidecar_key, maximum_bytes=HARD_MAX_ARCHIVE_RECEIPT_BYTES)
        try:
            decoded = archive_receipt_from_json_bytes(receipt_read.content)
        except Exception as exc:  # collector owns the canonical sidecar contract.
            raise FilingAttestationError("source archive receipt sidecar is invalid") from exc
        if decoded.to_dict() != expected:
            raise FilingAttestationError("source archive receipt sidecar differs from package receipt")
        if decoded.storage_key != storage_key or decoded.byte_length > maximum_bytes:
            raise FilingAttestationError("source archive receipt does not bind requested bounded object")
        obj = self._read(kind="archive", relative_path=storage_key, maximum_bytes=HARD_MAX_COMPANYFACTS_RESPONSE_BYTES)
        try:
            raw = read_archive_object_bytes(obj.content, decoded)
        except Exception as exc:  # collector owns exact bounded gzip replay.
            raise FilingAttestationError("source archive gzip object does not match sidecar receipt") from exc
        if len(raw) > maximum_bytes:
            raise FilingAttestationError("source archive object exceeds requested raw byte limit")
        return ArchiveDocumentRead(content=raw, object_read=obj, receipt_read=receipt_read)


@dataclass(frozen=True)
class CompanyFactsSourcePaths:
    """Optional immutable Company Facts capture to use for exact projections."""

    manifest_path: str
    capture_path: str
    response_path: str

    def __post_init__(self) -> None:
        for name in ("manifest_path", "capture_path", "response_path"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _PATH_RE.fullmatch(value) or "//" in value:
                raise FilingAttestationError(f"Company Facts {name} is invalid")


def _rehydrate_package(value: FilingPackage | Mapping[str, Any]) -> FilingPackage:
    if type(value) is FilingPackage:
        try:
            # Dispatch through the exact base implementation so a forged
            # nominal still gets revalidated, without trusting a subclass
            # override or passing MappingProxy/tuple internals directly to a
            # boundary that expects JSON-shaped lists.
            return FilingPackage.from_dict(FilingPackage.to_dict(value))
        except Exception as exc:  # noqa: BLE001
            raise FilingAttestationError("invalid FilingPackage nominal input") from exc
    if isinstance(value, FilingPackage):
        raise FilingAttestationError("FilingPackage subclasses are not accepted")
    try:
        return FilingPackage.from_dict(value)
    except (FilingPackageError, TypeError, ValueError) as exc:
        raise FilingAttestationError("invalid filing package") from exc


def _rehydrate_extraction(value: IxbrlExtraction | Mapping[str, Any]) -> IxbrlExtraction:
    if type(value) is IxbrlExtraction:
        try:
            return IxbrlExtraction.from_dict(IxbrlExtraction.to_dict(value))
        except Exception as exc:  # noqa: BLE001
            raise FilingAttestationError("invalid IxbrlExtraction nominal input") from exc
    if isinstance(value, IxbrlExtraction):
        raise FilingAttestationError("IxbrlExtraction subclasses are not accepted")
    try:
        return IxbrlExtraction.from_dict(value)
    except (IxbrlExtractionError, TypeError, ValueError) as exc:
        raise FilingAttestationError("invalid ixbrl extraction") from exc


def _source_evidence(read: SourceFileRead, *, raw: bytes | None = None, receipt_verified: bool = False) -> dict[str, Any]:
    out = {"outer": read.witness.to_dict(), "receipt_sidecar": None, "raw_sha256": sha256(read.content if raw is None else raw).hexdigest(), "raw_byte_length": len(read.content if raw is None else raw), "receipt_sidecar_verified": receipt_verified}
    return out


def _archive_evidence(read: ArchiveDocumentRead) -> dict[str, Any]:
    return {
        "outer": read.object_read.witness.to_dict(),
        "receipt_sidecar": read.receipt_read.witness.to_dict() if read.receipt_sidecar_verified else None,
        "raw_sha256": sha256(read.content).hexdigest(),
        "raw_byte_length": len(read.content),
        "receipt_sidecar_verified": read.receipt_sidecar_verified,
    }


def _package_filing_matches_manifest(package: FilingPackage, source_manifest: Mapping[str, Any]) -> None:
    p = package.to_dict()["filing"]
    if (
        source_manifest.get("schema") != p["manifest_schema"]
        or source_manifest.get("manifest_id") != p["manifest_id"]
        or source_manifest.get("filing_id") != p["filing_id"]
        or source_manifest.get("issuer", {}).get("cik") != p["cik"]
        or source_manifest.get("filing", {}).get("accession") != p["accession"]
    ):
        raise FilingAttestationError("pinned filing manifest does not bind filing package")


def _qname_to_taxonomy(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.startswith("{") or "}" not in value:
        return None
    namespace, local = value[1:].split("}", 1)
    if not local or TAXONOMY_NAMESPACE_POLICY.get(namespace) is None:
        return None
    return str(TAXONOMY_NAMESPACE_POLICY[namespace]), local


def _mapped_unit(unit: Mapping[str, Any]) -> str | None:
    numerator = unit.get("numerator_measures")
    denominator = unit.get("denominator_measures")
    if not isinstance(numerator, list) or not isinstance(denominator, list):
        return None
    if not all(isinstance(item, str) for item in numerator + denominator):
        return None
    # A static direct mapping only; no sorting/local-name coercion means a
    # subtly malformed divide cannot turn into a match.
    key = (tuple(numerator), tuple(denominator))
    return UNIT_POLICY.get(key)


def _canonical_decimal(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    try:
        with localcontext() as context:
            context.prec = MAX_DECIMAL_TEXT_BYTES + 10
            context.Emax = MAX_DECIMAL_TEXT_BYTES
            context.Emin = -MAX_DECIMAL_TEXT_BYTES
            if isinstance(value, Decimal):
                parsed = value
            elif isinstance(value, int):
                parsed = Decimal(value)
            elif isinstance(value, str) and value and len(value) <= MAX_DECIMAL_TEXT_BYTES:
                parsed = Decimal(value)
            else:
                return None
            if not parsed.is_finite():
                return None
            if parsed.adjusted() > MAX_DECIMAL_TEXT_BYTES or parsed.adjusted() < -MAX_DECIMAL_TEXT_BYTES:
                return None
            normalized = parsed.normalize()
            if normalized == 0:
                return "0"
            rendered = format(normalized, "f")
            if "." in rendered:
                rendered = rendered.rstrip("0").rstrip(".")
            if len(rendered) > MAX_DECIMAL_TEXT_BYTES:
                return None
            return rendered
    except (DecimalException, ValueError):
        return None


def _context_projection(context: Mapping[str, Any], *, cik: str) -> tuple[str | None, str | None] | None:
    entity = context.get("entity")
    period = context.get("period")
    if not isinstance(entity, Mapping) or not isinstance(period, Mapping):
        return None
    if entity.get("scheme") != "http://www.sec.gov/CIK":
        return None
    try:
        if canonical_cik(entity.get("identifier")) != cik:
            return None
    except Exception:  # noqa: BLE001 - parser record already validated, keep matcher fail-closed.
        return None
    if context.get("dimensions") != [] or context.get("segment_content_status") != "complete" or context.get("scenario_content_status") != "complete":
        return None
    def checked(value: Any) -> str | None:
        if not isinstance(value, str) or len(value) > 32:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return value if parsed.isoformat() == value else None
    kind = period.get("kind")
    if kind == "instant":
        end = checked(period.get("instant_date"))
        return (None, end) if end is not None else None
    if kind == "duration":
        start, end = checked(period.get("start_date")), checked(period.get("end_date"))
        if start is not None and end is not None and start < end:
            return start, end
    return None


def _source_cf_rows(payload: Mapping[str, Any], *, cik: str, accession: str) -> dict[tuple[str, str, str, str | None, str, str], list[dict[str, Any]]]:
    from collectors.fundamental_forensics_companyfacts import iter_companyfacts_occurrences
    index: dict[tuple[str, str, str, str | None, str, str], list[dict[str, Any]]] = {}
    count = 0
    for row in iter_companyfacts_occurrences(payload):
        count += 1
        if count > HARD_MAX_CANDIDATES:
            raise FilingAttestationError("Company Facts source response exceeds attestation candidate cap")
        sec_fact = row.get("sec_fact")
        if not isinstance(sec_fact, Mapping) or sec_fact.get("accn") != accession:
            continue
        value = _canonical_decimal(sec_fact.get("val")) if sec_fact.get("val") is not None else None
        end = sec_fact.get("end")
        start = sec_fact.get("start")
        try:
            end_date = date.fromisoformat(end) if isinstance(end, str) else None
            start_date = date.fromisoformat(start) if isinstance(start, str) else None
        except ValueError:
            continue
        if value is None or end_date is None or end_date.isoformat() != end or (start is not None and (start_date is None or start_date.isoformat() != start or start_date >= end_date)):
            continue
        taxonomy = row.get("taxonomy")
        concept = row.get("concept")
        unit = row.get("unit")
        if not all(isinstance(item, str) and item for item in (taxonomy, concept, unit)):
            continue
        key = (taxonomy, concept, unit, start, end, value)
        index.setdefault(key, []).append({
            "taxonomy": taxonomy,
            "concept": concept,
            "unit": unit,
            "entry_index": row.get("entry_index"),
        })
    return index


def _companyfacts_attestation(
    *, authority: PinnedSourceAuthority, paths: CompanyFactsSourcePaths, cik: str, accession: str, extraction: IxbrlExtraction
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int], list[dict[str, Any]]]:
    from collectors.fundamental_forensics_companyfacts import (
        companyfacts_capture_from_json_bytes,
        companyfacts_capture_storage_key,
        companyfacts_manifest_storage_key,
        parse_companyfacts_response_exact_numbers,
        validate_companyfacts_manifest,
        validate_companyfacts_response_bytes,
    )
    try:
        manifest_read = authority.read_file(kind="archive", relative_path=paths.manifest_path, maximum_bytes=HARD_MAX_FILING_ATTESTATION_BYTES)
        capture_read = authority.read_file(kind="raw", relative_path=paths.capture_path, maximum_bytes=HARD_MAX_FILING_ATTESTATION_BYTES)
    except Exception as exc:
        raise FilingAttestationError("Company Facts manifest/capture source read failed") from exc
    try:
        manifest = json.loads(manifest_read.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FilingAttestationError("Company Facts source manifest is not UTF-8 JSON") from exc
    if not isinstance(manifest, Mapping):
        raise FilingAttestationError("Company Facts source manifest must be an object")
    try:
        validate_companyfacts_manifest(manifest)
    except Exception as exc:  # collector owns source contract.
        raise FilingAttestationError("Company Facts source manifest is invalid") from exc
    if canonical_json(dict(manifest)).encode("utf-8") != manifest_read.content:
        raise FilingAttestationError("Company Facts source manifest is not canonical")
    if companyfacts_manifest_storage_key(manifest) != paths.manifest_path or manifest["issuer"]["cik"] != cik:
        raise FilingAttestationError("Company Facts source manifest does not bind requested CIK/path")
    try:
        capture = companyfacts_capture_from_json_bytes(capture_read.content)
    except Exception as exc:  # collector owns canonical capture restore.
        raise FilingAttestationError("Company Facts source capture is invalid") from exc
    if companyfacts_capture_storage_key(capture.cik, capture.capture_id) != paths.capture_path:
        raise FilingAttestationError("Company Facts source capture path does not bind identity")
    if capture.cik != cik or manifest["source"]["capture_id"] != capture.capture_id:
        raise FilingAttestationError("Company Facts manifest/capture chain is inconsistent")
    if manifest["source"]["response_sha256"] != capture.response["sha256"] or manifest["source"]["response_bytes"] != capture.response["bytes"]:
        raise FilingAttestationError("Company Facts manifest/capture response chain is inconsistent")
    if capture.response["object_path"] != paths.response_path:
        raise FilingAttestationError("Company Facts response path does not bind capture")
    try:
        response_read = authority.read_gzip_file(
            kind="raw", relative_path=paths.response_path, expected_sha256=capture.response["sha256"], expected_length=capture.response["bytes"], maximum_bytes=HARD_MAX_COMPANYFACTS_RESPONSE_BYTES
        )
    except Exception as exc:
        raise FilingAttestationError("Company Facts response source read failed") from exc
    try:
        payload, logical, occurrence_count, occurrence_sha = validate_companyfacts_response_bytes(response_read.content, expected_cik=cik)
    except Exception as exc:  # collector performs strict duplicate/nonfinite JSON rejection.
        raise FilingAttestationError("Company Facts response is invalid") from exc
    if (
        sha256(logical).hexdigest() != manifest["source"]["logical_sha256"]
        or len(logical) != manifest["source"]["logical_bytes"]
        or occurrence_count != manifest["source"]["fact_occurrence_count"]
        or occurrence_sha != manifest["source"]["fact_occurrence_sha256"]
        or sha256(logical).hexdigest() != capture.logical["sha256"]
        or len(logical) != capture.logical["bytes"]
        or occurrence_count != capture.logical["fact_occurrence_count"]
        or occurrence_sha != capture.logical["fact_occurrence_sha256"]
    ):
        raise FilingAttestationError("Company Facts logical source chain is inconsistent")
    # Keep the public collector parse for receipt logical-hash validation, but
    # source candidate values from an independent exact-number parse.
    try:
        exact_payload = parse_companyfacts_response_exact_numbers(response_read.content, expected_cik=cik)
    except Exception as exc:
        raise FilingAttestationError("Company Facts response exact-number projection is invalid") from exc
    rows = _source_cf_rows(exact_payload, cik=cik, accession=accession)
    record = extraction.to_dict()
    contexts = {item.get("ffxbrl_context_id"): item for item in record["contexts"] if isinstance(item, Mapping)}
    units = {item.get("ffxbrl_unit_id"): item for item in record["units"] if isinstance(item, Mapping)}
    eligible: dict[tuple[str, str, str, str | None, str, str], list[Mapping[str, Any]]] = {}
    matches: list[dict[str, Any]] = []
    reasons = {"not_eligible": 0, "unsupported_namespace": 0, "unsupported_unit": 0, "no_exact_companyfacts_row": 0, "ambiguous_companyfacts_row": 0, "ambiguous_ixbrl_fact": 0}
    for fact in record["facts"]:
        if not isinstance(fact, Mapping) or fact.get("kind") != "numeric" or fact.get("nil") is not False or fact.get("status") != "available":
            reasons["not_eligible"] += 1
            continue
        taxonomy_concept = _qname_to_taxonomy(fact.get("concept_qname"))
        if taxonomy_concept is None:
            reasons["unsupported_namespace"] += 1
            continue
        context = contexts.get(fact.get("ffxbrl_context_id"))
        unit = units.get(fact.get("ffxbrl_unit_id"))
        projection = _context_projection(context, cik=cik) if isinstance(context, Mapping) else None
        mapped_unit = _mapped_unit(unit) if isinstance(unit, Mapping) else None
        value = _canonical_decimal(fact.get("normalized_value"))
        if projection is None or value is None:
            reasons["not_eligible"] += 1
            continue
        if mapped_unit is None:
            reasons["unsupported_unit"] += 1
            continue
        taxonomy, concept = taxonomy_concept
        start, end = projection
        key = (taxonomy, concept, mapped_unit, start, end, value)
        eligible.setdefault(key, []).append(fact)
    # Only a one-to-one correspondence can make a positive projection claim.
    # Two iXBRL facts with the same projected tuple must not each inherit one
    # Company Facts row merely because the row happens to exist.
    for key, xbrl_facts in eligible.items():
        candidates = rows.get(key, [])
        if not candidates:
            reasons["no_exact_companyfacts_row"] += len(xbrl_facts)
            continue
        if len(candidates) != 1:
            reasons["ambiguous_companyfacts_row"] += len(xbrl_facts)
            continue
        if len(xbrl_facts) != 1:
            reasons["ambiguous_ixbrl_fact"] += len(xbrl_facts)
            continue
        if len(matches) >= HARD_MAX_MATCHES:
            raise FilingAttestationError("attestation exact-match cap exceeded")
        fact = xbrl_facts[0]
        row = candidates[0]
        taxonomy, concept, mapped_unit, start, end, value = key
        match_body = {
            "ffxbrl_fact_id": fact.get("ffxbrl_fact_id"),
            "ffxbrl_span_id": fact.get("ffxbrl_span_id"),
            "taxonomy": taxonomy,
            "concept": concept,
            "unit": mapped_unit,
            "entry_index": row["entry_index"],
            "projection": {"cik": cik, "accession": accession, "start": start, "end": end, "value": value},
        }
        if not isinstance(match_body["ffxbrl_fact_id"], str) or not isinstance(match_body["ffxbrl_span_id"], str) or isinstance(row["entry_index"], bool) or not isinstance(row["entry_index"], int) or row["entry_index"] < 0:
            raise FilingAttestationError("invalid immutable XBRL/Company Facts match identity")
        matches.append({"match_id": stable_id("ffatt_match", match_body), **match_body})
    evidence = {"manifest": _source_evidence(manifest_read), "capture": _source_evidence(capture_read), "response": _archive_evidence(response_read)}
    binding = {
        "manifest_id": manifest["manifest_id"], "capture_id": capture.capture_id,
        "response_sha256": capture.response["sha256"], "logical_sha256": capture.logical["sha256"],
        "captured_at": capture.clocks["captured_at"], "recorded_at": capture.clocks["recorded_at"],
        "match_policy_version": ATTESTATION_POLICY_VERSION, "match_policy_fingerprint": ATTESTATION_MATCH_POLICY_FINGERPRINT, "matches": matches, "reason_counts": reasons,
    }
    return binding, evidence, reasons, matches


def _attestation_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("attestation_id", None)
    return FILING_ATTESTATION_ID_PREFIX + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _validate_source_witness(value: Any, *, field: str, snapshot_id: str, snapshot_at: str) -> None:
    raw = _strict_mapping(
        value,
        field=field,
        required=frozenset({"snapshot_id", "snapshot_at", "kind", "relative_path", "object_key", "sha256", "byte_length", "content_type"}),
    )
    witness = SourceWitness(**raw)
    if witness.snapshot_id != snapshot_id or witness.snapshot_at != snapshot_at:
        raise FilingAttestationError(f"{field} is not bound to attestation source snapshot")


def _validate_source_evidence(value: Any, *, field: str, snapshot_id: str, snapshot_at: str, receipt_required: bool, raw_equals_outer: bool) -> None:
    raw = _strict_mapping(
        value,
        field=field,
        required=frozenset({"outer", "receipt_sidecar", "raw_sha256", "raw_byte_length", "receipt_sidecar_verified"}),
    )
    _validate_source_witness(raw["outer"], field=f"{field}.outer", snapshot_id=snapshot_id, snapshot_at=snapshot_at)
    _sha(raw["raw_sha256"], field=f"{field}.raw_sha256")
    if isinstance(raw["raw_byte_length"], bool) or not isinstance(raw["raw_byte_length"], int) or raw["raw_byte_length"] < 0:
        raise FilingAttestationError(f"{field}.raw_byte_length is invalid")
    if raw["raw_byte_length"] > HARD_MAX_COMPANYFACTS_RESPONSE_BYTES:
        raise FilingAttestationError(f"{field}.raw_byte_length exceeds hard cap")
    if raw["receipt_sidecar_verified"] is not receipt_required:
        raise FilingAttestationError(f"{field}.receipt_sidecar_verified is invalid")
    if receipt_required:
        _validate_source_witness(raw["receipt_sidecar"], field=f"{field}.receipt_sidecar", snapshot_id=snapshot_id, snapshot_at=snapshot_at)
    elif raw["receipt_sidecar"] is not None:
        raise FilingAttestationError(f"{field} must not claim an archive receipt sidecar")
    outer = _strict_mapping(raw["outer"], field=f"{field}.outer", required=frozenset({"snapshot_id", "snapshot_at", "kind", "relative_path", "object_key", "sha256", "byte_length", "content_type"}))
    if raw_equals_outer and (raw["raw_sha256"] != outer["sha256"] or raw["raw_byte_length"] != outer["byte_length"]):
        raise FilingAttestationError(f"{field} raw evidence does not equal source object")


def _normalise_record(value: Mapping[str, Any]) -> dict[str, Any]:
    required = frozenset({"schema", "attestation_id", "authority", "filing", "package", "extraction", "source_evidence", "company_facts", "coverage", "clocks", "nonclaims"})
    record = _strict_mapping(value, field="filing attestation", required=required)
    if record["schema"] != FILING_ATTESTATION_SCHEMA:
        raise FilingAttestationError("unsupported filing attestation schema")
    if not isinstance(record["attestation_id"], str) or not _ATTESTATION_ID_RE.fullmatch(record["attestation_id"]):
        raise FilingAttestationError("filing attestation identity is invalid")
    copied = _copy_json(record, field="filing attestation", budget=[HARD_MAX_JSON_NODES])
    assert isinstance(copied, dict)
    encoded = canonical_json(copied).encode("utf-8")
    if len(encoded) > HARD_MAX_FILING_ATTESTATION_BYTES:
        raise FilingAttestationError("filing attestation exceeds byte safety limit")
    if copied["attestation_id"] != _attestation_id(copied):
        raise FilingAttestationError("filing attestation identity mismatch")
    authority = _strict_mapping(copied["authority"], field="filing attestation authority", required=frozenset({"kind", "signed", "snapshot_id", "snapshot_at"}))
    if authority["kind"] != "internal_pinned_source_snapshot" or authority["signed"] is not False:
        raise FilingAttestationError("filing attestation authority claim is invalid")
    snapshot_id = authority["snapshot_id"]
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise FilingAttestationError("filing attestation authority snapshot id is invalid")
    snapshot_at = _clock(authority["snapshot_at"], field="filing attestation authority snapshot_at")
    if authority["snapshot_at"] != snapshot_at:
        raise FilingAttestationError("filing attestation authority snapshot clock is invalid")
    filing = _strict_mapping(copied["filing"], field="filing attestation filing", required=frozenset({"cik", "accession", "filing_id", "manifest_id"}))
    try:
        if canonical_cik(filing["cik"]) != filing["cik"]:
            raise FilingAttestationError("filing attestation filing CIK is invalid")
    except Exception as exc:
        if isinstance(exc, FilingAttestationError):
            raise
        raise FilingAttestationError("filing attestation filing CIK is invalid") from exc
    if not isinstance(filing["accession"], str) or not _ACCESSION_RE.fullmatch(filing["accession"]):
        raise FilingAttestationError("filing attestation accession is invalid")
    for name in ("filing_id", "manifest_id"):
        _text(filing[name], field=f"filing attestation {name}", maximum=256)
    package = _strict_mapping(copied["package"], field="filing attestation package", required=frozenset({"schema", "package_id", "assembled_at", "archive_index_sha256", "archive_index_byte_length"}))
    extraction = _strict_mapping(copied["extraction"], field="filing attestation extraction", required=frozenset({"schema", "extraction_id", "computed_at", "document_name", "member_sha256", "member_byte_length"}))
    if package["schema"] != "fundamental_forensics.filing_package/v1" or not isinstance(package["package_id"], str) or not re.fullmatch(r"ffpkg_[a-f0-9]{64}", package["package_id"]):
        raise FilingAttestationError("filing attestation package binding is invalid")
    if extraction["schema"] != "fundamental_forensics.ixbrl_extraction/v1" or not isinstance(extraction["extraction_id"], str) or not re.fullmatch(r"ffxbrl_[a-f0-9]{64}", extraction["extraction_id"]):
        raise FilingAttestationError("filing attestation extraction binding is invalid")
    for name, item in (("package.assembled_at", package["assembled_at"]), ("extraction.computed_at", extraction["computed_at"])):
        if _clock(item, field=name) != item:
            raise FilingAttestationError(f"filing attestation {name} is not canonical")
    _sha(package["archive_index_sha256"], field="filing attestation package archive_index_sha256")
    _sha(extraction["member_sha256"], field="filing attestation extraction member_sha256")
    for name, item in (("package.archive_index_byte_length", package["archive_index_byte_length"]), ("extraction.member_byte_length", extraction["member_byte_length"])):
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > HARD_MAX_MEMBER_BYTES:
            raise FilingAttestationError(f"filing attestation {name} is invalid")
    evidence = _strict_mapping(copied["source_evidence"], field="filing attestation source_evidence", required=frozenset({"filing_manifest", "archive_index", "selected_member", "company_facts"}))
    _validate_source_evidence(evidence["filing_manifest"], field="source_evidence.filing_manifest", snapshot_id=snapshot_id, snapshot_at=snapshot_at, receipt_required=False, raw_equals_outer=True)
    _validate_source_evidence(evidence["archive_index"], field="source_evidence.archive_index", snapshot_id=snapshot_id, snapshot_at=snapshot_at, receipt_required=True, raw_equals_outer=False)
    _validate_source_evidence(evidence["selected_member"], field="source_evidence.selected_member", snapshot_id=snapshot_id, snapshot_at=snapshot_at, receipt_required=True, raw_equals_outer=False)
    if evidence["archive_index"]["raw_sha256"] != package["archive_index_sha256"] or evidence["archive_index"]["raw_byte_length"] != package["archive_index_byte_length"]:
        raise FilingAttestationError("filing attestation index evidence does not bind package")
    if evidence["selected_member"]["raw_sha256"] != extraction["member_sha256"] or evidence["selected_member"]["raw_byte_length"] != extraction["member_byte_length"]:
        raise FilingAttestationError("filing attestation member evidence does not bind extraction")
    cf_raw = copied["company_facts"]
    if not isinstance(cf_raw, Mapping):
        raise FilingAttestationError("filing attestation company_facts must be an object")
    requested = cf_raw.get("requested")
    if requested is False:
        cf_required = frozenset({"requested", "match_policy_version", "match_policy_fingerprint", "matches", "reason_counts"})
    elif requested is True:
        cf_required = frozenset({"requested", "manifest_id", "capture_id", "response_sha256", "logical_sha256", "captured_at", "recorded_at", "match_policy_version", "match_policy_fingerprint", "matches", "reason_counts"})
    else:
        raise FilingAttestationError("filing attestation company_facts requested state is invalid")
    company_facts = _strict_mapping(cf_raw, field="filing attestation company_facts", required=cf_required)
    # The conditional source plane has a strict but intentionally small
    # contract: it projects exact captured rows, never a ledger/PIT identity.
    if company_facts["match_policy_version"] != ATTESTATION_POLICY_VERSION or company_facts["match_policy_fingerprint"] != ATTESTATION_MATCH_POLICY_FINGERPRINT or type(company_facts["matches"]) is not list or not isinstance(company_facts["reason_counts"], dict):
        raise FilingAttestationError("filing attestation Company Facts claim is invalid")
    if not company_facts["requested"] and (company_facts["matches"] or company_facts["reason_counts"] or evidence["company_facts"] != {}):
        raise FilingAttestationError("unrequested Company Facts attestation must remain empty")
    if company_facts["requested"]:
        cf_evidence = _strict_mapping(evidence["company_facts"], field="source_evidence.company_facts", required=frozenset({"manifest", "capture", "response"}))
        _validate_source_evidence(cf_evidence["manifest"], field="source_evidence.company_facts.manifest", snapshot_id=snapshot_id, snapshot_at=snapshot_at, receipt_required=False, raw_equals_outer=True)
        _validate_source_evidence(cf_evidence["capture"], field="source_evidence.company_facts.capture", snapshot_id=snapshot_id, snapshot_at=snapshot_at, receipt_required=False, raw_equals_outer=True)
        _validate_source_evidence(cf_evidence["response"], field="source_evidence.company_facts.response", snapshot_id=snapshot_id, snapshot_at=snapshot_at, receipt_required=False, raw_equals_outer=False)
        for name in ("manifest_id", "capture_id", "response_sha256", "logical_sha256"):
            _text(company_facts[name], field=f"filing attestation company_facts.{name}", maximum=256)
        _sha(company_facts["response_sha256"], field="filing attestation company_facts.response_sha256")
        _sha(company_facts["logical_sha256"], field="filing attestation company_facts.logical_sha256")
        for name in ("captured_at", "recorded_at"):
            if _clock(company_facts[name], field=f"filing attestation company_facts.{name}") != company_facts[name]:
                raise FilingAttestationError("filing attestation Company Facts clock is invalid")
        if parse_utc(company_facts["recorded_at"], field="Company Facts recorded_at") < parse_utc(company_facts["captured_at"], field="Company Facts captured_at"):
            raise FilingAttestationError("Company Facts recording clock predates capture")
        if cf_evidence["response"]["raw_sha256"] != company_facts["response_sha256"]:
            raise FilingAttestationError("Company Facts response evidence does not bind capture")
    expected_reason_keys = frozenset({"not_eligible", "unsupported_namespace", "unsupported_unit", "no_exact_companyfacts_row", "ambiguous_companyfacts_row", "ambiguous_ixbrl_fact"}) if company_facts["requested"] else frozenset()
    reasons = _strict_mapping(company_facts["reason_counts"], field="filing attestation Company Facts reason_counts", required=expected_reason_keys)
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in reasons.values()):
        raise FilingAttestationError("filing attestation Company Facts reason count is invalid")
    if len(company_facts["matches"]) > HARD_MAX_MATCHES:
        raise FilingAttestationError("filing attestation Company Facts match cap exceeded")
    seen_match_ids: set[str] = set()
    seen_fact_spans: set[tuple[str, str]] = set()
    seen_companyfacts_locators: set[tuple[str, str, str, int]] = set()
    for item in company_facts["matches"]:
        match = _strict_mapping(item, field="filing attestation Company Facts match", required=frozenset({"match_id", "ffxbrl_fact_id", "ffxbrl_span_id", "taxonomy", "concept", "unit", "entry_index", "projection"}))
        body = dict(match); actual_id = body.pop("match_id")
        if not isinstance(actual_id, str) or actual_id != stable_id("ffatt_match", body) or actual_id in seen_match_ids:
            raise FilingAttestationError("filing attestation Company Facts match identity is invalid")
        seen_match_ids.add(actual_id)
        if not all(isinstance(match[name], str) and match[name] for name in ("ffxbrl_fact_id", "ffxbrl_span_id", "taxonomy", "concept", "unit")) or isinstance(match["entry_index"], bool) or not isinstance(match["entry_index"], int) or match["entry_index"] < 0:
            raise FilingAttestationError("filing attestation Company Facts match fields are invalid")
        if not re.fullmatch(r"ffxbrl_fact_[a-f0-9]{64}", match["ffxbrl_fact_id"]) or not re.fullmatch(r"ffxbrl_span_[a-f0-9]{64}", match["ffxbrl_span_id"]):
            raise FilingAttestationError("filing attestation Company Facts match XBRL identity is invalid")
        if match["taxonomy"] not in {"us-gaap", "dei"} or match["unit"] not in set(UNIT_POLICY.values()):
            raise FilingAttestationError("filing attestation Company Facts match namespace/unit is unsupported")
        fact_span = (match["ffxbrl_fact_id"], match["ffxbrl_span_id"])
        row_locator = (match["taxonomy"], match["concept"], match["unit"], match["entry_index"])
        if fact_span in seen_fact_spans or row_locator in seen_companyfacts_locators:
            raise FilingAttestationError("filing attestation Company Facts match is not one-to-one")
        seen_fact_spans.add(fact_span)
        seen_companyfacts_locators.add(row_locator)
        projection = _strict_mapping(match["projection"], field="filing attestation Company Facts match projection", required=frozenset({"cik", "accession", "start", "end", "value"}))
        canonical_projection_value = _canonical_decimal(projection["value"])
        if projection["cik"] != filing["cik"] or projection["accession"] != filing["accession"] or canonical_projection_value is None or canonical_projection_value != projection["value"]:
            raise FilingAttestationError("filing attestation Company Facts match projection is invalid")
        try:
            start_date = date.fromisoformat(projection["start"]) if projection["start"] is not None and isinstance(projection["start"], str) else None
            end_date = date.fromisoformat(projection["end"]) if isinstance(projection["end"], str) else None
        except ValueError as exc:
            raise FilingAttestationError("filing attestation Company Facts match period is invalid") from exc
        if (projection["start"] is not None and (start_date is None or start_date.isoformat() != projection["start"])) or end_date is None or end_date.isoformat() != projection["end"] or (start_date is not None and start_date >= end_date):
            raise FilingAttestationError("filing attestation Company Facts match period is invalid")
    coverage = _strict_mapping(copied["coverage"], field="filing attestation coverage", required=frozenset({"selected_member_source_read", "archive_index_source_read", "selected_member_parser_replayed", "companyfacts_projection_matches", "filing_complete", "taxonomy_validation_complete", "relationship_validation_complete", "calculation_validation_complete", "companyfacts_completeness"}))
    clocks = _strict_mapping(copied["clocks"], field="filing attestation clocks", required=frozenset({"source_snapshot_at", "filing_manifest_recorded_at", "package_assembled_at", "extraction_computed_at", "attested_at"}))
    for name, item in clocks.items():
        if _clock(item, field=f"filing attestation clocks.{name}") != item:
            raise FilingAttestationError("filing attestation clocks are not canonical")
    if clocks["source_snapshot_at"] != snapshot_at or clocks["package_assembled_at"] != package["assembled_at"] or clocks["extraction_computed_at"] != extraction["computed_at"]:
        raise FilingAttestationError("filing attestation clocks do not bind evidence")
    if parse_utc(snapshot_at, field="source snapshot_at") < parse_utc(clocks["filing_manifest_recorded_at"], field="filing manifest recorded_at"):
        raise FilingAttestationError("filing attestation source snapshot predates filing manifest recording")
    # Fixed claim fences are checked on restore as well as build.
    nonclaims = _strict_mapping(copied["nonclaims"], field="filing attestation nonclaims", required=frozenset({"filing_complete", "taxonomy_validation_complete", "relationship_validation_complete", "calculation_validation_complete", "companyfacts_completeness", "submissions_source_presence", "ledger_acceptance_or_pit", "signature_verified", "trading_authority"}))
    for field in ("filing_complete", "taxonomy_validation_complete", "relationship_validation_complete", "calculation_validation_complete", "companyfacts_completeness", "submissions_source_presence", "ledger_acceptance_or_pit", "signature_verified", "trading_authority"):
        if nonclaims.get(field) is not False:
            raise FilingAttestationError("filing attestation nonclaims must remain false")
    for field in ("selected_member_source_read", "archive_index_source_read", "selected_member_parser_replayed"):
        if coverage.get(field) is not True:
            raise FilingAttestationError("filing attestation scoped coverage is invalid")
    for field in ("filing_complete", "taxonomy_validation_complete", "relationship_validation_complete", "calculation_validation_complete", "companyfacts_completeness"):
        if coverage.get(field) is not False:
            raise FilingAttestationError("filing attestation global coverage must remain false")
    if isinstance(coverage.get("companyfacts_projection_matches"), bool) or not isinstance(coverage.get("companyfacts_projection_matches"), int) or coverage["companyfacts_projection_matches"] != len(company_facts["matches"]):
        raise FilingAttestationError("filing attestation Company Facts match count is invalid")
    prerequisite_clocks = [snapshot_at, clocks["filing_manifest_recorded_at"], package["assembled_at"], extraction["computed_at"]]
    if company_facts["requested"]:
        prerequisite_clocks.extend([company_facts["captured_at"], company_facts["recorded_at"]])
        if any(parse_utc(snapshot_at, field="source snapshot_at") < parse_utc(item, field="Company Facts clock") for item in (company_facts["captured_at"], company_facts["recorded_at"])):
            raise FilingAttestationError("filing attestation source snapshot predates Company Facts evidence")
    if parse_utc(clocks["attested_at"], field="attested_at") < max(parse_utc(item, field="attestation clock") for item in prerequisite_clocks):
        raise FilingAttestationError("filing attestation clock predates bound source evidence")
    return copied


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class FilingAttestation:
    """Read-only canonical view of one tightly scoped ``ffatt_`` artifact."""

    _record: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_record", _freeze(_normalise_record(self._record)))

    @property
    def attestation_id(self) -> str:
        return str(self._record["attestation_id"])

    @property
    def content_id(self) -> str:
        return self.attestation_id

    @property
    def manifest(self) -> Mapping[str, Any]:
        return self._record

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._record)

    def to_json_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FilingAttestation":
        return cls(value)

    @classmethod
    def from_json_bytes(cls, content: bytes) -> "FilingAttestation":
        return filing_attestation_from_json_bytes(content)


def build_filing_attestation(
    package: FilingPackage | Mapping[str, Any],
    extraction: IxbrlExtraction | Mapping[str, Any],
    *,
    authority: PinnedSourceAuthority,
    companyfacts_paths: CompanyFactsSourcePaths | None = None,
) -> FilingAttestation:
    """Read a pinned snapshot and seal the exact limited source correspondence."""
    # The protocol exists for narrow test/adapter seams, but an artifact that
    # labels its authority as a pinned internal source snapshot must only be
    # sealed by the concrete adapter that reloads and checksum-verifies that
    # snapshot on every read.  A caller-supplied lookalike cannot self-assert
    # this authority class.
    if type(authority) is not PinnedSourceAuthority:
        raise FilingAttestationError("attestation requires an exact PinnedSourceAuthority")
    try:
        # Reconstruct the concrete authority rather than trusting an instance
        # whose snapshot handle may have been mutated through low-level object
        # APIs.  The constructor re-loads the named immutable manifest through
        # the strict bounded-store contract.
        authority = PinnedSourceAuthority(store=authority._store, snapshot_id=authority.snapshot_id)
    except Exception as exc:
        raise FilingAttestationError("attestation cannot reload exact pinned source authority") from exc
    pinned_id = _text(getattr(authority, "snapshot_id", None), field="authority.snapshot_id", maximum=128)
    if not _SNAPSHOT_ID_RE.fullmatch(pinned_id):
        raise FilingAttestationError("attestation source authority is not pinned to a source snapshot")
    snapshot_at = _clock(getattr(authority, "snapshot_at", None), field="authority.snapshot_at")
    package_value = _rehydrate_package(package)
    extraction_value = _rehydrate_extraction(extraction)
    p = package_value.to_dict()
    e = extraction_value.to_dict()
    if e["source"]["package_id"] != package_value.package_id:
        raise FilingAttestationError("ixbrl extraction is not bound to filing package")
    filing = p["filing"]
    cik, accession = filing["cik"], filing["accession"]
    # The package's selected index document and selected iXBRL member each
    # carry an embedded receipt that must be matched to its source sidecar.
    index_document = p["archive_index"]["document"]
    try:
        index_read = authority.read_archive_document(storage_key=index_document["storage_key"], expected_receipt=index_document["retrieval"], maximum_bytes=HARD_MAX_MEMBER_BYTES)
    except Exception as exc:
        raise FilingAttestationError("pinned archive index source read failed") from exc
    expected_index = base64.b64decode(p["archive_index"]["raw_content_base64"], validate=True)
    if index_read.content != expected_index:
        raise FilingAttestationError("pinned archive index bytes differ from filing package")
    member = e["source"]["member"]
    try:
        member_read = authority.read_archive_document(storage_key=member["storage_key"], expected_receipt=member["retrieval"], maximum_bytes=HARD_MAX_MEMBER_BYTES)
    except Exception as exc:
        raise FilingAttestationError("pinned selected member source read failed") from exc
    try:
        verify_ixbrl_extraction_source(extraction_value, package_value, member_read.content)
    except IxbrlExtractionError as exc:
        raise FilingAttestationError("pinned member does not replay ixbrl extraction") from exc
    # Package provenance is an immutable source manifest, but it does not
    # acquire a receipt sidecar because it is canonical JSON itself.
    manifest_key = f"manifests/{cik}/{accession}/{filing['manifest_id']}.json"
    try:
        manifest_read = authority.read_file(kind="archive", relative_path=manifest_key, maximum_bytes=HARD_MAX_FILING_ATTESTATION_BYTES)
    except Exception as exc:
        raise FilingAttestationError("pinned filing manifest source read failed") from exc
    try:
        source_manifest = manifest_from_json_bytes(manifest_read.content)
    except Exception as exc:  # spine owns canonical filing-manifest restore.
        raise FilingAttestationError("pinned filing manifest is invalid") from exc
    _package_filing_matches_manifest(package_value, source_manifest)
    from collectors.sec_document_spine import manifest_storage_key
    if manifest_storage_key(source_manifest) != manifest_key:
        raise FilingAttestationError("pinned filing manifest storage path does not bind source manifest")
    if parse_utc(snapshot_at, field="source snapshot_at") < parse_utc(source_manifest["clocks"]["recorded_at"], field="filing manifest recorded_at"):
        raise FilingAttestationError("pinned source snapshot predates filing manifest recording")
    # Rebuild the immutable package from its pinned filing manifest/index and
    # every declared inventory state.  Only the index and selected member make
    # an object-presence claim in this v1 artifact; the remaining inventory is
    # carried as already-validated package accounting so reconstruction binds
    # role/state to the verified manifest/index without silently widening the
    # read scope to an entire filing.
    member_states: dict[str, Any] = {}
    for inventory in p["inventory"]:
        name = inventory["document_name"]
        if inventory["state"] == "stored":
            member_states[name] = {
                "state": "stored", "content_sha256": inventory["content_sha256"], "byte_length": inventory["byte_length"],
                "storage_key": inventory["storage_key"], "retrieval": inventory["retrieval"], "policy_reason": inventory["policy_reason"],
            }
        elif inventory["state"] == "not_requested":
            member_states[name] = "not_requested"
        else:
            member_states[name] = {
                "state": inventory["state"], "content_sha256": inventory["content_sha256"], "byte_length": inventory["byte_length"],
                "storage_key": inventory["storage_key"], "retrieval": inventory["retrieval"], "policy_reason": inventory["policy_reason"],
            }
    try:
        rebuilt_package = build_filing_package(
            source_manifest, index_document, index_read.content, member_states,
            assembled_at=p["assembly"]["assembled_at"], policy_profile=p["assembly"]["policy_profile"], policy_version=p["assembly"]["policy_version"],
        )
    except FilingPackageError as exc:
        raise FilingAttestationError("pinned source cannot rebuild filing package") from exc
    if not hmac.compare_digest(rebuilt_package.to_json_bytes(), package_value.to_json_bytes()):
        raise FilingAttestationError("pinned source package reconstruction differs from filing package")
    cf_binding: dict[str, Any] = {"requested": False, "match_policy_version": ATTESTATION_POLICY_VERSION, "match_policy_fingerprint": ATTESTATION_MATCH_POLICY_FINGERPRINT, "matches": [], "reason_counts": {}}
    cf_evidence: dict[str, Any] = {}
    if companyfacts_paths is not None:
        if type(companyfacts_paths) is not CompanyFactsSourcePaths:
            raise FilingAttestationError("CompanyFactsSourcePaths subclasses are not accepted")
        cf_binding, cf_evidence, _, _ = _companyfacts_attestation(authority=authority, paths=companyfacts_paths, cik=cik, accession=accession, extraction=extraction_value)
        cf_binding["requested"] = True
    # This is intentionally sampled after all source reads and parser replay.
    attested_at = _clock(_utc_now(), field="attested_at")
    prerequisite_clocks = [snapshot_at, p["assembly"]["assembled_at"], e["extraction"]["computed_at"], source_manifest["clocks"]["recorded_at"]]
    if cf_binding["requested"]:
        prerequisite_clocks.extend([cf_binding["captured_at"], cf_binding["recorded_at"], cf_evidence["manifest"]["outer"]["snapshot_at"]])
        if any(parse_utc(snapshot_at, field="source snapshot_at") < parse_utc(item, field="Company Facts source clock") for item in (cf_binding["captured_at"], cf_binding["recorded_at"])):
            raise FilingAttestationError("pinned source snapshot predates Company Facts capture evidence")
    if parse_utc(attested_at, field="attested_at") < max(parse_utc(item, field="attestation prerequisite") for item in prerequisite_clocks):
        raise FilingAttestationError("internal attestation clock predates source evidence")
    record: dict[str, Any] = {
        "schema": FILING_ATTESTATION_SCHEMA,
        "attestation_id": "",
        "authority": {"kind": "internal_pinned_source_snapshot", "signed": False, "snapshot_id": pinned_id, "snapshot_at": snapshot_at},
        "filing": {"cik": cik, "accession": accession, "filing_id": filing["filing_id"], "manifest_id": filing["manifest_id"]},
        "package": {"schema": p["schema"], "package_id": package_value.package_id, "assembled_at": p["assembly"]["assembled_at"], "archive_index_sha256": index_document["content_sha256"], "archive_index_byte_length": index_document["byte_length"]},
        "extraction": {"schema": e["schema"], "extraction_id": extraction_value.extraction_id, "computed_at": e["extraction"]["computed_at"], "document_name": member["document_name"], "member_sha256": member["content_sha256"], "member_byte_length": member["byte_length"]},
        "source_evidence": {"filing_manifest": _source_evidence(manifest_read), "archive_index": _archive_evidence(index_read), "selected_member": _archive_evidence(member_read), "company_facts": cf_evidence},
        "company_facts": cf_binding,
        "coverage": {"selected_member_source_read": True, "archive_index_source_read": True, "selected_member_parser_replayed": True, "companyfacts_projection_matches": len(cf_binding["matches"]), "filing_complete": False, "taxonomy_validation_complete": False, "relationship_validation_complete": False, "calculation_validation_complete": False, "companyfacts_completeness": False},
        "clocks": {"source_snapshot_at": snapshot_at, "filing_manifest_recorded_at": source_manifest["clocks"]["recorded_at"], "package_assembled_at": p["assembly"]["assembled_at"], "extraction_computed_at": e["extraction"]["computed_at"], "attested_at": attested_at},
        "nonclaims": {"filing_complete": False, "taxonomy_validation_complete": False, "relationship_validation_complete": False, "calculation_validation_complete": False, "companyfacts_completeness": False, "submissions_source_presence": False, "ledger_acceptance_or_pit": False, "signature_verified": False, "trading_authority": False},
    }
    record["attestation_id"] = _attestation_id(record)
    return FilingAttestation.from_dict(record)


def _semantic_replay_bytes(record: Mapping[str, Any]) -> bytes:
    """Compare renewable source claims without treating a clock sample as a signature."""
    copied = _copy_json(record, field="filing attestation replay record", budget=[HARD_MAX_JSON_NODES])
    if not isinstance(copied, dict):  # pragma: no cover - sealed record callers.
        raise FilingAttestationError("filing attestation replay record is invalid")
    copied.pop("attestation_id", None)
    clocks = copied.get("clocks")
    if not isinstance(clocks, dict):
        raise FilingAttestationError("filing attestation replay clocks are invalid")
    clocks.pop("attested_at", None)
    return canonical_json(copied).encode("utf-8")


def verify_filing_attestation_source(
    attestation: FilingAttestation | Mapping[str, Any],
    package: FilingPackage | Mapping[str, Any],
    extraction: IxbrlExtraction | Mapping[str, Any],
    *,
    authority: PinnedSourceAuthority,
    companyfacts_paths: CompanyFactsSourcePaths | None = None,
) -> None:
    """Fresh-read the pinned source evidence and reproduce the scoped claim.

    Restoring an ``ffatt_`` only proves canonical self-consistency; this method
    is required before a caller relies on its positive source-presence or exact
    projection statements.  It never turns the internally content-addressed
    record into a signed artifact.
    """
    if type(attestation) is FilingAttestation:
        stored = FilingAttestation.from_dict(FilingAttestation.to_dict(attestation))
    elif isinstance(attestation, FilingAttestation):
        raise FilingAttestationError("FilingAttestation subclasses are not accepted")
    else:
        stored = FilingAttestation.from_dict(attestation)
    stored_record = stored.to_dict()
    if getattr(authority, "snapshot_id", None) != stored_record["authority"]["snapshot_id"]:
        raise FilingAttestationError("source verifier authority snapshot does not bind attestation")
    if stored_record["company_facts"]["requested"] != (companyfacts_paths is not None):
        raise FilingAttestationError("source verifier Company Facts scope does not bind attestation")
    checked_package = _rehydrate_package(package)
    checked_extraction = _rehydrate_extraction(extraction)
    if checked_package.package_id != stored_record["package"]["package_id"] or checked_extraction.extraction_id != stored_record["extraction"]["extraction_id"]:
        raise FilingAttestationError("source verifier package/extraction does not bind attestation")
    rebuilt = build_filing_attestation(
        checked_package, checked_extraction, authority=authority, companyfacts_paths=companyfacts_paths
    )
    if not hmac.compare_digest(_semantic_replay_bytes(rebuilt.to_dict()), _semantic_replay_bytes(stored_record)):
        raise FilingAttestationError("fresh source replay does not reproduce filing attestation semantics")


def filing_attestation_json_bytes(value: FilingAttestation | Mapping[str, Any]) -> bytes:
    if type(value) is FilingAttestation:
        return FilingAttestation.from_dict(value.manifest).to_json_bytes()
    if isinstance(value, FilingAttestation):
        raise FilingAttestationError("FilingAttestation subclasses are not accepted")
    return FilingAttestation.from_dict(value).to_json_bytes()


def filing_attestation_from_json_bytes(content: bytes) -> FilingAttestation:
    """Restore only canonical UTF-8 JSON; reject duplicate and nonfinite input."""
    if not isinstance(content, bytes) or len(content) > HARD_MAX_FILING_ATTESTATION_BYTES:
        raise FilingAttestationError("filing attestation JSON exceeds byte safety limit")

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, item in pairs:
            if key in out:
                raise FilingAttestationError(f"duplicate JSON key: {key}")
            out[key] = item
        return out

    def reject_constant(value: str) -> None:
        raise FilingAttestationError(f"non-finite JSON constant: {value}")

    try:
        decoded = json.loads(content.decode("utf-8"), object_pairs_hook=reject_pairs, parse_constant=reject_constant)
    except FilingAttestationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise FilingAttestationError("filing attestation JSON is not UTF-8 JSON") from exc
    if not isinstance(decoded, Mapping):
        raise FilingAttestationError("filing attestation JSON must be an object")
    value = FilingAttestation.from_dict(decoded)
    if not hmac.compare_digest(value.to_json_bytes(), content):
        raise FilingAttestationError("filing attestation JSON is not canonically encoded")
    return value


def validate_filing_attestation(value: Mapping[str, Any]) -> None:
    _normalise_record(value)


__all__ = [
    "ATTESTATION_MATCH_POLICY_FINGERPRINT", "ATTESTATION_POLICY_VERSION", "ArchiveDocumentRead", "CompanyFactsSourcePaths",
    "FILING_ATTESTATION_ID_PREFIX", "FILING_ATTESTATION_SCHEMA", "FilingAttestation",
    "FilingAttestationError", "HARD_MAX_FILING_ATTESTATION_BYTES", "PinnedSourceAuthority",
    "SourceAuthority", "SourceFileRead", "SourceWitness", "build_filing_attestation",
    "filing_attestation_from_json_bytes", "filing_attestation_json_bytes", "validate_filing_attestation", "verify_filing_attestation_source",
]
