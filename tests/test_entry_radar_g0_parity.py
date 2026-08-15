"""Live Entry Radar PR-2 (W2) — G0 grey-dot parity against the committed fixtures.

FIXTURES F1-F6, contract §3.2 as amended by §18 A1.1 / A4.1-A4.5.  Every value
asserted below is FROZEN in `research/live_entry_radar/W2_PARITY_REPORT.json`
(fresh vintage, feed_end 2026-08-13) and `W2_G0_PARITY_RECEIPTS.md`; it is
transcribed here, never re-derived from the code under test.

Everything runs on the five committed `mastermind.indicator/v1` slices under
``tests/fixtures/entry_radar/``.  Nothing reads ``data/``, ``site/`` or the
network: agent worktrees are sparse checkouts where those trees are absent, and
a suite that needed them would pass vacuously on the render host and fail
everywhere else (DSC:SESSION-WORKTREES-ARE-SPARSE).

These exact tables are the operative tripwire against a label-join regression.
A4.1's detection-power finding is why: the pre-#392 leaking map is NOT
distinguishable by truncation probes on this tape (its defect is a knowability
mislabel, which is extension-stable) — it IS distinguishable by the known-answer
footprint, ~25 differing full-feed dots across the panel.  So the frozen date
lists below, not the F6 truncation pair, are what catches a regression toward it.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from engine.entry_radar.entry_events import EntryEventStore
from engine.entry_radar.g0_adapter import (
    BLOCKED_TRIGGER_SAME_BAR,
    G0_DETECTOR_ID,
    NO_WATCH_ON_BAR,
    PROMOTED,
    SIDE_CHANNEL,
    WATCH_PROMOTED,
    g0_events,
    g0_population,
    g0_spec_hash,
)
from engine.entry_radar.indicator_ingest import (
    EXPECTED_SIGNAL_ERA,
    EXPECTED_SOURCE_HASH,
    CalendarUnanswerable,
    FutureDatedSlice,
    IdentityMismatch,
    PreFenceEraRefusal,
    StaleFeedRefusal,
    calendar_basis,
    freshness_gate,
    identity_gate,
    ingest_slice,
    load_slice,
    sessions_forward,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_radar"

#: The wall clock every freshness verdict in this suite is stated against.
REFERENCE_DATE = date(2026, 8, 14)

#: FROZEN — `W2_PARITY_REPORT.json` fresh_0813, `raw_dots_ge2025`.  These are the
#: RECONSTRUCTED G0 population (A1.1 union), not the artifact's side channel.
NVDA_DOTS_GE2025 = (
    "2025-01-17", "2025-03-12", "2025-09-11", "2025-09-29", "2025-12-02",
    "2025-12-18", "2026-01-21", "2026-07-07", "2026-07-31",
)
NFLX_DOTS_GE2025 = (
    "2025-01-17", "2025-03-17", "2025-04-10", "2025-08-04", "2025-11-05",
    "2025-12-23", "2026-02-06", "2026-02-25", "2026-05-18", "2026-06-09",
    "2026-06-26", "2026-07-28",
)
TSLA_DOTS_GE2025 = (
    "2025-01-16", "2025-02-12", "2025-03-11", "2025-04-09", "2025-07-11",
    "2025-08-11", "2025-11-20", "2026-02-05", "2026-02-24", "2026-03-30",
    "2026-07-30",
)

#: FROZEN — the three washout-promoted dots (A1.1's deep-washout cohort).  They
#: are ABSENT from `early_dots[]` and recoverable only through the union.
NFLX_PROMOTED_TRIO = ("2026-02-06", "2026-02-25", "2026-06-26")

#: FROZEN — `W2_PARITY_REPORT.json` fresh_0813.NFLX.watches_ge2025 (F5's watch half).
NFLX_WATCH_KNOWN_TS = {
    "2026-02-06": "2026-02-10",
    "2026-02-20": "2026-02-24",
    "2026-02-25": "2026-02-27",
    "2026-06-26": "2026-06-30",
    "2026-07-28": "2026-07-30",
}
NFLX_WATCH_SUBTYPES = {
    "2026-02-06": "early_dot",
    "2026-02-20": "blocked_trigger",
    "2026-02-25": "early_dot",
    "2026-06-26": "early_dot",
    "2026-07-28": "blocked_trigger",
}

GE2025 = "2025-01-01"


def _slice(name: str):
    return load_slice(FIXTURES / f"{name}.slice.json")


def _g0(name: str):
    """(slice, store, report) for one fixture."""
    sl = _slice(name)
    store = EntryEventStore()
    return sl, store, g0_events(sl, store)


def _events(store: EntryEventStore, family: str, *, since: str = GE2025):
    return sorted((e for e in store.events()
                   if e.family == family and e.signal_ts >= since),
                  key=lambda e: e.signal_ts)


# ---------------------------------------------------------------------------
# F1 — NVDA: a pure side-channel population, 1999 IPO grid phase
# ---------------------------------------------------------------------------

def test_F1_nvda_union_population_is_the_frozen_nine_all_side_channel():
    sl, store, report = _g0("NVDA")
    dots = [d for d in report.dots if d.ts >= GE2025]

    assert tuple(d.ts for d in dots) == NVDA_DOTS_GE2025
    assert {d.source_channel for d in dots} == {SIDE_CHANNEL}, (
        "NVDA has no washout promotions ≥2025 — every dot must come from the "
        "artifact's own side channel")
    assert {d.washout_evidence for d in dots} == {NO_WATCH_ON_BAR}, (
        "no BOTTOM_WATCH of either subtype sits on any NVDA dot bar ≥2025")

    # Zero watch events ≥2025 (frozen: watches_ge2025 == []).  NVDA's 27
    # all-history watches are older and are not this assertion's subject.
    assert _events(store, "washout_early_watch") == []
    assert _events(store, "washout_trigger_watch") == []

    grey = _events(store, "grey_dot")
    assert tuple(e.signal_ts for e in grey) == NVDA_DOTS_GE2025
    assert {e.detector_id for e in grey} == {G0_DETECTOR_ID}
    assert {e.producer for e in grey} == {"terminal.confluence_v2"}
    assert {e.source_identity.detector_spec_hash for e in grey} == {g0_spec_hash()}


# ---------------------------------------------------------------------------
# F2 — NFLX: the union recovers the deep-washout cohort, edges resolve
# ---------------------------------------------------------------------------

def test_F2_nflx_union_recovers_the_promoted_trio_the_side_channel_dropped():
    sl, store, report = _g0("NFLX")
    dots = [d for d in report.dots if d.ts >= GE2025]

    assert tuple(d.ts for d in dots) == NFLX_DOTS_GE2025

    # The whole point of A1.1: the trio is NOT in the artifact's side channel.
    for ts in NFLX_PROMOTED_TRIO:
        assert ts not in sl.early_dots, (
            f"{ts} must be absent from early_dots[] — the emitter suppresses "
            f"promoted dots from the side channel; if it is present the union "
            f"double-counts")
    side_only = tuple(d.ts for d in dots if d.source_channel == SIDE_CHANNEL)
    promoted = tuple(d.ts for d in dots if d.source_channel == WATCH_PROMOTED)
    assert promoted == NFLX_PROMOTED_TRIO
    assert side_only == tuple(t for t in NFLX_DOTS_GE2025 if t not in NFLX_PROMOTED_TRIO)

    # ...and each promoted dot is ALSO a distinct recorded family (A1.2).
    watches = _events(store, "washout_early_watch")
    assert tuple(e.signal_ts for e in watches) == NFLX_PROMOTED_TRIO
    assert {e.subtype for e in watches} == {"early_dot"}


def test_F2_promoted_by_edges_resolve_for_exactly_the_trio():
    sl, store, report = _g0("NFLX")
    by_id = {e.event_id: e for e in store.events()}

    promo = [g for g in store.edges() if g.relation == "promoted_by"]
    recent = [g for g in promo if by_id[g.target_event_id].signal_ts >= GE2025]

    assert sorted(by_id[g.target_event_id].signal_ts for g in recent) == \
        sorted(NFLX_PROMOTED_TRIO)
    for edge in recent:
        source = by_id[edge.source_event_id]
        target = by_id[edge.target_event_id]
        assert source.family == "washout_early_watch"
        assert target.family == "grey_dot"
        assert source.signal_ts == target.signal_ts
        # The artifact carries NO link field; the edge is Radar's ts-join and
        # says so rather than implying the emitter recorded it (A1.1).
        assert edge.link_basis == "ts_join_synthesized"
        assert edge.known_lossy is False
        assert edge.provenance == "A1.1 union ts-join"


# ---------------------------------------------------------------------------
# F3 — blocked_trigger: the in-cap negative and the same-bar specimen
# ---------------------------------------------------------------------------

def test_F3_2026_02_20_blocked_trigger_fired_with_provably_no_dot():
    sl, store, report = _g0("NFLX")
    by_id = {e.event_id: e for e in store.events()}

    watch = [e for e in _events(store, "washout_trigger_watch")
             if e.signal_ts == "2026-02-20"]
    assert len(watch) == 1, "the blocked_trigger watch itself must be recorded"
    assert "2026-02-20" not in sl.early_dots
    assert "2026-02-20" not in {d.ts for d in report.dots}, (
        "a blocked_trigger bar is not a grey dot — including it would inflate the "
        "G0 population with the family it is being distinguished from")

    touching = [g for g in store.edges()
                if "2026-02-20" in (by_id[g.source_event_id].signal_ts,
                                    by_id[g.target_event_id].signal_ts)]
    assert touching == [], "no edge may be invented for a bar where no dot fired"

    # In-cap absence is PROVABLE absence, and is reported as such (A4.4).
    assert "2026-02-20" in report.provably_no_dot
    assert "2026-02-20" not in report.unknowable_pre_cap
    assert "dot_coincidence" not in watch[0].context


def test_F3_2026_07_28_is_the_same_bar_specimen_with_one_dedup_edge():
    sl, store, report = _g0("NFLX")
    by_id = {e.event_id: e for e in store.events()}

    assert "2026-07-28" in sl.early_dots, (
        "A4.4: the side channel RETAINS the date on a blocked_trigger bar — only "
        "early_dot promotions are suppressed")
    assert "2026-07-28" in {d.ts for d in report.dots}
    watch = [e for e in _events(store, "washout_trigger_watch")
             if e.signal_ts == "2026-07-28"]
    assert len(watch) == 1

    dedup = [g for g in store.edges() if g.relation == "dedup_suppressed_by"]
    recent = [g for g in dedup if by_id[g.target_event_id].signal_ts >= GE2025]
    assert len(recent) == 1, (
        f"exactly one same-bar de-dup edge ≥2025 (the 2026-07-28 specimen), got "
        f"{[by_id[g.target_event_id].signal_ts for g in recent]}")

    edge = recent[0]
    assert by_id[edge.source_event_id].family == "grey_dot"
    assert by_id[edge.source_event_id].signal_ts == "2026-07-28"
    assert by_id[edge.target_event_id].event_id == watch[0].event_id
    assert edge.link_basis == "ts_join_synthesized"
    assert edge.known_lossy is False


def test_F3_pre_cap_blocked_triggers_are_marked_unknowable_never_denied():
    """A4.4's narrowing: outside the 40-cap the channel's silence proves nothing."""
    sl, store, report = _g0("NFLX")
    assert report.cap_window_start == min(sl.early_dots)
    assert len(sl.early_dots) == 40

    assert report.unknowable_pre_cap == (
        "2004-09-13", "2004-11-10", "2005-03-28", "2007-08-17", "2011-11-02",
        "2012-06-26")
    # B1: the marking is per-SLICE and must NOT ride event content — the cap
    # window slides, so a vintage-varying key at a fixed event_id would make a
    # cross-vintage re-ingest crash on its own earlier record.
    for event in store.events():
        assert "dot_coincidence" not in event.context
        assert not any(k.startswith("context.") for k in event.field_origin)


# ---------------------------------------------------------------------------
# F4 — TSLA: 2010 IPO anchor, pinned by exact dates
# ---------------------------------------------------------------------------

def test_F4_tsla_union_population_is_the_frozen_eleven():
    sl, store, report = _g0("TSLA")
    dots = [d for d in report.dots if d.ts >= GE2025]

    assert tuple(d.ts for d in dots) == TSLA_DOTS_GE2025
    assert {d.source_channel for d in dots} == {SIDE_CHANNEL}
    assert _events(store, "washout_early_watch") == []
    assert _events(store, "washout_trigger_watch") == []


# ---------------------------------------------------------------------------
# F5 — known_ts: verbatim where the emitter has it, ABSENT where it does not
# ---------------------------------------------------------------------------

def test_F5_watch_borne_known_ts_is_the_emitter_value_verbatim():
    sl, store, report = _g0("NFLX")
    watches = sorted((e for e in store.events()
                      if e.family in ("washout_early_watch", "washout_trigger_watch")
                      and e.signal_ts >= GE2025),
                     key=lambda e: e.signal_ts)

    assert {e.signal_ts: e.signal_known_ts for e in watches} == NFLX_WATCH_KNOWN_TS
    assert {e.signal_ts: e.subtype for e in watches} == NFLX_WATCH_SUBTYPES
    for event in watches:
        assert event.field_origin["signal_known_ts"] == "emitter_verbatim"
        assert event.field_origin["subtype"] == "emitter_verbatim"

    # The grey dot minted FROM a watch inherits that clock verbatim too.
    promoted = [e for e in _events(store, "grey_dot")
                if e.signal_ts in NFLX_PROMOTED_TRIO]
    assert {e.signal_ts: e.signal_known_ts for e in promoted} == \
        {ts: NFLX_WATCH_KNOWN_TS[ts] for ts in NFLX_PROMOTED_TRIO}


@pytest.mark.parametrize("name", ["NVDA", "NFLX", "TSLA"])
def test_F5_side_channel_known_ts_is_absent_never_reconstructed(name):
    """A4.5 honesty assertion.  A reconstructed known_ts here would be a BUG.

    The `early_dots` channel is bare date strings.  Recomputing the true clock
    (measured and receipted at generation time, e.g. NFLX 2026-06-26→06-30) would
    be the §3.2 fallback reimplementation smuggled in as provenance.
    """
    sl, store, report = _g0(name)
    side = [e for e in store.events()
            if e.family == "grey_dot" and e.context["source_channel"] == SIDE_CHANNEL]
    assert side, "fixture must contain side-channel dots for this to bind"
    for event in side:
        assert event.signal_known_ts is None
        assert event.field_origin["signal_known_ts"] == "artifact_absent"
        # N1/N2: the basis names WHICH ruler produced the +3.
        assert event.finality_basis.startswith(
            "side_channel_conservative_bound(ts+3s<=as_of)[")
        assert event.finality_basis.endswith("[nyse_calendar]")


# ---------------------------------------------------------------------------
# F6 — provisionality at the edge, immutability behind it (A4.1)
# ---------------------------------------------------------------------------

def test_F6c_known_ts_equal_to_the_feed_edge_is_provisional():
    """cut@ts: the 06-26 watch's known_ts IS the artifact edge ⇒ not settled."""
    sl, store, report = _g0("NFLX.trunc_ts_2026-06-26")
    watch = [e for e in store.events()
             if e.family == "washout_early_watch" and e.signal_ts == "2026-06-26"]
    assert len(watch) == 1
    assert watch[0].signal_known_ts == "2026-06-26" == sl.as_of.isoformat()
    assert watch[0].final is False
    assert watch[0].bar_state == "provisional"


