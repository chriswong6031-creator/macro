"""Forex Vector engine tests — FX-specific invariants the commodity suite can't cover.

Synthetic where possible; a real-data orientation cross-check skips if the store is
empty. Catches the silent-bug surfaces flagged in review: FRED-direction orientation,
dollar-orthogonalization invariance, carry sign, archetype risk-beta, peg override.

Run: .venv/bin/python -m tests.test_forex
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import forex_signals as FS  # noqa: E402
from engine import forex_conviction as FC  # noqa: E402
from lib import config, store  # noqa: E402

CFG = config.load()["forex"]


def _idx(n=900):
    return pd.date_range("2012-01-01", periods=n, freq="B")


# --------------------------------------------------------------------------- #
def test_orthogonalize_strips_dollar_beta():
    """Residual returns have ~0 beta to the broad dollar (that's the whole point)."""
    idx = _idx(1000)
    rng = np.random.default_rng(3)
    dret = pd.Series(rng.normal(0, 0.004, len(idx)), index=idx)
    dollar = np.exp(dret.cumsum()) * 100
    beta_true = -0.6
    base_ret = beta_true * dret + rng.normal(0, 0.005, len(idx))
    base = np.exp(pd.Series(base_ret, index=idx).cumsum())
    resid, beta = FS.orthogonalize(base, dollar, CFG["dollar"])
    e = np.log(resid).diff()
    m = beta.notna() & e.notna()
    var = dret[m].var()
    beta_resid = e[m].cov(dret[m]) / var if var else 0.0
    assert abs(beta_resid) < 0.25, f"residual still loads on the dollar: beta={beta_resid:.3f}"
    # and the rolling beta should recover the true sign (negative)
    assert beta.dropna().median() < 0, "rolling dollar beta should be negative for a USD pair"


def test_carry_sign_and_vol_penalty():
    idx = _idx(800)
    close = pd.Series(np.exp(np.cumsum(np.full(len(idx), 0.0))) , index=idx)  # flat -> low vol
    us = pd.Series(3.0, index=idx)
    hi = pd.Series(5.0, index=idx)     # foreign > US -> positive carry to hold base
    lo = pd.Series(1.0, index=idx)     # foreign < US -> negative carry
    up = FS.carry_signal(hi, us, close, CFG["carry"])
    dn = FS.carry_signal(lo, us, close, CFG["carry"])
    assert up["carry_diff"].iloc[-1] > 0 and up["carry_score"].iloc[-1] > 0
    assert dn["carry_diff"].iloc[-1] < 0 and dn["carry_score"].iloc[-1] < 0
    assert FS.carry_signal(None, us, close, CFG["carry"]).empty


def test_riskoff_factor_archetype_sign():
    """Same global stress -> havens rally (+), risk currencies fall (-)."""
    idx = _idx(300)
    R = pd.Series(0.8, index=idx)       # strong risk-OFF
    haven = FS.riskoff_factor(R, {"archetype": "haven-funder"}, idx)["riskoff"].iloc[-1]
    risk = FS.riskoff_factor(R, {"archetype": "commodity-dollar"}, idx)["riskoff"].iloc[-1]
    assert haven > 0, "haven should be bullish in risk-off"
    assert risk < 0, "risk currency should be bearish in risk-off"
    assert haven == -risk


def test_factor_panel_naive_bullish_bounds():
    idx = _idx(60)
    sig = pd.DataFrame({
        "close": 1.0, "ts_momentum": np.linspace(-2, 2, 60), "structure": np.linspace(2, -2, 60),
        "risk_index": np.linspace(0, 100, 60), "carry_score": np.linspace(-2, 2, 60),
        "rates_score": np.linspace(-2, 2, 60), "value_score": np.linspace(2, -2, 60),
        "riskoff": np.linspace(-2, 2, 60), "pos_pctile": np.linspace(0, 100, 60),
        "shock_z": np.linspace(-4, 4, 60),
    }, index=idx)
    f = FC.factor_panel("EURUSD", sig, {"base": "EUR"})
    assert (f.abs() <= 1.0 + 1e-9).all().all(), "every factor must be naive-bullish in [-1,1]"
    assert {"value", "rates"} <= set(f.columns), "value & rates factors must be in the panel"
    # contrarian positioning: crowded long (high pctile) -> bearish
    assert f["positioning"].iloc[-1] < 0 < f["positioning"].iloc[0]


def test_value_lag_has_no_lookahead():
    """A monthly REER value is only visible AFTER its publication lag (no look-ahead)."""
    from engine.forex_signals import _lag_to_daily
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    reer = pd.Series([100.0, 110.0], index=pd.to_datetime(["2020-06-30", "2020-07-31"]))
    out = _lag_to_daily(reer, idx, 45)
    assert out.loc["2020-08-15"] == 100.0, "the July print (released ~Sep) must not leak into August"
    assert out.loc["2020-09-20"] == 110.0, "after the lag, the July print is visible"


def _sig(close_last, n=700, **cols):
    idx = _idx(n)
    base = {"close": pd.Series(np.linspace(1.0, close_last, n), index=idx)}
    for k, v in cols.items():
        base[k] = pd.Series(v, index=idx)
    return pd.DataFrame(base)


def test_conviction_bounds_action_and_framing():
    sig = _sig(1.1, ts_momentum=0.4, structure=0.3, risk_index=20.0,
               carry_score=0.5, riskoff=0.3, shock_z=0.5, pos_pctile=40.0)
    c = FC.conviction("EURUSD", sig, CFG["assets"]["EURUSD"], calib={})   # un-calibrated path
    assert -100 <= c["score"] <= 100
    assert c["action"] in ("STRONG LONG", "LONG", "FLAT", "SHORT", "STRONG SHORT")
    assert c["framing"] and c["reliable"] is False       # empty calib -> dampened, prior weights
    assert 0.0 <= c["confidence"] <= 1.0


def test_conviction_peg_intervention_caps():
    """USD/JPY (inverted) with the quote inside the MoF watch zone -> |score| capped."""
    meta = {"base": "JPY", "invert": True, "carry": None,
            "peg": {"kind": "intervention", "watch": [150, 162]}}
    sig = _sig(1.0 / 160.0, ts_momentum=-0.9, structure=-0.9, risk_index=10.0,
               carry_score=-0.9, riskoff=-0.6, shock_z=-1.0, pos_pctile=80.0)
    c = FC.conviction("USDJPY", sig, meta)
    assert c["peg"] and c["peg"]["kind"] == "intervention"
    assert abs(c["score"]) <= 40, f"intervention zone must cap conviction, got {c['score']}"


def test_conviction_managed_forces_flat():
    meta = {"base": "CNH", "invert": True, "carry": "context", "peg": {"kind": "managed"}}
    sig = _sig(1.0 / 7.2, ts_momentum=0.9, structure=0.9, risk_index=10.0,
               riskoff=0.6, shock_z=1.0, pos_pctile=20.0)
    c = FC.conviction("USDCNH", sig, meta)
    assert abs(c["score"]) <= 15, "managed regime must flatten the verdict"
    assert "carry" not in [r["key"] for r in c["factors"]], "EM context carry must carry no weight"


def test_em_carry_context_has_no_carry_factor():
    meta = {"base": "MXN", "invert": True, "carry": "context"}
    sig = _sig(1.0 / 17.0, ts_momentum=0.2, structure=0.1, risk_index=30.0,
               carry_score=0.9, riskoff=0.2, shock_z=0.2, pos_pctile=50.0)
    c = FC.conviction("USDMXN", sig, meta)
    assert "carry" not in [r["key"] for r in c["factors"]]


def test_dollar_master_regime_is_valid_and_dir_matches():
    idx = _idx(700)
    rng = np.random.default_rng(5)
    drivers = {
        "broad_dollar": pd.Series(np.exp(np.cumsum(rng.normal(0.0002, 0.003, len(idx)))) * 100, index=idx),
        "dxy": pd.Series(np.exp(np.cumsum(rng.normal(0.0002, 0.004, len(idx)))) * 100, index=idx),
        "vix": pd.Series(18 + np.cumsum(rng.normal(0, 0.2, len(idx))), index=idx).clip(9, 80),
        "hy_oas": pd.Series(3.5 + np.cumsum(rng.normal(0, 0.02, len(idx))), index=idx).clip(2, 12),
        "copper": pd.Series(np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))) * 4, index=idx),
        "gold": pd.Series(np.exp(np.cumsum(rng.normal(0, 0.008, len(idx)))) * 1800, index=idx),
        "spy": pd.Series(np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx)))) * 400, index=idx),
    }
    dm = FS.dollar_master(drivers, CFG)
    last = dm.iloc[-1]
    assert last["smile_regime"] in ("Risk-off haven bid", "US growth premium",
                                    "Global reflation", "US-specific stress", "Neutral")
    assert np.sign(last["dollar_dir"]) == np.sign(last["dollar_roc"]) or pd.isna(last["dollar_roc"])
    assert -1 <= last["risk_off"] <= 1


