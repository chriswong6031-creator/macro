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


# ═══════════════════════════════════════════════════════════════════════════
# neuralweb.biopharma_seasonality_state.v2 — the multi-clock state
# ═══════════════════════════════════════════════════════════════════════════
#
# Appended as a self-contained block on purpose: every v1 symbol above is
# byte-identical, so "v2 is additive" is checkable with ``git diff`` rather
# than asserted in a docstring.
#
# WHY A SECOND SCHEMA RATHER THAN A WIDER v1
# -------------------------------------------
# ``v1.forecast.p`` is, and has always been, a *historical positive-year
# share*: the fraction of complete years in which this calendar window finished
# up.  It is not a calibrated probability, it was never fitted, and it carries
# no data cutoff.  The dangerous migration — the one this file exists to make
# impossible — is a later session that fits a model and writes its output into
# ``forecast.p`` because the field is already there, already plumbed, and
# already named ``p``.  Every downstream reader would silently reinterpret a
# frequency as a forecast, and nothing in the payload would record that the
# meaning changed.
#
# So v2 does three structural things, none of which is a comment:
#
# 1. It **has no ``forecast`` key at all** (:data:`_V2_FORBIDDEN_TOP_KEYS`).
#    The old name is not deprecated, it is absent — there is nowhere to write.
# 2. The v1 semantic is renamed to what it actually is,
#    ``historical_up_share``, and that object is *defined* as a realized
#    frequency: it carries ``n_years`` and a ``basis``, and it is not
#    permitted to carry a model version or a data cutoff, because a realized
#    frequency does not have either.
# 3. Any estimate that IS fitted lives in ``calibrated_estimate``, a
#    separately named and separately typed object that cannot exist without
#    ``calibration_version``, ``model_version``, and ``data_cutoff``
#    simultaneously.  A loosely-filled calibrated estimate is a
#    :class:`ContractError`, not a warning.
#
# ``clocks`` is a list because a name can be on more than one clock at once
# (a December calendar window AND a PDUFA date AND a regime phase), and a
# single ``clock`` object forced the producer to pick one and drop the rest.
# Types are unique within the list so a consumer projecting "the calendar
# clock" gets a deterministic answer rather than a first-match lottery.
#
# ``contradiction`` and ``overlap`` are MEASUREMENT slots, not verdict slots:
# both carry an explicit unavailable state, because the failure this program
# has already seen is a hook whose silence read as "checked, nothing found".

NEURALWEB_STATE_V2_SCHEMA = "neuralweb.biopharma_seasonality_state.v2"

#: Estimate kinds ``calibrated_estimate`` may declare.  Closed on purpose: a
#: reader must never have to guess whether ``value`` is a probability or a
#: return.
_ESTIMATE_KINDS = frozenset({"probability", "expectation", "quantiles", "distribution"})

#: How an interval on a calibrated estimate must describe itself.  A parameter
#: CI (how well do we know the mean) and a predictive interval (where will the
#: next outcome land) are different objects that plot identically, and a payload
#: that says only "interval" has already lost the distinction.
_UNCERTAINTY_KINDS = frozenset({"parameter_ci", "predictive_interval", "outcome_quantiles"})

#: Generic labels banned wherever an interval is described.  ``interval`` is
#: exactly the word that lets the two meanings above collapse into one.
_FORBIDDEN_UNCERTAINTY_LABELS = frozenset({"interval", "ci", "band", "range", "uncertainty"})