def test_F6c_known_ts_after_the_feed_edge_is_still_not_final():
    """cut@known: known_ts 06-30 POSTDATES as_of 06-26 — conservative rule holds."""
    sl, store, report = _g0("NFLX.trunc_known_2026-06-30")
    watch = [e for e in store.events()
             if e.family == "washout_early_watch" and e.signal_ts == "2026-06-26"]
    assert len(watch) == 1
    assert watch[0].signal_known_ts == "2026-06-30"
    assert sl.as_of == date(2026, 6, 26)
    assert watch[0].final is False
    assert watch[0].bar_state == "provisional"


def test_F6c_the_same_event_is_final_once_the_feed_extends_past_it():
    sl, store, report = _g0("NFLX")
    watch = [e for e in store.events()
             if e.family == "washout_early_watch" and e.signal_ts == "2026-06-26"]
    assert len(watch) == 1
    assert watch[0].signal_known_ts == "2026-06-30"
    assert watch[0].final is True
    assert watch[0].bar_state == "confirmed"


def test_F6b_events_behind_the_edge_are_byte_identical_across_vintages():
    """The load-bearing consumer guarantee: settled events never move.

    Measured 0 violations / 337 truncation probes and 0 drift over a real
    26-session extension (A4.1 F6b).  Pinned here on the committed pair.
    """
    cut = "2026-06-26"

    def snapshot(name):
        _sl, store, _report = _g0(name)
        settled = sorted((e.to_dict() for e in store.events()
                          if e.signal_known_ts and e.signal_known_ts < cut),
                         key=lambda d: d["event_id"])
        side = sorted((e.to_dict() for e in store.events()
                       if e.family == "grey_dot" and e.signal_known_ts is None
                       and GE2025 <= e.signal_ts < cut),
                      key=lambda d: d["event_id"])
        return settled, side

    fresh = snapshot("NFLX")
    assert len(fresh[0]) == 33 and len(fresh[1]) == 8, "guard against a vacuous compare"
    assert snapshot("NFLX.trunc_ts_2026-06-26") == fresh
    assert snapshot("NFLX.trunc_known_2026-06-30") == fresh


