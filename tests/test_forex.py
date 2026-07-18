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


# --------------------------------------------------------------------------- #
# F2 — _spark_pts unit tests
# --------------------------------------------------------------------------- #
def test_spark_pts_normalises_into_viewbox():
    from scripts.build_forex import _spark_pts
    # 10 values linearly spaced 0..1 -> y should span [pad, h-pad] = [2, 34] for h=36
    vals = list(np.linspace(0.0, 1.0, 10))
    pts = _spark_pts(vals, 300, 36, n=126)
    assert pts, "_spark_pts returned empty for valid input"
    coords = [tuple(float(c) for c in p.split(",")) for p in pts.split()]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    # x must span 0 .. w
    assert xs[0] == 0.0 and xs[-1] == 300.0, f"x range wrong: {xs[0]} .. {xs[-1]}"
    # y is inverted: min value (0.0) -> bottom (h - pad = 34), max value (1.0) -> top (pad = 2)
    assert ys[-1] == pytest.approx(2.0, abs=0.2), f"max value y wrong: {ys[-1]}"
    assert ys[0] == pytest.approx(34.0, abs=0.2), f"min value y wrong: {ys[0]}"
    # all y within [pad, h-pad]
    assert all(2.0 - 0.1 <= y <= 34.0 + 0.1 for y in ys), f"y out of bounds: {ys}"


def test_spark_pts_empty_on_insufficient_points():
    from scripts.build_forex import _spark_pts
    assert _spark_pts([], 300, 36) == "", "empty input should return empty string"
    assert _spark_pts([1.0], 300, 36) == "", "single point should return empty string"
    assert _spark_pts([float("nan"), float("nan")], 300, 36) == "", "all-NaN should return empty"


def test_spark_pts_flat_series():
    from scripts.build_forex import _spark_pts
    # constant series -> all y mid-point
    pts = _spark_pts([5.0] * 20, 100, 20, n=126)
    assert pts, "constant series should produce points"
    ys = [float(p.split(",")[1]) for p in pts.split()]
    assert all(abs(y - 10.0) < 0.2 for y in ys), f"constant series y should be mid-point: {ys[:3]}"


def test_spark_pts_respects_n_tail():
    from scripts.build_forex import _spark_pts
    # 200 values but n=50 -> only 50 used
    vals = list(range(200))
    pts_50 = _spark_pts(vals, 100, 20, n=50)
    pts_200 = _spark_pts(vals, 100, 20, n=200)
    n_50 = len(pts_50.split())
    n_200 = len(pts_200.split())
    assert n_50 == 50, f"expected 50 points for n=50, got {n_50}"
    assert n_200 == 200, f"expected 200 points for n=200, got {n_200}"


import pytest  # noqa: E402 — placed here to avoid top-level scope pollution in the existing file


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
    from engine.trial_ledger import TrialLedger
    import tempfile
    import os
    cfg = config.load()["forex"]
    inputs = forex_inputs.load_all(cfg, active_only=False)
    with tempfile.TemporaryDirectory() as _td:   # don't pollute the real data/trial_ledger.jsonl
        led = TrialLedger(os.path.join(_td, "t.jsonl"))
        out = calibrate_forex.calibrate_dollar(inputs, cfg["calibration"], cfg, n_trials=60, ledger=led)
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
from engine import forex_regime as RG  # noqa: E402


# --------------------------------------------------------------------------- #
# FX Stress & Regime Radar (engine/forex_regime.py)
# --------------------------------------------------------------------------- #
def test_regime_z_causal_excludes_t():
    """_z_causal moments are shift(1)-ed: a spike at the LAST bar cannot change z at
    any earlier bar (strictly leak-free)."""
    idx = _idx(420)
    rng = np.random.default_rng(0)
    g = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    z1 = RG._z_causal(g, 252, 60)
    g2 = g.copy()
    g2.iloc[-1] += 50.0
    z2 = RG._z_causal(g2, 252, 60)
    a, b = z1.iloc[:-1], z2.iloc[:-1]
    m = a.notna() & b.notna()
    assert m.any() and np.allclose(a[m].values, b[m].values)


