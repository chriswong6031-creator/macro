"""Clock-free W1B.4A uncertainty envelopes and sensitivity plans.

This module deliberately stops before replay materialization.  It has no
reader, store, API, wall clock, environment, network, or private Market Memory
dependency.  It can only:

* bind one pre-decision event reference to an honest ``date`` or ``session``
  uncertainty envelope;
* bind an XNYS schedule extraction to the exact reviewed source bytes; and
* enumerate three sensitivity-only assumptions (open, temporal midpoint, and
  close minus one microsecond) when a resolved session receipt permits it.

The emitted scenario timestamps are assumptions, never inferred event times.
Every artifact is strict, bounded, finite canonical JSON with display/context
only authority and a deterministic content identifier.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType
from typing import Any, Literal, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EVENT_TIME_UNCERTAINTY_SCHEMA = "market_memory.event_time_uncertainty.v1"
MARKET_SESSION_WINDOW_SCHEMA = "market_memory.market_session_window.v1"
SENSITIVITY_REPLAY_PLAN_SCHEMA = "market_memory.sensitivity_replay_plan.v1"

SOURCE_TIMEZONE = "America/New_York"
MARKET_SESSION = "XNYS_REGULAR"
BOUNDS_CONVENTION = "lower_inclusive_upper_exclusive"
CUTOFF_POLICY_VERSION = "market_memory.open_mid_close_sensitivity.v1"

_OFFICIAL_SCHEDULE_SOURCE = "NYSE"
_OFFICIAL_SCHEDULE_URL = "https://www.nyse.com/markets/hours-calendars"
_SOURCE_AUTHENTICATION = "exact_source_bytes_sha256_verified"
_SCHEDULE_BASIS = "reviewed_exchange_schedule"
_SOURCE_REFERENCE_BASIS = "caller_attested_predecision_projection"

_MAX_CONTRACT_BYTES = 64 * 1024
_MAX_SOURCE_ARTIFACT_BYTES = 512 * 1024
_MAX_STRING_BYTES = 4 * 1024
_MAX_COLLECTION_ITEMS = 256
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 4_096
_MIN_YEAR = 1970
_MAX_YEAR = 2100

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_CALENDAR_ID = re.compile(r"mmcalendar_[a-f0-9]{64}\Z")
_WINDOW_ID = re.compile(r"mmsessionwindow_[a-f0-9]{64}\Z")
_UNCERTAINTY_ID = re.compile(r"mmuncertainty_[a-f0-9]{64}\Z")
_PLAN_ID = re.compile(r"mmsensitivityplan_[a-f0-9]{64}\Z")
_OPAQUE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")

_SESSION_STATES = frozenset(
    {"regular_session", "early_close", "non_session", "unresolved"}
)
_EVENT_TIME_PRECISIONS = frozenset({"date", "session"})
_REPLAY_SCOPES = frozenset({"civil_date", "market_session"})
_SCENARIO_ORDER = ("session_open", "mid_session", "session_close")

AUTHORITY: Mapping[str, Any] = MappingProxyType(
    {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
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

_SOURCE_EVENT_REF_FIELDS = frozenset(
    {
        "owner",
        "source_schema",
        "event_id",
        "event_date_field",
        "predecision_event_sha256",
        "source_contract_sha256",
        "reference_basis",
        "predecision_event_bytes_verified",
        "source_contract_semantics_authenticated",
        "replay_scope_authenticated_by_source",
    }
)
_SOURCE_EVIDENCE_FIELDS = frozenset(
    {
        "source",
        "source_url",
        "schedule_version",
        "reviewed_at",
        "artifact_sha256",
        "artifact_bytes",
        "source_authentication",
        "schedule_basis",
        "actual_market_activity_authenticated",
    }
)
_WINDOW_FIELDS = frozenset(
    {
        "schema",
        "window_id",
        "calendar_id",
        "market_session",
        "session_date",
        "source_timezone",
        "session_state",
        "session_open",
        "session_close_exclusive",
        "bounds_convention",
        "source_evidence",
        "quality",
        "limitations",
        "authority",
    }
)
_UNCERTAINTY_FIELDS = frozenset(
    {
        "schema",
        "uncertainty_id",
        "source_event_ref",
        "event_date",
        "event_time_precision",
        "replay_scope",
        "source_timezone",
        "event_time_lower_bound",
        "event_time_upper_bound",
        "bounds_convention",
        "timestamp_inferred",
        "actual_event_time",
        "market_session_window_id",
        "sensitivity_coverage",
        "limitations",
        "authority",
    }
)
_PLAN_FIELDS = frozenset(
    {
        "schema",
        "plan_id",
        "uncertainty",
        "market_session_window",
        "plan_status",
        "abstention_reason",
        "cutoff_policy",
        "scenarios",
        "materialization_policy",
        "claim_policy",
        "authority",
    }
)

_FORBIDDEN_TOKENS = frozenset(
    {
        "label",
        "labels",
        "outcome",
        "outcomes",
        "direction",
        "bullish",
        "bearish",
        "bull",
        "bear",
        "long",
        "short",
        "pnl",
        "profit",
        "profits",
        "loss",
        "losses",
        "exit",
        "management",
        "matured",
        "close",
        "closed",
        "closing",
    }
)
_FORBIDDEN_PHRASES = (
    "forward return",
    "future return",
    "realized return",
    "realized pnl",
    "p and l",
    "p l",
    "profit and loss",
    "return pct",
    "exit price",
    "closed date",
    "close price",
    "premium return",
    "premium outcome",
    "h 60",
    "h plus 60",
    "h60",
)
_FORBIDDEN_COMPACT = (
    "forwardreturn",
    "futurereturn",
    "realizedreturn",
    "realizedpnl",
    "pnl",
    "premiumoutcome",
    "premiumreturn",
    "returnpct",
    "exitprice",
    "closeddate",
    "closeprice",
    "hplus60",
    "h60",
)


class MarketMemoryReplayContractError(ValueError):
    """A W1B.4A artifact is unsafe, ambiguous, or non-canonical."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryReplayContractError(message)


