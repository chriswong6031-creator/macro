"""Bind an Exhibit 99.1 body to an event, with exact receipts.

Before this module no code in the estate ingested a release BODY: releases
existed only as revision metadata, so nothing citing a release could be
verified.  Every committed span receipt in the golden corpus pointed at a
transcript.

The parser is NOT written here.  ``engine.fundamental_forensics.disclosure_diff``
already turns supplied filing HTML or text into stable sections and blocks while
retaining byte/character source coordinates, without network access — which is
exactly what a span receipt needs — so this module normalizes through it and
adds the earnings-specific layers on top.

FILING vs EVENT
---------------
These are two different identities and conflating them is the failure the
contract freeze legislates against:

* A **filing** is one submission: ``(cik, accession)``, exactly, no tolerance.
* An **event** is one earnings release: ``(cik, report_date)``.  An 8-K/A is a
  different FILING of the SAME event.  Grouping on the period of report is what
  keeps a correction attached to what it corrects instead of minting a second
  quarter, and it is a value EDGAR publishes (``reportDate``) rather than
  something inferred from proximity.

A filing with no ``report_date`` is its own event and says so
(``EventGroupingAbsence``); guessing a grouping from filing dates would
reintroduce the tolerance-window join by the back door.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping, Sequence

from engine.fundamental_forensics.disclosure_diff import (
    DisclosureDocument,
    normalize_filing,
)

from .figures import ReleaseFigureSet, extract_release_figures
from .filing_key import FilingKey, normalize_accession, normalize_cik
from .receipts import sha256_text

BINDING_SCHEMA = "earnings_release.bound_release/v1"
AUTHORITY = "context_only"

_AMENDMENT_RE = re.compile(r"/A\b", re.I)
_ISO_DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


class BindingError(ValueError):
    """The supplied release cannot be bound as an event document."""


def normalize_acceptance(value: object) -> str:
    """Normalize a SOURCE acceptance timestamp to ISO-8601 UTC, or return "".

    EDGAR's submissions JSON spells this ``2024-02-01T16:30:15.000Z`` and, on
    older shards, ``2024-02-01 16:30:15``.  Both are the SOURCE's timestamp;
    neither is a processing clock, and this function never reads one.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = text.replace("Z", "+00:00")
    if " " in candidate and "T" not in candidate:
        candidate = candidate.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ReleaseRevision:
    """One filed version of a release: the filing, its clocks, its body hash."""

    filing_key: FilingKey
    form: str
    filing_date: str
    acceptance_datetime: str
    report_date: str
    source_sha256: str
    document_id: str
    exhibit_url: str | None = None
    # The estate's existing revision-graph link (the same field name
    # ``engine.earnings_narrative.contracts`` uses in its event manifest).  It
    # is what separates a re-transmitted copy from a correction.
    supersedes_source_sha256: str = ""

    @property
    def is_amendment(self) -> bool:
        """Amendment status comes from the FORM, which the SEC assigns.

        ``8-K/A`` is a correction and earns a new revision; a second plain
        ``8-K`` carrying the same release is a re-transmission and does not.
        Reading this off a document-kind label the estate assigned to itself
        would let a downstream mislabel invent or erase a correction.
        """
        return bool(_AMENDMENT_RE.search(self.form))

    def to_dict(self) -> dict[str, Any]:
        return {
            "filing_key": self.filing_key.key,
            "cik": self.filing_key.cik,
            "accession": self.filing_key.accession,
            "form": self.form,
            "filing_date": self.filing_date,
            "acceptance_datetime": self.acceptance_datetime,
            "report_date": self.report_date,
            "source_sha256": self.source_sha256,
            "supersedes_source_sha256": self.supersedes_source_sha256,
            "document_id": self.document_id,
            "exhibit_url": self.exhibit_url,
            "is_amendment": self.is_amendment,
        }

    def order_key(self) -> tuple[str, str, str]:
        # Acceptance first (the source's own clock), then filing date, then the
        # accession — which is monotonic within a filer-year and therefore a
        # deterministic tie-break rather than an arbitrary one.
        return (self.acceptance_datetime, self.filing_date, self.filing_key.accession)


@dataclass(frozen=True)
class BoundRelease:
    """A release body bound to its filing, parsed, with receipts."""

    revision: ReleaseRevision
    document: DisclosureDocument
    figures: ReleaseFigureSet
    schema: str = BINDING_SCHEMA
    authority: str = AUTHORITY

    @property
    def source(self) -> str:
        return self.document.raw_source

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "authority": self.authority,
            "revision": self.revision.to_dict(),
            "figures": self.figures.to_dict(),
        }


