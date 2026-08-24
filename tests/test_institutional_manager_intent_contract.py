from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest

import lib.institutional_intelligence as manager_intent
from lib.evidence_foundation import (
    CORRECTION_KINDS,
    COVERAGE_CLASSES,
    REPLAY_MODES,
    SCHEMA_PATH as K1_REFERENCE_SCHEMA_PATH,
    VINTAGE_STATES,
    compute_reference_id,
    load_vocabulary,
    validate_reference,
)
from lib.institutional_intelligence import (
    InstitutionalIntelligenceError,
    compile_recipe,
    compute_recipe_id,
    validate,
    violations,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "institutional_intelligence"
    / "source_backed_manager_intent_recipe.json"
)
RAW_REF_ID = "efr_9b1450aec5bd550aff068fbd28246c44505702d75577cef76e2349d0706a8915"
THEME_REF_ID = "efr_c5a0444802fa2ed354a7324be6dc5bb17b81cd205d44ee49465be43db5e36011"
AS_OF = "2026-08-08T01:00:00Z"


def recipe() -> dict:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert value["recipe_id"] == compute_recipe_id(value)
    return value


def stamp(value: dict) -> dict:
    value["recipe_id"] = compute_recipe_id(value)
    return value


def rejected(value: dict, expected: str) -> None:
    stamp(value)
    with pytest.raises(InstitutionalIntelligenceError, match=expected):
        validate(value)


def event(value: dict, observation_id: str) -> dict:
    return next(row for row in value["observations"] if row["observation_id"] == observation_id)


def replace_reference(value: dict, old_id: str, mutate) -> str:
    reference = next(row for row in value["evidence_refs"] if row["reference_id"] == old_id)
    mutate(reference)
    reference["reference_id"] = compute_reference_id(reference)
    new_id = reference["reference_id"]
    validate_reference(reference)
    for row in value["observations"]:
        if row["evidence_reference_id"] == old_id:
            row["evidence_reference_id"] = new_id
            row["reference_binding"]["reference_id"] = new_id
    for row in value["theme_comparisons"]:
        if row["membership_reference_id"] == old_id:
            row["membership_reference_id"] = new_id
    return new_id


def _transition(
    transition_id: str,
    *,
    sequence: int,
    previous: str | None,
    from_state: str,
    to_state: str,
    at: str,
    campaign_id: str = "cmp_meeder_alpha_1",
) -> dict:
    return {
        "transition_id": transition_id,
        "campaign_id": campaign_id,
        "sequence": sequence,
        "previous_transition_id": previous,
        "subject_id": "SEC:US-XNAS-ALPH",
        "manager_complex_id": "mcx_meeder_adviser",
        "complex_epoch_id": "mce_meeder_2026q2",
        "from": from_state,
        "to": to_state,
        "transitioned_at": at,
        "observation_ids": ["obs_manager_positive"],
        "correction": {
            "kind": "none",
            "supersedes_transition_id": None,
            "reason": None,
            "append_only": True,
        },
    }


def test_full_k1_refs_are_valid_and_actual_raw_receipt_contract_is_exact() -> None:
    value = recipe()
    refs = {row["reference_id"]: validate_reference(row) for row in value["evidence_refs"]}
    assert set(refs) == {
        RAW_REF_ID,
        "efr_d9ddc49e1b0d02bc6980fbdc61df12a242f69f3a9b098fb34229f7dd64e58f34",
        THEME_REF_ID,
    }
    raw = refs[RAW_REF_ID]
    assert raw["owner_store"] == "institutional_13f.raw_receipt"
    assert raw["native_schema"] == "institutional_13f.raw_evidence_receipt/v1"
    assert raw["native_identity"] == {
        "accession": "0001398344-26-013841",
        "filer_cik": "0001792167",
        "receipt_id": "i13fraw_c16997a2b2d352a4b7ada643273e00ca482505cf84b1e33e3688d3b0dc6fa8d2",
    }
    assert raw["native_digest"] == {
        "state": "known",
        "sha256": "cc09d4f341c5d2fbb03ec994178f9ed38dddd4e4ee8e1bc333be9fb605917311",
    }
    assert raw["provenance"] == {
        "pointer_only": True,
        "body_embedded": False,
        "owner_reader": "engine.institutional_census.models.RawEvidenceReceipt.from_json_bytes",
        "owner_reader_kind": "parser",
        "pointer": "institutional-13f/raw/0001792167/0001398344-26-013841/i13fraw_c16997a2b2d352a4b7ada643273e00ca482505cf84b1e33e3688d3b0dc6fa8d2.json",
    }
    assert raw["rights"]["state"] == "permitted"
    assert raw["coverage_class"] == "source_release_snapshot_only"
    assert [row["field"] for row in raw["clocks"]] == [
        "clocks.report_period", "clocks.accepted_at", "clocks.retained_at"
    ]


