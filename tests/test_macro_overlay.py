"""Tests for the macro-risk overlay (research/MACRO_RISK_INTEGRATION.md):

  • MRS (macro-risk score) — bounds, label, monotonicity, leg renormalization
  • the sector-heat macro term — asymmetric, risk-OFF, and a no-op by default
  • the per-stock ladder macro term — subtract-only, buy-setup-only invariant
  • the kill-switch (engine.macro_overlay.enabled = false)
  • live==calibrate — the live scalar matches the historical series' last value
    (the trap that would otherwise make the displayed honesty bands lie)

Everything is engineered frames / pure functions — no network, no stored data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.conditions import (  # noqa: E402
    conditions_snapshot,
    macro_risk_score,
    macro_risk_series,
    macro_risk_snapshot,
    sector_macro_beta,
)
from engine.cycles import analyze  # noqa: E402
from engine.technicals import _macro_pts, _score_components  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures                                                                     #
# --------------------------------------------------------------------------- #

def _latest(recession=80.0, drawdown=90.0, nfci=0.2, nfci_pct=0.95,
            trend="tightening", liq="contracting", trans="TRANSITIONING") -> dict:
    """A latest.json-shaped snapshot with the fields macro_risk_score reads."""
    return {
        "conditions": {
            "recession": {"score": recession},
            "drawdown_risk": {"score": drawdown},
            "financial_conditions": {"nfci": nfci, "nfci_pctile": nfci_pct,
                                     "trend": trend},
        },
        "liquidity_overlay": liq,
        "transition_state": trans,
    }


def _frame(n: int = 400, **overrides) -> pd.DataFrame:
    """A plausible feature frame with all conditions inputs present (mirrors the
    helper in test_conditions.py so macro_risk_series has real legs to fold)."""
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.arange(n, dtype=float)
    f = pd.DataFrame(index=idx)
    f["SPY"] = 400 + np.cumsum(np.sin(rng / 9) * 0.4)
    f["vix"] = 16 + 3 * np.sin(rng / 30)
    f["vix3m"] = 18 + 2 * np.sin(rng / 30)
    f["skew"] = 130 + 8 * np.sin(rng / 40)
    f["us10y"] = 4.0 + 0.3 * np.sin(rng / 50)
    f["hy_oas"] = 3.5 + 0.4 * np.sin(rng / 45)
    f["copper_gold"] = 0.18 + 0.01 * np.sin(rng / 35)
    f["dxy"] = 103 + 2 * np.sin(rng / 60)
    f["spread_2s10s"] = 0.2 + 0.2 * np.sin(rng / 70)
    f["term_premium_10y"] = 0.4
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    f["nfci"] = -0.4 + 0.1 * np.sin(rng / 25)
    f["anfci"] = -0.2
    f["nfci_risk"] = -0.5
    f["nfci_credit"] = -0.05
    f["nfci_leverage"] = 0.4
    f["stlfsi"] = -0.8
    f["sahm"] = 0.10
    f["recession_prob"] = 1.0
    f["ebp"] = -0.3
    f["ebp_recession_prob"] = 0.08
    f["wei"] = 2.5
    f["gdpnow"] = 2.8
    f["sticky_cpi"] = 0.30
    f["flex_cpi"] = 0.50
    f["median_cpi"] = 3.5
    f["umich_infl_exp"] = 3.0
    for k, v in overrides.items():
        f[k] = v
    return f


def _regime(idx, liquidity="contracting", transition="TRANSITIONING") -> pd.DataFrame:
    return pd.DataFrame({"liquidity": liquidity, "transition_state": transition},
                        index=idx)


# --------------------------------------------------------------------------- #
# MRS scalar                                                                   #
# --------------------------------------------------------------------------- #

def test_mrs_bounds_and_label():
    hi = macro_risk_score(_latest())
    assert 0.0 <= hi["score"] <= 1.0 and hi["label"] == "severe"
    lo = macro_risk_score(_latest(recession=5, drawdown=10, nfci=-0.3, nfci_pct=0.1,
                                  trend="loosening", liq="expanding", trans="STABLE"))
    assert lo["score"] < 0.1 and lo["label"] == "low"


def test_mrs_monotonic_in_recession_and_drawdown():
    base = macro_risk_score(_latest(recession=20, drawdown=20))["score"]
    more_rec = macro_risk_score(_latest(recession=90, drawdown=20))["score"]
    more_dd = macro_risk_score(_latest(recession=20, drawdown=90))["score"]
    assert more_rec > base and more_dd > base


def test_mrs_nfci_leg_only_counts_when_tightening_and_positive():
    # negative nfci => leg contributes 0 even at high percentile
    neg = macro_risk_score(_latest(recession=0, drawdown=0, nfci=-0.2, nfci_pct=0.99,
                                   liq="neutral", trans="STABLE"))
    assert neg["components"]["nfci"] == 0.0
    # positive + tightening => leg counts
    pos = macro_risk_score(_latest(recession=0, drawdown=0, nfci=0.2, nfci_pct=0.99,
                                   liq="neutral", trans="STABLE"))
    assert pos["components"]["nfci"] == 0.99 and pos["score"] > neg["score"]


def test_mrs_renormalizes_when_legs_missing():
    # only the recession leg present -> score == recession value (others drop out)
    only_rec = macro_risk_score({"conditions": {"recession": {"score": 60}}})
    assert abs(only_rec["score"] - 0.6) < 1e-3
    assert only_rec["components"]["drawdown"] is None
    # transition-only -> its weighted value alone (0.5 * w / w)
    only_tr = macro_risk_score({"transition_state": "WEAKENING"})
    assert abs(only_tr["score"] - 0.5) < 1e-3
    # nothing at all -> None, no crash
    assert macro_risk_score({})["score"] is None


def test_mrs_liquidity_leg_contracting_only():
    # the liquidity leg is KEPT (it carries the validated cyclical/defensive split):
    # it fires only on contracting, and is 0 otherwise.
    assert macro_risk_score(_latest(liq="contracting"))["components"]["liquidity"] == 1.0
    assert macro_risk_score(_latest(liq="expanding"))["components"]["liquidity"] == 0.0
    assert macro_risk_score(_latest(liq="neutral"))["components"]["liquidity"] == 0.0


# --------------------------------------------------------------------------- #
# sector-heat term                                                             #
# --------------------------------------------------------------------------- #

def test_macro_pts_default_is_noop():
    assert _macro_pts(None, 1.0) == 0
    assert _macro_pts(0.0, 1.0) == 0


def test_macro_pts_asymmetric_risk_off():
    mmax = config.load()["engine"]["macro_overlay"]["macro_max"]
    # cyclical, max stress -> full penalty, capped at -macro_max
    assert _macro_pts(1.0, 1.0) == -mmax
    # defensive -> a credit, capped at +macro_max/2
    assert 0 < _macro_pts(1.0, -1.0) <= round(mmax / 2)
    # penalties are larger in magnitude than the defensive credit
    assert abs(_macro_pts(1.0, 1.0)) > abs(_macro_pts(1.0, -1.0))


def _tech():
    return {"above200": True, "above50": True, "macd_pos": True, "rsi14": 60}


def test_score_components_noop_without_macro_args():
    h = _score_components(True, 1, "leading", False, _tech(), 50.0)
    h_explicit_zero = _score_components(True, 1, "leading", False, _tech(), 50.0,
                                        macro_drag=0.0, macro_beta=1.0)
    assert h["macro"] == 0 and h_explicit_zero["macro"] == 0
    assert h["score"] == h_explicit_zero["score"]


def test_score_components_penalizes_cyclical_credits_defensive():
    base = _score_components(True, 1, "leading", False, _tech(), 50.0)["score"]
    cyc = _score_components(True, 1, "leading", False, _tech(), 50.0,
                           macro_drag=0.9, macro_beta=1.0)["score"]
    deff = _score_components(True, 1, "leading", False, _tech(), 50.0,
                            macro_drag=0.9, macro_beta=-0.4)["score"]
    assert cyc < base <= deff


def test_kill_switch_zeroes_overlay(monkeypatch):
    cfg = config.load()
    orig = cfg["engine"]["macro_overlay"]["enabled"]
    monkeypatch.setitem(cfg["engine"]["macro_overlay"], "enabled", False)
    try:
        assert _macro_pts(1.0, 1.0) == 0
        h = _score_components(True, 1, "leading", False, _tech(), 50.0,
                             macro_drag=0.9, macro_beta=1.0)
        assert h["macro"] == 0
        # the ladder dict must also go neutral: no penalty AND no stray metadata
        for seed in range(4):
            lad = analyze(_wavy_close(seed=seed), macro_drag=0.9, macro_beta=1.0)["ladder"]
            if not lad:
                continue
            assert lad["macro_pen"] == 0 and lad["macro_effect"] is None
            assert lad["macro_drag"] is None and lad["macro_beta"] == 0.0
    finally:
        monkeypatch.setitem(cfg["engine"]["macro_overlay"], "enabled", orig)


# --------------------------------------------------------------------------- #
# per-stock ladder term                                                        #
# --------------------------------------------------------------------------- #

def _wavy_close(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-02", periods=n)
    steps = rng.normal(0.0004, 0.02, n)
    return pd.Series(100 * np.exp(np.cumsum(steps)), index=idx)


def test_ladder_macro_is_subtract_only_and_buy_setup_only():
    """For ANY series: a risk-off macro reading on a cyclical name can only LOWER
    the ladder score (never raise it), a defensive name (beta<=0) is untouched,
    and the macro_* keys are always present."""
    for seed in range(6):
        close = _wavy_close(seed=seed)
        base = analyze(close, macro_drag=None)["ladder"]
        cyc = analyze(close, macro_drag=0.9, macro_beta=1.0)["ladder"]
        deff = analyze(close, macro_drag=0.9, macro_beta=-0.4)["ladder"]
        if not base:
            continue
        assert {"macro_effect", "macro_pen", "macro_drag", "macro_beta"} <= base.keys()
        assert cyc["score"] <= base["score"]          # subtract-only
        assert deff["score"] == base["score"]         # defensive untouched (beta<=0)
        # a penalty only ever fires on a buy-setup state
        if cyc["macro_pen"] > 0:
            assert base["state"] in ("FRESH BUY", "TURN SIGNALED")


# --------------------------------------------------------------------------- #
# the consistency guarantee                                                    #
# --------------------------------------------------------------------------- #

def test_live_snapshot_matches_calibrate_series():
    """The PERSISTED live value (macro_risk_snapshot — what the engine writes and
    the heat penalty reads) must equal macro_risk_series's last valid value (what
    calibrate folds into the honesty bands), BY CONSTRUCTION. If these drift the
    displayed band hit-rates silently lie. The date-coherent dict path
    (macro_risk_score) must agree too."""
    for liq, trans, nfci in (("contracting", "TRANSITIONING", -0.4),
                             ("expanding", "STABLE", 0.2),
                             ("neutral", "WEAKENING", 0.1)):
        f = _frame(nfci=np.full(400, nfci))
        reg = _regime(f.index, liquidity=liq, transition=trans)
        series = macro_risk_series(f, reg).dropna()
        assert series.shape[0] > 0
        # snapshot == series last value, exactly (shared leg computation)
        snap = macro_risk_snapshot(f, reg)
        assert abs(snap["score"] - float(series.iloc[-1])) < 1e-3, (liq, trans, nfci)
        # date-coherent dict path agrees too (to rounding)
        latest = {"conditions": conditions_snapshot(f),
                  "liquidity_overlay": liq, "transition_state": trans}
        assert abs(macro_risk_score(latest)["score"] - float(series.iloc[-1])) < 2e-3


def test_snapshot_robust_to_stale_quad():
    """The HIGH-severity bug the review caught: the live value must NOT mix legs
    across dates when quad goes stale before conditions/labels update. Because the
    snapshot is derived from the series (one coherent date), flipping the last rows'
    transition just moves it to the new last-row value — never a blend."""
    f = _frame(380)
    reg = _regime(f.index, transition="STABLE")
    col = reg.columns.get_loc("transition_state")
    reg.iloc[-10:, col] = "TRANSITIONING"          # a fresh signal at the very end
    series = macro_risk_series(f, reg).dropna()
    snap = macro_risk_snapshot(f, reg)
    assert abs(snap["score"] - float(series.iloc[-1])) < 1e-3
    # the end-of-series flip raised MRS vs the pre-flip level
    assert snap["score"] > float(series.iloc[-20])


def test_sector_macro_beta_lookup():
    # value-agnostic (betas are recalibrated by scripts/calibrate_macro_betas): assert
    # the STRUCTURE — cyclical positive, defensive negative, GICS alias == its SPDR,
    # case-insensitive, unknown -> 0.
    assert sector_macro_beta("XLF") > 0                     # cyclical penalized
    assert sector_macro_beta("XLP") < 0                     # defensive credited
    assert sector_macro_beta("Technology") == sector_macro_beta("XLK")   # GICS alias
    assert sector_macro_beta("health care") == sector_macro_beta("Health Care")  # case-insens.
    assert sector_macro_beta("SPY") == 0.0                  # unknown -> 0
    assert sector_macro_beta(None) == 0.0