def test_regime_forward_label_leak_free():
    """_fwd_drawdown looks only into (t, t+N]; the current bar is excluded and the last
    N bars have no realized window (-> NaN via _mask_tail)."""
    idx = _idx(100)
    s = pd.Series(np.ones(len(idx)), index=idx)
    s.iloc[60] = 0.5                                  # a one-day -50% dip at t=60
    dd = RG._fwd_drawdown(s, 5)
    assert dd.iloc[59] < -0.4                         # window t60..t64 sees the dip
    assert dd.iloc[55] < -0.4                         # window t56..t60 sees the dip
    assert dd.iloc[54] > -0.4                         # window t55..t59 excludes t60
    assert dd.iloc[60] > -0.4                         # the dip is the CURRENT denominator, not a forward drawdown
    y = RG._mask_tail(dd <= -0.4, s, 5)
    assert pd.isna(y.iloc[-1]) and pd.isna(y.iloc[-4])  # last N bars unrealized
    assert y.iloc[59] == 1.0 and y.iloc[54] == 0.0


def test_regime_probability_wilson_neff_semantics():
    """n_eff == n_raw/N; Wilson CI brackets p_cond within [0,1]; conditioning on high
    intensity lifts the rate vs the unconditional base (by construction)."""
    idx = _idx(2200)
    rng = np.random.default_rng(1)
    inten = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
    y = (rng.uniform(0, 1, len(idx)) < inten * 0.5).astype(float)
    y.iloc[-10:] = np.nan
    inten.iloc[-1] = 0.3                              # moderate -> large conditional set, status ok
    p = RG.scenario_probability(inten, y, 10, n_min=9)
    assert p["status"] == "ok"
    assert abs(p["n_eff"] - round(p["n_raw"] / 10, 1)) < 0.11
    assert 0 <= p["wilson_lo"] <= p["p_cond"] <= p["wilson_hi"] <= 1
    assert 0 <= p["base_rate"] <= 1
    assert p["p_cond"] >= p["base_rate"] - 0.03      # positive (or ~0) lift by construction
    assert isinstance(p["ci_separated"], bool)


def test_regime_probability_suppression_statuses():
    """n_raw<=2 -> 'unprecedented'; all-NaN intensity -> 'building'; the % is suppressed."""
    idx = _idx(2200)
    rng = np.random.default_rng(2)
    inten = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
    y = pd.Series((rng.uniform(0, 1, len(idx)) < 0.1).astype(float), index=idx)
    y.iloc[-20:] = np.nan
    inten.iloc[-1] = 5.0                              # above all history -> n_raw<=2
    p = RG.scenario_probability(inten, y, 20)
    assert p["status"] == "unprecedented" and p["p_cond"] is None
    p2 = RG.scenario_probability(pd.Series(np.nan, index=idx), y, 20)
    assert p2["status"] == "building"


def test_regime_wilson_bounds():
    lo, hi = RG._wilson(0.5, 20)
    assert 0 <= lo < 0.5 < hi <= 1
    nan_lo, _ = RG._wilson(0.5, 0)                    # n<=0 -> NaN, never crashes
    assert nan_lo != nan_lo


def test_regime_never_scored_isolation():
    """The radar is display-only: the scored engines must not import forex_regime."""
    import inspect
    from engine import forex_conviction, forex_scorecards
    for mod in (forex_conviction, forex_scorecards):
        assert "forex_regime" not in inspect.getsource(mod)


