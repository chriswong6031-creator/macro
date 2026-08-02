"""Time-aware health evaluation for Government Revenue context consumers.

Serialized status is only the state at build time. Long-lived static artifacts
must age conservatively even when a quiet or failed collector run publishes no
replacement. This module is deliberately descriptive: it can suppress context,
never create a score, candidate, forecast, or authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_STATUS_RANK = {
    "ok": 0,
    "unavailable": 0,  # An absent optional rail is handled by its own consumer.
    "partial": 1,
    "blocked": 2,
    "stale": 2,
    "failed": 3,
    "unknown": 3,
}

def _instant(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _reference(value: Any | None) -> datetime:
    return _instant(value) or datetime.now(timezone.utc)


def _aged_status(
    rail: dict[str, Any],
    *,
    reference: datetime,
    observed_keys: tuple[str, ...],
    sla_key: str,
    unit_seconds: float,
) -> str:
    status = str(rail.get("status") or "unknown").strip().lower()
    if status != "ok":
        return status
    observed = next((_instant(rail.get(key)) for key in observed_keys if rail.get(key)), None)
    try:
        sla = float(rail.get(sla_key))
    except (TypeError, ValueError):
        return "unknown"
    if observed is None or sla <= 0:
        return "unknown"
    age_seconds = (reference - observed).total_seconds()
    if age_seconds < 0:
        return "unknown"
    threshold = sla * unit_seconds
    if age_seconds > threshold * 2:
        return "stale"
    if age_seconds > threshold:
        return "partial"
    return "ok"


def _award_event_contract_status(
    payload: dict[str, Any],
    rail: dict[str, Any],
    status: str,
) -> str:
    """Keep the award-event rail fail-closed without conflating scope and age.

    The collector deliberately distinguishes a complete *declared bounded
    sample* from full USAspending corpus exhaustion.  A false
    ``source_exhausted`` and a declared page-cap stop are normal coverage
    metadata; a missing or false bounded-sample proof is not.  There is no
    implicit legacy bypass: without a versioned migration receipt, an envelope
    with every marker stripped is indistinguishable from corruption.
    """

    if status != "ok":
        return status
    bounded = rail.get("bounded_sample_complete")
    exhausted = rail.get("source_exhausted")
    truncated = rail.get("truncated_by_safety_cap")
    manifest_id = rail.get("coverage_manifest_id")
    manifest = rail.get("coverage_manifest")
    if (
        not isinstance(bounded, bool)
        or not isinstance(exhausted, bool)
        or not isinstance(truncated, bool)
        or not isinstance(manifest_id, str)
        or not manifest_id
        or not isinstance(manifest, dict)
        or not manifest
    ):
        return "partial"
    if bounded is not True:
        return "partial"
    return "ok"


def effective_freshness(payload: dict[str, Any], *, reference: Any | None = None) -> dict[str, Any]:
    """Return elapsed-time-aware overall and per-rail health.

    Optional rails serialized as ``unavailable`` do not sink otherwise current
    award context, but their own opportunity facts remain unavailable. A rail
    claiming ``ok`` without a usable observation clock/SLA fails closed.
    """
    freshness = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
    reference_at = _reference(reference)
    serialized_status = str(freshness.get("status") or "unknown").strip().lower()

    rail_specs = {
        "aggregate": (("known_at", "observed_at"), "freshness_sla_days", 86_400.0),
        "award_detail": (
            ("observed_at", "last_successful_observed_at"),
            "freshness_sla_days",
            86_400.0,
        ),
        "actions": (
            ("observed_at", "last_successful_observed_at"),
            "freshness_sla_days",
            86_400.0,
        ),
        "opportunities": (
            ("observed_at", "last_good_at"),
            "freshness_sla_minutes",
            60.0,
        ),
        "award_events": (
            ("observed_at", "known_at"),
            "freshness_sla_days",
            86_400.0,
        ),
    }
    rails: dict[str, str] = {}
    for name, (observed_keys, sla_key, unit_seconds) in rail_specs.items():
        rail = freshness.get(name)
        if not isinstance(rail, dict):
            rails[name] = "unknown"
            continue
        status = _aged_status(
            rail,
            reference=reference_at,
            observed_keys=observed_keys,
            sla_key=sla_key,
            unit_seconds=unit_seconds,
        )
        rails[name] = (
            _award_event_contract_status(payload, rail, status)
            if name == "award_events"
            else status
        )

    candidates = [serialized_status]
    for name, status in rails.items():
        # SAM is optional until activated; unavailable means suppress that rail,
        # not fresh USAspending facts. Opportunity health is always rail-local:
        # stale/blocked SAM suppresses opportunity candidates, not official award
        # history. The same applies to explicitly unavailable aggregate/detail
        # rails whose serialized overall contract remains honest.
        if name not in {"opportunities", "award_events"} and status != "unavailable":
            candidates.append(status)
    overall = max(candidates, key=lambda status: _STATUS_RANK.get(status, 3))
    return {
        "status": overall,
        "serialized_status": serialized_status,
        "opportunities": rails["opportunities"],
        "award_events": rails["award_events"],
        "rails": rails,
        "evaluated_at": reference_at.isoformat(),
    }


__all__ = ["effective_freshness"]
