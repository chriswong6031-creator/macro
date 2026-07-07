"""Tests for engine.signal_gate.is_buyable — the hard BUY gate behind the Top-setups strip
(us_stocks.html) and the discovery "Buy-zone" picks.

The owner's spec: a name is a recommendation ONLY if it has triggered the MACD-2D x StochRSI-3D
confluence within the fresh window (T1/T2 confirmed) or the 3D StochRSI has crossed and the 2D
MACD is about to (T3). T4 (off the 2D StochRSI) and every HOLD / topped / downtrend verdict are
NOT buyable.
"""
import json

import pytest

from engine.signal_gate import BUYABLE_TIERS, buy_signal, is_buyable
from engine.signal_gate import blend_sorted, tier_rank, TIER_FRAC
from engine import confluence_tiers


def test_buyable_tiers_are_t1_t2_t3_only():
    # T4 is deliberately excluded — it fires off the 2D StochRSI, not the StochRSI-3D the spec
    # requires; everything below it is not a confluence buy.
    assert BUYABLE_TIERS == ("T1", "T2", "T3")
    assert "T4" not in BUYABLE_TIERS


def test_is_buyable_admits_confirmed_and_anticipation_tiers():
    for tier in ("T1", "T2", "T3"):
        assert is_buyable({"eligible": True, "tier_cascade": tier}) is True


def test_is_buyable_rejects_t4_and_no_tier():
    assert is_buyable({"eligible": True, "tier_cascade": "T4"}) is False    # 2D StochRSI, not 3D
    assert is_buyable({"eligible": True, "tier_cascade": None}) is False    # early-only / no cross


def test_is_buyable_rejects_ineligible_even_with_a_tier():
    # a topped / stale verdict clears eligibility — never a fresh buy regardless of any stale tier
    assert is_buyable({"eligible": False, "tier_cascade": "T2"}) is False
    assert is_buyable({"eligible": False, "tier_cascade": "T1"}) is False


def test_is_buyable_handles_none_and_empty():
    assert is_buyable(None) is False
    assert is_buyable({}) is False


def test_buy_signal_is_slim_and_json_safe():
    # buy_signal drops the §7 marker payload (which can carry NaN) so signal_gate.json can be
    # persisted with allow_nan=False without ever crashing the build. is_buyable round-trips it.
    full = {"eligible": True, "tier_cascade": "T2", "tier_sub": "deep", "ticks": 1,
            "bars_to_cross": None, "last": {"price": float("nan")}, "result": {"big": "payload"}}
    slim = buy_signal(full)
    assert set(slim) == {"eligible", "tier_cascade", "tier_sub", "ticks", "bars_to_cross",
                         "provisional",  # provisional = the T3 partial-bucket badge (W6 #22)
                         "htf_s1", "htf_s2"}   # HTF super-tier badges (S1 display / S2 shadow)
    assert "last" not in slim and "result" not in slim          # no NaN-prone / heavy fields
    json.dumps(slim, allow_nan=False)                            # must not raise
    assert is_buyable(slim) is True                              # slim still gates correctly
    assert buy_signal(None) == {"eligible": False, "tier_cascade": None,
                                "htf_s1": False, "htf_s2": False}
    assert is_buyable(buy_signal(None)) is False


# ---------------------------------------------------------------------------
# W0.2 Stage C — near-miss annotation (Appendix A: EXACTLY-ONE-condition rule)
# ---------------------------------------------------------------------------
class TestNearMissAnnotation:
    """gate() must stamp near_miss_reason ONLY when a live take/pending lost the
    board for exactly one condition — topped AND stale together is two failures
    (a plain rejection), and eligible names carry no annotation."""

    def _series(self):
        import pandas as pd
        idx = pd.bdate_range("2024-01-01", periods=300)
        return pd.Series(range(100, 400), index=idx, dtype=float)

    def _gate(self, monkeypatch, *, topped: bool, ticks: int):
        from engine import signal_gate as sg
        from engine import confluence_tiers as ct
        res = {"markers": [{"date": "2025-01-06", "type": "buy",
                            "quality": "take"}],
               "state": "long-bias", "above200": True, "weekly_bull": True,
               "early_now": False, "asof": "2025-02-01"}
        monkeypatch.setattr(sg, "analyze", lambda t, c: res)
        monkeypatch.setattr(ct, "cascade",
                            lambda close, take_active=False, take_date=None: {
                                "not_topped": not topped, "tier": None,
                                "ticks": ticks, "sub": None,
                                "bars_to_cross": None, "provisional": False})
        return sg.gate("TEST", self._series())

    def test_topped_only_is_not_topped_veto(self, monkeypatch):
        v = self._gate(monkeypatch, topped=True, ticks=1)   # fresh but topped
        assert v["eligible"] is False
        assert v.get("near_miss_reason") == "not_topped_veto"

    def test_stale_only_is_freshness_expired(self, monkeypatch):
        from engine import confluence_tiers as ct
        v = self._gate(monkeypatch, topped=False, ticks=ct.FRESH_TICKS + 3)
        assert v["eligible"] is False
        assert v.get("near_miss_reason") == "freshness_expired"

    def test_two_failures_is_not_a_near_miss(self, monkeypatch):
        from engine import confluence_tiers as ct
        v = self._gate(monkeypatch, topped=True, ticks=ct.FRESH_TICKS + 3)
        assert v["eligible"] is False
        assert v.get("near_miss_reason") is None

    def test_eligible_take_carries_no_annotation(self, monkeypatch):
        from engine import signal_gate as sg
        from engine import confluence_tiers as ct
        res = {"markers": [{"date": "2025-01-06", "type": "buy",
                            "quality": "take"}],
               "state": "long-bias", "above200": True, "weekly_bull": True,
               "early_now": False, "asof": "2025-02-01"}
        monkeypatch.setattr(sg, "analyze", lambda t, c: res)
        monkeypatch.setattr(ct, "cascade",
                            lambda close, take_active=False, take_date=None: {
                                "not_topped": True, "tier": "T1", "ticks": 1,
                                "sub": None, "bars_to_cross": None,
                                "provisional": False})
        v = sg.gate("TEST", self._series())
        assert v["eligible"] is True
        assert v.get("near_miss_reason") is None


