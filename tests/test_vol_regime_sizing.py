"""Tests for the SUBTRACT-ONLY vol-regime sizing overlay (engine/vol_regime.sizing_overlay)
and its three consumers:

  • sizing_overlay      — bounds, subtract-only invariant, mechanical-vs-gated levers, no-op cases
  • per-stock ladder    — engine/cycles.analyze(vol_regime=...) is subtract-only + buy-setup-only,
                          gate-config kill-switch zeroes it, and calm regimes never bite
  • baskets             — engine/theme_scoring stands aggressive recos DOWN in a risk-off regime
                          WITHOUT moving any score or rank (never-lifts invariant)

The doctrine under test: the overlay can only CUT gross / conviction (drawdown / capital-
efficiency, never alpha); the continuous SCORED composite only deepens the cut when the
validation gate is open; everything degrades to a clean no-op when the regime is absent.
"""
import numpy as np
import pandas as pd
import pytest

from engine import vol_regime as vr
from engine.cycles import analyze
from lib import config


# --------------------------------------------------------------------------- #
# sizing_overlay                                                              #
# --------------------------------------------------------------------------- #
def _snap(regime="normalizing", vt=0.9, scored_active=False, scored=None):
    return {"available": True, "regime": regime, "scored_active": scored_active,
            "scored_score": scored, "vol_target_scalar": vt}


def test_sizing_overlay_bounds_subtract_only():
    """Over a random sweep of snapshots the gross scalar stays in [gross_floor, 1.0] —
    the overlay can never lever up, only cut."""
    rng = np.random.default_rng(0)
    floor = vr.OVERLAY_DEFAULTS["gross_floor"]
    for _ in range(500):
        s = _snap(regime=rng.choice(["calm-contango", "normalizing", "warning",
                                      "backwardation-stress"]),
                  vt=float(rng.uniform(0.5, 1.5)),
                  scored_active=bool(rng.integers(0, 2)),
                  scored=float(rng.uniform(-1, 1)))
        g = vr.sizing_overlay(s)["gross_scalar"]
        assert floor <= g <= 1.0


def test_sizing_overlay_mechanical_only_when_calm():
    """A calm regime applies ONLY the mechanical vol-target leg (no regime caution, no
    gated deepener)."""
    o = vr.sizing_overlay(_snap(regime="normalizing", vt=0.7))
    assert o["regime_caution"] == 1.0 and o["scored_cut"] == 1.0
    assert o["mech_scalar"] == 0.7 and o["gross_scalar"] == 0.7 and o["active"]


def test_sizing_overlay_regime_caution_is_extra_cut():
    """A risk-off STATE adds a haircut on top of the mechanical leg — strictly deeper than
    the calm read at the same vol-target."""
    calm = vr.sizing_overlay(_snap(regime="normalizing", vt=0.9))["gross_scalar"]
    warn = vr.sizing_overlay(_snap(regime="warning", vt=0.9))["gross_scalar"]
    stress = vr.sizing_overlay(_snap(regime="backwardation-stress", vt=0.9))["gross_scalar"]
    assert stress < warn < calm


def test_sizing_overlay_scored_deepener_only_when_gate_open():
    """The continuous SCORED composite only bites when the gate is OPEN. Gate closed => the
    scored leg contributes nothing even with an identical risk-off score (validate-first)."""
    closed = vr.sizing_overlay(_snap("backwardation-stress", vt=1.0, scored_active=False, scored=-0.8))
    opened = vr.sizing_overlay(_snap("backwardation-stress", vt=1.0, scored_active=True, scored=-0.8))
    assert closed["scored_cut"] == 1.0                 # gate closed -> no scored contribution
    assert opened["scored_cut"] < 1.0                  # gate open -> deepens the cut
    assert opened["gross_scalar"] < closed["gross_scalar"]


def test_sizing_overlay_gate_open_but_risk_on_scored_does_not_lift():
    """An OPEN gate with a risk-ON (positive) scored score must NOT lift gross — subtract-only."""
    o = vr.sizing_overlay(_snap("normalizing", vt=0.8, scored_active=True, scored=0.9))
    assert o["scored_cut"] == 1.0 and o["gross_scalar"] <= 0.8


def test_sizing_overlay_noop_on_empty_and_disabled():
    assert vr.sizing_overlay({})["gross_scalar"] == 1.0
    assert vr.sizing_overlay(None)["active"] is False
    assert vr.sizing_overlay({"available": False})["gross_scalar"] == 1.0
    off = vr.sizing_overlay(_snap("backwardation-stress", vt=0.5), cfg={"enabled": False})
    assert off["gross_scalar"] == 1.0 and off["active"] is False


def test_is_risk_off():
    assert vr.is_risk_off("warning") and vr.is_risk_off("backwardation-stress")
    assert not vr.is_risk_off("normalizing") and not vr.is_risk_off("calm-contango")
    assert not vr.is_risk_off(None)


