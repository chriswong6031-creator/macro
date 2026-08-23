"""Semantic validators for the contract-only Evidence Foundation surface.

This module creates no store and performs no owner read.  It validates
``EvidenceRef``, ``EvidenceBlock``, and ``EvidenceRecipe`` values and can compile
an in-memory recipe receipt from caller-supplied owner-reader results.  The
owner-native reader remains the only path to the referenced truth.
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
BLOCK_SCHEMA = "evidence_foundation.block.v1"
RECIPE_SCHEMA = "evidence_foundation.recipe.v1"
COMPILATION_RECEIPT_SCHEMA = "evidence_foundation.recipe_compilation_receipt.v1"
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
BLOCK_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "evidence_foundation"
    / "block.v1.schema.json"
)
RECIPE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "evidence_foundation"
    / "recipe.v1.schema.json"
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
_AUTHORITY_CLASS_BY_OBJECT_CLASS = {
    "world_observation": frozenset({"fact"}),
    "derived_view": frozenset({"deterministic", "model", "human"}),
    "system_belief": frozenset({"deterministic", "model"}),
    "forward_claim": frozenset({"model", "human"}),
    "instrument_state": frozenset({"deterministic"}),
}
_REQUIRED_RECIPE_RULES = frozenset({
    "REQUIRED_BLOCK_ABSENT",
    "OPTIONAL_BLOCK_ABSENT",
    "IDENTITY_UNRESOLVED",
    "RIGHTS_BLOCKED",
    "CONFLICTED_REQUIRED_BLOCK",
})
_DETERMINISTIC_DEPENDENCE_KINDS = frozenset({
    "exact_duplicate",
    "same_fact",
    "same_event",
})


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


def _content_identity(value: Mapping[str, Any], *, field: str, prefix: str) -> str:
    payload = {str(key): item for key, item in value.items() if key != field}
    return f"{prefix}{sha256(canonical_json_bytes(payload)).hexdigest()}"


def compute_block_id(block: Mapping[str, Any]) -> str:
    """Return the deterministic identity of one bounded consumer projection."""
    return _content_identity(block, field="evidence_block_id", prefix="ebl_")


def compute_recipe_id(recipe: Mapping[str, Any]) -> str:
    """Return the deterministic identity of one versioned composition recipe."""
    return _content_identity(recipe, field="recipe_id", prefix="erp_")


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
    allowed_authority_classes = _AUTHORITY_CLASS_BY_OBJECT_CLASS.get(
        reference.get("object_class"), frozenset()
    )
    if reference.get("authority_class") not in allowed_authority_classes:
        violations.append("authority_class_masquerade")

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

    freshness = reference.get("freshness")
    if not isinstance(freshness, Mapping):
        violations.append("freshness_invalid")
    else:
        state = freshness.get("state")
        field = freshness.get("clock_field")
        if state == "native_clock_bound" and field not in clock_fields:
            violations.append("freshness_clock_unbound")
        if state != "native_clock_bound" and field is not None:
            violations.append("freshness_nonbound_has_clock")
        if state == "not_applicable" and freshness.get("policy_id") is not None:
            violations.append("freshness_not_applicable_has_policy")

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

    rights = reference.get("rights")
    if not isinstance(rights, Mapping):
        violations.append("rights_invalid")
    else:
        rights_blocked = rights.get("state") == "rights_blocked"
        missingness_rights = (
            isinstance(missingness, Mapping)
            and missingness.get("state") == "absent"
            and missingness.get("reason") == "rights_blocked"
        )
        if rights_blocked != missingness_rights:
            violations.append("rights_missingness_mismatch")

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


def _contract_schema_violations(
    value: Mapping[str, Any], *, path: Path, label: str
) -> tuple[str, ...]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        SchemaError,
        TypeError,
        ValueError,
    ) as exc:
        raise EvidenceFoundationError(f"{label}_schema_unreadable") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    codes: list[str] = []
    for error in sorted(
        validator.iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        codes.append(f"json_schema:{path}:{error.validator}")
    return tuple(dict.fromkeys(codes))


def _schema_violations(reference: Mapping[str, Any]) -> tuple[str, ...]:
    return _contract_schema_violations(
        reference, path=SCHEMA_PATH, label="reference"
    )


def block_semantic_violations(
    block: Mapping[str, Any],
    *,
    references: Mapping[str, Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return stable cross-reference violations for one ``EvidenceBlock``."""
    violations: list[str] = []
    if block.get("schema") != BLOCK_SCHEMA:
        violations.append("block_schema_mismatch")
    if block.get("version") != VERSION:
        violations.append("block_version_mismatch")
    try:
        expected_id = compute_block_id(block)
    except (TypeError, ValueError):
        expected_id = None
        violations.append("block_identity_not_canonical_json")
    if block.get("evidence_block_id") != expected_id:
        violations.append("block_id_mismatch")

    reference_ids = block.get("reference_ids")
    reference_ids = reference_ids if isinstance(reference_ids, list) else []
    resolved: list[Mapping[str, Any]] = []
    for reference_id in reference_ids:
        reference = references.get(reference_id)
        if not isinstance(reference, Mapping):
            violations.append(f"block_reference_missing:{reference_id}")
            continue
        if combined_violations(reference):
            violations.append(f"block_reference_invalid:{reference_id}")
        resolved.append(reference)

    expected_owners = {str(reference.get("owner_store")) for reference in resolved}
    expected_classes = {str(reference.get("object_class")) for reference in resolved}
    if set(block.get("owner_stores") or ()) != expected_owners:
        violations.append("block_owner_stores_mismatch")
    if set(block.get("object_classes") or ()) != expected_classes:
        violations.append("block_object_classes_mismatch")

    evidence_class = block.get("evidence_class")
    reference_authority_classes = {
        reference.get("authority_class") for reference in resolved
    }
    allowed_by_block = {
        "fact": frozenset({"fact"}),
        "deterministic": frozenset({"fact", "deterministic"}),
        "model": frozenset({"fact", "deterministic", "model"}),
        "human": frozenset({"fact", "deterministic", "human"}),
    }
    if not reference_authority_classes <= allowed_by_block.get(evidence_class, frozenset()):
        violations.append("block_evidence_class_masquerade")
    if evidence_class in {"deterministic", "model", "human"} and resolved:
        if evidence_class not in reference_authority_classes:
            violations.append("block_evidence_class_without_authoritative_leg")

    expected_clocks: list[str] = []
    for reference in resolved:
        reference_id = reference.get("reference_id")
        for clock in reference.get("clocks") or ():
            if isinstance(clock, Mapping):
                expected_clocks.append(
                    json.dumps(
                        {"reference_id": reference_id, **dict(clock)},
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                )
    summary = block.get("clock_summary")
    actual_clocks: list[str] = []
    if not isinstance(summary, Mapping) or summary.get("collapsed") is not False:
        violations.append("block_clock_summary_collapsed_or_missing")
    else:
        for entry in summary.get("entries") or ():
            if isinstance(entry, Mapping):
                actual_clocks.append(
                    json.dumps(dict(entry), sort_keys=True, separators=(",", ":"), allow_nan=False)
                )
    if sorted(actual_clocks) != sorted(expected_clocks):
        violations.append("block_clock_summary_not_lossless")

    coverage = block.get("coverage")
    if not isinstance(coverage, Mapping):
        violations.append("block_coverage_invalid")
    else:
        total = coverage.get("total")
        included = coverage.get("included")
        excluded = coverage.get("excluded")
        if total != len(reference_ids):
            violations.append("block_denominator_total_mismatch")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (total, included, excluded)):
            violations.append("block_denominator_invalid")
        elif included + excluded != total:
            violations.append("block_denominator_not_reconciled")
        adverse_counts = [
            coverage.get(name)
            for name in ("missing", "stale", "rights_blocked", "fallback")
        ]
        if coverage.get("state") == "complete" and (
            excluded != 0 or any(value != 0 for value in adverse_counts)
        ):
            violations.append("block_complete_with_degradation")
        rights_count = sum(
            1 for reference in resolved if reference.get("rights", {}).get("state") == "rights_blocked"
        )
        if coverage.get("rights_blocked") != rights_count:
            violations.append("block_rights_denominator_mismatch")
        if rights_count and coverage.get("state") not in {"rights_blocked", "partial", "unavailable"}:
            violations.append("block_rights_not_dominant")
        supported_state_for_coverage = {
            "complete": "supported",
            "partial": "partial",
            "unknown": "partial",
            "unavailable": "unavailable",
            "rights_blocked": "rights_blocked",
            "stale": "stale",
            "conflicted": "conflicted",
            "corrected": "corrected",
        }
        supported_claim = block.get("supported_claim")
        expected_supported_state = supported_state_for_coverage.get(coverage.get("state"))
        if (
            not isinstance(supported_claim, Mapping)
            or supported_claim.get("state") != expected_supported_state
        ):
            violations.append("block_supported_claim_coverage_mismatch")

    dependence = block.get("dependence")
    if not isinstance(dependence, Mapping):
        violations.append("block_dependence_invalid")
    else:
        independent_count = dependence.get("independent_evidence_count")
        included = coverage.get("included") if isinstance(coverage, Mapping) else None
        if isinstance(independent_count, int) and isinstance(included, int) and independent_count > included:
            violations.append("block_independence_exceeds_included")
        groups = dependence.get("groups") or ()
        if dependence.get("state") in {"shared_upstream", "mixed"} and not groups:
            violations.append("block_dependence_group_missing")
        for index, group in enumerate(groups):
            if not isinstance(group, Mapping):
                continue
            group_ids = set(group.get("reference_ids") or ())
            if not group_ids <= set(reference_ids):
                violations.append(f"block_dependence_group_external:{index}")
            if group.get("kind") == "shared_upstream" and group.get("deterministic_key") is not None:
                violations.append(f"block_shared_upstream_key_must_be_null:{index}")
            if group.get("kind") == "shared_upstream":
                has_shared_upstream_relation = any(
                    isinstance(relation, Mapping)
                    and relation.get("type") == "shares_upstream"
                    and str(reference.get("reference_id")) in group_ids
                    and relation.get("target_reference_id") in group_ids
                    for reference in resolved
                    for relation in reference.get("relations") or ()
                )
                if not has_shared_upstream_relation:
                    violations.append(f"block_shared_upstream_relation_missing:{index}")
            if group.get("kind") in _DETERMINISTIC_DEPENDENCE_KINDS and not group.get("deterministic_key"):
                violations.append(f"block_deterministic_group_key_missing:{index}")

    conflict = block.get("conflict_correction")
    lineage = block.get("lineage")
    corrected_ids = {
        str(reference.get("reference_id"))
        for reference in resolved
        if reference.get("correction", {}).get("kind") != "none"
    }
    if not isinstance(conflict, Mapping):
        violations.append("block_conflict_correction_invalid")
    else:
        cited = set(conflict.get("reference_ids") or ())
        if not cited <= set(reference_ids):
            violations.append("block_conflict_reference_external")
        if corrected_ids and (
            conflict.get("state") not in {"corrected", "mixed"} or not corrected_ids <= cited
        ):
            violations.append("block_correction_not_propagated")
    if not isinstance(lineage, Mapping):
        violations.append("block_lineage_invalid")
    elif corrected_ids and (
        lineage.get("state") != "recompiled"
        or not corrected_ids <= set(lineage.get("invalidated_by_reference_ids") or ())
        or not lineage.get("predecessor_block_ids")
    ):
        violations.append("block_correction_missing_recompile_receipt")

    uncertainty = block.get("uncertainty")
    if not isinstance(uncertainty, Mapping):
        violations.append("block_uncertainty_invalid")
    else:
        probability = uncertainty.get("probability")
        if uncertainty.get("state") == "calibrated":
            if probability is None or not uncertainty.get("derivation_ref") or not uncertainty.get("calibration_ref"):
                violations.append("block_calibrated_probability_missing_receipt")
        elif probability is not None:
            violations.append("block_probability_without_calibration")

    next_observable = block.get("next_observable")
    if not isinstance(next_observable, Mapping):
        violations.append("block_next_observable_invalid")
    elif next_observable.get("state") == "known" and not next_observable.get("description"):
        violations.append("block_next_observable_missing_description")
    elif next_observable.get("state") != "known" and (
        next_observable.get("description") is not None
        or next_observable.get("owner_clock_field") is not None
    ):
        violations.append("block_next_observable_nonknown_has_value")

    if block.get("authority") != ALL_FALSE_AUTHORITY:
        violations.append("block_authority_leak")
    return tuple(dict.fromkeys(violations))