def test_regime_end_to_end_real_store():
    """Full radar on the real store (skips if empty): bounded intensities, valid
    probability statuses, the active gate matches min_legs, and dol<300 -> {}."""
    cfg = config.load()["forex"]
    inputs = forex_inputs.load_all(cfg)
    if not inputs:
        return
    res = FS.compute_all(inputs, cfg)
    dol = res.get("_dollar")
    if dol is None or dol.empty:
        return
    drivers = dict(next(iter(inputs.values()))["drivers"])
    reg = RG.fx_stress_regime(res, dol, drivers, cfg)
    assert reg and len(reg["scenarios"]) >= 5
    for s in reg["scenarios"]:
        assert 0 <= s["intensity_today"] <= 100
        assert s["active"] == (s["n_fired"] >= s["min_legs"])    # gate is exactly min_legs
        assert s["prob"]["status"] in ("ok", "insufficient", "unprecedented", "building")
        if s["prob"]["status"] == "ok":
            assert s["prob"]["n_eff"] == round(s["prob"]["n_raw"] / s["prob"]["N"], 1)
        for leg in s["fired_legs"]:
            assert leg["value"] is None or -1 <= leg["value"] <= 1
    kin = RG.fx_kinematics_table(res, drivers, cfg)
    assert kin and len(kin["rows"]) >= 5
    assert all(r["vel_z"] is None or np.isfinite(r["vel_z"]) for r in kin["rows"])
    assert RG.fx_stress_regime(res, dol.iloc[:50], drivers, cfg) == {}   # too few rows -> {}


def test_regime_missing_drivers_degrades():
    """Dropping MOVE / EM_OAS / EEM / VIX / SPY still returns scenarios (legs
    renormalize over the present ones); never raises."""
    cfg = config.load()["forex"]
    inputs = forex_inputs.load_all(cfg)
    if not inputs:
        return
    res = FS.compute_all(inputs, cfg)
    dol = res.get("_dollar")
    if dol is None or dol.empty:
        return
    drivers = dict(next(iter(inputs.values()))["drivers"])
    for k in ("move", "em_oas", "eem", "vix", "spy"):
        drivers.pop(k, None)
    reg = RG.fx_stress_regime(res, dol, drivers, cfg)
    assert reg and reg["scenarios"]


# ===========================================================================
# B1.7 NEW TESTS — latest.json contract, stance map, alert families, smile x
# ===========================================================================

def test_desk_latest_includes_smile_decomp():
    """_desk_latest now exports smile_decomp when present (B1.1 — fixes silent None bug)."""
    from scripts.build_forex import _desk_latest
    desk = {
        "lean": "supportive", "lean_zh": "偏多美元", "lean_net": 2, "lean_n": 4,
        "smile_decomp": {
            "regime": "US growth premium", "regime_60d": "Neutral",
            "safety_bid_today": False, "beta": 0.42, "r2": 0.18, "residual_20d_z": 1.1,
        },
        "smile": {"confidence": "medium", "triple_red": False},
    }
    out = _desk_latest(desk)
    assert "smile_decomp" in out
    sd = out["smile_decomp"]
    assert sd["regime"] == "US growth premium"
    assert sd["beta"] == 0.42
    assert sd["r2"] == 0.18


def test_desk_latest_backward_compat():
    """Keys from the old _desk_latest contract are still present (regression fence)."""
    from scripts.build_forex import _desk_latest
    desk = {
        "lean": "soft", "lean_zh": "偏空美元", "lean_net": -1, "lean_n": 3,
        "real_rate": {"regime": "Restrictive & Rising", "real_z": 1.4, "regime_zh": "限制性上升"},
        "fed_path": {"path_bps": -50.0, "lean": "dovish_repricing"},
        "positioning": {"pctile": 30.0, "state": "neutral"},
        "valuation": {"gap_pct": -3.5, "label": "cheap"},
        "trend": {"label": "up", "n_up": 4},
        "liquidity": {"dir": "soft"},
        "smile": {"confidence": "low", "triple_red": False},
    }
    out = _desk_latest(desk)
    for key in ("lean", "lean_zh", "lean_net", "lean_n", "real_rate_regime",
                "fed_path_bps", "usd_pos_pctile", "usd_reer_gap_pct",
                "trend", "trend_n_up", "liquidity_dir", "smile_confidence", "triple_red"):
        assert key in out, f"old key '{key}' missing from _desk_latest output"


