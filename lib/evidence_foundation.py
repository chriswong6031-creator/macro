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
import re
from string import Formatter
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError


SCHEMA = "evidence_foundation.reference.v1"
VERSION = "1.0.0"
VOCABULARY_SCHEMA = "evidence_foundation.vocabulary.v1"
VOCABULARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "evidence_foundation"
    / "vocabulary.v1.json"
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "evidence_foundation"
    / "reference.v1.schema.json"
)

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
READER_KINDS = frozenset({"direct", "collection", "materializer", "parser"})
COVERAGE_CLASSES = frozenset({
    "unknown",
    "current_only",
    "record_history_complete",
    "source_release_snapshot_only",
    "append_only_bitemporal",
    "immutable_generation",
    "prospective_only",
    "reconstruction",
    "partial",
})
REPLAY_MODES = frozenset({
    "live",
    "historical_replay",
    "retrospective_research",
    "current_rule_recomputation",
})
VINTAGE_STATES = frozenset({
    "owner_native",
    "reconstructed_not_operational_pit",
    "current_rule_recomputation",
    "unavailable",
})
CORRECTION_RELATION_KIND = {
    "amendment": "corrects",
    "restatement": "corrects",
    "source_correction": "corrects",
    "withdrawal": "corrects",
    "superseding_generation": "supersedes",
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


def _validate_grammar(grammar: object, expected_type: object, label: str) -> None:
    """Fail closed on the small, declarative value-grammar vocabulary."""
    if not isinstance(grammar, dict) or not isinstance(grammar.get("kind"), str):
        raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
    kind = grammar["kind"]
    if kind == "regex":
        if set(grammar) != {"kind", "pattern"} or expected_type != "string":
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        pattern = grammar.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise EvidenceFoundationError(
                f"vocabulary_value_grammar_invalid:{label}"
            ) from exc
        return
    if kind == "date":
        if set(grammar) != {"kind"} or expected_type != "string":
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        return
    if kind == "bounded_text":
        if (
            set(grammar) != {"kind", "minimum_length", "maximum_length"}
            or expected_type != "string"
        ):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        minimum = grammar.get("minimum_length")
        maximum = grammar.get("maximum_length")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or minimum < 1
            or minimum > maximum
        ):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        return
    if kind == "integer_range":
        if (
            set(grammar) not in (
                {"kind", "minimum"},
                {"kind", "minimum", "maximum"},
            )
            or expected_type != "integer"
        ):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        minimum = grammar.get("minimum")
        maximum = grammar.get("maximum")
        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or (
                maximum is not None
                and (
                    isinstance(maximum, bool)
                    or not isinstance(maximum, int)
                    or minimum > maximum
                )
            )
        ):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        return
    if kind == "enum":
        if set(grammar) != {"kind", "values"}:
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        values = grammar.get("values")
        if not isinstance(values, list) or not values or len(values) != len(set(values)):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        if expected_type == "string" and any(not isinstance(value, str) for value in values):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        if expected_type == "integer" and any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        if expected_type not in {"string", "integer"}:
            raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")
        return
    raise EvidenceFoundationError(f"vocabulary_value_grammar_invalid:{label}")


def _matches_grammar(value: object, grammar: object) -> bool:
    if not isinstance(grammar, Mapping):
        return False
    kind = grammar.get("kind")
    if kind == "regex":
        return isinstance(value, str) and re.fullmatch(str(grammar.get("pattern")), value) is not None
    if kind == "date":
        return isinstance(value, str) and _parse_clock(value, "date") is not None
    if kind == "bounded_text":
        return (
            isinstance(value, str)
            and int(grammar.get("minimum_length", -1)) <= len(value)
            <= int(grammar.get("maximum_length", -1))
        )
    if kind == "integer_range":
        maximum = grammar.get("maximum")
        return (
            not isinstance(value, bool)
            and isinstance(value, int)
            and int(grammar.get("minimum", 1)) <= value
            and (maximum is None or value <= int(maximum))
        )
    if kind == "enum":
        return value in list(grammar.get("values") or ())
    return False


