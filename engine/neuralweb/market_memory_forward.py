"""Pure W2A contracts for sealed Market Memory forward evaluation.

This module deliberately has no clock, filesystem, environment, network, API,
service, or production-writer dependency.  Callers supply synthetic values and
exact W1 context bytes.  The four records keep decision-time state, experiment
registration, forecasts, and later outcomes structurally separate.

The contracts are intentionally conservative: state is interpretable and
label-free, each admitted opportunity record is issued or explicitly
abstained, outcomes are append-only revisions keyed by a shared event, and all
authority remains private research context with emission disabled. Population
completeness requires a later opportunity schedule/writer and is not claimed
by this inert contract slice.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Final, NoReturn

from engine.neuralweb import market_memory

STATE_SNAPSHOT_SCHEMA = "market_memory.state_snapshot.v1"
TRIAL_REGISTRATION_SCHEMA = "market_memory.trial_registration.v1"
FORECAST_RECORD_SCHEMA = "market_memory.forecast_record.v1"
OUTCOME_RECORD_SCHEMA = "market_memory.outcome_record.v1"

CANONICAL_DOMAINS: tuple[str, ...] = market_memory.CANONICAL_CONTEXT_DOMAINS

_MAX_CONTRACT_BYTES = 256 * 1024
_MAX_CONTEXT_BYTES = 2 * 1024 * 1024
_MAX_JSON_DEPTH = 18
_MAX_JSON_NODES = 16_384
_MAX_COLLECTION_ITEMS = 512
_MAX_STRING_BYTES = 4 * 1024
_MAX_OBSERVATIONS_PER_DOMAIN = 128
_MAX_SOURCE_REFS = 32
_MAX_ABSOLUTE_NUMBER = 10**15
_MIN_YEAR = 1970
_MAX_YEAR = 2100

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_W1_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z"
)
_OPAQUE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_STATE_ID = re.compile(r"mmstate_[a-f0-9]{64}\Z")
_TRIAL_ID = re.compile(r"mmtrial_[a-f0-9]{64}\Z")
_FORECAST_ID = re.compile(r"mmforecast_[a-f0-9]{64}\Z")
_FORECAST_KEY = re.compile(r"mmforecastkey_[a-f0-9]{64}\Z")
_OUTCOME_EVENT_ID = re.compile(r"mmoutcomeevent_[a-f0-9]{64}\Z")
_OUTCOME_ID = re.compile(r"mmoutcome_[a-f0-9]{64}\Z")
_CONTEXT_ID = re.compile(r"mmctx_[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmstore_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmgeneration_[a-f0-9]{64}\Z")
_IDENTITY_ID = re.compile(r"mmidentity_[a-f0-9]{64}\Z")
_IDENTITY_VERSION = re.compile(r"mmidentityv_[a-f0-9]{64}\Z")
_UNIVERSE_ID = re.compile(r"mmuniverse_[a-f0-9]{64}\Z")
_CALENDAR_ID = re.compile(r"mmcalendar_[a-f0-9]{64}\Z")
_SOURCE_RECEIPT_ID = re.compile(r"mmsrc_[a-f0-9]{64}\Z")

AUTHORITY: Mapping[str, Any] = MappingProxyType(
    {
        "tier": "research",
        "visibility": "private",
        "context_only": True,
        "emission_enabled": False,
        "training_eligible": False,
        "promotion_eligible": False,
        "proposal_weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_originate": False,
        "may_select_options_candidate": False,
        "may_execute": False,
        "may_write_options_episode": False,
        "may_append_outcome": False,
        "may_train_prophet": False,
    }
)

_STATE_FIELDS = frozenset(
    {
        "schema",
        "state_snapshot_id",
        "context_id",
        "as_known_at",
        "context_manifest",
        "domain_states",
        "coverage",
        "representation_policy",
        "authority",
    }
)
_CONTEXT_MANIFEST_FIELDS = frozenset(
    {
        "context_sha256",
        "context_bytes",
        "store_id",
        "generation_id",
        "generation_sha256",
        "identity_receipt_id",
        "identity_version",
        "universe_id",
        "membership_source_receipt_id",
        "calendar_id",
        "calendar_version",
        "calendar_source_receipt_id",
        "state_snapshot_ref",
    }
)
_DOMAIN_STATE_FIELDS = frozenset({"domain", "status", "observations", "missing_reason"})
_OBSERVATION_FIELDS = frozenset(
    {
        "feature_id",
        "value_type",
        "value",
        "unit",
        "observed_at",
        "pit_basis",
        "transform_version",
        "source_receipt_ids",
        "quality",
    }
)
_QUALITY_FIELDS = frozenset({"status", "imputed"})
_SNAPSHOT_REF_FIELDS = frozenset({"snapshot_id", "schema", "content_sha256", "as_of"})
_COVERAGE_FIELDS = frozenset(
    {
        "required_domains",
        "observed_domains",
        "partial_domains",
        "missing_domains",
        "n_observed_domains",
        "n_partial_domains",
        "n_missing_domains",
        "multi_domain",
    }
)

_TRIAL_FIELDS = frozenset(
    {
        "schema",
        "trial_registration_id",
        "trial_key",
        "registered_at",
        "state_requirements",
        "target",
        "marks",
        "horizon",
        "outcome_definition_sha256",
        "distribution",
        "proper_score",
        "baselines",
        "splits",
        "purge",
        "embargo",
        "dependence",
        "trial_budget",
        "abstention",
        "expiry",
        "demotion",
        "implementation",
        "emission_enabled",
        "authority",
    }
)
_STATE_REQUIREMENTS_FIELDS = frozenset(
    {
        "state_schema",
        "context_schema",
        "minimum_observed_domains",
        "required_observed_domains",
    }
)
_TARGET_FIELDS = frozenset(
    {
        "target_id",
        "formula",
        "formula_version",
        "value_type",
        "unit",
        "categories",
        "target_sha256",
    }
)
_MARK_FIELDS = frozenset({"input_mark", "outcome_mark", "cost_convention", "benchmark"})
_HORIZON_FIELDS = frozenset(
    {
        "anchor",
        "start_offset_seconds",
        "end_offset_seconds",
        "evaluation_offset_seconds",
    }
)
_DISTRIBUTION_FIELDS = frozenset({"kind", "quantile_levels", "categories"})
_PROPER_SCORE_FIELDS = frozenset({"name", "orientation"})
_BASELINE_FIELDS = frozenset({"baseline_id", "baseline_version", "config_sha256"})
_SPLIT_FIELDS = frozenset(
    {
        "development_start",
        "development_end",
        "test_start",
        "test_end",
        "live_forward_start",
    }
)
_PURGE_FIELDS = frozenset({"enabled", "before_seconds", "after_seconds"})
_EMBARGO_FIELDS = frozenset({"enabled", "duration_seconds"})
_DEPENDENCE_FIELDS = frozenset({"keys", "clustering", "cluster_version"})
_TRIAL_BUDGET_FIELDS = frozenset(
    {"max_trials", "max_variants", "family_trials_already_registered"}
)
_ABSTENTION_FIELDS = frozenset(
    {"required", "minimum_observed_domains", "allowed_reasons"}
)
_EXPIRY_FIELDS = frozenset({"expires_at", "action"})
_DEMOTION_FIELDS = frozenset({"enabled", "triggers"})
_IMPLEMENTATION_FIELDS = frozenset({"model_sha256", "code_sha256", "config_sha256"})

_FORECAST_FIELDS = frozenset(
    {
        "schema",
        "forecast_id",
        "forecast_key",
        "outcome_event_id",
        "trial_registration_id",
        "trial_key",
        "state_snapshot_id",
        "context_id",
        "as_known_at",
        "decision_cutoff",
        "sealed_at",
        "horizon_start",
        "horizon_end",
        "evaluation_at",
        "disposition",
        "abstention_reason",
        "plan_sha256",
        "target_sha256",
        "outcome_definition_sha256",
        "model_sha256",
        "code_sha256",
        "config_sha256",
        "predictive_distribution",
        "baseline_refs",
        "emission_enabled",
        "authority",
    }
)
_PREDICTIVE_DISTRIBUTION_FIELDS = frozenset(
    {"kind", "point", "quantiles", "probabilities"}
)
_QUANTILE_FIELDS = frozenset({"level", "value"})
_PROBABILITY_FIELDS = frozenset({"category", "probability"})

_OUTCOME_FIELDS = frozenset(
    {
        "schema",
        "outcome_record_id",
        "outcome_event_id",
        "context_id",
        "target_sha256",
        "outcome_definition_sha256",
        "horizon_start",
        "horizon_end",
        "evaluation_at",
        "status",
        "outcome_value",
        "reason",
        "effective_at",
        "source_available_at",
        "known_at",
        "observed_at",
        "recorded_at",
        "source_receipts",
        "revision_number",
        "revision_of",
        "revision_reason",
        "emission_enabled",
        "authority",
    }
)
_OUTCOME_VALUE_FIELDS = frozenset({"value_type", "value", "unit"})
_OUTCOME_SOURCE_FIELDS = frozenset(
    {"receipt_id", "artifact_sha256", "source_schema", "source_version"}
)

_PIT_BASES = frozenset(
    {
        "live_captured",
        "source_vintage",
        "public_reconstructed",
        "recomputed_history",
        "current_snapshot_backfill",
    }
)
_MISSING_REASONS = frozenset(
    {
        "not_captured",
        "source_unavailable",
        "not_applicable",
        "quality_rejected",
        "outside_coverage",
    }
)
_W1_MISSING_REASON_MAP: Final[dict[str, str]] = {
    "adapter_not_implemented": "not_captured",
    "no_point_in_time_vintage": "not_captured",
    "not_applicable": "not_applicable",
    "outside_source_coverage": "outside_coverage",
    "source_unavailable_at_cutoff": "source_unavailable",
    "upstream_gap": "source_unavailable",
}
_MISSING_REASON_PRIORITY: Final[tuple[str, ...]] = (
    "quality_rejected",
    "source_unavailable",
    "outside_coverage",
    "not_captured",
    "not_applicable",
)
_ABSTENTION_REASONS = frozenset(
    {
        "insufficient_domains",
        "required_domain_missing",
        "input_stale",
        "out_of_distribution",
        "model_unavailable",
        "policy_expired",
        "quality_gate_failed",
    }
)
_DEMOTION_TRIGGERS = frozenset(
    {
        "stale_evidence",
        "coverage_breach",
        "calibration_decay",
        "broken_lineage",
        "schema_change",
        "source_change",
        "baseline_underperformance",
    }
)
_OUTCOME_REASONS = frozenset(
    {
        "source_window_incomplete",
        "instrument_unavailable",
        "event_invalidated",
        "coverage_ended",
        "source_unavailable",
        "source_not_published",
        "identity_unresolved",
        "quality_gate_failed",
    }
)
_REVISION_REASONS = frozenset(
    {"source_revision", "quality_correction", "clock_correction", "status_resolution"}
)

_STATE_FORBIDDEN_TOKENS = frozenset(
    {
        "embedding",
        "embeddings",
        "score",
        "scores",
        "forecast",
        "forecasts",
        "prediction",
        "predictions",
        "label",
        "labels",
        "outcome",
        "outcomes",
        "target",
        "targets",
        "pnl",
        "profit",
        "loss",
        "authority",
        "permission",
        "rank",
        "gate",
        "gates",
        "gated",
        "gating",
        "ungated",
        "gatekeeper",
        "gatekeepers",
        "gatekeeping",
        "size",
        "trade",
        "execute",
    }
)
_STATE_FORBIDDEN_COMPACT = (
    "embed",
    "scor",
    "forecast",
    "predict",
    "label",
    "outcome",
    "target",
    "pnl",
    "profit",
    "loss",
    "authority",
    "permission",
    "rank",
    "gating",
    "sizing",
    "size",
    "trading",
    "trade",
    "execut",
)


class MarketMemoryForwardContractError(ValueError):
    """A W2A record is unsafe, ambiguous, or non-canonical."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryForwardContractError(message)


