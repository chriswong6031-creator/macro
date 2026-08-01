from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"
OUTCOME_POLICY = ROOT / "config" / "biocatalyst_outcomes.yml"


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_source_registry_defaults_fail_closed() -> None:
    registry = _load_yaml(SOURCE_REGISTRY)

    assert registry["schema"] == "biocatalyst_source_registry.v1"
    defaults = registry["defaults"]
    assert defaults["unknown_rights_behavior"] == "block_ingest_and_export"
    assert defaults["missing_license_class_behavior"] == "hard_fail"
    assert defaults["source_fact_requires_evidence"] is True
    assert defaults["credentials_in_receipts"] is False
    assert defaults["complete_run_required_to_advance_watermark"] is True


def test_only_clinicaltrials_is_enabled_for_bounded_beta() -> None:
    registry = _load_yaml(SOURCE_REGISTRY)
    enabled = {
        source_id
        for source_id, source in registry["sources"].items()
        if source["production_ingest_allowed"]
    }

    assert enabled == {"clinicaltrials_gov_v2"}
    clinical = registry["sources"]["clinicaltrials_gov_v2"]
    assert clinical["owner"] == "biocatalyst"
    assert clinical["license_class"] == "us_government_source_facts"
    assert clinical["default_coverage_class"] == "current_only"
    assert clinical["source_version_semantics"] == (
        "current_state_api_no_complete_history_claim"
    )
    assert clinical["upstream_dataset_timestamp_endpoint"] == "/version"
    assert clinical["upstream_dataset_timestamp_field"] == "dataTimestamp"
    assert clinical["freshness_scope"] == (
        "collection_pipeline_after_observed_source_refresh"
    )
    assert clinical["freshness_slo_seconds"] == 7200


def test_clinicaltrials_distribution_obligations_are_explicit() -> None:
    clinical = _load_yaml(SOURCE_REGISTRY)["sources"]["clinicaltrials_gov_v2"]
    obligations = set(clinical["distribution_obligations"])

    assert clinical["terms_url"].startswith("https://clinicaltrials.gov/")
    assert {
        "attribute_clinicaltrials_gov",
        "display_source_processing_date",
        "keep_projected_data_current",
        "disclose_content_modifications",
        "do_not_assert_proprietary_rights_over_source_database",
        "do_not_use_extracted_email_addresses_for_marketing",
        "display_source_submitter_responsibility_note",
        "do_not_present_registry_as_government_validation",
    } <= obligations


def test_canary_is_disabled_and_empty_by_default() -> None:
    canary = _load_yaml(SOURCE_REGISTRY)["b0a_canary"]

    assert canary["universe_mode"] == "explicit_nct_allowlist"
    assert canary["default_allowlist"] == []
    assert canary["default_enabled"] is False
    assert canary["production_enable_env"] == "BIOCATALYST_ENABLED"
    assert canary["allowlist_config_env"] == "BIOCATALYST_CANARY_NCTS"


def test_benchmark_products_cannot_become_data_or_code_dependencies() -> None:
    sources = _load_yaml(SOURCE_REGISTRY)["sources"]
    for source_id in ("biopharmcatalyst_benchmark", "biopharmiq_benchmark"):
        source = sources[source_id]
        assert source["license_class"] == "benchmark_only"
        assert source["production_ingest_allowed"] is False
        assert source["raw_archive"] == "blocked"
        assert source["public_projection"] == "blocked"

    assert "asset_or_code_copy" in sources["biopharmcatalyst_benchmark"][
        "prohibited_uses"
    ]


def test_non_biocatalyst_sources_remain_disabled_or_adapter_owned() -> None:
    sources = _load_yaml(SOURCE_REGISTRY)["sources"]

    assert sources["sec_company_facts_and_filings"]["owner"] == (
        "corporate_intelligence"
    )
    assert sources["sec_company_facts_and_filings"]["production_ingest_allowed"] is False
    for source_id in ("aact", "openfda", "drugs_at_fda"):
        assert sources[source_id]["production_ingest_allowed"] is False


def test_outcome_policy_preserves_orthogonal_states_and_blocks_b0a_inference() -> None:
    policy = _load_yaml(OUTCOME_POLICY)

    assert policy["schema"] == "biocatalyst_outcome_policy.v1"
    assert policy["policy"]["flatten_to_binary_success_failure"] is False
    assert policy["policy"]["missing_is_not_negative"] is True
    assert policy["policy"]["source_record_change_is_not_protocol_change"] is True
    assert set(policy["layers"]) == {
        "study_conduct",
        "endpoint_result",
        "regulatory_disposition",
        "asset_program_state",
    }
    assert policy["b0a_scope"]["may_emit"] == ["registry_record_changed"]
    resolution = policy["resolution"]
    assert resolution["executable_contract"]["contract_id"] == "outcome_label.v1"
    assert resolution["executable_contract"]["field_mapping"] == {
        "outcome_id": "label_id",
        "layer": "outcome_type",
        "subject_id": "target_ref",
        "value": "outcome",
        "evidence_ids": "evidence_claim_refs",
        "policy_version": "resolution_policy.policy_version",
        "revision_of": "prior_label_ref",
    }
    assert {
        "protocol_changed",
        "endpoint_met",
        "endpoint_missed",
        "approval_probability",
    } <= set(policy["b0a_scope"]["may_not_emit"])
