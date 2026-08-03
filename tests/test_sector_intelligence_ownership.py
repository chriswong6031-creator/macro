from __future__ import annotations

import ast
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest
import yaml

from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_REGISTRY = ROOT / "config" / "sector_intelligence_ownership.yml"
ADAPTER_FIXTURE = (
    ROOT / "data" / "biocatalyst" / "fixtures" / "shared_plane_read_adapters.v1.json"
)
_FIXTURE_PATH = "data/biocatalyst/fixtures/shared_plane_read_adapters.v1.json"
_ADAPTER_FIELDS = (
    "canonical_owner",
    "implementation_state",
    "module",
    "callable",
    "route_prefix",
    "routes",
    "input_identity",
    "output_contracts",
    "transport",
    "point_in_time_scope",
    "available_dependency",
    "compatibility_fixture",
    "biocatalyst_eligible",
    "limitations",
    "blocker",
)
_LIST_DEFAULTS = frozenset({"routes", "output_contracts", "limitations"})


def _registry() -> dict:
    payload = yaml.safe_load(OWNERSHIP_REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _normalized_read_adapter_projection(adapters: dict) -> dict:
    """Return the complete stable fixture projection, including absent=null slots.

    The fixture is intentionally more explicit than the YAML registry: a missing
    field must be represented as either ``null`` or an empty list, so an adapter
    cannot silently acquire a route, output contract, or callable between
    reconciliations.
    """

    projected: dict[str, dict] = {}
    for name, raw_adapter in adapters.items():
        assert isinstance(name, str)
        assert isinstance(raw_adapter, dict)
        assert set(raw_adapter) <= set(_ADAPTER_FIELDS)
        projected[name] = {
            field: raw_adapter.get(field, [] if field in _LIST_DEFAULTS else None)
            for field in _ADAPTER_FIELDS
        }
    return projected


def _module_tree(module_name: str) -> ast.Module:
    """Read a first-party module without importing a potentially heavy dependency."""

    path = ROOT.joinpath(*module_name.split(".")).with_suffix(".py")
    assert path.is_file(), f"declared adapter module is absent: {module_name}"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _declared_functions(module_name: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(_module_tree(module_name))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _declared_classes(module_name: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(_module_tree(module_name))
        if isinstance(node, ast.ClassDef)
    }


def _declared_string_constant(module_name: str, name: str) -> str:
    for node in _module_tree(module_name).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError(f"{module_name} does not declare string constant {name}")


def _declared_router_get_paths(module_name: str) -> set[str]:
    paths: set[str] = set()
    for node in ast.walk(_module_tree(module_name)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "get"
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            paths.add(decorator.args[0].value)
    return paths


def test_ownership_policy_is_one_writer_and_fail_closed() -> None:
    registry = _registry()

    assert registry["schema"] == "sector_intelligence_ownership.v1"
    assert registry["status"] == "f0_reconciled_partial_freeze"
    assert registry["reconciled_against_commit"] == (
        "c2d466f2f568cc4c730d68ced758fafde0c6257a"
    )
    policy = registry["policy"]
    assert policy["one_writer_required"] is True
    assert policy["cross_domain_access"] == "versioned_read_adapter_only"
    assert policy["unresolved_owner_behavior"] == "block_or_degrade"
    assert policy["duplicate_writer_behavior"] == "hard_fail"

    activation = registry["runtime_controls"]["biocatalyst_prospective_accrual"]
    assert activation["operational_owner"] == "mastermindx_platform_ops"
    assert activation["implementation_state"] == "implemented_b4e_dark_until_external_seal"
    assert activation["worker_gate"]["access"] == "root_write_worker_read_only"
    assert (
        activation["worker_gate"]["failure_behavior"]
        == "quarantine_before_collection_store_or_pointer_mutation"
    )
    assert activation["credential_planes"]["control_token_visible_to_worker"] is False
    assert activation["deprecated_non_authority"] == {
        "BIOCATALYST_R2_RETENTION_CONFIRMED": "cannot authorize prospective collection"
    }


def test_biocatalyst_owns_only_declared_source_canonical_and_dark_regulatory_lanes() -> None:
    registrations = _registry()["registrations"]
    owned = {
        name
        for name, registration in registrations.items()
        if registration["canonical_owner"] == "biocatalyst"
    }

    assert owned == {
        "clinicaltrials_source_record",
        "trial_snapshot_and_exact_diff",
        "biocatalyst_read_projection",
        "drugs_at_fda_release_archive",
        "drugs_at_fda_private_query_index",
    }
    for name, expected_state in {
        "clinicaltrials_source_record": "frozen_for_b0a",
        "trial_snapshot_and_exact_diff": "implemented_b4d_retention_gated",
        "biocatalyst_read_projection": "implemented_b4d_retention_gated",
    }.items():
        registration = registrations[name]
        assert registration["implementation_state"] == expected_state
        assert registration["writer"] is not None
        assert registration["operational_owner"] == "mastermindx_platform_ops"

    prospective_writer = registrations["trial_snapshot_and_exact_diff"]["writer"]
    assert prospective_writer["module"] == "engine.biocatalyst.prospective"
    assert {
        "trial_snapshot_observation.v1",
        "trial_version_diff.v1",
        "trial_coverage_epoch.v1",
    } <= set(prospective_writer["schemas"])

    public_writer = registrations["biocatalyst_read_projection"]["writer"]
    assert public_writer["module"] == "engine.biocatalyst.publication"
    assert "trial_prospective_change_read_model.v1" in public_writer["schemas"]
    for name in {
        "drugs_at_fda_release_archive",
        "drugs_at_fda_private_query_index",
    }:
        registration = registrations[name]
        assert registration["implementation_state"] == "dark_b4a_private_only"
        assert registration["writer"] is not None
        assert registration["operational_owner"] == "mastermindx_platform_ops"
        assert registration["source_rights_gate"] == {
            "source_registry": "drugs_at_fda",
            "production_ingest_allowed": False,
            "public_projection": "blocked_until_review",
        }
        assert "public_projection" in registration["prohibited_uses"]
        assert any(
            "prophet" in prohibited
            for prohibited in registration["prohibited_uses"]
        )


def test_shared_company_document_and_capital_lanes_are_not_faked() -> None:
    registrations = _registry()["registrations"]

    for name, expected_owner in {
        "generic_company_identity": "corporate_intelligence",
        "corporate_documents_and_spans": "corporate_intelligence",
    }.items():
        registration = registrations[name]
        assert registration["canonical_owner"] == expected_owner
        assert registration["writer"] is None
        assert registration["implementation_state"] in {
            "partial_ticker_context_reader_not_pit_identity",
            "owner_substrates_exist_no_biocatalyst_read_contract",
        }

    capital = registrations["capital_structure_projection"]
    assert capital["canonical_owner"] == "capital_structure"
    assert capital["implementation_state"] == (
        "current_authenticated_projection_available"
    )
    assert capital["writer"] == {
        "service": "capital_structure_projection_builder",
        "module": "scripts.build_capital_structure_projection",
        "storage_class": "atomic_current_projection_twin",
        "artifact": "data/capital_structure/projection.json",
        "schema": "capital_structure.projection_bundle.v1",
    }


def test_f0_read_adapter_slots_are_exact_and_only_trial_facts_are_eligible() -> None:
    registry = _registry()
    adapters = registry["read_adapters"]
    fixture = json.loads(ADAPTER_FIXTURE.read_text(encoding="utf-8"))

    validate_contract(fixture, repo_root=ROOT)
    assert fixture["contract_id"] == "biocatalyst_shared_plane_read_adapters.v1"
    assert fixture["schema_version"] == "1.0.0"
    assert fixture["baseline_commit"] == registry["reconciled_against_commit"]
    assert fixture["adapters"] == _normalized_read_adapter_projection(adapters)
    assert {
        name for name, adapter in adapters.items() if adapter["biocatalyst_eligible"]
    } == {"biocatalyst_trial_read_api.v1"}

    trial = adapters["biocatalyst_trial_read_api.v1"]
    assert trial["compatibility_fixture"] == _FIXTURE_PATH
    assert trial["route_prefix"] == "/api/biocatalyst/v1"
    assert trial["point_in_time_scope"] == "committed_current_public_generation"
    assert "no_model_or_signal_authority" in trial["limitations"]
    assert set(trial["output_contracts"]) <= set(ContractRegistry(ROOT).contract_ids)

    # This is the sole eligible adapter. Import only its deliberately light
    # serving module, then inspect the actual mounted router rather than trusting
    # a fixture string or static route declaration.
    imported_trial = importlib.import_module(trial["module"])
    trial_router = getattr(imported_trial, trial["callable"])
    runtime_trial_paths = {route.path for route in trial_router.routes}
    assert runtime_trial_paths == set(trial["routes"])
    assert all(path.startswith(f"{trial['route_prefix']}/") for path in runtime_trial_paths)

    company = adapters["biocatalyst_company_identity_pit_adapter.v1"]
    company_dependency = company["available_dependency"]
    assert company_dependency["callable"] in _declared_functions(
        company_dependency["module"]
    )
    assert _declared_string_constant(
        "engine.company_intelligence.contracts", "CONTEXT_SCHEMA"
    ) == company_dependency["output_contract"]

    security = adapters["biocatalyst_security_identity_pit_adapter.v1"]
    security_dependency = security["available_dependency"]
    assert "SymbolDirectoryAdapter" in _declared_classes(security_dependency["module"])
    assert "output_contract" not in security_dependency

    corporate = adapters["biocatalyst_corporate_document_span_adapter.v1"]
    corporate_dependency = corporate["available_dependency"]
    assert {"archive_index_document", "build_filing_manifests"} <= _declared_functions(
        corporate_dependency["module"]
    )

    capital = adapters["biocatalyst_capital_structure_pit_adapter.v1"]
    capital_dependency = capital["available_dependency"]
    assert _declared_router_get_paths(capital_dependency["module"]) == set(
        capital_dependency["routes"]
    )
    assert _declared_string_constant(
        "engine.capital_structure.projection", "PROJECTION_BUNDLE_SCHEMA"
    ) == (
        capital_dependency["output_contract"]
    )
    assert "cash_runway_or_dilution" in capital_dependency["scope"]


def test_future_read_adapter_slots_cannot_claim_implementation_or_biocatalyst_use() -> None:
    adapters = _registry()["read_adapters"]
    blocked = {
        "biocatalyst_company_identity_pit_adapter.v1",
        "biocatalyst_security_identity_pit_adapter.v1",
        "biocatalyst_corporate_document_span_adapter.v1",
        "biocatalyst_capital_structure_pit_adapter.v1",
    }
    for name in blocked:
        adapter = adapters[name]
        assert adapter["module"] is None
        assert adapter["callable"] is None
        assert adapter["biocatalyst_eligible"] is False
        assert adapter["blocker"]
        assert adapter["available_dependency"]
        assert adapter["compatibility_fixture"] == _FIXTURE_PATH


def test_adapter_fixture_schema_rejects_blocked_slot_promotion() -> None:
    fixture = json.loads(ADAPTER_FIXTURE.read_text(encoding="utf-8"))
    promoted = deepcopy(fixture)
    promoted["adapters"]["biocatalyst_company_identity_pit_adapter.v1"]["module"] = (
        "app.company_intelligence"
    )

    with pytest.raises(ContractValidationError):
        validate_contract(promoted, repo_root=ROOT)


def test_neural_web_and_prophet_cannot_mutate_domain_truth() -> None:
    registrations = _registry()["registrations"]

    federation = registrations["cross_sector_read_federation"]
    assert federation["canonical_owner"] == "neural_web"
    assert {
        "domain_truth_writes",
        "source_record_mutation",
        "prediction_origination",
    } <= set(federation["prohibited_uses"])

    prophet = registrations["final_technical_selection"]
    assert prophet["canonical_owner"] == "prophet"
    assert {"candidate_origination", "candidate_reordering", "gating", "sizing"} <= set(
        prophet["prohibited_biocatalyst_fallbacks"]
    )


def test_full_b0_remains_explicitly_open() -> None:
    closure = _registry()["b0_closure"]

    assert closure["state"] == "open"
    assert closure["b0a_may_ship"] is True
    assert {
        "generic_company_identity_executable_contract",
        "complete_market_data_security_master_registration",
        "corporate_documents_and_spans_executable_contract",
        "capital_structure_biocatalyst_pit_read_adapter",
    } == set(closure["blockers"])
    assert "source_canonical_nct_identity" in closure["unblocked_scope"]
    assert "prospective_trial_observations" not in closure["unblocked_scope"]
    assert "exact_registry_record_diffs" not in closure["unblocked_scope"]
    assert closure["conditional_schema_scope"] == {
        "prospective_trial_observations": {
            "canonical_registration": "trial_snapshot_and_exact_diff",
            "schema": "trial_snapshot_observation.v1",
            "availability": "dark_until_runtime_retention_gate",
            "required_environment": {
                "BIOCATALYST_PROSPECTIVE_ENABLED": "1",
                "BIOCATALYST_R2_ACTIVATION_ID": "r2_activation_<24-hex>",
                "BIOCATALYST_R2_ACCOUNT_ID": "<32-hex-cloudflare-account>",
            },
            "required_root_artifacts": [
                "/var/lib/macro-biocatalyst/activation/gate.json",
                "/var/lib/macro-biocatalyst/activation/heartbeat.json",
            ],
        },
        "exact_registry_record_diffs": {
            "canonical_registration": "trial_snapshot_and_exact_diff",
            "schema": "trial_version_diff.v1",
            "availability": "dark_until_runtime_retention_gate",
            "required_environment": {
                "BIOCATALYST_PROSPECTIVE_ENABLED": "1",
                "BIOCATALYST_R2_ACTIVATION_ID": "r2_activation_<24-hex>",
                "BIOCATALYST_R2_ACCOUNT_ID": "<32-hex-cloudflare-account>",
            },
            "required_root_artifacts": [
                "/var/lib/macro-biocatalyst/activation/gate.json",
                "/var/lib/macro-biocatalyst/activation/heartbeat.json",
            ],
        },
    }
