from __future__ import annotations

from copy import deepcopy

import pytest

from engine.intelligence_workspace.consumers import (
    build_brain_fact_packet,
    evaluate_stage_momentum_fixture,
    parity_projection,
)
from engine.intelligence_workspace.contracts import DatapointContractError
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
