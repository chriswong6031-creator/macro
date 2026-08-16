"""Live Entry Radar PR-4 (W4) — the point-in-time mutation battery.

WHAT THIS SUITE IS FOR
----------------------
Every other W4 suite asks whether the pass computes the right thing.  This one
asks the only question that can be answered by BREAKING something: at evaluation
instant T, can anything that becomes knowable after T change what the lane said
at T?  The answer has to be no for every channel through which the future could
leak, so each test below MUTATES one channel and asserts the readings at or
before T are byte-identical — with a CONTROL proving the mutation was real and
the assertion could have failed.

  PIT-W4-1   a journal tick appended AFTER T cannot move a reading at or before T
  PIT-W4-2   the eventual EOD bar — tomorrow's pack — cannot move yesterday's
             journal or its readings; a cross-pack re-derivation REFUSES
  PIT-W4-3   raw/adjusted disagreement (a 2:1 split) darks the name and mints
             nothing; CONTROL: agreeing bases fire
  PIT-W4-4   a stale confirmed history yields ``stale`` + None, never False
  PIT-W4-5   a missing interval carries forward with ``interval_had_bar=False``;
             a missing OPEN yields None and fabricates nothing
  PIT-W4-6   extended-hours prints are excluded and an out-of-window pass
             evaluates nothing at all
  PIT-W4-11  the full §10 re-arm chain: arm → candidate → resolve → lawful
             re-arm; a premature re-arm is REFUSED and RECORDED, the prior
             episode is never mutated, and the detector specs are untouched
  PIT-W4-12  one ticker occupies many lanes at once; nothing is flattened into a
             generic entry signal, and C4 structurally cannot fire

A NOTE ON WHAT IS *NOT* HERE.  PIT-W4-7/-8 (incomplete 4H buckets, early closes)
live in ``test_entry_radar_w4_c3_reader.py`` beside the reader that produces
them; -9/-10/-13/-15/-16/-17/-18 live in ``test_entry_radar_w4_live.py`` beside
the pass mechanics; -14/-19/-20 live in ``test_entry_radar_w4_liveness.py`` and
``test_entry_radar_w4_pack.py``.  The battery is split by WHERE THE DEFECT WOULD
BE, not by number, so a failure names the module that broke.

THE FIXTURES ARE SYNTHETIC AND SAY SO — the deterministic trend+ripple corpus
from ``test_entry_radar_w4_pack``, a hand-built quote book, and no network.
"""
from __future__ import annotations

import ast
import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.entry_radar import challengers as ch
from engine.entry_radar import detectors as dt
from engine.entry_radar import four_hour as fh
from engine.entry_radar import indicator_core as ic
from engine.entry_radar import live_eval as le
from engine.entry_radar import live_ledger as ll
from engine.entry_radar import live_pack as lp
from engine.entry_radar.readings import canonical_readings
from engine.session_digest import session_window_et
from tests.test_entry_radar_w4_live import (et_now, name_of, one_pass, quote_book,
                                            recovery_tape)
from tests.test_entry_radar_w4_pack import (AS_OF, NEXT_SESSION, build,
                                            frame_from_closes, washout_closes)

#: The six frozen detector identities.  RE-TYPED from the contract rather than
#: imported from the module under test — two independent copies is the point, and
#: an ``assert HASHES == HASHES`` proves nothing.
FROZEN_SPEC_HASHES = {
    "G0_GREY_DOT@1": "9be89a8acc8b905c",
    "C1_1D_LIVE_WASHOUT@1": "f0bbd6cf3a6e2339",
    "C2_1D_TURN@1": "d8ba60a25cfa7400",
    "C3_1D_4H_RECOVERY@1": "d54dc1e55c4261c8",
    "C4_MTF_TURN@1": "dce21ac680233ee2",
    "C5_BOTTOM_WATCH@1": "13dec66345a0376c",
}


@pytest.fixture(scope="module")
def pack() -> lp.LivePack:
    return build()


def _daily(pack: lp.LivePack, ticker: str = "WASH") -> ch.DailyHistory:
    return le.pack_daily_history(pack, ticker)


def _builder(pack: lp.LivePack, ticker: str = "WASH",
             session: date = NEXT_SESSION) -> le.IncrementalObservationBuilder:
    return le.IncrementalObservationBuilder(ticker=ticker, daily=_daily(pack, ticker),
                                            session=session)


def _tape(prices, *, session: date = NEXT_SESSION, step: int = 5,
          basis: str = ch.BASIS_ADJUSTED, skip: set[int] | None = None,
          ) -> ch.SessionTape:
    """A tape from a price list, one bar per ``step`` minutes from the open.

    ``skip`` drops the bar at those indices WITHOUT shifting the rest, which is
    how a missing interval is staged: the grid keeps its slot and the sampler has
    to decide what to do with a hole rather than with a shorter session.
    """
    open_dt, _close = session_window_et(session)
    skip = skip or set()
    minutes = tuple(ch.MinuteBar(start=open_dt + timedelta(minutes=step * i),
                                 open=p, high=p, low=p, close=p)
                    for i, p in enumerate(prices) if i not in skip)
    return ch.SessionTape(session=session, minutes=minutes, price_basis=basis,
                          vintage="w4-pit-fixture")


# ---------------------------------------------------------------------------
# PIT-W4-1 — a future tick cannot move a past reading
# ---------------------------------------------------------------------------

def test_PIT_W4_1_a_tick_appended_after_T_leaves_every_reading_at_or_before_T(pack):
    """The structural half of the no-leak law.

    ``sample_session_path`` admits a minute only when ``knowable_at <= end``, so a
    bar that starts after an interval's end cannot enter it — the guarantee is a
    property of the sampler, not of a filter somebody remembered to apply.  This
    test proves it end to end at the OBSERVATION level, which is where a future
    consumer would read it.
    """
    prices = [90.0, 89.5, 89.0, 88.5, 87.0, 86.0]
    builder = _builder(pack)
    cut = session_window_et(NEXT_SESSION)[0] + timedelta(minutes=20)

    before = builder.observations(_tape(prices[:4]), now=cut)
    after = _builder(pack).observations(_tape(prices), now=cut)

    assert before == after, "a later tick changed a reading at or before T"
    assert canonical_readings(ch.run_c1(before).readings) == \
           canonical_readings(ch.run_c1(after).readings)


def test_PIT_W4_1_CONTROL_a_tick_INSIDE_the_window_does_move_the_reading(pack):
    """The mutation control.  Without it the test above would pass on a sampler
    that ignored the tape entirely."""
    builder = _builder(pack)
    cut = session_window_et(NEXT_SESSION)[0] + timedelta(minutes=20)
    quiet = builder.observations(_tape([90.0, 90.0, 90.0, 90.0]), now=cut)
    moved = _builder(pack).observations(_tape([90.0, 90.0, 90.0, 75.0]), now=cut)
    assert quiet != moved
    assert quiet[-1].k != moved[-1].k


def test_PIT_W4_1_the_journal_REFUSES_the_only_mutation_the_sampler_cannot_stop(
        tmp_path, pack):
    """A BACKDATED tick would land inside an already-published interval."""
    journal = le.SessionJournal(tmp_path)
    record = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    base = et_now(30)
    journal.append_point(record, ts=base, price=90.0, basis="trade", source="polygon",
                         basis_audit={})
    frozen = copy.deepcopy(record.points)
    assert journal.append_point(record, ts=base - timedelta(minutes=10), price=50.0,
                                basis="trade", source="polygon", basis_audit={}) is False
    assert record.points == frozen
    assert record.refused and record.refused[0]["reason"] == "not_after_last_point"


# ---------------------------------------------------------------------------
# PIT-W4-2 — tomorrow's pack cannot move yesterday
# ---------------------------------------------------------------------------

