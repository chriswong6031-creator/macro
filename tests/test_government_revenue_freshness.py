"""Elapsed-time health contracts for static Government Revenue artifacts."""
from __future__ import annotations

from engine.government_revenue.freshness import effective_freshness


def _payload(opportunity_status: str = "ok") -> dict:
    observed = "2026-08-01T10:00:00Z"
    return {
        "freshness": {
            "status": "ok",
            "aggregate": {
                "status": "ok", "known_at": observed, "freshness_sla_days": 35,
            },
            "award_detail": {
                "status": "ok", "observed_at": observed, "freshness_sla_days": 4,
            },
            "actions": {
                "status": "ok", "observed_at": observed, "freshness_sla_days": 4,
            },
            "opportunities": {
                "status": opportunity_status,
                "observed_at": observed if opportunity_status != "unavailable" else None,
                "freshness_sla_minutes": 90,
            },
        }
    }


def test_optional_opportunity_rail_ages_without_sinking_fresh_awards() -> None:
    assert effective_freshness(
        _payload(), reference="2026-08-01T11:00:00Z"
    )["status"] == "ok"
    partial = effective_freshness(
        _payload(), reference="2026-08-01T11:40:00Z"
    )
    assert partial["status"] == "ok"
    assert partial["opportunities"] == "partial"
    evaluated = effective_freshness(
        _payload(), reference="2026-08-01T13:10:00Z"
    )
    assert evaluated["status"] == "ok"
    assert evaluated["opportunities"] == "stale"


def test_once_ok_award_rails_age_partial_then_stale() -> None:
    assert effective_freshness(
        _payload(), reference="2026-08-05T11:00:00Z"
    )["status"] == "partial"
    assert effective_freshness(
        _payload(), reference="2026-08-10T11:00:00Z"
    )["status"] == "stale"


def test_unavailable_optional_sam_rail_does_not_hide_fresh_award_context() -> None:
    evaluated = effective_freshness(
        _payload("unavailable"), reference="2026-08-01T11:00:00Z"
    )

    assert evaluated["status"] == "ok"
    assert evaluated["opportunities"] == "unavailable"


def test_claimed_ok_rail_without_clock_or_sla_fails_closed() -> None:
    payload = _payload()
    payload["freshness"]["opportunities"] = {"status": "ok"}

    evaluated = effective_freshness(payload, reference="2026-08-01T11:00:00Z")

    assert evaluated["status"] == "ok"
    assert evaluated["opportunities"] == "unknown"
