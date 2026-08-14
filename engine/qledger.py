"""engine/qledger.py — the Universal Scoreboard (§2.2 of
research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md).

The ONE claims+grades substrate every scored number must pass through. It
generalises three ledger patterns already in the tree:
  * data/altdata/theses.jsonl rows — PIT `entry_levels {subject, bench}`,
    an engine-derived `falsifier`, `check_by`, `status`.
  * engine/radar_ic.py post-#904 — per-horizon grading, `horizon_d`-stamped
    snapshots, forward relative-return vs a benchmark.
  * engine/ai_desk.py — the price layer (`_close_series` with the S&P-1500
    breadth-cache fallback, `_level_asof`) and proxy-vs-bench scoring.

This module is the W1 CONTRACT the four W1 builders map their existing ledgers
onto by *adapter* — it does not itself write adapters, the nightly runner, or UI
(those are builder/W1-runner scope). It owns:
  * the CLAIM schema + `register()` validation (§2.2, D4, [P2]).
  * the GRADE model — multi-horizon [5,21,63] capped by the claim's horizon_d,
    matched-control excess, per-timestamp_quality embargo ([P2]).
  * the TRACK-RECORD emit — per-desk / per-claim-family, honest `n_dates`
    (independent date clusters, [P1]/§5), Wilson-CI lower bound, and the
    UNGRADED / ACCRUING / GRADED state chip the UI reads (D10).
  * the placebo-tape schema slot (`is_placebo`, D3) so B3's sampler just calls
    `register()`.

Price helpers are REUSED, never reinvented — the same parquet layer the whole
suite grades on.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, NamedTuple

import pandas as pd

# Reuse the exact price layer the rest of the suite grades on. `_close_series`
# has the breadth-cache fallback so subjects beyond the ~153 yahoo parquets are
# still scorable; `_level_asof`/`close_at`/`covers` share it.
from engine.ai_desk import _GICS_ETF, _level_asof
from engine import ai_desk as _aidesk  # module ref: tests monkeypatch ai_desk._close_series
from engine.ai_desk_scorer import _close_at, _covers
# V1 metric-validity contract (engine/qledger_validity.py, PR #5471). _aggregate
# is the single chokepoint every published excess figure passes through, so the
# legality gate is ENFORCED here rather than re-derived per consumer — one
# implementation of the invariant, so the emitter and the auditor cannot drift.
from engine.qledger_validity import FamilyProfile, may_pool_signed_excess, profile_families
from lib import config
# The canonical session rulers — ONE PER MARKET. Rule-computed sessions,
# stdlib-only, holiday aware. See `resolve_horizon_window` for why the
# price-store index is NOT the session source of record here, and
# `CLOCK_CALENDARS` for why there are three of these and not one.
from lib import cn_calendar as _cn_calendar
from lib import hk_calendar as _hk_calendar
from lib import nyse_calendar as _nyse_calendar
# The house ticker->market classifier (engine/session_anchor R3). REUSED, never
# re-invented: a second suffix table would drift from the one every board's
# session bucketing already reads.
from engine.session_anchor import MARKET_SUFFIX
# The house US-equity shape gate (engine/ticker_shape) — stdlib-only, no disk.
# Used as the CORROBORATION on the residual share-class branch of `_ticker_market`,
# so "single letter after the dot" is never on its own sufficient to name a market.
# `plausible_symbol` is the WIDER tripwire — "is this shaped like a ticker on ANY
# exchange at all" — used to tell a real (if ambiguous) ticker apart from a
# symbolic macro label like "CN_CENSORSHIP_RISK" that carries no market
# information in its shape and must never be asked to originate one (round 5).
from engine.ticker_shape import plausible_symbol, valid_us_ticker

log = logging.getLogger("qledger")


def _json_default(o: Any):
    """json.dumps `default=` for the claim/grade store.

    qledger is the serialization boundary for dicts assembled by many desks and
    stamped here with the US regime_vector (read from a parquet). A parquet read
    yields numpy scalars (np.int64/float64/bool_), which json.dumps cannot
    serialize natively — a single leaked np.int64 raised TypeError and, under a
    broad except in a caller, silently zeroed a whole batch of claims. Every
    claim-write routes through this so no numpy scalar can ever break the ledger.
    """
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    item = getattr(o, "item", None)   # numpy scalar → native python
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    return str(o)


# --------------------------------------------------------------------------- #
# store layout
# --------------------------------------------------------------------------- #
_CLAIMS_FILE = ("data", "qledger", "claims.jsonl")
_GRADES_FILE = ("data", "qledger", "grades.jsonl")
_TRACK_FILE = ("site", "qledger", "track_record.json")

# --------------------------------------------------------------------------- #
# frozen enums (the contract — builders MUST use these literals)
# --------------------------------------------------------------------------- #
SCOPE_TYPES = ("entity", "basket", "sector", "macro")
DIRECTIONS = (-1, 0, 1)                     # 0 == salience-only (§2.3, D5)

# The grading clock. Every claim grades at each horizon in GRADE_HORIZONS that is
# ≤ its own horizon_d (D2 — "grade every open claim at 5/21/63d simultaneously").
GRADE_HORIZONS = (5, 21, 63)

# --------------------------------------------------------------------------- #
# THE HORIZON CLOCK (P0a — explicit horizon-unit contract)
# --------------------------------------------------------------------------- #
# THE DEFECT THIS REPAIRS. `horizon_d` used to be a bare integer with NO declared
# unit, and qledger itself read it two different ways:
#   * make_claim()  -> check_by = asof + pd.offsets.BusinessDay(horizon_d)
#   * _fwd_ret()    -> exit     = fill + pd.Timedelta(days=horizon_d)  [CALENDAR]
# From a Friday asof=2026-08-07 those diverge by +2d at horizon_d=5, +4d at 7 and
# +10d at 21 — the falsifier deadline a human reads and the window actually graded
# were ten days apart at the 21d rung. Meanwhile the emitters disagreed about what
# the number even meant: policy_intent_desk/stock_desk/thematic_desk/altdata_brain
# document "integer TRADING days", build_whitehouse passes CALENDAR banner_days,
# and source_registry bypassed _fwd_ret entirely to compute an exact trading-session
# exit precisely because an approximated calendar horizon is unsafe.
#
# THE CONTRACT.
#   1. A new claim declares `horizon_unit` from this narrow vocabulary.
#   2. `horizon_d` stays the numeric DECLARED ruler and is NEVER converted — a
#      policy claim stays horizon_d=126/trading_days, a whitehouse claim stays
#      horizon_d=7/calendar_days.
#   3. The clock interprets the number ACCORDING TO ITS UNIT.
#   4. ONE resolver (`resolve_horizon_window`) answers check_by, maturity, the
#      graded window and the rendered ruler. There is no second implementation.
#   5. The window is resolved ONCE per (claim, horizon) and SHARED by subject,
#      bench and control, so no leg can silently receive a different horizon.
HORIZON_UNIT_TRADING = "trading_days"
HORIZON_UNIT_CALENDAR = "calendar_days"
HORIZON_UNITS = (HORIZON_UNIT_TRADING, HORIZON_UNIT_CALENDAR)

# The grading-clock basis stamped on every new grade row. Rows written before this
# contract carry NO clock stamp and are read as CLOCK_LEGACY — the immutable
# legacy grading basis. Legacy rows are NEVER rewritten and never re-labelled
# (same house pattern as the fill_convention discontinuity below).
CLOCK_LEGACY = "legacy_calendar_unstamped"
CLOCK_V1 = "explicit_unit_v1"

# Search bound for "the next open session": the longest closed stretch any
# calendar here models is CN Golden Week plus both flanking weekends (measured
# max over 2014-2030: US 3 days, CN 10, HK 6 — pinned by
# tests/test_qledger_horizon_clock.py). Bounded rather than a `while` loop so a
# broken calendar rule fails closed (None) instead of spinning.
_MAX_CLOSED_STRETCH_DAYS = 15

# --------------------------------------------------------------------------- #
# THE MARKET DISPATCH — a claim resolves on the calendar of the exchange it is
# PRICED on, never on NYSE by default.
# --------------------------------------------------------------------------- #
# THE DEFECT THIS REPAIRS. The first cut of this clock resolved EVERY claim
# through `lib.nyse_calendar`. The endpoint strictness in `_leg_ret_in_window`
# then requires the window's own fill/coverage bars to exist in each leg's
# store — so a CN-priced claim (5,726 live: china_news, cn_importance_v0,
# cn_importance_v0_pit, china_special_sits) got a window whose endpoints are
# NYSE sessions while its legs trade the A-share calendar. Two measured
# consequences on the live corpus (both reproduced in the commit message):
#   * 31.9% of live CN windows were the WRONG LENGTH — a "21 trading day" claim
#     spanning 20 or 22 A-share sessions, because US-only closures (Jul 3,
#     Labor Day) are not CN closures;
#   * on a representative 2025-2026 anchor sweep, 5.9% of h=21 CN windows land
#     an endpoint on a CN-only closure (Golden Week, Spring Festival) and are
#     therefore PERMANENTLY ungradeable — refused by rule 5, forever, because
#     no A-share bar will ever exist on that date.
# The CEO's rule — "resolve the exit using the canonical exchange calendar" —
# names the exchange the claim is priced on. For an A-share claim that is SSE/
# SZSE, not NYSE.
MARKET_US = "US"
MARKET_CN = "CN"
MARKET_HK = "HK"

#: market key -> its rule-computed session calendar module. Every module here
#: exposes the same two primitives this clock needs (`is_session`,
#: `last_session_on_or_before`); the forward walkers below are written over
#: `is_session` because the three modules do NOT share a forward API
#: (`nyse_calendar.sessions_between` returns a LIST of dates,
#: `cn_calendar.sessions_between` returns a COUNT, `hk_calendar` has none).
CLOCK_CALENDARS = {
    MARKET_US: _nyse_calendar,
    MARKET_CN: _cn_calendar,
    MARKET_HK: _hk_calendar,
}

# THE RESOLVER'S SUPPORTED DATE RANGE, PER MARKET. Each calendar models a finite
# span, and outside it the answer is confidently wrong rather than absent — so
# the clock declares its range and returns None outside it (fail closed) instead
# of guessing.
#
# US — floor only. `lib.nyse_calendar` computes SCHEDULED holidays from the rules
#   for any year (MLK from 1998, Juneteenth from 2022), but UNSCHEDULED full-day
#   closures cannot be derived and live in a hand-maintained list:
#   `ONE_OFF_CLOSURES` holds Hurricane Sandy (2012-10-29/30), the 2018-12-05 Bush
#   day of mourning and the 2025-01-09 Carter day of mourning — and NOTHING
#   earlier. It is blind to every pre-2012 one-off closure (2001-09-11..14,
#   2004-06-11 Reagan, 2007-01-02 Ford, 1994-04-27 Nixon, …), each of which would
#   place a session-counted exit one or more sessions LATE without any signal.
#   The floor is the first day after the earliest modelled one-off closure; every
#   qledger claim asof is 2025+, so nothing live sits near it. Moving it EARLIER
#   requires appending the missing closures to `ONE_OFF_CLOSURES` first.
# CN / HK — floor AND CEILING. Both calendars are lunar-table driven
#   (cn_calendar: LNY_FIRST / QINGMING / DRAGON_BOAT / MID_AUTUMN; hk_calendar:
#   LNY_FIRST / CHING_MING / BUDDHA / TUEN_NG / MID_AUTUMN / CHUNG_YEUNG), and
#   every one of those tables spans 2014-2030 exactly. Outside it the module does
#   not raise — it silently returns a holiday set with NO lunar closures at all
#   (cn_calendar.holidays(2031) is Jan 1 + May 1 + Golden Week), so a 2031 exit
#   would walk straight through Spring Festival. The ceiling is therefore checked
#   against the resolved EXIT, not only the anchor. Extending it means extending
#   those tables from the exchange notices first.
CLOCK_SUPPORTED_FROM = date(2012, 10, 31)          # US floor (name kept: US default)
CLOCK_MARKET_SUPPORT: dict[str, tuple[date, date | None]] = {
    MARKET_US: (CLOCK_SUPPORTED_FROM, None),
    MARKET_CN: (date(2014, 1, 1), date(2030, 12, 31)),
    MARKET_HK: (date(2014, 1, 1), date(2030, 12, 31)),
}

# DISCLOSED RESIDUAL — the CN table is deliberately INCOMPLETE, and this clock
# inherits that. `lib.cn_calendar` encodes only closures that recur EVERY year
# (its own "DIRECTION OF ERROR" note): the variable tail days of a long Golden
# Week or Spring Festival read as sessions, and State-Council makeup Saturdays
# read as closures. For a staleness banner both directions are safe. Here they
# are not symmetric:
#   * a real closure we call a session -> the exit lands on a day with no bar ->
#     `_leg_ret_in_window` REFUSES the window (endpoint assertion) and the claim
#     shows up in `n_blocked_by_coverage`. Fail closed, visible, correct.
#   * a real session we call a closure (a makeup Saturday) -> the exit lands one
#     session late and the window is graded ONE SESSION LONG under the declared
#     label. This is the residual: bounded to +1 session, and undetectable by the
#     endpoint assertion because the bar does exist.
# Not repaired here: the fix is a makeup-workday table in `lib.cn_calendar`
# (State Council annual notice), which is that module's scope, not this one's.
# It is recorded rather than left for the next reader to rediscover.
CLOCK_CN_RESIDUAL = "cn_makeup_workday_unmodelled_max_one_session_long"


class HorizonClockMismatch(ValueError):
    """Raised when observations produced under DIFFERENT grading clocks would be
    pooled. Two rows both saying ``horizon_d=21`` are not comparable when one was
    graded on the legacy calendar approximation and the other on 21 exchange
    sessions — pooling them launders a measurement-basis change into a track
    record. Fail closed."""


class HorizonWindow(NamedTuple):
    """The ONE resolved window every clock consumer reads.

    entry_anchor  the effective entry date (post-embargo asof); may be a non-session
    fill_date     the shared next-bar fill SESSION (first session STRICTLY after
                  the anchor) — one date for every leg, so subject/bench/control
                  can never measure different horizon lengths
    exit_date     the authoritative exit boundary in the DECLARED unit
    coverage_date the session a price store must cover for this window to be
                  matured (== exit_date under trading_days; the last session
                  on/before exit_date under calendar_days, since a calendar exit
                  can land on a weekend or a holiday)
    market        the exchange calendar every date above was resolved on — the
                  market the claim is PRICED in, never a default
    """
    entry_anchor: date
    fill_date: date
    exit_date: date
    coverage_date: date
    horizon_d: int
    horizon_unit: str
    clock_version: str
    market: str = MARKET_US


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _calendar_for(market: str):
    """The session calendar module for a market key. Raises on an unknown key —
    a market this clock has no calendar for must be refused UPSTREAM (see
    `resolve_claim_market`), never answered with somebody else's sessions."""
    cal = CLOCK_CALENDARS.get(market)
    if cal is None:
        raise ValueError(
            f"no session calendar for market {market!r}; "
            f"known markets are {tuple(sorted(CLOCK_CALENDARS))}")
    return cal


@lru_cache(maxsize=8192)
def _next_session_after(market: str, d: date) -> date | None:
    """First session on `market` STRICTLY after `d`, or None.

    Written over `is_session` rather than any module's own forward helper
    because the three calendars do not share one (`nyse_calendar.sessions_between`
    returns dates, `cn_calendar.sessions_between` returns a COUNT, `hk_calendar`
    has neither). Bounded by `_MAX_CLOSED_STRETCH_DAYS` so a broken rule table
    fails closed instead of spinning."""
    cal = _calendar_for(market)
    for i in range(1, _MAX_CLOSED_STRETCH_DAYS + 1):
        cand = d + timedelta(days=i)
        if cal.is_session(cand):
            return cand
    return None


@lru_cache(maxsize=16384)
def _session_n_forward(market: str, first: date, n: int) -> date | None:
    """The session exactly `n` sessions AFTER `first` on `market`, or None.

    Same fail-closed contract as `lib.nyse_calendar.session_n_forward`, which
    this reproduces exactly for `MARKET_US` (that helper indexes
    `sessions_between(first, first + 3n + 10)[n]`; widening the search span
    cannot change which session is the nth). None when `first` is not itself a
    session, or when the calendar cannot reach that far inside the search span."""
    cal = _calendar_for(market)
    if n < 0 or not cal.is_session(first):
        return None
    if n == 0:
        return first          # matches nyse_calendar.session_n_forward(first, 0)
    seen = 0
    # 3n + 30 calendar days covers n sessions plus weekends and the longest
    # modelled closed stretch (CN Golden Week + both flanking weekends = 10d).
    for i in range(1, 3 * n + 30 + 1):
        cand = first + timedelta(days=i)
        if cal.is_session(cand):
            seen += 1
            if seen == n:
                return cand
    return None


def next_session_strictly_after(d: date, market: str = MARKET_US) -> date | None:
    """First session STRICTLY after `d` on `market` (the shared next-bar fill).

    `d` itself need not be a session — a claim's asof can be a Saturday or a
    holiday. None when the calendar cannot find one inside the longest possible
    closed stretch (fail closed rather than invent a fill)."""
    return _next_session_after(market, _as_date(d))


def resolve_horizon_window(entry_anchor: Any, horizon_d: int,
                           horizon_unit: str,
                           market: str = MARKET_US) -> HorizonWindow | None:
    """THE clock resolver (contract rule 4). Every consumer — `check_by`,
    maturity, the graded window, the rendered ruler — derives from this and only
    this. None when the window cannot be resolved (fail closed).

    trading_days: the exit is resolved by canonical exchange SESSION arithmetic
    on the calendar of the market the claim is PRICED in (`market`, dispatched
    through `CLOCK_CALENDARS`) — NOT `pd.Timedelta`, NOT a 1.4x fudge, and NOT
    `pd.offsets.BusinessDay` (BusinessDay counts Mon–Fri and so silently walks
    THROUGH market holidays: from a Wednesday before Thanksgiving, 2 BusinessDays
    lands on the Friday half-session having counted a day the market was shut).

    THE MARKET IS AN INPUT, NOT A DEFAULT, FOR EVERY CLAIM PATH. The `MARKET_US`
    default here exists only so a direct caller asking a US question keeps a
    one-line call; `make_claim`, `_validate_claim` and `grade_claim` all pass the
    claim's OWN market from `resolve_claim_market`, and refuse the claim outright
    when it cannot be determined. A CN claim resolved on NYSE sessions is not
    approximately right — see the MARKET DISPATCH note above for the two measured
    failure modes (wrong window LENGTH, permanently unreachable endpoints).

    WHY THE RULES CALENDAR AND NOT THE PRICE-STORE INDEX. The store index is a
    record of what was COLLECTED, not of what the exchange held: it has known
    holes (`collectors/cboe.KNOWN_PERMANENT_GAPS`, and `lib.nyse_calendar` exists
    precisely because a frozen store cannot detect its own staleness), and it
    differs PER TICKER — so a store-derived ruler would hand subject, bench and
    control three different horizon lengths, which is the exact failure rule 5
    forbids. `lib.nyse_calendar` is rule-computed, stdlib-only, holiday-aware and
    identical for every leg. It is already the house pattern for this arithmetic
    (`engine/source_registry._add_trading_days`, `engine/basket_turn_watch.py`).
    The store still decides MATURITY (`coverage_date`) — it just does not get to
    define what a session is.

    SUPPORTED RANGE: per market, from `CLOCK_MARKET_SUPPORT`. Anchors before the
    market's floor return None rather than resolve, because the session ruler
    models no earlier unscheduled closure and would place the exit late without
    saying so. CN/HK additionally carry a CEILING, checked against the resolved
    EXIT as well as the anchor: their lunar holiday tables stop at 2030 and the
    modules do not raise past it, they just return a holiday set with no lunar
    closures in it — see the constant's note.

    MINIMUM WINDOW: the resolved window must contain at least TWO sessions
    (the fill bar and a later exit bar). A `calendar_days` horizon whose exit
    lands before the next session — 1 calendar day from a Friday fill — has no
    measurable return, and resolving it anyway produced a window that
    `_matured_window` called matured while `_leg_ret_in_window` refused on its
    two-bar guard. The two now agree BY CONSTRUCTION: such a horizon has no
    window at all, so it is never matured and never graded.
    """
    if horizon_unit not in HORIZON_UNITS:
        raise ValueError(
            f"horizon_unit must be one of {HORIZON_UNITS}, got {horizon_unit!r}")
    cal = _calendar_for(market)          # raises on an unknown market key
    try:
        h = int(horizon_d)
    except Exception:  # noqa: BLE001
        return None
    if h <= 0:
        return None
    try:
        anchor = _as_date(entry_anchor)
    except Exception:  # noqa: BLE001
        return None
    supported_from, supported_through = CLOCK_MARKET_SUPPORT[market]
    if anchor < supported_from:
        return None
    if supported_through is not None and anchor > supported_through:
        return None

    fill = _next_session_after(market, anchor)
    if fill is None:
        return None

    if horizon_unit == HORIZON_UNIT_TRADING:
        exit_date = _session_n_forward(market, fill, h)
        if exit_date is None:
            return None
        coverage = exit_date
    else:
        exit_date = fill + timedelta(days=h)
        # A calendar exit can land on a weekend/holiday; the bar that closes the
        # window is the last session on or before it. The lookback RAISES when a
        # calendar's rules are broken enough to show no session in 30 days — fail
        # closed here rather than propagate, so a bad rule table costs windows
        # (visible as ungradeable claims) and never a traceback in the nightly.
        try:
            coverage = cal.last_session_on_or_before(exit_date)
        except Exception:  # noqa: BLE001
            return None
        if coverage <= fill:
            # Zero measurable sessions after the fill (see MINIMUM WINDOW above).
            return None

    if supported_through is not None and max(exit_date, coverage) > supported_through:
        # The window ENDS past the calendar's modelled span — every closure after
        # the ceiling is invisible, so the exit would be confidently wrong.
        return None

    return HorizonWindow(
        entry_anchor=anchor,
        fill_date=fill,
        exit_date=exit_date,
        coverage_date=coverage,
        horizon_d=h,
        horizon_unit=horizon_unit,
        clock_version=CLOCK_V1,
        market=market,
    )


#: Reason codes `resolve_claim_market` returns when it cannot name ONE market.
#: Every one of these is a REFUSAL, not a fallback — see the function's note.
MARKET_UNDETERMINED_NO_LEG = "no_priced_leg"
MARKET_UNDETERMINED_UNKNOWN_SUFFIX = "unknown_exchange_suffix"
MARKET_UNDETERMINED_FOREIGN_EXCHANGE = "unsupported_exchange_suffix"
MARKET_UNDETERMINED_NOT_A_US_SYMBOL = "not_a_us_symbol"
MARKET_UNDETERMINED_MIXED = "mixed_markets"
MARKET_UNDETERMINED_NO_CALENDAR = "no_session_calendar_for_market"
#: round 5 — a ticker-shaped leg with NO exchange suffix, whose claim carries no
#: provenance market either, so nothing (shape or desk) can name a market for
#: it. See `_ticker_market`'s "NO SUFFIX AT ALL" note.
MARKET_UNDETERMINED_NO_PROVENANCE = "no_market_provenance"
#: P0a-2 — the two independent signals (ticker SHAPE and claim PROVENANCE) each
#: named a market and named DIFFERENT ones. Neither is authoritative alone, so
#: this is a contradiction to refuse, never a tie to break. See `_ticker_market`.
MARKET_UNDETERMINED_CONTRADICTION = "shape_provenance_contradiction"
#: P0a-2 — provenance named a market whose symbol shape this leg cannot have
#: (`AAPL` on a CN desk, `600519` on a US desk). Provenance is corroborated by
#: shape or it is refused; it never originates a market on its own.
MARKET_UNDETERMINED_SHAPE_EXCLUDES = "shape_excludes_provenance_market"
#: P0a-2 — a `^`-prefixed index symbol this clock has no market for. Index
#: symbols are enumerated (`INDEX_MARKET`), never inferred.
MARKET_UNDETERMINED_UNKNOWN_INDEX = "unknown_index_symbol"
#: P0a-2 — the claim carries no subject leg at all. Refused rather than resolved
#: off the DEFAULT BENCH, which is what used to happen. See `resolve_claim_market`.
MARKET_UNDETERMINED_NO_SUBJECT = "no_subject_leg"

#: The separator between a refusal reason's MACHINE-READABLE HEAD and its prose
#: tail. Everything before the FIRST occurrence is bounded-cardinality and safe to
#: bucket a histogram on; everything after it may name the offending ticker, the
#: anchor date, or the leg pair, and must never become a histogram key
#: (`clock_reason_head`, `count_unresolvable_clock_claims`).
CLOCK_REASON_SEP = " — "