#: The ONLY keys ``calibrated_estimate`` may carry.  Closed, not blacklisted.
#:
#: A blacklist of generic words cannot hold this line: the requirement to name
#: an interval's kind can be dodged by spelling the interval ``ci95``,
#: ``credible_interval``, ``lower``/``upper``, ``p05``/``p95``, or
#: ``stderr``/``sigma`` — six spellings of one object, none of them the banned
#: word, each of them an interval whose meaning the payload never states.  So
#: the vocabulary is closed instead: ``ci90`` is the one interval shape, it
#: carries ``uncertainty_kind``, and every other spelling is refused BY NAME
#: rather than tested against a list of words someone thought of in advance.
_CALIBRATED_ESTIMATE_KEYS = frozenset(
    {
        "kind",
        "value",
        "quantiles",
        "distribution",
        "baseline",
        "edge",
        "ci90",
        "uncertainty_kind",
        "calibration_version",
        "model_version",
        "data_cutoff",
    }
)

#: Keys a v2 state may never carry.  ``forecast`` is the frozen v1 name; the
#: rest are the fused-score vocabulary seasonality is not allowed to compute.
_V2_FORBIDDEN_TOP_KEYS = frozenset(
    {
        "forecast",
        "score",
        "combined_score",
        "weight",
        "combined_weight",
        "discount",
        "rank",
        "conviction",
        "size",
    }
)

#: Keys ``historical_up_share`` may never carry.  A realized frequency has no
#: model and no cutoff; a payload that gives it one is describing something
#: else under an honest object's name.
_HISTORICAL_FORBIDDEN_KEYS = frozenset(
    {"model_version", "calibration_version", "data_cutoff", "calibrated"}
)


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError(f"{field} must be a finite number")
    return number


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"{field} must be a list of strings")
    return list(value)


def _reject_generic_uncertainty_labels(payload: Mapping[str, Any], field: str) -> None:
    for key in payload:
        if str(key).lower() in _FORBIDDEN_UNCERTAINTY_LABELS:
            raise ContractError(
                f"{field}.{key} is a generic uncertainty label — name the kind "
                f"explicitly via uncertainty_kind ({sorted(_UNCERTAINTY_KINDS)})"
            )


def _validate_quantile_map(quantiles: Any, field: str) -> None:
    """``{"q05": …, "q50": …, "q95": …}`` — closed labels, monotone in level.

    Labels are a closed ``q<two-digit percentile>`` form rather than free text
    so the levels can be ORDERED, and once they can be ordered the values must
    not cross: a payload whose q05 sits above its q95 is not a wide
    distribution, it is a swapped pair, and it plots as a perfectly ordinary
    fan.

    Exactly two digits, because a longer form is ambiguous rather than more
    precise — ``q100`` reads as both the 100th percentile and the 10.0th, and a
    label whose LEVEL is a guess cannot order anything.
    """
    if not isinstance(quantiles, Mapping) or not quantiles:
        raise ContractError(f"{field} must be a non-empty object")
    levels: list[tuple[float, float]] = []
    for label, value in quantiles.items():
        text = str(label)
        if not (len(text) == 3 and text[0] == "q" and text[1:].isdigit()):
            raise ContractError(
                f"{field}[{label}] label must be 'q' followed by exactly two digits "
                "(q05, q50, q95) so the levels can be ordered — a longer form is "
                "ambiguous, not more precise"
            )
        level = float(text[1:]) / 100.0
        if not 0.0 < level < 1.0:
            raise ContractError(f"{field}[{label}] percentile must lie strictly inside (0, 1)")
        levels.append((level, _finite_number(value, f"{field}[{label}]")))
    levels.sort(key=lambda item: item[0])
    for (lower_level, lower_value), (upper_level, upper_value) in zip(levels, levels[1:]):
        if lower_value > upper_value:
            raise ContractError(
                f"{field} is non-monotone: the {lower_level:.3g} quantile "
                f"({lower_value}) exceeds the {upper_level:.3g} quantile "
                f"({upper_value})"
            )


