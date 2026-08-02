"""Deterministic, bounded bitemporal metric queries over the raw fact ledger.

This module is intentionally a query *kernel*, not an API handler or a storage
adapter.  It composes three immutable contracts:

* :mod:`raw_ledger` owns individual source occurrences and their revision
  history;
* :mod:`metric_registry` is the only authority for concept aliases and
  formulae; and
* :mod:`periods` owns typed period normalization.

The raw ledger has a one-clock selector.  A production query, however, must
apply both a source-event and a system/recorded cutoff at once.  The small
adapter below therefore selects a duplicate group only when the group and its
entire revision ancestry are available on *both* clocks.  It deliberately does
not reinterpret an unavailable mapping, a withdrawn fact, an ambiguous
duplicate, or an issuer extension as a numeric value.

There is no database or HTTP dependency here.  A caller supplies a bounded
``RawFactLedger``, a validated ``MetricRegistry``, entity identities, and (when
needed) an accession metadata adapter that can attest filing forms/dates.
"""
from __future__ import annotations

import ast
import csv
from dataclasses import dataclass, field
from datetime import date, datetime
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
import hashlib
import io
from itertools import islice
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .metric_registry import ConceptAlias, FormulaRule, MappingRule, MetricContract, MetricRegistry
from .periods import CalendarKind, PeriodKind, TypedPeriod
from .raw_ledger import (
    FactEventType,
    MAX_DECIMAL_SOURCE_CHARS,
    MAX_XBRL_ACCURACY_MAGNITUDE,
    RawFactLedger,
    RawFactOccurrence,
    canonical_json,
    decimal_text,
    parse_utc,
    stable_id,
    utc_text,
)


QUERY_SCHEMA = "fundamental_forensics.metric_query/v1"
REGISTRY_PROJECTION_SCHEMA = "fundamental_forensics.registry_projection/v1"
REGISTRY_PROJECTION_VERSION = "cutoff-projection-v1"
FILING_METADATA_SCHEMA = "fundamental_forensics.filing_metadata/v1"

# The first synchronous peer-grid contract is deliberately small.  A caller
# that needs a bulk history/export job must use a durable worker lane rather
# than accidentally turn a request path into an unbounded scan.
HARD_MAX_TICKERS = 50
HARD_MAX_METRICS = 50
HARD_MAX_PERIODS = 32
HARD_MAX_CELLS = 10_000
HARD_MAX_VISIBLE_SOURCE_EVENTS_PER_CELL = 10_000
HARD_MAX_PROVENANCE_IDS = 10_000
HARD_MAX_DEPENDENCY_RECEIPTS = HARD_MAX_METRICS
MAX_QUERY_TEXT_CHARS = 4096

# Formula arithmetic is deliberately owned by this kernel rather than by the
# process-global Decimal context. The contract is IEEE decimal128-shaped:
# 34 significant digits, round-half-even, exponent range -6143..6144, and
# traps for exceptional/non-representable results. Inexact division is a
# normal deterministic rounding operation under this contract; it is not a
# reason to discard a governed formula result.
FORMULA_DECIMAL_PRECISION = 34
FORMULA_DECIMAL_EMIN = -6143
FORMULA_DECIMAL_EMAX = 6144
MAX_DECIMAL_COEFFICIENT_DIGITS = 8192
MAX_DECIMAL_SERIALIZED_CHARS = 8192
SOURCE_COMPARISON_PRECISION = 2 * MAX_DECIMAL_SOURCE_CHARS + 8
SOURCE_COMPARISON_EXPONENT_LIMIT = (
    2 * MAX_DECIMAL_SOURCE_CHARS + 2 * MAX_XBRL_ACCURACY_MAGNITUDE + 8
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class QueryError(ValueError):
    """Base class for safe, client-actionable query errors."""


class QueryValidationError(QueryError):
    """The query shape or a supplied selector is malformed."""


class QueryBoundsError(QueryValidationError):
    """The request exceeds its explicitly declared synchronous bounds."""


class UnsupportedMetricError(QueryValidationError):
    """The metric is not in the immutable governed registry."""


class UnsupportedConceptError(QueryValidationError):
    """The concept is not a governed registry concept for this engine."""


class BitemporalPolicy(str, Enum):
    """The three externally meaningful raw-vintage policies.

    ``AS_REPORTED`` means the original source group, never a later amended
    value. ``LATEST_KNOWN_AS_OF`` selects the newest eligible source vintage
    of any immutable event type. ``LATEST_RESTATED`` is intentionally *not*
    an alias: it selects only an eligible, explicitly typed reported revision
    (amendment, comparative recast, restatement, source correction, or
    withdrawal). If no such vintage is known at both cutoffs, it is missing
    rather than silently returning the latest ordinary filing or a
    parser/mapping correction.

    Formula outputs are calculated on demand from the selected raw vintages;
    a formula query never pretends to be a separately materialized historical
    occurrence.
    """

    AS_REPORTED = "as_reported"
    LATEST_KNOWN_AS_OF = "latest_known_as_of"
    LATEST_RESTATED = "latest_restated"


# A descriptive compatibility spelling for callers that prefer the longer
# noun.  It remains an Enum, while QueryPolicy below carries the two cutoffs.
MetricQueryPolicy = BitemporalPolicy


class CellState(str, Enum):
    """A cell has a value, lacks evidence, or is unsafe to evaluate."""

    VALUE = "value"
    MISSING = "missing"
    NOT_EVALUABLE = "not_evaluable"


MetricCellState = CellState


class ProvenanceKind(str, Enum):
    """Whether a receipt describes absence, a raw fact, or an on-demand formula."""

    OPAQUE = "opaque"
    DIRECT = "direct"
    FORMULA = "formula"


class EvaluationPolicy(str, Enum):
    """How a normalized answer was produced from cutoff-visible artifacts."""

    ON_DEMAND_CUTOFF_PROJECTION = "on_demand_cutoff_projection"


_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")


def _require_text(value: Any, *, field_name: str) -> str:
    if isinstance(value, float):
        raise QueryValidationError(f"{field_name} cannot be a binary float")
    text = str(value or "").strip()
    if not text:
        raise QueryValidationError(f"{field_name} is required")
    if len(text) > MAX_QUERY_TEXT_CHARS:
        raise QueryValidationError(f"{field_name} exceeds the text safety limit")
    return text


def _required_utc(value: datetime | str | None, *, field_name: str) -> datetime:
    try:
        parsed = parse_utc(value, field_name=field_name)
    except ValueError as exc:
        raise QueryValidationError(str(exc)) from exc
    if parsed is None:
        raise QueryValidationError(f"{field_name} is required")
    return parsed


def _date_value(value: date | datetime | str | None, *, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise QueryValidationError(f"invalid {field_name}: {value!r}") from exc


def _date_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _positive_int(value: int, *, field_name: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise QueryBoundsError(f"{field_name} must be a positive integer")
    if value > ceiling:
        raise QueryBoundsError(f"{field_name} exceeds hard safety ceiling {ceiling}")
    return value


def _formula_context() -> Context:
    """Return a fresh, fixed Decimal context for every formula evaluation.

    Returning a new context prevents an importer from mutating a module-level
    ``Context`` object and thereby changing a query hash or a cell result.
    """
    context = Context(
        prec=FORMULA_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=FORMULA_DECIMAL_EMIN,
        Emax=FORMULA_DECIMAL_EMAX,
        capitals=1,
        clamp=0,
    )
    for signal in (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal):
        context.traps[signal] = True
    return context


def _source_comparison_context() -> Context:
    """Exact bounded context for raw XBRL duplicate interval comparison.

    Formula decimal128 rounding is intentionally unsuitable here: source
    coefficients can exceed 34 digits and XBRL accuracy exponents extend to
    10,000.  The raw-ledger token and accuracy ceilings provide a separate,
    finite context large enough to preserve those values exactly.
    """
    context = Context(
        prec=SOURCE_COMPARISON_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=-SOURCE_COMPARISON_EXPONENT_LIMIT,
        Emax=SOURCE_COMPARISON_EXPONENT_LIMIT,
        capitals=1,
        clamp=0,
    )
    for signal in (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal):
        context.traps[signal] = True
    return context


def _bounded_decimal(value: Decimal | str | int, *, field_name: str) -> Decimal:
    """Normalize a finite Decimal without permitting unbounded wire values."""
    if isinstance(value, float):
        raise QueryValidationError(f"{field_name} cannot be a binary float")
    if isinstance(value, str) and len(value) > MAX_DECIMAL_SERIALIZED_CHARS:
        raise QueryValidationError(f"{field_name} exceeds the decimal text safety limit")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, TypeError, ValueError) as exc:
        raise QueryValidationError(f"invalid {field_name}: {value!r}") from exc
    if not parsed.is_finite():
        raise QueryValidationError(f"{field_name} must be finite")
    digits = parsed.as_tuple().digits
    if len(digits) > MAX_DECIMAL_COEFFICIENT_DIGITS:
        raise QueryValidationError(f"{field_name} exceeds the decimal coefficient safety limit")
    if parsed != 0 and not FORMULA_DECIMAL_EMIN <= parsed.adjusted() <= FORMULA_DECIMAL_EMAX:
        raise QueryValidationError(f"{field_name} exponent is outside the query decimal contract")
    # This formatting is bounded by the checks above and protects the stable
    # cell ID/export path from an attacker-controlled million-character zero
    # expansion such as Decimal('1e-1000000').
    serialized = decimal_text(parsed)
    if serialized is None or len(serialized) > MAX_DECIMAL_SERIALIZED_CHARS:
        raise QueryValidationError(f"{field_name} exceeds the decimal serialization safety limit")
    return parsed


def _optional_text(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueryValidationError(f"{field_name} must be text when supplied")
    return _require_text(value, field_name=field_name)


def _optional_utc(value: Any, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, (datetime, str)):
        raise QueryValidationError(f"{field_name} must be an aware datetime or UTC text")
    try:
        return parse_utc(value, field_name=field_name)
    except ValueError as exc:
        raise QueryValidationError(str(exc)) from exc


def _bounded_collection(
    value: Any,
    *,
    field_name: str,
    maximum: int,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        raise QueryValidationError(f"{field_name} must be a bounded collection")
    try:
        count = len(value)
    except (TypeError, AttributeError):
        count = None
    except QueryError:
        raise
    except Exception as exc:
        raise QueryValidationError(f"{field_name} has an invalid length contract") from exc
    if count is not None and count > maximum:
        raise QueryBoundsError(f"{field_name} exceeds the item safety limit {maximum}")
    try:
        items = tuple(islice(iter(value), maximum + 1))
    except Exception as exc:
        raise QueryValidationError(f"{field_name} must be a bounded collection") from exc
    if len(items) > maximum:
        raise QueryBoundsError(f"{field_name} exceeds the item safety limit {maximum}")
    return items


def _canonical_text_tuple(
    value: Any,
    *,
    field_name: str,
    maximum: int = HARD_MAX_PROVENANCE_IDS,
) -> tuple[str, ...]:
    items = _bounded_collection(value, field_name=field_name, maximum=maximum)
    return tuple(sorted({_require_text(item, field_name=field_name) for item in items}))


def _optional_digest(value: Any, *, field_name: str) -> str | None:
    text = _optional_text(value, field_name=field_name)
    if text is not None and not _SHA256_RE.fullmatch(text):
        raise QueryValidationError(f"{field_name} must be lowercase 64-hex")
    return text


def _csv_safe(value: Any) -> str:
    """Prevent spreadsheet formula interpretation of textual export fields."""
    text = str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@dataclass(frozen=True)
class QueryPolicy:
    """Both cutoffs are mandatory; a missing cutoff is never silently "now".

    The source cutoff gates ``accepted_at`` for every selected source group and
    its revision lineage.  The recorded cutoff gates every retained source
    artifact clock plus the filing-metadata and governance definitions used by
    the answer.  Normalized cells are evaluated on demand from that cutoff
    projection: absent raw mapping/compute/publish clocks therefore mean the
    source was not materialized through those lanes, not that this query
    invented historical materialization timestamps.
    """

    source_snapshot_at: datetime | str | None
    recorded_at: datetime | str | None
    selection: BitemporalPolicy | str = BitemporalPolicy.LATEST_KNOWN_AS_OF

    def __post_init__(self) -> None:
        source_snapshot_at = _required_utc(
            self.source_snapshot_at, field_name="source_snapshot_at"
        )
        recorded_at = _required_utc(self.recorded_at, field_name="recorded_at")
        try:
            selection = (
                self.selection
                if isinstance(self.selection, BitemporalPolicy)
                else BitemporalPolicy(str(self.selection).strip().lower().replace("-", "_"))
            )
        except ValueError as exc:
            allowed = ", ".join(item.value for item in BitemporalPolicy)
            raise QueryValidationError(f"selection must be one of {allowed}") from exc
        object.__setattr__(self, "source_snapshot_at", source_snapshot_at)
        object.__setattr__(self, "recorded_at", recorded_at)
        object.__setattr__(self, "selection", selection)

    def to_dict(self) -> dict[str, str]:
        return {
            "selection": self.selection.value,
            "source_snapshot_at": utc_text(self.source_snapshot_at) or "",
            "recorded_at": utc_text(self.recorded_at) or "",
        }


# The public names make it easy for adapters written during the source-lane
# build to converge without retaining ambiguous "as_of" terminology.
BitemporalQueryPolicy = QueryPolicy
QueryCutoffs = QueryPolicy


@dataclass(frozen=True)
class QueryBounds:
    """Hard request limits for deterministic in-process query work."""

    max_tickers: int = HARD_MAX_TICKERS
    max_metrics: int = HARD_MAX_METRICS
    max_periods: int = HARD_MAX_PERIODS
    max_cells: int = HARD_MAX_CELLS
    max_visible_source_events_per_cell: int = HARD_MAX_VISIBLE_SOURCE_EVENTS_PER_CELL

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_tickers",
            _positive_int(self.max_tickers, field_name="max_tickers", ceiling=HARD_MAX_TICKERS),
        )
        object.__setattr__(
            self,
            "max_metrics",
            _positive_int(self.max_metrics, field_name="max_metrics", ceiling=HARD_MAX_METRICS),
        )
        object.__setattr__(
            self,
            "max_periods",
            _positive_int(self.max_periods, field_name="max_periods", ceiling=HARD_MAX_PERIODS),
        )
        object.__setattr__(
            self,
            "max_cells",
            _positive_int(self.max_cells, field_name="max_cells", ceiling=HARD_MAX_CELLS),
        )
        object.__setattr__(
            self,
            "max_visible_source_events_per_cell",
            _positive_int(
                self.max_visible_source_events_per_cell,
                field_name="max_visible_source_events_per_cell",
                ceiling=HARD_MAX_VISIBLE_SOURCE_EVENTS_PER_CELL,
            ),
        )


@dataclass(frozen=True)
class QueryEntity:
    """A display ticker bound to the immutable ledger entity identity."""

    ticker: str
    entity_id: str

    def __post_init__(self) -> None:
        ticker = _require_text(self.ticker, field_name="ticker").upper()
        if not _TICKER_RE.fullmatch(ticker):
            raise QueryValidationError(f"invalid ticker: {self.ticker!r}")
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "entity_id", _require_text(self.entity_id, field_name="entity_id"))

    def to_dict(self) -> dict[str, str]:
        return {"ticker": self.ticker, "entity_id": self.entity_id}


@dataclass(frozen=True)
class PeriodRequest:
    """A query-period selector normalized by :class:`TypedPeriod`.

    Raw facts do not carry an inferred fiscal label.  Callers therefore provide
    the requested fiscal metadata explicitly when it matters; the exact source
    interval must still match.  This prevents a 90-day fact from silently
    becoming a fiscal quarter or annual result merely because its length looks
    plausible.
    """

    kind: PeriodKind | str
    end: date | str
    start: date | str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    calendar_kind: CalendarKind | str = CalendarKind.UNKNOWN
    fiscal_year_weeks: int | None = None
    week_count: int | None = None
    label: str | None = None
    normalized: TypedPeriod = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            normalized = TypedPeriod(
                kind=self.kind,
                end=self.end,
                start=self.start,
                fiscal_year=self.fiscal_year,
                fiscal_quarter=self.fiscal_quarter,
                calendar_kind=self.calendar_kind,
                fiscal_year_weeks=self.fiscal_year_weeks,
                week_count=self.week_count,
            )
        except (TypeError, ValueError) as exc:
            raise QueryValidationError(str(exc)) from exc
        label = _require_text(self.label, field_name="period label") if self.label else None
        object.__setattr__(self, "kind", normalized.kind)
        object.__setattr__(self, "end", normalized.end)
        object.__setattr__(self, "start", normalized.start)
        object.__setattr__(self, "fiscal_year", normalized.fiscal_year)
        object.__setattr__(self, "fiscal_quarter", normalized.fiscal_quarter)
        object.__setattr__(self, "calendar_kind", normalized.calendar_kind)
        object.__setattr__(self, "fiscal_year_weeks", normalized.fiscal_year_weeks)
        object.__setattr__(self, "week_count", normalized.week_count)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "normalized", normalized)

    @classmethod
    def instant(cls, end: date | str, **kwargs: Any) -> "PeriodRequest":
        return cls(kind=PeriodKind.INSTANT, end=end, **kwargs)

    @classmethod
    def duration(cls, start: date | str, end: date | str, **kwargs: Any) -> "PeriodRequest":
        return cls(kind=PeriodKind.DURATION, start=start, end=end, **kwargs)

    @classmethod
    def from_typed(cls, period: TypedPeriod, *, label: str | None = None) -> "PeriodRequest":
        if not isinstance(period, TypedPeriod):
            raise QueryValidationError("period must be a TypedPeriod")
        return cls(
            kind=period.kind,
            start=period.start,
            end=period.end,
            fiscal_year=period.fiscal_year,
            fiscal_quarter=period.fiscal_quarter,
            calendar_kind=period.calendar_kind,
            fiscal_year_weeks=period.fiscal_year_weeks,
            week_count=period.week_count,
            label=label,
        )

    @property
    def key(self) -> tuple[Any, ...]:
        period = self.normalized
        return (
            period.kind.value,
            period.start.isoformat() if period.start else "",
            period.end.isoformat(),
            period.fiscal_year or 0,
            period.fiscal_quarter or 0,
            period.calendar_kind.value,
            period.fiscal_year_weeks or 0,
            period.week_count or 0,
            self.label or "",
        )

    def to_dict(self) -> dict[str, Any]:
        value = self.normalized.to_dict()
        value["label"] = self.label
        return value


# More explicit spellings used by API/adapter code are aliases, not separate
# classes with subtly divergent normalization rules.
MetricPeriod = PeriodRequest
PeriodSelector = PeriodRequest


@dataclass(frozen=True)
class FilingMetadata:
    """Immutable, source-bound filing metadata with an explicit system clock."""

    accession: str
    document_id: str
    source_body_sha256: str
    available_at: datetime | str
    form: str | None = None
    filed_at: date | datetime | str | None = None
    content_sha256: str | None = None
    schema: str = FILING_METADATA_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != FILING_METADATA_SCHEMA:
            raise QueryValidationError(f"unsupported filing metadata schema: {self.schema}")
        accession = _require_text(self.accession, field_name="filing_metadata.accession")
        document_id = _require_text(self.document_id, field_name="filing_metadata.document_id")
        source_body_sha256 = _optional_digest(
            self.source_body_sha256,
            field_name="filing_metadata.source_body_sha256",
        )
        if source_body_sha256 is None:  # pragma: no cover - required field guard.
            raise QueryValidationError("filing_metadata.source_body_sha256 is required")
        available_at = _required_utc(
            self.available_at,
            field_name="filing_metadata.available_at",
        )
        form = _require_text(self.form, field_name="form").upper() if self.form else None
        filed_at = _date_value(self.filed_at, field_name="filed_at")
        payload = {
            "schema": self.schema,
            "accession": accession,
            "document_id": document_id,
            "source_body_sha256": source_body_sha256,
            "available_at": utc_text(available_at),
            "form": form,
            "filed_at": _date_text(filed_at),
        }
        expected_digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        supplied_digest = _optional_digest(
            self.content_sha256,
            field_name="filing_metadata.content_sha256",
        )
        if supplied_digest is not None and supplied_digest != expected_digest:
            raise QueryValidationError(
                "filing_metadata.content_sha256 does not match canonical metadata content"
            )
        object.__setattr__(self, "accession", accession)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "source_body_sha256", source_body_sha256)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "form", form)
        object.__setattr__(self, "filed_at", filed_at)
        object.__setattr__(self, "content_sha256", expected_digest)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "schema": self.schema,
            "accession": self.accession,
            "document_id": self.document_id,
            "source_body_sha256": self.source_body_sha256,
            "available_at": utc_text(self.available_at),
            "form": self.form,
            "filed_at": _date_text(self.filed_at),
            "content_sha256": self.content_sha256,
        }


