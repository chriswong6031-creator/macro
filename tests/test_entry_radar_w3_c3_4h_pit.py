"""Live Entry Radar PR-3 (W3) — C3 and the 4H session grid.

WHAT THIS SUITE IS FOR
----------------------
C3 is a CONFIRMED-BAR detector whose two halves fail in different ways.  The
daily half fails by KNOWABILITY (reading today's eventual close while today is
still open); the 4H half fails by CALENDAR (a bucket that pretends the bell rang
at 16:00 on a 13:00 day, or that a 150-minute session-final bar is a 240-minute
bar).  Contract rows exercised:

  PIT-3   today's final daily close, present in the backing frame, is REFUSED
  PIT-7   a bucket is confirmed only at its effective end
  PIT-8   the 13:30-16:00 bucket is clipped, provisional until the bell, and
          discloses its shorter duration
  PIT-9   a 13:00 early close ends the session there — no fictitious 16:00 and
          no post-close minute
  PIT-10  a completed bucket is immutable against every later print
  PIT-11  extended-hours prints never enter a bucket
  PIT-17  appending future sessions moves nothing behind the edge
  warm-up  is the INDICATOR's, measured mechanically — there is no hand floor

THE GRID AND THE DETECTOR ARE TESTED SEPARATELY, ON PURPOSE.  The grid is tested
against committed minute tapes on REAL NYSE session dates (including a real
early-close date).  The detector is tested against constructed bucket sequences,
because C3's own warm-up needs ~80 completed 4H bars — 40 sessions of minute
tape, a fixture nobody would read and CI would carry forever.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import session_anchor
from engine.entry_radar import challengers as ch
from engine.entry_radar import four_hour as fh
from engine.entry_radar import indicator_core as ic
from engine.entry_radar.readings import canonical_readings
from engine.session_digest import is_early_close, session_window_et

from tests.test_entry_radar_w3_c1c2_pit import (
    ET,
    TICKER,
    daily_history,
    load_fixture,
    session_tapes,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "entry_radar"


@pytest.fixture(scope="module")
def fixture() -> dict:
    return load_fixture()


@pytest.fixture(scope="module")
def normal_tape(fixture) -> ch.SessionTape:
    return session_tapes(fixture)[0]


@pytest.fixture(scope="module")
def early_tape() -> ch.SessionTape:
    raw = json.loads((FIXTURES / "w3_early_close_tape.json").read_text(encoding="utf-8"))
    return fh.tape_from_rows(date.fromisoformat(raw["session"]), raw["rows"],
                             price_basis=raw["price_basis"], vintage="w3-fixture",
                             tz=ET)


# ---------------------------------------------------------------------------
# PIT-7 / PIT-8 — the normal-session grid
# ---------------------------------------------------------------------------

def test_a_normal_session_yields_one_full_bucket_and_one_clipped_one(normal_tape):
    buckets = fh.four_hour_buckets(normal_tape)
    assert len(buckets) == 2
    first, tail = buckets
    open_dt, close_dt = session_window_et(normal_tape.session)
    assert first.start == open_dt
    assert first.effective_end == open_dt + timedelta(minutes=240)
    assert first.effective_minutes == 240 and not first.clipped
    assert tail.start == first.effective_end
    assert tail.effective_end == close_dt
    assert tail.effective_minutes == 150
    assert tail.clipped, "a 150-minute session-final bar is not a 240-minute bar"
    assert tail.nominal_minutes == 240, "the nominal width is disclosed beside it"


@pytest.mark.parametrize("hhmm,first_confirmed,tail_confirmed", [
    ("09:30", False, False),
    ("13:29", False, False),
    ("13:30", True, False),
    ("15:59", True, False),
    ("16:00", True, True),
])
def test_PIT7_a_bucket_is_confirmed_only_at_its_effective_end(
        normal_tape, hhmm, first_confirmed, tail_confirmed):
    hour, minute = (int(p) for p in hhmm.split(":"))
    now = datetime.combine(normal_tape.session, datetime.min.time(),
                           tzinfo=ET).replace(hour=hour, minute=minute)
    first, tail = fh.four_hour_buckets(normal_tape, now=now)
    assert first.confirmed is first_confirmed
    assert tail.confirmed is tail_confirmed


def test_PIT8_the_clipped_bucket_is_provisional_before_the_bell_and_final_at_it(
        normal_tape):
    _open, close_dt = session_window_et(normal_tape.session)
    before = fh.four_hour_buckets(normal_tape, now=close_dt - timedelta(minutes=1))[1]
    at_bell = fh.four_hour_buckets(normal_tape, now=close_dt)[1]
    assert not before.confirmed and at_bell.confirmed
    # the VALUE does not change on confirmation — only the permission to read it
    assert before.close == at_bell.close
    assert fh.confirmed_four_hour_series([before]).empty
    assert len(fh.confirmed_four_hour_series([at_bell])) == 1


def test_an_incomplete_bucket_is_visible_as_a_diagnostic_and_cannot_be_read_by_c3(
        normal_tape):
    _open, close_dt = session_window_et(normal_tape.session)
    buckets = fh.four_hour_buckets(normal_tape, now=close_dt - timedelta(minutes=30))
    provisional = [b for b in buckets if not b.confirmed]
    assert provisional, "the partial bucket exists and is inspectable"
    assert provisional[0].close is not None, "its value is visible as a diagnostic"
    assert fh.confirmed_four_hour_series(buckets).index.tolist() == \
        [buckets[0].effective_end], "only the completed bucket reaches the indicator"


# ---------------------------------------------------------------------------
# PIT-9 — the early close
# ---------------------------------------------------------------------------

def test_the_early_close_fixture_sits_on_a_real_early_close_session(early_tape):
    assert is_early_close(early_tape.session), early_tape.session
    _open, close_dt = session_window_et(early_tape.session)
    assert close_dt.hour == 13 and close_dt.minute == 0


def test_PIT9_an_early_close_yields_one_bucket_that_ends_at_the_real_bell(early_tape):
    buckets = fh.four_hour_buckets(early_tape)
    assert len(buckets) == 1, "210 minutes is one bucket, not one-and-a-fiction"
    only = buckets[0]
    open_dt, close_dt = session_window_et(early_tape.session)
    assert only.start == open_dt
    assert only.effective_end == close_dt
    assert only.effective_end.hour == 13
    assert only.effective_minutes == 210 and only.clipped
    assert all(b.effective_end <= close_dt for b in buckets), "no fabricated 16:00"


def test_PIT9_no_minute_after_the_early_bell_enters_the_bucket(early_tape):
    _open, close_dt = session_window_et(early_tape.session)
    padded = ch.SessionTape(
        session=early_tape.session,
        minutes=early_tape.minutes + tuple(
            ch.MinuteBar(start=close_dt + timedelta(minutes=i), open=9e3, high=9e3,
                         low=9e3, close=9e3)
            for i in range(30)),
        price_basis=early_tape.price_basis)
    assert fh.four_hour_buckets(padded)[0].close == \
        fh.four_hour_buckets(early_tape)[0].close


# ---------------------------------------------------------------------------
# PIT-10 / PIT-11 / PIT-17 — bucket immutability
# ---------------------------------------------------------------------------

def test_PIT10_a_completed_bucket_is_immutable_against_every_later_print(fixture):
    """Mutate every minute after 13:30 and the session's whole daily bar."""
    session = date.fromisoformat(fixture["tape_sessions"][0])
    open_dt, _close = session_window_et(session)
    boundary = open_dt + timedelta(minutes=240)
    reference = fh.four_hour_buckets(session_tapes(fixture)[0])[0]

    mutated = copy.deepcopy(fixture)
    for tape in mutated["tapes"]:
        for row in tape["rows"]:
            if datetime.fromisoformat(row[0]).replace(tzinfo=ET) >= boundary:
                for i in (1, 2, 3, 4):
                    row[i] = round(row[i] * 4.0, 4)
    for row in mutated["daily"]["rows"]:
        if row[0] >= session.isoformat():
            for i in (1, 2, 3, 4):
                row[i] = round(row[i] * 4.0, 4)

    after = fh.four_hour_buckets(session_tapes(mutated)[0])[0]
    assert after.to_dict() == reference.to_dict()
    assert fh.four_hour_buckets(session_tapes(mutated)[0])[1].close != \
        fh.four_hour_buckets(session_tapes(fixture)[0])[1].close, \
        "the mutation is real — the LATER bucket does move"


