"""Pure, pointer-only K2-B Manager Research Intent compiler.

This module is deliberately a contract surface: it neither reads an owner, writes a
store, ranks a security, nor turns historical ownership into a live-flow claim.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA = "institutional_intelligence.manager_intent_recipe.v1"
ALL_FALSE_AUTHORITY = {
    "can_rank": False, "can_gate": False, "can_size": False,
    "can_originate": False, "can_open_entry": False,
}
PLANES = frozenset({
    "manager_research_intent", "fund_flow_pressure", "theme_capital_rotation",
    "institutionalization_saturation",
})
VEHICLE_CLASSES = frozenset({
    "concentrated_discretionary_active", "diversified_discretionary_active",
    "sector_specialist_active", "systematic_active", "thematic_passive",
    "broad_passive", "options_income_overlay", "leveraged_inverse", "synthetic_fund_of_funds",
})
CAMPAIGN_STATES = ("IDLE", "INITIATED", "ACCUMULATING", "PAUSED", "CLOSED")
NEXT_CAMPAIGN_STATE = dict(zip(CAMPAIGN_STATES, CAMPAIGN_STATES[1:]))
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "institutional_intelligence" / "manager_intent_recipe.v1.schema.json"


class InstitutionalIntelligenceError(ValueError):
    """A caller attempted an unsafe or semantically incoherent K2-B recipe."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def compute_recipe_id(recipe: Mapping[str, Any]) -> str:
    """Stable identity of the declared recipe, excluding its derived id."""
    payload = {key: value for key, value in recipe.items() if key != "recipe_id"}
    return "mri_" + sha256(_canonical(payload)).hexdigest()


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}") from exc
    if parsed.tzinfo is None:
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}")
    return parsed.astimezone(timezone.utc)


def _schema_errors(recipe: Mapping[str, Any]) -> list[str]:
    validator = Draft202012Validator(_load_schema())
    return sorted(error.message for error in validator.iter_errors(recipe))


