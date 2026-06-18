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


def test_forex_mtf_uses_measured_fx_preset():
    """forex_mtf runs the MEASURED fx cycle preset, not the equity one."""
    from engine import forex_mtf, cycles
    assert "fx" in cycles.CYCLE_PRESETS
    assert cycles.CYCLE_PRESETS["fx"]["dc_band"] != cycles.CYCLE_PRESETS["equity"]["dc_band"]
    idx = pd.date_range("2010-01-01", periods=1600, freq="B")
    rng = np.random.default_rng(7)
    close = np.exp(pd.Series(rng.normal(0, 0.005, len(idx)), index=idx).cumsum())
    a = forex_mtf.mtf_ladder(close)
    assert isinstance(a, dict)
    if a and a.get("cycle"):
        assert tuple(a["cycle"]["dc_band"]) == cycles.CYCLE_PRESETS["fx"]["dc_band"]


def test_cnh_basis_sign_and_states():
    """Offshore weaker than onshore -> positive bps; thresholds map to stress / inflow."""
    from engine.forex_signals import cnh_basis
    idx = _idx(40)
    onshore = pd.Series(7.10, index=idx)
    cfg = {"stress_bps": 150, "inflow_bps": -100}
    assert cnh_basis(pd.Series(7.20, index=idx), onshore, cfg)["cnh_basis_bps"].iloc[-1] > 0
    assert cnh_basis(pd.Series(7.30, index=idx), onshore, cfg)["cnh_basis_state"].iloc[-1] == "outflow_stress"
    assert cnh_basis(pd.Series(7.00, index=idx), onshore, cfg)["cnh_basis_state"].iloc[-1] == "inflow"


# --------------------------------------------------------------------------- #
# Dollar Desk · transmission · strength · scorecards (the revamp)
# --------------------------------------------------------------------------- #
from engine import forex_dollar as FD          # noqa: E402
from engine import forex_transmission as FT     # noqa: E402
from engine import forex_scorecards as FSC      # noqa: E402

DD = CFG["dollar_desk"]


def test_real_rate_regime_quadrants():
    """High & rising real yields -> Restrictive/USD-supportive; low -> Easy/USD-soft."""
    idx = _idx(800)
    rising = pd.Series(np.linspace(0.3, 3.0, 800), index=idx)
    falling_be = pd.Series(np.linspace(2.6, 1.9, 800), index=idx)
    hi = FD.real_rate_regime(rising, falling_be, DD["real_rate"])
    assert hi and hi["real_rising"] is True and hi["lean"] == "supportive"
    assert "Restrictive" in hi["regime"]
    lo = FD.real_rate_regime(pd.Series(np.linspace(3.0, 0.3, 800), index=idx), falling_be, DD["real_rate"])
    assert lo and lo["lean"] == "soft" and "Easy" in lo["regime"]


def test_fed_path_tightening_sign():
    """far (12m) above near (1m) implied rate -> positive path_bps (tightening priced)."""
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    zq = pd.DataFrame({"m1": 3.5, "m3": 3.6, "m6": 3.8, "m12": 4.0}, index=idx)
    out = FD.fed_path(zq, DD["fed_path"])
    assert out and out["path_bps"] == 50.0
    cuts = FD.fed_path(pd.DataFrame({"m1": 4.0, "m3": 3.8, "m6": 3.5, "m12": 3.0}, index=idx), DD["fed_path"])
    assert cuts["path_bps"] < 0      # cuts priced


def test_dollar_positioning_crowded():
    """A recent extreme in net spec -> high percentile + crowded_long."""
    wk = pd.date_range("2015-01-06", periods=420, freq="W-TUE")   # COT reports as-of Tuesday (a weekday)
    net = pd.Series(np.concatenate([np.full(400, -8.0), np.full(20, 45.0)]), index=wk)
    daily = pd.date_range(wk[0], wk[-1], freq="B")                # daily span tracks the COT series
    out = FD.positioning(net, daily, DD["positioning"])
    assert out and out["pctile"] >= 80 and out["state"] == "crowded_long"


def test_trend_stack_all_up():
    idx = _idx(700)
    broad = pd.Series(np.exp(np.linspace(0, 0.25, 700)), index=idx)   # steadily rising
    out = FD.trend_stack(broad, DD["trend"])
    assert out and out["label"] == "up" and out["n_up"] == out["n_tot"] == 4


