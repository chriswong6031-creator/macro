"""Bitcoin Vector signal engine.

Architecture per research/VECTOR_SIGNAL_RECON.md (evidence from Swissblock's
own panels): momentum & structure are VOTE ENSEMBLES (mean of -1/0/+1 votes —
hence the observed pinning at ±1 and quantized steps); the Risk Index is a
SATURATING weighted composite with a deadband (hence pinning at exactly 0 in
healthy uptrends); the Risk Oscillator is bounded risk-momentum parked at 0.50
when quiet; BFI blends Network-Growth and Liquidity percentile oscillators
with 40/60 bands.

Every tunable lives in config.yml `vector:`. compute_all() returns a daily
DataFrame of every signal — the calibration script and (later) the dashboard
builder consume it. No look-ahead anywhere: rolling windows + shift(1) where
a same-day print wouldn't have been known.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import config


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _pctile(s: pd.Series, lookback: int) -> pd.Series:
    return s.rolling(lookback, min_periods=lookback // 4).rank(pct=True)


def _confirm(state: pd.Series, days: int) -> pd.Series:
    """A state change must hold `days` consecutive days before it takes effect."""
    if days <= 1:
        return state
    out, cur, cand, run = [], None, None, 0
    for v in state:
        if cur is None:
            cur = v
        if v == cur:
            cand, run = None, 0
        elif v == cand:
            run += 1
            if run >= days:
                cur, cand, run = v, None, 0
        else:
            cand, run = v, 1
        out.append(cur)
    return pd.Series(out, index=state.index)


def _hysteresis_tri(score: pd.Series, enter: float, exit_: float,
                    labels=("bear", "neutral", "bull")) -> pd.Series:
    """Three-state hysteresis: enter bull/bear when |score| > enter; leave only
    when score retreats past ±exit_. Kills the chop that a single threshold
    creates when the score oscillates around it (the whipsaw fix)."""
    lo, mid, hi = labels
    out, cur = [], mid
    for v in score:
        if np.isnan(v):
            out.append(cur)
            continue
        if cur == hi:
            cur = mid if v < exit_ else hi
            if v < -enter:
                cur = lo
        elif cur == lo:
            cur = mid if v > -exit_ else lo
            if v > enter:
                cur = hi
        else:
            cur = hi if v > enter else (lo if v < -enter else mid)
        out.append(cur)
    return pd.Series(out, index=score.index)


def _hysteresis_bi(value: pd.Series, enter: float, exit_: float,
                   high="high", low="low") -> pd.Series:
    """Two-state hysteresis around an upper/lower band (e.g. risk regime: enter
    high at 25, fall back to low only below 18)."""
    out, cur = [], low
    for v in value:
        if np.isnan(v):
            out.append(cur)
            continue
        if cur == low and v >= enter:
            cur = high
        elif cur == high and v < exit_:
            cur = low
        out.append(cur)
    return pd.Series(out, index=value.index)


# --------------------------------------------------------------------------- #
# momentum ensemble  [-1, +1]
# --------------------------------------------------------------------------- #
def momentum(inputs: dict, cfg: dict) -> pd.DataFrame:
    px = inputs["price"]
    close = px["close"]
    idx = close.index
    w = cfg["votes"]
    votes = pd.DataFrame(index=idx)

    ema20, ema50 = _ema(close, 20), _ema(close, 50)
    votes["ema_trend"] = np.sign(close - ema50) * (np.sign(ema50.diff(5)) == np.sign(close - ema50))
    votes["ema_trend"] = np.where(close > ema50, 1, -1) * np.where(
        np.sign(ema50.diff(5)) == np.where(close > ema50, 1, -1), 1, 0.5)
    votes["ema_cross"] = np.where(ema20 > ema50, 1, -1)
    macd_hist = _ema(close, 12) - _ema(close, 26) - _ema(_ema(close, 12) - _ema(close, 26), 9)
    votes["macd_hist"] = np.sign(macd_hist)
    votes["sma200"] = np.where(close > close.rolling(200).mean(), 1, -1)
    votes["roc20"] = np.sign(close.pct_change(20))
    rsi = _rsi(close)
    votes["rsi_zone"] = np.where(rsi > cfg["rsi_bull"], 1, np.where(rsi < cfg["rsi_bear"], -1, 0))

    sopr = inputs.get("sopr")
    if sopr is not None:
        s7 = _ema(sopr.reindex(idx).ffill(limit=3), 7)
        votes["sopr_momentum"] = np.sign(s7 - 1.0)
    sth_rp = inputs.get("sth_realized_price")
    if sth_rp is not None:
        votes["sth_cost_basis"] = np.sign(close - sth_rp.reindex(idx).ffill(limit=5))

    weights = pd.Series({k: w[k] for k in votes.columns if k in w})
    wsum = votes.notna().mul(weights, axis=1).sum(axis=1)
    score = votes.mul(weights, axis=1).sum(axis=1, min_count=3) / wsum.replace(0, np.nan)
    score = score.ewm(span=cfg["smooth_days"], adjust=False).mean().clip(-1, 1)

    state = _confirm(_hysteresis_tri(score, cfg["trigger"], cfg["exit"]), cfg["confirm_days"])
    return pd.DataFrame({"momentum": score, "momentum_state": state})


# --------------------------------------------------------------------------- #
# risk index 0..100 (saturating, deadbanded) + risk oscillator [0,1]
# --------------------------------------------------------------------------- #
def risk(inputs: dict, mom: pd.Series, cfg: dict) -> pd.DataFrame:
    px = inputs["price"]
    close = px["close"]
    idx = close.index
    w = cfg["weights"]
    stress = pd.DataFrame(index=idx)

    ret = close.pct_change()
    # DOWNSIDE semi-deviation, not total vol: an explosive *up* rally (high vol,
    # few down days) must not read as risk — Swissblock's upside/downside-vol
    # distinction. Fixes the Nov-2024 false high-risk found vs their panel.
    dvol = ret.clip(upper=0).rolling(cfg["vol_window_d"]).std() * np.sqrt(365)
    stress["vol_pctile"] = _pctile(dvol, cfg["vol_pctile_lookback_d"])

    dd = 1 - close / close.rolling(cfg["drawdown_window_d"]).max()
    stress["drawdown"] = (dd / cfg["drawdown_full_stress"]).clip(0, 1)

    sopr = inputs.get("sopr")
    if sopr is not None:
        s7 = _ema(sopr.reindex(idx).ffill(limit=3), cfg["sopr_ema_d"])
        stress["sopr_stress"] = ((1.0 - s7) * 40).clip(0, 1)  # SOPR 0.975 -> 1.0 stress

    intraday = inputs.get("intraday_vol")
    if intraday is not None:
        intr = intraday.reindex(idx)
        inter = ret.abs().rolling(10).mean()
        ratio = (inter / intr.rolling(10).mean().replace(0, np.nan)).clip(0, 5)
        stress["interday_ratio"] = _pctile(ratio, cfg["vol_pctile_lookback_d"])

    stress["momentum_deterioration"] = ((-mom.diff(10)).clip(0, 1) * (mom < 0.5)).clip(0, 1)

    etf = inputs.get("etf_flow")
    if etf is not None:
        out7 = etf.reindex(idx).fillna(0).rolling(cfg["etf_flow_sum_d"]).sum()
        scale = etf.abs().rolling(90, min_periods=20).mean().reindex(idx).ffill() * cfg["etf_flow_sum_d"]
        stress["etf_outflow"] = ((-out7) / scale.replace(0, np.nan)).clip(0, 1)
        stress.loc[etf.reindex(idx).isna(), "etf_outflow"] = np.nan  # pre-ETF era: no vote

    funding = inputs.get("funding")
    if funding is not None:
        f = funding.reindex(idx).ffill(limit=3)
        stress["funding_stress"] = (f.abs() > f.abs().rolling(180, min_periods=60)
                                    .quantile(0.9)).astype(float).where(f.notna())

    weights = pd.Series({k: w[k] for k in stress.columns if k in w})
    wsum = stress.notna().mul(weights, axis=1).sum(axis=1)
    raw = stress.mul(weights, axis=1).sum(axis=1, min_count=2) / wsum.replace(0, np.nan)

    db = cfg["deadband"]
    risk_idx = (((raw - db).clip(lower=0) / (1 - db)) * 100).clip(0, 100)

    osc = (0.5 + risk_idx.diff(cfg["oscillator_delta_d"]) / cfg["oscillator_scale"] * 0.5).clip(0, 1)
    osc = osc.fillna(0.5)

    regime = _hysteresis_bi(risk_idx, cfg["threshold"], cfg["exit_threshold"],
                            high="high_risk", low="low_risk")
    return pd.DataFrame({"risk_index": risk_idx, "risk_oscillator": osc,
                         "risk_regime": regime})


# --------------------------------------------------------------------------- #
# BFI: network growth & liquidity percentile oscillators, bands 40/60
# --------------------------------------------------------------------------- #
def bfi(inputs: dict, cfg: dict) -> pd.DataFrame:
    px = inputs["price"]
    idx = px.index
    out = pd.DataFrame(index=idx)

    addr = inputs.get("active_addresses")
    if addr is not None:
        a = addr.reindex(idx).ffill(limit=3)
        growth = _ema(a, cfg["growth_mom_d"]) / _ema(a, cfg["growth_base_d"]) - 1
        out["network_growth"] = _pctile(growth, cfg["pctile_lookback_d"]) * 100

    liq_parts = []
    rc = inputs.get("realized_cap")
    if rc is not None:
        liq_parts.append(rc.reindex(idx).ffill(limit=3).pct_change(cfg["liq_components_sum_d"]))
    st = inputs.get("stablecoins")
    if st is not None:
        liq_parts.append(st.reindex(idx).ffill(limit=5).pct_change(cfg["liq_components_sum_d"]))
    etf = inputs.get("etf_flow")
    if etf is not None:
        e = etf.reindex(idx).fillna(0).rolling(cfg["liq_components_sum_d"]).sum()
        liq_parts.append((e / e.abs().rolling(365, min_periods=60).max()).where(
            etf.reindex(idx).notna().rolling(5).max() > 0))
    if liq_parts:
        z = pd.concat([(p - p.rolling(365, min_periods=90).mean())
                       / p.rolling(365, min_periods=90).std() for p in liq_parts], axis=1)
        out["liquidity"] = _pctile(z.mean(axis=1, skipna=True), cfg["pctile_lookback_d"]) * 100

    if {"network_growth", "liquidity"} <= set(out.columns):
        raw = out[["network_growth", "liquidity"]].mean(axis=1)
        out["bfi"] = raw.ewm(span=cfg["smooth_d"], adjust=False).mean()
        out["bfi_zone"] = np.where(out["bfi"] >= cfg["band_hi"], "positive",
                          np.where(out["bfi"] < cfg["band_lo"], "negative", "neutral"))
    return out


# --------------------------------------------------------------------------- #
# structure shift  [-1, +1]
# --------------------------------------------------------------------------- #
def structure(inputs: dict, cfg: dict) -> pd.DataFrame:
    px = inputs["price"]
    close, high, low = px["close"], px["high"].fillna(px["close"]), px["low"].fillna(px["close"])
    n = cfg["swing_window_d"]
    votes = pd.DataFrame(index=close.index)
    hh = high.rolling(n).max()
    ll = low.rolling(n).min()
    votes["higher_high"] = np.sign(hh.diff(n)).replace(0, np.nan)
    votes["higher_low"] = np.sign(ll.diff(n)).replace(0, np.nan)
    votes["mid_range"] = np.where(close > (hh + ll) / 2, 1, -1)
    bo = cfg["breakout_lookback_d"]
    votes["breakout"] = np.where(close >= close.rolling(bo).max() * 0.999, 1,
                        np.where(close <= close.rolling(bo).min() * 1.001, -1, np.nan))
    votes["breakout"] = votes["breakout"].ffill(limit=5)
    votes["above_50"] = np.where(close > close.rolling(50).mean(), 1, -1)

    score = votes.mean(axis=1, skipna=True).clip(-1, 1).ewm(span=3, adjust=False).mean()
    state = _confirm(_hysteresis_tri(score, cfg["trigger"], cfg["exit"],
                                     labels=("broken", "neutral", "constructive")),
                     cfg["confirm_days"])
    return pd.DataFrame({"structure": score, "structure_state": state})


# --------------------------------------------------------------------------- #
# gauges, environment, allocation, btc-vs-alts, tactical
# --------------------------------------------------------------------------- #
def gauges(inputs: dict, cfg_g: dict, cfg_r: dict) -> pd.DataFrame:
    px = inputs["price"]
    close = px["close"]
    ret = close.pct_change()
    rv = ret.rolling(cfg_r["vol_window_d"]).std() * np.sqrt(365)
    volp = _pctile(rv, cfg_r["vol_pctile_lookback_d"])
    vol_state = pd.Series(np.where(volp < cfg_g["vol_low_pctile"], "Low",
                          np.where(volp > cfg_g["vol_high_pctile"], "High", "Sweet spot")),
                          index=close.index)
    up = ret.clip(lower=0).rolling(30).std()
    dn = (-ret.clip(upper=0)).rolling(30).std()
    vol_side = pd.Series(np.where(up > dn, "Upside", "Downside"), index=close.index)

    flow_parts = [_pctile(px["volume"].rolling(7).mean(), 365)]
    etf = inputs.get("etf_flow")
    if etf is not None:
        flow_parts.append(_pctile(etf.reindex(close.index).fillna(0).rolling(7).sum(), 365)
                          .where(etf.reindex(close.index).notna().rolling(7).max() > 0))
    st = inputs.get("stablecoins")
    if st is not None:
        flow_parts.append(_pctile(st.reindex(close.index).ffill(limit=5).pct_change(30), 365))
    flowp = pd.concat(flow_parts, axis=1).mean(axis=1, skipna=True)
    flow_state = pd.Series(np.where(flowp < cfg_g["flow_low_pctile"], "Low",
                           np.where(flowp > cfg_g["flow_high_pctile"], "High", "Sweet spot")),
                           index=close.index)
    return pd.DataFrame({"vol_pctile": volp, "vol_state": vol_state, "vol_side": vol_side,
                         "flow_pctile": flowp, "flow_state": flow_state})


def cycle_stage(mom: pd.Series, risk_idx: pd.Series) -> pd.Series:
    """Defensive / Fragile / Recovery / Expansion knob in [0,1]:
    momentum carries direction, risk drags the knob left."""
    pos = (mom + 1) / 2 * 0.75 + (1 - risk_idx / 100) * 0.25
    return pos.clip(0, 1).rename("cycle_position")


def allocation(mom: pd.Series, risk_idx: pd.Series, cfg: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=mom.index)
    for name, v in cfg["variants"].items():
        full = (mom > v["mom_full"]) & (risk_idx < v["risk_full"])
        half = (mom > v["mom_half"]) & (risk_idx < v["risk_half"])
        raw = pd.Series(np.where(full, 1.0, np.where(half, 0.5, 0.0)), index=mom.index)
        out[f"alloc_{name}"] = _confirm(raw, cfg["confirm_days"])
    return out


def btc_vs_alts(inputs: dict, cfg: dict) -> pd.Series | None:
    px = inputs["price"]["close"]
    eth = inputs.get("eth")
    dom = inputs.get("btc_dominance")
    if eth is None:
        return None
    idx = px.index
    n = cfg["rs_window_d"]
    eth_rs = eth.reindex(idx).ffill(limit=3).pct_change(n) - px.pct_change(n)
    alts_rs = None
    if dom is not None:
        d = dom.reindex(idx).ffill(limit=5)
        alts_rs = -(d.diff(n))  # dominance falling = alts leading
    leader = pd.Series("BTC", index=idx)
    leader[eth_rs > 0] = "ETH"
    if alts_rs is not None:
        scale = alts_rs.abs().rolling(365, min_periods=60).quantile(0.8)
        leader[(alts_rs > scale) & (eth_rs > 0)] = "Alts"
    return _confirm(leader, cfg["confirm_days"]).rename("alt_cycle_leader")


def tactical(inputs: dict, risk_idx: pd.Series, cfg: dict) -> pd.Series:
    close = inputs["price"]["close"]
    n = cfg["efficiency_window_d"]
    eff = (close.diff(n).abs() / close.diff().abs().rolling(n).sum()).clip(0, 1)
    strategic = (eff > cfg["strategic_min_efficiency"]) & (risk_idx < cfg["strategic_max_risk"])
    return _confirm(pd.Series(np.where(strategic, "Strategic", "Tactical"), index=close.index), 3) \
        .rename("market_mode")


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def compute_all(inputs: dict | None = None) -> pd.DataFrame:
    from engine import btc_inputs
    cfg = config.load()["vector"]
    if inputs is None:
        inputs = btc_inputs.load_all()

    mom = momentum(inputs, cfg["momentum"])
    rk = risk(inputs, mom["momentum"], cfg["risk"])
    bf = bfi(inputs, cfg["bfi"])
    st = structure(inputs, cfg["structure"])
    gg = gauges(inputs, cfg["gauges"], cfg["risk"])
    al = allocation(mom["momentum"], rk["risk_index"], cfg["allocation"])

    out = pd.concat([inputs["price"][["close"]], mom, rk, bf, st, gg, al], axis=1)
    out["cycle_position"] = cycle_stage(mom["momentum"], rk["risk_index"])
    alt = btc_vs_alts(inputs, cfg["btc_vs_alts"])
    if alt is not None:
        out["alt_cycle_leader"] = alt
    out["market_mode"] = tactical(inputs, rk["risk_index"], cfg["tactical"])
    return out
