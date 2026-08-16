"""Live Entry Radar PR-4 (W4) — the RTH pass mechanics.

WHAT THIS SUITE IS FOR
----------------------
``engine/entry_radar/live_eval.py`` is the only place in the Radar where a
reading is produced from a price that has not yet closed a bar.  Everything it
does is therefore a claim about KNOWABILITY, and every claim below is tested as
one:

  LIVE-1   the basis audit runs BEFORE the engine, and a mismatched tape is
           never normalised into compliance — no tape, no observation, no verdict
  LIVE-2   the journal is append-only and PINNED to the pack that produced it;
           a cross-pack re-derivation refuses rather than backfilling
  LIVE-3   incremental observation construction is BYTE-IDENTICAL to
           ``build_observation_path`` across the fixture corpus (PIT-W4-16) —
           the one derived construction in W4, pinned rather than believed
  LIVE-4   the grid is TRUNCATED at ``now``: a 10:02 pass cannot emit a reading
           stamped 15:55, which the full-session sampler would happily do
  LIVE-5   the pack's solved levels and the W3 oracle must AGREE; disagreement
           refuses the name ``pack_integrity`` and never falls back (PIT-W4-15)
  LIVE-6   spool BEFORE commit — a failed spool withholds the transitions from
           the ledger AND the payload (PIT-W4-13)
  LIVE-7   a same-cycle re-run is deterministic and admits nothing twice
           (PIT-W4-9), and a mid-session restart duplicates nothing (PIT-W4-10)
  LIVE-8   the four quote rules, each reachable and each NAMED
  LIVE-9   quote-coverage honesty: a probe name with no quote is ``unavailable``
           and COUNTED, never dropped (PIT-W4-17)
  LIVE-10  C2 fires at K well above 20 inside a live episode — the frozen A5.3
           semantics, driven end-to-end through the live wrapper (PIT-W4-18)
  LIVE-11  the W4 write/network fence over the two modules Builder B added

EVERY LOAD-BEARING GUARD CARRIES A MUTATION CONTROL.  A test that only restates
today's behaviour proves the code does what it does; the controls below break
each property and watch the guard fire.

THE FIXTURES ARE SYNTHETIC AND SAY SO.  The substrate comes from
``test_entry_radar_w4_pack``'s deterministic trend+ripple corpus (no randomness,
no ``data/``, no ``site/``, no network); the tape comes from a quote book this
module builds by hand.  The C3 minute reader is never the real one — a transport
callable over generated rows stands in, so no test can open a socket.
"""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.entry_radar import challengers as ch
from engine.entry_radar import four_hour as fh
from engine.entry_radar import indicator_core as ic
from engine.entry_radar import live_eval as le
from engine.entry_radar import live_ledger as ll
from engine.entry_radar import live_pack as lp
from engine.entry_radar import vendor_minutes as vm
from engine.entry_radar.readings import canonical_readings
from engine.session_digest import session_window_et
from tests.test_entry_radar_w4_pack import (AS_OF, NEXT_SESSION, build,
                                            frame_from_closes, store,
                                            vshape_closes, washout_closes)

ROOT = Path(__file__).resolve().parents[1]
RADAR_DIR = ROOT / "engine" / "entry_radar"

#: W4's two BUILDER-B engine modules.  Named explicitly so the fence below
#: cannot go vacuous through a glob that matches nothing (Builder A's own guard
#: names ``live_pack.py``/``live_ledger.py`` the same way).
W4_BUILDER_B_MODULES = ("live_eval.py", "vendor_minutes.py")

#: The ONE module allowed to reach a vendor, and why.  ``vendor_minutes`` IS the
#: network seam C3 needs (design §3); everything else in the package must be
#: unable to fetch.  An exemption list beats widening the fence: the fence keeps
#: catching, and the exemption states out loud what was traded.
NETWORK_EXEMPT: dict[str, str] = {
    "vendor_minutes.py": "the designated C3 IntradayReader seam (W4 design §3) — "
                         "and even there the client is resolved lazily inside "
                         "default_transport, never at module import",
}


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

def et_now(minutes_after_open: float, session: date = NEXT_SESSION) -> datetime:
    """A pass instant, ``minutes_after_open`` into ``session``, in UTC."""
    return (session_window_et(session)[0]
            + timedelta(minutes=float(minutes_after_open))).astimezone(timezone.utc)


def quote_book(pack: lp.LivePack, *, multiple: float, ts: datetime,
               tickers=None, **overrides) -> dict:
    """A quote artifact in ``live_verify.load_live_quotes`` shape.

    ``prevClose`` defaults to each name's own pack ``as_of_close``, which is the
    AGREEING case — the basis audit passes and the engine is reached.  Tests that
    want a mismatch move it deliberately.
    """
    names = sorted(pack.substrate) if tickers is None else list(tickers)
    quotes = {}
    for ticker in names:
        row = pack.by_ticker().get(ticker)
        close = None if row is None else row.as_of_close
        quotes[ticker] = {"price": (close or 100.0) * float(multiple),
                          "ts": ts.timestamp() * 1000.0, "source": "polygon",
                          "basis": "trade", "prevClose": close}
        quotes[ticker].update(overrides)
    return {"asof": ts.isoformat(), "delayed_min": 15, "quotes": quotes}


def one_pass(pack, quotes, *, now, ledger=None, state_dir=None, **kwargs):
    """``run_pass`` with the test defaults: no spool sink, explicitly unspooled."""
    kwargs.setdefault("unspooled_ok", True)
    return le.run_pass(now=now, pack=pack, quotes=quotes,
                       ledger=ledger if ledger is not None else ll.LiveEpisodeLedger(None),
                       state_dir=state_dir, spool=kwargs.pop("spool", None), **kwargs)


def name_of(result: le.PassResult, ticker: str) -> le.NameResult:
    for row in result.names:
        if row.ticker == ticker:
            return row
    raise AssertionError(f"{ticker} is not in the pass result")


@pytest.fixture(scope="module")
def pack() -> lp.LivePack:
    return build()


# ---------------------------------------------------------------------------
# LIVE-1 — the basis audit runs BEFORE the engine
# ---------------------------------------------------------------------------

def test_LIVE1_a_basis_mismatch_darks_the_name_before_any_observation_exists(pack):
    """No tape, no observation, no reading with a verdict — and no re-basing.

    W3-1 carried forward: the seam between an adjusted daily half and a raw
    intraday half FABRICATES a move, and a fabricated move fabricates a cross.
    The refusal has to happen before the observation is built, which is what
    ``observations == ()`` proves — a name darked afterwards would still have
    computed the very number the audit exists to prevent.
    """
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    for row in book["quotes"].values():
        row["prevClose"] = float(row["prevClose"]) * 2.0
    result = one_pass(pack, book, now=now)

    wash = name_of(result, "WASH")
    assert wash.state == "unavailable"
    assert wash.reasons == ("basis_mismatch",)
    assert wash.observations == (), \
        "the engine was reached: an observation exists for a name the audit refused"
    assert wash.runs == ()
    assert result.payload["transitions"] == [] and result.payload["events"] == []
    assert result.health["basis"]["mismatched_n"] == len(pack.substrate)
    assert sorted(result.health["basis"]["refused"]) == sorted(pack.substrate)


def test_LIVE1_the_mismatched_row_carries_the_numbers_that_refused_it(pack):
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    for row in book["quotes"].values():
        row["prevClose"] = float(row["prevClose"]) * 2.0
    audit = name_of(one_pass(pack, book, now=now), "WASH").basis

    assert audit["mismatch"] is True
    assert audit["gap_pct"] > audit["tolerance_pct"]
    for key in ("as_of_close", "prev_close", "gap_pct", "tolerance_pct"):
        assert audit[key] is not None, f"the receipt cannot be audited without {key}"


def test_LIVE1_CONTROL_an_agreeing_basis_reaches_the_engine(pack):
    """The mutation control: without the gap the same pass evaluates."""
    now = et_now(32)
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2)),
                      now=now)
    wash = name_of(result, "WASH")
    assert wash.state == "evaluated" and wash.observations
    assert result.health["basis"]["mismatched_n"] == 0


def test_LIVE1_an_absent_prev_close_is_UNVERIFIED_not_verified(pack):
    """A comparison we could not make is not a comparison that passed.

    Absence is deliberately NOT a mismatch — §5's row is about a gap past
    tolerance — so the name still evaluates.  What must not happen is the feed
    going quiet on ``prevClose`` and producing the same zero-mismatch count as a
    healthy pass, which is what ``unchecked_n`` and the health reason exist for.
    """
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    for row in book["quotes"].values():
        row["prevClose"] = None
    result = one_pass(pack, book, now=now)

    assert name_of(result, "WASH").state == "evaluated"
    assert result.health["basis"]["audited_n"] == 0
    assert result.health["basis"]["unchecked_n"] == len(pack.substrate)
    assert "basis_unverified" in result.health["reasons"]


