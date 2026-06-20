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


# --------------------------------------------------------------------------- #
# Point-4: size by CONVICTION, cap RISK. Conviction used to be a UI label only —
# a thin TOSS-UP and a strong EDGE both sized the grid to 1.0. These two helpers
# turn it into actual SIZE (a continuous multiplier on the grid) and add an
# ENFORCED drawdown brake (today MaxDD is only a MEASURED backtest stat). Both
# modulate magnitude only; the (momentum, risk) grid still owns DIRECTION.
# --------------------------------------------------------------------------- #
def conviction_multiplier(score, cfg: dict):
    """Continuous position-size multiplier in [floor, 1] from a directional-confidence
    score in [0,1] (0.5 = a 50/50 coin-flip). The score's distance ABOVE the coin-flip
    is the same honest ladder the dashboard's conviction layer shows — TOSS-UP (no
    edge) / LEAN / EDGE — and the multiplier ramps the grid size `conviction_floor`->1
    linearly across it: an EDGE setup sizes the full grid, a TOSS-UP only the floor.
    Monotone non-decreasing in the score (so EDGE ≥ LEAN ≥ TOSS-UP). Accepts a scalar,
    ndarray or pandas Series and returns the same kind."""
    floor = float(cfg.get("conviction_floor", 0.5))
    toss = float(cfg.get("conviction_toss", 0.05))
    edge = float(cfg.get("conviction_edge", 0.30))
    lean = np.clip(np.asarray(score, dtype=float) - 0.5, 0.0, None)   # bullish edge above coin-flip
    ramp = np.clip((lean - toss) / max(edge - toss, 1e-9), 0.0, 1.0)  # 0 at TOSS-UP .. 1 at EDGE
    mult = np.clip(floor + (1.0 - floor) * ramp, floor, 1.0)
    if isinstance(score, pd.Series):
        return pd.Series(mult, index=score.index, name="conviction_mult")
    return mult if mult.ndim else float(mult)


def conviction_tier(score, cfg: dict) -> str:
    """TOSS-UP / LEAN / EDGE label for a scalar directional-confidence score — the
    ladder that backs conviction_multiplier(), kept beside it so size and label can
    never drift apart (the bug this fix closes)."""
    toss = float(cfg.get("conviction_toss", 0.05))
    edge = float(cfg.get("conviction_edge", 0.30))
    lean = max(float(score) - 0.5, 0.0)
    return "TOSS-UP" if lean <= toss else ("LEAN" if lean <= edge else "EDGE")


def drawdown_brake(alloc: pd.Series, ret: pd.Series, cfg: dict) -> pd.Series:
    """ENFORCED max-drawdown cap: tighten exposure as the strategy's OWN equity falls
    further below its high-water mark — a live position cap, not just a backtest stat.
    Path-dependent (the cap feeds back into the equity it is measured on), so it is
    simulated day-by-day. No look-ahead: the cap that scales tomorrow's position uses
    only the drawdown realized THROUGH today, and equity is advanced with yesterday's
    position (the same shift(1) timing as the backtest engine). The cap is
    `clip(1 - decay * max(0, drawdown - threshold), floor, 1)`, so it is 1.0 until the
    strategy is `dd_threshold` underwater, then tightens linearly to `dd_floor`."""
    thr = float(cfg.get("dd_threshold", 0.25))
    decay = float(cfg.get("dd_decay", 1.0))
    floor = float(cfg.get("dd_floor", 0.40))
    a = alloc.to_numpy(dtype=float)
    r = ret.reindex(alloc.index).to_numpy(dtype=float)
    out = a.copy()
    equity, peak, prev_pos = 1.0, 1.0, 0.0
    for i in range(len(a)):
        ri = r[i] if np.isfinite(r[i]) else 0.0
        equity *= 1.0 + prev_pos * ri              # realize today on yesterday's position
        if equity > peak:
            peak = equity
        dd = equity / peak - 1.0                    # <= 0, known only at end of day i
        cap = min(1.0, max(floor, 1.0 - decay * max(0.0, (-dd) - thr)))
        if np.isnan(a[i]):
            out[i], prev_pos = a[i], 0.0
        else:
            out[i] = a[i] * cap
            prev_pos = out[i]
    return pd.Series(out, index=alloc.index)


