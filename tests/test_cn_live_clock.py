"""CN-PR-0 — the mainland session-state contract + calendar threading.

Pins the three foundations the CN Breathing Platform evaluator will stand on
(research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md §2/§4):

  * engine.prophet_live.cn_clock — phases (lunch is session_break, not stale),
    per-board daily-limit bands (301xxx.SZ IS ChiNext — a ±20% name misread as
    ±10% gets a FALSE limit_up_locked at +10% with its tape still running), and
    the delay-aware quote-age anchor (with the 15-min spark floor, an 11:29 CST
    print at 13:02 CST is the freshest print that exists — bare wall-clock age
    darks the whole board for the first delay-floor minutes of every afternoon).
  * lib.cn_calendar.sessions_behind — sessions, not calendar days, with the
    17:00 CST settle buffer (a store is not "behind" on the morning of a session
    whose bar cannot exist yet).
  * engine.prophet_live.armed_pack calendar threading — calendar=None IS the
    NYSE path (the US suite proves it byte-unchanged); a module exposing
    is_session() places the probe's appended bar on that market's calendar,
    across Golden Week, not on a weekday guess.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from engine.prophet_live import armed_pack, cn_clock
from lib import cn_calendar

UTC = timezone.utc


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


# 2026-08-18 is a Tuesday with no mainland holiday.
SESSION_DAY = "2026-08-18"


# ─────────────────────────────────────────────────────────────────────────────
# Phases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("utc_hhmm,expected", [
    ("00:30", "closed"),            # 08:30 CST — before pre-open
    ("01:12", "pre_open"),          # 09:12 CST
    ("01:20", "pre_open"),          # 09:20 CST — opening auction folds into pre_open
    ("01:31", "morning"),           # 09:31 CST
    ("03:29", "morning"),           # 11:29 CST
    ("03:31", "session_break"),     # 11:31 CST — lunch, NOT stale
    ("04:59", "session_break"),     # 12:59 CST
    ("05:01", "afternoon"),         # 13:01 CST
    ("06:56", "afternoon"),         # 14:56 CST
    ("06:58", "closing_auction"),   # 14:58 CST
    ("07:05", "post_close"),        # 15:05 CST — close pass window
    ("07:20", "closed"),            # 15:20 CST — past the honesty deadline
])
def test_phase_table_on_a_session_day(utc_hhmm: str, expected: str) -> None:
    assert cn_clock.phase(_dt(f"{SESSION_DAY}T{utc_hhmm}:00")) == expected


def test_weekend_and_holiday_phases() -> None:
    assert cn_clock.phase(_dt("2026-08-15T02:00:00")) == "weekend"   # Saturday
    # National Day is a mainland closure every year; 2026-10-01 falls midweek.
    assert not cn_calendar.is_session(date(2026, 10, 1))
    assert cn_clock.phase(_dt("2026-10-01T02:00:00")) == "holiday"


def test_lunch_is_a_freeze_phase_and_trading_is_not() -> None:
    assert "session_break" in cn_clock.FREEZE_PHASES
    assert "pre_open" in cn_clock.FREEZE_PHASES
    assert "closing_auction" in cn_clock.FREEZE_PHASES
    assert cn_clock.TRADING_PHASES == frozenset({"morning", "afternoon"})
    assert cn_clock.TRADING_PHASES.isdisjoint(cn_clock.FREEZE_PHASES)


# ─────────────────────────────────────────────────────────────────────────────
# Daily limit bands + lock detection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ticker,expected", [
    ("688111.SS", 20.0),   # STAR
    ("689009.SS", 20.0),   # STAR-listed CDR
    ("300750.SZ", 20.0),   # ChiNext
    ("301269.SZ", 20.0),   # ChiNext post-registration-reform — the miss that
                           # would have stamped a false lock at +10%
    ("302132.SZ", 20.0),   # newest ChiNext range
    ("600519.SS", 10.0),   # SSE main board
    ("000001.SZ", 10.0),   # SZSE main board
    ("^HSI", None),        # not a mainland single name
    ("0700.HK", None),
    ("AAPL", None),
    (None, None),
])
def test_limit_pct_for(ticker, expected) -> None:
    assert cn_clock.limit_pct_for(ticker) == expected


def test_limit_lock_status_up_down_and_tolerance() -> None:
    # Main board: prev 10.00 → band edge 11.00; exchange rounds to the fen.
    assert cn_clock.limit_lock_status(11.00, 10.00, 10.0) == cn_clock.LIMIT_UP_LOCKED
    assert cn_clock.limit_lock_status(10.99, 10.00, 10.0) == cn_clock.LIMIT_UP_LOCKED
    assert cn_clock.limit_lock_status(9.00, 10.00, 10.0) == cn_clock.LIMIT_DOWN_LOCKED
    assert cn_clock.limit_lock_status(10.50, 10.00, 10.0) is None
    # A 301xxx ChiNext name trading at exactly +10% is NOT locked — its band is 20%.
    pct = cn_clock.limit_pct_for("301269.SZ")
    assert cn_clock.limit_lock_status(11.00, 10.00, pct) is None
    assert cn_clock.limit_lock_status(12.00, 10.00, pct) == cn_clock.LIMIT_UP_LOCKED
    # Garbage in → no verdict, never a guess.
    assert cn_clock.limit_lock_status(None, 10.0, 10.0) is None
    assert cn_clock.limit_lock_status(11.0, 0.0, 10.0) is None
    assert cn_clock.limit_lock_status(11.0, 10.0, None) is None


# ─────────────────────────────────────────────────────────────────────────────
# Quote-age anchor (the CN-specific correctness core)
# ─────────────────────────────────────────────────────────────────────────────

def test_anchor_during_lunch_is_morning_close() -> None:
    anchor = cn_clock.expected_latest_quote_time(_dt(f"{SESSION_DAY}T04:02:00"))
    assert anchor == _dt(f"{SESSION_DAY}T03:30:00")


def test_anchor_pre_open_is_prior_session_close() -> None:
    anchor = cn_clock.expected_latest_quote_time(_dt(f"{SESSION_DAY}T01:00:00"))
    assert anchor == _dt("2026-08-17T07:00:00")   # Monday's 15:00 CST close


def test_anchor_after_close_is_todays_close() -> None:
    anchor = cn_clock.expected_latest_quote_time(_dt(f"{SESSION_DAY}T09:00:00"))
    assert anchor == _dt(f"{SESSION_DAY}T07:00:00")


def test_lunch_reopen_quote_is_fresh_under_the_delay_floor() -> None:
    # 13:02 CST, feed floor 15 min: the 11:29 CST print the vendor is actually
    # serving is ~1 minute old — the freshest print that exists.
    age = cn_clock.quote_age_min(_dt(f"{SESSION_DAY}T03:29:00"),
                                 _dt(f"{SESSION_DAY}T05:02:00"),
                                 delay_floor_min=15.0)
    assert age is not None and age <= 2.0
    # Without the floor the same print reads ~93 min — the bug this pins against.
    bare = cn_clock.quote_age_min(_dt(f"{SESSION_DAY}T03:29:00"),
                                  _dt(f"{SESSION_DAY}T05:02:00"))
    assert bare is not None and bare > 90.0


def test_mid_afternoon_stale_quote_stays_stale_with_the_floor() -> None:
    # 14:30 CST, print from 10:15 CST: four hours behind a running tape.
    age = cn_clock.quote_age_min(_dt(f"{SESSION_DAY}T02:15:00"),
                                 _dt(f"{SESSION_DAY}T06:30:00"),
                                 delay_floor_min=15.0)
    assert age is not None and age > 200.0


def test_open_minutes_prior_close_is_fresh_and_live_print_clamps() -> None:
    # 09:32 CST with the floor: nothing newer than Monday's close is lawfully
    # expected yet, so that close is fresh…
    prior_close = _dt("2026-08-17T07:00:00")
    age = cn_clock.quote_age_min(prior_close, _dt(f"{SESSION_DAY}T01:32:00"),
                                 delay_floor_min=15.0)
    assert age is not None and age <= 1.0
    # …and a feed running AHEAD of the floor clamps to zero, never negative.
    live = cn_clock.quote_age_min(_dt(f"{SESSION_DAY}T01:31:30"),
                                  _dt(f"{SESSION_DAY}T01:32:00"),
                                  delay_floor_min=15.0)
    assert live == 0.0


def test_no_timestamp_is_not_fresh() -> None:
    assert cn_clock.quote_age_min(None, _dt(f"{SESSION_DAY}T02:00:00")) is None


def test_session_date_and_close_helpers() -> None:
    assert cn_clock.session_date(_dt(f"{SESSION_DAY}T02:00:00")).isoformat() == SESSION_DAY
    # Saturday resolves back to Friday's session.
    assert cn_clock.session_date(_dt("2026-08-15T02:00:00")).isoformat() == "2026-08-14"
    assert cn_clock.session_close_utc(_dt(f"{SESSION_DAY}T07:05:00")) == _dt(f"{SESSION_DAY}T07:00:00")
    assert cn_clock.post_close_deadline(_dt(f"{SESSION_DAY}T07:05:00")) == _dt(f"{SESSION_DAY}T07:15:00")


def test_last_completed_session_is_prior_through_a_live_pass() -> None:
    # All through Tuesday's session the pack must be Monday's (17:00 CST settle buffer).
    assert cn_clock.last_completed_session(_dt(f"{SESSION_DAY}T02:00:00")) == "2026-08-17"
    assert cn_clock.last_completed_session(_dt(f"{SESSION_DAY}T07:10:00")) == "2026-08-17"


# ─────────────────────────────────────────────────────────────────────────────
# lib.cn_calendar.sessions_behind
# ─────────────────────────────────────────────────────────────────────────────

def test_sessions_behind_semantics() -> None:
    # Store tip = Friday 08-14; queried Tuesday morning mid-session: Monday is the
    # only COMPLETED missing session — Tuesday's bar cannot exist yet.
    assert cn_calendar.sessions_behind(date(2026, 8, 14), _dt(f"{SESSION_DAY}T02:00:00")) == 1
    # Current store → 0; future-dated row → 0, never negative.
    assert cn_calendar.sessions_behind(date(2026, 8, 17), _dt(f"{SESSION_DAY}T02:00:00")) == 0
    assert cn_calendar.sessions_behind(date(2026, 8, 21), _dt(f"{SESSION_DAY}T02:00:00")) == 0
    # Weekend query: Friday-tipped store is current.
    assert cn_calendar.sessions_behind(date(2026, 8, 14), _dt("2026-08-15T10:00:00")) == 0


# ─────────────────────────────────────────────────────────────────────────────
# armed_pack calendar threading
# ─────────────────────────────────────────────────────────────────────────────

def test_next_session_stamp_default_is_nyse_and_cn_module_is_cn() -> None:
    # Default (None) = NYSE: the Friday-before-US-Labor-Day probe bar lands on
    # Tuesday (2026-09-07 is Labor Day).
    us = armed_pack.next_session_stamp(pd.Timestamp("2026-09-04"))
    assert us == pd.Timestamp("2026-09-08")
    # CN calendar: 2026-09-07 is an ordinary mainland Monday.
    cn = armed_pack.next_session_stamp(pd.Timestamp("2026-09-04"), cn_calendar)
    assert cn == pd.Timestamp("2026-09-07")


def test_next_session_stamp_crosses_golden_week_on_the_cn_calendar() -> None:
    tip = pd.Timestamp("2026-09-30")
    nxt = armed_pack.next_session_stamp(tip, cn_calendar)
    # Whatever the exact reopen date, it is a real session, strictly after the
    # closure, within the search horizon — never Oct 1-3.
    assert cn_calendar.is_session(nxt.date())
    assert nxt > tip
    assert (nxt - tip).days <= armed_pack._NEXT_SESSION_HORIZON_DAYS
    assert nxt.date() > date(2026, 10, 3)


def test_probe_series_appends_on_the_cn_calendar() -> None:
    idx = pd.DatetimeIndex([pd.Timestamp("2026-08-13"), pd.Timestamp("2026-08-14")])
    close = pd.Series([10.0, 10.5], index=idx, name="301269.SZ")
    probed = armed_pack.probe_series(close, 11.0, cn_calendar)
    assert len(probed) == 3
    assert probed.index[-1] == pd.Timestamp("2026-08-17")   # Monday, not Saturday
    assert probed.iloc[-1] == 11.0
    # The settled history is untouched — append, never replace (W-L0 #4982).
    assert list(probed.iloc[:2]) == [10.0, 10.5]


def test_session_lag_counts_cn_sessions_not_weekdays() -> None:
    # Friday bar against a Monday tip: one CN session apart, zero if same.
    assert armed_pack.session_lag("2026-08-14", "2026-08-17", cn_calendar) == 1
    assert armed_pack.session_lag("2026-08-17", "2026-08-17", cn_calendar) == 0