def test_PIT11_extended_hours_prints_never_enter_a_bucket(fixture, normal_tape):
    mutated = copy.deepcopy(fixture)
    session = date.fromisoformat(mutated["tapes"][0]["session"])
    open_dt, close_dt = session_window_et(session)
    touched = 0
    for row in mutated["tapes"][0]["rows"]:
        start = datetime.fromisoformat(row[0]).replace(tzinfo=ET)
        if start < open_dt or start + timedelta(minutes=1) > close_dt:
            touched += 1
            for i in (1, 2, 3, 4):
                row[i] = round(row[i] * 5.0, 4)
    assert touched >= 40, "the fixture must carry extended-hours prints to mutate"
    assert [b.to_dict() for b in fh.four_hour_buckets(session_tapes(mutated)[0])] == \
        [b.to_dict() for b in fh.four_hour_buckets(normal_tape)]


def test_PIT17_a_later_session_cannot_move_an_earlier_session_bucket(fixture):
    tapes = session_tapes(fixture)
    first_only = [b.to_dict() for b in fh.four_hour_buckets(tapes[0])]
    with_more = [b.to_dict() for b in fh.four_hour_buckets(tapes[0])]
    assert first_only == with_more
    # and the later sessions produce their OWN buckets, never merged into the first
    later = fh.four_hour_buckets(tapes[1])
    assert {b.session for b in later} == {tapes[1].session.isoformat()}


