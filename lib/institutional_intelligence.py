"""Pure, pointer-only K2-B manager-complex and research-intent compiler.

It validates caller-declared descriptors in memory only.  It never opens an
institutional owner, persists a payload, ranks, gates, sizes, originates, or
opens an entry.  Historical 13F observations remain historical public facts.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from lib.evidence_foundation import EvidenceFoundationError, validate_reference


SCHEMA = "institutional_intelligence.manager_intent_recipe.v1"
ALL_FALSE_AUTHORITY = {
    "can_rank": False, "can_gate": False, "can_size": False,
    "can_originate": False, "can_open_entry": False,
}
ACTIVE_CLASSES = frozenset({
    "concentrated_discretionary_active", "diversified_discretionary_active",
    "sector_specialist_active",
})
EXCLUDED_CLASSES = frozenset({
    "systematic_active", "thematic_passive", "broad_passive",
    "options_income_overlay", "leveraged_inverse", "synthetic_fund_of_funds",
})
NEXT_CAMPAIGN_STATE = {
    "IDLE": "INITIATED", "INITIATED": "ACCUMULATING",
    "ACCUMULATING": "PAUSED", "PAUSED": "CLOSED",
}
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "institutional_intelligence" / "manager_intent_recipe.v1.schema.json"


class InstitutionalIntelligenceError(ValueError):
    """A K2-B descriptor fails a closed semantic contract."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def compute_recipe_id(recipe: Mapping[str, Any]) -> str:
    return "mri_" + sha256(_canonical({k: v for k, v in recipe.items() if k != "recipe_id"})).hexdigest()


def _time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}") from exc
    if parsed.tzinfo is None:
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}")
    return parsed.astimezone(timezone.utc)


def _schema_errors(recipe: Mapping[str, Any]) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return sorted(error.message for error in Draft202012Validator(schema).iter_errors(recipe))


def _coverage_state(event: Mapping[str, Any], cutoff: datetime) -> str:
    """K1-style coverage/rights/missingness state before any interpretive state."""
    coverage = event["coverage"]
    if coverage["rights"] == "rights_blocked" or event["missingness"]["reason"] == "rights_blocked":
        return "RIGHTS_BLOCKED"
    if coverage["rights"] == "unknown":
        return "RIGHTS_UNKNOWN"
    if coverage["state"] == "unknown":
        return "UNKNOWN_COVERAGE"
    if coverage["state"] == "partial":
        return "PARTIAL_COVERAGE"
    if cutoff < _time(event["knowable_at"], "knowable_at"):
        return "NOT_KNOWABLE"
    if (cutoff - _time(event["published_at"], "published_at")).days > int(event.get("stale_after_days", 180)):
        return "STALE"
    return "OBSERVED"


