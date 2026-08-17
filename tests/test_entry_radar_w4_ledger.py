"""Live Entry Radar PR-4 (W4) — the runtime episode ledger + clock overlay.

WHAT THIS SUITE IS FOR
----------------------
The ledger is where a live lane either preserves its history or quietly loses
it.  Every property below is one of the ways that goes wrong:

  LED-1   the §13 record shape is FROZEN, its three score fields are ``None``
          always, and the one extension (``variant``) is declared
  LED-2   ``apply_run`` is IDEMPOTENT — the same inputs twice admit nothing
          twice, which is the whole restart-safety story
  LED-3   append-only: a TERMINAL episode's record may never change again, and
          a transition is admitted at most once per address
  LED-4   spool-before-consume is STRUCTURAL — ``commit`` cannot be called
          without the receipt, and a spool failure withholds everything
  LED-5   the clock overlay resolves CANDIDATE at exactly H = 10 sessions, at
          the resolving session's CLOSE instant, reading NO price (PIT-W4-20)
  LED-6   the full §10 re-arm chain (PIT-W4-11): arm → candidate → resolve →
          lawful re-arm as a NEW episode; a premature re-arm is REFUSED and
          recorded ``suppressed_by_rearm``; the prior episode is byte-identical
          before and after the new one exists
  LED-7   compaction ARCHIVES, never deletes — archive ∪ live is lossless
  LED-8   the G0/C5 confirmed-bar wiring lands candidates as episodes that
          REFERENCE the preserved watch events and never mutate them

Every load-bearing guard carries a mutation control.  Synthetic fixtures only
(shared with ``test_entry_radar_w4_pack.py``) plus the COMMITTED Terminal slice
fixtures under ``tests/fixtures/entry_radar/``.  No ``data/``, no ``site/``, no
network, no wall clock.
"""
from __future__ import annotations

import ast
import inspect
import json
from datetime import date, timedelta, timezone
from pathlib import Path

import pytest

from engine.entry_radar import challengers as ch
from engine.entry_radar import detectors as dt
from engine.entry_radar import live_ledger as ll
from engine.entry_radar.c5_adapter import C5_DETECTOR_ID, run_c5
from engine.entry_radar.entry_events import EntryEventStore
from engine.entry_radar.g0_adapter import g0_events
from engine.entry_radar.indicator_ingest import (
    feed_end_lower_bound,
    ingest_slice,
    load_slice,
)
from engine.session_digest import session_window_et
from tests.test_entry_radar_w4_pack import (
    AS_OF,
    NEXT_SESSION,
    frame_from_closes,
    washout_closes,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_radar"
RADAR_DIR = ROOT / "engine" / "entry_radar"

#: §13's episode field list, RE-TYPED here from the contract rather than imported
#: from the module under test.  Two independent copies is the point: a drift in
#: either one reds this test, which an ``assert FIELDS == FIELDS`` cannot.
CONTRACT_13_FIELDS = (
    "episode_id", "ticker", "detector_id", "detector_version", "detector_spec_hash",
    "state", "first_armed_at", "candidate_at", "last_observed_at", "market_session",
    "bar_availability", "feature_snapshot", "universe_admission", "lobe_nominations",
    "price_at_signal", "risk_geometry", "detector_score", "research_priority",
    "opportunity_score", "data_quality", "freshness", "evidence_refs",
)

RECEIPT = "live_flow/entry_radar_events/2026-08-17/143000-rth.json"


# ---------------------------------------------------------------------------
# fixtures — synthetic W3 runs
# ---------------------------------------------------------------------------

def washout_history(end: date = AS_OF) -> ch.DailyHistory:
    return ch.DailyHistory(frame=frame_from_closes(washout_closes(), end)
                           .loc[:, ["high", "low", "close"]],
                           price_basis=ch.BASIS_ADJUSTED, vintage="w4-fixture")


def flat_tape(session: date, price: float, *, minutes: int = 30) -> ch.SessionTape:
    open_dt, _close = session_window_et(session)
    return ch.SessionTape(
        session=session,
        minutes=tuple(ch.MinuteBar(start=open_dt + timedelta(minutes=m), open=price,
                                   high=price, low=price, close=price)
                      for m in range(0, minutes, 5)),
        price_basis=ch.BASIS_ADJUSTED, vintage="w4-fixture")


def c1_run(session: date = NEXT_SESSION, *, end: date = AS_OF, ticker: str = "WASH"):
    history = washout_history(end)
    price = float(history.frame["close"].iloc[-1])
    path = ch.build_observation_path(ticker=ticker, daily=history,
                                     tapes=[flat_tape(session, price)])
    return ch.run_c1(path), path


def ledger_with_candidate(tmp_path: Path, *, session: date = NEXT_SESSION):
    run, path = c1_run(session)
    assert run.episode is not None, "the fixture must produce a C1 candidate"
    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="WASH", as_of_session=session.isoformat(),
                             runs=[run], pass_id="rth")
    ledger.commit(delta, spool_receipt=RECEIPT)
    return ledger, run, delta


# ---------------------------------------------------------------------------
# LED-1 — the frozen record shape
# ---------------------------------------------------------------------------

def test_LED1_the_contract_field_list_is_section_13_verbatim():
    assert ll.EPISODE_CONTRACT_FIELDS == CONTRACT_13_FIELDS


def test_LED1_the_stored_record_is_schema_plus_contract_plus_variant():
    assert ll.EPISODE_FIELDS == ("schema",) + CONTRACT_13_FIELDS + ("variant",)