@dataclass(frozen=True)
class EventGroupingAbsence:
    """A filing that could not be grouped into a multi-revision event."""

    filing_key: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"filing_key": self.filing_key, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class CollapsedRevision:
    """A filing that added no new version of the event, and why."""

    filing_key: str
    collapsed_into: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "filing_key": self.filing_key,
            "collapsed_into": self.collapsed_into,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReleaseEvent:
    """One earnings release, however many times it was filed."""

    cik: int
    report_date: str
    revisions: tuple[ReleaseRevision, ...]

    @property
    def event_key(self) -> str:
        return f"{self.cik:010d}|{self.report_date}"

    @property
    def original(self) -> ReleaseRevision:
        return self.revisions[0]

    @property
    def current(self) -> ReleaseRevision:
        return self.revisions[-1]

    @property
    def amended(self) -> bool:
        return any(revision.is_amendment for revision in self.revisions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key,
            "cik": self.cik,
            "report_date": self.report_date,
            "amended": self.amended,
            "revision_count": len(self.revisions),
            "original_accession": self.original.filing_key.accession,
            "current_accession": self.current.filing_key.accession,
            "revisions": [item.to_dict() for item in self.revisions],
        }


@dataclass(frozen=True)
class ReleaseEventSet:
    events: tuple[ReleaseEvent, ...] = ()
    collapsed: tuple[CollapsedRevision, ...] = ()
    ungrouped: tuple[EventGroupingAbsence, ...] = ()

    def event_for(self, filing_key: FilingKey | str) -> ReleaseEvent | None:
        wanted = filing_key.key if isinstance(filing_key, FilingKey) else str(filing_key)
        for event in self.events:
            if any(revision.filing_key.key == wanted for revision in event.revisions):
                return event
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [item.to_dict() for item in self.events],
            "collapsed": [item.to_dict() for item in self.collapsed],
            "ungrouped": [item.to_dict() for item in self.ungrouped],
        }


def _iso_date_or_empty(value: object) -> str:
    text = str(value or "").strip()
    return text if _ISO_DATE_RE.match(text) else ""


def bind_release_document(
    *,
    cik: object,
    accession: object,
    body: str,
    form: str = "8-K",
    filing_date: object = "",
    acceptance_datetime: object = "",
    report_date: object = "",
    exhibit_url: str | None = None,
    content_type: str | None = None,
    registry: Mapping[str, Any] | None = None,
) -> BoundRelease:
    """Normalize one Exhibit 99.1 body and bind it to its filing.

    Pure and offline: the body is supplied, never fetched.  Every figure the
    extractor emits carries a span receipt that was replayed against these exact
    bytes before it was returned.
    """
    if not isinstance(body, str) or not body.strip():
        raise BindingError("release body must be non-empty text")
    key = FilingKey(cik=normalize_cik(cik), accession=normalize_accession(accession))
    form_text = str(form or "").strip() or "8-K"

    payload: dict[str, Any] = {
        "accession": key.accession,
        "entity_cik": f"{key.cik:010d}",
        "form": form_text,
        "content": body,
        "filed_at": _iso_date_or_empty(filing_date),
        "report_date": _iso_date_or_empty(report_date),
        "source_url": exhibit_url or None,
    }
    if content_type:
        payload["content_type"] = content_type
    document = normalize_filing(payload, registry=registry)

    revision = ReleaseRevision(
        filing_key=key,
        form=form_text,
        filing_date=_iso_date_or_empty(filing_date),
        acceptance_datetime=normalize_acceptance(acceptance_datetime),
        report_date=_iso_date_or_empty(report_date),
        source_sha256=document.source_sha256,
        document_id=document.document_id,
        exhibit_url=exhibit_url,
    )
    return BoundRelease(
        revision=revision,
        document=document,
        figures=extract_release_figures(document),
    )