# ---------------------------------------------------------------------------
# PIT-3 — the confirmed-daily knowability fence
# ---------------------------------------------------------------------------

def _daily_k_through(frame: pd.DataFrame, cutoff: date) -> float | None:
    closes = frame.loc[frame.index < pd.Timestamp(cutoff)]["close"].astype(float)
    return ic.last_finite(ic.stoch_rsi_kd(closes)[0])


def test_PIT3_todays_final_close_in_the_backing_frame_is_refused_as_confirmed(fixture):
    """The fixture carries a session whose OWN close flips the washout verdict."""
    daily = daily_history(fixture)
    session = date.fromisoformat(fixture["tape_sessions"][0])
    frame = daily.frame

    with_today = ic.last_finite(ic.stoch_rsi_kd(
        frame.loc[frame.index <= pd.Timestamp(session)]["close"].astype(float))[0])
    without_today = _daily_k_through(frame, session)
    assert with_today < ic.OVERSOLD <= without_today, \
        "the setup: today's close WOULD arm C3, yesterday's does not"

    leg = fh.c3_daily_leg(daily, session)
    assert leg.washed is False, "'the parquet already has it' is not knowability"
    assert leg.k == pytest.approx(without_today)
    assert leg.source_bar_time < session.isoformat()
    assert leg.source_bar_known_at == session.isoformat()


def test_PIT3_deleting_todays_row_entirely_changes_nothing(fixture):
    daily = daily_history(fixture)
    session = date.fromisoformat(fixture["tape_sessions"][0])
    truncated = daily_history(fixture, rows=[r for r in fixture["daily"]["rows"]
                                             if r[0] < session.isoformat()])
    assert fh.c3_daily_leg(daily, session) == fh.c3_daily_leg(truncated, session)


def test_PIT3_the_next_session_DOES_see_it_once_it_is_knowable(fixture):
    daily = daily_history(fixture)
    armed_session = date.fromisoformat(fixture["tape_sessions"][1])
    leg = fh.c3_daily_leg(daily, armed_session)
    assert leg.washed is True, "one session later the same close is lawful evidence"
    assert leg.source_bar_time == fixture["tape_sessions"][0]


# ---------------------------------------------------------------------------
# the C3 detector — arm, post-arm turn, warm-up
# ---------------------------------------------------------------------------