# ---------------------------------------------------------------------------
# the three gates
# ---------------------------------------------------------------------------

def test_freshness_gate_refuses_a_stale_slice():
    sl = _slice("NFLX.trunc_ts_2026-06-26")
    verdict = freshness_gate(sl, as_of_reference_date=REFERENCE_DATE, max_age_sessions=5)
    assert verdict.verdict == "STALE"
    assert verdict.feed_end_lower_bound == date(2026, 6, 26)
    assert verdict.age_sessions_upper_bound > 5

    with pytest.raises(StaleFeedRefusal):
        ingest_slice(sl, EntryEventStore(), as_of_reference_date=REFERENCE_DATE,
                     max_age_sessions=5)

    # ...and the historical-replay door still derives finality from the SLICE.
    report = ingest_slice(sl, EntryEventStore(), as_of_reference_date=REFERENCE_DATE,
                          max_age_sessions=5, allow_stale=True)
    assert report.freshness.verdict == "STALE"
    assert report.freshness.feed_end_lower_bound == sl.as_of


def test_freshness_gate_passes_the_current_vintage():
    for name, expected in (("NFLX", date(2026, 8, 13)), ("TSLA", date(2026, 8, 12))):
        verdict = freshness_gate(_slice(name), as_of_reference_date=REFERENCE_DATE)
        assert verdict.verdict == "FRESH"
        assert verdict.feed_end_lower_bound == expected
        assert "max_age_sessions=5" in verdict.basis