def test_fixture_is_closed_deterministic_pointer_only_and_all_authority_false() -> None:
    value = recipe()
    assert validate(value) == value
    first = compile_recipe(value, as_of=AS_OF)
    second = compile_recipe(deepcopy(value), as_of=AS_OF)
    assert first == second
    assert first["owner_payloads_copied"] is False
    assert first["persistence"] == "none"
    assert first["master_score"] is None
    assert first["authority"] == {
        "can_rank": False,
        "can_gate": False,
        "can_size": False,
        "can_originate": False,
        "can_open_entry": False,
    }


def test_four_planes_have_closed_positive_and_adverse_receipts() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    by_id = {row["observation_id"]: row for row in receipt["events"]}
    assert {row["plane"] for row in receipt["events"]} == {
        "manager_research_intent",
        "fund_flow_pressure",
        "theme_capital_rotation",
        "institutionalization_saturation",
    }
    assert by_id["obs_manager_positive"]["state"] == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    assert by_id["obs_source_pointer_only"]["state"] == "SOURCE_POINTER_ONLY_NO_SECURITY_BINDING"
    assert by_id["obs_flow_true_s"]["state"] == "MECHANICAL_FLOW_RESIDUAL"
    assert by_id["obs_flow_proxy"]["state"] == "MECHANICAL_FLOW_PROXY"
    assert by_id["obs_saturation_positive"]["state"] == "SATURATION_OBSERVED"
    assert by_id["obs_saturation_adverse"]["state"] == "SATURATION_UNAVAILABLE"


def test_event_pointer_tamper_and_full_ref_tamper_fail_closed() -> None:
    value = recipe()
    event(value, "obs_manager_positive")["evidence_reference_id"] = "efr_" + "0" * 64
    rejected(value, "event_reference_id_conflict|event_reference_unresolved")

    value = recipe()
    raw = next(row for row in value["evidence_refs"] if row["reference_id"] == RAW_REF_ID)
    raw["native_identity"]["filer_cik"] = "0000000001"
    rejected(value, "k1_evidence_ref_invalid")

    value = recipe()
    event(value, "obs_manager_positive")["reference_binding"]["native_identity"]["filer_cik"] = "0000000001"
    rejected(value, "event_native_identity_binding_conflict")


def test_source_pointer_cannot_claim_security_binding_without_owner_selection() -> None:
    value = recipe()
    event(value, "obs_source_pointer_only")["subject_id"] = "SEC:US-XNAS-FAKE"
    rejected(value, "source_pointer_cannot_bind_security_subject")


def test_true_s_residual_is_compiler_derived_and_caller_result_is_forbidden() -> None:
    value = recipe()
    row = event(value, "obs_flow_true_s")
    row["measure"]["residual_shares"] = 999
    rejected(value, "json_schema:observations")
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    compiled = next(row for row in receipt["events"] if row["observation_id"] == "obs_flow_true_s")
    assert compiled["measure"] == {
        "kind": "etf_true_share_residual",
        "state": "computed_true_shares_outstanding",
        "formula": "Q_now - Q_prev * (S_now / S_prev)",
        "residual_shares": 30.0,
    }


