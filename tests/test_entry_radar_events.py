"""Live Entry Radar PR-2 (W2) — the `mastermind.entry_event.v1` store contract.

Contract §18 A1.2 (no flattening), A1.2.1 (field list, field_origin, typed
edges), A4.3 (family enums minted from emitter receipts), §2 (authority
all-false).

Every test is self-contained on the committed fixtures under
``tests/fixtures/entry_radar/`` or on inline synthetic micro-slices.  Nothing
reads ``data/``, ``site/`` or the network (DSC:SESSION-WORKTREES-ARE-SPARSE).
The synthetic slices exist for exactly one reason: three lawful emitter
qualities (`pending`, `override_take`, `reclaim_override_take`) do not occur on
this panel's tape, and A4.3 mints them from CODE receipts.  Covering them with
invented history would be worse than not covering them, so they are covered by
unit fixtures that claim to be nothing else.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from engine.entry_radar.contracts import AUTHORITY_BLOCK
from engine.entry_radar.detectors import (
    ALLOWED_TRANSITIONS,
    DETECTORS,
    RESERVED_DETECTOR_IDS,
    TERMINAL_STATES,
    DetectorError,
    DetectorState,
    IllegalTransition,
    NotYetSpecified,
    TransitionRecord,
    assert_g0_registry_matches_implementation,
    get_spec,
)
from engine.entry_radar.entry_events import (
    EDGE_LINK_BASES,
    EDGE_RELATIONS,
    EVENT_FIELDS,
    FAMILY_KEYS,
    FORBIDDEN_FAMILY_KEYS,
    AppendOnlyViolation,
    EdgeEndpointMissing,
    EntryEvent,
    EntryEventError,
    EntryEventStore,
    EventEdge,
    SourceIdentity,
    compute_event_id,
    event_dataclass_fields,
    family_first_available,
)
from engine.entry_radar.g0_adapter import g0_events
from engine.entry_radar.indicator_ingest import (
    EXPECTED_SOURCE_HASH,
    TERMINAL_PRODUCER,
    IndicatorSliceError,
    ingest_slice,
    load_slice,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_radar"
REFERENCE_DATE = date(2026, 8, 14)

#: One lawful subtype per family, for construction smoke tests.
#: One lawful subtype per minted family.  W3 (PR-3) added the three Radar-native
#: families (contract §18 A5.8), so this map and the test below grew from six
#: entries to nine — a family-list PIN updated for a family-list CHANGE, which is
#: the only reason a pin like this may ever move.
LAWFUL_SUBTYPE = {
    "grey_dot": None,
    "washout_early_watch": "early_dot",
    "washout_trigger_watch": "blocked_trigger",
    "oracle_buy": "take",
    "oracle_rebuy": "take",
    "oracle_reclaim": "reclaim",
    "radar_1d_live_washout": "live_k_lt_20",
    "radar_1d_turn": "c2a_kd_cross",
    "radar_1d_4h_recovery": "confirmed_4h_hist_trough",
}

#: Verbs that must never name a method on an append-only store.
MUTATION_VERBS = (
    "update", "delete", "remove", "pop", "clear", "discard", "truncate",
    "overwrite", "replace", "insert", "purge", "drop", "assign", "modify",
    "setitem", "setattr", "edit", "rewrite",
)


def _independent_six_part_id(producer, family, subtype, ticker, signal_ts, signal_era):
    """The SIX-part address, re-implemented independently of the module under test.

    Deliberately NOT a call into ``compute_event_id`` with the discriminator
    omitted.  A byte-stability claim checked against the code it is about cannot
    fail: measured 2026-08-14, a mutation that appended the discriminator
    UNCONDITIONALLY (so every id in the store moves) left both sides of such a
    comparison equal and the whole suite green.
    """
    payload = json.dumps([producer, family, subtype, ticker, signal_ts, signal_era],
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _event(**kw) -> EntryEvent:
    base = dict(
        producer=TERMINAL_PRODUCER,
        ticker="ZZTOP",
        family="oracle_buy",
        subtype="take",
        signal_ts="2026-08-05",
        signal_known_ts="2026-08-07",
        source_identity=SourceIdentity(source_hash="sha256:abc", signal_era="gc_v2_wo2"),
        field_origin={"signal_ts": "emitter_verbatim"},
        bar_state="confirmed",
        final=True,
        finality_basis="known_ts_settled(known_ts<as_of)",
    )
    base.update(kw)
    return EntryEvent(**base)


def _micro_slice(signals, *, early_dots=(), symbol="ZZTOP",
                 as_of="2026-08-13T00:00:00Z", era="gc_v2_wo2", warnings=()):
    """A minimal, well-formed `mastermind.indicator/v1` doc in the slim shape."""
    return {"indicator": {
        "schema": "mastermind.indicator/v1",
        "symbol": symbol,
        "as_of": as_of,
        "signal_era": era,
        "timeframe": "3D",
        "early_dots": list(early_dots),
        "signals": list(signals),
        "warnings": list(warnings),
        "state": {},
        "bar_quality": "synthetic",
        "meta": {},
        "indicator": {"source_hash": EXPECTED_SOURCE_HASH, "params": {}},
    }}


def _nflx_store() -> tuple[object, EntryEventStore]:
    """The NFLX panel through BOTH doors into ONE store — the realistic shape."""
    sl = load_slice(FIXTURES / "NFLX.slice.json")
    store = EntryEventStore()
    report = ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE)
    g0_events(sl, store)
    return (sl, report), store


# ---------------------------------------------------------------------------
# append-only
# ---------------------------------------------------------------------------

def test_identical_content_is_idempotent():
    store = EntryEventStore()
    first = store.append(_event())
    again = store.append(_event())
    assert len(store) == 1
    assert first.event_id == again.event_id


def test_same_address_different_content_is_refused_never_overwritten():
    store = EntryEventStore()
    store.append(_event(quality="take"))
    with pytest.raises(AppendOnlyViolation, match="never overwrites"):
        store.append(_event(quality="block"))
    assert len(store) == 1
    assert store.events()[0].quality == "take"


def test_store_exposes_no_mutation_api_at_all():
    """The absence is asserted so it cannot be re-added by accident."""
    store = EntryEventStore()
    names = [n for n in dir(store) if not n.startswith("__")]
    offenders = [n for n in names
                 if any(verb in n.lower() for verb in MUTATION_VERBS)]
    assert offenders == [], (
        f"EntryEventStore grew a mutation-shaped API: {offenders}; an append-only "
        f"store that can be edited cannot answer 'what did we know on the day'")
    assert "append" in names and "add_edge" in names, "guard must not go vacuous"


def test_returned_events_are_copies_the_caller_cannot_reach_the_store_through():
    store = EntryEventStore()
    store.append(_event(context={"reasons": ["a"]}))
    got = store.events()[0]
    got.context["reasons"].append("b")
    assert store.events()[0].context["reasons"] == ["a"]


# ---------------------------------------------------------------------------
# authority + family enums
# ---------------------------------------------------------------------------

def test_authority_block_is_all_false_and_exact():
    assert _event().authority == AUTHORITY_BLOCK
    assert set(AUTHORITY_BLOCK) == {"can_rank", "can_size", "can_gate",
                                    "can_originate_signal", "can_escalate"}


@pytest.mark.parametrize("grant", sorted(AUTHORITY_BLOCK))
def test_any_truthy_authority_is_refused_at_construction(grant):
    with pytest.raises(EntryEventError, match="display/research tier"):
        _event(authority={**AUTHORITY_BLOCK, grant: True})


def test_authority_block_with_a_missing_key_is_refused():
    partial = {k: v for k, v in AUTHORITY_BLOCK.items() if k != "can_rank"}
    with pytest.raises(EntryEventError, match="exact"):
        _event(authority=partial)


@pytest.mark.parametrize("family", sorted(FORBIDDEN_FAMILY_KEYS))
def test_forbidden_family_keys_are_refused(family):
    with pytest.raises(EntryEventError, match="forbidden flattening/UI-label key"):
        _event(family=family, subtype=None)


@pytest.mark.parametrize("family", FAMILY_KEYS)
def test_every_minted_family_constructs(family):
    event = _event(family=family, subtype=LAWFUL_SUBTYPE[family])
    assert event.family == family
    assert event.event_id and len(event.event_id) == 16


def test_forbidden_set_is_the_frozen_seven():
    assert FORBIDDEN_FAMILY_KEYS == frozenset({
        "entry_signal", "buy", "candidate", "golden_oracle", "early", "starter",
        "re_entry"})
    assert not (FORBIDDEN_FAMILY_KEYS & set(FAMILY_KEYS))


def test_event_id_is_deterministic_and_refuses_an_asserted_address():
    event = _event()
    assert event.event_id == compute_event_id(
        producer=TERMINAL_PRODUCER, family="oracle_buy", subtype="take",
        ticker="ZZTOP", signal_ts="2026-08-05", signal_era="gc_v2_wo2")
    with pytest.raises(EntryEventError, match="derived, never asserted"):
        _event(event_id="0" * 16)


def test_era_is_part_of_the_address_so_two_eras_never_collide():
    fenced = _event()
    pre = _event(source_identity=SourceIdentity(source_hash="sha256:abc",
                                                signal_era="SIGNAL_ERA_PRE"))
    assert fenced.event_id != pre.event_id


# ---------------------------------------------------------------------------
# no flattening
# ---------------------------------------------------------------------------

REQUIRED_PAIRS = {
    ("grey_dot", None),
    ("washout_early_watch", "early_dot"),
    ("washout_trigger_watch", "blocked_trigger"),
    ("oracle_buy", "take"),
    ("oracle_buy", "block"),
    ("oracle_buy", "regime_blocked"),
    ("oracle_reclaim", "reclaim"),
    ("oracle_reclaim", "block_repair"),
    ("oracle_reclaim", "stop_sweep_reclaim"),
}


def test_nflx_panel_keeps_every_distinct_family_subtype_pair():
    _meta, store = _nflx_store()
    pairs = {(e.family, e.subtype) for e in store.events()}
    missing = REQUIRED_PAIRS - pairs
    assert missing == set(), f"flattened away: {sorted(missing)}"
    assert {f for f, _s in pairs} <= set(FAMILY_KEYS)
    assert not ({f for f, _s in pairs} & FORBIDDEN_FAMILY_KEYS)


def test_no_event_carries_a_forbidden_family_after_a_real_ingest():
    _meta, store = _nflx_store()
    for event in store.events():
        assert event.family not in FORBIDDEN_FAMILY_KEYS
        assert event.family in FAMILY_KEYS


def test_oracle_events_preserve_the_emitter_record_verbatim():
    (sl, _report), store = _nflx_store()
    by_id = {e.event_id: e for e in store.events()}
    checked = 0
    for raw in sl.signals:
        family = {"BUY": "oracle_buy", "REBUY": "oracle_rebuy",
                  "RECLAIM": "oracle_reclaim"}.get(raw.get("type"))
        if family is None:
            continue
        event = by_id[compute_event_id(
            producer=TERMINAL_PRODUCER, family=family, subtype=raw.get("quality"),
            ticker=sl.symbol, signal_ts=raw["ts"], signal_era=sl.signal_era,
            discriminator=raw.get("anchor_ts"))]
        assert event.subtype == raw["quality"], "subtype IS the emitter quality (A4.3)"
        assert event.quality == raw["quality"]
        for key in ("type", "quality", "reasons", "regime"):
            assert event.context[key] == raw[key]
        for key, value in raw.items():
            assert event.context[key] == value, f"{key} was renamed or dropped"
        # A recorded fact about the emitter's own claim, never a grant to Radar.
        assert event.scored_authority == raw.get("scored")
        assert event.authority == AUTHORITY_BLOCK
        checked += 1
    assert checked == 141, "BUY 50 + REBUY 10 + RECLAIM 81 on the NFLX panel"


def test_blocked_flag_rides_the_context_rather_than_becoming_a_family():
    (sl, _report), store = _nflx_store()
    blocked = [e for e in store.events()
               if e.family == "oracle_buy" and e.subtype == "regime_blocked"]
    assert len(blocked) == 18
    assert all(e.context["blocked"] is True for e in blocked)


def test_watch_events_carry_their_washout_context_verbatim():
    (sl, _report), store = _nflx_store()
    watches = [e for e in store.events()
               if e.family in ("washout_early_watch", "washout_trigger_watch")]
    assert len(watches) == 23
    for event in watches:
        for key in ("washout_ctx", "trigger_ts", "trigger_known_ts", "sweep_low",
                    "atr14", "stop_level", "risk_basis"):
            assert key in event.context, f"{key} lost from a BOTTOM_WATCH event"
        assert event.field_origin["stage"] == "artifact_absent"
        assert event.stage is None


# ---------------------------------------------------------------------------
# exit-side exclusions
# ---------------------------------------------------------------------------

def test_sell_and_warnings_are_excluded_and_counted():
    (sl, report), store = _nflx_store()
    assert report.excluded_exit_side == {"warnings": 40, "SELL": 85}
    assert report.n_excluded_exit_side == 125
    assert report.excluded_unknown_type == {}
    assert all("structure_stop" != e.context.get("basis") for e in store.events())
    assert report.n_ingested + report.n_excluded_exit_side - sl.n_warnings == \
        report.n_signals


def test_the_family_filter_is_counted_not_silent():
    sl = load_slice(FIXTURES / "NFLX.slice.json")
    store = EntryEventStore()
    report = ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE,
                          families=("oracle_buy",))
    assert report.excluded_family_filter == 249 - 85 - 50  # signals - SELL - BUY
    assert {e.family for e in store.events()} == {"oracle_buy"}


# ---------------------------------------------------------------------------
# edges
# ---------------------------------------------------------------------------

def test_add_edge_requires_both_endpoints_to_exist():
    store = EntryEventStore()
    source = store.append(_event())
    with pytest.raises(EdgeEndpointMissing, match="never recorded"):
        store.add_edge(EventEdge(relation="promoted_by",
                                 source_event_id=str(source.event_id),
                                 target_event_id="f" * 16,
                                 link_basis="ts_join_synthesized"))


def test_edge_relation_and_link_basis_are_restricted_to_the_enums():
    with pytest.raises(EntryEventError, match="relation"):
        EventEdge(relation="caused_by", source_event_id="a", target_event_id="b",
                  link_basis="ts_join_synthesized")
    with pytest.raises(EntryEventError, match="link_basis"):
        EventEdge(relation="promoted_by", source_event_id="a", target_event_id="b",
                  link_basis="obviously")
    assert EDGE_RELATIONS == frozenset({"promoted_by", "dedup_suppressed_by"})
    assert EDGE_LINK_BASES == frozenset({"ts_join_synthesized", "emitter_recorded"})


def test_edges_are_objects_not_scalars_on_the_event():
    """A1.2.1: promotion/de-dup links are typed edges, never a scalar field."""
    fields = set(_event().to_dict())
    assert not (fields & {"promoted_by", "dedup_suppressed_by", "promoted_from",
                          "parent_event_id"})


def test_edge_append_is_idempotent_and_refuses_content_drift():
    store = EntryEventStore()
    a = store.append(_event(signal_ts="2026-08-05"))
    b = store.append(_event(signal_ts="2026-08-06"))
    edge = EventEdge(relation="promoted_by", source_event_id=str(a.event_id),
                     target_event_id=str(b.event_id),
                     link_basis="ts_join_synthesized", provenance="x")
    store.add_edge(edge)
    store.add_edge(edge)
    assert len(store.edges()) == 1
    with pytest.raises(AppendOnlyViolation):
        store.add_edge(EventEdge(relation="promoted_by", source_event_id=str(a.event_id),
                                 target_event_id=str(b.event_id),
                                 link_basis="ts_join_synthesized", provenance="y"))


def test_jsonl_round_trip_preserves_events_and_edges_exactly():
    _meta, store = _nflx_store()
    assert len(store) == 217 and len(store.edges()) == 15, "guard against a thin compare"
    back = EntryEventStore.from_jsonl(store.to_jsonl())
    assert [e.to_dict() for e in back.events()] == [e.to_dict() for e in store.events()]
    assert [g.to_dict() for g in back.edges()] == [g.to_dict() for g in store.edges()]


# ---------------------------------------------------------------------------
# families minted from CODE receipts, never from invented history (A4.3)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,quality,family,first_available", [
    ("BUY", "pending", "oracle_buy", {"kind": "era_fence", "value": "pre_fence"}),
    ("BUY", "override_take", "oracle_buy",
     {"kind": "era_fence", "value": "gc_v2_wo1 (07244dff)"}),
    ("REBUY", "reclaim_override_take", "oracle_rebuy",
     {"kind": "era_fence", "value": "gc_v2_wo2 (e152fd85)"}),
])
def test_synthetic_micro_slice_families_keep_their_quality_and_era(
        kind, quality, family, first_available):
    raw = {"type": kind, "ts": "2026-08-05", "known_ts": "2026-08-07",
           "quality": quality, "quality_reason": "unit fixture", "price": 1.0,
           "reasons": ["synthetic"], "regime": {"above200": True}, "strength": 0.5}
    sl = load_slice(_micro_slice([raw]))
    store = EntryEventStore()
    report = ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE)

    assert report.by_family == {f"{family}/{quality}": 1}
    event = store.events()[0]
    assert (event.family, event.subtype, event.quality) == (family, quality, quality)
    assert event.family_first_available == first_available
    # era_fence is not a date, so it can never put an event "before the channel".
    assert event.pre_channel_reconstruction is False
    assert event.family_era == "gc_v2_wo2"
    assert event.context == raw
    assert event.scored_authority is None
    assert event.field_origin["scored_authority"] == "artifact_absent"


def test_an_unreceipted_quality_lands_on_the_unrecorded_sentinel_not_pre_fence():
    """Absence of a receipt is recorded as absence, never borrowed from a sibling.

    ``stop_sweep_reclaim`` is the live example on this panel: A4.3 receipts the
    quality but mints no first-availability for it.  A quality the emitter has not
    shipped is the synthetic one.
    """
    assert family_first_available("oracle_reclaim", "stop_sweep_reclaim") == \
        {"kind": "unrecorded", "value": None}
    assert family_first_available("oracle_buy", "some_future_quality") == \
        {"kind": "unrecorded", "value": None}
    # ...while the dated and the era-bounded rows say WHICH kind they are.
    assert family_first_available("oracle_buy", "take") == \
        {"kind": "era_fence", "value": "pre_fence"}
    assert family_first_available("oracle_buy", "regime_blocked") == \
        {"kind": "quality_string_birth",
         "value": "2026-08-08 (HK-O1 #365, 7e49bade)"}
    assert family_first_available("oracle_reclaim", "reclaim") == \
        {"kind": "scored_promotion", "value": "2026-07-16"}
    assert family_first_available("grey_dot", None) == \
        {"kind": "artifact_channel_birth", "value": "2026-08-11"}
    # the accessor hands back a COPY — one event cannot rewrite the shared table
    got = family_first_available("grey_dot", None)
    got["value"] = "1999-01-01"
    assert family_first_available("grey_dot", None)["value"] == "2026-08-11"


def test_an_unminted_watch_subtype_is_a_receipt_gap_not_a_default():
    raw = {"type": "BOTTOM_WATCH", "subtype": "brand_new_kind", "ts": "2026-08-05",
           "known_ts": "2026-08-07", "quality": "washout_early_watch"}
    sl = load_slice(_micro_slice([raw]))
    store = EntryEventStore()
    report = ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE)
    assert report.excluded_unknown_type == {"BOTTOM_WATCH/brand_new_kind": 1}
    assert len(store) == 0


# ---------------------------------------------------------------------------
# same-bar discrimination — RESOLVED, with the refusal law kept
# ---------------------------------------------------------------------------

#: Receipts from ``NVDA.slice.json``: the three bars carrying TWO
#: `stop_sweep_reclaim` events each, with the two structure-stop anchors.
NVDA_SAME_BAR_RECLAIMS = {
    "2000-09-15": {"2000-09-11", "2000-09-13"},
    "2007-10-31": {"2007-10-25", "2007-10-29"},
    "2016-06-30": {"2016-06-24", "2016-06-29"},
}


def test_RESOLVED_same_bar_reclaims_get_distinct_ids():
    """Two reclaims of two different anchors on one bar are two events.

    Measured on the committed NVDA fixture: 2000-09-15, 2007-10-31 and
    2016-06-30 each carry two `stop_sweep_reclaim` events, identical in
    ``type``/``quality``/``ts`` and differing in ``anchor_ts`` (plus
    ``stop_level``/``sweep_low``/``quality_reason``).  The EMITTER's own
    ``anchor_ts`` is the seventh component of the address, so all six land — and
    the panel ingests instead of raising.
    """
    sl = load_slice(FIXTURES / "NVDA.slice.json")
    store = EntryEventStore()
    report = ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE)

    for ts, anchors in NVDA_SAME_BAR_RECLAIMS.items():
        raws = [s for s in sl.signals
                if s.get("type") == "RECLAIM" and s.get("ts") == ts]
        assert len(raws) == 2, f"fixture must still carry the {ts} pair"
        assert {s["anchor_ts"] for s in raws} == anchors
        assert len({s["quality"] for s in raws}) == 1

        events = [e for e in store.events()
                  if e.family == "oracle_reclaim" and e.signal_ts == ts]
        assert len(events) == 2, f"{ts} lost an event to an address collision"
        assert len({e.event_id for e in events}) == 2
        assert {e.context["anchor_ts"] for e in events} == anchors
        assert {e.subtype for e in events} == {"stop_sweep_reclaim"}
        # The distinguishing body travels with them, unflattened.  `stop_level`
        # alone would NOT separate them — the 2007-10-31 pair shares one
        # (0.72426); the anchor is what the emitter actually discriminates on.
        assert len({e.context["quality_reason"] for e in events}) == 2

    # 311 signals − 105 SELL = 206, with zero unknown types: the whole entry-side
    # stream now lands, where the six-part address refused 3 of it.
    assert (report.n_signals, report.n_ingested) == (311, 206)
    assert report.excluded_unknown_type == {}
    assert report.by_family["oracle_reclaim/stop_sweep_reclaim"] == 66

    # The G0 lane is unaffected — grey dots and watches have no such collision.
    g0_store = EntryEventStore()
    assert g0_events(sl, g0_store).counts["dots_total"] == 56


def test_the_discriminator_is_omitted_when_the_emitter_records_none():
    """Byte-stability: an event with no ``anchor_ts`` hashes the six-part tuple.

    Without this, widening the address would have moved every id in the store —
    a silent re-keying of every episode reference in §13.
    """
    args = dict(producer=TERMINAL_PRODUCER, family="oracle_buy", subtype="take",
                ticker="ZZTOP", signal_ts="2026-08-05", signal_era="gc_v2_wo2")
    independent = _independent_six_part_id(**args)

    assert compute_event_id(**args) == independent
    assert compute_event_id(**args, discriminator=None) == independent
    assert compute_event_id(**args, discriminator="2026-08-01") != independent
    assert _event().event_id == independent


def test_only_stop_sweep_reclaim_ids_move_on_the_real_panel():
    """Fixture-level byte-stability, without a stored snapshot to rot.

    Measured against the six-part form at adjudication time: NFLX 176 of 217 ids
    unchanged, TSLA 129 of 156 — the movers were exactly the `stop_sweep_reclaim`
    events.  Re-derived here from the six-part address so the pin survives a
    fixture refresh.
    """
    _meta, store = _nflx_store()
    moved, held = 0, 0
    for event in store.events():
        six_part = _independent_six_part_id(
            event.producer, event.family, event.subtype, event.ticker,
            event.signal_ts, event.source_identity.signal_era)
        if event.event_id == six_part:
            held += 1
            assert "anchor_ts" not in event.context
        else:
            moved += 1
            assert event.subtype == "stop_sweep_reclaim", (
                f"{event.family}/{event.subtype} was re-keyed by the discriminator; "
                f"only families the emitter discriminates may move")
            assert event.context["anchor_ts"]
    assert (held, moved) == (176, 41)


def test_two_events_the_emitter_CANNOT_discriminate_are_still_refused():
    """The residual law.  Widening the address records a REAL distinction; it is
    not a licence to absorb an unreal one.  Same bar, SAME ``anchor_ts``,
    different body ⇒ the artifact contradicts itself and the store says so.
    """
    def reclaim(stop_level):
        return {"type": "RECLAIM", "ts": "2026-08-05", "known_ts": "2026-08-07",
                "quality": "stop_sweep_reclaim", "anchor_ts": "2026-08-01",
                "stop_level": stop_level, "sweep_low": 1.0, "atr14": 0.1,
                "scored": False, "reasons": [], "regime": {}}

    sl = load_slice(_micro_slice([reclaim(9.0), reclaim(7.5)]))
    with pytest.raises(AppendOnlyViolation, match="never overwrites"):
        ingest_slice(sl, EntryEventStore(), as_of_reference_date=REFERENCE_DATE)

    # ...while the same pair with DIFFERENT anchors is two lawful events.
    two = load_slice(_micro_slice([reclaim(9.0),
                                   {**reclaim(7.5), "anchor_ts": "2026-07-30"}]))
    store = EntryEventStore()
    assert ingest_slice(two, store, as_of_reference_date=REFERENCE_DATE).n_ingested == 2


# ---------------------------------------------------------------------------
# the frozen field list + the two-door invariant
# ---------------------------------------------------------------------------

def test_entry_event_v1_field_list_is_frozen():
    """A1.2.1's field set, asserted mechanically rather than editorially."""
    assert set(event_dataclass_fields()) == set(EVENT_FIELDS)
    assert set(_event().to_dict()) == set(EVENT_FIELDS)
    for required in ("field_origin", "source_identity", "scored_authority",
                     "family_first_available", "family_era", "stage", "authority"):
        assert required in EVENT_FIELDS