def test_a_future_dated_slice_is_refused_rather_than_clamped_to_fresh():
    """A zero-age clamp would report an artifact dated arbitrarily ahead as FRESH.

    Both readings of the state are refusals — the artifact is corrupt, or the
    reference clock handed to the gate is wrong — and neither is 'fresh'.
    """
    sl = _slice("NFLX")  # as_of 2026-08-13
    with pytest.raises(FutureDatedSlice, match="postdates"):
        freshness_gate(sl, as_of_reference_date=date(2026, 8, 12))
    with pytest.raises(FutureDatedSlice):
        ingest_slice(sl, EntryEventStore(), as_of_reference_date=date(2026, 1, 1))

    # The boundary itself is lawful: as_of == reference is age 0, FRESH.
    assert freshness_gate(sl, as_of_reference_date=date(2026, 8, 13)).verdict == "FRESH"


def test_identity_gate_pins_source_hash_and_era():
    sl = _slice("NFLX")
    identity_gate(sl)  # the pinned pair — must not raise
    assert sl.source_hash == EXPECTED_SOURCE_HASH
    assert sl.signal_era == EXPECTED_SIGNAL_ERA

    with pytest.raises(IdentityMismatch, match="source_hash"):
        identity_gate(sl, expected_source_hash="sha256:0000")
    with pytest.raises(IdentityMismatch, match="signal_era"):
        identity_gate(sl, expected_signal_era="gc_v2_wo1")