#: EXCHANGE SUFFIXES THIS CLOCK REFUSES — an EXPLICIT, AUTHORITATIVE DENY-LIST.
#:
#: THE DEFECT THIS REPAIRS. The first two cuts of this dispatch discriminated on
#: the SHAPE of the suffix: "multi-letter => exchange, single letter => US share
#: class". That is right for `BRK.B` / `BRK.A` (527 legs in the live store) and
#: WRONG — silently, onto NYSE — for every real exchange whose Yahoo suffix is one
#: letter: `.L` (London), `.T` (Tokyo), `.F` (Frankfurt/Fukuoka). A shape
#: heuristic failed twice here; it is replaced by enumeration, and the residual
#: share-class branch now additionally requires the WHOLE symbol to pass the
#: house US-equity gate (`engine.ticker_shape.valid_us_ticker`).
#:
#: WHAT AN ENTRY CLAIMS, EXACTLY. Only this: "at least one non-US venue lists
#: symbols under this suffix, so a leg carrying it cannot be assumed to trade on a
#: calendar in `CLOCK_CALENDARS`." It does NOT claim to be the suffix's unique
#: meaning — `.F` is Frankfurt to one vendor and Fukuoka to another, `.CN` is the
#: Canadian Securities Exchange and not China, and `.N`/`.S` are Nagoya/Sapporo
#: under the Yahoo convention this repo's tickers follow while a RIC feed would
#: read `.N` as NYSE. Every entry produces the SAME outcome — a named, counted
#: refusal — so ambiguity between two foreign venues costs nothing, and the only
#: error that matters is an OMISSION (which grades a foreign name on NYSE).
#:
#: DIRECTION OF ERROR, STATED. Over-inclusion refuses a claim: visible, countable
#: (`count_unresolvable_clock_claims`), and repairable by mapping the suffix in
#: `session_anchor.MARKET_SUFFIX` + adding its calendar. Under-inclusion grades on
#: the wrong exchange calendar and says nothing. So this table errs INCLUSIVE.
#:
#: Suffixes in `MARKET_SUFFIX` are NOT repeated here — they are resolved, not
#: refused (`.TO`/`.V` map to CA and are then refused one step later by
#: `resolve_claim_market`, for the different and honest reason that this repo has
#: no Canadian session calendar). The disjointness is pinned by a test.
EXCHANGE_SUFFIXES_UNSUPPORTED: dict[str, str] = {
    # --- SINGLE-LETTER suffixes: the branch that used to fail open onto NYSE ---
    ".L": "London Stock Exchange",
    ".T": "Tokyo Stock Exchange",
    ".F": "Frankfurt Stock Exchange (Fukuoka under the JP convention)",
    ".N": "Nagoya Stock Exchange",
    ".S": "Sapporo Stock Exchange",
    # --- Greater China / Asia-Pacific ---
    ".BJ": "Beijing Stock Exchange",
    ".TW": "Taiwan Stock Exchange",
    ".TWO": "Taipei Exchange (OTC)",
    ".KS": "Korea Exchange (KOSPI)",
    ".KQ": "Korea Exchange (KOSDAQ)",
    ".NS": "National Stock Exchange of India",
    ".BO": "BSE (Bombay Stock Exchange)",
    ".SI": "Singapore Exchange",
    ".KL": "Bursa Malaysia",
    ".JK": "Indonesia Stock Exchange",
    ".BK": "Stock Exchange of Thailand",
    ".PS": "Philippine Stock Exchange",
    ".VN": "Ho Chi Minh Stock Exchange",
    ".AX": "Australian Securities Exchange",
    ".NZ": "New Zealand Exchange",
    # --- Europe ---
    ".DE": "Deutsche Boerse XETRA",
    ".BE": "Boerse Berlin",
    ".DU": "Boerse Duesseldorf",
    ".HM": "Boerse Hamburg",
    ".HA": "Boerse Hannover",
    ".MU": "Boerse Muenchen",
    ".SG": "Boerse Stuttgart",
    ".IL": "London Stock Exchange International Order Book",
    ".PA": "Euronext Paris",
    ".AS": "Euronext Amsterdam",
    ".BR": "Euronext Brussels",
    ".LS": "Euronext Lisbon",
    ".IR": "Euronext Dublin",
    ".MI": "Borsa Italiana",
    ".MC": "Bolsa de Madrid",
    ".VI": "Wiener Boerse",
    ".SW": "SIX Swiss Exchange",
    ".ST": "Nasdaq Stockholm",
    ".OL": "Oslo Boers",
    ".CO": "Nasdaq Copenhagen",
    ".HE": "Nasdaq Helsinki",
    ".IC": "Nasdaq Iceland",
    ".AT": "Athens Stock Exchange",
    ".WA": "Warsaw Stock Exchange",
    ".PR": "Prague Stock Exchange",
    ".BD": "Budapest Stock Exchange",
    ".RO": "Bucharest Stock Exchange",
    ".IS": "Borsa Istanbul",
    ".ME": "Moscow Exchange",
    # --- Middle East / Africa ---
    ".TA": "Tel Aviv Stock Exchange",
    ".SR": "Saudi Exchange (Tadawul)",
    ".QA": "Qatar Stock Exchange",
    ".KW": "Boursa Kuwait",
    ".JO": "Johannesburg Stock Exchange",
    ".CA": "Egyptian Exchange (Cairo)",
    # --- Americas (non-US) ---
    ".SA": "B3 (Sao Paulo)",
    ".MX": "Bolsa Mexicana de Valores",
    ".BA": "Bolsa de Comercio de Buenos Aires",
    ".SN": "Bolsa de Santiago",
    ".CN": "Canadian Securities Exchange",
    ".NE": "Cboe Canada (NEO)",
}


#: ROUND 5 — THE MARKET'S AUTHORITATIVE SOURCE IS THE CLAIM'S OWN PROVENANCE,
#: NOT THE TICKER STRING. Three rounds in a row (2, 3, 4) each patched a new
#: failure of the SAME assumption: "a claim's market can be read off the SHAPE
#: of its ticker." It cannot — a bare numeric like `600519` (Kweichow Moutai,
#: Shanghai) or `0700` (Tencent, Hong Kong) carries NO market information in
#: its shape at all, and the pre-round-5 fallback ("no suffix -> US") answered
#: US for those, silently, every time. The desk/claim_family a claim is
#: registered under is not a guess: `cn_importance_v0` / `cn_importance_v0_pit`
#: / `china_news` / `china_special_sits` price CN by construction (their
#: producers name a CN bench and pull from CN event stores); `us_importance_v0`
#: / `us_importance_v0_pit` / `radar` / `whitehouse` / `policy` price US by
#: construction. This table is that fact, made explicit and machine-readable —
#: it is consulted ONLY for a leg whose ticker shape carries no suffix (a real
#: exchange suffix is always a stronger, leg-level fact and is resolved first,
#: see `_ticker_market`); it never overrides one.
#:
#: A desk/family not listed here is NOT assumed to be either market — it falls
#: through to the shape-corroborated US fallback (`ticker_shape.valid_us_ticker`)
#: exactly as an unlisted desk always has, so every existing US lane (altdata,
#: narrative, intel_hub, basket_turn, flip_confirmation, placebo, …) is
#: untouched. Listing a desk here is a POSITIVE claim about its market and nulls
#: the shape fallback for that desk's non-suffixed legs — get it wrong and a
#: leg refuses loudly (counted) rather than resolving quietly on the wrong
#: calendar, which is the same inclusive-errs-safe design as
#: `EXCHANGE_SUFFIXES_UNSUPPORTED`.
#:
#: Both spellings a producer uses for the same family are listed (desk vs
#: claim_family sometimes drift — `china_special_situations.py` registers
#: `desk="china_special_sits"` but `claim_family="cn_special_sits"`).
DESK_MARKET: dict[str, str] = {
    "cn_importance_v0": MARKET_CN,
    "cn_importance_v0_pit": MARKET_CN,
    "china_news": MARKET_CN,
    "china_special_sits": MARKET_CN,
    "cn_special_sits": MARKET_CN,
    "us_importance_v0": MARKET_US,
    "us_importance_v0_pit": MARKET_US,
    "radar": MARKET_US,
    "whitehouse": MARKET_US,
    "policy": MARKET_US,
}


#: INDEX SYMBOLS ARE ENUMERATED, NEVER INFERRED (P0a-2).
#:
#: THE DEFECT THIS REPAIRS. A `^`-prefixed index symbol fails
#: `ticker_shape.plausible_symbol` (the `^` is not in `PLAUSIBLE_SYMBOL_RE`), so
#: the round-5 resolver read it as "contributes NO market information, same as
#: an absent leg" and skipped it. For a claim whose SUBJECT is an index that
#: leaves only the bench — and the bench defaults to `_DEFAULT_BENCH` (SPY) —
#: so `{'desk': 'radar', 'scope': {'key': '^HSI'}}` resolved (US, ''), grading
#: the Hang Seng on NYSE sessions against SPY, silently. The skip is right for a
#: symbolic MACRO label (`CN_CENSORSHIP_RISK` — nothing is priced); it is wrong
#: for an index, which is a real priced instrument on a real exchange.
#:
#: A `^` symbol therefore resolves through this table or is REFUSED BY NAME. It
#: is never inferred from the string: `^HSI` and `^GSPC` are shaped identically
#: and trade on different continents, so there is nothing in the shape to infer
#: from. An omission costs a counted refusal; a wrong guess costs a silent wrong
#: calendar — so, like `EXCHANGE_SUFFIXES_UNSUPPORTED`, this errs toward refusal.
#:
#: ZERO live legs today: no `^` symbol appears in any leg of the 46,630-claim
#: corpus, and `_DEFAULT_BENCH` is `SPY`, not `^GSPC`. This is prospective, and
#: `test_the_index_table_changes_nothing_on_the_live_corpus` pins that.
INDEX_MARKET: dict[str, str] = {
    # --- US ---
    "^GSPC": MARKET_US,     # S&P 500
    "^SPX": MARKET_US,      # S&P 500 (alternate vendor spelling)
    "^DJI": MARKET_US,      # Dow Jones Industrial Average
    "^IXIC": MARKET_US,     # Nasdaq Composite
    "^NDX": MARKET_US,      # Nasdaq 100
    "^RUT": MARKET_US,      # Russell 2000
    "^VIX": MARKET_US,      # CBOE Volatility Index
    "^NYA": MARKET_US,      # NYSE Composite
    "^XAX": MARKET_US,      # NYSE American Composite
    # --- Hong Kong ---
    "^HSI": MARKET_HK,      # Hang Seng
    "^HSCE": MARKET_HK,     # Hang Seng China Enterprises
    "^HSCC": MARKET_HK,     # Hang Seng China-Affiliated Corporations
    # --- Mainland China ---
    "^SSEC": MARKET_CN,     # SSE Composite
    "^SZSC": MARKET_CN,     # SZSE Composite
    "^CSI300": MARKET_CN,   # CSI 300
}

#: SHAPE ADMISSIBILITY, PER MARKET (P0a-2). "Could a symbol of this shape trade
#: on this market at all?" — the corroboration half of the agree-or-refuse rule.
#:
#: This is deliberately NOT a second market classifier. It answers a strictly
#: weaker question than `_ticker_market`'s enumeration: not "which market is
#: this?" but "is `market` even POSSIBLE for this string?". That is what lets
#: provenance decide a bare code without letting it override the string — a CN
#: desk's bare `600519` is admitted (6-digit A-share code), a US desk's bare
#: `600519` is refused (`valid_us_ticker` rejects a digit-first root), and the
#: refusal names which signal blocked it.
#:
#: The three predicates are mutually exclusive on every bare code, which is a
#: property worth having and is pinned by a test: a 6-digit code is CN and only
#: CN, a 1-5 digit code is HK and only HK, and everything `valid_us_ticker`
#: accepts is digit-first-free and therefore neither.
_CN_BARE_CODE_RE = re.compile(r"^\d{6}$")      # 600519 / 000001 / 300750
_HK_BARE_CODE_RE = re.compile(r"^\d{1,5}$")    # 0700 / 9988 / 5


def _shape_admits_market(ticker: str, market: str) -> bool:
    """Could a symbol shaped like `ticker` (already upper-cased, no exchange
    suffix) trade on `market`? PURE; consults no claim state.

    False is a POSITIVE exclusion — "this string cannot be that market" — and is
    what turns provenance from an override into a corroborated inference. An
    unknown market key is False (fail closed), never True."""
    if market == MARKET_US:
        return valid_us_ticker(ticker) is not None
    if market == MARKET_CN:
        return bool(_CN_BARE_CODE_RE.match(ticker))
    if market == MARKET_HK:
        return bool(_HK_BARE_CODE_RE.match(ticker))
    return False


def _provenance_market(claim: dict) -> str | None:
    """The market implied by a claim's OWN provenance — `claim_family` first
    (the finer-grained tag), falling back to `desk` — or None when neither
    names a market this table knows. PURE; never inspects a ticker string.

    This is the round-5 fix's primary source. `_ticker_market` calls it once
    per claim (not per leg — provenance is a property of the CLAIM) and uses
    the answer ONLY for a leg whose suffix names nothing; a leg with its own
    exchange suffix ignores this entirely (a real suffix outranks provenance,
    it is never overridden by it)."""
    if not isinstance(claim, dict):
        return None
    for key in (claim.get("claim_family"), claim.get("desk")):
        k = str(key or "").strip()
        if k in DESK_MARKET:
            return DESK_MARKET[k]
    return None


def _ticker_market(ticker: Any, provenance: str | None = None) -> tuple[str | None, str]:
    """(market, reason) for ONE priced leg. `reason` is "" on success.

    The mapped-suffix table is `engine.session_anchor.MARKET_SUFFIX` — the same
    one the board session bucketing reads — with ONE deliberate narrowing:
    `session_anchor.market_for_ticker` resolves an UNMAPPED suffix to US openly
    (its R3 ruling: approximate bucket edges are harmless there). Here that
    default is not harmless — it is exactly the "silently resolving on the wrong
    calendar" this dispatch exists to stop — so this function refuses instead.

    THE DISCRIMINATOR IS AN ENUMERATION AND PROVENANCE, NEVER A BARE SHAPE
    DEFAULT. Three earlier cuts each read the ticker STRING as the sole source
    of market truth and each failed a new way: round 2 hardcoded NYSE for
    every claim; round 3 read "single letter after the dot" as a US share
    class, which fails OPEN onto NYSE for `.L` / `.T` / `.F` (real exchanges);
    round 4 enumerated the exchange suffixes but still answered US for ANY
    ticker with no suffix at all — silently wrong for a bare A-share code like
    `600519` or `0700`, which carries NO market information in its shape. The
    order is now:

      1. suffix in `MARKET_SUFFIX`                   -> that market (a real
         exchange suffix is a leg-level fact and always wins)
      2. suffix in `EXCHANGE_SUFFIXES_UNSUPPORTED`   -> REFUSED, by name
      3. a residual, un-enumerated MULTI-letter suffix -> REFUSED, unknown
      4. a SINGLE-LETTER residual suffix on a symbol the house US-equity gate
         (`ticker_shape.valid_us_ticker`) accepts  -> US (share class: BRK.B/BRK.A)
      5. NO suffix at all, and not even ticker-SHAPED on any exchange
         (`ticker_shape.plausible_symbol` is False — a symbolic macro label
         like `CN_CENSORSHIP_RISK`, never a real subject) -> contributes NO
         market information, same as an absent leg (`MARKET_UNDETERMINED_NO_LEG`
         — `resolve_claim_market` skips it and lets another leg decide)
      6. NO suffix, ticker-SHAPED, and `valid_us_ticker` accepts it -> US, but
         as an INFERENCE, not a fact — so it goes through `_corroborate` with
         `shape_is_decisive=False` and a disagreeing provenance REFUSES it
         (`AAPL` on a CN desk is a contradiction). The gate is bounded on both
         sides: the enumeration above has taken every known exchange suffix,
         and `valid_us_ticker` must accept the whole symbol, so no bare
         digit-first or symbol-first code — `600519`, `000001`, `0700` — can
         reach US by shape alone.
      7. NO suffix, ticker-SHAPED, shape SILENT, and the claim's OWN provenance
         (`_provenance_market`) names a market -> THAT market, but ONLY where
         `_shape_admits_market` agrees the string could be one (a CN desk's
         6-digit `600519` is admitted; a US desk's is not, because
         `valid_us_ticker` positively excludes a digit-first root). Provenance
         corroborates a silent shape; it never overrides a speaking one.
      8. anything else                               -> REFUSED
         (`MARKET_UNDETERMINED_NO_PROVENANCE`) — a ticker-shaped leg with no
         suffix, no provenance and no US shape has nothing to determine its
         market from, and this clock fails closed rather than guess.

    ORDER MATTERS AND IS NOT THE ROUND-5 ORDER. Round 5 tried provenance BEFORE
    the shape fallback, which is how the string `SPY` itself resolved CN under a
    CN desk. The shape is now read FIRST, and provenance is reached only where
    the shape says nothing. P0a-2's rule, stated once:

        a HARD exchange fact in the string (rules 1, 4, and the `^` index table)
        WINS outright — provenance may not veto it;
        an INFERRED shape reading (rule 6) must AGREE with a speaking provenance;
        a SILENT shape (rule 7) lets provenance decide, if the shape admits it.

    A claim whose legs then straddle two markets is refused one level up, by
    `resolve_claim_market`, as MIXED — which is a fact about the claim, not a
    disagreement between two classifiers.

    Rule 2 is not hypothetical: four live `china_special_sits` claims are priced
    on `920007.BJ`-style Beijing Stock Exchange tickers, a suffix `MARKET_SUFFIX`
    does not carry. `market_for_ticker` calls them US, which would have graded
    Beijing names on NYSE sessions. They refuse, visibly, until `.BJ` is mapped
    in `session_anchor` (that module's scope, not this one's — mapping it here
    would fork the table this reuses).

    Every refusal reason is `HEAD{CLOCK_REASON_SEP}detail`: the head is
    bounded-cardinality and safe to bucket on, the detail names the offender.
    """
    if not ticker:
        return None, MARKET_UNDETERMINED_NO_LEG
    t = str(ticker).strip().upper()
    if not t:
        return None, MARKET_UNDETERMINED_NO_LEG

    # --- P0a-2: INDEX SYMBOLS, ENUMERATED (see INDEX_MARKET) ---------------- #
    # Checked before the suffix split: `^` symbols carry no exchange suffix and
    # fail `plausible_symbol`, so every later branch would read them as "absent
    # leg" and let the DEFAULT BENCH name the market.
    if t.startswith("^"):
        market = INDEX_MARKET.get(t)
        if market is None:
            return None, (f"{MARKET_UNDETERMINED_UNKNOWN_INDEX}"
                          f"{CLOCK_REASON_SEP}{t} is an index symbol this clock "
                          f"has no market for; index symbols are enumerated in "
                          f"INDEX_MARKET, never inferred from the string")
        return _corroborate(t, market, provenance, shape_is_decisive=True)

    head, _, tail = t.rpartition(".")
    suffix = f".{tail}" if head else ""
    if suffix:
        market = MARKET_SUFFIX.get(suffix)
        if market is not None:
            return _corroborate(t, market, provenance, shape_is_decisive=True)
        exchange = EXCHANGE_SUFFIXES_UNSUPPORTED.get(suffix)
        if exchange is not None:
            return None, (f"{MARKET_UNDETERMINED_FOREIGN_EXCHANGE}:{suffix}"
                          f"{CLOCK_REASON_SEP}{exchange}; this clock has no "
                          f"session calendar for it")
        if not (len(tail) == 1 and tail.isalpha()):
            return None, (f"{MARKET_UNDETERMINED_UNKNOWN_SUFFIX}:{suffix}"
                          f"{CLOCK_REASON_SEP}suffix is in neither the mapped "
                          f"table nor the known-exchange table")
        if valid_us_ticker(t) is None:
            # A single letter is only a share class on something the house gate
            # agrees is a US symbol at all.
            return None, (f"{MARKET_UNDETERMINED_NOT_A_US_SYMBOL}:{suffix}"
                          f"{CLOCK_REASON_SEP}a single-letter suffix reads as a US "
                          f"share class only on a symbol ticker_shape accepts")
        return _corroborate(t, MARKET_US, provenance, shape_is_decisive=True)

    # --- NO SUFFIX AT ALL (round 5) ---
    if not plausible_symbol(t):
        # Not shaped like a ticker on ANY exchange — a symbolic macro label
        # (`CN_CENSORSHIP_RISK`, a cohort date key, …), never a real priced
        # subject. It carries nothing to corroborate, refuse, or originate a
        # market FROM, so it is read exactly like an absent leg: the market
        # must come from a leg that IS priced, or from provenance applied
        # where a real ticker sits. Refusing it here would silently kill a
        # claim whose OTHER legs are perfectly resolvable (missing_tape's
        # `CN_CENSORSHIP_RISK` scope key against a `510300.SS` bench — round 5
        # blocker 2).
        return None, MARKET_UNDETERMINED_NO_LEG
    if valid_us_ticker(t) is not None:
        # The shape SPEAKS: `valid_us_ticker` accepts it, so US is a positive
        # shape reading and goes through the same corroboration as a suffix
        # (a US-shaped ticker on a CN desk is a contradiction, not a US claim).
        return _corroborate(t, MARKET_US, provenance, shape_is_decisive=False)
    if provenance is not None:
        # THE SHAPE IS SILENT (a bare code — 600519, 0700 — that names no
        # market on its own). Provenance may decide, but only where the shape
        # ADMITS that market: this is corroboration, not an override. A CN
        # desk's `600519` is admitted (6-digit A-share code); a US desk's
        # `600519` is refused, because `valid_us_ticker` positively excludes a
        # digit-first root and nothing else corroborates US.
        if _shape_admits_market(t, provenance):
            return provenance, ""
        return None, (f"{MARKET_UNDETERMINED_SHAPE_EXCLUDES}:{provenance}"
                      f"{CLOCK_REASON_SEP}{t} cannot be a {provenance} symbol, "
                      f"so the claim's own provenance is contradicted by the "
                      f"only other signal — refusing rather than trusting one")
    return None, (f"{MARKET_UNDETERMINED_NO_PROVENANCE}:{t}"
                  f"{CLOCK_REASON_SEP}no exchange suffix, no claim provenance "
                  f"names a market, and the shape is not a US ticker either — "
                  f"refusing rather than defaulting to US")


def _corroborate(ticker: str, shape_market: str, provenance: str | None,
                 *, shape_is_decisive: bool) -> tuple[str | None, str]:
    """Combine the two INDEPENDENT market signals for one leg — the P0a-2 rule.

    > Provenance and ticker shape are two independent signals. NEITHER IS
    > AUTHORITATIVE ALONE. Where both speak they must AGREE, or the leg is
    > refused and counted.

    THE HISTORY THIS ENCODES. Five rounds of this dispatch each picked ONE
    source and let it win, and each failed a new way. Rounds 2-4 made SHAPE the
    sole source: hardcoded NYSE; then "single letter suffix => US share class",
    which reads `.L`/`.T`/`.F` (London, Tokyo, Frankfurt) as US; then "no suffix
    => US", which reads `600519` and `0700` as US. Round 5 inverted it and made
    PROVENANCE the sole source for a no-suffix leg — so a US-listed desk
    emitting a bare A-share code resolved US, silently, on NYSE sessions. The
    error was never which source was picked; it was that ONE source was allowed
    to be sufficient. A US desk claiming `600519` is not a market to guess. It
    is a CONTRADICTION, and the only safe answer is refusal.

    BUT "NEITHER IS AUTHORITATIVE ALONE" IS A RULE ABOUT INFERENCES, NOT ABOUT
    FACTS, and `shape_is_decisive` is where that distinction lives:

      * True — A HARD EXCHANGE FACT IS IN THE STRING ITSELF: a mapped suffix
        (`.SS`/`.SZ`/`.HK`), an enumerated `^` index, or a share-class suffix on
        a symbol the house US gate accepts. **The shape WINS; provenance may not
        veto it.** `0700.HK` names the Hong Kong exchange in the ticker. That is
        DIRECT evidence about the INSTRUMENT. `DESK_MARKET` is indirect evidence
        about the PRODUCER — a summary of what a desk has typically priced, not
        a promise that it can never price anything else. Letting the weaker,
        indirect signal veto the stronger, direct one is the same "one source is
        sufficient" error the history above is made of, merely inverted.
      * False — THE SHAPE READING IS ITSELF AN INFERENCE: a bare symbol that
        `valid_us_ticker` happens to accept. Here the two signals are of
        comparable strength, so the agree-or-refuse rule binds: a disagreeing
        provenance makes it a CONTRADICTION and the leg is refused.

    THE DEFECT THIS REPAIRS — AND IT WAS THIS FUNCTION'S OWN. The first cut of
    P0a-2 documented exactly the distinction above, threaded `shape_is_decisive`
    through all four call sites, added a test pinning every call site's value…
    and then **never read the parameter in the body**. Every caller therefore
    got the agree-or-refuse arm, so a hard suffix WAS vetoed by provenance:

        {'desk': 'china_news', 'scope': {'key': '0700.HK'}, 'bench': '2800.HK'}
            -> (None, 'shape_provenance_contradiction:HK!=CN')

    while the SAME claim on the unlisted desk `altdata` resolved `('HK', '')`.
    Admissibility depended on whether a claim's desk happened to be enumerated,
    which is backwards; and since `DESK_MARKET` carries no HK entry at all while
    HK is a first-class market in `CLOCK_CALENDARS`, **no enumerated desk could
    ever claim a Hong Kong security.** The pinning test could not catch it: it
    asserts the parameter's value at each call site, not its effect, so it is a
    guard that cannot fail on the defect it exists to gate. It is now paired with
    `test_a_hard_exchange_suffix_is_never_vetoed_by_provenance`, which asserts
    the BEHAVIOUR.

    A genuinely cross-market claim is still refused — just for the honest reason.
    `600519.SS` under a US desk resolves CN on its own leg, and
    `resolve_claim_market` then sees {CN: 600519.SS, US: SPY} and refuses as
    MIXED, because those two legs have no single session ruler. Nothing is
    graded on the wrong calendar in either design; the difference is that this
    one does not also refuse the well-formed single-market claims.
    """
    if provenance is None or provenance == shape_market:
        return shape_market, ""
    if shape_is_decisive:
        # A hard exchange fact outranks a desk-level generalisation. The leg
        # stands; a claim whose OTHER legs sit in another market is still caught
        # one level up, by `resolve_claim_market`'s MIXED refusal.
        return shape_market, ""
    return None, (f"{MARKET_UNDETERMINED_CONTRADICTION}"
                  f":{shape_market}!={provenance}"
                  f"{CLOCK_REASON_SEP}{ticker} reads as {shape_market} only by "
                  f"shape INFERENCE while the claim's own provenance names "
                  f"{provenance}; two signals of equal strength disagree, so "
                  f"this is refused rather than resolved on whichever wins the tie")