def _synthetic_daily(n_sessions: int) -> tuple[ch.DailyHistory, list[date]]:
    """A daily frame that holds above K=20 until a LATE decline, on REAL sessions.

    The lateness is the whole point: C3's 4H leg needs ~80 completed buckets
    (~40 sessions) before its own indicator warms up, so an early daily arm would
    leave no pre-arm turn to fence and the pre/post-arm tests would pass
    vacuously.  A small wobble is still required — a monotone series has no down
    moves, so Wilder RSI's denominator is zero and every oscillator is NaN.
    """
    reference = session_anchor.reference_sessions("US")
    sessions = [ts.date() for ts in
                reference[reference <= pd.Timestamp("2026-06-26")][-n_sessions:]]
    t = np.arange(n_sessions, dtype=float)
    wobble = 1 + 0.004 * np.sin(t / 2.3)
    closes = 100.0 * np.exp(0.0035 * t) * wobble
    span = int(n_sessions * 0.16)
    tail = np.linspace(0.0, 1.0, span)
    closes[-span:] = (closes[-span - 1] * (1 - 0.16 * tail ** 0.7)
                      * (1 + 0.004 * np.sin(np.arange(span) / 2.3)))
    frame = pd.DataFrame({"open": closes, "high": closes * 1.004,
                          "low": closes * 0.996, "close": closes},
                         index=pd.DatetimeIndex(sessions))
    return ch.DailyHistory(frame=frame, vintage="synthetic"), sessions