def test_missing_signal_era_is_refused_then_recorded_as_pre_fence():
    raw = json.loads((FIXTURES / "NFLX.slice.json").read_text(encoding="utf-8"))
    raw["indicator"].pop("signal_era")
    sl = load_slice(raw)
    assert sl.pre_fence is True
    assert sl.signal_era == "SIGNAL_ERA_PRE"

    with pytest.raises(PreFenceEraRefusal):
        ingest_slice(sl, EntryEventStore(), as_of_reference_date=REFERENCE_DATE)

    store = EntryEventStore()
    report = ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE,
                          allow_pre_fence=True)
    assert report.signal_era == "SIGNAL_ERA_PRE"
    assert {e.family_era for e in store.events()} == {"SIGNAL_ERA_PRE"}
    assert {e.source_identity.signal_era for e in store.events()} == {"SIGNAL_ERA_PRE"}


# ---------------------------------------------------------------------------
# N6 — the FULL committed side-channel tables, all three names
# ---------------------------------------------------------------------------
#
# The ≥2025 window above is where the specimens live, but it sees 9-12 of 40
# dots.  A label-join regression is caught by the KNOWN-ANSWER FOOTPRINT (A4.1:
# the pre-#392 leaking map differs on ~25 full-feed dots across the panel), and
# most of those differences sit in the years the window misses — 2019-05-23,
# 2019-09-05, 2020-03-19 and their neighbours.  These are the operative tripwire.

