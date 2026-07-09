"""Commodity Vector signal engine.

Per-asset signals for the core four (gold/silver/oil/copper):

  PRICE LAYER (asset-agnostic, mirrors engine/btc_signals.py):
    momentum vote-ensemble [-1,+1], structure shift [-1,+1], saturating Risk
    Index 0..100 (+ oscillator + regime), gauges, allocation grid, tactical mode,
    cycle position.

  COMMODITY-SPECIFIC LAYER (replaces BTC's on-chain block):
    driver_axis    macro tailwind/headwind from each asset's key drivers
                   (real yields, dollar, breakevens, growth)
    residual_shock the "intelligent" exogenous-bid detector — actual return minus
                   what the macro drivers predict (causal expanding fit, refit
                   monthly), z-scored, plus a driver-decoupling flag. This is what
                   surfaces China-CB / war / OPEC / data-center bids WITHOUT news.
    positioning    COT spec extremes on a ROLLING window (audit §2.3: the oil
                   NYMEX->ICE contract handoff forbids full-history normalization)

  CROSS-ASSET: gold/silver, copper/gold, oil/gold ratios + a commodity-complex
    macro-regime quadrant (Reflation / Stagflation / Goldilocks / Deflation-scare).

Every tunable lives in config.yml `commodities:`. No look-ahead: rolling windows
and a strictly-causal residual fit. compute_all() returns {asset: DataFrame} plus
a "_complex" cross-asset frame for the dashboard + calibration to consume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import config

YIELD_DRIVERS = {"real_yield", "us10y", "us2y", "breakeven10", "breakeven5y5y"}
ANN = np.sqrt(252)  # commodities trade ~252 days/yr (BTC engine uses 365)


# --------------------------------------------------------------------------- #
# small helpers (kept local so this engine is standalone, like btc_signals)
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
    return s.rolling(lookback, min_periods=max(20, lookback // 4)).rank(pct=True)


def _confirm(state: pd.Series, days: int) -> pd.Series:
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


def _driver_change(s: pd.Series, name: str, idx: pd.Index, window: int) -> pd.Series:
    """Yield drivers change in absolute terms; price-like drivers in pct."""
    s = s.reindex(idx).ffill()
    return s.diff(window) if name in YIELD_DRIVERS else s.pct_change(window)


# --------------------------------------------------------------------------- #
# price layer (asset-agnostic)
# --------------------------------------------------------------------------- #
def momentum(px: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    close = px["close"]
    idx = close.index
    w = cfg["votes"]
    votes = pd.DataFrame(index=idx)
    ema20, ema50 = _ema(close, 20), _ema(close, 50)
    up = np.where(close > ema50, 1, -1)
    votes["ema_trend"] = up * np.where(np.sign(ema50.diff(5)) == up, 1, 0.5)
    votes["ema_cross"] = np.where(ema20 > ema50, 1, -1)
    macd = _ema(close, 12) - _ema(close, 26)
    votes["macd_hist"] = np.sign(macd - _ema(macd, 9))
    votes["sma200"] = np.where(close > close.rolling(200).mean(), 1, -1)
    votes["roc20"] = np.sign(close.pct_change(20))
    rsi = _rsi(close)
    votes["rsi_zone"] = np.where(rsi > cfg["rsi_bull"], 1, np.where(rsi < cfg["rsi_bear"], -1, 0))

    weights = pd.Series({k: w[k] for k in votes.columns if k in w})
    wsum = votes.notna().mul(weights, axis=1).sum(axis=1)
    score = votes.mul(weights, axis=1).sum(axis=1, min_count=3) / wsum.replace(0, np.nan)
    score = score.ewm(span=cfg["smooth_days"], adjust=False).mean().clip(-1, 1)
    state = _confirm(_hysteresis_tri(score, cfg["trigger"], cfg["exit"]), cfg["confirm_days"])
    return pd.DataFrame({"momentum": score, "momentum_state": state})


def structure(px: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    close, high, low = px["close"], px["high"].fillna(px["close"]), px["low"].fillna(px["close"])
    n = cfg["swing_window_d"]
    votes = pd.DataFrame(index=close.index)
    hh, ll = high.rolling(n).max(), low.rolling(n).min()
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


def positioning(pos: pd.Series | None, idx: pd.Index, cfg: dict) -> pd.DataFrame:
    """COT spec net % of OI -> rolling percentile + crowding state. Rolling (not
    full-history) so the 2022 oil contract handoff doesn't distort the scale."""
    out = pd.DataFrame(index=idx)
    if pos is None:
        return out
    p = pos.reindex(idx).ffill(limit=10)
    pct = _pctile(p, cfg["pctile_lookback_d"])
    out["pos_net_pct_oi"] = p
    out["pos_pctile"] = pct * 100
    out["pos_state"] = np.where(pct > cfg["crowded_long_pctile"], "crowded_long",
                       np.where(pct < cfg["crowded_short_pctile"], "crowded_short", "neutral"))
    return out


