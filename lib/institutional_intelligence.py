"""Pure K2-B manager-complex and research-intent contract compiler.

The compiler accepts complete, already validated K1 ``EvidenceRef`` pointers and
bounded descriptor values.  It never opens an owner, copies an owner payload,
persists state, creates a score, or acquires rank/gate/size/origination authority.
Professional investors remain evidence-producing agents, never oracles.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
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
VERSION = "1.1.0"
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
PIT_USABLE_COVERAGE_CLASSES = frozenset({
    "record_history_complete",
    "source_release_snapshot_only",
    "append_only_bitemporal",
    "immutable_generation",
    "prospective_only",
})
EPOCH_APPLICABLE = "APPLICABLE"
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


def _clock_time(clock: Mapping[str, Any], label: str) -> datetime:
    """Map a native K1 clock to a conservative UTC knowability boundary."""
    value = clock.get("value")
    if clock.get("value_state") != "known" or not isinstance(value, str):
        raise InstitutionalIntelligenceError(f"invalid_clock:{label}")
    if clock.get("grain") == "date":
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise InstitutionalIntelligenceError(f"invalid_clock:{label}") from exc
        # A date-only native clock proves no intraday instant. It becomes safely
        # usable at the following UTC midnight, after the entire native date.
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc) + timedelta(days=1)
    if clock.get("grain") == "datetime":
        return _time(value, label)
    raise InstitutionalIntelligenceError(f"invalid_clock:{label}")


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
        if end_time is not None and end_time <= start_time:
            errors.append(f"epoch_interval_reversed:{label}:{prefix}")
    return errors


def _interval_state(row: Mapping[str, Any], cutoff: datetime) -> str:
    """Return bitemporal applicability using inclusive starts/exclusive ends."""
    interval = row.get("interval")
    if not isinstance(interval, Mapping):
        return "EPOCH_INTERVAL_INVALID"
    for dimension in ("effective", "valid", "knowable"):
        try:
            start = _time(interval.get(f"{dimension}_from"), f"{dimension}_from")
            raw_end = interval.get(f"{dimension}_to")
            end = _time(raw_end, f"{dimension}_to") if raw_end is not None else None
        except InstitutionalIntelligenceError:
            return "EPOCH_INTERVAL_INVALID"
        if cutoff < start:
            return f"EPOCH_{dimension.upper()}_NOT_STARTED"
        if end is not None and cutoff >= end:
            return f"EPOCH_{dimension.upper()}_EXPIRED"
    return EPOCH_APPLICABLE


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


def _registry_lineage_errors(
    rows: Mapping[str, Mapping[str, Any]],
    *,
    entity_fields: tuple[str, ...],
    label: str,
) -> list[str]:
    """Validate one append-only epoch registry as a linear acyclic history."""
    errors: list[str] = []
    successors: defaultdict[str, list[str]] = defaultdict(list)
    graph: dict[str, str] = {}
    for epoch_id, row in rows.items():
        lineage = row.get("lineage")
        if not isinstance(lineage, Mapping):
            continue
        state = lineage.get("state")
        predecessor_id = lineage.get("predecessor_epoch_id")
        if state not in {"remapped", "corrected"} and not (
            state == "unresolved" and predecessor_id is not None
        ):
            continue
        predecessor = rows.get(str(predecessor_id))
        if predecessor is None or predecessor_id == epoch_id:
            errors.append(f"{label}_lineage_predecessor_invalid")
            continue
        if any(row.get(field) != predecessor.get(field) for field in entity_fields):
            errors.append(f"{label}_lineage_identity_conflict")
        graph[epoch_id] = str(predecessor_id)
        successors[str(predecessor_id)].append(epoch_id)
        try:
            predecessor_interval = predecessor["interval"]
            interval = row["interval"]
            if state == "remapped":
                for dimension in ("effective", "valid", "knowable"):
                    predecessor_end = predecessor_interval.get(f"{dimension}_to")
                    if predecessor_end is None or _time(
                        predecessor_end,
                        f"{label}:{epoch_id}:{dimension}:predecessor_end",
                    ) > _time(
                        interval.get(f"{dimension}_from"),
                        f"{label}:{epoch_id}:{dimension}:successor_start",
                    ):
                        errors.append(f"{label}_lineage_interval_overlap")
                        break
            elif _time(
                interval.get("knowable_from"),
                f"{label}:{epoch_id}:knowable_from",
            ) <= _time(
                predecessor_interval.get("knowable_from"),
                f"{label}:{epoch_id}:predecessor_knowable_from",
            ):
                errors.append(f"{label}_correction_not_later")
        except (KeyError, InstitutionalIntelligenceError):
            errors.append(f"{label}_lineage_interval_invalid")

    if any(len(epoch_ids) > 1 for epoch_ids in successors.values()):
        errors.append(f"{label}_lineage_not_linear")
    for start in graph:
        seen: set[str] = set()
        cursor: str | None = start
        while cursor in graph:
            if cursor in seen:
                errors.append(f"{label}_lineage_cycle")
                break
            seen.add(cursor)
            cursor = graph[cursor]
    return errors


def _actor_remap_errors(
    complexes: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Bind actor remaps to the manager-complex epoch registry, not free strings."""
    errors: list[str] = []
    successors: defaultdict[str, list[str]] = defaultdict(list)
    graph: dict[str, str] = {}
    for epoch_id, row in complexes.items():
        actor = row.get("actor_identity")
        lineage = row.get("lineage")
        remap = actor.get("remap_lineage") if isinstance(actor, Mapping) else None
        if not isinstance(actor, Mapping) or not isinstance(remap, Mapping):
            continue
        state = remap.get("state")
        row_state = lineage.get("state") if isinstance(lineage, Mapping) else None
        if actor.get("resolution_state") == "unresolved":
            if state != "unresolved":
                errors.append("actor_remap_resolution_conflict")
        elif state == "unresolved":
            errors.append("actor_remap_resolution_conflict")
        if state in {"original", "remapped", "corrected"} and row_state != state:
            errors.append("actor_remap_epoch_lineage_conflict")
        predecessor_id = remap.get("predecessor_epoch_id")
        if state not in {"remapped", "corrected"} and not (
            state == "unresolved" and predecessor_id is not None
        ):
            continue
        predecessor = complexes.get(str(predecessor_id))
        if predecessor is None or predecessor_id == epoch_id:
            errors.append("actor_remap_predecessor_invalid")
            continue
        if predecessor.get("manager_complex_id") != row.get("manager_complex_id"):
            errors.append("actor_remap_identity_conflict")
        predecessor_actor = predecessor.get("actor_identity")
        if isinstance(predecessor_actor, Mapping) and any(
            actor.get(field) != predecessor_actor.get(field)
            for field in ("raw_actor_string", "original_ontology_version")
        ):
            errors.append("actor_remap_raw_history_conflict")
        if not isinstance(lineage, Mapping) or (
            lineage.get("predecessor_epoch_id") != predecessor_id
        ):
            errors.append("actor_remap_epoch_lineage_conflict")
        graph[epoch_id] = str(predecessor_id)
        successors[str(predecessor_id)].append(epoch_id)
    if any(len(epoch_ids) > 1 for epoch_ids in successors.values()):
        errors.append("actor_remap_not_linear")
    for start in graph:
        seen: set[str] = set()
        cursor: str | None = start
        while cursor in graph:
            if cursor in seen:
                errors.append("actor_remap_cycle")
                break
            seen.add(cursor)
            cursor = graph[cursor]
    return errors


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