def allocation(mom: pd.Series, risk_idx: pd.Series, cfg: dict,
               val: pd.DataFrame | None = None,
               close: pd.Series | None = None) -> pd.DataFrame:
    """Strategy grids on (momentum, risk) -> {0, 0.5, 1.0}, then Point-4 sizing:
    a CONTINUOUS conviction multiplier scales the grid (EDGE sizes larger than a LEAN
    than a TOSS-UP — size BY conviction, not just label it) and, when `close` is given,
    an ENFORCED drawdown brake caps exposure as the strategy goes underwater (cap risk).
    Both are config-gated (vector.allocation.*) and modulate SIZE only — the grid still
    owns direction, and the whipsaw guard runs on the DISCRETE grid before scaling.
    Backward-compatible: omit `close` and leave the new keys unset for the legacy
    stepped grid."""
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
    conv_on = cfg.get("conviction_sizing", True)
    brake_on = cfg.get("drawdown_brake", True) and close is not None
    # directional-confidence proxy (the dashboard's regime-cell p_bull isn't a
    # historical series, so reuse cycle_position — momentum carries direction, risk
    # drags it); fill the warm-up gap with a coin-flip (sizes the floor, never NaN).
    score = cycle_stage(mom, risk_idx).fillna(0.5) if conv_on else None
    ret = close.pct_change() if brake_on else None
    for name, v in cfg["variants"].items():
        full = (mom > v["mom_full"]) & (risk_idx < v["risk_full"])
        half = (mom > v["mom_half"]) & (risk_idx < v["risk_half"])
        raw = pd.Series(np.where(full, 1.0, np.where(half, 0.5, 0.0)), index=mom.index)
        if deep_value is not None:
            raw = raw.mask(deep_value, raw.clip(lower=0.5))   # accumulate the bottom
            raw = raw.mask(overvalued, raw.clip(upper=0.5))   # trim the cycle top
        raw = _confirm(raw, cfg["confirm_days"])              # whipsaw guard on the DISCRETE grid
        if conv_on:
            raw = raw * conviction_multiplier(score, cfg)     # size by conviction (magnitude only)
        if brake_on:
            raw = drawdown_brake(raw, ret, cfg)               # cap risk while underwater
        out[f"alloc_{name}"] = raw.clip(0.0, 1.0)
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
        for c in ("skew_25d", "rr_25d", "term_slope_30_90", "atm_iv_7d", "atm_iv_30d",
                  "atm_iv_90d", "put_call_oi_ratio", "max_pain", "gex_per_1pct_usd",
                  "skew_term", "basis_front_ann", "basis_ann", "basis_slope",
                  "gamma_flip", "dist_to_flip_pct", "gamma_regime"):
            if c in o.columns:
                out[c] = o[c].reindex(idx).ffill()

    # --- VRP regime: variance-risk-premium z + state (deep 2021->, calibratable). vol_rich
    #     = implied >> delivered (options expensive → sell-vol / vol mean-reverts down);
    #     vol_cheap = implied underpricing risk (cheap → vol-expansion / drawdown tail). ---
    if "vrp" in out:
        out["vrp_z"] = _zscore(out["vrp"], cfg.get("vrp_z_window_d", 365)).clip(-4, 4)
        rich, cheap = cfg.get("vrp_rich_z", 0.7), cfg.get("vrp_cheap_z", -0.7)
        out["vrp_state"] = np.where(out["vrp_z"] >= rich, "vol_rich",
                           np.where(out["vrp_z"] <= cheap, "vol_cheap", "vol_fair"))
    # --- DVOL-implied forward expected-move band — the options leg of the RISK model:
    #     ±1σ price band over the horizon from the implied (annualized) vol. ---
    if "dvol" in out:
        h = int(cfg.get("expected_move_horizon_d", 30))
        sigma = out["dvol"] / 100.0 * np.sqrt(h / 365.0)
        out["expected_move_pct"] = sigma * 100.0
        out["em_upper"] = close * (1 + sigma)
        out["em_lower"] = close * (1 - sigma)
    # --- IV term structure + 25Δ skew (snapshot context; forward-accumulating) ---
    if "atm_iv_30d" in out and "atm_iv_90d" in out:
        term = out["atm_iv_90d"] - out["atm_iv_30d"]
        out["iv_term_spread"] = term
        bw = cfg.get("term_backwardation_pct", -1.0)
        out["iv_term_state"] = np.where(term <= bw, "backwardation",
                               np.where(term >= -bw, "contango", "flat"))
    if "rr_25d" in out:
        out["skew_state"] = np.where(out["rr_25d"] < -1.0, "put_bid",
                            np.where(out["rr_25d"] > 1.0, "call_bid", "balanced"))
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

    # OKX rubik retail positioning — DISPLAY-ONLY context columns (NOT scored: they
    # are deliberately kept OUT of the parts/weights leverage_stress block above and
    # out of allocation/regime). rubik history is shallow -> short rolling windows.
    lsr = inputs.get("okx_ls_ratio")
    if lsr is not None:
        s = lsr.reindex(idx).ffill(limit=3)
        out["okx_ls_ratio"] = s
        out["okx_ls_ratio_pctile"] = _pctile(s, cfg.get("okx_pctile_lookback_d", 180)) * 100
        out["okx_ls_ratio_z"] = _zscore(s, cfg.get("okx_z_window_d", 90))
    tk = inputs.get("okx_taker_buy")
    if tk is not None:
        s = tk.reindex(idx).ffill(limit=3)
        out["okx_taker_buy"] = s
        out["okx_taker_buy_pctile"] = _pctile(s, cfg.get("okx_pctile_lookback_d", 180)) * 100
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


