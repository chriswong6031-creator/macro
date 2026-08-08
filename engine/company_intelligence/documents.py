"""``source_document.v1`` / ``source_span.v1`` — the receipt layer.

Docket §4.5: "The span is the fundamental receipt.  A citation in an article,
Brain answer, Topic cluster, relationship edge, or guidance comparison must
resolve through it."

The receipt discipline is taken directly from
``engine/earnings_narrative/contracts.py`` rather than re-derived: a text span
is minted through that module's ``receipt_for_span``, which re-hashes the
segment, re-slices the bytes, and raises when the slice does not reproduce the
quoted text.  ``verify_span`` replays the same check against the document body
on the way OUT.  A receipt that cannot be replayed is worthless, so an
unreplayable span is a refusal, never a warning.

Two receipt states exist and they are never interchangeable:

* ``byte_replayed`` — a UTF-8 byte span inside a document body we hold.  It
  carries ``text_sha256`` and can be re-proved offline at any time.
* ``address_only`` — an exact address (PDF table cell, slide page region) in a
  document whose bytes this estate does not hold yet.  It carries NO
  ``text_sha256`` and is explicitly marked unreplayable.  Emitting one as if it
  were a byte receipt is the "silently upgrade document-level lineage to
  span-level lineage" failure that handoff §Wave 1.8 forbids by name.

Where neither is derivable the answer is a ``TypedAbsence``, not a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import sha256
import re
from typing import Any, Iterable, Mapping

from .contracts import ContractError, parse_date
from .identity import company_id_for_cik
from ..earnings_narrative.contracts import ContractError as NarrativeContractError
from ..earnings_narrative.contracts import _RECEIPT_KEYS, receipt_for_span, sha256_bytes


DOCUMENT_SCHEMA = "source_document.v1"
SPAN_SCHEMA = "source_span.v1"
ABSENCE_SCHEMA = "typed_absence.v1"
AUTHORITY = "context_only"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")

SOURCE_CLASSES: frozenset[str] = frozenset({
    "primary_filing", "issuer_release", "transcript", "presentation", "third_party",
})
DOCUMENT_KINDS: frozenset[str] = frozenset({
    "filing", "release", "release_amendment", "release_duplicate",
    "transcript", "transcript_only", "presentation", "supplement",
})
# A duplicate is a re-delivery of a document we already hold; an amendment
# restates it.  The distinction decides whether an event is minted, so it lives
# in one place instead of being re-derived per call site.
DUPLICATE_KINDS: frozenset[str] = frozenset({"release_duplicate"})
AMENDMENT_KINDS: frozenset[str] = frozenset({"release_amendment"})

# Docket §4.5's example uses ``kind: transcript_segment``; the golden corpus
# names the same shape ``text_span``.  They are one kind, normalized here.
LOCATOR_KINDS: frozenset[str] = frozenset({"text_span", "table_cell", "slide_region"})
_LOCATOR_ALIASES = {"transcript_segment": "text_span"}
REPLAYABLE_LOCATOR_KINDS: frozenset[str] = frozenset({"text_span"})

RECEIPT_STATES: frozenset[str] = frozenset({"byte_replayed", "address_only"})

# Closed vocabulary.  A free-text absence reason cannot be counted, and the
# whole point of typed absence is that it is countable.
ABSENCE_REASONS: frozenset[str] = frozenset({
    "no_source_document",
    "no_transcript",
    "no_primary_release",
    "no_span_addressable_evidence",
    "document_bytes_not_held",
    "scanned_image_no_text_layer",
    "unjoinable_filing_identity",
    "speaker_unresolvable",
    "slide_family_discontinued",
    "superseded_by_duplicate",
    "missing_basis",
    "missing_units",
    "missing_period",
    "missing_source",
})

RIGHTS_STATES: frozenset[str] = frozenset({
    "public_primary", "licensed", "internal_only", "unknown",
})


class DocumentError(ContractError):
    """The document, revision chain, or span cannot back a citation."""


def _sha(value: object, *, field_name: str) -> str:
    text = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(text):
        raise DocumentError(f"{field_name} is not a sha256: {value!r}")
    return text


def _utc(value: object | None, *, field_name: str) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.combine(parse_date(text, field=field_name), datetime.min.time())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class FilingKey:
    """``(cik, accession)`` — the canonical filing key (contract freeze Q2).

    Not ``(cik, filing_date)`` with a tolerance window: a fuzzy date join cannot
    support the "no consumer outran the source" claim, and amendments would
    collapse into their originals.
    """

    cik: str
    accession: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cik", company_id_for_cik(self.cik).split(":", 1)[1])
        accession = str(self.accession or "").strip()
        if not _ACCESSION_RE.fullmatch(accession):
            raise DocumentError(f"not an EDGAR accession: {self.accession!r}")
        object.__setattr__(self, "accession", accession)

    def to_payload(self) -> dict[str, str]:
        return {"cik": self.cik, "accession": self.accession}


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One versioned source object (docket §4.1 / §4.4 ``document_ids``)."""

    document_id: str
    event_id: str
    document_kind: str
    source_class: str
    content_sha256: str
    revision: int = 1
    content_bytes: int | None = None
    filing_key: FilingKey | None = None
    fetched_at: datetime | None = None
    published_at: datetime | None = None
    available_at: datetime | None = None
    supersedes_document_id: str | None = None
    superseded_by_document_id: str | None = None
    rights_profile: str = "rp_unknown_v1"
    rights_state: str = "unknown"
    # Contract freeze Q4: the fiscal LABEL belongs to the event.  What a
    # document may record is which calendar it PRESENTED — a dual-listed issuer
    # can publish one event under two calendars without forking the event.
    presented_fiscal_label: str | None = None
    holds_bytes: bool = True

    def __post_init__(self) -> None:
        document_id = str(self.document_id or "").strip()
        if not document_id or len(document_id) > 128:
            raise DocumentError(f"unusable document_id: {self.document_id!r}")
        object.__setattr__(self, "document_id", document_id)
        if self.document_kind not in DOCUMENT_KINDS:
            raise DocumentError(f"unknown document_kind: {self.document_kind!r}")
        if self.source_class not in SOURCE_CLASSES:
            raise DocumentError(f"unknown source_class: {self.source_class!r}")
        if self.rights_state not in RIGHTS_STATES:
            raise DocumentError(f"unknown rights_state: {self.rights_state!r}")
        object.__setattr__(self, "content_sha256", _sha(self.content_sha256, field_name="content_sha256"))
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise DocumentError(f"revision must be a positive integer: {self.revision!r}")
        if self.content_bytes is not None and (
            isinstance(self.content_bytes, bool)
            or not isinstance(self.content_bytes, int)
            or self.content_bytes < 0
        ):
            raise DocumentError(f"content_bytes invalid: {self.content_bytes!r}")
        for name in ("fetched_at", "published_at", "available_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), field_name=name))
        if self.revision > 1 and self.supersedes_document_id is None:
            raise DocumentError(
                f"{self.document_id}: revision {self.revision} names no predecessor, so the "
                "supersession chain cannot be walked"
            )

    @property
    def is_duplicate(self) -> bool:
        return self.document_kind in DUPLICATE_KINDS

    @property
    def is_amendment(self) -> bool:
        return self.document_kind in AMENDMENT_KINDS

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": DOCUMENT_SCHEMA,
            "authority": AUTHORITY,
            "document_id": self.document_id,
            "event_id": self.event_id,
            "document_kind": self.document_kind,
            "source_class": self.source_class,
            "revision": self.revision,
            "content_sha256": self.content_sha256,
            "content_bytes": self.content_bytes,
            "filing_key": self.filing_key.to_payload() if self.filing_key else None,
            "fetched_at": _iso(self.fetched_at),
            "published_at": _iso(self.published_at),
            "available_at": _iso(self.available_at),
            "supersedes_document_id": self.supersedes_document_id,
            "superseded_by_document_id": self.superseded_by_document_id,
            "rights_profile": self.rights_profile,
            "rights_state": self.rights_state,
            "presented_fiscal_label": self.presented_fiscal_label,
            "holds_bytes": self.holds_bytes,
        }