def load_vocabulary(path: str | Path | None = None) -> dict[str, Any]:
    """Load and fail-closed validate the frozen owner vocabulary."""
    target = Path(path) if path is not None else VOCABULARY_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceFoundationError(f"vocabulary_unreadable:{target}") from exc
    if not isinstance(payload, dict):
        raise EvidenceFoundationError("vocabulary_not_object")
    if payload.get("schema") != VOCABULARY_SCHEMA or payload.get("version") != VERSION:
        raise EvidenceFoundationError("vocabulary_schema_or_version_mismatch")
    for field in ("object_classes", "clock_classes", "subject_key_types"):
        values = payload.get(field)
        if (
            not isinstance(values, list)
            or not values
            or len(values) != len(set(values))
            or any(not isinstance(value, str) or not value for value in values)
        ):
            raise EvidenceFoundationError(f"vocabulary_{field}_invalid")
    subject_key_grammars = payload.get("subject_key_grammars")
    if (
        not isinstance(subject_key_grammars, dict)
        or set(subject_key_grammars) != set(payload["subject_key_types"])
    ):
        raise EvidenceFoundationError("vocabulary_subject_key_grammars_invalid")
    for key_type, grammar in subject_key_grammars.items():
        _validate_grammar(grammar, "string", f"subject:{key_type}")
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
        identity_fields = owner["native_identity_fields"]
        if (
            len(set(identity_fields)) != len(identity_fields)
            or any(not isinstance(field, str) or not field for field in identity_fields)
        ):
            raise EvidenceFoundationError(f"vocabulary_owner_identity_invalid:{name}")
        identity_types = owner.get("native_identity_types")
        if (
            not isinstance(identity_types, dict)
            or set(identity_types) != set(identity_fields)
            or any(value not in {"string", "integer"} for value in identity_types.values())
        ):
            raise EvidenceFoundationError(f"vocabulary_owner_identity_types_invalid:{name}")
        identity_grammars = owner.get("native_identity_grammars")
        if not isinstance(identity_grammars, dict) or set(identity_grammars) != set(
            identity_fields
        ):
            raise EvidenceFoundationError(
                f"vocabulary_owner_identity_grammars_invalid:{name}"
            )
        for field in identity_fields:
            _validate_grammar(
                identity_grammars[field],
                identity_types[field],
                f"owner:{name}:{field}",
            )
        native_schemas = owner.get("native_schemas")
        if (
            not isinstance(native_schemas, list)
            or not native_schemas
            or len(set(native_schemas)) != len(native_schemas)
            or any(not isinstance(value, str) or not value for value in native_schemas)
        ):
            raise EvidenceFoundationError(f"vocabulary_owner_native_schemas_invalid:{name}")
        if (
            not isinstance(owner.get("object_classes"), list)
            or not owner["object_classes"]
            or len(owner["object_classes"]) != len(set(owner["object_classes"]))
            or not set(owner["object_classes"]).issubset(payload["object_classes"])
        ):
            raise EvidenceFoundationError(f"vocabulary_owner_classes_missing:{name}")
        if (
            not isinstance(owner.get("subject_key_types"), list)
            or not owner["subject_key_types"]
            or len(owner["subject_key_types"]) != len(set(owner["subject_key_types"]))
            or not set(owner["subject_key_types"]).issubset(payload["subject_key_types"])
        ):
            raise EvidenceFoundationError(f"vocabulary_owner_subjects_missing:{name}")
        coverage_classes = owner.get("coverage_classes")
        if (
            not isinstance(coverage_classes, list)
            or len(coverage_classes) != 1
            or coverage_classes[0] not in COVERAGE_CLASSES
        ):
            raise EvidenceFoundationError(
                f"vocabulary_owner_coverage_classes_invalid:{name}"
            )
        replay_capabilities = owner.get("replay_capabilities")
        if (
            not isinstance(replay_capabilities, dict)
            or "live" not in replay_capabilities
            or not replay_capabilities
            or not set(replay_capabilities).issubset(REPLAY_MODES)
        ):
            raise EvidenceFoundationError(
                f"vocabulary_owner_replay_capabilities_invalid:{name}"
            )
        for mode, vintage_states in replay_capabilities.items():
            if (
                not isinstance(vintage_states, list)
                or not vintage_states
                or len(vintage_states) != len(set(vintage_states))
                or not set(vintage_states).issubset(VINTAGE_STATES)
            ):
                raise EvidenceFoundationError(
                    f"vocabulary_owner_replay_capability_invalid:{name}:{mode}"
                )
        bindings = owner.get("clock_bindings")
        if not isinstance(bindings, dict) or not bindings:
            raise EvidenceFoundationError(f"vocabulary_owner_clocks_missing:{name}")
        for field, binding in bindings.items():
            if (
                not isinstance(field, str)
                or not isinstance(binding, dict)
                or set(binding) != {"class", "grains"}
                or binding.get("class") not in payload.get("clock_classes", ())
                or not isinstance(binding.get("grains"), list)
                or not binding["grains"]
                or len(set(binding["grains"])) != len(binding["grains"])
                or any(grain not in {"date", "datetime"} for grain in binding["grains"])
            ):
                raise EvidenceFoundationError(
                    f"vocabulary_owner_clock_binding_invalid:{name}:{field}"
                )
        if "synapse_asof_field" not in owner:
            raise EvidenceFoundationError(f"vocabulary_synapse_asof_unspecified:{name}")
        synapse_asof = owner["synapse_asof_field"]
        if synapse_asof is not None and (
            not isinstance(synapse_asof, str) or synapse_asof not in bindings
        ):
            raise EvidenceFoundationError(f"vocabulary_synapse_asof_unbound:{name}")
        if not isinstance(owner.get("reader"), str) or not owner["reader"]:
            raise EvidenceFoundationError(f"vocabulary_owner_reader_missing:{name}")
        if owner.get("reader_kind") not in READER_KINDS:
            raise EvidenceFoundationError(f"vocabulary_owner_reader_kind_invalid:{name}")
        template = owner.get("pointer_template")
        if not isinstance(template, str) or not template:
            raise EvidenceFoundationError(f"vocabulary_owner_pointer_template_missing:{name}")
        try:
            placeholders = [
                field_name
                for _, field_name, _, _ in Formatter().parse(template)
                if field_name is not None
            ]
        except ValueError as exc:
            raise EvidenceFoundationError(
                f"vocabulary_owner_pointer_template_invalid:{name}"
            ) from exc
        if len(placeholders) != len(set(placeholders)) or set(placeholders) != set(
            identity_fields
        ):
            raise EvidenceFoundationError(
                f"vocabulary_owner_pointer_identity_mismatch:{name}"
            )
    return payload


