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

``biopharma.event.v2`` adds the temporal-honesty layer.  ``v1`` demands an exact
timezone-bearing instant for every date it carries, so a source that only ever
said "Q3 2025" had to be pushed through a midpoint or a midnight to fit — the
payload then asserted a precision the issuer never did.  ``v2`` replaces every
such field with a ``source_temporal`` object that carries a *precision*, a
*bound rule*, and a ``[lower_bound, upper_bound]`` span.  It deliberately offers
no single ``value`` timestamp, so a consumer cannot collapse a month to an
instant: the fabrication is structurally unavailable rather than merely
discouraged.

Span convention (one convention, everywhere): bounds are **inclusive on both
ends** and resolve to microsecond granularity, so a day span ends at
``23:59:59.999999`` of that day, a month span ends on the last calendar day of
that month (2024-02-29, but 2025-02-28), a quarter span ends on the last day of
its third month, and a year span ends 12-31.  When ``source_timezone`` is
``None`` the span is a UTC calendar period; when the source itself declared a
zone the span is that zone's calendar period, and comparisons normalise to UTC.
A zone is recorded only when the source supplied one — it is never inferred.
Both edges are computed as instants — the upper bound is the microsecond before
the next period begins — so consecutive periods are contiguous even in zones
whose UTC offset changes at midnight, and both edges are re-rendered in the
declared zone so a stored wall time is one the zone actually had.

The bounds are checked against the rule that names them, not merely labelled by
it: a ``month_span`` must be exactly that calendar month in the declared zone,
so a peer-produced payload cannot wear a ``month`` label over a collapsed
instant or an arbitrary window.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

BIOTEMPORAL_EVENT_SCHEMA = "biopharma.event.v1"
BIOTEMPORAL_EVENT_V2_SCHEMA = "biopharma.event.v2"
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


# ---------------------------------------------------------------------------
# biopharma.event.v2 — versioned event temporal contract
# ---------------------------------------------------------------------------

EVENT_TYPE_ALLOWLIST_V2 = frozenset(
    {
        "trial_start",
        "trial_status_change",
        "trial_completion",
        "primary_completion",
        "results_posted",
        "readout",
        "pdufa_date",
        "advisory_committee",
        "regulatory_decision",
        "regulatory_submission",
        "approval",
        "complete_response_letter",
        "clinical_hold",
        "trial_termination",
        "trial_suspension",
        "trial_withdrawal",
        "conference_presentation",
        "issuer_announcement",
    }
)

EVENT_STATUS_ALLOWLIST_V2 = frozenset(
    {
        "scheduled",
        "estimated",
        "confirmed",
        "occurred",
        "delayed",
        "cancelled",
        "withdrawn",
        "superseded",
        "unknown",
    }
)

TEMPORAL_PRECISIONS_V2 = frozenset(
    {"exact_time", "exact_date", "month", "quarter", "year", "range", "unknown"}
)
TEMPORAL_BOUND_RULES_V2 = frozenset(
    {
        "exact_instant",
        "day_span",
        "month_span",
        "quarter_span",
        "year_span",
        "source_declared_range",
        "unavailable",
        "unparsed",
    }
)

# The precision <-> bound_rule bijection.  ``unknown`` is the single precision
# with two honest rules: the source said nothing (``unavailable``) or the source
# said something we could not interpret (``unparsed``).  Those are different
# facts and the contract keeps them apart.
_PRECISION_BOUND_RULES_V2: dict[str, frozenset[str]] = {
    "exact_time": frozenset({"exact_instant"}),
    "exact_date": frozenset({"day_span"}),
    "month": frozenset({"month_span"}),
    "quarter": frozenset({"quarter_span"}),
    "year": frozenset({"year_span"}),
    "range": frozenset({"source_declared_range"}),
    "unknown": frozenset({"unavailable", "unparsed"}),
}

_SOURCE_TEMPORAL_KEYS = frozenset(
    {
        "available",
        "unavailable_reason",
        "original_value",
        "precision",
        "lower_bound",
        "upper_bound",
        "source_timezone",
        "bound_rule",
    }
)

_EVENT_V2_TEMPORAL_FIELDS = ("source_published", "source_effective", "scheduled_window", "actual")

