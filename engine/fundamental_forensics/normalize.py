"""Versioned, fail-closed normalization for the Company Facts fixture slice."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import (
    IngestBundle,
    KnowledgeClock,
    NormalizationIssue,
    NormalizationResult,
    NormalizedObservation,
    StatementVintage,
    VintagePolicy,
    parse_utc,
    stable_id,
)


ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
MIN_ANNUAL_DAYS = 300
MAX_ANNUAL_DAYS = 400


@dataclass(frozen=True)
class ConceptAlias:
    taxonomy: str
    concept: str
    tier: str
    priority: int


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    period_type: str
    units: tuple[str, ...]
    aliases: tuple[ConceptAlias, ...]


@dataclass(frozen=True)
class DetectorSpec:
    detector_id: str
    order: int
    formula: str
    thresholds: tuple[tuple[str, str], ...]

    def threshold_map(self) -> dict[str, str]:
        return dict(self.thresholds)


@dataclass(frozen=True)
class ForensicsRegistry:
    schema: str
    mapping_version: str
    mapping_available_at: datetime
    detector_pack_version: str
    detector_pack_available_at: datetime
    metrics: tuple[MetricSpec, ...]
    detectors: tuple[DetectorSpec, ...]

    def metric(self, name: str) -> MetricSpec:
        return next(item for item in self.metrics if item.metric == name)

    def detector(self, name: str) -> DetectorSpec:
        return next(item for item in self.detectors if item.detector_id == name)


def registry_from_dict(raw: Mapping[str, Any]) -> ForensicsRegistry:
    metrics: list[MetricSpec] = []
    for metric, spec in sorted((raw.get("metrics") or {}).items()):
        aliases = tuple(
            ConceptAlias(
                taxonomy=str(alias["taxonomy"]),
                concept=str(alias["concept"]),
                tier=str(alias["tier"]),
                priority=int(alias["priority"]),
            )
            for alias in spec.get("aliases", [])
        )
        metrics.append(
            MetricSpec(
                metric=str(metric),
                period_type=str(spec["period_type"]),
                units=tuple(str(unit) for unit in spec.get("units", [])),
                aliases=aliases,
            )
        )

    detectors: list[DetectorSpec] = []
    for detector_id, spec in (raw.get("detectors") or {}).items():
        thresholds = tuple(
            sorted((str(key), str(value)) for key, value in (spec.get("thresholds") or {}).items())
        )
        detectors.append(
            DetectorSpec(
                detector_id=str(detector_id),
                order=int(spec["order"]),
                formula=str(spec["formula"]),
                thresholds=thresholds,
            )
        )
    detectors.sort(key=lambda item: (item.order, item.detector_id))

    mapping_available = parse_utc(raw.get("mapping_available_at"), field="mapping_available_at")
    detector_available = parse_utc(
        raw.get("detector_pack_available_at"), field="detector_pack_available_at"
    )
    if mapping_available is None or detector_available is None:
        raise ValueError("registry rule availability timestamps are required")
    return ForensicsRegistry(
        schema=str(raw["schema"]),
        mapping_version=str(raw["mapping_version"]),
        mapping_available_at=mapping_available,
        detector_pack_version=str(raw["detector_pack_version"]),
        detector_pack_available_at=detector_available,
        metrics=tuple(metrics),
        detectors=tuple(detectors),
    )


def load_registry(path: str | Path) -> ForensicsRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("fundamental-forensics registry must be an object")
    return registry_from_dict(raw)


def _duration_days(start: str | None, end: str) -> int | None:
    if not start:
        return None
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def _fact_matches_metric(fact, metric: MetricSpec, *, filing_form: str | None) -> bool:
    form = fact.form or filing_form
    if form not in ANNUAL_FORMS or fact.unit not in metric.units:
        return False
    if metric.period_type == "duration":
        days = _duration_days(fact.period_start, fact.period_end)
        return days is not None and MIN_ANNUAL_DAYS <= days <= MAX_ANNUAL_DAYS
    if metric.period_type == "instant":
        return fact.period_start is None
    raise ValueError(f"unsupported period type for {metric.metric}: {metric.period_type}")


def normalize_companyfacts(bundle: IngestBundle, registry: ForensicsRegistry) -> NormalizationResult:
    """Map direct standard facts while retaining every accession vintage.

    Alias disagreement is not resolved by priority.  Priority chooses the label
    only after all matching aliases agree on value, unit, and period context.
    """
    alias_index: defaultdict[tuple[str, str], list[tuple[MetricSpec, ConceptAlias]]] = defaultdict(list)
    for metric in registry.metrics:
        for alias in metric.aliases:
            alias_index[(alias.taxonomy, alias.concept)].append((metric, alias))

    filing_forms = {item.filing_id: item.form for item in bundle.filings}
    groups: defaultdict[
        tuple[str, str, str, str], list[tuple[Any, ConceptAlias]]
    ] = defaultdict(list)
    for fact in bundle.facts:
        if not fact.accession:
            continue
        for metric, alias in alias_index.get((fact.taxonomy, fact.concept), []):
            if _fact_matches_metric(fact, metric, filing_form=filing_forms.get(fact.filing_id)):
                groups[(metric.metric, fact.entity_cik, fact.accession, fact.period_end)].append(
                    (fact, alias)
                )

    observations: list[NormalizedObservation] = []
    issues: list[NormalizationIssue] = []
    metric_by_name = {item.metric: item for item in registry.metrics}
    for group_key in sorted(groups):
        metric_name, entity_cik, accession, period_end = group_key
        candidates = groups[group_key]
        fact_ids = tuple(sorted({fact.fact_id for fact, _ in candidates}))
        semantic_values = {
            (fact.value, fact.unit, fact.period_start, fact.period_end) for fact, _ in candidates
        }
        if len(semantic_values) != 1:
            issue_id = stable_id(
                "normissue", registry.mapping_version, metric_name, entity_cik, accession,
                period_end, fact_ids,
            )
            issues.append(
                NormalizationIssue(
                    issue_id=issue_id,
                    code="ambiguous_metric",
                    metric=metric_name,
                    entity_cik=entity_cik,
                    accession=accession,
                    period_end=period_end,
                    fact_ids=fact_ids,
                    detail="matching standard concepts disagree on value, unit, or period context",
                )
            )
            continue

        chosen_fact, chosen_alias = min(
            candidates, key=lambda item: (item[1].priority, item[1].concept, item[0].fact_id)
        )
        metric = metric_by_name[metric_name]
        source_times = [fact.source_event_at for fact, _ in candidates if fact.source_event_at]
        recorded_times = [fact.recorded_at for fact, _ in candidates]
        mapping_rule_id = (
            f"{metric_name}:{chosen_alias.taxonomy}:{chosen_alias.concept}"
        )
        observation_id = stable_id(
            "observation",
            registry.mapping_version,
            metric_name,
            entity_cik,
            accession,
            chosen_fact.period_start,
            chosen_fact.period_end,
            chosen_fact.unit,
            chosen_fact.value,
            fact_ids,
        )
        observations.append(
            NormalizedObservation(
                observation_id=observation_id,
                entity_cik=entity_cik,
                metric=metric_name,
                value=chosen_fact.value,
                unit=chosen_fact.unit,
                period_type=metric.period_type,
                period_start=chosen_fact.period_start,
                period_end=chosen_fact.period_end,
                accession=accession,
                source_event_at=max(source_times) if source_times else None,
                recorded_at=max(recorded_times),
                mapping_version=registry.mapping_version,
                mapping_rule_id=mapping_rule_id,
                mapping_tier=chosen_alias.tier,
                mapping_rule_available_at=registry.mapping_available_at,
                fact_ids=fact_ids,
            )
        )

    observations.sort(key=lambda item: item.observation_id)
    issues.sort(key=lambda item: item.issue_id)

    vintage_groups: defaultdict[tuple[str, str, str], list[NormalizedObservation]] = defaultdict(list)
    for observation in observations:
        vintage_groups[
            (observation.entity_cik, observation.accession, observation.period_end)
        ].append(observation)

    vintages: list[StatementVintage] = []
    for (entity_cik, accession, period_end), items in sorted(vintage_groups.items()):
        metric_refs = tuple(sorted((item.metric, item.observation_id) for item in items))
        source_times = [item.source_event_at for item in items if item.source_event_at]
        recorded_at = max(item.recorded_at for item in items)
        vintage_id = stable_id(
            "vintage", registry.mapping_version, entity_cik, accession, period_end, metric_refs
        )
        vintages.append(
            StatementVintage(
                vintage_id=vintage_id,
                entity_cik=entity_cik,
                accession=accession,
                period_end=period_end,
                source_event_at=max(source_times) if source_times else None,
                recorded_at=recorded_at,
                metric_observation_ids=metric_refs,
            )
        )
    vintages.sort(key=lambda item: (item.period_end, item.accession, item.vintage_id))
    return NormalizationResult(
        observations=tuple(observations),
        issues=tuple(issues),
        vintages=tuple(vintages),
    )


def select_statement_vintages(
    normalized: NormalizationResult,
    registry: ForensicsRegistry,
    *,
    as_of: str | datetime,
    knowledge_clock: KnowledgeClock | str,
    vintage_policy: VintagePolicy | str,
) -> tuple[StatementVintage, ...]:
    cutoff = parse_utc(as_of, field="as_of")
    if cutoff is None:  # pragma: no cover - guarded by required argument
        raise ValueError("as_of is required")
    clock = KnowledgeClock(knowledge_clock)
    policy = VintagePolicy(vintage_policy)

    eligible: list[StatementVintage] = []
    for vintage in normalized.vintages:
        if clock is KnowledgeClock.SOURCE_EVENT:
            if vintage.source_event_at is None or vintage.source_event_at > cutoff:
                continue
        else:
            if registry.mapping_available_at > cutoff or vintage.recorded_at > cutoff:
                continue
        eligible.append(vintage)

    by_period: defaultdict[str, list[StatementVintage]] = defaultdict(list)
    for vintage in eligible:
        by_period[vintage.period_end].append(vintage)

    selected: list[StatementVintage] = []
    for period_end, vintages in sorted(by_period.items()):
        def order_key(item: StatementVintage):
            event = item.source_event_at or item.recorded_at
            return event, item.accession, item.vintage_id

        ordered = sorted(vintages, key=order_key)
        selected.append(
            ordered[0] if policy is VintagePolicy.FIRST_REPORTED else ordered[-1]
        )
    return tuple(selected)
