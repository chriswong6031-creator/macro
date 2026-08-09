"""``company_event.v1`` — the canonical, issuer-keyed company event.

Docket §4.4 gives the envelope, §4.3 the lifecycle.  Two properties are
load-bearing and both are tested:

* **Issuer-keyed identity.**  The id is a pure function of
  ``(company_id, fiscal_period, event_type)``.  It never sees a ticker, so an
  issuer that reports one quarter under two listings still has ONE event.  The
  ticker-keyed ``cie_…`` and ``TICKER/YYYYQn`` ids remain valid aliases through
  ``event_id_adapter``; nothing old is rewritten.
* **Correction stability.**  The id never sees a call date, a document hash, or
  a revision number, so a provider re-dating a call or filing an amendment does
  not fork identity.  ``stable_event_id`` already had this property; it is
  preserved rather than re-derived.

The lifecycle record is the point-in-time firewall.  Every transition carries
``observed_at`` and ``source_available_at``, and a transition observed BEFORE
its source became available is refused — that is the mechanical form of the
Wave 1 acceptance line "availability timestamps prove no consumer outran the
source".
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
import re
from typing import Any, Iterable, Mapping

from .contracts import (
    ContractError,
    normalize_quarter,
    normalize_year,
    parse_date,
)
from .identity import company_id_for_cik


EVENT_SCHEMA = "company_event.v1"
AUTHORITY = "context_only"
PROCESSOR_VERSION = "company_event_spine/1.0.0"

# Docket §4.3.  ``cancelled`` and ``superseded`` are terminal.
EVENT_STATES: frozenset[str] = frozenset({
    "discovered",
    "scheduled",
    "rescheduled",
    "started",
    "completed_partial",
    "complete",
    "corrected",
    "superseded",
    "derived_ready",
    "distributed",
    "cancelled",
})

_TRANSITIONS: dict[str, frozenset[str]] = {
    "discovered": frozenset({"scheduled", "started", "cancelled"}),
    "scheduled": frozenset({"rescheduled", "started", "cancelled"}),
    "rescheduled": frozenset({"rescheduled", "started", "cancelled"}),
    "started": frozenset({"completed_partial", "complete"}),
    "completed_partial": frozenset({"complete", "corrected", "superseded"}),
    "complete": frozenset({"corrected", "superseded", "derived_ready"}),
    "corrected": frozenset({"corrected", "superseded", "derived_ready"}),
    "derived_ready": frozenset({"distributed", "corrected", "superseded"}),
    "distributed": frozenset({"corrected", "superseded"}),
    "superseded": frozenset(),
    "cancelled": frozenset(),
}

# Docket §4.3: "blocked_rights and source_missing are coverage states, not event
# states."  Naming them here means a producer that tries to use one as a state
# gets a specific refusal instead of a generic "unknown state".
COVERAGE_STATES: frozenset[str] = frozenset({"blocked_rights", "source_missing"})

# Contract-freeze Q5.  ``blocked_rights`` is the Wave 7 value and is deliberately
# NOT mintable: a status no code path can produce is a lie in a dropdown.  It is
# named in the target vocabulary so the enum does not have to be re-opened, and
# excluded from ``INTELLIGENCE_STATUS`` so nothing can emit it.
TARGET_STATUS_VOCABULARY: tuple[str, ...] = (
    "ready", "degraded", "stale", "partial", "blocked_rights", "empty",
)
RESERVED_STATUS: frozenset[str] = frozenset({"blocked_rights"})
INTELLIGENCE_STATUS: frozenset[str] = frozenset(TARGET_STATUS_VOCABULARY) - RESERVED_STATUS

# The three genuine status vocabularies converge (freeze Q5).  Per-source status
# and ``source_completeness`` describe SOURCE PRESENCE, an orthogonal axis, and
# are deliberately absent from this table.
_CONTEXT_STATUS_ADAPTER = {"ready": "ready", "partial": "partial", "stale": "stale", "not_covered": "empty"}
_MANIFEST_STATUS_ADAPTER = {"ready": "ready", "degraded": "degraded", "empty": "empty"}
_HEALTH_STATUS_ADAPTER = {"ready": "ready", "degraded": "degraded", "empty": "empty"}

EVENT_TYPES: dict[str, str] = {
    "earnings_results": "results",
    "earnings_call": "call",
    "guidance_update": "guidance",
    "investor_day": "investorday",
    "shareholder_meeting": "meeting",
    "corporate_action": "action",
}

_EVENT_ID_RE = re.compile(r"^evt_cik\d{10}_(\d{4})(q[1-4]|fy)_([a-z0-9]+)$")


class EventError(ContractError):
    """The event envelope or one of its transitions is not trustworthy."""


def adapt_status(value: object, *, vocabulary: str) -> str:
    """Map one of the three legacy status vocabularies onto the typed enum."""
    table = {
        "context": _CONTEXT_STATUS_ADAPTER,
        "manifest": _MANIFEST_STATUS_ADAPTER,
        "health": _HEALTH_STATUS_ADAPTER,
    }.get(vocabulary)
    if table is None:
        raise EventError(f"unknown status vocabulary: {vocabulary!r}")
    text = str(value or "").strip()
    if text not in table:
        raise EventError(f"{vocabulary} status {value!r} is not in that vocabulary")
    return table[text]


def _utc(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        text = str(value or "").strip()
        if not text:
            raise EventError(f"{field_name} is required")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.combine(parse_date(text, field=field_name), datetime.min.time())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class FiscalPeriod:
    """The fiscal label, which belongs to the EVENT (contract freeze Q4).

    A dual-listed issuer publishing under two reporting calendars is a
    DOCUMENT-level presentation difference; the document revision records which
    calendar it presented and the event keeps one fiscal identity.  Putting the
    label on the document would reintroduce two events per issuer quarter
    through the back door.
    """

    year: int
    quarter: int | None = None
    calendar_end: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "year", normalize_year(self.year))
        if self.quarter is not None:
            object.__setattr__(self, "quarter", normalize_quarter(self.quarter))
        if self.calendar_end is not None and not isinstance(self.calendar_end, date):
            object.__setattr__(
                self, "calendar_end", parse_date(self.calendar_end, field="calendar_end")
            )

    @property
    def token(self) -> str:
        return f"{self.year}q{self.quarter}" if self.quarter else f"{self.year}fy"

    def to_payload(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "quarter": self.quarter,
            "calendar_end": self.calendar_end.isoformat() if self.calendar_end else None,
        }


def canonical_event_id(
    company_id: object,
    fiscal_period: FiscalPeriod,
    event_type: str = "earnings_results",
) -> str:
    """``evt_cik0000320193_2026q3_results`` — issuer-keyed, correction-stable.

    Deliberately readable rather than hashed.  ``stable_event_id`` truncates a
    sha256 and therefore cannot be inverted; a canonical id that a human can
    read back to an issuer and a quarter is what makes the alias index
    auditable when a mapping later turns out to be wrong.
    """
    issuer = company_id_for_cik(company_id)
    if not isinstance(fiscal_period, FiscalPeriod):
        raise EventError("fiscal_period must be a FiscalPeriod")
    token = EVENT_TYPES.get(str(event_type))
    if token is None:
        raise EventError(f"unknown event_type: {event_type!r}")
    return f"evt_{issuer.replace(':', '')}_{fiscal_period.token}_{token}"


def parse_canonical_event_id(event_id: object) -> tuple[str, FiscalPeriod, str]:
    """Invert ``canonical_event_id``; raise if the id is not one of ours."""
    text = str(event_id or "").strip()
    match = _EVENT_ID_RE.fullmatch(text)
    if match is None:
        raise EventError(f"not a canonical event id: {event_id!r}")
    year, period_token, type_token = match.groups()
    for name, token in EVENT_TYPES.items():
        if token == type_token:
            event_type = name
            break
    else:
        raise EventError(f"unknown event type token in {event_id!r}")
    quarter = None if period_token == "fy" else int(period_token[1:])
    company_id = company_id_for_cik(text[len("evt_cik"):len("evt_cik") + 10])
    return company_id, FiscalPeriod(year=int(year), quarter=quarter), event_type


@dataclass(frozen=True, slots=True)
class EventTransition:
    """One lifecycle transition — docket §4.3's point-in-time record."""

    prior_state: str | None
    state: str
    observed_at: datetime
    source_available_at: datetime
    effective_at: datetime | None = None
    processor_version: str = PROCESSOR_VERSION
    source_receipt_ids: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.state in COVERAGE_STATES:
            raise EventError(
                f"{self.state} is a coverage state, not an event state (docket §4.3)"
            )
        if self.state not in EVENT_STATES:
            raise EventError(f"unknown event state: {self.state!r}")
        if self.prior_state is not None and self.prior_state not in EVENT_STATES:
            raise EventError(f"unknown prior event state: {self.prior_state!r}")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        object.__setattr__(
            self, "source_available_at", _utc(self.source_available_at, field_name="source_available_at")
        )
        if self.effective_at is not None:
            object.__setattr__(self, "effective_at", _utc(self.effective_at, field_name="effective_at"))
        if self.observed_at < self.source_available_at:
            raise EventError(
                "observed_at precedes source_available_at: a consumer cannot have "
                "seen a transition before its source existed"
            )
        object.__setattr__(self, "source_receipt_ids", tuple(self.source_receipt_ids))
        reason = str(self.reason or "").strip()
        if len(reason) > 400:
            raise EventError("transition reason is too long to be a reason")
        object.__setattr__(self, "reason", reason)

    def to_payload(self) -> dict[str, Any]:
        return {
            "prior_state": self.prior_state,
            "state": self.state,
            "observed_at": _iso(self.observed_at),
            "source_available_at": _iso(self.source_available_at),
            "effective_at": _iso(self.effective_at) if self.effective_at else None,
            "processor_version": self.processor_version,
            "source_receipt_ids": list(self.source_receipt_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CompanyEvent:
    """``company_event.v1``.  Immutable; transitions return a new record."""

    event_id: str
    company_id: str
    fiscal_period: FiscalPeriod
    event_type: str = "earnings_results"
    security_ids: tuple[str, ...] = ()
    state: str = "discovered"
    scheduled_at: datetime | None = None
    source_available_at: datetime | None = None
    observed_at: datetime | None = None
    document_ids: tuple[str, ...] = ()
    supersedes: str | None = None
    point_in_time: bool = True
    transitions: tuple[EventTransition, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", company_id_for_cik(self.company_id))
        expected = canonical_event_id(self.company_id, self.fiscal_period, self.event_type)
        if self.event_id != expected:
            raise EventError(f"event_id {self.event_id!r} is not canonical for this issuer/period")
        if self.state not in EVENT_STATES:
            raise EventError(f"unknown event state: {self.state!r}")
        object.__setattr__(self, "security_ids", tuple(dict.fromkeys(self.security_ids)))
        object.__setattr__(self, "document_ids", tuple(dict.fromkeys(self.document_ids)))
        object.__setattr__(self, "transitions", tuple(self.transitions))
        for name in ("scheduled_at", "source_available_at", "observed_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, field_name=name))

    @classmethod
    def create(
        cls,
        *,
        company_id: object,
        fiscal_period: FiscalPeriod,
        event_type: str = "earnings_results",
        security_ids: Iterable[str] = (),
        **kwargs: Any,
    ) -> "CompanyEvent":
        issuer = company_id_for_cik(company_id)
        return cls(
            event_id=canonical_event_id(issuer, fiscal_period, event_type),
            company_id=issuer,
            fiscal_period=fiscal_period,
            event_type=event_type,
            security_ids=tuple(security_ids),
            **kwargs,
        )

    def can_transition_to(self, state: str) -> bool:
        return state in _TRANSITIONS.get(self.state, frozenset())

    def apply_transition(
        self,
        state: str,
        *,
        observed_at: object,
        source_available_at: object,
        effective_at: object | None = None,
        reason: str = "",
        source_receipt_ids: Iterable[str] = (),
        document_ids: Iterable[str] = (),
        processor_version: str = PROCESSOR_VERSION,
    ) -> "CompanyEvent":
        """Return the event advanced to ``state``, keeping the SAME ``event_id``.

        An amendment is a ``corrected`` transition: it adds a document revision
        and invalidates derivatives, and the logical event id is untouched.
        """
        if not self.can_transition_to(state):
            raise EventError(f"illegal transition {self.state} → {state}")
        transition = EventTransition(
            prior_state=self.state,
            state=state,
            observed_at=observed_at,
            source_available_at=source_available_at,
            effective_at=effective_at,
            processor_version=processor_version,
            source_receipt_ids=tuple(source_receipt_ids),
            reason=reason,
        )
        if self.transitions and transition.observed_at < self.transitions[-1].observed_at:
            raise EventError("transitions must be observed in non-decreasing order")
        merged = tuple(dict.fromkeys((*self.document_ids, *document_ids)))
        return replace(
            self,
            state=state,
            transitions=(*self.transitions, transition),
            document_ids=merged,
            observed_at=transition.observed_at,
            source_available_at=transition.source_available_at,
        )

    def with_documents(self, document_ids: Iterable[str]) -> "CompanyEvent":
        return replace(self, document_ids=tuple(dict.fromkeys((*self.document_ids, *document_ids))))

    def latest_source_available_at(self) -> datetime | None:
        stamps = [t.source_available_at for t in self.transitions]
        if self.source_available_at is not None:
            stamps.append(self.source_available_at)
        return max(stamps) if stamps else None

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": EVENT_SCHEMA,
            "authority": AUTHORITY,
            "event_id": self.event_id,
            "company_id": self.company_id,
            "security_ids": list(self.security_ids),
            "event_type": self.event_type,
            "fiscal_period": self.fiscal_period.to_payload(),
            "state": self.state,
            "scheduled_at": _iso(self.scheduled_at) if self.scheduled_at else None,
            "source_available_at": _iso(self.source_available_at) if self.source_available_at else None,
            "observed_at": _iso(self.observed_at) if self.observed_at else None,
            "document_ids": list(self.document_ids),
            "supersedes": self.supersedes,
            "point_in_time": self.point_in_time,
            "transitions": [t.to_payload() for t in self.transitions],
        }


@dataclass(frozen=True, slots=True)
class QuarantineVerdict:
    """Evidence that a record is unobservable at the reading clock."""

    offending_field: str
    record_timestamp: datetime
    observed_at: datetime
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "offending_field": self.offending_field,
            "record_timestamp": _iso(self.record_timestamp),
            "observed_at": _iso(self.observed_at),
            "reason": self.reason,
        }


def quarantine_verdict(
    stamps: Mapping[str, object],
    *,
    observed_at: object,
) -> QuarantineVerdict | None:
    """Return the first stamp that postdates the reading clock, or ``None``.

    Publishing a record stamped after the clock that read it is precisely how a
    consumer outruns its source, so this is a refusal rather than a warning.
    ``stamps`` is ordered by the caller: the earliest-declared offending field
    wins so the verdict is deterministic.
    """
    clock = _utc(observed_at, field_name="observed_at")
    for field_name, value in stamps.items():
        if value is None:
            continue
        stamp = _utc(value, field_name=field_name)
        if stamp > clock:
            return QuarantineVerdict(
                offending_field=field_name,
                record_timestamp=stamp,
                observed_at=clock,
                reason=f"{field_name} is stamped after the observation time",
            )
    return None