def _corrected_pack() -> lp.LivePack:
    """Tomorrow's pack after a VENDOR CORRECTION to a confirmed close.

    The appended EOD bar turns out to be the WEAKER channel: ``confirmed_through``
    cuts strictly before the session under evaluation, so a bar AT or after that
    session cannot reach a reading no matter how many packs are built on top of
    it — a structural guarantee, asserted separately below.  The channel that
    CAN move a past reading is a correction to a bar the cut still includes, and
    that is what this pack stages: the same corpus with one prior close revised.
    """
    closes = washout_closes()
    closes[-4] = closes[-4] * 0.80
    frames = {"WASH": frame_from_closes(closes, AS_OF)}
    return lp.build_pack(probe_set=["WASH"],
                         store_reader=lambda t: frames.get(t), as_of=AS_OF,
                         built_at=datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc))


def test_PIT_W4_2_a_later_pack_cannot_move_the_session_it_closed(tmp_path, pack):
    """Yesterday's readings were computed on yesterday's substrate, and stay so.

    The live lane never re-derives a past session — it REPLAYS the journal — so
    even a corrected confirmed close cannot reach back.  The CONTROL is the
    second assertion: the corrected pack really would compute different readings
    for the same prices, so a re-derivation would have changed the answer and the
    verbatim replay is what prevents it.
    """
    journal = le.SessionJournal(tmp_path)
    record = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    tape = _tape([90.0, 89.0, 88.0, 87.0])
    frozen = _builder(pack).observations(tape)
    journal.freeze_observations(record, frozen)
    journal.flush(record)

    corrected = _corrected_pack()
    assert corrected.pack_hash != pack.pack_hash

    assert le.SessionJournal(tmp_path).replay(NEXT_SESSION.isoformat(), "WASH") == frozen

    recomputed = le.IncrementalObservationBuilder(
        ticker="WASH", daily=le.pack_daily_history(corrected, "WASH"),
        session=NEXT_SESSION).observations(tape)
    assert recomputed != frozen, (
        "the corrected pack computes the SAME observations — this fixture cannot "
        "distinguish a verbatim replay from a re-derivation")


def test_PIT_W4_2_an_EOD_bar_AT_the_session_is_cut_before_it_can_matter(pack):
    """The structural half: a bar at or after the evaluated session is never even
    loaded, so no number of later packs can move that session's readings."""
    closes = washout_closes()
    frames = {"WASH": frame_from_closes(closes + [closes[-1] * 0.60], NEXT_SESSION)}
    tomorrow = lp.build_pack(probe_set=["WASH"], store_reader=lambda t: frames.get(t),
                             as_of=NEXT_SESSION,
                             built_at=datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc))
    tape = _tape([90.0, 89.0, 88.0, 87.0])
    assert le.IncrementalObservationBuilder(
        ticker="WASH", daily=le.pack_daily_history(tomorrow, "WASH"),
        session=NEXT_SESSION).observations(tape) == _builder(pack).observations(tape)


def test_PIT_W4_2_a_cross_pack_re_derivation_of_TODAY_refuses(tmp_path, pack):
    journal = le.SessionJournal(tmp_path)
    record = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    journal.flush(record)
    corrected = _corrected_pack()
    with pytest.raises(le.LiveEvalError, match="backfill"):
        le.SessionJournal(tmp_path).open_session(
            session=NEXT_SESSION.isoformat(), ticker="WASH",
            pack_as_of=corrected.as_of, pack_hash=corrected.pack_hash,
            price_basis=corrected.price_basis)


def test_PIT_W4_2_the_pack_substrate_is_cut_STRICTLY_before_the_session(pack):
    """The knowability law made structural: while session D is open the confirmed
    history ends at D−1, so today's eventual close is never even loaded."""
    frame = pack.substrate["WASH"]
    assert pd.DatetimeIndex(frame.index).max() < pd.Timestamp(NEXT_SESSION)
    assert pd.DatetimeIndex(frame.index).max() == pd.Timestamp(AS_OF)


# ---------------------------------------------------------------------------
# PIT-W4-3 — the price-basis gate
# ---------------------------------------------------------------------------

def test_PIT_W4_3_a_two_for_one_split_darks_the_name_and_mints_nothing(pack):
    """A 2:1 split is the canonical raw/adjusted disagreement.

    The feed reports the RAW prior close (twice the adjusted one); the pack holds
    the adjusted. Concatenating the two halves fabricates a −50% move on the seam
    — which fabricates a cross and mints a candidate out of a corporate action.
    """
    now = et_now(37)
    book = quote_book(pack, multiple=0.97, ts=et_now(30))
    for row in book["quotes"].values():
        row["prevClose"] = float(row["prevClose"]) * 2.0
    result = one_pass(pack, book, now=now)

    wash = name_of(result, "WASH")
    assert wash.reasons == ("basis_mismatch",)
    assert wash.observations == () and wash.runs == ()
    assert result.payload["events"] == [] and result.payload["transitions"] == []
    assert abs(wash.basis["gap_pct"] - 100.0) < 1e-6


def test_PIT_W4_3_CONTROL_agreeing_bases_reach_the_engine_and_can_fire(pack):
    now = et_now(37)
    result = one_pass(pack, quote_book(pack, multiple=0.90, ts=et_now(30)), now=now)
    wash = name_of(result, "WASH")
    assert wash.state == "evaluated"
    assert wash.observations and wash.runs
    assert wash.basis["mismatch"] is False


def test_PIT_W4_3_a_disagreeing_TAPE_basis_voids_the_whole_observation(pack):
    """W3-1's other half: the check is not only on the prior close.  A tape
    fetched on a different basis voids %K as well as the ATR — the seam is
    between the two halves of the concatenated series, not in one field."""
    observations = _builder(pack).observations(
        _tape([90.0, 89.0, 88.0], basis=ch.BASIS_RAW))
    assert {o.availability for o in observations} == {"unavailable"}
    assert {o.k for o in observations} == {None}
    assert {o.atr_prior_confirmed for o in observations} == {None}
    assert {r.condition_met for r in ch.run_c1(observations).readings} == {None}


# ---------------------------------------------------------------------------
# PIT-W4-4 — a stale confirmed history
# ---------------------------------------------------------------------------

def test_PIT_W4_4_a_stale_history_yields_stale_and_None_never_False(pack):
    """W3-5.  A %K derived from a weeks-old base is a current-looking number
    about an old world, and the safest place for it is nowhere."""
    observations = _builder(pack, "STALE").observations(_tape([90.0, 89.0, 88.0]))
    assert {o.availability for o in observations} == {"stale"}
    assert {o.history_freshness for o in observations} == {"stale"}
    assert {o.k for o in observations} == {None}

    readings = ch.run_c1(observations).readings
    assert {r.condition_met for r in readings} == {None}
    assert False not in {r.condition_met for r in readings}, \
        "a stale input produced a MEASURED NON-FIRE"
    assert "stale" in ch.NULL_AVAILABILITY


def test_PIT_W4_4_CONTROL_a_fresh_history_carries_a_verdict(pack):
    observations = _builder(pack, "WASH").observations(_tape([90.0, 89.0, 88.0]))
    assert {o.history_freshness for o in observations} == {"confirmed"}
    assert any(r.condition_met is not None for r in ch.run_c1(observations).readings)


def test_PIT_W4_4_a_stale_name_still_appears_in_the_payload(pack):
    """Null law at the artifact level: withheld is not the same as absent."""
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(37))
    row = next(r for r in result.payload["names"] if r["ticker"] == "STALE")
    assert row["state"] == "evaluated"
    assert "reading_stale" in row["reasons"]


# ---------------------------------------------------------------------------
# PIT-W4-5 — missing intervals, and the missing open
# ---------------------------------------------------------------------------