def render_owner_pointer(owner: Mapping[str, Any], identity: Mapping[str, Any]) -> str:
    """Render the one canonical pointer for an exact owner-native identity."""
    template = owner.get("pointer_template")
    fields = owner.get("native_identity_fields")
    identity_types = owner.get("native_identity_types")
    identity_grammars = owner.get("native_identity_grammars")
    if (
        not isinstance(template, str)
        or not isinstance(fields, list)
        or not isinstance(identity_types, Mapping)
        or not isinstance(identity_grammars, Mapping)
        or set(identity_types) != set(fields)
        or set(identity_grammars) != set(fields)
    ):
        raise EvidenceFoundationError("owner_pointer_contract_invalid")
    if set(identity) != set(fields):
        raise EvidenceFoundationError("owner_pointer_identity_fields_mismatch")
    for field in fields:
        value = identity[field]
        expected_type = identity_types[field]
        type_valid = (
            expected_type == "string"
            and isinstance(value, str)
            or expected_type == "integer"
            and not isinstance(value, bool)
            and isinstance(value, int)
        )
        if not type_valid or not _matches_grammar(value, identity_grammars[field]):
            raise EvidenceFoundationError("owner_pointer_identity_value_invalid")
    try:
        pointer = template.format(**identity)
    except (KeyError, ValueError) as exc:
        raise EvidenceFoundationError("owner_pointer_render_failed") from exc
    if not pointer or pointer != pointer.strip():
        raise EvidenceFoundationError("owner_pointer_render_invalid")
    return pointer


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
        if value.date() == ceiling:
            return None
        return value.date() > ceiling
    return None