# ---------------------------------------------------------------------------
# LIVE-2 — the journal
# ---------------------------------------------------------------------------

def test_LIVE2_a_journal_written_under_another_pack_refuses_re_derivation(tmp_path, pack):
    """The mechanical no-backfill law (§7.1), enforced at the door.

    Re-deriving a session against a different substrate is exactly the backfill
    the contract forbids: every K and D in the session would move.  The journal
    refuses instead of silently recomputing.
    """
    journal = le.SessionJournal(tmp_path)
    journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                         pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                         price_basis=pack.price_basis)
    with pytest.raises(le.LiveEvalError, match="backfill"):
        journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                             pack_as_of=pack.as_of, pack_hash="a-different-pack",
                             price_basis=pack.price_basis)


def test_LIVE2_CONTROL_the_same_pack_hash_reopens_the_same_record(tmp_path, pack):
    journal = le.SessionJournal(tmp_path)
    first = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                 pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                 price_basis=pack.price_basis)
    again = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                 pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                 price_basis=pack.price_basis)
    assert again is first


def test_LIVE2_a_backdated_point_is_REFUSED_and_counted(tmp_path, pack):
    """A vendor timestamp at or before the last point would rewrite history.

    ``sample_session_path`` admits every minute knowable by an interval's END, so
    a backdated row lands INSIDE an already-published interval and changes a
    reading somebody has already seen.  A FUTURE tick cannot do this — that is
    why PIT-W4-1 is provable by construction — so this is the one direction the
    journal has to police itself.
    """
    journal = le.SessionJournal(tmp_path)
    record = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    base = et_now(32)
    assert journal.append_point(record, ts=base, price=100.0, basis="trade",
                                source="polygon", basis_audit={}) is True
    assert journal.append_point(record, ts=base - timedelta(minutes=5), price=99.0,
                                basis="trade", source="polygon", basis_audit={}) is False
    assert journal.append_point(record, ts=base, price=98.0, basis="trade",
                                source="polygon", basis_audit={}) is False, \
        "a DUPLICATE timestamp is as dangerous as a backdated one"
    assert len(record.points) == 1
    assert [row["reason"] for row in record.refused] == \
           ["not_after_last_point", "not_after_last_point"]


