"""Fail-closed contracts for biopharma seasonality and its consumers.

The contracts encode the authority boundary before any predictive model exists:

* mutable catalyst facts are bitemporal (``effective_at`` and ``known_at``);
* Neural Web receives a compact, expiring, context-only state;
* Prophet may narrate or request attention, but seasonality cannot originate,
  rank, size, gate, or rewrite a trade plan;
* a future adverse-event confidence cap is impossible unless a separately
  recorded de-escalation gate has passed.

These are pure-stdlib validators/builders so ingestion jobs and thin CI runners
can use them without pandas, scipy, or jsonschema.
"""
from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

BIOTEMPORAL_EVENT_SCHEMA = "biopharma.event.v1"
NEURALWEB_STATE_SCHEMA = "neuralweb.biopharma_seasonality_state.v1"
PROPHET_OVERLAY_SCHEMA = "prophet.seasonality_overlay/v1"

_DATE_PRECISIONS = frozenset({"exact_time", "exact_date", "month", "quarter", "range", "unknown"})
_CLOCK_TYPES = frozenset({"calendar", "event", "regime"})
_STATE_TIERS = frozenset({"display", "shadow"})
_OVERLAY_ACTIONS = frozenset({"NONE", "NARRATE", "ATTEND", "CAP_CONFIDENCE"})
_FORBIDDEN_AUTHORITY_KEYS = (
    "may_rank",
    "may_gate",
    "may_size",
    "may_originate",
    "may_rewrite_geometry",
    "may_boost_confidence",
)


class ContractError(ValueError):
    """Raised when a seasonality payload violates a safety or data contract."""


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field} must be an object")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _parse_utc(value: Any, field: str) -> datetime:
    text = _require_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a number in [0, 1]")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ContractError(f"{field} must be a finite number in [0, 1]")
    return number


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} must be a non-negative integer")
    return value


def _sha256_ref(value: Any, field: str) -> str:
    text = _require_text(value, field)
    prefix, separator, digest = text.partition(":")
    if prefix != "sha256" or not separator or len(digest) != 64:
        raise ContractError(f"{field} must be a sha256:<64 hex chars> reference")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ContractError(f"{field} must be a sha256:<64 hex chars> reference") from exc
    return text


