"""Deterministic detector formulas, boundaries, evidence, and failure states."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.fundamental_forensics import load_registry, run_fixture_slice
from engine.moat_falsifiers import (
    _sensor_capex_intensity,
    _sensor_inventory_build,
    _sensor_margin_compression,
    _sensor_receivables_stretch,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
REGISTRY_PATH = ROOT / "config" / "fundamental_forensics.yml"
LATEST_ACCESSION = "0000000001-25-000001"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _set_value(payload, concept: str, accession: str, period_end: str, value) -> None:
    entries = payload["facts"]["us-gaap"][concept]["units"]["USD"]
    target = next(
        entry for entry in entries
        if entry.get("accn") == accession and entry.get("end") == period_end
    )
    target["val"] = value


def _remove_value(payload, concept: str, accession: str, period_end: str) -> None:
    entries = payload["facts"]["us-gaap"][concept]["units"]["USD"]
    payload["facts"]["us-gaap"][concept]["units"]["USD"] = [
        entry for entry in entries
        if not (entry.get("accn") == accession and entry.get("end") == period_end)
    ]


def _run(payload=None):
    return run_fixture_slice(
        payload or _load("companyfacts_versions.json"),
        _load("submissions_versions.json"),
        load_registry(REGISTRY_PATH),
        as_of="2025-12-31T23:59:59Z",
        recorded_at="2026-08-01T12:00:00Z",
        computed_at="2026-08-01T12:05:00Z",
        knowledge_clock="source_event",
        vintage_policy="latest_known",
    )


def _states(result):
    return {finding.detector_id: finding.state.value for finding in result.findings}


def test_fixture_triggers_all_five_and_evidence_is_exact() -> None:
    result = _run()
    assert len(result.findings) == 5
    assert set(_states(result).values()) == {"triggered"}
    for finding in result.findings:
        assert finding.display_only is True
        assert finding.authority == "review_priority_only"
        assert finding.detector_version == "fundamental-forensics-five/v1"
        assert set(finding.evidence_observation_ids) == {
            item.observation_id for item in finding.inputs
        }
        assert set(finding.evidence_fact_ids) == {
            fact_id for item in finding.inputs for fact_id in item.fact_ids
        }


@pytest.mark.parametrize(
    ("concept", "value", "detector_id"),
    [
        ("GrossProfit", 560, "margin_compression_despite_revenue_growth"),
        ("AccountsReceivableNetCurrent", 127, "receivables_stretch"),
        ("InventoryNet", 132, "inventory_build"),
        ("PaymentsToAcquirePropertyPlantAndEquipment", 127, "capital_intensity_rising"),
        ("NetCashProvidedByUsedInOperatingActivities", 160, "accruals_trending_up"),
    ],
)
def test_each_detector_has_a_clear_case(concept, value, detector_id) -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _set_value(payload, concept, LATEST_ACCESSION, "2024-12-31", value)
    assert _states(_run(payload))[detector_id] == "clear"


def test_missing_input_is_explicitly_not_evaluable() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _remove_value(payload, "GrossProfit", LATEST_ACCESSION, "2024-12-31")
    result = _run(payload)
    finding = next(
        item for item in result.findings
        if item.detector_id == "margin_compression_despite_revenue_growth"
    )
    assert finding.state.value == "not_evaluable"
    assert finding.applicability == "insufficient_evidence"
    assert finding.missing_inputs == ("gross_profit@2024-12-31",)


def test_missing_operating_income_does_not_take_revenue_only_branch() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _remove_value(payload, "OperatingIncomeLoss", LATEST_ACCESSION, "2024-12-31")
    finding = next(
        item for item in _run(payload).findings
        if item.detector_id == "capital_intensity_rising"
    )
    assert finding.state.value == "not_evaluable"
    assert "operating_income@2024-12-31" in finding.missing_inputs


def test_margin_three_percent_boundary_is_inclusive() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2023-12-31", 1000)
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2024-12-31", 1030)
    _set_value(payload, "GrossProfit", LATEST_ACCESSION, "2023-12-31", 500)
    _set_value(payload, "GrossProfit", LATEST_ACCESSION, "2024-12-31", 500)
    assert _states(_run(payload))["margin_compression_despite_revenue_growth"] == "triggered"


def test_receivables_ten_point_gap_boundary_is_strict() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2023-12-31", 1000)
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2024-12-31", 1030)
    _set_value(payload, "AccountsReceivableNetCurrent", LATEST_ACCESSION, "2023-12-31", 100)
    _set_value(payload, "AccountsReceivableNetCurrent", LATEST_ACCESSION, "2024-12-31", 113)
    assert _states(_run(payload))["receivables_stretch"] == "clear"


def test_inventory_fifteen_point_gap_boundary_is_strict() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2023-12-31", 1000)
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2024-12-31", 1030)
    _set_value(payload, "InventoryNet", LATEST_ACCESSION, "2023-12-31", 100)
    _set_value(payload, "InventoryNet", LATEST_ACCESSION, "2024-12-31", 118)
    assert _states(_run(payload))["inventory_build"] == "clear"


def test_capex_ten_point_gap_boundary_is_strict() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2023-12-31", 1000)
    _set_value(payload, "RevenueFromContractWithCustomerExcludingAssessedTax", LATEST_ACCESSION, "2024-12-31", 1030)
    _set_value(payload, "PaymentsToAcquirePropertyPlantAndEquipment", LATEST_ACCESSION, "2023-12-31", 100)
    _set_value(payload, "PaymentsToAcquirePropertyPlantAndEquipment", LATEST_ACCESSION, "2024-12-31", 113)
    _set_value(payload, "OperatingIncomeLoss", LATEST_ACCESSION, "2023-12-31", 100)
    _set_value(payload, "OperatingIncomeLoss", LATEST_ACCESSION, "2024-12-31", 100)
    assert _states(_run(payload))["capital_intensity_rising"] == "clear"


def test_accrual_three_point_boundary_is_inclusive() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    # Oldest ratio = (100-110)/1000 = -0.01. Latest = (160-136)/1200 = 0.02.
    _set_value(payload, "NetCashProvidedByUsedInOperatingActivities", LATEST_ACCESSION, "2024-12-31", 136)
    finding = next(
        item for item in _run(payload).findings if item.detector_id == "accruals_trending_up"
    )
    assert finding.state.value == "triggered"
    assert dict(finding.derived_values)["accrual_ratio_change"] == "0.03"


def test_nonadjacent_annual_periods_are_not_compared() -> None:
    payload = deepcopy(_load("companyfacts_versions.json"))
    for concept in payload["facts"]["us-gaap"].values():
        entries = concept["units"].get("USD", [])
        concept["units"]["USD"] = [
            entry for entry in entries if entry.get("end") != "2023-12-31"
        ]
    assert set(_states(_run(payload)).values()) == {"not_evaluable"}


def test_complete_rows_match_existing_four_sensor_booleans() -> None:
    result = _run()
    observation_by_id = {item.observation_id: item for item in result.observations}
    selected = [
        item for item in result.statement_vintages
        if item.vintage_id in result.selected_vintage_ids
    ][-2:]

    def row(vintage):
        metrics = vintage.metrics()
        aliases = {
            "revenue": "revenue", "gross_profit": "gross_profit",
            "accounts_receivable": "receivables", "inventory": "inventory",
            "capital_expenditures": "capex", "operating_income": "op_income",
        }
        return pd.Series({
            target: float(observation_by_id[metrics[source]].value)
            for source, target in aliases.items()
        })

    prior, current = row(selected[0]), row(selected[1])
    old = {
        "margin_compression_despite_revenue_growth": _sensor_margin_compression(current, prior),
        "receivables_stretch": _sensor_receivables_stretch(current, prior),
        "inventory_build": _sensor_inventory_build(current, prior),
        "capital_intensity_rising": _sensor_capex_intensity(current, prior),
    }
    new = _states(result)
    assert {name: new[name] == "triggered" for name in old} == old