class FilingMetadataResolver(Protocol):
    """Legacy shape retained for typing; query engines reject late resolvers."""

    def metadata_for_fact(self, fact: RawFactOccurrence) -> FilingMetadata | Mapping[str, Any] | None:
        """Return filing metadata for one raw occurrence, if authoritatively known."""


@dataclass(frozen=True)
class CellProvenance:
    """The complete receipt needed to reproduce one cell decision."""

    kind: ProvenanceKind | str
    evaluation_policy: EvaluationPolicy | str | None
    policy: BitemporalPolicy
    source_snapshot_at: datetime
    recorded_cutoff_at: datetime
    source: str | None = None
    accession: str | None = None
    document_id: str | None = None
    source_url: str | None = None
    source_body_sha256: str | None = None
    form: str | None = None
    filed_at: date | None = None
    filing_metadata_available_at: datetime | None = None
    filing_metadata_content_sha256: str | None = None
    accepted_at: datetime | None = None
    recorded_at: datetime | None = None
    # Raw artifact's recorded mapping clock, if the fact was already through a
    # materialization lane.  It is not overloaded with the registry's rule
    # availability below.
    mapping_available_at: datetime | None = None
    # Latest catalog/metric/mapping-or-formula availability required to govern
    # this answer; included separately so a replay receipt retains both clocks.
    governance_available_at: datetime | None = None
    computed_at: datetime | None = None
    published_at: datetime | None = None
    source_ready_at: datetime | None = None
    system_ready_at: datetime | None = None
    concept_qname: str | None = None
    taxonomy: str | None = None
    concept: str | None = None
    unit: str | None = None
    metric_rule_id: str | None = None
    metric_rule_version: str | None = None
    metric_rule_digest: str | None = None
    mapping_rule_id: str | None = None
    mapping_rule_version: str | None = None
    mapping_digest: str | None = None
    mapping_rule_ids: tuple[str, ...] = ()
    mapping_rule_versions: tuple[str, ...] = ()
    mapping_digests: tuple[str, ...] = ()
    formula_rule_id: str | None = None
    formula_rule_version: str | None = None
    formula_digest: str | None = None
    catalog_id: str | None = None
    catalog_version: str | None = None
    catalog_digest: str | None = None
    mapping_pack_version: str | None = None
    mapping_pack_digest: str | None = None
    formula_pack_version: str | None = None
    formula_pack_digest: str | None = None
    confidence: str | None = None
    alias_priority: int | None = None
    source_occurrence_ids: tuple[str, ...] = ()
    dependency_cell_ids: tuple[str, ...] = ()
    dependency_cells: tuple["MetricCell", ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        try:
            kind = ProvenanceKind(self.kind)
        except ValueError as exc:
            raise QueryValidationError(f"invalid provenance kind: {self.kind!r}") from exc
        object.__setattr__(self, "kind", kind)
        if self.evaluation_policy is None:
            evaluation_policy = None
        else:
            try:
                evaluation_policy = EvaluationPolicy(self.evaluation_policy)
            except ValueError as exc:
                raise QueryValidationError(
                    f"invalid evaluation policy: {self.evaluation_policy!r}"
                ) from exc
        object.__setattr__(self, "evaluation_policy", evaluation_policy)
        try:
            policy = BitemporalPolicy(self.policy)
        except ValueError as exc:
            raise QueryValidationError(f"invalid provenance policy: {self.policy!r}") from exc
        object.__setattr__(self, "policy", policy)
        object.__setattr__(
            self,
            "source_snapshot_at",
            _required_utc(self.source_snapshot_at, field_name="provenance.source_snapshot_at"),
        )
        object.__setattr__(
            self,
            "recorded_cutoff_at",
            _required_utc(self.recorded_cutoff_at, field_name="provenance.recorded_cutoff_at"),
        )
        for field_name in (
            "accepted_at",
            "recorded_at",
            "mapping_available_at",
            "filing_metadata_available_at",
            "governance_available_at",
            "computed_at",
            "published_at",
            "source_ready_at",
            "system_ready_at",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_utc(getattr(self, field_name), field_name=f"provenance.{field_name}"),
            )
        if self.accepted_at is not None and self.accepted_at > self.source_snapshot_at:
            raise QueryValidationError("provenance.accepted_at exceeds source_snapshot_at")
        if self.source_ready_at is not None and self.source_ready_at > self.source_snapshot_at:
            raise QueryValidationError("provenance.source_ready_at exceeds source_snapshot_at")
        for field_name in (
            "recorded_at",
            "mapping_available_at",
            "filing_metadata_available_at",
            "governance_available_at",
            "computed_at",
            "published_at",
            "system_ready_at",
        ):
            value = getattr(self, field_name)
            if value is not None and value > self.recorded_cutoff_at:
                raise QueryValidationError(
                    f"provenance.{field_name} exceeds recorded_cutoff_at"
                )
        object.__setattr__(
            self,
            "filed_at",
            _date_value(self.filed_at, field_name="provenance.filed_at"),
        )
        for field_name in (
            "source",
            "accession",
            "document_id",
            "source_url",
            "form",
            "concept_qname",
            "taxonomy",
            "concept",
            "unit",
            "metric_rule_id",
            "metric_rule_version",
            "mapping_rule_id",
            "mapping_rule_version",
            "formula_rule_id",
            "formula_rule_version",
            "catalog_id",
            "catalog_version",
            "mapping_pack_version",
            "formula_pack_version",
            "confidence",
            "reason",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name), field_name=f"provenance.{field_name}"),
            )
        if self.form is not None:
            object.__setattr__(self, "form", self.form.upper())
        for field_name in (
            "source_body_sha256",
            "filing_metadata_content_sha256",
            "metric_rule_digest",
            "mapping_digest",
            "formula_digest",
            "catalog_digest",
            "mapping_pack_digest",
            "formula_pack_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_digest(getattr(self, field_name), field_name=f"provenance.{field_name}"),
            )
        metadata_evidence = (
            self.form,
            self.filed_at,
            self.filing_metadata_available_at,
            self.filing_metadata_content_sha256,
        )
        if any(value is not None for value in metadata_evidence):
            required_metadata = {
                "accession": self.accession,
                "document_id": self.document_id,
                "source_body_sha256": self.source_body_sha256,
                "filing_metadata_available_at": self.filing_metadata_available_at,
                "filing_metadata_content_sha256": self.filing_metadata_content_sha256,
            }
            missing_metadata = tuple(
                name for name, value in required_metadata.items() if value is None
            )
            if missing_metadata:
                raise QueryValidationError(
                    "filing metadata provenance is incomplete: "
                    + ", ".join(missing_metadata)
                )
            FilingMetadata(
                accession=self.accession,
                document_id=self.document_id,
                source_body_sha256=self.source_body_sha256,
                available_at=self.filing_metadata_available_at,
                form=self.form,
                filed_at=self.filed_at,
                content_sha256=self.filing_metadata_content_sha256,
            )
            if (
                self.accepted_at is not None
                and self.filing_metadata_available_at < self.accepted_at
            ):
                raise QueryValidationError(
                    "filing metadata provenance cannot precede source acceptance"
                )
            if (
                self.accepted_at is not None
                and self.filed_at is not None
                and self.filed_at > self.accepted_at.date()
            ):
                raise QueryValidationError(
                    "filing metadata provenance filed_at follows source acceptance"
                )
        if self.alias_priority is not None and (
            isinstance(self.alias_priority, bool)
            or not isinstance(self.alias_priority, int)
            or self.alias_priority < 1
        ):
            raise QueryValidationError("provenance.alias_priority must be a positive integer")
        mapping_rule_ids = set(
            _canonical_text_tuple(self.mapping_rule_ids, field_name="provenance.mapping_rule_ids")
        )
        mapping_rule_versions = set(
            _canonical_text_tuple(
                self.mapping_rule_versions, field_name="provenance.mapping_rule_versions"
            )
        )
        mapping_digests = set(
            _canonical_text_tuple(self.mapping_digests, field_name="provenance.mapping_digests")
        )
        if self.mapping_rule_id:
            mapping_rule_ids.add(self.mapping_rule_id)
        if self.mapping_rule_version:
            mapping_rule_versions.add(self.mapping_rule_version)
        if self.mapping_digest:
            mapping_digests.add(self.mapping_digest)
        if any(not _SHA256_RE.fullmatch(item) for item in mapping_digests):
            raise QueryValidationError("provenance.mapping_digests must be lowercase 64-hex")
        object.__setattr__(self, "mapping_rule_ids", tuple(sorted(mapping_rule_ids)))
        object.__setattr__(self, "mapping_rule_versions", tuple(sorted(mapping_rule_versions)))
        object.__setattr__(self, "mapping_digests", tuple(sorted(mapping_digests)))
        object.__setattr__(
            self,
            "source_occurrence_ids",
            _canonical_text_tuple(
                self.source_occurrence_ids, field_name="provenance.source_occurrence_ids"
            ),
        )
        object.__setattr__(
            self,
            "dependency_cell_ids",
            _canonical_text_tuple(
                self.dependency_cell_ids, field_name="provenance.dependency_cell_ids"
            ),
        )

        dependency_cells = _bounded_collection(
            self.dependency_cells,
            field_name="provenance.dependency_cells",
            maximum=HARD_MAX_DEPENDENCY_RECEIPTS,
        )
        if any(not isinstance(item, MetricCell) for item in dependency_cells):
            raise QueryValidationError(
                "provenance.dependency_cells must contain immutable MetricCell receipts"
            )
        dependency_cells = tuple(sorted(dependency_cells, key=lambda item: item.cell_id or ""))
        if len({item.cell_id for item in dependency_cells}) != len(dependency_cells):
            raise QueryValidationError("provenance.dependency_cells cannot contain duplicates")
        for item in dependency_cells:
            dependency_provenance = item.provenance
            if (
                dependency_provenance.policy is not self.policy
                or dependency_provenance.source_snapshot_at != self.source_snapshot_at
                or dependency_provenance.recorded_cutoff_at != self.recorded_cutoff_at
            ):
                raise QueryValidationError(
                    "embedded dependency receipt policy/cutoffs do not match formula provenance"
                )
        derived_dependency_ids = tuple(item.cell_id for item in dependency_cells)
        if self.dependency_cell_ids and self.dependency_cell_ids != derived_dependency_ids:
            raise QueryValidationError(
                "provenance.dependency_cell_ids do not match embedded dependency receipts"
            )
        object.__setattr__(self, "dependency_cells", dependency_cells)
        object.__setattr__(self, "dependency_cell_ids", derived_dependency_ids)

        self._validate_clock_order()
        self._validate_kind_completeness()

    def _validate_clock_order(self) -> None:
        if self.accepted_at is not None and self.recorded_at is not None:
            if self.accepted_at > self.recorded_at:
                raise QueryValidationError("provenance.accepted_at cannot follow recorded_at")
        if self.source_ready_at is not None and self.accepted_at is not None:
            if self.source_ready_at < self.accepted_at:
                raise QueryValidationError("provenance.source_ready_at cannot precede accepted_at")
        if self.computed_at is not None:
            prerequisites = tuple(
                value for value in (self.recorded_at, self.mapping_available_at) if value is not None
            )
            if prerequisites and self.computed_at < max(prerequisites):
                raise QueryValidationError("provenance.computed_at precedes its prerequisites")
        if self.published_at is not None:
            prerequisites = tuple(
                value
                for value in (self.recorded_at, self.mapping_available_at, self.computed_at)
                if value is not None
            )
            if prerequisites and self.published_at < max(prerequisites):
                raise QueryValidationError("provenance.published_at precedes its prerequisites")
        if self.system_ready_at is not None:
            prerequisites = tuple(
                value
                for value in (
                    self.recorded_at,
                    self.mapping_available_at,
                    self.filing_metadata_available_at,
                    self.governance_available_at,
                    self.computed_at,
                    self.published_at,
                )
                if value is not None
            )
            if prerequisites and self.system_ready_at < max(prerequisites):
                raise QueryValidationError("provenance.system_ready_at precedes its prerequisites")

    def _validate_kind_completeness(self) -> None:
        if self.kind is ProvenanceKind.OPAQUE:
            if self.reason is None:
                raise QueryValidationError("opaque provenance requires a generic reason")
            excluded = (
                self.source,
                self.evaluation_policy,
                self.accession,
                self.document_id,
                self.source_url,
                self.source_body_sha256,
                self.form,
                self.filed_at,
                self.filing_metadata_available_at,
                self.filing_metadata_content_sha256,
                self.accepted_at,
                self.recorded_at,
                self.mapping_available_at,
                self.governance_available_at,
                self.computed_at,
                self.published_at,
                self.source_ready_at,
                self.system_ready_at,
                self.concept_qname,
                self.taxonomy,
                self.concept,
                self.unit,
                self.metric_rule_id,
                self.metric_rule_version,
                self.metric_rule_digest,
                self.mapping_rule_id,
                self.mapping_rule_version,
                self.mapping_digest,
                self.mapping_rule_ids,
                self.mapping_rule_versions,
                self.mapping_digests,
                self.formula_rule_id,
                self.formula_rule_version,
                self.formula_digest,
                self.catalog_id,
                self.catalog_version,
                self.catalog_digest,
                self.mapping_pack_version,
                self.mapping_pack_digest,
                self.formula_pack_version,
                self.formula_pack_digest,
                self.confidence,
                self.alias_priority,
                self.source_occurrence_ids,
                self.dependency_cells,
            )
            if any(value not in (None, (), []) for value in excluded):
                raise QueryValidationError("opaque provenance cannot expose receipt details")
            return

        required = {
            "evaluation_policy": self.evaluation_policy,
            "metric_rule_id": self.metric_rule_id,
            "metric_rule_version": self.metric_rule_version,
            "metric_rule_digest": self.metric_rule_digest,
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "catalog_digest": self.catalog_digest,
            "confidence": self.confidence,
            "governance_available_at": self.governance_available_at,
        }
        if self.kind is ProvenanceKind.DIRECT:
            required.update(
                {
                    "mapping_pack_version": self.mapping_pack_version,
                    "mapping_pack_digest": self.mapping_pack_digest,
                    "mapping_rule_ids": self.mapping_rule_ids,
                    "mapping_rule_versions": self.mapping_rule_versions,
                    "mapping_digests": self.mapping_digests,
                }
            )
        else:
            required.update(
                {
                    "formula_pack_version": self.formula_pack_version,
                    "formula_pack_digest": self.formula_pack_digest,
                }
            )
        missing = tuple(
            name for name, value in required.items() if value is None or value == ()
        )
        if missing:
            raise QueryValidationError(
                f"{self.kind.value} provenance is incomplete: {', '.join(missing)}"
            )
        if self.evaluation_policy is not EvaluationPolicy.ON_DEMAND_CUTOFF_PROJECTION:
            raise QueryValidationError(
                "normalized provenance must explicitly use on-demand cutoff projection"
            )
        if self.kind is ProvenanceKind.DIRECT:
            if any(
                value not in (None, (), [])
                for value in (
                    self.formula_rule_id,
                    self.formula_rule_version,
                    self.formula_digest,
                    self.dependency_cells,
                )
            ):
                raise QueryValidationError("direct provenance cannot contain formula receipts")
            return
        if self.formula_rule_id is None or self.formula_rule_version is None:
            raise QueryValidationError("formula provenance requires its immutable formula rule")
        if self.formula_digest is None:
            raise QueryValidationError("formula provenance requires its formula digest")
        if self.computed_at is not None or self.published_at is not None:
            raise QueryValidationError(
                "on-demand formula provenance cannot claim computed_at or published_at"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "evaluation_policy": (
                self.evaluation_policy.value if self.evaluation_policy is not None else None
            ),
            "policy": self.policy.value,
            "source_snapshot_at": utc_text(self.source_snapshot_at),
            "recorded_cutoff_at": utc_text(self.recorded_cutoff_at),
            "source": self.source,
            "accession": self.accession,
            "document_id": self.document_id,
            "source_url": self.source_url,
            "source_body_sha256": self.source_body_sha256,
            "form": self.form,
            "filed_at": _date_text(self.filed_at),
            "filing_metadata_available_at": utc_text(self.filing_metadata_available_at),
            "filing_metadata_content_sha256": self.filing_metadata_content_sha256,
            "accepted_at": utc_text(self.accepted_at),
            "recorded_at": utc_text(self.recorded_at),
            "mapping_available_at": utc_text(self.mapping_available_at),
            "governance_available_at": utc_text(self.governance_available_at),
            "computed_at": utc_text(self.computed_at),
            "published_at": utc_text(self.published_at),
            "source_ready_at": utc_text(self.source_ready_at),
            "system_ready_at": utc_text(self.system_ready_at),
            "concept_qname": self.concept_qname,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "unit": self.unit,
            "metric_rule_id": self.metric_rule_id,
            "metric_rule_version": self.metric_rule_version,
            "metric_rule_digest": self.metric_rule_digest,
            "mapping_rule_id": self.mapping_rule_id,
            "mapping_rule_version": self.mapping_rule_version,
            "mapping_digest": self.mapping_digest,
            "mapping_rule_ids": list(self.mapping_rule_ids),
            "mapping_rule_versions": list(self.mapping_rule_versions),
            "mapping_digests": list(self.mapping_digests),
            "formula_rule_id": self.formula_rule_id,
            "formula_rule_version": self.formula_rule_version,
            "formula_digest": self.formula_digest,
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "catalog_digest": self.catalog_digest,
            "mapping_pack_version": self.mapping_pack_version,
            "mapping_pack_digest": self.mapping_pack_digest,
            "formula_pack_version": self.formula_pack_version,
            "formula_pack_digest": self.formula_pack_digest,
            "confidence": self.confidence,
            "alias_priority": self.alias_priority,
            "source_occurrence_ids": list(self.source_occurrence_ids),
            "dependency_cell_ids": list(self.dependency_cell_ids),
            "dependency_receipts": [item.to_dict() for item in self.dependency_cells],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MetricCell:
    """One normalized result or an explicit no-result state."""

    ticker: str
    entity_id: str
    metric_id: str
    period: PeriodRequest
    state: CellState | str
    value: Decimal | str | int | None
    unit: str | None
    provenance: CellProvenance
    reason: str | None = None
    cell_id: str | None = None

    def __post_init__(self) -> None:
        ticker = _require_text(self.ticker, field_name="ticker").upper()
        if not _TICKER_RE.fullmatch(ticker):
            raise QueryValidationError(f"invalid ticker: {self.ticker!r}")
        state = CellState(self.state)
        if not isinstance(self.period, PeriodRequest):
            raise TypeError("period must be a PeriodRequest")
        if not isinstance(self.provenance, CellProvenance):
            raise TypeError("provenance must be CellProvenance")
        parsed_value: Decimal | None
        if state is CellState.VALUE:
            if self.value is None:
                raise QueryValidationError("value cells require a Decimal value")
            try:
                parsed_value = _bounded_decimal(self.value, field_name="cell value")
            except QueryValidationError as exc:
                raise QueryValidationError(str(exc)) from exc
            if not self.unit:
                raise QueryValidationError("value cells require a unit")
        else:
            if self.value is not None:
                raise QueryValidationError("missing/not_evaluable cells cannot contain a value")
            parsed_value = None
        metric_id = _require_text(self.metric_id, field_name="metric_id")
        entity_id = _require_text(self.entity_id, field_name="entity_id")
        unit = _require_text(self.unit, field_name="unit") if self.unit else None
        reason = _require_text(self.reason, field_name="reason") if self.reason else None
        if state is CellState.VALUE and reason is not None:
            raise QueryValidationError("value cells cannot carry a reason")
        if state is not CellState.VALUE and reason is None:
            raise QueryValidationError("missing/not_evaluable cells require a reason")
        payload = {
            "ticker": ticker,
            "entity_id": entity_id,
            "metric_id": metric_id,
            "period": self.period.to_dict(),
            "state": state.value,
            "value": decimal_text(parsed_value),
            "unit": unit,
            "provenance": self.provenance.to_dict(),
            "reason": reason,
        }
        expected_cell_id = stable_id("metric_cell", payload)
        if self.cell_id is not None:
            supplied_cell_id = _require_text(self.cell_id, field_name="cell_id")
            if supplied_cell_id != expected_cell_id:
                raise QueryValidationError("cell_id does not match the canonical cell payload")
        if reason != self.provenance.reason:
            raise QueryValidationError("cell reason must exactly match provenance.reason")
        if self.provenance.kind is ProvenanceKind.FORMULA:
            dependencies = self.provenance.dependency_cells
            if any(
                item.ticker != ticker or item.entity_id != entity_id
                for item in dependencies
            ):
                raise QueryValidationError(
                    "formula dependency receipts must match the formula cell entity"
                )
            dependency_metric_ids = tuple(item.metric_id for item in dependencies)
            if len(set(dependency_metric_ids)) != len(dependency_metric_ids):
                raise QueryValidationError(
                    "formula dependency receipts must have unique metric_ids"
                )
        if state is CellState.VALUE:
            if self.provenance.kind is ProvenanceKind.OPAQUE:
                raise QueryValidationError("value cells cannot carry opaque provenance")
            if unit != self.provenance.unit:
                raise QueryValidationError("value cell unit must match provenance.unit")
            if self.provenance.kind is ProvenanceKind.DIRECT:
                required = {
                    "source": self.provenance.source,
                    "accession": self.provenance.accession,
                    "document_id": self.provenance.document_id,
                    "source_body_sha256": self.provenance.source_body_sha256,
                    "form": self.provenance.form,
                    "filing_metadata_available_at": self.provenance.filing_metadata_available_at,
                    "filing_metadata_content_sha256": self.provenance.filing_metadata_content_sha256,
                    "accepted_at": self.provenance.accepted_at,
                    "recorded_at": self.provenance.recorded_at,
                    "source_ready_at": self.provenance.source_ready_at,
                    "system_ready_at": self.provenance.system_ready_at,
                    "concept_qname": self.provenance.concept_qname,
                    "taxonomy": self.provenance.taxonomy,
                    "concept": self.provenance.concept,
                    "mapping_rule_id": self.provenance.mapping_rule_id,
                    "mapping_rule_version": self.provenance.mapping_rule_version,
                    "mapping_digest": self.provenance.mapping_digest,
                    "source_occurrence_ids": self.provenance.source_occurrence_ids,
                }
            else:
                if any(
                    item.state is not CellState.VALUE
                    for item in self.provenance.dependency_cells
                ):
                    raise QueryValidationError(
                        "value formula cells require value dependency receipts"
                    )
                required = {
                    "source": self.provenance.source,
                    "accession": self.provenance.accession,
                    "document_id": self.provenance.document_id,
                    "source_body_sha256": self.provenance.source_body_sha256,
                    "source_ready_at": self.provenance.source_ready_at,
                    "system_ready_at": self.provenance.system_ready_at,
                    "formula_rule_id": self.provenance.formula_rule_id,
                    "formula_rule_version": self.provenance.formula_rule_version,
                    "formula_digest": self.provenance.formula_digest,
                    "dependency_receipts": self.provenance.dependency_cells,
                }
            missing_receipts = tuple(name for name, value in required.items() if not value)
            if missing_receipts:
                raise QueryValidationError(
                    "value cell provenance is incomplete: " + ", ".join(missing_receipts)
                )
        elif self.provenance.kind is ProvenanceKind.OPAQUE and unit is not None:
            raise QueryValidationError("opaque cells cannot expose a governed unit")
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "metric_id", metric_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "value", parsed_value)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "cell_id", expected_cell_id)

    @property
    def status(self) -> CellState:
        """Compatibility-friendly status spelling for table renderers."""
        return self.state

    @property
    def is_value(self) -> bool:
        return self.state is CellState.VALUE

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "ticker": self.ticker,
            "entity_id": self.entity_id,
            "metric_id": self.metric_id,
            "period": self.period.to_dict(),
            "state": self.state.value,
            "status": self.state.value,
            "value": decimal_text(self.value),
            "unit": self.unit,
            "reason": self.reason,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class DeterministicExport:
    """One reproducible wire representation plus its content hash."""

    media_type: str
    payload: bytes
    sha256: str

    def __post_init__(self) -> None:
        media_type = _require_text(self.media_type, field_name="media_type")
        if not isinstance(self.payload, bytes):
            raise TypeError("export payload must be immutable bytes")
        sha256 = _require_text(self.sha256, field_name="sha256")
        expected = hashlib.sha256(self.payload).hexdigest()
        if not _SHA256_RE.fullmatch(sha256) or sha256 != expected:
            raise QueryValidationError("export sha256 does not match its payload")
        object.__setattr__(self, "media_type", media_type)
        object.__setattr__(self, "sha256", sha256)

    @classmethod
    def from_payload(cls, *, media_type: str, payload: bytes) -> "DeterministicExport":
        return cls(
            media_type=_require_text(media_type, field_name="media_type"),
            payload=bytes(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )


def _cell_sort_key(cell: MetricCell) -> tuple[Any, ...]:
    return cell.ticker, cell.metric_id, *cell.period.key, cell.entity_id


_REGISTRY_RECEIPT_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("catalog", ("catalog_id", "catalog_version", "catalog_content_sha256")),
    ("mapping", ("mapping_pack_version", "mapping_pack_content_sha256")),
    ("formula", ("formula_pack_version", "formula_pack_content_sha256")),
)
_REGISTRY_RECEIPT_FIELDS = frozenset(
    field_name for _, fields in _REGISTRY_RECEIPT_GROUPS for field_name in fields
)


