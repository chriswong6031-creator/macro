"""Dual-clock and immutable-correction point-in-time tests."""
from __future__ import annotations

from engine.capital_structure.event_spine import (
    build_event_version,
    current_events_as_of,
    make_stable_span,
)


HASH = "c" * 64


def _event(
    accession: str,
    *,
    accepted: str | None,
    seen: str,
    correction_version: int = 1,
    correction_of: str | None = None,
):
    observation = {
        "manifest_id": f"manifest:{accession}:{correction_version}",
        "accession": accession,
        "source_id": accession,
        "issuer_id": "issuer:0000000001",
        "cik": "1",
        "ticker": "ABC",
        "form": "S-3",
        "file_number": "333-123",
        "filing_date": "2020-01-02",
        "accepted_at": accepted,
        "first_seen_at": seen,
        "content_hashes": [HASH],
    }
    span = make_stable_span(observation["manifest_id"], f"v{correction_version}", locator="document")
    return build_event_version(
        observation,
        [span],
        correction_version=correction_version,
        correction_of=correction_of,
    )


def test_backfilled_filing_does_not_leak_into_canonical_system_replay():
    event = _event(
        "0000000001-20-000001",
        accepted="2020-01-02T15:30:00Z",
        seen="2026-08-01T10:00:00Z",
    )
    assert current_events_as_of([event], "2020-01-03T00:00:00Z") == []
    assert current_events_as_of([event], "2026-08-01T10:00:00Z") == [event]


def test_public_mode_is_explicit_and_uses_acceptance_not_filing_midnight():
    event = _event(
        "0000000001-20-000001",
        accepted="2020-01-02T15:30:00Z",
        seen="2026-08-01T10:00:00Z",
    )
    assert current_events_as_of([event], "2020-01-02T15:29:59Z", mode="public") == []
    assert current_events_as_of([event], "2020-01-02T15:30:00Z", mode="public") == [event]


def test_public_mode_excludes_unknown_acceptance_instead_of_guessing():
    event = _event("0000000001-20-000001", accepted=None, seen="2026-08-01T10:00:00Z")
    assert current_events_as_of([event], "2026-08-02T00:00:00Z", mode="public") == []
    assert current_events_as_of([event], "2026-08-02T00:00:00Z", mode="system") == [event]


def test_correction_appears_only_when_produced_in_both_modes():
    original = _event(
        "0000000001-20-000001",
        accepted="2020-01-02T15:30:00Z",
        seen="2026-08-01T10:00:00Z",
    )
    correction = _event(
        "0000000001-20-000001",
        accepted="2020-01-02T15:30:00Z",
        seen="2026-08-03T10:00:00Z",
        correction_version=2,
        correction_of=original["event_id"],
    )
    assert current_events_as_of([original, correction], "2026-08-02T00:00:00Z") == [original]
    assert current_events_as_of([original, correction], "2026-08-02T00:00:00Z", mode="public") == [original]
    assert current_events_as_of([original, correction], "2026-08-03T10:00:00Z") == [correction]
    assert current_events_as_of([original, correction], "2026-08-03T10:00:00Z", mode="public") == [correction]


def test_as_of_returns_latest_version_per_accession_not_every_correction():
    original = _event(
        "0000000001-20-000001", accepted="2020-01-02T15:30:00Z", seen="2026-08-01T10:00:00Z"
    )
    correction = _event(
        "0000000001-20-000001", accepted="2020-01-02T15:30:00Z", seen="2026-08-03T10:00:00Z",
        correction_version=2, correction_of=original["event_id"],
    )
    other = _event(
        "0000000001-20-000002", accepted="2020-01-04T15:30:00Z", seen="2026-08-02T10:00:00Z"
    )
    current = current_events_as_of([correction, other, original], "2026-08-04T00:00:00Z")
    assert {event["event_id"] for event in current} == {correction["event_id"], other["event_id"]}


def test_naive_as_of_is_rejected():
    event = _event(
        "0000000001-20-000001", accepted="2020-01-02T15:30:00Z", seen="2026-08-01T10:00:00Z"
    )
    try:
        current_events_as_of([event], "2026-08-02T00:00:00")
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("naive PIT cutoff was accepted")
