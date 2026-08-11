from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from engine.sector_intelligence.contracts import (
    ContractValidationError,
    canonical_json_sha256,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_REGISTRY = ROOT / "config" / "sector_intelligence_ownership.yml"
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"
LAUNCH_SLO_MANIFEST = ROOT / "config" / "biocatalyst_launch_slo_manifest.yml"
CLOSED_BETA_MANIFEST = ROOT / "config" / "biocatalyst_closed_beta_source_manifest.yml"
ADAPTER_FIXTURE = (
    ROOT / "data" / "biocatalyst" / "fixtures" / "shared_plane_read_adapters.v1.json"
)
RECONCILIATION_RECEIPT = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "biocatalyst_f0_delta_reconciliation_receipt.v2.json"
)

_BLOCKED_ADAPTERS = {
    "biocatalyst_company_identity_pit_adapter.v1": (
        "reviewed_point_in_time_company_identity_contract"
    ),
    "biocatalyst_security_identity_pit_adapter.v1": (
        "complete_point_in_time_security_and_corporate_actions_contract"
    ),
    "biocatalyst_corporate_document_span_adapter.v1": (
        "versioned_document_and_exact_span_read_contract"
    ),
}
_ELIGIBLE_ADAPTERS = {
    "biocatalyst_trial_read_api.v1",
    "biocatalyst_earnings_transcript_span_adapter.v1",
    "biocatalyst_capital_structure_pit_adapter.v1",
}
_EXPECTED_FAMILIES = {
    "clinicaltrials_current_record",
    "clinicaltrials_discovery_scope",
    "clinicaltrials_record_history",
    "regulator_application_and_submission",
    "label_and_safety",
    "company_and_asset_identity_pit",
    "security_context_boundary",
    "corporate_document_and_span",
    "earnings_transcript_context",
    "capital_structure_pit",
    "market_and_options_context",
}


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plane_by_adapter(receipt: dict) -> dict[str, dict]:
    return {
        plane["adapter_id"]: plane
        for plane in receipt["planes"]
        if plane["adapter_id"] is not None
    }


def _family_by_id(manifest: dict) -> dict[str, dict]:
    return {family["family_id"]: family for family in manifest["families"]}


def test_reconciliation_receipt_binds_the_exact_bytes_and_commit_it_audited() -> None:
    receipt = _load_json(RECONCILIATION_RECEIPT)
    registry = _load_yaml(OWNERSHIP_REGISTRY)
    fixture = _load_json(ADAPTER_FIXTURE)

    validate_contract(receipt, repo_root=ROOT)
    assert receipt["contract_id"] == "biocatalyst_f0_delta_reconciliation_receipt.v1"
    assert receipt["schema_version"] == "1.0.0"
    assert receipt["owner"] == "biocatalyst"

    # The receipt must hash the files it claims to have audited, so a later
    # session can tell whether the registry drifted after this reconciliation.
    assert receipt["ownership_registry_sha256"] == _file_sha256(OWNERSHIP_REGISTRY)
    assert receipt["adapter_fixture_sha256"] == _file_sha256(ADAPTER_FIXTURE)

    # ownership.yml and the fixture move in lockstep; the receipt records both
    # that shared baseline and the newer commit this audit actually ran against.
    assert (
        receipt["ownership_registry_reconciled_against_commit"]
        == registry["reconciled_against_commit"]
    )
    assert receipt["adapter_fixture_baseline_commit"] == fixture["baseline_commit"]
    assert fixture["baseline_commit"] == registry["reconciled_against_commit"]

    identity = canonical_json_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key not in {"receipt_id", "content_sha256"}
        }
    )
    assert receipt["content_sha256"] == identity
    assert receipt["receipt_id"] == f"biocatalyst_f0_delta_{identity[:24]}"


