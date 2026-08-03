"""Closed-world candidate-term projection for the issuer-state build.

This module is intentionally pre-instrument.  A validated document-term row is
projected one-for-one into an immutable *candidate term* so later resolver work
has a clean, point-in-time input.  It performs no fuzzy joining, never creates
an ``instrument_id``, and cannot calculate capacity, dilution, risk, or a
trading/Prophet decision.

The important distinction is temporal: a document-term may have been available
in the source ledger before this compiler ran, but the candidate-term becomes
available only when this deterministic projection is actually compiled.  This
prevents a later W3A deployment from silently backdating its own knowledge.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import inspect
import json
from pathlib import Path
from types import CodeType, MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.document_terms import (
    DOCUMENT_TERM_SCHEMA,
    SemanticEntrypoint,
    _SCHEMA_FORMAT_BINDINGS,
    _semantic_closure,
    current_document_terms_as_of,
    validate_document_term_contract,
    validate_document_term_source_authority,
)


_RELEASED_CURRENT_DOCUMENT_TERMS_AS_OF = current_document_terms_as_of
_RELEASED_DOCUMENT_TERM_CONTRACT = validate_document_term_contract
_RELEASED_DOCUMENT_TERM_SOURCE_AUTHORITY = validate_document_term_source_authority


INSTRUMENT_CANDIDATE_TERM_SCHEMA = "capital_structure.instrument_candidate_term.v1"
MAPPING_VERSION = "capital-structure-instrument-candidate-terms/1.0.0"
_CANDIDATE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "capital_structure_instrument_candidate_term.schema.json"
_CANDIDATE_SCHEMA_SHA256 = (
    "139401d9d0f24569363a9ea8198acffa4fd295cab89c150b69827a718a97cd7d"
)

_FAMILY_BY_DIRECT_CLASSIFICATION = (
    ("common_stock", "common_stock"),
    ("preferred_stock", "preferred_stock"),
    ("debt", "debt"),
    ("units", "units"),
    ("warrants", "warrant"),
    ("other", "other"),
)
_SUPPORTED_TERM_TYPES = (
    (
        "amount_to_be_registered",
        frozenset({"share_count", "principal_amount", "quantity"}),
    ),
    ("proposed_maximum_offering_price_per_unit", frozenset({"price"})),
    ("proposed_maximum_aggregate_offering_price", frozenset({"amount"})),
    ("registration_fee", frozenset({"amount"})),
    ("filing_fee_rate", frozenset({"rate"})),
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _digest_id(prefix: str, body: Mapping[str, Any]) -> str:
    return prefix + _sha256(body)[:24]


def _parse_time(value: Any, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any, field: str) -> str:
    return _parse_time(value, field).isoformat().replace("+00:00", "Z")


def _make_candidate_term_contract_validator(
    schema_path: Path,
    schema_sha256: str,
    validator_class: type[Any],
    format_checker_class: type[Any],
    schema_format_bindings: tuple[
        tuple[str, Callable[[Any], bool], tuple[type[BaseException], ...]], ...
    ],
) -> Callable[[], Callable[[Mapping[str, Any]], Any]]:
    """Prebuild and seal the actually invoked candidate validation method."""
    def descriptor_functions(value: Any) -> tuple[Callable[..., Any], ...]:
        if inspect.isfunction(value):
            return (value,)
        if isinstance(value, (staticmethod, classmethod)):
            return (value.__func__,)
        if isinstance(value, property):
            return tuple(
                function
                for function in (value.fget, value.fset, value.fdel)
                if function is not None
            )
        return ()

    def descriptor_codes(value: Any) -> tuple[CodeType, ...]:
        return tuple(
            function.__code__ for function in descriptor_functions(value)
        )

    def function_dependency_bindings(
        roots: Sequence[Callable[..., Any]],
    ) -> tuple[
        tuple[
            Callable[..., Any],
            CodeType,
            tuple[tuple[str, Any, CodeType | None], ...],
        ],
        ...,
    ]:
        pending = list(roots)
        seen: set[Callable[..., Any]] = set()
        bindings: list[
            tuple[
                Callable[..., Any],
                CodeType,
                tuple[tuple[str, Any, CodeType | None], ...],
            ]
        ] = []
        while pending:
            function = pending.pop()
            if not inspect.isfunction(function) or function in seen:
                continue
            seen.add(function)
            globals_bound: list[tuple[str, Any, CodeType | None]] = []
            for name in sorted(set(function.__code__.co_names)):
                if name not in function.__globals__:
                    continue
                value = function.__globals__[name]
                globals_bound.append(
                    (name, value, getattr(value, "__code__", None)),
                )
                if (
                    inspect.isfunction(value)
                    and str(value.__module__).startswith(
                        ("jsonschema.", "referencing."),
                    )
                ):
                    pending.append(value)
            bindings.append(
                (function, function.__code__, tuple(globals_bound)),
            )
        return tuple(
            sorted(
                bindings,
                key=lambda item: (
                    str(item[0].__module__), str(item[0].__qualname__),
                ),
            ),
        )

    def execution_surface(
        cls: type[Any],
    ) -> tuple[tuple[str, Any, tuple[CodeType, ...]], ...]:
        names = {
            name
            for owner in cls.__mro__
            if owner is not object
            for name, value in vars(owner).items()
            if callable(value)
            or isinstance(value, (staticmethod, classmethod, property))
        }
        bindings: list[tuple[str, Any, tuple[CodeType, ...]]] = []
        for name in sorted(names):
            for owner in cls.__mro__:
                if name in vars(owner):
                    descriptor = vars(owner)[name]
                    bindings.append((name, descriptor, descriptor_codes(descriptor)))
                    break
        return tuple(bindings)

    encoded = schema_path.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(encoded).hexdigest(), schema_sha256):
        raise ValueError("instrument candidate-term schema release digest mismatch")
    schema = json.loads(encoded.decode("utf-8"))
    validator_class.check_schema(schema)
    original_iter_errors = validator_class.iter_errors
    validator_registry_bindings = tuple(
        (keyword, implementation, getattr(implementation, "__code__", None))
        for keyword, implementation in sorted(validator_class.VALIDATORS.items())
    )
    type_checker_bindings = tuple(
        (name, implementation, getattr(implementation, "__code__", None))
        for name, implementation in sorted(
            validator_class.TYPE_CHECKER._type_checkers.items(),
        )
    )
    format_checker_bindings = tuple(
        (
            name,
            implementation,
            getattr(implementation, "__code__", None),
            raises,
        )
        for name, implementation, raises in schema_format_bindings
    )
    execution_surfaces = (
        (validator_class, execution_surface(validator_class)),
        (format_checker_class, execution_surface(format_checker_class)),
    )
    dependency_roots = [
        implementation
        for _name, implementation, _code in (
            *validator_registry_bindings,
            *type_checker_bindings,
        )
    ]
    dependency_roots.extend(
        implementation
        for _name, implementation, _code, _raises in format_checker_bindings
    )
    validator_runtime_methods = frozenset({
        "__init__", "__attrs_post_init__", "iter_errors", "descend",
        "evolve", "is_type", "_validate_reference", "is_valid",
    })
    format_checker_runtime_methods = frozenset({
        "__init__", "check", "conforms",
    })
    dependency_roots.extend(
        function
        for cls, bindings in execution_surfaces
        for name, descriptor, _codes in bindings
        if name in (
            validator_runtime_methods
            if cls is validator_class
            else format_checker_runtime_methods
        )
        for function in descriptor_functions(descriptor)
    )
    schema_execution_dependencies = function_dependency_bindings(dependency_roots)

    def _candidate_term_contract_validator() -> Callable[[Mapping[str, Any]], Any]:
        current = schema_path.read_bytes()
        if not hmac.compare_digest(hashlib.sha256(current).hexdigest(), schema_sha256):
            raise ValueError("instrument candidate-term schema release digest mismatch")
        for cls, bindings in execution_surfaces:
            for name, expected, expected_codes in bindings:
                actual_owner = next(
                    (owner for owner in cls.__mro__ if name in vars(owner)),
                    None,
                )
                if (
                    actual_owner is None
                    or vars(actual_owner)[name] is not expected
                ):
                    raise ValueError(
                        "instrument candidate schema validator executable binding changed"
                    )
                actual_codes = descriptor_codes(vars(actual_owner)[name])
                if (
                    len(actual_codes) != len(expected_codes)
                    or any(
                        actual is not expected_code
                        for actual, expected_code in zip(
                            actual_codes, expected_codes, strict=True,
                        )
                    )
                ):
                    raise ValueError(
                        "instrument candidate schema validator executable binding changed"
                    )
        for function, expected_code, globals_bound in schema_execution_dependencies:
            if function.__code__ is not expected_code:
                raise ValueError(
                    "instrument candidate schema validator executable binding changed"
                )
            for name, expected, expected_code in globals_bound:
                if name not in function.__globals__:
                    raise ValueError(
                        "instrument candidate schema validator executable binding changed"
                    )
                actual = function.__globals__[name]
                if (
                    actual is not expected
                    or getattr(actual, "__code__", None) is not expected_code
                ):
                    raise ValueError(
                        "instrument candidate schema validator executable binding changed"
                    )
        current_registry = validator_class.VALIDATORS
        if set(current_registry) != {
            name for name, _implementation, _code in validator_registry_bindings
        }:
            raise ValueError(
                "instrument candidate schema validator executable binding changed"
            )
        for keyword, expected_implementation, expected_code in (
            validator_registry_bindings
        ):
            implementation = current_registry[keyword]
            if (
                implementation is not expected_implementation
                or getattr(implementation, "__code__", None) is not expected_code
            ):
                raise ValueError(
                    "instrument candidate schema validator executable binding changed"
                )
        current_type_checkers = validator_class.TYPE_CHECKER._type_checkers
        if set(current_type_checkers) != {
            name for name, _implementation, _code in type_checker_bindings
        }:
            raise ValueError(
                "instrument candidate schema validator executable binding changed"
            )
        for name, expected_implementation, expected_code in type_checker_bindings:
            implementation = current_type_checkers[name]
            if (
                implementation is not expected_implementation
                or getattr(implementation, "__code__", None) is not expected_code
            ):
                raise ValueError(
                    "instrument candidate schema validator executable binding changed"
                )
        format_checker = format_checker_class(formats=())
        if format_checker.checkers:
            raise ValueError(
                "instrument candidate schema validator executable binding changed"
            )
        current_format_checkers = MappingProxyType({
            name: (implementation, raises)
            for name, implementation, _code, raises in format_checker_bindings
        })
        format_checker.checkers = current_format_checkers
        for name, expected_implementation, expected_code, expected_raises in (
            format_checker_bindings
        ):
            implementation, raises = current_format_checkers[name]
            if (
                implementation is not expected_implementation
                or getattr(implementation, "__code__", None) is not expected_code
                or raises != expected_raises
            ):
                raise ValueError(
                    "instrument candidate schema validator executable binding changed"
                )
        fresh_schema = json.loads(current.decode("utf-8"))
        validator = validator_class(
            fresh_schema, format_checker=format_checker,
        )
        return original_iter_errors.__get__(validator, validator_class)

    return _candidate_term_contract_validator


_candidate_term_contract_validator = _make_candidate_term_contract_validator(
    _CANDIDATE_SCHEMA_PATH,
    _CANDIDATE_SCHEMA_SHA256,
    Draft202012Validator,
    FormatChecker,
    _SCHEMA_FORMAT_BINDINGS,
)


def direct_observation_sha256(record: Mapping[str, Any]) -> str:
    """Return the exact canonical digest of a validated direct observation."""
    return _sha256(record)


def logical_candidate_term_id_for(source: Mapping[str, Any]) -> str:
    """Stable one-to-one slot identity; it intentionally contains no instrument key."""
    return _digest_id(
        "instrument-candidate-term-slot:cs:",
        {
            "source_logical_observation_id": source.get("logical_observation_id"),
            "mapping_version": MAPPING_VERSION,
        },
    )


def candidate_term_id_for(record: Mapping[str, Any]) -> str:
    body = deepcopy(dict(record))
    body.pop("candidate_term_id", None)
    return _digest_id("instrument-candidate-term:cs:", body)


def _source_receipt(source: Mapping[str, Any], source_digest: str) -> dict[str, Any]:
    point_in_time = source.get("point_in_time") or {}
    body = {
        "direct_observation_id": source.get("observation_id"),
        "direct_observation_sha256": source_digest,
        "direct_available_at": point_in_time.get("available_at"),
    }
    return {
        "schema": "capital_structure.instrument_candidate_term_input_receipt.v1",
        "receipt_id": _digest_id("receipt:instrument-candidate-term-input:cs:", body),
        "verification_state": "validated_document_term_observation",
        **body,
    }


def candidate_mapping_for_document_term(source: Mapping[str, Any]) -> dict[str, Any]:
    """Classify only what the source row directly closes.

    ``registration_security_candidate`` is deliberately weaker than primary,
    resale, active, executable, or available capacity.  Only the direct amount
    field can receive it; fee, rate, and price rows are linked evidence but do
    not establish a supply role.
    """
    upstream_state = source.get("state") or {}
    disposition = str(upstream_state.get("disposition") or "")
    if disposition == "ambiguous":
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "ambiguous", "reason": "upstream_document_term_ambiguous"},
        }
    if disposition != "observed":
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "upstream_document_term_unavailable"},
        }

    term = source.get("term") or {}
    name = str(term.get("name") or "")
    term_type = str(term.get("term_type") or "")
    if term_type not in dict(_SUPPORTED_TERM_TYPES).get(name, frozenset()):
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "unsupported_source_term_type"},
        }

    security = source.get("security") or {}
    row_id = security.get("row_id")
    classification = str(security.get("classification") or "unknown")
    if row_id is None:
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "missing_security_row"},
        }
    family = dict(_FAMILY_BY_DIRECT_CLASSIFICATION).get(classification)
    if family is None:
        return {
            "mapping_version": MAPPING_VERSION,
            "family": "unknown",
            "supply_role": "unknown",
            "state": {"disposition": "deferred", "reason": "security_classification_unknown"},
        }
    if name == "amount_to_be_registered":
        return {
            "mapping_version": MAPPING_VERSION,
            "family": family,
            "supply_role": "registration_security_candidate",
            "state": {"disposition": "observed", "reason": "direct_security_class_mapping"},
        }
    return {
        "mapping_version": MAPPING_VERSION,
        "family": family,
        "supply_role": "not_applicable",
        "state": {
            "disposition": "observed",
            "reason": "direct_security_class_mapping_supply_not_applicable",
        },
    }


def _candidate_semantic_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    source = record.get("source_term") or {}
    candidate = record.get("candidate") or {}
    return (
        str(source.get("observation_id") or ""),
        str(source.get("observation_sha256") or ""),
        str(candidate.get("mapping_version") or ""),
    )


def _embedded_mapping_source(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the closed mapping inputs carried inside a candidate record.

    This intentionally needs no external ledger so standalone validation catches
    a family/supply-role mutation even if an attacker recomputes the immutable
    candidate ID.  The compiler performs the stronger whole-source binding
    separately when the direct ledger is available.
    """
    return {
        "state": deepcopy(record.get("source_term_state") or {}),
        "security": deepcopy(record.get("security") or {}),
        "term": deepcopy(record.get("term") or {}),
    }