def clock_reason_head(reason: Any) -> str:
    """The MACHINE-READABLE head of a clock refusal reason.

    Everything before the first `CLOCK_REASON_SEP`. This is what a histogram may
    bucket on: it carries the reason CLASS and, where the class is about a
    suffix or a market, that bounded token — and never the offending ticker, the
    anchor date, or the leg pair that follows the separator."""
    return str(reason or "").split(CLOCK_REASON_SEP)[0].strip()


def resolve_claim_market(claim: dict) -> tuple[str | None, str]:
    """The ONE market a claim's window resolves on, or (None, reason).

    FAIL CLOSED, THREE WAYS. Rule 5 gives subject, bench and control ONE shared
    window, so a claim only HAS a canonical exchange when all of its priced legs
    trade on one. This returns None — and `_validate_claim` then refuses the
    claim, and `grade_claim` grades nothing — when:

      * a leg carries a KNOWN foreign exchange suffix (`.L`, `.T`, `.F`, `.BJ`,
        … — `EXCHANGE_SUFFIXES_UNSUPPORTED`) or a suffix no house table can name
        at all (`_ticker_market`);
      * the legs span two markets (a `.SZ` subject against an SPY bench has no
        single session ruler, and picking one would hand two legs different
        horizon lengths);
      * the named market has no session calendar in `CLOCK_CALENDARS` — `.TO`
        and `.V` map to CA and this repo has no `lib/ca_calendar.py`, so a
        Canadian claim is refused rather than graded on somebody else's sessions;
      * a ticker-shaped leg carries no suffix, the claim's OWN provenance
        (`_provenance_market`) names no market, and the shape is not even a US
        ticker (round 5 — `MARKET_UNDETERMINED_NO_PROVENANCE`).

    Returning US "for now" in any of those cases is the failure this replaces.

    PROVENANCE IS DERIVED ONCE, PER CLAIM, AND OFFERED TO EVERY LEG. It is the
    claim's own desk/claim_family (`_provenance_market`) — never re-derived
    from a ticker string — and a leg with its own exchange suffix ignores it
    entirely (a real suffix is a stronger, leg-level fact, see `_ticker_market`
    rule 1). This is what lets `missing_tape`'s `CN_CENSORSHIP_RISK` scope key
    (no suffix, not even ticker-shaped) sit beside a `510300.SS` bench without
    either leg inventing a market: the symbolic key contributes nothing (same
    as an absent leg) and the bench's own suffix decides CN, unaided.
    """
    scope = claim.get("scope") if isinstance(claim.get("scope"), dict) else {}
    provenance = _provenance_market(claim)
    subject = scope.get("key")
    if not subject:
        # P0a-2 — A CLAIM WITH NO SUBJECT LEG IS REFUSED, NOT RESOLVED OFF THE
        # DEFAULT BENCH. Without this the subject was simply skipped and
        # `_DEFAULT_BENCH` (SPY) named US for a claim that has no subject at
        # all, so ANY malformed or partially-built claim resolved US silently.
        # `_validate_claim` already rejects a claim missing `scope.key`, so this
        # is unreachable through registration — but `resolve_claim_market` is a
        # public entry point that callers and tests reach directly, and this
        # exact fail-open is what made a malformed probe report a defect that
        # did not exist (see research/EVAL_OS_P0A_HORIZON_CLOCK.md §3). A
        # function whose answer is "US" for an empty claim is not fail-closed.
        return None, (f"{MARKET_UNDETERMINED_NO_SUBJECT}"
                      f"{CLOCK_REASON_SEP}the claim names no scope.key, so the "
                      f"only legs left are the bench and control — resolving "
                      f"there would let the DEFAULT bench name the market")
    # EXACTLY the legs `grade_claim` prices, including its bench default — so the
    # market the validator refuses on and the market the grader would have used
    # can never be two different answers.
    legs = [subject, claim.get("bench") or _DEFAULT_BENCH,
            claim.get("control")]
    markets: dict[str, str] = {}          # market -> the leg that named it
    for leg in legs:
        if not leg:
            continue
        m, reason = _ticker_market(leg, provenance)
        if m is None:
            if reason == MARKET_UNDETERMINED_NO_LEG:
                continue
            # The leg goes AFTER the separator: it is the detail, never a
            # histogram key (`clock_reason_head`).
            return None, f"{reason}; leg {leg}"
        markets.setdefault(m, str(leg))
    if not markets:
        return None, MARKET_UNDETERMINED_NO_LEG
    if len(markets) > 1:
        detail = ", ".join(f"{m}={t}" for m, t in sorted(markets.items()))
        return None, f"{MARKET_UNDETERMINED_MIXED}{CLOCK_REASON_SEP}{detail}"
    market = next(iter(markets))
    if market not in CLOCK_CALENDARS:
        return None, (f"{MARKET_UNDETERMINED_NO_CALENDAR}:{market}"
                      f"{CLOCK_REASON_SEP}no calendar module in CLOCK_CALENDARS")
    return market, ""


def claim_window(claim: dict, horizon_d: int,
                 entry_anchor: str | None = None) -> HorizonWindow | None:
    """THE window for a claim at one horizon — the single call every consumer
    makes so the market dispatch cannot be applied in one place and forgotten in
    another (it was: the nightly's maturity pre-gate ran the LEGACY calendar
    function for every claim, explicit-clock ones included).

    None for a legacy (unitless) claim — those grade through `_fwd_ret`/`_matured`
    and have no resolved window at all — and None when the market cannot be
    determined or the window cannot be resolved."""
    unit = claim_horizon_unit(claim)
    if unit is None:
        return None
    market, _reason = resolve_claim_market(claim)
    if market is None:
        return None
    anchor = entry_anchor if entry_anchor is not None else _entry_date(claim)
    return resolve_horizon_window(anchor, horizon_d, unit, market)


def check_by_is_a_graded_exit(horizon_d: int) -> bool:
    """True when a claim's `check_by` IS one of the exits the grader resolves.

    THE SCOPE OF THE HEADLINE GUARANTEE, MADE EXECUTABLE rather than asserted in
    prose. `check_by` is resolved at the claim's OWN `horizon_d`; the grader
    grades at `in_scope_horizons(horizon_d)`. As of P0b that list now includes
    the claim's own ruler whenever it sits at or below the ladder's ceiling
    (`GRADE_HORIZONS[-1]`, 63 today) — so this predicate is True for EVERY
    horizon_d <= 63 (on-rung, off-rung, or below the smallest rung — 7, 30, 60
    all now hold), not only the exact rungs 5/21/63.

    It is False only above that ceiling: a 126-trading-day policy claim still
    grades at 5, 21 and 63 sessions while its check_by sits at session 126, and
    that gap is intentional, not a bug — extending `GRADE_HORIZONS` /
    `in_scope_horizons` past 63d in the live nightly grader is forbidden by
    ruling LH-U6 (`config/ruling_graph.yml`). This predicate is exported so a
    caller (and a test) can ask the question instead of trusting a docstring.
    """
    try:
        h = int(horizon_d)
    except Exception:  # noqa: BLE001
        return False
    return h in in_scope_horizons(h)


def claim_horizon_unit(claim: dict) -> str | None:
    """The claim's DECLARED horizon unit, or None for a legacy (unitless) claim.
    An unrecognised value reads as None — a claim is never silently promoted onto
    the explicit clock on the strength of a typo."""
    unit = claim.get("horizon_unit")
    return unit if unit in HORIZON_UNITS else None


#: The market segment of a basis key for an explicit-clock row that carries no
#: `clock_market` stamp. Such a row exists only if it was written between the
#: first cut of this contract (NYSE-hardcoded, unstamped) and the market
#: dispatch. It gets its OWN basis rather than being folded into US: an unstamped
#: row is a row whose calendar is unknown, and "unknown" pools with nothing.
CLOCK_MARKET_UNSTAMPED = "market_unstamped"


def clock_basis_key(clock_version: Any, horizon_unit: Any,
                    clock_market: Any = None) -> str:
    """The basis key for one (clock_version, horizon_unit, market) triple.

    ONE constructor, so a caller (or a test) never hand-assembles the string and
    a later segment addition cannot leave a second spelling behind."""
    market = str(clock_market or CLOCK_MARKET_UNSTAMPED)
    return f"{clock_version}:{horizon_unit}:{market}"


def grade_clock_basis(grade: dict) -> str:
    """The grading-clock basis a grade ROW was produced under.

    ``CLOCK_LEGACY`` for every row lacking an explicit stamp (all rows written
    before this contract) — mirroring how `fill_convention` reads absent rows as
    ``asof_legacy``. Otherwise
    ``"<clock_version>:<horizon_unit>:<clock_market>"``. Fail closed: a stamped
    row whose unit is not in the vocabulary reads as legacy rather than as a
    fourth, unnamed basis.

    THE MARKET IS PART OF THE KEY, and that is the whole point of the boundary.
    Without it this function answered ``explicit_unit_v1:trading_days`` for a
    US-resolved row and for a CN-resolved row alike, so two observations measured
    on INCOMPATIBLE session calendars — 21 NYSE sessions and 21 SSE sessions are
    different spans of wall-clock time, and Golden Week/Thanksgiving fall in
    different places — pooled into one statistic through
    `partition_grades_by_clock`, `require_single_clock`, `_aggregate` and the §3
    gate. The clock basis exists to stop exactly that; a basis key blind to the
    ruler it was measured with does not."""
    cv = grade.get("clock_version")
    unit = grade.get("horizon_unit")
    if not cv or unit not in HORIZON_UNITS:
        return CLOCK_LEGACY
    return clock_basis_key(cv, unit, grade.get("clock_market"))


def partition_grades_by_clock(grades: Iterable[dict]) -> dict[str, list[dict]]:
    """Split grade rows by `grade_clock_basis`. The pooling boundary."""
    out: dict[str, list[dict]] = {}
    for g in grades:
        out.setdefault(grade_clock_basis(g), []).append(g)
    return out


def require_single_clock(grades: Iterable[dict], *, context: str = "") -> str:
    """Assert every row shares ONE grading-clock basis; return it.

    Raises `HorizonClockMismatch` on a mixed set. This is the refusal contract
    rule for "different horizon units / clock versions cannot be silently
    pooled" — it is asserted at the aggregation primitive, not left to callers
    to remember. Returns ``CLOCK_LEGACY`` for an empty set (nothing to pool)."""
    bases = sorted({grade_clock_basis(g) for g in grades})
    if len(bases) > 1:
        where = f" ({context})" if context else ""
        raise HorizonClockMismatch(
            f"refusing to pool grade rows across {len(bases)} grading-clock "
            f"bases{where}: {bases}. horizon_d alone does not make two "
            f"observations comparable — the legacy basis approximated the "
            f"horizon in calendar days, the explicit-unit clock resolves it in "
            f"the declared unit, and two explicit rows resolved on DIFFERENT "
            f"exchange calendars are two different rulers under one number."
        )
    return bases[0] if bases else CLOCK_LEGACY

# timestamp_quality enum + embargo, verbatim from [P2] / §2.2. `embargo` is the
# minimum delay applied to the entry anchor before a claim is gradeable; the
# special cases (EVENT_DATE / SNAPSHOT_DATE / CORRUPTED) are handled in
# `_embargo_ok` rather than as a timedelta.
_DEFAULT_BENCH = "SPY"

TIMESTAMP_QUALITY = {
    # name              -> (embargo_minutes, gradeable, note)
    "CRAWL_BOUNDED":   (0,        True,  "crawl time bounds the event; no embargo"),
    "PUBLISHER_STATED": (15,      True,  "publisher pubDate; +15min (reject pubDate < crawl-48h upstream)"),
    "DISCLOSURE_DATE": (1440,     True,  "regulatory disclosure; +1 business day"),
    "EVENT_DATE":      (0,        False, "event date is NOT a valid entry anchor"),
    "SNAPSHOT_DATE":   (0,        False, "point-in-time snapshot; display-only"),
    "CORRUPTED":       (0,        False, "corrupted timestamp; blocked + alert"),
}

# claim lifecycle status
STATUS_OPEN = "open"
STATUS_GRADED = "graded"       # all in-scope horizons matured
STATUS_REJECTED = "rejected"   # failed registration validation (kept for audit)

#: Prefix on the `reject_reason` of a claim refused because its declared horizon
#: clock could not resolve (unknown market, mixed markets, no calendar for the
#: market, or an anchor/exit outside the calendar's modelled span). Stable so the
#: population is COUNTABLE rather than grep-able — see
#: `count_unresolvable_clock_claims` and the § NO ZOMBIE CLAIMS note in
#: `_validate_claim`.
REJECT_CLOCK_UNRESOLVABLE = "clock_unresolvable"

# track-record state chips (D10 / spec D10, "the chip states the UI reads")
STATE_UNGRADED = "UNGRADED"    # n_dates == 0
STATE_ACCRUING = "ACCRUING"    # 0 < n_dates < GRADED_MIN_DATES
STATE_GRADED = "GRADED"        # n_dates >= GRADED_MIN_DATES
# P0a: the state a PROMOTION gate reports when a family's grades straddle two
# EXPLICIT grading clocks (trading_days and calendar_days at the same horizon) —
# the one straddle with no non-arbitrary basis to promote on, so the gate refuses.
# A legacy+explicit straddle is NOT this state: it evaluates inside the explicit
# basis (`_authority_clock_basis`), because a permanent refusal would make the
# migration non-terminating. Display never refuses — it selects and labels
# (`_select_single_clock_block`).
STATE_MIXED_CLOCK = "MIXED_CLOCK"
# P0c-2 — CEO ruling 2026-08-13 §5. "Legacy-clock evidence remains VISIBLE but
# cannot independently create a new promotion after the explicit-clock
# discontinuity." A family whose evaluated `promotion_check` basis resolved to
# CLOCK_LEGACY — i.e. it holds no explicit-clock grade row at all — that
# reaches GRADED territory (n_dates >= GRADED_MIN_DATES on that legacy basis)
# reads THIS state instead of STATE_GRADED. The numbers (n_dates, hit_rate,
# wilson_ci_low) are unchanged and still reported alongside it — this state
# withdraws AUTHORITY, not disclosure. It is deliberately distinct from:
#   * STATE_GRADED         — means "authority-eligible pending the CI leg";
#                            never true on a legacy-only basis after this ruling.
#   * STATE_MIXED_CLOCK    — a DIFFERENT refusal, for a DIFFERENT reason: two
#                            EXPLICIT bases colliding with no non-arbitrary
#                            basis to pick. A legacy-only family is not mixing
#                            anything; it simply has no explicit-clock evidence
#                            yet. See `promotion_check`.
STATE_LEGACY_NOT_AUTHORITY_ELIGIBLE = "LEGACY_NOT_AUTHORITY_ELIGIBLE"
GRADED_MIN_DATES = 25          # §3: n_graded >= 25 DATES (not overlapping obs)


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(root: Path | str | None) -> Path:
    return Path(root) if root else config.ROOT


def _claim_id(desk: str, asof: str, scope_key: str, horizon_d: int,
              direction: int, salt: str = "") -> str:
    """Deterministic, collision-resistant id. Stable across re-registration of
    the same logical claim so adapters are idempotent (like radar's snapshot_key
    and altdata's `{asof}-{ticker}-altconv`)."""
    raw = f"{desk}|{asof}|{scope_key}|{horizon_d}|{direction}|{salt}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def body_hash(body: str) -> str:
    """sha256 of a text body — the `source_id` convention shared with
    qual_extraction.v1 (§2.4) and the Missing-Tape body-hash leg (D8). Exposed
    here so desks stamp a stable id without importing the extraction lane."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def in_scope_horizons(horizon_d: int) -> list[int]:
    """The horizons a claim of this horizon_d grades at: every GRADE_HORIZON
    <= horizon_d, PLUS the claim's own declared ruler (P0b) — but only while
    that ruler sits AT OR BELOW the ladder's existing ceiling.

    THE DEFECT THIS REPAIRS. The docstring here used to promise "always at
    least the claim's own horizon", but the code only delivered that when the
    ladder came back EMPTY (horizon_d < 5). For every other value a claim was
    read at its own declared ruler only if that ruler happened to land exactly
    on 5, 21 or 63 — so a policy claim at horizon_d=30 graded at [5, 21] and
    NEVER at 30, forever, no matter how much time passed. That is not an
    accrual fact (more data would not have fixed it); it is a construction
    defect, and on the live corpus it made 9 family/horizon pairs (`policy`
    @ 30/42/45/60, `narrative_source_call` @ 26/27/28, `whitehouse` @ 6/7)
    permanently unreachable at their own ruler.

    THE RULE (CEO 2026-08-13 §6, P0b). `GRADE_HORIZONS` itself is UNCHANGED —
    still exactly (5, 21, 63); this function never adds a rung to the ladder,
    it only ever adds ONE extra element to a single claim's own grade list.
      * declared ruler <= the ladder's ceiling (`GRADE_HORIZONS[-1]`, 63 today)
        -> the ruler is included, even when off-rung (7 -> [5, 7]; 30 ->
        [5, 21, 30]).
      * declared ruler > the ceiling -> NOT added here. `policy` claims at
        84/90/126 stay off-render / research scope, exactly as before — see
        `config/ruling_graph.yml` ruling LH-U6, which forbids extending
        GRADE_HORIZONS (or what feeds the live nightly grader) past 63d. This
        function's own-ruler addition never crosses that ceiling, so it
        cannot violate LH-U6 by construction: nothing above `GRADE_HORIZONS[-1]`
        is ever appended.
      * a horizon_d below the smallest rung (< 5) still falls through the
        empty-ladder branch unchanged and grades once, at its own clock — the
        pre-P0b behaviour for that case is preserved exactly.
    """
    hs = [h for h in GRADE_HORIZONS if h <= horizon_d]
    if not hs:
        return [horizon_d]
    ceiling = GRADE_HORIZONS[-1]
    if horizon_d <= ceiling and horizon_d not in hs:
        hs = hs + [horizon_d]
    return hs


# --------------------------------------------------------------------------- #
# benchmark / control resolution
# --------------------------------------------------------------------------- #
def default_bench_for(scope_type: str, scope_key: str) -> str:
    """The benchmark a scope grades against when the caller does not name one.
    entity/basket/sector -> SPY; a sector scope whose key is a GICS name still
    grades vs SPY at the claim level (the sector-matched *control* is the second
    leg, resolved separately). Macro claims MUST name their own bench (D4) — this
    returns SPY only as a non-macro default."""
    return _DEFAULT_BENCH


def control_for_sector(sector_name: str | None) -> str | None:
    """Sector-matched control ETF for entity/basket/sector claims (the second
    grading leg, D4). Returns None when the sector is unknown — a null control is
    a valid, honestly-recorded state (excess-vs-control simply stays null)."""
    if not sector_name:
        return None
    return _GICS_ETF.get(sector_name)


# --------------------------------------------------------------------------- #
# P0d — THE MATCHED-CONTROL EVIDENCE CONTRACT
# research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md (the binding clauses C1-C9)
# research/EVAL_OS_P0D_CONTROL_CENSUS.md (the grounding measurement)
#
# THE RULING THIS EXECUTES (CEO P0d): the BENCHMARK is the universal baseline;
# a MATCHED CONTROL is a stricter SECOND evidence basis, required exactly where a
# defensible matched counterfactual exists and is constructible at registration.
# No family is forced to invent a control; no family may claim matched-control
# evaluation without prospectively accrued, control-carrying claims.
#
# THE DEFECT THIS REPAIRS. `promotion_check(control_only=True)` was the blanket
# production call: every family was evaluated "vs matched control" while the
# store held 46,695 claims and ZERO control legs (census §0). With coverage
# exactly zero the control arm produced `ci_low=None` everywhere, so the gate
# was neither passing nor failing on the basis it named — it was silent, and the
# architecture doc meanwhile described a "matched-control grading substrate" as a
# live capability. Whether an evaluation is matched-control is now POLICY, read
# from one governed table, never inferred from which rows happen to carry data.
# --------------------------------------------------------------------------- #
CONTROL_POLICY_REQUIRED = "matched_control_required"
CONTROL_POLICY_BENCHMARK_ONLY = "benchmark_only"
CONTROL_POLICY_NOT_APPLICABLE = "not_applicable"

#: C4.2 — ONE global coverage floor, pre-registered. Tolerates a rare metadata
#: failure (the census's ADR tail) without permitting subset selection: at the
#: gate's own 25-date floor a family may carry at most one uncovered date.
#: DELIBERATELY NOT per-family-tunable — a per-family knob is subset selection
#: with a config file.
CONTROL_COVERAGE_MIN = 0.95

#: The evidence basis a verdict was reached on (C5.4). Every emitted verdict
#: carries exactly one of these, so "benchmark-relative" and "matched-control"
#: can never be read as the same sentence by a downstream surface (C6.1).
EVIDENCE_BASIS_MATCHED_CONTROL = "matched_control"
EVIDENCE_BASIS_BENCHMARK = "benchmark"
EVIDENCE_BASIS_NOT_APPLICABLE = "not_applicable"

# --------------------------------------------------------------------------- #
# THE GOVERNED CLASSIFICATION TABLE (C1.1/C1.2) — census §4, verbatim.
#
# CHANGING A FAMILY'S POLICY IS A GOVERNED ACT, never a drive-by: it requires
# (1) this table edited, (2) the exact-content pinning test in
# tests/test_qledger_control_policy.py updated in the SAME change, and (3) cited
# evidence in the PR (for a benchmark_only -> matched_control_required move, the
# census §5 condition: a registration-time control source covering >=95% of the
# family's real flow). This is the same governed-table pattern as `DESK_MARKET`.
#
# WHY IT IS NOT DERIVED. Policy is not a derivable fact. `config/qual_ladder.yml`
# is FIELD-keyed (one family appears under many fields), so a per-family policy
# there would be duplicated state; and deriving policy from row contents — "this
# family's rows carry controls, so evaluate it on controls" — is precisely the
# data-conditioned evaluation the ruling forbids (C1.4, adversarial control #7).
#
# A family ABSENT from this table is `unclassified` (C1.3): benchmark mechanics,
# labelled `unclassified`, and STRUCTURALLY INELIGIBLE for matched-control
# authority. Matched-control authority is opt-in by table edit only.
# --------------------------------------------------------------------------- #
FAMILY_CONTROL_POLICY: dict[str, str] = {
    # --- matched_control_required -------------------------------------------
    # The only two families where the counterfactual is BOTH economically
    # defensible AND constructible >=95% from an existing canonical source at
    # registration (census §3). Both are prospective-only families, so their
    # matched-control record is born clean — no historical rows exist to tempt a
    # backfill (C3.3).
    "stock_desk": CONTROL_POLICY_REQUIRED,
    "demand_chain": CONTROL_POLICY_REQUIRED,
    # --- benchmark_only ------------------------------------------------------
    # Legitimate benchmark-relative evidence, labelled as such, never marketed as
    # matched-control. For radar/policy/thematic_desk this is the PERMANENTLY
    # correct economics (the subject IS the theme's proxy, so a sector control
    # nets the claim against itself), not a data gap; for intel_hub (72%) and
    # altdata* (89%) it is a coverage condition with a named re-classification
    # path (census §5).
    "intel_hub": CONTROL_POLICY_BENCHMARK_ONLY,
    "altdata": CONTROL_POLICY_BENCHMARK_ONLY,
    "altdata_event": CONTROL_POLICY_BENCHMARK_ONLY,
    "altdata_flow": CONTROL_POLICY_BENCHMARK_ONLY,
    "altdata_mid": CONTROL_POLICY_BENCHMARK_ONLY,
    "altdata_slow": CONTROL_POLICY_BENCHMARK_ONLY,
    "radar": CONTROL_POLICY_BENCHMARK_ONLY,
    "policy": CONTROL_POLICY_BENCHMARK_ONLY,
    "whitehouse": CONTROL_POLICY_BENCHMARK_ONLY,
    "thematic_desk": CONTROL_POLICY_BENCHMARK_ONLY,
    "basket_turn.v1": CONTROL_POLICY_BENCHMARK_ONLY,
    "flip_confirmation.v1": CONTROL_POLICY_BENCHMARK_ONLY,
    # --- not_applicable ------------------------------------------------------
    # Salience/descriptive species: no directional skill proposition exists, so
    # no directional matched-control contract can apply. They grade MAGNITUDE
    # against the placebo tape (standards §4.2). `placebo` is itself the control
    # arm.
    "china_news": CONTROL_POLICY_NOT_APPLICABLE,
    "cn_importance_v0": CONTROL_POLICY_NOT_APPLICABLE,
    "cn_importance_v0_pit": CONTROL_POLICY_NOT_APPLICABLE,
    "us_importance_v0": CONTROL_POLICY_NOT_APPLICABLE,
    "us_importance_v0_pit": CONTROL_POLICY_NOT_APPLICABLE,
    "cn_special_sits": CONTROL_POLICY_NOT_APPLICABLE,
    "narrative_source_call": CONTROL_POLICY_NOT_APPLICABLE,
    "narrative_flare_state": CONTROL_POLICY_NOT_APPLICABLE,
    "communique_diff": CONTROL_POLICY_NOT_APPLICABLE,
    "missing_tape": CONTROL_POLICY_NOT_APPLICABLE,
    "extraction_8k": CONTROL_POLICY_NOT_APPLICABLE,
    "placebo": CONTROL_POLICY_NOT_APPLICABLE,
}


def family_control_policy(family: str | None) -> tuple[str, bool]:
    """(policy, classified) for a claim family — C1.3.

    `classified` is False for a family absent from `FAMILY_CONTROL_POLICY`; such
    a family runs BENCHMARK mechanics and is labelled `unclassified`, and it can
    never reach matched-control authority (that requires a table edit, never a
    row-level field). Row contents NEVER influence the answer."""
    policy = FAMILY_CONTROL_POLICY.get(str(family or ""))
    if policy is None:
        return CONTROL_POLICY_BENCHMARK_ONLY, False
    return policy, True


# --------------------------------------------------------------------------- #
# CONTROL CONSTRUCTION (C2.3) — existing primitives only, no new engine
# --------------------------------------------------------------------------- #
#: Census D0-2 — `data/universe/membership.parquet`, the only broad
#: ticker->sector source in the repo, speaks TWO sector vocabularies: GICS names
#: ("Information Technology") mixed with Yahoo-style ones ("Technology"). A naive
#: join through `control_for_sector` silently nulls on roughly half the universe,
#: which is D0-1's defect class one file over: intel_hub's control wiring was
#: dead for four months because a lookup that returned None was a legal state and
#: nothing alarmed. The normalisation is therefore EXPLICIT and the refusals are
#: countable — never a silent None from a vocabulary mismatch.
_SECTOR_ALIASES: dict[str, str] = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Financial": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Basic Materials": "Materials",
    "Consumer Defensive": "Consumer Staples",
}


def sector_gics_etf(sector: str | None) -> str | None:
    """Sector name -> GICS sector ETF, through the explicit alias normalisation
    (D0-2). None for an empty, unknown or unmapped vocabulary value — the CALLER
    counts that refusal (C2.4: `vocabulary_unmapped` vs `sector_absent`).

    NOT a ticker map. An ETF ticker is not a sector name: `sector_gics_etf("QQQ")`
    is None, because answering it would re-create D0-1 in reverse — a producer
    handing this function its own ETF stamps and getting a plausible-looking
    control back.

    `control_for_sector()` above is deliberately left byte-identical: display-tier
    callers depend on its exact null-tolerant behaviour."""
    key = str(sector or "").strip()
    if not key:
        return None
    return _GICS_ETF.get(_SECTOR_ALIASES.get(key, key))


#: {resolved-root -> {UPPERCASE ticker -> raw sector name}}. Lazily built, one
#: parquet read per root per process. `None` marks a root whose membership file
#: is absent/unreadable, so a missing file costs one failed read, not one per
#: lookup.
_MEMBERSHIP_SECTORS: dict[str, dict[str, str] | None] = {}
_MEMBERSHIP_FILE = ("data", "universe", "membership.parquet")


def sector_of_ticker(ticker: str | None, root: Path | str | None = None) -> str | None:
    """The RAW sector name `data/universe/membership.parquet` records for a
    ticker, or None when the file or the ticker is absent.

    THE CANONICAL CONSTRUCTION for `demand_chain`'s control leg (C2.3): the
    control is `sector_gics_etf(sector_of_ticker(subject))`, resolved at
    REGISTRATION from registration-time metadata only. It returns the raw
    vocabulary value rather than the ETF so a caller can tell the two refusal
    classes apart — `None` here is `sector_absent`, `sector_gics_etf(...) is None`
    on a non-empty sector is `vocabulary_unmapped` (C2.4).

    FAIL-OPEN on a missing/unreadable file (a null control is a legal state and
    this is not a gate) — but the absence is logged once per root, because
    silence is exactly how D0-1 stayed dead for four months."""
    key = str(ticker or "").strip().upper()
    if not key:
        return None
    root_p = _root(root)
    cache_key = str(root_p)
    if cache_key not in _MEMBERSHIP_SECTORS:
        mapping: dict[str, str] | None = None
        path = root_p.joinpath(*_MEMBERSHIP_FILE)
        try:
            df = pd.read_parquet(path, columns=["ticker", "sector"])
            mapping = {}
            for t, s in zip(df["ticker"], df["sector"]):
                tk = str(t or "").strip().upper()
                sec = str(s or "").strip()
                if tk and sec and sec.lower() != "nan":
                    mapping.setdefault(tk, sec)   # keep-FIRST, deterministic
        except Exception as exc:  # noqa: BLE001 — fail open, but say so once
            log.debug("sector_of_ticker: no usable membership store at %s (%s)",
                      path, exc)
            mapping = None
        _MEMBERSHIP_SECTORS[cache_key] = mapping
    mapping = _MEMBERSHIP_SECTORS[cache_key]
    if not mapping:
        return None
    return mapping.get(key)


def control_leg_is_valid(claim: dict) -> bool:
    """C2.2 — is this claim's control leg a VALID matched control?

    A valid control is a non-null ticker with `control != scope.key` and
    `control != bench`. A control equal to the subject nets the claim against
    itself; a control equal to the bench relabels the baseline as a stricter
    basis. Both are MISSING-CONTROL: the row still registers, and the absence is
    COUNTED into coverage (C4) rather than quietly passing as evidence.

    Compared case-insensitively: `xlk` and `XLK` are one instrument, and a
    casing difference must not be able to launder a self-netted claim."""
    if not isinstance(claim, dict):
        return False
    control = str(claim.get("control") or "").strip().upper()
    if not control:
        return False
    scope = claim.get("scope") if isinstance(claim.get("scope"), dict) else {}
    subject = str(scope.get("key") or "").strip().upper()
    bench = str(claim.get("bench") or "").strip().upper()
    return control != subject and control != bench


# --------------------------------------------------------------------------- #
# THE CONTROL EVIDENCE CLOCK (C3.1/C3.4) — write-once, registrar-written
# --------------------------------------------------------------------------- #
#: One file per required family. NOTHING PRE-CREATES THESE: a timestamp written
#: by hand is the retrospective stamping this design forbids, and this PR ships
#: with zero of them and reports that fact rather than a placeholder (C3.4/C9).
_CONTROL_CLOCK_DIR = ("data", "qledger", "control_evidence_clock_start")


def _clock_family_slug(family: str) -> str:
    """Filename-safe slug for a family key. Family names are house literals
    (`basket_turn.v1`), but a slug keeps a future key with a slash or a space
    from escaping the directory."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(family or "")).strip("._-") or "_"