def test_LED1_the_three_score_fields_are_None_and_refused_otherwise(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    for name in ll.NULL_ONLY_FIELDS:
        assert getattr(episode, name) is None
    for name in ll.NULL_ONLY_FIELDS:
        with pytest.raises(ll.LedgerError, match="W6/W7 territory"):
            episode.replace(**{name: 91})


def test_LED1_a_score_shaped_feature_key_is_refused(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    with pytest.raises(ll.LedgerError, match="strength/priority"):
        episode.replace(feature_snapshot={"detector_strength": 4})


def test_LED1_CONTROL_an_ordinary_feature_key_is_accepted(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    got = ledger.episodes[0].replace(feature_snapshot={"k": 3.0, "sampled_close": 84.0})
    assert got.feature_snapshot["k"] == 3.0


def test_LED1_an_unknown_field_is_refused_on_read():
    with pytest.raises(ll.LedgerError, match="unknown episode field"):
        ll.LiveEpisode.from_dict({"schema": ll.SCHEMA_LIVE_EPISODE, "episode_id": "x",
                                  "ticker": "AAA", "detector_id": ch.C1_DETECTOR_ID,
                                  "detector_version": 1, "detector_spec_hash": "h",
                                  "state": "ARMED", "market_session": "2026-08-17",
                                  "forward_return_10d": 0.1})


def test_LED1_C4_may_never_hold_an_episode():
    with pytest.raises(ch.StratificationOnly):
        ll.LiveEpisode(episode_id="x", ticker="AAA", detector_id=ch.C4_DETECTOR_ID,
                       detector_version=1, detector_spec_hash="h", state="ARMED",
                       market_session="2026-08-17")


def test_LED1_the_episode_id_carries_the_whole_unit_key():
    base = dict(ticker="AAA", detector_id=ch.C2_DETECTOR_ID, variant="c2a_kd_cross",
                first_armed_at="2026-08-17T13:35:00Z")
    stable = ll.compute_episode_id(**base)
    assert stable == ll.compute_episode_id(**base)
    assert stable != ll.compute_episode_id(**{**base, "variant": "c2b_k_slope"})
    assert stable != ll.compute_episode_id(**{**base,
                                              "first_armed_at": "2026-08-18T13:35:00Z"})
    assert stable != ll.compute_episode_id(**{**base, "ticker": "BBB"})


def test_LED1_the_record_registers_the_detectors_own_spec_hash(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    assert episode.detector_spec_hash == dt.get_spec(ch.C1_DETECTOR_ID).spec_hash
    assert episode.detector_spec_hash == "f0bbd6cf3a6e2339"


# ---------------------------------------------------------------------------
# LED-2 — idempotency
# ---------------------------------------------------------------------------

def test_LED2_re_running_the_same_inputs_yields_an_EMPTY_delta(tmp_path):
    ledger, run, first = ledger_with_candidate(tmp_path)
    assert not first.empty
    second = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                              runs=[run], pass_id="rth")
    assert second.empty


def test_LED2_apply_run_is_PURE_until_commit(tmp_path):
    run, _path = c1_run()
    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    assert not delta.empty
    assert ledger.episodes == () and ledger.transitions == ()


def test_LED2_a_repeated_commit_of_the_same_delta_admits_nothing_twice(tmp_path):
    ledger, _run, delta = ledger_with_candidate(tmp_path)
    before = (len(ledger.episodes), len(ledger.transitions), len(ledger.events))
    ledger.commit(delta, spool_receipt=RECEIPT)
    assert (len(ledger.episodes), len(ledger.transitions),
            len(ledger.events)) == before


def test_LED2_save_then_load_roundtrips_the_whole_ledger(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    ledger.save()
    got = ll.LiveEpisodeLedger.load(tmp_path)
    assert [e.canonical for e in got.episodes] == \
           [e.canonical for e in ledger.episodes]
    assert got.transitions == ledger.transitions
    assert got.last_session == ledger.last_session


def test_LED2_a_loaded_ledger_still_dedups(tmp_path):
    ledger, run, _delta = ledger_with_candidate(tmp_path)
    ledger.save()
    got = ll.LiveEpisodeLedger.load(tmp_path)
    assert got.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                         runs=[run], pass_id="rth").empty


def test_LED2_merge_deltas_dedups_by_address(tmp_path):
    _ledger, run, delta = ledger_with_candidate(tmp_path)
    merged = ll.merge_deltas([delta, delta], as_of_session=NEXT_SESSION.isoformat(),
                             pass_id="rth")
    assert len(merged.transitions) == len(delta.transitions)
    assert len(merged.events) == len(delta.events)


# ---------------------------------------------------------------------------
# LED-3 — append-only
# ---------------------------------------------------------------------------

def _terminal_copy(episode: ll.LiveEpisode) -> ll.LiveEpisode:
    return episode.replace(state=dt.DetectorState.EXPIRED.value)


def test_LED3_a_terminal_episode_may_never_change_again(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(_terminal_copy(episode).to_dict(),)),
        spool_receipt=RECEIPT)
    assert ledger.episodes[0].terminal
    mutated = ledger.episodes[0].replace(last_observed_at="2999-01-01T00:00:00Z")
    with pytest.raises(ll.TerminalEpisodeMutation, match="never change again"):
        ledger.commit(
            ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                            pass_id="rth", episodes=(mutated.to_dict(),)),
            spool_receipt=RECEIPT)


def test_LED3_CONTROL_a_nonterminal_episode_may_advance(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    advanced = ledger.episodes[0].replace(last_observed_at="2026-08-17T19:00:00Z")
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(advanced.to_dict(),)),
        spool_receipt=RECEIPT)
    assert ledger.episodes[0].last_observed_at == "2026-08-17T19:00:00Z"


def test_LED3_a_stale_trace_of_a_terminal_episode_is_IGNORED_and_REPORTED(tmp_path):
    """A resolved episode is still re-produced by every later stateless replay.

    Ignoring it must not be silent (the delta names it) and must not wedge the
    name (no raise): the enforcing door is ``commit``, tested above.
    """
    ledger, run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    frozen = _terminal_copy(episode)
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(frozen.to_dict(),)),
        spool_receipt=RECEIPT)
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    assert delta.episodes == ()
    assert delta.superseded == (episode.episode_id,)
    ledger.commit(delta, spool_receipt=RECEIPT)
    assert ledger.get(episode.episode_id).canonical == frozen.canonical


def test_LED3_CONTROL_a_matching_trace_of_a_terminal_episode_is_not_reported(tmp_path):
    ledger, run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    # Same content, merely re-derived: nothing changed, so nothing is superseded.
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    assert delta.superseded == () and delta.episodes == ()
    assert ledger.get(episode.episode_id).state == "CANDIDATE"


def test_LED3_a_transition_is_admitted_at_most_once_per_address(tmp_path):
    ledger, _run, delta = ledger_with_candidate(tmp_path)
    count = len(ledger.transitions)
    doubled = ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                              pass_id="rth",
                              transitions=delta.transitions + delta.transitions)
    ledger.commit(doubled, spool_receipt=RECEIPT)
    assert len(ledger.transitions) == count