def test_LIVE2_a_prior_session_is_replayed_VERBATIM(tmp_path, pack):
    """Multi-day episodes read the observations that WERE computed, not new ones."""
    journal = le.SessionJournal(tmp_path)
    record = journal.open_session(session=AS_OF.isoformat(), ticker="WASH",
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    minted = builder.observations(_flat_tape(NEXT_SESSION, 90.0))
    journal.freeze_observations(record, minted)
    journal.flush(record)

    fresh = le.SessionJournal(tmp_path)
    assert fresh.replay(AS_OF.isoformat(), "WASH") == minted


def test_LIVE2_an_unknown_journal_field_refuses_rather_than_dropping_it(pack):
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    row = le.observation_to_dict(builder.observations(_flat_tape(NEXT_SESSION, 90.0))[0])
    row["forward_return_21d"] = 0.1
    with pytest.raises(le.LiveEvalError, match="unknown field"):
        le.observation_from_dict(row)


def recovery_tape(pack: lp.LivePack, ticker: str = "WASH") -> ch.SessionTape:
    """A deep washout that then RECOVERS hard — the A5.3 discriminating shape.

    Six flat intervals at 10% below the confirmed close arm C1, then a steady
    2%-per-interval climb carries %K back through 20 and on past 33.  A gentler
    recovery still fires C2, but every fire lands under K=20 — and a fixture like
    that cannot tell the frozen semantics from an oversold-at-turn gate, which is
    the whole point of PIT-W4-18.  The numbers are tuned to that discrimination
    and are not arbitrary: at ``slope=0.012`` the highest firing K is 21.5, which
    would let a re-introduced ``K < 20`` gate through on a rounding argument.
    """
    low = float(pack.by_ticker()[ticker].as_of_close) * 0.90
    open_dt, _close = session_window_et(NEXT_SESSION)
    minutes = []
    for step in range(30):
        price = low if step < 6 else low * (1.0 + 0.020 * (step - 5))
        minutes.append(ch.MinuteBar(start=open_dt + timedelta(minutes=5 * step),
                                    open=price, high=price, low=price, close=price))
    return ch.SessionTape(session=NEXT_SESSION, minutes=tuple(minutes),
                          price_basis=ch.BASIS_ADJUSTED, vintage="w4-recovery-fixture")


def _flat_tape(session: date, price: float, *, minutes: int = 60) -> ch.SessionTape:
    open_dt, _close = session_window_et(session)
    return ch.SessionTape(
        session=session,
        minutes=tuple(ch.MinuteBar(start=open_dt + timedelta(minutes=m), open=price,
                                   high=price, low=price, close=price)
                      for m in range(0, minutes, 5)),
        price_basis=ch.BASIS_ADJUSTED, vintage="w4-live-fixture")


# ---------------------------------------------------------------------------
# LIVE-3 — PIT-W4-16, the byte-parity pin
# ---------------------------------------------------------------------------

def _parity_case(pack, ticker, tape, *, daily=None):
    daily = daily if daily is not None else le.pack_daily_history(pack, ticker)
    builder = le.IncrementalObservationBuilder(ticker=ticker, daily=daily,
                                               session=tape.session)
    incremental = builder.observations(tape)
    oracle = ch.build_observation_path(ticker=ticker, daily=daily, tapes=[tape])
    return incremental, oracle


@pytest.mark.parametrize("ticker", ["WASH", "VSHAPE", "FLAT", "SHORT", "STALE"])
def test_LIVE3_incremental_construction_is_byte_identical_to_the_oracle(pack, ticker):
    """PIT-W4-16.  The ONE derived construction in W4, pinned across the corpus.

    ``build_observation_path`` recomputes the chain per sampled point;
    ``IncrementalObservationBuilder`` computes the per-session preamble once and
    memoises the chain by sampled close.  Identical BY CONSTRUCTION is a claim,
    and a claim about a second implementation is exactly the thing that drifts —
    so it is asserted on the observations themselves AND on the canonical
    readings the detectors produce from them.
    """
    tape = _flat_tape(NEXT_SESSION, 90.0)
    incremental, oracle = _parity_case(pack, ticker, tape)
    assert incremental == oracle
    assert canonical_readings(ch.run_c1(incremental).readings) == \
           canonical_readings(ch.run_c1(oracle).readings)


def test_LIVE3_parity_holds_across_a_GAPPED_tape(pack):
    """An interval with no prints carries forward — on both paths identically."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    minutes = tuple(ch.MinuteBar(start=open_dt + timedelta(minutes=m), open=90.0,
                                 high=90.0, low=90.0, close=90.0)
                    for m in (0, 5, 55, 60))          # a 45-minute hole
    tape = ch.SessionTape(session=NEXT_SESSION, minutes=minutes,
                          price_basis=ch.BASIS_ADJUSTED, vintage="gap")
    incremental, oracle = _parity_case(pack, "WASH", tape)
    assert incremental == oracle
    assert any(o.sampled_close is not None and not o.availability == "unavailable"
               for o in incremental)


def test_LIVE3_parity_holds_on_a_BASIS_MISMATCHED_tape(pack):
    """The disagreeing-basis branch is a branch too, and it must match."""
    tape = ch.SessionTape(session=NEXT_SESSION,
                          minutes=_flat_tape(NEXT_SESSION, 90.0).minutes,
                          price_basis=ch.BASIS_RAW, vintage="raw")
    incremental, oracle = _parity_case(pack, "WASH", tape)
    assert incremental == oracle
    assert {o.availability for o in incremental} == {"unavailable"}
    assert {o.atr_prior_confirmed for o in incremental} == {None}


def test_LIVE3_parity_holds_on_a_STALE_history(pack):
    """A stale confirmed frame yields ``stale``+None on both paths, never False."""
    incremental, oracle = _parity_case(pack, "STALE", _flat_tape(NEXT_SESSION, 90.0))
    assert incremental == oracle
    assert {o.availability for o in incremental} == {"stale"}
    assert {o.k for o in incremental} == {None}
    assert {r.condition_met for r in ch.run_c1(incremental).readings} == {None}


def test_LIVE3_parity_holds_on_an_EARLY_CLOSE_session(pack):
    """The grid clips to the real close — identically on both constructions."""
    from engine.session_digest import is_early_close
    early = next((d for d in (date(2026, 11, 27), date(2026, 12, 24))
                  if is_early_close(d)), None)
    if early is None:                                   # pragma: no cover
        pytest.skip("no early close in the reference window to exercise")
    daily = ch.DailyHistory(frame=frame_from_closes(washout_closes(), AS_OF)
                            .loc[:, ["high", "low", "close"]],
                            price_basis=ch.BASIS_ADJUSTED, vintage="w4-fixture")
    tape = _flat_tape(early, 90.0)
    incremental, oracle = _parity_case(pack, "WASH", tape, daily=daily)
    assert incremental == oracle
    open_dt, close_dt = session_window_et(early)
    assert (close_dt - open_dt) < timedelta(minutes=390), "not actually an early close"
    assert incremental[-1].observed_at == ch.utc_iso(close_dt)


def test_LIVE3_the_chain_memo_is_keyed_by_PRICE_so_a_changed_point_recomputes(pack):
    """A carry-forward interval is free; a DIFFERENT price is a different key."""
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    first = builder.chain_at(90.0)
    assert builder.chain_at(90.0) is first, "the same price must hit the memo"
    assert builder.chain_at(91.0) != first, "a different price must recompute"


# ---------------------------------------------------------------------------
# LIVE-4 — the grid is truncated at `now`
# ---------------------------------------------------------------------------

def test_LIVE4_a_mid_session_pass_emits_no_reading_stamped_after_now(pack):
    """The full-session sampler would; the live lane must not.

    ``sample_session_path`` builds EVERY interval of the session and carries the
    last known value across the empty ones — correct for a replay, and a leak
    mid-session: a 10:02 pass would otherwise emit an observation stamped 15:55
    carrying the 10:00 price, and C1 could arm at an instant that has not
    happened yet.
    """
    now = et_now(32)
    result = one_pass(pack, quote_book(pack, multiple=0.97,
                                       ts=now - timedelta(minutes=2)), now=now)
    observations = name_of(result, "WASH").observations
    assert observations, "the pass produced no observations at all"
    assert all(o.observed_at <= le._iso(now) for o in observations)
    assert len(observations) < 78, \
        "78 intervals is the WHOLE session — the grid was not truncated at now"


def test_LIVE4_CONTROL_a_replay_with_no_now_yields_the_whole_session(pack):
    """``now=None`` is the replay case — the SAME contract as four_hour_buckets."""
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    tape = _flat_tape(NEXT_SESSION, 90.0)
    assert len(builder.observations(tape, now=None)) == 78
    cut = session_window_et(NEXT_SESSION)[0] + timedelta(minutes=30)
    assert len(builder.observations(tape, now=cut)) == 6


def test_LIVE4_an_arm_instant_is_never_in_the_future(tmp_path, pack):
    now = et_now(37)
    ledger = ll.LiveEpisodeLedger(tmp_path)
    one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)), now=et_now(32),
             ledger=ledger, state_dir=tmp_path)
    result = one_pass(pack, quote_book(pack, multiple=0.96, ts=et_now(35)), now=now,
                      ledger=ledger, state_dir=tmp_path)
    for transition in result.payload["transitions"]:
        assert str(transition["at"]) <= le._iso(now)


# ---------------------------------------------------------------------------
# LIVE-5 — PIT-W4-15, the threshold cross-check
# ---------------------------------------------------------------------------

def _with_moved_c1_level(pack: lp.LivePack, ticker: str,
                         factor: float) -> lp.LivePack:
    from dataclasses import replace as dreplace
    names = tuple(
        dreplace(row, c1_arm_price=dreplace(row.c1_arm_price,
                                            price=(row.c1_arm_price.price or 100.0)
                                            * factor))
        if row.ticker == ticker and row.c1_arm_price.price is not None else row
        for row in pack.names)
    return lp.LivePack(schema=pack.schema, as_of=pack.as_of,
                       next_session=pack.next_session, built_at=pack.built_at,
                       price_basis=pack.price_basis, spec_hashes=pack.spec_hashes,
                       probe_set=pack.probe_set, names=names,
                       substrate=pack.substrate, pack_hash=pack.pack_hash)


def test_LIVE5_a_corrupted_pack_level_refuses_the_name_pack_integrity(tmp_path, pack):
    """Fail CLOSED.  An evaluator that disagrees with its own frozen thresholds
    does not know which of the two answers is wrong, so it produces neither."""
    corrupt = _with_moved_c1_level(pack, "WASH", 0.2)
    now = et_now(32)
    result = one_pass(corrupt, quote_book(corrupt, multiple=0.97,
                                          ts=now - timedelta(minutes=2)),
                      now=now, state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path))
    later = one_pass(corrupt, quote_book(corrupt, multiple=0.96, ts=et_now(35)),
                     now=et_now(37), state_dir=tmp_path,
                     ledger=ll.LiveEpisodeLedger(tmp_path))
    wash = name_of(later, "WASH")
    assert wash.state == "unavailable"
    assert wash.reasons == ("pack_integrity",)
    assert wash.cross_check["verdict"] == "disagree"
    assert wash.runs == (), "a refused name must produce no run at all"
    assert not any(t.get("ticker") == "WASH" for t in later.payload["transitions"])
    assert "pack_integrity:1" in later.health["reasons"]
    assert result is not None


def test_LIVE5_CONTROL_an_honest_pack_agrees_and_evaluates(tmp_path, pack):
    # The quote's vendor ts must be old enough for its minute bar to be KNOWABLE
    # by the end of an interval that has itself already ended — a print at 10:05
    # is only lawful from the 10:10 interval on, so a pass at 10:07 reading a
    # 10:05 print has nothing to check yet.  That one-interval publication lag is
    # the knowability law working, not a gap to close.
    result = one_pass(pack, quote_book(pack, multiple=0.96, ts=et_now(30)),
                      now=et_now(37), state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path))
    wash = name_of(result, "WASH")
    assert wash.state == "evaluated"
    assert wash.cross_check["verdict"] in ("agree", "boundary_band")
    assert not any("pack_integrity" in r for r in result.health["reasons"])


def test_LIVE5_a_price_at_the_solved_level_is_the_BOUNDARY_BAND_not_a_disagreement(pack):
    """The level was bisected to a relative tolerance; at that distance both
    answers are correct readings of the same boundary."""
    row = pack.by_ticker()["WASH"]
    assert row.c1_arm_price.price is not None
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    obs = builder.observations(_flat_tape(NEXT_SESSION,
                                          float(row.c1_arm_price.price)))[-1]
    assert le.cross_check(row, obs)["c1"]["verdict"] == "boundary_band"


def test_LIVE5_a_degenerate_level_with_no_verdict_is_UNCHECKED_never_a_pass(pack):
    """``flat_rsi_nan``/``non_monotone`` are NULLS — a hole, not an answer."""
    row = pack.by_ticker()["FLAT"]
    assert row.c1_arm_price.no_threshold_exists
    daily = le.pack_daily_history(pack, "FLAT")
    builder = le.IncrementalObservationBuilder(ticker="FLAT", daily=daily,
                                               session=NEXT_SESSION)
    checks = le.cross_check(row, builder.observations(_flat_tape(NEXT_SESSION, 100.0))[-1])
    assert checks["verdict"] == "unchecked"
    assert checks["c1"]["pack"] is None


# ---------------------------------------------------------------------------
# LIVE-6 — PIT-W4-13, spool before commit
# ---------------------------------------------------------------------------

class DeadSpool(ll.EventSpool):
    """A sink that always fails.  Nothing may be admitted behind it."""

    def append_pass(self, payload, *, session, stamp, pass_id):  # noqa: D102
        return None


def _arm_over_two_passes(pack, ledger, tmp_path, *, spool=None, unspooled_ok=True):
    le.run_pass(now=et_now(32), pack=pack,
                quotes=quote_book(pack, multiple=0.97, ts=et_now(30)), ledger=ledger,
                state_dir=tmp_path, spool=spool, unspooled_ok=unspooled_ok)
    return le.run_pass(now=et_now(37), pack=pack,
                       quotes=quote_book(pack, multiple=0.96, ts=et_now(35)),
                       ledger=ledger, state_dir=tmp_path, spool=spool,
                       unspooled_ok=unspooled_ok)


def test_LIVE6_a_failed_spool_withholds_from_BOTH_the_ledger_and_the_payload(tmp_path, pack):
    """Spool-before-consume (§0).  A transition that is not durable before it is
    admitted is a false start nobody can reconstruct."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    result = _arm_over_two_passes(pack, ledger, tmp_path,
                                  spool=DeadSpool(local_dir=tmp_path),
                                  unspooled_ok=False)
    assert result.delta.transitions, "the fixture produced nothing to withhold"
    assert result.committed is False
    assert result.exit_code == 4
    assert result.payload["transitions"] == [], \
        "a payload showing a withheld transition is the second source of truth"
    assert result.payload["events"] == []
    assert ledger.transitions == ()
    assert result.health["state"] == "degraded"
    assert "spool_failed" in result.health["reasons"]


