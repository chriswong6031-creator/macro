"""Semantic validator for the pointer-only Evidence Foundation contract.

This module creates no store and performs no owner read.  It validates one
``evidence_foundation.reference.v1`` value against the frozen owner vocabulary;
the owner-native reader remains the only path to the referenced truth.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


SCHEMA = "evidence_foundation.reference.v1"
VERSION = "1.0.0"
VOCABULARY_SCHEMA = "evidence_foundation.vocabulary.v1"
VOCABULARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "evidence_foundation"
    / "vocabulary.v1.json"
)

AUTOMATIC_RELATIONS = frozenset({"exact_duplicate", "same_fact", "same_event"})
NON_AUTOMATIC_RELATIONS = frozenset({
    "corroborates",
    "contradicts",
    "shares_upstream",
    "corrects",
    "supersedes",
    "projects",
})
CORRECTION_KINDS = frozenset({
    "amendment",
    "restatement",
    "source_correction",
    "withdrawal",
    "superseding_generation",
})
ALL_FALSE_AUTHORITY = {
    "can_rank": False,
    "can_gate": False,
    "can_size": False,
    "can_originate": False,
    "can_open_entry": False,
}


class EvidenceFoundationError(ValueError):
    """A reference violates the frozen interoperability contract."""


def canonical_json_bytes(value: Any) -> bytes:
    """Canonical JSON used for deterministic reference identity."""
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


def reference_identity_payload(reference: Mapping[str, Any]) -> dict[str, Any]:
    """All immutable pointer fields, excluding only the derived ``reference_id``."""
    return {str(key): value for key, value in reference.items() if key != "reference_id"}


def compute_reference_id(reference: Mapping[str, Any]) -> str:
    """Return ``efr_<sha256>`` without adding a run/write clock."""
    digest = sha256(canonical_json_bytes(reference_identity_payload(reference))).hexdigest()
    return f"efr_{digest}"


def load_vocabulary(path: str | Path | None = None) -> dict[str, Any]:
    """Load and minimally authenticate the frozen vocabulary file."""
    target = Path(path) if path is not None else VOCABULARY_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceFoundationError(f"vocabulary_unreadable:{target}") from exc
    if not isinstance(payload, dict):
        raise EvidenceFoundationError("vocabulary_not_object")
    if payload.get("schema") != VOCABULARY_SCHEMA or payload.get("version") != VERSION:
        raise EvidenceFoundationError("vocabulary_schema_or_version_mismatch")
    owner_stores = payload.get("owner_stores")
    if not isinstance(owner_stores, dict):
        raise EvidenceFoundationError("vocabulary_owner_stores_missing")
    for name, owner in owner_stores.items():
        if not isinstance(name, str) or not isinstance(owner, dict):
            raise EvidenceFoundationError("vocabulary_owner_entry_invalid")
        if not isinstance(owner.get("native_identity_fields"), list) or not owner[
            "native_identity_fields"
        ]:
            raise EvidenceFoundationError(f"vocabulary_owner_identity_missing:{name}")
        if not isinstance(owner.get("object_classes"), list) or not owner["object_classes"]:
            raise EvidenceFoundationError(f"vocabulary_owner_classes_missing:{name}")
        if not isinstance(owner.get("subject_key_types"), list) or not owner[
            "subject_key_types"
        ]:
            raise EvidenceFoundationError(f"vocabulary_owner_subjects_missing:{name}")
        bindings = owner.get("clock_bindings")
        if not isinstance(bindings, dict) or not bindings:
            raise EvidenceFoundationError(f"vocabulary_owner_clocks_missing:{name}")
        if "synapse_asof_field" not in owner:
            raise EvidenceFoundationError(f"vocabulary_synapse_asof_unspecified:{name}")
        synapse_asof = owner["synapse_asof_field"]
        if synapse_asof is not None and (
            not isinstance(synapse_asof, str) or synapse_asof not in bindings
        ):
            raise EvidenceFoundationError(f"vocabulary_synapse_asof_unbound:{name}")
        if not isinstance(owner.get("reader"), str) or not owner["reader"]:
            raise EvidenceFoundationError(f"vocabulary_owner_reader_missing:{name}")
    return payload


def _parse_clock(value: object, grain: object) -> date | datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if grain == "date":
            parsed_date = date.fromisoformat(value)
            return parsed_date if parsed_date.isoformat() == value else None
        if grain == "datetime":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
            return parsed.astimezone(timezone.utc)
    except ValueError:
        return None
    return None


def _beyond_cutoff(clock: Mapping[str, Any], cutoff: Mapping[str, Any]) -> bool | None:
    """True beyond, False within, None when cross-grain ordering is ambiguous."""
    value = _parse_clock(clock.get("value"), clock.get("grain"))
    ceiling = _parse_clock(cutoff.get("value"), cutoff.get("grain"))
    if value is None or ceiling is None:
        return None
    if isinstance(value, datetime) and isinstance(ceiling, datetime):
        return value > ceiling
    if isinstance(value, date) and not isinstance(value, datetime):
        if isinstance(ceiling, date) and not isinstance(ceiling, datetime):
            return value > ceiling
        if isinstance(ceiling, datetime):
            if value == ceiling.date():
                return None
            return value > ceiling.date()
    if isinstance(value, datetime) and isinstance(ceiling, date):
        return value.date() > ceiling
    return None


def semantic_violations(
    reference: Mapping[str, Any],
    *,
    vocabulary: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Return stable violation codes for semantics JSON Schema cannot express."""
    vocab = dict(vocabulary) if vocabulary is not None else load_vocabulary()
    violations: list[str] = []

    if reference.get("schema") != SCHEMA:
        violations.append("schema_mismatch")
    if reference.get("version") != VERSION:
        violations.append("version_mismatch")
    try:
        expected_reference_id = compute_reference_id(reference)
    except (TypeError, ValueError):
        expected_reference_id = None
        violations.append("reference_identity_not_canonical_json")
    if reference.get("reference_id") != expected_reference_id:
        violations.append("reference_id_mismatch")

    owner_stores = vocab.get("owner_stores")
    owner_store = reference.get("owner_store")
    owner = owner_stores.get(owner_store) if isinstance(owner_stores, Mapping) else None
    if not isinstance(owner, Mapping):
        violations.append("owner_store_unknown")
        owner = {}

    native_identity = reference.get("native_identity")
    expected_identity_fields = owner.get("native_identity_fields")
    if isinstance(native_identity, Mapping) and isinstance(expected_identity_fields, list):
        if set(native_identity) != set(expected_identity_fields):
            violations.append("native_identity_fields_mismatch")
    else:
        violations.append("native_identity_invalid")

    if reference.get("object_class") not in set(owner.get("object_classes") or []):
        violations.append("object_class_not_owned")

    allowed_subjects = set(owner.get("subject_key_types") or [])
    subjects = [reference.get("subject")]
    secondary = reference.get("secondary_subjects")
    if isinstance(secondary, list):
        subjects.extend(secondary)
    for index, subject in enumerate(subjects):
        if not isinstance(subject, Mapping):
            violations.append(f"subject_{index}_invalid")
        elif subject.get("key_type") not in allowed_subjects:
            violations.append(f"subject_{index}_not_owned")

    provenance = reference.get("provenance")
    if not isinstance(provenance, Mapping):
        violations.append("provenance_invalid")
    else:
        if provenance.get("pointer_only") is not True or provenance.get("body_embedded") is not False:
            violations.append("provenance_not_pointer_only")
        if provenance.get("owner_reader") != owner.get("reader"):
            violations.append("owner_reader_mismatch")

    bindings = owner.get("clock_bindings") if isinstance(owner, Mapping) else {}
    bindings = bindings if isinstance(bindings, Mapping) else {}
    clock_fields: dict[str, Mapping[str, Any]] = {}
    clocks = reference.get("clocks")
    if not isinstance(clocks, list):
        violations.append("clocks_invalid")
        clocks = []
    for index, clock in enumerate(clocks):
        if not isinstance(clock, Mapping):
            violations.append(f"clock_{index}_invalid")
            continue
        field = clock.get("field")
        if not isinstance(field, str):
            violations.append(f"clock_{index}_field_invalid")
            continue
        if field in clock_fields:
            violations.append(f"clock_field_duplicate:{field}")
        clock_fields[field] = clock
        if bindings.get(field) != clock.get("class"):
            violations.append(f"clock_binding_mismatch:{field}")
        if clock.get("value_state") == "known" and _parse_clock(
            clock.get("value"), clock.get("grain")
        ) is None:
            violations.append(f"clock_value_invalid:{field}")
        if clock.get("value_state") == "unknown" and clock.get("value") is not None:
            violations.append(f"clock_unknown_has_value:{field}")

    correction = reference.get("correction")
    if not isinstance(correction, Mapping):
        violations.append("correction_invalid")
    else:
        kind = correction.get("kind")
        predecessors = correction.get("predecessor_reference_ids")
        predecessors = predecessors if isinstance(predecessors, list) else []
        clock_field = correction.get("clock_field")
        if correction.get("append_only") is not True or correction.get("mutates_predecessor") is not False:
            violations.append("correction_not_append_only")
        if kind == "none":
            if predecessors or clock_field is not None:
                violations.append("correction_none_has_lineage")
        elif kind in CORRECTION_KINDS:
            if not predecessors:
                violations.append("correction_missing_predecessor")
            if clock_field not in clock_fields:
                violations.append("correction_clock_unbound")
        else:
            violations.append("correction_kind_unknown")

    relations = reference.get("relations")
    if not isinstance(relations, list):
        violations.append("relations_invalid")
        relations = []
    for index, relation in enumerate(relations):
        if not isinstance(relation, Mapping):
            violations.append(f"relation_{index}_invalid")
            continue
        relation_type = relation.get("type")
        automatic = relation.get("automatic_effect") is True
        deterministic_key = relation.get("deterministic_key")
        if automatic and relation_type not in AUTOMATIC_RELATIONS:
            violations.append(f"relation_{index}_automatic_forbidden")
        if relation_type in NON_AUTOMATIC_RELATIONS and automatic:
            violations.append(f"relation_{index}_non_deterministic_effect")
        if automatic and not isinstance(deterministic_key, str):
            violations.append(f"relation_{index}_automatic_without_key")
        if relation_type in AUTOMATIC_RELATIONS and automatic is False and deterministic_key is not None:
            violations.append(f"relation_{index}_inactive_key_must_be_null")
        independence = relation.get("independence")
        if relation_type == "shares_upstream" and isinstance(independence, Mapping):
            source_axis = independence.get("source_independence")
            if isinstance(source_axis, Mapping) and source_axis.get("state") == "independent":
                violations.append(f"relation_{index}_false_source_independence")

    missingness = reference.get("missingness")
    if not isinstance(missingness, Mapping):
        violations.append("missingness_invalid")
    else:
        if missingness.get("zero_substituted") is not False:
            violations.append("missingness_zero_substitution")
        if missingness.get("state") == "present" and missingness.get("reason") is not None:
            violations.append("present_has_missing_reason")
        if missingness.get("state") == "absent" and missingness.get("reason") is None:
            violations.append("absent_missing_reason")

    replay = reference.get("replay")
    if not isinstance(replay, Mapping):
        violations.append("replay_invalid")
    else:
        mode = replay.get("mode")
        if mode == "historical_replay":
            if not replay.get("code_revision") or not replay.get("input_digest"):
                violations.append("historical_replay_missing_reproducibility")
            if replay.get("vintage_state") == "current_rule_recomputation":
                violations.append("recomputation_mislabeled_replay")
        if mode == "current_rule_recomputation" and replay.get("vintage_state") != mode:
            violations.append("recomputation_vintage_state_mismatch")
        if mode in {"historical_replay", "retrospective_research"}:
            cutoffs = replay.get("cutoffs")
            cutoffs = cutoffs if isinstance(cutoffs, Mapping) else {}
            for field, clock in clock_fields.items():
                if clock.get("value_state") != "known":
                    continue
                clock_class = clock.get("class")
                cutoff = cutoffs.get(clock_class)
                if not isinstance(cutoff, Mapping) or cutoff.get("state") != "known":
                    violations.append(f"replay_cutoff_missing:{clock_class}")
                    continue
                beyond = _beyond_cutoff(clock, cutoff)
                if beyond is True:
                    violations.append(f"replay_lookahead:{field}")
                elif beyond is None:
                    violations.append(f"replay_grain_ambiguous:{field}")

    authority = reference.get("authority")
    if authority is None:
        # Default-on-absence is all false, but the v1 wire requires materialization.
        authority = ALL_FALSE_AUTHORITY
        violations.append("authority_not_materialized")
    if authority != ALL_FALSE_AUTHORITY:
        violations.append("authority_leak")

    return tuple(dict.fromkeys(violations))


def assert_semantically_valid(
    reference: Mapping[str, Any],
    *,
    vocabulary: Mapping[str, Any] | None = None,
) -> None:
    """Raise one stable error containing every semantic violation."""
    violations = semantic_violations(reference, vocabulary=vocabulary)
    if violations:
        raise EvidenceFoundationError(";".join(violations))


__all__ = [
    "ALL_FALSE_AUTHORITY",
    "EvidenceFoundationError",
    "SCHEMA",
    "VERSION",
    "VOCABULARY_PATH",
    "assert_semantically_valid",
    "canonical_json_bytes",
    "compute_reference_id",
    "load_vocabulary",
    "reference_identity_payload",
    "semantic_violations",
]
