"""Narrative-Rotation alert engine (engine.allocation_alerts) — run-over-run change detection.

Verify the seed run is silent, book entries/exits + leadership rotation + trend-gate flips +
risk-dial/crash events fire correctly, and ids are stable + bilingual. Pure logic; no network.
"""
from __future__ import annotations

from engine import allocation_alerts as aa


def _data(held, leader, cash, eligible, crash=False, as_of="2026-06-19"):
    weights = [{"id": h, "name": h.upper(), "name_zh": h} for h in held]
    ranks = [{"id": e, "name": e.upper(), "eligible": True} for e in eligible]
    for h in held:
        if h not in eligible:
            ranks.append({"id": h, "name": h.upper(), "eligible": True})
    return {"as_of": as_of, "allocation": {"weights": weights, "cash": cash,
            "n_held": len(held), "crash_overlay": {"active": crash}},
            "rotation": {"leader": {"id": leader}}, "ranks": ranks}


def test_seed_run_silent():
    d = _data(["ai_infra", "nuclear"], "ai_infra", 0.4, ["ai_infra", "nuclear", "travel"])
    assert aa.compute_events(d, None, "us") == []
    assert aa.compute_events(d, {}, "us") == []


def test_book_entry_exit_and_leadership():
    prior = aa._snapshot(_data(["ai_infra", "nuclear"], "ai_infra", 0.4, ["ai_infra", "nuclear", "travel"]))
    cur = _data(["travel", "nuclear"], "travel", 0.4, ["travel", "nuclear", "ai_infra"])
    evs = aa.compute_events(cur, prior, "us")
    types = {e["type"] for e in evs}
    assert "entered_book" in types and "left_book" in types and "leadership_rotation" in types
    entered = [e for e in evs if e["type"] == "entered_book"][0]
    assert entered["asset"] == "travel" and entered["headline_zh"] and entered["headline_zh"] != entered["headline"]
    assert entered["id"].startswith("rotation:us:travel:entered_book:2026-06-19")


def test_trend_gate_flips():
    prior = aa._snapshot(_data(["ai_infra"], "ai_infra", 0.5, ["ai_infra", "nuclear"]))
    cur = _data(["ai_infra"], "ai_infra", 0.5, ["ai_infra", "travel"])  # nuclear lost gate, travel gained
    evs = aa.compute_events(cur, prior, "us")
    g = {(e["type"], e["asset"]) for e in evs}
    assert ("gate_lost", "nuclear") in g and ("gate_gained", "travel") in g


def test_risk_dial_and_crash():
    prior = aa._snapshot(_data(["ai_infra"], "ai_infra", 0.2, ["ai_infra"]))
    cur = _data(["ai_infra"], "ai_infra", 0.6, ["ai_infra"], crash=True)  # cash +40pp + crash on
    evs = aa.compute_events(cur, prior, "us")
    types = {e["type"] for e in evs}
    assert "risk_shift" in types and "crash_derisk_on" in types


def test_roundtrip_seed_then_change(tmp_path, monkeypatch):
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    d1 = _data(["ai_infra", "nuclear"], "ai_infra", 0.4, ["ai_infra", "nuclear"], as_of="2026-06-19")
    assert aa.rebuild(d1, "us") == []                      # seed: silent
    assert aa.load_events("us") == []
    d2 = _data(["travel", "nuclear"], "travel", 0.4, ["travel", "nuclear"], as_of="2026-06-20")
    fired = aa.rebuild(d2, "us")
    assert any(e["type"] == "entered_book" for e in fired)
    n = len(aa.load_events("us"))
    assert aa.rebuild(d2, "us") == [] and len(aa.load_events("us")) == n   # idempotent
