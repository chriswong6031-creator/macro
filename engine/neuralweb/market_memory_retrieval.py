"""Pure W4A synthetic supplied-candidate episodic retrieval conformance.

This module is deliberately inert.  It validates already-built W2A objects,
computes one preregistered normalized Euclidean distance over caller-supplied
synthetic coordinates, and records a deterministic purge/embargo audit over a
caller-supplied candidate list.  It does not discover candidates, project
coordinates, fit normalization, estimate effective sample size, read or write
a store, expose a service, or grant any forecasting or trading authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from types import MappingProxyType
from typing import Any, Final, NoReturn

from engine.neuralweb import market_memory_forward as forward

RETRIEVAL_REGISTRATION_SCHEMA = "market_memory.retrieval_registration.v1"
EPISODIC_RETRIEVAL_RECORD_SCHEMA = "market_memory.episodic_retrieval_record.v1"
INPUT_PROFILE: Final = "synthetic_fixture_only"
NUMERIC_CONVENTION: Final = "decimal64_half_even_q18/v1"

CLAIMS: Mapping[str, bool] = MappingProxyType(
    {
        "operational_seal_authenticated": False,
        "coordinate_projection_authenticated": False,
        "normalization_fit_authenticated": False,
        "opportunity_population_complete": False,
        "candidate_population_complete": False,
        "statistical_effective_n_estimated": False,
        "interval_coverage_measured": False,
        "retrieval_quality_evaluated": False,
        "forecast_input_eligible": False,
        "aggregate_eligible": False,
        "skill_claim_eligible": False,
    }
)

_MAX_REGISTRATION_BYTES = 256 * 1024
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_CONTEXT_DEPENDENCY_BYTES = 16 * 1024 * 1024
_MAX_COORDINATES = 32
_MAX_CANDIDATES = 128
_MAX_RESULTS = 32
_MAX_ABSOLUTE_DECIMAL = Decimal(1000000000000000)
_DECIMAL_CONTEXT = Context(
    prec=64,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
)
_QUANTUM = Decimal("0.000000000000000001")

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_OPAQUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_Q18 = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{18}\Z")
_POSITIVE_Q18 = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{18}\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_REGISTRATION_ID = re.compile(r"mmretrievalregistration_[a-f0-9]{64}\Z")
_RECORD_ID = re.compile(r"mmepisodicretrieval_[a-f0-9]{64}\Z")

_REGISTRATION_FIELDS = frozenset(
    {
        "schema",
        "retrieval_registration_id",
        "registration_key",
        "registered_at",
        "trial_registration_id",
        "trial_plan_sha256",
        "coordinate_specs",
        "distance",
        "temporal_policy",
        "maximum_results",
        "implementation",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_COORDINATE_SPEC_FIELDS = frozenset(
    {"coordinate_id", "unit", "transform_version", "scale_decimal"}
)
_DISTANCE_FIELDS = frozenset(
    {"formula", "formula_version", "numeric_convention", "normalization", "missingness"}
)
_TEMPORAL_FIELDS = frozenset(
    {
        "subject_scope",
        "self_exclusion",
        "candidate_time_rule",
        "purge_before_seconds",
        "purge_after_seconds",
        "embargo_duration_seconds",
        "interval_convention",
        "query_overlap_policy",
        "selection_overlap_policy",
        "tie_breaker",
    }
)
_IMPLEMENTATION_FIELDS = frozenset({"producer_code_sha256", "producer_config_sha256"})
_CLAIM_FIELDS = frozenset(CLAIMS)

_RECORD_FIELDS = frozenset(
    {
        "schema",
        "episodic_retrieval_record_id",
        "retrieval_registration_id",
        "trial_registration_id",
        "trial_plan_sha256",
        "query",
        "retrieved_at",
        "retrieval_disposition",
        "retrieval_reason",
        "candidates",
        "selected_forecast_ids",
        "effective_n",
        "counts",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_QUERY_FIELDS = frozenset(
    {
        "forecast_id",
        "forecast_key",
        "state_snapshot_id",
        "context_id",
        "subject",
        "decision_cutoff",
        "sealed_at",
        "horizon_start",
        "horizon_end",
        "forecast_disposition",
        "coordinates",
    }
)
_SUBJECT_FIELDS = frozenset({"subject_id", "instrument_id"})
_COORDINATE_FIELDS = frozenset({"coordinate_id", "value_decimal"})
_CANDIDATE_FIELDS = frozenset(
    {
        "forecast_id",
        "forecast_key",
        "state_snapshot_id",
        "context_id",
        "subject",
        "decision_cutoff",
        "sealed_at",
        "horizon_start",
        "horizon_end",
        "forecast_disposition",
        "coordinates",
        "distance_value",
        "distance_rank",
        "selection_rank",
        "disposition",
        "reason",
        "overlap_with_forecast_ids",
    }
)
_EFFECTIVE_N_FIELDS = frozenset({"status", "value", "reason"})
_COUNTS_FIELDS = frozenset(
    {
        "supplied_candidates",
        "distance_eligible_candidates",
        "selected_nonoverlapping_candidates",
    }
)
_CANDIDATE_INPUT_FIELDS = frozenset(
    {"state_snapshot", "forecast_record", "exact_context_bytes", "coordinates"}
)

_DISTANCE = MappingProxyType(
    {
        "formula": "exact_normalized_euclidean",
        "formula_version": "exact_normalized_euclidean.v1",
        "numeric_convention": NUMERIC_CONVENTION,
        "normalization": "synthetic_fixed_positive_scales",
        "missingness": "complete_case_no_repair",
    }
)


class MarketMemoryRetrievalContractError(ValueError):
    """A W4A supplied-candidate retrieval value is unsafe or ambiguous."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryRetrievalContractError(message)


def _forward_error(exc: Exception, *, field: str) -> NoReturn:
    raise MarketMemoryRetrievalContractError(
        f"{field} fails its W2A owner: {exc}"
    ) from exc