def test_13f_never_borrows_etf_s_and_proxy_never_becomes_intent() -> None:
    value = recipe()
    event(value, "obs_manager_positive")["measure"] = {
        "kind": "etf_true_share_residual",
        "q_prev": 100,
        "q_now": 150,
        "s_prev": 1000,
        "s_now": 1200,
    }
    rejected(value, "plane_measure_denominator_shape_conflict")
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    proxy = next(row for row in receipt["events"] if row["observation_id"] == "obs_flow_proxy")
    assert proxy["measure"]["residual_shares"] is None
    assert proxy["state"] == "MECHANICAL_FLOW_PROXY"


def test_within_theme_preference_is_derived_from_distinct_pit_members() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    positive, adverse = receipt["theme_comparisons"]
    assert positive["state"] == "WITHIN_THEME_PREFERENCE_COMPUTED"
    assert positive["target_reported_share_delta"] == 40.0
    assert positive["eligible_peer_mean_reported_share_delta"] == 10.0
    assert positive["preference_spread"] == 30.0
    assert adverse["state"] == "INSUFFICIENT_ELIGIBLE_PEERS"
    assert adverse["preference_spread"] is None


def test_same_target_peer_or_one_name_denominator_is_rejected() -> None:
    value = recipe()
    comparison = value["theme_comparisons"][0]
    comparison["peer_observation_ids"] = [comparison["target_observation_id"]]
    comparison["denominator_receipt"]["member_observation_ids"] = [comparison["target_observation_id"]]
    comparison["denominator_receipt"]["eligible_observation_ids"] = [comparison["target_observation_id"]]
    rejected(value, "theme_target_peer_overlap|theme_denominator_membership_invalid")


def test_late_peer_and_passive_peer_as_eligible_are_rejected() -> None:
    value = recipe()
    peer = event(value, "obs_theme_peer")
    peer["reference_binding"]["available_clock"]["value"] = "2026-09-01T00:00:00Z"
    rejected(value, "event_available_clock_binding_conflict|theme_peer_not_knowable_at_cutoff")

    value = recipe()
    comparison = value["theme_comparisons"][1]
    comparison["denominator_receipt"]["eligible_observation_ids"].append("obs_theme_peer_mechanical")
    comparison["denominator_receipt"]["excluded_members"] = []
    rejected(value, "theme_ineligible_member_marked_eligible")


def test_membership_pointer_clock_tamper_is_rejected() -> None:
    value = recipe()
    value["theme_comparisons"][0]["membership_clock_binding"]["value"] = "2026-08-09T00:00:00Z"
    rejected(value, "theme_membership_clock_unbound|theme_membership_lookahead")


def test_campaign_refuses_rights_blocked_and_preknowledge_observations() -> None:
    value = recipe()

    def block(reference: dict) -> None:
        reference["rights"] = {"state": "rights_blocked", "policy_id": "test_block"}
        reference["missingness"] = {
            "state": "absent",
            "reason": "rights_blocked",
            "zero_substituted": False,
        }

    replace_reference(value, RAW_REF_ID, block)
    rejected(value, "campaign_observation_ineligible")

    value = recipe()
    value["campaign_transitions"][0]["transitioned_at"] = "2026-05-15T20:00:30Z"
    rejected(value, "campaign_observation_ineligible|campaign_observation_not_yet_knowable")