def _validate_candidate_source_binding_core(
    record: Mapping[str, Any], source: Mapping[str, Any],
) -> None:
    """Prove a candidate remains an exact projection of one direct source row.

    The candidate ledger keeps copied evidence for queryability, but that copy is
    not trusted merely because its candidate ID was recomputed.  This binding is
    checked whenever the offline compiler sees the append-only direct ledger.
    """
    source_digest = direct_observation_sha256(source)
    source_term = record.get("source_term") or {}
    source_point = source.get("point_in_time") or {}
    if (
        source_term.get("schema") != DOCUMENT_TERM_SCHEMA
        or source_term.get("observation_id") != source.get("observation_id")
        or source_term.get("logical_observation_id") != source.get("logical_observation_id")
        or int(source_term.get("correction_version") or 0)
        != int((source.get("version") or {}).get("correction_version") or 0)
        or source_term.get("observation_sha256") != source_digest
        or source_term.get("source_available_at") != source_point.get("source_available_at")
        or source_term.get("available_at") != source_point.get("available_at")
        or source_term.get("receipt") != _source_receipt(source, source_digest)
    ):
        raise ValueError("instrument candidate-term source receipt does not bind its direct observation")
    copied_fields = (
        "issuer_id", "filing", "document", "security", "term", "reported",
        "normalized", "evidence", "extraction",
    )
    for field in copied_fields:
        if record.get(field) != source.get(field):
            raise ValueError(f"instrument candidate-term {field} is detached from its direct observation")
    if record.get("source_term_state") != source.get("state"):
        raise ValueError("instrument candidate-term source_term_state is detached from its direct observation")
    point = record.get("point_in_time") or {}
    if (
        point.get("source_available_at") != source_point.get("source_available_at")
        or point.get("source_term_available_at") != source_point.get("available_at")
    ):
        raise ValueError("instrument candidate-term point-in-time source lineage is detached")
    relationships = record.get("relationships") or {}
    if list(relationships.get("source_observation_supersedes") or []) != list(
        (source.get("relationships") or {}).get("supersedes") or []
    ):
        raise ValueError("instrument candidate-term source supersedes lineage is detached")
    if record.get("logical_candidate_term_id") != logical_candidate_term_id_for(source):
        raise ValueError("instrument candidate-term logical identity is detached from its direct observation")
    if record.get("candidate") != candidate_mapping_for_document_term(source):
        raise ValueError("instrument candidate-term mapping is detached from its direct observation")