def _canonical_registry_receipt(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("registry_receipt must be a mapping")
    raw = dict(value)
    unknown = set(raw) - _REGISTRY_RECEIPT_FIELDS
    if unknown:
        raise QueryValidationError(
            f"registry_receipt contains unsupported field(s): {', '.join(sorted(map(str, unknown)))}"
        )
    normalized: dict[str, str] = {}
    for _, fields in _REGISTRY_RECEIPT_GROUPS:
        present = [field_name in raw for field_name in fields]
        if any(present) and not all(present):
            raise QueryValidationError(
                "registry_receipt groups must be complete or absent at the requested cutoff"
            )
        if not all(present):
            continue
        for field_name in fields:
            if field_name.endswith("sha256"):
                digest = _optional_digest(raw[field_name], field_name=f"registry_receipt.{field_name}")
                if digest is None:  # pragma: no cover - complete-group guard above.
                    raise QueryValidationError(f"registry_receipt.{field_name} is required")
                normalized[field_name] = digest
            else:
                text = _optional_text(raw[field_name], field_name=f"registry_receipt.{field_name}")
                if text is None:  # pragma: no cover - complete-group guard above.
                    raise QueryValidationError(f"registry_receipt.{field_name} is required")
                normalized[field_name] = text
    return dict(sorted(normalized.items()))


@dataclass(frozen=True)
class MetricMatrix:
    """A cross-company/metric/period result with stable JSON and CSV exports."""

    policy: QueryPolicy
    entities: tuple[QueryEntity, ...]
    metric_ids: tuple[str, ...]
    periods: tuple[PeriodRequest, ...]
    cells: tuple[MetricCell, ...]
    registry_receipt: Mapping[str, Any]
    schema: str = QUERY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != QUERY_SCHEMA:
            raise QueryValidationError(f"unsupported matrix schema: {self.schema}")
        if not isinstance(self.policy, QueryPolicy):
            raise TypeError("policy must be QueryPolicy")
        if any(not isinstance(item, QueryEntity) for item in self.entities):
            raise TypeError("matrix entities must be QueryEntity instances")
        if any(not isinstance(item, PeriodRequest) for item in self.periods):
            raise TypeError("matrix periods must be PeriodRequest instances")
        if any(not isinstance(item, MetricCell) for item in self.cells):
            raise TypeError("matrix cells must be MetricCell instances")
        receipt = _canonical_registry_receipt(self.registry_receipt)
        entities = tuple(sorted(self.entities, key=lambda item: (item.ticker, item.entity_id)))
        metrics_raw = tuple(_require_text(item, field_name="metric_id") for item in self.metric_ids)
        metrics = tuple(sorted(metrics_raw))
        periods = tuple(sorted(self.periods, key=lambda item: item.key))
        cells = tuple(sorted(self.cells, key=_cell_sort_key))
        if not entities or not metrics or not periods:
            raise QueryValidationError("matrix requires at least one entity, metric, and period")
        if len({item.ticker for item in entities}) != len(entities):
            raise QueryValidationError("matrix entities must have unique tickers")
        if len({item.entity_id for item in entities}) != len(entities):
            raise QueryValidationError("matrix entities must have unique entity_ids")
        if len(set(metrics_raw)) != len(metrics_raw):
            raise QueryValidationError("matrix metric_ids must be unique")
        if len({item.key for item in periods}) != len(periods):
            raise QueryValidationError("matrix periods must be unique")
        expected = len(entities) * len(metrics) * len(periods)
        if len(cells) != expected:
            raise QueryValidationError(
                f"matrix must contain one cell per entity/metric/period ({expected}); got {len(cells)}"
            )
        entity_by_ticker = {item.ticker: item.entity_id for item in entities}
        expected_keys = {
            (entity.ticker, entity.entity_id, metric_id, period.key)
            for entity in entities
            for metric_id in metrics
            for period in periods
        }
        cell_keys = {(cell.ticker, cell.entity_id, cell.metric_id, cell.period.key) for cell in cells}
        if len(cell_keys) != len(cells):
            raise QueryValidationError("matrix contains duplicate entity/metric/period cells")
        if len({cell.cell_id for cell in cells}) != len(cells):
            raise QueryValidationError("matrix contains duplicate cell_id values")
        if cell_keys != expected_keys:
            raise QueryValidationError("matrix cells do not match the declared entity/metric/period membership")
        for cell in cells:
            if entity_by_ticker.get(cell.ticker) != cell.entity_id:
                raise QueryValidationError("matrix cell ticker/entity identity does not match its entity binding")
            provenance = cell.provenance
            if (
                provenance.policy is not self.policy.selection
                or provenance.source_snapshot_at != self.policy.source_snapshot_at
                or provenance.recorded_cutoff_at != self.policy.recorded_at
            ):
                raise QueryValidationError("matrix cell provenance policy/cutoffs do not match matrix policy")
        pending = list(cells)
        inspected_cell_ids: set[str] = set()
        while pending:
            cell = pending.pop()
            if cell.cell_id in inspected_cell_ids:
                continue
            inspected_cell_ids.add(cell.cell_id)
            provenance = cell.provenance
            if (
                provenance.policy is not self.policy.selection
                or provenance.source_snapshot_at != self.policy.source_snapshot_at
                or provenance.recorded_cutoff_at != self.policy.recorded_at
            ):
                raise QueryValidationError(
                    "embedded cell provenance policy/cutoffs do not match matrix policy"
                )
            if provenance.kind is ProvenanceKind.OPAQUE:
                continue
            expected_catalog = (
                provenance.catalog_id,
                provenance.catalog_version,
                provenance.catalog_digest,
            )
            actual_catalog = (
                receipt.get("catalog_id"),
                receipt.get("catalog_version"),
                receipt.get("catalog_content_sha256"),
            )
            if expected_catalog != actual_catalog:
                raise QueryValidationError(
                    "cell catalog receipt does not match matrix registry receipt"
                )
            for lane, expected, actual in (
                (
                    "mapping",
                    (provenance.mapping_pack_version, provenance.mapping_pack_digest),
                    (
                        receipt.get("mapping_pack_version"),
                        receipt.get("mapping_pack_content_sha256"),
                    ),
                ),
                (
                    "formula",
                    (provenance.formula_pack_version, provenance.formula_pack_digest),
                    (
                        receipt.get("formula_pack_version"),
                        receipt.get("formula_pack_content_sha256"),
                    ),
                ),
            ):
                if any(value is not None for value in expected) and expected != actual:
                    raise QueryValidationError(
                        f"cell {lane} pack receipt does not match matrix registry receipt"
                    )
            pending.extend(provenance.dependency_cells)
        object.__setattr__(self, "entities", entities)
        object.__setattr__(self, "metric_ids", metrics)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "cells", cells)
        # The receipt participates in the query hash.  A frozen dataclass is
        # not enough if this remains a caller-owned mutable dict: mutating it
        # after construction would silently rewrite a matrix's identity.
        object.__setattr__(
            self,
            "registry_receipt",
            MappingProxyType(receipt),
        )

    def _unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy": self.policy.to_dict(),
            "entities": [item.to_dict() for item in self.entities],
            "metric_ids": list(self.metric_ids),
            "periods": [item.to_dict() for item in self.periods],
            "registry": dict(self.registry_receipt),
            "cells": [item.to_dict() for item in self.cells],
        }

    @property
    def query_hash(self) -> str:
        return hashlib.sha256(canonical_json(self._unsigned_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        value = self._unsigned_dict()
        value["query_hash"] = self.query_hash
        return value

    def to_json_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    def to_csv_bytes(self) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        query_hash = self.query_hash
        writer.writerow(
            (
                "query_hash",
                "ticker",
                "entity_id",
                "metric_id",
                "period_kind",
                "period_start",
                "period_end",
                "period_fiscal_year",
                "period_fiscal_quarter",
                "state",
                "value",
                "unit",
                "reason",
                "accession",
                "form",
                "filed_at",
                "accepted_at",
                "recorded_at",
                "mapping_available_at",
                "governance_available_at",
                "source_ready_at",
                "system_ready_at",
                "concept_qname",
                "mapping_rule_id",
                "mapping_rule_version",
                "mapping_digest",
                "mapping_rule_ids",
                "mapping_rule_versions",
                "mapping_digests",
                "formula_rule_id",
                "formula_rule_version",
                "formula_digest",
                "confidence",
                "source_occurrence_ids",
                "dependency_cell_ids",
                "provenance_receipt",
            )
        )
        for cell in self.cells:
            provenance = cell.provenance
            period = cell.period.normalized
            # Excel/Sheets treats several leading characters as a formula.
            # The canonical numeric value is intentionally excluded: a
            # negative Decimal must remain a negative numeric field, not a
            # text value with a leading apostrophe.
            row = (
                query_hash,
                cell.ticker,
                cell.entity_id,
                cell.metric_id,
                period.kind.value,
                period.start.isoformat() if period.start else "",
                period.end.isoformat(),
                period.fiscal_year or "",
                period.fiscal_quarter or "",
                cell.state.value,
                decimal_text(cell.value) or "",
                cell.unit or "",
                cell.reason or "",
                provenance.accession or "",
                provenance.form or "",
                _date_text(provenance.filed_at) or "",
                utc_text(provenance.accepted_at) or "",
                utc_text(provenance.recorded_at) or "",
                utc_text(provenance.mapping_available_at) or "",
                utc_text(provenance.governance_available_at) or "",
                utc_text(provenance.source_ready_at) or "",
                utc_text(provenance.system_ready_at) or "",
                provenance.concept_qname or "",
                provenance.mapping_rule_id or "",
                provenance.mapping_rule_version or "",
                provenance.mapping_digest or "",
                canonical_json(list(provenance.mapping_rule_ids)),
                canonical_json(list(provenance.mapping_rule_versions)),
                canonical_json(list(provenance.mapping_digests)),
                provenance.formula_rule_id or "",
                provenance.formula_rule_version or "",
                provenance.formula_digest or "",
                provenance.confidence or "",
                canonical_json(list(provenance.source_occurrence_ids)),
                canonical_json(list(provenance.dependency_cell_ids)),
                canonical_json(provenance.to_dict()),
            )
            writer.writerow(
                tuple(value if index == 10 else _csv_safe(value) for index, value in enumerate(row))
            )
        return output.getvalue().encode("utf-8")

    def export(self, format: str) -> DeterministicExport:
        normalized = _require_text(format, field_name="export format").lower()
        if normalized == "json":
            return DeterministicExport.from_payload(
                media_type="application/json", payload=self.to_json_bytes()
            )
        if normalized == "csv":
            return DeterministicExport.from_payload(media_type="text/csv", payload=self.to_csv_bytes())
        raise QueryValidationError("export format must be json or csv")

    def export_json(self) -> DeterministicExport:
        return self.export("json")

    def export_csv(self) -> DeterministicExport:
        return self.export("csv")


@dataclass(frozen=True)
class _SourceSelection:
    state: CellState
    occurrence: RawFactOccurrence | None
    source_ready_at: datetime | None
    system_ready_at: datetime | None
    source_occurrence_ids: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True)
class _AliasCandidate:
    mapping: MappingRule
    alias: ConceptAlias


@dataclass(frozen=True)
class _RegistryProjection:
    recorded_at: datetime
    contracts_by_metric: Mapping[str, MetricContract]
    mappings_by_metric: Mapping[str, tuple[MappingRule, ...]]
    formulas_by_metric: Mapping[str, FormulaRule]
    contract_digests: Mapping[str, str]
    mapping_digests: Mapping[tuple[str, str, str], str]
    formula_digests: Mapping[str, str]
    governance_available_by_metric: Mapping[str, datetime]
    catalog_digest: str | None
    mapping_pack_digest: str | None
    formula_pack_digest: str | None
    receipt: Mapping[str, str]


@dataclass(frozen=True)
class _LineageMetadata:
    root_occurrence_id: str
    depth: int
    source_ready_at: datetime | None
    system_ready_at: datetime


def _content_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _immutable_rule_payload(rule: Any) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "version": rule.version,
        "available_at": utc_text(rule.available_at),
        "confidence": rule.confidence,
    }


