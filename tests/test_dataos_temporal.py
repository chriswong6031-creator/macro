"""Temporal model + the fail-closed PIT law (Data OS §D3) — ``lib/dataos/temporal.py``.

The defect this suite pins is not an exception anyone has seen: it is the SILENT
latest-vintage return.  A store with no ``known_at`` clock answers an as-of read with
today's revised number, the backtest scores beautifully, and nothing goes red.  Every
test below is therefore about something REFUSING rather than something returning.

Pure unit tests — the clock is injected everywhere, nothing reads ``data/``.

Run: .venv/bin/python -m pytest tests/test_dataos_temporal.py -q
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lib.dataos.temporal import (
    INSTANT_CLOCKS,
    INTERVAL_CLOCKS,
    KNOWN_AT_CLOCKS,
    Clock,
    PointInTimeError,
    TemporalError,
    TemporalProfile,
    as_of_filter,
    assert_pit_readable,
    known_at,
    pit_refusal_reason,
    utc,
)

EAST = timezone(timedelta(hours=-5))


# ── utc(): refuse to guess ───────────────────────────────────────────────────
def test_utc_raises_on_a_naive_datetime_instead_of_assuming_a_timezone() -> None:
    """CI runs UTC and the operator works US-eastern evenings, so the SAME naive
    stamp means two different instants depending on which machine wrote it."""
    with pytest.raises(TemporalError, match="naive datetime"):
        utc(datetime(2026, 8, 12, 9, 30))


def test_utc_raises_on_a_naive_iso_string_too() -> None:
    with pytest.raises(TemporalError, match="naive datetime"):
        utc("2026-08-12T09:30:00")


def test_utc_raises_on_a_bare_date_because_a_date_has_no_timezone() -> None:
    with pytest.raises(TemporalError):
        utc("2026-08-12")


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 8, 12, 14, 30, tzinfo=timezone.utc),
        "2026-08-12T14:30:00+00:00",
        "2026-08-12T14:30:00Z",
        datetime(2026, 8, 12, 9, 30, tzinfo=EAST),
        "2026-08-12T09:30:00-05:00",
    ],
)
def test_utc_normalizes_every_offset_bearing_form_to_the_same_instant(value) -> None:
    assert utc(value) == datetime(2026, 8, 12, 14, 30, tzinfo=timezone.utc)
    assert utc(value).tzinfo is timezone.utc


@pytest.mark.parametrize("bad", ["", "   ", "not-a-time", 12345, None])
def test_utc_raises_on_unusable_input(bad) -> None:
    with pytest.raises(TemporalError):
        utc(bad)


# ── the clock/profile vocabulary ─────────────────────────────────────────────
def test_the_interval_label_is_not_counted_among_the_instants() -> None:
    """``period_start``/``period_end`` describe an interval; nobody learned anything
    at a bar's period_end."""
    assert INTERVAL_CLOCKS == {Clock.PERIOD_START, Clock.PERIOD_END}
    assert len(INSTANT_CLOCKS) == 6
    assert INSTANT_CLOCKS.isdisjoint(INTERVAL_CLOCKS)
    assert INSTANT_CLOCKS | INTERVAL_CLOCKS == set(Clock)


def test_a_clock_value_is_its_column_name() -> None:
    assert Clock.PUBLISHED_AT == "published_at"
    assert Clock.INGESTED_AT.value == "ingested_at"


@pytest.mark.parametrize(
    "profile, required",
    [
        (TemporalProfile.BARS, {Clock.PERIOD_START, Clock.PERIOD_END, Clock.INGESTED_AT}),
        (TemporalProfile.REVISABLE_RELEASE,
         {Clock.PERIOD_END, Clock.PUBLISHED_AT, Clock.INGESTED_AT}),
        (TemporalProfile.SNAPSHOT_SERIES, {Clock.EFFECTIVE_AT, Clock.INGESTED_AT}),
        (TemporalProfile.EVENT, {Clock.EVENT_AT, Clock.PUBLISHED_AT, Clock.INGESTED_AT}),
        (TemporalProfile.DERIVED, {Clock.COMPUTED_AT}),
        (TemporalProfile.INTELLIGENCE, {Clock.COMPUTED_AT, Clock.SERVED_AT}),
    ],
)
def test_each_profile_declares_exactly_the_spec_clocks(profile, required) -> None:
    assert profile.required_clocks == required


def test_the_non_clock_obligations_live_beside_the_clocks_not_inside_them() -> None:
    assert "revision_seq" in TemporalProfile.REVISABLE_RELEASE.required_fields
    assert "code_version" in TemporalProfile.DERIVED.required_fields
    assert {"data_cutoff_at", "expires_at"} <= TemporalProfile.INTELLIGENCE.required_fields
    assert not set(TemporalProfile.REVISABLE_RELEASE.required_fields) & {c.value for c in Clock}


def test_every_profile_has_a_known_at_declaration() -> None:
    assert set(KNOWN_AT_CLOCKS) == set(TemporalProfile)


# ── assert_pit_readable: the fail-closed law ─────────────────────────────────
@pytest.mark.parametrize(
    "profile",
    [TemporalProfile.BARS, TemporalProfile.REVISABLE_RELEASE,
     TemporalProfile.SNAPSHOT_SERIES, TemporalProfile.EVENT,
     TemporalProfile.INTELLIGENCE],
)
def test_assert_pit_readable_passes_for_a_profile_that_carries_a_known_at_clock(profile) -> None:
    assert assert_pit_readable(profile) is None
    assert profile.pit_readable
    assert pit_refusal_reason(profile) is None