NVDA_EARLY_DOTS_FULL = (
    "2016-11-09", "2017-01-20", "2017-04-18", "2017-05-09", "2017-09-15",
    "2017-10-06", "2017-12-14", "2018-04-10", "2018-05-01", "2018-07-10",
    "2018-08-03", "2019-06-03", "2020-03-19", "2020-11-03", "2020-11-24",
    "2021-01-05", "2021-02-04", "2021-03-11", "2021-08-02", "2021-08-23",
    "2021-10-08", "2021-12-30", "2022-01-26", "2022-03-07", "2023-08-21",
    "2023-09-25", "2023-11-01", "2024-04-25", "2024-08-08", "2024-09-12",
    "2024-12-19", "2025-01-17", "2025-03-12", "2025-09-11", "2025-09-29",
    "2025-12-02", "2025-12-18", "2026-01-21", "2026-07-07", "2026-07-31",
)
NFLX_EARLY_DOTS_FULL = (
    "2018-05-04", "2018-07-31", "2018-08-21", "2018-11-06", "2018-11-28",
    "2018-12-26", "2019-05-23", "2019-07-29", "2019-09-05", "2019-10-04",
    "2019-10-30", "2020-03-19", "2020-06-15", "2020-08-21", "2020-09-25",
    "2020-11-03", "2020-11-24", "2021-03-19", "2021-05-19", "2021-06-15",
    "2021-12-21", "2022-01-26", "2022-12-30", "2023-03-13", "2023-08-03",
    "2023-08-21", "2023-09-28", "2023-10-19", "2024-04-30", "2024-08-08",
    "2024-09-12", "2025-01-17", "2025-03-17", "2025-04-10", "2025-08-04",
    "2025-11-05", "2025-12-23", "2026-05-18", "2026-06-09", "2026-07-28",
)
TSLA_EARLY_DOTS_FULL = (
    "2017-10-10", "2017-12-08", "2018-03-29", "2018-04-25", "2018-08-02",
    "2018-10-15", "2019-01-03", "2019-01-30", "2019-02-26", "2019-03-27",
    "2019-05-01", "2019-08-29", "2020-03-23", "2020-10-02", "2020-11-02",
    "2021-03-31", "2021-05-21", "2021-12-20", "2022-01-28", "2022-03-01",
    "2022-06-22", "2022-10-17", "2023-05-02", "2023-08-18", "2023-10-31",
    "2024-01-29", "2024-08-15", "2024-09-03", "2024-10-23", "2025-01-16",
    "2025-02-12", "2025-03-11", "2025-04-09", "2025-07-11", "2025-08-11",
    "2025-11-20", "2026-02-05", "2026-02-24", "2026-03-30", "2026-07-30",
)

FULL_SIDE_CHANNELS = {
    "NVDA": NVDA_EARLY_DOTS_FULL,
    "NFLX": NFLX_EARLY_DOTS_FULL,
    "TSLA": TSLA_EARLY_DOTS_FULL,
}