def test_reconciliation_records_exactly_one_adapter_eligibility_change() -> None:
    receipt = _load_json(RECONCILIATION_RECEIPT)
    fixture_adapters = _load_json(ADAPTER_FIXTURE)["adapters"]
    planes = _plane_by_adapter(receipt)

    assert receipt["state"] == "reconciled_with_eligibility_change"
    changed = [plane for plane in receipt["planes"] if plane["eligibility_changed"]]
    assert [plane["adapter_id"] for plane in changed] == [
        "biocatalyst_capital_structure_pit_adapter.v1"
    ]

    for adapter_id, blocker in _BLOCKED_ADAPTERS.items():
        plane = planes[adapter_id]
        assert plane["verdict"] == "still_blocked"
        assert plane["prior_biocatalyst_eligible"] is False
        assert plane["reconciled_biocatalyst_eligible"] is False
        assert plane["blocker"] == blocker
        # The receipt may never soften the registry it audited.
        assert fixture_adapters[adapter_id]["blocker"] == blocker
        assert fixture_adapters[adapter_id]["biocatalyst_eligible"] is False
        for relative in plane["inspected_paths"]:
            assert (ROOT / relative).exists(), relative

    for adapter_id in _ELIGIBLE_ADAPTERS:
        plane = planes[adapter_id]
        assert plane["verdict"] == "eligible"
        assert plane["blocker"] is None
        assert fixture_adapters[adapter_id]["biocatalyst_eligible"] is True

    assert set(planes) == set(_BLOCKED_ADAPTERS) | _ELIGIBLE_ADAPTERS

    capital = planes["biocatalyst_capital_structure_pit_adapter.v1"]
    assert capital["verdict"] == "eligible"
    assert capital["prior_biocatalyst_eligible"] is False
    assert capital["reconciled_biocatalyst_eligible"] is True
    assert capital["eligibility_changed"] is True
    assert capital["blocker"] is None
    capital_evidence = " ".join(capital["evidence"])
    assert "one issuer" in capital_evidence
    assert "cash" in capital_evidence
    assert "authority" in capital_evidence


def test_receipt_records_the_planes_that_own_no_biocatalyst_read_adapter() -> None:
    receipt = _load_json(RECONCILIATION_RECEIPT)
    slotless = {
        plane["plane"]: plane
        for plane in receipt["planes"]
        if plane["verdict"] == "no_read_adapter_slot"
    }

    assert set(slotless) == {"terminal_supabase", "neural_web", "prophet"}
    for plane in slotless.values():
        assert plane["adapter_id"] is None
        assert plane["reconciled_biocatalyst_eligible"] is None
        assert plane["blocker"] is None
        assert plane["eligibility_changed"] is False

    assert all(value is False for value in receipt["authority"].values())
    rule = receipt["eligibility_rule"]
    assert rule["plane_existence_is_sufficient"] is False
    assert rule["importable_module_is_sufficient"] is False
    assert rule["requires_point_in_time_scope"] is True


def test_receipt_schema_rejects_an_eligible_verdict_that_keeps_its_blocker() -> None:
    promoted = deepcopy(_load_json(RECONCILIATION_RECEIPT))
    for plane in promoted["planes"]:
        if plane["adapter_id"] == "biocatalyst_capital_structure_pit_adapter.v1":
            plane["blocker"] = "forbidden_widening"

    with pytest.raises(ContractValidationError):
        validate_contract(promoted, repo_root=ROOT)


def test_receipt_schema_rejects_a_no_change_state_that_changed_an_eligibility() -> None:
    changed = deepcopy(_load_json(RECONCILIATION_RECEIPT))
    changed["state"] = "reconciled_no_eligibility_change"

    with pytest.raises(ContractValidationError):
        validate_contract(changed, repo_root=ROOT)


def test_closed_beta_manifest_is_a_denominator_and_not_an_activation() -> None:
    manifest = _load_yaml(CLOSED_BETA_MANIFEST)

    validate_contract(manifest, repo_root=ROOT)
    assert manifest["contract_id"] == "biocatalyst_closed_beta_source_manifest.v1"
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["state"] == "draft_denominator_unarmed"
    assert manifest["owner"] == "biocatalyst"
    assert all(value is False for value in manifest["authority"].values())
    assert manifest["authority"]["constitutes_soak_evidence"] is False
    assert manifest["authority"]["constitutes_rights_review"] is False
    assert manifest["authority"]["authorizes_operator_arming"] is False
    assert manifest["authority"]["originates_signals_scores_or_ranking"] is False

    identity = canonical_json_sha256(
        {
            key: value
            for key, value in manifest.items()
            if key not in {"manifest_id", "content_sha256"}
        }
    )
    assert manifest["content_sha256"] == identity
    assert manifest["manifest_id"] == f"biocatalyst_closed_beta_{identity[:24]}"

    # A denominator names sources; it never publishes a route or an endpoint.
    text = CLOSED_BETA_MANIFEST.read_text(encoding="utf-8")
    assert "/api/" not in text
    assert "http://" not in text
    assert "https://" not in text


