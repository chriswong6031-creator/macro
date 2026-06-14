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


def _zscore(s: pd.Series, n: int) -> pd.Series:
    m = s.rolling(n, min_periods=max(20, n // 4))
    return (s - m.mean()) / m.std().replace(0, np.nan)


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


def _hysteresis_asym(s: pd.Series, hi_enter: float, hi_exit: float,
                     lo_enter: float, lo_exit: float,
                     labels=("low", "mid", "high")) -> pd.Series:
    """Three-state hysteresis with INDEPENDENT high/low thresholds (valuation is
    asymmetric — e.g. overvalued above z=3.5, undervalued below z=0). Requires
    lo_enter < lo_exit < hi_exit < hi_enter."""
    lo, mid, hi = labels
    out, cur = [], mid
    for v in s:
        if np.isnan(v):
            out.append(cur)
            continue
        if cur == hi:
            cur = hi if v > hi_exit else (lo if v < lo_enter else mid)
        elif cur == lo:
            cur = lo if v < lo_exit else (hi if v > hi_enter else mid)
        else:
            cur = hi if v > hi_enter else (lo if v < lo_enter else mid)
        out.append(cur)
    return pd.Series(out, index=s.index)


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


def allocation(mom: pd.Series, risk_idx: pd.Series, cfg: dict,
               val: pd.DataFrame | None = None) -> pd.DataFrame:
    out = pd.DataFrame(index=mom.index)
    deep_value = overvalued = None
    if val is not None and cfg.get("use_valuation_overlay"):
        dv = pd.Series(False, index=mom.index)
        if "mvrv_z" in val:
            dv = dv | (val["mvrv_z"].reindex(mom.index) < cfg["deep_value_z"])
        if "nupl" in val:
            dv = dv | (val["nupl"].reindex(mom.index) < cfg["deep_value_nupl"])
        ov = pd.Series(False, index=mom.index)
        if "mayer" in val:
            ov = ov | (val["mayer"].reindex(mom.index) > cfg["overvalued_mayer"])
        if "reserve_risk" in val and cfg.get("overvalued_rr"):
            # calibrated TOP cap (>0.02 -> -42%/90d); neutral in-sample (momentum/
            # risk already de-risk first) but a safety guard if they ever lag it.
            ov = ov | (val["reserve_risk"].reindex(mom.index) > cfg["overvalued_rr"])
        deep_value, overvalued = dv.fillna(False), ov.fillna(False)
    for name, v in cfg["variants"].items():
        full = (mom > v["mom_full"]) & (risk_idx < v["risk_full"])
        half = (mom > v["mom_half"]) & (risk_idx < v["risk_half"])
        raw = pd.Series(np.where(full, 1.0, np.where(half, 0.5, 0.0)), index=mom.index)
        if deep_value is not None:
            raw = raw.mask(deep_value, raw.clip(lower=0.5))   # accumulate the bottom
            raw = raw.mask(overvalued, raw.clip(upper=0.5))   # trim the cycle top
        out[f"alloc_{name}"] = _confirm(raw, cfg["confirm_days"])
    return out


def composite_state(out: pd.DataFrame, cfg: dict | None = None) -> pd.Series:
    """One actionable headline that fuses ALL confirmed axes (valuation/extreme
    first, because those resolve the Risk Index's forward-return U-shape into a
    direction): ACCUMULATE / DISTRIBUTE / RISK-OFF / RISK-ON / NEUTRAL. Now
    incorporates the CONFIRMED macro_regime + BFI and the reserve-risk TOP
    (previously display-only) per the integration audit."""
    cfg = cfg or {}
    idx = out.index
    state = pd.Series("NEUTRAL", index=idx)
    risk_hi = out.get("risk_regime", pd.Series("low_risk", index=idx)) == "high_risk"
    mom_bull = out.get("momentum_state", pd.Series("neutral", index=idx)) == "bull"
    mom_bear = out.get("momentum_state", pd.Series("neutral", index=idx)) == "bear"
    extreme = out.get("market_extreme", pd.Series("normal", index=idx))
    val_state = out.get("valuation_state", pd.Series("fair", index=idx))
    macro = out.get("macro_regime", pd.Series("neutral", index=idx))
    bfi = out.get("bfi", pd.Series(np.nan, index=idx))
    rr = out.get("reserve_risk", pd.Series(np.nan, index=idx))
    rr_top = rr > cfg.get("reserve_risk_top", 0.02)
    bfi_strong = bfi > cfg.get("bfi_strong", 60)
    cot_z = out.get("cot_z", pd.Series(np.nan, index=idx))
    cot_crowded = cot_z > cfg.get("cot_crowded_z", 1.5)  # crowded spec long = contrarian top

    # priority order (later assignments win): trend < risk-off < distribute < accumulate
    state[mom_bull & ~risk_hi] = "RISK-ON"
    state[mom_bear] = "RISK-OFF"
    state[risk_hi] = "RISK-OFF"
    # CONFIRMED confirmers: BFI>60 or macro tailwind upgrades a non-risk-off, non-bear
    # tape to RISK-ON (fundamentals/liquidity backing the trend).
    state[(bfi_strong | (macro == "tailwind")) & ~risk_hi & ~mom_bear] = "RISK-ON"
    # macro headwind reinforces risk-off when momentum is weak.
    state[(macro == "headwind") & ~mom_bull] = "RISK-OFF"
    # distribution: euphoria / overvalued / reserve-risk TOP / crowded CME spec long.
    state[(extreme == "euphoria") | (val_state == "overvalued") | rr_top | cot_crowded] = "DISTRIBUTE"
    # accumulation wins outright (capitulation extremes resolve the risk U-shape).
    state[(extreme == "capitulation") | (val_state == "undervalued")] = "ACCUMULATE"
    return state.rename("composite_state")


def composite_context(out: pd.DataFrame, cfg: dict | None = None) -> pd.Series:
    """Display-only confirmer TAG shown beside the headline stance. These are the
    CONFIRMATION-ONLY positioning factors the integration A/B (scripts/integration_lab.py,
    reports/vector-integration-candidates.md) said to SURFACE but never wire into the
    allocation/risk math (no pre-2021 footprint -> can't clear the both-halves bar):
    crowded-short capitulation (funding_z, an ACCUMULATE-side corroborator) and froth
    (crowded CME longs via cot_z, a DISTRIBUTE-side corroborator). It is a tag only —
    it does NOT move the Risk Index, allocation, or composite_state."""
    cfg = cfg or {}
    idx = out.index
    ctx = pd.Series("", index=idx)
    fz = out.get("funding_z", pd.Series(np.nan, index=idx))
    cz = out.get("cot_z", pd.Series(np.nan, index=idx))
    ctx = ctx.mask(fz < cfg.get("funding_capitulation_z", -1.0), "crowded_short")
    ctx = ctx.mask(cz > cfg.get("cot_crowded_z", 1.5), "froth")
    return ctx.rename("composite_context")


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
# valuation axis: MVRV-Z, NUPL, Mayer (Tier-1 accuracy upgrade)
# --------------------------------------------------------------------------- #
def valuation(inputs: dict, cfg: dict) -> pd.DataFrame:
    """The missing cycle anchor. MVRV-Z = (mcap - realized_cap) / rolling_std(mcap)
    on a ~1-cycle window (ETF-era responsive). NUPL and Mayer are cheap orthogonal
    cross-checks. All ~2010-> depth, so these are calibration anchors, not
    confirmation. Emitted standalone — measured before any blend (§3 of the doc)."""
    idx = inputs["price"].index
    out = pd.DataFrame(index=idx)
    mcap, rcap = inputs.get("mcap"), inputs.get("realized_cap")
    if mcap is not None and rcap is not None:
        m = mcap.reindex(idx).ffill()
        r = rcap.reindex(idx).ffill()
        std = m.rolling(cfg["z_window_d"], min_periods=cfg["z_min_periods_d"]).std()
        z = ((m - r) / std.replace(0, np.nan)).rename("mvrv_z")
        out["mvrv_z"] = z
        out["mvrv_z_pctile"] = _pctile(z, cfg["pctile_lookback_d"]) * 100
        out["valuation_state"] = _hysteresis_asym(
            z, cfg["z_over"], cfg["z_over_exit"], cfg["z_under"], cfg["z_under_exit"],
            labels=("undervalued", "fair", "overvalued"))
    nupl = inputs.get("nupl")
    if nupl is not None:
        out["nupl"] = nupl.reindex(idx).ffill()
    close = inputs["price"]["close"]
    out["mayer"] = close / close.rolling(cfg.get("mayer_window_d", 200)).mean()
    # Reserve Risk (checkonchain, 2010->): price vs the opportunity cost of HODLing.
    # Low = high-conviction accumulation (cycle bottoms); high = euphoric distribution.
    rr = inputs.get("reserve_risk")
    if rr is not None:
        r = rr.replace([np.inf, -np.inf], np.nan).reindex(idx).ffill(limit=5)
        out["reserve_risk"] = r
        out["reserve_risk_pctile"] = _pctile(r, cfg.get("reserve_risk_pctile_lookback_d", 1460)) * 100
    return out


# --------------------------------------------------------------------------- #
# miner cycle: hash ribbons + Puell multiple (Tier-1)
# --------------------------------------------------------------------------- #
def miner(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Hash Ribbons (SMA30<SMA60 hashrate = capitulation, cross-back = recovery)
    and Puell (issuance_usd vs its 365d mean). Both are historically reliable
    BOTTOM detectors with 2010-> depth."""
    idx = inputs["price"].index
    out = pd.DataFrame(index=idx)
    hr = inputs.get("hashrate")
    if hr is not None:
        h = hr.reindex(idx).ffill()
        ma_f = h.rolling(cfg["hash_fast_d"]).mean()
        ma_s = h.rolling(cfg["hash_slow_d"]).mean()
        capit = (ma_f < ma_s)
        out["hash_ribbon_capit"] = capit.astype(float).where(ma_s.notna())
        recovery = capit.shift(1).fillna(False) & (~capit)  # first cross back up
        out["hash_ribbon"] = np.where(capit, "capitulation",
                             np.where(recovery, "recovery", "normal"))
    iss = inputs.get("issuance_usd")
    if iss is not None:
        i = iss.reindex(idx).ffill()
        out["puell"] = i / i.rolling(cfg["puell_window_d"],
                                     min_periods=cfg["puell_min_periods_d"]).mean()
    return out


# --------------------------------------------------------------------------- #
# cost-basis levels: STH realized price / realized price (Tier-1)
# --------------------------------------------------------------------------- #
def cost_basis(inputs: dict, cfg: dict) -> pd.DataFrame:
    """STH realized price is the most-watched bull/bear pivot. Emit the level
    (for the chart) and the distance ratio (signal candidate)."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    sth = inputs.get("sth_realized_price")
    if sth is not None:
        s = sth.reindex(idx).ffill(limit=cfg["sth_ffill_limit_d"])
        out["sth_cost_basis"] = s
        out["sth_cb_ratio"] = close / s - 1
    rp = inputs.get("realized_price")
    if rp is not None:
        out["realized_price"] = rp.reindex(idx).ffill(limit=cfg["sth_ffill_limit_d"])
    return out


# --------------------------------------------------------------------------- #
# options structure: DVOL / VRP (calibratable) + Deribit snapshot (Tier-2)
# --------------------------------------------------------------------------- #
def options(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Forward-looking vol layer (research/VECTOR_PROVIDER_RECON.md). DVOL (the
    Deribit 'crypto VIX', 2021-> history) and VRP (= DVOL - realized vol) are
    calibratable signals; the per-strike structure snapshot (25d skew, term
    slope, max pain, GEX) is forward-accumulating CONTEXT — emitted so the
    dashboard can show it and it builds a backtestable history over time."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    # Realized-vol CONES + VOL-OF-VOL — full history (2014->), price-derived so it
    # survives BOTH split-halves where the implied-vol stack (DVOL ~2021) cannot.
    # rv_cone_pctile = where current RV sits in its own ~3y distribution (the cone
    # position); vol_of_vol = RV's own rolling std (regime instability). Strengthens
    # the DRAWDOWN/risk read, not 7d direction. (D-vec-RVCONE)
    rvw = cfg.get("rv_window_d", 30)
    cone_lb = cfg.get("rv_cone_lookback_d", 1095)
    rv_full = close.pct_change().rolling(rvw).std() * np.sqrt(365) * 100
    out["rv_realized"] = rv_full
    out["rv_cone_pctile"] = _pctile(rv_full, cone_lb) * 100
    vov = rv_full.rolling(rvw).std()
    out["vol_of_vol"] = vov
    out["vov_pctile"] = _pctile(vov, cone_lb) * 100
    dvol = inputs.get("dvol")
    if dvol is not None:
        dv = dvol.reindex(idx).ffill(limit=3)
        out["dvol"] = dv
        out["dvol_pctile"] = _pctile(dv, cfg["dvol_pctile_lookback_d"]) * 100
        out["realized_vol"] = rv_full   # full-history RV (was DVOL-branch-only)
        out["vrp"] = (dv - rv_full).ewm(span=cfg["vrp_smooth_d"], adjust=False).mean()
    snap = inputs.get("options_structure")
    if snap is not None and not snap.empty:
        o = snap.copy()
        o.index = pd.to_datetime(o.index)
        for c in ("skew_25d", "rr_25d", "term_slope_30_90", "atm_iv_30d",
                  "put_call_oi_ratio", "max_pain", "gex_per_1pct_usd",
                  "skew_term", "basis_front_ann", "basis_ann", "basis_slope",
                  "gamma_flip", "dist_to_flip_pct", "gamma_regime"):
            if c in o.columns:
                out[c] = o[c].reindex(idx).ffill()
    return out


# --------------------------------------------------------------------------- #
# leverage / liquidation layer (Tier-2): OI crowding + funding stress
# --------------------------------------------------------------------------- #
def leverage(inputs: dict, cfg: dict) -> pd.DataFrame:
    """The reflexive-leverage state CoinGlass sells, rebuilt from the 15-exchange
    BGeometrics OI + aggregate funding we already store (research/
    VECTOR_PROVIDER_RECON.md). oi_mcap_ratio = froth; oi_price_divergence = OI
    building faster than price (crowded/leveraged); funding_z = positioning
    extremity; leverage_stress blends them into a liquidation-cascade gauge.
    ~2yr depth -> confirmation, not a calibration anchor."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)

    oi_df = inputs.get("open_interest_df")
    oi_total = None
    if oi_df is not None and not oi_df.empty:
        core = [c for c in cfg["oi_venues"] if c in oi_df.columns]
        if core:
            oi = oi_df[core].copy()
            oi.index = pd.to_datetime(oi.index)
            oi = oi.reindex(idx).ffill(limit=5)
            oi_total = oi.sum(axis=1, min_count=max(1, len(core) // 2))
            out["oi_total_usd"] = oi_total
            mcap = inputs.get("mcap")
            if mcap is not None:
                ratio = oi_total / mcap.reindex(idx).ffill()
                out["oi_mcap_ratio"] = ratio
                out["oi_mcap_pctile"] = _pctile(ratio, cfg["pctile_lookback_d"]) * 100
            n = cfg["change_window_d"]
            oi_chg = oi_total.pct_change(n)
            out["oi_change"] = oi_chg
            # OI rising while price isn't = leverage building into a stale move
            out["oi_price_divergence"] = oi_chg - close.pct_change(n)

    funding = inputs.get("funding")
    funding_z = None
    if funding is not None:
        f = funding.reindex(idx).ffill(limit=3)
        out["funding_rate"] = f
        out["funding_annual_pct"] = f * 3 * 365 * 100  # 8h interval -> annualized %
        w = cfg["funding_z_window_d"]
        funding_z = (f - f.rolling(w, min_periods=60).mean()) / f.rolling(w, min_periods=60).std()
        out["funding_z"] = funding_z

    parts, weights = [], []
    if "oi_mcap_pctile" in out:
        parts.append(out["oi_mcap_pctile"] / 100); weights.append(cfg["stress_oi_pctile_w"])
    if funding_z is not None:
        parts.append((funding_z.abs() / 3).clip(0, 1)); weights.append(cfg["stress_funding_w"])
    if "oi_change" in out:
        parts.append(out["oi_change"].clip(0, 0.5) / 0.5); weights.append(cfg["stress_oi_rise_w"])
    if parts:
        stacked = pd.concat(parts, axis=1)
        wsum = stacked.notna().mul(weights, axis=1).sum(axis=1)
        out["leverage_stress"] = (stacked.mul(weights, axis=1).sum(axis=1, min_count=1)
                                  / wsum.replace(0, np.nan) * 100).clip(0, 100)
    return out


# --------------------------------------------------------------------------- #
# New-factor hunt: cycle clock / positioning / cross-asset correlation
# (research/VECTOR_NEW_FACTORS.md — three orthogonal axes the model lacked)
# --------------------------------------------------------------------------- #
def cycle_clock(inputs: dict, cfg: dict) -> pd.DataFrame:
    """The pure TIME axis the model completely lacked: where we are in the ~4yr
    halving cycle. Deterministic (zero data dependency), maximally orthogonal to
    every price/on-chain factor. A soft PRIOR (only n=3 completed cycles) — used
    to tilt, never to trigger."""
    idx = pd.to_datetime(inputs["price"].index)
    hv = pd.to_datetime(pd.Index(cfg["halving_dates"])).sort_values()
    pos = np.searchsorted(hv.values, idx.values, side="right") - 1
    ds = np.where(pos >= 0,
                  (idx.values - hv.values[np.clip(pos, 0, len(hv) - 1)]) / np.timedelta64(1, "D"),
                  np.nan)
    out = pd.DataFrame(index=inputs["price"].index)
    out["days_since_halving"] = ds
    out["cycle_pct"] = (pd.Series(ds, index=out.index) / cfg["cycle_len_d"]).clip(0, 1.4)
    def _phase(p):
        if pd.isna(p):
            return "—"
        if p < cfg["accumulation_end"]:
            return "accumulation"
        if p < cfg["markup_end"]:
            return "markup"
        if p < cfg["markdown_end"]:
            return "markdown"
        return "recovery"
    out["cycle_phase"] = out["cycle_pct"].map(_phase)
    return out


def positioning(inputs: dict, cfg: dict) -> pd.DataFrame:
    """CME COT net-spec positioning — already collected (cot_bitcoin) but never
    wired in. The only REGULATED, real-money, weekly positioning input (everything
    else is offshore perp/options). Crowded-spec extremes are contrarian."""
    idx = inputs["price"].index
    out = pd.DataFrame(index=idx)
    cot = inputs.get("cot_net_pct")
    if cot is not None:
        c = cot.reindex(idx).ffill(limit=cfg["ffill_limit_d"])
        out["cot_net_pct"] = c
        out["cot_z"] = _zscore(c, cfg["z_window_d"])
    return out


def stablecoin_tide(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Crypto-native liquidity TIDE: the GROWTH RATE of aggregate stablecoin supply
    = the pace new capital is minted INTO crypto. Orthogonal to the FIAT net-liquidity
    / global-M2 overlay (central-bank money) — this is money that already crossed into
    crypto. A z-scored growth-impulse, de-trended so 2017 hyper-growth and the 2024
    base are comparable. (D-vec-STBL) The deepest crypto-native-liquidity series (2017->);
    NOT the SSR ratio / BFI leg that already use the level. Calibrated as a tide (want +1)."""
    stbl = inputs.get("stablecoins")
    idx = inputs["price"]["close"].index
    out = pd.DataFrame(index=idx)
    if stbl is None:
        return out
    s = stbl[stbl.columns[0]] if hasattr(stbl, "columns") else stbl
    sm = s.reindex(idx).ffill()
    gw = cfg.get("stbl_growth_window_d", 30)
    lb = cfg.get("stbl_z_lookback_d", 365)
    out["stbl_mcap_bn"] = (sm / 1e9).round(1)
    g = sm.pct_change(gw) * 100
    out["stbl_growth"] = g
    mu = g.rolling(lb, min_periods=150).mean()
    sd = g.rolling(lb, min_periods=150).std().replace(0, np.nan)
    out["stbl_growth_z"] = ((g - mu) / sd).clip(-4, 4)
    out["stbl_regime"] = np.where(out["stbl_growth_z"] > 0.5, "expanding",
                          np.where(out["stbl_growth_z"] < -0.5, "contracting", "neutral"))

    # Stablecoin PEG-deviation VETO — collateral/solvency stress, ORTHOGONAL to the
    # supply tide above (issuance) and to funding/OI leverage. Max |price-1| across
    # the alive systemic majors (USDT/USDC/DAI). Event-driven (the USDC SVB break hit
    # ~390bps; normal noise is ~5-40bps) -> a binary risk veto / Gate-1, NOT a
    # calibrated factor. (D-vec-PEG)
    peg = inputs.get("stablecoin_peg")
    if peg is not None:
        ps = (peg[peg.columns[0]] if hasattr(peg, "columns") else peg).reindex(idx).ffill()
        bps = (ps * 1e4)
        watch = cfg.get("peg_watch_bps", 50)
        brk = cfg.get("peg_break_bps", 150)
        out["peg_dev_bps"] = bps.round(0)
        out["peg_state"] = np.where(bps >= brk, "break",
                            np.where(bps >= watch, "watch", "stable"))
        out["peg_stress"] = (bps >= brk).astype(float).where(bps.notna())
    return out


def cme_basis(inputs: dict, cfg: dict) -> pd.DataFrame:
    """CME (regulated) Bitcoin-futures BASIS = front-month future vs spot premium —
    the REAL-MONEY, regulated institutional carry, distinct from the offshore Deribit
    perp funding the model already has. Rich contango = leverage / positioning froth;
    backwardation = stress / forced de-risking. Daily 2017->. MEASURED: ~zero forward-
    RETURN edge (rank-IC ~0, flat across bands), so this ships as POSITIONING CONTEXT,
    NOT a calibrated predictive signal — the honest read. (D-vec-CME)"""
    fut = inputs.get("btc_future")
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    if fut is None:
        return out
    f = (fut[fut.columns[0]] if hasattr(fut, "columns") else fut).reindex(idx).ffill(limit=3)
    basis = (f / close - 1.0) * 100.0
    out["cme_basis"] = basis
    out["cme_basis_ann"] = basis * cfg.get("ann_mult", 12)          # ~front-month -> annualized (approx)
    out["cme_basis_pctile"] = _pctile(basis, cfg.get("pctile_lookback_d", 365)) * 100
    out["cme_basis_regime"] = np.where(basis > cfg.get("froth_pct", 0.7), "contango",
                              np.where(basis < cfg.get("stress_pct", -0.2), "backwardation", "flat"))
    return out


def global_liquidity(inputs: dict, cfg: dict) -> pd.DataFrame:
    """US + China M2 GROWTH impulse — the broad-money read our Fed-balance-sheet
    net-liquidity lacks, and adds the PBoC dimension. Combined as a weighted
    average of the two YoY growth rates (unit-free, no FX). EZ/JP/UK FRED M2 are
    discontinued, so US+China are the two largest LIVE blocs. Money supply leads
    BTC ~10 weeks → a slow strategic tide, not a trigger."""
    idx = inputs["price"].index
    out = pd.DataFrame(index=idx)
    parts = {}
    us = inputs.get("us_m2")
    if us is not None:
        u = us.copy()
        u.index = pd.to_datetime(u.index)
        parts["us"] = (u.pct_change(12) * 100).sort_index().reindex(idx, method="ffill")  # monthly YoY
    cn = inputs.get("china_m2_yoy")
    if cn is not None:
        c = cn.copy()
        c.index = pd.to_datetime(c.index)
        parts["china"] = c.sort_index().reindex(idx, method="ffill")
    if parts:
        w = {"us": cfg["us_weight"], "china": 1 - cfg["us_weight"]}
        dd = pd.DataFrame(parts)
        ww = pd.Series({k: w[k] for k in dd.columns})
        wsum = dd.notna().mul(ww, axis=1).sum(axis=1)
        out["global_m2_yoy"] = dd.mul(ww, axis=1).sum(axis=1, min_count=1) / wsum.replace(0, np.nan)
        out["global_m2_accel"] = out["global_m2_yoy"].diff(cfg["accel_window_d"])
        out["global_liq_regime"] = np.where(out["global_m2_yoy"] > cfg["expanding_thresh"],
                                            "expanding", "contracting")
    return out


def behaviour(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Spending-behaviour / coin-age axis — the single factor family the model
    completely lacked. VDD Multiple (checkonchain 2011->) = Value-Days-Destroyed
    vs a long baseline: HIGH (>~2.9) = old/long-dormant coins waking = LTH
    distribution (tops); LOW (<~0.75) = dormant network = accumulation. Orthogonal
    to the price-vs-cost-basis valuation cluster (same MVRV can have opposite VDD)."""
    idx = inputs["price"].index
    out = pd.DataFrame(index=idx)
    vdd = inputs.get("vdd_multiple")
    if vdd is not None:
        v = vdd.replace([np.inf, -np.inf], np.nan).reindex(idx).ffill(limit=5)
        out["vdd_multiple"] = v
        out["vdd_pctile"] = _pctile(v, cfg["pctile_lookback_d"]) * 100
    return out


def cross_asset_corr(inputs: dict, cfg: dict) -> pd.DataFrame:
    """BTC's rolling correlation REGIME to equities/gold/dollar — a 2nd-moment
    (co-movement) signal the all-levels macro overlay cannot express. Tells us
    WHAT BTC is being traded as: leveraged risk-asset (high SPX corr) vs
    diversifier/digital-gold (decoupled)."""
    close = inputs["price"]["close"]
    idx = close.index
    r = close.pct_change()
    w = cfg["corr_window_d"]
    out = pd.DataFrame(index=idx)
    for name, key in (("spx", "spx"), ("gold", "gold"), ("dxy", "dxy")):
        s = inputs.get(key)
        if s is not None:
            sr = s.reindex(idx).ffill(limit=3).pct_change()
            out[f"corr_{name}"] = r.rolling(w).corr(sr)
    if "corr_spx" in out:
        out["corr_spx_pctile"] = _pctile(out["corr_spx"], cfg["pctile_lookback_d"]) * 100
        out["risk_asset_regime"] = np.where(out["corr_spx"] > cfg["coupled_thresh"], "coupled",
                                   np.where(out["corr_spx"] < cfg["decoupled_thresh"],
                                            "decoupled", "mixed"))
    return out


# --------------------------------------------------------------------------- #
# IMPULSE: acceleration of momentum (Glassnode/Swissblock-style early detector)
# --------------------------------------------------------------------------- #
def impulse(inputs: dict, cfg: dict) -> pd.DataFrame:
    """The capability our model lacked. Swissblock's Impulse measures the
    'exponential price structure' (the RATE OF TREND / acceleration), not the
    level — it spots the START and EXHAUSTION of a move (research/
    VECTOR_PROVIDER_RECON.md + the impulse research). Construction (single-asset,
    free): z-scored MACD-histogram = the denoised 2nd derivative of price;
    Kaufman efficiency ratio gates out chop (a MULTIPLIER, not a vote); a
    positioning impulse (funding+OI shock) adds an orthogonal, often-earlier
    input. winsorized to +/-3."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)

    macd = _ema(close, 12) - _ema(close, 26)
    macd_hist = macd - _ema(macd, 9)
    accel = _zscore(macd_hist, cfg["accel_z_window_d"])

    n = cfg["er_window_d"]
    er = (close.diff(n).abs() / close.diff().abs().rolling(n).sum().replace(0, np.nan)).clip(0, 1)

    # weight-normalized mean that SKIPS missing parts, so the deep (2014->) accel
    # core is never NaN-poisoned by the shallow (2023->) positioning impulse.
    parts = pd.DataFrame({"accel": accel})
    weights = {"accel": cfg["accel_w"]}
    pos_parts = []
    funding = inputs.get("funding")
    if funding is not None:
        pos_parts.append(_zscore(funding.reindex(idx).ffill(limit=3).diff(), cfg["pos_z_window_d"]))
    oi_df = inputs.get("open_interest_df")
    if oi_df is not None and not oi_df.empty:
        oi = oi_df.copy()
        oi.index = pd.to_datetime(oi.index)
        oi_total = oi.reindex(idx).ffill(limit=5).sum(axis=1, min_count=1)
        pos_parts.append(_zscore(oi_total.diff(), cfg["pos_z_window_d"]))
    if pos_parts:
        parts["pos"] = pd.concat(pos_parts, axis=1).mean(axis=1, skipna=True).clip(-3, 3)
        weights["pos"] = cfg["pos_w"]
    w = pd.Series(weights)
    wsum = parts.notna().mul(w, axis=1).sum(axis=1)
    core = parts.mul(w, axis=1).sum(axis=1, min_count=1) / wsum.replace(0, np.nan)

    imp = (er * core).clip(-3, 3)
    out["impulse"] = imp
    db = 0.15
    out["impulse_state"] = np.where(imp > db, "positive",
                           np.where(imp < -db, "negative", "neutral"))
    # breadth/participation proxy: rolling % of positive-impulse days (single-asset
    # stand-in for Swissblock's "% of top-350 in negative impulse").
    pw = cfg["participation_window_d"]
    out["impulse_pos_pct"] = (imp > 0).rolling(pw, min_periods=pw // 2).mean() * 100
    out["efficiency_ratio"] = er
    return out


# --------------------------------------------------------------------------- #
# on-chain regime: Coinbase Premium / SSR oscillator / MPI (CryptoQuant-style)
# --------------------------------------------------------------------------- #
def onchain_regime(inputs: dict, cfg: dict) -> pd.DataFrame:
    """CryptoQuant's signature on-chain-demand metrics, reproduced from free data
    (research/VECTOR_PROVIDER_RECON.md). Coinbase Premium = US/institutional
    demand (Coinbase−Binance, via bgeo); SSR oscillator = stablecoin dry powder
    (low SSR = buying power); MPI = miner distribution (outflow vs its 365d mean).
    The wallet-labeled exchange Netflow/Whale-Ratio are CryptoQuant's true moat —
    not reproduced; these three are the derivable ones."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)

    prem = inputs.get("coinbase_premium")
    if prem is not None:
        p = prem.reindex(idx).ffill(limit=3)
        out["coinbase_premium"] = p
        # EMA tames the brief dislocation spikes (±10%+) in the raw index
        out["coinbase_premium_ema"] = _ema(p.clip(-5, 5), cfg["premium_smooth_d"])

    ssr = inputs.get("ssr")
    if ssr is not None:
        s = ssr.reindex(idx).ffill(limit=5)
        out["ssr"] = s
        w = cfg["ssr_window_d"]
        z = (s - s.rolling(w, min_periods=90).mean()) / s.rolling(w, min_periods=90).std()
        out["ssr_oscillator"] = (-z).clip(-3, 3)  # high = low SSR = dry powder = bullish

    md = inputs.get("miner_df")
    col = "miner_sell_pressure_minerOutflowBtc"
    if md is not None and col in md.columns:
        of = md[col].copy()
        of.index = pd.to_datetime(of.index)
        outflow_usd = of.reindex(idx).ffill(limit=3) * close
        ma = outflow_usd.rolling(cfg["mpi_window_d"], min_periods=cfg["mpi_min_periods_d"]).mean()
        out["mpi"] = outflow_usd / ma.replace(0, np.nan)
    return out


def etf_flow(inputs: dict, cfg: dict) -> pd.DataFrame:
    """US spot-ETF net flows — the institutional bid Swissblock tracks in 'Risk
    Index & ETF Net Flows' (the Glassnode-sourced bgeo series, 2024-01-> i.e. since
    the ETFs launched). Net creations/redemptions in BTC: sustained positive =
    accumulation (the new structural buyer), negative = distribution. ETF-era only
    (~2.4y) -> a CONFIRMATION / context flow gauge, never a deep calibration anchor
    (house rule). Emits the smoothed flow regime, an extremity z (vs recent norm),
    the accumulation/distribution state, and a cumulative-holdings proxy."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    ef = inputs.get("etf_flow")
    if ef is None:
        return out
    f = ef.reindex(idx)                                    # daily net flow, BTC (NaN pre-launch)
    out["etf_flow_btc"] = f
    out["etf_flow_usd_mn"] = (f * close) / 1e6            # USD millions (panel-friendly)
    sm = f.rolling(cfg["smooth_d"], min_periods=cfg["min_periods_d"]).sum()
    out["etf_flow_sum"] = sm                              # N-day net flow = the regime
    w, mp = cfg["z_window_d"], cfg["z_min_periods_d"]
    mu = sm.rolling(w, min_periods=mp).mean()
    sd = sm.rolling(w, min_periods=mp).std()
    out["etf_flow_z"] = ((sm - mu) / sd).clip(-3, 3)     # extremity vs recent norm
    out["etf_flow_cum"] = f.cumsum()                     # holdings proxy (BTC) since launch
    out["etf_flow_state"] = _hysteresis_tri(
        out["etf_flow_z"], cfg["state_enter_z"], cfg["state_exit_z"],
        labels=("distribution", "neutral", "accumulation"))
    return out


# --------------------------------------------------------------------------- #
# macro liquidity / risk-appetite overlay (Tier-3)
# --------------------------------------------------------------------------- #
def macro_overlay(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Strategic macro tailwind/headwind for BTC, from data the macro dashboard
    already collects (research/VECTOR_PROVIDER_RECON.md Tier-3). Net liquidity
    (WALCL−RRP−TGA) RATE OF CHANGE is the headline driver — research-confirmed
    BTC tracks the *change* in liquidity, not the level; real yields, HY credit
    spreads, VIX and the dollar are the risk-appetite confirmers. Deep history
    (BTC 2014->), so this can be a genuine strategic signal."""
    idx = inputs["price"].index

    def s(key):
        v = inputs.get(key)
        if v is None:
            return None
        if hasattr(v, "columns"):
            v = v.iloc[:, 0]
        v = v.copy()
        v.index = pd.to_datetime(v.index)
        return v.reindex(idx).ffill(limit=7)

    out = pd.DataFrame(index=idx)
    drivers = {}
    walcl, rrp, tga = s("walcl"), s("rrp"), s("tga")
    if walcl is not None and tga is not None:
        netliq = walcl / 1000 - (rrp.fillna(0) if rrp is not None else 0) - tga / 1000
        out["net_liquidity_bn"] = netliq
        roc = netliq.pct_change(cfg["netliq_roc_window_d"])
        out["net_liq_roc"] = roc * 100
        drivers["liquidity"] = np.tanh(roc / cfg["netliq_roc_scale"])
    ry = s("real_yield")
    if ry is not None:
        out["real_yield"] = ry
        drivers["real_yield"] = -np.tanh(ry.diff(cfg["yield_chg_window_d"]) / cfg["yield_chg_scale"])
    oas = s("hy_oas")
    if oas is not None:
        out["hy_oas"] = oas
        drivers["credit"] = (0.5 - _pctile(oas, cfg["pctile_lookback_d"])) * 2
    vix = s("vix")
    if vix is not None:
        out["vix"] = vix
        drivers["vix"] = (0.5 - _pctile(vix, cfg["pctile_lookback_d"])) * 2
    dxy = s("dxy")
    if dxy is not None:
        out["dxy"] = dxy
        drivers["dxy"] = -np.tanh(dxy.pct_change(cfg["dxy_roc_window_d"]) / cfg["dxy_roc_scale"])

    if drivers:
        dd = pd.DataFrame(drivers)
        w = cfg["weights"]
        ww = pd.Series({k: w.get(k, 1.0) for k in dd.columns})
        wsum = dd.notna().mul(ww, axis=1).sum(axis=1)
        score = (dd.mul(ww, axis=1).sum(axis=1, min_count=1) / wsum.replace(0, np.nan)).clip(-1, 1)
        out["macro_score"] = score
        out["macro_regime"] = _hysteresis_tri(score, cfg["enter"], cfg["exit"],
                                              labels=("headwind", "neutral", "tailwind"))
    return out


# --------------------------------------------------------------------------- #
# contrarian capitulation / euphoria overlay (Tier-1)
# --------------------------------------------------------------------------- #
def market_extreme(inputs: dict, val: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Vote of orthogonal extremes — NUPL, supply-in-profit, Fear&Greed, MVRV-Z.
    >=min_votes in one tail flags a contrarian regime: this is what lets the
    dashboard tell an early-bull pullback (risk-off) from a cycle-bottom
    capitulation (accumulate) — the Risk Index calibration already shows the
    forward-return U-shape this resolves."""
    idx = inputs["price"].index
    capit = pd.DataFrame(index=idx)
    euph = pd.DataFrame(index=idx)

    nupl = inputs.get("nupl")
    if nupl is not None:
        n = nupl.reindex(idx).ffill()
        capit["nupl"] = n < cfg.get("nupl_capitulation", 0.0)
        euph["nupl"] = n > cfg.get("nupl_euphoria", 0.65)
    sip = inputs.get("supply_in_profit_pct")
    if sip is not None:
        s = sip.reindex(idx).ffill(limit=5)
        capit["sip"] = s < cfg["sip_capitulation"]
        euph["sip"] = s > cfg["sip_euphoria"]
    fg = inputs.get("fear_greed")
    if fg is not None:
        f = fg.reindex(idx).ffill(limit=3)
        capit["fg"] = f < cfg["fg_capitulation"]
        euph["fg"] = f > cfg["fg_euphoria"]
    if "mvrv_z" in val:
        z = val["mvrv_z"]
        capit["z"] = z < cfg.get("z_under", 0.0)
        euph["z"] = z > cfg.get("z_over", 3.5)

    out = pd.DataFrame(index=idx)
    if capit.empty:
        return out
    cv = capit.sum(axis=1, min_count=1)
    ev = euph.sum(axis=1, min_count=1)
    navail = capit.notna().sum(axis=1).replace(0, np.nan)
    out["extreme_score"] = ((ev - cv) / navail).clip(-1, 1)  # -1 capit .. +1 euph
    mn = cfg["min_votes"]
    out["market_extreme"] = np.where(cv >= mn, "capitulation",
                            np.where(ev >= mn, "euphoria", "normal"))
    return out


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
    # Tier-1 accuracy upgrade: standalone valuation / miner / cost-basis axes +
    # contrarian overlay (research/VECTOR_ACCURACY_UPGRADE.md). Measured before
    # being blended into the composites above.
    va = valuation(inputs, cfg["valuation"])
    mn = miner(inputs, cfg["miner"])
    cb = cost_basis(inputs, cfg["cost_basis"])
    ex = market_extreme(inputs, va, {**cfg["valuation"], **cfg["extreme"]})
    op = options(inputs, cfg["options"])
    lv = leverage(inputs, cfg["leverage"])
    ma = macro_overlay(inputs, cfg["macro"])
    oc = onchain_regime(inputs, cfg["onchain"])
    ef = etf_flow(inputs, cfg["etf_flow"])
    im = impulse(inputs, cfg["impulse"])
    cc = cycle_clock(inputs, cfg["cycle_clock"])
    po = positioning(inputs, cfg["positioning"])
    xa = cross_asset_corr(inputs, cfg["cross_asset"])
    bh = behaviour(inputs, cfg["cross_asset"])
    gl = global_liquidity(inputs, cfg["global_liquidity"])
    sc = stablecoin_tide(inputs, cfg["global_liquidity"])  # crypto-native liquidity tide
    cm = cme_basis(inputs, cfg.get("cme_basis", {}))       # regulated institutional carry (context)
    # Tier-1b: blend the confirmed valuation tails into allocation (gated by the
    # allocation backtest below).
    al = allocation(mom["momentum"], rk["risk_index"], cfg["allocation"], va)

    out = pd.concat([inputs["price"][["close"]], mom, rk, bf, st, gg, al,
                     va, mn, cb, ex, op, lv, ma, oc, ef, im, cc, po, xa, bh, gl, sc, cm], axis=1)
    out["cycle_position"] = cycle_stage(mom["momentum"], rk["risk_index"])
    alt = btc_vs_alts(inputs, cfg["btc_vs_alts"])
    if alt is not None:
        out["alt_cycle_leader"] = alt
    out["market_mode"] = tactical(inputs, rk["risk_index"], cfg["tactical"])
    out["composite_state"] = composite_state(out, cfg["composite"])
    out["composite_context"] = composite_context(out, cfg["composite"])
    return out