def test_real_orientation_crosscheck():
    """Canonical base-vs-USD price agrees with the FRED reference (direction sanity).
    Skips offline / before collection."""
    eur = store.read("yahoo", "EURUSD=X")
    dex = store.read("fred", "DEXUSEU")           # USD per EUR — same orientation as EURUSD=X
    if eur is None or dex is None or eur.empty or dex.empty:
        print("  (skipped: store empty)")
        return
    a = eur["close"].rename("y").tail(500)
    b = dex.iloc[:, 0].reindex(a.index).ffill()
    corr = a.corr(b)
    assert corr > 0.9, f"EURUSD vs DEXUSEU should track positively (corr={corr:.2f})"
    # inverted pair: JPY-vs-USD = 1/USDJPY must track 1/DEXJPUS (JPY per USD)
    jpy = store.read("yahoo", "USDJPY=X")
    dexj = store.read("fred", "DEXJPUS")
    if jpy is not None and dexj is not None and not jpy.empty and not dexj.empty:
        ya = (1.0 / jpy["close"]).rename("y").tail(500)
        yb = (1.0 / dexj.iloc[:, 0]).reindex(ya.index).ffill()
        cj = ya.corr(yb)
        assert cj > 0.9, f"JPY-vs-USD (1/USDJPY) vs 1/DEXJPUS should track (corr={cj:.2f})"


