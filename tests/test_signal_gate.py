"""Tests for the standout-grid buy gate (engine/signal_gate.py).

The gate turns an engine.signal_quality.analyze() result into a grid eligibility verdict:
a held buy-filter TAKE is the primary buy; the anticipation exception (a just-fired pending
buy, or the early advance-warning) is eligible but ALWAYS ranked below a take; everything else
(blocked buy, flat, thin history) is excluded. See research/signal_engine/GRID_GATE.md.
"""
from __future__ import annotations

from engine import signal_gate as sg


def _res(markers, *, early_now=False, state="long-bias"):
    return {"ticker": "T", "asof": "2026-06-18", "tf": "3D", "state": state,
            "above200": True, "weekly_bull": True, "markers": markers,
            "risk_flags": [], "early_markers": [], "early_now": early_now}


def test_held_take_is_eligible_take():
    v = sg.verdict(_res([{"date": "2026-06-01", "type": "buy", "quality": "take", "reason": "held"}]))
    assert v["eligible"] and v["tier"] == sg.TAKE and v["sub"] is None
    assert sg.tier_rank(v) == 0


def test_pending_buy_is_anticipation_pending():
    v = sg.verdict(_res([{"date": "2026-06-18", "type": "buy", "quality": "pending", "reason": "pending"}]))
    assert v["eligible"] and v["tier"] == sg.ANTICIPATION and v["sub"] == "pending"


def test_blocked_buy_is_excluded():
    v = sg.verdict(_res([{"date": "2026-06-10", "type": "buy", "quality": "block", "reason": "no reclaim"}]))
    assert not v["eligible"] and v["tier"] is None


def test_blocked_buy_with_early_surfaces_as_anticipation_early():
    v = sg.verdict(_res([{"date": "2026-06-10", "type": "buy", "quality": "block", "reason": "x"}],
                        early_now=True))
    assert v["eligible"] and v["tier"] == sg.ANTICIPATION and v["sub"] == "early"


def test_flat_after_sell_is_excluded():
    v = sg.verdict(_res([{"date": "2026-05-01", "type": "buy", "quality": "take", "reason": "h"},
                         {"date": "2026-06-01", "type": "sell"}]))
    assert not v["eligible"]


def test_flat_after_sell_with_early_is_anticipation():
    v = sg.verdict(_res([{"date": "2026-06-01", "type": "sell"}], early_now=True))
    assert v["eligible"] and v["tier"] == sg.ANTICIPATION and v["sub"] == "early"


def test_early_only_no_markers_is_anticipation():
    v = sg.verdict(_res([], early_now=True))
    assert v["eligible"] and v["sub"] == "early"


def test_no_signal_and_thin_history_excluded():
    assert not sg.verdict(_res([]))["eligible"]
    none = sg.verdict(None)
    assert not none["eligible"] and none["reason"] == "insufficient history"


def test_rebuy_take_is_eligible():
    v = sg.verdict(_res([{"date": "2026-06-01", "type": "rebuy", "quality": "take", "reason": "r"}]))
    assert v["eligible"] and v["tier"] == sg.TAKE


def test_tier_rank_orders_take_above_anticipation_above_excluded():
    take = sg.verdict(_res([{"date": "2026-06-01", "type": "buy", "quality": "take", "reason": "h"}]))
    pend = sg.verdict(_res([{"date": "2026-06-18", "type": "buy", "quality": "pending", "reason": "p"}]))
    early = sg.verdict(_res([], early_now=True))
    excl = sg.verdict(None)
    assert sg.tier_rank(take) < sg.tier_rank(pend) < sg.tier_rank(early) < sg.tier_rank(excl)


def test_compact_drops_result_and_keeps_display_keys():
    v = sg.verdict(_res([{"date": "2026-06-01", "type": "buy", "quality": "take", "reason": "h"}]))
    v["result"] = {"big": "payload"}
    c = sg.compact(v)
    assert "result" not in c and c["tier"] == sg.TAKE and c["eligible"] is True
    assert set(c) == set(sg._VERDICT_KEYS)
