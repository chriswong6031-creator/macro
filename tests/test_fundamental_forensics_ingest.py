"""Fixture tests for immutable SEC Company Facts ingestion."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from engine.fundamental_forensics.models import canonical_json
from engine.fundamental_forensics.sec_companyfacts import ingest_companyfacts


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
RECORDED_AT = "2026-08-01T12:00:00Z"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _bundle(companyfacts=None, submissions=None):
    return ingest_companyfacts(
        companyfacts or _load("companyfacts_versions.json"),
        submissions or _load("submissions_versions.json"),
        recorded_at=RECORDED_AT,
    )


def test_versions_survive_and_exact_duplicate_coalesces() -> None:
    bundle = _bundle()
    revenue = [
        fact for fact in bundle.facts
        if fact.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
        and fact.period_end == "2023-12-31"
    ]
    assert {(fact.accession, fact.value) for fact in revenue} == {
        ("0000000001-24-000001", "1050"),
        ("0000000001-25-000001", "1060"),
    }
    original = next(
        fact for fact in bundle.facts
        if fact.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
        and fact.period_end == "2022-12-31"
    )
    assert original.source_record_count == 2
    assert sum(fact.source_record_count for fact in bundle.facts) == len(bundle.facts) + 1


def test_acceptance_clock_is_joined_and_missing_join_fails_closed() -> None:
    bundle = _bundle()
    known = next(fact for fact in bundle.facts if fact.accession == "0000000001-23-000001")
    assert known.source_event_at.isoformat() == "2023-02-15T16:00:00+00:00"
    assert known.recorded_at.isoformat() == "2026-08-01T12:00:00+00:00"
    assert known.pit_eligible is True

    missing = next(fact for fact in bundle.facts if fact.taxonomy == "fixture")
    assert missing.source_event_at is None
    assert missing.filing_id is None
    assert missing.pit_eligible is False
    assert missing.filed == "2025-03-01"  # preserved, never promoted to an event clock


def test_input_array_order_does_not_change_ids_or_canonical_facts() -> None:
    companyfacts = _load("companyfacts_versions.json")
    submissions = _load("submissions_versions.json")
    shuffled_facts = deepcopy(companyfacts)
    for concepts in shuffled_facts["facts"].values():
        for concept in concepts.values():
            for entries in concept["units"].values():
                entries.reverse()
    shuffled_submissions = deepcopy(submissions)
    for values in shuffled_submissions["filings"]["recent"].values():
        if isinstance(values, list):
            values.reverse()

    left = _bundle(companyfacts, submissions)
    right = _bundle(shuffled_facts, shuffled_submissions)
    assert [fact.fact_id for fact in left.facts] == [fact.fact_id for fact in right.facts]
    assert canonical_json([fact.to_dict() for fact in left.facts]) == canonical_json(
        [fact.to_dict() for fact in right.facts]
    )
    assert [filing.filing_id for filing in left.filings] == [filing.filing_id for filing in right.filings]


def test_ids_are_full_sha256_and_cik_is_canonical() -> None:
    bundle = _bundle()
    assert bundle.entity_cik == "0000000001"
    assert all(len(fact.fact_id.removeprefix("fact_")) == 64 for fact in bundle.facts)
    assert all(len(filing.filing_id.removeprefix("filing_")) == 64 for filing in bundle.filings)