def risk(px: pd.DataFrame, mom: pd.Series, pos_pctile: pd.Series | None, cfg: dict) -> pd.DataFrame:
    close = px["close"]
    idx = close.index
    w = cfg["weights"]
    stress = pd.DataFrame(index=idx)
    ret = close.pct_change()
    # downside semi-deviation (an explosive up-move must not read as risk)
    dvol = ret.clip(upper=0).rolling(cfg["vol_window_d"]).std() * ANN
    stress["vol_pctile"] = _pctile(dvol, cfg["vol_pctile_lookback_d"])
    dd = 1 - close / close.rolling(cfg["drawdown_window_d"]).max()
    stress["drawdown"] = (dd / cfg["drawdown_full_stress"]).clip(0, 1)
    stress["momentum_deterioration"] = ((-mom.diff(10)).clip(0, 1) * (mom < 0.5)).clip(0, 1)
    if pos_pctile is not None:
        # only a crowded LONG tail adds risk (washout-ahead); >70th pctile ramps 0->1
        stress["positioning_stress"] = ((pos_pctile / 100 - 0.70) / 0.30).clip(0, 1)

    weights = pd.Series({k: w[k] for k in stress.columns if k in w})
    wsum = stress.notna().mul(weights, axis=1).sum(axis=1)
    raw = stress.mul(weights, axis=1).sum(axis=1, min_count=2) / wsum.replace(0, np.nan)
    db = cfg["deadband"]
    risk_idx = (((raw - db).clip(lower=0) / (1 - db)) * 100).clip(0, 100)
    osc = (0.5 + risk_idx.diff(cfg["oscillator_delta_d"]) / cfg["oscillator_scale"] * 0.5).clip(0, 1).fillna(0.5)
    regime = _hysteresis_bi(risk_idx, cfg["threshold"], cfg["exit_threshold"],
                            high="high_risk", low="low_risk")
    return pd.DataFrame({"risk_index": risk_idx, "risk_oscillator": osc, "risk_regime": regime})


def gauges(px: pd.DataFrame, cfg_g: dict, cfg_r: dict) -> pd.DataFrame:
    close = px["close"]
    ret = close.pct_change()
    rv = ret.rolling(cfg_r["vol_window_d"]).std() * ANN
    volp = _pctile(rv, cfg_r["vol_pctile_lookback_d"])
    vol_state = pd.Series(np.where(volp < cfg_g["vol_low_pctile"], "Low",
                          np.where(volp > cfg_g["vol_high_pctile"], "High", "Sweet spot")),
                          index=close.index)
    up = ret.clip(lower=0).rolling(30).std()
    dn = (-ret.clip(upper=0)).rolling(30).std()
    vol_side = pd.Series(np.where(up > dn, "Upside", "Downside"), index=close.index)
    out = pd.DataFrame({"vol_pctile": volp, "vol_state": vol_state, "vol_side": vol_side})
    if "volume" in px.columns and px["volume"].notna().any():
        flowp = _pctile(px["volume"].rolling(7).mean(), 365)
        out["flow_pctile"] = flowp
        out["flow_state"] = np.where(flowp < cfg_g["flow_low_pctile"], "Low",
                            np.where(flowp > cfg_g["flow_high_pctile"], "High", "Sweet spot"))
    return out


