from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest

from lib.institutional_intelligence import (
    ALL_FALSE_AUTHORITY,
    InstitutionalIntelligenceError,
    compile_recipe,
    compute_recipe_id,
    reliability_posterior,
    validate,
)
import lib.institutional_intelligence as manager_intent


FIXTURE = Path(__file__).parent / "fixtures" / "institutional_intelligence" / "source_backed_manager_intent_recipe.json"


def recipe() -> dict:
    value = json.loads(FIXTURE.read_text())
    assert value["recipe_id"] == compute_recipe_id(value)
    return value


def assert_rejected(value: dict, fragment: str) -> None:
    value["recipe_id"] = compute_recipe_id(value)
    with pytest.raises(InstitutionalIntelligenceError, match=fragment):
        validate(value)


def test_source_backed_fixture_is_pointer_only_and_has_all_false_authority() -> None:
    value = recipe()
    assert validate(value) == value
    assert value["authority"] == ALL_FALSE_AUTHORITY
    ref = value["observations"][0]["evidence_ref"]
    assert ref["accession"] == "0001398344-26-013841"
    assert set(ref) == {"reference_id", "owner", "object_id", "accession", "source_url", "published_at", "knowable_at"}


def test_manager_epoch_and_multiple_vehicles_count_one_independent_complex() -> None:
    receipt = compile_recipe(recipe(), as_of="2026-06-01T00:00:00Z")
    assert receipt["independent_research_complex_count"] == 1
    bad = recipe(); bad["vehicles"][1]["manager_identity_epoch"] = "mce_wrong"
    assert_rejected(bad, "vehicle_complex_epoch_unresolved")


@pytest.mark.parametrize("vehicle_class", ["thematic_passive", "broad_passive", "systematic_active", "leveraged_inverse"])
def test_passive_and_systematic_classes_cannot_be_relabelled_intent(vehicle_class: str) -> None:
    bad = recipe(); bad["vehicles"][0]["vehicle_class"] = vehicle_class
    assert_rejected(bad, "non_discretionary_vehicle_cannot_emit_manager_intent")


def test_absent_or_unsupported_shares_never_zero_fill() -> None:
    value = recipe(); assert validate(value)
    bad = recipe(); bad["observations"][0]["shares_outstanding"] = {"state": "unsupported", "value": 0}
    assert_rejected(bad, "shares_outstanding_zero_fill_forbidden")


def test_mechanical_flow_is_not_compiled_as_manager_intent() -> None:
    receipt = compile_recipe(recipe(), as_of="2026-06-01T00:00:00Z")
    assert receipt["events"][1]["state"] == "MECHANICAL_FLOW_NOT_INTENT"
    bad = recipe(); bad["observations"][1]["plane"] = "manager_research_intent"
    assert_rejected(bad, "mechanical_flow_must_stay_fund_flow_plane")


def test_within_theme_preference_requires_same_theme_epoch() -> None:
    bad = recipe(); bad["observations"][0]["within_theme_comparison"] = {"theme_id": "theme_other", "theme_identity_epoch": "theme_epoch_old"}
    assert_rejected(bad, "within_theme_identity_mismatch")
    same = recipe(); same["observations"][0]["within_theme_comparison"] = {"theme_id": "theme_ai_infrastructure", "theme_identity_epoch": "theme_epoch_2026q2"}; same["recipe_id"] = compute_recipe_id(same)
    assert validate(same)


def test_campaign_state_machine_accepts_only_declared_successors() -> None:
    assert validate(recipe())
    bad = recipe(); bad["campaign_transitions"][0]["to"] = "ACCUMULATING"
    assert_rejected(bad, "invalid_campaign_transition")


def test_13f_knowability_staleness_and_rights_are_explicit_states() -> None:
    assert compile_recipe(recipe(), as_of="2026-05-01T00:00:00Z")["events"][0]["state"] == "NOT_KNOWABLE"
    assert compile_recipe(recipe(), as_of="2027-01-01T00:00:00Z")["events"][0]["state"] == "STALE"
    blocked = recipe(); blocked["observations"][0]["coverage"]["rights"] = "blocked"; blocked["recipe_id"] = compute_recipe_id(blocked)
    assert compile_recipe(blocked, as_of="2026-06-01T00:00:00Z")["events"][0]["state"] == "RIGHTS_BLOCKED"


