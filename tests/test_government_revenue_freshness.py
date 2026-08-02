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
            "award_events": {
                "status": "ok", "observed_at": observed, "freshness_sla_days": 4,
                "bounded_sample_complete": True,
                "source_exhausted": False,
                "truncated_by_safety_cap": False,
                "coverage_manifest_id": "award-coverage-" + "a" * 64,
                "coverage_manifest": {"schema_version": "test", "entities": []},
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


def test_award_event_tape_ages_locally_without_hiding_other_award_context() -> None:
    partial = effective_freshness(
        _payload(), reference="2026-08-05T11:00:00Z"
    )
    assert partial["award_events"] == "partial"

    payload = _payload()
    payload["freshness"]["award_events"]["observed_at"] = "2026-07-01T10:00:00Z"
    evaluated = effective_freshness(payload, reference="2026-08-01T11:00:00Z")
    assert evaluated["award_events"] == "stale"
    assert evaluated["status"] == "ok"


def test_award_event_ok_status_requires_bounded_sample_proof_not_corpus_exhaustion() -> None:
    payload = _payload()
    payload["freshness"]["award_events"]["bounded_sample_complete"] = False

    incomplete = effective_freshness(payload, reference="2026-08-01T11:00:00Z")

    assert incomplete["award_events"] == "partial"
    assert incomplete["status"] == "ok"

    payload = _payload()
    payload["freshness"]["award_events"]["truncated_by_safety_cap"] = True
    capped = effective_freshness(payload, reference="2026-08-01T11:00:00Z")

    assert capped["award_events"] == "ok"
    assert capped["status"] == "ok"


def test_stripped_award_event_contract_markers_fail_closed_without_migration_receipt() -> None:
    fields = (
        "bounded_sample_complete",
        "source_exhausted",
        "truncated_by_safety_cap",
        "coverage_manifest_id",
        "coverage_manifest",
    )
    legacy = _payload()
    for field in fields:
        legacy["freshness"]["award_events"].pop(field)
    legacy["procurement_workspace"] = {
        "freshness": {"award_events": {"status": "ok"}},
    }

    assert effective_freshness(legacy, reference="2026-08-01T11:00:00Z")["award_events"] == "partial"

    manifest_era = _payload()
    for field in fields:
        manifest_era["freshness"]["award_events"].pop(field)
    manifest_era["procurement_workspace"] = {
        "freshness": {"award_events": {"bounded_sample_complete": True}},
    }

    assert effective_freshness(
        manifest_era, reference="2026-08-01T11:00:00Z"
    )["award_events"] == "partial"


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