def test_LED3_the_committed_transition_carries_its_spool_receipt(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    assert {t["spool_key"] for t in ledger.transitions} == {RECEIPT}
    assert {e["spool_key"] for e in ledger.events} == {RECEIPT}


def test_LED3_an_event_with_no_id_cannot_be_addressed(tmp_path):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    with pytest.raises(ll.LedgerError, match="cannot be addressed"):
        ledger.commit(
            ll.PendingDelta(ticker="WASH", as_of_session="2026-08-17", pass_id="rth",
                            events=({"family": "radar_1d_live_washout"},)),
            spool_receipt=RECEIPT)


# ---------------------------------------------------------------------------
# LED-4 — spool before consume
# ---------------------------------------------------------------------------

def test_LED4_commit_without_a_receipt_is_REFUSED(tmp_path):
    run, _path = c1_run()
    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    with pytest.raises(ll.SpoolReceiptRequired, match="Spool-before-consume"):
        ledger.commit(delta, spool_receipt=None)
    with pytest.raises(ll.SpoolReceiptRequired):
        ledger.commit(delta, spool_receipt="   ")
    assert ledger.episodes == ()


def test_LED4_the_only_bypass_is_the_explicit_test_hook(tmp_path):
    run, _path = c1_run()
    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    ledger.commit(delta, spool_receipt=None, unspooled_ok=True)
    assert len(ledger.episodes) == 1
    assert ledger.transitions[0]["spool_key"] is None


def test_LED4_a_failed_spool_withholds_EVERYTHING(tmp_path):
    class DeadSpool(ll.EventSpool):
        def _put(self, key, payload):  # noqa: ANN001, ARG002
            return False

    run, _path = c1_run()
    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    receipt, committed = ll.spool_then_commit(
        ledger, delta, spool=DeadSpool(local_dir=tmp_path / "spool"),
        pass_ts="2026-08-17T14:30:00Z", session="2026-08-17", stamp="143000",
        pack_as_of="2026-08-14", pack_hash="deadbeefdeadbeef")
    assert receipt is None and committed is False
    assert ledger.episodes == () and ledger.transitions == ()


def test_LED4_CONTROL_a_healthy_spool_commits_and_writes_one_object(tmp_path):
    run, _path = c1_run()
    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                             runs=[run], pass_id="rth")
    spool_dir = tmp_path / "spool"
    receipt, committed = ll.spool_then_commit(
        ledger, delta, spool=ll.EventSpool(local_dir=spool_dir),
        pass_ts="2026-08-17T14:30:00Z", session="2026-08-17", stamp="143000",
        pack_as_of="2026-08-14", pack_hash="deadbeefdeadbeef")
    assert committed is True
    assert receipt.startswith(ll.EVENT_SPOOL_PREFIX)
    written = sorted(spool_dir.rglob("*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["schema"] == ll.SCHEMA_ENTRY_RADAR_EVENTS
    assert payload["pack"] == {"as_of": "2026-08-14", "pack_hash": "deadbeefdeadbeef"}
    assert len(payload["transitions"]) == len(delta.transitions)


def test_LED4_the_event_spool_is_the_W1_mechanism_at_a_second_prefix():
    from engine.entry_radar.spool import NominationSpool, SPOOL_PREFIX
    assert issubclass(ll.EventSpool, NominationSpool)
    assert ll.EVENT_SPOOL_PREFIX != SPOOL_PREFIX
    assert ll.EventSpool().prefix == ll.EVENT_SPOOL_PREFIX


def test_LED4_an_empty_delta_spools_nothing_and_is_reported_committed(tmp_path):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    empty = ll.PendingDelta(ticker="WASH", as_of_session="2026-08-17", pass_id="rth")
    receipt, committed = ll.spool_then_commit(
        ledger, empty, spool=ll.EventSpool(local_dir=tmp_path / "spool"),
        pass_ts="2026-08-17T14:30:00Z", session="2026-08-17", stamp="143000",
        pack_as_of="2026-08-14", pack_hash="h")
    assert (receipt, committed) == (None, True)
    assert not list((tmp_path / "spool").rglob("*.json"))


def test_LED4_spool_then_commit_without_a_spool_refuses(tmp_path):
    ledger, run, _delta = ledger_with_candidate(tmp_path)
    delta = ll.PendingDelta(ticker="WASH", as_of_session="2026-08-18", pass_id="rth",
                            transitions=({"ticker": "WASH",
                                          "detector_id": ch.C1_DETECTOR_ID,
                                          "variant": None, "from_state": "ARMED",
                                          "to_state": "EXPIRED",
                                          "at": "2026-08-18T20:00:00Z"},))
    with pytest.raises(ll.SpoolReceiptRequired):
        ll.spool_then_commit(ledger, delta, spool=None,
                             pass_ts="x", session="2026-08-18", stamp="200000",
                             pack_as_of="2026-08-14", pack_hash="h")


# ---------------------------------------------------------------------------
# LED-5 — the clock overlay (PIT-W4-20)
# ---------------------------------------------------------------------------

def test_LED5_a_candidate_resolves_at_exactly_H_sessions(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    for offset in range(0, ll.RESOLVE_HORIZON_SESSIONS):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        delta = ll.apply_session_clocks(ledger, as_of_session=session.isoformat(),
                                        confirmed_k_by_name={})
        assert delta.transitions == (), f"resolved early at +{offset}"
    session = ll.session_at_offset(NEXT_SESSION, ll.RESOLVE_HORIZON_SESSIONS)
    delta = ll.apply_session_clocks(ledger, as_of_session=session.isoformat(),
                                    confirmed_k_by_name={})
    assert len(delta.transitions) == 1
    row = delta.transitions[0]
    assert (row["from_state"], row["to_state"]) == ("CANDIDATE", "RESOLVED")


def test_LED5_the_stamp_is_the_resolving_sessions_CLOSE_instant(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    resolving = ll.session_at_offset(NEXT_SESSION, ll.RESOLVE_HORIZON_SESSIONS)
    delta = ll.apply_session_clocks(ledger, as_of_session=resolving.isoformat(),
                                    confirmed_k_by_name={})
    _open_dt, close_dt = session_window_et(resolving)
    expected = close_dt.astimezone(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")
    assert delta.transitions[0]["at"] == expected
    assert expected.startswith(resolving.isoformat())


def test_LED5_an_early_close_session_stamps_the_EARLY_close(tmp_path):
    """The stamp is the ACTUAL exchange close, never a hard-coded 16:00 ET."""
    # 2026-11-27 is the day after Thanksgiving — a 13:00 ET early close.
    early = date(2026, 11, 27)
    assert session_window_et(early)[1].hour == 13
    assert ll.session_close_instant(early).startswith("2026-11-27T18:00")


def test_LED5_resolution_needs_NO_price_input(tmp_path):
    """PIT-W4-20's ledger half: the resolve path is calendar arithmetic only."""
    ledger_a, _run, _delta = ledger_with_candidate(tmp_path / "a")
    ledger_b, _run_b, _delta_b = ledger_with_candidate(tmp_path / "b")
    resolving = ll.session_at_offset(NEXT_SESSION, ll.RESOLVE_HORIZON_SESSIONS)
    with_k = ll.apply_session_clocks(ledger_a, as_of_session=resolving.isoformat(),
                                     confirmed_k_by_name={"WASH": 91.0})
    without_k = ll.apply_session_clocks(ledger_b, as_of_session=resolving.isoformat(),
                                        confirmed_k_by_name={})
    assert with_k.transitions == without_k.transitions


def test_LED5_the_overlay_signature_admits_no_price_argument():
    params = set(inspect.signature(ll.apply_session_clocks).parameters)
    assert params == {"ledger", "as_of_session", "confirmed_k_by_name", "market",
                      "pass_id"}
    forbidden = ("price", "quote", "close", "return", "outcome", "mfe", "mae")
    assert [p for p in params if any(f in p for f in forbidden)] == []


def test_LED5_no_forward_outcome_token_appears_in_the_ledger_module():
    source = (RADAR_DIR / "live_ledger.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    forbidden = ("forward_return", "mfe", "mae", "hit_rate", "win_rate",
                 "false_start", "pnl")
    offenders = sorted(n for n in names
                       if any(f in str(n).lower() for f in forbidden))
    assert offenders == [], offenders


def test_LED5_CONTROL_the_outcome_scanner_catches_a_planted_name():
    tree = ast.parse("def f():\n    forward_return_10d = 1\n    return forward_return_10d\n")
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert any("forward_return" in n for n in names)


def test_LED5_INVALIDATED_has_no_producer_in_W4(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    resolving = ll.session_at_offset(NEXT_SESSION, ll.RESOLVE_HORIZON_SESSIONS + 5)
    delta = ll.apply_session_clocks(ledger, as_of_session=resolving.isoformat(),
                                    confirmed_k_by_name={"WASH": 5.0})
    assert {t["to_state"] for t in delta.transitions} == {"RESOLVED"}
    source = (RADAR_DIR / "live_ledger.py").read_text(encoding="utf-8")
    assert "DetectorState.INVALIDATED" not in source
    # ...and it stays a LEGAL §13 state, merely unproduced here.
    assert dt.DetectorState.INVALIDATED in dt.TERMINAL_STATES


def test_LED5_sessions_elapsed_counts_on_the_reference_calendar():
    # Friday -> Monday is ONE session, not three days.
    assert ll.sessions_elapsed(date(2026, 8, 14), date(2026, 8, 17)) == 1
    assert ll.sessions_elapsed(date(2026, 8, 14), date(2026, 8, 14)) == 0


# ---------------------------------------------------------------------------
# LED-6 — the full §10 re-arm chain (PIT-W4-11)
# ---------------------------------------------------------------------------

def _resolve(ledger, *, offset: int = ll.RESOLVE_HORIZON_SESSIONS, k=None):
    session = ll.session_at_offset(NEXT_SESSION, offset)
    delta = ll.apply_session_clocks(ledger, as_of_session=session.isoformat(),
                                    confirmed_k_by_name=k or {})
    ledger.commit(delta, spool_receipt=RECEIPT)
    return session, delta


def test_LED6_the_full_chain_arm_candidate_resolve_rearm(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    first = ledger.episodes[0]
    assert first.state == "CANDIDATE"

    resolved_session, delta = _resolve(ledger)
    assert len(delta.transitions) == 1
    assert ledger.get(first.episode_id).state == "RESOLVED"
    frozen_after_resolution = ledger.get(first.episode_id).canonical

    # A re-arm is REFUSED while the §10 window is open, and the refusal is
    # RECORDED — §11's control pool needs the names the rule suppressed.
    allowed, reason = ledger.arm_allowed(
        "WASH", ch.C1_DETECTOR_ID, session=resolved_session.isoformat(),
        would_have_armed_at="2026-08-31T14:00:00Z")
    assert (allowed, reason) == (False, "rearm_window_open")
    assert len(ledger.suppressions) == 1
    note = ledger.suppressions[0]
    assert note["ticker"] == "WASH" and note["detector_id"] == ch.C1_DETECTOR_ID
    assert note["would_have_armed_at"] == "2026-08-31T14:00:00Z"

    # Two consecutive confirmed K above the floor earns the re-arm (§10).
    for offset in (ll.RESOLVE_HORIZON_SESSIONS + 1, ll.RESOLVE_HORIZON_SESSIONS + 2):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        ledger.advance_rearm(as_of_session=session.isoformat(),
                             confirmed_k_by_name={"WASH": ch.REARM_K_FLOOR + 5})
    allowed, reason = ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID)
    assert (allowed, reason) == (True, "rearm_eligible")

    # The NEW episode is a new address, and the OLD one is byte-identical.
    new_session = ll.session_at_offset(NEXT_SESSION, ll.RESOLVE_HORIZON_SESSIONS + 3)
    run, _path = c1_run(new_session, end=ll.session_at_offset(new_session, -1))
    assert run.episode is not None
    delta = ledger.apply_run(ticker="WASH", as_of_session=new_session.isoformat(),
                             runs=[run], pass_id="rth")
    ledger.commit(delta, spool_receipt=RECEIPT)
    ids = {e.episode_id for e in ledger.episodes_for("WASH", ch.C1_DETECTOR_ID)}
    assert len(ids) == 2, ids
    assert first.episode_id in ids
    # PIT-W4-11: the new episode does not touch the old one's identity or history.
    assert ledger.get(first.episode_id).canonical == frozen_after_resolution


def test_LED6_the_prior_episode_is_byte_identical_once_the_new_one_exists(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    _resolve(ledger)
    first = ledger.episodes_for("WASH", ch.C1_DETECTOR_ID)[0]
    frozen = first.canonical
    for offset in (11, 12):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        ledger.advance_rearm(as_of_session=session.isoformat(),
                             confirmed_k_by_name={"WASH": 88.0})
    new_session = ll.session_at_offset(NEXT_SESSION, 13)
    run, _path = c1_run(new_session, end=ll.session_at_offset(new_session, -1))
    ledger.commit(ledger.apply_run(ticker="WASH",
                                   as_of_session=new_session.isoformat(),
                                   runs=[run], pass_id="rth"),
                  spool_receipt=RECEIPT)
    assert ledger.get(first.episode_id).canonical == frozen


def test_LED6_a_live_episode_blocks_a_second_arm(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    allowed, reason = ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID,
                                         would_have_armed_at="2026-08-17T15:00:00Z")
    assert (allowed, reason) == (False, "live_episode_open")
    assert ledger.suppressions[-1]["reason"] == "live_episode_open"


def test_LED6_a_name_with_no_history_may_arm(tmp_path):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    assert ledger.arm_allowed("NEWCO", ch.C1_DETECTOR_ID) == (True, "no_prior_episode")


def test_LED6_a_just_ended_episode_leaves_the_window_OPEN_not_unmeasured(tmp_path):
    """``commit`` opens the §10 clock at the instant the episode ends.

    "Just terminated, nothing measured yet" is a window that is legitimately
    open; it must not read as the unmeasurable case below.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(_terminal_copy(episode).to_dict(),)),
        spool_receipt=RECEIPT)
    block = ledger.rearm[f"WASH|{ch.C1_DETECTOR_ID}"]
    assert block["ended_session"] == NEXT_SESSION.isoformat()
    assert block["sessions_elapsed"] == 0 and block["confirmed_k"] == []
    assert ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID) == (False, "rearm_window_open")


def test_LED6_a_terminal_history_with_no_measurement_FAILS_CLOSED(tmp_path):
    """An episode that ended before this ledger measured anything cannot re-arm.

    Reached by dropping the re-arm block from a persisted ledger — the shape a
    state file written before the block existed, or a partially restored one,
    actually has.  An unmeasured recovery is not a recovery.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(_terminal_copy(episode).to_dict(),)),
        spool_receipt=RECEIPT)
    path = ledger.save()
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["rearm"] = {}
    path.write_text(json.dumps(raw), encoding="utf-8")

    reloaded = ll.LiveEpisodeLedger.load(tmp_path)
    assert reloaded.rearm == {}
    assert reloaded.arm_allowed("WASH", ch.C1_DETECTOR_ID) == (False,
                                                               "rearm_unmeasured")


def test_LED6_a_None_K_BREAKS_the_consecutive_run(tmp_path):
    """``rearm_eligible``'s documented law, driven through the overlay.

    A missing reading is not evidence of recovery, so it must not be skipped over
    the way a low reading is — it RESETS the run.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    _resolve(ledger)
    high = ch.REARM_K_FLOOR + 5
    for offset, value in ((11, high), (12, None), (13, high)):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        ledger.advance_rearm(as_of_session=session.isoformat(),
                             confirmed_k_by_name={"WASH": value})
    block = ledger.rearm[f"WASH|{ch.C1_DETECTOR_ID}"]
    assert block["confirmed_k"] == [high, None, high]
    assert ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID)[0] is False
    # CONTROL: one more clean session completes the run and the answer flips.
    ledger.advance_rearm(as_of_session=ll.session_at_offset(NEXT_SESSION,
                                                            14).isoformat(),
                         confirmed_k_by_name={"WASH": high})
    assert ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID)[0] is True


def test_LED6_the_elapsed_cap_alone_earns_the_rearm(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    _resolve(ledger)
    for offset in range(11, 11 + ch.REARM_MAX_SESSIONS):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        ledger.advance_rearm(as_of_session=session.isoformat(),
                             confirmed_k_by_name={"WASH": 3.0})
    block = ledger.rearm[f"WASH|{ch.C1_DETECTOR_ID}"]
    assert block["sessions_elapsed"] == ch.REARM_MAX_SESSIONS
    assert ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID) == (True, "rearm_eligible")


def test_LED6_replaying_a_session_cannot_inflate_the_rearm_run(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    _resolve(ledger)
    session = ll.session_at_offset(NEXT_SESSION, 11).isoformat()
    for _ in range(3):
        ledger.advance_rearm(as_of_session=session,
                             confirmed_k_by_name={"WASH": 99.0})
    block = ledger.rearm[f"WASH|{ch.C1_DETECTOR_ID}"]
    assert block["sessions_elapsed"] == 1
    assert block["confirmed_k"] == [99.0]


def _c2_episode(ledger, variant: str, *, armed_at: str, state: str = "CANDIDATE"):
    """Admit one C2 variant episode directly — the JC2 unit is (ticker, C2, variant)."""
    record = ll.LiveEpisode(
        episode_id=ll.compute_episode_id(ticker="WASH", detector_id=ch.C2_DETECTOR_ID,
                                         variant=variant, first_armed_at=armed_at),
        ticker="WASH", detector_id=ch.C2_DETECTOR_ID,
        detector_version=ch.C2_VERSION,
        detector_spec_hash=dt.get_spec(ch.C2_DETECTOR_ID).spec_hash,
        state=state, variant=variant, first_armed_at=armed_at, candidate_at=armed_at,
        market_session=NEXT_SESSION.isoformat())
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(record.to_dict(),)),
        spool_receipt=RECEIPT)
    return record


def test_LED6_a_terminated_c2a_does_not_gate_the_first_ever_c2b_arm(tmp_path):
    """The re-arm MEASUREMENT is per name; "has this unit fired before" is per unit.

    Sharing one key for both would put ``c2b`` inside a window it was never in.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _c2_episode(ledger, "c2a_kd_cross", armed_at="2026-08-17T13:35:00Z",
                state="EXPIRED")
    assert ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID, variant="c2a_kd_cross") == \
        (False, "rearm_window_open")
    assert ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID, variant="c2b_k_slope") == \
        (True, "no_prior_episode")


def test_LED6_a_live_variant_does_not_block_a_different_variant(tmp_path):
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _c2_episode(ledger, "c2a_kd_cross", armed_at="2026-08-17T13:35:00Z")
    assert ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID,
                              variant="c2a_kd_cross") == (False, "live_episode_open")
    assert ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID,
                              variant="c2c_higher_k_low") == (True, "no_prior_episode")


def test_LED6_a_second_ending_RESTARTS_the_rearm_window(tmp_path):
    """§10's window runs from the MOST RECENT ending, never the first one ever."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    _c2_episode(ledger, "c2a_kd_cross", armed_at="2026-08-17T13:35:00Z",
                state="EXPIRED")
    for offset in (1, 2):
        session = ll.session_at_offset(NEXT_SESSION, offset)
        ledger.advance_rearm(as_of_session=session.isoformat(),
                             confirmed_k_by_name={"WASH": ch.REARM_K_FLOOR + 5})
    assert ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID,
                              variant="c2a_kd_cross") == (True, "rearm_eligible")

    later = ll.session_at_offset(NEXT_SESSION, 3)
    record = ll.LiveEpisode(
        episode_id=ll.compute_episode_id(ticker="WASH",
                                         detector_id=ch.C2_DETECTOR_ID,
                                         variant="c2b_k_slope",
                                         first_armed_at="2026-08-20T13:35:00Z"),
        ticker="WASH", detector_id=ch.C2_DETECTOR_ID, detector_version=ch.C2_VERSION,
        detector_spec_hash=dt.get_spec(ch.C2_DETECTOR_ID).spec_hash,
        state="EXPIRED", variant="c2b_k_slope",
        first_armed_at="2026-08-20T13:35:00Z", candidate_at="2026-08-20T13:35:00Z",
        market_session=later.isoformat())
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=later.isoformat(),
                        pass_id="rth", episodes=(record.to_dict(),)),
        spool_receipt=RECEIPT)
    block = ledger.rearm[f"WASH|{ch.C2_DETECTOR_ID}"]
    assert block["ended_session"] == later.isoformat()
    assert (block["confirmed_k"], block["sessions_elapsed"]) == ([], 0)
    assert ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID,
                              variant="c2a_kd_cross") == (False, "rearm_window_open")


# ---------------------------------------------------------------------------
# W4R-H3 — ONE would-be arm is ONE suppression fact
#
# Review round 1, finding H3, ledger half.  ``arm_allowed`` is consulted on every
# pass of a stateless replay and ``_refuse`` appended unconditionally, so pass k
# left k identical rows: measured 4 passes -> 4 rows, and at ~78 passes a session
# one suppressed name ended the day with 78 copies in ``episodes.json``.  The
# growth was invisible — ``compact()`` never touches ``_suppressions`` and
# ``_ledger_hash`` covers only ``episodes`` — and it inflated any S11 control-pool
# count built from the field by exactly the pass number.
#
# The EVALUATOR half of the fix (snapshot the row count, publish only the new
# rows) is pinned in ``tests/test_entry_radar_w4_pit.py``.  What these pin is the
# LEDGER half, and the one that has to survive a PROCESS BOUNDARY: the deploy
# lane is one capped oneshot per pass (``app/deploy/macro-live-entry-radar.
# service``), so a dedup that lived only in a live object would be no dedup at
# all on the host it was written for.
# ---------------------------------------------------------------------------

SUPPRESSED_AT = "2026-08-17T15:00:00Z"


def test_W4R_H3_the_same_would_be_arm_records_exactly_ONE_suppression_row(tmp_path):
    """Four passes over one open episode leave one row, not four."""
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    for _ in range(4):
        allowed, reason = ledger.arm_allowed(
            "WASH", ch.C1_DETECTOR_ID, session=NEXT_SESSION.isoformat(),
            would_have_armed_at=SUPPRESSED_AT)
        assert (allowed, reason) == (False, "live_episode_open")
    assert len(ledger.suppressions) == 1
    assert ledger.suppressions[0]["would_have_armed_at"] == SUPPRESSED_AT


def test_W4R_H3_the_dedup_SURVIVES_a_save_and_a_RELOAD(tmp_path):
    """The lane is one process per pass, so the dedup lives on DISK or nowhere.

    An in-memory-only guard passes the test above and still writes 78 rows a
    session on the host, because pass N+1 starts from ``LiveEpisodeLedger.load``
    with an empty object and an ``episodes.json`` full of history.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID, session=NEXT_SESSION.isoformat(),
                       would_have_armed_at=SUPPRESSED_AT)
    ledger.save()

    for _ in range(3):
        reloaded = ll.LiveEpisodeLedger.load(tmp_path)
        assert len(reloaded.suppressions) == 1, "the reload must carry the fact"
        reloaded.arm_allowed("WASH", ch.C1_DETECTOR_ID,
                             session=NEXT_SESSION.isoformat(),
                             would_have_armed_at=SUPPRESSED_AT)
        reloaded.save()

    final = ll.LiveEpisodeLedger.load(tmp_path)
    assert len(final.suppressions) == 1
    on_disk = json.loads((tmp_path / "episodes.json").read_text(encoding="utf-8"))
    assert len(on_disk["suppressions"]) == 1


