"""Hermetic tests for engine.oracle.alerts — idempotency, silent seed, alert types.

All fixtures synthetic.  Verifies the R4 mandates:
  - false-start rate embedded in oracle_onset detail text
  - silent seed on first run (no prior state → no events)
  - idempotent ids
  - rollover fires when confirmed-OUT episode disappears
  - regime event fires on breadth crossing
"""
from __future__ import annotations

import json

import pytest

from engine.oracle import alerts as A


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _state(episodes=None, breadth=0.5, n_active=2, asof="2026-07-01"):
    return {
        "schema": "oracle_state.v1",
        "asof": asof,
        "regime": {"n_active_complexes": n_active, "breadth": breadth, "vix_regime": 0.38},
        "complexes": [],
        "active_episodes": episodes or [],
        "onset_watchlist": [],
        "disclaimers": {
            "display_only": True,
            "error_rates": {
                "onset_to_confirmed_conversion": 0.997,
                "false_start_rate": 0.38,
            },
        },
    }


def _ep(node, direction, tier, two_sided=False, pair=None, surv=False):
    od = "2026-06-25"
    cd = "2026-06-28" if tier in ("confirmed", "undeniable") else None
    return {
        "node": node, "direction": direction, "tier": tier,
        "onset_date": od, "confirmed_date": cd,
        "two_sided": two_sided, "pair": pair,
        "survivorship_flagged": surv,
    }


# ---------------------------------------------------------------------------
# Core contract: silent seed
# ---------------------------------------------------------------------------

def test_seed_is_silent_with_none_prior():
    state = _state([_ep("XLK", "out", "onset")])
    assert A.compute_events(state, None) == []


def test_seed_is_silent_with_empty_prior():
    state = _state([_ep("XLK", "out", "onset")])
    assert A.compute_events(state, {}) == []


# ---------------------------------------------------------------------------
# oracle_onset
# ---------------------------------------------------------------------------

def test_onset_fires_on_new_episode():
    state = _state([_ep("XLK", "out", "onset")])
    prior = {"__regime__": {"breadth": 0.5}}
    evs = A.compute_events(state, prior)
    assert len(evs) == 1
    e = evs[0]
    assert e["type"] == "oracle_onset"
    assert e["asset"] == "XLK"
    assert e["severity"] == "minor"
    assert e["source"] == "oracle"


def test_onset_detail_embeds_false_start_rate():
    """R4 mandate: onset detail MUST contain the false-start rate."""
    state = _state([_ep("XLK", "out", "onset")])
    prior = {"__regime__": {"breadth": 0.5}}
    evs = A.compute_events(state, prior)
    assert len(evs) == 1
    detail = evs[0]["detail"]
    # 0.38 formatted as 38%
    assert "38%" in detail
    assert "false-start rate" in detail.lower()


def test_onset_no_refire_when_already_onset():
    state = _state([_ep("XLK", "out", "onset")])
    prior = {"XLK__out": {"tier": "onset", "direction": "out", "two_sided": False}}
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_onset" for e in evs)


# ---------------------------------------------------------------------------
# oracle_confirmed
# ---------------------------------------------------------------------------

def test_confirmed_fires_when_advancing_from_onset():
    state = _state([_ep("XLK", "out", "confirmed")])
    prior = {"XLK__out": {"tier": "onset", "direction": "out", "two_sided": False},
             "__regime__": {"breadth": 0.5}}
    evs = A.compute_events(state, prior)
    conf_evs = [e for e in evs if e["type"] == "oracle_confirmed"]
    assert len(conf_evs) == 1
    assert conf_evs[0]["severity"] == "minor"


def test_confirmed_no_refire_when_already_confirmed():
    state = _state([_ep("XLK", "out", "confirmed")])
    prior = {"XLK__out": {"tier": "confirmed", "direction": "out", "two_sided": False}}
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_confirmed" for e in evs)


# ---------------------------------------------------------------------------
# oracle_rollover (the loudest exit surface)
# ---------------------------------------------------------------------------

def test_rollover_fires_when_confirmed_out_episode_exhausts():
    """A prior confirmed OUT episode that is now absent → rollover event."""
    state = _state([])  # no active episodes (exhausted)
    prior = {
        "XLK__out": {"tier": "confirmed", "direction": "out", "two_sided": False},
        "__regime__": {"breadth": 0.5},
    }
    evs = A.compute_events(state, prior)
    ro_evs = [e for e in evs if e["type"] == "oracle_rollover"]
    assert len(ro_evs) == 1
    assert ro_evs[0]["severity"] == "high"
    assert ro_evs[0]["asset"] == "XLK"


def test_rollover_does_not_fire_for_onset_only():
    """onset-tier out episodes that exhaust do NOT fire rollover."""
    state = _state([])
    prior = {
        "XLK__out": {"tier": "onset", "direction": "out", "two_sided": False},
    }
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_rollover" for e in evs)


def test_rollover_does_not_fire_for_in_direction():
    """IN episodes exhausting do NOT fire rollover."""
    state = _state([])
    prior = {
        "XLV__in": {"tier": "confirmed", "direction": "in", "two_sided": False},
    }
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_rollover" for e in evs)


