from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"
OUTCOME_POLICY = ROOT / "config" / "biocatalyst_outcomes.yml"
LAUNCH_SLO_MANIFEST = ROOT / "config" / "biocatalyst_launch_slo_manifest.yml"
_FIXED_COHORT_CONTRACT_ID = "ctgov_fixed_cohort.v1"
_FIXED_COHORT_CONTROL_RAW = b"""b1s1_fixed_cohort_control:
  source_id: clinicaltrials_gov_v2
  implementation_state: validation_only_fixed_cohort_control
  universe_mode: fixed_explicit_nct_cohort
  membership_authority: fixed_cohort_only
  candidate_admission_policy: candidate_subset_only
  minimum_nct_ids: 1
  maximum_nct_ids: 25
  maximum_query_bytes: 299
  default_enabled: false
  live_network_allowed: false
  worker_mode_available: false
  public_projection_allowed: false
  api_exposure_allowed: false
  storage_publication_allowed: false
  consumers: []
  authority: facts_and_context_only
  allowed_contracts:
    - ctgov_fixed_cohort.v1
  prohibited_claims:
    - dynamic_cohort_expansion
    - live_ingestion
    - identity_mapping
    - scoring
    - prediction
    - prophet_authority
    - neural_web_authority
    - ranking
    - sizing
    - alerts
  prohibited_uses:
    - dynamic_cohort_expansion
    - live_ingestion
    - identity_mapping
    - scoring
    - prediction
    - prophet_authority
    - neural_web_authority
    - ranking
    - sizing
    - alerts
"""


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

    # Rights permission and runtime arming remain separate controls. Record
    # History was rights-cleared by the named 2026-08-07 ruling; the later
    # forward-clock wave arms only its exact four-NCT canary universe.
    assert enabled == {"clinicaltrials_gov_v2", "clinicaltrials_gov_record_history"}
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
    assert clinical["request_headers_allowlist"] == [
        "accept",
        "accept-encoding",
        "user-agent",
    ]
    assert "content-encoding" in clinical["receipt_response_headers_allowlist"]


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


def test_scalable_discovery_control_is_dark_bounded_and_non_authoritative() -> None:
    control = _load_yaml(SOURCE_REGISTRY)["b1s0_discovery_control"]

    assert control["source_id"] == "clinicaltrials_gov_v2"
    assert control["implementation_state"] == (
        "dark_contract_and_hermetic_harness_only"
    )
    assert control["universe_mode"] == "declared_last_update_post_date_window"
    assert control["source_selection_field"] == "LastUpdatePostDate"
    assert control["source_query_form"] == (
        "AREA[LastUpdatePostDate]RANGE[YYYY-MM-DD,YYYY-MM-DD]"
    )
    assert control["source_dataset_clock"] == "/version.dataTimestamp"
    assert control["knowledge_clock"] == "response_received_at"
    assert control["source_selection_precision"] == "day"
    assert control["default_enabled"] is False
    assert control["live_network_allowed"] is False
    assert control["worker_mode_available"] is False
    assert control["public_projection_allowed"] is False
    assert control["api_exposure_allowed"] is False
    assert control["storage_publication_allowed"] is False
    assert set(control["allowed_contracts"]) == {
        "ctgov_discovery_scope.v1",
        "ctgov_discovery_run.v1",
        "ctgov_discovery_coverage_epoch.v1",
    }
    assert control["allowed_scope_language"] == (
        "Records returned for this declared ClinicalTrials.gov source query."
    )
    assert {
        "complete_clinicaltrials_gov_universe",
        "missing_record_means_deleted",
        "last_update_post_date_is_event_time",
        "last_update_post_date_is_knowledge_time",
        "discovery_membership_is_issuer_or_security_identity",
        "partial_or_quarantined_run_is_publishable",
    } <= set(control["prohibited_claims"])


