"""Contract tests for the governed core GAAP metric registry."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
import yaml

from engine.fundamental_forensics.models import canonical_json
from engine.fundamental_forensics.metric_registry import (
    ALLOWED_CONFIDENCE,
    CORE_V1_DIRECT_METRIC_COUNT,
    CORE_V1_FORMULA_METRIC_COUNT,
    load_core_metric_registry,
    metric_registry_from_dicts,
)


ROOT = Path(__file__).resolve().parent.parent
METRICS_ROOT = ROOT / "config" / "fundamental_forensics" / "metrics" / "v1"


def _raw() -> tuple[dict, dict, dict]:
    return tuple(
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in (
            METRICS_ROOT / "metric_catalog.yaml",
            METRICS_ROOT / "mappings" / "core.yaml",
            METRICS_ROOT / "formulas" / "core.yaml",
        )
    )


def _pin_digest(raw: dict) -> None:
    content = dict(raw)
    content.pop("content_sha256", None)
    raw["content_sha256"] = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def _pin_all(raw: tuple[dict, dict, dict]) -> None:
    for document in raw:
        _pin_digest(document)


def _registry(raw: tuple[dict, dict, dict] | None = None, *, repin: bool = True):
    catalog, mappings, formulas = raw or _raw()
    if repin:
        _pin_all((catalog, mappings, formulas))
    return metric_registry_from_dicts(catalog, mappings, formulas)


def _metric(catalog: dict, metric_id: str) -> dict:
    return next(item for item in catalog["metrics"] if item["metric_id"] == metric_id)


def _formula(formulas: dict, metric_id: str) -> dict:
    return next(item for item in formulas["formulas"] if item["metric_id"] == metric_id)


def test_core_registry_has_exactly_fifty_complete_no_fallback_contracts() -> None:
    registry = load_core_metric_registry(ROOT)

    assert len(registry.contracts) == 50
    assert sum(contract.formula is None for contract in registry.contracts) == CORE_V1_DIRECT_METRIC_COUNT
    assert sum(contract.formula is not None for contract in registry.contracts) == CORE_V1_FORMULA_METRIC_COUNT
    assert len(set(registry.metric_ids)) == 50
    assert registry.available_at.tzinfo is not None
    assert len(registry.catalog_content_sha256) == 64
    assert registry.mapping_pack_available_at.tzinfo is not None
    assert registry.formula_pack_available_at.tzinfo is not None
    assert len(registry.mapping_pack_content_sha256) == 64
    assert len(registry.formula_pack_content_sha256) == 64
    assert {contract.category for contract in registry.contracts} >= {
        "income_statement", "cash_flow", "balance_sheet", "working_capital", "debt_cash", "shares"
    }
    for contract in registry.contracts:
        assert contract.rule_id.endswith("/v1")
        assert contract.version == "1.0.0"
        assert contract.available_at.tzinfo is not None
        assert contract.confidence in ALLOWED_CONFIDENCE
        assert contract.units
        assert contract.period_constraints.kind in {"instant", "duration"}
        assert contract.dimensional_profile.mode == "consolidated_only"
        assert contract.presentation_constraints.statement
        assert contract.review.triggers
        assert contract.no_result.mode == "withhold"
        assert contract.no_result.codes
        assert bool(contract.mappings) ^ bool(contract.formula)


def test_direct_mapping_contract_has_standard_aliases_and_derived_contract_has_dag_inputs() -> None:
    registry = load_core_metric_registry(ROOT)
    revenue = registry.metric("revenue")
    margin = registry.metric("gross_margin")

    assert revenue.units == ("USD",)
    assert revenue.formula is None
    assert [alias.taxonomy for alias in revenue.taxonomy_concept_aliases] == [
        "us-gaap", "us-gaap", "us-gaap"
    ]
    assert revenue.taxonomy_concept_aliases[0].concept == (
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert revenue.taxonomy_concept_aliases[0].taxonomy_version_end == 2026
    assert margin.mappings == ()
    assert margin.formula is not None
    assert margin.formula_dependencies == ("gross_profit", "revenue")
    assert margin.formula.dependency_period_alignment == "same_period"


def test_only_governed_standard_taxonomy_concepts_and_version_ranges_are_admitted() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    mappings["mappings"][0]["taxonomy_concept_aliases"][0]["taxonomy"] = "acme-2026"

    with pytest.raises(ValueError, match="issuer-extension"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    mappings["mappings"][0]["taxonomy_concept_aliases"][0]["concept"] = "MadeUpRevenue"
    with pytest.raises(ValueError, match="known-concept allowlist"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    mappings["mappings"][0]["taxonomy_concept_aliases"][1]["taxonomy_version_end"] = 2026
    with pytest.raises(ValueError, match="governed version range"):
        _registry((catalog, mappings, formulas))


def test_duplicate_metric_and_cross_metric_alias_are_rejected() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    catalog["metrics"].append(deepcopy(catalog["metrics"][0]))
    with pytest.raises(ValueError, match="requires exactly 50"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    mappings["mappings"][1]["taxonomy_concept_aliases"][0]["concept"] = (
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    with pytest.raises(ValueError, match="duplicate standard concept alias"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    duplicate = deepcopy(mappings["mappings"][0])
    duplicate["rule"]["rule_id"] = "mapping.revenue_duplicate/v1"
    mappings["mappings"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate standard concept alias"):
        _registry((catalog, mappings, formulas))


def test_content_digests_are_pinned_and_detect_unversioned_rule_content_changes() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    mappings["mappings"][0]["taxonomy_concept_aliases"][2]["concept"] = "RevenueRemainingPerformanceObligation"

    with pytest.raises(ValueError, match="content_sha256 does not match"):
        _registry((catalog, mappings, formulas), repin=False)


def test_current_portion_of_long_term_debt_prevents_total_debt_omission() -> None:
    registry = load_core_metric_registry(ROOT)
    total_debt = registry.metric("total_debt")

    assert "cash_conversion_ratio" not in registry.metric_ids
    assert registry.metric("long_term_debt_current").taxonomy_concept_aliases[0].concept == (
        "LongTermDebtCurrent"
    )
    assert total_debt.formula_dependencies == (
        "short_term_debt", "long_term_debt_current", "long_term_debt"
    )


def test_unknown_formula_dependency_and_formula_cycle_are_rejected() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "gross_margin")["formula_dependencies"] = ["not_a_metric"]
    _formula(formulas, "gross_margin").update(
        {"dependencies": ["not_a_metric"], "expression": "not_a_metric"}
    )
    with pytest.raises(ValueError, match="unknown dependencies"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "total_debt")["formula_dependencies"] = [
        "cash_to_total_debt",
        "stockholders_equity",
    ]
    _formula(formulas, "total_debt").update(
        {
            "dependencies": ["cash_to_total_debt", "stockholders_equity"],
            "expression": "cash_to_total_debt * stockholders_equity",
        }
    )
    with pytest.raises(ValueError, match="contains a cycle"):
        _registry((catalog, mappings, formulas))


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("gross_profit / unrelated", "identifiers must exactly equal"),
        ("__import__('os')", "unsupported expression construct"),
    ],
)
def test_formula_ast_is_restricted_and_bound_to_declared_dependencies(expression: str, message: str) -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    _formula(formulas, "gross_margin")["expression"] = expression

    with pytest.raises(ValueError, match=message):
        _registry((catalog, mappings, formulas))


def test_formula_unit_algebra_and_direct_formula_split_are_governed() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    _formula(formulas, "gross_margin")["expression"] = "gross_profit + revenue"
    with pytest.raises(ValueError, match="unit algebra"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    metric = _metric(catalog, "research_and_development_expense")
    metric["formula_dependencies"] = ["revenue"]
    metric["review"] = {
        "required": True,
        "triggers": ["missing_dependency"],
    }
    metric["no_result"] = {
        "mode": "withhold",
        "codes": ["missing_dependency", "incompatible_dependencies", "division_by_zero"],
    }
    mappings["mappings"] = [
        item
        for item in mappings["mappings"]
        if item["metric_id"] != "research_and_development_expense"
    ]
    formulas["formulas"].append(
        {
            "metric_id": "research_and_development_expense",
            "rule": {
                "rule_id": "formula.research_and_development_expense/v1",
                "version": "1.0.0",
                "available_at": "2026-08-02T00:00:00Z",
                "confidence": "A",
            },
            "expression": "revenue",
            "dependencies": ["revenue"],
            "output_unit": "USD",
            "dependency_period_alignment": "same_period",
        }
    )
    with pytest.raises(ValueError, match="40 direct and 10 formula"):
        _registry((catalog, mappings, formulas))


def test_formula_period_geometry_and_point_in_time_dependency_clocks_fail_closed() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "revenue")["period_constraints"] = {
        "kind": "instant",
        "allowed_forms": ["10-K", "10-K/A", "10-Q", "10-Q/A"],
    }
    with pytest.raises(ValueError, match="does not match revenue period"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "gross_margin")["period_constraints"] = {
        "kind": "instant",
        "allowed_forms": ["10-K", "10-K/A", "10-Q", "10-Q/A"],
    }
    with pytest.raises(ValueError, match="same_period alignment"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "total_debt")["rule"]["available_at"] = "2026-08-03T00:00:00Z"
    _formula(formulas, "total_debt")["rule"]["available_at"] = "2026-08-03T00:00:00Z"
    with pytest.raises(ValueError, match="cannot predate dependency availability"):
        _registry((catalog, mappings, formulas))


@pytest.mark.parametrize(
    ("target", "metric_id"),
    [("mapping", "revenue"), ("formula", "gross_margin")],
)
def test_mapping_and_formula_confidence_must_match_metric_contract(target: str, metric_id: str) -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    if target == "mapping":
        next(item for item in mappings["mappings"] if item["metric_id"] == metric_id)["rule"]["confidence"] = "D"
    else:
        _formula(formulas, metric_id)["rule"]["confidence"] = "D"

    with pytest.raises(ValueError, match="confidence must match"):
        _registry((catalog, mappings, formulas))


def test_no_result_contracts_are_not_merely_free_text() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "revenue")["no_result"]["codes"].remove("missing_standard_fact")
    with pytest.raises(ValueError, match="required fail-closed"):
        _registry((catalog, mappings, formulas))

    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "gross_margin")["review"]["required"] = False
    with pytest.raises(ValueError, match="must require review"):
        _registry((catalog, mappings, formulas))


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda catalog, mappings, formulas: _metric(catalog, "revenue")["rule"].update(
                {"available_at": "2026-08-02T00:00:00"}
            ),
            "timezone",
        ),
        (
            lambda catalog, mappings, formulas: _metric(catalog, "revenue").update({"units": ["EUR"]}),
            "unsupported",
        ),
        (
            lambda catalog, mappings, formulas: _metric(catalog, "revenue")["period_constraints"].update(
                {"kind": "rolling"}
            ),
            "period_constraints.kind",
        ),
        (
            lambda catalog, mappings, formulas: _metric(catalog, "revenue")["rule"].update(
                {"confidence": "Z"}
            ),
            "A/B/C/D",
        ),
    ],
)
def test_clocks_units_period_constraints_and_confidence_fail_closed(mutator, message: str) -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    mutator(catalog, mappings, formulas)

    with pytest.raises(ValueError, match=message):
        _registry((catalog, mappings, formulas))


def test_confidence_d_is_a_supported_review_tier_not_an_implicit_rejection() -> None:
    catalog, mappings, formulas = deepcopy(_raw())
    _metric(catalog, "revenue")["rule"]["confidence"] = "D"
    next(item for item in mappings["mappings"] if item["metric_id"] == "revenue")["rule"][
        "confidence"
    ] = "D"

    assert _registry((catalog, mappings, formulas)).metric("revenue").confidence == "D"
