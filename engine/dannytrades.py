"""engine/dannytrades.py — a REPRODUCIBLE reconstruction of Danny Cheng's
("DannyTrades", X @dannycheng2022) discretionary signal stack, as pure functions
over EOD OHLCV, built to be BACKTESTED and combined with the repo's other signals.

Danny is a weekly/monthly *investor* whose public method (reconstructed from his X
posts) rests on four proprietary chart indicators we approximate with standard,
documented tools — the formulas behind his are paywalled, so each leg here is a
best-supported PROXY, not his exact indicator:

  • "whale accumulation %" (his Panel 3, red=institutions / green=retail, 0–100;
     thresholds >35 momentum / >50 rises / >75 soars, "green must disappear")
        → a Chaikin-money-flow accumulation oscillator rescaled 0–100 by its own
          trailing percentile (runs hot in sustained accumulation, like his reads).
  • "volatility hole / black hole" (a sticky compression box; close above upper =
     buy, below lower = sell)
        → a Bollinger-bandwidth squeeze whose frozen range becomes the box, with a
          close-beyond-the-edge breakout/breakdown.
  • "momentum bars" / POC (whale transaction levels / whales' average cost; close
     above = bullish)
        → rolling volume-weighted price (a POC proxy) + reclaim.
  • red/blue "ribbon" trend + inverted candle colour + MACD/RSI "down-curl"
        → an EMA-ribbon trend state + a MACD/RSI momentum-OK filter.

DISPLAY / RESEARCH leaf — NOTHING here is a price target or a promise of edge. His
~90% self-reported hit rate is selection-biased (concentrated in strong AI names in
a bull market) and unverified; the point of this module is to MEASURE whether the
reconstructed composite carries any *incremental confirmation* value alongside the
repo's existing signals (scripts/dannytrades_phase0.py runs it through the standard
engine.validation / engine.forward_dist gate). All functions are causal (trailing
windows only); forward returns are computed separately with shift(-h).

Input contract: pandas Series of EOD close / high / low / volume on a shared daily
DatetimeIndex (the data/stocks/<T>.parquet schema). No 'open' is required.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.technicals import macd_hist, rsi

# --------------------------------------------------------------------------- #
# tunables (kept transparent + perturbed in the phase-0 sensitivity sweep)
# --------------------------------------------------------------------------- #
CFG = dict(
    # whale-accumulation oscillator
    cmf_n=21, whale_smooth=10, whale_win=63,
    whale_momentum=50.0, whale_soar=75.0, whale_enter_k=10,
    # volatility-hole squeeze box
    bb_n=20, bb_k=2.0, squeeze_lookback=126, squeeze_pctile=0.25, box_win=20,
    # POC proxy
    poc_win=126,
    # ribbon trend
    ribbon_fast=20, ribbon_slow=50, ribbon_slope_win=10,
    # composite score weights (sum to 1)
    w_whale=0.35, w_box=0.20, w_poc=0.15, w_ribbon=0.15, w_momentum=0.15,
)


# --------------------------------------------------------------------------- #
# small causal helpers
# --------------------------------------------------------------------------- #
def _pctile_rank(s: pd.Series, win: int) -> pd.Series:
    """Trailing percentile rank (0..1) of each point within its own `win` window —
    causal (uses only past+current). Falls back to a manual roll if the pandas
    Rolling.rank isn't available."""
    try:
        return s.rolling(win, min_periods=max(10, win // 3)).rank(pct=True)
    except (AttributeError, TypeError):  # very old pandas
        out = s.rolling(win, min_periods=max(10, win // 3)).apply(
            lambda a: (a <= a[-1]).mean(), raw=True)
        return out


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span).mean()


# --------------------------------------------------------------------------- #
# volume indicators (the "whale" family)
# --------------------------------------------------------------------------- #
def money_flow_volume(high, low, close, volume) -> pd.Series:
    """Chaikin money-flow volume per bar: where the bar closes in its range × volume.
    Positive = accumulation (closing near the high on volume)."""
    rng = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / rng
    return (mfm * volume).fillna(0.0)


def cmf(high, low, close, volume, n: int = 21) -> pd.Series:
    """Chaikin Money Flow ∈ [-1, 1]: n-day money-flow volume / n-day volume."""
    mfv = money_flow_volume(high, low, close, volume)
    return mfv.rolling(n, min_periods=max(5, n // 2)).sum() / \
        volume.rolling(n, min_periods=max(5, n // 2)).sum().replace(0, np.nan)


def obv(close, volume) -> pd.Series:
    """On-balance volume."""
    return (np.sign(close.diff().fillna(0.0)) * volume).fillna(0.0).cumsum()


def whale_buy_fraction(high, low, close, volume, win: int = 63) -> pd.Series:
    """A FAITHFUL "whale accumulation %" (vs the percentile proxy): the share of the
    last `win` bars' volume that traded as BUYING — each bar's volume split by where
    it closed in its range ((close-low)-(high-close))/(high-low) → buy fraction — then
    summed and divided by total volume, 0–100. Unlike the percentile oscillator this
    SATURATES toward 100 in sustained accumulation and toward 0 when 'green/retail'
    selling dominates, mirroring Danny's 90s reads and his "green must disappear"."""
    rng = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / rng            # -1..+1
    buy_share = ((mfm + 1.0) / 2.0).clip(0, 1)              # 0..1 of the bar that's buying
    mp = max(5, win // 3)
    bv = (buy_share * volume).rolling(win, min_periods=mp).sum()
    tv = volume.rolling(win, min_periods=mp).sum().replace(0, np.nan)
    return (bv / tv * 100.0)


def whale_accumulation(high, low, close, volume, cfg: dict | None = None) -> pd.Series:
    """Danny's Panel-3 "whale accumulation %" proxy, 0–100.

    Smoothed Chaikin Money Flow rescaled by its OWN trailing percentile, so it runs
    hot (90s) during sustained institutional accumulation and collapses when the tape
    distributes — mirroring his behaviour ("FICO >92%, WULF >94%, green bars gone").
    High = whales accumulating (his long red bars); low = retail / distribution."""
    c = {**CFG, **(cfg or {})}
    raw = cmf(high, low, close, volume, c["cmf_n"])
    smooth = raw.ewm(span=c["whale_smooth"], min_periods=c["whale_smooth"]).mean()
    return (_pctile_rank(smooth, c["whale_win"]) * 100.0)


# --------------------------------------------------------------------------- #
# volatility hole (sticky Bollinger-squeeze breakout box)
# --------------------------------------------------------------------------- #
def bb_bandwidth(close, n: int = 20, k: float = 2.0) -> pd.Series:
    """Bollinger bandwidth = (upper − lower) / mid. Low = volatility compression."""
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std()
    return (2 * k * sd) / mid.replace(0, np.nan)


def volatility_hole(close, high, low, cfg: dict | None = None) -> pd.DataFrame:
    """Reconstructed "volatility hole": a low-volatility consolidation box (frozen
    from the most recent Bollinger-bandwidth squeeze), with a close-beyond-the-edge
    breakout. Returns columns: box_upper, box_lower, in_hole, breakout_up,
    breakdown, pos_in_box (0..1), to_upper_pct, to_lower_pct. All causal."""
    c = {**CFG, **(cfg or {})}
    bw = bb_bandwidth(close, c["bb_n"], c["bb_k"])
    bw_pct = _pctile_rank(bw, c["squeeze_lookback"])
    squeeze = bw_pct <= c["squeeze_pctile"]                       # compression present
    # the box = range carved out DURING the squeeze bars, carried forward (sticky)
    hi_sq = high.where(squeeze)
    lo_sq = low.where(squeeze)
    box_upper = hi_sq.rolling(c["box_win"], min_periods=1).max().ffill()
    box_lower = lo_sq.rolling(c["box_win"], min_periods=1).min().ffill()
    prev_c = close.shift(1)
    breakout_up = (close > box_upper) & (prev_c <= box_upper.shift(1)) & box_upper.notna()
    breakdown = (close < box_lower) & (prev_c >= box_lower.shift(1)) & box_lower.notna()
    in_hole = (close <= box_upper) & (close >= box_lower)
    width = (box_upper - box_lower).replace(0, np.nan)
    return pd.DataFrame({
        "box_upper": box_upper, "box_lower": box_lower,
        "in_hole": in_hole.fillna(False),
        "breakout_up": breakout_up.fillna(False),
        "breakdown": breakdown.fillna(False),
        "pos_in_box": ((close - box_lower) / width).clip(0, 1),
        "to_upper_pct": (box_upper / close - 1) * 100,
        "to_lower_pct": (close / box_lower - 1) * 100,
    }, index=close.index)


# --------------------------------------------------------------------------- #
# POC proxy (whales' average cost / momentum bars)
# --------------------------------------------------------------------------- #
def poc_proxy(close, volume, win: int = 126) -> pd.Series:
    """Point-of-control proxy: trailing volume-weighted average price over `win`
    days ≈ the price where most volume traded ≈ whales' average cost. Close above =
    bullish (above whales' cost), per Danny's POC rule."""
    pv = (close * volume).rolling(win, min_periods=max(20, win // 4)).sum()
    v = volume.rolling(win, min_periods=max(20, win // 4)).sum().replace(0, np.nan)
    return pv / v


# --------------------------------------------------------------------------- #
# ribbon trend + momentum filter
# --------------------------------------------------------------------------- #
def ribbon_trend(close, cfg: dict | None = None) -> pd.Series:
    """Danny's red(up)/blue(down) ribbon → trend state in {+1, 0, -1}: +1 when the
    fast EMA leads a rising slow EMA and price is above it; −1 the mirror."""
    c = {**CFG, **(cfg or {})}
    fast, slow = _ema(close, c["ribbon_fast"]), _ema(close, c["ribbon_slow"])
    slope = slow.diff(c["ribbon_slope_win"])
    up = (fast > slow) & (slope > 0) & (close > slow)
    dn = (fast < slow) & (slope < 0) & (close < slow)
    return (up.astype(int) - dn.astype(int)).astype(float)


def momentum_ok(close) -> pd.Series:
    """His MACD/RSI confirmation: True when momentum is NOT curling down — MACD
    histogram rising or positive, and RSI not rolling over from overbought."""
    h = macd_hist(close)
    r = rsi(close)
    macd_ok = (h > 0) | (h.diff() > 0)
    rsi_ok = (r < 70) | (r.diff() > 0)
    return (macd_ok & rsi_ok).fillna(False)


# --------------------------------------------------------------------------- #
# composite — the full DannyTrades panel
# --------------------------------------------------------------------------- #
def signals(close, high, low, volume, cfg: dict | None = None) -> pd.DataFrame:
    """The full reconstructed DannyTrades stack for one ticker: every leg, a 0–100
    confluence SCORE (monotone in bullishness, for IC tests), and the discrete BUY /
    SELL states from his checklist. Causal throughout."""
    c = {**CFG, **(cfg or {})}
    close = close.astype(float); high = high.astype(float)
    low = low.astype(float); volume = volume.astype(float).fillna(0.0)

    whale = whale_accumulation(high, low, close, volume, c)
    hole = volatility_hole(close, high, low, c)
    poc = poc_proxy(close, volume, c["poc_win"])
    ribbon = ribbon_trend(close, c)
    mom_ok = momentum_ok(close)

    above_poc = close > poc
    reclaim_poc = above_poc & (close.shift(1) <= poc.shift(1))
    whale_rising = whale.diff(5) > 0
    whale_entering = ((whale >= c["whale_momentum"])
                      & (whale.shift(c["whale_enter_k"]) < c["whale_momentum"])
                      & whale_rising)

    # --- continuous 0–100 confluence score (for rank IC) ---
    whale_leg = whale.clip(0, 100)
    box_leg = (hole["pos_in_box"] * 100).where(hole["box_upper"].notna(), 50.0)
    box_leg = box_leg.mask(hole["breakout_up"], 100.0).mask(hole["breakdown"], 0.0)
    poc_leg = (50.0 + ((close / poc - 1.0) * 500.0)).clip(0, 100)   # ±10% → 0..100
    ribbon_leg = (ribbon + 1.0) * 50.0                              # -1/0/1 → 0/50/100
    mom_leg = mom_ok.astype(float) * 100.0
    score = (c["w_whale"] * whale_leg + c["w_box"] * box_leg + c["w_poc"] * poc_leg
             + c["w_ribbon"] * ribbon_leg + c["w_momentum"] * mom_leg)

    # --- discrete states from his buy/sell checklist ---
    danny_buy = ((hole["breakout_up"] | reclaim_poc)
                 & (whale >= c["whale_momentum"]) & (ribbon >= 0) & mom_ok)
    danny_buy_strong = (hole["breakout_up"] & (whale >= c["whale_soar"]) & (ribbon > 0))
    cross_below_poc = (~above_poc) & (close.shift(1) >= poc.shift(1))
    danny_sell = (hole["breakdown"] | (cross_below_poc & (ribbon <= 0))
                  | ((whale < c["whale_momentum"]) & (whale.diff(5) < 0) & (ribbon < 0)))

    out = pd.DataFrame({
        "whale": whale, "whale_entering": whale_entering.fillna(False),
        "box_upper": hole["box_upper"], "box_lower": hole["box_lower"],
        "in_hole": hole["in_hole"], "breakout_up": hole["breakout_up"],
        "breakdown": hole["breakdown"], "poc": poc, "above_poc": above_poc,
        "ribbon": ribbon, "momentum_ok": mom_ok,
        "score": score,
        "danny_buy": danny_buy.fillna(False),
        "danny_buy_strong": danny_buy_strong.fillna(False),
        "danny_sell": danny_sell.fillna(False),
    }, index=close.index)
    return out


def panel(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Convenience: run signals() on a data/stocks OHLCV DataFrame
    (columns close/high/low/volume)."""
    return signals(df["close"], df["high"], df["low"], df["volume"], cfg)
