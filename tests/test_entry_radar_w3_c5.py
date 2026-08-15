"""Live Entry Radar PR-3 (W3) — C5, the Terminal Bottom Watch interpretation.

WHAT THIS SUITE IS FOR
----------------------
C5 is the one W3 detector with nothing of its own to compute: its population is
already in the append-only store, preserved by W2.  So the failure modes are all
about DAMAGE to that record, and the tests are the corresponding refusals:

  PIT-15  every C5 candidate REFERENCES a preserved ``event_id``; no second event
          is minted for the same market observation, and the store is untouched
  PIT-16  candidate knowability is ``signal_known_ts`` — a ``signal_ts``-dated
          implementation is run beside it and must produce a DIFFERENT answer
  parity  the interpretation reproduces the preserved watch population exactly,
          on the committed W2 real-slice fixtures

The W2 fixtures are reused as-is.  No Terminal archaeology is re-run and the
expert-preservation store is not touched: C5 reads what W2 already recorded, which
is the entire architectural point of A5.6.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.entry_radar import c5_adapter as c5
from engine.entry_radar.entry_events import (
    WATCH_SUBTYPES,
    EntryEventStore,
)
from engine.entry_radar.g0_adapter import g0_events
from engine.entry_radar.indicator_ingest import EXPECTED_SOURCE_HASH, load_slice

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "entry_radar"
PANEL = ("NVDA", "NFLX", "TSLA")


def _store_for(symbol: str) -> EntryEventStore:
    store = EntryEventStore()
    g0_events(load_slice(FIXTURES / f"{symbol}.slice.json"), store)
    return store


@pytest.fixture(scope="module")
def stores() -> dict[str, EntryEventStore]:
    return {symbol: _store_for(symbol) for symbol in PANEL}


# ---------------------------------------------------------------------------
# parity with the preserved population
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", PANEL)
def test_c5_reproduces_the_preserved_watch_population_exactly(stores, symbol):
    store = stores[symbol]
    watches = [e for e in store.events() if e.family in WATCH_SUBTYPES]
    assert watches, f"{symbol} must carry watch events for this to mean anything"

    run = c5.run_c5(store)
    covered = {c.event_id for c in run.candidates}
    covered |= {eid for c in run.candidates for eid in c.superseded_event_ids}
    assert covered == {str(e.event_id) for e in watches}, \
        "every preserved watch is interpreted, and nothing else is"
    assert run.counts["watch_events"] == len(watches)
    assert run.counts["candidates"] + run.counts["superseded"] == len(watches)


@pytest.mark.parametrize("symbol", PANEL)
def test_both_watch_subtypes_survive_as_distinct_c5_variants(stores, symbol):
    run = c5.run_c5(stores[symbol])
    subtypes = {c.subtype for c in run.candidates}
    assert subtypes == {"early_dot", "blocked_trigger"}, \
        "the two families are two experts and are never deduped into one"
    for candidate in run.candidates:
        assert candidate.family == c5.C5_FAMILIES[candidate.subtype]


# ---------------------------------------------------------------------------
# PIT-15 — reference, never duplicate; never mutate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", PANEL)
def test_PIT15_c5_references_the_preserved_event_id_and_mints_nothing(stores, symbol):
    store = stores[symbol]
    before = {str(e.event_id): e.content_key for e in store.events()}
    run = c5.run_c5(store)

    assert run.minted_events == (), "C5 reuses the Terminal watch events (A5.8)"
    assert run.counts["minted_events"] == 0
    after = {str(e.event_id): e.content_key for e in store.events()}
    assert after == before, "the interpretation may not mutate what it reads"
    assert len(store) == len(before)

    for reading in run.readings:
        assert reading.evidence_refs, "a C5 reading with no evidence is an assertion"
        assert all(ref in before for ref in reading.evidence_refs)
        assert reading.detector_id == c5.C5_DETECTOR_ID


@pytest.mark.parametrize("symbol", PANEL)
def test_PIT15_no_detector_id_is_written_back_into_the_preserved_event(stores, symbol):
    c5.run_c5(stores[symbol])
    for event in stores[symbol].events():
        if event.family in WATCH_SUBTYPES:
            assert event.detector_id is None, \
                "a recorded family is not an arena detector (A1.2.4)"


@pytest.mark.parametrize("symbol", PANEL)
def test_PIT15_one_candidate_per_bar_no_duplicate_observation(stores, symbol):
    run = c5.run_c5(stores[symbol])
    bars = [(c.ticker, c.signal_ts) for c in run.candidates]
    assert len(bars) == len(set(bars)), "one C5 candidate per (ticker, bar)"
    episodes = [(e.ticker, e.candidate_at, e.variant) for e in run.episodes]
    assert len(episodes) == len(set(episodes))


def test_PIT15_running_c5_twice_changes_nothing(stores):
    store = stores["NFLX"]
    first = c5.run_c5(store)
    second = c5.run_c5(store)
    assert [c.to_dict() for c in first.candidates] == \
        [c.to_dict() for c in second.candidates]
    assert [r.canonical for r in first.readings] == [r.canonical for r in second.readings]


# ---------------------------------------------------------------------------
# PIT-16 — knowability is signal_known_ts
# ---------------------------------------------------------------------------

def _dated_at_signal_ts(candidate: c5.C5Candidate) -> str:
    """THE MUTATION: dating the candidate at the 3D bar's OPEN date.

    ``signal_ts`` is the 3D bar's open and can precede knowability by up to two
    sessions (§3.1's measured backdating).  A C5 dated there claims a decision the
    data could not have supported yet.
    """
    return candidate.signal_ts


@pytest.mark.parametrize("symbol", PANEL)
def test_PIT16_the_reading_is_dated_at_signal_known_ts(stores, symbol):
    run = c5.run_c5(stores[symbol])
    for candidate in run.candidates:
        assert candidate.knowable, "the watch stream carries known_ts verbatim (A4.5)"
        reading = c5.c5_reading(candidate)
        assert reading.observed_at == candidate.signal_known_ts
        assert reading.source_bar_known_at == candidate.signal_known_ts
        assert reading.source_bar_time == candidate.signal_ts
        assert reading.features["knowability_basis"] == "signal_known_ts"


@pytest.mark.parametrize("symbol", PANEL)
def test_PIT16_MUTATION_dating_at_signal_ts_is_a_different_and_earlier_answer(
        stores, symbol):
    run = c5.run_c5(stores[symbol])
    backdated = [c for c in run.candidates
                 if _dated_at_signal_ts(c) != c.signal_known_ts]
    assert backdated, \
        f"{symbol}: the panel must contain a backdated bar, or PIT-16 proves nothing"
    for candidate in backdated:
        assert _dated_at_signal_ts(candidate) < str(candidate.signal_known_ts), \
            "the mutation is always EARLIER — that is what makes it a leak"
    lawful = {c5.c5_reading(c).observed_at for c in run.candidates}
    mutated = {_dated_at_signal_ts(c) for c in run.candidates}
    assert lawful != mutated


def test_PIT16_a_watch_with_no_known_ts_is_unavailable_not_dated_at_signal_ts():
    """The honest landing when the emitter recorded no clock."""
    candidate = c5.C5Candidate(
        ticker="ZZTOP", subtype="early_dot", family="washout_early_watch",
        signal_ts="2026-07-01", signal_known_ts=None, event_id="0" * 16, final=False)
    reading = c5.c5_reading(candidate)
    assert reading.availability == "unavailable"
    assert reading.condition_met is None, "no clock is not a non-fire"
    assert reading.features["knowability_basis"] == "signal_known_ts (absent)"


# ---------------------------------------------------------------------------
# blocked_trigger precedence on a shared bar
# ---------------------------------------------------------------------------

def _micro_slice(signals, *, early_dots=()):
    return {"indicator": {
        "schema": "mastermind.indicator/v1", "symbol": "ZZTOP",
        "as_of": "2026-08-13T00:00:00Z", "signal_era": "gc_v2_wo2", "timeframe": "3D",
        "early_dots": list(early_dots), "signals": list(signals), "warnings": [],
        "state": {}, "bar_quality": "synthetic", "meta": {},
        "indicator": {"source_hash": EXPECTED_SOURCE_HASH, "params": {}},
    }}


def _watch(ts, known_ts, subtype):
    return {"type": "BOTTOM_WATCH", "subtype": subtype, "ts": ts, "known_ts": known_ts,
            "quality": ("washout_early_watch" if subtype == "early_dot"
                        else "washout_trigger_watch"),
            "washout_ctx": {}, "trigger_ts": ts, "trigger_known_ts": known_ts,
            "sweep_low": 1.0, "atr14": 0.1, "stop_level": 0.9,
            "risk_basis": "daily_ohlc_atr14", "scored": False}


def _shared_bar_store() -> EntryEventStore:
    store = EntryEventStore()
    g0_events(load_slice(_micro_slice([
        _watch("2026-07-01", "2026-07-03", "early_dot"),
        _watch("2026-07-01", "2026-07-03", "blocked_trigger"),
    ])), store)
    return store


def test_the_shared_bar_case_is_synthetic_because_the_panel_has_none(stores):
    """Recorded, not hidden: the real panel carries no same-bar watch pair."""
    for symbol in PANEL:
        bars = [(e.ticker, e.signal_ts) for e in stores[symbol].events()
                if e.family in WATCH_SUBTYPES]
        assert len(bars) == len(set(bars)), symbol


def test_blocked_trigger_takes_precedence_and_the_dot_is_recorded_not_dropped():
    store = _shared_bar_store()
    before = len(store)
    run = c5.run_c5(store)
    assert len(run.candidates) == 1, "one candidate per bar"
    candidate = run.candidates[0]
    assert candidate.subtype == "blocked_trigger", "the emitter's own de-dup rule (§3.4)"
    assert len(candidate.superseded_event_ids) == 1

    superseded = store.get(candidate.superseded_event_ids[0])
    assert superseded is not None and superseded.subtype == "early_dot"
    loser = next(r for r in run.readings
                 if r.variant == "early_dot" and r.condition_met is False)
    assert loser.features["superseded_by_event_id"] == candidate.event_id
    assert loser.condition_met is False, \
        "it was evaluated and lost — unavailable would erase an evaluated fact"
    watches = [e for e in store.events() if e.family in WATCH_SUBTYPES]
    assert len(watches) == 2, "both watch events still exist; C5 dropped nothing"
    assert len(store) == before, "and C5 added none either"


def test_MUTATION_reversing_the_precedence_order_changes_the_candidate():
    """Control: precedence is a real decision, not an artefact of dict order."""
    store = _shared_bar_store()
    original = c5.C5_SUBTYPE_PRECEDENCE
    try:
        c5.C5_SUBTYPE_PRECEDENCE = ("early_dot", "blocked_trigger")
        flipped = c5.c5_candidates(store.events())
    finally:
        c5.C5_SUBTYPE_PRECEDENCE = original
    assert flipped[0].subtype == "early_dot"
    assert c5.c5_candidates(store.events())[0].subtype == "blocked_trigger"


# ---------------------------------------------------------------------------
# identity + authority
# ---------------------------------------------------------------------------

def test_c5_spec_pins_the_terminal_receipt_and_its_constants():
    assert c5.C5_SPEC["upstream_pin"].endswith("82cb8cbf799fc3a91c9bee0f11a4db718fde68eb")
    assert c5.C5_SPEC["constants"] == {"DD_LOOKBACK_3D": 84, "DD_MIN": -0.35,
                                       "MO_DWELL_MIN": 3, "OS_WINDOW": 8}
    assert "blocked_trigger takes precedence" in c5.C5_SPEC["precedence"]
    assert c5.C5_SPEC["knowability"].startswith("the watch event's signal_known_ts")


@pytest.mark.parametrize("symbol", PANEL)
def test_every_c5_reading_and_episode_is_display_tier(stores, symbol):
    run = c5.run_c5(stores[symbol])
    for reading in run.readings:
        assert reading.authority == {k: False for k in reading.authority}
        assert reading.detector_spec_hash == c5.c5_spec_hash()
    for episode in run.episodes:
        assert episode.candidate_at == episode.first_armed_at
        assert episode.state.value == "CANDIDATE"
        assert episode.event_ids, "the episode names the preserved event as evidence"