def test_both_doors_into_one_store_agree_in_either_order():
    """`ingest_slice` and `g0_events` both mint BOTTOM_WATCH events.

    They must produce byte-identical content, or the append-only store sees two
    contents at one address and the second door raises.  Order-independence is
    the observable form of that invariant, and a refactor that moves the
    dot-coincidence marking into only one door breaks exactly this test.
    """
    sl = load_slice(FIXTURES / "NFLX.slice.json")

    ingest_first = EntryEventStore()
    ingest_slice(sl, ingest_first, as_of_reference_date=REFERENCE_DATE)
    g0_events(sl, ingest_first)

    g0_first = EntryEventStore()
    g0_events(sl, g0_first)
    ingest_slice(sl, g0_first, as_of_reference_date=REFERENCE_DATE)

    assert len(ingest_first) == len(g0_first) == 217
    left = sorted((e.to_dict() for e in ingest_first.events()),
                  key=lambda d: d["event_id"])
    right = sorted((e.to_dict() for e in g0_first.events()),
                   key=lambda d: d["event_id"])
    assert left == right


# ---------------------------------------------------------------------------
# detector identity + §13 lifecycle
# ---------------------------------------------------------------------------

def test_g0_is_registered_and_matches_its_implementation():
    """W2 registered G0 alone; W3 (PR-3) added the five challengers beside it.

    This test keeps G0's OWN pin — its presence, its era and its population rule —
    and no longer asserts the registry's SIZE, which is now W3's to pin
    (`tests/test_entry_radar_w3_detectors.py`).
    """
    assert "G0_GREY_DOT@1" in DETECTORS
    assert_g0_registry_matches_implementation()
    spec = get_spec("G0_GREY_DOT@1")
    assert spec.version == 1
    assert spec.spec["era_pin"] == "gc_v2_wo2"
    assert spec.spec["population_rule"] == \
        "early_dots UNION bottom_watches[subtype==early_dot].ts"


