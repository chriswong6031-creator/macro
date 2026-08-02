"""Typed fiscal-period and safe flow-derivation kernel.

Financial filings contain intervals, not automatically comparable "quarters".
This module makes period semantics explicit and only derives a Q4 or TTM when
the required temporal, entity, unit, dimensional, and availability gates all
pass.  A failed gate yields ``not_evaluable``; missing evidence yields
``not_available``.  Neither case is a numeric zero or a quiet fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import (
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Subnormal,
    Underflow,
    localcontext,
)
from enum import Enum
from itertools import islice
from typing import Any, Iterable, Mapping

from .raw_ledger import (
    AvailabilityStatus,
    ReplayClock,
    TemporalClocks,
    canonical_json,
    decimal_text,
    parse_utc,
    stable_id,
    utc_text,
)


PERIOD_SCHEMA = "fundamental_forensics.periods/v1"
PERIOD_DECIMAL_PRECISION = 34
PERIOD_DECIMAL_EMIN = -6143
PERIOD_DECIMAL_EMAX = 6144
MAX_PERIOD_DECIMAL_COEFFICIENT_DIGITS = 8192
MAX_PERIOD_DECIMAL_SERIALIZED_CHARS = 8192
MAX_PERIOD_TEXT_CHARS = 4096
MAX_PERIOD_DIMENSIONS = 128
MAX_PERIOD_SEMANTIC_TAGS = 64
MAX_PERIOD_SOURCE_IDS = 16_384
MAX_PERIOD_LINEAGE_IDS = 32_768
MAX_PERIOD_QUALITY_FLAGS = 256
MAX_DERIVATION_REASONS = 64
MAX_DERIVATION_INPUT_IDS = 64


class PeriodKind(str, Enum):
    """Primary period role of a fact or derived observation."""

    INSTANT = "instant"
    DURATION = "duration"
    FISCAL_QUARTER = "fiscal_quarter"
    YTD = "ytd"
    ANNUAL = "annual"
    DIRECT_Q4 = "direct_q4"
    DERIVED_Q4 = "derived_q4"
    TTM = "ttm"
    STUB = "stub"


class CalendarKind(str, Enum):
    """Fiscal-calendar metadata that must not be inferred away."""

    UNKNOWN = "unknown"
    WEEK_52 = "52_week"
    WEEK_53 = "53_week"
    STUB = "stub"


class FlowDerivationKind(str, Enum):
    DERIVED_Q4 = "annual_minus_ytd"
    TTM = "sum_four_discrete_quarters"


def _require_text(value: Any, *, field_name: str) -> str:
    if isinstance(value, float):
        raise ValueError(f"{field_name} cannot be a binary float")
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    if len(text) > MAX_PERIOD_TEXT_CHARS:
        raise ValueError(f"{field_name} exceeds the text safety limit")
    return text


def _bounded_tuple(
    values: Iterable[Any], *, maximum: int, field_name: str
) -> tuple[Any, ...]:
    try:
        iterator = iter(values)
        items = tuple(islice(iterator, maximum + 1))
    except Exception as exc:
        raise ValueError(f"{field_name} must be a bounded iterable") from exc
    if len(items) > maximum:
        raise ValueError(f"{field_name} exceeds the item safety limit {maximum}")
    return items


def _bounded_text_ids(
    values: Iterable[Any], *, maximum: int, field_name: str
) -> tuple[str, ...]:
    items = _bounded_tuple(values, maximum=maximum, field_name=field_name)
    return tuple(
        sorted({_require_text(item, field_name=field_name) for item in items})
    )


def _parse_date(value: date | str, *, field_name: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a date, not datetime")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc


def _decimal(value: Decimal | str | int, *, field_name: str) -> Decimal:
    if isinstance(value, float):
        raise ValueError(f"{field_name} cannot be a binary float; pass Decimal or source text")
    if isinstance(value, str) and len(value) > MAX_PERIOD_DECIMAL_SERIALIZED_CHARS:
        raise ValueError(f"{field_name} exceeds the decimal text safety limit")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite: {value!r}")
    if len(parsed.as_tuple().digits) > MAX_PERIOD_DECIMAL_COEFFICIENT_DIGITS:
        raise ValueError(f"{field_name} exceeds the decimal coefficient safety limit")
    if (
        parsed != 0
        and not PERIOD_DECIMAL_EMIN <= parsed.adjusted() <= PERIOD_DECIMAL_EMAX
    ):
        raise ValueError(f"{field_name} exponent is outside the period decimal contract")
    try:
        serialized = decimal_text(parsed)
    except ValueError as exc:
        raise ValueError(f"{field_name} exceeds the decimal serialization safety limit") from exc
    if serialized is None or len(serialized) > MAX_PERIOD_DECIMAL_SERIALIZED_CHARS:
        raise ValueError(f"{field_name} exceeds the decimal serialization safety limit")
    return parsed


def _period_decimal_context() -> Context:
    """Return an unshared deterministic context for additive derivations."""
    context = Context(
        prec=PERIOD_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=PERIOD_DECIMAL_EMIN,
        Emax=PERIOD_DECIMAL_EMAX,
        capitals=1,
        clamp=0,
    )
    for signal in (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal):
        context.traps[signal] = True
    return context


def _canonical_dimensions(
    value: Mapping[str, Any] | Iterable[tuple[str, Any]] | None,
) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    try:
        raw = value.items() if isinstance(value, Mapping) else value
    except Exception as exc:
        raise ValueError("dimensions must be a bounded mapping or pair iterable") from exc
    items = _bounded_tuple(
        raw, maximum=MAX_PERIOD_DIMENSIONS, field_name="dimensions"
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        try:
            axis, member = item
        except (TypeError, ValueError) as exc:
            raise ValueError("dimensions must contain (axis, member) pairs") from exc
        normalized_axis = _require_text(axis, field_name="dimension axis")
        if normalized_axis in seen:
            raise ValueError(f"dimensions contains duplicate axis: {normalized_axis}")
        seen.add(normalized_axis)
        if isinstance(member, (dict, list, tuple, set, frozenset)):
            try:
                normalized_member = canonical_json(member)
            except Exception as exc:
                raise ValueError("dimension member cannot be canonicalized") from exc
            if len(normalized_member) > MAX_PERIOD_TEXT_CHARS:
                raise ValueError("dimension member exceeds the text safety limit")
        else:
            normalized_member = _require_text(member, field_name="dimension member")
        out.append((normalized_axis, normalized_member))
    return tuple(sorted(out))


def _duration_days(start: date, end: date) -> int:
    return (end - start).days


def _approx_weeks(start: date, end: date) -> int:
    """Nearest whole fiscal week, stable around ordinary 91/92-day quarters."""
    return (_duration_days(start, end) + 3) // 7


def _semantics_for(kind: PeriodKind, calendar_kind: CalendarKind) -> tuple[str, ...]:
    tags: set[str] = {kind.value}
    if kind is not PeriodKind.INSTANT:
        tags.add(PeriodKind.DURATION.value)
    if kind in {PeriodKind.FISCAL_QUARTER, PeriodKind.DIRECT_Q4, PeriodKind.DERIVED_Q4}:
        tags.add(PeriodKind.FISCAL_QUARTER.value)
    if kind in {PeriodKind.DIRECT_Q4, PeriodKind.DERIVED_Q4}:
        tags.add("q4")
    if calendar_kind is CalendarKind.WEEK_53:
        tags.add("53_week")
    if calendar_kind is CalendarKind.STUB or kind is PeriodKind.STUB:
        tags.add(PeriodKind.STUB.value)
    return tuple(sorted(tags))


@dataclass(frozen=True)
class TypedPeriod:
    """A period with a single primary role and explicit fiscal semantics.

    Dates use XBRL-style interval semantics: ``start`` is inclusive and ``end``
    is the reported period-end date.  The duration is therefore ``end-start``;
    this matches SEC facts such as 2024-01-01 through 2025-01-01 = 366 days.
    """

    kind: PeriodKind | str
    end: date | str
    start: date | str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN
    fiscal_year_weeks: int | None = None
    week_count: int | None = None
    semantics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        kind = PeriodKind(self.kind)
        calendar_kind = CalendarKind(self.calendar_kind)
        end = _parse_date(self.end, field_name="period end")
        start = _parse_date(self.start, field_name="period start") if self.start is not None else None
        if kind is PeriodKind.INSTANT:
            if start is not None:
                raise ValueError("instant period cannot have start")
        elif start is None:
            raise ValueError(f"{kind.value} period requires start")
        if start is not None and start >= end:
            raise ValueError("period start must precede end")
        if self.fiscal_year is not None and (
            type(self.fiscal_year) is not int or self.fiscal_year < 1
        ):
            raise ValueError("fiscal_year must be a positive integer when supplied")
        if self.fiscal_quarter is not None and (
            type(self.fiscal_quarter) is not int
            or self.fiscal_quarter not in {1, 2, 3, 4}
        ):
            raise ValueError("fiscal_quarter must be 1, 2, 3, or 4")
        if self.fiscal_quarter is not None and self.fiscal_year is None:
            raise ValueError("fiscal_quarter requires fiscal_year")
        if kind in {
            PeriodKind.FISCAL_QUARTER,
            PeriodKind.YTD,
            PeriodKind.ANNUAL,
            PeriodKind.DIRECT_Q4,
            PeriodKind.DERIVED_Q4,
        } and self.fiscal_year is None:
            raise ValueError(f"{kind.value} period requires fiscal_year")
        if kind in {PeriodKind.FISCAL_QUARTER, PeriodKind.DIRECT_Q4, PeriodKind.DERIVED_Q4, PeriodKind.YTD}:
            if self.fiscal_quarter is None:
                raise ValueError(f"{kind.value} period requires fiscal_quarter")
        if kind is PeriodKind.DIRECT_Q4 and self.fiscal_quarter != 4:
            raise ValueError("direct_q4 requires fiscal_quarter=4")
        if kind is PeriodKind.DERIVED_Q4 and self.fiscal_quarter != 4:
            raise ValueError("derived_q4 requires fiscal_quarter=4")
        if kind is PeriodKind.YTD and self.fiscal_quarter not in {1, 2, 3}:
            raise ValueError("YTD is reserved for Q1/Q2/Q3 cumulative periods; annual owns Q4")
        if kind is PeriodKind.ANNUAL and self.fiscal_quarter is not None:
            raise ValueError("annual period cannot claim a fiscal_quarter")
        if kind is PeriodKind.STUB and calendar_kind is not CalendarKind.STUB:
            calendar_kind = CalendarKind.STUB
        if calendar_kind is CalendarKind.STUB and kind not in {PeriodKind.STUB, PeriodKind.DURATION}:
            raise ValueError("a stub calendar must use stub or generic duration period kind")
        if self.fiscal_year_weeks is not None and (
            type(self.fiscal_year_weeks) is not int
            or self.fiscal_year_weeks not in {52, 53}
        ):
            raise ValueError("fiscal_year_weeks must be 52 or 53")
        if self.fiscal_year_weeks == 53 and calendar_kind is CalendarKind.UNKNOWN:
            calendar_kind = CalendarKind.WEEK_53
        if self.fiscal_year_weeks == 52 and calendar_kind is CalendarKind.UNKNOWN:
            calendar_kind = CalendarKind.WEEK_52
        if calendar_kind is CalendarKind.WEEK_52 and self.fiscal_year_weeks not in {None, 52}:
            raise ValueError("52-week calendar cannot declare a 53-week fiscal year")
        if calendar_kind is CalendarKind.WEEK_53 and self.fiscal_year_weeks not in {None, 53}:
            raise ValueError("53-week calendar requires fiscal_year_weeks=53 when supplied")
        if self.week_count is not None and (
            type(self.week_count) is not int or self.week_count <= 0
        ):
            raise ValueError("week_count must be a positive integer")
        if kind is PeriodKind.INSTANT and self.week_count is not None:
            raise ValueError("instant period cannot have week_count")
        actual_weeks = _approx_weeks(start, end) if start is not None else None
        if self.week_count is not None and actual_weeks is not None and self.week_count != actual_weeks:
            raise ValueError(
                f"week_count={self.week_count} conflicts with date interval of {actual_weeks} weeks"
            )
        if (
            kind in {PeriodKind.ANNUAL, PeriodKind.TTM}
            and self.fiscal_year_weeks is not None
            and actual_weeks is not None
            and self.fiscal_year_weeks != actual_weeks
        ):
            raise ValueError(
                f"fiscal_year_weeks={self.fiscal_year_weeks} conflicts with date interval of {actual_weeks} weeks"
            )
        if (
            kind in {PeriodKind.ANNUAL, PeriodKind.TTM}
            and calendar_kind is CalendarKind.WEEK_53
            and self.fiscal_year_weeks != 53
        ):
            raise ValueError("53-week annual/TTM periods require fiscal_year_weeks=53")
        tags = set(_semantics_for(kind, calendar_kind))
        semantic_tags = _bounded_tuple(
            self.semantics,
            maximum=MAX_PERIOD_SEMANTIC_TAGS,
            field_name="period semantic tags",
        )
        tags.update(
            _require_text(tag, field_name="period semantic tag")
            for tag in semantic_tags
        )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "calendar_kind", calendar_kind)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "semantics", tuple(sorted(tags)))

    @property
    def is_instant(self) -> bool:
        return self.kind is PeriodKind.INSTANT

    @property
    def is_duration(self) -> bool:
        return not self.is_instant

    @property
    def duration_days(self) -> int | None:
        return _duration_days(self.start, self.end) if self.start else None

    @property
    def inferred_week_count(self) -> int | None:
        if self.start is None:
            return None
        return self.week_count if self.week_count is not None else _approx_weeks(self.start, self.end)

    @property
    def is_stub(self) -> bool:
        return self.kind is PeriodKind.STUB or self.calendar_kind is CalendarKind.STUB

    @property
    def is_53_week(self) -> bool:
        return self.calendar_kind is CalendarKind.WEEK_53 or self.fiscal_year_weeks == 53

    @property
    def is_discrete_quarter(self) -> bool:
        return self.kind in {
            PeriodKind.FISCAL_QUARTER,
            PeriodKind.DIRECT_Q4,
            PeriodKind.DERIVED_Q4,
        }

    @property
    def quarter_ordinal(self) -> int | None:
        if not self.is_discrete_quarter or self.fiscal_year is None or self.fiscal_quarter is None:
            return None
        return (self.fiscal_year * 4) + self.fiscal_quarter

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat(),
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "calendar_kind": self.calendar_kind.value,
            "fiscal_year_weeks": self.fiscal_year_weeks,
            "week_count": self.week_count,
            "inferred_week_count": self.inferred_week_count,
            "semantics": list(self.semantics),
        }


def instant_period(end: date | str, *, fiscal_year: int | None = None, fiscal_quarter: int | None = None) -> TypedPeriod:
    return TypedPeriod(
        kind=PeriodKind.INSTANT,
        end=end,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
    )


def duration_period(
    start: date | str,
    end: date | str,
    *,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN,
    week_count: int | None = None,
) -> TypedPeriod:
    return TypedPeriod(
        kind=PeriodKind.DURATION,
        start=start,
        end=end,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        calendar_kind=calendar_kind,
        week_count=week_count,
    )


def fiscal_quarter_period(
    start: date | str,
    end: date | str,
    *,
    fiscal_year: int,
    fiscal_quarter: int,
    direct_q4: bool = False,
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN,
    week_count: int | None = None,
) -> TypedPeriod:
    kind = PeriodKind.DIRECT_Q4 if direct_q4 else PeriodKind.FISCAL_QUARTER
    if direct_q4 and fiscal_quarter != 4:
        raise ValueError("direct_q4 can only be set for fiscal_quarter=4")
    return TypedPeriod(
        kind=kind,
        start=start,
        end=end,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        calendar_kind=calendar_kind,
        week_count=week_count,
    )


def ytd_period(
    start: date | str,
    end: date | str,
    *,
    fiscal_year: int,
    through_quarter: int,
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN,
    week_count: int | None = None,
) -> TypedPeriod:
    return TypedPeriod(
        kind=PeriodKind.YTD,
        start=start,
        end=end,
        fiscal_year=fiscal_year,
        fiscal_quarter=through_quarter,
        calendar_kind=calendar_kind,
        week_count=week_count,
    )


def annual_period(
    start: date | str,
    end: date | str,
    *,
    fiscal_year: int,
    fiscal_year_weeks: int | None = None,
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN,
) -> TypedPeriod:
    inferred_calendar = CalendarKind(calendar_kind)
    if fiscal_year_weeks == 53 and inferred_calendar is CalendarKind.UNKNOWN:
        inferred_calendar = CalendarKind.WEEK_53
    if fiscal_year_weeks == 52 and inferred_calendar is CalendarKind.UNKNOWN:
        inferred_calendar = CalendarKind.WEEK_52
    return TypedPeriod(
        kind=PeriodKind.ANNUAL,
        start=start,
        end=end,
        fiscal_year=fiscal_year,
        calendar_kind=inferred_calendar,
        fiscal_year_weeks=fiscal_year_weeks,
        week_count=fiscal_year_weeks,
    )


def stub_period(
    start: date | str,
    end: date | str,
    *,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
) -> TypedPeriod:
    return TypedPeriod(
        kind=PeriodKind.STUB,
        start=start,
        end=end,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        calendar_kind=CalendarKind.STUB,
    )


@dataclass(frozen=True)
class PeriodObservation:
    """A typed flow/instant observation with enough lineage for derivation."""

    entity_id: str
    metric: str
    unit: str
    value: Decimal | str | int
    period: TypedPeriod
    clocks: TemporalClocks
    dimensions: Mapping[str, Any] | tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    observation_id: str | None = None
    source_occurrence_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    lineage_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    revision_basis: str | None = None
    quality_flags: tuple[str, ...] | list[str] = field(default_factory=tuple)
    derivation_kind: FlowDerivationKind | str | None = None

    def __post_init__(self) -> None:
        entity_id = _require_text(self.entity_id, field_name="entity_id")
        metric = _require_text(self.metric, field_name="metric")
        unit = _require_text(self.unit, field_name="unit")
        value = _decimal(self.value, field_name="value")
        if not isinstance(self.period, TypedPeriod):
            raise TypeError("period must be a TypedPeriod")
        if not isinstance(self.clocks, TemporalClocks):
            raise TypeError("clocks must be TemporalClocks")
        dimensions = _canonical_dimensions(self.dimensions)
        source_ids = _bounded_text_ids(
            self.source_occurrence_ids,
            maximum=MAX_PERIOD_SOURCE_IDS,
            field_name="source_occurrence_id",
        )
        lineage = _bounded_text_ids(
            self.lineage_ids,
            maximum=MAX_PERIOD_LINEAGE_IDS,
            field_name="lineage_id",
        )
        flags = _bounded_text_ids(
            self.quality_flags,
            maximum=MAX_PERIOD_QUALITY_FLAGS,
            field_name="quality_flag",
        )
        revision_basis = _require_text(self.revision_basis, field_name="revision_basis") if self.revision_basis else None
        derivation_kind = FlowDerivationKind(self.derivation_kind) if self.derivation_kind else None
        payload = {
            "entity_id": entity_id,
            "metric": metric,
            "unit": unit,
            "value": decimal_text(value),
            "period": self.period.to_dict(),
            "dimensions": dimensions,
            # An observation is an event, not only an economic value.  Bind
            # every availability clock so caches cannot conflate the same
            # calculation published in two different knowledge states.
            "clocks": self.clocks.to_dict(),
            "source_occurrence_ids": source_ids,
            "lineage_ids": lineage,
            "revision_basis": revision_basis,
            "quality_flags": flags,
            "derivation_kind": derivation_kind.value if derivation_kind else None,
        }
        computed_observation_id = stable_id("period_observation", payload)
        if self.observation_id is not None:
            supplied_observation_id = _require_text(
                self.observation_id, field_name="observation_id"
            )
            if supplied_observation_id != computed_observation_id:
                raise ValueError("observation_id does not match canonical observation content")
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "source_occurrence_ids", source_ids)
        object.__setattr__(self, "lineage_ids", lineage)
        object.__setattr__(self, "revision_basis", revision_basis)
        object.__setattr__(self, "quality_flags", flags)
        object.__setattr__(self, "derivation_kind", derivation_kind)
        object.__setattr__(self, "observation_id", computed_observation_id)

    @property
    def compatibility_key(self) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
        return self.entity_id, self.metric, self.unit, self.dimensions

    @property
    def accepted_at(self) -> datetime | None:
        return self.clocks.accepted_at

    @property
    def recorded_at(self) -> datetime:
        return self.clocks.recorded_at

    def ready_at(self, clock: ReplayClock | str) -> datetime | None:
        return self.clocks.ready_at(clock)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "entity_id": self.entity_id,
            "metric": self.metric,
            "unit": self.unit,
            "value": decimal_text(self.value),
            "period": self.period.to_dict(),
            "dimensions": dict(self.dimensions),
            "clocks": self.clocks.to_dict(),
            "source_occurrence_ids": list(self.source_occurrence_ids),
            "lineage_ids": list(self.lineage_ids),
            "revision_basis": self.revision_basis,
            "quality_flags": list(self.quality_flags),
            "derivation_kind": self.derivation_kind.value if self.derivation_kind else None,
        }


@dataclass(frozen=True)
class DerivationResult:
    """A value plus exact input lineage, or an intentional typed non-result."""

    status: AvailabilityStatus
    derivation_kind: FlowDerivationKind
    observation: PeriodObservation | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    input_observation_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        status = AvailabilityStatus(self.status)
        derivation_kind = FlowDerivationKind(self.derivation_kind)
        reasons = _bounded_text_ids(
            self.reasons,
            maximum=MAX_DERIVATION_REASONS,
            field_name="derivation reason",
        )
        inputs = _bounded_text_ids(
            self.input_observation_ids,
            maximum=MAX_DERIVATION_INPUT_IDS,
            field_name="input_observation_id",
        )
        if status is AvailabilityStatus.AVAILABLE and self.observation is None:
            raise ValueError("available derivation requires observation")
        if status is not AvailabilityStatus.AVAILABLE and self.observation is not None:
            raise ValueError("non-available derivation cannot contain observation")
        if status is AvailabilityStatus.AVAILABLE and reasons:
            raise ValueError("available derivation cannot contain no-result reasons")
        if status is not AvailabilityStatus.AVAILABLE and not reasons:
            raise ValueError("non-available derivation requires a reason")
        if self.observation is not None and self.observation.derivation_kind is not derivation_kind:
            raise ValueError("derived observation must declare the result derivation_kind")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "derivation_kind", derivation_kind)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "input_observation_ids", inputs)

    @property
    def is_available(self) -> bool:
        return self.status is AvailabilityStatus.AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "derivation_kind": self.derivation_kind.value,
            "observation": self.observation.to_dict() if self.observation else None,
            "reasons": list(self.reasons),
            "input_observation_ids": list(self.input_observation_ids),
        }


def _not_available(kind: FlowDerivationKind, *reasons: str, inputs: Iterable[PeriodObservation] = ()) -> DerivationResult:
    return DerivationResult(
        status=AvailabilityStatus.NOT_AVAILABLE,
        derivation_kind=kind,
        reasons=tuple(reasons),
        input_observation_ids=tuple(item.observation_id for item in inputs),
    )


def _not_evaluable(kind: FlowDerivationKind, *reasons: str, inputs: Iterable[PeriodObservation] = ()) -> DerivationResult:
    return DerivationResult(
        status=AvailabilityStatus.NOT_EVALUABLE,
        derivation_kind=kind,
        reasons=tuple(reasons),
        input_observation_ids=tuple(item.observation_id for item in inputs),
    )


def _check_cutoff(
    observations: Iterable[PeriodObservation],
    *,
    as_of: datetime | str | None,
    clock: ReplayClock | str,
    kind: FlowDerivationKind,
) -> DerivationResult | None:
    if as_of is None:
        return None
    cutoff = parse_utc(as_of, field_name="as_of")
    if cutoff is None:  # pragma: no cover - guarded above
        raise ValueError("as_of is required when a clock is supplied")
    replay_clock = ReplayClock(clock)
    items = tuple(observations)
    missing = [item.observation_id for item in items if item.ready_at(replay_clock) is None]
    if missing:
        return DerivationResult(
            status=AvailabilityStatus.NOT_AVAILABLE,
            derivation_kind=kind,
            reasons=(f"required inputs unavailable at requested {replay_clock.value} cutoff",),
        )
    future = [item.observation_id for item in items if item.ready_at(replay_clock) > cutoff]
    if future:
        # Do not expose a future occurrence ID, exact readiness clock, or a
        # reason whose wording changes with future-only ledger structure.
        return DerivationResult(
            status=AvailabilityStatus.NOT_AVAILABLE,
            derivation_kind=kind,
            reasons=(f"required inputs unavailable at requested {replay_clock.value} cutoff",),
        )
    return None


def _combined_clocks(
    inputs: Iterable[PeriodObservation],
    *,
    mapping_available_at: datetime | str,
    computed_at: datetime | str,
    published_at: datetime | str,
) -> TemporalClocks:
    items = tuple(inputs)
    if not items:
        raise ValueError("derived clocks require at least one input")
    mapping = parse_utc(mapping_available_at, field_name="mapping_available_at")
    computed = parse_utc(computed_at, field_name="computed_at")
    published = parse_utc(published_at, field_name="published_at")
    if mapping is None or computed is None or published is None:  # pragma: no cover - required args
        raise ValueError("mapping_available_at, computed_at, and published_at are required")
    source_times = [item.clocks.accepted_at for item in items]
    accepted = max(source_times) if all(value is not None for value in source_times) else None
    recorded = max(item.clocks.recorded_at for item in items)
    dependency_system_ready = max(item.clocks.system_ready_at for item in items)
    if computed < dependency_system_ready:
        raise ValueError("computed_at cannot precede the system-ready time of any dependency")
    if computed < mapping:
        raise ValueError("computed_at cannot precede mapping_available_at")
    if published < computed:
        raise ValueError("published_at cannot precede computed_at")
    return TemporalClocks(
        accepted_at=accepted,
        recorded_at=recorded,
        mapping_available_at=mapping,
        computed_at=computed,
        published_at=published,
    )


def _check_governance_cutoff(
    *,
    mapping_available_at: datetime | str,
    computed_at: datetime | str,
    published_at: datetime | str,
    as_of: datetime | str | None,
    clock: ReplayClock | str,
    kind: FlowDerivationKind,
) -> DerivationResult | None:
    """Gate future rule/artifact clocks before evaluating their relationships."""
    if as_of is None or ReplayClock(clock) is not ReplayClock.SYSTEM:
        return None
    cutoff = parse_utc(as_of, field_name="as_of")
    mapping = parse_utc(mapping_available_at, field_name="mapping_available_at")
    computed = parse_utc(computed_at, field_name="computed_at")
    published = parse_utc(published_at, field_name="published_at")
    if cutoff is None or mapping is None or computed is None or published is None:
        raise ValueError("system derivation clocks are required")
    if max(mapping, computed, published) > cutoff:
        return DerivationResult(
            status=AvailabilityStatus.NOT_AVAILABLE,
            derivation_kind=kind,
            reasons=("derivation governance unavailable at requested system cutoff",),
        )
    return None


def _check_derived_output_cutoff(
    clocks: TemporalClocks,
    *,
    as_of: datetime | str | None,
    clock: ReplayClock | str,
    kind: FlowDerivationKind,
    inputs: Iterable[PeriodObservation],
) -> DerivationResult | None:
    """Block actual-system replay until the *new* artifact was consumable."""
    if as_of is None:
        return None
    cutoff = parse_utc(as_of, field_name="as_of")
    if cutoff is None:  # pragma: no cover - guarded by caller signature
        raise ValueError("as_of is required when a clock is supplied")
    replay_clock = ReplayClock(clock)
    if replay_clock is ReplayClock.SYSTEM and clocks.system_ready_at > cutoff:
        return DerivationResult(
            status=AvailabilityStatus.NOT_AVAILABLE,
            derivation_kind=kind,
            reasons=("derived artifact not available at requested system cutoff",),
        )
    return None


def _same_revision_basis(inputs: Iterable[PeriodObservation]) -> bool:
    """Require one explicit vintage basis for every arithmetic dependency."""
    values = tuple(inputs)
    bases = tuple(item.revision_basis for item in values)
    return bool(values) and all(bases) and len(set(bases)) == 1


def _comparable(inputs: Iterable[PeriodObservation]) -> tuple[bool, str | None]:
    values = tuple(inputs)
    if not values:
        return False, "no inputs"
    if len({item.compatibility_key for item in values}) != 1:
        return False, "entity, metric, unit, or dimensions are incompatible"
    if not _same_revision_basis(values):
        return False, "inputs require one explicit common revision_basis"
    return True, None


def _unique_lineage(inputs: Iterable[PeriodObservation], rule_id: str) -> tuple[str, ...]:
    ids: set[str] = {rule_id}
    for item in inputs:
        ids.add(item.observation_id)
        ids.update(item.source_occurrence_ids)
        ids.update(item.lineage_ids)
    return tuple(sorted(ids))


def derive_q4(
    annual: PeriodObservation | None,
    ytd: PeriodObservation | None,
    *,
    mapping_available_at: datetime | str,
    computed_at: datetime | str,
    published_at: datetime | str,
    rule_id: str = "derived_q4/annual_minus_ytd/v1",
    as_of: datetime | str | None = None,
    clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
) -> DerivationResult:
    """Derive a discrete Q4 only from a compatible annual and nine-month YTD flow.

    53-week years are allowed only when their annual/YTD week metadata makes the
    resulting 14-week Q4 explicit.  Stub fiscal years are never silently
    annualized or subtracted.
    """
    kind = FlowDerivationKind.DERIVED_Q4
    present = tuple(item for item in (annual, ytd) if item is not None)
    governance_cutoff = _check_governance_cutoff(
        mapping_available_at=mapping_available_at,
        computed_at=computed_at,
        published_at=published_at,
        as_of=as_of,
        clock=clock,
        kind=kind,
    )
    if governance_cutoff:
        return governance_cutoff
    cutoff = _check_cutoff(present, as_of=as_of, clock=clock, kind=kind)
    if cutoff:
        return cutoff
    if annual is None or ytd is None:
        missing = "annual" if annual is None else "ytd"
        return _not_available(kind, f"missing required {missing} input", inputs=present)
    compatible, reason = _comparable((annual, ytd))
    if not compatible:
        return _not_evaluable(kind, reason or "inputs incompatible", inputs=(annual, ytd))
    if annual.period.kind is not PeriodKind.ANNUAL:
        return _not_evaluable(kind, "annual input is not typed annual", inputs=(annual, ytd))
    if ytd.period.kind is not PeriodKind.YTD or ytd.period.fiscal_quarter != 3:
        return _not_evaluable(kind, "YTD input must be a Q3 cumulative period", inputs=(annual, ytd))
    if annual.period.is_stub or ytd.period.is_stub:
        return _not_evaluable(kind, "stub fiscal periods cannot support derived Q4", inputs=(annual, ytd))
    if annual.period.fiscal_year != ytd.period.fiscal_year:
        return _not_evaluable(kind, "annual and YTD inputs must share fiscal_year", inputs=(annual, ytd))
    if annual.period.start != ytd.period.start:
        return _not_evaluable(kind, "annual and YTD intervals must share fiscal-year start", inputs=(annual, ytd))
    if ytd.period.end >= annual.period.end:
        return _not_evaluable(kind, "YTD interval must end before annual interval", inputs=(annual, ytd))
    annual_weeks = annual.period.inferred_week_count
    ytd_weeks = ytd.period.inferred_week_count
    if annual_weeks not in {52, 53}:
        return _not_evaluable(
            kind,
            f"annual interval must be 52 or 53 weeks; got {annual_weeks}",
            inputs=(annual, ytd),
        )
    if ytd_weeks != 39:
        return _not_evaluable(
            kind,
            f"Q3 YTD interval must be 39 weeks; got {ytd_weeks}",
            inputs=(annual, ytd),
        )
    if annual_weeks == 53 and annual.period.fiscal_year_weeks != 53:
        return _not_evaluable(kind, "53-week annual requires explicit fiscal_year_weeks=53", inputs=(annual, ytd))
    if annual_weeks == 52 and annual.period.is_53_week:
        return _not_evaluable(kind, "52-week annual cannot carry 53-week calendar metadata", inputs=(annual, ytd))
    if annual_weeks == 52 and ytd.period.is_53_week:
        return _not_evaluable(kind, "YTD 53-week metadata conflicts with a non-53-week annual", inputs=(annual, ytd))

    # A YTD end date is inclusive in an issuer's displayed calendar.  The
    # discrete Q4 interval starts on the following day, otherwise it overlaps
    # Q3 and cannot later participate in a four-quarter TTM.
    q4_start = ytd.period.end + timedelta(days=1)
    q4_weeks = _approx_weeks(q4_start, annual.period.end)
    expected_q4_weeks = annual_weeks - ytd_weeks
    if q4_weeks != expected_q4_weeks:
        return _not_evaluable(
            kind,
            f"annual/YTD geometry must leave a {expected_q4_weeks}-week Q4; got {q4_weeks}",
            inputs=(annual, ytd),
        )
    try:
        clocks = _combined_clocks(
            (annual, ytd),
            mapping_available_at=mapping_available_at,
            computed_at=computed_at,
            published_at=published_at,
        )
    except ValueError as exc:
        return _not_evaluable(kind, str(exc), inputs=(annual, ytd))
    output_cutoff = _check_derived_output_cutoff(
        clocks,
        as_of=as_of,
        clock=clock,
        kind=kind,
        inputs=(annual, ytd),
    )
    if output_cutoff:
        return output_cutoff
    period = TypedPeriod(
        kind=PeriodKind.DERIVED_Q4,
        start=q4_start,
        end=annual.period.end,
        fiscal_year=annual.period.fiscal_year,
        fiscal_quarter=4,
        calendar_kind=CalendarKind.WEEK_53 if annual_weeks == 53 else annual.period.calendar_kind,
        fiscal_year_weeks=annual.period.fiscal_year_weeks,
        week_count=q4_weeks,
    )
    try:
        with localcontext(_period_decimal_context()):
            derived_value = annual.value - ytd.value
    except (DecimalException, OverflowError):
        return _not_evaluable(
            kind,
            "derived Q4 arithmetic is outside the fixed decimal contract",
            inputs=(annual, ytd),
        )
    derived = PeriodObservation(
        entity_id=annual.entity_id,
        metric=annual.metric,
        unit=annual.unit,
        value=derived_value,
        period=period,
        clocks=clocks,
        dimensions=annual.dimensions,
        source_occurrence_ids=tuple(
            sorted(set(annual.source_occurrence_ids).union(ytd.source_occurrence_ids))
        ),
        lineage_ids=_unique_lineage((annual, ytd), rule_id),
        revision_basis=annual.revision_basis or ytd.revision_basis,
        derivation_kind=kind,
    )
    return DerivationResult(
        status=AvailabilityStatus.AVAILABLE,
        derivation_kind=kind,
        observation=derived,
        input_observation_ids=(annual.observation_id, ytd.observation_id),
    )


def _quarter_sort_key(item: PeriodObservation) -> tuple[int, date, str]:
    ordinal = item.period.quarter_ordinal
    if ordinal is None:  # caller validates
        raise ValueError("quarter sort requested for non-quarter observation")
    return ordinal, item.period.end, item.observation_id


def derive_ttm(
    quarters: Iterable[PeriodObservation],
    *,
    mapping_available_at: datetime | str,
    computed_at: datetime | str,
    published_at: datetime | str,
    rule_id: str = "ttm/sum_four_discrete_quarters/v1",
    as_of: datetime | str | None = None,
    clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
) -> DerivationResult:
    """Sum exactly four consecutive compatible discrete fiscal quarters.

    A 53-week fiscal year produces a 53-week TTM only when the component
    quarter lengths make that fact explicit.  Partial-quarter sums are not
    labelled TTM.
    """
    kind = FlowDerivationKind.TTM
    try:
        # Read one item beyond the contract instead of materializing an
        # attacker-controlled (or accidentally infinite) iterable.
        supplied = tuple(islice(iter(quarters), 5))
    except TypeError as exc:
        raise ValueError("quarters must be an iterable of period observations") from exc
    governance_cutoff = _check_governance_cutoff(
        mapping_available_at=mapping_available_at,
        computed_at=computed_at,
        published_at=published_at,
        as_of=as_of,
        clock=clock,
        kind=kind,
    )
    if governance_cutoff:
        return governance_cutoff
    cutoff = _check_cutoff(supplied, as_of=as_of, clock=clock, kind=kind)
    if cutoff:
        return cutoff
    if not supplied:
        return _not_available(kind, "no quarterly inputs supplied")
    if len(supplied) < 4:
        return _not_available(
            kind,
            f"TTM requires exactly four discrete quarters; received {len(supplied)}",
            inputs=supplied,
        )
    if len(supplied) > 4:
        return _not_evaluable(
            kind,
            "TTM requires exactly four discrete quarters; received more than four",
            inputs=supplied,
        )
    compatible, reason = _comparable(supplied)
    if not compatible:
        return _not_evaluable(kind, reason or "inputs incompatible", inputs=supplied)
    if any(not item.period.is_discrete_quarter for item in supplied):
        return _not_evaluable(kind, "TTM accepts only discrete quarter, direct_q4, or derived_q4 inputs", inputs=supplied)
    if any(item.period.is_stub for item in supplied):
        return _not_evaluable(kind, "stub quarters cannot support TTM", inputs=supplied)
    has_derived_quarter = any(item.period.kind is PeriodKind.DERIVED_Q4 for item in supplied)
    has_direct_quarter = any(
        item.period.kind in {PeriodKind.FISCAL_QUARTER, PeriodKind.DIRECT_Q4}
        for item in supplied
    )
    if has_derived_quarter and has_direct_quarter:
        if any(not item.revision_basis for item in supplied):
            return _not_evaluable(
                kind,
                "mixed direct/derived TTM requires an explicit common revision_basis",
                inputs=supplied,
            )
        if len({item.revision_basis for item in supplied}) != 1:
            return _not_evaluable(
                kind,
                "mixed direct/derived TTM requires one common revision_basis",
                inputs=supplied,
            )
    ordered = tuple(sorted(supplied, key=_quarter_sort_key))
    ordinals = [item.period.quarter_ordinal for item in ordered]
    if len(set(ordinals)) != 4 or any(right != left + 1 for left, right in zip(ordinals, ordinals[1:])):
        return _not_evaluable(kind, "TTM quarters must be four consecutive fiscal quarters", inputs=ordered)
    if any(
        earlier.period.end >= later.period.start
        for earlier, later in zip(ordered, ordered[1:])
        if later.period.start is not None
    ):
        return _not_evaluable(kind, "TTM quarters have overlapping economic intervals", inputs=ordered)
    if any(
        later.period.start != earlier.period.end + timedelta(days=1)
        for earlier, later in zip(ordered, ordered[1:])
    ):
        return _not_evaluable(kind, "TTM quarters must be adjacent without calendar gaps", inputs=ordered)
    total_weeks = sum(item.period.inferred_week_count or 0 for item in ordered)
    if total_weeks not in {52, 53}:
        return _not_evaluable(
            kind,
            f"TTM quarter lengths must total 52 or 53 weeks; got {total_weeks}",
            inputs=ordered,
        )
    has_53_week = total_weeks == 53
    if has_53_week and not any(item.period.inferred_week_count == 14 or item.period.is_53_week for item in ordered):
        return _not_evaluable(kind, "53-week TTM requires explicit 14-week or 53-week component metadata", inputs=ordered)
    span_weeks = _approx_weeks(ordered[0].period.start, ordered[-1].period.end)
    if span_weeks != total_weeks:
        return _not_evaluable(
            kind,
            f"TTM calendar span must equal component total ({total_weeks} weeks); got {span_weeks}",
            inputs=ordered,
        )
    try:
        clocks = _combined_clocks(
            ordered,
            mapping_available_at=mapping_available_at,
            computed_at=computed_at,
            published_at=published_at,
        )
    except ValueError as exc:
        return _not_evaluable(kind, str(exc), inputs=ordered)
    output_cutoff = _check_derived_output_cutoff(
        clocks,
        as_of=as_of,
        clock=clock,
        kind=kind,
        inputs=ordered,
    )
    if output_cutoff:
        return output_cutoff
    period = TypedPeriod(
        kind=PeriodKind.TTM,
        start=ordered[0].period.start,
        end=ordered[-1].period.end,
        fiscal_year=ordered[-1].period.fiscal_year,
        calendar_kind=CalendarKind.WEEK_53 if has_53_week else CalendarKind.WEEK_52,
        fiscal_year_weeks=53 if has_53_week else 52,
        week_count=total_weeks,
    )
    try:
        with localcontext(_period_decimal_context()):
            derived_value = sum((item.value for item in ordered), Decimal("0"))
    except (DecimalException, OverflowError):
        return _not_evaluable(
            kind,
            "TTM arithmetic is outside the fixed decimal contract",
            inputs=ordered,
        )
    derived = PeriodObservation(
        entity_id=ordered[0].entity_id,
        metric=ordered[0].metric,
        unit=ordered[0].unit,
        value=derived_value,
        period=period,
        clocks=clocks,
        dimensions=ordered[0].dimensions,
        source_occurrence_ids=tuple(
            sorted({source_id for item in ordered for source_id in item.source_occurrence_ids})
        ),
        lineage_ids=_unique_lineage(ordered, rule_id),
        revision_basis=next((item.revision_basis for item in ordered if item.revision_basis), None),
        derivation_kind=kind,
    )
    return DerivationResult(
        status=AvailabilityStatus.AVAILABLE,
        derivation_kind=kind,
        observation=derived,
        input_observation_ids=tuple(item.observation_id for item in ordered),
    )


def direct_q4_period(
    start: date | str,
    end: date | str,
    *,
    fiscal_year: int,
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN,
    week_count: int | None = None,
) -> TypedPeriod:
    """Named helper so a filed discrete Q4 can never masquerade as derived."""
    return fiscal_quarter_period(
        start,
        end,
        fiscal_year=fiscal_year,
        fiscal_quarter=4,
        direct_q4=True,
        calendar_kind=calendar_kind,
        week_count=week_count,
    )
