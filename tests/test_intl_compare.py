"""International comparison-layer tests (engine/intl_compare.py) — pure functions
over synthetic per-country records: rankings, regime heatmap, global summary."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_compare as ic  # noqa: E402


def _records() -> list[dict]:
    return [
        {"cc": "JP", "flag": "🇯🇵", "name": "Japan", "region": "Asia",
         "quad": "Q1", "quad_name": "Goldilocks", "growth_score": 0.7,
         "inflation_score": -0.5, "confidence": 0.6, "recession_score": 5,
         "macro": {"real_yield": 0.5, "yield_10y": 2.6, "cpi_yoy": 2.0, "fx_strength_3m": -0.7},
         "equity": {"drawdown_risk": 16}, "data_limited": False},
        {"cc": "GB", "flag": "🇬🇧", "name": "United Kingdom", "region": "Europe",
         "quad": "Q2", "quad_name": "Reflation", "growth_score": 0.6,
         "inflation_score": 0.3, "confidence": 0.5, "recession_score": 30,
         "macro": {"real_yield": 1.1, "yield_10y": 4.9, "cpi_yoy": 3.4, "fx_strength_3m": 0.8},
         "equity": {"drawdown_risk": 8}, "data_limited": False},
        {"cc": "TW", "flag": "🇹🇼", "name": "Taiwan", "region": "Asia",
         "quad": "Q1", "quad_name": "Goldilocks", "growth_score": 1.0,
         "inflation_score": -1.0, "confidence": 0.5, "recession_score": 7,
         "macro": {"real_yield": None, "yield_10y": None, "cpi_yoy": None, "fx_strength_3m": 0.9},
         "equity": {"drawdown_risk": 19}, "data_limited": True},
    ]


def test_rankings_sorted_and_skip_none():
    rk = ic.rankings(_records())
    assert "recession_score" in rk
    # risk_high metric -> highest first
    rows = rk["recession_score"]["rows"]
    assert rows[0]["cc"] == "GB" and rows[-1]["cc"] == "JP"
    # yield_10y ranking drops the None (Taiwan)
    yrows = rk["yield_10y"]["rows"]
    assert all(r["value"] is not None for r in yrows)
    assert not any(r["cc"] == "TW" for r in yrows)


def test_heatmap_shape():
    hm = ic.regime_heatmap(_records())
    assert len(hm) == 3
    assert {h["cc"] for h in hm} == {"JP", "GB", "TW"}
    assert all("growth" in h and "inflation" in h for h in hm)


def test_global_summary():
    s = ic.global_summary(_records())
    assert s["n"] == 3
    assert s["dominant_quad"] == "Goldilocks"      # 2 of 3
    assert s["recession_watch"] == 0               # none >= 45
    assert s["avg_recession"] is not None
