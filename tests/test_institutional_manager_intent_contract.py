from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest

import lib.institutional_intelligence as manager_intent
from lib.institutional_intelligence import InstitutionalIntelligenceError, compile_recipe, compute_recipe_id, reliability_posterior, validate


FIXTURE = Path(__file__).parent / "fixtures" / "institutional_intelligence" / "source_backed_manager_intent_recipe.json"


def recipe() -> dict:
    row = json.loads(FIXTURE.read_text())
    assert row["recipe_id"] == compute_recipe_id(row)
    return row


def rejected(row: dict, expected: str) -> None:
    row["recipe_id"] = compute_recipe_id(row)
    with pytest.raises(InstitutionalIntelligenceError, match=expected):
        validate(row)


def test_source_backed_k1_pointer_fixture_and_four_planes_are_closed() -> None:
    row = recipe()
    assert validate(row)
    assert row["observations"][0]["evidence_ref"]["accession"] == "0001398344-26-013841"
    assert {event["plane"] for event in row["observations"]} == {"manager_research_intent", "fund_flow_pressure", "theme_capital_rotation", "institutionalization_saturation"}
    assert compile_recipe(row, as_of="2026-06-01T00:00:00Z")["authority"] == {key: False for key in ("can_rank", "can_gate", "can_size", "can_originate", "can_open_entry")}


@pytest.mark.parametrize("state,value", [("observed", None), ("observed", -10), ("observed", 0), ("absent", 1), ("unsupported", 1)])
def test_shares_outstanding_uses_typed_nonzero_semantics(state: str, value: object) -> None:
    row = recipe(); row["observations"][1]["shares_outstanding"] = {"state": state, "value": value}
    rejected(row, "observed_shares_must_be_positive_non_null|typed_missing_shares_must_be_null")


def test_13f_never_uses_etf_normalization_or_live_flow() -> None:
    row = recipe(); row["observations"][0]["holdings_normalization"]["basis"] = "etf_true_shares_outstanding"
    rejected(row, "form_13f_etf_normalization_forbidden")
    row = recipe(); row["observations"][0]["observation_kind"] = "live_flow"
    rejected(row, "form_13f_live_flow_masquerade")


def test_mechanical_residual_is_typed_and_never_launders_into_intent() -> None:
    receipt = compile_recipe(recipe(), as_of="2026-06-01T00:00:00Z")
    assert receipt["events"][1]["state"] == "MECHANICAL_FLOW_PROXY_OR_UNRESOLVED"
    row = recipe(); row["observations"][1]["plane"] = "manager_research_intent"
    rejected(row, "mechanical_flow_must_stay_fund_flow_plane|non_discretionary_vehicle_cannot_emit_manager_intent")
    row = recipe(); row["observations"][1]["mechanical_residual"] = None
    rejected(row, "mechanical_residual_required")


def test_pointer_and_event_clocks_are_one_canonical_source() -> None:
    row = recipe(); row["observations"][0]["evidence_ref"]["knowable_at"] = "2026-05-16T20:00:00Z"
    rejected(row, "event_pointer_clock_conflict")


def test_13f_cutoff_staleness_and_append_supersession_are_lossless() -> None:
    stale = recipe(); stale["observations"][0]["coverage"] = {"state": "complete", "coverage_class": "source_release_snapshot_only", "rights": "permitted"}; stale["observations"][0]["missingness"] = {"state": "present", "reason": None, "zero_substituted": False}; stale["recipe_id"] = compute_recipe_id(stale)
    assert compile_recipe(stale, as_of="2026-05-01T00:00:00Z")["events"][0]["state"] == "NOT_KNOWABLE"
    assert compile_recipe(stale, as_of="2027-01-01T00:00:00Z")["events"][0]["state"] == "STALE"
    amended = recipe(); event = deepcopy(amended["observations"][0]); event["event_id"] = "obs_13f_amend"; event["evidence_ref"]["reference_id"] = "efr_1f6c6c5982b088121fcacb92f3f1e37db8a9b949a6fb8c2d541bccc6ed572014"; event["evidence_ref"]["accession"] = "0001398344-26-013843"; event["correction"] = {"supersedes_event_id": "obs_13f_q1", "reason": "amendment"}; amended["observations"].append(event); amended["recipe_id"] = compute_recipe_id(amended)
    assert compile_recipe(amended, as_of="2026-06-01T00:00:00Z")["events"][0]["state"] == "SUPERSEDED"