def test_calibrate_peg_mask_excises_zones():
    from scripts import calibrate_forex as CAL
    idx = _idx(120)
    close = pd.Series(np.linspace(0.0060, 0.0067, 120), index=idx)   # USD/JPY canonical = 1/quote ~166..149
    meta = {"invert": True, "peg": {"kind": "intervention", "watch": [150, 162]}}
    m = CAL.peg_mask(close, meta)
    quote = 1.0 / close
    inzone = (quote >= 150) & (quote <= 162)
    assert (~m[inzone]).all() and m[~inzone].all(), "intervention zone rows must be excised"
    assert not CAL.peg_mask(close, {"peg": {"kind": "managed"}}).any(), "managed -> all excised"
    assert CAL.peg_mask(close, {}).all(), "no peg -> all kept"


def test_calibrate_pair_signs_inverted_and_normalizes():
    """A factor that negatively predicts forward returns -> INVERTED + negative weight;
    weights normalize to sum|w| = 1."""
    from scripts import calibrate_forex as CAL
    cal = config.load()["forex"]["calibration"]
    idx = pd.date_range("2010-01-01", periods=3200, freq="B")   # spans the 2015 split boundary
    rng = np.random.default_rng(11)
    n = len(idx)
    # persistent AR(1) factor x; future returns are DRIVEN negatively by it, so x[t]
    # robustly anti-predicts forward returns at every horizon (an INVERTED factor).
    x = np.zeros(n)
    e = rng.normal(0, 0.3, n)
    for i in range(1, n):
        x[i] = 0.98 * x[i - 1] + e[i]
    xs = pd.Series(np.tanh(x), index=idx)
    r = (-0.4 * xs.shift(1)).fillna(0.0) + rng.normal(0, 0.002, n)
    close = np.exp(pd.Series(r, index=idx).cumsum())
    sig = pd.DataFrame({"close": close, "ts_momentum": xs, "structure": 0.0,
                        "risk_index": 50.0, "carry_score": 0.0, "riskoff": 0.0,
                        "shock_z": 0.0}, index=idx)
    out = CAL.calibrate_pair("X", sig, {"base": "X", "invert": False}, cal)
    assert abs(sum(abs(w) for w in out["weights"].values()) - 1.0) < 1e-6, "weights must sum-|w| to 1"
    assert out["signals"]["trend"]["verdict"] == "INVERTED"
    assert out["weights"]["trend"] < 0, "INVERTED factor must carry a negative (sign-flipped) weight"


