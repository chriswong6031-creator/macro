"""Resolve one observed event to ``event_id → document_revision → span``, or to
a typed absence.

This is the v2 projection contract-freeze Q3 calls for: the event-level
``claim_citations_pending`` boolean becomes DERIVED
(``pending == any(claim has no receipt)``) instead of a stored assertion.  v1 is
untouched — ``contracts.validate_context`` still raises unless the stored flag
is exactly ``True``, and it must keep doing so.

The resolution order is the safety order, and it is deliberate:

1. **Availability firewall.**  A record stamped after the clock that read it is
   quarantined and never published, even when it carries a perfect receipt.
2. **Supersession collapse.**  A duplicate re-delivery resolves to the event the
   original already minted; it never mints a second one.
3. **Byte replay.**  A committed receipt is re-sliced against the body we hold.
   Drift raises rather than downgrades — a receipt that cannot be replayed is
   worthless, and silently demoting it to an absence would hide a corrupted
   store.
4. **Declared address.**  An exact PDF cell or slide region in a document whose
   bytes this estate does not hold: an address, explicitly not a receipt.
5. **Typed absence.**  The fall-through.

Because absence is the fall-through and a receipt can only be minted from bytes
that replay, this resolver cannot manufacture a citation: the failure direction
is always MORE absences, never more receipts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from .contracts import ContractError
from .documents import (
    DocumentError,
    DocumentRevisionChain,
    SourceSpan,
    TypedAbsence,
    address_only_span,
    text_span,
    verify_span,
)
from .events import (
    CompanyEvent,
    FiscalPeriod,
    QuarantineVerdict,
    canonical_event_id,
    quarantine_verdict,
)
from .event_id_adapter import EventAliases, aliases_for


RESOLUTION_SCHEMA = "company_event_resolution.v2"
AUTHORITY = "context_only"

OUTCOMES: tuple[str, ...] = (
    "exact_receipt", "typed_absence", "duplicate_collapsed", "quarantined",
)

# What the verdict RESTS ON.  ``declared_*`` bases are the ones a producer
# asserted rather than proved, and they are counted separately so a suite can
# state exactly how much of a grade came from evidence.
EVIDENCE_BASES: tuple[str, ...] = (
    "byte_replay",
    "timestamp_firewall",
    "supersession_chain",
    "declared_locator",
    "declared_duplicate_filing",
    "no_derivable_receipt",
)
DECLARED_BASES: frozenset[str] = frozenset({"declared_locator", "declared_duplicate_filing"})


class ResolutionError(ContractError):
    """The observation cannot be resolved without guessing."""


@dataclass(frozen=True, slots=True)
class TranscriptSource:
    """A ``mastermind.tx/v1`` body this estate holds, plus its content hash."""

    document_id: str
    body_sha256: str
    segments: tuple[Mapping[str, Any], ...]

    def segment(self, index: int) -> Mapping[str, Any]:
        try:
            return self.segments[index]
        except IndexError:
            raise ResolutionError(f"{self.document_id}: no segment {index}") from None


@dataclass(frozen=True, slots=True)
class DeclaredLocator:
    """A non-text address a source DECLARES but whose bytes we do not hold.

    Kept distinct from evidence throughout: it can only ever produce an
    ``address_only`` span, and stripping it degrades the case to a typed
    absence rather than to a weaker receipt.
    """

    kind: str
    address: Mapping[str, Any]
    reason: str = "document bytes are not held by this estate"


@dataclass(frozen=True, slots=True)
class EventObservation:
    """Everything a producer knows about one observed issuer event."""

    company_id: str
    fiscal_period: FiscalPeriod
    tickers: tuple[str, ...]
    revisions: DocumentRevisionChain
    observation_ref: str = ""
    event_type: str = "earnings_results"
    effective_at: object | None = None
    transcript: TranscriptSource | None = None
    committed_receipt: Mapping[str, Any] | None = None
    declared_locator: DeclaredLocator | None = None
    declared_duplicate_of: str | None = None
    absence_reason: str | None = None
    extra_timestamps: Mapping[str, object] = field(default_factory=dict)

    def without_declared_inputs(self) -> "EventObservation":
        """The same observation with every producer ASSERTION removed.

        Running the corpus twice — once with these inputs, once without — is
        what separates "the resolver derived it" from "the benchmark told it".
        """
        return replace(self, declared_locator=None, declared_duplicate_of=None)

    def availability_stamps(self) -> dict[str, object]:
        stamps: dict[str, object] = {}
        if self.effective_at is not None:
            stamps["event.effective_at"] = self.effective_at
        for document in self.revisions.revisions:
            if document.available_at is not None:
                stamps[f"document_revision.{document.revision}.available_at"] = document.available_at
            if document.published_at is not None:
                stamps[f"document_revision.{document.revision}.published_at"] = document.published_at
        stamps.update(self.extra_timestamps)
        return stamps


@dataclass(frozen=True, slots=True)
class Resolution:
    """The verdict for one observation."""

    observation_ref: str
    outcome: str
    evidence_basis: str
    event_id: str | None = None
    event: CompanyEvent | None = None
    document_id: str | None = None
    document_revision: int | None = None
    span: SourceSpan | None = None
    absence: TypedAbsence | None = None
    quarantine: QuarantineVerdict | None = None
    aliases: EventAliases | None = None
    mints_event: bool = True

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ResolutionError(f"unknown outcome: {self.outcome!r}")
        if self.evidence_basis not in EVIDENCE_BASES:
            raise ResolutionError(f"unknown evidence basis: {self.evidence_basis!r}")

    @property
    def is_declared(self) -> bool:
        return self.evidence_basis in DECLARED_BASES

    @property
    def has_receipt(self) -> bool:
        """Whether a CLAIM on this event resolves to an exact address.

        This is the derived replacement for the stored v1
        ``claim_citations_pending`` flag: pending is the negation of this, per
        claim, computed rather than asserted.
        """
        return self.outcome == "exact_receipt" and self.span is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": RESOLUTION_SCHEMA,
            "authority": AUTHORITY,
            "observation_ref": self.observation_ref,
            "outcome": self.outcome,
            "evidence_basis": self.evidence_basis,
            "event_id": self.event_id,
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "mints_event": self.mints_event,
            "span": self.span.to_payload() if self.span else None,
            "absence": self.absence.to_payload() if self.absence else None,
            "quarantine": self.quarantine.to_payload() if self.quarantine else None,
            "aliases": self.aliases.to_payload() if self.aliases else None,
        }


def _build_event(observation: EventObservation, *, clock: object) -> CompanyEvent:
    """Mint the canonical event and walk it through its lifecycle.

    The transitions are not decoration: ``EventTransition`` refuses an
    ``observed_at`` that precedes ``source_available_at``, so building the event
    is itself the proof that no consumer outran the source.
    """
    source_available_at = observation.effective_at or clock
    event = CompanyEvent.create(
        company_id=observation.company_id,
        fiscal_period=observation.fiscal_period,
        event_type=observation.event_type,
        security_ids=(),
        scheduled_at=observation.effective_at,
    )
    event = event.apply_transition(
        "started",
        observed_at=clock,
        source_available_at=source_available_at,
        effective_at=observation.effective_at,
        reason="source observed",
        document_ids=(observation.revisions.original().document_id,),
    )
    event = event.apply_transition(
        "complete",
        observed_at=clock,
        source_available_at=source_available_at,
        effective_at=observation.effective_at,
        reason="primary source revision available",
    )
    for amendment in observation.revisions.amendments():
        event = event.apply_transition(
            "corrected",
            observed_at=clock,
            source_available_at=amendment.available_at or source_available_at,
            effective_at=observation.effective_at,
            reason=f"revision {amendment.revision} restates the original",
            document_ids=(amendment.document_id,),
        )
    return event


def resolve(observation: EventObservation, *, clock: object) -> Resolution:
    """Resolve one observation.  See the module docstring for the order."""
    aliases = aliases_for(
        observation.company_id,
        observation.fiscal_period,
        observation.tickers,
        event_type=observation.event_type,
    )
    event_id = aliases.canonical_event_id

    verdict = quarantine_verdict(observation.availability_stamps(), observed_at=clock)
    if verdict is not None:
        return Resolution(
            observation_ref=observation.observation_ref,
            outcome="quarantined",
            evidence_basis="timestamp_firewall",
            quarantine=verdict,
            mints_event=False,
        )

    event = _build_event(observation, clock=clock)
    latest = observation.revisions.latest()

    duplicates = observation.revisions.duplicates()
    if duplicates or observation.declared_duplicate_of is not None:
        collapsed = duplicates[-1] if duplicates else latest
        return Resolution(
            observation_ref=observation.observation_ref,
            outcome="duplicate_collapsed",
            evidence_basis="supersession_chain" if duplicates else "declared_duplicate_filing",
            event_id=event_id,
            event=event,
            document_id=collapsed.document_id,
            document_revision=collapsed.revision,
            aliases=aliases,
            mints_event=False,
        )

    if observation.committed_receipt is not None:
        if observation.transcript is None:
            raise ResolutionError(
                f"{observation.observation_ref}: a receipt was supplied with no body to replay it "
                "against, so it can never be proved"
            )
        span = _span_from_receipt(observation)
        return Resolution(
            observation_ref=observation.observation_ref,
            outcome="exact_receipt",
            evidence_basis="byte_replay",
            event_id=event_id,
            event=event,
            document_id=observation.transcript.document_id,
            document_revision=latest.revision,
            span=span,
            aliases=aliases,
        )

    if observation.declared_locator is not None:
        span = address_only_span(
            document_id=latest.document_id,
            document_version=latest.revision,
            kind=observation.declared_locator.kind,
            address=observation.declared_locator.address,
            unreplayable_reason=observation.declared_locator.reason,
            rights_profile=latest.rights_profile,
        )
        return Resolution(
            observation_ref=observation.observation_ref,
            outcome="exact_receipt",
            evidence_basis="declared_locator",
            event_id=event_id,
            event=event,
            document_id=latest.document_id,
            document_revision=latest.revision,
            span=span,
            aliases=aliases,
        )

    absence = TypedAbsence(
        reason=observation.absence_reason or "no_span_addressable_evidence",
        subject=observation.observation_ref or event_id,
        detail="no receipt is derivable from the sources held for this event",
        event_id=event_id,
        document_id=latest.document_id,
    )
    return Resolution(
        observation_ref=observation.observation_ref,
        outcome="typed_absence",
        evidence_basis="no_derivable_receipt",
        event_id=event_id,
        event=event,
        document_id=latest.document_id,
        document_revision=latest.revision,
        absence=absence,
        aliases=aliases,
    )


def _span_from_receipt(observation: EventObservation) -> SourceSpan:
    """Rebuild the span from the committed receipt and REPLAY it both ways."""
    transcript = observation.transcript
    assert transcript is not None  # guarded by the caller
    receipt = dict(observation.committed_receipt or {})
    if receipt.get("source_sha256") != transcript.body_sha256:
        raise DocumentError(
            f"{observation.observation_ref}: receipt does not bind the body held for this event"
        )
    index = receipt.get("segment_index")
    if not isinstance(index, int):
        raise DocumentError(f"{observation.observation_ref}: receipt has no segment index")
    segment = transcript.segment(index)
    segment_text = str(segment.get("text", ""))
    start = receipt.get("span_start_byte")
    end = receipt.get("span_end_byte")
    if not isinstance(start, int) or not isinstance(end, int):
        raise DocumentError(f"{observation.observation_ref}: receipt has no byte bounds")
    quoted = segment_text.encode("utf-8")[start:end].decode("utf-8")
    span = text_span(
        document_id=transcript.document_id,
        document_version=observation.revisions.latest().revision,
        body_sha256=transcript.body_sha256,
        segment_index=index,
        segment_text=segment_text,
        start_byte=start,
        end_byte=end,
        text=quoted,
        speaker=segment.get("speaker"),
        role=segment.get("role"),
        rights_profile=observation.revisions.latest().rights_profile,
    )
    if span.receipt != receipt:
        raise DocumentError(
            f"{observation.observation_ref}: re-derived receipt disagrees with the committed one"
        )
    verify_span(span, segment_text=segment_text, body_sha256=transcript.body_sha256)
    return span


def resolve_all(
    observations: Iterable[EventObservation], *, clock: object
) -> tuple[Resolution, ...]:
    return tuple(resolve(observation, clock=clock) for observation in observations)


def outcome_distribution(resolutions: Sequence[Resolution]) -> dict[str, int]:
    counts = Counter(resolution.outcome for resolution in resolutions)
    return {outcome: counts.get(outcome, 0) for outcome in OUTCOMES}


def evidence_distribution(resolutions: Sequence[Resolution]) -> dict[str, int]:
    counts = Counter(resolution.evidence_basis for resolution in resolutions)
    return {basis: counts.get(basis, 0) for basis in EVIDENCE_BASES}


def canonical_events(resolutions: Sequence[Resolution]) -> tuple[str, ...]:
    """Distinct canonical events these resolutions address.

    Quarantined records are excluded because they are never published at all.
    A duplicate IS included: it resolves to the event its original already
    minted — that is what "collapsed" means.  What a duplicate never does is
    ADD one, which is ``mints_event`` and is counted separately.
    """
    addressed: dict[str, None] = {}
    for resolution in resolutions:
        if resolution.outcome != "quarantined" and resolution.event_id:
            addressed[resolution.event_id] = None
    return tuple(addressed)


def documents_that_mint_events(resolutions: Sequence[Resolution]) -> tuple[str, ...]:
    """The documents that mint a NEW event — duplicates are absent by design."""
    return tuple(
        resolution.document_id or ""
        for resolution in resolutions
        if resolution.mints_event and resolution.document_id
    )


def claim_citations_pending(resolutions: Sequence[Resolution]) -> bool:
    """The DERIVED replacement for the stored v1 flag (contract freeze Q3).

    ``pending == any(claim has no receipt)`` — computed from the claim set, not
    asserted by the producer.  v1's stored boolean is left exactly as it is.
    """
    publishable = [r for r in resolutions if r.outcome != "quarantined"]
    if not publishable:
        return True
    return any(not resolution.has_receipt for resolution in publishable)


def event_id_for(company_id: object, fiscal_period: FiscalPeriod, event_type: str = "earnings_results") -> str:
    return canonical_event_id(company_id, fiscal_period, event_type)