# --------------------------------------------------------------------------- #
# per-stock ladder caution                                                    #
# --------------------------------------------------------------------------- #
def _wavy_close(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-02", periods=n)
    steps = rng.normal(0.0004, 0.02, n)
    return pd.Series(100 * np.exp(np.cumsum(steps)), index=idx)


_STRESS = {"available": True, "regime": "backwardation-stress", "scored_active": False,
           "scored_score": None, "vol_target_scalar": 0.7}
_CALM = {"available": True, "regime": "normalizing", "scored_active": False,
         "scored_score": None, "vol_target_scalar": 0.9}


def test_ladder_vol_regime_is_subtract_only_and_buy_setup_only():
    """A risk-off vol-regime can only LOWER the ladder score, never raise it, and a penalty
    only ever fires on a buy-setup state. A calm regime never bites."""
    for seed in range(8):
        close = _wavy_close(seed=seed)
        base = analyze(close, vol_regime=None)["ladder"]
        stress = analyze(close, vol_regime=_STRESS)["ladder"]
        calm = analyze(close, vol_regime=_CALM)["ladder"]
        if not base:
            continue
        assert {"vol_regime_state", "vol_regime_pen", "vol_regime_effect"} <= base.keys()
        assert stress["score"] <= base["score"]          # subtract-only
        assert calm["score"] == base["score"]            # calm regime is inert
        assert calm["vol_regime_pen"] == 0
        if stress["vol_regime_pen"] > 0:
            assert base["state"] in ("FRESH BUY", "TURN SIGNALED")
            assert stress["vol_regime_line"]             # bilingual prose attached
            assert stress["vol_regime_line_zh"]


def test_ladder_stress_deeper_than_warning():
    """backwardation-stress is at least as deep a cut as warning on the same buy setup."""
    warn = dict(_STRESS, regime="warning")
    found = False
    for seed in range(12):
        close = _wavy_close(seed=seed)
        b = analyze(close, vol_regime=None)["ladder"]
        if not b or b["state"] not in ("FRESH BUY", "TURN SIGNALED"):
            continue
        s = analyze(close, vol_regime=_STRESS)["ladder"]
        w = analyze(close, vol_regime=warn)["ladder"]
        assert s["vol_regime_pen"] >= w["vol_regime_pen"] > 0
        found = True
    assert found, "no buy-setup series found to compare stress vs warning"


def test_ladder_kill_switch_config_zeroes_overlay(monkeypatch):
    cfg = config.load()
    monkeypatch.setitem(cfg["engine"]["vol_regime_overlay"], "enabled", False)
    for seed in range(6):
        lad = analyze(_wavy_close(seed=seed), vol_regime=_STRESS)["ladder"]
        if not lad:
            continue
        assert lad["vol_regime_pen"] == 0 and lad["vol_regime_effect"] is None
        assert lad["vol_regime_state"] is None


def test_ladder_gate_open_deepens_cut():
    """With the gate OPEN and a risk-off scored score, the buy-setup penalty is >= the
    gate-closed penalty on the same series."""
    open_stress = {"available": True, "regime": "backwardation-stress", "scored_active": True,
                   "scored_score": -0.7, "vol_target_scalar": 0.7}
    found = False
    for seed in range(12):
        close = _wavy_close(seed=seed)
        b = analyze(close, vol_regime=None)["ladder"]
        if not b or b["state"] not in ("FRESH BUY", "TURN SIGNALED"):
            continue
        closed = analyze(close, vol_regime=_STRESS)["ladder"]
        opened = analyze(close, vol_regime=open_stress)["ladder"]
        assert opened["vol_regime_pen"] >= closed["vol_regime_pen"] > 0
        found = True
    assert found


# --------------------------------------------------------------------------- #
# baskets — reco demotion never lifts a score or rank                         #
# --------------------------------------------------------------------------- #
def test_baskets_regime_demotes_recos_without_moving_rank(monkeypatch):
    from engine import theme_scoring as ts

    base = ts.compute_theme_intel("us")
    if base is None:
        pytest.skip("baskets data plane unavailable in this checkout")

    monkeypatch.setattr(ts.vol_regime, "published_snapshot",
                        lambda *a, **k: {"available": True, "regime": "backwardation-stress",
                                         "scored_active": False, "scored_score": None,
                                         "vol_target_scalar": 0.7})
    stressed = ts.compute_theme_intel("us")
    assert stressed is not None

    base_by = {t["id"]: t for t in base["themes"]}
    for t in stressed["themes"]:
        b = base_by[t["id"]]
        # never lifts: score + rank are byte-identical to the calm baseline
        assert t["score"] == b["score"] and t["rank"] == b["rank"]
        # aggressive recos are stood down to hold
        if b["reco"] in ("enter", "accumulate"):
            assert t["reco"] == "hold" and t["regime_demoted"]
        else:
            assert t["reco"] == b["reco"]
    # the gross scalar is published and risk-off
    rs = stressed["regime_sizing"]
    assert rs["regime"] == "backwardation-stress" and rs["gross_scalar"] < 1.0
    # no aggressive buys survive in act_now under stress
    assert stressed["act_now"]["buy"] == []
