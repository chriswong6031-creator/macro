"""Tests for direct-tag mapping, ambiguity handling, and statement vintages."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from engine.fundamental_forensics import KnowledgeClock, VintagePolicy, load_registry
from engine.fundamental_forensics.normalize import (
    normalize_companyfacts,
    select_statement_vintages,
)
from engine.fundamental_forensics.sec_companyfacts import ingest_companyfacts


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
REGISTRY = ROOT / "config" / "fundamental_forensics.yml"
RECORDED_AT = "2026-08-01T12:00:00Z"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _normalized(companyfacts=None):
    bundle = ingest_companyfacts(
        companyfacts or _load("companyfacts_versions.json"),
        _load("submissions_versions.json"),
        recorded_at=RECORDED_AT,
    )
    registry = load_registry(REGISTRY)
    return bundle, registry, normalize_companyfacts(bundle, registry)


def test_alias_agreement_uses_priority_and_retains_every_evidence_fact() -> None:
    _, registry, normalized = _normalized()
    observation = next(
        item for item in normalized.observations
        if item.metric == "revenue"
        and item.period_end == "2022-12-31"
        and item.accession == "0000000001-23-000001"
    )
    assert observation.value == "1000"
    assert observation.mapping_tier == "A"
    assert observation.mapping_rule_id.endswith(
        ":RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert observation.mapping_version == registry.mapping_version
    assert len(observation.fact_ids) == 2  # primary occurrence + agreeing Tier-B alias


def test_recast_is_a_second_accession_coherent_statement_vintage() -> None:
    _, registry, normalized = _normalized()
    vintages = [item for item in normalized.vintages if item.period_end == "2023-12-31"]
    assert {item.accession for item in vintages} == {
        "0000000001-24-000001",
        "0000000001-25-000001",
    }
    observations = {item.observation_id: item for item in normalized.observations}
    for vintage in vintages:
        assert all(
            observations[observation_id].accession == vintage.accession
            for observation_id in vintage.metrics().values()
        )

    before_recast = select_statement_vintages(
        normalized,
        registry,
        as_of="2024-12-31T23:59:59Z",
        knowledge_clock=KnowledgeClock.SOURCE_EVENT,
        vintage_policy=VintagePolicy.LATEST_KNOWN,
    )
    assert next(item for item in before_recast if item.period_end == "2023-12-31").accession == (
        "0000000001-24-000001"
    )

    first = select_statement_vintages(
        normalized,
        registry,
        as_of="2025-12-31T23:59:59Z",
        knowledge_clock="source_event",
        vintage_policy="first_reported",
    )
    latest = select_statement_vintages(
        normalized,
        registry,
        as_of="2025-12-31T23:59:59Z",
        knowledge_clock="source_event",
        vintage_policy="latest_known",
    )
    assert next(item for item in first if item.period_end == "2023-12-31").accession == (
        "0000000001-24-000001"
    )
    assert next(item for item in latest if item.period_end == "2023-12-31").accession == (
        "0000000001-25-000001"
    )


def test_recorded_clock_is_distinct_from_source_event_clock() -> None:
    _, registry, normalized = _normalized()
    before_recording = select_statement_vintages(
        normalized,
        registry,
        as_of="2026-08-01T11:59:59Z",
        knowledge_clock="recorded",
        vintage_policy="latest_known",
    )
    after_recording = select_statement_vintages(
        normalized,
        registry,
        as_of="2026-08-01T12:00:01Z",
        knowledge_clock="recorded",
        vintage_policy="latest_known",
    )
    assert before_recording == ()
    assert {item.period_end for item in after_recording} == {
        "2022-12-31", "2023-12-31", "2024-12-31"
    }


def test_conflicting_aliases_fail_closed_with_issue_and_no_observation() -> None:
    payload = _load("companyfacts_versions.json")
    payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["val"] = 999
    _, _, normalized = _normalized(payload)
    issue = next(item for item in normalized.issues if item.metric == "revenue")
    assert issue.code == "ambiguous_metric"
    assert len(issue.fact_ids) == 2
    assert not any(
        item.metric == "revenue"
        and item.period_end == "2022-12-31"
        and item.accession == "0000000001-23-000001"
        for item in normalized.observations
    )


def test_unit_duration_form_and_custom_taxonomy_are_out_of_scope() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    revenue = payload["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]["units"]
    revenue["EUR"] = [{
        "start": "2024-01-01", "end": "2024-12-31", "val": 9999,
        "accn": "0000000001-25-000001", "fy": 2024, "fp": "FY",
        "form": "10-K", "filed": "2025-02-15"
    }]
    revenue["USD"].append({
        "start": "2024-10-01", "end": "2024-12-31", "val": 9999,
        "accn": "0000000001-25-000001", "fy": 2024, "fp": "Q4",
        "form": "10-K", "filed": "2025-02-15"
    })
    bundle, _, normalized = _normalized(payload)
    current = [
        item for item in normalized.observations
        if item.metric == "revenue" and item.period_end == "2024-12-31"
    ]
    assert len(current) == 1 and current[0].value == "1120" and current[0].unit == "USD"
    assert any(fact.taxonomy == "fixture" for fact in bundle.facts)
    assert all(item.metric != "CustomerCount" for item in normalized.observations)
