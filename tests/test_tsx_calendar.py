"""TSX session calendar (lib/tsx_calendar.py).

The load-bearing property is the DIRECTION OF ERROR, not completeness: omitting a real
holiday over-counts a store's lag and shows a false "stale" (safe, self-clearing), while
INVENTING a holiday under-counts and produces a silently-wrong "fresh" — the failure the
whole per-market freshness check exists to prevent. So the tests below pin the ten
closures TMX publishes every year, pin the observance shifts that have actually happened,
and pin the one federal statutory holiday TMX deliberately trades through.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from lib import tsx_calendar as tsx


class TestWeekends:
    def test_weekends_are_never_sessions(self):
        assert tsx.is_session(date(2026, 8, 8)) is False   # Saturday
        assert tsx.is_session(date(2026, 8, 9)) is False   # Sunday

    def test_ordinary_weekdays_are_sessions(self):
        for d in range(10, 15):                           # Mon-Fri 2026-08, no holiday
            assert tsx.is_session(date(2026, 8, d)) is True


class TestTheTenAnnualClosures:
    @pytest.mark.parametrize("year", [2024, 2025, 2026, 2027, 2028])
    def test_exactly_ten_scheduled_closures_every_year(self, year):
        """TMX publishes ten. A drift in either direction is a rule bug: eleven means an
        invented holiday (the dangerous direction), nine means one silently vanished."""
        assert len(tsx.holidays(year)) == 10, sorted(tsx.holidays(year))

    def test_2026_closures_are_the_published_set(self):
        assert sorted(tsx.holidays(2026)) == [
            date(2026, 1, 1),    # New Year's Day (Thu)
            date(2026, 2, 16),   # Family Day — 3rd Mon Feb
            date(2026, 4, 3),    # Good Friday
            date(2026, 5, 18),   # Victoria Day — Mon before May 25
            date(2026, 7, 1),    # Canada Day (Wed)
            date(2026, 8, 3),    # Civic Holiday — 1st Mon Aug
            date(2026, 9, 7),    # Labour Day — 1st Mon Sep
            date(2026, 10, 12),  # Thanksgiving (CA) — 2nd Mon Oct
            date(2026, 12, 25),  # Christmas (Fri)
            date(2026, 12, 28),  # Boxing Day observed (Sat 12-26 -> Mon)
        ]

    def test_victoria_day_is_the_monday_before_may_25(self):
        for year, expected in [(2024, date(2024, 5, 20)), (2025, date(2025, 5, 19)),
                               (2026, date(2026, 5, 18)), (2027, date(2027, 5, 24))]:
            assert expected in tsx.holidays(year), year
            assert expected.weekday() == 0
            assert date(year, 5, 25) - expected <= timedelta(days=7)


class TestObservanceShifts:
    def test_christmas_and_boxing_day_take_two_separate_weekdays(self):
        """2021-12-25 fell on Saturday and 12-26 on Sunday; TSX was closed BOTH Monday
        12-27 and Tuesday 12-28. A shared observance that collapsed them onto one Monday
        would delete a real closure and silently under-count a December lag."""
        hs = tsx.holidays(2021)
        assert date(2021, 12, 27) in hs
        assert date(2021, 12, 28) in hs
        assert tsx.is_session(date(2021, 12, 27)) is False
        assert tsx.is_session(date(2021, 12, 28)) is False

    def test_weekend_new_year_rolls_forward_not_back(self):
        """Canadian observance is forward-only. 2022-01-01 was a Saturday and TSX was
        closed Monday 01-03 — NOT Friday 2021-12-31, which the NYSE rule would pick."""
        assert date(2022, 1, 3) in tsx.holidays(2022)
        assert tsx.is_session(date(2021, 12, 31)) is True


class TestDeliberateOmissions:
    def test_truth_and_reconciliation_day_is_a_session(self):
        """Sept 30 is a federal statutory holiday, and TMX keeps the markets OPEN. Adding
        it would delete a real session — the silently-wrong-"fresh" direction."""
        for year in (2024, 2025, 2026):
            assert tsx.is_session(date(year, 9, 30)) is (date(year, 9, 30).weekday() < 5)

    def test_easter_monday_is_a_session(self):
        """TSX closes Good Friday only."""
        easter_monday_2026 = date(2026, 4, 6)
        assert tsx.is_session(date(2026, 4, 3)) is False   # Good Friday
        assert tsx.is_session(easter_monday_2026) is True


class TestExpectedLastSession:
    def test_settle_buffer_holds_through_the_toronto_session(self):
        """A same-day morning run must expect only the PRIOR session — today's bar does
        not exist yet, and counting to today trips every budget a day early."""
        morning = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)   # 09:00 ET Tue
        assert tsx.expected_last_session(morning) == date(2026, 8, 17)
        evening = datetime(2026, 8, 18, 22, 0, tzinfo=timezone.utc)   # 18:00 ET Tue
        assert tsx.expected_last_session(evening) == date(2026, 8, 18)

    def test_weekend_resolves_back_to_friday(self):
        sat = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
        assert tsx.expected_last_session(sat) == date(2026, 8, 14)

    def test_naive_datetime_is_read_as_utc(self):
        naive = datetime(2026, 8, 18, 13, 0)
        assert tsx.expected_last_session(naive) == date(2026, 8, 17)


class TestSessionsBehind:
    def test_current_store_is_zero_behind(self):
        now = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)   # Mon 04:00 ET
        assert tsx.sessions_behind(date(2026, 8, 14), now) == 0

    def test_the_2026_08_canada_freeze(self):
        """The motivating exemplar. canada_standouts.json sat at as_of=2026-08-13 from
        08-14 onward: one session behind on the 17th (inside the guard's budget of 1),
        two on the 18th — which is where scripts/check_nightly_liveness.py pages."""
        assert tsx.sessions_behind(
            date(2026, 8, 13), datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)) == 1
        assert tsx.sessions_behind(
            date(2026, 8, 13), datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)) == 2

    def test_a_store_ahead_of_the_calendar_is_never_negative(self):
        now = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)
        assert tsx.sessions_behind(date(2026, 8, 20), now) == 0

    def test_a_long_weekend_adds_zero(self):
        """Victoria Day 2026-05-18. A store holding Friday 05-15 is 0 behind on the
        Monday holiday — the whole reason the anchor is a calendar and not a clock."""
        holiday_monday = datetime(2026, 5, 18, 13, 0, tzinfo=timezone.utc)
        assert tsx.sessions_behind(date(2026, 5, 15), holiday_monday) == 0