def _require_plain_dict(value: object, *, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{field} must be a plain JSON object")
    if not all(type(key) is str for key in value):
        _fail(f"{field} keys must be strings")
    return value


def _require_fields(
    value: object, expected: frozenset[str], *, field: str
) -> dict[str, Any]:
    payload = _require_plain_dict(value, field=field)
    if set(payload) != expected:
        missing = sorted(expected - set(payload))
        extra = sorted(set(payload) - expected)
        _fail(f"{field} fields are not canonical; missing={missing}, extra={extra}")
    return payload


def _bounded_canonical_bytes(
    value: object, *, field: str, maximum: int = _MAX_CONTRACT_BYTES
) -> bytes:
    nodes = 0
    active: set[int] = set()
    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            _fail(f"{field} exceeds the JSON node bound")
        if depth > _MAX_JSON_DEPTH:
            _fail(f"{field} exceeds the JSON depth bound")
        if type(current) is dict:
            if id(current) in active:
                _fail(f"{field} contains a cycle")
            if len(current) > _MAX_COLLECTION_ITEMS:
                _fail(f"{field} object exceeds its member bound")
            if not all(type(key) is str for key in current):
                _fail(f"{field} object keys must be strings")
            active.add(id(current))
            stack.append((current, depth, True))
            for key, item in reversed(list(current.items())):
                _bounded_text_scalar(key, field=f"{field} key")
                stack.append((item, depth + 1, False))
            continue
        if type(current) is list:
            if id(current) in active:
                _fail(f"{field} contains a cycle")
            if len(current) > _MAX_COLLECTION_ITEMS:
                _fail(f"{field} array exceeds its item bound")
            active.add(id(current))
            stack.append((current, depth, True))
            stack.extend((item, depth + 1, False) for item in reversed(current))
            continue
        if type(current) is str:
            _bounded_text_scalar(current, field=field)
            continue
        if current is None or type(current) is bool or type(current) is int:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail(f"{field} contains a non-finite number")
            continue
        _fail(f"{field} contains a non-JSON value")
    try:
        body = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryForwardContractError(
            f"{field} is not finite canonical JSON"
        ) from exc
    if not body or len(body) > maximum:
        _fail(f"{field} is empty or exceeds its canonical byte bound")
    return body


def canonical_json_bytes(value: object) -> bytes:
    """Return bounded canonical UTF-8 JSON bytes for a W2A value."""

    return _bounded_canonical_bytes(value, field="W2A value")


def _bounded_text_scalar(value: str, *, field: str) -> str:
    if any(unicodedata.category(char) == "Cs" for char in value):
        _fail(f"{field} contains a surrogate code point")
    if any(ord(char) < 32 for char in value):
        _fail(f"{field} contains a control character")
    if len(value.encode("utf-8")) > _MAX_STRING_BYTES:
        _fail(f"{field} exceeds its UTF-8 byte bound")
    return value


def _detached(value: object, *, field: str) -> dict[str, Any]:
    body = _bounded_canonical_bytes(value, field=field)
    return _require_plain_dict(json.loads(body), field=field)


def _exact_json_equal(left: object, right: object, *, field: str) -> bool:
    return _bounded_canonical_bytes(
        left, field=f"{field} supplied"
    ) == _bounded_canonical_bytes(right, field=f"{field} expected")


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return (
        prefix
        + hashlib.sha256(
            _bounded_canonical_bytes(core, field=f"{field} preimage")
        ).hexdigest()
    )


def _sha256(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        _fail(f"{field} must be lowercase SHA-256")
    return value


def _match(value: object, pattern: re.Pattern[str], *, field: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(f"{field} is malformed")
    return value


def _text(value: object, *, field: str, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{field} must be non-empty bounded text")
    _bounded_text_scalar(value, field=field)
    return value


def _opaque(value: object, *, field: str, maximum: int = 256) -> str:
    text = _text(value, field=field, maximum=maximum)
    if not _OPAQUE_REF.fullmatch(text):
        _fail(f"{field} contains unsupported characters")
    return text


def _exact_int(
    value: object, *, field: str, minimum: int = 0, maximum: int = 10**9
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{field} is outside its exact integer bound")
    return value


def _number(value: object, *, field: str) -> int | float:
    if (
        type(value) not in {int, float}
        or not math.isfinite(value)
        or abs(value) > _MAX_ABSOLUTE_NUMBER
    ):
        _fail(f"{field} must be a finite JSON number, not bool")
    return value


def _exact_utc(value: object, *, field: str) -> datetime:
    if type(value) is not str or not _UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{field} must be exact microsecond RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryForwardContractError(f"{field} is not real") from exc
    if parsed.utcoffset() != timedelta(0):
        _fail(f"{field} must be UTC")
    if not _MIN_YEAR <= parsed.year <= _MAX_YEAR:
        _fail(f"{field} is outside the frozen year range")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _exact_w1_utc(value: object, *, field: str) -> datetime:
    """Parse the owner contract's canonical zero-to-six fractional UTC form."""

    if type(value) is not str or not _W1_UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{field} is not a canonical W1 RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryForwardContractError(f"{field} is not real") from exc
    if parsed.utcoffset() != timedelta(0):
        _fail(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _validate_authority(value: object, *, field: str) -> dict[str, Any]:
    expected = dict(AUTHORITY)
    if type(value) is not dict or not _exact_json_equal(value, expected, field=field):
        _fail(f"{field} must equal the frozen zero-authority contract")
    return expected


def _normalize_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", normalized).casefold()
    return set(re.findall(r"[a-z0-9]+", normalized))


def _assert_interpretable_state_text(value: str, *, field: str) -> None:
    tokens = _normalize_tokens(value)
    compact = "".join(
        re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", value).casefold())
    )
    if tokens & _STATE_FORBIDDEN_TOKENS or any(
        marker in compact for marker in _STATE_FORBIDDEN_COMPACT
    ):
        _fail(f"{field} contains a forbidden learned/post-event/action semantic")


def _strict_json_object(
    body: bytes, *, field: str, maximum: int = _MAX_CONTRACT_BYTES
) -> dict[str, Any]:
    if type(body) is not bytes:
        _fail(f"{field} JSON body must be bytes")
    if not body or len(body) > maximum:
        _fail(f"{field} JSON body is empty or exceeds its byte bound")
    if body.startswith(b"\xef\xbb\xbf"):
        _fail(f"{field} JSON body must not carry a UTF-8 BOM")

    def reject_constant(value: str) -> NoReturn:
        _fail(f"{field} JSON contains non-finite constant {value}")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                _fail(f"{field} JSON contains duplicate key {key!r}")
            output[key] = value
        return output

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise MarketMemoryForwardContractError(
            f"{field} JSON is not valid UTF-8"
        ) from exc
    except MarketMemoryForwardContractError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise MarketMemoryForwardContractError(
            f"{field} JSON is not one exact JSON document"
        ) from exc
    payload = _require_plain_dict(value, field=field)
    canonical = _bounded_canonical_bytes(payload, field=field, maximum=maximum)
    if body != canonical:
        _fail(f"{field} JSON body must be exact canonical JSON bytes")
    return payload


def _load_exact_context(exact_context_bytes: bytes) -> dict[str, Any]:
    packet = _strict_json_object(
        exact_context_bytes, field="exact W1 context", maximum=_MAX_CONTEXT_BYTES
    )
    if (
        _bounded_canonical_bytes(
            packet, field="exact W1 context", maximum=_MAX_CONTEXT_BYTES
        )
        != exact_context_bytes
    ):
        _fail("exact W1 context bytes are not canonical JSON")
    try:
        clean = market_memory.validate_as_known_at_context(packet)
    except (ValueError, TypeError, KeyError) as exc:
        raise MarketMemoryForwardContractError(
            "exact W1 context fails its owner validator"
        ) from exc
    return _require_plain_dict(dict(clean), field="exact W1 context")


def _representation_policy() -> dict[str, Any]:
    return {
        "representation": "interpretable_typed_observations",
        "missingness": "explicit_per_domain",
        "context_reference": "immutable_exact_bytes",
        "post_event_data": "forbidden",
        "learned_representation": False,
    }


def _validate_state_scalar(
    value_type: str, value: object, *, field: str
) -> str | bool | int | float | dict[str, str]:
    if value_type == "string":
        text = _text(value, field=field, maximum=512)
        _assert_interpretable_state_text(text, field=field)
        return text
    if value_type == "boolean":
        if type(value) is not bool:
            _fail(f"{field} must be boolean")
        return value
    if value_type == "integer":
        if (
            type(value) is not int
            or not -_MAX_ABSOLUTE_NUMBER <= value <= _MAX_ABSOLUTE_NUMBER
        ):
            _fail(f"{field} must be integer, not bool")
        return value
    if value_type == "number":
        return _number(value, field=field)
    if value_type == "snapshot_ref":
        payload = _require_fields(value, _SNAPSHOT_REF_FIELDS, field=field)
        snapshot_id = _match(
            payload["snapshot_id"],
            re.compile(r"mmsnap_[a-f0-9]{64}\Z"),
            field=f"{field}.snapshot_id",
        )
        content_sha = _sha256(
            payload["content_sha256"], field=f"{field}.content_sha256"
        )
        if snapshot_id != f"mmsnap_{content_sha}":
            _fail(f"{field}.snapshot_id does not bind content_sha256")
        schema = _opaque(payload["schema"], field=f"{field}.schema")
        _assert_interpretable_state_text(schema, field=f"{field}.schema")
        as_of = _format_utc(_exact_w1_utc(payload["as_of"], field=f"{field}.as_of"))
        return {
            "snapshot_id": snapshot_id,
            "schema": schema,
            "content_sha256": content_sha,
            "as_of": as_of,
        }
    _fail(f"{field} value_type is unsupported")


def _validate_observation(value: object, *, as_known_at: datetime) -> dict[str, Any]:
    payload = _require_fields(value, _OBSERVATION_FIELDS, field="state observation")
    feature_id = _opaque(payload["feature_id"], field="observation.feature_id")
    _assert_interpretable_state_text(feature_id, field="observation.feature_id")
    value_type = payload["value_type"]
    if value_type not in {"string", "boolean", "integer", "number", "snapshot_ref"}:
        _fail("observation.value_type is unsupported")
    clean_value = _validate_state_scalar(
        value_type, payload["value"], field="observation.value"
    )
    unit = _opaque(payload["unit"], field="observation.unit", maximum=64)
    _assert_interpretable_state_text(unit, field="observation.unit")
    observed = _exact_utc(payload["observed_at"], field="observation.observed_at")
    if observed > as_known_at:
        _fail("state observation is later than as_known_at")
    pit_basis = payload["pit_basis"]
    if pit_basis not in _PIT_BASES:
        _fail("observation.pit_basis is unsupported")
    transform = _opaque(
        payload["transform_version"], field="observation.transform_version"
    )
    _assert_interpretable_state_text(transform, field="observation.transform_version")
    refs = payload["source_receipt_ids"]
    if type(refs) is not list or not 1 <= len(refs) <= _MAX_SOURCE_REFS:
        _fail("observation.source_receipt_ids is outside its bound")
    clean_refs = [
        _match(ref, _SOURCE_RECEIPT_ID, field="observation source receipt")
        for ref in refs
    ]
    if clean_refs != sorted(set(clean_refs)):
        _fail("observation.source_receipt_ids must be sorted and unique")
    quality = _require_fields(
        payload["quality"], _QUALITY_FIELDS, field="observation.quality"
    )
    if quality["status"] not in {"ok", "degraded"}:
        _fail("observation.quality.status is unsupported")
    if quality["imputed"] is not False:
        _fail("W2A state observations cannot be imputed")
    return {
        "feature_id": feature_id,
        "value_type": value_type,
        "value": clean_value,
        "unit": unit,
        "observed_at": _format_utc(observed),
        "pit_basis": pit_basis,
        "transform_version": transform,
        "source_receipt_ids": clean_refs,
        "quality": {"status": quality["status"], "imputed": False},
    }


def _validate_domain_states(
    value: object, *, as_known_at: datetime
) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) != len(CANONICAL_DOMAINS):
        _fail("domain_states must carry all canonical domains exactly once")
    clean: list[dict[str, Any]] = []
    all_features: set[str] = set()
    for index, expected_domain in enumerate(CANONICAL_DOMAINS):
        row = _require_fields(
            value[index], _DOMAIN_STATE_FIELDS, field=f"domain_states[{index}]"
        )
        if row["domain"] != expected_domain:
            _fail("domain_states must follow canonical domain order")
        status = row["status"]
        if status not in {"observed", "partial", "missing"}:
            _fail(f"domain {expected_domain} status is unsupported")
        observations = row["observations"]
        if (
            type(observations) is not list
            or len(observations) > _MAX_OBSERVATIONS_PER_DOMAIN
        ):
            _fail(f"domain {expected_domain} observations exceed their bound")
        clean_observations = [
            _validate_observation(item, as_known_at=as_known_at)
            for item in observations
        ]
        feature_ids = [item["feature_id"] for item in clean_observations]
        if feature_ids != sorted(feature_ids) or len(feature_ids) != len(
            set(feature_ids)
        ):
            _fail(f"domain {expected_domain} observations must be sorted and unique")
        if all_features.intersection(feature_ids):
            _fail("state feature IDs must be globally unique")
        all_features.update(feature_ids)
        reason = row["missing_reason"]
        if status == "observed":
            if not clean_observations or reason is not None:
                _fail("observed domain requires observations and no missing reason")
        elif status == "partial":
            if not clean_observations or reason not in _MISSING_REASONS:
                _fail("partial domain requires observations and a canonical reason")
        elif clean_observations or reason not in _MISSING_REASONS:
            _fail("missing domain requires no observations and a canonical reason")
        clean.append(
            {
                "domain": expected_domain,
                "status": status,
                "observations": clean_observations,
                "missing_reason": reason,
            }
        )
    return clean


def _w1_observation_projection(
    feature: Mapping[str, Any], *, as_known_at: datetime
) -> dict[str, Any]:
    value = feature["value"]
    if type(value) is str:
        value_type = "string"
    elif type(value) is bool:
        value_type = "boolean"
    elif type(value) is int:
        value_type = "integer"
    elif type(value) is float:
        value_type = "number"
    elif type(value) is dict:
        value_type = "snapshot_ref"
    else:
        _fail("observed W1 feature has an unsupported state value")
    projected = {
        "feature_id": feature["feature_id"],
        "value_type": value_type,
        "value": copy.deepcopy(value),
        "unit": feature["unit"],
        "observed_at": _format_utc(
            _exact_w1_utc(feature["observed_at"], field="W1 feature observed_at")
        ),
        "pit_basis": feature["pit_basis"],
        "transform_version": feature["transform_version"],
        "source_receipt_ids": list(feature["source_receipt_ids"]),
        "quality": {
            "status": feature["quality"]["status"],
            "imputed": feature["quality"]["imputed"],
        },
    }
    return _validate_observation(projected, as_known_at=as_known_at)


def _mapped_w1_missing_reason(features: Sequence[Mapping[str, Any]]) -> str:
    mapped: set[str] = set()
    for feature in features:
        reason = feature["missing_reason"]
        try:
            mapped.add(_W1_MISSING_REASON_MAP[reason])
        except (KeyError, TypeError) as exc:
            raise MarketMemoryForwardContractError(
                "W1 missing reason has no frozen W2A projection"
            ) from exc
    return next(reason for reason in _MISSING_REASON_PRIORITY if reason in mapped)


def _project_w1_domain_states(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Produce the only admitted W2A state view of the exact W1 feature receipts."""

    as_known_at = _exact_w1_utc(
        packet["clocks"]["as_known_at"], field="context as_known_at"
    )
    rows: list[dict[str, Any]] = []
    for domain in CANONICAL_DOMAINS:
        domain_features = [
            feature
            for feature in packet["feature_receipts"]
            if feature["domain"] == domain
        ]
        observed_features = [
            feature for feature in domain_features if feature["status"] == "observed"
        ]
        admitted_observed_features = [
            feature
            for feature in observed_features
            if feature["quality"]["imputed"] is False
        ]
        rejected_imputed_features = [
            feature
            for feature in observed_features
            if feature["quality"]["imputed"] is True
        ]
        missing_features = [
            feature for feature in domain_features if feature["status"] == "missing"
        ]
        observations = [
            _w1_observation_projection(feature, as_known_at=as_known_at)
            for feature in admitted_observed_features
        ]
        observations.sort(key=lambda row: row["feature_id"])
        missing_reasons: set[str] = set()
        if missing_features:
            missing_reasons.add(_mapped_w1_missing_reason(missing_features))
        if rejected_imputed_features:
            missing_reasons.add("quality_rejected")
        reason = next(
            (
                candidate
                for candidate in _MISSING_REASON_PRIORITY
                if candidate in missing_reasons
            ),
            None,
        )
        if observations and reason is None:
            status = "observed"
        elif observations:
            status = "partial"
        else:
            status = "missing"
            if reason is None:
                _fail("W1 domain has neither admissible observations nor missingness")
        rows.append(
            {
                "domain": domain,
                "status": status,
                "observations": observations,
                "missing_reason": reason,
            }
        )
    return _validate_domain_states(rows, as_known_at=as_known_at)


def _coverage(domain_states: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [row["domain"] for row in domain_states if row["status"] == "observed"]
    partial = [row["domain"] for row in domain_states if row["status"] == "partial"]
    missing = [row["domain"] for row in domain_states if row["status"] == "missing"]
    return {
        "required_domains": list(CANONICAL_DOMAINS),
        "observed_domains": observed,
        "partial_domains": partial,
        "missing_domains": missing,
        "n_observed_domains": len(observed),
        "n_partial_domains": len(partial),
        "n_missing_domains": len(missing),
        "multi_domain": len(observed) >= 2,
    }


def _context_manifest(
    packet: Mapping[str, Any],
    exact_context_bytes: bytes,
    *,
    store_id: str,
    generation_id: str,
    generation_sha256: str,
) -> dict[str, Any]:
    identity = _require_plain_dict(packet["identity_receipt"], field="identity_receipt")
    return {
        "context_sha256": hashlib.sha256(exact_context_bytes).hexdigest(),
        "context_bytes": len(exact_context_bytes),
        "store_id": _match(store_id, _STORE_ID, field="store_id"),
        "generation_id": _match(generation_id, _GENERATION_ID, field="generation_id"),
        "generation_sha256": _sha256(generation_sha256, field="generation_sha256"),
        "identity_receipt_id": identity["receipt_id"],
        "identity_version": identity["identity_version"],
        "universe_id": identity["universe_id"],
        "membership_source_receipt_id": identity["membership_source_receipt_id"],
        "calendar_id": identity["calendar_id"],
        "calendar_version": identity["calendar_version"],
        "calendar_source_receipt_id": identity["calendar_source_receipt_id"],
        "state_snapshot_ref": packet["state_snapshot_ref"],
    }


def build_state_snapshot(
    *,
    exact_context_bytes: bytes,
    store_id: str,
    generation_id: str,
    generation_sha256: str,
    domain_states: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a separate, immutable state manifest over exact W1 context bytes."""

    packet = _load_exact_context(exact_context_bytes)
    if packet["state_snapshot_ref"] is not None:
        _fail("W2A cannot mutate or consume a back-written state_snapshot_ref")
    as_known_at = _format_utc(
        _exact_w1_utc(packet["clocks"]["as_known_at"], field="context as_known_at")
    )
    clean_domains = _validate_domain_states(
        list(domain_states), as_known_at=_exact_utc(as_known_at, field="as_known_at")
    )
    payload: dict[str, Any] = {
        "schema": STATE_SNAPSHOT_SCHEMA,
        "state_snapshot_id": "",
        "context_id": packet["context_id"],
        "as_known_at": as_known_at,
        "context_manifest": _context_manifest(
            packet,
            exact_context_bytes,
            store_id=store_id,
            generation_id=generation_id,
            generation_sha256=generation_sha256,
        ),
        "domain_states": clean_domains,
        "coverage": _coverage(clean_domains),
        "representation_policy": _representation_policy(),
        "authority": dict(AUTHORITY),
    }
    payload["state_snapshot_id"] = _content_id(
        "mmstate_", payload, field="state_snapshot_id"
    )
    return validate_state_snapshot(payload, exact_context_bytes=exact_context_bytes)


def validate_state_snapshot_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one stored state record without an external context dependency."""

    payload = _require_fields(value, _STATE_FIELDS, field="state_snapshot")
    _bounded_canonical_bytes(payload, field="state_snapshot")
    if payload["schema"] != STATE_SNAPSHOT_SCHEMA:
        _fail("state snapshot schema drift")
    state_id = _match(
        payload["state_snapshot_id"], _STATE_ID, field="state_snapshot_id"
    )
    context_id = _match(payload["context_id"], _CONTEXT_ID, field="context_id")
    as_known_at_dt = _exact_utc(payload["as_known_at"], field="as_known_at")
    manifest = _require_fields(
        payload["context_manifest"],
        _CONTEXT_MANIFEST_FIELDS,
        field="context_manifest",
    )
    clean_manifest = {
        "context_sha256": _sha256(
            manifest["context_sha256"], field="context_manifest.context_sha256"
        ),
        "context_bytes": _exact_int(
            manifest["context_bytes"],
            field="context_manifest.context_bytes",
            minimum=1,
            maximum=_MAX_CONTEXT_BYTES,
        ),
        "store_id": _match(
            manifest["store_id"], _STORE_ID, field="context_manifest.store_id"
        ),
        "generation_id": _match(
            manifest["generation_id"],
            _GENERATION_ID,
            field="context_manifest.generation_id",
        ),
        "generation_sha256": _sha256(
            manifest["generation_sha256"],
            field="context_manifest.generation_sha256",
        ),
        "identity_receipt_id": _match(
            manifest["identity_receipt_id"],
            _IDENTITY_ID,
            field="context_manifest.identity_receipt_id",
        ),
        "identity_version": _match(
            manifest["identity_version"],
            _IDENTITY_VERSION,
            field="context_manifest.identity_version",
        ),
        "universe_id": _match(
            manifest["universe_id"],
            _UNIVERSE_ID,
            field="context_manifest.universe_id",
        ),
        "membership_source_receipt_id": _match(
            manifest["membership_source_receipt_id"],
            _SOURCE_RECEIPT_ID,
            field="context_manifest.membership_source_receipt_id",
        ),
        "calendar_id": _match(
            manifest["calendar_id"],
            _CALENDAR_ID,
            field="context_manifest.calendar_id",
        ),
        "calendar_version": _match(
            manifest["calendar_version"],
            re.compile(r"mmv_[a-f0-9]{64}\Z"),
            field="context_manifest.calendar_version",
        ),
        "calendar_source_receipt_id": _match(
            manifest["calendar_source_receipt_id"],
            _SOURCE_RECEIPT_ID,
            field="context_manifest.calendar_source_receipt_id",
        ),
        "state_snapshot_ref": manifest["state_snapshot_ref"],
    }
    if clean_manifest["state_snapshot_ref"] is not None:
        _fail("W2A state manifest must preserve the null W1 state_snapshot_ref")
    if not _exact_json_equal(manifest, clean_manifest, field="context_manifest record"):
        _fail("context manifest is not exact canonical JSON")
    clean_domains = _validate_domain_states(
        payload["domain_states"], as_known_at=as_known_at_dt
    )
    expected_coverage = _coverage(clean_domains)
    coverage = _require_fields(payload["coverage"], _COVERAGE_FIELDS, field="coverage")
    if not _exact_json_equal(coverage, expected_coverage, field="coverage"):
        _fail("state coverage is not derived from domain states")
    if not _exact_json_equal(
        payload["representation_policy"],
        _representation_policy(),
        field="representation_policy",
    ):
        _fail("state representation policy drift")
    authority = _validate_authority(payload["authority"], field="state authority")
    clean: dict[str, Any] = {
        "schema": STATE_SNAPSHOT_SCHEMA,
        "state_snapshot_id": state_id,
        "context_id": context_id,
        "as_known_at": _format_utc(as_known_at_dt),
        "context_manifest": clean_manifest,
        "domain_states": clean_domains,
        "coverage": expected_coverage,
        "representation_policy": _representation_policy(),
        "authority": authority,
    }
    if not _exact_json_equal(payload, clean, field="state_snapshot"):
        _fail("state snapshot is not exact canonical JSON")
    if state_id != _content_id("mmstate_", clean, field="state_snapshot_id"):
        _fail("state_snapshot_id does not bind canonical content")
    return _detached(clean, field="state_snapshot")


def validate_state_snapshot(
    value: Mapping[str, Any], *, exact_context_bytes: bytes
) -> dict[str, Any]:
    """Strongly validate a state record against exact immutable W1 bytes."""

    clean = validate_state_snapshot_record(value)
    packet = _load_exact_context(exact_context_bytes)
    if packet["state_snapshot_ref"] is not None:
        _fail("W2A context state_snapshot_ref must remain null")
    if clean["context_id"] != packet["context_id"]:
        _fail("state snapshot context_id differs from exact context bytes")
    packet_cutoff = _format_utc(
        _exact_w1_utc(packet["clocks"]["as_known_at"], field="context as_known_at")
    )
    if clean["as_known_at"] != packet_cutoff:
        _fail("state snapshot cannot mutate the W1 as_known_at clock")
    manifest = clean["context_manifest"]
    expected_manifest = _context_manifest(
        packet,
        exact_context_bytes,
        store_id=manifest["store_id"],
        generation_id=manifest["generation_id"],
        generation_sha256=manifest["generation_sha256"],
    )
    if not _exact_json_equal(manifest, expected_manifest, field="context_manifest"):
        _fail("context manifest does not bind the exact W1 context")
    projected_domains = _project_w1_domain_states(packet)
    if not _exact_json_equal(
        clean["domain_states"], projected_domains, field="W1 state projection"
    ):
        _fail("state observations do not exactly project the W1 feature receipts")
    source_rows = packet["source_receipts"]
    source_by_id = {row["receipt_id"]: row for row in source_rows}
    for domain in clean["domain_states"]:
        for observation in domain["observations"]:
            refs = observation["source_receipt_ids"]
            if any(receipt_id not in source_by_id for receipt_id in refs):
                _fail("state observation cites a source absent from exact W1 context")
            latest_source_observation = max(
                _exact_w1_utc(
                    source_by_id[receipt_id]["observed_at"],
                    field="W1 source observed_at",
                )
                for receipt_id in refs
            )
            if (
                _exact_utc(
                    observation["observed_at"], field="state observation observed_at"
                )
                < latest_source_observation
            ):
                _fail("state observation predates one of its exact W1 sources")
    return clean


def load_state_snapshot_json(
    body: bytes, *, exact_context_bytes: bytes
) -> dict[str, Any]:
    """Strictly parse and validate one state snapshot."""

    return validate_state_snapshot(
        _strict_json_object(body, field="state_snapshot"),
        exact_context_bytes=exact_context_bytes,
    )


def load_state_snapshot_record_json(body: bytes) -> dict[str, Any]:
    """Strictly parse a self-authenticating state record without W1 bytes."""

    return validate_state_snapshot_record(
        _strict_json_object(body, field="state_snapshot")
    )


def _string_list(
    value: object,
    *,
    field: str,
    minimum: int = 0,
    maximum: int = 64,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail(f"{field} is outside its array bound")
    clean = [_opaque(item, field=f"{field} item") for item in value]
    if clean != sorted(set(clean)):
        _fail(f"{field} must be sorted and unique")
    if allowed is not None and not set(clean) <= allowed:
        _fail(f"{field} contains an unsupported value")
    return clean


def _validate_state_requirements(value: object) -> dict[str, Any]:
    payload = _require_fields(
        value, _STATE_REQUIREMENTS_FIELDS, field="state_requirements"
    )
    if payload["state_schema"] != STATE_SNAPSHOT_SCHEMA:
        _fail("state_requirements.state_schema drift")
    if payload["context_schema"] != market_memory.AS_KNOWN_AT_SCHEMA:
        _fail("state_requirements.context_schema drift")
    minimum = _exact_int(
        payload["minimum_observed_domains"],
        field="state_requirements.minimum_observed_domains",
        minimum=1,
        maximum=len(CANONICAL_DOMAINS),
    )
    raw_required = payload["required_observed_domains"]
    if type(raw_required) is not list or len(raw_required) > len(CANONICAL_DOMAINS):
        _fail("required_observed_domains exceeds its array bound")
    if not all(
        type(domain) is str and domain in CANONICAL_DOMAINS for domain in raw_required
    ):
        _fail("required_observed_domains contains an unsupported domain")
    required = list(raw_required)
    if len(required) != len(set(required)) or required != [
        domain for domain in CANONICAL_DOMAINS if domain in required
    ]:
        _fail("required_observed_domains must follow canonical domain order")
    if minimum < len(required):
        _fail("minimum_observed_domains cannot be below required domain count")
    return {
        "state_schema": STATE_SNAPSHOT_SCHEMA,
        "context_schema": market_memory.AS_KNOWN_AT_SCHEMA,
        "minimum_observed_domains": minimum,
        "required_observed_domains": required,
    }


def _target_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_id": value["target_id"],
        "formula": value["formula"],
        "formula_version": value["formula_version"],
        "value_type": value["value_type"],
        "unit": value["unit"],
        "categories": value["categories"],
        "target_sha256": "",
    }


def _validate_target(
    value: object, *, allow_missing_digest: bool = False
) -> dict[str, Any]:
    payload = _require_plain_dict(value, field="target")
    fields_without_digest = _TARGET_FIELDS - {"target_sha256"}
    if allow_missing_digest and set(payload) == fields_without_digest:
        supplied_digest: object = None
    elif set(payload) == _TARGET_FIELDS:
        supplied_digest = payload["target_sha256"]
    else:
        _fail("target fields are not canonical")
    target_id = _opaque(payload["target_id"], field="target.target_id")
    formula = _text(payload["formula"], field="target.formula", maximum=512)
    formula_version = _opaque(
        payload["formula_version"], field="target.formula_version"
    )
    value_type = payload["value_type"]
    if value_type not in {"number", "integer", "string"}:
        _fail("target.value_type is unsupported")
    unit = _opaque(payload["unit"], field="target.unit", maximum=64)
    categories = _string_list(
        payload["categories"], field="target.categories", maximum=32
    )
    if value_type == "string" and len(categories) < 2:
        _fail("string target requires at least two frozen categories")
    if value_type != "string" and categories:
        _fail("numeric target cannot carry categories")
    core = {
        "target_id": target_id,
        "formula": formula,
        "formula_version": formula_version,
        "value_type": value_type,
        "unit": unit,
        "categories": categories,
        "target_sha256": "",
    }
    expected_digest = hashlib.sha256(
        _bounded_canonical_bytes(core, field="target digest preimage")
    ).hexdigest()
    if (
        supplied_digest is not None
        and _sha256(supplied_digest, field="target.target_sha256") != expected_digest
    ):
        _fail("target_sha256 does not bind the frozen target")
    core["target_sha256"] = expected_digest
    return core


def _validate_marks(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _MARK_FIELDS, field="marks")
    return {
        "input_mark": _opaque(payload["input_mark"], field="marks.input_mark"),
        "outcome_mark": _opaque(payload["outcome_mark"], field="marks.outcome_mark"),
        "cost_convention": _opaque(
            payload["cost_convention"], field="marks.cost_convention"
        ),
        "benchmark": _opaque(payload["benchmark"], field="marks.benchmark"),
    }


def _validate_horizon(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _HORIZON_FIELDS, field="horizon")
    if payload["anchor"] != "decision_cutoff":
        _fail("horizon.anchor must be decision_cutoff")
    start = _exact_int(
        payload["start_offset_seconds"],
        field="horizon.start_offset_seconds",
        minimum=1,
        maximum=10 * 365 * 24 * 3600,
    )
    end = _exact_int(
        payload["end_offset_seconds"],
        field="horizon.end_offset_seconds",
        minimum=2,
        maximum=10 * 365 * 24 * 3600,
    )
    evaluation = _exact_int(
        payload["evaluation_offset_seconds"],
        field="horizon.evaluation_offset_seconds",
        minimum=2,
        maximum=10 * 365 * 24 * 3600,
    )
    if not start < end or evaluation != end:
        _fail("horizon must start before end and evaluate exactly at end")
    return {
        "anchor": "decision_cutoff",
        "start_offset_seconds": start,
        "end_offset_seconds": end,
        "evaluation_offset_seconds": evaluation,
    }


def _outcome_definition_sha256(
    *,
    target: Mapping[str, Any],
    marks: Mapping[str, Any],
    horizon: Mapping[str, Any],
) -> str:
    preimage = {
        "target": dict(target),
        "marks": dict(marks),
        "horizon": dict(horizon),
        "evaluation_rule": "horizon_end",
    }
    return hashlib.sha256(
        _bounded_canonical_bytes(preimage, field="outcome definition preimage")
    ).hexdigest()


def _probability_level(value: object, *, field: str) -> int | float:
    clean = _number(value, field=field)
    if not 0 < clean < 1:
        _fail(f"{field} must be strictly between zero and one")
    return clean


def _validate_distribution_spec(
    value: object, *, target: Mapping[str, Any]
) -> dict[str, Any]:
    payload = _require_fields(value, _DISTRIBUTION_FIELDS, field="distribution")
    kind = payload["kind"]
    if kind not in {"scalar", "quantiles", "categorical"}:
        _fail("distribution.kind is unsupported")
    levels_raw = payload["quantile_levels"]
    if type(levels_raw) is not list or len(levels_raw) > 32:
        _fail("distribution.quantile_levels exceeds its bound")
    levels = [
        _probability_level(item, field="distribution quantile level")
        for item in levels_raw
    ]
    if levels != sorted(set(levels)):
        _fail("distribution quantile levels must be sorted and unique")
    categories = _string_list(
        payload["categories"], field="distribution.categories", maximum=32
    )
    if kind == "scalar":
        if levels or categories or target["value_type"] == "string":
            _fail("scalar distribution requires a numeric target and no grid")
    elif kind == "quantiles":
        if not levels or categories or target["value_type"] == "string":
            _fail("quantile distribution requires levels and a numeric target")
    elif not categories or levels or categories != target["categories"]:
        _fail("categorical distribution must equal target categories")
    return {"kind": kind, "quantile_levels": levels, "categories": categories}


def _validate_proper_score(value: object, *, distribution_kind: str) -> dict[str, Any]:
    payload = _require_fields(value, _PROPER_SCORE_FIELDS, field="proper_score")
    allowed = {
        "scalar": {"squared_error", "absolute_error"},
        "quantiles": {"pinball_loss"},
        "categorical": {"log_loss", "brier_score"},
    }[distribution_kind]
    if payload["name"] not in allowed:
        _fail("proper_score.name does not match the distribution")
    if payload["orientation"] != "lower_is_better":
        _fail("proper_score.orientation drift")
    return {"name": payload["name"], "orientation": "lower_is_better"}


def _validate_baselines(value: object) -> list[dict[str, Any]]:
    if type(value) is not list or not 1 <= len(value) <= 32:
        _fail("baselines is outside its array bound")
    clean: list[dict[str, Any]] = []
    for item in value:
        row = _require_fields(item, _BASELINE_FIELDS, field="baseline")
        clean.append(
            {
                "baseline_id": _opaque(
                    row["baseline_id"], field="baseline.baseline_id"
                ),
                "baseline_version": _opaque(
                    row["baseline_version"], field="baseline.baseline_version"
                ),
                "config_sha256": _sha256(
                    row["config_sha256"], field="baseline.config_sha256"
                ),
            }
        )
    ids = [item["baseline_id"] for item in clean]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("baselines must be sorted and unique by baseline_id")
    return clean


def _validate_splits(value: object, *, registered_at: datetime) -> dict[str, Any]:
    payload = _require_fields(value, _SPLIT_FIELDS, field="splits")
    fields = (
        "development_start",
        "development_end",
        "test_start",
        "test_end",
        "live_forward_start",
    )
    parsed = [_exact_utc(payload[field], field=f"splits.{field}") for field in fields]
    if not parsed[0] < parsed[1] <= parsed[2] < parsed[3] <= parsed[4]:
        _fail("development, test, and live-forward splits overlap or reverse")
    if registered_at >= parsed[4]:
        _fail("trial registration must precede the live-forward split")
    return {field: _format_utc(item) for field, item in zip(fields, parsed)}


def _validate_purge(value: object, *, horizon_end_seconds: int) -> dict[str, Any]:
    payload = _require_fields(value, _PURGE_FIELDS, field="purge")
    if payload["enabled"] is not True:
        _fail("purge must be enabled")
    before = _exact_int(
        payload["before_seconds"], field="purge.before_seconds", maximum=10**9
    )
    after = _exact_int(
        payload["after_seconds"], field="purge.after_seconds", maximum=10**9
    )
    if before < horizon_end_seconds:
        _fail("purge.before_seconds must cover the full outcome horizon")
    return {"enabled": True, "before_seconds": before, "after_seconds": after}


def _validate_embargo(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _EMBARGO_FIELDS, field="embargo")
    if payload["enabled"] is not True:
        _fail("embargo must be enabled")
    duration = _exact_int(
        payload["duration_seconds"],
        field="embargo.duration_seconds",
        minimum=1,
        maximum=10**9,
    )
    return {"enabled": True, "duration_seconds": duration}


def _validate_dependence(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _DEPENDENCE_FIELDS, field="dependence")
    keys = _string_list(payload["keys"], field="dependence.keys", minimum=1, maximum=16)
    if payload["clustering"] not in {"exact_key_tuple", "effective_event_cluster"}:
        _fail("dependence.clustering is unsupported")
    return {
        "keys": keys,
        "clustering": payload["clustering"],
        "cluster_version": _opaque(
            payload["cluster_version"], field="dependence.cluster_version"
        ),
    }


def _validate_trial_budget(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _TRIAL_BUDGET_FIELDS, field="trial_budget")
    max_trials = _exact_int(
        payload["max_trials"], field="trial_budget.max_trials", minimum=1, maximum=10**6
    )
    max_variants = _exact_int(
        payload["max_variants"],
        field="trial_budget.max_variants",
        minimum=1,
        maximum=max_trials,
    )
    already = _exact_int(
        payload["family_trials_already_registered"],
        field="trial_budget.family_trials_already_registered",
        maximum=max_trials - 1,
    )
    return {
        "max_trials": max_trials,
        "max_variants": max_variants,
        "family_trials_already_registered": already,
    }


def _validate_abstention(value: object, *, minimum_domains: int) -> dict[str, Any]:
    payload = _require_fields(value, _ABSTENTION_FIELDS, field="abstention")
    if payload["required"] is not True:
        _fail("abstention must be required")
    minimum = _exact_int(
        payload["minimum_observed_domains"],
        field="abstention.minimum_observed_domains",
        minimum=1,
        maximum=len(CANONICAL_DOMAINS),
    )
    if minimum != minimum_domains:
        _fail("abstention and state minimum observed domains differ")
    reasons = _string_list(
        payload["allowed_reasons"],
        field="abstention.allowed_reasons",
        minimum=1,
        maximum=len(_ABSTENTION_REASONS),
        allowed=_ABSTENTION_REASONS,
    )
    if "policy_expired" not in reasons:
        _fail("abstention.allowed_reasons must include policy_expired")
    return {
        "required": True,
        "minimum_observed_domains": minimum,
        "allowed_reasons": reasons,
    }


def _validate_expiry(
    value: object, *, registered_at: datetime, live_forward_start: datetime
) -> dict[str, Any]:
    payload = _require_fields(value, _EXPIRY_FIELDS, field="expiry")
    expires = _exact_utc(payload["expires_at"], field="expiry.expires_at")
    if expires <= registered_at:
        _fail("trial expiry must follow registration")
    if expires <= live_forward_start:
        _fail("trial expiry must leave a non-empty live-forward window")
    if payload["action"] != "abstain":
        _fail("expired trial action must be abstain")
    return {"expires_at": _format_utc(expires), "action": "abstain"}


def _validate_demotion(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _DEMOTION_FIELDS, field="demotion")
    if payload["enabled"] is not True:
        _fail("continuous demotion must be enabled")
    triggers = _string_list(
        payload["triggers"],
        field="demotion.triggers",
        minimum=1,
        maximum=len(_DEMOTION_TRIGGERS),
        allowed=_DEMOTION_TRIGGERS,
    )
    return {"enabled": True, "triggers": triggers}


def _validate_implementation(value: object) -> dict[str, str]:
    """Freeze the exact model and executable artifacts before opportunities occur."""

    payload = _require_fields(
        value, _IMPLEMENTATION_FIELDS, field="trial implementation"
    )
    return {
        "model_sha256": _sha256(
            payload["model_sha256"], field="implementation.model_sha256"
        ),
        "code_sha256": _sha256(
            payload["code_sha256"], field="implementation.code_sha256"
        ),
        "config_sha256": _sha256(
            payload["config_sha256"], field="implementation.config_sha256"
        ),
    }


def build_trial_registration(
    *,
    trial_key: str,
    registered_at: str,
    state_requirements: Mapping[str, Any],
    target: Mapping[str, Any],
    marks: Mapping[str, Any],
    horizon: Mapping[str, Any],
    distribution: Mapping[str, Any],
    proper_score: Mapping[str, Any],
    baselines: Sequence[Mapping[str, Any]],
    splits: Mapping[str, Any],
    purge: Mapping[str, Any],
    embargo: Mapping[str, Any],
    dependence: Mapping[str, Any],
    trial_budget: Mapping[str, Any],
    abstention: Mapping[str, Any],
    expiry: Mapping[str, Any],
    demotion: Mapping[str, Any],
    implementation: Mapping[str, Any],
) -> dict[str, Any]:
    """Content-address one complete preregistration before opportunities occur."""

    clean_target = _validate_target(target, allow_missing_digest=True)
    clean_marks = _validate_marks(marks)
    clean_horizon = _validate_horizon(horizon)
    payload: dict[str, Any] = {
        "schema": TRIAL_REGISTRATION_SCHEMA,
        "trial_registration_id": "",
        "trial_key": trial_key,
        "registered_at": registered_at,
        "state_requirements": dict(state_requirements),
        "target": clean_target,
        "marks": clean_marks,
        "horizon": clean_horizon,
        "outcome_definition_sha256": _outcome_definition_sha256(
            target=clean_target,
            marks=clean_marks,
            horizon=clean_horizon,
        ),
        "distribution": dict(distribution),
        "proper_score": dict(proper_score),
        "baselines": [dict(item) for item in baselines],
        "splits": dict(splits),
        "purge": dict(purge),
        "embargo": dict(embargo),
        "dependence": dict(dependence),
        "trial_budget": dict(trial_budget),
        "abstention": dict(abstention),
        "expiry": dict(expiry),
        "demotion": dict(demotion),
        "implementation": dict(implementation),
        "emission_enabled": False,
        "authority": dict(AUTHORITY),
    }
    payload["trial_registration_id"] = _content_id(
        "mmtrial_", payload, field="trial_registration_id"
    )
    return validate_trial_registration(payload)


def validate_trial_registration(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach a frozen trial registration."""

    payload = _require_fields(value, _TRIAL_FIELDS, field="trial_registration")
    _bounded_canonical_bytes(payload, field="trial_registration")
    if payload["schema"] != TRIAL_REGISTRATION_SCHEMA:
        _fail("trial registration schema drift")
    trial_id = _match(
        payload["trial_registration_id"], _TRIAL_ID, field="trial_registration_id"
    )
    trial_key = _opaque(payload["trial_key"], field="trial_key")
    registered = _exact_utc(payload["registered_at"], field="registered_at")
    state_requirements = _validate_state_requirements(payload["state_requirements"])
    target = _validate_target(payload["target"])
    marks = _validate_marks(payload["marks"])
    horizon = _validate_horizon(payload["horizon"])
    outcome_definition_sha = _sha256(
        payload["outcome_definition_sha256"], field="outcome_definition_sha256"
    )
    if outcome_definition_sha != _outcome_definition_sha256(
        target=target, marks=marks, horizon=horizon
    ):
        _fail("outcome_definition_sha256 does not bind target, marks, and horizon")
    distribution = _validate_distribution_spec(payload["distribution"], target=target)
    proper_score = _validate_proper_score(
        payload["proper_score"], distribution_kind=distribution["kind"]
    )
    baselines = _validate_baselines(payload["baselines"])
    splits = _validate_splits(payload["splits"], registered_at=registered)
    purge = _validate_purge(
        payload["purge"], horizon_end_seconds=horizon["end_offset_seconds"]
    )
    embargo = _validate_embargo(payload["embargo"])
    dependence = _validate_dependence(payload["dependence"])
    trial_budget = _validate_trial_budget(payload["trial_budget"])
    abstention = _validate_abstention(
        payload["abstention"],
        minimum_domains=state_requirements["minimum_observed_domains"],
    )
    expiry = _validate_expiry(
        payload["expiry"],
        registered_at=registered,
        live_forward_start=_exact_utc(
            splits["live_forward_start"], field="splits.live_forward_start"
        ),
    )
    demotion = _validate_demotion(payload["demotion"])
    implementation = _validate_implementation(payload["implementation"])
    if payload["emission_enabled"] is not False:
        _fail("trial registration emission must remain disabled")
    authority = _validate_authority(payload["authority"], field="trial authority")
    clean: dict[str, Any] = {
        "schema": TRIAL_REGISTRATION_SCHEMA,
        "trial_registration_id": trial_id,
        "trial_key": trial_key,
        "registered_at": _format_utc(registered),
        "state_requirements": state_requirements,
        "target": target,
        "marks": marks,
        "horizon": horizon,
        "outcome_definition_sha256": outcome_definition_sha,
        "distribution": distribution,
        "proper_score": proper_score,
        "baselines": baselines,
        "splits": splits,
        "purge": purge,
        "embargo": embargo,
        "dependence": dependence,
        "trial_budget": trial_budget,
        "abstention": abstention,
        "expiry": expiry,
        "demotion": demotion,
        "implementation": implementation,
        "emission_enabled": False,
        "authority": authority,
    }
    if not _exact_json_equal(payload, clean, field="trial_registration"):
        _fail("trial registration is not exact canonical JSON")
    if trial_id != _content_id("mmtrial_", clean, field="trial_registration_id"):
        _fail("trial_registration_id does not bind canonical content")
    return _detached(clean, field="trial_registration")


def load_trial_registration_json(body: bytes) -> dict[str, Any]:
    """Strictly parse and validate one trial registration."""

    return validate_trial_registration(
        _strict_json_object(body, field="trial_registration")
    )


def _outcome_event_id(
    *,
    context_id: str,
    outcome_definition_sha256: str,
    horizon_start: str,
    horizon_end: str,
    evaluation_at: str,
) -> str:
    preimage = {
        "context_id": context_id,
        "outcome_definition_sha256": outcome_definition_sha256,
        "horizon_start": horizon_start,
        "horizon_end": horizon_end,
        "evaluation_at": evaluation_at,
    }
    return (
        "mmoutcomeevent_"
        + hashlib.sha256(
            _bounded_canonical_bytes(preimage, field="outcome event preimage")
        ).hexdigest()
    )


def _forecast_key(
    *, trial_registration_id: str, state_snapshot_id: str, outcome_event_id: str
) -> str:
    preimage = {
        "trial_registration_id": trial_registration_id,
        "state_snapshot_id": state_snapshot_id,
        "outcome_event_id": outcome_event_id,
    }
    return (
        "mmforecastkey_"
        + hashlib.sha256(
            _bounded_canonical_bytes(preimage, field="forecast key preimage")
        ).hexdigest()
    )


def _validate_predictive_distribution(value: object) -> dict[str, Any]:
    payload = _require_fields(
        value, _PREDICTIVE_DISTRIBUTION_FIELDS, field="predictive_distribution"
    )
    kind = payload["kind"]
    if kind not in {"scalar", "quantiles", "categorical"}:
        _fail("predictive_distribution.kind is unsupported")
    point = payload["point"]
    quantiles_raw = payload["quantiles"]
    probabilities_raw = payload["probabilities"]
    if type(quantiles_raw) is not list or len(quantiles_raw) > 32:
        _fail("predictive_distribution.quantiles exceeds its bound")
    if type(probabilities_raw) is not list or len(probabilities_raw) > 32:
        _fail("predictive_distribution.probabilities exceeds its bound")
    quantiles: list[dict[str, Any]] = []
    for item in quantiles_raw:
        row = _require_fields(item, _QUANTILE_FIELDS, field="forecast quantile")
        quantiles.append(
            {
                "level": _probability_level(
                    row["level"], field="forecast quantile level"
                ),
                "value": _number(row["value"], field="forecast quantile value"),
            }
        )
    levels = [item["level"] for item in quantiles]
    if levels != sorted(set(levels)):
        _fail("forecast quantiles must be sorted and unique")
    if any(left["value"] > right["value"] for left, right in pairwise(quantiles)):
        _fail("forecast quantile values must be nondecreasing")
    probabilities: list[dict[str, Any]] = []
    for item in probabilities_raw:
        row = _require_fields(
            item, _PROBABILITY_FIELDS, field="forecast category probability"
        )
        probability = _number(row["probability"], field="forecast category probability")
        if not 0 <= probability <= 1:
            _fail("forecast category probability is outside [0,1]")
        probabilities.append(
            {
                "category": _opaque(
                    row["category"], field="forecast probability category"
                ),
                "probability": probability,
            }
        )
    categories = [item["category"] for item in probabilities]
    if categories != sorted(set(categories)):
        _fail("forecast probability categories must be sorted and unique")
    if kind == "scalar":
        clean_point: int | float | None = _number(point, field="forecast point")
        if quantiles or probabilities:
            _fail("scalar forecast cannot carry quantiles or probabilities")
    elif kind == "quantiles":
        clean_point = None
        if point is not None or not quantiles or probabilities:
            _fail("quantile forecast must carry only quantiles")
    else:
        clean_point = None
        if point is not None or quantiles or len(probabilities) < 2:
            _fail("categorical forecast must carry only category probabilities")
        probability_total = sum(
            (Fraction(Decimal(str(item["probability"]))) for item in probabilities),
            Fraction(0),
        )
        if probability_total != 1:
            _fail("forecast category probabilities must sum to one")
    return {
        "kind": kind,
        "point": clean_point,
        "quantiles": quantiles,
        "probabilities": probabilities,
    }


def _validate_distribution_against_spec(
    value: Mapping[str, Any], *, spec: Mapping[str, Any]
) -> None:
    if value["kind"] != spec["kind"]:
        _fail("forecast distribution kind differs from preregistration")
    if value["kind"] == "quantiles":
        if [row["level"] for row in value["quantiles"]] != spec["quantile_levels"]:
            _fail("forecast quantile grid differs from preregistration")
    elif (
        value["kind"] == "categorical"
        and [row["category"] for row in value["probabilities"]] != spec["categories"]
    ):
        _fail("forecast categories differ from preregistration")


def _validate_forecast_times(payload: Mapping[str, Any]) -> dict[str, str]:
    as_known_at = _exact_utc(payload["as_known_at"], field="forecast.as_known_at")
    decision = _exact_utc(payload["decision_cutoff"], field="forecast.decision_cutoff")
    sealed = _exact_utc(payload["sealed_at"], field="forecast.sealed_at")
    start = _exact_utc(payload["horizon_start"], field="forecast.horizon_start")
    end = _exact_utc(payload["horizon_end"], field="forecast.horizon_end")
    evaluation = _exact_utc(payload["evaluation_at"], field="forecast.evaluation_at")
    if as_known_at != decision:
        _fail("forecast as_known_at and decision_cutoff must be identical")
    if not decision <= sealed < start < end:
        _fail(
            "forecast requires decision_cutoff <= sealed_at < horizon_start < horizon_end"
        )
    if evaluation != end:
        _fail("forecast evaluation_at must equal horizon_end")
    return {
        "as_known_at": _format_utc(as_known_at),
        "decision_cutoff": _format_utc(decision),
        "sealed_at": _format_utc(sealed),
        "horizon_start": _format_utc(start),
        "horizon_end": _format_utc(end),
        "evaluation_at": _format_utc(evaluation),
    }


def validate_forecast_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one stored ForecastRecord without external mutable inputs."""

    payload = _require_fields(value, _FORECAST_FIELDS, field="forecast_record")
    _bounded_canonical_bytes(payload, field="forecast_record")
    if payload["schema"] != FORECAST_RECORD_SCHEMA:
        _fail("forecast record schema drift")
    forecast_id = _match(payload["forecast_id"], _FORECAST_ID, field="forecast_id")
    forecast_key = _match(payload["forecast_key"], _FORECAST_KEY, field="forecast_key")
    event_id = _match(
        payload["outcome_event_id"], _OUTCOME_EVENT_ID, field="outcome_event_id"
    )
    trial_id = _match(
        payload["trial_registration_id"], _TRIAL_ID, field="trial_registration_id"
    )
    trial_key = _opaque(payload["trial_key"], field="trial_key")
    state_id = _match(
        payload["state_snapshot_id"], _STATE_ID, field="state_snapshot_id"
    )
    context_id = _match(payload["context_id"], _CONTEXT_ID, field="context_id")
    times = _validate_forecast_times(payload)
    disposition = payload["disposition"]
    if disposition not in {"issued", "abstained"}:
        _fail("forecast disposition must be issued or abstained")
    reason = payload["abstention_reason"]
    distribution: dict[str, Any] | None
    if disposition == "issued":
        if reason is not None or payload["predictive_distribution"] is None:
            _fail("issued forecast requires a distribution and no abstention reason")
        distribution = _validate_predictive_distribution(
            payload["predictive_distribution"]
        )
    else:
        if (
            reason not in _ABSTENTION_REASONS
            or payload["predictive_distribution"] is not None
        ):
            _fail("abstained forecast requires a canonical reason and no distribution")
        distribution = None
    plan_sha = _sha256(payload["plan_sha256"], field="plan_sha256")
    target_sha = _sha256(payload["target_sha256"], field="target_sha256")
    outcome_definition_sha = _sha256(
        payload["outcome_definition_sha256"], field="outcome_definition_sha256"
    )
    model_sha = _sha256(payload["model_sha256"], field="model_sha256")
    code_sha = _sha256(payload["code_sha256"], field="code_sha256")
    config_sha = _sha256(payload["config_sha256"], field="config_sha256")
    baselines = _validate_baselines(payload["baseline_refs"])
    expected_event = _outcome_event_id(
        context_id=context_id,
        outcome_definition_sha256=outcome_definition_sha,
        horizon_start=times["horizon_start"],
        horizon_end=times["horizon_end"],
        evaluation_at=times["evaluation_at"],
    )
    if event_id != expected_event:
        _fail("outcome_event_id does not bind outcome definition, context, and horizon")
    expected_key = _forecast_key(
        trial_registration_id=trial_id,
        state_snapshot_id=state_id,
        outcome_event_id=event_id,
    )
    if forecast_key != expected_key:
        _fail("forecast_key does not bind the planned opportunity and trial")
    if payload["emission_enabled"] is not False:
        _fail("forecast emission must remain disabled")
    authority = _validate_authority(payload["authority"], field="forecast authority")
    clean: dict[str, Any] = {
        "schema": FORECAST_RECORD_SCHEMA,
        "forecast_id": forecast_id,
        "forecast_key": forecast_key,
        "outcome_event_id": event_id,
        "trial_registration_id": trial_id,
        "trial_key": trial_key,
        "state_snapshot_id": state_id,
        "context_id": context_id,
        **times,
        "disposition": disposition,
        "abstention_reason": reason,
        "plan_sha256": plan_sha,
        "target_sha256": target_sha,
        "outcome_definition_sha256": outcome_definition_sha,
        "model_sha256": model_sha,
        "code_sha256": code_sha,
        "config_sha256": config_sha,
        "predictive_distribution": distribution,
        "baseline_refs": baselines,
        "emission_enabled": False,
        "authority": authority,
    }
    if not _exact_json_equal(payload, clean, field="forecast_record"):
        _fail("forecast record is not exact canonical JSON")
    if forecast_id != _content_id("mmforecast_", clean, field="forecast_id"):
        _fail("forecast_id does not bind canonical content")
    return _detached(clean, field="forecast_record")


def _validate_forecast_trial_join(
    clean: Mapping[str, Any], *, trial: Mapping[str, Any]
) -> None:
    """Bind a structurally valid forecast to every preregistered choice."""

    if clean["trial_registration_id"] != trial["trial_registration_id"]:
        _fail("forecast trial_registration_id differs from preregistration")
    if clean["trial_key"] != trial["trial_key"]:
        _fail("forecast trial_key differs from preregistration")
    expected_plan_sha = hashlib.sha256(
        _bounded_canonical_bytes(trial, field="trial plan hash")
    ).hexdigest()
    if clean["plan_sha256"] != expected_plan_sha:
        _fail("forecast plan_sha256 differs from exact preregistration")
    if clean["target_sha256"] != trial["target"]["target_sha256"]:
        _fail("forecast target_sha256 differs from preregistration")
    if clean["outcome_definition_sha256"] != trial["outcome_definition_sha256"]:
        _fail("forecast outcome_definition_sha256 differs from preregistration")
    if not _exact_json_equal(
        clean["baseline_refs"], trial["baselines"], field="forecast baseline refs"
    ):
        _fail("forecast baseline refs differ from preregistration")
    for field in ("model_sha256", "code_sha256", "config_sha256"):
        if clean[field] != trial["implementation"][field]:
            _fail(f"forecast {field} differs from preregistration")

    decision = _exact_utc(clean["decision_cutoff"], field="decision_cutoff")
    expected_start = decision + timedelta(
        seconds=trial["horizon"]["start_offset_seconds"]
    )
    expected_end = decision + timedelta(seconds=trial["horizon"]["end_offset_seconds"])
    if clean["horizon_start"] != _format_utc(expected_start):
        _fail("forecast horizon_start differs from preregistered rule")
    if clean["horizon_end"] != _format_utc(expected_end):
        _fail("forecast horizon_end differs from preregistered rule")
    if clean["evaluation_at"] != _format_utc(expected_end):
        _fail("forecast evaluation_at differs from preregistered rule")
    registered = _exact_utc(trial["registered_at"], field="registered_at")
    if registered > decision:
        _fail("trial was not registered by the forecast decision cutoff")
    live_forward_start = _exact_utc(
        trial["splits"]["live_forward_start"], field="live_forward_start"
    )
    if decision < live_forward_start:
        _fail("forecast decision precedes the preregistered live-forward split")
    sealed = _exact_utc(clean["sealed_at"], field="sealed_at")
    expired = sealed >= _exact_utc(trial["expiry"]["expires_at"], field="expires_at")
    if expired and not (
        clean["disposition"] == "abstained"
        and clean["abstention_reason"] == "policy_expired"
    ):
        _fail("expired preregistration must abstain with policy_expired")
    if not expired and clean["abstention_reason"] == "policy_expired":
        _fail("unexpired preregistration cannot claim policy_expired")
    if clean["disposition"] == "abstained":
        if clean["abstention_reason"] not in trial["abstention"]["allowed_reasons"]:
            _fail("forecast abstention reason was not preregistered")
    else:
        assert clean["predictive_distribution"] is not None
        _validate_distribution_against_spec(
            clean["predictive_distribution"], spec=trial["distribution"]
        )


def validate_forecast_record_join(
    value: Mapping[str, Any],
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    exact_context_bytes: bytes,
) -> dict[str, Any]:
    """Revalidate a ForecastRecord against its exact trial, state, and W1 bytes."""

    clean = validate_forecast_record(value)
    trial = validate_trial_registration(trial_registration)
    state = validate_state_snapshot(
        state_snapshot, exact_context_bytes=exact_context_bytes
    )
    _validate_forecast_trial_join(clean, trial=trial)
    if clean["state_snapshot_id"] != state["state_snapshot_id"]:
        _fail("forecast state_snapshot_id differs from admitted state")
    if clean["context_id"] != state["context_id"]:
        _fail("forecast context_id differs from admitted state")
    if clean["as_known_at"] != state["as_known_at"]:
        _fail("forecast cannot mutate the state as_known_at clock")
    domain_status = {row["domain"]: row["status"] for row in state["domain_states"]}
    observed_count = state["coverage"]["n_observed_domains"]
    minimum = trial["state_requirements"]["minimum_observed_domains"]
    required = trial["state_requirements"]["required_observed_domains"]
    requirements_met = observed_count >= minimum and all(
        domain_status[domain] == "observed" for domain in required
    )
    if clean["disposition"] == "issued" and not requirements_met:
        _fail("forecast issued despite unmet preregistered state requirements")
    if clean["disposition"] == "abstained":
        if (
            clean["abstention_reason"] == "insufficient_domains"
            and observed_count >= minimum
        ):
            _fail("forecast falsely claims insufficient domains")
        if clean["abstention_reason"] == "required_domain_missing" and all(
            domain_status[domain] == "observed" for domain in required
        ):
            _fail("forecast falsely claims a required domain is missing")
    return clean


def build_forecast_record(
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    exact_context_bytes: bytes,
    sealed_at: str,
    disposition: str,
    abstention_reason: str | None,
    model_sha256: str,
    code_sha256: str,
    config_sha256: str,
    predictive_distribution: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Seal one issued or abstained opportunity before its horizon starts."""

    trial = validate_trial_registration(trial_registration)
    state = validate_state_snapshot(
        state_snapshot, exact_context_bytes=exact_context_bytes
    )
    decision = _exact_utc(state["as_known_at"], field="state as_known_at")
    start = decision + timedelta(seconds=trial["horizon"]["start_offset_seconds"])
    end = decision + timedelta(seconds=trial["horizon"]["end_offset_seconds"])
    start_text = _format_utc(start)
    end_text = _format_utc(end)
    target_sha = trial["target"]["target_sha256"]
    outcome_definition_sha = trial["outcome_definition_sha256"]
    event_id = _outcome_event_id(
        context_id=state["context_id"],
        outcome_definition_sha256=outcome_definition_sha,
        horizon_start=start_text,
        horizon_end=end_text,
        evaluation_at=end_text,
    )
    key = _forecast_key(
        trial_registration_id=trial["trial_registration_id"],
        state_snapshot_id=state["state_snapshot_id"],
        outcome_event_id=event_id,
    )
    payload: dict[str, Any] = {
        "schema": FORECAST_RECORD_SCHEMA,
        "forecast_id": "",
        "forecast_key": key,
        "outcome_event_id": event_id,
        "trial_registration_id": trial["trial_registration_id"],
        "trial_key": trial["trial_key"],
        "state_snapshot_id": state["state_snapshot_id"],
        "context_id": state["context_id"],
        "as_known_at": state["as_known_at"],
        "decision_cutoff": state["as_known_at"],
        "sealed_at": sealed_at,
        "horizon_start": start_text,
        "horizon_end": end_text,
        "evaluation_at": end_text,
        "disposition": disposition,
        "abstention_reason": abstention_reason,
        "plan_sha256": hashlib.sha256(
            _bounded_canonical_bytes(trial, field="trial plan hash")
        ).hexdigest(),
        "target_sha256": target_sha,
        "outcome_definition_sha256": outcome_definition_sha,
        "model_sha256": model_sha256,
        "code_sha256": code_sha256,
        "config_sha256": config_sha256,
        "predictive_distribution": dict(predictive_distribution)
        if predictive_distribution is not None
        else None,
        "baseline_refs": copy.deepcopy(trial["baselines"]),
        "emission_enabled": False,
        "authority": dict(AUTHORITY),
    }
    payload["forecast_id"] = _content_id("mmforecast_", payload, field="forecast_id")
    return validate_forecast_record_join(
        payload,
        trial_registration=trial,
        state_snapshot=state,
        exact_context_bytes=exact_context_bytes,
    )


def load_forecast_record_json(body: bytes) -> dict[str, Any]:
    """Strictly parse a self-authenticating ForecastRecord."""

    return validate_forecast_record(_strict_json_object(body, field="forecast_record"))


def load_forecast_record_join_json(
    body: bytes,
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    exact_context_bytes: bytes,
) -> dict[str, Any]:
    """Parse a ForecastRecord and revalidate all immutable joins."""

    return validate_forecast_record_join(
        _strict_json_object(body, field="forecast_record"),
        trial_registration=trial_registration,
        state_snapshot=state_snapshot,
        exact_context_bytes=exact_context_bytes,
    )


def _validate_outcome_value(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _OUTCOME_VALUE_FIELDS, field="outcome_value")
    value_type = payload["value_type"]
    if value_type == "number":
        clean_value: str | int | float = _number(
            payload["value"], field="outcome_value.value"
        )
    elif value_type == "integer":
        if (
            type(payload["value"]) is not int
            or not -_MAX_ABSOLUTE_NUMBER <= payload["value"] <= _MAX_ABSOLUTE_NUMBER
        ):
            _fail("integer outcome value must be int, not bool")
        clean_value = payload["value"]
    elif value_type == "string":
        clean_value = _opaque(
            payload["value"], field="outcome_value.value", maximum=128
        )
    else:
        _fail("outcome_value.value_type is unsupported")
    return {
        "value_type": value_type,
        "value": clean_value,
        "unit": _opaque(payload["unit"], field="outcome_value.unit", maximum=64),
    }


def _validate_outcome_sources(value: object) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > 32:
        _fail("outcome source_receipts exceeds its array bound")
    clean: list[dict[str, Any]] = []
    for item in value:
        row = _require_fields(
            item, _OUTCOME_SOURCE_FIELDS, field="outcome source receipt"
        )
        clean.append(
            {
                "receipt_id": _opaque(
                    row["receipt_id"], field="outcome source receipt_id"
                ),
                "artifact_sha256": _sha256(
                    row["artifact_sha256"],
                    field="outcome source artifact_sha256",
                ),
                "source_schema": _opaque(
                    row["source_schema"], field="outcome source schema"
                ),
                "source_version": _opaque(
                    row["source_version"], field="outcome source version"
                ),
            }
        )
    ids = [item["receipt_id"] for item in clean]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("outcome source receipts must be sorted and unique")
    return clean


def validate_outcome_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach one append-only outcome revision."""

    payload = _require_fields(value, _OUTCOME_FIELDS, field="outcome_record")
    _bounded_canonical_bytes(payload, field="outcome_record")
    if payload["schema"] != OUTCOME_RECORD_SCHEMA:
        _fail("outcome record schema drift")
    record_id = _match(
        payload["outcome_record_id"], _OUTCOME_ID, field="outcome_record_id"
    )
    event_id = _match(
        payload["outcome_event_id"], _OUTCOME_EVENT_ID, field="outcome_event_id"
    )
    context_id = _match(payload["context_id"], _CONTEXT_ID, field="context_id")
    target_sha = _sha256(payload["target_sha256"], field="target_sha256")
    outcome_definition_sha = _sha256(
        payload["outcome_definition_sha256"], field="outcome_definition_sha256"
    )
    start = _exact_utc(payload["horizon_start"], field="outcome.horizon_start")
    end = _exact_utc(payload["horizon_end"], field="outcome.horizon_end")
    evaluation = _exact_utc(payload["evaluation_at"], field="outcome.evaluation_at")
    if not start < end or evaluation != end:
        _fail("outcome horizon must end after start and evaluation must equal end")
    expected_event = _outcome_event_id(
        context_id=context_id,
        outcome_definition_sha256=outcome_definition_sha,
        horizon_start=_format_utc(start),
        horizon_end=_format_utc(end),
        evaluation_at=_format_utc(evaluation),
    )
    if event_id != expected_event:
        _fail("outcome_event_id does not bind its immutable event definition")
    status = payload["status"]
    if status not in {"complete", "censored", "missing"}:
        _fail("outcome status is unsupported")
    reason = payload["reason"]
    outcome_value: dict[str, Any] | None
    if status == "complete":
        if reason is not None or payload["outcome_value"] is None:
            _fail("complete outcome requires a value and no reason")
        outcome_value = _validate_outcome_value(payload["outcome_value"])
    elif status == "censored":
        if (
            reason
            not in {
                "source_window_incomplete",
                "instrument_unavailable",
                "event_invalidated",
                "coverage_ended",
            }
            or payload["outcome_value"] is not None
        ):
            _fail("censored outcome requires a canonical reason and null value")
        outcome_value = None
    else:
        if (
            reason
            not in {
                "source_unavailable",
                "source_not_published",
                "identity_unresolved",
                "quality_gate_failed",
            }
            or payload["outcome_value"] is not None
        ):
            _fail("missing outcome requires a canonical reason and null value")
        outcome_value = None
    effective = _exact_utc(payload["effective_at"], field="outcome.effective_at")
    available = _exact_utc(
        payload["source_available_at"], field="outcome.source_available_at"
    )
    known = _exact_utc(payload["known_at"], field="outcome.known_at")
    observed = _exact_utc(payload["observed_at"], field="outcome.observed_at")
    recorded = _exact_utc(payload["recorded_at"], field="outcome.recorded_at")
    if effective != end:
        _fail("outcome effective_at must equal forecast horizon/evaluation end")
    if not effective <= available <= known <= observed <= recorded:
        _fail(
            "outcome clocks violate effective/available/known/observed/recorded order"
        )
    sources = _validate_outcome_sources(payload["source_receipts"])
    if status == "complete" and not sources:
        _fail("complete outcome requires at least one source receipt")
    revision_number = _exact_int(
        payload["revision_number"],
        field="outcome.revision_number",
        minimum=1,
        maximum=10**6,
    )
    revision_of = payload["revision_of"]
    revision_reason = payload["revision_reason"]
    if revision_number == 1:
        if revision_of is not None or revision_reason is not None:
            _fail("first outcome revision cannot name a predecessor or reason")
        clean_revision_of = None
        clean_revision_reason = None
    else:
        clean_revision_of = _match(
            revision_of, _OUTCOME_ID, field="outcome.revision_of"
        )
        if clean_revision_of == record_id:
            _fail("outcome revision cannot name itself as predecessor")
        if revision_reason not in _REVISION_REASONS:
            _fail("outcome revision requires a canonical revision reason")
        clean_revision_reason = revision_reason
    if payload["emission_enabled"] is not False:
        _fail("outcome emission must remain disabled")
    authority = _validate_authority(payload["authority"], field="outcome authority")
    clean: dict[str, Any] = {
        "schema": OUTCOME_RECORD_SCHEMA,
        "outcome_record_id": record_id,
        "outcome_event_id": event_id,
        "context_id": context_id,
        "target_sha256": target_sha,
        "outcome_definition_sha256": outcome_definition_sha,
        "horizon_start": _format_utc(start),
        "horizon_end": _format_utc(end),
        "evaluation_at": _format_utc(evaluation),
        "status": status,
        "outcome_value": outcome_value,
        "reason": reason,
        "effective_at": _format_utc(effective),
        "source_available_at": _format_utc(available),
        "known_at": _format_utc(known),
        "observed_at": _format_utc(observed),
        "recorded_at": _format_utc(recorded),
        "source_receipts": sources,
        "revision_number": revision_number,
        "revision_of": clean_revision_of,
        "revision_reason": clean_revision_reason,
        "emission_enabled": False,
        "authority": authority,
    }
    if not _exact_json_equal(payload, clean, field="outcome_record"):
        _fail("outcome record is not exact canonical JSON")
    if record_id != _content_id("mmoutcome_", clean, field="outcome_record_id"):
        _fail("outcome_record_id does not bind canonical content")
    return _detached(clean, field="outcome_record")


def build_outcome_record(
    *,
    outcome_event_id: str,
    context_id: str,
    target_sha256: str,
    outcome_definition_sha256: str,
    horizon_start: str,
    horizon_end: str,
    evaluation_at: str,
    status: str,
    outcome_value: Mapping[str, Any] | None,
    reason: str | None,
    effective_at: str,
    source_available_at: str,
    known_at: str,
    observed_at: str,
    recorded_at: str,
    source_receipts: Sequence[Mapping[str, Any]],
    revision_number: int = 1,
    revision_of: str | None = None,
    revision_reason: str | None = None,
) -> dict[str, Any]:
    """Build one immutable outcome revision without mutating any forecast."""

    payload: dict[str, Any] = {
        "schema": OUTCOME_RECORD_SCHEMA,
        "outcome_record_id": "",
        "outcome_event_id": outcome_event_id,
        "context_id": context_id,
        "target_sha256": target_sha256,
        "outcome_definition_sha256": outcome_definition_sha256,
        "horizon_start": horizon_start,
        "horizon_end": horizon_end,
        "evaluation_at": evaluation_at,
        "status": status,
        "outcome_value": dict(outcome_value) if outcome_value is not None else None,
        "reason": reason,
        "effective_at": effective_at,
        "source_available_at": source_available_at,
        "known_at": known_at,
        "observed_at": observed_at,
        "recorded_at": recorded_at,
        "source_receipts": [dict(item) for item in source_receipts],
        "revision_number": revision_number,
        "revision_of": revision_of,
        "revision_reason": revision_reason,
        "emission_enabled": False,
        "authority": dict(AUTHORITY),
    }
    payload["outcome_record_id"] = _content_id(
        "mmoutcome_", payload, field="outcome_record_id"
    )
    return validate_outcome_record(payload)


def validate_outcome_record_join(
    value: Mapping[str, Any],
    *,
    forecast_record: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind an outcome fact to one forecast event and its frozen target semantics."""

    clean = validate_outcome_record(value)
    forecast = validate_forecast_record(forecast_record)
    trial = validate_trial_registration(trial_registration)
    _validate_forecast_trial_join(forecast, trial=trial)
    for field in (
        "outcome_event_id",
        "context_id",
        "target_sha256",
        "outcome_definition_sha256",
        "horizon_start",
        "horizon_end",
        "evaluation_at",
    ):
        if clean[field] != forecast[field]:
            _fail(f"outcome {field} differs from the sealed forecast event")
    if clean["effective_at"] != forecast["evaluation_at"]:
        _fail("outcome effective_at differs from forecast evaluation_at")
    if clean["target_sha256"] != trial["target"]["target_sha256"]:
        _fail("outcome target differs from preregistration")
    if clean["outcome_definition_sha256"] != trial["outcome_definition_sha256"]:
        _fail("outcome definition differs from preregistration")
    if clean["status"] == "complete":
        outcome_value = clean["outcome_value"]
        assert outcome_value is not None
        target = trial["target"]
        if outcome_value["value_type"] != target["value_type"]:
            _fail("outcome value_type differs from preregistered target")
        if outcome_value["unit"] != target["unit"]:
            _fail("outcome unit differs from preregistered target")
        if (
            target["value_type"] == "string"
            and outcome_value["value"] not in target["categories"]
        ):
            _fail("outcome category was not preregistered")
    return clean


def validate_outcome_record_revision(
    value: Mapping[str, Any],
    *,
    previous_outcome: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate an initial outcome or one correction against the active predecessor."""

    clean = validate_outcome_record(value)
    if previous_outcome is None:
        if clean["revision_number"] != 1 or clean["revision_of"] is not None:
            _fail("first outcome revision must be 1 with no predecessor")
        return clean
    previous = validate_outcome_record(previous_outcome)
    if clean["outcome_event_id"] != previous["outcome_event_id"]:
        _fail("outcome correction changed outcome_event_id")
    for field in (
        "context_id",
        "target_sha256",
        "outcome_definition_sha256",
        "horizon_start",
        "horizon_end",
        "evaluation_at",
        "effective_at",
    ):
        if clean[field] != previous[field]:
            _fail(f"outcome correction changed immutable {field}")
    if clean["revision_number"] != previous["revision_number"] + 1:
        _fail("outcome correction skipped or repeated a revision number")
    if clean["revision_of"] != previous["outcome_record_id"]:
        _fail("outcome correction does not name the active predecessor")
    for field in ("source_available_at", "known_at", "observed_at", "recorded_at"):
        if _exact_utc(clean[field], field=f"correction {field}") < _exact_utc(
            previous[field], field=f"previous {field}"
        ):
            _fail(f"outcome correction rewound {field}")
    if clean["recorded_at"] == previous["recorded_at"]:
        _fail("outcome correction must have a later recorded_at")
    return clean


def load_outcome_record_json(body: bytes) -> dict[str, Any]:
    """Strictly parse and validate one immutable outcome revision."""

    return validate_outcome_record(_strict_json_object(body, field="outcome_record"))


__all__ = [
    "AUTHORITY",
    "CANONICAL_DOMAINS",
    "FORECAST_RECORD_SCHEMA",
    "OUTCOME_RECORD_SCHEMA",
    "STATE_SNAPSHOT_SCHEMA",
    "TRIAL_REGISTRATION_SCHEMA",
    "MarketMemoryForwardContractError",
    "build_forecast_record",
    "build_outcome_record",
    "build_state_snapshot",
    "build_trial_registration",
    "canonical_json_bytes",
    "load_forecast_record_join_json",
    "load_forecast_record_json",
    "load_outcome_record_json",
    "load_state_snapshot_json",
    "load_state_snapshot_record_json",
    "load_trial_registration_json",
    "validate_forecast_record",
    "validate_forecast_record_join",
    "validate_outcome_record",
    "validate_outcome_record_join",
    "validate_outcome_record_revision",
    "validate_state_snapshot",
    "validate_state_snapshot_record",
    "validate_trial_registration",
]
