#!/usr/bin/env python3
"""Cron-liveness dead-man switch for the authoritative US nightly (daily.yml).

WHY THIS EXISTS — the 2026-08-11/08-12 outage.  The US nightly went dark for two
consecutive sessions and NOTHING reported it; the operator found it by looking at
the site.  Every instrument we already had was blind to this failure, each for its
own structural reason:

  * ``heartbeat.yml`` -> ``scripts.healthcheck`` measures ``run_status.json``'s
    ``last_run`` against ``max_age_hours=96``.  96h is sized so a Friday bake still
    looks alive at the Monday 14:30Z check (Fri 22:40Z -> Mon 14:30Z is 63.8h), so
    it CANNOT trip on one — or two — missed nightlies.  It is a four-day instrument.
  * ``scripts/freshness_sentinel.py`` (VPS, every 30 min) budgets Prophet at
    ``PROPHET_MAX_SESSIONS_BEHIND=1``.  That budget is correct and cannot be
    tightened: between the 20:00Z close and the 22:30Z bake, "1 session behind" IS
    the healthy state.  So a missed bake for session D cannot honestly breach until
    after session D+1's close — ~24h of designed blindness.
  * ``heartbeat.yml`` also runs ``runs-on: [self-hosted, macstudio]`` — the same
    pool as the lane it watches.  A watchdog that shares fate with its subject
    reports nothing exactly when it matters.

None of those is wrong; they measure DATA staleness with weekend-safe budgets.  The
failure mode they all miss is the one that actually happened: **the scheduled run
was never created at all.**  #5362 pushed daily.yml past GitHub's silent ~512,000
byte processing cap, and the cron simply stopped firing — workflow state read
``active``, githubstatus was all-operational, and the stranded dispatches sat queued
with zero jobs (see ``tests/test_workflow_file_size.py`` for that postmortem).  A
data-staleness instrument can only infer that hours-to-days later, through its
weekend padding.  Asking GitHub "did a run get created?" sees it immediately.

WHAT THIS CHECKS.  Four questions, in the order a human would ask them:

  A. RUN CREATED   — did daily.yml produce a run at all since the last completed
                     NYSE session's fire window?  Catches: the workflow-file strand,
                     a disabled workflow, a deleted/renamed cron, GitHub dropping
                     the schedule.  This is the check that would have fired on
                     2026-08-12 at 08:00Z, ~9.5h into the outage.
  B. RUN CONCLUDED — did one of those runs actually finish ``success``?  Catches
                     the 2026-08-12 signature: six dispatches force-cancelled by a
                     live fleet session, one stuck queued.  A FRESH in-flight run is
                     INDETERMINATE, never a breach — the nightly legitimately runs
                     for hours.  But an in-flight run older than IN_FLIGHT_MAX_AGE
                     is a POSITIVE observation of a wedge, not a long bake: on
                     2026-08-16/17 a job queued on a runner label with no live
                     runner held run 31977372592 open ~24h while every check read
                     the eternal in-flight as "still baking" and the boards froze.
                     Age turns "still baking" into "hung or hostage" — breach.
  C. DATA ADVANCED — did ``site/prophet/index.json``'s ``source_asof`` actually move?
                     Catches the case A and B cannot see: a run that concludes green
                     while the ledger silently fails to advance (the #4779 law — an
                     absence of red is not a pass).  This is also the backstop for a
                     run that hangs forever and so never leaves INDETERMINATE in B.
                     Weekend hole (closed 2026-08-17): with a flat budget of 1, a
                     missed FRIDAY bake reads "1 behind" all weekend and could not
                     alarm before Tuesday.  Once the fire window is STALE_GRACE
                     behind us and no fresh run is alive, even 1-behind is a breach
                     — a healthy Friday bake lands hours before the grace expires.
  D. EVERY BOARD   — did each of the FIVE market boards (US, China, Hong Kong,
                     Canada, International) advance, each measured on its OWN
                     exchange calendar?  Catches the 2026-08-14 Canada freeze: the
                     Canadian board sat at ``as_of=2026-08-13`` for five days while
                     daily.yml ran green, the render lane re-committed the file
                     nightly, and its four siblings advanced.  C could not see it —
                     C grades one artifact, and it belongs to a different market.

WHY D IS A SEPARATE CHECK RATHER THAN A WIDER C.  A re-render is not an advance and
a green lane is not a green board, but the deeper reason is the calendar: HK and the
mainland close hours BEFORE the ET nightly fires, so their boards routinely carry a
session the US board has not reached yet (measured 2026-08-04: hk/cn read 08-04 while
us read 07-31).  One shared NYSE anchor would call that healthy state stale and, in
the other direction, paper over a real freeze.  See MARKET_BOARDS for the per-market
budgets, the mainland's table-independent holiday floor, and the one market
(International) that no single exchange calendar can govern.

VERDICT DISCIPLINE (borrowed verbatim from freshness_sentinel).  Blindness is never
a breach.  An unreadable API response, an empty run list, a missing index file, an
unparseable timestamp -> INDETERMINATE: reported as a ``::warning``, exit stays 0.
A false alarm every night trains the operator to ignore the channel, which is how a
dead-man switch dies.  Only a POSITIVE observation of absence fails.

FRESHNESS IS MEASURED AGAINST THE EXCHANGE CALENDAR, never the wall clock — the
cross-cutting lesson of every stale-store incident here.  When the pipeline dies,
every store freezes together and agrees with itself; only the calendar knows a
completed session is missing.  A calendar anchor also means a weekend or a market
holiday can never manufacture a breach, which is what lets this budget be tight
where the 96h heartbeat has to be loose.

WHERE IT RUNS.  ``.github/workflows/nightly-liveness.yml``, on GitHub-hosted
``ubuntu-latest`` — deliberately NOT the macstudio pool, so the watchdog cannot be
taken out by whatever took out the nightly.  The repo is public, so that runner is
free (CI self-hosted migration Wave 1, #5465).

Usage:
    python3 scripts/check_nightly_liveness.py                 # live: fetch + evaluate
    python3 scripts/check_nightly_liveness.py --selftest      # synthetic assertions
    python3 scripts/check_nightly_liveness.py --runs-json F --index-json G   # offline
    python3 scripts/check_nightly_liveness.py --site-root DIR # offline check D

Exit codes:
    0  healthy, or INDETERMINATE (blind — see above)
    1  a positive observation of absence: no run, no success, stale data, or a market
       board that did not advance
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL by contract (tests/test_check_script_import_pinning.py). A
# `if str(REPO_ROOT) not in sys.path` guard is NOT a strong pin: it is not
# guaranteed to run, and a root that is merely PRESENT further down sys.path
# still loses to a foreign package ahead of it. This guard runs from a bare
# `python3 scripts/check_nightly_liveness.py` on a GitHub-hosted runner whose
# CWD and sys.path[0] are not this repo, which is exactly the case the pin
# exists for.
sys.path.insert(0, str(REPO_ROOT))

from lib.nyse_calendar import expected_last_session, sessions_behind  # noqa: E402

#: The lane this guard watches.  daily.yml is Build B — the sole authoritative,
#: ledger-advancing nightly.  Build A (closing-bell.yml) ships a provisional site
#: and is NOT a substitute: on 2026-08-11/12 closing-bell ran green both nights
#: while the board it re-rendered still read ``price_through=2026-08-10``, because
#: the price store is advanced by daily.yml's ``collect`` job.  A green Build A
#: alongside a dead Build B is exactly the shape this guard must not be fooled by.
WORKFLOW_FILE = "daily.yml"

#: Repo the runs are read from.  ``GITHUB_REPOSITORY`` is always set in Actions;
#: the literal is the local-run fallback.  A wrong slug 404s, which lands in
#: INDETERMINATE rather than a false green — but it also means a typo here makes
#: the guard permanently blind, so tests/test_nightly_liveness.py pins it against
#: the git remote.
DEFAULT_REPO = (
    os.environ.get("GITHUB_REPOSITORY") or "mastermindx-market-intelligence/macro"
)

#: Safe-earliest boundary for "the bake for session D should have fired".  The DST
#: cron pair is 22:30Z (EDT) / 23:30Z (EST) and et_gate keeps exactly one, so any
#: run created at or after D 22:00Z is the D bake.  Deliberately 30 min early: this
#: is a floor for "a run exists", not a punctuality check.
FIRE_BOUNDARY_UTC = time(22, 0)

#: Keep in lockstep with daily.yml's schedule / et_gate (tests/test_daily_et_gate.py).
EDT_CRON = "30 22 * * *"
EST_CRON = "30 23 * * *"

#: How far behind the calendar ``source_asof`` may sit before check C fails.
#: 1 session, because the watchdog's own schedule (see the workflow) runs AFTER the
#: bake window: at 08:00Z on D+1 a healthy store reads D (0 behind), and a bake that
#: is merely running long still reads D-1 (1 behind) and must not alarm.  Two behind
#: means a whole session produced nothing — the 2026-08-11 signature.
MAX_SESSIONS_BEHIND = 1

#: An in-flight run older than this is a WEDGE, not a long bake.  The serial
#: worst case through daily.yml's own caps (et_gate + collect 240m + engine 300m
#: + tails) is ~13h; 14h clears it while the 14:00Z look still pages the same
#: day for a 22:30Z fire (15.5h > 14h; the 08:00Z look at 9.5h keeps its
#: designed tolerance).  2026-08-16/17 calibration: the hostage run was alive
#: 24h+ and every look before this constant existed read it as INDETERMINATE.
IN_FLIGHT_MAX_AGE = timedelta(hours=14)

#: Weekend-hole closure for check C.  Once ``now >= boundary + STALE_GRACE`` and
#: no fresh run is alive, a store even ONE session behind is a breach: a healthy
#: bake fires 22:30Z and lands its store hours before 08:00Z (= 22:00Z + 10h).
#: Sized to the same 08:00Z look the workflow schedule already documents as
#: "comfortably past a healthy bake"; an in-flight run under IN_FLIGHT_MAX_AGE
#: still excuses it (a slow-but-alive bake must not page at 08:00Z).
STALE_GRACE = timedelta(hours=10)

#: Runs older than this are irrelevant to today's verdict; keeps the API page small.
LOOKBACK_DAYS = 7


# ─────────────────────────────────────────────────────────────────────────────
# check D — per-market board freshness
# ─────────────────────────────────────────────────────────────────────────────
#
# WHY D EXISTS.  Checks A/B/C above watch the LANE (daily.yml) and ONE artifact
# (site/prophet/index.json, the US Prophet board).  All five market boards are baked
# by that same lane, so A and B already cover "did the nightly run" for every market
# — but C's dual-read covers only US.  On 2026-08-14 that gap opened for real:
# site/factordata/canada_standouts.json froze at ``as_of=2026-08-13`` and was still
# frozen five days later, while daily.yml ran green, the render lane re-committed the
# file every day, and its US/HK/mainland siblings all advanced to 2026-08-14.  Every
# instrument we owned was satisfied: the lane was green, the file's git mtime was
# minutes old, and the ONE stamp anyone graded belonged to a different market.  A
# re-render is not an advance, and a green lane is not a green board.
#
# EACH MARKET IS GRADED ON ITS OWN EXCHANGE CALENDAR, never on NYSE and never on the
# wall clock.  This is not pedantry: HK and the mainland close hours BEFORE the ET
# nightly fires, so their boards routinely carry a session date the US board has not
# reached yet (measured 2026-08-04: hk/cn read 2026-08-04 while us read 2026-07-31).
# Grading those against expected_last_session(NYSE) would read the healthy state as
# stale in one direction and paper over a real freeze in the other.
#
# THE COARSE FORM ONLY.  Check C has two branches: a SHARP one ("a run concluded
# success for session D and the store is still on D-1") and a COARSE one ("the store
# is more than N sessions behind").  D uses only the coarse one, on purpose.  The
# sharp branch compares the store against the session THE BAKE WAS FOR, and that
# session is a NYSE date; at the 14:00Z slot the HK and mainland calendars have
# already rolled forward to a session whose bake has not fired yet, so a sharp
# comparison would page every weekday afternoon on a healthy estate.  The per-market
# budgets below absorb exactly that one session, which is what makes the coarse form
# safe across five different session clocks.

#: How the guard reaches each market's session calendar.  ``"weekday"`` is the
#: documented degradation for a market no single exchange calendar can govern.
_CALENDAR_MODULES = {
    "nyse": "lib.nyse_calendar",
    "cn": "lib.cn_calendar",
    "hk": "lib.hk_calendar",
    "tsx": "lib.tsx_calendar",
}


class _WeekdayCalendar:
    """Mon-Fri approximation for a board no single exchange calendar can govern.

    ``intl`` is a union of eight-plus venues (Tokyo, London, Seoul, Sydney, Mumbai,
    Milan, Taipei, Madrid — read straight off the board's own tickers: 4004.T, EMG.L,
    066570.KS, SIG.AX, PHOENIXLTD.NS, TIT.MI, 1303.TW, ACS.MC).  Their holiday
    schedules are disjoint, so there is no session calendar to write: on almost every
    weekday SOME covered venue trades, and the board's stamp advances when any of them
    does.  Weekday arithmetic is the honest approximation of that union.

    DIRECTION OF ERROR: a day on which every covered venue happened to be closed
    (realistically only Jan 1, and Dec 25 for the western half) is still counted as a
    session here, so this over-counts how far behind a board is — a false "stale",
    never a silently-wrong "fresh".  The market's budget carries a documented +2
    tolerance for exactly that, which is why intl's budget is 3 where the
    calendar-backed markets run at 1.

    Settle at 22:00 UTC: after every covered venue's close (Tokyo 06:00Z, London
    16:30Z), so "yesterday was completed" is true for all of them at once.
    """

    _SETTLE_UTC = time(22, 0)

    @classmethod
    def expected_last_session(cls, now: datetime) -> date:
        instant = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        instant = instant.astimezone(timezone.utc)
        today = instant.date()
        if today.weekday() < 5 and instant.time() >= cls._SETTLE_UTC:
            return today
        day = today - timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day

    @classmethod
    def sessions_behind(cls, latest: date, now: datetime) -> int:
        end = cls.expected_last_session(now)
        count, day = 0, latest
        while day < end:
            day += timedelta(days=1)
            if day.weekday() < 5:
                count += 1
        return count


#: The five Prophet market boards, each with the artifact that carries its own
#: "as of what session are these picks" stamp and the calendar that stamp lives on.
#:
#: ``max_sessions_behind`` is 1 for every calendar-backed market, for the reason
#: PROPHET_MAX_SESSIONS_BEHIND is 1: the guard's own slots (08:00Z / 14:00Z) straddle
#: the bake, so exactly one session of lag is the healthy state at some hour of the
#: day and the SECOND missed session is the breach.  Measured, not assumed — at
#: 14:00Z the HK calendar has rolled to today while today's bake fires at 22:30Z, so
#: a healthy HK board reads 1 behind every weekday afternoon.
#:
#: ``min_calendar_days`` is a table-INDEPENDENT floor that must ALSO be exceeded
#: before a breach is declared, and it is set for the mainland alone.  lib/cn_calendar
#: is deliberately minimal (its own docstring: a missing holiday reads as a false
#: "stale", never a silently-wrong "fresh"), and the State Council routinely extends
#: Spring Festival and Golden Week past the statutory core the table encodes — 2026
#: encodes Feb 16-20, the real closure runs longer.  Those un-encoded days are phantom
#: sessions, so a bare 1-session budget would page every February and every October on
#: a board behaving exactly as it should.  MAX_LEGIT_CLOSURE_DAYS (11) is the constant
#: lib/cn_calendar publishes for precisely this pairing, and it is what
#: build_china_library.compute_board_staleness already pairs with.
#:
#: The floor is NOT always on.  Phantom sessions can only accrue while the exchange is
#: shut, so it applies only when the calendar places a scheduled weekday closure between
#: the board's stamp and the session we expect (``_holiday_in_gap``).  Outside a holiday
#: window the mainland pages at 2 sessions like every other market.  Measured against the
#: 2026-08-14 freeze shape, that narrowing moves the mainland's first page from
#: 2026-08-26 to 2026-08-19 while leaving Spring Festival and Golden Week silent.
#: COST, NAMED, AND IT IS BIGGER THAN IT LOOKS: a mainland board that dies ON THE EVE of
#: a long closure is caught at 11+ calendar days rather than 2 sessions, and — unlike
#: every other market — NOTHING ELSE IS WATCHING IT IN THE MEANTIME.  Checks A and B
#: watch WORKFLOW_FILE (daily.yml), and daily.yml does NOT bake the mainland or HK
#: boards: it iterates build_canada_library + build_intl_library (daily.yml:4365), while
#: build_china_library + build_hk_library are baked by asia-close.yml:696.  So for cn and
#: hk, check D is the ONLY instrument in this guard, and inside a closure window the
#: floor is a real uncovered gap rather than a delay behind a faster check.  Accepted
#: here because the alternative is a false page every Spring Festival and every Golden
#: Week, which mutes the channel; the durable fix is to teach checks A and B about
#: asia-close.yml, which is a wider change than this one.
#:
#: MEASURED, not assumed.  Sweeping a healthy board (stamped by the most recent 22:30 ET
#: fire) across every 08:00Z and 14:00Z slot of 2026, 2027 and 2028 produces ZERO breaches
#: on all five markets.  On a board frozen after the Fri 2026-08-14 bake, the first page
#: lands: hk/cn 08-18 14:00Z, us/ca 08-19 08:00Z, intl 08-21 08:00Z.  Re-run that sweep
#: before changing any budget here — the numbers are the argument.
MARKET_BOARDS: tuple[dict, ...] = (
    {
        # NOT redundant with check C, and do not "deduplicate" them. C reads
        # site/prophet/index.json's ``source_asof``, which build_prophet derives from the
        # PRICE watermark (_source_staleness["price_through"], build_prophet.py:1845);
        # this reads the board's own selection date. They freeze independently and on
        # origin/main @789e6e10 they already disagree — source_asof=2026-08-13 while
        # us_standouts as_of=2026-08-14.
        "market": "us",
        "label": "US",
        "path": "site/factordata/us_standouts.json",
        "stamp_known_absent": False,
        "field": "as_of",
        "calendar": "nyse",
        "max_sessions_behind": 1,
        "min_calendar_days": None,
    },
    {
        "market": "cn",
        "label": "China",
        "path": "site/factordata/china_standouts.json",
        "stamp_known_absent": False,
        "field": "as_of",
        "calendar": "cn",
        "max_sessions_behind": 1,
        "min_calendar_days": 11,   # lib.cn_calendar.MAX_LEGIT_CLOSURE_DAYS
    },
    {
        "market": "hk",
        "label": "Hong Kong",
        "path": "site/factordata/hk_standouts.json",
        "stamp_known_absent": False,
        "field": "as_of",
        "calendar": "hk",
        "max_sessions_behind": 1,
        "min_calendar_days": None,
    },
    {
        "market": "ca",
        "label": "Canada",
        "path": "site/factordata/canada_standouts.json",
        "stamp_known_absent": False,
        "field": "as_of",
        "calendar": "tsx",
        "max_sessions_behind": 1,
        "min_calendar_days": None,
    },
    {
        "market": "intl",
        "label": "International",
        # NOTE: this board's ``as_of`` is None on every commit in main's history —
        # compute_intl_alpha carries no as_of on any return path (documented at
        # scripts/build_intl_library.py, adversarial review D1, PR #5674), so the
        # stamp never reaches the artifact.  D therefore reports International as
        # INDETERMINATE every run and says why, rather than inventing a verdict.
        # tests/test_nightly_liveness.py pins that as a KNOWN blind spot so the day
        # the builder starts stamping, the test is what tells us to expect a grade.
        "path": "site/factordata/intl_setups.json",
        "stamp_known_absent": True,
        "field": "as_of",
        "calendar": "weekday",
        "max_sessions_behind": 3,   # 1 + the +2 weekday-approximation tolerance
        "min_calendar_days": None,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# pure evaluation core — every input injected, so tests pin behaviour not plumbing
# ─────────────────────────────────────────────────────────────────────────────
def _parse_dt(value: object) -> "datetime | None":
    """Parse a GitHub ISO-8601 timestamp.  Unparseable -> None (blindness, not breach)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_date(value: object) -> "date | None":
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def intended_schedule_cron(when: datetime) -> str:
    """Which daily.yml cron the America/New_York regime intends at ``when``."""
    instant = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    offset = instant.astimezone(ZoneInfo("America/New_York")).utcoffset()
    return EDT_CRON if offset == timedelta(hours=-4) else EST_CRON


