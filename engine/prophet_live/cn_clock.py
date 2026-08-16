"""engine.prophet_live.cn_clock — the mainland (SSE/SZSE) session-state contract.

THE CN CLOCK IS NOT THE US CLOCK WITH DIFFERENT NUMBERS. The US lane has ONE
continuous window (09:30-16:00 ET) so "how old is this quote" and "how long since we
looked" are the same question all day. The mainland session has a 90-minute LUNCH
BREAK in the middle of it, and during that break the tape is not stale — it is
CLOSED. At 13:02 CST a quote stamped 11:29 is the freshest print that exists; at
14:30 a quote stamped 10:15 is four hours behind a tape that has been running the
whole time. Wall-clock age cannot tell those two apart, so every freshness question
on this lane is asked against :func:`expected_latest_quote_time`, never against
``now`` (spec §2 quote-age law, research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md).

LANE LAW (inherited from the US program, unchanged):
  * NO ``data/`` WRITES from anything that imports this module on the live path. The
    nightly asia-close lane is the sole writer of ``data/cn_prophet_live/``.
  * The NIGHTLY is the single writer of every ledger and the only thing that
    confirms. Nothing here confirms, grades, refutes or validates.
  * Kill switch ``CN_PROPHET_LIVE_NO_PUBLISH=1`` stands the CN publish path down
    (:mod:`engine.prophet_live.cn_states`), separate from the US switch.

STDLIB ONLY, deliberately — stdlib + :mod:`lib.cn_calendar` + ``zoneinfo``. NO
pandas. The */5 evaluator installs ``pyyaml boto3`` and nothing else, exactly like the
US lane, and this module is on its import path. The same reason
:mod:`engine.prophet_live.interval` is pandas-free.

ALL BOUNDARIES ARE Asia/Shanghai WALL CLOCK. The mainland observes no DST, so the
UTC equivalents are fixed year-round (CST = UTC+8) — but they are still derived
through ``zoneinfo`` rather than hardcoded as UTC, because a hardcoded offset is how
the US lane's window was an hour wrong for five months of every year.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from lib import cn_calendar

log = logging.getLogger(__name__)

#: The mainland trading-day wall clock. No DST — but resolved through zoneinfo all
#: the same, so a tzdata update is the single place a boundary can move.
CST = cn_calendar.CST

# ─────────────────────────────────────────────────────────────────────────────
# Session boundaries (CST). One definition; the UTC column in the spec's §2 table
# is these minus 8 hours and is never written down a second time.
# ─────────────────────────────────────────────────────────────────────────────

#: Call-auction order entry opens; the evaluator's warmup pass may run from here.
PRE_OPEN_START = time(9, 10)
#: Continuous trading opens. 09:15-09:25 is the OPENING AUCTION — it prints
#: indications, not trades, so it is folded into ``pre_open`` (spec §2) and no state
#: transition may be taken off it.
MORNING_OPEN = time(9, 30)
#: Morning session ends. THIS is the anchor a lunchtime quote's age is measured from.
MORNING_CLOSE = time(11, 30)
#: Afternoon session opens.
AFTERNOON_OPEN = time(13, 0)
#: Closing call auction begins — continuous trading stops, so a print after this is
#: an auction indication and no NEW transition may be confirmed on it.
CLOSING_AUCTION_START = time(14, 57)
#: The close. The afternoon segment ends here (the auction is part of it: the auction
#: DOES print a settled price at 15:00, which is what the close pass observes).
SESSION_CLOSE = time(15, 0)
#: The close pass stands down here. Past it there is nothing lawful left to observe
#: that the settlement lane will not do better.
POST_CLOSE_END = time(15, 15)

#: Every phase this module can return. ``opening_auction`` is deliberately NOT here:
#: the spec folds it into ``pre_open`` handling, and a phase nobody may act on
#: differently from its neighbour is a distinction that only invites one.
PHASES: tuple[str, ...] = ("holiday", "weekend", "pre_open", "morning",
                           "session_break", "afternoon", "closing_auction",
                           "post_close", "closed")

#: Phases in which the evaluator runs a pass at all. Everything else exits in <1s.
EVAL_PHASES: frozenset[str] = frozenset({"pre_open", "morning", "session_break",
                                         "afternoon", "closing_auction",
                                         "post_close"})

#: Phases in which the tape is genuinely running and a transition may be taken.
TRADING_PHASES: frozenset[str] = frozenset({"morning", "afternoon"})

#: Phases in which a pass may RUN but every public state FREEZES (spec §2):
#:   pre_open         states carry over from the prior session's close
#:   session_break    no fades, no crosses; debounce counters carried intact
#:   closing_auction  no NEW transition confirmed off an auction indication
#: A frozen pass still refreshes price/quote age/market_status and still publishes —
#: the artifact says the phase out loud so a reader never mistakes a frozen state for
#: a fresh verdict.
FREEZE_PHASES: frozenset[str] = frozenset({"pre_open", "session_break",
                                           "closing_auction"})

# ─────────────────────────────────────────────────────────────────────────────
# Per-class daily price limit (spec §2). Ticker-derived, mainland only.
# ─────────────────────────────────────────────────────────────────────────────
#
# These size the PACK's probe span as well as the lock overlay: probing beyond the
# daily limit band spends budget on prices tomorrow's tape cannot lawfully print
# (spec §4). ST names are already excluded by the nightly's tradability screen and
# .BJ is not in the universe, so the 5%/30% classes are deliberately absent — a
# ticker that reaches neither branch gets None and NO lock verdict, which is the
# honest answer for a symbol this lane does not model.

#: STAR Market (科创板) — Shanghai. ±20%.
STAR_LIMIT_PCT = 20.0
#: ChiNext (创业板) — Shenzhen. ±20%.
CHINEXT_LIMIT_PCT = 20.0
#: Main board, both exchanges. ±10%.
MAIN_BOARD_LIMIT_PCT = 10.0

# THE PREFIX LISTS ARE THE WHOLE SCREEN, so they are named, measured against the real
# store, and NOT a single startswith. A ±20% board misread as ±10% is the dangerous
# direction TWICE OVER: the pack's probe span stops at +10% and never sweeps the
# lawful 10-20% region, and — worse — `limit_lock_status` stamps a FALSE
# `limit_up_locked` on a ChiNext name printing exactly +10% while its tape is still
# running, which is a regime this lane would be asserting out of nothing.
#
# MEASURED on data/china_stocks (2026-08-15, 1,857 names): 300.SZ 253 · 301.SZ 104 ·
# 302.SZ 1 · 688.SS 248. A 300-only ChiNext test would have mislabelled 105 live names.
#
#: STAR: 688xxx plus 689xxx (the CDR range — same board, same ±20% band).
_STAR_PREFIXES: tuple[str, ...] = ("688", "689")
#: ChiNext: 300xxx plus the registration-reform 301xxx/302xxx ranges. All ±20%.
_CHINEXT_PREFIXES: tuple[str, ...] = ("300", "301", "302")

#: Absolute floor on the limit-lock comparison tolerance, in yuan. A-share limit
#: prices are rounded to the fen by the exchange, so a lock sits within one fen of
#: the computed band edge by construction.
_LOCK_ABS_TOL = 0.01
#: Relative half-width of the same tolerance (5 bp), which takes over for names
#: expensive enough that one fen is tighter than the rounding it is meant to absorb.
_LOCK_REL_TOL = 0.0005

LIMIT_UP_LOCKED = "limit_up_locked"
LIMIT_DOWN_LOCKED = "limit_down_locked"


def limit_pct_for(ticker: Any) -> float | None:
    """The daily price limit for ``ticker``, in percent. None = not modelled here.

    Derived from the ticker alone because that is where the board membership lives:
    :data:`_STAR_PREFIXES` on ``.SS`` is STAR, :data:`_CHINEXT_PREFIXES` on ``.SZ`` is
    ChiNext, and every other ``.SS``/``.SZ`` name is main board. No lookup, no network,
    no data dependency — a screen that needed a file would fail differently on the pack
    lane and the evaluator lane, and the two must agree about the band by construction.
    """
    try:
        sym = str(ticker or "").strip().upper()
    except Exception:  # noqa: BLE001
        return None
    if "." not in sym:
        return None
    code, _, suffix = sym.rpartition(".")
    if suffix == "SS":
        return STAR_LIMIT_PCT if code.startswith(_STAR_PREFIXES) else MAIN_BOARD_LIMIT_PCT
    if suffix == "SZ":
        return CHINEXT_LIMIT_PCT if code.startswith(_CHINEXT_PREFIXES) else MAIN_BOARD_LIMIT_PCT
    return None


def limit_lock_status(price: Any, prev_close: Any,
                      limit_pct: Any) -> str | None:
    """``limit_up_locked``/``limit_down_locked``/None for one live print.

    A LIMIT-LOCKED PRICE IS A REAL PRICE (spec §2). This function names the REGIME,
    it does not gate the state machine: a name pinned at +10% all day has traded, the
    gate can be evaluated at that price, and the difference between "one-price
    session" and "no observation" is exactly what a user needs and what a single
    ``unavailable`` bucket would destroy.

    Tolerance is ``max(0.01, prev_close * 0.0005)`` — the exchange rounds the limit
    price to the fen, so an exact equality test would miss most real locks.
    """
    try:
        px = float(price)
        prev = float(prev_close)
        pct = float(limit_pct)
    except (TypeError, ValueError):
        return None
    if not (px > 0 and prev > 0) or pct <= 0:
        return None
    tol = max(_LOCK_ABS_TOL, prev * _LOCK_REL_TOL)
    if abs(px - prev * (1.0 + pct / 100.0)) <= tol:
        return LIMIT_UP_LOCKED
    if abs(px - prev * (1.0 - pct / 100.0)) <= tol:
        return LIMIT_DOWN_LOCKED
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Clock
# ─────────────────────────────────────────────────────────────────────────────

def _utc(now: datetime | None) -> datetime:
    """``now`` as an aware UTC datetime. Naive inputs are UTC (pipeline convention)."""
    t = now or datetime.now(timezone.utc)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def cst_clock(now: datetime | None = None) -> datetime:
    """``now`` on the mainland wall clock."""
    return _utc(now).astimezone(CST)


def _at(d: date, t: time) -> datetime:
    """A CST wall-clock instant, returned in UTC so callers do arithmetic in one zone."""
    return datetime.combine(d, t, tzinfo=CST).astimezone(timezone.utc)


def phase(now: datetime | None = None) -> str:
    """Which of :data:`PHASES` the mainland market is in at ``now``.

    Never raises: an unreadable calendar degrades to the weekday check, which errs
    toward calling a holiday a session (a pass that finds no fresh quotes and says so)
    rather than toward calling a session a holiday (a dark hour nobody notices).
    """
    t = cst_clock(now)
    d = t.date()
    if d.weekday() >= 5:
        return "weekend"
    try:
        if not cn_calendar.is_session(d):
            return "holiday"
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_clock: calendar unavailable (%s) — weekday only", exc)
    wall = t.time()
    if wall < PRE_OPEN_START:
        return "closed"
    if wall < MORNING_OPEN:
        return "pre_open"
    if wall < MORNING_CLOSE:
        return "morning"
    if wall < AFTERNOON_OPEN:
        return "session_break"
    if wall < CLOSING_AUCTION_START:
        return "afternoon"
    if wall < SESSION_CLOSE:
        return "closing_auction"
    if wall < POST_CLOSE_END:
        return "post_close"
    return "closed"


def is_evaluable(now: datetime | None = None) -> bool:
    """True when a pass should do work. The service self-gates on this."""
    return phase(now) in EVAL_PHASES


def session_date(now: datetime | None = None) -> date:
    """The CN session date ``now`` belongs to — in progress, or most recently closed.

    Mirrors :func:`lib.nyse_calendar.session_date`'s semantics on the mainland clock:
    on a session day the whole CST calendar day stamps to that session (pre-open and
    post-close included, which is what an artifact ``session`` field and an event
    spool prefix need); on a weekend or holiday it resolves back to the last session.

    NOT the UTC date. The whole CN session sits in the 01:00-07:15 UTC band, so UTC
    and CST agree on the calendar date for every instant this lane runs — but the
    stand-down ticks either side do not, and a stamp that is right only while the
    market is open is a stamp that breaks exactly when something goes wrong.
    """
    return cn_calendar.last_session_on_or_before(cst_clock(now).date())


def last_completed_session(now: datetime | None = None) -> str:
    """The last COMPLETED mainland session, ISO — what the pack's ``as_of`` must equal.

    Delegates to :func:`lib.cn_calendar.expected_last_session`, whose 17:00 CST settle
    buffer is what makes this the PRIOR session all through a live pass: the pack was
    armed last night on last night's store, and evaluating today's tape against a pack
    armed on an N-2 store is the one failure this lane must never have (spec §4).
    """
    try:
        return cn_calendar.expected_last_session(_utc(now)).isoformat()
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_clock: calendar unavailable (%s) — weekday fallback", exc)
        d = cst_clock(now).date() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()


def _prev_session_close(d: date) -> datetime:
    """15:00 CST of the last session STRICTLY before ``d`` (UTC-aware)."""
    prev = cn_calendar.last_session_on_or_before(d - timedelta(days=1))
    return _at(prev, SESSION_CLOSE)


def expected_latest_quote_time(now: datetime | None = None) -> datetime:
    """The newest instant a LAWFUL quote could carry — ``min(now, segment end)``.

    THE ANCHOR EVERY FRESHNESS QUESTION ON THIS LANE IS ASKED AGAINST (spec §2).
    Wall-clock age is wrong on the mainland twice a day and wrong in the dangerous
    direction both times:

      * at 13:02 CST a quote stamped 11:29 is 93 minutes old by the wall clock and
        the FRESHEST PRINT THAT EXISTS. Gating on the wall clock darks the entire
        board every lunchtime, which looks exactly like a dead lane.
      * at 09:20 CST (pre-open) the freshest lawful print is YESTERDAY's close, and
        an anchor of ``now`` would call it fresh. It is not fresh, it is
        *the newest thing there is*, which is why the pre-open phase freezes states
        instead of evaluating them — this function returns the honest anchor and
        :mod:`engine.prophet_live.cn_states` decides what to do with it.

    Returned in UTC so the caller subtracts two aware datetimes in one zone.
    """
    t = cst_clock(now)
    d = t.date()
    utc_now = _utc(now)
    try:
        session_today = cn_calendar.is_session(d)
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_clock: calendar unavailable (%s) — weekday only", exc)
        session_today = d.weekday() < 5
    if not session_today:
        return _prev_session_close(d)
    wall = t.time()
    if wall < MORNING_OPEN:
        # Nothing has printed today. Pre-open and the opening auction included: an
        # auction indication is not a trade and this lane never reads one.
        return _prev_session_close(d)
    if wall < MORNING_CLOSE:
        return utc_now
    if wall < AFTERNOON_OPEN:
        return _at(d, MORNING_CLOSE)
    if wall < SESSION_CLOSE:
        return utc_now
    return _at(d, SESSION_CLOSE)


def quote_age_min(quote_ts: datetime | None, now: datetime | None = None,
                  *, delay_floor_min: float = 0.0) -> float | None:
    """A quote's age in minutes, measured against :func:`expected_latest_quote_time`.

    None when the quote carries no timestamp — "not measured" is a different claim
    from "fresh", and this lane never lets the second stand in for the first.

    ``delay_floor_min`` IS LOAD-BEARING ON A DELAYED FEED. The anchor is evaluated at
    ``now - delay_floor_min``, because the newest instant a quote could LAWFULLY carry
    on a floor-delayed feed is the segment position of ``now`` minus that floor, not of
    ``now`` itself. Concretely, with the 15-minute spark floor: at 13:02 CST the anchor
    resolves through 12:47 → lunch → 11:30, so the 11:29 print the vendor is actually
    serving reads ~1 minute old (FRESH — it is the freshest print that exists); with an
    anchor at bare ``now`` it reads 93 minutes old and the entire board goes dark for
    the first delay-floor minutes of every afternoon and every open. The same shift
    makes the first minutes after 09:30 honest: nothing newer than yesterday's close is
    lawfully expected until the floor has elapsed, and a feed that IS ahead of the
    floor clamps to zero below. A genuinely stale feed stays caught: at 14:30 the
    shifted anchor is 14:15, and a 10:15 print reads 4 hours old either way.

    CLAMPED AT ZERO. A print stamped INSIDE the closing auction (or a vendor clock a
    few seconds ahead of ours) is newer than the segment anchor; that is a vendor
    artifact, not negative age, and a negative number here would sort wrong in every
    percentile the liveness record publishes.
    """
    if quote_ts is None:
        return None
    try:
        ts = quote_ts if quote_ts.tzinfo is not None else quote_ts.replace(tzinfo=timezone.utc)
    except AttributeError:
        return None
    shifted = _utc(now) - timedelta(minutes=max(0.0, float(delay_floor_min)))
    anchor = expected_latest_quote_time(shifted)
    return max(0.0, (anchor - ts.astimezone(timezone.utc)).total_seconds() / 60.0)


def session_close_utc(now: datetime | None = None) -> datetime:
    """07:00 UTC (15:00 CST) of the session ``now`` belongs to.

    The close pass's observability floor: a print stamped before this instant cannot
    be a close, whatever else it is (spec §5).
    """
    return _at(session_date(now), SESSION_CLOSE)


def post_close_deadline(now: datetime | None = None) -> datetime:
    """07:15 UTC (15:15 CST) of this session — the close board's honesty deadline.

    Past it the close pass publishes whatever share it can genuinely observe with
    ``close_pending: true``; it never waits, and it never manufactures a close.
    """
    return _at(session_date(now), POST_CLOSE_END)