def semantic_violations(reference: Mapping[str, Any]) -> tuple[str, ...]:
    """Return stable violation codes for semantics JSON Schema cannot express."""
    # This public boundary always uses the validated, repository-frozen vocabulary.
    # Caller-supplied owner schemas/readers must never become validation authority.
    vocab = load_vocabulary()
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
        expected_identity_types = owner.get("native_identity_types")
        expected_identity_grammars = owner.get("native_identity_grammars")
        if isinstance(expected_identity_types, Mapping):
            for field, expected_type in expected_identity_types.items():
                value = native_identity.get(field)
                type_valid = False
                if expected_type == "string" and not isinstance(value, str):
                    violations.append(f"native_identity_type_mismatch:{field}")
                elif expected_type == "string":
                    type_valid = True
                if expected_type == "integer" and (
                    isinstance(value, bool) or not isinstance(value, int)
                ):
                    violations.append(f"native_identity_type_mismatch:{field}")
                elif expected_type == "integer":
                    type_valid = True
                grammar = (
                    expected_identity_grammars.get(field)
                    if isinstance(expected_identity_grammars, Mapping)
                    else None
                )
                if type_valid and not _matches_grammar(value, grammar):
                    violations.append(f"native_identity_value_invalid:{field}")
        if owner_store == "txi.episode_transition":
            chain = native_identity.get("chain")
            rev = native_identity.get("rev")
            episode_id = native_identity.get("episode_id")
            if (
                isinstance(chain, str)
                and not isinstance(rev, bool)
                and isinstance(rev, int)
                and isinstance(episode_id, str)
                and not episode_id.startswith(f"{chain}@r{rev}:")
            ):
                violations.append("native_identity_composite_mismatch:episode_id")
    else:
        violations.append("native_identity_invalid")

    if reference.get("native_schema") not in set(owner.get("native_schemas") or []):
        violations.append("native_schema_not_owned")

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
        else:
            key_type = subject.get("key_type")
            subject_grammars = vocab.get("subject_key_grammars")
            grammar = (
                subject_grammars.get(key_type)
                if isinstance(subject_grammars, Mapping)
                else None
            )
            if not _matches_grammar(subject.get("key"), grammar):
                violations.append(f"subject_{index}_key_invalid:{key_type}")

    if reference.get("coverage_class") not in set(owner.get("coverage_classes") or []):
        violations.append("coverage_class_not_owned")

    provenance = reference.get("provenance")
    if not isinstance(provenance, Mapping):
        violations.append("provenance_invalid")
    else:
        if provenance.get("pointer_only") is not True or provenance.get("body_embedded") is not False:
            violations.append("provenance_not_pointer_only")
        if provenance.get("owner_reader") != owner.get("reader"):
            violations.append("owner_reader_mismatch")
        if provenance.get("owner_reader_kind") != owner.get("reader_kind"):
            violations.append("owner_reader_kind_mismatch")
        if isinstance(native_identity, Mapping):
            try:
                expected_pointer = render_owner_pointer(owner, native_identity)
            except EvidenceFoundationError:
                expected_pointer = None
                violations.append("owner_pointer_identity_invalid")
            if provenance.get("pointer") != expected_pointer:
                violations.append("owner_pointer_mismatch")

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
        binding = bindings.get(field)
        if not isinstance(binding, Mapping):
            violations.append(f"clock_field_unknown:{field}")
            binding = {}
        if binding.get("class") != clock.get("class"):
            violations.append(f"clock_binding_mismatch:{field}")
        if clock.get("grain") not in set(binding.get("grains") or []):
            violations.append(f"clock_grain_mismatch:{field}")
        if clock.get("value_state") == "known" and _parse_clock(
            clock.get("value"), clock.get("grain")
        ) is None:
            violations.append(f"clock_value_invalid:{field}")
        if clock.get("value_state") == "unknown" and clock.get("value") is not None:
            violations.append(f"clock_unknown_has_value:{field}")
    for field in sorted(set(bindings) - set(clock_fields)):
        violations.append(f"clock_field_missing:{field}")

    correction = reference.get("correction")
    if not isinstance(correction, Mapping):
        violations.append("correction_invalid")
    else:
        kind = correction.get("kind")
        predecessors = correction.get("predecessor_reference_ids")
        predecessors = predecessors if isinstance(predecessors, list) else []
        clock_field = correction.get("clock_field")
        chronology_state = correction.get("chronology_state")
        if correction.get("append_only") is not True or correction.get("mutates_predecessor") is not False:
            violations.append("correction_not_append_only")
        if kind == "none":
            if predecessors or clock_field is not None or chronology_state != "not_applicable":
                violations.append("correction_none_has_lineage")
        elif kind in CORRECTION_KINDS:
            if not predecessors:
                violations.append("correction_missing_predecessor")
            if clock_field not in clock_fields:
                violations.append("correction_clock_unbound")
            if chronology_state not in {
                "owner_clock_order_verified",
                "owner_clock_order_not_verified",
            }:
                violations.append("correction_chronology_unstated")
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
        automatic_effect = relation.get("automatic_effect")
        deterministic_key = relation.get("deterministic_key")
        # V1 has no frozen owner-native deterministic-lineage type.  Consequently
        # even an apparently exact duplicate is declarative context only: an
        # arbitrary caller-authored key must never acquire automatic effect.
        if automatic_effect is not False:
            violations.append(f"relation_{index}_automatic_effect_forbidden_v1")
        if deterministic_key is not None:
            violations.append(f"relation_{index}_deterministic_key_forbidden_v1")
        independence = relation.get("independence")
        if isinstance(independence, Mapping):
            for axis_name in (
                "source_independence",
                "information_novelty",
                "mechanism_independence",
            ):
                axis = independence.get(axis_name)
                if not isinstance(axis, Mapping) or axis.get("assessment") != "declarative_unverified":
                    violations.append(
                        f"relation_{index}_independence_not_declarative:{axis_name}"
                    )

    if isinstance(correction, Mapping):
        kind = correction.get("kind")
        predecessors = correction.get("predecessor_reference_ids")
        predecessor_values = predecessors if isinstance(predecessors, list) else []
        predecessor_set = {
            value for value in predecessor_values if isinstance(value, str)
        }
        expected_relation_kind = CORRECTION_RELATION_KIND.get(kind)
        correction_relations = [
            relation
            for relation in relations
            if isinstance(relation, Mapping)
            and relation.get("type") in {"corrects", "supersedes"}
        ]
        if expected_relation_kind is None:
            if correction_relations:
                violations.append("correction_none_has_relation")
        else:
            target_values = [
                relation.get("target_reference_id") for relation in correction_relations
            ]
            target_set = {value for value in target_values if isinstance(value, str)}
            if any(
                relation.get("type") != expected_relation_kind
                for relation in correction_relations
            ):
                violations.append("correction_relation_wrong_kind")
            if len(target_values) != len(target_set):
                violations.append("correction_relation_duplicate_target")
            if predecessor_set - target_set:
                violations.append("correction_relation_missing_target")
            if target_set - predecessor_set:
                violations.append("correction_relation_extra_target")

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
        vintage_state = replay.get("vintage_state")
        replay_capabilities = owner.get("replay_capabilities")
        replay_capabilities = (
            replay_capabilities if isinstance(replay_capabilities, Mapping) else {}
        )
        if mode not in replay_capabilities:
            violations.append("replay_mode_not_owned")
        elif vintage_state not in set(replay_capabilities.get(mode) or []):
            violations.append(f"replay_vintage_not_owned:{mode}")
        cutoffs = replay.get("cutoffs")
        cutoffs = cutoffs if isinstance(cutoffs, Mapping) else {}
        for clock_class in vocab.get("clock_classes") or ():
            cutoff = cutoffs.get(clock_class)
            if not isinstance(cutoff, Mapping):
                violations.append(f"replay_cutoff_missing:{clock_class}")
                continue
            if cutoff.get("state") == "known" and _parse_clock(
                cutoff.get("value"), cutoff.get("grain")
            ) is None:
                violations.append(f"replay_cutoff_invalid:{clock_class}")
            if cutoff.get("state") == "unknown" and cutoff.get("value") is not None:
                violations.append(f"replay_cutoff_unknown_has_value:{clock_class}")
        if mode == "historical_replay":
            if not replay.get("code_revision") or not replay.get("input_digest"):
                violations.append("historical_replay_missing_reproducibility")
            if replay.get("vintage_state") == "unavailable":
                violations.append("historical_replay_vintage_unavailable")
            if replay.get("vintage_state") == "current_rule_recomputation":
                violations.append("recomputation_mislabeled_replay")
            if owner_store == "fif.raw_occurrence":
                for required_field in ("clocks.accepted_at", "clocks.recorded_at"):
                    required_clock = clock_fields.get(required_field)
                    if (
                        not isinstance(required_clock, Mapping)
                        or required_clock.get("value_state") != "known"
                    ):
                        violations.append(
                            f"historical_replay_fif_clock_unknown:{required_field}"
                        )
        if mode == "current_rule_recomputation" and replay.get("vintage_state") != mode:
            violations.append("recomputation_vintage_state_mismatch")
        if mode in {"historical_replay", "retrospective_research"}:
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