def allocation(mom: pd.Series, risk_idx: pd.Series, cfg: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=mom.index)
    for name, v in cfg["variants"].items():
        full = (mom > v["mom_full"]) & (risk_idx < v["risk_full"])
        half = (mom > v["mom_half"]) & (risk_idx < v["risk_half"])
        raw = pd.Series(np.where(full, 1.0, np.where(half, 0.5, 0.0)), index=mom.index)
        out[f"alloc_{name}"] = _confirm(raw, cfg["confirm_days"])
    return out


def tactical(px: pd.DataFrame, risk_idx: pd.Series, cfg: dict) -> pd.Series:
    close = px["close"]
    n = cfg["efficiency_window_d"]
    eff = (close.diff(n).abs() / close.diff().abs().rolling(n).sum()).clip(0, 1)
    strat = (eff > cfg["strategic_min_efficiency"]) & (risk_idx < cfg["strategic_max_risk"])
    return _confirm(pd.Series(np.where(strat, "Strategic", "Tactical"), index=close.index), 3) \
        .rename("market_mode")


def cycle_stage(mom: pd.Series, risk_idx: pd.Series) -> pd.Series:
    pos = (mom + 1) / 2 * 0.75 + (1 - risk_idx / 100) * 0.25
    return pos.clip(0, 1).rename("cycle_position")


# --------------------------------------------------------------------------- #
# commodity-specific: driver axis (macro tailwind / headwind)
# --------------------------------------------------------------------------- #
def driver_axis(px: pd.DataFrame, drivers: dict, asset: str, cfg: dict) -> pd.DataFrame:
    """Weighted vote of each driver's DIRECTION times its configured orientation
    (sign = effect of a rising driver on this commodity). -> [-1,+1] tailwind score.
    Per-ROW weight normalization so a driver with a shorter history (broad_dollar
    starts 2006) doesn't dilute the score before it exists."""
    idx = px.index
    weights = cfg["weights"].get(asset, {})
    win = cfg["change_window_d"]
    contrib = pd.DataFrame(index=idx)   # signed vote * |w|
    avail = pd.DataFrame(index=idx)     # |w| where the vote is present
    for dn, ow in weights.items():
        s = drivers.get(dn)
        if s is None:
            continue
        vote = np.sign(ow) * np.sign(_driver_change(s, dn, idx, win))
        contrib[dn] = vote * abs(ow)
        avail[dn] = pd.Series(np.where(np.isfinite(vote), abs(ow), np.nan), index=idx)
    if contrib.empty:
        return pd.DataFrame(index=idx)
    score = (contrib.sum(axis=1, min_count=1) / avail.sum(axis=1, min_count=1).replace(0, np.nan))
    score = score.ewm(span=cfg["smooth_days"], adjust=False).mean().clip(-1, 1)
    state = _hysteresis_tri(score, cfg["trigger"], cfg["exit"],
                            labels=("headwind", "neutral", "tailwind"))
    return pd.DataFrame({"driver_score": score, "driver_state": state})