def test_fixed_cohort_control_is_byte_pinned_dark_and_facts_context_only() -> None:
    registry_bytes = SOURCE_REGISTRY.read_bytes()
    start = registry_bytes.index(b"b1s1_fixed_cohort_control:\n")
    end = registry_bytes.index(b"\nb2_history_canary:\n", start)
    assert registry_bytes[start:end] == _FIXED_COHORT_CONTROL_RAW

    control = _load_yaml(SOURCE_REGISTRY)["b1s1_fixed_cohort_control"]
    assert control == {
        "source_id": "clinicaltrials_gov_v2",
        "implementation_state": "validation_only_fixed_cohort_control",
        "universe_mode": "fixed_explicit_nct_cohort",
        "membership_authority": "fixed_cohort_only",
        "candidate_admission_policy": "candidate_subset_only",
        "minimum_nct_ids": 1,
        "maximum_nct_ids": 25,
        "maximum_query_bytes": 299,
        "default_enabled": False,
        "live_network_allowed": False,
        "worker_mode_available": False,
        "public_projection_allowed": False,
        "api_exposure_allowed": False,
        "storage_publication_allowed": False,
        "consumers": [],
        "authority": "facts_and_context_only",
        "allowed_contracts": [_FIXED_COHORT_CONTRACT_ID],
        "prohibited_claims": [
            "dynamic_cohort_expansion",
            "live_ingestion",
            "identity_mapping",
            "scoring",
            "prediction",
            "prophet_authority",
            "neural_web_authority",
            "ranking",
            "sizing",
            "alerts",
        ],
        "prohibited_uses": [
            "dynamic_cohort_expansion",
            "live_ingestion",
            "identity_mapping",
            "scoring",
            "prediction",
            "prophet_authority",
            "neural_web_authority",
            "ranking",
            "sizing",
            "alerts",
        ],
    }


def test_fixed_cohort_contract_has_no_operational_wiring() -> None:
    # A contract declaration is allowed to reach only the generic semantic
    # registry.  These are the real route, collector, worker, store,
    # publication, consumer, and activation seams that must remain unaware of
    # B1S1 until a separately reviewed implementation exists.
    forbidden_paths = (
        ROOT / "app" / "biocatalyst.py",
        ROOT / "collectors" / "biocatalyst" / "clinicaltrials_v2.py",
        ROOT / "engine" / "biocatalyst" / "storage.py",
        ROOT / "engine" / "biocatalyst" / "publication.py",
        ROOT / "scripts" / "biocatalyst_worker.py",
        ROOT / "scripts" / "biocatalyst_activation.py",
        ROOT / "config" / "sector_intelligence_ownership.yml",
    )

    assert all(path.is_file() for path in forbidden_paths)
    for path in forbidden_paths:
        assert _FIXED_COHORT_CONTRACT_ID not in path.read_text(encoding="utf-8")


def test_launch_slo_manifest_schedules_the_exact_critical_set_without_widening_authority() -> None:
    registry = _load_yaml(SOURCE_REGISTRY)
    manifest = _load_yaml(LAUNCH_SLO_MANIFEST)
    critical = {
        source_id
        for source_id, source in registry["sources"].items()
        if source["launch_critical"] is True
    }

    assert critical == {"clinicaltrials_gov_v2"}
    assert {row["source_id"] for row in manifest["sources"]} == critical
    assert manifest["state"] == "soak_scheduled"
    assert manifest["sources"][0]["activation_state"] == "armed"
    assert registry["b0a_canary"]["default_enabled"] is False
    assert manifest["soak"]["window_start"] == "2026-08-12T02:00:00Z"
    assert manifest["soak"]["window_end"] == "2026-08-26T02:00:00Z"
    assert manifest["soak"]["scheduling_blockers"] == []
    assert manifest["soak"]["source_results"] == []
    assert manifest["soak"]["aggregate_passed"] is False
    assert all(value is False for value in manifest["authority"].values())


