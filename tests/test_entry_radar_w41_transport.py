"""W4.1 — the live-transport correction contract tests.

Radar W4.1 (research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md §6 item
2A, WS:LIVE-ENTRY-RADAR W4.1 wave row) fixes two transport gaps that made
Radar's canonical live output structurally unreachable:

  1. the RTH evaluator's confirmed-lane reader (``live_eval._nightly_lanes``)
     read a pack field (``probe_set["nightly_lanes"]``) no writer ever
     populated, so G0/C5 confirmed-bar lanes were ALWAYS ``unavailable``
     regardless of whether a Terminal slice store existed;
  2. the W5 nightly reconciler's spool reader (``read_spool_events``) gated on
     a top-level schema no real W4 producer has ever emitted, so every
     ``entry_radar.events/v1`` pass envelope W4 has ever spooled was silently
     counted-by-omission as "off-schema".

Both are transport-plane fixes: no detector spec, no firing predicate and no
``mastermind.entry_event.v1`` event field changes.  These tests pin the FULL
real pipeline for each — a real pack round-trip for (1), a real
``build_event_payload()`` envelope consumed by ``read_spool_events()`` for (2)
— rather than a synthetic shape that could quietly drift from what the real
producers emit again.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine.entry_radar import live_eval as le
from engine.entry_radar import live_ledger as ll
from engine.entry_radar import live_pack as lp
from engine.entry_radar.entry_events import build_radar_native_event
from engine.entry_radar.replay import prereg
from scripts import reconcile_entry_radar as rec

C1_DETECTOR = "C1_1D_LIVE_WASHOUT@1"
C1_SPEC_HASH = prereg.EXPECTED_SPEC_HASHES[C1_DETECTOR]


# =============================================================================
# helpers
# =============================================================================
def _native_event(ticker: str = "AAPL", *, signal_ts: str = "2026-08-14T19:55:00Z",
                  session: str = "2026-08-14") -> dict:
    """One real, validly-constructed ``mastermind.entry_event.v1`` dict."""
    event = build_radar_native_event(
        detector_id=C1_DETECTOR, detector_spec_hash=C1_SPEC_HASH, ticker=ticker,
        family="radar_1d_live_washout", subtype="live_k_lt_20",
        signal_ts=signal_ts, market_session=session, bar_state="provisional")
    return event.to_dict()


def _envelope(events: list[dict], *, pass_ts: str, pass_id: str = "pass-1",
             pack_as_of: str = "2026-08-14", pack_hash: str = "0" * 16) -> dict:
    """A REAL W4 pass envelope, built through the actual production function —
    never a hand-typed approximation of its shape."""
    delta = ll.PendingDelta(ticker="*", as_of_session=pack_as_of, pass_id=pass_id,
                            events=tuple(events))
    return ll.build_event_payload(delta, pass_ts=pass_ts, pack_as_of=pack_as_of,
                                  pack_hash=pack_hash)


def _write_jsonl(path, objects: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(o) for o in objects) + "\n", encoding="utf-8")


# =============================================================================
# Part A — W4->W5 envelope contract (item 2)
# =============================================================================
def test_a_real_w4_envelope_is_no_longer_off_schema(tmp_path):
    """The exact defect: every real envelope W4 has ever produced was
    previously counted-by-omission.  This is the control that proves it now
    reaches ``read_spool_events`` at all."""
    event = _native_event()
    env = _envelope([event], pass_ts="2026-08-14T20:05:00Z")
    assert env["schema"] == rec.ENVELOPE_SCHEMA == ll.SCHEMA_ENTRY_RADAR_EVENTS

    spool = tmp_path / "spool"
    _write_jsonl(spool / "2026-08-14.jsonl", [env])
    records = rec.read_spool_events(spool)
    assert len(records) == 1


def test_event_identity_is_preserved_byte_exact_through_the_envelope(tmp_path):
    """Exact-event preservation (contract item 3): every ``mastermind.entry_event.v1``
    field the store minted survives `EntryEventStore -> PendingDelta ->
    build_event_payload -> read_spool_events` unchanged.  Only transport-plane
    keys (`observed_at`, `_spool_path`) may be added, and NEVER inside the
    frozen field set itself."""
    from engine.entry_radar.entry_events import EVENT_FIELDS

    event = _native_event()
    env = _envelope([event], pass_ts="2026-08-14T20:05:00Z")
    spool = tmp_path / "spool"
    _write_jsonl(spool / "2026-08-14.jsonl", [env])
    [record] = rec.read_spool_events(spool)

    for field_name in EVENT_FIELDS:
        assert record[field_name] == event[field_name], field_name
    # transport keys are ADDITIVE, never a mutation of a frozen field
    assert set(record) - set(EVENT_FIELDS) <= {"observed_at", "_spool_path"}


def test_first_observation_is_the_earliest_envelope_pass_ts(tmp_path):
    """§4: `first_observed_at` = the earliest envelope `pass_ts` that carried the
    `event_id` — not the latest, and not simply the file-encounter order."""
    event = _native_event()
    early = _envelope([event], pass_ts="2026-08-14T19:35:00Z", pass_id="pass-early")
    late = _envelope([event], pass_ts="2026-08-14T20:05:00Z", pass_id="pass-late")

    spool = tmp_path / "spool"
    # LATE written/discovered first (reverse chronological filename) — proves
    # the result is a genuine min(), not "whichever the walk sees first".
    _write_jsonl(spool / "a-late.jsonl", [late])
    _write_jsonl(spool / "b-early.jsonl", [early])
    records = rec.read_spool_events(spool)
    assert len(records) == 2
    assert {r["observed_at"] for r in records} == {"2026-08-14T19:35:00Z"}


def test_a_torn_inner_event_is_skipped_never_repaired(tmp_path, capsys):
    """A malformed event INSIDE an otherwise well-formed envelope is
    counted-by-omission, exactly like a torn spool file always was — it must
    never crash the reconciler and must never be silently invented."""
    good = _native_event("AAPL")
    torn = {"ticker": "ZZZZ"}  # not a lawful mastermind.entry_event.v1 record
    env = _envelope([good, torn], pass_ts="2026-08-14T20:05:00Z")

    spool = tmp_path / "spool"
    _write_jsonl(spool / "2026-08-14.jsonl", [env])
    records = rec.read_spool_events(spool)
    assert len(records) == 1
    assert records[0]["ticker"] == "AAPL"
    assert "SKIPPED" in capsys.readouterr().out


def test_the_bare_event_shape_still_works_alongside_a_real_envelope(tmp_path):
    """Backward compatibility: a producer (or fixture) that spools one bare
    `mastermind.entry_event.v1` record directly, with no envelope, coexists
    with a real W4 envelope in the same spool."""
    bare = {
        "schema": rec.SPOOL_EVENT_SCHEMA,
        "record": {
            "event_id": "bare-1", "producer": "entry_radar",
            "detector_id": "C2_1D_TURN@1", "ticker": "MSFT",
            "family": "radar_turn", "subtype": "c2_turn",
            "context": {"market_session": "2026-08-14"},
            "signal_ts": "2026-08-14T19:55:00Z",
            "signal_known_ts": "2026-08-14T20:00:00Z",
            "observed_at": "2026-08-14T20:00:05Z",
            "bar_state": "confirmed", "final": True,
            "source_identity": {"detector_spec_hash":
                                prereg.EXPECTED_SPEC_HASHES["C2_1D_TURN@1"]},
        },
    }
    env = _envelope([_native_event("AAPL")], pass_ts="2026-08-14T20:05:00Z")

    spool = tmp_path / "spool"
    _write_jsonl(spool / "2026-08-14.jsonl", [bare, env])
    records = rec.read_spool_events(spool)
    tickers = {r["ticker"] for r in records}
    assert tickers == {"MSFT", "AAPL"}


def test_end_to_end_main_writes_a_forward_row_from_a_real_envelope(tmp_path,
                                                                    monkeypatch):
    """The full nightly pipeline, driven by the REAL producer's envelope shape:
    a `forward.parquet` row lands with `observed_at_basis == spool_envelope`
    and the pass_ts-derived `observed_at`, event identity intact."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(rec, "LIVE_FORWARD_EPOCH", "2026-01-01T00:00:00+00:00")

    event = _native_event("AAPL")
    env = _envelope([event], pass_ts="2026-08-14T20:05:00Z")
    spool = tmp_path / "spool"
    _write_jsonl(spool / "2026-08-14.jsonl", [env])
    monkeypatch.setenv(rec.SPOOL_DIR_ENV, str(spool))

    assert rec.main(["--root", str(tmp_path), "--nightly"]) == 0
    frame = pd.read_parquet(tmp_path / "data" / "entry_radar" / rec.FORWARD_NAME)
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["ticker"] == "AAPL"
    assert row["detector_id"] == C1_DETECTOR
    assert row["observed_at"] == "2026-08-14T20:05:00Z"
    assert row["observed_at_basis"] == "spool_envelope"
    assert row["episode_address"] == event["event_id"]
    assert row["state"] == rec.STATE_LIVE_FORWARD