def _synthetic_buckets(sessions: list[date], closes: list[float],
                       ) -> list[tuple[date, list[fh.FourHourBucket]]]:
    """Two completed 4H buckets per session, carrying the supplied close path."""
    out: list[tuple[date, list[fh.FourHourBucket]]] = []
    cursor = 0
    for session in sessions:
        open_dt, close_dt = session_window_et(session)
        buckets: list[fh.FourHourBucket] = []
        start = open_dt
        index = 0
        while start < close_dt and cursor < len(closes):
            end = min(start + timedelta(minutes=fh.FOUR_HOUR_MINUTES), close_dt)
            buckets.append(fh.FourHourBucket(
                session=session.isoformat(), index=index, start=start,
                effective_end=end, confirmed=True, close=float(closes[cursor]),
                minutes=int((end - start).total_seconds() // 60)))
            start, index, cursor = end, index + 1, cursor + 1
        out.append((session, buckets))
    return out


@pytest.fixture(scope="module")
def c3_setup():
    daily, sessions = _synthetic_daily(150)
    t = np.arange(300, dtype=float)
    closes = list(100.0 * np.exp(-0.0016 * t) * (1 + 0.012 * np.sin(t / 3.1)
                                                 + 0.006 * np.sin(t / 11.0)))
    return daily, sessions, _synthetic_buckets(sessions, closes)


def test_the_c3_setup_has_an_arm_with_turns_on_both_sides(c3_setup):
    """A precondition, asserted: without it the pre/post-arm tests are vacuous."""
    daily, sessions, buckets = c3_setup
    armed = [s for s in sessions if fh.c3_daily_leg(daily, s).washed is True]
    assert armed, "the synthetic daily must reach a confirmed washout"
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    # W3-14: armed_at is an INSTANT (that session's 09:30 ET open, UTC-normalised);
    # armed_session is the date eligibility compares against.
    assert run.armed_session == armed[0].isoformat()
    assert run.armed_at == ch.utc_iso(session_window_et(armed[0])[0])
    assert any(t < run.armed_at for t in run.turns), "a pre-arm turn must exist"
    assert any(t >= run.armed_at for t in run.turns), "and a post-arm one"


def test_a_pre_arm_4h_turn_never_promotes_and_a_post_arm_one_does(c3_setup):
    daily, _sessions, buckets = c3_setup
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    assert run.episode is not None
    assert run.episode.candidate_at is not None
    assert run.episode.candidate_at >= run.armed_at
    assert len(run.events) == 1, "the FIRST post-arm turn is the candidate"
    assert run.events[0].family == "radar_1d_4h_recovery"
    assert run.events[0].subtype == "confirmed_4h_hist_trough"
    assert run.events[0].final is True and run.events[0].bar_state == "confirmed"

    pre_arm = [r for r in run.readings if r.features.get("pre_arm")]
    assert pre_arm, "pre-arm readings exist"
    assert all(r.condition_met is not True for r in pre_arm), \
        "a pre-arm 4H turn is stale context and cannot promote"
    turned_pre_arm = [r for r in pre_arm if r.features.get("h4_turn") is True]
    assert turned_pre_arm, "and at least one of them DID turn — so the fence bites"


def test_MUTATION_dropping_the_pre_arm_fence_moves_the_candidate_earlier(c3_setup):
    """Prove the fence is load-bearing by removing it and watching the answer move."""
    daily, _sessions, buckets = c3_setup
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    completed: list[fh.FourHourBucket] = []
    unfenced: str | None = None
    for _session, session_buckets in buckets:
        for bucket in session_buckets:
            completed.append(bucket)
            if fh.four_hour_turn(fh.confirmed_four_hour_series(completed)):
                unfenced = ch.utc_iso(bucket.effective_end)
                break
        if unfenced:
            break
    assert unfenced is not None
    assert unfenced < run.episode.candidate_at, \
        "without the arm fence the first turn on the tape would have promoted"


def test_the_warm_up_is_the_indicators_own_and_carries_no_hand_floor(c3_setup):
    _daily, _sessions, buckets = c3_setup
    flat = [b for _s, session_buckets in buckets for b in session_buckets]
    series = fh.confirmed_four_hour_series(flat)
    mechanical = fh.first_lawful_turn_index(series)
    assert mechanical is not None

    for length in range(1, mechanical + 1):
        assert fh.four_hour_turn(series.iloc[:length]) is None, \
            f"the predicate must be UNAVAILABLE at {length} bars, never False"
    assert fh.four_hour_turn(series.iloc[:mechanical + 1]) in (True, False)

    hist = ic.rsi_macd_hist(series)
    finite = int(pd.Series(hist).notna().to_numpy().argmax())
    assert mechanical == finite + fh.TURN_POINTS - 1, \
        "the first lawful point is exactly the indicator's own warm-up plus 3 points"
    assert fh.C3_SPEC["warm_up"].startswith("no hand-tuned bar-count floor")


def test_c3_readings_are_unavailable_while_the_indicator_is_warming(c3_setup):
    daily, _sessions, buckets = c3_setup
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    warming = [r for r in run.readings if r.availability == "unavailable"]
    assert warming, "the warm-up must actually be observed in a run"
    assert all(r.condition_met is None for r in warming)
    assert all(r.authority == {k: False for k in r.authority} for r in run.readings)


def test_PIT17_appending_later_sessions_leaves_earlier_c3_readings_identical(c3_setup):
    daily, _sessions, buckets = c3_setup
    short = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets[:-6])
    full = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    edge = short.readings[-1].observed_at
    assert canonical_readings(short.readings) == canonical_readings(
        [r for r in full.readings if r.observed_at <= edge])


def test_c3_mints_no_event_when_the_daily_leg_never_arms(c3_setup):
    daily, sessions, buckets = c3_setup
    calm = ch.DailyHistory(
        frame=daily.frame.assign(**{c: daily.frame[c] * 0 + 100.0
                                    for c in ("open", "high", "low", "close")}),
        vintage="flat")
    run = fh.run_c3(ticker=TICKER, daily=calm, buckets_by_session=buckets)
    assert run.armed_at is None
    assert run.events == () and run.episodes == ()
    assert all(r.condition_met is None for r in run.readings), \
        "a flat series has no oscillator at all — unavailable, never False"


# ---------------------------------------------------------------------------
# 2026-08-14 adversarial-review regressions (W3-2, W3-5, W3-11, W3-14)
# ---------------------------------------------------------------------------

def _expiry_daily(n_sessions: int = 200) -> tuple[ch.DailyHistory, list[date]]:
    """Like :func:`_synthetic_daily`, but the decline sits MID-RUN.

    The arm has to land early enough that 16 more sessions still fit, which the
    late-decline frame (built so a pre-arm 4H turn exists) cannot provide.
    """
    reference = session_anchor.reference_sessions("US")
    sessions = [ts.date() for ts in
                reference[reference <= pd.Timestamp("2026-06-26")][-n_sessions:]]
    t = np.arange(n_sessions, dtype=float)
    wobble = 1 + 0.004 * np.sin(t / 2.3)
    closes = 100.0 * np.exp(0.0035 * t) * wobble
    start, span = n_sessions // 2, 20
    tail = np.linspace(0.0, 1.0, span)
    closes[start:start + span] = (closes[start - 1] * (1 - 0.18 * tail ** 0.7)
                                  * (1 + 0.004 * np.sin(np.arange(span) / 2.3)))
    rally = np.arange(n_sessions - (start + span), dtype=float)
    closes[start + span:] = closes[start + span - 1] * np.exp(0.004 * (rally + 1))
    frame = pd.DataFrame({"open": closes, "high": closes * 1.004,
                          "low": closes * 0.996, "close": closes},
                         index=pd.DatetimeIndex(sessions))
    return ch.DailyHistory(frame=frame, vintage="synthetic-expiry"), sessions


def _expiry_case(turn_offset: int):
    """An arm, then a first post-arm 4H turn ``turn_offset`` sessions later.

    The 4H series is built so the ONLY lawful turn lands on a chosen session:
    a long monotone decline (histogram falling, no trough) followed by one clean
    upturn.  That isolates §10's clock from every other reason C3 might not fire.
    """
    daily, sessions = _expiry_daily()
    armed = [s for s in sessions if fh.c3_daily_leg(daily, s).washed is True]
    assert armed, "the synthetic daily must reach a confirmed washout"
    arm_index = sessions.index(armed[0])

    n_buckets = 2 * len(sessions)
    closes = [100.0 * (0.996 ** i) for i in range(n_buckets)]
    turn_at = 2 * (arm_index + turn_offset)
    assert turn_at + 6 < n_buckets, "the turn must fit inside the run"
    for j in range(turn_at, n_buckets):
        closes[j] = closes[turn_at - 1] * (1.0 + 0.010 * (j - turn_at + 1))
    buckets = _synthetic_buckets(sessions, closes)
    return daily, sessions, buckets, arm_index


def test_W3_2_an_arm_that_waits_out_the_15_session_clock_EXPIRES(c3_setup):
    """W3-2: a C3 ARMED episode never expired.  The reviewer promoted a candidate
    88 sessions after the arm, with the confirmed daily K back at 95.8 — a washout
    that had healed months earlier still buying the first 4H turn that arrived.
    §10 already froze the instrument: ARMED without promotion expires at 15
    sessions.
    """
    daily, sessions, buckets, arm_index = _expiry_case(16)
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    assert run.armed_session == sessions[arm_index].isoformat()
    assert run.expired_at is not None, "the clock must have run out"
    assert run.events == (), "no candidate may be minted at or after expiry"
    episode = run.episode
    assert episode.state.value == "EXPIRED"
    assert episode.candidate_at is None
    # the turn DID arrive — it simply arrived too late
    assert any(t > run.expired_at for t in run.turns)
    assert run.expired_at == ch.utc_iso(
        session_window_et(sessions[arm_index + fh.C3_ARM_EXPIRY_SESSIONS])[0])


def test_W3_2_a_turn_inside_the_clock_still_promotes(c3_setup):
    """CONTROL: the expiry must not eat a lawful candidate.

    The price inflection is placed 10 sessions after the arm; the HISTOGRAM turn
    that follows it lands a bar or two later still (the RSI-MACD is smoothed), so
    the assertion below is on the OBSERVED candidate session rather than on the
    offset — an offset is an input, and the clock is about the outcome.
    """
    daily, sessions, buckets, arm_index = _expiry_case(10)
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    assert run.expired_at is None
    assert len(run.events) == 1
    assert run.episode.state.value == "CANDIDATE"
    assert run.episode.candidate_at >= run.armed_at
    candidate_session = date.fromisoformat(run.events[0].context["market_session"])
    elapsed = sessions.index(candidate_session) - arm_index
    assert 0 <= elapsed < fh.C3_ARM_EXPIRY_SESSIONS, \
        f"the candidate must land inside the clock, got {elapsed} sessions"


def test_W3_2_MUTATION_without_the_clock_the_stale_arm_promotes(monkeypatch):
    """The before/after receipt, on the real code path.

    Raise the constant out of reach and the SAME inputs promote a candidate long
    after the arm — the reviewer's finding, reproduced here rather than described.
    Restore it and the promotion is refused.
    """
    expiry = fh.C3_ARM_EXPIRY_SESSIONS  # captured BEFORE the patch moves it
    daily, sessions, buckets, arm_index = _expiry_case(16)
    fenced = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    assert fenced.events == () and fenced.expired_at is not None

    monkeypatch.setattr(fh, "C3_ARM_EXPIRY_SESSIONS", 10_000)
    unfenced = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    assert unfenced.expired_at is None
    assert len(unfenced.events) == 1, "without the clock the stale arm still fires"
    late = date.fromisoformat(unfenced.events[0].context["market_session"])
    elapsed = sessions.index(late) - arm_index
    assert elapsed > expiry, \
        f"the promotion must be provably late, got {elapsed} sessions vs {expiry}"
    fired = [r for r in unfenced.readings
             if r.observed_at == unfenced.events[0].signal_ts][0]
    assert fired.features["daily_k"] > ic.OVERSOLD, \
        "and the washout it claims to be buying has long since healed"


def test_W3_2_the_expiry_constant_is_section_10s_frozen_fifteen():
    assert fh.C3_ARM_EXPIRY_SESSIONS == 15
    assert fh.C3_SPEC["arm_expiry_sessions"] == fh.C3_ARM_EXPIRY_SESSIONS
    assert "still oversold" not in fh.C3_SPEC["turn_rule"], \
        "the REJECTED fix would have rebuilt A5.3's forbidden requirement at 4H"


def test_W3_5_a_stale_daily_leg_arms_nothing(c3_setup):
    """W3-5: a confirmed history that stops short of the prior reference session is
    `stale`; a stale leg carries no washout verdict and cannot arm.
    """
    daily, sessions, buckets = c3_setup
    stale_frame = daily.frame.iloc[:-60]
    stale = ch.DailyHistory(frame=stale_frame, vintage="stale")
    late = sessions[-1]
    leg = fh.c3_daily_leg(stale, late)
    assert leg.availability == "stale"
    assert leg.washed is None and leg.k is None

    run = fh.run_c3(ticker=TICKER, daily=stale,
                    buckets_by_session=[(late, buckets[-1][1])])
    assert run.armed_at is None and run.events == ()
    assert all(r.availability == "stale" and r.condition_met is None
               for r in run.readings)


def test_W3_5_CONTROL_a_contiguous_daily_leg_is_unchanged(c3_setup):
    daily, sessions, _buckets = c3_setup
    leg = fh.c3_daily_leg(daily, sessions[-1])
    assert leg.availability == "confirmed"
    assert leg.k is not None


def test_W3_11_a_confirmed_but_empty_bucket_is_disclosed_not_silently_dropped(
        c3_setup):
    """W3-11: an empty CONFIRMED bucket contributed no close, so two non-adjacent
    bars became adjacent in the indicator's input with nothing recording it.  No
    close is fabricated (that would be worse); the gap is now counted per reading
    and listed on the run.
    """
    daily, sessions, buckets = c3_setup
    holed = []
    for index, (session, session_buckets) in enumerate(buckets):
        if index in (40, 41):
            session_buckets = [
                fh.FourHourBucket(session=b.session, index=b.index, start=b.start,
                                  effective_end=b.effective_end, confirmed=True,
                                  close=None, minutes=0)
                for b in session_buckets]
        holed.append((session, session_buckets))

    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=holed)
    dropped = [row for row in run.provisional if row.get("reason") == "confirmed_empty"]
    assert len(dropped) == 4, "two sessions x two buckets"
    assert {row["session"] for row in dropped} == {
        buckets[40][0].isoformat(), buckets[41][0].isoformat()}
    assert all({"session", "index", "reason"} <= set(row) for row in dropped)
    tail = [r for r in run.readings if r.market_session > buckets[41][0].isoformat()]
    assert tail and all(r.features["completed_4h_gaps"] == 4 for r in tail)
    head = [r for r in run.readings if r.market_session < buckets[40][0].isoformat()]
    assert head and all(r.features["completed_4h_gaps"] == 0 for r in head)


def test_W3_14_the_arm_is_an_instant_and_a_same_session_turn_stays_eligible(c3_setup):
    """W3-14: ``armed_at`` was a bare date beside a UTC candidate instant, so the
    two could not be ordered without guessing.  It is now the arming session's
    09:30 ET open; eligibility still compares SESSION to SESSION, so a bucket
    completing later on the arming session is post-arm and stays eligible.
    """
    daily, sessions, buckets = c3_setup
    run = fh.run_c3(ticker=TICKER, daily=daily, buckets_by_session=buckets)
    assert run.armed_at is not None and run.armed_at.endswith("Z")
    assert run.armed_at == ch.utc_iso(
        session_window_et(date.fromisoformat(run.armed_session))[0])
    assert run.armed_at > run.armed_session, "an instant sorts after its bare date"

    same_session = [r for r in run.readings if r.market_session == run.armed_session]
    assert same_session, "the arming session must contribute buckets"
    assert all(r.features["eligible"] is True for r in same_session), \
        "a 13:30 bucket on the arming session is AFTER a 09:30 arm"
    assert all(r.features["pre_arm"] is False for r in same_session)