def _validate_calendar_window(window: Mapping[str, Any], field: str) -> None:
    """The three fields every reader of a calendar clock projects.

    These are not optional decoration.  ``seasonality_state_projection`` reads
    exactly ``start_doy`` / ``end_doy`` / ``occurrence_end_date`` out of the
    calendar clock, and ``state.register_rows`` turns the last of the three into
    a ``date`` to mint the forward-ledger key.  A calendar clock carrying an
    empty window therefore validates, projects a ``p`` with a NULL window (a
    probability about no period), and then takes the whole nightly down inside
    ``date.fromisoformat(None)`` — a contract-valid payload that removes the
    lobe.  So the window is checked where it is written, not where it explodes.
    """
    start = window.get("start_doy")
    end = window.get("end_doy")
    for name, value in (("start_doy", start), ("end_doy", end)):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 366:
            raise ContractError(f"{field}.{name} must be a day-of-year integer in [1, 366]")
    if start >= end:  # type: ignore[operator]
        raise ContractError(
            f"{field}.start_doy must precede {field}.end_doy — the calendar family "
            "does not wrap the year"
        )
    end_date = _require_text(window.get("occurrence_end_date"), f"{field}.occurrence_end_date")
    try:
        # strptime rather than fromisoformat: the ledger key is minted from a
        # pure calendar date, and fromisoformat would also accept a timestamp.
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ContractError(
            f"{field}.occurrence_end_date must be an ISO-8601 calendar date "
            "(it is the forward-ledger occurrence identity)"
        ) from exc


def _validate_clocks(clocks: Any) -> None:
    """A non-empty list of clocks, one per type, each stating its own window.

    Emptiness is refused rather than tolerated: a state with no clock is not a
    weaker seasonality read, it is a state about nothing.

    Exactly one of them must be the ``calendar`` clock, because
    ``historical_up_share`` — which every v2 state is required to carry — IS a
    calendar-window statistic (the share of complete years in which THIS window
    finished up).  A state that publishes that share while declaring no calendar
    clock is a number about a period it never names.
    """
    if not isinstance(clocks, list) or not clocks:
        raise ContractError("clocks must be a non-empty list")
    seen: set[str] = set()
    for position, clock in enumerate(clocks):
        field = f"clocks[{position}]"
        entry = _require_mapping(clock, field)
        clock_type = entry.get("type")
        if clock_type not in _CLOCK_TYPES:
            raise ContractError(f"{field}.type must be one of {sorted(_CLOCK_TYPES)}")
        if clock_type in seen:
            raise ContractError(
                f"{field}.type {clock_type!r} is declared twice — clock types are "
                "unique so a consumer projecting one clock gets a deterministic answer"
            )
        seen.add(str(clock_type))
        _require_text(entry.get("phase"), f"{field}.phase")
        window = _require_mapping(entry.get("window"), f"{field}.window")
        _require_mapping(entry.get("evidence"), f"{field}.evidence")
        if clock_type == "calendar":
            _validate_calendar_window(window, f"{field}.window")
    if "calendar" not in seen:
        raise ContractError(
            "clocks must include the 'calendar' clock — historical_up_share is a "
            "calendar-window statistic, so the window it measures has to be declared"
        )


