"""A-share session calendar (lib/cn_calendar.py).

The load-bearing property is the DIRECTION OF ERROR, not completeness. This table is
deliberately minimal: marking a real holiday as a session over-counts the lag and shows a
false "stale" banner (safe, self-clearing), while marking a real session as a holiday
under-counts and produces a silently-wrong "fresh" (the failure the whole disclosure exists to
prevent). So the tests below pin the days that are closed EVERY year, and pin that days the
State Council merely *often* closes still read as sessions.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from lib import cn_calendar as cn


class TestWeekends:
    def test_weekends_are_never_sessions(self):
        assert cn.is_session(date(2026, 8, 8)) is False   # Saturday
        assert cn.is_session(date(2026, 8, 9)) is False   # Sunday

    def test_ordinary_weekdays_are_sessions(self):
        for d in range(3, 8):                             # Mon-Fri, no holiday
            assert cn.is_session(date(2026, 8, d)) is True


class TestGoldenWeek:
    @pytest.mark.parametrize("year", [2024, 2025, 2026, 2027, 2028])
    def test_national_day_week_is_closed_every_year(self, year):
        """Oct 1-7 is closed without exception — the longest predictable closure."""
        for day in range(1, 8):
            assert cn.is_session(date(year, 10, day)) is False

    def test_oct_8_reopens_when_it_is_a_weekday(self):
        assert cn.is_session(date(2026, 10, 8)) is True   # Thursday


class TestSpringFestival:
    def test_invariant_core_is_closed(self):
        """Eve + LNY days 1-4, the span closed in every year on record."""
        lny = cn.LNY_FIRST[2026]                          # 2026-02-17
        assert cn.is_session(lny - timedelta(days=1)) is False
        for i in range(4):
            assert cn.is_session(lny + timedelta(days=i)) is False

    def test_2019_reopened_on_lny_plus_6_and_the_table_agrees(self):
        """2019 is the year that refutes a fixed eve..LNY+6 span: the exchanges closed
        Feb 4-8 and traded again on Feb 11. Encoding the longer span would have marked a
        real session as a holiday — the dangerous direction."""
        for day in range(4, 9):
            assert cn.is_session(date(2019, 2, day)) is False
        assert cn.is_session(date(2019, 2, 11)) is True

    def test_long_closure_tail_reads_as_a_session_not_a_holiday(self):
        """2024 actually closed Feb 9-16, but only the core is encoded. Feb 15 therefore
        reads as a session — a false "stale", which is the SAFE direction and the reason the
        china sentinel budget is 12 days."""
        assert cn.is_session(date(2024, 2, 15)) is True


class TestFixedAndLunarHolidays:
    def test_new_year_and_labour_day(self):
        assert cn.is_session(date(2027, 1, 1)) is False   # Friday
        assert cn.is_session(date(2027, 5, 3)) is True    # Labour Day tail is not encoded

    def test_qingming_matches_the_exchange_notice_not_the_leap_rule(self):
        """2025 Qingming was Apr 4; the leap-year rule yields Apr 5 and is wrong."""
        assert cn.QINGMING[2025] == date(2025, 4, 4)
        assert cn.is_session(date(2025, 4, 4)) is False

    def test_lunar_tables_cover_the_forward_window(self):
        for table in (cn.LNY_FIRST, cn.QINGMING, cn.DRAGON_BOAT, cn.MID_AUTUMN):
            for year in range(2024, 2031):
                assert year in table, f"{year} missing from a lunar table"

    def test_mid_autumn_is_the_festival_day_not_hkex_s_day_after(self):
        """HKEX closes lunar 8/16; the mainland closes 8/15. Confusing the two would shift
        every entry by a day."""
        assert cn.MID_AUTUMN[2024] == date(2024, 9, 17)
        assert cn.MID_AUTUMN[2022] == date(2022, 9, 10)


class TestExpectedLastSession:
    def test_settle_buffer_holds_back_the_same_day(self):
        """Before 17:00 CST the current session's bar is not yet expected."""
        pre = datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc)    # 10:00 CST, mid-session
        post = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)  # 20:00 CST, settled
        assert cn.expected_last_session(pre) == date(2026, 8, 5)
        assert cn.expected_last_session(post) == date(2026, 8, 6)

    def test_naive_datetimes_are_read_as_utc(self):
        naive = datetime(2026, 8, 6, 12, 0)
        assert cn.expected_last_session(naive) == cn.expected_last_session(
            naive.replace(tzinfo=timezone.utc)
        )

    def test_weekend_falls_back_to_friday(self):
        sunday = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
        assert cn.expected_last_session(sunday) == date(2026, 8, 7)


class TestSessionsBetween:
    def test_counts_strictly_after_start_through_end(self):
        # 2026-07-31 Fri -> 2026-08-06 Thu: Aug 3,4,5,6
        assert cn.sessions_between(date(2026, 7, 31), date(2026, 8, 6)) == 4

    def test_zero_when_end_is_not_after_start(self):
        assert cn.sessions_between(date(2026, 8, 6), date(2026, 8, 6)) == 0
        assert cn.sessions_between(date(2026, 8, 6), date(2026, 8, 3)) == 0

    def test_golden_week_contributes_no_sessions(self):
        """Sep 30 -> Oct 9 2026 spans ten calendar days but only two sessions (Oct 8, 9).
        This is why a calendar-day rule alone would page every October."""
        assert cn.sessions_between(date(2026, 9, 30), date(2026, 10, 9)) == 2


class TestBackstopConstant:
    def test_backstop_clears_the_longest_real_closure(self):
        """MAX_LEGIT_CLOSURE_DAYS is the table-independent guard: it must exceed the
        longest sessionless run the calendar can legitimately produce."""
        longest = 0
        for year in (2024, 2025, 2026, 2027):
            for start in (cn.LNY_FIRST[year], date(year, 10, 1)):
                d, gap = start, 0
                for _ in range(20):
                    if cn.is_session(d):
                        break
                    gap += 1
                    d = d + timedelta(days=1)
                longest = max(longest, gap)
        assert longest <= cn.MAX_LEGIT_CLOSURE_DAYS

    def test_no_session_gap_ever_reaches_the_backstop_in_a_normal_year(self):
        """Walk a full year and assert the longest sessionless run stays inside the
        backstop — if a table edit ever produces a 12-day hole, this fails."""
        d, gap, longest = date(2026, 1, 1), 0, 0
        while d < date(2027, 1, 1):
            gap = 0 if cn.is_session(d) else gap + 1
            longest = max(longest, gap)
            d = d + timedelta(days=1)
        assert longest <= cn.MAX_LEGIT_CLOSURE_DAYS