def _require_dict(value: object, *, field: str) -> dict[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail(f"{field} must be a plain JSON object with string keys")
    return value


def _require_fields(
    value: object, fields: frozenset[str], *, field: str
) -> dict[str, Any]:
    payload = _require_dict(value, field=field)
    if set(payload) != fields:
        missing = sorted(fields - set(payload))
        extra = sorted(set(payload) - fields)
        _fail(f"{field} fields are not canonical; missing={missing}, extra={extra}")
    return payload


def _canonical_bytes(value: object, *, field: str, maximum: int) -> bytes:
    try:
        body = forward.canonical_json_bytes(value)
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field=field)
    if len(body) > maximum:
        _fail(f"{field} exceeds its canonical byte bound")
    return body


def _detached(value: object, *, field: str, maximum: int) -> dict[str, Any]:
    return _require_dict(
        json.loads(_canonical_bytes(value, field=field, maximum=maximum)), field=field
    )


def _exact_equal(left: object, right: object, *, field: str, maximum: int) -> bool:
    return _canonical_bytes(
        left, field=f"{field} supplied", maximum=maximum
    ) == _canonical_bytes(right, field=f"{field} expected", maximum=maximum)


def _content_id(
    prefix: str, value: Mapping[str, Any], *, field: str, maximum: int
) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(core, field=f"{field} preimage", maximum=maximum)
        ).hexdigest()
    )


