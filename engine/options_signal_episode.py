"""Point-in-time options signal episodes and separately matured outcome labels.

This module is the permanent, zero-authority learning seam between the live
options tape and future model research.  It deliberately separates immutable
decision-time rows from later outcome rows:

``data/options_signal_episode/episodes.jsonl``
    What was knowable when an event first became available.  A row is never
    enriched later with a field learned after ``available_at``.

``data/options_signal_episode/outcomes_h60.jsonl``
    Aligned-bar proxy measurements appended only after the actual measurement
    window and any declared source delay have matured. Desired H+60 remains a
    separate target clock; coarse or delayed measurements are training-ineligible.
    Missing price bars remain pending so a later nightly can retry; the only
    terminal incomplete rows are horizons that cannot exist inside the source
    session (for example a 15:20 event on a regular close).

``data/options_signal_episode/outcomes_session.jsonl``
    Immutable underlying close outcomes at EOD and 1/3/5/10 NYSE-session
    horizons. These rows retain a compact, metric-replayable and path-committed
    summary of their receipt-bound RTH evidence and never alter the frozen H+60
    v1 contract.

Authority is intentionally zero.  A notable live-flow event is a ``watch``
episode, not a stock pick.  Nothing here ranks, gates, sizes, escalates, or
originates a trade.  The live poller may add raw observation provenance to R2,
but only the nightly lane may append these committed JSONL ledgers.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from engine.ledger_lane import nightly_advance_enabled
from engine.session_digest import ET, session_window_et
from lib import nyse_calendar

EPISODE_SCHEMA = "options.signal_episode/v1"
OUTCOME_SCHEMA = "options.signal_episode_outcome/v1"
SESSION_OUTCOME_SCHEMA = "options.signal_episode_session_outcome/v1"
HORIZON_MINUTES = 60
MEASUREMENT_VERSION = "h60-aligned-bars/v1"
SESSION_MEASUREMENT_VERSION = "session-close-aligned-bars/v1"
SESSION_CALENDAR_BASIS = "nyse_session_window_recurring_schedule/v1"
TRAINING_MAX_BAR_SECONDS = 60
TRAINING_MAX_PRICE_DELAY_MINUTES = 1
PRICE_RECEIPT_SCHEMA = "polygon.intraday_price_receipt/v1"
PRICE_EVIDENCE_SCHEMA = "options.signal_episode_price_evidence/v1"
SESSION_PRICE_EVIDENCE_SCHEMA = "options.signal_episode_session_price_evidence/v1"
PRICE_BASIS = "split_adjusted_polygon_aggregate_ohlc"
TIMESTAMP_BASIS = "aggregate_window_start_utc"

EPISODE_REL = Path("options_signal_episode") / "episodes.jsonl"
OUTCOME_REL = Path("options_signal_episode") / "outcomes_h60.jsonl"
SESSION_OUTCOME_REL = Path("options_signal_episode") / "outcomes_session.jsonl"

SESSION_HORIZONS = {
    "eod": 0,
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "10d": 10,
}

DISPOSITIONS = frozenset({"fire", "watch", "suppressed", "abstain"})
UNDERLYING_DIRECTIONS = frozenset({"long", "short", "none"})
OPTION_ACTIONS = frozenset({"buy", "sell", "none"})
TERMINAL_INCOMPLETE_REASONS = frozenset({
    "decision_after_session_close",
    "horizon_crosses_session_close",
})
FALSE_AUTHORITY = {
    "may_originate": False,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_publish_pick": False,
    "may_train_prophet": False,
}


class ContractError(ValueError):
    """A row violates the point-in-time contract."""


@lru_cache(maxsize=2)
def _schema_validator(filename: str) -> Draft202012Validator:
    path = Path(__file__).resolve().parent.parent / "contracts" / "options" / filename
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ContractError(f"cannot load contract schema {path}") from exc
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_json_schema(row: dict[str, Any], filename: str) -> None:
    errors = sorted(_schema_validator(filename).iter_errors(row), key=lambda e: list(e.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "<root>"
        raise ContractError(f"schema validation failed at {location}: {error.message}")


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _episode_id(source: str, source_event_id: str) -> str:
    """One stable v1 identity per upstream source event."""
    return _stable_id("osep", EPISODE_SCHEMA, source, source_event_id)


def _outcome_id(episode_id: str, horizon_minutes: int = HORIZON_MINUTES) -> str:
    """One stable v1 identity per episode/horizon/measurement contract."""
    return _stable_id(
        "oout", OUTCOME_SCHEMA, MEASUREMENT_VERSION, episode_id, horizon_minutes,
    )


def _session_outcome_id(episode_id: str, horizon: str) -> str:
    """One stable identity per episode/session-horizon/measurement contract."""
    return _stable_id(
        "oout", SESSION_OUTCOME_SCHEMA, SESSION_MEASUREMENT_VERSION, episode_id, horizon,
    )


def _canonical_bytes(row: dict[str, Any]) -> bytes:
    return json.dumps(
        row, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_price(value: object, field: str) -> float:
    """Freeze price evidence to the same eight-decimal precision as outcomes."""
    return round(_finite_float(value, field, positive=True), 8)


def _exact_canonical_price(value: object, field: str) -> float:
    """Reject persisted evidence that escapes the frozen eight-decimal basis."""
    out = _exact_finite_number(value, field, positive=True)
    if round(out, 8) != out:
        raise ContractError(f"{field} must use the canonical eight-decimal price basis")
    return out


def _build_price_evidence(path: pd.DataFrame, exit_time: datetime, exit_open: float) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for timestamp, bar in path.iterrows():
        observations.append({
            "time": _iso_utc(timestamp.to_pydatetime().astimezone(timezone.utc)),
            "open": _canonical_price(bar["open"], "price evidence open"),
            "high": _canonical_price(bar["high"], "price evidence high"),
            "low": _canonical_price(bar["low"], "price evidence low"),
            "close": _canonical_price(bar["close"], "price evidence close"),
        })
    payload = {
        "path": observations,
        "exit": {
            "time": _iso_utc(exit_time),
            "open": _canonical_price(exit_open, "price evidence exit open"),
        },
    }
    return {
        "schema": PRICE_EVIDENCE_SCHEMA,
        **payload,
        "observation_count": len(observations) + 1,
        "sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
    }


def _validate_price_evidence(
    evidence: object,
    *,
    entry: datetime,
    exit_: datetime,
    bar_seconds: int,
) -> tuple[float, float, float, float, float]:
    """Validate/recompute entry, exit, return, MFE and MAE from retained inputs."""
    if not isinstance(evidence, dict) or set(evidence) != {
        "schema", "path", "exit", "observation_count", "sha256",
    }:
        raise ContractError("complete outcome requires exact retained price evidence")
    if evidence.get("schema") != PRICE_EVIDENCE_SCHEMA:
        raise ContractError("retained price evidence schema is outside the v1 contract")
    path = evidence.get("path")
    exit_observation = evidence.get("exit")
    if not isinstance(path, list) or not path or not isinstance(exit_observation, dict):
        raise ContractError("retained price evidence requires path and exit observations")
    if set(exit_observation) != {"time", "open"}:
        raise ContractError("retained exit evidence may contain only time and open")
    if type(evidence.get("observation_count")) is not int or (
        evidence["observation_count"] != len(path) + 1
    ):
        raise ContractError("retained price evidence observation_count is inconsistent")
    digest = evidence.get("sha256")
    payload = {"path": path, "exit": exit_observation}
    expected_digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest) or digest != expected_digest:
        raise ContractError("retained price evidence digest is inconsistent")

    cadence = timedelta(seconds=bar_seconds)
    expected_times = [entry + offset * cadence for offset in range(len(path))]
    if expected_times[-1] + cadence != exit_:
        raise ContractError("retained price evidence does not span the measurement grid")
    highs: list[float] = []
    lows: list[float] = []
    entry_price: float | None = None
    for index, observation in enumerate(path):
        if not isinstance(observation, dict) or set(observation) != {
            "time", "open", "high", "low", "close",
        }:
            raise ContractError("retained path observation has an invalid shape")
        observed_time = _as_utc(observation["time"], f"price_evidence.path[{index}].time")
        if observation["time"] != _iso_utc(observed_time) or observed_time != expected_times[index]:
            raise ContractError("retained price evidence timestamps violate the aligned grid")
        open_price = _exact_finite_number(
            observation["open"], f"price_evidence.path[{index}].open", positive=True,
        )
        high = _exact_finite_number(
            observation["high"], f"price_evidence.path[{index}].high", positive=True,
        )
        low = _exact_finite_number(
            observation["low"], f"price_evidence.path[{index}].low", positive=True,
        )
        close = _exact_finite_number(
            observation["close"], f"price_evidence.path[{index}].close", positive=True,
        )
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise ContractError("retained price evidence contains invalid OHLC arithmetic")
        if entry_price is None:
            entry_price = open_price
        highs.append(high)
        lows.append(low)
    exit_time = _as_utc(exit_observation["time"], "price_evidence.exit.time")
    if exit_observation["time"] != _iso_utc(exit_time) or exit_time != exit_:
        raise ContractError("retained exit evidence timestamp disagrees with the outcome")
    exit_price = _exact_finite_number(
        exit_observation["open"], "price_evidence.exit.open", positive=True,
    )
    assert entry_price is not None
    ret = round(exit_price / entry_price - 1.0, 8)
    mfe = round(max(*highs, entry_price, exit_price) / entry_price - 1.0, 8)
    mae = round(min(*lows, entry_price, exit_price) / entry_price - 1.0, 8)
    return entry_price, exit_price, ret, mfe, mae


def _build_session_price_evidence(
    path: pd.DataFrame,
    *,
    target_time: datetime,
    final_bar_time: datetime,
    exit_close: float,
    bar_seconds: int,
) -> dict[str, Any]:
    """Commit a bounded summary while fully inspecting the selected RTH path.

    The ledger stores only exact metric inputs, cadence manifests, per-session
    raw-path commitments, and a recomputable manifest-root commitment. Evidence
    size is therefore bounded by the number of sessions. This is deliberately
    metric-replayable and path-committed, not full-path-replayable without a
    separately retained exact source snapshot.
    """
    observations: list[dict[str, Any]] = []
    for timestamp, bar in path.iterrows():
        observations.append({
            "time": _iso_utc(timestamp.to_pydatetime().astimezone(timezone.utc)),
            "open": _canonical_price(bar["open"], "session price evidence open"),
            "high": _canonical_price(bar["high"], "session price evidence high"),
            "low": _canonical_price(bar["low"], "session price evidence low"),
            "close": _canonical_price(bar["close"], "session price evidence close"),
        })
    if not observations:
        raise ContractError("session price evidence path cannot be empty")

    sessions: list[dict[str, Any]] = []
    for session in sorted({
        _as_utc(observation["time"], "session evidence observation time")
        .astimezone(ET).date()
        for observation in observations
    }):
        session_observations = [
            observation for observation in observations
            if _as_utc(observation["time"], "session evidence observation time")
            .astimezone(ET).date() == session
        ]
        first_time = _as_utc(
            session_observations[0]["time"], "session evidence first bar time",
        )
        last_time = _as_utc(
            session_observations[-1]["time"], "session evidence last bar time",
        )
        span_seconds = int((last_time - first_time).total_seconds())
        if span_seconds < 0 or span_seconds % bar_seconds:
            raise ContractError("session price evidence does not follow declared cadence")
        expected_count = span_seconds // bar_seconds + 1
        session_open = session_window_et(session)[0].astimezone(timezone.utc)
        uncovered_open_seconds = int((first_time - session_open).total_seconds())
        if uncovered_open_seconds < 0:
            raise ContractError("session price evidence begins before the scheduled open")
        sessions.append({
            "session": session.isoformat(),
            "first_bar_time": _iso_utc(first_time),
            "last_bar_time": _iso_utc(last_time),
            "uncovered_open_seconds": uncovered_open_seconds,
            "observation_count": len(session_observations),
            "expected_count": expected_count,
            "session_path_sha256": hashlib.sha256(
                _canonical_bytes(session_observations)
            ).hexdigest(),
        })

    high_observation = max(observations, key=lambda item: item["high"])
    low_observation = min(observations, key=lambda item: item["low"])
    entry_observation = observations[0]
    return {
        "schema": SESSION_PRICE_EVIDENCE_SCHEMA,
        "entry": {
            "bar_time": entry_observation["time"],
            "open": entry_observation["open"],
        },
        "exit": {
            "bar_time": _iso_utc(final_bar_time),
            "time": _iso_utc(target_time),
            "close": _canonical_price(exit_close, "session price evidence exit close"),
        },
        "extrema": {
            "high": {
                "bar_time": high_observation["time"],
                "value": high_observation["high"],
            },
            "low": {
                "bar_time": low_observation["time"],
                "value": low_observation["low"],
            },
        },
        "sessions": sessions,
        "observation_count": len(observations),
        "manifest_root_sha256": hashlib.sha256(_canonical_bytes(sessions)).hexdigest(),
    }


def _validate_session_price_evidence(
    evidence: object,
    *,
    entry: datetime,
    target_time: datetime,
    final_bar_time: datetime,
    bar_seconds: int,
) -> tuple[float, float, float, float, float]:
    """Recompute all persisted metrics from the bounded evidence summary."""
    if not isinstance(evidence, dict) or set(evidence) != {
        "schema", "entry", "exit", "extrema", "sessions",
        "observation_count", "manifest_root_sha256",
    }:
        raise ContractError("complete session outcome requires exact compact price evidence")
    if evidence.get("schema") != SESSION_PRICE_EVIDENCE_SCHEMA:
        raise ContractError("retained session price evidence schema is outside v1")
    entry_observation = evidence.get("entry")
    exit_observation = evidence.get("exit")
    extrema = evidence.get("extrema")
    sessions = evidence.get("sessions")
    if (
        not isinstance(entry_observation, dict)
        or not isinstance(exit_observation, dict)
        or not isinstance(extrema, dict)
        or not isinstance(sessions, list)
        or not sessions
    ):
        raise ContractError("retained session evidence requires entry, exit, extrema, and sessions")
    if set(entry_observation) != {"bar_time", "open"}:
        raise ContractError("retained session entry evidence has an invalid shape")
    if set(exit_observation) != {"bar_time", "time", "close"}:
        raise ContractError("retained session exit evidence has an invalid shape")
    if set(extrema) != {"high", "low"}:
        raise ContractError("retained session extrema evidence has an invalid shape")
    if any(
        not isinstance(extrema.get(side), dict)
        or set(extrema[side]) != {"bar_time", "value"}
        for side in ("high", "low")
    ):
        raise ContractError("retained session extrema observations have an invalid shape")
    observation_count = evidence.get("observation_count")
    if type(observation_count) is not int or observation_count < 1:
        raise ContractError("retained session evidence observation_count is invalid")
    digest = evidence.get("manifest_root_sha256")
    if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ContractError("retained session manifest-root digest is invalid")
    expected_root_digest = hashlib.sha256(_canonical_bytes(sessions)).hexdigest()
    if digest != expected_root_digest:
        raise ContractError("retained session manifest-root digest is inconsistent")

    entry_bar_time = _as_utc(
        entry_observation["bar_time"], "session_price_evidence.entry.bar_time",
    )
    if entry_observation["bar_time"] != _iso_utc(entry_bar_time) or entry_bar_time != entry:
        raise ContractError("retained session entry clock disagrees with the outcome")
    entry_price = _exact_canonical_price(
        entry_observation["open"], "session_price_evidence.entry.open",
    )

    exit_bar_time = _as_utc(exit_observation["bar_time"], "session_price_evidence.exit.bar_time")
    exit_time = _as_utc(exit_observation["time"], "session_price_evidence.exit.time")
    if (
        exit_observation["bar_time"] != _iso_utc(exit_bar_time)
        or exit_observation["time"] != _iso_utc(exit_time)
        or exit_bar_time != final_bar_time
        or exit_time != target_time
    ):
        raise ContractError("retained session exit clocks disagree with the outcome")
    exit_price = _exact_canonical_price(
        exit_observation["close"], "session_price_evidence.exit.close",
    )
    extrema_times: dict[str, datetime] = {}
    extrema_values: dict[str, float] = {}
    for side in ("high", "low"):
        observation = extrema[side]
        observed_time = _as_utc(
            observation["bar_time"], f"session_price_evidence.extrema.{side}.bar_time",
        )
        if observation["bar_time"] != _iso_utc(observed_time):
            raise ContractError("retained session extrema clocks must be canonical UTC")
        extrema_times[side] = observed_time
        extrema_values[side] = _exact_canonical_price(
            observation["value"],
            f"session_price_evidence.extrema.{side}.value",
        )
    if extrema_values["high"] < max(entry_price, exit_price):
        raise ContractError("retained session high extrema contradicts entry or exit")
    if extrema_values["low"] > min(entry_price, exit_price):
        raise ContractError("retained session low extrema contradicts entry or exit")

    _validate_session_evidence_grid(
        evidence,
        entry=entry,
        target_session=target_time.astimezone(ET).date(),
        target_time=target_time,
        bar_seconds=bar_seconds,
        extrema_times=extrema_times,
    )
    ret = round(exit_price / entry_price - 1.0, 8)
    mfe = round(extrema_values["high"] / entry_price - 1.0, 8)
    mae = round(extrema_values["low"] / entry_price - 1.0, 8)
    return entry_price, exit_price, ret, mfe, mae


def _reject_duplicate_object_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON object key {key!r}")
        obj[key] = value
    return obj


def _strict_json_loads(value):
    return json.loads(
        value,
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {token}")
        ),
    )


def _as_utc(value: object, field: str) -> datetime:
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        out = datetime.fromisoformat(text)
    except Exception as exc:  # noqa: BLE001
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if out.tzinfo is None:
        raise ContractError(f"{field} must carry an explicit timezone")
    return out.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception as exc:  # noqa: BLE001
        raise ContractError(f"{field} must be YYYY-MM-DD") from exc


def _finite_float(value: object, field: str, *, positive: bool = False) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must be numeric") from exc
    if not math.isfinite(out) or (positive and out <= 0):
        raise ContractError(f"{field} must be {'positive and ' if positive else ''}finite")
    return out


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _exact_finite_number(value: object, field: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ContractError(f"{field} must be an exact JSON number")
    return _finite_float(value, field, positive=positive)


def _exact_iso_date(value: object, field: str) -> str:
    if type(value) is not str:
        raise ContractError(f"{field} must be an exact YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be an exact YYYY-MM-DD string") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{field} must be an exact YYYY-MM-DD string")
    return parsed.isoformat()


def validate_episode(row: dict[str, Any]) -> None:
    """Validate one immutable decision-time row; raise ``ContractError`` on drift."""
    _validate_json_schema(row, "options.signal_episode.v1.schema.json")
    required = {
        "schema", "episode_id", "source", "source_event_id", "event_time",
        "observed_at", "decision_at", "available_at", "published_at",
        "anchor_strategy", "session_date", "ticker", "contract",
        "decision", "feature_snapshot", "provenance", "quality",
    }
    missing = required - set(row)
    if missing:
        raise ContractError(f"episode missing fields: {sorted(missing)}")
    if row["schema"] != EPISODE_SCHEMA:
        raise ContractError(f"episode schema must be {EPISODE_SCHEMA!r}")
    source = str(row["source"]).strip()
    if not source or source != row["source"]:
        raise ContractError("source must be non-empty and whitespace-normalized")
    source_event_id = str(row["source_event_id"]).strip()
    if not source_event_id or source_event_id != row["source_event_id"]:
        raise ContractError("source_event_id is required")
    if row["episode_id"] != _episode_id(source, source_event_id):
        raise ContractError("episode_id must be stable for schema, source, and source_event_id")

    event_time = _as_utc(row["event_time"], "event_time")
    observed_at = _as_utc(row["observed_at"], "observed_at")
    decision_at = _as_utc(row["decision_at"], "decision_at")
    available_at = _as_utc(row["available_at"], "available_at")
    published_at = (
        _as_utc(row["published_at"], "published_at")
        if row["published_at"] is not None else None
    )
    if not (event_time <= observed_at <= decision_at <= available_at):
        raise ContractError(
            "clock order must be event_time <= observed_at <= decision_at <= available_at"
        )
    if published_at is not None and published_at < available_at:
        raise ContractError("published_at cannot predate durable availability")
    if row["anchor_strategy"] != "durable_available_at":
        raise ContractError("v1 horizon anchor strategy must be durable_available_at")

    session = _as_date(row["session_date"], "session_date")
    if not nyse_calendar.is_session(session):
        raise ContractError("session_date is not an NYSE session")
    if event_time.astimezone(ET).date() != session:
        raise ContractError("event_time does not belong to session_date in exchange time")
    open_et, close_et = session_window_et(session)
    open_utc = open_et.astimezone(timezone.utc)
    close_utc = close_et.astimezone(timezone.utc)
    if not (open_utc <= event_time < close_utc):
        raise ContractError("v1 rejects premarket, after-close, and at-close events")
    if observed_at < open_utc:
        raise ContractError("decision-time clocks cannot predate the regular-session open")
    if any(
        value.astimezone(ET).date() != session
        for value in (observed_at, decision_at, available_at)
    ):
        raise ContractError("decision-time clocks must remain on the event exchange date")

    ticker = str(row["ticker"]).strip().upper()
    if not ticker or ticker != row["ticker"]:
        raise ContractError("ticker must be non-empty uppercase")
    contract = row["contract"]
    if not isinstance(contract, dict):
        raise ContractError("contract must be an object")
    if contract.get("right") not in ("C", "P"):
        raise ContractError("contract.right must be C or P")
    _finite_float(contract.get("strike"), "contract.strike", positive=True)
    expiry = _as_date(contract.get("expiration"), "contract.expiration")
    if expiry < session:
        raise ContractError("contract expiration precedes the event session")

    decision = row["decision"]
    if decision.get("disposition") not in DISPOSITIONS:
        raise ContractError("decision.disposition is outside the frozen vocabulary")
    if decision.get("underlying_direction") not in UNDERLYING_DIRECTIONS:
        raise ContractError("decision.underlying_direction is invalid")
    if decision.get("option_action") not in OPTION_ACTIONS:
        raise ContractError("decision.option_action is invalid")
    if decision.get("authority") != FALSE_AUTHORITY:
        raise ContractError("decision authority must remain identically false")

    features = row["feature_snapshot"]
    if not isinstance(features, dict):
        raise ContractError("feature_snapshot must be an object")
    if features.get("flow_side") not in ("~buy", "~sell", "mixed"):
        raise ContractError("feature_snapshot.flow_side must retain the soft-side vocabulary")
    _finite_float(features.get("premium_usd"), "feature_snapshot.premium_usd", positive=True)
    if features.get("selection_rule") != "premium_floor/v1":
        raise ContractError("feature_snapshot.selection_rule must be premium_floor/v1")
    selection_floor = _exact_finite_number(
        features.get("selection_floor_usd"),
        "feature_snapshot.selection_floor_usd",
    )
    if selection_floor < 0 or float(features["premium_usd"]) < selection_floor:
        raise ContractError("episode premium must meet its frozen selection floor")
    if features.get("selection_root_class") not in ("etf_anchor", "single_name"):
        raise ContractError("feature_snapshot.selection_root_class is invalid")
    _finite_float(features.get("contracts"), "feature_snapshot.contracts", positive=True)
    dte = features.get("dte")
    if dte is not None:
        if type(dte) is not int or dte < 0:
            raise ContractError("feature_snapshot.dte must be an exact non-negative integer")
        if dte != (expiry - session).days:
            raise ContractError("feature_snapshot.dte disagrees with expiration and session")
    avg_option_price = features.get("avg_option_trade_price")
    _finite_float(
        avg_option_price, "feature_snapshot.avg_option_trade_price", positive=True,
    )
    expected_avg = float(features["premium_usd"]) / (float(features["contracts"]) * 100.0)
    if not math.isclose(float(avg_option_price), expected_avg, abs_tol=0.0051):
        raise ContractError(
            "avg_option_trade_price disagrees with premium_usd and contracts"
        )

    provenance = row["provenance"]
    expected_artifact = f"live_flow/events/{session.isoformat()}.jsonl"
    if provenance.get("source_artifact") != expected_artifact:
        raise ContractError(
            "source_artifact session must exactly match the episode exchange session"
        )
    snapshot_asof = _as_utc(
        provenance.get("source_snapshot_asof"),
        "provenance.source_snapshot_asof",
    )
    if snapshot_asof != available_at:
        raise ContractError("v1 source_snapshot_asof must equal durable event availability")
    oi_vintage = provenance.get("oi_vintage")
    if oi_vintage is not None:
        oi_date = _as_date(oi_vintage, "provenance.oi_vintage")
        if oi_date >= session or not nyse_calendar.is_session(oi_date):
            raise ContractError("OI vintage must be a real session strictly before the event")
    if features.get("vol_gt_prior_oi") is not None and oi_vintage is None:
        raise ContractError("a vol_gt_prior_oi feature requires its exact OI vintage")
    if provenance.get("feature_cutoff") != row["available_at"]:
        raise ContractError("feature_cutoff must equal available_at")
    if row["quality"].get("availability_exact") is not True:
        raise ContractError("v1 admits only exact event-level availability stamps")
    if row["quality"].get("source_baseline") != "floor":
        raise ContractError("v1 contract episodes are floor-selected only")


def validate_outcome(row: dict[str, Any]) -> None:
    """Validate one append-only H+60 label row."""
    _validate_json_schema(row, "options.signal_episode_outcome.v1.schema.json")
    required = {
        "schema", "outcome_id", "episode_id", "horizon_minutes", "status",
        "reason", "horizon_anchor", "target_time", "computed_at", "matured_at",
        "measurement", "underlying", "option", "provenance", "label_authority",
    }
    missing = required - set(row)
    if missing:
        raise ContractError(f"outcome missing fields: {sorted(missing)}")
    if row["schema"] != OUTCOME_SCHEMA:
        raise ContractError(f"outcome schema must be {OUTCOME_SCHEMA!r}")
    if type(row["horizon_minutes"]) is not int or row["horizon_minutes"] != HORIZON_MINUTES:
        raise ContractError("v1 outcome horizon must be 60 minutes")
    expected_id = _outcome_id(str(row["episode_id"]), row["horizon_minutes"])
    if row["outcome_id"] != expected_id:
        raise ContractError("outcome_id must be stable for schema, measurement version, episode, and horizon")
    status = row["status"]
    if status not in ("complete", "incomplete"):
        raise ContractError("persisted outcomes must be complete or terminal incomplete")
    if status == "complete" and row["reason"] is not None:
        raise ContractError("complete outcomes must have a null reason")
    if status == "incomplete" and (
        not isinstance(row["reason"], str) or not row["reason"].strip()
    ):
        raise ContractError("terminal incomplete outcomes require a reason")
    if status == "incomplete" and row["reason"] not in TERMINAL_INCOMPLETE_REASONS:
        raise ContractError("terminal incomplete outcome reason is outside the v1 vocabulary")
    anchor = _as_utc(row["horizon_anchor"], "horizon_anchor")
    target = _as_utc(row["target_time"], "target_time")
    if target - anchor != timedelta(minutes=HORIZON_MINUTES):
        raise ContractError("target_time must be exactly H+60 from horizon_anchor")
    computed = _as_utc(row["computed_at"], "computed_at")
    matured = _as_utc(row["matured_at"], "matured_at")
    if matured < target or computed < matured:
        raise ContractError("matured_at must be at/after target_time and not exceed computed_at")
    if row["label_authority"] != "research_only":
        raise ContractError("outcome label authority must remain research_only")

    measurement = row["measurement"]
    if measurement.get("version") != MEASUREMENT_VERSION:
        raise ContractError("measurement.version is outside the v1 contract")
    if measurement.get("kind") not in ("aligned_bar_proxy", "unavailable"):
        raise ContractError("measurement.kind is invalid")
    if not isinstance(measurement.get("target_aligned"), bool):
        raise ContractError("measurement.target_aligned must be boolean")
    if not isinstance(measurement.get("training_eligible"), bool):
        raise ContractError("measurement.training_eligible must be boolean")
    reasons = measurement.get("training_ineligibility_reasons")
    if not isinstance(reasons, list) or any(not isinstance(v, str) or not v for v in reasons):
        raise ContractError("measurement training reasons must be a string list")
    if measurement["training_eligible"] and reasons:
        raise ContractError("training-eligible measurements cannot carry ineligibility reasons")
    if not measurement["training_eligible"] and not reasons:
        raise ContractError("training-ineligible measurements require reasons")
    window = measurement.get("window")
    if not isinstance(window, dict) or set(window) != {"start", "end"}:
        raise ContractError("measurement.window must contain exactly start and end")

    underlying = row["underlying"]
    provenance = row["provenance"]
    option = row["option"]
    if status == "complete":
        if underlying.get("status") != "complete":
            raise ContractError("complete outcomes require underlying.status=complete")
        for key in (
            "entry_time", "exit_time", "entry_price", "exit_price", "ret", "mfe", "mae",
            "entry_delay_minutes", "exit_delay_minutes", "bar_seconds", "path_basis",
            "evidence",
        ):
            if underlying.get(key) is None:
                raise ContractError(f"complete outcome missing underlying.{key}")
        entry = _as_utc(underlying["entry_time"], "underlying.entry_time")
        exit_ = _as_utc(underlying["exit_time"], "underlying.exit_time")
        if entry < anchor or exit_ < target or exit_ <= entry:
            raise ContractError("underlying observations must bracket the anchored H+60 window")
        if measurement["kind"] != "aligned_bar_proxy":
            raise ContractError("complete v1 outcomes must declare aligned_bar_proxy")
        if window["start"] != underlying["entry_time"] or window["end"] != underlying["exit_time"]:
            raise ContractError("measurement window must equal the actual entry/exit observation window")
        target_aligned = entry == anchor and exit_ == target
        if measurement["target_aligned"] is not target_aligned:
            raise ContractError("measurement.target_aligned disagrees with actual timestamps")
        bar_seconds = underlying.get("bar_seconds")
        if type(bar_seconds) is not int or bar_seconds not in (60, 300, 900, 1800, 3600):
            raise ContractError("complete outcome bar_seconds is outside the supported cadence")
        price_delay = provenance.get("price_delay_minutes")
        if type(price_delay) is not int or price_delay < 0:
            raise ContractError("complete outcomes require an exact non-negative price delay")
        expected_aligned, expected_eligible, expected_reasons = _training_quality(
            available=anchor,
            target=target,
            entry=entry,
            exit_=exit_,
            bar_seconds=bar_seconds,
            price_delay_minutes=price_delay,
        )
        if measurement["target_aligned"] is not expected_aligned:
            raise ContractError("measurement target alignment is not reproducible")
        if measurement["training_eligible"] is not expected_eligible:
            raise ContractError("measurement.training_eligible violates the exactness gate")
        if reasons != expected_reasons:
            raise ContractError("measurement training reasons are not reproducible")
        source_available = _as_utc(
            provenance.get("source_available_at"), "provenance.source_available_at",
        )
        source_delay_maturity = exit_ + timedelta(minutes=price_delay)
        if source_available < source_delay_maturity:
            raise ContractError(
                "source_available_at cannot predate the exit observation plus vendor delay"
            )
        expected_maturity = max(source_delay_maturity, source_available)
        if matured != expected_maturity:
            raise ContractError(
                "matured_at must include both vendor delay and source-receipt availability"
            )
        price_source = provenance.get("price_source")
        if not isinstance(price_source, str) or not price_source.strip():
            raise ContractError("complete outcomes require non-empty price_source provenance")
        if provenance.get("source_receipt_schema") != PRICE_RECEIPT_SCHEMA:
            raise ContractError("complete outcome source receipt schema is outside v1")
        source_digest = provenance.get("source_file_sha256")
        if type(source_digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", source_digest):
            raise ContractError("complete outcome requires an exact source file digest")
        source_rows = provenance.get("source_file_row_count")
        if type(source_rows) is not int or source_rows <= 0:
            raise ContractError("complete outcome requires a positive source row count")
        source_first = _as_utc(
            provenance.get("source_file_first_time"), "provenance.source_file_first_time",
        )
        source_last = _as_utc(
            provenance.get("source_file_last_time"), "provenance.source_file_last_time",
        )
        if source_first > entry or source_last < exit_ or source_first > source_last:
            raise ContractError("source file receipt does not cover the retained measurement")
        if provenance.get("adjusted") is not True:
            raise ContractError("v1 complete outcomes require adjusted Polygon aggregates")
        if provenance.get("price_basis") != PRICE_BASIS:
            raise ContractError("price_basis is outside the v1 contract")
        if provenance.get("timestamp_basis") != TIMESTAMP_BASIS:
            raise ContractError("timestamp_basis is outside the v1 contract")
        price_vintage = _as_utc(provenance.get("price_vintage"), "provenance.price_vintage")
        if price_vintage != exit_:
            raise ContractError("price_vintage must equal the latest source bar timestamp used")
        if underlying.get("path_basis") != "aligned_bar_open_to_open_with_intervening_bar_high_low":
            raise ContractError("complete outcome path_basis is outside the v1 contract")
        _finite_float(underlying["entry_price"], "underlying.entry_price", positive=True)
        _finite_float(underlying["exit_price"], "underlying.exit_price", positive=True)
        entry_price = float(underlying["entry_price"])
        exit_price = float(underlying["exit_price"])
        ret = _finite_float(underlying["ret"], "underlying.ret")
        mfe = _finite_float(underlying["mfe"], "underlying.mfe")
        mae = _finite_float(underlying["mae"], "underlying.mae")
        if mae < -1.0:
            raise ContractError("underlying.mae cannot fall below -100 percent")
        if not math.isclose(ret, exit_price / entry_price - 1.0, abs_tol=1e-7):
            raise ContractError("underlying.ret is arithmetically inconsistent")
        if mfe < max(0.0, ret) - 1e-7:
            raise ContractError("underlying.mfe must include entry and exit observations")
        if mae > min(0.0, ret) + 1e-7:
            raise ContractError("underlying.mae must include entry and exit observations")
        evidence_entry, evidence_exit, evidence_ret, evidence_mfe, evidence_mae = (
            _validate_price_evidence(
                underlying.get("evidence"),
                entry=entry,
                exit_=exit_,
                bar_seconds=bar_seconds,
            )
        )
        if not all((
            math.isclose(entry_price, evidence_entry, abs_tol=1e-8),
            math.isclose(exit_price, evidence_exit, abs_tol=1e-8),
            math.isclose(ret, evidence_ret, abs_tol=1e-8),
            math.isclose(mfe, evidence_mfe, abs_tol=1e-8),
            math.isclose(mae, evidence_mae, abs_tol=1e-8),
        )):
            raise ContractError("outcome arithmetic disagrees with retained price evidence")
        if source_rows < underlying["evidence"]["observation_count"]:
            raise ContractError("source row count cannot be smaller than retained evidence")
        entry_delay = _finite_float(
            underlying.get("entry_delay_minutes"), "underlying.entry_delay_minutes",
        )
        exit_delay = _finite_float(
            underlying.get("exit_delay_minutes"), "underlying.exit_delay_minutes",
        )
        if entry_delay < 0 or exit_delay < 0:
            raise ContractError("measurement alignment delays cannot be negative")
        if not math.isclose(entry_delay, (entry - anchor).total_seconds() / 60.0, abs_tol=1e-3):
            raise ContractError("entry_delay_minutes disagrees with the measurement window")
        if not math.isclose(exit_delay, (exit_ - target).total_seconds() / 60.0, abs_tol=1e-3):
            raise ContractError("exit_delay_minutes disagrees with the measurement window")
    else:
        if measurement["kind"] != "unavailable" or any(value is not None for value in window.values()):
            raise ContractError("incomplete outcomes must have an unavailable null measurement window")
        if measurement["target_aligned"] or measurement["training_eligible"]:
            raise ContractError("incomplete outcomes cannot be aligned or training eligible")
        if reasons != ["outcome_incomplete"]:
            raise ContractError("incomplete outcomes require the canonical ineligibility reason")
        if underlying.get("status") != "unavailable" or any(
            value is not None for key, value in underlying.items() if key != "status"
        ):
            raise ContractError("incomplete outcomes require a fully null unavailable underlying")
        if matured != target:
            raise ContractError("terminal incomplete outcomes mature at the desired H+60 target")
        if any(value is not None for value in provenance.values()):
            raise ContractError("incomplete outcomes cannot invent price provenance")

    if option.get("status") != "unavailable":
        raise ContractError("v1 option outcomes must remain unavailable")
    if option.get("reason") != "no_executable_nbbo_quote_path":
        raise ContractError("v1 option outcome requires the canonical unavailable reason")
    if option.get("quote_basis") is not None or any(
        option.get(key) is not None for key in ("ret", "mfe", "mae")
    ):
        raise ContractError("v1 option outcomes cannot carry quote or return fields")


def validate_outcome_against_episode(
    outcome: dict[str, Any], episode: dict[str, Any],
) -> None:
    """Validate the immutable episode/outcome join, not just each row alone."""
    validate_episode(episode)
    validate_outcome(outcome)
    if outcome["episode_id"] != episode["episode_id"]:
        raise ContractError("outcome references a different episode")
    anchor = _as_utc(outcome["horizon_anchor"], "horizon_anchor")
    available = _as_utc(episode["available_at"], "episode.available_at")
    if anchor != available:
        raise ContractError("outcome horizon_anchor must equal episode.available_at")

    session = _as_date(episode["session_date"], "episode.session_date")
    open_et, close_et = session_window_et(session)
    open_utc = open_et.astimezone(timezone.utc)
    close_utc = close_et.astimezone(timezone.utc)
    target = _as_utc(outcome["target_time"], "target_time")
    if outcome["status"] == "complete":
        if available >= close_utc or target >= close_utc:
            raise ContractError("complete outcome is impossible across the session close")
        underlying = outcome["underlying"]
        entry = _as_utc(underlying["entry_time"], "underlying.entry_time")
        exit_ = _as_utc(underlying["exit_time"], "underlying.exit_time")
        if not (open_utc <= entry < exit_ < close_utc):
            raise ContractError(
                "complete measurement window must remain inside the episode session"
            )
        bar_seconds = underlying["bar_seconds"]
        max_entry_gap = max(300, int(bar_seconds * 1.10))
        if (entry - max(available, open_utc)).total_seconds() > max_entry_gap:
            raise ContractError("complete measurement entry exceeds the admitted bar gap")
        seconds_after_entry = max(0.0, (target - entry).total_seconds())
        cadence_steps = max(1, math.ceil(seconds_after_entry / bar_seconds))
        expected_exit = entry + timedelta(seconds=cadence_steps * bar_seconds)
        if exit_ != expected_exit:
            raise ContractError(
                "complete measurement exit is not the first aligned bar boundary"
            )
        price_source = outcome["provenance"].get("price_source")
        expected_source_file = f"{episode['ticker']}.parquet"
        if (
            type(price_source) is not str
            or not price_source
            or Path(price_source).name != expected_source_file
        ):
            raise ContractError(
                "complete outcome price source must match the episode ticker parquet"
            )
        return

    reason = outcome["reason"]
    if available >= close_utc:
        expected_reason = "decision_after_session_close"
    elif target >= close_utc:
        expected_reason = "horizon_crosses_session_close"
    else:
        raise ContractError(
            "terminal incomplete outcome is not reproducible from episode clocks"
        )
    if reason != expected_reason:
        raise ContractError("terminal outcome reason disagrees with episode session clocks")


def _session_target(session: date, horizon: str) -> tuple[int, date, datetime]:
    if type(horizon) is not str or horizon not in SESSION_HORIZONS:
        raise ContractError("session outcome horizon is outside the frozen vocabulary")
    offset = SESSION_HORIZONS[horizon]
    target_session = nyse_calendar.session_n_forward(session, offset)
    if target_session is None:
        raise ContractError("session outcome target cannot be resolved from the NYSE calendar")
    _, close_et = session_window_et(target_session)
    return offset, target_session, close_et.astimezone(timezone.utc)


def _validate_runtime_session_evidence_grid(
    times: list[datetime],
    *,
    entry: datetime,
    target_session: date,
    target_time: datetime,
    bar_seconds: int,
) -> None:
    """Fully inspect the in-memory path before committing its bounded summary."""
    if not times or times[0] != entry:
        raise ContractError("session evidence must begin at the admitted entry bar")
    cadence = timedelta(seconds=bar_seconds)
    entry_session = entry.astimezone(ET).date()
    expected_sessions = nyse_calendar.sessions_between(entry_session, target_session)
    if not expected_sessions or expected_sessions[-1] != target_session:
        raise ContractError("session evidence target range is not a valid NYSE span")
    seen_dates = [stamp.astimezone(ET).date() for stamp in times]
    if sorted(set(seen_dates)) != expected_sessions:
        raise ContractError("session evidence omits or invents a target-window session")
    max_open_gap = bar_seconds * 1.10
    for index, session in enumerate(expected_sessions):
        open_et, close_et = session_window_et(session)
        open_utc = open_et.astimezone(timezone.utc)
        close_utc = close_et.astimezone(timezone.utc)
        stamps = [stamp for stamp in times if stamp.astimezone(ET).date() == session]
        if not stamps or any(not (open_utc <= stamp < close_utc) for stamp in stamps):
            raise ContractError("session evidence contains a non-RTH or empty session")
        expected_start = entry if index == 0 else open_utc
        if (stamps[0] - expected_start).total_seconds() > max_open_gap:
            raise ContractError("session evidence begins after the admitted cadence gap")
        if any(later - earlier != cadence for earlier, later in pairwise(stamps)):
            raise ContractError("session evidence contains an interior cadence gap")
        if not (stamps[-1] < close_utc <= stamps[-1] + cadence):
            raise ContractError("session evidence lacks the close-covering bar")
    if target_time != session_window_et(target_session)[1].astimezone(timezone.utc):
        raise ContractError("session outcome target_time is not the declared scheduled close")


def _validate_session_evidence_grid(
    evidence: dict[str, Any],
    *,
    entry: datetime,
    target_session: date,
    target_time: datetime,
    bar_seconds: int,
    extrema_times: dict[str, datetime],
) -> None:
    """Validate compact manifests without claiming the inline path is replayable."""
    manifests = evidence.get("sessions")
    if not isinstance(manifests, list) or not manifests:
        raise ContractError("session evidence requires non-empty cadence manifests")
    entry_session = entry.astimezone(ET).date()
    expected_sessions = nyse_calendar.sessions_between(entry_session, target_session)
    if not expected_sessions or expected_sessions[-1] != target_session:
        raise ContractError("session evidence target range is not a valid NYSE span")
    if len(manifests) != len(expected_sessions):
        raise ContractError("session evidence omits or invents a target-window session")
    if target_time != session_window_et(target_session)[1].astimezone(timezone.utc):
        raise ContractError("session outcome target_time is not the declared scheduled close")

    cadence = timedelta(seconds=bar_seconds)
    max_open_gap = bar_seconds * 1.10
    total_observations = 0
    grids: list[tuple[datetime, datetime]] = []
    for index, (manifest, session) in enumerate(zip(manifests, expected_sessions)):
        if not isinstance(manifest, dict) or set(manifest) != {
            "session", "first_bar_time", "last_bar_time", "uncovered_open_seconds",
            "observation_count", "expected_count", "session_path_sha256",
        }:
            raise ContractError("session evidence manifest has an invalid shape")
        if manifest["session"] != session.isoformat():
            raise ContractError("session evidence manifest date disagrees with its NYSE span")
        first = _as_utc(
            manifest["first_bar_time"], f"session_price_evidence.sessions[{index}].first_bar_time",
        )
        last = _as_utc(
            manifest["last_bar_time"], f"session_price_evidence.sessions[{index}].last_bar_time",
        )
        if (
            manifest["first_bar_time"] != _iso_utc(first)
            or manifest["last_bar_time"] != _iso_utc(last)
        ):
            raise ContractError("session evidence manifest clocks must be canonical UTC")
        open_et, close_et = session_window_et(session)
        open_utc = open_et.astimezone(timezone.utc)
        close_utc = close_et.astimezone(timezone.utc)
        if not (open_utc <= first <= last < close_utc):
            raise ContractError("session evidence manifest endpoints must remain inside RTH")
        expected_start = entry if index == 0 else open_utc
        if first < expected_start or (first - expected_start).total_seconds() > max_open_gap:
            raise ContractError("session evidence begins after the admitted cadence gap")
        if index == 0 and first != entry:
            raise ContractError("session evidence first manifest must begin at entry")
        if not (last < close_utc <= last + cadence):
            raise ContractError("session evidence lacks the close-covering bar")
        span_seconds = int((last - first).total_seconds())
        if span_seconds < 0 or span_seconds % bar_seconds:
            raise ContractError("session evidence manifest clocks violate cadence")
        expected_count = span_seconds // bar_seconds + 1
        observation_count = manifest.get("observation_count")
        declared_expected = manifest.get("expected_count")
        if (
            type(observation_count) is not int
            or type(declared_expected) is not int
            or observation_count < 1
            or observation_count != expected_count
            or declared_expected != expected_count
        ):
            raise ContractError("session evidence manifest count arithmetic is inconsistent")
        uncovered = manifest.get("uncovered_open_seconds")
        expected_uncovered = int((first - open_utc).total_seconds())
        if type(uncovered) is not int or uncovered != expected_uncovered:
            raise ContractError("session evidence uncovered-open disclosure is inconsistent")
        digest = manifest.get("session_path_sha256")
        if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ContractError("session evidence manifest digest is invalid")
        total_observations += observation_count
        grids.append((first, last))

    if type(evidence.get("observation_count")) is not int or (
        evidence["observation_count"] != total_observations
    ):
        raise ContractError("session evidence total observation_count is inconsistent")
    exit_bar_time = _as_utc(
        evidence["exit"]["bar_time"], "session_price_evidence.exit.bar_time",
    )
    if manifests[-1]["last_bar_time"] != _iso_utc(exit_bar_time):
        raise ContractError("session evidence final manifest disagrees with exit bar")
    for side, observed_time in extrema_times.items():
        on_grid = any(
            first <= observed_time <= last
            and int((observed_time - first).total_seconds()) % bar_seconds == 0
            for first, last in grids
        )
        if not on_grid:
            raise ContractError(f"session evidence {side} extrema is outside committed grids")


def validate_session_outcome(row: dict[str, Any]) -> None:
    """Validate one append-only EOD/1d/3d/5d/10d close-outcome row."""
    _validate_json_schema(
        row, "options.signal_episode_session_outcome.v1.schema.json",
    )
    required = {
        "schema", "outcome_id", "episode_id", "horizon", "horizon_sessions",
        "status", "reason", "horizon_anchor", "target_session", "target_time",
        "computed_at", "matured_at", "measurement", "underlying", "option",
        "provenance", "label_authority",
    }
    if set(row) != required:
        raise ContractError("session outcome fields differ from the exact v1 contract")
    if row["schema"] != SESSION_OUTCOME_SCHEMA:
        raise ContractError(f"session outcome schema must be {SESSION_OUTCOME_SCHEMA!r}")
    horizon = row["horizon"]
    if type(horizon) is not str or horizon not in SESSION_HORIZONS:
        raise ContractError("session outcome horizon is outside the frozen vocabulary")
    horizon_sessions = row["horizon_sessions"]
    if type(horizon_sessions) is not int or horizon_sessions != SESSION_HORIZONS[horizon]:
        raise ContractError("session outcome horizon_sessions disagrees with horizon")
    if row["outcome_id"] != _session_outcome_id(str(row["episode_id"]), horizon):
        raise ContractError("session outcome_id is not stable for its schema/version/episode/horizon")

    status = row["status"]
    if status not in ("complete", "incomplete"):
        raise ContractError("persisted session outcomes must be complete or terminal incomplete")
    if status == "complete" and row["reason"] is not None:
        raise ContractError("complete session outcomes must have a null reason")
    if status == "incomplete" and row["reason"] != "decision_after_target_close":
        raise ContractError("terminal session outcome reason is outside v1")
    anchor = _as_utc(row["horizon_anchor"], "horizon_anchor")
    target_session = _as_date(row["target_session"], "target_session")
    if type(row["target_session"]) is not str or row["target_session"] != target_session.isoformat():
        raise ContractError("target_session must be a canonical exact date")
    if not nyse_calendar.is_session(target_session):
        raise ContractError("target_session is not an NYSE session")
    target = _as_utc(row["target_time"], "target_time")
    computed = _as_utc(row["computed_at"], "computed_at")
    matured = _as_utc(row["matured_at"], "matured_at")
    for field, parsed in (
        ("horizon_anchor", anchor), ("target_time", target),
        ("computed_at", computed), ("matured_at", matured),
    ):
        if row[field] != _iso_utc(parsed):
            raise ContractError(f"{field} must be canonical UTC")
    expected_close = session_window_et(target_session)[1].astimezone(timezone.utc)
    if target != expected_close:
        raise ContractError("target_time must be the declared recurring-schedule close")
    if matured < max(target, anchor) or computed < matured:
        raise ContractError(
            "session outcome maturity must follow target and decision availability"
        )
    if row["label_authority"] != "research_only":
        raise ContractError("session outcome label authority must remain research_only")

    measurement = row["measurement"]
    if measurement.get("version") != SESSION_MEASUREMENT_VERSION:
        raise ContractError("session measurement.version is outside v1")
    if measurement.get("calendar_basis") != SESSION_CALENDAR_BASIS:
        raise ContractError("session measurement.calendar_basis is outside v1")
    if measurement.get("kind") not in ("session_close_bar_proxy", "unavailable"):
        raise ContractError("session measurement.kind is invalid")
    if not isinstance(measurement.get("target_aligned"), bool):
        raise ContractError("session measurement.target_aligned must be boolean")
    if measurement.get("training_eligible") is not False:
        raise ContractError("session outcomes are never training eligible in v1")
    reasons = measurement.get("training_ineligibility_reasons")
    if not isinstance(reasons, list) or any(type(reason) is not str or not reason for reason in reasons):
        raise ContractError("session measurement requires exact training ineligibility reasons")
    window = measurement.get("window")
    if not isinstance(window, dict) or set(window) != {"start", "end"}:
        raise ContractError("session measurement.window must contain exactly start and end")

    underlying = row["underlying"]
    provenance = row["provenance"]
    option = row["option"]
    if status == "complete":
        if measurement["kind"] != "session_close_bar_proxy":
            raise ContractError("complete session outcomes require session_close_bar_proxy")
        if reasons != ["session_outcome_shadow_only"]:
            raise ContractError("complete session outcomes require the frozen shadow-only reason")
        if underlying.get("status") != "complete":
            raise ContractError("complete session outcomes require underlying.status=complete")
        for key in (
            "entry_time", "exit_time", "entry_price", "exit_price", "ret", "mfe", "mae",
            "entry_delay_minutes", "exit_delay_minutes", "bar_seconds", "path_basis", "evidence",
        ):
            if underlying.get(key) is None:
                raise ContractError(f"complete session outcome missing underlying.{key}")
        entry = _as_utc(underlying["entry_time"], "underlying.entry_time")
        exit_ = _as_utc(underlying["exit_time"], "underlying.exit_time")
        if underlying["entry_time"] != _iso_utc(entry) or underlying["exit_time"] != _iso_utc(exit_):
            raise ContractError("session underlying clocks must be canonical UTC")
        if entry < anchor or exit_ != target or entry >= exit_:
            raise ContractError("session underlying window must run from post-anchor entry to target close")
        if window != {"start": underlying["entry_time"], "end": underlying["exit_time"]}:
            raise ContractError("session measurement window must equal the actual entry/exit window")
        if measurement["target_aligned"] is not (entry == anchor):
            raise ContractError("session target alignment disagrees with the admitted entry")
        bar_seconds = underlying["bar_seconds"]
        if type(bar_seconds) is not int or bar_seconds not in (60, 300, 900, 1800, 3600):
            raise ContractError("session outcome bar_seconds is outside the supported cadence")
        if underlying["path_basis"] != (
            "first_admissible_bar_open_to_declared_session_close_with_observed_rth_bar_high_low_proxies"
        ):
            raise ContractError("session outcome path_basis is outside v1")

        evidence = underlying["evidence"]
        try:
            final_bar_time = _as_utc(
                evidence["exit"]["bar_time"], "session_price_evidence.exit.bar_time",
            )
        except (KeyError, TypeError) as exc:
            raise ContractError("session outcome lacks final-bar evidence") from exc
        ev_entry, ev_exit, ev_ret, ev_mfe, ev_mae = _validate_session_price_evidence(
            evidence,
            entry=entry,
            target_time=target,
            final_bar_time=final_bar_time,
            bar_seconds=bar_seconds,
        )
        entry_price = _exact_finite_number(
            underlying["entry_price"], "underlying.entry_price", positive=True,
        )
        exit_price = _exact_finite_number(
            underlying["exit_price"], "underlying.exit_price", positive=True,
        )
        ret = _exact_finite_number(underlying["ret"], "underlying.ret")
        mfe = _exact_finite_number(underlying["mfe"], "underlying.mfe")
        mae = _exact_finite_number(underlying["mae"], "underlying.mae")
        if mae < -1.0 or (
            entry_price, exit_price, ret, mfe, mae
        ) != (
            ev_entry, ev_exit, ev_ret, ev_mfe, ev_mae
        ):
            raise ContractError("session outcome arithmetic disagrees with retained evidence")
        entry_delay = _exact_finite_number(
            underlying["entry_delay_minutes"], "underlying.entry_delay_minutes",
        )
        exit_delay = _exact_finite_number(
            underlying["exit_delay_minutes"], "underlying.exit_delay_minutes",
        )
        if entry_delay < 0 or not math.isclose(
            entry_delay,
            (entry - anchor).total_seconds() / 60.0,
            rel_tol=0.0,
            abs_tol=1e-3,
        ):
            raise ContractError("session entry_delay_minutes disagrees with the window")
        if exit_delay != 0:
            raise ContractError("session close exit delay must be exactly zero")

        delay = provenance.get("price_delay_minutes")
        if type(delay) is not int or delay < 0:
            raise ContractError("session outcomes require an exact non-negative price delay")
        source_available = _as_utc(
            provenance.get("source_available_at"), "provenance.source_available_at",
        )
        if provenance.get("source_available_at") != _iso_utc(source_available):
            raise ContractError("session source_available_at must be canonical UTC")
        expected_maturity = max(target + timedelta(minutes=delay), source_available)
        if source_available < target + timedelta(minutes=delay) or matured != expected_maturity:
            raise ContractError("session maturity must bind target-close delay and source receipt")
        if provenance.get("source_receipt_schema") != PRICE_RECEIPT_SCHEMA:
            raise ContractError("session source receipt schema is outside v1")
        price_source = provenance.get("price_source")
        if type(price_source) is not str or not price_source.strip():
            raise ContractError("complete session outcomes require price_source")
        digest = provenance.get("source_file_sha256")
        if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ContractError("complete session outcomes require a source digest")
        source_rows = provenance.get("source_file_row_count")
        if type(source_rows) is not int or source_rows < evidence["observation_count"]:
            raise ContractError("session source row count cannot be smaller than evidence")
        source_first = _as_utc(
            provenance.get("source_file_first_time"), "provenance.source_file_first_time",
        )
        source_last = _as_utc(
            provenance.get("source_file_last_time"), "provenance.source_file_last_time",
        )
        if (
            provenance.get("source_file_first_time") != _iso_utc(source_first)
            or provenance.get("source_file_last_time") != _iso_utc(source_last)
        ):
            raise ContractError("session source receipt endpoints must be canonical UTC")
        if source_first > entry or source_last < final_bar_time or source_first > source_last:
            raise ContractError("session source receipt does not cover retained evidence")
        if provenance.get("adjusted") is not True or provenance.get("price_basis") != PRICE_BASIS:
            raise ContractError("session outcome price basis is outside v1")
        if provenance.get("timestamp_basis") != TIMESTAMP_BASIS:
            raise ContractError("session outcome timestamp basis is outside v1")
        price_vintage = _as_utc(provenance.get("price_vintage"), "provenance.price_vintage")
        if provenance.get("price_vintage") != _iso_utc(price_vintage):
            raise ContractError("session price_vintage must be canonical UTC")
        if price_vintage != final_bar_time:
            raise ContractError("session price_vintage must equal the final consumed bar start")
    else:
        if measurement["kind"] != "unavailable" or measurement["target_aligned"]:
            raise ContractError("incomplete session outcomes require an unavailable measurement")
        if reasons != ["outcome_incomplete"] or any(value is not None for value in window.values()):
            raise ContractError("incomplete session outcomes require the canonical null window")
        if underlying.get("status") != "unavailable" or any(
            value is not None for key, value in underlying.items() if key != "status"
        ):
            raise ContractError("incomplete session outcomes require a null underlying block")
        if any(value is not None for value in provenance.values()):
            raise ContractError("incomplete session outcomes cannot invent price provenance")
        if matured != max(target, anchor) or anchor < target:
            raise ContractError("terminal session outcome must be clock-reproducible")

    if option.get("status") != "unavailable":
        raise ContractError("session option outcomes must remain unavailable")
    if option.get("reason") != "no_executable_nbbo_quote_path":
        raise ContractError("session option outcome requires the canonical unavailable reason")
    if option.get("quote_basis") is not None or any(
        option.get(key) is not None for key in ("ret", "mfe", "mae")
    ):
        raise ContractError("session option outcomes cannot carry quote or return fields")


def validate_session_outcome_against_episode(
    outcome: dict[str, Any], episode: dict[str, Any],
) -> None:
    validate_episode(episode)
    validate_session_outcome(outcome)
    if outcome["episode_id"] != episode["episode_id"]:
        raise ContractError("session outcome references a different episode")
    available = _as_utc(episode["available_at"], "episode.available_at")
    if _as_utc(outcome["horizon_anchor"], "horizon_anchor") != available:
        raise ContractError("session outcome horizon_anchor must equal episode.available_at")
    session = _as_date(episode["session_date"], "episode.session_date")
    offset, target_session, target = _session_target(session, outcome["horizon"])
    if outcome["horizon_sessions"] != offset:
        raise ContractError("session outcome offset disagrees with its episode join")
    if outcome["target_session"] != target_session.isoformat():
        raise ContractError("session outcome target_session disagrees with the NYSE horizon")
    if _as_utc(outcome["target_time"], "target_time") != target:
        raise ContractError("session outcome target_time disagrees with the NYSE close")
    if outcome["status"] == "complete":
        entry = _as_utc(outcome["underlying"]["entry_time"], "underlying.entry_time")
        _, episode_close_et = session_window_et(session)
        episode_close = episode_close_et.astimezone(timezone.utc)
        if available < episode_close:
            expected_entry_session = session
        else:
            expected_entry_session = nyse_calendar.session_n_forward(session, 1)
        if expected_entry_session is None or entry.astimezone(ET).date() != expected_entry_session:
            raise ContractError("session outcome entry is not on the first admissible session")
        entry_open = session_window_et(expected_entry_session)[0].astimezone(timezone.utc)
        max_entry_gap = outcome["underlying"]["bar_seconds"] * 1.10
        if (entry - max(available, entry_open)).total_seconds() > max_entry_gap:
            raise ContractError("session outcome entry exceeds the admitted cadence gap")
        expected_source_file = f"{episode['ticker']}.parquet"
        if Path(outcome["provenance"]["price_source"]).name != expected_source_file:
            raise ContractError("session outcome price source must match the episode ticker")
    elif outcome["horizon"] != "eod" or available < target:
        raise ContractError("terminal session outcome is not reproducible from episode clocks")


def episode_from_live_event(
    event: dict[str, Any],
    *,
    source_snapshot_asof: str,
    source_artifact: str = "live_flow/events/{session_date}.jsonl",
) -> dict[str, Any]:
    """Freeze one ``live_flow.feed/v1`` event into a zero-authority watch episode.

    No fallback from the cumulative envelope's ``asof`` to first availability is
    allowed.  Old events without event-level ``observed_at`` / ``available_at``
    are rejected instead of being retrospectively dated.
    """
    source_event_id = event.get("id")
    if (
        type(source_event_id) is not str
        or not source_event_id
        or source_event_id != source_event_id.strip()
    ):
        raise ContractError("live event id must be a normalized string")
    event_dt = _as_utc(event.get("ts"), "event.ts")
    event_time = _iso_utc(event_dt)
    observed_at = _iso_utc(_as_utc(event.get("observed_at"), "event.observed_at"))
    decision_at = _iso_utc(_as_utc(event.get("decision_at"), "event.decision_at"))
    available_at = _iso_utc(_as_utc(event.get("available_at"), "event.available_at"))
    published_at = (
        _iso_utc(_as_utc(event.get("published_at"), "event.published_at"))
        if event.get("published_at") is not None else None
    )
    event_snapshot_dt = _as_utc(
        event.get("source_snapshot_asof"), "event.source_snapshot_asof",
    )
    envelope_snapshot_dt = _as_utc(source_snapshot_asof, "source_snapshot_asof")
    if envelope_snapshot_dt != event_snapshot_dt:
        raise ContractError(
            "v1 source snapshot envelope must equal the durable event snapshot"
        )
    session = event_dt.astimezone(ET).date().isoformat()
    ticker = event.get("root")
    if type(ticker) is not str or not ticker or ticker != ticker.strip().upper():
        raise ContractError("event.root must be a normalized uppercase string")
    right = event.get("right")
    if type(right) is not str or right not in ("C", "P"):
        raise ContractError("event.right must be exactly C or P")
    expiration = _exact_iso_date(event.get("exp"), "event.exp")
    strike = _exact_finite_number(event.get("strike"), "event.strike", positive=True)
    premium = _exact_finite_number(event.get("premium"), "event.premium", positive=True)
    size = event.get("size")
    if type(size) is not int or size <= 0:
        raise ContractError("event.size must be an exact positive integer")
    contracts = size
    dte = event.get("dte")
    if dte is not None and (type(dte) is not int or dte < 0):
        raise ContractError("event.dte must be null or an exact non-negative integer")
    moneyness_bucket = event.get("mny_bucket")
    if moneyness_bucket not in ("itm", "atm", "near_otm", "far_otm", "unknown"):
        raise ContractError("event.mny_bucket is outside the live-flow vocabulary")
    repeated = event.get("repeated")
    swept = event.get("swept")
    if type(repeated) is not bool or type(swept) is not bool:
        raise ContractError("event.repeated and event.swept must be exact booleans")
    avg_price_raw = event.get("avg_price")
    avg_price = (
        None if avg_price_raw is None
        else _exact_finite_number(avg_price_raw, "event.avg_price", positive=True)
    )
    oi_vintage_raw = event.get("oi_vintage")
    oi_vintage = (
        None if oi_vintage_raw is None
        else _exact_iso_date(oi_vintage_raw, "event.oi_vintage")
    )
    vol_gt_oi = event.get("vol_gt_oi")
    if vol_gt_oi is not None and type(vol_gt_oi) is not bool:
        raise ContractError("event.vol_gt_oi must be true, false, or null")
    signing_source = event.get("signing_source")
    if signing_source != "tape":
        raise ContractError("event.signing_source must be the observed tape provenance")
    baseline_source = event.get("baseline_source")
    if baseline_source != "floor":
        raise ContractError(
            "event.baseline_source must be floor until a governed per-contract baseline exists"
        )
    if "premium_z" not in event or event.get("premium_z") is not None:
        raise ContractError(
            "event.premium_z must be explicit null for the floor-only contract gate"
        )
    if event.get("selection_rule") != "premium_floor/v1":
        raise ContractError("event.selection_rule must be premium_floor/v1")
    selection_floor = _exact_finite_number(
        event.get("selection_floor_usd"), "event.selection_floor_usd",
    )
    if selection_floor < 0 or premium < selection_floor:
        raise ContractError("event premium must meet its non-negative selection floor")
    selection_root_class = event.get("selection_root_class")
    if selection_root_class not in ("etf_anchor", "single_name"):
        raise ContractError("event.selection_root_class is outside the frozen vocabulary")

    episode = {
        "schema": EPISODE_SCHEMA,
        "episode_id": _episode_id("live_flow.notable_contract", source_event_id),
        "source": "live_flow.notable_contract",
        "source_event_id": source_event_id,
        "event_time": event_time,
        "observed_at": observed_at,
        "decision_at": decision_at,
        "available_at": available_at,
        "published_at": published_at,
        "anchor_strategy": event.get("anchor_strategy"),
        "session_date": session,
        "ticker": ticker,
        "contract": {
            "right": right,
            "expiration": expiration,
            "strike": strike,
        },
        "decision": {
            "disposition": "watch",
            "reason": "notable_flow_event",
            "underlying_direction": "none",
            "option_action": "none",
            "authority": dict(FALSE_AUTHORITY),
        },
        "feature_snapshot": {
            "premium_usd": premium,
            "selection_rule": "premium_floor/v1",
            "selection_floor_usd": selection_floor,
            "selection_root_class": selection_root_class,
            "contracts": contracts,
            "avg_option_trade_price": avg_price,
            "flow_side": event.get("side"),
            "dte": dte,
            "moneyness_bucket": moneyness_bucket,
            "vol_gt_prior_oi": vol_gt_oi,
            "repeated": repeated,
            "swept": swept,
        },
        "provenance": {
            "source_schema": "live_flow.event_stage/v1",
            "source_artifact": source_artifact.format(session_date=session),
            "source_snapshot_asof": _iso_utc(event_snapshot_dt),
            "feature_cutoff": available_at,
            "signing_source": signing_source,
            "oi_vintage": oi_vintage,
            "oi_vintage_rule": "latest_available_chain_before_session",
        },
        "quality": {
            "availability_exact": True,
            "trade_direction_reliability": "soft",
            "option_quote_outcome_eligible": False,
            "source_baseline": baseline_source,
        },
    }
    validate_episode(episode)
    return episode


def normalize_price_bars(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Return a UTC-indexed OHLC frame, preserving only finite usable bars."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    df = frame.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        ts_col = next((c for c in ("timestamp", "ts", "time", "datetime") if c in df.columns), None)
        if ts_col is None:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df.index = pd.to_datetime(df.pop(ts_col), errors="coerce", utc=True)
    else:
        df.index = pd.to_datetime(df.index, errors="coerce", utc=True)
    rename: dict[str, str] = {}
    for canonical, aliases in {
        "open": ("open", "o"), "high": ("high", "h"),
        "low": ("low", "l"), "close": ("close", "c"),
    }.items():
        src = next((a for a in aliases if a in df.columns), None)
        if src:
            rename[src] = canonical
    df = df.rename(columns=rename)
    if any(c not in df.columns for c in ("open", "high", "low", "close")):
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    out = df[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.dropna(how="all")


def _terminal_incomplete(episode: dict[str, Any], *, reason: str,
                         computed_at: datetime, target_time: datetime) -> dict[str, Any]:
    row = {
        "schema": OUTCOME_SCHEMA,
        "outcome_id": _outcome_id(episode["episode_id"]),
        "episode_id": episode["episode_id"],
        "horizon_minutes": HORIZON_MINUTES,
        "status": "incomplete",
        "reason": reason,
        "horizon_anchor": episode["available_at"],
        "target_time": _iso_utc(target_time),
        "computed_at": _iso_utc(computed_at),
        "matured_at": _iso_utc(target_time),
        "measurement": {
            "version": MEASUREMENT_VERSION,
            "kind": "unavailable",
            "target_aligned": False,
            "training_eligible": False,
            "training_ineligibility_reasons": ["outcome_incomplete"],
            "window": {"start": None, "end": None},
        },
        "underlying": {
            "status": "unavailable", "entry_time": None, "exit_time": None,
            "entry_price": None, "exit_price": None, "ret": None,
            "mfe": None, "mae": None, "entry_delay_minutes": None,
            "exit_delay_minutes": None,
            "bar_seconds": None, "path_basis": None, "evidence": None,
        },
        "option": {
            "status": "unavailable", "reason": "no_executable_nbbo_quote_path",
            "quote_basis": None, "ret": None, "mfe": None, "mae": None,
        },
        "provenance": {
            "price_source": None,
            "price_vintage": None,
            "price_delay_minutes": None,
            "source_receipt_schema": None,
            "source_available_at": None,
            "source_file_sha256": None,
            "source_file_row_count": None,
            "source_file_first_time": None,
            "source_file_last_time": None,
            "adjusted": None,
            "price_basis": None,
            "timestamp_basis": None,
        },
        "label_authority": "research_only",
    }
    validate_outcome(row)
    return row


def _terminal_session_incomplete(
    episode: dict[str, Any],
    *,
    horizon: str,
    horizon_sessions: int,
    target_session: date,
    target_time: datetime,
    computed_at: datetime,
) -> dict[str, Any]:
    row = {
        "schema": SESSION_OUTCOME_SCHEMA,
        "outcome_id": _session_outcome_id(episode["episode_id"], horizon),
        "episode_id": episode["episode_id"],
        "horizon": horizon,
        "horizon_sessions": horizon_sessions,
        "status": "incomplete",
        "reason": "decision_after_target_close",
        "horizon_anchor": episode["available_at"],
        "target_session": target_session.isoformat(),
        "target_time": _iso_utc(target_time),
        "computed_at": _iso_utc(computed_at),
        "matured_at": _iso_utc(max(
            target_time,
            _as_utc(episode["available_at"], "episode.available_at"),
        )),
        "measurement": {
            "version": SESSION_MEASUREMENT_VERSION,
            "calendar_basis": SESSION_CALENDAR_BASIS,
            "kind": "unavailable",
            "target_aligned": False,
            "training_eligible": False,
            "training_ineligibility_reasons": ["outcome_incomplete"],
            "window": {"start": None, "end": None},
        },
        "underlying": {
            "status": "unavailable", "entry_time": None, "exit_time": None,
            "entry_price": None, "exit_price": None, "ret": None,
            "mfe": None, "mae": None, "entry_delay_minutes": None,
            "exit_delay_minutes": None, "bar_seconds": None,
            "path_basis": None, "evidence": None,
        },
        "option": {
            "status": "unavailable", "reason": "no_executable_nbbo_quote_path",
            "quote_basis": None, "ret": None, "mfe": None, "mae": None,
        },
        "provenance": {
            "price_source": None, "price_vintage": None,
            "price_delay_minutes": None, "source_receipt_schema": None,
            "source_available_at": None, "source_file_sha256": None,
            "source_file_row_count": None, "source_file_first_time": None,
            "source_file_last_time": None, "adjusted": None,
            "price_basis": None, "timestamp_basis": None,
        },
        "label_authority": "research_only",
    }
    validate_session_outcome(row)
    return row


def derive_session_outcome(
    episode: dict[str, Any],
    horizon: str,
    bars: pd.DataFrame | None,
    *,
    computed_at: datetime,
    price_source: str,
    bar_seconds: int | None = None,
    price_delay_minutes: int | None = None,
    price_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive one immutable close outcome without changing the H+60 v1 seam."""
    validate_episode(episode)
    if not isinstance(computed_at, datetime) or computed_at.tzinfo is None:
        raise ContractError("computed_at must be a timezone-aware datetime")
    now = computed_at.astimezone(timezone.utc)
    episode_session = _as_date(episode["session_date"], "session_date")
    horizon_sessions, target_session, target_time = _session_target(episode_session, horizon)
    available = _as_utc(episode["available_at"], "available_at")
    if now < max(target_time, available):
        return {
            "status": "pending", "reason": "horizon_not_matured",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    if available >= target_time:
        return _terminal_session_incomplete(
            episode,
            horizon=horizon,
            horizon_sessions=horizon_sessions,
            target_session=target_session,
            target_time=target_time,
            computed_at=now,
        )
    if bars is None and price_receipt is None:
        return {
            "status": "pending", "reason": "missing_price_receipt",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    if price_delay_minutes is not None and (
        type(price_delay_minutes) is not int or price_delay_minutes < 0
    ):
        raise ContractError("price_delay_minutes must be an exact non-negative integer")
    if bar_seconds is not None and type(bar_seconds) is not int:
        raise ContractError("bar_seconds must be an exact integer when declared")
    if bar_seconds not in (60, 300, 900, 1800, 3600):
        return {
            "status": "pending", "reason": "unknown_bar_cadence",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    frame = normalize_price_bars(bars)
    expected_sessions = nyse_calendar.sessions_between(episode_session, target_session)
    if len(expected_sessions) != horizon_sessions + 1:
        raise ContractError("session horizon mapping disagrees with the NYSE calendar")

    measurement_sessions: list[date] = []
    for session in expected_sessions:
        close_utc = session_window_et(session)[1].astimezone(timezone.utc)
        if session == episode_session and available >= close_utc:
            continue
        measurement_sessions.append(session)
    if not measurement_sessions or measurement_sessions[-1] != target_session:
        raise ContractError("session measurement window has no admissible target session")

    selected_parts: list[pd.DataFrame] = []
    entry_time: datetime | None = None
    final_bar_time: datetime | None = None
    max_open_gap = bar_seconds * 1.10
    for session_index, session in enumerate(measurement_sessions):
        open_et, close_et = session_window_et(session)
        open_utc = open_et.astimezone(timezone.utc)
        close_utc = close_et.astimezone(timezone.utc)
        session_frame = frame[
            (frame.index >= pd.Timestamp(open_utc)) & (frame.index < pd.Timestamp(close_utc))
        ]
        if session_frame.empty:
            return {
                "status": "pending", "reason": "missing_session_bars",
                "episode_id": episode["episode_id"], "horizon": horizon,
            }
        admitted_start = max(available, open_utc) if session_index == 0 else open_utc
        start_candidates = session_frame[session_frame.index >= pd.Timestamp(admitted_start)]
        if start_candidates.empty:
            return {
                "status": "pending", "reason": "missing_entry_bar",
                "episode_id": episode["episode_id"], "horizon": horizon,
            }
        first_time = start_candidates.index[0].to_pydatetime().astimezone(timezone.utc)
        if (first_time - admitted_start).total_seconds() > max_open_gap:
            return {
                "status": "pending", "reason": "entry_bar_gap",
                "episode_id": episode["episode_id"], "horizon": horizon,
            }
        covering = session_frame[
            (session_frame.index < pd.Timestamp(close_utc))
            & (session_frame.index + pd.Timedelta(seconds=bar_seconds) >= pd.Timestamp(close_utc))
        ]
        if covering.empty:
            return {
                "status": "pending", "reason": "missing_session_close_bar",
                "episode_id": episode["episode_id"], "horizon": horizon,
            }
        close_bar_time = covering.index[-1].to_pydatetime().astimezone(timezone.utc)
        if close_bar_time < first_time:
            return {
                "status": "pending", "reason": "late_entry_after_close_bar",
                "episode_id": episode["episode_id"], "horizon": horizon,
            }
        part = session_frame[
            (session_frame.index >= pd.Timestamp(first_time))
            & (session_frame.index <= pd.Timestamp(close_bar_time))
        ]
        expected_index = pd.date_range(
            start=pd.Timestamp(first_time),
            end=pd.Timestamp(close_bar_time),
            freq=pd.Timedelta(seconds=bar_seconds),
        )
        if not part.index.equals(expected_index):
            return {
                "status": "pending", "reason": "measurement_path_gap",
                "episode_id": episode["episode_id"], "horizon": horizon,
            }
        selected_parts.append(part)
        if entry_time is None:
            entry_time = first_time
        final_bar_time = close_bar_time

    assert entry_time is not None and final_bar_time is not None
    path = pd.concat(selected_parts)
    try:
        _validate_runtime_session_evidence_grid(
            [stamp.to_pydatetime().astimezone(timezone.utc) for stamp in path.index],
            entry=entry_time,
            target_session=target_session,
            target_time=target_time,
            bar_seconds=bar_seconds,
        )
    except ContractError:
        return {
            "status": "pending", "reason": "measurement_path_gap",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    if price_delay_minutes is None:
        return {
            "status": "pending", "reason": "unknown_price_delay",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    if not isinstance(price_source, str) or not price_source.strip():
        raise ContractError("price_source must be a non-empty provenance string")
    if price_receipt is None:
        return {
            "status": "pending", "reason": "missing_price_receipt",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    try:
        receipt = _validated_session_price_receipt(
            price_receipt,
            ticker=episode["ticker"],
            price_source=price_source,
            bar_seconds=bar_seconds,
            price_delay_minutes=price_delay_minutes,
            entry=entry_time,
            final_bar_time=final_bar_time,
            target_time=target_time,
        )
    except ContractError:
        return {
            "status": "pending", "reason": "invalid_price_receipt",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    source_available = _as_utc(
        receipt["source_available_at"], "price_receipt.source_available_at",
    )
    matured_at = max(
        target_time + timedelta(minutes=price_delay_minutes), source_available,
    )
    if now < matured_at:
        return {
            "status": "pending", "reason": "measurement_not_available",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }

    numeric_path = path[["open", "high", "low", "close"]]
    finite_path = numeric_path.apply(
        lambda column: column.map(lambda value: math.isfinite(float(value)))
    )
    structurally_valid = (
        finite_path.all(axis=1)
        & (numeric_path > 0).all(axis=1)
        & (numeric_path["high"] >= numeric_path[["open", "close", "low"]].max(axis=1))
        & (numeric_path["low"] <= numeric_path[["open", "close", "high"]].min(axis=1))
    )
    if not bool(structurally_valid.all()):
        return {
            "status": "pending", "reason": "invalid_ohlc_bar",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    exit_close = _optional_float(path.iloc[-1].get("close"))
    if exit_close is None or exit_close <= 0:
        return {
            "status": "pending", "reason": "missing_price_fields",
            "episode_id": episode["episode_id"], "horizon": horizon,
        }
    evidence = _build_session_price_evidence(
        path,
        target_time=target_time,
        final_bar_time=final_bar_time,
        exit_close=exit_close,
        bar_seconds=bar_seconds,
    )
    ev_entry, ev_exit, ev_ret, ev_mfe, ev_mae = _validate_session_price_evidence(
        evidence,
        entry=entry_time,
        target_time=target_time,
        final_bar_time=final_bar_time,
        bar_seconds=bar_seconds,
    )
    row = {
        "schema": SESSION_OUTCOME_SCHEMA,
        "outcome_id": _session_outcome_id(episode["episode_id"], horizon),
        "episode_id": episode["episode_id"],
        "horizon": horizon,
        "horizon_sessions": horizon_sessions,
        "status": "complete",
        "reason": None,
        "horizon_anchor": episode["available_at"],
        "target_session": target_session.isoformat(),
        "target_time": _iso_utc(target_time),
        "computed_at": _iso_utc(now),
        "matured_at": _iso_utc(matured_at),
        "measurement": {
            "version": SESSION_MEASUREMENT_VERSION,
            "calendar_basis": SESSION_CALENDAR_BASIS,
            "kind": "session_close_bar_proxy",
            "target_aligned": entry_time == available,
            "training_eligible": False,
            "training_ineligibility_reasons": ["session_outcome_shadow_only"],
            "window": {"start": _iso_utc(entry_time), "end": _iso_utc(target_time)},
        },
        "underlying": {
            "status": "complete",
            "entry_time": _iso_utc(entry_time),
            "exit_time": _iso_utc(target_time),
            "entry_price": ev_entry,
            "exit_price": ev_exit,
            "ret": ev_ret,
            "mfe": ev_mfe,
            "mae": ev_mae,
            "entry_delay_minutes": round((entry_time - available).total_seconds() / 60.0, 3),
            "exit_delay_minutes": 0,
            "bar_seconds": bar_seconds,
            "path_basis": (
                "first_admissible_bar_open_to_declared_session_close_with_observed_rth_bar_high_low_proxies"
            ),
            "evidence": evidence,
        },
        "option": {
            "status": "unavailable", "reason": "no_executable_nbbo_quote_path",
            "quote_basis": None, "ret": None, "mfe": None, "mae": None,
        },
        "provenance": {
            "price_source": price_source,
            "price_vintage": _iso_utc(final_bar_time),
            "price_delay_minutes": price_delay_minutes,
            "source_receipt_schema": receipt["schema"],
            "source_available_at": receipt["source_available_at"],
            "source_file_sha256": receipt["source_file_sha256"],
            "source_file_row_count": receipt["row_count"],
            "source_file_first_time": receipt["first_time"],
            "source_file_last_time": receipt["last_time"],
            "adjusted": receipt["adjusted"],
            "price_basis": receipt["price_basis"],
            "timestamp_basis": receipt["timestamp_basis"],
        },
        "label_authority": "research_only",
    }
    validate_session_outcome(row)
    return row


def _training_quality(
    *,
    available: datetime,
    target: datetime,
    entry: datetime,
    exit_: datetime,
    bar_seconds: int,
    price_delay_minutes: int | None,
) -> tuple[bool, bool, list[str]]:
    target_aligned = entry == available and exit_ == target
    reasons: list[str] = []
    if not target_aligned:
        reasons.append("measurement_window_not_target_aligned")
    if int(bar_seconds) > TRAINING_MAX_BAR_SECONDS:
        reasons.append("bar_resolution_exceeds_60s")
    if price_delay_minutes is None:
        reasons.append("price_delay_unknown")
    elif int(price_delay_minutes) > TRAINING_MAX_PRICE_DELAY_MINUTES:
        reasons.append("price_delay_exceeds_1m")
    eligible = not reasons
    return target_aligned, eligible, reasons


def _validated_price_receipt(
    receipt: object,
    *,
    ticker: str,
    price_source: str,
    bar_seconds: int,
    price_delay_minutes: int,
    entry: datetime,
    exit_: datetime,
) -> dict[str, Any]:
    required = {
        "schema", "ticker", "source_file", "source_file_sha256",
        "source_available_at", "bar_seconds", "vendor_delay_minutes",
        "adjusted", "price_basis", "timestamp_basis", "row_count",
        "first_time", "last_time",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ContractError("price receipt has an invalid shape")
    if receipt.get("schema") != PRICE_RECEIPT_SCHEMA:
        raise ContractError("price receipt schema is outside v1")
    if receipt.get("ticker") != ticker:
        raise ContractError("price receipt ticker disagrees with the episode")
    source_file = receipt.get("source_file")
    if (
        type(source_file) is not str
        or not source_file
        or source_file != source_file.strip()
        or Path(price_source).name != source_file
    ):
        raise ContractError("price receipt source file disagrees with price_source")
    digest = receipt.get("source_file_sha256")
    if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ContractError("price receipt source digest is invalid")
    if type(receipt.get("bar_seconds")) is not int or receipt["bar_seconds"] != bar_seconds:
        raise ContractError("price receipt cadence disagrees with the measurement")
    if (
        type(receipt.get("vendor_delay_minutes")) is not int
        or receipt["vendor_delay_minutes"] != price_delay_minutes
    ):
        raise ContractError("price receipt delay disagrees with the measurement")
    if receipt.get("adjusted") is not True:
        raise ContractError("price receipt must attest adjusted aggregates")
    if receipt.get("price_basis") != PRICE_BASIS:
        raise ContractError("price receipt basis is outside v1")
    if receipt.get("timestamp_basis") != TIMESTAMP_BASIS:
        raise ContractError("price receipt timestamp basis is outside v1")
    if type(receipt.get("row_count")) is not int or receipt["row_count"] <= 0:
        raise ContractError("price receipt row_count must be a positive exact integer")
    available = _as_utc(receipt.get("source_available_at"), "price_receipt.source_available_at")
    first = _as_utc(receipt.get("first_time"), "price_receipt.first_time")
    last = _as_utc(receipt.get("last_time"), "price_receipt.last_time")
    for field, parsed in (
        ("source_available_at", available), ("first_time", first), ("last_time", last),
    ):
        if receipt[field] != _iso_utc(parsed):
            raise ContractError(f"price receipt {field} must be canonical UTC")
    if first > entry or last < exit_ or first > last:
        raise ContractError("price receipt source window does not cover the measurement")
    if available < exit_ + timedelta(minutes=price_delay_minutes):
        raise ContractError("price receipt availability predates the consumed delayed exit")
    return receipt


def _validated_session_price_receipt(
    receipt: object,
    *,
    ticker: str,
    price_source: str,
    bar_seconds: int,
    price_delay_minutes: int,
    entry: datetime,
    final_bar_time: datetime,
    target_time: datetime,
) -> dict[str, Any]:
    """Validate the same immutable source receipt for a close-based measurement."""
    required = {
        "schema", "ticker", "source_file", "source_file_sha256",
        "source_available_at", "bar_seconds", "vendor_delay_minutes",
        "adjusted", "price_basis", "timestamp_basis", "row_count",
        "first_time", "last_time",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ContractError("session price receipt has an invalid shape")
    if receipt.get("schema") != PRICE_RECEIPT_SCHEMA or receipt.get("ticker") != ticker:
        raise ContractError("session price receipt identity is outside v1")
    source_file = receipt.get("source_file")
    if (
        type(source_file) is not str
        or not source_file
        or source_file != source_file.strip()
        or Path(price_source).name != source_file
    ):
        raise ContractError("session price receipt source file disagrees with price_source")
    digest = receipt.get("source_file_sha256")
    if type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ContractError("session price receipt source digest is invalid")
    if type(receipt.get("bar_seconds")) is not int or receipt["bar_seconds"] != bar_seconds:
        raise ContractError("session price receipt cadence disagrees with the measurement")
    if (
        type(receipt.get("vendor_delay_minutes")) is not int
        or receipt["vendor_delay_minutes"] != price_delay_minutes
    ):
        raise ContractError("session price receipt delay disagrees with the measurement")
    if receipt.get("adjusted") is not True or receipt.get("price_basis") != PRICE_BASIS:
        raise ContractError("session price receipt basis is outside v1")
    if receipt.get("timestamp_basis") != TIMESTAMP_BASIS:
        raise ContractError("session price receipt timestamp basis is outside v1")
    if type(receipt.get("row_count")) is not int or receipt["row_count"] <= 0:
        raise ContractError("session price receipt row_count must be a positive exact integer")
    available = _as_utc(receipt.get("source_available_at"), "price_receipt.source_available_at")
    first = _as_utc(receipt.get("first_time"), "price_receipt.first_time")
    last = _as_utc(receipt.get("last_time"), "price_receipt.last_time")
    for field, parsed in (
        ("source_available_at", available), ("first_time", first), ("last_time", last),
    ):
        if receipt[field] != _iso_utc(parsed):
            raise ContractError(f"session price receipt {field} must be canonical UTC")
    if first > entry or last < final_bar_time or first > last:
        raise ContractError("session price receipt source window does not cover the measurement")
    if available < target_time + timedelta(minutes=price_delay_minutes):
        raise ContractError("session price receipt availability predates target close plus delay")
    return receipt


def derive_h60_outcome(
    episode: dict[str, Any],
    bars: pd.DataFrame | None,
    *,
    computed_at: datetime,
    price_source: str,
    bar_seconds: int | None = None,
    price_delay_minutes: int | None = None,
    price_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a truthful same-session H+60 label or a non-persisted pending result.

    Desired H+60 is anchored to ``available_at``. Entry is the first bar open at
    or after that anchor; exit is the first bar open at or after H+60. Return,
    MFE and MAE describe the actual aligned-bar entry-to-exit window, which may
    end after the desired target. Measurement version/kind, alignment, bar size
    and source delay make coarse or delayed proxies training-ineligible.
    """
    validate_episode(episode)
    if not isinstance(computed_at, datetime) or computed_at.tzinfo is None:
        raise ContractError("computed_at must be a timezone-aware datetime")
    now = computed_at.astimezone(timezone.utc)
    session = _as_date(episode["session_date"], "session_date")
    open_et, close_et = session_window_et(session)
    open_utc, close_utc = open_et.astimezone(timezone.utc), close_et.astimezone(timezone.utc)
    available = _as_utc(episode["available_at"], "available_at")
    target = available + timedelta(minutes=HORIZON_MINUTES)

    # Even an impossible same-session horizon is not yet an accrued fact before
    # its desired H+60 clock. Early jobs must remain retryable, not write the future.
    if now < target:
        return {"status": "pending", "reason": "horizon_not_matured", "episode_id": episode["episode_id"]}
    if available >= close_utc:
        return _terminal_incomplete(
            episode, reason="decision_after_session_close",
            computed_at=now, target_time=target,
        )
    if target >= close_utc:
        return _terminal_incomplete(
            episode, reason="horizon_crosses_session_close",
            computed_at=now, target_time=target,
        )
    # Session-terminal facts consume no price observations. Only a potentially
    # measurable path depends on vendor cadence and delay metadata.
    if bars is None and price_receipt is None:
        return {
            "status": "pending",
            "reason": "missing_price_receipt",
            "episode_id": episode["episode_id"],
        }
    if price_delay_minutes is not None and (
        type(price_delay_minutes) is not int or price_delay_minutes < 0
    ):
        raise ContractError("price_delay_minutes must be an exact non-negative integer")
    if bar_seconds is not None and type(bar_seconds) is not int:
        raise ContractError("bar_seconds must be an exact integer when declared")
    if bar_seconds not in (60, 300, 900, 1800, 3600):
        return {
            "status": "pending",
            "reason": "unknown_bar_cadence",
            "episode_id": episode["episode_id"],
        }

    df = normalize_price_bars(bars)
    session_df = df[(df.index >= pd.Timestamp(open_utc)) & (df.index < pd.Timestamp(close_utc))]
    entry_candidates = session_df[session_df.index >= pd.Timestamp(max(available, open_utc))]
    if entry_candidates.empty:
        return {"status": "pending", "reason": "missing_entry_bar", "episode_id": episode["episode_id"]}
    entry_ts = entry_candidates.index[0].to_pydatetime().astimezone(timezone.utc)
    max_delay = max(300, int(bar_seconds * 1.10))
    if (entry_ts - max(available, open_utc)).total_seconds() > max_delay:
        return {"status": "pending", "reason": "entry_bar_gap", "episode_id": episode["episode_id"]}

    # The outcome is measured on the declared bar grid, not on an arbitrary
    # later timestamp that happens to be present.  Work out the first grid
    # boundary at/after desired H+60 from the admitted entry. A coarse source
    # whose aligned exit reaches the close stays pending because v1 terminal
    # rows do not retain enough causal cadence/entry provenance to freeze that
    # source-dependent conclusion permanently.
    cadence = timedelta(seconds=int(bar_seconds))
    seconds_after_entry = max(0.0, (target - entry_ts).total_seconds())
    cadence_steps = max(1, math.ceil(seconds_after_entry / int(bar_seconds)))
    expected_exit_ts = entry_ts + cadence_steps * cadence
    if expected_exit_ts >= close_utc:
        # A later/finer source may still make this horizon measurable.  V1's
        # terminal-incomplete row intentionally carries no cadence or admitted
        # entry provenance, so persisting this source-dependent condition would
        # be impossible to reproduce from the episode/outcome join. Keep it
        # pending until a future contract can freeze that causal measurement.
        return {
            "status": "pending",
            "reason": "aligned_exit_crosses_session_close",
            "episode_id": episode["episode_id"],
        }

    exit_candidates = session_df[
        session_df.index == pd.Timestamp(expected_exit_ts)
    ]
    if exit_candidates.empty:
        return {"status": "pending", "reason": "missing_exit_bar", "episode_id": episode["episode_id"]}
    exit_ts = exit_candidates.index[0].to_pydatetime().astimezone(timezone.utc)
    if price_delay_minutes is None:
        return {
            "status": "pending",
            "reason": "unknown_price_delay",
            "episode_id": episode["episode_id"],
        }
    if not isinstance(price_source, str) or not price_source.strip():
        raise ContractError("price_source must be a non-empty provenance string")
    declared_delay = int(price_delay_minutes)
    if price_receipt is None:
        return {
            "status": "pending",
            "reason": "missing_price_receipt",
            "episode_id": episode["episode_id"],
        }
    try:
        receipt = _validated_price_receipt(
            price_receipt,
            ticker=episode["ticker"],
            price_source=price_source,
            bar_seconds=int(bar_seconds),
            price_delay_minutes=declared_delay,
            entry=entry_ts,
            exit_=exit_ts,
        )
    except ContractError:
        return {
            "status": "pending",
            "reason": "invalid_price_receipt",
            "episode_id": episode["episode_id"],
        }
    source_available_at = _as_utc(
        receipt["source_available_at"], "price_receipt.source_available_at",
    )
    measurement_complete_at = max(
        exit_ts + timedelta(minutes=declared_delay), source_available_at,
    )
    if now < measurement_complete_at:
        return {
            "status": "pending",
            "reason": "measurement_not_available",
            "episode_id": episode["episode_id"],
        }

    entry_price = _optional_float(entry_candidates.iloc[0].get("open"))
    exit_price = _optional_float(exit_candidates.iloc[0].get("open"))
    # Excursions describe the actual aligned-bar measurement window, not the
    # desired event-time target. This may extend beyond target_time and is labeled.
    path = session_df[(session_df.index >= pd.Timestamp(entry_ts)) & (session_df.index < pd.Timestamp(exit_ts))]
    if entry_price is None or entry_price <= 0 or exit_price is None or exit_price <= 0 or path.empty:
        return {"status": "pending", "reason": "missing_price_fields", "episode_id": episode["episode_id"]}
    expected_path_index = pd.date_range(
        start=pd.Timestamp(entry_ts),
        end=pd.Timestamp(exit_ts),
        freq=pd.Timedelta(seconds=int(bar_seconds)),
        inclusive="left",
    )
    if not path.index.equals(expected_path_index):
        return {
            "status": "pending",
            "reason": "measurement_path_gap",
            "episode_id": episode["episode_id"],
        }
    # Validate only facts consumed by this label. A corrupt bar later in the
    # session must not retroactively change an already matured H+60 result. Only
    # the selected exit OPEN is consumed; its high/low/close form after the exit
    # clock and therefore cannot influence status or arithmetic.
    numeric_path = path[["open", "high", "low", "close"]]
    finite_path = numeric_path.apply(
        lambda col: col.map(lambda value: math.isfinite(float(value)))
    )
    structurally_valid = (
        finite_path.all(axis=1)
        & (numeric_path > 0).all(axis=1)
        & (numeric_path["high"] >= numeric_path[["open", "close", "low"]].max(axis=1))
        & (numeric_path["low"] <= numeric_path[["open", "close", "high"]].min(axis=1))
    )
    if not bool(structurally_valid.all()):
        return {
            "status": "pending",
            "reason": "invalid_ohlc_bar",
            "episode_id": episode["episode_id"],
        }
    evidence = _build_price_evidence(path, exit_ts, exit_price)
    evidence_entry, evidence_exit, evidence_ret, evidence_mfe, evidence_mae = (
        _validate_price_evidence(
            evidence,
            entry=entry_ts,
            exit_=exit_ts,
            bar_seconds=int(bar_seconds),
        )
    )

    # Latest timestamp actually used by this label, never the nightly cache's
    # later end-of-session tail.
    price_vintage = _iso_utc(exit_ts)
    target_aligned, training_eligible, training_reasons = _training_quality(
        available=available,
        target=target,
        entry=entry_ts,
        exit_=exit_ts,
        bar_seconds=int(bar_seconds),
        price_delay_minutes=price_delay_minutes,
    )
    row = {
        "schema": OUTCOME_SCHEMA,
        "outcome_id": _outcome_id(episode["episode_id"]),
        "episode_id": episode["episode_id"],
        "horizon_minutes": HORIZON_MINUTES,
        "status": "complete",
        "reason": None,
        "horizon_anchor": episode["available_at"],
        "target_time": _iso_utc(target),
        "computed_at": _iso_utc(now),
        "matured_at": _iso_utc(measurement_complete_at),
        "measurement": {
            "version": MEASUREMENT_VERSION,
            "kind": "aligned_bar_proxy",
            "target_aligned": target_aligned,
            "training_eligible": training_eligible,
            "training_ineligibility_reasons": training_reasons,
            "window": {"start": _iso_utc(entry_ts), "end": _iso_utc(exit_ts)},
        },
        "underlying": {
            "status": "complete",
            "entry_time": _iso_utc(entry_ts),
            "exit_time": _iso_utc(exit_ts),
            "entry_price": evidence_entry,
            "exit_price": evidence_exit,
            "ret": evidence_ret,
            "mfe": evidence_mfe,
            "mae": evidence_mae,
            "entry_delay_minutes": round((entry_ts - available).total_seconds() / 60.0, 3),
            "exit_delay_minutes": round((exit_ts - target).total_seconds() / 60.0, 3),
            "bar_seconds": int(bar_seconds),
            "path_basis": "aligned_bar_open_to_open_with_intervening_bar_high_low",
            "evidence": evidence,
        },
        "option": {
            "status": "unavailable",
            "reason": "no_executable_nbbo_quote_path",
            "quote_basis": None,
            "ret": None,
            "mfe": None,
            "mae": None,
        },
        "provenance": {
            "price_source": price_source,
            "price_vintage": price_vintage,
            "price_delay_minutes": (
                int(price_delay_minutes) if price_delay_minutes is not None else None
            ),
            "source_receipt_schema": receipt["schema"],
            "source_available_at": receipt["source_available_at"],
            "source_file_sha256": receipt["source_file_sha256"],
            "source_file_row_count": receipt["row_count"],
            "source_file_first_time": receipt["first_time"],
            "source_file_last_time": receipt["last_time"],
            "adjusted": receipt["adjusted"],
            "price_basis": receipt["price_basis"],
            "timestamp_basis": receipt["timestamp_basis"],
        },
        "label_authority": "research_only",
    }
    validate_outcome(row)
    return row


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a newline-terminated JSONL ledger, failing closed on any corruption."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read JSONL ledger {p}: {exc}") from exc
    return _decode_jsonl(raw, p)


def _decode_jsonl(raw: bytes, path: Path) -> list[dict[str, Any]]:
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise ContractError(f"JSONL ledger {path} has a torn/non-terminated final line")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(f"JSONL ledger {path} is not valid UTF-8") from exc
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise ContractError(f"JSONL ledger {path} has a blank line at {lineno}")
        try:
            obj = _strict_json_loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ContractError(f"JSONL ledger {path} has malformed line {lineno}") from exc
        if not isinstance(obj, dict):
            raise ContractError(f"JSONL ledger {path} line {lineno} is not an object")
        out.append(obj)
    return out


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _ensure_directory_durable(path: Path) -> None:
    """Durably link every newly-created ledger-directory component."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise ContractError(f"cannot find an existing parent for ledger directory {path}")
        cursor = parent
    if not cursor.is_dir():
        raise ContractError(f"ledger parent is not a directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir()
        _fsync_directory(directory)
        _fsync_directory(directory.parent)


def _append_validated(path: Path, rows: Iterable[dict[str, Any]], *,
                      id_field: str, semantic_key, validator) -> int:
    """Nightly-only, locked append with semantic idempotency and drift rejection."""
    if not nightly_advance_enabled():
        return -1
    candidates = list(rows)
    for row in candidates:
        validator(row)
    if not candidates and not path.exists():
        return 0
    _ensure_directory_durable(path.parent)

    # Lock the ledger inode itself: no sidecar can be accidentally committed, and
    # all cooperating nightly writers serialize the read/compare/append window.
    with path.open("a+b") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            # Opening with ``a+b`` may have created the ledger pathname. Persist
            # that link before a later checkpoint can claim the append exists.
            fh.flush()
            os.fsync(fh.fileno())
            _fsync_directory(path.parent)
            fh.seek(0)
            existing_rows = _decode_jsonl(fh.read(), path)
            by_id: dict[object, bytes] = {}
            by_semantic: dict[object, bytes] = {}
            for existing in existing_rows:
                validator(existing)
                canonical = _canonical_bytes(existing)
                identity = existing.get(id_field)
                semantic = semantic_key(existing)
                if identity in by_id and by_id[identity] != canonical:
                    raise ContractError(f"conflicting existing payload for {id_field}={identity!r}")
                if semantic in by_semantic and by_semantic[semantic] != canonical:
                    raise ContractError(f"conflicting existing payload for semantic key={semantic!r}")
                by_id[identity] = canonical
                by_semantic[semantic] = canonical

            fresh: list[dict[str, Any]] = []
            for row in candidates:
                canonical = _canonical_bytes(row)
                identity = row.get(id_field)
                semantic = semantic_key(row)
                prior_id = by_id.get(identity)
                prior_semantic = by_semantic.get(semantic)
                if prior_id is not None or prior_semantic is not None:
                    if ((prior_id is None or prior_id == canonical)
                            and (prior_semantic is None or prior_semantic == canonical)):
                        continue
                    raise ContractError(
                        f"conflicting append payload for {id_field}={identity!r}, "
                        f"semantic key={semantic!r}"
                    )
                by_id[identity] = canonical
                by_semantic[semantic] = canonical
                fresh.append(row)
            if not fresh:
                return 0
            fh.seek(0, os.SEEK_END)
            for row in fresh:
                fh.write(_canonical_bytes(row) + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
            return len(fresh)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def append_episodes(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    return _append_validated(
        path,
        rows,
        id_field="episode_id",
        semantic_key=lambda row: (row.get("source"), row.get("source_event_id")),
        validator=validate_episode,
    )


def append_outcomes(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    return _append_validated(
        path,
        rows,
        id_field="outcome_id",
        semantic_key=lambda row: (row.get("episode_id"), row.get("horizon_minutes")),
        validator=validate_outcome,
    )


def append_session_outcomes(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    return _append_validated(
        path,
        rows,
        id_field="outcome_id",
        semantic_key=lambda row: (row.get("episode_id"), row.get("horizon")),
        validator=validate_session_outcome,
    )