# =============================================================================
# Part B — confirmed-lane pack transport (item 1)
# =============================================================================
def _minimal_pack(confirmed_lanes=None, *, tickers=("AAPL",)):
    return lp.build_pack(
        probe_set=list(tickers), store_reader=lambda t: None,
        as_of="2026-08-13", built_at="2026-08-13T21:00:00Z",
        confirmed_lanes=confirmed_lanes)


def test_v2_schema_and_default_confirmed_lanes_are_honestly_unavailable():
    pack = _minimal_pack()
    assert pack.schema == lp.SCHEMA_LIVE_PACK == "entry_radar.live_pack/v2"
    assert pack.confirmed_lanes["AAPL"] == {
        "g0": {"availability": "unavailable", "reason": "slice_store_unconfigured"},
        "c5": {"availability": "unavailable", "reason": "slice_store_unconfigured"},
    }


def test_a_real_confirmed_lane_row_survives_into_the_pack_and_the_rth_reader():
    lanes_in = {"AAPL": {"g0": {"availability": "available", "grey_events": 2},
                         "c5": {"availability": "available", "candidates": 1}}}
    pack = _minimal_pack(lanes_in)
    assert pack.confirmed_lanes["AAPL"]["g0"]["availability"] == "available"
    assert pack.confirmed_lanes["AAPL"]["g0"]["grey_events"] == 2

    # the RTH reader (`live_eval._nightly_lanes`) is the actual consumer
    row = le._nightly_lanes(pack, "AAPL")
    assert row["g0"]["availability"] == "available"
    assert row["c5"]["candidates"] == 1

    # a ticker the confirmed-lane source never covered stays honest
    absent = le._nightly_lanes(pack, "NVDA")
    assert absent == {
        "g0": {"availability": "unavailable", "reason": "slice_store_unconfigured"},
        "c5": {"availability": "unavailable", "reason": "slice_store_unconfigured"}}