def test_campaign_history_is_emitted_and_requires_append_only_linear_chain() -> None:
    value = recipe()
    value["campaign_transitions"].extend([
        _transition("ctr_campaign_2", sequence=2, previous="ctr_campaign_1", from_state="INITIATED", to_state="ACCUMULATING", at="2026-05-17T20:01:00Z"),
        _transition("ctr_campaign_3", sequence=3, previous="ctr_campaign_2", from_state="ACCUMULATING", to_state="PAUSED", at="2026-05-18T20:01:00Z"),
        _transition("ctr_campaign_4", sequence=4, previous="ctr_campaign_3", from_state="PAUSED", to_state="CLOSED", at="2026-05-19T20:01:00Z"),
        _transition("ctr_campaign_5", sequence=1, previous=None, from_state="IDLE", to_state="INITIATED", at="2026-05-20T20:01:00Z", campaign_id="cmp_meeder_alpha_2"),
    ])
    stamp(value)
    receipt = compile_recipe(value, as_of=AS_OF)
    assert [row["transition_id"] for row in receipt["campaign_history"]] == [
        "ctr_campaign_1", "ctr_campaign_2", "ctr_campaign_3", "ctr_campaign_4", "ctr_campaign_5"
    ]
    assert receipt["current_campaign_states"] == {
        "cmp_meeder_alpha_1": "CLOSED",
        "cmp_meeder_alpha_2": "INITIATED",
    }

    value = recipe()
    value["campaign_transitions"].append(
        _transition("ctr_overlap", sequence=1, previous=None, from_state="IDLE", to_state="INITIATED", at="2026-05-17T20:01:00Z", campaign_id="cmp_overlap")
    )
    rejected(value, "new_campaign_before_prior_close")


def test_campaign_skips_reversals_unresolved_and_duplicate_edges_fail() -> None:
    value = recipe()
    value["campaign_transitions"].append(
        _transition("ctr_skip", sequence=2, previous="ctr_campaign_1", from_state="INITIATED", to_state="PAUSED", at="2026-05-17T20:01:00Z")
    )
    rejected(value, "invalid_campaign_history")

    value = recipe()
    value["campaign_transitions"][0]["observation_ids"] = ["obs_flow_true_s"]
    rejected(value, "campaign_observation_ineligible")


def test_event_missingness_rights_coverage_and_caller_output_cannot_be_invented() -> None:
    for field, value_to_add in (
        ("missingness", {"state": "present", "reason": None, "zero_substituted": False}),
        ("rights", {"state": "permitted", "policy_id": None}),
        ("coverage_class", "record_history_complete"),
        ("compiled_result", 999),
    ):
        value = recipe()
        event(value, "obs_manager_positive")[field] = value_to_add
        rejected(value, "json_schema:observations")


def test_epoch_intervals_lineage_decision_modes_and_raw_actor_history_are_closed() -> None:
    value = recipe()
    value["manager_complex_epochs"][0]["interval"]["valid_to"] = "2026-03-01T00:00:00Z"
    rejected(value, "epoch_interval_reversed")

    value = recipe()
    value["manager_complex_epochs"][0]["lineage"].update(
        predecessor_epoch_id="mce_old", reason="silent rename"
    )
    rejected(value, "epoch_original_has_predecessor")

    value = recipe()
    value["vehicle_epochs"][2]["decision_mode"] = "discretionary"
    rejected(value, "vehicle_class_decision_mode_conflict")

    assert value["manager_complex_epochs"][0]["actor_identity"]["raw_actor_string"]
    assert value["manager_complex_epochs"][0]["actor_identity"]["original_ontology_version"]


@pytest.mark.parametrize(
    "role",
    [
        "institution_or_manager_complex",
        "fund_company",
        "fund_vehicle",
        "manager_or_person",
        "broker_or_research_house",
        "analyst",
        "named_market_actor_or_broker_seat",
        "holder_controller_or_executive",
    ],
)
def test_canonical_eight_china_actor_roles_are_additive_extensions(role: str) -> None:
    value = recipe()
    actor = value["manager_complex_epochs"][0]["actor_identity"]
    actor["role"] = role
    actor["ontology_source"] = "CHINA_ALPHA_INTELLIGENCE_MASTERPLAN"
    stamp(value)
    assert validate(value)


