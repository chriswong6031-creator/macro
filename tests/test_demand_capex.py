"""engine.demand_capex — T2 customer-capex demand leg. Verifies the hyperscaler-capex pool
is projected onto the AI-beneficiary themes with the right band/strength, that non-AI themes
are excluded, and that it degrades to None without cached statements. DISPLAY-ONLY adapter.
"""
from __future__ import annotations

from engine import demand_capex as dx
from engine import demand_chain as dc

FAKE_SIG = {"ai_datacenter": {"yoy_pct": 69.0, "yoy_prev_pct": 50.4, "trend": "accelerating",
                              "total_latest_bn": 378.7, "fy_latest": 2025,
                              "spenders": ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]}}


def _patch(monkeypatch, sig=None, themes=None):
    monkeypatch.setattr(dx, "_statements", lambda: object())     # non-None sentinel
    monkeypatch.setattr(dc, "compute_signals", lambda df: sig if sig is not None else FAKE_SIG)
    monkeypatch.setattr(dx.config, "load", lambda: {"themes": themes or {
        "memory_storage": {"name": "Memory"}, "ai_semiconductors": {"name": "AI Semis"},
        "semicap_equipment": {"name": "WFE"}, "cybersecurity": {"name": "Cyber"}}})


def test_projects_capex_onto_ai_themes(monkeypatch):
    _patch(monkeypatch)
    out = dx.compute_demand_capex()
    assert out["pool_yoy"] == 69.0 and out["pool_trend"] == "accelerating"
    t = out["themes"]["memory_storage"]
    assert t["demand_band"] == "ACCELERATING"
    assert t["strength"] == "direct"          # HBM is a direct AI-capex beneficiary
    assert t["capex_yoy"] == 69.0
    assert out["themes"]["semicap_equipment"]["strength"] == "lagged"
    # a non-AI-capex theme is excluded (honest: not capex-linked)
    assert "cybersecurity" not in out["themes"]


def test_cooling_band(monkeypatch):
    sig = {"ai_datacenter": dict(FAKE_SIG["ai_datacenter"], trend="peaking")}
    _patch(monkeypatch, sig=sig)
    out = dx.compute_demand_capex()
    assert out["themes"]["memory_storage"]["demand_band"] == "COOLING"


def test_none_without_statements(monkeypatch):
    monkeypatch.setattr(dx, "_statements", lambda: None)
    assert dx.compute_demand_capex() is None


def test_none_when_signal_empty(monkeypatch):
    _patch(monkeypatch, sig={})               # demand_chain found no ai_datacenter signal
    assert dx.compute_demand_capex() is None