def test_LIVE6_CONTROL_a_healthy_spool_commits_and_publishes(tmp_path, pack):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    result = _arm_over_two_passes(pack, ledger, tmp_path,
                                  spool=ll.EventSpool(local_dir=tmp_path),
                                  unspooled_ok=False)
    assert result.committed is True and result.exit_code == 0
    assert result.payload["transitions"] and ledger.transitions
    assert result.spool_key and result.spool_key.startswith(ll.EVENT_SPOOL_PREFIX)
    spooled = json.loads(next(Path(tmp_path).rglob("*-entry_radar_live.json"))
                         .read_text(encoding="utf-8"))
    assert spooled["schema"] == ll.SCHEMA_ENTRY_RADAR_EVENTS
    assert spooled["pack"]["pack_hash"] == pack.pack_hash


def test_LIVE6_the_retry_after_a_spool_failure_is_once_effective(tmp_path, pack):
    """The withheld transitions land on the NEXT pass, exactly once.

    "Once-effective" is a claim about ADDRESSES, not about pass counts: a later
    pass legitimately produces NEW transitions because its tape is longer, so a
    test asserting "the next pass has nothing" would be asserting the fixture
    stopped moving rather than that the retry was safe.  What must hold is that
    no address is ever admitted twice, and that re-running the SAME instant over
    the SAME tape admits nothing at all.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    withheld = _arm_over_two_passes(pack, ledger, tmp_path,
                                    spool=DeadSpool(local_dir=tmp_path),
                                    unspooled_ok=False)
    assert withheld.delta.transitions and ledger.transitions == ()

    healed = le.run_pass(now=et_now(42), pack=pack,
                         quotes=quote_book(pack, multiple=0.955, ts=et_now(40)),
                         ledger=ledger, state_dir=tmp_path,
                         spool=ll.EventSpool(local_dir=tmp_path))
    assert healed.committed is True
    recovered = {ll.transition_address(t) for t in ledger.transitions}
    assert recovered >= {ll.transition_address(t) for t in withheld.delta.transitions}, \
        "the transitions withheld by the failed spool were never recovered"
    assert len(recovered) == len(ledger.transitions), "an address was admitted twice"

    replay = le.run_pass(now=et_now(42), pack=pack,
                         quotes=quote_book(pack, multiple=0.955, ts=et_now(40)),
                         ledger=ledger, state_dir=tmp_path,
                         spool=ll.EventSpool(local_dir=tmp_path))
    assert replay.delta.transitions == ()
    assert len(ledger.transitions) == len(recovered)


# ---------------------------------------------------------------------------
# LIVE-7 — PIT-W4-9 / -10, determinism and restart
# ---------------------------------------------------------------------------

def test_LIVE7_a_same_cycle_rerun_is_deterministic_and_admits_nothing(tmp_path, pack):
    """PIT-W4-9 asks TWO things and they are different questions: the state map
    must be byte-identical, and the delta must be empty.  Comparing whole
    payloads conflates them — the second run legitimately reports no new
    transitions, which is the very thing the test wanted to see."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    first = _arm_over_two_passes(pack, ledger, tmp_path)
    again = le.run_pass(now=et_now(37), pack=pack,
                        quotes=quote_book(pack, multiple=0.96, ts=et_now(35)),
                        ledger=ledger, state_dir=tmp_path, spool=None,
                        unspooled_ok=True)
    assert le.state_map(first.payload) == le.state_map(again.payload)
    assert again.delta.empty is True
    assert again.payload["transitions"] == []


