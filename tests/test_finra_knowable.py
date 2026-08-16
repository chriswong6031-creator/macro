"""lib/finra_knowable.py — the FINRA short-interest publication lag, pinned to measurement.

WHAT THESE CATCH.  The lag used to be the literal ``10`` CALENDAR days, mirrored in
``engine/neuralweb/context_api.py`` and ``scripts/backfill_finra_short_interest.py``
and described in both as "the deliberately conservative floor".  It was not
conservative: it lands 2-3 days EARLY on every settlement this repo holds, it is
two days short of the FINRA schedule example its own comment cited, and on the
2026-07-31 settlement it declared the row knowable three days before our collector
could have seen it.  Every test below pins one of those measured facts so a revert
to calendar arithmetic fails loudly rather than quietly re-opening the look-ahead.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent

from lib.finra_knowable import (
    KNOWABLE_LAG_FALLBACK_DAYS,
    KNOWABLE_LAG_SESSIONS,
    knowable_date,
    knowable_series,
)
from lib.nyse_calendar import is_session

#: The three settlements the committed data/finra/short_interest_history.parquet
#: holds, with their 8-session knowable dates and the collector's real capture
#: dates.  Measured 2026-08-14 — see the parquet test at the bottom of this file.
_COMMITTED = [
    # settlement,       8 sessions,       capture_date,     +10cal is early by
    (date(2026, 6, 30), date(2026, 7, 13), date(2026, 7, 22), 3),
    (date(2026, 7, 15), date(2026, 7, 27), date(2026, 8, 6), 2),
    (date(2026, 7, 31), date(2026, 8, 12), date(2026, 8, 13), 2),
]


def test_the_three_committed_settlements_are_pinned_to_eight_sessions():
    """Pure arithmetic, no store: the convention resolves to the measured dates.

    Catches a silent change to KNOWABLE_LAG_SESSIONS or to the session scan.  The
    3-day gap on 2026-06-30 is the observed Independence Day closure (2026-07-03),
    which is exactly the class of thing calendar arithmetic cannot see.
    """
    assert KNOWABLE_LAG_SESSIONS == 8
    assert not is_session(date(2026, 7, 3)), "2026-07-03 is the observed July 4th closure"
    for settlement, expected, _capture, _early in _COMMITTED:
        assert knowable_date(settlement) == expected, (
            f"{settlement}: expected the 8th session {expected}, "
            f"got {knowable_date(settlement)}"
        )


def test_the_retired_ten_calendar_day_rule_lands_early_on_every_committed_settlement():
    """THE NEGATIVE CONTROL — this is the test that fails on a revert to +10 calendar.

    The retired rule stamped ``settlement + 10 calendar days``.  On all three
    committed settlements that date PRECEDES the session answer, by 3/2/2 days,
    so every study joining on it saw the figure days before it existed.
    """
    for settlement, expected, _capture, early_by in _COMMITTED:
        retired = settlement + timedelta(days=10)
        assert retired < expected, (
            f"{settlement}: the retired +10-calendar rule gave {retired}, which is not "
            f"before the 8-session answer {expected} — the defect this module fixes is gone"
        )
        assert (expected - retired).days == early_by, (
            f"{settlement}: +10 calendar is early by {(expected - retired).days} days, "
            f"measured {early_by}"
        )


def test_the_calendar_fallback_never_precedes_the_session_answer():
    """The degraded answer must wait LONGER than the real one, never shorter.

    ``knowable_date`` falls back to ``settlement + KNOWABLE_LAG_FALLBACK_DAYS``
    when the session scan cannot answer.  A fallback shorter than the widest
    8-session span would reintroduce the very early-stamp defect on exactly the
    rows where the calendar already failed us.  Checked over every weekday
    2015-01-01..2035-12-31 (pure rule arithmetic with a cached holiday table —
    ~5.5k dates, well under a second).  The tightest case is 2015-12-21, whose
    8th session is 2016-01-04, exactly 14 days out.
    """
    d, end = date(2015, 1, 1), date(2035, 12, 31)
    tightest, tightest_day = -1, None
    while d <= end:
        if d.weekday() < 5:
            span = (knowable_date(d) - d).days
            assert d + timedelta(days=KNOWABLE_LAG_FALLBACK_DAYS) >= knowable_date(d), (
                f"{d}: fallback {d + timedelta(days=KNOWABLE_LAG_FALLBACK_DAYS)} precedes "
                f"the 8-session answer {knowable_date(d)} — the fallback errs EARLY"
            )
            if span > tightest:
                tightest, tightest_day = span, d
        d += timedelta(days=1)
    assert tightest == 14 and tightest_day == date(2015, 12, 21), (
        f"widest 8-session span moved to {tightest}d at {tightest_day}; "
        f"KNOWABLE_LAG_FALLBACK_DAYS={KNOWABLE_LAG_FALLBACK_DAYS} may no longer dominate it"
    )


def test_eight_sessions_dominates_the_cited_finra_schedule_example():
    """"Conservative" must be TRUE, which is what the retired comment got wrong.

    The comment cited FINRA's own schedule — settlement Jan 15 -> due Jan 20 ->
    published Jan 27 — and then used a 10-CALENDAR-day constant, i.e. Jan 25, two
    days before the publication it had just quoted.  The session convention clears
    the cited publication date in every year where Jan 15 is itself a session.
    """
    checked = 0
    for year in range(2015, 2027):
        jan15 = date(year, 1, 15)
        if not is_session(jan15):
            continue
        checked += 1
        assert knowable_date(jan15) >= date(year, 1, 27), (
            f"{year}: knowable {knowable_date(jan15)} precedes the cited "
            f"publication date {date(year, 1, 27)}"
        )
        assert jan15 + timedelta(days=10) < date(year, 1, 27), (
            f"{year}: the retired +10-calendar rule no longer precedes the cited "
            f"publication date — the negative control is dead"
        )
    assert checked >= 6, f"only {checked} years had Jan 15 as a session — sample too thin"


def test_knowable_series_is_nat_safe_and_maps_over_unique_settlements():
    """A NaT settlement stays NaT; repeats resolve identically; the index survives.

    Fail-closed matters here: ``_short_int_dim`` gates on ``knowable_date <=
    date_ts``, and NaT compares False, so an undated settlement stays invisible.
    Mapping it to some default would make a row with no settlement date knowable
    on a date nothing justifies.  The index is preserved because the caller
    assigns the result straight back onto the frame.
    """
    src = pd.Series(
        ["2026-06-30", None, "2026-07-15", "2026-06-30", "not-a-date", "2026-07-31"],
        index=[10, 11, 12, 13, 14, 15],
    )
    out = knowable_series(src)

    assert list(out.index) == list(src.index)
    assert out.loc[10] == pd.Timestamp("2026-07-13")
    assert out.loc[13] == pd.Timestamp("2026-07-13")     # repeat resolves identically
    assert out.loc[12] == pd.Timestamp("2026-07-27")
    assert out.loc[15] == pd.Timestamp("2026-08-12")
    assert pd.isna(out.loc[11])                          # None -> NaT
    assert pd.isna(out.loc[14])                          # unparseable -> NaT

    # And a NaT knowable_date is invisible to the resolver's gate, in both directions.
    assert not (out.loc[11] <= pd.Timestamp("2099-01-01"))
    assert len(knowable_series(pd.Series([], dtype=object))) == 0


@pytest.mark.needs_full_checkout("data")
def test_committed_history_store_is_knowable_no_earlier_than_its_capture_date():
    """THE MEASURED LEAK, pinned against the real store.

    ``data/finra/short_interest_history.parquet`` carries ``capture_date`` — the
    collector's own run date.  Under the retired +10-calendar rule EVERY row in the
    store was declared knowable BEFORE the day we could first have seen it (07-31
    settlement: stamped 08-10, captured 08-13).  Under the session rule floored by
    capture_date, no row is knowable before its capture.
    """
    path = _ROOT / "data" / "finra" / "short_interest_history.parquet"
    if not path.exists():                       # host without the store
        pytest.skip(f"{path} absent")
    df = pd.read_parquet(path)

    settlements = pd.to_datetime(df["settlement_date"], errors="coerce").dt.normalize()
    capture = pd.to_datetime(df["capture_date"], errors="coerce").dt.normalize()
    assert set(settlements.unique()) == {pd.Timestamp(s) for s, _k, _c, _e in _COMMITTED}, (
        f"the committed store's settlements moved: {sorted(set(settlements.unique()))}"
    )

    derived = knowable_series(settlements)
    effective = derived.where(~(capture > derived), capture)
    retired = settlements + pd.Timedelta(days=10)

    assert (effective >= capture).all(), (
        "some row is knowable before the collector captured it — the floor is not holding"
    )
    assert (retired < capture).all(), (
        "the retired +10-calendar rule no longer precedes capture on every row — "
        "the negative control this test exists for is dead"
    )