# ---------------------------------------------------------------------------
# Operator re-weight 2026-07-06: T2 > T1 > T3 > T4 invariant
# ---------------------------------------------------------------------------
class TestT2AboveT1OperatorReweight:
    """Pin the operator-ratified 2026-07-06 re-weight: T2 scores above T1 in WEIGHTS,
    _CASCADE_RANK, tier_rank, and blend_sorted. Eligibility / BUYABLE_TIERS unchanged."""

    def test_weights_ordering_t2_above_t1(self):
        """WEIGHTS["T2"] > WEIGHTS["T1"] > WEIGHTS["T3"] > WEIGHTS["T4"]."""
        w = confluence_tiers.WEIGHTS
        assert w["T2"] > w["T1"], f"T2 weight {w['T2']} must exceed T1 {w['T1']}"
        assert w["T1"] > w["T3"], f"T1 weight {w['T1']} must exceed T3 {w['T3']}"
        assert w["T3"] > w["T4"], f"T3 weight {w['T3']} must exceed T4 {w['T4']}"

    def test_weights_exact_values(self):
        """Pin the exact re-weight values."""
        w = confluence_tiers.WEIGHTS
        assert w["T2"] == pytest.approx(1.00)
        assert w["T1"] == pytest.approx(0.90)
        assert w["T3"] == pytest.approx(0.60)
        assert w["T4"] == pytest.approx(0.40)

    def test_tier_rank_t2_best_among_eligible_cascade(self):
        """tier_rank(T2 eligible) < tier_rank(T1 held) < tier_rank(T3) < tier_rank(T4)."""
        v_t2 = {"eligible": True, "tier_cascade": "T2", "sub": None}
        v_t1 = {"eligible": True, "tier_cascade": "T1", "sub": None}
        v_t3 = {"eligible": True, "tier_cascade": "T3", "sub": None}
        v_t4 = {"eligible": True, "tier_cascade": "T4", "sub": None}
        assert tier_rank(v_t2) < tier_rank(v_t1)
        assert tier_rank(v_t1) < tier_rank(v_t3)
        assert tier_rank(v_t3) < tier_rank(v_t4)
        assert tier_rank({"eligible": False, "tier_cascade": "T2"}) == 9   # ineligible sinks

    def test_tier_rank_t1_pending_below_t1_held(self):
        """T1 forming master (pending) ranks below both T2 and held T1."""
        v_t2 = {"eligible": True, "tier_cascade": "T2", "sub": None}
        v_t1_held = {"eligible": True, "tier_cascade": "T1", "sub": None}
        v_t1_pend = {"eligible": True, "tier_cascade": "T1", "sub": "pending"}
        assert tier_rank(v_t2) < tier_rank(v_t1_pend)
        assert tier_rank(v_t1_held) < tier_rank(v_t1_pend)

    def test_blend_sorted_orders_t2_above_t1_equal_conviction(self):
        """With identical conviction scores, blend_sorted must place T2 before T1.
        Before the re-weight T1 would have ranked first; confirm the ordering inverted."""
        items = ["T1_item", "T2_item", "T3_item", "T4_item"]
        base_scores = {"T1_item": 50.0, "T2_item": 50.0, "T3_item": 50.0, "T4_item": 50.0}
        verdicts = {
            "T1_item": {"weight": confluence_tiers.WEIGHTS["T1"], "eligible": True},
            "T2_item": {"weight": confluence_tiers.WEIGHTS["T2"], "eligible": True},
            "T3_item": {"weight": confluence_tiers.WEIGHTS["T3"], "eligible": True},
            "T4_item": {"weight": confluence_tiers.WEIGHTS["T4"], "eligible": True},
        }
        ordered = blend_sorted(items,
                               base_of=lambda x: base_scores[x],
                               verdict_of=lambda x: verdicts[x],
                               reverse=True)
        assert ordered[0] == "T2_item", f"Expected T2 first, got {ordered}"
        assert ordered[1] == "T1_item", f"Expected T1 second, got {ordered}"
        assert ordered[2] == "T3_item", f"Expected T3 third, got {ordered}"
        assert ordered[3] == "T4_item", f"Expected T4 fourth, got {ordered}"

    def test_blend_sorted_t1_still_beats_t3_t4(self):
        """T1 must still rank above T3 and T4 with equal conviction."""
        items = ["T1_item", "T3_item", "T4_item"]
        base_scores = {x: 50.0 for x in items}
        verdicts = {
            "T1_item": {"weight": confluence_tiers.WEIGHTS["T1"], "eligible": True},
            "T3_item": {"weight": confluence_tiers.WEIGHTS["T3"], "eligible": True},
            "T4_item": {"weight": confluence_tiers.WEIGHTS["T4"], "eligible": True},
        }
        ordered = blend_sorted(items,
                               base_of=lambda x: base_scores[x],
                               verdict_of=lambda x: verdicts[x],
                               reverse=True)
        assert ordered[0] == "T1_item"
        assert ordered[1] == "T3_item"
        assert ordered[2] == "T4_item"