@pytest.mark.parametrize("detector_id", RESERVED_DETECTOR_IDS)
def test_a_reserved_detector_id_has_no_spec_and_says_so(detector_id):
    """PR-3 locks these.  A placeholder spec would hash to a meaningless value."""
    assert detector_id not in DETECTORS
    with pytest.raises(NotYetSpecified, match="RESERVED"):
        get_spec(detector_id)


def test_an_unknown_detector_id_is_an_error_not_a_default():
    with pytest.raises(DetectorError, match="unknown detector_id"):
        get_spec("C9_INVENTED")


@pytest.mark.parametrize("src,dst", [
    (DetectorState.PROBING, DetectorState.ARMED),
    (DetectorState.ARMED, DetectorState.TURNING),
    (DetectorState.ARMED, DetectorState.CANDIDATE),
    (DetectorState.ARMED, DetectorState.PROBING),
    (DetectorState.TURNING, DetectorState.CANDIDATE),
    (DetectorState.TURNING, DetectorState.ARMED),
    (DetectorState.CANDIDATE, DetectorState.RESOLVED),
    (DetectorState.CANDIDATE, DetectorState.INVALIDATED),
])
def test_legal_lifecycle_transitions(src, dst):
    TransitionRecord(ticker="ZZTOP", detector_id="G0_GREY_DOT@1", from_state=src,
                     to_state=dst, at="2026-08-14T14:00:00Z")