def is_et_gate_skip(row: dict, *, now: datetime) -> bool:
    """True when a schedule run's run-name is the off-regime DST cron.

    Duplicated in scripts/prophet_rescue.py on purpose (the two organs must not
    share fate).  Unlabelled successes use ``counts_as_bake``.
    """
    if row.get("event") != "schedule" or row.get("conclusion") != "success":
        return False
    title = " ".join(str(row.get(k) or "") for k in ("display_title", "name"))
    if EDT_CRON not in title and EST_CRON not in title:
        return False
    when = _parse_dt(row.get("created_at")) or now
    return intended_schedule_cron(when) not in title


def counts_as_bake(row: dict, recent: list, *, now: datetime) -> bool:
    """A success that ran the nightly, not an et_gate no-op.

    31851452961's display_title was just ``daily`` and run_started_at equalled
    created_at (queued pending), so duration cannot identify a skip.  An
    unlabelled schedule success next to a cancelled schedule sibling is that
    night's shape.
    """
    if row.get("conclusion") != "success":
        return False
    if is_et_gate_skip(row, now=now):
        return False
    if row.get("event") == "schedule":
        title = " ".join(str(row.get(k) or "") for k in ("display_title", "name"))
        named = EDT_CRON in title or EST_CRON in title
        if not named and any(
            sib.get("event") == "schedule" and sib.get("conclusion") == "cancelled"
            for sib in recent
        ):
            return False
    return True