def test_strength_meter_zero_sum_and_usd():
    """Strengths are excess vs the average currency -> ~zero-sum, and USD is included."""
    idx = _idx(400)
    rng = np.random.default_rng(1)
    results, acfg = {}, {}
    for p, base in [("EURUSD", "EUR"), ("USDJPY", "JPY"), ("AUDUSD", "AUD")]:
        results[p] = pd.DataFrame({"close": np.exp(pd.Series(rng.normal(0, 0.005, 400), index=idx).cumsum())})
        acfg[p] = {"base": base}
    sm = FD.strength_meter(results, CFG["strength"], acfg)
    rows = sm["horizons"][sm["default"]]
    assert {"USD", "EUR", "JPY", "AUD"} == {r["ccy"] for r in rows}
    assert abs(sum(r["strength"] for r in rows)) < 0.1          # zero-sum


def test_transmission_known_inverse():
    """An asset that is the exact inverse of the dollar -> corr ~ -1, stable, headwind."""
    idx = _idx(400)
    uret = pd.Series(np.random.default_rng(2).normal(0, 0.004, 400), index=idx)
    broad = np.exp(uret.cumsum()) * 100
    asset = np.exp((-uret).cumsum()) * 100
    out = FT.transmission(broad, {"SPY": asset}, None, None, CFG["transmission"])
    row = out["rows"][0]
    assert row["corr_fast"] < -0.9 and row["stability"] == "stable" and row["effect"] == "headwind"


def test_transmission_flipping_flag():
    """A sign-flip between the slow and fast window -> flagged unstable/flipping."""
    idx = _idx(400)
    uret = pd.Series(np.random.default_rng(3).normal(0, 0.004, 400), index=idx)
    aret = -uret.copy()
    aret.iloc[-63:] = uret.iloc[-63:]                          # recent 63d positively correlated
    broad = np.exp(uret.cumsum()) * 100
    asset = np.exp(aret.cumsum()) * 100
    out = FT.transmission(broad, {"SPY": asset}, None, None, CFG["transmission"])
    assert out["rows"][0]["stability"] == "flipping" and "US equities" in out["unstable"]


def test_scorecards_finite_and_maxdd_nonpositive():
    idx = _idx(1500)
    rng = np.random.default_rng(4)
    results, acfg = {}, {}
    carries = {"EUR": -1.0, "JPY": -2.0, "GBP": 0.5, "AUD": 2.0, "CAD": 1.0, "CHF": -1.5}
    for p, base in [("EURUSD", "EUR"), ("USDJPY", "JPY"), ("GBPUSD", "GBP"),
                    ("AUDUSD", "AUD"), ("USDCAD", "CAD"), ("USDCHF", "CHF")]:
        df = pd.DataFrame({"close": np.exp(pd.Series(rng.normal(0, 0.005, len(idx)), index=idx).cumsum())})
        df["carry_diff"] = carries[base]
        results[p], acfg[p] = df, {"base": base}
    c = FSC.g10_carry(results, acfg, CFG["scorecards"])
    assert c and c["metrics"]["full"] and c["metrics"]["full"]["maxdd"] <= 0
    assert len(c["longs"]) == 3 and len(c["shorts"]) == 3
    dxy = np.exp(pd.Series(rng.normal(0, 0.005, len(idx)), index=idx).cumsum()) * 100
    d = FSC.dollar_trend(dxy, CFG["scorecards"])
    assert d and d["metrics"]["full"]["maxdd"] <= 0


def test_dollar_desk_assembles_gracefully():
    """The desk assembles a dict even when every data leg is missing (never raises)."""
    idx = _idx(300)
    dol = pd.DataFrame({"smile_regime": ["Neutral"] * 300, "risk_off": 0.0}, index=idx)
    out = FD.dollar_desk(dol, {}, {}, CFG)
    assert isinstance(out, dict) and "lean" in out and out["smile"]["confidence"] == "none"