def test_LIVE7_a_mid_session_restart_duplicates_nothing(tmp_path, pack):
    """PIT-W4-10.  A restart re-derives from the journal on disk; the ledger it
    reloads already knows every address the previous process admitted."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_over_two_passes(pack, ledger, tmp_path)
    ledger.save()
    before = len(ledger.transitions)
    assert before, "the fixture admitted nothing to duplicate"

    restarted = ll.LiveEpisodeLedger.load(tmp_path)
    result = le.run_pass(now=et_now(42), pack=pack,
                         quotes=quote_book(pack, multiple=0.96, ts=et_now(35)),
                         ledger=restarted, state_dir=tmp_path, spool=None,
                         unspooled_ok=True)
    assert result.delta.transitions == ()
    assert result.delta.events == ()
    assert len(restarted.transitions) == before


def test_LIVE7_the_journal_survives_the_restart_and_is_still_pinned(tmp_path, pack):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _arm_over_two_passes(pack, ledger, tmp_path)
    record = le.SessionJournal(tmp_path).read(NEXT_SESSION.isoformat(), "WASH")
    assert record is not None
    assert record.pack_hash == pack.pack_hash
    assert len(record.points) == 2
    assert record.observations


# ---------------------------------------------------------------------------
# LIVE-8 / LIVE-9 — the quote rules and coverage honesty
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("basis", sorted(le.CARRIED_QUOTE_BASES))
def test_LIVE8_a_carried_quote_is_excluded_as_a_print(pack, basis):
    """§3b: ``prev``/``day`` republish a PRIOR close.  Admitting one would append
    yesterday's number as today's provisional bar — a fabricated flat day."""
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    book["quotes"]["WASH"]["basis"] = basis
    wash = name_of(one_pass(pack, book, now=now), "WASH")
    assert wash.state == "unavailable" and wash.reasons == ("carried_quote",)
    assert wash.observations == ()


def test_LIVE8_a_premarket_print_is_excluded(pack):
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    book["quotes"]["WASH"]["ts"] = (session_window_et(NEXT_SESSION)[0]
                                    - timedelta(hours=1)).timestamp() * 1000.0
    wash = name_of(one_pass(pack, book, now=now), "WASH")
    assert wash.state == "unavailable" and wash.reasons == ("premarket_quote",)


def test_LIVE8_a_quote_past_the_derived_budget_is_stale(pack):
    """The budget is ``meta.delayed_min + slack`` — DERIVED.  A budget tighter
    than the declared feed delay cannot be met at any polling speed and darks the
    whole universe while looking exactly like a healthy lane."""
    now = et_now(180)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=90))
    assert le.quote_budget(book) == 25.0
    wash = name_of(one_pass(pack, book, now=now), "WASH")
    assert wash.state == "unavailable" and wash.reasons == ("stale_quote",)
    assert wash.quote.age_min > wash.quote.max_age_min


def test_LIVE8_CONTROL_a_fresh_in_session_print_is_admitted(pack):
    now = et_now(180)
    wash = name_of(one_pass(pack, quote_book(pack, multiple=0.97,
                                             ts=now - timedelta(minutes=2)),
                            now=now), "WASH")
    assert wash.state == "evaluated" and wash.quote.state == "ok"


def test_LIVE9_a_probe_name_with_no_quote_is_unavailable_and_COUNTED(pack):
    """PIT-W4-17.  Never dropped: a name missing from the payload is
    indistinguishable from a name that is not in the probe set."""
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    book["quotes"].pop("WASH")
    result = one_pass(pack, book, now=now)

    assert name_of(result, "WASH").reasons == ("no_quote",)
    assert "WASH" in {row["ticker"] for row in result.payload["names"]}
    expected = f"{len(pack.substrate) - 1}/{len(pack.substrate)}"
    assert result.health["inputs"]["quotes"]["coverage"] == expected
    assert f"quote_coverage:{expected}" in result.health["reasons"]
    assert result.health["dark"]["no_quote"] == 1


def test_LIVE9_a_name_with_no_substrate_is_unavailable_and_named(pack):
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(32), tickers=sorted(pack.substrate) + ["GHOST"])
    assert name_of(result, "GHOST").reasons == ("no_substrate",)
    assert result.health["dark"]["no_substrate"] == 1


# ---------------------------------------------------------------------------
# LIVE-10 — PIT-W4-18, no oversold-at-turn requirement
# ---------------------------------------------------------------------------

def test_LIVE10_c2_fires_above_K20_inside_a_live_episode_through_the_live_wrapper(pack):
    """A5.3's frozen semantics, driven END TO END rather than on a bare path.

    The washout is the EPISODE'S HISTORY and the turn is the event, so a variant
    may lawfully fire after %K has recovered above 20 while the C1 episode is
    still nonterminal.  Re-introducing a current-K<20 gate is the single change
    the contract most explicitly forbids, and it would be invisible in a suite
    that only ever drove deeply oversold tapes.
    """
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    path = builder.observations(recovery_tape(pack))

    c1 = ch.run_c1(path)
    assert c1.episode is not None, "the fixture never armed C1"
    c2 = ch.run_c2(path, c1.episode)
    fired = {v: stamps for v, stamps in c2.fires.items() if stamps}
    assert fired, "no C2 variant fired in the recovery fixture"

    ks = {o.observed_at: o.k for o in path}
    above = [(variant, at) for variant, stamps in fired.items() for at in stamps
             if ks.get(at) is not None and ks[at] >= ic.OVERSOLD]
    assert above, (
        "every C2 fire happened below K=20 — this fixture cannot distinguish the "
        "frozen A5.3 semantics from an oversold-at-turn gate")
    assert max(ks[at] for _v, at in above) > 24.0


# ---------------------------------------------------------------------------
# LIVE-13 — the C3 minute budget, and the injection surface
# ---------------------------------------------------------------------------

def _bucket_reader(calls: list):
    """A reader double in the ``IntradayReader`` shape, over generated rows."""
    from engine.entry_radar import four_hour as fh

    def reader(ticker, session):
        calls.append((ticker, session))
        open_dt, close_dt = session_window_et(session)
        rows, cursor, index = [], open_dt, 0
        while cursor < close_dt:
            price = 90.0 * (1.0 + 0.004 * ((index % 23) - 11))
            rows.append((cursor, price, price * 1.001, price * 0.999, price, 100.0))
            cursor += timedelta(minutes=5)
            index += 1
        return fh.tape_from_rows(session, rows, price_basis=ch.BASIS_ADJUSTED,
                                 vintage="w4-c3-fixture")
    return reader


def test_LIVE13_the_c3_budget_defers_the_overflow_and_NAMES_it(tmp_path, pack):
    """A deferred 4H lane is not a name with no turn, and must not look like one.

    A cold C3 name costs one request per warm-up session (measured: 61 for one
    name), so an unbounded pass over a washed cohort cannot finish inside a
    5-minute cadence at any pacing.  The bound is not a haircut on the signal —
    completed sessions are cached permanently, so a deferred name is fully warm
    within a few passes — but a silent deferral would be indistinguishable from a
    quiet 4H tape.
    """
    calls: list = []
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(37), state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path),
                      intraday_reader=_bucket_reader(calls),
                      config=le.LiveEvalConfig(c3_max_names_per_pass=1))

    deferred = [n for n in result.names if "c3_deferred" in n.lanes]
    assert len(deferred) == 1
    assert deferred[0].lanes["c3_deferred"]["reason"] == "c3_budget_deferred"
    assert result.health["inputs"]["c3_reader"]["deferred_n"] == 1
    assert "c3_deferred:1" in result.health["reasons"]
    assert {t for t, _s in calls} == {n.ticker for n in result.names
                                      if "c3" in n.lanes}


def test_LIVE13_the_budget_choice_is_DETERMINISTIC(tmp_path, pack):
    """Two passes over the same state must make the same choice, or the whole
    idempotency battery is measuring dict ordering."""
    config = le.LiveEvalConfig(c3_max_names_per_pass=1)
    picks = []
    for _ in range(2):
        calls: list = []
        result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                          now=et_now(37), state_dir=tmp_path,
                          ledger=ll.LiveEpisodeLedger(tmp_path),
                          intraday_reader=_bucket_reader(calls),
                          config=config)
        picks.append(sorted(n.ticker for n in result.names if "c3" in n.lanes))
    assert picks[0] == picks[1]


def test_LIVE13_CONTROL_a_budget_covering_the_cohort_defers_nothing(tmp_path, pack):
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(37), state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path),
                      intraday_reader=_bucket_reader([]),
                      config=le.LiveEvalConfig(c3_max_names_per_pass=99))
    assert result.health["inputs"]["c3_reader"]["deferred_n"] == 0
    assert not any("c3_deferred" in r for r in result.health["reasons"])
    assert any("c3" in n.lanes for n in result.names), \
        "no name ran C3 at all — this control cannot distinguish a budget from a bug"


def test_LIVE13_c3_can_be_switched_off_entirely_without_darkening_C1_or_C2(
        tmp_path, pack):
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(37), state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path),
                      intraday_reader=_bucket_reader([]),
                      config=le.LiveEvalConfig(c3_enabled=False))
    wash = name_of(result, "WASH")
    assert "c3" not in wash.lanes and "c3_deferred" not in wash.lanes
    assert wash.lanes["c1"] and wash.lanes["c2"]
    assert result.health["inputs"]["c3_reader"]["fetched_n"] == 0


def test_LIVE13_a_reader_fault_darks_C3_and_never_the_pass(tmp_path, pack):
    """C3 is one lane of several.  A vendor outage must not stand down C1/C2."""
    def exploding(ticker, session):
        raise RuntimeError("vendor is down")

    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(30)),
                      now=et_now(37), state_dir=tmp_path,
                      ledger=ll.LiveEpisodeLedger(tmp_path),
                      intraday_reader=exploding)
    wash = name_of(result, "WASH")
    assert wash.state == "evaluated" and wash.lanes["c1"]
    assert "c3" not in wash.lanes
    assert result.health["inputs"]["c3_reader"]["errors"] > 0
    assert any(r.startswith("c3_reader_errors:") for r in result.health["reasons"])


def test_LIVE13_the_quote_slack_override_binds(pack):
    """``LiveEvalConfig`` is the injection surface; an override nothing reads is
    a knob that lies.  Each override below changes an OUTCOME, not just a number.

    The 20-minute-old print sits inside the shipped budget (15 declared + 10
    slack) and outside a zero-slack one, so the SAME quote lands on both sides of
    the gate depending only on the config.
    """
    now = et_now(180)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=20))
    assert le.quote_budget(book) == 25.0
    assert name_of(one_pass(pack, book, now=now), "WASH").quote.state == "ok"

    assert le.quote_budget(book, slack_min=0.0) == 15.0
    tightened = one_pass(pack, book, now=now,
                         config=le.LiveEvalConfig(quote_slack_min=0.0))
    assert name_of(tightened, "WASH").reasons == ("stale_quote",)


def test_LIVE13_the_basis_tolerance_override_binds(pack):
    """A 0.1% gap passes the shipped 0.25% tolerance and fails a tighter one.

    Staged as a REAL gap rather than an exact match: with ``prevClose`` identical
    to the pack close the gap is 0.0 and no tolerance is tight enough to refuse
    it, so the parametrised version of this test passed for the wrong reason.
    """
    now = et_now(180)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    for row in book["quotes"].values():
        row["prevClose"] = float(row["prevClose"]) * 1.001

    default = name_of(one_pass(pack, book, now=now), "WASH")
    assert default.basis["mismatch"] is False and default.state == "evaluated"

    tightened = name_of(one_pass(pack, book, now=now,
                                 config=le.LiveEvalConfig(basis_tolerance_pct=0.01)),
                        "WASH")
    assert tightened.basis["mismatch"] is True
    assert tightened.reasons == ("basis_mismatch",)


def test_LIVE13_the_window_grace_override_binds(pack):
    """The shipped grace keeps a pass 30 seconds past the close; zero does not."""
    just_after = et_now(390.5)
    assert le.in_window(just_after)[0] is True
    assert le.in_window(just_after, grace_min=0.0) == (False, "post_close",
                                                       NEXT_SESSION)
    result = one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(380)),
                      now=just_after,
                      config=le.LiveEvalConfig(window_end_grace_min=0.0))
    assert result.health["state"] == "out_of_window"


# ---------------------------------------------------------------------------
# LIVE-11 — the W4 write / network fence over Builder B's modules
# ---------------------------------------------------------------------------

def _module_ast(name: str) -> ast.Module:
    return ast.parse((RADAR_DIR / name).read_text(encoding="utf-8"))


def _string_constants(tree: ast.AST) -> list[str]:
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


@pytest.mark.parametrize("name", W4_BUILDER_B_MODULES)
def test_LIVE11_no_module_names_a_data_path(name):
    """The W5 writer is a separate lane; W4's durable footprint is ZERO.

    Docstrings are stripped first — the modules DISCUSS ``data/`` at length, and
    a grep that cannot tell prose from code is a guard that gets disabled.
    """
    tree = _module_ast(name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    offenders = [text for text in _string_constants(tree)
                 if text.startswith("data/") or "/data/" in text]
    assert offenders == [], f"{name} names a data/ path: {offenders}"


@pytest.mark.parametrize("name", W4_BUILDER_B_MODULES)
def test_LIVE11_no_module_imports_a_protected_module(name):
    """Radar imports nothing from Prophet, the entry gate, or ``engine.technicals``.

    The W1 leaf-discipline precedent: a shared import would make a Prophet change
    a Radar change, and the two programs are allowed to diverge.
    """
    banned = ("engine.prophet_", "engine.technicals", "engine.entry_signal",
              "engine.signal_gate")
    found = []
    for node in ast.walk(_module_ast(name)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    offenders = [mod for mod in found if any(mod.startswith(b) for b in banned)]
    assert offenders == [], f"{name} imports a protected module: {offenders}"


@pytest.mark.parametrize("name", W4_BUILDER_B_MODULES)
def test_LIVE11_no_module_imports_a_network_client_at_module_level(name):
    """``vendor_minutes`` is the ONE seam allowed to reach a vendor, and even it
    resolves the client lazily — so no ``engine`` import can open a socket."""
    network = ("requests", "httpx", "urllib", "socket", "boto3", "s3fs", "aiohttp")
    tree = _module_ast(name)
    top: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.append(node.module.split(".")[0])
    offenders = [mod for mod in top if mod in network]
    assert offenders == [], (
        f"{name} imports {offenders} at module level; "
        f"{NETWORK_EXEMPT.get(name, 'this module has no vendor exemption')}")


def test_LIVE11_the_network_exemption_is_real_and_not_dead_weight():
    """An exemption that names a module which never fetches hides a widened fence."""
    assert NETWORK_EXEMPT, "an empty exemption set makes the fence untestable"
    for name in NETWORK_EXEMPT:
        assert (RADAR_DIR / name).is_file()
        body = (RADAR_DIR / name).read_text(encoding="utf-8")
        assert "collectors.polygon_options" in body, \
            f"{name} is exempted as the vendor seam but reaches no vendor"


@pytest.mark.parametrize("name", W4_BUILDER_B_MODULES)
def test_LIVE11_no_module_writes_a_columnar_artifact(name):
    body = (RADAR_DIR / name).read_text(encoding="utf-8")
    for banned in ("to_parquet", "to_csv", "to_feather"):
        assert banned not in body, f"{name} calls {banned}"


# ---------------------------------------------------------------------------
# W4R — round-1 adversarial review regressions (pass mechanics half)
#
# One named test per adjudicated finding.  These are not restatements of today's
# behaviour: every one of them was REPRODUCED against this fixture corpus before
# the fix, and each asserts the property the reproduction violated.  Where the
# guard is load-bearing a CONTROL breaks it back and watches the guard fire.
# ---------------------------------------------------------------------------

def _rising_tape(session: date, *, base: float = 90.0, n: int = 12,
                 step: float = 0.4) -> ch.SessionTape:
    """A tape with a DISTINCT price per sampled interval.

    The corpus's flat tape gives the chain memo exactly one key, so a memo that
    never worked and a memo that works perfectly cost the same on it — which is
    how the O(1) claim went unmeasured.  One price per interval makes the chain
    call count equal the interval count, and the difference visible.
    """
    open_dt, _close = session_window_et(session)
    return ch.SessionTape(
        session=session,
        minutes=tuple(ch.MinuteBar(start=open_dt + timedelta(minutes=5 * i),
                                   open=base + step * i, high=base + step * i,
                                   low=base + step * i, close=base + step * i)
                      for i in range(n)),
        price_basis=ch.BASIS_ADJUSTED, vintage="w4r-rising")


def _function_ast(name: str):
    tree = ast.parse((RADAR_DIR / "live_eval.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in live_eval.py")


class _ExplodingLedger(ll.LiveEpisodeLedger):
    """A ledger whose ``apply_run`` raises for ONE name.

    ``apply_run`` used to sit OUTSIDE the per-name try entirely, so a
    ``LedgerError`` from a record's own validation ended the whole pass.
    """

    def __init__(self, state_dir=None, *, ticker: str = "WASH") -> None:
        super().__init__(state_dir)
        self.boom = ticker

    def apply_run(self, *, ticker, **kwargs):  # noqa: D102
        if ticker == self.boom:
            raise ll.LedgerError("injected: an episode record refused validation")
        return super().apply_run(ticker=ticker, **kwargs)


# --- C2: one bad name cannot kill the pass ---------------------------------

@pytest.mark.parametrize("raised,expected", [
    (lambda: ch.ChallengerError("injected"), "challenger_error"),
    (lambda: fh.C3Error("injected"), "c3_error"),
    (lambda: vm.VendorMinutesError("injected"), "c3_error"),
    # THE JOURNAL SPLIT.  ``journal_refused`` belongs to the journal's OWN
    # refusals; a bare ``LiveEvalError`` is a defect in the caller or in
    # ``live_eval`` itself and must not send a reader to the state dir.  Both
    # rows are here because the pairing is the property — one alone passes
    # while the mapping collapses them again.
    (lambda: le.JournalRefused("injected"), "journal_refused"),
    (lambda: le.LiveEvalError("injected"), "evaluator_error"),
    (lambda: KeyError("injected"), "evaluator_error"),
])
def test_W4R_C2_a_sibling_exception_darks_ONE_name_and_the_pass_survives(
        pack, monkeypatch, raised, expected):
    """``LiveEvalError`` and the rest are SIBLINGS, not subclasses.

    Measured before the fix: injecting a ``ChallengerError`` into ``run_c1`` for
    one ticker raised out of ``run_pass`` — zero names evaluated, no
    ``PassResult``, no payload, and the entrypoint returned 0 with the previous
    artifact still served.
    """
    real = ch.run_c1

    def boom(path):
        if path and path[0].ticker == "WASH":
            raise raised()
        return real(path)

    monkeypatch.setattr(ch, "run_c1", boom)
    now = et_now(32)
    result = one_pass(pack, quote_book(pack, multiple=0.97,
                                       ts=now - timedelta(minutes=2)), now=now)

    wash = name_of(result, "WASH")
    assert wash.state == "unavailable"
    assert wash.reasons == (expected,)
    assert wash.lanes["error_class"] == type(raised()).__name__
    assert name_of(result, "VSHAPE").state == "evaluated", \
        "one name's fault ended the pass for every other name"
    assert len(result.payload["names"]) == len(pack.substrate)
    assert result.health["state"] == "degraded"
    assert f"{expected}:1" in result.health["reasons"]
    assert result.health["dark"][expected] == 1


def test_W4R_C2_a_LEDGER_error_darks_only_its_name_so_apply_run_is_INSIDE_the_guard(
        tmp_path, pack):
    ledger = _ExplodingLedger(tmp_path, ticker="WASH")
    now = et_now(32)
    result = one_pass(pack, quote_book(pack, multiple=0.97,
                                       ts=now - timedelta(minutes=2)),
                      now=now, ledger=ledger, state_dir=tmp_path)
    wash = name_of(result, "WASH")
    assert wash.reasons == ("ledger_error",)
    assert wash.lanes["error_class"] == "LedgerError"
    assert name_of(result, "VSHAPE").state == "evaluated"


def test_W4R_C2_every_classified_reason_is_an_ENUMERATED_refusal():
    """A reason the payload can carry but the receipt cannot count is a hole."""
    for _cls, reason in le.NAME_ERROR_REASONS:
        assert reason in le.NAME_REFUSALS, reason
    assert "evaluator_error" in le.NAME_REFUSALS


# --- H2: a refused journal append is NAMED, and the row shows the tape ------

def test_W4R_H2_a_corrected_price_at_the_SAME_ts_is_named_and_the_row_shows_the_tape(
        tmp_path, pack):
    """A vendor correction (or the two-file freshest-wins merge flipping source)
    republishes the same ``ts`` with a different price.  The append-only law
    refuses it — lawfully — and the row used to advertise the REJECTED price
    beside an observation computed from the kept one, disclosed nowhere but a
    journal file on the VPS."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    ts = et_now(30)
    one_pass(pack, quote_book(pack, multiple=0.97, ts=ts), now=et_now(32),
             ledger=ledger, state_dir=tmp_path)

    book = quote_book(pack, multiple=0.97, ts=ts)          # SAME vendor timestamp
    kept = float(book["quotes"]["WASH"]["price"])
    book["quotes"]["WASH"]["price"] = kept * 0.82          # a 18% "correction"
    second = one_pass(pack, book, now=et_now(37), ledger=ledger, state_dir=tmp_path)

    wash = name_of(second, "WASH")
    assert "journal_refused_point" in wash.reasons
    assert wash.state == "evaluated", "the tape is still lawful — keep evaluating"
    row = next(r for r in second.payload["names"] if r["ticker"] == "WASH")
    assert row["quote"]["price"] == pytest.approx(kept), \
        "the payload advertises a price no detector read"
    assert row["quote_rejected"]["price"] == pytest.approx(kept * 0.82)
    assert row["observation"]["sampled_close"] == pytest.approx(kept)
    assert second.health["dark"]["journal_refused_point"] == 1
    assert "journal_refused_point:1" in second.health["reasons"]
    assert "journal_refused_point" not in name_of(second, "VSHAPE").reasons