def _schema_violations(reference: Mapping[str, Any]) -> tuple[str, ...]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        SchemaError,
        TypeError,
        ValueError,
    ) as exc:
        raise EvidenceFoundationError("reference_schema_unreadable") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    codes: list[str] = []
    for error in sorted(
        validator.iter_errors(reference),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        codes.append(f"json_schema:{path}:{error.validator}")
    return tuple(dict.fromkeys(codes))


def combined_violations(reference: Mapping[str, Any]) -> tuple[str, ...]:
    """Return JSON-Schema and semantic violations through one fail-closed API."""
    if not isinstance(reference, Mapping):
        return ("reference_not_mapping",)
    return tuple(
        dict.fromkeys(
            (*_schema_violations(reference), *semantic_violations(reference))
        )
    )


def validate_reference(reference: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the entire v1 contract and return a defensive JSON copy."""
    violations = combined_violations(reference)
    if violations:
        raise EvidenceFoundationError(";".join(violations))
    try:
        return json.loads(json.dumps(reference, allow_nan=False))
    except (TypeError, ValueError) as exc:  # defensive; canonical identity already checks this
        raise EvidenceFoundationError("reference_not_canonical_json") from exc


def assert_semantically_valid(reference: Mapping[str, Any]) -> None:
    """Backward-compatible alias for the combined fail-closed validator."""
    violations = combined_violations(reference)
    if violations:
        raise EvidenceFoundationError(";".join(violations))


__all__ = [
    "ALL_FALSE_AUTHORITY",
    "EvidenceFoundationError",
    "SCHEMA",
    "VERSION",
    "VOCABULARY_PATH",
    "SCHEMA_PATH",
    "assert_semantically_valid",
    "canonical_json_bytes",
    "combined_violations",
    "compute_reference_id",
    "load_vocabulary",
    "reference_identity_payload",
    "render_owner_pointer",
    "semantic_violations",
    "validate_reference",
]