def _require_plain_dict(value: object, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{field} must be a plain JSON object")
    if not all(type(key) is str for key in value):
        _fail(f"{field} keys must be strings")
    return value


def _require_fields(
    value: object, expected: frozenset[str], field: str
) -> dict[str, Any]:
    payload = _require_plain_dict(value, field)
    if set(payload) != expected:
        missing = sorted(expected - set(payload))
        extra = sorted(set(payload) - expected)
        _fail(f"{field} fields are not canonical; missing={missing}, extra={extra}")
    return payload


def _bounded_canonical_bytes(value: object, *, field: str) -> bytes:
    """Return canonical JSON after bounding shape, depth, cycles, and scalars."""

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
                if any(unicodedata.category(char) == "Cs" for char in key):
                    _fail(f"{field} key contains a surrogate code point")
                if any(ord(char) < 32 for char in key):
                    _fail(f"{field} key contains a control character")
                if len(key.encode("utf-8")) > _MAX_STRING_BYTES:
                    _fail(f"{field} key exceeds its byte bound")
                stack.append((item, depth + 1, False))
            continue
        if type(current) is list:
            if id(current) in active:
                _fail(f"{field} contains a cycle")
            if len(current) > _MAX_COLLECTION_ITEMS:
                _fail(f"{field} array exceeds its item bound")
            active.add(id(current))
            stack.append((current, depth, True))
            for item in reversed(current):
                stack.append((item, depth + 1, False))
            continue
        if type(current) is str:
            if any(unicodedata.category(char) == "Cs" for char in current):
                _fail(f"{field} contains a surrogate code point")
            if any(ord(char) < 32 for char in current):
                _fail(f"{field} contains a control character")
            if len(current.encode("utf-8")) > _MAX_STRING_BYTES:
                _fail(f"{field} string exceeds its byte bound")
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
        raise MarketMemoryReplayContractError(
            f"{field} is not finite canonical JSON"
        ) from exc
    if len(body) > _MAX_CONTRACT_BYTES:
        _fail(f"{field} exceeds the canonical byte bound")
    return body


def _detached(value: object, *, field: str) -> dict[str, Any]:
    body = _bounded_canonical_bytes(value, field=field)
    detached = json.loads(body)
    return _require_plain_dict(detached, field)


def _exact_json_equal(left: object, right: object, *, field: str) -> bool:
    return _bounded_canonical_bytes(
        left, field=f"{field} supplied"
    ) == _bounded_canonical_bytes(right, field=f"{field} expected")


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    body = _bounded_canonical_bytes(core, field=f"{field} preimage")
    return prefix + hashlib.sha256(body).hexdigest()


def _normalize_semantics(value: str) -> tuple[set[str], str]:
    # Split camelCase before case-folding destroys its boundary.  Run the split
    # against the original NFKC text and only then normalize case.
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", normalized).casefold()
    normalized = normalized.replace("&", " and ").replace("+", " plus ")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return set(tokens), " ".join(tokens)


def _assert_predecision_semantics(value: object, *, field: str) -> None:
    """Reject outcome/direction language anywhere in caller-controlled JSON."""

    stack: list[tuple[object, str]] = [(value, field)]
    visited = 0
    while stack:
        current, path = stack.pop()
        visited += 1
        if visited > _MAX_JSON_NODES:
            _fail(f"{field} exceeds the semantic scan bound")
        if type(current) is dict:
            for key, item in current.items():
                tokens, phrase = _normalize_semantics(key)
                compact = phrase.replace(" ", "")
                if (
                    tokens & _FORBIDDEN_TOKENS
                    or any(marker in phrase for marker in _FORBIDDEN_PHRASES)
                    or any(marker in compact for marker in _FORBIDDEN_COMPACT)
                ):
                    _fail(f"{path} contains forbidden post-event semantics")
                stack.append((item, f"{path}.{key}"))
        elif type(current) is list:
            stack.extend(
                (item, f"{path}[{index}]") for index, item in enumerate(current)
            )
        elif type(current) is str:
            tokens, phrase = _normalize_semantics(current)
            compact = phrase.replace(" ", "")
            if (
                tokens & _FORBIDDEN_TOKENS
                or any(marker in phrase for marker in _FORBIDDEN_PHRASES)
                or any(marker in compact for marker in _FORBIDDEN_COMPACT)
            ):
                _fail(f"{path} contains forbidden post-event semantics")


def _exact_text(value: object, *, field: str, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{field} must be non-empty bounded text")
    if not _OPAQUE_REF.fullmatch(value):
        _fail(f"{field} contains unsupported characters")
    return value


def _exact_sha256(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        _fail(f"{field} must be lowercase SHA-256")
    return value


def _exact_date(value: object, *, field: str) -> date:
    if type(value) is not str or not _DATE.fullmatch(value):
        _fail(f"{field} must be an exact YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise MarketMemoryReplayContractError(f"{field} is not a real date") from exc
    if not _MIN_YEAR <= parsed.year <= _MAX_YEAR:
        _fail(f"{field} is outside the frozen year range")
    return parsed


def _exact_utc(value: object, *, field: str) -> datetime:
    if type(value) is not str or not _UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{field} must be exact microsecond RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryReplayContractError(
            f"{field} is not a real timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        _fail(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_york() -> ZoneInfo:
    try:
        return ZoneInfo(SOURCE_TIMEZONE)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - deployment prerequisite
        raise MarketMemoryReplayContractError(
            "canonical America/New_York timezone data is unavailable"
        ) from exc


def _validate_authority(value: object, *, field: str) -> dict[str, Any]:
    expected = dict(AUTHORITY)
    if type(value) is not dict or not _exact_json_equal(value, expected, field=field):
        _fail(f"{field} must equal the frozen zero-authority contract")
    return copy.deepcopy(expected)


def _validate_source_event_ref(value: object) -> dict[str, Any]:
    payload = _require_fields(value, _SOURCE_EVENT_REF_FIELDS, "source_event_ref")
    _bounded_canonical_bytes(payload, field="source_event_ref")
    _assert_predecision_semantics(payload, field="source_event_ref")
    clean = {
        "owner": _exact_text(
            payload["owner"], field="source_event_ref.owner", maximum=128
        ),
        "source_schema": _exact_text(
            payload["source_schema"],
            field="source_event_ref.source_schema",
            maximum=160,
        ),
        "event_id": _exact_text(payload["event_id"], field="source_event_ref.event_id"),
        "event_date_field": _exact_text(
            payload["event_date_field"],
            field="source_event_ref.event_date_field",
            maximum=64,
        ),
        "predecision_event_sha256": _exact_sha256(
            payload["predecision_event_sha256"],
            field="source_event_ref.predecision_event_sha256",
        ),
        "source_contract_sha256": _exact_sha256(
            payload["source_contract_sha256"],
            field="source_event_ref.source_contract_sha256",
        ),
        "reference_basis": payload["reference_basis"],
        "predecision_event_bytes_verified": payload["predecision_event_bytes_verified"],
        "source_contract_semantics_authenticated": payload[
            "source_contract_semantics_authenticated"
        ],
        "replay_scope_authenticated_by_source": payload[
            "replay_scope_authenticated_by_source"
        ],
    }
    if clean["reference_basis"] != _SOURCE_REFERENCE_BASIS:
        _fail("source_event_ref reference basis drift")
    for field in (
        "predecision_event_bytes_verified",
        "source_contract_semantics_authenticated",
        "replay_scope_authenticated_by_source",
    ):
        if clean[field] is not False:
            _fail(f"source_event_ref.{field} must disclose unauthenticated provenance")
    return clean


def _validate_source_artifact(value: object) -> bytes:
    if type(value) is not bytes:
        _fail("exact_source_artifact must be bytes")
    if not 0 < len(value) <= _MAX_SOURCE_ARTIFACT_BYTES:
        _fail("exact_source_artifact is empty or exceeds its byte bound")
    return value


def _validate_source_evidence(
    value: object, *, exact_source_artifact: bytes
) -> dict[str, Any]:
    payload = _require_fields(value, _SOURCE_EVIDENCE_FIELDS, "source_evidence")
    _bounded_canonical_bytes(payload, field="source_evidence")
    _assert_predecision_semantics(payload, field="source_evidence")
    artifact = _validate_source_artifact(exact_source_artifact)
    if payload["source"] != _OFFICIAL_SCHEDULE_SOURCE:
        _fail("source_evidence.source must name the frozen exchange source")
    if payload["source_url"] != _OFFICIAL_SCHEDULE_URL:
        _fail("source_evidence.source_url is not the reviewed schedule URL")
    schedule_version = _exact_text(
        payload["schedule_version"],
        field="source_evidence.schedule_version",
        maximum=128,
    )
    reviewed_at = _format_utc(
        _exact_utc(payload["reviewed_at"], field="source_evidence.reviewed_at")
    )
    artifact_sha = _exact_sha256(
        payload["artifact_sha256"], field="source_evidence.artifact_sha256"
    )
    if artifact_sha != hashlib.sha256(artifact).hexdigest():
        _fail("source_evidence artifact SHA-256 does not bind exact source bytes")
    artifact_bytes = payload["artifact_bytes"]
    if type(artifact_bytes) is not int or artifact_bytes != len(artifact):
        _fail("source_evidence artifact byte count does not bind exact source bytes")
    if payload["source_authentication"] != _SOURCE_AUTHENTICATION:
        _fail("source_evidence authentication profile drift")
    if payload["schedule_basis"] != _SCHEDULE_BASIS:
        _fail("source_evidence schedule basis drift")
    if payload["actual_market_activity_authenticated"] is not False:
        _fail("a reviewed schedule cannot authenticate actual market activity")
    return {
        "source": _OFFICIAL_SCHEDULE_SOURCE,
        "source_url": _OFFICIAL_SCHEDULE_URL,
        "schedule_version": schedule_version,
        "reviewed_at": reviewed_at,
        "artifact_sha256": artifact_sha,
        "artifact_bytes": artifact_bytes,
        "source_authentication": _SOURCE_AUTHENTICATION,
        "schedule_basis": _SCHEDULE_BASIS,
        "actual_market_activity_authenticated": False,
    }


def _window_quality(session_state: str) -> dict[str, Any]:
    unresolved = session_state == "unresolved"
    return {
        "status": "unresolved" if unresolved else "complete",
        "flags": (
            ["schedule_unresolved", "scheduled_window_not_actual_market_activity"]
            if unresolved
            else ["scheduled_window_not_actual_market_activity"]
        ),
        "source_bytes_verified": True,
        "session_window_resolved": not unresolved,
        "actual_market_activity_authenticated": False,
    }


def _window_limitations() -> dict[str, bool]:
    return {
        "schedule_only": True,
        "actual_market_activity_authenticated": False,
        "unscheduled_interruptions_authenticated": False,
        "event_time_authenticated": False,
    }


def _validate_window_geometry(
    *,
    session_date: date,
    session_state: str,
    session_open: object,
    session_close_exclusive: object,
) -> tuple[str | None, str | None]:
    if session_state in {"non_session", "unresolved"}:
        if session_open is not None or session_close_exclusive is not None:
            _fail(f"{session_state} cannot carry session clocks")
        return None, None
    opened = _exact_utc(session_open, field="market_session_window.session_open")
    closed = _exact_utc(
        session_close_exclusive,
        field="market_session_window.session_close_exclusive",
    )
    if closed <= opened:
        _fail("market session close must follow open")
    zone = _new_york()
    local_open = opened.astimezone(zone)
    local_close = closed.astimezone(zone)
    if local_open.date() != session_date or local_close.date() != session_date:
        _fail("market session clocks must remain on session_date in New York")
    if local_open.timetz().replace(tzinfo=None) != time(9, 30):
        _fail("XNYS session open must be 09:30 America/New_York")
    expected_close = time(16, 0) if session_state == "regular_session" else time(13, 0)
    if local_close.timetz().replace(tzinfo=None) != expected_close:
        _fail("market session state and close clock disagree")
    return _format_utc(opened), _format_utc(closed)


def build_market_session_window(
    *,
    calendar_id: str,
    session_date: str,
    session_state: Literal[
        "regular_session", "early_close", "non_session", "unresolved"
    ],
    session_open: str | None,
    session_close_exclusive: str | None,
    source_evidence: Mapping[str, Any],
    exact_source_artifact: bytes,
) -> dict[str, Any]:
    """Build one source-byte-bound XNYS schedule-window receipt.

    Exact source bytes authenticate the retained schedule artifact, while the
    receipt still states that a schedule is not proof of actual market activity
    or of an event's intraday time.
    """

    payload: dict[str, Any] = {
        "schema": MARKET_SESSION_WINDOW_SCHEMA,
        "window_id": "",
        "calendar_id": calendar_id,
        "market_session": MARKET_SESSION,
        "session_date": session_date,
        "source_timezone": SOURCE_TIMEZONE,
        "session_state": session_state,
        "session_open": session_open,
        "session_close_exclusive": session_close_exclusive,
        "bounds_convention": BOUNDS_CONVENTION,
        "source_evidence": dict(source_evidence),
        "quality": _window_quality(session_state),
        "limitations": _window_limitations(),
        "authority": dict(AUTHORITY),
    }
    payload["window_id"] = _content_id("mmsessionwindow_", payload, field="window_id")
    return _validate_market_session_window_candidate(
        payload, exact_source_artifact=exact_source_artifact
    )


def _validate_market_session_window_candidate(
    value: Mapping[str, Any],
    *,
    exact_source_artifact: bytes,
) -> dict[str, Any]:
    """Validate integrity of a candidate, without admitting it as trusted."""

    payload = _require_fields(value, _WINDOW_FIELDS, "market_session_window")
    _bounded_canonical_bytes(payload, field="market_session_window")
    if payload["schema"] != MARKET_SESSION_WINDOW_SCHEMA:
        _fail("market session window schema drift")
    window_id = payload["window_id"]
    if type(window_id) is not str or not _WINDOW_ID.fullmatch(window_id):
        _fail("market session window ID is malformed")
    calendar_id = payload["calendar_id"]
    if type(calendar_id) is not str or not _CALENDAR_ID.fullmatch(calendar_id):
        _fail("market session window calendar_id is malformed")
    if payload["market_session"] != MARKET_SESSION:
        _fail("market session window market_session drift")
    session_day = _exact_date(
        payload["session_date"], field="market_session_window.session_date"
    )
    if payload["source_timezone"] != SOURCE_TIMEZONE:
        _fail("market session window must use canonical America/New_York")
    session_state = payload["session_state"]
    if session_state not in _SESSION_STATES:
        _fail("market session window state is unsupported")
    opened, closed = _validate_window_geometry(
        session_date=session_day,
        session_state=session_state,
        session_open=payload["session_open"],
        session_close_exclusive=payload["session_close_exclusive"],
    )
    if payload["bounds_convention"] != BOUNDS_CONVENTION:
        _fail("market session window bounds convention drift")
    source_evidence = _validate_source_evidence(
        payload["source_evidence"],
        exact_source_artifact=exact_source_artifact,
    )
    if not _exact_json_equal(
        payload["quality"], _window_quality(session_state), field="window quality"
    ):
        _fail("market session window quality drift")
    if not _exact_json_equal(
        payload["limitations"], _window_limitations(), field="window limitations"
    ):
        _fail("market session window limitations drift")
    authority = _validate_authority(
        payload["authority"], field="market_session_window.authority"
    )
    clean: dict[str, Any] = {
        "schema": MARKET_SESSION_WINDOW_SCHEMA,
        "window_id": window_id,
        "calendar_id": calendar_id,
        "market_session": MARKET_SESSION,
        "session_date": session_day.isoformat(),
        "source_timezone": SOURCE_TIMEZONE,
        "session_state": session_state,
        "session_open": opened,
        "session_close_exclusive": closed,
        "bounds_convention": BOUNDS_CONVENTION,
        "source_evidence": source_evidence,
        "quality": _window_quality(session_state),
        "limitations": _window_limitations(),
        "authority": authority,
    }
    expected = _content_id("mmsessionwindow_", clean, field="window_id")
    if not _exact_json_equal(payload, clean, field="market_session_window"):
        _fail("market session window is not exact canonical JSON")
    if window_id != expected:
        _fail("market session window ID does not bind canonical content")
    return _detached(clean, field="market_session_window")


def validate_market_session_window(
    value: Mapping[str, Any],
    *,
    exact_source_artifact: bytes,
    expected_window_id: str,
) -> dict[str, Any]:
    """Admit a candidate only against an out-of-band trusted window ID."""

    if type(expected_window_id) is not str or not _WINDOW_ID.fullmatch(
        expected_window_id
    ):
        _fail("expected_window_id is malformed")
    clean = _validate_market_session_window_candidate(
        value, exact_source_artifact=exact_source_artifact
    )
    if clean["window_id"] != expected_window_id:
        _fail("market session window does not match the trusted window ID")
    return clean


def _civil_date_bounds(event_date: date) -> tuple[str, str]:
    zone = _new_york()
    lower = datetime.combine(event_date, time.min, tzinfo=zone)
    upper = datetime.combine(event_date + timedelta(days=1), time.min, tzinfo=zone)
    return _format_utc(lower), _format_utc(upper)


def _uncertainty_limitations() -> dict[str, bool]:
    return {
        "actual_time_known": False,
        "scenario_times_are_observed_event_time": False,
        "actual_scenario_selected": False,
        "point_claim_permitted": False,
        "consumer_conclusion_evaluated": False,
    }


def _sensitivity_coverage(
    *,
    precision: str,
    replay_scope: str,
    window: Mapping[str, Any] | None,
) -> str:
    if replay_scope == "civil_date":
        return "none_civil_date"
    if window is None or window["session_state"] == "unresolved":
        return "none_session_window_unresolved"
    if window["session_state"] == "non_session":
        return "none_non_session"
    if precision == "date":
        return "partial_session_sensitivity"
    return "session_samples_only"


def build_event_time_uncertainty(
    *,
    source_event_ref: Mapping[str, Any],
    event_date: str,
    event_time_precision: Literal["date", "session"],
    replay_scope: Literal["civil_date", "market_session"],
    source_timezone: str = SOURCE_TIMEZONE,
    market_session_window: Mapping[str, Any] | None = None,
    exact_source_artifact: bytes | None = None,
    expected_window_id: str | None = None,
) -> dict[str, Any]:
    """Build one honest date/session uncertainty envelope.

    ``date`` always spans the full civil day.  Opting a date-only event into
    ``market_session`` merely permits partial session sensitivity when a matching
    reviewed receipt is present; it never narrows the date or proves RTH timing.
    """

    if source_timezone != SOURCE_TIMEZONE:
        _fail("W1B.4A supports canonical America/New_York only")
    clean_ref = _validate_source_event_ref(source_event_ref)
    event_day = _exact_date(event_date, field="event_date")
    if event_time_precision not in _EVENT_TIME_PRECISIONS:
        _fail("event_time_precision must be date or session")
    if replay_scope not in _REPLAY_SCOPES:
        _fail("replay_scope must be civil_date or market_session")
    if event_time_precision == "session" and replay_scope != "market_session":
        _fail("session precision requires market_session replay_scope")
    if replay_scope == "civil_date" and market_session_window is not None:
        _fail("civil_date scope cannot consume a market session window")
    if market_session_window is None:
        if exact_source_artifact is not None or expected_window_id is not None:
            _fail("session source proof cannot be supplied without a window")
        window = None
    else:
        if exact_source_artifact is None:
            _fail("market session window requires its exact source artifact")
        if expected_window_id is None:
            _fail("market session window requires an out-of-band trusted window ID")
        window = validate_market_session_window(
            market_session_window,
            exact_source_artifact=exact_source_artifact,
            expected_window_id=expected_window_id,
        )
        if window["session_date"] != event_day.isoformat():
            _fail("market session window date differs from event_date")
        if window["session_state"] == "unresolved":
            _fail("an unresolved session-window candidate cannot be bound")
    if event_time_precision == "session":
        if window is None:
            _fail("session precision requires a market session window")
        if window["session_state"] not in {"regular_session", "early_close"}:
            _fail("session precision requires a resolved trading session")
        lower = window["session_open"]
        upper = window["session_close_exclusive"]
    else:
        lower, upper = _civil_date_bounds(event_day)
    payload: dict[str, Any] = {
        "schema": EVENT_TIME_UNCERTAINTY_SCHEMA,
        "uncertainty_id": "",
        "source_event_ref": clean_ref,
        "event_date": event_day.isoformat(),
        "event_time_precision": event_time_precision,
        "replay_scope": replay_scope,
        "source_timezone": SOURCE_TIMEZONE,
        "event_time_lower_bound": lower,
        "event_time_upper_bound": upper,
        "bounds_convention": BOUNDS_CONVENTION,
        "timestamp_inferred": False,
        "actual_event_time": None,
        "market_session_window_id": window["window_id"] if window else None,
        "sensitivity_coverage": _sensitivity_coverage(
            precision=event_time_precision,
            replay_scope=replay_scope,
            window=window,
        ),
        "limitations": _uncertainty_limitations(),
        "authority": dict(AUTHORITY),
    }
    payload["uncertainty_id"] = _content_id(
        "mmuncertainty_", payload, field="uncertainty_id"
    )
    return validate_event_time_uncertainty(
        payload,
        market_session_window=window,
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )


def validate_event_time_uncertainty(
    value: Mapping[str, Any],
    *,
    market_session_window: Mapping[str, Any] | None = None,
    exact_source_artifact: bytes | None = None,
    expected_window_id: str | None = None,
) -> dict[str, Any]:
    """Validate and detach an uncertainty envelope.

    A window-bound envelope is admitted only with the exact source bytes and an
    out-of-band trusted window ID.  Integrity alone cannot mint session fanout.
    """

    payload = _require_fields(value, _UNCERTAINTY_FIELDS, "event_time_uncertainty")
    _bounded_canonical_bytes(payload, field="event_time_uncertainty")
    if payload["schema"] != EVENT_TIME_UNCERTAINTY_SCHEMA:
        _fail("event time uncertainty schema drift")
    uncertainty_id = payload["uncertainty_id"]
    if type(uncertainty_id) is not str or not _UNCERTAINTY_ID.fullmatch(uncertainty_id):
        _fail("event time uncertainty ID is malformed")
    clean_ref = _validate_source_event_ref(payload["source_event_ref"])
    event_day = _exact_date(payload["event_date"], field="event_date")
    precision = payload["event_time_precision"]
    replay_scope = payload["replay_scope"]
    if precision not in _EVENT_TIME_PRECISIONS:
        _fail("event_time_precision must be date or session")
    if replay_scope not in _REPLAY_SCOPES:
        _fail("replay_scope must be civil_date or market_session")
    if precision == "session" and replay_scope != "market_session":
        _fail("session precision requires market_session replay_scope")
    if payload["source_timezone"] != SOURCE_TIMEZONE:
        _fail("event uncertainty must use canonical America/New_York")
    lower = _exact_utc(
        payload["event_time_lower_bound"], field="event_time_lower_bound"
    )
    upper = _exact_utc(
        payload["event_time_upper_bound"], field="event_time_upper_bound"
    )
    if upper <= lower:
        _fail("event uncertainty upper bound must follow lower bound")
    if payload["bounds_convention"] != BOUNDS_CONVENTION:
        _fail("event uncertainty bounds convention drift")
    if payload["timestamp_inferred"] is not False:
        _fail("event uncertainty cannot infer a timestamp")
    if payload["actual_event_time"] is not None:
        _fail("uncertain event cannot carry an actual event time")
    window_id = payload["market_session_window_id"]
    if window_id is not None and (
        type(window_id) is not str or not _WINDOW_ID.fullmatch(window_id)
    ):
        _fail("event uncertainty session window ID is malformed")
    if replay_scope == "civil_date" and window_id is not None:
        _fail("civil_date uncertainty cannot bind a session window")
    if precision == "session" and window_id is None:
        _fail("session precision must bind a session window")
    if window_id is None:
        if (
            market_session_window is not None
            or exact_source_artifact is not None
            or expected_window_id is not None
        ):
            _fail("unbound uncertainty cannot consume session-window proof")
        window = None
    else:
        if market_session_window is None or exact_source_artifact is None:
            _fail("window-bound uncertainty requires the window and exact source bytes")
        if expected_window_id is None:
            _fail("window-bound uncertainty requires an out-of-band trusted window ID")
        window = validate_market_session_window(
            market_session_window,
            exact_source_artifact=exact_source_artifact,
            expected_window_id=expected_window_id,
        )
        if window["window_id"] != window_id:
            _fail("event uncertainty window ID differs from the admitted receipt")
        if window["session_date"] != event_day.isoformat():
            _fail("event uncertainty window date differs from event_date")
        if window["session_state"] == "unresolved":
            _fail("an unresolved session-window candidate cannot be bound")
    if precision == "date":
        expected_lower, expected_upper = _civil_date_bounds(event_day)
        if _format_utc(lower) != expected_lower or _format_utc(upper) != expected_upper:
            _fail("date precision must retain the entire local civil day")
        allowed_coverage = (
            {"none_civil_date"}
            if replay_scope == "civil_date"
            else {
                "none_session_window_unresolved",
                "none_non_session",
                "partial_session_sensitivity",
            }
        )
    else:
        local_lower = lower.astimezone(_new_york())
        local_upper = upper.astimezone(_new_york())
        if local_lower.date() != event_day:
            _fail("session lower bound differs from event_date")
        if local_upper.date() != event_day:
            _fail("session upper bound differs from event_date")
        if local_lower.timetz().replace(tzinfo=None) != time(9, 30):
            _fail("session uncertainty must begin at 09:30 America/New_York")
        if local_upper.timetz().replace(tzinfo=None) not in {time(13, 0), time(16, 0)}:
            _fail("session uncertainty must end at an admitted XNYS close")
        allowed_coverage = {"session_samples_only"}
    coverage = payload["sensitivity_coverage"]
    if coverage not in allowed_coverage:
        _fail("event uncertainty sensitivity coverage is inconsistent")
    expected_coverage = _sensitivity_coverage(
        precision=precision,
        replay_scope=replay_scope,
        window=window,
    )
    if coverage != expected_coverage:
        _fail("event uncertainty coverage differs from its session receipt")
    if (
        window is not None
        and precision == "session"
        and (
            _format_utc(lower) != window["session_open"]
            or _format_utc(upper) != window["session_close_exclusive"]
        )
    ):
        _fail("session uncertainty bounds differ from its session receipt")
    if not _exact_json_equal(
        payload["limitations"],
        _uncertainty_limitations(),
        field="uncertainty limitations",
    ):
        _fail("event uncertainty limitations drift")
    authority = _validate_authority(
        payload["authority"], field="event_time_uncertainty.authority"
    )
    clean: dict[str, Any] = {
        "schema": EVENT_TIME_UNCERTAINTY_SCHEMA,
        "uncertainty_id": uncertainty_id,
        "source_event_ref": clean_ref,
        "event_date": event_day.isoformat(),
        "event_time_precision": precision,
        "replay_scope": replay_scope,
        "source_timezone": SOURCE_TIMEZONE,
        "event_time_lower_bound": _format_utc(lower),
        "event_time_upper_bound": _format_utc(upper),
        "bounds_convention": BOUNDS_CONVENTION,
        "timestamp_inferred": False,
        "actual_event_time": None,
        "market_session_window_id": window_id,
        "sensitivity_coverage": coverage,
        "limitations": _uncertainty_limitations(),
        "authority": authority,
    }
    expected = _content_id("mmuncertainty_", clean, field="uncertainty_id")
    if not _exact_json_equal(payload, clean, field="event_time_uncertainty"):
        _fail("event time uncertainty is not exact canonical JSON")
    if uncertainty_id != expected:
        _fail("event time uncertainty ID does not bind canonical content")
    return _detached(clean, field="event_time_uncertainty")


def _cutoff_policy() -> dict[str, Any]:
    return {
        "policy_version": CUTOFF_POLICY_VERSION,
        "ordered_cutoffs": list(_SCENARIO_ORDER),
        "midpoint_rule": "floor_temporal_midpoint",
        "close_rule": "session_close_exclusive_minus_one_microsecond",
        "caller_supplied_cutoffs_allowed": False,
        "actual_cutoff_selected": False,
    }


def _materialization_policy() -> dict[str, bool]:
    return {
        "packet_materialization": False,
        "reader_bound": False,
        "store_bound": False,
        "api_bound": False,
        "private_evidence_read": False,
    }


def _claim_policy() -> dict[str, bool]:
    return {
        "sensitivity_only": True,
        "point_claim_permitted": False,
        "consumer_conclusion_evaluated": False,
        "sampled_stability_claimed": False,
        "session_samples_prove_event_occurred_in_session": False,
    }


def _scenarios(window: Mapping[str, Any]) -> list[dict[str, Any]]:
    opened = _exact_utc(window["session_open"], field="session_open")
    closed = _exact_utc(
        window["session_close_exclusive"], field="session_close_exclusive"
    )
    microseconds = (closed - opened) // timedelta(microseconds=1)
    midpoint = opened + timedelta(microseconds=microseconds // 2)
    close_boundary = closed - timedelta(microseconds=1)
    values = (opened, midpoint, close_boundary)
    return [
        {
            "ordinal": ordinal,
            "cutoff_scenario": cutoff,
            "assumed_event_time": _format_utc(instant),
            "as_known_at": _format_utc(instant),
            "assumed_time_role": "sensitivity_only_not_observed_event_time",
            "materialization_status": "unmaterialized",
        }
        for ordinal, (cutoff, instant) in enumerate(zip(_SCENARIO_ORDER, values))
    ]


def _plan_disposition(
    uncertainty: Mapping[str, Any], window: Mapping[str, Any] | None
) -> tuple[str, str | None, list[dict[str, Any]]]:
    if uncertainty["replay_scope"] == "civil_date":
        return "abstained", "civil_date_scope", []
    if window is None:
        return "abstained", "session_window_unresolved", []
    if window["session_state"] == "unresolved":
        return "abstained", "session_window_unresolved", []
    if window["session_state"] == "non_session":
        return "abstained", "non_session", []
    return "unmaterialized", None, _scenarios(window)


def build_sensitivity_replay_plan(
    uncertainty: Mapping[str, Any],
    *,
    market_session_window: Mapping[str, Any] | None = None,
    exact_source_artifact: bytes | None = None,
    expected_window_id: str | None = None,
) -> dict[str, Any]:
    """Build an ordered sensitivity plan without reading or materializing packets."""

    if market_session_window is None:
        if exact_source_artifact is not None or expected_window_id is not None:
            _fail("session source proof cannot be supplied without a window")
        window = None
    else:
        if exact_source_artifact is None:
            _fail("market session window requires its exact source artifact")
        if expected_window_id is None:
            _fail("market session window requires an out-of-band trusted window ID")
        window = validate_market_session_window(
            market_session_window,
            exact_source_artifact=exact_source_artifact,
            expected_window_id=expected_window_id,
        )
    clean_uncertainty = validate_event_time_uncertainty(
        uncertainty,
        market_session_window=window,
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )
    if window is not None and window["session_date"] != clean_uncertainty["event_date"]:
        _fail("sensitivity window date differs from uncertainty event_date")
    bound_window_id = clean_uncertainty["market_session_window_id"]
    if bound_window_id is None and window is not None:
        _fail("uncertainty must bind a session window before plan construction")
    if bound_window_id is not None and (
        window is None or window["window_id"] != bound_window_id
    ):
        _fail("plan session window differs from the uncertainty receipt")
    status, reason, scenarios = _plan_disposition(clean_uncertainty, window)
    payload: dict[str, Any] = {
        "schema": SENSITIVITY_REPLAY_PLAN_SCHEMA,
        "plan_id": "",
        "uncertainty": clean_uncertainty,
        "market_session_window": window,
        "plan_status": status,
        "abstention_reason": reason,
        "cutoff_policy": _cutoff_policy(),
        "scenarios": scenarios,
        "materialization_policy": _materialization_policy(),
        "claim_policy": _claim_policy(),
        "authority": dict(AUTHORITY),
    }
    payload["plan_id"] = _content_id("mmsensitivityplan_", payload, field="plan_id")
    return validate_sensitivity_replay_plan(
        payload,
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )


def validate_sensitivity_replay_plan(
    value: Mapping[str, Any],
    *,
    exact_source_artifact: bytes | None = None,
    expected_window_id: str | None = None,
) -> dict[str, Any]:
    """Validate and detach an unmaterialized sensitivity plan."""

    payload = _require_fields(value, _PLAN_FIELDS, "sensitivity_replay_plan")
    _bounded_canonical_bytes(payload, field="sensitivity_replay_plan")
    if payload["schema"] != SENSITIVITY_REPLAY_PLAN_SCHEMA:
        _fail("sensitivity replay plan schema drift")
    plan_id = payload["plan_id"]
    if type(plan_id) is not str or not _PLAN_ID.fullmatch(plan_id):
        _fail("sensitivity replay plan ID is malformed")
    raw_window = payload["market_session_window"]
    if raw_window is None:
        if exact_source_artifact is not None or expected_window_id is not None:
            _fail("session source proof cannot be supplied without a window")
        window = None
    else:
        if exact_source_artifact is None:
            _fail("embedded session window requires its exact source artifact")
        if expected_window_id is None:
            _fail("embedded session window requires an out-of-band trusted window ID")
        window = validate_market_session_window(
            raw_window,
            exact_source_artifact=exact_source_artifact,
            expected_window_id=expected_window_id,
        )
    uncertainty = validate_event_time_uncertainty(
        payload["uncertainty"],
        market_session_window=window,
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )
    if window is not None and window["session_date"] != uncertainty["event_date"]:
        _fail("embedded session window date differs from uncertainty")
    bound_window_id = uncertainty["market_session_window_id"]
    if bound_window_id is None and window is not None:
        _fail("plan embeds a window not bound by uncertainty")
    if bound_window_id is not None and (
        window is None or window["window_id"] != bound_window_id
    ):
        _fail("plan window differs from uncertainty binding")
    expected_status, expected_reason, expected_scenarios = _plan_disposition(
        uncertainty, window
    )
    if payload["plan_status"] != expected_status:
        _fail("sensitivity replay plan status drift")
    if payload["abstention_reason"] != expected_reason:
        _fail("sensitivity replay plan abstention reason drift")
    if not _exact_json_equal(
        payload["cutoff_policy"], _cutoff_policy(), field="cutoff policy"
    ):
        _fail("sensitivity replay cutoff policy drift")
    if not _exact_json_equal(
        payload["scenarios"], expected_scenarios, field="sensitivity scenarios"
    ):
        _fail("sensitivity replay scenarios are not canonical")
    lower = _exact_utc(
        uncertainty["event_time_lower_bound"], field="event_time_lower_bound"
    )
    upper = _exact_utc(
        uncertainty["event_time_upper_bound"], field="event_time_upper_bound"
    )
    for scenario in expected_scenarios:
        assumed = _exact_utc(
            scenario["assumed_event_time"], field="scenario.assumed_event_time"
        )
        if not lower <= assumed < upper:
            _fail("sensitivity scenario lies outside the uncertainty envelope")
    if not _exact_json_equal(
        payload["materialization_policy"],
        _materialization_policy(),
        field="materialization policy",
    ):
        _fail("sensitivity replay materialization policy drift")
    if not _exact_json_equal(
        payload["claim_policy"], _claim_policy(), field="claim policy"
    ):
        _fail("sensitivity replay claim policy drift")
    authority = _validate_authority(
        payload["authority"], field="sensitivity_replay_plan.authority"
    )
    clean: dict[str, Any] = {
        "schema": SENSITIVITY_REPLAY_PLAN_SCHEMA,
        "plan_id": plan_id,
        "uncertainty": uncertainty,
        "market_session_window": window,
        "plan_status": expected_status,
        "abstention_reason": expected_reason,
        "cutoff_policy": _cutoff_policy(),
        "scenarios": expected_scenarios,
        "materialization_policy": _materialization_policy(),
        "claim_policy": _claim_policy(),
        "authority": authority,
    }
    expected_id = _content_id("mmsensitivityplan_", clean, field="plan_id")
    if not _exact_json_equal(payload, clean, field="sensitivity_replay_plan"):
        _fail("sensitivity replay plan is not exact canonical JSON")
    if plan_id != expected_id:
        _fail("sensitivity replay plan ID does not bind canonical content")
    return _detached(clean, field="sensitivity_replay_plan")


def _strict_json_object(body: bytes, *, field: str) -> dict[str, Any]:
    if type(body) is not bytes:
        _fail(f"{field} JSON body must be bytes")
    if not body or len(body) > _MAX_CONTRACT_BYTES:
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
        text = body.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise MarketMemoryReplayContractError(
            f"{field} JSON is not valid UTF-8"
        ) from exc
    except MarketMemoryReplayContractError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise MarketMemoryReplayContractError(
            f"{field} JSON is not one exact JSON document"
        ) from exc
    payload = _require_plain_dict(value, field)
    _bounded_canonical_bytes(payload, field=field)
    return payload


def load_event_time_uncertainty_json(
    body: bytes,
    *,
    market_session_window: Mapping[str, Any] | None = None,
    exact_source_artifact: bytes | None = None,
    expected_window_id: str | None = None,
) -> dict[str, Any]:
    """Strictly parse and validate one uncertainty JSON object."""

    return validate_event_time_uncertainty(
        _strict_json_object(body, field="event_time_uncertainty"),
        market_session_window=market_session_window,
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )


def load_market_session_window_json(
    body: bytes,
    *,
    exact_source_artifact: bytes,
    expected_window_id: str,
) -> dict[str, Any]:
    """Parse and admit a window only against an out-of-band trusted ID."""

    return validate_market_session_window(
        _strict_json_object(body, field="market_session_window"),
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )


def load_sensitivity_replay_plan_json(
    body: bytes,
    *,
    exact_source_artifact: bytes | None = None,
    expected_window_id: str | None = None,
) -> dict[str, Any]:
    """Strictly parse and validate one unmaterialized plan JSON object."""

    return validate_sensitivity_replay_plan(
        _strict_json_object(body, field="sensitivity_replay_plan"),
        exact_source_artifact=exact_source_artifact,
        expected_window_id=expected_window_id,
    )


__all__ = [
    "AUTHORITY",
    "BOUNDS_CONVENTION",
    "CUTOFF_POLICY_VERSION",
    "EVENT_TIME_UNCERTAINTY_SCHEMA",
    "MARKET_SESSION_WINDOW_SCHEMA",
    "SENSITIVITY_REPLAY_PLAN_SCHEMA",
    "SOURCE_TIMEZONE",
    "MarketMemoryReplayContractError",
    "build_event_time_uncertainty",
    "build_market_session_window",
    "build_sensitivity_replay_plan",
    "load_event_time_uncertainty_json",
    "load_market_session_window_json",
    "load_sensitivity_replay_plan_json",
    "validate_event_time_uncertainty",
    "validate_market_session_window",
    "validate_sensitivity_replay_plan",
]