def _validate_historical_up_share(share: Mapping[str, Any]) -> None:
    """The v1 ``forecast`` semantic, renamed to what it measures.

    EVERY check :func:`_validate_forecast` makes still runs here — ``target``,
    ``horizon_td``, ``p``, ``p_baseline``, ``edge``, ``ci90`` — so a v1 payload
    and a v2 payload built from one panel cannot disagree about any of them.  A
    rename that quietly drops a check is a loosening wearing a migration's name,
    which is why ``horizon_td`` is validated here even though nothing downstream
    projects it.

    The two intervals this object ships each declare WHICH interval they are,
    under the same closed vocabulary ``calibrated_estimate`` uses.  They are not
    the same kind of object: ``ci90`` is a Wilson interval on the realized share
    (a PARAMETER CI — how well the frequency itself is pinned), while
    ``quantiles`` describes where a single future window's RETURN might land.
    They plot identically and a payload that labels neither has already lost the
    distinction, so both labels are required rather than inferred.
    """
    field = "historical_up_share"
    for key in _HISTORICAL_FORBIDDEN_KEYS:
        if key in share:
            raise ContractError(
                f"{field}.{key} is forbidden — historical_up_share is a realized "
                "frequency, so a model version or a data cutoff means a fitted "
                "estimate was written under its name (use calibrated_estimate)"
            )
    _reject_generic_uncertainty_labels(share, field)
    _require_text(share.get("target"), f"{field}.target")
    horizon = share.get("horizon_td")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ContractError(f"{field}.horizon_td must be a positive integer")
    p = _probability(share.get("p"), f"{field}.p")
    baseline = _probability(share.get("p_baseline"), f"{field}.p_baseline")
    edge = _finite_number(share.get("edge"), f"{field}.edge")
    if not math.isclose(edge, p - baseline, abs_tol=1e-9):
        raise ContractError(f"{field}.edge must equal {field}.p - {field}.p_baseline")
    ci = share.get("ci90")
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        raise ContractError(f"{field}.ci90 must contain [lower, upper]")
    lower = _probability(ci[0], f"{field}.ci90[0]")
    upper = _probability(ci[1], f"{field}.ci90[1]")
    if lower > upper or not lower <= p <= upper:
        raise ContractError(f"{field}.ci90 must be ordered and contain {field}.p")
    if share.get("ci90_kind") != "parameter_ci":
        raise ContractError(
            f"{field}.ci90_kind must be 'parameter_ci' — the Wilson interval on a "
            "realized share bounds the FREQUENCY, not the next outcome, and an "
            "unlabelled interval is the exact ambiguity this schema refuses"
        )
    if share.get("quantiles") is not None:
        _validate_quantile_map(share.get("quantiles"), f"{field}.quantiles")
        if share.get("quantiles_kind") != "outcome_quantiles":
            raise ContractError(
                f"{field}.quantiles_kind must be 'outcome_quantiles' — these are "
                "realized window RETURNS, a different object from the ci90 on p"
            )
    _non_negative_int(share.get("n_years"), f"{field}.n_years")
    _require_text(share.get("basis"), f"{field}.basis")