def test_PIT_W4_5_a_missing_interval_carries_forward_and_DISCLOSES_it(pack):
    """A5.1: "no trade" is not "no price".  The value carries; the FACT that the
    interval had no bar of its own is recorded so a consumer can tell."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    tape = _tape([90.0, 89.0, 88.0, 87.0], skip={2})
    points = ch.sample_session_path(tape)
    cut = open_dt + timedelta(minutes=20)
    live = [p for p in points if p.observed_at <= cut]

    carried = [p for p in live if not p.interval_had_bar and p.sampled_close is not None]
    assert carried, "the fixture never produced a carried-forward interval"
    assert all(p.sampled_close is not None for p in carried)

    observations = _builder(pack).observations(tape, now=cut)
    assert all(o.sampled_close is not None for o in observations[1:])


def test_PIT_W4_5_a_missing_OPEN_is_None_and_fabricates_nothing(pack):
    """Before the first print there is no price, and none is invented."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    late = ch.SessionTape(
        session=NEXT_SESSION,
        minutes=(ch.MinuteBar(start=open_dt + timedelta(minutes=40), open=90.0,
                              high=90.0, low=90.0, close=90.0),),
        price_basis=ch.BASIS_ADJUSTED, vintage="late-open")
    observations = _builder(pack).observations(
        late, now=open_dt + timedelta(minutes=30))
    assert observations, "the grid produced no intervals at all"
    assert {o.sampled_close for o in observations} == {None}
    assert {o.availability for o in observations} == {"unavailable"}
    assert {o.source_bar_time for o in observations} == {None}
    assert {r.condition_met for r in ch.run_c1(observations).readings} == {None}


def test_PIT_W4_5_running_sampled_low_is_the_SAMPLED_low_not_the_minute_low(pack):
    """§7.1.  Minute lows are <= sampled lows, so a rebound variant fed the
    minute low would fire earlier and more often than the live lane could ever
    have observed.  The minute low is carried so the gap is MEASURABLE."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    minutes = (
        ch.MinuteBar(start=open_dt, open=90.0, high=90.0, low=70.0, close=90.0),
        ch.MinuteBar(start=open_dt + timedelta(minutes=5), open=90.0, high=90.0,
                     low=90.0, close=90.0),
    )
    tape = ch.SessionTape(session=NEXT_SESSION, minutes=minutes,
                          price_basis=ch.BASIS_ADJUSTED, vintage="wick")
    point = ch.sample_session_path(tape)[1]
    assert point.running_sampled_low == 90.0
    assert point.running_minute_low == 70.0

    observations = _builder(pack).observations(
        tape, now=open_dt + timedelta(minutes=10))
    assert observations[1].running_sampled_low == 90.0
    assert observations[1].running_minute_low == 70.0


# ---------------------------------------------------------------------------
# PIT-W4-6 — extended hours, and the out-of-window pass
# ---------------------------------------------------------------------------

def test_PIT_W4_6_premarket_and_postmarket_prints_are_excluded_from_the_tape(pack):
    """§7.  A bar is admitted iff it OPENS at/after the open and CLOSES at/before
    the close, so the 15:59 bar is inside and the 16:00 bar is not."""
    open_dt, close_dt = session_window_et(NEXT_SESSION)
    minutes = (
        ch.MinuteBar(start=open_dt - timedelta(minutes=30), open=50.0, high=50.0,
                     low=50.0, close=50.0),
        ch.MinuteBar(start=open_dt, open=90.0, high=90.0, low=90.0, close=90.0),
        ch.MinuteBar(start=close_dt - timedelta(minutes=1), open=91.0, high=91.0,
                     low=91.0, close=91.0),
        ch.MinuteBar(start=close_dt, open=200.0, high=200.0, low=200.0, close=200.0),
    )
    tape = ch.SessionTape(session=NEXT_SESSION, minutes=minutes,
                          price_basis=ch.BASIS_ADJUSTED, vintage="extended")
    admitted = ch.rth_minutes(tape)
    assert [m.close for m in admitted] == [90.0, 91.0]

    observations = _builder(pack).observations(tape)
    assert 50.0 not in {o.sampled_close for o in observations}
    assert 200.0 not in {o.sampled_close for o in observations}


def test_PIT_W4_6_a_premarket_QUOTE_never_enters_the_journal(tmp_path, pack):
    """The gate is on the quote as well as on the tape — the pass must not
    journal a print it would then have to exclude."""
    now = et_now(37)
    book = quote_book(pack, multiple=0.97, ts=et_now(30))
    book["quotes"]["WASH"]["ts"] = (session_window_et(NEXT_SESSION)[0]
                                    - timedelta(hours=1)).timestamp() * 1000.0
    result = one_pass(pack, book, now=now, state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path))
    assert name_of(result, "WASH").reasons == ("premarket_quote",)
    assert le.SessionJournal(tmp_path).read(NEXT_SESSION.isoformat(), "WASH") is None


@pytest.mark.parametrize("offset,expected", [
    (-30.0, "pre_open"),
    (390.0 + le.WINDOW_END_GRACE_MIN + 5.0, "post_close"),
])
def test_PIT_W4_6_an_out_of_window_pass_evaluates_nothing(pack, offset, expected):
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(offset))
    assert result.health["state"] == "out_of_window"
    assert result.health["reasons"] == [expected]
    assert result.payload["transitions"] == [] and result.payload["events"] == []
    assert all(row["state"] == "unavailable" for row in result.payload["names"])


def test_PIT_W4_6_CONTROL_the_close_side_grace_keeps_the_last_interval(pack):
    """The session's final interval ends AT the close and a UTC-gridded timer
    lands seconds later; an ungraced window would drop the most informative
    interval of the day."""
    inside, why, _session = le.in_window(et_now(390.0 + le.WINDOW_END_GRACE_MIN - 1.0))
    assert inside is True and why == "in_window"


# ---------------------------------------------------------------------------
# PIT-W4-11 — the full §10 re-arm chain
# ---------------------------------------------------------------------------

def _arm_and_candidate(pack, ledger, tmp_path):
    le.run_pass(now=et_now(32), pack=pack,
                quotes=quote_book(pack, multiple=0.97, ts=et_now(30)), ledger=ledger,
                state_dir=tmp_path, spool=None, unspooled_ok=True)
    return le.run_pass(now=et_now(37), pack=pack,
                       quotes=quote_book(pack, multiple=0.96, ts=et_now(35)),
                       ledger=ledger, state_dir=tmp_path, spool=None,
                       unspooled_ok=True)


def test_PIT_W4_11_arm_then_candidate_then_resolve_then_a_LAWFUL_re_arm(tmp_path, pack):
    """The whole lifecycle, in one test, because the bugs live in the seams.

    Resolve is calendar arithmetic in the pack builder's overlay; the re-arm
    window then opens on the confirmed-K ledger.  A unit that has genuinely
    recovered (K > 50 on two consecutive sessions) may arm again as a NEW
    episode, and the old one is untouched by it.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_and_candidate(pack, ledger, tmp_path)
    episode = next(e for e in ledger.episodes
                   if e.detector_id == ch.C1_DETECTOR_ID)
    assert episode.state == dt.DetectorState.CANDIDATE.value
    original = episode.canonical

    resolved_session = ll.session_at_offset(episode.market_session,
                                            ll.RESOLVE_HORIZON_SESSIONS)
    delta = ll.apply_session_clocks(ledger, as_of_session=resolved_session.isoformat(),
                                    confirmed_k_by_name={})
    ledger.commit(delta, spool_receipt="live_flow/entry_radar_events/x.json")
    reloaded = ledger.get(episode.episode_id)
    assert reloaded.state == dt.DetectorState.RESOLVED.value
    assert reloaded.terminal

    blocked, reason = ledger.arm_allowed(
        "WASH", ch.C1_DETECTOR_ID, session=resolved_session.isoformat(),
        would_have_armed_at=f"{resolved_session.isoformat()}T14:05:00Z")
    assert blocked is False and reason == "rearm_window_open"

    session = resolved_session
    for _ in range(ch.REARM_K_SESSIONS):
        session = ll.session_at_offset(session, 1)
        ll.apply_session_clocks(ledger, as_of_session=session.isoformat(),
                                confirmed_k_by_name={"WASH": 71.0})
    allowed, why = ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID,
                                      session=session.isoformat())
    assert allowed is True and why == "rearm_eligible"
    assert ledger.get(episode.episode_id).canonical != original, \
        "the RESOLVED transition should have changed the stored record"