def _available_time(
    event: Mapping[str, Any],
    reference: Mapping[str, Any] | None = None,
) -> datetime:
    binding = event["reference_binding"]["available_clock"]
    if reference is not None:
        clock = _clock_entry(reference, binding)
        if clock is not None:
            return _clock_time(clock, f"available_clock:{event['observation_id']}")
    value = binding["value"]
    if isinstance(value, str) and len(value) == 10:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise InstitutionalIntelligenceError(
                f"invalid_timestamp:available_clock:{event['observation_id']}"
            ) from exc
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc) + timedelta(days=1)
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
    coverage = str(reference["coverage_class"])
    if coverage not in PIT_USABLE_COVERAGE_CLASSES:
        return f"COVERAGE_{coverage.upper()}"
    freshness = reference["freshness"]
    freshness_state = str(freshness["state"])
    if freshness_state != "native_clock_bound":
        return f"FRESHNESS_{freshness_state.upper()}"
    freshness_clock = next(
        (
            clock
            for clock in reference["clocks"]
            if clock["field"] == freshness["clock_field"]
            and clock["value_state"] == "known"
        ),
        None,
    )
    if freshness_clock is None:
        return "FRESHNESS_CLOCK_UNBOUND"
    if _clock_time(freshness_clock, "freshness_clock") > cutoff:
        return "NOT_KNOWABLE"
    if cutoff < available_at:
        return "NOT_KNOWABLE"
    return "PRESENT"


