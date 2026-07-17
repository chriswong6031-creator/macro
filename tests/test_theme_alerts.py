"""Theme Rotation alert engine (engine.theme_alerts) — run-over-run change detection.

Verify the seed run is silent (no first-run storm), each lifecycle / reco flip fires the
right event exactly once, a label event suppresses the duplicate reco_change for that
basket, leadership rotation fires on a new #1, and the jsonl round-trip dedups by id and
honours the keep window. Pure logic + a tmp-dir round-trip; no network.
"""
from __future__ import annotations

import json

import pytest

from engine import theme_alerts as ta
from lib import config


def _theme(tid, label="neutral", reco="hold", rank=5, score=50):
    return {"id": tid, "label": label, "reco": reco, "rank": rank, "score": score,
            "name": tid.upper(), "name_zh": tid}


def _intel(themes, as_of="2026-06-18"):
    return {"as_of": as_of, "themes": themes}


# --------------------------------------------------------------- change detection
def test_seed_run_is_silent():
    intel = _intel([_theme("ai", "dominant", "accumulate", 1, 70)])
    assert ta.compute_events(intel, None) == []
    assert ta.compute_events(intel, {}) == []


def test_reco_flip_fires_once():
    prior = {"ai": _theme("ai", "neutral", "hold", 3, 50)}
    intel = _intel([_theme("ai", "emerging", "enter", 2, 58)])
    evs = ta.compute_events(intel, prior)
    types = {e["type"] for e in evs}
    # emerging label event fires; the reco_change is SUPPRESSED (label covers the basket)
    assert "theme_emerging" in types
    assert "reco_change" not in types
    assert len(evs) == 1


def test_pure_reco_change_without_label_change():
    prior = {"ai": _theme("ai", "dominant", "hold", 1, 66)}
    intel = _intel([_theme("ai", "dominant", "accumulate", 1, 68)])
    evs = ta.compute_events(intel, prior)
    assert len(evs) == 1 and evs[0]["type"] == "reco_change"
    assert evs[0]["context"]["from"] == "hold" and evs[0]["context"]["to"] == "accumulate"


def test_topping_event_dominant_to_fading():
    prior = {"x": _theme("x", "dominant", "accumulate", 1, 70)}
    intel = _intel([_theme("x", "fading", "trim", 2, 60)])
    evs = ta.compute_events(intel, prior)
    assert [e["type"] for e in evs] == ["theme_topping"]
    assert evs[0]["severity"] == "high"


def test_deteriorating_event():
    prior = {"x": _theme("x", "neutral", "hold", 4, 48)}
    intel = _intel([_theme("x", "deteriorating", "avoid", 9, 32)])
    evs = ta.compute_events(intel, prior)
    assert [e["type"] for e in evs] == ["theme_deteriorating"]


def test_leadership_rotation_fires_on_new_number_one():
    prior = {"a": _theme("a", "dominant", "accumulate", 1, 70),
             "b": _theme("b", "dominant", "hold", 2, 66)}
    intel = _intel([_theme("b", "dominant", "accumulate", 1, 72),
                    _theme("a", "dominant", "hold", 2, 69)])
    evs = ta.compute_events(intel, prior)
    rot = [e for e in evs if e["type"] == "leadership_rotation"]
    assert len(rot) == 1 and rot[0]["asset"] == "b"


def test_event_ids_are_stable_and_bilingual():
    prior = {"x": _theme("x", "neutral", "hold", 4, 48)}
    intel = _intel([_theme("x", "deteriorating", "avoid", 9, 32)])
    e = ta.compute_events(intel, prior)[0]
    assert e["id"].startswith("themes:x:theme_deteriorating:2026-06-18")
    assert e["headline_zh"] and e["headline_zh"] != e["headline"]
    assert e["anchor"] == "#theme-x"


# --------------------------------------------------------------- jsonl round-trip
def test_rebuild_seed_then_change_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    intel1 = _intel([_theme("ai", "dominant", "hold", 1, 66),
                     _theme("en", "neutral", "hold", 2, 50)], as_of="2026-06-18")

    # seed run: no events, state persisted, alerts file empty
    assert ta.rebuild(intel1) == []
    assert (tmp_path / "themes" / "state.json").exists()
    assert ta.load_events() == []

    # next run: 'en' enters emerging — constructive flip is DEBOUNCED (N_STREAK=2)
    intel2 = _intel([_theme("ai", "dominant", "hold", 1, 66),
                     _theme("en", "emerging", "enter", 2, 58)], as_of="2026-06-19")
    assert ta.rebuild(intel2) == []     # buffered on first sighting
    assert ta.load_events() == []

    # confirming run on the next session date → one fresh event fires
    intel3 = _intel([_theme("ai", "dominant", "hold", 1, 66),
                     _theme("en", "emerging", "enter", 2, 59)], as_of="2026-06-20")
    fired = ta.rebuild(intel3)
    assert len(fired) == 1 and fired[0]["type"] == "theme_emerging"
    assert len(ta.load_events()) == 1

    # idempotent re-run on the SAME payload → no new event, no dup line (keep-first by id)
    assert ta.rebuild(intel3) == []
    assert len(ta.load_events()) == 1
    assert len(ta.recent(30, as_of="2026-06-20")) == 1
