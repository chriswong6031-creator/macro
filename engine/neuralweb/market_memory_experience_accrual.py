"""Private prospective SPY experience census and outcome accrual.

W2C is deliberately disjoint from the synthetic W2A forward store.  It owns
one bounded 126-session census, references exact already-published trusted
macro and private technical generations, and seals one terminal opportunity
disposition per expected XNYS session.  It never builds a combined W2 state,
copies source bodies, forecasts, scores, promotes, or emits to an API.

The decision cutoff is the writer clock sampled between two reads of both
current owner HEADs.  A source receipt clock is not publication proof: a
producer may have prepared it and crashed before HEAD.  The sandwich proves
only that the same authenticated, content-addressed generation was observed on
both sides of the local sample under the owners' monotone append-only protocol.
It does not prove continuous stability or detect an unobserved A -> B -> A.
The local cutoff must land inside the registered 04:30-04:45Z window.  A
create-once prepared seal written in that window may finish after a crash;
without one, later reconciliation records ``missed`` and never retro-captures
the state.
"""

from __future__ import annotations

import copy
import fcntl
import json
import math
import os
import re
import stat
import time as time_module
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, NoReturn

from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_technical_store as technical_store
from engine.neuralweb import market_memory_trusted as trusted_store
from lib import nyse_calendar

REGISTRATION_SCHEMA = "market_memory.spy_experience_registration.v1"
OPPORTUNITY_SCHEMA = "market_memory.spy_experience_opportunity.v1"
OUTCOME_SCHEMA = "market_memory.spy_experience_outcome_revision.v1"
POPULATION_SCHEMA = "market_memory.spy_experience_population_receipt.v1"
PREPARED_SCHEMA = "market_memory.spy_experience_prepared.v1"
PREPARED_SEAL_SCHEMA = "market_memory.spy_experience_prepared_seal.v1"
INSTALLATION_SCHEMA = "market_memory.spy_experience_registration_installation.v1"
STORE_SCHEMA = "market_memory.spy_experience_store.v1"
POPULATION_HEAD_SCHEMA = "market_memory.spy_experience_population_head.v1"
TECHNICAL_VIEW_SCHEMA = "market_memory.spy_experience_technical_view.v1"
TECHNICAL_VIEW_HEAD_SCHEMA = "market_memory.spy_experience_technical_view_head.v1"
TERMINAL_MARKER_SCHEMA = "market_memory.spy_experience_terminal_marker.v1"
DECISION_STATE_PROJECTION_SCHEMA = (
    "market_memory.spy_regime_decision_state_projection.v1"
)
SOURCE_REGIME_TRANSFORM_VERSION = "market_memory.macro_regime_transform.v1"
PROFILE = "market_memory.private.spy_experience_accrual.v1"

DEFAULT_REGISTRATION_PATH = Path(
    "config/market_memory_spy_experience_registration.v1.json"
)
ACTIVATION_SESSION = date(2026, 8, 17)
SUNSET_SESSION = date(2027, 2, 16)
FINAL_TARGET_SESSION = date(2027, 2, 23)
CORRECTION_SUNSET_SESSION = date(2027, 3, 2)
TERMINAL_CENSUS_DATE = date(2027, 3, 3)
PILOT_EXPECTED_SESSIONS = 126
OUTCOME_HORIZON_SESSIONS = 5
CORRECTION_OBSERVATION_SESSIONS = 5
MAX_OWNER_GENERATION_CAPTURES = 256
TRUSTED_FUTURE_CAPTURES = 126
TECHNICAL_FUTURE_CAPTURES = 136
REVISION_RESERVE = 32
MAX_OUTCOME_REVISIONS = 4_096
OWNER_PAIR_RETRY_INTERVAL_SECONDS = 30
OWNER_PAIR_MAX_ATTEMPTS = 31

_MAX_REGISTRATION_BYTES = 64 * 1024
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PREPARED_BYTES = 256 * 1024
_MAX_OPPORTUNITY_BYTES = 256 * 1024
_MAX_OUTCOME_BYTES = 256 * 1024
_MAX_POPULATION_BYTES = 2 * 1024 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_MAX_INSTALLATION_BYTES = 64 * 1024
_MAX_TECHNICAL_VIEW_BYTES = 2 * 1024 * 1024
_MAX_TERMINAL_BYTES = 64 * 1024
_MAX_EXACT_DECIMAL_CHARS = 768

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_SESSION = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)
_REGISTRATION_ID = re.compile(r"mmspyexpreg_[a-f0-9]{64}\Z")
_PREPARED_ID = re.compile(r"mmspyexpprep_[a-f0-9]{64}\Z")
_OPPORTUNITY_ID = re.compile(r"mmspyexpopp_[a-f0-9]{64}\Z")
_OUTCOME_ID = re.compile(r"mmspyexpout_[a-f0-9]{64}\Z")
_POPULATION_ID = re.compile(r"mmspyexppop_[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmspyexpstore_[a-f0-9]{64}\Z")
_INSTALLATION_ID = re.compile(r"mmspyexpinstall_[a-f0-9]{64}\Z")
_TECHNICAL_VIEW_ID = re.compile(r"mmspyexptechview_[a-f0-9]{64}\Z")
_TERMINAL_ID = re.compile(r"mmspyexpterminal_[a-f0-9]{64}\Z")

_SUBJECT = {
    "symbol": "SPY",
    "subject_id": "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c",
    "instrument_id": "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea",
    "identity_version": "mmidentityv_65ec5e55473e953b55fa2d146f40e8b56dfae2e68a3df7423405db1034d16903",
    "mic": "ARCX",
    "currency": "USD",
}
_CALENDAR = {
    "calendar_id": "mmcalendar_a102c5367c17f9c0b4df3af5c2826824fc112935ec76e6d18d55833f53644e0c",
    "market_session": "XNYS_REGULAR",
}
_TECHNICAL_SUBJECT = {
    **_SUBJECT,
    "universe_id": "mmuniverse_5f6904b77722f506a8d1d6f283ef69678a1ec7df3b2c1fc25cc1a15a3a4e8e6a",
    **_CALENDAR,
}

_OPPORTUNITY_EVIDENCE_POLICY = {
    "prospective_only": True,
    "actual_output_only": True,
    "same_session": True,
    "combined_w2_state": False,
    "training_eligible": False,
    "promotion_eligible": False,
}
_OUTCOME_EVIDENCE_POLICY = {
    "prospective_only": True,
    "calendar_session_derivation_authenticated": True,
    "append_only_revision": True,
    "terminal_absence_retained": True,
    "training_eligible": False,
    "promotion_eligible": False,
}

_EXTERNAL_CLOCK_CLAIM = {
    "external_clock_authenticated": False,
    "aba_resistance_authenticated": False,
    "calendar_session_derivation_authenticated": True,
}


def _opportunity_claims(*, source_pins_authenticated: bool) -> dict[str, bool]:
    return {
        **_EXTERNAL_CLOCK_CLAIM,
        "source_generation_pins_authenticated": source_pins_authenticated,
    }


def _outcome_claims(*, target_generation_pin_authenticated: bool) -> dict[str, bool]:
    return {
        **_EXTERNAL_CLOCK_CLAIM,
        "target_generation_pin_authenticated": target_generation_pin_authenticated,
    }


def _population_claims() -> dict[str, bool]:
    return {
        **_EXTERNAL_CLOCK_CLAIM,
        "coverage_derived_from_authenticated_ledger_rows": True,
    }


class MarketMemoryExperienceError(RuntimeError):
    """Base W2C contract or store failure."""


class MarketMemoryExperienceRegistrationError(MarketMemoryExperienceError):
    """The tracked preregistration is malformed or no longer frozen."""


class MarketMemoryExperienceStoreError(MarketMemoryExperienceError):
    """The private W2C ledger is missing, unsafe, or corrupted."""


class MarketMemoryExperienceAccrualError(MarketMemoryExperienceError):
    """An opportunity or outcome cannot be sealed under the registration."""


class _OwnerObservationIntegrityError(MarketMemoryExperienceError):
    """An authenticated owner read failed W2C projection validation."""


@dataclass(frozen=True)
class Registration:
    value: dict[str, Any]
    body: bytes

    @property
    def registration_id(self) -> str:
        return str(self.value["registration_id"])

    @property
    def content_sha256(self) -> str:
        return str(self.value["content_sha256"])


@dataclass(frozen=True)
class OwnerPins:
    trusted: Any
    technical: technical_store.PinnedTechnicalGenerationSnapshot


@dataclass(frozen=True)
class SourceSandwich:
    sampled_at: str
    stable: bool
    source_pins: dict[str, Any] | None
    disposition: str | None
    reason: str | None


@dataclass(frozen=True)
class _TechnicalCandidate:
    reference: dict[str, Any]
    end_close: float


@dataclass(frozen=True)
class _TrustedCandidate:
    reference: dict[str, Any]


@dataclass(frozen=True)
class _TargetObservation:
    pin_observed_at: str
    stable: bool
    generation_pin: dict[str, Any] | None
    candidates: tuple[_TechnicalCandidate, ...]
    clock_tie: bool
    generation_capture_ordinals: dict[str, int]
    ancestry_generation_ids: tuple[str, ...]
    failure_reason: str | None = None


@dataclass(frozen=True)
class _RunOwnerView:
    pin_observed_at: str
    stable: bool
    reader: trusted_store.TrustedFileAsKnownAtReader | None
    pins: OwnerPins | None
    trusted_candidates_by_session: dict[str, tuple[_TrustedCandidate, ...]]
    technical_candidates_by_session: dict[str, tuple[_TechnicalCandidate, ...]]
    failure_reason: str | None = None


@dataclass(frozen=True)
class _ReferenceGenerationPin:
    """Minimal authenticated generation identity reconstructed from a receipt."""

    profile: str
    store_id: str
    generation_id: str
    generation_sha256: str
    captures: tuple[None, ...]


@dataclass(frozen=True)
class AccrualResult:
    registration_id: str
    opportunity_ids: tuple[str, ...]
    outcome_revision_ids: tuple[str, ...]
    population_receipt_id: str | None


def _require_registration_capability(value: object) -> Registration:
    if type(value) is not Registration:
        _fail("W2C registration capability is not one exact Registration")
    body = value.body
    clean = validate_registration(value.value, body=body)
    return Registration(clean, body)


def _fail(message: str) -> NoReturn:
    raise MarketMemoryExperienceStoreError(message)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_json_native(
    value: object,
    *,
    label: str,
    max_depth: int = 64,
    max_nodes: int = 100_000,
    max_string_bytes: int = 2 * 1024 * 1024,
    max_total_string_bytes: int = 8 * 1024 * 1024,
) -> Any:
    """Snapshot one bounded exact JSON-native value without coercion.

    The explicit depth/node/text budgets keep hostile in-memory arguments on
    the same fail-closed path as bounded files.  Exact ``type`` checks reject
    split-view mappings, tuples, and scalar/container subclasses before any
    validation or serialization observes them.
    """

    active: set[int] = set()
    nodes = 0
    total_string_bytes = 0
    root_holder: list[Any] = [None]
    # visit tasks carry the destination container/key. Exit tasks release one
    # active ancestor only after every child has been frozen.
    stack: list[tuple[str, object, int, Any, Any]] = [
        ("visit", value, 0, root_holder, 0)
    ]

    def text_size(item: str, *, key: bool) -> int:
        nonlocal total_string_bytes
        try:
            size = len(item.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise MarketMemoryExperienceStoreError(
                f"{label} contains a non-UTF-8 {'key' if key else 'text'}"
            ) from exc
        if size > max_string_bytes:
            _fail(
                f"{label} contains a {'key' if key else 'text'} beyond its byte bound"
            )
        total_string_bytes += size
        if total_string_bytes > max_total_string_bytes:
            _fail(f"{label} exceeds its aggregate UTF-8 byte bound")
        return size

    try:
        while stack:
            operation, item, depth, destination, destination_key = stack.pop()
            if operation == "exit":
                active.remove(int(item))
                continue
            nodes += 1
            if nodes > max_nodes:
                _fail(f"{label} exceeds its JSON node bound")
            if depth > max_depth:
                _fail(f"{label} exceeds its JSON depth bound")
            item_type = type(item)
            if item is None or item_type in {bool, int}:
                destination[destination_key] = item
                continue
            if item_type is str:
                text_size(item, key=False)
                destination[destination_key] = item
                continue
            if item_type is float:
                if not math.isfinite(item):
                    _fail(f"{label} contains a non-finite number")
                destination[destination_key] = item
                continue
            if item_type not in {list, dict}:
                _fail(f"{label} contains a non-JSON-native value or subclass")
            identity = id(item)
            if identity in active:
                _fail(
                    f"{label} contains a recursive "
                    f"{'list' if item_type is list else 'object'}"
                )
            if len(item) > max_nodes - nodes:
                _fail(f"{label} exceeds its JSON node bound")
            active.add(identity)
            if item_type is list:
                frozen_list: list[Any] = [None] * len(item)
                destination[destination_key] = frozen_list
                stack.append(("exit", identity, depth, None, None))
                for index in range(len(item) - 1, -1, -1):
                    stack.append(
                        ("visit", item[index], depth + 1, frozen_list, index)
                    )
                continue
            frozen_object: dict[str, Any] = {}
            destination[destination_key] = frozen_object
            items = list(item.items())
            for key, _child in items:
                if type(key) is not str:
                    _fail(f"{label} contains a non-string or subclass key")
                text_size(key, key=True)
            stack.append(("exit", identity, depth, None, None))
            for key, child in reversed(items):
                stack.append(
                    ("visit", child, depth + 1, frozen_object, key)
                )
        return root_holder[0]
    except MemoryError as exc:
        raise MarketMemoryExperienceStoreError(
            f"{label} exceeds its bounded JSON memory budget"
        ) from exc
    except (RuntimeError, IndexError, KeyError) as exc:
        if isinstance(exc, MarketMemoryExperienceStoreError):
            raise
        raise MarketMemoryExperienceStoreError(
            f"{label} changed while its JSON snapshot was being frozen"
        ) from exc


def _canonical_bytes(value: object) -> bytes:
    try:
        frozen = _freeze_json_native(value, label="W2C canonical value")
        return json.dumps(
            frozen,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C value is not finite canonical JSON"
        ) from exc


def _digest(body: bytes) -> str:
    return sha256(body).hexdigest()


def _require_value_bound(value: object, *, limit: int, label: str) -> bytes:
    body = _canonical_bytes(value)
    if not body or len(body) > limit:
        _fail(f"{label} is empty or exceeds its canonical byte bound")
    return body


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = _freeze_json_native(value, label="W2C content-addressed value")
    if type(core) is not dict:
        _fail("W2C content-addressed value is not an exact object")
    core[field] = ""
    return prefix + _digest(_canonical_bytes(core))


def _exact_utc_datetime(value: object, *, field: str) -> datetime:
    """Freeze one hostile clock value as an exact base UTC datetime.

    Clock callbacks are a trust boundary.  In particular, accepting a
    ``datetime`` subclass would let its Python-level ``astimezone`` or
    ``isoformat`` override run after the nominal type check.  Reject subclasses,
    sample the offset once, and reconstruct a plain ``datetime`` whose only
    timezone object is the standard-library UTC singleton.
    """

    if type(value) is not datetime or value.tzinfo is None:
        _fail(f"W2C {field} must be one exact timezone-aware datetime")
    try:
        offset = value.utcoffset()
        if type(offset) is not timedelta:
            _fail(f"W2C {field} has an invalid UTC offset")
        local = datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            fold=value.fold,
        )
        utc_naive = local - offset
        return datetime(
            utc_naive.year,
            utc_naive.month,
            utc_naive.day,
            utc_naive.hour,
            utc_naive.minute,
            utc_naive.second,
            utc_naive.microsecond,
            tzinfo=timezone.utc,
        )
    except MarketMemoryExperienceError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise MarketMemoryExperienceStoreError(
            f"W2C {field} cannot be normalized to UTC"
        ) from exc