def expected_fire_after(now: datetime) -> "tuple[date, datetime]":
    """The session whose bake we are owed, and the instant its fire window opens.

    Anchored on ``expected_last_session`` so weekends and market holidays can never
    manufacture a breach: on a Saturday this resolves to Friday's session and asks
    for Friday's 22:00Z bake, which already happened.
    """
    session = expected_last_session(now)
    boundary = datetime.combine(session, FIRE_BOUNDARY_UTC, tzinfo=timezone.utc)
    return session, boundary


def _market_calendar(name: str):
    """The session calendar a market named.  Raises so the caller maps it to INDETERMINATE.

    Lazy and unguarded HERE on purpose: the one caller wraps it, so an unimportable or
    renamed calendar module degrades that ONE market to a named blind spot instead of
    crashing the pass or silently greening all five.
    """
    if name == "weekday":
        return _WeekdayCalendar
    module = _CALENDAR_MODULES[name]
    return __import__(module, fromlist=["sessions_behind"])


def _holiday_in_gap(cal, stamp: date, now: datetime) -> bool:
    """Does the market's calendar place a scheduled weekday closure between ``stamp`` and
    the session we expect?

    This is what narrows the mainland's calendar-day floor from "always on" to "only
    inside a closure window".  The floor exists to absorb PHANTOM sessions — weekdays
    lib/cn_calendar counts as sessions because the State Council extended a holiday past
    the statutory core the table encodes — and phantom sessions can only accrue while the
    exchange is shut.  Outside a holiday window there is nothing for the floor to excuse,
    so the mainland pages at the same 2 sessions as everyone else instead of waiting 12
    calendar days.  Measured against the 2026-08-14 freeze shape: 2026-08-26 -> 2026-08-19.
    """
    end = cal.expected_last_session(now)
    day = stamp
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5 and day in cal.holidays(day.year):
            return True
    return False


