"""China Intelligence transmission bus — contract tests (pure, network-free).

The bus is a context-only fan-in of four surface JSON emits. It must ALWAYS return a
valid, schema-versioned, JSON-serializable briefing — even with zero surfaces built —
and NEVER raise into a build.
"""
from __future__ import annotations

import json

from engine import china_intel_bus as bus


def test_briefing_shape(monkeypatch):
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)   # no surfaces built
    b = bus.briefing(asof="2026-06-20")
    assert b["schema"] == "china_intel.briefing.v2"
    assert b["is_context_only"] is True
    assert b["asof"] == "2026-06-20"
    for k in ("news", "policy", "altdata", "radar", "analysis"):
        assert k in b
    # v2 hoisted synthesis keys always present
    for k in ("conviction", "cross_surface", "flagged_tickers", "what_changed", "salience",
              "surface_asof", "max_staleness_days"):
        assert k in b
    assert isinstance(b["digest"], str) and b["digest"]
    assert b["disclaimer"] and b["disclaimer_zh"]


def test_briefing_is_json_serializable():
    json.dumps(bus.briefing(), default=str)  # must not raise


def test_digest_text_synthesis_led():
    b = {
        "analysis": {
            "what_matters": [{"label_en": "Brokers divergence (positive)", "detail_en": "stacked"}],
            "conviction": [{"sector_en": "Brokers", "radar_sign": "positive",
                            "context_conviction": 34, "surfaces_confirming": ["radar", "news"]}],
            "what_changed": {"stance_change": {"from": "neutral", "to": "easing"}},
        },
        "news": {"band": "supportive", "sentiment_z": 0.8, "n_events_7d": 12,
                 "flagged_baskets": [{"name_en": "Brokers", "hits": 3}]},
        "policy": {"pboc_stance": "easing", "lpr_1y": 3.0, "lpr_5y": 3.5, "rrr": 6.0},
        "altdata": {"accumulate": [{"name": "中信证券", "ticker": "600030.SS"}]},
        "radar": {"divergences": [{"signal_en": "PBoC easing", "sector": "Brokers", "sign": "positive"}],
                  "ledger": {"grade": "unproven"}},
    }
    txt = bus._digest_text(b)
    assert "WHAT MATTERS MOST" in txt
    assert "CHANGED TODAY" in txt and "neutral→easing" in txt
    assert "STACKED READS" in txt and "Brokers" in txt
    assert "中信证券(600030.SS)" in txt          # names, not bare codes
    assert "unproven" in txt


def test_digest_text_empty_when_nothing_present():
    assert "no surfaces" in bus._digest_text({}).lower()
