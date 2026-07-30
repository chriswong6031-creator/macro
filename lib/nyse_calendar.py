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

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Plain messages only — never a '::' prefix through a logger (a level prefix
# pushes the workflow command off column 0 and GitHub drops it silently;
# see tests/test_gh_annotation_line_start.py).
_log = logging.getLogger(__name__)

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


def sessions_between(start: date, end: date) -> list[date]:
    """Every session date in the INCLUSIVE range [start, end], ascending.

    Empty when start > end. Callers wanting "strictly after d" pass
    `d + timedelta(days=1)` as start."""
    out: list[date] = []
    d = start
    while d <= end:
        if is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


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


def sessions_behind(latest: date, now: datetime | None = None) -> int:
    """How many completed sessions a store holding `latest` is missing.

    Counts sessions strictly after `latest` up to and including
    `expected_last_session(now)` — NOT up to today. On a session morning the
    current day's bar does not exist yet, so counting to today would report
    every store as one session staler than it is and trip a >N SLA a day early.

    0 = current. Negative is impossible: a store ahead of the calendar (a
    future-dated row) returns 0, since no completed session is missing."""
    return len(sessions_between(latest + timedelta(days=1), expected_last_session(now)))


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


def session_rows(df, date_col: str | None = None, *, label: str = "store",
                 keep_unparseable: bool = True):
    """Drop non-session rows from a dated frame — the #3721 weekend-row guard.

    Several EOD options stores accrue a row on non-session days: as of 2026-07-29
    ``data/cboe/gex.parquet`` carried 13 non-session rows of 39,
    ``data/cboe/putcall.parquet`` 13 of 39, ``data/options_skew/snapshots.parquet``
    8 of 28, ``data/options_ivspread/snapshots.parquet`` 6 of 21, and the
    ``data/polygon_gex/summary_*.parquet`` family ~11 of 39 dates.  A weekend row is
    NOT a harmless carry-forward duplicate: the builder recomputes IV, spot, walls and
    net-GEX off a stale carried-forward price, so the row is a fabricated observation.
    Left in, it corrupts three things at once — ``.iloc[-1]`` (the "latest" reading can
    be a Saturday), percentile/quantile windows (fabricated points in the distribution),
    and POSITIONAL lookbacks (``.iloc[-6]`` stops meaning "5 sessions ago") including
    any ``n_obs`` count used as an activation gate.

    Two frame shapes are supported:
      * ``date_col=None`` — the frame is indexed by date/DatetimeIndex.
      * ``date_col="date"`` — the dates live in that column (str or datetime).

    PER-ROW REALITY (the docstring used to overpromise here).  A value that cannot be
    read as a date is kept when ``keep_unparseable`` (the default), and that now
    genuinely includes null/NaT: ``pd.Timestamp(None)`` returns ``NaT`` rather than
    raising, and ``is_session(NaT)`` is False, so nulls used to be silently DROPPED by
    the very branch documented as keeping them.  Nulls are detected explicitly.

    NOT-A-DATED-FRAME is a WARNING, not a silent pass.  A missing ``date_col`` or a
    non-datetime index (a ``RangeIndex`` from a ``reset_index()`` or a hand-built test
    frame) makes this function a no-op, which is the worst outcome for a guard: the call
    reads as protection and does nothing.  Both cases log at WARNING and return the frame
    unchanged — the caller is doing something the guard cannot honour.

    FAIL-OPEN otherwise: if filtering would empty the frame the original is returned.  A
    calendar-arithmetic surprise must degrade to the old behaviour, never to a blank
    panel.  ``label`` names the store in the log lines (drops log at DEBUG — a drop is the
    normal case and this runs per-ticker inside the stamp pass, so INFO would flood).

    Returns the filtered frame (a view/copy per pandas' own semantics).
    """
    if df is None or len(df) == 0:
        return df
    try:
        import pandas as pd

        if date_col is not None:
            if date_col not in getattr(df, "columns", ()):
                _log.warning("session_rows(%s): no %r column — NOT filtered "
                             "(the guard is a no-op on this frame)", label, date_col)
                return df
            src = df[date_col]
        else:
            src = df.index
            if not isinstance(src, pd.DatetimeIndex):
                # A NUMERIC index is never a date index here, and it must not be coerced:
                # pd.Timestamp(0..2) yields 1970-01-01, which is a holiday, so a RangeIndex
                # frame would silently reach the all-non-session fail-open and read as
                # "filtered" in the logs. Reject it by dtype instead.
                if pd.api.types.is_numeric_dtype(src):
                    _log.warning("session_rows(%s): index is %s (numeric), not dates — "
                                 "NOT filtered (the guard is a no-op on this frame; pass "
                                 "date_col= or set a DatetimeIndex)",
                                 label, type(src).__name__)
                    return df
                coerced = pd.to_datetime(pd.Series(list(src)), errors="coerce")
                if coerced.isna().all():
                    _log.warning("session_rows(%s): index is %s, not dates — NOT filtered "
                                 "(the guard is a no-op on this frame)",
                                 label, type(src).__name__)
                    return df

        keep = []
        for raw in src:
            if raw is None or raw is pd.NaT or (isinstance(raw, float) and raw != raw):
                keep.append(keep_unparseable)     # null: keep by default, never silent
                continue
            try:
                ts = pd.Timestamp(raw)
            except (ValueError, TypeError):
                keep.append(keep_unparseable)     # unreadable: same contract
                continue
            if pd.isna(ts):                       # pd.Timestamp(None) -> NaT, no raise
                keep.append(keep_unparseable)
                continue
            keep.append(is_session(ts.date()))

        if not any(keep):
            _log.warning("session_rows(%s): every one of %d rows is non-session — "
                         "keeping the frame unfiltered (fail-open)", label, len(df))
            return df
        filtered = df[pd.Series(keep, index=df.index)] if date_col is not None else df[keep]
        if not len(filtered):
            return df
        if len(filtered) != len(df):
            _log.debug("session_rows(%s): dropped %d non-session row(s) of %d",
                       label, len(df) - len(filtered), len(df))
        return filtered
    except Exception as exc:  # noqa: BLE001
        _log.warning("session_rows(%s): filter failed (%s) — using the frame unfiltered",
                     label, exc)
        return df


def session_dates(dates, *, key=None, keep_unparseable: bool = True,
                  label: str = "store") -> list:
    """The session-only subset of an iterable of dates/strings, order preserved.

    The filename-keyed twin of :func:`session_rows` — for stores whose "rows" are files
    (``data/polygon_gex/chains/{DATE}.parquet`` carried 11 non-session snapshots of 39
    on 2026-07-29).  Pass ``key`` to extract the date from each item (e.g.
    ``key=lambda p: Path(p).stem`` for a list of paths); without it the items themselves
    must parse as dates — and a list of PATHS does not, so omitting ``key`` there makes
    the whole filter a silent no-op under ``keep_unparseable``.

    ``keep_unparseable`` defaults to True to match :func:`session_rows`' contract (never
    silently drop data the guard cannot read); both call sites pass it explicitly.

    FAIL-OPEN: returns the input unchanged when the filter would empty it or when the
    scan raises, so a calendar surprise degrades to the old behaviour.
    """
    import pandas as pd

    src = list(dates)          # materialise: an iterator would be consumed by the scan
    try:
        out = []
        for raw in src:
            probe = key(raw) if key is not None else raw
            if probe is None:
                if keep_unparseable:
                    out.append(raw)
                continue
            try:
                ts = pd.Timestamp(probe)
            except (ValueError, TypeError):
                if keep_unparseable:
                    out.append(raw)
                continue
            if pd.isna(ts):
                if keep_unparseable:
                    out.append(raw)
                continue
            if is_session(ts.date()):
                out.append(raw)
    except Exception as exc:  # noqa: BLE001
        _log.warning("session_dates(%s): filter failed (%s) — using the list unfiltered",
                     label, exc)
        return src
    if not out:
        _log.warning("session_dates(%s): every one of %d entries is non-session — "
                     "keeping the list unfiltered (fail-open)", label, len(src))
        return src
    if len(out) != len(src):
        _log.debug("session_dates(%s): dropped %d non-session entr(ies) of %d",
                   label, len(src) - len(out), len(src))
    return out
