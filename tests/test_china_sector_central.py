"""China Sector Central (Phase-2 fuser) + self-grader tests.

Pure confluence/gate invariants always run; the data-dependent compute()/grader contract
skips cleanly when the china_sectors plane is absent.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

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


def test_rolling_over_two_arms():
    """2026-07 rollover-lag audit port: the detector must fire BOTH on a stretched name whose
    daily ladder is still in decline (legacy arm) AND on a name that has ALREADY fallen — pos
    dropped below 68 and the ladder moved on to bottom-hunting — when the oscillator collapse
    carries a confirming fast signal (post-roll arm). Mild wiggles never fire."""
    # legacy decline arm: falling + stretched + ladder in decline
    assert cc._rolling_over({"osc_slope": -5.0, "pos_v2": 80.0, "timing_state": "DECLINE"})
    # post-roll arm: collapse off an elevated (not stretched) position + SELL confirm —
    # the pre-fix single arm read this False (pos < 68, ladder = TURN SIGNALED)
    assert cc._rolling_over({"osc_slope": -18.0, "pos_v2": 55.0,
                             "timing_state": "TURN SIGNALED", "signal": "SELL"})
    assert cc._rolling_over({"osc_slope": -12.0, "pos_v2": 60.0,
                             "timing_state": "TURN SIGNALED", "divergence": "bearish"})
    # collapse without any confirming fast signal: stays quiet
    assert not cc._rolling_over({"osc_slope": -12.0, "pos_v2": 60.0,
                                 "timing_state": "TURN SIGNALED"})
    # mild wiggle: neither arm
    assert not cc._rolling_over({"osc_slope": -4.0, "pos_v2": 55.0,
                                 "timing_state": "TURN SIGNALED", "signal": "SELL"})
    # rolling-over de-rates the state score to cautious even off a lagging bullish phase
    score, d = cc._state_score({"signature": {"score": 40}, "phase": "Expansion",
                                "osc_slope": -18.0, "pos_v2": 55.0,
                                "timing_state": "TURN SIGNALED", "signal": "SELL"})
    assert d["rolling"] is True and score <= -0.25


def test_forward_tilt_only_with_pathway():
    assert cc._forward_tilt({})[0] is None
    # W2.6 schema: n_months + n_eff + block-bootstrap LIFT band (lift_ci_lo/hi around 0).
    rec = {"pathway": {"conditional": {"h6": {"lift": 0.15, "n_months": 24, "n_eff": 12.0,
                                              "lift_ci_lo": 0.05, "lift_ci_hi": 0.30,
                                              "base_rate": 0.5, "cond_rate": 0.7, "h": 6,
                                              "composition_version": "v4-a+b+c+d-deadbeef"}},
                       "setup": {"tercile": "high"}}}
    tilt, d = cc._forward_tilt(rec)
    assert tilt is not None and tilt > 0 and d["n_months"] == 24 and d["cond_rate"] == 0.7
    # a LIFT CI that straddles zero must HALVE the confidence (no separation from base).
    rec2 = {"pathway": {"conditional": {"h6": {"lift": 0.15, "n_months": 24, "n_eff": 12.0,
                                               "lift_ci_lo": -0.05, "lift_ci_hi": 0.30,
                                               "base_rate": 0.5, "cond_rate": 0.7, "h": 6}},
                        "setup": {"tercile": "high"}}}
    _tilt2, d2 = cc._forward_tilt(rec2)
    assert d2["confidence"] < d["confidence"]


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
    fwd_d = {"cond_rate": 0.62, "base_rate": 0.5, "lift": 0.12, "lift_ci_lo": 0.02,
             "lift_ci_hi": 0.22, "n_months": 24, "n_eff": 12.0, "h": 6}
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


# ---- W0.4: gate-cap and staleness honesty tests ---- #

def test_gate_caps_tier_set_when_gate_at_floor():
    """_regime_anchor() must set gate_caps_tier='Accumulate' whenever gate is at the 0.2
    floor.  Derivation: max achievable score at gate=0.2 is 68, below the Accumulate
    threshold of 72 — so Accumulate is structurally unreachable and the honesty field must
    name it.  This guards against silent suppression of the top conviction tier."""
    # Patch regime_state to return extreme risk-off (tilt→1 → risk_on→−1 → gate floor=0.2)
    # and latest.json to Q3/neutral (Q3 penalty would push gate below floor, clipped to 0.2).
    fake_rs = {"tilt": 1.0, "blended": 1.0, "pct": 100,
               "state_en": "Risk-off — de-risking", "state_zh": "风险偏离 — 降险中",
               "tone": "off", "legs": [], "asof": "2026-07-03"}
    import json as _json
    fake_json_bytes = _json.dumps({"quad": "Q3", "quad_name": "Stagflation",
                                   "liquidity_overlay": "neutral"}).encode()

    # Patch both the regime_state import and the latest.json read
    with patch("engine.china_sector_central.json") as mock_json, \
         patch("engine.china_masterminds.regime_state", return_value=fake_rs):
        # Make json.loads return our controlled dict regardless of what path is read
        mock_json.loads.return_value = {"quad": "Q3", "quad_name": "Stagflation",
                                        "liquidity_overlay": "neutral"}
        from lib import config as cfg
        # Also ensure the path is reported as existing via monkeypatching config.data_dir
        # indirectly — we must patch the Path.exists so the json branch fires.
        import unittest.mock as _mock
        with _mock.patch.object(Path, "exists", return_value=True), \
             _mock.patch.object(Path, "read_text", return_value=_json.dumps(
                 {"quad": "Q3", "quad_name": "Stagflation", "liquidity_overlay": "neutral"})):
            anc = cc._regime_anchor()

    assert anc["gate_factor"] == 0.2, f"expected gate=0.2, got {anc['gate_factor']}"
    assert anc.get("gate_caps_tier") == "Accumulate", (
        f"gate_caps_tier should be 'Accumulate' when gate=0.2, got {anc.get('gate_caps_tier')!r}"
    )


def test_gate_caps_tier_none_when_gate_above_floor():
    """_regime_anchor() must NOT set gate_caps_tier when the gate is high enough that
    Accumulate (score ≥ 72) is reachable.  At gate ≥ 0.29 max_score ≥ 72."""
    # risk_on = +0.4 → gate = clip(0.5 + 0.5*0.4) = 0.7, no quad/liq penalty → 0.7
    fake_rs = {"tilt": -0.4, "blended": 0.3, "pct": 30,
               "state_en": "Risk-on — leaning in", "state_zh": "风险偏好 — 加仓",
               "tone": "on", "legs": [], "asof": "2026-07-03"}
    import json as _json
    import unittest.mock as _mock
    with _mock.patch("engine.china_masterminds.regime_state", return_value=fake_rs), \
         _mock.patch.object(Path, "exists", return_value=True), \
         _mock.patch.object(Path, "read_text", return_value=_json.dumps(
             {"quad": "Q1", "quad_name": "Goldilocks", "liquidity_overlay": "neutral"})):
        anc = cc._regime_anchor()

    assert anc["gate_factor"] >= 0.29, f"gate should be ≥ 0.29, got {anc['gate_factor']}"
    assert anc.get("gate_caps_tier") is None, (
        f"gate_caps_tier should be None when gate={anc['gate_factor']}, "
        f"got {anc.get('gate_caps_tier')!r}"
    )


def test_staleness_constant_gate_and_stale_leg_fails():
    """W0.4 sentinel: FAIL when gate_factor is constant across all calls for >=10 sessions
    while any regime-leg input file is stale (overdue beyond its threshold).

    A frozen upstream collector produces a gate stuck at one value for weeks without
    any explicit error.  This test uses the LIVE calls.parquet and the LIVE input file
    mtimes so it acts as an ongoing CI tripwire:
    - TODAY (healthy): gate IS constant at 0.2, but input files are fresh → passes.
    - FUTURE (broken): gate stays constant AND a file goes overdue → fails and alerts.

    NOTE: the test only activates once >=10 sessions have been logged.  Before that it
    skips (insufficient history to judge).
    """
    import time
    import os
    from lib import config

    calls_p = config.data_dir() / "china_sector_central" / "calls.parquet"
    if not calls_p.exists():
        pytest.skip("calls.parquet not yet present")

    df = pd.read_parquet(calls_p)
    if df.empty or "gate_factor" not in df.columns or "date" not in df.columns:
        pytest.skip("calls.parquet missing required columns")

    n_sessions = df["date"].nunique()
    if n_sessions < 10:
        pytest.skip(f"only {n_sessions} sessions logged — need >=10 to activate the sentinel")

    gate_values = df["gate_factor"].dropna().unique()
    gate_is_constant = len(gate_values) == 1

    # Compute actual age of each leg's source file
    now = time.time()
    leg_ages = cc._regime_leg_staleness(None)
    any_stale = any(
        age is not None and age > cc._LEG_STALE_DAYS.get(k, 999)
        for k, age in leg_ages.items()
    )

    stale_legs = {k: age for k, age in leg_ages.items()
                  if age is not None and age > cc._LEG_STALE_DAYS.get(k, 999)}

    # The test FAILS exactly when both conditions are true simultaneously — this is the
    # silent-freeze scenario that the W0.4 item exists to detect.
    assert not (gate_is_constant and any_stale), (
        f"gate_factor is constant at {gate_values[0] if len(gate_values)==1 else gate_values} "
        f"across {n_sessions} sessions AND regime-leg input(s) are stale: {stale_legs} "
        f"(thresholds: {cc._LEG_STALE_DAYS}) — "
        "a frozen upstream collector is likely silently pinning the gate"
    )


def test_regime_anchor_returns_staleness_fields():
    """_regime_anchor() must always return leg_stale, any_stale, and gate_caps_tier keys,
    even when the regime_state call fails (degraded state).  Missing keys would silently
    omit the honesty fields from the data emitted to the template."""
    # Patch regime_state to raise so we exercise the failure path
    import unittest.mock as _mock
    import json as _json
    with _mock.patch("engine.china_masterminds.regime_state", side_effect=RuntimeError("no data")), \
         _mock.patch.object(Path, "exists", return_value=False):
        anc = cc._regime_anchor()

    assert "leg_stale" in anc, "leg_stale must always be present in _regime_anchor() output"
    assert "any_stale" in anc, "any_stale must always be present in _regime_anchor() output"
    assert "gate_caps_tier" in anc, "gate_caps_tier must always be present in _regime_anchor() output"
    # with no regime data, gate defaults to 0.7 (>= 0.29) → no cap
    assert anc.get("gate_caps_tier") is None, (
        f"with no regime_state, gate=0.7 should not cap any tier; got {anc.get('gate_caps_tier')!r}"
    )