def _contract_definition_payload(contract: MetricContract) -> dict[str, Any]:
    period = contract.period_constraints
    dimensions = contract.dimensional_profile
    presentation = contract.presentation_constraints
    return {
        "metric_id": contract.metric_id,
        "label": contract.label,
        "category": contract.category,
        "rule": _immutable_rule_payload(contract.rule),
        "units": list(contract.units),
        "period_constraints": {
            "kind": period.kind,
            "allowed_forms": list(period.allowed_forms),
            "min_duration_days": period.min_duration_days,
            "max_duration_days": period.max_duration_days,
        },
        "dimensional_profile": {
            "mode": dimensions.mode,
            "allowed_axes": list(dimensions.allowed_axes),
            "require_dimensions": dimensions.require_dimensions,
            "allow_member_selection": dimensions.allow_member_selection,
        },
        "presentation_constraints": {
            "statement": presentation.statement,
            "sign_convention": presentation.sign_convention,
            "display_scale": presentation.display_scale,
            "comparability": presentation.comparability,
        },
        "review": {
            "required": contract.review.required,
            "triggers": list(contract.review.triggers),
        },
        "no_result": {
            "mode": contract.no_result.mode,
            "codes": list(contract.no_result.codes),
        },
        "declared_formula_dependencies": list(contract.declared_formula_dependencies),
    }


def _mapping_rule_payload(mapping: MappingRule) -> dict[str, Any]:
    aliases = sorted(
        mapping.taxonomy_concept_aliases,
        key=lambda item: (
            item.priority,
            item.taxonomy,
            item.concept,
            item.taxonomy_version_start,
            item.taxonomy_version_end,
        ),
    )
    return {
        "metric_id": mapping.metric_id,
        "rule": _immutable_rule_payload(mapping.rule),
        "taxonomy_concept_aliases": [
            {
                "taxonomy": alias.taxonomy,
                "concept": alias.concept,
                "priority": alias.priority,
                "taxonomy_version_start": alias.taxonomy_version_start,
                "taxonomy_version_end": alias.taxonomy_version_end,
            }
            for alias in aliases
        ],
    }


def _formula_rule_payload(formula: FormulaRule) -> dict[str, Any]:
    return {
        "metric_id": formula.metric_id,
        "rule": _immutable_rule_payload(formula.rule),
        "expression": formula.expression,
        "dependencies": list(formula.dependencies),
        "output_unit": formula.output_unit,
        "dependency_period_alignment": formula.dependency_period_alignment,
    }


_REPORTED_REVISION_EVENT_TYPES = frozenset(
    {
        FactEventType.AMENDMENT,
        FactEventType.COMPARATIVE_RECAST,
        FactEventType.RESTATEMENT,
        FactEventType.SOURCE_CORRECTION,
        FactEventType.WITHDRAWN,
    }
)


def _clock_max(values: Iterable[datetime | None]) -> datetime | None:
    present = tuple(value for value in values if value is not None)
    return max(present) if present else None


def _rounding_tolerance(fact: RawFactOccurrence) -> Decimal:
    """Mirror the ledger's public selection semantics without importing private API."""
    if fact.parsed_value is None:
        return Decimal("0")
    if fact.decimals is not None:
        return (
            Decimal("0")
            if fact.decimals == "INF"
            else Decimal((0, (5,), -int(fact.decimals) - 1))
        )
    if fact.precision is not None:
        value = Decimal(fact.parsed_value)
        if value == 0:
            return Decimal("0")
        scale = value.copy_abs().adjusted() - int(fact.precision) + 1
        return Decimal((0, (5,), scale - 1))
    return Decimal("0")


def _duplicate_interval(item: RawFactOccurrence) -> tuple[Decimal, Decimal]:
    """Return one source fact's exact inclusive XBRL accuracy interval."""
    value = +Decimal(item.parsed_value)
    tolerance = _rounding_tolerance(item)
    return value - tolerance, value + tolerance


def _duplicates_agree(items: Sequence[RawFactOccurrence]) -> bool:
    if len(items) < 2:
        return True
    if len({item.is_nil for item in items}) != 1:
        return False
    if items[0].is_nil:
        return True
    numeric = [item.parsed_value is not None for item in items]
    if any(numeric) and not all(numeric):
        return False
    if not any(numeric):
        return len({item.raw_token for item in items}) == 1
    try:
        with localcontext(_source_comparison_context()):
            greatest_lower: Decimal | None = None
            least_upper: Decimal | None = None
            for item in items:
                lower, upper = _duplicate_interval(item)
                greatest_lower = (
                    lower
                    if greatest_lower is None or lower > greatest_lower
                    else greatest_lower
                )
                least_upper = (
                    upper if least_upper is None or upper < least_upper else least_upper
                )
                if greatest_lower > least_upper:
                    return False
            return True
    except (DecimalException, OverflowError, ValueError):
        # An invalid raw numeric interval cannot prove duplicate equivalence.
        return False


def _duplicate_representative(items: Sequence[RawFactOccurrence]) -> RawFactOccurrence:
    return min(
        items,
        key=lambda item: (
            item.source_span is None,
            item.source_span or (0, 0),
            item.occurrence_id,
        ),
    )


def _qname_parts(value: str) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if text.count(":") != 1:
        return None
    taxonomy, concept = text.split(":", 1)
    return (taxonomy, concept) if taxonomy and concept else None