@pytest.mark.parametrize("src,dst", [
    (DetectorState.PROBING, DetectorState.CANDIDATE),
    (DetectorState.PROBING, DetectorState.RESOLVED),
    (DetectorState.ARMED, DetectorState.INVALIDATED),
    (DetectorState.ARMED, DetectorState.RESOLVED),
    (DetectorState.TURNING, DetectorState.RESOLVED),
    (DetectorState.CANDIDATE, DetectorState.ARMED),
])
def test_illegal_lifecycle_transitions_raise(src, dst):
    with pytest.raises(IllegalTransition):
        TransitionRecord(ticker="ZZTOP", detector_id="G0_GREY_DOT@1", from_state=src,
                         to_state=dst, at="2026-08-14T14:00:00Z")


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_terminal_states_have_no_exits(state):
    """A resolved episode that could be re-armed in place would rewrite history."""
    assert ALLOWED_TRANSITIONS[state] == frozenset()
    with pytest.raises(IllegalTransition, match="TERMINAL"):
        TransitionRecord(ticker="ZZTOP", detector_id="G0_GREY_DOT@1", from_state=state,
                         to_state=DetectorState.ARMED, at="2026-08-14T14:00:00Z")


def test_a_transition_record_carries_the_event_ids_that_justified_it():
    record = TransitionRecord(
        ticker="NFLX", detector_id="G0_GREY_DOT@1", from_state=DetectorState.PROBING,
        to_state=DetectorState.ARMED, at="2026-08-14T14:00:00Z",
        reason="grey dot 2026-07-28", evidence_refs=("abc123def4567890",))
    assert record.to_dict()["evidence_refs"] == ["abc123def4567890"]
    assert record.to_dict()["from_state"] == "PROBING"