@dataclass(frozen=True, slots=True)
class DocumentRevisionChain:
    """The ordered revisions of one logical source object.

    The chain is what makes "amendments preserve event identity" and "duplicate
    releases do not create duplicate events" mechanical rather than aspirational:
    ``mints_event`` is False for every duplicate, and an amendment is a new
    revision of the SAME chain, so the event id never moves.
    """

    revisions: tuple[SourceDocument, ...]

    def __post_init__(self) -> None:
        revisions = tuple(self.revisions)
        if not revisions:
            raise DocumentError("a revision chain needs at least one revision")
        ordered = tuple(sorted(revisions, key=lambda doc: doc.revision))
        expected = list(range(1, len(ordered) + 1))
        if [doc.revision for doc in ordered] != expected:
            raise DocumentError(
                f"revision numbers are not contiguous from 1: {[d.revision for d in ordered]}"
            )
        event_ids = {doc.event_id for doc in ordered}
        if len(event_ids) != 1:
            raise DocumentError(f"a revision chain cannot span events: {sorted(event_ids)}")
        for previous, current in zip(ordered, ordered[1:]):
            if current.supersedes_document_id not in {previous.document_id, previous.content_sha256}:
                raise DocumentError(
                    f"revision {current.revision} does not supersede revision {previous.revision}"
                )
        object.__setattr__(self, "revisions", ordered)

    @property
    def event_id(self) -> str:
        return self.revisions[0].event_id

    def latest(self) -> SourceDocument:
        return self.revisions[-1]

    def original(self) -> SourceDocument:
        return self.revisions[0]

    def amendments(self) -> tuple[SourceDocument, ...]:
        return tuple(doc for doc in self.revisions if doc.is_amendment)

    def duplicates(self) -> tuple[SourceDocument, ...]:
        return tuple(doc for doc in self.revisions if doc.is_duplicate)

    def mints_event(self, document: SourceDocument) -> bool:
        """Only the ORIGINAL revision mints an event.

        An amendment corrects the event it already belongs to; a duplicate is a
        re-delivery and mints nothing.  Both keep ``event_id`` constant, which is
        the property the corpus's amendment and duplicate_release classes exist
        to grade.
        """
        return document.revision == 1 and not document.is_duplicate

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "revision_count": len(self.revisions),
            "latest_revision": self.latest().revision,
            "has_amendment": bool(self.amendments()),
            "has_duplicate": bool(self.duplicates()),
            "revisions": [doc.to_payload() for doc in self.revisions],
        }


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """``source_span.v1`` — an exact evidence address plus its receipt state."""

    span_id: str
    document_id: str
    document_version: int
    locator: Mapping[str, Any]
    receipt_state: str
    text_sha256: str | None = None
    display_excerpt: str | None = None
    rights_profile: str = "rp_unknown_v1"
    receipt: Mapping[str, Any] | None = None
    unreplayable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.receipt_state not in RECEIPT_STATES:
            raise DocumentError(f"unknown receipt_state: {self.receipt_state!r}")
        locator = dict(self.locator or {})
        kind = _LOCATOR_ALIASES.get(str(locator.get("kind")), str(locator.get("kind")))
        if kind not in LOCATOR_KINDS:
            raise DocumentError(f"unknown locator kind: {locator.get('kind')!r}")
        locator["kind"] = kind
        object.__setattr__(self, "locator", locator)
        if self.receipt_state == "byte_replayed":
            if kind not in REPLAYABLE_LOCATOR_KINDS:
                raise DocumentError(f"{kind} cannot carry a byte receipt in this estate")
            if self.receipt is None:
                raise DocumentError("a byte_replayed span must carry its receipt")
            if set(self.receipt) != set(_RECEIPT_KEYS):
                raise DocumentError("receipt does not match the earnings_narrative receipt shape")
            _sha(self.text_sha256, field_name="text_sha256")
            if self.text_sha256 != self.receipt.get("text_sha256"):
                raise DocumentError("span text_sha256 disagrees with its own receipt")
        else:
            if self.text_sha256 is not None or self.receipt is not None:
                raise DocumentError(
                    "an address_only span must not carry a text hash or a receipt: it would "
                    "read as span-level lineage this estate does not hold"
                )
            if not str(self.unreplayable_reason or "").strip():
                raise DocumentError("an address_only span must name why it cannot be replayed")

    @property
    def is_replayable(self) -> bool:
        return self.receipt_state == "byte_replayed"

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": SPAN_SCHEMA,
            "authority": AUTHORITY,
            "span_id": self.span_id,
            "document_id": self.document_id,
            "document_version": self.document_version,
            "locator": dict(self.locator),
            "text_sha256": self.text_sha256,
            "display_excerpt": self.display_excerpt,
            "rights_profile": self.rights_profile,
            "receipt_state": self.receipt_state,
            "receipt": dict(self.receipt) if self.receipt else None,
            "unreplayable_reason": self.unreplayable_reason,
        }