def test_record_history_canary_is_separate_bounded_and_exactly_armed() -> None:
    registry = _load_yaml(SOURCE_REGISTRY)
    source = registry["sources"]["clinicaltrials_gov_record_history"]
    canary = registry["b2_history_canary"]

    # The rights gate came from the named 2026-08-07 operator ruling. The
    # separately reviewed forward-clock wave arms only the exact B1 universe;
    # tests/test_biocatalyst_record_history_enablement.py is the dedicated guard.
    assert source["production_ingest_allowed"] is True
    assert source["raw_archive"] == "private_only"
    assert source["interface_stability"] == "undocumented_ui_backing_route"
    assert source["source_shape_canary_required"] is True
    assert source["etag_semantics"] == (
        "retained_as_transport_metadata_never_content_identity_or_freshness"
    )
    assert source["source_version_semantics"] == (
        "source_record_history_versions_not_event_time"
    )
    assert {
        "attribute_clinicaltrials_gov",
        "do_not_use_extracted_email_addresses_for_marketing",
        "display_source_submitter_responsibility_note",
        "do_not_present_registry_as_government_validation",
    } <= set(source["distribution_obligations"])
    assert source["public_projection"] == "source_facts_with_attribution"
    assert canary["default_enabled"] is True
    assert canary["default_allowlist"] == [
        "NCT04528082",
        "NCT05020236",
        "NCT06602479",
        "NCT07218380",
    ]
    assert canary["production_enable_env"] == "BIOCATALYST_HISTORY_ENABLED"
    assert canary["allowlist_config_env"] == "BIOCATALYST_CANARY_NCTS"
    assert canary["universe_relation"] == "exact_b1_current_nct_set"
    assert set(canary["allowed_contracts"]) == {
        "ctgov_history_receipt.v1",
        "ctgov_history_run.v1",
        "trial_history_source_snapshot.v1",
        "trial_history_exact_diff.v1",
        "trial_registry_change_fact.v1",
        "trial_history_read_model.v1",
    }
    assert "no protocol or materiality inference" in canary[
        "allowed_product_language"
    ]

    # B2 registration must not steal B1's watermark or product-language policy.
    assert "ctgov_watermark.v1" in registry["b0a_canary"]["allowed_contracts"]
    assert "first observed within this interval" in registry["b0a_canary"][
        "allowed_product_language"
    ]


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


def test_biopharmcatalyst_jv_snapshot_is_distinct_from_the_benchmark() -> None:
    registry = _load_yaml(SOURCE_REGISTRY)
    sources = registry["sources"]
    benchmark = sources["biopharmcatalyst_benchmark"]
    snapshot = sources["biopharmcatalyst_jv_snapshot"]

    assert "finite_jv_snapshot_seed" in registry["license_classes"]
    assert snapshot["source_id"] == "biopharmcatalyst_jv_snapshot"
    assert snapshot["source_id"] != benchmark["source_id"]
    assert snapshot["license_class"] == "finite_jv_snapshot_seed"
    assert snapshot["license_class"] != benchmark["license_class"]
    assert snapshot["production_ingest_allowed"] is False
    assert snapshot["raw_archive"] == "operator_held_never_git"
    assert snapshot["public_projection"] == "blocked"
    assert snapshot["producer"] is None

    assert set(benchmark["permitted_uses"]) == {
        "behavioral_parity_review",
        "public_feature_inventory",
        "clean_room_acceptance_benchmark",
    }
    assert "proprietary_historical_row_import" in benchmark["prohibited_uses"]
    assert set(snapshot["permitted_uses"]) == {
        "schema_and_clock_census",
        "reconstruction_matching",
        "coverage_scoring",
    }
    assert {
        "production_data_feed",
        "continuous_bpc_api",
        "proprietary_historical_row_import",
        "proprietary_row_commit",
        "export_time_as_pre_event_feature",
    } <= set(snapshot["prohibited_uses"])
    assert snapshot["seed_inventory"]["workbook_sha256"] == (
        "946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535"
    )


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