def _validate_calibrated_estimate(estimate: Any) -> None:
    """``None``, or a fully-provenanced estimate. There is no middle state.

    The three provenance fields are required TOGETHER because each alone is
    uninterpretable: a model version without a data cutoff cannot be checked
    for leakage, and a cutoff without a calibration version cannot be checked
    for whether the mapping from score to probability was ever fitted.
    """
    if estimate is None:
        return
    field = "calibrated_estimate"
    payload = _require_mapping(estimate, field)

    # Closed vocabulary FIRST, so an unknown key cannot smuggle in an interval
    # under a spelling the checks below never look for.
    unknown = sorted(set(payload) - _CALIBRATED_ESTIMATE_KEYS)
    if unknown:
        raise ContractError(
            f"{field} carries unknown key(s) {unknown} — the vocabulary is closed "
            f"to {sorted(_CALIBRATED_ESTIMATE_KEYS)} so an interval cannot arrive "
            "under a name whose meaning nothing states (ci95, credible_interval, "
            "lower/upper, p05/p95, stderr all describe intervals; use ci90 with "
            "uncertainty_kind)"
        )

    kind = payload.get("kind")
    if kind not in _ESTIMATE_KINDS:
        raise ContractError(f"{field}.kind must be one of {sorted(_ESTIMATE_KINDS)}")

    for key in ("calibration_version", "model_version", "data_cutoff"):
        if key not in payload:
            raise ContractError(
                f"{field}.{key} is required — a calibrated estimate without a "
                "calibration version, a model version, AND a data cutoff cannot "
                "be audited, reproduced, or checked for leakage"
            )
        _require_text(payload.get(key), f"{field}.{key}")

    _reject_generic_uncertainty_labels(payload, field)

    if kind == "quantiles":
        _validate_quantile_map(payload.get("quantiles"), f"{field}.quantiles")
    elif kind == "distribution":
        _require_mapping(payload.get("distribution"), f"{field}.distribution")
    elif kind == "probability":
        _probability(payload.get("value"), f"{field}.value")
    else:  # expectation
        _finite_number(payload.get("value"), f"{field}.value")

    if payload.get("baseline") is not None:
        _finite_number(payload.get("baseline"), f"{field}.baseline")
    if payload.get("edge") is not None:
        _finite_number(payload.get("edge"), f"{field}.edge")

    # An interval that does not say WHICH interval it is is the defect this
    # field exists to prevent, so the requirement is triggered by the presence
    # of interval-shaped content rather than by the producer opting in.
    carries_interval = (
        payload.get("ci90") is not None
        or payload.get("quantiles") is not None
        or kind in {"quantiles", "distribution"}
    )
    uncertainty_kind = payload.get("uncertainty_kind")
    if carries_interval:
        if uncertainty_kind not in _UNCERTAINTY_KINDS:
            raise ContractError(
                f"{field}.uncertainty_kind is required whenever an interval is "
                f"present and must be one of {sorted(_UNCERTAINTY_KINDS)} — a "
                "generic interval label is forbidden"
            )
    elif uncertainty_kind is not None and uncertainty_kind not in _UNCERTAINTY_KINDS:
        raise ContractError(
            f"{field}.uncertainty_kind must be one of {sorted(_UNCERTAINTY_KINDS)}"
        )

    if payload.get("ci90") is not None:
        ci = payload["ci90"]
        if not isinstance(ci, (list, tuple)) or len(ci) != 2:
            raise ContractError(f"{field}.ci90 must contain [lower, upper]")
        # Same arithmetic v1's _validate_forecast applies to its own interval:
        # a probability's interval lives in [0, 1] and CONTAINS the point
        # estimate.  An interval that excludes its own estimate is not a wider
        # read, it is two numbers from different objects printed side by side —
        # and it plots as an ordinary error bar.
        edge_check = _probability if kind == "probability" else _finite_number
        lower = edge_check(ci[0], f"{field}.ci90[0]")
        upper = edge_check(ci[1], f"{field}.ci90[1]")
        if lower > upper:
            raise ContractError(f"{field}.ci90 must be ordered")
        if kind in {"probability", "expectation"}:
            value = _finite_number(payload.get("value"), f"{field}.value")
            if not lower <= value <= upper:
                raise ContractError(f"{field}.ci90 must contain {field}.value")


def _validate_contradiction(contradiction: Mapping[str, Any]) -> None:
    """Measured, or explicitly unavailable — never silent, never asserted.

    ``present: false`` with an empty ``detail`` would be the exact failure this
    slot replaces: an absence that reads as "checked, nothing found" when it
    actually means "never checked".
    """
    field = "contradiction"
    present = contradiction.get("present")
    if not isinstance(present, bool):
        raise ContractError(f"{field}.present must be a boolean")
    between = _string_list(contradiction.get("between"), f"{field}.between")
    _require_text(contradiction.get("detail"), f"{field}.detail")
    if present:
        if len(between) < 2:
            raise ContractError(
                f"{field}.between must name at least two legs when a contradiction is present"
            )
        # A CLAIMED contradiction has to name the artifact that measured it, for
        # the same reason ``overlap`` always carries ``measured_by``: the second
        # leg of this comparison is an event-timing probability whose producer
        # contract has not landed, so "the calendar disagrees with X" is a
        # finding about a measurement someone has to be able to open.  Without
        # it the strongest positive claim in the payload is the only one with no
        # provenance at all.
        _require_text(contradiction.get("measured_by"), f"{field}.measured_by")
    else:
        _require_text(contradiction.get("reason_code"), f"{field}.reason_code")