def _span_id(document_id: str, locator: Mapping[str, Any]) -> str:
    material = "|".join(f"{key}={locator[key]}" for key in sorted(locator))
    return "span_" + sha256(f"{document_id}|{material}".encode("utf-8")).hexdigest()[:20]


def text_span(
    *,
    document_id: str,
    document_version: int,
    body_sha256: str,
    segment_index: int,
    segment_text: str,
    start_byte: int,
    end_byte: int,
    text: str,
    speaker: str | None = None,
    role: str | None = None,
    chapter: str | None = None,
    rights_profile: str = "rp_unknown_v1",
    display_excerpt: str | None = None,
) -> SourceSpan:
    """Mint a byte-replayable ``source_span.v1``.

    Delegates to ``earnings_narrative.contracts.receipt_for_span``, which
    re-slices the segment and refuses when the slice does not reproduce the
    exact UTF-8 text.  Reusing it — rather than writing a second hasher — is
    what keeps the two estates' receipts the same object.
    """
    try:
        receipt = receipt_for_span(
            source_sha256=body_sha256,
            segment_index=segment_index,
            segment_text=segment_text,
            start_byte=start_byte,
            end_byte=end_byte,
            text=text,
        )
    except NarrativeContractError as exc:
        raise DocumentError(f"span does not replay against its segment: {exc}") from exc
    locator: dict[str, Any] = {
        "kind": "text_span",
        "sub_kind": "transcript_segment",
        "segment_index": segment_index,
        "span_start_byte": start_byte,
        "span_end_byte": end_byte,
    }
    if chapter is not None:
        locator["chapter"] = chapter
    if speaker is not None:
        locator["speaker"] = speaker
    if role is not None:
        locator["role"] = role
    return SourceSpan(
        span_id=_span_id(document_id, locator),
        document_id=document_id,
        document_version=document_version,
        locator=locator,
        receipt_state="byte_replayed",
        text_sha256=receipt["text_sha256"],
        display_excerpt=display_excerpt if display_excerpt is not None else text,
        rights_profile=rights_profile,
        receipt=receipt,
    )