@pytest.mark.parametrize("name", sorted(FULL_SIDE_CHANNELS))
def test_N6_full_side_channel_table_is_exact(name):
    sl = _slice(name)
    expected = FULL_SIDE_CHANNELS[name]
    assert len(expected) == 40, "the emitter's cap — a shorter table is a fixture change"
    assert sl.early_dots == expected


@pytest.mark.parametrize("name", sorted(FULL_SIDE_CHANNELS))
def test_N6_every_side_channel_dot_becomes_exactly_one_grey_event(name):
    """No dot is lost between the artifact table and the minted population."""
    sl, store, report = _g0(name)
    minted = sorted(d.ts for d in report.dots if d.source_channel == SIDE_CHANNEL)
    assert minted == sorted(FULL_SIDE_CHANNELS[name])


# ---------------------------------------------------------------------------
# M1 — washout evidence is three-valued and reads the WHOLE watch stream
# ---------------------------------------------------------------------------

#: FROZEN specimens: a dot RETAINED in the side channel whose bar also carries a
#: `blocked_trigger` watch.  The same slice proves those bars ARE washed, so a
#: boolean "promoted?" flag reported them as unwashed and contradicted the
#: artifact it was built from.
BLOCKED_SAME_BAR_SPECIMENS = {
    "NFLX": ("2018-12-26", "2026-07-28"),
    "TSLA": ("2022-06-22",),
    "NVDA": (),
}


@pytest.mark.parametrize("name", sorted(BLOCKED_SAME_BAR_SPECIMENS))
def test_M1_blocked_trigger_on_a_retained_dot_bar_is_recorded_as_washed(name):
    sl, store, report = _g0(name)
    by_ts = {d.ts: d for d in report.dots}

    same_bar = tuple(sorted(d.ts for d in report.dots
                            if d.washout_evidence == BLOCKED_TRIGGER_SAME_BAR))
    assert same_bar == BLOCKED_SAME_BAR_SPECIMENS[name]

    for ts in BLOCKED_SAME_BAR_SPECIMENS[name]:
        dot = by_ts[ts]
        # side-channel BORNE and washed — two independent facts, both recorded
        assert dot.source_channel == SIDE_CHANNEL
        assert dot.washout_evidence == BLOCKED_TRIGGER_SAME_BAR
        grey = [e for e in store.events()
                if e.family == "grey_dot" and e.signal_ts == ts]
        assert grey[0].context["washout_evidence"] == BLOCKED_TRIGGER_SAME_BAR
        assert "washed" not in grey[0].context


def test_M1_the_promoted_trio_reads_promoted_and_the_rest_read_no_watch():
    sl, store, report = _g0("NFLX")
    by_ts = {d.ts: d.washout_evidence for d in report.dots}
    for ts in NFLX_PROMOTED_TRIO:
        assert by_ts[ts] == PROMOTED
    assert by_ts["2026-05-18"] == NO_WATCH_ON_BAR
    assert {d.washout_evidence for d in report.dots} == {
        PROMOTED, BLOCKED_TRIGGER_SAME_BAR, NO_WATCH_ON_BAR}


# ---------------------------------------------------------------------------
# M2 — field_origin honesty on the pinned values
# ---------------------------------------------------------------------------

def test_M2_oracle_subtype_is_radar_derived_because_radar_lifted_it():
    """The VALUE is the emitter's quality string; the SLOT is Radar's choice."""
    sl = _slice("NFLX")
    store = EntryEventStore()
    ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE)
    oracle = [e for e in store.events() if e.family.startswith("oracle_")]
    assert oracle
    for event in oracle:
        assert event.field_origin["subtype"] == "radar_derived"
        assert event.field_origin["quality"] == "emitter_verbatim"
        assert event.subtype == event.quality  # the value is still verbatim

    watches = [e for e in store.events() if e.family.startswith("washout_")]
    for event in watches:
        # BOTTOM_WATCH carries a real `subtype` field — that one IS verbatim.
        assert event.field_origin["subtype"] == "emitter_verbatim"


