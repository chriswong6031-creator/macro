"""Forex Vector signal engine.

Per-pair signals for the currency board. Reuses the ASSET-AGNOSTIC price layer
from engine.commodity_signals (momentum / structure / risk / ts_momentum /
positioning / cycle_stage) and adds the FX-specific layer:

  orthogonalize   strip each pair's broad-dollar beta -> an idiosyncratic
                  residual price index. Trend/structure run on the RESIDUAL, so 8
                  USD pairs are NOT one repeated dollar bet (the dollar lives in
                  the master tile, not as a per-pair factor).
  carry           foreign short/policy rate minus US (DFF), vol-penalized
                  (carry-crash haircut). EM pairs are carry:context (no weight).
  residual_shock  causal expanding-fit decoupling detector (intervention /
                  geopolitics) on the raw quote.
  riskoff factor  archetype risk-beta x the global risk-off composite (havens
                  rally / risk currencies fall when stress rises).
  dollar master   the broad-dollar tile: trend, advanced/EM legs, the risk-off
                  composite, the dollar-smile regime, and a dollar-day flag.

Every tunable lives in config.yml `forex:`. No look-ahead: rolling windows, a
strictly-causal residual fit, and step-function rates ffilled (economically
correct). compute_all() returns {pair: DataFrame} plus a "_dollar" master frame.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import config
from engine import commodity_signals as cs

ANN = cs.ANN
FX_YIELD = {"us2y", "us10y", "us_short"}   # rate drivers change in absolute terms (diff)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _zclip(s: pd.Series, lb: int = 252, cap: float = 2.5) -> pd.Series:
    """Rolling z-score scaled into [-1, 1]."""
    mp = max(40, lb // 6)
    m = s.rolling(lb, min_periods=mp).mean()
    sd = s.rolling(lb, min_periods=mp).std()
    z = (s - m) / sd.replace(0, np.nan)
    return (z.clip(-cap, cap) / cap)


def _zraw(s: pd.Series, lb: int = 252) -> pd.Series:
    mp = max(40, lb // 6)
    m = s.rolling(lb, min_periods=mp).mean()
    sd = s.rolling(lb, min_periods=mp).std()
    return (s - m) / sd.replace(0, np.nan)


def _synth_ohlc(close: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame({"close": close})
    for c in ("open", "high", "low"):
        out[c] = close
    return out[["open", "high", "low", "close"]]


def _driver_change(s: pd.Series, name: str, idx: pd.Index, window: int) -> pd.Series:
    s = s.reindex(idx).ffill()
    return s.diff(window) if name in FX_YIELD else s.pct_change(window)


# --------------------------------------------------------------------------- #
# dollar orthogonalization: residual idiosyncratic price index
# --------------------------------------------------------------------------- #
def orthogonalize(base_close: pd.Series, broad: pd.Series | None,
                  cfg: dict) -> tuple[pd.Series, pd.Series]:
    """Residual base-vs-USD index = the pair's move AFTER stripping its rolling
    broad-dollar beta. Causal (uses the PRIOR window's beta). Before a beta is
    estimable, the residual == the raw return."""
    idx = base_close.index
    r = np.log(base_close.replace(0, np.nan)).diff()
    if broad is None:
        return base_close.rename("resid_close"), pd.Series(np.nan, index=idx, name="dollar_beta")
    d = np.log(broad.reindex(idx).ffill().replace(0, np.nan)).diff()
    win = cfg["beta_window_d"]
    mp = cfg.get("beta_min_train_d", win)
    cov = r.rolling(win, min_periods=mp).cov(d)
    var = d.rolling(win, min_periods=mp).var()
    beta = (cov / var.replace(0, np.nan)).shift(1)              # causal
    e = (r - beta * d).where(beta.notna(), r)                   # raw return until beta exists
    resid = np.exp(e.fillna(0.0).cumsum())
    return resid.rename("resid_close"), beta.rename("dollar_beta")


# --------------------------------------------------------------------------- #
# carry: rate differential (foreign short - US), vol-penalized
# --------------------------------------------------------------------------- #
def carry_signal(fr: pd.Series | None, us: pd.Series | None,
                 raw_close: pd.Series, cfg: dict) -> pd.DataFrame:
    idx = raw_close.index
    if fr is None or us is None:
        return pd.DataFrame(index=idx)
    frr = fr.reindex(idx).ffill()                              # step-function rate, ffill correct
    uss = us.reindex(idx).ffill()
    diff = (frr - uss).rename("carry_diff")                    # ann % carry of holding base vs USD
    ret = raw_close.pct_change()
    vol = ret.rolling(cfg["vol_window_d"]).std() * ANN         # annualized realized vol (frac)
    volp = cs._pctile(vol, cfg["pctile_lookback_d"])           # 0..1
    pen = (1.0 - 0.5 * volp).clip(0.4, 1.0)                    # high-vol carry -> haircut (crash-prone)
    score = (np.tanh(diff / cfg["scale"]) * pen).clip(-1, 1)
    ctv = (diff / (vol * 100).replace(0, np.nan))             # carry / %vol (for the carry table)
    out = pd.DataFrame({"carry_diff": diff, "carry_score": score, "carry_to_vol": ctv})
    out["carry_score"] = out["carry_score"].ewm(span=cfg.get("smooth_days", 5), adjust=False).mean()
    return out


def _lag_to_daily(s: pd.Series, idx: pd.Index, pub_lag_d: int) -> pd.Series:
    """Shift a monthly/lagged series forward by its publication lag, then hold the last
    KNOWN value across the daily index (no look-ahead — the value only appears once it
    was actually released)."""
    r = s.copy()
    r.index = pd.to_datetime(r.index) + pd.Timedelta(days=pub_lag_d)
    return r.reindex(r.index.union(idx)).sort_index().ffill().reindex(idx)


# --------------------------------------------------------------------------- #
# value: REER mean-reversion (slow valuation anchor)
# --------------------------------------------------------------------------- #
def value_signal(reer: pd.Series | None, cfg: dict, idx: pd.Index) -> pd.DataFrame:
    if reer is None:
        return pd.DataFrame(index=idx)
    r = _lag_to_daily(reer, idx, cfg.get("pub_lag_d", 45))
    logr = np.log(r.replace(0, np.nan))
    win = cfg["gap_window_d"]
    mean = logr.rolling(win, min_periods=max(120, win // 4)).mean()
    gap = (logr - mean).rename("reer_gap")                # + = REER rich vs its long-run mean
    score = (-_zclip(gap, cfg["z_lookback_d"])).clip(-1, 1)   # overvalued -> bearish (mean-revert)
    return pd.DataFrame({"reer_gap": gap, "value_score": score})


# --------------------------------------------------------------------------- #
# rates: 10y yield-differential momentum (relative monetary policy)
# --------------------------------------------------------------------------- #
def rates_signal(long_rate: pd.Series | None, us10y: pd.Series | None,
                 cfg: dict, idx: pd.Index) -> pd.DataFrame:
    if long_rate is None or us10y is None:
        return pd.DataFrame(index=idx)
    f = _lag_to_daily(long_rate, idx, cfg.get("pub_lag_d", 45))
    u = us10y.reindex(idx).ffill()
    diff = (f - u).rename("rate_diff_10y")                # foreign 10y - US 10y
    mom = diff.diff(cfg["diff_window_d"])
    score = _zclip(mom, cfg["z_lookback_d"]).clip(-1, 1)  # rising diff -> base attracts flows (bullish)
    return pd.DataFrame({"rate_diff_10y": diff, "rates_score": score})


# --------------------------------------------------------------------------- #
# residual shock: causal decoupling / intervention detector (FX-specific)
# --------------------------------------------------------------------------- #
def residual_shock(close: pd.Series, drivers: dict, commodity: dict | None,
                   cfg: dict) -> pd.DataFrame:
    idx = close.index
    w = cfg["return_window_d"]
    y = close.pct_change(w).rename("y")
    feats: dict[str, pd.Series] = {}
    for dn in cfg["drivers"]:
        s = drivers.get(dn)
        if s is not None:
            feats[dn] = _driver_change(s, dn, idx, w)
    if commodity:                                             # AUD/CAD terms-of-trade leg
        cc = None
        for s in commodity.values():
            ch = s.reindex(idx).ffill().pct_change(w)
            cc = ch if cc is None else cc.add(ch, fill_value=0)
        if cc is not None:
            feats["commodity"] = cc / float(len(commodity))
    out = pd.DataFrame(index=idx)
    if not feats:
        return out
    X = pd.DataFrame(feats)
    cols = list(X.columns)
    valid = pd.concat([y, X], axis=1).dropna()
    if len(valid) < cfg["min_train_d"] + cfg["refit_every_d"]:
        return out
    resid = pd.Series(index=idx, dtype=float)
    mintr, refit = cfg["min_train_d"], cfg["refit_every_d"]
    yv = valid["y"].to_numpy()
    Aall = np.column_stack([np.ones(len(valid)), valid[cols].to_numpy()])
    pos_index = valid.index
    beta = None
    for i in range(mintr, len(valid)):
        if beta is None or (i - mintr) % refit == 0:
            beta = np.linalg.lstsq(Aall[:i], yv[:i], rcond=None)[0]   # history strictly < i
        resid.iloc[idx.get_loc(pos_index[i])] = yv[i] - (Aall[i] @ beta)
    out["resid_ret"] = resid
    sd = resid.rolling(cfg["z_lookback_d"], min_periods=60).std()
    z = (resid / sd.replace(0, np.nan)).rename("shock_z")
    out["shock_z"] = z
    thr = cfg["shock_z"]
    out["shock_state"] = np.where(z > thr, "exogenous_bid",
                         np.where(z < -thr, "exogenous_pressure", "normal"))
    out.loc[z.isna(), "shock_state"] = np.nan
    return out


# --------------------------------------------------------------------------- #
# global risk-off composite + per-pair risk factor
# --------------------------------------------------------------------------- #
# archetype risk-beta: how pro-cyclical the BASE currency is (havens are negative)
RISK_BETA = {"commodity-dollar": 1.0, "em": 1.0, "em-managed": 1.0,
             "major": 0.5, "haven-funder": -1.0}


def riskoff_on(idx: pd.Index, drivers: dict, cfg: dict) -> pd.Series:
    """Global risk-off intensity in [-1,1]; HIGH = risk-OFF (stress). z of equity
    vol + credit/EM spreads + (inverted) copper/gold, equities, EM equity."""
    comps = cfg["dollar"]["risk"]["components"]
    lb = cfg["dollar"]["risk"].get("z_lookback_d", 252)
    z: dict[str, pd.Series] = {}
    for k in ("vix", "hy_oas", "em_oas"):
        if k in drivers:
            z[k] = _zclip(drivers[k].reindex(idx).ffill(), lb)          # high level = risk-off
    if "copper" in drivers and "gold" in drivers:
        cg = drivers["copper"].reindex(idx).ffill() / drivers["gold"].reindex(idx).ffill()
        z["copper_gold"] = -_zclip(cg.pct_change(63), lb)              # falling growth = risk-off
    if "spy" in drivers:
        z["spy"] = -_zclip(drivers["spy"].reindex(idx).ffill().pct_change(63), lb)
    if "eem" in drivers:
        z["eem"] = -_zclip(drivers["eem"].reindex(idx).ffill().pct_change(63), lb)
    if not z:
        return pd.Series(np.nan, index=idx, name="risk_off")
    num = pd.Series(0.0, index=idx)
    den = pd.Series(0.0, index=idx)
    for k, zz in z.items():
        w = float(comps.get(k, 0.0))
        num = num.add((zz * w).fillna(0.0))
        den = den.add(zz.notna().astype(float) * w)
    return (num / den.replace(0, np.nan)).clip(-1, 1).rename("risk_off")


def riskoff_factor(R: pd.Series | None, meta: dict, idx: pd.Index) -> pd.DataFrame:
    if R is None:
        return pd.DataFrame(index=idx)
    beta = RISK_BETA.get(meta.get("archetype"), 0.5)
    f = (-beta * R.reindex(idx).ffill()).clip(-1, 1)          # +=bullish base (havens flip via beta<0)
    return pd.DataFrame({"riskoff": f})


# --------------------------------------------------------------------------- #
# dollar master frame
# --------------------------------------------------------------------------- #
def dollar_master(drivers: dict, cfg: dict) -> pd.DataFrame:
    dxy = drivers.get("dxy")
    broad = drivers.get("broad_dollar")
    if dxy is None and broad is None:
        return pd.DataFrame()
    idx = (dxy.index if dxy is not None else broad.index)
    out = pd.DataFrame(index=idx)
    out["dxy"] = dxy.reindex(idx).ffill() if dxy is not None else np.nan
    out["broad"] = broad.reindex(idx).ffill() if broad is not None else np.nan
    for leg in ("broad_afe", "broad_eme"):
        s = drivers.get(leg)
        out[leg] = s.reindex(idx).ffill() if s is not None else np.nan
    drv = out["broad"] if broad is not None else out["dxy"]
    win = cfg["dollar"]["trend_window_d"]
    out["dollar_roc"] = drv.pct_change(win)
    out["dollar_dir"] = np.sign(out["dollar_roc"])
    out["risk_off"] = riskoff_on(idx, drivers, cfg)
    out["dollar_day_z"] = _zraw(drv.pct_change()).abs()
    up = out["dollar_dir"] > 0
    ro = out["risk_off"] > 0
    reg = pd.Series("Neutral", index=idx, dtype=object)
    reg[up & ro] = "Risk-off haven bid"        # right of the smile
    reg[up & ~ro] = "US growth premium"        # left of the smile
    reg[~up & ~ro] = "Global reflation"        # bottom of the smile (USD weak)
    reg[~up & ro] = "US-specific stress"       # smile breaking (USD weak + stress)
    out["smile_regime"] = cs._confirm(reg, 5)
    return out


# --------------------------------------------------------------------------- #
# per-pair assembly
# --------------------------------------------------------------------------- #
def compute_asset(ai: dict, cfg: dict | None = None, R: pd.Series | None = None) -> pd.DataFrame:
    cfg = cfg or config.load()["forex"]
    meta = ai["meta"]
    px = ai["price"]                                          # canonical base-vs-USD OHLC
    drivers = ai["drivers"]

    resid_close, beta = orthogonalize(px["close"], drivers.get("broad_dollar"), cfg["dollar"])
    px_resid = _synth_ohlc(resid_close)

    mom = cs.momentum(px_resid, cfg["momentum"])             # idiosyncratic short trend
    st = cs.structure(px_resid, cfg["structure"])
    ts = cs.ts_momentum(px_resid, cfg["trend"])              # idiosyncratic 12m trend
    pos = cs.positioning(ai.get("cot_net_pct_oi"), px.index, cfg["positioning"])
    pos_pctile = pos["pos_pctile"] if "pos_pctile" in pos else None
    rk = cs.risk(px, mom["momentum"], pos_pctile, cfg["risk"])   # risk on the ACTUAL price
    ca = (carry_signal(ai.get("short_rate"), drivers.get("us_short"), px["close"], cfg["carry"])
          if meta.get("carry") != "context" else pd.DataFrame(index=px.index))
    va = value_signal(ai.get("reer"), cfg["value"], px.index)
    ra = rates_signal(ai.get("long_rate"), drivers.get("us10y"), cfg["rates"], px.index)
    rs = residual_shock(px["close"], drivers, ai.get("commodity"), cfg["residual"])
    ro = riskoff_factor(R, meta, px.index)

    parts = [px[["close"]], resid_close, beta, mom, st, ts, pos, rk, ca, va, ra, rs, ro]
    out = pd.concat(parts, axis=1)
    out["cycle_position"] = cs.cycle_stage(mom["momentum"], rk["risk_index"])
    out["pair"] = ai["pair"]
    return out


def compute_all(inputs: dict | None = None, cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    from engine import forex_inputs
    cfg = cfg or config.load()["forex"]
    if inputs is None:
        inputs = forex_inputs.load_all(cfg)
    drivers = next(iter(inputs.values()))["drivers"] if inputs else {}
    dollar = dollar_master(drivers, cfg)
    R = dollar["risk_off"] if "risk_off" in dollar else None
    results = {p: compute_asset(ai, cfg, R) for p, ai in inputs.items()}
    results["_dollar"] = dollar
    return results
