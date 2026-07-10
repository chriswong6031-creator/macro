"""NYSE session calendar — which US equity sessions exist, computed from the rules.

WHY THIS EXISTS (2026-07-07 stale-regime incident): when the nightly collection push
dies, EVERY committed price store freezes on the same stale date, so any store-vs-store
freshness check (e.g. yahoo/SPY vs the massive manifest in
scripts/refresh_regime_if_stale.py mode 3) sees agreement and stays silent. Only the
exchange calendar knows a completed session is missing from the store. This module is
that independent reference: pure rule arithmetic, zero data dependencies, stdlib only.

Scope: full-day closures for US cash equities (NYSE/Nasdaq share the schedule). Early
closes (13:00 ET) are NOT modeled — a session with an early close still produces a daily
bar, and `expected_last_session` only asks "should a bar for day D exist by now?", for
which the regular 16:00 ET close plus a settle buffer is a conservative answer.

Unscheduled one-off closures (presidential mourning, disasters) cannot be computed:
they live in `ONE_OFF_CLOSURES` and MUST be appended when announced. The cost of a
missing entry is a false "store stale" — a red-but-non-fatal gate step and an honest
`stale` stamp until the date is added — never a silently-wrong "fresh".
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# The last completed session's daily bar is expected in the store only after the close
# plus a settle buffer (vendors finalize the daily bar some minutes after 16:00 ET;
# 1h is generous — the nightly pipeline runs hours later anyway).
_CLOSE_PLUS_SETTLE = time(17, 0)

# Announced full-day closures the rules can't derive. Append when announced.
ONE_OFF_CLOSURES: frozenset[date] = frozenset({
    date(2012, 10, 29), date(2012, 10, 30),   # Hurricane Sandy
    date(2018, 12, 5),                        # G.H.W. Bush national day of mourning
    date(2025, 1, 9),                         # Carter national day of mourning
})


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) `weekday` (Mon=0) of the month."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


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


def _observed(d: date) -> date:
    """NYSE observance shift for fixed-date holidays: Sat -> Friday before,
    Sun -> Monday after. (New Year's is special-cased inline: a Saturday Jan 1
    is NOT observed early, so it never routes through here.)"""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def holidays(year: int) -> frozenset[date]:
    """Scheduled full-day NYSE holidays for `year` (rule-computed, cached)."""
    return _holidays_cached(year)


_HOLIDAY_CACHE: dict[int, frozenset[date]] = {}


def _holidays_cached(year: int) -> frozenset[date]:
    got = _HOLIDAY_CACHE.get(year)
    if got is not None:
        return got
    hs: set[date] = set()
    # New Year's Day — NYSE does NOT observe it early when Jan 1 is a Saturday
    # (e.g. 2022: Fri 2021-12-31 was a full session).
    ny = date(year, 1, 1)
    if ny.weekday() == 6:
        hs.add(ny + timedelta(days=1))
    elif ny.weekday() != 5:
        hs.add(ny)
    if year >= 1998:
        hs.add(_nth_weekday(year, 1, 0, 3))       # MLK Day — 3rd Mon Jan
    hs.add(_nth_weekday(year, 2, 0, 3))           # Washington's Birthday — 3rd Mon Feb
    hs.add(_easter(year) - timedelta(days=2))     # Good Friday
    hs.add(_last_weekday(year, 5, 0))             # Memorial Day — last Mon May
    if year >= 2022:
        hs.add(_observed(date(year, 6, 19)))      # Juneteenth (NYSE from 2022)
    hs.add(_observed(date(year, 7, 4)))           # Independence Day
    hs.add(_nth_weekday(year, 9, 0, 1))           # Labor Day — 1st Mon Sep
    hs.add(_nth_weekday(year, 11, 3, 4))          # Thanksgiving — 4th Thu Nov
    hs.add(_observed(date(year, 12, 25)))         # Christmas
    out = frozenset(h for h in hs if h.year == year)
    _HOLIDAY_CACHE[year] = out
    return out


def is_session(d: date) -> bool:
    """True when the US cash equity market holds a full or shortened session on `d`."""
    return (d.weekday() < 5
            and d not in holidays(d.year)
            and d not in ONE_OFF_CLOSURES)


def last_session_on_or_before(d: date) -> date:
    """Most recent session date <= d."""
    for _ in range(30):  # longest possible closed stretch is a few days
        if is_session(d):
            return d
        d -= timedelta(days=1)
    raise ValueError("no NYSE session found in the prior 30 days — calendar rules broken")


def expected_last_session(now: datetime | None = None) -> date:
    """The most recent COMPLETED session whose daily bar the price store should hold.

    'Completed' = the regular 16:00 ET close plus a settle buffer has passed (17:00 ET),
    so a same-day afternoon run conservatively expects only the PRIOR session. Naive
    datetimes are taken as UTC (the pipeline's convention)."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_et = now.astimezone(ET)
    today = now_et.date()
    if is_session(today) and now_et.time() >= _CLOSE_PLUS_SETTLE:
        return today
    return last_session_on_or_before(today - timedelta(days=1))


def session_date(now_utc: datetime | None = None) -> date:
    """Return the NYSE SESSION DATE that a UTC timestamp belongs to.

    Semantics — returns the ET calendar date of the session IN PROGRESS or MOST
    RECENTLY COMPLETED at the given instant:
    -----------------------------------------------------------------------
    • On a session day (any time during that ET calendar date) → return that date.
      This covers pre-market, RTH, and post-market hours equally: the whole ET
      calendar day is "the session day" for stamping and dedup purposes.
    • On a non-session day (weekend, holiday) → return the prior completed session.

    Examples (2026-07-09 is a Thursday session; ET = UTC-4 in July):
      • 10:00 ET 07-09 (14:00 UTC)           → 2026-07-09  (RTH, in-progress session)
      • 14:00 ET 07-09 (18:00 UTC)           → 2026-07-09  (RTH, in-progress session)
      • 16:00 ET 07-09 (20:00 UTC)           → 2026-07-09  (just closed)
      • 19:59 ET 07-09 (23:59 UTC 07-09)     → 2026-07-09  (evening, still same ET day)
      • 20:57 ET 07-09 (00:57 UTC 07-10)     → 2026-07-09  (past UTC midnight, same ET day)
      • 00:30 ET 07-10 (04:30 UTC 07-10)     → 2026-07-10  (new ET calendar day, session day)
      • Saturday any time                     → prior Friday (or last trading day)
      • Holiday any time                      → last trading day before the holiday

    WHY NO 16:00 CUTOFF: The intraday fastpath (*/30 11-20 UTC Mon-Fri = 07:00-16:30 ET)
    tape-watches the CURRENT session. session_date() at 10:00 ET on session day D must
    return D, not D-1. A 16:00 cutoff (as-completed semantics) breaks every intraday
    run from 07:00-15:59 ET, producing wrong-day dedup keys and ledger stamps (TS-R2).
    The UTC-midnight rollover defect is already fixed by keying off the ET calendar date.

    This is the correct date to stamp in artifact `as_of` fields and state-dedup keys.
    Using date.today() (UTC) or datetime.utcnow() breaks after ~00:00 UTC when ET is
    still in the same session evening (TS-R2).

    Parameters
    ----------
    now_utc : datetime | None
        UTC-aware datetime to evaluate. If None, uses the current UTC wall clock.
        Naive datetimes are treated as UTC (pipeline convention).

    Returns
    -------
    date
        The NYSE session date the timestamp belongs to.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_et = now_utc.astimezone(ET)
    today_et = now_et.date()
    # If the ET calendar date is a session day, it IS the session to stamp —
    # regardless of whether we are pre-open, mid-session, or post-close.
    if is_session(today_et):
        return today_et
    # Non-session day (weekend, holiday): the last completed session is on
    # or before the prior ET calendar day.
    return last_session_on_or_before(today_et - timedelta(days=1))
