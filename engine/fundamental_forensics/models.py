"""Immutable domain objects for the Fundamental Forensics fixture kernel.

The first slice deliberately uses only the standard library.  Financial values
are represented as canonical decimal strings at the contract boundary, and all
IDs are content-derived so replaying the same source payload is byte-stable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


RUN_SCHEMA = "fundamental_forensics.run/v1"


class KnowledgeClock(str, Enum):
    SOURCE_EVENT = "source_event"
    RECORDED = "recorded"


class VintagePolicy(str, Enum):
    FIRST_REPORTED = "first_reported"
    LATEST_KNOWN = "latest_known"


class FindingState(str, Enum):
    TRIGGERED = "triggered"
    CLEAR = "clear"
    NOT_EVALUABLE = "not_evaluable"


def parse_utc(value: str | datetime | None, *, field: str = "timestamp") -> datetime | None:
    """Parse an aware timestamp and normalize it to UTC.

    Clock assumptions are never implicit.  A naive timestamp is rejected rather
    than silently interpreted in the machine's local timezone.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        out = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            out = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid {field}: {value!r}") from exc
    if out.tzinfo is None:
        raise ValueError(f"{field} must include a timezone: {value!r}")
    return out.astimezone(timezone.utc)


def utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def decimal_text(value: Any) -> str:
    """Return a non-exponent, non-lossy canonical Decimal representation."""
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc
    if not out.is_finite():
        raise ValueError(f"decimal value must be finite: {value!r}")
    if out == 0:
        return "0"
    text = format(out, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _primitive(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, Mapping):
        return {str(k): _primitive(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_primitive(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def stable_id(prefix: str, *parts: Any) -> str:
    payload = canonical_json(list(parts)).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True)
class SourceFiling:
    filing_id: str
    entity_cik: str
    accession: str
    form: str | None
    filing_date: str | None
    report_date: str | None
    source_event_at: datetime | None
    primary_document: str | None
    is_xbrl: bool | None
    is_inline_xbrl: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filing_id": self.filing_id,
            "entity_cik": self.entity_cik,
            "accession": self.accession,
            "form": self.form,
            "filing_date": self.filing_date,
            "report_date": self.report_date,
            "source_event_at": utc_text(self.source_event_at),
            "primary_document": self.primary_document,
            "is_xbrl": self.is_xbrl,
            "is_inline_xbrl": self.is_inline_xbrl,
        }


@dataclass(frozen=True)
class FactOccurrence:
    fact_id: str
    entity_cik: str
    entity_name: str
    taxonomy: str
    concept: str
    unit: str
    value: str
    period_start: str | None
    period_end: str
    accession: str | None
    form: str | None
    filed: str | None
    reported_fy: int | None
    reported_fp: str | None
    frame: str | None
    filing_id: str | None
    source_event_at: datetime | None
    recorded_at: datetime
    pit_eligible: bool
    source_record_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "entity_cik": self.entity_cik,
            "entity_name": self.entity_name,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "unit": self.unit,
            "value": self.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "accession": self.accession,
            "form": self.form,
            "filed": self.filed,
            "reported_fy": self.reported_fy,
            "reported_fp": self.reported_fp,
            "frame": self.frame,
            "filing_id": self.filing_id,
            "source_event_at": utc_text(self.source_event_at),
            "recorded_at": utc_text(self.recorded_at),
            "pit_eligible": self.pit_eligible,
            "source_record_count": self.source_record_count,
        }


@dataclass(frozen=True)
class NormalizationIssue:
    issue_id: str
    code: str
    metric: str
    entity_cik: str
    accession: str | None
    period_end: str
    fact_ids: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "code": self.code,
            "metric": self.metric,
            "entity_cik": self.entity_cik,
            "accession": self.accession,
            "period_end": self.period_end,
            "fact_ids": list(self.fact_ids),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class NormalizedObservation:
    observation_id: str
    entity_cik: str
    metric: str
    value: str
    unit: str
    period_type: str
    period_start: str | None
    period_end: str
    accession: str
    source_event_at: datetime | None
    recorded_at: datetime
    mapping_version: str
    mapping_rule_id: str
    mapping_tier: str
    mapping_rule_available_at: datetime
    fact_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "entity_cik": self.entity_cik,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "period_type": self.period_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "accession": self.accession,
            "source_event_at": utc_text(self.source_event_at),
            "recorded_at": utc_text(self.recorded_at),
            "mapping_version": self.mapping_version,
            "mapping_rule_id": self.mapping_rule_id,
            "mapping_tier": self.mapping_tier,
            "mapping_rule_available_at": utc_text(self.mapping_rule_available_at),
            "fact_ids": list(self.fact_ids),
        }


@dataclass(frozen=True)
class StatementVintage:
    vintage_id: str
    entity_cik: str
    accession: str
    period_end: str
    source_event_at: datetime | None
    recorded_at: datetime
    metric_observation_ids: tuple[tuple[str, str], ...]

    def metrics(self) -> dict[str, str]:
        return dict(self.metric_observation_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vintage_id": self.vintage_id,
            "entity_cik": self.entity_cik,
            "accession": self.accession,
            "period_end": self.period_end,
            "source_event_at": utc_text(self.source_event_at),
            "recorded_at": utc_text(self.recorded_at),
            "metric_observation_ids": dict(self.metric_observation_ids),
        }


