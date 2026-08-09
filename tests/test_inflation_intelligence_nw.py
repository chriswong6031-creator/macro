"""Focused Neural Web consumer tests for ``inflation_intelligence.v1``.

The producer has its own unit tests. These guards cover only the additive,
read-only consumer path and its authority ceiling.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _target(release_type: str, *, point: float) -> dict:
    return {
        "available": True,
        "release_type": release_type,
        "period": "2026-07",
        "release_date": "2026-08-12",
        "days_to_release": 3,
        "target": "mom_pct",
        "forecast_asof": "2026-08-09",
        "release_radar_projection": {
            "point": point,
            "p10": point - 0.1,
            "p25": point - 0.05,
            "p50": point,
            "p75": point + 0.05,
            "p90": point + 0.1,
            "confidence": 0.71,
        },
        "combined_display_estimate": {
            "point": point + 0.01,
            "p10": point - 0.09,
            "p90": point + 0.11,
            "inputs_used": ["release_radar", "cleveland"],
            "includes_external_benchmark": True,
            "n_scored_basis": 8,
            # Deliberately hostile inputs: consumers must overwrite these.
            "display_only": False,
            "authority": True,
        },
        "coverage": {
            "input_completeness": 0.86,
            "radar_weight_coverage": 0.74,
            "radar_fresh_proxy_coverage": 0.69,
            "bridge_weight_basis": (
                "bls_dec_2025_starting_relative_importance_fixed_approximation"
            ),
            "bridge_weight_basis_warning": "BLS relative importance evolves monthly",
            "bridge_known_scope_mismatches": [
                {
                    "block": "core_services_ex_shelter",
                    "series": f"SERIES-{i}",
                    "official_label": "Services Less Energy Services",
                    "warning": "includes shelter; not core services ex shelter",
                }
                for i in range(12)
            ],
            "absent_legs": ["airfare"],
            "revision_optimistic_legs": ["rent"],
            "range_violation_legs": [],
        },
        "input_snapshot_ref": "sha256:input-snapshot",
        "component_freshness": [{"component": f"component-{i}"} for i in range(50)],
        "forecast_evolution": {
            "basis": "append_only_release_radar_forward_ledger_champion_path",
            "n_points": 50,
            "first_asof": "2026-06-20",
            "last_asof": "2026-08-09",
            "points": [{"asof": f"2026-07-{i + 1:02d}", "point": point} for i in range(30)],
        },
    }


def _artifact() -> dict:
    headline = {
        "available": True,
        "series_id": "CPIAUCSL",
        "label": "Headline CPI-U",
        "observation_period": "2026-06",
        "observation_age_months": 2,
        "index_level": 324.1,
        "mom_pct": 0.21,
        "yoy_pct": 2.62,
        "annualized_3m_pct": 2.41,
        "annualized_6m_pct": 2.53,
        "acceleration_3m_minus_6m_pp": -0.12,
        "revision_basis": "latest_local_fred_not_original_release_vintage",
    }
    sticky = {
        "available": True,
        "series_id": "STICKCPIM157SFRBATL",
        "observation_period": "2026-06",
        "monthly_pct": 0.28,
        "annualized_3m_pct": 3.12,
        "annualized_6m_pct": 3.24,
        "acceleration_3m_minus_6m_pp": -0.12,
        "revision_basis": "latest_local_fred_proxy_series",
    }
    return {
        "schema": "inflation_intelligence.v1",
        "asof": "2026-08-09",
        # Deliberately hostile inputs: every consumer must force the fence.
        "display_only": False,
        "authority": True,
        "is_context_only": False,
        "allowed_actions": {
            "may_rank": True,
            "may_score": True,
            "may_size": True,
            "may_gate": True,
            "may_escalate": True,
            "may_trade": True,
        },
        "released_state": {
            "available": True,
            "basis": "latest_local_fred_official_index_levels_not_original_release_vintage",
            "headline": headline,
            "core": {**headline, "series_id": "CPILFESL", "label": "Core CPI-U"},
            "underlying_proxies": {"sticky": sticky, "flexible": sticky},
        },
        "next_release_forecast": {
            "available": True,
            "release_date": "2026-08-12",
            "period": "2026-07",
            "headline": _target("cpi_headline", point=0.23),
            "core": _target("cpi_core", point=0.27),
        },
        "current_month_proxy_pressure": {
            "available": True,
            "period": "2026-08",
            "definition": "Model pressure only; not an official CPI observation.",
            "pressure_direction": "upward_price_pressure",
            "headline_model_pressure": _target("cpi_headline", point=0.19),
            "core_model_pressure": _target("cpi_core", point=0.24),
            "coverage": _target("cpi_headline", point=0.19)["coverage"],
            "underlying_proxy_mix": {
                "read": "sticky_led",
                "sticky": sticky,
                "flexible": sticky,
            },
        },
        "source_status": {
            "release_radar_latest": {"available": True, "asof": "2026-08-09"},
            "release_radar_forward_ledger": {"available": True, "rows_read": 50},
        },
        "gaps": ["fred:FLEXCPIM157SFRBATL:stale"],
    }


def _write_artifact(root: Path, payload: object | None = None) -> Path:
    path = root / "data" / "release_forecast" / "inflation_intelligence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_artifact() if payload is None else payload), encoding="utf-8")
    return path


def _assert_authority_false(payload: dict) -> None:
    assert payload["display_only"] is True
    assert payload["authority"] is False
    assert payload["is_context_only"] is True
    assert payload["allowed_actions"]
    assert not any(payload["allowed_actions"].values())


def test_world_state_inflation_lobe_is_bounded_and_authority_false(tmp_path: Path) -> None:
    from engine.neuralweb.world_state import _compose_inflation_intelligence

    _write_artifact(tmp_path)
    lobe = _compose_inflation_intelligence(tmp_path)

    _assert_authority_false(lobe)
    assert lobe["available"] is True
    assert lobe["released_state"]["headline"]["yoy_pct"] == 2.62
    headline = lobe["next_release_forecast"]["headline"]
    assert headline["release_radar_projection"]["point"] == 0.23
    assert headline["input_snapshot_ref"] == "sha256:input-snapshot"
    assert headline["combined_display_estimate"]["authority"] is False
    assert headline["coverage"]["bridge_weight_basis"].endswith("fixed_approximation")
    assert "evolves monthly" in headline["coverage"]["bridge_weight_basis_warning"]
    assert headline["coverage"]["bridge_known_scope_mismatches"][0]["series"] == "SERIES-0"
    assert len(headline["coverage"]["bridge_known_scope_mismatches"]) == 8
    assert "points" not in headline["forecast_evolution"]
    assert "component_freshness" not in headline
    current_pressure = lobe["current_month_proxy_pressure"]
    assert current_pressure["pressure_direction"] == "upward_price_pressure"
    assert "evolves monthly" in current_pressure["coverage"]["bridge_weight_basis_warning"]
    assert len(current_pressure["coverage"]["bridge_known_scope_mismatches"]) == 8


def test_world_state_build_wires_null_safe_inflation_lobe(tmp_path: Path) -> None:
    from engine.neuralweb.world_state import build_world_state

    missing = build_world_state(tmp_path, now=datetime(2026, 8, 9, tzinfo=timezone.utc))
    _assert_authority_false(missing["inflation_intelligence"])
    assert missing["inflation_intelligence"]["available"] is False
    assert missing["inflation_intelligence"]["gaps"]

    _write_artifact(tmp_path)
    populated = build_world_state(tmp_path, now=datetime(2026, 8, 9, tzinfo=timezone.utc))
    assert populated["inflation_intelligence"]["next_release_forecast"]["release_date"] == "2026-08-12"


def test_mastermind_inflation_lobe_is_registered_bounded_and_fresh(tmp_path: Path) -> None:
    from engine.neuralweb.mastermind_context import (
        LOBE_SUMMARIZERS,
        _build_freshness,
        _summarize_inflation_intelligence,
    )

    _write_artifact(tmp_path)
    lobe, gap = _summarize_inflation_intelligence(tmp_path)

    assert gap is None
    assert LOBE_SUMMARIZERS["inflation_intelligence"] is _summarize_inflation_intelligence
    _assert_authority_false(lobe)
    assert "official CPI observation" in lobe["standing_law"]
    assert lobe["next_release_forecast"]["headline"]["input_snapshot_ref"] == "sha256:input-snapshot"
    coverage = lobe["next_release_forecast"]["headline"]["coverage"]
    assert coverage["bridge_weight_basis_warning"] == "BLS relative importance evolves monthly"
    assert len(coverage["bridge_known_scope_mismatches"]) == 8
    current_coverage = lobe["current_month_proxy_pressure"]["coverage"]
    assert current_coverage["bridge_known_scope_mismatches"][0]["warning"].startswith(
        "includes shelter"
    )
    assert "points" not in lobe["next_release_forecast"]["headline"]["forecast_evolution"]
    freshness = _build_freshness({"inflation_intelligence": lobe}, [])
    assert freshness["inflation_intelligence"]["as_of"] == "2026-08-09"


def test_mastermind_context_wires_source_and_absence_gap(tmp_path: Path) -> None:
    from engine.neuralweb.mastermind_context import build_context

    absent = build_context(tmp_path, now=datetime(2026, 8, 9, tzinfo=timezone.utc))
    assert absent["lobes"]["inflation_intelligence"] == {}
    assert any("lobe.inflation_intelligence" in gap for gap in absent["gap_notes"])

    _write_artifact(tmp_path)
    populated = build_context(tmp_path, now=datetime(2026, 8, 9, tzinfo=timezone.utc))
    assert "data/release_forecast/inflation_intelligence.json" in populated["source_artifacts"]
    _assert_authority_false(populated["lobes"]["inflation_intelligence"])


def test_cortex_tool_fails_open_and_overwrites_hostile_authority(tmp_path: Path) -> None:
    from engine.neuralweb.cortex import _tool_read_inflation_intelligence
    from engine.neuralweb.mastermind_context import _summarize_inflation_intelligence
    from engine.neuralweb.world_state import _compose_inflation_intelligence

    absent = _tool_read_inflation_intelligence(tmp_path, {})
    _assert_authority_false(absent)
    assert absent["gaps"]

    _write_artifact(tmp_path)
    present = _tool_read_inflation_intelligence(tmp_path, {})
    _assert_authority_false(present)
    assert present["next_release_forecast"]["headline"]["release_radar_projection"]["point"] == 0.23
    nested_combined = present["next_release_forecast"]["headline"]["combined_display_estimate"]
    assert nested_combined["display_only"] is True
    assert nested_combined["authority"] is False

    _write_artifact(tmp_path, ["not", "an", "object"])
    malformed = _tool_read_inflation_intelligence(tmp_path, {})
    _assert_authority_false(malformed)
    assert "not_object" in malformed["gaps"][0]
    malformed_world = _compose_inflation_intelligence(tmp_path)
    _assert_authority_false(malformed_world)
    assert "not_object" in malformed_world["gaps"][0]
    malformed_mastermind, gap = _summarize_inflation_intelligence(tmp_path)
    assert malformed_mastermind == {}
    assert gap and "absent or unreadable" in gap


def test_inflation_tool_registered_and_routes_through_cortex_and_ask(tmp_path: Path) -> None:
    from engine.neuralweb.ask_brain import (
        _ASK_READ_TOOLS,
        _classify_question,
        _dispatch_read_tool_raw,
    )
    from engine.neuralweb.cortex import (
        _READ_TOOLS,
        _SYSTEM_PROMPT,
        _WRITE_TOOLS,
        _tool_schemas,
        dispatch_tool,
    )

    _write_artifact(tmp_path)
    name = "read_inflation_intelligence"
    assert name in _READ_TOOLS
    assert name in _ASK_READ_TOOLS
    assert name not in _WRITE_TOOLS
    schema = next(item for item in _tool_schemas() if item["name"] == name)
    assert "never originate, score, rank, gate, size" in schema["description"].lower()
    assert name in _SYSTEM_PROMPT

    cortex_result = dispatch_tool(name, {}, tmp_path, "2026-08-09", {}, {})
    ask_result = _dispatch_read_tool_raw(name, {}, tmp_path)
    _assert_authority_false(cortex_result)
    _assert_authority_false(ask_result)

    budget, seeds = _classify_question("What will the next CPI print be?", None)
    assert budget >= 2
    assert seeds == [name, "read_world_state"]