def address_only_span(
    *,
    document_id: str,
    document_version: int,
    kind: str,
    address: Mapping[str, Any],
    unreplayable_reason: str,
    rights_profile: str = "rp_unknown_v1",
) -> SourceSpan:
    """Mint an exact ADDRESS with no byte receipt (PDF cell, slide region).

    The address is exact — page, table, row, column — so a reader can be sent
    to the precise place.  What it is not is a receipt, and the record says so
    in ``receipt_state`` and ``unreplayable_reason`` rather than leaving a
    consumer to infer it from a missing hash.
    """
    normalized = _LOCATOR_ALIASES.get(str(kind), str(kind))
    if normalized in REPLAYABLE_LOCATOR_KINDS:
        raise DocumentError(
            f"{normalized} is byte-replayable in this estate; mint it with text_span()"
        )
    locator = {"kind": normalized, **{str(k): v for k, v in dict(address).items()}}
    if not str(unreplayable_reason or "").strip():
        raise DocumentError("an address_only span must name why it cannot be replayed")
    return SourceSpan(
        span_id=_span_id(document_id, locator),
        document_id=document_id,
        document_version=document_version,
        locator=locator,
        receipt_state="address_only",
        rights_profile=rights_profile,
        unreplayable_reason=unreplayable_reason,
    )