def test_M2_pre_fence_era_is_marked_absent_not_emitter_verbatim():
    """``SIGNAL_ERA_PRE`` is RADAR's sentinel for an era the artifact lacks."""
    raw = json.loads((FIXTURES / "NFLX.slice.json").read_text(encoding="utf-8"))
    raw["indicator"].pop("signal_era")
    sl = load_slice(raw)
    store = EntryEventStore()
    ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE, allow_pre_fence=True)
    for event in store.events():
        assert event.family_era == "SIGNAL_ERA_PRE"
        assert event.field_origin["family_era"] == "artifact_absent"
        assert event.field_origin["source_identity"] == "artifact_absent"

    # ...and a fenced slice attributes the era to the emitter, which wrote it.
    fenced = EntryEventStore()
    ingest_slice(_slice("NFLX"), fenced, as_of_reference_date=REFERENCE_DATE)
    for event in fenced.events():
        assert event.field_origin["family_era"] == "emitter_verbatim"
        assert event.field_origin["source_identity"] == "emitter_verbatim"


# ---------------------------------------------------------------------------
# N11 — edge subject conventions, asserted by name
# ---------------------------------------------------------------------------

def test_N11_edge_subject_conventions_hold_in_both_directions():
    """An edge read backwards inverts what happened, so both are pinned here.

    promoted_by:          source = promoted WATCH  → target = origin GREY_DOT
    dedup_suppressed_by:  source = suppressed GREY_DOT → target = BLOCKED_TRIGGER
    """
    sl, store, report = _g0("NFLX")
    by_id = {e.event_id: e for e in store.events()}

    promo = [g for g in store.edges() if g.relation == "promoted_by"]
    dedup = [g for g in store.edges() if g.relation == "dedup_suppressed_by"]
    assert promo and dedup, "both relations must be exercised for this to bind"

    for edge in promo:
        assert by_id[edge.source_event_id].family == "washout_early_watch"
        assert by_id[edge.target_event_id].family == "grey_dot"
    for edge in dedup:
        assert by_id[edge.source_event_id].family == "grey_dot"
        assert by_id[edge.target_event_id].family == "washout_trigger_watch"


# ---------------------------------------------------------------------------
# N1/N2 — calendar honesty
# ---------------------------------------------------------------------------

def test_N1_calendar_basis_only_claims_nyse_when_it_verifiably_is():
    from lib import nyse_calendar

    assert calendar_basis(nyse_calendar) == "nyse_calendar"
    assert calendar_basis() == "nyse_calendar"  # importable in this checkout

    class _Stub:
        """Has the right methods and is NOT the NYSE calendar."""
        @staticmethod
        def sessions_between(a, b):
            return []

        @staticmethod
        def session_n_forward(d, n):
            return None

    basis = calendar_basis(_Stub())
    assert basis.startswith("unverified_calendar("), basis
    assert "nyse" not in basis


def test_N2_a_calendar_that_cannot_answer_raises_rather_than_substituting():
    """No silent mid-computation ruler swap.

    Substituting business days here would put a business-day number under a
    basis string that still named the calendar — the exact mislabel the basis
    exists to prevent.
    """
    class _Blind:
        BASIS_NAME = "blind_calendar"

        @staticmethod
        def session_n_forward(d, n):
            return None

    with pytest.raises(CalendarUnanswerable, match="blind_calendar"):
        sessions_forward(date(2026, 7, 1), 3, calendar=_Blind())


def test_N2_a_weekend_dot_is_refused_not_silently_stepped():
    """A dot on a non-session is a data problem; the calendar says so."""
    sl = load_slice(_micro_slice_parity(early_dots=["2026-07-04"]))  # Saturday
    with pytest.raises(CalendarUnanswerable):
        g0_events(sl, EntryEventStore())


def _micro_slice_parity(*, early_dots=(), signals=()):
    return {"indicator": {
        "schema": "mastermind.indicator/v1", "symbol": "ZZTOP",
        "as_of": "2026-08-13T00:00:00Z", "signal_era": "gc_v2_wo2", "timeframe": "3D",
        "early_dots": list(early_dots), "signals": list(signals), "warnings": [],
        "state": {}, "bar_quality": "synthetic", "meta": {},
        "indicator": {"source_hash": EXPECTED_SOURCE_HASH, "params": {}},
    }}