def collapse_release_events(
    revisions: Iterable[ReleaseRevision | BoundRelease],
) -> ReleaseEventSet:
    """Group filings into events; amendments join, duplicates collapse.

    Two collapse rules, both exact and neither date-based:

    * the SAME ``(cik, accession)`` filed twice is one filing seen twice;
    * a different accession whose body hashes identically to a revision already
      held is a re-transmission of that revision, not a new version of the
      event.

    An 8-K/A with its own body is neither: it is a further revision of the same
    event, and it lands in ``revisions`` after the original.
    """
    rows: list[ReleaseRevision] = []
    for item in revisions:
        rows.append(item.revision if isinstance(item, BoundRelease) else item)

    grouped: dict[tuple[int, str], list[ReleaseRevision]] = {}
    ungrouped: list[EventGroupingAbsence] = []
    collapsed: list[CollapsedRevision] = []
    seen_keys: dict[str, ReleaseRevision] = {}

    for row in rows:
        if row.filing_key.key in seen_keys:
            collapsed.append(CollapsedRevision(
                filing_key=row.filing_key.key,
                collapsed_into=row.filing_key.key,
                reason="duplicate_filing_key",
            ))
            continue
        seen_keys[row.filing_key.key] = row
        if not row.report_date:
            ungrouped.append(EventGroupingAbsence(
                filing_key=row.filing_key.key,
                reason="report_date_absent",
                detail=(
                    "the filing declares no period of report, so it cannot be "
                    "grouped with its amendments; grouping it by filing-date "
                    "proximity would be the tolerance-window join the contract "
                    "freeze forbids"
                ),
            ))
        grouped.setdefault((row.filing_key.cik, row.report_date), []).append(row)

    events: list[ReleaseEvent] = []
    for (cik, report_date), members in sorted(grouped.items()):
        members.sort(key=ReleaseRevision.order_key)
        kept: list[ReleaseRevision] = []
        by_body: dict[str, ReleaseRevision] = {}
        for member in members:
            prior = by_body.get(member.source_sha256)
            if prior is not None:
                collapsed.append(CollapsedRevision(
                    filing_key=member.filing_key.key,
                    collapsed_into=prior.filing_key.key,
                    reason="identical_body_sha256",
                ))
                continue
            # The same release reaching the estate twice through two channels
            # (newswire copy and EDGAR exhibit) hashes differently but declares
            # what it supersedes.  A plain 8-K that supersedes a revision we
            # already hold is that copy; an 8-K/A is a correction and stays.
            superseded = by_body.get(member.supersedes_source_sha256 or "")
            if superseded is not None and not member.is_amendment:
                collapsed.append(CollapsedRevision(
                    filing_key=member.filing_key.key,
                    collapsed_into=superseded.filing_key.key,
                    reason="supersedes_without_amending",
                ))
                continue
            by_body[member.source_sha256] = member
            kept.append(member)
        if not report_date:
            # Each ungroupable filing stands alone rather than pooling under a
            # shared empty report date.
            for member in kept:
                events.append(ReleaseEvent(cik=cik, report_date="", revisions=(member,)))
            continue
        events.append(ReleaseEvent(cik=cik, report_date=report_date, revisions=tuple(kept)))

    events.sort(key=lambda event: (event.cik, event.report_date, event.original.order_key()))
    return ReleaseEventSet(
        events=tuple(events),
        collapsed=tuple(collapsed),
        ungrouped=tuple(ungrouped),
    )


def revision_from_submissions_row(
    *,
    cik: object,
    row: Mapping[str, Any],
    source_sha256: str = "",
    document_id: str = "",
    exhibit_url: str | None = None,
    supersedes_source_sha256: str = "",
) -> ReleaseRevision:
    """Build a revision from one parallel-array slice of SEC submissions JSON.

    The field names are EDGAR's own — ``accessionNumber``, ``form``,
    ``filingDate``, ``acceptanceDateTime``, ``reportDate`` — so the adapter is
    a rename, not an interpretation.
    """
    key = FilingKey(
        cik=normalize_cik(cik),
        accession=normalize_accession(row.get("accessionNumber") or row.get("accession")),
    )
    body = str(source_sha256 or "")
    return ReleaseRevision(
        filing_key=key,
        form=str(row.get("form") or "8-K").strip(),
        filing_date=_iso_date_or_empty(row.get("filingDate") or row.get("filing_date")),
        acceptance_datetime=normalize_acceptance(
            row.get("acceptanceDateTime") or row.get("acceptance_datetime")
        ),
        report_date=_iso_date_or_empty(row.get("reportDate") or row.get("report_date")),
        # A revision with no body still needs a stable identity; hashing the
        # filing key keeps two bodiless revisions from colliding on "" and
        # silently collapsing into each other.
        source_sha256=body or sha256_text(f"no-body:{key.key}"),
        document_id=document_id or f"revision:{key.key}",
        exhibit_url=exhibit_url,
        supersedes_source_sha256=str(supersedes_source_sha256 or ""),
    )


def submissions_rows(payload: Mapping[str, Any], *, block: str = "recent") -> list[dict[str, Any]]:
    """Transpose EDGAR's parallel arrays into per-filing dicts.

    The submissions JSON stores each field as its own list, index-aligned.
    Reading them by index in five separate places is how ``accessionNumber``
    came to be read by one module and ignored by the other.
    """
    filings = payload.get("filings") if isinstance(payload, Mapping) else None
    source: Mapping[str, Any]
    if isinstance(filings, Mapping) and block in filings:
        candidate = filings.get(block)
        source = candidate if isinstance(candidate, Mapping) else {}
    elif isinstance(payload, Mapping) and "form" in payload:
        source = payload
    else:
        source = {}
    forms = source.get("form") or []
    if not isinstance(forms, Sequence):
        return []

    def _at(name: str, index: int) -> Any:
        values = source.get(name) or []
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)) and index < len(values):
            return values[index]
        return ""

    return [
        {
            "form": str(form),
            "accessionNumber": _at("accessionNumber", index),
            "filingDate": _at("filingDate", index),
            "acceptanceDateTime": _at("acceptanceDateTime", index),
            "reportDate": _at("reportDate", index),
            "items": _at("items", index),
            "primaryDocument": _at("primaryDocument", index),
        }
        for index, form in enumerate(forms)
    ]


__all__ = [
    "AUTHORITY",
    "BINDING_SCHEMA",
    "BindingError",
    "BoundRelease",
    "CollapsedRevision",
    "EventGroupingAbsence",
    "ReleaseEvent",
    "ReleaseEventSet",
    "ReleaseRevision",
    "bind_release_document",
    "collapse_release_events",
    "normalize_acceptance",
    "revision_from_submissions_row",
    "submissions_rows",
]
