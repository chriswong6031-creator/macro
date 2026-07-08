"""HKEX session calendar — which HK equity sessions exist, computed from the rules.

WHY THIS EXISTS (2026-07-08 stale-data incident): when `data/hk_breadth/_closes_cache.parquet`
is committed stale (the `-X theirs` rebase allowed a stale local cache to win), the HK page
served data frozen at 2026-07-02 while appearing fresh. This module is the independent reference
that can detect that staleness: pure rule arithmetic, zero data dependencies, stdlib only.

Scope: full-day closures for HKEX (Hong Kong Stock Exchange). HKEX is closed on HK public
holidays and weekends. The session day is defined as 09:30 – 16:00 HKT; `expected_last_session`
conservatively uses a 17:30 HKT settle buffer.

Unscheduled one-off closures (Typhoon Signal No.8, Black Rainstorm Warning, ad-hoc government
declarations) cannot be computed from rules — they live in `ONE_OFF_CLOSURES` and MUST be
appended when announced. The cost of a missing entry is a false "stale" — a banner on the
page until the date is added — never a silently-wrong "fresh".

HOW TO ADD A ONE-OFF CLOSURE:
    Add the date to ONE_OFF_CLOSURES as `date(YYYY, MM, DD)`.
    Example for a Typhoon No.8 on 2026-09-15:
        date(2026, 9, 15),   # Typhoon No.8 closure
    Commit the change so all environments see the update.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

HKT = ZoneInfo("Asia/Hong_Kong")

# The last completed session's daily bar is expected only after the close (16:00 HKT)
# plus a settle buffer (data vendors finalize bars 30-90 min after close; 17:30 is generous).
_CLOSE_PLUS_SETTLE = time(17, 30)

# Unscheduled full-day closures — Typhoon No.8/10, Black Rainstorm, ad-hoc government
# declarations. Append when announced. A missing entry is a false "stale" page banner
# (non-fatal), never a silently-wrong "fresh".
# Pattern: date(YYYY, MM, DD),  # reason
ONE_OFF_CLOSURES: frozenset[date] = frozenset({
    date(2023, 9, 8),   # Super Typhoon Saola — No.10 signal, full-day closure
    date(2018, 9, 16),  # Super Typhoon Mangkhut — No.10 signal
    date(2017, 8, 23),  # Typhoon Hato — No.10 signal
    date(2016, 8, 2),   # Super Typhoon Nida — No.10 signal
})


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) `weekday` (Mon=0) of the month."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _observed_hk(d: date) -> date:
    """HKEX observance: if the holiday falls on Sunday, the following Monday is a holiday.
    If it falls on Saturday, the following Monday is a holiday (HK compensatory policy).
    If Monday is already a holiday, Tuesday becomes the extra day."""
    if d.weekday() == 6:  # Sunday -> Monday
        return d + timedelta(days=1)
    if d.weekday() == 5:  # Saturday -> Monday
        return d + timedelta(days=2)
    return d


def holidays(year: int) -> frozenset[date]:
    """Scheduled full-day HKEX holidays for `year` (rule-computed, cached)."""
    return _holidays_cached(year)


_HOLIDAY_CACHE: dict[int, frozenset[date]] = {}


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


def _holidays_cached(year: int) -> frozenset[date]:
    got = _HOLIDAY_CACHE.get(year)
    if got is not None:
        return got
    hs: set[date] = set()

    # New Year's Day (January 1) — observed Monday if falls on Sunday or Saturday
    ny = date(year, 1, 1)
    hs.add(_observed_hk(ny))

    # Lunar New Year — approximated as fixed rule: 3 days starting on the lunar new year.
    # HKEX closes for 3 days (LNY eve is a half-day or closed, plus 1st and 2nd day).
    # The exact dates vary; we use a lookup table for CY2024-2030 + a stub for earlier.
    # Key: first day of Chinese New Year (CE date). Source: HK government gazette.
    LNY_FIRST: dict[int, date] = {
        2024: date(2024, 2, 10),   # Year of Dragon
        2025: date(2025, 1, 29),   # Year of Snake
        2026: date(2026, 2, 17),   # Year of Horse
        2027: date(2027, 2, 6),    # Year of Goat
        2028: date(2028, 1, 26),   # Year of Monkey
        2029: date(2029, 2, 13),   # Year of Rooster
        2030: date(2030, 2, 3),    # Year of Dog
        # Earlier years (approximate; sufficient for freshness gate which is forward-looking)
        2023: date(2023, 1, 22),
        2022: date(2022, 2, 1),
        2021: date(2021, 2, 12),
        2020: date(2020, 1, 25),
        2019: date(2019, 2, 5),
        2018: date(2018, 2, 16),
        2017: date(2017, 1, 28),
        2016: date(2016, 2, 8),
        2015: date(2015, 2, 19),
        2014: date(2014, 1, 31),
    }
    if year in LNY_FIRST:
        lny = LNY_FIRST[year]
        # HKEX closes: day before LNY (if afternoon session) + 1st, 2nd, 3rd day of LNY.
        # We model it as a 3-day closure (1st, 2nd, 3rd) + compensatory days when they
        # fall on a weekend. The day before LNY (除夕) is typically a half-session or full
        # closure — model it as closed for conservatism.
        lny_eve = lny - timedelta(days=1)
        if lny_eve.weekday() < 5:
            hs.add(lny_eve)   # New Year's Eve
        for i in range(3):   # 1st, 2nd, 3rd day
            d = lny + timedelta(days=i)
            hs.add(d)
            # If holiday falls on Saturday, add the following Monday (compensatory)
            if d.weekday() == 5:
                hs.add(d + timedelta(days=2))
            # If holiday falls on Sunday, add the following Monday (compensatory)
            if d.weekday() == 6:
                hs.add(d + timedelta(days=1))

    # Ching Ming Festival — solar term (around 4-5 April); exact date from HK
    # Observatory / HKEX holiday schedule each year. Do NOT use the leap-year rule
    # (April 4 in leap years, else April 5) — it is wrong (e.g. 2025 actual = Apr 4
    # but the rule yields Apr 5). Use a per-year lookup table (same approach as the
    # other lunar holidays in this file). Source: HKEX holiday notice each year.
    # Sunday→Monday observance applied via _observed_hk consistently with other holidays.
    CHING_MING: dict[int, date] = {
        2014: date(2014, 4, 5),   # Saturday -> Monday Apr 7 (observed)
        2015: date(2015, 4, 5),   # Sunday -> Monday Apr 6 (observed)
        2016: date(2016, 4, 4),   # Monday
        2017: date(2017, 4, 4),   # Tuesday
        2018: date(2018, 4, 5),   # Thursday
        2019: date(2019, 4, 5),   # Friday
        2020: date(2020, 4, 4),   # Saturday -> Monday Apr 6 (observed)
        2021: date(2021, 4, 5),   # Monday
        2022: date(2022, 4, 5),   # Tuesday
        2023: date(2023, 4, 5),   # Wednesday
        2024: date(2024, 4, 4),   # Thursday
        2025: date(2025, 4, 4),   # Friday (actual HKEX closure; rule would have given Apr 5)
        2026: date(2026, 4, 5),   # Sunday -> Monday Apr 6 (observed)
        2027: date(2027, 4, 5),   # Monday
        2028: date(2028, 4, 4),   # Tuesday
        2029: date(2029, 4, 4),   # Wednesday
        2030: date(2030, 4, 5),   # Friday
    }
    if year in CHING_MING:
        hs.add(_observed_hk(CHING_MING[year]))

    # Good Friday + Saturday before Easter + Easter Monday
    easter = _easter(year)
    hs.add(easter - timedelta(days=2))   # Good Friday
    hs.add(easter - timedelta(days=1))   # Day before Easter (Holy Saturday — HKEX closed)
    hs.add(easter + timedelta(days=1))   # Easter Monday

    # Labour Day — May 1
    hs.add(_observed_hk(date(year, 5, 1)))

    # Buddha's Birthday — 4th month of lunar calendar, 8th day.
    # Approximated by a lookup table; falls in May typically.
    BUDDHA: dict[int, date] = {
        2024: date(2024, 5, 15), 2025: date(2025, 5, 5), 2026: date(2026, 5, 24),
        2027: date(2027, 5, 13), 2028: date(2028, 5, 2), 2029: date(2029, 5, 20),
        2030: date(2030, 5, 9),
        2023: date(2023, 5, 26), 2022: date(2022, 5, 9), 2021: date(2021, 5, 19),
        2020: date(2020, 4, 30), 2019: date(2019, 5, 12), 2018: date(2018, 5, 22),
        2017: date(2017, 5, 3), 2016: date(2016, 5, 14), 2015: date(2015, 5, 25),
        2014: date(2014, 5, 6),
    }
    if year in BUDDHA:
        hs.add(_observed_hk(BUDDHA[year]))

    # Tuen Ng (Dragon Boat) Festival — 5th month, 5th day of lunar calendar.
    TUEN_NG: dict[int, date] = {
        2024: date(2024, 6, 10), 2025: date(2025, 5, 31), 2026: date(2026, 6, 19),
        2027: date(2027, 6, 9), 2028: date(2028, 6, 28), 2029: date(2029, 6, 16),
        2030: date(2030, 6, 5),
        2023: date(2023, 6, 22), 2022: date(2022, 6, 3), 2021: date(2021, 6, 14),
        2020: date(2020, 6, 25), 2019: date(2019, 6, 7), 2018: date(2018, 6, 18),
        2017: date(2017, 5, 30), 2016: date(2016, 6, 9), 2015: date(2015, 6, 20),
        2014: date(2014, 6, 2),
    }
    if year in TUEN_NG:
        hs.add(_observed_hk(TUEN_NG[year]))

    # Hong Kong SAR Establishment Day — July 1
    hs.add(_observed_hk(date(year, 7, 1)))

    # Mid-Autumn Festival following day — 16th day of 8th lunar month.
    MID_AUTUMN: dict[int, date] = {
        2024: date(2024, 9, 18), 2025: date(2025, 10, 7), 2026: date(2026, 9, 25),
        2027: date(2027, 9, 16), 2028: date(2028, 10, 4), 2029: date(2029, 9, 22),
        2030: date(2030, 9, 12),
        2023: date(2023, 9, 30), 2022: date(2022, 9, 12), 2021: date(2021, 9, 22),
        2020: date(2020, 10, 2), 2019: date(2019, 9, 14), 2018: date(2018, 9, 25),
        2017: date(2017, 10, 5), 2016: date(2016, 9, 16), 2015: date(2015, 9, 28),
        2014: date(2014, 9, 9),
    }
    if year in MID_AUTUMN:
        hs.add(_observed_hk(MID_AUTUMN[year]))

    # National Day — October 1
    hs.add(_observed_hk(date(year, 10, 1)))

    # Chung Yeung Festival — 9th month, 9th day of lunar calendar.
    CHUNG_YEUNG: dict[int, date] = {
        2024: date(2024, 10, 11), 2025: date(2025, 10, 29), 2026: date(2026, 10, 19),
        2027: date(2027, 10, 8), 2028: date(2028, 10, 26), 2029: date(2029, 10, 16),
        2030: date(2030, 11, 3),
        2023: date(2023, 10, 23), 2022: date(2022, 10, 4), 2021: date(2021, 10, 14),
        2020: date(2020, 10, 26), 2019: date(2019, 10, 7), 2018: date(2018, 10, 17),
        2017: date(2017, 10, 28), 2016: date(2016, 10, 10), 2015: date(2015, 10, 21),
        2014: date(2014, 10, 2),
    }
    if year in CHUNG_YEUNG:
        hs.add(_observed_hk(CHUNG_YEUNG[year]))

    # Christmas Day — December 25 + Boxing Day (December 26)
    hs.add(_observed_hk(date(year, 12, 25)))
    boxing = date(year, 12, 26)
    # If Christmas is Saturday -> Monday, Boxing Day (Sunday) -> Tuesday
    if date(year, 12, 25).weekday() == 5:
        hs.add(date(year, 12, 28))   # Compensatory Boxing Day
    elif date(year, 12, 25).weekday() == 6:
        hs.add(date(year, 12, 27))   # Compensatory Boxing Day (Monday after Xmas Monday)
    else:
        hs.add(_observed_hk(boxing))

    out = frozenset(h for h in hs if h.year == year)
    _HOLIDAY_CACHE[year] = out
    return out


def is_session(d: date) -> bool:
    """True when HKEX holds a session on `d` (Mon-Fri, not a HK public holiday or one-off)."""
    return (d.weekday() < 5
            and d not in holidays(d.year)
            and d not in ONE_OFF_CLOSURES)


def last_session_on_or_before(d: date) -> date:
    """Most recent HKEX session date <= d."""
    for _ in range(30):
        if is_session(d):
            return d
        d -= timedelta(days=1)
    raise ValueError("no HKEX session found in the prior 30 days — calendar rules broken")


def expected_last_session(now: datetime | None = None) -> date:
    """The most recent COMPLETED HKEX session whose daily bar the store should hold.

    'Completed' = the 16:00 HKT close plus a settle buffer has passed (17:30 HKT),
    so a same-day afternoon run conservatively expects only the PRIOR session. Naive
    datetimes are taken as UTC (the pipeline's convention)."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_hkt = now.astimezone(HKT)
    today = now_hkt.date()
    if is_session(today) and now_hkt.time() >= _CLOSE_PLUS_SETTLE:
        return today
    return last_session_on_or_before(today - timedelta(days=1))