def test_transmission_latest_includes_assets():
    """_transmission_latest now includes per-asset effect/stability (B1.1)."""
    from scripts.build_forex import _transmission_latest
    tr = {
        "usd_dir": "strengthening",
        "rows": [
            {"key": "GC=F", "corr_fast": -0.55, "corr_slow": -0.48,
             "effect": "headwind", "stability": "stable"},
            {"key": "SPY", "corr_fast": 0.3, "corr_slow": 0.25,
             "effect": "tailwind", "stability": "flipping"},
        ],
        "headwind_for": ["gold"], "tailwind_for": ["US stocks"], "unstable": [],
        "as_of": "2026-07-18",
    }
    out = _transmission_latest(tr)
    assert "assets" in out
    assert "GC=F" in out["assets"]
    assert out["assets"]["GC=F"]["effect"] == "headwind"
    assert out["assets"]["SPY"]["stability"] == "flipping"
    # Old keys still present
    assert "usd_dir" in out and "corr" in out and "headwind_for" in out


def test_stance_all_branches():
    """_stance returns fixed vocab words + ZH + all three tone branches (B1.3)."""
    from scripts.build_forex import _stance
    KNOWN_WORDS = {"Get ready", "Watch — don't chase"}
    KNOWN_ZH = {"做好准备", "观望，别追"}
    KNOWN_TONES = {"alert", "watch", "calm"}
    # alert branch: active scenarios
    s1 = _stance("up", ["carry_unwind"], False, False, "risk-off")
    assert s1["word_en"] == "Get ready"
    assert s1["word_zh"] == "做好准备"
    assert s1["tone"] == "alert"
    assert s1["headline_en"] and s1["headline_zh"]
    assert s1["sentence_en"] and s1["sentence_zh"]
    # alert branch: triple_red
    s2 = _stance("down", [], False, True, "risk-off")
    assert s2["tone"] == "alert"
    # watch branch: dollar_day_flag, no active
    s3 = _stance("up", [], True, False, "risk-on")
    assert s3["word_en"] == "Watch — don't chase"
    assert s3["tone"] == "watch"
    # calm branch: nothing active
    s4 = _stance("down", [], False, False, "risk-on")
    assert s4["word_en"] == "Watch — don't chase"
    assert s4["tone"] == "calm"
    for s in (s1, s2, s3, s4):
        assert s["word_en"] in KNOWN_WORDS
        assert s["word_zh"] in KNOWN_ZH
        assert s["tone"] in KNOWN_TONES
        # headline maps
        assert s["headline_en"] in ("Dollar strong", "Dollar soft", "Dollar mixed")
        assert s["headline_zh"] in ("美元偏强", "美元偏弱", "美元分化")


def test_stance_sentence_plain_words():
    """Stance sentence uses plain asset names from B1.5, not ticker strings."""
    from scripts.build_forex import _stance
    s = _stance("strengthening", [], False, False, "risk-off",
                headwind_for=["GC=F", "SPY"], tailwind_for=[])
    # sentence must contain plain English names, not ticker strings
    assert "GC=F" not in s["sentence_en"]
    assert "SPY" not in s["sentence_en"]
    assert "gold" in s["sentence_en"].lower() or "US stocks" in s["sentence_en"]