def test_PIT_W4_11_a_premature_re_arm_is_REFUSED_and_RECORDED_never_silent(tmp_path, pack):
    """§11's control pool needs the names the rule SUPPRESSED, not just the ones
    it let through."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_and_candidate(pack, ledger, tmp_path)
    episode = next(e for e in ledger.episodes if e.detector_id == ch.C1_DETECTOR_ID)
    resolved_session = ll.session_at_offset(episode.market_session,
                                            ll.RESOLVE_HORIZON_SESSIONS)
    ledger.commit(ll.apply_session_clocks(
        ledger, as_of_session=resolved_session.isoformat(), confirmed_k_by_name={}),
        spool_receipt="live_flow/entry_radar_events/x.json")

    before = len(ledger.suppressions)
    allowed, reason = ledger.arm_allowed(
        "WASH", ch.C1_DETECTOR_ID, session=resolved_session.isoformat(),
        would_have_armed_at=f"{resolved_session.isoformat()}T14:05:00Z")
    assert allowed is False and reason == "rearm_window_open"
    assert len(ledger.suppressions) == before + 1
    note = ledger.suppressions[-1]
    assert note["ticker"] == "WASH" and note["reason"] == "rearm_window_open"
    assert note["would_have_armed_at"]


def test_PIT_W4_11_a_suppressed_arm_keeps_its_READINGS(tmp_path, pack):
    """The name WAS evaluated and the condition really WAS met.  Dropping the
    readings too would erase the evidence that the rule bit."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    result = _arm_and_candidate(pack, ledger, tmp_path)
    wash = name_of(result, "WASH")
    assert wash.lanes["c1"], "the fixture produced no C1 readings"
    assert any(row["condition_met"] is True for row in wash.lanes["c1"])


def test_PIT_W4_11_the_old_episode_is_never_mutated_by_a_later_one(tmp_path, pack):
    """Once a transition existed it is never erased (append-only, §0)."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_and_candidate(pack, ledger, tmp_path)
    episode = next(e for e in ledger.episodes if e.detector_id == ch.C1_DETECTOR_ID)
    resolved_session = ll.session_at_offset(episode.market_session,
                                            ll.RESOLVE_HORIZON_SESSIONS)
    ledger.commit(ll.apply_session_clocks(
        ledger, as_of_session=resolved_session.isoformat(), confirmed_k_by_name={}),
        spool_receipt="live_flow/entry_radar_events/x.json")
    terminal = ledger.get(episode.episode_id).canonical

    with pytest.raises(ll.TerminalEpisodeMutation):
        ledger.commit(ll.PendingDelta(
            ticker="WASH", as_of_session=resolved_session.isoformat(), pass_id="rth",
            episodes=(ledger.get(episode.episode_id)
                      .replace(last_observed_at="2099-01-01T00:00:00Z").to_dict(),)),
            spool_receipt="live_flow/entry_radar_events/y.json")
    assert ledger.get(episode.episode_id).canonical == terminal


def test_PIT_W4_11_repeated_cycles_cannot_duplicate_a_transition(tmp_path, pack):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_and_candidate(pack, ledger, tmp_path)
    for _ in range(4):
        _arm_and_candidate(pack, ledger, tmp_path)
    addresses = [ll.transition_address(t) for t in ledger.transitions]
    assert len(addresses) == len(set(addresses))


def test_PIT_W4_11_the_detector_specs_are_UNTOUCHED_by_the_whole_chain():
    """The lifecycle is a CLOCK.  If any of these moved, every level the pack
    publishes would be attributed to a detector that no longer exists."""
    registered = lp.registered_spec_hashes()
    for detector_id, frozen in FROZEN_SPEC_HASHES.items():
        assert registered[detector_id] == frozen, f"{detector_id} spec hash MOVED"
    assert ch.c1_spec_hash() == FROZEN_SPEC_HASHES["C1_1D_LIVE_WASHOUT@1"]
    assert ch.c2_spec_hash() == FROZEN_SPEC_HASHES["C2_1D_TURN@1"]
    assert fh.c3_spec_hash() == FROZEN_SPEC_HASHES["C3_1D_4H_RECOVERY@1"]
    assert ch.c4_spec_hash() == FROZEN_SPEC_HASHES["C4_MTF_TURN@1"]


def test_PIT_W4_11_F1_FUSION_still_refuses():
    from engine.entry_radar.detectors import (RESERVED_DETECTOR_IDS, NotYetSpecified,
                                              get_spec)
    assert RESERVED_DETECTOR_IDS == ("F1_FUSION",)
    with pytest.raises(NotYetSpecified):
        get_spec("F1_FUSION")


# ---------------------------------------------------------------------------
# PIT-W4-12 — many lanes, one ticker, no flattening
# ---------------------------------------------------------------------------

def test_PIT_W4_12_one_ticker_occupies_many_lanes_at_once(pack):
    """Six C2 variants are six mechanistically distinct experts (§18 A5.3).

    They are never deduped into one generic "C2 read", which is what the
    per-variant key proves: a flattening bug would collapse them to one row and
    the count below would fall to one.
    """
    path = _builder(pack).observations(recovery_tape(pack))
    c1 = ch.run_c1(path)
    assert c1.episode is not None
    c2 = ch.run_c2(path, c1.episode)

    fired = {variant for variant, stamps in c2.fires.items() if stamps}
    assert len(fired) >= 3, f"only {fired} fired — cannot test multi-lane occupancy"

    rows = le._lane_rows(list(c1.readings) + list(c2.readings))
    keys = [(row["detector_id"], row["variant"]) for row in rows]
    assert len(keys) == len(set(keys))
    assert (ch.C1_DETECTOR_ID, None) in keys
    assert len({v for d, v in keys if d == ch.C2_DETECTOR_ID}) == len(ch.C2_VARIANTS)


def test_PIT_W4_12_the_payload_carries_no_generic_entry_signal_key(tmp_path, pack):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    result = _arm_and_candidate(pack, ledger, tmp_path)
    keys = {k.lower() for k in le.emitted_keys(result.payload)}
    for banned in ("entry_signal", "signal", "combined", "consensus", "fused",
                   "aggregate_state", "overall"):
        assert banned not in keys, f"the payload flattened its lanes into {banned!r}"


def test_PIT_W4_12_C4_structurally_cannot_fire(pack):
    """C4 has no condition to meet, so there is nothing for a boolean to be
    about.  Recording False would invite a reader to treat the absence of a turn
    as a measured non-fire of a detector that cannot fire at all."""
    state = ch.c4_snapshot(ticker="WASH", daily=_daily(pack), market_session=NEXT_SESSION)
    reading = ch.c4_reading(state, observed_at="2026-08-17T14:05:00Z")
    assert reading.condition_met is None
    with pytest.raises(ch.StratificationOnly):
        ch.assert_can_fire(ch.C4_DETECTOR_ID)


def test_PIT_W4_12_a_C4_context_block_rides_the_row_and_mints_no_episode(tmp_path, pack):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_and_candidate(pack, ledger, tmp_path)
    assert all(e.detector_id != ch.C4_DETECTOR_ID for e in ledger.episodes)
    assert all(t.get("detector_id") != ch.C4_DETECTOR_ID for t in ledger.transitions)


# ---------------------------------------------------------------------------
# W4R — round-1 adversarial review regressions (PIT + lifecycle half)
#
# Each test asserts the property its finding's REPRODUCTION violated, with a
# control that breaks it back where the guard is load-bearing.
# ---------------------------------------------------------------------------

def _c4_block(daily: ch.DailyHistory, session: date, observed_at: str) -> dict:
    """The lawful C4 block cut at ``session`` — the oracle this fix must match."""
    row = ch.c4_reading(ch.c4_snapshot(ticker="WASH", daily=daily,
                                       market_session=session),
                        observed_at=observed_at).to_dict()
    row.pop("authority", None)
    return row


def _c2_run_with_prior_candidate(pack, *, candidate_session: date):
    """A ``C2Run`` whose primary-variant candidate is stamped on a PRIOR session.

    ``run_c2`` replays the whole episode path every pass and re-mints
    ``candidate_at`` at its ORIGINAL instant, so this is the shape a multi-day
    episode presents to ``_c4_context`` on every pass after the first.  Built
    directly rather than driven over days because the property under test is
    about the STAMP, not about how the stamp came to be there.
    """
    path = _builder(pack).observations(recovery_tape(pack))
    c1 = ch.run_c1(path)
    assert c1.episode is not None
    run = ch.run_c2(path, c1.episode)
    episode = run.variant_episode(ch.C2_PRIMARY_VARIANT)
    assert episode is not None and episode.candidate_at
    open_dt, _close = session_window_et(candidate_session)
    episode.candidate_at = ch.utc_iso(open_dt + timedelta(hours=5))
    return run, episode


def test_W4R_C3_a_prior_session_candidate_snapshots_at_ITS_OWN_session(pack):
    """§0's PIT gate, verbatim: at evaluation T nothing after T may influence a
    reading.

    Measured before the fix: ``candidate_at`` 2026-08-11T15:00Z, pass session
    2026-08-17, and the emitted row carried ``observed_at`` 2026-08-11 beside
    ``market_session`` 2026-08-17 — computed from bars confirmed through
    2026-08-14, four confirmed sessions of future information behind a reading
    stamped in the past.  The row contradicted itself, and C4 structurally cannot
    fire, so no firing decision would ever have caught it.
    """
    prior = ll.session_at_offset(NEXT_SESSION, -4)
    daily = _daily(pack)
    run, episode = _c2_run_with_prior_candidate(pack, candidate_session=prior)

    row = le._c4_context(ticker="WASH", daily=daily, c2_run=run)
    assert row is not None
    assert row["observed_at"] == str(episode.candidate_at)
    assert row["market_session"] == prior.isoformat(), \
        "the row names two different sessions for one reading"
    assert row == _c4_block(daily, prior, str(episode.candidate_at)), \
        "the published block is not the one the candidate instant cuts"


def test_W4R_C3_CONTROL_the_pass_session_cut_is_a_DIFFERENT_block(pack):
    """The control that makes the assertion above load-bearing.

    If both cuts produced the same bytes the fix would be untestable — and on
    this corpus they do not: ``d2_recent_washout`` is False at the candidate's
    session and True at the pass's, which is exactly the post-stamp information
    the old code published.
    """
    prior = ll.session_at_offset(NEXT_SESSION, -4)
    daily = _daily(pack)
    at = ch.utc_iso(session_window_et(prior)[0] + timedelta(hours=5))
    assert _c4_block(daily, prior, at) != _c4_block(daily, NEXT_SESSION, at)


def test_W4R_C3_a_bar_confirmed_AFTER_the_candidate_cannot_move_the_snapshot(pack):
    """The mutation control, on the substrate itself."""
    prior = ll.session_at_offset(NEXT_SESSION, -4)
    daily = _daily(pack)
    run, _episode = _c2_run_with_prior_candidate(pack, candidate_session=prior)
    before = le._c4_context(ticker="WASH", daily=daily, c2_run=run)

    frame = daily.frame.copy()
    mask = frame.index >= pd.Timestamp(prior)
    assert mask.any(), "the fixture has no post-candidate bars to mutate"
    frame.loc[mask] = frame.loc[mask] * 1.65
    mutated = ch.DailyHistory(frame=frame, price_basis=daily.price_basis,
                              vintage=daily.vintage)

    assert le._c4_context(ticker="WASH", daily=mutated, c2_run=run) == before, \
        "post-candidate bars reached a pre-candidate reading"
    at = str(_c2_run_with_prior_candidate(pack, candidate_session=prior)[1].candidate_at)
    assert _c4_block(mutated, NEXT_SESSION, at) != _c4_block(daily, NEXT_SESSION, at), \
        "the CONTROL must show the mutation moving the PASS-session cut"


# --- H3 / M5 / M9: one suppression fact, one row, and it reaches the row -----

def _terminal_c1_episode(ledger, *, ticker: str = "WASH"):
    """Seed a TERMINAL C1 episode armed on a long-past instant.

    Today's tape then re-arms at a DIFFERENT instant, so the §10 gate is really
    consulted — a re-derived arm at the SAME instant is the same episode id and
    never reaches ``arm_allowed`` at all, which is why the existing PIT-W4-11
    tests call the gate directly and why the duplication defect survived them.
    """
    armed = ll.session_at_offset(NEXT_SESSION, -40)
    at = f"{armed.isoformat()}T14:00:00Z"
    episode = ll.LiveEpisode(
        episode_id=ll.compute_episode_id(ticker=ticker,
                                         detector_id=ch.C1_DETECTOR_ID,
                                         variant=None, first_armed_at=at),
        ticker=ticker, detector_id=ch.C1_DETECTOR_ID,
        detector_version=ch.C1_VERSION, detector_spec_hash=ch.c1_spec_hash(),
        state=dt.DetectorState.EXPIRED.value, market_session=armed.isoformat(),
        first_armed_at=at)
    ledger.commit(ll.PendingDelta(ticker=ticker,
                                  as_of_session=NEXT_SESSION.isoformat(),
                                  pass_id="w4r-fixture",
                                  episodes=(episode.to_dict(),)),
                  spool_receipt="live_flow/entry_radar_events/seed.json")
    assert ledger.get(episode.episode_id).terminal
    return episode


def _suppressed_passes(pack, ledger, tmp_path, *, count: int = 5):
    out = []
    for index in range(count):
        out.append(le.run_pass(
            now=et_now(32 + 5 * index), pack=pack,
            quotes=quote_book(pack, multiple=0.97 - 0.005 * index,
                              ts=et_now(30 + 5 * index)),
            ledger=ledger, state_dir=tmp_path, spool=None, unspooled_ok=True,
            env={}))
    return out


def test_W4R_H3_repeated_passes_leave_exactly_ONE_suppression_row(tmp_path, pack):
    """Measured before the fix: pass k collected k identical rows in the payload
    AND appended a k-th copy to the ledger.

    At ~78 passes a session that is 78 duplicates of ONE fact in
    ``episodes.json`` and 78 in the final payload; the row count grew
    quadratically in sessions x suppressed names, ``compact()`` never touched
    ``_suppressions`` and ``_ledger_hash`` covers only ``episodes`` — so the
    growth was invisible to the content signal — and any §11 control-pool count
    built from the field was inflated by exactly the pass number.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _terminal_c1_episode(ledger)
    results = _suppressed_passes(pack, ledger, tmp_path)

    suppressing = [r for r in results if "suppressed_by_rearm" in name_of(r, "WASH").reasons]
    assert len(suppressing) >= 4, "the fixture did not suppress on enough passes"
    assert all(len([row for row in r.payload["suppressed"]
                    if row.get("ticker") == "WASH"]) == 1 for r in suppressing)

    wash = [row for row in ledger.suppressions if row.get("ticker") == "WASH"]
    identities = {(r["ticker"], r["detector_id"], r["variant"], r["session"],
                   r["would_have_armed_at"]) for r in wash}
    assert len(wash) == len(identities) == 1, \
        f"{len(wash)} ledger rows for {len(identities)} suppression fact(s)"