def combined_block_violations(
    block: Mapping[str, Any],
    *,
    references: Mapping[str, Mapping[str, Any]],
) -> tuple[str, ...]:
    if not isinstance(block, Mapping):
        return ("block_not_mapping",)
    return tuple(dict.fromkeys((
        *_contract_schema_violations(block, path=BLOCK_SCHEMA_PATH, label="block"),
        *block_semantic_violations(block, references=references),
    )))


def validate_block(
    block: Mapping[str, Any],
    *,
    references: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    violations = combined_block_violations(block, references=references)
    if violations:
        raise EvidenceFoundationError(";".join(violations))
    return json.loads(json.dumps(block, allow_nan=False))


def recipe_semantic_violations(recipe: Mapping[str, Any]) -> tuple[str, ...]:
    """Return stable violations for one ordered consumer composition recipe."""
    vocab = load_vocabulary()
    violations: list[str] = []
    if recipe.get("schema") != RECIPE_SCHEMA:
        violations.append("recipe_schema_mismatch")
    if recipe.get("version") != VERSION:
        violations.append("recipe_version_mismatch")
    try:
        expected_id = compute_recipe_id(recipe)
    except (TypeError, ValueError):
        expected_id = None
        violations.append("recipe_identity_not_canonical_json")
    if recipe.get("recipe_id") != expected_id:
        violations.append("recipe_id_mismatch")

    owners = vocab.get("owner_stores") or {}
    subject_types = set(vocab.get("subject_key_types") or ())
    if not set(recipe.get("subject_key_types") or ()) <= subject_types:
        violations.append("recipe_subject_key_unknown")

    specs = recipe.get("block_specs")
    specs = specs if isinstance(specs, list) else []
    keys = [spec.get("block_key") for spec in specs if isinstance(spec, Mapping)]
    orders = [spec.get("order") for spec in specs if isinstance(spec, Mapping)]
    if len(keys) != len(set(keys)):
        violations.append("recipe_block_key_duplicate")
    if len(orders) != len(set(orders)) or sorted(orders) != list(range(1, len(orders) + 1)):
        violations.append("recipe_block_order_invalid")
    for index, spec in enumerate(specs):
        if not isinstance(spec, Mapping):
            continue
        minimum = spec.get("minimum_references")
        maximum = spec.get("maximum_references")
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            violations.append(f"recipe_block_bounds_invalid:{index}")
        if spec.get("requirement") == "required" and spec.get("on_absent") != "refuse":
            violations.append(f"recipe_required_block_not_fail_closed:{index}")
        if spec.get("requirement") == "optional" and spec.get("on_absent") == "refuse":
            violations.append(f"recipe_optional_block_refuses:{index}")
        allowed_owners = spec.get("allowed_owner_stores") or ()
        allowed_classes = set(spec.get("allowed_object_classes") or ())
        for owner_name in allowed_owners:
            owner = owners.get(owner_name)
            if not isinstance(owner, Mapping):
                violations.append(f"recipe_owner_unknown:{owner_name}")
            elif not allowed_classes <= set(owner.get("object_classes") or ()):
                violations.append(f"recipe_owner_class_not_bound:{owner_name}")

    allowed_joins = {
        (row.get("from"), row.get("to"), row.get("only_via"))
        for row in vocab.get("identity_join_rules") or ()
        if isinstance(row, Mapping)
    }
    for index, join in enumerate(recipe.get("identity_joins") or ()):
        if isinstance(join, Mapping) and (
            join.get("from"), join.get("to"), join.get("only_via")
        ) not in allowed_joins:
            violations.append(f"recipe_identity_join_forbidden:{index}")

    output_fields: set[str] = set()
    block_keys = set(keys)
    for index, mapping in enumerate(recipe.get("output_mappings") or ()):
        if not isinstance(mapping, Mapping):
            continue
        output_field = mapping.get("output_field")
        if output_field in output_fields:
            violations.append(f"recipe_output_field_duplicate:{output_field}")
        output_fields.add(output_field)
        if mapping.get("block_key") not in block_keys:
            violations.append(f"recipe_output_block_unknown:{index}")

    rule_codes = {
        rule.get("code") for rule in recipe.get("refusal_degradation_rules") or ()
        if isinstance(rule, Mapping)
    }
    for missing in sorted(_REQUIRED_RECIPE_RULES - rule_codes):
        violations.append(f"recipe_required_rule_missing:{missing}")
    if recipe.get("authority") != ALL_FALSE_AUTHORITY:
        violations.append("recipe_authority_leak")
    return tuple(dict.fromkeys(violations))


def combined_recipe_violations(recipe: Mapping[str, Any]) -> tuple[str, ...]:
    if not isinstance(recipe, Mapping):
        return ("recipe_not_mapping",)
    return tuple(dict.fromkeys((
        *_contract_schema_violations(recipe, path=RECIPE_SCHEMA_PATH, label="recipe"),
        *recipe_semantic_violations(recipe),
    )))


def validate_recipe(recipe: Mapping[str, Any]) -> dict[str, Any]:
    violations = combined_recipe_violations(recipe)
    if violations:
        raise EvidenceFoundationError(";".join(violations))
    return json.loads(json.dumps(recipe, allow_nan=False))


def compile_recipe(
    recipe: Mapping[str, Any],
    *,
    blocks: list[Mapping[str, Any]],
    references: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compile a deterministic in-memory receipt; persist no owner fact or block."""
    validated_recipe = validate_recipe(recipe)
    validated_blocks: dict[str, dict[str, Any]] = {}
    for block in blocks:
        validated = validate_block(block, references=references)
        key = validated["block_key"]
        if key in validated_blocks:
            raise EvidenceFoundationError(f"compile_block_key_duplicate:{key}")
        validated_blocks[key] = validated

    recipe_block_keys = {spec["block_key"] for spec in validated_recipe["block_specs"]}
    for key in sorted(set(validated_blocks) - recipe_block_keys):
        raise EvidenceFoundationError(f"compile_block_not_in_recipe:{key}")

    ordered_ids: list[str] = []
    missing_required: list[str] = []
    missing_optional: list[str] = []
    adverse_states: list[str] = []
    denominator = {
        key: 0 for key in (
            "total", "included", "excluded", "missing", "stale", "rights_blocked", "fallback"
        )
    }
    for spec in sorted(validated_recipe["block_specs"], key=lambda item: item["order"]):
        key = spec["block_key"]
        block = validated_blocks.get(key)
        if block is None:
            minimum = spec["minimum_references"]
            denominator["total"] += minimum
            denominator["excluded"] += minimum
            denominator["missing"] += minimum
            if spec["requirement"] == "required":
                missing_required.append(key)
            else:
                missing_optional.append(key)
            continue
        if block["consumer"] != validated_recipe["consumer"]:
            raise EvidenceFoundationError(f"compile_consumer_mismatch:{key}")
        if block["evidence_class"] != spec["evidence_class"]:
            raise EvidenceFoundationError(f"compile_evidence_class_mismatch:{key}")
        if not set(block["owner_stores"]) <= set(spec["allowed_owner_stores"]):
            raise EvidenceFoundationError(f"compile_owner_not_allowed:{key}")
        if not set(block["object_classes"]) <= set(spec["allowed_object_classes"]):
            raise EvidenceFoundationError(f"compile_object_class_not_allowed:{key}")
        count = len(block["reference_ids"])
        if not spec["minimum_references"] <= count <= spec["maximum_references"]:
            raise EvidenceFoundationError(f"compile_reference_count_out_of_bounds:{key}")
        if validated_recipe["consumer"]["output_contract"] not in block["permitted_consumers"]:
            raise EvidenceFoundationError(f"compile_consumer_not_permitted:{key}")
        ordered_ids.append(block["evidence_block_id"])
        for field in denominator:
            denominator[field] += block["coverage"][field]
        if block["coverage"]["state"] != "complete":
            adverse_states.append(block["coverage"]["state"])

    if missing_required:
        state = "refused"
        dominant = "required_block_absent"
    elif any(
        validated_blocks[key]["coverage"]["state"] == "conflicted"
        for key in validated_blocks
        if key in {spec["block_key"] for spec in validated_recipe["block_specs"] if spec["requirement"] == "required"}
    ):
        state = "conflicted"
        dominant = "conflicted"
    elif missing_optional or adverse_states:
        state = "partial"
        severity = [
            "rights_blocked", "unavailable", "conflicted", "stale", "partial", "unknown", "corrected"
        ]
        dominant = next((name for name in severity if name in adverse_states), "optional_block_absent")
    elif any(block["conflict_correction"]["state"] in {"corrected", "mixed"} for block in validated_blocks.values()):
        state = "corrected"
        dominant = "corrected"
    else:
        state = "complete"
        dominant = "none"

    return {
        "schema": COMPILATION_RECEIPT_SCHEMA,
        "version": VERSION,
        "recipe_id": validated_recipe["recipe_id"],
        "consumer": validated_recipe["consumer"],
        "state": state,
        "dominant_degradation": dominant,
        "block_ids": ordered_ids,
        "missing_required_blocks": missing_required,
        "missing_optional_blocks": missing_optional,
        "denominator": denominator,
        "owner_payloads_persisted": False,
        "authority": dict(ALL_FALSE_AUTHORITY),
    }


def combined_violations(
    reference: Mapping[str, Any],
) -> tuple[str, ...]:
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
    "BLOCK_SCHEMA",
    "BLOCK_SCHEMA_PATH",
    "COMPILATION_RECEIPT_SCHEMA",
    "EvidenceFoundationError",
    "RECIPE_SCHEMA",
    "RECIPE_SCHEMA_PATH",
    "SCHEMA",
    "VERSION",
    "VOCABULARY_PATH",
    "SCHEMA_PATH",
    "assert_semantically_valid",
    "canonical_json_bytes",
    "block_semantic_violations",
    "combined_block_violations",
    "combined_recipe_violations",
    "combined_violations",
    "compile_recipe",
    "compute_block_id",
    "compute_recipe_id",
    "compute_reference_id",
    "load_vocabulary",
    "reference_identity_payload",
    "render_owner_pointer",
    "semantic_violations",
    "recipe_semantic_violations",
    "validate_block",
    "validate_recipe",
    "validate_reference",
]
