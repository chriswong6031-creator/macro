"""Perception-contract tests (2026-07-02 semis-breakdown incident fixes).

Covers: the transition de-escalation ratchet (H1), the liquidity-quality
classifier (H3), the quad_vector published contract (H2), and the radar <->
de-escalation-panel reconciliation (incident signals.md §4 item 4).
See research/PERCEPTION_CONTRACTS.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.quad_vector import build as build_quad_vector
from engine.regime import liquidity_quality
from engine.risk_radar import _deescalation
from engine.transition import contradiction_floor, state_machine_detail

FLAG_COLS = ["flag_breadth_price", "flag_credit_equity", "flag_ratio_inflection",
             "flag_inflation_basket", "flag_confidence_decay", "flag_gex",
             "flag_rotation_persistence"]


def _mk(n_flags_seq, rot_seq=None, quad="Q1", g_score=0.4,
        c_cyc=None, c_wei=None):
    """Synthetic (flags, regime) pair driving the state machine directly."""
    idx = pd.bdate_range("2026-01-05", periods=len(n_flags_seq))
    flags = pd.DataFrame(False, index=idx, columns=FLAG_COLS)
    rot = list(rot_seq or [False] * len(idx))
    for i, (n, r) in enumerate(zip(n_flags_seq, rot)):
        cols = [c for c in FLAG_COLS if c != "flag_rotation_persistence"][:n]
        flags.iloc[i, [flags.columns.get_loc(c) for c in cols]] = True
        if r:
            flags.iloc[i, flags.columns.get_loc("flag_rotation_persistence")] = True
    flags["n_flags"] = flags[FLAG_COLS].sum(axis=1)
    regime = pd.DataFrame({
        "quad": quad, "pending_days": 0, "growth_score": g_score,
        "c_growth_cyclical_defensive": c_cyc if c_cyc is not None else 0.0,
        "c_growth_wei_trend": c_wei if c_wei is not None else 0.0,
    }, index=idx)
    return flags, regime


class TestRatchet:
    def test_escalation_instant(self):
        flags, regime = _mk([0, 0, 3])
        d = state_machine_detail(flags, regime)
        assert d["transition_state"].iloc[-1] == "TRANSITIONING"
        assert not d["transition_ratcheted"].iloc[-1]

    def test_weakening_holds_through_flag_rolloff(self):
        # the incident regression: WEAKENING then all flags roll off — raw resets
        # to STABLE next session, the ratchet must hold WEAKENING for the dwell
        flags, regime = _mk([2, 2, 0, 0, 0, 0])
        d = state_machine_detail(flags, regime)
        assert d["transition_state_raw"].iloc[2] == "STABLE"
        assert d["transition_state"].iloc[2] == "WEAKENING"
        assert d["transition_ratcheted"].iloc[2]
        assert d["transition_dwell_remaining"].iloc[2] == 4  # 5-day dwell, 1 clean done

    def test_deescalates_after_clear_dwell(self):
        flags, regime = _mk([2, 2] + [0] * 7)
        d = state_machine_detail(flags, regime)
        # 5 clean sessions after the last dirty one -> back to STABLE
        assert d["transition_state"].iloc[2 + 4] == "STABLE"
        assert (d["transition_state"].iloc[-1]) == "STABLE"

    def test_rearm_resets_countdown(self):
        # 3 clean sessions, flags re-fire, then clean again: the early clean
        # sessions must NOT count — WEAKENING persists past where a naive
        # cumulative count would have cleared
        flags, regime = _mk([2, 0, 0, 0, 2, 0, 0, 0, 0])
        d = state_machine_detail(flags, regime)
        assert d["transition_state"].iloc[7] == "WEAKENING"   # only 3 clean since re-fire
        assert d["transition_state"].iloc[8] == "WEAKENING"   # 4 clean — still short

    def test_rotation_flag_gates_deescalation(self):
        # n_flags drops below the bar but the slow rotation flag stays on:
        # sessions are not clean -> no step-down until max_dwell auto-release
        seq = [2, 2] + [0] * 16
        rot = [False, False] + [True] * 16
        flags, regime = _mk(seq, rot_seq=rot)
        d = state_machine_detail(flags, regime)
        assert (d["transition_state"].iloc[2:16] == "WEAKENING").all()
        # max_dwell (15 held sessions) force-releases eventually
        assert d["transition_state"].iloc[-1] == "STABLE"

    def test_contradiction_floor_forces_weakening(self):
        flags, regime = _mk([0] * 6, c_cyc=-1.0, c_wei=-1.0, g_score=0.4)
        assert contradiction_floor(regime).all()
        d = state_machine_detail(flags, regime)
        assert (d["transition_state"] == "WEAKENING").all()
        assert (d["transition_state_raw"] == "STABLE").all()

    def test_new_regime_passthrough_resets_ladder(self):
        flags, regime = _mk([2, 2, 0, 0])
        regime["quad"] = ["Q1", "Q1", "Q3", "Q3"]
        d = state_machine_detail(flags, regime)
        assert d["transition_state"].iloc[2] == "NEW_REGIME"


def _liq_frame(walcl_step=0.0, tga_step=0.0, rrp_level=500.0, n=340):
    idx = pd.bdate_range("2025-01-02", periods=n)
    walcl = pd.Series(6600.0, index=idx) + walcl_step * np.arange(n)
    tga = pd.Series(700.0, index=idx) + tga_step * np.arange(n)
    rrp = pd.Series(float(rrp_level), index=idx)
    f = pd.DataFrame({
        "walcl_bn": walcl, "rrp_bn": rrp, "tga_bn": tga,
        "hy_oas": 3.0, "nfci": -0.5,
    }, index=idx)
    f["net_liquidity_bn"] = f["walcl_bn"] - f["rrp_bn"] - f["tga_bn"]
    return f


class TestLiquidityQuality:
    def test_mechanical_expansion_is_stress(self):
        # net-liq rising purely via TGA drawdown against an empty RRP — the
        # 2026-07-01 read. Must NOT be labelled benign.
        f = _liq_frame(walcl_step=0.0, tga_step=-4.0, rrp_level=6.4)
        q = liquidity_quality(f, overlay="expanding")
        assert q["label"] == "stress-expansion"
        assert q["rrp_exhausted"] and q["composition"]["mechanical"]
        assert q["schema_version"] == 1 and q["asof"]

    def test_fed_driven_expansion_is_benign(self):
        f = _liq_frame(walcl_step=5.0, tga_step=0.0, rrp_level=500.0)
        q = liquidity_quality(f, overlay="expanding")
        assert q["label"] == "benign-expansion"
        assert not q["composition"]["mechanical"]

    def test_neutral_hollow(self):
        f = _liq_frame(walcl_step=0.0, tga_step=-4.0, rrp_level=6.4)
        q = liquidity_quality(f, overlay="neutral")
        assert q["label"] == "neutral-hollow"

    def test_contracting_and_missing(self):
        f = _liq_frame()
        assert liquidity_quality(f, overlay="contracting")["label"] == "contracting"
        assert liquidity_quality(pd.DataFrame({"x": [1.0]})) is None


def _full_row_frame():
    idx = pd.bdate_range("2026-06-01", periods=5)
    return pd.DataFrame({
        "growth_agreement": 0.75, "inflation_agreement": 0.75,
        "c_growth_copper_gold": 1.0, "c_growth_cyclical_defensive": -1.0,
        "c_growth_payrolls_trend": 1.0, "c_inflation_oil_trend": -1.0,
    }, index=idx)


class TestQuadVector:
    def test_causal_source_shape(self):
        hist = [{"date": "d", "Q1": 0.8, "Q2": 0.1, "Q3": 0.05, "Q4": 0.05},
                {"date": "d", "Q1": 0.7, "Q2": 0.1, "Q3": 0.05, "Q4": 0.15}]
        latest = {"quad": "Q1", "date": "2026-06-05",
                  "regime_one": {"asof": "2026-06-05", "forward": {"p_quad": {
                      "value": {"Q1": 0.7, "Q2": 0.1, "Q3": 0.05, "Q4": 0.15},
                      "history_filtered": hist}}}}
        full = _full_row_frame()
        qv = build_quad_vector(latest, full, full.index[-1])
        assert qv["schema_version"] == 1
        assert abs(sum(qv["p"].values()) - 1.0) < 1e-6
        assert qv["source"].startswith("regime_one")
        assert not qv["degraded"]
        assert qv["hard_label"] == "Q1" and qv["hard_label_agrees"]
        assert qv["transition_momentum"]["gaining"] == "Q4"
        assert qv["transition_momentum"]["losing"] == "Q1"
        growth_legs = {d["leg"] for d in qv["drivers"]["growth"]}
        assert {"copper_gold", "cyclical_defensive", "payrolls_trend"} <= growth_legs
        slow = [d for d in qv["drivers"]["growth"] if d["leg"] == "payrolls_trend"]
        assert slow and slow[0].get("slow") is True
        assert 0.0 <= qv["confidence"] <= 1.0

    def test_smoothed_fallback_degrades(self):
        latest = {"quad": "Q2", "date": "2026-06-05",
                  "regime_hmm": {"asof": "2026-06-05",
                                 "regime_probs": {"Q1": 0.2, "Q2": 0.6, "Q3": 0.1, "Q4": 0.1}}}
        full = _full_row_frame()
        qv = build_quad_vector(latest, full, full.index[-1])
        assert qv["degraded"] and "fallback" in qv["degrade_reason"]
        assert abs(sum(qv["p"].values()) - 1.0) < 1e-6

    def test_uniform_when_no_producer(self):
        qv = build_quad_vector({"quad": "Q1", "date": "2026-06-05"},
                               _full_row_frame(), _full_row_frame().index[-1])
        assert qv["degraded"] and qv["p"] == {q: 0.25 for q in ("Q1", "Q2", "Q3", "Q4")}


class TestDeescalation:
    def _subs(self, dominant_rising: bool):
        idx = pd.bdate_range("2026-05-01", periods=40)
        growth = np.linspace(40, 90, 40) if dominant_rising else np.linspace(90, 60, 40)
        vol = np.concatenate([np.linspace(50, 88, 20), np.linspace(88, 40, 20)])
        return pd.DataFrame({"growth": growth, "vol": vol}, index=idx)

    def test_suppressed_when_dominant_riskoff_and_odds_rising(self):
        traj = {"phase": "receding", "odds_delta": +0.03, "odds_now": 0.19}
        d = _deescalation("growth", self._subs(True), traj, {"h21": 0.19})
        assert d["eligible"] is False
        assert d["drawdown_prob_trend"] == "rising"
        assert d["receding_scare"] == "vol"   # what IS fading, named honestly

    def test_eligible_when_dominant_receding(self):
        traj = {"phase": "receding", "odds_delta": -0.03, "odds_now": 0.10}
        d = _deescalation("growth", self._subs(False), traj, {"h21": 0.10})
        assert d["eligible"] is True

    def test_recovery_panel_gates_on_radar_verdict(self):
        from engine.risk_radar_recovery import assess
        traj = {"phase": "receding", "reached_risk": True, "off_peak": 8.0,
                "velocity": -3.0, "peak_days_ago": 4, "intensity": 70.0,
                "peak": 90.8, "odds_now": 0.19, "odds_peak": 0.16,
                "odds_delta": 0.03, "spark": [], "spark_pts": "",
                "spark_peak": None, "spark_last": None, "spark_w": 96, "spark_h": 26}
        rr = {"trajectory": traj, "dominant_scare": "growth",
              "dominant_label_en": "Growth scare / defensive rotation",
              "deescalation": {"eligible": False, "receding_scare": "vol",
                               "reason": "dominant scare = growth; h21 drawdown_prob RISING",
                               "drawdown_prob_trend": "rising", "drawdown_prob_h21": 0.19}}
        rv = assess({"risk_radar": rr, "liquidity_overlay": "neutral"})
        assert rv["present"] and rv["suppressed"]
        assert rv["receding"] is False and rv["turn_confirmed"] is False
        assert "escalating" in rv["headline_en"]
        # and with an eligible verdict the green path is intact
        rr2 = dict(rr)
        rr2["deescalation"] = {**rr["deescalation"], "eligible": True}
        rv2 = assess({"risk_radar": rr2, "liquidity_overlay": "neutral"})
        assert rv2["receding"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