def _superseded_observations_as_of(
    observations: Mapping[str, Mapping[str, Any]],
    references: Mapping[str, Mapping[str, Any]],
    vehicles: Mapping[str, Mapping[str, Any]],
    complexes: Mapping[str, Mapping[str, Any]],
    filers: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> set[str]:
    """Return predecessors erased only by a usable PIT-known correction."""
    superseded: set[str] = set()
    for successor in observations.values():
        correction = successor.get("correction")
        if not isinstance(correction, Mapping) or correction.get("kind") == "none":
            continue
        reference = references.get(str(successor.get("evidence_reference_id")))
        try:
            if reference is None:
                continue
            available_at = _available_time(successor, reference)
            if (
                available_at <= cutoff
                and _reference_state(reference, available_at, cutoff) == "PRESENT"
                and _observation_epoch_state(
                    successor,
                    reference=reference,
                    vehicles=vehicles,
                    complexes=complexes,
                    filers=filers,
                    cutoff=available_at,
                ) == EPOCH_APPLICABLE
            ):
                superseded.add(str(correction.get("predecessor_observation_id")))
        except (KeyError, InstitutionalIntelligenceError):
            continue
    return superseded


def _superseded_transitions_as_of(
    transitions: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> set[str]:
    """Campaign correction availability is its append-only transitioned_at clock."""
    return {
        str(row["correction"]["supersedes_transition_id"])
        for row in transitions.values()
        if isinstance(row.get("correction"), Mapping)
        and row["correction"].get("kind") != "none"
        and _time(row["transitioned_at"], "campaign_correction_available") <= cutoff
    }


def _complex_exclusion_reason(row: Mapping[str, Any], cutoff: datetime) -> str | None:
    if row.get("resolution_state") != "resolved":
        return "unresolved"
    if row.get("status") != "active":
        return "inactive"
    decision_mode = str(row.get("decision_mode"))
    if decision_mode in {"passive", "systematic", "mixed", "unknown"}:
        return decision_mode
    if decision_mode != "discretionary":
        return "unknown"
    if _interval_state(row, cutoff) != EPOCH_APPLICABLE:
        return "epoch_not_applicable"
    return None


def _saturation_denominator(
    complexes: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> dict[str, Any]:
    eligible: list[str] = []
    excluded: list[dict[str, str]] = []
    for epoch_id in sorted(complexes):
        reason = _complex_exclusion_reason(complexes[epoch_id], cutoff)
        if reason is None:
            eligible.append(epoch_id)
        else:
            excluded.append({"complex_epoch_id": epoch_id, "reason": reason})
    return {
        "kind": "eligible_research_complexes",
        "eligible_complex_epoch_ids": eligible,
        "excluded_complex_epochs": excluded,
    }


def _vehicle_is_discretionary(
    vehicle: Mapping[str, Any] | None,
    complex_epoch: Mapping[str, Any] | None,
    *,
    cutoff: datetime,
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
        and _interval_state(vehicle, cutoff) == EPOCH_APPLICABLE
        and _interval_state(complex_epoch, cutoff) == EPOCH_APPLICABLE
    )


def _observation_epoch_state(
    event: Mapping[str, Any],
    *,
    reference: Mapping[str, Any],
    vehicles: Mapping[str, Mapping[str, Any]],
    complexes: Mapping[str, Mapping[str, Any]],
    filers: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> str:
    vehicle = vehicles.get(str(event.get("vehicle_epoch_id")))
    if not vehicle:
        return "VEHICLE_EPOCH_UNRESOLVED"
    complex_epoch = complexes.get(str(vehicle.get("complex_epoch_id")))
    if not complex_epoch:
        return "COMPLEX_EPOCH_UNRESOLVED"
    for label, row in (("VEHICLE", vehicle), ("COMPLEX", complex_epoch)):
        state = _interval_state(row, cutoff)
        if state != EPOCH_APPLICABLE:
            return f"{label}_{state}"
    if (
        event.get("evidence_basis") == "source_backed_pointer_only"
        and reference.get("owner_store") == "institutional_13f.raw_receipt"
    ):
        native_cik = reference.get("native_identity", {}).get("filer_cik")
        matching_filers = [
            row
            for row in filers.values()
            if row.get("filer_id") == native_cik
            and row.get("complex_epoch_id") == vehicle.get("complex_epoch_id")
            and row.get("resolution_state") == "resolved"
            and row.get("status") == "active"
        ]
        if len(matching_filers) != 1:
            return "FILER_EPOCH_UNRESOLVED"
        state = _interval_state(matching_filers[0], cutoff)
        if state != EPOCH_APPLICABLE:
            return f"FILER_{state}"
    return EPOCH_APPLICABLE


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
    filers: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
    superseded_observations: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    if str(event.get("observation_id")) in superseded_observations:
        return "superseded"
    reference = references.get(str(event.get("evidence_reference_id")))
    if reference is None:
        return "unresolved_identity"
    state = _reference_state(reference, _available_time(event, reference), cutoff)
    if state == "RIGHTS_BLOCKED":
        return "rights_blocked"
    if state not in {"PRESENT"}:
        return "missing"
    if event.get("evidence_basis") == "source_backed_pointer_only":
        return "unresolved_identity"
    epoch_state = _observation_epoch_state(
        event,
        reference=reference,
        vehicles=vehicles,
        complexes=complexes,
        filers=filers,
        cutoff=cutoff,
    )
    if epoch_state != EPOCH_APPLICABLE:
        return "epoch_not_applicable"
    vehicle = vehicles.get(event["vehicle_epoch_id"])
    complex_epoch = complexes.get(str(vehicle.get("complex_epoch_id"))) if vehicle else None
    if not vehicle or not complex_epoch or complex_epoch.get("resolution_state") != "resolved":
        return "unresolved_identity"
    if not _vehicle_is_discretionary(vehicle, complex_epoch, cutoff=cutoff):
        return "passive_or_systematic"
    if _measure_delta(event["measure"]) is None:
        return "unavailable_measure"
    return None


_OWNER_ROW_RAW_STORE = "institutional_13f.raw_receipt"
_OWNER_ROW_CATALOG_STORE = "institutional_13f.catalog_generation"
_OWNER_ROW_EXPECTED_FRESHNESS_FIELD = {
    _OWNER_ROW_RAW_STORE: "clocks.retained_at",
    _OWNER_ROW_CATALOG_STORE: "clocks.published_at",
}


def _owner_row_expected_available_time(
    reference: Mapping[str, Any],
    *,
    expected_owner_store: str,
    label: str,
) -> datetime | None:
    """Return the one lawful PIT-availability instant for an owner-row store.

    ``institutional_13f.raw_receipt``: ``max(clocks.accepted_at,
    clocks.retained_at)`` -- mirrors ``event_13f_operational_knowable_clock_
    conflict``, the law already enforced for the *primary* observation
    binding.  ``institutional_13f.catalog_generation``:
    ``clocks.published_at`` exactly (never the earlier
    ``clocks.source_cutoff_at``).  Returns ``None`` when the reference lacks
    the clocks this owner store requires -- callers treat that as a binding
    error, never as an honest absence.
    """
    clocks = reference.get("clocks", [])
    if not isinstance(clocks, list):
        return None

    def _known(field: str) -> Mapping[str, Any] | None:
        return next(
            (
                clock for clock in clocks
                if isinstance(clock, Mapping)
                and clock.get("field") == field
                and clock.get("value_state") == "known"
            ),
            None,
        )

    try:
        if expected_owner_store == _OWNER_ROW_RAW_STORE:
            accepted = _known("clocks.accepted_at")
            retained = _known("clocks.retained_at")
            if accepted is None or retained is None:
                return None
            return max(
                _clock_time(accepted, f"{label}:accepted_at"),
                _clock_time(retained, f"{label}:retained_at"),
            )
        if expected_owner_store == _OWNER_ROW_CATALOG_STORE:
            published = _known("clocks.published_at")
            if published is None:
                return None
            return _clock_time(published, f"{label}:published_at")
    except InstitutionalIntelligenceError:
        return None
    return None


def _owner_row_pit_clock_errors(
    binding: Mapping[str, Any],
    reference: Mapping[str, Any],
    *,
    expected_owner_store: str,
    label: str,
) -> list[str]:
    """Pin one owner-row sub-binding's declared clock to the honest one.

    Without this, a sub-binding could declare ``available_clock`` on an
    earlier, unrelated native clock (e.g. ``clocks.accepted_at`` instead of
    the operational ``max(accepted_at, retained_at)``, or
    ``clocks.source_cutoff_at`` instead of ``clocks.published_at``) and
    silently steer PIT availability -- the exact forged-clock-field gap this
    law closes for every owner-row sub-binding, mirroring the field pin the
    primary observation binding already enforces for
    ``institutional_13f.raw_receipt``.
    """
    errors: list[str] = []
    expected_freshness_field = _OWNER_ROW_EXPECTED_FRESHNESS_FIELD.get(expected_owner_store)
    if reference.get("freshness", {}).get("clock_field") != expected_freshness_field:
        errors.append(f"owner_row_binding_freshness_clock_field_conflict:{label}")
    expected_time = _owner_row_expected_available_time(
        reference, expected_owner_store=expected_owner_store, label=label
    )
    available_clock = _clock_entry(reference, binding.get("available_clock"))
    try:
        actual_time = (
            _clock_time(available_clock, f"{label}:available_clock")
            if available_clock is not None
            else None
        )
    except InstitutionalIntelligenceError:
        actual_time = None
    if expected_time is None or actual_time is None or actual_time != expected_time:
        errors.append(f"owner_row_binding_available_clock_conflict:{label}")
    return errors


def _owner_row_reference_binding_errors(
    binding: object,
    references: Mapping[str, Mapping[str, Any]],
    *,
    expected_owner_store: str,
    label: str,
) -> tuple[list[str], Mapping[str, Any] | None]:
    """Resolve one owner-row sub-binding against the listed K1 references."""
    if not isinstance(binding, Mapping):
        return [f"owner_row_binding_malformed:{label}"], None
    reference = references.get(str(binding.get("reference_id")))
    if reference is None:
        return [f"owner_row_binding_reference_unresolved:{label}"], None
    errors: list[str] = []
    if binding.get("owner_store") != reference.get("owner_store"):
        errors.append(f"owner_row_binding_owner_store_conflict:{label}")
    if reference.get("owner_store") != expected_owner_store:
        errors.append(f"owner_row_binding_owner_store_mismatch:{label}")
    if binding.get("native_identity") != reference.get("native_identity"):
        errors.append(f"owner_row_binding_native_identity_conflict:{label}")
    valid_clock = _clock_entry(reference, binding.get("valid_clock"))
    if not valid_clock or valid_clock.get("class") != "world_valid":
        errors.append(f"owner_row_binding_valid_clock_conflict:{label}")
    errors.extend(
        _owner_row_pit_clock_errors(
            binding, reference, expected_owner_store=expected_owner_store, label=label
        )
    )
    return errors, reference


def _owner_row_period_errors(
    period: object,
    references: Mapping[str, Mapping[str, Any]],
    *,
    label: str,
) -> tuple[list[str], dict[str, Any]]:
    """Validate one previous/current ``ownerPeriodBinding`` and derive its facts."""
    errors: list[str] = []
    period = period if isinstance(period, Mapping) else {}
    catalog_errors, catalog_ref = _owner_row_reference_binding_errors(
        period.get("catalog_binding"), references,
        expected_owner_store=_OWNER_ROW_CATALOG_STORE,
        label=f"{label}:catalog",
    )
    raw_errors, raw_ref = _owner_row_reference_binding_errors(
        period.get("raw_receipt_binding"), references,
        expected_owner_store=_OWNER_ROW_RAW_STORE,
        label=f"{label}:raw",
    )
    errors.extend(catalog_errors)
    errors.extend(raw_errors)
    row = period.get("row")
    row = row if isinstance(row, Mapping) else {}
    if raw_ref is not None and row.get("accession") != raw_ref.get("native_identity", {}).get("accession"):
        errors.append(f"owner_row_accession_conflict:{label}")
    catalog_report_period = (
        catalog_ref.get("native_identity", {}).get("report_period") if catalog_ref is not None else None
    )
    raw_report_period_clock = (
        next(
            (
                clock for clock in raw_ref.get("clocks", [])
                if clock.get("field") == "clocks.report_period" and clock.get("class") == "world_valid"
            ),
            None,
        )
        if raw_ref is not None
        else None
    )
    raw_report_period = raw_report_period_clock.get("value") if raw_report_period_clock is not None else None
    if catalog_ref is not None and raw_ref is not None and catalog_report_period != raw_report_period:
        errors.append(f"owner_row_report_period_conflict:{label}")
    return errors, {
        "catalog_ref": catalog_ref,
        "raw_ref": raw_ref,
        "row": row,
        "report_period": catalog_report_period if catalog_report_period is not None else raw_report_period,
    }


def _owner_row_binding_errors(
    event: Mapping[str, Any],
    *,
    references: Mapping[str, Mapping[str, Any]],
    reference_id: object,
) -> list[str]:
    """Validate one ``source_backed_owner_row`` observation's ``owner_row_binding``."""
    errors: list[str] = []
    owner_binding = event.get("owner_row_binding")
    owner_binding = owner_binding if isinstance(owner_binding, Mapping) else {}
    security = owner_binding.get("security")
    security = security if isinstance(security, Mapping) else {}
    previous = owner_binding.get("previous")
    current = owner_binding.get("current")

    previous_errors, previous_info = _owner_row_period_errors(previous, references, label="previous")
    current_errors, current_info = _owner_row_period_errors(current, references, label="current")
    errors.extend(previous_errors)
    errors.extend(current_errors)

    cusip = security.get("cusip")
    previous_row = previous_info["row"]
    current_row = current_info["row"]
    if isinstance(previous_row, Mapping) and previous_row.get("cusip") != cusip:
        errors.append("owner_row_security_cusip_conflict:previous")
    if isinstance(current_row, Mapping) and current_row.get("cusip") != cusip:
        errors.append("owner_row_security_cusip_conflict:current")
    if event.get("subject_id") != f"cusip:{cusip}":
        errors.append("owner_row_subject_id_conflict")

    previous_period = previous_info["report_period"]
    current_period = current_info["report_period"]
    if previous_period is not None and current_period is not None:
        try:
            if not date.fromisoformat(str(previous_period)) < date.fromisoformat(str(current_period)):
                errors.append("owner_row_report_period_not_increasing")
        except ValueError:
            errors.append("owner_row_report_period_invalid")

    current_raw_binding = current.get("raw_receipt_binding") if isinstance(current, Mapping) else None
    current_raw_reference_id = (
        current_raw_binding.get("reference_id") if isinstance(current_raw_binding, Mapping) else None
    )
    if str(reference_id) != str(current_raw_reference_id):
        errors.append("owner_row_primary_reference_not_current_raw_receipt")

    measure = event.get("measure")
    measure = measure if isinstance(measure, Mapping) else {}
    if measure.get("kind") == "reported_share_change":
        if measure.get("q_prev") is None or measure.get("q_now") is None:
            errors.append("owner_row_measure_null_quantity_forbidden")
    elif measure.get("kind") != "unavailable":
        errors.append("owner_row_measure_kind_invalid")

    return errors


_OWNER_ROW_BINDING_STORES = (
    ("catalog_binding", _OWNER_ROW_CATALOG_STORE),
    ("raw_receipt_binding", _OWNER_ROW_RAW_STORE),
)


def _owner_row_all_refs_present(
    event: Mapping[str, Any],
    references: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> bool:
    """PIT availability of all four owner-row bound refs gates positivity.

    Availability is always recomputed from each reference's OWN lawful clock
    (:func:`_owner_row_expected_available_time`), never trusted from the
    binding's declared ``available_clock`` -- a forged/mislabeled clock field
    on the binding cannot steer this compile-time gate.
    """
    owner_binding = event.get("owner_row_binding")
    if not isinstance(owner_binding, Mapping):
        return False
    for period_key in ("previous", "current"):
        period = owner_binding.get(period_key)
        if not isinstance(period, Mapping):
            return False
        for binding_key, expected_owner_store in _OWNER_ROW_BINDING_STORES:
            binding = period.get(binding_key)
            if not isinstance(binding, Mapping):
                return False
            reference = references.get(str(binding.get("reference_id")))
            if reference is None or reference.get("owner_store") != expected_owner_store:
                return False
            available_at = _owner_row_expected_available_time(
                reference,
                expected_owner_store=expected_owner_store,
                label=f"owner_row:{period_key}:{binding_key}",
            )
            if available_at is None:
                return False
            if _reference_state(reference, available_at, cutoff) != "PRESENT":
                return False
    return True


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
    errors.extend(_registry_lineage_errors(
        complexes,
        entity_fields=("manager_complex_id",),
        label="manager_complex",
    ))
    errors.extend(_actor_remap_errors(complexes))

    filer_rows = recipe.get("filer_epochs", [])
    filers = _rows_by_id(filer_rows, "filer_epoch_id", errors, "duplicate_filer_epoch")
    for epoch_id, row in filers.items():
        errors.extend(_interval_errors(row, epoch_id))
        errors.extend(_lineage_errors(row, epoch_id))
        complex_epoch = complexes.get(str(row.get("complex_epoch_id")))
        if not complex_epoch or complex_epoch.get("manager_complex_id") != row.get("manager_complex_id"):
            errors.append("filer_complex_epoch_unresolved")
    errors.extend(_registry_lineage_errors(
        filers,
        entity_fields=("filer_id", "manager_complex_id"),
        label="filer",
    ))

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
    errors.extend(_registry_lineage_errors(
        vehicles,
        entity_fields=("vehicle_id", "manager_complex_id"),
        label="vehicle",
    ))

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
        if available_clock:
            epoch_state = _observation_epoch_state(
                event,
                reference=reference,
                vehicles=vehicles,
                complexes=complexes,
                filers=filers,
                cutoff=_clock_time(available_clock, f"event_available:{observation_id}"),
            )
            if epoch_state != EPOCH_APPLICABLE:
                errors.append("event_epoch_not_applicable")
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

        if event.get("evidence_basis") == "source_backed_owner_row":
            errors.extend(
                _owner_row_binding_errors(event, references=references, reference_id=reference_id)
            )

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
            eligibility_cutoff = (
                _clock_time(available_clock, f"event_available:{observation_id}")
                if available_clock
                else datetime.min.replace(tzinfo=timezone.utc)
            )
            if not _vehicle_is_discretionary(
                vehicle,
                complex_epoch,
                cutoff=eligibility_cutoff,
            ):
                errors.append("non_discretionary_vehicle_cannot_emit_manager_intent")
        if plane == "theme_capital_rotation" and denominator.get("comparison_id") not in comparison_ids:
            errors.append("theme_comparison_unresolved")
        if plane == "institutionalization_saturation":
            try:
                saturation_cutoff = (
                    _clock_time(available_clock, f"saturation_available:{observation_id}")
                    if available_clock
                    else datetime.min.replace(tzinfo=timezone.utc)
                )
                expected_denominator = _saturation_denominator(complexes, saturation_cutoff)
                if denominator != expected_denominator:
                    errors.append("saturation_denominator_not_derived")
                if measure.get("kind") == "complex_presence":
                    present_ids = list(measure.get("present_complex_epoch_ids", []))
                    eligible_ids = set(expected_denominator["eligible_complex_epoch_ids"])
                    if measure.get("state") == "observed":
                        if not present_ids or not set(present_ids) <= eligible_ids:
                            errors.append("saturation_observed_shape_invalid")
                    elif present_ids:
                        errors.append("saturation_unavailable_shape_invalid")
            except InstitutionalIntelligenceError:
                errors.append("saturation_denominator_not_derived")

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
                        predecessor_reference = references.get(
                            str(predecessor.get("evidence_reference_id"))
                        )
                        if _available_time(event, reference) <= _available_time(
                            predecessor,
                            predecessor_reference,
                        ):
                            errors.append("observation_correction_clock_not_later")
                    except (KeyError, InstitutionalIntelligenceError):
                        errors.append("observation_correction_clock_not_later")
                    predecessor_ref = predecessor.get("evidence_reference_id")
                    ref_correction = reference.get("correction", {})
                    if ref_correction.get("kind") not in CORRECTION_KINDS or predecessor_ref not in set(ref_correction.get("predecessor_reference_ids", [])):
                        errors.append("observation_correction_k1_lineage_unbound")

    correction_predecessors = [
        str(row["correction"]["predecessor_observation_id"])
        for row in observations.values()
        if isinstance(row.get("correction"), Mapping) and row["correction"].get("kind") != "none"
    ]
    if len(correction_predecessors) != len(set(correction_predecessors)):
        errors.append("observation_correction_lineage_not_linear")

    for observation_id, saturation in observations.items():
        if saturation.get("plane") != "institutionalization_saturation":
            continue
        measure = saturation.get("measure")
        if not isinstance(measure, Mapping) or measure.get("kind") != "complex_presence":
            continue
        reference = references.get(str(saturation.get("evidence_reference_id")))
        try:
            saturation_cutoff = _available_time(saturation, reference)
        except (KeyError, InstitutionalIntelligenceError):
            continue
        saturation_superseded = _superseded_observations_as_of(
            observations,
            references,
            vehicles,
            complexes,
            filers,
            saturation_cutoff,
        )
        for complex_epoch_id in measure.get("present_complex_epoch_ids", []):
            backed = False
            for candidate_id, candidate in observations.items():
                candidate_reference = references.get(str(candidate.get("evidence_reference_id")))
                candidate_vehicle = vehicles.get(str(candidate.get("vehicle_epoch_id")))
                try:
                    candidate_available = _available_time(candidate, candidate_reference)
                except (KeyError, InstitutionalIntelligenceError):
                    continue
                if (
                    candidate_id not in saturation_superseded
                    and candidate.get("plane") == "institutionalization_saturation"
                    and isinstance(candidate.get("measure"), Mapping)
                    and candidate["measure"].get("kind") == "complex_presence"
                    and candidate["measure"].get("state") == "observed"
                    and complex_epoch_id in candidate["measure"].get("present_complex_epoch_ids", [])
                    and candidate_vehicle is not None
                    and candidate_vehicle.get("complex_epoch_id") == complex_epoch_id
                    and candidate_reference is not None
                    and candidate_available <= saturation_cutoff
                    and _reference_state(
                        candidate_reference,
                        candidate_available,
                        saturation_cutoff,
                    ) == "PRESENT"
                    and _observation_epoch_state(
                        candidate,
                        reference=candidate_reference,
                        vehicles=vehicles,
                        complexes=complexes,
                        filers=filers,
                        cutoff=candidate_available,
                    ) == EPOCH_APPLICABLE
                ):
                    backed = True
                    break
            if not backed:
                errors.append("saturation_present_complex_unbacked")

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
            if membership_clock and _clock_time(membership_clock, "membership_clock") > as_of:
                errors.append("theme_membership_lookahead")
            if membership_ref and membership_clock and _reference_state(
                membership_ref,
                _clock_time(membership_clock, "membership_clock"),
                as_of,
            ) != "PRESENT":
                errors.append("theme_membership_reference_unusable")
        except InstitutionalIntelligenceError:
            as_of = datetime.max.replace(tzinfo=timezone.utc)
        comparison_superseded = _superseded_observations_as_of(
            observations,
            references,
            vehicles,
            complexes,
            filers,
            as_of,
        )
        for observation_id in expected_members:
            event = observations.get(str(observation_id))
            if not event:
                errors.append("theme_observation_unresolved")
                continue
            if event.get("plane") != "theme_capital_rotation":
                errors.append("theme_observation_wrong_plane")
            if event.get("theme_id") != comparison.get("theme_id") or event.get("theme_epoch_id") != comparison.get("theme_epoch_id"):
                errors.append("theme_observation_epoch_conflict")
            event_reference = references.get(str(event.get("evidence_reference_id")))
            if _available_time(event, event_reference) > as_of:
                errors.append("theme_peer_not_knowable_at_cutoff")
        target = observations.get(str(target_id))
        for peer_id in peer_ids:
            peer = observations.get(str(peer_id))
            if target and peer and target.get("subject_id") == peer.get("subject_id"):
                errors.append("theme_target_peer_subject_not_distinct")
        for observation_id in eligible_ids:
            event = observations.get(str(observation_id))
            if event and _observation_ineligible_reason(
                event,
                references=references,
                vehicles=vehicles,
                complexes=complexes,
                filers=filers,
                cutoff=as_of,
                superseded_observations=comparison_superseded,
            ) is not None:
                errors.append("theme_ineligible_member_marked_eligible")
        for excluded in excluded_rows:
            if not isinstance(excluded, Mapping):
                continue
            event = observations.get(str(excluded.get("observation_id")))
            if event:
                actual = _observation_ineligible_reason(
                    event,
                    references=references,
                    vehicles=vehicles,
                    complexes=complexes,
                    filers=filers,
                    cutoff=as_of,
                    superseded_observations=comparison_superseded,
                )
                if actual != excluded.get("reason"):
                    errors.append("theme_exclusion_reason_conflict")

    transition_rows = recipe.get("campaign_transitions", [])
    transitions = _rows_by_id(transition_rows, "transition_id", errors, "duplicate_campaign_transition_id")
    superseded_transitions: set[str] = set()
    transition_correction_predecessors: list[str] = []
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
                transition_correction_predecessors.append(str(predecessor_id))
                if _time(transition["transitioned_at"], "transitioned_at") <= _time(predecessor["transitioned_at"], "transitioned_at"):
                    errors.append("campaign_correction_clock_not_later")
        elif isinstance(correction, Mapping) and (
            correction.get("supersedes_transition_id") is not None or correction.get("reason") is not None
        ):
            errors.append("campaign_original_has_lineage")
    if len(transition_correction_predecessors) != len(set(transition_correction_predecessors)):
        errors.append("campaign_correction_lineage_not_linear")

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
        transition_superseded_observations = _superseded_observations_as_of(
            observations,
            references,
            vehicles,
            complexes,
            filers,
            transitioned_at,
        )
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
                or observation_id in transition_superseded_observations
            ):
                errors.append("campaign_observation_ineligible")
                continue
            reason = _observation_ineligible_reason(
                event,
                references=references,
                vehicles=vehicles,
                complexes=complexes,
                filers=filers,
                cutoff=transitioned_at,
                superseded_observations=transition_superseded_observations,
            )
            if reason is not None:
                errors.append("campaign_observation_ineligible")
            event_reference = references.get(str(event.get("evidence_reference_id")))
            if _available_time(event, event_reference) > transitioned_at:
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
            trial_cutoff = _time(row.get("trial_cutoff_at"), "trial_cutoff_at")
            maturity_cutoff = _time(row.get("maturity_cutoff_at"), "maturity_cutoff_at")
            if maturity_cutoff < trial_cutoff:
                errors.append("reliability_cutoff_order_invalid")
            if complex_epoch and (
                _interval_state(complex_epoch, trial_cutoff) != EPOCH_APPLICABLE
                or _interval_state(complex_epoch, maturity_cutoff) != EPOCH_APPLICABLE
            ):
                errors.append("reliability_epoch_not_applicable")
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
        present_ids = sorted(set(measure["present_complex_epoch_ids"]))
        return {
            "kind": kind,
            "state": measure["state"],
            "present_complex_epoch_ids": present_ids,
            "present_complex_count": (
                len(present_ids) if measure["state"] == "observed" else None
            ),
        }
    return {"kind": "unavailable", "state": str(measure["reason"]).upper(), "value": None}


def _suppressed_measure(event: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "kind": event["measure"]["kind"],
        "state": "not_compiled",
        "reason": reason,
        "value": None,
    }


def _reliability_receipt(
    row: Mapping[str, Any],
    *,
    epoch_state: str,
) -> dict[str, Any]:
    if row["eligibility_state"] != "eligible" or epoch_state != EPOCH_APPLICABLE:
        return {
            **row,
            "eligibility_state": "insufficient",
            "maturity_state": "insufficient",
            "scored_state": "insufficient",
            "epoch_state": epoch_state,
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
        "epoch_state": epoch_state,
        "posterior": posterior,
        "uncertainty_bounds": {"lower": lower, "upper": upper},
    }


def _owner_row_reference_states(
    event: Mapping[str, Any],
    references: Mapping[str, Mapping[str, Any]],
    cutoff: datetime,
) -> dict[str, dict[str, str]] | None:
    """Name which one of the four owner-row sub-references blocked eligibility.

    ``_owner_row_all_refs_present`` collapses all four refs' absence kinds
    into one boolean, so the compiled receipt could not previously say
    whether a non-positive owner-row observation was blocked by
    ``rights_blocked``, a not-yet-knowable clock, or something else, or on
    which of the four bindings.  Additive only: ``None`` for every other
    evidence basis, never touching any existing receipt field.
    """
    if event.get("evidence_basis") != "source_backed_owner_row":
        return None
    owner_binding = event.get("owner_row_binding")
    if not isinstance(owner_binding, Mapping):
        return None
    result: dict[str, dict[str, str]] = {}
    for period_key in ("previous", "current"):
        period = owner_binding.get(period_key)
        period_states: dict[str, str] = {}
        for binding_key, ref_key, expected_owner_store in (
            ("catalog_binding", "catalog", _OWNER_ROW_CATALOG_STORE),
            ("raw_receipt_binding", "raw_receipt", _OWNER_ROW_RAW_STORE),
        ):
            binding = period.get(binding_key) if isinstance(period, Mapping) else None
            reference = (
                references.get(str(binding.get("reference_id")))
                if isinstance(binding, Mapping)
                else None
            )
            if reference is None or reference.get("owner_store") != expected_owner_store:
                period_states[ref_key] = "UNRESOLVED"
                continue
            available_at = _owner_row_expected_available_time(
                reference,
                expected_owner_store=expected_owner_store,
                label=f"owner_row_state:{period_key}:{binding_key}",
            )
            if available_at is None:
                period_states[ref_key] = "AVAILABLE_CLOCK_UNBOUND"
                continue
            period_states[ref_key] = _reference_state(reference, available_at, cutoff)
        result[period_key] = period_states
    return result


def compile_recipe(recipe: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    validated = validate(recipe)
    cutoff = _time(as_of, "as_of")
    references = {row["reference_id"]: row for row in validated["evidence_refs"]}
    complexes = {row["complex_epoch_id"]: row for row in validated["manager_complex_epochs"]}
    filers = {row["filer_epoch_id"]: row for row in validated["filer_epochs"]}
    vehicles = {row["vehicle_epoch_id"]: row for row in validated["vehicle_epochs"]}
    observations = {row["observation_id"]: row for row in validated["observations"]}
    superseded_observations = _superseded_observations_as_of(
        observations,
        references,
        vehicles,
        complexes,
        filers,
        cutoff,
    )

    event_receipts: list[dict[str, Any]] = []
    event_receipt_map: dict[str, dict[str, Any]] = {}
    eligible_intent_complexes: set[str] = set()
    eligible_intent_vehicle_epochs: set[str] = set()
    for event in validated["observations"]:
        reference = references[event["evidence_reference_id"]]
        reference_state = _reference_state(
            reference,
            _available_time(event, reference),
            cutoff,
        )
        vehicle = vehicles[event["vehicle_epoch_id"]]
        complex_epoch = complexes[vehicle["complex_epoch_id"]]
        epoch_state = _observation_epoch_state(
            event,
            reference=reference,
            vehicles=vehicles,
            complexes=complexes,
            filers=filers,
            cutoff=cutoff,
        )
        compiled_measure = _compile_measure(event)
        state = reference_state
        if event["observation_id"] in superseded_observations:
            state = "SUPERSEDED"
        elif reference_state != "PRESENT":
            state = reference_state
        elif epoch_state != EPOCH_APPLICABLE:
            state = epoch_state
        else:
            if event["evidence_basis"] == "source_backed_pointer_only":
                state = "SOURCE_POINTER_ONLY_NO_SECURITY_BINDING"
            elif event["plane"] == "manager_research_intent":
                owner_row_ready = (
                    event["evidence_basis"] != "source_backed_owner_row"
                    or _owner_row_all_refs_present(event, references, cutoff)
                )
                state = (
                    "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
                    if _vehicle_is_discretionary(vehicle, complex_epoch, cutoff=cutoff)
                    and compiled_measure["state"] == "computed"
                    and owner_row_ready
                    else "MANAGER_INTENT_INELIGIBLE_OR_INSUFFICIENT"
                )
            elif event["plane"] == "fund_flow_pressure":
                state = {
                    "computed_true_shares_outstanding": "MECHANICAL_FLOW_RESIDUAL",
                    "proxy_not_true_residual": "MECHANICAL_FLOW_PROXY",
                }.get(compiled_measure["state"], "MECHANICAL_FLOW_UNAVAILABLE")
            elif event["plane"] == "theme_capital_rotation":
                state = "THEME_MEMBER_CHANGE" if compiled_measure["state"] == "computed" else "THEME_MEMBER_CHANGE_UNAVAILABLE"
            else:
                state = "SATURATION_OBSERVED" if compiled_measure["state"] == "observed" else "SATURATION_UNAVAILABLE"
        measure = (
            compiled_measure
            if state in {
                "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT",
                "MECHANICAL_FLOW_RESIDUAL",
                "MECHANICAL_FLOW_PROXY",
                "THEME_MEMBER_CHANGE",
                "SATURATION_OBSERVED",
            }
            else _suppressed_measure(event, state)
        )
        receipt = {
            "observation_id": event["observation_id"],
            "plane": event["plane"],
            "state": state,
            "reference_state": reference_state,
            "epoch_state": epoch_state,
            "evidence_reference_id": event["evidence_reference_id"],
            "evidence_basis": event["evidence_basis"],
            "measure": measure,
            "denominator": (
                _saturation_denominator(complexes, cutoff)
                if event["plane"] == "institutionalization_saturation"
                else event["denominator"]
            ),
            "correction": event["correction"],
            "owner_row_reference_states": _owner_row_reference_states(event, references, cutoff),
        }
        event_receipts.append(receipt)
        event_receipt_map[event["observation_id"]] = receipt
        if state == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT":
            eligible_intent_complexes.add(vehicle["complex_epoch_id"])
            eligible_intent_vehicle_epochs.add(vehicle["vehicle_epoch_id"])

    saturation_denominator = _saturation_denominator(complexes, cutoff)
    saturation_eligible = set(saturation_denominator["eligible_complex_epoch_ids"])
    saturation_present = sorted({
        complex_epoch_id
        for event_receipt in event_receipts
        if event_receipt["plane"] == "institutionalization_saturation"
        and event_receipt["state"] == "SATURATION_OBSERVED"
        for complex_epoch_id in event_receipt["measure"]["present_complex_epoch_ids"]
        if complex_epoch_id in saturation_eligible
    })
    saturation_eligible_count = len(saturation_eligible)
    saturation_receipt = {
        "state": (
            "SATURATION_COMPUTED"
            if saturation_eligible_count > 0
            else "SATURATION_INSUFFICIENT_DENOMINATOR"
        ),
        "as_of": as_of,
        "denominator": saturation_denominator,
        "present_complex_epoch_ids": saturation_present,
        "present_complex_count": len(saturation_present),
        "eligible_complex_count": saturation_eligible_count,
        "saturation_ratio": (
            len(saturation_present) / saturation_eligible_count
            if saturation_eligible_count > 0
            else None
        ),
    }

    comparison_receipts: list[dict[str, Any]] = []
    for comparison in validated["theme_comparisons"]:
        comparison_cutoff = _time(comparison["as_of"], "theme_comparison_as_of")
        member_ids = list(comparison["denominator_receipt"]["member_observation_ids"])
        membership_reference = references[comparison["membership_reference_id"]]
        membership_clock = _clock_entry(
            membership_reference,
            comparison["membership_clock_binding"],
        )
        if membership_clock is None:  # validate() already rejects this; defensive only.
            raise InstitutionalIntelligenceError("theme_membership_clock_unbound")
        membership_available = _clock_time(
            membership_clock,
            "theme_membership_available",
        )
        membership_state = _reference_state(
            membership_reference,
            membership_available,
            comparison_cutoff,
        )
        derived_eligible_ids: list[str] = []
        derived_excluded_members: list[dict[str, str]] = []
        comparison_measures: dict[str, dict[str, Any]] = {}
        comparison_superseded = _superseded_observations_as_of(
            observations,
            references,
            vehicles,
            complexes,
            filers,
            comparison_cutoff,
        )
        if comparison_cutoff > cutoff:
            comparison_state = "NOT_YET_KNOWABLE"
            for observation_id in member_ids:
                derived_excluded_members.append({
                    "observation_id": observation_id,
                    "reason": "comparison_not_yet_knowable",
                })
        elif membership_state != "PRESENT":
            comparison_state = "MEMBERSHIP_REFERENCE_UNUSABLE"
            for observation_id in member_ids:
                derived_excluded_members.append({
                    "observation_id": observation_id,
                    "reason": membership_state.lower(),
                })
        else:
            comparison_state = "READY"
            for observation_id in member_ids:
                event = observations[observation_id]
                reason = _observation_ineligible_reason(
                    event,
                    references=references,
                    vehicles=vehicles,
                    complexes=complexes,
                    filers=filers,
                    cutoff=comparison_cutoff,
                    superseded_observations=comparison_superseded,
                )
                if reason is None:
                    comparison_measures[observation_id] = _compile_measure(event)
                    derived_eligible_ids.append(observation_id)
                else:
                    derived_excluded_members.append({
                        "observation_id": observation_id,
                        "reason": reason,
                    })
        derived_denominator = {
            "member_observation_ids": member_ids,
            "eligible_observation_ids": derived_eligible_ids,
            "excluded_members": derived_excluded_members,
        }
        target_id = comparison["target_observation_id"]
        eligible_peer_ids = [
            observation_id
            for observation_id in comparison["peer_observation_ids"]
            if observation_id in derived_eligible_ids
        ]
        target_delta = (
            comparison_measures[target_id].get("reported_share_delta")
            if target_id in derived_eligible_ids
            else None
        )
        peer_deltas = [
            comparison_measures[observation_id].get("reported_share_delta")
            for observation_id in eligible_peer_ids
        ]
        if comparison_state == "NOT_YET_KNOWABLE":
            state = comparison_state
            peer_mean = None
            spread = None
        elif comparison_state == "MEMBERSHIP_REFERENCE_UNUSABLE":
            state = comparison_state
            peer_mean = None
            spread = None
        elif target_id not in derived_eligible_ids:
            state = "TARGET_INELIGIBLE"
            peer_mean = None
            spread = None
        elif eligible_peer_ids and target_delta is not None and all(value is not None for value in peer_deltas):
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
            "target_observation_id": target_id,
            "eligible_peer_observation_ids": eligible_peer_ids,
            "target_reported_share_delta": target_delta,
            "eligible_peer_mean_reported_share_delta": peer_mean,
            "preference_spread": spread,
            "denominator_receipt": derived_denominator,
            "membership_reference_id": comparison["membership_reference_id"],
            "membership_reference_state": membership_state,
            "as_of": comparison["as_of"],
            "compiled_as_of": as_of,
        })

    transitions = {
        row["transition_id"]: row for row in validated["campaign_transitions"]
    }
    superseded_transitions = _superseded_transitions_as_of(transitions, cutoff)
    campaign_history: list[dict[str, Any]] = []
    current_campaign_states: dict[str, str] = {}
    for transition in sorted(
        validated["campaign_transitions"],
        key=lambda row: (row["campaign_id"], row["sequence"], row["transitioned_at"]),
    ):
        transitioned_at = _time(transition["transitioned_at"], "transitioned_at")
        campaign_complex = complexes[transition["complex_epoch_id"]]
        campaign_epoch_state = _interval_state(campaign_complex, transitioned_at)
        if campaign_epoch_state == EPOCH_APPLICABLE:
            for observation_id in transition["observation_ids"]:
                observation = observations[observation_id]
                vehicle = vehicles[observation["vehicle_epoch_id"]]
                vehicle_state = _interval_state(vehicle, transitioned_at)
                if vehicle_state != EPOCH_APPLICABLE:
                    campaign_epoch_state = vehicle_state
                    break
        if transition["transition_id"] in superseded_transitions:
            record_state = "SUPERSEDED"
        elif transitioned_at > cutoff:
            record_state = "NOT_YET_KNOWABLE"
        elif campaign_epoch_state != EPOCH_APPLICABLE:
            record_state = "EPOCH_NOT_APPLICABLE_AT_TRANSITION"
        else:
            record_state = "CURRENT_APPEND_ONLY_RECORD"
            current_campaign_states[transition["campaign_id"]] = transition["to"]
        campaign_history.append({
            **transition,
            "record_state": record_state,
            "transition_epoch_state": campaign_epoch_state,
        })

    resolved_complex_epochs = {
        epoch_id
        for epoch_id, row in complexes.items()
        if row["resolution_state"] == "resolved"
        and row["status"] == "active"
        and _interval_state(row, cutoff) == EPOCH_APPLICABLE
    }
    excluded_vehicle_epochs = {
        epoch_id
        for epoch_id, row in vehicles.items()
        if row["resolution_state"] != "resolved"
        or row["status"] != "active"
        or row["decision_mode"] != "discretionary"
        or row["vehicle_class"] not in ACTIVE_CLASSES
        or row["complex_epoch_id"] not in resolved_complex_epochs
        or _interval_state(row, cutoff) != EPOCH_APPLICABLE
    }
    mechanical_vehicle_epochs = {
        observations[event_receipt["observation_id"]]["vehicle_epoch_id"]
        for event_receipt in event_receipts
        if event_receipt["plane"] == "fund_flow_pressure"
        and event_receipt["state"] in {"MECHANICAL_FLOW_RESIDUAL", "MECHANICAL_FLOW_PROXY"}
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
        complex_epoch = complexes[row["complex_epoch_id"]]
        trial_epoch_state = _interval_state(
            complex_epoch,
            _time(row["trial_cutoff_at"], "trial_cutoff_at"),
        )
        maturity_epoch_state = _interval_state(
            complex_epoch,
            _time(row["maturity_cutoff_at"], "maturity_cutoff_at"),
        )
        epoch_state = (
            trial_epoch_state
            if trial_epoch_state != EPOCH_APPLICABLE
            else maturity_epoch_state
        )
        reliability_receipts.append(
            _reliability_receipt(row, epoch_state=epoch_state)
        )

    return {
        "schema": RECEIPT_SCHEMA,
        "version": VERSION,
        "recipe_id": validated["recipe_id"],
        "as_of": as_of,
        "events": event_receipts,
        "theme_comparisons": comparison_receipts,
        "campaign_history": campaign_history,
        "current_campaign_states": current_campaign_states,
        "institutionalization_saturation": saturation_receipt,
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