_EVENT_V2_KEYS = frozenset(
    {
        "schema",
        "event_id",
        "issuer_id",
        "event_type",
        "status",
        "source_class",
        "source_url",
        "source_hash",
        "known_at",
        "ingested_at",
        "source_published",
        "source_effective",
        "scheduled_window",
        "actual",
        "date_precision",
        "certainty",
        "revision",
    }
)

_REVISION_KEYS_V2 = frozenset({"revision_id", "revision_index", "supersedes"})


def _utc_text(moment: datetime) -> str:
    """Render an instant in the one canonical UTC form used for hashing."""
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _zone(source_timezone: str | None, field: str = "source_timezone") -> Any:
    if source_timezone is None:
        return timezone.utc
    _require_text(source_timezone, field)
    try:
        return ZoneInfo(source_timezone)
    except Exception as exc:  # pragma: no cover - zoneinfo raises several types
        raise ContractError(f"{field} must be a known IANA timezone") from exc


def _calendar_year(year: Any, field: str = "year") -> int:
    """A calendar year the standard library can actually represent."""
    value = _non_negative_int(year, field)
    if not 1 <= value <= 9999:
        raise ContractError(f"{field} must be an integer in [1, 9999]")
    return value


def _calendar_span(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    source_timezone: str | None,
) -> tuple[str, str]:
    """Return inclusive ``[lower, upper]`` ISO strings for a calendar period.

    Both edges are resolved as *instants* and then re-rendered in the declared
    zone.  Naming the upper edge by its wall clock (``23:59:59.999999``) is
    wrong in any zone whose offset changes at midnight: that wall time is
    ambiguous when the clocks go back, and Python resolves the ambiguity to the
    earlier offset, which drops the last hour of the period and leaves a
    one-hour gap between consecutive spans.  The upper edge is therefore the
    microsecond before the next period begins, which is contiguous by
    construction.  The lower edge is likewise round-tripped through UTC so that
    a period beginning on a *nonexistent* local midnight (clocks jump forward
    at 00:00) records the wall time the zone actually had rather than one it
    never showed.
    """
    tzinfo = _zone(source_timezone)
    lower_instant = datetime(start[0], start[1], start[2], 0, 0, 0, 0, tzinfo=tzinfo).astimezone(
        timezone.utc
    )
    try:
        next_start = datetime(end[0], end[1], end[2]) + timedelta(days=1)
    except OverflowError as exc:  # pragma: no cover - only reachable at 9999-12-31
        raise ContractError("calendar span cannot extend past 9999-12-31") from exc
    upper_instant = (
        datetime(
            next_start.year, next_start.month, next_start.day, 0, 0, 0, 0, tzinfo=tzinfo
        ).astimezone(timezone.utc)
        - timedelta(microseconds=1)
    )
    return (
        lower_instant.astimezone(tzinfo).isoformat(),
        upper_instant.astimezone(tzinfo).isoformat(),
    )


_CALENDAR_BOUND_RULES = ("day_span", "month_span", "quarter_span", "year_span")


