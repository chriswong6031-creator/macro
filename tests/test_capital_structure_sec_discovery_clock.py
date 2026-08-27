from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine.capital_structure.sec_discovery_clock import (
    latest_expected_daily_index_date,
    latest_expected_realtime_filing_date,
)


ET = ZoneInfo("America/New_York")


@pytest.mark.parametrize(
    ("observed_at", "daily_expected", "realtime_expected"),
    [
        # Monday current-day index is not overdue before its build begins.
        (datetime(2026, 8, 24, 18, 30, tzinfo=ET), date(2026, 8, 21), date(2026, 8, 24)),
        # 22:00 ET is the documented start of a build that may take hours.
        (datetime(2026, 8, 24, 22, 0, tzinfo=ET), date(2026, 8, 21), date(2026, 8, 24)),
        # Once the conservative next-day readiness boundary passes, Monday is due.
        (datetime(2026, 8, 25, 6, 1, tzinfo=ET), date(2026, 8, 24), date(2026, 8, 25)),
        # Weekend health remains bound to Friday rather than inventing an index day.
        (datetime(2026, 8, 29, 12, 0, tzinfo=ET), date(2026, 8, 28), date(2026, 8, 28)),
        # Labor Day is not a filing/index session.
        (datetime(2026, 9, 7, 18, 30, tzinfo=ET), date(2026, 9, 4), date(2026, 9, 4)),
        # UTC has rolled to Tuesday while New York is still Monday evening.
        (
            datetime.fromisoformat("2026-08-25T01:30:00+00:00"),
            date(2026, 8, 21),
            date(2026, 8, 24),
        ),
    ],
)
def test_sec_discovery_clock_uses_new_york_filing_day_and_readiness(
    observed_at: datetime,
    daily_expected: date,
    realtime_expected: date,
):
    assert latest_expected_daily_index_date(observed_at) == daily_expected
    assert latest_expected_realtime_filing_date(observed_at) == realtime_expected


def test_sec_discovery_clock_rejects_naive_instants():
    with pytest.raises(ValueError, match="timezone-aware"):
        latest_expected_daily_index_date(datetime(2026, 8, 24, 18, 30))