def test_W4R_H3_the_PAYLOAD_publishes_only_THIS_passs_suppression(tmp_path, pack):
    """The evaluator half's observable contract, over a NON-TRIVIAL history.

    The test above runs against a ledger holding exactly one suppression fact, so
    "one row published" is true there however the filter is written.  This seeds
    a second, genuinely historical fact (a prior session's) and requires the
    payload to publish this pass's and only this pass's.

    HONEST LIMIT, stated so nobody re-derives it: the two halves of the H3 fix
    are REDUNDANT by construction and cannot be discriminated from each other
    here.  ``_refuse`` is idempotent, ``would_have_armed_at`` is in the identity
    (and an instant belongs to exactly one session), and the publisher caps at
    ``[:1]`` — so ``mark``, the ``session`` key and the cap are each individually
    revertible with every assertion still green.  The load-bearing guard is the
    ledger's idempotency, and THAT is mutation-proved in
    ``tests/test_entry_radar_w4_ledger.py`` (reverting it reds three tests).
    What this pins is the contract the payload owes a reader; what it does not
    pin is which of three overlapping mechanisms delivers it.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _terminal_c1_episode(ledger)
    prior_session = ll.session_at_offset(NEXT_SESSION, -1)
    ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID,
                       session=prior_session.isoformat(),
                       would_have_armed_at=f"{prior_session.isoformat()}T15:00:00Z")
    assert len(ledger.suppressions) == 1, "the historical fact was not seeded"

    # The LAST suppressing pass, not the first.  On pass 1 the row this pass
    # minted is still "fresh" (past the mark), so the publisher never reaches its
    # fallback; from pass 2 on ``_refuse`` has deduped and the fallback over the
    # ledger's whole history is the only path — which is where a filter that
    # forgot to scope by session republishes a PRIOR session's suppression.
    suppressing = [r for r in _suppressed_passes(pack, ledger, tmp_path)
                   if "suppressed_by_rearm" in name_of(r, "WASH").reasons]
    assert len(suppressing) >= 2, "the fixture did not suppress on enough passes"
    result = suppressing[-1]

    assert len(ledger.suppressions) >= 2, "this pass recorded no new suppression"
    published = [row for row in result.payload["suppressed"]
                 if row.get("ticker") == "WASH"]
    assert len(published) == 1, (
        f"{len(published)} rows published — the payload is republishing history "
        "rather than this pass's new suppression")
    assert published[0]["session"] == NEXT_SESSION.isoformat(), \
        "the payload published a PRIOR session's suppression as this pass's"


def test_W4R_M5_a_SUPPRESSED_lane_is_active_even_with_no_met_condition(tmp_path):
    """``_has_active_lane``'s two clauses, discriminated.

    On the end-to-end fixture below both fire at once (a suppressed arm whose C1
    reading also met its condition), so deleting the ``suppressed`` clause leaves
    that test green.  This is the clause on its own: a blocked arm whose readings
    are all non-fires is still evidence the §10 rule bit, and the served payload
    is the only durable trace of it.
    """
    reading = {"detector_id": ch.C1_DETECTOR_ID, "condition_met": False,
               "availability": "confirmed"}
    result = le.NameResult(
        ticker="WASH", state="evaluated", reasons=("suppressed_by_rearm",),
        lanes={"c1": [reading]},
        suppressed=({"ticker": "WASH", "detector_id": ch.C1_DETECTOR_ID,
                     "reason": "rearm_window_open"},))
    assert not any(r["condition_met"] for r in result.lanes["c1"]), \
        "the fixture must not let the OTHER clause carry the assertion"
    assert le._has_active_lane(result) is True


def test_W4R_M5_a_suppressed_names_row_carries_its_C1_READINGS(tmp_path, pack):
    """``_gate_arm`` keeps the readings on purpose — "dropping them too would
    erase the evidence that the rule bit" — and they then died at the artifact
    boundary, because an episode-only ``_has_active_lane`` sent the row down the
    compact branch.  The served payload is the ONLY durable trace of a suppressed
    pass: nothing is spooled and nothing is committed."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _terminal_c1_episode(ledger)
    result = next(r for r in _suppressed_passes(pack, ledger, tmp_path)
                  if "suppressed_by_rearm" in name_of(r, "WASH").reasons)

    wash = name_of(result, "WASH")
    assert wash.suppressed, "the rule did not bite on this fixture"
    row = next(r for r in result.payload["names"] if r["ticker"] == "WASH")
    assert row["lanes"].get("c1"), "the C1 readings died at the artifact boundary"
    assert any(reading["condition_met"] is True for reading in row["lanes"]["c1"])
    assert result.health["null_readings"]["suppressed"] >= 1