def test_alerts_carry_flip_and_states():
    """A carry differential crossing zero fires a carry_flip; a momentum state flip fires too."""
    from engine import forex_alerts as FA
    idx = _idx(60)
    df = pd.DataFrame({"close": pd.Series(1.1, index=idx),
                       "carry_diff": pd.Series([-1.0] * 30 + [1.0] * 30, index=idx),
                       "momentum_state": ["bear"] * 30 + ["bull"] * 30}, index=idx)
    ev = FA._pair_events("EURUSD", df, {"label": "EUR/USD", "base": "EUR", "invert": False})
    types = [e["type"] for e in ev]
    assert "carry_flip" in types and "momentum" in types
    cf = next(e for e in ev if e["type"] == "carry_flip")
    assert "positive" in cf["headline"].lower()


def test_alerts_peg_approach_fires():
    """The quote entering the MoF intervention watch band fires a peg_approach event."""
    from engine import forex_alerts as FA
    idx = _idx(40)
    quote = pd.Series([145.0] * 20 + [155.0] * 20, index=idx)   # crosses into [150,162]
    df = pd.DataFrame({"close": 1.0 / quote}, index=idx)         # canonical (inverted) price
    meta = {"label": "USD/JPY", "base": "JPY", "invert": True,
            "peg": {"kind": "intervention", "watch": [150, 162]}}
    ev = FA._pair_events("USDJPY", df, meta)
    assert any(e["type"] == "peg_approach" for e in ev)


def test_mtf_runs_on_fx_close():
    """The reused commodity/equity MTF engine produces a ladder on an FX close, no crash."""
    from engine import commodity_mtf
    idx = pd.date_range("2010-01-01", periods=1500, freq="B")
    rng = np.random.default_rng(5)
    close = np.exp(pd.Series(rng.normal(0, 0.005, len(idx)), index=idx).cumsum())
    a = commodity_mtf.mtf_ladder(close)
    assert isinstance(a, dict)
    if a:
        assert "mtf" in a and {"D", "W"} <= set(a["mtf"].keys())


if __name__ == "__main__":
    for fn in [test_orthogonalize_strips_dollar_beta, test_carry_sign_and_vol_penalty,
               test_riskoff_factor_archetype_sign, test_factor_panel_naive_bullish_bounds,
               test_conviction_bounds_action_and_framing, test_conviction_peg_intervention_caps,
               test_conviction_managed_forces_flat, test_em_carry_context_has_no_carry_factor,
               test_dollar_master_regime_is_valid_and_dir_matches, test_real_orientation_crosscheck,
               test_value_lag_has_no_lookahead,
               test_alerts_carry_flip_and_states, test_alerts_peg_approach_fires, test_mtf_runs_on_fx_close,
               test_calibrate_peg_mask_excises_zones, test_calibrate_pair_signs_inverted_and_normalizes]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all forex engine tests passed")
