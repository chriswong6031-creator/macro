"""Hermetic precision and coverage tests for the P0 recipient-resolution graph."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.government_revenue.entity_resolution import (
    build_entity_coverage,
    coverage_invariants,
    dedupe_source_records,
    resolve_recipient,
    resolve_records,
    source_record_key,
)


CONTRACTS = Path(__file__).parents[1] / "contracts" / "government_revenue"


def _graph(*, edge_known_at: str = "2025-01-01T00:00:00+00:00", edge_valid_from: str = "2020-01-01", overrides=None):
    return {
        "entities": [
            {"entity_id": "le:lmt-sub", "canonical_name": "Lockheed Martin Services, LLC"},
            {"entity_id": "le:cage-sub", "canonical_name": "Boeing CAGE subsidiary"},
            {"entity_id": "le:source-sub", "canonical_name": "Source-ID subsidiary"},
        ],
        "companies": [
            {
                "company_id": "central:LMT",
                "ticker": "LMT",
                "verification_state": "confirmed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:company-lmt"],
            },
            {
                "company_id": "central:BA",
                "ticker": "BA",
                "verification_state": "confirmed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:company-ba"],
            },
            {
                "company_id": "central:NOC",
                "ticker": "NOC",
                "verification_state": "confirmed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:company-noc"],
            },
        ],
        "identifiers": [
            {
                "identifier_id": "id-lmt-uei",
                "entity_id": "le:lmt-sub",
                "namespace": "sam_uei",
                "value": "UEI-LMT-123",
                "verification_state": "confirmed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:uei-lmt"],
            },
            {
                "identifier_id": "id-ba-cage",
                "entity_id": "le:cage-sub",
                "namespace": "cage",
                "value": "1ABC2",
                "verification_state": "confirmed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:cage-ba"],
            },
            {
                "identifier_id": "id-source",
                "entity_id": "le:source-sub",
                "namespace": "usaspending_recipient_id",
                "value": "recipient-42",
                "verification_state": "reviewed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:source-id"],
            },
        ],
        "ownership_edges": [
            {
                "edge_id": "edge-lmt",
                "child_entity_id": "le:lmt-sub",
                "parent_company_id": "central:LMT",
                "relationship": "wholly_owned",
                "confidence_state": "confirmed",
                "known_at": edge_known_at,
                "valid_from": edge_valid_from,
                "evidence_refs": ["evidence:ownership-lmt"],
            },
            {
                "edge_id": "edge-ba",
                "child_entity_id": "le:cage-sub",
                "parent_company_id": "central:BA",
                "relationship": "wholly_owned",
                "confidence_state": "confirmed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:ownership-ba"],
            },
            {
                "edge_id": "edge-source",
                "child_entity_id": "le:source-sub",
                "parent_company_id": "central:NOC",
                "relationship": "wholly_owned",
                "confidence_state": "reviewed",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01",
                "evidence_refs": ["evidence:ownership-source"],
            },
        ],
        "overrides": overrides or [],
    }


def _record(**changes):
    row = {
        "source_award_key": "award-1",
        "recipient_name": "LOCKHEED MARTIN SERVICES, LLC",
        "recipient_uei": "UEI-LMT-123",
        "effective_at": "2026-06-15",
        "known_at": "2026-06-16T12:00:00+00:00",
        "amount": 100.0,
        "discovery_query_id": "query:lmt",
        "source_url": "https://api.usaspending.gov/example",
    }
    row.update(changes)
    return row


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_exact_uei_resolves_only_through_visible_temporal_ownership_path():
    resolved = resolve_recipient(_record(), _graph(), as_of="2026-06-30")

    assert resolved["resolution_state"] == "confirmed"
    assert resolved["resolution_rule"] == "exact_uei"
    assert resolved["recipient_entity_id"] == "le:lmt-sub"
    assert resolved["issuer"] == {"company_id": "central:LMT", "ticker": "LMT"}
    assert resolved["economic_share"] == 1.0
    assert [edge["edge_id"] for edge in resolved["ownership_path"]] == ["edge-lmt"]
    assert set(resolved["evidence_refs"]) == {
        "evidence:uei-lmt",
        "evidence:ownership-lmt",
        "evidence:company-lmt",
    }


@pytest.mark.parametrize(
    ("changes", "issuer", "rule", "state"),
    [
        (
            {"recipient_uei": "unknown", "recipient_cage": "1abc2"},
            "central:BA", "exact_cage", "confirmed",
        ),
        (
            {"recipient_uei": "unknown", "recipient_source_id": "recipient-42"},
            "central:NOC", "exact_source_id", "reviewed",
        ),
    ],
)
def test_exact_identifier_ladder_uses_cage_then_source_id(changes, issuer, rule, state):
    resolved = resolve_recipient(_record(**changes), _graph(), as_of="2026-06-30")

    assert resolved["resolution_state"] == state
    assert resolved["resolution_rule"] == rule
    assert resolved["issuer"]["company_id"] == issuer


def test_name_match_alone_never_creates_issuer_attribution():
    resolved = resolve_recipient(
        _record(recipient_uei=None, recipient_name="Lockheed Martin Corporation"),
        _graph(),
        as_of="2026-06-30",
    )

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["missing_exact_identifier"]


def test_analyst_block_wins_over_an_exact_identifier():
    override = {
        "override_id": "override:block-lmt",
        "action": "block_identifier",
        "namespace": "sam_uei",
        "value": "UEI-LMT-123",
        "reviewer_state": "analyst_approved",
        "known_at": "2026-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:block"],
    }
    resolved = resolve_recipient(_record(), _graph(overrides=[override]), as_of="2026-06-30")

    assert resolved["resolution_state"] == "rejected"
    assert resolved["resolution_rule"] == "analyst_override"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["blocked_by_analyst_override"]


def test_analyst_assert_can_resolve_an_exact_source_id_but_is_labeled_reviewed():
    override = {
        "override_id": "override:source",
        "action": "assert_identifier",
        "namespace": "usaspending_recipient_id",
        "value": "recipient-override",
        "target_entity_id": "le:lmt-sub",
        "reviewer_state": "analyst_approved",
        "known_at": "2026-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:override"],
    }
    record = _record(recipient_uei="unknown", recipient_source_id="recipient-override")
    resolved = resolve_recipient(record, _graph(overrides=[override]), as_of="2026-06-30")

    assert resolved["resolution_state"] == "reviewed"
    assert resolved["resolution_rule"] == "analyst_override"
    assert resolved["issuer"]["ticker"] == "LMT"


def test_visible_analyst_ownership_override_is_temporal_and_never_backfills_replay():
    override = {
        "override_id": "override:ownership",
        "action": "assert_ownership",
        "child_entity_id": "le:lmt-sub",
        "target_company_id": "central:LMT",
        "relationship": "wholly_owned",
        "reviewer_state": "analyst_approved",
        "known_at": "2026-06-20T00:00:00+00:00",
        "valid_from": "2026-01-01",
        "evidence_refs": ["evidence:ownership-override"],
    }
    graph = _graph(overrides=[override])
    graph["ownership_edges"] = [
        edge for edge in graph["ownership_edges"] if edge["edge_id"] != "edge-lmt"
    ]

    before_known = resolve_recipient(_record(), graph, as_of="2026-06-19")
    after_known = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert before_known["resolution_state"] == "unresolved"
    assert before_known["issuer"] is None
    assert after_known["resolution_state"] == "reviewed"
    assert after_known["issuer"]["ticker"] == "LMT"
    assert after_known["ownership_path"][0]["edge_id"] == "override:ownership"


def test_exact_identifier_conflict_fails_closed_without_a_ticker():
    graph = _graph()
    graph["entities"].append({"entity_id": "le:conflict", "canonical_name": "Unrelated Co"})
    graph["identifiers"].append({
        "identifier_id": "id-conflict",
        "entity_id": "le:conflict",
        "namespace": "sam_uei",
        "value": "UEI-LMT-123",
        "verification_state": "confirmed",
        "known_at": "2025-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:conflicting-identifier"],
    })
    graph["ownership_edges"].append({
        "edge_id": "edge-conflict",
        "child_entity_id": "le:conflict",
        "parent_company_id": "central:NOC",
        "relationship": "wholly_owned",
        "confidence_state": "confirmed",
        "known_at": "2025-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:conflicting-ownership"],
    })

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")
    assert resolved["resolution_state"] == "conflicted"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["exact_identifier_maps_to_multiple_entities"]


def test_temporal_ownership_and_knowledge_clocks_prevent_future_parent_leakage():
    effective_before_acquisition = resolve_recipient(
        _record(effective_at="2026-03-01"),
        _graph(edge_valid_from="2026-04-01"),
        as_of="2026-06-30",
    )
    learned_after_replay = resolve_recipient(
        _record(effective_at="2026-06-15"),
        _graph(edge_known_at="2026-07-01T00:00:00+00:00"),
        as_of="2026-06-30",
    )

    assert effective_before_acquisition["resolution_state"] == "unresolved"
    assert effective_before_acquisition["issuer"] is None
    assert learned_after_replay["resolution_state"] == "unresolved"
    assert learned_after_replay["issuer"] is None


def test_joint_venture_requires_documented_economic_share():
    graph = _graph()
    graph["ownership_edges"][0].update({"relationship": "joint_venture", "economic_share": None})

    unresolved = resolve_recipient(_record(), graph, as_of="2026-06-30")
    assert unresolved["resolution_state"] == "unresolved"
    assert unresolved["reason_codes"] == ["ownership_economic_share_missing"]

    graph["ownership_edges"][0]["economic_share"] = 0.4
    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")
    assert resolved["resolution_state"] == "confirmed"
    assert resolved["economic_share"] == pytest.approx(0.4)


def test_global_dedupe_unions_queries_and_never_double_counts_a_source_award():
    first = _record(source_award_key="same-award", known_at="2026-06-16T10:00:00+00:00", discovery_query_id="query:lmt")
    second = _record(source_award_key="same-award", known_at="2026-06-16T11:00:00+00:00", discovery_query_id="query:alias")

    deduped = dedupe_source_records([first, second])
    assert len(deduped) == 1
    assert deduped[0]["_dedupe_input_count"] == 2
    assert deduped[0]["discovery_query_ids"] == ["query:alias", "query:lmt"]

    resolved = resolve_records([first, second], _graph(), as_of="2026-06-30")
    coverage = build_entity_coverage(
        resolved,
        collection={"queries_requested": 2, "queries_complete": 2},
    )
    assert coverage["records"]["input_records"] == 2
    assert coverage["records"]["unique_source_records"] == 1
    assert coverage["records"]["duplicates_removed"] == 1
    assert coverage["amounts"]["candidate_amount"] == pytest.approx(100.0)
    assert coverage["amounts"]["mapped_attributable_amount"] == pytest.approx(100.0)


def test_coverage_keeps_unresolved_and_conflicted_dollars_in_denominator():
    graph = _graph()
    graph["entities"].append({"entity_id": "le:conflict", "canonical_name": "Conflict"})
    graph["identifiers"].append({
        "entity_id": "le:conflict", "namespace": "sam_uei", "value": "UEI-CONFLICT",
        "verification_state": "confirmed", "known_at": "2025-01-01T00:00:00+00:00", "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:coverage-conflict-a"],
    })
    graph["identifiers"].append({
        "entity_id": "le:lmt-sub", "namespace": "sam_uei", "value": "UEI-CONFLICT",
        "verification_state": "confirmed", "known_at": "2025-01-01T00:00:00+00:00", "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:coverage-conflict-b"],
    })
    rows = [
        _record(source_award_key="mapped", amount=100.0),
        _record(source_award_key="unknown", recipient_uei="UEI-UNKNOWN", amount=50.0),
        _record(source_award_key="conflicted", recipient_uei="UEI-CONFLICT", amount=20.0),
    ]
    coverage = build_entity_coverage(
        resolve_records(rows, graph, as_of="2026-06-30"),
        collection={"queries_requested": 3, "queries_complete": 2, "queries_partial": 1},
    )

    assert coverage["records"]["unique_source_records"] == 3
    assert coverage["records"]["issuer_attributed_records"] == 1
    assert coverage["records"]["unresolved_records"] == 1
    assert coverage["records"]["conflicted_records"] == 1
    assert coverage["amounts"]["candidate_amount"] == pytest.approx(170.0)
    assert coverage["amounts"]["mapped_attributable_amount"] == pytest.approx(100.0)
    assert coverage["amounts"]["unmapped_amount"] == pytest.approx(70.0)
    assert coverage["amounts"]["mapping_coverage_ratio"] == pytest.approx(100.0 / 170.0)
    assert coverage["collection"]["complete_scope"] is False
    assert coverage_invariants(coverage) is True


def test_resolution_and_coverage_outputs_satisfy_public_contracts():
    resolution = resolve_recipient(_record(), _graph(), as_of="2026-06-30")
    coverage = build_entity_coverage(
        resolve_records([_record()], _graph(), as_of="2026-06-30"),
        collection={"queries_requested": 1, "queries_complete": 1},
    )
    formatter = FormatChecker()
    Draft202012Validator(
        _schema("government_recipient_resolution.v1.schema.json"),
        format_checker=formatter,
    ).validate(resolution)
    Draft202012Validator(
        _schema("government_entity_coverage.v1.schema.json"),
        format_checker=formatter,
    ).validate(coverage)


def test_source_action_identity_precedes_award_identity_and_namespaces_each_action():
    first = _record(
        source_award_key=None,
        generated_unique_award_id="GENERATED-A",
        action_id="ACTION-SHARED",
    )
    second = _record(
        source_award_key=None,
        generated_unique_award_id="GENERATED-B",
        action_id="ACTION-SHARED",
    )
    award_only = _record(
        source_award_key=None,
        generated_unique_award_id="GENERATED-A",
        action_id=None,
    )

    assert source_record_key(first).startswith("action:award:GENERATED-A|ACTION-SHARED")
    assert source_record_key(first) != source_record_key(second)
    assert source_record_key(award_only) == "award:GENERATED-A"
    assert len(dedupe_source_records([first, second])) == 2


def test_unkeyed_records_never_merge_or_create_attribution_or_coverage():
    unkeyed = _record(
        source_award_key=None,
        generated_unique_award_id=None,
        generated_award_id=None,
        award_key=None,
        action_id=None,
        source_action_id=None,
        source_action_key=None,
        award_id="COLLIDING-PIID-ONLY",
    )
    deduped = dedupe_source_records([unkeyed, dict(unkeyed)])
    resolved = resolve_records([unkeyed, dict(unkeyed)], _graph(), as_of="2026-06-30")
    coverage = build_entity_coverage(
        resolved,
        collection={"queries_requested": 1, "queries_complete": 1},
        as_of="2026-06-30",
    )

    assert len(deduped) == 2
    assert all(row["_source_identity_stable"] is False for row in deduped)
    assert all(item["resolution"]["resolution_state"] == "unresolved" for item in resolved)
    assert all(item["resolution"]["issuer"] is None for item in resolved)
    assert coverage["records"]["records_excluded_unstable_identity"] == 2
    assert coverage["amounts"]["candidate_amount"] is None
    assert coverage["invariants"]["stable_source_identity_only"] is False
    assert coverage_invariants(coverage) is False


def test_historical_dedupe_selects_latest_visible_source_version_not_future_revision():
    older = _record(
        source_award_key="versioned-award",
        known_at="2026-01-15T00:00:00+00:00",
        amount=100.0,
    )
    future_revision = _record(
        source_award_key="versioned-award",
        known_at="2026-07-15T00:00:00+00:00",
        recipient_uei="UEI-UNKNOWN",
        amount=999.0,
    )

    deduped = dedupe_source_records([older, future_revision], as_of="2026-06-30")
    resolved = resolve_records([older, future_revision], _graph(), as_of="2026-06-30")

    assert len(deduped) == 1
    assert deduped[0]["amount"] == 100.0
    assert deduped[0]["_dedupe_input_count"] == 1
    assert len(resolved) == 1
    assert resolved[0]["record"]["amount"] == 100.0
    assert resolved[0]["resolution"]["resolution_state"] == "confirmed"


def test_preflight_identifier_blocks_apply_across_every_present_identifier():
    override = {
        "override_id": "override:block-cage",
        "action": "block_identifier",
        "namespace": "cage",
        "value": "1ABC2",
        "target_entity_id": "le:cage-sub",
        "reviewer_state": "analyst_approved",
        "known_at": "2026-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01",
        "evidence_refs": ["evidence:block-cage"],
    }

    resolved = resolve_recipient(
        _record(recipient_cage="1ABC2"),
        _graph(overrides=[override]),
        as_of="2026-06-30",
    )

    assert resolved["resolution_state"] == "rejected"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["blocked_by_analyst_override"]


def test_all_exact_identifier_mappings_reconcile_before_issuer_attribution():
    resolved = resolve_recipient(
        _record(recipient_cage="1ABC2"),
        _graph(),
        as_of="2026-06-30",
    )

    assert resolved["resolution_state"] == "conflicted"
    assert resolved["issuer"] is None
    assert resolved["economic_share"] is None
    assert resolved["reason_codes"] == ["exact_identifiers_map_to_multiple_entities"]


def test_conflicting_exact_identifier_issuer_claims_fail_closed():
    graph = _graph()
    graph["identifiers"][0]["issuer_company_id"] = "central:LMT"
    graph["identifiers"].append(
        {
            "identifier_id": "id-lmt-cage-claim",
            "entity_id": "le:lmt-sub",
            "namespace": "cage",
            "value": "CLAIM1",
            "issuer_company_id": "central:NOC",
            "verification_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00",
            "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:issuer-claim-noc"],
        }
    )

    resolved = resolve_recipient(
        _record(recipient_cage="CLAIM1"),
        graph,
        as_of="2026-06-30",
    )

    assert resolved["resolution_state"] == "conflicted"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["exact_identifiers_map_to_multiple_issuers"]


def test_exact_identifier_issuer_claim_must_agree_with_vetted_ownership_terminal():
    graph = _graph()
    graph["identifiers"][0]["issuer_company_id"] = "central:NOC"

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "conflicted"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["exact_identifier_issuer_conflicts_with_ownership"]


@pytest.mark.parametrize("missing_field", ["valid_from", "known_at", "evidence_refs"])
def test_exact_identifier_without_explicit_temporal_evidence_never_maps(missing_field):
    graph = _graph()
    graph["identifiers"][0].pop(missing_field)

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["exact_identifier_not_mapped"]


def test_nested_identifier_cannot_inherit_temporal_evidence_from_entity():
    graph = _graph()
    graph["identifiers"] = []
    graph["entities"][0].update(
        {
            "known_at": "2025-01-01T00:00:00+00:00",
            "valid_from": "2020-01-01",
            "verification_state": "confirmed",
            "evidence_refs": ["evidence:entity-metadata"],
            "identifiers": [
                {
                    "namespace": "sam_uei",
                    "value": "UEI-LMT-123",
                    "verification_state": "confirmed",
                }
            ],
        }
    )

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["exact_identifier_not_mapped"]


@pytest.mark.parametrize("invalid_field", ["valid_from", "known_at", "valid_to"])
def test_malformed_identifier_temporal_clocks_fail_closed(invalid_field):
    graph = _graph()
    graph["identifiers"][0][invalid_field] = "not-a-timestamp"

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["exact_identifier_not_mapped"]


@pytest.mark.parametrize("missing_field", ["valid_from", "known_at", "evidence_refs"])
def test_ownership_edge_without_explicit_temporal_evidence_never_attributes(missing_field):
    graph = _graph()
    graph["ownership_edges"][0].pop(missing_field)

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["ownership_path_missing"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda graph: graph["companies"].pop(0),
        lambda graph: graph["companies"][0].pop("evidence_refs"),
        lambda graph: graph["companies"][0].update({"ticker": "not-a-ticker"}),
    ],
)
def test_unvetted_public_company_terminal_never_creates_a_ticker(mutate):
    graph = _graph()
    mutate(graph)

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["parent_company_not_vetted"]


def test_public_parent_metadata_without_an_explicit_ownership_edge_is_not_a_terminal():
    graph = _graph()
    graph["ownership_edges"] = [
        edge for edge in graph["ownership_edges"] if edge["edge_id"] != "edge-lmt"
    ]
    graph["entities"][0].update(
        {
            "entity_type": "public_parent",
            "issuer_company_id": "central:LMT",
            "verification_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00",
            "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:direct-parent"],
        }
    )

    resolved = resolve_recipient(_record(), graph, as_of="2026-06-30")

    assert resolved["resolution_state"] == "unresolved"
    assert resolved["issuer"] is None
    assert resolved["reason_codes"] == ["ownership_path_missing"]


def test_coverage_excludes_resolution_with_mismatched_requested_cutoff():
    resolved = resolve_records([_record()], _graph(), as_of="2026-06-30")
    coverage = build_entity_coverage(
        resolved,
        collection={"queries_requested": 1, "queries_complete": 1},
        as_of="2026-05-31",
    )

    assert coverage["as_of"].startswith("2026-05-31")
    assert coverage["records"]["records_excluded_asof_mismatch"] == 1
    assert coverage["records"]["records_eligible_for_coverage"] == 0
    assert coverage["amounts"]["candidate_amount"] is None
    assert coverage["invariants"]["analysis_cutoff_matches_requested"] is False
    assert coverage_invariants(coverage) is False


def test_resolution_schema_rejects_incomplete_attribution_and_issuer_on_unresolved():
    validator = Draft202012Validator(
        _schema("government_recipient_resolution.v1.schema.json"),
        format_checker=FormatChecker(),
    )
    confirmed = resolve_recipient(_record(), _graph(), as_of="2026-06-30")
    confirmed["issuer"] = None
    assert list(validator.iter_errors(confirmed))

    unresolved = resolve_recipient(
        _record(recipient_uei="UEI-UNKNOWN"),
        _graph(),
        as_of="2026-06-30",
    )
    unresolved["issuer"] = {"company_id": "central:LMT", "ticker": "LMT"}
    unresolved["economic_share"] = 1.0
    assert list(validator.iter_errors(unresolved))
