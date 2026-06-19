"""Tests for engine.policy_summary — the policy-layer accountability scorecard."""
from __future__ import annotations

from engine import policy_summary as ps


def test_summarize_full():
    out = ps.summarize(
        {"total": 29, "open": 26, "hit": 2, "miss": 1, "hit_rate": 0.67},
        {"themes": {"Defense": {"verdict": "lagging", "avg_rel": -0.08},
                    "Nuclear": {"verdict": "working", "avg_rel": 0.05},
                    "Semis": {"verdict": "lagging", "avg_rel": -0.03},
                    "Gold": {"verdict": "na", "avg_rel": None}}},
        {"current": "hawkish", "days_in_stance": 197, "changed_recently": True},
        {"overdue_predictions": 1, "staleness": {"age_days": 3, "stale": False}})
    assert out["predictions"] == {"total": 29, "open": 26, "resolved": 3, "hit_rate": 0.67, "overdue": 1}
    assert out["rotation"]["working"] == 1 and out["rotation"]["lagging"] == 2 and out["rotation"]["na"] == 1
    assert out["rotation"]["sharpest_divergence"] == {"theme": "Defense", "rel": -0.08}   # worst lagging
    assert out["stance"]["current"] == "hawkish" and out["stance"]["days"] == 197
    assert out["intel"] == {"age_days": 3, "stale": False}


def test_no_divergence_when_nothing_lagging():
    out = ps.summarize({"total": 1}, {"themes": {"A": {"verdict": "working", "avg_rel": 0.04}}}, None, None)
    assert out["rotation"]["sharpest_divergence"] is None
    assert out["stance"] is None


def test_defensive_on_empty():
    out = ps.summarize(None, None, None, None)
    assert out["predictions"]["total"] == 0 and out["rotation"]["sharpest_divergence"] is None
    assert out["stance"] is None and out["intel"]["stale"] is False