def evaluate_market_boards(
    boards: "dict[str, dict | None] | None",
    now: datetime,
) -> "tuple[list[str], list[str], dict]":
    """Check D: per-market board staleness, each on its own exchange calendar.

    ``boards`` maps a MARKET_BOARDS ``market`` id to that artifact's parsed JSON, or to
    None when it could not be read.  ``None`` for the whole argument means check D was
    not requested (offline callers, and every pre-D test) and produces nothing.

    Blindness is never a breach, per market and independently: an absent artifact, an
    absent or unparseable stamp, or a calendar that will not import degrades THAT market
    to a named ``::warning`` and leaves the other four graded.  Only a positive
    observation of absence — a readable stamp, on a working calendar, past its budget —
    fails, and every message names its market.
    """
    fail: list[str] = []
    warn: list[str] = []
    facts: dict[str, Any] = {}
    if boards is None:
        return fail, warn, facts

    states: dict[str, Any] = {}
    facts["boards"] = states
    for spec in MARKET_BOARDS:
        market, label, path = spec["market"], spec["label"], spec["path"]
        state: dict[str, Any] = {"as_of": None, "behind": None}
        states[market] = state

        payload = boards.get(market)
        # isinstance, not `is None`: load_index already maps a non-dict artifact to None,
        # but this is a PURE function and its blindness contract must hold for every
        # caller. A board that becomes a JSON array would otherwise raise here — and a
        # traceback out of a dead-man switch is a page about the wrong thing.
        if not isinstance(payload, dict):
            warn.append(
                f"INDETERMINATE [{label}]: {path} is absent or unreadable — this market "
                "is UNGRADED, not green. If the path is right, check the lane's "
                "sparse-checkout list."
            )
            continue

        raw = payload.get(spec["field"])
        state["as_of"] = raw
        stamp = _parse_date(raw)
        if stamp is None:
            if spec["stamp_known_absent"]:
                warn.append(
                    f"INDETERMINATE [{label}]: {path} carries no usable "
                    f"{spec['field']} ({raw!r}). This board has NEVER carried one — see "
                    "MARKET_BOARDS — so it is a standing, named blind spot rather than "
                    "a new fault. It is not graded and must not be read as healthy."
                )
            else:
                # NOT blindness, and this distinction is the whole point. Blindness is
                # "we cannot see"; here we CAN see the artifact and can see that it
                # refuses to say which session it is for. A board that carried a stamp
                # yesterday and publishes none today is a POSITIVE observation that its
                # producer broke — and it is the failure that would otherwise switch
                # this market off silently and permanently. build_canada_library.py:1093
                # resolves `as_of = (alpha or {}).get("as_of")`, so a missing alpha
                # publishes a null stamp: without this branch, check D would go quiet on
                # the exact market it was written for and read green forever.
                fail.append(
                    f"BOARD PUBLISHED WITHOUT A STAMP [{label}]: {path} is readable but "
                    f"carries no usable {spec['field']} ({raw!r}). Its producer stopped "
                    "stating which session the board is for, which silences every "
                    "freshness instrument for this market — a regression, not blindness."
                )
            continue

        try:
            behind = _market_calendar(spec["calendar"]).sessions_behind(stamp, now)
        except Exception as exc:  # noqa: BLE001 — a broken calendar blinds ONE market
            warn.append(
                f"INDETERMINATE [{label}]: {spec['calendar']} calendar unusable "
                f"({exc!r}); this market is ungraded"
            )
            continue
        state["behind"] = behind

        budget = spec["max_sessions_behind"]
        if behind <= budget:
            continue

        floor = spec["min_calendar_days"]
        if floor is not None and (now.date() - stamp).days <= floor:
            # The table-independent holiday floor. See MARKET_BOARDS for why the
            # mainland alone carries one and what it costs. It applies only INSIDE a
            # closure window: a broken holiday probe falls back to applying it, because
            # blindness must never manufacture a page.
            try:
                in_closure = _holiday_in_gap(
                    _market_calendar(spec["calendar"]), stamp, now)
            except Exception:  # noqa: BLE001 — a broken probe suppresses, never pages
                in_closure = True
            if in_closure:
                warn.append(
                    f"INDETERMINATE [{label}]: board is {behind} sessions behind "
                    f"({stamp.isoformat()}), only {(now.date() - stamp).days} calendar "
                    f"days old, and a scheduled exchange closure falls in that gap — "
                    f"inside the {floor}-day longest-legitimate-closure floor, so this "
                    "is a holiday shape rather than a proven freeze."
                )
                continue

        fail.append(
            f"STALE BOARD [{label}]: {path} still reads {spec['field']}="
            f"{stamp.isoformat()}, {behind} completed {spec['calendar'].upper()} "
            f"sessions behind (limit {budget}). The board was re-rendered but did not "
            "advance — a green lane and a fresh git mtime both look exactly like this."
        )

    return fail, warn, facts


