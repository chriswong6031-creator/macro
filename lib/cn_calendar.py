"""A-share (SSE/SZSE) session calendar — which mainland equity sessions exist, from the rules.

WHY THIS EXISTS: china.html had no engine-driven delayed-board disclosure because there was
no CN exchange calendar to measure "sessions behind" against — templates/china.html.j2 said so
in as many words ("There is no CN exchange calendar in lib/, so this claims NO session-count
verdict"), and scripts/freshness_sentinel.py therefore ran the china surface bake-only. The
2026-08-06 outage froze the US board for six days while the page re-baked every night; the
same failure on the China board had nothing watching it. This module is the independent
reference that makes the China board's own lag computable: pure rule arithmetic, zero data
dependencies, stdlib only. Mirrors lib/hk_calendar.py and lib/nyse_calendar.py.

Scope: full-day closures for the Shanghai and Shenzhen exchanges, which share one holiday
schedule. The session day is 09:30-15:00 CST; ``expected_last_session`` uses a 17:00 CST
settle buffer.

DIRECTION OF ERROR — the rule this table is built on
    Marking a real holiday as a session  → we over-count sessions behind → a false "stale"
        banner. Non-fatal, self-clearing, and the sentinel's 12-day china budget absorbs it.
    Marking a real session as a holiday  → we under-count → a silently-wrong "fresh".
        This is the dangerous direction and the reason this table is deliberately MINIMAL.

So the holiday spans below encode only days that are closed EVERY year. Mainland closures are
set annually by the State Council and routinely run longer than the statutory core (Spring
Festival is commonly 8-9 calendar days; Labour Day and Qingming are commonly 3-5). Those extra
days are intentionally NOT encoded — they land in the false-stale direction by construction.
The State Council also designates makeup workdays that turn a Saturday into a real session;
those are not encoded either, and a missed one costs at most one session of under-count, which
cannot by itself flip a >= 2-session verdict.

Because the table is deliberately incomplete, callers must not treat it as the only guard:
scripts/build_china_library.compute_board_staleness pairs it with a calendar-day backstop
(MAX_LEGIT_CLOSURE_DAYS) so a genuine long freeze is disclosed even if every rule here is wrong.

HOW TO ADD A ONE-OFF CLOSURE:
    Add the date to ONE_OFF_CLOSURES as `date(YYYY, MM, DD)`.
    Commit the change so all environments see the update.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")

# The last completed session's daily bar is expected only after the 15:00 CST close plus a
# settle buffer (vendors finalize bars 30-90 min after close; 17:00 is generous).
_CLOSE_PLUS_SETTLE = time(17, 0)

#: The longest closure the mainland calendar can legitimately produce, in CALENDAR days.
#: Spring Festival and National Day Golden Week both run ~9-10 days end to end. Callers use
#: this as a table-independent backstop: past it, the board is stale no matter what the
#: holiday rules below claim.
MAX_LEGIT_CLOSURE_DAYS = 11

# Unscheduled full-day closures. Append when announced. A missing entry is a false "stale"
# page banner (non-fatal), never a silently-wrong "fresh".
# Pattern: date(YYYY, MM, DD),  # reason
ONE_OFF_CLOSURES: frozenset[date] = frozenset()

# First day of Chinese New Year (CE date). Spring Festival is the one mainland closure long
# enough to matter most for a staleness verdict. Source: State Council annual notice; values
# match the LNY table in lib/hk_calendar.py.
LNY_FIRST: dict[int, date] = {
    2014: date(2014, 1, 31), 2015: date(2015, 2, 19), 2016: date(2016, 2, 8),
    2017: date(2017, 1, 28), 2018: date(2018, 2, 16), 2019: date(2019, 2, 5),
    2020: date(2020, 1, 25), 2021: date(2021, 2, 12), 2022: date(2022, 2, 1),
    2023: date(2023, 1, 22), 2024: date(2024, 2, 10), 2025: date(2025, 1, 29),
    2026: date(2026, 2, 17), 2027: date(2027, 2, 6), 2028: date(2028, 1, 26),
    2029: date(2029, 2, 13), 2030: date(2030, 2, 3),
}

# Qingming (清明) — solar term, 4-6 April. NOT the leap-year rule, which is wrong (2025 was
# Apr 4, the rule yields Apr 5). Values match the Ching Ming table in lib/hk_calendar.py,
# which is sourced from the exchange holiday notice each year.
QINGMING: dict[int, date] = {
    2014: date(2014, 4, 5), 2015: date(2015, 4, 5), 2016: date(2016, 4, 4),
    2017: date(2017, 4, 4), 2018: date(2018, 4, 5), 2019: date(2019, 4, 5),
    2020: date(2020, 4, 4), 2021: date(2021, 4, 5), 2022: date(2022, 4, 5),
    2023: date(2023, 4, 5), 2024: date(2024, 4, 4), 2025: date(2025, 4, 4),
    2026: date(2026, 4, 5), 2027: date(2027, 4, 5), 2028: date(2028, 4, 4),
    2029: date(2029, 4, 4), 2030: date(2030, 4, 5),
}

# Dragon Boat / Duanwu (端午) — lunar 5/5. Same festival and same lunar date HKEX observes as
# Tuen Ng, so the values match lib/hk_calendar.py's TUEN_NG table.
DRAGON_BOAT: dict[int, date] = {
    2014: date(2014, 6, 2), 2015: date(2015, 6, 20), 2016: date(2016, 6, 9),
    2017: date(2017, 5, 30), 2018: date(2018, 6, 18), 2019: date(2019, 6, 7),
    2020: date(2020, 6, 25), 2021: date(2021, 6, 14), 2022: date(2022, 6, 3),
    2023: date(2023, 6, 22), 2024: date(2024, 6, 10), 2025: date(2025, 5, 31),
    2026: date(2026, 6, 19), 2027: date(2027, 6, 9), 2028: date(2028, 6, 28),
    2029: date(2029, 6, 16), 2030: date(2030, 6, 5),
}

# Mid-Autumn (中秋) — lunar 8/15. The mainland closes on the festival day itself; HKEX instead
# closes the DAY AFTER (lunar 8/16), so lib/hk_calendar.py's MID_AUTUMN table is one day later
# than this one and additionally carries HK's Sunday->Monday observance. These are the lunar
# 8/15 dates directly, not derived from that table.
# Blast radius of a wrong entry here is bounded to ONE session in either direction, which
# cannot on its own reach the >= 2-session verdict; verify against the exchange notice when
# extending past 2030 rather than continuing the sequence by arithmetic.
MID_AUTUMN: dict[int, date] = {
    2014: date(2014, 9, 8), 2015: date(2015, 9, 27), 2016: date(2016, 9, 15),
    2017: date(2017, 10, 4), 2018: date(2018, 9, 24), 2019: date(2019, 9, 13),
    2020: date(2020, 10, 1), 2021: date(2021, 9, 21), 2022: date(2022, 9, 10),
    2023: date(2023, 9, 29), 2024: date(2024, 9, 17), 2025: date(2025, 10, 6),
    2026: date(2026, 9, 25), 2027: date(2027, 9, 15), 2028: date(2028, 10, 3),
    2029: date(2029, 9, 22), 2030: date(2030, 9, 12),
}

_HOLIDAY_CACHE: dict[int, frozenset[date]] = {}


def holidays(year: int) -> frozenset[date]:
    """Scheduled full-day SSE/SZSE closures for `year` (rule-computed, cached).

    Deliberately minimal — see the module docstring's DIRECTION OF ERROR note.
    """
    got = _HOLIDAY_CACHE.get(year)
    if got is not None:
        return got
    hs: set[date] = set()

    # New Year's Day. The State Council usually bridges this to the nearest weekend; only
    # Jan 1 itself is closed every year, so only Jan 1 is encoded.
    hs.add(date(year, 1, 1))

    # Spring Festival. The full closure commonly runs New Year's Eve through LNY+6, but the
    # span varies by year — 2019 closed Feb 4-8 only (eve..LNY+3) and traded again on Feb 11.
    # Only that invariant core — the eve plus LNY days 1-4 — is encoded; longer years leave
    # their tail days reading as sessions, which is the safe direction.
    lny = LNY_FIRST.get(year)
    if lny is not None:
        hs.add(lny - timedelta(days=1))          # 除夕 — New Year's Eve
        for i in range(4):                        # LNY days 1, 2, 3, 4
            hs.add(lny + timedelta(days=i))

    if year in QINGMING:
        hs.add(QINGMING[year])

    # Labour Day. Recent years run May 1-5; only May 1 is closed every year.
    hs.add(date(year, 5, 1))

    if year in DRAGON_BOAT:
        hs.add(DRAGON_BOAT[year])

    if year in MID_AUTUMN:
        hs.add(MID_AUTUMN[year])

    # National Day Golden Week — Oct 1-7, closed every year without exception.
    for i in range(7):
        hs.add(date(year, 10, 1) + timedelta(days=i))

    out = frozenset(h for h in hs if h.year == year)
    _HOLIDAY_CACHE[year] = out
    return out


def is_session(d: date) -> bool:
    """True when the mainland exchanges hold a session on `d`."""
    return (d.weekday() < 5
            and d not in holidays(d.year)
            and d not in ONE_OFF_CLOSURES)


def last_session_on_or_before(d: date) -> date:
    """Most recent A-share session date <= d."""
    for _ in range(30):
        if is_session(d):
            return d
        d -= timedelta(days=1)
    raise ValueError("no A-share session found in the prior 30 days — calendar rules broken")


def expected_last_session(now: datetime | None = None) -> date:
    """The most recent COMPLETED A-share session whose daily bar the store should hold.

    'Completed' = the 15:00 CST close plus a settle buffer has passed (17:00 CST), so a
    same-day afternoon run conservatively expects only the PRIOR session. Naive datetimes are
    taken as UTC (the pipeline's convention).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_cst = now.astimezone(CST)
    today = now_cst.date()
    if is_session(today) and now_cst.time() >= _CLOSE_PLUS_SETTLE:
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