def test_stance_sentence_zh_no_ascii_when_headwinds():
    """P3: ZH sentence must contain no [A-Za-z] when headwinds present."""
    import re
    from scripts.build_forex import _stance
    # ticker keys
    s1 = _stance("strengthening", [], False, False, "risk-off",
                 headwind_for=["SPY", "EEM"], tailwind_for=[])
    assert not re.search(r'[A-Za-z]', s1["sentence_zh"]), \
        f"ZH sentence has ASCII: {s1['sentence_zh']!r}"
    # transmission label keys
    s2 = _stance("strengthening", [], False, False, "risk-off",
                 headwind_for=["US equities", "EM equities"], tailwind_for=[])
    assert not re.search(r'[A-Za-z]', s2["sentence_zh"]), \
        f"ZH sentence has ASCII: {s2['sentence_zh']!r}"
    # Gold key
    s3 = _stance("weakening", [], False, False, "risk-on",
                 headwind_for=[], tailwind_for=["GC=F"])
    assert not re.search(r'[A-Za-z]', s3["sentence_zh"]), \
        f"ZH tailwind sentence has ASCII: {s3['sentence_zh']!r}"


def test_trend_map_plain_words():
    """m5: n_up→plain label mapping tests the REAL Python maps from build_forex, not
    a local copy — so a template/script divergence would fail this test."""
    from scripts.build_forex import TREND_LABEL_EN, TREND_LABEL_ZH
    expected = {
        4: ("Rising on all horizons", "全线上行"),
        3: ("Mostly rising", "大多上行"),
        2: ("Mixed", "涨跌互现"),
        1: ("Mostly falling", "大多下行"),
        0: ("Falling on all horizons", "全线下行"),
    }
    for n, (en, zh) in expected.items():
        assert TREND_LABEL_EN[n] == en, f"TREND_LABEL_EN[{n}] mismatch: {TREND_LABEL_EN[n]!r} != {en!r}"
        assert TREND_LABEL_ZH[n] == zh, f"TREND_LABEL_ZH[{n}] mismatch: {TREND_LABEL_ZH[n]!r} != {zh!r}"
    # Coverage: all 5 values present
    assert set(TREND_LABEL_EN.keys()) == {0, 1, 2, 3, 4}
    assert set(TREND_LABEL_ZH.keys()) == {0, 1, 2, 3, 4}


def test_scenario_events_fire_on_active():
    """scenario_events produces bilingual events for active scenarios (B1.2)."""
    from engine.forex_alerts import scenario_events
    regime = {
        "as_of": "2026-07-18",
        "scenarios": [
            {"key": "carry_unwind", "name_en": "Carry-trade unwind", "name_zh": "套息平仓",
             "active": True, "n_fired": 3, "min_legs": 2,
             "intensity_today": 72.0, "illustrative": False},
            {"key": "reflation_risk_on", "name_en": "Risk-on rally", "name_zh": "风险偏好回升",
             "active": False, "n_fired": 1, "min_legs": 2,
             "intensity_today": 20.0, "illustrative": False},
        ],
    }
    evs = scenario_events(regime)
    assert len(evs) == 1  # only active one fires
    e = evs[0]
    assert e["type"] == "scenario"
    assert e["severity"] == "high"
    assert "Carry-trade unwind" in e["headline"] or "carry" in e["headline"].lower()
    assert e["headline_zh"]  # bilingual
    assert "套息" in e["headline_zh"] or "激活" in e["headline_zh"]


def test_dollar_flash_events_fire_on_threshold():
    """dollar_flash_events fires when dollar_day_z transitions to >= 2.0 (B1.2)."""
    from engine.forex_alerts import dollar_flash_events
    idx = _idx(60)
    # first 30 normal, last 30 flash
    dollar_day_z = pd.Series([0.8] * 30 + [2.5] * 30, index=idx)
    dol = pd.DataFrame({"dollar_day_z": dollar_day_z, "dollar_roc": 0.005}, index=idx)
    evs = dollar_flash_events(dol)
    assert len(evs) >= 1
    e = evs[0]
    assert e["type"] == "dollar_flash"
    assert e["severity"] == "high"
    assert e["headline_zh"]  # bilingual
    assert "异常" in e["headline_zh"] or "波动" in e["headline_zh"]