# ---------------------------------------------------------------------------
# B1 — nothing that varies with the SLICE VINTAGE may ride event content
# ---------------------------------------------------------------------------

def _cap_slid(name: str, *, drop: int = 20):
    """The same slice with its side channel aged forward: oldest `drop` dots gone,
    `drop` newer sessions appended, `as_of` bumped to match.

    This is what a later nightly artifact looks like.  It slides the 40-cap
    window forward, which re-classifies dot-coincidence for bars that fell off
    the back — 2018-12-26 was IN the channel (so provably dotted) and is outside
    it here (so unknowable).
    """
    from lib import nyse_calendar

    raw = json.loads((FIXTURES / f"{name}.slice.json").read_text(encoding="utf-8"))
    doc = raw["indicator"]
    fresh = [d.isoformat() for d in
             nyse_calendar.sessions_between(date(2026, 8, 14), date(2026, 11, 1))][:drop]
    doc["early_dots"] = list(doc["early_dots"])[drop:] + fresh
    doc["as_of"] = f"{fresh[-1]}T00:00:00Z"
    return raw


def test_B1_a_cap_slide_does_not_change_content_at_a_fixed_event_id():
    """Two vintages of one symbol into ONE store must not collide.

    Dot-coincidence knowability is a property of the (event, SLICE VINTAGE) pair.
    While it rode watch-event ``context`` this ingest raised mid-slice on its own
    earlier record — a routine cross-vintage read turned into a crash, and the
    append-only store cannot roll back the half it already took.
    """
    first = load_slice(FIXTURES / "NFLX.slice.json")
    later = load_slice(_cap_slid("NFLX"))

    # the vintages genuinely disagree about knowability — otherwise this is vacuous
    a = ingest_slice(first, EntryEventStore(), as_of_reference_date=REFERENCE_DATE)
    b = ingest_slice(later, EntryEventStore(), as_of_reference_date=date(2026, 9, 12))
    assert "2018-12-26" not in a.unknowable_pre_cap
    assert "2018-12-26" in b.unknowable_pre_cap
    assert a.unknowable_pre_cap != b.unknowable_pre_cap

    # ...and both land in ONE store without a collision
    store = EntryEventStore()
    ingest_slice(first, store, as_of_reference_date=REFERENCE_DATE)
    g0_events(first, store)
    before = {e.event_id for e in store.events()
              if e.family.startswith("washout_")}
    ingest_slice(later, store, as_of_reference_date=date(2026, 9, 12))
    g0_events(later, store)
    after = {e.event_id for e in store.events() if e.family.startswith("washout_")}
    assert before == after, "watch event_ids must be vintage-stable"
    assert all("dot_coincidence" not in e.context for e in store.events())