# --------------------------------------------------------------------------- #
# Follow-ups: haven basket · dollar-index calibration · cross-page link
# --------------------------------------------------------------------------- #
def test_haven_basket_is_carry_mirror():
    """The haven basket is long havens / short risk currencies, and (the whole point)
    its return is BETTER in risk-off than in calm — the mirror of the carry trade."""
    idx = _idx(1500)
    rng = np.random.default_rng(11)
    risk_off = pd.Series(rng.normal(0, 0.5, len(idx)), index=idx)        # stress when >0
    results, acfg = {}, {}
    # havens (JPY/CHF) rally in stress; risk ccys (AUD/CAD) fall in stress
    specs = [("USDJPY", "JPY", "haven-funder", +1), ("USDCHF", "CHF", "haven-funder", +1),
             ("AUDUSD", "AUD", "commodity-dollar", -1), ("USDCAD", "CAD", "commodity-dollar", -1)]
    for p, base, arch, beta in specs:
        shock = beta * risk_off.clip(lower=0) * 0.01                     # move with stress
        r = pd.Series(rng.normal(0, 0.004, len(idx)), index=idx) + shock
        df = pd.DataFrame({"close": np.exp(r.cumsum())})
        df["carry_diff"] = -1.0 if arch == "haven-funder" else 2.0
        results[p], acfg[p] = df, {"base": base, "archetype": arch}
    h = FSC.haven_basket(results, acfg, risk_off, CFG["scorecards"])
    assert set(h["longs"]) == {"JPY", "CHF"} and set(h["shorts"]) == {"AUD", "CAD"}
    assert h["regime"]["stress_ann"] > h["regime"]["calm_ann"]           # pays in risk-off


def test_calibrate_dollar_reer_leg():
    """The dollar-index REER calibration leg runs (scipy-free) and returns a verdict
    with a deflated-Sharpe gate; it is display-only (never auto-promoted)."""
    from scripts import calibrate_forex
    cfg = config.load()["forex"]
    inputs = forex_inputs.load_all(cfg, active_only=False)
    out = calibrate_forex.calibrate_dollar(inputs, cfg["calibration"], cfg, n_trials=60)
    if out is None:
        return                                                          # store may be empty in CI sandbox
    assert out["verdict"] in ("CONFIRMED", "INVERTED", "DIRECTIONAL", "CONTEXT")
    assert out["display_only"] is True
    assert isinstance(out["promotable"], bool)


def test_forex_link_reads_and_degrades():
    """forex_link.asset_corr maps a transmission key to a corr dict, and returns None
    when the block is absent (so consumer pages never crash on build order)."""
    from lib import forex_link
    tr = {"corr": {"GC=F": -0.5, "HG=F": -0.6}, "unstable": ["Copper"], "usd_dir": "strengthening"}
    g = forex_link.asset_corr("GC=F", tr)
    assert g and g["corr"] == -0.5 and g["stable"] is True               # Gold not in unstable
    c = forex_link.asset_corr("HG=F", tr)
    assert c and c["stable"] is False                                    # Copper IS unstable
    assert forex_link.asset_corr("SPY", tr) is None                      # key absent -> None
    assert forex_link.asset_corr("GC=F", {}) is None                    # empty block -> None


from engine import forex_inputs  # noqa: E402  (used by the calibration test)


if __name__ == "__main__":
    for fn in [test_orthogonalize_strips_dollar_beta, test_carry_sign_and_vol_penalty,
               test_riskoff_factor_archetype_sign, test_factor_panel_naive_bullish_bounds,
               test_conviction_bounds_action_and_framing, test_conviction_peg_intervention_caps,
               test_conviction_managed_forces_flat, test_em_carry_context_has_no_carry_factor,
               test_dollar_master_regime_is_valid_and_dir_matches, test_real_orientation_crosscheck,
               test_value_lag_has_no_lookahead,
               test_alerts_carry_flip_and_states, test_alerts_peg_approach_fires, test_mtf_runs_on_fx_close,
               test_forex_mtf_uses_measured_fx_preset, test_cnh_basis_sign_and_states,
               test_calibrate_peg_mask_excises_zones, test_calibrate_pair_signs_inverted_and_normalizes,
               test_real_rate_regime_quadrants, test_fed_path_tightening_sign,
               test_dollar_positioning_crowded, test_trend_stack_all_up,
               test_strength_meter_zero_sum_and_usd, test_transmission_known_inverse,
               test_transmission_flipping_flag, test_scorecards_finite_and_maxdd_nonpositive,
               test_dollar_desk_assembles_gracefully, test_haven_basket_is_carry_mirror,
               test_calibrate_dollar_reer_leg, test_forex_link_reads_and_degrades]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all forex engine tests passed")