def test_W4R_H3_CONTROL_a_DIFFERENT_instant_is_a_DIFFERENT_fact(tmp_path):
    """The guard must dedup a repeat, never swallow a second suppression.

    Without this the "fix" of returning early on any prior row would pass every
    assertion above while erasing S11's control pool.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    for instant in (SUPPRESSED_AT, "2026-08-17T15:05:00Z", "2026-08-17T15:10:00Z"):
        ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID,
                           session=NEXT_SESSION.isoformat(),
                           would_have_armed_at=instant)
    assert len(ledger.suppressions) == 3
    # ... and the same instant on a LATER session is a later fact too.
    ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID,
                       session=ll.session_at_offset(NEXT_SESSION, 1).isoformat(),
                       would_have_armed_at=SUPPRESSED_AT)
    assert len(ledger.suppressions) == 4


def test_W4R_H3_a_second_variant_at_the_same_instant_is_its_own_fact(tmp_path):
    """The unit is (ticker, detector, VARIANT) — JC2 refuses per variant."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    for variant, armed_at in (("c2a_kd_cross", "2026-08-17T13:35:00Z"),
                              ("c2b_k_slope", "2026-08-17T13:40:00Z")):
        _c2_episode(ledger, variant, armed_at=armed_at)
        ledger.arm_allowed("WASH", ch.C2_DETECTOR_ID, variant=variant,
                           session=NEXT_SESSION.isoformat(),
                           would_have_armed_at=SUPPRESSED_AT)
    assert {s["variant"] for s in ledger.suppressions} == {"c2a_kd_cross",
                                                           "c2b_k_slope"}
    assert len(ledger.suppressions) == 2


