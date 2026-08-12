"""Private prospective exact-option NBBO cohort accrual.

This module is deliberately narrow.  It consumes an append-only, host-private
event ledger whose rows enroll or terminalize an already-selected exact OCC
contract.  It never chooses a contract, scores a signal, publishes a pick, or
grants trading authority.

For each enrollment/terminal boundary it may retain the first valid OPRA NBBO
quote at or after the boundary from ThetaData's v3 option history ``quote``
endpoint.  Raw provider responses and every durable object remain outside the
repository.  Entry uses ask, exit uses bid, and a return is computed only when
both observations satisfy the frozen ten-minute availability fence.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from engine.session_digest import session_window_et
from lib import nyse_calendar

EVENT_SCHEMA = "options.prospective_nbbo_cohort_event/v1"
OBSERVATION_SCHEMA = "options.prospective_nbbo_observation/v1"
SNAPSHOT_SCHEMA = "options.prospective_nbbo_cohort_snapshot/v1"
HEAD_SCHEMA = "options.prospective_nbbo_cohort_head/v1"
CAPTURE_SCHEMA = "options.prospective_nbbo_capture_receipt/v1"
AUTHENTICATED_EVENT_EVIDENCE_SCHEMA = "options.nbbo_authenticated_event_evidence/v1"
AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA = "options.nbbo_authenticated_capture_evidence/v1"
UNAVAILABLE_CAPTURE_EVIDENCE_SCHEMA = "options.nbbo_capture_unavailable_evidence/v1"
EXPIRY_EVENT_SOURCE_SCHEMA = "options.nbbo_expiry_liquidation_source/v1"
BENCHMARK_DIGEST = "20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42"
BENCHMARK_EFFECTIVE_FREEZE_AT = "2026-08-11T15:47:06.000000Z"
PROSPECTIVE_PHASE = "prospective_after_benchmark_freeze"
COHORT_RULE_ID = "momoedge_same_basis_opra_nbbo/v1"
QUOTE_RULE_ID = "first_role_side_firm_known_exchange_opra_nbbo_tick/v1"
SOURCE_ENDPOINT = "/v3/option/history/quote"
SOURCE_CLASS = "licensed_opra_nbbo_with_event_and_available_clocks"
SOURCE_INTERVAL = "tick"
MAX_AVAILABLE_LAG_SECONDS = 600
FEE_PER_SIDE_USD = Decimal("0.65")
MAX_EVENTS = 4096
MAX_EVENT_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_ROWS = 100_000
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_RECEIPTS = 100_000
MAX_CAPTURE_BYTES = 128 * 1024 * 1024
CAPTURE_CADENCE_SECONDS = 300
MAX_CAPTURE_GAP_SECONDS = 900
MIN_CAPTURE_COVERAGE_RATIO = Decimal("0.95")
CAPTURE_RULE_ID = "two_system_authenticated_rth_capture_300s/v1"
ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "options"
    / "options.prospective_nbbo_cohort.v1.schema.json"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_RE = re.compile(r"^[A-Z0-9]{1,6}$")
_OCC_RE = re.compile(r"^[A-Z0-9 ]{6}\d{6}[CP]\d{8}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d{1,3})?$")
_SCHEMA_VALIDATOR: Any | None = None

_QUERY_FIELDS = {
    "symbol",
    "expiration",
    "strike",
    "right",
    "date",
    "start_time",
    "end_time",
    "interval",
    "format",
}
_TERMINAL_UNAVAILABLE_REASONS = {
    "BOUNDARY_OUTSIDE_RTH",
    "QUOTE_WINDOW_CLOSED",
    "FIRST_QUOTE_AVAILABLE_TOO_LATE",
}
_EVENT_SYSTEMS = {
    "mastermindx_prophet",
    "mastermindx_selector",
    "momoedge",
}
_CAPTURE_SYSTEMS = {"mastermindx", "momoedge"}
_CAPTURE_DISPOSITIONS = {
    "new_calls_observed",
    "no_new_calls_observed",
    "selector_abstained",
    "unavailable",
}
_CAPTURE_UNAVAILABLE_REASONS = {
    "AUTHENTICATED_CAPTURE_NOT_CONFIGURED",
    "PRECISE_PRODUCER_NOT_CONFIGURED",
    "SOURCE_UNAVAILABLE",
    "PRODUCER_OUTPUT_INVALID",
    "NO_CAPTURE_RECEIPT_FOR_SLOT",
}
FIRM_OPRA_QUOTE_CONDITIONS = frozenset(
    {0, 1, 3, 4, 5, 7, 8, 12, 13, 14, 15, 16, 42, 48, 49, 50, 51, 52, 53, 54, 56}
)
KNOWN_THETA_EXCHANGES = frozenset(set(range(1, 78)) - {74, 76})

# These registries are intentionally unarmed.  Successful producer rows require
# a reviewed code change that pins all rule/source identities; an operator flag,
# environment variable, or first observed receipt can never arm them post hoc.
DEFAULT_EVENT_PRODUCER_REGISTRY: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        system: MappingProxyType(
            {
                "armed": False,
                "source_schema": None,
                "decision_rule_sha256": None,
                "lifecycle_rule_sha256": None,
                "authentication_basis": None,
            }
        )
        for system in sorted(_EVENT_SYSTEMS)
    }
)
DEFAULT_CAPTURE_PRODUCER_REGISTRY: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        system: MappingProxyType(
            {
                "armed": False,
                "source_schema": None,
                "producer_rule_sha256": None,
                "authentication_basis": None,
            }
        )
        for system in sorted(_CAPTURE_SYSTEMS)
    }
)
EVENT_PRODUCER_REGISTRY = DEFAULT_EVENT_PRODUCER_REGISTRY
CAPTURE_PRODUCER_REGISTRY = DEFAULT_CAPTURE_PRODUCER_REGISTRY

FALSE_AUTHORITY: dict[str, bool] = {
    "may_originate_signal": False,
    "may_score": False,
    "may_rank": False,
    "may_select": False,
    "may_issue": False,
    "may_size": False,
    "may_trade": False,
    "may_publish_pick": False,
    "may_train_prophet": False,
    "may_feed_neural_web": False,
    "may_claim_completion": False,
}


class NbboCohortError(ValueError):
    """A cohort input, source response, or durable object is invalid."""


class NbboSourceError(NbboCohortError):
    """The licensed quote source failed or returned a contradictory payload."""


@dataclass(frozen=True)
class SourceQuote:
    event_at: datetime
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    bid_exchange: int
    ask_exchange: int
    bid_condition: int
    ask_condition: int


@dataclass(frozen=True)
class FetchedQuoteResponse:
    """Exact private HTTP bytes paired with their strictly parsed JSON value."""

    payload: Any
    raw_body: bytes


def canonical_json_bytes(payload: object) -> bytes:
    """Return strict canonical UTF-8 JSON with one trailing newline."""
    try:
        return (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise NbboCohortError(f"payload is not strict canonical JSON: {exc}") from exc


def strict_json_value(body: bytes, *, label: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in values:
            if key in out:
                raise NbboCohortError(f"{label} has duplicate key {key!r}")
            out[key] = value
        return out

    def constant(value: str) -> None:
        raise NbboCohortError(f"{label} contains non-finite number {value}")

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NbboCohortError(f"{label} is invalid JSON: {exc}") from exc
    return value


def strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    value = strict_json_value(body, label=label)
    if not isinstance(value, dict):
        raise NbboCohortError(f"{label} root must be an object")
    return value


def _schema_validator() -> Any:
    global _SCHEMA_VALIDATOR
    if _SCHEMA_VALIDATOR is not None:
        return _SCHEMA_VALIDATOR
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        schema = strict_json_object(
            SCHEMA_PATH.read_bytes(), label="NBBO cohort schema"
        )
        Draft202012Validator.check_schema(schema)
        _SCHEMA_VALIDATOR = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
    except Exception as exc:
        raise NbboCohortError(f"NBBO cohort schema is unavailable: {exc}") from exc
    return _SCHEMA_VALIDATOR


def validate_schema(payload: Mapping[str, Any], *, label: str) -> None:
    try:
        errors = sorted(
            _schema_validator().iter_errors(dict(payload)),
            key=lambda error: "/".join(str(part) for part in error.path),
        )
    except NbboCohortError:
        raise
    except Exception as exc:
        raise NbboCohortError(f"{label} schema validation failed: {exc}") from exc
    if errors:
        summary = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise NbboCohortError(f"{label} schema validation failed: {summary}")


def _utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise NbboCohortError(f"{label} must be a UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise NbboCohortError(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise NbboCohortError(f"{label} must be UTC")
    return parsed


def effective_boundary(event: Mapping[str, Any]) -> datetime:
    """Return the frozen quote boundary: the immutable trigger/terminal clock.

    The separate event ``available_at`` clock gates when a request may begin;
    it never moves the preregistered first-quote boundary.
    """

    return _utc(event.get("event_at"), label="event_at")


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise NbboCohortError("cannot format a naive clock")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _aware_utc(value: Any, *, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise NbboCohortError(f"{label} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _session_window(session: date) -> tuple[datetime, datetime]:
    """Return the repository-governed NYSE RTH window for one session."""

    if not nyse_calendar.is_session(session):
        raise NbboCohortError(f"{session.isoformat()} is not an NYSE session")
    opened, closed = session_window_et(session)
    return opened.astimezone(timezone.utc), closed.astimezone(timezone.utc)


def _in_rth(value: datetime) -> bool:
    value = _aware_utc(value, label="RTH clock")
    session = value.astimezone(ET).date()
    if not nyse_calendar.is_session(session):
        return False
    opened, closed = _session_window(session)
    return opened <= value < closed


def _decimal(value: Any, *, label: str) -> Decimal:
    if isinstance(value, bool):
        raise NbboCohortError(f"{label} is not numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise NbboCohortError(f"{label} is not decimal") from exc
    if not parsed.is_finite():
        raise NbboCohortError(f"{label} must be finite")
    return parsed


def _canonical_strike(value: Any) -> tuple[str, int]:
    if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value):
        raise NbboCohortError("contract.strike must be a canonical decimal string")
    strike = _decimal(value, label="contract.strike")
    if strike <= 0 or strike.as_tuple().exponent < -3:
        raise NbboCohortError("contract.strike must be positive with <=3 decimals")
    millis = strike * 1000
    if millis != millis.to_integral_value() or millis > 99_999_999:
        raise NbboCohortError(
            "contract.strike cannot be represented as OCC millistrike"
        )
    canonical = format(strike.normalize(), "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    return canonical, int(millis)


def canonical_occ_symbol(
    *, root: str, expiration: str, right: str, strike_millis: int
) -> str:
    if not _ROOT_RE.fullmatch(root):
        raise NbboCohortError("contract.root is not OCC-safe")
    try:
        expiry = date.fromisoformat(expiration)
    except (TypeError, ValueError) as exc:
        raise NbboCohortError("contract.expiration is malformed") from exc
    if expiry.isoformat() != expiration:
        raise NbboCohortError("contract.expiration is not canonical")
    if right not in {"call", "put"}:
        raise NbboCohortError("contract.right must be call or put")
    if not isinstance(strike_millis, int) or isinstance(strike_millis, bool):
        raise NbboCohortError("contract.strike_millis must be an integer")
    if not 0 < strike_millis <= 99_999_999:
        raise NbboCohortError("contract.strike_millis is outside OCC bounds")
    return (
        f"{root:<6}{expiry:%y%m%d}{'C' if right == 'call' else 'P'}{strike_millis:08d}"
    )


def validate_contract(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise NbboCohortError("contract must be an object")
    required = {
        "root",
        "expiration",
        "right",
        "strike",
        "strike_millis",
        "occ_symbol",
    }
    if set(raw) != required:
        raise NbboCohortError("contract fields are not exact")
    root = raw["root"]
    expiration = raw["expiration"]
    right = raw["right"]
    strike_text, strike_millis = _canonical_strike(raw["strike"])
    if raw["strike"] != strike_text:
        raise NbboCohortError("contract.strike is not canonical")
    if raw["strike_millis"] != strike_millis:
        raise NbboCohortError("contract strike and millistrike disagree")
    if (
        not isinstance(root, str)
        or not isinstance(expiration, str)
        or not isinstance(right, str)
    ):
        raise NbboCohortError("contract identity fields must be strings")
    expected_occ = canonical_occ_symbol(
        root=root,
        expiration=expiration,
        right=right,
        strike_millis=strike_millis,
    )
    if raw["occ_symbol"] != expected_occ or not _OCC_RE.fullmatch(expected_occ):
        raise NbboCohortError("contract OCC symbol does not match exact fields")
    return {
        "root": root,
        "expiration": expiration,
        "right": right,
        "strike": strike_text,
        "strike_millis": strike_millis,
        "occ_symbol": expected_occ,
    }


def _content_id(prefix: str, payload: Mapping[str, Any], id_field: str) -> str:
    identity = dict(payload)
    identity.pop(id_field, None)
    return prefix + sha256(canonical_json_bytes(identity)).hexdigest()


def _event_content_id(payload: Mapping[str, Any]) -> str:
    """Return the event identity without creating an evidence hash cycle."""

    identity = dict(payload)
    identity.pop("event_id", None)
    identity.pop("private_evidence", None)
    return "nbboevt_" + sha256(canonical_json_bytes(identity)).hexdigest()


def _capture_content_id(payload: Mapping[str, Any]) -> str:
    """Return the capture identity without creating an evidence hash cycle."""

    identity = dict(payload)
    identity.pop("capture_receipt_id", None)
    identity.pop("private_evidence", None)
    return "nbbocap_" + sha256(canonical_json_bytes(identity)).hexdigest()


def _armed_event_producer(system: str) -> Mapping[str, Any]:
    registration = EVENT_PRODUCER_REGISTRY.get(system)
    if not isinstance(registration, Mapping) or registration.get("armed") is not True:
        raise NbboCohortError(
            f"{system} event producer is not armed; audited adapter required"
        )
    required = {
        "armed",
        "source_schema",
        "decision_rule_sha256",
        "lifecycle_rule_sha256",
        "authentication_basis",
    }
    if set(registration) != required:
        raise NbboCohortError(f"{system} event producer registration is incomplete")
    for key in ("decision_rule_sha256", "lifecycle_rule_sha256"):
        value = registration[key]
        if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
            raise NbboCohortError(f"{system} event producer {key} is not pinned")
    for key in ("source_schema", "authentication_basis"):
        if not isinstance(registration[key], str) or not registration[key]:
            raise NbboCohortError(f"{system} event producer {key} is not pinned")
    return registration


def _armed_capture_producer(system: str) -> Mapping[str, Any]:
    registration = CAPTURE_PRODUCER_REGISTRY.get(system)
    if not isinstance(registration, Mapping) or registration.get("armed") is not True:
        raise NbboCohortError(
            f"{system} capture producer is not armed; audited adapter required"
        )
    required = {
        "armed",
        "source_schema",
        "producer_rule_sha256",
        "authentication_basis",
    }
    if set(registration) != required:
        raise NbboCohortError(f"{system} capture producer registration is incomplete")
    digest = registration["producer_rule_sha256"]
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise NbboCohortError(f"{system} capture producer rule digest is not pinned")
    for key in ("source_schema", "authentication_basis"):
        if not isinstance(registration[key], str) or not registration[key]:
            raise NbboCohortError(f"{system} capture producer {key} is not pinned")
    return registration


def validate_event(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise NbboCohortError("cohort event must be an object")
    event = dict(raw)
    if event.get("schema") != EVENT_SCHEMA:
        raise NbboCohortError("cohort event schema mismatch")
    kind = event.get("kind")
    if kind not in {"enroll", "terminal"}:
        raise NbboCohortError("cohort event kind is invalid")
    if event.get("cohort_rule_id") != COHORT_RULE_ID:
        raise NbboCohortError("cohort rule mismatch")
    if event.get("benchmark_digest_sha256") != BENCHMARK_DIGEST:
        raise NbboCohortError("benchmark digest mismatch")
    if event.get("benchmark_effective_freeze_at") != BENCHMARK_EFFECTIVE_FREEZE_AT:
        raise NbboCohortError("benchmark effective freeze mismatch")
    if event.get("phase") != PROSPECTIVE_PHASE:
        raise NbboCohortError("cohort event phase is not prospective")
    system = event.get("system")
    if system not in _EVENT_SYSTEMS:
        raise NbboCohortError("cohort system is invalid")
    signal_id = event.get("stable_signal_id")
    if not isinstance(signal_id, str) or not _ID_RE.fullmatch(signal_id):
        raise NbboCohortError("stable signal id is malformed")
    contract = validate_contract(event.get("contract"))
    event_at = _utc(event.get("event_at"), label="event_at")
    available_at = _utc(event.get("available_at"), label="available_at")
    if available_at < event_at:
        raise NbboCohortError("event availability precedes event time")
    freeze = _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze")
    if event_at < freeze or available_at < freeze:
        raise NbboCohortError("pre-freeze event cannot enter the prospective cohort")
    if event.get("authority") != FALSE_AUTHORITY:
        raise NbboCohortError("event authority must be the exact all-false block")
    digests = event.get("rule_digests")
    if not isinstance(digests, Mapping) or set(digests) != {
        "decision_rule_sha256",
        "lifecycle_rule_sha256",
        "quote_rule_sha256",
    }:
        raise NbboCohortError("event rule digests are incomplete")
    for name, digest in digests.items():
        if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
            raise NbboCohortError(f"event {name} is malformed")
    expected_quote_digest = sha256(QUOTE_RULE_ID.encode("utf-8")).hexdigest()
    if digests["quote_rule_sha256"] != expected_quote_digest:
        raise NbboCohortError("event quote rule digest mismatch")
    registration = _armed_event_producer(system)
    if digests["decision_rule_sha256"] != registration["decision_rule_sha256"]:
        raise NbboCohortError("event producer decision rule digest mismatch")
    if digests["lifecycle_rule_sha256"] != registration["lifecycle_rule_sha256"]:
        raise NbboCohortError("event producer lifecycle rule digest mismatch")
    evidence = event.get("private_evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "schema",
        "object_sha256",
        "object_bytes",
    }:
        raise NbboCohortError("private evidence receipt is incomplete")
    if evidence["schema"] != AUTHENTICATED_EVENT_EVIDENCE_SCHEMA:
        raise NbboCohortError("private event evidence schema is not frozen")
    if not isinstance(evidence["object_sha256"], str) or not _SHA_RE.fullmatch(
        evidence["object_sha256"]
    ):
        raise NbboCohortError("private evidence digest is malformed")
    if (
        not isinstance(evidence["object_bytes"], int)
        or isinstance(evidence["object_bytes"], bool)
        or not 0 < evidence["object_bytes"] <= MAX_RESPONSE_BYTES
    ):
        raise NbboCohortError("private evidence byte count is malformed")
    enrollment_event_id = event.get("enrollment_event_id")
    terminal_reason = event.get("terminal_reason")
    if kind == "enroll":
        if enrollment_event_id is not None:
            raise NbboCohortError("enrollment cannot reference another enrollment")
        if terminal_reason is not None:
            raise NbboCohortError("enrollment cannot carry a terminal reason")
        if date.fromisoformat(contract["expiration"]) < event_at.astimezone(ET).date():
            raise NbboCohortError("enrollment contract is already expired")
        expiry = date.fromisoformat(contract["expiration"])
        last_session = nyse_calendar.last_session_on_or_before(expiry)
        liquidation = datetime.combine(
            last_session, time(15, 55), tzinfo=ET
        ).astimezone(timezone.utc)
        if max(event_at, available_at) > liquidation:
            raise NbboCohortError(
                "enrollment boundary follows frozen expiry liquidation"
            )
    else:
        if not isinstance(
            enrollment_event_id, str
        ) or not enrollment_event_id.startswith("nbboevt_"):
            raise NbboCohortError("terminal event enrollment reference is malformed")
        if terminal_reason not in {
            "lifecycle_terminal",
            "expiry_liquidation_1555_et",
        }:
            raise NbboCohortError("terminal reason is not frozen")
        if terminal_reason == "expiry_liquidation_1555_et":
            expiry = date.fromisoformat(contract["expiration"])
            last_session = nyse_calendar.last_session_on_or_before(expiry)
            expected = datetime.combine(last_session, time(15, 55), tzinfo=ET)
            if event_at != expected.astimezone(timezone.utc):
                raise NbboCohortError(
                    "expiry liquidation terminal must be exactly 15:55 ET on the last tradable session"
                )
    expected_id = _event_content_id(event)
    if event.get("event_id") != expected_id:
        raise NbboCohortError("cohort event content identity mismatch")
    event["contract"] = contract
    validate_schema(event, label="cohort event")
    return event


def make_event(
    *,
    kind: str,
    system: str,
    stable_signal_id: str,
    contract: Mapping[str, Any],
    event_at: str,
    available_at: str,
    decision_rule_sha256: str,
    lifecycle_rule_sha256: str,
    private_evidence_schema: str,
    private_evidence_sha256: str,
    private_evidence_bytes: int,
    enrollment_event_id: str | None = None,
    terminal_reason: str | None = None,
) -> dict[str, Any]:
    if kind == "terminal" and terminal_reason is None:
        terminal_reason = "lifecycle_terminal"
    payload: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "event_id": None,
        "kind": kind,
        "system": system,
        "stable_signal_id": stable_signal_id,
        "cohort_rule_id": COHORT_RULE_ID,
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "benchmark_effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
        "phase": PROSPECTIVE_PHASE,
        "contract": dict(contract),
        "event_at": event_at,
        "available_at": available_at,
        "enrollment_event_id": enrollment_event_id,
        "terminal_reason": terminal_reason,
        "rule_digests": {
            "decision_rule_sha256": decision_rule_sha256,
            "lifecycle_rule_sha256": lifecycle_rule_sha256,
            "quote_rule_sha256": sha256(QUOTE_RULE_ID.encode()).hexdigest(),
        },
        "private_evidence": {
            "schema": private_evidence_schema,
            "object_sha256": private_evidence_sha256,
            "object_bytes": private_evidence_bytes,
        },
        "authority": dict(FALSE_AUTHORITY),
    }
    payload["event_id"] = _event_content_id(payload)
    return validate_event(payload)


_EVENT_EVIDENCE_BINDING_FIELDS = (
    "event_id",
    "kind",
    "system",
    "stable_signal_id",
    "cohort_rule_id",
    "benchmark_digest_sha256",
    "benchmark_effective_freeze_at",
    "phase",
    "contract",
    "event_at",
    "available_at",
    "enrollment_event_id",
    "terminal_reason",
    "rule_digests",
    "authority",
)


def build_event_evidence_bytes(
    *,
    event: Mapping[str, Any],
    source_schema: str,
    source_payload: Mapping[str, Any],
) -> bytes:
    """Build a private envelope that replays one exact producer event claim."""

    row = validate_event(event)
    registration = _armed_event_producer(row["system"])
    if row["terminal_reason"] == "expiry_liquidation_1555_et":
        expected_schema = EXPIRY_EVENT_SOURCE_SCHEMA
        authentication_basis = "deterministic_nyse_calendar_derivation"
    else:
        expected_schema = registration["source_schema"]
        authentication_basis = registration["authentication_basis"]
    if source_schema != expected_schema:
        raise NbboCohortError("event evidence source schema is not preregistered")
    if not isinstance(source_payload, Mapping) or not source_payload:
        raise NbboCohortError("event evidence source payload is empty")
    source_body = canonical_json_bytes(dict(source_payload))
    return canonical_json_bytes(
        {
            "schema": AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
            "cohort_rule_id": COHORT_RULE_ID,
            "benchmark_digest_sha256": BENCHMARK_DIGEST,
            "binding": {field: row[field] for field in _EVENT_EVIDENCE_BINDING_FIELDS},
            "authentication_basis": authentication_basis,
            "source": {
                "schema": source_schema,
                "payload": dict(source_payload),
                "payload_sha256": sha256(source_body).hexdigest(),
                "payload_bytes": len(source_body),
            },
            "authority": dict(FALSE_AUTHORITY),
        }
    )


def validate_event_evidence_binding(
    evidence_payload: Mapping[str, Any], event: Mapping[str, Any]
) -> None:
    """Replay an event envelope and reject forgery or evidence reuse."""

    row = validate_event(event)
    if not isinstance(evidence_payload, Mapping) or set(evidence_payload) != {
        "schema",
        "cohort_rule_id",
        "benchmark_digest_sha256",
        "binding",
        "authentication_basis",
        "source",
        "authority",
    }:
        raise NbboCohortError("event evidence envelope fields are not exact")
    if (
        evidence_payload.get("schema") != AUTHENTICATED_EVENT_EVIDENCE_SCHEMA
        or evidence_payload.get("cohort_rule_id") != COHORT_RULE_ID
        or evidence_payload.get("benchmark_digest_sha256") != BENCHMARK_DIGEST
        or evidence_payload.get("authority") != FALSE_AUTHORITY
    ):
        raise NbboCohortError("event evidence governance binding drifted")
    expected_binding = {field: row[field] for field in _EVENT_EVIDENCE_BINDING_FIELDS}
    if evidence_payload.get("binding") != expected_binding:
        raise NbboCohortError("event evidence does not bind the exact event")
    source = evidence_payload.get("source")
    if not isinstance(source, Mapping) or set(source) != {
        "schema",
        "payload",
        "payload_sha256",
        "payload_bytes",
    }:
        raise NbboCohortError("authenticated event source object is malformed")
    if not isinstance(source.get("payload"), Mapping) or not source["payload"]:
        raise NbboCohortError("authenticated event source payload is empty")
    source_body = canonical_json_bytes(dict(source["payload"]))
    if source.get("payload_sha256") != sha256(source_body).hexdigest() or source.get(
        "payload_bytes"
    ) != len(source_body):
        raise NbboCohortError("authenticated event source payload receipt drifted")
    registration = _armed_event_producer(row["system"])
    if row["terminal_reason"] == "expiry_liquidation_1555_et":
        expected_schema = EXPIRY_EVENT_SOURCE_SCHEMA
        expected_basis = "deterministic_nyse_calendar_derivation"
        expiry = date.fromisoformat(row["contract"]["expiration"])
        last_session = nyse_calendar.last_session_on_or_before(expiry)
        expected_payload = {
            "enrollment_event_id": row["enrollment_event_id"],
            "contract": row["contract"],
            "last_tradable_session": last_session.isoformat(),
            "terminal_event_at": row["event_at"],
            "available_at": row["available_at"],
            "rule": "last_nyse_session_on_or_before_occ_expiration_at_1555_et/v1",
        }
        if source["payload"] != expected_payload:
            raise NbboCohortError("expiry evidence source derivation is not exact")
    else:
        expected_schema = registration["source_schema"]
        expected_basis = registration["authentication_basis"]
    if source.get("schema") != expected_schema:
        raise NbboCohortError("event evidence source schema is not preregistered")
    if evidence_payload.get("authentication_basis") != expected_basis:
        raise NbboCohortError("event evidence authentication basis is wrong")


def validate_capture_receipt(raw: Any) -> dict[str, Any]:
    """Validate one host-private two-system capture attempt.

    A successful zero-call poll is valid coverage.  An absent producer is not an
    abstention: it must be recorded as ``unavailable`` and cannot help cover a
    session.
    """

    if not isinstance(raw, Mapping):
        raise NbboCohortError("capture receipt must be an object")
    receipt = dict(raw)
    if receipt.get("schema") != CAPTURE_SCHEMA:
        raise NbboCohortError("capture receipt schema mismatch")
    if receipt.get("cohort_rule_id") != COHORT_RULE_ID:
        raise NbboCohortError("capture receipt cohort rule mismatch")
    if receipt.get("capture_rule_id") != CAPTURE_RULE_ID:
        raise NbboCohortError("capture receipt rule mismatch")
    if receipt.get("benchmark_digest_sha256") != BENCHMARK_DIGEST:
        raise NbboCohortError("capture receipt benchmark mismatch")
    if receipt.get("benchmark_effective_freeze_at") != BENCHMARK_EFFECTIVE_FREEZE_AT:
        raise NbboCohortError("capture receipt freeze mismatch")
    if receipt.get("phase") != PROSPECTIVE_PHASE:
        raise NbboCohortError("capture receipt phase mismatch")
    system = receipt.get("comparison_system")
    if system not in _CAPTURE_SYSTEMS:
        raise NbboCohortError("capture comparison system is invalid")
    disposition = receipt.get("disposition")
    if disposition not in _CAPTURE_DISPOSITIONS:
        raise NbboCohortError("capture disposition is invalid")
    if system == "momoedge" and disposition == "selector_abstained":
        raise NbboCohortError("MomoEdge capture cannot infer selector abstention")

    scheduled = _utc(receipt.get("scheduled_at"), label="capture scheduled_at")
    attempted = _utc(receipt.get("attempted_at"), label="capture attempted_at")
    completed = _utc(receipt.get("completed_at"), label="capture completed_at")
    freeze = _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze")
    if scheduled < freeze or attempted < freeze or completed < freeze:
        raise NbboCohortError("pre-freeze capture cannot enter the cohort")
    session = scheduled.astimezone(ET).date()
    if receipt.get("session_date") != session.isoformat():
        raise NbboCohortError("capture session_date disagrees with scheduled_at")
    opened, closed = _session_window(session)
    if not opened <= scheduled < closed:
        raise NbboCohortError("capture scheduled_at is outside NYSE RTH")
    if int((scheduled - opened).total_seconds()) % CAPTURE_CADENCE_SECONDS != 0:
        raise NbboCohortError("capture scheduled_at is not on the frozen 300s grid")
    if not scheduled <= attempted <= completed:
        raise NbboCohortError("capture attempt clocks are not causal")
    if completed >= scheduled + timedelta(seconds=CAPTURE_CADENCE_SECONDS):
        raise NbboCohortError("capture did not complete inside its scheduled slot")

    authenticated = receipt.get("evidence_authenticated")
    event_at_text = receipt.get("capture_event_at")
    observed_count = receipt.get("observed_new_call_count")
    event_ids = receipt.get("new_enrollment_event_ids")
    reason = receipt.get("reason")
    producer_digest = receipt.get("producer_rule_sha256")
    if (
        not isinstance(observed_count, int)
        or isinstance(observed_count, bool)
        or observed_count < 0
        or not isinstance(event_ids, list)
        or len(event_ids) != observed_count
        or len(set(event_ids)) != len(event_ids)
        or any(
            not isinstance(event_id, str)
            or re.fullmatch(r"nbboevt_[0-9a-f]{64}", event_id) is None
            for event_id in event_ids
        )
    ):
        raise NbboCohortError("capture enrollment reconciliation is malformed")
    if disposition == "unavailable":
        if (
            authenticated is not False
            or event_at_text is not None
            or observed_count != 0
            or reason not in _CAPTURE_UNAVAILABLE_REASONS
            or producer_digest is not None
        ):
            raise NbboCohortError("unavailable capture carries a success claim")
    else:
        if authenticated is not True or reason is not None:
            raise NbboCohortError("successful capture lacks authenticated evidence")
        registration = _armed_capture_producer(system)
        event_at = _utc(event_at_text, label="capture event_at")
        if not scheduled <= event_at <= completed:
            raise NbboCohortError("capture event clock is outside its exact poll")
        if not isinstance(producer_digest, str) or not _SHA_RE.fullmatch(
            producer_digest
        ):
            raise NbboCohortError("capture producer rule digest is malformed")
        if producer_digest != registration["producer_rule_sha256"]:
            raise NbboCohortError("capture producer rule digest is not preregistered")
        if disposition == "new_calls_observed" and observed_count < 1:
            raise NbboCohortError("new-call capture has no enrollment")
        if disposition != "new_calls_observed" and observed_count != 0:
            raise NbboCohortError("zero-call capture carries an enrollment")

    evidence = receipt.get("private_evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "schema",
        "object_sha256",
        "object_bytes",
    }:
        raise NbboCohortError("capture private evidence receipt is incomplete")
    if not isinstance(evidence["schema"], str) or not evidence["schema"]:
        raise NbboCohortError("capture private evidence schema is missing")
    expected_evidence_schema = (
        UNAVAILABLE_CAPTURE_EVIDENCE_SCHEMA
        if disposition == "unavailable"
        else AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA
    )
    if evidence["schema"] != expected_evidence_schema:
        raise NbboCohortError("capture private evidence schema is not frozen")
    if not isinstance(evidence["object_sha256"], str) or not _SHA_RE.fullmatch(
        evidence["object_sha256"]
    ):
        raise NbboCohortError("capture private evidence digest is malformed")
    if (
        not isinstance(evidence["object_bytes"], int)
        or isinstance(evidence["object_bytes"], bool)
        or not 0 < evidence["object_bytes"] <= MAX_RESPONSE_BYTES
    ):
        raise NbboCohortError("capture private evidence byte count is malformed")
    if receipt.get("authority") != FALSE_AUTHORITY:
        raise NbboCohortError("capture authority must be the exact all-false block")
    expected_id = _capture_content_id(receipt)
    if receipt.get("capture_receipt_id") != expected_id:
        raise NbboCohortError("capture receipt content identity mismatch")
    validate_schema(receipt, label="NBBO capture receipt")
    return receipt


def _capture_claim(
    *,
    comparison_system: str,
    scheduled_at: str,
    attempted_at: str,
    completed_at: str,
    disposition: str,
    capture_event_at: str | None = None,
    observed_new_call_count: int = 0,
    new_enrollment_event_ids: Sequence[str] = (),
    producer_rule_sha256: str | None = None,
    evidence_authenticated: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    scheduled = _utc(scheduled_at, label="capture scheduled_at")
    return {
        "schema": CAPTURE_SCHEMA,
        "capture_receipt_id": None,
        "cohort_rule_id": COHORT_RULE_ID,
        "capture_rule_id": CAPTURE_RULE_ID,
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "benchmark_effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
        "phase": PROSPECTIVE_PHASE,
        "comparison_system": comparison_system,
        "session_date": scheduled.astimezone(ET).date().isoformat(),
        "scheduled_at": scheduled_at,
        "attempted_at": attempted_at,
        "completed_at": completed_at,
        "capture_event_at": capture_event_at,
        "disposition": disposition,
        "reason": reason,
        "evidence_authenticated": evidence_authenticated,
        "observed_new_call_count": observed_new_call_count,
        "new_enrollment_event_ids": list(new_enrollment_event_ids),
        "producer_rule_sha256": producer_rule_sha256,
        "authority": dict(FALSE_AUTHORITY),
    }


def make_capture_receipt(
    *,
    comparison_system: str,
    scheduled_at: str,
    attempted_at: str,
    completed_at: str,
    disposition: str,
    private_evidence_schema: str,
    private_evidence_sha256: str,
    private_evidence_bytes: int,
    capture_event_at: str | None = None,
    observed_new_call_count: int = 0,
    new_enrollment_event_ids: Sequence[str] = (),
    producer_rule_sha256: str | None = None,
    evidence_authenticated: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    payload = _capture_claim(
        comparison_system=comparison_system,
        scheduled_at=scheduled_at,
        attempted_at=attempted_at,
        completed_at=completed_at,
        disposition=disposition,
        capture_event_at=capture_event_at,
        observed_new_call_count=observed_new_call_count,
        new_enrollment_event_ids=new_enrollment_event_ids,
        producer_rule_sha256=producer_rule_sha256,
        evidence_authenticated=evidence_authenticated,
        reason=reason,
    )
    payload["private_evidence"] = {
        "schema": private_evidence_schema,
        "object_sha256": private_evidence_sha256,
        "object_bytes": private_evidence_bytes,
    }
    payload["capture_receipt_id"] = _capture_content_id(payload)
    return validate_capture_receipt(payload)


_CAPTURE_EVIDENCE_BINDING_FIELDS = (
    "capture_receipt_id",
    "comparison_system",
    "session_date",
    "scheduled_at",
    "attempted_at",
    "completed_at",
    "capture_event_at",
    "disposition",
    "reason",
    "evidence_authenticated",
    "observed_new_call_count",
    "new_enrollment_event_ids",
    "producer_rule_sha256",
)

_CAPTURE_SOURCE_BINDING_FIELDS = (
    "comparison_system",
    "scheduled_at",
    "attempted_at",
    "completed_at",
    "capture_event_at",
    "disposition",
    "observed_new_call_count",
    "new_enrollment_event_ids",
    "producer_rule_sha256",
)


def _validate_capture_source_binding(
    source_payload: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    for field in _CAPTURE_SOURCE_BINDING_FIELDS:
        if source_payload.get(field) != binding.get(field):
            raise NbboCohortError(f"authenticated capture source does not bind {field}")


def build_capture_evidence_bytes(
    *,
    comparison_system: str,
    scheduled_at: str,
    attempted_at: str,
    completed_at: str,
    capture_event_at: str | None,
    disposition: str,
    reason: str | None,
    evidence_authenticated: bool,
    observed_new_call_count: int,
    new_enrollment_event_ids: Sequence[str],
    producer_rule_sha256: str | None,
    source_schema: str | None,
    source_payload: Mapping[str, Any] | None,
) -> bytes:
    """Build exact private evidence that can replay every coverage claim."""

    session_text = (
        _utc(scheduled_at, label="capture evidence scheduled_at")
        .astimezone(ET)
        .date()
        .isoformat()
    )
    binding: dict[str, Any] = {
        "comparison_system": comparison_system,
        "session_date": session_text,
        "scheduled_at": scheduled_at,
        "attempted_at": attempted_at,
        "completed_at": completed_at,
        "capture_event_at": capture_event_at,
        "disposition": disposition,
        "reason": reason,
        "evidence_authenticated": evidence_authenticated,
        "observed_new_call_count": observed_new_call_count,
        "new_enrollment_event_ids": list(new_enrollment_event_ids),
        "producer_rule_sha256": producer_rule_sha256,
    }
    claim = _capture_claim(
        comparison_system=comparison_system,
        scheduled_at=scheduled_at,
        attempted_at=attempted_at,
        completed_at=completed_at,
        capture_event_at=capture_event_at,
        disposition=disposition,
        reason=reason,
        evidence_authenticated=evidence_authenticated,
        observed_new_call_count=observed_new_call_count,
        new_enrollment_event_ids=new_enrollment_event_ids,
        producer_rule_sha256=producer_rule_sha256,
    )
    binding["capture_receipt_id"] = _capture_content_id(claim)
    if disposition == "unavailable":
        evidence_schema = UNAVAILABLE_CAPTURE_EVIDENCE_SCHEMA
        authentication_basis = "none"
        if source_schema is not None or source_payload is not None:
            raise NbboCohortError("unavailable capture evidence cannot carry a source")
        source = None
    else:
        evidence_schema = AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA
        registration = _armed_capture_producer(comparison_system)
        authentication_basis = registration["authentication_basis"]
        if (
            not isinstance(source_schema, str)
            or not source_schema
            or not isinstance(source_payload, Mapping)
            or not source_payload
        ):
            raise NbboCohortError(
                "successful capture evidence requires a non-empty private source object"
            )
        if source_schema != registration["source_schema"]:
            raise NbboCohortError("capture evidence source schema is not preregistered")
        _validate_capture_source_binding(source_payload, binding)
        source_body = canonical_json_bytes(dict(source_payload))
        source = {
            "schema": source_schema,
            "payload": dict(source_payload),
            "payload_sha256": sha256(source_body).hexdigest(),
            "payload_bytes": len(source_body),
        }
    return canonical_json_bytes(
        {
            "schema": evidence_schema,
            "cohort_rule_id": COHORT_RULE_ID,
            "capture_rule_id": CAPTURE_RULE_ID,
            "benchmark_digest_sha256": BENCHMARK_DIGEST,
            "binding": binding,
            "authentication_basis": authentication_basis,
            "source": source,
            "authority": dict(FALSE_AUTHORITY),
        }
    )


def validate_capture_evidence_binding(
    evidence_payload: Mapping[str, Any], receipt: Mapping[str, Any]
) -> None:
    row = validate_capture_receipt(receipt)
    if not isinstance(evidence_payload, Mapping) or set(evidence_payload) != {
        "schema",
        "cohort_rule_id",
        "capture_rule_id",
        "benchmark_digest_sha256",
        "binding",
        "authentication_basis",
        "source",
        "authority",
    }:
        raise NbboCohortError("capture evidence envelope fields are not exact")
    if (
        evidence_payload.get("schema") != row["private_evidence"]["schema"]
        or evidence_payload.get("cohort_rule_id") != COHORT_RULE_ID
        or evidence_payload.get("capture_rule_id") != CAPTURE_RULE_ID
        or evidence_payload.get("benchmark_digest_sha256") != BENCHMARK_DIGEST
        or evidence_payload.get("authority") != FALSE_AUTHORITY
    ):
        raise NbboCohortError("capture evidence governance binding drifted")
    expected_binding = {field: row[field] for field in _CAPTURE_EVIDENCE_BINDING_FIELDS}
    if evidence_payload.get("binding") != expected_binding:
        raise NbboCohortError("capture evidence does not bind the exact receipt")
    source = evidence_payload.get("source")
    if row["disposition"] == "unavailable":
        if evidence_payload.get("authentication_basis") != "none" or source is not None:
            raise NbboCohortError("unavailable capture evidence claims authentication")
        return
    registration = _armed_capture_producer(row["comparison_system"])
    expected_basis = registration["authentication_basis"]
    if evidence_payload.get("authentication_basis") != expected_basis:
        raise NbboCohortError("capture evidence authentication basis is wrong")
    if not isinstance(source, Mapping) or set(source) != {
        "schema",
        "payload",
        "payload_sha256",
        "payload_bytes",
    }:
        raise NbboCohortError("authenticated capture source object is malformed")
    if source.get("schema") != registration["source_schema"]:
        raise NbboCohortError("capture evidence source schema is not preregistered")
    if not isinstance(source.get("payload"), Mapping) or not source["payload"]:
        raise NbboCohortError("authenticated capture source payload is empty")
    _validate_capture_source_binding(source["payload"], expected_binding)
    source_body = canonical_json_bytes(dict(source["payload"]))
    if source.get("payload_sha256") != sha256(source_body).hexdigest() or source.get(
        "payload_bytes"
    ) != len(source_body):
        raise NbboCohortError("authenticated capture source payload receipt drifted")


def read_capture_ledger(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            body = handle.read(MAX_CAPTURE_BYTES + 1)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise NbboCohortError(f"cannot read private capture ledger: {exc}") from exc
    if len(body) > MAX_CAPTURE_BYTES:
        raise NbboCohortError("private capture ledger exceeds byte cap")
    if body and not body.endswith(b"\n"):
        raise NbboCohortError("private capture ledger lacks a final line boundary")
    receipts: list[dict[str, Any]] = []
    seen: dict[str, bytes] = {}
    for row_number, line in enumerate(body.splitlines(), 1):
        if not line:
            raise NbboCohortError(f"private capture ledger row {row_number} is empty")
        receipt = validate_capture_receipt(
            strict_json_object(line, label=f"capture row {row_number}")
        )
        canonical = canonical_json_bytes(receipt).rstrip(b"\n")
        if canonical != line:
            raise NbboCohortError(
                f"private capture ledger row {row_number} is not canonical"
            )
        receipt_id = receipt["capture_receipt_id"]
        previous = seen.get(receipt_id)
        if previous is not None and previous != line:
            raise NbboCohortError("conflicting duplicate capture receipt")
        if previous is None:
            seen[receipt_id] = line
            receipts.append(receipt)
    if len(receipts) > MAX_CAPTURE_RECEIPTS:
        raise NbboCohortError("private capture ledger exceeds row cap")
    return receipts, {
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
        "row_count": len(receipts),
    }


def expiry_terminal_candidates(
    events: Sequence[Mapping[str, Any]], *, available_at: datetime
) -> list[tuple[dict[str, Any], bytes]]:
    """Derive honest 15:55 ET expiry terminals for still-open enrollments.

    The terminal event clock is the frozen calendar rule.  ``available_at`` is
    the actual runtime clock and is never backdated; a late runner therefore
    remains visibly late and cannot create a qualifying quote observation.
    """

    observed = _aware_utc(available_at, label="expiry producer clock")
    enrollments, terminals = reconcile_events(events)
    candidates: list[tuple[dict[str, Any], bytes]] = []
    for enrollment in enrollments:
        if enrollment["event_id"] in terminals:
            continue
        expiry = date.fromisoformat(enrollment["contract"]["expiration"])
        last_session = nyse_calendar.last_session_on_or_before(expiry)
        boundary = datetime.combine(last_session, time(15, 55), tzinfo=ET).astimezone(
            timezone.utc
        )
        if observed < boundary:
            continue
        source_payload = {
            "enrollment_event_id": enrollment["event_id"],
            "contract": enrollment["contract"],
            "last_tradable_session": last_session.isoformat(),
            "terminal_event_at": utc_text(boundary),
            "available_at": utc_text(observed),
            "rule": "last_nyse_session_on_or_before_occ_expiration_at_1555_et/v1",
        }
        terminal_claim = make_event(
            kind="terminal",
            system=enrollment["system"],
            stable_signal_id=enrollment["stable_signal_id"],
            contract=enrollment["contract"],
            event_at=utc_text(boundary),
            available_at=utc_text(observed),
            decision_rule_sha256=enrollment["rule_digests"]["decision_rule_sha256"],
            lifecycle_rule_sha256=enrollment["rule_digests"]["lifecycle_rule_sha256"],
            private_evidence_schema=AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
            private_evidence_sha256="0" * 64,
            private_evidence_bytes=1,
            enrollment_event_id=enrollment["event_id"],
            terminal_reason="expiry_liquidation_1555_et",
        )
        evidence_body = build_event_evidence_bytes(
            event=terminal_claim,
            source_schema=EXPIRY_EVENT_SOURCE_SCHEMA,
            source_payload=source_payload,
        )
        terminal = make_event(
            kind="terminal",
            system=enrollment["system"],
            stable_signal_id=enrollment["stable_signal_id"],
            contract=enrollment["contract"],
            event_at=utc_text(boundary),
            available_at=utc_text(observed),
            decision_rule_sha256=enrollment["rule_digests"]["decision_rule_sha256"],
            lifecycle_rule_sha256=enrollment["rule_digests"]["lifecycle_rule_sha256"],
            private_evidence_schema=AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
            private_evidence_sha256=sha256(evidence_body).hexdigest(),
            private_evidence_bytes=len(evidence_body),
            enrollment_event_id=enrollment["event_id"],
            terminal_reason="expiry_liquidation_1555_et",
        )
        candidates.append((terminal, evidence_body))
    return candidates


def read_event_ledger(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            body = handle.read(MAX_EVENT_BYTES + 1)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise NbboCohortError(f"cannot read private event ledger: {exc}") from exc
    if len(body) > MAX_EVENT_BYTES:
        raise NbboCohortError("private event ledger exceeds byte cap")
    if body and not body.endswith(b"\n"):
        raise NbboCohortError("private event ledger lacks a final line boundary")
    events: list[dict[str, Any]] = []
    seen: dict[str, bytes] = {}
    for row_number, line in enumerate(body.splitlines(), 1):
        if not line:
            raise NbboCohortError(f"private event ledger row {row_number} is empty")
        event = validate_event(
            strict_json_object(line, label=f"event row {row_number}")
        )
        canonical = canonical_json_bytes(event).rstrip(b"\n")
        if canonical != line:
            raise NbboCohortError(
                f"private event ledger row {row_number} is not canonical"
            )
        event_id = event["event_id"]
        previous = seen.get(event_id)
        if previous is not None and previous != line:
            raise NbboCohortError("conflicting duplicate cohort event")
        if previous is None:
            seen[event_id] = line
            events.append(event)
    if len(events) > MAX_EVENTS:
        raise NbboCohortError("private event ledger exceeds row cap")
    return events, {
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
        "row_count": len(events),
    }


def reconcile_events(
    events: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    enrollments: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    by_signal: dict[tuple[str, str], str] = {}
    terminals: dict[str, dict[str, Any]] = {}
    system_rules: dict[str, dict[str, str]] = {}
    for raw in events:
        event = validate_event(raw)
        event_id = event["event_id"]
        if event["kind"] == "enroll":
            rules = dict(event["rule_digests"])
            prior_rules = system_rules.get(event["system"])
            if prior_rules is not None and prior_rules != rules:
                raise NbboCohortError("system rule digests changed within the cohort")
            system_rules[event["system"]] = rules
            signal_key = (event["system"], event["stable_signal_id"])
            prior = by_signal.get(signal_key)
            if prior is not None and prior != event_id:
                raise NbboCohortError("stable signal identity has multiple enrollments")
            by_signal[signal_key] = event_id
            by_id[event_id] = event
            enrollments.append(event)
            continue
        enrollment_id = event["enrollment_event_id"]
        enrollment = by_id.get(enrollment_id)
        if enrollment is None:
            raise NbboCohortError("terminal references a missing or later enrollment")
        for key in ("system", "stable_signal_id", "contract", "rule_digests"):
            if event[key] != enrollment[key]:
                raise NbboCohortError(f"terminal {key} drifts from enrollment")
        if _utc(event["event_at"], label="terminal event_at") < _utc(
            enrollment["event_at"], label="enrollment event_at"
        ):
            raise NbboCohortError("terminal predates enrollment trigger")
        if _utc(event["available_at"], label="terminal available_at") < _utc(
            enrollment["available_at"], label="enrollment available_at"
        ):
            raise NbboCohortError("terminal availability predates enrollment")
        if effective_boundary(event) < effective_boundary(enrollment):
            raise NbboCohortError("terminal causal boundary predates enrollment")
        prior_terminal = terminals.get(enrollment_id)
        if prior_terminal is not None and prior_terminal["event_id"] != event_id:
            raise NbboCohortError("enrollment has multiple terminal events")
        terminals[enrollment_id] = event
    enrollments.sort(key=lambda row: (row["available_at"], row["event_id"]))
    return enrollments, terminals


def _source_clock(value: Any) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise NbboSourceError("source quote timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise NbboSourceError("source quote timestamp is malformed") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(timezone.utc)


def _source_int(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise NbboSourceError(f"source {label} is not an integer")
    if value < 0:
        raise NbboSourceError(f"source {label} is outside bounds")
    return value


def parse_quote_response(
    payload: Any,
    *,
    role: str,
    contract: Mapping[str, Any],
    boundary_at: datetime,
    query_end_at: datetime | None = None,
) -> SourceQuote | None:
    if role not in {"entry", "exit"}:
        raise NbboSourceError("quote selection role is invalid")
    exact_contract = validate_contract(contract)
    boundary_at = _aware_utc(boundary_at, label="quote boundary")
    if query_end_at is not None:
        query_end_at = _aware_utc(query_end_at, label="quote query end")
        if query_end_at < boundary_at:
            raise NbboSourceError("source query end precedes the causal boundary")
    if not isinstance(payload, list):
        raise NbboSourceError("Theta v3 quote response must be a flat JSON array")
    if len(payload) > MAX_RESPONSE_ROWS:
        raise NbboSourceError("source response exceeds row cap")
    candidates: list[SourceQuote] = []
    seen_at: dict[datetime, SourceQuote] = {}
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise NbboSourceError("source quote row is malformed")
        required = {
            "symbol",
            "expiration",
            "strike",
            "right",
            "timestamp",
            "bid_size",
            "ask_size",
            "bid_exchange",
            "ask_exchange",
            "bid_condition",
            "ask_condition",
            "bid",
            "ask",
        }
        if set(raw) != required:
            raise NbboSourceError("source quote fields are not exact")
        try:
            source_strike, _ = _canonical_strike(str(raw["strike"]))
        except NbboCohortError as exc:
            raise NbboSourceError("source quote strike is malformed") from exc
        if (
            raw["symbol"] != exact_contract["root"]
            or raw["expiration"] != exact_contract["expiration"]
            or str(raw["right"]).lower() != exact_contract["right"]
            or source_strike != exact_contract["strike"]
        ):
            raise NbboSourceError("source returned a different exact contract")
        event_at = _source_clock(raw["timestamp"])
        if event_at < boundary_at:
            continue
        if query_end_at is not None and event_at > query_end_at:
            raise NbboSourceError("source returned a quote after the exact query end")
        if not _in_rth(event_at):
            continue
        try:
            bid = _decimal(raw["bid"], label="source bid")
            ask = _decimal(raw["ask"], label="source ask")
        except NbboCohortError as exc:
            raise NbboSourceError("source quote price is malformed") from exc
        bid_size = _source_int(raw["bid_size"], label="bid_size")
        ask_size = _source_int(raw["ask_size"], label="ask_size")
        bid_exchange = _source_int(raw["bid_exchange"], label="bid_exchange")
        ask_exchange = _source_int(raw["ask_exchange"], label="ask_exchange")
        if bid < 0 or ask < 0 or (bid > 0 and ask > 0 and ask < bid):
            continue
        bid_condition = _source_int(raw["bid_condition"], label="bid_condition")
        ask_condition = _source_int(raw["ask_condition"], label="ask_condition")
        selected_valid = (
            ask > 0
            and ask_size > 0
            and ask_condition in FIRM_OPRA_QUOTE_CONDITIONS
            and ask_exchange in KNOWN_THETA_EXCHANGES
            if role == "entry"
            else bid > 0
            and bid_size > 0
            and bid_condition in FIRM_OPRA_QUOTE_CONDITIONS
            and bid_exchange in KNOWN_THETA_EXCHANGES
        )
        if not selected_valid:
            continue
        quote = SourceQuote(
            event_at=event_at,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            bid_exchange=bid_exchange,
            ask_exchange=ask_exchange,
            bid_condition=bid_condition,
            ask_condition=ask_condition,
        )
        previous = seen_at.get(event_at)
        if previous is not None and previous != quote:
            raise NbboSourceError("source returned conflicting quotes at one timestamp")
        if previous is None:
            seen_at[event_at] = quote
            candidates.append(quote)
    if not candidates:
        return None
    return min(candidates, key=lambda quote: quote.event_at)


def source_query(
    *,
    contract: Mapping[str, Any],
    boundary_at: datetime,
    available_at: datetime,
    ceiling_at: datetime | None = None,
) -> dict[str, str]:
    exact = validate_contract(contract)
    boundary_at = _aware_utc(boundary_at, label="quote boundary")
    available_at = _aware_utc(available_at, label="quote query clock")
    boundary_et = boundary_at.astimezone(ET)
    available_et = available_at.astimezone(ET)
    if boundary_et.date() != available_et.date():
        raise NbboCohortError("quote query crosses exchange sessions")
    opened, rth_close = _session_window(boundary_et.date())
    if not opened <= boundary_at < rth_close:
        raise NbboCohortError("quote boundary is outside NYSE RTH")
    end = min(available_at, rth_close)
    if ceiling_at is not None:
        ceiling = _aware_utc(ceiling_at, label="quote query ceiling")
        if ceiling.astimezone(ET).date() != boundary_et.date() or ceiling < boundary_at:
            raise NbboCohortError("quote query ceiling is outside the event session")
        end = min(end, ceiling)
    if end < boundary_at:
        raise NbboCohortError("quote query clock precedes the causal boundary")
    end_et = end.astimezone(ET)
    return {
        "symbol": exact["root"],
        "expiration": exact["expiration"].replace("-", ""),
        "strike": f"{Decimal(exact['strike']):.3f}",
        "right": exact["right"],
        "date": boundary_et.strftime("%Y%m%d"),
        "start_time": boundary_et.strftime("%H:%M:%S.%f")[:-3],
        "end_time": end_et.strftime("%H:%M:%S.%f")[:-3],
        "interval": SOURCE_INTERVAL,
        "format": "json",
    }


def validate_source_query(
    query: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    boundary_at: datetime,
    requested_at: datetime,
    observed_at: datetime,
    ceiling_at: datetime | None = None,
) -> tuple[dict[str, str], datetime]:
    """Validate and resolve the exact query that was sent to the local terminal."""

    if not isinstance(query, Mapping) or set(query) != _QUERY_FIELDS:
        raise NbboCohortError("source query fields are not exact")
    if not all(isinstance(value, str) for value in query.values()):
        raise NbboCohortError("source query values must be strings")
    clean = {key: str(query[key]) for key in sorted(_QUERY_FIELDS)}
    exact = validate_contract(contract)
    boundary = _aware_utc(boundary_at, label="quote boundary")
    requested = _aware_utc(requested_at, label="source request clock")
    observed = _aware_utc(observed_at, label="observation clock")
    if requested > observed:
        raise NbboCohortError("source request clock follows response availability")
    boundary_et = boundary.astimezone(ET)
    expected_static = {
        "symbol": exact["root"],
        "expiration": exact["expiration"].replace("-", ""),
        "strike": f"{Decimal(exact['strike']):.3f}",
        "right": exact["right"],
        "date": boundary_et.strftime("%Y%m%d"),
        "start_time": boundary_et.strftime("%H:%M:%S.%f")[:-3],
        "interval": SOURCE_INTERVAL,
        "format": "json",
    }
    for key, expected in expected_static.items():
        if clean[key] != expected:
            raise NbboCohortError(f"source query {key} disagrees with the event")
    expected_query = source_query(
        contract=exact,
        boundary_at=boundary,
        available_at=requested,
        ceiling_at=ceiling_at,
    )
    if clean != expected_query:
        raise NbboCohortError("source query differs from its request clock")
    try:
        parsed_end = datetime.strptime(
            clean["date"] + clean["end_time"], "%Y%m%d%H:%M:%S.%f"
        ).replace(tzinfo=ET)
    except ValueError as exc:
        raise NbboCohortError("source query end_time is malformed") from exc
    query_end = parsed_end.astimezone(timezone.utc)
    _, rth_close_utc = _session_window(boundary_et.date())
    if query_end < boundary or query_end > observed:
        raise NbboCohortError("source query end is outside its causal clocks")
    if query_end > rth_close_utc:
        raise NbboCohortError("source query end exceeds NYSE RTH")
    return clean, query_end


def build_observation(
    *,
    role: str,
    event: Mapping[str, Any],
    available_at: datetime,
    source_payload: Any | None,
    source_error: str | None = None,
    query: Mapping[str, Any] | None = None,
    request_started_at: datetime | None = None,
    source_response_body: bytes | None = None,
    query_ceiling_at: datetime | None = None,
    window_closed: bool = False,
) -> dict[str, Any]:
    if role not in {"entry", "exit"}:
        raise NbboCohortError("observation role is invalid")
    event = validate_event(event)
    boundary = effective_boundary(event)
    event_available = _utc(event["available_at"], label="event available_at")
    available = _aware_utc(available_at, label="observation clock")
    boundary_et = boundary.astimezone(ET)
    boundary_in_rth = _in_rth(boundary)
    session_close = (
        _session_window(boundary_et.date())[1] if boundary_in_rth else boundary
    )
    ceiling = _aware_utc(
        query_ceiling_at or session_close,
        label="quote query ceiling",
    )
    if ceiling < boundary or ceiling.astimezone(ET).date() != boundary_et.date():
        raise NbboCohortError("quote query ceiling is outside the event session")
    exact_query: dict[str, str] | None = None
    query_end: datetime | None = None
    request_attempted = (
        query is not None or source_payload is not None or source_error is not None
    )
    requested: datetime | None = None
    if request_attempted:
        if request_started_at is None:
            raise NbboCohortError(
                "attempted quote requires explicit request_started_at"
            )
        requested = _aware_utc(
            request_started_at,
            label="source request clock",
        )
        if requested < event_available:
            raise NbboCohortError("source request precedes event availability")
        raw_query = query or source_query(
            contract=event["contract"],
            boundary_at=boundary,
            available_at=requested,
            ceiling_at=ceiling,
        )
        exact_query, query_end = validate_source_query(
            raw_query,
            contract=event["contract"],
            boundary_at=boundary,
            requested_at=requested,
            observed_at=available,
            ceiling_at=ceiling,
        )
    quote: SourceQuote | None = None
    reason: str | None = None
    response_receipt: dict[str, Any] | None = None
    if source_payload is not None:
        if source_response_body is None:
            raise NbboSourceError("exact source response bytes are required")
        if not isinstance(source_response_body, bytes) or not source_response_body:
            raise NbboSourceError("exact source response bytes are malformed")
        response_body = source_response_body
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise NbboSourceError("source response exceeds byte cap")
        parsed_response = strict_json_value(
            response_body, label="source response bytes"
        )
        if parsed_response != source_payload:
            raise NbboSourceError("source response bytes disagree with parsed payload")
        response_receipt = {
            "sha256": sha256(response_body).hexdigest(),
            "bytes": len(response_body),
        }
    elif source_response_body is not None:
        raise NbboSourceError("source response bytes lack a parsed payload")
    if not boundary_in_rth:
        if request_attempted:
            raise NbboCohortError("cannot query an event outside NYSE RTH")
        reason = "BOUNDARY_OUTSIDE_RTH"
    elif available < event_available:
        if request_attempted:
            raise NbboCohortError("cannot query before event availability")
        reason = "BOUNDARY_NOT_YET_AVAILABLE"
    elif window_closed:
        if request_attempted:
            raise NbboCohortError("closed quote window cannot carry a new request")
        reason = "QUOTE_WINDOW_CLOSED"
    elif not request_attempted:
        raise NbboCohortError("in-window observation requires an exact source request")
    elif source_error is not None or source_payload is None:
        reason = "SOURCE_UNAVAILABLE"
    else:
        quote = parse_quote_response(
            source_payload,
            role=role,
            contract=event["contract"],
            boundary_at=boundary,
            query_end_at=query_end,
        )
        if quote is None:
            reason = (
                "QUOTE_WINDOW_CLOSED"
                if requested is not None and requested >= ceiling
                else "NO_VALID_NBBO_AFTER_BOUNDARY"
            )
        elif quote.event_at > available:
            raise NbboSourceError("selected quote event is after availability clock")
        elif (available - quote.event_at).total_seconds() > MAX_AVAILABLE_LAG_SECONDS:
            quote = None
            reason = "FIRST_QUOTE_AVAILABLE_TOO_LATE"
    admitted = quote is not None
    quote_payload: dict[str, Any] | None = None
    if quote is not None:
        quote_payload = {
            "event_at": utc_text(quote.event_at),
            "available_at": utc_text(available),
            "bid": format(quote.bid, "f"),
            "ask": format(quote.ask, "f"),
            "bid_size": quote.bid_size,
            "ask_size": quote.ask_size,
            "bid_exchange": quote.bid_exchange,
            "ask_exchange": quote.ask_exchange,
            "bid_condition": quote.bid_condition,
            "ask_condition": quote.ask_condition,
            "selected_side": "ask" if role == "entry" else "bid",
            "selected_price": format(quote.ask if role == "entry" else quote.bid, "f"),
            "event_to_available_lag_seconds": round(
                (available - quote.event_at).total_seconds(), 6
            ),
        }
    payload: dict[str, Any] = {
        "schema": OBSERVATION_SCHEMA,
        "observation_id": None,
        "role": role,
        "status": "admitted" if admitted else "unavailable",
        "reason": reason,
        "cohort_rule_id": COHORT_RULE_ID,
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "benchmark_effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
        "phase": PROSPECTIVE_PHASE,
        "event": {
            "event_id": event["event_id"],
            "sha256": sha256(canonical_json_bytes(event)).hexdigest(),
        },
        "system": event["system"],
        "stable_signal_id": event["stable_signal_id"],
        "contract": event["contract"],
        "boundary_at": utc_text(boundary),
        "observed_at": utc_text(available),
        "source": {
            "endpoint": SOURCE_ENDPOINT,
            "source_class": SOURCE_CLASS,
            "interval": SOURCE_INTERVAL,
            "request_attempted": request_attempted,
            "requested_at": utc_text(requested) if requested is not None else None,
            "query_ceiling_at": utc_text(ceiling),
            "query": exact_query,
            "query_sha256": (
                sha256(canonical_json_bytes(exact_query)).hexdigest()
                if exact_query is not None
                else None
            ),
            "response": response_receipt,
            "raw_response_retained_private": response_receipt is not None,
            "private_only": True,
            "nbbo": True,
            "executable_fill_claim": False,
        },
        "quote": quote_payload,
        "source_error_class": source_error,
        "authority": dict(FALSE_AUTHORITY),
    }
    payload["observation_id"] = _content_id("nbboobs_", payload, "observation_id")
    return validate_observation(payload)


def validate_observation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise NbboCohortError("observation must be an object")
    observation = dict(raw)
    if observation.get("schema") != OBSERVATION_SCHEMA:
        raise NbboCohortError("observation schema mismatch")
    if observation.get("cohort_rule_id") != COHORT_RULE_ID:
        raise NbboCohortError("observation cohort rule mismatch")
    if observation.get("benchmark_digest_sha256") != BENCHMARK_DIGEST:
        raise NbboCohortError("observation benchmark digest mismatch")
    if (
        observation.get("benchmark_effective_freeze_at")
        != BENCHMARK_EFFECTIVE_FREEZE_AT
    ):
        raise NbboCohortError("observation benchmark freeze mismatch")
    if observation.get("phase") != PROSPECTIVE_PHASE:
        raise NbboCohortError("observation phase mismatch")
    if observation.get("authority") != FALSE_AUTHORITY:
        raise NbboCohortError("observation authority is not all false")
    contract = validate_contract(observation.get("contract"))
    if observation.get("role") not in {"entry", "exit"}:
        raise NbboCohortError("observation role is invalid")
    boundary = _utc(observation.get("boundary_at"), label="observation boundary_at")
    observed = _utc(observation.get("observed_at"), label="observation observed_at")
    source = observation.get("source")
    if not isinstance(source, Mapping):
        raise NbboCohortError("observation source receipt is malformed")
    expected_source_constants = {
        "endpoint": SOURCE_ENDPOINT,
        "source_class": SOURCE_CLASS,
        "interval": SOURCE_INTERVAL,
        "private_only": True,
        "nbbo": True,
        "executable_fill_claim": False,
    }
    for key, expected in expected_source_constants.items():
        if source.get(key) != expected:
            raise NbboCohortError(f"observation source {key} mismatch")
    request_attempted = source.get("request_attempted")
    if not isinstance(request_attempted, bool):
        raise NbboCohortError("observation source request flag is malformed")
    query = source.get("query")
    query_sha = source.get("query_sha256")
    requested_text = source.get("requested_at")
    ceiling = _utc(source.get("query_ceiling_at"), label="source query_ceiling_at")
    if (
        ceiling < boundary
        or ceiling.astimezone(ET).date() != boundary.astimezone(ET).date()
    ):
        raise NbboCohortError("observation source query ceiling is invalid")
    query_end: datetime | None = None
    if request_attempted:
        requested_at = _utc(requested_text, label="source requested_at")
        clean_query, query_end = validate_source_query(
            query,
            contract=contract,
            boundary_at=boundary,
            requested_at=requested_at,
            observed_at=observed,
            ceiling_at=ceiling,
        )
        if query_sha != sha256(canonical_json_bytes(clean_query)).hexdigest():
            raise NbboCohortError("observation source query digest mismatch")
    elif query is not None or query_sha is not None or requested_text is not None:
        raise NbboCohortError("unattempted observation carries a source query")
    response_receipt = source.get("response")
    retained = source.get("raw_response_retained_private")
    if response_receipt is None:
        if retained is not False:
            raise NbboCohortError("missing source response has a retention claim")
    else:
        if retained is not True or not isinstance(response_receipt, Mapping):
            raise NbboCohortError("source response receipt is malformed")
        if set(response_receipt) != {"sha256", "bytes"}:
            raise NbboCohortError("source response receipt fields are not exact")
        if not isinstance(response_receipt.get("sha256"), str) or not _SHA_RE.fullmatch(
            response_receipt["sha256"]
        ):
            raise NbboCohortError("source response digest is malformed")
        if (
            not isinstance(response_receipt.get("bytes"), int)
            or isinstance(response_receipt["bytes"], bool)
            or not 0 < response_receipt["bytes"] <= MAX_RESPONSE_BYTES
        ):
            raise NbboCohortError("source response byte count is malformed")
    source_error = observation.get("source_error_class")
    if source_error is not None and (
        not isinstance(source_error, str) or not source_error or not request_attempted
    ):
        raise NbboCohortError("observation source error class is malformed")
    status_value = observation.get("status")
    quote = observation.get("quote")
    reason = observation.get("reason")
    if status_value == "admitted":
        if (
            not isinstance(quote, Mapping)
            or reason is not None
            or not request_attempted
            or source_error is not None
            or query_end is None
            or response_receipt is None
        ):
            raise NbboCohortError("admitted observation lacks quote")
        if quote.get("selected_side") != (
            "ask" if observation["role"] == "entry" else "bid"
        ):
            raise NbboCohortError("observation selected side is wrong")
        bid = _decimal(quote.get("bid"), label="quote.bid")
        ask = _decimal(quote.get("ask"), label="quote.ask")
        if bid < 0 or ask < 0:
            raise NbboCohortError("observation quote price is invalid")
        if bid > 0 and ask > 0 and ask < bid:
            raise NbboCohortError("observation NBBO is crossed")
        bid_size = _source_int(quote.get("bid_size"), label="quote.bid_size")
        ask_size = _source_int(quote.get("ask_size"), label="quote.ask_size")
        bid_exchange = _source_int(
            quote.get("bid_exchange"), label="quote.bid_exchange"
        )
        ask_exchange = _source_int(
            quote.get("ask_exchange"), label="quote.ask_exchange"
        )
        bid_condition = _source_int(
            quote.get("bid_condition"), label="quote.bid_condition"
        )
        ask_condition = _source_int(
            quote.get("ask_condition"), label="quote.ask_condition"
        )
        selected_valid = (
            ask > 0
            and ask_size > 0
            and ask_condition in FIRM_OPRA_QUOTE_CONDITIONS
            and ask_exchange in KNOWN_THETA_EXCHANGES
            if observation["role"] == "entry"
            else bid > 0
            and bid_size > 0
            and bid_condition in FIRM_OPRA_QUOTE_CONDITIONS
            and bid_exchange in KNOWN_THETA_EXCHANGES
        )
        if not selected_valid:
            raise NbboCohortError(
                "observation selected quote side is not valid firm NBBO"
            )
        selected = _decimal(quote.get("selected_price"), label="selected price")
        expected_selected = ask if observation["role"] == "entry" else bid
        if selected != expected_selected:
            raise NbboCohortError("observation selected price disagrees with its side")
        quote_event = _utc(quote.get("event_at"), label="quote.event_at")
        quote_available = _utc(quote.get("available_at"), label="quote.available_at")
        if quote_available != observed:
            raise NbboCohortError("quote availability differs from observation clock")
        if quote_event < boundary or quote_event > query_end or quote_event > observed:
            raise NbboCohortError(
                "observation quote is outside its causal query window"
            )
        if not _in_rth(quote_event):
            raise NbboCohortError("observation quote is outside NYSE RTH")
        lag = quote.get("event_to_available_lag_seconds")
        if not isinstance(lag, (int, float)) or isinstance(lag, bool):
            raise NbboCohortError("observation quote lag is malformed")
        if lag < 0 or lag > MAX_AVAILABLE_LAG_SECONDS:
            raise NbboCohortError("observation quote lag exceeds the frozen fence")
        expected_lag = round((observed - quote_event).total_seconds(), 6)
        if Decimal(str(lag)) != Decimal(str(expected_lag)):
            raise NbboCohortError("observation quote lag disagrees with its clocks")
    elif status_value == "unavailable":
        allowed_reasons = _TERMINAL_UNAVAILABLE_REASONS | {
            "BOUNDARY_NOT_YET_AVAILABLE",
            "SOURCE_UNAVAILABLE",
            "NO_VALID_NBBO_AFTER_BOUNDARY",
        }
        if quote is not None or reason not in allowed_reasons:
            raise NbboCohortError("unavailable observation lacks reason")
        if (
            reason in {"SOURCE_UNAVAILABLE", "NO_VALID_NBBO_AFTER_BOUNDARY"}
            and not request_attempted
        ):
            raise NbboCohortError("source unavailability lacks an exact request")
        if reason == "SOURCE_UNAVAILABLE" and source_error is None:
            raise NbboCohortError("source unavailability lacks an error class")
        if reason != "SOURCE_UNAVAILABLE" and source_error is not None:
            raise NbboCohortError("non-source failure carries a source error class")
        if (
            reason in {"NO_VALID_NBBO_AFTER_BOUNDARY", "FIRST_QUOTE_AVAILABLE_TOO_LATE"}
            and response_receipt is None
        ):
            raise NbboCohortError("no-valid-quote receipt lacks its source response")
        if (
            reason == "QUOTE_WINDOW_CLOSED"
            and request_attempted
            and response_receipt is None
        ):
            raise NbboCohortError(
                "closed quote-window attempt lacks its source response"
            )
        if (
            reason in _TERMINAL_UNAVAILABLE_REASONS
            and reason
            not in {
                "FIRST_QUOTE_AVAILABLE_TOO_LATE",
                "QUOTE_WINDOW_CLOSED",
            }
            and request_attempted
        ):
            raise NbboCohortError("unattempted terminal reason carries a query")
    else:
        raise NbboCohortError("observation status is invalid")
    expected_id = _content_id("nbboobs_", observation, "observation_id")
    if observation.get("observation_id") != expected_id:
        raise NbboCohortError("observation content identity mismatch")
    validate_schema(observation, label="NBBO observation")
    return observation


def net_return_pct(entry_ask: Any, exit_bid: Any) -> Decimal:
    entry = _decimal(entry_ask, label="entry ask")
    exit_value = _decimal(exit_bid, label="exit bid")
    if entry <= 0 or exit_value < 0:
        raise NbboCohortError("return prices are outside bounds")
    entry_cost = Decimal(100) * entry + FEE_PER_SIDE_USD
    exit_value_net = Decimal(100) * exit_value - FEE_PER_SIDE_USD
    return ((exit_value_net - entry_cost) / entry_cost * Decimal(100)).quantize(
        Decimal("0.000001")
    )


def observation_pointer(observation: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_observation(observation)
    body = canonical_json_bytes(validated)
    return {
        "observation_id": validated["observation_id"],
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
    }


def bind_observation_to_event(
    observation: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    """Prove that a content-valid observation belongs to one exact source event."""

    row = validate_observation(observation)
    source_event = validate_event(event)
    expected_role = "entry" if source_event["kind"] == "enroll" else "exit"
    expected_pointer = {
        "event_id": source_event["event_id"],
        "sha256": sha256(canonical_json_bytes(source_event)).hexdigest(),
    }
    expected = {
        "event": expected_pointer,
        "role": expected_role,
        "system": source_event["system"],
        "stable_signal_id": source_event["stable_signal_id"],
        "contract": source_event["contract"],
        "boundary_at": utc_text(effective_boundary(source_event)),
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise NbboCohortError(f"observation {key} does not bind its source event")
    source = row["source"]
    if source["request_attempted"]:
        requested = _utc(source["requested_at"], label="source requested_at")
        event_available = _utc(source_event["available_at"], label="event available_at")
        if requested < event_available:
            raise NbboCohortError(
                "observation source request precedes event availability"
            )
    return row


def _capture_slots(session: date) -> list[datetime]:
    opened, closed = _session_window(session)
    slots: list[datetime] = []
    cursor = opened
    while cursor < closed:
        slots.append(cursor)
        cursor += timedelta(seconds=CAPTURE_CADENCE_SECONDS)
    return slots


def _ratio_text(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.000000"
    return format(
        (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001")),
        "f",
    )


def _maximum_capture_gap(
    successful_slots: Sequence[datetime], *, opened: datetime, closed: datetime
) -> int | None:
    if not successful_slots:
        return None
    ordered = sorted(set(successful_slots))
    gaps = [ordered[0] - opened]
    gaps.extend(later - earlier for earlier, later in pairwise(ordered))
    gaps.append(closed - ordered[-1])
    maximum = max(gaps)
    microseconds = maximum // timedelta(microseconds=1)
    return (microseconds + 999_999) // 1_000_000


def build_session_coverage(
    *,
    capture_receipts: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    built_at: datetime,
) -> tuple[dict[str, Any], set[str], int]:
    """Build the frozen same-window two-system coverage reconciliation."""

    built = _aware_utc(built_at, label="coverage build clock")
    clean_events = [validate_event(row) for row in events]
    clean_receipts = [validate_capture_receipt(row) for row in capture_receipts]
    producer_rules: dict[str, str] = {}
    for receipt in clean_receipts:
        digest = receipt["producer_rule_sha256"]
        if digest is None:
            continue
        prior = producer_rules.get(receipt["comparison_system"])
        if prior is not None and prior != digest:
            raise NbboCohortError(
                "capture producer rule changed inside the frozen cohort"
            )
        producer_rules[receipt["comparison_system"]] = digest

    freeze = _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze")
    first_candidate = freeze.astimezone(ET).date()
    final_candidate = built.astimezone(ET).date()
    session_dates = {
        session.isoformat()
        for session in nyse_calendar.sessions_between(first_candidate, final_candidate)
        if _session_window(session)[0] >= freeze
    }
    session_dates.update(receipt["session_date"] for receipt in clean_receipts)
    session_dates.update(
        event["event_at"][:10]
        for event in clean_events
        if nyse_calendar.is_session(
            _utc(event["event_at"], label="event_at").astimezone(ET).date()
        )
    )

    event_by_id = {event["event_id"]: event for event in clean_events}
    enrollment_ids_by_session_system: dict[tuple[str, str], set[str]] = {}
    for event in clean_events:
        if event["kind"] != "enroll":
            continue
        event_at = _utc(event["event_at"], label="event_at")
        if not _in_rth(event_at):
            continue
        comparison_system = (
            "momoedge" if event["system"] == "momoedge" else "mastermindx"
        )
        session_text = event_at.astimezone(ET).date().isoformat()
        enrollment_ids_by_session_system.setdefault(
            (session_text, comparison_system), set()
        ).add(event["event_id"])

    receipts_by_session_system: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for receipt in clean_receipts:
        receipts_by_session_system.setdefault(
            (receipt["session_date"], receipt["comparison_system"]), []
        ).append(receipt)

    session_rows: list[dict[str, Any]] = []
    covered_dates: set[str] = set()
    total_silent_drops = 0
    eligible_finalized = 0
    for session_text in sorted(session_dates):
        session = date.fromisoformat(session_text)
        if not nyse_calendar.is_session(session):
            raise NbboCohortError("coverage references a non-session date")
        opened, closed = _session_window(session)
        slots = _capture_slots(session)
        slot_texts = {utc_text(slot): slot for slot in slots}
        full_post_freeze = opened >= freeze
        finalized = built >= closed
        if full_post_freeze and finalized:
            eligible_finalized += 1
        by_system: dict[str, dict[str, Any]] = {}
        successful_by_system: dict[str, set[datetime]] = {}
        successful_receipts_by_system: dict[str, dict[datetime, dict[str, Any]]] = {}
        session_missing_refs = 0
        session_duplicate_refs = 0
        session_invalid_refs = 0
        for system in sorted(_CAPTURE_SYSTEMS):
            attempts = receipts_by_session_system.get((session_text, system), [])
            successes_by_slot: dict[str, list[dict[str, Any]]] = {}
            referenced: list[str] = []
            for receipt in attempts:
                if receipt["disposition"] == "unavailable":
                    continue
                successes_by_slot.setdefault(receipt["scheduled_at"], []).append(
                    receipt
                )
                referenced.extend(receipt["new_enrollment_event_ids"])
            for slot, rows in successes_by_slot.items():
                if slot not in slot_texts:
                    raise NbboCohortError("capture success is outside its session grid")
                if len(rows) > 1:
                    distinct = {canonical_json_bytes(row) for row in rows}
                    if len(distinct) > 1:
                        raise NbboCohortError(
                            "one system has conflicting successful captures in one slot"
                        )
            successful_slots = {
                slot_texts[slot] for slot in successes_by_slot if slot in slot_texts
            }
            successful_by_system[system] = successful_slots
            successful_receipts_by_system[system] = {
                slot_texts[slot]: rows[0]
                for slot, rows in successes_by_slot.items()
                if slot in slot_texts
            }
            expected_ids = enrollment_ids_by_session_system.get(
                (session_text, system), set()
            )
            referenced_set = set(referenced)
            session_duplicate_refs += len(referenced) - len(referenced_set)
            session_missing_refs += len(expected_ids - referenced_set)
            for event_id in referenced_set:
                event = event_by_id.get(event_id)
                if event is None or event["kind"] != "enroll":
                    session_invalid_refs += 1
                    continue
                event_system = (
                    "momoedge" if event["system"] == "momoedge" else "mastermindx"
                )
                event_session = (
                    _utc(event["event_at"], label="event_at")
                    .astimezone(ET)
                    .date()
                    .isoformat()
                )
                if (
                    event_system != system
                    or event_session != session_text
                    or not _in_rth(_utc(event["event_at"], label="event_at"))
                ):
                    session_invalid_refs += 1
            for receipt in attempts:
                if receipt["disposition"] == "unavailable":
                    continue
                scheduled_at = _utc(
                    receipt["scheduled_at"], label="capture scheduled_at"
                )
                capture_event_at = _utc(
                    receipt["capture_event_at"], label="capture event_at"
                )
                for event_id in receipt["new_enrollment_event_ids"]:
                    event = event_by_id.get(event_id)
                    if event is None or event["kind"] != "enroll":
                        continue
                    event_system = (
                        "momoedge" if event["system"] == "momoedge" else "mastermindx"
                    )
                    event_session = (
                        _utc(event["event_at"], label="event_at")
                        .astimezone(ET)
                        .date()
                        .isoformat()
                    )
                    if event_system != system or event_session != session_text:
                        continue
                    if not _in_rth(_utc(event["event_at"], label="event_at")):
                        continue
                    event_available_at = _utc(
                        event["available_at"], label="event available_at"
                    )
                    if not scheduled_at <= event_available_at <= capture_event_at:
                        session_invalid_refs += 1
            successful_count = len(successful_slots)
            by_system[system] = {
                "attempt_count": len(attempts),
                "unavailable_attempt_count": sum(
                    1 for row in attempts if row["disposition"] == "unavailable"
                ),
                "successful_slot_count": successful_count,
                "new_call_slot_count": sum(
                    1
                    for rows in successes_by_slot.values()
                    if rows[0]["disposition"] == "new_calls_observed"
                ),
                "zero_new_call_slot_count": sum(
                    1
                    for rows in successes_by_slot.values()
                    if rows[0]["disposition"]
                    in {"no_new_calls_observed", "selector_abstained"}
                ),
                "expected_slot_count": len(slots),
                "capture_coverage_ratio": _ratio_text(successful_count, len(slots)),
                "maximum_capture_gap_seconds": _maximum_capture_gap(
                    [
                        _utc(row["completed_at"], label="capture completed_at")
                        for row in successful_receipts_by_system[system].values()
                    ],
                    opened=opened,
                    closed=closed,
                ),
                "observed_new_call_count": sum(
                    row["observed_new_call_count"]
                    for rows in successes_by_slot.values()
                    for row in rows[:1]
                ),
                "producer_rule_sha256": producer_rules.get(system),
            }

        common_slots = successful_by_system.get(
            "mastermindx", set()
        ) & successful_by_system.get("momoedge", set())
        common_ratio_text = _ratio_text(len(common_slots), len(slots))
        common_ratio = Decimal(common_ratio_text)
        common_observation_clocks = [
            max(
                _utc(
                    successful_receipts_by_system["mastermindx"][slot]["completed_at"],
                    label="MastermindX capture completed_at",
                ),
                _utc(
                    successful_receipts_by_system["momoedge"][slot]["completed_at"],
                    label="MomoEdge capture completed_at",
                ),
            )
            for slot in common_slots
        ]
        common_gap = _maximum_capture_gap(
            common_observation_clocks, opened=opened, closed=closed
        )
        exclusions: list[str] = []
        if not full_post_freeze:
            exclusions.append("PARTIAL_FREEZE_SESSION")
        if not finalized:
            exclusions.append("SESSION_IN_PROGRESS")
        if common_ratio < MIN_CAPTURE_COVERAGE_RATIO:
            exclusions.append("COMMON_CAPTURE_COVERAGE_BELOW_95_PERCENT")
        if common_gap is None:
            exclusions.append("NO_COMMON_AUTHENTICATED_CAPTURE")
        elif common_gap > MAX_CAPTURE_GAP_SECONDS:
            exclusions.append("COMMON_CAPTURE_GAP_OVER_900_SECONDS")
        if session_missing_refs or session_duplicate_refs or session_invalid_refs:
            exclusions.append("EVENT_RECONCILIATION_INCOMPLETE")
        covered = not exclusions
        if covered:
            covered_dates.add(session_text)
        silent_drops = (
            session_missing_refs + session_duplicate_refs + session_invalid_refs
        )
        total_silent_drops += silent_drops
        session_rows.append(
            {
                "session_date": session_text,
                "session_open_at": utc_text(opened),
                "session_close_at": utc_text(closed),
                "finalized": finalized,
                "expected_slot_count": len(slots),
                "common_successful_slot_count": len(common_slots),
                "common_capture_coverage_ratio": common_ratio_text,
                "common_maximum_capture_gap_seconds": common_gap,
                "event_reconciliation": {
                    "missing_enrollment_reference_count": session_missing_refs,
                    "duplicate_enrollment_reference_count": session_duplicate_refs,
                    "invalid_enrollment_reference_count": session_invalid_refs,
                },
                "covered": covered,
                "exclusion_reasons": exclusions,
                "by_system": by_system,
            }
        )

    covered_count = len(covered_dates)
    payload = {
        "capture_rule_id": CAPTURE_RULE_ID,
        "capture_cadence_seconds": CAPTURE_CADENCE_SECONDS,
        "maximum_authenticated_capture_gap_seconds": MAX_CAPTURE_GAP_SECONDS,
        "minimum_capture_coverage_ratio": format(MIN_CAPTURE_COVERAGE_RATIO, "f"),
        "eligible_finalized_session_count": eligible_finalized,
        "covered_session_count": covered_count,
        "excluded_finalized_session_count": eligible_finalized - covered_count,
        "covered_session_ratio": _ratio_text(covered_count, eligible_finalized),
        "covered_session_dates": sorted(covered_dates),
        "sessions": session_rows,
    }
    return payload, covered_dates, total_silent_drops


def build_snapshot(
    *,
    events: Sequence[Mapping[str, Any]],
    event_receipt: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    built_at: datetime,
    capture_receipts: Sequence[Mapping[str, Any]] = (),
    capture_ledger_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    enrollments, terminals = reconcile_events(events)
    if capture_ledger_receipt is None:
        capture_ledger_receipt = {
            "sha256": sha256(b"").hexdigest(),
            "bytes": 0,
            "row_count": 0,
        }
    session_coverage, covered_dates, silent_drop_count = build_session_coverage(
        capture_receipts=capture_receipts,
        events=events,
        built_at=built_at,
    )
    event_by_id = {
        row["event_id"]: row for row in (validate_event(raw) for raw in events)
    }
    validated_observations: list[dict[str, Any]] = []
    seen_observations: set[str] = set()
    for raw in observations:
        basic = validate_observation(raw)
        event = event_by_id.get(basic["event"]["event_id"])
        if event is None:
            raise NbboCohortError("observation references an unknown cohort event")
        row = bind_observation_to_event(basic, event)
        if row["observation_id"] in seen_observations:
            raise NbboCohortError("snapshot contains a duplicate observation")
        seen_observations.add(row["observation_id"])
        validated_observations.append(row)
    by_event_role: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in validated_observations:
        by_event_role.setdefault((row["event"]["event_id"], row["role"]), []).append(
            row
        )
    rows: list[dict[str, Any]] = []
    complete = 0
    quote_complete = 0
    uncovered_quote_complete = 0
    for enrollment in enrollments:
        entry_candidates = [
            row
            for row in by_event_role.get((enrollment["event_id"], "entry"), [])
            if row["status"] == "admitted"
        ]
        if len(entry_candidates) > 1:
            unique_quotes = {
                canonical_json_bytes(row["quote"]) for row in entry_candidates
            }
            if len(unique_quotes) != 1:
                raise NbboCohortError("enrollment has conflicting admitted entries")
        entry = (
            min(entry_candidates, key=lambda row: row["quote"]["event_at"])
            if entry_candidates
            else None
        )
        terminal = terminals.get(enrollment["event_id"])
        exit_candidates: list[dict[str, Any]] = []
        if terminal is not None:
            exit_candidates = [
                row
                for row in by_event_role.get((terminal["event_id"], "exit"), [])
                if row["status"] == "admitted"
            ]
            if len(exit_candidates) > 1:
                unique_quotes = {
                    canonical_json_bytes(row["quote"]) for row in exit_candidates
                }
                if len(unique_quotes) != 1:
                    raise NbboCohortError("enrollment has conflicting admitted exits")
        exit_row = (
            min(exit_candidates, key=lambda row: row["quote"]["event_at"])
            if exit_candidates
            else None
        )
        return_value: str | None = None
        quote_is_complete = False
        completion_reason: str
        if entry is None:
            completion_reason = "ENTRY_UNAVAILABLE"
        elif terminal is None:
            completion_reason = "TERMINAL_PENDING"
        elif exit_row is None:
            completion_reason = "EXIT_UNAVAILABLE"
        elif _utc(entry["quote"]["event_at"], label="entry quote event_at") > _utc(
            terminal["event_at"], label="terminal event_at"
        ) or _utc(exit_row["quote"]["event_at"], label="exit quote event_at") < _utc(
            entry["quote"]["event_at"], label="entry quote event_at"
        ):
            completion_reason = "ENTRY_AFTER_TERMINAL"
        else:
            quote_is_complete = True
            quote_complete += 1
            issue_session = (
                _utc(enrollment["event_at"], label="enrollment event_at")
                .astimezone(ET)
                .date()
                .isoformat()
            )
            if issue_session in covered_dates:
                return_value = format(
                    net_return_pct(
                        entry["quote"]["selected_price"],
                        exit_row["quote"]["selected_price"],
                    ),
                    "f",
                )
                completion_reason = "COMPLETE"
                complete += 1
            else:
                completion_reason = "UNCOVERED_CAPTURE_SESSION"
                uncovered_quote_complete += 1
        rows.append(
            {
                "system": enrollment["system"],
                "stable_signal_id": enrollment["stable_signal_id"],
                "enrollment_event_id": enrollment["event_id"],
                "terminal_event_id": terminal["event_id"] if terminal else None,
                "contract": enrollment["contract"],
                "entry_observation": observation_pointer(entry) if entry else None,
                "exit_observation": observation_pointer(exit_row) if exit_row else None,
                "net_return_pct": return_value,
                "quote_complete": quote_is_complete,
                "complete": return_value is not None,
                "completion_reason": completion_reason,
            }
        )
    rows.sort(key=lambda row: (row["system"], row["stable_signal_id"]))
    by_system: dict[str, dict[str, int]] = {}
    for system in ("mastermindx_prophet", "mastermindx_selector", "momoedge"):
        system_rows = [row for row in rows if row["system"] == system]
        system_complete = sum(1 for row in system_rows if row["complete"])
        by_system[system] = {
            "enrollment_count": len(system_rows),
            "terminal_count": sum(
                1 for row in system_rows if row["terminal_event_id"] is not None
            ),
            "complete_outcome_count": system_complete,
            "incomplete_outcome_count": len(system_rows) - system_complete,
            "quote_complete_outcome_count": sum(
                1 for row in system_rows if row["quote_complete"]
            ),
            "uncovered_quote_complete_count": sum(
                1
                for row in system_rows
                if row["completion_reason"] == "UNCOVERED_CAPTURE_SESSION"
            ),
        }
    pointers = sorted(
        (observation_pointer(row) for row in validated_observations),
        key=lambda pointer: pointer["observation_id"],
    )
    payload: dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_id": None,
        "cohort_rule_id": COHORT_RULE_ID,
        "quote_rule_id": QUOTE_RULE_ID,
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "benchmark_effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
        "phase": PROSPECTIVE_PHASE,
        "built_at": utc_text(built_at),
        "event_ledger": dict(event_receipt),
        "capture_ledger": dict(capture_ledger_receipt),
        "observation_objects": pointers,
        "coverage": {
            "enrollment_count": len(enrollments),
            "terminal_count": len(terminals),
            "complete_outcome_count": complete,
            "incomplete_outcome_count": len(enrollments) - complete,
            "quote_complete_outcome_count": quote_complete,
            "uncovered_quote_complete_count": uncovered_quote_complete,
            "silent_drop_count": silent_drop_count,
            "by_system": by_system,
            "session_coverage": session_coverage,
        },
        "rows": rows,
        "authority": dict(FALSE_AUTHORITY),
    }
    payload["snapshot_id"] = _content_id("nbbosnap_", payload, "snapshot_id")
    validate_schema(payload, label="NBBO cohort snapshot")
    return payload


def _fsync_dir(path: Path) -> None:
    fd = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_owned_private_directory(path: Path, *, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NbboCohortError(f"cannot inspect {label}: {exc}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
    ):
        raise NbboCohortError(f"{label} must be an owned 0700 directory")


def _mkdir_private_durable(path: Path) -> None:
    """Create a private directory chain and persist every new parent link."""

    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise NbboCohortError("private state path contains a symlink")
        missing.append(cursor)
        if cursor == cursor.parent:
            raise NbboCohortError("private state root has no safe parent")
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise NbboCohortError("private state parent is not a directory")
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            pass
        _validate_owned_private_directory(directory, label="new private directory")
        _fsync_dir(directory.parent)


def _validate_private_dir(path: Path, *, create: bool) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise NbboCohortError("private state root must be absolute")
    cursor = Path(expanded.anchor)
    for part in expanded.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise NbboCohortError("private state path contains a symlink")
    resolved = expanded.resolve()
    repo = Path(__file__).resolve().parents[1]
    if resolved == repo or repo in resolved.parents:
        raise NbboCohortError("private state root cannot be inside the repository")
    if resolved in {Path(resolved.anchor), Path.home().resolve()}:
        raise NbboCohortError("private state root is too broad")
    if {"site", "site.served"}.intersection(resolved.parts):
        raise NbboCohortError("private state root cannot be public")
    if create:
        _mkdir_private_durable(resolved)
    _validate_owned_private_directory(resolved, label="private state root")
    # Re-prove a link left visible by an interrupted parent fsync.
    _fsync_dir(resolved.parent)
    return resolved


def _private_subdir(root: Path, name: str) -> Path:
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name) is None:
        raise NbboCohortError("private subdirectory name is unsafe")
    path = root / name
    if path.is_symlink():
        raise NbboCohortError(f"private subdirectory {name} is a symlink")
    _mkdir_private_durable(path)
    _validate_owned_private_directory(path, label=f"private subdirectory {name}")
    _fsync_dir(root)
    return path


def _validate_private_file(path: Path, *, label: str, maximum: int) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NbboCohortError(f"cannot inspect {label}: {exc}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
    ):
        raise NbboCohortError(f"{label} must be an owned private 0600 file")
    if info.st_size > maximum:
        raise NbboCohortError(f"{label} exceeds its byte bound")
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise NbboCohortError(f"cannot read {label}: {exc}") from exc
    if len(body) != info.st_size:
        raise NbboCohortError(f"{label} changed while being read")
    return body


def _reconcile_staging(root: Path) -> Path:
    staging = _private_subdir(root, ".staging")
    entries = list(staging.iterdir())
    if len(entries) > MAX_EVENTS * 4:
        raise NbboCohortError("private staging namespace exceeds its fixed bound")
    for path in entries:
        info = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,240}\.tmp", path.name) is None
        ):
            raise NbboCohortError("private staging namespace contains an unowned path")
        path.unlink()
    _fsync_dir(staging)
    return staging


@contextmanager
def _private_store_lock(root: Path):
    """Serialize staging cleanup, immutable publication, and HEAD replacement."""

    root = _validate_private_dir(root, create=True)
    lock_path = root / ".store.lock"
    fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise NbboCohortError("private store lock must be an owned 0600 file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _write_private_bytes(
    root: Path,
    *,
    namespace: str,
    filename: str,
    body: bytes,
    maximum: int,
    label: str,
    _store_locked: bool = False,
) -> Path:
    if not body or len(body) > maximum:
        raise NbboCohortError(f"{label} is empty or exceeds its byte bound")
    root = _validate_private_dir(root, create=True)
    if not _store_locked:
        with _private_store_lock(root):
            return _write_private_bytes(
                root,
                namespace=namespace,
                filename=filename,
                body=body,
                maximum=maximum,
                label=label,
                _store_locked=True,
            )
    parent = _private_subdir(root, namespace)
    staging = _reconcile_staging(root)
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,220}", filename) is None:
        raise NbboCohortError(f"{label} filename is unsafe")
    target = parent / filename
    if target.exists() or target.is_symlink():
        existing = _validate_private_file(
            target, label=f"existing {label}", maximum=maximum
        )
        if existing != body:
            raise NbboCohortError(f"immutable {label} collision")
        _fsync_dir(parent)
        return target
    temporary = staging / (f"{filename}.{sha256(body).hexdigest()}.{uuid4().hex}.tmp")
    fd: int | None = None
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short private write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            existing = _validate_private_file(
                target, label=f"raced {label}", maximum=maximum
            )
            if existing != body:
                raise NbboCohortError(f"immutable {label} collision")
        _fsync_dir(parent)
    except NbboCohortError:
        raise
    except OSError as exc:
        raise NbboCohortError(f"cannot publish immutable {label}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()
            _fsync_dir(staging)
    stored = _validate_private_file(target, label=label, maximum=maximum)
    if stored != body:
        raise NbboCohortError(f"immutable {label} readback mismatch")
    return target


def write_immutable(root: Path, observation: Mapping[str, Any]) -> Path:
    validated = validate_observation(observation)
    body = canonical_json_bytes(validated)
    return _write_private_bytes(
        root,
        namespace="observations",
        filename=f"{validated['observation_id']}.json",
        body=body,
        maximum=2 * 1024 * 1024,
        label="NBBO observation",
    )


def write_source_response(root: Path, raw_body: bytes) -> dict[str, Any]:
    """Persist exact provider bytes privately and return their bound receipt."""

    if not isinstance(raw_body, bytes) or not raw_body:
        raise NbboSourceError("source response bytes are empty")
    if len(raw_body) > MAX_RESPONSE_BYTES:
        raise NbboSourceError("source response exceeds byte cap")
    strict_json_value(raw_body, label="private source response")
    digest = sha256(raw_body).hexdigest()
    path = _write_private_bytes(
        root,
        namespace="source_responses",
        filename=f"{digest}.json",
        body=raw_body,
        maximum=MAX_RESPONSE_BYTES,
        label="source response",
    )
    return {"sha256": digest, "bytes": path.stat().st_size}


def write_private_evidence(
    root: Path,
    *,
    namespace: str,
    raw_body: bytes,
    receipt: Mapping[str, Any],
) -> Path:
    """Store exact producer evidence bytes before admitting their ledger row."""

    if namespace not in {"event_evidence", "capture_evidence"}:
        raise NbboCohortError("private evidence namespace is not allowed")
    if not isinstance(raw_body, bytes) or not raw_body:
        raise NbboCohortError("private producer evidence is empty")
    if len(raw_body) > MAX_RESPONSE_BYTES:
        raise NbboCohortError("private producer evidence exceeds byte cap")
    if not isinstance(receipt, Mapping) or set(receipt) != {
        "schema",
        "object_sha256",
        "object_bytes",
    }:
        raise NbboCohortError("private producer evidence receipt is malformed")
    payload = strict_json_object(raw_body, label="private producer evidence")
    if payload.get("schema") != receipt.get("schema"):
        raise NbboCohortError("private producer evidence schema disagrees with receipt")
    digest = sha256(raw_body).hexdigest()
    if digest != receipt.get("object_sha256") or len(raw_body) != receipt.get(
        "object_bytes"
    ):
        raise NbboCohortError("private producer evidence bytes disagree with receipt")
    return _write_private_bytes(
        root,
        namespace=namespace,
        filename=f"{digest}.json",
        body=raw_body,
        maximum=MAX_RESPONSE_BYTES,
        label="producer evidence",
    )


def verify_private_evidence(
    root: Path, *, namespace: str, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    if namespace not in {"event_evidence", "capture_evidence"}:
        raise NbboCohortError("private evidence namespace is not allowed")
    if not isinstance(receipt, Mapping):
        raise NbboCohortError("private producer evidence receipt is malformed")
    digest = receipt.get("object_sha256")
    size = receipt.get("object_bytes")
    if (
        not isinstance(digest, str)
        or not _SHA_RE.fullmatch(digest)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 0 < size <= MAX_RESPONSE_BYTES
    ):
        raise NbboCohortError("private producer evidence receipt is malformed")
    directory = _private_subdir(_validate_private_dir(root, create=True), namespace)
    body = _validate_private_file(
        directory / f"{digest}.json",
        label="producer evidence",
        maximum=MAX_RESPONSE_BYTES,
    )
    if len(body) != size or sha256(body).hexdigest() != digest:
        raise NbboCohortError("private producer evidence receipt does not match bytes")
    payload = strict_json_object(body, label="private producer evidence")
    if payload.get("schema") != receipt.get("schema"):
        raise NbboCohortError("private producer evidence schema does not replay")
    return payload


def verify_event_evidence(root: Path, events: Sequence[Mapping[str, Any]]) -> None:
    for raw in events:
        event = validate_event(raw)
        evidence_payload = verify_private_evidence(
            root, namespace="event_evidence", receipt=event["private_evidence"]
        )
        validate_event_evidence_binding(evidence_payload, event)


def verify_capture_evidence(root: Path, receipts: Sequence[Mapping[str, Any]]) -> None:
    for raw in receipts:
        receipt = validate_capture_receipt(raw)
        evidence_payload = verify_private_evidence(
            root,
            namespace="capture_evidence",
            receipt=receipt["private_evidence"],
        )
        validate_capture_evidence_binding(evidence_payload, receipt)


def _read_source_response(root: Path, receipt: Mapping[str, Any]) -> tuple[Any, bytes]:
    if not isinstance(receipt, Mapping) or set(receipt) != {"sha256", "bytes"}:
        raise NbboCohortError("source response receipt is malformed")
    digest = receipt.get("sha256")
    size = receipt.get("bytes")
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise NbboCohortError("source response digest is malformed")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or not 0 < size <= MAX_RESPONSE_BYTES
    ):
        raise NbboCohortError("source response byte count is malformed")
    response_dir = _private_subdir(
        _validate_private_dir(root, create=True), "source_responses"
    )
    path = response_dir / f"{digest}.json"
    body = _validate_private_file(
        path, label="source response", maximum=MAX_RESPONSE_BYTES
    )
    if len(body) != size or sha256(body).hexdigest() != digest:
        raise NbboCohortError("source response receipt does not match private bytes")
    return strict_json_value(body, label="source response"), body


def verify_observation_source(root: Path, observation: Mapping[str, Any]) -> None:
    """Replay the first-quote claim against the exact retained provider bytes."""

    row = validate_observation(observation)
    receipt = row["source"]["response"]
    if receipt is None:
        return
    payload, _body = _read_source_response(root, receipt)
    source = row["source"]
    requested = _utc(source["requested_at"], label="source requested_at")
    _clean_query, query_end = validate_source_query(
        source["query"],
        contract=row["contract"],
        boundary_at=_utc(row["boundary_at"], label="boundary_at"),
        requested_at=requested,
        observed_at=_utc(row["observed_at"], label="observed_at"),
        ceiling_at=_utc(source["query_ceiling_at"], label="query_ceiling_at"),
    )
    try:
        selected = parse_quote_response(
            payload,
            role=row["role"],
            contract=row["contract"],
            boundary_at=_utc(row["boundary_at"], label="boundary_at"),
            query_end_at=query_end,
        )
    except NbboSourceError:
        if row["reason"] == "SOURCE_UNAVAILABLE":
            return
        raise
    if row["status"] == "admitted":
        if selected is None:
            raise NbboCohortError("admitted observation has no replayable first quote")
        expected_quote = {
            "event_at": utc_text(selected.event_at),
            "available_at": row["observed_at"],
            "bid": format(selected.bid, "f"),
            "ask": format(selected.ask, "f"),
            "bid_size": selected.bid_size,
            "ask_size": selected.ask_size,
            "bid_exchange": selected.bid_exchange,
            "ask_exchange": selected.ask_exchange,
            "bid_condition": selected.bid_condition,
            "ask_condition": selected.ask_condition,
            "selected_side": "ask" if row["role"] == "entry" else "bid",
            "selected_price": format(
                selected.ask if row["role"] == "entry" else selected.bid,
                "f",
            ),
            "event_to_available_lag_seconds": round(
                (
                    _utc(row["observed_at"], label="observed_at") - selected.event_at
                ).total_seconds(),
                6,
            ),
        }
        if row["quote"] != expected_quote:
            raise NbboCohortError("admitted quote differs from exact source replay")
    elif (
        row["reason"] in {"NO_VALID_NBBO_AFTER_BOUNDARY", "QUOTE_WINDOW_CLOSED"}
        and selected is not None
    ):
        raise NbboCohortError("no-valid-quote receipt contradicts exact source replay")
    elif row["reason"] == "FIRST_QUOTE_AVAILABLE_TOO_LATE":
        if (
            selected is None
            or (
                _utc(row["observed_at"], label="observed_at") - selected.event_at
            ).total_seconds()
            <= MAX_AVAILABLE_LAG_SECONDS
        ):
            raise NbboCohortError(
                "late-first-quote receipt contradicts exact source replay"
            )


def read_observations(root: Path) -> list[dict[str, Any]]:
    root = _validate_private_dir(root, create=True)
    objects = _private_subdir(root, "observations")
    rows: list[dict[str, Any]] = []
    paths = sorted(objects.iterdir(), key=lambda item: item.name)
    if len(paths) > MAX_EVENTS * 8:
        raise NbboCohortError("private observation namespace exceeds its fixed bound")
    for path in paths:
        if re.fullmatch(r"nbboobs_[0-9a-f]{64}\.json", path.name) is None:
            raise NbboCohortError(
                "private observation namespace contains an unknown path"
            )
        body = _validate_private_file(
            path, label="private observation", maximum=2 * 1024 * 1024
        )
        row = validate_observation(strict_json_object(body, label=path.name))
        if path.name != f"{row['observation_id']}.json":
            raise NbboCohortError(
                "private observation filename disagrees with identity"
            )
        if canonical_json_bytes(row) != body:
            raise NbboCohortError("private observation is not canonical")
        verify_observation_source(root, row)
        rows.append(row)
    return rows


def write_snapshot(root: Path, snapshot: Mapping[str, Any]) -> tuple[Path, Path]:
    root = _validate_private_dir(root, create=True)
    validate_schema(snapshot, label="NBBO cohort snapshot")
    body = canonical_json_bytes(snapshot)
    snapshot_id = snapshot.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.startswith("nbbosnap_"):
        raise NbboCohortError("snapshot identity is malformed")
    expected = _content_id("nbbosnap_", snapshot, "snapshot_id")
    if snapshot_id != expected:
        raise NbboCohortError("snapshot content identity mismatch")
    with _private_store_lock(root):
        target = _write_private_bytes(
            root,
            namespace="snapshots",
            filename=f"{snapshot_id}.json",
            body=body,
            maximum=64 * 1024 * 1024,
            label="NBBO cohort snapshot",
            _store_locked=True,
        )
        head = {
            "schema": HEAD_SCHEMA,
            "snapshot_id": snapshot_id,
            "sha256": sha256(body).hexdigest(),
            "bytes": len(body),
            "coverage": snapshot["coverage"],
            "authority": dict(FALSE_AUTHORITY),
        }
        validate_schema(head, label="NBBO cohort head")
        head_body = canonical_json_bytes(head)
        staging = _reconcile_staging(root)
        temp_head = staging / f"HEAD.{sha256(head_body).hexdigest()}.{uuid4().hex}.tmp"
        fd = os.open(
            temp_head,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(head_body)
            while view:
                written = os.write(fd, view)
                if written <= 0:  # pragma: no cover - defensive OS boundary
                    raise OSError("short private HEAD write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        head_path = root / "HEAD.json"
        if head_path.is_symlink():
            raise NbboCohortError("private cohort HEAD is a symlink")
        os.replace(temp_head, head_path)
        _fsync_dir(root)
        _fsync_dir(staging)
        stored_head = _validate_private_file(
            head_path, label="private cohort HEAD", maximum=2 * 1024 * 1024
        )
        if stored_head != head_body:
            raise NbboCohortError("private cohort HEAD readback mismatch")
    return target, head_path


FetchQuote = Callable[[Mapping[str, str]], FetchedQuoteResponse]
Clock = Callable[[], datetime]


def _acquire_advance_lock(root: Path) -> int:
    root = _validate_private_dir(root, create=True)
    lock_path = root / ".advance.lock"
    created = not lock_path.exists()
    fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise NbboCohortError("advance lock must be an owned private 0600 file")
        if created:
            os.fsync(fd)
            _fsync_dir(root)
        else:
            _fsync_dir(root)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise NbboCohortError(
                "another NBBO cohort advance is already running"
            ) from exc
        return fd
    except Exception:
        os.close(fd)
        raise


def _clock(clock: Clock | None, fallback: datetime) -> datetime:
    return _aware_utc(clock() if clock is not None else fallback, label="runtime clock")


def advance(
    *,
    event_ledger: Path,
    private_root: Path,
    fetch_quote: FetchQuote,
    now: datetime,
    clock: Clock | None = None,
    capture_ledger: Path | None = None,
) -> dict[str, Any]:
    private_root = _validate_private_dir(private_root, create=True)
    lock_fd = _acquire_advance_lock(private_root)
    try:
        return _advance_locked(
            event_ledger=event_ledger,
            private_root=private_root,
            fetch_quote=fetch_quote,
            now=_aware_utc(now, label="advance clock"),
            clock=clock,
            capture_ledger=capture_ledger or private_root / "captures.jsonl",
        )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _advance_locked(
    *,
    event_ledger: Path,
    private_root: Path,
    fetch_quote: FetchQuote,
    now: datetime,
    clock: Clock | None,
    capture_ledger: Path,
) -> dict[str, Any]:
    events, receipt = read_event_ledger(event_ledger)
    capture_receipts, capture_receipt = read_capture_ledger(capture_ledger)
    if any(
        _utc(row["completed_at"], label="capture completed_at") > now
        for row in capture_receipts
    ):
        raise NbboCohortError("capture ledger contains a future receipt")
    if any(
        _utc(row[field], label=f"event {field}") > now
        for row in events
        for field in ("event_at", "available_at")
    ):
        raise NbboCohortError("event ledger contains a future clock")
    verify_event_evidence(private_root, events)
    verify_capture_evidence(private_root, capture_receipts)
    enrollments, terminals = reconcile_events(events)
    observations = read_observations(private_root)
    if any(
        _utc(row["observed_at"], label="observation observed_at") > now
        for row in observations
    ):
        raise NbboCohortError("private store contains a future observation")
    admitted = {
        (row["event"]["event_id"], row["role"])
        for row in observations
        if row["status"] == "admitted"
    }
    closed = {
        (row["event"]["event_id"], row["role"])
        for row in observations
        if row["status"] == "unavailable"
        and row["reason"] in _TERMINAL_UNAVAILABLE_REASONS
    }
    new_rows: list[dict[str, Any]] = []
    attempt_count = 0
    transient_failure_count = 0
    for enrollment in enrollments:
        work: list[tuple[str, dict[str, Any], datetime]] = []
        terminal = terminals.get(enrollment["event_id"])
        enrollment_boundary = effective_boundary(enrollment)
        enrollment_close = (
            _session_window(enrollment_boundary.astimezone(ET).date())[1]
            if _in_rth(enrollment_boundary)
            else enrollment_boundary
        )
        entry_ceiling = min(
            enrollment_close,
            effective_boundary(terminal) if terminal is not None else enrollment_close,
        )
        entry_key = (enrollment["event_id"], "entry")
        if entry_key not in admitted and entry_key not in closed:
            work.append(("entry", enrollment, entry_ceiling))
        if terminal is not None:
            exit_key = (terminal["event_id"], "exit")
            exit_boundary = effective_boundary(terminal)
            exit_close = (
                _session_window(exit_boundary.astimezone(ET).date())[1]
                if _in_rth(exit_boundary)
                else exit_boundary
            )
            if exit_key not in admitted and exit_key not in closed:
                work.append(("exit", terminal, exit_close))
        for role, event, ceiling in work:
            boundary = effective_boundary(event)
            event_available = _utc(event["available_at"], label="event available_at")
            attempt_at = _clock(clock, now)
            if attempt_at < event_available:
                continue
            boundary_in_rth = _in_rth(boundary)
            source_payload: Any | None = None
            source_response_body: bytes | None = None
            source_error: str | None = None
            query: dict[str, str] | None = None
            window_closed = False
            if not boundary_in_rth:
                observed_at = attempt_at
            elif attempt_at > ceiling + timedelta(seconds=MAX_AVAILABLE_LAG_SECONDS):
                observed_at = attempt_at
                window_closed = True
            else:
                if clock is None:
                    raise NbboCohortError(
                        "quote attempts require an explicit runtime clock callback"
                    )
                query = source_query(
                    contract=event["contract"],
                    boundary_at=boundary,
                    available_at=attempt_at,
                    ceiling_at=ceiling,
                )
                attempt_count += 1
                try:
                    fetched = fetch_quote(query)
                except Exception as exc:  # noqa: BLE001 - converted to a private receipt
                    source_error = type(exc).__name__
                else:
                    if not isinstance(fetched, FetchedQuoteResponse):
                        raise NbboCohortError(
                            "quote fetcher must return exact FetchedQuoteResponse bytes"
                        )
                    source_payload = fetched.payload
                    source_response_body = fetched.raw_body
                observed_at = _clock(clock, now)
            try:
                observation = build_observation(
                    role=role,
                    event=event,
                    available_at=observed_at,
                    source_payload=source_payload,
                    source_error=source_error,
                    query=query,
                    request_started_at=attempt_at if query is not None else None,
                    source_response_body=source_response_body,
                    query_ceiling_at=ceiling,
                    window_closed=window_closed,
                )
            except NbboSourceError as exc:
                if query is None or source_payload is None:
                    raise
                observation = build_observation(
                    role=role,
                    event=event,
                    available_at=observed_at,
                    source_payload=source_payload,
                    source_error=type(exc).__name__,
                    query=query,
                    request_started_at=attempt_at,
                    source_response_body=source_response_body,
                    query_ceiling_at=ceiling,
                )
            should_persist = (
                observation["status"] == "admitted"
                or observation["reason"] in _TERMINAL_UNAVAILABLE_REASONS
            )
            if not should_persist:
                transient_failure_count += 1
                continue
            if source_response_body is not None:
                stored_response = write_source_response(
                    private_root, source_response_body
                )
                if stored_response != observation["source"]["response"]:
                    raise NbboCohortError("stored source response receipt drifted")
            write_immutable(private_root, observation)
            observations.append(observation)
            new_rows.append(observation)
    material_clocks = (
        [_utc(row["available_at"], label="event available_at") for row in events]
        + [
            _utc(row["observed_at"], label="observation observed_at")
            for row in observations
        ]
        + [
            _utc(row["completed_at"], label="capture completed_at")
            for row in capture_receipts
        ]
    )
    for session_text in {row["session_date"] for row in capture_receipts}:
        _, closed_at = _session_window(date.fromisoformat(session_text))
        if now >= closed_at:
            material_clocks.append(closed_at)
    freeze_date = (
        _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze")
        .astimezone(ET)
        .date()
    )
    for session in nyse_calendar.sessions_between(
        freeze_date, now.astimezone(ET).date()
    ):
        opened_at, closed_at = _session_window(session)
        if (
            opened_at >= _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze")
            and closed_at <= now
        ):
            material_clocks.append(closed_at)
    built_at = max(material_clocks) if material_clocks else now
    snapshot = build_snapshot(
        events=events,
        event_receipt=receipt,
        observations=observations,
        built_at=built_at,
        capture_receipts=capture_receipts,
        capture_ledger_receipt=capture_receipt,
    )
    write_snapshot(private_root, snapshot)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "new_observation_count": len(new_rows),
        "attempt_count": attempt_count,
        "transient_failure_count": transient_failure_count,
        "coverage": snapshot["coverage"],
    }


def canonical_event_line(event: Mapping[str, Any]) -> bytes:
    """Return one validated event row suitable for the private source ledger."""
    return canonical_json_bytes(validate_event(event))


__all__ = [
    "AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA",
    "AUTHENTICATED_EVENT_EVIDENCE_SCHEMA",
    "BENCHMARK_DIGEST",
    "CAPTURE_PRODUCER_REGISTRY",
    "COHORT_RULE_ID",
    "DEFAULT_CAPTURE_PRODUCER_REGISTRY",
    "DEFAULT_EVENT_PRODUCER_REGISTRY",
    "EVENT_PRODUCER_REGISTRY",
    "EVENT_SCHEMA",
    "EXPIRY_EVENT_SOURCE_SCHEMA",
    "FALSE_AUTHORITY",
    "FEE_PER_SIDE_USD",
    "HEAD_SCHEMA",
    "MAX_AVAILABLE_LAG_SECONDS",
    "OBSERVATION_SCHEMA",
    "QUOTE_RULE_ID",
    "SNAPSHOT_SCHEMA",
    "SOURCE_CLASS",
    "SOURCE_ENDPOINT",
    "FetchedQuoteResponse",
    "NbboCohortError",
    "NbboSourceError",
    "advance",
    "build_capture_evidence_bytes",
    "build_event_evidence_bytes",
    "build_observation",
    "build_snapshot",
    "canonical_event_line",
    "canonical_json_bytes",
    "canonical_occ_symbol",
    "make_event",
    "net_return_pct",
    "parse_quote_response",
    "read_event_ledger",
    "read_observations",
    "reconcile_events",
    "source_query",
    "strict_json_value",
    "utc_text",
    "validate_capture_evidence_binding",
    "validate_capture_receipt",
    "validate_contract",
    "validate_event",
    "validate_event_evidence_binding",
    "validate_observation",
]
