"""Tests for lib/nyse_calendar.py — the exchange-calendar freshness reference.

Pins the rule arithmetic against known dates (incl. the 2026-07-07 incident window:
July-4 observed Friday 07-03, Monday 07-06 a session) and the NYSE-specific edge cases
(Saturday New Year NOT observed early; Juneteenth Sun->Mon; one-off mourning closures).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from lib import nyse_calendar as cal


def test_2026_holiday_slate():
    expected = {
        date(2026, 1, 1),    # New Year (Thursday)
        date(2026, 1, 19),   # MLK — 3rd Mon Jan
        date(2026, 2, 16),   # Washington's Birthday — 3rd Mon Feb
        date(2026, 4, 3),    # Good Friday (Easter 2026-04-05)
        date(2026, 5, 25),   # Memorial Day — last Mon May
        date(2026, 6, 19),   # Juneteenth (Friday)
        date(2026, 7, 3),    # Independence Day observed (Jul 4 = Saturday)
        date(2026, 9, 7),    # Labor Day — 1st Mon Sep
        date(2026, 11, 26),  # Thanksgiving — 4th Thu Nov
        date(2026, 12, 25),  # Christmas (Friday)
    }
    assert cal.holidays(2026) == frozenset(expected)


def test_incident_window_sessions():
    """2026-07-02 (Thu) traded; 07-03 holiday; 07-04/05 weekend; 07-06 (Mon) traded."""
    assert cal.is_session(date(2026, 7, 2))
    assert not cal.is_session(date(2026, 7, 3))
    assert not cal.is_session(date(2026, 7, 4))
    assert not cal.is_session(date(2026, 7, 5))
    assert cal.is_session(date(2026, 7, 6))


def test_saturday_new_year_not_observed_early():
    """NYSE does not move a Saturday Jan 1 to Friday: 2021-12-31 was a full session."""
    assert cal.is_session(date(2021, 12, 31))
    assert date(2021, 12, 31) not in cal.holidays(2021)
    # but a Sunday Jan 1 IS observed on Monday (2023-01-02)
    assert not cal.is_session(date(2023, 1, 2))


def test_juneteenth_observance_and_start_year():
    assert not cal.is_session(date(2022, 6, 20))   # 2022: Jun 19 Sunday -> Monday observed
    assert cal.is_session(date(2021, 6, 18))       # 2021: NYSE did not yet observe Juneteenth


def test_one_off_closures():
    assert not cal.is_session(date(2025, 1, 9))    # Carter mourning
    assert not cal.is_session(date(2018, 12, 5))   # Bush mourning


def test_expected_last_session_incident_replay():
    """At the incident engine run (06:01 UTC Tue 07-07) the store should hold Mon 07-06."""
    t = datetime(2026, 7, 7, 6, 1, tzinfo=timezone.utc)
    assert cal.expected_last_session(t) == date(2026, 7, 6)


def test_expected_last_session_before_close_plus_settle():
    """Mid-session Monday (19:00 UTC = 15:00 ET) the last COMPLETED session is still
    Thursday 07-02 (Friday was the observed holiday)."""
    t = datetime(2026, 7, 6, 19, 0, tzinfo=timezone.utc)
    assert cal.expected_last_session(t) == date(2026, 7, 2)


def test_expected_last_session_settle_buffer_edge():
    """20:59 UTC Monday (16:59 ET) is inside the settle buffer -> prior session;
    21:00 UTC (17:00 ET) expects Monday's own bar."""
    assert cal.expected_last_session(
        datetime(2026, 7, 6, 20, 59, tzinfo=timezone.utc)) == date(2026, 7, 2)
    assert cal.expected_last_session(
        datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc)) == date(2026, 7, 6)


def test_expected_last_session_weekend_and_naive_utc():
    """Saturday always expects Friday's (or the last pre-weekend) session; naive
    datetimes are taken as UTC."""
    assert cal.expected_last_session(
        datetime(2026, 7, 4, 12, 0)) == date(2026, 7, 2)  # Sat of the holiday weekend
    assert cal.expected_last_session(
        datetime(2026, 3, 14, 12, 0)) == date(2026, 3, 13)  # ordinary Saturday -> Friday


def test_sessions_between_skips_weekend_and_holiday():
    """The inclusive range drops Fri 07-03 (July-4 observed) and the weekend."""
    assert cal.sessions_between(date(2026, 7, 1), date(2026, 7, 8)) == [
        date(2026, 7, 1), date(2026, 7, 2),
        date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8),
    ]


def test_sessions_between_degenerate_ranges():
    assert cal.sessions_between(date(2026, 7, 8), date(2026, 7, 1)) == []   # start > end
    assert cal.sessions_between(date(2026, 7, 6), date(2026, 7, 6)) == [date(2026, 7, 6)]
    assert cal.sessions_between(date(2026, 7, 4), date(2026, 7, 5)) == []   # weekend only


def test_sessions_behind_counts_real_sessions():
    """Thu 2026-07-16 16:00 ET is inside the settle buffer -> expects Wed 07-15.

    Pins the SLA ladder the flow/radar builders gate on: a store two sessions
    back is still inside a >2 SLA, three sessions back trips it."""
    now = datetime(2026, 7, 16, 20, 0, tzinfo=timezone.utc)  # 16:00 ET
    assert cal.expected_last_session(now) == date(2026, 7, 15)
    assert cal.sessions_behind(date(2026, 7, 15), now) == 0
    assert cal.sessions_behind(date(2026, 7, 14), now) == 1
    assert cal.sessions_behind(date(2026, 7, 13), now) == 2
    assert cal.sessions_behind(date(2026, 7, 10), now) == 3   # Fri -> skips the weekend
    assert cal.sessions_behind(date(2026, 7, 9), now) == 4


def test_sessions_behind_ignores_weekend_and_holiday_gaps():
    """A store holding Thu 07-02 is only ONE session behind on Mon 07-06 —
    the holiday Friday and the weekend are not missing bars."""
    now = datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc)  # 17:00 ET Monday
    assert cal.expected_last_session(now) == date(2026, 7, 6)
    assert cal.sessions_behind(date(2026, 7, 2), now) == 1


def test_sessions_behind_future_store_is_not_negative():
    """A future-dated row means no COMPLETED session is missing, not -N."""
    now = datetime(2026, 7, 16, 20, 0, tzinfo=timezone.utc)
    assert cal.sessions_behind(date(2026, 12, 1), now) == 0


import pytest


@pytest.mark.parametrize(
    "name",
    ["is_session", "last_session_on_or_before", "expected_last_session",
     "session_date", "sessions_between", "sessions_behind"],
)
def test_public_calendar_api_present(name: str):
    """The helpers every freshness gate is built on must not silently disappear.

    Carried over from tests/test_nyse_calendar_import_names.py, whose AST sweep was
    promoted repo-wide into tests/test_first_party_import_names.py.  That sweep
    resolves import NAMES statically; this asserts the calendar's own public surface
    is present AND callable at runtime, which the static sweep cannot see.
    """
    assert callable(getattr(cal, name, None)), f"lib.nyse_calendar.{name} missing"