def validate_bitemporal_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a detached ``biopharma.event.v1`` payload.

    ``effective_at`` may be later than ``known_at``: an issuer can announce a
    future PDUFA date today.  The anti-leakage invariant is instead that the
    system cannot know a record before it was published and ingested.
    """
    payload = dict(_require_mapping(event, "event"))
    if payload.get("schema") != BIOTEMPORAL_EVENT_SCHEMA:
        raise ContractError(f"schema must be {BIOTEMPORAL_EVENT_SCHEMA!r}")

    for field in (
        "event_id",
        "issuer_id",
        "event_type",
        "status",
        "source_class",
        "source_url",
    ):
        _require_text(payload.get(field), field)

    precision = payload.get("date_precision")
    if precision not in _DATE_PRECISIONS:
        raise ContractError(f"date_precision must be one of {sorted(_DATE_PRECISIONS)}")

    published_at = _parse_utc(payload.get("published_at"), "published_at")
    ingested_at = _parse_utc(payload.get("ingested_at"), "ingested_at")
    known_at = _parse_utc(payload.get("known_at"), "known_at")
    _parse_utc(payload.get("effective_at"), "effective_at")
    if ingested_at < published_at:
        raise ContractError("ingested_at cannot precede published_at")
    if known_at < ingested_at:
        raise ContractError("known_at cannot precede ingested_at")

    scheduled_start = payload.get("scheduled_start")
    scheduled_end = payload.get("scheduled_end")
    if (scheduled_start is None) ^ (scheduled_end is None):
        raise ContractError("scheduled_start and scheduled_end must be supplied together")
    if scheduled_start is not None:
        start = _parse_utc(scheduled_start, "scheduled_start")
        end = _parse_utc(scheduled_end, "scheduled_end")
        if end < start:
            raise ContractError("scheduled_end cannot precede scheduled_start")

    if payload.get("actual_at") is not None:
        _parse_utc(payload["actual_at"], "actual_at")

    _sha256_ref(payload.get("source_hash"), "source_hash")
    certainty = payload.get("certainty")
    if certainty is not None:
        _probability(certainty, "certainty")
    return deepcopy(payload)


def _validate_forecast(forecast: Mapping[str, Any]) -> None:
    _require_text(forecast.get("target"), "forecast.target")
    horizon = forecast.get("horizon_td")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ContractError("forecast.horizon_td must be a positive integer")
    p = _probability(forecast.get("p"), "forecast.p")
    baseline = _probability(forecast.get("p_baseline"), "forecast.p_baseline")
    edge = forecast.get("edge")
    if isinstance(edge, bool) or not isinstance(edge, (int, float)) or not math.isfinite(float(edge)):
        raise ContractError("forecast.edge must be a finite number")
    if not math.isclose(float(edge), p - baseline, abs_tol=1e-9):
        raise ContractError("forecast.edge must equal forecast.p - forecast.p_baseline")
    ci = forecast.get("ci90")
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        raise ContractError("forecast.ci90 must contain [lower, upper]")
    lower = _probability(ci[0], "forecast.ci90[0]")
    upper = _probability(ci[1], "forecast.ci90[1]")
    if lower > upper or not lower <= p <= upper:
        raise ContractError("forecast.ci90 must be ordered and contain forecast.p")


def _validate_authority(authority: Mapping[str, Any]) -> None:
    if authority.get("may_explain") is not True:
        raise ContractError("authority.may_explain must be true")
    if authority.get("may_flag_attention") is not True:
        raise ContractError("authority.may_flag_attention must be true")
    if authority.get("may_deescalate") is not False:
        raise ContractError("authority.may_deescalate must remain false before a separate gate")
    for key in _FORBIDDEN_AUTHORITY_KEYS:
        if authority.get(key) is not False:
            raise ContractError(f"authority.{key} must be false")


def validate_neuralweb_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a compact, expiring Neural Web context state."""
    payload = dict(_require_mapping(state, "state"))
    if payload.get("schema") != NEURALWEB_STATE_SCHEMA:
        raise ContractError(f"schema must be {NEURALWEB_STATE_SCHEMA!r}")
    if payload.get("tier") not in _STATE_TIERS:
        raise ContractError(f"tier must be one of {sorted(_STATE_TIERS)}")
    if payload.get("is_context_only") is not True:
        raise ContractError("is_context_only must be true")

    entity = _require_mapping(payload.get("entity"), "entity")
    _require_text(entity.get("type"), "entity.type")
    _require_text(entity.get("id"), "entity.id")

    clock = _require_mapping(payload.get("clock"), "clock")
    if clock.get("type") not in _CLOCK_TYPES:
        raise ContractError(f"clock.type must be one of {sorted(_CLOCK_TYPES)}")
    _require_text(clock.get("phase"), "clock.phase")

    available_at = _parse_utc(payload.get("available_at"), "available_at")
    expires_at = _parse_utc(payload.get("expires_at"), "expires_at")
    if expires_at <= available_at:
        raise ContractError("expires_at must be later than available_at")

    forecast = _require_mapping(payload.get("forecast"), "forecast")
    _validate_forecast(forecast)

    evidence = _require_mapping(payload.get("evidence"), "evidence")
    for field in ("n_independent", "n_issuers", "n_date_clusters", "live_n"):
        _non_negative_int(evidence.get(field), f"evidence.{field}")
    for field in ("q_by", "p_max_t", "spa_p"):
        if evidence.get(field) is not None:
            _probability(evidence[field], f"evidence.{field}")

    uncertainty = _require_mapping(payload.get("uncertainty"), "uncertainty")
    if not isinstance(uncertainty.get("abstain"), bool):
        raise ContractError("uncertainty.abstain must be a boolean")
    flags = uncertainty.get("flags")
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ContractError("uncertainty.flags must be a list of strings")

    authority = _require_mapping(payload.get("authority"), "authority")
    _validate_authority(authority)

    provenance = _require_mapping(payload.get("provenance"), "provenance")
    _require_text(provenance.get("model_version"), "provenance.model_version")
    _sha256_ref(provenance.get("pattern_spec_hash"), "provenance.pattern_spec_hash")
    _sha256_ref(provenance.get("data_snapshot"), "provenance.data_snapshot")
    return deepcopy(payload)