# ---------------------------------------------------------------------------
# oracle_two_sided
# ---------------------------------------------------------------------------

def test_two_sided_fires_when_newly_paired():
    state = _state([_ep("XLK", "out", "confirmed", two_sided=True, pair="healthcare")])
    prior = {
        "XLK__out": {"tier": "confirmed", "direction": "out", "two_sided": False},
        "__regime__": {"breadth": 0.5},
    }
    evs = A.compute_events(state, prior)
    ts_evs = [e for e in evs if e["type"] == "oracle_two_sided"]
    assert len(ts_evs) == 1
    assert ts_evs[0]["severity"] == "high"


def test_two_sided_no_refire_when_already_two_sided():
    state = _state([_ep("XLK", "out", "confirmed", two_sided=True, pair="healthcare")])
    prior = {
        "XLK__out": {"tier": "confirmed", "direction": "out", "two_sided": True},
    }
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_two_sided" for e in evs)


# ---------------------------------------------------------------------------
# oracle_regime
# ---------------------------------------------------------------------------

def test_regime_fires_on_breadth_crossing_floor():
    state = _state([], breadth=0.70, n_active=3)
    prior = {"__regime__": {"breadth": 0.60}}
    evs = A.compute_events(state, prior)
    rg_evs = [e for e in evs if e["type"] == "oracle_regime"]
    assert len(rg_evs) == 1
    assert rg_evs[0]["severity"] == "high"


def test_regime_no_fire_when_already_above_floor():
    state = _state([], breadth=0.75, n_active=3)
    prior = {"__regime__": {"breadth": 0.72}}
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_regime" for e in evs)


def test_regime_no_fire_when_below_floor():
    state = _state([], breadth=0.55, n_active=1)
    prior = {"__regime__": {"breadth": 0.50}}
    evs = A.compute_events(state, prior)
    assert not any(e["type"] == "oracle_regime" for e in evs)


# ---------------------------------------------------------------------------
# Idempotent ids
# ---------------------------------------------------------------------------

def test_event_ids_are_deterministic_for_same_date():
    """Same episode same date → same id → setdefault keeps first occurrence."""
    state = _state([_ep("XLK", "out", "onset")])
    prior = {"__regime__": {"breadth": 0.5}}
    e1 = A.compute_events(state, prior)[0]
    e2 = A.compute_events(state, prior)[0]
    assert e1["id"] == e2["id"]


def test_snapshot_structure():
    state = _state([_ep("XLK", "out", "confirmed")])
    snap = A._snapshot(state)
    assert "XLK__out" in snap
    assert snap["XLK__out"]["tier"] == "confirmed"
    assert "__regime__" in snap


# ---------------------------------------------------------------------------
# Bilingual fields
# ---------------------------------------------------------------------------

def test_events_are_bilingual():
    state = _state([_ep("XLK", "out", "onset")])
    prior = {"__regime__": {"breadth": 0.5}}
    evs = A.compute_events(state, prior)
    for e in evs:
        assert e.get("headline_zh"), f"Missing headline_zh on {e.get('type')}"
        assert e.get("detail_zh"), f"Missing detail_zh on {e.get('type')}"


# ---------------------------------------------------------------------------
# rebuild() integration test
# ---------------------------------------------------------------------------

def test_rebuild_is_idempotent(tmp_path):
    """Running rebuild correctly:
      - run 1 (no prior state): SEED silently — 0 events
      - run 2 (new episode XLV confirmed, prior has XLK onset): fires oracle_onset for XLV advance
        which in this test means XLV is NEW to prior → fires oracle_onset
      - run 3 (same state as run 2): 0 new events
    """
    import engine.oracle.alerts as OA_mod
    # Patch paths to use tmp_path
    orig_dir = OA_mod._dir
    orig_state = OA_mod._state_path
    orig_path = OA_mod._path

    OA_mod._dir = lambda: tmp_path / "oracle"
    OA_mod._state_path = lambda: tmp_path / "oracle" / "alerts_state.json"
    OA_mod._path = lambda: tmp_path / "oracle" / "oracle_alerts.jsonl"

    try:
        (tmp_path / "oracle").mkdir()
        # Run 1: no prior state → seed silently
        state1 = _state([_ep("XLK", "out", "onset")])
        new1 = OA_mod.rebuild(state1)
        assert new1 == []  # silent seed

        # Run 2: prior has XLK__out onset; now add XLV in onset (brand NEW episode)
        state2 = _state([_ep("XLK", "out", "onset"), _ep("XLV", "in", "onset")])
        new2 = OA_mod.rebuild(state2)
        # XLV__in is new (not in prior) → fires oracle_onset
        assert len(new2) == 1
        assert new2[0]["type"] == "oracle_onset"
        assert new2[0]["asset"] == "XLV"

        # Run 3: same state as run 2 → no new events
        state3 = _state([_ep("XLK", "out", "onset"), _ep("XLV", "in", "onset")])
        new3 = OA_mod.rebuild(state3)
        assert new3 == []

    finally:
        OA_mod._dir = orig_dir
        OA_mod._state_path = orig_state
        OA_mod._path = orig_path