def test_unknown_partial_and_rights_blocked_coverage_compile_typed_states() -> None:
    row = recipe(); row["observations"][0]["coverage"] = {"state": "unknown", "coverage_class": "source_release_snapshot_only", "rights": "unknown"}; row["recipe_id"] = compute_recipe_id(row)
    assert compile_recipe(row, as_of="2026-06-01T00:00:00Z")["events"][0]["state"] == "RIGHTS_UNKNOWN"
    row = recipe(); row["observations"][0]["coverage"] = {"state": "partial", "coverage_class": "source_release_snapshot_only", "rights": "permitted"}; row["recipe_id"] = compute_recipe_id(row)
    assert compile_recipe(row, as_of="2026-06-01T00:00:00Z")["events"][0]["state"] == "PARTIAL_COVERAGE"
    row = recipe(); row["observations"][0]["coverage"] = {"state": "complete", "coverage_class": "source_release_snapshot_only", "rights": "rights_blocked"}; row["recipe_id"] = compute_recipe_id(row)
    assert compile_recipe(row, as_of="2026-06-01T00:00:00Z")["events"][0]["state"] == "RIGHTS_BLOCKED"


def test_real_within_theme_comparator_and_denominator_are_epoch_and_pit_bound() -> None:
    row = recipe(); event = row["observations"][2]
    assert validate(row)
    event["within_theme_comparison"]["theme_identity_epoch"] = "theme_old"
    rejected(row, "within_theme_identity_or_epoch_mismatch")


def test_all_four_planes_have_distinct_closed_shapes() -> None:
    row = recipe()
    assert {event["plane"] for event in row["observations"]} == {"manager_research_intent", "fund_flow_pressure", "theme_capital_rotation", "institutionalization_saturation"}
    row["observations"][3]["plane_descriptor"] = {"intent_state": "reported_preference"}
    rejected(row, "plane_descriptor_shape_invalid")


def test_campaign_is_append_only_history_not_free_vocabulary_edges() -> None:
    assert validate(recipe())
    row = recipe()
    for ordinal in range(4):
        duplicate = deepcopy(row["campaign_transitions"][0])
        duplicate["transition_id"] = f"ctr_duplicate_{ordinal}"
        row["campaign_transitions"].append(duplicate)
    rejected(row, "duplicate_campaign_transition|invalid_campaign_history")
    row = recipe(); row["campaign_transitions"][1]["from"] = "IDLE"
    rejected(row, "invalid_campaign_history")
    row = recipe(); row["campaign_transitions"][3]["to"] = "ACCUMULATING"
    rejected(row, "invalid_campaign_history")
    row = recipe(); row["campaign_transitions"][0]["observation_ids"] = ["obs_missing"]
    rejected(row, "campaign_observation_unresolved")
    row = recipe(); row["campaign_transitions"][0]["evidence_ref_id"] = "efr_missing"
    rejected(row, "campaign_provenance_unresolved")
    row = recipe(); post_closed = deepcopy(row["campaign_transitions"][-1]); post_closed.update({"transition_id": "ctr_post_closed", "from": "CLOSED", "to": "IDLE", "transitioned_at": "2026-05-19T20:00:00Z", "knowable_at": "2026-05-19T20:00:00Z"}); row["campaign_transitions"].append(post_closed)
    rejected(row, "invalid_campaign_history")