# ---------------------------------------------------------------------------
# M3 — pre_channel_reconstruction: receipts §6 made mechanical
# ---------------------------------------------------------------------------

def test_M3_events_predating_their_family_channel_are_flagged():
    """"Earlier reconstructions are radar_derived, never emitter history" (§6).

    A `washout_early_watch` at 2004-07-30 is not something Terminal emitted in
    2004 — that channel was born 2026-08-11 (#392) — it is the current emitter
    run backwards over history.  Measured on the NFLX panel: 134 of 217 events
    predate their own family's first availability.
    """
    _meta, store = _nflx_store()
    flagged = [e for e in store.events() if e.pre_channel_reconstruction]
    assert (len(flagged), len(store)) == (134, 217)

    watch = next(e for e in store.events()
                 if e.family == "washout_early_watch" and e.signal_ts == "2004-07-30")
    assert watch.pre_channel_reconstruction is True
    assert watch.family_first_available == {"kind": "artifact_channel_birth",
                                            "value": "2026-08-11"}
    assert watch.field_origin["pre_channel_reconstruction"] == "radar_derived"

    # Every grey dot and watch on this panel predates the 2026-08-11 channel —
    # the newest is 2026-07-28.  That is the honest reading, not a bug.
    assert all(e.pre_channel_reconstruction
               for e in store.events()
               if e.family in ("grey_dot", "washout_early_watch",
                               "washout_trigger_watch"))


