"""engine.signal_stack — consolidated "Signal Stack" read (display-only).

The card re-presents already-computed fields on ``latest``; these tests pin the
direction mapping, the 3-tier contradiction detector, the scored-vs-context
tiers, the quality bands and graceful degradation — and assert it stays a *pure
read* (invents no signal, never mutates input) by running it on the real stored
state.
"""
from __future__ import annotations

import json

from engine.signal_stack import build_signal_stack
from lib import config


def _latest(**over):
    base = {
        "quad": "Q1", "quad_name": "Goldilocks",
        "growth_score": 0.5, "confidence": 0.44,
        "liquidity_overlay": "neutral",
        "transition_state": "STABLE",
        "transition_flags": {"flag_gex": False, "flag_breadth_price": False},
        "confirming": ["growth_breadth_direction"],
        "contradicting": [],
        "conditions": {
            "financial_conditions": {"state": "loose", "trend": "loosening"},
            "risk_appetite": {"vix_term_state": "contango (calm)",
                              "roro_state": "risk-on",
                              "news_sentiment_state": "optimistic"},
        },
    }
    base.update(over)
    return base


def _by_key(stack):
    return {leg["key"]: leg for leg in stack["legs"]}


def test_builds_seven_legs_with_correct_tiers():
    s = build_signal_stack(_latest())
    legs = _by_key(s)
    assert set(legs) == {"regime", "liquidity", "credit", "volatility",
                         "breadth", "options", "sentiment"}
    assert {k: legs[k]["tier"] for k in ("regime", "liquidity", "credit", "breadth")} \
        == {"regime": "scored", "liquidity": "scored", "credit": "scored", "breadth": "scored"}
    assert {legs[k]["tier"] for k in ("volatility", "options", "sentiment")} == {"context"}


def test_direction_mapping_bullish_state():
    legs = _by_key(build_signal_stack(_latest()))
    assert legs["regime"]["dir"] == 1 and legs["regime"]["tone"] == "up"
    assert legs["credit"]["dir"] == 1        # loose
    assert legs["volatility"]["dir"] == 1    # contango / calm
    assert legs["breadth"]["dir"] == 1       # confirming
    assert legs["sentiment"]["dir"] == 1     # risk-on
    assert legs["liquidity"]["dir"] == 0     # neutral
    assert legs["options"]["dir"] == 0       # not fragile


def test_direction_mapping_bearish_state():
    s = build_signal_stack(_latest(
        quad="Q3", quad_name="Stagflation", growth_score=-0.4,
        liquidity_overlay="contracting",
        transition_flags={"flag_gex": True, "flag_breadth_price": True},
        confirming=[], contradicting=["growth_breadth_direction"],
        conditions={
            "financial_conditions": {"state": "tight", "trend": "tightening"},
            "risk_appetite": {"vix_term_state": "backwardation (stress)",
                              "roro_state": "risk-off",
                              "news_sentiment_state": "pessimistic"},
        }))
    legs = _by_key(s)
    assert all(legs[k]["dir"] == -1 for k in
               ("regime", "credit", "volatility", "breadth", "options", "sentiment"))
    assert legs["liquidity"]["dir"] == -1    # contracting
    assert s["final_en"].startswith("bearish")
    assert s["anchor_tone"] == "down"


def test_hard_stack_dissent_is_the_named_contradiction():
    # bullish regime but breadth lagging -> breadth is THE contradiction, and fragile
    s = build_signal_stack(_latest(confirming=[], contradicting=["growth_breadth_direction"]))
    assert s["anchor"] == 1 and s["n_dissent"] >= 1
    assert "breadth" in s["contradiction_en"].lower()
    assert "regime bullish" in s["contradiction_en"]
    assert "but fragile" in s["final_en"]


def test_internal_contradiction_fallback_when_stack_agrees():
    # every stack leg agrees with the regime; an internal regime component dissents
    s = build_signal_stack(_latest(contradicting=["growth_cyclical_defensive"]))
    assert s["n_dissent"] == 0
    assert "cyclicals vs defensives" in s["contradiction_en"]
    assert "Goldilocks" in s["contradiction_en"]


def test_news_vs_positioning_fallback():
    s = build_signal_stack(_latest(
        contradicting=[],
        conditions={
            "financial_conditions": {"state": "loose", "trend": "loosening"},
            "risk_appetite": {"vix_term_state": "contango (calm)",
                              "roro_state": "risk-on",
                              "news_sentiment_state": "pessimistic"},
        }))
    assert s["contradiction_en"] == "positioning risk-on but news tone pessimistic"


def test_broad_agreement_has_no_contradiction():
    s = build_signal_stack(_latest())  # all bullish/neutral, news optimistic
    assert s["contradiction_en"] is None
    assert s["n_bull"] == 5 and s["n_flat"] == 2 and s["n_bear"] == 0


def test_quality_bands_track_confidence():
    assert build_signal_stack(_latest(confidence=0.20))["quality_en"].startswith("mixed")
    assert "usable, not high" in build_signal_stack(_latest(confidence=0.40))["quality_en"]
    assert build_signal_stack(_latest(confidence=0.55))["quality_en"].startswith("solid")
    assert build_signal_stack(_latest(confidence=0.44))["agreement_pct"] == 44


def test_graceful_degradation():
    assert build_signal_stack(None) is None
    assert build_signal_stack({}) is None
    # too little to be meaningful (<3 legs) -> None, never a half-empty card
    assert build_signal_stack({"quad": "Q1", "quad_name": "Goldilocks",
                               "growth_score": 0.1}) is None


def test_every_leg_is_bilingual():
    s = build_signal_stack(_latest())
    for leg in s["legs"]:
        assert leg["label_en"] and leg["label_zh"]
        assert leg["state_en"] and leg["state_zh"]
    assert s["final_zh"]


def test_pure_read_of_real_stored_state():
    """It must build from the actual stored latest.json and never mutate it."""
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():  # data-light checkout — skip rather than fail
        return
    latest = json.loads(p.read_text())
    before = json.dumps(latest, sort_keys=True)
    s = build_signal_stack(latest)
    assert s is not None and len(s["legs"]) >= 5
    assert s["agreement_pct"] is not None
    assert {leg["tier"] for leg in s["legs"]} <= {"scored", "context"}
    assert json.dumps(latest, sort_keys=True) == before  # no mutation
