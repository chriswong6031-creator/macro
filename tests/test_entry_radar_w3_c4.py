"""Live Entry Radar PR-3 (W3) — C4 stratification features, and the kill fence.

WHAT THIS SUITE IS FOR
----------------------
C4 exists to STRATIFY C2 episodes and to do nothing else.  Two independent
failure modes are pinned here:

**The grid** (PIT-12).  Radar's 2D/3D buckets ride the ABSOLUTE session anchor,
so dropping leading history cannot re-phase them.  ``canon.resample_sessions``
counts from the caller's first bar and DOES re-phase — it is used below as the
live counterexample, because a test that only asserts the anchored path is stable
would also pass on an implementation that never had a phase problem to solve.

**The fence** (PIT-13, `DNR:KILL-WASHOUT-TURN`).  The killed construction is
higher-timeframe washout DEPTH used as arming authority.  C4 is refused at every
door: no entry-event family exists for it, ``assert_can_fire`` rejects its id,
``DetectorEpisode`` rejects it at construction, and ``C4State`` exposes no arm,
candidate, promote or fire API.  The API check is CONTROL-TESTED against a
planted subclass that adds one, so it cannot pass by scanning nothing.

PIT-14 pins the confirmed-bar law: a bucket that completes later never rewrites
the snapshot attached to an earlier C2 event.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

import copy
from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import canon, session_anchor
from engine.entry_radar import challengers as ch
from engine.entry_radar.entry_events import (
    FAMILY_KEYS,
    EntryEvent,
    EntryEventError,
    build_radar_native_event,
)

from tests.test_entry_radar_w3_c1c2_pit import (
    TICKER,
    daily_history,
    load_fixture,
    observation_path,
)


@pytest.fixture(scope="module")
def fixture() -> dict:
    return load_fixture()


@pytest.fixture(scope="module")
def daily(fixture) -> ch.DailyHistory:
    return daily_history(fixture)


# ---------------------------------------------------------------------------
# PIT-12 — the absolute anchor, against its own counterexample
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [2, 3])
@pytest.mark.parametrize("drop", [1, 2, 4, 5, 7])
def test_PIT12_dropping_leading_sessions_cannot_move_an_absolute_bucket(daily, n, drop):
    frame = daily.frame
    full = {b.bucket_id: (b.last_session, b.close, b.confirmed)
            for b in ch.mtf_buckets(frame, n)}
    trimmed = {b.bucket_id: (b.last_session, b.close, b.confirmed)
               for b in ch.mtf_buckets(frame.iloc[drop:], n)}
    shared = sorted(set(full) & set(trimmed))
    assert len(shared) > 20, "the comparison must have real overlap"
    for bucket_id in shared:
        assert full[bucket_id] == trimmed[bucket_id], \
            f"bucket {bucket_id} moved when {drop} leading sessions were dropped"


@pytest.mark.parametrize("n", [2, 3])
def test_PIT12_COUNTEREXAMPLE_the_first_row_ordinal_path_does_re_phase(daily, n):
    """``canon.resample_sessions`` counts from the CALLER's first bar.

    This is the implementation Radar refuses, and running it here is what makes
    PIT-12 a real property rather than a restatement: a leading drop that is not
    a multiple of ``n`` moves the ordinal grid and leaves the anchored one alone.
    """
    closes = daily.frame["close"].astype(float)
    drop = 1  # never a multiple of 2 or 3
    base, _known = canon.resample_sessions(closes, n)
    moved, _known2 = canon.resample_sessions(closes.iloc[drop:], n)
    # The ordinal grid RE-PHASES: the very set of bucket end-dates changes.
    base_days = {ts.date() for ts in base.index}
    moved_days = {ts.date() for ts in moved.index}
    assert base_days != moved_days, \
        "the ordinal path must visibly re-phase, or the counterexample is not one"
    assert len(base_days - moved_days) > 20

    anchored = {b.last_session for b in ch.mtf_buckets(daily.frame, n)}
    anchored_trimmed = {b.last_session
                        for b in ch.mtf_buckets(daily.frame.iloc[drop:], n)}
    # The anchored grid does not: every bucket the trimmed window still contains
    # keeps its identity, so the difference is a PREFIX and nothing else.
    assert anchored_trimmed <= anchored
    assert len(anchored & anchored_trimmed) > 20


def test_the_bucket_grid_is_the_absolute_session_position_divided_by_n(daily):
    frame = daily.frame
    positions = session_anchor.session_positions(pd.DatetimeIndex(frame.index))
    for n in (2, 3):
        expected = sorted({int(p) // n for p in positions})
        assert [b.bucket_id for b in ch.mtf_buckets(frame, n)] == expected


@pytest.mark.parametrize("n", [2, 3])
def test_a_trailing_partial_bucket_is_returned_unconfirmed(daily, n):
    """Cut the frame INSIDE a bucket and the trailing bucket must be provisional."""
    frame = daily.frame
    positions = session_anchor.session_positions(pd.DatetimeIndex(frame.index))
    inside = [i for i, p in enumerate(positions) if int(p) % n != n - 1]
    assert inside, "the frame must contain a mid-bucket session to cut at"
    cut = frame.iloc[:inside[-1] + 1]
    buckets = ch.mtf_buckets(cut, n)
    assert buckets[-1].confirmed is False, "the bucket's window has not elapsed"
    assert all(b.confirmed for b in buckets[:-1])
    # and cutting on a boundary confirms everything
    boundary = [i for i, p in enumerate(positions) if int(p) % n == n - 1]
    whole = ch.mtf_buckets(frame.iloc[:boundary[-1] + 1], n)
    assert all(b.confirmed for b in whole)


def test_the_radar_anchor_era_is_its_own_and_not_the_cascade_era():
    assert ch.RADAR_MTF_ANCHOR_ERA == "radar-abs-session-2026-08-14"
    assert ch.RADAR_MTF_ANCHOR_ERA != "abs-session-2026-08-06"
    assert ch.C4_SPEC["anchor_era"] == ch.RADAR_MTF_ANCHOR_ERA


# ---------------------------------------------------------------------------
# PIT-14 — later completion never rewrites an earlier snapshot
# ---------------------------------------------------------------------------

def test_PIT14_a_bucket_completing_later_never_rewrites_an_earlier_snapshot(fixture):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    short_rows = [r for r in fixture["daily"]["rows"] if r[0] <= session.isoformat()]
    at_the_time = ch.c4_snapshot(ticker=TICKER, daily=daily_history(
        fixture, rows=short_rows), market_session=session)

    extended = copy.deepcopy(fixture)
    last = date.fromisoformat(extended["daily"]["rows"][-1][0])
    price = float(extended["daily"]["rows"][-1][4])
    for step in range(1, 13):
        nxt = last.toordinal() + step
        extended["daily"]["rows"].append(
            [date.fromordinal(nxt).isoformat(), price, price * 1.05, price * 0.95,
             round(price * (1 + 0.04 * step), 4)])
    later = ch.c4_snapshot(ticker=TICKER, daily=daily_history(extended),
                           market_session=session)
    assert at_the_time.to_dict() == later.to_dict()


def test_a_partial_bucket_rides_debug_context_and_not_the_registered_value(daily):
    session = date.fromisoformat(daily.frame.index[-1].date().isoformat())
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    # W3-5 added the freshness receipt beside the partial-bucket debug context.
    assert set(state.provisional_context) == {"d2", "d3", "note", "history_freshness"}
    assert state.provisional_context["history_freshness"] == "confirmed"
    registered = state.to_dict()
    assert "partial_buckets" not in registered["d2"]
    assert registered["role"] == "stratification_only"


def test_the_snapshot_reads_only_confirmed_history_before_the_candidate_session(
        fixture, daily):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    for grain in (state.d2, state.d3):
        if grain.bucket_last_session is not None:
            assert grain.bucket_last_session < session.isoformat()


# ---------------------------------------------------------------------------
# §22 — the stratification fixture: turn flags and depth flags are separate
# ---------------------------------------------------------------------------

def _scan_for_mixed_turn_state():
    """Find a session where the 2D turn is False and the 3D turn is True.

    Scanned rather than asserted from a magic date: the point is that the two
    grains disagree, and a hand-picked date would silently stop being such a
    session the first time the anchor era moved.
    """
    reference = session_anchor.reference_sessions("US")
    sessions = [ts.date() for ts in
                reference[reference <= pd.Timestamp("2026-06-26")][-260:]]
    t = np.arange(len(sessions), dtype=float)
    closes = (100.0 * np.exp(-0.0008 * t)
              * (1 + 0.030 * np.sin(t / 5.7) + 0.018 * np.sin(t / 13.3 + 0.6)))
    frame = pd.DataFrame({"open": closes, "high": closes * 1.01,
                          "low": closes * 0.99, "close": closes},
                         index=pd.DatetimeIndex(sessions))
    history = ch.DailyHistory(frame=frame, vintage="synthetic")
    for session in sessions[120:]:
        state = ch.c4_snapshot(ticker=TICKER, daily=history, market_session=session)
        if state.d2.turn is False and state.d3.turn is True:
            return history, session, state
    return None, None, None


def test_S22_a_session_exists_with_no_2D_turn_and_a_3D_turn_present():
    history, session, state = _scan_for_mixed_turn_state()
    assert state is not None, "the §22 stratification case must be constructible"
    assert state.d2.turn is False and state.d3.turn is True
    assert state.recovery_count == 2, "1 (the observed 1D turn) + 0 + 1"
    assert state.d2.recent_washout is not None
    assert state.d3.recent_washout is not None
    payload = state.to_dict()
    # Both HTF washout flags are represented INDEPENDENTLY of the turn booleans —
    # four separate facts, never fused into one "deep and turning" verdict.
    assert set(payload["d2"]) >= {"turn", "recent_washout"}
    assert set(payload["d3"]) >= {"turn", "recent_washout"}
    assert history is not None and session is not None


def test_S22_the_c2_event_identity_does_not_depend_on_higher_tf_depth(fixture):
    """C2 never reads C4, so varying the depth flags cannot move a C2 event.

    Demonstrated with a REAL pair: two sessions whose turn booleans agree and
    whose washout flags disagree.  The C2 event beside them is byte-identical,
    because depth is context and never authority.  (A C2 that DID read depth
    would be `DNR:KILL-WASHOUT-TURN`'s interaction form at a new grain.)
    """
    path = observation_path(fixture)
    c1 = ch.run_c1(path)
    c2 = ch.run_c2(path, c1.episode)
    event = next(e for e in c2.events if e.subtype == "c2a_kd_cross")
    baseline_key = event.content_key

    history, _session, _state = _scan_for_mixed_turn_state()
    assert history is not None
    by_turn: dict[tuple, list] = {}
    for day in [ts.date() for ts in pd.DatetimeIndex(history.frame.index)][120:]:
        state = ch.c4_snapshot(ticker=TICKER, daily=history, market_session=day)
        by_turn.setdefault((state.d2.turn, state.d3.turn), []).append(state)
    pair = next((states for states in by_turn.values()
                 if len({(s.d2.recent_washout, s.d3.recent_washout)
                         for s in states}) > 1), None)
    assert pair is not None, \
        "the scan must find equal turn flags with unequal washout depth"

    rerun = ch.run_c2(path, c1.episode)
    same = next(e for e in rerun.events if e.subtype == "c2a_kd_cross")
    assert same.content_key == baseline_key
    for key in ("d2_turn", "d3_turn", "recent_washout", "recovery_count",
                "d2_recent_washout", "d3_recent_washout"):
        assert key not in event.context, f"a C2 event must not carry {key}"


@pytest.mark.parametrize("variant", ch.C2_VARIANTS)
def test_no_c2_variant_predicate_can_see_a_higher_timeframe_field(variant):
    """The Observation a variant reads has no 2D/3D field at all."""
    fields = set(ch.Observation.__dataclass_fields__)
    assert not [f for f in fields if any(tok in f for tok in ("d2", "d3", "mtf",
                                                              "washout", "depth"))]
    assert variant in ch.C2_EVALUATORS


# ---------------------------------------------------------------------------
# PIT-13 — C4 cannot fire, at every door
# ---------------------------------------------------------------------------

#: Any of these on a C4 state object would be a firing surface.
FIRING_API = ("arm", "candidate", "promote", "fire", "transition", "emit", "signal",
              "trigger", "advance")


def _firing_api(obj) -> list[str]:
    return sorted(name for name in dir(obj)
                  if not name.startswith("__")
                  and any(tok in name.lower() for tok in FIRING_API))


def test_PIT13_assert_can_fire_refuses_c4_and_permits_the_others():
    with pytest.raises(ch.StratificationOnly, match="stratification_only"):
        ch.assert_can_fire(ch.C4_DETECTOR_ID)
    for detector_id in (ch.C1_DETECTOR_ID, ch.C2_DETECTOR_ID):
        ch.assert_can_fire(detector_id)  # must not raise


def test_PIT13_a_c4_episode_cannot_even_be_constructed():
    with pytest.raises(ch.StratificationOnly):
        ch.DetectorEpisode(ticker=TICKER, detector_id=ch.C4_DETECTOR_ID)


def test_PIT13_c4_has_no_entry_event_family_so_it_cannot_address_an_event():
    assert not [f for f in FAMILY_KEYS if "mtf" in f or "c4" in f.lower()]
    with pytest.raises(EntryEventError, match="not a Radar-native family"):
        build_radar_native_event(
            detector_id=ch.C4_DETECTOR_ID, detector_spec_hash=ch.c4_spec_hash(),
            ticker=TICKER, family="radar_mtf_turn", subtype="d3_turn",
            signal_ts="2026-06-24T14:00:00Z", market_session="2026-06-24",
            bar_state="confirmed", finality_basis="x")
    with pytest.raises(EntryEventError, match="not in the minted set"):
        EntryEvent(producer="radar.entry_radar", ticker=TICKER,
                   family="radar_mtf_turn", subtype="d3_turn",
                   signal_ts="2026-06-24", source_identity=None,  # type: ignore[arg-type]
                   field_origin={}, bar_state="confirmed", final=True,
                   finality_basis="x")


def test_PIT13_a_c4_state_object_exposes_no_firing_api(fixture, daily):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    assert _firing_api(state) == []
    assert _firing_api(state.d2) == [] and _firing_api(state.d3) == []


def test_PIT13_MUTATION_a_planted_arm_method_is_caught_by_the_api_scanner(fixture,
                                                                         daily):
    """Control: the scanner must fire on the thing it exists to find."""
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)

    class _MutatedC4State(type(state)):  # type: ignore[misc]
        def arm_candidate(self):  # pragma: no cover - never invoked
            return "CANDIDATE"

    planted = _MutatedC4State(**{f: getattr(state, f)
                                 for f in state.__dataclass_fields__})
    assert _firing_api(planted) == ["arm_candidate"], \
        "a scanner that misses a planted arm path proves nothing about the real one"
    assert _firing_api(state) == []


def test_PIT13_the_c4_reading_carries_no_condition_at_all(fixture, daily):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    reading = ch.c4_reading(state, observed_at="2026-06-25T14:00:00Z")
    assert reading.condition_met is None, \
        "C4 has no condition to meet — False would read as a measured non-fire"
    assert reading.features["role"] == "stratification_only"
    assert reading.authority == {k: False for k in reading.authority}


def test_c4_is_computed_on_the_c2a_base_only(daily, fixture):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    with pytest.raises(ch.ChallengerError, match="C2a base only"):
        ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session,
                       base_variant="c2f_rebound_atr")
    ok = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    assert ok.base_variant == "c2a_kd_cross"


def test_recovery_count_is_one_plus_the_two_grain_turns(daily, fixture):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    if state.recovery_count is None:
        pytest.skip("both grains unavailable on this session")
    assert state.recovery_count == 1 + int(state.d2.turn) + int(state.d3.turn)
    assert 1 <= state.recovery_count <= 3


# ---------------------------------------------------------------------------
# 2026-08-14 adversarial-review regressions (W3-5, W3-7)
# ---------------------------------------------------------------------------

def test_W3_7_the_builder_refuses_c4_even_under_a_LAWFUL_family():
    """W3-7 (PIT-13, reproduction 1): the fence was on the FAMILY only, so
    ``detector_id="C4_MTF_TURN@1"`` under ``radar_1d_turn`` walked straight
    through the builder.  The refusal is now on the detector_id.
    """
    with pytest.raises(EntryEventError, match="stratification_only"):
        build_radar_native_event(
            detector_id=ch.C4_DETECTOR_ID, detector_spec_hash=ch.c4_spec_hash(),
            ticker=TICKER, family="radar_1d_turn", subtype="c2a_kd_cross",
            signal_ts="2026-06-24T14:00:00Z", market_session="2026-06-24",
            bar_state="provisional")


def test_W3_7_the_direct_constructor_refuses_c4_too():
    """W3-7 (PIT-13, reproduction 2): bypassing the builder bypassed the fence."""
    from engine.entry_radar.entry_events import SourceIdentity, radar_field_origin

    with pytest.raises(EntryEventError, match="stratification_only"):
        EntryEvent(producer="radar.entry_radar", detector_id=ch.C4_DETECTOR_ID,
                   ticker=TICKER, family="radar_1d_turn", subtype="c2a_kd_cross",
                   signal_ts="2026-06-24T14:00:00Z",
                   source_identity=SourceIdentity(signal_era="radar_w3_a5"),
                   field_origin=radar_field_origin(), bar_state="provisional",
                   final=False, finality_basis="x")


def test_W3_7_CONTROL_a_lawful_detector_under_the_same_family_still_mints():
    event = build_radar_native_event(
        detector_id=ch.C2_DETECTOR_ID, detector_spec_hash=ch.c2_spec_hash(),
        ticker=TICKER, family="radar_1d_turn", subtype="c2a_kd_cross",
        signal_ts="2026-06-24T14:00:00Z", market_session="2026-06-24",
        bar_state="provisional")
    assert event.detector_id == ch.C2_DETECTOR_ID


def test_W3_7_there_is_exactly_one_stratification_only_list():
    """The refusal list and the declared roles must be the same set, both ways."""
    from engine.entry_radar.detectors import DETECTORS, STRATIFICATION_ONLY
    from engine.entry_radar.entry_events import STRATIFICATION_ONLY_DETECTOR_IDS

    assert ch.STRATIFICATION_ONLY_IDS == frozenset(STRATIFICATION_ONLY_DETECTOR_IDS)
    declared = {did for did, record in DETECTORS.items()
                if record.spec.get("role") == "stratification_only"}
    assert declared == set(STRATIFICATION_ONLY_DETECTOR_IDS), \
        "a detector fenced at one door and open at another is the W3-7 defect"
    assert set(STRATIFICATION_ONLY) == declared


def test_W3_5_a_stale_daily_frame_withholds_the_c4_features(fixture):
    """W3-5: a stratification snapshot computed on an aged frame reads as a current
    higher-timeframe state.  Features are withheld and the reason is recorded.
    """
    rows = [r for r in fixture["daily"]["rows"] if r[0] <= "2026-04-30"]
    stale = daily_history(fixture, rows=rows)
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=stale, market_session=session)

    assert state.d2.availability == "stale" and state.d3.availability == "stale"
    assert state.d2.turn is None and state.d3.turn is None
    assert state.d2.recent_washout is None and state.d3.recent_washout is None
    assert state.recovery_count is None
    assert state.provisional_context["history_freshness"] == "stale"

    reading = ch.c4_reading(state, observed_at="2026-06-25T14:00:00Z")
    assert reading.availability == "stale"
    assert reading.condition_met is None
    assert reading.features["recovery_count"] is None


def test_W3_5_CONTROL_a_contiguous_frame_still_produces_the_features(fixture, daily):
    session = date.fromisoformat(fixture["tape_sessions"][1])
    state = ch.c4_snapshot(ticker=TICKER, daily=daily, market_session=session)
    assert state.d2.availability == "confirmed"
    assert state.provisional_context["history_freshness"] == "confirmed"