def evaluate(
    runs: "list[dict] | None",
    index: "dict | None",
    now: datetime,
    *,
    max_sessions_behind: int = MAX_SESSIONS_BEHIND,
    boards: "dict[str, dict | None] | None" = None,
) -> dict:
    """Pure verdict over the four checks.  See module docstring for the contract."""
    fail: list[str] = []
    warn: list[str] = []
    facts: dict[str, Any] = {}

    session, boundary = expected_fire_after(now)
    facts["expected_session"] = session.isoformat()
    facts["fire_boundary"] = boundary.isoformat()

    # ── A. RUN CREATED ──────────────────────────────────────────────────────
    if runs is None:
        warn.append(
            f"INDETERMINATE: could not read {WORKFLOW_FILE} runs from the API "
            "(guard is blind, not green)"
        )
        recent: list[dict] = []
    else:
        recent = [
            r for r in runs
            if (dt := _parse_dt(r.get("created_at"))) is not None and dt >= boundary
        ]
        facts["runs_since_boundary"] = len(recent)
        if not recent:
            # The 2026-08-11 signature: the cron did not fire at all.
            fail.append(
                f"NO RUN: {WORKFLOW_FILE} created no run since {boundary.isoformat()} "
                f"(bake owed for session {session.isoformat()}). A stranded workflow "
                "file, a disabled workflow or a dropped schedule all look like this — "
                "check the file size against tests/test_workflow_file_size.py first."
            )

    # ── B. RUN CONCLUDED SUCCESS ────────────────────────────────────────────
    # A no-success night is NOT judged here: the verdict is deferred to C, because
    # the run-level conclusion is a SINGLE-LANE LATCH, not a product verdict. The
    # first live night this guard was evaluated against (2026-08-13) proved it:
    # the recovery bake concluded `cancelled` — engine's final commit step lost a
    # push race against a main moving ~1/min and one offrender lane was cancelled
    # — while 17/19 jobs were green and the picks landed on main (asof advanced,
    # 25 fresh plans). Failing on the conclusion alone would have paged the
    # operator at 08:00Z about a healthy night; the DUAL-READ leads, the state
    # verdict is the footnote (the standing instrument-vs-market law, applied to
    # our own instrument).
    baked = False
    no_success_detail: "str | None" = None
    # In-flight age triage over the FULL fetched window, not just `recent`: a
    # hostage run created before this session's boundary (a Thursday run still
    # alive on Saturday) must not become invisible by falling out of `recent`.
    wedged: list[str] = []
    live_fresh = False
    for row in (runs or []):
        if row.get("status") == "completed":
            continue
        created_live = _parse_dt(row.get("created_at"))
        if created_live is None:
            # Unparseable timestamp: cannot prove a wedge — blindness, not breach.
            live_fresh = True
            continue
        age = now - created_live
        if age > IN_FLIGHT_MAX_AGE:
            wedged.append(
                f"run {row.get('id')} {row.get('status')} for "
                f"{age.total_seconds() / 3600:.1f}h"
            )
        else:
            live_fresh = True
    if wedged:
        facts["wedged_in_flight"] = wedged
        fail.append(
            "WEDGED IN FLIGHT: "
            + "; ".join(wedged)
            + f" (cap {IN_FLIGHT_MAX_AGE.total_seconds() / 3600:.0f}h — the serial "
            "worst case through daily.yml's own job caps is ~13h). A run alive this "
            "long is a hung bake or a hostage: on 2026-08-16/17 a job queued on a "
            "runner label with no live runner held a run open 24h+, pended the next "
            "night's slot behind it, and froze every Prophet board while this check "
            "read the eternal in-flight as 'still baking'. Read the run's job list "
            "for a queued job whose runs-on label has no online runner."
        )
    if recent:
        conclusions = [(r.get("status"), r.get("conclusion")) for r in recent]
        facts["conclusions"] = [f"{s}/{c or '-'}" for s, c in conclusions]
        skips = [
            r for r in recent
            if r.get("conclusion") == "success" and not counts_as_bake(r, recent, now=now)
        ]
        if skips:
            facts["gate_skips"] = [r.get("id") for r in skips]
        real_success = any(counts_as_bake(r, recent, now=now) for r in recent)
        if real_success:
            baked = True
        elif any(s != "completed" for s, _ in conclusions) and not wedged:
            # Still baking.  The nightly legitimately runs for hours; check C is the
            # backstop if it never lands.
            warn.append(
                f"INDETERMINATE: {WORKFLOW_FILE} run for session {session.isoformat()} "
                "is still in flight — no success yet, but not a breach"
            )
        elif all(s == "completed" for s, _ in conclusions):
            no_success_detail = ", ".join(f"{s}/{c or '-'}" for s, c in conclusions)

    # ── C. DATA ADVANCED ────────────────────────────────────────────────────
    src = None
    if index is None:
        warn.append(
            "INDETERMINATE: site/prophet/index.json unreadable (guard is blind)"
        )
    else:
        src = _parse_date(index.get("source_asof"))
        facts["source_asof"] = index.get("source_asof")
        if src is None:
            warn.append(
                f"INDETERMINATE: source_asof missing/unparseable "
                f"({index.get('source_asof')!r})"
            )
        else:
            behind = sessions_behind(src, now)
            facts["sessions_behind"] = behind
            if no_success_detail is not None and src >= session:
                # The 2026-08-13 shape: no run succeeded, but the store carries
                # the owed session. The night's data is LIVE; only a lane is red.
                warn.append(
                    f"LANE LATCH: every {WORKFLOW_FILE} run since "
                    f"{boundary.isoformat()} concluded without success "
                    f"[{no_success_detail}], but source_asof already reads "
                    f"{src.isoformat()} — the run-level conclusion is a "
                    "single-lane latch, not a missing night. Investigate the red "
                    "lane; do not re-bake."
                )
                no_success_detail = None
            if baked and src < session:
                # The sharp case.  A run for THIS session concluded success, so the
                # store is owed exactly this session — no weekend padding applies and
                # no long-running bake can explain the gap.  #4779: an absence of red
                # is not a pass, and this is the only check that can tell the two
                # apart.
                fail.append(
                    f"RAN GREEN BUT DID NOT ADVANCE: {WORKFLOW_FILE} concluded success "
                    f"for session {session.isoformat()} but Prophet source_asof is "
                    f"still {src.isoformat()}. The lane reported success while the "
                    "store stood still."
                )
            elif not baked and behind > max_sessions_behind:
                # Coarse backstop for the no-successful-run case: catches a bake that
                # hangs forever (B stays INDETERMINATE) or a run list we could not read.
                fail.append(
                    f"STALE DATA: Prophet source_asof {src.isoformat()} is {behind} "
                    f"completed sessions behind {session.isoformat()} "
                    f"(limit {max_sessions_behind}), with no successful "
                    f"{WORKFLOW_FILE} run for this session."
                )
            elif (not baked and behind >= 1 and runs is not None and not live_fresh
                  and now >= boundary + STALE_GRACE):
                # Weekend hole (closed 2026-08-17): a missed FRIDAY bake reads
                # "1 behind" all weekend under the flat budget and could not alarm
                # before Tuesday — Canada sat frozen from 08-11 with zero noise.
                # Past the grace, 1-behind with a READ run list and nothing fresh
                # alive is a positive observation: the bake window came, went, and
                # nothing is baking. `runs is not None` keeps blindness from
                # breaching; a fresh in-flight run still excuses (slow bake at the
                # 08:00Z look must not page).
                fail.append(
                    f"STALE DATA (grace expired): Prophet source_asof "
                    f"{src.isoformat()} is {behind} completed session(s) behind "
                    f"{session.isoformat()}, the fire window closed "
                    f"{(now - boundary).total_seconds() / 3600:.1f}h ago (grace "
                    f"{STALE_GRACE.total_seconds() / 3600:.0f}h), and no fresh "
                    f"{WORKFLOW_FILE} run is alive to excuse it."
                )

    if no_success_detail is not None:
        # No success AND the store could not excuse it — either it is verifiably
        # behind, or it is unreadable. An unreadable store does not soften a
        # POSITIVE observation of failure: the only evidence that could downgrade
        # this is evidence we do not have.
        excuse = (
            f"the store is behind ({src.isoformat()})" if src is not None
            else "the store cannot be read to excuse it"
        )
        fail.append(
            f"NO SUCCESS: every {WORKFLOW_FILE} run since {boundary.isoformat()} "
            f"concluded without success [{no_success_detail}], and {excuse}. "
            "Force-cancellation by a live fleet session produced exactly this on "
            "2026-08-12."
        )

    # ── D. PER-MARKET BOARDS ────────────────────────────────────────────────
    d_fail, d_warn, d_facts = evaluate_market_boards(boards, now)
    fail.extend(d_fail)
    warn.extend(d_warn)
    facts.update(d_facts)

    return {
        "ok": not fail,
        "fail_reasons": fail,
        "warnings": warn,
        "facts": facts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# live plumbing
# ─────────────────────────────────────────────────────────────────────────────
def fetch_runs(repo: str, token: "str | None", *,
               lookback_days: int = LOOKBACK_DAYS) -> "list[dict] | None":
    """Recent daily.yml runs.  Any transport failure -> None (INDETERMINATE)."""
    created = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date()
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?per_page=50&created=%3E%3D{created.isoformat()}"
    )
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "macro-nightly-liveness",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        print(f"::warning title=nightly-liveness-blind::run fetch failed: {exc}",
              flush=True)
        return None
    runs = payload.get("workflow_runs")
    return runs if isinstance(runs, list) else None


