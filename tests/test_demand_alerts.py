"""Tests for engine/demand_alerts.py — demand-variant change-detection alerts."""
from __future__ import annotations

from engine import demand_alerts as da


def _r(div, chain="ai_datacenter", yoy=69.0):
    return {"divergence": div, "chain_key": chain, "yoy_pct": yoy}


def test_seed_run_is_silent():
    reads = {"QCOM": _r("ahead_of_consensus")}
    assert da.compute_events(reads, prior=None, as_of="2026-06-20") == []
    assert da.compute_events(reads, prior={}, as_of="2026-06-20") == []


def test_new_actionable_fires_one_event():
    reads = {"QCOM": _r("ahead_of_consensus"), "NVDA": _r("aligned")}
    evs = da.compute_events(reads, prior={"PCG": "ahead_of_consensus"}, as_of="2026-06-20")
    assert len(evs) == 1
    e = evs[0]
    assert e["asset"] == "QCOM" and e["source"] == "demand"
    assert e["type"] == "demand_ahead" and e["tier"] == "context"
    assert e["id"] == "demand:QCOM:ahead_of_consensus:2026-06-20"
    assert "QCOM" in e["headline"] and e["headline_zh"]


def test_unchanged_does_not_refire():
    reads = {"QCOM": _r("ahead_of_consensus")}
    assert da.compute_events(reads, prior={"QCOM": "ahead_of_consensus"}, as_of="2026-06-20") == []


def test_flip_direction_fires():
    reads = {"MAS": _r("consensus_at_risk", chain="housing", yoy=-4.0)}
    evs = da.compute_events(reads, prior={"MAS": "ahead_of_consensus"}, as_of="2026-06-20")
    assert len(evs) == 1 and evs[0]["type"] == "demand_at_risk"
    assert "caution" in evs[0]["headline"].lower()


def test_aligned_and_signal_only_never_alert():
    reads = {"A": _r("aligned"), "B": _r("signal_only")}
    assert da.compute_events(reads, prior={"X": "ahead_of_consensus"}, as_of="2026-06-20") == []
    assert da._actionable(reads) == {}


def test_rebuild_seeds_then_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(da.config, "data_dir", lambda: tmp_path)
    # seed run — silent, persists state
    assert da.rebuild({"QCOM": _r("ahead_of_consensus")}, as_of="2026-06-19") == []
    assert da.load_state() == {"QCOM": "ahead_of_consensus"}
    # next run with a NEW actionable name → one event, appended + deduped
    fired = da.rebuild({"QCOM": _r("ahead_of_consensus"), "PANW": _r("ahead_of_consensus", chain="own_rpo", yoy=24.0)},
                       as_of="2026-06-20")
    assert [e["asset"] for e in fired] == ["PANW"]
    assert len(da.load_events()) == 1
    # idempotent re-run same day → no duplicate
    da.rebuild({"QCOM": _r("ahead_of_consensus"), "PANW": _r("ahead_of_consensus")}, as_of="2026-06-20")
    assert len(da.load_events()) == 1


def test_triage_registers_demand_source():
    from engine import alert_triage
    assert "demand" in alert_triage.SOURCES
    assert alert_triage.SOURCES["demand"]["page"] == "demand.html"
    assert "demand_ahead" in alert_triage._DEMAND_TIER