def test_transmission_shift_events_fire_on_change():
    """transmission_shift_events fires when effect changes between two transmission dicts (B1.2)."""
    from engine.forex_alerts import transmission_shift_events
    tr_prev = {
        "rows": [{"key": "GC=F", "effect": "tailwind", "stability": "stable"}],
        "as_of": "2026-07-17",
    }
    tr_now = {
        "rows": [{"key": "GC=F", "effect": "headwind", "stability": "stable"}],
        "as_of": "2026-07-18",
    }
    evs = transmission_shift_events(tr_now, tr_prev)
    assert len(evs) == 1
    e = evs[0]
    assert e["type"] == "transmission_shift"
    assert e["severity"] == "medium"
    assert "Gold" in e["headline"] or "gold" in e["headline"].lower()
    assert e["headline_zh"] and "黄金" in e["headline_zh"]


def test_scenario_concurrent_activations_distinct_ids():
    """m6(a): Two concurrent active scenarios survive dedup as two distinct event ids (M1 fix).

    Before M1: both got id …:active, so dedup collapsed them to one.
    After M1: id includes the scenario key → both survive.
    """
    from engine.forex_alerts import scenario_events
    regime = {
        "as_of": "2026-07-18",
        "scenarios": [
            {"key": "carry_unwind", "active": True, "n_fired": 3, "min_legs": 2,
             "intensity_today": 70.0},
            {"key": "haven_flight_risk_off", "active": True, "n_fired": 2, "min_legs": 2,
             "intensity_today": 55.0},
        ],
    }
    # No prev_active → both are new activations
    evs = scenario_events(regime, prev_active=set())
    assert len(evs) == 2, f"Expected 2 distinct events, got {len(evs)}"
    ids = [e["id"] for e in evs]
    assert len(set(ids)) == 2, f"Event ids not distinct: {ids}"
    # Each id must contain the scenario key
    assert any("carry_unwind" in eid for eid in ids)
    assert any("haven_flight_risk_off" in eid for eid in ids)


def test_scenario_unchanged_active_emits_no_event():
    """m6(b): If the active set is unchanged (same keys prev and now), no new event fires (M3 fix).

    Before M3: scenario_events fired EVERY day a scenario stayed active (date-bucketed id).
    After M3: only edges (inactive→active, active→inactive) emit events.
    """
    from engine.forex_alerts import scenario_events
    regime = {
        "as_of": "2026-07-18",
        "scenarios": [
            {"key": "carry_unwind", "active": True, "n_fired": 3, "min_legs": 2,
             "intensity_today": 70.0},
        ],
    }
    # prev_active already includes carry_unwind → no edge → no event
    evs = scenario_events(regime, prev_active={"carry_unwind"})
    assert len(evs) == 0, f"Expected 0 events (no edge), got {len(evs)}: {[e['id'] for e in evs]}"


def test_scenario_deactivation_emits_info_event():
    """m6(c): A scenario that was active but is now inactive emits a severity=info event (M3 fix)."""
    from engine.forex_alerts import scenario_events
    regime = {
        "as_of": "2026-07-18",
        "scenarios": [
            {"key": "carry_unwind", "active": False, "n_fired": 1, "min_legs": 2,
             "intensity_today": 20.0},
        ],
    }
    # prev_active: carry_unwind was active yesterday → deactivation edge
    evs = scenario_events(regime, prev_active={"carry_unwind"})
    assert len(evs) == 1, f"Expected 1 deactivation event, got {len(evs)}"
    e = evs[0]
    assert e["severity"] == "info", f"Deactivation must be info severity, got {e['severity']!r}"
    assert e["type"] == "scenario"
    assert "no longer active" in e["headline"] or "解除" in e["headline_zh"]