# --------------------------------------------------------------------------- #
# commodity-specific: 12-month time-series momentum (TSMOM, the academic factor)
# --------------------------------------------------------------------------- #
def ts_momentum(px: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Trailing 12-month total return — the canonical commodity-momentum factor.
    MEASURED far more predictive than short-term trend for the metals; oil
    mean-reverts (calibration flags it INVERTED). Emit the raw factor (for
    banding) + a bounded score + a confirmed up/down state."""
    close = px["close"]
    ret = close.pct_change(cfg["lookback_d"])
    score = np.tanh(ret / cfg["scale"]).clip(-1, 1)
    state = _confirm(pd.Series(np.where(ret > 0, "up", np.where(ret < 0, "down", "flat")),
                               index=close.index), cfg["confirm_days"])
    return pd.DataFrame({"ts_return_12m": ret, "ts_momentum": score, "ts_trend": state})


# --------------------------------------------------------------------------- #
# commodity-specific: Brent-WTI spread (oil energy microstructure)
# --------------------------------------------------------------------------- #
def brent_wti(wti: pd.Series, brent: pd.Series, cfg: dict) -> pd.DataFrame:
    """Brent minus WTI. MEASURED: a WIDENING spread precedes WTI strength
    (WTI-discount mean-reversion / global tightness leading). Emit the spread,
    its rolling percentile, and the change (the predictive piece)."""
    idx = wti.index
    b = brent.reindex(idx).ffill()
    spread = (b - wti).rename("bw_spread")
    out = pd.DataFrame(index=idx)
    out["bw_spread"] = spread
    out["bw_spread_pctile"] = _pctile(spread, cfg["spread_pctile_lookback_d"]) * 100
    out["bw_change"] = spread.diff(cfg["change_window_d"])
    return out


# --------------------------------------------------------------------------- #
# cross-metal: gold/silver ratio value signal (merged into gold + silver frames)
# --------------------------------------------------------------------------- #
def gold_silver_ratio(gold_close: pd.Series, silver_close: pd.Series, cfg: dict) -> pd.DataFrame:
    """GSR = gold/silver. MEASURED: a high GSR (silver cheap vs gold) precedes
    silver outperformance (mean-reversion / value); mildly bullish gold too."""
    idx = gold_close.index.union(silver_close.index)
    g = gold_close.reindex(idx).ffill()
    s = silver_close.reindex(idx).ffill()
    gsr = (g / s).rename("gsr")
    pct = _pctile(gsr, cfg["pctile_lookback_d"])
    out = pd.DataFrame(index=idx)
    out["gsr"] = gsr
    out["gsr_pctile"] = pct * 100
    out["gsr_state"] = np.where(pct > cfg["high_pctile"], "silver_cheap",
                       np.where(pct < cfg["low_pctile"], "silver_rich", "neutral"))
    return out


# --------------------------------------------------------------------------- #
# commodity-specific: residual shock engine (the "intelligent" exogenous detector)
# --------------------------------------------------------------------------- #
def residual_shock(px: pd.DataFrame, drivers: dict, asset: str, cfg: dict) -> pd.DataFrame:
    """Causal residual = actual w-day return minus what the macro drivers predict.
    Betas are refit on an EXPANDING history every `refit_every_d` days (no
    look-ahead), so a large positive residual = an unexplained bid (CB buying,
    war premium, data-center demand). Also flags driver DECOUPLING when the
    rolling correlation to the primary driver loses its expected sign/strength.
    """
    idx = px.index
    w = cfg["return_window_d"]
    drv_names = cfg["drivers"].get(asset, [])
    y = px["close"].pct_change(w).rename("y")
    feats = {dn: _driver_change(drivers[dn], dn, idx, w)
             for dn in drv_names if dn in drivers}
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
    Xv = valid[cols].to_numpy()
    Aall = np.column_stack([np.ones(len(valid)), Xv])
    pos_index = valid.index
    beta = None
    for i in range(mintr, len(valid)):
        if beta is None or (i - mintr) % refit == 0:
            beta = np.linalg.lstsq(Aall[:i], yv[:i], rcond=None)[0]  # history strictly < i
        pred = Aall[i] @ beta
        resid.iloc[idx.get_loc(pos_index[i])] = yv[i] - pred

    out["resid_ret"] = resid
    sd = resid.rolling(cfg["z_lookback_d"], min_periods=60).std()
    z = (resid / sd.replace(0, np.nan)).rename("shock_z")
    out["shock_z"] = z
    thr = cfg["shock_z"]
    out["shock_state"] = np.where(z > thr, "exogenous_bid",
                         np.where(z < -thr, "exogenous_pressure", "normal"))
    out.loc[z.isna(), "shock_state"] = np.nan

    # decoupling: rolling corr of the w-return to the PRIMARY driver change
    prim = drv_names[0]
    if prim in X.columns:
        corr = y.rolling(cfg["decoupling_corr_window_d"], min_periods=90).corr(X[prim])
        out["driver_corr"] = corr
        orient = config.load()["commodities"]["driver_axis"]["weights"][asset].get(prim, -1.0)
        exp_sign = 1.0 if orient > 0 else -1.0
        out["decoupled"] = ((np.sign(corr) != exp_sign) | (corr.abs() < cfg["decoupling_corr_max"]))
    return out


# --------------------------------------------------------------------------- #
# technical arming detector (policy-shock W1-B)
# --------------------------------------------------------------------------- #
def _stoch_kd(close: pd.Series, k_period: int = 14,
              smooth_k: int = 3, smooth_d: int = 3) -> tuple[pd.Series, pd.Series]:
    """Full stochastic %K and %D on raw OHLC-style close (no RSI step).

    Uses close as both high and low proxy when only close is available —
    commodity OHLC is often synthesised from close in the inputs layer.
    Returns (K, D) each in [0, 100], NaN where insufficient history."""
    lo = close.rolling(k_period, min_periods=k_period).min()
    hi = close.rolling(k_period, min_periods=k_period).max()
    raw_k = ((close - lo) / (hi - lo).replace(0, np.nan) * 100)
    k = raw_k.rolling(smooth_k, min_periods=smooth_k).mean()
    d = k.rolling(smooth_d, min_periods=smooth_d).mean()
    return k, d


def technical_arming(px: pd.DataFrame, cfg: dict) -> dict:
    """Per-asset technical-arming block (display-tier only, context not scoring).

    Returns a JSON-safe dict with v1.1 parameters printed verbatim.
    All booleans are True/False (never None/NaN).  Null-safe: returns a
    partial dict with armed=False when the series is too short.

    Indicators
    ----------
    stoch_k / stoch_d : 14-3-3 full stochastic on daily closes, 0-100.
    stoch_curl        : %K crosses above %D AND %K < 30 on the latest bar
                        (the cross must have happened within the last 3 bars
                        to avoid flagging stale crosses).
    macd_curl         : MACD histogram rising for 3 consecutive bars while
                        below zero (histogram = MACD-line minus signal line).
                        v1.1: each positive diff must also exceed a
                        scale-invariant minimum (`macd_rise_min_frac` × the
                        rolling mean |histogram|) so float jitter on a
                        near-constant negative histogram does NOT fire.
    basing            : close within `base_pct` of the `base_window`-day low
                        for >= `base_min_days` consecutive sessions AND the
                        `drawdown_window`-day max-drawdown <= `drawdown_min`.
                        v1.1: additionally the absolute net close-to-close
                        return over the in-band window — min(days_in_base,
                        4 x base_min_days) sessions — must be
                        <= `base_flat_max_abs_return` (flatness gate — a
                        genuine base is ±few %, an ongoing decline is −10%+).
    days_in_base      : consecutive sessions meeting the basing PRICE-BAND
                        test (resets when price leaves the band); `basing` (and
                        therefore `armed`) additionally requires the flatness
                        gate to pass.
    armed             : basing AND (stoch_curl OR macd_curl).
    """
    acfg = cfg.get("technical_arming", {})
    # --- parameters (v1-frozen unless noted as v1.1 additions) ---------------
    k_period       = int(acfg.get("stoch_k_period", 14))
    smooth_k       = int(acfg.get("stoch_smooth_k", 3))
    smooth_d       = int(acfg.get("stoch_smooth_d", 3))
    stoch_oversold = float(acfg.get("stoch_oversold", 30.0))
    macd_fast      = int(acfg.get("macd_fast", 12))
    macd_slow      = int(acfg.get("macd_slow", 26))
    macd_signal    = int(acfg.get("macd_signal", 9))
    macd_consec    = int(acfg.get("macd_consecutive_bars", 3))
    base_window    = int(acfg.get("base_window_d", 60))
    base_pct       = float(acfg.get("base_pct", 0.08))
    base_min_days  = int(acfg.get("base_min_days", 10))
    drawdown_window = int(acfg.get("drawdown_window_d", 120))
    drawdown_min   = float(acfg.get("drawdown_min", -0.15))
    stoch_curl_lookback = int(acfg.get("stoch_curl_lookback", 3))
    # v1.1: flatness gate — basing requires |net return| over the in-band window
    # (min(days_in_base, 4 x base_min_days) sessions) <= this
    base_flat_max_abs_return = float(acfg.get("base_flat_max_abs_return", 0.06))
    # v1.1: scale-invariant minimum per-diff for the MACD rising test
    # each positive diff must exceed (macd_rise_min_frac × rolling mean |histogram|)
    macd_rise_min_frac = float(acfg.get("macd_rise_min_frac", 0.02))

    params = {
        "stoch_k_period": k_period, "stoch_smooth_k": smooth_k,
        "stoch_smooth_d": smooth_d, "stoch_oversold": stoch_oversold,
        "macd_fast": macd_fast, "macd_slow": macd_slow,
        "macd_signal": macd_signal, "macd_consecutive_bars": macd_consec,
        "base_window_d": base_window, "base_pct": base_pct,
        "base_min_days": base_min_days,
        "drawdown_window_d": drawdown_window, "drawdown_min": drawdown_min,
        "stoch_curl_lookback": stoch_curl_lookback,
        # v1.1 additions
        "base_flat_max_abs_return": base_flat_max_abs_return,
        "macd_rise_min_frac": macd_rise_min_frac,
        "version": "v1.1",
    }

    null_result = {
        "stoch_k": None, "stoch_d": None,
        "stoch_curl": False, "macd_curl": False,
        "basing": False, "days_in_base": 0,
        "flatness": None,
        "armed": False, "params": params,
    }

    close = px["close"].dropna()
    min_bars = max(macd_slow + macd_signal + macd_consec,
                   k_period + smooth_k + smooth_d,
                   base_window, drawdown_window)
    if len(close) < min_bars:
        return null_result

    # --- stochastic (14-3-3 on daily closes) ---------------------------------
    k, d = _stoch_kd(close, k_period, smooth_k, smooth_d)
    stoch_k_last = float(k.iloc[-1]) if pd.notna(k.iloc[-1]) else None
    stoch_d_last = float(d.iloc[-1]) if pd.notna(d.iloc[-1]) else None

    # stoch curl: %K crosses above %D within the last `stoch_curl_lookback` bars,
    # AND %K is below `stoch_oversold` on the bar of the cross.
    stoch_curl = False
    look = min(stoch_curl_lookback, len(k) - 1)
    for i in range(1, look + 1):
        idx = -(i)         # latest = -1, one-before = -2, ...
        k_now = k.iloc[idx] if pd.notna(k.iloc[idx]) else np.nan
        d_now = d.iloc[idx] if pd.notna(d.iloc[idx]) else np.nan
        k_prev = k.iloc[idx - 1] if pd.notna(k.iloc[idx - 1]) else np.nan
        d_prev = d.iloc[idx - 1] if pd.notna(d.iloc[idx - 1]) else np.nan
        if (np.isfinite(k_now) and np.isfinite(d_now) and
                np.isfinite(k_prev) and np.isfinite(d_prev)):
            if k_now > d_now and k_prev <= d_prev and k_now < stoch_oversold:
                stoch_curl = True
                break

    # --- MACD curl: histogram rising for `macd_consec` consecutive bars while < 0
    #     v1.1: each positive diff must exceed a scale-invariant minimum so that
    #     float jitter on a near-constant negative histogram does NOT fire.
    macd_line = _ema(close, macd_fast) - _ema(close, macd_slow)
    macd_sig = _ema(macd_line, macd_signal)
    hist = macd_line - macd_sig

    macd_curl = False
    hist_clean = hist.dropna()
    if len(hist_clean) >= macd_consec + 1:
        tail = hist_clean.iloc[-(macd_consec + 1):]
        if len(tail) == macd_consec + 1:
            below_zero = (tail.iloc[1:] < 0).all()
            diffs = tail.diff().iloc[1:]
            rising = (diffs > 0).all()
            if below_zero and rising:
                # v1.1 scale-invariant minimum: each diff must exceed
                # macd_rise_min_frac × rolling mean |histogram| (use a
                # 60-bar window so the floor adapts to the asset's scale).
                # An absolute floor of price_mean × 1e-6 guards against the
                # degenerate case where a perfectly linear series produces a
                # near-constant float-jitter histogram whose rolling magnitude
                # is also floating-point scale, making the relative epsilon
                # trivially small.  The floor sets a price-commensurate
                # lower bound so purely numerical noise cannot satisfy the gate.
                roll_mag = hist_clean.abs().rolling(60, min_periods=20).mean()
                mag_floor = float(roll_mag.iloc[-1]) if pd.notna(roll_mag.iloc[-1]) else 0.0
                price_floor = float(close.mean()) * 1e-6
                min_diff = max(macd_rise_min_frac * mag_floor, price_floor)
                economically_rising = (diffs > min_diff).all()
                macd_curl = bool(economically_rising)

    # --- basing: close within `base_pct` of the `base_window`-day low
    #     for >= `base_min_days` consecutive sessions AND 120d drawdown <= -15%
    #     v1.1: additionally the net return over the in-band window — the last
    #     min(days_in_base, 4 x base_min_days) sessions — must be
    #     <= base_flat_max_abs_return in absolute value (flatness gate).
    low_60 = close.rolling(base_window, min_periods=base_window).min()
    in_base_band = (close <= low_60 * (1 + base_pct))

    # count consecutive sessions in price-band (resets on first False)
    days_in_base = 0
    arr = in_base_band.to_numpy()
    for v in reversed(arr):
        if v:
            days_in_base += 1
        else:
            break

    # 120d max-drawdown (peak-to-trough from 120-day rolling high)
    dd_120 = float((close / close.rolling(drawdown_window, min_periods=drawdown_window).max() - 1).iloc[-1]) \
        if len(close) >= drawdown_window else 0.0

    # v1.1 flatness gate: |net return over the in-band period| <= threshold.
    # Window = min(days_in_base, 4 × base_min_days).  The 4× multiplier (default
    # 40 sessions) is deliberately wider than the base_min_days minimum (10) but
    # narrower than base_window (60), which can step back into the preceding drop
    # phase when days_in_base is inflated by the proximity-to-low counter running
    # throughout the descent.  An ongoing decline shows -8%+ over 40 sessions; a
    # genuine sideways coil remains ±few % across its full duration.
    flat_window = min(days_in_base, 4 * base_min_days) if days_in_base >= base_min_days else base_min_days
    if len(close) >= flat_window and flat_window >= 2:
        flat_slice = close.iloc[-flat_window:]
        flatness = float(abs(flat_slice.iloc[-1] / flat_slice.iloc[0] - 1))
    else:
        flatness = None
    flat_ok = (flatness is not None and flatness <= base_flat_max_abs_return)

    basing = bool(days_in_base >= base_min_days and dd_120 <= drawdown_min and flat_ok)
    armed = bool(basing and (stoch_curl or macd_curl))

    return {
        "stoch_k": round(stoch_k_last, 2) if stoch_k_last is not None else None,
        "stoch_d": round(stoch_d_last, 2) if stoch_d_last is not None else None,
        "stoch_curl": stoch_curl,
        "macd_curl": macd_curl,
        "basing": basing,
        "days_in_base": days_in_base,
        "flatness": round(flatness, 4) if flatness is not None else None,
        "armed": armed,
        "params": params,
    }


# --------------------------------------------------------------------------- #
# per-asset assembly
# --------------------------------------------------------------------------- #
def compute_asset(ai: dict, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or config.load()["commodities"]
    asset = ai["asset"]
    px = ai["price"]
    drivers = ai["drivers"]

    mom = momentum(px, cfg["momentum"])
    st = structure(px, cfg["structure"])
    pos = positioning(ai.get("cot_net_pct_oi"), px.index, cfg["positioning"])
    pos_pctile = pos["pos_pctile"] if "pos_pctile" in pos else None
    rk = risk(px, mom["momentum"], pos_pctile, cfg["risk"])
    gg = gauges(px, cfg["gauges"], cfg["risk"])
    al = allocation(mom["momentum"], rk["risk_index"], cfg["allocation"])
    da = driver_axis(px, drivers, asset, cfg["driver_axis"])
    rs = residual_shock(px, drivers, asset, cfg["residual"])
    ts = ts_momentum(px, cfg["trend"])

    parts = [px[["close"]], mom, st, ts, pos, rk, gg, al, da, rs]
    # oil only: Brent-WTI energy microstructure
    brent = ai.get("brent")
    if asset == "oil" and brent is not None:
        parts.append(brent_wti(px["close"], brent, cfg["brent_wti"]))
    out = pd.concat(parts, axis=1)
    out["cycle_position"] = cycle_stage(mom["momentum"], rk["risk_index"])
    out["market_mode"] = tactical(px, rk["risk_index"], cfg["tactical"])
    out["asset"] = asset
    return out


# --------------------------------------------------------------------------- #
# cross-asset: ratios + commodity-complex macro-regime quadrant
# --------------------------------------------------------------------------- #
def complex_regime(results: dict[str, pd.DataFrame], drivers: dict, cfg: dict) -> pd.DataFrame:
    ccfg = cfg["cross_asset"]
    closes = {a: results[a]["close"] for a in results}
    idx = sorted(set().union(*[c.index for c in closes.values()]))
    idx = pd.DatetimeIndex(idx)
    C = {a: closes[a].reindex(idx).ffill() for a in closes}
    out = pd.DataFrame(index=idx)

    if {"gold", "silver"} <= C.keys():
        out["gold_silver"] = C["gold"] / C["silver"]
    if {"copper", "gold"} <= C.keys():
        out["copper_gold"] = C["copper"] / C["gold"]
    if {"oil", "gold"} <= C.keys():
        out["oil_gold"] = C["oil"] / C["gold"]

    dxy = drivers.get("dxy")
    rw = ccfg["ratio_window_d"]
    dollar_dir = np.sign(dxy.reindex(idx).ffill().pct_change(ccfg["dollar_trend_window_d"])) \
        if dxy is not None else pd.Series(0, index=idx)
    growth_dir = np.sign(out["copper_gold"].pct_change(rw)) if "copper_gold" in out else pd.Series(0, index=idx)

    # quadrant on (dollar direction, growth direction)
    regime = pd.Series("Neutral", index=idx, dtype=object)
    regime[(dollar_dir < 0) & (growth_dir > 0)] = "Reflation"         # broad commodity bull
    regime[(dollar_dir < 0) & (growth_dir < 0)] = "Stagflation"       # metals lead, copper lags
    regime[(dollar_dir > 0) & (growth_dir > 0)] = "Goldilocks"        # growth ok, dollar headwind
    regime[(dollar_dir > 0) & (growth_dir < 0)] = "Deflation-scare"   # broad commodity bear
    out["dollar_dir"] = dollar_dir
    out["growth_dir"] = growth_dir
    out["complex_regime"] = _confirm(regime, 5)
    return out


def compute_all(inputs: dict | None = None) -> dict[str, pd.DataFrame]:
    from engine import commodity_inputs
    cfg = config.load()["commodities"]
    if inputs is None:
        inputs = commodity_inputs.load_all(cfg)
    results = {a: compute_asset(ai, cfg) for a, ai in inputs.items()}
    drivers = next(iter(inputs.values()))["drivers"] if inputs else {}
    # cross-metal: gold/silver ratio value signal merged into both metal frames
    if {"gold", "silver"} <= results.keys():
        gsr = gold_silver_ratio(results["gold"]["close"], results["silver"]["close"],
                                cfg["gold_silver_ratio"])
        for a in ("gold", "silver"):
            results[a] = results[a].join(gsr.reindex(results[a].index))
    results["_complex"] = complex_regime({a: results[a] for a in inputs}, drivers, cfg)
    return results
