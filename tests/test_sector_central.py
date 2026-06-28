"""Tests for the US Sector Central fuser (engine.sector_central) + its self-grader.

The fuser's load-bearing US-specific behaviors are tested deterministically with hand-built
cycle records: (1) the cycle-state score keys off the 0–100 oscillator (no `signature` field);
(2) the VALIDATED absolute-trend gate de-rates / caps a bullish read when a sector is below its
own trend (the genuine US drawdown lever — the opposite of China, where the gate failed);
(3) the per-sector macro-beta differentiation gates cyclicals harder than defensives in risk-off.
The public compute() is checked for fail-soft well-formedness, and the grader for a PIT roundtrip.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import sector_central as sc
from engine import sector_central_grader as scg


def _rec(ticker="XLK", name="Technology", pos=10.0, phase="Recovery", signal="BUY",
         rs_rank=1, above200d=True, rs_63d=5.0, kind="sector"):
    """A bullish, washed-out cycle record (the strongest setup) unless overridden."""
    return {
        "id": ticker.lower(), "ticker": ticker, "kind": kind, "name": name,
        "accent": "#38bdf8", "group": "Growth",
        "proj": {"tilt": "tailwind", "nextTurn": "trough", "low": "2026-07", "high": "2027-01"},
        "now": {"pos": pos, "phase": phase, "phaseLabel": phase, "signal": signal,
                "osc_slope": 1.0, "rs_rank": rs_rank, "above200d": above200d, "rs_63d": rs_63d},
    }


def _mkt(risk_on=0.5, gate_factor=1.0):
    return {"risk_on": risk_on, "gate_factor": gate_factor, "state_en": "Risk-on",
            "quad_name": "Goldilocks", "liquidity": "expanding", "derisk_blended": 0.25,
            "_crowd_by_ticker": {}}


# ------------------------------------------------------------- state scoring ----

def test_state_score_washout_is_bullish_stretched_is_bearish():
    washed, _ = sc._state_score({"pos": 5, "phase": "Trough", "signal": None})
    stretched, _ = sc._state_score({"pos": 95, "phase": "Peak", "signal": None})
    assert washed > 0.4
    assert stretched < -0.3


def test_state_score_turn_signal_nudges():
    base, _ = sc._state_score({"pos": 50, "phase": "Expansion", "signal": None})
    buy, _ = sc._state_score({"pos": 50, "phase": "Expansion", "signal": "BUY"})
    sell, _ = sc._state_score({"pos": 50, "phase": "Expansion", "signal": "SELL"})
    assert buy > base > sell


def test_as_str_flattens_list_proxy():
    assert sc._as_str(["XLP", "XLU"]) == "XLP/XLU"
    assert sc._as_str("XLK") == "XLK"
    assert sc._as_str(None) is None


def test_tier_for_thresholds():
    assert sc._tier_for(80)[0] == "Accumulate"
    assert sc._tier_for(60)[0] == "Constructive"
    assert sc._tier_for(50)[0] == "Neutral"
    assert sc._tier_for(35)[0] == "Cautious"
    assert sc._tier_for(10)[0] == "Reduce"


# -------------------------------------- the VALIDATED absolute-trend drawdown gate ----

def test_trend_gate_below_trend_derates_and_caps_a_bullish_read():
    """The US lever: a strongly bullish washed-out sector that is BELOW its own 200-day trend is
    de-rated and cannot be top-tier (validated_risk_control), even though the cycle setup screams
    buy. This is the XLC 2026-06 behavior and the core US-vs-China difference."""
    rec = _rec()
    above = sc._fuse(rec, _mkt(), 11, trend={"pass": True, "above_200dma": True})
    below = sc._fuse(rec, _mkt(), 11, trend={"pass": False, "above_200dma": False})
    assert above["conviction"]["score"] > below["conviction"]["score"]
    # below-trend can never be an up-tier conviction
    assert below["conviction"]["label_en"] not in ("Accumulate", "Constructive")
    assert above["conviction"]["label_en"] in ("Accumulate", "Constructive")
    assert below["components"]["trend_pass"] is False


def test_trend_gate_none_is_neither_derated_nor_capped():
    rec = _rec()
    none = sc._fuse(rec, _mkt(), 11, trend=None)
    above = sc._fuse(rec, _mkt(), 11, trend={"pass": True})
    # an unknown gate behaves like a permissive (no de-rate)
    assert none["conviction"]["score"] == above["conviction"]["score"]


# ----------------------------------------- per-sector macro-beta differentiation ----

def test_macro_beta_gates_cyclical_harder_than_defensive_in_riskoff():
    """In a risk-OFF regime the per-sector gate shrinks a cyclical (XLF, β+) more than a
    defensive (XLP, β−). Both are otherwise identical bullish above-trend reads."""
    mkt = _mkt(risk_on=-0.6, gate_factor=0.6)
    cyc = sc._fuse(_rec(ticker="XLF", name="Financials"), mkt, 11, trend={"pass": True})
    dfn = sc._fuse(_rec(ticker="XLP", name="Consumer Staples"), mkt, 11, trend={"pass": True})
    # the defensive keeps a higher effective gate → higher conviction
    assert dfn["components"]["gate_eff"] > cyc["components"]["gate_eff"]
    assert dfn["conviction"]["score"] >= cyc["conviction"]["score"]
    assert cyc["components"]["macro_beta"] > dfn["components"]["macro_beta"]


# ------------------------------------------------------------- momentum confirmer ----

def test_momentum_is_capped_and_lagging_marks_early():
    rec = _rec(rs_rank=11, above200d=True)            # last of 11 = lagging
    out = sc._fuse(rec, _mkt(), 11, trend={"pass": True})
    assert -0.3 <= out["components"]["momentum"] <= 0.3      # hard cap
    assert out["conviction"]["early"] is True               # bullish lead + lagging RS = early


def test_reasoning_trace_tiers_are_well_formed():
    out = sc._fuse(_rec(), _mkt(), 11, trend={"pass": True},
                   heat={"heat_1M": 2.5, "breadth_pct": 80})
    layers = {r["layer"] for r in out["reasoning"]}
    assert {"Cycle state", "Trend gate", "Regime gate", "Momentum"} <= layers
    for r in out["reasoning"]:
        assert r["tier"] in ("validated", "confirmer", "display")
        assert r["en"] and r["zh"]


def test_reasoning_zh_has_no_english_leak():
    """The zh reasoning BODIES must translate every phaseLabel/quad/lead/signal/beta token so a
    zh reader sees no English in the expanded trace (guards the build-side i18n fix). state_zh is
    supplied upstream, so the regime row falls back to it rather than leaking the English state."""
    import re
    latin = re.compile(r"[A-Za-z]")
    mkt = {"state_en": "Risk-on — adding", "state_zh": "风险偏好 — 加仓", "derisk_blended": 0.25,
           "quad": "Q1", "quad_name": "Goldilocks", "liquidity": "expanding",
           "gate_factor": 0.6, "risk_on": 0.5}
    fwd = {"trend_pass": True, "ret_12m": 0.17}
    plabs = [("Bottoming", "Trough"), ("Prime entry", "Recovery"), ("Trending", "Expansion"),
             ("Topping", "Peak"), ("Rolling over", "Downturn")]
    for (plab, phase), sig, lead, beta in [(p, s, ld, b) for p in plabs
                                           for s in ("BUY", "SELL", None)
                                           for ld in ("leading", "lagging", "mid-pack")
                                           for b in (0.5, -0.5, 0.0)]:
        state_d = {"pos": 27.0, "phase": phase, "phaseLabel": plab, "signal": sig, "osc_slope": 1.0}
        rows = sc._trace(state_d, fwd, mkt, {"rs_rank": 3, "lead": lead},
                         {"n_crowded": 2, "n_members": 6, "frac": 0.33}, early=True,
                         stretched=True, beta=beta, heat={"breadth_pct": 55, "heat_1M": 2.3})
        for r in rows:
            assert not latin.search(r["zh"]), f"English leaked into zh body: {r['zh']!r}"


# ---------------------------------------------------------------- trend gates map ----

def test_trend_gates_keys_sectors_by_ticker_and_baskets_by_bid():
    idx = pd.bdate_range("2022-01-01", periods=400)
    up = pd.Series(100 * np.cumprod(1 + np.full(400, 0.001)), index=idx)      # above trend, +12m
    dn = pd.Series(100 * np.cumprod(1 + np.full(400, -0.0015)), index=idx)    # below trend, −12m
    closes = pd.DataFrame({"XLK": up, "XLE": dn})
    rotation = {"ranks": [{"id": "us_sector_tech", "eligible": True,
                           "gate": {"above_200dma": True, "pos_12m": True}}]}
    gates = sc._trend_gates(closes, rotation)
    assert gates["xlk"]["pass"] is True and gates["xlk"]["source"] == "spdr"
    assert gates["xle"]["pass"] is False
    assert gates["b-us_sector_tech"]["pass"] is True and gates["b-us_sector_tech"]["source"] == "basket-ctx"


# --------------------------------------------------------------- compute (soft) ----

def test_compute_is_fail_soft_and_well_formed():
    """compute() must return None OR a well-formed payload — never raise (additive build)."""
    out = sc.compute()
    if out is None:
        return                                       # store unavailable in this env — acceptable
    assert out["meta"]["region"] == "us"
    assert isinstance(out["sectors"], list) and out["sectors"]
    for s in out["sectors"]:
        c = s["conviction"]
        assert 0 <= c["score"] <= 100
        assert c["label_en"] in {t[1] for t in sc.TIERS}
        assert isinstance(s["reasoning"], list) and s["reasoning"]
    # sorted by conviction descending
    scores = [s["conviction"]["score"] for s in out["sectors"]]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------------- grader ----

def test_grader_append_keeps_first_and_grade_accrues(tmp_path, monkeypatch):
    monkeypatch.setattr(scg.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(scg, "_yahoo_panel", lambda: None)
    monkeypatch.setattr(scg, "_basket_levels", lambda: {})
    data = {"as_of": "2026-06-01",
            "sectors": [{"id": "xlk", "kind": "sector", "ticker": "XLK", "name": "Technology",
                         "conviction": {"score": 70, "label_en": "Accumulate", "dir": "up",
                                        "confluence": {"agree": 3}},
                         "forward": {"trend_pass": True, "ret_12m": 0.2},
                         "components": {"gate_factor": 0.6}}],
            "baskets": []}
    assert scg.append_central_log(data) == 1
    # keep-FIRST: a second append on the same (date, id) must not duplicate
    data2 = dict(data); data2["sectors"] = [dict(data["sectors"][0])]
    data2["sectors"][0]["conviction"] = {"score": 5, "label_en": "Reduce", "dir": "down",
                                         "confluence": {"agree": 0}}
    scg.append_central_log(data2)
    g = scg.grade()
    assert g["available"] is True and g["n_calls"] == 1
    # sparse → accruing (no matured horizons / <3 graded)
    for h in ("21d", "63d", "126d"):
        assert g["by_horizon"][h].get("dir_hit_rate") in (None,)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