def _semantic_errors(recipe: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if recipe.get("authority") != ALL_FALSE_AUTHORITY:
        errors.append("authority_must_be_all_false")
    if recipe.get("recipe_id") != compute_recipe_id(recipe):
        errors.append("recipe_id_mismatch")
    if "caller_vocabulary" in recipe or "model_prose" in recipe:
        errors.append("caller_vocabulary_or_model_prose_forbidden")
    for transition in recipe.get("campaign_transitions", []):
        if NEXT_CAMPAIGN_STATE.get(transition.get("from")) != transition.get("to"):
            errors.append("invalid_campaign_transition")
    complexes = recipe.get("manager_complexes", [])
    vehicles = recipe.get("vehicles", [])
    complex_epochs = {(row.get("manager_complex_id"), row.get("identity_epoch")) for row in complexes}
    seen_complexes: set[tuple[str, str]] = set()
    for row in complexes:
        identity = (row.get("manager_complex_id"), row.get("identity_epoch"))
        if identity in seen_complexes:
            errors.append("duplicate_manager_complex_epoch")
        seen_complexes.add(identity)
        if row.get("identity_aliases"):
            errors.append("identity_aliases_forbidden")
    vehicle_ids: set[str] = set()
    for row in vehicles:
        vehicle_id = row.get("vehicle_id")
        if vehicle_id in vehicle_ids:
            errors.append("duplicate_vehicle")
        vehicle_ids.add(vehicle_id)
        if (row.get("manager_complex_id"), row.get("manager_identity_epoch")) not in complex_epochs:
            errors.append("vehicle_complex_epoch_unresolved")
        if row.get("vehicle_class") not in VEHICLE_CLASSES:
            errors.append("unknown_vehicle_class")
    vehicle_map = {row.get("vehicle_id"): row for row in vehicles}
    event_ids: set[str] = set()
    evidence_ids: set[str] = set()
    event_map: dict[str, Mapping[str, Any]] = {}
    for event in recipe.get("observations", []):
        event_id = event.get("event_id")
        if event_id in event_ids:
            errors.append("duplicate_event")
        event_ids.add(event_id)
        event_map[event_id] = event
        vehicle = vehicle_map.get(event.get("vehicle_id"))
        if vehicle is None:
            errors.append("event_vehicle_unresolved")
            continue
        ref = event.get("evidence_ref", {})
        if set(ref) - {"reference_id", "owner", "object_id", "accession", "source_url", "published_at", "knowable_at"}:
            errors.append("owner_payload_persistence_forbidden")
        reference_id = ref.get("reference_id")
        if reference_id in evidence_ids:
            errors.append("duplicate_or_uncorroborated_evidence_ref")
        evidence_ids.add(reference_id)
        if event.get("plane") not in PLANES:
            errors.append("plane_unknown")
        if event.get("plane") == "manager_research_intent" and vehicle.get("vehicle_class") in {
            "thematic_passive", "broad_passive", "systematic_active", "options_income_overlay",
            "leveraged_inverse", "synthetic_fund_of_funds",
        }:
            errors.append("non_discretionary_vehicle_cannot_emit_manager_intent")
        shares_state = event.get("shares_outstanding", {}).get("state")
        if shares_state in {"absent", "unsupported"} and event.get("shares_outstanding", {}).get("value") is not None:
            errors.append("typed_missing_shares_cannot_have_value")
        if event.get("shares_outstanding", {}).get("value") == 0:
            errors.append("shares_outstanding_zero_fill_forbidden")
        if event.get("observation_kind") == "mechanical_flow" and event.get("plane") != "fund_flow_pressure":
            errors.append("mechanical_flow_must_stay_fund_flow_plane")
        if event.get("source_kind") == "form_13f":
            required = ("report_period_end", "filed_at", "published_at", "knowable_at")
            if not all(key in event for key in required):
                errors.append("form_13f_clock_incomplete")
            else:
                clocks = [_parse_time(event[key], key) for key in required]
                if not (clocks[0] <= clocks[1] <= clocks[2] <= clocks[3]):
                    errors.append("form_13f_clock_order_invalid")
                if event.get("observation_kind") == "live_flow":
                    errors.append("form_13f_live_flow_masquerade")
        comparison = event.get("within_theme_comparison")
        if comparison and comparison.get("theme_id") != event.get("theme_id"):
            errors.append("within_theme_identity_mismatch")
        if comparison and comparison.get("theme_identity_epoch") != event.get("theme_identity_epoch"):
            errors.append("within_theme_epoch_mismatch")
        correction = event.get("correction")
        if correction:
            prior = correction.get("supersedes_event_id")
            if prior not in event_map:
                errors.append("correction_predecessor_missing_or_not_append_only")
    for event in recipe.get("observations", []):
        correction = event.get("correction")
        if correction and correction.get("supersedes_event_id") == event.get("event_id"):
            errors.append("correction_self_cycle")
    skill_keys: set[tuple[str, str, str, str]] = set()
    for row in recipe.get("reliability", []):
        key = (row.get("manager_complex_id"), row.get("domain"), row.get("horizon"), row.get("action"))
        if key in skill_keys:
            errors.append("reliability_dimension_duplicate")
        skill_keys.add(key)
        if row.get("successes", 0) > row.get("trials", 0):
            errors.append("reliability_successes_exceed_trials")
        if row.get("oracle_semantics") is not False:
            errors.append("oracle_semantics_forbidden")
    return sorted(set(errors))


def violations(recipe: Mapping[str, Any]) -> list[str]:
    """Return all closed-schema and semantic violations without modifying input."""
    return _schema_errors(recipe) + _semantic_errors(recipe)


def validate(recipe: Mapping[str, Any]) -> dict[str, Any]:
    errors = violations(recipe)
    if errors:
        raise InstitutionalIntelligenceError(";".join(errors))
    return dict(recipe)


def reliability_posterior(row: Mapping[str, Any]) -> float:
    """Shrunken descriptive reliability, deliberately separated by domain/horizon/action."""
    return (float(row["successes"]) + float(row["prior_strength"]) * float(row["prior_rate"])) / (
        float(row["trials"]) + float(row["prior_strength"])
    )


def compile_recipe(recipe: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    """Compile an in-memory descriptive receipt; this never creates an authority action."""
    validated = validate(recipe)
    cutoff = _parse_time(as_of, "as_of")
    active_events: list[dict[str, Any]] = []
    superseded = {row["correction"]["supersedes_event_id"] for row in validated["observations"] if row.get("correction")}
    for event in validated["observations"]:
        state = "OBSERVED"
        if event["event_id"] in superseded:
            state = "SUPERSEDED"
        elif event.get("coverage", {}).get("rights") == "blocked":
            state = "RIGHTS_BLOCKED"
        elif event.get("source_kind") == "form_13f":
            knowable = _parse_time(event["knowable_at"], "knowable_at")
            published = _parse_time(event["published_at"], "published_at")
            if cutoff < knowable:
                state = "NOT_KNOWABLE"
            elif (cutoff - published).days > int(event.get("stale_after_days", 180)):
                state = "STALE"
        if event.get("observation_kind") == "mechanical_flow":
            state = "MECHANICAL_FLOW_NOT_INTENT" if state == "OBSERVED" else state
        active_events.append({"event_id": event["event_id"], "state": state, "plane": event["plane"]})
    independent = len({(row["manager_complex_id"], row["manager_identity_epoch"]) for row in validated["vehicles"]})
    return {
        "schema": "institutional_intelligence.manager_intent_compilation_receipt.v1",
        "recipe_id": validated["recipe_id"], "as_of": as_of, "events": active_events,
        "independent_research_complex_count": independent,
        "reliability": [{**row, "posterior": reliability_posterior(row)} for row in validated["reliability"]],
        "authority": dict(ALL_FALSE_AUTHORITY), "persistence": "none",
    }