def verify_span(span: SourceSpan, *, segment_text: str, body_sha256: str) -> None:
    """Replay a byte receipt against the document body; raise on any drift.

    This is the outbound half of the discipline.  Minting proves the span was
    right when it was made; replay proves it is still right against the body we
    hold now — which is the check that catches a tampered or re-issued body.
    """
    if not span.is_replayable:
        raise DocumentError(f"{span.span_id} carries no byte receipt to replay")
    receipt = dict(span.receipt or {})
    if receipt.get("source_sha256") != body_sha256:
        raise DocumentError(f"{span.span_id}: receipt does not bind this document body")
    segment_bytes = segment_text.encode("utf-8")
    if sha256_bytes(segment_bytes) != receipt.get("segment_sha256"):
        raise DocumentError(f"{span.span_id}: segment hash disagrees with the receipt")
    if len(segment_bytes) != receipt.get("segment_bytes"):
        raise DocumentError(f"{span.span_id}: segment length disagrees with the receipt")
    start = receipt.get("span_start_byte")
    end = receipt.get("span_end_byte")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(segment_bytes):
        raise DocumentError(f"{span.span_id}: span bounds do not lie inside the segment")
    if sha256_bytes(segment_bytes[start:end]) != receipt.get("text_sha256"):
        raise DocumentError(f"{span.span_id}: replayed bytes do not reproduce the cited text")


@dataclass(frozen=True, slots=True)
class TypedAbsence:
    """A named, countable absence — a first-class value, not a null.

    Handoff §Wave 1.5: a number without basis, units, period, and source is
    ABSENT, not guessed.  ``for_number`` builds exactly that verdict.
    """

    reason: str
    subject: str
    detail: str = ""
    missing_fields: tuple[str, ...] = ()
    event_id: str | None = None
    document_id: str | None = None

    def __post_init__(self) -> None:
        if self.reason not in ABSENCE_REASONS:
            raise DocumentError(f"unknown absence reason: {self.reason!r}")
        subject = str(self.subject or "").strip()
        if not subject:
            raise DocumentError("a typed absence must name its subject")
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": ABSENCE_SCHEMA,
            "authority": AUTHORITY,
            "reason": self.reason,
            "subject": self.subject,
            "detail": self.detail,
            "missing_fields": list(self.missing_fields),
            "event_id": self.event_id,
            "document_id": self.document_id,
        }


_NUMBER_REQUIRED = ("basis", "units", "period", "source")


def absent_number(
    subject: str,
    *,
    basis: object = None,
    units: object = None,
    period: object = None,
    source: object = None,
    event_id: str | None = None,
) -> TypedAbsence | None:
    """Return the absence verdict for a number, or ``None`` if it is complete."""
    missing = [
        name
        for name, value in zip(_NUMBER_REQUIRED, (basis, units, period, source))
        if value is None or str(value).strip() == ""
    ]
    if not missing:
        return None
    return TypedAbsence(
        reason=f"missing_{missing[0]}",
        subject=subject,
        detail=f"a number without {', '.join(missing)} is absent, not guessed",
        missing_fields=tuple(missing),
        event_id=event_id,
    )


def documents_for_event(documents: Iterable[SourceDocument], event_id: str) -> tuple[SourceDocument, ...]:
    return tuple(doc for doc in documents if doc.event_id == event_id)