def _canonical_raw_unit(fact: RawFactOccurrence) -> str | None:
    unit = fact.unit
    if unit is None:
        return None
    numerator = tuple(str(item).strip() for item in unit.measures)
    denominator = tuple(str(item).strip() for item in unit.denominator_measures)
    usd_measures = {"USD", "iso4217:USD"}
    share_measures = {"share", "shares", "xbrli:shares"}
    if len(numerator) == 1 and numerator[0] in usd_measures and not denominator:
        return "USD"
    if len(numerator) == 1 and numerator[0] in share_measures and not denominator:
        return "shares"
    if (
        len(numerator) == 1
        and numerator[0] in usd_measures
        and len(denominator) == 1
        and denominator[0] in share_measures
    ):
        return "USD/shares"
    return None


def _formula_digest(formula: FormulaRule | None) -> str | None:
    if formula is None:
        return None
    return _content_digest(_formula_rule_payload(formula))


def _fact_period_index_key(fact: RawFactOccurrence) -> tuple[str, str, str]:
    context = fact.context
    if context.instant is not None:
        return (PeriodKind.INSTANT.value, "", context.instant.isoformat())
    # RawFactOccurrence validates an exact instant-or-duration context.
    assert context.start is not None and context.end is not None
    return (PeriodKind.DURATION.value, context.start.isoformat(), context.end.isoformat())


def _request_period_index_key(period: PeriodRequest) -> tuple[str, str, str]:
    normalized = period.normalized
    return (
        (
            PeriodKind.INSTANT.value
            if normalized.is_instant
            else PeriodKind.DURATION.value
        ),
        normalized.start.isoformat() if normalized.start else "",
        normalized.end.isoformat(),
    )


