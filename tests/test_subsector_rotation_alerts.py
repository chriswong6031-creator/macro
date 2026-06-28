"""Unit tests for engine.subsector_rotation_alerts — rotation change-detection."""
from __future__ import annotations

from engine import subsector_rotation_alerts as A


def _payload(subs):
    return {"generated_utc": "2026-06-28 00:00", "subsectors": subs}


def _sub(key, name, quadrant, rs_mom, accel, emerging_score, rs_ratio=0.0, perf=None):
    return {"key": key, "name": name, "theme": "T", "quadrant": quadrant,
            "rs_mom": rs_mom, "accel": accel, "emerging_score": emerging_score,
            "rs_ratio": rs_ratio, "perf": perf or {"1W": 5, "1M": 4, "3M": 3}}


def test_seed_is_silent():
    p = _payload([_sub("a", "A", "improving", 1.5, 4.0, 2.0)])
    assert A.compute_events(p, None) == []
    assert A.compute_events(p, {}) == []


def test_rotate_in_fires_on_flip():
    p = _payload([_sub("a", "A", "improving", 1.5, 4.0, 2.0)])
    prior = {"a": {"quadrant": "lagging", "emerging": False}}
    evs = A.compute_events(p, prior)
    assert len(evs) == 1
    e = evs[0]
    assert e["type"] == "rotation_emerging" and e["asset"] == "a"
    assert e["source"] == "rotation" and e["severity"] == "high"  # score >= 1.8
    assert "Rotating in" in e["headline"]


def test_no_refire_when_already_emerging():
    p = _payload([_sub("a", "A", "improving", 1.5, 4.0, 2.0)])
    prior = {"a": {"quadrant": "improving", "emerging": True}}
    assert A.compute_events(p, prior) == []


def test_rotate_out_fires_when_leader_rolls_over():
    p = _payload([_sub("a", "A", "weakening", -2.0, -1.0, -0.5, rs_ratio=1.5)])
    prior = {"a": {"quadrant": "leading", "emerging": True}}
    evs = A.compute_events(p, prior)
    assert len(evs) == 1 and evs[0]["type"] == "rotation_fading"
    assert "Rolling over" in evs[0]["headline"]


def test_below_bar_does_not_fire():
    # improving but weak score / negative accel → not "emerging".
    p = _payload([_sub("a", "A", "improving", 0.2, -0.5, 0.3)])
    prior = {"a": {"quadrant": "lagging", "emerging": False}}
    assert A.compute_events(p, prior) == []


def test_snapshot_roundtrip():
    p = _payload([_sub("a", "A", "improving", 1.5, 4.0, 2.0)])
    snap = A._snapshot(p)
    assert snap["a"]["emerging"] is True and snap["a"]["quadrant"] == "improving"
