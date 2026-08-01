"""One deterministic public pipeline for the Fundamental Forensics fixture slice."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .detectors import evaluate_detectors
from .models import (
    Coverage,
    FindingState,
    KnowledgeClock,
    RunResult,
    VintagePolicy,
    parse_utc,
    stable_id,
)
from .normalize import (
    ForensicsRegistry,
    normalize_companyfacts,
    registry_from_dict,
    select_statement_vintages,
)
from .sec_companyfacts import ingest_companyfacts


SOURCE_SCOPE = "sec_companyfacts_standard_entitywide_annual_v1"
SOURCE_LIMITATIONS = (
    "company_facts_omits_custom_taxonomy_facts",
    "company_facts_omits_dimensions_and_context_ids",
    "company_facts_omits_reported_decimals_and_filing_source_spans",
    "sec_acceptance_is_a_source_event_clock_not_direct_collector_observation",
)


def run_fixture_slice(
    companyfacts: Mapping[str, Any],
    submissions: Mapping[str, Any],
    registry: ForensicsRegistry | Mapping[str, Any],
    *,
    as_of: str | datetime,
    recorded_at: str | datetime,
    computed_at: str | datetime,
    knowledge_clock: KnowledgeClock | str = KnowledgeClock.SOURCE_EVENT,
    vintage_policy: VintagePolicy | str = VintagePolicy.LATEST_KNOWN,
) -> RunResult:
    """Run the pure PR-1 kernel with no implicit clock, I/O, or network access."""
    config = registry if isinstance(registry, ForensicsRegistry) else registry_from_dict(registry)
    as_of_time = parse_utc(as_of, field="as_of")
    recorded_time = parse_utc(recorded_at, field="recorded_at")
    computed_time = parse_utc(computed_at, field="computed_at")
    if as_of_time is None or recorded_time is None or computed_time is None:
        raise ValueError("as_of, recorded_at, and computed_at are required")
    clock = KnowledgeClock(knowledge_clock)
    policy = VintagePolicy(vintage_policy)

    ingested = ingest_companyfacts(
        companyfacts,
        submissions,
        recorded_at=recorded_time,
    )
    normalized = normalize_companyfacts(ingested, config)
    selected = select_statement_vintages(
        normalized,
        config,
        as_of=as_of_time,
        knowledge_clock=clock,
        vintage_policy=policy,
    )
    detector_rules_eligible = (
        clock is KnowledgeClock.SOURCE_EVENT
        or config.detector_pack_available_at <= as_of_time
    )
    findings = evaluate_detectors(
        normalized.observations,
        selected,
        config,
        computed_at=computed_time,
        detector_rules_eligible=detector_rules_eligible,
        entity_cik=ingested.entity_cik,
    )

    states = [item.state for item in findings]
    coverage = Coverage(
        source_fact_records=sum(item.source_record_count for item in ingested.facts),
        distinct_fact_occurrences=len(ingested.facts),
        facts_with_source_clock=sum(item.source_event_at is not None for item in ingested.facts),
        normalized_observations=len(normalized.observations),
        normalization_issues=len(normalized.issues),
        statement_vintages=len(normalized.vintages),
        selected_statement_vintages=len(selected),
        findings_triggered=states.count(FindingState.TRIGGERED),
        findings_clear=states.count(FindingState.CLEAR),
        findings_not_evaluable=states.count(FindingState.NOT_EVALUABLE),
    )
    selected_ids = tuple(item.vintage_id for item in selected)
    limitations = list(SOURCE_LIMITATIONS)
    if clock is KnowledgeClock.SOURCE_EVENT:
        limitations.append("source_event_replay_uses_the_supplied_current_rule_versions")
    source_limitations = tuple(sorted(limitations))
    run_id = stable_id(
        "ffrun",
        ingested.entity_cik,
        as_of_time,
        recorded_time,
        computed_time,
        clock.value,
        policy.value,
        config.mapping_version,
        config.detector_pack_version,
        tuple(item.fact_id for item in ingested.facts),
        tuple(item.observation_id for item in normalized.observations),
        tuple(item.issue_id for item in normalized.issues),
        selected_ids,
        tuple(item.finding_id for item in findings),
    )
    return RunResult(
        run_id=run_id,
        entity_cik=ingested.entity_cik,
        entity_name=ingested.entity_name,
        as_of=as_of_time,
        recorded_at=recorded_time,
        computed_at=computed_time,
        knowledge_clock=clock,
        vintage_policy=policy,
        mapping_version=config.mapping_version,
        mapping_available_at=config.mapping_available_at,
        detector_pack_version=config.detector_pack_version,
        detector_pack_available_at=config.detector_pack_available_at,
        source_scope=SOURCE_SCOPE,
        source_limitations=source_limitations,
        coverage=coverage,
        filings=ingested.filings,
        fact_occurrences=ingested.facts,
        issues=normalized.issues,
        observations=normalized.observations,
        statement_vintages=normalized.vintages,
        selected_vintage_ids=selected_ids,
        findings=findings,
    )