def test_assert_pit_readable_raises_for_derived_which_has_no_known_at_clock() -> None:
    """DERIVED is RECOMPUTABLE, not REPLAYABLE — serving an as-of read from it is the
    current-rule recomputation the Calcbench reproduce!=replay ruling names."""
    with pytest.raises(PointInTimeError) as exc:
        assert_pit_readable(TemporalProfile.DERIVED)
    message = str(exc.value)
    assert "DERIVED" in message
    assert "RECOMPUTABLE" in message or "recompute" in message
    assert not TemporalProfile.DERIVED.pit_readable


def test_the_refusal_carries_a_reason_not_just_a_verdict() -> None:
    reason = pit_refusal_reason(TemporalProfile.DERIVED)
    assert reason and len(reason) > 40
    assert "INTELLIGENCE" in reason      # names the actual next move


# ── known_at: coalesce(published_at, ingested_at) ────────────────────────────
PUBLISHED = datetime(2026, 8, 10, 12, 30, tzinfo=timezone.utc)
INGESTED = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)


def test_known_at_prefers_published_at_over_ingested_at() -> None:
    row = {"published_at": PUBLISHED, "ingested_at": INGESTED, "value": 1.0}
    assert known_at(row, TemporalProfile.REVISABLE_RELEASE) == PUBLISHED


def test_known_at_falls_back_to_ingested_at_when_the_source_never_said() -> None:
    row = {"ingested_at": INGESTED, "value": 1.0}
    assert known_at(row, TemporalProfile.BARS) == INGESTED


def test_known_at_accepts_iso_strings_and_normalizes_them() -> None:
    row = {"published_at": "2026-08-10T07:30:00-05:00"}
    assert known_at(row, TemporalProfile.EVENT) == PUBLISHED


def test_intelligence_answers_known_at_with_its_replay_clock() -> None:
    served = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)
    row = {"computed_at": PUBLISHED, "served_at": served}
    assert known_at(row, TemporalProfile.INTELLIGENCE) == served


def test_a_row_that_cannot_say_when_it_became_knowable_raises() -> None:
    """Neither silently included (leakage) nor silently dropped (an invisible hole)."""
    with pytest.raises(PointInTimeError, match="known_at is unanswerable"):
        known_at({"value": 1.0, "period_end": PUBLISHED}, TemporalProfile.BARS)


def test_known_at_refuses_before_it_looks_at_the_row_for_a_non_pit_profile() -> None:
    with pytest.raises(PointInTimeError):
        known_at({"published_at": PUBLISHED}, TemporalProfile.DERIVED)


# ── as_of_filter ─────────────────────────────────────────────────────────────
ROWS = [
    {"series": "CPIAUCSL", "period_end": "2026-05-31T00:00:00+00:00",
     "value": 100.0, "published_at": "2026-06-10T12:30:00+00:00",
     "ingested_at": "2026-06-10T13:00:00+00:00", "revision_seq": 0},
    {"series": "CPIAUCSL", "period_end": "2026-05-31T00:00:00+00:00",
     "value": 100.4, "published_at": "2026-07-10T12:30:00+00:00",
     "ingested_at": "2026-07-10T13:00:00+00:00", "revision_seq": 1},
    {"series": "CPIAUCSL", "period_end": "2026-06-30T00:00:00+00:00",
     "value": 101.0, "published_at": "2026-07-10T12:30:00+00:00",
     "ingested_at": "2026-07-10T13:00:00+00:00", "revision_seq": 0},
]


def test_as_of_filter_hides_the_revision_that_had_not_happened_yet() -> None:
    """The whole point: on 2026-06-15, May CPI is 100.0 — the revision to 100.4 does
    not exist for another month, and a latest-vintage read would leak it."""
    seen = as_of_filter(ROWS, "2026-06-15T00:00:00+00:00", TemporalProfile.REVISABLE_RELEASE)
    assert [r["value"] for r in seen] == [100.0]

    later = as_of_filter(ROWS, "2026-07-15T00:00:00+00:00", TemporalProfile.REVISABLE_RELEASE)
    assert [r["value"] for r in later] == [100.0, 100.4, 101.0]


def test_as_of_filter_is_inclusive_at_the_boundary_instant() -> None:
    at_publication = as_of_filter(
        ROWS, "2026-06-10T12:30:00+00:00", TemporalProfile.REVISABLE_RELEASE
    )
    assert len(at_publication) == 1


def test_as_of_filter_is_pure_and_returns_plain_dicts() -> None:
    before = [dict(r) for r in ROWS]
    out = as_of_filter(ROWS, "2026-07-15T00:00:00+00:00", TemporalProfile.REVISABLE_RELEASE)
    assert ROWS == before                      # inputs untouched
    assert all(isinstance(r, dict) for r in out)
    out[0]["value"] = -1
    assert ROWS[0]["value"] == 100.0           # outputs are copies, not aliases


def test_as_of_filter_refuses_a_non_pit_profile_before_touching_a_row() -> None:
    with pytest.raises(PointInTimeError):
        as_of_filter(ROWS, "2026-07-15T00:00:00+00:00", TemporalProfile.DERIVED)


def test_as_of_filter_refuses_a_naive_cutoff() -> None:
    with pytest.raises(TemporalError):
        as_of_filter(ROWS, datetime(2026, 7, 15), TemporalProfile.REVISABLE_RELEASE)


def test_an_empty_input_is_an_empty_output_not_an_error() -> None:
    assert as_of_filter([], "2026-07-15T00:00:00+00:00", TemporalProfile.BARS) == []
