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


# ── turn-lane events (engine.subsector_turn) ───────────────────────────────────
def _turn_sub(key, state, **kw):
    s = _sub(key, key.upper(), "improving", 1.0, 2.0, 1.5)
    s.update({"turn_state": state, "turn_since": "2026-06-28", "n_members": 8,
              "bottom_score": 0.8, "top_score": 0.8, "turn_score": 0.8,
              "dd_from_peak": -14.0, "up_from_trough": 30.0,
              "breadth": {"n": 8, "turn_up": 0.9, "turn_dn": 0.9, "concentrated": False},
              "pace_mkt": {"w1": -1.0}, "legs_up": {}, "legs_dn": {}})
    s.update(kw)
    return s


def test_turn_up_fires_once_on_the_transition():
    p = _payload([_turn_sub("a", "turn_up")])
    prior = {"a": {"name": "A", "theme": "T", "quadrant": "improving", "emerging": True,
                   "turn_state": "bottoming"}}
    evs = [e for e in A.compute_events(p, prior) if e["type"] == "rotation_turn_up"]
    assert len(evs) == 1 and evs[0]["severity"] == "high"
    # already in the state → no re-fire
    prior2 = {"a": {**prior["a"], "turn_state": "turn_up"}}
    assert [e for e in A.compute_events(p, prior2) if e["type"].startswith("rotation_turn")] == []


def test_turn_lane_seeds_silently_when_prior_predates_the_field():
    """A state file written before the turn engine shipped must not fire 11 turns at once."""
    p = _payload([_turn_sub("a", "turn_up"), _turn_sub("b", "turn_down")])
    prior = {"a": {"name": "A", "theme": "T", "quadrant": "improving", "emerging": True},
             "b": {"name": "B", "theme": "T", "quadrant": "weakening", "emerging": False}}
    assert [e for e in A.compute_events(p, prior) if e["type"].startswith("rotation_turn")] == []


def test_turn_severity_needs_size_and_breadth():
    """RC-R5: a one-name move cannot print `high` however violent its score."""
    thin = _turn_sub("t", "turn_up", n_members=2,
                     breadth={"n": 2, "turn_up": 1.0, "turn_dn": 0.0, "concentrated": True})
    assert A._turn_severity(thin, up=True) == "minor"
    narrow = _turn_sub("n", "turn_up", n_members=8,
                       breadth={"n": 8, "turn_up": 0.25, "turn_dn": 0.0, "concentrated": True})
    assert A._turn_severity(narrow, up=True) == "medium"
    assert A._turn_severity(_turn_sub("g", "turn_up"), up=True) == "high"
    # an unconfirmed candidate never reaches high
    assert A._turn_severity(_turn_sub("c", "topping"), up=False) == "minor"