def test_W4R_H3_a_CHANGED_reason_at_the_same_instant_does_not_re_record(tmp_path):
    """``reason``/``detail`` sit OUTSIDE the identity, and the first one stands.

    The same would-be arm reaches a different refusal once the open episode
    terminates and the S10 window opens behind it.  That is one suppression fact
    re-derived by a second rule, not two suppressed arms — recording it twice
    would double-count the control pool exactly as the original defect did.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID, session=NEXT_SESSION.isoformat(),
                       would_have_armed_at=SUPPRESSED_AT)
    assert ledger.suppressions[0]["reason"] == "live_episode_open"

    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth",
                        episodes=(_terminal_copy(ledger.episodes[0]).to_dict(),)),
        spool_receipt=RECEIPT)
    allowed, reason = ledger.arm_allowed(
        "WASH", ch.C1_DETECTOR_ID, session=NEXT_SESSION.isoformat(),
        would_have_armed_at=SUPPRESSED_AT)
    assert (allowed, reason) == (False, "rearm_window_open"), "the RULE still answers"
    assert len(ledger.suppressions) == 1
    assert ledger.suppressions[0]["reason"] == "live_episode_open"


def test_W4R_H3_the_suppression_identity_is_re_typed_from_the_ruling(tmp_path):
    """The five-part key, written out here rather than imported from the module.

    Two independent copies is the point: a narrowing of ``_suppression_key`` —
    dropping ``variant``, say — reds this rather than silently collapsing two
    units into one fact.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID, session=NEXT_SESSION.isoformat(),
                       would_have_armed_at=SUPPRESSED_AT)
    row = ledger.suppressions[0]
    assert ll._suppression_key(row) == ("WASH", ch.C1_DETECTOR_ID, "",
                                        NEXT_SESSION.isoformat(), SUPPRESSED_AT)
    for field, other in (("ticker", "OTHER"), ("detector_id", "x"), ("variant", "v"),
                         ("session", "2026-08-18"), ("would_have_armed_at", "z")):
        assert ll._suppression_key({**row, field: other}) != ll._suppression_key(row), (
            f"{field} must be part of the suppression identity")