def test_transmission_shift_concurrent_distinct_ids():
    """m6(a) for transmission: two assets shifting simultaneously keep distinct event ids (M2 fix)."""
    from engine.forex_alerts import transmission_shift_events
    tr_prev = {
        "rows": [
            {"key": "GC=F", "effect": "tailwind", "stability": "stable"},
            {"key": "SPY", "effect": "neutral", "stability": "stable"},
        ],
        "as_of": "2026-07-17",
    }
    tr_now = {
        "rows": [
            {"key": "GC=F", "effect": "headwind", "stability": "stable"},
            {"key": "SPY", "effect": "headwind", "stability": "stable"},
        ],
        "as_of": "2026-07-18",
    }
    evs = transmission_shift_events(tr_now, tr_prev)
    assert len(evs) == 2, f"Expected 2 distinct shift events, got {len(evs)}"
    ids = [e["id"] for e in evs]
    assert len(set(ids)) == 2, f"Shift ids not distinct: {ids}"


def test_smile_x_mapping_anchors():
    """m5: smile x anchors tested against the REAL Python map from build_forex — not a
    local copy — so any divergence between source and test is caught immediately."""
    from scripts.build_forex import SMILE_X
    for regime, x in SMILE_X.items():
        assert 0.0 <= x <= 1.0, f"{regime}: x={x} out of range"
    assert SMILE_X["US growth premium"] == 0.13
    assert SMILE_X["Risk-off haven bid"] == 0.87
    assert SMILE_X["Global reflation"] == SMILE_X["Neutral"] == 0.50
    # All spec regimes present
    for r in ("US growth premium", "US-specific stress", "Global reflation",
              "Neutral", "Risk-off haven bid"):
        assert r in SMILE_X, f"SMILE_X missing regime {r!r}"


def test_alert_timeline_sorted_ts_desc():
    """compute_all_events returns events sorted ts DESC across all assets (B1.2 fix)."""
    from engine.forex_alerts import compute_all_events
    # minimal results with two pairs and a dollar frame
    idx_a = pd.date_range("2024-01-01", periods=400, freq="B")
    idx_b = pd.date_range("2024-01-01", periods=350, freq="B")
    rng = np.random.default_rng(42)
    results = {
        "EURUSD": pd.DataFrame({
            "close": np.exp(pd.Series(rng.normal(0, 0.005, 400), index=idx_a).cumsum()),
            "carry_diff": pd.Series([-1.0]*200 + [1.0]*200, index=idx_a),
        }),
        "USDJPY": pd.DataFrame({
            "close": np.exp(pd.Series(rng.normal(0, 0.005, 350), index=idx_b).cumsum()),
            "carry_diff": pd.Series([1.0]*175 + [-1.0]*175, index=idx_b),
        }),
        "_dollar": pd.DataFrame({
            "smile_regime": ["Neutral"]*350 + ["Risk-off haven bid"]*50,
        }, index=idx_a[:400]),
    }
    evs = compute_all_events(results)
    if len(evs) >= 2:
        tss = [e["ts"] for e in evs]
        assert tss == sorted(tss, reverse=True), "events not sorted ts DESC"