def _format_utc(value: datetime) -> str:
    snapshot = _exact_utc_datetime(value, field="clock")
    return snapshot.isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, *, field: str) -> datetime:
    if type(value) is not str or not _UTC.fullmatch(value):
        _fail(f"W2C {field} is not exact RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:  # pragma: no cover - regex excludes ordinary cases
        raise MarketMemoryExperienceStoreError(
            f"W2C {field} is not a real UTC instant"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        _fail(f"W2C {field} is not UTC")
    return parsed.astimezone(timezone.utc)


def _parse_session(value: object, *, field: str) -> date:
    if type(value) is not str or not _SESSION.fullmatch(value):
        _fail(f"W2C {field} is not an exact session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise MarketMemoryExperienceStoreError(
            f"W2C {field} is not a real date"
        ) from exc
    if not nyse_calendar.is_session(parsed):
        _fail(f"W2C {field} is not an XNYS session")
    return parsed


def _require_digest(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        _fail(f"W2C {field} is not lowercase SHA-256")
    return value


def _require_commit(value: object, *, field: str = "writer_commit") -> str:
    if type(value) is not str or not _COMMIT.fullmatch(value):
        _fail(f"W2C {field} is not a full Git object ID")
    return value


def _strict_json(body: bytes, *, label: str) -> dict[str, Any]:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite token {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise MarketMemoryExperienceStoreError(
            f"{label} is not strict JSON"
        ) from exc
    if not isinstance(value, dict) or _canonical_bytes(value) != body:
        _fail(f"{label} is not a canonical JSON object")
    return value


def _expected_registration_spec() -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "subject": {
            "symbol": "SPY",
            "subject_id": "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c",
            "instrument_id": "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea",
            "identity_version": "mmidentityv_65ec5e55473e953b55fa2d146f40e8b56dfae2e68a3df7423405db1034d16903",
            "mic": "ARCX",
            "currency": "USD",
        },
        "activation_session": "2026-08-17",
        "calendar": {
            "owner_path": "lib/nyse_calendar.py",
            "owner_sha256": "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce",
            "calendar_id": "mmcalendar_a102c5367c17f9c0b4df3af5c2826824fc112935ec76e6d18d55833f53644e0c",
            "market_session": "XNYS_REGULAR",
            "expected_opportunity_rule": "first_126_xnys_sessions_on_or_after_activation.v1",
        },
        "cutoff": {
            "rule": "first_same_head_sandwich_observation_in_fixed_window",
            "following_calendar_days": 1,
            "window_opens_utc_time": "04:30:00Z",
            "admission_window_seconds": 900,
            "actual_cutoff": "local_pin_observed_at_no_later_than_deadline",
            "clock_model": "session_ordinal_only_no_fabricated_market_close_timestamp",
            "head_observation_model": "same_authenticated_head_before_and_after_local_sample_under_monotone_append_only_owner_protocol",
            "aba_adversary_model": "transient_a_to_b_to_a_between_reads_not_detectable_v1",
            "owner_pair_retry_interval_seconds": OWNER_PAIR_RETRY_INTERVAL_SECONDS,
            "owner_pair_max_attempts": OWNER_PAIR_MAX_ATTEMPTS,
            "unstable_pair_policy": "retry_within_window_then_missed_owner_pair_not_stable_by_deadline",
        },
        "state_inputs": {
            "trusted_profile": trusted_store.TRUSTED_STORE_PROFILE,
            "macro_feature_id": "macro.regime_state",
            "macro_session_field": "source_artifact.source_asof",
            "technical_profile": technical_store.STORE_PROFILE,
            "technical_session_field": "feature_object.session",
            "same_session_required": True,
            "published_generation_ancestry_required": True,
            "max_owner_generation_capture_count": MAX_OWNER_GENERATION_CAPTURES,
            "capture_clock_not_after_cutoff": True,
            "publication_proof": "same_authenticated_head_observed_before_and_after_local_sample",
            "owner_protocol_assumption": "monotone_append_only_content_addressed_head",
            "selection": "owner_observed_revision_chain.v1",
            "state_semantics": "narrow_owner_reference_pair_not_w2a_or_combined_domain_state",
            "fallback_allowed": False,
        },
        "decision_state_projection": {
            "projection_version": DECISION_STATE_PROJECTION_SCHEMA,
            "source_transform_version": SOURCE_REGIME_TRANSFORM_VERSION,
            "source_feature_id": "macro.regime_state",
            "coordinates": [
                "growth_score.q18", "inflation_score.q18", "quad",
                "liquidity_overlay", "cycle_tag",
            ],
            "numeric_conversion": "exact_source_binary64_integer_ratio_half_even_q18",
            "numeric_scale_denominators_q18": {
                "growth_score.q18": "2.000000000000000000",
                "inflation_score.q18": "2.000000000000000000",
            },
            "categorical_mismatch": {
                "equal": 0,
                "unequal": 1,
                "fields": ["quad", "liquidity_overlay", "cycle_tag"],
            },
            "distance_arithmetic": {
                "decimal_context_precision": 64,
                "rounding": "ROUND_HALF_EVEN",
                "numeric_delta": "(q18_query-q18_candidate)/2.000000000000000000",
                "categorical_delta": "0_if_equal_else_1",
                "sum": "five_squared_deltas_no_intermediate_quantization",
                "sqrt": "decimal_sqrt_then_quantize_once_q18",
            },
            "missingness": "fail_closed_no_imputation",
            "categorical_unknown_policy": "projection_unavailable_non_scoreable_opportunity_unchanged",
            "future_w4_consumption": "exact_persisted_opportunity_projection_only",
        },
        "capacity_preflight": {
            "max_owner_generation_capture_count": MAX_OWNER_GENERATION_CAPTURES,
            "trusted_future_captures": TRUSTED_FUTURE_CAPTURES,
            "technical_future_captures": TECHNICAL_FUTURE_CAPTURES,
            "revision_reserve": REVISION_RESERVE,
            "rule": "current_count_plus_future_plus_reserve_lte_max",
            "failure": "pilot_no_go_before_any_w2c_write",
        },
        "auditability": {
            "warning_owner_capture_count": 320,
            "checkpoint_migration_required_before_owner_count": 384,
            "v2_acceptance_requirement": "reload_every_v1_pilot_source_ref_from_authenticated_checkpoint_or_delta",
            "indefinite_v1_auditability": False,
        },
        "outcome": {
            "horizon_sessions": OUTCOME_HORIZON_SESSIONS,
            "target": "spy.raw_unadjusted_daily_aggregate_close_ratio",
            "formula": "target_capture.feature.state.end_close/sealed_anchor_capture.feature.state.end_close",
            "source": "owner_validated_technical_capture_feature_marks",
            "price_basis": "raw_unadjusted_daily_aggregate_close",
            "input_encoding": "ieee754_binary64_exact_hex_and_integer_ratio",
            "exact_decimal_encoding": "python_decimal_from_float_exact",
            "quantization": "q18",
            "rounding": "exact_integer_ratio_half_even",
            "economic_return": False,
            "corporate_action_adjusted": False,
            "missing_target_policy": "append_unavailable_at_maturity_cutoff",
            "late_target_policy": "append_late_source_resolution_preserve_unavailable_revision",
            "clock_tie_policy": "append_censored_no_capture_selection",
            "maturity_owner_miss_policy": "append_censored_preserve_late_resolution_chain",
            "target_maturity_window_rule": "target_session_following_calendar_day_same_registered_window",
            "revision_selection": "owner_observed_revision_chain.v1",
            "correction_policy": "strictly_later_owner_observation_active_predecessor_chain",
            "final_tail_xnys_sessions": CORRECTION_OBSERVATION_SESSIONS,
            "final_tail_sunset_session": CORRECTION_SUNSET_SESSION.isoformat(),
            "correction_observation_window_rule": "daily_0430_0445z_from_target_maturity_window_through_terminal_date_inclusive",
            "terminal_census_window_opens_at": "2027-03-03T04:30:00Z",
            "terminal_census_deadline_at": "2027-03-03T04:45:00Z",
            "terminal_marker_policy": "immutable_final_population_receipt_then_no_write",
        },
        "population": {
            "dispositions": ["admitted", "abstained", "missed"],
            "one_row_per_expected_session": True,
            "timely_abstention_is_final": True,
            "late_unsealed_disposition": "missed",
            "pilot_expected_sessions": PILOT_EXPECTED_SESSIONS,
            "sunset_session": "2027-02-16",
            "final_target_session": "2027-02-23",
            "correction_sunset_session": CORRECTION_SUNSET_SESSION.isoformat(),
            "terminal_census_date": TERMINAL_CENSUS_DATE.isoformat(),
            "renewal_requirement": "authenticated_checkpoint_or_delta_generations_before_v2",
        },
        "evidence_policy": {
            "prospective_only": True,
            "historical_backfill_allowed": False,
            "actual_output_only": True,
            "population_receipt_required": True,
            "training_eligible": False,
            "promotion_eligible": False,
            "external_clock_authenticated": False,
            "aba_resistance_authenticated": False,
            "calendar_session_derivation_authenticated": True,
        },
        "claims": copy.deepcopy(_EXTERNAL_CLOCK_CLAIM),
        "authority": dict(market_memory.AUTHORITY),
    }


def validate_registration(
    value: Mapping[str, Any], *, body: bytes | None = None
) -> dict[str, Any]:
    fields = {"schema", "registration_id", "content_sha256", "content_bytes", "spec"}
    try:
        clean = _freeze_json_native(value, label="W2C registration")
    except MarketMemoryExperienceStoreError as exc:
        raise MarketMemoryExperienceRegistrationError(str(exc)) from exc
    if type(clean) is not dict or set(clean) != fields:
        raise MarketMemoryExperienceRegistrationError(
            "W2C registration fields are not canonical"
        )
    if clean.get("schema") != REGISTRATION_SCHEMA:
        raise MarketMemoryExperienceRegistrationError(
            "W2C registration schema mismatch"
        )
    try:
        canonical_registration = _require_value_bound(
            clean, limit=_MAX_REGISTRATION_BYTES, label="W2C registration"
        )
    except MarketMemoryExperienceStoreError as exc:
        raise MarketMemoryExperienceRegistrationError(str(exc)) from exc
    if clean.get("spec") != _expected_registration_spec():
        raise MarketMemoryExperienceRegistrationError(
            "W2C registration spec drift"
        )
    spec_body = _canonical_bytes(clean["spec"])
    digest = _digest(spec_body)
    if (
        clean.get("content_sha256") != digest
        or clean.get("registration_id") != f"mmspyexpreg_{digest}"
        or clean.get("content_bytes") != len(spec_body)
    ):
        raise MarketMemoryExperienceRegistrationError(
            "W2C registration identity does not bind its canonical spec"
        )
    if body is not None:
        if type(body) is not bytes or canonical_registration != body:
            raise MarketMemoryExperienceRegistrationError(
                "W2C registration bytes are not exact canonical bytes"
            )
    sessions = nyse_calendar.sessions_between(ACTIVATION_SESSION, SUNSET_SESSION)
    if (
        len(sessions) != PILOT_EXPECTED_SESSIONS
        or sessions[0] != ACTIVATION_SESSION
        or sessions[-1] != SUNSET_SESSION
        or nyse_calendar.session_n_forward(ACTIVATION_SESSION, 125) != SUNSET_SESSION
        or _target_session(SUNSET_SESSION) != FINAL_TARGET_SESSION
        or nyse_calendar.session_n_forward(
            FINAL_TARGET_SESSION, CORRECTION_OBSERVATION_SESSIONS
        )
        != CORRECTION_SUNSET_SESSION
        or _terminal_window()
        != (
            datetime(2027, 3, 3, 4, 30, tzinfo=timezone.utc),
            datetime(2027, 3, 3, 4, 45, tzinfo=timezone.utc),
        )
    ):
        raise MarketMemoryExperienceRegistrationError(
            "W2C pilot session census differs from the bound calendar"
        )
    return clean


def load_registration(
    repository_root: str | Path,
    *,
    path: str | Path | None = None,
) -> Registration:
    repository = Path(repository_root).expanduser().resolve()
    candidate = (
        Path(path).expanduser().resolve()
        if path is not None
        else repository / DEFAULT_REGISTRATION_PATH
    )
    try:
        body = candidate.read_bytes()
    except OSError as exc:
        raise MarketMemoryExperienceRegistrationError(
            "W2C tracked registration cannot be read"
        ) from exc
    if len(body) > _MAX_REGISTRATION_BYTES:
        raise MarketMemoryExperienceRegistrationError(
            "W2C tracked registration exceeds its byte bound"
        )
    canonical_body = body[:-1] if body.endswith(b"\n") else body
    if not canonical_body or b"\n" in canonical_body:
        raise MarketMemoryExperienceRegistrationError(
            "W2C tracked registration must be one canonical JSON line"
        )
    value = _strict_json(canonical_body, label="W2C tracked registration")
    clean = validate_registration(value, body=canonical_body)
    try:
        calendar_body = (repository / "lib/nyse_calendar.py").read_bytes()
    except OSError as exc:
        raise MarketMemoryExperienceRegistrationError(
            "W2C calendar owner cannot be read"
        ) from exc
    if _digest(calendar_body) != clean["spec"]["calendar"]["owner_sha256"]:
        raise MarketMemoryExperienceRegistrationError(
            "W2C calendar owner bytes differ from the registration"
        )
    return Registration(clean, canonical_body)


def _window(session: date) -> tuple[datetime, datetime]:
    opened = datetime.combine(
        session + timedelta(days=1), time(4, 30), tzinfo=timezone.utc
    )
    return opened, opened + timedelta(seconds=900)


def _terminal_window() -> tuple[datetime, datetime]:
    opened = datetime.combine(
        TERMINAL_CENSUS_DATE, time(4, 30), tzinfo=timezone.utc
    )
    return opened, opened + timedelta(seconds=900)


def _final_tail_observation_windows() -> tuple[tuple[datetime, datetime], ...]:
    sessions: list[date] = []
    cursor = FINAL_TARGET_SESSION
    for _ in range(CORRECTION_OBSERVATION_SESSIONS):
        cursor = nyse_calendar.session_n_forward(cursor, 1)
        if cursor is None:  # pragma: no cover - frozen calendar proves this
            raise MarketMemoryExperienceRegistrationError(
                "W2C correction observation session cannot be resolved"
            )
        sessions.append(cursor)
    if not sessions or sessions[-1] != CORRECTION_SUNSET_SESSION:
        raise MarketMemoryExperienceRegistrationError(
            "W2C correction observation sessions differ from registration"
        )
    return tuple(_window(session) for session in sessions)


def _inside_finite_correction_window(
    value: datetime, *, target_session: date
) -> bool:
    """Permit revisions only in daily 04:30-04:45Z windows through terminal."""

    observed = value.astimezone(timezone.utc)
    first_opened, _first_deadline = _window(target_session)
    terminal_opened, terminal_deadline = _terminal_window()
    if not first_opened.date() <= observed.date() <= terminal_opened.date():
        return False
    opened = datetime.combine(
        observed.date(), time(4, 30), tzinfo=timezone.utc
    )
    deadline = opened + timedelta(minutes=15)
    return opened <= observed <= deadline and observed <= terminal_deadline


def _target_session(session: date) -> date:
    target = nyse_calendar.session_n_forward(session, OUTCOME_HORIZON_SESSIONS)
    if target is None:
        raise MarketMemoryExperienceRegistrationError(
            "W2C cannot resolve the registered +5 session ordinal"
        )
    return target


def expected_sessions_due(now: datetime) -> list[date]:
    observed = _exact_utc_datetime(now, field="expected sessions clock")
    return [
        session
        for session in nyse_calendar.sessions_between(
            ACTIVATION_SESSION, SUNSET_SESSION
        )
        if _window(session)[0] <= observed
    ]


def _binary64_mark(value: object, *, field: str) -> dict[str, str]:
    if type(value) is not float or not math.isfinite(value) or value <= 0:
        _fail(f"W2C {field} is not one positive finite binary64 value")
    exact_decimal = format(Decimal.from_float(value), "f")
    if len(exact_decimal) > _MAX_EXACT_DECIMAL_CHARS:
        _fail(f"W2C {field} exact decimal exceeds its bound")
    return {
        "end_close_binary64_hex": value.hex(),
        "end_close_exact_decimal": exact_decimal,
    }


def _q18_ratio(numerator: float, denominator: float) -> str:
    """Round an exact binary64 ratio to q18 without ambient Decimal context."""

    if any(
        type(value) is not float or not math.isfinite(value) or value <= 0
        for value in (numerator, denominator)
    ):
        _fail("W2C close-ratio inputs must be positive finite binary64 values")
    numerator_n, numerator_d = numerator.as_integer_ratio()
    denominator_n, denominator_d = denominator.as_integer_ratio()
    exact_n = numerator_n * denominator_d
    exact_d = numerator_d * denominator_n
    scaled, remainder = divmod(exact_n * 10**18, exact_d)
    doubled = remainder * 2
    if doubled > exact_d or (doubled == exact_d and scaled % 2 == 1):
        scaled += 1
    return f"{scaled // 10**18}.{scaled % 10**18:018d}"


def _q18_fraction(numerator: int, denominator: int) -> str:
    if numerator < 0 or denominator < 0:
        _fail("W2C coverage counts cannot be negative")
    if denominator == 0:
        return "0.000000000000000000"
    scaled, remainder = divmod(numerator * 10**18, denominator)
    doubled = remainder * 2
    if doubled > denominator or (doubled == denominator and scaled % 2 == 1):
        scaled += 1
    return f"{scaled // 10**18}.{scaled % 10**18:018d}"


def _signed_binary64_q18(value: object, *, field: str) -> dict[str, str]:
    """Bind a normalized owner binary64 and its exact HALF_EVEN q18 value."""

    if type(value) not in {int, float}:
        _fail(f"W2C {field} is not one JSON number")
    normalized = float(value)
    if not math.isfinite(normalized) or not -1.0 <= normalized <= 1.0:
        _fail(f"W2C {field} is not one normalized finite binary64 value")
    numerator, denominator = normalized.as_integer_ratio()
    magnitude = abs(numerator)
    scaled, remainder = divmod(magnitude * 10**18, denominator)
    doubled = remainder * 2
    if doubled > denominator or (doubled == denominator and scaled % 2 == 1):
        scaled += 1
    if numerator < 0:
        scaled = -scaled
    sign = "-" if scaled < 0 else ""
    absolute = abs(scaled)
    return {
        "source_binary64_hex": normalized.hex(),
        "source_exact_decimal": format(Decimal.from_float(normalized), "f"),
        "q18": f"{sign}{absolute // 10**18}.{absolute % 10**18:018d}",
    }


def _decision_state_projection(
    feature: Mapping[str, Any], *, feature_snapshot_id: str,
    feature_content_sha256: str,
) -> tuple[dict[str, Any] | None, str, dict[str, str]]:
    """Freeze the preregistered W4-ready coordinates from one owner feature."""

    if (
        type(feature) is not dict
        or feature.get("schema") != "market_memory.macro_regime_feature_object.v1"
        or feature.get("transform_version") != SOURCE_REGIME_TRANSFORM_VERSION
        or type(feature.get("state")) is not dict
    ):
        _fail("W2C owner macro feature cannot produce the frozen decision state")
    state = feature["state"]
    quad = state.get("quad")
    liquidity = state.get("liquidity_overlay")
    cycle = state.get("cycle_tag")
    if quad not in {"Q1", "Q2", "Q3", "Q4"}:
        _fail("W2C owner macro quad is outside the frozen vocabulary")
    if liquidity not in {"expanding", "neutral", "contracting", "unknown"}:
        _fail("W2C owner liquidity overlay is outside the frozen vocabulary")
    if cycle not in {"early", "mid", "late", "unknown"}:
        _fail("W2C owner cycle tag is outside the frozen vocabulary")
    _require_digest(feature_content_sha256, field="decision-state feature digest")
    if type(feature_snapshot_id) is not str or not re.fullmatch(
        r"mmsnap_[a-f0-9]{64}", feature_snapshot_id
    ):
        _fail("W2C decision-state feature snapshot ID is malformed")
    raw_categories = {
        "quad": str(quad),
        "liquidity_overlay": str(liquidity),
        "cycle_tag": str(cycle),
    }
    if liquidity == "unknown" or cycle == "unknown":
        if liquidity == "unknown" and cycle == "unknown":
            reason = "owner_liquidity_overlay_and_cycle_tag_unknown"
        elif liquidity == "unknown":
            reason = "owner_liquidity_overlay_unknown"
        else:
            reason = "owner_cycle_tag_unknown"
        return None, reason, raw_categories
    projection = {
        "schema": DECISION_STATE_PROJECTION_SCHEMA,
        "source_feature_id": "macro.regime_state",
        "source_transform_version": SOURCE_REGIME_TRANSFORM_VERSION,
        "feature_snapshot_id": feature_snapshot_id,
        "feature_content_sha256": feature_content_sha256,
        "growth_score": _signed_binary64_q18(
            state.get("growth_score"), field="growth_score"
        ),
        "inflation_score": _signed_binary64_q18(
            state.get("inflation_score"), field="inflation_score"
        ),
        "quad": quad,
        "liquidity_overlay": liquidity,
        "cycle_tag": cycle,
        "missingness_policy": "fail_closed_no_imputation",
    }
    return projection, "exact_owner_macro_regime_transform", raw_categories


def validate_experience_store_root(root: str | Path) -> Path:
    """Require the disjoint private ``state/experience-v1`` owner root."""

    unresolved = Path(root).expanduser()
    absolute = Path(os.path.abspath(os.fspath(unresolved)))
    if absolute.name != "experience-v1" or absolute.parent.name != "state":
        _fail("W2C store root must end in state/experience-v1")
    cursor = absolute
    while True:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MarketMemoryExperienceStoreError(
                "W2C store path components cannot be inspected"
            ) from exc
        else:
            if stat.S_ISLNK(metadata.st_mode):
                _fail("W2C store root and parents cannot be symlinks")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    return absolute


def _safe_path(root: Path, *parts: str) -> Path:
    if not parts or any(
        type(part) is not str
        or not part
        or part in {".", ".."}
        or "/" in part
        or "\x00" in part
        for part in parts
    ):
        _fail("W2C internal path is unsafe")
    candidate = root.joinpath(*parts)
    if candidate.parent != root and root not in candidate.parents:
        _fail("W2C internal path escapes its store")
    return candidate


def _mkdir(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = path.lstat()
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C private directory cannot be created or inspected"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("W2C private path is not a real directory")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_bounded(path: Path, *, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(f"{label} cannot be opened") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            _fail(f"{label} is not one bounded regular file")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    body = b"".join(chunks)
    if (
        len(body) > limit
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or len(body) != after.st_size
    ):
        _fail(f"{label} changed during its bounded read")
    return body


def _read_json_path(path: Path, *, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    body = _read_bounded(path, limit=limit, label=label)
    return _strict_json(body, label=label), body


def _publish_boundary(_stage: str, _path: Path) -> None:
    """Fault-injection seam for durability-boundary crash tests."""


def _pending_create_path(path: Path, body: bytes) -> Path:
    return path.parent / f".{path.name}.{_digest(body)}.pending"


def _pending_create_paths(path: Path) -> list[Path]:
    try:
        return sorted(path.parent.glob(f".{path.name}.*.pending"))
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C create-once pending publications cannot be inspected"
        ) from exc


def _write_create_once(path: Path, body: bytes, *, limit: int, label: str) -> None:
    if not body or len(body) > limit:
        _fail(f"{label} is empty or exceeds its byte bound")
    _mkdir(path.parent)
    temporary = _pending_create_path(path, body)
    pending = _pending_create_paths(path)
    if any(item != temporary for item in pending):
        _fail(f"{label} has an ambiguous pending publication")
    if path.exists() or path.is_symlink():
        existing = _read_bounded(path, limit=limit, label=label)
        if existing != body:
            _fail(f"{label} already exists with different bytes")
        if temporary.exists() or temporary.is_symlink():
            staged = _read_bounded(
                temporary, limit=limit, label=f"pending {label}"
            )
            if staged != body:
                _fail(f"pending {label} differs from its final publication")
            temporary.unlink()
            _fsync_directory(path.parent)
        return

    if temporary.exists() or temporary.is_symlink():
        staged = _read_bounded(temporary, limit=limit, label=f"pending {label}")
        if staged != body:
            _fail(f"pending {label} is partial or has different bytes")
    else:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(temporary, flags, 0o600)
        except OSError as exc:
            raise MarketMemoryExperienceStoreError(
                f"pending {label} cannot be created"
            ) from exc
        try:
            cursor = 0
            while cursor < len(body):
                written = os.write(descriptor, body[cursor:])
                if written <= 0:  # pragma: no cover - defensive OS boundary
                    _fail(f"pending {label} write made no progress")
                cursor += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _publish_boundary("temporary_fsynced", path)

    try:
        os.link(temporary, path, follow_symlinks=False)
    except FileExistsError:
        existing = _read_bounded(path, limit=limit, label=label)
        if existing != body:
            _fail(f"{label} raced with different bytes")
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            f"{label} cannot be atomically linked"
        ) from exc
    _publish_boundary("final_linked", path)
    _fsync_directory(path.parent)
    _publish_boundary("final_directory_fsynced", path)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            f"pending {label} cannot be removed"
        ) from exc
    _publish_boundary("temporary_unlinked", path)
    _fsync_directory(path.parent)


def _read_one_pending_create(
    path: Path, *, limit: int, label: str
) -> tuple[dict[str, Any], bytes] | None:
    pending = _pending_create_paths(path)
    if not pending:
        return None
    if len(pending) != 1:
        _fail(f"{label} has multiple pending publications")
    raw, body = _read_json_path(
        pending[0], limit=limit, label=f"pending {label}"
    )
    if pending[0] != _pending_create_path(path, body):
        _fail(f"pending {label} filename does not bind its bytes")
    return raw, body


def _recover_immutable_json(
    path: Path,
    *,
    limit: int,
    label: str,
    validator: Callable[[dict[str, Any], bytes], Any],
) -> Any | None:
    """Recover exactly one validated create-once publication in place."""

    final_exists = path.exists() or path.is_symlink()
    pending = _read_one_pending_create(path, limit=limit, label=label)
    if final_exists:
        raw, body = _read_json_path(path, limit=limit, label=label)
        clean = validator(raw, body)
        if pending is not None and pending[1] != body:
            _fail(f"{label} final and pending publications differ")
        # Re-entering the create-once publisher removes an identical pending
        # name left after final link publication.
        _write_create_once(path, body, limit=limit, label=label)
        return clean
    if pending is None:
        return None
    raw, body = pending
    clean = validator(raw, body)
    _write_create_once(path, body, limit=limit, label=label)
    return clean


def _validate_empty_initialization_prefix(root: Path) -> None:
    """Permit only deterministic, non-capture-bearing fresh-init prefixes."""

    allowed_files = {
        "writer.lock",
        "registration_installation.json",
        "manifest.json",
    }
    allowed_directories = {
        "prepared_objects",
        "prepared_sessions",
        "opportunities",
        "outcomes",
        "population_receipts",
        "technical_views",
    }
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C initialization prefix cannot be inspected"
        ) from exc
    for entry in entries:
        name = entry.name
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _fail("W2C initialization prefix contains a symlink")
        if name in allowed_directories:
            if not stat.S_ISDIR(metadata.st_mode) or any(entry.iterdir()):
                _fail("W2C partial initialization contains capture-bearing state")
            continue
        if name == "writer.lock":
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != 0:
                _fail("W2C initialization lock is ambiguous")
            continue
        if name in allowed_files:
            if not stat.S_ISREG(metadata.st_mode):
                _fail("W2C initialization receipt is not a regular file")
            continue
        if re.fullmatch(
            r"\.(registration_installation|manifest)\.json\.[a-f0-9]{64}\.pending",
            name,
        ):
            if not stat.S_ISREG(metadata.st_mode):
                _fail("W2C pending initialization receipt is not regular")
            continue
        _fail("W2C initialization prefix contains an unknown artifact")


def _replace_head(path: Path, body: bytes) -> None:
    if not body or len(body) > _MAX_HEAD_BYTES:
        _fail("W2C mutable HEAD exceeds its byte bound")
    _mkdir(path.parent)
    temporary = _pending_create_path(path, body)
    pending = _pending_create_paths(path)
    if any(item != temporary for item in pending):
        _fail("W2C mutable HEAD has an ambiguous pending publication")
    if path.exists() or path.is_symlink():
        existing = _read_bounded(
            path, limit=_MAX_HEAD_BYTES, label="W2C mutable HEAD"
        )
        if existing == body:
            if temporary.exists() or temporary.is_symlink():
                staged = _read_bounded(
                    temporary,
                    limit=_MAX_HEAD_BYTES,
                    label="pending W2C mutable HEAD",
                )
                if staged != body:
                    _fail("pending W2C mutable HEAD differs from its final bytes")
                temporary.unlink()
                _fsync_directory(path.parent)
            return
    if temporary.exists() or temporary.is_symlink():
        staged = _read_bounded(
            temporary,
            limit=_MAX_HEAD_BYTES,
            label="pending W2C mutable HEAD",
        )
        if staged != body:
            _fail("pending W2C mutable HEAD differs from requested bytes")
    else:
        flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(temporary, flags, 0o600)
        try:
            cursor = 0
            while cursor < len(body):
                written = os.write(descriptor, body[cursor:])
                if written <= 0:  # pragma: no cover - OS defensive boundary
                    _fail("pending W2C mutable HEAD write made no progress")
                cursor += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _publish_boundary("temporary_fsynced", path)
    os.replace(temporary, path)
    _publish_boundary("final_replaced", path)
    _fsync_directory(path.parent)
    _publish_boundary("final_directory_fsynced", path)


def _recover_mutable_head(
    path: Path,
    *,
    label: str,
    validator: Callable[[dict[str, Any], bytes], Any],
) -> Any | None:
    """Finish one fsynced mutable-HEAD replacement after validating its target."""

    pending = _read_one_pending_create(
        path, limit=_MAX_HEAD_BYTES, label=label
    )
    if pending is not None:
        pending_raw, pending_body = pending
        validator(pending_raw, pending_body)
        _replace_head(path, pending_body)
    if not (path.exists() or path.is_symlink()):
        return None
    raw, body = _read_json_path(path, limit=_MAX_HEAD_BYTES, label=label)
    return validator(raw, body)


def _sample_clock(clock: Callable[[], datetime]) -> datetime:
    sampled = clock()
    return _exact_utc_datetime(sampled, field="writer clock sample")


def _pin_owners(
    trusted_root: str | Path,
    technical_root: str | Path,
) -> tuple[trusted_store.TrustedFileAsKnownAtReader, OwnerPins]:
    """Read both owner HEADs with the pilot cap before any W2C mutation."""

    reader = trusted_store.TrustedFileAsKnownAtReader(trusted_root)
    trusted_pin = reader.read_pinned_generation(
        maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    technical_pin = technical_store.pin_technical_actual_output_generation(
        technical_root,
        maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES,
    )
    return reader, OwnerPins(trusted=trusted_pin, technical=technical_pin)


def _head_identity(value: Any) -> tuple[str, str, str, str]:
    return (
        str(value.profile),
        str(value.store_id),
        str(value.generation_id),
        str(value.generation_sha256),
    )


def _pin_matches_head(pin: Any, head: Any) -> bool:
    return _head_identity(pin) == _head_identity(head)


def _active_retry_deadline(now: datetime) -> datetime:
    opened = datetime.combine(now.date(), time(4, 30), tzinfo=timezone.utc)
    deadline = opened + timedelta(seconds=900)
    return deadline if opened <= now <= deadline else now


def _owner_failure_reason(exc: Exception) -> str:
    message = str(exc).lower()
    if "pin budget" in message or "capture count" in message and "256" in message:
        return "owner_pin_cap_exceeded_by_deadline"
    if isinstance(exc, (FileNotFoundError, OSError)) or any(
        token in message
        for token in ("not found", "no such file", "cannot be opened", "missing head")
    ):
        return "owner_unavailable_by_deadline"
    return "owner_integrity_failure_by_deadline"


def _observe_run_owner_view(
    root: Path,
    *,
    registration: Registration,
    trusted_root: str | Path,
    reader: trusted_store.TrustedFileAsKnownAtReader | None,
    initial_pins: OwnerPins | None,
    technical_root: str | Path,
    clock: Callable[[], datetime],
    retry_deadline: datetime,
    sleeper: Callable[[float], None],
    require_capacity_preflight: bool = False,
) -> _RunOwnerView:
    """Retry HEAD sandwiches, then pin the exact head seen around a local sample.

    This authenticates the two observations and the pinned generation, not
    continuous head stability: an unobserved A -> B -> A transition between
    reads is outside the v1 evidence model and is durably disclaimed.
    """

    last_sample = _sample_clock(clock)
    current_reader = reader
    current_pins = initial_pins
    failure_reason = "owner_pair_not_stable_by_deadline"
    for attempt in range(OWNER_PAIR_MAX_ATTEMPTS):
        try:
            if current_reader is None or current_pins is None:
                current_reader, current_pins = _pin_owners(
                    trusted_root, technical_root
                )
            before_trusted = current_reader.observe_generation_head(
                maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
            )
            before_technical = technical_store.observe_technical_actual_output_generation_head(
                technical_root, maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
            )
            sampled = _sample_clock(clock)
            after_trusted = current_reader.observe_generation_head(
                maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
            )
            after_technical = technical_store.observe_technical_actual_output_generation_head(
                technical_root, maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
            )
            last_sample = sampled
            if (
                _head_identity(before_trusted) == _head_identity(after_trusted)
                and _head_identity(before_technical) == _head_identity(after_technical)
            ):
                trusted_pin = (
                    current_pins.trusted
                    if _pin_matches_head(current_pins.trusted, before_trusted)
                    else current_reader.read_pinned_generation(
                        generation_id=before_trusted.generation_id,
                        maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES,
                    )
                )
                technical_pin = (
                    current_pins.technical
                    if _pin_matches_head(current_pins.technical, before_technical)
                    else technical_store.pin_technical_actual_output_generation(
                        technical_root,
                        generation_id=before_technical.generation_id,
                        maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES,
                    )
                )
                if (
                    not _pin_matches_head(trusted_pin, before_trusted)
                    or not _pin_matches_head(technical_pin, before_technical)
                ):
                    _fail("W2C authenticated pin differs from its stable HEAD sandwich")
                exact_pins = OwnerPins(
                    trusted=trusted_pin, technical=technical_pin
                )
                if require_capacity_preflight:
                    _capacity_preflight(exact_pins)
                try:
                    trusted_by_session = _trusted_candidates_by_session(
                        current_reader, trusted_pin
                    )
                except MarketMemoryExperienceStoreError as exc:
                    raise _OwnerObservationIntegrityError(
                        "trusted owner projection failed W2C validation"
                    ) from exc
                technical_by_session, pending_view = _prepare_technical_view(
                    root,
                    registration=registration,
                    technical_root=technical_root,
                    pin=technical_pin,
                    trusted_pin=trusted_pin,
                    pair_observed_at=_format_utc(sampled),
                )
                cutoff = sampled.astimezone(timezone.utc)
                try:
                    _validate_candidate_clocks(
                        [
                            row
                            for rows in trusted_by_session.values()
                            for row in rows
                        ],
                        [
                            row
                            for rows in technical_by_session.values()
                            for row in rows
                        ],
                        cutoff=cutoff,
                    )
                except MarketMemoryExperienceAccrualError as exc:
                    raise _OwnerObservationIntegrityError(
                        "owner capture clock failed W2C cutoff validation"
                    ) from exc
                _publish_technical_view(root, pending_view)
                return _RunOwnerView(
                    pin_observed_at=_format_utc(sampled),
                    stable=True,
                    reader=current_reader,
                    pins=exact_pins,
                    trusted_candidates_by_session=trusted_by_session,
                    technical_candidates_by_session=technical_by_session,
                )
            failure_reason = "owner_pair_not_stable_by_deadline"
        except (MarketMemoryExperienceAccrualError, MarketMemoryExperienceStoreError):
            raise
        except Exception as exc:
            failure_reason = _owner_failure_reason(exc)
            if (
                require_capacity_preflight
                and failure_reason == "owner_pin_cap_exceeded_by_deadline"
            ):
                raise MarketMemoryExperienceAccrualError(
                    "W2C pilot NO-GO: exact activation owner pair exceeds its pin cap"
                ) from exc
            current_reader = None
            current_pins = None
            sampled = _sample_clock(clock)
            last_sample = max(last_sample, sampled)
        if sampled >= retry_deadline or attempt + 1 >= OWNER_PAIR_MAX_ATTEMPTS:
            break
        remaining = (retry_deadline - sampled).total_seconds()
        if remaining <= 0:
            break
        sleeper(min(float(OWNER_PAIR_RETRY_INTERVAL_SECONDS), remaining))
    # This is a reconciliation clock, not another owner observation attempt.
    # It lets the same bounded oneshot persist the deadline miss after the
    # final inclusive-window sandwich without inventing a generation pin.
    reconciled = _sample_clock(clock)
    if reconciled > last_sample:
        last_sample = reconciled
    return _RunOwnerView(
        pin_observed_at=_format_utc(last_sample),
        stable=False,
        reader=current_reader,
        pins=None,
        trusted_candidates_by_session={},
        technical_candidates_by_session={},
        failure_reason=failure_reason,
    )


def _capacity_preflight(pins: OwnerPins) -> dict[str, Any]:
    trusted_count = len(pins.trusted.captures)
    technical_count = len(pins.technical.captures)
    trusted_required = trusted_count + TRUSTED_FUTURE_CAPTURES + REVISION_RESERVE
    technical_required = technical_count + TECHNICAL_FUTURE_CAPTURES + REVISION_RESERVE
    if (
        trusted_required > MAX_OWNER_GENERATION_CAPTURES
        or technical_required > MAX_OWNER_GENERATION_CAPTURES
    ):
        raise MarketMemoryExperienceAccrualError(
            "W2C pilot NO-GO: owner generation capacity preflight failed"
        )
    return {
        "max_owner_generation_capture_count": MAX_OWNER_GENERATION_CAPTURES,
        "trusted_initial_capture_count": trusted_count,
        "trusted_future_captures": TRUSTED_FUTURE_CAPTURES,
        "trusted_required_capacity": trusted_required,
        "technical_initial_capture_count": technical_count,
        "technical_future_captures": TECHNICAL_FUTURE_CAPTURES,
        "technical_required_capacity": technical_required,
        "revision_reserve": REVISION_RESERVE,
        "passed": True,
    }


def _new_installation(
    registration: Registration,
    *,
    installed_at: str,
    writer_commit: str,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": INSTALLATION_SCHEMA,
        "installation_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "registration_content_bytes": int(registration.value["content_bytes"]),
        "installed_at": installed_at,
        "activation_session": ACTIVATION_SESSION.isoformat(),
        "installation_status": "locally_observed_before_activation",
        "capacity_preflight": copy.deepcopy(dict(preflight)),
        "writer_commit": writer_commit,
        "claims": copy.deepcopy(_EXTERNAL_CLOCK_CLAIM),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["installation_id"] = _content_id(
        "mmspyexpinstall_", value, field="installation_id"
    )
    return _validate_installation(value, registration=registration)


def _validate_installation(
    value: Mapping[str, Any], *, registration: Registration
) -> dict[str, Any]:
    fields = {
        "schema", "installation_id", "registration_id", "registration_sha256",
        "registration_content_bytes", "installed_at", "activation_session",
        "installation_status", "capacity_preflight", "writer_commit", "claims",
        "authority",
    }
    clean = _freeze_json_native(value, label="W2C registration installation")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C registration installation fields are not canonical")
    if (
        clean.get("schema") != INSTALLATION_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("registration_content_bytes") != registration.value["content_bytes"]
        or clean.get("activation_session") != ACTIVATION_SESSION.isoformat()
        or clean.get("installation_status") != "locally_observed_before_activation"
        or clean.get("claims") != _EXTERNAL_CLOCK_CLAIM
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C registration installation binding drift")
    installed = _parse_utc(clean.get("installed_at"), field="installation installed_at")
    if installed >= datetime.combine(ACTIVATION_SESSION, time(), tzinfo=timezone.utc):
        _fail("W2C registration was not installed before activation")
    _require_commit(clean.get("writer_commit"))
    preflight = clean.get("capacity_preflight")
    expected_fields = {
        "max_owner_generation_capture_count", "trusted_initial_capture_count",
        "trusted_future_captures", "trusted_required_capacity",
        "technical_initial_capture_count", "technical_future_captures",
        "technical_required_capacity", "revision_reserve", "passed",
    }
    if not isinstance(preflight, Mapping) or set(preflight) != expected_fields:
        _fail("W2C installation capacity preflight is not canonical")
    if (
        preflight.get("max_owner_generation_capture_count") != MAX_OWNER_GENERATION_CAPTURES
        or preflight.get("trusted_future_captures") != TRUSTED_FUTURE_CAPTURES
        or preflight.get("technical_future_captures") != TECHNICAL_FUTURE_CAPTURES
        or preflight.get("revision_reserve") != REVISION_RESERVE
        or preflight.get("passed") is not True
    ):
        _fail("W2C installation capacity policy drift")
    for field in (
        "trusted_initial_capture_count", "trusted_required_capacity",
        "technical_initial_capture_count", "technical_required_capacity",
    ):
        if type(preflight.get(field)) is not int or not 0 <= preflight[field] <= 256:
            _fail("W2C installation capacity count is outside its bound")
    if (
        preflight["trusted_required_capacity"]
        != preflight["trusted_initial_capture_count"] + TRUSTED_FUTURE_CAPTURES + REVISION_RESERVE
        or preflight["technical_required_capacity"]
        != preflight["technical_initial_capture_count"] + TECHNICAL_FUTURE_CAPTURES + REVISION_RESERVE
    ):
        _fail("W2C installation capacity arithmetic drift")
    installation_id = clean.get("installation_id")
    if type(installation_id) is not str or not _INSTALLATION_ID.fullmatch(installation_id):
        _fail("W2C installation ID is malformed")
    if _content_id("mmspyexpinstall_", clean, field="installation_id") != installation_id:
        _fail("W2C installation ID does not bind its content")
    return clean


def _new_manifest(registration: Registration, installation: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": STORE_SCHEMA,
        "profile": PROFILE,
        "store_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "installation_id": installation["installation_id"],
        "authority": dict(market_memory.AUTHORITY),
    }
    value["store_id"] = _content_id("mmspyexpstore_", value, field="store_id")
    return _validate_manifest(value, registration=registration, installation=installation)


def _validate_manifest(
    value: Mapping[str, Any], *, registration: Registration, installation: Mapping[str, Any]
) -> dict[str, Any]:
    fields = {
        "schema", "profile", "store_id", "registration_id",
        "registration_sha256", "installation_id", "authority",
    }
    clean = _freeze_json_native(value, label="W2C store manifest")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C store manifest fields are not canonical")
    if (
        clean.get("schema") != STORE_SCHEMA
        or clean.get("profile") != PROFILE
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("installation_id") != installation["installation_id"]
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C store manifest binding drift")
    store_id = clean.get("store_id")
    if type(store_id) is not str or not _STORE_ID.fullmatch(store_id):
        _fail("W2C store ID is malformed")
    if _content_id("mmspyexpstore_", clean, field="store_id") != store_id:
        _fail("W2C store ID does not bind its manifest")
    return clean


def _initialize_or_load_store(
    root: Path,
    *,
    registration: Registration,
    pins: OwnerPins | None,
    installed_at: datetime | None,
    writer_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    installation_path = _safe_path(root, "registration_installation.json")
    manifest_path = _safe_path(root, "manifest.json")
    installation_exists = installation_path.exists() or installation_path.is_symlink()
    manifest_exists = manifest_path.exists() or manifest_path.is_symlink()
    if installation_exists:
        installation_raw, installation_body = _read_json_path(
            installation_path, limit=_MAX_INSTALLATION_BYTES,
            label="W2C registration installation",
        )
        installation = _validate_installation(installation_raw, registration=registration)
        # A crash after link publication may leave the deterministic pending
        # name.  Re-entering the create-once publisher validates and removes it.
        _write_create_once(
            installation_path,
            installation_body,
            limit=_MAX_INSTALLATION_BYTES,
            label="W2C registration installation",
        )
        expected_manifest = _new_manifest(registration, installation)
        expected_manifest_body = _canonical_bytes(expected_manifest)
        if manifest_exists:
            manifest_raw, manifest_body = _read_json_path(
                manifest_path, limit=_MAX_MANIFEST_BYTES,
                label="W2C store manifest",
            )
            manifest = _validate_manifest(
                manifest_raw, registration=registration, installation=installation
            )
            if manifest_body != expected_manifest_body:
                _fail("W2C store manifest differs from its installation receipt")
            _write_create_once(
                manifest_path,
                manifest_body,
                limit=_MAX_MANIFEST_BYTES,
                label="W2C store manifest",
            )
        else:
            _validate_empty_initialization_prefix(root)
            pending_manifest = _read_one_pending_create(
                manifest_path,
                limit=_MAX_MANIFEST_BYTES,
                label="W2C store manifest",
            )
            if pending_manifest is not None:
                pending_raw, pending_body = pending_manifest
                _validate_manifest(
                    pending_raw, registration=registration,
                    installation=installation,
                )
                if pending_body != expected_manifest_body:
                    _fail("pending W2C manifest differs from the installed receipt")
            _write_create_once(
                manifest_path,
                expected_manifest_body,
                limit=_MAX_MANIFEST_BYTES,
                label="W2C store manifest",
            )
            manifest = expected_manifest
        for name in (
            "prepared_objects", "prepared_sessions", "opportunities",
            "outcomes", "population_receipts", "technical_views",
        ):
            _mkdir(_safe_path(root, name))
        _fsync_directory(root)
        return manifest, installation

    if manifest_exists:
        _fail("W2C manifest without an installation receipt is ambiguous")

    _validate_empty_initialization_prefix(root)

    pending_installation = _read_one_pending_create(
        installation_path,
        limit=_MAX_INSTALLATION_BYTES,
        label="W2C registration installation",
    )
    if pending_installation is None:
        if installed_at is None:
            _fail("W2C new installation lacks its local installation observation")
        if installed_at >= datetime.combine(
            ACTIVATION_SESSION, time(), tzinfo=timezone.utc
        ):
            raise MarketMemoryExperienceAccrualError(
                "W2C pilot NO-GO: registration installation missed activation; register a new forward version"
            )
        if pins is None:
            _fail("W2C new installation lacks exact preactivation owner pins")
        preflight = _capacity_preflight(pins)
        installation = _new_installation(
            registration,
            installed_at=_format_utc(installed_at),
            writer_commit=writer_commit,
            preflight=preflight,
        )
        installation_body = _canonical_bytes(installation)
    else:
        pending_raw, installation_body = pending_installation
        installation = _validate_installation(
            pending_raw, registration=registration
        )
    manifest = _new_manifest(registration, installation)
    _write_create_once(
        installation_path, installation_body,
        limit=_MAX_INSTALLATION_BYTES, label="W2C registration installation",
    )
    manifest_body = _canonical_bytes(manifest)
    pending_manifest = _read_one_pending_create(
        manifest_path,
        limit=_MAX_MANIFEST_BYTES,
        label="W2C store manifest",
    )
    if pending_manifest is not None:
        pending_raw, pending_body = pending_manifest
        _validate_manifest(
            pending_raw, registration=registration, installation=installation
        )
        if pending_body != manifest_body:
            _fail("pending W2C manifest differs from the installed receipt")
    _write_create_once(
        manifest_path, manifest_body,
        limit=_MAX_MANIFEST_BYTES, label="W2C store manifest",
    )
    for name in (
        "prepared_objects", "prepared_sessions", "opportunities", "outcomes",
        "population_receipts", "technical_views",
    ):
        _mkdir(_safe_path(root, name))
    _fsync_directory(root)
    return manifest, installation


def _generation_ref(pin: Any, *, technical: bool) -> dict[str, Any]:
    expected_profile = (
        technical_store.STORE_PROFILE if technical else trusted_store.TRUSTED_STORE_PROFILE
    )
    if pin.profile != expected_profile:
        _fail("W2C owner generation profile drift")
    return {
        "profile": expected_profile,
        "store_id": pin.store_id,
        "generation_id": pin.generation_id,
        "generation_sha256": pin.generation_sha256,
        "capture_count": len(pin.captures),
    }


def _same_generation(left: Any, right: Any) -> bool:
    return (
        left.profile,
        left.store_id,
        left.generation_id,
        left.generation_sha256,
    ) == (
        right.profile,
        right.store_id,
        right.generation_id,
        right.generation_sha256,
    )


def _require_clock_not_after(value: object, cutoff: datetime, *, field: str) -> str:
    parsed = _parse_utc(value, field=field)
    if parsed > cutoff:
        raise MarketMemoryExperienceAccrualError(
            f"W2C owner availability clock follows actual pin cutoff: {field}"
        )
    return str(value)


def _trusted_candidates(
    reader: trusted_store.TrustedFileAsKnownAtReader,
    pin: Any,
    *,
    session: date,
) -> list[_TrustedCandidate]:
    return list(_trusted_candidates_by_session(reader, pin).get(session.isoformat(), ()))


def _trusted_candidates_by_session(
    reader: trusted_store.TrustedFileAsKnownAtReader,
    pin: Any,
) -> dict[str, tuple[_TrustedCandidate, ...]]:
    """Project each trusted owner capture once into a run-scoped session index."""

    grouped: dict[str, list[_TrustedCandidate]] = {}
    projections = reader.read_pinned_capture_projections(pin)
    if len(projections) != len(pin.captures):
        _fail("W2C trusted batch projection differs from its pinned census")
    for projection in projections:
        receipt = projection.receipt
        feature = projection.feature
        session_text = feature.get("source_artifact", {}).get("source_asof")
        if type(session_text) is not str or not _SESSION.fullmatch(session_text):
            _fail("W2C trusted owner source session is malformed")
        packet = projection.stored.packet
        identity = packet["identity_receipt"]
        macro_receipt = next(
            row
            for row in packet["feature_receipts"]
            if row["feature_id"] == "macro.regime_state"
        )
        if receipt["subject"] != {
            "subject_id": _SUBJECT["subject_id"],
            "instrument_id": _SUBJECT["instrument_id"],
        }:
            _fail("W2C trusted owner subject differs from the registered SPY identity")
        if (
            identity.get("subject_id") != _SUBJECT["subject_id"]
            or identity.get("instrument_id") != _SUBJECT["instrument_id"]
            or identity.get("identity_version") != _SUBJECT["identity_version"]
            or identity.get("calendar_id") != _CALENDAR["calendar_id"]
        ):
            _fail("W2C trusted owner identity/calendar binding drift")
        (
            decision_projection,
            decision_projection_reason,
            decision_raw_categories,
        ) = _decision_state_projection(
            feature,
            feature_snapshot_id=receipt["feature_snapshot"]["snapshot_id"],
            feature_content_sha256=receipt["feature_snapshot"]["content_sha256"],
        )
        grouped.setdefault(session_text, []).append(
            _TrustedCandidate(
                {
                    "capture_id": receipt["capture_id"],
                    "query_id": receipt["query_id"],
                    "context_id": receipt["context_id"],
                    "packet_sha256": receipt["packet_sha256"],
                    "feature_snapshot_id": receipt["feature_snapshot"]["snapshot_id"],
                    "feature_content_sha256": receipt["feature_snapshot"]["content_sha256"],
                    "source_session": session_text,
                    "captured_at": receipt["captured_at"],
                    "feature_observed_at": macro_receipt["observed_at"],
                    "source_observed_at": receipt["source_evidence"]["raw_source_observed_at"],
                    "subject_id": _SUBJECT["subject_id"],
                    "instrument_id": _SUBJECT["instrument_id"],
                    "identity_version": _SUBJECT["identity_version"],
                    "decision_state_projection": decision_projection,
                    "decision_state_projection_reason": decision_projection_reason,
                    "decision_state_raw_categories": decision_raw_categories,
                }
            )
        )
    return {session: tuple(rows) for session, rows in grouped.items()}


def _technical_candidate_from_entry(
    technical_root: str | Path,
    pin: technical_store.PinnedTechnicalGenerationSnapshot,
    entry: technical_store.PinnedTechnicalCaptureIndexEntry,
) -> _TechnicalCandidate:
    stored_rows = technical_store.load_technical_actual_output_captures_from_pinned_generation(
        technical_root,
        pin=pin,
        capture_ids=(entry.capture_id,),
    )
    return _technical_candidate_from_stored(entry, stored_rows[0])


def _technical_candidate_from_stored(
    entry: technical_store.PinnedTechnicalCaptureIndexEntry,
    stored: technical_store.StoredTechnicalActualOutput,
) -> _TechnicalCandidate:
    receipt = stored.capture_receipt
    feature = stored.bundle.feature_object
    if feature.get("subject") != _TECHNICAL_SUBJECT:
        _fail("W2C technical owner subject/MIC/calendar binding drift")
    if feature.get("session") != entry.session or receipt.get("session") != entry.session:
        _fail("W2C technical owner session binding drift")
    basis = feature.get("price_basis")
    if (
        not isinstance(basis, Mapping)
        or basis.get("basis") != "provider_documented_unadjusted_flat_file"
        or basis.get("source_product") != "us_stocks_sip/day_aggs_v1"
        or basis.get("source_session_scope")
        != "provider_daily_aggregate_eligible_trades_full_market_day"
        or basis.get("regular_session_close_authenticated") is not False
        or basis.get("xnys_calendar_dates_only") is not True
        or basis.get("raw_unadjusted") is not True
        or basis.get("split_adjusted") is not False
        or basis.get("dividend_adjusted") is not False
        or basis.get("other_corporate_action_adjusted") is not False
        or basis.get("economic_return") is not False
    ):
        _fail("W2C technical owner price-basis contract drift")
    end_close = feature.get("state", {}).get("end_close")
    mark = _binary64_mark(end_close, field="technical end_close")
    reference = {
        "capture_id": receipt["capture_id"],
        "revision_id": receipt["revision_id"],
        "source_observation_id": receipt["source_observation"]["source_observation_id"],
        "snapshot_id": receipt["feature_object"]["snapshot_id"],
        "source_session": entry.session,
        "first_observed_at": receipt["clocks"]["first_observed_at"],
        "spy_parquet_sha256": receipt["source_bodies"]["spy_daily_parquet"]["sha256"],
        **mark,
        "subject": copy.deepcopy(_SUBJECT),
        "calendar": copy.deepcopy(_CALENDAR),
        "price_basis": {
            "raw_unadjusted": True,
            "split_adjusted": False,
            "dividend_adjusted": False,
            "economic_return": False,
        },
    }
    return _TechnicalCandidate(reference=reference, end_close=end_close)


def _technical_candidates(
    technical_root: str | Path,
    pin: technical_store.PinnedTechnicalGenerationSnapshot,
    *,
    session: date,
) -> list[_TechnicalCandidate]:
    entries = [
        entry for entry in pin.captures if entry.session == session.isoformat()
    ]
    if not entries:
        return []
    stored = technical_store.load_technical_actual_output_captures_from_pinned_generation(
        technical_root,
        pin=pin,
        capture_ids=[entry.capture_id for entry in entries],
    )
    return [
        _technical_candidate_from_stored(entry, row)
        for entry, row in zip(entries, stored, strict=True)
    ]


def _technical_view_head_path(root: Path) -> Path:
    return _safe_path(root, "technical_view_HEAD.json")


def _validate_technical_view(
    value: Mapping[str, Any], *, registration: Registration
) -> dict[str, Any]:
    fields = {
        "schema", "technical_view_id", "registration_id",
        "registration_sha256", "previous_technical_view_id",
        "pair_observed_at", "trusted_generation", "technical_generation",
        "captures",
    }
    clean = _freeze_json_native(value, label="W2C technical view")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C technical view fields are not canonical")
    if (
        clean.get("schema") != TECHNICAL_VIEW_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
    ):
        _fail("W2C technical view registration binding drift")
    previous_view_id = clean.get("previous_technical_view_id")
    if previous_view_id is not None and (
        type(previous_view_id) is not str
        or not _TECHNICAL_VIEW_ID.fullmatch(previous_view_id)
        or previous_view_id == clean.get("technical_view_id")
    ):
        _fail("W2C technical-view predecessor is malformed or self-referential")
    generation = _validate_generation_ref(
        clean.get("technical_generation"), technical=True
    )
    clean["trusted_generation"] = _validate_generation_ref(
        clean.get("trusted_generation"), technical=False
    )
    pair_observed_at = _parse_utc(
        clean.get("pair_observed_at"), field="technical-view owner pair"
    )
    rows = clean.get("captures")
    if not isinstance(rows, list) or len(rows) != generation["capture_count"]:
        _fail("W2C technical view capture census differs from its generation")
    capture_ids: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"index", "reference"}:
            _fail("W2C technical view row fields are not canonical")
        index = row["index"]
        index_fields = {
            "capture_id", "session", "revision_id", "source_observation_id",
            "snapshot_id", "first_observed_at", "receipt_sha256",
        }
        if not isinstance(index, Mapping) or set(index) != index_fields:
            _fail("W2C technical view index fields are not canonical")
        reference = _validate_technical_ref(
            row["reference"], session=str(index.get("session"))
        )
        if _parse_utc(
            reference["first_observed_at"],
            field="technical-view capture first_observed_at",
        ) > pair_observed_at:
            _fail("W2C technical view contains a future owner capture")
        if (
            reference["capture_id"] != index.get("capture_id")
            or reference["revision_id"] != index.get("revision_id")
            or reference["source_observation_id"]
            != index.get("source_observation_id")
            or reference["snapshot_id"] != index.get("snapshot_id")
            or reference["first_observed_at"] != index.get("first_observed_at")
        ):
            _fail("W2C technical view reference differs from its owner index")
        _require_digest(index.get("receipt_sha256"), field="technical view receipt")
        capture_ids.append(str(index["capture_id"]))
    if len(capture_ids) != len(set(capture_ids)):
        _fail("W2C technical view duplicates an owner capture")
    view_id = clean.get("technical_view_id")
    if type(view_id) is not str or not _TECHNICAL_VIEW_ID.fullmatch(view_id):
        _fail("W2C technical view ID is malformed")
    if _content_id("mmspyexptechview_", clean, field="technical_view_id") != view_id:
        _fail("W2C technical view ID does not bind its content")
    clean["technical_generation"] = generation
    return clean


def _recover_technical_view_chain_head(
    root: Path,
    *,
    registration: Registration,
    pin: technical_store.PinnedTechnicalGenerationSnapshot | None,
) -> dict[str, Any] | None:
    views_directory = _safe_path(root, "technical_views")
    head_path = _technical_view_head_path(root)
    if not views_directory.exists():
        if head_path.exists() or head_path.is_symlink() or _pending_create_paths(
            head_path
        ):
            _fail("W2C technical-view HEAD exists without its inventory")
        return None
    view_ids: set[str] = set()
    for item in sorted(views_directory.iterdir()):
        final_match = re.fullmatch(
            r"(mmspyexptechview_[a-f0-9]{64})\.json", item.name
        )
        pending_match = re.fullmatch(
            r"\.(mmspyexptechview_[a-f0-9]{64})\.json\.[a-f0-9]{64}\.pending",
            item.name,
        )
        if final_match is None and pending_match is None:
            _fail("W2C technical-view inventory is noncanonical")
        view_ids.add(
            (final_match or pending_match).group(1)  # type: ignore[union-attr]
        )
    views: dict[str, dict[str, Any]] = {}
    allowed_generation_ids = (
        None
        if pin is None
        else {pin.generation_id, *pin.ancestry_generation_ids}
    )
    for view_id in sorted(view_ids):
        final_path = _safe_path(
            root, "technical_views", f"{view_id}.json"
        )

        def validate_view(
            raw: dict[str, Any], _body: bytes, *, expected_id: str = view_id
        ) -> dict[str, Any]:
            clean = _validate_technical_view(raw, registration=registration)
            generation = clean["technical_generation"]
            if clean["technical_view_id"] != expected_id:
                _fail("W2C technical-view path differs from its ID")
            if pin is not None and (
                generation["store_id"] != pin.store_id
                or generation["generation_id"] not in allowed_generation_ids
            ):
                _fail("W2C technical view is outside current ancestry")
            return clean

        clean = _recover_immutable_json(
            final_path,
            limit=_MAX_TECHNICAL_VIEW_BYTES,
            label="W2C technical view",
            validator=validate_view,
        )
        if clean is None:  # pragma: no cover - inventory proves a candidate
            _fail("W2C technical-view publication disappeared during recovery")
        views[view_id] = clean
    if not views:
        if head_path.exists() or head_path.is_symlink() or _pending_create_paths(
            head_path
        ):
            _fail("W2C technical-view HEAD exists without a target")
        return None

    predecessor_ids: set[str] = set()
    successor_by_id: dict[str, str] = {}
    roots: list[str] = []
    generation_refs_by_kind: dict[str, dict[str, dict[str, Any]]] = {
        "trusted_generation": {},
        "technical_generation": {},
    }
    for view_id, view in views.items():
        for kind, refs_by_id in generation_refs_by_kind.items():
            generation = view[kind]
            generation_id = str(generation["generation_id"])
            prior_generation = refs_by_id.get(generation_id)
            if prior_generation is not None and prior_generation != generation:
                _fail("W2C technical-view chain rewrites a generation identity")
            refs_by_id[generation_id] = generation
        predecessor = view["previous_technical_view_id"]
        if predecessor is None:
            roots.append(view_id)
            continue
        predecessor = str(predecessor)
        if predecessor not in views or predecessor in successor_by_id:
            _fail("W2C technical-view predecessor chain is gapped or branched")
        predecessor_ids.add(predecessor)
        successor_by_id[predecessor] = view_id
    tips = sorted(set(views) - predecessor_ids)
    if len(roots) != 1 or len(tips) != 1:
        _fail("W2C technical-view predecessor chain is not one history")
    tip_id = tips[0]
    reached: set[str] = set()
    cursor: str | None = tip_id
    descendant: dict[str, Any] | None = None
    generation_history: list[str] = []
    trusted_generation_history: list[str] = []
    while cursor is not None:
        if cursor in reached:
            _fail("W2C technical-view predecessor chain is cyclic")
        reached.add(cursor)
        view = views[cursor]
        if descendant is not None:
            predecessor_rows = view["captures"]
            descendant_by_capture_id = {
                str(row["index"]["capture_id"]): row
                for row in descendant["captures"]
            }
            if (
                descendant["technical_generation"]["profile"]
                != view["technical_generation"]["profile"]
                or descendant["technical_generation"]["store_id"]
                != view["technical_generation"]["store_id"]
                or descendant["trusted_generation"]["profile"]
                != view["trusted_generation"]["profile"]
                or descendant["trusted_generation"]["store_id"]
                != view["trusted_generation"]["store_id"]
                or descendant["technical_generation"]["capture_count"]
                < view["technical_generation"]["capture_count"]
                or descendant["trusted_generation"]["capture_count"]
                < view["trusted_generation"]["capture_count"]
                or _parse_utc(
                    descendant["pair_observed_at"],
                    field="technical-view descendant owner pair",
                )
                < _parse_utc(
                    view["pair_observed_at"],
                    field="technical-view predecessor owner pair",
                )
                or any(
                    descendant_by_capture_id.get(
                        str(row["index"]["capture_id"])
                    )
                    != row
                    for row in predecessor_rows
                )
            ):
                _fail("W2C technical-view successor rewrites its predecessor")
        generation_history.append(
            str(view["technical_generation"]["generation_id"])
        )
        trusted_generation_history.append(
            str(view["trusted_generation"]["generation_id"])
        )
        descendant = view
        predecessor = view["previous_technical_view_id"]
        cursor = str(predecessor) if predecessor is not None else None
    if reached != set(views):
        _fail("W2C technical-view inventory contains an orphan")
    # Traversal above is newest-to-oldest.  A generation may span consecutive
    # views while the trusted owner advances, but cannot be reopened later.
    compressed_generations = [
        generation_id
        for index, generation_id in enumerate(generation_history)
        if index == 0 or generation_id != generation_history[index - 1]
    ]
    if len(compressed_generations) != len(set(compressed_generations)):
        _fail("W2C technical-view chain reopens an old generation")
    compressed_trusted_generations = [
        generation_id
        for index, generation_id in enumerate(trusted_generation_history)
        if index == 0
        or generation_id != trusted_generation_history[index - 1]
    ]
    if len(compressed_trusted_generations) != len(
        set(compressed_trusted_generations)
    ):
        _fail("W2C technical-view chain reopens an old trusted generation")

    def validate_head(
        head: dict[str, Any], _head_body: bytes
    ) -> dict[str, Any]:
        if type(head) is not dict or set(head) != {
            "schema", "technical_view_id", "technical_view_sha256",
            "technical_view_bytes", "technical_generation_id",
        }:
            _fail("W2C technical view HEAD fields are not canonical")
        view_id = head.get("technical_view_id")
        if (
            head.get("schema") != TECHNICAL_VIEW_HEAD_SCHEMA
            or type(view_id) is not str
            or not _TECHNICAL_VIEW_ID.fullmatch(view_id)
            or type(head.get("technical_view_bytes")) is not int
            or not 1 <= head["technical_view_bytes"] <= _MAX_TECHNICAL_VIEW_BYTES
        ):
            _fail("W2C technical view HEAD is malformed")
        _require_digest(
            head.get("technical_view_sha256"), field="technical view HEAD"
        )
        if view_id not in views:
            _fail("W2C technical-view HEAD target is absent")
        view_body = _read_bounded(
            _safe_path(root, "technical_views", f"{view_id}.json"),
            limit=_MAX_TECHNICAL_VIEW_BYTES,
            label="W2C technical view HEAD target",
        )
        if (
            len(view_body) != head["technical_view_bytes"]
            or _digest(view_body) != head["technical_view_sha256"]
        ):
            _fail("W2C technical view differs from its HEAD")
        previous_generation_id = views[view_id]["technical_generation"][
            "generation_id"
        ]
        if (
            head.get("technical_generation_id") != previous_generation_id
        ):
            _fail("W2C technical-view HEAD generation drift")
        return head

    head = _recover_mutable_head(
        head_path, label="W2C technical view HEAD", validator=validate_head
    )
    if head is None or head["technical_view_id"] != tip_id:
        if head is not None and str(head["technical_view_id"]) not in reached:
            _fail("W2C technical-view HEAD is outside its predecessor chain")
        _publish_technical_view(root, views[tip_id])
    return views[tip_id]


def _load_cached_technical_view(
    root: Path,
    *,
    registration: Registration,
    pin: technical_store.PinnedTechnicalGenerationSnapshot,
) -> dict[str, Any] | None:
    view = _recover_technical_view_chain_head(
        root, registration=registration, pin=pin
    )
    if view is None:
        return None
    active = {entry.capture_id: entry.as_dict() for entry in pin.captures}
    for row in view["captures"]:
        if active.get(row["index"]["capture_id"]) != row["index"]:
            _fail("W2C cached technical index is not an immutable active prefix")
    return view


def _prepare_technical_view(
    root: Path,
    *,
    registration: Registration,
    technical_root: str | Path,
    pin: technical_store.PinnedTechnicalGenerationSnapshot,
    trusted_pin: Any,
    pair_observed_at: str,
) -> tuple[dict[str, tuple[_TechnicalCandidate, ...]], dict[str, Any] | None]:
    _parse_utc(pair_observed_at, field="technical-view owner pair")
    cached = _load_cached_technical_view(
        root, registration=registration, pin=pin
    )
    cached_rows = [] if cached is None else list(cached["captures"])
    cached_ids = {row["index"]["capture_id"] for row in cached_rows}
    new_entries = [entry for entry in pin.captures if entry.capture_id not in cached_ids]
    try:
        stored = (
            technical_store.load_technical_actual_output_captures_from_pinned_generation(
                technical_root,
                pin=pin,
                capture_ids=[entry.capture_id for entry in new_entries],
            )
            if new_entries else ()
        )
        new_rows = [
            {
                "index": entry.as_dict(),
                "reference": _technical_candidate_from_stored(entry, row).reference,
            }
            for entry, row in zip(new_entries, stored, strict=True)
        ]
    except MarketMemoryExperienceStoreError as exc:
        raise _OwnerObservationIntegrityError(
            "technical owner projection failed W2C validation"
        ) from exc
    rows = [*cached_rows, *new_rows]
    by_id = {row["index"]["capture_id"]: row for row in rows}
    ordered_rows = [by_id[entry.capture_id] for entry in pin.captures]
    if len(ordered_rows) != len(pin.captures):
        _fail("W2C technical view is incomplete for its authenticated pin")
    by_session: dict[str, list[_TechnicalCandidate]] = {}
    for row in ordered_rows:
        reference = copy.deepcopy(dict(row["reference"]))
        by_session.setdefault(str(row["index"]["session"]), []).append(
            _TechnicalCandidate(
                reference=reference,
                end_close=float.fromhex(reference["end_close_binary64_hex"]),
            )
        )
    grouped = {key: tuple(value) for key, value in by_session.items()}
    if (
        cached is not None
        and cached["technical_generation"]["generation_id"]
        == pin.generation_id
        and cached["trusted_generation"]["generation_id"]
        == trusted_pin.generation_id
    ):
        if new_entries:
            _fail("W2C unchanged technical generation produced new captures")
        return grouped, None
    view: dict[str, Any] = {
        "schema": TECHNICAL_VIEW_SCHEMA,
        "technical_view_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "previous_technical_view_id": (
            cached["technical_view_id"] if cached is not None else None
        ),
        "pair_observed_at": pair_observed_at,
        "trusted_generation": _generation_ref(
            trusted_pin, technical=False
        ),
        "technical_generation": _generation_ref(pin, technical=True),
        "captures": ordered_rows,
    }
    view["technical_view_id"] = _content_id(
        "mmspyexptechview_", view, field="technical_view_id"
    )
    try:
        clean_view = _validate_technical_view(
            view, registration=registration
        )
    except MarketMemoryExperienceStoreError as exc:
        raise _OwnerObservationIntegrityError(
            "technical owner view failed W2C validation"
        ) from exc
    return grouped, clean_view


def _publish_technical_view(root: Path, view: Mapping[str, Any] | None) -> None:
    if view is None:
        return
    body = _canonical_bytes(view)
    _write_create_once(
        _safe_path(root, "technical_views", f"{view['technical_view_id']}.json"),
        body,
        limit=_MAX_TECHNICAL_VIEW_BYTES,
        label="W2C technical view",
    )
    head = {
        "schema": TECHNICAL_VIEW_HEAD_SCHEMA,
        "technical_view_id": view["technical_view_id"],
        "technical_view_sha256": _digest(body),
        "technical_view_bytes": len(body),
        "technical_generation_id": view["technical_generation"]["generation_id"],
    }
    _replace_head(_technical_view_head_path(root), _canonical_bytes(head))


def _recover_last_registered_run_view(
    root: Path, *, registration: Registration
) -> _RunOwnerView | None:
    """Recover the last durable pre-terminal owner view under writer.lock.

    A retry after the terminal window must finish an already-authenticated
    correction suffix from the immutable local view, not replace that evidence
    with a new post-deadline owner observation.  The view chain is authenticated
    first; equal-clock or later out-of-window descendants are ambiguous and
    fail closed.
    """

    tip = _recover_technical_view_chain_head(
        root, registration=registration, pin=None
    )
    if tip is None:
        return None
    views: list[dict[str, Any]] = []
    reached: set[str] = set()
    cursor: dict[str, Any] | None = tip
    while cursor is not None:
        view_id = str(cursor["technical_view_id"])
        if view_id in reached:
            _fail("W2C persisted technical-view recovery is cyclic")
        reached.add(view_id)
        views.append(cursor)
        predecessor_id = cursor["previous_technical_view_id"]
        if predecessor_id is None:
            cursor = None
            continue
        raw, _body = _read_json_path(
            _safe_path(
                root, "technical_views", f"{predecessor_id}.json"
            ),
            limit=_MAX_TECHNICAL_VIEW_BYTES,
            label="W2C persisted technical-view predecessor",
        )
        cursor = _validate_technical_view(raw, registration=registration)
        if cursor["technical_view_id"] != predecessor_id:
            _fail("W2C persisted technical-view predecessor path drift")

    _terminal_opened, terminal_deadline = _terminal_window()

    def registered_daily_window(value: datetime) -> bool:
        opened = datetime.combine(
            value.date(), time(4, 30), tzinfo=timezone.utc
        )
        return opened <= value <= opened + timedelta(minutes=15)

    eligible = [
        (view, _parse_utc(
            view["pair_observed_at"], field="persisted owner pair"
        ))
        for view in views
        if registered_daily_window(
            _parse_utc(
                view["pair_observed_at"], field="persisted owner pair"
            )
        )
        and _parse_utc(
            view["pair_observed_at"], field="persisted owner pair"
        ) <= terminal_deadline
    ]
    if not eligible:
        return None
    latest_clock = max(clock for _view, clock in eligible)
    latest = [view for view, clock in eligible if clock == latest_clock]
    if len(latest) != 1:
        _fail("W2C persisted owner-pair clock is ambiguous")
    selected = latest[0]
    if any(
        _parse_utc(view["pair_observed_at"], field="later persisted owner pair")
        > latest_clock
        for view in views
    ):
        _fail("W2C persisted owner-pair recovery has later out-of-window facts")

    ancestry_generation_ids: list[str] = []
    selected_seen = False
    for view in views:
        if view["technical_view_id"] == selected["technical_view_id"]:
            selected_seen = True
            continue
        if not selected_seen:
            continue
        generation_id = str(view["technical_generation"]["generation_id"])
        if generation_id not in ancestry_generation_ids:
            ancestry_generation_ids.append(generation_id)

    entries = tuple(
        technical_store.PinnedTechnicalCaptureIndexEntry(
            **dict(row["index"])
        )
        for row in selected["captures"]
    )
    technical_generation = selected["technical_generation"]
    technical_pin = technical_store.PinnedTechnicalGenerationSnapshot(
        profile=str(technical_generation["profile"]),
        store_id=str(technical_generation["store_id"]),
        generation_id=str(technical_generation["generation_id"]),
        generation_sha256=str(technical_generation["generation_sha256"]),
        captures=entries,
        ancestry_generation_ids=tuple(ancestry_generation_ids),
    )
    trusted_generation = selected["trusted_generation"]
    trusted_pin = _ReferenceGenerationPin(
        profile=str(trusted_generation["profile"]),
        store_id=str(trusted_generation["store_id"]),
        generation_id=str(trusted_generation["generation_id"]),
        generation_sha256=str(trusted_generation["generation_sha256"]),
        captures=(None,) * int(trusted_generation["capture_count"]),
    )
    by_session: dict[str, list[_TechnicalCandidate]] = {}
    for row in selected["captures"]:
        reference = copy.deepcopy(dict(row["reference"]))
        by_session.setdefault(str(row["index"]["session"]), []).append(
            _TechnicalCandidate(
                reference=reference,
                end_close=float.fromhex(
                    reference["end_close_binary64_hex"]
                ),
            )
        )
    return _RunOwnerView(
        pin_observed_at=str(selected["pair_observed_at"]),
        stable=True,
        reader=None,
        pins=OwnerPins(trusted=trusted_pin, technical=technical_pin),
        trusted_candidates_by_session={},
        technical_candidates_by_session={
            session: tuple(candidates)
            for session, candidates in by_session.items()
        },
    )


def _owner_clock_tie(values: list[Any], *, clock_field: str) -> bool:
    clocks = [
        _parse_utc(item.reference[clock_field], field=f"owner {clock_field}")
        for item in values
    ]
    return len(clocks) != len(set(clocks))


def _first_owner_observed(values: list[Any], *, clock_field: str) -> Any | None:
    if not values:
        return None
    return min(
        values,
        key=lambda item: (
            _parse_utc(
                item.reference[clock_field], field=f"owner {clock_field}"
            ),
            item.reference.get("capture_id", ""),
        ),
    )


def _validate_candidate_clocks(
    trusted_candidates: list[_TrustedCandidate],
    technical_candidates: list[_TechnicalCandidate],
    *,
    cutoff: datetime,
) -> None:
    for candidate in trusted_candidates:
        ref = candidate.reference
        for field in ("captured_at", "feature_observed_at", "source_observed_at"):
            _require_clock_not_after(ref[field], cutoff, field=f"trusted {field}")
    for candidate in technical_candidates:
        _require_clock_not_after(
            candidate.reference["first_observed_at"],
            cutoff,
            field="technical first_observed_at",
        )


def _source_pins(
    pins: OwnerPins,
    *,
    pin_observed_at: str,
    trusted_candidate: _TrustedCandidate | None,
    technical_candidate: _TechnicalCandidate | None,
) -> dict[str, Any]:
    return {
        "pin_observed_at": pin_observed_at,
        "selection": "owner_observed_revision_chain.v1",
        "subject": copy.deepcopy(_SUBJECT),
        "calendar": copy.deepcopy(_CALENDAR),
        "trusted_generation": _generation_ref(pins.trusted, technical=False),
        "technical_generation": _generation_ref(pins.technical, technical=True),
        "trusted_capture": (
            copy.deepcopy(trusted_candidate.reference)
            if trusted_candidate is not None else None
        ),
        "technical_capture": (
            copy.deepcopy(technical_candidate.reference)
            if technical_candidate is not None else None
        ),
    }


def _observe_opportunity_sources(
    *,
    reader: trusted_store.TrustedFileAsKnownAtReader,
    trusted_root: str | Path,
    technical_root: str | Path,
    session: date,
    clock: Callable[[], datetime],
) -> SourceSandwich:
    """Perform A1/B1 -> writer clock -> A2/B2 over exact owner APIs."""

    before_trusted = reader.read_pinned_generation(
        maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    before_technical = technical_store.pin_technical_actual_output_generation(
        technical_root, maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    trusted_candidates = _trusted_candidates(reader, before_trusted, session=session)
    technical_candidates = _technical_candidates(
        technical_root, before_technical, session=session
    )
    observed = _sample_clock(clock)
    observed_at = _format_utc(observed)
    after_trusted = reader.read_pinned_generation(
        maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    after_technical = technical_store.pin_technical_actual_output_generation(
        technical_root, maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    stable = _same_generation(before_trusted, after_trusted) and _same_generation(
        before_technical, after_technical
    )
    if not stable:
        return SourceSandwich(
            sampled_at=observed_at,
            stable=False,
            source_pins=None,
            disposition=None,
            reason="owner_pair_not_stable",
        )
    _validate_candidate_clocks(
        trusted_candidates, technical_candidates, cutoff=observed
    )
    pins = OwnerPins(trusted=before_trusted, technical=before_technical)
    trusted_tie = _owner_clock_tie(trusted_candidates, clock_field="captured_at")
    technical_tie = _owner_clock_tie(
        technical_candidates, clock_field="first_observed_at"
    )
    trusted_candidate = None if trusted_tie else _first_owner_observed(
        trusted_candidates, clock_field="captured_at"
    )
    technical_candidate = None if technical_tie else _first_owner_observed(
        technical_candidates, clock_field="first_observed_at"
    )
    source_pins = _source_pins(
        pins,
        pin_observed_at=observed_at,
        trusted_candidate=trusted_candidate,
        technical_candidate=technical_candidate,
    )
    if trusted_tie or technical_tie:
        return SourceSandwich(
            sampled_at=observed_at,
            stable=True,
            source_pins=source_pins,
            disposition="abstained",
            reason="owner_capture_clock_tie",
        )
    if trusted_candidate is None and technical_candidate is None:
        reason = "trusted_macro_and_technical_session_absent"
        disposition = "abstained"
    elif trusted_candidate is None:
        reason = "trusted_macro_session_absent"
        disposition = "abstained"
    elif technical_candidate is None:
        reason = "technical_session_absent"
        disposition = "abstained"
    else:
        reason = "exact_same_session_owner_pins"
        disposition = "admitted"
    return SourceSandwich(
        sampled_at=observed_at,
        stable=True,
        source_pins=source_pins,
        disposition=disposition,
        reason=reason,
    )


def _opportunity_sandwich_from_run(
    view: _RunOwnerView,
    *,
    session: date,
) -> SourceSandwich:
    if not view.stable or view.pins is None:
        return SourceSandwich(
            sampled_at=view.pin_observed_at,
            stable=False,
            source_pins=None,
            disposition=None,
            reason="owner_pair_not_stable",
        )
    cutoff = _parse_utc(view.pin_observed_at, field="run owner pin")
    trusted_candidates = list(
        view.trusted_candidates_by_session.get(session.isoformat(), ())
    )
    technical_candidates = list(
        view.technical_candidates_by_session.get(session.isoformat(), ())
    )
    _validate_candidate_clocks(
        trusted_candidates, technical_candidates, cutoff=cutoff
    )
    trusted_tie = _owner_clock_tie(
        trusted_candidates, clock_field="captured_at"
    )
    technical_tie = _owner_clock_tie(
        technical_candidates, clock_field="first_observed_at"
    )
    trusted_candidate = None if trusted_tie else _first_owner_observed(
        trusted_candidates, clock_field="captured_at"
    )
    technical_candidate = None if technical_tie else _first_owner_observed(
        technical_candidates, clock_field="first_observed_at"
    )
    source_pins = _source_pins(
        view.pins,
        pin_observed_at=view.pin_observed_at,
        trusted_candidate=trusted_candidate,
        technical_candidate=technical_candidate,
    )
    if trusted_tie or technical_tie:
        return SourceSandwich(
            sampled_at=view.pin_observed_at,
            stable=True,
            source_pins=source_pins,
            disposition="abstained",
            reason="owner_capture_clock_tie",
        )
    if trusted_candidate is None and technical_candidate is None:
        disposition, reason = (
            "abstained", "trusted_macro_and_technical_session_absent"
        )
    elif trusted_candidate is None:
        disposition, reason = "abstained", "trusted_macro_session_absent"
    elif technical_candidate is None:
        disposition, reason = "abstained", "technical_session_absent"
    else:
        disposition, reason = "admitted", "exact_same_session_owner_pins"
    return SourceSandwich(
        sampled_at=view.pin_observed_at,
        stable=True,
        source_pins=source_pins,
        disposition=disposition,
        reason=reason,
    )


def _validate_generation_ref(value: object, *, technical: bool) -> dict[str, Any]:
    fields = {"profile", "store_id", "generation_id", "generation_sha256", "capture_count"}
    clean = _freeze_json_native(value, label="W2C generation reference")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C owner generation reference fields are not canonical")
    prefix = "mmactual" if technical else "mm"
    expected_profile = technical_store.STORE_PROFILE if technical else trusted_store.TRUSTED_STORE_PROFILE
    store_pattern = re.compile(rf"{prefix}store_[a-f0-9]{{64}}\Z")
    generation_pattern = re.compile(rf"{prefix}generation_[a-f0-9]{{64}}\Z")
    if (
        clean.get("profile") != expected_profile
        or type(clean.get("store_id")) is not str
        or not store_pattern.fullmatch(clean["store_id"])
        or type(clean.get("generation_id")) is not str
        or not generation_pattern.fullmatch(clean["generation_id"])
    ):
        _fail("W2C owner generation identity is malformed")
    _require_digest(clean.get("generation_sha256"), field="owner generation digest")
    if type(clean.get("capture_count")) is not int or not 0 <= clean["capture_count"] <= 256:
        _fail("W2C owner generation count exceeds the pilot pin cap")
    return clean


def _validate_exact_mark_fields(value: Mapping[str, Any], *, prefix: str = "") -> float:
    hex_field = f"{prefix}end_close_binary64_hex"
    decimal_field = f"{prefix}end_close_exact_decimal"
    raw_hex = value.get(hex_field)
    raw_decimal = value.get(decimal_field)
    if type(raw_hex) is not str or type(raw_decimal) is not str:
        _fail("W2C technical mark encodings are malformed")
    try:
        decoded = float.fromhex(raw_hex)
    except (ValueError, OverflowError) as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C technical binary64 hex is malformed"
        ) from exc
    expected = _binary64_mark(decoded, field="stored technical end_close")
    if expected["end_close_binary64_hex"] != raw_hex or expected["end_close_exact_decimal"] != raw_decimal:
        _fail("W2C technical mark encodings do not bind one exact binary64")
    return decoded


def _validate_decision_state_projection(
    value: object, *, feature_snapshot_id: str, feature_content_sha256: str
) -> dict[str, Any]:
    fields = {
        "schema", "source_feature_id", "source_transform_version",
        "feature_snapshot_id",
        "feature_content_sha256", "growth_score", "inflation_score", "quad",
        "liquidity_overlay", "cycle_tag", "missingness_policy",
    }
    clean = _freeze_json_native(value, label="W2C decision-state projection")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C decision-state projection fields are not canonical")
    if (
        clean.get("schema") != DECISION_STATE_PROJECTION_SCHEMA
        or clean.get("source_feature_id") != "macro.regime_state"
        or clean.get("source_transform_version") != SOURCE_REGIME_TRANSFORM_VERSION
        or clean.get("feature_snapshot_id") != feature_snapshot_id
        or clean.get("feature_content_sha256") != feature_content_sha256
        or clean.get("missingness_policy") != "fail_closed_no_imputation"
        or clean.get("quad") not in {"Q1", "Q2", "Q3", "Q4"}
        or clean.get("liquidity_overlay")
        not in {"expanding", "neutral", "contracting"}
        or clean.get("cycle_tag") not in {"early", "mid", "late"}
    ):
        _fail("W2C decision-state projection identity/category binding drift")
    for name in ("growth_score", "inflation_score"):
        coordinate = clean.get(name)
        if type(coordinate) is not dict or set(coordinate) != {
            "source_binary64_hex", "source_exact_decimal", "q18"
        }:
            _fail(f"W2C {name} coordinate fields are not canonical")
        try:
            decoded = float.fromhex(coordinate["source_binary64_hex"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MarketMemoryExperienceStoreError(
                f"W2C {name} coordinate binary64 is malformed"
            ) from exc
        if coordinate != _signed_binary64_q18(decoded, field=name):
            _fail(f"W2C {name} coordinate does not bind one owner binary64")
    return clean


def _validate_trusted_ref(value: object, *, session: str) -> dict[str, Any]:
    fields = {
        "capture_id", "query_id", "context_id", "packet_sha256",
        "feature_snapshot_id", "feature_content_sha256", "source_session",
        "captured_at", "feature_observed_at", "source_observed_at",
        "subject_id", "instrument_id", "identity_version",
        "decision_state_projection", "decision_state_projection_reason",
        "decision_state_raw_categories",
    }
    clean = _freeze_json_native(value, label="W2C trusted reference")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C trusted capture reference fields are not canonical")
    patterns = {
        "capture_id": re.compile(r"mmcapture_[a-f0-9]{64}\Z"),
        "query_id": re.compile(r"mmquery_[a-f0-9]{64}\Z"),
        "context_id": re.compile(r"mmctx_[a-f0-9]{64}\Z"),
        "feature_snapshot_id": re.compile(r"mmsnap_[a-f0-9]{64}\Z"),
    }
    for field, pattern in patterns.items():
        if type(clean.get(field)) is not str or not pattern.fullmatch(clean[field]):
            _fail(f"W2C trusted {field} is malformed")
    for field in ("packet_sha256", "feature_content_sha256"):
        _require_digest(clean.get(field), field=f"trusted {field}")
    if clean.get("source_session") != session:
        _fail("W2C trusted capture session differs from opportunity")
    for field in ("captured_at", "feature_observed_at", "source_observed_at"):
        _parse_utc(clean.get(field), field=f"trusted {field}")
    for field in ("subject_id", "instrument_id", "identity_version"):
        if clean.get(field) != _SUBJECT[field]:
            _fail("W2C trusted capture identity differs from registration")
    raw_categories = clean.get("decision_state_raw_categories")
    if type(raw_categories) is not dict or set(raw_categories) != {
        "quad", "liquidity_overlay", "cycle_tag"
    }:
        _fail("W2C trusted decision-state raw categories are not canonical")
    quad = raw_categories.get("quad")
    liquidity = raw_categories.get("liquidity_overlay")
    cycle = raw_categories.get("cycle_tag")
    if (
        quad not in {"Q1", "Q2", "Q3", "Q4"}
        or liquidity not in {"expanding", "neutral", "contracting", "unknown"}
        or cycle not in {"early", "mid", "late", "unknown"}
    ):
        _fail("W2C trusted decision-state raw category vocabulary drift")
    if liquidity == "unknown" or cycle == "unknown":
        expected_reason = (
            "owner_liquidity_overlay_and_cycle_tag_unknown"
            if liquidity == "unknown" and cycle == "unknown"
            else "owner_liquidity_overlay_unknown"
            if liquidity == "unknown"
            else "owner_cycle_tag_unknown"
        )
        if (
            clean.get("decision_state_projection") is not None
            or clean.get("decision_state_projection_reason") != expected_reason
        ):
            _fail("W2C trusted unknown category was imputed into a projection")
    else:
        clean["decision_state_projection"] = _validate_decision_state_projection(
            clean.get("decision_state_projection"),
            feature_snapshot_id=str(clean["feature_snapshot_id"]),
            feature_content_sha256=str(clean["feature_content_sha256"]),
        )
        if (
            clean["decision_state_projection"]["quad"] != quad
            or clean["decision_state_projection"]["liquidity_overlay"] != liquidity
            or clean["decision_state_projection"]["cycle_tag"] != cycle
            or clean.get("decision_state_projection_reason")
            != "exact_owner_macro_regime_transform"
        ):
            _fail("W2C trusted decision-state projection differs from raw categories")
    return clean


def _validate_technical_ref(value: object, *, session: str) -> dict[str, Any]:
    fields = {
        "capture_id", "revision_id", "source_observation_id", "snapshot_id",
        "source_session", "first_observed_at", "spy_parquet_sha256",
        "end_close_binary64_hex", "end_close_exact_decimal", "subject",
        "calendar", "price_basis",
    }
    clean = _freeze_json_native(value, label="W2C technical reference")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C technical capture reference fields are not canonical")
    patterns = {
        "capture_id": re.compile(r"mmactualcapture_[a-f0-9]{64}\Z"),
        "revision_id": re.compile(r"mmtechrev_[a-f0-9]{64}\Z"),
        "source_observation_id": re.compile(r"mmtechsrc_[a-f0-9]{64}\Z"),
        "snapshot_id": re.compile(r"mmtechsnap_[a-f0-9]{64}\Z"),
    }
    for field, pattern in patterns.items():
        if type(clean.get(field)) is not str or not pattern.fullmatch(clean[field]):
            _fail(f"W2C technical {field} is malformed")
    if clean.get("source_session") != session:
        _fail("W2C technical capture session differs from opportunity")
    _parse_utc(clean.get("first_observed_at"), field="technical first_observed_at")
    _require_digest(clean.get("spy_parquet_sha256"), field="technical SPY parquet digest")
    _validate_exact_mark_fields(clean)
    if clean.get("subject") != _SUBJECT or clean.get("calendar") != _CALENDAR:
        _fail("W2C technical ARCX instrument or XNYS calendar binding drift")
    if clean.get("price_basis") != {
        "raw_unadjusted": True,
        "split_adjusted": False,
        "dividend_adjusted": False,
        "economic_return": False,
    }:
        _fail("W2C technical capture price-basis receipt drift")
    return clean


def _validate_source_pins(value: object, *, session: str) -> dict[str, Any]:
    fields = {
        "pin_observed_at", "selection", "subject", "calendar",
        "trusted_generation", "technical_generation", "trusted_capture",
        "technical_capture",
    }
    clean = _freeze_json_native(value, label="W2C source pins")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C source pin fields are not canonical")
    _parse_utc(clean.get("pin_observed_at"), field="source pin observed_at")
    if (
        clean.get("selection") != "owner_observed_revision_chain.v1"
        or clean.get("subject") != _SUBJECT
        or clean.get("calendar") != _CALENDAR
    ):
        _fail("W2C source pin policy/identity binding drift")
    clean["trusted_generation"] = _validate_generation_ref(
        clean.get("trusted_generation"), technical=False
    )
    clean["technical_generation"] = _validate_generation_ref(
        clean.get("technical_generation"), technical=True
    )
    if clean.get("trusted_capture") is not None:
        clean["trusted_capture"] = _validate_trusted_ref(
            clean["trusted_capture"], session=session
        )
    if clean.get("technical_capture") is not None:
        clean["technical_capture"] = _validate_technical_ref(
            clean["technical_capture"], session=session
        )
    return clean


def _new_prepared(
    registration: Registration,
    *,
    session: date,
    sandwich: SourceSandwich,
    writer_commit: str,
) -> dict[str, Any]:
    opened, deadline = _window(session)
    if not sandwich.stable:
        _fail("W2C cannot prepare an unauthenticated owner-pair sample")
    observed = _parse_utc(sandwich.sampled_at, field="prepared actual cutoff")
    if not opened <= observed <= deadline:
        raise MarketMemoryExperienceAccrualError(
            "W2C opportunity pin did not land inside its registered window"
        )
    trusted_capture = (
        sandwich.source_pins.get("trusted_capture")
        if isinstance(sandwich.source_pins, Mapping)
        else None
    )
    projection = (
        copy.deepcopy(trusted_capture["decision_state_projection"])
        if isinstance(trusted_capture, Mapping)
        else None
    )
    projection_reason = (
        str(trusted_capture["decision_state_projection_reason"])
        if isinstance(trusted_capture, Mapping)
        else "trusted_macro_unavailable_or_ambiguous"
    )
    value: dict[str, Any] = {
        "schema": PREPARED_SCHEMA,
        "prepared_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "session": session.isoformat(),
        "target_session": _target_session(session).isoformat(),
        "cutoff": {
            "window_opens_at": _format_utc(opened),
            "deadline_at": _format_utc(deadline),
            "actual_cutoff_at": sandwich.sampled_at,
            "first_owner_observed_at": sandwich.sampled_at,
            "reconciled_at": None,
            "clock_model": "session_ordinal_only_no_fabricated_market_close_timestamp",
        },
        "disposition": sandwich.disposition,
        "reason": sandwich.reason,
        "source_pins": copy.deepcopy(sandwich.source_pins),
        "decision_state_projection": projection,
        "decision_state_projection_reason": projection_reason,
        "writer_commit": writer_commit,
        "evidence_policy": copy.deepcopy(_OPPORTUNITY_EVIDENCE_POLICY),
        "claims": _opportunity_claims(source_pins_authenticated=True),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["prepared_id"] = _content_id("mmspyexpprep_", value, field="prepared_id")
    return _validate_prepared(value, registration=registration)


def _validate_prepared(
    value: Mapping[str, Any], *, registration: Registration
) -> dict[str, Any]:
    fields = {
        "schema", "prepared_id", "registration_id", "registration_sha256",
        "session", "target_session", "cutoff", "disposition", "reason",
        "source_pins", "decision_state_projection",
        "decision_state_projection_reason", "writer_commit",
        "evidence_policy", "authority", "claims",
    }
    clean = _freeze_json_native(value, label="W2C prepared opportunity")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C prepared opportunity fields are not canonical")
    if (
        clean.get("schema") != PREPARED_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("evidence_policy") != _OPPORTUNITY_EVIDENCE_POLICY
        or clean.get("claims")
        != _opportunity_claims(source_pins_authenticated=True)
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C prepared opportunity binding drift")
    session = _parse_session(clean.get("session"), field="prepared session")
    if session not in nyse_calendar.sessions_between(ACTIVATION_SESSION, SUNSET_SESSION):
        _fail("W2C prepared session is outside the frozen pilot")
    if clean.get("target_session") != _target_session(session).isoformat():
        _fail("W2C prepared target session is not the registered +5 ordinal")
    cutoff = clean.get("cutoff")
    cutoff_fields = {
        "window_opens_at", "deadline_at", "actual_cutoff_at",
        "first_owner_observed_at", "reconciled_at", "clock_model",
    }
    if not isinstance(cutoff, Mapping) or set(cutoff) != cutoff_fields:
        _fail("W2C prepared cutoff fields are not canonical")
    opened, deadline = _window(session)
    actual = _parse_utc(cutoff.get("actual_cutoff_at"), field="prepared actual cutoff")
    if (
        cutoff.get("window_opens_at") != _format_utc(opened)
        or cutoff.get("deadline_at") != _format_utc(deadline)
        or cutoff.get("first_owner_observed_at") != cutoff.get("actual_cutoff_at")
        or cutoff.get("reconciled_at") is not None
        or cutoff.get("clock_model")
        != "session_ordinal_only_no_fabricated_market_close_timestamp"
        or not opened <= actual <= deadline
    ):
        _fail("W2C prepared cutoff does not match the registered window")
    disposition = clean.get("disposition")
    reason = clean.get("reason")
    allowed_abstentions = {
        "trusted_macro_session_absent", "technical_session_absent",
        "trusted_macro_and_technical_session_absent", "owner_capture_clock_tie",
    }
    if disposition == "admitted":
        if reason != "exact_same_session_owner_pins" or clean.get("source_pins") is None:
            _fail("W2C admitted preparation lacks its exact owner pins")
    elif disposition == "abstained":
        if reason not in allowed_abstentions:
            _fail("W2C abstention reason is not registered")
    else:
        _fail("W2C prepared opportunity must be admitted or abstained")
    if clean.get("source_pins") is not None:
        pins = _validate_source_pins(clean["source_pins"], session=session.isoformat())
        if pins["pin_observed_at"] != cutoff["actual_cutoff_at"]:
            _fail("W2C source pin clock differs from prepared cutoff")
        trusted_capture = pins["trusted_capture"]
        technical_capture = pins["technical_capture"]
        if disposition == "admitted" and (trusted_capture is None or technical_capture is None):
            _fail("W2C admitted preparation has incomplete owner captures")
        clean["source_pins"] = pins
    else:
        _fail("W2C stable preparation must bind both owner generations")
    trusted_capture = clean["source_pins"]["trusted_capture"]
    expected_projection = (
        trusted_capture["decision_state_projection"]
        if trusted_capture is not None else None
    )
    expected_projection_reason = (
        trusted_capture["decision_state_projection_reason"]
        if trusted_capture is not None
        else "trusted_macro_unavailable_or_ambiguous"
    )
    if (
        clean.get("decision_state_projection") != expected_projection
        or clean.get("decision_state_projection_reason")
        != expected_projection_reason
    ):
        _fail("W2C prepared decision-state projection binding drift")
    _require_commit(clean.get("writer_commit"))
    prepared_id = clean.get("prepared_id")
    if type(prepared_id) is not str or not _PREPARED_ID.fullmatch(prepared_id):
        _fail("W2C prepared ID is malformed")
    if _content_id("mmspyexpprep_", clean, field="prepared_id") != prepared_id:
        _fail("W2C prepared ID does not bind its content")
    return clean


def _seal_prepared(
    root: Path,
    *,
    registration: Registration,
    prepared: Mapping[str, Any],
    clock: Callable[[], datetime],
) -> dict[str, Any] | None:
    body = _canonical_bytes(prepared)
    object_path = _safe_path(root, "prepared_objects", f"{prepared['prepared_id']}.json")
    _write_create_once(
        object_path, body, limit=_MAX_PREPARED_BYTES, label="W2C prepared object"
    )
    durable = _sample_clock(clock)
    actual = _parse_utc(prepared["cutoff"]["actual_cutoff_at"], field="prepared cutoff")
    deadline = _parse_utc(prepared["cutoff"]["deadline_at"], field="prepared deadline")
    if durable < actual:
        _fail("W2C writer clock moved backward during prepared durability proof")
    if durable > deadline:
        # The object is only a staging body until its durable pre-deadline seal
        # exists.  A late durability sample cannot create a resumable fact.
        try:
            object_path.unlink()
        except FileNotFoundError:  # pragma: no cover - just published above
            pass
        _fsync_directory(object_path.parent)
        return None
    seal = {
        "schema": PREPARED_SEAL_SCHEMA,
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "session": prepared["session"],
        "prepared_id": prepared["prepared_id"],
        "prepared_sha256": _digest(body),
        "prepared_bytes": len(body),
        "durable_observed_at": _format_utc(durable),
        "writer_commit": prepared["writer_commit"],
        "claims": copy.deepcopy(_EXTERNAL_CLOCK_CLAIM),
        "authority": dict(market_memory.AUTHORITY),
    }
    _validate_prepared_seal(seal, registration=registration, prepared=prepared, body=body)
    _write_create_once(
        _safe_path(root, "prepared_sessions", f"{prepared['session']}.json"),
        _canonical_bytes(seal), limit=_MAX_PREPARED_BYTES,
        label="W2C prepared session seal",
    )
    return seal


def _validate_prepared_seal(
    value: Mapping[str, Any], *, registration: Registration,
    prepared: Mapping[str, Any], body: bytes,
) -> dict[str, Any]:
    fields = {
        "schema", "registration_id", "registration_sha256", "session",
        "prepared_id", "prepared_sha256", "prepared_bytes",
        "durable_observed_at", "writer_commit", "claims", "authority",
    }
    clean = _freeze_json_native(value, label="W2C prepared seal")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C prepared seal fields are not canonical")
    if (
        clean.get("schema") != PREPARED_SEAL_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("session") != prepared["session"]
        or clean.get("prepared_id") != prepared["prepared_id"]
        or clean.get("prepared_sha256") != _digest(body)
        or clean.get("prepared_bytes") != len(body)
        or clean.get("writer_commit") != prepared["writer_commit"]
        or clean.get("claims") != _EXTERNAL_CLOCK_CLAIM
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C prepared seal binding drift")
    durable = _parse_utc(clean.get("durable_observed_at"), field="prepared durable_observed_at")
    actual = _parse_utc(prepared["cutoff"]["actual_cutoff_at"], field="prepared cutoff")
    deadline = _parse_utc(prepared["cutoff"]["deadline_at"], field="prepared deadline")
    if not actual <= durable <= deadline:
        _fail("W2C prepared seal was not durably observed before deadline")
    _require_commit(clean.get("writer_commit"))
    return clean


def _load_prepared_seal(
    root: Path, *, registration: Registration, session: date
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    seal_path = _safe_path(root, "prepared_sessions", f"{session.isoformat()}.json")
    seal_candidate: tuple[dict[str, Any], bytes] | None
    if seal_path.exists() or seal_path.is_symlink():
        seal_candidate = _read_json_path(
            seal_path, limit=_MAX_PREPARED_BYTES,
            label="W2C prepared session seal",
        )
    else:
        seal_candidate = _read_one_pending_create(
            seal_path, limit=_MAX_PREPARED_BYTES,
            label="W2C prepared session seal",
        )
    if seal_candidate is None:
        return None
    seal_raw, _seal_body = seal_candidate
    prepared_id = seal_raw.get("prepared_id")
    if type(prepared_id) is not str or not _PREPARED_ID.fullmatch(prepared_id):
        _fail("W2C prepared session seal has a malformed object ID")
    prepared_path = _safe_path(
        root, "prepared_objects", f"{prepared_id}.json"
    )
    prepared_body_holder: list[bytes] = []

    def validate_prepared(
        raw: dict[str, Any], body: bytes
    ) -> dict[str, Any]:
        clean = _validate_prepared(raw, registration=registration)
        if clean["prepared_id"] != prepared_id:
            _fail("W2C prepared object path differs from its content ID")
        prepared_body_holder[:] = [body]
        return clean

    prepared = _recover_immutable_json(
        prepared_path,
        limit=_MAX_PREPARED_BYTES,
        label="W2C prepared object",
        validator=validate_prepared,
    )
    if prepared is None:
        _fail("W2C prepared session seal lacks its immutable object")

    def validate_seal(raw: dict[str, Any], _body: bytes) -> dict[str, Any]:
        return _validate_prepared_seal(
            raw,
            registration=registration,
            prepared=prepared,
            body=prepared_body_holder[0],
        )

    seal = _recover_immutable_json(
        seal_path,
        limit=_MAX_PREPARED_BYTES,
        label="W2C prepared session seal",
        validator=validate_seal,
    )
    if seal is None:  # pragma: no cover - candidate above proves publication
        _fail("W2C prepared session seal disappeared during recovery")
    if prepared["session"] != session.isoformat():
        _fail("W2C prepared seal belongs to another session")
    return seal, prepared


def _cleanup_unsealed_prepared_staging(
    root: Path, *, registration: Registration
) -> None:
    """Remove validated staging objects that never gained a session seal."""

    seals_directory = _safe_path(root, "prepared_sessions")
    referenced_ids: set[str] = set()
    if seals_directory.exists():
        for item in seals_directory.iterdir():
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.json", item.name) or re.fullmatch(
                r"\.[0-9]{4}-[0-9]{2}-[0-9]{2}\.json\.[a-f0-9]{64}\.pending",
                item.name,
            ):
                raw, _ = _read_json_path(
                    item,
                    limit=_MAX_PREPARED_BYTES,
                    label="W2C prepared seal staging inventory",
                )
                prepared_id = raw.get("prepared_id")
                if type(prepared_id) is not str or not _PREPARED_ID.fullmatch(
                    prepared_id
                ):
                    _fail("W2C prepared seal staging has a malformed object ID")
                referenced_ids.add(prepared_id)
            else:
                _fail("W2C prepared seal staging inventory is noncanonical")
    objects_directory = _safe_path(root, "prepared_objects")
    if not objects_directory.exists():
        return
    removed = False
    for item in list(objects_directory.iterdir()):
        final_match = re.fullmatch(
            r"(mmspyexpprep_[a-f0-9]{64})\.json", item.name
        )
        pending_match = re.fullmatch(
            r"\.(mmspyexpprep_[a-f0-9]{64})\.json\.[a-f0-9]{64}\.pending",
            item.name,
        )
        if final_match is None and pending_match is None:
            _fail("W2C prepared object staging inventory is noncanonical")
        prepared_id = (
            final_match.group(1) if final_match is not None else pending_match.group(1)
        )
        if prepared_id in referenced_ids:
            continue
        raw, body = _read_json_path(
            item,
            limit=_MAX_PREPARED_BYTES,
            label="W2C unsealed prepared staging object",
        )
        prepared = _validate_prepared(raw, registration=registration)
        if (
            prepared["prepared_id"] != prepared_id
            or (pending_match is not None and item != _pending_create_path(
                _safe_path(root, "prepared_objects", f"{prepared_id}.json"), body
            ))
        ):
            _fail("W2C unsealed prepared staging path differs from its bytes")
        opportunity_path = _opportunity_path(
            root, date.fromisoformat(prepared["session"])
        )
        if (
            opportunity_path.exists()
            or opportunity_path.is_symlink()
            or _pending_create_paths(opportunity_path)
        ):
            _fail("W2C opportunity exists without its durable prepared seal")
        item.unlink()
        removed = True
    if removed:
        _fsync_directory(objects_directory)


def _capture_bearing_admission_exists_without_recovery(
    root: Path, *, registration: Registration
) -> bool:
    """Read-only proof that the one-time activation capacity recheck ran.

    A missed opportunity contains no owner captures and therefore cannot waive
    the recheck for a later stable pair.  Pending-only objects are likewise not
    durable admissions: accepting them here could both bypass the capacity gate
    and make a NO-GO invocation mutate state while recovering the publication.
    """

    sessions = nyse_calendar.sessions_between(
        ACTIVATION_SESSION, SUNSET_SESSION
    )
    for session in sessions:
        opportunity_path = _opportunity_path(root, session)
        if opportunity_path.exists() or opportunity_path.is_symlink():
            raw, _body = _read_json_path(
                opportunity_path,
                limit=_MAX_OPPORTUNITY_BYTES,
                label="W2C capacity-gate opportunity",
            )
            opportunity = validate_opportunity(raw, registration=registration)
            if opportunity["session"] != session.isoformat():
                _fail("W2C capacity-gate opportunity belongs to another session")
            if opportunity["disposition"] != "missed":
                return True

        seal_path = _safe_path(
            root, "prepared_sessions", f"{session.isoformat()}.json"
        )
        final_seal = (
            _read_json_path(
                seal_path,
                limit=_MAX_PREPARED_BYTES,
                label="W2C capacity-gate prepared seal",
            )
            if seal_path.exists() or seal_path.is_symlink()
            else None
        )
        pending_seal = _read_one_pending_create(
            seal_path,
            limit=_MAX_PREPARED_BYTES,
            label="W2C capacity-gate prepared seal",
        )
        if final_seal is not None and pending_seal is not None and (
            final_seal[1] != pending_seal[1]
        ):
            _fail("W2C capacity-gate final and pending seals differ")
        seal_candidate = final_seal or pending_seal
        if seal_candidate is None:
            continue
        seal_raw, _seal_body = seal_candidate
        prepared_id = seal_raw.get("prepared_id")
        if type(prepared_id) is not str or not _PREPARED_ID.fullmatch(
            prepared_id
        ):
            _fail("W2C capacity-gate prepared seal has a malformed object ID")
        prepared_raw, prepared_body = _read_json_path(
            _safe_path(root, "prepared_objects", f"{prepared_id}.json"),
            limit=_MAX_PREPARED_BYTES,
            label="W2C capacity-gate prepared object",
        )
        prepared = _validate_prepared(
            prepared_raw, registration=registration
        )
        seal = _validate_prepared_seal(
            seal_raw,
            registration=registration,
            prepared=prepared,
            body=prepared_body,
        )
        if (
            prepared["session"] != session.isoformat()
            or seal["session"] != session.isoformat()
        ):
            _fail("W2C capacity-gate prepared seal belongs to another session")
        return True
    return False


def _opportunity_from_prepared(
    registration: Registration,
    *,
    seal: Mapping[str, Any],
    prepared: Mapping[str, Any],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": OPPORTUNITY_SCHEMA,
        "opportunity_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "session": prepared["session"],
        "target_session": prepared["target_session"],
        "cutoff": copy.deepcopy(prepared["cutoff"]),
        "disposition": prepared["disposition"],
        "reason": prepared["reason"],
        "source_pins": copy.deepcopy(prepared["source_pins"]),
        "decision_state_projection": copy.deepcopy(
            prepared["decision_state_projection"]
        ),
        "decision_state_projection_reason": prepared[
            "decision_state_projection_reason"
        ],
        "sealed_at": seal["durable_observed_at"],
        "writer_commit": prepared["writer_commit"],
        "evidence_policy": copy.deepcopy(_OPPORTUNITY_EVIDENCE_POLICY),
        "claims": copy.deepcopy(prepared["claims"]),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["opportunity_id"] = _content_id(
        "mmspyexpopp_", value, field="opportunity_id"
    )
    return validate_opportunity(value, registration=registration)


def _missed_opportunity(
    registration: Registration,
    *,
    session: date,
    reconciled_at: datetime,
    writer_commit: str,
    reason: str = "not_sealed_by_deadline",
) -> dict[str, Any]:
    opened, deadline = _window(session)
    if reconciled_at <= deadline:
        raise MarketMemoryExperienceAccrualError(
            "W2C missed reconciliation cannot precede the admission deadline"
        )
    timestamp = _format_utc(reconciled_at)
    value: dict[str, Any] = {
        "schema": OPPORTUNITY_SCHEMA,
        "opportunity_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "session": session.isoformat(),
        "target_session": _target_session(session).isoformat(),
        "cutoff": {
            "window_opens_at": _format_utc(opened),
            "deadline_at": _format_utc(deadline),
            "actual_cutoff_at": None,
            "first_owner_observed_at": None,
            "reconciled_at": timestamp,
            "clock_model": "session_ordinal_only_no_fabricated_market_close_timestamp",
        },
        "disposition": "missed",
        "reason": reason,
        "source_pins": None,
        "decision_state_projection": None,
        "decision_state_projection_reason": "missed_without_authenticated_owner_pair",
        "sealed_at": timestamp,
        "writer_commit": writer_commit,
        "evidence_policy": copy.deepcopy(_OPPORTUNITY_EVIDENCE_POLICY),
        "claims": _opportunity_claims(source_pins_authenticated=False),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["opportunity_id"] = _content_id(
        "mmspyexpopp_", value, field="opportunity_id"
    )
    return validate_opportunity(value, registration=registration)


def validate_opportunity(
    value: Mapping[str, Any], *, registration: Registration
) -> dict[str, Any]:
    registration = _require_registration_capability(registration)
    return _validate_opportunity_frozen(value, registration=registration)


def _validate_opportunity_frozen(
    value: Mapping[str, Any], *, registration: Registration
) -> dict[str, Any]:
    fields = {
        "schema", "opportunity_id", "registration_id", "registration_sha256",
        "session", "target_session", "cutoff", "disposition", "reason",
        "source_pins", "decision_state_projection",
        "decision_state_projection_reason", "sealed_at", "writer_commit",
        "evidence_policy", "authority", "claims",
    }
    clean = _freeze_json_native(value, label="W2C opportunity")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C opportunity fields are not canonical")
    _require_value_bound(
        clean, limit=_MAX_OPPORTUNITY_BYTES, label="W2C opportunity"
    )
    if (
        clean.get("schema") != OPPORTUNITY_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("evidence_policy") != _OPPORTUNITY_EVIDENCE_POLICY
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C opportunity registration/evidence binding drift")
    session = _parse_session(clean.get("session"), field="opportunity session")
    pilot_sessions = nyse_calendar.sessions_between(ACTIVATION_SESSION, SUNSET_SESSION)
    if session not in pilot_sessions:
        _fail("W2C opportunity is outside the frozen 126-session pilot")
    if clean.get("target_session") != _target_session(session).isoformat():
        _fail("W2C opportunity target is not exactly +5 XNYS sessions")
    cutoff = clean.get("cutoff")
    cutoff_fields = {
        "window_opens_at", "deadline_at", "actual_cutoff_at",
        "first_owner_observed_at", "reconciled_at", "clock_model",
    }
    if not isinstance(cutoff, Mapping) or set(cutoff) != cutoff_fields:
        _fail("W2C opportunity cutoff fields are not canonical")
    opened, deadline = _window(session)
    if (
        cutoff.get("window_opens_at") != _format_utc(opened)
        or cutoff.get("deadline_at") != _format_utc(deadline)
        or cutoff.get("clock_model")
        != "session_ordinal_only_no_fabricated_market_close_timestamp"
    ):
        _fail("W2C opportunity window differs from registration")
    disposition = clean.get("disposition")
    reason = clean.get("reason")
    if disposition == "missed":
        if (
            reason not in {
                "not_sealed_by_deadline",
                "owner_pair_not_stable_by_deadline",
                "owner_unavailable_by_deadline",
                "owner_integrity_failure_by_deadline",
                "owner_pin_cap_exceeded_by_deadline",
            }
            or clean.get("source_pins") is not None
            or clean.get("decision_state_projection") is not None
            or clean.get("decision_state_projection_reason")
            != "missed_without_authenticated_owner_pair"
            or cutoff.get("actual_cutoff_at") is not None
            or cutoff.get("first_owner_observed_at") is not None
            or cutoff.get("reconciled_at") is None
            or clean.get("claims")
            != _opportunity_claims(source_pins_authenticated=False)
        ):
            _fail("W2C missed opportunity conditional fields disagree")
        reconciled = _parse_utc(cutoff["reconciled_at"], field="missed reconciled_at")
        if reconciled <= deadline or clean.get("sealed_at") != cutoff["reconciled_at"]:
            _fail("W2C missed opportunity was not reconciled after deadline")
    elif disposition in {"admitted", "abstained"}:
        if (
            cutoff.get("actual_cutoff_at") is None
            or cutoff.get("first_owner_observed_at") != cutoff.get("actual_cutoff_at")
            or cutoff.get("reconciled_at") is not None
            or clean.get("claims")
            != _opportunity_claims(source_pins_authenticated=True)
        ):
            _fail("W2C timely opportunity cutoff conditional fields disagree")
        actual = _parse_utc(cutoff["actual_cutoff_at"], field="opportunity actual cutoff")
        sealed = _parse_utc(clean.get("sealed_at"), field="opportunity sealed_at")
        if not opened <= actual <= sealed <= deadline:
            _fail("W2C timely opportunity lacks a durable pre-deadline seal")
        if clean.get("source_pins") is not None:
            pins = _validate_source_pins(clean["source_pins"], session=session.isoformat())
            if pins["pin_observed_at"] != cutoff["actual_cutoff_at"]:
                _fail("W2C opportunity source pin clock differs from cutoff")
            clean["source_pins"] = pins
        trusted_capture = (
            clean["source_pins"]["trusted_capture"]
            if clean.get("source_pins") is not None else None
        )
        expected_projection = (
            trusted_capture["decision_state_projection"]
            if trusted_capture is not None else None
        )
        expected_projection_reason = (
            trusted_capture["decision_state_projection_reason"]
            if trusted_capture is not None
            else "trusted_macro_unavailable_or_ambiguous"
        )
        if (
            clean.get("decision_state_projection") != expected_projection
            or clean.get("decision_state_projection_reason")
            != expected_projection_reason
        ):
            _fail("W2C timely decision-state projection binding drift")
        if disposition == "admitted":
            if (
                reason != "exact_same_session_owner_pins"
                or clean.get("source_pins") is None
                or clean["source_pins"]["trusted_capture"] is None
                or clean["source_pins"]["technical_capture"] is None
            ):
                _fail("W2C admitted opportunity lacks exact same-session pins")
        else:
            if reason not in {
                "trusted_macro_session_absent", "technical_session_absent",
                "trusted_macro_and_technical_session_absent",
                "owner_capture_clock_tie",
            }:
                _fail("W2C abstention reason is not registered")
            if clean.get("source_pins") is None:
                _fail("W2C stable abstention must bind both owner generations")
    else:
        _fail("W2C opportunity disposition is not canonical")
    _parse_utc(clean.get("sealed_at"), field="opportunity sealed_at")
    _require_commit(clean.get("writer_commit"))
    opportunity_id = clean.get("opportunity_id")
    if type(opportunity_id) is not str or not _OPPORTUNITY_ID.fullmatch(opportunity_id):
        _fail("W2C opportunity ID is malformed")
    if _content_id("mmspyexpopp_", clean, field="opportunity_id") != opportunity_id:
        _fail("W2C opportunity ID does not bind its content")
    return clean


def _opportunity_path(root: Path, session: date) -> Path:
    return _safe_path(root, "opportunities", f"{session.isoformat()}.json")


def _load_opportunity(
    root: Path, *, registration: Registration, session: date
) -> dict[str, Any] | None:
    def validate(raw: dict[str, Any], _body: bytes) -> dict[str, Any]:
        clean = validate_opportunity(raw, registration=registration)
        if clean["session"] != session.isoformat():
            _fail("W2C pending opportunity belongs to another session")
        return clean

    return _recover_immutable_json(
        _opportunity_path(root, session),
        limit=_MAX_OPPORTUNITY_BYTES,
        label="W2C opportunity",
        validator=validate,
    )


def _write_opportunity(root: Path, opportunity: Mapping[str, Any]) -> None:
    session = date.fromisoformat(str(opportunity["session"]))
    _write_create_once(
        _opportunity_path(root, session),
        _canonical_bytes(opportunity),
        limit=_MAX_OPPORTUNITY_BYTES,
        label="W2C terminal opportunity",
    )


def _observe_target_sources(
    *,
    technical_root: str | Path,
    target_session: date,
    clock: Callable[[], datetime],
) -> _TargetObservation:
    before = technical_store.pin_technical_actual_output_generation(
        technical_root, maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    candidates = _technical_candidates(
        technical_root, before, session=target_session
    )
    observed = _sample_clock(clock)
    observed_at = _format_utc(observed)
    after = technical_store.pin_technical_actual_output_generation(
        technical_root, maximum_capture_count=MAX_OWNER_GENERATION_CAPTURES
    )
    if not _same_generation(before, after):
        return _TargetObservation(
            pin_observed_at=observed_at,
            stable=False,
            generation_pin=None,
            candidates=(),
            clock_tie=False,
            generation_capture_ordinals={},
            ancestry_generation_ids=(),
        )
    _validate_candidate_clocks([], candidates, cutoff=observed)
    generation_pin = {
        **_generation_ref(before, technical=True),
        "pin_observed_at": observed_at,
        "selection": "owner_observed_revision_chain.v1",
        "subject": copy.deepcopy(_SUBJECT),
        "calendar": copy.deepcopy(_CALENDAR),
    }
    return _TargetObservation(
        pin_observed_at=observed_at,
        stable=True,
        generation_pin=generation_pin,
        candidates=tuple(candidates),
        clock_tie=_owner_clock_tie(
            candidates, clock_field="first_observed_at"
        ),
        generation_capture_ordinals={
            entry.capture_id: index for index, entry in enumerate(before.captures)
        },
        ancestry_generation_ids=tuple(
            getattr(before, "ancestry_generation_ids", ())
        ),
    )


def _target_observation_from_run(
    view: _RunOwnerView, *, target_session: date
) -> _TargetObservation:
    if not view.stable or view.pins is None:
        return _TargetObservation(
            pin_observed_at=view.pin_observed_at,
            stable=False,
            generation_pin=None,
            candidates=(),
            clock_tie=False,
            generation_capture_ordinals={},
            ancestry_generation_ids=(),
            failure_reason=view.failure_reason,
        )
    candidates = view.technical_candidates_by_session.get(
        target_session.isoformat(), ()
    )
    cutoff = _parse_utc(view.pin_observed_at, field="run target pin")
    _validate_candidate_clocks([], list(candidates), cutoff=cutoff)
    generation_pin = {
        **_generation_ref(view.pins.technical, technical=True),
        "pin_observed_at": view.pin_observed_at,
        "selection": "owner_observed_revision_chain.v1",
        "subject": copy.deepcopy(_SUBJECT),
        "calendar": copy.deepcopy(_CALENDAR),
    }
    return _TargetObservation(
        pin_observed_at=view.pin_observed_at,
        stable=True,
        generation_pin=generation_pin,
        candidates=tuple(candidates),
        clock_tie=_owner_clock_tie(
            list(candidates), clock_field="first_observed_at"
        ),
        generation_capture_ordinals={
            entry.capture_id: index
            for index, entry in enumerate(view.pins.technical.captures)
        },
        ancestry_generation_ids=tuple(
            getattr(view.pins.technical, "ancestry_generation_ids", ())
        ),
    )


def _validate_target_generation_pin(value: object) -> dict[str, Any]:
    fields = {
        "profile", "store_id", "generation_id", "generation_sha256",
        "capture_count", "pin_observed_at", "selection", "subject", "calendar",
    }
    clean = _freeze_json_native(value, label="W2C target generation pin")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C target generation pin fields are not canonical")
    generation = _validate_generation_ref(
        {key: clean[key] for key in (
            "profile", "store_id", "generation_id", "generation_sha256", "capture_count"
        )},
        technical=True,
    )
    if (
        clean.get("selection") != "owner_observed_revision_chain.v1"
        or clean.get("subject") != _SUBJECT
        or clean.get("calendar") != _CALENDAR
    ):
        _fail("W2C target generation selection/identity binding drift")
    _parse_utc(clean.get("pin_observed_at"), field="target generation pin_observed_at")
    return {**generation, **{key: clean[key] for key in (
        "pin_observed_at", "selection", "subject", "calendar"
    )}}


def _mark_from_technical(reference: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "session": reference["source_session"],
        "capture_id": reference["capture_id"],
        "snapshot_id": reference["snapshot_id"],
        "end_close_binary64_hex": reference["end_close_binary64_hex"],
        "end_close_exact_decimal": reference["end_close_exact_decimal"],
    }


def _validate_mark(value: object, *, expected_session: str) -> tuple[dict[str, Any], float]:
    fields = {
        "session", "capture_id", "snapshot_id", "end_close_binary64_hex",
        "end_close_exact_decimal",
    }
    clean = _freeze_json_native(value, label="W2C outcome mark")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C outcome mark fields are not canonical")
    if clean.get("session") != expected_session:
        _fail("W2C outcome mark session drift")
    if type(clean.get("capture_id")) is not str or not re.fullmatch(
        r"mmactualcapture_[a-f0-9]{64}", clean["capture_id"]
    ):
        _fail("W2C outcome mark capture ID is malformed")
    if type(clean.get("snapshot_id")) is not str or not re.fullmatch(
        r"mmtechsnap_[a-f0-9]{64}", clean["snapshot_id"]
    ):
        _fail("W2C outcome mark snapshot ID is malformed")
    decoded = _validate_exact_mark_fields(clean)
    return clean, decoded


def _measurement(target: float, anchor: float) -> dict[str, Any]:
    return {
        "target": "spy.raw_unadjusted_daily_aggregate_close_ratio",
        "formula": "target_capture.feature.state.end_close/sealed_anchor_capture.feature.state.end_close",
        "input_encoding": "ieee754_binary64_exact_hex_and_integer_ratio",
        "exact_decimal_encoding": "python_decimal_from_float_exact",
        "close_ratio_q18": _q18_ratio(target, anchor),
        "quantization": "q18",
        "rounding": "exact_integer_ratio_half_even",
        "price_basis": "raw_unadjusted_daily_aggregate_close",
        "economic_return": False,
        "corporate_action_adjusted": False,
    }


def _validate_measurement(
    value: object, *, target: float, anchor: float
) -> dict[str, Any]:
    expected = _measurement(target, anchor)
    if value != expected:
        _fail("W2C outcome measurement is not the exact raw close ratio")
    return copy.deepcopy(expected)


def _new_outcome_revision(
    registration: Registration,
    *,
    opportunity: Mapping[str, Any],
    revision_number: int,
    previous_outcome_revision_id: str | None,
    previous: Mapping[str, Any] | None,
    status: str,
    revision_kind: str,
    reason: str,
    maturity_actual_pin: str | None,
    target_generation_pin: Mapping[str, Any] | None,
    target_candidate: _TechnicalCandidate | None,
    current_generation_group: list[_TechnicalCandidate] | None,
    consumed_generation_capture_ids: list[str] | None,
    appended_at: str,
    writer_commit: str,
    history: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    target_session = date.fromisoformat(str(opportunity["target_session"]))
    opened, deadline = _window(target_session)
    anchor_ref = opportunity["source_pins"]["technical_capture"]
    anchor_mark = _mark_from_technical(anchor_ref)
    target_capture = (
        copy.deepcopy(target_candidate.reference)
        if target_candidate is not None else None
    )
    target_mark = (
        _mark_from_technical(target_candidate.reference)
        if target_candidate is not None else None
    )
    anchor_value = float.fromhex(anchor_mark["end_close_binary64_hex"])
    target_value = target_candidate.end_close if target_candidate is not None else None
    measurement = (
        _measurement(target_value, anchor_value)
        if target_value is not None else None
    )
    absence_fact = None
    if status != "observed":
        absence_fact = {
            "kind": "missing" if status == "unavailable" else "censored",
            "reason": reason,
            "observed_at": (
                str(target_generation_pin["pin_observed_at"])
                if target_generation_pin is not None
                else maturity_actual_pin or appended_at
            ),
        }
    target_generation_progress = None
    if target_generation_pin is not None:
        group = current_generation_group or []
        consumed = consumed_generation_capture_ids or []
        target_generation_progress = {
            "generation_id": target_generation_pin["generation_id"],
            "consumed_capture_ids": list(consumed),
            "current_group": [
                {
                    "capture_id": candidate.reference["capture_id"],
                    "first_observed_at": candidate.reference["first_observed_at"],
                }
                for candidate in group
            ],
        }
    value: dict[str, Any] = {
        "schema": OUTCOME_SCHEMA,
        "outcome_revision_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "opportunity_id": opportunity["opportunity_id"],
        "revision_number": revision_number,
        "previous_outcome_revision_id": previous_outcome_revision_id,
        "status": status,
        "revision_kind": revision_kind,
        "reason": reason,
        "maturity": {
            "origin_session": opportunity["session"],
            "target_session": opportunity["target_session"],
            "horizon_sessions": OUTCOME_HORIZON_SESSIONS,
            "window_opens_at": _format_utc(opened),
            "deadline_at": _format_utc(deadline),
            "clock_model": "session_ordinal_only_no_fabricated_market_close_timestamp",
        },
        "maturity_cutoff": {
            "actual_pin_observed_at": maturity_actual_pin,
            "rule": "target_session_following_calendar_day_same_registered_window",
        },
        "anchor_mark": anchor_mark,
        "target_generation_pin": (
            copy.deepcopy(dict(target_generation_pin))
            if target_generation_pin is not None else None
        ),
        "target_generation_progress": target_generation_progress,
        "target_capture": target_capture,
        "target_mark": target_mark,
        "measurement": measurement,
        "absence_fact": absence_fact,
        "appended_at": appended_at,
        "writer_commit": writer_commit,
        "evidence_policy": copy.deepcopy(_OUTCOME_EVIDENCE_POLICY),
        "claims": _outcome_claims(
            target_generation_pin_authenticated=target_generation_pin is not None
        ),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["outcome_revision_id"] = _content_id(
        "mmspyexpout_", value, field="outcome_revision_id"
    )
    return validate_outcome_revision(
        value,
        registration=registration,
        opportunity=opportunity,
        previous=previous,
        history=history,
    )


def validate_outcome_revision(
    value: Mapping[str, Any], *, registration: Registration,
    opportunity: Mapping[str, Any], previous: Mapping[str, Any] | None = None,
    history: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    registration = _require_registration_capability(registration)
    frozen_opportunity = _freeze_json_native(
        opportunity, label="W2C outcome opportunity argument"
    )
    if type(frozen_opportunity) is not dict:
        _fail("W2C outcome opportunity argument is not one exact object")
    opportunity = _validate_opportunity_frozen(
        frozen_opportunity, registration=registration
    )
    if history is not None:
        if type(history) is not list:
            _fail("W2C outcome history argument is not one exact list")
        frozen_history = _freeze_json_native(
            history, label="W2C outcome history argument"
        )
        validated_history: list[dict[str, Any]] = []
        for row in frozen_history:
            if type(row) is not dict:
                _fail("W2C outcome history contains a non-object row")
            validated_history.append(
                _validate_outcome_revision_frozen(
                    row,
                    registration=registration,
                    opportunity=opportunity,
                    previous=(validated_history[-1] if validated_history else None),
                    history=validated_history,
                )
            )
        history = validated_history
    if previous is not None:
        frozen_previous = _freeze_json_native(
            previous, label="W2C previous outcome argument"
        )
        if type(frozen_previous) is not dict:
            _fail("W2C previous outcome argument is not one exact object")
        if history is not None:
            if not history or frozen_previous != history[-1]:
                _fail("W2C previous outcome does not equal the frozen history tail")
            previous = history[-1]
        else:
            previous = _validate_outcome_revision_frozen(
                frozen_previous,
                registration=registration,
                opportunity=opportunity,
            )
    return _validate_outcome_revision_frozen(
        value,
        registration=registration,
        opportunity=opportunity,
        previous=previous,
        history=history,
    )


def _validate_outcome_revision_frozen(
    value: Mapping[str, Any], *, registration: Registration,
    opportunity: Mapping[str, Any], previous: Mapping[str, Any] | None = None,
    history: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    fields = {
        "schema", "outcome_revision_id", "registration_id", "registration_sha256",
        "opportunity_id", "revision_number", "previous_outcome_revision_id",
        "status", "revision_kind", "reason", "maturity", "maturity_cutoff",
        "anchor_mark", "target_generation_pin", "target_generation_progress",
        "target_capture", "target_mark",
        "measurement", "absence_fact", "appended_at", "writer_commit",
        "evidence_policy", "authority",
        "claims",
    }
    clean = _freeze_json_native(value, label="W2C outcome revision")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C outcome revision fields are not canonical")
    _require_value_bound(
        clean, limit=_MAX_OUTCOME_BYTES, label="W2C outcome revision"
    )
    if (
        clean.get("schema") != OUTCOME_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("opportunity_id") != opportunity["opportunity_id"]
        or clean.get("evidence_policy") != _OUTCOME_EVIDENCE_POLICY
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C outcome registration/opportunity binding drift")
    revision_number = clean.get("revision_number")
    if type(revision_number) is not int or not 1 <= revision_number <= MAX_OUTCOME_REVISIONS:
        _fail("W2C outcome revision number is outside its bound")
    if previous is None:
        if revision_number != 1 or clean.get("previous_outcome_revision_id") is not None:
            _fail("W2C initial outcome predecessor fields disagree")
    else:
        if (
            revision_number != previous["revision_number"] + 1
            or clean.get("previous_outcome_revision_id") != previous["outcome_revision_id"]
        ):
            _fail("W2C outcome does not extend the one active predecessor")
    maturity = clean.get("maturity")
    maturity_fields = {
        "origin_session", "target_session", "horizon_sessions",
        "window_opens_at", "deadline_at", "clock_model",
    }
    target_session = date.fromisoformat(str(opportunity["target_session"]))
    opened, deadline = _window(target_session)
    if (
        not isinstance(maturity, Mapping)
        or set(maturity) != maturity_fields
        or maturity.get("origin_session") != opportunity["session"]
        or maturity.get("target_session") != opportunity["target_session"]
        or maturity.get("horizon_sessions") != OUTCOME_HORIZON_SESSIONS
        or maturity.get("window_opens_at") != _format_utc(opened)
        or maturity.get("deadline_at") != _format_utc(deadline)
        or maturity.get("clock_model")
        != "session_ordinal_only_no_fabricated_market_close_timestamp"
    ):
        _fail("W2C outcome maturity is not the exact registered +5 window")
    cutoff = clean.get("maturity_cutoff")
    if (
        not isinstance(cutoff, Mapping)
        or set(cutoff) != {"actual_pin_observed_at", "rule"}
        or cutoff.get("rule")
        != "target_session_following_calendar_day_same_registered_window"
    ):
        _fail("W2C outcome maturity-cutoff fields are not canonical")
    actual_pin = cutoff.get("actual_pin_observed_at")
    if actual_pin is not None:
        pin_dt = _parse_utc(actual_pin, field="outcome maturity actual pin")
        if not opened <= pin_dt <= deadline:
            _fail("W2C initial maturity pin is outside the registered window")
    appended = _parse_utc(clean.get("appended_at"), field="outcome appended_at")
    if appended < opened:
        _fail("W2C outcome was appended before the +5 maturity window")
    anchor_ref = opportunity["source_pins"]["technical_capture"]
    anchor_mark, anchor_value = _validate_mark(
        clean.get("anchor_mark"), expected_session=opportunity["session"]
    )
    if anchor_mark != _mark_from_technical(anchor_ref):
        _fail("W2C outcome rewrites its sealed anchor reference")
    target_pin = clean.get("target_generation_pin")
    if target_pin is not None:
        target_pin = _validate_target_generation_pin(target_pin)
        clean["target_generation_pin"] = target_pin
    if clean.get("claims") != _outcome_claims(
        target_generation_pin_authenticated=target_pin is not None
    ):
        _fail("W2C outcome authentication claims disagree with its generation pin")
    progress = clean.get("target_generation_progress")
    if target_pin is None:
        if progress is not None:
            _fail("W2C outcome without a generation pin invents capture progress")
    else:
        progress_fields = {
            "generation_id", "consumed_capture_ids", "current_group"
        }
        if type(progress) is not dict or set(progress) != progress_fields:
            _fail("W2C target-generation progress fields are not canonical")
        consumed_ids = progress.get("consumed_capture_ids")
        current_group = progress.get("current_group")
        if (
            progress.get("generation_id") != target_pin["generation_id"]
            or type(consumed_ids) is not list
            or type(current_group) is not list
            or len(consumed_ids) != len(set(consumed_ids))
            or any(
                type(capture_id) is not str
                or not re.fullmatch(r"mmactualcapture_[a-f0-9]{64}", capture_id)
                for capture_id in consumed_ids
            )
        ):
            _fail("W2C target-generation progress identity/census drift")
        group_ids: list[str] = []
        for group_row in current_group:
            if type(group_row) is not dict or set(group_row) != {
                "capture_id", "first_observed_at"
            }:
                _fail("W2C target-generation current group is not canonical")
            capture_id = group_row.get("capture_id")
            if (
                type(capture_id) is not str
                or not re.fullmatch(r"mmactualcapture_[a-f0-9]{64}", capture_id)
                or _parse_utc(
                    group_row.get("first_observed_at"),
                    field="target-generation group owner clock",
                )
                > _parse_utc(
                    target_pin["pin_observed_at"], field="target progress pin"
                )
            ):
                _fail("W2C target-generation current group binding drift")
            group_ids.append(capture_id)
        if (
            len(group_ids) != len(set(group_ids))
            or len(group_ids) > len(consumed_ids)
            or consumed_ids[-len(group_ids):] != group_ids
            if group_ids else False
        ):
            _fail("W2C target-generation current group is not a consumed suffix")
    target_capture = clean.get("target_capture")
    target_mark = clean.get("target_mark")
    measurement = clean.get("measurement")
    absence = clean.get("absence_fact")
    status = clean.get("status")
    reason = clean.get("reason")
    kind = clean.get("revision_kind")
    pin_clock = (
        _parse_utc(target_pin["pin_observed_at"], field="target pin observed")
        if target_pin is not None else None
    )
    if revision_number == 1:
        allowed_initial = {
            (
                "observed", "initial_maturity_observation",
                "owner_capture_observed_at_maturity",
            ),
            (
                "unavailable", "initial_maturity_absence",
                "target_capture_absent_at_maturity_cutoff",
            ),
            (
                "censored", "initial_maturity_censoring",
                "target_capture_clock_tie_censored",
            ),
            (
                "censored", "initial_maturity_owner_miss",
                "maturity_owner_window_missed",
            ),
            (
                "censored", "initial_maturity_owner_miss",
                "maturity_owner_unavailable_by_deadline",
            ),
            (
                "censored", "initial_maturity_owner_miss",
                "maturity_owner_integrity_failure_by_deadline",
            ),
            (
                "censored", "initial_maturity_owner_miss",
                "maturity_owner_pin_cap_exceeded_by_deadline",
            ),
        }
        if (status, kind, reason) not in allowed_initial:
            _fail("W2C initial outcome status/kind/reason matrix drift")
        if reason in {
            "maturity_owner_window_missed",
            "maturity_owner_unavailable_by_deadline",
            "maturity_owner_integrity_failure_by_deadline",
            "maturity_owner_pin_cap_exceeded_by_deadline",
        }:
            if (
                target_pin is not None
                or actual_pin is not None
                or appended <= deadline
                or target_capture is not None
                or target_mark is not None
                or measurement is not None
                or not isinstance(absence, Mapping)
                or absence != {
                    "kind": "censored",
                    "reason": reason,
                    "observed_at": clean["appended_at"],
                }
            ):
                _fail("W2C initial maturity-window miss matrix drift")
        else:
            if (
                target_pin is None
                or actual_pin != target_pin["pin_observed_at"]
                or pin_clock is None
                or not opened <= pin_clock <= deadline
                or appended < pin_clock
            ):
                _fail("W2C initial stable pin clocks do not bind one cutoff")
            if status == "unavailable" and absence != {
                "kind": "missing",
                "reason": reason,
                "observed_at": target_pin["pin_observed_at"],
            }:
                _fail("W2C initial unavailable absence fact drift")
            if status == "censored" and absence != {
                "kind": "censored",
                "reason": reason,
                "observed_at": target_pin["pin_observed_at"],
            }:
                _fail("W2C initial tie-censor absence fact drift")
    else:
        if history is None:
            if previous is None or previous.get("revision_number") != 1:
                _fail("W2C later outcome validation requires its complete history")
            history = [previous]
        if (
            previous is None
            or not history
            or history[-1].get("outcome_revision_id")
            != previous.get("outcome_revision_id")
            or [row.get("revision_number") for row in history]
            != list(range(1, revision_number))
        ):
            _fail("W2C later outcome history is branched or gapped")
        selected_history = [
            row["target_capture"] for row in history
            if row.get("target_capture") is not None
        ]
        initial_status = history[0].get("status")
        if status == "censored":
            expected_later = (status, kind, reason) if (
                kind == "source_correction_censoring"
                and reason in {
                    "later_owner_capture_clock_tie_censored",
                    "later_owner_capture_order_integrity_censored",
                }
            ) else None
        elif status == "observed" and selected_history:
            expected_later = (
                "observed", "source_correction", "later_owner_source_revision",
            )
        elif status == "observed" and initial_status == "unavailable":
            expected_later = (
                "observed", "late_source_resolution",
                "late_owner_source_resolution_after_unavailable",
            )
        elif status == "observed" and initial_status == "censored":
            expected_later = (
                "observed", "late_source_resolution",
                "late_owner_source_resolution_after_censored",
            )
        else:
            expected_later = None
        if expected_later is None or (status, kind, reason) != expected_later:
            _fail("W2C later outcome status/kind/reason matrix drift")
        historical_group_clocks = [
            _parse_utc(
                group_row["first_observed_at"],
                field="historical target-generation group clock",
            )
            for row in history
            if type(row.get("target_generation_progress")) is dict
            for group_row in row["target_generation_progress"]["current_group"]
        ]
        current_group_clocks = (
            [
                _parse_utc(
                    group_row["first_observed_at"],
                    field="current target-generation group clock",
                )
                for group_row in progress["current_group"]
            ]
            if type(progress) is dict else []
        )
        historical_boundary = (
            max(historical_group_clocks) if historical_group_clocks else None
        )
        if reason == "later_owner_capture_order_integrity_censored" and (
            not current_group_clocks
            or historical_boundary is None
            or max(current_group_clocks) >= historical_boundary
        ):
            _fail("W2C owner-order censor does not bind a reordered capture group")
        if reason == "later_owner_capture_clock_tie_censored" and (
            not current_group_clocks
            or not (
                len(current_group_clocks) > 1
                or (
                    historical_boundary is not None
                    and current_group_clocks[0] == historical_boundary
                )
            )
        ):
            _fail("W2C later tie censor does not bind an equal-clock group")
        terminal_deadline = datetime.combine(
            TERMINAL_CENSUS_DATE, time(4, 45), tzinfo=timezone.utc
        )
        previous_appended = _parse_utc(
            previous["appended_at"], field="previous outcome appended_at"
        )
        previous_pin_value = next(
            (
                row["target_generation_pin"]["pin_observed_at"]
                for row in reversed(history)
                if row.get("target_generation_pin") is not None
            ),
            None,
        )
        previous_pin_clock = (
            _parse_utc(previous_pin_value, field="previous outcome generation pin")
            if previous_pin_value is not None
            else None
        )
        first_pin = history[0].get("target_generation_pin")
        same_generation_suffix = (
            target_pin is not None
            and previous.get("target_generation_pin") is not None
            and target_pin["generation_id"]
            == previous["target_generation_pin"]["generation_id"]
            and target_pin["pin_observed_at"]
            == previous["target_generation_pin"]["pin_observed_at"]
            and any(
                row.get("target_generation_pin", {}).get("generation_id")
                == target_pin["generation_id"]
                for row in history
                if isinstance(row.get("target_generation_pin"), Mapping)
            )
        )
        if (
            target_pin is None
            or pin_clock is None
            or appended < pin_clock
            or appended < previous_appended
            or pin_clock > terminal_deadline
            or (
                same_generation_suffix
                and previous_pin_clock is not None
                and pin_clock != previous_pin_clock
            )
            or (
                not same_generation_suffix
                and (
                    (
                        previous_pin_clock is not None
                        and pin_clock <= previous_pin_clock
                    )
                    or not _inside_finite_correction_window(
                        pin_clock, target_session=target_session
                    )
                    or (
                        previous.get("target_generation_pin") is not None
                        and target_pin["generation_id"]
                        == previous["target_generation_pin"]["generation_id"]
                    )
                )
            )
            or (
                same_generation_suffix
                and first_pin is not None
                and target_pin["generation_id"] == first_pin["generation_id"]
                and not opened <= pin_clock <= deadline
            )
        ):
            _fail("W2C later outcome generation/revision clock is not strictly new")
        if status == "censored" and absence != {
            "kind": "censored",
            "reason": reason,
            "observed_at": target_pin["pin_observed_at"],
        }:
            _fail("W2C later tie-censor absence fact drift")
    if status == "observed":
        if target_pin is None or target_capture is None or target_mark is None or measurement is None or absence is not None:
            _fail("W2C observed outcome conditional fields disagree")
        target_ref = _validate_technical_ref(
            target_capture, session=opportunity["target_session"]
        )
        clean["target_capture"] = target_ref
        if (
            type(progress) is not dict
            or progress["current_group"] != [{
                "capture_id": target_ref["capture_id"],
                "first_observed_at": target_ref["first_observed_at"],
            }]
        ):
            _fail("W2C observed target is not the exact consumed owner group")
        mark, target_value = _validate_mark(
            target_mark, expected_session=opportunity["target_session"]
        )
        if mark != _mark_from_technical(target_ref):
            _fail("W2C target mark differs from its exact owner capture")
        _validate_measurement(measurement, target=target_value, anchor=anchor_value)
        if _parse_utc(target_ref["first_observed_at"], field="target first observed") > _parse_utc(
            target_pin["pin_observed_at"], field="target pin observed"
        ):
            _fail("W2C target capture owner clock follows its generation pin")
        if revision_number > 1 and history:
            selected_history = [
                row["target_capture"] for row in history
                if row.get("target_capture") is not None
            ]
            if selected_history and _parse_utc(
                target_ref["first_observed_at"], field="later target clock"
            ) <= _parse_utc(
                selected_history[-1]["first_observed_at"],
                field="prior selected target clock",
            ):
                _fail("W2C source correction is not strictly later owner observation")
    elif status in {"unavailable", "censored"}:
        if target_capture is not None or target_mark is not None or measurement is not None:
            _fail("W2C missing/censored outcome cannot carry a selected target")
        absence_fields = {"kind", "reason", "observed_at"}
        if not isinstance(absence, Mapping) or set(absence) != absence_fields or absence.get("reason") != reason:
            _fail("W2C missing/censored outcome lacks its immutable absence fact")
        _parse_utc(absence.get("observed_at"), field="outcome absence observed_at")
        if status == "unavailable" and revision_number != 1:
            _fail("W2C unavailable is an initial terminal fact only")
        if status == "unavailable" and (
            type(progress) is not dict
            or progress["consumed_capture_ids"]
            or progress["current_group"]
        ):
            _fail("W2C target absence invents consumed owner captures")
        if status == "censored" and target_pin is not None:
            group_size = len(progress["current_group"])
            if (
                reason == "target_capture_clock_tie_censored"
                and group_size < 2
            ) or (
                reason in {
                    "later_owner_capture_clock_tie_censored",
                    "later_owner_capture_order_integrity_censored",
                }
                and group_size < 1
            ):
                _fail("W2C target censor does not bind its offending owner group")
    else:
        _fail("W2C outcome status is not canonical")
    if previous is not None:
        if clean["anchor_mark"] != previous["anchor_mark"]:
            _fail("W2C later outcome revision rewrites its anchor")
        if clean["maturity"] != previous["maturity"] or clean["maturity_cutoff"] != previous["maturity_cutoff"]:
            _fail("W2C later outcome revision rewrites its maturity fact")
        previous_progress = previous.get("target_generation_progress")
        if (
            type(progress) is dict
            and type(previous_progress) is dict
            and progress["generation_id"] == previous_progress["generation_id"]
            and progress["consumed_capture_ids"][:len(
                previous_progress["consumed_capture_ids"]
            )] != previous_progress["consumed_capture_ids"]
        ):
            _fail("W2C target-generation progress rewrites its consumed prefix")
    _require_commit(clean.get("writer_commit"))
    outcome_id = clean.get("outcome_revision_id")
    if type(outcome_id) is not str or not _OUTCOME_ID.fullmatch(outcome_id):
        _fail("W2C outcome revision ID is malformed")
    if _content_id("mmspyexpout_", clean, field="outcome_revision_id") != outcome_id:
        _fail("W2C outcome revision ID does not bind its content")
    return clean


def _outcome_directory(root: Path, opportunity_id: str) -> Path:
    return _safe_path(root, "outcomes", opportunity_id)


def _load_outcome_chain(
    root: Path, *, registration: Registration, opportunity: Mapping[str, Any]
) -> list[dict[str, Any]]:
    directory = _outcome_directory(root, str(opportunity["opportunity_id"]))
    if not directory.exists():
        return []
    metadata = directory.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("W2C outcome path is not a real directory")
    revision_numbers: set[int] = set()
    for item in directory.iterdir():
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("W2C outcome directory contains a non-regular artifact")
        match = re.fullmatch(r"([0-9]{6})\.json", item.name)
        pending_match = re.fullmatch(
            r"\.([0-9]{6}\.json)\.[a-f0-9]{64}\.pending",
            item.name,
        )
        if match is not None:
            revision_numbers.add(int(match.group(1)))
        elif pending_match is not None:
            revision_numbers.add(int(pending_match.group(1)[:6]))
        else:
            _fail("W2C outcome revision artifact name is noncanonical")
    if (
        len(revision_numbers) > MAX_OUTCOME_REVISIONS
        or sorted(revision_numbers)
        != list(range(1, len(revision_numbers) + 1))
    ):
        _fail("W2C outcome revision files are gapped or noncanonical")
    chain: list[dict[str, Any]] = []
    for revision_number in sorted(revision_numbers):
        path = _safe_path(
            root, "outcomes", str(opportunity["opportunity_id"]),
            f"{revision_number:06d}.json",
        )

        def validate(raw: dict[str, Any], _body: bytes) -> dict[str, Any]:
            return validate_outcome_revision(
                raw,
                registration=registration,
                opportunity=opportunity,
                previous=chain[-1] if chain else None,
                history=chain,
            )

        clean = _recover_immutable_json(
            path,
            limit=_MAX_OUTCOME_BYTES,
            label="W2C outcome revision",
            validator=validate,
        )
        if clean is None:  # pragma: no cover - census above proves an artifact
            _fail("W2C outcome revision disappeared during recovery")
        chain.append(clean)
    return chain


def _write_outcome(root: Path, outcome: Mapping[str, Any]) -> None:
    path = _safe_path(
        root, "outcomes", str(outcome["opportunity_id"]),
        f"{int(outcome['revision_number']):06d}.json",
    )
    _write_create_once(
        path, _canonical_bytes(outcome),
        limit=_MAX_OUTCOME_BYTES, label="W2C outcome revision",
    )


def _append_initial_outcome(
    root: Path,
    *,
    registration: Registration,
    opportunity: Mapping[str, Any],
    observation: _TargetObservation,
    appended_at: datetime,
    writer_commit: str,
) -> list[dict[str, Any]]:
    target_session = date.fromisoformat(str(opportunity["target_session"]))
    opened, deadline = _window(target_session)
    pin_dt = _parse_utc(observation.pin_observed_at, field="target pin observed_at")
    if not opened <= pin_dt <= deadline:
        return []
    if not observation.stable or observation.generation_pin is None:
        return []
    candidates = sorted(
        observation.candidates,
        key=lambda item: (
            _parse_utc(
                item.reference["first_observed_at"], field="target first observed"
            ),
            item.reference["capture_id"],
        ),
    )
    if not candidates:
        initial = _new_outcome_revision(
            registration,
            opportunity=opportunity,
            revision_number=1,
            previous_outcome_revision_id=None,
            previous=None,
            status="unavailable",
            revision_kind="initial_maturity_absence",
            reason="target_capture_absent_at_maturity_cutoff",
            maturity_actual_pin=observation.pin_observed_at,
            target_generation_pin=observation.generation_pin,
            target_candidate=None,
            current_generation_group=[],
            consumed_generation_capture_ids=[],
            appended_at=_format_utc(appended_at),
            writer_commit=writer_commit,
        )
        _write_outcome(root, initial)
        return [initial]
    groups: list[list[_TechnicalCandidate]] = []
    for candidate in candidates:
        clock = _parse_utc(
            candidate.reference["first_observed_at"],
            field="initial target owner clock",
        )
        if not groups or _parse_utc(
            groups[-1][0].reference["first_observed_at"],
            field="initial target group clock",
        ) != clock:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    chain: list[dict[str, Any]] = []
    consumed_capture_ids: list[str] = []
    for group in groups:
        previous = chain[-1] if chain else None
        revision_number = len(chain) + 1
        if len(group) > 1:
            status = "censored"
            kind = (
                "initial_maturity_censoring"
                if previous is None else "source_correction_censoring"
            )
            reason = (
                "target_capture_clock_tie_censored"
                if previous is None else "later_owner_capture_clock_tie_censored"
            )
            selected = None
        else:
            status = "observed"
            if previous is None:
                kind = "initial_maturity_observation"
                reason = "owner_capture_observed_at_maturity"
            elif any(row["target_capture"] is not None for row in chain):
                kind = "source_correction"
                reason = "later_owner_source_revision"
            else:
                kind = "late_source_resolution"
                reason = "late_owner_source_resolution_after_censored"
            selected = group[0]
        consumed_capture_ids.extend(
            candidate.reference["capture_id"] for candidate in group
        )
        row = _new_outcome_revision(
            registration,
            opportunity=opportunity,
            revision_number=revision_number,
            previous_outcome_revision_id=(
                previous["outcome_revision_id"] if previous is not None else None
            ),
            previous=previous,
            status=status,
            revision_kind=kind,
            reason=reason,
            maturity_actual_pin=observation.pin_observed_at,
            target_generation_pin=observation.generation_pin,
            target_candidate=selected,
            current_generation_group=group,
            consumed_generation_capture_ids=consumed_capture_ids,
            appended_at=_format_utc(appended_at),
            writer_commit=writer_commit,
            history=list(chain) if chain else None,
        )
        _write_outcome(root, row)
        chain.append(row)
    return chain


def _append_maturity_owner_miss(
    root: Path,
    *,
    registration: Registration,
    opportunity: Mapping[str, Any],
    reconciled_at: datetime,
    reason: str = "maturity_owner_window_missed",
    writer_commit: str,
) -> dict[str, Any]:
    target_session = date.fromisoformat(str(opportunity["target_session"]))
    _opened, deadline = _window(target_session)
    if reconciled_at <= deadline:
        raise MarketMemoryExperienceAccrualError(
            "W2C maturity-owner miss cannot be reconciled before deadline"
        )
    outcome = _new_outcome_revision(
        registration,
        opportunity=opportunity,
        revision_number=1,
        previous_outcome_revision_id=None,
        previous=None,
        status="censored",
        revision_kind="initial_maturity_owner_miss",
        reason=reason,
        maturity_actual_pin=None,
        target_generation_pin=None,
        target_candidate=None,
        current_generation_group=None,
        consumed_generation_capture_ids=None,
        appended_at=_format_utc(reconciled_at),
        writer_commit=writer_commit,
    )
    _write_outcome(root, outcome)
    return outcome


def _append_later_target_revisions(
    root: Path,
    *,
    registration: Registration,
    opportunity: Mapping[str, Any],
    chain: list[dict[str, Any]],
    observation: _TargetObservation,
    appended_at: datetime,
    writer_commit: str,
) -> list[dict[str, Any]]:
    if not observation.stable or observation.generation_pin is None:
        return []
    target_session = date.fromisoformat(str(opportunity["target_session"]))
    generation_id = observation.generation_pin["generation_id"]
    pinned_rows = [
        row for row in chain if row.get("target_generation_pin") is not None
    ]
    previous_pinned = pinned_rows[-1]["target_generation_pin"] if pinned_rows else None
    same_generation_resume = (
        previous_pinned is not None
        and previous_pinned["generation_id"] == generation_id
    )
    if any(
        row["target_generation_pin"]["generation_id"] == generation_id
        for row in pinned_rows[:-1]
    ) and not same_generation_resume:
        _fail("W2C correction generation reopens a non-active owner generation")

    effective_pin = (
        copy.deepcopy(previous_pinned)
        if same_generation_resume else copy.deepcopy(observation.generation_pin)
    )
    pin_clock = _parse_utc(
        effective_pin["pin_observed_at"], field="later target generation pin"
    )
    if not _inside_finite_correction_window(
        pin_clock, target_session=target_session
    ):
        return []

    all_candidates = sorted(
        observation.candidates,
        key=lambda item: (
            _parse_utc(
                item.reference["first_observed_at"], field="target first observed"
            ),
            item.reference["capture_id"],
        ),
    )
    historically_consumed_ids = {
        str(capture_id)
        for row in chain
        if type(row.get("target_generation_progress")) is dict
        for capture_id in row["target_generation_progress"][
            "consumed_capture_ids"
        ]
    }
    current_candidate_ids = {
        item.reference["capture_id"] for item in all_candidates
    }
    if not historically_consumed_ids.issubset(current_candidate_ids):
        _fail("W2C correction generation lost a previously consumed capture")
    consumed_capture_ids: list[str] = []
    if same_generation_resume:
        if (
            observation.generation_pin["generation_sha256"]
            != previous_pinned["generation_sha256"]
            or observation.generation_pin["capture_count"]
            != previous_pinned["capture_count"]
        ):
            _fail("W2C same-generation resume changed immutable owner identity")
        same_generation_rows = [
            row for row in pinned_rows
            if row["target_generation_pin"]["generation_id"] == generation_id
        ]
        progress = same_generation_rows[-1].get("target_generation_progress")
        if type(progress) is not dict:
            _fail("W2C same-generation resume lacks consumed capture progress")
        consumed_capture_ids = list(progress["consumed_capture_ids"])
        consumed_before_generation = {
            str(capture_id)
            for row in chain
            if type(row.get("target_generation_progress")) is dict
            and row["target_generation_progress"]["generation_id"]
            != generation_id
            for capture_id in row["target_generation_progress"][
                "consumed_capture_ids"
            ]
        }
        generation_candidates = [
            item for item in all_candidates
            if item.reference["capture_id"] not in consumed_before_generation
        ]
        all_ids = [
            item.reference["capture_id"] for item in generation_candidates
        ]
        if all_ids[:len(consumed_capture_ids)] != consumed_capture_ids:
            _fail("W2C same-generation resume cannot authenticate its consumed prefix")
        new_candidates = generation_candidates[len(consumed_capture_ids):]
    else:
        if previous_pinned is not None:
            previous_generation_id = previous_pinned["generation_id"]
            if previous_generation_id not in observation.ancestry_generation_ids:
                _fail("W2C correction pin does not descend from its active predecessor")
            if (
                observation.generation_pin["capture_count"]
                <= int(previous_pinned["capture_count"])
            ):
                _fail("W2C correction generation does not extend its predecessor")
        new_candidates = [
            item for item in all_candidates
            if item.reference["capture_id"] not in historically_consumed_ids
        ]
    if not new_candidates:
        return []

    historical_group_clocks = [
        _parse_utc(
            group_row["first_observed_at"], field="prior consumed owner clock"
        )
        for row in chain
        if type(row.get("target_generation_progress")) is dict
        for group_row in row["target_generation_progress"]["current_group"]
    ]
    prior_boundary: datetime | None = (
        max(historical_group_clocks) if historical_group_clocks else None
    )
    candidates = list(new_candidates)
    groups: list[list[_TechnicalCandidate]] = []
    for candidate in candidates:
        clock = _parse_utc(
            candidate.reference["first_observed_at"],
            field="new target owner clock",
        )
        if not groups or _parse_utc(
            groups[-1][0].reference["first_observed_at"],
            field="new target group clock",
        ) != clock:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    appended: list[dict[str, Any]] = []
    working = list(chain)
    for group in groups:
        group_clock = _parse_utc(
            group[0].reference["first_observed_at"],
            field="new target group clock",
        )
        reordered = prior_boundary is not None and group_clock < prior_boundary
        tie = len(group) > 1 or (
            prior_boundary is not None and group_clock == prior_boundary
        )
        previous = working[-1]
        selected_history = [
            row["target_capture"] for row in working
            if row["target_capture"] is not None
        ]
        if reordered:
            status = "censored"
            kind = "source_correction_censoring"
            reason = "later_owner_capture_order_integrity_censored"
            target_candidate = None
        elif tie:
            status = "censored"
            kind = "source_correction_censoring"
            reason = "later_owner_capture_clock_tie_censored"
            target_candidate = None
        else:
            status = "observed"
            if selected_history:
                kind = "source_correction"
                reason = "later_owner_source_revision"
            else:
                kind = "late_source_resolution"
                reason = (
                    "late_owner_source_resolution_after_unavailable"
                    if working[0]["status"] == "unavailable"
                    else "late_owner_source_resolution_after_censored"
                )
            target_candidate = group[0]
        row = _new_outcome_revision(
            registration,
            opportunity=opportunity,
            revision_number=previous["revision_number"] + 1,
            previous_outcome_revision_id=previous["outcome_revision_id"],
            previous=previous,
            status=status,
            revision_kind=kind,
            reason=reason,
            maturity_actual_pin=working[0]["maturity_cutoff"]["actual_pin_observed_at"],
            target_generation_pin=effective_pin,
            target_candidate=target_candidate,
            current_generation_group=group,
            consumed_generation_capture_ids=[
                *consumed_capture_ids,
                *(candidate.reference["capture_id"] for candidate in group),
            ],
            appended_at=_format_utc(appended_at),
            writer_commit=writer_commit,
            history=list(working),
        )
        _write_outcome(root, row)
        appended.append(row)
        working.append(row)
        consumed_capture_ids.extend(
            candidate.reference["capture_id"] for candidate in group
        )
        prior_boundary = (
            group_clock if prior_boundary is None else max(prior_boundary, group_clock)
        )
    return appended


def _accrue_outcomes(
    root: Path,
    *,
    registration: Registration,
    opportunity: Mapping[str, Any],
    now: datetime,
    observation: _TargetObservation,
    writer_commit: str,
) -> list[str]:
    if opportunity["disposition"] != "admitted":
        return []
    target_session = date.fromisoformat(str(opportunity["target_session"]))
    opened, deadline = _window(target_session)
    if now < opened:
        return []
    chain = _load_outcome_chain(
        root, registration=registration, opportunity=opportunity
    )
    appended: list[dict[str, Any]] = []
    if not chain:
        pin_dt = _parse_utc(
            observation.pin_observed_at, field="target actual pin"
        )
        if (
            observation.stable
            and observation.generation_pin is not None
            and opened <= pin_dt <= deadline
        ):
            initial = _append_initial_outcome(
                root,
                registration=registration,
                opportunity=opportunity,
                observation=observation,
                appended_at=now,
                writer_commit=writer_commit,
            )
            appended.extend(initial)
            chain = list(initial)
        elif now > deadline:
            maturity_miss_reason = {
                "owner_unavailable_by_deadline":
                    "maturity_owner_unavailable_by_deadline",
                "owner_integrity_failure_by_deadline":
                    "maturity_owner_integrity_failure_by_deadline",
                "owner_pin_cap_exceeded_by_deadline":
                    "maturity_owner_pin_cap_exceeded_by_deadline",
            }.get(
                observation.failure_reason,
                "maturity_owner_window_missed",
            )
            appended.append(
                _append_maturity_owner_miss(
                    root,
                    registration=registration,
                    opportunity=opportunity,
                    reconciled_at=now,
                    reason=maturity_miss_reason,
                    writer_commit=writer_commit,
                )
            )
            chain = list(appended)
    if chain:
        later = _append_later_target_revisions(
            root,
            registration=registration,
            opportunity=opportunity,
            chain=chain,
            observation=observation,
            appended_at=now,
            writer_commit=writer_commit,
        )
        appended.extend(later)
    return [str(row["outcome_revision_id"]) for row in appended]


def _auditability_status(trusted_count: int, technical_count: int) -> str:
    maximum = max(trusted_count, technical_count)
    if maximum >= 384:
        return "critical_checkpoint_migration_required"
    if maximum >= 320:
        return "warning_checkpoint_migration_due"
    return "within_v1_auditability_window"


def _validate_population_opportunity_input(
    expected_sessions: list[date], opportunities: list[dict[str, Any]]
) -> None:
    expected = [session.isoformat() for session in expected_sessions]
    observed_sessions = [row.get("session") for row in opportunities]
    observed_ids = [row.get("opportunity_id") for row in opportunities]
    expected_order = [session for session in expected if session in observed_sessions]
    if (
        len(observed_sessions) != len(set(observed_sessions))
        or len(observed_ids) != len(set(observed_ids))
        or any(session not in expected for session in observed_sessions)
        or observed_sessions != expected_order
    ):
        _fail("W2C population opportunity input is duplicated, extra, or permuted")


def _new_population_receipt(
    registration: Registration,
    *,
    root: Path,
    expected_sessions: list[date],
    opportunities: list[dict[str, Any]],
    owner_pins: OwnerPins | None,
    owner_pin_observed_at: str | None,
    terminal_receipt: Mapping[str, Any] | None,
    observed_at: str,
    writer_commit: str,
    previous_population_receipt_id: str | None = None,
) -> dict[str, Any]:
    if not expected_sessions:
        _fail("W2C cannot issue a population receipt before the first obligation")
    _validate_population_opportunity_input(expected_sessions, opportunities)
    by_session = {row["session"]: row for row in opportunities}
    opportunity_rows = [
        {
            "session": session.isoformat(),
            "opportunity_id": by_session[session.isoformat()]["opportunity_id"],
            "disposition": by_session[session.isoformat()]["disposition"],
        }
        for session in expected_sessions
        if session.isoformat() in by_session
    ]
    missing_sessions = [
        session.isoformat() for session in expected_sessions
        if session.isoformat() not in by_session
    ]
    observed_dt = _parse_utc(observed_at, field="population observed_at")
    matured: list[dict[str, Any]] = []
    latest_outcomes: list[dict[str, Any]] = []
    outcome_missing: list[str] = []
    revision_count = 0
    for opportunity in opportunities:
        if opportunity["disposition"] != "admitted":
            continue
        target = date.fromisoformat(str(opportunity["target_session"]))
        if observed_dt < _window(target)[0]:
            continue
        matured.append(opportunity)
        chain = _load_outcome_chain(
            root, registration=registration, opportunity=opportunity
        )
        chain = [
            row
            for row in chain
            if _parse_utc(
                row["appended_at"], field="population outcome appended_at"
            )
            <= observed_dt
        ]
        revision_count += len(chain)
        if not chain:
            outcome_missing.append(opportunity["opportunity_id"])
            continue
        latest = chain[-1]
        owner_failure_reason_counts = {
            "integrity": sum(
                row["reason"] in {
                    "maturity_owner_window_missed",
                    "maturity_owner_integrity_failure_by_deadline",
                    "later_owner_capture_clock_tie_censored",
                    "later_owner_capture_order_integrity_censored",
                    "target_capture_clock_tie_censored",
                }
                for row in chain
            ),
            "unavailable": sum(
                row["reason"] == "maturity_owner_unavailable_by_deadline"
                for row in chain
            ),
            "pin_cap": sum(
                row["reason"] == "maturity_owner_pin_cap_exceeded_by_deadline"
                for row in chain
            ),
        }
        latest_outcomes.append(
            {
                "opportunity_id": opportunity["opportunity_id"],
                "outcome_revision_id": latest["outcome_revision_id"],
                "revision_number": latest["revision_number"],
                "status": latest["status"],
                "owner_failure_reason_counts": owner_failure_reason_counts,
            }
        )
    dispositions = [row["disposition"] for row in opportunities]
    observed_count = sum(row["status"] == "observed" for row in latest_outcomes)
    unavailable_count = sum(row["status"] == "unavailable" for row in latest_outcomes)
    censored_count = sum(row["status"] == "censored" for row in latest_outcomes)
    latest_by_opportunity = {row["opportunity_id"]: row for row in latest_outcomes}
    timely = [row for row in opportunities if row["disposition"] != "missed"]
    projected_timely = [
        row for row in timely if row["decision_state_projection"] is not None
    ]
    scoreable = [
        row for row in matured
        if row["decision_state_projection"] is not None
        and latest_by_opportunity.get(row["opportunity_id"], {}).get("status")
        == "observed"
    ]
    scoreable_ids = [row["opportunity_id"] for row in scoreable]
    scoreable_id_set = set(scoreable_ids)
    abstention_reasons = {
        reason: sum(
            row["disposition"] == "abstained" and row["reason"] == reason
            for row in opportunities
        )
        for reason in (
            "trusted_macro_session_absent", "technical_session_absent",
            "trusted_macro_and_technical_session_absent",
            "owner_capture_clock_tie",
        )
    }
    projection_unavailable_reasons = {
        reason: sum(
            row["decision_state_projection"] is None
            and row["decision_state_projection_reason"] == reason
            for row in opportunities
        )
        for reason in (
            "trusted_macro_unavailable_or_ambiguous",
            "missed_without_authenticated_owner_pair",
            "owner_liquidity_overlay_unknown",
            "owner_cycle_tag_unknown",
            "owner_liquidity_overlay_and_cycle_tag_unknown",
        )
    }
    opportunity_owner_integrity_failures = sum(
        row["reason"] in {
            "owner_pair_not_stable_by_deadline",
            "owner_integrity_failure_by_deadline",
            "owner_pin_cap_exceeded_by_deadline",
            "owner_capture_clock_tie",
        }
        for row in opportunities
    )
    opportunity_owner_unavailable_failures = sum(
        row["reason"] == "owner_unavailable_by_deadline"
        for row in opportunities
    )
    opportunity_owner_pin_cap_failures = sum(
        row["reason"] == "owner_pin_cap_exceeded_by_deadline"
        for row in opportunities
    )
    outcome_owner_integrity_failures = sum(
        row["owner_failure_reason_counts"]["integrity"]
        for row in latest_outcomes
    )
    outcome_owner_unavailable_failures = sum(
        row["owner_failure_reason_counts"]["unavailable"]
        for row in latest_outcomes
    )
    outcome_owner_pin_cap_failures = sum(
        row["owner_failure_reason_counts"]["pin_cap"]
        for row in latest_outcomes
    )

    def category_counts(field: str, vocabulary: tuple[str, ...]) -> dict[str, int]:
        return {
            item: sum(
                row["decision_state_projection"][field] == item
                for row in scoreable
            )
            for item in vocabulary
        }

    quad_counts = category_counts("quad", ("Q1", "Q2", "Q3", "Q4"))
    liquidity_counts = category_counts(
        "liquidity_overlay", ("expanding", "neutral", "contracting", "unknown")
    )
    cycle_counts = category_counts("cycle_tag", ("early", "mid", "late", "unknown"))
    numeric_pairs = {
        (
            row["decision_state_projection"]["growth_score"]["q18"],
            row["decision_state_projection"]["inflation_score"]["q18"],
        )
        for row in scoreable
    }
    complete_scoreable_blocks = sum(
        len(block) == 5
        and all(
            by_session.get(session.isoformat(), {}).get("opportunity_id")
            in scoreable_id_set
            for session in block
        )
        for start in range(0, len(expected_sessions), 5)
        for block in (expected_sessions[start:start + 5],)
    )
    trusted_count = (
        len(owner_pins.trusted.captures) if owner_pins is not None else None
    )
    technical_count = (
        len(owner_pins.technical.captures) if owner_pins is not None else None
    )
    terminal_opened, terminal_deadline = _terminal_window()
    terminal = {
        "correction_observation_sessions": CORRECTION_OBSERVATION_SESSIONS,
        "correction_sunset_session": CORRECTION_SUNSET_SESSION.isoformat(),
        "terminal_window_opens_at": _format_utc(terminal_opened),
        "terminal_deadline_at": _format_utc(terminal_deadline),
        "status": "sealed" if terminal_receipt is not None else "open",
        "receipt": (
            copy.deepcopy(dict(terminal_receipt))
            if terminal_receipt is not None else None
        ),
        "denominator_and_maturity_receipts_complete": (
            not missing_sessions and not outcome_missing
        ),
        "final_source_revision_census_authenticated": (
            terminal_receipt is not None
            and terminal_receipt.get("disposition")
            == "stable_terminal_generation_observed"
        ),
    }
    counts = {
        "expected": len(expected_sessions),
        "recorded": len(opportunities),
        "admitted": dispositions.count("admitted"),
        "abstained": dispositions.count("abstained"),
        "missed": dispositions.count("missed"),
        "matured_admitted": len(matured),
        "outcome_receipted": len(latest_outcomes),
        "outcome_observed": observed_count,
        "outcome_unavailable": unavailable_count,
        "outcome_censored": censored_count,
        "outcome_revision_count": revision_count,
        "pending_admitted": dispositions.count("admitted") - len(matured),
        "corrected_outcome_chains": sum(
            row["revision_number"] > 1 for row in latest_outcomes
        ),
        "scoreable": len(scoreable),
        "timely": len(timely),
        "projected_timely": len(projected_timely),
    }
    value: dict[str, Any] = {
        "schema": POPULATION_SCHEMA,
        "population_receipt_id": "",
        "previous_population_receipt_id": previous_population_receipt_id,
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "through_session": expected_sessions[-1].isoformat(),
        "census_basis": "frozen_activation_plus_xnys_calendar_not_presence_or_timer_runs",
        "expected_sessions": [item.isoformat() for item in expected_sessions],
        "opportunities": opportunity_rows,
        "missing_sessions": missing_sessions,
        "matured_admitted_opportunity_ids": [row["opportunity_id"] for row in matured],
        "latest_outcomes": latest_outcomes,
        "outcome_missing_opportunity_ids": outcome_missing,
        "scoreable_opportunity_ids": scoreable_ids,
        "counts": counts,
        "coverage": {
            "opportunity_completeness_q18": _q18_fraction(counts["recorded"], counts["expected"]),
            "admission_coverage_q18": _q18_fraction(counts["admitted"], counts["expected"]),
            "mature_outcome_receipt_coverage_q18": _q18_fraction(counts["outcome_receipted"], counts["matured_admitted"]),
            "mature_observed_target_coverage_q18": _q18_fraction(counts["outcome_observed"], counts["matured_admitted"]),
            "timely_opportunity_coverage_q18": _q18_fraction(
                counts["timely"], counts["expected"]
            ),
            "due_outcome_completion_q18": _q18_fraction(
                counts["outcome_receipted"], counts["matured_admitted"]
            ),
            "timely_coordinate_coverage_q18": _q18_fraction(
                counts["projected_timely"], counts["timely"]
            ),
        },
        "decision_state_diagnostics": {
            "abstained_by_reason": abstention_reasons,
            "projection_unavailable_by_reason": projection_unavailable_reasons,
            "scoreable_quad_counts": quad_counts,
            "scoreable_liquidity_overlay_counts": liquidity_counts,
            "scoreable_cycle_tag_counts": cycle_counts,
            "scoreable_distinct_quads": sum(value > 0 for value in quad_counts.values()),
            "scoreable_distinct_liquidity_overlays": sum(
                value > 0 for value in liquidity_counts.values()
            ),
            "scoreable_distinct_cycle_tags": sum(
                value > 0 for value in cycle_counts.values()
            ),
            "scoreable_distinct_numeric_coordinate_pairs": len(numeric_pairs),
            "scoreable_coordinates_nondegenerate": (
                len(numeric_pairs) > 1
                or sum(value > 0 for value in quad_counts.values()) > 1
                or sum(value > 0 for value in liquidity_counts.values()) > 1
                or sum(value > 0 for value in cycle_counts.values()) > 1
            ),
            "complete_non_overlapping_five_session_scoreable_blocks": complete_scoreable_blocks,
            "owner_integrity_failure_fact_count": (
                opportunity_owner_integrity_failures
                + outcome_owner_integrity_failures
            ),
            "owner_unavailable_failure_fact_count": (
                opportunity_owner_unavailable_failures
                + outcome_owner_unavailable_failures
            ),
            "owner_pin_cap_failure_fact_count": (
                opportunity_owner_pin_cap_failures
                + outcome_owner_pin_cap_failures
            ),
            "w4_eligibility_claimed": False,
            "retrieval_skill_claimed": False,
        },
        "owner_auditability": {
            "trusted_current_capture_count": trusted_count,
            "technical_current_capture_count": technical_count,
            "status": (
                _auditability_status(trusted_count, technical_count)
                if trusted_count is not None and technical_count is not None
                else "no_authenticated_owner_pair_ever"
            ),
            "warning_owner_capture_count": 320,
            "checkpoint_migration_required_before_owner_count": 384,
            "v2_acceptance_requirement": "reload_every_v1_pilot_source_ref_from_authenticated_checkpoint_or_delta",
            "indefinite_v1_auditability": False,
        },
        "owner_generation_refs": (
            {
                "pin_observed_at": owner_pin_observed_at,
                "trusted_generation": _generation_ref(
                    owner_pins.trusted, technical=False
                ),
                "technical_generation": _generation_ref(
                    owner_pins.technical, technical=True
                ),
            }
            if owner_pins is not None and owner_pin_observed_at is not None
            else None
        ),
        "terminal": terminal,
        "complete": (
            not missing_sessions
            and not outcome_missing
            and terminal["status"] == "sealed"
        ),
        "observed_at": observed_at,
        "writer_commit": writer_commit,
        "evidence_policy": {
            "denominator_complete": True,
            "abstentions_retained": True,
            "misses_retained": True,
            "timer_runs_are_census": False,
            "training_eligible": False,
            "promotion_eligible": False,
        },
        "claims": _population_claims(),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["population_receipt_id"] = _content_id(
        "mmspyexppop_", value, field="population_receipt_id"
    )
    return validate_population_receipt(
        value,
        registration=registration,
        expected_sessions=expected_sessions,
        opportunities=opportunities,
    )


def validate_population_receipt(
    value: Mapping[str, Any], *, registration: Registration,
    expected_sessions: list[date], opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    registration = _require_registration_capability(registration)
    if type(expected_sessions) is not list or any(
        type(session) is not date for session in expected_sessions
    ):
        _fail("W2C population expected-session argument is not one exact date list")
    if type(opportunities) is not list:
        _fail("W2C population opportunity argument is not one exact list")
    frozen_opportunities = _freeze_json_native(
        opportunities, label="W2C population opportunity argument"
    )
    if any(type(row) is not dict for row in frozen_opportunities):
        _fail("W2C population opportunity argument contains a non-object row")
    opportunities = [
        _validate_opportunity_frozen(row, registration=registration)
        for row in frozen_opportunities
    ]
    fields = {
        "schema", "population_receipt_id", "registration_id",
        "previous_population_receipt_id",
        "registration_sha256", "through_session", "census_basis",
        "expected_sessions", "opportunities", "missing_sessions",
        "matured_admitted_opportunity_ids", "latest_outcomes",
        "outcome_missing_opportunity_ids", "scoreable_opportunity_ids",
        "counts", "coverage", "decision_state_diagnostics",
        "owner_auditability", "owner_generation_refs", "terminal", "complete",
        "observed_at", "writer_commit", "evidence_policy", "claims", "authority",
    }
    clean = _freeze_json_native(value, label="W2C population receipt")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C population receipt fields are not canonical")
    _require_value_bound(
        clean, limit=_MAX_POPULATION_BYTES, label="W2C population receipt"
    )
    if (
        clean.get("schema") != POPULATION_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("census_basis")
        != "frozen_activation_plus_xnys_calendar_not_presence_or_timer_runs"
        or clean.get("authority") != dict(market_memory.AUTHORITY)
        or clean.get("claims") != _population_claims()
    ):
        _fail("W2C population registration/census binding drift")
    previous_population_id = clean.get("previous_population_receipt_id")
    if previous_population_id is not None and (
        type(previous_population_id) is not str
        or not _POPULATION_ID.fullmatch(previous_population_id)
        or previous_population_id == clean.get("population_receipt_id")
    ):
        _fail("W2C population predecessor ID is malformed or self-referential")
    _validate_population_opportunity_input(expected_sessions, opportunities)
    expected_strings = [item.isoformat() for item in expected_sessions]
    if (
        not expected_strings
        or clean.get("expected_sessions") != expected_strings
        or clean.get("through_session") != expected_strings[-1]
    ):
        _fail("W2C population denominator is not calendar-derived")
    by_session = {row["session"]: row for row in opportunities}
    expected_opportunities = [
        {
            "session": session,
            "opportunity_id": by_session[session]["opportunity_id"],
            "disposition": by_session[session]["disposition"],
        }
        for session in expected_strings if session in by_session
    ]
    missing = [session for session in expected_strings if session not in by_session]
    if clean.get("opportunities") != expected_opportunities or clean.get("missing_sessions") != missing:
        _fail("W2C population opportunity census disagrees with immutable rows")
    observed_at = _parse_utc(clean.get("observed_at"), field="population observed_at")
    if any(
        _parse_utc(
            row["sealed_at"], field="population opportunity sealed_at"
        )
        > observed_at
        for row in opportunities
    ):
        _fail("W2C population includes an opportunity from its future")
    matured = [
        row for row in opportunities
        if row["disposition"] == "admitted"
        and observed_at >= _window(date.fromisoformat(row["target_session"]))[0]
    ]
    if clean.get("matured_admitted_opportunity_ids") != [row["opportunity_id"] for row in matured]:
        _fail("W2C population matured opportunity set drift")
    latest = clean.get("latest_outcomes")
    if not isinstance(latest, list) or any(
        not isinstance(row, Mapping)
        or set(row) != {
            "opportunity_id", "outcome_revision_id", "revision_number", "status",
            "owner_failure_reason_counts",
        }
        or type(row.get("revision_number")) is not int
        or not 1 <= row["revision_number"] <= MAX_OUTCOME_REVISIONS
        or type(row.get("outcome_revision_id")) is not str
        or not _OUTCOME_ID.fullmatch(row["outcome_revision_id"])
        or row.get("status") not in {"observed", "unavailable", "censored"}
        or type(row.get("owner_failure_reason_counts")) is not dict
        or set(row["owner_failure_reason_counts"]) != {
            "integrity", "unavailable", "pin_cap"
        }
        or any(
            type(number) is not int or number < 0
            for number in row["owner_failure_reason_counts"].values()
        )
        or sum(row["owner_failure_reason_counts"].values())
        > row["revision_number"]
        for row in latest
    ):
        _fail("W2C population latest-outcome rows are not canonical")
    matured_ids = [row["opportunity_id"] for row in matured]
    latest_ids = [row["opportunity_id"] for row in latest]
    outcome_missing = [item for item in matured_ids if item not in latest_ids]
    if (
        len(latest_ids) != len(set(latest_ids))
        or any(item not in matured_ids for item in latest_ids)
        or clean.get("outcome_missing_opportunity_ids") != outcome_missing
    ):
        _fail("W2C population outcome census is incomplete or duplicated")
    dispositions = [row["disposition"] for row in opportunities]
    expected_counts = {
        "expected": len(expected_sessions),
        "recorded": len(opportunities),
        "admitted": dispositions.count("admitted"),
        "abstained": dispositions.count("abstained"),
        "missed": dispositions.count("missed"),
        "matured_admitted": len(matured),
        "outcome_receipted": len(latest),
        "outcome_observed": sum(row["status"] == "observed" for row in latest),
        "outcome_unavailable": sum(row["status"] == "unavailable" for row in latest),
        "outcome_censored": sum(row["status"] == "censored" for row in latest),
        "pending_admitted": dispositions.count("admitted") - len(matured),
        "corrected_outcome_chains": sum(
            row["revision_number"] > 1 for row in latest
        ),
        "timely": sum(row["disposition"] != "missed" for row in opportunities),
        "projected_timely": sum(
            row["disposition"] != "missed"
            and row["decision_state_projection"] is not None
            for row in opportunities
        ),
    }
    latest_by_opportunity = {row["opportunity_id"]: row for row in latest}
    scoreable = [
        row for row in matured
        if row["decision_state_projection"] is not None
        and latest_by_opportunity.get(row["opportunity_id"], {}).get("status")
        == "observed"
    ]
    expected_counts["scoreable"] = len(scoreable)
    scoreable_ids = [row["opportunity_id"] for row in scoreable]
    if clean.get("scoreable_opportunity_ids") != scoreable_ids:
        _fail("W2C population scoreable episode census drift")
    counts = clean.get("counts")
    if not isinstance(counts, Mapping) or set(counts) != {
        *expected_counts, "outcome_revision_count"
    }:
        _fail("W2C population counts are not canonical")
    if any(counts.get(field) != number for field, number in expected_counts.items()):
        _fail("W2C population counts disagree with its arrays")
    if (
        type(counts.get("outcome_revision_count")) is not int
        or counts["outcome_revision_count"]
        != sum(row["revision_number"] for row in latest)
    ):
        _fail("W2C population revision count is not the exact chain census")
    expected_coverage = {
        "opportunity_completeness_q18": _q18_fraction(counts["recorded"], counts["expected"]),
        "admission_coverage_q18": _q18_fraction(counts["admitted"], counts["expected"]),
        "mature_outcome_receipt_coverage_q18": _q18_fraction(counts["outcome_receipted"], counts["matured_admitted"]),
        "mature_observed_target_coverage_q18": _q18_fraction(counts["outcome_observed"], counts["matured_admitted"]),
        "timely_opportunity_coverage_q18": _q18_fraction(
            counts["timely"], counts["expected"]
        ),
        "due_outcome_completion_q18": _q18_fraction(
            counts["outcome_receipted"], counts["matured_admitted"]
        ),
        "timely_coordinate_coverage_q18": _q18_fraction(
            counts["projected_timely"], counts["timely"]
        ),
    }
    if clean.get("coverage") != expected_coverage:
        _fail("W2C population coverage arithmetic drift")
    scoreable_id_set = set(scoreable_ids)

    def expected_category_counts(
        field: str, vocabulary: tuple[str, ...]
    ) -> dict[str, int]:
        return {
            item: sum(
                row["decision_state_projection"][field] == item
                for row in scoreable
            )
            for item in vocabulary
        }

    quad_counts = expected_category_counts("quad", ("Q1", "Q2", "Q3", "Q4"))
    liquidity_counts = expected_category_counts(
        "liquidity_overlay", ("expanding", "neutral", "contracting", "unknown")
    )
    cycle_counts = expected_category_counts(
        "cycle_tag", ("early", "mid", "late", "unknown")
    )
    numeric_pairs = {
        (
            row["decision_state_projection"]["growth_score"]["q18"],
            row["decision_state_projection"]["inflation_score"]["q18"],
        )
        for row in scoreable
    }
    expected_diagnostics = {
        "abstained_by_reason": {
            reason: sum(
                row["disposition"] == "abstained" and row["reason"] == reason
                for row in opportunities
            )
            for reason in (
                "trusted_macro_session_absent", "technical_session_absent",
                "trusted_macro_and_technical_session_absent",
                "owner_capture_clock_tie",
            )
        },
        "projection_unavailable_by_reason": {
            reason: sum(
                row["decision_state_projection"] is None
                and row["decision_state_projection_reason"] == reason
                for row in opportunities
            )
            for reason in (
                "trusted_macro_unavailable_or_ambiguous",
                "missed_without_authenticated_owner_pair",
                "owner_liquidity_overlay_unknown",
                "owner_cycle_tag_unknown",
                "owner_liquidity_overlay_and_cycle_tag_unknown",
            )
        },
        "scoreable_quad_counts": quad_counts,
        "scoreable_liquidity_overlay_counts": liquidity_counts,
        "scoreable_cycle_tag_counts": cycle_counts,
        "scoreable_distinct_quads": sum(value > 0 for value in quad_counts.values()),
        "scoreable_distinct_liquidity_overlays": sum(
            value > 0 for value in liquidity_counts.values()
        ),
        "scoreable_distinct_cycle_tags": sum(
            value > 0 for value in cycle_counts.values()
        ),
        "scoreable_distinct_numeric_coordinate_pairs": len(numeric_pairs),
        "scoreable_coordinates_nondegenerate": (
            len(numeric_pairs) > 1
            or sum(value > 0 for value in quad_counts.values()) > 1
            or sum(value > 0 for value in liquidity_counts.values()) > 1
            or sum(value > 0 for value in cycle_counts.values()) > 1
        ),
        "complete_non_overlapping_five_session_scoreable_blocks": sum(
            len(block) == 5
            and all(
                by_session.get(session.isoformat(), {}).get("opportunity_id")
                in scoreable_id_set
                for session in block
            )
            for start in range(0, len(expected_sessions), 5)
            for block in (expected_sessions[start:start + 5],)
        ),
        "owner_integrity_failure_fact_count": (
            sum(
                row["reason"] in {
                    "owner_pair_not_stable_by_deadline",
                    "owner_integrity_failure_by_deadline",
                    "owner_pin_cap_exceeded_by_deadline",
                    "owner_capture_clock_tie",
                }
                for row in opportunities
            )
            + sum(
                row["owner_failure_reason_counts"]["integrity"]
                for row in latest
            )
        ),
        "owner_unavailable_failure_fact_count": (
            sum(
                row["reason"] == "owner_unavailable_by_deadline"
                for row in opportunities
            )
            + sum(
                row["owner_failure_reason_counts"]["unavailable"]
                for row in latest
            )
        ),
        "owner_pin_cap_failure_fact_count": (
            sum(
                row["reason"] == "owner_pin_cap_exceeded_by_deadline"
                for row in opportunities
            )
            + sum(
                row["owner_failure_reason_counts"]["pin_cap"]
                for row in latest
            )
        ),
        "w4_eligibility_claimed": False,
        "retrieval_skill_claimed": False,
    }
    if clean.get("decision_state_diagnostics") != expected_diagnostics:
        _fail("W2C decision-state population diagnostics drift")
    auditability = clean.get("owner_auditability")
    audit_fields = {
        "trusted_current_capture_count", "technical_current_capture_count", "status",
        "warning_owner_capture_count", "checkpoint_migration_required_before_owner_count",
        "v2_acceptance_requirement", "indefinite_v1_auditability",
    }
    if not isinstance(auditability, Mapping) or set(auditability) != audit_fields:
        _fail("W2C population owner auditability fields are not canonical")
    for field in ("trusted_current_capture_count", "technical_current_capture_count"):
        if auditability.get(field) is not None and (
            type(auditability.get(field)) is not int
            or not 0 <= auditability[field] <= 256
        ):
            _fail("W2C population owner count exceeds the active pilot pin cap")
    no_owner_pair = (
        auditability["trusted_current_capture_count"] is None
        and auditability["technical_current_capture_count"] is None
    )
    if (
        auditability.get("status")
        != (
            "no_authenticated_owner_pair_ever"
            if no_owner_pair
            else _auditability_status(
                auditability["trusted_current_capture_count"],
                auditability["technical_current_capture_count"],
            )
        )
        or auditability.get("warning_owner_capture_count") != 320
        or auditability.get("checkpoint_migration_required_before_owner_count") != 384
        or auditability.get("v2_acceptance_requirement")
        != "reload_every_v1_pilot_source_ref_from_authenticated_checkpoint_or_delta"
        or auditability.get("indefinite_v1_auditability") is not False
    ):
        _fail("W2C population auditability policy drift")
    owner_refs = clean.get("owner_generation_refs")
    if no_owner_pair:
        if owner_refs is not None:
            _fail("W2C no-owner-pair population invents stable owner refs")
        trusted_generation = None
        technical_generation = None
    else:
        if not isinstance(owner_refs, Mapping) or set(owner_refs) != {
            "pin_observed_at", "trusted_generation", "technical_generation"
        }:
            _fail("W2C population stable owner generation refs are not canonical")
        owner_pin_clock = _parse_utc(
            owner_refs.get("pin_observed_at"), field="population owner pin"
        )
        if owner_pin_clock > observed_at:
            _fail("W2C population owner pin follows receipt observation")
        trusted_generation = _validate_generation_ref(
            owner_refs.get("trusted_generation"), technical=False
        )
        technical_generation = _validate_generation_ref(
            owner_refs.get("technical_generation"), technical=True
        )
        if (
            trusted_generation["capture_count"]
            != auditability["trusted_current_capture_count"]
            or technical_generation["capture_count"]
            != auditability["technical_current_capture_count"]
        ):
            _fail("W2C population stable owner refs disagree with audit counts")
    terminal = clean.get("terminal")
    terminal_fields = {
        "correction_observation_sessions", "correction_sunset_session",
        "terminal_window_opens_at", "terminal_deadline_at", "status", "receipt",
        "denominator_and_maturity_receipts_complete",
        "final_source_revision_census_authenticated",
    }
    terminal_opened, terminal_deadline = _terminal_window()
    if (
        not isinstance(terminal, Mapping)
        or set(terminal) != terminal_fields
        or terminal.get("correction_observation_sessions")
        != CORRECTION_OBSERVATION_SESSIONS
        or terminal.get("correction_sunset_session")
        != CORRECTION_SUNSET_SESSION.isoformat()
        or terminal.get("terminal_window_opens_at") != _format_utc(terminal_opened)
        or terminal.get("terminal_deadline_at") != _format_utc(terminal_deadline)
        or terminal.get("status") not in {"open", "sealed"}
    ):
        _fail("W2C population terminal FSM fields drift")
    terminal_receipt = terminal.get("receipt")
    if terminal["status"] == "open":
        if terminal_receipt is not None or observed_at >= terminal_deadline:
            _fail("W2C open terminal census persists beyond its finite deadline")
    else:
        receipt_fields = {
            "disposition", "observed_at", "technical_generation_pin"
        }
        if not isinstance(terminal_receipt, Mapping) or set(terminal_receipt) != receipt_fields:
            _fail("W2C sealed terminal census lacks its receipt")
        terminal_observed = _parse_utc(
            terminal_receipt.get("observed_at"), field="terminal receipt observed_at"
        )
        disposition = terminal_receipt.get("disposition")
        terminal_pin = terminal_receipt.get("technical_generation_pin")
        if disposition == "stable_terminal_generation_observed":
            if (
                no_owner_pair
                or not isinstance(terminal_pin, Mapping)
                or not terminal_opened <= terminal_observed <= terminal_deadline
                or terminal_pin.get("pin_observed_at")
                != terminal_receipt.get("observed_at")
                or terminal_pin.get("generation_id")
                != technical_generation["generation_id"]
                or terminal_receipt.get("observed_at")
                != owner_refs.get("pin_observed_at")
            ):
                _fail("W2C stable terminal receipt lacks its in-window generation pin")
            _validate_target_generation_pin(terminal_pin)
        elif disposition == "terminal_owner_window_missed":
            if terminal_pin is not None or terminal_observed <= terminal_deadline:
                _fail("W2C terminal owner-window miss matrix drift")
        elif disposition == "no_authenticated_owner_pair_ever":
            if (
                not no_owner_pair
                or terminal_pin is not None
                or terminal_observed <= terminal_deadline
            ):
                _fail("W2C no-owner-pair terminal matrix drift")
        else:
            _fail("W2C terminal receipt disposition is not canonical")
    expected_denominator_complete = not missing and not outcome_missing
    expected_final_source = (
        terminal["status"] == "sealed"
        and isinstance(terminal_receipt, Mapping)
        and terminal_receipt.get("disposition")
        == "stable_terminal_generation_observed"
    )
    if (
        terminal.get("denominator_and_maturity_receipts_complete")
        is not expected_denominator_complete
        or terminal.get("final_source_revision_census_authenticated")
        is not expected_final_source
    ):
        _fail("W2C terminal completeness/authentication claims drift")
    expected_complete = (
        not missing and not outcome_missing and terminal["status"] == "sealed"
    )
    if clean.get("complete") is not expected_complete:
        _fail("W2C population complete flag disagrees with its receipt")
    if clean.get("evidence_policy") != {
        "denominator_complete": True,
        "abstentions_retained": True,
        "misses_retained": True,
        "timer_runs_are_census": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }:
        _fail("W2C population evidence policy drift")
    _require_commit(clean.get("writer_commit"))
    receipt_id = clean.get("population_receipt_id")
    if type(receipt_id) is not str or not _POPULATION_ID.fullmatch(receipt_id):
        _fail("W2C population receipt ID is malformed")
    if _content_id("mmspyexppop_", clean, field="population_receipt_id") != receipt_id:
        _fail("W2C population receipt ID does not bind its content")
    return clean


def _write_population_receipt(root: Path, receipt: Mapping[str, Any]) -> None:
    body = _canonical_bytes(receipt)
    receipt_id = str(receipt["population_receipt_id"])
    _write_create_once(
        _safe_path(root, "population_receipts", f"{receipt_id}.json"),
        body, limit=_MAX_POPULATION_BYTES, label="W2C population receipt",
    )
    head = {
        "schema": POPULATION_HEAD_SCHEMA,
        "population_receipt_id": receipt_id,
        "population_receipt_sha256": _digest(body),
        "population_receipt_bytes": len(body),
    }
    _replace_head(
        _safe_path(root, "population_HEAD.json"), _canonical_bytes(head)
    )


def _current_population_receipt(
    root: Path,
    *,
    registration: Registration | None = None,
    expected_sessions: list[date] | None = None,
    opportunities: list[dict[str, Any]] | None = None,
    recover_unheaded: bool = False,
) -> dict[str, Any] | None:
    if registration is not None and (
        expected_sessions is None or opportunities is None
    ):
        _fail("W2C population recovery requires its complete ledger context")

    def validate_with_receipt_denominator(
        raw: dict[str, Any]
    ) -> dict[str, Any]:
        if registration is None:
            return raw
        raw_sessions = raw.get("expected_sessions")
        if type(raw_sessions) is not list:
            _fail("W2C population recovery receipt lacks its denominator")
        try:
            receipt_sessions = [date.fromisoformat(item) for item in raw_sessions]
        except (TypeError, ValueError) as exc:
            raise MarketMemoryExperienceStoreError(
                "W2C population recovery denominator is malformed"
            ) from exc
        if receipt_sessions != expected_sessions[:len(receipt_sessions)]:
            _fail("W2C population recovery denominator is not a due prefix")
        opportunity_by_session = {
            row["session"]: row for row in opportunities
        }
        receipt_opportunities = [
            opportunity_by_session[session.isoformat()]
            for session in receipt_sessions
            if session.isoformat() in opportunity_by_session
        ]
        clean = validate_population_receipt(
            raw,
            registration=registration,
            expected_sessions=receipt_sessions,
            opportunities=receipt_opportunities,
        )
        if clean.get("owner_generation_refs") is None:
            receipt_pins = None
            receipt_pin_observed_at = None
        else:
            receipt_pins, receipt_pin_observed_at = (
                _owner_pins_from_population_receipt(clean)
            )
        recomputed = _new_population_receipt(
            registration,
            root=root,
            expected_sessions=receipt_sessions,
            opportunities=receipt_opportunities,
            owner_pins=receipt_pins,
            owner_pin_observed_at=receipt_pin_observed_at,
            terminal_receipt=(
                clean["terminal"]["receipt"]
                if clean["terminal"]["status"] == "sealed"
                else None
            ),
            observed_at=clean["observed_at"],
            writer_commit=clean["writer_commit"],
            previous_population_receipt_id=clean[
                "previous_population_receipt_id"
            ],
        )
        if _canonical_bytes(recomputed) != _canonical_bytes(clean):
            _fail("W2C population recovery receipt differs from its as-of ledger")
        return clean

    def validate_predecessor(
        descendant: Mapping[str, Any], predecessor: Mapping[str, Any]
    ) -> None:
        predecessor_sessions = predecessor["expected_sessions"]
        descendant_sessions = descendant["expected_sessions"]
        if (
            _parse_utc(
                descendant["observed_at"],
                field="population recovery descendant observed_at",
            )
            <= _parse_utc(
                predecessor["observed_at"],
                field="population recovery predecessor observed_at",
            )
            or len(descendant_sessions) < len(predecessor_sessions)
            or descendant_sessions[:len(predecessor_sessions)]
            != predecessor_sessions
            or predecessor["terminal"]["status"] == "sealed"
            or _same_population_state(descendant, predecessor)
        ):
            _fail("W2C population recovery predecessor semantics drift")
    receipts_directory = _safe_path(root, "population_receipts")
    if registration is not None and receipts_directory.exists():
        for item in sorted(receipts_directory.iterdir()):
            match = re.fullmatch(
                r"\.(mmspyexppop_[a-f0-9]{64}\.json)\.[a-f0-9]{64}\.pending",
                item.name,
            )
            if match is None:
                continue
            if not recover_unheaded:
                _fail("W2C read-only population state contains a pending receipt")
            final_path = _safe_path(root, "population_receipts", match.group(1))

            def validate_pending_receipt(
                raw: dict[str, Any], _body: bytes
            ) -> dict[str, Any]:
                clean = validate_with_receipt_denominator(raw)
                if final_path.name != f"{clean['population_receipt_id']}.json":
                    _fail("W2C pending population path differs from its ID")
                return clean

            _recover_immutable_json(
                final_path,
                limit=_MAX_POPULATION_BYTES,
                label="W2C population receipt",
                validator=validate_pending_receipt,
            )

    receipt_holder: list[dict[str, Any]] = []

    def validate_head(
        head: dict[str, Any], _head_body: bytes
    ) -> dict[str, Any]:
        if type(head) is not dict or set(head) != {
            "schema", "population_receipt_id", "population_receipt_sha256",
            "population_receipt_bytes",
        }:
            _fail("W2C population HEAD fields are not canonical")
        receipt_id = head.get("population_receipt_id")
        if (
            head.get("schema") != POPULATION_HEAD_SCHEMA
            or type(receipt_id) is not str
            or not _POPULATION_ID.fullmatch(receipt_id)
        ):
            _fail("W2C population HEAD is malformed")
        raw, body = _read_json_path(
            _safe_path(root, "population_receipts", f"{receipt_id}.json"),
            limit=_MAX_POPULATION_BYTES,
            label="W2C current population receipt",
        )
        if (
            _digest(body) != head.get("population_receipt_sha256")
            or len(body) != head.get("population_receipt_bytes")
            or raw.get("population_receipt_id") != receipt_id
            or _content_id(
                "mmspyexppop_", raw, field="population_receipt_id"
            ) != receipt_id
        ):
            _fail("W2C population HEAD does not bind its receipt")
        clean = (
            validate_with_receipt_denominator(raw)
            if registration is not None else raw
        )
        receipt_holder[:] = [clean]
        return head

    head_path = _safe_path(root, "population_HEAD.json")
    if recover_unheaded:
        head = _recover_mutable_head(
            head_path,
            label="W2C population HEAD",
            validator=validate_head,
        )
    else:
        if _pending_create_paths(head_path):
            _fail("W2C read-only population state contains a pending HEAD")
        if head_path.exists() or head_path.is_symlink():
            raw_head, head_body = _read_json_path(
                head_path,
                limit=_MAX_HEAD_BYTES,
                label="W2C population HEAD",
            )
            head = validate_head(raw_head, head_body)
        else:
            head = None
    current = None if head is None else receipt_holder[0]
    if registration is None or not receipts_directory.exists():
        return current

    receipts_by_id: dict[str, dict[str, Any]] = {}
    receipt_bodies_by_id: dict[str, bytes] = {}
    for item in sorted(receipts_directory.iterdir()):
        if not re.fullmatch(r"mmspyexppop_[a-f0-9]{64}\.json", item.name):
            _fail("W2C population recovery inventory is noncanonical")
        raw, body = _read_json_path(
            item,
            limit=_MAX_POPULATION_BYTES,
            label="W2C population recovery receipt",
        )
        clean = validate_with_receipt_denominator(raw)
        receipt_id = str(clean["population_receipt_id"])
        if item.name != f"{receipt_id}.json" or receipt_id in receipts_by_id:
            _fail("W2C population recovery receipt path/ID is ambiguous")
        receipts_by_id[receipt_id] = clean
        receipt_bodies_by_id[receipt_id] = body

    reached: set[str] = set()
    cursor = (
        str(current["population_receipt_id"])
        if current is not None
        else None
    )
    while cursor is not None:
        if cursor in reached or cursor not in receipts_by_id:
            _fail("W2C population recovery predecessor chain is cyclic or gapped")
        reached.add(cursor)
        row = receipts_by_id[cursor]
        predecessor_id = row["previous_population_receipt_id"]
        if predecessor_id is not None:
            predecessor_key = str(predecessor_id)
            if predecessor_key not in receipts_by_id:
                _fail("W2C population recovery predecessor chain is cyclic or gapped")
            validate_predecessor(row, receipts_by_id[predecessor_key])
            cursor = predecessor_key
        else:
            cursor = None

    unheaded_ids = set(receipts_by_id) - reached
    if not unheaded_ids:
        return current
    if not recover_unheaded:
        _fail("W2C population recovery requires the locked writer")
    if len(unheaded_ids) != 1:
        _fail("W2C population recovery found multiple or branched descendants")
    candidate = receipts_by_id[unheaded_ids.pop()]
    expected_predecessor_id = (
        str(current["population_receipt_id"])
        if current is not None
        else None
    )
    if candidate["previous_population_receipt_id"] != expected_predecessor_id:
        _fail("W2C population recovery found a noncontiguous descendant")
    if current is not None:
        validate_predecessor(candidate, current)
        if _same_population_state(candidate, current):
            _fail("W2C population recovery found a redundant descendant")
    candidate_body = receipt_bodies_by_id[
        str(candidate["population_receipt_id"])
    ]
    candidate_head = {
        "schema": POPULATION_HEAD_SCHEMA,
        "population_receipt_id": candidate["population_receipt_id"],
        "population_receipt_sha256": _digest(candidate_body),
        "population_receipt_bytes": len(candidate_body),
    }
    _replace_head(
        _safe_path(root, "population_HEAD.json"),
        _canonical_bytes(candidate_head),
    )
    return candidate


def _owner_pins_from_population_receipt(
    receipt: Mapping[str, Any],
) -> tuple[OwnerPins, str]:
    """Preserve the last stable pair when the terminal owner window is missed."""

    refs = receipt.get("owner_generation_refs")
    if not isinstance(refs, Mapping):
        _fail("W2C terminal fallback lacks stable population owner refs")
    trusted_ref = _validate_generation_ref(
        refs.get("trusted_generation"), technical=False
    )
    technical_ref = _validate_generation_ref(
        refs.get("technical_generation"), technical=True
    )

    def pin(value: Mapping[str, Any]) -> _ReferenceGenerationPin:
        return _ReferenceGenerationPin(
            profile=str(value["profile"]),
            store_id=str(value["store_id"]),
            generation_id=str(value["generation_id"]),
            generation_sha256=str(value["generation_sha256"]),
            captures=(None,) * int(value["capture_count"]),
        )

    pin_observed_at = refs.get("pin_observed_at")
    _parse_utc(pin_observed_at, field="last stable population owner pin")
    return (
        OwnerPins(trusted=pin(trusted_ref), technical=pin(technical_ref)),
        str(pin_observed_at),
    )


def _owner_pins_from_opportunities(
    opportunities: list[dict[str, Any]],
) -> tuple[OwnerPins, str] | None:
    """Recover the last durable owner pair when population write never ran."""

    durable_pairs: list[tuple[datetime, Mapping[str, Any]]] = []
    for opportunity in opportunities:
        refs = opportunity.get("source_pins")
        if not isinstance(refs, Mapping):
            continue
        durable_pairs.append(
            (
                _parse_utc(
                    refs.get("pin_observed_at"),
                    field="opportunity fallback owner pin",
                ),
                refs,
            )
        )
    if not durable_pairs:
        return None
    pin_clock, refs = max(durable_pairs, key=lambda item: item[0])
    trusted_ref = _validate_generation_ref(
        refs.get("trusted_generation"), technical=False
    )
    technical_ref = _validate_generation_ref(
        refs.get("technical_generation"), technical=True
    )

    def pin(value: Mapping[str, Any]) -> _ReferenceGenerationPin:
        return _ReferenceGenerationPin(
            profile=str(value["profile"]),
            store_id=str(value["store_id"]),
            generation_id=str(value["generation_id"]),
            generation_sha256=str(value["generation_sha256"]),
            captures=(None,) * int(value["capture_count"]),
        )

    return (
        OwnerPins(trusted=pin(trusted_ref), technical=pin(technical_ref)),
        _format_utc(pin_clock),
    )


def _owner_pins_from_technical_view_head(
    root: Path, *, registration: Registration
) -> tuple[OwnerPins, str] | None:
    """Recover the last durable pair cached before opportunity publication."""
    view = _recover_technical_view_chain_head(
        root, registration=registration, pin=None
    )
    if view is None:
        return None

    def pin(value: Mapping[str, Any]) -> _ReferenceGenerationPin:
        return _ReferenceGenerationPin(
            profile=str(value["profile"]),
            store_id=str(value["store_id"]),
            generation_id=str(value["generation_id"]),
            generation_sha256=str(value["generation_sha256"]),
            captures=(None,) * int(value["capture_count"]),
        )

    return (
        OwnerPins(
            trusted=pin(view["trusted_generation"]),
            technical=pin(view["technical_generation"]),
        ),
        str(view["pair_observed_at"]),
    )


def _same_population_state(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    def state(value: Mapping[str, Any]) -> dict[str, Any]:
        clean = copy.deepcopy(dict(value))
        clean.pop("population_receipt_id", None)
        clean.pop("previous_population_receipt_id", None)
        clean.pop("observed_at", None)
        clean.pop("writer_commit", None)
        refs = clean.get("owner_generation_refs")
        if isinstance(refs, dict):
            refs.pop("pin_observed_at", None)
        return clean

    return state(left) == state(right)


def _terminal_marker_path(root: Path) -> Path:
    return _safe_path(root, "TERMINAL.json")


def _validate_terminal_marker(
    value: Mapping[str, Any], *, registration: Registration, root: Path
) -> dict[str, Any]:
    fields = {
        "schema", "terminal_marker_id", "registration_id",
        "registration_sha256", "population_receipt_id",
        "population_receipt_sha256", "population_receipt_bytes", "sealed_at",
        "claims", "authority",
    }
    clean = _freeze_json_native(value, label="W2C terminal marker")
    if type(clean) is not dict or set(clean) != fields:
        _fail("W2C terminal marker fields are not canonical")
    if (
        clean.get("schema") != TERMINAL_MARKER_SCHEMA
        or clean.get("registration_id") != registration.registration_id
        or clean.get("registration_sha256") != registration.content_sha256
        or clean.get("claims") != _population_claims()
        or clean.get("authority") != dict(market_memory.AUTHORITY)
    ):
        _fail("W2C terminal marker binding drift")
    receipt_id = clean.get("population_receipt_id")
    if type(receipt_id) is not str or not _POPULATION_ID.fullmatch(receipt_id):
        _fail("W2C terminal population receipt ID is malformed")
    receipt_raw, receipt_body = _read_json_path(
        _safe_path(root, "population_receipts", f"{receipt_id}.json"),
        limit=_MAX_POPULATION_BYTES,
        label="W2C terminal population receipt",
    )
    if (
        _require_digest(
            clean.get("population_receipt_sha256"),
            field="terminal population receipt",
        )
        != _digest(receipt_body)
        or clean.get("population_receipt_bytes") != len(receipt_body)
        or receipt_raw.get("population_receipt_id") != receipt_id
        or receipt_raw.get("registration_id") != registration.registration_id
        or receipt_raw.get("registration_sha256") != registration.content_sha256
        or receipt_raw.get("terminal", {}).get("status") != "sealed"
        or receipt_raw.get("complete") is not True
        or receipt_raw.get("claims") != _population_claims()
        or _content_id(
            "mmspyexppop_", receipt_raw, field="population_receipt_id"
        )
        != receipt_id
    ):
        _fail("W2C terminal marker does not bind one final population receipt")
    sealed_at = _parse_utc(clean.get("sealed_at"), field="terminal sealed_at")
    receipt_observed = _parse_utc(
        receipt_raw.get("observed_at"), field="terminal population observed_at"
    )
    if sealed_at != receipt_observed:
        _fail("W2C terminal marker clock differs from its population receipt")
    marker_id = clean.get("terminal_marker_id")
    if type(marker_id) is not str or not _TERMINAL_ID.fullmatch(marker_id):
        _fail("W2C terminal marker ID is malformed")
    if _content_id("mmspyexpterminal_", clean, field="terminal_marker_id") != marker_id:
        _fail("W2C terminal marker ID does not bind its content")
    return clean


def _load_terminal_marker(
    root: Path, *, registration: Registration
) -> dict[str, Any] | None:
    path = _terminal_marker_path(root)

    def validate(raw: dict[str, Any], _body: bytes) -> dict[str, Any]:
        return _validate_terminal_marker(
            raw, registration=registration, root=root
        )

    return _recover_immutable_json(
        path,
        limit=_MAX_TERMINAL_BYTES,
        label="W2C terminal marker",
        validator=validate,
    )


def _read_terminal_marker_without_recovery(
    root: Path, *, registration: Registration
) -> dict[str, Any] | None:
    """Read a final marker without replaying or removing pending state."""

    path = _terminal_marker_path(root)
    if not (path.exists() or path.is_symlink()):
        return None
    raw, _body = _read_json_path(
        path, limit=_MAX_TERMINAL_BYTES, label="W2C terminal marker"
    )
    return _validate_terminal_marker(
        raw, registration=registration, root=root
    )


def _write_terminal_marker(
    root: Path,
    *,
    registration: Registration,
    population_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if population_receipt.get("terminal", {}).get("status") != "sealed":
        _fail("W2C cannot publish a terminal marker for an open census")
    population_body = _canonical_bytes(population_receipt)
    value: dict[str, Any] = {
        "schema": TERMINAL_MARKER_SCHEMA,
        "terminal_marker_id": "",
        "registration_id": registration.registration_id,
        "registration_sha256": registration.content_sha256,
        "population_receipt_id": population_receipt["population_receipt_id"],
        "population_receipt_sha256": _digest(population_body),
        "population_receipt_bytes": len(population_body),
        "sealed_at": population_receipt["observed_at"],
        "claims": _population_claims(),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["terminal_marker_id"] = _content_id(
        "mmspyexpterminal_", value, field="terminal_marker_id"
    )
    clean = _validate_terminal_marker(value, registration=registration, root=root)
    _write_create_once(
        _terminal_marker_path(root),
        _canonical_bytes(clean),
        limit=_MAX_TERMINAL_BYTES,
        label="W2C terminal marker",
    )
    return clean


def _recover_terminal_marker_if_ready(
    root: Path, *, registration: Registration
) -> dict[str, Any] | None:
    """Finish final population -> marker publication under writer.lock."""

    population_head_path = _safe_path(root, "population_HEAD.json")
    population_receipts_directory = _safe_path(root, "population_receipts")
    try:
        has_population_receipt = (
            population_receipts_directory.exists()
            and any(population_receipts_directory.iterdir())
        )
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C terminal population recovery inventory cannot be read"
        ) from exc
    if not (
        population_head_path.exists()
        or population_head_path.is_symlink()
        or _pending_create_paths(population_head_path)
        or has_population_receipt
    ):
        return None

    sessions = nyse_calendar.sessions_between(
        ACTIVATION_SESSION, SUNSET_SESSION
    )
    opportunities: list[dict[str, Any]] = []
    for session in sessions:
        row = _load_opportunity(
            root, registration=registration, session=session
        )
        if row is None:
            return None
        opportunities.append(row)
    current = _current_population_receipt(
        root,
        registration=registration,
        expected_sessions=sessions,
        opportunities=opportunities,
        recover_unheaded=True,
    )
    if current is None or current.get("terminal", {}).get("status") != "sealed":
        return None
    if current.get("owner_generation_refs") is None:
        pins = None
        pin_observed_at = None
    else:
        pins, pin_observed_at = _owner_pins_from_population_receipt(current)
    recomputed = _new_population_receipt(
        registration,
        root=root,
        expected_sessions=sessions,
        opportunities=opportunities,
        owner_pins=pins,
        owner_pin_observed_at=pin_observed_at,
        terminal_receipt=current["terminal"]["receipt"],
        observed_at=current["observed_at"],
        writer_commit=current["writer_commit"],
        previous_population_receipt_id=current[
            "previous_population_receipt_id"
        ],
    )
    if _canonical_bytes(recomputed) != _canonical_bytes(current):
        _fail("W2C sealed terminal population differs from its immutable ledger")
    existing = _load_terminal_marker(root, registration=registration)
    if existing is not None:
        return existing
    return _write_terminal_marker(
        root, registration=registration, population_receipt=current
    )


def _authenticate_terminal_ledger(
    root: Path,
    *,
    registration: Registration,
    marker: Mapping[str, Any],
) -> dict[str, Any]:
    """Read-only authentication of the complete finite W2C store closure."""

    expected_top_level = {
        "TERMINAL.json", "manifest.json", "population_HEAD.json",
        "population_receipts", "prepared_objects", "prepared_sessions",
        "opportunities", "outcomes", "registration_installation.json",
        "technical_views", "writer.lock",
    }
    optional_top_level = {"technical_view_HEAD.json"}
    try:
        top_entries = {entry.name: entry for entry in root.iterdir()}
    except OSError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C terminal store inventory cannot be read"
        ) from exc
    if not expected_top_level.issubset(top_entries) or (
        set(top_entries) - expected_top_level - optional_top_level
    ):
        _fail("W2C terminal store inventory is missing or contains an orphan")
    directory_names = {
        "population_receipts", "prepared_objects", "prepared_sessions",
        "opportunities", "outcomes", "technical_views",
    }
    for name, entry in top_entries.items():
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _fail("W2C terminal store inventory contains a symlink")
        if name in directory_names:
            if not stat.S_ISDIR(metadata.st_mode):
                _fail("W2C terminal store inventory directory drift")
        elif not stat.S_ISREG(metadata.st_mode):
            _fail("W2C terminal store inventory file drift")
        if ".pending" in name or name.startswith("."):
            _fail("W2C terminal store inventory contains pending state")
    lock_metadata = top_entries["writer.lock"].stat()
    if lock_metadata.st_size != 0:
        _fail("W2C terminal writer lock is not empty")

    installation_raw, _ = _read_json_path(
        _safe_path(root, "registration_installation.json"),
        limit=_MAX_INSTALLATION_BYTES,
        label="W2C terminal installation receipt",
    )
    installation = _validate_installation(
        installation_raw, registration=registration
    )
    manifest_raw, _ = _read_json_path(
        _safe_path(root, "manifest.json"),
        limit=_MAX_MANIFEST_BYTES,
        label="W2C terminal manifest",
    )
    _validate_manifest(
        manifest_raw, registration=registration, installation=installation
    )

    sessions = nyse_calendar.sessions_between(
        ACTIVATION_SESSION, SUNSET_SESSION
    )
    opportunity_directory = _safe_path(root, "opportunities")
    opportunity_names = sorted(item.name for item in opportunity_directory.iterdir())
    expected_opportunity_names = [f"{session.isoformat()}.json" for session in sessions]
    if opportunity_names != expected_opportunity_names:
        _fail("W2C terminal opportunity inventory is not the exact denominator")
    opportunities: list[dict[str, Any]] = []
    for session in sessions:
        row = _load_opportunity(root, registration=registration, session=session)
        if row is None:
            _fail("W2C terminal opportunity ledger is incomplete")
        opportunities.append(row)

    technical_reference_facts: dict[str, dict[str, Any]] = {}
    technical_progress_facts: dict[str, str] = {}
    technical_generation_facts: dict[str, dict[str, Any]] = {}
    technical_generation_capture_facts: set[tuple[str, str]] = set()
    population_owner_ref_facts: list[dict[str, Any]] = []
    outcome_chains_by_opportunity_id: dict[str, list[dict[str, Any]]] = {}

    def record_technical_generation(
        generation: Mapping[str, Any], *, label: str
    ) -> str:
        generation_id = str(generation["generation_id"])
        frozen = copy.deepcopy(dict(generation))
        prior = technical_generation_facts.get(generation_id)
        if prior is not None and prior != frozen:
            _fail(f"W2C terminal {label} rewrites one technical generation")
        technical_generation_facts[generation_id] = frozen
        return generation_id

    def record_technical_reference(
        reference: Mapping[str, Any], *, label: str
    ) -> None:
        capture_id = str(reference["capture_id"])
        frozen = copy.deepcopy(dict(reference))
        prior = technical_reference_facts.get(capture_id)
        if prior is not None and prior != frozen:
            _fail(f"W2C terminal {label} rewrites one technical capture")
        technical_reference_facts[capture_id] = frozen

    for row in opportunities:
        source_pins = row.get("source_pins")
        technical_capture = (
            source_pins.get("technical_capture")
            if isinstance(source_pins, Mapping)
            else None
        )
        technical_generation_id = None
        if isinstance(source_pins, Mapping):
            technical_generation_id = record_technical_generation(
                source_pins["technical_generation"],
                label="opportunity generation",
            )
        if technical_capture is not None:
            record_technical_reference(
                technical_capture, label="opportunity reference"
            )
            technical_generation_capture_facts.add(
                (
                    str(technical_generation_id),
                    str(technical_capture["capture_id"]),
                )
            )

    prepared_session_directory = _safe_path(root, "prepared_sessions")
    prepared_session_names = sorted(
        item.name for item in prepared_session_directory.iterdir()
    )
    expected_prepared_sessions = sorted(
        f"{row['session']}.json"
        for row in opportunities if row["disposition"] != "missed"
    )
    if prepared_session_names != expected_prepared_sessions:
        _fail("W2C terminal prepared-seal inventory is orphaned or incomplete")
    referenced_prepared_ids: set[str] = set()
    for row in opportunities:
        if row["disposition"] == "missed":
            continue
        session = date.fromisoformat(row["session"])
        sealed = _load_prepared_seal(
            root, registration=registration, session=session
        )
        if sealed is None:
            _fail("W2C terminal timely opportunity lacks its prepared seal")
        seal, prepared = sealed
        expected_row = _opportunity_from_prepared(
            registration, seal=seal, prepared=prepared
        )
        if _canonical_bytes(expected_row) != _canonical_bytes(row):
            _fail("W2C terminal opportunity differs from its prepared seal")
        referenced_prepared_ids.add(str(prepared["prepared_id"]))
    prepared_object_names = sorted(
        item.name for item in _safe_path(root, "prepared_objects").iterdir()
    )
    if prepared_object_names != sorted(
        f"{prepared_id}.json" for prepared_id in referenced_prepared_ids
    ):
        _fail("W2C terminal prepared-object inventory contains an orphan")

    admitted_ids = {
        row["opportunity_id"]
        for row in opportunities if row["disposition"] == "admitted"
    }
    outcome_directory = _safe_path(root, "outcomes")
    outcome_names = sorted(item.name for item in outcome_directory.iterdir())
    if outcome_names != sorted(admitted_ids):
        _fail("W2C terminal outcome inventory differs from admitted episodes")
    for row in opportunities:
        if row["disposition"] != "admitted":
            continue
        episode_directory = _outcome_directory(
            root, str(row["opportunity_id"])
        )
        try:
            episode_entries = sorted(episode_directory.iterdir())
        except OSError as exc:
            raise MarketMemoryExperienceStoreError(
                "W2C terminal outcome inventory cannot be read"
            ) from exc
        if not episode_entries:
            _fail("W2C terminal admitted episode lacks a maturity receipt")
        expected_revision_names = [
            f"{number:06d}.json"
            for number in range(1, len(episode_entries) + 1)
        ]
        if [item.name for item in episode_entries] != expected_revision_names:
            _fail("W2C terminal outcome inventory is gapped or contains pending state")
        for item in episode_entries:
            metadata = item.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                _fail("W2C terminal outcome inventory contains a non-regular artifact")
        chain = _load_outcome_chain(
            root, registration=registration, opportunity=row
        )
        if not chain:
            _fail("W2C terminal admitted episode lacks a maturity receipt")
        outcome_chains_by_opportunity_id[str(row["opportunity_id"])] = chain
        for revision in chain:
            target_generation_pin = revision.get("target_generation_pin")
            target_generation_id = None
            if isinstance(target_generation_pin, Mapping):
                target_generation_id = record_technical_generation(
                    {
                        key: target_generation_pin[key]
                        for key in (
                            "profile", "store_id", "generation_id",
                            "generation_sha256", "capture_count",
                        )
                    },
                    label="outcome generation",
                )
            target_capture = revision.get("target_capture")
            if target_capture is not None:
                record_technical_reference(
                    target_capture, label="outcome reference"
                )
                technical_generation_capture_facts.add(
                    (
                        str(target_generation_id),
                        str(target_capture["capture_id"]),
                    )
                )
            progress = revision.get("target_generation_progress")
            if not isinstance(progress, Mapping):
                continue
            for capture_id in progress["consumed_capture_ids"]:
                technical_progress_facts.setdefault(str(capture_id), "")
                technical_generation_capture_facts.add(
                    (str(target_generation_id), str(capture_id))
                )
            for group_row in progress["current_group"]:
                capture_id = str(group_row["capture_id"])
                first_observed_at = str(group_row["first_observed_at"])
                prior_clock = technical_progress_facts.get(capture_id)
                if prior_clock not in {None, "", first_observed_at}:
                    _fail("W2C terminal outcome progress rewrites an owner clock")
                technical_progress_facts[capture_id] = first_observed_at

    population_directory = _safe_path(root, "population_receipts")
    population_files = sorted(population_directory.iterdir())
    if not population_files or any(
        not re.fullmatch(r"mmspyexppop_[a-f0-9]{64}\.json", item.name)
        or not stat.S_ISREG(item.lstat().st_mode)
        for item in population_files
    ):
        _fail("W2C terminal population inventory is noncanonical")
    opportunity_by_session = {row["session"]: row for row in opportunities}
    population_ids: set[str] = set()
    population_by_id: dict[str, dict[str, Any]] = {}
    for item in population_files:
        raw, _ = _read_json_path(
            item,
            limit=_MAX_POPULATION_BYTES,
            label="W2C terminal population receipt",
        )
        raw_sessions = raw.get("expected_sessions")
        if type(raw_sessions) is not list:
            _fail("W2C terminal population receipt lacks its denominator")
        try:
            receipt_sessions = [date.fromisoformat(value) for value in raw_sessions]
        except (TypeError, ValueError) as exc:
            raise MarketMemoryExperienceStoreError(
                "W2C terminal population denominator is malformed"
            ) from exc
        if receipt_sessions != sessions[:len(receipt_sessions)]:
            _fail("W2C terminal population denominator is not a pilot prefix")
        receipt_opportunities = [
            opportunity_by_session[session.isoformat()]
            for session in receipt_sessions
            if session.isoformat() in opportunity_by_session
        ]
        clean = validate_population_receipt(
            raw,
            registration=registration,
            expected_sessions=receipt_sessions,
            opportunities=receipt_opportunities,
        )
        if item.name != f"{clean['population_receipt_id']}.json":
            _fail("W2C terminal population filename differs from its ID")
        if clean.get("owner_generation_refs") is None:
            receipt_pins = None
            receipt_pin_observed_at = None
        else:
            population_owner_ref_facts.append(
                copy.deepcopy(dict(clean["owner_generation_refs"]))
            )
            record_technical_generation(
                clean["owner_generation_refs"]["technical_generation"],
                label="population generation",
            )
            receipt_pins, receipt_pin_observed_at = (
                _owner_pins_from_population_receipt(clean)
            )
        recomputed_receipt = _new_population_receipt(
            registration,
            root=root,
            expected_sessions=receipt_sessions,
            opportunities=receipt_opportunities,
            owner_pins=receipt_pins,
            owner_pin_observed_at=receipt_pin_observed_at,
            terminal_receipt=(
                clean["terminal"]["receipt"]
                if clean["terminal"]["status"] == "sealed"
                else None
            ),
            observed_at=clean["observed_at"],
            writer_commit=clean["writer_commit"],
            previous_population_receipt_id=clean[
                "previous_population_receipt_id"
            ],
        )
        if _canonical_bytes(recomputed_receipt) != _canonical_bytes(clean):
            _fail("W2C terminal population receipt differs from its as-of ledger")
        population_ids.add(str(clean["population_receipt_id"]))
        population_by_id[str(clean["population_receipt_id"])] = clean

    current = _current_population_receipt(
        root,
        registration=registration,
        expected_sessions=sessions,
        opportunities=opportunities,
    )
    if (
        current is None
        or current["population_receipt_id"] not in population_ids
        or current["population_receipt_id"] != marker["population_receipt_id"]
        or current["terminal"]["status"] != "sealed"
        or current["complete"] is not True
    ):
        _fail("W2C terminal population HEAD/marker closure drift")
    reached_population_ids: set[str] = set()
    cursor: str | None = str(current["population_receipt_id"])
    while cursor is not None:
        if cursor in reached_population_ids or cursor not in population_by_id:
            _fail("W2C terminal population predecessor chain is cyclic or gapped")
        reached_population_ids.add(cursor)
        descendant = population_by_id[cursor]
        predecessor = descendant["previous_population_receipt_id"]
        if predecessor is not None:
            predecessor_id = str(predecessor)
            if predecessor_id not in population_by_id:
                _fail("W2C terminal population predecessor chain is cyclic or gapped")
            predecessor_receipt = population_by_id[predecessor_id]
            predecessor_sessions = predecessor_receipt["expected_sessions"]
            descendant_sessions = descendant["expected_sessions"]
            if (
                _parse_utc(
                    descendant["observed_at"],
                    field="population descendant observed_at",
                )
                <= _parse_utc(
                    predecessor_receipt["observed_at"],
                    field="population predecessor observed_at",
                )
                or len(descendant_sessions) < len(predecessor_sessions)
                or descendant_sessions[:len(predecessor_sessions)]
                != predecessor_sessions
                or predecessor_receipt["terminal"]["status"] == "sealed"
            ):
                _fail("W2C terminal population predecessor semantics drift")
        cursor = str(predecessor) if predecessor is not None else None
    if reached_population_ids != population_ids:
        _fail("W2C terminal population inventory contains an orphan receipt")

    if current.get("owner_generation_refs") is None:
        pins = None
        pin_observed_at = None
    else:
        pins, pin_observed_at = _owner_pins_from_population_receipt(current)
    recomputed = _new_population_receipt(
        registration,
        root=root,
        expected_sessions=sessions,
        opportunities=opportunities,
        owner_pins=pins,
        owner_pin_observed_at=pin_observed_at,
        terminal_receipt=current["terminal"]["receipt"],
        observed_at=current["observed_at"],
        writer_commit=current["writer_commit"],
        previous_population_receipt_id=current[
            "previous_population_receipt_id"
        ],
    )
    if _canonical_bytes(recomputed) != _canonical_bytes(current):
        _fail("W2C terminal population differs from its exact immutable ledger")

    technical_view_directory = _safe_path(root, "technical_views")
    technical_view_ids: set[str] = set()
    technical_views_by_id: dict[str, dict[str, Any]] = {}
    technical_views_by_generation_id: dict[str, list[dict[str, Any]]] = {}
    view_generation_refs_by_kind: dict[str, dict[str, dict[str, Any]]] = {
        "trusted_generation": {},
        "technical_generation": {},
    }
    for item in sorted(technical_view_directory.iterdir()):
        if not re.fullmatch(r"mmspyexptechview_[a-f0-9]{64}\.json", item.name):
            _fail("W2C terminal technical-view inventory is noncanonical")
        raw, _ = _read_json_path(
            item,
            limit=_MAX_TECHNICAL_VIEW_BYTES,
            label="W2C terminal technical view",
        )
        clean = _validate_technical_view(raw, registration=registration)
        if item.name != f"{clean['technical_view_id']}.json":
            _fail("W2C terminal technical-view filename differs from its ID")
        generation_id = str(clean["technical_generation"]["generation_id"])
        for kind, refs_by_id in view_generation_refs_by_kind.items():
            generation = clean[kind]
            owner_generation_id = str(generation["generation_id"])
            prior_generation = refs_by_id.get(owner_generation_id)
            if prior_generation is not None and prior_generation != generation:
                _fail("W2C terminal technical views rewrite a generation identity")
            refs_by_id[owner_generation_id] = generation
        technical_view_ids.add(str(clean["technical_view_id"]))
        technical_views_by_id[str(clean["technical_view_id"])] = clean
        technical_views_by_generation_id.setdefault(generation_id, []).append(
            clean
        )
    technical_head_path = _technical_view_head_path(root)
    if technical_head_path.exists() or technical_head_path.is_symlink():
        head, _ = _read_json_path(
            technical_head_path,
            limit=_MAX_HEAD_BYTES,
            label="W2C terminal technical-view HEAD",
        )
        if (
            type(head) is not dict
            or set(head) != {
                "schema", "technical_view_id", "technical_view_sha256",
                "technical_view_bytes", "technical_generation_id",
            }
            or head.get("schema") != TECHNICAL_VIEW_HEAD_SCHEMA
            or head.get("technical_view_id") not in technical_view_ids
            or type(head.get("technical_view_bytes")) is not int
            or not (
                1
                <= head["technical_view_bytes"]
                <= _MAX_TECHNICAL_VIEW_BYTES
            )
        ):
            _fail("W2C terminal technical-view HEAD is not canonical")
        _require_digest(
            head.get("technical_view_sha256"),
            field="terminal technical-view HEAD",
        )
        view_body = _read_bounded(
            _safe_path(root, "technical_views", f"{head['technical_view_id']}.json"),
            limit=_MAX_TECHNICAL_VIEW_BYTES,
            label="W2C terminal technical-view HEAD target",
        )
        if (
            _digest(view_body) != head.get("technical_view_sha256")
            or len(view_body) != head.get("technical_view_bytes")
        ):
            _fail("W2C terminal technical-view HEAD target drift")
        head_view = technical_views_by_id[str(head["technical_view_id"])]
        if (
            head.get("technical_generation_id")
            != head_view["technical_generation"]["generation_id"]
        ):
            _fail("W2C terminal technical-view HEAD generation drift")
        owner_generation_refs = current.get("owner_generation_refs")
        if (
            owner_generation_refs is None
            and not technical_generation_facts
        ):
            _fail("W2C terminal technical-view chain has no ledger owner reference")
        if owner_generation_refs is not None and (
            head_view["technical_generation"]
            != owner_generation_refs["technical_generation"]
            or head_view["trusted_generation"]
            != owner_generation_refs["trusted_generation"]
            or _parse_utc(
                head_view["pair_observed_at"],
                field="technical-view HEAD owner pair",
            )
            > _parse_utc(
                owner_generation_refs["pin_observed_at"],
                field="population owner pair",
            )
        ):
            _fail("W2C terminal technical-view HEAD differs from population owner refs")
        reached_view_ids: set[str] = set()
        cursor = str(head["technical_view_id"])
        descendant: dict[str, Any] | None = None
        technical_generation_history: list[str] = []
        trusted_generation_history: list[str] = []
        while cursor is not None:
            if cursor in reached_view_ids or cursor not in technical_views_by_id:
                _fail("W2C terminal technical-view chain is cyclic or gapped")
            reached_view_ids.add(cursor)
            view = technical_views_by_id[cursor]
            if descendant is not None:
                predecessor_rows = view["captures"]
                descendant_rows = descendant["captures"]
                descendant_by_capture_id = {
                    str(row["index"]["capture_id"]): row
                    for row in descendant_rows
                }
                if (
                    descendant["technical_generation"]["profile"]
                    != view["technical_generation"]["profile"]
                    or descendant["technical_generation"]["store_id"]
                    != view["technical_generation"]["store_id"]
                    or descendant["trusted_generation"]["profile"]
                    != view["trusted_generation"]["profile"]
                    or descendant["trusted_generation"]["store_id"]
                    != view["trusted_generation"]["store_id"]
                    or descendant["trusted_generation"]["capture_count"]
                    < view["trusted_generation"]["capture_count"]
                    or _parse_utc(
                        descendant["pair_observed_at"],
                        field="technical-view descendant owner pair",
                    )
                    < _parse_utc(
                        view["pair_observed_at"],
                        field="technical-view predecessor owner pair",
                    )
                    or len(descendant_rows) < len(predecessor_rows)
                    or any(
                        descendant_by_capture_id.get(
                            str(row["index"]["capture_id"])
                        )
                        != row
                        for row in predecessor_rows
                    )
                ):
                    _fail("W2C terminal technical-view chain rewrites its immutable capture set")
            technical_generation_history.append(
                str(view["technical_generation"]["generation_id"])
            )
            trusted_generation_history.append(
                str(view["trusted_generation"]["generation_id"])
            )
            predecessor = view["previous_technical_view_id"]
            descendant = view
            cursor = str(predecessor) if predecessor is not None else None
        if reached_view_ids != technical_view_ids:
            _fail("W2C terminal technical-view inventory contains an orphan")
        compressed_generations = [
            generation_id
            for index, generation_id in enumerate(
                technical_generation_history
            )
            if index == 0
            or generation_id != technical_generation_history[index - 1]
        ]
        if len(compressed_generations) != len(set(compressed_generations)):
            _fail("W2C terminal technical-view chain reopens an old generation")
        compressed_trusted_generations = [
            generation_id
            for index, generation_id in enumerate(
                trusted_generation_history
            )
            if index == 0
            or generation_id != trusted_generation_history[index - 1]
        ]
        if len(compressed_trusted_generations) != len(
            set(compressed_trusted_generations)
        ):
            _fail(
                "W2C terminal technical-view chain reopens an old trusted generation"
            )
        head_rows_by_capture_id = {
            str(row["index"]["capture_id"]): row
            for row in head_view["captures"]
        }
        for capture_id, reference in technical_reference_facts.items():
            indexed = head_rows_by_capture_id.get(capture_id)
            if indexed is None or indexed["reference"] != reference:
                _fail("W2C terminal technical reference is absent from the active view")
        for capture_id, first_observed_at in technical_progress_facts.items():
            indexed = head_rows_by_capture_id.get(capture_id)
            if indexed is None or (
                first_observed_at
                and indexed["reference"]["first_observed_at"]
                != first_observed_at
            ):
                _fail("W2C terminal outcome progress is absent from the active view")
        for generation_id, generation in technical_generation_facts.items():
            generation_views = technical_views_by_generation_id.get(
                generation_id, []
            )
            if not any(
                view["technical_generation"] == generation
                for view in generation_views
            ):
                _fail("W2C terminal technical generation fact lacks its exact view")
        for generation_id, capture_id in technical_generation_capture_facts:
            generation_views = technical_views_by_generation_id.get(
                generation_id, []
            )
            if not any(
                capture_id
                in {
                    str(row["index"]["capture_id"])
                    for row in view["captures"]
                }
                for view in generation_views
            ):
                _fail("W2C terminal technical capture is absent from its pinned view")
        for opportunity in opportunities:
            if opportunity["disposition"] != "admitted":
                continue
            chain = outcome_chains_by_opportunity_id[
                str(opportunity["opportunity_id"])
            ]
            checked_pins: set[tuple[str, str]] = set()
            for revision in chain:
                target_pin = revision.get("target_generation_pin")
                if not isinstance(target_pin, Mapping):
                    continue
                pin_key = (
                    str(target_pin["generation_id"]),
                    str(target_pin["pin_observed_at"]),
                )
                if pin_key in checked_pins:
                    continue
                checked_pins.add(pin_key)
                last_generation_revision = max(
                    index
                    for index, row in enumerate(chain)
                    if isinstance(row.get("target_generation_pin"), Mapping)
                    and row["target_generation_pin"]["generation_id"]
                    == target_pin["generation_id"]
                    and row["target_generation_pin"]["pin_observed_at"]
                    == target_pin["pin_observed_at"]
                )
                generation = {
                    key: target_pin[key]
                    for key in (
                        "profile", "store_id", "generation_id",
                        "generation_sha256", "capture_count",
                    )
                }
                exact_views = [
                    view
                    for view in technical_views_by_generation_id.get(
                        str(target_pin["generation_id"]), []
                    )
                    if view["technical_generation"] == generation
                    and _parse_utc(
                        view["pair_observed_at"],
                        field="outcome generation view owner pair",
                    )
                    <= _parse_utc(
                        target_pin["pin_observed_at"],
                        field="outcome generation pin owner pair",
                    )
                ]
                if not exact_views:
                    _fail(
                        "W2C terminal outcome generation pin lacks its authenticated view"
                    )
                expected_candidate_orders = {
                    tuple(
                        str(view_row["index"]["capture_id"])
                        for view_row in view["captures"]
                        if view_row["index"]["session"]
                        == opportunity["target_session"]
                    )
                    for view in exact_views
                }
                if len(expected_candidate_orders) != 1:
                    _fail(
                        "W2C terminal exact generation views disagree on candidates"
                    )
                expected_capture_ids = set(
                    next(iter(expected_candidate_orders))
                )
                consumed_capture_ids = {
                    str(capture_id)
                    for prior in chain[:last_generation_revision + 1]
                    if isinstance(
                        prior.get("target_generation_progress"), Mapping
                    )
                    for capture_id in prior["target_generation_progress"][
                        "consumed_capture_ids"
                    ]
                }
                if consumed_capture_ids != expected_capture_ids:
                    _fail(
                        "W2C terminal outcome generation candidate census is incomplete"
                    )
        terminal_receipt = current["terminal"]["receipt"]
        if (
            terminal_receipt["disposition"]
            == "stable_terminal_generation_observed"
        ):
            terminal_pin = terminal_receipt["technical_generation_pin"]
            terminal_generation = {
                key: terminal_pin[key]
                for key in (
                    "profile", "store_id", "generation_id",
                    "generation_sha256", "capture_count",
                )
            }
            terminal_views = [
                view
                for view in technical_views_by_generation_id.get(
                    str(terminal_pin["generation_id"]), []
                )
                if view["technical_generation"] == terminal_generation
                and _parse_utc(
                    view["pair_observed_at"],
                    field="terminal generation view owner pair",
                )
                <= _parse_utc(
                    terminal_pin["pin_observed_at"],
                    field="terminal generation pin owner pair",
                )
            ]
            if not terminal_views:
                _fail(
                    "W2C stable terminal generation lacks its authenticated view"
                )
            for opportunity in opportunities:
                if opportunity["disposition"] != "admitted":
                    continue
                expected_candidate_orders = {
                    tuple(
                        str(view_row["index"]["capture_id"])
                        for view_row in view["captures"]
                        if view_row["index"]["session"]
                        == opportunity["target_session"]
                    )
                    for view in terminal_views
                }
                if len(expected_candidate_orders) != 1:
                    _fail(
                        "W2C terminal generation views disagree on candidates"
                    )
                expected_capture_ids = set(
                    next(iter(expected_candidate_orders))
                )
                chain = outcome_chains_by_opportunity_id[
                    str(opportunity["opportunity_id"])
                ]
                consumed_capture_ids = {
                    str(capture_id)
                    for revision in chain
                    if isinstance(
                        revision.get("target_generation_progress"), Mapping
                    )
                    for capture_id in revision["target_generation_progress"][
                        "consumed_capture_ids"
                    ]
                }
                if consumed_capture_ids != expected_capture_ids:
                    _fail(
                        "W2C terminal generation candidate census is incomplete"
                    )
        for refs in population_owner_ref_facts:
            pin_observed_at = _parse_utc(
                refs["pin_observed_at"],
                field="population historical owner pair",
            )
            if not any(
                view["trusted_generation"] == refs["trusted_generation"]
                and view["technical_generation"]
                == refs["technical_generation"]
                and _parse_utc(
                    view["pair_observed_at"],
                    field="technical-view historical owner pair",
                )
                <= pin_observed_at
                for view in technical_views_by_id.values()
            ):
                _fail(
                    "W2C terminal population owner refs lack their authenticated technical view"
                )
    elif technical_view_ids:
        _fail("W2C terminal technical views exist without an authenticated HEAD")
    elif (
        technical_reference_facts
        or technical_progress_facts
        or technical_generation_facts
        or technical_generation_capture_facts
    ):
        _fail("W2C terminal technical facts exist without an authenticated view")

    return current


def _read_installation_manifest(
    root: Path,
    *,
    registration: Registration,
    expected_writer_commit: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Authenticate the immutable installation closure without recovering it."""

    installation_path = _safe_path(root, "registration_installation.json")
    manifest_path = _safe_path(root, "manifest.json")
    if _pending_create_paths(installation_path) or _pending_create_paths(
        manifest_path
    ):
        _fail("W2C installation verification found pending publication state")
    try:
        installation_raw, _ = _read_json_path(
            installation_path,
            limit=_MAX_INSTALLATION_BYTES,
            label="W2C registration installation",
        )
        manifest_raw, _ = _read_json_path(
            manifest_path,
            limit=_MAX_MANIFEST_BYTES,
            label="W2C store manifest",
        )
    except FileNotFoundError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C installation verification requires both immutable receipts"
        ) from exc
    installation = _validate_installation(
        installation_raw, registration=registration
    )
    manifest = _validate_manifest(
        manifest_raw,
        registration=registration,
        installation=installation,
    )
    if expected_writer_commit is not None:
        _require_commit(expected_writer_commit)
        if installation["writer_commit"] != expected_writer_commit:
            _fail("W2C installation writer commit differs from the expected pin")
    return installation, manifest


def verify_experience_installation(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
    expected_writer_commit: str | None = None,
) -> dict[str, Any]:
    """Read-only verification of the tracked registration and install receipts.

    ``installed_at`` is intentionally only a local writer-clock observation.
    Validation authenticates that durable false-clock claim, its content ID,
    the finite capacity arithmetic, and the manifest binding.  It does not
    turn the local clock into external time authority.
    """

    registration = load_registration(repository_root)
    root = validate_experience_store_root(experience_root)
    try:
        metadata = root.lstat()
    except FileNotFoundError as exc:
        raise MarketMemoryExperienceStoreError(
            "W2C installation store does not exist"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("W2C installation store is not one real directory")
    installation, manifest = _read_installation_manifest(
        root,
        registration=registration,
        expected_writer_commit=expected_writer_commit,
    )
    return {
        "schema": "market_memory.spy_experience_installation_verification.v1",
        "registration_id": registration.registration_id,
        "installation_id": installation["installation_id"],
        "store_id": manifest["store_id"],
        "writer_commit": installation["writer_commit"],
        "installation_status": installation["installation_status"],
        "claims": copy.deepcopy(installation["claims"]),
        "capacity_preflight": copy.deepcopy(
            installation["capacity_preflight"]
        ),
        "verified": True,
    }


def verify_terminal_ledger(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
    expected_writer_commit: str | None = None,
) -> dict[str, Any] | None:
    """Read-only authenticate the finite terminal ledger, or return ``None``.

    A mere ``TERMINAL.json`` pathname is never a latch.  This entry point first
    authenticates installation provenance, rejects every pending publication,
    then recomputes the final census from the exact opportunity/outcome ledger
    without sampling clocks or reading either source owner.
    """

    registration = load_registration(repository_root)
    root = validate_experience_store_root(experience_root)
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("W2C terminal store is not one real directory")
    marker_path = _terminal_marker_path(root)
    marker_pending = _pending_create_paths(marker_path)
    if marker_pending:
        _fail("W2C terminal verification found pending marker state")
    if not (marker_path.exists() or marker_path.is_symlink()):
        return None
    installation, _manifest = _read_installation_manifest(
        root,
        registration=registration,
        expected_writer_commit=expected_writer_commit,
    )
    marker_raw, _ = _read_json_path(
        marker_path,
        limit=_MAX_TERMINAL_BYTES,
        label="W2C terminal marker",
    )
    marker = _validate_terminal_marker(
        marker_raw, registration=registration, root=root
    )
    population = _authenticate_terminal_ledger(
        root, registration=registration, marker=marker
    )
    return {
        "schema": "market_memory.spy_experience_terminal_verification.v1",
        "registration_id": registration.registration_id,
        "installation_id": installation["installation_id"],
        "terminal_marker_id": marker["terminal_marker_id"],
        "population_receipt_id": population["population_receipt_id"],
        "denominator_and_maturity_receipts_complete": population["terminal"][
            "denominator_and_maturity_receipts_complete"
        ],
        "final_source_revision_census_authenticated": population["terminal"][
            "final_source_revision_census_authenticated"
        ],
        "verified": True,
    }


def accrue_spy_experience(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
    trusted_root: str | Path,
    technical_root: str | Path,
    writer_commit: str,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> AccrualResult:
    """Install or advance the bounded W2C census through one private writer."""

    _require_commit(writer_commit)
    clock_fn = clock or _utc_now
    sleep_fn = sleeper or time_module.sleep
    registration = load_registration(repository_root)
    root = validate_experience_store_root(experience_root)

    # The immutable terminal marker is checked before owner reads, a lock open,
    # or any timestamp sample.  A completed pilot is a byte-for-byte no-op.
    if root.exists():
        marker_path = _terminal_marker_path(root)
        if (
            (marker_path.exists() or marker_path.is_symlink())
            and not _pending_create_paths(marker_path)
        ):
            terminal = _read_terminal_marker_without_recovery(
                root, registration=registration
            )
            _authenticate_terminal_ledger(
                root, registration=registration, marker=terminal
            )
            return AccrualResult(
                registration_id=registration.registration_id,
                opportunity_ids=(),
                outcome_revision_ids=(),
                population_receipt_id=str(terminal["population_receipt_id"]),
            )

    installation_path = _safe_path(root, "registration_installation.json")
    installation_exists = installation_path.exists() or installation_path.is_symlink()
    installation_pending = bool(_pending_create_paths(installation_path))
    reader: trusted_store.TrustedFileAsKnownAtReader | None = None
    initial_pins: OwnerPins | None = None
    installed_at: datetime | None = None
    if not installation_exists and not installation_pending:
        # A new pilot installation is the one phase that requires owners before
        # any W2C path exists: its exact capacity receipt is a preactivation
        # NO-GO gate, not a fact that can be inferred later.
        reader, initial_pins = _pin_owners(trusted_root, technical_root)
        _capacity_preflight(initial_pins)
        installed_at = _sample_clock(clock_fn)
        if installed_at >= datetime.combine(
            ACTIVATION_SESSION, time(), tzinfo=timezone.utc
        ):
            raise MarketMemoryExperienceAccrualError(
                "W2C pilot NO-GO: installation receipt is not live before activation; create a new registration"
            )

    _mkdir(root)
    lock_path = _safe_path(root, "writer.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    lock_metadata = os.fstat(descriptor)
    if not stat.S_ISREG(lock_metadata.st_mode) or lock_metadata.st_size != 0:
        os.close(descriptor)
        _fail("W2C writer lock is not one empty regular file")
    opportunity_ids: list[str] = []
    outcome_ids: list[str] = []
    population_id: str | None = None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _manifest, _installation = _initialize_or_load_store(
            root,
            registration=registration,
            pins=initial_pins,
            installed_at=installed_at,
            writer_commit=writer_commit,
        )
        terminal = _load_terminal_marker(root, registration=registration)
        if terminal is None:
            terminal = _recover_terminal_marker_if_ready(
                root, registration=registration
            )
        if terminal is not None:
            _authenticate_terminal_ledger(
                root, registration=registration, marker=terminal
            )
            return AccrualResult(
                registration_id=registration.registration_id,
                opportunity_ids=(),
                outcome_revision_ids=(),
                population_receipt_id=str(terminal["population_receipt_id"]),
            )
        now = _sample_clock(clock_fn)
        due = expected_sessions_due(now)
        if not due:
            return AccrualResult(
                registration_id=registration.registration_id,
                opportunity_ids=(),
                outcome_revision_ids=(),
                population_receipt_id=None,
            )
        activation_preflight_required = not (
            _capture_bearing_admission_exists_without_recovery(
                root, registration=registration
            )
        )
        terminal_opened, terminal_deadline = _terminal_window()
        recovered_run_view = (
            _recover_last_registered_run_view(
                root, registration=registration
            )
            if now > terminal_deadline
            else None
        )
        run_view = recovered_run_view or _observe_run_owner_view(
                root,
                registration=registration,
                reader=reader,
                initial_pins=initial_pins,
                trusted_root=trusted_root,
                technical_root=technical_root,
                clock=clock_fn,
                retry_deadline=_active_retry_deadline(now),
                sleeper=sleep_fn,
                require_capacity_preflight=activation_preflight_required,
            )
        _cleanup_unsealed_prepared_staging(
            root, registration=registration
        )
        run_pin_time = _parse_utc(
            run_view.pin_observed_at, field="run owner view pin"
        )
        decision_now = max(now, run_pin_time)
        opportunities: list[dict[str, Any]] = []
        for session in due:
            existing = _load_opportunity(
                root, registration=registration, session=session
            )
            if existing is None:
                sealed = _load_prepared_seal(
                    root, registration=registration, session=session
                )
                if sealed is not None:
                    seal, prepared = sealed
                    existing = _opportunity_from_prepared(
                        registration, seal=seal, prepared=prepared
                    )
                    _write_opportunity(root, existing)
                    opportunity_ids.append(existing["opportunity_id"])
                else:
                    opened, deadline = _window(session)
                    if decision_now > deadline:
                        miss_reason = (
                            run_view.failure_reason
                            or "owner_pair_not_stable_by_deadline"
                            if not run_view.stable
                            else "not_sealed_by_deadline"
                        )
                        existing = _missed_opportunity(
                            registration,
                            session=session,
                            reconciled_at=decision_now,
                            writer_commit=writer_commit,
                            reason=miss_reason,
                        )
                        _write_opportunity(root, existing)
                        opportunity_ids.append(existing["opportunity_id"])
                    elif decision_now >= opened:
                        sandwich = _opportunity_sandwich_from_run(
                            run_view, session=session
                        )
                        observed = _parse_utc(
                            sandwich.sampled_at,
                            field="opportunity actual pin",
                        )
                        if not sandwich.stable:
                            if observed > deadline:
                                existing = _missed_opportunity(
                                    registration,
                                    session=session,
                                    reconciled_at=observed,
                                    writer_commit=writer_commit,
                                    reason="owner_pair_not_stable_by_deadline",
                                )
                                _write_opportunity(root, existing)
                                opportunity_ids.append(existing["opportunity_id"])
                        elif observed > deadline:
                            existing = _missed_opportunity(
                                registration,
                                session=session,
                                reconciled_at=observed,
                                writer_commit=writer_commit,
                            )
                            _write_opportunity(root, existing)
                            opportunity_ids.append(existing["opportunity_id"])
                        elif observed >= opened:
                            prepared = _new_prepared(
                                registration,
                                session=session,
                                sandwich=sandwich,
                                writer_commit=writer_commit,
                            )
                            seal = _seal_prepared(
                                root,
                                registration=registration,
                                prepared=prepared,
                                clock=clock_fn,
                            )
                            if seal is not None:
                                existing = _opportunity_from_prepared(
                                    registration, seal=seal, prepared=prepared
                                )
                                _write_opportunity(root, existing)
                                opportunity_ids.append(existing["opportunity_id"])
                            else:
                                reconciled = _sample_clock(clock_fn)
                                if reconciled <= deadline:
                                    _fail("W2C prepared seal crossed deadline without a later reconciliation clock")
                                existing = _missed_opportunity(
                                    registration,
                                    session=session,
                                    reconciled_at=reconciled,
                                    writer_commit=writer_commit,
                                )
                                _write_opportunity(root, existing)
                                opportunity_ids.append(existing["opportunity_id"])
            if existing is not None:
                opportunities.append(existing)

        outcome_now = max(decision_now, _sample_clock(clock_fn))
        for opportunity in opportunities:
            target_session = date.fromisoformat(str(opportunity["target_session"]))
            observation = _target_observation_from_run(
                run_view, target_session=target_session
            )
            if (
                recovered_run_view is None
                and outcome_now > terminal_deadline
                and _load_outcome_chain(
                root, registration=registration, opportunity=opportunity
                )
            ):
                observation = _TargetObservation(
                    pin_observed_at=_format_utc(outcome_now),
                    stable=False,
                    generation_pin=None,
                    candidates=(),
                    clock_tie=False,
                    generation_capture_ordinals={},
                    ancestry_generation_ids=(),
                )
            outcome_ids.extend(
                _accrue_outcomes(
                    root,
                    registration=registration,
                    opportunity=opportunity,
                    now=outcome_now,
                    observation=observation,
                    writer_commit=writer_commit,
                )
            )
        population_pins: OwnerPins | None = None
        population_pin_observed_at: str | None = None
        terminal_receipt: dict[str, Any] | None = None
        if run_view.stable and run_view.pins is not None:
            population_pins = run_view.pins
            population_pin_observed_at = run_view.pin_observed_at
            if outcome_now >= terminal_opened:
                if terminal_opened <= run_pin_time <= terminal_deadline:
                    terminal_pin = _target_observation_from_run(
                        run_view, target_session=FINAL_TARGET_SESSION
                    ).generation_pin
                    terminal_receipt = {
                        "disposition": "stable_terminal_generation_observed",
                        "observed_at": run_view.pin_observed_at,
                        "technical_generation_pin": terminal_pin,
                    }
                elif outcome_now > terminal_deadline:
                    terminal_receipt = {
                        "disposition": "terminal_owner_window_missed",
                        "observed_at": _format_utc(outcome_now),
                        "technical_generation_pin": None,
                    }
        elif outcome_now > terminal_deadline:
            previous_population = _current_population_receipt(
                root,
                registration=registration,
                expected_sessions=due,
                opportunities=opportunities,
                recover_unheaded=True,
            )
            if previous_population is None:
                opportunity_pair = _owner_pins_from_opportunities(
                    opportunities
                )
                technical_view_pair = _owner_pins_from_technical_view_head(
                    root, registration=registration
                )
                if technical_view_pair is not None and (
                    opportunity_pair is None
                    or _parse_utc(
                        technical_view_pair[1],
                        field="technical-view fallback owner pair",
                    )
                    > _parse_utc(
                        opportunity_pair[1],
                        field="opportunity fallback owner pair",
                    )
                ):
                    opportunity_pair = technical_view_pair
                if opportunity_pair is None:
                    terminal_receipt = {
                        "disposition": "no_authenticated_owner_pair_ever",
                        "observed_at": _format_utc(outcome_now),
                        "technical_generation_pin": None,
                    }
                else:
                    population_pins, population_pin_observed_at = (
                        opportunity_pair
                    )
                    terminal_receipt = {
                        "disposition": "terminal_owner_window_missed",
                        "observed_at": _format_utc(outcome_now),
                        "technical_generation_pin": None,
                    }
            else:
                (
                    population_pins,
                    population_pin_observed_at,
                ) = _owner_pins_from_population_receipt(previous_population)
                terminal_receipt = {
                    "disposition": "terminal_owner_window_missed",
                    "observed_at": _format_utc(outcome_now),
                    "technical_generation_pin": None,
                }
        if (
            population_pins is not None
            and population_pin_observed_at is not None
        ) or (
            terminal_receipt is not None
            and terminal_receipt.get("disposition")
            == "no_authenticated_owner_pair_ever"
        ):
            current_population = _current_population_receipt(
                root,
                registration=registration,
                expected_sessions=due,
                opportunities=opportunities,
                recover_unheaded=True,
            )
            # Adopt any single durable receipt whose HEAD publication crashed
            # before sampling bytes for a successor population observation.
            observed_at = _format_utc(_sample_clock(clock_fn))
            if current_population is not None and _parse_utc(
                observed_at, field="new population observed_at"
            ) < _parse_utc(
                current_population["observed_at"],
                field="current population observed_at",
            ):
                _fail(
                    "W2C changed population state lacks a strictly later writer clock"
                )
            receipt = _new_population_receipt(
                registration,
                root=root,
                expected_sessions=due,
                opportunities=opportunities,
                owner_pins=population_pins,
                owner_pin_observed_at=population_pin_observed_at,
                terminal_receipt=terminal_receipt,
                observed_at=observed_at,
                writer_commit=writer_commit,
                previous_population_receipt_id=(
                    current_population["population_receipt_id"]
                    if current_population is not None else None
                ),
            )
            if current_population is not None and _same_population_state(
                current_population, receipt
            ):
                population_id = str(current_population["population_receipt_id"])
                receipt = current_population
            else:
                if current_population is not None and _parse_utc(
                    observed_at, field="new population observed_at"
                ) <= _parse_utc(
                    current_population["observed_at"],
                    field="current population observed_at",
                ):
                    _fail(
                        "W2C changed population state lacks a strictly later writer clock"
                    )
                _write_population_receipt(root, receipt)
                population_id = receipt["population_receipt_id"]
            if receipt["terminal"]["status"] == "sealed":
                marker = _write_terminal_marker(
                    root,
                    registration=registration,
                    population_receipt=receipt,
                )
                _authenticate_terminal_ledger(
                    root, registration=registration, marker=marker
                )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return AccrualResult(
        registration_id=registration.registration_id,
        opportunity_ids=tuple(opportunity_ids),
        outcome_revision_ids=tuple(outcome_ids),
        population_receipt_id=population_id,
    )


__all__ = [
    "ACTIVATION_SESSION",
    "CORRECTION_OBSERVATION_SESSIONS",
    "CORRECTION_SUNSET_SESSION",
    "FINAL_TARGET_SESSION",
    "MAX_OWNER_GENERATION_CAPTURES",
    "MarketMemoryExperienceAccrualError",
    "MarketMemoryExperienceError",
    "MarketMemoryExperienceRegistrationError",
    "MarketMemoryExperienceStoreError",
    "OUTCOME_HORIZON_SESSIONS",
    "PILOT_EXPECTED_SESSIONS",
    "PROFILE",
    "Registration",
    "SUNSET_SESSION",
    "TERMINAL_CENSUS_DATE",
    "AccrualResult",
    "accrue_spy_experience",
    "expected_sessions_due",
    "load_registration",
    "validate_experience_store_root",
    "validate_opportunity",
    "validate_outcome_revision",
    "validate_population_receipt",
    "validate_registration",
    "verify_experience_installation",
    "verify_terminal_ledger",
]
