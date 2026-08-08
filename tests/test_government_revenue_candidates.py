from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    build_candidate_queue,
    build_mapping_backlog,
    candidate_queue_content_id,
    is_valid_candidate_payload,
    is_valid_candidate_queue,
)


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
KNOWN_AT = "2026-08-02T12:00:00+00:00"
EFFECTIVE_AT = "2026-08-01T12:00:00+00:00"
GENERATED_AT = "2026-08-03T07:00:00+00:00"


def _graph() -> dict:
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.1.0",
        "graph_id": "recipient-graph:test-noc",
        "graph_known_at": "2026-08-02T00:00:00+00:00",
        "graph_effective_at": "2026-08-02T00:00:00+00:00",
        "evidence": [
            {
                "evidence_id": "evidence:noc",
                "source_ref": f"recipient-evidence:sha256:{SHA_A}",
                "publisher": "SEC",
                "evidence_class": "official_filing",
                "record_id": "0000000000-26-000001",
                "url": "https://www.sec.gov/Archives/edgar/data/1/test.htm",
                "content_sha256": SHA_A,
                "byte_length": 100,
                "retrieved_at": "2026-08-01T00:00:00+00:00",
                "claim_scopes": [
                    "public_company", "legal_entity", "exact_identifier", "ownership",
                ],
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
            }
        ],
        "companies": [
            {
                "company_id": "issuer:noc",
                "ticker": "NOC",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "legal_entities": [
            {
                "entity_id": "entity:noc",
                "canonical_name": "Northrop Grumman Systems Corporation",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "identifiers": [
            {
                "identifier_id": "identifier:noc",
                "entity_id": "entity:noc",
                "namespace": "sam_uei",
                "value": "ABCDEFGHJKLM",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "ownership_edges": [
            {
                "edge_id": "edge:noc",
                "child_entity_id": "entity:noc",
                "parent_company_id": "issuer:noc",
                "relationship": "wholly_owned",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }


def _ownership_path() -> list[dict]:
    return [
        {
            "edge_id": "edge:noc",
            "child_entity_id": "entity:noc",
            "parent_company_id": "issuer:noc",
            "relationship": "wholly_owned",
            "economic_share": 1.0,
            "known_at": "2026-08-01T00:00:00+00:00",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": None,
            "evidence_refs": ["evidence:noc"],
        }
    ]


def _award_event(*, event_type: str = "obligation", late: bool = False) -> dict:
    return {
        "kind": "award_change",
        "event_id": "govawd-noc-001",
        "record_id": "CONT_AWD_TEST_001",
        "change": {
            "type": event_type,
            "effective_at": EFFECTIVE_AT,
            "known_at": KNOWN_AT,
            "what_changed_en": "Official obligation increase observed",
        },
        "award_change": {
            "event_type": event_type,
            "source_rail": "usaspending_award_action",
            "source_identity": {"id": "action:1", "version": "1", "content_sha256": SHA_B},
            "is_late_discovery": late,
        },
        "primary_amount_id": "amount:obligation",
        "amounts": [
            {
                "id": "amount:obligation",
                "value": 125000000.0,
                "currency": "USD",
                "semantic": "federal_action_obligation_delta",
                "as_of": EFFECTIVE_AT,
                "source_ref": "receipt:action:1",
            }
        ],
        "listed_company_impacts": [
            {
                "ticker": "NOC",
                "company_name": "Northrop Grumman Corporation",
                "issuer_company_id": "issuer:noc",
                "relation_semantic": "reviewed",
                "resolution_state": "reviewed",
                "ownership_path": _ownership_path(),
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "reviewed",
            "conflicts": [],
            "receipts": [
                {
                    "ref_id": "receipt:action:1",
                    "publisher": "U.S. Treasury, USAspending.gov",
                    "record_id": "CONT_AWD_TEST_001",
                    "url": "https://api.usaspending.gov/api/v2/transactions/",
                    "effective_at": EFFECTIVE_AT,
                    "known_at": KNOWN_AT,
                    "retrieved_at": KNOWN_AT,
                    "content_sha256": SHA_B,
                }
            ],
        },
    }


def _payload(event: dict | None = None) -> dict:
    return {
        "as_of": "2026-08-03",
        "known_at": KNOWN_AT,
        "companies": [
            {
                "ticker": "NOC",
                "name": "Northrop Grumman Corporation",
                "entity_match": {"method": "curated_fuzzy_name"},
            },
            {
                "ticker": "LMT",
                "name": "Lockheed Martin Corporation",
                "entity_match": {"method": "curated_fuzzy_name"},
            },
        ],
        "procurement_workspace": {
            "bundle_id": "grw2-1234567890abcdef12345678",
            "freshness": {"award_events": {"status": "ok"}},
            "events": [event] if event is not None else [],
        },
    }


def test_current_truth_is_zero_candidates_with_twenty_one_mapping_rows() -> None:
    latest = json.loads((ROOT / "data/government_revenue/latest.json").read_text(encoding="utf-8"))
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text(encoding="utf-8"))

    queue = build_candidate_queue(latest, graph, generated_at=GENERATED_AT)

    assert queue["counts"]["total"] == 0
    assert queue["counts"]["mapping_needed"] == 21
    assert len(queue["mapping_backlog"]) == 21
    # "not_observed", not "unavailable", since 2026-08-08: the SAM opportunity
    # evidence commits (18:01Z/20:27Z) brought the award-event rail to status
    # "ok", and candidates.py:948 reads a healthy rail with zero eligible
    # candidates as not_observed (rail fine, nothing to see) rather than
    # unavailable (rail down). Current-truth pin — re-pin deliberately when the
    # rail state moves, in the PR that moves it.
    assert queue["freshness"]["exact_candidate_availability"] == "not_observed"
    assert queue["coverage"]["reviewed_issuer_company_count"] == 1
    assert queue["coverage"]["reviewed_issuer_tickers"] == ["PLTR"]
    assert next(
        row for row in queue["mapping_backlog"] if row["ticker"] == "PLTR"
    )["mapping_state"] == "partial_identifier_coverage"
    assert all(row["issuer_attribution"] == "not_asserted" for row in queue["mapping_backlog"])
    assert is_valid_candidate_queue(queue)


def test_exact_receipt_bound_reviewed_event_builds_one_context_candidate() -> None:
    candidate_rows = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)

    assert len(candidate_rows) == 1
    candidate = candidate_rows[0]
    assert candidate["candidate_family"] == "award_obligation_change"
    assert candidate["ticker"] == "NOC"
    assert candidate["materiality"] == {
        "observed_event_amount": 125000000.0,
        "attributable_amount": 125000000.0,
        "economic_share": 1.0,
        "issuer_attributed_denominator": None,
        "materiality_ratio": None,
        "comparison_state": "not_comparable",
        "reason_code": "exact_issuer_attributed_denominator_not_available",
    }
    assert candidate["authority"]["can_originate_signal"] is False
    assert candidate["authority"]["can_add_candidates"] is False
    assert SHA_A in candidate["artifact_content_ids"]
    assert is_valid_candidate_payload(candidate)


@pytest.mark.parametrize(
    ("event_type", "expected_family", "expected_direction"),
    [
        ("obligation", "award_obligation_change", "possible_positive"),
        ("deobligation", "award_obligation_change", "possible_negative"),
        ("ceiling_changed", "award_ceiling_change", "possible_positive"),
        ("option_exercised", "option_exercise", "possible_positive"),
        ("new_award", "new_award", "possible_positive"),
    ],
)
def test_supported_event_families_have_exact_reviewed_candidate_mapping(
    event_type: str, expected_family: str, expected_direction: str
) -> None:
    candidate = build_candidate_observations(
        _payload(_award_event(event_type=event_type)), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["candidate_family"] == expected_family
    assert candidate["transmission_direction"] == expected_direction
    assert candidate["is_neuralweb_trade_candidate"] is False


@pytest.mark.parametrize(
    ("mutation", "description"),
    [
        (lambda event: event["evidence"].update({"mapping_class": "deterministic_inference"}), "fuzzy mapping"),
        (lambda event: event["evidence"].update({"receipts": []}), "missing receipt"),
        (lambda event: event["award_change"].update({"is_late_discovery": True}), "late new award"),
        (lambda event: event["listed_company_impacts"][0].update({"ownership_path": []}), "missing ownership path"),
    ],
)
def test_candidate_engine_fails_closed_when_exact_eligibility_breaks(mutation, description: str) -> None:
    event = _award_event(event_type="new_award")
    mutation(event)

    assert build_candidate_observations(_payload(event), _graph(), generated_at=GENERATED_AT) == [], description


def test_candidate_known_at_waits_for_every_graph_and_receipt_claim() -> None:
    graph = _graph()
    graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    graph["companies"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["ownership_edges"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["legal_entities"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["identifiers"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["evidence"][0]["known_at"] = "2026-08-02T18:00:00+00:00"

    candidate = build_candidate_observations(
        _payload(_award_event()), graph, generated_at=GENERATED_AT
    )[0]

    assert candidate["source_event"]["known_at"] == KNOWN_AT
    assert candidate["known_at"] == "2026-08-02T18:00:00+00:00"


def test_candidate_rejects_unverified_impact_evidence_reference() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["evidence_refs"] = ["unverified-future-proof"]

    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_candidate_known_at_waits_for_impact_specific_graph_evidence() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["evidence_refs"] = ["evidence:impact-later"]
    graph = _graph()
    graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    graph["evidence"].append({
        "evidence_id": "evidence:impact-later",
        "source_ref": f"recipient-evidence:sha256:{SHA_B}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-26-000002",
        "url": "https://www.sec.gov/Archives/edgar/data/1/impact-later.htm",
        "content_sha256": SHA_B,
        "byte_length": 101,
        "retrieved_at": "2026-08-02T18:00:00+00:00",
        "claim_scopes": ["public_company"],
        "known_at": "2026-08-02T18:00:00+00:00",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_to": None,
    })

    candidate = build_candidate_observations(
        _payload(event), graph, generated_at=GENERATED_AT
    )[0]

    assert candidate["known_at"] == "2026-08-02T18:00:00+00:00"
    assert "evidence:impact-later" in candidate["issuer_resolution_ref"]["evidence_refs"]


def test_candidate_accepts_exact_official_receipt_url_as_impact_evidence() -> None:
    event = _award_event()
    receipt_url = event["evidence"]["receipts"][0]["url"]
    event["listed_company_impacts"][0]["evidence_refs"] = [receipt_url]

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert receipt_url in candidate["issuer_resolution_ref"]["evidence_refs"]


def test_graph_revision_creates_a_new_immutable_observation_identity() -> None:
    event = _award_event()
    first_graph = _graph()
    second_graph = _graph()
    second_graph["graph_id"] = "recipient-graph:test-noc-revised"
    second_graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    second_graph["evidence"].append({
        "evidence_id": "evidence:noc-revision",
        "source_ref": f"recipient-evidence:sha256:{'c' * 64}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-26-000003",
        "url": "https://www.sec.gov/Archives/edgar/data/1/revision.htm",
        "content_sha256": "c" * 64,
        "byte_length": 102,
        "retrieved_at": "2026-08-02T18:00:00+00:00",
        "claim_scopes": ["public_company"],
        "known_at": "2026-08-02T18:00:00+00:00",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_to": None,
    })
    second_graph["companies"][0]["evidence_refs"].append("evidence:noc-revision")
    second_graph["companies"][0]["known_at"] = "2026-08-02T18:00:00+00:00"

    first = build_candidate_observations(_payload(event), first_graph, generated_at=GENERATED_AT)[0]
    second = build_candidate_observations(_payload(event), second_graph, generated_at=GENERATED_AT)[0]

    assert first["candidate_id"] == second["candidate_id"]
    assert first["observation_id"] != second["observation_id"]
    assert first["issuer_resolution_ref"]["graph_digest"] != second["issuer_resolution_ref"]["graph_digest"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["listed_company_impacts"][0]["ownership_path"][0].update(
            {"parent_company_id": "issuer:lmt"}
        ),
        lambda event: event["listed_company_impacts"][0]["ownership_path"][0].update(
            {"economic_share": 0.5}
        ),
        lambda event: event["evidence"]["receipts"][0].update(
            {"record_id": "UNRELATED_AWARD"}
        ),
        lambda event: event["award_change"]["source_identity"].update(
            {"content_sha256": "c" * 64}
        ),
        lambda event: event["amounts"][0].update(
            {"source_ref": "receipt:unrelated"}
        ),
    ],
)
def test_candidate_rechecks_graph_path_and_receipt_binding(mutation) -> None:
    event = _award_event()
    mutation(event)

    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_mapping_backlog_keeps_fuzzy_discovery_out_of_issuer_attribution() -> None:
    backlog = build_mapping_backlog(_payload(), _graph())

    assert [row["ticker"] for row in backlog] == ["LMT", "NOC"]
    assert backlog[0]["source_association_method"] == "curated_fuzzy_name"
    assert backlog[0]["issuer_attribution"] == "not_asserted"
    assert "exact_identifier_mapping_required" in backlog[0]["reason_codes"]
    assert backlog[1]["mapping_state"] == "partial_identifier_coverage"
    assert backlog[1]["reason_codes"] == ["partial_identifier_coverage"]


def test_candidate_schema_rejects_trade_authority_or_borrowed_materiality_ratio() -> None:
    candidate = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)[0]
    authority_mutation = deepcopy(candidate)
    authority_mutation["authority"]["can_gate"] = True
    ratio_mutation = deepcopy(candidate)
    ratio_mutation["materiality"]["materiality_ratio"] = 0.1

    assert not is_valid_candidate_payload(authority_mutation)
    assert not is_valid_candidate_payload(ratio_mutation)


def test_queue_is_deterministic_and_never_an_investment_rank() -> None:
    first = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    second = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)

    assert first == second
    assert first["counts"]["exact_linked"] == 1
    assert first["counts"]["mapping_needed"] == 2
    assert first["coverage"]["reviewed_issuer_tickers"] == ["NOC"]
    assert first["display_sort"]["is_investment_rank"] is False
    assert first["authority"]["can_rank"] is False


def test_queue_content_id_excludes_delivery_clock_but_detects_data_mutation() -> None:
    queue = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    regenerated = deepcopy(queue)
    regenerated["generated_at"] = "2026-08-04T07:00:00+00:00"
    regenerated["candidates"][0]["generated_at"] = "2026-08-04T07:00:00+00:00"

    assert candidate_queue_content_id(regenerated) == queue["content_id"]
    assert is_valid_candidate_queue(regenerated)

    mutated = deepcopy(queue)
    mutated["candidates"][0]["ticker"] = "LMT"
    assert not is_valid_candidate_queue(mutated)