def test_unresolved_complex_never_inflates_independent_research_count() -> None:
    receipt = compile_recipe(recipe(), as_of=AS_OF)
    assert receipt["complex_count_receipt"]["unresolved_complex_epoch_count"] == 1
    assert receipt["complex_count_receipt"]["distinct_eligible_research_complex_count"] == 1

    value = recipe()
    value["observations"] = [event(value, "obs_source_pointer_only")]
    value["theme_comparisons"] = []
    value["campaign_transitions"] = []
    value["reliability"] = [value["reliability"][1]]
    meeder = value["manager_complex_epochs"][0]
    meeder.update(status="unresolved", resolution_state="unresolved", decision_mode="unknown")
    meeder["actor_identity"]["resolution_state"] = "unresolved"
    meeder["actor_identity"]["remap_lineage"] = {
        "state": "unresolved", "predecessor_epoch_id": None,
        "reason": "hostile unresolved", "append_only": True,
    }
    vehicle_row = value["vehicle_epochs"][0]
    vehicle_row.update(status="unresolved", resolution_state="unresolved", decision_mode="unknown", vehicle_class="synthetic_fund_of_funds")
    vehicle_row["lineage"] = {
        "state": "unresolved", "predecessor_epoch_id": None,
        "reason": "hostile unresolved", "append_only": True,
    }
    stamp(value)
    compiled = compile_recipe(value, as_of=AS_OF)
    assert compiled["complex_count_receipt"]["distinct_eligible_research_complex_count"] == 0


def test_same_complex_deductions_cannot_be_negative_when_complexes_exceed_vehicles() -> None:
    value = recipe()
    for ordinal in range(5):
        row = deepcopy(value["manager_complex_epochs"][1])
        row["manager_complex_id"] = f"mcx_extra_{ordinal}"
        row["complex_epoch_id"] = f"mce_extra_{ordinal}"
        row["actor_identity"]["raw_actor_string"] = f"Synthetic extra {ordinal}"
        value["manager_complex_epochs"].append(row)
    stamp(value)
    count = compile_recipe(value, as_of=AS_OF)["complex_count_receipt"]
    assert count["same_complex_multivehicle_deductions"] == 0
    assert count["same_complex_multivehicle_deductions"] >= 0


def test_independence_axes_remain_separate_and_declarative_unverified() -> None:
    independence = compile_recipe(recipe(), as_of=AS_OF)["complex_count_receipt"]["independence"]
    assert set(independence) == {
        "source_independence", "information_novelty", "mechanism_independence"
    }
    assert {
        (row["state"], row["assessment"])
        for row in independence.values()
    } == {("not_assessed", "declarative_unverified")}
    assert all("not independence proof" in row["basis"] for row in independence.values())


def test_reliability_counts_states_cutoffs_and_uncertainty_are_fail_closed() -> None:
    value = recipe()
    value["reliability"][1]["eligibility_state"] = "eligible"
    rejected(value, "reliability_state_coherence_invalid")

    value = recipe()
    value["reliability"][0]["matured_trials"] = 3
    rejected(value, "reliability_count_coherence_invalid")

    value = recipe()
    value["reliability"][0]["uncertainty_method"].update(lower=0.9, upper=0.1)
    rejected(value, "json_schema:reliability")

    receipt = compile_recipe(recipe(), as_of=AS_OF)
    eligible, insufficient = receipt["reliability"]
    assert 0 <= eligible["uncertainty_bounds"]["lower"] <= eligible["posterior"] <= eligible["uncertainty_bounds"]["upper"] <= 1
    assert insufficient["posterior"] is None
    assert insufficient["uncertainty_bounds"] == {"lower": None, "upper": None}

    with pytest.raises(InstitutionalIntelligenceError, match="reliability_cutoff_after_compile_as_of"):
        compile_recipe(recipe(), as_of="2026-07-15T00:00:00Z")


def test_reliability_is_closed_complex_epoch_domain_horizon_action_and_eval_os_only() -> None:
    value = recipe()
    value["reliability"][0]["domain"] = "caller_story"
    rejected(value, "json_schema:reliability")
    value = recipe()
    value["reliability"][0]["manager_complex_id"] = "mcx_wrong"
    rejected(value, "reliability_complex_epoch_unresolved")
    value = recipe()
    value["reliability"][0]["legacy_grade_imported"] = True
    rejected(value, "json_schema:reliability")
    source = inspect.getsource(manager_intent)
    assert all(
        name not in source
        for name in (
            "engine.manager_quality",
            "engine.manager_trades",
            "engine.fund_followability",
        )
    )


