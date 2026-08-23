from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from engine.intelligence_workspace.consumers import (
    build_brain_fact_packet,
    evaluate_stage_momentum_fixture,
    parity_projection,
)
from engine.intelligence_workspace.contracts import (
    AdapterResult,
    CanonicalEntity,
    DatapointContractError,
)
from engine.intelligence_workspace.registry import load_registry
from engine.intelligence_workspace.resolver import DatapointResolver
from engine.neuralweb.brain_gateway import _json_safe, _model_visible_tool_result


def _row(field_id, value, unit, *, status="available", audience="subscriber"):
    reason = None if status == "available" else status
    if status == "rights_blocked":
        reason = "rights_blocked"
        value = None
    return {
        "schema": "datapoint_value.v1",
        "registry_version": "1.0.0",
        "registry_digest": "d" * 64,
        "field_id": field_id,
        "entity": {"type": "security", "id": "SEC:US-XNAS-AAPL"},
        "value": value,
        "status": status,
        "reason_code": reason,
        "unit": unit,
        "observed_at": "2026-08-22T20:15:00Z",
        "effective_at": "2026-08-22T20:15:00Z",
        "as_of": "2026-08-22T20:15:00Z",
        "generated_at": "2026-08-23T12:00:00.000000Z",
        "freshness": {"state": "fresh", "policy": "owner_native"},
        "quality": {"state": "ok", "issues": []},
        "source": {
            "source_id": "owner.fixture",
            "owner": "stage_analysis",
            "license_class": "internal_derived",
            "dataset_id": None,
        },
        "provenance": {"kind": "owner_derived", "owner_field_key": field_id},
        "consumer_uses": ["display", "query", "ai_fact", "context"],
        "audience": audience,
        "fact_fingerprint": (field_id[0] if field_id else "f") * 64,
    }


def test_tiny_query_fixture_uses_registered_percent_unit_and_exact_facts():
    rows = (
        _row("stage.current", 2, "stage_code"),
        _row("market.return.3m", 15.0, "percent"),
    )
    result = evaluate_stage_momentum_fixture(rows)
    assert result["matched"] is True
    assert tuple(result["facts"]) == parity_projection(rows)
    mutant = deepcopy(rows[1])
    mutant["value"] = 0.15
    assert evaluate_stage_momentum_fixture((rows[0], mutant))["matched"] is False
    mutant["unit"] = "ratio"
    with pytest.raises(DatapointContractError, match="unit drift"):
        evaluate_stage_momentum_fixture((rows[0], mutant))


def test_tiny_query_fixture_rejects_duplicate_contradictory_facts():
    first = _row("stage.current", 1, "stage_code")
    second = _row("stage.current", 2, "stage_code")
    returns = _row("market.return.3m", 15.0, "percent")
    with pytest.raises(DatapointContractError, match="exactly two|duplicate"):
        evaluate_stage_momentum_fixture((first, second, returns))


def test_brain_fixture_uses_existing_model_visible_tool_result_contract_without_recompute():
    rows = (
        _row("market.return.3m", 15.0, "percent"),
        _row("theme.local.memberships", None, "entity_refs", status="rights_blocked"),
    )
    packet = build_brain_fact_packet(rows)
    visible = _json_safe(_model_visible_tool_result("get_symbol_context", packet))
    assert visible == packet
    assert visible["facts"][0]["value"] == 15.0
    assert visible["facts"][0]["as_of"] == "2026-08-22T20:15:00Z"
    assert visible["facts"][0]["freshness"]["state"] == "fresh"
    assert visible["facts"][1]["status"] == "rights_blocked"
    assert visible["facts"][1]["value"] is None
    assert "originate or recompute" in visible["instruction"]


def test_brain_fixture_rejects_internal_projection_and_blocked_value_leak():
    internal = _row("market.return.3m", 15.0, "percent", audience="internal")
    with pytest.raises(DatapointContractError, match="subscriber projection"):
        build_brain_fact_packet((internal,))

    blocked = _row("theme.local.memberships", None, "entity_refs", status="rights_blocked")
    blocked["value"] = ["ltheme:finviz:ai"]
    with pytest.raises(DatapointContractError, match="rights-blocked"):
        build_brain_fact_packet((blocked,))


def test_direct_query_brain_parity_surface_is_identical():
    rows = (
        _row("stage.current", 2, "stage_code"),
        _row("market.return.3m", 15.0, "percent"),
    )
    direct = parity_projection(rows)
    query = tuple(evaluate_stage_momentum_fixture(rows)["facts"])
    brain = build_brain_fact_packet(rows)
    brain_parity = tuple(
        {
            **{key: fact[key] for key in direct[0] if key not in {"source_id", "quality_state"}},
            "source_id": fact["source"]["source_id"],
            "quality_state": fact["quality_state"],
        }
        for fact in brain["facts"]
    )
    assert query == direct == brain_parity


def test_real_resolver_direct_query_brain_fingerprints_are_identical():
    class Identity:
        def normalize_many(self, entities):
            return tuple(
                CanonicalEntity("security", "SEC:US-XNAS-AAPL", "us_equity")
                for _ in entities
            )

    class Owner:
        def resolve_many(self, entities, specs, request, context):
            del request, context
            values = {"stage.current": 2, "market.return.3m": 15.0}
            return {
                (entity.type, entity.id, spec.field_id): AdapterResult(
                    value=values[spec.field_id],
                    status="available",
                    reason_code=None,
                    unit=spec.unit,
                    observed_at="2026-08-22T20:15:00Z",
                    effective_at="2026-08-22T20:15:00Z",
                    as_of="2026-08-22T20:15:00Z",
                    freshness={"state": "fresh", "policy": "owner_native"},
                    quality={"state": "ok", "issues": []},
                    source={
                        "source_id": f"owner.{spec.owner_field_key}",
                        "owner": spec.owner_ref["owner"],
                        "license_class": "internal_derived",
                        "dataset_id": spec.owner_ref["dataset_id"],
                    },
                    provenance={
                        "kind": "owner_derived",
                        "owner_field_key": spec.owner_field_key,
                        "basis": spec.basis_policy,
                    },
                )
                for entity in entities
                for spec in specs
            }

    owner = Owner()
    rows = DatapointResolver(
        registry=load_registry(),
        identity_normalizer=Identity(),
        adapters={"stage": owner, "technicals": owner},
        clock=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    ).resolve(
        {
            "entities": [{"type": "security", "id": "SEC:US-XNAS-AAPL"}],
            "field_ids": ["stage.current", "market.return.3m"],
            "audience": "subscriber",
            "consumer_use": "query",
        }
    )

    direct = parity_projection(rows)
    query = tuple(evaluate_stage_momentum_fixture(rows)["facts"])
    brain = build_brain_fact_packet(rows)
    brain_parity = tuple(
        {
            **{key: fact[key] for key in direct[0] if key not in {"source_id", "quality_state"}},
            "source_id": fact["source"]["source_id"],
            "quality_state": fact["quality_state"],
        }
        for fact in brain["facts"]
    )

    assert query == direct == brain_parity
    assert {fact["fact_fingerprint"] for fact in direct} == {
        fact["fact_fingerprint"] for fact in query
    } == {fact["fact_fingerprint"] for fact in brain_parity}
