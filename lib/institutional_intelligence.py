"""Pure K2-B manager-complex and research-intent contract compiler.

The compiler accepts complete, already validated K1 ``EvidenceRef`` pointers and
bounded descriptor values.  It never opens an owner, copies an owner payload,
persists state, creates a score, or acquires rank/gate/size/origination authority.
Professional investors remain evidence-producing agents, never oracles.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    CORRECTION_KINDS,
    COVERAGE_CLASSES,
    REPLAY_MODES,
    SCHEMA_PATH as K1_REFERENCE_SCHEMA_PATH,
    VINTAGE_STATES,
    EvidenceFoundationError,
    load_vocabulary,
    validate_reference,
)


SCHEMA = "institutional_intelligence.manager_intent_recipe.v1"
RECEIPT_SCHEMA = "institutional_intelligence.manager_intent_compilation_receipt.v1"
VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "institutional_intelligence" / "manager_intent_recipe.v1.schema.json"

ACTIVE_CLASSES = frozenset({
    "concentrated_discretionary_active",
    "diversified_discretionary_active",
    "sector_specialist_active",
})
PASSIVE_CLASSES = frozenset({"thematic_passive", "broad_passive", "leveraged_inverse"})
SYSTEMATIC_CLASSES = frozenset({"systematic_active"})
MIXED_OR_UNKNOWN_CLASSES = frozenset({"options_income_overlay", "synthetic_fund_of_funds"})
PLANES = (
    "manager_research_intent",
    "fund_flow_pressure",
    "theme_capital_rotation",
    "institutionalization_saturation",
)
NEXT_CAMPAIGN_STATE = {
    "IDLE": "INITIATED",
    "INITIATED": "ACCUMULATING",
    "ACCUMULATING": "PAUSED",
    "PAUSED": "CLOSED",
}


def _load_k1_reference_schema() -> dict[str, Any]:
    try:
        payload = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceFoundationError("k1_reference_schema_unreadable") from exc
    if not isinstance(payload, dict):
        raise EvidenceFoundationError("k1_reference_schema_not_object")
    return payload


_K1_REFERENCE_SCHEMA = _load_k1_reference_schema()
_K1_VOCABULARY = load_vocabulary()
_K1_DEFS = _K1_REFERENCE_SCHEMA["$defs"]
K1_RIGHTS_STATES = frozenset(
    _K1_DEFS["rights"]["properties"]["state"]["enum"]
)
K1_MISSINGNESS_STATES = frozenset(
    _K1_DEFS["missingness"]["properties"]["state"]["enum"]
)
K1_MISSINGNESS_REASONS = frozenset(
    value
    for value in _K1_DEFS["missingness"]["properties"]["reason"]["enum"]
    if value is not None
)
K1_CORRECTION_KINDS = frozenset(
    _K1_DEFS["correction"]["properties"]["kind"]["enum"]
)
K1_CORRECTION_CHRONOLOGY_STATES = frozenset(
    _K1_DEFS["correction"]["properties"]["chronology_state"]["enum"]
)
K1_INDEPENDENCE_AXES = tuple(_K1_DEFS["independence"]["required"])
K1_INDEPENDENCE_STATES = frozenset(
    _K1_DEFS["axis"]["properties"]["state"]["enum"]
)
K1_INDEPENDENCE_ASSESSMENT = _K1_DEFS["axis"]["properties"]["assessment"]["const"]
K1_CLOCK_CLASSES = frozenset(_K1_VOCABULARY["clock_classes"])
K1_CLOCK_GRAINS = frozenset(
    _K1_DEFS["nativeClock"]["properties"]["grain"]["enum"]
)
K1_CLOCK_VALUE_STATES = frozenset(
    _K1_DEFS["nativeClock"]["properties"]["value_state"]["enum"]
)
K1_OBJECT_CLASSES = frozenset(_K1_VOCABULARY["object_classes"])
K1_AUTHORITY_CLASSES = frozenset(
    _K1_REFERENCE_SCHEMA["properties"]["authority_class"]["enum"]
)


class InstitutionalIntelligenceError(ValueError):
    """A K2-B recipe violates the closed contract."""


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def compute_recipe_id(recipe: Mapping[str, Any]) -> str:
    payload = {str(key): value for key, value in recipe.items() if key != "recipe_id"}
    return "mri_" + sha256(_canonical(payload)).hexdigest()


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}") from exc
    if parsed.tzinfo is None:
        raise InstitutionalIntelligenceError(f"invalid_timestamp:{label}")
    return parsed.astimezone(timezone.utc)


def _schema_errors(recipe: Mapping[str, Any]) -> list[str]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstitutionalIntelligenceError("schema_unreadable") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(
        f"json_schema:{'.'.join(str(part) for part in error.absolute_path) or '<root>'}:{error.validator}"
        for error in validator.iter_errors(recipe)
    )


def _rows_by_id(rows: object, field: str, errors: list[str], duplicate_error: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        value = row.get(field)
        if not isinstance(value, str):
            continue
        if value in result:
            errors.append(duplicate_error)
        result[value] = row
    return result


def _interval_errors(row: Mapping[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    interval = row.get("interval")
    if not isinstance(interval, Mapping):
        return [f"epoch_interval_invalid:{label}"]
    for prefix in ("effective", "valid", "knowable"):
        start = interval.get(f"{prefix}_from")
        end = interval.get(f"{prefix}_to")
        try:
            start_time = _time(start, f"{label}:{prefix}_from")
            end_time = _time(end, f"{label}:{prefix}_to") if end is not None else None
        except InstitutionalIntelligenceError:
            errors.append(f"epoch_interval_invalid:{label}:{prefix}")
            continue
        if end_time is not None and end_time < start_time:
            errors.append(f"epoch_interval_reversed:{label}:{prefix}")
    return errors


def _lineage_errors(row: Mapping[str, Any], label: str) -> list[str]:
    lineage = row.get("lineage")
    if not isinstance(lineage, Mapping):
        return [f"epoch_lineage_invalid:{label}"]
    state = lineage.get("state")
    predecessor = lineage.get("predecessor_epoch_id")
    reason = lineage.get("reason")
    if lineage.get("append_only") is not True:
        return [f"epoch_lineage_not_append_only:{label}"]
    if state == "original" and (predecessor is not None or reason is not None):
        return [f"epoch_original_has_predecessor:{label}"]
    if state in {"remapped", "corrected"} and (not predecessor or not reason):
        return [f"epoch_lineage_missing_predecessor:{label}"]
    if state == "unresolved" and not reason:
        return [f"epoch_unresolved_reason_missing:{label}"]
    return []


def _clock_entry(reference: Mapping[str, Any], binding: object) -> Mapping[str, Any] | None:
    if not isinstance(binding, Mapping):
        return None
    field = binding.get("field")
    value = binding.get("value")
    matches = [
        clock
        for clock in reference.get("clocks", [])
        if isinstance(clock, Mapping)
        and clock.get("field") == field
        and clock.get("value_state") == "known"
        and clock.get("value") == value
    ]
    return matches[0] if len(matches) == 1 else None


def _available_time(event: Mapping[str, Any]) -> datetime:
    binding = event["reference_binding"]["available_clock"]
    return _time(binding["value"], f"available_clock:{event['observation_id']}")


def _reference_state(reference: Mapping[str, Any], available_at: datetime, cutoff: datetime) -> str:
    rights = reference["rights"]["state"]
    missingness = reference["missingness"]
    if rights == "rights_blocked":
        return "RIGHTS_BLOCKED"
    if rights == "unknown":
        return "RIGHTS_UNKNOWN"
    if missingness["state"] == "absent":
        return str(missingness["reason"]).upper()
    if cutoff < available_at:
        return "NOT_KNOWABLE"
    return "PRESENT"


def _vehicle_is_discretionary(
    vehicle: Mapping[str, Any] | None,
    complex_epoch: Mapping[str, Any] | None,
) -> bool:
    return bool(
        vehicle
        and complex_epoch
        and vehicle.get("status") == "active"
        and vehicle.get("resolution_state") == "resolved"
        and vehicle.get("decision_mode") == "discretionary"
        and vehicle.get("vehicle_class") in ACTIVE_CLASSES
        and complex_epoch.get("status") == "active"
        and complex_epoch.get("resolution_state") == "resolved"
        and complex_epoch.get("decision_mode") == "discretionary"
    )


def _measure_delta(measure: Mapping[str, Any]) -> float | None:
    if measure.get("kind") not in {"reported_share_change", "theme_member_reported_share_change"}:
        return None
    q_prev = measure.get("q_prev")
    q_now = measure.get("q_now")
    if isinstance(q_prev, bool) or isinstance(q_now, bool):
        return None
    if not isinstance(q_prev, (int, float)) or not isinstance(q_now, (int, float)):
        return None
    return float(q_now) - float(q_prev)


def _observation_ineligible_reason(
    event: Mapping[str, Any],
    *,
    references: Mapping[str, Mapping[str, Any]],
    vehicles: Mapping[str, Mapping[str, Any]],
    complexes: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> str | None:
    reference = references.get(str(event.get("evidence_reference_id")))
    if reference is None:
        return "unresolved_identity"
    state = _reference_state(reference, _available_time(event), cutoff)
    if state == "RIGHTS_BLOCKED":
        return "rights_blocked"
    if state not in {"PRESENT"}:
        return "missing"
    vehicle = vehicles.get(event["vehicle_epoch_id"])
    complex_epoch = complexes.get(str(vehicle.get("complex_epoch_id"))) if vehicle else None
    if not vehicle or not complex_epoch or complex_epoch.get("resolution_state") != "resolved":
        return "unresolved_identity"
    if not _vehicle_is_discretionary(vehicle, complex_epoch):
        return "passive_or_systematic"
    if _measure_delta(event["measure"]) is None:
        return "unavailable_measure"
    return None


def _semantic_errors(recipe: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if recipe.get("authority") != ALL_FALSE_AUTHORITY:
        errors.append("authority_must_be_all_false")
    try:
        if recipe.get("recipe_id") != compute_recipe_id(recipe):
            errors.append("recipe_id_mismatch")
    except (TypeError, ValueError):
        errors.append("recipe_not_canonical_json")

    references: dict[str, Mapping[str, Any]] = {}
    for raw_reference in recipe.get("evidence_refs", []):
        if not isinstance(raw_reference, Mapping):
            continue
        try:
            reference = validate_reference(raw_reference)
        except EvidenceFoundationError:
            errors.append("k1_evidence_ref_invalid")
            continue
        reference_id = reference["reference_id"]
        if reference_id in references:
            errors.append("duplicate_evidence_reference_id")
        references[reference_id] = reference

    complex_rows = recipe.get("manager_complex_epochs", [])
    complexes = _rows_by_id(complex_rows, "complex_epoch_id", errors, "duplicate_manager_complex_epoch")
    complex_pairs: set[tuple[object, object]] = set()
    for epoch_id, row in complexes.items():
        pair = (row.get("manager_complex_id"), epoch_id)
        if pair in complex_pairs:
            errors.append("duplicate_manager_complex_epoch")
        complex_pairs.add(pair)
        errors.extend(_interval_errors(row, epoch_id))
        errors.extend(_lineage_errors(row, epoch_id))
        actor = row.get("actor_identity")
        if isinstance(actor, Mapping):
            if actor.get("resolution_state") != row.get("resolution_state"):
                errors.append("actor_complex_resolution_conflict")
            remap = actor.get("remap_lineage")
            if isinstance(remap, Mapping):
                shadow = {"lineage": remap}
                errors.extend(_lineage_errors(shadow, f"actor:{epoch_id}"))
        if row.get("resolution_state") == "unresolved" and row.get("status") != "unresolved":
            errors.append("unresolved_complex_status_conflict")

    filer_rows = recipe.get("filer_epochs", [])
    filers = _rows_by_id(filer_rows, "filer_epoch_id", errors, "duplicate_filer_epoch")
    for epoch_id, row in filers.items():
        errors.extend(_interval_errors(row, epoch_id))
        errors.extend(_lineage_errors(row, epoch_id))
        complex_epoch = complexes.get(str(row.get("complex_epoch_id")))
        if not complex_epoch or complex_epoch.get("manager_complex_id") != row.get("manager_complex_id"):
            errors.append("filer_complex_epoch_unresolved")

    vehicle_rows = recipe.get("vehicle_epochs", [])
    vehicles = _rows_by_id(vehicle_rows, "vehicle_epoch_id", errors, "duplicate_vehicle_epoch")
    for epoch_id, row in vehicles.items():
        errors.extend(_interval_errors(row, epoch_id))
        errors.extend(_lineage_errors(row, epoch_id))
        complex_epoch = complexes.get(str(row.get("complex_epoch_id")))
        if not complex_epoch or complex_epoch.get("manager_complex_id") != row.get("manager_complex_id"):
            errors.append("vehicle_complex_epoch_unresolved")
        expected_mode = (
            "discretionary" if row.get("vehicle_class") in ACTIVE_CLASSES
            else "passive" if row.get("vehicle_class") in PASSIVE_CLASSES
            else "systematic" if row.get("vehicle_class") in SYSTEMATIC_CLASSES
            else None
        )
        if expected_mode and row.get("decision_mode") != expected_mode:
            errors.append("vehicle_class_decision_mode_conflict")
        if row.get("vehicle_class") in MIXED_OR_UNKNOWN_CLASSES and row.get("decision_mode") not in {"mixed", "unknown"}:
            errors.append("vehicle_class_decision_mode_conflict")

    observations = _rows_by_id(recipe.get("observations", []), "observation_id", errors, "duplicate_observation_id")
    comparison_ids = {
        row.get("comparison_id")
        for row in recipe.get("theme_comparisons", [])
        if isinstance(row, Mapping)
    }
    for observation_id, event in observations.items():
        reference_id = event.get("evidence_reference_id")
        binding = event.get("reference_binding")
        if not isinstance(binding, Mapping) or binding.get("reference_id") != reference_id:
            errors.append("event_reference_id_conflict")
            continue
        reference = references.get(str(reference_id))
        if not reference:
            errors.append("event_reference_unresolved")
            continue
        if binding.get("owner_store") != reference.get("owner_store"):
            errors.append("event_owner_binding_conflict")
        if binding.get("native_identity") != reference.get("native_identity"):
            errors.append("event_native_identity_binding_conflict")
        valid_clock = _clock_entry(reference, binding.get("valid_clock"))
        available_clock = _clock_entry(reference, binding.get("available_clock"))
        if not valid_clock or valid_clock.get("class") != "world_valid":
            errors.append("event_valid_clock_binding_conflict")
        if not available_clock or available_clock.get("class") not in {"source_published", "knowable", "system_recorded", "belief_or_build"}:
            errors.append("event_available_clock_binding_conflict")
        vehicle = vehicles.get(str(event.get("vehicle_epoch_id")))
        if not vehicle:
            errors.append("event_vehicle_epoch_unresolved")
            continue
        complex_epoch = complexes.get(str(vehicle.get("complex_epoch_id")))
        if not complex_epoch:
            errors.append("event_complex_epoch_unresolved")
        if reference.get("owner_store") == "institutional_13f.raw_receipt":
            native = reference.get("native_identity", {})
            owned_filers = {
                row.get("filer_id")
                for row in filers.values()
                if row.get("complex_epoch_id") == vehicle.get("complex_epoch_id")
            }
            if (
                event.get("evidence_basis") == "source_backed_pointer_only"
                and native.get("filer_cik") not in owned_filers
            ):
                errors.append("event_13f_filer_epoch_conflict")
            if binding.get("valid_clock", {}).get("field") != "clocks.report_period":
                errors.append("event_13f_report_period_clock_unbound")
            accepted = next(
                (clock for clock in reference["clocks"] if clock["field"] == "clocks.accepted_at"),
                None,
            )
            retained = next(
                (clock for clock in reference["clocks"] if clock["field"] == "clocks.retained_at"),
                None,
            )
            if accepted and retained:
                expected = max(_time(accepted["value"], "accepted_at"), _time(retained["value"], "retained_at"))
                if not available_clock or _time(available_clock["value"], "available_clock") != expected:
                    errors.append("event_13f_operational_knowable_clock_conflict")
            if event.get("evidence_basis") == "source_backed_pointer_only" and event.get("subject_id") != "unresolved_security_subject":
                errors.append("source_pointer_cannot_bind_security_subject")

        plane = event.get("plane")
        measure = event.get("measure") if isinstance(event.get("measure"), Mapping) else {}
        denominator = event.get("denominator") if isinstance(event.get("denominator"), Mapping) else {}
        expected_shapes = {
            "manager_research_intent": ({"reported_share_change", "unavailable"}, "public_reported_sleeve"),
            "fund_flow_pressure": ({"etf_true_share_residual", "proxy_residual", "unavailable"}, "vehicle_shares_outstanding"),
            "theme_capital_rotation": ({"theme_member_reported_share_change", "unavailable"}, "pit_theme_membership"),
            "institutionalization_saturation": ({"complex_presence", "unavailable"}, "eligible_research_complexes"),
        }
        allowed_measure, expected_denominator = expected_shapes.get(str(plane), (set(), None))
        if measure.get("kind") not in allowed_measure or denominator.get("kind") != expected_denominator:
            errors.append("plane_measure_denominator_shape_conflict")
        if plane == "manager_research_intent":
            total = denominator.get("total_positions")
            parts = [denominator.get(key) for key in ("included_positions", "excluded_positions", "missing_positions")]
            if not isinstance(total, int) or any(not isinstance(item, int) for item in parts) or total != sum(parts):
                errors.append("manager_denominator_arithmetic_invalid")
        if measure.get("kind") == "etf_true_share_residual" and denominator.get("state") != "true_observed":
            errors.append("true_s_residual_denominator_unobserved")
        if measure.get("kind") == "proxy_residual" and denominator.get("state") != "proxy":
            errors.append("proxy_residual_denominator_conflict")
        if plane == "manager_research_intent" and complex_epoch and _measure_delta(measure) is not None:
            if not _vehicle_is_discretionary(vehicle, complex_epoch):
                errors.append("non_discretionary_vehicle_cannot_emit_manager_intent")
        if plane == "theme_capital_rotation" and denominator.get("comparison_id") not in comparison_ids:
            errors.append("theme_comparison_unresolved")
        if measure.get("kind") == "complex_presence":
            if measure.get("state") == "observed" and (
                not isinstance(measure.get("present"), bool)
                or not isinstance(measure.get("position_count"), int)
            ):
                errors.append("saturation_observed_shape_invalid")
            if measure.get("state") == "unavailable" and (
                measure.get("present") is not None or measure.get("position_count") is not None
            ):
                errors.append("saturation_unavailable_shape_invalid")

        correction = event.get("correction")
        if isinstance(correction, Mapping):
            kind = correction.get("kind")
            predecessor_id = correction.get("predecessor_observation_id")
            if kind == "none":
                if predecessor_id is not None or correction.get("reason") is not None:
                    errors.append("observation_original_has_lineage")
            else:
                predecessor = observations.get(str(predecessor_id))
                if not predecessor or predecessor_id == observation_id:
                    errors.append("observation_correction_predecessor_invalid")
                else:
                    if any(event.get(field) != predecessor.get(field) for field in ("vehicle_epoch_id", "subject_id", "plane")):
                        errors.append("observation_correction_identity_conflict")
                    try:
                        if _available_time(event) <= _available_time(predecessor):
                            errors.append("observation_correction_clock_not_later")
                    except (KeyError, InstitutionalIntelligenceError):
                        errors.append("observation_correction_clock_not_later")
                    predecessor_ref = predecessor.get("evidence_reference_id")
                    ref_correction = reference.get("correction", {})
                    if ref_correction.get("kind") not in CORRECTION_KINDS or predecessor_ref not in set(ref_correction.get("predecessor_reference_ids", [])):
                        errors.append("observation_correction_k1_lineage_unbound")

    superseded_observations = {
        str(row["correction"]["predecessor_observation_id"])
        for row in observations.values()
        if isinstance(row.get("correction"), Mapping) and row["correction"].get("kind") != "none"
    }

    comparison_rows = recipe.get("theme_comparisons", [])
    seen_comparisons: set[str] = set()
    for comparison in comparison_rows if isinstance(comparison_rows, list) else []:
        if not isinstance(comparison, Mapping):
            continue
        comparison_id = str(comparison.get("comparison_id"))
        if comparison_id in seen_comparisons:
            errors.append("duplicate_theme_comparison")
        seen_comparisons.add(comparison_id)
        target_id = comparison.get("target_observation_id")
        peer_ids = list(comparison.get("peer_observation_ids", []))
        if target_id in peer_ids:
            errors.append("theme_target_peer_overlap")
        member_ids = set(comparison.get("denominator_receipt", {}).get("member_observation_ids", []))
        expected_members = {target_id, *peer_ids}
        if len(expected_members) < 2 or member_ids != expected_members:
            errors.append("theme_denominator_membership_invalid")
        eligible_ids = set(comparison.get("denominator_receipt", {}).get("eligible_observation_ids", []))
        excluded_rows = comparison.get("denominator_receipt", {}).get("excluded_members", [])
        excluded_ids = {
            row.get("observation_id") for row in excluded_rows if isinstance(row, Mapping)
        }
        if eligible_ids & excluded_ids or eligible_ids | excluded_ids != member_ids:
            errors.append("theme_denominator_partition_invalid")
        if target_id not in eligible_ids:
            errors.append("theme_target_not_eligible")
        membership_ref = references.get(str(comparison.get("membership_reference_id")))
        membership_clock = _clock_entry(membership_ref, comparison.get("membership_clock_binding")) if membership_ref else None
        if not membership_ref or membership_ref.get("owner_store") not in {"theme_graph.evidence", "theme_graph.edge_belief"}:
            errors.append("theme_membership_reference_invalid")
        elif membership_ref["rights"]["state"] != "permitted" or membership_ref["missingness"]["state"] != "present":
            errors.append("theme_membership_reference_unusable")
        if not membership_clock:
            errors.append("theme_membership_clock_unbound")
        try:
            as_of = _time(comparison.get("as_of"), f"theme_as_of:{comparison_id}")
            if membership_clock and _time(membership_clock["value"], "membership_clock") > as_of:
                errors.append("theme_membership_lookahead")
        except InstitutionalIntelligenceError:
            as_of = datetime.max.replace(tzinfo=timezone.utc)
        for observation_id in expected_members:
            event = observations.get(str(observation_id))
            if not event:
                errors.append("theme_observation_unresolved")
                continue
            if event.get("plane") != "theme_capital_rotation":
                errors.append("theme_observation_wrong_plane")
            if event.get("theme_id") != comparison.get("theme_id") or event.get("theme_epoch_id") != comparison.get("theme_epoch_id"):
                errors.append("theme_observation_epoch_conflict")
            if _available_time(event) > as_of:
                errors.append("theme_peer_not_knowable_at_cutoff")
        target = observations.get(str(target_id))
        for peer_id in peer_ids:
            peer = observations.get(str(peer_id))
            if target and peer and target.get("subject_id") == peer.get("subject_id"):
                errors.append("theme_target_peer_subject_not_distinct")
        for observation_id in eligible_ids:
            event = observations.get(str(observation_id))
            if event and _observation_ineligible_reason(event, references=references, vehicles=vehicles, complexes=complexes, cutoff=as_of) is not None:
                errors.append("theme_ineligible_member_marked_eligible")
        for excluded in excluded_rows:
            if not isinstance(excluded, Mapping):
                continue
            event = observations.get(str(excluded.get("observation_id")))
            if event:
                actual = _observation_ineligible_reason(event, references=references, vehicles=vehicles, complexes=complexes, cutoff=as_of)
                if actual != excluded.get("reason"):
                    errors.append("theme_exclusion_reason_conflict")

    transition_rows = recipe.get("campaign_transitions", [])
    transitions = _rows_by_id(transition_rows, "transition_id", errors, "duplicate_campaign_transition_id")
    superseded_transitions: set[str] = set()
    for transition_id, transition in transitions.items():
        correction = transition.get("correction")
        if isinstance(correction, Mapping) and correction.get("kind") != "none":
            predecessor_id = correction.get("supersedes_transition_id")
            predecessor = transitions.get(str(predecessor_id))
            if not predecessor or predecessor_id == transition_id:
                errors.append("campaign_correction_predecessor_invalid")
            elif any(transition.get(field) != predecessor.get(field) for field in ("campaign_id", "sequence", "previous_transition_id", "from", "to", "subject_id", "manager_complex_id", "complex_epoch_id")):
                errors.append("campaign_correction_identity_conflict")
            else:
                superseded_transitions.add(str(predecessor_id))
                if _time(transition["transitioned_at"], "transitioned_at") <= _time(predecessor["transitioned_at"], "transitioned_at"):
                    errors.append("campaign_correction_clock_not_later")
        elif isinstance(correction, Mapping) and (
            correction.get("supersedes_transition_id") is not None or correction.get("reason") is not None
        ):
            errors.append("campaign_original_has_lineage")

    active_transitions = {
        key: value for key, value in transitions.items() if key not in superseded_transitions
    }
    by_campaign: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for transition_id, transition in active_transitions.items():
        by_campaign[str(transition.get("campaign_id"))].append(transition)
        complex_epoch = complexes.get(str(transition.get("complex_epoch_id")))
        if not complex_epoch or complex_epoch.get("manager_complex_id") != transition.get("manager_complex_id") or complex_epoch.get("resolution_state") != "resolved":
            errors.append("campaign_complex_epoch_unresolved")
        transitioned_at = _time(transition.get("transitioned_at"), f"transitioned_at:{transition_id}")
        for observation_id in transition.get("observation_ids", []):
            event = observations.get(str(observation_id))
            if not event:
                errors.append("campaign_observation_unresolved")
                continue
            vehicle = vehicles.get(str(event.get("vehicle_epoch_id")))
            if (
                event.get("plane") != "manager_research_intent"
                or event.get("subject_id") != transition.get("subject_id")
                or not vehicle
                or vehicle.get("complex_epoch_id") != transition.get("complex_epoch_id")
                or observation_id in superseded_observations
            ):
                errors.append("campaign_observation_ineligible")
                continue
            reason = _observation_ineligible_reason(event, references=references, vehicles=vehicles, complexes=complexes, cutoff=transitioned_at)
            if reason is not None:
                errors.append("campaign_observation_ineligible")
            if _available_time(event) > transitioned_at:
                errors.append("campaign_observation_not_yet_knowable")

    campaign_ranges: dict[tuple[str, str, str], list[tuple[datetime, datetime | None, str]]] = defaultdict(list)
    for campaign_id, rows in by_campaign.items():
        ordered = sorted(rows, key=lambda row: int(row.get("sequence", 0)))
        expected_state = "IDLE"
        previous_id: str | None = None
        expected_sequence = 1
        for transition in ordered:
            if transition.get("sequence") != expected_sequence:
                errors.append("campaign_sequence_gap")
            if transition.get("previous_transition_id") != previous_id:
                errors.append("campaign_previous_transition_mismatch")
            if transition.get("from") != expected_state or transition.get("to") != NEXT_CAMPAIGN_STATE.get(expected_state):
                errors.append("invalid_campaign_history")
            previous_id = str(transition.get("transition_id"))
            expected_state = str(transition.get("to"))
            expected_sequence += 1
        if ordered:
            first = _time(ordered[0]["transitioned_at"], "campaign_first")
            close = _time(ordered[-1]["transitioned_at"], "campaign_close") if expected_state == "CLOSED" else None
            stream_key = (
                str(ordered[0].get("subject_id")),
                str(ordered[0].get("manager_complex_id")),
                str(ordered[0].get("complex_epoch_id")),
            )
            campaign_ranges[stream_key].append((first, close, campaign_id))
    for ranges in campaign_ranges.values():
        ranges.sort()
        prior_close: datetime | None = None
        for index, (start, close, _campaign_id) in enumerate(ranges):
            if index and (prior_close is None or start <= prior_close):
                errors.append("new_campaign_before_prior_close")
            prior_close = close

    reliability_keys: set[tuple[object, ...]] = set()
    for row in recipe.get("reliability", []):
        if not isinstance(row, Mapping):
            continue
        key = (
            row.get("manager_complex_id"), row.get("complex_epoch_id"), row.get("domain"),
            row.get("horizon"), row.get("action"),
        )
        if key in reliability_keys:
            errors.append("reliability_dimension_duplicate")
        reliability_keys.add(key)
        complex_epoch = complexes.get(str(row.get("complex_epoch_id")))
        if not complex_epoch or complex_epoch.get("manager_complex_id") != row.get("manager_complex_id"):
            errors.append("reliability_complex_epoch_unresolved")
        counts = [row.get(name) for name in ("trials", "matured_trials", "scored_trials", "successes")]
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in counts):
            continue
        trials, matured, scored, successes = counts
        if not (trials >= matured >= scored >= successes >= 0):
            errors.append("reliability_count_coherence_invalid")
        fully_scored = trials > 0 and matured == trials and scored == trials
        if fully_scored:
            if (row.get("eligibility_state"), row.get("maturity_state"), row.get("scored_state")) != ("eligible", "matured", "scored"):
                errors.append("reliability_state_coherence_invalid")
            if complex_epoch and complex_epoch.get("resolution_state") != "resolved":
                errors.append("reliability_unresolved_complex_eligible")
        else:
            allowed = (
                row.get("eligibility_state") == "insufficient"
                and row.get("maturity_state") in {"immature", "insufficient"}
                and row.get("scored_state") in {"unscored", "insufficient"}
            )
            if not allowed:
                errors.append("reliability_state_coherence_invalid")
        try:
            if _time(row.get("maturity_cutoff_at"), "maturity_cutoff_at") < _time(row.get("trial_cutoff_at"), "trial_cutoff_at"):
                errors.append("reliability_cutoff_order_invalid")
        except InstitutionalIntelligenceError:
            pass

    return sorted(set(errors))


def violations(recipe: Mapping[str, Any]) -> list[str]:
    if not isinstance(recipe, Mapping):
        return ["recipe_not_mapping"]
    return list(dict.fromkeys((*_schema_errors(recipe), *_semantic_errors(recipe))))


def validate(recipe: Mapping[str, Any]) -> dict[str, Any]:
    errors = violations(recipe)
    if errors:
        raise InstitutionalIntelligenceError(";".join(errors))
    try:
        return json.loads(json.dumps(recipe, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise InstitutionalIntelligenceError("recipe_not_canonical_json") from exc


def _compile_measure(event: Mapping[str, Any]) -> dict[str, Any]:
    measure = event["measure"]
    kind = measure["kind"]
    if kind in {"reported_share_change", "theme_member_reported_share_change"}:
        delta = _measure_delta(measure)
        return {
            "kind": kind,
            "state": "computed" if delta is not None else "insufficient_baseline",
            "reported_share_delta": delta,
        }
    if kind == "etf_true_share_residual":
        residual = float(measure["q_now"]) - float(measure["q_prev"]) * (
            float(measure["s_now"]) / float(measure["s_prev"])
        )
        return {
            "kind": kind,
            "state": "computed_true_shares_outstanding",
            "formula": "Q_now - Q_prev * (S_now / S_prev)",
            "residual_shares": residual,
        }
    if kind == "proxy_residual":
        return {
            "kind": kind,
            "state": "proxy_not_true_residual",
            "proxy_method": measure["proxy_method"],
            "residual_shares": None,
        }
    if kind == "complex_presence":
        return {
            "kind": kind,
            "state": measure["state"],
            "present": measure["present"],
            "position_count": measure["position_count"],
        }
    return {"kind": "unavailable", "state": str(measure["reason"]).upper(), "value": None}


def _reliability_receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    if row["eligibility_state"] != "eligible":
        return {
            **row,
            "posterior": None,
            "uncertainty_bounds": {"lower": None, "upper": None},
        }
    alpha = float(row["prior_alpha"]) + int(row["successes"])
    beta = float(row["prior_beta"]) + int(row["scored_trials"]) - int(row["successes"])
    posterior = alpha / (alpha + beta)
    variance = alpha * beta / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
    half_width = 1.959963984540054 * sqrt(variance)
    lower = max(0.0, posterior - half_width)
    upper = min(1.0, posterior + half_width)
    return {
        **row,
        "posterior": posterior,
        "uncertainty_bounds": {"lower": lower, "upper": upper},
    }


def compile_recipe(recipe: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    validated = validate(recipe)
    cutoff = _time(as_of, "as_of")
    references = {row["reference_id"]: row for row in validated["evidence_refs"]}
    complexes = {row["complex_epoch_id"]: row for row in validated["manager_complex_epochs"]}
    vehicles = {row["vehicle_epoch_id"]: row for row in validated["vehicle_epochs"]}
    superseded_observations = {
        row["correction"]["predecessor_observation_id"]
        for row in validated["observations"]
        if row["correction"]["kind"] != "none"
    }

    event_receipts: list[dict[str, Any]] = []
    event_receipt_map: dict[str, dict[str, Any]] = {}
    eligible_intent_complexes: set[str] = set()
    eligible_intent_vehicle_epochs: set[str] = set()
    for event in validated["observations"]:
        reference = references[event["evidence_reference_id"]]
        reference_state = _reference_state(reference, _available_time(event), cutoff)
        vehicle = vehicles[event["vehicle_epoch_id"]]
        complex_epoch = complexes[vehicle["complex_epoch_id"]]
        measure = _compile_measure(event)
        state = reference_state
        if event["observation_id"] in superseded_observations:
            state = "SUPERSEDED"
        elif reference_state == "PRESENT":
            if event["evidence_basis"] == "source_backed_pointer_only":
                state = "SOURCE_POINTER_ONLY_NO_SECURITY_BINDING"
            elif event["plane"] == "manager_research_intent":
                state = (
                    "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
                    if _vehicle_is_discretionary(vehicle, complex_epoch)
                    and measure["state"] == "computed"
                    else "MANAGER_INTENT_INELIGIBLE_OR_INSUFFICIENT"
                )
            elif event["plane"] == "fund_flow_pressure":
                state = {
                    "computed_true_shares_outstanding": "MECHANICAL_FLOW_RESIDUAL",
                    "proxy_not_true_residual": "MECHANICAL_FLOW_PROXY",
                }.get(measure["state"], "MECHANICAL_FLOW_UNAVAILABLE")
            elif event["plane"] == "theme_capital_rotation":
                state = "THEME_MEMBER_CHANGE" if measure["state"] == "computed" else "THEME_MEMBER_CHANGE_UNAVAILABLE"
            else:
                state = "SATURATION_OBSERVED" if measure["state"] == "observed" else "SATURATION_UNAVAILABLE"
        receipt = {
            "observation_id": event["observation_id"],
            "plane": event["plane"],
            "state": state,
            "reference_state": reference_state,
            "evidence_reference_id": event["evidence_reference_id"],
            "evidence_basis": event["evidence_basis"],
            "measure": measure,
            "denominator": event["denominator"],
            "correction": event["correction"],
        }
        event_receipts.append(receipt)
        event_receipt_map[event["observation_id"]] = receipt
        if state == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT":
            eligible_intent_complexes.add(vehicle["complex_epoch_id"])
            eligible_intent_vehicle_epochs.add(vehicle["vehicle_epoch_id"])

    comparison_receipts: list[dict[str, Any]] = []
    observations = {row["observation_id"]: row for row in validated["observations"]}
    for comparison in validated["theme_comparisons"]:
        target = event_receipt_map[comparison["target_observation_id"]]
        eligible_peer_ids = [
            observation_id
            for observation_id in comparison["peer_observation_ids"]
            if observation_id in comparison["denominator_receipt"]["eligible_observation_ids"]
        ]
        target_delta = target["measure"].get("reported_share_delta")
        peer_deltas = [
            event_receipt_map[observation_id]["measure"].get("reported_share_delta")
            for observation_id in eligible_peer_ids
        ]
        if eligible_peer_ids and target_delta is not None and all(value is not None for value in peer_deltas):
            peer_mean = sum(float(value) for value in peer_deltas) / len(peer_deltas)
            state = "WITHIN_THEME_PREFERENCE_COMPUTED"
            spread = float(target_delta) - peer_mean
        else:
            peer_mean = None
            state = "INSUFFICIENT_ELIGIBLE_PEERS"
            spread = None
        comparison_receipts.append({
            "comparison_id": comparison["comparison_id"],
            "state": state,
            "target_observation_id": comparison["target_observation_id"],
            "eligible_peer_observation_ids": eligible_peer_ids,
            "target_reported_share_delta": target_delta,
            "eligible_peer_mean_reported_share_delta": peer_mean,
            "preference_spread": spread,
            "denominator_receipt": comparison["denominator_receipt"],
            "membership_reference_id": comparison["membership_reference_id"],
            "as_of": comparison["as_of"],
        })

    superseded_transitions = {
        row["correction"]["supersedes_transition_id"]
        for row in validated["campaign_transitions"]
        if row["correction"]["kind"] != "none"
    }
    campaign_history: list[dict[str, Any]] = []
    current_campaign_states: dict[str, str] = {}
    for transition in sorted(
        validated["campaign_transitions"],
        key=lambda row: (row["campaign_id"], row["sequence"], row["transitioned_at"]),
    ):
        transitioned_at = _time(transition["transitioned_at"], "transitioned_at")
        if transition["transition_id"] in superseded_transitions:
            record_state = "SUPERSEDED"
        elif transitioned_at > cutoff:
            record_state = "NOT_YET_KNOWABLE"
        else:
            record_state = "CURRENT_APPEND_ONLY_RECORD"
            current_campaign_states[transition["campaign_id"]] = transition["to"]
        campaign_history.append({
            **transition,
            "record_state": record_state,
        })

    resolved_complex_epochs = {
        epoch_id
        for epoch_id, row in complexes.items()
        if row["resolution_state"] == "resolved" and row["status"] == "active"
    }
    excluded_vehicle_epochs = {
        epoch_id
        for epoch_id, row in vehicles.items()
        if row["resolution_state"] != "resolved"
        or row["status"] != "active"
        or row["decision_mode"] != "discretionary"
        or row["vehicle_class"] not in ACTIVE_CLASSES
        or row["complex_epoch_id"] not in resolved_complex_epochs
    }
    mechanical_vehicle_epochs = {
        event["vehicle_epoch_id"]
        for event in validated["observations"]
        if event["plane"] == "fund_flow_pressure"
    }
    eligible_vehicle_complexes = {
        vehicles[epoch_id]["complex_epoch_id"] for epoch_id in eligible_intent_vehicle_epochs
    }
    deductions = len(eligible_intent_vehicle_epochs) - len(eligible_vehicle_complexes)
    if deductions < 0:  # defensive invariant: callers cannot create a negative count
        raise InstitutionalIntelligenceError("negative_same_complex_vehicle_deductions")
    count_receipt = {
        "raw_vehicle_epoch_count": len(validated["vehicle_epochs"]),
        "raw_filer_epoch_count": len(validated["filer_epochs"]),
        "resolved_active_complex_epoch_count": len(resolved_complex_epochs),
        "same_complex_multivehicle_deductions": deductions,
        "unresolved_complex_epoch_count": sum(
            row["resolution_state"] != "resolved" for row in validated["manager_complex_epochs"]
        ),
        "excluded_vehicle_epoch_count": len(excluded_vehicle_epochs),
        "mechanical_vehicle_epoch_count": len(mechanical_vehicle_epochs),
        "distinct_eligible_research_complex_count": len(eligible_intent_complexes),
        "independence": {
            axis: {
                "state": "not_assessed",
                "assessment": K1_INDEPENDENCE_ASSESSMENT,
                "basis": "distinct eligible research complex count is not independence proof",
            }
            for axis in K1_INDEPENDENCE_AXES
        },
    }

    reliability_receipts: list[dict[str, Any]] = []
    for row in validated["reliability"]:
        if _time(row["trial_cutoff_at"], "trial_cutoff_at") > cutoff or _time(row["maturity_cutoff_at"], "maturity_cutoff_at") > cutoff:
            raise InstitutionalIntelligenceError("reliability_cutoff_after_compile_as_of")
        reliability_receipts.append(_reliability_receipt(row))

    return {
        "schema": RECEIPT_SCHEMA,
        "version": VERSION,
        "recipe_id": validated["recipe_id"],
        "as_of": as_of,
        "events": event_receipts,
        "theme_comparisons": comparison_receipts,
        "campaign_history": campaign_history,
        "current_campaign_states": current_campaign_states,
        "complex_count_receipt": count_receipt,
        "reliability": reliability_receipts,
        "k1_contract_reuse": {
            "coverage_classes": sorted(COVERAGE_CLASSES),
            "rights_states": sorted(K1_RIGHTS_STATES),
            "missingness_states": sorted(K1_MISSINGNESS_STATES),
            "missingness_reasons": sorted(K1_MISSINGNESS_REASONS),
            "correction_kinds": sorted(K1_CORRECTION_KINDS),
            "correction_chronology_states": sorted(K1_CORRECTION_CHRONOLOGY_STATES),
            "replay_modes": sorted(REPLAY_MODES),
            "vintage_states": sorted(VINTAGE_STATES),
            "independence_axes": list(K1_INDEPENDENCE_AXES),
            "independence_states": sorted(K1_INDEPENDENCE_STATES),
            "independence_assessment": K1_INDEPENDENCE_ASSESSMENT,
            "clock_classes": sorted(K1_CLOCK_CLASSES),
            "clock_grains": sorted(K1_CLOCK_GRAINS),
            "clock_value_states": sorted(K1_CLOCK_VALUE_STATES),
            "object_classes": sorted(K1_OBJECT_CLASSES),
            "authority_classes": sorted(K1_AUTHORITY_CLASSES),
            "authority_fields": sorted(ALL_FALSE_AUTHORITY),
        },
        "authority": dict(ALL_FALSE_AUTHORITY),
        "owner_payloads_copied": False,
        "persistence": "none",
        "master_score": None,
    }


__all__ = [
    "ACTIVE_CLASSES",
    "ALL_FALSE_AUTHORITY",
    "InstitutionalIntelligenceError",
    "PLANES",
    "RECEIPT_SCHEMA",
    "SCHEMA",
    "SCHEMA_PATH",
    "VERSION",
    "compile_recipe",
    "compute_recipe_id",
    "validate",
    "violations",
]
