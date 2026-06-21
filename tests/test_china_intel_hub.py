"""China Intelligence transmission — full four-surface fan-in + master_brain wiring."""
from __future__ import annotations

from engine import china_intel_bus as bus
from engine import master_brain as mb


_FIXTURES = {
    "chinanews/sentiment.json": {"z": 0.6, "band": "supportive", "n_events_7d": 40},
    "chinanews/feed.json": {"top_themes": ["monetary", "policy"],
                            "scheduled_ahead": [{"type": "LPR", "date": "2026-06-22"}]},
    "data/china_policy/latest.json": {"stance": "easing", "lpr_1y": 3.0, "lpr_5y": 3.5,
                                      "rrr": 9.0, "fx_reserves": 34000.0,
                                      "last_moves": ["RRR -25bp"], "predictions": ["X"]},
    "chinaaltdata/mastermind.json": {"n_triple": 12, "convergence_top": ["600519.SS"],
                                     "convergence_bottom": ["000001.SZ"], "crowding_flags": []},
    "chinaradar/radar.json": {"divergences": [{"sector": "banks", "sign": "positive"}]},
}


def test_briefing_fans_in_all_four_surfaces(monkeypatch):
    monkeypatch.setattr(bus, "_read_json", lambda rel: _FIXTURES.get(rel))
    b = bus.briefing(asof="2026-06-20")
    assert set(b["surfaces_present"]) == {"news", "policy", "altdata", "radar"}
    assert b["news"]["band"] == "supportive"
    assert b["policy"]["pboc_stance"] == "easing"
    assert b["altdata"]["n_triple"] == 12
    assert b["radar"]["divergences"][0]["sector"] == "banks"
    # digest mentions every surface
    d = b["digest"].lower()
    assert "supportive" in d and "easing" in d and "600519" in d and "banks" in d


def test_briefing_partial_surfaces(monkeypatch):
    only_news = {"chinanews/sentiment.json": _FIXTURES["chinanews/sentiment.json"],
                 "chinanews/feed.json": _FIXTURES["chinanews/feed.json"]}
    monkeypatch.setattr(bus, "_read_json", lambda rel: only_news.get(rel))
    b = bus.briefing()
    assert b["surfaces_present"] == ["news"]
    assert b["policy"] is None and b["altdata"] is None and b["radar"] is None


def test_master_brain_china_lens_includes_intel():
    # reads live disk; must never raise and, when surfaces are built, expose china_intel
    st = mb.gather_china_state()
    assert isinstance(st, dict)
    if "china_intel" in st:
        assert set(st["china_intel"]).issubset({"news", "policy", "altdata", "radar"})