def test_confirmed_lanes_are_covered_by_the_pack_hash():
    """A pack whose slice read moved must not hash equal to one whose did not —
    confirmed_lanes is firing-relevant to the confirmed-bar lanes exactly as
    the six inverted thresholds are to C1/C2a."""
    baseline = _minimal_pack(None)
    moved = _minimal_pack(
        {"AAPL": {"g0": {"availability": "available", "grey_events": 9},
                  "c5": {"availability": "available", "candidates": 9}}})
    assert baseline.pack_hash != moved.pack_hash


def test_a_v1_pack_with_no_confirmed_lanes_field_reads_unavailable_not_a_crash():
    """Back-compat: a pre-W4.1 pack manifest has no `confirmed_lanes` key at
    all.  `load_pack` must default it, and the RTH reader must not KeyError."""
    manifest = {
        "schema": "entry_radar.live_pack/v1",
        "as_of": "2026-08-13", "next_session": "2026-08-14", "built_at": "",
        "price_basis": "adjusted", "spec_hashes": {}, "probe_set": {},
        "names": [], "substrate_missing": [], "pack_hash": "deadbeef",
    }
    pack = lp.LivePack(
        schema=manifest["schema"], as_of=manifest["as_of"],
        next_session=manifest["next_session"], built_at="",
        price_basis="adjusted", spec_hashes={}, probe_set={}, names=(),
        pack_hash="deadbeef")
    assert pack.confirmed_lanes == {}
    row = le._nightly_lanes(pack, "AAPL")
    assert row["g0"]["reason"] == "slice_store_unconfigured"


_UNAVAILABLE = {"availability": "unavailable", "reason": "slice_store_unconfigured"}


@pytest.mark.parametrize("bad_row,expected_g0,expected_c5", [
    # one lane malformed, its SIBLING lane is untouched — normalization is
    # per-lane, so a bad g0 read must not also blind a good c5 read.
    ({"g0": {"availability": "maybe"}, "c5": {"availability": "available"}},
     _UNAVAILABLE, {"availability": "available"}),
    ({"g0": "not-a-mapping", "c5": {"availability": "available"}},
     _UNAVAILABLE, {"availability": "available"}),
    # the WHOLE row is not a mapping at all -> both lanes fall to the default
    ("not-a-mapping-at-all", _UNAVAILABLE, _UNAVAILABLE),
    (None, _UNAVAILABLE, _UNAVAILABLE),
])
def test_a_malformed_confirmed_lane_row_normalizes_to_unavailable(
        bad_row, expected_g0, expected_c5):
    """The null law applied AT THE PACK BOUNDARY: a malformed nightly-builder
    input can never reach a live reader as a plausible 'available' row — but a
    malformed LANE does not need to blind its sound sibling lane."""
    normalized = lp.confirmed_lanes_snapshot({"AAPL": bad_row}, ["AAPL"])
    assert normalized["AAPL"] == {"g0": expected_g0, "c5": expected_c5}