class BitemporalMetricQueryEngine:
    """Evaluate a bounded governed metric matrix with complete decision receipts."""

    def __init__(
        self,
        ledger: RawFactLedger | Iterable[RawFactOccurrence],
        registry: MetricRegistry,
        *,
        entities: Mapping[str, str] | Iterable[QueryEntity] = (),
        filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]] | None = None,
        bounds: QueryBounds | None = None,
    ) -> None:
        if isinstance(ledger, RawFactLedger):
            self.ledger = ledger
        else:
            self.ledger = RawFactLedger(tuple(ledger))
        if not isinstance(registry, MetricRegistry):
            raise TypeError("registry must be a MetricRegistry")
        self.registry = registry
        self.bounds = bounds or QueryBounds()
        if not isinstance(self.bounds, QueryBounds):
            raise TypeError("bounds must be QueryBounds")
        self._entities = self._normalize_entities(entities)
        # Immutable indexes make a matrix query proportional to the requested
        # cells and their matching fact groups, not to all ledger events for
        # every alias. Revision traversal uses the event-id parent index rather
        # than rebuilding a ledger-wide id map for each selected group.
        by_entity_qname_period: dict[tuple[str, str, tuple[str, str, str]], list[RawFactOccurrence]] = {}
        by_accession: dict[str, list[RawFactOccurrence]] = {}
        event_by_id: dict[str, RawFactOccurrence] = {}
        parent_by_id: dict[str, str | None] = {}
        lineage_by_id: dict[str, _LineageMetadata] = {}
        for event in self.ledger.events:
            key = (event.source.entity_id, event.concept_qname, _fact_period_index_key(event))
            by_entity_qname_period.setdefault(key, []).append(event)
            by_accession.setdefault(event.source.accession, []).append(event)
            event_by_id[event.occurrence_id] = event
            parent_by_id[event.occurrence_id] = event.revision_of
            parent_lineage = lineage_by_id.get(event.revision_of) if event.revision_of else None
            if parent_lineage is None:
                source_ready_at = event.accepted_at
                root_occurrence_id = event.occurrence_id
                depth = 0
                system_ready_at = event.clocks.system_ready_at
            else:
                source_ready_at = (
                    max(parent_lineage.source_ready_at, event.accepted_at)
                    if parent_lineage.source_ready_at is not None and event.accepted_at is not None
                    else None
                )
                root_occurrence_id = parent_lineage.root_occurrence_id
                depth = parent_lineage.depth + 1
                system_ready_at = max(
                    parent_lineage.system_ready_at,
                    event.clocks.system_ready_at,
                )
            lineage_by_id[event.occurrence_id] = _LineageMetadata(
                root_occurrence_id=root_occurrence_id,
                depth=depth,
                source_ready_at=source_ready_at,
                system_ready_at=system_ready_at,
            )
        self._events_by_entity_qname_period = MappingProxyType(
            {
                key: tuple(sorted(events, key=lambda item: item.occurrence_id))
                for key, events in by_entity_qname_period.items()
            }
        )
        self._event_by_occurrence_id = MappingProxyType(event_by_id)
        self._events_by_accession = MappingProxyType(
            {key: tuple(events) for key, events in by_accession.items()}
        )
        self._parent_by_occurrence_id = MappingProxyType(parent_by_id)
        self._lineage_by_occurrence_id = MappingProxyType(lineage_by_id)
        self._known_entity_ids = frozenset(event.source.entity_id for event in self.ledger.events)
        self._filing_metadata_by_occurrence = self._freeze_filing_metadata(filing_metadata)

    @staticmethod
    def _normalize_entities(
        entities: Mapping[str, str] | Iterable[QueryEntity],
    ) -> dict[str, QueryEntity]:
        if isinstance(entities, Mapping):
            raw = (QueryEntity(ticker=str(ticker), entity_id=str(entity_id)) for ticker, entity_id in entities.items())
        else:
            raw = entities
        out: dict[str, QueryEntity] = {}
        for item in raw:
            entity = item if isinstance(item, QueryEntity) else QueryEntity(**item)  # type: ignore[arg-type]
            if entity.ticker in out and out[entity.ticker] != entity:
                raise QueryValidationError(f"ticker maps to multiple entity_ids: {entity.ticker}")
            out[entity.ticker] = entity
        return out

    def _registry_projection(self, policy: QueryPolicy) -> _RegistryProjection:
        """Project immutable governance definitions at the recorded cutoff.

        Original pack versions and full-pack digests describe the registry
        object's latest contents.  They cannot identify a historical view:
        adding one future rule would otherwise rewrite old query hashes.  This
        projection therefore derives every catalog/pack and per-rule digest
        exclusively from definitions whose own availability clock is visible.
        """
        catalog_visible = self.registry.available_at <= policy.recorded_at
        mapping_pack_visible = (
            catalog_visible
            and self.registry.mapping_pack_available_at <= policy.recorded_at
        )
        formula_pack_visible = (
            catalog_visible
            and self.registry.formula_pack_available_at <= policy.recorded_at
        )
        visible_contracts = tuple(
            sorted(
                (
                    contract
                    for contract in self.registry.contracts
                    if catalog_visible and contract.rule.available_at <= policy.recorded_at
                ),
                key=lambda item: item.metric_id,
            )
        )
        contracts_by_metric = {item.metric_id: item for item in visible_contracts}
        mappings_by_metric: dict[str, tuple[MappingRule, ...]] = {}
        formulas_by_metric: dict[str, FormulaRule] = {}
        contract_digests: dict[str, str] = {}
        mapping_digests: dict[tuple[str, str, str], str] = {}
        formula_digests: dict[str, str] = {}
        governance_available: dict[str, datetime] = {}
        catalog_payloads: list[dict[str, Any]] = []
        mapping_payloads: list[dict[str, Any]] = []
        formula_payloads: list[dict[str, Any]] = []

        for contract in visible_contracts:
            contract_payload = _contract_definition_payload(contract)
            catalog_payloads.append(contract_payload)
            contract_digests[contract.metric_id] = _content_digest(contract_payload)
            visible_mappings = tuple(
                sorted(
                    (
                        mapping
                        for mapping in contract.mappings
                        if mapping_pack_visible
                        and mapping.rule.available_at <= policy.recorded_at
                    ),
                    key=lambda item: (item.rule.rule_id, item.rule.version),
                )
            )
            mappings_by_metric[contract.metric_id] = visible_mappings
            governing_clocks = [self.registry.available_at, contract.rule.available_at]
            for mapping in visible_mappings:
                payload = _mapping_rule_payload(mapping)
                mapping_payloads.append(payload)
                key = (contract.metric_id, mapping.rule.rule_id, mapping.rule.version)
                mapping_digests[key] = _content_digest(payload)
                governing_clocks.extend(
                    (self.registry.mapping_pack_available_at, mapping.rule.available_at)
                )
            formula = contract.formula
            if (
                formula_pack_visible
                and formula is not None
                and formula.rule.available_at <= policy.recorded_at
            ):
                formulas_by_metric[contract.metric_id] = formula
                payload = _formula_rule_payload(formula)
                formula_payloads.append(payload)
                formula_digests[contract.metric_id] = _content_digest(payload)
                governing_clocks.extend(
                    (self.registry.formula_pack_available_at, formula.rule.available_at)
                )
            governance_available[contract.metric_id] = max(governing_clocks)

        catalog_digest = (
            _content_digest(
                {
                    "schema": REGISTRY_PROJECTION_SCHEMA,
                    "lane": "catalog",
                    "catalog_id": self.registry.catalog_id,
                    "contracts": catalog_payloads,
                }
            )
            if catalog_visible
            else None
        )
        mapping_pack_digest = (
            _content_digest(
                {
                    "schema": REGISTRY_PROJECTION_SCHEMA,
                    "lane": "mapping",
                    "mappings": sorted(
                        mapping_payloads,
                        key=lambda item: (
                            item["metric_id"],
                            item["rule"]["rule_id"],
                            item["rule"]["version"],
                        ),
                    ),
                }
            )
            if mapping_pack_visible
            else None
        )
        formula_pack_digest = (
            _content_digest(
                {
                    "schema": REGISTRY_PROJECTION_SCHEMA,
                    "lane": "formula",
                    "formulas": sorted(
                        formula_payloads,
                        key=lambda item: (
                            item["metric_id"],
                            item["rule"]["rule_id"],
                            item["rule"]["version"],
                        ),
                    ),
                }
            )
            if formula_pack_visible
            else None
        )
        receipt_values: dict[str, str] = {}
        if catalog_visible:
            assert catalog_digest is not None
            receipt_values.update(
                {
                "catalog_id": self.registry.catalog_id,
                "catalog_version": REGISTRY_PROJECTION_VERSION,
                "catalog_content_sha256": catalog_digest,
                }
            )
        if mapping_pack_visible:
            assert mapping_pack_digest is not None
            receipt_values.update(
                {
                "mapping_pack_version": REGISTRY_PROJECTION_VERSION,
                "mapping_pack_content_sha256": mapping_pack_digest,
                }
            )
        if formula_pack_visible:
            assert formula_pack_digest is not None
            receipt_values.update(
                {
                "formula_pack_version": REGISTRY_PROJECTION_VERSION,
                "formula_pack_content_sha256": formula_pack_digest,
                }
            )
        receipt = MappingProxyType(receipt_values)
        return _RegistryProjection(
            recorded_at=policy.recorded_at,
            contracts_by_metric=MappingProxyType(contracts_by_metric),
            mappings_by_metric=MappingProxyType(mappings_by_metric),
            formulas_by_metric=MappingProxyType(formulas_by_metric),
            contract_digests=MappingProxyType(contract_digests),
            mapping_digests=MappingProxyType(mapping_digests),
            formula_digests=MappingProxyType(formula_digests),
            governance_available_by_metric=MappingProxyType(governance_available),
            catalog_digest=catalog_digest,
            mapping_pack_digest=mapping_pack_digest,
            formula_pack_digest=formula_pack_digest,
            receipt=receipt,
        )

    @staticmethod
    def _fact_metadata_binding(fact: RawFactOccurrence) -> tuple[str, str, str]:
        return (
            fact.source.accession,
            fact.source.document_id,
            fact.source.body_sha256,
        )

    @staticmethod
    def _coerce_bound_metadata(
        value: FilingMetadata | Mapping[str, Any],
        *,
        binding: tuple[str, str, str],
    ) -> FilingMetadata:
        if isinstance(value, FilingMetadata):
            metadata = value
        elif isinstance(value, Mapping):
            raw = dict(value)
            allowed = {
                "schema",
                "accession",
                "document_id",
                "source_body_sha256",
                "available_at",
                "form",
                "filed_at",
                "content_sha256",
            }
            unknown = set(raw) - allowed
            if unknown:
                raise QueryValidationError(
                    "filing metadata contains unsupported field(s): "
                    + ", ".join(sorted(map(str, unknown)))
                )
            metadata = FilingMetadata(
                schema=raw.get("schema", FILING_METADATA_SCHEMA),
                accession=raw.get("accession", binding[0]),
                document_id=raw.get("document_id", binding[1]),
                source_body_sha256=raw.get("source_body_sha256", binding[2]),
                available_at=raw.get("available_at"),
                form=raw.get("form"),
                filed_at=raw.get("filed_at"),
                content_sha256=raw.get("content_sha256"),
            )
        else:  # pragma: no cover - constructor annotation plus caller guard.
            raise QueryValidationError("filing metadata values must be mappings or FilingMetadata")
        if (metadata.accession, metadata.document_id, metadata.source_body_sha256) != binding:
            raise QueryValidationError(
                "filing metadata binding does not match accession/document/source body"
            )
        return metadata

    def _freeze_filing_metadata(
        self,
        value: Mapping[str, FilingMetadata | Mapping[str, Any]] | None,
    ) -> Mapping[str, FilingMetadata]:
        if value is None:
            return MappingProxyType({})
        if not isinstance(value, Mapping):
            raise QueryValidationError(
                "filing_metadata must be a construction-time mapping; mutable late resolvers are unsupported"
            )
        frozen: dict[str, FilingMetadata] = {}
        for raw_key, raw_metadata in tuple(value.items()):
            key = _require_text(raw_key, field_name="filing_metadata key")
            occurrence = self._event_by_occurrence_id.get(key)
            candidates = (
                (occurrence,)
                if occurrence is not None
                else self._events_by_accession.get(key, ())
            )
            if not candidates:
                raise QueryValidationError(
                    f"filing metadata key does not identify a ledger occurrence/accession: {key}"
                )
            bindings = {self._fact_metadata_binding(fact) for fact in candidates}
            if len(bindings) != 1:
                raise QueryValidationError(
                    "accession-level filing metadata spans multiple document bodies; use occurrence IDs"
                )
            binding = next(iter(bindings))
            metadata = self._coerce_bound_metadata(raw_metadata, binding=binding)
            for fact in candidates:
                if fact.accepted_at is not None and metadata.available_at < fact.accepted_at:
                    raise QueryValidationError(
                        "filing metadata available_at cannot precede source acceptance"
                    )
                if metadata.filed_at is not None and fact.accepted_at is not None:
                    if metadata.filed_at > fact.accepted_at.date():
                        raise QueryValidationError("filing metadata filed_at follows source acceptance")
                existing = frozen.get(fact.occurrence_id)
                if existing is not None and existing != metadata:
                    raise QueryValidationError(
                        f"conflicting filing metadata for occurrence {fact.occurrence_id}"
                    )
                frozen[fact.occurrence_id] = metadata
        return MappingProxyType(frozen)

    def _entity_for(self, ticker: str | QueryEntity) -> QueryEntity:
        if isinstance(ticker, QueryEntity):
            known = self._entities.get(ticker.ticker)
            if known is not None and known != ticker:
                raise QueryValidationError(f"ticker maps to a different entity_id: {ticker.ticker}")
            return ticker
        normalized = _require_text(ticker, field_name="ticker").upper()
        entity = self._entities.get(normalized)
        if entity is None:
            # Entity IDs are valid non-display identifiers in programmatic
            # callers, but only when exact; this is not a ticker lookup guess.
            if normalized in self._known_entity_ids:
                return QueryEntity(ticker=normalized, entity_id=normalized)
            raise QueryValidationError(f"unknown ticker/entity: {normalized}")
        return entity

    @staticmethod
    def _period_for(value: PeriodRequest | TypedPeriod | Mapping[str, Any]) -> PeriodRequest:
        if isinstance(value, PeriodRequest):
            return value
        if isinstance(value, TypedPeriod):
            return PeriodRequest.from_typed(value)
        if isinstance(value, Mapping):
            try:
                return PeriodRequest(**dict(value))
            except (TypeError, ValueError) as exc:
                raise QueryValidationError(f"invalid period selector: {exc}") from exc
        raise QueryValidationError("period must be PeriodRequest, TypedPeriod, or mapping")

    @staticmethod
    def _policy_for(value: QueryPolicy | Mapping[str, Any]) -> QueryPolicy:
        if isinstance(value, QueryPolicy):
            return value
        if isinstance(value, Mapping):
            try:
                return QueryPolicy(**dict(value))
            except (TypeError, ValueError) as exc:
                raise QueryValidationError(f"invalid query policy: {exc}") from exc
        raise QueryValidationError("policy must be QueryPolicy")

    def governed_metric_for_concept(
        self,
        concept_qname: str,
        policy: QueryPolicy | Mapping[str, Any],
    ) -> str:
        """Return the sole cutoff-visible governed metric for a standard concept."""
        parts = _qname_parts(_require_text(concept_qname, field_name="concept_qname"))
        if parts is None:
            raise UnsupportedConceptError("concept_qname must have taxonomy:concept form")
        projection = self._registry_projection(self._policy_for(policy))
        matches = sorted(
            {
                metric_id
                for metric_id, mappings in projection.mappings_by_metric.items()
                for mapping in mappings
                for alias in mapping.taxonomy_concept_aliases
                if (alias.taxonomy, alias.concept) == parts
            }
        )
        if len(matches) != 1:
            raise UnsupportedConceptError(f"unsupported or ambiguous governed concept: {concept_qname}")
        return matches[0]

    # A concise API spelling for source ingestion/adapters.
    query_concept = governed_metric_for_concept

    def query_cell(
        self,
        ticker: str | QueryEntity,
        metric_id: str,
        period: PeriodRequest | TypedPeriod | Mapping[str, Any],
        policy: QueryPolicy | Mapping[str, Any],
    ) -> MetricCell:
        entity = self._entity_for(ticker)
        selector = self._period_for(period)
        query_policy = self._policy_for(policy)
        projection = self._registry_projection(query_policy)
        metric = _require_text(metric_id, field_name="metric_id")
        if metric not in projection.contracts_by_metric:
            raise UnsupportedMetricError(f"unsupported metric: {metric}")
        cache: dict[tuple[Any, ...], MetricCell] = {}
        return self._evaluate(
            entity,
            metric,
            selector,
            query_policy,
            projection,
            cache,
            stack=(),
        )

    # API aliases make the narrow kernel pleasant to use without broadening its
    # semantics or exporting a second result shape.
    cell = query_cell
    evaluate_cell = query_cell

    def query_matrix(
        self,
        *,
        tickers: Sequence[str | QueryEntity],
        metrics: Sequence[str],
        periods: Sequence[PeriodRequest | TypedPeriod | Mapping[str, Any]],
        policy: QueryPolicy | Mapping[str, Any],
    ) -> MetricMatrix:
        raw_tickers = self._bounded_materialize(
            tickers, maximum=self.bounds.max_tickers, field_name="max_tickers"
        )
        raw_metrics = self._bounded_materialize(
            metrics, maximum=self.bounds.max_metrics, field_name="max_metrics"
        )
        raw_periods = self._bounded_materialize(
            periods, maximum=self.bounds.max_periods, field_name="max_periods"
        )
        entities = tuple(self._entity_for(item) for item in raw_tickers)
        metric_ids = tuple(_require_text(item, field_name="metric_id") for item in raw_metrics)
        selectors = tuple(self._period_for(item) for item in raw_periods)
        query_policy = self._policy_for(policy)
        projection = self._registry_projection(query_policy)
        self._validate_matrix_shape(entities, metric_ids, selectors)
        unsupported = sorted(set(metric_ids) - set(projection.contracts_by_metric))
        if unsupported:
            raise UnsupportedMetricError(f"unsupported metric(s): {', '.join(unsupported)}")
        cache: dict[tuple[Any, ...], MetricCell] = {}
        cells = tuple(
            self._evaluate(
                entity,
                metric,
                selector,
                query_policy,
                projection,
                cache,
                stack=(),
            )
            for entity in sorted(entities, key=lambda item: (item.ticker, item.entity_id))
            for metric in sorted(metric_ids)
            for selector in sorted(selectors, key=lambda item: item.key)
        )
        return MetricMatrix(
            policy=query_policy,
            entities=entities,
            metric_ids=metric_ids,
            periods=selectors,
            cells=cells,
            registry_receipt=projection.receipt,
        )

    query = query_matrix
    matrix = query_matrix

    @staticmethod
    def _bounded_materialize(
        values: Sequence[Any], *, maximum: int, field_name: str
    ) -> tuple[Any, ...]:
        """Consume at most ``maximum + 1`` even when a Sequence lies about length."""
        if isinstance(values, (str, bytes, bytearray)):
            raise QueryValidationError(f"{field_name} must be a sequence of items")
        try:
            count = len(values)
        except TypeError:
            count = None
        except QueryError:
            raise
        except Exception as exc:
            raise QueryValidationError(f"{field_name} has an invalid length contract") from exc
        if count is not None and count > maximum:
            raise QueryBoundsError(f"{field_name} exceeds the configured bound {maximum}")
        try:
            materialized = tuple(islice(iter(values), maximum + 1))
        except QueryError:
            raise
        except Exception as exc:
            raise QueryValidationError(f"{field_name} must be a bounded iterable") from exc
        if len(materialized) > maximum:
            raise QueryBoundsError(f"{field_name} exceeds the configured bound {maximum}")
        return materialized

    def _validate_matrix_shape(
        self,
        entities: Sequence[QueryEntity],
        metric_ids: Sequence[str],
        periods: Sequence[PeriodRequest],
    ) -> None:
        if not entities:
            raise QueryBoundsError("at least one ticker/entity is required")
        if not metric_ids:
            raise QueryBoundsError("at least one metric is required")
        if not periods:
            raise QueryBoundsError("at least one period is required")
        if len(entities) > self.bounds.max_tickers:
            raise QueryBoundsError(f"ticker count exceeds max_tickers={self.bounds.max_tickers}")
        if len(metric_ids) > self.bounds.max_metrics:
            raise QueryBoundsError(f"metric count exceeds max_metrics={self.bounds.max_metrics}")
        if len(periods) > self.bounds.max_periods:
            raise QueryBoundsError(f"period count exceeds max_periods={self.bounds.max_periods}")
        if len({item.ticker for item in entities}) != len(entities):
            raise QueryBoundsError("tickers must be unique")
        if len({item.entity_id for item in entities}) != len(entities):
            raise QueryBoundsError("entity_ids must be unique")
        if len(set(metric_ids)) != len(metric_ids):
            raise QueryBoundsError("metrics must be unique")
        if len({item.key for item in periods}) != len(periods):
            raise QueryBoundsError("periods must be unique")
        cells = len(entities) * len(metric_ids) * len(periods)
        if cells > self.bounds.max_cells:
            raise QueryBoundsError(f"cell count {cells} exceeds max_cells={self.bounds.max_cells}")

    @staticmethod
    def _opaque_provenance(policy: QueryPolicy, *, reason: str) -> CellProvenance:
        """A historical no-result that deliberately carries no future receipt."""
        return CellProvenance(
            kind=ProvenanceKind.OPAQUE,
            evaluation_policy=None,
            policy=policy.selection,
            source_snapshot_at=policy.source_snapshot_at,
            recorded_cutoff_at=policy.recorded_at,
            reason=reason,
        )

    def _base_provenance(
        self,
        projection: _RegistryProjection,
        policy: QueryPolicy,
        contract: MetricContract,
        *,
        kind: ProvenanceKind = ProvenanceKind.DIRECT,
        reason: str | None = None,
        **overrides: Any,
    ) -> CellProvenance:
        values: dict[str, Any] = {
            "kind": kind,
            "evaluation_policy": EvaluationPolicy.ON_DEMAND_CUTOFF_PROJECTION,
            "policy": policy.selection,
            "source_snapshot_at": policy.source_snapshot_at,
            "recorded_cutoff_at": policy.recorded_at,
            "metric_rule_id": contract.rule.rule_id,
            "metric_rule_version": contract.rule.version,
            "metric_rule_digest": projection.contract_digests[contract.metric_id],
            "catalog_id": projection.receipt["catalog_id"],
            "catalog_version": REGISTRY_PROJECTION_VERSION,
            "catalog_digest": projection.catalog_digest,
            "confidence": contract.confidence,
            "governance_available_at": projection.governance_available_by_metric[
                contract.metric_id
            ],
            "reason": reason,
        }
        if "mapping_pack_content_sha256" in projection.receipt:
            values.update(
                {
                    "mapping_pack_version": REGISTRY_PROJECTION_VERSION,
                    "mapping_pack_digest": projection.mapping_pack_digest,
                }
            )
        if kind is ProvenanceKind.DIRECT:
            visible_mappings = projection.mappings_by_metric.get(contract.metric_id, ())
            values.update(
                {
                    "mapping_rule_ids": tuple(
                        mapping.rule.rule_id for mapping in visible_mappings
                    ),
                    "mapping_rule_versions": tuple(
                        mapping.rule.version for mapping in visible_mappings
                    ),
                    "mapping_digests": tuple(
                        projection.mapping_digests[
                            (
                                contract.metric_id,
                                mapping.rule.rule_id,
                                mapping.rule.version,
                            )
                        ]
                        for mapping in visible_mappings
                    ),
                }
            )
        if "formula_pack_content_sha256" in projection.receipt:
            values.update(
                {
                    "formula_pack_version": REGISTRY_PROJECTION_VERSION,
                    "formula_pack_digest": projection.formula_pack_digest,
                }
            )
        if kind is ProvenanceKind.FORMULA:
            formula = projection.formulas_by_metric.get(contract.metric_id)
            if formula is None:
                raise QueryValidationError("formula provenance requires a cutoff-visible formula rule")
            values.update(
                {
                    "formula_rule_id": formula.rule.rule_id,
                    "formula_rule_version": formula.rule.version,
                    "formula_digest": projection.formula_digests[contract.metric_id],
                }
            )
        values.update(overrides)
        return CellProvenance(**values)

    def _new_cell(
        self,
        *,
        entity: QueryEntity,
        metric_id: str,
        period: PeriodRequest,
        state: CellState,
        value: Decimal | None,
        unit: str | None,
        provenance: CellProvenance,
        reason: str | None = None,
    ) -> MetricCell:
        return MetricCell(
            ticker=entity.ticker,
            entity_id=entity.entity_id,
            metric_id=metric_id,
            period=period,
            state=state,
            value=value,
            unit=unit,
            provenance=provenance,
            reason=reason,
        )

    def _evaluate(
        self,
        entity: QueryEntity,
        metric_id: str,
        period: PeriodRequest,
        policy: QueryPolicy,
        projection: _RegistryProjection,
        cache: dict[tuple[Any, ...], MetricCell],
        *,
        stack: tuple[str, ...],
    ) -> MetricCell:
        cache_key = (
            entity.entity_id,
            metric_id,
            period.key,
            policy.selection.value,
            utc_text(policy.source_snapshot_at),
            utc_text(policy.recorded_at),
        )
        existing = cache.get(cache_key)
        if existing is not None:
            return existing
        contract = projection.contracts_by_metric.get(metric_id)
        if contract is None:
            reason = "governance unavailable at recorded_at cutoff"
            result = self._new_cell(
                entity=entity,
                metric_id=metric_id,
                period=period,
                state=CellState.MISSING,
                value=None,
                unit=None,
                provenance=self._opaque_provenance(policy, reason=reason),
                reason=reason,
            )
            cache[cache_key] = result
            return result
        if metric_id in stack:
            # Registry construction rejects formula cycles; retain a safe guard
            # here so a hand-built registry cannot recurse forever.
            reason = f"formula dependency cycle at {metric_id}"
            result = self._new_cell(
                entity=entity,
                metric_id=metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=contract.units[0] if contract.units else None,
                provenance=self._base_provenance(
                    projection,
                    policy,
                    contract,
                    kind=(
                        ProvenanceKind.FORMULA
                        if metric_id in projection.formulas_by_metric
                        else ProvenanceKind.DIRECT
                    ),
                    reason=reason,
                ),
                reason=reason,
            )
            cache[cache_key] = result
            return result
        if contract.formula is None:
            result = self._evaluate_direct(entity, contract, period, policy, projection)
        else:
            result = self._evaluate_formula(
                entity,
                contract,
                period,
                policy,
                projection,
                cache,
                stack + (metric_id,),
            )
        cache[cache_key] = result
        return result

    def _period_contract_error(self, contract: MetricContract, period: PeriodRequest) -> str | None:
        expected = PeriodKind(contract.period_constraints.kind)
        actual = (
            PeriodKind.INSTANT
            if period.normalized.is_instant
            else PeriodKind.DURATION
        )
        if actual is not expected:
            return f"outside_period_constraint: metric requires {expected.value}, requested {actual.value}"
        if expected is PeriodKind.DURATION:
            days = period.normalized.duration_days
            minimum = contract.period_constraints.min_duration_days
            maximum = contract.period_constraints.max_duration_days
            if days is None or minimum is None or maximum is None:
                return "outside_period_constraint: duration bounds are not evaluable"
            if not minimum <= days <= maximum:
                return (
                    "outside_period_constraint: duration "
                    f"{days} days is outside {minimum}..{maximum}"
                )
        return None

    def _direct_rule_available_at(self, contract: MetricContract, mapping: MappingRule) -> datetime:
        # Rule availability is a system knowledge gate, not a source-event
        # claim.  It is intentionally separate from the raw source clocks.
        return max(contract.rule.available_at, mapping.rule.available_at)

    def _formula_rule_available_at(self, contract: MetricContract, formula: FormulaRule) -> datetime:
        return max(contract.rule.available_at, formula.rule.available_at)

    def _aliases_for_period(
        self,
        contract: MetricContract,
        period: PeriodRequest,
        projection: _RegistryProjection,
    ) -> tuple[_AliasCandidate, ...]:
        # Wave 3A boundary: the raw v1 occurrence does not yet carry an
        # attested taxonomy-version field. Until that source contract exists,
        # registry applicability remains a requested-period guard only; it
        # must not be misrepresented as source-taxonomy attestation.
        tax_year = period.normalized.end.year
        values = [
            _AliasCandidate(mapping=mapping, alias=alias)
            for mapping in projection.mappings_by_metric.get(contract.metric_id, ())
            for alias in mapping.taxonomy_concept_aliases
            if alias.taxonomy_version_start <= tax_year <= alias.taxonomy_version_end
        ]
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.alias.priority,
                    item.alias.taxonomy,
                    item.alias.concept,
                    item.mapping.rule.rule_id,
                ),
            )
        )

    def _events_for_alias(
        self,
        entity: QueryEntity,
        alias: ConceptAlias,
        period: PeriodRequest,
    ) -> tuple[RawFactOccurrence, ...]:
        return self._events_by_entity_qname_period.get(
            (
                entity.entity_id,
                f"{alias.taxonomy}:{alias.concept}",
                _request_period_index_key(period),
            ),
            (),
        )

    @staticmethod
    def _context_matches_period(fact: RawFactOccurrence, period: PeriodRequest) -> bool:
        requested = period.normalized
        context = fact.context
        if requested.kind is PeriodKind.INSTANT:
            return context.instant == requested.end
        return context.start == requested.start and context.end == requested.end

    @staticmethod
    def _fact_dimensions_allowed(fact: RawFactOccurrence, contract: MetricContract) -> bool:
        # Registry v1 admits only explicit consolidated-only contracts.  Keep
        # this branch declarative so a later governed dimensional profile can
        # extend it rather than accidentally falling through to a raw fact.
        if contract.dimensional_profile.mode != "consolidated_only":
            return False
        return (
            fact.dimensions_known
            and not fact.context.explicit_dimensions
            and not fact.context.typed_dimensions
        )

    @staticmethod
    def _fact_unit_allowed(fact: RawFactOccurrence, contract: MetricContract) -> bool:
        return _canonical_raw_unit(fact) in set(contract.units)

    def _metadata_for(
        self,
        fact: RawFactOccurrence,
        policy: QueryPolicy,
    ) -> FilingMetadata | None:
        metadata = self._filing_metadata_by_occurrence.get(fact.occurrence_id)
        if metadata is not None and metadata.available_at <= policy.recorded_at:
            return metadata
        # A document filename is not an attested SEC form.  More importantly,
        # absence is not a retained negative metadata artifact: emit no digest
        # or availability clock until an explicitly bound witness is visible.
        return None

    def _event_temporally_eligible(
        self,
        fact: RawFactOccurrence,
        policy: QueryPolicy,
    ) -> bool:
        """Whether this fact *and all required ancestry* is visible on both clocks."""
        lineage = self._lineage_by_occurrence_id[fact.occurrence_id]
        return (
            lineage.source_ready_at is not None
            and lineage.source_ready_at <= policy.source_snapshot_at
            and lineage.system_ready_at <= policy.recorded_at
        )

    def _bounded_visible_events(
        self,
        events: Sequence[RawFactOccurrence],
        policy: QueryPolicy,
        *,
        maximum: int | None = None,
    ) -> tuple[tuple[RawFactOccurrence, ...], bool]:
        limit = (
            self.bounds.max_visible_source_events_per_cell
            if maximum is None
            else maximum
        )
        visible: list[RawFactOccurrence] = []
        for item in events:
            if not self._event_temporally_eligible(item, policy):
                continue
            visible.append(item)
            if len(visible) > limit:
                return (), True
        return tuple(visible), False

    def _lineage_ids_for(
        self,
        group: Sequence[RawFactOccurrence],
    ) -> tuple[str, ...]:
        """Materialize a candidate set's unique ancestry in one linear walk."""
        identifiers: set[str] = set()
        for fact in group:
            current_id: str | None = fact.occurrence_id
            while current_id is not None and current_id not in identifiers:
                identifiers.add(current_id)
                current_id = self._parent_by_occurrence_id.get(current_id)
        return tuple(sorted(identifiers))

    def _group_readiness(
        self,
        group: Sequence[RawFactOccurrence],
    ) -> tuple[datetime | None, datetime | None]:
        metadata = tuple(self._lineage_by_occurrence_id[item.occurrence_id] for item in group)
        if not metadata or any(item.source_ready_at is None for item in metadata):
            source_ready_at = None
        else:
            source_ready_at = max(
                item.source_ready_at for item in metadata if item.source_ready_at is not None
            )
        system_ready_at = max((item.system_ready_at for item in metadata), default=None)
        return source_ready_at, system_ready_at

    def _group_clocks(
        self,
        group: Sequence[RawFactOccurrence],
    ) -> tuple[datetime | None, datetime | None, tuple[str, ...]]:
        source_ready, system_ready = self._group_readiness(group)
        return source_ready, system_ready, self._lineage_ids_for(group)

    def _select_source_group(
        self,
        events: Sequence[RawFactOccurrence],
        policy: QueryPolicy,
    ) -> _SourceSelection:
        """Select one fully visible economic vintage without tie-breaking by ID.

        All temporal filtering happens before duplicate, unit, dimension, or
        revision reasoning. A fact unavailable on either clock is therefore
        indistinguishable from absence to this query snapshot: no occurrence
        ID, exact future clock, or future-specific explanation escapes.
        """
        if not events:
            return _SourceSelection(
                state=CellState.MISSING,
                occurrence=None,
                source_ready_at=None,
                system_ready_at=None,
                source_occurrence_ids=(),
                reason="missing_standard_fact",
            )
        visible_events = tuple(
            item for item in events if self._event_temporally_eligible(item, policy)
        )
        if not visible_events:
            return _SourceSelection(
                state=CellState.MISSING,
                occurrence=None,
                source_ready_at=None,
                system_ready_at=None,
                source_occurrence_ids=(),
                reason="missing_standard_fact",
            )
        # A raw-ledger logical key includes the source origin as well as the
        # economic context.  A query must never choose between two origins by
        # timestamp alone; a source-fusion policy would need its own governed
        # contract and receipt.
        logical_keys = {item.logical_key for item in visible_events}
        if len(logical_keys) != 1:
            source_ready_at, system_ready_at = self._group_readiness(visible_events)
            return _SourceSelection(
                state=CellState.NOT_EVALUABLE,
                occurrence=None,
                source_ready_at=source_ready_at,
                system_ready_at=system_ready_at,
                source_occurrence_ids=self._lineage_ids_for(visible_events),
                reason="multiple raw economic identities require an explicit governed source-fusion rule",
            )
        groups: dict[str, list[RawFactOccurrence]] = {}
        for event in visible_events:
            groups.setdefault(event.duplicate_group_key, []).append(event)
        ordered: list[
            tuple[datetime, datetime, int, tuple[RawFactOccurrence, ...], str]
        ] = []
        for key, values in groups.items():
            group = tuple(values)
            source_ready, system_ready = self._group_readiness(group)
            # ``visible_events`` gates every ancestry member, so source_ready
            # is non-null and both clocks are known to the snapshot.
            if source_ready is None:
                continue
            depth = max(
                self._lineage_by_occurrence_id[item.occurrence_id].depth for item in group
            )
            ordered.append((source_ready, system_ready, depth, group, key))
        if not ordered:
            return _SourceSelection(
                state=CellState.MISSING,
                occurrence=None,
                source_ready_at=None,
                system_ready_at=None,
                source_occurrence_ids=(),
                reason="missing_standard_fact",
            )

        def ids_for(
            items: Sequence[
                tuple[datetime, datetime, int, tuple[RawFactOccurrence, ...], str]
            ],
        ) -> tuple[str, ...]:
            return self._lineage_ids_for(
                tuple(event for item in items for event in item[3])
            )

        # Two visible roots have no attested revision relationship. Filing
        # time and hashes are not a source-fusion policy, so never infer one.
        root_ids = {
            self._lineage_by_occurrence_id[item[3][0].occurrence_id].root_occurrence_id
            for item in ordered
            if item[3]
        }
        if len(root_ids) != 1:
            return _SourceSelection(
                state=CellState.NOT_EVALUABLE,
                occurrence=None,
                source_ready_at=_clock_max(item[0] for item in ordered),
                system_ready_at=_clock_max(item[1] for item in ordered),
                source_occurrence_ids=ids_for(ordered),
                reason="unlinked source vintages require an explicit typed revision lineage",
            )

        if policy.selection is BitemporalPolicy.AS_REPORTED:
            candidates = [item for item in ordered if all(event.revision_of is None for event in item[3])]
            if not candidates:
                return _SourceSelection(
                    state=CellState.MISSING,
                    occurrence=None,
                    source_ready_at=None,
                    system_ready_at=None,
                    source_occurrence_ids=(),
                    reason="missing_standard_fact",
                )
            rank = min(item[0] for item in candidates)
            winners = [item for item in candidates if item[0] == rank]
        elif policy.selection is BitemporalPolicy.LATEST_RESTATED:
            candidates = [
                item
                for item in ordered
                if all(event.event_type in _REPORTED_REVISION_EVENT_TYPES for event in item[3])
            ]
            if not candidates:
                return _SourceSelection(
                    state=CellState.MISSING,
                    occurrence=None,
                    source_ready_at=None,
                    system_ready_at=None,
                    source_occurrence_ids=(),
                    reason="no eligible explicitly typed reported revision vintage",
                )
            rank = max((item[0], item[2]) for item in candidates)
            winners = [item for item in candidates if (item[0], item[2]) == rank]
        else:
            candidates = ordered
            rank = max((item[0], item[2]) for item in candidates)
            winners = [item for item in candidates if (item[0], item[2]) == rank]

        if len(winners) != 1:
            return _SourceSelection(
                state=CellState.NOT_EVALUABLE,
                occurrence=None,
                source_ready_at=_clock_max(item[0] for item in winners),
                system_ready_at=_clock_max(item[1] for item in winners),
                source_occurrence_ids=ids_for(winners),
                reason="ambiguous equal-precedence source vintages cannot be selected",
            )
        source_ready, system_ready, _, group, _ = winners[0]
        ids = ids_for(winners)
        if any(item.is_withdrawn for item in group):
            return _SourceSelection(
                state=CellState.MISSING,
                occurrence=None,
                source_ready_at=source_ready,
                system_ready_at=system_ready,
                source_occurrence_ids=ids,
                reason="selected source vintage is withdrawn",
            )
        if not _duplicates_agree(group):
            return _SourceSelection(
                state=CellState.NOT_EVALUABLE,
                occurrence=None,
                source_ready_at=source_ready,
                system_ready_at=system_ready,
                source_occurrence_ids=ids,
                reason="conflicting duplicate raw facts cannot be selected",
            )
        chosen = _duplicate_representative(group)
        if chosen.is_nil or chosen.parsed_value is None:
            return _SourceSelection(
                state=CellState.MISSING,
                occurrence=None,
                source_ready_at=source_ready,
                system_ready_at=system_ready,
                source_occurrence_ids=ids,
                reason="selected source fact has no numeric value",
            )
        return _SourceSelection(
            state=CellState.VALUE,
            occurrence=chosen,
            source_ready_at=source_ready,
            system_ready_at=system_ready,
            source_occurrence_ids=ids,
        )

    def _ambiguous_alias_priorities(
        self,
        candidates: Sequence[_AliasCandidate],
    ) -> set[int]:
        """Return fallback priorities claimed by multiple visible aliases.

        Priority is metric-global.  Treating it as local to each mapping rule
        would make lexical concept/rule order an undocumented tie-breaker.
        """
        by_priority: dict[int, set[tuple[str, str, str, str]]] = {}
        for item in candidates:
            by_priority.setdefault(item.alias.priority, set()).add(
                (
                    item.alias.taxonomy,
                    item.alias.concept,
                    item.mapping.rule.rule_id,
                    item.mapping.rule.version,
                )
            )
        return {priority for priority, aliases in by_priority.items() if len(aliases) > 1}

    def _evaluate_direct(
        self,
        entity: QueryEntity,
        contract: MetricContract,
        period: PeriodRequest,
        policy: QueryPolicy,
        projection: _RegistryProjection,
    ) -> MetricCell:
        """Evaluate a direct metric after temporal and governance eligibility.

        A visible-but-unsafe candidate is retained as a governed N/E outcome
        only after every eligible governed alias has failed to supply a safe
        consolidated/unit-compatible source. This permits a valid
        consolidated fact to coexist with segmented inventory without opening
        an ungoverned fallback path.
        """
        visible_mappings = projection.mappings_by_metric.get(contract.metric_id, ())
        if not visible_mappings:
            reason = "governance unavailable at recorded_at cutoff"
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.MISSING,
                value=None,
                unit=None,
                provenance=self._opaque_provenance(policy, reason=reason),
                reason=reason,
            )
        all_candidates = self._aliases_for_period(contract, period, projection)
        # A mapping/rule unknown at the recorded cutoff cannot even suppress a
        # lower-priority governed alias. It also cannot contribute its future
        # ID, digest, or alias-specific reason to a historical cell. Do this
        # before period semantics, matching formula-rule treatment: an
        # otherwise invalid request must not become a side channel for a
        # future mapping's existence.
        candidates = all_candidates
        if not candidates:
            reason = "no governed concept alias applies to the requested taxonomy period"
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.MISSING,
                value=None,
                unit=contract.units[0] if contract.units else None,
                provenance=self._base_provenance(
                    projection, policy, contract, reason=reason
                ),
                reason=reason,
            )
        contract_error = self._period_contract_error(contract, period)
        if contract_error:
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=contract.units[0] if contract.units else None,
                provenance=self._base_provenance(
                    projection, policy, contract, reason=contract_error
                ),
                reason=contract_error,
            )
        ambiguous_priorities = self._ambiguous_alias_priorities(candidates)
        if ambiguous_priorities:
            reason = "ambiguous governed alias priorities across visible mapping rules"
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=contract.units[0] if contract.units else None,
                provenance=self._base_provenance(
                    projection,
                    policy,
                    contract,
                    reason=reason,
                ),
                reason=reason,
            )
        visible_candidate_events: list[
            tuple[_AliasCandidate, tuple[RawFactOccurrence, ...]]
        ] = []
        visible_source_count = 0
        for candidate in candidates:
            raw_events = self._events_for_alias(entity, candidate.alias, period)
            remaining = (
                self.bounds.max_visible_source_events_per_cell
                - visible_source_count
            )
            period_events, source_history_over_bound = self._bounded_visible_events(
                raw_events,
                policy,
                maximum=remaining,
            )
            if source_history_over_bound:
                reason = "visible source history exceeds the synchronous per-cell bound"
                return self._new_cell(
                    entity=entity,
                    metric_id=contract.metric_id,
                    period=period,
                    state=CellState.NOT_EVALUABLE,
                    value=None,
                    unit=contract.units[0] if contract.units else None,
                    provenance=self._base_provenance(
                        projection,
                        policy,
                        contract,
                        reason=reason,
                    ),
                    reason=reason,
                )
            visible_source_count += len(period_events)
            visible_candidate_events.append((candidate, period_events))
        structural_failure: tuple[_AliasCandidate, str, tuple[RawFactOccurrence, ...]] | None = None
        for candidate, period_events in visible_candidate_events:
            mapping, alias = candidate.mapping, candidate.alias
            mapping_digest = projection.mapping_digests[
                (contract.metric_id, mapping.rule.rule_id, mapping.rule.version)
            ]
            if not period_events:
                # A higher-priority alias that exists only in the future is
                # indistinguishable from absent and cannot block a lower one.
                continue
            unknown_dimension_scope = tuple(
                item for item in period_events if not item.dimensions_known
            )
            disallowed_dimensions = tuple(
                item for item in period_events if not self._fact_dimensions_allowed(item, contract)
            )
            unit_events = tuple(item for item in period_events if not self._fact_unit_allowed(item, contract))
            eligible_structure = tuple(
                item
                for item in period_events
                if self._fact_dimensions_allowed(item, contract) and self._fact_unit_allowed(item, contract)
            )
            if not eligible_structure:
                if structural_failure is None:
                    if unknown_dimension_scope:
                        structural_failure = (
                            candidate,
                            "unknown_dimension_scope: source does not expose dimensions, "
                            "so consolidated-only eligibility cannot be established",
                            unknown_dimension_scope,
                        )
                    elif disallowed_dimensions:
                        structural_failure = (
                            candidate,
                            "disallowed_dimension: governed metric requires consolidated dimensionless fact",
                            disallowed_dimensions,
                        )
                    elif unit_events:
                        structural_failure = (
                            candidate,
                            "unexpected_unit: source unit is outside the governed metric contract",
                            unit_events,
                        )
                continue
            selection = self._select_source_group(eligible_structure, policy)
            if selection.state is not CellState.VALUE:
                reason = selection.reason or "missing_standard_fact"
                if selection.state is CellState.MISSING and reason in {
                    "missing_standard_fact",
                    "no eligible explicitly typed reported revision vintage",
                }:
                    continue
                return self._new_cell(
                    entity=entity,
                    metric_id=contract.metric_id,
                    period=period,
                    state=selection.state,
                    value=None,
                    unit=contract.units[0] if contract.units else None,
                    provenance=self._base_provenance(
                        projection,
                        policy,
                        contract,
                        reason=reason,
                        concept_qname=f"{alias.taxonomy}:{alias.concept}",
                        taxonomy=alias.taxonomy,
                        concept=alias.concept,
                        mapping_rule_id=mapping.rule.rule_id,
                        mapping_rule_version=mapping.rule.version,
                        mapping_digest=mapping_digest,
                        alias_priority=alias.priority,
                        source_ready_at=selection.source_ready_at,
                        system_ready_at=_clock_max(
                            (
                                selection.system_ready_at,
                                projection.governance_available_by_metric[contract.metric_id],
                            )
                        ),
                        source_occurrence_ids=selection.source_occurrence_ids,
                    ),
                    reason=reason,
                )
            fact = selection.occurrence
            if fact is None:  # pragma: no cover - _SourceSelection guards this invariant.
                raise AssertionError("value source selection omitted occurrence")
            metadata = self._metadata_for(fact, policy)
            source_receipt = {
                "source": fact.source.source,
                "accession": fact.source.accession,
                "document_id": fact.source.document_id,
                "source_url": fact.source.source_url,
                "source_body_sha256": fact.source.body_sha256,
                "form": metadata.form if metadata is not None else None,
                "filed_at": metadata.filed_at if metadata is not None else None,
                "filing_metadata_available_at": (
                    metadata.available_at if metadata is not None else None
                ),
                "filing_metadata_content_sha256": (
                    metadata.content_sha256 if metadata is not None else None
                ),
                "accepted_at": fact.accepted_at,
                "recorded_at": fact.recorded_at,
                "mapping_available_at": fact.mapping_available_at,
                "computed_at": fact.computed_at,
                "published_at": fact.published_at,
                "source_ready_at": selection.source_ready_at,
                "system_ready_at": _clock_max(
                    (
                        selection.system_ready_at,
                        metadata.available_at if metadata is not None else None,
                        projection.governance_available_by_metric[contract.metric_id],
                    )
                ),
                "concept_qname": fact.concept_qname,
                "taxonomy": alias.taxonomy,
                "concept": alias.concept,
                "unit": _canonical_raw_unit(fact),
                "mapping_rule_id": mapping.rule.rule_id,
                "mapping_rule_version": mapping.rule.version,
                "mapping_digest": mapping_digest,
                "alias_priority": alias.priority,
                "source_occurrence_ids": selection.source_occurrence_ids,
            }
            if (
                metadata is None
                or metadata.form not in contract.period_constraints.allowed_forms
            ):
                reason = "filing form is unavailable or outside the governed metric contract"
                return self._new_cell(
                    entity=entity,
                    metric_id=contract.metric_id,
                    period=period,
                    state=CellState.NOT_EVALUABLE,
                    value=None,
                    unit=contract.units[0] if contract.units else None,
                    provenance=self._base_provenance(
                        projection,
                        policy,
                        contract,
                        reason=reason,
                        **source_receipt,
                    ),
                    reason=reason,
                )
            try:
                numeric_value = _bounded_decimal(fact.parsed_value, field_name="source fact value")
            except QueryValidationError:
                reason = "source numeric value is outside the query decimal contract"
                return self._new_cell(
                    entity=entity,
                    metric_id=contract.metric_id,
                    period=period,
                    state=CellState.NOT_EVALUABLE,
                    value=None,
                    unit=contract.units[0] if contract.units else None,
                    provenance=self._base_provenance(
                        projection,
                        policy,
                        contract,
                        reason=reason,
                        **source_receipt,
                    ),
                    reason=reason,
                )
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.VALUE,
                value=numeric_value,
                unit=_canonical_raw_unit(fact),
                provenance=self._base_provenance(
                    projection,
                    policy,
                    contract,
                    **source_receipt,
                ),
            )
        if structural_failure is not None:
            candidate, reason, evidence = structural_failure
            mapping, alias = candidate.mapping, candidate.alias
            mapping_digest = projection.mapping_digests[
                (contract.metric_id, mapping.rule.rule_id, mapping.rule.version)
            ]
            source_ready_at, evidence_system_ready_at, evidence_ids = self._group_clocks(evidence)
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=contract.units[0] if contract.units else None,
                provenance=self._base_provenance(
                    projection,
                    policy,
                    contract,
                    reason=reason,
                    concept_qname=f"{alias.taxonomy}:{alias.concept}",
                    taxonomy=alias.taxonomy,
                    concept=alias.concept,
                    mapping_rule_id=mapping.rule.rule_id,
                    mapping_rule_version=mapping.rule.version,
                    mapping_digest=mapping_digest,
                    alias_priority=alias.priority,
                    source_ready_at=source_ready_at,
                    system_ready_at=_clock_max(
                        (
                            evidence_system_ready_at,
                            projection.governance_available_by_metric[contract.metric_id],
                        )
                    ),
                    source_occurrence_ids=evidence_ids,
                ),
                reason=reason,
            )
        reason = (
            "no eligible explicitly typed reported revision vintage"
            if policy.selection is BitemporalPolicy.LATEST_RESTATED
            else "missing_standard_fact: no governed concept alias supplied an exact eligible source interval"
        )
        return self._new_cell(
            entity=entity,
            metric_id=contract.metric_id,
            period=period,
            state=CellState.MISSING,
            value=None,
            unit=contract.units[0] if contract.units else None,
            provenance=self._base_provenance(
                projection, policy, contract, reason=reason
            ),
            reason=reason,
        )

    @staticmethod
    def _dependency_period(
        output_period: PeriodRequest,
        dependency: MetricContract,
        formula: FormulaRule,
    ) -> PeriodRequest:
        dependency_kind = PeriodKind(dependency.period_constraints.kind)
        if formula.dependency_period_alignment == "same_period":
            return output_period
        if formula.dependency_period_alignment == "ending_instant_to_duration":
            if dependency_kind is PeriodKind.INSTANT:
                return PeriodRequest(
                    kind=PeriodKind.INSTANT,
                    end=output_period.normalized.end,
                    fiscal_year=output_period.normalized.fiscal_year,
                    fiscal_quarter=output_period.normalized.fiscal_quarter,
                )
            return output_period
        raise QueryValidationError(
            f"unsupported governed dependency_period_alignment: {formula.dependency_period_alignment}"
        )

    @staticmethod
    def _eval_formula(expression: str, values: Mapping[str, Decimal]) -> Decimal:
        """Evaluate governed arithmetic under the fixed query Decimal contract."""
        try:
            root = ast.parse(expression, mode="eval").body
        except SyntaxError as exc:  # pragma: no cover - registry validation catches this first.
            raise QueryValidationError("formula expression is invalid") from exc

        try:
            with localcontext(_formula_context()):
                normalized_values: dict[str, Decimal] = {}
                for name, value in values.items():
                    if not isinstance(value, Decimal):
                        raise QueryValidationError(
                            f"formula dependency {name} is not a Decimal value"
                        )
                    normalized_values[name] = +_bounded_decimal(
                        value, field_name=f"formula dependency {name}"
                    )

                def visit(node: ast.AST) -> Decimal:
                    if isinstance(node, ast.Name):
                        try:
                            return normalized_values[node.id]
                        except KeyError as exc:
                            raise QueryValidationError(
                                f"formula references unbound dependency: {node.id}"
                            ) from exc
                    if isinstance(node, ast.BinOp):
                        left, right = visit(node.left), visit(node.right)
                        if isinstance(node.op, ast.Add):
                            return left + right
                        if isinstance(node.op, ast.Sub):
                            return left - right
                        if isinstance(node.op, ast.Mult):
                            return left * right
                        if isinstance(node.op, ast.Div):
                            if right == 0:
                                raise ZeroDivisionError
                            return left / right
                    raise QueryValidationError("formula contains unsupported expression construct")

                value = +visit(root)
                if not value.is_finite():
                    raise QueryValidationError("formula result is not finite")
                return _bounded_decimal(value, field_name="formula result")
        except (DecimalException, OverflowError) as exc:
            raise QueryValidationError(
                "formula numeric result violates the fixed decimal contract"
            ) from exc

    def _formula_provenance(
        self,
        projection: _RegistryProjection,
        policy: QueryPolicy,
        contract: MetricContract,
        formula: FormulaRule,
        dependencies: Sequence[MetricCell],
        *,
        reason: str | None = None,
    ) -> CellProvenance:
        def common(field_name: str) -> Any | None:
            values = {getattr(item.provenance, field_name) for item in dependencies}
            if len(values) != 1:
                return None
            value = next(iter(values))
            return value if value is not None else None

        mapping_rule_ids = tuple(
            sorted({identifier for item in dependencies for identifier in item.provenance.mapping_rule_ids})
        )
        mapping_rule_versions = tuple(
            sorted({version for item in dependencies for version in item.provenance.mapping_rule_versions})
        )
        mapping_digests = tuple(
            sorted({digest for item in dependencies for digest in item.provenance.mapping_digests})
        )
        formula_available_at = self._formula_rule_available_at(contract, formula)
        source_ready_at = _clock_max(item.provenance.source_ready_at for item in dependencies)
        system_ready_at = _clock_max(
            [formula_available_at]
            + [item.provenance.system_ready_at for item in dependencies]
        )
        return self._base_provenance(
            projection,
            policy,
            contract,
            kind=ProvenanceKind.FORMULA,
            reason=reason,
            source_ready_at=source_ready_at,
            system_ready_at=system_ready_at,
            mapping_rule_id=mapping_rule_ids[0] if len(mapping_rule_ids) == 1 else None,
            mapping_rule_version=(
                mapping_rule_versions[0] if len(mapping_rule_versions) == 1 else None
            ),
            mapping_digest=mapping_digests[0] if len(mapping_digests) == 1 else None,
            mapping_rule_ids=mapping_rule_ids,
            mapping_rule_versions=mapping_rule_versions,
            mapping_digests=mapping_digests,
            confidence=formula.rule.confidence,
            source=common("source"),
            accession=common("accession"),
            document_id=common("document_id"),
            source_body_sha256=common("source_body_sha256"),
            source_url=common("source_url"),
            dependency_cells=tuple(dependencies),
            unit=formula.output_unit,
        )

    def _evaluate_formula(
        self,
        entity: QueryEntity,
        contract: MetricContract,
        period: PeriodRequest,
        policy: QueryPolicy,
        projection: _RegistryProjection,
        cache: dict[tuple[Any, ...], MetricCell],
        stack: tuple[str, ...],
    ) -> MetricCell:
        formula = projection.formulas_by_metric.get(contract.metric_id)
        # Do not inspect dependencies before the formula itself existed in the
        # system's governed state. Otherwise a future formula ID/digest and
        # dependency lineage can leak into an historical query result.
        if formula is None:
            reason = "governance unavailable at recorded_at cutoff"
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.MISSING,
                value=None,
                unit=None,
                provenance=self._opaque_provenance(policy, reason=reason),
                reason=reason,
            )
        contract_error = self._period_contract_error(contract, period)
        if contract_error:
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=formula.output_unit,
                provenance=self._base_provenance(
                    projection,
                    policy,
                    contract,
                    kind=ProvenanceKind.FORMULA,
                    reason=contract_error,
                ),
                reason=contract_error,
            )
        dependency_cells: list[MetricCell] = []
        for dependency_id in formula.dependencies:
            dependency_contract = projection.contracts_by_metric.get(dependency_id)
            if dependency_contract is None:
                reason = "governance unavailable at recorded_at cutoff"
                return self._new_cell(
                    entity=entity,
                    metric_id=contract.metric_id,
                    period=period,
                    state=CellState.MISSING,
                    value=None,
                    unit=None,
                    provenance=self._opaque_provenance(policy, reason=reason),
                    reason=reason,
                )
            dependency_period = self._dependency_period(period, dependency_contract, formula)
            dependency_cells.append(
                self._evaluate(
                    entity,
                    dependency_id,
                    dependency_period,
                    policy,
                    projection,
                    cache,
                    stack=stack,
                )
            )
        not_evaluable = [item for item in dependency_cells if item.state is CellState.NOT_EVALUABLE]
        if not_evaluable:
            reason = "incompatible_dependencies: " + ", ".join(
                f"{item.metric_id} ({item.reason or 'not_evaluable'})" for item in not_evaluable
            )
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=formula.output_unit,
                provenance=self._formula_provenance(
                    projection, policy, contract, formula, dependency_cells, reason=reason
                ),
                reason=reason,
            )
        missing = [item for item in dependency_cells if item.state is CellState.MISSING]
        if missing:
            reason = "missing_dependency: " + ", ".join(
                f"{item.metric_id} ({item.reason or 'missing'})" for item in missing
            )
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.MISSING,
                value=None,
                unit=formula.output_unit,
                provenance=self._formula_provenance(
                    projection, policy, contract, formula, dependency_cells, reason=reason
                ),
                reason=reason,
            )
        values = {item.metric_id: item.value for item in dependency_cells}
        if any(value is None for value in values.values()):  # pragma: no cover - state invariant.
            raise AssertionError("value dependencies must carry Decimal values")
        revision_bases = {
            (
                item.provenance.source,
                item.provenance.accession,
                item.provenance.document_id,
                item.provenance.source_body_sha256,
            )
            for item in dependency_cells
        }
        if (
            len(revision_bases) != 1
            or any(any(part is None for part in basis) for basis in revision_bases)
        ):
            reason = "incompatible_revision_basis: formula dependencies require one shared source accession/document"
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=formula.output_unit,
                provenance=self._formula_provenance(
                    projection, policy, contract, formula, dependency_cells, reason=reason
                ),
                reason=reason,
            )
        try:
            result = self._eval_formula(
                formula.expression,
                {key: value for key, value in values.items() if value is not None},
            )
        except ZeroDivisionError:
            reason = "division_by_zero"
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=formula.output_unit,
                provenance=self._formula_provenance(
                    projection, policy, contract, formula, dependency_cells, reason=reason
                ),
                reason=reason,
            )
        except QueryValidationError as exc:
            reason = str(exc)
            return self._new_cell(
                entity=entity,
                metric_id=contract.metric_id,
                period=period,
                state=CellState.NOT_EVALUABLE,
                value=None,
                unit=formula.output_unit,
                provenance=self._formula_provenance(
                    projection, policy, contract, formula, dependency_cells, reason=reason
                ),
                reason=reason,
            )
        return self._new_cell(
            entity=entity,
            metric_id=contract.metric_id,
            period=period,
            state=CellState.VALUE,
            value=result,
            unit=formula.output_unit,
            provenance=self._formula_provenance(
                projection, policy, contract, formula, dependency_cells
            ),
        )


