"""TSX (Toronto Stock Exchange) session calendar — which Canadian equity sessions
exist, computed from the rules.

WHY THIS EXISTS (2026-08-14 Canada board freeze).  ``site/factordata/canada_standouts.json``
sat frozen at ``as_of=2026-08-13`` from 2026-08-14 through 2026-08-18 while its US, HK
and mainland siblings all advanced — and nothing reported it, because
``scripts/check_nightly_liveness.py`` graded only the US Prophet board and there was no
Canadian session calendar to measure a Canadian board against.  A weekday approximation
would have worked, but only with a budget wide enough to swallow Christmas + Boxing Day,
and that width is paid every day of the year to cover six of them: measured against the
real freeze, a weekday budget of 3 first pages on 2026-08-20 where this table pages on
2026-08-18.  So the calendar is worth writing.  Pure rule arithmetic, zero data
dependencies, stdlib only — the same shape as ``lib/nyse_calendar.py``,
``lib/hk_calendar.py`` and ``lib/cn_calendar.py``.

Scope: full-day closures for TSX/TSXV cash equities.  Early closes (13:00 ET, typically
Christmas Eve) are NOT modeled — a shortened session still produces a daily bar, and
``expected_last_session`` only asks "should a bar for day D exist by now?", for which the
regular 16:00 ET close plus a settle buffer is a conservative answer.

DIRECTION OF ERROR — the rule this table is built on
    Omitting a real holiday   → we count a session that never happened → we over-count
        how far behind a store is → a false "stale".  Non-fatal and self-clearing.
    Inventing a holiday       → we skip a session that did happen → we under-count →
        a silently-wrong "fresh".  This is the dangerous direction.
So when a day is uncertain, it is LEFT OUT.  The clearest live example is the National
Day for Truth and Reconciliation (Sept 30, a federal statutory holiday since 2021): TMX
keeps the markets OPEN that day, so encoding it would delete a real session from this
calendar.  It is deliberately absent.

Unscheduled one-off closures (systems outages, days of mourning) cannot be computed from
rules — they live in ``ONE_OFF_CLOSURES`` and MUST be appended when announced.  The cost
of a missing entry is a false "stale", never a silently-wrong "fresh".

HOW TO ADD A ONE-OFF CLOSURE:
    Add the date to ONE_OFF_CLOSURES as `date(YYYY, MM, DD)`.
    Example for a systems outage on 2026-09-15:
        date(2026, 9, 15),   # TMX systems outage — full-day halt
    Commit the change so all environments see the update.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")

# The last completed session's daily bar is expected only after the 16:00 ET close plus a
# settle buffer (vendors finalize daily bars some minutes after the close; 1h is generous
# and matches lib/nyse_calendar, whose trading day this one shares).
_CLOSE_PLUS_SETTLE = time(17, 0)

# Announced full-day closures the rules cannot derive. Append when announced.
# Pattern: date(YYYY, MM, DD),  # reason
ONE_OFF_CLOSURES: frozenset[date] = frozenset()


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) `weekday` (Mon=0) of the month."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous computus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 — canonical computus variable
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed_ca(d: date, taken: set[date]) -> date:
    """TMX observance for a fixed-date holiday: a weekend date rolls FORWARD to the next
    weekday not already taken.

    Unlike the NYSE rule (which rolls a Saturday holiday BACK to the Friday), Canadian
    practice is forward-only, and the Christmas/Boxing Day pair is the case that proves
    it: 2021-12-25 fell on a Saturday and 12-26 on a Sunday, and TSX was closed BOTH
    Monday 12-27 and Tuesday 12-28.  ``taken`` is what makes the second one land on the
    Tuesday instead of colliding onto the Monday.
    """
    while d.weekday() >= 5 or d in taken:
        d += timedelta(days=1)
    return d


def holidays(year: int) -> frozenset[date]:
    """Scheduled full-day TSX holidays for `year` (rule-computed, cached)."""
    return _holidays_cached(year)


_HOLIDAY_CACHE: dict[int, frozenset[date]] = {}


def _holidays_cached(year: int) -> frozenset[date]:
    got = _HOLIDAY_CACHE.get(year)
    if got is not None:
        return got
    hs: set[date] = set()
    hs.add(_observed_ca(date(year, 1, 1), hs))     # New Year's Day
    hs.add(_nth_weekday(year, 2, 0, 3))            # Family Day — 3rd Mon Feb (TSX from 2008)
    hs.add(_easter(year) - timedelta(days=2))      # Good Friday (TSX trades Easter Monday)
    # Victoria Day — the Monday PRECEDING May 25, i.e. the Monday on or before May 24.
    may24 = date(year, 5, 24)
    hs.add(may24 - timedelta(days=may24.weekday()))
    hs.add(_observed_ca(date(year, 7, 1), hs))     # Canada Day
    hs.add(_nth_weekday(year, 8, 0, 1))            # Civic Holiday — 1st Mon Aug
    hs.add(_nth_weekday(year, 9, 0, 1))            # Labour Day — 1st Mon Sep
    hs.add(_nth_weekday(year, 10, 0, 2))           # Thanksgiving (CA) — 2nd Mon Oct
    # Christmas then Boxing Day, in that order: _observed_ca's `taken` set is what
    # pushes Boxing Day to the next free weekday when both land on a weekend.
    hs.add(_observed_ca(date(year, 12, 25), hs))
    hs.add(_observed_ca(date(year, 12, 26), hs))
    # Sept 30 (National Day for Truth and Reconciliation) is NOT here on purpose — TMX
    # keeps the markets open. See the module docstring's direction-of-error rule.
    out = frozenset(h for h in hs if h.year == year)
    _HOLIDAY_CACHE[year] = out
    return out


def is_session(d: date) -> bool:
    """True when TSX holds a session on `d`."""
    return (d.weekday() < 5
            and d not in holidays(d.year)
            and d not in ONE_OFF_CLOSURES)


def last_session_on_or_before(d: date) -> date:
    """Most recent TSX session date <= d."""
    for _ in range(30):
        if is_session(d):
            return d
        d -= timedelta(days=1)
    raise ValueError("no TSX session found in the prior 30 days — calendar rules broken")


def expected_last_session(now: datetime | None = None) -> date:
    """The most recent COMPLETED TSX session whose daily bar the store should hold.

    'Completed' = the 16:00 ET close plus a settle buffer has passed (17:00 ET), so a
    same-day afternoon run conservatively expects only the PRIOR session. Naive datetimes
    are taken as UTC (the pipeline's convention).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_et = now.astimezone(TORONTO)
    today = now_et.date()
    if is_session(today) and now_et.time() >= _CLOSE_PLUS_SETTLE:
        return today
    return last_session_on_or_before(today - timedelta(days=1))


def sessions_between(start: date, end: date) -> int:
    """Count sessions strictly after `start`, up to and including `end`. 0 when end <= start."""
    n = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if is_session(d):
            n += 1
    return n


def sessions_behind(latest: date, now: datetime | None = None) -> int:
    """How many completed TSX sessions a store/artifact holding `latest` is missing.

    Counts sessions strictly after `latest` up to and including ``expected_last_session(now)``
    — NOT up to today. On a session morning today's bar does not exist yet, so counting to
    today would report every store as one session staler than it is and trip a budget a day
    early. The 17:00 ET settle buffer in ``expected_last_session`` is what makes that true
    through the whole Toronto session.

    0 = current. Negative is impossible: a store ahead of the calendar returns 0, since no
    completed session is missing.

    NOTE the return-type difference from lib/nyse_calendar: ``sessions_between`` here already
    RETURNS A COUNT (the NYSE one returns the list of dates), so there is no ``len()`` in
    this expression and adding one would be a TypeError, not a style choice. Mirrors
    lib/cn_calendar, which made the same choice for the same reason.
    """
    return sessions_between(latest, expected_last_session(now))