def _control_clock_path(family: str, root: Path | str | None = None) -> Path:
    return _root(root).joinpath(*_CONTROL_CLOCK_DIR, f"{_clock_family_slug(family)}.json")


def read_control_clock_start(family: str, root: Path | str | None = None) -> dict | None:
    """The family's recorded control-evidence clock start, or None when it has
    NOT started. None is the honest answer for every family today (C9) and is
    never a miss, a zero, or a placeholder. Never raises."""
    try:
        path = _control_clock_path(family, root)
        if not path.exists():
            return None
        rec = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rec, dict) and rec.get("first_controlled_prospective_registration_utc"):
            return rec
        return None
    except Exception as exc:  # noqa: BLE001
        log.error("read_control_clock_start(%s): unreadable clock record: %s",
                  family, exc)
        return None


def record_control_clock_start(family: str, *, horizon_d: Any,
                               horizon_unit: Any, control: Any,
                               git_sha: str | None = None,
                               root: Path | str | None = None,
                               now: str | None = None) -> dict:
    """WRITE-ONCE record of when a family's matched-control evidence began (C3.1).

    Written by the REGISTRAR — never by a producer — so no producer wiring can be
    bypassed around it, and it records the triggering claim's own declared
    horizon and control (C3.4).

    WRITE-ONCE IS THE WHOLE POINT. An existing record is returned UNCHANGED and
    every argument is ignored: a clock that can be moved is a clock that can be
    moved backwards, and a start date chosen after seeing the results is the
    retrospective stamping this contract exists to make impossible.

    Atomic tmp+replace so a reader never sees a partial record, guarded by an
    existence re-check so a concurrent second writer loses rather than clobbers.
    (The nightly registrar is single-writer; the guard closes the window to the
    `os.replace` itself, and the record is re-read from disk before returning, so
    the value a caller gets is always the value that actually persisted.)
    Never raises — a clock-write failure must not take down a registration."""
    existing = read_control_clock_start(family, root)
    if existing is not None:
        return existing
    rec = {
        "claim_family": str(family),
        "first_controlled_prospective_registration_utc": now or _now_iso(),
        "declared_horizon_d": horizon_d,
        "horizon_unit": horizon_unit,
        "control": control,
        "git_sha": git_sha,
    }
    try:
        path = _control_clock_path(family, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f"{path.name}.tmp"
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2,
                                  default=_json_default) + "\n", encoding="utf-8")
        if path.exists():                      # a concurrent writer won the race
            tmp.unlink(missing_ok=True)
            return read_control_clock_start(family, root) or rec
        tmp.replace(path)
        return read_control_clock_start(family, root) or rec
    except Exception as exc:  # noqa: BLE001
        log.error("record_control_clock_start(%s): clock write failed: %s",
                  family, exc)
        return rec


def _cohort_prospective(claim: dict, ref_date: date) -> bool:
    """C3.2(e) — is this claim PROSPECTIVE as of `ref_date`?

    True iff the claim declares an explicit `horizon_unit`, its window RESOLVES
    through `claim_window` (the one clock predicate — never a second
    implementation), and that window's `fill_date` is STRICTLY after `ref_date`.
    Unresolvable input is False: FAIL-CLOSED, and the caller counts it.

    THE TWO CALLERS PASS DIFFERENT REFERENCE DATES, and that is the design:
      * the REGISTRAR passes today (the registration date), so the clock starts
        only on a claim that was forward-looking when it was made;
      * the GATE passes `date(claim["timestamp"])` — the claim's own registration
        stamp — so a LATER import of old-asof rows can never join the cohort. A
        claim registered after its window had already begun fails this forever
        (adversarial control #5: historical backfill cannot mint authority).
    Passing "today" at gate time would have let exactly that import in, because
    every old row's window is in the past relative to nothing in particular."""
    try:
        if claim_horizon_unit(claim) is None:
            return False
        horizon_d = int(claim.get("horizon_d"))
        window = claim_window(claim, horizon_d)
        if window is None:
            return False
        return window.fill_date > _as_date(ref_date)
    except Exception:  # noqa: BLE001 — fail closed, never a member on a guess
        return False


# --------------------------------------------------------------------------- #
# CLAIM SCHEMA + registrar
# --------------------------------------------------------------------------- #
def _validate_claim(claim: dict) -> tuple[bool, str]:
    """Structural validation. Returns (ok, reason). Rejection is a first-class
    outcome — register() records rejected claims with status='rejected' so the
    fraction going dark under D4 is itself logged (D4: "the fraction that goes
    dark under this constraint is itself logged and reported")."""
    if not isinstance(claim, dict):
        return False, "claim is not an object"

    desk = str(claim.get("desk") or "").strip()
    if not desk:
        return False, "missing desk"

    asof = str(claim.get("asof") or "").strip()
    try:
        pd.Timestamp(asof)
    except Exception:  # noqa: BLE001
        return False, f"asof not a date: {asof!r}"

    scope = claim.get("scope")
    if not isinstance(scope, dict):
        return False, "missing scope object"
    stype = scope.get("type")
    skey = str(scope.get("key") or "").strip()
    if stype not in SCOPE_TYPES:
        return False, f"scope.type not in {SCOPE_TYPES}: {stype!r}"
    if not skey:
        return False, "missing scope.key"

    direction = claim.get("direction")
    if direction not in DIRECTIONS:
        return False, f"direction not in {DIRECTIONS}: {direction!r}"

    try:
        horizon_d = int(claim.get("horizon_d"))
    except Exception:  # noqa: BLE001
        return False, "horizon_d not an int"
    if horizon_d <= 0:
        return False, f"horizon_d must be positive: {horizon_d}"

    # P0a: an ABSENT horizon_unit is legal — it declares the LEGACY clock basis
    # and is never re-labelled. A PRESENT one must be in the narrow vocabulary;
    # a typo would otherwise read as legacy and silently grade on the old clock.
    if "horizon_unit" in claim and claim.get("horizon_unit") is not None:
        if claim.get("horizon_unit") not in HORIZON_UNITS:
            return False, (f"horizon_unit not in {HORIZON_UNITS}: "
                           f"{claim.get('horizon_unit')!r}")

    tq = claim.get("timestamp_quality")
    if tq not in TIMESTAMP_QUALITY:
        return False, f"timestamp_quality not in enum: {tq!r}"
    if tq == "CORRUPTED":
        return False, "timestamp_quality=CORRUPTED is blocked (D2/[P2])"

    bench = str(claim.get("bench") or "").strip()

    # D4: macro claims MUST name a machine-checkable observable at registration,
    # else they are rejected. "Machine-checkable" == a bench key we can price
    # (a ticker/series in the parquet layer). We validate it is *named*; whether
    # it resolves is a data-availability question the grader reports, not a
    # registration failure — but an empty/placeholder bench is rejected here.
    if stype == "macro":
        if not bench or bench.upper() in ("SPY", "NONE", "NULL"):
            return False, ("macro claim must name a machine-checkable observable "
                           "as `bench` (a rate/FX/breadth series) — D4")

    entry = claim.get("entry_levels")
    if entry is not None and not isinstance(entry, dict):
        return False, "entry_levels must be an object or null"

    # P0a — NO ZOMBIE CLAIMS. A claim that DECLARES a unit but whose clock cannot
    # resolve used to register as status=open with check_by=None: it could never
    # grade (grade_claim skips an unresolvable window), never close (status only
    # advances once every in-scope horizon matures), and was counted nowhere — a
    # silently immortal row. It is now REFUSED at registration, which is a
    # first-class, COUNTED outcome: register()/register_batch persist it with
    # status='rejected' and the reason, and `count_unresolvable_clock_claims`
    # reports the population. Fail closed, disclosed, countable.
    #
    # The predicate is the claim's OWN horizon, because `check_by` — the
    # falsifier deadline the claim IS — is resolved there. Legacy (unitless)
    # claims are untouched: they have no resolved window by construction.
    unit = claim.get("horizon_unit")
    if unit in HORIZON_UNITS:
        market, market_reason = resolve_claim_market(claim)
        if market is None:
            # HEAD (bucketable) then detail. The head inherits the market
            # resolver's own bounded reason head; the prose — which names the
            # offending leg — stays behind the separator.
            return False, (
                f"{REJECT_CLOCK_UNRESOLVABLE}:{clock_reason_head(market_reason)}"
                f"{CLOCK_REASON_SEP}cannot name the market this claim is priced "
                f"in ({market_reason}); refusing rather than resolving the exit "
                f"on another exchange's calendar")
        anchor = _entry_anchor(asof, tq)
        if resolve_horizon_window(anchor, horizon_d, unit, market) is None:
            supported_from, supported_through = CLOCK_MARKET_SUPPORT[market]
            return False, (
                f"{REJECT_CLOCK_UNRESOLVABLE}:window_unresolvable:{market}"
                f"{CLOCK_REASON_SEP}cannot resolve a window for "
                f"horizon_d={horizon_d} {unit} on the {market} calendar from "
                f"anchor {anchor} (supported {supported_from}"
                f"{'..' + supported_through.isoformat() if supported_through else '+'})"
                f"; a claim with no resolvable exit has no falsifier deadline "
                f"and could never grade or close")

    return True, ""


# W0 Stage B-e (§3.4): the US regime_vector stamp keys carried on every claim row.
# qledger is a US-lane desk/family ledger → US vector is the PRIMARY stamp
# (same convention as track_record #1139 and grade_us_board #1142).
_REGIME_STAMP_KEYS = (
    "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
    "risk_radar_state", "regime_vector_degraded", "vector_asof",
    "staleness_hours",
)


@lru_cache(maxsize=512)
def _regime_stamp_cached(asof: str) -> tuple:
    null = {k: None for k in _REGIME_STAMP_KEYS}
    if not asof:
        return tuple(null.items())
    try:
        from engine.regime_vector import get_vector_for_date  # noqa: PLC0415
        raw = get_vector_for_date(asof)
        out = {k: raw.get(k) for k in _REGIME_STAMP_KEYS}
        return tuple(out.items())
    except Exception as exc:  # noqa: BLE001
        log.debug("regime stamp lookup failed for %s: %s", asof, exc)
        return tuple(null.items())


def _regime_stamp_for_asof(asof: str) -> dict:
    """PIT US regime_vector stamp for a claim's asof date (§3.4).

    Reads ONLY the persisted daily vector (data/regime/regime_vector.parquet,
    last committed row with date ≤ asof) — never recomputes from latest-state
    sources. All-None stamp when the vector is absent or covers no such date.
    Cached per asof-date string: a 2,800-claim batch on one asof costs one
    parquet read, not 2,800.
    """
    return dict(_regime_stamp_cached(asof))


def _prepare_claim(claim: dict) -> dict:
    """Validate + stamp ONE claim into its stored form (shared by register()
    and register_batch(); extracted so batch registration is semantically
    identical to N single calls)."""
    ok, reason = _validate_claim(claim)

    scope = claim.get("scope") if isinstance(claim.get("scope"), dict) else {}
    horizon_d = 0
    try:
        horizon_d = int(claim.get("horizon_d"))
    except Exception:  # noqa: BLE001
        horizon_d = 0

    cid = claim.get("claim_id") or _claim_id(
        str(claim.get("desk") or ""),
        str(claim.get("asof") or ""),
        str(scope.get("key") or ""),
        horizon_d,
        claim.get("direction") if claim.get("direction") in DIRECTIONS else 0,
        salt=str(claim.get("salt") or ""),
    )

    stored = dict(claim)
    stored["claim_id"] = cid
    stored["timestamp"] = _now_iso()
    stored["status"] = STATUS_OPEN if ok else STATUS_REJECTED
    if not ok:
        stored["reject_reason"] = reason
    stored.setdefault("is_placebo", bool(claim.get("is_placebo", False)))
    # normalise the two grading legs so the grader never guesses
    stored.setdefault("bench", default_bench_for(scope.get("type"), scope.get("key")))
    stored.setdefault("control", None)
    stored.pop("salt", None)

    # W0 Stage B-e (§3.4): US regime_vector PIT stamp at registration time.
    if stored.get("vector_asof") is None:
        stamp = _regime_stamp_for_asof(str(claim.get("asof") or ""))
        for k, v in stamp.items():
            if stored.get(k) is None:
                stored[k] = v
    # Schema consistency across the five Stage-B ledgers. Nothing in
    # data/species/registry.json binds ledger="qledger" (qualitative desk
    # ledger, desk/family granularity) → both are null today by design.
    stored.setdefault("species_id", None)
    stored.setdefault("archetype", None)
    return stored


def _start_control_clocks_for(new_rows: Iterable[dict],
                              root: Path | str | None = None,
                              today: date | None = None) -> None:
    """P0d C3.1 — THE REGISTRAR HOOK. Start a required family's matched-control
    evidence clock at the first claim that is cohort-eligible AND control-carrying.

    Placed in the REGISTRAR, not in any producer, for one reason: a producer-side
    clock can be bypassed by wiring a second producer, and the whole contract
    rests on the clock being unbypassable. It runs over the NEWLY APPENDED rows
    only — never the whole store — so the cost is O(batch), not O(ledger).

    Every guard here is also a GATE-side cohort condition (C3.2), so the clock
    can never start on a claim the gate would refuse to count: family policy is
    `matched_control_required`, the row is live/open, directional, carries an
    explicit horizon unit and a VALID control leg (C2.2), and is prospective at
    registration. `benchmark_only` and `not_applicable` families never start a
    clock, whatever their rows carry (C1.4).

    NEVER RAISES INTO REGISTRATION. A ledger write that a clock bookkeeping
    failure could abort would be a worse defect than the one this closes."""
    try:
        ref = today or date.today()
        git_sha = os.environ.get("GITHUB_SHA") or None
        started: dict[str, bool] = {}
        for stored in new_rows:
            if not isinstance(stored, dict):
                continue
            if stored.get("status") != STATUS_OPEN or stored.get("is_placebo"):
                continue
            if stored.get("direction") not in (1, -1):
                continue
            fam = _family_key(stored, "family")
            if not fam:
                continue
            policy, _classified = family_control_policy(fam)
            if policy != CONTROL_POLICY_REQUIRED:
                continue
            if not control_leg_is_valid(stored):
                continue
            if claim_horizon_unit(stored) is None:
                continue
            if not _cohort_prospective(stored, ref):
                continue
            if fam not in started:          # ONE store read per family per batch
                started[fam] = read_control_clock_start(fam, root) is not None
            if started[fam]:
                continue
            rec = record_control_clock_start(
                fam, horizon_d=stored.get("horizon_d"),
                horizon_unit=stored.get("horizon_unit"),
                control=stored.get("control"), git_sha=git_sha, root=root)
            started[fam] = True
            log.info("control evidence clock STARTED for claim_family=%s at %s "
                     "(control=%s, horizon_d=%s %s)", fam,
                     rec.get("first_controlled_prospective_registration_utc"),
                     rec.get("control"), rec.get("declared_horizon_d"),
                     rec.get("horizon_unit"))
    except Exception as exc:  # noqa: BLE001 — registration must never fail here
        log.error("control evidence clock hook failed (registration unaffected): %s",
                  exc)


def register(claim: dict, root: Path | str | None = None,
             *, dedupe: bool = True) -> dict:
    """Register ONE claim. Validates against the schema, stamps `claim_id`,
    `timestamp`, and `status`, then appends to data/qledger/claims.jsonl.

    Returns the stored claim dict (with `status` in {open, rejected}). Rejected
    claims ARE persisted (audit trail for the D4 dark-fraction report) but never
    graded. Registration is idempotent by claim_id when `dedupe=True`.

    The `is_placebo` slot (D3) rides through untouched — B3's sampler registers
    placebo claims via this same call.

    COST NOTE (W0 Stage B-e): the dedupe scan re-reads the whole claims file —
    O(file) PER CALL. Loop-callers must use register_batch() (one read, one
    write for the whole batch); at ~2,800 calls/day the loop pattern was
    quadratic in ledger size.
    """
    root = _root(root)
    stored = _prepare_claim(claim)
    cid = stored["claim_id"]

    p = root.joinpath(*_CLAIMS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)

    if dedupe:
        for existing in load_claims(root):
            if existing.get("claim_id") == cid:
                return existing  # idempotent — adapters re-run freely

    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(stored, ensure_ascii=False, default=_json_default) + "\n")
    # P0d C3.1: the control evidence clock starts HERE, on the newly stored row
    # only — a dedupe hit above returns before this, so re-registering a claim can
    # never restart or re-stamp a clock.
    _start_control_clocks_for([stored], root)
    return stored


def register_batch(claims: Iterable[dict], root: Path | str | None = None,
                   *, dedupe: bool = True) -> list[dict]:
    """Register MANY claims with ONE store read and ONE append write
    (§5.1 sub-task 3 / §5.2 — required before any volume increase).

    Semantically identical to calling register() once per claim, including
    idempotent dedupe by claim_id (keep-FIRST: the store's existing row wins;
    within the batch, the first occurrence of a claim_id wins and later
    duplicates return that stored row).

    Per-claim error isolation: a claim whose preparation raises yields
    {"status": "error", "error": "..."} in its result slot; the rest of the
    batch still registers (a batch with one invalid claim never loses the
    valid ones — schema-invalid claims don't raise, they persist as
    status="rejected" exactly as register() does).

    Returns one stored dict per input claim, in input order.
    """
    root = _root(root)
    p = root.joinpath(*_CLAIMS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)

    existing_by_id: dict[str, dict] = {}
    if dedupe:
        for c in load_claims(root):          # ONE read for the whole batch
            existing_by_id.setdefault(str(c.get("claim_id")), c)

    results: list[dict] = []
    new_rows: list[dict] = []
    for claim in claims:
        try:
            stored = _prepare_claim(claim)
        except Exception as exc:  # noqa: BLE001 — isolate, never sink the batch
            log.warning("register_batch: claim preparation failed: %s", exc)
            results.append({"status": "error", "error": str(exc)})
            continue
        cid = stored["claim_id"]
        if dedupe and cid in existing_by_id:
            results.append(existing_by_id[cid])
            continue
        new_rows.append(stored)
        if dedupe:
            existing_by_id[cid] = stored
        results.append(stored)

    if new_rows:
        with p.open("a", encoding="utf-8") as fh:  # ONE write for the batch
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
        # P0d C3.1: NEW rows only. A batch that deduped entirely against the
        # store appends nothing and starts nothing.
        _start_control_clocks_for(new_rows, root)
    return results