def cycle_phase_clock(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Bottom-anchored 1064/364-day cycle-time structure — the chart's "1064 days up /
    364 days down" theory. A SECOND, tighter view of the same ~4yr axis as cycle_clock(),
    anchored on the OBSERVED cycle lows/highs rather than the halving. Measured fit vs the
    repo's own spliced price history (objective global extrema, window-insensitive): up-legs
    1067/1059/1050d (theory 1064), down-legs 364/378d (theory 364) -> mean-abs-err 7.2d, but
    only n=3 cycles (in-sample, 2-param) — so a soft CONTEXT/PRIOR, it tilts, never triggers.
    TIMING ONLY — not amplitude, and NO price target. PIT-honest: each row reads only the
    pivots that had occurred on/before that date (no look-ahead)."""
    px = inputs["price"]
    close = px["close"]
    idx = pd.to_datetime(px.index)
    out = pd.DataFrame(index=px.index)

    pivots = sorted([(pd.Timestamp(d), "bottom") for d in cfg["bottoms"]]
                    + [(pd.Timestamp(d), "top") for d in cfg["tops"]], key=lambda x: x[0])
    if not pivots:
        return out
    up, dn = float(cfg["up_days"]), float(cfg["down_days"])
    overdue = float(cfg.get("overdue_pct", 1.10))
    # compare as integer-nanosecond stamps (Timestamp.value is always ns, dodging
    # datetime64 unit mismatches between the index [us/ns] and the pivot dates)
    pv_ns = np.array([p[0].value for p in pivots], dtype="int64")
    pv_price = [float(close.asof(p[0])) if pd.notna(close.asof(p[0])) else np.nan for p in pivots]
    idx_ns = np.fromiter((t.value for t in idx), dtype="int64", count=len(idx))
    pos = np.searchsorted(pv_ns, idx_ns, side="right") - 1  # last pivot on/before each row

    phase, anchor, length, days_in, nxt, kind, status = ([] for _ in range(7))
    cval = close.values
    for i, p in enumerate(pos):
        if p < 0:                                   # before the first anchor
            phase.append(None); anchor.append(None); length.append(np.nan)
            days_in.append(np.nan); nxt.append(None); kind.append(None); status.append(None)
            continue
        pdate, pkind = pivots[p]
        is_up = (pkind == "bottom")
        ph = "markup" if is_up else "markdown"
        ln = up if is_up else dn
        di = (idx[i] - pdate).days
        npiv = pdate + pd.Timedelta(days=int(ln))
        nk = "top" if is_up else "bottom"
        # status: invalidated if price breaks the anchor's own extreme (new low under a
        # markup's low / new high over a markdown's high); else overdue past the window.
        ap = pv_price[p]
        if pd.notna(ap) and ((is_up and cval[i] < ap) or ((not is_up) and cval[i] > ap)):
            stt = "invalidated"
        elif di > ln * overdue:
            stt = "overdue"
        else:
            stt = "on_track"
        phase.append(ph); anchor.append(pdate.strftime("%Y-%m-%d")); length.append(ln)
        days_in.append(float(di)); nxt.append(npiv.strftime("%Y-%m-%d")); kind.append(nk)
        status.append(stt)

    out["cphase_phase"] = phase
    out["cphase_anchor_date"] = anchor
    out["cphase_len"] = length
    out["cphase_days_in"] = days_in
    pct = pd.Series(days_in, index=out.index) / pd.Series(length, index=out.index)
    out["cphase_pct"] = pct.clip(0, 1.4)
    out["cphase_days_left"] = (pd.Series(length, index=out.index) - pd.Series(days_in, index=out.index))
    out["cphase_next_pivot"] = nxt
    out["cphase_next_kind"] = kind
    out["cphase_status"] = status
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


def futures_carry(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Consolidated derivatives CARRY across the futures complex — one leverage-cycle
    read fusing the annualized carries already stored: CME regulated basis (2017->),
    perp funding (annualized, 2023->), and Deribit dated-future basis (snapshot). Each
    z-scored vs its own ~1y norm, then weighted-averaged. Froth = leveraged longs paying
    up across the complex (late-cycle); stress = backwardation / negative funding
    (deleveraging / capitulation). Confirmation context (leg depth varies), not a deep
    calibration anchor — the honest read."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    zw = cfg.get("z_window_d", 365)
    parts, weights = [], []

    fut = inputs.get("btc_future")
    if fut is not None:
        f = (fut[fut.columns[0]] if hasattr(fut, "columns") else fut).reindex(idx).ffill(limit=3)
        cme = (f / close - 1.0) * 100.0
        out["carry_cme_pct"] = cme
        parts.append(_zscore(cme, zw)); weights.append(cfg.get("cme_weight", 1.0))

    funding = inputs.get("funding")
    if funding is not None:
        ann = funding.reindex(idx).ffill(limit=3) * 3 * 365 * 100   # 8h funding -> annualized %
        out["carry_funding_ann"] = ann
        parts.append(_zscore(ann, zw)); weights.append(cfg.get("funding_weight", 0.8))

    snap = inputs.get("options_structure")
    if snap is not None and not snap.empty and "basis_ann" in snap.columns:
        b = snap["basis_ann"].copy()
        b.index = pd.to_datetime(b.index)
        out["carry_deribit_ann"] = b.reindex(idx).ffill(limit=7)
        parts.append(_zscore(out["carry_deribit_ann"], zw)); weights.append(cfg.get("deribit_weight", 0.6))

    if parts:
        stacked = pd.concat(parts, axis=1).clip(-4, 4)
        wsum = stacked.notna().mul(weights, axis=1).sum(axis=1)
        carry_z = (stacked.mul(weights, axis=1).sum(axis=1, min_count=1) / wsum.replace(0, np.nan))
        out["futures_carry_z"] = carry_z.clip(-4, 4)
        froth, stress = cfg.get("froth_z", 0.8), cfg.get("stress_z", -0.8)
        out["futures_carry_state"] = np.where(carry_z >= froth, "froth",
                                     np.where(carry_z <= stress, "stress", "neutral"))
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
# miner economics: hashprice (margin) + hashrate/difficulty shock — the one deep
# (2010->) NEW miner anchor (research/VECTOR_FACTOR_ROADMAP_2026 Tier-1)
# --------------------------------------------------------------------------- #
def miner_economics(inputs: dict, cfg: dict) -> pd.DataFrame:
    """The miner PROFIT-MARGIN axis the model lacked. Puell / MPI / hash-ribbons all
    read miner REVENUE or RESERVES; the missing primitive is the MARGIN (hashprice =
    USD revenue per unit hashrate = revenue / work) and its TRIGGER (a hashrate flush /
    difficulty drop = forced shutdown = capitulation in progress). Deep history
    (CoinMetrics issuance_usd + hashrate, 2010->), so a real cycle-bottom anchor
    candidate, not just context: a compressed hashprice percentile = squeezed margins =
    miner-capitulation / bottoming zone; a sharp hashrate flush is the timestamped
    capitulation trigger. PIT-safe: rolling percentile/z end at the current row."""
    idx = inputs["price"].index
    out = pd.DataFrame(index=idx)
    iss, hr = inputs.get("issuance_usd"), inputs.get("hashrate")
    if iss is None or hr is None:
        return out
    i = iss.reindex(idx).ffill(limit=7)
    h = hr.reindex(idx).ffill(limit=7).replace(0, np.nan)
    hp = i / h                                  # daily USD revenue per unit hashrate
    out["hashprice"] = hp
    lb = cfg.get("pctile_lookback_d", 1460)
    out["hashprice_pctile"] = _pctile(hp, lb) * 100
    out["hashprice_z"] = _zscore(np.log(hp.replace(0, np.nan)), cfg.get("z_window_d", 365))
    n = cfg.get("shock_window_d", 14)
    shock = h.pct_change(n) * 100               # hashrate flush = miners powering off
    out["hashrate_shock"] = shock
    diff = inputs.get("difficulty")
    if diff is not None:
        out["difficulty_shock"] = diff.reindex(idx).ffill(limit=20).pct_change(n) * 100
    margin_stress = ((100 - out["hashprice_pctile"]) / 100).clip(0, 1)
    flush = (-shock / cfg.get("shock_full", 15.0)).clip(0, 1)
    out["miner_stress"] = (pd.concat([margin_stress, flush], axis=1)
                           .mean(axis=1, skipna=True) * 100).clip(0, 100)
    out["miner_econ_state"] = np.where(
        (out["hashprice_pctile"] < cfg.get("capit_pctile", 15)) | (flush > 0.6), "capitulation",
        np.where(out["hashprice_pctile"] > cfg.get("euphoria_pctile", 85), "euphoria",
                 np.where(out["miner_stress"] > 55, "stress", "healthy")))
    return out


# --------------------------------------------------------------------------- #
# conditional (downside-vs-upside) beta to equities / gold — the asymmetry a
# single Pearson correlation hides (research/VECTOR_FACTOR_ROADMAP_2026 Tier-2)
# --------------------------------------------------------------------------- #
def _masked_beta(b: pd.Series, m: pd.Series, mask: pd.Series, w: int, mp: int) -> pd.Series:
    """Rolling beta of `b` on `m` over the trailing `w` window, restricted to the days
    where `mask` is true (up-days or down-days). NaN-on-the-wrong-sign so E[xy]/E[x]/E[y]
    all share the same paired subset; no look-ahead (window ends at the current row)."""
    bm, mm = b.where(mask), m.where(mask)
    exy = (bm * mm).rolling(w, min_periods=mp).mean()
    ex = bm.rolling(w, min_periods=mp).mean()
    ey = mm.rolling(w, min_periods=mp).mean()
    eyy = (mm * mm).rolling(w, min_periods=mp).mean()
    cov, var = exy - ex * ey, eyy - ey * ey
    return cov / var.replace(0, np.nan)


def conditional_beta(inputs: dict, cfg: dict) -> pd.DataFrame:
    """DOWNSIDE-vs-UPSIDE beta to the equity risk proxy (NDX via QQQ) + gold. BTC
    couples HARD to risk assets on the way DOWN and decouples on the way UP — a single
    Pearson hides this, and the DOWNSIDE beta is what actually predicts forward
    drawdown. beta_asym = up_beta - down_beta (< 0 = a drawdown amplifier). Pure compute
    on Yahoo closes already on disk (deep). Scales the drawdown read; never a trigger."""
    close = inputs["price"]["close"]
    idx = close.index
    r = close.pct_change()
    w, mp = cfg.get("beta_window_d", 90), cfg.get("min_periods_d", 20)
    out = pd.DataFrame(index=idx)
    eq = inputs.get("ndx")
    if eq is not None:
        mr = eq.reindex(idx).ffill(limit=3).pct_change()
        dn, up = mr < 0, mr > 0
        db = _masked_beta(r, mr, dn, w, mp)
        ub = _masked_beta(r, mr, up, w, mp)
        out["down_beta"] = db
        out["up_beta"] = ub
        out["beta_asym"] = ub - db
        out["down_beta_pctile"] = _pctile(db, cfg.get("pctile_lookback_d", 730)) * 100
        hi = cfg.get("high_down_beta_pctile", 70)
        out["beta_regime"] = np.where(out["down_beta_pctile"] > hi, "drawdown_amplifier",
                             np.where(db < cfg.get("decoupled_beta", 0.15), "diversifier", "mixed"))
    gold = inputs.get("gold")
    if gold is not None:
        gr = gold.reindex(idx).ffill(limit=3).pct_change()
        out["down_beta_gold"] = _masked_beta(r, gr, gr < 0, w, mp)
    return out


# --------------------------------------------------------------------------- #
# holder spread: STH-vs-LTH realization (cycle-timing edge) — bgeo ~1-cycle =
# CONTEXT/accrue-forward (research/VECTOR_FACTOR_ROADMAP_2026 Tier-1, on disk)
# --------------------------------------------------------------------------- #
def holder_spread(inputs: dict, cfg: dict) -> pd.DataFrame:
    """STH-vs-LTH realization SPREAD — where cycle-timing edge concentrates. STH-SOPR
    minus LTH-SOPR (who is realizing profit) and the STH realized-price PREMIUM over the
    aggregate realized price (STH cost basis far above the whole market = late-cycle
    distribution; below = early accumulation). bgeo cohort series are a ~4y window
    (~1 cycle) so this ships as CONTEXT / accrue-forward, never a deep anchor."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    sth, lth = inputs.get("sth_sopr"), inputs.get("lth_sopr")
    sm = cfg.get("smooth_d", 7)
    if sth is not None and lth is not None:
        s = _ema(sth.reindex(idx).ffill(limit=5), sm)
        l = _ema(lth.reindex(idx).ffill(limit=5), sm)
        out["sth_lth_sopr_spread"] = s - l
    rp, srp = inputs.get("realized_price"), inputs.get("sth_realized_price")
    if rp is not None and srp is not None:
        out["sth_realized_premium"] = (srp.reindex(idx).ffill(limit=5)
                                       / rp.reindex(idx).ffill(limit=5) - 1) * 100
    if "sth_lth_sopr_spread" in out:
        sp = out["sth_lth_sopr_spread"]
        out["holder_state"] = np.where(sp > cfg.get("dist_thresh", 0.02), "distribution",
                              np.where(sp < cfg.get("accum_thresh", -0.02), "accumulation", "neutral"))
    return out


# --------------------------------------------------------------------------- #
# attention: Wikipedia pageviews — the retail/attention axis the model lacked
# (keyless, 2015-07->, the rare attention source that survives both halves)
# --------------------------------------------------------------------------- #
def attention(inputs: dict, cfg: dict) -> pd.DataFrame:
    """Retail-ATTENTION axis (only F&G + dominance before). Wikipedia 'Bitcoin'
    pageviews (Wikimedia REST, keyless, 2015-07->) = the rare attention source that
    survives both split-halves. Attention predicts VOL / volume, NOT 7d direction
    (Kristoufek), so it is read as an EXTREMES gauge: a mania spike = froth / blow-off
    risk, apathy = disinterest bottoms. z-scored on log-views, EMA-smoothed."""
    idx = inputs["price"]["close"].index
    out = pd.DataFrame(index=idx)
    wiki = inputs.get("wiki_views")
    if wiki is None:
        return out
    sm = _ema(wiki.reindex(idx).ffill(limit=3), cfg.get("smooth_d", 7))
    out["wiki_views"] = sm
    z = _zscore(np.log1p(sm), cfg.get("z_window_d", 365)).clip(-4, 4)
    out["wiki_views_z"] = z
    out["attention_state"] = np.where(z > cfg.get("mania_z", 2.0), "mania",
                            np.where(z < cfg.get("apathy_z", -1.0), "apathy", "normal"))
    return out


# --------------------------------------------------------------------------- #
# taker flow: aggressor CVD + price-vs-flow divergence (OKX rubik, shallow ->
# DISPLAY/accrue-forward, never scored)
# --------------------------------------------------------------------------- #
def taker_flow(inputs: dict, cfg: dict) -> pd.DataFrame:
    """The order-flow / aggressor-demand axis the model lacked (only a price-spread
    premium + a volume percentile before). OKX taker buy-share buy/(buy+sell); > 0.5 =
    net aggressive BUYING. CVD = rolling sum of the (share - 0.5) lean; the price-vs-CVD
    divergence is a momentum-exhaustion tell the vote-ensemble structurally misses. OKX
    rubik history is shallow (~6mo) so this is DISPLAY / accrue-forward context."""
    close = inputs["price"]["close"]
    idx = close.index
    out = pd.DataFrame(index=idx)
    tk = inputs.get("okx_taker_buy")
    if tk is None:
        return out
    s = tk.reindex(idx).ffill(limit=3)
    out["taker_buy_share"] = s
    out["taker_cvd"] = (s - 0.5).rolling(cfg.get("cvd_window_d", 30), min_periods=5).sum()
    out["taker_buy_z"] = _zscore(s, cfg.get("z_window_d", 90))
    n = cfg.get("div_window_d", 14)
    pc, fc = np.sign(close.pct_change(n)), np.sign(out["taker_cvd"].diff(n))
    out["taker_divergence"] = np.where((pc > 0) & (fc < 0), "bearish",
                              np.where((pc < 0) & (fc > 0), "bullish", "aligned"))
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

    # Coinbase Premium MODEL — the US-institutional-demand spread (Coinbase USD vs the
    # offshore USDT price). Prefer a SELF-COMPUTED premium (our own Coinbase-USD close vs
    # the OKX BTC-USDT close, fresh daily, 2018->) and splice the bgeo coinbase-premium
    # index onto any gaps / the deep tail. Then a smoothed level, extremity z/percentile,
    # a regime state, and a smart-money DIVERGENCE (price trend vs premium trend).
    prem_bgeo = inputs.get("coinbase_premium")           # bgeo index % (2022->, quota-limited)
    okx_usdt = inputs.get("okx_spot_usdt")               # offshore USDT reference (2018->)
    prem = None
    if okx_usdt is not None:
        ou = okx_usdt.reindex(idx).ffill(limit=3)
        prem = ((close - ou) / ou * 100.0).where(ou > 0)  # self-computed Coinbase−OKX spread %
    if prem_bgeo is not None:
        pb = prem_bgeo.reindex(idx).ffill(limit=3)
        prem = pb if prem is None else prem.fillna(pb)    # bgeo fills the pre-2018 tail / gaps
    if prem is not None:
        p = prem.clip(-5, 5)                              # tame brief dislocation spikes (±10%+)
        out["coinbase_premium"] = p
        ema = _ema(p, cfg["premium_smooth_d"])
        out["coinbase_premium_ema"] = ema
        out["coinbase_premium_z"] = _zscore(ema, cfg.get("premium_z_window_d", 180)).clip(-4, 4)
        out["coinbase_premium_pctile"] = _pctile(ema, cfg.get("premium_pctile_lookback_d", 365)) * 100
        hi, oh = cfg.get("premium_state_hi", 0.35), cfg.get("premium_state_overheat", 0.9)
        lo, dp = cfg.get("premium_state_lo", -0.2), cfg.get("premium_state_deep", -0.6)
        out["coinbase_premium_state"] = np.where(ema >= oh, "overheated",
                                        np.where(ema >= hi, "premium",
                                        np.where(ema <= dp, "deep_discount",
                                        np.where(ema <= lo, "discount", "neutral"))))
        dw = cfg.get("premium_div_window_d", 21)
        pr_chg, pm_chg = close.pct_change(dw), ema.diff(dw)
        div = np.where((pr_chg > 0) & (pm_chg < 0), "distribution",
              np.where((pr_chg < 0) & (pm_chg > 0), "accumulation", "aligned"))
        out["coinbase_premium_divergence"] = pd.Series(div, index=idx).where(ema.notna())

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
    w, mp = cfg["z_window_d"], cfg["z_min_periods_d"]
    ef = inputs.get("etf_flow")
    if ef is not None:                                     # bgeo aggregate (BTC) — cross-check / legacy
        f = ef.reindex(idx)                                # daily net flow, BTC (NaN pre-launch)
        out["etf_flow_btc"] = f
        out["etf_flow_usd_mn"] = (f * close) / 1e6        # USD millions (panel-friendly)
        sm = f.rolling(cfg["smooth_d"], min_periods=cfg["min_periods_d"]).sum()
        out["etf_flow_sum"] = sm                          # N-day net flow = the regime
        mu = sm.rolling(w, min_periods=mp).mean()
        sd = sm.rolling(w, min_periods=mp).std()
        out["etf_flow_z"] = ((sm - mu) / sd).clip(-3, 3)  # extremity vs recent norm
        out["etf_flow_cum"] = f.cumsum()                  # holdings proxy (BTC) since launch
        out["etf_flow_state"] = _hysteresis_tri(
            out["etf_flow_z"], cfg["state_enter_z"], cfg["state_exit_z"],
            labels=("distribution", "neutral", "accumulation"))

    # --- Farside per-fund layer (US$m, 2024-01->): richer/fresher/per-issuer. Primary
    #     going forward; the bgeo BTC series above is the cross-check / fallback. ---
    fa = inputs.get("farside_total")
    if fa is not None:
        tot = fa.reindex(idx)                              # daily net flow, US$m
        out["etf_flow_total_usd"] = tot
        usd_sum = tot.rolling(cfg.get("usd_smooth_d", 5), min_periods=2).sum()
        out["etf_usd_sum"] = usd_sum
        out["etf_usd_z"] = ((usd_sum - usd_sum.rolling(w, min_periods=mp).mean())
                            / usd_sum.rolling(w, min_periods=mp).std()).clip(-3, 3)
        out["etf_usd_cum"] = tot.cumsum().ffill()          # net $ in since launch (AUM-in proxy; carries across non-publish days)
        if "etf_flow_z" not in out:                        # no bgeo → drive the scored z/state off USD
            out["etf_flow_z"] = out["etf_usd_z"]
            out["etf_flow_state"] = _hysteresis_tri(
                out["etf_flow_z"], cfg["state_enter_z"], cfg["state_exit_z"],
                labels=("distribution", "neutral", "accumulation"))

    fdf = inputs.get("farside_etf")
    if fdf is not None and not fdf.empty:
        fd = fdf.copy()
        fd.index = pd.to_datetime(fd.index)
        fd = fd.reindex(idx)
        funds = [c for c in fd.columns if c != "total"]
        if "gbtc" in fd.columns and "total" in fd.columns:  # strip GBTC one-way-unlock distortion
            exg = fd["total"] - fd["gbtc"]
            out["etf_exgbtc_usd"] = exg
            out["etf_exgbtc_cum"] = exg.cumsum().ffill()
        cw = cfg.get("conc_window_d", 21)                  # top issuer's share of GROSS flow (1 = one fund carries it)
        roll = fd[funds].rolling(cw, min_periods=max(3, cw // 3)).sum()
        gross = roll.abs().sum(axis=1).replace(0, np.nan)
        out["etf_concentration"] = (roll.abs().max(axis=1) / gross).clip(0, 1)
        dw = cfg.get("div_window_d", 21)                   # price-trend vs cumulative-flow-trend divergence
        if "etf_usd_cum" in out:
            pr_chg, fl_chg = close.pct_change(dw), out["etf_usd_cum"].diff(dw)
            out["etf_flow_divergence"] = pd.Series(
                np.where((pr_chg > 0) & (fl_chg < 0), "distribution",
                np.where((pr_chg < 0) & (fl_chg > 0), "accumulation", "aligned")),
                index=idx).where(out["etf_usd_cum"].notna())
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

    # Tier-3 curve regime + Fed path — emitted as oriented {-2..+2} sub-scores for the
    # macro-regime composite (engine/btc_regime). DELIBERATELY NOT folded into
    # macro_score: the calibrated score stays unchanged; these are display-only.
    spread, us10, dff = s("spread_2s10s"), s("us10y"), s("fed_funds")
    if spread is not None and us10 is not None:
        cw = cfg.get("curve_chg_window_d", 20)
        steepening = spread.diff(cw) > 0          # term spread widening
        bull = us10.diff(cw) < 0                   # long-end yields falling = "bull"
        cs = pd.Series(np.nan, index=idx)
        cs[bull & steepening] = 2                  # bull steepening — recovery fuel (best)
        cs[bull & ~steepening] = 1                 # bull flattening — mixed-positive
        cs[~bull & steepening] = -1                # bear steepening — ambiguous
        cs[~bull & ~steepening] = -2               # bear flattening — worst (Fed choking)
        out["curve_score"] = cs.where(spread.diff(cw).notna() & us10.diff(cw).notna())
    if dff is not None:
        fw = cfg.get("fed_chg_window_d", 60)
        d_fed = dff.diff(fw)                        # <0 easing (bullish), >0 hiking (bearish)
        fs = pd.Series(np.nan, index=idx)
        fs[d_fed.notna()] = 0.0
        fs[d_fed < -0.25] = 1                       # cutting
        fs[d_fed < -0.75] = 2                       # cutting fast / post-pivot
        fs[d_fed > 0.25] = -1                       # hiking
        fs[d_fed > 0.75] = -2                       # hiking fast
        out["fed_score"] = fs

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
    cp = cycle_phase_clock(inputs, cfg["cycle_phase_clock"])  # bottom-anchored 1064/364 structure
    po = positioning(inputs, cfg["positioning"])
    xa = cross_asset_corr(inputs, cfg["cross_asset"])
    bh = behaviour(inputs, cfg["cross_asset"])
    gl = global_liquidity(inputs, cfg["global_liquidity"])
    sc = stablecoin_tide(inputs, cfg["global_liquidity"])  # crypto-native liquidity tide
    cm = cme_basis(inputs, cfg.get("cme_basis", {}))       # regulated institutional carry (context)
    fc = futures_carry(inputs, cfg.get("futures_carry", {}))  # consolidated derivatives-carry leverage cycle
    # Mastermind upgrade (research/VECTOR_FACTOR_ROADMAP_2026): deep miner-margin anchor +
    # conditional downside/upside beta (both pure-compute, deep) + cohort/attention/flow context.
    me = miner_economics(inputs, cfg.get("miner_econ", {}))
    cba = conditional_beta(inputs, cfg.get("conditional_beta", {}))
    hs = holder_spread(inputs, cfg.get("holder_spread", {}))
    at = attention(inputs, cfg.get("attention", {}))
    tf = taker_flow(inputs, cfg.get("taker_flow", {}))
    # Tier-1b: blend the confirmed valuation tails into allocation (gated by the
    # allocation backtest below). `close` enables the ENFORCED drawdown brake live.
    al = allocation(mom["momentum"], rk["risk_index"], cfg["allocation"], va,
                    close=inputs["price"]["close"])

    out = pd.concat([inputs["price"][["close"]], mom, rk, bf, st, gg, al,
                     va, mn, cb, ex, op, lv, ma, oc, ef, im, cc, cp, po, xa, bh, gl, sc, cm, fc,
                     me, cba, hs, at, tf], axis=1)
    out["cycle_position"] = cycle_stage(mom["momentum"], rk["risk_index"])
    alt = btc_vs_alts(inputs, cfg["btc_vs_alts"])
    if alt is not None:
        out["alt_cycle_leader"] = alt
    out["market_mode"] = tactical(inputs, rk["risk_index"], cfg["tactical"])
    out["composite_state"] = composite_state(out, cfg["composite"])
    out["composite_context"] = composite_context(out, cfg["composite"])
    return out