def test_W4R_H3_an_arm_with_no_recorded_instant_stays_unrecorded(tmp_path):
    """The pre-existing contract the dedup must not have moved.

    ``arm_allowed`` records only when the caller supplied the instant it would
    have armed at; a bare eligibility question is not a suppressed arm.
    """
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    assert ledger.arm_allowed("WASH", ch.C1_DETECTOR_ID)[0] is False
    assert ledger.suppressions == ()


def test_LED3_an_event_readdressed_with_different_content_is_REFUSED(tmp_path):
    ledger, _run, delta = ledger_with_candidate(tmp_path)
    assert delta.events, "the fixture must mint a C1 event"
    tampered = {**delta.events[0], "ticker": "OTHER"}
    with pytest.raises(ll.LedgerError, match="DIFFERENT content"):
        ledger.commit(
            ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                            pass_id="rth", events=(tampered,)),
            spool_receipt=RECEIPT)


def test_LED3_CONTROL_the_same_event_from_a_later_pass_is_accepted(tmp_path):
    ledger, _run, delta = ledger_with_candidate(tmp_path)
    before = len(ledger.events)
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", events=delta.events),
        spool_receipt="live_flow/entry_radar_events/2026-08-17/144500-rth.json")
    assert len(ledger.events) == before
    # The FIRST pass's receipt stands: spool_key records what made it durable.
    assert {e["spool_key"] for e in ledger.events} == {RECEIPT}


