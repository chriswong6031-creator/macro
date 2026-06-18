"""Tests for engine/hk_signal_stack.py — the consolidated HK signal-stack read.

Pure function of the HK `latest` dict; display-only; bilingual; graceful.
"""
from __future__ import annotations

import json

from engine.hk_signal_stack import build_hk_signal_stack
from lib import config

_LATEST = {
    "quad": "Q2", "quad_name": "Reflation", "growth_score": 0.2, "inflation_score": 1.0,
    "confidence": 0.57, "liquidity_overlay": "neutral", "cycle_tag": "mid",
    "risk_state": "Neutral", "peg_state": "weak-side (outflow)",
    "conditions": {"roro": {"roro_state": "neutral"},
                   "recession": {"label": "high"}, "drawdown_risk": {"band": "high"}},
    "market_drivers": {"verdict": "clear", "primary": "china_spillover", "dir_sign": -1},
}


def test_returns_none_below_three_legs():
    assert build_hk_signal_stack({}) is None
    assert build_hk_signal_stack({"quad": "Q1"}) is None  # 1 leg only


def test_shape_and_bilingual():
    ss = build_hk_signal_stack(_LATEST)
    assert ss is not None
    assert ss["n"] == ss["n_bull"] + ss["n_flat"] + ss["n_bear"]
    assert ss["anchor_tone"] in ("up", "flat", "down")
    assert ss["final_en"] and ss["final_zh"]
    for leg in ss["legs"]:
        assert leg["label_en"] and leg["label_zh"]
        assert leg["state_en"] and leg["state_zh"]
        assert leg["tone"] in ("up", "flat", "down")
        assert leg["tier"] in ("scored", "context")


def test_has_hk_native_legs():
    """The HK headline legs — global risk + HKD peg — must appear."""
    ss = build_hk_signal_stack(_LATEST)
    keys = {leg["key"] for leg in ss["legs"]}
    assert "risk" in keys      # global-risk overlay (HK's headline)
    assert "peg" in keys       # HKD peg state
    assert "regime" in keys and "growth" in keys


def test_agreement_is_confidence():
    ss = build_hk_signal_stack(_LATEST)
    assert ss["agreement_pct"] == round(_LATEST["confidence"] * 100)


def test_contradiction_detected():
    """Reflation (constructive anchor) with a weak-side peg + high drawdown should
    surface a contradiction."""
    ss = build_hk_signal_stack(_LATEST)
    assert ss["contradiction_en"] is not None


def test_runs_on_live_latest():
    """Against the real persisted latest.json (if present), it must not raise."""
    p = config.data_dir() / "hk_regime" / "latest.json"
    if not p.exists():
        return
    ss = build_hk_signal_stack(json.loads(p.read_text()))
    assert ss is None or (ss["n"] >= 3 and ss["final_en"])