@dataclass(frozen=True)
class FindingInput:
    metric: str
    period_end: str
    value: str
    observation_id: str
    fact_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "period_end": self.period_end,
            "value": self.value,
            "observation_id": self.observation_id,
            "fact_ids": list(self.fact_ids),
        }


@dataclass(frozen=True)
class Finding:
    finding_id: str
    detector_id: str
    detector_version: str
    detector_rule_available_at: datetime
    entity_cik: str
    state: FindingState
    applicability: str
    formula: str
    thresholds: tuple[tuple[str, str], ...]
    derived_values: tuple[tuple[str, str], ...]
    period_ends: tuple[str, ...]
    inputs: tuple[FindingInput, ...]
    missing_inputs: tuple[str, ...]
    evidence_observation_ids: tuple[str, ...]
    evidence_fact_ids: tuple[str, ...]
    source_ready_at: datetime | None
    recorded_ready_at: datetime | None
    computed_at: datetime
    limitations: tuple[str, ...]
    display_only: bool = True
    authority: str = "review_priority_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "detector_rule_available_at": utc_text(self.detector_rule_available_at),
            "entity_cik": self.entity_cik,
            "state": self.state.value,
            "applicability": self.applicability,
            "formula": self.formula,
            "thresholds": dict(self.thresholds),
            "derived_values": dict(self.derived_values),
            "period_ends": list(self.period_ends),
            "inputs": [item.to_dict() for item in self.inputs],
            "missing_inputs": list(self.missing_inputs),
            "evidence_observation_ids": list(self.evidence_observation_ids),
            "evidence_fact_ids": list(self.evidence_fact_ids),
            "source_ready_at": utc_text(self.source_ready_at),
            "recorded_ready_at": utc_text(self.recorded_ready_at),
            "computed_at": utc_text(self.computed_at),
            "limitations": list(self.limitations),
            "display_only": self.display_only,
            "authority": self.authority,
        }


@dataclass(frozen=True)
class Coverage:
    source_fact_records: int
    distinct_fact_occurrences: int
    facts_with_source_clock: int
    normalized_observations: int
    normalization_issues: int
    statement_vintages: int
    selected_statement_vintages: int
    findings_triggered: int
    findings_clear: int
    findings_not_evaluable: int

    def to_dict(self) -> dict[str, int]:
        return {
            "source_fact_records": self.source_fact_records,
            "distinct_fact_occurrences": self.distinct_fact_occurrences,
            "facts_with_source_clock": self.facts_with_source_clock,
            "normalized_observations": self.normalized_observations,
            "normalization_issues": self.normalization_issues,
            "statement_vintages": self.statement_vintages,
            "selected_statement_vintages": self.selected_statement_vintages,
            "findings_triggered": self.findings_triggered,
            "findings_clear": self.findings_clear,
            "findings_not_evaluable": self.findings_not_evaluable,
        }


@dataclass(frozen=True)
class IngestBundle:
    entity_cik: str
    entity_name: str
    filings: tuple[SourceFiling, ...]
    facts: tuple[FactOccurrence, ...]


@dataclass(frozen=True)
class NormalizationResult:
    observations: tuple[NormalizedObservation, ...]
    issues: tuple[NormalizationIssue, ...]
    vintages: tuple[StatementVintage, ...]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    entity_cik: str
    entity_name: str
    as_of: datetime
    recorded_at: datetime
    computed_at: datetime
    knowledge_clock: KnowledgeClock
    vintage_policy: VintagePolicy
    mapping_version: str
    mapping_available_at: datetime
    detector_pack_version: str
    detector_pack_available_at: datetime
    source_scope: str
    source_limitations: tuple[str, ...]
    coverage: Coverage
    filings: tuple[SourceFiling, ...]
    fact_occurrences: tuple[FactOccurrence, ...]
    issues: tuple[NormalizationIssue, ...]
    observations: tuple[NormalizedObservation, ...]
    statement_vintages: tuple[StatementVintage, ...]
    selected_vintage_ids: tuple[str, ...]
    findings: tuple[Finding, ...]
    schema: str = RUN_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "entity_cik": self.entity_cik,
            "entity_name": self.entity_name,
            "as_of": utc_text(self.as_of),
            "recorded_at": utc_text(self.recorded_at),
            "computed_at": utc_text(self.computed_at),
            "knowledge_clock": self.knowledge_clock.value,
            "vintage_policy": self.vintage_policy.value,
            "mapping_version": self.mapping_version,
            "mapping_available_at": utc_text(self.mapping_available_at),
            "detector_pack_version": self.detector_pack_version,
            "detector_pack_available_at": utc_text(self.detector_pack_available_at),
            "source_scope": self.source_scope,
            "source_limitations": list(self.source_limitations),
            "coverage": self.coverage.to_dict(),
            "filings": [item.to_dict() for item in self.filings],
            "fact_occurrences": [item.to_dict() for item in self.fact_occurrences],
            "issues": [item.to_dict() for item in self.issues],
            "observations": [item.to_dict() for item in self.observations],
            "statement_vintages": [item.to_dict() for item in self.statement_vintages],
            "selected_vintage_ids": list(self.selected_vintage_ids),
            "findings": [item.to_dict() for item in self.findings],
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())