def test_LED6_the_detector_semantics_are_UNTOUCHED_by_the_overlay():
    """PIT-W4-11's tail: the ledger may not move a single spec hash."""
    assert dt.get_spec(ch.C1_DETECTOR_ID).spec_hash == "f0bbd6cf3a6e2339"
    assert dt.get_spec(ch.C2_DETECTOR_ID).spec_hash == "d8ba60a25cfa7400"
    assert dt.get_spec(C5_DETECTOR_ID).spec_hash == "13dec66345a0376c"
    assert (ch.REARM_K_FLOOR, ch.REARM_K_SESSIONS, ch.REARM_MAX_SESSIONS) == (50, 2, 15)
    assert ll.RESOLVE_HORIZON_SESSIONS == 10


# ---------------------------------------------------------------------------
# LED-7 — compaction archives, never deletes
# ---------------------------------------------------------------------------

def test_LED7_compaction_moves_old_terminal_episodes_and_loses_nothing(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(_terminal_copy(episode).to_dict(),)),
        spool_receipt=RECEIPT)
    before = {e.episode_id: e.canonical for e in ledger.episodes}

    far = ll.session_at_offset(NEXT_SESSION, ll.COMPACTION_SESSIONS + 5)
    report = ledger.compact(as_of_session=far.isoformat())
    assert sum(report["archived"].values()) == 1
    assert ledger.episodes == ()

    archived = {str(r["episode_id"]): ll.LiveEpisode.from_dict(r).canonical
                for r in ledger.archived_episodes()}
    assert {**archived, **{e.episode_id: e.canonical for e in ledger.episodes}} == before