def _expected_calendar_span(
    bound_rule: str, lower: datetime, source_timezone: str | None
) -> tuple[str, str]:
    """The one span a calendar ``bound_rule`` can mean, given where it starts."""
    local = lower.astimezone(_zone(source_timezone))
    if bound_rule == "day_span":
        start = end = (local.year, local.month, local.day)
    elif bound_rule == "month_span":
        start = (local.year, local.month, 1)
        end = (local.year, local.month, calendar.monthrange(local.year, local.month)[1])
    elif bound_rule == "quarter_span":
        start_month = 3 * ((local.month - 1) // 3) + 1
        end_month = start_month + 2
        start = (local.year, start_month, 1)
        end = (local.year, end_month, calendar.monthrange(local.year, end_month)[1])
    else:  # year_span
        start = (local.year, 1, 1)
        end = (local.year, 12, 31)
    return _calendar_span(start, end, source_timezone)


def validate_source_temporal(
    temporal: Mapping[str, Any], field: str = "source_temporal"
) -> dict[str, Any]:
    """Validate and return a detached ``source_temporal`` object.

    The object carries a span, never an instant, so a month can never be read as
    a midnight.  ``exact_time`` is the only precision whose bounds collapse, and
    it must collapse exactly.

    The calendar rules are checked against their own bounds rather than trusted
    as labels: a ``month_span`` must be exactly the calendar month its lower
    bound falls in, in the zone the payload declares.  Without that check the
    guarantee would live only in this module's builders, and any payload built
    elsewhere — the ingestion jobs this validator exists for — could label a
    single instant, or a four-year window, as a month.
    """
    payload = dict(_require_mapping(temporal, field))
    unsupported = sorted(set(payload) - _SOURCE_TEMPORAL_KEYS)
    if unsupported:
        raise ContractError(
            f"{field} carries unsupported keys {unsupported}; a span has no single instant"
        )
    missing = sorted(_SOURCE_TEMPORAL_KEYS - set(payload))
    if missing:
        raise ContractError(f"{field} is missing required keys {missing}")

    available = payload["available"]
    if not isinstance(available, bool):
        raise ContractError(f"{field}.available must be a boolean")

    precision = payload["precision"]
    if precision not in TEMPORAL_PRECISIONS_V2:
        raise ContractError(f"{field}.precision must be one of {sorted(TEMPORAL_PRECISIONS_V2)}")
    bound_rule = payload["bound_rule"]
    if bound_rule not in TEMPORAL_BOUND_RULES_V2:
        raise ContractError(f"{field}.bound_rule must be one of {sorted(TEMPORAL_BOUND_RULES_V2)}")
    if bound_rule not in _PRECISION_BOUND_RULES_V2[precision]:
        raise ContractError(
            f"{field}.bound_rule {bound_rule!r} is not the bound rule for precision {precision!r}"
        )

    reason = payload["unavailable_reason"]
    original_value = payload["original_value"]
    lower = payload["lower_bound"]
    upper = payload["upper_bound"]
    source_timezone = payload["source_timezone"]
    if source_timezone is not None:
        _zone(source_timezone, f"{field}.source_timezone")

    if not available:
        if bound_rule != "unavailable":
            raise ContractError(
                f"{field}.bound_rule must be 'unavailable' when available is false"
            )
        _require_text(reason, f"{field}.unavailable_reason")
        if original_value is not None:
            raise ContractError(f"{field}.original_value must be null when available is false")
        if lower is not None or upper is not None:
            raise ContractError(f"{field} bounds must be null when available is false")
        return deepcopy(payload)

    if bound_rule == "unavailable":
        raise ContractError(f"{field}.bound_rule 'unavailable' requires available to be false")
    if reason is not None:
        raise ContractError(f"{field}.unavailable_reason must be null when available is true")
    if original_value is not None:
        _require_text(original_value, f"{field}.original_value")

    if bound_rule == "unparsed":
        _require_text(original_value, f"{field}.original_value")
        if lower is not None or upper is not None:
            raise ContractError(f"{field} bounds must be null when the source value is unparsed")
        return deepcopy(payload)

    if bound_rule == "source_declared_range":
        _require_text(original_value, f"{field}.original_value")

    lower_dt = _parse_utc(lower, f"{field}.lower_bound")
    upper_dt = _parse_utc(upper, f"{field}.upper_bound")
    if upper_dt < lower_dt:
        raise ContractError(f"{field}.upper_bound cannot precede {field}.lower_bound")
    if precision == "exact_time" and lower_dt != upper_dt:
        raise ContractError(f"{field} exact_time requires lower_bound to equal upper_bound")
    if bound_rule == "source_declared_range" and lower_dt == upper_dt:
        raise ContractError(
            f"{field} source_declared_range collapsed to one instant; that is an exact_instant"
        )
    if bound_rule in _CALENDAR_BOUND_RULES:
        expected_lower, expected_upper = _expected_calendar_span(bound_rule, lower_dt, source_timezone)
        if _parse_utc(expected_lower, f"{field}.lower_bound") != lower_dt or _parse_utc(
            expected_upper, f"{field}.upper_bound"
        ) != upper_dt:
            raise ContractError(
                f"{field} bounds are not the {bound_rule} they claim: "
                f"expected {expected_lower} .. {expected_upper}"
            )
    return deepcopy(payload)


def build_source_temporal(
    *,
    available: bool,
    precision: str,
    bound_rule: str,
    unavailable_reason: str | None = None,
    original_value: str | None = None,
    lower_bound: str | None = None,
    upper_bound: str | None = None,
    source_timezone: str | None = None,
) -> dict[str, Any]:
    """Build a ``source_temporal`` object, validating on the way out."""
    payload = {
        "available": available,
        "unavailable_reason": unavailable_reason,
        "original_value": original_value,
        "precision": precision,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "source_timezone": source_timezone,
        "bound_rule": bound_rule,
    }
    return validate_source_temporal(payload)


def source_temporal_unavailable(reason: str) -> dict[str, Any]:
    """The source said nothing.  That absence is a fact, not a missing field."""
    return build_source_temporal(
        available=False,
        precision="unknown",
        bound_rule="unavailable",
        unavailable_reason=reason,
    )


def source_temporal_unparsed(original_value: str) -> dict[str, Any]:
    """The source said something we could not interpret — keep the words."""
    return build_source_temporal(
        available=True,
        precision="unknown",
        bound_rule="unparsed",
        original_value=original_value,
    )


def source_temporal_exact(instant: str, *, original_value: str | None = None) -> dict[str, Any]:
    """A source-asserted instant: the only case whose span collapses to a point."""
    return build_source_temporal(
        available=True,
        precision="exact_time",
        bound_rule="exact_instant",
        original_value=original_value,
        lower_bound=instant,
        upper_bound=instant,
    )


def source_temporal_day(
    date_str: str,
    *,
    source_timezone: str | None = None,
    original_value: str | None = None,
) -> dict[str, Any]:
    """A date-only source value, spanning that whole calendar day."""
    text = _require_text(date_str, "date_str")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ContractError("date_str must be an ISO-8601 calendar date (YYYY-MM-DD)") from exc
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        # ``strptime`` accepts "2025-3-9"; storing it unnormalised as
        # ``original_value`` would hash two records of the same source date
        # differently, so only the zero-padded form is admitted.
        raise ContractError("date_str must be an ISO-8601 calendar date (YYYY-MM-DD)")
    _calendar_year(parsed.year, "date_str year")
    lower, upper = _calendar_span(
        (parsed.year, parsed.month, parsed.day),
        (parsed.year, parsed.month, parsed.day),
        source_timezone,
    )
    return build_source_temporal(
        available=True,
        precision="exact_date",
        bound_rule="day_span",
        original_value=original_value if original_value is not None else text,
        lower_bound=lower,
        upper_bound=upper,
        source_timezone=source_timezone,
    )


def source_temporal_month(
    year: int,
    month: int,
    *,
    source_timezone: str | None = None,
    original_value: str | None = None,
) -> dict[str, Any]:
    """A year-month source value, spanning the whole calendar month."""
    _calendar_year(year, "year")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ContractError("month must be an integer in [1, 12]")
    last_day = calendar.monthrange(year, month)[1]
    lower, upper = _calendar_span((year, month, 1), (year, month, last_day), source_timezone)
    return build_source_temporal(
        available=True,
        precision="month",
        bound_rule="month_span",
        original_value=original_value if original_value is not None else f"{year:04d}-{month:02d}",
        lower_bound=lower,
        upper_bound=upper,
        source_timezone=source_timezone,
    )


def source_temporal_quarter(
    year: int,
    quarter: int,
    *,
    source_timezone: str | None = None,
    original_value: str | None = None,
) -> dict[str, Any]:
    """A calendar-quarter source value, spanning its three whole months."""
    _calendar_year(year, "year")
    if isinstance(quarter, bool) or not isinstance(quarter, int) or not 1 <= quarter <= 4:
        raise ContractError("quarter must be an integer in [1, 4]")
    start_month = 3 * (quarter - 1) + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    lower, upper = _calendar_span(
        (year, start_month, 1), (year, end_month, last_day), source_timezone
    )
    return build_source_temporal(
        available=True,
        precision="quarter",
        bound_rule="quarter_span",
        original_value=original_value if original_value is not None else f"{year:04d}-Q{quarter}",
        lower_bound=lower,
        upper_bound=upper,
        source_timezone=source_timezone,
    )


def source_temporal_year(
    year: int,
    *,
    source_timezone: str | None = None,
    original_value: str | None = None,
) -> dict[str, Any]:
    """A year-only source value, spanning the whole calendar year."""
    _calendar_year(year, "year")
    lower, upper = _calendar_span((year, 1, 1), (year, 12, 31), source_timezone)
    return build_source_temporal(
        available=True,
        precision="year",
        bound_rule="year_span",
        original_value=original_value if original_value is not None else f"{year:04d}",
        lower_bound=lower,
        upper_bound=upper,
        source_timezone=source_timezone,
    )


def source_temporal_range(
    lower: str,
    upper: str,
    *,
    original_value: str,
    source_timezone: str | None = None,
) -> dict[str, Any]:
    """A range the source itself declared — not one we widened for it.

    ``original_value`` is required rather than optional: it is the only thing
    that distinguishes a window the source stated from a window we invented,
    and a ``source_declared_range`` with no record of what was declared is the
    second claim wearing the first one's label.  A range whose ends coincide is
    refused — that is an ``exact_instant``, and calling it a range would widen
    the apparent honesty of a point.
    """
    return build_source_temporal(
        available=True,
        precision="range",
        bound_rule="source_declared_range",
        original_value=original_value,
        lower_bound=lower,
        upper_bound=upper,
        source_timezone=source_timezone,
    )


def source_temporal_is_study_eligible(temporal: Mapping[str, Any]) -> bool:
    """True iff the value is available and bounded on both ends.

    Imprecision does not disqualify: a month or a quarter is bounded, and the
    event study handles the width through interval sensitivity.  An unbounded
    value — nothing said, or something unparsable — is not eligible, because
    there is no window to study.
    """
    payload = validate_source_temporal(temporal)
    return bool(
        payload["available"]
        and payload["lower_bound"] is not None
        and payload["upper_bound"] is not None
    )


def source_temporal_span_seconds(temporal: Mapping[str, Any]) -> float | None:
    """Width of the span in seconds, or ``None`` when the value is unbounded."""
    payload = validate_source_temporal(temporal)
    if payload["lower_bound"] is None or payload["upper_bound"] is None:
        return None
    lower = _parse_utc(payload["lower_bound"], "lower_bound")
    upper = _parse_utc(payload["upper_bound"], "upper_bound")
    return (upper - lower).total_seconds()


def validate_bitemporal_event_v2(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a detached ``biopharma.event.v2`` payload.

    ``source_effective`` is deliberately unconstrained against the system
    clocks — v1's documented intent is preserved here: an issuer can announce a
    future PDUFA date today, so an effective span later than ``known_at`` is
    correct, not leakage.  The anti-leakage invariants are the ones that involve
    the system's own clocks: we cannot know a record before we ingested it, we
    cannot have ingested it before the earliest moment it could have been
    published, and we cannot have known an event *occurred* before the earliest
    moment it could have occurred.  The published *upper* bound is not
    constrained — a March document is legitimately ingested in June — and
    neither is the ``actual`` upper bound, because a coarse actual span may
    legitimately extend past the moment we learned of it.

    The key set is closed.  A payload carrying an extra ``effective_at`` beside
    its ``source_effective`` span would be exactly the collapsed instant this
    schema exists to make unavailable, and :func:`canonical_event_v2_bytes`
    would then certify that fabrication as part of the replay hash.
    """
    payload = dict(_require_mapping(event, "event"))
    if payload.get("schema") != BIOTEMPORAL_EVENT_V2_SCHEMA:
        raise ContractError(f"schema must be {BIOTEMPORAL_EVENT_V2_SCHEMA!r}")

    unsupported = sorted(set(payload) - _EVENT_V2_KEYS)
    if unsupported:
        raise ContractError(
            f"event carries unsupported keys {unsupported}; a span has no single instant"
        )
    missing = sorted(_EVENT_V2_KEYS - set(payload))
    if missing:
        raise ContractError(f"event is missing required keys {missing}")

    for field in ("event_id", "issuer_id", "source_class", "source_url"):
        _require_text(payload.get(field), field)

    if payload.get("event_type") not in EVENT_TYPE_ALLOWLIST_V2:
        raise ContractError(f"event_type must be one of {sorted(EVENT_TYPE_ALLOWLIST_V2)}")
    if payload.get("status") not in EVENT_STATUS_ALLOWLIST_V2:
        raise ContractError(f"status must be one of {sorted(EVENT_STATUS_ALLOWLIST_V2)}")
    _sha256_ref(payload.get("source_hash"), "source_hash")

    ingested_at = _parse_utc(payload.get("ingested_at"), "ingested_at")
    known_at = _parse_utc(payload.get("known_at"), "known_at")
    if known_at < ingested_at:
        raise ContractError("known_at cannot precede ingested_at")

    source_published = validate_source_temporal(payload.get("source_published"), "source_published")
    source_effective = validate_source_temporal(payload.get("source_effective"), "source_effective")
    optional: dict[str, dict[str, Any] | None] = {"scheduled_window": None, "actual": None}
    for field in optional:
        if payload.get(field) is not None:
            optional[field] = validate_source_temporal(payload[field], field)

    if source_published["lower_bound"] is not None:
        published_lower = _parse_utc(source_published["lower_bound"], "source_published.lower_bound")
        if published_lower > ingested_at:
            raise ContractError("ingested_at cannot precede source_published.lower_bound")

    actual = optional["actual"]
    if actual is not None and actual["lower_bound"] is not None:
        actual_lower = _parse_utc(actual["lower_bound"], "actual.lower_bound")
        if actual_lower > known_at:
            raise ContractError("known_at cannot precede actual.lower_bound")

    if payload.get("date_precision") != source_effective["precision"]:
        raise ContractError("date_precision must mirror source_effective.precision")

    if payload.get("certainty") is not None:
        _probability(payload["certainty"], "certainty")

    revision = _require_mapping(payload.get("revision"), "revision")
    unsupported_revision = sorted(set(revision) - _REVISION_KEYS_V2)
    if unsupported_revision:
        # Lineage is lineage.  An authority-shaped key smuggled in here would
        # survive into the payload and into the replay hash.
        raise ContractError(f"revision carries unsupported keys {unsupported_revision}")
    revision_id = _require_text(revision.get("revision_id"), "revision.revision_id")
    _non_negative_int(revision.get("revision_index"), "revision.revision_index")
    supersedes = revision.get("supersedes")
    if supersedes is not None:
        _require_text(supersedes, "revision.supersedes")
        if supersedes == revision_id:
            raise ContractError("revision.supersedes must differ from revision.revision_id")
    return deepcopy(payload)


def build_bitemporal_event_v2(
    *,
    event_id: str,
    issuer_id: str,
    event_type: str,
    status: str,
    source_class: str,
    source_url: str,
    source_hash: str,
    known_at: str,
    ingested_at: str,
    source_published: Mapping[str, Any],
    source_effective: Mapping[str, Any],
    revision: Mapping[str, Any],
    scheduled_window: Mapping[str, Any] | None = None,
    actual: Mapping[str, Any] | None = None,
    certainty: float | None = None,
) -> dict[str, Any]:
    """Build a v2 event whose ``date_precision`` cannot outrun its source."""
    payload = {
        "schema": BIOTEMPORAL_EVENT_V2_SCHEMA,
        "event_id": event_id,
        "issuer_id": issuer_id,
        "event_type": event_type,
        "status": status,
        "source_class": source_class,
        "source_url": source_url,
        "source_hash": source_hash,
        "known_at": known_at,
        "ingested_at": ingested_at,
        "source_published": dict(source_published),
        "source_effective": dict(source_effective),
        "scheduled_window": None if scheduled_window is None else dict(scheduled_window),
        "actual": None if actual is None else dict(actual),
        "date_precision": _require_mapping(source_effective, "source_effective").get("precision"),
        "certainty": certainty,
        "revision": dict(revision),
    }
    return validate_bitemporal_event_v2(payload)


def _lift_v1_instant(instant: str, precision: str, field: str) -> dict[str, Any]:
    """Record a v1 event instant at the precision v1 itself declared.

    v1 forced every date through a timezone-bearing instant, so a row that only
    ever knew "Q3 2025" still stored a midpoint — and ``date_precision`` is the
    only surviving record that the instant was manufactured.  Reading the
    instant as an exact assertion and dropping ``date_precision`` would trust
    the fabricated field and delete the honest one, turning the upgrade into a
    one-way precision ratchet (quarter in, certified instant out).  The instant
    is therefore widened back to the calendar period v1 named, and kept
    verbatim as ``original_value`` so the widening is auditable.

    ``range`` and ``unknown`` name a width that v1's single instant cannot
    carry (v1 stores its only declared range in ``scheduled_start``/
    ``scheduled_end``, which upgrades on its own), so those lift to ``unparsed``
    with the v1 text preserved rather than to bounds we would have to invent.
    """
    if precision == "exact_time":
        return source_temporal_exact(instant, original_value=instant)
    moment = _parse_utc(instant, field)
    if precision == "exact_date":
        return source_temporal_day(moment.strftime("%Y-%m-%d"), original_value=instant)
    if precision == "month":
        return source_temporal_month(moment.year, moment.month, original_value=instant)
    if precision == "quarter":
        return source_temporal_quarter(
            moment.year, (moment.month - 1) // 3 + 1, original_value=instant
        )
    return source_temporal_unparsed(instant)


def upgrade_event_v1_to_v2(event_v1: Mapping[str, Any]) -> dict[str, Any]:
    """Lift a ``biopharma.event.v1`` payload into v2 without inventing anything.

    The v1 event-date fields (``effective_at`` and ``actual_at``) are lifted at
    the precision v1's own ``date_precision`` declared — see
    :func:`_lift_v1_instant`, which also explains why the instant is not simply
    trusted — and the v1 ``scheduled_start``/``scheduled_end`` pair becomes a
    ``range`` / ``source_declared_range`` window carrying that pair as its
    ``original_value``.  Three consequences are worth stating out loud:

    * ``published_at`` is not an event date but a document timestamp, which v1
      asserts exactly, so it stays ``exact_time`` regardless of
      ``date_precision``.
    * v1 records no inclusive/exclusive convention for ``scheduled_end`` and no
      producer in this repo pins one, so the pair is re-asserted as v1 stored
      it.  A window built under an exclusive convention keeps whatever width it
      already had; the ``original_value`` records the exact strings it came
      from.  An end equal to its start is written back as an ``exact_instant``
      rather than as a range with no width.
    * v1 has no revision lineage, so one is synthesised as
      ``{"revision_id": event_id, "revision_index": 0, "supersedes": None}`` —
      the event is its own first revision and supersedes nothing.

    A v1 ``event_type`` or ``status`` outside the v2 allowlists raises rather
    than being coerced: silently mapping an unknown code onto ``unknown`` would
    be the same fabrication this schema exists to prevent.
    """
    source = validate_bitemporal_event(event_v1)
    if source["event_type"] not in EVENT_TYPE_ALLOWLIST_V2:
        raise ContractError(f"event_type must be one of {sorted(EVENT_TYPE_ALLOWLIST_V2)}")
    if source["status"] not in EVENT_STATUS_ALLOWLIST_V2:
        raise ContractError(f"status must be one of {sorted(EVENT_STATUS_ALLOWLIST_V2)}")

    precision = source["date_precision"]
    scheduled_window = None
    if source.get("scheduled_start") is not None:
        start = source["scheduled_start"]
        end = source["scheduled_end"]
        declared = f"{start}/{end}"
        if _parse_utc(start, "scheduled_start") == _parse_utc(end, "scheduled_end"):
            scheduled_window = source_temporal_exact(start, original_value=declared)
        else:
            scheduled_window = source_temporal_range(start, end, original_value=declared)
    actual = None
    if source.get("actual_at") is not None:
        actual = _lift_v1_instant(source["actual_at"], precision, "actual_at")

    return build_bitemporal_event_v2(
        event_id=source["event_id"],
        issuer_id=source["issuer_id"],
        event_type=source["event_type"],
        status=source["status"],
        source_class=source["source_class"],
        source_url=source["source_url"],
        source_hash=source["source_hash"],
        known_at=source["known_at"],
        ingested_at=source["ingested_at"],
        source_published=source_temporal_exact(
            source["published_at"], original_value=source["published_at"]
        ),
        source_effective=_lift_v1_instant(source["effective_at"], precision, "effective_at"),
        scheduled_window=scheduled_window,
        actual=actual,
        certainty=source.get("certainty"),
        revision={"revision_id": source["event_id"], "revision_index": 0, "supersedes": None},
    )


def downgrade_event_v2_to_v1(event_v2: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a v2 event back to v1, refusing whenever that would fabricate.

    v1 stores ``published_at``, ``effective_at``, and ``actual_at`` as single
    instants, so those fields may only be written back when the v2 temporal is
    ``exact_time`` — anything else (a month, a quarter, an unparsed string, an
    absent value) would have to be collapsed to a point the source never
    asserted, and instead raises a :class:`ContractError` naming the field.

    ``scheduled_window`` is the one field with a two-bound counterpart in v1
    (``scheduled_start``/``scheduled_end``), so a ``range`` there is written
    back losslessly and is accepted alongside ``exact_time``.  Every other
    precision is still refused.

    The two optional fields are also nullable in v1, so a temporal that
    honestly records *absence* (``available`` false) maps losslessly onto v1's
    ``None`` instead of raising: refusing it would punish
    :func:`source_temporal_unavailable` — the encouraged form — while a payload
    that simply omitted the field downgraded fine.  An ``unparsed`` value is
    still refused, because there the source did say something and v1 has
    nowhere to keep it.
    """
    payload = validate_bitemporal_event_v2(event_v2)

    for field in _EVENT_V2_TEMPORAL_FIELDS:
        temporal = payload.get(field)
        if temporal is None:
            continue
        if field in ("scheduled_window", "actual") and not temporal["available"]:
            continue
        allowed = {"exact_time", "range"} if field == "scheduled_window" else {"exact_time"}
        if not temporal["available"] or temporal["precision"] not in allowed:
            raise ContractError(
                f"{field} cannot be downgraded to {BIOTEMPORAL_EVENT_SCHEMA}: "
                f"precision {temporal['precision']!r} is not an exact instant"
            )

    scheduled_window = payload.get("scheduled_window")
    if scheduled_window is not None and not scheduled_window["available"]:
        scheduled_window = None
    actual = payload.get("actual")
    if actual is not None and not actual["available"]:
        actual = None
    downgraded = {
        "schema": BIOTEMPORAL_EVENT_SCHEMA,
        "event_id": payload["event_id"],
        "issuer_id": payload["issuer_id"],
        "event_type": payload["event_type"],
        "status": payload["status"],
        "date_precision": payload["date_precision"],
        "scheduled_start": None if scheduled_window is None else scheduled_window["lower_bound"],
        "scheduled_end": None if scheduled_window is None else scheduled_window["upper_bound"],
        "actual_at": None if actual is None else actual["lower_bound"],
        "certainty": payload.get("certainty"),
        "published_at": payload["source_published"]["lower_bound"],
        "ingested_at": payload["ingested_at"],
        "known_at": payload["known_at"],
        "effective_at": payload["source_effective"]["lower_bound"],
        "source_class": payload["source_class"],
        "source_url": payload["source_url"],
        "source_hash": payload["source_hash"],
    }
    return validate_bitemporal_event(downgraded)


def event_v2_pit_leakage_is_checkable(event: Mapping[str, Any]) -> bool:
    """True iff this event's publication-leakage invariant could be evaluated.

    ``ingested_at >= source_published.lower_bound`` is the invariant v2 inherits
    from v1, and it can only fire when the source dated its own document.  A
    publication temporal that is ``unavailable`` or ``unparsed`` has no bound to
    compare against, so the check is skipped — nothing can be compared to
    nothing, and inventing a bound would be the fabrication this schema
    prevents.  What must not happen is a consumer reading an unchecked event as
    a checked one, so the skip is reported here rather than left implicit.
    """
    payload = validate_bitemporal_event_v2(event)
    return payload["source_published"]["lower_bound"] is not None


def _canonical_temporal(temporal: Mapping[str, Any], field: str) -> dict[str, Any]:
    canonical = dict(temporal)
    for key in ("lower_bound", "upper_bound"):
        if canonical.get(key) is not None:
            canonical[key] = _utc_text(_parse_utc(canonical[key], f"{field}.{key}"))
    return canonical


def canonical_event_v2_bytes(event: Mapping[str, Any]) -> bytes:
    """Deterministic bytes for a v2 event: sorted keys, no whitespace, UTC.

    Two payloads that assert the same facts hash the same even when their
    timestamps were written differently (``...T00:00:00Z`` versus
    ``...T00:00:00+00:00``, or a bound recorded at a source offset), because
    every instant is re-rendered in one UTC form first.  That is what makes
    replay determinism checkable rather than merely claimed.
    """
    payload = validate_bitemporal_event_v2(event)
    canonical = dict(payload)
    for key in ("known_at", "ingested_at"):
        canonical[key] = _utc_text(_parse_utc(payload[key], key))
    for field in _EVENT_V2_TEMPORAL_FIELDS:
        if payload.get(field) is not None:
            canonical[field] = _canonical_temporal(payload[field], field)
    canonical["revision"] = dict(payload["revision"])
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def event_v2_content_hash(event: Mapping[str, Any]) -> str:
    """Return ``sha256:<64 hex>`` over :func:`canonical_event_v2_bytes`."""
    digest = hashlib.sha256(canonical_event_v2_bytes(event)).hexdigest()
    return _sha256_ref(f"sha256:{digest}", "event_v2_content_hash")
