"""China Intelligence transmission v2 — full five-surface fan-in + master_brain wiring."""
from __future__ import annotations

from engine import china_intel_bus as bus
from engine import master_brain as mb


_FIXTURES = {
    "chinanews/sentiment.json": {"z": 0.6, "band": "supportive", "label_en": "Supportive",
                                 "label_zh": "偏积极", "n_events_7d": 40},
    "chinanews/feed.json": {"asof": "2026-06-20", "top_themes": ["monetary", "policy"],
                            "theme_label": {"monetary": ["Monetary", "货币"], "policy": ["Policy", "政策"]},
                            "by_basket": {"cn_brokers": 3}, "basket_label": {"cn_brokers": ["Brokers", "券商"]},
                            "items": [{"title": "央行降准", "theme_en": "Monetary", "theme_zh": "货币",
                                       "tier": 1, "baskets": ["cn_brokers"], "tickers": ["600030.SS"],
                                       "importance_en": "High", "importance_zh": "重磅",
                                       "surprise": True, "scheduled_ref": "LPR@2026-06-22", "url": "u"}],
                            "scheduled_ahead": [{"type": "LPR", "date": "2026-06-22"}]},
    "data/china_policy/latest.json": {"stance": "easing", "stance_en": "Easing", "stance_zh": "宽松",
                                      "lpr_1y": 3.0, "lpr_5y": 3.5, "rrr": 9.0, "fr007": 1.8,
                                      "fx_reserves": 34000.0, "last_moves": ["RRR cut 25bp"],
                                      "predictions": ["X"], "asof": "2026-05-20", "stale": False},
    "chinaaltdata/mastermind.json": {"n_triple": 12, "n_universe": 1355, "asof": "2026-06-20",
                                     "convergence_top": [{"ticker": "600519.SS", "name": "贵州茅台",
                                                          "convergence": 0.9, "conviction100": 90,
                                                          "reasons": ["value", "margin"], "flags": [], "side": "accumulate"}],
                                     "convergence_bottom": [{"ticker": "000001.SZ", "name": "平安银行",
                                                             "convergence": -0.8, "side": "distribute"}],
                                     "crowding_flags": []},
    "chinaradar/radar.json": {"asof": "2026-06-20",
                              "divergences": [{"signal_en": "PBoC easing", "signal_zh": "央行宽松",
                                               "sector": "Brokers", "sign": "positive", "conviction100": 30,
                                               "reliability": {"basis": "unproven", "n_resolved": 0}}]},
    "chinaradar/ledger.json": {"n_total": 6, "n_resolved": 0, "hit_rate": None},
    "china_intel_analysis/analysis.json": {
        "conviction": [{"sector_en": "Brokers", "radar_sign": "positive", "context_conviction": 34,
                        "n_surfaces": 3, "surfaces_confirming": ["radar", "news", "policy"]}],
        "chains": [{"name": "EASING_REFLATION", "band": "forming", "k": 2, "n": 5}],
        "cross_refs": [{"signal_key": "pboc_easing", "kind": "conflict"}],
        "what_matters": [{"rank": 1, "label_en": "Brokers divergence", "detail_en": "stacked", "salience": 0.34}],
        "what_changed": {"stance_change": {"from": "neutral", "to": "easing"}},
        "flagged_tickers": [{"ticker": "300059.SZ", "name": "东方财富", "side": "long-context"}]},
}


def test_briefing_v2_fans_in_all_five_surfaces(monkeypatch):
    monkeypatch.setattr(bus, "_read_json", lambda rel: _FIXTURES.get(rel))
    b = bus.briefing(asof="2026-06-20")
    assert b["schema"] == "china_intel.briefing.v6"
    assert set(b["surfaces_present"]) == {"news", "policy", "altdata", "radar", "analysis"}
    # enriched blocks
    assert b["news"]["band_label_en"] == "Supportive"               # zh-leak fix carried
    assert b["news"]["flagged_baskets"][0]["name_en"] == "Brokers"
    assert b["news"]["top_headlines"][0]["tickers"] == ["600030.SS"]
    assert b["policy"]["stance_label_en"] == "Easing"
    assert b["altdata"]["accumulate"][0]["name"] == "贵州茅台"
    assert b["radar"]["ledger"]["grade"] == "unproven"
    # hoisted synthesis
    assert b["conviction"][0]["sector_en"] == "Brokers"
    assert b["flagged_tickers"][0]["ticker"] == "300059.SZ"
    assert b["what_changed"]["stance_change"]["to"] == "easing"
    # digest is synthesis-led with names
    assert "WHAT MATTERS MOST" in b["digest"]
    assert "贵州茅台(600519.SS)" in b["digest"]


def test_briefing_partial_surfaces(monkeypatch):
    only_news = {"chinanews/sentiment.json": _FIXTURES["chinanews/sentiment.json"],
                 "chinanews/feed.json": _FIXTURES["chinanews/feed.json"]}
    monkeypatch.setattr(bus, "_read_json", lambda rel: only_news.get(rel))
    b = bus.briefing()
    assert b["surfaces_present"] == ["news"]
    assert b["policy"] is None and b["analysis"] is None


def test_master_brain_china_lens_includes_synthesis():
    st = mb.gather_china_state()
    assert isinstance(st, dict)
    if "china_intel" in st:
        ci = st["china_intel"]
        # the widened whitelist must propagate the synthesis, not just raw surfaces
        assert "digest" in ci
        assert ci.get("is_context_only") is True       # contract marker travels with the synthesis
        assert set(ci).issubset({"news", "policy", "altdata", "radar", "analysis",
                                 "conviction", "cross_surface", "flagged_tickers",
                                 "what_changed", "salience", "digest", "regime", "discovery",
                                 "is_context_only", "disclaimer", "disclaimer_zh"})