def _make_validate_candidate_source_binding(
    policy_validator: Callable[[], None],
    source_binding_core: Callable[[Mapping[str, Any], Mapping[str, Any]], None],
    candidate_contract_validator: Callable[[Sequence[Mapping[str, Any]]], None],
    document_contract_validator: Callable[[Mapping[str, Any]], None],
) -> Callable[[Mapping[str, Any], Mapping[str, Any]], None]:
    def validate_candidate_source_binding(
        record: Mapping[str, Any], source: Mapping[str, Any],
    ) -> None:
        """Prove a candidate remains an exact projection of one direct row."""
        if globals().get("_validated_candidate_authority_policy") is not policy_validator:
            raise ValueError("instrument candidate authority policy binding changed")
        if (
            globals().get("_validate_candidate_source_binding_core")
            is not source_binding_core
        ):
            raise ValueError("instrument candidate source-binding core changed")
        if (
            globals().get("_validate_candidate_term_records_contract")
            is not candidate_contract_validator
        ):
            raise ValueError("instrument candidate closed-contract binding changed")
        if (
            globals().get("validate_document_term_contract")
            is not document_contract_validator
        ):
            raise ValueError("instrument candidate document-term contract binding changed")
        policy_validator()
        candidate_contract_validator([record])
        document_contract_validator(source)
        source_binding_core(record, source)

    return validate_candidate_source_binding