def test_W4R_H2_CONTROL_a_benign_republish_at_the_SAME_price_raises_no_reason(
        tmp_path, pack):
    """An illiquid name republishes one vendor ``ts`` for many consecutive
    passes, so refusal is the STEADY STATE there.  Alarming on it would train an
    operator to ignore the reason that means a price actually changed."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    ts = et_now(30)
    one_pass(pack, quote_book(pack, multiple=0.97, ts=ts), now=et_now(32),
             ledger=ledger, state_dir=tmp_path)
    second = one_pass(pack, quote_book(pack, multiple=0.97, ts=ts), now=et_now(37),
                      ledger=ledger, state_dir=tmp_path)

    wash = name_of(second, "WASH")
    assert "journal_refused_point" not in wash.reasons
    row = next(r for r in second.payload["names"] if r["ticker"] == "WASH")
    assert row["quote_rejected"] is None
    assert second.health["dark"]["journal_refused_point"] == 0
    record = le.SessionJournal(tmp_path).read(NEXT_SESSION.isoformat(), "WASH")
    assert len(record.points) == 1 and len(record.refused) >= 1


# --- M1: the journal IS the memo -------------------------------------------

def test_W4R_M1_the_second_pass_evaluates_the_chain_only_for_NEW_intervals(pack):
    """The O(1)-per-pass claim, MEASURED.

    Before the fix a fresh builder per name per pass walked every interval since
    the open (measured 1,2,3,4,5,6,7 chain evaluations over seven passes), so the
    session total was O(intervals squared) — the exact cost design §1 says the
    class avoids.  A oneshot process cannot memoise across passes; the journal
    can.
    """
    daily = le.pack_daily_history(pack, "WASH")
    tape = _rising_tape(NEXT_SESSION)
    open_dt, _close = session_window_et(NEXT_SESSION)
    early = (open_dt + timedelta(minutes=30)).astimezone(timezone.utc)
    late = (open_dt + timedelta(minutes=60)).astimezone(timezone.utc)

    calls: list[float] = []
    real = le.IncrementalObservationBuilder.chain_at

    def counting(self, price):
        calls.append(float(price))
        return real(self, price)

    def fresh():
        return le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                                session=NEXT_SESSION)

    original, le.IncrementalObservationBuilder.chain_at = (
        le.IncrementalObservationBuilder.chain_at, counting)
    try:
        first = fresh().observations(tape, now=early)
        pass_one = len(calls)
        calls.clear()
        incremental = fresh().observations(tape, now=late, journaled=first)
        pass_two = len(calls)
        calls.clear()
        cold = fresh().observations(tape, now=late)
        pass_two_cold = len(calls)
    finally:
        le.IncrementalObservationBuilder.chain_at = original

    assert pass_one == len(first) > 0
    assert pass_two == len(incremental) - len(first), \
        "the second pass re-evaluated intervals the journal already held"
    assert pass_two_cold == len(cold) > pass_two, \
        "the CONTROL must show the whole path being recomputed"
    assert incremental == cold, "the journal-backed path is not byte-identical"


def _count_chain_at(fn):
    """Run ``fn()`` with ``chain_at`` counted.  Returns ``(result, n_calls)``."""
    calls: list[float] = []
    real = le.IncrementalObservationBuilder.chain_at

    def counting(self, price):
        calls.append(float(price))
        return real(self, price)

    le.IncrementalObservationBuilder.chain_at = counting
    try:
        return fn(), len(calls)
    finally:
        le.IncrementalObservationBuilder.chain_at = real


def test_W4R_M1_the_PASS_ITSELF_reads_the_memo_off_the_journal(tmp_path, pack):
    """The wiring, not the builder API — the half a builder-level test cannot see.

    ``test_W4R_M1_the_second_pass_evaluates_the_chain_only_for_NEW_intervals``
    hands ``journaled=`` to the builder in memory, so it stays green even if
    ``_evaluate_name`` passes ``journaled=None`` and every pass recomputes the
    whole path from the open — which IS the reported defect.  This drives two
    real passes over a SHARED state dir with a ledger reloaded from disk between
    them, which is what the deploy lane does (one capped oneshot per pass), and
    the cold control is the same second pass against an EMPTY state dir.
    """
    def second_pass(state):
        """The identical second pass, over whatever journal ``state`` holds."""
        return one_pass(pack, quote_book(pack, multiple=0.96, ts=et_now(50)),
                        now=et_now(62), ledger=ll.LiveEpisodeLedger.load(state),
                        state_dir=state)

    def build_journal(state):
        for minutes, ts in ((32, 20), (47, 40)):
            one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(ts)),
                     now=et_now(minutes), ledger=ll.LiveEpisodeLedger.load(state),
                     state_dir=state)

    warm_dir, cold_dir = tmp_path / "warm", tmp_path / "cold"
    build_journal(warm_dir)
    build_journal(cold_dir)

    # THE CONTROL VARIES ONE THING.  A fresh state dir would also give the second
    # pass a SHORTER TAPE (the tape is built from journaled POINTS), so it would
    # cost less rather than more and the comparison would be backwards.  So both
    # dirs get the identical journal and the control has only its frozen
    # OBSERVATIONS stripped — exactly the state a pass that never journaled them
    # would be in, with the points untouched.
    for path in (cold_dir / "journal").rglob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw.get("observations"), f"{path.name} journaled no observations"
        raw["observations"] = []
        path.write_text(json.dumps(raw), encoding="utf-8")

    warm, warm_calls = _count_chain_at(lambda: second_pass(warm_dir))
    cold, cold_calls = _count_chain_at(lambda: second_pass(cold_dir))

    assert cold_calls > 0, "the counter never fired — the probe is broken"
    assert warm_calls < cold_calls, (
        f"the second pass cost the same with the memo ({warm_calls}) as without "
        f"it ({cold_calls}) — the pass is not reading the journaled observations")
    # …and the answer is the SAME one, which is what makes the saving lawful.
    assert name_of(warm, "WASH").observations == name_of(cold, "WASH").observations


def test_W4R_M1_a_restart_replays_the_journal_and_stays_byte_identical(tmp_path, pack):
    """The parity that matters in production: a NEW process, a journal on disk."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    one_pass(pack, quote_book(pack, multiple=0.97, ts=et_now(20)), now=et_now(32),
             ledger=ledger, state_dir=tmp_path)

    restarted = ll.LiveEpisodeLedger.load(tmp_path)
    second = one_pass(pack, quote_book(pack, multiple=0.96, ts=et_now(35)),
                      now=et_now(52), ledger=restarted, state_dir=tmp_path)
    got = name_of(second, "WASH").observations

    record = le.SessionJournal(tmp_path).read(NEXT_SESSION.isoformat(), "WASH")
    builder = le.IncrementalObservationBuilder(
        ticker="WASH", daily=le.pack_daily_history(pack, "WASH"),
        session=NEXT_SESSION)
    assert got == builder.observations(record.tape(NEXT_SESSION), now=et_now(52))
    assert len(record.observations) == len(got)