def _semantic_errors(recipe: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if recipe.get("authority") != ALL_FALSE_AUTHORITY:
        errors.append("authority_must_be_all_false")
    if recipe.get("recipe_id") != compute_recipe_id(recipe):
        errors.append("recipe_id_mismatch")
    try:
        validate_reference(recipe.get("k1_evidence_ref", {}))
    except EvidenceFoundationError:
        errors.append("k1_evidence_ref_invalid")
    complexes = recipe.get("manager_complexes", [])
    identities = {(row.get("manager_complex_id"), row.get("identity_epoch")) for row in complexes}
    if len(identities) != len(complexes):
        errors.append("duplicate_manager_complex_epoch")
    for row in complexes:
        if row.get("identity_aliases"):
            errors.append("identity_aliases_forbidden")
        if row.get("actor_class", "").startswith("cn_") and row.get("actor_class_source") != "CHINA_ALPHA_INTELLIGENCE_ARCHITECTURE_FREEZE":
            errors.append("china_actor_extension_source_unbound")
        if {item.get("filer_id") for item in row.get("filer_epochs", [])} != set(row.get("filer_ids", [])):
            errors.append("filer_epoch_identity_unbound")
    vehicles = {row.get("vehicle_id"): row for row in recipe.get("vehicles", [])}
    if len(vehicles) != len(recipe.get("vehicles", [])):
        errors.append("duplicate_vehicle")
    for vehicle in vehicles.values():
        if (vehicle.get("manager_complex_id"), vehicle.get("manager_identity_epoch")) not in identities:
            errors.append("vehicle_complex_epoch_unresolved")
    events = {row.get("event_id"): row for row in recipe.get("observations", [])}
    if len(events) != len(recipe.get("observations", [])):
        errors.append("duplicate_event")
    ref_ids: set[str] = set()
    for event in events.values():
        vehicle = vehicles.get(event.get("vehicle_id"))
        if vehicle is None:
            errors.append("event_vehicle_unresolved")
            continue
        ref = event.get("evidence_ref", {})
        if set(ref) != {"reference_id", "owner", "object_id", "accession", "source_url", "published_at", "knowable_at"}:
            errors.append("owner_payload_persistence_forbidden")
        if ref.get("reference_id") in ref_ids:
            errors.append("duplicate_or_uncorroborated_evidence_ref")
        ref_ids.add(ref.get("reference_id"))
        if event.get("published_at") != ref.get("published_at") or event.get("knowable_at") != ref.get("knowable_at"):
            errors.append("event_pointer_clock_conflict")
        shares = event.get("shares_outstanding", {})
        if shares.get("state") == "observed" and (not isinstance(shares.get("value"), (int, float)) or isinstance(shares.get("value"), bool) or shares.get("value") <= 0):
            errors.append("observed_shares_must_be_positive_non_null")
        if shares.get("state") in {"absent", "unsupported"} and shares.get("value") is not None:
            errors.append("typed_missing_shares_must_be_null")
        normal = event.get("holdings_normalization", {})
        if event.get("source_kind") == "form_13f":
            if normal.get("basis") != "13f_unscaled_reported_shares":
                errors.append("form_13f_etf_normalization_forbidden")
            if shares.get("state") != "unsupported":
                errors.append("form_13f_shares_outstanding_unsupported")
            clocks = [event.get(key) for key in ("report_period_end", "filed_at", "published_at", "knowable_at")]
            if any(value is None for value in clocks):
                errors.append("form_13f_clock_incomplete")
            else:
                parsed = [_time(value, key) for value, key in zip(clocks, ("report_period_end", "filed_at", "published_at", "knowable_at"))]
                if not (parsed[0] <= parsed[1] <= parsed[2] <= parsed[3]):
                    errors.append("form_13f_clock_order_invalid")
            if event.get("observation_kind") == "live_flow":
                errors.append("form_13f_live_flow_masquerade")
        if event.get("observation_kind") == "mechanical_flow":
            residual = event.get("mechanical_residual")
            if event.get("plane") != "fund_flow_pressure":
                errors.append("mechanical_flow_must_stay_fund_flow_plane")
            if not isinstance(residual, dict):
                errors.append("mechanical_residual_required")
        descriptor = event.get("plane_descriptor", {})
        required_plane_field = {
            "manager_research_intent": "intent_state",
            "fund_flow_pressure": "flow_driver",
            "theme_capital_rotation": "rotation_membership_state",
            "institutionalization_saturation": "saturation_measure_state",
        }.get(event.get("plane"))
        if required_plane_field not in descriptor or len(descriptor) != 1:
            errors.append("plane_descriptor_shape_invalid")
        if event.get("plane") == "manager_research_intent" and vehicle.get("vehicle_class") in EXCLUDED_CLASSES:
            errors.append("non_discretionary_vehicle_cannot_emit_manager_intent")
        comparison = event.get("within_theme_comparison")
        if event.get("observation_kind") == "within_theme_preference" and not isinstance(comparison, dict):
            errors.append("within_theme_comparator_required")
        if isinstance(comparison, dict):
            if comparison.get("theme_id") != event.get("theme_id") or comparison.get("theme_identity_epoch") != event.get("theme_identity_epoch"):
                errors.append("within_theme_identity_or_epoch_mismatch")
            if _time(comparison["as_of"], "comparison_as_of") > _time(comparison["knowable_at"], "comparison_knowable_at"):
                errors.append("within_theme_pit_order_invalid")
            for compared_id in set(comparison["target_observation_ids"] + comparison["comparator_observation_ids"] + comparison["denominator_observation_ids"]):
                compared = events.get(compared_id)
                if compared is None:
                    errors.append("within_theme_comparator_unresolved")
                elif compared["theme_id"] != event["theme_id"] or compared["theme_identity_epoch"] != event["theme_identity_epoch"]:
                    errors.append("within_theme_comparator_epoch_mismatch")
    for event in events.values():
        correction = event.get("correction")
        if correction:
            previous = correction.get("supersedes_event_id")
            if previous not in events or previous == event.get("event_id"):
                errors.append("correction_predecessor_missing_or_self_cycle")
    transitions: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    seen_transition_ids: set[str] = set()
    for transition in recipe.get("campaign_transitions", []):
        if transition.get("transition_id") in seen_transition_ids:
            errors.append("duplicate_campaign_transition_id")
        seen_transition_ids.add(transition.get("transition_id"))
        key = (transition.get("campaign_id"), transition.get("subject_id"), transition.get("manager_complex_id"), transition.get("manager_identity_epoch"))
        transitions[key].append(transition)
        if (transition.get("manager_complex_id"), transition.get("manager_identity_epoch")) not in identities:
            errors.append("campaign_complex_epoch_unresolved")
        for event_id in transition.get("observation_ids", []):
            if event_id not in events:
                errors.append("campaign_observation_unresolved")
        if transition.get("evidence_ref_id") not in ref_ids:
            errors.append("campaign_provenance_unresolved")
    for rows in transitions.values():
        ordered = sorted(rows, key=lambda row: _time(row["transitioned_at"], "transitioned_at"))
        edges: set[tuple[str, str]] = set()
        state = "IDLE"
        for row in ordered:
            edge = (row["from"], row["to"])
            if edge in edges:
                errors.append("duplicate_campaign_transition")
            edges.add(edge)
            if row["from"] != state or NEXT_CAMPAIGN_STATE.get(row["from"]) != row["to"]:
                errors.append("invalid_campaign_history")
            if _time(row["transitioned_at"], "transitioned_at") > _time(row["knowable_at"], "campaign_knowable_at"):
                errors.append("campaign_clock_order_invalid")
            state = row["to"]
    reliability_keys: set[tuple[str, str, str, str, str]] = set()
    for row in recipe.get("reliability", []):
        identity = (row.get("manager_complex_id"), row.get("manager_identity_epoch"))
        if identity not in identities:
            errors.append("reliability_complex_epoch_unresolved")
        key = (*identity, row.get("domain"), row.get("horizon"), row.get("action"))
        if key in reliability_keys:
            errors.append("reliability_dimension_duplicate")
        reliability_keys.add(key)
        if row.get("successes", 0) > row.get("trials", 0):
            errors.append("reliability_successes_exceed_trials")
        if row.get("eligibility_state") == "insufficient" and row.get("maturity_state") != "insufficient":
            errors.append("reliability_insufficient_state_incoherent")
        if row.get("eligibility_state") == "insufficient" and row.get("scored_state") != "insufficient":
            errors.append("reliability_insufficient_state_incoherent")
        if row.get("maturity_state") == "matured":
            if row.get("scored_state") != "scored" or row.get("matured_at") is None:
                errors.append("reliability_maturity_state_incoherent")
            elif _time(row["matured_at"], "reliability_matured_at") > _time(row["cutoff_at"], "reliability_cutoff_at"):
                errors.append("reliability_cutoff_before_maturity")
        if row.get("oracle_semantics") is not False:
            errors.append("oracle_semantics_forbidden")
    return sorted(set(errors))


def violations(recipe: Mapping[str, Any]) -> list[str]:
    return _schema_errors(recipe) + _semantic_errors(recipe)


def validate(recipe: Mapping[str, Any]) -> dict[str, Any]:
    errors = violations(recipe)
    if errors:
        raise InstitutionalIntelligenceError(";".join(errors))
    return dict(recipe)


def reliability_posterior(row: Mapping[str, Any]) -> float | None:
    """A declared shrinkage estimate; insufficient rows refuse a numeric posterior."""
    if row["eligibility_state"] == "insufficient":
        return None
    return (float(row["successes"]) + float(row["prior_strength"]) * float(row["prior_rate"])) / (float(row["trials"]) + float(row["prior_strength"]))


def compile_recipe(recipe: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    validated = validate(recipe)
    cutoff = _time(as_of, "as_of")
    superseded = {row["correction"]["supersedes_event_id"] for row in validated["observations"] if row.get("correction")}
    events: list[dict[str, str]] = []
    observed_intent_complexes: set[tuple[str, str]] = set()
    vehicles = {row["vehicle_id"]: row for row in validated["vehicles"]}
    for event in validated["observations"]:
        coverage_state = _coverage_state(event, cutoff)
        state = "SUPERSEDED" if event["event_id"] in superseded else coverage_state
        if event["observation_kind"] == "mechanical_flow" and coverage_state in {"OBSERVED", "PARTIAL_COVERAGE"} and state != "SUPERSEDED":
            residual = event["mechanical_residual"]
            state = "MECHANICAL_FLOW_RESIDUAL" if residual["state"] == "resolved" and residual["basis"] == "true_shares_outstanding" else "MECHANICAL_FLOW_PROXY_OR_UNRESOLVED"
        vehicle = vehicles[event["vehicle_id"]]
        if state in {"OBSERVED", "PARTIAL_COVERAGE"} and event["plane"] == "manager_research_intent" and vehicle["vehicle_class"] in ACTIVE_CLASSES:
            observed_intent_complexes.add((vehicle["manager_complex_id"], vehicle["manager_identity_epoch"]))
        events.append({"event_id": event["event_id"], "state": state, "coverage_state": coverage_state, "plane": event["plane"]})
    complexes = validated["manager_complexes"]
    resolved = {(row["manager_complex_id"], row["identity_epoch"]) for row in complexes if row["resolution_state"] == "resolved"}
    excluded_vehicle_ids = {row["vehicle_id"] for row in validated["vehicles"] if row["vehicle_class"] in EXCLUDED_CLASSES}
    mechanical_vehicle_ids = {row["vehicle_id"] for row in validated["observations"] if row["observation_kind"] == "mechanical_flow"}
    raw_filers = {filer for row in complexes for filer in row["filer_ids"]}
    count_receipt = {
        "raw_vehicle_count": len(validated["vehicles"]),
        "raw_filer_count": len(raw_filers),
        "distinct_resolved_complex_count": len(resolved),
        "same_complex_vehicle_deductions": len(validated["vehicles"]) - len(resolved),
        "unresolved_complex_count": len(complexes) - len(resolved),
        "excluded_passive_systematic_vehicle_count": len(excluded_vehicle_ids),
        "mechanical_vehicle_count": len(mechanical_vehicle_ids),
        "independent_research_complex_count": len(observed_intent_complexes),
        "independence_state": "declarative_unverified",
    }
    return {
        "schema": "institutional_intelligence.manager_intent_compilation_receipt.v1",
        "recipe_id": validated["recipe_id"], "as_of": as_of, "events": events,
        "complex_count_receipt": count_receipt,
        "independent_research_complex_count": count_receipt["independent_research_complex_count"],
        "reliability": [{**row, "posterior": reliability_posterior(row)} for row in validated["reliability"]],
        "authority": dict(ALL_FALSE_AUTHORITY), "persistence": "none",
    }
