"""SEC filing-day and daily-index readiness law for Capital Structure.

EDGAR daily indexes are a nightly reconciliation surface, not a UTC-midnight
clock.  The SEC says current-day indexes begin updating around 22:00 Eastern
and usually finish within a few hours.  Capital Structure therefore treats a
business day's index as expected only after 06:00 Eastern on the following
calendar day.  Latest Filings remains the same-day observation surface.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar


SEC_TIMEZONE = ZoneInfo("America/New_York")
DAILY_INDEX_READY_TIME_ET = time(6, 0)
DISCOVERY_CLOCK_POLICY_VERSION = "capital-structure-sec-discovery-clock/1.0.0"


def _as_sec_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("SEC discovery clocks require a timezone-aware instant")
    return value.astimezone(SEC_TIMEZONE)


@lru_cache(maxsize=512)
def is_sec_calendar_closed(value: date) -> bool:
    """Return true for weekends and observed US federal weekday closures."""
    if value.weekday() >= 5:
        return True
    holidays = USFederalHolidayCalendar().holidays(
        start=pd.Timestamp(value), end=pd.Timestamp(value),
    )
    return not holidays.empty


def _latest_open_day_on_or_before(value: date) -> date:
    current = value
    while is_sec_calendar_closed(current):
        current -= timedelta(days=1)
    return current


def latest_expected_realtime_filing_date(observed_at: datetime) -> date:
    """Latest New York filing day whose Latest Filings stream must be observed."""
    return _latest_open_day_on_or_before(_as_sec_time(observed_at).date())


def daily_index_ready_at(index_date: date) -> datetime:
    """Conservative accepted completion boundary for one SEC daily index."""
    return datetime.combine(
        index_date + timedelta(days=1),
        DAILY_INDEX_READY_TIME_ET,
        tzinfo=SEC_TIMEZONE,
    )


def latest_expected_daily_index_date(observed_at: datetime) -> date:
    """Latest SEC business-day index that should be complete at ``observed_at``."""
    observed_et = _as_sec_time(observed_at)
    candidate = observed_et.date() - timedelta(days=1)
    while True:
        if (
            not is_sec_calendar_closed(candidate)
            and daily_index_ready_at(candidate) <= observed_et
        ):
            return candidate
        candidate -= timedelta(days=1)


def daily_reconciliation_updated_boundary(index_date: date) -> datetime:
    """Oldest Latest Filings update not already covered by an index date."""
    return datetime.combine(
        index_date + timedelta(days=1), time.min, tzinfo=SEC_TIMEZONE,
    )