def test_M3_an_era_fenced_family_is_never_flagged():
    """An era is not a date, so it cannot put an event before a line."""
    _meta, store = _nflx_store()
    take = [e for e in store.events()
            if e.family == "oracle_buy" and e.subtype == "take"]
    assert take
    assert all(e.pre_channel_reconstruction is False for e in take)
    assert all(e.family_first_available["kind"] == "era_fence" for e in take)

    # ...and neither can an unrecorded receipt.
    sweeps = [e for e in store.events() if e.subtype == "stop_sweep_reclaim"]
    assert sweeps
    assert all(e.pre_channel_reconstruction is False for e in sweeps)


def test_M3_a_quality_string_birth_flags_only_what_predates_it():
    """`regime_blocked` was born 2026-08-08; the PHENOMENON is much older."""
    _meta, store = _nflx_store()
    blocked = [e for e in store.events() if e.subtype == "regime_blocked"]
    assert len(blocked) == 18
    assert max(e.signal_ts for e in blocked) == "2026-07-28"
    assert all(e.pre_channel_reconstruction for e in blocked), (
        "every regime_blocked fire on this panel predates the string's birth — "
        "they are relabelled history, not contemporaneous emitter rows")


def test_M3_the_flag_is_derived_and_a_contradicting_value_is_refused():
    receipt = {"kind": "artifact_channel_birth", "value": "2026-08-11"}
    assert _event(family="grey_dot", subtype=None, signal_ts="2020-01-02",
                  family_first_available=receipt).pre_channel_reconstruction is True
    assert _event(family="grey_dot", subtype=None, signal_ts="2026-08-12",
                  family_first_available=receipt).pre_channel_reconstruction is False
    with pytest.raises(EntryEventError, match="disagrees with signal_ts"):
        _event(family="grey_dot", subtype=None, signal_ts="2020-01-02",
               family_first_available=receipt, pre_channel_reconstruction=False)