def _match(value: object, pattern: re.Pattern[str], *, field: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(f"{field} is not canonical")
    return value


def _opaque(value: object, *, field: str) -> str:
    return _match(value, _OPAQUE, field=field)


def _sha256(value: object, *, field: str) -> str:
    return _match(value, _SHA256, field=field)


def _exact_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


def _utc(value: object, *, field: str) -> datetime:
    if type(value) is not str or _UTC_TIMESTAMP.fullmatch(value) is None:
        _fail(f"{field} must be a canonical UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise MarketMemoryRetrievalContractError(f"{field} is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        _fail(f"{field} is not a real canonical UTC timestamp")
    return parsed


def _trial(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return forward.validate_trial_registration(value)
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field="trial_registration")


def _plan_sha(trial: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_bytes(trial, field="trial plan", maximum=_MAX_REGISTRATION_BYTES)
    ).hexdigest()


def _authority(value: object) -> dict[str, Any]:
    expected = dict(forward.AUTHORITY)
    if not _exact_equal(
        value, expected, field="authority", maximum=_MAX_REGISTRATION_BYTES
    ):
        _fail("authority must equal the frozen W2A zero-authority block")
    return expected


def _claims(value: object) -> dict[str, bool]:
    payload = _require_fields(value, _CLAIM_FIELDS, field="claims")
    expected = dict(CLAIMS)
    if payload != expected:
        _fail("all W4A evidence claims must remain false")
    return expected


def _q18(value: object, *, field: str, positive: bool = False) -> tuple[str, Decimal]:
    pattern = _POSITIVE_Q18 if positive else _Q18
    text = _match(value, pattern, field=field)
    if text.startswith("-0.") and Decimal(text).is_zero():
        _fail(f"{field} must normalize negative zero")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise MarketMemoryRetrievalContractError(f"{field} is invalid decimal") from exc
    if not number.is_finite() or abs(number) > _MAX_ABSOLUTE_DECIMAL:
        _fail(f"{field} exceeds the finite decimal bound")
    if positive and number <= 0:
        _fail(f"{field} must be positive")
    return text, number


def _decimal_text(value: Decimal, *, field: str) -> str:
    try:
        with localcontext(_DECIMAL_CONTEXT):
            rounded = value.quantize(_QUANTUM)
    except InvalidOperation as exc:
        raise MarketMemoryRetrievalContractError(
            f"{field} cannot be represented as q18"
        ) from exc
    if rounded.is_zero():
        rounded = Decimal(0).quantize(_QUANTUM)
    text = format(rounded, "f")
    _q18(text, field=field)
    return text


def _coordinate_specs(value: object) -> list[dict[str, str]]:
    if type(value) is not list or not 1 <= len(value) <= _MAX_COORDINATES:
        _fail("coordinate_specs must contain 1..32 rows")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(value):
        row = _require_fields(
            item, _COORDINATE_SPEC_FIELDS, field=f"coordinate_specs[{index}]"
        )
        scale, _ = _q18(
            row["scale_decimal"],
            field=f"coordinate_specs[{index}].scale_decimal",
            positive=True,
        )
        rows.append(
            {
                "coordinate_id": _opaque(
                    row["coordinate_id"],
                    field=f"coordinate_specs[{index}].coordinate_id",
                ),
                "unit": _opaque(row["unit"], field=f"coordinate_specs[{index}].unit"),
                "transform_version": _opaque(
                    row["transform_version"],
                    field=f"coordinate_specs[{index}].transform_version",
                ),
                "scale_decimal": scale,
            }
        )
    ids = [row["coordinate_id"] for row in rows]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        _fail("coordinate_specs must be sorted by unique coordinate_id")
    return rows


def _distance(value: object) -> dict[str, str]:
    payload = _require_fields(value, _DISTANCE_FIELDS, field="distance")
    if payload != dict(_DISTANCE):
        _fail("distance policy differs from the frozen W4A formula")
    return dict(_DISTANCE)


def _temporal_policy(trial: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "subject_scope": "exact_subject_and_instrument",
        "self_exclusion": "forecast_id_or_context_id",
        "candidate_time_rule": "strictly_earlier_decision_cutoff",
        "purge_before_seconds": trial["purge"]["before_seconds"],
        "purge_after_seconds": trial["purge"]["after_seconds"],
        "embargo_duration_seconds": trial["embargo"]["duration_seconds"],
        "interval_convention": "[decision_cutoff-purge.after_seconds,decision_cutoff+purge.before_seconds+embargo.duration_seconds)",
        "query_overlap_policy": "exclude",
        "selection_overlap_policy": "greedy_exclude",
        "tie_breaker": "distance_then_forecast_id",
    }


def _implementation(value: object) -> dict[str, str]:
    payload = _require_fields(value, _IMPLEMENTATION_FIELDS, field="implementation")
    return {
        "producer_code_sha256": _sha256(
            payload["producer_code_sha256"], field="producer_code_sha256"
        ),
        "producer_config_sha256": _sha256(
            payload["producer_config_sha256"], field="producer_config_sha256"
        ),
    }


def build_retrieval_registration(
    *,
    trial_registration: Mapping[str, Any],
    registration_key: str,
    registered_at: str,
    coordinate_specs: Sequence[Mapping[str, Any]],
    maximum_results: int,
    producer_code_sha256: str,
    producer_config_sha256: str,
) -> dict[str, Any]:
    """Build an inert synthetic registration for supplied-candidate retrieval."""

    trial = _trial(trial_registration)
    if type(coordinate_specs) not in {list, tuple}:
        _fail("coordinate_specs must be a list or tuple")
    clean_specs = _coordinate_specs(
        [dict(row) if type(row) is dict else row for row in coordinate_specs]
    )
    payload: dict[str, Any] = {
        "schema": RETRIEVAL_REGISTRATION_SCHEMA,
        "retrieval_registration_id": "",
        "registration_key": registration_key,
        "registered_at": registered_at,
        "trial_registration_id": trial["trial_registration_id"],
        "trial_plan_sha256": _plan_sha(trial),
        "coordinate_specs": clean_specs,
        "distance": dict(_DISTANCE),
        "temporal_policy": _temporal_policy(trial),
        "maximum_results": maximum_results,
        "implementation": {
            "producer_code_sha256": producer_code_sha256,
            "producer_config_sha256": producer_config_sha256,
        },
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }
    payload["retrieval_registration_id"] = _content_id(
        "mmretrievalregistration_",
        payload,
        field="retrieval_registration_id",
        maximum=_MAX_REGISTRATION_BYTES,
    )
    return validate_retrieval_registration_join(payload, trial_registration=trial)


def validate_retrieval_registration_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a self-authenticating W4A registration without its W2A join."""

    payload = _require_fields(
        value, _REGISTRATION_FIELDS, field="retrieval_registration"
    )
    _canonical_bytes(
        payload, field="retrieval_registration", maximum=_MAX_REGISTRATION_BYTES
    )
    if payload["schema"] != RETRIEVAL_REGISTRATION_SCHEMA:
        _fail("retrieval registration schema drift")
    registration_id = _match(
        payload["retrieval_registration_id"],
        _REGISTRATION_ID,
        field="retrieval_registration_id",
    )
    registered = _utc(payload["registered_at"], field="registered_at")
    clean: dict[str, Any] = {
        "schema": RETRIEVAL_REGISTRATION_SCHEMA,
        "retrieval_registration_id": registration_id,
        "registration_key": _opaque(
            payload["registration_key"], field="registration_key"
        ),
        "registered_at": registered.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "trial_registration_id": _match(
            payload["trial_registration_id"],
            re.compile(r"mmtrial_[a-f0-9]{64}\Z"),
            field="trial_registration_id",
        ),
        "trial_plan_sha256": _sha256(
            payload["trial_plan_sha256"], field="trial_plan_sha256"
        ),
        "coordinate_specs": _coordinate_specs(payload["coordinate_specs"]),
        "distance": _distance(payload["distance"]),
        "temporal_policy": _require_fields(
            payload["temporal_policy"], _TEMPORAL_FIELDS, field="temporal_policy"
        ),
        "maximum_results": _exact_int(
            payload["maximum_results"],
            field="maximum_results",
            minimum=1,
            maximum=_MAX_RESULTS,
        ),
        "implementation": _implementation(payload["implementation"]),
        "input_profile": payload["input_profile"],
        "claims": _claims(payload["claims"]),
        "emission_enabled": payload["emission_enabled"],
        "authority": _authority(payload["authority"]),
    }
    if clean["input_profile"] != INPUT_PROFILE:
        _fail("retrieval input_profile must remain synthetic_fixture_only")
    if clean["emission_enabled"] is not False:
        _fail("retrieval emission must remain disabled")
    temporal = clean["temporal_policy"]
    for name in (
        "purge_before_seconds",
        "purge_after_seconds",
        "embargo_duration_seconds",
    ):
        _exact_int(
            temporal[name],
            field=f"temporal_policy.{name}",
            minimum=0 if name != "embargo_duration_seconds" else 1,
            maximum=1_000_000_000,
        )
    fixed_temporal = {
        "subject_scope": "exact_subject_and_instrument",
        "self_exclusion": "forecast_id_or_context_id",
        "candidate_time_rule": "strictly_earlier_decision_cutoff",
        "purge_before_seconds": temporal["purge_before_seconds"],
        "purge_after_seconds": temporal["purge_after_seconds"],
        "embargo_duration_seconds": temporal["embargo_duration_seconds"],
        "interval_convention": "[decision_cutoff-purge.after_seconds,decision_cutoff+purge.before_seconds+embargo.duration_seconds)",
        "query_overlap_policy": "exclude",
        "selection_overlap_policy": "greedy_exclude",
        "tie_breaker": "distance_then_forecast_id",
    }
    if temporal != fixed_temporal:
        _fail("temporal policy differs from the frozen W4A audit")
    clean["temporal_policy"] = fixed_temporal
    if not _exact_equal(
        payload, clean, field="retrieval_registration", maximum=_MAX_REGISTRATION_BYTES
    ):
        _fail("retrieval registration is not exact canonical JSON")
    expected_id = _content_id(
        "mmretrievalregistration_",
        clean,
        field="retrieval_registration_id",
        maximum=_MAX_REGISTRATION_BYTES,
    )
    if registration_id != expected_id:
        _fail("retrieval_registration_id does not bind canonical content")
    return _detached(
        clean, field="retrieval_registration", maximum=_MAX_REGISTRATION_BYTES
    )


def validate_retrieval_registration_join(
    value: Mapping[str, Any], *, trial_registration: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind a registration to the exact W2A trial and its temporal controls."""

    clean = validate_retrieval_registration_record(value)
    trial = _trial(trial_registration)
    if clean["trial_registration_id"] != trial["trial_registration_id"]:
        _fail("retrieval registration trial id differs from exact W2A trial")
    if clean["trial_plan_sha256"] != _plan_sha(trial):
        _fail("retrieval registration trial hash differs from exact W2A trial")
    if clean["temporal_policy"] != _temporal_policy(trial):
        _fail("retrieval temporal policy differs from exact W2A purge and embargo")
    registered = _utc(clean["registered_at"], field="registered_at")
    trial_registered = _utc(trial["registered_at"], field="trial.registered_at")
    live_start = _utc(
        trial["splits"]["live_forward_start"], field="trial.live_forward_start"
    )
    if not trial_registered <= registered < live_start:
        _fail(
            "retrieval registration must be frozen after the trial and before live forward"
        )
    return clean


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _strict_json_object(body: bytes, *, field: str, maximum: int) -> dict[str, Any]:
    if type(body) is not bytes or not body or len(body) > maximum:
        _fail(f"{field} body is empty or exceeds its byte bound")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarketMemoryRetrievalContractError(f"{field} is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_constant=lambda token: _fail(f"{field} contains non-finite {token}"),
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MarketMemoryRetrievalContractError(f"{field} is not strict JSON") from exc
    return _require_dict(value, field=field)


def load_retrieval_registration_join_json(
    body: bytes, *, trial_registration: Mapping[str, Any]
) -> dict[str, Any]:
    """Strictly load and rejoin one W4A registration."""

    return validate_retrieval_registration_join(
        _strict_json_object(
            body, field="retrieval_registration", maximum=_MAX_REGISTRATION_BYTES
        ),
        trial_registration=trial_registration,
    )


def _coordinate_rows(
    value: object,
    *,
    specs: Sequence[Mapping[str, Any]],
    field: str,
) -> tuple[list[dict[str, str | None]], bool]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail(f"{field} must be a plain coordinate_id mapping")
    expected_ids = [row["coordinate_id"] for row in specs]
    if set(value) != set(expected_ids):
        _fail(f"{field} must contain every and only registered coordinate_id")
    rows: list[dict[str, str | None]] = []
    complete = True
    for coordinate_id in expected_ids:
        raw = value[coordinate_id]
        if raw is None:
            clean_value = None
            complete = False
        else:
            clean_value, _ = _q18(raw, field=f"{field}.{coordinate_id}")
        rows.append({"coordinate_id": coordinate_id, "value_decimal": clean_value})
    return rows, complete


def _coordinate_mapping(
    value: object, *, specs: Sequence[Mapping[str, Any]], field: str
) -> dict[str, str | None]:
    if type(value) is not list or len(value) != len(specs):
        _fail(f"{field} must contain the registered coordinate rows")
    result: dict[str, str | None] = {}
    for index, item in enumerate(value):
        row = _require_fields(item, _COORDINATE_FIELDS, field=f"{field}[{index}]")
        expected_id = specs[index]["coordinate_id"]
        if row["coordinate_id"] != expected_id:
            _fail(f"{field} rows must follow registration order")
        raw = row["value_decimal"]
        if raw is not None:
            raw, _ = _q18(raw, field=f"{field}[{index}].value_decimal")
        result[expected_id] = raw
    return result


def score_normalized_euclidean(
    *,
    retrieval_registration: Mapping[str, Any],
    query_coordinates: Mapping[str, str | None],
    candidate_coordinates: Mapping[str, str | None],
) -> str | None:
    """Compute exact fixed-scale Euclidean distance, or ``None`` if incomplete."""

    registration = validate_retrieval_registration_record(retrieval_registration)
    specs = registration["coordinate_specs"]
    query_rows, query_complete = _coordinate_rows(
        query_coordinates, specs=specs, field="query_coordinates"
    )
    candidate_rows, candidate_complete = _coordinate_rows(
        candidate_coordinates, specs=specs, field="candidate_coordinates"
    )
    if not query_complete or not candidate_complete:
        return None
    try:
        with localcontext(_DECIMAL_CONTEXT):
            total = Decimal(0)
            for spec, query_row, candidate_row in zip(
                specs, query_rows, candidate_rows, strict=True
            ):
                assert query_row["value_decimal"] is not None
                assert candidate_row["value_decimal"] is not None
                query = Decimal(query_row["value_decimal"])
                candidate = Decimal(candidate_row["value_decimal"])
                scale = Decimal(spec["scale_decimal"])
                normalized = (query - candidate) / scale
                total += normalized * normalized
            distance = total.sqrt()
    except (InvalidOperation, OverflowError) as exc:
        raise MarketMemoryRetrievalContractError(
            "distance is outside the fixed Decimal64 domain"
        ) from exc
    if not distance.is_finite() or distance > _MAX_ABSOLUTE_DECIMAL:
        _fail("distance exceeds the finite decimal bound")
    return _decimal_text(distance, field="distance")


def _subject(exact_context_bytes: bytes, *, field: str) -> dict[str, str]:
    try:
        packet = json.loads(exact_context_bytes)
    except (TypeError, ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise MarketMemoryRetrievalContractError(
            f"{field} is not exact context JSON"
        ) from exc
    payload = _require_fields(
        packet.get("subject") if type(packet) is dict else None,
        _SUBJECT_FIELDS,
        field=f"{field}.subject",
    )
    return {
        "subject_id": _opaque(payload["subject_id"], field=f"{field}.subject_id"),
        "instrument_id": _opaque(
            payload["instrument_id"], field=f"{field}.instrument_id"
        ),
    }


def _joined_forecast(
    *,
    trial: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
    field: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    if type(exact_context_bytes) is not bytes:
        _fail(f"{field}.exact_context_bytes must be bytes")
    try:
        state = forward.validate_state_snapshot(
            state_snapshot, exact_context_bytes=exact_context_bytes
        )
        forecast = forward.validate_forecast_record_join(
            forecast_record,
            trial_registration=trial,
            state_snapshot=state,
            exact_context_bytes=exact_context_bytes,
        )
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field=field)
    return (
        state,
        forecast,
        _subject(exact_context_bytes, field=f"{field}.exact_context_bytes"),
    )


def _interval(decision: str, temporal: Mapping[str, Any]) -> tuple[datetime, datetime]:
    anchor = _utc(decision, field="decision_cutoff")
    try:
        return (
            anchor - timedelta(seconds=temporal["purge_after_seconds"]),
            anchor
            + timedelta(
                seconds=temporal["purge_before_seconds"]
                + temporal["embargo_duration_seconds"]
            ),
        )
    except OverflowError as exc:
        raise MarketMemoryRetrievalContractError(
            "purge and embargo interval exceeds the UTC timestamp domain"
        ) from exc


def _overlap(left: tuple[datetime, datetime], right: tuple[datetime, datetime]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _query_row(
    forecast: Mapping[str, Any],
    subject: Mapping[str, str],
    coordinates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "forecast_id": forecast["forecast_id"],
        "forecast_key": forecast["forecast_key"],
        "state_snapshot_id": forecast["state_snapshot_id"],
        "context_id": forecast["context_id"],
        "subject": dict(subject),
        "decision_cutoff": forecast["decision_cutoff"],
        "sealed_at": forecast["sealed_at"],
        "horizon_start": forecast["horizon_start"],
        "horizon_end": forecast["horizon_end"],
        "forecast_disposition": forecast["disposition"],
        "coordinates": coordinates,
    }


def build_episodic_retrieval_record(
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
    retrieved_at: str,
) -> dict[str, Any]:
    """Audit and rank one bounded, explicitly supplied synthetic candidate list."""

    trial = _trial(trial_registration)
    registration = validate_retrieval_registration_join(
        retrieval_registration, trial_registration=trial
    )
    if (
        type(candidate_inputs) not in {list, tuple}
        or len(candidate_inputs) > _MAX_CANDIDATES
    ):
        _fail("candidate_inputs must be a sequence of at most 128 rows")
    total_context_bytes = (
        len(query_exact_context_bytes)
        if type(query_exact_context_bytes) is bytes
        else 0
    )
    for index, raw in enumerate(candidate_inputs):
        item = _require_fields(
            raw, _CANDIDATE_INPUT_FIELDS, field=f"candidate_inputs[{index}]"
        )
        if type(item["exact_context_bytes"]) is not bytes:
            _fail(f"candidate_inputs[{index}].exact_context_bytes must be bytes")
        total_context_bytes += len(item["exact_context_bytes"])
    if total_context_bytes > _MAX_CONTEXT_DEPENDENCY_BYTES:
        _fail("aggregate exact-context dependencies exceed 16 MiB")
    query_state, query_forecast, query_subject = _joined_forecast(
        trial=trial,
        state_snapshot=query_state_snapshot,
        forecast_record=query_forecast_record,
        exact_context_bytes=query_exact_context_bytes,
        field="query",
    )
    del query_state
    retrieved = _utc(retrieved_at, field="retrieved_at")
    if retrieved < _utc(query_forecast["sealed_at"], field="query.sealed_at"):
        _fail("retrieved_at must not precede the sealed query forecast")
    specs = registration["coordinate_specs"]
    query_coordinate_rows, query_complete = _coordinate_rows(
        query_coordinates, specs=specs, field="query_coordinates"
    )
    query_interval = _interval(
        query_forecast["decision_cutoff"], registration["temporal_policy"]
    )

    working: list[dict[str, Any]] = []
    seen_forecasts: set[str] = set()
    for index, raw in enumerate(candidate_inputs):
        item = _require_fields(
            raw, _CANDIDATE_INPUT_FIELDS, field=f"candidate_inputs[{index}]"
        )
        _, forecast, subject = _joined_forecast(
            trial=trial,
            state_snapshot=item["state_snapshot"],
            forecast_record=item["forecast_record"],
            exact_context_bytes=item["exact_context_bytes"],
            field=f"candidate_inputs[{index}]",
        )
        if forecast["forecast_id"] in seen_forecasts:
            _fail("candidate_inputs cannot repeat a forecast_id")
        seen_forecasts.add(forecast["forecast_id"])
        coordinate_rows, candidate_complete = _coordinate_rows(
            item["coordinates"],
            specs=specs,
            field=f"candidate_inputs[{index}].coordinates",
        )
        reason: str | None = None
        if not query_complete:
            reason = "query_coordinate_unavailable"
        elif forecast["forecast_id"] == query_forecast["forecast_id"]:
            reason = "self_forecast"
        elif forecast["context_id"] == query_forecast["context_id"]:
            reason = "self_context"
        elif subject != query_subject:
            reason = "subject_or_instrument_mismatch"
        elif _utc(
            forecast["decision_cutoff"], field="candidate.decision_cutoff"
        ) >= _utc(query_forecast["decision_cutoff"], field="query.decision_cutoff"):
            reason = "not_strictly_earlier"
        elif _overlap(
            _interval(forecast["decision_cutoff"], registration["temporal_policy"]),
            query_interval,
        ):
            reason = "query_interval_overlap"
        elif not candidate_complete:
            reason = "candidate_coordinate_unavailable"
        distance = None
        if reason is None:
            distance = score_normalized_euclidean(
                retrieval_registration=registration,
                query_coordinates=query_coordinates,
                candidate_coordinates=item["coordinates"],
            )
            assert distance is not None
        working.append(
            {
                "forecast_id": forecast["forecast_id"],
                "forecast_key": forecast["forecast_key"],
                "state_snapshot_id": forecast["state_snapshot_id"],
                "context_id": forecast["context_id"],
                "subject": subject,
                "decision_cutoff": forecast["decision_cutoff"],
                "sealed_at": forecast["sealed_at"],
                "horizon_start": forecast["horizon_start"],
                "horizon_end": forecast["horizon_end"],
                "forecast_disposition": forecast["disposition"],
                "coordinates": coordinate_rows,
                "distance_value": distance,
                "distance_rank": None,
                "selection_rank": None,
                "disposition": "ineligible"
                if reason is not None
                else "distance_eligible",
                "reason": reason,
                "overlap_with_forecast_ids": [],
            }
        )

    eligible = sorted(
        (row for row in working if row["disposition"] == "distance_eligible"),
        key=lambda row: (Decimal(row["distance_value"]), row["forecast_id"]),
    )
    selected: list[dict[str, Any]] = []
    for distance_rank, row in enumerate(eligible, start=1):
        row["distance_rank"] = distance_rank
        candidate_interval = _interval(
            row["decision_cutoff"], registration["temporal_policy"]
        )
        overlaps = [
            prior["forecast_id"]
            for prior in selected
            if _overlap(
                candidate_interval,
                _interval(prior["decision_cutoff"], registration["temporal_policy"]),
            )
        ]
        if overlaps:
            row["disposition"] = "not_selected"
            row["reason"] = "selection_interval_overlap"
            row["overlap_with_forecast_ids"] = overlaps
        elif len(selected) >= registration["maximum_results"]:
            row["disposition"] = "not_selected"
            row["reason"] = "maximum_results_reached"
        else:
            row["disposition"] = "selected"
            row["selection_rank"] = len(selected) + 1
            selected.append(row)

    payload: dict[str, Any] = {
        "schema": EPISODIC_RETRIEVAL_RECORD_SCHEMA,
        "episodic_retrieval_record_id": "",
        "retrieval_registration_id": registration["retrieval_registration_id"],
        "trial_registration_id": trial["trial_registration_id"],
        "trial_plan_sha256": _plan_sha(trial),
        "query": _query_row(query_forecast, query_subject, query_coordinate_rows),
        "retrieved_at": retrieved_at,
        "retrieval_disposition": "completed" if query_complete else "abstained",
        "retrieval_reason": None if query_complete else "query_coordinate_unavailable",
        "candidates": sorted(working, key=lambda row: row["forecast_id"]),
        "selected_forecast_ids": [row["forecast_id"] for row in selected],
        "effective_n": {
            "status": "not_estimated",
            "value": None,
            "reason": "dependence_model_not_evidence_ready",
        },
        "counts": {
            "supplied_candidates": len(working),
            "distance_eligible_candidates": len(eligible),
            "selected_nonoverlapping_candidates": len(selected),
        },
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }
    payload["episodic_retrieval_record_id"] = _content_id(
        "mmepisodicretrieval_",
        payload,
        field="episodic_retrieval_record_id",
        maximum=_MAX_RECORD_BYTES,
    )
    return validate_episodic_retrieval_record(payload)


def _subject_record(value: object, *, field: str) -> dict[str, str]:
    payload = _require_fields(value, _SUBJECT_FIELDS, field=field)
    return {
        "subject_id": _opaque(payload["subject_id"], field=f"{field}.subject_id"),
        "instrument_id": _opaque(
            payload["instrument_id"], field=f"{field}.instrument_id"
        ),
    }


def _query_record(
    value: object, *, specs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    payload = _require_fields(value, _QUERY_FIELDS, field="query")
    coordinates = _coordinate_mapping(
        payload["coordinates"], specs=specs, field="query.coordinates"
    )
    return {
        "forecast_id": _match(
            payload["forecast_id"],
            re.compile(r"mmforecast_[a-f0-9]{64}\Z"),
            field="query.forecast_id",
        ),
        "forecast_key": _match(
            payload["forecast_key"],
            re.compile(r"mmforecastkey_[a-f0-9]{64}\Z"),
            field="query.forecast_key",
        ),
        "state_snapshot_id": _match(
            payload["state_snapshot_id"],
            re.compile(r"mmstate_[a-f0-9]{64}\Z"),
            field="query.state_snapshot_id",
        ),
        "context_id": _match(
            payload["context_id"],
            re.compile(r"mmctx_[a-f0-9]{64}\Z"),
            field="query.context_id",
        ),
        "subject": _subject_record(payload["subject"], field="query.subject"),
        "decision_cutoff": _utc(
            payload["decision_cutoff"], field="query.decision_cutoff"
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "sealed_at": _utc(payload["sealed_at"], field="query.sealed_at").strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "horizon_start": _utc(
            payload["horizon_start"], field="query.horizon_start"
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "horizon_end": _utc(payload["horizon_end"], field="query.horizon_end").strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "forecast_disposition": payload["forecast_disposition"],
        "coordinates": [
            {"coordinate_id": key, "value_decimal": value}
            for key, value in coordinates.items()
        ],
    }


def _candidate_record(
    value: object, *, specs: Sequence[Mapping[str, Any]], index: int
) -> dict[str, Any]:
    field = f"candidates[{index}]"
    payload = _require_fields(value, _CANDIDATE_FIELDS, field=field)
    coordinates = _coordinate_mapping(
        payload["coordinates"], specs=specs, field=f"{field}.coordinates"
    )
    disposition = payload["disposition"]
    reason = payload["reason"]
    allowed = {
        "ineligible": {
            "query_coordinate_unavailable",
            "self_forecast",
            "self_context",
            "subject_or_instrument_mismatch",
            "not_strictly_earlier",
            "query_interval_overlap",
            "candidate_coordinate_unavailable",
        },
        "not_selected": {"selection_interval_overlap", "maximum_results_reached"},
        "selected": {None},
    }
    if disposition not in allowed or reason not in allowed[disposition]:
        _fail(f"{field} disposition and reason are inconsistent")
    distance = payload["distance_value"]
    distance_rank = payload["distance_rank"]
    selection_rank = payload["selection_rank"]
    overlaps = payload["overlap_with_forecast_ids"]
    if type(overlaps) is not list or len(overlaps) > _MAX_RESULTS:
        _fail(f"{field}.overlap_with_forecast_ids is invalid")
    clean_overlaps = [
        _match(item, re.compile(r"mmforecast_[a-f0-9]{64}\Z"), field=f"{field}.overlap")
        for item in overlaps
    ]
    if len(set(clean_overlaps)) != len(clean_overlaps):
        _fail(f"{field}.overlap_with_forecast_ids contains duplicates")
    if disposition == "ineligible":
        if (
            distance is not None
            or distance_rank is not None
            or selection_rank is not None
            or clean_overlaps
        ):
            _fail(f"{field} ineligible row carries ranking data")
    else:
        _, clean_distance = _q18(
            distance, field=f"{field}.distance_value", positive=False
        )
        if clean_distance < 0:
            _fail(f"{field}.distance_value must be nonnegative")
        _exact_int(
            distance_rank,
            field=f"{field}.distance_rank",
            minimum=1,
            maximum=_MAX_CANDIDATES,
        )
        if disposition == "selected":
            _exact_int(
                selection_rank,
                field=f"{field}.selection_rank",
                minimum=1,
                maximum=_MAX_RESULTS,
            )
            if clean_overlaps:
                _fail(f"{field} selected row cannot carry overlaps")
        elif selection_rank is not None:
            _fail(f"{field} unselected row cannot have selection_rank")
        if reason == "selection_interval_overlap" and not clean_overlaps:
            _fail(f"{field} overlap rejection must cite selected forecasts")
        if reason == "maximum_results_reached" and clean_overlaps:
            _fail(f"{field} maximum rejection cannot cite overlaps")
    if payload["forecast_disposition"] not in {"issued", "abstained"}:
        _fail(f"{field}.forecast_disposition is invalid")
    return {
        "forecast_id": _match(
            payload["forecast_id"],
            re.compile(r"mmforecast_[a-f0-9]{64}\Z"),
            field=f"{field}.forecast_id",
        ),
        "forecast_key": _match(
            payload["forecast_key"],
            re.compile(r"mmforecastkey_[a-f0-9]{64}\Z"),
            field=f"{field}.forecast_key",
        ),
        "state_snapshot_id": _match(
            payload["state_snapshot_id"],
            re.compile(r"mmstate_[a-f0-9]{64}\Z"),
            field=f"{field}.state_snapshot_id",
        ),
        "context_id": _match(
            payload["context_id"],
            re.compile(r"mmctx_[a-f0-9]{64}\Z"),
            field=f"{field}.context_id",
        ),
        "subject": _subject_record(payload["subject"], field=f"{field}.subject"),
        "decision_cutoff": _utc(
            payload["decision_cutoff"], field=f"{field}.decision_cutoff"
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "sealed_at": _utc(payload["sealed_at"], field=f"{field}.sealed_at").strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "horizon_start": _utc(
            payload["horizon_start"], field=f"{field}.horizon_start"
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "horizon_end": _utc(
            payload["horizon_end"], field=f"{field}.horizon_end"
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "forecast_disposition": payload["forecast_disposition"],
        "coordinates": [
            {"coordinate_id": key, "value_decimal": value}
            for key, value in coordinates.items()
        ],
        "distance_value": distance,
        "distance_rank": distance_rank,
        "selection_rank": selection_rank,
        "disposition": disposition,
        "reason": reason,
        "overlap_with_forecast_ids": clean_overlaps,
    }


def validate_episodic_retrieval_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a self-authenticating W4A result and its internal audit."""

    payload = _require_fields(value, _RECORD_FIELDS, field="episodic_retrieval_record")
    _canonical_bytes(
        payload, field="episodic_retrieval_record", maximum=_MAX_RECORD_BYTES
    )
    if payload["schema"] != EPISODIC_RETRIEVAL_RECORD_SCHEMA:
        _fail("episodic retrieval record schema drift")
    record_id = _match(
        payload["episodic_retrieval_record_id"],
        _RECORD_ID,
        field="episodic_retrieval_record_id",
    )
    # The exact registration dependency is required for semantic validation; the
    # record stores its coordinate registration projection through the query.
    query_payload = _require_dict(payload["query"], field="query")
    raw_coordinates = query_payload.get("coordinates")
    if (
        type(raw_coordinates) is not list
        or not 1 <= len(raw_coordinates) <= _MAX_COORDINATES
    ):
        _fail("query.coordinates must contain 1..32 rows")
    synthetic_specs = []
    for index, item in enumerate(raw_coordinates):
        row = _require_fields(
            item, _COORDINATE_FIELDS, field=f"query.coordinates[{index}]"
        )
        synthetic_specs.append(
            {
                "coordinate_id": _opaque(
                    row["coordinate_id"],
                    field=f"query.coordinates[{index}].coordinate_id",
                )
            }
        )
    ids = [row["coordinate_id"] for row in synthetic_specs]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("query coordinate ids must be sorted and unique")
    query = _query_record(payload["query"], specs=synthetic_specs)
    candidates_raw = payload["candidates"]
    if type(candidates_raw) is not list or len(candidates_raw) > _MAX_CANDIDATES:
        _fail("candidates must contain at most 128 rows")
    candidates = [
        _candidate_record(item, specs=synthetic_specs, index=index)
        for index, item in enumerate(candidates_raw)
    ]
    forecast_ids = [row["forecast_id"] for row in candidates]
    if forecast_ids != sorted(forecast_ids) or len(forecast_ids) != len(
        set(forecast_ids)
    ):
        _fail("candidate rows must be sorted by unique forecast_id")
    selected_rows = sorted(
        (row for row in candidates if row["disposition"] == "selected"),
        key=lambda row: row["selection_rank"],
    )
    selected_ids = payload["selected_forecast_ids"]
    if type(selected_ids) is not list or selected_ids != [
        row["forecast_id"] for row in selected_rows
    ]:
        _fail("selected_forecast_ids must exactly project selection_rank order")
    distance_rows = sorted(
        (row for row in candidates if row["disposition"] != "ineligible"),
        key=lambda row: row["distance_rank"],
    )
    if [row["distance_rank"] for row in distance_rows] != list(
        range(1, len(distance_rows) + 1)
    ):
        _fail("distance ranks must be consecutive")
    if [row["selection_rank"] for row in selected_rows] != list(
        range(1, len(selected_rows) + 1)
    ):
        _fail("selection ranks must be consecutive")
    expected_distance_order = sorted(
        distance_rows,
        key=lambda row: (Decimal(row["distance_value"]), row["forecast_id"]),
    )
    if distance_rows != expected_distance_order:
        _fail("distance ranks must follow distance then forecast_id")
    if [row["distance_rank"] for row in selected_rows] != sorted(
        row["distance_rank"] for row in selected_rows
    ):
        _fail("selection ranks must preserve distance audit order")
    selected_by_id = {row["forecast_id"]: row for row in selected_rows}
    for row in candidates:
        for overlap_id in row["overlap_with_forecast_ids"]:
            prior = selected_by_id.get(overlap_id)
            if prior is None or prior["distance_rank"] >= row["distance_rank"]:
                _fail("overlap audit must cite an earlier selected forecast")
        if row["overlap_with_forecast_ids"] != sorted(
            row["overlap_with_forecast_ids"],
            key=lambda forecast_id: selected_by_id[forecast_id]["selection_rank"],
        ):
            _fail("overlap audit must follow selected forecast order")
    effective_n = _require_fields(
        payload["effective_n"], _EFFECTIVE_N_FIELDS, field="effective_n"
    )
    expected_effective_n = {
        "status": "not_estimated",
        "value": None,
        "reason": "dependence_model_not_evidence_ready",
    }
    if effective_n != expected_effective_n:
        _fail("effective_n must remain explicitly not estimated")
    counts = _require_fields(payload["counts"], _COUNTS_FIELDS, field="counts")
    expected_counts = {
        "supplied_candidates": len(candidates),
        "distance_eligible_candidates": len(distance_rows),
        "selected_nonoverlapping_candidates": len(selected_rows),
    }
    if counts != expected_counts:
        _fail("retrieval counts are not derived from candidate audit")
    disposition = payload["retrieval_disposition"]
    reason = payload["retrieval_reason"]
    query_complete = all(
        row["value_decimal"] is not None for row in query["coordinates"]
    )
    if (disposition, reason) != (
        ("completed", None)
        if query_complete
        else ("abstained", "query_coordinate_unavailable")
    ):
        _fail("retrieval disposition differs from query coordinate completeness")
    for row in candidates:
        candidate_complete = all(
            coordinate["value_decimal"] is not None for coordinate in row["coordinates"]
        )
        if not query_complete and not (
            row["disposition"] == "ineligible"
            and row["reason"] == "query_coordinate_unavailable"
        ):
            _fail("an unavailable query must abstain every supplied candidate")
        if query_complete and row["reason"] == "query_coordinate_unavailable":
            _fail("a complete query cannot claim unavailable query coordinates")
        if (
            query_complete
            and not candidate_complete
            and not (
                row["disposition"] == "ineligible"
                and row["reason"] == "candidate_coordinate_unavailable"
            )
        ):
            _fail("an incomplete candidate must remain distance-ineligible")
        if candidate_complete and row["reason"] == "candidate_coordinate_unavailable":
            _fail("a complete candidate cannot claim unavailable coordinates")
    clean: dict[str, Any] = {
        "schema": EPISODIC_RETRIEVAL_RECORD_SCHEMA,
        "episodic_retrieval_record_id": record_id,
        "retrieval_registration_id": _match(
            payload["retrieval_registration_id"],
            _REGISTRATION_ID,
            field="retrieval_registration_id",
        ),
        "trial_registration_id": _match(
            payload["trial_registration_id"],
            re.compile(r"mmtrial_[a-f0-9]{64}\Z"),
            field="trial_registration_id",
        ),
        "trial_plan_sha256": _sha256(
            payload["trial_plan_sha256"], field="trial_plan_sha256"
        ),
        "query": query,
        "retrieved_at": _utc(payload["retrieved_at"], field="retrieved_at").strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "retrieval_disposition": disposition,
        "retrieval_reason": reason,
        "candidates": candidates,
        "selected_forecast_ids": selected_ids,
        "effective_n": expected_effective_n,
        "counts": expected_counts,
        "input_profile": payload["input_profile"],
        "claims": _claims(payload["claims"]),
        "emission_enabled": payload["emission_enabled"],
        "authority": _authority(payload["authority"]),
    }
    if (
        clean["input_profile"] != INPUT_PROFILE
        or clean["emission_enabled"] is not False
    ):
        _fail("episodic retrieval must remain inert synthetic_fixture_only")
    if _utc(clean["retrieved_at"], field="retrieved_at") < _utc(
        query["sealed_at"], field="query.sealed_at"
    ):
        _fail("retrieved_at must not precede the sealed query forecast")
    if not _exact_equal(
        payload, clean, field="episodic_retrieval_record", maximum=_MAX_RECORD_BYTES
    ):
        _fail("episodic retrieval record is not exact canonical JSON")
    expected_id = _content_id(
        "mmepisodicretrieval_",
        clean,
        field="episodic_retrieval_record_id",
        maximum=_MAX_RECORD_BYTES,
    )
    if record_id != expected_id:
        _fail("episodic_retrieval_record_id does not bind canonical content")
    return _detached(
        clean, field="episodic_retrieval_record", maximum=_MAX_RECORD_BYTES
    )


def validate_episodic_retrieval_record_join(
    value: Mapping[str, Any],
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rebuild the pure audit from all exact dependencies and require identity."""

    clean = validate_episodic_retrieval_record(value)
    expected = build_episodic_retrieval_record(
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
        query_state_snapshot=query_state_snapshot,
        query_forecast_record=query_forecast_record,
        query_exact_context_bytes=query_exact_context_bytes,
        query_coordinates=query_coordinates,
        candidate_inputs=candidate_inputs,
        retrieved_at=clean["retrieved_at"],
    )
    if not _exact_equal(
        clean,
        expected,
        field="episodic retrieval exact joins",
        maximum=_MAX_RECORD_BYTES,
    ):
        _fail("episodic retrieval record differs from its exact supplied dependencies")
    return clean


def load_episodic_retrieval_record_join_json(
    body: bytes,
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Strictly load one record and revalidate every exact supplied dependency."""

    return validate_episodic_retrieval_record_join(
        _strict_json_object(
            body, field="episodic_retrieval_record", maximum=_MAX_RECORD_BYTES
        ),
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
        query_state_snapshot=query_state_snapshot,
        query_forecast_record=query_forecast_record,
        query_exact_context_bytes=query_exact_context_bytes,
        query_coordinates=query_coordinates,
        candidate_inputs=candidate_inputs,
    )


__all__ = [
    "CLAIMS",
    "EPISODIC_RETRIEVAL_RECORD_SCHEMA",
    "INPUT_PROFILE",
    "NUMERIC_CONVENTION",
    "RETRIEVAL_REGISTRATION_SCHEMA",
    "MarketMemoryRetrievalContractError",
    "build_episodic_retrieval_record",
    "build_retrieval_registration",
    "load_episodic_retrieval_record_join_json",
    "load_retrieval_registration_join_json",
    "score_normalized_euclidean",
    "validate_episodic_retrieval_record",
    "validate_episodic_retrieval_record_join",
    "validate_retrieval_registration_join",
    "validate_retrieval_registration_record",
]