def build_neuralweb_state(
    *,
    artifact_id: str,
    entity: Mapping[str, Any],
    asof: str,
    available_at: str,
    expires_at: str,
    clock: Mapping[str, Any],
    forecast: Mapping[str, Any],
    evidence: Mapping[str, Any],
    uncertainty: Mapping[str, Any],
    provenance: Mapping[str, Any],
    tier: str = "shadow",
) -> dict[str, Any]:
    """Build a state with the birth authority ceiling wired in."""
    payload = {
        "schema": NEURALWEB_STATE_SCHEMA,
        "artifact_id": artifact_id,
        "entity": dict(entity),
        "asof": asof,
        "available_at": available_at,
        "expires_at": expires_at,
        "tier": tier,
        "is_context_only": True,
        "clock": dict(clock),
        "forecast": dict(forecast),
        "evidence": dict(evidence),
        "uncertainty": dict(uncertainty),
        "authority": {
            "may_explain": True,
            "may_flag_attention": True,
            "may_deescalate": False,
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_originate": False,
            "may_rewrite_geometry": False,
            "may_boost_confidence": False,
        },
        "provenance": dict(provenance),
    }
    return validate_neuralweb_state(payload)


def validate_prophet_overlay(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the one-way, shrink-only Prophet integration contract."""
    payload = dict(_require_mapping(overlay, "overlay"))
    if payload.get("schema") != PROPHET_OVERLAY_SCHEMA:
        raise ContractError(f"schema must be {PROPHET_OVERLAY_SCHEMA!r}")
    _require_text(payload.get("plan_id"), "plan_id")
    _require_text(payload.get("seasonality_state_ref"), "seasonality_state_ref")
    _parse_utc(payload.get("expires_at"), "expires_at")
    action = payload.get("action")
    if action not in _OVERLAY_ACTIONS:
        raise ContractError(f"action must be one of {sorted(_OVERLAY_ACTIONS)}")
    reasons = payload.get("reason_codes")
    if not isinstance(reasons, list) or not all(isinstance(reason, str) and reason for reason in reasons):
        raise ContractError("reason_codes must be a list of non-empty strings")

    for field in ("horizon_match", "event_inside_plan_horizon", "overlap_with_existing_features"):
        if not isinstance(payload.get(field), bool):
            raise ContractError(f"{field} must be a boolean")

    authority = _require_mapping(payload.get("authority"), "authority")
    for key in (
        "may_originate",
        "may_rank",
        "may_gate",
        "may_size",
        "may_rewrite_geometry",
        "may_boost_confidence",
    ):
        if authority.get(key) is not False:
            raise ContractError(f"authority.{key} must be false")

    if action == "CAP_CONFIDENCE":
        if payload.get("adverse_event") is not True:
            raise ContractError("CAP_CONFIDENCE requires adverse_event=true")
        if payload.get("deescalation_gate_passed") is not True:
            raise ContractError("CAP_CONFIDENCE requires a separately passed de-escalation gate")
        _probability(payload.get("confidence_cap"), "confidence_cap")
    elif payload.get("confidence_cap") is not None:
        raise ContractError("confidence_cap is allowed only for CAP_CONFIDENCE")
    return deepcopy(payload)


def build_prophet_overlay(
    *,
    plan_id: str,
    seasonality_state_ref: str,
    horizon_match: bool,
    event_inside_plan_horizon: bool,
    overlap_with_existing_features: bool,
    action: str,
    reason_codes: list[str],
    expires_at: str,
    adverse_event: bool = False,
    deescalation_gate_passed: bool = False,
    confidence_cap: float | None = None,
) -> dict[str, Any]:
    """Build an overlay that can never lift rank, confidence, size, or geometry."""
    payload = {
        "schema": PROPHET_OVERLAY_SCHEMA,
        "plan_id": plan_id,
        "seasonality_state_ref": seasonality_state_ref,
        "horizon_match": horizon_match,
        "event_inside_plan_horizon": event_inside_plan_horizon,
        "overlap_with_existing_features": overlap_with_existing_features,
        "action": action,
        "reason_codes": list(reason_codes),
        "expires_at": expires_at,
        "adverse_event": adverse_event,
        "deescalation_gate_passed": deescalation_gate_passed,
        "confidence_cap": confidence_cap,
        "authority": {
            "may_originate": False,
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_rewrite_geometry": False,
            "may_boost_confidence": False,
        },
    }
    return validate_prophet_overlay(payload)