def test_M3_a_bare_string_receipt_is_refused():
    with pytest.raises(EntryEventError, match="kind, value"):
        _event(family_first_available="pre_fence")
    with pytest.raises(EntryEventError, match="kind"):
        _event(family_first_available={"kind": "vibes", "value": "2020-01-01"})


# ---------------------------------------------------------------------------
# M4 — a slice lands whole or not at all
# ---------------------------------------------------------------------------

def test_M4_a_mid_slice_validation_failure_leaves_the_store_untouched():
    """An append-only store cannot be rolled back, so a half-ingested slice is a
    permanent lie about what we read.  Build+validate everything, then commit.
    """
    good = {"type": "BUY", "ts": "2026-08-03", "known_ts": "2026-08-05",
            "quality": "take", "reasons": [], "regime": {}}
    bad = {"type": "BUY", "ts": "2026-08-05", "known_ts": "2026-08-07",
           "quality": "not_a_real_quality", "reasons": [], "regime": {}}
    sl = load_slice(_micro_slice([good, bad]))
    store = EntryEventStore()

    with pytest.raises(EntryEventError, match="not an emitter quality"):
        ingest_slice(sl, store, as_of_reference_date=REFERENCE_DATE)
    assert store.events() == ()
    assert len(store) == 0

    # the good half alone still ingests
    ok = load_slice(_micro_slice([good]))
    assert ingest_slice(ok, store, as_of_reference_date=REFERENCE_DATE).n_ingested == 1


def test_M4_g0_events_is_all_or_nothing_too():
    """A BOTTOM_WATCH subtype with no minted family halts the whole projection."""
    watch = {"type": "BOTTOM_WATCH", "subtype": "brand_new_kind", "ts": "2026-07-01",
             "known_ts": "2026-07-03", "quality": "washout_early_watch"}
    sl = load_slice(_micro_slice([watch], early_dots=["2026-06-24"]))
    store = EntryEventStore()
    with pytest.raises(IndicatorSliceError, match="not a minted family"):
        g0_events(sl, store)
    assert store.events() == ()


# ---------------------------------------------------------------------------
# M5 — an exclusion count off a CAPPED channel is a floor, not a total
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,oldest", [
    ("NVDA", "2021-12-01"), ("NFLX", "2021-09-20"), ("TSLA", "2021-08-18"),
])
def test_M5_the_warnings_exclusion_declares_its_cap(name, oldest):
    """All three committed slices sit exactly at the emitter's 40-warning cap, so
    "40 excluded" means "at least 40" — and a consumer must be able to see that.
    """
    sl = load_slice(FIXTURES / f"{name}.slice.json")
    report = ingest_slice(sl, EntryEventStore(), as_of_reference_date=REFERENCE_DATE)
    assert report.excluded_exit_side["warnings"] == 40
    assert report.excluded_warnings_detail == {
        "counted": 40, "cap_bound": True, "oldest": oldest}
    assert report.to_dict()["excluded_warnings_detail"]["cap_bound"] is True


def test_M5_an_uncapped_warnings_channel_says_so():
    sl = load_slice(_micro_slice([], warnings=[{"kind": "confirm", "ts": "2026-01-05"},
                                               {"kind": "arm", "ts": "2026-02-09"}]))
    report = ingest_slice(sl, EntryEventStore(), as_of_reference_date=REFERENCE_DATE)
    assert report.excluded_warnings_detail == {
        "counted": 2, "cap_bound": False, "oldest": "2026-01-05"}