def test_W4R_M1_a_journaled_interval_is_never_rewritten(tmp_path, pack):
    """Append-only for observations, exactly as for points."""
    journal = le.SessionJournal(tmp_path)
    record = journal.open_session(session=NEXT_SESSION.isoformat(), ticker="WASH",
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    first = builder.observations(_flat_tape(NEXT_SESSION, 90.0, minutes=30))
    assert journal.freeze_observations(record, first) == len(first)

    contradicting = tuple(replace_obs for replace_obs in
                          builder.observations(_flat_tape(NEXT_SESSION, 91.0,
                                                          minutes=30)))
    assert journal.freeze_observations(record, contradicting) == 0
    assert journal.observations_of(record) == first
    assert any(row.get("reason") == "observation_already_journaled"
               for row in record.refused)


# --- M2: the builder is diagonal-only --------------------------------------

def test_W4R_M2_an_OFF_DIAGONAL_tape_session_refuses(pack):
    """Measured before the fix: builder session 2026-08-17 against a 2026-01-20
    tape returned %K 15.25 where the oracle said 65.46, with no error at all."""
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    with pytest.raises(le.LiveEvalError, match="not the builder's"):
        builder.observations(_flat_tape(AS_OF, 90.0))


@pytest.mark.parametrize("index,ticker", list(enumerate(
    ["WASH", "VSHAPE", "FLAT", "SHORT", "STALE"])))
def test_W4R_M2_parity_holds_on_a_MULTI_PRICE_tape_and_under_now_TRUNCATION(
        pack, index, ticker):
    """Two parity-coverage holes closed at once: the corpus tape was flat (one
    memo key on every case) and ``now=None`` on every case, so the truncating
    branch was never compared against anything."""
    tape = _rising_tape(NEXT_SESSION, base=90.0 + 7.0 * index)
    daily = le.pack_daily_history(pack, ticker)
    builder = le.IncrementalObservationBuilder(ticker=ticker, daily=daily,
                                               session=NEXT_SESSION)
    oracle = ch.build_observation_path(ticker=ticker, daily=daily, tapes=[tape])
    assert builder.observations(tape) == oracle

    open_dt, _close = session_window_et(NEXT_SESSION)
    cut = (open_dt + timedelta(minutes=30)).astimezone(timezone.utc)
    truncated = le.IncrementalObservationBuilder(
        ticker=ticker, daily=daily, session=NEXT_SESSION).observations(tape, now=cut)
    assert truncated == tuple(o for o in oracle if o.observed_at <= le._iso(cut))
    assert 0 < len(truncated) < len(oracle)


# --- M3: the cross-check band is the SOLVER's, not a constant 100x wider ----

def test_W4R_M3_a_disagreement_at_TEN_TIMES_the_bisection_tolerance_is_a_DISAGREEMENT(
        pack):
    """``CROSS_CHECK_EPSILON_REL`` pointed at ``PROOF_EPSILON_REL`` (1e-4, the
    proof battery's straddle offset), which is 100x the solver's own 1e-6.  On a
    $100 name the justified band is +/-$0.0001 and the implemented one was
    +/-$0.01, so a real pack/oracle disagreement inside 1bp of the level reported
    ``boundary_band`` and no ``pack_integrity`` refusal ever fired."""
    from dataclasses import replace as dreplace

    row = pack.by_ticker()["WASH"]
    solution = row.c1_arm_price
    assert solution.price is not None
    tol = float(solution.rel_tolerance)
    assert tol == lp.BISECTION_REL_TOLERANCE == 1e-6
    assert le.CROSS_CHECK_EPSILON_REL == lp.BISECTION_REL_TOLERANCE
    assert lp.PROOF_EPSILON_REL / tol == pytest.approx(100.0), \
        "the measured 100x ratio moved"

    level = float(solution.price)
    inside = level * (1.0 + tol / 2.0)
    outside = level * (1.0 + 10.0 * tol)
    assert le._boundary_band(solution, inside,
                             epsilon_rel=le.CROSS_CHECK_EPSILON_REL) is True
    assert le._boundary_band(solution, outside,
                             epsilon_rel=le.CROSS_CHECK_EPSILON_REL) is False
    # THE CONTROL, stated as the OLD RULE's own arithmetic — the band is read
    # from the solution now, so passing the old constant through no longer
    # widens anything, which is itself the property under test.
    assert abs(outside - level) <= lp.PROOF_EPSILON_REL * abs(level), \
        "the old PROOF_EPSILON_REL band would have swallowed this disagreement"
    assert le._boundary_band(dreplace(solution, rel_tolerance=lp.PROOF_EPSILON_REL),
                             outside, epsilon_rel=tol) is True, \
        "the band must come from the SOLUTION, not from the module constant"

    # End to end: a level seeded 10x-tolerance away from a price the oracle reads
    # as armed must REFUSE the name rather than report a boundary artefact.
    daily = le.pack_daily_history(pack, "WASH")
    builder = le.IncrementalObservationBuilder(ticker="WASH", daily=daily,
                                               session=NEXT_SESSION)
    obs = builder.observations(_flat_tape(NEXT_SESSION,
                                          float(row.as_of_close) * 0.90))[-1]
    assert obs.k is not None and obs.k < ic.OVERSOLD, "the fixture is not armed"
    seeded = dreplace(row, c1_arm_price=dreplace(
        solution, price=float(obs.sampled_close) * (1.0 - 10.0 * tol)))
    assert le.cross_check(seeded, obs)["c1"]["verdict"] == "disagree"
    swallowed = dreplace(seeded, c1_arm_price=dreplace(
        seeded.c1_arm_price, rel_tolerance=lp.PROOF_EPSILON_REL))
    assert le.cross_check(swallowed, obs)["c1"]["verdict"] == "boundary_band", \
        "the CONTROL must show a 100x-wider band reporting the same disagreement " \
        "as a solver artefact"


# --- M4: quotes (step 4) before the basis audit (step 5) --------------------

def test_W4R_M4_the_quote_gate_runs_BEFORE_the_basis_audit(pack):
    """Measured: a premarket-timestamped quote WITH a 2x prevClose reported
    ``basis_mismatch`` and counted a ``basis_mismatch`` dark name — so a feed
    publishing a stale prevClose universe-wide would page as a data-integrity
    incident when the actual fault was a dead quote lane."""
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    premarket = (session_window_et(NEXT_SESSION)[0]
                 - timedelta(hours=1)).timestamp() * 1000.0
    for row in book["quotes"].values():
        row["ts"] = premarket
        row["prevClose"] = float(row["prevClose"]) * 2.0
    result = one_pass(pack, book, now=now)

    wash = name_of(result, "WASH")
    assert wash.reasons == ("premarket_quote",), "the real problem is invisible"
    assert wash.basis is None, "a name that never reached the engine was audited"
    assert result.health["basis"]["audited_n"] == 0
    assert result.health["basis"]["mismatched_n"] == 0
    assert result.health["dark"]["basis_mismatch"] == 0
    assert result.health["dark"]["premarket_quote"] == len(pack.substrate)


def test_W4R_M4_audited_n_counts_only_names_that_REACHED_the_engine(pack):
    """``audited_n`` overstated the audited EVALUATED population, so the
    ``basis_unverified`` guard could be satisfied by dark names alone."""
    now = et_now(32)
    book = quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))
    for row in book["quotes"].values():
        row["basis"] = "prev"                      # a carried quote, never live
    result = one_pass(pack, book, now=now)
    assert name_of(result, "WASH").reasons == ("carried_quote",)
    assert result.health["basis"] == {"audited_n": 0, "mismatched_n": 0,
                                      "unchecked_n": 0, "refused": []}