def _validate_candidate_term_records_contract(
    records: Sequence[Mapping[str, Any]],
) -> None:
    """Apply the closed candidate schema to every admitted row."""
    iter_errors = _candidate_term_contract_validator()
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise ValueError(f"instrument candidate-term row {index} must be an object")
        record = dict(raw)
        errors = sorted(
            iter_errors(record),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            joined = "; ".join(
                f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
                f"{error.message}"
                for error in errors[:5]
            )
            raise ValueError(
                f"instrument candidate-term row {index} contract violation: {joined}"
            )


def _validate_candidate_term_structure(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate candidate-local shape, IDs, and correction chains only.

    This is intentionally private: a candidate record duplicates direct-term
    fields, and a recomputed candidate ID can make an altered duplicate look
    structurally self-consistent.  It is therefore not proof of issuer,
    evidence, direct-value, or source-receipt authority.  Public validation and
    all PIT reads bind these rows to verified direct observations below.
    """
    _validate_candidate_term_records_contract(records)
    by_id: set[str] = set()
    by_logical: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, raw in enumerate(records):
        record = dict(raw)
        candidate_id = str(record.get("candidate_term_id") or "")
        if candidate_id != candidate_term_id_for(record):
            raise ValueError(f"instrument candidate-term row {index} candidate_term_id digest mismatch")
        if candidate_id in by_id:
            raise ValueError(f"duplicate instrument candidate-term candidate_term_id {candidate_id}")
        by_id.add(candidate_id)
        source = record.get("source_term") or {}
        receipt = source.get("receipt") or {}
        if (
            source.get("observation_id") != receipt.get("direct_observation_id")
            or source.get("observation_sha256") != receipt.get("direct_observation_sha256")
            or source.get("available_at") != receipt.get("direct_available_at")
        ):
            raise ValueError(f"instrument candidate-term row {index} source receipt is detached")
        expected_receipt = _source_receipt(
            {
                "observation_id": source.get("observation_id"),
                "point_in_time": {"available_at": source.get("available_at")},
            },
            str(source.get("observation_sha256") or ""),
        )
        if receipt != expected_receipt:
            raise ValueError(f"instrument candidate-term row {index} source receipt digest mismatch")
        point = record.get("point_in_time") or {}
        source_available = _parse_time(point.get("source_available_at"), "source_available_at")
        direct_available = _parse_time(point.get("source_term_available_at"), "source_term_available_at")
        available = _parse_time(point.get("available_at"), "available_at")
        if direct_available < source_available or available < direct_available:
            raise ValueError(f"instrument candidate-term row {index} point-in-time lineage is retroactive")
        if record.get("candidate") != candidate_mapping_for_document_term(_embedded_mapping_source(record)):
            raise ValueError(f"instrument candidate-term row {index} candidate mapping is detached from embedded source fields")
        logical = str(record.get("logical_candidate_term_id") or "")
        if not logical:
            raise ValueError(f"instrument candidate-term row {index} lacks logical_candidate_term_id")
        by_logical[logical].append(record)

    for logical, versions in by_logical.items():
        ordered = sorted(versions, key=lambda row: int((row.get("version") or {}).get("correction_version") or 0))
        actual = [int((row.get("version") or {}).get("correction_version") or 0) for row in ordered]
        if actual != list(range(1, len(ordered) + 1)):
            raise ValueError(f"instrument candidate-term {logical} has non-contiguous correction versions")
        for number, record in enumerate(ordered, start=1):
            version = record.get("version") or {}
            relationships = record.get("relationships") or {}
            prior = ordered[number - 2] if number > 1 else None
            if prior is None:
                if version.get("correction_of") is not None or list(relationships.get("supersedes") or []):
                    raise ValueError(f"instrument candidate-term {logical} v1 cannot be a correction")
                continue
            if version.get("correction_of") != prior.get("candidate_term_id"):
                raise ValueError(f"instrument candidate-term {logical} correction does not point to prior version")
            if list(relationships.get("supersedes") or []) != [prior.get("candidate_term_id")]:
                raise ValueError(f"instrument candidate-term {logical} supersedes does not point to prior version")
            prior_time = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
            current_time = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
            if current_time <= prior_time:
                raise ValueError(f"instrument candidate-term {logical} correction is retroactive")


def _make_validate_candidate_term_structure(
    policy_validator: Callable[[], None],
    structure_core: Callable[[Sequence[Mapping[str, Any]]], None],
) -> Callable[[Sequence[Mapping[str, Any]]], None]:
    def validate_candidate_term_structure(
        records: Sequence[Mapping[str, Any]],
    ) -> None:
        """Run sealed candidate-local integrity checks without source authority."""
        if globals().get("_validated_candidate_authority_policy") is not policy_validator:
            raise ValueError("instrument candidate authority policy binding changed")
        if globals().get("_validate_candidate_term_structure") is not structure_core:
            raise ValueError("instrument candidate structure core binding changed")
        policy_validator()
        structure_core(records)

    return validate_candidate_term_structure


def _validate_candidate_term_history_against_sources(
    records: Sequence[Mapping[str, Any]], direct_sources: Sequence[Mapping[str, Any]],
) -> None:
    _validate_candidate_term_structure(records)
    sources_by_id = {str(row["observation_id"]): row for row in direct_sources}
    for index, record in enumerate(records):
        source_id = str((record.get("source_term") or {}).get("observation_id") or "")
        source = sources_by_id.get(source_id)
        if source is None:
            raise ValueError(
                f"instrument candidate-term row {index} source observation is absent from verified direct ledger"
            )
        _validate_candidate_source_binding_core(record, source)


def _validate_candidate_term_history_core(
    records: Sequence[Mapping[str, Any]],
    *,
    document_term_observations: Sequence[Mapping[str, Any]],
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    document_term_authority_validator: Callable[..., list[dict[str, Any]]],
) -> None:
    """Validate candidates against the verified direct-term source authority.

    Candidate-local IDs detect accidental corruption but are not an authority
    boundary.  A trusted read must prove each copied issuer, evidence span, and
    direct fact against the validated direct ledger and its retained source
    bytes.
    """
    direct_sources = document_term_authority_validator(
        document_term_observations,
        source_manifests=source_manifests,
        source_reader=source_reader,
    )
    _validate_candidate_term_history_against_sources(records, direct_sources)


def _make_validate_candidate_term_history(
    policy_validator: Callable[[], None],
    history_core: Callable[..., None],
    document_term_authority_validator: Callable[..., list[dict[str, Any]]],
) -> Callable[..., None]:
    def validate_candidate_term_history(
        records: Sequence[Mapping[str, Any]],
        *,
        document_term_observations: Sequence[Mapping[str, Any]],
        source_manifests: Sequence[Mapping[str, Any]],
        source_reader: Callable[[Mapping[str, Any]], bytes | None],
    ) -> None:
        """Validate candidates against sealed direct-term source authority."""
        if globals().get("_validated_candidate_authority_policy") is not policy_validator:
            raise ValueError("instrument candidate authority policy binding changed")
        if globals().get("_validate_candidate_term_history_core") is not history_core:
            raise ValueError("instrument candidate history core binding changed")
        if (
            globals().get("validate_document_term_authority")
            is not document_term_authority_validator
        ):
            raise ValueError("instrument candidate document-term gate binding changed")
        policy_validator()
        history_core(
            records,
            document_term_observations=document_term_observations,
            source_manifests=source_manifests,
            source_reader=source_reader,
            document_term_authority_validator=document_term_authority_validator,
        )

    return validate_candidate_term_history


def _current_candidate_terms_as_of_core(
    records: Sequence[Mapping[str, Any]],
    as_of: str,
) -> list[dict[str, Any]]:
    cutoff = _parse_time(as_of, "as_of")
    visible: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        available = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
        if available > cutoff:
            continue
        logical = str(record["logical_candidate_term_id"])
        prior = visible.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            visible[logical] = record
    return [dict(visible[key]) for key in sorted(visible)]


def _make_current_candidate_terms_as_of(
    policy_validator: Callable[[], None],
    current_core: Callable[..., list[dict[str, Any]]],
    candidate_history_validator: Callable[..., None],
) -> Callable[..., list[dict[str, Any]]]:
    def current_candidate_terms_as_of(
        records: Sequence[Mapping[str, Any]],
        as_of: str,
        *,
        document_term_observations: Sequence[Mapping[str, Any]],
        source_manifests: Sequence[Mapping[str, Any]],
        source_reader: Callable[[Mapping[str, Any]], bytes | None],
    ) -> list[dict[str, Any]]:
        """Return verified candidate versions visible strictly at system time."""
        if globals().get("_validated_candidate_authority_policy") is not policy_validator:
            raise ValueError("instrument candidate authority policy binding changed")
        if globals().get("_current_candidate_terms_as_of_core") is not current_core:
            raise ValueError("instrument candidate current core binding changed")
        if (
            globals().get("validate_candidate_term_history")
            is not candidate_history_validator
        ):
            raise ValueError("instrument candidate history gate binding changed")
        policy_validator()
        candidate_history_validator(
            records,
            document_term_observations=document_term_observations,
            source_manifests=source_manifests,
            source_reader=source_reader,
        )
        return current_core(records, as_of)

    return current_candidate_terms_as_of


def _validate_document_term_authority_core(
    records: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    trusted_source_authority: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Verify direct-term rows against immutable manifests and retained bytes.

    Candidate receipts name a direct observation, but no digest alone can prove
    that the candidate's copied issuer/evidence/value came from that observation.
    Reuse the direct-term source validator before a candidate ledger is compiled
    or read, so a self-consistent edit to either Parquet file fails closed.
    """
    sources = [deepcopy(dict(raw)) for raw in records]
    return trusted_source_authority(
        sources,
        source_manifests=source_manifests,
        source_reader=source_reader,
    )


def _make_validate_document_term_authority(
    policy_validator: Callable[[], None],
    authority_core: Callable[..., list[dict[str, Any]]],
    trusted_source_authority: Callable[..., list[dict[str, Any]]],
) -> Callable[..., list[dict[str, Any]]]:
    def validate_document_term_authority(
        records: Sequence[Mapping[str, Any]],
        *,
        source_manifests: Sequence[Mapping[str, Any]],
        source_reader: Callable[[Mapping[str, Any]], bytes | None],
    ) -> list[dict[str, Any]]:
        """Verify direct rows through the sealed document-term source gate."""
        if globals().get("_validated_candidate_authority_policy") is not policy_validator:
            raise ValueError("instrument candidate authority policy binding changed")
        if globals().get("_validate_document_term_authority_core") is not authority_core:
            raise ValueError("instrument candidate document authority core changed")
        if (
            globals().get("validate_document_term_source_authority")
            is not trusted_source_authority
        ):
            raise ValueError("instrument candidate document-term authority binding changed")
        policy_validator()
        return authority_core(
            records,
            source_manifests=source_manifests,
            source_reader=source_reader,
            trusted_source_authority=trusted_source_authority,
        )

    return validate_document_term_authority


def _project_record(
    source: Mapping[str, Any], *, generated_at: str, correction_version: int, correction_of: str | None,
) -> dict[str, Any]:
    source_digest = direct_observation_sha256(source)
    source_point = source.get("point_in_time") or {}
    source_relationships = source.get("relationships") or {}
    record: dict[str, Any] = {
        "schema": INSTRUMENT_CANDIDATE_TERM_SCHEMA,
        "logical_candidate_term_id": logical_candidate_term_id_for(source),
        "issuer_id": source["issuer_id"],
        "source_term": {
            "schema": DOCUMENT_TERM_SCHEMA,
            "observation_id": source["observation_id"],
            "logical_observation_id": source["logical_observation_id"],
            "correction_version": int((source.get("version") or {}).get("correction_version") or 0),
            "observation_sha256": source_digest,
            "source_available_at": source_point["source_available_at"],
            "available_at": source_point["available_at"],
            "receipt": _source_receipt(source, source_digest),
        },
        "candidate": candidate_mapping_for_document_term(source),
        "filing": deepcopy(source["filing"]),
        "document": deepcopy(source["document"]),
        "security": deepcopy(source["security"]),
        "term": deepcopy(source["term"]),
        "source_term_state": deepcopy(source["state"]),
        "reported": deepcopy(source["reported"]),
        "normalized": deepcopy(source["normalized"]),
        "evidence": deepcopy(source["evidence"]),
        "extraction": deepcopy(source["extraction"]),
        "relationships": {
            "supersedes": [correction_of] if correction_of else [],
            "source_observation_supersedes": list(source_relationships.get("supersedes") or []),
            "contradiction_ids": [],
        },
        "version": {
            "immutable_record": True,
            "correction_version": correction_version,
            "correction_of": correction_of,
        },
        "point_in_time": {
            "source_available_at": source_point["source_available_at"],
            "source_term_available_at": source_point["available_at"],
            "available_at": generated_at,
        },
        "authority": {
            "is_context_only": True,
            "instrument_authority": False,
            "capacity_authority": False,
            "risk_authority": False,
            "probability_authority": False,
            "rank_authority": False,
            "sizing_authority": False,
            "entry_authority": False,
            "trade_authority": False,
            "prophet_authority": False,
        },
    }
    record["candidate_term_id"] = candidate_term_id_for(record)
    return record


def _compile_candidate_term_records_core(
    document_term_observations: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    existing_candidate_terms: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
    source_as_of: str | None = None,
    document_term_authority_validator: Callable[..., list[dict[str, Any]]],
    current_document_terms_selector: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any]:
    """Project current direct terms into an append-only candidate-term ledger.

    A first run intentionally establishes a fresh candidate baseline from the
    latest direct row visible in the input ledger.  It does **not** replay old
    upstream corrections with fabricated historical candidate availability.
    Subsequent source corrections create an ordinary candidate correction when
    this compiler observes them.
    """
    generated = _iso(generated_at, "generated_at")
    direct_sources = document_term_authority_validator(
        document_term_observations,
        source_manifests=source_manifests,
        source_reader=source_reader,
    )
    existing = [deepcopy(dict(raw)) for raw in existing_candidate_terms]
    _validate_candidate_term_history_against_sources(existing, direct_sources)

    if source_as_of is None:
        source_cutoff = max(
            (_parse_time((row.get("point_in_time") or {}).get("available_at"), "source.available_at") for row in direct_sources),
            default=_parse_time(generated, "generated_at"),
        ).isoformat().replace("+00:00", "Z")
    else:
        source_cutoff = _iso(source_as_of, "source_as_of")
        latest_direct = max(
            (_parse_time((row.get("point_in_time") or {}).get("available_at"), "source.available_at") for row in direct_sources),
            default=_parse_time(generated, "generated_at"),
        )
        if _parse_time(source_cutoff, "source_as_of") < latest_direct:
            raise ValueError(
                "historical source_as_of cannot write the canonical candidate ledger; "
                "use a read-only isolated replay instead"
            )
    selected = (
        current_document_terms_selector(direct_sources, source_cutoff)
        if direct_sources
        else []
    )
    for source in selected:
        direct_available = _parse_time((source.get("point_in_time") or {}).get("available_at"), "source.available_at")
        if _parse_time(generated, "generated_at") < direct_available:
            raise ValueError("generated_at cannot precede a selected document-term availability")

    current_by_logical: dict[str, Mapping[str, Any]] = {}
    for record in existing:
        logical = str(record["logical_candidate_term_id"])
        prior = current_by_logical.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            current_by_logical[logical] = record

    additions: list[dict[str, Any]] = []
    unchanged = 0
    for source in sorted(selected, key=lambda row: str(row["logical_observation_id"])):
        logical = logical_candidate_term_id_for(source)
        prior = current_by_logical.get(logical)
        source_digest = direct_observation_sha256(source)
        next_key = (str(source["observation_id"]), source_digest, MAPPING_VERSION)
        if prior is not None and _candidate_semantic_key(prior) == next_key:
            unchanged += 1
            continue
        correction_version = 1 if prior is None else int((prior.get("version") or {}).get("correction_version") or 0) + 1
        correction_of = None if prior is None else str(prior["candidate_term_id"])
        if prior is not None:
            prior_available = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
            if _parse_time(generated, "generated_at") <= prior_available:
                raise ValueError("generated_at must be later than the prior candidate-term correction")
        additions.append(_project_record(
            source,
            generated_at=generated,
            correction_version=correction_version,
            correction_of=correction_of,
        ))

    observations = existing + additions
    _validate_candidate_term_history_against_sources(observations, direct_sources)
    return {
        "observations": sorted(
            observations,
            key=lambda row: (str(row["logical_candidate_term_id"]), int((row.get("version") or {}).get("correction_version") or 0)),
        ),
        "counts": {
            "input_document_terms": len(direct_sources),
            "input_current_document_terms": len(selected),
            "created": len(additions),
            "unchanged": unchanged,
            "total": len(observations),
        },
        "source_as_of": source_cutoff,
    }


def _make_compile_candidate_term_records(
    policy_validator: Callable[[], None],
    compiler_core: Callable[..., dict[str, Any]],
    document_term_authority_validator: Callable[..., list[dict[str, Any]]],
    current_document_terms_selector: Callable[..., list[dict[str, Any]]],
) -> Callable[..., dict[str, Any]]:
    def compile_candidate_term_records(
        document_term_observations: Sequence[Mapping[str, Any]],
        *,
        source_manifests: Sequence[Mapping[str, Any]],
        source_reader: Callable[[Mapping[str, Any]], bytes | None],
        existing_candidate_terms: Sequence[Mapping[str, Any]] = (),
        generated_at: str,
        source_as_of: str | None = None,
    ) -> dict[str, Any]:
        """Project direct terms through sealed candidate and document gates."""
        if globals().get("_validated_candidate_authority_policy") is not policy_validator:
            raise ValueError("instrument candidate authority policy binding changed")
        if globals().get("_compile_candidate_term_records_core") is not compiler_core:
            raise ValueError("instrument candidate compiler core binding changed")
        if (
            globals().get("validate_document_term_authority")
            is not document_term_authority_validator
        ):
            raise ValueError("instrument candidate document-term gate binding changed")
        if (
            globals().get("current_document_terms_as_of")
            is not current_document_terms_selector
        ):
            raise ValueError("instrument candidate current document-term binding changed")
        policy_validator()
        return compiler_core(
            document_term_observations,
            source_manifests=source_manifests,
            source_reader=source_reader,
            existing_candidate_terms=existing_candidate_terms,
            generated_at=generated_at,
            source_as_of=source_as_of,
            document_term_authority_validator=document_term_authority_validator,
            current_document_terms_selector=current_document_terms_selector,
        )

    return compile_candidate_term_records


def _candidate_authority_entrypoints() -> tuple[SemanticEntrypoint, ...]:
    return (
        SemanticEntrypoint(
            "closed_candidate_contract", _validate_candidate_term_records_contract,
        ),
        SemanticEntrypoint("source_binding", _validate_candidate_source_binding_core),
        SemanticEntrypoint("structure", _validate_candidate_term_structure),
        SemanticEntrypoint("history", _validate_candidate_term_history_core),
        SemanticEntrypoint("current_as_of", _current_candidate_terms_as_of_core),
        SemanticEntrypoint(
            "document_authority", _validate_document_term_authority_core,
        ),
        SemanticEntrypoint("compiler", _compile_candidate_term_records_core),
    )


# Release goldens are filled only when an intentional candidate authority
# implementation or closed-schema change is reviewed.
_CANDIDATE_AUTHORITY_DEPENDENCY_COUNT = 194
_CANDIDATE_AUTHORITY_DEPENDENCY_MANIFEST_SHA256 = (
    "5c93c5790e103ebc82f9e7865e27bb9576370235ddd27c64ff57a84fbc1bb9eb"
)
_CANDIDATE_AUTHORITY_IMPLEMENTATION_SHA256 = (
    "7adefd79136224d8c0ca0c84cd4ef41bd206690f9ec28622cdf95f682c811b28"
)
_CANDIDATE_AUTHORITY_ENTRYPOINTS = _candidate_authority_entrypoints()
_CANDIDATE_AUTHORITY_ALIAS_BINDINGS = (
    (
        "_validate_candidate_term_records_contract",
        _validate_candidate_term_records_contract,
    ),
    ("_validate_candidate_source_binding_core", _validate_candidate_source_binding_core),
    ("_validate_candidate_term_structure", _validate_candidate_term_structure),
    ("_validate_candidate_term_history_core", _validate_candidate_term_history_core),
    ("_current_candidate_terms_as_of_core", _current_candidate_terms_as_of_core),
    ("_validate_document_term_authority_core", _validate_document_term_authority_core),
    ("_compile_candidate_term_records_core", _compile_candidate_term_records_core),
)


def _make_validated_candidate_authority_policy(
    entrypoints: tuple[SemanticEntrypoint, ...],
    alias_bindings: tuple[tuple[str, Callable[..., Any]], ...],
    dependency_count: int,
    dependency_manifest_sha256: str,
    implementation_sha256: str,
    semantic_closure: Callable[..., tuple[tuple[str, ...], str, str]],
    digest_comparator: Callable[[str, str], bool],
) -> Callable[[], None]:
    """Seal candidate trust roots and revalidate their closure on every use."""
    def _validated_candidate_authority_policy() -> None:
        if globals().get("_semantic_closure") is not semantic_closure:
            raise ValueError("instrument candidate semantic-closure binding changed")
        for name, expected in alias_bindings:
            if globals().get(name) is not expected:
                raise ValueError(
                    f"instrument candidate authority policy binding changed: {name}"
                )
        try:
            manifest, manifest_sha256, digest = semantic_closure(entrypoints)
        except ValueError as exc:
            raise ValueError("instrument candidate authority closure mismatch") from exc
        if (
            len(manifest) != dependency_count
            or not digest_comparator(
                manifest_sha256, dependency_manifest_sha256,
            )
            or not digest_comparator(digest, implementation_sha256)
        ):
            raise ValueError("instrument candidate authority closure mismatch")

    return _validated_candidate_authority_policy


_validated_candidate_authority_policy = _make_validated_candidate_authority_policy(
    _CANDIDATE_AUTHORITY_ENTRYPOINTS,
    _CANDIDATE_AUTHORITY_ALIAS_BINDINGS,
    _CANDIDATE_AUTHORITY_DEPENDENCY_COUNT,
    _CANDIDATE_AUTHORITY_DEPENDENCY_MANIFEST_SHA256,
    _CANDIDATE_AUTHORITY_IMPLEMENTATION_SHA256,
    _semantic_closure,
    hmac.compare_digest,
)

validate_candidate_source_binding = _make_validate_candidate_source_binding(
    _validated_candidate_authority_policy,
    _validate_candidate_source_binding_core,
    _validate_candidate_term_records_contract,
    _RELEASED_DOCUMENT_TERM_CONTRACT,
)
validate_candidate_term_structure = _make_validate_candidate_term_structure(
    _validated_candidate_authority_policy,
    _validate_candidate_term_structure,
)
validate_document_term_authority = _make_validate_document_term_authority(
    _validated_candidate_authority_policy,
    _validate_document_term_authority_core,
    _RELEASED_DOCUMENT_TERM_SOURCE_AUTHORITY,
)
validate_candidate_term_history = _make_validate_candidate_term_history(
    _validated_candidate_authority_policy,
    _validate_candidate_term_history_core,
    validate_document_term_authority,
)
current_candidate_terms_as_of = _make_current_candidate_terms_as_of(
    _validated_candidate_authority_policy,
    _current_candidate_terms_as_of_core,
    validate_candidate_term_history,
)
compile_candidate_term_records = _make_compile_candidate_term_records(
    _validated_candidate_authority_policy,
    _compile_candidate_term_records_core,
    validate_document_term_authority,
    _RELEASED_CURRENT_DOCUMENT_TERMS_AS_OF,
)


def _self_check_candidate_authority_policy() -> None:
    try:
        _validated_candidate_authority_policy()
    except ValueError as exc:
        raise RuntimeError(
            "instrument candidate authority policy startup self-check failed"
        ) from exc


_self_check_candidate_authority_policy()