def test_W4R_M9_the_row_reason_covers_the_C2_and_C3_gates_too(tmp_path, pack):
    """``_gate_c2`` returned no flag at all and the C3 ``_gate_arm`` call threw
    its flag away, so a C2- or C3-suppressed name carried no
    ``suppressed_by_rearm`` and the only evidence lived in the payload block."""
    tree = ast.parse((Path(le.__file__)).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_evaluate_name")
    source = ast.unparse(node)
    assert "c1_blocked or c2_blocked or c3_blocked" in source
    assert "c2_run, c2_blocked = _gate_c2(" in source
    assert "c3_run, c3_blocked = _gate_arm(" in source

    ledger = ll.LiveEpisodeLedger(tmp_path)
    _terminal_c1_episode(ledger)
    result = next(r for r in _suppressed_passes(pack, ledger, tmp_path)
                  if name_of(r, "WASH").suppressed)
    assert "suppressed_by_rearm" in name_of(result, "WASH").reasons


# --- M8: a stale C3 anchor clamps rather than wedging the pass ---------------

class _ClampProbe:
    """A reader that records the window it was asked to bound.

    ``max_window_sessions`` is read OFF THE INJECTED READER rather than imported:
    ``live_eval`` must not import the concrete reader — the injection is the
    whole seam — so the bound has to travel on the object.
    """

    max_window_sessions = 180

    def __init__(self) -> None:
        self.windows: list[tuple[date, date]] = []

    def assert_window(self, start: date, end: date) -> None:
        from lib.nyse_calendar import sessions_between
        self.windows.append((start, end))
        span = len(sessions_between(start, end))
        if span > self.max_window_sessions:
            raise fh.C3Error(f"window {start}..{end} spans {span} sessions")

    def buckets(self, ticker: str, session: date, *, now=None, vintage=None):
        return ()


def test_W4R_M8_a_130_session_old_C3_anchor_CLAMPS_instead_of_wedging_the_pass(
        tmp_path, pack):
    """Self-reinforcing before the fix: ``assert_window`` raises
    ``VendorMinutesError`` — a ``C3Error``, i.e. a SIBLING of ``LiveEvalError`` —
    which killed the whole pass; and C3's ARMED-without-candidate expiry is
    internal to ``run_c3``, so the code that would expire the episode was the
    code that could not run.  Permanent wedge, exit 0, no payload.
    """
    from lib.nyse_calendar import sessions_between

    ledger = ll.LiveEpisodeLedger(tmp_path)
    anchor = ll.session_at_offset(NEXT_SESSION, -130)
    at = f"{anchor.isoformat()}T13:30:00Z"
    ledger.commit(ll.PendingDelta(
        ticker="WASH", as_of_session=NEXT_SESSION.isoformat(), pass_id="w4r-fixture",
        episodes=(ll.LiveEpisode(
            episode_id=ll.compute_episode_id(ticker="WASH",
                                             detector_id=fh.C3_DETECTOR_ID,
                                             variant=None, first_armed_at=at),
            ticker="WASH", detector_id=fh.C3_DETECTOR_ID,
            detector_version=fh.C3_VERSION, detector_spec_hash=fh.c3_spec_hash(),
            state=dt.DetectorState.ARMED.value, market_session=anchor.isoformat(),
            first_armed_at=at).to_dict(),)),
        spool_receipt="live_flow/entry_radar_events/anchor.json")
    assert ledger.live_episode("WASH", fh.C3_DETECTOR_ID, None) is not None

    probe = _ClampProbe()
    unclamped = len(sessions_between(
        ll.session_at_offset(anchor, -le.C3_WARMUP_SESSIONS), NEXT_SESSION))
    assert unclamped > probe.max_window_sessions, \
        "the fixture's anchor is not old enough to have raised"

    result = le.run_pass(now=et_now(32), pack=pack,
                         quotes=quote_book(pack, multiple=0.97, ts=et_now(30)),
                         ledger=ledger, state_dir=tmp_path, spool=None,
                         intraday_reader=probe, unspooled_ok=True, env={})

    assert probe.windows, "assert_window was never consulted"
    start, end = probe.windows[0]
    assert len(sessions_between(start, end)) <= probe.max_window_sessions
    assert result.payload["names"], "the pass produced no payload at all"
    wash = name_of(result, "WASH")
    assert wash.state == "evaluated", "one stale anchor still killed the name"
    assert "c3_incomplete_window" in wash.reasons
    # ...and the gapped refusal is COUNTED, not merely named on the row — a name
    # stuck here has to be visible in the receipt rather than reading as a quiet
    # market.  (Carried over from the deleted OPEN-GAP test, which owned it.)
    assert result.health["dark"]["c3_incomplete_window"] >= 1


class _FullProbe(_ClampProbe):
    """``_ClampProbe`` with every session's buckets actually present.

    A dataless tape still yields CONFIRMED buckets carrying ``close=None``, which
    ``run_c3`` discloses as ``confirmed_empty`` rather than fabricating — so this
    is a complete window with nothing in it, not a gapped one.  The distinction
    is the whole point of the pair below.
    """

    def buckets(self, ticker: str, session: date, *, now=None, vintage=None):
        tape = fh.tape_from_rows(session, [], price_basis=ch.BASIS_ADJUSTED,
                                 vintage="w4r-m8-fixture")
        return fh.four_hour_buckets(tape, now=now)


def _c3_episode(ledger, *, session, ticker: str = "WASH",
                state: str = dt.DetectorState.ARMED.value,
                candidate_at: str | None = None) -> str:
    """Commit one C3 episode armed at ``session``'s open.  Returns its id."""
    at = f"{session.isoformat()}T13:30:00Z"
    episode_id = ll.compute_episode_id(ticker=ticker, detector_id=fh.C3_DETECTOR_ID,
                                       variant=None, first_armed_at=at)
    ledger.commit(ll.PendingDelta(
        ticker=ticker, as_of_session=NEXT_SESSION.isoformat(), pass_id="w4r-fixture",
        episodes=(ll.LiveEpisode(
            episode_id=episode_id,
            ticker=ticker, detector_id=fh.C3_DETECTOR_ID,
            detector_version=fh.C3_VERSION, detector_spec_hash=fh.c3_spec_hash(),
            state=state, market_session=session.isoformat(),
            first_armed_at=at, candidate_at=candidate_at).to_dict(),)),
        spool_receipt="live_flow/entry_radar_events/anchor.json")
    return episode_id


def _stale_c3_anchor(ledger, *, sessions_back: int = 130, **kwargs) -> str:
    """Commit one ARMED C3 episode ``sessions_back`` sessions before today."""
    return _c3_episode(ledger,
                       session=ll.session_at_offset(NEXT_SESSION, -sessions_back),
                       **kwargs)


def _open_instant(session) -> str:
    """The session's 09:30 ET open as a UTC stamp — RE-DERIVED, not imported.

    ``ll.session_open_instant`` is part of what these tests are checking, so the
    expected stamp is computed from ``session_window_et`` here instead.
    """
    open_dt, _close_dt = session_window_et(session)
    return open_dt.astimezone(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def test_W4R_M8_the_clamped_window_RUNS_the_S10_ARM_CLOCK_through_the_pass(
        tmp_path, pack):
    """The clamp is only lawful if the shortened window still evaluates §10.

    Driven through ``run_pass`` and read back off the LEDGER, because that is
    where the wedge lived: C3's ARMED-without-candidate expiry is internal to
    ``run_c3``, so before the clamp the code that would expire the episode was
    the code that could not run — a raise on every pass, forever.  Calling
    ``fh.run_c3`` directly on a hand-built window exercises neither the clamp nor
    the pass and passes with the wedge fully intact, which is what the first
    version of this test did.

    What is asserted is what is TRUE: the clock runs, and an ARMED episode that
    waits out §10 inside the replayed window reaches EXPIRED in the ledger.
    Whether it also reaches the pre-existing ledger record is a separate
    question, pinned by the OPEN-GAP test below.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _stale_c3_anchor(ledger)
    before = {e.episode_id for e in ledger.episodes
              if e.detector_id == fh.C3_DETECTOR_ID}

    result = le.run_pass(now=et_now(32), pack=pack,
                         quotes=quote_book(pack, multiple=0.97, ts=et_now(30)),
                         ledger=ledger, state_dir=tmp_path, spool=None,
                         intraday_reader=_FullProbe(), unspooled_ok=True, env={})

    assert result.payload["names"], "the pass produced no payload at all"
    minted = [e for e in ledger.episodes
              if e.detector_id == fh.C3_DETECTOR_ID and e.episode_id not in before]
    assert minted, "the clamped window ran no C3 replay at all"
    assert any(e.state == dt.DetectorState.EXPIRED.value for e in minted), \
        "the clamped window never reached the §10 expiry"
    assert fh.C3_ARM_EXPIRY_SESSIONS == 15


# --- M8, closed: the OVERLAY is §10's second lawful enforcement point --------
#
# The OPEN-GAP test that stood here (``…_the_stale_LEDGER_episode_is_not_expired
# _by_the_replay``) is DELETED, because the gap it pinned is closed.  What it
# recorded, kept as the reason these five exist: ``run_c3`` is a stateless replay
# that counts §10 by POSITION within the sessions it walks, and episode identity
# is ``compute_episode_id(ticker, detector, variant, first_armed_at)`` — so the
# replay's clock can only ever reach episodes its OWN walk mints.  A ledger
# episode armed outside even the clamped window was never matched by any replay,
# stayed ARMED forever, and blocked its unit's re-arm (`live_episode_open`)
# indefinitely.  ``apply_session_clocks`` now runs the same frozen 15-session
# clock as calendar arithmetic, which is where §10 bookkeeping belongs.

_M8_RECEIPT = "live_flow/entry_radar_events/2026-08-17/143000-pack.json"


@pytest.mark.parametrize("state", [dt.DetectorState.ARMED.value,
                                   dt.DetectorState.TURNING.value])
def test_W4R_M8_a_130_session_old_LEDGER_episode_EXPIRES_and_the_unit_RE_ARMS(
        tmp_path, state):
    """M8's OPEN GAP, closed at the overlay — the whole chain, end to end.

    The wedge is asserted first (``live_episode_open`` before the overlay runs),
    because a test that only shows the EXPIRED transition would pass on a ledger
    that was never stuck.  Then: the transition lands at the EXPIRING session's
    OPEN instant (``run_c3``'s W3-2 convention, re-derived here from
    ``session_window_et`` rather than from the helper under test), ``commit``'s
    existing terminal hook opens the §10 re-arm window, the window is earned on
    confirmed K, and a later arm mints a NEW episode with its own address.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    anchor = ll.session_at_offset(NEXT_SESSION, -130)
    stale_id = _stale_c3_anchor(ledger, state=state)
    assert ledger.arm_allowed("WASH", fh.C3_DETECTOR_ID) == \
        (False, "live_episode_open"), "the fixture was not wedged to begin with"

    delta = ll.apply_session_clocks(ledger, as_of_session=NEXT_SESSION.isoformat(),
                                    confirmed_k_by_name={})
    assert delta.pass_id == ll.PACK_PASS_ID
    assert len(delta.transitions) == 1
    row = delta.transitions[0]
    assert (row["from_state"], row["to_state"]) == (state, "EXPIRED")
    expiring = ll.session_at_offset(anchor, fh.C3_ARM_EXPIRY_SESSIONS)
    assert row["at"] == _open_instant(expiring), "not the expiring session's OPEN"
    assert row["at"] != ll.session_close_instant(expiring), \
        "stamped at the CLOSE — run_c3 stamps the OPEN (W3-2)"
    assert row["at"].startswith(expiring.isoformat())

    ledger.commit(delta, spool_receipt=_M8_RECEIPT)
    assert ledger.get(stale_id).state == dt.DetectorState.EXPIRED.value
    assert ledger.get(stale_id).terminal

    # commit()'s terminal hook opened the window — the refusal MOVED from "a live
    # episode exists forever" to "the §10 clock is running", which is the fix.
    assert ledger.arm_allowed("WASH", fh.C3_DETECTOR_ID) == \
        (False, "rearm_window_open")
    for offset in (1, 2):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        ledger.advance_rearm(as_of_session=session.isoformat(),
                             confirmed_k_by_name={"WASH": ch.REARM_K_FLOOR + 5})
    assert ledger.arm_allowed("WASH", fh.C3_DETECTOR_ID) == (True, "rearm_eligible")

    # ...and the next washed session arms a NEW episode, not the old one back.
    new_id = _c3_episode(ledger, session=ll.session_at_offset(NEXT_SESSION, 3))
    assert new_id != stale_id
    live = ledger.live_episode("WASH", fh.C3_DETECTOR_ID, None)
    assert live is not None and live.episode_id == new_id
    assert ledger.get(stale_id).state == dt.DetectorState.EXPIRED.value


def test_W4R_M8_the_clock_fires_at_EXACTLY_15_ELAPSED_SESSIONS_never_at_14(tmp_path):
    """The boundary, walked one session at a time — 0..14 quiet, 15 expires.

    Two boundary points would pass on an off-by-one that fires early somewhere in
    the middle; the ramp cannot.  The span itself is asserted to be the SPEC's
    value, imported rather than re-minted, because a second 15 in the ledger
    module could drift away from the ``C3_SPEC`` hash that publishes it (W3-4).
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    anchor = ll.session_at_offset(NEXT_SESSION, -fh.C3_ARM_EXPIRY_SESSIONS)
    _stale_c3_anchor(ledger, sessions_back=fh.C3_ARM_EXPIRY_SESSIONS)

    for elapsed in range(0, fh.C3_ARM_EXPIRY_SESSIONS):
        session = ll.session_at_offset(anchor, elapsed)
        delta = ll.apply_session_clocks(ledger, as_of_session=session.isoformat(),
                                        confirmed_k_by_name={})
        assert delta.transitions == (), f"expired early at +{elapsed} session(s)"

    session = ll.session_at_offset(anchor, fh.C3_ARM_EXPIRY_SESSIONS)
    assert session == NEXT_SESSION
    delta = ll.apply_session_clocks(ledger, as_of_session=session.isoformat(),
                                    confirmed_k_by_name={})
    assert [t["to_state"] for t in delta.transitions] == ["EXPIRED"]

    assert fh.C3_ARM_EXPIRY_SESSIONS == 15
    assert fh.C3_SPEC["arm_expiry_sessions"] == fh.C3_ARM_EXPIRY_SESSIONS
    source = Path(ll.__file__).read_text(encoding="utf-8")
    assert "from engine.entry_radar.four_hour import C3_ARM_EXPIRY_SESSIONS" in source
    assert "C3_ARM_EXPIRY_SESSIONS = " not in source, "the span was RE-MINTED here"


def test_W4R_M8_an_episode_that_HAS_a_candidate_is_NEVER_expired_by_this_path(
        tmp_path):
    """``candidate_at`` set ⇒ the RESOLVED clock owns the episode, not this one.

    Both shapes are covered because they fail differently.  The ordinary
    CANDIDATE record is excluded by its STATE; an ARMED record that carries a
    candidate stamp is excluded only by the ``candidate_at`` clause — and without
    that clause it would expire on the ARM's 15-session clock while its candidate
    was still inside the 10-session resolve horizon, terminating an episode twice
    over on two different clocks.
    """
    candidate = ll.LiveEpisodeLedger(tmp_path / "candidate")
    anchor = ll.session_at_offset(NEXT_SESSION, -130)
    _stale_c3_anchor(candidate, state=dt.DetectorState.CANDIDATE.value,
                     candidate_at=f"{anchor.isoformat()}T14:30:00Z")
    delta = ll.apply_session_clocks(candidate, as_of_session=NEXT_SESSION.isoformat(),
                                    confirmed_k_by_name={})
    assert [(t["from_state"], t["to_state"]) for t in delta.transitions] == \
        [("CANDIDATE", "RESOLVED")]

    armed = ll.LiveEpisodeLedger(tmp_path / "armed_with_candidate")
    _stale_c3_anchor(armed, state=dt.DetectorState.ARMED.value,
                     candidate_at=f"{anchor.isoformat()}T14:30:00Z")
    assert ll.apply_session_clocks(armed, as_of_session=NEXT_SESSION.isoformat(),
                                   confirmed_k_by_name={}).transitions == ()


def test_W4R_M8_MUTATION_without_the_overlay_expiry_the_stale_episode_WEDGES(
        tmp_path, monkeypatch):
    """Revert the fix in place; the wedge comes back.  CONTROL runs first.

    The mutation puts §10's span out of reach rather than editing the branch, so
    the overlay is byte-identical and only the clock it reads has moved — and the
    CANDIDATE episode committed alongside still RESOLVES under the same mutation,
    which is what makes the mutation provably scoped to the expiry path rather
    than to ``apply_session_clocks`` as a whole.
    """
    control = ll.LiveEpisodeLedger(tmp_path / "control")
    _stale_c3_anchor(control)
    assert [t["to_state"] for t in ll.apply_session_clocks(
        control, as_of_session=NEXT_SESSION.isoformat(),
        confirmed_k_by_name={}).transitions] == ["EXPIRED"]

    ledger = ll.LiveEpisodeLedger(tmp_path / "mutated")
    stale_id = _stale_c3_anchor(ledger)
    anchor = ll.session_at_offset(NEXT_SESSION, -130)
    _c3_episode(ledger, session=anchor, ticker="TURN",
                state=dt.DetectorState.CANDIDATE.value,
                candidate_at=f"{anchor.isoformat()}T14:30:00Z")

    monkeypatch.setattr(ll, "C3_ARM_EXPIRY_SESSIONS", 10 ** 6)
    delta = ll.apply_session_clocks(ledger, as_of_session=NEXT_SESSION.isoformat(),
                                    confirmed_k_by_name={})
    assert [t["to_state"] for t in delta.transitions] == ["RESOLVED"], \
        "the mutation was not scoped to the expiry clock"
    ledger.commit(delta, spool_receipt=_M8_RECEIPT)

    assert ledger.get(stale_id).state == dt.DetectorState.ARMED.value
    assert ledger.arm_allowed("WASH", fh.C3_DETECTOR_ID) == \
        (False, "live_episode_open"), "the wedge did not come back"


def test_W4R_M8_the_expiry_APPENDS_and_rewrites_no_history(tmp_path):
    """Append-only law (§0, contract §13, P-10) across the new transition.

    The prior episode's history must be byte-identical after the expiry apart
    from the one appended row: the earlier transitions unchanged in place, the
    record moved in exactly ``state`` and ``last_observed_at``, and — once
    terminal — frozen against every later pass, including the one that arms the
    unit's next episode.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    anchor = ll.session_at_offset(NEXT_SESSION, -130)
    stale_id = _stale_c3_anchor(ledger)
    ledger.commit(ll.PendingDelta(
        ticker="WASH", as_of_session=NEXT_SESSION.isoformat(), pass_id="w4r-fixture",
        transitions=({"ticker": "WASH", "detector_id": fh.C3_DETECTOR_ID,
                      "variant": None, "from_state": "PROBING", "to_state": "ARMED",
                      "at": f"{anchor.isoformat()}T13:30:00Z",
                      "reason": "fixture arm", "evidence_refs": [],
                      "pass_id": "w4r-fixture"},)),
        spool_receipt=_M8_RECEIPT)
    before_record = ledger.get(stale_id).to_dict()
    before_history = json.dumps(list(ledger.transitions), sort_keys=True)
    assert len(ledger.transitions) == 1, "the history to preserve must be non-empty"

    ledger.commit(ll.apply_session_clocks(ledger,
                                          as_of_session=NEXT_SESSION.isoformat(),
                                          confirmed_k_by_name={}),
                  spool_receipt=_M8_RECEIPT)

    after = list(ledger.transitions)
    assert json.dumps(after[:1], sort_keys=True) == before_history
    assert len(after) == 2
    assert (after[-1]["from_state"], after[-1]["to_state"]) == ("ARMED", "EXPIRED")

    after_record = ledger.get(stale_id).to_dict()
    assert {k for k in after_record if after_record[k] != before_record[k]} == \
        {"state", "last_observed_at"}
    assert after_record["last_observed_at"] == after[-1]["at"]

    # Terminal and frozen: a re-run admits nothing, and the unit's NEXT episode
    # leaves the expired record byte-identical.
    frozen = ledger.get(stale_id).canonical
    replay = ll.apply_session_clocks(ledger, as_of_session=NEXT_SESSION.isoformat(),
                                     confirmed_k_by_name={})
    assert (replay.transitions, replay.episodes) == ((), ())
    _c3_episode(ledger, session=ll.session_at_offset(NEXT_SESSION, 3))
    assert ledger.get(stale_id).canonical == frozen
    assert json.dumps(list(ledger.transitions)[:2], sort_keys=True) == \
        json.dumps(after, sort_keys=True)