# --- M10 / LOW: the gates keep every field and every flag ------------------

def test_W4R_M10_gate_c2_uses_replace_and_names_only_the_two_fields_it_changes():
    """A hand-written ``C2Run(...)`` silently drops any field added later.

    Source-level on purpose: a functional test can only cover TODAY's fields,
    and the defect is about tomorrow's.
    """
    node = _function_ast("_gate_c2")
    constructed = [n for n in ast.walk(node) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr == "C2Run"]
    assert constructed == [], "_gate_c2 rebuilds C2Run field by field"
    replaces = [n for n in ast.walk(node) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "replace"]
    assert len(replaces) == 1
    assert {kw.arg for kw in replaces[0].keywords} == {"episodes", "events"}


def test_W4R_LOW_gate_arm_returns_its_blocked_flag_on_every_path():
    """``return run, False`` on the all-kept path discards ``blocked``.

    Correct only because ``blocked`` can be True today exactly when an episode is
    dropped — one added early ``continue`` breaks it, at no benefit.
    """
    source = (RADAR_DIR / "live_eval.py").read_text(encoding="utf-8")
    node = _function_ast("_gate_arm")
    flags = []
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and isinstance(child.value, ast.Tuple):
            flags.append(ast.get_source_segment(source, child.value.elts[-1]))
    assert flags.count("blocked") == 2, flags
    assert flags.count("False") == 1, "only the no-episodes early return may be False"


# --- LOW: the reader counters are volatile within one cycle ----------------

def test_W4R_LOW_stable_content_ignores_the_c3_reader_counters(pack):
    """A warm bucket cache legitimately turns ``fetched_n`` into ``cache_hits`` on
    a same-cycle re-run, so a determinism assertion built on them would flake the
    day C3 is enabled in that test."""
    now = et_now(32)
    result = one_pass(pack, quote_book(pack, multiple=0.97,
                                       ts=now - timedelta(minutes=2)), now=now)
    moved = json.loads(json.dumps(result.payload, default=str))
    moved["health"]["inputs"]["c3_reader"]["cache_hits"] = 99
    moved["health"]["inputs"]["c3_reader"]["fetched_n"] = 42
    assert le.stable_content(moved) == le.stable_content(result.payload)
    assert ("health", "inputs", "c3_reader") in le.VOLATILE_PAYLOAD_PATHS