def _validate_overlap(overlap: Mapping[str, Any]) -> None:
    """Redundancy against existing features, or a named reason it is unmeasured."""
    field = "overlap"
    measured = overlap.get("measured")
    if not isinstance(measured, bool):
        raise ContractError(f"{field}.measured must be a boolean")
    _string_list(overlap.get("measured_against"), f"{field}.measured_against")
    redundancy = overlap.get("redundancy")
    if measured:
        if redundancy is None:
            raise ContractError(f"{field}.redundancy is required when measured is true")
        _finite_number(redundancy, f"{field}.redundancy")
    else:
        if redundancy is not None:
            raise ContractError(
                f"{field}.redundancy must be null when the overlap was not measured "
                "— an unmeasured redundancy is not zero redundancy"
            )
        _require_text(overlap.get("reason_code"), f"{field}.reason_code")
    _require_text(overlap.get("measured_by"), f"{field}.measured_by")


def validate_neuralweb_state_v2(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a multi-clock ``neuralweb.biopharma_seasonality_state.v2`` state.

    The authority ceiling is IDENTICAL to v1 — same :func:`_validate_authority`,
    not a re-implementation — because a schema bump is not an authority grant.
    """
    payload = dict(_require_mapping(state, "state"))
    if payload.get("schema") != NEURALWEB_STATE_V2_SCHEMA:
        raise ContractError(f"schema must be {NEURALWEB_STATE_V2_SCHEMA!r}")

    forbidden = sorted(_V2_FORBIDDEN_TOP_KEYS & set(payload))
    if forbidden:
        raise ContractError(
            f"v2 state carries forbidden key(s) {forbidden}: 'forecast' is the frozen "
            "v1 historical-share name and the rest are fused-score fields seasonality "
            "does not compute"
        )

    if payload.get("tier") not in _STATE_TIERS:
        raise ContractError(f"tier must be one of {sorted(_STATE_TIERS)}")
    if payload.get("is_context_only") is not True:
        raise ContractError("is_context_only must be true")

    entity = _require_mapping(payload.get("entity"), "entity")
    _require_text(entity.get("type"), "entity.type")
    _require_text(entity.get("id"), "entity.id")

    _validate_clocks(payload.get("clocks"))

    available_at = _parse_utc(payload.get("available_at"), "available_at")
    expires_at = _parse_utc(payload.get("expires_at"), "expires_at")
    if expires_at <= available_at:
        raise ContractError("expires_at must be later than available_at")

    # POINT-IN-TIME: ``asof`` is the vintage of the DATA the numbers were folded
    # from, ``available_at`` is when this state came into existence.  Data
    # cannot be older-than-itself and cannot come from after the moment it was
    # read, so an asof past available_at is a look-ahead — the payload claiming
    # it knew, at build time, something that had not happened.  v1 left this
    # unchecked and the only defence was producer-side; a hand-built or
    # third-party state walked straight past it.
    asof_text = _require_text(payload.get("asof"), "asof")
    try:
        asof_date = datetime.strptime(asof_text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError("asof must begin with an ISO-8601 calendar date") from exc
    if asof_date.date() > available_at.date():
        raise ContractError(
            f"asof {asof_text!r} is later than available_at "
            f"{payload.get('available_at')!r} — a state cannot be built from data "
            "that was not yet available when it was built"
        )

    share = _require_mapping(payload.get("historical_up_share"), "historical_up_share")
    _validate_historical_up_share(share)
    if "calibrated_estimate" not in payload:
        raise ContractError(
            "calibrated_estimate is required and must be explicitly null when no "
            "calibrated model exists — an absent key reads as an oversight"
        )
    _validate_calibrated_estimate(payload.get("calibrated_estimate"))
    _validate_contradiction(_require_mapping(payload.get("contradiction"), "contradiction"))
    _validate_overlap(_require_mapping(payload.get("overlap"), "overlap"))

    evidence = _require_mapping(payload.get("evidence"), "evidence")
    for field in ("n_independent", "n_issuers", "n_date_clusters", "live_n"):
        _non_negative_int(evidence.get(field), f"evidence.{field}")
    for field in ("q_by", "p_max_t", "spa_p"):
        if evidence.get(field) is not None:
            _probability(evidence[field], f"evidence.{field}")

    # ONE independence count, written twice.  ``seasonality_state_projection``
    # reads ``historical_up_share.n_years`` for v2 and ``evidence.n_independent``
    # for v1 — the same field from two places — so a producer that wrote
    # different numbers into them would hand the consumer block one count and
    # the forward ledger another, with nothing anywhere recording the split.
    # The independence unit here is one complete year, which is exactly what
    # ``n_independent`` counts, so they must agree or one of them is wrong.
    if share.get("n_years") != evidence.get("n_independent"):
        raise ContractError(
            f"historical_up_share.n_years ({share.get('n_years')!r}) must equal "
            f"evidence.n_independent ({evidence.get('n_independent')!r}) — they are "
            "the same count (one complete year is the independence unit), and a "
            "disagreement makes the projected n_years depend on which key a reader "
            "happens to consult"
        )

    uncertainty = _require_mapping(payload.get("uncertainty"), "uncertainty")
    if not isinstance(uncertainty.get("abstain"), bool):
        raise ContractError("uncertainty.abstain must be a boolean")
    _string_list(uncertainty.get("flags"), "uncertainty.flags")

    _validate_authority(_require_mapping(payload.get("authority"), "authority"))

    provenance = _require_mapping(payload.get("provenance"), "provenance")
    _require_text(provenance.get("model_version"), "provenance.model_version")
    _sha256_ref(provenance.get("pattern_spec_hash"), "provenance.pattern_spec_hash")
    _sha256_ref(provenance.get("data_snapshot"), "provenance.data_snapshot")
    return deepcopy(payload)


def build_neuralweb_state_v2(
    *,
    artifact_id: str,
    entity: Mapping[str, Any],
    asof: str,
    available_at: str,
    expires_at: str,
    clocks: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    historical_up_share: Mapping[str, Any],
    contradiction: Mapping[str, Any],
    overlap: Mapping[str, Any],
    evidence: Mapping[str, Any],
    uncertainty: Mapping[str, Any],
    provenance: Mapping[str, Any],
    calibrated_estimate: Mapping[str, Any] | None = None,
    tier: str = "shadow",
) -> dict[str, Any]:
    """Build a v2 state with the same birth authority ceiling v1 is born with.

    ``calibrated_estimate`` defaults to ``None`` and stays ``None`` unless a
    caller passes a fully-provenanced object — the validator refuses anything
    partial, so the default cannot decay into a half-filled estimate.
    """
    payload = {
        "schema": NEURALWEB_STATE_V2_SCHEMA,
        "artifact_id": artifact_id,
        "entity": dict(entity),
        "asof": asof,
        "available_at": available_at,
        "expires_at": expires_at,
        "tier": tier,
        "is_context_only": True,
        "clocks": [dict(clock) for clock in clocks],
        "historical_up_share": dict(historical_up_share),
        "calibrated_estimate": (
            dict(calibrated_estimate) if calibrated_estimate is not None else None
        ),
        "contradiction": dict(contradiction),
        "overlap": dict(overlap),
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
    return validate_neuralweb_state_v2(payload)


def validate_seasonality_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a v1 OR v2 seasonality state, dispatching on its own ``schema``.

    Dispatch is on the declared schema and nothing else: a payload whose schema
    string is unknown is refused rather than sniffed, because a shape-sniffing
    reader is exactly how a v3 would get half-interpreted by a v2 consumer.
    """
    payload = _require_mapping(state, "state")
    schema = payload.get("schema")
    if schema == NEURALWEB_STATE_SCHEMA:
        return validate_neuralweb_state(payload)
    if schema == NEURALWEB_STATE_V2_SCHEMA:
        return validate_neuralweb_state_v2(payload)
    raise ContractError(
        f"schema must be {NEURALWEB_STATE_SCHEMA!r} or {NEURALWEB_STATE_V2_SCHEMA!r}, "
        f"got {schema!r}"
    )


#: The consumer-facing block keys.  ONE list, shared by every reader, so "the
#: v1 block and the v2 block are equivalent" is a property of the code rather
#: than of two hand-kept projections agreeing by luck.
SEASONALITY_BLOCK_KEYS = (
    "as_of",
    "phase",
    "start_doy",
    "end_doy",
    "occurrence_end_date",
    "p",
    "p_baseline",
    "edge",
    "n_years",
    "live_n",
    "flags",
    "expires_at",
)


def seasonality_state_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    """Project a validated v1 or v2 state onto the shared consumer view.

    Returns ``{"block", "abstain", "expires_at", "ledger"}``:

    * ``block`` — exactly :data:`SEASONALITY_BLOCK_KEYS`, the annotate-only
      context a candidate row carries.  A v1 state and a v2 state built from
      the same panel project to the same block, which is what makes the
      migration a rename rather than a reinterpretation;
    * ``abstain`` / ``expires_at`` — the two control facts a consumer needs to
      decide whether to attach the block at all;
    * ``ledger`` — the forward-outcome identity fields, so the append-only
      ledger keeps one row schema across the schema migration.

    ``p`` is the HISTORICAL up share in both versions and never a calibrated
    value: v2 has no ``forecast`` key to read one from, and
    ``calibrated_estimate`` is deliberately not projected here — a calibrated
    number reaching consumers is a separate, gauntleted decision.
    """
    payload = _require_mapping(state, "state")
    schema = payload.get("schema")
    uncertainty = payload.get("uncertainty") or {}
    evidence = payload.get("evidence") or {}
    provenance = payload.get("provenance") or {}

    if schema == NEURALWEB_STATE_SCHEMA:
        window = dict(payload.get("clock") or {})
        share: Mapping[str, Any] = payload.get("forecast") or {}
        n_years = evidence.get("n_independent")
    elif schema == NEURALWEB_STATE_V2_SCHEMA:
        window = {}
        for clock in payload.get("clocks") or ():
            if isinstance(clock, Mapping) and clock.get("type") == "calendar":
                window = {**dict(clock.get("window") or {}), "phase": clock.get("phase")}
                break
        share = payload.get("historical_up_share") or {}
        # ONE source: the validator pins historical_up_share.n_years ==
        # evidence.n_independent, so this cannot depend on which key is read.
        n_years = share.get("n_years")
    else:
        raise ContractError(f"cannot project an unknown seasonality schema {schema!r}")

    block = {
        "as_of": payload.get("asof"),
        "phase": window.get("phase"),
        "start_doy": window.get("start_doy"),
        "end_doy": window.get("end_doy"),
        "occurrence_end_date": window.get("occurrence_end_date"),
        "p": share.get("p"),
        "p_baseline": share.get("p_baseline"),
        "edge": share.get("edge"),
        "n_years": n_years,
        "live_n": evidence.get("live_n"),
        # The FULL flag list, never a filtered one: the flags are the honesty
        # of this block, and a trimmed list reads as a cleaner finding than the
        # lobe actually has.
        "flags": list(uncertainty.get("flags") or []),
        "expires_at": payload.get("expires_at"),
    }
    return {
        "block": {key: block[key] for key in SEASONALITY_BLOCK_KEYS},
        "abstain": bool(uncertainty.get("abstain")),
        "expires_at": payload.get("expires_at"),
        "ledger": {
            "start_doy": window.get("start_doy"),
            "end_doy": window.get("end_doy"),
            "occurrence_end_date": window.get("occurrence_end_date"),
            "p": share.get("p"),
            "p_baseline": share.get("p_baseline"),
            "n_years": n_years,
            "pattern_spec_hash": provenance.get("pattern_spec_hash"),
            "model_version": provenance.get("model_version"),
        },
    }