def load_index(path: Path) -> "dict | None":
    try:
        loaded = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def load_market_boards(root: Path) -> "dict[str, dict | None]":
    """Every MARKET_BOARDS artifact, parsed.  Unreadable -> None (that market goes
    INDETERMINATE); the key is ALWAYS present so a market can never be silently dropped
    from the registry by a read failure."""
    return {spec["market"]: load_index(root / spec["path"]) for spec in MARKET_BOARDS}


def _notify(report: dict) -> None:
    """Best-effort outbound alert on the same W6b spine healthcheck uses.

    The non-zero exit (and the failed-workflow notification it trips) is the primary
    signal; this is the push that reaches a phone.
    """
    msg = ("🚨 macro-dashboard NIGHTLY LIVENESS FAILED — "
           + "; ".join(report["fail_reasons"]))
    try:
        from engine.alert_triage import push_ops_alert  # noqa: PLC0415
        push_ops_alert(
            source="nightly_liveness",
            type_="nightly_dead",
            message=msg,
            severity="critical",
            lane="nightly_liveness",
        )
    except Exception:  # noqa: BLE001 — alerting is best-effort, never the gate
        pass


# ─────────────────────────────────────────────────────────────────────────────
# selftest — synthetic assertions over the exact shapes this week produced
# ─────────────────────────────────────────────────────────────────────────────
def _selftest() -> int:
    """Fixture dates are CONSTANTS with no relation to the wall clock — a guard
    whose fixtures age is a scheduled red."""
    ok = True
    # 08:00Z on 2026-08-12 — the real incident, one night in. Owed session = 08-11,
    # fire boundary = 2026-08-11T22:00Z, store frozen at 08-10.
    now = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
    frozen = {"source_asof": "2026-08-10"}
    advanced = {"source_asof": "2026-08-11"}

    def _check(label: str, got: bool, want: bool) -> None:
        nonlocal ok
        if got is not want:
            print(f"::error title=selftest::{label}: ok={got}, expected {want}",
                  flush=True)
            ok = False

    # A: the strand. Newest run is the 08-11T00:00Z bake — BEFORE the boundary, so
    # no run exists for session 08-11. Note the store is only 1 behind here, inside
    # every data budget we own: check A is the ONLY instrument that sees this, which
    # is the entire reason this guard exists.
    r = evaluate([{"created_at": "2026-08-11T00:00:55Z", "status": "completed",
                   "conclusion": "success"}], frozen, now)
    _check("A/no-run-created", r["ok"], False)
    assert any("NO RUN" in f for f in r["fail_reasons"]), r
    assert r["facts"]["sessions_behind"] == 1, r  # data alone would NOT have alarmed

    # B: run created but force-cancelled — the 2026-08-12 dispatch signature.
    # Store frozen BEHIND the session, so the latch downgrade must NOT apply.
    r = evaluate([{"created_at": "2026-08-11T22:30:00Z", "status": "completed",
                   "conclusion": "cancelled"}], frozen, now)
    _check("B/all-cancelled", r["ok"], False)
    assert any("NO SUCCESS" in f for f in r["fail_reasons"]), r

    # B latch downgrade — the 2026-08-13 first-live-night shape: run concluded
    # `cancelled` (engine commit push-race + one cancelled offrender lane) while
    # the store ADVANCED to the owed session. Warning, never a page.
    r = evaluate([{"created_at": "2026-08-11T22:30:00Z", "status": "completed",
                   "conclusion": "cancelled"}], advanced, now)
    _check("B/lane-latch-is-not-a-page", r["ok"], True)
    assert any("LANE LATCH" in w for w in r["warnings"]), r

    # B: no success and the store is UNREADABLE — a positive observation of
    # failure with no evidence to excuse it still pages.
    r = evaluate([{"created_at": "2026-08-11T22:30:00Z", "status": "completed",
                   "conclusion": "cancelled"}], None, now)
    _check("B/no-success-blind-store-fails", r["ok"], False)
    assert any("cannot be read to excuse" in f for f in r["fail_reasons"]), r

    # B: still in flight -> INDETERMINATE. The nightly runs for hours; alarming here
    # would train the operator to ignore the channel.  (9.5h old at the 08:00Z look
    # — under IN_FLIGHT_MAX_AGE by design.)
    r = evaluate([{"created_at": "2026-08-11T22:30:00Z", "status": "in_progress",
                   "conclusion": None}], frozen, now)
    _check("B/in-flight-indeterminate", r["ok"], True)
    assert r["warnings"], r

    # B age cap: the 2026-08-16/17 hostage signature — the same run at the 14:00Z
    # look is 15.5h old.  "Still baking" has become "hung or hostage": breach.
    r = evaluate([{"id": 31977372592, "created_at": "2026-08-11T22:30:00Z",
                   "status": "queued", "conclusion": None}], frozen,
                 datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc))
    _check("B/in-flight-past-cap-pages", r["ok"], False)
    assert any("WEDGED IN FLIGHT" in f for f in r["fail_reasons"]), r

    # C weekend hole (closed 2026-08-17): Saturday morning, Friday bake never
    # created, store 1 behind, nothing alive.  Under the flat budget this stayed
    # quiet until Tuesday — Canada froze 08-11→08-17 with zero noise.
    sat = datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc)
    r = evaluate([], {"source_asof": "2026-08-13"}, sat)
    _check("C/weekend-one-behind-past-grace-pages", r["ok"], False)
    assert any("grace expired" in f for f in r["fail_reasons"]), r

    # C weekend control: the same Saturday instant with a FRESH run alive is a
    # slow bake, not a breach — the grace path must stay excused.
    r = evaluate([{"created_at": "2026-08-15T04:00:00Z", "status": "in_progress",
                   "conclusion": None}], {"source_asof": "2026-08-13"}, sat)
    _check("C/weekend-fresh-run-excuses-grace", r["ok"], True)

    # C sharp: the run concluded SUCCESS for 08-11 and the store still reads 08-10.
    # No weekend padding, no long-bake excuse — green that did not advance.
    r = evaluate([{"created_at": "2026-08-11T22:30:00Z", "status": "completed",
                   "conclusion": "success"}], frozen, now)
    _check("C/green-but-not-advanced", r["ok"], False)
    assert any("DID NOT ADVANCE" in f for f in r["fail_reasons"]), r

    # C coarse: second night out. Owed session 08-12, still nothing since 08-12T22:00Z,
    # store 2 behind -> A and C both fire.
    later = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    r = evaluate([{"created_at": "2026-08-11T00:00:55Z", "status": "completed",
                   "conclusion": "success"}], frozen, later)
    _check("C/two-sessions-out", r["ok"], False)
    assert any("NO RUN" in f for f in r["fail_reasons"]), r
    assert any("STALE DATA" in f for f in r["fail_reasons"]), r

    # Healthy night.
    r = evaluate([{"created_at": "2026-08-11T22:30:00Z", "status": "completed",
                   "conclusion": "success"}], advanced, now)
    _check("healthy", r["ok"], True)

    # 2026-08-14/15: cancelled EDT real slot + surviving EST-guard no-op. The
    # no-op concluded success in ~5s; that must NOT count as a bake (otherwise
    # this reads RAN GREEN BUT DID NOT ADVANCE — "the nightly ran").
    r = evaluate([
        {"id": 31848262472, "created_at": "2026-08-14T22:52:00Z",
         "event": "schedule", "status": "completed", "conclusion": "cancelled",
         "display_title": "daily 30 22 * * *"},
        {"id": 31851452961, "created_at": "2026-08-14T23:45:00Z",
         "event": "schedule", "status": "completed", "conclusion": "success",
         "display_title": "daily 30 23 * * *",
         "run_started_at": "2026-08-15T02:16:00Z",
         "updated_at": "2026-08-15T02:16:05Z"},
    ], {"source_asof": "2026-08-13"},
       datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc))
    _check("B/cancelled-real-plus-gate-skip", r["ok"], False)
    assert any("NO SUCCESS" in f for f in r["fail_reasons"]), r
    assert not any("DID NOT ADVANCE" in f for f in r["fail_reasons"]), r

    # Live API shape: display_title was just "daily"; run_started_at == created_at.
    r = evaluate([
        {"id": 31848262472, "created_at": "2026-08-14T22:52:07Z",
         "event": "schedule", "status": "completed", "conclusion": "cancelled",
         "display_title": "daily"},
        {"id": 31851452961, "created_at": "2026-08-14T23:45:40Z",
         "event": "schedule", "status": "completed", "conclusion": "success",
         "display_title": "daily",
         "run_started_at": "2026-08-14T23:45:40Z",
         "updated_at": "2026-08-15T02:16:21Z"},
    ], {"source_asof": "2026-08-13"},
       datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc))
    _check("B/unlabelled-skip-plus-cancelled-sibling", r["ok"], False)
    assert any("NO SUCCESS" in f for f in r["fail_reasons"]), r
    assert not any("DID NOT ADVANCE" in f for f in r["fail_reasons"]), r

    # Blindness is never a breach.
    r = evaluate(None, None, now)
    _check("blind-indeterminate", r["ok"], True)
    assert len(r["warnings"]) == 2, r

    # Weekend: Saturday resolves to Friday's bake, which happened. A calendar anchor
    # is what lets this budget be tight where the 96h heartbeat has to be loose.
    sat = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    r = evaluate([{"created_at": "2026-08-14T22:30:00Z", "status": "completed",
                   "conclusion": "success"}], {"source_asof": "2026-08-14"}, sat)
    _check("weekend-no-false-alarm", r["ok"], True)

    # ── D: per-market boards ────────────────────────────────────────────────
    # 2026-08-18T08:00Z. Owed sessions: NYSE/TSX 08-17, HKEX/mainland 08-17.
    # The real 2026-08-14 Canada freeze: ca stuck at 08-13, siblings at 08-17.
    d_now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)
    healthy_runs = [{"created_at": "2026-08-17T22:30:00Z", "status": "completed",
                     "conclusion": "success"}]
    d_index = {"source_asof": "2026-08-17"}
    fresh = {m: {"as_of": "2026-08-17"} for m in ("us", "cn", "hk", "ca")}

    r = evaluate(healthy_runs, d_index, d_now,
                 boards={**fresh, "intl": {"as_of": "2026-08-17"}})
    _check("D/all-five-fresh", r["ok"], True)

    # The Canada freeze. 08-13 is 2 completed TSX sessions behind 08-17 (08-14, 08-17)
    # — past the budget of 1 — and the message must NAME the market.
    r = evaluate(healthy_runs, d_index, d_now,
                 boards={**fresh, "ca": {"as_of": "2026-08-13"},
                         "intl": {"as_of": "2026-08-17"}})
    _check("D/canada-freeze-pages", r["ok"], False)
    assert any("STALE BOARD [Canada]" in f for f in r["fail_reasons"]), r
    assert r["facts"]["boards"]["ca"]["behind"] == 2, r
    # and it must not smear onto the four healthy markets
    assert len([f for f in r["fail_reasons"] if "STALE BOARD" in f]) == 1, r

    # One session behind is the HEALTHY afternoon shape for HK/mainland (their
    # calendars roll forward hours before the ET bake fires). Budget 1 absorbs it.
    r = evaluate(healthy_runs, d_index, d_now,
                 boards={**fresh, "hk": {"as_of": "2026-08-14"},
                         "intl": {"as_of": "2026-08-17"}})
    _check("D/one-behind-is-not-a-breach", r["ok"], True)

    # Mainland holiday floor, INSIDE a closure window. 2026-10-09: a board stamped
    # 2026-09-28 reads 3 sessions behind because Golden Week (Oct 1-7) sits in the gap
    # and the State Council routinely runs it longer than the table encodes. 11 calendar
    # days old, so the floor holds and this is a holiday shape, not a proven freeze.
    gw_now = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
    gw_fresh = {m: {"as_of": "2026-10-08"} for m in ("us", "hk", "ca", "intl")}
    gw_runs = [{"created_at": "2026-10-08T22:30:00Z", "status": "completed",
                "conclusion": "success"}]
    r = evaluate(gw_runs, {"source_asof": "2026-10-08"}, gw_now,
                 boards={**gw_fresh, "cn": {"as_of": "2026-09-28"}})
    _check("D/mainland-holiday-floor-suppresses", r["ok"], True)
    assert any("longest-legitimate-closure floor" in w for w in r["warnings"]), r

    # ...and it EXPIRES. Past the floor the same stamp is a proven freeze.
    r = evaluate(gw_runs, {"source_asof": "2026-10-08"},
                 datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc),
                 boards={**gw_fresh, "cn": {"as_of": "2026-09-28"}})
    _check("D/mainland-floor-expires", r["ok"], False)
    assert any("STALE BOARD [China]" in f for f in r["fail_reasons"]), r

    # OUTSIDE a closure window the floor does not apply at all: there are no phantom
    # sessions to excuse in August, so the mainland pages at 2 like every other market.
    # This is the narrowing — without it the mainland waited until 2026-08-26.
    r = evaluate(healthy_runs, d_index, d_now,
                 boards={**fresh, "cn": {"as_of": "2026-08-13"},
                         "intl": {"as_of": "2026-08-17"}})
    _check("D/mainland-floor-is-not-always-on", r["ok"], False)
    assert any("STALE BOARD [China]" in f for f in r["fail_reasons"]), r

    # Blindness, per market and independently: a missing artifact, an absent stamp
    # (the live International shape — its as_of is None on every commit in history)
    # and an unparseable stamp are all INDETERMINATE, and the other markets stay graded.
    r = evaluate(healthy_runs, d_index, d_now,
                 boards={"us": None, "cn": None, "hk": None,
                         "ca": {"as_of": "2026-08-17"}, "intl": {"as_of": None}})
    _check("D/blind-markets-never-breach", r["ok"], True)
    assert len([w for w in r["warnings"] if "INDETERMINATE [" in w]) == 4, r
    assert r["facts"]["boards"]["ca"]["behind"] == 0, r

    # ...but an artifact we CAN read that publishes no stamp is a producer regression,
    # not blindness — otherwise the market switches itself off silently and forever.
    r = evaluate(healthy_runs, d_index, d_now,
                 boards={**fresh, "ca": {"as_of": None}, "intl": {"as_of": None}})
    _check("D/unstamped-board-is-a-breach", r["ok"], False)
    assert any("BOARD PUBLISHED WITHOUT A STAMP [Canada]" in f
               for f in r["fail_reasons"]), r
    # and the one board that has NEVER carried a stamp stays a named warning
    assert any("INDETERMINATE [International]" in w for w in r["warnings"]), r

    # A market absent from the payload entirely must warn, never vanish quietly —
    # that is what a forgotten sparse-checkout path looks like.
    r = evaluate(healthy_runs, d_index, d_now, boards={})
    _check("D/empty-payload-is-blind-not-green", r["ok"], True)
    assert len([w for w in r["warnings"] if "INDETERMINATE [" in w]) == len(MARKET_BOARDS), r

    # Not supplied at all -> check D produces nothing (offline callers).
    r = evaluate(healthy_runs, d_index, d_now)
    _check("D/not-requested-is-silent", r["ok"], True)
    assert "boards" not in r["facts"], r

    print("nightly-liveness selftest: " + ("PASS" if ok else "FAIL"), flush=True)
    return 0 if ok else 1


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="synthetic assertions over the 2026-08 failure shapes")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--runs-json", type=Path,
                        help="offline: read the run list from a file instead of the API")
    parser.add_argument("--index-json", type=Path,
                        default=REPO_ROOT / "site" / "prophet" / "index.json")
    parser.add_argument("--max-sessions-behind", type=int, default=MAX_SESSIONS_BEHIND)
    parser.add_argument(
        "--site-root", type=Path, default=REPO_ROOT,
        help="offline: repo root the MARKET_BOARDS paths resolve against (check D)")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    now = datetime.now(timezone.utc)
    if args.runs_json:
        # Offline mode accepts either a bare list or a full API payload.
        try:
            raw = json.loads(args.runs_json.read_text())
        except (OSError, ValueError):
            raw = None
        if isinstance(raw, list):
            runs = raw
        elif isinstance(raw, dict) and isinstance(raw.get("workflow_runs"), list):
            runs = raw["workflow_runs"]
        else:
            runs = None
    else:
        runs = fetch_runs(args.repo, os.environ.get("GITHUB_TOKEN"))

    report = evaluate(runs, load_index(args.index_json), now,
                      max_sessions_behind=args.max_sessions_behind,
                      boards=load_market_boards(args.site_root))

    for line in report["warnings"]:
        print(f"::warning title=nightly-liveness::{line}", flush=True)
    for line in report["fail_reasons"]:
        print(f"::error title=nightly-liveness::{line}", flush=True)

    facts = report["facts"]
    print(
        "nightly liveness | session={} runs_since={} source_asof={} behind={}".format(
            facts.get("expected_session"),
            facts.get("runs_since_boundary", "?"),
            facts.get("source_asof", "?"),
            facts.get("sessions_behind", "?"),
        ),
        flush=True,
    )
    print(
        "market boards | " + " ".join(
            "{}={}({})".format(
                m,
                st.get("as_of") if st.get("as_of") is not None else "-",
                "?" if st.get("behind") is None else st["behind"],
            )
            for m, st in (facts.get("boards") or {}).items()
        ),
        flush=True,
    )

    if not report["ok"]:
        _notify(report)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