def test_closed_beta_manifest_names_every_family_by_exact_registry_id() -> None:
    manifest = _load_yaml(CLOSED_BETA_MANIFEST)
    sources = _load_yaml(SOURCE_REGISTRY)["sources"]
    adapters = _load_yaml(OWNERSHIP_REGISTRY)["read_adapters"]
    receipt = _load_json(RECONCILIATION_RECEIPT)

    assert set(_family_by_id(manifest)) == _EXPECTED_FAMILIES
    assert manifest["reconciliation_receipt_id"] == receipt["receipt_id"]
    assert manifest["reconciliation_receipt_sha256"] == _file_sha256(
        RECONCILIATION_RECEIPT
    )
    assert manifest["source_registry_sha256"] == _file_sha256(SOURCE_REGISTRY)
    assert manifest["ownership_registry_sha256"] == _file_sha256(OWNERSHIP_REGISTRY)

    for family in manifest["families"]:
        for binding in family["bindings"]:
            if binding["binding_kind"] == "source_registry_source":
                source = sources[binding["id"]]
                assert binding["launch_critical"] == source["launch_critical"]
                assert (
                    binding["production_ingest_allowed"]
                    == source["production_ingest_allowed"]
                )
                assert binding["license_class"] == source["license_class"]
                assert binding["rights_state"] == source["rights_state"]
            else:
                adapter = adapters[binding["id"]]
                assert binding["rights_state"] == adapter["implementation_state"]
                assert binding["launch_critical"] is None
                assert binding["production_ingest_allowed"] is None

    clinical = sources["clinicaltrials_gov_v2"]
    current = _family_by_id(manifest)["clinicaltrials_current_record"]
    version = current["bindings"][0]["version"]
    assert clinical["api_schema_version"] in version
    assert clinical["parser_version"] in version


def test_launch_denominator_cannot_be_claimed_from_the_single_critical_source() -> None:
    manifest = _load_yaml(CLOSED_BETA_MANIFEST)
    sources = _load_yaml(SOURCE_REGISTRY)["sources"]
    denominator = manifest["launch_denominator"]

    launch_critical = {
        source_id
        for source_id, source in sources.items()
        if source["launch_critical"] is True
    }
    assert launch_critical == {"clinicaltrials_gov_v2"}

    mandatory = [
        family for family in manifest["families"] if family["obligation"] == "mandatory"
    ]
    available = [
        family for family in mandatory if family["availability"] == "available"
    ]
    assert denominator["mandatory_family_ids"] == [
        family["family_id"] for family in mandatory
    ]
    assert denominator["mandatory_families_total"] == len(mandatory)
    assert denominator["mandatory_families_available"] == len(available)
    assert len(mandatory) > len(launch_critical)

    assert denominator["all_mandatory_families_available"] is False
    assert denominator["readiness_claim"] == "closed_beta_source_denominator_not_met"
    assert denominator["single_launch_critical_source_is_sufficient"] is False
    assert denominator["omitted_family_allowed"] is False
    assert denominator["unknown_family_allowed"] is False
    assert denominator["weighted_substitution_allowed"] is False


def test_every_unavailable_family_states_a_blocker_and_unlocks_nothing() -> None:
    manifest = _load_yaml(CLOSED_BETA_MANIFEST)
    families = _family_by_id(manifest)

    unavailable = {
        family_id
        for family_id, family in families.items()
        if family["availability"] == "unavailable"
    }
    assert unavailable == _EXPECTED_FAMILIES - {
        "clinicaltrials_current_record",
        "clinicaltrials_record_history",
        "earnings_transcript_context",
        "capital_structure_pit",
    }

    for family_id in unavailable:
        family = families[family_id]
        assert family["blocker"]
        assert family["features_unlocked"] == []
        assert family["features_unavailable"]
        assert family["slo"]["freshness_denominator"]
        assert family["slo"]["completeness_denominator"]
        assert family["slo"]["error_denominator"]
        assert family["slo"]["correction_denominator"]
        assert family["rights"]["retention"]

    # Blocked shared planes must reuse the ownership registry's exact blocker.
    for family_id, adapter_id in {
        "company_and_asset_identity_pit": (
            "biocatalyst_company_identity_pit_adapter.v1"
        ),
        "security_context_boundary": (
            "biocatalyst_security_identity_pit_adapter.v1"
        ),
        "corporate_document_and_span": (
            "biocatalyst_corporate_document_span_adapter.v1"
        ),
    }.items():
        assert families[family_id]["blocker"] == _BLOCKED_ADAPTERS[adapter_id]