# The shorter name is the natural import in request handlers; preserve the
# fully explicit class above for code that makes temporal semantics visible.
MetricQueryEngine = BitemporalMetricQueryEngine


__all__ = [
    "BitemporalMetricQueryEngine",
    "BitemporalPolicy",
    "BitemporalQueryPolicy",
    "CellProvenance",
    "CellState",
    "DeterministicExport",
    "EvaluationPolicy",
    "FilingMetadata",
    "FilingMetadataResolver",
    "FORMULA_DECIMAL_EMAX",
    "FORMULA_DECIMAL_EMIN",
    "FORMULA_DECIMAL_PRECISION",
    "HARD_MAX_CELLS",
    "HARD_MAX_DEPENDENCY_RECEIPTS",
    "HARD_MAX_METRICS",
    "HARD_MAX_PERIODS",
    "HARD_MAX_PROVENANCE_IDS",
    "HARD_MAX_TICKERS",
    "HARD_MAX_VISIBLE_SOURCE_EVENTS_PER_CELL",
    "MAX_QUERY_TEXT_CHARS",
    "MetricCell",
    "MetricCellState",
    "MetricMatrix",
    "MetricPeriod",
    "MetricQueryEngine",
    "MetricQueryPolicy",
    "PeriodRequest",
    "PeriodSelector",
    "ProvenanceKind",
    "QUERY_SCHEMA",
    "QueryBounds",
    "QueryBoundsError",
    "QueryCutoffs",
    "QueryEntity",
    "QueryError",
    "QueryPolicy",
    "QueryValidationError",
    "UnsupportedConceptError",
    "UnsupportedMetricError",
]