def test_LED7_a_nonterminal_episode_is_never_compacted(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    far = ll.session_at_offset(NEXT_SESSION, ll.COMPACTION_SESSIONS + 50)
    report = ledger.compact(as_of_session=far.isoformat())
    assert report["archived"] == {}
    assert len(ledger.episodes) == 1


def test_LED7_a_recent_terminal_episode_is_never_compacted(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    episode = ledger.episodes[0]
    ledger.commit(
        ll.PendingDelta(ticker="WASH", as_of_session=NEXT_SESSION.isoformat(),
                        pass_id="rth", episodes=(_terminal_copy(episode).to_dict(),)),
        spool_receipt=RECEIPT)
    near = ll.session_at_offset(NEXT_SESSION, ll.COMPACTION_SESSIONS - 1)
    assert ledger.compact(as_of_session=near.isoformat())["archived"] == {}
    assert len(ledger.episodes) == 1


def test_LED7_the_ledger_has_no_delete_api():
    forbidden = {"delete", "remove", "pop", "clear", "purge", "drop", "prune",
                 "truncate"}
    surface = {n for n in dir(ll.LiveEpisodeLedger) if not n.startswith("_")}
    assert surface & forbidden == set(), sorted(surface & forbidden)


# ---------------------------------------------------------------------------
# LED-8 — the confirmed-bar G0 / C5 wiring
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def slice_store():
    """NVDA's committed slice, ingested exactly as the pack lane ingests it."""
    slice_ = load_slice(FIXTURES / "NVDA.slice.json")
    store = EntryEventStore()
    ingest_slice(slice_, store, as_of_reference_date=feed_end_lower_bound(slice_))
    g0_events(slice_, store)
    return slice_, store


def test_LED8_c5_candidates_land_as_episodes_referencing_preserved_events(tmp_path,
                                                                          slice_store):
    _slice_, store = slice_store
    before = store.to_jsonl()
    run = run_c5(store)
    assert store.to_jsonl() == before, "run_c5 mutated the preserved event store"
    assert run.minted_events == ()

    ledger = ll.LiveEpisodeLedger(tmp_path)
    delta = ledger.apply_run(ticker="NVDA", as_of_session=AS_OF.isoformat(),
                             runs=[run], pass_id=ll.PACK_PASS_ID)
    ledger.commit(delta, spool_receipt=RECEIPT)
    assert len(ledger.episodes) == len(run.episodes) > 0
    # C5 mints NO event of its own: every reference is to a PRESERVED watch event.
    assert delta.events == ()
    known = {str(e.event_id) for e in store.events()}
    for episode in ledger.episodes:
        assert episode.detector_id == C5_DETECTOR_ID
        assert episode.evidence_refs, episode.episode_id
        assert set(episode.evidence_refs) <= known
    assert store.to_jsonl() == before


def test_LED8_the_c5_episode_takes_its_session_from_the_knowability_clock(tmp_path,
                                                                          slice_store):
    _slice_, store = slice_store
    run = run_c5(store)
    ledger = ll.LiveEpisodeLedger(tmp_path)
    ledger.commit(ledger.apply_run(ticker="NVDA", as_of_session=AS_OF.isoformat(),
                                   runs=[run], pass_id=ll.PACK_PASS_ID),
                  spool_receipt=RECEIPT)
    by_id = {e.episode_id: e for e in ledger.episodes}
    for candidate in run.candidates:
        if not candidate.knowable:
            continue
        episode_id = ll.compute_episode_id(
            ticker="NVDA", detector_id=C5_DETECTOR_ID, variant=candidate.subtype,
            first_armed_at=candidate.signal_known_ts)
        assert episode_id in by_id
        assert by_id[episode_id].market_session == str(candidate.signal_known_ts)[:10]
        assert by_id[episode_id].market_session != AS_OF.isoformat() or \
            str(candidate.signal_known_ts).startswith(AS_OF.isoformat())


def test_LED8_the_c5_lane_is_idempotent(tmp_path, slice_store):
    _slice_, store = slice_store
    run = run_c5(store)
    ledger = ll.LiveEpisodeLedger(tmp_path)
    ledger.commit(ledger.apply_run(ticker="NVDA", as_of_session=AS_OF.isoformat(),
                                   runs=[run], pass_id=ll.PACK_PASS_ID),
                  spool_receipt=RECEIPT)
    assert ledger.apply_run(ticker="NVDA", as_of_session=AS_OF.isoformat(),
                            runs=[run_c5(store)], pass_id=ll.PACK_PASS_ID).empty


def test_LED8_an_unconfigured_slice_store_reports_BOTH_lanes_unavailable():
    from scripts.entry_radar_live_pack import slice_lanes
    lanes, runs = slice_lanes(["NVDA"], as_of=AS_OF, slice_dir=None)
    assert runs == []
    for lane in ("g0", "c5"):
        assert lanes[lane]["available"] is False
        assert lanes[lane]["reason"] == "slice_store_unconfigured"


def test_LED8_a_configured_slice_store_runs_both_lanes():
    from scripts.entry_radar_live_pack import slice_lanes
    slice_ = load_slice(FIXTURES / "NVDA.slice.json")
    lanes, runs = slice_lanes(["NVDA", "NOPE"], as_of=feed_end_lower_bound(slice_),
                              slice_dir=FIXTURES)
    assert lanes["g0"]["available"] is True
    assert lanes["c5"]["available"] is True
    assert lanes["c5"]["candidates"] > 0
    assert lanes["per_name"]["NOPE"] == {"available": False, "reason": "slice_absent"}
    assert [t for t, _run in runs] == ["NVDA"]


def test_LED8_an_empty_probe_set_is_not_reported_as_a_data_problem():
    from scripts.entry_radar_live_pack import slice_lanes
    lanes, runs = slice_lanes([], as_of=AS_OF, slice_dir=FIXTURES)
    assert runs == []
    assert lanes["g0"]["reason"] == "no_probe_names"
    assert lanes["c5"]["reason"] == "no_probe_names"


def test_LED8_a_stale_slice_costs_its_own_name_and_nothing_else():
    from scripts.entry_radar_live_pack import slice_lanes
    lanes, runs = slice_lanes(["NVDA"], as_of=date(2027, 6, 1), slice_dir=FIXTURES)
    assert lanes["per_name"]["NVDA"]["available"] is False
    assert lanes["per_name"]["NVDA"]["reason"] == "slice_refused"
    assert lanes["g0"]["available"] is False
    assert runs == []


# ---------------------------------------------------------------------------
# housekeeping: the ledger writes only where it was told to
# ---------------------------------------------------------------------------

def test_the_ledger_writes_nothing_outside_its_state_dir(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    ledger.save()
    written = sorted(p.relative_to(tmp_path).as_posix()
                     for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["episodes.json"], written


def test_an_in_memory_ledger_writes_nothing_at_all(tmp_path):
    ledger = ll.LiveEpisodeLedger(None)
    run, _path = c1_run()
    ledger.commit(ledger.apply_run(ticker="WASH",
                                   as_of_session=NEXT_SESSION.isoformat(),
                                   runs=[run], pass_id="rth"),
                  spool_receipt=RECEIPT)
    assert ledger.save() is None
    assert len(ledger.episodes) == 1


def test_the_ledger_file_is_strict_json(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    body = ledger.save().read_text(encoding="utf-8")
    json.loads(body)
    assert "NaN" not in body and "Infinity" not in body


def test_reads_return_copies_not_the_live_objects(tmp_path):
    ledger, _run, _delta = ledger_with_candidate(tmp_path)
    rows = ledger.transitions
    rows[0]["to_state"] = "TAMPERED"
    assert ledger.transitions[0]["to_state"] != "TAMPERED"
    events = ledger.events
    if events:
        events[0]["ticker"] = "TAMPERED"
        assert ledger.events[0]["ticker"] != "TAMPERED"