def test_complex_count_receipt_excludes_passive_only_complexes_and_does_not_claim_independence() -> None:
    row = recipe(); extra = {"manager_complex_id": "mcx_passive_only", "identity_epoch": "mce_2026q2", "actor_class": "global_institutional_manager", "actor_class_source": "B0_MANAGER_COMPLEX_DRAFT", "resolution_state": "resolved", "filer_ids": ["0000000001"], "filer_epochs": [{"filer_id": "0000000001", "identity_epoch": "fie_2026q2"}]}; row["manager_complexes"].append(extra); row["vehicles"].append({"vehicle_id": "veh_passive_only", "vehicle_identity_epoch": "vie_2026q2", "manager_complex_id": "mcx_passive_only", "manager_identity_epoch": "mce_2026q2", "vehicle_class": "broad_passive"}); row["recipe_id"] = compute_recipe_id(row)
    receipt = compile_recipe(row, as_of="2026-06-01T00:00:00Z")["complex_count_receipt"]
    assert receipt["independent_research_complex_count"] == 1
    assert receipt["distinct_resolved_complex_count"] == 2
    assert receipt["independence_state"] == "declarative_unverified"
    assert receipt["excluded_passive_systematic_vehicle_count"] == 2


def test_reliability_is_exact_complex_epoch_and_typed_insufficient() -> None:
    row = recipe(); row["reliability"][0]["manager_complex_id"] = "mcx_unknown"
    rejected(row, "reliability_complex_epoch_unresolved")
    row = recipe(); row["reliability"][0]["manager_identity_epoch"] = "mce_unknown"
    rejected(row, "reliability_complex_epoch_unresolved")
    row = recipe(); row["reliability"][0].update({"eligibility_state": "insufficient", "matured_at": None, "maturity_state": "insufficient", "scored_state": "insufficient", "trials": 0, "successes": 0, "uncertainty": {"state": "insufficient", "lower": None, "upper": None}}); row["recipe_id"] = compute_recipe_id(row)
    assert reliability_posterior(row["reliability"][0]) is None
    assert compile_recipe(row, as_of="2026-06-01T00:00:00Z")["reliability"][0]["posterior"] is None


def test_correction_lineage_china_extension_and_legacy_import_boundary() -> None:
    for actor_class in ("cn_public_fund", "cn_insurer", "cn_securities_firm", "cn_qfii", "cn_social_security", "cn_southbound_holder", "cn_lhb_seat", "cn_institutional_visit_actor"):
        row = recipe(); row["manager_complexes"][0].update({"actor_class": actor_class, "actor_class_source": "CHINA_ALPHA_INTELLIGENCE_ARCHITECTURE_FREEZE"}); row["recipe_id"] = compute_recipe_id(row)
        assert validate(row)
    row = recipe(); row["manager_complexes"][0].update({"actor_class": "cn_public_fund", "actor_class_source": "CHINA_ALPHA_INTELLIGENCE_ARCHITECTURE_FREEZE"}); row["recipe_id"] = compute_recipe_id(row)
    row["manager_complexes"][0]["actor_class_source"] = "B0_MANAGER_COMPLEX_DRAFT"
    rejected(row, "china_actor_extension_source_unbound")
    source = inspect.getsource(manager_intent)
    assert all(name not in source for name in ("engine.manager_quality", "engine.manager_trades", "engine.fund_followability"))


def test_pointer_payload_alias_authority_and_model_prose_attacks_fail_closed() -> None:
    row = recipe(); row["observations"][0]["evidence_ref"]["owner_payload"] = {"shares": 10}
    rejected(row, "Additional properties")
    row = recipe(); row["manager_complexes"][0]["identity_aliases"] = ["famous-name"]
    rejected(row, "identity_aliases_forbidden")
    row = recipe(); row["authority"]["can_rank"] = True
    rejected(row, "False was expected")
    row = recipe(); row["k1_evidence_ref"]["provenance"]["body_embedded"] = True
    rejected(row, "k1_evidence_ref_invalid")