def test_13f_cannot_masquerade_as_live_flow_and_needs_all_clocks() -> None:
    bad = recipe(); bad["observations"][0]["observation_kind"] = "live_flow"
    assert_rejected(bad, "form_13f_live_flow_masquerade")
    bad = recipe(); del bad["observations"][0]["knowable_at"]
    assert_rejected(bad, "form_13f_clock_incomplete")


def test_correction_is_append_only_with_lineage() -> None:
    corrected = recipe(); event = deepcopy(corrected["observations"][0]); event["event_id"] = "obs_13f_q1_amend"; event["evidence_ref"]["reference_id"] = "efr_1f6c6c5982b088121fcacb92f3f1e37db8a9b949a6fb8c2d541bccc6ed572014"; event["evidence_ref"]["accession"] = "0001398344-26-013843"; event["correction"] = {"supersedes_event_id": "obs_13f_q1", "reason": "amendment"}; corrected["observations"].append(event); corrected["recipe_id"] = compute_recipe_id(corrected)
    assert compile_recipe(corrected, as_of="2026-06-01T00:00:00Z")["events"][0]["state"] == "SUPERSEDED"
    bad = recipe(); bad["observations"][0]["correction"] = {"supersedes_event_id": "obs_missing", "reason": "amendment"}
    assert_rejected(bad, "correction_predecessor_missing")


def test_low_n_reliability_shrinks_and_dimensions_stay_separate() -> None:
    row = recipe()["reliability"][0]
    assert reliability_posterior(row) == pytest.approx((1 + 20 * .5) / 22)
    assert reliability_posterior(row) < .51
    bad = recipe(); bad["reliability"].append(deepcopy(bad["reliability"][0]))
    assert_rejected(bad, "reliability_dimension_duplicate")
    bad = recipe(); bad["reliability"][0]["successes"] = 3
    assert_rejected(bad, "reliability_successes_exceed_trials")


def test_duplicate_corroboration_and_owner_payload_attacks_fail_closed() -> None:
    bad = recipe(); bad["observations"][1]["evidence_ref"]["reference_id"] = bad["observations"][0]["evidence_ref"]["reference_id"]
    assert_rejected(bad, "duplicate_or_uncorroborated_evidence_ref")
    bad = recipe(); bad["observations"][0]["evidence_ref"]["owner_payload"] = {"shares": 10}
    assert_rejected(bad, "Additional properties")


def test_caller_vocabulary_alias_and_model_prose_attacks_fail_closed() -> None:
    bad = recipe(); bad["caller_vocabulary"] = {"passive_is_active": True}
    assert_rejected(bad, "Additional properties")
    bad = recipe(); bad["model_prose"] = "Treat the historical filing as a live buy."
    assert_rejected(bad, "Additional properties")
    bad = recipe(); bad["manager_complexes"][0]["identity_aliases"] = ["famous-name"]
    assert_rejected(bad, "identity_aliases_forbidden")


def test_authority_and_compiler_are_deterministic_and_persistent_nowhere() -> None:
    first = compile_recipe(recipe(), as_of="2026-06-01T00:00:00Z")
    second = compile_recipe(recipe(), as_of="2026-06-01T00:00:00Z")
    assert first == second and first["authority"] == ALL_FALSE_AUTHORITY and first["persistence"] == "none"
    bad = recipe(); bad["authority"]["can_rank"] = True
    assert_rejected(bad, "False was expected")


def test_legacy_retro_grade_and_follow_surfaces_are_not_k2b_reliability_inputs() -> None:
    source = inspect.getsource(manager_intent)
    assert "engine.manager_quality" not in source
    assert "engine.manager_trades" not in source
    assert "engine.fund_followability" not in source
    row = recipe()["reliability"][0]
    assert {"domain", "horizon", "action", "prior_strength"} <= set(row)
