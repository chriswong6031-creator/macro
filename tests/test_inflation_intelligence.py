"""Contract tests for the display-only inflation intelligence foundation."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.inflation_intelligence import (
    build_inflation_intelligence,
    write_inflation_intelligence,
)
from scripts.build_inflation_intelligence import main

_AS_OF = "2026-08-08"


def _write_series(root: Path, series_id: str, column: str, values: list[float]) -> None:
    path = root / "data" / "fred" / f"{series_id}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    index = pd.date_range("2025-05-01", periods=len(values), freq="MS")
    pd.DataFrame({column: values}, index=index).to_parquet(path)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict], malformed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
        if malformed:
            handle.write("{not-json\n")


def _entry(
    release_type: str,
    period: str,
    release_date: str,
    point: float,
    *,
    current_components: bool = False,
) -> dict:
    entry = {
        "release": "cpi",
        "release_type": release_type,
        "period": period,
        "release_date": release_date,
        "days_to": 4 if period == "2026-07" else 34,
        "target": "mom_sa_pct",
        "projection": {
            "point": point,
            "p10": point - 0.2,
            "p25": point - 0.1,
            "p50": point,
            "p75": point + 0.1,
            "p90": point + 0.2,
        },
        "confidence": 0.4,
        "input_completeness": 0.9,
        "model_epoch": f"champion-model:{release_type}",
        "target_epoch": f"coherent-target:{release_type}",
        "code_receipt": "git:0123456789abcdef",
        "inputs_hash": f"sha256:champion-inputs:{release_type}:{period}",
        "primary_forecast_basis": "combined_v1_benchmark_augmented",
        "context_metrics_basis": "champion_legacy_target_v1",
        "basis_warning": "Combined point and champion context use different bases.",
        "coverage_flags": {
            "weight_coverage": 1.0,
            "fresh_proxy_coverage": 0.75,
            "non_vintaged_share": 0.25,
            "model_maturity": 2,
        },
        "pit": {
            "absent_legs": [],
            "revision_optimistic_legs": ["shelter_nowcast"],
            "range_violation_legs": [],
            "display_only": True,
            "authority": False,
        },
        "input_snapshot_ref": f"snapshots/{release_type}_{period}.json",
        "combined": {
            "combined_point": point + 0.02,
            "p10": point - 0.2,
            "p90": point + 0.2,
            "n_scored_basis": 1,
            "model_epoch": f"combined-model:{release_type}",
            "target_epoch": f"combined-target:{release_type}",
            "code_receipt": "git:combined012345",
            "inputs_hash": f"sha256:combined:{release_type}:{period}",
            "combined_components": {
                "inputs_used": ["champion", "cpi_bridge", "cleveland"],
                "input_hashes": {
                    "champion": f"sha256:champion:{release_type}:{period}",
                    "cpi_bridge": f"sha256:bridge:{release_type}:{period}",
                },
            },
        },
    }
    if current_components and release_type == "cpi_headline":
        entry["shadows"] = {
            "cpi_bridge": {
                "weight_coverage": 0.8,
                "prior_driven_share": 0.2,
                "weight_basis": "bls_dec_2025_starting_relative_importance_fixed_approximation",
                "weight_basis_warning": "BLS relative importance evolves monthly",
                "known_scope_mismatches": [
                    {
                        "series": "CUSR0000SASLE",
                        "warning": "includes shelter; not core services ex shelter",
                    }
                ],
                "components": [
                    {
                        "block": "energy_gasoline",
                        "mom_est": 1.2,
                        "weight": 3.0,
                        "contribution_pp": 0.036,
                        "confidence": 1.0,
                        "prior_only": False,
                        "degraded": False,
                        "legs_used": 1,
                        "legs_expected": 1,
                        "missing_legs": [],
                    },
                    {
                        "block": "unmodelled_residual",
                        "mom_est": 0.2,
                        "weight": 20.0,
                        "contribution_pp": 0.04,
                        "confidence": 0.0,
                        "prior_only": True,
                        "degraded": False,
                        "legs_used": 0,
                        "legs_expected": 0,
                        "missing_legs": [],
                    },
                ],
            }
        }
    return entry


def _fixture(root: Path) -> None:
    periods = 16
    _write_series(
        root,
        "CPIAUCSL",
        "headline_cpi",
        list(100.0 * np.power(1.01, np.arange(periods))),
    )
    _write_series(
        root,
        "CPILFESL",
        "core_cpi",
        list(100.0 * np.power(1.005, np.arange(periods))),
    )
    _write_series(root, "STICKCPIM157SFRBATL", "sticky_cpi", [0.2] * periods)
    _write_series(root, "FLEXCPIM157SFRBATL", "flex_cpi", [0.1] * periods)

    _write_json(root / "data" / "release_forecast" / "latest.json", {
        "schema": "release_forecast.v2",
        "asof": "2026-08-08T16:19:51Z",
        "display_only": True,
        "upcoming": [
            _entry("cpi_headline", "2026-07", "2026-08-12", 0.2),
            _entry("cpi_core", "2026-07", "2026-08-12", 0.3),
            _entry("cpi_headline", "2026-08", "2026-09-11", 0.4, current_components=True),
            _entry("cpi_core", "2026-08", "2026-09-11", 0.25),
        ],
    })
    _write_jsonl(root / "data" / "release_forecast" / "forward_ledger.jsonl", [
        {
            "row_type": "projection",
            "asof_night": "2026-08-01",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 0.1,
            "projection_p10": -0.1,
            "projection_p90": 0.3,
            "model_epoch": "champion-model:cpi_headline",
            "target_epoch": "coherent-target:cpi_headline",
            "code_receipt": "git:ledger-0801",
            "inputs_hash": "sha256:ledger-inputs-0801",
            "input_snapshot_ref": "snapshots/ledger-0801.json",
        },
        {
            "row_type": "projection",
            "asof_night": "2026-08-05",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 0.2,
        },
        # Same-asof append replaces the earlier receipt in the compact evolution.
        {
            "row_type": "projection",
            "asof_night": "2026-08-05",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 0.22,
            "prediction_id": "latest-same-day",
            "model_epoch": "champion-model:cpi_headline",
            "target_epoch": "coherent-target:cpi_headline",
            "code_receipt": "git:ledger-0805",
            "inputs_hash": "sha256:ledger-inputs-0805",
            "input_snapshot_ref": "snapshots/ledger-0805.json",
        },
        # A shadow model must not contaminate the champion evolution path.
        {
            "row_type": "shadow_projection",
            "model": "combined_v1",
            "asof_night": "2026-08-05",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 9.9,
        },
        {
            "row_type": "projection",
            "asof_night": "2026-08-05",
            "release": "cpi_core",
            "period": "2026-07",
            "projection_point": 0.3,
        },
        {
            "row_type": "projection",
            "asof_night": "2026-08-05",
            "release": "cpi_headline",
            "period": "2026-08",
            "projection_point": 0.4,
        },
        # The append-only ledger may be newer than a historical artifact build.
        # Later and unparseable clocks must fail closed for each matching target.
        {
            "row_type": "projection",
            "asof_night": "2026-08-09",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 8.9,
        },
        {
            "row_type": "projection",
            "asof_night": "not-a-date",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 7.7,
        },
        {
            "row_type": "projection",
            "asof_night": "2026-08",
            "release": "cpi_headline",
            "period": "2026-07",
            "projection_point": 7.6,
        },
        {
            "row_type": "projection",
            "asof_night": "2026-08-09",
            "release": "cpi_headline",
            "period": "2026-08",
            "projection_point": 6.6,
        },
    ])


def test_contract_separates_three_inflation_clocks(tmp_path: Path) -> None:
    _fixture(tmp_path)
    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)

    assert state["schema"] == "inflation_intelligence.v1"
    assert state["display_only"] is True
    assert state["authority"] is False
    assert all(value is False for value in state["allowed_actions"].values())
    assert {
        "released_state",
        "next_release_forecast",
        "current_month_proxy_pressure",
    } <= set(state)

    assert state["released_state"]["headline"]["observation_period"] == "2026-08"
    assert state["next_release_forecast"]["period"] == "2026-07"
    assert state["next_release_forecast"]["release_date"] == "2026-08-12"
    assert state["current_month_proxy_pressure"]["period"] == "2026-08"
    assert state["freshness"]["status"] == "current_with_publication_lag"
    assert "rebuilding this wrapper" in state["freshness"]["policy"]

    rendered = json.dumps(state).lower()
    assert "current cpi" not in rendered
    assert "not an official cpi observation" in rendered


def test_released_state_uses_exact_3m_6m_annualization(tmp_path: Path) -> None:
    _fixture(tmp_path)
    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)
    headline = state["released_state"]["headline"]
    expected = ((1.01**12) - 1.0) * 100.0
    assert headline["mom_pct"] == pytest.approx(1.0, abs=1e-6)
    assert headline["annualized_3m_pct"] == pytest.approx(expected, abs=1e-6)
    assert headline["annualized_6m_pct"] == pytest.approx(expected, abs=1e-6)
    assert headline["acceleration_3m_minus_6m_pp"] == pytest.approx(0.0, abs=1e-6)
    assert headline["revision_basis"] == "latest_local_fred_not_original_release_vintage"

    sticky = state["released_state"]["underlying_proxies"]["sticky"]
    sticky_expected = ((1.002**12) - 1.0) * 100.0
    assert sticky["annualized_3m_pct"] == pytest.approx(sticky_expected, abs=1e-6)


def test_forecast_evolution_is_append_order_deduped_and_shadow_free(tmp_path: Path) -> None:
    _fixture(tmp_path)
    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)
    evolution = state["next_release_forecast"]["headline"]["forecast_evolution"]
    assert evolution["n_points"] == 2
    assert [point["asof"] for point in evolution["points"]] == ["2026-08-01", "2026-08-05"]
    assert evolution["points"][-1]["point"] == pytest.approx(0.22)
    assert evolution["points"][-1]["prediction_id"] == "latest-same-day"
    assert evolution["points"][-1]["code_receipt"] == "git:ledger-0805"
    assert evolution["points"][-1]["inputs_hash"] == "sha256:ledger-inputs-0805"
    assert all(point["point"] != 9.9 for point in evolution["points"])
    assert all(point["point"] not in {7.6, 7.7, 8.9} for point in evolution["points"])
    assert evolution["cutoff_asof"] == _AS_OF
    assert evolution["excluded_after_cutoff"] == 1
    assert evolution["excluded_unparseable_asof"] == 2


def test_forecast_evolution_uses_artifact_or_explicit_historical_cutoff(
    tmp_path: Path,
) -> None:
    _fixture(tmp_path)

    # With no caller override, the Release Radar artifact asof is authoritative.
    artifact_clock = build_inflation_intelligence(tmp_path)
    evolution = artifact_clock["next_release_forecast"]["headline"]["forecast_evolution"]
    assert artifact_clock["asof"] == _AS_OF
    assert evolution["cutoff_asof"] == _AS_OF
    assert evolution["last_asof"] == "2026-08-05"

    # A replay resolved to an earlier day may not see rows appended afterward.
    historical = build_inflation_intelligence(tmp_path, as_of="2026-08-03")
    historical_evolution = historical["next_release_forecast"]["headline"][
        "forecast_evolution"
    ]
    assert [point["asof"] for point in historical_evolution["points"]] == [
        "2026-08-01"
    ]
    assert historical_evolution["cutoff_asof"] == "2026-08-03"
    assert historical_evolution["last_asof"] == "2026-08-01"
    assert historical_evolution["excluded_after_cutoff"] == 3

    pressure_evolution = artifact_clock["current_month_proxy_pressure"][
        "headline_model_pressure"
    ]["forecast_evolution"]
    assert [point["asof"] for point in pressure_evolution["points"]] == ["2026-08-05"]
    assert pressure_evolution["excluded_after_cutoff"] == 1


def test_forecast_provenance_and_combined_basis_are_preserved(tmp_path: Path) -> None:
    _fixture(tmp_path)
    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)
    target = state["next_release_forecast"]["headline"]

    assert target["model_epoch"] == "champion-model:cpi_headline"
    assert target["target_epoch"] == "coherent-target:cpi_headline"
    assert target["code_receipt"] == "git:0123456789abcdef"
    assert target["inputs_hash"] == "sha256:champion-inputs:cpi_headline:2026-07"
    assert target["input_snapshot_ref"] == "snapshots/cpi_headline_2026-07.json"
    assert target["primary_forecast_basis"] == "combined_v1_benchmark_augmented"
    assert target["context_metrics_basis"] == "champion_legacy_target_v1"
    assert target["basis_warning"].startswith("Combined point")

    combined = target["combined_display_estimate"]
    assert combined["model_epoch"] == "combined-model:cpi_headline"
    assert combined["target_epoch"] == "combined-target:cpi_headline"
    assert combined["code_receipt"] == "git:combined012345"
    assert combined["inputs_hash"] == "sha256:combined:cpi_headline:2026-07"
    assert combined["input_hashes"]["cpi_bridge"] == (
        "sha256:bridge:cpi_headline:2026-07"
    )


def test_component_freshness_and_coverage_are_explicit(tmp_path: Path) -> None:
    _fixture(tmp_path)
    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)
    pressure = state["current_month_proxy_pressure"]
    assert pressure["coverage"]["bridge_known_scope_mismatches"][0]["series"] == (
        "CUSR0000SASLE"
    )
    assert "evolves monthly" in pressure["coverage"]["bridge_weight_basis_warning"]
    components = {row["component"]: row for row in pressure["component_freshness"]}
    assert components["energy_gasoline"]["status"] == "proxy_available"
    assert components["unmodelled_residual"]["status"] == "prior_only"
    assert pressure["coverage"]["radar_fresh_proxy_coverage"] == pytest.approx(0.75)
    assert pressure["coverage"]["bridge_modelled_weight_coverage"] == pytest.approx(0.8)
    assert pressure["coverage"]["revision_optimistic_legs"] == ["shelter_nowcast"]
    combined = pressure["headline_model_pressure"]["combined_display_estimate"]
    assert combined["includes_external_benchmark"] is True
    assert combined["authority"] is False


def test_missing_inputs_fail_open_and_writer_emits_valid_json(tmp_path: Path) -> None:
    state, target = write_inflation_intelligence(tmp_path, as_of=_AS_OF)
    assert target.exists()
    assert json.loads(target.read_text()) == state
    assert state["released_state"]["available"] is False
    assert state["next_release_forecast"]["available"] is False
    assert state["current_month_proxy_pressure"]["available"] is False
    assert state["gaps"]
    assert state["authority"] is False


def test_malformed_ledger_row_is_quarantined_not_fatal(tmp_path: Path) -> None:
    _fixture(tmp_path)
    ledger = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)
    status = state["source_status"]["release_radar_forward_ledger"]
    assert status["available"] is True
    assert status["malformed_rows"] == 1
    assert any("malformed_rows:1" in gap for gap in state["gaps"])


def test_fresh_wrapper_does_not_hide_stale_underlying_monthly_sources(
    tmp_path: Path,
) -> None:
    for series_id, column in (
        ("CPIAUCSL", "headline_cpi"),
        ("CPILFESL", "core_cpi"),
        ("STICKCPIM157SFRBATL", "sticky_cpi"),
        ("FLEXCPIM157SFRBATL", "flex_cpi"),
    ):
        _write_series(tmp_path, series_id, column, [100.0, 101.0, 102.0])
    _write_json(
        tmp_path / "data" / "release_forecast" / "latest.json",
        {"schema": "release_forecast.v2", "asof": f"{_AS_OF}T02:00:00Z", "upcoming": []},
    )
    _write_jsonl(
        tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl",
        [],
    )

    state = build_inflation_intelligence(tmp_path, as_of=_AS_OF)

    assert state["asof"] == _AS_OF
    assert state["freshness"]["status"] == "degraded"
    assert any(
        reason.startswith("fred:CPIAUCSL:stale:")
        for reason in state["freshness"]["degraded_reasons"]
    )
    assert state["released_state"]["headline"]["freshness_status"] == "stale"
    assert state["source_status"]["fred"]["headline"]["freshness_status"] == "stale"


def test_cli_writes_requested_output(tmp_path: Path) -> None:
    _fixture(tmp_path)
    custom = tmp_path / "out" / "inflation.json"
    rc = main(["--root", str(tmp_path), "--as-of", _AS_OF, "--output", str(custom)])
    assert rc == 0
    assert custom.exists()
    assert json.loads(custom.read_text())["schema"] == "inflation_intelligence.v1"