def backfill_regime_stamps(root: Path | str | None = None) -> dict:
    """§3.4 backfill: fill missing regime stamps on existing claim rows ONLY
    from the persisted daily vector for dates it covers (PIT-safe by
    construction) — never reconstructed from latest-state sources.

    Fill-null-only (keep-FIRST): an existing non-null value is never altered.
    Atomic rewrite, and only when at least one row gained a stamp. Returns
    {n_claims, n_backfilled, n_unstamped, n_precoverage} — the nightly runner
    prints the residual unstamped count (§3.4 requires it visible).

    R-CI3 provenance law: every backfilled row receives
      regime_stamp_basis='recomputed_history'
    This MUST NOT be overwritten to 'pit_live' by engine/neuralweb/query.py (the
    engine/neuralweb/query.py:1094-1102 clobber guard checks _no_basis = basis is None, so
    pre-existing 'recomputed_history' values survive unchanged).
    Claims whose asof predates regime_vector.parquet coverage stay
    vector_asof=None and are counted in n_precoverage.
    """
    root = _root(root)
    p = root.joinpath(*_CLAIMS_FILE)
    claims = _read_jsonl(p)
    if not claims:
        return {"n_claims": 0, "n_backfilled": 0, "n_unstamped": 0, "n_precoverage": 0}

    # Guard: A-share and HK symbols must not receive US regime_vector rich stamps.
    _SKIP_SUFFIXES = (".SS", ".SZ", ".HK")
    n_skipped = 0
    n_precoverage = 0

    n_backfilled = 0
    for c in claims:
        if c.get("vector_asof") is None:
            scope_key = str((c.get("scope") or {}).get("key") or "")
            if any(scope_key.endswith(sfx) for sfx in _SKIP_SUFFIXES):
                n_skipped += 1
                continue
            stamp = _regime_stamp_for_asof(str(c.get("asof") or ""))
            if stamp.get("vector_asof") is not None:
                for k, v in stamp.items():
                    if c.get(k) is None:
                        c[k] = v
                # R-CI3: mark as recomputed from history, never pit_live.
                # keep-FIRST applies only to rows that already had vector_asof
                # (genuinely PIT-stamped) — those rows are not reached here
                # because the outer `if c.get("vector_asof") is None` gate
                # excludes them.  Any basis label on a vector_asof=None row is
                # a lying label: values are demonstrably being recomputed now.
                # Always stamp 'recomputed_history'.
                c["regime_stamp_basis"] = "recomputed_history"
                n_backfilled += 1
            else:
                # asof predates regime_vector.parquet coverage — stays null
                n_precoverage += 1

    if n_skipped:
        log.info("backfill_regime_stamps: skipped %d A-share/HK claim(s) (.SS/.SZ/.HK)", n_skipped)
    if n_precoverage:
        log.info(
            "backfill_regime_stamps: %d claim(s) predate regime_vector coverage — vector_asof stays null",
            n_precoverage,
        )

    n_unstamped = sum(1 for c in claims if c.get("vector_asof") is None)
    if n_backfilled:
        tmp = p.with_name(p.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for c in claims:
                fh.write(json.dumps(c, ensure_ascii=False, default=_json_default) + "\n")
        tmp.replace(p)
    return {
        "n_claims": len(claims),
        "n_backfilled": n_backfilled,
        "n_unstamped": n_unstamped,
        "n_precoverage": n_precoverage,
    }


def make_claim(*, desk: str, asof: str, scope_type: str, scope_key: str,
               direction: int, horizon_d: int,
               timestamp_quality: str,
               horizon_unit: str | None = None,
               subject_level: float | None = None,
               bench: str | None = None,
               bench_level: float | None = None,
               control: str | None = None,
               falsifier: Any = None,
               check_by: str | None = None,
               sector: str | None = None,
               is_placebo: bool = False,
               claim_family: str | None = None,
               extra: dict | None = None) -> dict:
    """Adapter helper — build a well-formed claim dict from the fields a W1
    builder already has, so desks map existing ledger rows into claims WITHOUT
    copying validation/scoring logic (§2.2 "adapter helpers").

    * `bench` defaults to the scope's default (SPY for non-macro). Macro callers
      MUST pass a named observable or register() rejects the claim (D4).
    * `control` defaults to the sector-matched ETF derived from `sector`.
    * `entry_levels` is assembled as {subject, bench} — the altdata PIT model,
      generalised (subject key == scope_key).
    * `horizon_unit` (P0a) DECLARES what the `horizon_d` number means:
      'trading_days' or 'calendar_days'. The number itself is never converted.
      Omitting it registers a LEGACY-clock claim graded by the pre-P0a calendar
      approximation — supported so unmigrated callers keep their exact behaviour,
      never as a silent declaration of either unit.
    * `check_by` is the claim's OWN resolved exit boundary, from the SAME
      `resolve_horizon_window` (and the same anchor, unit and market) the grader
      uses — so the deadline a human reads and the arithmetic the grade is
      measured with can no longer diverge as implementations. Legacy (unitless)
      claims keep the pre-P0a `asof + horizon_d business days` default untouched.

      EXACTLY WHAT THAT GUARANTEES, AND WHERE IT STOPS. `check_by` is resolved at
      the claim's OWN `horizon_d`; the grader grades at
      `in_scope_horizons(horizon_d)`. Those are the SAME date — check_by IS a
      graded exit, equal to some row's `clock_exit_date` — whenever
      `check_by_is_a_graded_exit(horizon_d)` holds, which as of P0b is every
      horizon_d at or below the ladder's ceiling (`GRADE_HORIZONS[-1]`, 63
      today): `in_scope_horizons` now always includes the claim's own ruler
      there, on-rung or off. It is NOT the same date only ABOVE that ceiling: a
      126-trading-day policy claim still grades at 5, 21 and 63 sessions while
      its check_by sits at session 126. The deadline is still a real, correctly
      resolved exchange exit under the declared unit — it is simply the
      claim's own horizon rather than a graded rung. Closing that remaining gap
      would mean extending `GRADE_HORIZONS` itself past 63d in the live nightly
      grader, which ruling LH-U6 (`config/ruling_graph.yml`) forbids; the
      predicate is exported so the scope is checkable instead of merely
      stated.

      A CALLER-SUPPLIED `check_by` DOES NOT OVERRIDE THE CLOCK. On a claim that
      DECLARES a unit, the resolver's exit always wins and the supplied value is
      preserved for audit as `check_by_source` (only when it disagrees). This is
      the difference between a contract and a convention: the two highest-volume
      US lanes — `scripts/backfill_qledger_us.py` `backfill_altdata` and
      `backfill_policy` — both pass a `check_by` read straight off their source
      thesis, and those values came from `ai_desk._check_by`, i.e. from
      `asof + BusinessDay(horizon)`: the very arithmetic P0a exists to replace,
      holiday-blind and anchored pre-embargo. Honouring them would have left the
      headline guarantee ("check_by IS the exit the grader resolves") with a
      bypass on exactly the lanes that carry the most claims. The alternative —
      validate and REFUSE on disagreement — was rejected: it would reject those
      lanes' entire output on day one, and a claim whose deadline is merely
      restated more precisely is not an invalid claim. Nothing is lost or
      hidden: the source's stated deadline stays on the row under
      `check_by_source`, so every overridden claim is countable in the store.
      Legacy (unitless) claims are untouched — a supplied value passes through
      exactly as before.
    """
    bench = bench or default_bench_for(scope_type, scope_key)
    if control is None:
        control = control_for_sector(sector)

    entry_levels: dict[str, float] = {}
    if subject_level is not None:
        entry_levels["subject"] = round(float(subject_level), 6)
    if bench_level is not None:
        entry_levels["bench"] = round(float(bench_level), 6)

    check_by_source: str | None = None
    clock_market: str | None = None
    if horizon_unit in HORIZON_UNITS:
        # ONE resolver, ONE anchor, ONE market, NO bypass: check_by is resolved by
        # the same call the grader makes, whether or not the caller supplied one.
        # The anchor is the post-embargo entry date, the same one grade_claim()
        # passes in — a DISCLOSURE_DATE claim shifts +1bd on BOTH sides or on
        # neither — and the market is the claim's own (`resolve_claim_market`),
        # so a CN claim's deadline is an A-share session, not an NYSE one.
        clock_market, _market_reason = resolve_claim_market({
            "scope": {"type": scope_type, "key": scope_key},
            "bench": bench,
            "control": control,
            # round 5: provenance is derived from THESE two fields
            # (`_provenance_market`) — they must be present here, at the point
            # of construction, not only on the assembled claim dict below, or
            # a claim whose subject leg carries no exchange suffix (a bare
            # A-share code, a symbolic macro key) can never reach its desk's
            # own known market.
            "desk": desk,
            "claim_family": claim_family or desk,
        })
        win = (resolve_horizon_window(
                   _entry_anchor(asof, timestamp_quality), horizon_d,
                   horizon_unit, clock_market)
               if clock_market is not None else None)
        resolved = win.exit_date.isoformat() if win is not None else None
        if check_by is not None and check_by != resolved:
            check_by_source = str(check_by)   # audit: what the source asked for
        check_by = resolved
    elif check_by is None:
        # LEGACY (unitless) claim: pre-P0a default, byte for byte.
        try:
            check_by = (pd.Timestamp(asof) +
                        pd.offsets.BusinessDay(int(horizon_d))).date().isoformat()
        except Exception:  # noqa: BLE001
            check_by = None

    claim: dict[str, Any] = {
        "desk": desk,
        "asof": asof,
        "scope": {"type": scope_type, "key": scope_key},
        "direction": direction,
        "horizon_d": int(horizon_d),
        "entry_levels": entry_levels,
        "bench": bench,
        "control": control,
        "falsifier": falsifier,
        "check_by": check_by,
        "timestamp_quality": timestamp_quality,
        "is_placebo": bool(is_placebo),
        "claim_family": claim_family or desk,
    }
    if horizon_unit is not None:
        # Stamped ONLY when declared: an absent key is the LEGACY basis, and a
        # written-in null would make every unmigrated caller look like it had
        # declared something. Deliberately NOT part of `_claim_id` — a claim
        # already registered under the legacy clock must keep its id (and be
        # deduped away on re-registration), never fork into a second row.
        claim["horizon_unit"] = horizon_unit
    if clock_market is not None:
        # The exchange calendar this claim's clock resolves on. Stamped so a
        # reader of the store can see WHICH calendar produced check_by without
        # re-deriving it from the ticker suffixes, and so a later change to the
        # suffix table is visible as a change rather than a silent re-reading.
        claim["clock_market"] = clock_market
    if check_by_source is not None:
        # The deadline the SOURCE stated, kept only when the clock disagreed with
        # it. Never read by the grader — it exists so an override is auditable
        # rather than invisible.
        claim["check_by_source"] = check_by_source
    if sector:
        claim["sector"] = sector
    if extra:
        claim.update(extra)
    return claim


# --------------------------------------------------------------------------- #
# store readers
# --------------------------------------------------------------------------- #
def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def load_claims(root: Path | str | None = None) -> list[dict]:
    return _read_jsonl(_root(root).joinpath(*_CLAIMS_FILE))


def load_grades(root: Path | str | None = None) -> list[dict]:
    return _read_jsonl(_root(root).joinpath(*_GRADES_FILE))


def count_unresolvable_clock_claims(root: Path | str | None = None,
                                    claims: Iterable[dict] | None = None) -> dict:
    """How many claims the horizon clock REFUSED, and why — the countable half of
    the no-zombie rule.

    Before this contract an unresolvable declared-clock claim registered
    status=open with check_by=None: it could never grade, never close, and
    appeared in no count at all. `_validate_claim` now refuses it, so it is a
    `status='rejected'` row carrying a `REJECT_CLOCK_UNRESOLVABLE` reason, and
    this function is what turns that store state into a number the nightly can
    print. Returns {n, by_reason, by_family} — never a bare total, because "12
    refused" and "12 refused, all of them Beijing tickers" are different facts.

    `by_reason` is keyed on `clock_reason_head` — the bounded head of the reason
    (`clock_unresolvable:unsupported_exchange_suffix:.L`,
    `clock_unresolvable:window_unresolvable:CN`) — never the prose tail. The tail
    carries the offending ticker AND the anchor date, and the previous split
    ("everything before the first '(' or ' — '") kept the anchor date for the
    out-of-range class, so that class got one key per claim. A histogram with as
    many rows as refusals is not a histogram.
    """
    rows = list(claims) if claims is not None else load_claims(root)
    by_reason: dict[str, int] = {}
    by_family: dict[str, int] = {}
    n = 0
    for c in rows:
        if c.get("status") != STATUS_REJECTED:
            continue
        reason = str(c.get("reject_reason") or "")
        if not reason.startswith(REJECT_CLOCK_UNRESOLVABLE):
            continue
        n += 1
        # Bucket on the machine-readable head of the reason, not the prose tail
        # (which carries the offending ticker and the anchor date).
        head = clock_reason_head(reason)
        by_reason[head] = by_reason.get(head, 0) + 1
        fam = str(c.get("claim_family") or c.get("desk") or "unknown")
        by_family[fam] = by_family.get(fam, 0) + 1
    return {"n": n,
            "by_reason": dict(sorted(by_reason.items())),
            "by_family": dict(sorted(by_family.items()))}


# --------------------------------------------------------------------------- #
# forward relative return — grading fill semantics (W0 Stage B-e)
# --------------------------------------------------------------------------- #
# THE STAMPED DISCONTINUITY (§5.1 sub-task 3): before Stage B-e, _fwd_ret used
# asof-entry semantics (entry = close ON/BEFORE the claim's asof — the same-bar
# convention the measurement law bans: it flatters mean-reversion claims by
# filling at the trough close). From Stage B-e on, entry = the first close
# STRICTLY AFTER the entry date (the one-grader next-bar convention; the exit
# window is anchored at the fill so the horizon length is preserved).
#
# The convention change is a GRADE-HISTORY DISCONTINUITY and is stamped, never
# silent: every new grade row carries fill_convention="next_bar" +
# entry_fill_date; rows already in grades.jsonl lack the field and are read as
# "asof_legacy". Legacy graded values are NEVER rewritten (keep-FIRST).
# compute_track_record() reports row counts per convention.
FILL_NEXT_BAR = "next_bar"
FILL_ASOF_LEGACY = "asof_legacy"


def _fill_entry(ticker: str, root: Path,
                entry_date: str) -> tuple[float | None, pd.Timestamp | None]:
    """Next-bar fill: (entry_price, fill_ts) = first close STRICTLY AFTER
    entry_date. (None, None) when the series is absent or has no later bar."""
    try:
        s = _aidesk._close_series(ticker, root)
        if s is None or s.empty:
            return None, None
        fwd = s[s.index > pd.Timestamp(entry_date)]
        if not len(fwd):
            return None, None
        return float(fwd.iloc[0]), fwd.index[0]
    except Exception as e:  # noqa: BLE001
        log.debug("_fill_entry(%s,%s): %s", ticker, entry_date, e)
        return None, None


def _fwd_ret(ticker: str, root: Path, start_date: str, horizon_d: int,
             *, fill_convention: str = FILL_NEXT_BAR) -> float | None:
    """Total return of `ticker` over `horizon_d` calendar days.

    next_bar (default, Stage B-e): entry = first close STRICTLY AFTER
    start_date; exit = close ON/BEFORE fill+horizon_d, and only when the
    series actually covers the exit day (never grade a shortened window).

    asof_legacy: the pre-Stage-B-e math (entry = close ON/BEFORE start_date;
    exit = close ON/BEFORE start+horizon_d) — kept ONLY so tests and audits
    can reproduce how legacy grade rows were computed. No production path
    grades with it anymore.

    None when price unavailable. Returns the RAW return (excess is computed
    against bench/control at the grader level so both legs share one entry).
    """
    try:
        if fill_convention == FILL_ASOF_LEGACY:
            end_ts = (pd.Timestamp(start_date) +
                      pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
            e0 = _level_asof(ticker, root, start_date)
            e1 = _close_at(ticker, root, end_ts)
            if None in (e0, e1) or not e0:
                return None
            return round(e1 / e0 - 1.0, 6)

        e0, fill_ts = _fill_entry(ticker, root, start_date)
        if e0 is None or not e0 or fill_ts is None:
            return None
        s = _aidesk._close_series(ticker, root)
        end_ts = fill_ts + pd.Timedelta(days=horizon_d)
        if s.index.max() < end_ts:
            return None            # exit day not covered yet — not matured
        w = s[s.index <= end_ts]
        if not len(w):
            return None
        e1 = float(w.iloc[-1])
        return round(e1 / e0 - 1.0, 6)
    except Exception as e:  # noqa: BLE001
        log.debug("_fwd_ret(%s,%s,%s): %s", ticker, start_date, horizon_d, e)
        return None


def _leg_ret_in_window(ticker: str, root: Path, window: HorizonWindow) -> float | None:
    """Total return of ONE leg over the SHARED resolved window (contract rule 5).

    Entry is the close ON the shared fill SESSION — which is by construction
    strictly after the entry anchor, so the next-bar law is intact — and the exit
    is the close on the window's `coverage_date`, the last session the declared
    horizon contains. The window dates come from the resolver, never from this
    ticker's own index, so subject, bench and control are measured over the same
    declared horizon.

    RULE 5 IS ENFORCED HERE, NOT DESCRIBED. The two endpoint bars must be the
    window's OWN endpoint sessions:

      * the first bar in [fill, exit] must BE `fill_date`, and
      * the last bar in [fill, exit] must BE `coverage_date`.

    An endpoint the store does not hold — a halt, an IPO that starts mid-window,
    a collection hole, a ticker delisted before the exit — used to be silently
    absorbed: the slice simply started later or ended earlier and a SHORTER
    window was graded under the declared horizon's label, differently for each
    leg. That is the exact failure the docstring promised against while maturity
    was checked somewhere else entirely (`_matured_window` asks `_covers`, which
    only tests the series MAX, so a ticker whose store has an interior hole or a
    late start passes maturity and then grades short). Both endpoints are now
    asserted against the shared window, so a shortened window is REFUSED (None),
    never graded. Interior gaps do not matter: a two-endpoint total return reads
    only its endpoints (`lib.nyse_calendar` § GAP DISCIPLINE).

    NOT SILENT EITHER: a refused leg makes `grade_claim` return no row for that
    horizon, and `scripts/grade_qledger.py` counts exactly that outcome into
    `n_blocked_by_coverage` in `data/qledger/run_status.json` — so if this rule
    ever refuses at scale (a price store with widespread holes), the nightly
    summary shows it as a coverage number rather than as quietly missing grades.
    The per-leg reason is at DEBUG.

    None (never a shortened window silently graded) when the series is absent,
    does not yet cover `coverage_date`, or does not hold both endpoint bars."""
    try:
        s = _aidesk._close_series(ticker, root)
        if s is None or s.empty:
            return None
        cover_ts = pd.Timestamp(window.coverage_date)
        if s.index.max() < cover_ts:
            return None                       # not matured for this leg
        fill_ts = pd.Timestamp(window.fill_date)
        exit_ts = pd.Timestamp(window.exit_date)
        w = s[(s.index >= fill_ts) & (s.index <= exit_ts)]
        if len(w) < 2:
            return None
        # RULE 5: the graded window's endpoints, or nothing.
        if pd.Timestamp(w.index[0]).normalize() != fill_ts.normalize():
            log.debug("_leg_ret_in_window(%s): entry bar %s != shared fill %s — "
                      "refusing a shortened window", ticker, w.index[0], fill_ts)
            return None
        if pd.Timestamp(w.index[-1]).normalize() != cover_ts.normalize():
            log.debug("_leg_ret_in_window(%s): exit bar %s != window close %s — "
                      "refusing a shortened window", ticker, w.index[-1], cover_ts)
            return None
        e0 = float(w.iloc[0])
        if not e0:
            return None
        return round(float(w.iloc[-1]) / e0 - 1.0, 6)
    except Exception as e:  # noqa: BLE001
        log.debug("_leg_ret_in_window(%s,%s): %s", ticker, window, e)
        return None


def _matured_window(root: Path, window: HorizonWindow, today: date,
                    tickers: Iterable[str]) -> bool:
    """Maturity under the explicit clock — same resolver, no second arithmetic.

    Matured when the resolved `coverage_date` has passed AND every leg's price
    cache covers it. (`_matured` below is the LEGACY-clock twin and is left
    exactly as it was: legacy rows must stay reproducible.)

    NECESSARY, NOT SUFFICIENT: `_covers` tests only that a leg's series REACHES
    `coverage_date`, so a leg that reaches it while missing the window's own
    endpoint bars still passes here. The shortened-window refusal therefore lives
    in `_leg_ret_in_window`, which asserts both endpoints per leg — this function
    decides only "is it time yet", never "is the window whole"."""
    try:
        if today < window.coverage_date:
            return False
        end_ts = window.coverage_date.isoformat()
        return all(_covers(t, root, end_ts) for t in tickers if t)
    except Exception:  # noqa: BLE001
        return False


def _matured(root: Path, start_date: str, horizon_d: int,
             today: date, tickers: Iterable[str]) -> bool:
    """A horizon is matured when it is old enough AND every leg's price cache
    covers the exit day (radar_ic._is_matured, generalised to N legs).

    LEGACY CLOCK ONLY (calendar-day approximation of an undeclared unit).
    Explicit-unit claims resolve maturity through `_matured_window`."""
    try:
        snap = pd.Timestamp(start_date)
        if (pd.Timestamp(today) - snap).days < horizon_d:
            return False
        end_ts = (snap + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        return all(_covers(t, root, end_ts) for t in tickers if t)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# EMBARGO
# --------------------------------------------------------------------------- #
def _embargo_ok(claim: dict) -> tuple[bool, bool]:
    """(gradeable, embargo_applied) per timestamp_quality ([P2]).

    * CRAWL_BOUNDED   -> gradeable, no embargo.
    * PUBLISHER_STATED -> gradeable, embargo applied (+15min at entry).
    * DISCLOSURE_DATE  -> gradeable, embargo applied (+1bd at entry).
    * EVENT_DATE       -> NOT gradeable as an entry anchor (never).
    * SNAPSHOT_DATE    -> display-only, NOT graded.
    * CORRUPTED        -> blocked (never reaches here — rejected at register()).

    The actual +15min / +1bd shift is on the ENTRY ANCHOR; since qledger's entry
    is a daily close (the finest resolution the parquet layer offers), the
    +15min case cannot move the close and is recorded via `embargo_applied` for
    audit. The +1bd case shifts the effective entry date used by the grader.
    """
    tq = claim.get("timestamp_quality")
    spec = TIMESTAMP_QUALITY.get(tq)
    if spec is None:
        return False, False
    minutes, gradeable, _ = spec
    return bool(gradeable), bool(minutes > 0)


def _entry_anchor(asof: str, timestamp_quality: str | None) -> str:
    """The effective entry date after embargo, from the two fields that decide it.

    DISCLOSURE_DATE shifts +1bd; all others anchor at asof (the +15min PUBLISHER
    case cannot move a daily close). Extracted so `make_claim`'s `check_by` and
    `grade_claim`'s window resolve from the SAME anchor — a check_by computed off
    the raw asof while the grader anchored one business day later would reopen
    the very divergence this contract closes."""
    asof = str(asof)
    if timestamp_quality == "DISCLOSURE_DATE":
        try:
            return (pd.Timestamp(asof) +
                    pd.offsets.BusinessDay(1)).date().isoformat()
        except Exception:  # noqa: BLE001
            return asof
    return asof


def _entry_date(claim: dict) -> str:
    """The effective entry date after embargo for a CLAIM (see `_entry_anchor`)."""
    return _entry_anchor(str(claim.get("asof")), claim.get("timestamp_quality"))


# --------------------------------------------------------------------------- #
# GRADING
# --------------------------------------------------------------------------- #
def grade_claim(claim: dict, root: Path | str | None = None,
                today: date | str | None = None) -> list[dict]:
    """Grade ONE open claim at every in-scope, matured horizon. Returns a list of
    grade rows (may be empty when nothing has matured). Pure/read-only — the
    nightly runner is what appends these; this is the contract the runner calls.

    A grade row (grades.jsonl schema):
      {claim_id, horizon_d, graded_at, subject_ret, bench_ret, control_ret,
       excess, hit, embargo_applied, fill_convention, entry_fill_date}

    W0 Stage B-e: rows grade under the next-bar fill convention and say so
    (fill_convention="next_bar" + the subject leg's entry_fill_date). Rows
    written before Stage B-e lack the field and are read as "asof_legacy";
    their graded values are never rewritten (keep-FIRST — the discontinuity
    is stamped, not silent).

    P0a (the horizon clock): a claim that DECLARES a `horizon_unit` grades on
    ONE window resolved by `claim_window` — the declared unit, on the calendar of
    the market the claim is PRICED in — shared by subject, bench and control, and
    its rows carry horizon_unit + clock_version + clock_exit_date + clock_market.
    ALL THREE legs must measure over that window or the row is refused: a control
    that cannot be priced over it is a leg on a different window, not a null.
    A claim whose market cannot be determined grades NOTHING (it is refused at
    registration too). A claim with no declared unit keeps the pre-P0a calendar
    arithmetic byte-for-byte and its rows carry NO clock stamp — read as
    ``CLOCK_LEGACY``. Same stamped-discontinuity pattern, same law: legacy grades
    are never rewritten and the two bases are never pooled (`require_single_clock`).

    * `excess` = subject_ret - bench_ret (the primary leg).
    * `control_ret` = matched sector-control return (null when no control), for
      the second leg the promotion gate reads (excess-vs-control).
    * `hit` uses the claim direction: +1 -> excess>0; -1 -> excess<0; 0
      (salience-only) -> hit is null (salience claims grade magnitude via the
      placebo tape, not direction — §2.3/D3).
    """
    root = _root(root)
    today_dt = (today if isinstance(today, date)
                else pd.Timestamp(today).date() if today else date.today())

    gradeable, embargo_applied = _embargo_ok(claim)
    if not gradeable:
        return []

    scope = claim.get("scope") or {}
    subject = scope.get("key")
    bench = claim.get("bench") or _DEFAULT_BENCH
    control = claim.get("control")
    direction = claim.get("direction")
    start = _entry_date(claim)

    try:
        horizon_d = int(claim.get("horizon_d"))
    except Exception:  # noqa: BLE001
        return []

    unit = claim_horizon_unit(claim)

    rows: list[dict] = []
    for h in in_scope_horizons(horizon_d):
        legs = [subject, bench] + ([control] if control else [])

        if unit is None:
            # LEGACY CLOCK — the claim declared no unit, so it is graded by the
            # pre-P0a calendar approximation and stamped as such. Never migrated,
            # never re-labelled (§ legacy law).
            if not _matured(root, start, h, today_dt, legs):
                continue
            subj = _fwd_ret(subject, root, start, h)
            bench_ret = _fwd_ret(bench, root, start, h)
            if subj is None or bench_ret is None:
                continue
            ctrl = _fwd_ret(control, root, start, h) if control else None
            _, fill_ts = _fill_entry(subject, root, start)
            fill_date = str(fill_ts.date()) if fill_ts is not None else None
            clock_stamp: dict[str, Any] = {}
        else:
            # EXPLICIT CLOCK — ONE window resolved from the declared unit, on the
            # claim's OWN market's calendar, and SHARED by every leg (rules 3-5).
            window = claim_window(claim, h, entry_anchor=start)
            if window is None:
                continue
            if not _matured_window(root, window, today_dt, legs):
                continue
            subj = _leg_ret_in_window(subject, root, window)
            bench_ret = _leg_ret_in_window(bench, root, window)
            if subj is None or bench_ret is None:
                continue
            # RULE 5 APPLIES TO THE CONTROL LEG TOO. A control that fails the
            # endpoint assertion used to be absorbed as `ctrl = None`, which is
            # indistinguishable in the store from "this claim declared no
            # control" — so the §3 promotion gate, whose bar is excess-vs-CONTROL,
            # silently fell back to the primary hit on exactly the claims whose
            # control window was broken. That is a leg receiving a different
            # window in all but name. A declared control that cannot be measured
            # over the shared window now REFUSES the row, the same as subject and
            # bench, and `scripts/grade_qledger.py` counts it into
            # `n_blocked_by_coverage`.
            ctrl = None
            if control:
                ctrl = _leg_ret_in_window(control, root, window)
                if ctrl is None:
                    log.debug("grade_claim(%s h=%s): control leg %s refused the "
                              "shared window — no row (rule 5)",
                              claim.get("claim_id"), h, control)
                    continue
            fill_date = window.fill_date.isoformat()
            clock_stamp = {
                "horizon_unit": window.horizon_unit,
                "clock_version": window.clock_version,
                "clock_exit_date": window.exit_date.isoformat(),
                "clock_coverage_date": window.coverage_date.isoformat(),
                "clock_market": window.market,
            }

        excess = round(subj - bench_ret, 6)
        if direction == 1:
            hit: bool | None = excess > 0
        elif direction == -1:
            hit = excess < 0
        else:                       # salience-only: no directional hit
            hit = None
        rows.append({
            "claim_id": claim.get("claim_id"),
            "horizon_d": h,
            "graded_at": _now_iso(),
            "subject_ret": subj,
            "bench_ret": bench_ret,
            "control_ret": ctrl,
            "excess": excess,
            "hit": hit,
            "embargo_applied": embargo_applied,
            # W0 Stage B-e: the stamped fill convention (see module note)
            "fill_convention": FILL_NEXT_BAR,
            "entry_fill_date": fill_date,
            **clock_stamp,          # P0a: absent == the legacy clock basis
        })
    return rows


# --------------------------------------------------------------------------- #
# WILSON CI + track-record aggregation
# --------------------------------------------------------------------------- #
def wilson_ci_low(hits: int, n: int, z: float = 1.96) -> float | None:
    """Lower bound of the Wilson score interval for a binomial proportion.
    None when n == 0. The promotion gate (§3) reads this lower bound vs the coin-flip
    null, ``PROMOTION_MIN_CI_LOW`` = 0.5 — NOT vs 0.

    The return is a PROPORTION in [0, 1], never a signed edge. Comparing it to 0 was
    therefore vacuous: wilson_ci_low(1, 27) > 0, so any family with a single hit cleared
    the bar. It opened radar@5d on 2026-07-28 at a 51.0% hit rate whose CI [0.340, 0.693]
    brackets 0.5 outright, with mean excess NEGATIVE (-0.26%) — a live alert fired off a
    gate that could not fail (2026-08-03 experiments audit). The honest null for "does
    this call the direction better than a coin" is 0.5, so the lower bound must clear 0.5.

    Wilson is used (not normal-approx) because n is small and p can be near 0/1;
    the lower bound is the honest floor the gate requires to exceed.
    """
    if n <= 0:
        return None
    phat = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = phat + z2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)
    return round((centre - margin) / denom, 6)


def _date_cluster(asof: str) -> str:
    """The independent-date key ([P1]/§5 overlapping-observation illusion). One
    claim's asof date is one cluster; n_dates counts DISTINCT asof dates so
    overlapping/autocorrelated obs never inflate n. This is the honest n."""
    try:
        return pd.Timestamp(asof).date().isoformat()
    except Exception:  # noqa: BLE001
        return str(asof)


def derive_state(n_dates: int) -> str:
    """UNGRADED (n_dates==0) | ACCRUING (0<n_dates<25) | GRADED (n_dates>=25).
    The chip the UI reads (D10)."""
    if n_dates <= 0:
        return STATE_UNGRADED
    if n_dates < GRADED_MIN_DATES:
        return STATE_ACCRUING
    return STATE_GRADED


def _family_key(claim: dict, by: str) -> str | None:
    if by == "desk":
        return claim.get("desk")
    if by == "family":
        return claim.get("claim_family") or claim.get("desk")
    return None


# The two legal bases for an excess figure out of _aggregate. `pooled_signed` is
# the historical `excess_mean`; `magnitude_only` is the V1-legal replacement for a
# family that holds calls in both directions.
EXCESS_BASIS_POOLED = "pooled_signed"
EXCESS_BASIS_MAGNITUDE = "magnitude_only"


def _group_profiles(claims: list[dict], by: str) -> dict[str, FamilyProfile]:
    """FamilyProfile per _aggregate group key, keyed exactly as `_family_key`.

    `profile_families` keys on ``claim_family or desk`` — identical to
    ``_family_key(c, 'family')`` but NOT to the ``by='desk'`` grouping. Rather
    than re-deriving the profile (a second implementation of the invariant is how
    two copies drift), project each claim onto the group key and hand the
    projection to the contract's own builder, so direction coercion and the
    placebo exclusion stay owned by engine/qledger_validity.py.
    """
    projected = (
        {
            "claim_family": _family_key(c, by),
            "direction": c.get("direction"),
            "horizon_d": c.get("horizon_d"),
            "is_placebo": c.get("is_placebo"),
        }
        for c in claims
    )
    return profile_families(projected)


def _coerce_direction(raw: Any) -> int | None:
    """Coerce ONE stored direction through the CONTRACT's own parser.

    Stores hold both ``1`` and ``"1"``. Re-implementing that coercion here would
    let the per-direction split disagree with the V1 gate about what a direction
    IS, so the value is run through `profile_families` and read back out. Callers
    memoise: the corpus holds a handful of distinct raw direction values, so this
    is called ~3 times per aggregation, not once per row.
    """
    prof = profile_families([{"claim_family": "_", "direction": raw}]).get("_")
    if prof is None or len(prof.directions) != 1:
        return None
    return next(iter(prof.directions))


def _aggregate(claims: list[dict], grades: list[dict],
               by: str, horizon_d: int,
               clock_basis: str | None = None) -> dict[str, dict]:
    """Aggregate grade rows into per-group track-record stats at ONE horizon.
    `by` in {'desk','family'}. Groups exclude placebo claims from the headline
    hit-rate (placebo is the counterfactual, graded separately by B3).

    P0a: aggregation happens WITHIN one grading-clock basis. Pass `clock_basis`
    to select one (`grade_clock_basis` values); leave it None and a mixed input
    raises `HorizonClockMismatch` rather than pooling. The default is fail-closed
    on purpose — a caller that never heard of the clock cannot silently blend a
    legacy 21-calendar-day observation with a 21-session one.

    METRIC-VALIDITY GATE (V1 SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS). `grades.excess`
    is RAW subject-minus-control return and is NOT direction-signed — `hit` is what
    carries direction. A correct BEARISH call therefore contributes a NEGATIVE
    excess, so pooling signed excess over a family holding both directions measures
    the drift of the subject universe, not skill. This function is the single
    chokepoint feeding compute_track_record() (site/qledger/track_record.json) and
    scripts/grade_qledger.compute_promotion_readiness() (-> the admin Experiments
    tab), so the gate lives here: `excess_mean` is emitted ONLY when
    `engine.qledger_validity.may_pool_signed_excess` allows it. Mixed-direction
    groups get the legal replacements instead — `mean_abs_excess` (the magnitude
    form `_placebo_magnitude` already uses, which is also what the placebo duel
    compares against) and `excess_mean_by_direction` (the per-direction split).
    `excess_basis` names which reading is live so an emitter can label it honestly
    rather than render an ambiguous dash. hit_rate needs no gate: grade_claim()
    stores hit=None for direction==0, so a salience family resolves to None already.
    """
    cid_meta = {c["claim_id"]: c for c in claims if c.get("claim_id")}
    profiles = _group_profiles(claims, by)
    dir_cache: dict[Any, int | None] = {}

    at_h = [g for g in grades if int(g.get("horizon_d", -1)) == horizon_d]
    if clock_basis is None:
        require_single_clock(at_h, context=f"_aggregate(by={by!r}, h={horizon_d})")
    else:
        at_h = [g for g in at_h if grade_clock_basis(g) == clock_basis]

    # group -> {n_obs, hits, excess_sum, abs_excess_sum, n_abs, per-direction, date_set}
    acc: dict[str, dict] = {}
    for g in at_h:
        c = cid_meta.get(g.get("claim_id"))
        if c is None or c.get("is_placebo"):
            continue
        key = _family_key(c, by)
        if key is None:
            continue
        a = acc.setdefault(key, {"n_obs": 0, "hits": 0, "graded_hits": 0,
                                 "excess_sum": 0.0, "abs_excess_sum": 0.0,
                                 "n_abs": 0, "by_dir": {}, "dates": set()})
        a["n_obs"] += 1
        excess = g.get("excess")
        # Pooled sum keeps its historical `or 0.0` convention so a single-direction
        # family's excess_mean is bit-identical to the pre-gate value.
        a["excess_sum"] += float(excess or 0.0)
        if excess is not None:
            # Magnitude leg mirrors _placebo_magnitude: null excess is SKIPPED, not
            # counted as a zero move, so the two sides of the duel are comparable.
            a["abs_excess_sum"] += abs(float(excess))
            a["n_abs"] += 1
        raw_dir = c.get("direction")
        try:
            d = dir_cache[raw_dir]
        except (KeyError, TypeError):       # unseen value, or an unhashable one
            d = _coerce_direction(raw_dir)
            try:
                dir_cache[raw_dir] = d
            except TypeError:
                pass
        if d is not None:
            dacc = a["by_dir"].setdefault(d, {"n": 0, "sum": 0.0})
            dacc["n"] += 1
            dacc["sum"] += float(excess or 0.0)
        a["dates"].add(_date_cluster(c.get("asof")))
        hit = g.get("hit")
        if hit is not None:                 # directional claim contributes a hit
            a["graded_hits"] += 1
            if hit:
                a["hits"] += 1

    out: dict[str, dict] = {}
    for key, a in acc.items():
        n_obs = a["n_obs"]
        n_dates = len(a["dates"])
        gh = a["graded_hits"]
        hit_rate = round(a["hits"] / gh, 6) if gh else None
        # V1: absent a profile the group is UNKNOWN, so refuse the signed pool
        # (fail closed) rather than publish an uninterpretable number.
        prof = profiles.get(key)
        poolable = prof is not None and may_pool_signed_excess(prof)
        excess_mean = (round(a["excess_sum"] / n_obs, 6)
                       if (n_obs and poolable) else None)
        mean_abs_excess = (round(a["abs_excess_sum"] / a["n_abs"], 6)
                           if a["n_abs"] else None)
        # Cluster-honest Wilson CI: project the pooled hit rate onto the date-cluster n
        # so that n_dates (distinct asof clusters) — not the correlated n_obs — drives
        # the confidence interval.  This matches the altdata_brain.py article3 convention
        # (hits=round(hit_rate*n_dates), n=n_dates) and the ticker-cluster time-confound
        # law: overlapping observations across the same date clusters inflate n and make
        # the CI anti-conservative (see _date_cluster / §5 doctrine above).
        if gh and n_dates:
            cluster_hits = int(round((a["hits"] / gh) * n_dates))
            ci_low = wilson_ci_low(cluster_hits, n_dates)
        else:
            ci_low = None
        row = {
            "n_obs": n_obs,
            "n_dates": n_dates,          # the honest n
            "hit_rate": hit_rate,
            "excess_mean": excess_mean,
            "mean_abs_excess": mean_abs_excess,
            "excess_basis": (EXCESS_BASIS_POOLED if poolable
                             else EXCESS_BASIS_MAGNITUDE),
            "wilson_ci_low": ci_low,
            "state": derive_state(n_dates),
        }
        if not poolable:
            # The per-direction split is the OTHER legal reading of a mixed family;
            # published only where the pooled mean is refused, so its presence in the
            # payload is itself the marker that the pooled figure was withheld.
            row["excess_mean_by_direction"] = {
                str(d): round(v["sum"] / v["n"], 6)
                for d, v in sorted(a["by_dir"].items()) if v["n"]
            }
            row["excess_directions"] = sorted(prof.directions) if prof else []
        out[key] = row
    return out


def _placebo_magnitude(claims: list[dict], grades: list[dict]) -> dict:
    """Compute per-horizon magnitude stats for the placebo tape (D3).

    Reports the mean |excess| across placebo grades at each horizon, split by
    placebo_path ('covered_ticker' entity claims vs 'fallback_no_ticker'
    bench-basket claims). The UI's scoreboard reads this to display the
    "beat placebo" comparison.

    n_fallback is the count of sampled events that had no covered ticker and
    fell back to the bench-basket path (a diagnostic for placebo tape quality).

    P0a MAJOR 1 — THIS WAS THE ONE SURFACE THAT POOLED ACROSS THE CLOCK BASIS,
    NO GUARD AT ALL. Every other aggregation point in this module
    (`_aggregate`, `compute_track_record`, `promotion_check`) partitions grades
    by `grade_clock_basis` before summing anything — this function iterated
    every grade row unconditionally, so a legacy row, a US-explicit row and a
    CN-explicit row at the same horizon summed into ONE |excess| mean. That is
    the exact pooling `require_single_clock`/`partition_grades_by_clock` exist
    to forbid, and it is the placebo tape's counterfactual — the control arm
    the whole "beat placebo" comparison leans on. It now buckets by
    (horizon, placebo_path, clock_basis) and, like `_select_single_clock_block`,
    NEVER blends a horizon's numbers across a basis change: a single basis is
    published as-is; more than one is SELECT-AND-LABEL (most `n_grades` wins,
    every basis's own count stays visible under `clock_bases_n_grades`, and
    `pooling_refused: True` says why the published cell is not the union).
    """
    cid_meta = {c["claim_id"]: c for c in claims
                if c.get("claim_id") and c.get("is_placebo")}
    if not cid_meta:
        return {}

    per_h_basis: dict[str, dict[str, dict[str, dict]]] = {}
    for g in grades:
        cid = g.get("claim_id")
        c = cid_meta.get(cid)
        if c is None:
            continue
        h = int(g.get("horizon_d", -1))
        if h < 0:
            continue
        path = str(c.get("placebo_path") or "unknown")
        exc = g.get("excess")
        if exc is None:
            continue
        basis = grade_clock_basis(g)
        paths = per_h_basis.setdefault(str(h), {}).setdefault(basis, {})
        agg = paths.setdefault(path, {"n": 0, "abs_excess_sum": 0.0})
        agg["n"] += 1
        agg["abs_excess_sum"] += abs(float(exc))

    def _block(paths: dict[str, dict]) -> dict[str, Any]:
        h_out: dict[str, Any] = {}
        total_n = 0
        total_abs = 0.0
        for path, agg in paths.items():
            n = agg["n"]
            mean_abs = round(agg["abs_excess_sum"] / n, 6) if n else None
            h_out[path] = {"n_grades": n, "mean_abs_excess": mean_abs}
            total_n += n
            total_abs += agg["abs_excess_sum"]
        h_out["overall"] = {
            "n_grades": total_n,
            "mean_abs_excess": round(total_abs / total_n, 6) if total_n else None,
        }
        return h_out

    out: dict[str, dict] = {}
    for h_str, by_basis in per_h_basis.items():
        # SORTED, so the selection below cannot depend on grade-row order. This
        # dict was built by iterating `grades` (append-only file order), and the
        # first cut selected with `max(blocks, key=...)` over that insertion
        # order — so on a TIE `max` kept whichever basis happened to appear
        # first in grades.jsonl. Two bases' `n_grades` are monotone integer
        # counts climbing past each other during a migration, so they pass
        # through equality EXACTLY ONCE, and on that night the published placebo
        # counterfactual could flip on file order alone. The placebo tape is the
        # control arm of the whole "beat placebo" comparison; it may not depend
        # on which row was appended first.
        blocks = {basis: _block(paths) for basis, paths in sorted(by_basis.items())}
        if len(blocks) == 1:
            basis, h_out = next(iter(blocks.items()))
            h_out = dict(h_out)
            h_out["clock_basis"] = basis
        else:
            # SELECT-AND-LABEL, never blend — same rule, same reason and now the
            # same DETERMINISTIC tie-break as `_select_single_clock_block`: most
            # `n_grades`, ties to the newer clock, then alphabetically by basis
            # (the sorted feed above + `max` keeping the first maximum). The
            # published cell is one basis's own honest numbers, with every
            # basis's own count disclosed beside it rather than summed into it.
            def _rank(item: tuple[str, dict]) -> tuple[int, int]:
                b, blk = item
                return (int(blk["overall"]["n_grades"] or 0),
                        0 if b == CLOCK_LEGACY else 1)

            basis, chosen = max(blocks.items(), key=_rank)
            h_out = dict(chosen)
            h_out["clock_basis"] = basis
            h_out["pooling_refused"] = True
        h_out["clock_bases"] = sorted(blocks)
        h_out["clock_bases_n_grades"] = {
            b: blk["overall"]["n_grades"] for b, blk in sorted(blocks.items())
        }
        out[h_str] = h_out

    # Fallback rate: fraction of sampled events with no covered ticker
    n_fallback_claims = sum(
        1 for c in cid_meta.values() if c.get("placebo_path") == "fallback_no_ticker"
    )
    # Claims are registered per-horizon × per-ticker; count unique events instead
    fallback_event_ids = {
        c.get("event_id") for c in cid_meta.values()
        if c.get("placebo_path") == "fallback_no_ticker"
    }
    covered_event_ids = {
        c.get("event_id") for c in cid_meta.values()
        if c.get("placebo_path") == "covered_ticker"
    }
    out["_meta"] = {
        "n_placebo_claims": len(cid_meta),
        "n_covered_events": len(covered_event_ids),
        "n_fallback_events": len(fallback_event_ids),
        "fallback_rate": (
            round(len(fallback_event_ids) /
                  (len(fallback_event_ids) + len(covered_event_ids)), 4)
            if (fallback_event_ids or covered_event_ids) else None
        ),
    }
    return out


def _authority_clock_basis(bases: Iterable[str]) -> str | None:
    """The ONE basis a PROMOTION gate evaluates on, or None when no non-arbitrary
    choice exists.

    THE MIGRATION MUST TERMINATE. Refusing every straddled family outright — the
    first cut of this contract — is a permanent state, not a migration: a family
    with one legacy row and 25 explicit-clock dates would stay INELIGIBLE forever,
    so `promotion_check` could never again return True for anything that existed
    before P0a. The rule here is instead: **authority evaluates INSIDE the
    explicit-clock basis and counts nothing else.**

      * one basis present            -> that basis
      * legacy + exactly ONE v1      -> the v1 basis (legacy rows are not counted)
      * two or more v1 bases         -> None (a family mixing trading_days and
                                        calendar_days — or US sessions and CN
                                        sessions — at one horizon has no
                                        non-arbitrary answer: refuse, and say so.
                                        A caller that wants ONE of them asks for
                                        it by name, `promotion_check(...,
                                        clock_basis=...)`, which is how a
                                        multi-market family stays PROMOTABLE
                                        per market without anything pooling.)

    Why this terminates: a lane that declares a unit stops minting legacy claims,
    so its legacy rows stop accruing once the last unitless claim matures (≤63d),
    while the v1 count climbs from 0 toward the 25-date bar. The path is
    monotone and finite. Authority is RESET by the basis change rather than
    inherited across it, which is the honest reading of a measurement-basis
    change — the alternative (pool, or ride whichever basis is bigger) launders
    59,326 legacy observations into a gate about a clock they were never measured
    on. NOT a trailing time window: a window that straddles the change still
    pools, and its length would be a free parameter nobody pre-registered.
    """
    bases = sorted(set(bases))
    if not bases:
        return None
    if len(bases) == 1:
        return bases[0]
    explicit = [b for b in bases if b != CLOCK_LEGACY]
    return explicit[0] if len(explicit) == 1 else None


# The DISPLAY-tier selection rule, named so the intent is explicit rather than
# implied by a lambda. "Most independent date clusters, ties to the newer clock."
CLOCK_DISPLAY_SELECTION = "max_n_dates_tie_newer"


def _select_single_clock_block(blocks: dict[str, dict]) -> dict:
    """Resolve a group/horizon cell whose history STRADDLES two clock bases.

    The rule is SELECT-AND-LABEL, never pool: the published cell is ONE basis's
    own honest numbers — `CLOCK_DISPLAY_SELECTION`, i.e. the basis with the most
    independent date clusters, ties broken toward the newer clock — carrying
    `clock_basis`, every basis present in `clock_bases`, `pooling_refused: True`,
    the named rule in `clock_basis_selection`, and EVERY basis's date count in
    `clock_bases_n_dates`. Nothing is summed across a measurement-basis change.

    DISCLOSED LIMITATION — the legacy basis will win for a long time. Selecting
    on sample size is deliberate for a display tier (the headline cell should be
    the largest honest sample, not the newest sliver), but with 59,326 legacy
    grade rows already in the store the legacy basis takes essentially every
    straddled cell until the explicit-clock corpus overtakes it, which is years
    of accrual at current volume. Correctly-clocked observations are therefore
    NOT the headline for those cells — but they are never invisible: their count
    sits in the same cell under `clock_bases_n_dates`, their full stats under
    ``track_record["by_clock_basis"]``, and the row split under
    ``counts.grades_by_clock_basis``. A reader who wants the new clock's numbers
    can always get them; a reader who reads only the headline is told, in the
    cell, that a bigger-but-older basis was chosen and how big the other one is.

    A TIE BETWEEN TWO MARKETS RESOLVES ALPHABETICALLY, not meaningfully. Now that
    the basis key carries the market, two EXPLICIT blocks (a US one and a CN one)
    can tie on n_dates and on the legacy/newer key; `compute_track_record` feeds
    the blocks in sorted-basis order and `max` keeps the first, so the CN block
    wins such a tie. That is deterministic (the published cell never depends on
    grade-row order) but it is NOT a judgement that CN is the better read — the
    other market's own numbers stay in `clock_bases_n_dates` and under
    ``by_clock_basis``, and a consumer that needs a specific market must name it.

    Display selects; AUTHORITY does the opposite — `promotion_check` evaluates
    inside the EXPLICIT basis via `_authority_clock_basis` and ignores the legacy
    pile entirely, because a gate may not ride the sample size of a clock it is
    not gating on.
    """
    def rank(item: tuple[str, dict]) -> tuple[int, int]:
        basis, block = item
        return (int(block.get("n_dates") or 0), 0 if basis == CLOCK_LEGACY else 1)

    basis, chosen = max(blocks.items(), key=rank)
    out = dict(chosen)
    out["clock_basis"] = basis
    out["clock_bases"] = sorted(blocks)
    out["clock_basis_selection"] = CLOCK_DISPLAY_SELECTION
    out["clock_bases_n_dates"] = {b: int(blk.get("n_dates") or 0)
                                  for b, blk in sorted(blocks.items())}
    out["pooling_refused"] = True
    return out


def compute_track_record(root: Path | str | None = None) -> dict:
    """Build the track_record.json payload — per desk and per claim-family, at
    each grade horizon. Does not write; `emit_track_record` persists it. Pure so
    it is trivially testable and the nightly runner controls IO.

    P0a: stats are computed PER GRADING-CLOCK BASIS and published under
    `by_clock_basis`; nothing is ever summed across bases. A group whose history
    straddles two bases at one horizon publishes ONE basis's numbers, labelled
    (`_select_single_clock_block`), never a blend."""
    root = _root(root)
    claims = load_claims(root)
    grades = load_grades(root)

    bases = sorted(partition_grades_by_clock(grades))
    # basis -> {"by_desk": {...}, "by_family": {...}}
    per_basis: dict[str, dict[str, dict]] = {
        b: {"by_desk": {}, "by_family": {}} for b in bases
    }
    for b in bases:
        for h in GRADE_HORIZONS:
            for grp, dest_key in (("desk", "by_desk"), ("family", "by_family")):
                stats = _aggregate(claims, grades, grp, h, clock_basis=b)
                for key, s in stats.items():
                    per_basis[b][dest_key].setdefault(key, {})[str(h)] = s

    by_desk: dict[str, dict] = {}
    by_family: dict[str, dict] = {}
    for dest_key, dest in (("by_desk", by_desk), ("by_family", by_family)):
        # group -> horizon -> {basis: block}
        seen: dict[str, dict[str, dict[str, dict]]] = {}
        for b in bases:
            for key, horizons in per_basis[b][dest_key].items():
                for hkey, block in horizons.items():
                    seen.setdefault(key, {}).setdefault(hkey, {})[b] = block
        for key, horizons in seen.items():
            for hkey, blocks in horizons.items():
                dest.setdefault(key, {})[hkey] = (
                    next(iter(blocks.values())) if len(blocks) == 1
                    else _select_single_clock_block(blocks))

    n_placebo = sum(1 for c in claims if c.get("is_placebo"))
    n_rejected = sum(1 for c in claims if c.get("status") == STATUS_REJECTED)
    # W0 Stage B-e honesty lines: the stamped fill-convention split (rows
    # lacking the field predate the next-bar migration = asof_legacy) and the
    # §3.4 residual regime-unstamped claim count.
    conv_counts: dict[str, int] = {}
    for g in grades:
        k = str(g.get("fill_convention") or FILL_ASOF_LEGACY)
        conv_counts[k] = conv_counts.get(k, 0) + 1
    # P0a: the SECOND stamped discontinuity — the grading clock. Same honesty
    # line as the fill-convention split above; unstamped rows read as legacy.
    clock_counts: dict[str, int] = {}
    for g in grades:
        k = grade_clock_basis(g)
        clock_counts[k] = clock_counts.get(k, 0) + 1
    n_unstamped = sum(1 for c in claims if c.get("vector_asof") is None)
    n_unit_declared = sum(1 for c in claims
                          if claim_horizon_unit(c) is not None)
    return {
        "generated_at": _now_iso(),
        "grade_horizons": list(GRADE_HORIZONS),
        "graded_min_dates": GRADED_MIN_DATES,
        "by_desk": by_desk,
        "by_family": by_family,
        "by_clock_basis": per_basis,
        "placebo_magnitude": _placebo_magnitude(claims, grades),  # D3 counterfactual
        "counts": {
            "n_claims": len(claims),
            "n_grades": len(grades),
            "n_placebo": n_placebo,
            "n_rejected": n_rejected,     # the D4 dark-fraction numerator
            "grades_by_fill_convention": conv_counts,   # stamped discontinuity
            "grades_by_clock_basis": clock_counts,      # P0a stamped discontinuity
            "n_claims_horizon_unit_declared": n_unit_declared,
            "n_claims_unstamped_regime": n_unstamped,   # §3.4 residual
        },
    }


def emit_track_record(root: Path | str | None = None) -> dict:
    """Compute and write site/qledger/track_record.json. Returns the payload.
    Data write precedes any render (the macro#895 class fixed architecturally,
    §2.5) — this is a data write, callers render from the file."""
    root = _root(root)
    payload = compute_track_record(root)
    p = root.joinpath(*_TRACK_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


# --------------------------------------------------------------------------- #
# PROMOTION LADDER — §3 gate + auto-demote
# --------------------------------------------------------------------------- #
# Ladder rungs in order; a family can only move up one rung at a time (gate
# required at each step) and can auto-demote if the rolling CI falls below 0.
LADDER_RUNGS = ("DISPLAY", "SHADOW", "CONFIRMER", "SCORED")
_RUNG_IDX = {r: i for i, r in enumerate(LADDER_RUNGS)}

# Block-bootstrap: minimum number of distinct date clusters required to pass §3.
PROMOTION_MIN_DATES = GRADED_MIN_DATES   # 25 — same constant, aliased for clarity
# §3 criterion 2 floor. wilson_ci_low returns a HIT-RATE PROPORTION in [0, 1], so the old
# `> 0` test was satisfied by any nonzero hit count — a gate that could not fail. 0.5 is the
# coin-flip null: the honest question is whether the family calls direction better than
# chance, not whether it ever hits at all (2026-08-03 experiments audit).
PROMOTION_MIN_CI_LOW = 0.5


class PromotionResult:
    """Outcome of a promotion_check() call.

    Attributes:
        eligible:       True if the §3 gate would permit promotion to CONFIRMER.
        reason:         Human-readable explanation of the gate result.
        n_dates:        Number of independent date clusters in the grade set.
        wilson_ci_low:  Wilson CI lower bound (None if n_dates == 0).
        current_state:  derive_state() chip value, EXCEPT that a legacy-only
                        basis reaching GRADED territory reads
                        STATE_LEGACY_NOT_AUTHORITY_ELIGIBLE instead of
                        STATE_GRADED (P0c-2, CEO ruling 2026-08-13 §5) — the
                        one deliberate override of the plain n_dates chip.
        demote:         True if the rolling CI has gone negative — auto-demote is warranted.
        pinned_reason:  Suggested pin reason string (mirrors narrative_regime precedent).
        clock_basis:    (P0a) the ONE grading-clock basis this verdict was computed
                        on. None when no basis could be chosen (the family mixes two
                        EXPLICIT bases) or when there are no rows to evaluate. Any
                        consumer reporting these numbers must report this alongside
                        them — the same n_dates means different things on different
                        clocks.
        clock_migration: (P0a) True while this verdict's `n_dates` is SMALLER
                        than the largest excluded basis's own n_dates — i.e.
                        while there is a drop to explain, and the drop is a clock
                        migration rather than a performance collapse. It is False
                        for a family that never straddled, AND for one that has
                        finished migrating: the flag CLEARS as soon as the count
                        on the corrected clock reaches the excluded history it
                        replaced. It is not "this family has any old rows" —
                        that condition never clears, and a banner that never
                        clears says nothing.

                        (round 5, MAJOR 3) It is ALSO False for a family in
                        `STATE_MIXED_CLOCK` — a family that has genuinely
                        started accruing on two EXPLICIT bases at once (two
                        markets, most often). That is not a migration: there is
                        no single corrected clock this family is converging
                        toward, both bases keep accruing forever, and a flag
                        that would never clear is not disclosure, it is a
                        permanently false "re-accruing" sentence. Read
                        `current_state` to tell the two apart:
                        `STATE_MIXED_CLOCK` + `clock_migration=False` is a
                        stable multi-basis split (promote each basis by name,
                        `promotion_check_by_market`); `clock_migration=True`
                        (any other state) is a one-time, terminating
                        legacy->explicit changeover.
        clock_prior_n_dates: {basis -> its own n_dates} for every basis this
                        verdict is NOT counting toward its headline —whether
                        excluded (a migration) or simply the OTHER market in a
                        MIXED_CLOCK split — so a consumer can say "1 date on
                        the corrected clock; the 40 dates it had were measured
                        on the old one" (migration) or "26 dates on US; 26 on
                        CN, neither summed" (split) instead of showing a bare
                        number with no context. Populated whenever another
                        basis exists, INCLUDING after `clock_migration` has
                        cleared and for a MIXED_CLOCK split (where it is never
                        going to clear) — this is a fact about the verdict,
                        not gated on the flag.
        migration_note: one plain sentence a surface can render as-is; empty
                        string exactly when `clock_migration` is False —
                        including the MIXED_CLOCK case, where `reason` already
                        carries the (different, accurate) prose.

    WHY THIS EXISTS. `_authority_clock_basis` resets authority at a basis change
    — the right call, and the CEO's explicit ruling (do NOT pool bases). But the
    reset is instantaneous and total: the night the first explicit-clock grade
    lands for an already-promoted family, this object flips from
    GRADED/n_dates=40 to ACCRUING/n_dates=1 with nothing on it saying why. A
    reader — or the admin Experiments tab, or a readiness alert — cannot tell
    that apart from a family whose evidence evaporated. The numbers stay exactly
    as the ruling requires; what is added is the reason they moved.

    P0d — THE EVIDENCE BASIS TRAVELS WITH THE VERDICT (C5.4). Four concepts stay
    separate on every rendered surface (C6.1): benchmark-relative evidence,
    matched-control evidence, control coverage, and authority eligibility. So a
    verdict now says which basis produced it (`evidence_basis` ∈ matched_control
    | benchmark | not_applicable, plus the `unclassified` flag for a family
    absent from the governed policy table), and a matched-control verdict carries
    the coverage accounting it was reached under: `n_cohort_dates` (independent
    date clusters over ALL prospective cohort members at this horizon/basis),
    `n_controlled_dates` (the same count over members carrying a valid control),
    `control_coverage` (their ratio), the row-count pair `n_cohort_rows` /
    `n_controlled_rows`, and `control_clock_start` (when this family's
    matched-control evidence began accruing — None while it has not). The
    headline `n_dates` of a matched-control verdict IS `n_controlled_dates`: the
    Wilson interval is projected onto the controlled count only (C4.3), never
    onto the full family's, so a rate measured on 37 rows can never be stated at
    a 100-row N. Every field defaults to None/False, so a benchmark verdict is
    unchanged in shape and no consumer has to know about P0d to keep working.
    """
    __slots__ = ("eligible", "reason", "n_dates", "wilson_ci_low",
                 "current_state", "demote", "pinned_reason", "clock_basis",
                 "clock_migration", "clock_prior_n_dates", "migration_note",
                 "evidence_basis", "control_coverage", "n_cohort_dates",
                 "n_controlled_dates", "n_cohort_rows", "n_controlled_rows",
                 "control_clock_start", "unclassified")

    def __init__(self, eligible: bool, reason: str, n_dates: int,
                 ci_low: float | None, current_state: str,
                 demote: bool = False, pinned_reason: str = "",
                 clock_basis: str | None = None,
                 clock_migration: bool = False,
                 clock_prior_n_dates: dict | None = None,
                 migration_note: str = "",
                 evidence_basis: str | None = None,
                 control_coverage: float | None = None,
                 n_cohort_dates: int | None = None,
                 n_controlled_dates: int | None = None,
                 n_cohort_rows: int | None = None,
                 n_controlled_rows: int | None = None,
                 control_clock_start: str | None = None,
                 unclassified: bool = False) -> None:
        self.eligible = eligible
        self.reason = reason
        self.n_dates = n_dates
        self.wilson_ci_low = ci_low
        self.current_state = current_state
        self.demote = demote
        self.pinned_reason = pinned_reason
        self.clock_basis = clock_basis
        self.clock_migration = clock_migration
        self.clock_prior_n_dates = dict(clock_prior_n_dates or {})
        self.migration_note = migration_note
        # P0d (C5.4) — all default-safe: an untouched benchmark verdict keeps its
        # exact previous shape plus a label.
        self.evidence_basis = evidence_basis
        self.control_coverage = control_coverage
        self.n_cohort_dates = n_cohort_dates
        self.n_controlled_dates = n_controlled_dates
        self.n_cohort_rows = n_cohort_rows
        self.n_controlled_rows = n_controlled_rows
        self.control_clock_start = control_clock_start
        self.unclassified = unclassified

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "reason": self.reason,
            "n_dates": self.n_dates,
            "wilson_ci_low": self.wilson_ci_low,
            "current_state": self.current_state,
            "demote": self.demote,
            "pinned_reason": self.pinned_reason,
            "clock_basis": self.clock_basis,
            "clock_migration": self.clock_migration,
            "clock_prior_n_dates": self.clock_prior_n_dates,
            "migration_note": self.migration_note,
            "evidence_basis": self.evidence_basis,
            "control_coverage": self.control_coverage,
            "n_cohort_dates": self.n_cohort_dates,
            "n_controlled_dates": self.n_controlled_dates,
            "n_cohort_rows": self.n_cohort_rows,
            "n_controlled_rows": self.n_controlled_rows,
            "control_clock_start": self.control_clock_start,
            "unclassified": self.unclassified,
        }


def promotion_check(claim_family: str, horizon: int,
                    root: Path | str | None = None,
                    control_only: bool = False,
                    clock_basis: str | None = None) -> PromotionResult:
    """Evaluate the §3 promotion gate for a claim_family at a given horizon.

    §3 gate (SHADOW → CONFIRMER):
      1. n_dates >= 25 (independent date clusters, the honest n [P1])
      2. Wilson-CI lower bound of excess hit-rate vs matched control > 0.5 at the
         claim's horizon (not vs SPY — vs control; SPY excess is the headline,
         control excess is the gate). The bound is a PROPORTION, so 0.5 — the
         coin-flip null — is the bar; the old `> 0` was cleared by a single hit.
      3. Rolling check: if wilson_ci_low <= 0.5 on the trailing window → demote.

    The block-bootstrap stability check (§3: "across date clusters") and the
    incremental-information check ("incremental over price+VIX baseline") are
    noted in the result but their implementation is deferred to the W6 composite
    validator — this function gates on the two hard numeric criteria.

    P0a — THE GATE EVALUATES INSIDE EXACTLY ONE GRADING-CLOCK BASIS, and never
    pools two. When a family's rows straddle the legacy and explicit clocks, the
    gate counts ONLY the explicit-clock rows (`_authority_clock_basis`): the
    legacy pile is neither pooled in nor allowed to carry the family over the
    bar, and the family's authority accrues from zero on the clock it is now
    measured on. That is a TERMINATING migration — see `_authority_clock_basis`
    for why the first cut (refuse every straddled family) was not. A family
    mixing two EXPLICIT bases at one horizon is genuinely ambiguous and is still
    refused as `STATE_MIXED_CLOCK`.

    P0c-2 — CEO ruling 2026-08-13 §5: EVEN WHEN a legacy-only basis is the ONE
    basis a family holds (today, every live family — no explicit-clock grade
    row exists yet), it may not INDEPENDENTLY produce `eligible=True`. The
    numbers still compute and still publish (n_dates, wilson_ci_low, the reason
    string); only the verdict is withdrawn — see
    `STATE_LEGACY_NOT_AUTHORITY_ELIGIBLE`. This does not change straddled-family
    behaviour above: a family holding legacy + exactly one explicit basis still
    evaluates and promotes on the explicit basis alone, unaffected.

    Args:
        claim_family: The `claim_family` tag (matches qledger claims.jsonl rows).
        horizon:      The horizon_d to check (typically 5, 21, or 63).
        root:         Repo root; defaults to config.ROOT.
        control_only: When True, evaluate excess vs control_ret rather than bench.
                      §3 specifies "vs matched control" as the gate leg.
        clock_basis:  Evaluate on THIS `grade_clock_basis` value explicitly (e.g.
                      to ask what the legacy history said). Default None selects
                      per `_authority_clock_basis`.

    Returns:
        PromotionResult with eligible/reason/n_dates/wilson_ci_low/demote and the
        `clock_basis` the verdict was computed on.
    """
    root = _root(root)
    claims = load_claims(root)
    grades = load_grades(root)

    # Index claims by claim_id for fast lookup
    cid_meta = {
        c["claim_id"]: c for c in claims
        if c.get("claim_id") and c.get("claim_family") == claim_family
        and not c.get("is_placebo")
    }

    if not cid_meta:
        return PromotionResult(
            eligible=False,
            reason=f"No claims found for claim_family={claim_family!r}",
            n_dates=0, ci_low=None,
            current_state=STATE_UNGRADED,
        )

    # Collect grade rows at the target horizon for this family
    hits = 0
    graded_hits = 0
    dates: set[str] = set()

    family_rows = [g for g in grades
                   if int(g.get("horizon_d", -1)) == horizon
                   and cid_meta.get(g.get("claim_id")) is not None]

    # P0a: a promotion gate is the sharpest place pooling could launder a
    # measurement-basis change into authority. It never pools — it evaluates
    # inside ONE basis and says which, and it refuses (INELIGIBLE, not a
    # traceback) only when no non-arbitrary basis exists.
    family_bases = sorted({grade_clock_basis(g) for g in family_rows})
    basis = clock_basis or _authority_clock_basis(family_bases)

    # P0a MIGRATION LEGIBILITY. Count each basis's OWN independent date clusters
    # before the excluded ones are dropped, so the verdict can carry the size of
    # the history it is NOT counting. Nothing here is pooled or added to n_dates —
    # this is disclosure, not arithmetic (see PromotionResult.clock_migration).
    n_dates_by_basis: dict[str, int] = {}
    for b in family_bases:
        n_dates_by_basis[b] = len({
            _date_cluster(str((cid_meta.get(g.get("claim_id")) or {}).get("asof", "")))
            for g in family_rows if grade_clock_basis(g) == b
            and cid_meta.get(g.get("claim_id")) is not None
        })

    if basis is None and family_bases:
        return PromotionResult(
            # P0a MAJOR 3 (round 5) — THIS IS A STABLE SPLIT, NOT A MIGRATION.
            # `clock_migration` means "the live count is smaller than a history
            # counted on a DIFFERENT clock because this family is partway
            # through a ONE-TIME basis change" (see the single-basis branch
            # below) — and it is TRUE exactly while that count is catching up,
            # then CLEARS. A family straddling two markets never converges to
            # one clock: both keep accruing every night, forever, so there is
            # no "corrected clock" this family is re-accruing toward. Labelling
            # that `clock_migration=True` was market-blind and produced a
            # FALSE sentence downstream (`experiments_registry` rendered
            # "RE-ACCRUING on a corrected clock ... not lost" for a family that
            # was never migrating anywhere) that never cleared, because a
            # bi-market split cannot clear — that is not disclosure, it is a
            # permanently mislabelled state. `current_state=STATE_MIXED_CLOCK`
            # already names what this is; `clock_prior_n_dates` still
            # discloses each basis's own count (unchanged — it is a fact about
            # the verdict, not gated on this flag) so nothing is hidden, but
            # promotion for EACH market on its own is reachable by name
            # (`promotion_check(..., clock_basis=...)`, wired into production
            # via `promotion_check_by_market`/`emit_ladder_states`) — this is
            # never the family's terminal state.
            clock_migration=False,
            clock_prior_n_dates=n_dates_by_basis,
            migration_note="",
            eligible=False,
            reason=(f"claim_family={claim_family!r} horizon={horizon}d: grades "
                    f"straddle {len(family_bases)} grading-clock bases "
                    f"({', '.join(family_bases)}) with no single explicit clock "
                    f"to promote on — refusing to pool. Two rows both stamped "
                    f"horizon_d={horizon} are not comparable across a clock "
                    f"change or across two exchange calendars; give this family "
                    f"ONE horizon_unit, or evaluate ONE basis by name "
                    f"(clock_basis=...) to promote per market."),
            n_dates=0, ci_low=None,
            current_state=STATE_MIXED_CLOCK,
            clock_basis=None,
        )
    excluded = [b for b in family_bases if b != basis]
    family_rows = [g for g in family_rows if grade_clock_basis(g) == basis]
    basis_note = ""
    prior_n_dates = {b: n_dates_by_basis.get(b, 0) for b in excluded}
    if excluded:
        basis_note = (f" Evaluated on clock basis {basis!r}; "
                      f"{len(excluded)} other basis/bases "
                      f"({', '.join(excluded)}) excluded, NOT pooled — this "
                      f"family's authority accrues on the clock it is now "
                      f"measured on.")

    for g in family_rows:
        c = cid_meta.get(g.get("claim_id"))
        if c is None:
            continue
        dates.add(_date_cluster(c.get("asof", "")))

        hit = g.get("hit")
        if hit is None:
            continue

        if control_only:
            # P0c-1 (research/PREREG_P0C1_DIRECTION_CORRECT_CONTROL_HITS.md).
            # THE DEFECT this replaces: `if ctrl_excess > 0: hits += 1` never
            # read the claim's `direction`, so a direction=-1 (bearish) call
            # that correctly called subject_ret < control_ret scored a MISS,
            # and a WRONG bearish call scored a HIT — an inverted hit series
            # for every family holding short claims. The §3 Wilson bound (the
            # promotion gate) was therefore computed on inverted arithmetic
            # for any family holding short claims.
            #
            # `bench_ret` used to be read AND GATED ON here but never used in
            # the comparison — the gate is dropped (not the field's meaning
            # elsewhere): it is not part of the control leg, and gating on it
            # only caused a row with a valid control leg but a null bench to
            # wrongly fall through to the primary-hit fallback below.
            ctrl = g.get("control_ret")
            subj = g.get("subject_ret")
            if ctrl is None or subj is None:
                # Missing control leg: this row CANNOT be scored on the
                # control leg. Prereg §2/§3 — EXCLUDED from numerator AND
                # denominator, never converted into a miss, and never
                # silently rescored on the primary (bench-relative) `hit` the
                # way the old `elif hit: hits += 1` fallback did (that
                # fallback is exactly what let a control-only reading mix in
                # bench-relative outcomes). Skip both `graded_hits` and `hits`
                # for this row — it contributes to neither the numerator nor
                # the denominator of the control-only hit rate. (n_dates is
                # unaffected: it is computed above, over the whole grade set,
                # unconditionally — this fix changes how a row's hit counts,
                # never which claims are eligible.)
                continue

            direction = c.get("direction")
            if not direction:
                # direction == 0 (salience) or absent: "salience-only claims
                # have no direction to be right about" (prereg §2). No
                # directional hit, AND excluded from the denominator so a
                # salience-dominated family cannot inflate its control-only
                # hit rate's base via rows it has nothing to say about
                # (prereg §6.3). In production these rows already carry
                # hit=None (grade_claim() salience path, prereg §5) and never
                # reach this branch at all — this check makes that invariant
                # explicit rather than assumed, so this function's
                # control-only semantics do not silently depend on an
                # upstream contract it cannot see.
                continue

            graded_hits += 1
            raw_control_excess = subj - ctrl
            # direction * raw_control_excess > 0  <=>  (direction==+1 and
            # excess>0) or (direction==-1 and excess<0) — the mirrored rule,
            # prereg §2. Strict `>` so an exact-zero excess is NOT a hit.
            if direction * raw_control_excess > 0:
                hits += 1
        else:
            graded_hits += 1
            if hit:
                hits += 1

    n_dates = len(dates)
    current_state = derive_state(n_dates)

    # P0c-2 — CEO ruling 2026-08-13 §5: legacy-clock evidence "cannot
    # independently create a new promotion after the explicit-clock
    # discontinuity". `basis` resolves to CLOCK_LEGACY only when the family
    # holds NO explicit-clock grade row at all (see `_authority_clock_basis`:
    # legacy is picked only as the sole basis, never over an explicit one).
    # Once such a family reaches GRADED territory this verdict is relabelled
    # STATE_LEGACY_NOT_AUTHORITY_ELIGIBLE and forced ineligible below — the
    # numbers (n_dates, ci_low once computed) are untouched and still returned.
    legacy_authority_withdrawn = (basis == CLOCK_LEGACY
                                  and current_state == STATE_GRADED)
    if legacy_authority_withdrawn:
        current_state = STATE_LEGACY_NOT_AUTHORITY_ELIGIBLE

    # P0a — THE MIGRATION BANNER MUST CLEAR. `clock_migration` used to be
    # `bool(excluded)`: any family carrying even ONE row on another basis was
    # flagged as migrating forever, including a family that finished migrating
    # years ago and whose legacy pile is a closed, never-growing set. A permanent
    # banner is not a disclosure, it is furniture.
    #
    # WHAT THE FLAG MEANS, EXACTLY (and the docstrings say only this): the
    # headline `n_dates` on the authoritative basis is SMALLER than the history
    # this verdict is not counting — i.e. the drop a reader sees is a clock
    # migration, not a performance collapse. It is therefore TRUE exactly while
    # there is a drop to explain and CLEARS the moment the family's own count on
    # the corrected clock reaches the largest excluded basis's count. That is
    # monotone and terminating for the same reason `_authority_clock_basis` is: a
    # lane that declares a unit stops minting rows on the old basis, so the
    # excluded count is frozen while `n_dates` climbs.
    #
    # `clock_prior_n_dates` is NOT gated on the flag — the excluded history is a
    # fact about the verdict whether or not it is still shrinking the headline,
    # and a consumer that shows counts side by side needs it either way.
    biggest_excluded = max(prior_n_dates.values()) if prior_n_dates else 0
    clock_migration = bool(excluded) and n_dates < biggest_excluded
    migration_note = ""
    if clock_migration:
        # The one sentence a surface may render as-is. Plain words on purpose: a
        # reader must be able to tell a clock migration from a collapse without
        # knowing what a "basis" is.
        migration_note = (
            f"Re-accruing under a corrected clock: this family is counted from "
            f"zero on the clock it is now measured on. Its earlier "
            f"{biggest_excluded} dates were measured on a different clock and "
            f"are not counted here — that history was not lost and its numbers "
            f"have not changed.")
    mig = {"clock_migration": clock_migration,
           "clock_prior_n_dates": prior_n_dates,
           "migration_note": migration_note}
    # Cluster-honest Wilson CI: project pooled hit rate onto independent date-cluster n.
    # Mirrors _aggregate convention (altdata_brain.py:389, ticker-cluster time-confound law).
    if graded_hits and n_dates:
        cluster_hits = int(round(hits / graded_hits * n_dates))
        ci_low = wilson_ci_low(cluster_hits, n_dates)
    else:
        ci_low = None

    # §3 gate criterion 1: n_dates
    if n_dates < PROMOTION_MIN_DATES:
        return PromotionResult(
            eligible=False,
            reason=(f"n_dates={n_dates} < {PROMOTION_MIN_DATES} required. "
                    f"State: {current_state}. "
                    f"Need {PROMOTION_MIN_DATES - n_dates} more independent date "
                    f"clusters.{basis_note}"),
            n_dates=n_dates, ci_low=ci_low,
            current_state=current_state,
            clock_basis=basis,
            **mig,
        )

    # §3 gate criterion 2: wilson_ci_low > PROMOTION_MIN_CI_LOW (the coin-flip null)
    if ci_low is None:
        return PromotionResult(
            eligible=False,
            reason=(f"n_dates={n_dates} OK but no directional hits recorded "
                    f"(graded_hits={graded_hits}) — cannot compute Wilson CI. "
                    f"Family may be salience-only (direction=0); salience families "
                    f"gate on |excess| > placebo instead.{basis_note}"),
            n_dates=n_dates, ci_low=None,
            current_state=current_state,
            clock_basis=basis,
            **mig,
        )

    # Auto-demote check: CI bracketing (or below) the coin-flip null on a family that was
    # previously above the bar. A hit-rate CI whose lower bound sits at or under 0.5 is
    # consistent with no directional skill at all — that is not a rung, it is a coin.
    demote = ci_low <= PROMOTION_MIN_CI_LOW
    pinned_reason = ""
    if demote:
        pinned_reason = (
            f"claim_family={claim_family!r} horizon={horizon}d: "
            f"rolling Wilson CI lower bound={ci_low:.4f} <= {PROMOTION_MIN_CI_LOW} "
            f"(coin-flip null) at n_dates={n_dates}. Auto-demote one rung. "
            f"Pinned as of {_now_iso()[:10]} (narrative_regime precedent)."
        )
        return PromotionResult(
            eligible=False,
            reason=f"Wilson CI lower bound {ci_low:.4f} <= {PROMOTION_MIN_CI_LOW} — the "
                   f"hit-rate interval does not clear a coin flip. AUTO-DEMOTE warranted. "
                   f"{pinned_reason}{basis_note}",
            n_dates=n_dates, ci_low=ci_low,
            current_state=current_state,
            demote=True, pinned_reason=pinned_reason,
            clock_basis=basis,
            **mig,
        )

    # Both §3 numeric gates pass — but P0c-2 (CEO ruling 2026-08-13 §5) withdraws
    # AUTHORITY from a legacy-only basis even when the numbers clear. This branch
    # only ever fires when `basis` resolved to CLOCK_LEGACY, which — per
    # `_authority_clock_basis` — happens only when the family holds NO
    # explicit-clock grade row at all. Explicit-clock evidence is untouched by
    # this check and still promotes normally, on its own n (never pooled with
    # any legacy count — see `family_bases`/`_authority_clock_basis` above).
    if legacy_authority_withdrawn:
        return PromotionResult(
            eligible=False,
            reason=(f"n_dates={n_dates} >= {PROMOTION_MIN_DATES} and Wilson CI "
                    f"lower bound={ci_low:.4f} > {PROMOTION_MIN_CI_LOW} on the "
                    f"LEGACY grading clock — but legacy-clock evidence cannot "
                    f"independently mint a new promotion (CEO ruling 2026-08-13 "
                    f"§5, post explicit-clock discontinuity). This is historical "
                    f"evidence, honestly reported, not authority: an "
                    f"explicit-clock grade row must accrue for this family and "
                    f"independently clear this same gate on its own n before it "
                    f"promotes.{basis_note}"),
            n_dates=n_dates, ci_low=ci_low,
            current_state=current_state,
            clock_basis=basis,
            **mig,
        )

    # Both gates pass
    return PromotionResult(
        eligible=True,
        reason=(f"§3 gate PASS at horizon={horizon}d: "
                f"n_dates={n_dates} >= {PROMOTION_MIN_DATES}, "
                f"Wilson CI lower bound={ci_low:.4f} > {PROMOTION_MIN_CI_LOW}. "
                f"Block-bootstrap stability and incremental-information checks "
                f"(price+VIX baseline) are delegated to the W6 composite "
                f"validator.{basis_note}"),
        n_dates=n_dates, ci_low=ci_low,
        current_state=current_state,
        clock_basis=basis,
        **mig,
    )


def promotion_check_by_market(claim_family: str, horizon: int,
                              mixed: "PromotionResult",
                              root: Path | str | None = None,
                              control_only: bool = False) -> dict[str, "PromotionResult"]:
    """P0a MAJOR 2 (round 5) — PROMOTION, REACHABLE PER MARKET, FROM PRODUCTION.

    `promotion_check`'s default resolves via `_authority_clock_basis`, which
    answers None for a family holding two or more EXPLICIT bases (a family
    that has genuinely started accruing on two markets) — that is the correct,
    deliberate refusal to pool. `promotion_check(..., clock_basis=...)` CAN
    promote such a family per market, but nothing in the only two production
    call paths that reach `promotion_check` (`emit_ladder_states`,
    `scripts.grade_qledger.compute_promotion_readiness`) ever names one, so a
    bi-market family was unreachable for promotion through any path a nightly
    run actually takes — reachable in principle, never in practice.

    Call this with the STATE_MIXED_CLOCK `PromotionResult` `promotion_check`
    just returned (`mixed`); it re-evaluates the SAME family/horizon once per
    EXPLICIT basis that result's own `clock_prior_n_dates` discloses (the
    disclosure IS the enumeration), NEVER pooling any two of them. Returns
    `{}` when `mixed` was not actually a MIXED_CLOCK verdict (nothing to
    re-evaluate — the default already named the one basis that matters).

    THE LEGACY BASIS IS ENUMERATED BUT NEVER RE-EVALUATED. `clock_prior_n_dates`
    discloses every basis a family holds, `CLOCK_LEGACY` included — that
    disclosure is deliberate and stays. Feeding it back into `promotion_check`
    is a different act: it would mint a real, per-basis PROMOTION VERDICT on
    the legacy grading basis and publish it into `track_record.json`
    (`ladder_states.<fam>.<h>.by_clock_basis`), where a `GRADED` cell reads as
    authority earned. `_authority_clock_basis` already refuses exactly this for
    the default path ("legacy + one v1 -> the v1 basis; legacy rows are not
    counted"), and the whole point of the P0a contract is that a
    measurement-basis change RESETS authority rather than carrying it across.
    So the per-market escape hatch inherits that rule instead of quietly
    routing around it: authority is evaluated only inside an explicit basis.

    Not reachable on today's corpus — no explicit-clock grade row exists yet, so
    nothing can be STATE_MIXED_CLOCK — but it becomes reachable the first night
    a second market accrues, which is precisely when a legacy `GRADED` cell
    would appear beside the real ones. Pinned by
    `test_promotion_check_by_market_never_evaluates_the_legacy_basis`."""
    if mixed.current_state != STATE_MIXED_CLOCK:
        return {}
    return {
        basis: promotion_check(claim_family, horizon, root=root,
                               control_only=control_only, clock_basis=basis)
        for basis in sorted(mixed.clock_prior_n_dates or {})
        if basis != CLOCK_LEGACY
    }


def matched_control_check(claim_family: str, horizon: int,
                          root: Path | str | None = None,
                          clock_basis: str | None = None) -> PromotionResult:
    """P0d C5.1 — THE MATCHED-CONTROL GATE for a `matched_control_required` family.

    Such a family's AUTHORITY BASIS IS THE MATCHED CONTROL. This returns
    eligible=True only when ALL of the following hold on ONE explicit clock basis:
      * the family's control evidence clock has started (C3.1);
      * `control_coverage >= CONTROL_COVERAGE_MIN` (0.95) — C4.2;
      * `n_controlled_dates >= PROMOTION_MIN_DATES` (25) — C4.1/C5.1;
      * Wilson `ci_low > PROMOTION_MIN_CI_LOW` (0.5) on CONTROLLED rows only,
        direction-correct per P0c-1's rule (strict inequality; `direction=0` and
        missing legs excluded from numerator AND denominator).

    THERE IS NO BENCH FALLBACK, UNDER ANY DATA CONDITION (adversarial control
    #1). A required family whose bench-relative record would sail past the bar
    still refuses while its controls are missing — that is the entire point of
    the classification. Its benchmark-relative statistics remain computed and
    published as the labelled BASELINE by the track-record/readiness paths; they
    simply can never produce `ready=True` for it.

    TWO THINGS THIS FIXES THAT `promotion_check(control_only=True)` GOT WRONG:

    1. THE DENOMINATOR (census D0-3). The old path computed the control-only hit
       RATE over rows carrying control legs and then projected it onto `n_dates`
       counted over the WHOLE family — stating a Wilson interval at full-cohort N
       for a rate measured on a subset. With 37 controlled rows in a 100-row
       cohort it published an n=100 interval. Here the projection is onto
       `n_controlled_dates` and nothing else (C4.3), and the issued cohort stays
       VISIBLE: missing-control rows can never leave the denominator of coverage
       (adversarial control #6).

    2. THE COHORT (C3.2/C3.3). Evidence is PROSPECTIVE-ONLY. A claim joins the
       cohort only if it is directional, declares an explicit horizon unit, was
       registered at or after the clock start, and was forward-looking AT ITS OWN
       REGISTRATION STAMP (`_cohort_prospective`). So a later import of old-asof
       rows — even perfectly controlled ones — can never join the cohort, start
       the clock, or enter the N. Historical rows are untouched, never
       backfilled, never combined with cohort evidence.

    Refusals NAME their failing clause and print both date counts and the
    coverage. `clock_basis` names ONE basis explicitly (the per-market escape
    hatch, mirroring `promotion_check`'s parameter of the same name).
    """
    root = _root(root)
    clock = read_control_clock_start(claim_family, root)
    if clock is None:
        # C5.1 first refusal — and it is NEVER a miss, a zero, or a bench
        # substitute. "Has not begun" is the honest state of every required
        # family at the moment this contract registers (C9).
        return PromotionResult(
            eligible=False,
            reason=(f"claim_family={claim_family!r} horizon={horizon}d: "
                    f"matched-control evidence has not begun accruing for this "
                    f"family — the control evidence clock has not started; no "
                    f"bench substitute is evaluated (contract C5.1). The clock "
                    f"starts at the first prospective, control-carrying "
                    f"registration (C3.1)."),
            n_dates=0, ci_low=None,
            current_state=STATE_UNGRADED,
            evidence_basis=EVIDENCE_BASIS_MATCHED_CONTROL,
        )

    clock_start = str(clock.get("first_controlled_prospective_registration_utc") or "")
    try:
        clock_start_dt = datetime.fromisoformat(clock_start)
    except Exception:  # noqa: BLE001 — an unparseable clock admits NOBODY
        clock_start_dt = None

    claims = load_claims(root)
    cohort: dict[str, dict] = {}
    excluded_unresolvable = 0
    for c in claims:
        cid = c.get("claim_id")
        if not cid or c.get("is_placebo"):
            continue
        if _family_key(c, "family") != claim_family:
            continue
        if c.get("direction") not in (1, -1):        # C3.2(b) — directional only
            continue
        if claim_horizon_unit(c) is None:            # C3.2(c) — explicit clock only
            continue
        try:                                          # C3.2(d) — at/after the clock
            ts = datetime.fromisoformat(str(c.get("timestamp")))
        except Exception:  # noqa: BLE001
            excluded_unresolvable += 1
            continue
        if clock_start_dt is None or ts < clock_start_dt:
            continue
        # C3.2(e) — prospective AT ITS OWN REGISTRATION STAMP, never at "today".
        if not _cohort_prospective(c, ts.date()):
            excluded_unresolvable += 1
            continue
        cohort[str(cid)] = c

    grades = load_grades(root)
    rows = [g for g in grades
            if int(g.get("horizon_d", -1)) == horizon
            and str(g.get("claim_id")) in cohort]

    bases = sorted({grade_clock_basis(g) for g in rows})
    n_dates_by_basis: dict[str, int] = {
        b: len({_date_cluster(str(cohort[str(g.get("claim_id"))].get("asof", "")))
                for g in rows if grade_clock_basis(g) == b})
        for b in bases
    }
    basis = clock_basis or _authority_clock_basis(bases)
    if basis is None and bases:
        # Mirrors `promotion_check`'s refusal semantics exactly: a family
        # straddling two EXPLICIT bases has no non-arbitrary basis to promote on.
        # Reachable per basis by name (`clock_basis=...`), which is what
        # `emit_ladder_states` does with this result's `clock_prior_n_dates`.
        return PromotionResult(
            eligible=False,
            reason=(f"claim_family={claim_family!r} horizon={horizon}d: the "
                    f"matched-control cohort straddles {len(bases)} "
                    f"grading-clock bases ({', '.join(bases)}) with no single "
                    f"explicit clock to promote on — refusing to pool. Evaluate "
                    f"ONE basis by name (clock_basis=...) to promote per market."),
            n_dates=0, ci_low=None,
            current_state=STATE_MIXED_CLOCK,
            clock_basis=None,
            clock_prior_n_dates=n_dates_by_basis,
            evidence_basis=EVIDENCE_BASIS_MATCHED_CONTROL,
            control_clock_start=clock_start,
        )

    rows = [g for g in rows if grade_clock_basis(g) == basis]
    prior_n_dates = {b: n for b, n in n_dates_by_basis.items() if b != basis}

    # C4.1 — the issued cohort is the denominator, ALWAYS. Missing-control rows
    # stay in it; that is what coverage measures.
    n_cohort_rows = len(rows)
    n_cohort_dates = len({
        _date_cluster(str(cohort[str(g.get("claim_id"))].get("asof", ""))) for g in rows})
    controlled = [g for g in rows
                  if g.get("control_ret") is not None
                  and control_leg_is_valid(cohort[str(g.get("claim_id"))])]
    n_controlled_rows = len(controlled)
    n_controlled_dates = len({
        _date_cluster(str(cohort[str(g.get("claim_id"))].get("asof", "")))
        for g in controlled})

    unresolvable_note = (f" {excluded_unresolvable} claim(s) excluded as "
                         f"unresolvable (fail-closed, C3.2)."
                         if excluded_unresolvable else "")
    basis_note = (f" Evaluated on clock basis {basis!r}."
                  f" Cohort: {n_cohort_rows} row(s) / {n_cohort_dates} date(s);"
                  f" controlled: {n_controlled_rows} row(s) /"
                  f" {n_controlled_dates} date(s).{unresolvable_note}")
    common = {
        "evidence_basis": EVIDENCE_BASIS_MATCHED_CONTROL,
        "n_cohort_dates": n_cohort_dates,
        "n_controlled_dates": n_controlled_dates,
        "n_cohort_rows": n_cohort_rows,
        "n_controlled_rows": n_controlled_rows,
        "control_clock_start": clock_start,
        "clock_basis": basis,
        "clock_prior_n_dates": prior_n_dates,
    }

    if n_cohort_dates == 0:
        return PromotionResult(
            eligible=False,
            reason=(f"claim_family={claim_family!r} horizon={horizon}d: the "
                    f"matched-control cohort is EMPTY at this horizon/basis — "
                    f"accruing since {clock_start} (contract C5.1). No verdict, "
                    f"and no bench substitute.{basis_note}"),
            n_dates=0, ci_low=None,
            current_state=STATE_UNGRADED,
            control_coverage=None,
            **common,
        )

    coverage = round(n_controlled_dates / n_cohort_dates, 6)
    common["control_coverage"] = coverage

    # THE HIT ARITHMETIC — P0c-1's rule, verbatim, over CONTROLLED rows only.
    hits = 0
    graded = 0
    for g in controlled:
        if g.get("hit") is None:
            continue
        ctrl = g.get("control_ret")
        subj = g.get("subject_ret")
        if ctrl is None or subj is None:
            # A row that cannot be scored on the control leg is excluded from
            # numerator AND denominator — never converted into a miss and never
            # silently rescored on the bench-relative `hit` (P0c-1 §2/§3).
            continue
        direction = cohort[str(g.get("claim_id"))].get("direction")
        if not direction:
            # direction == 0 (salience): nothing to be right about. Excluded from
            # both, so a salience row can never manufacture a control hit
            # (adversarial control #3). Cohort membership already excludes these;
            # the check makes the invariant explicit rather than assumed.
            continue
        graded += 1
        # direction * (subject_ret - control_ret) > 0 — the mirrored rule, strict
        # so an exact-zero control excess is NOT a hit (adversarial control #2).
        if direction * (subj - ctrl) > 0:
            hits += 1

    # C4.3 — the interval is projected onto `n_controlled_dates` ONLY. Projecting
    # onto the full cohort's date count is census defect D0-3.
    if graded and n_controlled_dates:
        cluster_hits = int(round(hits / graded * n_controlled_dates))
        ci_low = wilson_ci_low(cluster_hits, n_controlled_dates)
    else:
        ci_low = None

    current_state = derive_state(n_controlled_dates)
    headline = {"n_dates": n_controlled_dates, "ci_low": ci_low,
                "current_state": current_state}

    if coverage < CONTROL_COVERAGE_MIN:
        return PromotionResult(
            eligible=False,
            reason=(f"accruing_with_missing_control: claim_family={claim_family!r} "
                    f"horizon={horizon}d has control_coverage={coverage} < "
                    f"{CONTROL_COVERAGE_MIN} required (contract C4.2) — "
                    f"{n_controlled_dates} controlled date(s) of {n_cohort_dates} "
                    f"cohort date(s). The uncovered cohort NEVER leaves the "
                    f"denominator, and no benchmark-relative record substitutes "
                    f"for the missing controls (C5.1).{basis_note}"),
            **headline, **common,
        )

    if n_controlled_dates < PROMOTION_MIN_DATES:
        return PromotionResult(
            eligible=False,
            reason=(f"accruing: claim_family={claim_family!r} horizon={horizon}d "
                    f"has n_controlled_dates={n_controlled_dates} < "
                    f"{PROMOTION_MIN_DATES} required (contract C5.1) at "
                    f"control_coverage={coverage} over {n_cohort_dates} cohort "
                    f"date(s). Need "
                    f"{PROMOTION_MIN_DATES - n_controlled_dates} more independent "
                    f"controlled date cluster(s).{basis_note}"),
            **headline, **common,
        )

    if ci_low is None:
        return PromotionResult(
            eligible=False,
            reason=(f"claim_family={claim_family!r} horizon={horizon}d: "
                    f"n_controlled_dates={n_controlled_dates} and "
                    f"control_coverage={coverage} clear their bars, but no "
                    f"directional control-leg hits were scorable (graded={graded}) "
                    f"— cannot compute a Wilson CI on the matched-control basis "
                    f"(contract C5.1).{basis_note}"),
            **headline, **common,
        )

    if ci_low <= PROMOTION_MIN_CI_LOW:
        pinned_reason = (
            f"claim_family={claim_family!r} horizon={horizon}d: matched-control "
            f"Wilson CI lower bound={ci_low:.4f} <= {PROMOTION_MIN_CI_LOW} "
            f"(coin-flip null) at n_controlled_dates={n_controlled_dates}. "
            f"Auto-demote one rung. Pinned as of {_now_iso()[:10]}.")
        return PromotionResult(
            eligible=False,
            reason=(f"matched-control Wilson CI lower bound {ci_low:.4f} <= "
                    f"{PROMOTION_MIN_CI_LOW} — the control-relative hit-rate "
                    f"interval does not clear a coin flip. AUTO-DEMOTE warranted. "
                    f"{pinned_reason}{basis_note}"),
            demote=True, pinned_reason=pinned_reason,
            **headline, **common,
        )

    return PromotionResult(
        eligible=True,
        reason=(f"MATCHED-CONTROL gate PASS at horizon={horizon}d: "
                f"n_controlled_dates={n_controlled_dates} >= {PROMOTION_MIN_DATES}, "
                f"control_coverage={coverage} >= {CONTROL_COVERAGE_MIN}, "
                f"Wilson CI lower bound={ci_low:.4f} > {PROMOTION_MIN_CI_LOW} on "
                f"controlled rows only (contract C5.1). Evidence accruing since "
                f"{clock_start}.{basis_note}"),
        **headline, **common,
    )


def _apply_policy_label(pr: "PromotionResult", policy: str,
                        classified: bool) -> "PromotionResult":
    """Stamp a BENCH-basis `PromotionResult` with its family's policy label.

    ONE implementation, shared by `promotion_check_dispatch` and every per-market
    sub-result the production paths publish beside it — an unlabelled sub-result
    under `by_clock_basis` is exactly the kind of side door through which a
    `not_applicable` family could publish an `eligible=True` cell (C5.3), or a
    benchmark verdict could be read as matched-control (C6.1).

    Mutates and returns `pr` (always a freshly-built object from
    `promotion_check`, never shared)."""
    if policy == CONTROL_POLICY_NOT_APPLICABLE:
        pr.eligible = False
        pr.demote = False
        pr.evidence_basis = EVIDENCE_BASIS_NOT_APPLICABLE
        pr.reason = ("not_applicable family (salience/descriptive) — no "
                     "directional promotion basis exists; magnitude grades vs "
                     "the placebo tape; " + pr.reason)
        return pr
    pr.evidence_basis = EVIDENCE_BASIS_BENCHMARK
    pr.unclassified = not classified
    return pr


def promotion_check_dispatch(claim_family: str, horizon: int,
                             root: Path | str | None = None) -> PromotionResult:
    """P0d C5 — THE PRODUCTION ENTRY POINT: dispatch by the family's POLICY.

    This is what replaces the blanket `promotion_check(control_only=True)` on
    every production path (C5.4). The basis is decided by the governed
    classification table alone and NEVER by data availability (C1.4): a
    `benchmark_only` family whose rows all happen to carry controls still
    evaluates benchmark-relative, and a `matched_control_required` family with
    zero controls still evaluates matched-control and fails closed. There is no
    "optional control" state to drift into.

      * `matched_control_required` -> `matched_control_check` (C5.1).
      * `benchmark_only` / unclassified -> today's `promotion_check(control_only=
        False)`, labelled `evidence_basis="benchmark"` (+ `unclassified`). P0c-2's
        legacy-cannot-originate-authority rule applies unchanged inside it (C5.2).
      * `not_applicable` -> no directional gate: the bench statistics are still
        computed as description, but eligibility is forced False and the verdict
        says so (C5.3). These are salience/descriptive species; they grade
        magnitude against the placebo tape, not direction against a control.
    """
    policy, classified = family_control_policy(claim_family)

    if policy == CONTROL_POLICY_REQUIRED:
        return matched_control_check(claim_family, horizon, root=root)

    pr = promotion_check(claim_family, horizon, root=root, control_only=False)
    return _apply_policy_label(pr, policy, classified)


def emit_ladder_states(root: Path | str | None = None,
                       families: list[str] | None = None) -> dict:
    """Run promotion_check at every GRADE_HORIZON for each claim_family found in
    claims.jsonl and emit the results into track_record.json under 'ladder_states'.

    Called by grade_qledger.py at end-of-collect so the ladder state is always
    current alongside the grade stats. Returns the per-family results dict.
    """
    root = _root(root)
    claims = load_claims(root)
    all_families = families or list({
        c.get("claim_family") or c.get("desk")
        for c in claims
        if not c.get("is_placebo") and (c.get("claim_family") or c.get("desk"))
    })

    results: dict[str, dict] = {}
    for fam in sorted(all_families):
        policy, classified = family_control_policy(fam)
        fam_res: dict[str, dict] = {}
        for h in GRADE_HORIZONS:
            # P0d C5.4: the blanket `control_only=True` call is GONE from
            # production. Which basis a family is evaluated on is decided by its
            # governed policy, and the verdict says which basis it used.
            pr = promotion_check_dispatch(fam, h, root=root)
            entry = pr.as_dict()
            # P0a MAJOR 2 (round 5): the pooled default refuses a bi-market
            # family as STATE_MIXED_CLOCK — correctly, it never pools — but
            # this is the production call path that gates SHADOW->CONFIRMER,
            # so a family stuck here never reaches promotion on EITHER market.
            # `by_clock_basis` adds each market's own verdict beside the
            # refused pooled one; nothing here is summed, and a family with a
            # single basis (today, every live family) carries no extra key.
            #
            # P0d: the per-market escape hatch keeps the family's OWN evidence
            # basis. A benchmark-basis family re-enters through
            # `promotion_check_by_market` (now `control_only=False` — production
            # no longer evaluates a control arm for a family whose policy is not
            # matched-control); a required family re-enters through
            # `matched_control_check(clock_basis=...)`, so nothing can slip back
            # onto a bench basis by taking the per-market route.
            if pr.current_state == STATE_MIXED_CLOCK:
                if policy == CONTROL_POLICY_REQUIRED:
                    per_market = {
                        b: matched_control_check(fam, h, root=root, clock_basis=b)
                        for b in sorted(pr.clock_prior_n_dates or {})
                        if b != CLOCK_LEGACY
                    }
                else:
                    per_market = {
                        b: _apply_policy_label(r, policy, classified)
                        for b, r in promotion_check_by_market(
                            fam, h, pr, root=root, control_only=False).items()
                    }
                if per_market:
                    entry["by_clock_basis"] = {b: r.as_dict()
                                               for b, r in per_market.items()}
            fam_res[str(h)] = entry
        results[fam] = fam_res

    # Merge into the existing track_record if it exists, else write fresh
    tr_path = root.joinpath(*_TRACK_FILE)
    payload: dict = {}
    if tr_path.exists():
        try:
            payload = json.loads(tr_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
    payload["ladder_states"] = results
    payload["ladder_states_at"] = _now_iso()
    tr_path.parent.mkdir(parents=True, exist_ok=True)
    tr_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return results
