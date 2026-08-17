"""SP1-B trading-day price index — the filter must refuse a contaminated calendar.

Prereg §5C: HORIZONS are positional row offsets, so a weekend row in the union
index silently shortens every labelled horizon. session_rows fail-opens when
every row is non-session; restrict_to_nyse_sessions must not inherit that.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.nyse_calendar import is_session
from scripts.research.sp1_short_pressure_study import restrict_to_nyse_sessions


def _panel(dates: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"AAA": range(len(idx)), "BTC-USD": range(len(idx))},
                        index=idx)


def test_drops_weekend_and_nyse_holiday_rows():
    # 2024-07-04 was Thursday Independence Day; 07-06/07 are the weekend.
    px = _panel(["2024-07-03", "2024-07-04", "2024-07-05",
                 "2024-07-06", "2024-07-07", "2024-07-08"])
    out = restrict_to_nyse_sessions(px)
    got = [d.date().isoformat() for d in out.index]
    assert got == ["2024-07-03", "2024-07-05", "2024-07-08"]
    assert all(is_session(d.date()) for d in out.index)
    # A 2-row step is 2 true sessions (Fri + Mon), not a weekend-inflated span.
    assert len(out) - 1 >= 2
    assert (out.index[2] - out.index[0]).days == 5  # Wed -> Mon, two sessions later


def test_raises_when_session_rows_would_fail_open():
    px = _panel(["2024-07-06", "2024-07-07"])  # Saturday + Sunday only
    with pytest.raises(RuntimeError, match="not a trading-day index"):
        restrict_to_nyse_sessions(px)


def test_clean_index_is_unchanged():
    px = _panel(["2024-07-03", "2024-07-05", "2024-07-08"])
    out = restrict_to_nyse_sessions(px)
    assert list(out.index) == list(px.index)
