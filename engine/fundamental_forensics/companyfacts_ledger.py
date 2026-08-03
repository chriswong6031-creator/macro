"""Strict SEC Company Facts -> immutable raw-ledger adapter.

SEC's Company Facts endpoint is a convenient occurrence inventory, not a
filing package.  In particular, it has no acceptance timestamp and no XBRL
context or unit identifiers.  This adapter retains that boundary instead of
pretending the endpoint knows more than it does:

* a verified Company Facts capture manifest supplies the capture/recording
  clocks and binds the decoded payload by its logical digest;
* SEC Submissions payloads supply only accession acceptance clocks, including
  caller-provided historical ``*-submissions-*.json`` files; and
* fields not present in Company Facts (notably dimensions and fact-level
  amendment lineage) remain absent unless the caller provides explicit,
  auditable evidence.

The result is intentionally a small bridge rather than another generic SEC
parser.  It preserves every unit-array entry, including duplicates, in a
``RawFactLedger`` and carries the remaining SEC metadata in immutable companion
records.  A missing Submissions join is visible and fails closed for
source-event replay through ``TemporalClocks.accepted_at is None``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import heapq
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from collectors.fundamental_forensics_companyfacts import (
    CompanyFactsAcquisitionError,
    iter_companyfacts_occurrences,
    validate_companyfacts_manifest,
)
from engine.fundamental_forensics.models import canonical_json as source_canonical_json
from engine.fundamental_forensics.raw_ledger import (
    AvailabilityStatus,
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    RawFactOccurrence,
    SourceIdentity,
    TemporalClocks,
    canonical_json as raw_ledger_canonical_json,
    decimal_text,
    parse_utc,
    stable_id,
    utc_text,
)


COMPANYFACTS_LEDGER_SCHEMA = "fundamental_forensics.companyfacts_ledger/v2"
COMPANYFACTS_LEDGER_RECEIPT_SCHEMA = "fundamental_forensics.companyfacts_ledger_receipt/v2"
COMPANYFACTS_LEDGER_ADAPTER_VERSION = "2.0.0"
SUBMISSIONS_CLOCK_SCOPE = "recent_and_all_supplied_older_files"

# The source collector admits a 64 MiB Company Facts response.  The bridge
# receives decoded objects, so it separately caps their deterministic logical
# encoding and all supplied Submissions payloads before constructing facts.
DEFAULT_MAX_OCCURRENCES = 250_000
HARD_MAX_OCCURRENCES = 1_000_000
DEFAULT_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
HARD_MAX_PAYLOAD_BYTES = 128 * 1024 * 1024
DEFAULT_MAX_TOTAL_INPUT_BYTES = 128 * 1024 * 1024
HARD_MAX_TOTAL_INPUT_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_SUBMISSION_ROWS = 100_000
HARD_MAX_SUBMISSION_ROWS = 500_000
DEFAULT_MAX_OLDER_SUBMISSIONS_FILES = 128
HARD_MAX_OLDER_SUBMISSIONS_FILES = 512
DEFAULT_MAX_REVISION_EVIDENCE = 10_000
HARD_MAX_REVISION_EVIDENCE = 100_000
DEFAULT_MAX_REVISION_EVIDENCE_BYTES = 4 * 1024 * 1024
HARD_MAX_REVISION_EVIDENCE_BYTES = 32 * 1024 * 1024

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_OLDER_SUBMISSIONS_NAME_RE = re.compile(
    r"^CIK([0-9]{10})-submissions-[0-9]+\.json$"
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_REVISION_EVENT_TYPES = frozenset(
    {
        FactEventType.AMENDMENT,
        FactEventType.COMPARATIVE_RECAST,
        FactEventType.RESTATEMENT,
        FactEventType.SOURCE_CORRECTION,
    }
)


class CompanyFactsLedgerError(ValueError):
    """The Company Facts source cannot safely be converted to the raw ledger."""


class CompanyFactsLedgerInputTooLarge(CompanyFactsLedgerError):
    """A decoded source object or occurrence inventory exceeded an explicit cap."""


@dataclass(frozen=True)
class CompanyFactsLedgerConversionConfig:
    """Explicit bounds for one pinned-source ledger conversion.

    This is deliberately the same small set of limits accepted by
    :func:`convert_companyfacts_to_raw_ledger`.  The pinned loader applies the
    per-payload and aggregate limits while it reads evidence, then passes the
    exact values through to the pure conversion boundary.
    """

    max_occurrences: int = DEFAULT_MAX_OCCURRENCES
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
    max_total_input_bytes: int = DEFAULT_MAX_TOTAL_INPUT_BYTES
    max_submission_rows: int = DEFAULT_MAX_SUBMISSION_ROWS
    max_older_submissions_files: int = DEFAULT_MAX_OLDER_SUBMISSIONS_FILES
    max_revision_evidence: int = DEFAULT_MAX_REVISION_EVIDENCE
    max_revision_evidence_bytes: int = DEFAULT_MAX_REVISION_EVIDENCE_BYTES

    def __post_init__(self) -> None:
        _positive_limit(
            self.max_occurrences,
            field="max_occurrences",
            ceiling=HARD_MAX_OCCURRENCES,
        )
        _positive_limit(
            self.max_payload_bytes,
            field="max_payload_bytes",
            ceiling=HARD_MAX_PAYLOAD_BYTES,
        )
        _positive_limit(
            self.max_total_input_bytes,
            field="max_total_input_bytes",
            ceiling=HARD_MAX_TOTAL_INPUT_BYTES,
        )
        _positive_limit(
            self.max_submission_rows,
            field="max_submission_rows",
            ceiling=HARD_MAX_SUBMISSION_ROWS,
        )
        _positive_limit(
            self.max_older_submissions_files,
            field="max_older_submissions_files",
            ceiling=HARD_MAX_OLDER_SUBMISSIONS_FILES,
        )
        _positive_limit(
            self.max_revision_evidence,
            field="max_revision_evidence",
            ceiling=HARD_MAX_REVISION_EVIDENCE,
        )
        _positive_limit(
            self.max_revision_evidence_bytes,
            field="max_revision_evidence_bytes",
            ceiling=HARD_MAX_REVISION_EVIDENCE_BYTES,
        )

    def conversion_kwargs(self) -> dict[str, int]:
        """Return only the public conversion-limit keyword arguments."""
        return {
            "max_occurrences": self.max_occurrences,
            "max_payload_bytes": self.max_payload_bytes,
            "max_total_input_bytes": self.max_total_input_bytes,
            "max_submission_rows": self.max_submission_rows,
            "max_older_submissions_files": self.max_older_submissions_files,
            "max_revision_evidence": self.max_revision_evidence,
            "max_revision_evidence_bytes": self.max_revision_evidence_bytes,
        }


@dataclass(frozen=True)
class PinnedSubmissionsSource:
    """One named immutable SEC Submissions receipt/object pair.

    ``receipt_path`` must name the content-addressed ``.receipt.json`` sidecar,
    never the mutable ``latest.json`` convenience pointer.  ``object_path`` is
    separately supplied so a caller cannot make the loader silently follow a
    newly repointed or guessed object location.
    """

    source_name: str
    receipt_path: str
    object_path: str
    is_older: bool

    def __post_init__(self) -> None:
        source_name = _required_text(self.source_name, field="Submissions source_name")
        if not isinstance(self.is_older, bool):
            raise TypeError("Submissions is_older must be a boolean")
        if self.is_older:
            if _OLDER_SUBMISSIONS_NAME_RE.fullmatch(source_name) is None:
                raise CompanyFactsLedgerError(
                    "older Submissions source_name must be a canonical SEC filename"
                )
        elif source_name != "recent":
            raise CompanyFactsLedgerError(
                "the non-older Submissions source must be named recent"
            )
        receipt_path = _pinned_source_path(
            self.receipt_path, field="Submissions receipt_path"
        )
        object_path = _pinned_source_path(
            self.object_path, field="Submissions object_path"
        )
        if receipt_path.endswith("/latest.json") or receipt_path == "latest.json":
            raise CompanyFactsLedgerError(
                "Submissions receipt_path cannot use a mutable latest pointer"
            )
        object.__setattr__(self, "source_name", source_name)
        object.__setattr__(self, "receipt_path", receipt_path)
        object.__setattr__(self, "object_path", object_path)


@dataclass(frozen=True)
class CompanyFactsConversionSourceBundle:
    """All exact pinned-source paths needed for one issuer conversion.

    No source path is inferred from a CIK.  In particular, a current
    Submissions receipt and every historical file declared by it must be named
    by the caller before the loader performs a source read.
    """

    cik: str
    companyfacts_manifest_path: str
    companyfacts_capture_path: str
    companyfacts_response_path: str
    recent_submissions: PinnedSubmissionsSource
    older_submissions: tuple[PinnedSubmissionsSource, ...] = ()

    def __post_init__(self) -> None:
        cik = _cik(self.cik, field="source bundle cik")
        for field in (
            "companyfacts_manifest_path",
            "companyfacts_capture_path",
            "companyfacts_response_path",
        ):
            object.__setattr__(
                self,
                field,
                _pinned_source_path(getattr(self, field), field=field),
            )
        if type(self.recent_submissions) is not PinnedSubmissionsSource:
            raise CompanyFactsLedgerError(
                "recent_submissions must be an exact PinnedSubmissionsSource"
            )
        if self.recent_submissions.is_older:
            raise CompanyFactsLedgerError("recent_submissions must not be historical")
        if not isinstance(self.older_submissions, tuple):
            raise TypeError("older_submissions must be a tuple")
        names: set[str] = set()
        paths: set[str] = {
            self.companyfacts_manifest_path,
            self.companyfacts_capture_path,
            self.companyfacts_response_path,
            self.recent_submissions.receipt_path,
            self.recent_submissions.object_path,
        }
        for source in self.older_submissions:
            if type(source) is not PinnedSubmissionsSource:
                raise CompanyFactsLedgerError(
                    "older_submissions entries must be exact PinnedSubmissionsSource values"
                )
            match = _OLDER_SUBMISSIONS_NAME_RE.fullmatch(source.source_name)
            if not source.is_older or match is None or match.group(1) != cik:
                raise CompanyFactsLedgerError(
                    "older Submissions source does not bind the bundle CIK"
                )
            if source.source_name in names:
                raise CompanyFactsLedgerError("older_submissions contains duplicate names")
            if source.receipt_path in paths or source.object_path in paths:
                raise CompanyFactsLedgerError("source bundle paths must be unique")
            names.add(source.source_name)
            paths.add(source.receipt_path)
            paths.add(source.object_path)
        if len(paths) != 5 + (2 * len(self.older_submissions)):
            raise CompanyFactsLedgerError("source bundle paths must be unique")
        object.__setattr__(self, "cik", cik)


@dataclass(frozen=True)
class RevisionEvidence:
    """An explicit, source-auditable document relationship.

    A filing form ending in ``/A`` is retained as SEC metadata, but it is not
    enough to infer a fact-level parent, recast, or restatement.  To type an
    immutable raw-ledger revision, callers must provide both accession IDs,
    the event kind, and a stable evidence reference (for example a source
    document-spine relationship or a reviewed issuer disclosure key).
    """

    child_accession: str
    parent_accession: str
    event_type: FactEventType | str
    evidence_id: str
    available_at: datetime | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_accession", _accession(self.child_accession, field="child_accession"))
        object.__setattr__(self, "parent_accession", _accession(self.parent_accession, field="parent_accession"))
        if self.child_accession == self.parent_accession:
            raise CompanyFactsLedgerError("revision evidence cannot point an accession at itself")
        try:
            event_type = FactEventType(self.event_type)
        except ValueError as exc:
            raise CompanyFactsLedgerError(f"unsupported revision event type: {self.event_type!r}") from exc
        if event_type not in _REVISION_EVENT_TYPES:
            raise CompanyFactsLedgerError("revision evidence must name a supported typed revision event")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "evidence_id", _required_text(self.evidence_id, field="evidence_id"))
        available_at, _ = _required_utc(self.available_at, field="revision_evidence.available_at")
        object.__setattr__(self, "available_at", available_at)

    def to_dict(self) -> dict[str, str]:
        return {
            "child_accession": self.child_accession,
            "parent_accession": self.parent_accession,
            "event_type": self.event_type.value,
            "evidence_id": self.evidence_id,
            "available_at": utc_text(self.available_at) or "",
        }


@dataclass(frozen=True)
class SubmissionSourceWitness:
    """Compact immutable witness for one retained Submissions payload."""

    source_name: str
    payload_sha256: str
    row_count: int
    is_older: bool

    def __post_init__(self) -> None:
        source_name = _required_text(
            self.source_name,
            field="submission source_name",
        )
        if not isinstance(self.payload_sha256, str) or not _SHA256_RE.fullmatch(
            self.payload_sha256
        ):
            raise CompanyFactsLedgerError(
                "submission source payload_sha256 must be a lowercase SHA-256 digest"
            )
        if (
            isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count < 0
        ):
            raise CompanyFactsLedgerError(
                "submission source row_count must be a non-negative integer"
            )
        if not isinstance(self.is_older, bool):
            raise TypeError("submission source is_older must be a boolean")
        if self.is_older:
            if _OLDER_SUBMISSIONS_NAME_RE.fullmatch(source_name) is None:
                raise CompanyFactsLedgerError(
                    "older submission source_name must be a canonical SEC filename"
                )
        elif source_name != "recent":
            raise CompanyFactsLedgerError(
                "the non-older submission source must be named recent"
            )
        object.__setattr__(self, "source_name", source_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "payload_sha256": self.payload_sha256,
            "row_count": self.row_count,
            "is_older": self.is_older,
        }


@dataclass(frozen=True)
class CompanyFactsLedgerOccurrence:
    """One retained Company Facts entry plus its raw-ledger event.

    ``fy``, ``fp``, ``frame``, ``form``, and ``filed`` are deliberately kept
    as source metadata here.  Company Facts does not provide dimensions, so
    the associated ``FactContext`` has empty explicit and typed dimensions.
    """

    occurrence: RawFactOccurrence
    taxonomy: str
    concept: str
    unit: str
    entry_index: int
    start: str | None
    end: str
    fy: int | None
    fp: str | None
    frame: str | None
    form: str | None
    filed: str | None
    accession: str
    pit_eligible: bool
    availability: AvailabilityStatus
    amendment_declared: bool
    revision_evidence_id: str | None = None
    revision_evidence_available_at: datetime | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.occurrence, RawFactOccurrence):
            raise TypeError("occurrence must be RawFactOccurrence")
        if self.accession != self.occurrence.source.accession:
            raise CompanyFactsLedgerError("companion accession does not match raw occurrence source")
        if self.occurrence.dimensions_known:
            raise CompanyFactsLedgerError("Company Facts occurrences must declare dimensions_known=false")
        if self.pit_eligible != (self.occurrence.accepted_at is not None):
            raise CompanyFactsLedgerError("pit_eligible must exactly reflect the acceptance clock")
        expected = AvailabilityStatus.AVAILABLE if self.pit_eligible else AvailabilityStatus.NOT_AVAILABLE
        if self.availability is not expected:
            raise CompanyFactsLedgerError("source replay availability does not match pit eligibility")
        if isinstance(self.entry_index, bool) or not isinstance(self.entry_index, int) or self.entry_index < 0:
            raise CompanyFactsLedgerError("entry_index must be a non-negative integer")
        evidence_available = None
        if self.revision_evidence_available_at not in (None, ""):
            evidence_available, _ = _required_utc(
                self.revision_evidence_available_at,
                field="revision_evidence_available_at",
            )
        if (self.revision_evidence_id is None) != (evidence_available is None):
            raise CompanyFactsLedgerError(
                "revision evidence id and availability clock must be supplied together"
            )
        if self.occurrence.event_type is FactEventType.FILED and evidence_available is not None:
            raise CompanyFactsLedgerError("filed occurrence cannot carry revision evidence")
        if evidence_available is not None and self.occurrence.recorded_at < evidence_available:
            raise CompanyFactsLedgerError("occurrence system clock predates revision evidence")
        object.__setattr__(self, "revision_evidence_available_at", evidence_available)

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence.occurrence_id,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "unit": self.unit,
            "entry_index": self.entry_index,
            "start": self.start,
            "end": self.end,
            "fy": self.fy,
            "fp": self.fp,
            "frame": self.frame,
            "form": self.form,
            "filed": self.filed,
            "accn": self.accession,
            "pit_eligible": self.pit_eligible,
            "availability": self.availability.value,
            "amendment_declared": self.amendment_declared,
            "revision_evidence_id": self.revision_evidence_id,
            "revision_evidence_available_at": utc_text(self.revision_evidence_available_at),
            "event_type": self.occurrence.event_type.value,
            "revision_of": self.occurrence.revision_of,
        }


@dataclass(frozen=True)
class CompanyFactsLedgerReceipt:
    """Content-addressed receipt binding one immutable conversion."""

    schema: str
    receipt_id: str
    adapter_version: str
    capture_id: str
    manifest_id: str
    cik: str
    clocks: tuple[tuple[str, str], ...]
    submissions_clock_scope: str
    input_sha256: str
    companyfacts_sha256: str
    submissions_sha256: str
    output_sha256: str
    submission_sources: tuple[SubmissionSourceWitness, ...]
    occurrence_count: int
    output_occurrence_count: int
    submission_row_count: int
    older_submissions_file_count: int
    mapped_accessions: tuple[str, ...]
    unmapped_accessions: tuple[str, ...]
    mapped_accession_count: int
    unmapped_accession_count: int
    pit_eligible_count: int
    typed_revision_count: int
    availability: str

    def __post_init__(self) -> None:
        if self.schema != COMPANYFACTS_LEDGER_RECEIPT_SCHEMA:
            raise CompanyFactsLedgerError("unsupported Company Facts ledger receipt schema")
        if self.adapter_version != COMPANYFACTS_LEDGER_ADAPTER_VERSION:
            raise CompanyFactsLedgerError("unsupported Company Facts ledger adapter version")
        if self.submissions_clock_scope != SUBMISSIONS_CLOCK_SCOPE:
            raise CompanyFactsLedgerError("unsupported Submissions recording-clock scope")
        normalized_cik = _cik(self.cik, field="receipt.cik")
        if normalized_cik != self.cik:
            raise CompanyFactsLedgerError("receipt CIK must be normalized")
        for field in ("input_sha256", "companyfacts_sha256", "submissions_sha256", "output_sha256"):
            value = getattr(self, field)
            if not _SHA256_RE.fullmatch(value):
                raise CompanyFactsLedgerError(f"{field} must be a lowercase SHA-256 digest")
        if not self.receipt_id.startswith("cffledger_") or not _SHA256_RE.fullmatch(self.receipt_id[10:]):
            raise CompanyFactsLedgerError("invalid Company Facts ledger receipt id")
        if not isinstance(self.clocks, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2
            for item in self.clocks
        ):
            raise TypeError(
                "receipt clocks must be an immutable tuple of immutable pairs"
            )
        expected_clocks = (
            "acquisition_started_at",
            "captured_at",
            "recorded_at",
            "source_snapshot_at",
            "submissions_recorded_at",
        )
        if tuple(name for name, _ in self.clocks) != expected_clocks:
            raise CompanyFactsLedgerError("receipt clocks must use canonical manifest clock order")
        for name, value in self.clocks:
            try:
                parsed = parse_utc(value, field_name=f"receipt.{name}")
            except ValueError as exc:
                raise CompanyFactsLedgerError(str(exc)) from exc
            if parsed is None or utc_text(parsed) != value:
                raise CompanyFactsLedgerError("receipt clocks must be UTC-normalized")
        if self.availability not in {"available", "partial"}:
            raise CompanyFactsLedgerError("receipt availability must be available or partial")
        counts = (
            self.occurrence_count,
            self.output_occurrence_count,
            self.submission_row_count,
            self.older_submissions_file_count,
            self.mapped_accession_count,
            self.unmapped_accession_count,
            self.pit_eligible_count,
            self.typed_revision_count,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise CompanyFactsLedgerError("receipt counts must be non-negative integers")
        if self.occurrence_count != self.output_occurrence_count:
            raise CompanyFactsLedgerError("receipt input/output occurrence counts differ")
        if not isinstance(self.submission_sources, tuple):
            raise TypeError("receipt submission_sources must be an immutable tuple")
        if not all(
            isinstance(item, SubmissionSourceWitness)
            for item in self.submission_sources
        ):
            raise TypeError(
                "receipt submission_sources entries must be SubmissionSourceWitness"
            )
        for item in self.submission_sources:
            item.__post_init__()
        expected_sources = tuple(
            sorted(
                self.submission_sources,
                key=lambda item: (item.is_older, item.source_name),
            )
        )
        if self.submission_sources != expected_sources:
            raise CompanyFactsLedgerError(
                "receipt submission source witnesses must use canonical order"
            )
        if len({item.source_name for item in self.submission_sources}) != len(
            self.submission_sources
        ):
            raise CompanyFactsLedgerError(
                "receipt submission source witness names must be unique"
            )
        recent = [item for item in self.submission_sources if not item.is_older]
        if len(recent) != 1 or recent[0].source_name != "recent":
            raise CompanyFactsLedgerError(
                "receipt requires exactly one recent Submissions source witness"
            )
        for item in self.submission_sources:
            if item.is_older:
                match = _OLDER_SUBMISSIONS_NAME_RE.fullmatch(item.source_name)
                if match is None or match.group(1) != self.cik:
                    raise CompanyFactsLedgerError(
                        "receipt older Submissions witness CIK does not match capture"
                    )
        if self.submission_row_count != sum(
            item.row_count for item in self.submission_sources
        ):
            raise CompanyFactsLedgerError(
                "receipt submission row count does not match source witnesses"
            )
        if self.older_submissions_file_count != sum(
            item.is_older for item in self.submission_sources
        ):
            raise CompanyFactsLedgerError(
                "receipt older Submissions file count does not match source witnesses"
            )
        if not isinstance(self.mapped_accessions, tuple) or not isinstance(
            self.unmapped_accessions, tuple
        ):
            raise TypeError("receipt accession partitions must be immutable tuples")
        mapped = tuple(
            _accession(value, field="receipt.mapped_accessions", expected_cik=self.cik)
            for value in self.mapped_accessions
        )
        unmapped = tuple(
            _accession(value, field="receipt.unmapped_accessions", expected_cik=self.cik)
            for value in self.unmapped_accessions
        )
        if mapped != tuple(sorted(set(mapped))) or unmapped != tuple(sorted(set(unmapped))):
            raise CompanyFactsLedgerError("receipt accession partitions must be unique canonical tuples")
        if set(mapped).intersection(unmapped):
            raise CompanyFactsLedgerError("receipt mapped/unmapped accession partitions overlap")
        if self.mapped_accession_count != len(mapped) or self.unmapped_accession_count != len(unmapped):
            raise CompanyFactsLedgerError("receipt accession partition counts do not match partitions")
        if (
            self.pit_eligible_count > self.occurrence_count
            or self.typed_revision_count > self.occurrence_count
            or self.mapped_accession_count > self.occurrence_count
            or self.unmapped_accession_count > self.occurrence_count
            or self.mapped_accession_count + self.unmapped_accession_count > self.occurrence_count
        ):
            raise CompanyFactsLedgerError("receipt count exceeds occurrence count")
        if self.submission_row_count < self.mapped_accession_count:
            raise CompanyFactsLedgerError("receipt maps more accessions than supplied Submissions rows")
        if self.availability == "available" and self.unmapped_accession_count:
            raise CompanyFactsLedgerError("available receipt cannot contain unmapped accessions")
        if self.availability == "partial" and not self.unmapped_accession_count:
            raise CompanyFactsLedgerError("partial receipt requires unmapped accessions")
        expected = _receipt_id(self.to_dict(include_id=False))
        if self.receipt_id != expected:
            raise CompanyFactsLedgerError("Company Facts ledger receipt identity mismatch")

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        output = {
            "schema": self.schema,
            "adapter_version": self.adapter_version,
            "capture_id": self.capture_id,
            "manifest_id": self.manifest_id,
            "cik": self.cik,
            "clocks": dict(self.clocks),
            "submissions_clock_scope": self.submissions_clock_scope,
            "input_sha256": self.input_sha256,
            "companyfacts_sha256": self.companyfacts_sha256,
            "submissions_sha256": self.submissions_sha256,
            "output_sha256": self.output_sha256,
            "submission_sources": [
                item.to_dict() for item in self.submission_sources
            ],
            "occurrence_count": self.occurrence_count,
            "output_occurrence_count": self.output_occurrence_count,
            "submission_row_count": self.submission_row_count,
            "older_submissions_file_count": self.older_submissions_file_count,
            "mapped_accessions": list(self.mapped_accessions),
            "unmapped_accessions": list(self.unmapped_accessions),
            "mapped_accession_count": self.mapped_accession_count,
            "unmapped_accession_count": self.unmapped_accession_count,
            "pit_eligible_count": self.pit_eligible_count,
            "typed_revision_count": self.typed_revision_count,
            "availability": self.availability,
        }
        if include_id:
            return {"receipt_id": self.receipt_id, **output}
        return output


@dataclass(frozen=True)
class CompanyFactsLedgerConversion:
    """The raw append-only ledger, source metadata, and immutable receipt."""

    ledger: RawFactLedger
    occurrences: tuple[CompanyFactsLedgerOccurrence, ...]
    submission_sources: tuple[SubmissionSourceWitness, ...]
    receipt: CompanyFactsLedgerReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.ledger, RawFactLedger):
            raise TypeError("ledger must be RawFactLedger")
        if not isinstance(self.receipt, CompanyFactsLedgerReceipt):
            raise TypeError("receipt must be CompanyFactsLedgerReceipt")
        if not isinstance(self.occurrences, tuple):
            raise TypeError("conversion occurrences must be an immutable tuple")
        # Re-run the frozen receipt's complete invariant set so a conversion
        # cannot bless a post-construction mutation made through low-level
        # object APIs.
        self.receipt.__post_init__()
        if not isinstance(self.submission_sources, tuple) or not all(
            isinstance(item, SubmissionSourceWitness)
            for item in self.submission_sources
        ):
            raise TypeError(
                "conversion submission_sources must be immutable source witnesses"
            )
        if self.submission_sources != self.receipt.submission_sources:
            raise CompanyFactsLedgerError(
                "conversion submission source witnesses do not match receipt"
            )
        if self.receipt.submission_row_count != sum(
            item.row_count for item in self.submission_sources
        ):
            raise CompanyFactsLedgerError(
                "receipt submission row count does not match conversion witnesses"
            )
        if self.receipt.older_submissions_file_count != sum(
            item.is_older for item in self.submission_sources
        ):
            raise CompanyFactsLedgerError(
                "receipt older Submissions file count does not match conversion witnesses"
            )
        if self.receipt.receipt_id != _receipt_id(
            self.receipt.to_dict(include_id=False)
        ):
            raise CompanyFactsLedgerError(
                "Company Facts ledger receipt identity mismatch"
            )
        if len(self.ledger.events) != len(self.occurrences):
            raise CompanyFactsLedgerError("ledger event count does not match companion occurrences")
        if tuple(item.occurrence for item in self.occurrences) != self.ledger.events:
            raise CompanyFactsLedgerError("companion occurrence order must equal immutable ledger order")
        occurrence_count = len(self.ledger.events)
        if (
            self.receipt.occurrence_count != occurrence_count
            or self.receipt.output_occurrence_count != occurrence_count
        ):
            raise CompanyFactsLedgerError("receipt occurrence counts do not match ledger")
        mapped = tuple(sorted({item.accession for item in self.occurrences if item.pit_eligible}))
        unmapped = tuple(sorted({item.accession for item in self.occurrences if not item.pit_eligible}))
        if set(mapped).intersection(unmapped):  # one accession cannot have two acceptance joins
            raise CompanyFactsLedgerError("conversion contains inconsistent accession availability")
        if self.receipt.mapped_accessions != mapped or self.receipt.unmapped_accessions != unmapped:
            raise CompanyFactsLedgerError("receipt accession partitions do not match conversion")
        if (
            self.receipt.mapped_accession_count != len(mapped)
            or self.receipt.unmapped_accession_count != len(unmapped)
        ):
            raise CompanyFactsLedgerError("receipt accession counts do not match conversion")
        pit_count = sum(item.pit_eligible for item in self.occurrences)
        typed_count = sum(item.revision_evidence_id is not None for item in self.occurrences)
        if self.receipt.pit_eligible_count != pit_count:
            raise CompanyFactsLedgerError("receipt PIT-eligible count does not match conversion")
        if self.receipt.typed_revision_count != typed_count:
            raise CompanyFactsLedgerError("receipt typed-revision count does not match conversion")
        expected_availability = "partial" if unmapped else "available"
        if self.receipt.availability != expected_availability:
            raise CompanyFactsLedgerError("receipt availability does not match accession partition")
        clocks = dict(self.receipt.clocks)
        companyfacts_recorded, _ = _required_utc(
            clocks.get("recorded_at"), field="receipt.recorded_at"
        )
        companyfacts_captured, _ = _required_utc(
            clocks.get("captured_at"), field="receipt.captured_at"
        )
        submissions_recorded, _ = _required_utc(
            clocks.get("submissions_recorded_at"),
            field="receipt.submissions_recorded_at",
        )
        event_by_id = {
            item.occurrence_id: item for item in self.ledger.events
        }
        for item in self.occurrences:
            if item.occurrence.source.entity_id != self.receipt.cik:
                raise CompanyFactsLedgerError("occurrence CIK does not match receipt")
            prerequisites = [
                companyfacts_recorded,
                companyfacts_captured,
                submissions_recorded,
            ]
            if item.revision_evidence_available_at is not None:
                prerequisites.append(item.revision_evidence_available_at)
            if item.occurrence.revision_of is not None:
                parent = event_by_id.get(item.occurrence.revision_of)
                if parent is None:  # RawFactLedger also enforces this invariant.
                    raise CompanyFactsLedgerError(
                        "revision occurrence parent is absent from conversion"
                    )
                prerequisites.append(parent.recorded_at)
            if item.occurrence.recorded_at != max(prerequisites):
                raise CompanyFactsLedgerError(
                    "occurrence system availability does not match retained input/evidence clocks"
                )
        if self.receipt.output_sha256 != _output_sha256(self.ledger, self.occurrences):
            raise CompanyFactsLedgerError("receipt output hash does not match conversion")


@dataclass(frozen=True)
class _SubmissionRow:
    accession: str
    accepted_at: datetime | None
    source_name: str


@dataclass(frozen=True)
class _DraftOccurrence:
    source_order: int
    draft_id: str
    source: SourceIdentity
    context: FactContext
    unit_object: FactUnit
    concept_qname: str
    value_text: str
    accepted_at: datetime | None
    taxonomy: str
    concept: str
    unit: str
    entry_index: int
    start: str | None
    end: str
    fy: int | None
    fp: str | None
    frame: str | None
    form: str | None
    filed: str | None
    accession: str
    amendment_declared: bool

    @property
    def logical_key(self) -> str:
        return stable_id(
            "rawfact_lineage",
            self.source.source,
            self.source.entity_id,
            self.concept_qname,
            self.context.semantic_key,
            self.unit_object.semantic_key,
        )


@dataclass(frozen=True)
class _TypedRevision:
    event_type: FactEventType
    parent_draft_id: str
    evidence_id: str
    evidence_available_at: datetime


def _required_text(value: Any, *, field: str) -> str:
    if isinstance(value, float):
        raise CompanyFactsLedgerError(f"{field} cannot be a binary float")
    text = str(value or "").strip()
    if not text:
        raise CompanyFactsLedgerError(f"{field} is required")
    return text


def _cik(value: Any, *, field: str) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise CompanyFactsLedgerError(f"{field} must be a CIK integer/text, not a binary float")
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9]{1,10}", text) is None:
        raise CompanyFactsLedgerError(f"invalid {field}: {value!r}")
    normalized = f"{int(text):010d}"
    if normalized == "0000000000":
        raise CompanyFactsLedgerError(f"invalid {field}: {value!r}")
    return normalized


def _accession(value: Any, *, field: str, expected_cik: str | None = None) -> str:
    text = _required_text(value, field=field)
    if not _ACCESSION_RE.fullmatch(text):
        raise CompanyFactsLedgerError(f"invalid {field}: {value!r}")
    if expected_cik is not None and text[:10] != expected_cik:
        raise CompanyFactsLedgerError(f"{field} CIK prefix does not match capture CIK")
    return text


def _required_utc(value: Any, *, field: str) -> tuple[datetime, str]:
    if value is None or value == "":
        raise CompanyFactsLedgerError(f"{field} is required")
    try:
        parsed = parse_utc(value, field_name=field)
    except ValueError as exc:
        raise CompanyFactsLedgerError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - explicit missing guard above
        raise CompanyFactsLedgerError(f"{field} is required")
    return parsed, utc_text(parsed) or ""


def _optional_text(value: Any, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    return _required_text(value, field=field)


def _date_text(value: Any, *, field: str, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise CompanyFactsLedgerError(f"{field} is required")
        return None
    if isinstance(value, datetime):
        raise CompanyFactsLedgerError(f"{field} must be an ISO date, not a datetime")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        raise CompanyFactsLedgerError(f"{field} cannot be a binary float")
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise CompanyFactsLedgerError(f"invalid {field}: {value!r}") from exc


def _optional_fy(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise CompanyFactsLedgerError("fy must be an integer/text, not a binary float")
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,4}", text):
        raise CompanyFactsLedgerError(f"invalid fy: {value!r}")
    return int(text)


def _decimal_value(value: Any) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise CompanyFactsLedgerError("SEC Company Facts val must be Decimal-compatible text/int, never float")
    if not isinstance(value, (Decimal, str, int)):
        raise CompanyFactsLedgerError("SEC Company Facts val must be Decimal-compatible text/int")
    try:
        text = decimal_text(value)
    except ValueError as exc:
        raise CompanyFactsLedgerError(str(exc)) from exc
    if text is None:
        raise CompanyFactsLedgerError("SEC Company Facts val is required")
    return text


def _positive_limit(value: int, *, field: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CompanyFactsLedgerError(f"{field} must be a positive integer")
    if value > ceiling:
        raise CompanyFactsLedgerError(f"{field} exceeds hard safety ceiling {ceiling}")
    return value


def _preflight_source_canonical_decimals(value: Any, *, label: str) -> None:
    """Reject unsafe Decimal expansion before the source canonicalizer runs.

    The collector's canonicalizer uses fixed-point Decimal formatting.  Its
    result-size check therefore comes too late for an adversarial exponent.
    Traverse decoded JSON containers first and delegate to the raw ledger's
    bounded decimal canonicalizer, which estimates expansion before format().
    """
    stack = [value]
    seen_containers: set[int] = set()
    while stack:
        item = stack.pop()
        if isinstance(item, Decimal):
            try:
                decimal_text(item)
            except ValueError as exc:
                raise CompanyFactsLedgerError(
                    f"{label} contains a Decimal with unsafe bounded expansion"
                ) from exc
            continue
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in seen_containers:
                continue
            seen_containers.add(identity)
            try:
                iterator = iter(item.values())
                while True:
                    try:
                        stack.append(next(iterator))
                    except StopIteration:
                        break
            except Exception as exc:
                raise CompanyFactsLedgerError(
                    f"{label} mapping failed during Decimal preflight"
                ) from exc
        elif isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in seen_containers:
                continue
            seen_containers.add(identity)
            try:
                stack.extend(item)
            except Exception as exc:  # pragma: no cover - hostile sequence subclass
                raise CompanyFactsLedgerError(
                    f"{label} sequence failed during Decimal preflight"
                ) from exc


def _canonical_bytes(
    payload: Mapping[str, Any],
    *,
    label: str,
    maximum: int,
    canonicalizer=raw_ledger_canonical_json,
) -> bytes:
    if not isinstance(payload, Mapping):
        raise CompanyFactsLedgerError(f"{label} must be an object")
    try:
        encoded = canonicalizer(payload).encode("utf-8")
    except Exception as exc:
        raise CompanyFactsLedgerError(f"{label} cannot be canonicalized") from exc
    if len(encoded) > maximum:
        raise CompanyFactsLedgerInputTooLarge(f"{label} exceeds bounded payload input limit")
    return encoded


def _sha256(content: bytes) -> str:
    return sha256(content).hexdigest()


def _receipt_id(record: Mapping[str, Any]) -> str:
    return "cffledger_" + _sha256(raw_ledger_canonical_json(record).encode("utf-8"))


def _unit(value: str) -> FactUnit:
    """Preserve the Company Facts unit label without fabricating XBRL measures."""
    unit_text = _required_text(value, field="Company Facts unit")
    # Company Facts represents compound units as e.g. ``USD/shares``.  That
    # separator is source-provided, so retaining it as numerator/denominator
    # does not invent a dimension.  More complex labels remain one opaque
    # source measure rather than being speculatively decomposed.
    parts = unit_text.split("/")
    if len(parts) == 2 and all(part.strip() for part in parts):
        measures = (parts[0].strip(),)
        denominator = (parts[1].strip(),)
    else:
        measures = (unit_text,)
        denominator = ()
    return FactUnit(
        unit_id=stable_id("sec_companyfacts_unit", measures, denominator),
        measures=measures,
        denominator_measures=denominator,
    )


def _context(*, cik: str, start: str | None, end: str) -> FactContext:
    if start is None:
        return FactContext(
            context_id=stable_id("sec_companyfacts_context", cik, "instant", end),
            entity_scheme="sec-cik",
            entity_identifier=cik,
            instant=end,
            explicit_dimensions=(),
            typed_dimensions=(),
        )
    return FactContext(
        context_id=stable_id("sec_companyfacts_context", cik, "duration", start, end),
        entity_scheme="sec-cik",
        entity_identifier=cik,
        start=start,
        end=end,
        explicit_dimensions=(),
        typed_dimensions=(),
    )


def _manifest_contract(
    capture_manifest: Mapping[str, Any],
    companyfacts: Mapping[str, Any],
    *,
    max_payload_bytes: int,
    max_occurrences: int,
) -> tuple[dict[str, Any], str, bytes, list[dict[str, Any]]]:
    """Validate manifest identity/clocks and bind it to this decoded payload."""
    if not isinstance(capture_manifest, Mapping):
        raise CompanyFactsLedgerError("capture_manifest must be an object")
    if not isinstance(companyfacts, Mapping):
        raise CompanyFactsLedgerError("companyfacts must be an object")
    _preflight_source_canonical_decimals(
        capture_manifest,
        label="capture manifest",
    )
    _preflight_source_canonical_decimals(
        companyfacts,
        label="Company Facts payload",
    )
    manifest = dict(capture_manifest)
    try:
        validate_companyfacts_manifest(manifest)
    except CompanyFactsAcquisitionError as exc:
        raise CompanyFactsLedgerError(f"invalid verified Company Facts manifest: {exc}") from exc

    cik = _cik(companyfacts.get("cik"), field="companyfacts.cik")
    if cik != manifest["issuer"]["cik"]:
        raise CompanyFactsLedgerError("Company Facts payload CIK does not match capture manifest")
    payload_bytes = _canonical_bytes(
        companyfacts,
        label="Company Facts payload",
        maximum=max_payload_bytes,
        canonicalizer=source_canonical_json,
    )
    source = manifest["source"]
    if _sha256(payload_bytes) != source["logical_sha256"] or len(payload_bytes) != source["logical_bytes"]:
        raise CompanyFactsLedgerError("Company Facts payload logical digest/length does not match manifest")

    occurrence_digest = sha256()
    occurrence_rows: list[dict[str, Any]] = []
    try:
        for occurrence in iter_companyfacts_occurrences(companyfacts):
            occurrence_rows.append(occurrence)
            if len(occurrence_rows) > max_occurrences:
                raise CompanyFactsLedgerInputTooLarge("Company Facts occurrence count exceeds bounded limit")
            occurrence_digest.update(source_canonical_json(occurrence).encode("utf-8"))
    except CompanyFactsLedgerInputTooLarge:
        raise
    except (CompanyFactsAcquisitionError, TypeError, ValueError) as exc:
        raise CompanyFactsLedgerError(f"malformed Company Facts occurrence payload: {exc}") from exc
    if (
        len(occurrence_rows) != source["fact_occurrence_count"]
        or occurrence_digest.hexdigest() != source["fact_occurrence_sha256"]
    ):
        raise CompanyFactsLedgerError("Company Facts occurrence inventory does not match manifest")
    return manifest, cik, payload_bytes, occurrence_rows


def _submission_columns(payload: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
    """Return a strict SEC column-array payload, including older file forms."""
    if not isinstance(payload, Mapping):
        raise CompanyFactsLedgerError(f"{label} must be an object")
    if "filings" in payload:
        filings = payload.get("filings")
        if not isinstance(filings, Mapping):
            raise CompanyFactsLedgerError(f"{label}.filings must be an object")
        columns = filings.get("recent")
        if not isinstance(columns, Mapping):
            raise CompanyFactsLedgerError(f"{label}.filings.recent must be an object")
    else:
        # Historical SEC ``*-submissions-*.json`` files are column objects.
        # Some retained wrappers also carry a scalar CIK; it is checked by the
        # caller and is not itself a filing column.
        columns = {key: value for key, value in payload.items() if key != "cik"}
    if not isinstance(columns, Mapping):  # pragma: no cover - structural belt-and-braces
        raise CompanyFactsLedgerError(f"{label} columns must be an object")
    accessions = columns.get("accessionNumber")
    if not isinstance(accessions, list):
        raise CompanyFactsLedgerError(f"{label}.accessionNumber must be an array")
    size = len(accessions)
    for field, values in columns.items():
        if not isinstance(values, list):
            raise CompanyFactsLedgerError(f"{label}.{field} must be an array")
        if len(values) != size:
            raise CompanyFactsLedgerError(f"{label} column arrays have inconsistent lengths")
    return columns


def _declared_older_files(submissions: Mapping[str, Any], *, cik: str) -> tuple[str, ...]:
    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        raise CompanyFactsLedgerError("submissions.filings must be an object")
    files = filings.get("files", [])
    if files is None:
        files = []
    if not isinstance(files, list):
        raise CompanyFactsLedgerError("submissions.filings.files must be an array")
    names: set[str] = set()
    for index, record in enumerate(files):
        if not isinstance(record, Mapping):
            raise CompanyFactsLedgerError("submissions.filings.files entries must be objects")
        name = _required_text(record.get("name"), field=f"submissions.filings.files[{index}].name")
        match = _OLDER_SUBMISSIONS_NAME_RE.fullmatch(name)
        if match is None:
            raise CompanyFactsLedgerError("older Submissions filename must contain a canonical SEC CIK")
        if match.group(1) != cik:
            raise CompanyFactsLedgerError("older Submissions filename CIK does not match capture CIK")
        if name in names:
            raise CompanyFactsLedgerError("submissions.filings.files contains duplicate names")
        names.add(name)
    return tuple(sorted(names))


def _normalised_older_payloads(
    value: Mapping[str, Mapping[str, Any]]
    | Iterable[tuple[str, Mapping[str, Any]]]
    | None,
    *,
    declared_names: tuple[str, ...],
    maximum: int,
    max_payload_bytes: int,
    aggregate_bytes: int,
    max_total_input_bytes: int,
) -> tuple[
    tuple[tuple[str, Mapping[str, Any]], ...],
    int,
    tuple[tuple[str, str], ...],
]:
    if value is None:
        return (), aggregate_bytes, ()
    try:
        source = value.items() if isinstance(value, Mapping) else value
        iterator = iter(source)
    except Exception as exc:
        raise CompanyFactsLedgerError(
            "older_submissions_files must be a name->payload mapping or pairs"
        ) from exc
    out: list[tuple[str, Mapping[str, Any]]] = []
    payload_hashes: dict[str, str] = {}
    seen: set[str] = set()
    declared = set(declared_names)
    while True:
        try:
            item = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            raise CompanyFactsLedgerError("older submissions iterable failed during bounded read") from exc
        if len(out) >= maximum:
            raise CompanyFactsLedgerInputTooLarge("older submissions file count exceeds bounded limit")
        if isinstance(item, (str, bytes)):
            raise CompanyFactsLedgerError("older submissions iterable entries must be (name, payload) pairs")
        try:
            raw_name, payload = item
        except Exception as exc:
            raise CompanyFactsLedgerError(
                "older submissions iterable entries must be (name, payload) pairs"
            ) from exc
        name = _required_text(raw_name, field="older submissions file name")
        if name in seen:
            raise CompanyFactsLedgerError("older submissions payload names must be unique")
        if name not in declared:
            raise CompanyFactsLedgerError("older submissions payload is not declared by submissions.filings.files")
        if not isinstance(payload, Mapping):
            raise CompanyFactsLedgerError("older submissions payload must be an object")
        encoded = _canonical_bytes(
            payload,
            label=f"older Submissions payload {name}",
            maximum=max_payload_bytes,
        )
        aggregate_bytes += len(encoded)
        if aggregate_bytes > max_total_input_bytes:
            raise CompanyFactsLedgerInputTooLarge(
                "combined Company Facts/Submissions inputs exceed bounded limit"
            )
        seen.add(name)
        out.append((name, payload))
        payload_hashes[name] = _sha256(encoded)
    return (
        tuple(sorted(out, key=lambda item: item[0])),
        aggregate_bytes,
        tuple(sorted(payload_hashes.items())),
    )


def _submission_rows(
    *,
    cik: str,
    submissions: Mapping[str, Any],
    older_payloads: tuple[tuple[str, Mapping[str, Any]], ...],
    recent_payload_sha256: str,
    older_payload_sha256: Mapping[str, str],
    submissions_recorded_at: datetime,
    max_submission_rows: int,
) -> tuple[
    dict[str, _SubmissionRow],
    int,
    tuple[SubmissionSourceWitness, ...],
]:
    if not isinstance(submissions, Mapping):
        raise CompanyFactsLedgerError("submissions must be an object")
    if _cik(submissions.get("cik"), field="submissions.cik") != cik:
        raise CompanyFactsLedgerError("submissions CIK does not match Company Facts capture")
    sources: list[tuple[str, Mapping[str, Any], bool, str]] = [
        ("recent", submissions, False, recent_payload_sha256)
    ]
    sources.extend(
        (name, payload, True, older_payload_sha256[name])
        for name, payload in older_payloads
    )
    index: dict[str, _SubmissionRow] = {}
    witnesses: list[SubmissionSourceWitness] = []
    total_rows = 0
    for source_name, payload, is_older, payload_sha256 in sources:
        label = f"older:{source_name}" if is_older else source_name
        supplied_cik = payload.get("cik") if isinstance(payload, Mapping) else None
        if supplied_cik not in (None, "") and _cik(supplied_cik, field=f"{label}.cik") != cik:
            raise CompanyFactsLedgerError("older submissions CIK does not match Company Facts capture")
        columns = _submission_columns(payload, label=label)
        accessions = columns["accessionNumber"]
        accepted = columns.get("acceptanceDateTime")
        if accepted is not None and not isinstance(accepted, list):  # guarded in _submission_columns
            raise CompanyFactsLedgerError(f"{label}.acceptanceDateTime must be an array")
        witnesses.append(
            SubmissionSourceWitness(
                source_name=source_name,
                payload_sha256=payload_sha256,
                row_count=len(accessions),
                is_older=is_older,
            )
        )
        total_rows += len(accessions)
        if total_rows > max_submission_rows:
            raise CompanyFactsLedgerInputTooLarge("Submissions row count exceeds bounded limit")
        for offset, raw_accession in enumerate(accessions):
            accession = _accession(
                raw_accession,
                field=f"{label}.accessionNumber[{offset}]",
                expected_cik=cik,
            )
            accepted_value = accepted[offset] if accepted is not None else None
            try:
                accepted_at = parse_utc(accepted_value, field_name=f"{label}.acceptanceDateTime[{offset}]")
            except ValueError as exc:
                raise CompanyFactsLedgerError(str(exc)) from exc
            if accepted_at is not None and accepted_at > submissions_recorded_at:
                raise CompanyFactsLedgerError(
                    "Submissions acceptanceDateTime cannot be after submissions_recorded_at"
                )
            row = _SubmissionRow(accession=accession, accepted_at=accepted_at, source_name=label)
            existing = index.get(accession)
            if existing is not None and existing.accepted_at != row.accepted_at:
                raise CompanyFactsLedgerError("accession acceptance clocks conflict across Submissions payloads")
            if existing is None:
                index[accession] = row
    return index, total_rows, tuple(witnesses)


def _revision_evidence(
    value: Mapping[str, Mapping[str, Any] | RevisionEvidence]
    | Iterable[RevisionEvidence | Mapping[str, Any]]
    | None,
    *,
    expected_cik: str,
    maximum: int,
    max_bytes: int,
) -> tuple[dict[str, RevisionEvidence], bytes]:
    if value is None:
        empty = raw_ledger_canonical_json([]).encode("utf-8")
        if len(empty) > max_bytes:
            raise CompanyFactsLedgerInputTooLarge(
                "revision evidence bytes exceed bounded limit"
            )
        return {}, empty
    try:
        keyed = isinstance(value, Mapping)
        source = value.items() if keyed else value
        iterator = iter(source)
    except Exception as exc:
        raise CompanyFactsLedgerError("revision_evidence must be a mapping or iterable") from exc
    out: dict[str, RevisionEvidence] = {}
    canonical_records: list[dict[str, str]] = []
    encoded_size = 2  # []
    while True:
        try:
            item = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            raise CompanyFactsLedgerError("revision evidence iterable failed during bounded read") from exc
        if len(out) >= maximum:
            raise CompanyFactsLedgerInputTooLarge("revision evidence count exceeds bounded limit")
        if keyed:
            try:
                mapping_key, raw = item
            except Exception as exc:
                raise CompanyFactsLedgerError("revision evidence mapping entry is malformed") from exc
            mapping_key = _accession(
                mapping_key,
                field="revision evidence mapping key",
                expected_cik=expected_cik,
            )
        else:
            mapping_key, raw = None, item
        if isinstance(raw, RevisionEvidence):
            evidence = raw
        elif isinstance(raw, Mapping):
            child = raw.get("child_accession", mapping_key)
            if mapping_key is not None and raw.get("child_accession") not in (None, mapping_key):
                raise CompanyFactsLedgerError("revision evidence mapping key disagrees with child_accession")
            evidence = RevisionEvidence(
                child_accession=child,
                parent_accession=raw.get("parent_accession", raw.get("revision_of_accession")),
                event_type=raw.get("event_type"),
                evidence_id=raw.get("evidence_id", raw.get("evidence")),
                available_at=raw.get("available_at"),
            )
        else:
            raise CompanyFactsLedgerError("revision evidence entries must be objects")
        if evidence.child_accession in out:
            raise CompanyFactsLedgerError("only one explicit revision evidence record is allowed per child accession")
        _accession(
            evidence.child_accession,
            field="revision evidence child_accession",
            expected_cik=expected_cik,
        )
        _accession(
            evidence.parent_accession,
            field="revision evidence parent_accession",
            expected_cik=expected_cik,
        )
        out[evidence.child_accession] = evidence
        record = evidence.to_dict()
        record_size = len(raw_ledger_canonical_json(record).encode("utf-8"))
        encoded_size += record_size + (1 if canonical_records else 0)
        if encoded_size > max_bytes:
            raise CompanyFactsLedgerInputTooLarge("revision evidence bytes exceed bounded limit")
        canonical_records.append(record)
    _validate_revision_evidence_graph(out)
    encoded = raw_ledger_canonical_json(
        [out[key].to_dict() for key in sorted(out)]
    ).encode("utf-8")
    if len(encoded) > max_bytes:  # exact canonical check after incremental admission
        raise CompanyFactsLedgerInputTooLarge("revision evidence bytes exceed bounded limit")
    return out, encoded


def _validate_revision_evidence_graph(evidence: Mapping[str, RevisionEvidence]) -> None:
    """Reject cycles in the child -> parent functional graph without recursion.

    A complete Submissions history can legitimately contain tens of thousands
    of explicit reviewed relationships.  The old recursive DFS would fail at
    Python's recursion limit long before the adapter's bounded evidence cap.
    Every node has at most one parent, so an iterative path walk is both
    simpler and linear in the number of evidence records.
    """
    state: dict[str, int] = {}
    for root in sorted(evidence):
        if state.get(root, 0) == 2:
            continue
        path: list[str] = []
        current = root
        while current in evidence:
            marker = state.get(current, 0)
            if marker == 1:
                raise CompanyFactsLedgerError(
                    "revision evidence accession graph contains a cycle"
                )
            if marker == 2:
                break
            state[current] = 1
            path.append(current)
            current = evidence[current].parent_accession
        for accession in path:
            state[accession] = 2


def _draft_occurrences(
    occurrence_rows: Sequence[dict[str, Any]],
    *,
    cik: str,
    manifest: Mapping[str, Any],
    submission_index: Mapping[str, _SubmissionRow],
    companyfacts_captured_at: datetime,
) -> tuple[_DraftOccurrence, ...]:
    capture_id = str(manifest["source"]["capture_id"])
    response_sha256 = str(manifest["source"]["response_sha256"])
    document_id = stable_id("sec_companyfacts_capture_document", capture_id)
    source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    drafts: list[_DraftOccurrence] = []
    for source_order, source_row in enumerate(occurrence_rows):
        taxonomy = _required_text(source_row.get("taxonomy"), field="taxonomy")
        concept = _required_text(source_row.get("concept"), field="concept")
        unit_text = _required_text(source_row.get("unit"), field="unit")
        entry_index = source_row.get("entry_index")
        if isinstance(entry_index, bool) or not isinstance(entry_index, int) or entry_index < 0:
            raise CompanyFactsLedgerError("Company Facts occurrence entry_index is invalid")
        sec_fact = source_row.get("sec_fact")
        if not isinstance(sec_fact, Mapping):
            raise CompanyFactsLedgerError("Company Facts occurrence sec_fact must be an object")
        accession = _accession(
            sec_fact.get("accn"), field="Company Facts accn", expected_cik=cik
        )
        start = _date_text(sec_fact.get("start"), field="Company Facts start")
        end = _date_text(sec_fact.get("end"), field="Company Facts end", required=True)
        context = _context(cik=cik, start=start, end=end or "")
        fact_unit = _unit(unit_text)
        accepted_at = submission_index.get(accession).accepted_at if accession in submission_index else None
        if accepted_at is not None and accepted_at > companyfacts_captured_at:
            raise CompanyFactsLedgerError(
                "Submissions acceptanceDateTime cannot be after manifest captured_at"
            )
        value_text = _decimal_value(sec_fact.get("val"))
        fy = _optional_fy(sec_fact.get("fy"))
        fp = _optional_text(sec_fact.get("fp"), field="Company Facts fp")
        frame = _optional_text(sec_fact.get("frame"), field="Company Facts frame")
        form = _optional_text(sec_fact.get("form"), field="Company Facts form")
        filed = _date_text(sec_fact.get("filed"), field="Company Facts filed")
        source = SourceIdentity(
            source="sec-companyfacts",
            entity_id=cik,
            accession=accession,
            document_id=document_id,
            body_sha256=response_sha256,
            source_url=source_url,
        )
        draft_id = stable_id(
            "sec_companyfacts_draft",
            capture_id,
            taxonomy,
            concept,
            unit_text,
            entry_index,
            dict(sec_fact),
        )
        drafts.append(
            _DraftOccurrence(
                source_order=source_order,
                draft_id=draft_id,
                source=source,
                context=context,
                unit_object=fact_unit,
                concept_qname=f"{taxonomy}:{concept}",
                value_text=value_text,
                accepted_at=accepted_at,
                taxonomy=taxonomy,
                concept=concept,
                unit=unit_text,
                entry_index=entry_index,
                start=start,
                end=end or "",
                fy=fy,
                fp=fp,
                frame=frame,
                form=form,
                filed=filed,
                accession=accession,
                amendment_declared=bool(form and form.upper().endswith("/A")),
            )
        )
    return tuple(drafts)


def _typed_parent_ids(
    drafts: Sequence[_DraftOccurrence],
    evidence_by_child: Mapping[str, RevisionEvidence],
) -> dict[str, _TypedRevision]:
    """Map evidence to same-economic-identity facts without inferring gaps."""
    # Index once.  Rebuilding parent/child maps for each evidence edge becomes
    # quadratic when a single annual filing has a large fact inventory and
    # multiple later filings reference it.  Tuples and mapping proxies make
    # the index stable after its one deterministic construction pass.
    mutable_by_accession: dict[
        str, dict[str, list[_DraftOccurrence]]
    ] = {}
    max_accepted_by_accession: dict[str, datetime | None] = {}
    for draft in drafts:
        by_key = mutable_by_accession.setdefault(draft.accession, {})
        by_key.setdefault(draft.logical_key, []).append(draft)
        existing = max_accepted_by_accession.get(draft.accession)
        if draft.accepted_at is not None and (
            existing is None or draft.accepted_at > existing
        ):
            max_accepted_by_accession[draft.accession] = draft.accepted_at
        else:
            max_accepted_by_accession.setdefault(draft.accession, existing)
    by_accession: Mapping[str, Mapping[str, tuple[_DraftOccurrence, ...]]] = (
        MappingProxyType(
            {
                accession: MappingProxyType(
                    {
                        logical_key: tuple(
                            sorted(values, key=lambda item: item.source_order)
                        )
                        for logical_key, values in by_key.items()
                    }
                )
                for accession, by_key in mutable_by_accession.items()
            }
        )
    )
    for child, evidence in evidence_by_child.items():
        if child not in by_accession:
            raise CompanyFactsLedgerError("revision evidence child accession is absent from Company Facts")
        if evidence.parent_accession not in by_accession:
            raise CompanyFactsLedgerError("revision evidence parent accession is absent from Company Facts")
    typed: dict[str, _TypedRevision] = {}
    for child_accession in sorted(evidence_by_child):
        evidence = evidence_by_child[child_accession]
        known_clocks = [
            accepted_at
            for accepted_at in (
                max_accepted_by_accession[child_accession],
                max_accepted_by_accession[evidence.parent_accession],
            )
            if accepted_at is not None
        ]
        if known_clocks and evidence.available_at < max(known_clocks):
            raise CompanyFactsLedgerError(
                "revision evidence available_at cannot precede a related acceptanceDateTime"
            )
        parent_by_key = by_accession[evidence.parent_accession]
        child_by_key = by_accession[child_accession]
        for logical_key, children in child_by_key.items():
            parents = parent_by_key.get(logical_key)
            # Evidence proves a document relation, not a synthetic parent for a
            # newly introduced concept.  Such a fact remains FILED rather than
            # being made into a false revision.
            if not parents:
                continue
            if len(parents) != 1 or len(children) != 1:
                raise CompanyFactsLedgerError(
                    "ambiguous fact pairing for explicit revision evidence"
                )
            parent, child = parents[0], children[0]
            if (
                parent.accepted_at is not None
                and child.accepted_at is not None
                and parent.accepted_at > child.accepted_at
            ):
                raise CompanyFactsLedgerError(
                    "revision parent acceptanceDateTime is after child acceptanceDateTime"
                )
            typed[child.draft_id] = _TypedRevision(
                event_type=evidence.event_type,
                parent_draft_id=parent.draft_id,
                evidence_id=evidence.evidence_id,
                evidence_available_at=evidence.available_at,
            )
    return typed


def _topological_drafts(
    drafts: Sequence[_DraftOccurrence],
    typed: Mapping[str, _TypedRevision],
) -> tuple[_DraftOccurrence, ...]:
    """Append revisions after their parents while retaining deterministic order."""
    by_id = {draft.draft_id: draft for draft in drafts}
    if len(by_id) != len(drafts):  # pragma: no cover - stable IDs include source entry identity
        raise CompanyFactsLedgerError("Company Facts source produced duplicate raw occurrence identities")
    children: dict[str, list[str]] = {key: [] for key in by_id}
    indegree: dict[str, int] = {key: 0 for key in by_id}
    for child_id, revision in typed.items():
        parent_id = revision.parent_draft_id
        if child_id not in by_id or parent_id not in by_id:
            raise CompanyFactsLedgerError("typed revision references an unknown occurrence")
        children[parent_id].append(child_id)
        indegree[child_id] += 1

    def key(occurrence_id: str) -> tuple[int, datetime, int, str]:
        draft = by_id[occurrence_id]
        # Known acceptance times order first; undated events stay deterministic
        # and remain source-replay ineligible regardless of their append spot.
        return (
            1 if draft.accepted_at is None else 0,
            draft.accepted_at or datetime.max.replace(tzinfo=timezone.utc),
            draft.source_order,
            occurrence_id,
        )

    ready = [
        (key(occurrence_id), occurrence_id)
        for occurrence_id, degree in indegree.items()
        if degree == 0
    ]
    heapq.heapify(ready)
    ordered: list[_DraftOccurrence] = []
    while ready:
        _, current = heapq.heappop(ready)
        ordered.append(by_id[current])
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (key(child), child))
    if len(ordered) != len(drafts):
        raise CompanyFactsLedgerError("revision evidence contains a cycle")
    return tuple(ordered)


def _output_sha256(ledger: RawFactLedger, occurrences: Sequence[CompanyFactsLedgerOccurrence]) -> str:
    payload = {
        "schema": COMPANYFACTS_LEDGER_SCHEMA,
        "raw_ledger_schema": ledger.schema,
        "events": [item.to_dict() for item in ledger.events],
        "occurrences": [item.to_dict() for item in occurrences],
    }
    return _sha256(raw_ledger_canonical_json(payload).encode("utf-8"))


def convert_companyfacts_to_raw_ledger(
    *,
    companyfacts: Mapping[str, Any],
    capture_manifest: Mapping[str, Any],
    submissions: Mapping[str, Any],
    submissions_recorded_at: datetime | str,
    older_submissions_files: Mapping[str, Mapping[str, Any]]
    | Iterable[tuple[str, Mapping[str, Any]]]
    | None = None,
    revision_evidence: Mapping[str, Mapping[str, Any] | RevisionEvidence]
    | Iterable[RevisionEvidence | Mapping[str, Any]]
    | None = None,
    max_occurrences: int = DEFAULT_MAX_OCCURRENCES,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    max_total_input_bytes: int = DEFAULT_MAX_TOTAL_INPUT_BYTES,
    max_submission_rows: int = DEFAULT_MAX_SUBMISSION_ROWS,
    max_older_submissions_files: int = DEFAULT_MAX_OLDER_SUBMISSIONS_FILES,
    max_revision_evidence: int = DEFAULT_MAX_REVISION_EVIDENCE,
    max_revision_evidence_bytes: int = DEFAULT_MAX_REVISION_EVIDENCE_BYTES,
) -> CompanyFactsLedgerConversion:
    """Convert one verified capture and bounded Submissions inventory.

    No network or filesystem access occurs here.  The caller must pass the
    immutable manifest returned by the verified Company Facts collector and
    the decoded payload that was verified against it.  Older Submissions files
    must be keyed by an entry explicitly declared in ``filings.files``.
    ``submissions_recorded_at`` is one mandatory bundle-retention clock that
    covers the recent payload and every supplied older file.
    """
    occurrence_limit = _positive_limit(
        max_occurrences, field="max_occurrences", ceiling=HARD_MAX_OCCURRENCES
    )
    payload_limit = _positive_limit(
        max_payload_bytes, field="max_payload_bytes", ceiling=HARD_MAX_PAYLOAD_BYTES
    )
    total_limit = _positive_limit(
        max_total_input_bytes,
        field="max_total_input_bytes",
        ceiling=HARD_MAX_TOTAL_INPUT_BYTES,
    )
    row_limit = _positive_limit(
        max_submission_rows,
        field="max_submission_rows",
        ceiling=HARD_MAX_SUBMISSION_ROWS,
    )
    older_file_limit = _positive_limit(
        max_older_submissions_files,
        field="max_older_submissions_files",
        ceiling=HARD_MAX_OLDER_SUBMISSIONS_FILES,
    )
    evidence_limit = _positive_limit(
        max_revision_evidence,
        field="max_revision_evidence",
        ceiling=HARD_MAX_REVISION_EVIDENCE,
    )
    evidence_byte_limit = _positive_limit(
        max_revision_evidence_bytes,
        field="max_revision_evidence_bytes",
        ceiling=HARD_MAX_REVISION_EVIDENCE_BYTES,
    )

    manifest, cik, companyfacts_bytes, occurrence_rows = _manifest_contract(
        capture_manifest,
        companyfacts,
        max_payload_bytes=payload_limit,
        max_occurrences=occurrence_limit,
    )
    if not isinstance(submissions, Mapping):
        raise CompanyFactsLedgerError("submissions must be an object")
    submissions_recorded_dt, submissions_recorded_text = _required_utc(
        submissions_recorded_at, field="submissions_recorded_at"
    )
    companyfacts_recorded_at, _ = _required_utc(
        manifest["clocks"]["recorded_at"], field="manifest.recorded_at"
    )
    companyfacts_captured_at, _ = _required_utc(
        manifest["clocks"]["captured_at"], field="manifest.captured_at"
    )
    submissions_bytes = _canonical_bytes(
        submissions, label="Submissions payload", maximum=payload_limit
    )
    manifest_bytes = _canonical_bytes(
        manifest, label="capture manifest", maximum=payload_limit
    )
    evidence, evidence_bytes = _revision_evidence(
        revision_evidence,
        expected_cik=cik,
        maximum=evidence_limit,
        max_bytes=evidence_byte_limit,
    )
    total_input = (
        len(companyfacts_bytes)
        + len(submissions_bytes)
        + len(manifest_bytes)
        + len(evidence_bytes)
    )
    if total_input > total_limit:
        raise CompanyFactsLedgerInputTooLarge(
            "combined Company Facts/Submissions inputs exceed bounded limit"
        )
    declared_older = _declared_older_files(submissions, cik=cik)
    older_payloads, total_input, older_payload_hashes = _normalised_older_payloads(
        older_submissions_files,
        declared_names=declared_older,
        maximum=older_file_limit,
        max_payload_bytes=payload_limit,
        aggregate_bytes=total_input,
        max_total_input_bytes=total_limit,
    )

    submission_index, submission_row_count, submission_sources = _submission_rows(
        cik=cik,
        submissions=submissions,
        older_payloads=older_payloads,
        recent_payload_sha256=_sha256(submissions_bytes),
        older_payload_sha256=dict(older_payload_hashes),
        submissions_recorded_at=submissions_recorded_dt,
        max_submission_rows=row_limit,
    )
    drafts = _draft_occurrences(
        occurrence_rows,
        cik=cik,
        manifest=manifest,
        submission_index=submission_index,
        companyfacts_captured_at=companyfacts_captured_at,
    )
    typed = _typed_parent_ids(drafts, evidence)
    ordered_drafts = _topological_drafts(drafts, typed)

    events: list[RawFactOccurrence] = []
    companion: list[CompanyFactsLedgerOccurrence] = []
    final_id_by_draft: dict[str, str] = {}
    system_available_by_draft: dict[str, datetime] = {}
    base_system_available_at = max(
        companyfacts_recorded_at,
        companyfacts_captured_at,
        submissions_recorded_dt,
    )
    for draft in ordered_drafts:
        revision = typed.get(draft.draft_id)
        event_type = revision.event_type if revision else FactEventType.FILED
        revision_of = (
            final_id_by_draft[revision.parent_draft_id] if revision else None
        )
        evidence_available_at = revision.evidence_available_at if revision else None
        system_available_at = max(
            value
            for value in (
                base_system_available_at,
                evidence_available_at,
                system_available_by_draft.get(revision.parent_draft_id)
                if revision
                else None,
            )
            if value is not None
        )
        source_occurrence_key = stable_id(
            "sec_companyfacts_source_occurrence",
            draft.draft_id,
            revision.evidence_id if revision else None,
            utc_text(evidence_available_at),
        )
        event = RawFactOccurrence(
            source=draft.source,
            concept_qname=draft.concept_qname,
            context=draft.context,
            unit=draft.unit_object,
            dimensions_known=False,
            source_occurrence_key=source_occurrence_key,
            clocks=TemporalClocks(
                accepted_at=draft.accepted_at,
                recorded_at=system_available_at,
            ),
            raw_token=draft.value_text,
            parsed_value=draft.value_text,
            event_type=event_type,
            revision_of=revision_of,
        )
        final_id_by_draft[draft.draft_id] = event.occurrence_id
        system_available_by_draft[draft.draft_id] = system_available_at
        events.append(event)
        pit_eligible = draft.accepted_at is not None
        companion.append(
            CompanyFactsLedgerOccurrence(
                occurrence=event,
                taxonomy=draft.taxonomy,
                concept=draft.concept,
                unit=draft.unit,
                entry_index=draft.entry_index,
                start=draft.start,
                end=draft.end,
                fy=draft.fy,
                fp=draft.fp,
                frame=draft.frame,
                form=draft.form,
                filed=draft.filed,
                accession=draft.accession,
                pit_eligible=pit_eligible,
                availability=(AvailabilityStatus.AVAILABLE if pit_eligible else AvailabilityStatus.NOT_AVAILABLE),
                amendment_declared=draft.amendment_declared,
                revision_evidence_id=revision.evidence_id if revision else None,
                revision_evidence_available_at=evidence_available_at,
            )
        )
    ledger = RawFactLedger(tuple(events))
    output_hash = _output_sha256(ledger, companion)

    accession_set = {draft.accession for draft in drafts}
    mapped_accessions = tuple(
        sorted(
            accession
            for accession in accession_set
            if accession in submission_index
            and submission_index[accession].accepted_at is not None
        )
    )
    unmapped_accessions = tuple(sorted(accession_set - set(mapped_accessions)))
    input_hash = _sha256(
        raw_ledger_canonical_json(
            {
                "capture_manifest": manifest,
                "companyfacts": companyfacts,
                "submissions": submissions,
                "submissions_recorded_at": submissions_recorded_text,
                "submissions_clock_scope": SUBMISSIONS_CLOCK_SCOPE,
                "older_submissions_files": {name: payload for name, payload in older_payloads},
                "revision_evidence": [evidence[key].to_dict() for key in sorted(evidence)],
            }
        ).encode("utf-8")
    )
    submission_hash = _sha256(
        raw_ledger_canonical_json(
            {
                "recent": submissions,
                "older": {name: payload for name, payload in older_payloads},
                "recorded_at": submissions_recorded_text,
                "clock_scope": SUBMISSIONS_CLOCK_SCOPE,
            }
        ).encode("utf-8")
    )
    clocks = tuple(
        (field, manifest["clocks"][field])
        for field in (
            "acquisition_started_at",
            "captured_at",
            "recorded_at",
            "source_snapshot_at",
        )
    ) + (("submissions_recorded_at", submissions_recorded_text),)
    receipt_fields: dict[str, Any] = {
        "schema": COMPANYFACTS_LEDGER_RECEIPT_SCHEMA,
        "adapter_version": COMPANYFACTS_LEDGER_ADAPTER_VERSION,
        "capture_id": manifest["source"]["capture_id"],
        "manifest_id": manifest["manifest_id"],
        "cik": cik,
        "clocks": dict(clocks),
        "submissions_clock_scope": SUBMISSIONS_CLOCK_SCOPE,
        "input_sha256": input_hash,
        "companyfacts_sha256": _sha256(companyfacts_bytes),
        "submissions_sha256": submission_hash,
        "output_sha256": output_hash,
        "submission_sources": [
            item.to_dict() for item in submission_sources
        ],
        "occurrence_count": len(drafts),
        "output_occurrence_count": len(events),
        "submission_row_count": submission_row_count,
        "older_submissions_file_count": len(older_payloads),
        "mapped_accessions": list(mapped_accessions),
        "unmapped_accessions": list(unmapped_accessions),
        "mapped_accession_count": len(mapped_accessions),
        "unmapped_accession_count": len(unmapped_accessions),
        "pit_eligible_count": sum(item.pit_eligible for item in companion),
        "typed_revision_count": len(typed),
        "availability": "partial" if unmapped_accessions else "available",
    }
    # The receipt stores clocks as an immutable ordered tuple, while its
    # canonical public representation is the object-shaped ``dict(clocks)``
    # used above for the content address.  Keep those two representations
    # deliberately aligned rather than passing a mutable mapping into a
    # frozen dataclass.
    receipt = CompanyFactsLedgerReceipt(
        receipt_id=_receipt_id(receipt_fields),
        **{
            **receipt_fields,
            "clocks": clocks,
            "submission_sources": submission_sources,
            "mapped_accessions": mapped_accessions,
            "unmapped_accessions": unmapped_accessions,
        },
    )
    return CompanyFactsLedgerConversion(
        ledger=ledger,
        occurrences=tuple(companion),
        submission_sources=submission_sources,
        receipt=receipt,
    )


def _pinned_source_path(value: Any, *, field: str) -> str:
    """Use the source-sync path policy without accepting an authority shortcut."""
    try:
        from .source_sync import canonical_source_relative_path

        return canonical_source_relative_path(value)
    except Exception as exc:  # source-sync owns the exact path grammar.
        raise CompanyFactsLedgerError(f"{field} is not a canonical source path") from exc


def _strict_source_json_object(
    content: Any, *, label: str, maximum_bytes: int
) -> dict[str, Any]:
    """Decode one bounded SEC sidecar/body without duplicate or nonfinite JSON."""
    if type(content) is not bytes:
        raise CompanyFactsLedgerError(f"{label} source content must be bytes")
    if len(content) > maximum_bytes:
        raise CompanyFactsLedgerInputTooLarge(
            f"{label} exceeds bounded payload input limit"
        )

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, item in pairs:
            if key in output:
                raise CompanyFactsLedgerError(
                    f"{label} contains duplicate JSON key: {key}"
                )
            output[key] = item
        return output

    def reject_constant(value: str) -> None:
        raise CompanyFactsLedgerError(
            f"{label} contains non-finite JSON constant: {value}"
        )

    try:
        decoded = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=Decimal,
        )
    except CompanyFactsLedgerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise CompanyFactsLedgerError(f"{label} is not UTF-8 JSON") from exc
    if type(decoded) is not dict:
        raise CompanyFactsLedgerError(f"{label} must be a JSON object")
    return decoded


@dataclass
class _PinnedReadBudget:
    """One aggregate source-read budget; bytes are charged only after a read."""

    maximum: int
    consumed: int = 0

    def ensure_room(self, amount: int, *, label: str) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise CompanyFactsLedgerError(f"{label} source length is invalid")
        if amount > self.maximum or self.consumed + amount > self.maximum:
            raise CompanyFactsLedgerInputTooLarge(
                "combined pinned Company Facts/Submissions source inputs exceed bounded limit"
            )

    def charge(self, content: Any, *, label: str) -> bytes:
        if type(content) is not bytes:
            raise CompanyFactsLedgerError(f"{label} source content must be bytes")
        self.ensure_room(len(content), label=label)
        self.consumed += len(content)
        return content


def _read_pinned_file(
    authority: Any,
    *,
    kind: str,
    relative_path: str,
    label: str,
    maximum_bytes: int,
    budget: _PinnedReadBudget,
) -> bytes:
    remaining = budget.maximum - budget.consumed
    if remaining < 1:
        raise CompanyFactsLedgerInputTooLarge(
            "combined pinned Company Facts/Submissions source inputs exceed bounded limit"
        )
    try:
        read = authority.read_file(
            kind=kind,
            relative_path=relative_path,
            maximum_bytes=min(maximum_bytes, remaining),
        )
        return budget.charge(read.content, label=label)
    except CompanyFactsLedgerError:
        raise
    except Exception as exc:
        raise CompanyFactsLedgerError(f"{label} pinned source read failed") from exc


def _read_pinned_gzip_file(
    authority: Any,
    *,
    relative_path: str,
    expected_sha256: str,
    expected_length: int,
    label: str,
    maximum_bytes: int,
    budget: _PinnedReadBudget,
) -> bytes:
    # Bound the compressed outer object independently of the trusted raw
    # length.  A content-addressed gzip may otherwise carry arbitrary trailing
    # bytes that the decoder ignores, causing a small raw payload to trigger a
    # much larger source read.  This conservative zlib-style bound covers the
    # collector's deterministic gzip output plus wrapper overhead.
    from .filing_attestation import (
        HARD_MAX_COMPANYFACTS_RESPONSE_BYTES,
        gzip_stored_byte_ceiling,
    )

    budget.ensure_room(expected_length, label=label)
    remaining_for_stored = budget.maximum - budget.consumed - expected_length
    if remaining_for_stored < 1:
        raise CompanyFactsLedgerInputTooLarge(
            "combined pinned Company Facts/Submissions source inputs exceed bounded limit"
        )
    stored_limit = min(
        gzip_stored_byte_ceiling(expected_length),
        remaining_for_stored,
        HARD_MAX_COMPANYFACTS_RESPONSE_BYTES,
    )
    try:
        read = authority.read_gzip_file(
            kind="raw",
            relative_path=relative_path,
            expected_sha256=expected_sha256,
            expected_length=expected_length,
            maximum_bytes=maximum_bytes,
            maximum_stored_bytes=stored_limit,
        )
        budget.charge(read.object_read.content, label=f"{label} compressed object")
        return budget.charge(read.content, label=label)
    except CompanyFactsLedgerError:
        raise
    except Exception as exc:
        raise CompanyFactsLedgerError(f"{label} pinned gzip source read failed") from exc


def _pinned_authority(value: Any) -> Any:
    """Rehydrate the exact source authority before every materialization."""
    try:
        from .filing_attestation import PinnedSourceAuthority
    except Exception as exc:  # pragma: no cover - import failure is environmental.
        raise CompanyFactsLedgerError("pinned source authority is unavailable") from exc
    if type(value) is not PinnedSourceAuthority:
        raise CompanyFactsLedgerError(
            "authority must be an exact PinnedSourceAuthority"
        )
    try:
        # The caller's nominal could have had its private store attributes
        # mutated after construction.  Re-opening by the sealed snapshot ID
        # makes the boundary use source-sync's strict manifest validation.
        return PinnedSourceAuthority(store=value._store, snapshot_id=value.snapshot_id)
    except Exception as exc:
        raise CompanyFactsLedgerError("pinned source authority cannot be reopened") from exc


def _require_exact_retrieval_receipt(
    receipt: Mapping[str, Any],
    content: bytes,
    *,
    source: PinnedSubmissionsSource,
    cik: str,
) -> tuple[str, int, datetime]:
    """Validate one immutable SEC retrieval sidecar and its explicit locations."""
    required = {
        "schema",
        "cik",
        "endpoint",
        "url",
        "retrieved_at",
        "sha256",
        "bytes",
        "object_path",
        "http_etag",
        "http_last_modified",
    }
    if set(receipt) != required:
        raise CompanyFactsLedgerError("Submissions receipt shape is invalid")
    if receipt.get("schema") != "fundamental_forensics_retrieval.v1":
        raise CompanyFactsLedgerError("Submissions receipt schema is invalid")
    if receipt.get("endpoint") != "submissions":
        raise CompanyFactsLedgerError("Submissions receipt endpoint is invalid")
    try:
        receipt_cik = _cik(receipt.get("cik"), field="Submissions receipt CIK")
    except CompanyFactsLedgerError:
        raise CompanyFactsLedgerError("Submissions receipt CIK is invalid") from None
    if receipt_cik != cik:
        raise CompanyFactsLedgerError("Submissions receipt CIK does not bind source bundle")
    expected_url = (
        f"https://data.sec.gov/submissions/CIK{cik}.json"
        if not source.is_older
        else f"https://data.sec.gov/submissions/{source.source_name}"
    )
    if receipt.get("url") != expected_url:
        raise CompanyFactsLedgerError("Submissions receipt URL does not bind source name")
    retrieved_at, _ = _required_utc(
        receipt.get("retrieved_at"), field="Submissions receipt retrieved_at"
    )
    digest = receipt.get("sha256")
    length = receipt.get("bytes")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise CompanyFactsLedgerError("Submissions receipt SHA-256 is invalid")
    if isinstance(length, bool) or not isinstance(length, int) or length < 1:
        raise CompanyFactsLedgerError("Submissions receipt byte length is invalid")
    expected_object_path = f"{cik}/submissions/{digest}.json.gz"
    expected_receipt_path = f"{cik}/submissions/{digest}.json.receipt.json"
    if (
        source.object_path != expected_object_path
        or receipt.get("object_path") != expected_object_path
        or source.receipt_path != expected_receipt_path
    ):
        raise CompanyFactsLedgerError(
            "Submissions receipt/object paths do not bind immutable source identity"
        )
    if any(
        value is not None and not isinstance(value, str)
        for value in (receipt.get("http_etag"), receipt.get("http_last_modified"))
    ):
        raise CompanyFactsLedgerError("Submissions receipt HTTP metadata is invalid")
    try:
        expected_receipt_bytes = (
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise CompanyFactsLedgerError("Submissions receipt cannot be canonically encoded") from exc
    if content != expected_receipt_bytes:
        raise CompanyFactsLedgerError("Submissions receipt is not canonically encoded")
    return digest, length, retrieved_at


def _load_pinned_submissions_source(
    authority: Any,
    *,
    source: PinnedSubmissionsSource,
    cik: str,
    config: CompanyFactsLedgerConversionConfig,
    submissions_recorded_at: datetime,
    source_snapshot_at: datetime,
    budget: _PinnedReadBudget,
) -> dict[str, Any]:
    receipt_content = _read_pinned_file(
        authority,
        kind="raw",
        relative_path=source.receipt_path,
        label=f"Submissions {source.source_name} receipt",
        maximum_bytes=config.max_payload_bytes,
        budget=budget,
    )
    receipt = _strict_source_json_object(
        receipt_content,
        label=f"Submissions {source.source_name} receipt",
        maximum_bytes=config.max_payload_bytes,
    )
    digest, length, retrieved_at = _require_exact_retrieval_receipt(
        receipt,
        receipt_content,
        source=source,
        cik=cik,
    )
    if length > config.max_payload_bytes:
        raise CompanyFactsLedgerInputTooLarge(
            f"Submissions {source.source_name} exceeds bounded payload input limit"
        )
    if retrieved_at > submissions_recorded_at:
        raise CompanyFactsLedgerError(
            "Submissions receipt retrieved_at cannot be after submissions_recorded_at"
        )
    if retrieved_at > source_snapshot_at:
        raise CompanyFactsLedgerError(
            "Submissions receipt retrieved_at cannot be after pinned source snapshot_at"
        )
    content = _read_pinned_gzip_file(
        authority,
        relative_path=source.object_path,
        expected_sha256=digest,
        expected_length=length,
        label=f"Submissions {source.source_name} response",
        maximum_bytes=config.max_payload_bytes,
        budget=budget,
    )
    payload = _strict_source_json_object(
        content,
        label=f"Submissions {source.source_name} response",
        maximum_bytes=config.max_payload_bytes,
    )
    response_cik = payload.get("cik")
    if not source.is_older and response_cik is None:
        raise CompanyFactsLedgerError("recent Submissions response must declare a CIK")
    if response_cik is not None:
        try:
            if _cik(response_cik, field="Submissions response CIK") != cik:
                raise CompanyFactsLedgerError(
                    "Submissions response CIK does not bind source bundle"
                )
        except CompanyFactsLedgerError:
            raise CompanyFactsLedgerError(
                "Submissions response CIK does not bind source bundle"
            ) from None
    return payload


def load_companyfacts_ledger_from_pinned_source(
    *,
    authority: Any,
    source_bundle: CompanyFactsConversionSourceBundle,
    submissions_recorded_at: datetime | str,
    config: CompanyFactsLedgerConversionConfig = CompanyFactsLedgerConversionConfig(),
    revision_evidence: Mapping[str, Mapping[str, Any] | RevisionEvidence]
    | Iterable[RevisionEvidence | Mapping[str, Any]]
    | None = None,
) -> CompanyFactsLedgerConversion:
    """Materialize one ledger only from named members of an ``ffsecsrc_`` snapshot.

    The caller selects the issuer-specific source paths and retention clock.
    The loader never performs network I/O, examines a mutable ``latest``
    pointer, reads an ambient filesystem source, derives a missing path, or
    consults the wall clock.  Every older SEC Submissions file declared by the
    selected recent response must have one matching explicit source member.
    """
    if type(source_bundle) is not CompanyFactsConversionSourceBundle:
        raise CompanyFactsLedgerError(
            "source_bundle must be an exact CompanyFactsConversionSourceBundle"
        )
    if type(config) is not CompanyFactsLedgerConversionConfig:
        raise CompanyFactsLedgerError(
            "config must be an exact CompanyFactsLedgerConversionConfig"
        )
    # Reconstruct every caller-owned frozen nominal before the first source
    # read.  ``frozen=True`` prevents ordinary mutation, not low-level
    # ``object.__setattr__`` changes, and nested source values need their own
    # exact-type/path validation rather than nominal trust.
    try:
        config = CompanyFactsLedgerConversionConfig(
            max_occurrences=config.max_occurrences,
            max_payload_bytes=config.max_payload_bytes,
            max_total_input_bytes=config.max_total_input_bytes,
            max_submission_rows=config.max_submission_rows,
            max_older_submissions_files=config.max_older_submissions_files,
            max_revision_evidence=config.max_revision_evidence,
            max_revision_evidence_bytes=config.max_revision_evidence_bytes,
        )
        raw_older = source_bundle.older_submissions
        if type(raw_older) is not tuple:
            raise CompanyFactsLedgerError("older_submissions must be an immutable tuple")
        if len(raw_older) > config.max_older_submissions_files:
            raise CompanyFactsLedgerInputTooLarge(
                "older Submissions source count exceeds bounded limit"
            )

        def exact_source(value: Any) -> PinnedSubmissionsSource:
            if type(value) is not PinnedSubmissionsSource:
                raise CompanyFactsLedgerError(
                    "Submissions sources must be exact PinnedSubmissionsSource values"
                )
            return PinnedSubmissionsSource(
                source_name=value.source_name,
                receipt_path=value.receipt_path,
                object_path=value.object_path,
                is_older=value.is_older,
            )

        source_bundle = CompanyFactsConversionSourceBundle(
            cik=source_bundle.cik,
            companyfacts_manifest_path=source_bundle.companyfacts_manifest_path,
            companyfacts_capture_path=source_bundle.companyfacts_capture_path,
            companyfacts_response_path=source_bundle.companyfacts_response_path,
            recent_submissions=exact_source(source_bundle.recent_submissions),
            older_submissions=tuple(exact_source(item) for item in raw_older),
        )
    except CompanyFactsLedgerError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise CompanyFactsLedgerError(
            "pinned Company Facts conversion configuration is invalid"
        ) from exc
    submissions_recorded_dt, _ = _required_utc(
        submissions_recorded_at, field="submissions_recorded_at"
    )
    sealed_authority = _pinned_authority(authority)
    source_snapshot_dt, _ = _required_utc(
        getattr(sealed_authority, "snapshot_at", None),
        field="pinned source snapshot_at",
    )
    if submissions_recorded_dt > source_snapshot_dt:
        raise CompanyFactsLedgerError(
            "submissions_recorded_at cannot be after pinned source snapshot_at"
        )
    budget = _PinnedReadBudget(maximum=config.max_total_input_bytes)
    try:
        from collectors.fundamental_forensics_companyfacts import (
            companyfacts_capture_from_json_bytes,
            companyfacts_capture_storage_key,
            companyfacts_manifest_storage_key,
            parse_companyfacts_response_exact_numbers,
            validate_companyfacts_manifest,
            validate_companyfacts_response_bytes,
        )

        manifest_content = _read_pinned_file(
            sealed_authority,
            kind="archive",
            relative_path=source_bundle.companyfacts_manifest_path,
            label="Company Facts manifest",
            maximum_bytes=config.max_payload_bytes,
            budget=budget,
        )
        capture_content = _read_pinned_file(
            sealed_authority,
            kind="raw",
            relative_path=source_bundle.companyfacts_capture_path,
            label="Company Facts capture",
            maximum_bytes=config.max_payload_bytes,
            budget=budget,
        )
        manifest = _strict_source_json_object(
            manifest_content,
            label="Company Facts manifest",
            maximum_bytes=config.max_payload_bytes,
        )
        try:
            validate_companyfacts_manifest(manifest)
        except Exception as exc:  # collector owns this source contract.
            raise CompanyFactsLedgerError("Company Facts manifest is invalid") from exc
        if source_canonical_json(manifest).encode("utf-8") != manifest_content:
            raise CompanyFactsLedgerError("Company Facts manifest is not canonical")
        for clock_name, clock_value in manifest["clocks"].items():
            clock_dt, _ = _required_utc(
                clock_value,
                field=f"Company Facts manifest {clock_name}",
            )
            if clock_dt > source_snapshot_dt:
                raise CompanyFactsLedgerError(
                    "Company Facts manifest clock cannot be after pinned source snapshot_at"
                )
        if (
            companyfacts_manifest_storage_key(manifest)
            != source_bundle.companyfacts_manifest_path
            or manifest["issuer"]["cik"] != source_bundle.cik
        ):
            raise CompanyFactsLedgerError(
                "Company Facts manifest does not bind source bundle CIK/path"
            )
        try:
            capture = companyfacts_capture_from_json_bytes(capture_content)
        except Exception as exc:  # collector owns this source contract.
            raise CompanyFactsLedgerError("Company Facts capture is invalid") from exc
        if companyfacts_capture_storage_key(capture.cik, capture.capture_id) != source_bundle.companyfacts_capture_path:
            raise CompanyFactsLedgerError(
                "Company Facts capture path does not bind identity"
            )
        if capture.cik != source_bundle.cik or manifest["source"]["capture_id"] != capture.capture_id:
            raise CompanyFactsLedgerError("Company Facts manifest/capture chain is inconsistent")
        if dict(capture.clocks) != manifest["clocks"]:
            raise CompanyFactsLedgerError(
                "Company Facts manifest clocks differ from capture receipt"
            )
        if (
            manifest["source"]["response_sha256"] != capture.response["sha256"]
            or manifest["source"]["response_bytes"] != capture.response["bytes"]
        ):
            raise CompanyFactsLedgerError(
                "Company Facts manifest/capture response chain is inconsistent"
            )
        if capture.response["object_path"] != source_bundle.companyfacts_response_path:
            raise CompanyFactsLedgerError(
                "Company Facts response path does not bind capture"
            )
        response_length = capture.response["bytes"]
        if response_length > config.max_payload_bytes:
            raise CompanyFactsLedgerInputTooLarge(
                "Company Facts response exceeds bounded payload input limit"
            )
        response_content = _read_pinned_gzip_file(
            sealed_authority,
            relative_path=source_bundle.companyfacts_response_path,
            expected_sha256=capture.response["sha256"],
            expected_length=response_length,
            label="Company Facts response",
            maximum_bytes=config.max_payload_bytes,
            budget=budget,
        )
        try:
            _, logical, occurrence_count, occurrence_sha = validate_companyfacts_response_bytes(
                response_content,
                expected_cik=source_bundle.cik,
            )
        except Exception as exc:  # collector owns exact Company Facts decoding.
            raise CompanyFactsLedgerError("Company Facts response is invalid") from exc
        logical_sha = _sha256(logical)
        if (
            logical_sha != manifest["source"]["logical_sha256"]
            or len(logical) != manifest["source"]["logical_bytes"]
            or occurrence_count != manifest["source"]["fact_occurrence_count"]
            or occurrence_sha != manifest["source"]["fact_occurrence_sha256"]
            or logical_sha != capture.logical["sha256"]
            or len(logical) != capture.logical["bytes"]
            or occurrence_count != capture.logical["fact_occurrence_count"]
            or occurrence_sha != capture.logical["fact_occurrence_sha256"]
        ):
            raise CompanyFactsLedgerError("Company Facts logical source chain is inconsistent")
        try:
            companyfacts = parse_companyfacts_response_exact_numbers(
                response_content,
                expected_cik=source_bundle.cik,
            )
        except Exception as exc:  # collector owns exact number parsing.
            raise CompanyFactsLedgerError(
                "Company Facts exact-number projection is invalid"
            ) from exc

        submissions = _load_pinned_submissions_source(
            sealed_authority,
            source=source_bundle.recent_submissions,
            cik=source_bundle.cik,
            config=config,
            submissions_recorded_at=submissions_recorded_dt,
            source_snapshot_at=source_snapshot_dt,
            budget=budget,
        )
        declared_older = _declared_older_files(
            submissions,
            cik=source_bundle.cik,
        )
        supplied_older = tuple(
            sorted(source.source_name for source in source_bundle.older_submissions)
        )
        if supplied_older != declared_older:
            raise CompanyFactsLedgerError(
                "declared older Submissions files must exactly match supplied pinned sources"
            )
        older_payloads = {
            source.source_name: _load_pinned_submissions_source(
                sealed_authority,
                source=source,
                cik=source_bundle.cik,
                config=config,
                submissions_recorded_at=submissions_recorded_dt,
                source_snapshot_at=source_snapshot_dt,
                budget=budget,
            )
            for source in source_bundle.older_submissions
        }
    except CompanyFactsLedgerError:
        raise
    except Exception as exc:
        raise CompanyFactsLedgerError(
            "pinned Company Facts conversion inputs are invalid"
        ) from exc
    return convert_companyfacts_to_raw_ledger(
        companyfacts=companyfacts,
        capture_manifest=manifest,
        submissions=submissions,
        submissions_recorded_at=submissions_recorded_at,
        older_submissions_files=older_payloads,
        revision_evidence=revision_evidence,
        **config.conversion_kwargs(),
    )


# This name keeps adjacent source-materialization callers from needing to know
# the raw-ledger implementation detail while preserving the strict same API.
materialize_companyfacts_ledger_from_pinned_source = (
    load_companyfacts_ledger_from_pinned_source
)


# Intent-revealing aliases for adjacent ingestion/query lanes.  They all use
# the same strict contract and avoid a second source adapter vocabulary.
convert_verified_companyfacts_to_raw_ledger = convert_companyfacts_to_raw_ledger
build_companyfacts_ledger = convert_companyfacts_to_raw_ledger
ingest_companyfacts_to_raw_ledger = convert_companyfacts_to_raw_ledger


__all__ = [
    "COMPANYFACTS_LEDGER_ADAPTER_VERSION",
    "COMPANYFACTS_LEDGER_RECEIPT_SCHEMA",
    "COMPANYFACTS_LEDGER_SCHEMA",
    "DEFAULT_MAX_OCCURRENCES",
    "DEFAULT_MAX_OLDER_SUBMISSIONS_FILES",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "DEFAULT_MAX_REVISION_EVIDENCE",
    "DEFAULT_MAX_REVISION_EVIDENCE_BYTES",
    "DEFAULT_MAX_SUBMISSION_ROWS",
    "DEFAULT_MAX_TOTAL_INPUT_BYTES",
    "HARD_MAX_OCCURRENCES",
    "HARD_MAX_OLDER_SUBMISSIONS_FILES",
    "HARD_MAX_PAYLOAD_BYTES",
    "HARD_MAX_REVISION_EVIDENCE",
    "HARD_MAX_REVISION_EVIDENCE_BYTES",
    "HARD_MAX_SUBMISSION_ROWS",
    "HARD_MAX_TOTAL_INPUT_BYTES",
    "SUBMISSIONS_CLOCK_SCOPE",
    "CompanyFactsConversionSourceBundle",
    "CompanyFactsLedgerConversion",
    "CompanyFactsLedgerConversionConfig",
    "CompanyFactsLedgerError",
    "CompanyFactsLedgerInputTooLarge",
    "CompanyFactsLedgerOccurrence",
    "CompanyFactsLedgerReceipt",
    "PinnedSubmissionsSource",
    "RevisionEvidence",
    "SubmissionSourceWitness",
    "build_companyfacts_ledger",
    "convert_companyfacts_to_raw_ledger",
    "convert_verified_companyfacts_to_raw_ledger",
    "ingest_companyfacts_to_raw_ledger",
    "load_companyfacts_ledger_from_pinned_source",
    "materialize_companyfacts_ledger_from_pinned_source",
]
