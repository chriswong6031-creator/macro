"""Strict reviewed recipient-graph admission and coverage tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from engine.government_revenue.entity_resolution import (
    attach_recipient_resolution,
    build_recipient_resolution_coverage,
    load_recipient_entity_graph,
    resolve_recipient,
    source_record_key,
)
from scripts.curate_government_revenue_recipient_graph import curate_graph


CONTRACTS = Path(__file__).parents[1] / "contracts" / "government_revenue"
ROOT = Path(__file__).parents[1]


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _temporal(**values):
    row = {
        "known_at": "2025-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None,
        "evidence_refs": ["evidence:primary"],
    }
    row.update(values)
    return row


def _graph():
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.0.0",
        "graph_id": "recipient-graph:unit:2026-06-30",
        "graph_known_at": "2026-06-30T12:00:00+00:00",
        "graph_effective_at": "2026-06-30T12:00:00+00:00",
        "evidence": [
            {
                "evidence_id": "evidence:primary",
                "source_ref": "official:entity-filing:123",
                "known_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2020-01-01T00:00:00+00:00",
                "valid_to": None,
            }
        ],
        "companies": [
            {
                "company_id": "central:ABC",
                "ticker": "ABC",
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "legal_entities": [
            {
                "entity_id": "legal:abc-services",
                "canonical_name": "ABC Services LLC",
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "identifiers": [
            {
                "identifier_id": "identifier:abc-uei",
                "entity_id": "legal:abc-services",
                "namespace": "sam_uei",
                "value": "UEI-ABC-123",
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "ownership_edges": [
            {
                "edge_id": "ownership:abc-services-to-abc",
                "child_entity_id": "legal:abc-services",
                "parent_company_id": "central:ABC",
                "relationship": "wholly_owned",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }


def _record(**changes):
    row = {
        "source_award_key": "award:abc-1",
        "recipient_name": "ABC Services LLC",
        "recipient_uei": "UEI-ABC-123",
        "effective_at": "2026-06-15T00:00:00+00:00",
        "known_at": "2026-06-16T00:00:00+00:00",
        "amount": 100.0,
    }
    row.update(changes)
    return row


def _load(graph=None):
    return load_recipient_entity_graph(
        _graph() if graph is None else graph,
        as_of="2026-06-30T23:59:59+00:00",
    )


def test_loader_requires_reviewed_exact_graph_and_uses_no_display_name_join():
    loaded = _load()
    assert loaded["status"] == "ready"
    assert loaded["graph"]["_recipient_graph_id"] == "recipient-graph:unit:2026-06-30"

    resolved = resolve_recipient(_record(), loaded, as_of="2026-06-30")
    assert resolved["issuer"] == {"company_id": "central:ABC", "ticker": "ABC"}

    name_only = resolve_recipient(
        _record(recipient_uei=None, recipient_name="ABC Services LLC"),
        loaded,
        as_of="2026-06-30",
    )
    assert name_only["resolution_state"] == "unresolved"
    assert name_only["issuer"] is None
    assert name_only["reason_codes"] == ["missing_exact_identifier"]

    fuzzy = _graph()
    fuzzy["name_candidates"] = [{"name": "ABC Services LLC", "company_id": "central:ABC"}]
    rejected = _load(fuzzy)
    assert rejected["status"] == "invalid"
    assert "graph_shape_invalid" in rejected["error_codes"]


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda graph: graph["identifiers"][0].update({"evidence_refs": []}), "missing_evidence_refs"),
        (lambda graph: graph.update({"graph_known_at": "2026-06-30T12:00:00"}), "invalid_graph_known_at"),
        (lambda graph: graph["identifiers"][0].update({"known_at": "2026-07-01T00:00:00+00:00"}), "future_known_claim"),
        (lambda graph: graph["ownership_edges"][0].update({"valid_from": "2026-07-01T00:00:00+00:00"}), "future_effective_claim"),
        (lambda graph: graph["ownership_edges"][0].update({"parent_company_id": "central:UNKNOWN"}), "ownership_references_unknown_company"),
        (lambda graph: graph["ownership_edges"][0].update({"relationship": "joint_venture", "economic_share": None}), "ownership_economic_share_missing"),
    ],
)
def test_loader_rejects_missing_evidence_future_claims_unknown_issuers_and_unfunded_jvs(mutate, error_code):
    graph = _graph()
    mutate(graph)
    loaded = _load(graph)
    assert loaded["status"] == "invalid"
    assert error_code in loaded["error_codes"]


def test_loader_rejects_ownership_cycles_and_ambiguous_exact_paths():
    cycle = _graph()
    cycle["legal_entities"].append(
        {
            "entity_id": "legal:abc-parent",
            "canonical_name": "ABC Parent LLC",
            "verification_state": "reviewed",
            **_temporal(),
        }
    )
    cycle["ownership_edges"][0].pop("parent_company_id")
    cycle["ownership_edges"][0]["parent_entity_id"] = "legal:abc-parent"
    cycle["ownership_edges"].append(
        {
            "edge_id": "ownership:abc-parent-to-services",
            "child_entity_id": "legal:abc-parent",
            "parent_entity_id": "legal:abc-services",
            "relationship": "wholly_owned",
            "economic_share": 1.0,
            "verification_state": "reviewed",
            **_temporal(),
        }
    )
    assert "ownership_cycle" in _load(cycle)["error_codes"]

    ambiguous = _graph()
    ambiguous["legal_entities"].append(
        {
            "entity_id": "legal:other",
            "canonical_name": "Other LLC",
            "verification_state": "reviewed",
            **_temporal(),
        }
    )
    ambiguous["identifiers"].append(
        {
            "identifier_id": "identifier:duplicate-uei",
            "entity_id": "legal:other",
            "namespace": "sam_uei",
            "value": "UEI-ABC-123",
            "verification_state": "reviewed",
            **_temporal(),
        }
    )
    assert "ambiguous_exact_identifier_path" in _load(ambiguous)["error_codes"]


def test_reviewed_blocks_conflicts_and_overrides_are_explicit_and_fail_closed():
    blocked = _graph()
    blocked["blocks"].append(
        {
            "block_id": "block:abc-uei",
            "scope": "identifier",
            "namespace": "sam_uei",
            "value": "UEI-ABC-123",
            "reason_code": "official_identifier_retired",
            "reviewer_state": "reviewed",
            **_temporal(),
        }
    )
    block_loaded = _load(blocked)
    assert block_loaded["status"] == "ready"
    assert resolve_recipient(_record(), block_loaded, as_of="2026-06-30")["resolution_state"] == "rejected"

    ownership_blocked = _graph()
    ownership_blocked["blocks"].append(
        {
            "block_id": "block:abc-ownership",
            "scope": "ownership",
            "target_edge_id": "ownership:abc-services-to-abc",
            "reason_code": "ownership_research_disputed",
            "reviewer_state": "reviewed",
            **_temporal(),
        }
    )
    ownership_block_result = resolve_recipient(
        _record(), _load(ownership_blocked), as_of="2026-06-30"
    )
    assert ownership_block_result["resolution_state"] == "unresolved"
    assert ownership_block_result["issuer"] is None

    conflicted = _graph()
    conflicted["conflicts"].append(
        {
            "conflict_id": "conflict:abc-uei",
            "scope": "identifier",
            "namespace": "sam_uei",
            "value": "UEI-ABC-123",
            "reason_code": "official_sources_disagree",
            "reviewer_state": "reviewed",
            **_temporal(),
        }
    )
    # The loader does not use conflict candidates to fabricate a second entity;
    # the explicit conflict itself safely withholds issuer attribution.
    conflict_loaded = _load(conflicted)
    assert conflict_loaded["status"] == "ready"
    result = resolve_recipient(_record(), conflict_loaded, as_of="2026-06-30")
    assert result["resolution_state"] == "conflicted"
    assert result["issuer"] is None

    overridden = _graph()
    overridden["overrides"].append(
        {
            "override_id": "override:source-uei",
            "action": "assert_identifier",
            "namespace": "sam_uei",
            "value": "UEI-OVERRIDE-456",
            "target_entity_id": "legal:abc-services",
            "reviewer_state": "reviewed",
            **_temporal(),
        }
    )
    override_loaded = _load(overridden)
    assert override_loaded["status"] == "ready"
    override_result = resolve_recipient(
        _record(recipient_uei="UEI-OVERRIDE-456"), override_loaded, as_of="2026-06-30"
    )
    assert override_result["resolution_state"] == "reviewed"
    assert override_result["resolution_rule"] == "analyst_override"


def test_safe_join_copies_source_record_and_graph_changes_never_change_source_identity():
    source = _record()
    original = deepcopy(source)
    first = _load()
    graph_changed = _graph()
    graph_changed["companies"][0]["ticker"] = "ABCD"
    second = _load(graph_changed)

    joined = attach_recipient_resolution(source, first, as_of="2026-06-30")
    assert source == original
    assert "recipient_resolution" not in source
    assert joined["recipient_resolution"]["issuer"]["ticker"] == "ABC"
    assert source_record_key(source) == source_record_key(joined)
    assert source_record_key(source) == source_record_key(
        attach_recipient_resolution(source, second, as_of="2026-06-30")
    )


def test_resolver_rechecks_strict_loader_source_and_never_trusts_a_forged_normalized_graph():
    loaded = _load()
    tampered = deepcopy(loaded)
    tampered["graph"]["companies"][0]["ticker"] = "FAKE"
    # The raw strict source is reloaded, so a caller cannot swap in a made-up
    # normalized issuer graph after validation.
    assert resolve_recipient(_record(), tampered, as_of="2026-06-30")["issuer"]["ticker"] == "ABC"

    forged = deepcopy(loaded)
    forged.pop("_strict_source_graph")
    withheld = resolve_recipient(_record(), forged, as_of="2026-06-30")
    assert withheld["resolution_state"] == "unresolved"
    assert withheld["issuer"] is None
    assert withheld["reason_codes"] == ["recipient_graph_invalid"]


def test_independent_snapshot_and_action_coverage_preserves_unresolved_absolute_denominators():
    loaded = _load()
    snapshots = [
        _record(source_award_key="snapshot:mapped", amount=100.0),
        _record(source_award_key="snapshot:unknown", recipient_uei="UEI-UNKNOWN", amount=50.0),
        _record(source_award_key="snapshot:conflict", recipient_uei="UEI-CONFLICT", amount=20.0),
    ]
    conflict_graph = _graph()
    conflict_graph["conflicts"].append(
        {
            "conflict_id": "conflict:unresolved-uei",
            "scope": "identifier",
            "namespace": "sam_uei",
            "value": "UEI-CONFLICT",
            "reason_code": "review_pending",
            "reviewer_state": "reviewed",
            **_temporal(),
        }
    )
    loaded = _load(conflict_graph)
    actions = [
        _record(source_award_key="action:mapped", amount=-40.0),
        _record(source_award_key="action:unknown", recipient_uei="UEI-UNKNOWN", amount=10.0),
    ]
    coverage = build_recipient_resolution_coverage(
        snapshots,
        actions,
        loaded,
        as_of="2026-06-30",
        snapshot_collection={"queries_requested": 3, "queries_complete": 3},
        action_collection={"queries_requested": 2, "queries_complete": 2},
    )

    assert coverage["snapshot"]["amounts"]["candidate_amount"] == pytest.approx(170.0)
    assert coverage["snapshot"]["amounts"]["mapped_attributable_amount"] == pytest.approx(100.0)
    assert coverage["snapshot"]["amounts"]["unmapped_amount"] == pytest.approx(70.0)
    assert coverage["snapshot"]["records"]["conflicted_records"] == 1
    assert coverage["action"]["amounts"]["candidate_amount"] == pytest.approx(50.0)
    assert coverage["action"]["amounts"]["mapped_attributable_amount"] == pytest.approx(40.0)
    assert coverage["action"]["amounts"]["unmapped_amount"] == pytest.approx(10.0)
    assert coverage["invariants"]["absolute_denominators"] is True


def test_absent_or_invalid_graph_withholds_issuer_impacts_but_leaves_source_rows_available():
    source = _record(amount=125.0)
    attached = attach_recipient_resolution(source, _load(), as_of="2026-06-30")
    coverage = build_recipient_resolution_coverage(
        [attached],
        [],
        None,
        as_of="2026-06-30",
        snapshot_collection={"queries_requested": 1, "queries_complete": 1},
        action_collection={"queries_requested": 0},
    )

    assert coverage["resolution_graph"]["load_status"] == "absent"
    assert coverage["snapshot"]["records"]["unique_source_records"] == 1
    assert coverage["snapshot"]["amounts"]["candidate_amount"] == pytest.approx(125.0)
    assert coverage["snapshot"]["records"]["issuer_attributed_records"] == 0
    assert coverage["snapshot"]["states"]["unresolved"] == 1
    assert coverage["invariants"]["graph_withheld_when_not_ready"] is True


def test_new_graph_and_coverage_contracts_validate_with_existing_entity_coverage_contract():
    graph = _graph()
    graph_validator = Draft202012Validator(
        _schema("government_recipient_entity_graph.v1.schema.json"),
        format_checker=FormatChecker(),
    )
    graph_validator.validate(graph)

    coverage = build_recipient_resolution_coverage(
        [_record()], [], _load(), as_of="2026-06-30",
        snapshot_collection={"queries_requested": 1, "queries_complete": 1},
        action_collection={"queries_requested": 0},
    )
    entity_schema = _schema("government_entity_coverage.v1.schema.json")
    coverage_schema = _schema("government_recipient_resolution_coverage.v1.schema.json")
    registry = Registry().with_resource(entity_schema["$id"], Resource.from_contents(entity_schema))
    Draft202012Validator(
        coverage_schema,
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(coverage)


def test_canonical_empty_first_graph_is_strict_and_reports_zero_real_rail_coverage():
    graph = json.loads(
        (
            ROOT
            / "data"
            / "government_revenue"
            / "recipient_entity_graph.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(
        _schema("government_recipient_entity_graph.v1.schema.json"),
        format_checker=FormatChecker(),
    ).validate(graph)
    assert all(
        graph[field] == []
        for field in (
            "evidence", "companies", "legal_entities", "identifiers",
            "ownership_edges", "blocks", "conflicts", "overrides",
        )
    )
    loaded = load_recipient_entity_graph(graph, as_of="2026-08-02")
    assert loaded["status"] == "ready"
    coverage = build_recipient_resolution_coverage(
        [],
        [],
        loaded,
        as_of="2026-08-02",
        snapshot_amount_field="total_obligation",
        action_amount_field="federal_action_obligation",
    )
    assert coverage["snapshot"]["amounts"] == {
        "field": "total_obligation",
        "basis": "absolute",
        "candidate_amount": None,
        "mapped_attributable_amount": None,
        "mapped_unallocated_amount": None,
        "unmapped_amount": None,
        "mapping_coverage_ratio": None,
        "recipient_identity_resolution_ratio": None,
        "issuer_attribution_count_ratio": None,
    }
    assert coverage["action"]["amounts"]["field"] == "federal_action_obligation"
    assert coverage["snapshot"]["records"]["unique_source_records"] == 0
    assert coverage["action"]["records"]["unique_source_records"] == 0


def test_manual_curator_atomically_publishes_only_a_strict_reviewed_graph(tmp_path):
    candidate_path = tmp_path / "candidate.json"
    target_path = tmp_path / "recipient_entity_graph.json"
    candidate_path.write_text(json.dumps(_graph()), encoding="utf-8")

    loaded = curate_graph(candidate_path, target_path=target_path, as_of="2026-06-30")

    assert loaded["status"] == "ready"
    assert json.loads(target_path.read_text(encoding="utf-8")) == _graph()
    assert target_path.read_text(encoding="utf-8").endswith("\n")

    invalid = _graph()
    invalid["graph_known_at"] = "2026-06-30T12:00:00"
    candidate_path.write_text(json.dumps(invalid), encoding="utf-8")
    before = target_path.read_bytes()
    with pytest.raises(ValueError, match="failed admission"):
        curate_graph(candidate_path, target_path=target_path, as_of="2026-06-30")
    assert target_path.read_bytes() == before


def test_dag_and_synapse_register_only_the_reviewed_graph_and_coverage_artifacts():
    dag = yaml.safe_load((ROOT / "config" / "dag.yml").read_text(encoding="utf-8"))
    modules = dag.get("modules") or dag.get("artifacts") or []
    builder = next(
        row for row in modules
        if isinstance(row, dict) and row.get("module") == "scripts.build_government_revenue"
    )
    collector = next(
        row for row in modules
        if isinstance(row, dict) and row.get("module") == "collectors.usaspending_awards"
    )
    graph_path = "data/government_revenue/recipient_entity_graph.json"
    coverage_path = "data/government_revenue/recipient_resolution_coverage.json"
    assert graph_path in builder["reads"]
    assert coverage_path in builder["writes"]
    assert graph_path not in collector.get("reads", [])
    assert graph_path not in collector.get("writes", [])
    assert coverage_path not in collector.get("writes", [])

    registry = yaml.safe_load(
        (ROOT / "config" / "synapse.yml").read_text(encoding="utf-8")
    )["artifacts"]
    recipient_artifacts = {
        artifact_id: row
        for artifact_id, row in registry.items()
        if row.get("path") in {graph_path, coverage_path}
    }
    assert set(recipient_artifacts) == {
        "government-revenue-recipient-entity-graph",
        "government-revenue-recipient-resolution-coverage",
    }
    assert recipient_artifacts["government-revenue-recipient-entity-graph"]["producer"] == (
        "scripts/curate_government_revenue_recipient_graph.py"
    )
    expected_authority = {
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }
    for row in recipient_artifacts.values():
        assert row["tier"] == "infrastructure"
        assert row["horizon_role"] == "context"
        assert row["weights"] == "none"
        assert row["scored_path_surfaces"] == []
        assert row["authority"] == expected_authority