def test_k1_closed_vocabularies_are_reused_not_locally_weakened() -> None:
    k1_schema = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    k1_defs = k1_schema["$defs"]
    k1_vocabulary = load_vocabulary()
    k2_schema = json.loads(manager_intent.SCHEMA_PATH.read_text(encoding="utf-8"))
    reused = compile_recipe(recipe(), as_of=AS_OF)["k1_contract_reuse"]
    assert reused["coverage_classes"] == sorted(COVERAGE_CLASSES)
    assert reused["correction_kinds"] == sorted({"none", *CORRECTION_KINDS})
    assert reused["replay_modes"] == sorted(REPLAY_MODES)
    assert reused["vintage_states"] == sorted(VINTAGE_STATES)
    assert reused["rights_states"] == sorted(k1_defs["rights"]["properties"]["state"]["enum"])
    assert reused["missingness_states"] == sorted(k1_defs["missingness"]["properties"]["state"]["enum"])
    assert reused["missingness_reasons"] == sorted(
        value for value in k1_defs["missingness"]["properties"]["reason"]["enum"]
        if value is not None
    )
    assert reused["correction_chronology_states"] == sorted(
        k1_defs["correction"]["properties"]["chronology_state"]["enum"]
    )
    assert reused["independence_axes"] == k1_defs["independence"]["required"]
    assert reused["independence_states"] == sorted(k1_defs["axis"]["properties"]["state"]["enum"])
    assert reused["independence_assessment"] == k1_defs["axis"]["properties"]["assessment"]["const"]
    assert reused["clock_classes"] == sorted(k1_vocabulary["clock_classes"])
    assert reused["clock_grains"] == sorted(k1_defs["nativeClock"]["properties"]["grain"]["enum"])
    assert reused["clock_value_states"] == sorted(k1_defs["nativeClock"]["properties"]["value_state"]["enum"])
    assert reused["object_classes"] == sorted(k1_vocabulary["object_classes"])
    assert reused["authority_classes"] == sorted(k1_schema["properties"]["authority_class"]["enum"])
    assert reused["authority_fields"] == sorted(k1_defs["authority"]["required"])
    assert set(k2_schema["$defs"]["missingReason"]["enum"]) == set(reused["missingness_reasons"])
    assert set(k2_schema["$defs"]["observationCorrection"]["properties"]["kind"]["enum"]) == set(reused["correction_kinds"])
    assert set(k2_schema["$defs"]["campaignCorrection"]["properties"]["kind"]["enum"]) == set(reused["correction_kinds"])


def test_correction_requires_real_k1_append_supersession_lineage() -> None:
    value = recipe()
    successor = deepcopy(event(value, "obs_manager_positive"))
    successor["observation_id"] = "obs_manager_corrected"
    successor["correction"] = {
        "kind": "source_correction",
        "predecessor_observation_id": "obs_manager_positive",
        "reason": "synthetic correction attack",
        "append_only": True,
    }
    value["observations"].append(successor)
    rejected(value, "observation_correction_clock_not_later|observation_correction_k1_lineage_unbound")


def test_no_authority_alias_payload_copy_or_freeform_plane_shape_can_enter() -> None:
    value = recipe()
    value["authority"]["can_rank"] = True
    rejected(value, "json_schema:authority|authority_must_be_all_false")
    value = recipe()
    event(value, "obs_manager_positive")["owner_payload"] = {"shares": 10}
    rejected(value, "json_schema:observations")
    value = recipe()
    event(value, "obs_saturation_positive")["denominator"] = {
        "kind": "public_reported_sleeve",
        "state": "complete",
        "total_positions": 1,
        "included_positions": 1,
        "excluded_positions": 0,
        "missing_positions": 0,
    }
    rejected(value, "plane_measure_denominator_shape_conflict")


def test_recipe_id_and_schema_reject_noncanonical_mutation() -> None:
    value = recipe()
    value["manager_complex_epochs"][0]["status"] = "inactive"
    assert "recipe_id_mismatch" in violations(value)