def test_latest_json_old_keys_unchanged():
    """m4: Old latest.json keys survive additive expansion — tested via the REAL export
    helpers (_desk_latest, _transmission_latest, _stance) with synthetic inputs rather
    than an inert dict-vs-itself check.
    """
    from scripts.build_forex import _desk_latest, _transmission_latest, _stance

    # --- _desk_latest with synthetic desk ---
    desk = {
        "lean": "supportive", "lean_zh": "偏多美元", "lean_net": 2, "lean_n": 4,
        "real_rate": {"regime": "Restrictive & Rising", "real_z": 1.4, "regime_zh": "限制性上升"},
        "fed_path": {"path_bps": -50.0, "lean": "dovish_repricing"},
        "positioning": {"pctile": 30.0, "state": "neutral"},
        "valuation": {"gap_pct": -3.5, "label": "cheap"},
        "trend": {"label": "up", "n_up": 4},
        "liquidity": {"dir": "soft"},
        "smile": {"confidence": "medium", "triple_red": True},
        "smile_decomp": {
            "regime": "US growth premium", "regime_60d": "Neutral",
            "safety_bid_today": False, "beta": 0.42, "r2": 0.18, "residual_20d_z": 1.1,
        },
    }
    dl = _desk_latest(desk)
    # Old keys must still be present
    for key in ("lean", "lean_zh", "lean_net", "lean_n", "real_rate_regime",
                "fed_path_bps", "usd_pos_pctile", "usd_reer_gap_pct",
                "trend", "trend_n_up", "liquidity_dir", "smile_confidence", "triple_red"):
        assert key in dl, f"_desk_latest missing old key '{key}'"
    # New key must also be present
    assert "smile_decomp" in dl, "_desk_latest missing new key 'smile_decomp'"
    assert dl["smile_decomp"]["regime"] == "US growth premium"
    assert dl["triple_red"] is True   # reads from smile block (correct path)

    # --- _transmission_latest with synthetic transmission ---
    tr = {
        "usd_dir": "strengthening",
        "rows": [
            {"key": "GC=F", "corr_fast": -0.55, "corr_slow": -0.48,
             "effect": "headwind", "stability": "stable"},
            {"key": "SPY", "corr_fast": 0.3, "corr_slow": 0.25,
             "effect": "tailwind", "stability": "flipping"},
        ],
        "headwind_for": ["gold"], "tailwind_for": ["US stocks"], "unstable": [],
        "as_of": "2026-07-18",
    }
    tl = _transmission_latest(tr)
    # Old keys
    for key in ("usd_dir", "corr", "headwind_for", "tailwind_for", "unstable"):
        assert key in tl, f"_transmission_latest missing old key '{key}'"
    # New key
    assert "assets" in tl, "_transmission_latest missing new key 'assets'"
    assert tl["assets"]["GC=F"]["effect"] == "headwind"
    assert tl["assets"]["SPY"]["stability"] == "flipping"

    # --- _stance: all branches return correct keys ---
    for (args, expected_word_en, expected_tone) in [
        ({"dollar_dir": "up", "active_scenarios": ["carry_unwind"], "dollar_day_flag": False,
          "triple_red": False, "risk_word": "risk-off"}, "Get ready", "alert"),
        ({"dollar_dir": "down", "active_scenarios": [], "dollar_day_flag": True,
          "triple_red": False, "risk_word": "risk-on"}, "Watch — don't chase", "watch"),
        ({"dollar_dir": "up", "active_scenarios": [], "dollar_day_flag": False,
          "triple_red": False, "risk_word": "risk-on"}, "Watch — don't chase", "calm"),
    ]:
        s = _stance(**args)
        assert s["word_en"] == expected_word_en, f"stance word_en wrong for {args}"
        assert s["tone"] == expected_tone, f"stance tone wrong for {args}"
        for k in ("word_en", "word_zh", "tone", "headline_en", "headline_zh",
                  "sentence_en", "sentence_zh"):
            assert k in s, f"_stance missing key '{k}'"


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
               test_calibrate_dollar_reer_leg, test_forex_link_reads_and_degrades,
               test_regime_z_causal_excludes_t, test_regime_forward_label_leak_free,
               test_regime_probability_wilson_neff_semantics, test_regime_probability_suppression_statuses,
               test_regime_wilson_bounds, test_regime_never_scored_isolation,
               test_regime_end_to_end_real_store, test_regime_missing_drivers_degrades,
               # B1.7 new tests
               test_desk_latest_includes_smile_decomp, test_desk_latest_backward_compat,
               test_transmission_latest_includes_assets,
               test_stance_all_branches, test_stance_sentence_plain_words,
               test_stance_sentence_zh_no_ascii_when_headwinds, test_trend_map_plain_words,
               test_scenario_events_fire_on_active, test_dollar_flash_events_fire_on_threshold,
               test_transmission_shift_events_fire_on_change,
               test_smile_x_mapping_anchors, test_alert_timeline_sorted_ts_desc,
               test_latest_json_old_keys_unchanged]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all forex engine tests passed")
