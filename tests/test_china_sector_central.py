"""China Sector Central (Phase-2 fuser) + self-grader tests.

Pure confluence/gate invariants always run; the data-dependent compute()/grader contract
skips cleanly when the china_sectors plane is absent.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine import china_sector_central as cc
from engine import china_sector_central_grader as cg
from engine import china_sector_index as csi

HAVE_DATA = csi.sw_close("801780") is not None


# --------------------------------------------------------------- pure logic ----

def test_tier_thresholds():
    assert cc._tier_for(90)[0] == "Accumulate"
    assert cc._tier_for(60)[0] == "Constructive"
    assert cc._tier_for(50)[0] == "Neutral"
    assert cc._tier_for(35)[0] == "Cautious"
    assert cc._tier_for(5)[0] == "Reduce"


def test_state_score_washout_is_bullish():
    bull, _ = cc._state_score({"signature": {"score": 8}, "phase": "Trough"})
    bear, _ = cc._state_score({"signature": {"score": 92}, "phase": "Peak"})
    assert bull > 0.4 and bear < -0.3 and bull > bear


def test_forward_tilt_only_with_pathway():
    assert cc._forward_tilt({})[0] is None
    rec = {"pathway": {"conditional": {"h6": {"lift": 0.15, "n": 40, "ci_lo": 0.55,
                                              "ci_hi": 0.85, "base_rate": 0.5, "cond_rate": 0.7, "h": 6}},
                       "setup": {"tercile": "high"}}}
    tilt, d = cc._forward_tilt(rec)
    assert tilt is not None and tilt > 0 and d["n"] == 40 and d["cond_rate"] == 0.7


def test_regime_gate_shrinks_bullish_conviction():
    """A risk-OFF gate must produce a LOWER conviction than a risk-ON gate for the same bullish setup."""
    rec = {"now": {"signature": {"score": 10}, "phase": "Recovery", "rs_rank": 2,
                   "above200d": True, "rs_63d": 5.0}}
    mkt_on = {"gate_factor": 1.0, "risk_on": 0.8, "state_en": "risk-on", "_crowd_by_ticker": {}}
    mkt_off = {"gate_factor": 0.2, "risk_on": -0.9, "state_en": "risk-off", "_crowd_by_ticker": {}}
    s_on = cc._fuse(rec, mkt_on, 31)["conviction"]["score"]
    s_off = cc._fuse(rec, mkt_off, 31)["conviction"]["score"]
    assert s_on > s_off, f"risk-off ({s_off}) should gate below risk-on ({s_on})"


def test_euphoric_cannot_be_top_tier():
    rec = {"now": {"signature": {"score": 95}, "phase": "Peak", "rs_rank": 1, "above200d": True}}
    mkt = {"gate_factor": 1.0, "risk_on": 0.9, "state_en": "risk-on", "_crowd_by_ticker": {}}
    conv = cc._fuse(rec, mkt, 31)["conviction"]
    assert conv["label_en"] in ("Neutral", "Cautious", "Reduce")  # euphoric → not Accumulate


def test_reasoning_zh_has_no_english_leak():
    """The zh reasoning BODIES must translate every regime/quad/phase/momentum token so a
    zh reader sees no English in the expanded trace (guards the build-side i18n fix)."""
    import re
    latin = re.compile(r"[A-Za-z]")
    mkt = {"state_en": "Risk-off — de-risking", "state_zh": "风险偏离 — 降险中",
           "derisk_blended": 0.96, "quad": "Q3", "quad_name": "Stagflation",
           "liquidity": "neutral", "gate_factor": 0.2, "risk_on": -0.9}
    fwd_d = {"cond_rate": 0.62, "base_rate": 0.5, "lift": 0.12, "ci_lo": 0.55,
             "ci_hi": 0.7, "n": 40, "h": 6}
    cases = [("Beaten down", "深度超跌", "Trough"), ("Recovering", "修复回升", "Recovery"),
             ("Mid-cycle", "周期中段", "Expansion"), ("Stretched", "走高偏贵", "Peak"),
             ("Overheated", "过热", "Downturn")]
    for (label, label_zh, phase), lead in [(c, ld) for c in cases
                                           for ld in ("leading", "lagging", "mid-pack")]:
        state_d = {"signature": 50, "phase": phase, "label": label, "label_zh": label_zh}
        rows = cc._trace(state_d, fwd_d, mkt, {"rs_rank": 3, "lead": lead},
                         {"n_crowded": 2, "n_members": 6, "frac": 0.33}, early=True, euphoric=True)
        for r in rows:
            assert not latin.search(r["zh"]), f"English leaked into zh body: {r['zh']!r}"


# ------------------------------------------------------------ data-dependent ----

@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_compute_contract():
    data = cc.compute()
    assert data and data["sectors"]
    m = data["market"]
    assert "gate_factor" in m and 0.2 <= m["gate_factor"] <= 1.0
    assert m.get("validated") is True
    for s in data["sectors"]:
        c = s["conviction"]
        assert 0 <= c["score"] <= 100 and c["label_en"] and c["dir"] in ("up", "down", "flat")
        assert c["confluence"]["agree"] <= 3
        assert isinstance(s["reasoning"], list) and len(s["reasoning"]) >= 2
        # every reasoning row is tier-tagged for the honesty colouring
        assert all(r["tier"] in ("validated", "confirmer", "display") for r in s["reasoning"])
    # the 4 GS sectors carry the validated forward layer
    fwd = [s for s in data["sectors"] if s.get("forward") and s["forward"].get("cond_rate") is not None]
    assert len(fwd) >= 3
    assert "NaN" not in json.dumps(data, default=str)


@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_grader_roundtrip(tmp_path, monkeypatch):
    from lib import config
    data = cc.compute()                              # real data dir — needs the price plane
    assert data
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)   # redirect only the log write/read
    n = cg.append_central_log(data)
    assert n == data["meta"]["n_sectors"] + data["meta"]["n_baskets"]
    gr = cg.grade()
    assert gr["available"] is True and gr["n_calls"] == n
    # nothing matured on day one → by_horizon present but accruing
    assert "by_horizon" in gr
