"""China Intelligence transmission bus — contract tests (pure, network-free).

The bus is a context-only fan-in of four surface JSON emits. It must ALWAYS return a
valid, schema-versioned, JSON-serializable briefing — even with zero surfaces built —
and NEVER raise into a build.
"""
from __future__ import annotations

import json

from engine import china_intel_bus as bus


def test_briefing_shape_with_no_surfaces():
    b = bus.briefing(asof="2026-06-20")
    assert b["schema"] == "china_intel.briefing.v1"
    assert b["is_context_only"] is True
    assert b["asof"] == "2026-06-20"
    # all four surface slots exist (None when not built)
    for k in ("news", "policy", "altdata", "radar"):
        assert k in b
    assert isinstance(b["surfaces_present"], list)
    assert isinstance(b["digest"], str) and b["digest"]
    # disclaimers present in both languages
    assert b["disclaimer"] and b["disclaimer_zh"]


def test_briefing_is_json_serializable():
    json.dumps(bus.briefing(), default=str)  # must not raise


def test_digest_text_summarizes_present_surfaces():
    b = {
        "news": {"band": "supportive", "sentiment_z": 0.8, "n_events_7d": 12,
                 "top_themes": ["monetary", "policy"]},
        "policy": {"pboc_stance": "easing", "lpr_1y": 3.0, "lpr_5y": 3.5, "rrr": 6.0,
                   "last_moves": ["RRR -25bp"]},
        "altdata": {"convergence_top": ["600519.SS", "300750.SZ"]},
        "radar": {"divergences": [{"sector": "banks", "sign": "positive"}]},
    }
    txt = bus._digest_text(b)
    assert "supportive" in txt
    assert "easing" in txt.lower()
    assert "600519.SS" in txt
    assert "banks" in txt


def test_digest_text_empty_when_nothing_present():
    assert "no surfaces" in bus._digest_text({}).lower()