def test_closed_beta_manifest_binds_a_successor_of_the_fourteen_day_launch_slo() -> None:
    manifest = _load_yaml(CLOSED_BETA_MANIFEST)
    slo = _load_yaml(LAUNCH_SLO_MANIFEST)
    binding = manifest["successor_binding"]

    assert manifest["launch_slo_manifest_id"] == slo["manifest_id"]
    assert manifest["launch_slo_manifest_content_sha256"] == slo["content_sha256"]
    assert binding["binds_launch_slo_contract"] == slo["contract_id"]
    assert (
        binding["required_soak_duration_seconds"]
        == slo["soak"]["required_duration_seconds"]
    )
    assert binding["required_soak_duration_seconds"] == 1209600
    assert binding["successor_manifest_required_before_soak_scheduling"] is True

    # The source soak has cleared its own blockers. Closed-beta launch remains
    # separately blocked until its full mandatory source denominator is met.
    assert set(slo["soak"]["scheduling_blockers"]) <= set(
        binding["soak_scheduling_blockers"]
    )
    assert binding["soak_scheduling_blockers"] == [
        "closed_beta_source_denominator_not_met"
    ]
    assert "closed_beta_source_denominator_not_met" in binding[
        "soak_scheduling_blockers"
    ]

    # Every source the 14-day SLO measures must be named by this manifest.
    manifest_source_ids = {
        source_binding["id"]
        for family in manifest["families"]
        for source_binding in family["bindings"]
        if source_binding["binding_kind"] == "source_registry_source"
    }
    assert {row["source_id"] for row in slo["sources"]} <= manifest_source_ids


def test_manifest_schema_rejects_a_readiness_claim_without_every_mandatory_family() -> None:
    claimed = deepcopy(_load_yaml(CLOSED_BETA_MANIFEST))
    claimed["launch_denominator"]["readiness_claim"] = (
        "closed_beta_source_denominator_met"
    )

    with pytest.raises(ContractValidationError):
        validate_contract(claimed, repo_root=ROOT)


def test_manifest_schema_rejects_an_available_family_with_a_blocker() -> None:
    promoted = deepcopy(_load_yaml(CLOSED_BETA_MANIFEST))
    for family in promoted["families"]:
        if family["family_id"] == "capital_structure_pit":
            family["blocker"] = "forbidden_widening"

    with pytest.raises(ContractValidationError):
        validate_contract(promoted, repo_root=ROOT)


def test_fixture_promotes_only_the_implemented_capital_adapter() -> None:
    fixture = _load_json(ADAPTER_FIXTURE)
    registry = _load_yaml(OWNERSHIP_REGISTRY)

    validate_contract(fixture, repo_root=ROOT)
    eligible = {
        name
        for name, adapter in registry["read_adapters"].items()
        if adapter["biocatalyst_eligible"]
    }
    assert eligible == _ELIGIBLE_ADAPTERS
    assert set(_BLOCKED_ADAPTERS) <= set(fixture["adapters"])
    for adapter_id in _BLOCKED_ADAPTERS:
        adapter = fixture["adapters"][adapter_id]
        assert adapter["module"] is None
        assert adapter["callable"] is None
        assert adapter["routes"] == []
        assert adapter["output_contracts"] == []

    capital = fixture["adapters"][
        "biocatalyst_capital_structure_pit_adapter.v1"
    ]
    assert capital["module"] == "engine.capital_structure.biocatalyst_pit_adapter"
    assert capital["callable"] == "read_biocatalyst_capital_structure_pit"
    assert capital["routes"] == []
    assert capital["output_contracts"] == [
        "biocatalyst_capital_structure_pit_read.v1"
    ]
    assert capital["blocker"] is None
