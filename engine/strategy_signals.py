"""Per-name (time-series) trading-strategy signal library for the strategy lab
(research/STRATEGY_LAB.md). Every function is CAUSAL: a value at bar t uses only
data at/<=t, so the same code serves the walk-forward backtest and the live build.

Two objects per strategy:
  * signal(df)   -> pd.Series  : a continuous feature, oriented so HIGHER = more
                                 bullish over the strategy's horizon. Used for the
                                 banded event-study and the IC/forward-return tests.
  * position(df) -> pd.Series  : the tradable LONG/FLAT allocation in [0,1], RAW
                                 (pre-shift). engine.validation.backtest_core does the
                                 shift(1) so a position decided at close t acts at t+1.
                                 No look-ahead lives here.

Strategies are grouped by family so the lab can score "buy-in timing" (short-horizon
mean-reversion / breakout entries) separately from "selection / swing" (trend &
momentum state). Indicators are hand-rolled numpy/pandas (no TA-Lib) to keep the
data-bot env thin. df is a single name's OHLCV frame: columns close/high/low/volume,
DatetimeIndex (the data/stocks schema). Volume-using legs degrade gracefully if absent.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# indicators (causal)
# --------------------------------------------------------------------------- #
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(2, n // 2)).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, min_periods=max(2, n // 2), adjust=False).mean()


def wilder_rsi(s: pd.Series, n: int) -> pd.Series:
    """Wilder's RSI (the standard). n=2 gives the Connors short-term oscillator."""
    d = s.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    # Wilder smoothing == EMA with alpha = 1/n
    roll_up = up.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()
    roll_dn = dn.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()
    rs = roll_up / roll_dn.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(roll_dn != 0, 100.0)


def bollinger_pctb(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    """%b = (price - lower) / (upper - lower). <0 below lower band, >1 above upper."""
    mid = s.rolling(n, min_periods=n).mean()
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    lower, upper = mid - k * sd, mid + k * sd
    width = (upper - lower).replace(0.0, np.nan)
    return (s - lower) / width


def realized_vol(s: pd.Series, n: int) -> pd.Series:
    """Annualized close-to-close realized vol over n bars."""
    return s.pct_change().rolling(n, min_periods=max(5, n // 2)).std(ddof=0) * np.sqrt(252.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Average true range (Wilder). Falls back to close-only range if no high/low."""
    c = df["close"]
    if "high" in df and "low" in df:
        h, l = df["high"], df["low"]
        pc = c.shift(1)
        tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    else:
        tr = c.diff().abs()
    return tr.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()


def dd_from_high(s: pd.Series, n: int) -> pd.Series:
    """Current drawdown from the trailing n-bar high (<=0)."""
    hi = s.rolling(n, min_periods=max(5, n // 2)).max()
    return s / hi - 1.0


def _zscore(s: pd.Series, n: int) -> pd.Series:
    mu = s.rolling(n, min_periods=max(5, n // 2)).mean()
    sd = s.rolling(n, min_periods=max(5, n // 2)).std(ddof=0).replace(0.0, np.nan)
    return (s - mu) / sd


def hold_for(trigger: pd.Series, h: int) -> pd.Series:
    """Long/flat position = 1 on any of the h bars starting the bar a trigger fired.
    Decided at close t (backtest_core shifts entry to t+1); overlapping fires stay
    long; expiry after h bars. The canonical fixed-horizon entry rule (no tuned exit)."""
    t = trigger.fillna(False).astype(float)
    return (t.rolling(h, min_periods=1).max() > 0).astype(float)


def donchian_position(df: pd.DataFrame, entry_n: int = 55, exit_n: int = 20) -> pd.Series:
    """Turtle-style state machine: go long when close makes a new entry_n-bar high,
    exit when it makes a new exit_n-bar low. Causal scan (uses trailing extrema only)."""
    c = df["close"]
    hi = c.rolling(entry_n, min_periods=entry_n).max()
    lo = c.rolling(exit_n, min_periods=exit_n).min()
    cv, hv, lv = c.to_numpy(), hi.to_numpy(), lo.to_numpy()
    pos = np.zeros(len(c))
    state = 0.0
    for i in range(len(c)):
        if np.isnan(hv[i]) or np.isnan(lv[i]):
            pos[i] = 0.0
            continue
        if state == 0.0 and cv[i] >= hv[i]:
            state = 1.0
        elif state == 1.0 and cv[i] <= lv[i]:
            state = 0.0
        pos[i] = state
    return pd.Series(pos, index=c.index)


# --------------------------------------------------------------------------- #
# strategy registry
# --------------------------------------------------------------------------- #
class Strat:
    """A per-name strategy: a continuous bullish-oriented `signal` and a long/flat
    tradable `position`. family/horizon/thesis are metadata for the lab report."""

    def __init__(self, key, name, family, horizon, signal, position, thesis=""):
        self.key = key
        self.name = name
        self.family = family          # entry_timing | mean_reversion | trend | breakout
        self.horizon = horizon        # primary forward horizon (days)
        self.signal = signal
        self.position = position
        self.thesis = thesis


# ---- entry-timing / mean-reversion (short horizon: buy-in timing) ---------- #
def _rsi2_oversold(df, up_n=200, buy=10.0, h=5):
    c = df["close"]
    r2 = wilder_rsi(c, 2)
    uptrend = c > sma(c, up_n)
    sig = (-r2).where(uptrend)                     # higher = more oversold-in-uptrend
    pos = hold_for((r2 < buy) & uptrend, h)
    return sig, pos


def _bb_reversion(df, n=20, up_n=200, h=10):
    c = df["close"]
    pb = bollinger_pctb(c, n)
    uptrend = c > sma(c, up_n)
    sig = (-pb).where(uptrend)                     # higher = further below lower band
    pos = hold_for((pb < 0.0) & uptrend, h)
    return sig, pos


def _dd_reversion(df, win=20, up_n=200, depth=-0.07, h=10):
    c = df["close"]
    dd = dd_from_high(c, win)
    uptrend = c > sma(c, up_n)
    sig = (-dd).where(uptrend)                     # higher = deeper pullback in uptrend
    pos = hold_for((dd <= depth) & uptrend, h)
    return sig, pos


def _dist_below_ma(df, ma_n=20, z_n=100, up_n=200, thr=-1.0, h=8):
    c = df["close"]
    stretch = (c / sma(c, ma_n) - 1.0)
    z = _zscore(stretch, z_n)
    uptrend = c > sma(c, up_n)
    sig = (-z).where(uptrend)                      # higher = unusually far below MA
    pos = hold_for((z <= thr) & uptrend, h)
    return sig, pos


def _gap_fade(df, up_n=200, gap=-0.02, h=3):
    c = df["close"]
    gap_ret = c / c.shift(1) - 1.0                 # close-to-close proxy for the gap
    uptrend = c > sma(c, up_n)
    sig = (-gap_ret).where(uptrend)                # higher = bigger down-day to fade
    pos = hold_for((gap_ret <= gap) & uptrend, h)
    return sig, pos


def _internal_reversal(df, up_n=200, h=3):
    c, lo = df["close"], df.get("low", df["close"])
    cond = (lo < lo.shift(1)) & (c > c.shift(1))   # lower low, higher close
    uptrend = c > sma(c, up_n)
    # reversal score: today's up-close strength + how far below yesterday's low we dipped
    score = (c / c.shift(1) - 1.0) + (lo.shift(1) - lo).clip(lower=0.0) / c
    sig = score.where(uptrend)                     # higher = stronger intrabar reversal
    pos = hold_for(cond & uptrend, h)
    return sig, pos


def _oversold_uptrend(df, up_n=200, rsi_n=14, buy=35.0, h=10):
    c = df["close"]
    r = wilder_rsi(c, rsi_n)
    uptrend = c > sma(c, up_n)
    sig = (-r).where(uptrend)
    pos = hold_for((r < buy) & uptrend, h)
    return sig, pos


def _nr7_breakout(df, up_n=50, h=8):
    """Volatility-contraction (narrowest range in 7) then an up-close breakout."""
    c = df["close"]
    h_, l_ = df.get("high", c), df.get("low", c)
    rng = (h_ - l_)
    nr7 = rng <= rng.rolling(7, min_periods=7).min()
    breakout = c > c.shift(1)
    uptrend = c > sma(c, up_n)
    sig = (-(rng / sma(c, 20))).where(uptrend)     # higher = tighter coil
    pos = hold_for(nr7.shift(1).fillna(False) & breakout & uptrend, h)
    return sig, pos


# ---- trend / time-series momentum (selection / swing) ---------------------- #
def _tsmom_200(df, n=200):
    c = df["close"]
    sig = (c / sma(c, n) - 1.0)
    pos = (c > sma(c, n)).astype(float)
    return sig, pos


def _tsmom_10mo(df, n=210):
    c = df["close"]
    sig = (c / sma(c, n) - 1.0)
    pos = (c > sma(c, n)).astype(float)
    return sig, pos


def _tsmom_12_1(df, form=252, skip=21):
    c = df["close"]
    mom = c.shift(skip) / c.shift(form + skip) - 1.0
    sig = mom
    pos = (mom > 0).astype(float)
    return sig, pos


def _ma_cross(df, fast=50, slow=200):
    c = df["close"]
    f, s = sma(c, fast), sma(c, slow)
    sig = (f / s - 1.0)
    pos = (f > s).astype(float)
    return sig, pos


def _ma_slope(df, n=50, look=20):
    c = df["close"]
    m = sma(c, n)
    slope = m / m.shift(look) - 1.0
    sig = slope
    pos = ((slope > 0) & (c > m)).astype(float)
    return sig, pos


def _donchian(df, entry_n=55, exit_n=20):
    c = df["close"]
    sig = (c / c.rolling(entry_n, min_periods=entry_n).max() - 1.0)  # proximity to breakout high
    pos = donchian_position(df, entry_n, exit_n)
    return sig, pos


def _accel_mom(df, fast=63, slow=252):
    c = df["close"]
    mf = c / c.shift(fast) - 1.0
    msl = c / c.shift(slow) - 1.0
    sig = mf - msl                                 # acceleration: short mom > long mom
    pos = ((mf > 0) & (mf > msl)).astype(float)
    return sig, pos


def _vol_scaled_trend(df, n=200, vol_n=63, target=0.15):
    c = df["close"]
    trend = c > sma(c, n)
    rv = realized_vol(c, vol_n)
    scale = (target / rv).clip(upper=1.0)
    sig = (c / sma(c, n) - 1.0)
    pos = (trend.astype(float) * scale).fillna(0.0)
    return sig, pos


def _below_long_vol(df, vol_n=126):
    """Low-volatility state: lower trailing vol = the constructive read (low-vol anomaly)."""
    c = df["close"]
    rv = realized_vol(c, vol_n)
    sig = -rv
    pos = (rv < rv.rolling(252, min_periods=120).median()).astype(float)
    return sig, pos


REGISTRY = [
    # entry-timing / mean-reversion (short horizon → buy-in timing)
    Strat("rsi2_oversold", "RSI(2) oversold in uptrend", "mean_reversion", 5, _rsi2_oversold,
          None, "Connors short-term reversion; buy panic dips while >200dma."),
    Strat("bb_reversion", "Bollinger %b lower-band reversion", "mean_reversion", 10, _bb_reversion,
          None, "Buy below the lower band inside an uptrend."),
    Strat("dd_reversion", "Pullback-from-20d-high reversion", "mean_reversion", 10, _dd_reversion,
          None, "Buy a >=7% pullback from the recent high while >200dma."),
    Strat("dist_below_ma", "Stretch-below-20dma reversion", "mean_reversion", 8, _dist_below_ma,
          None, "Buy when price is unusually far below its 20dma in an uptrend."),
    Strat("gap_fade", "Down-day fade in uptrend", "entry_timing", 3, _gap_fade,
          None, "Fade a >=2% down day inside an uptrend."),
    Strat("internal_reversal", "Lower-low/higher-close reversal", "entry_timing", 3, _internal_reversal,
          None, "Internal-bar reversal (lower low, higher close) in an uptrend."),
    Strat("oversold_uptrend", "RSI(14)<35 buy-the-dip", "mean_reversion", 10, _oversold_uptrend,
          None, "Classic oversold-in-uptrend dip buy."),
    Strat("nr7_breakout", "NR7 volatility-contraction breakout", "breakout", 8, _nr7_breakout,
          None, "Buy the breakout after the tightest range in 7 bars."),
    # trend / TS-momentum (selection / swing)
    Strat("tsmom_200", "Above 200dma trend", "trend", 63, _tsmom_200,
          None, "Long while above the 200dma (Faber-style risk gate)."),
    Strat("tsmom_10mo", "Above 10-month MA trend", "trend", 63, _tsmom_10mo,
          None, "Long while above the 10-month MA."),
    Strat("tsmom_12_1", "Own 12-1 momentum > 0", "trend", 63, _tsmom_12_1,
          None, "Long while trailing 12-1 total return is positive."),
    Strat("ma_cross_50_200", "50/200 MA cross", "trend", 63, _ma_cross,
          None, "Golden/death cross trend state."),
    Strat("ma_slope_50", "Rising 50dma", "trend", 42, _ma_slope,
          None, "Long while the 50dma is rising and price is above it."),
    Strat("donchian_55_20", "Donchian 55/20 breakout", "breakout", 63, _donchian,
          None, "Turtle channel breakout with a 20-day trailing exit."),
    Strat("accel_mom", "Momentum acceleration", "trend", 42, _accel_mom,
          None, "Long when 3-month momentum leads 12-month momentum."),
    Strat("vol_scaled_trend", "Vol-targeted 200dma trend", "trend", 63, _vol_scaled_trend,
          None, "Above-200dma trend sized to a 15% vol target."),
    Strat("low_vol_state", "Low-volatility state", "trend", 63, _below_long_vol,
          None, "Long while realized vol sits below its 1-year median (low-vol anomaly)."),
]


def by_key() -> dict:
    return {s.key: s for s in REGISTRY}


# --------------------------------------------------------------------------- #
# COMBINED ENGINES — built from the strategies that survived honest validation.
#   * entry_timing_score  — blends the 5 mean-reversion entry overlays whose
#     short-horizon forward-return IC was FDR-significant (rsi2 / %b / pullback /
#     stretch-below-MA / RSI14). HIGHER = a better entry RIGHT NOW. The blend
#     diversifies idiosyncratic timing noise so its IC exceeds any single leg.
#   * exit_extension_score — the symmetric overbought/extension gauge for trimming
#     (sell-out timing): HIGHER = more stretched, worse spot to add.
#   * Both are oriented to be gated by an uptrend (the validated risk-control leg):
#     a dip is only a buy inside a constructive trend.
# These are pure, causal, and shaped exactly like the live build needs (call once at
# the latest bar) and the backtest needs (a full causal series).
# --------------------------------------------------------------------------- #
ENTRY_LEGS = ("rsi2", "pctb", "pullback", "stretch", "rsi14")


def _entry_leg_z(df: pd.DataFrame, z_n: int = 252) -> pd.DataFrame:
    """Causal z-scores of the surviving oversold legs, oriented HIGHER = more
    oversold (better entry). Each is z-scored over a trailing year so the blend is
    scale-free and comparable across names."""
    c = df["close"]
    legs = {
        "rsi2": _zscore(-wilder_rsi(c, 2), z_n),
        "pctb": _zscore(-bollinger_pctb(c, 20), z_n),
        "pullback": _zscore(-dd_from_high(c, 20), z_n),
        "stretch": _zscore(-(c / sma(c, 20) - 1.0), z_n),
        "rsi14": _zscore(-wilder_rsi(c, 14), z_n),
    }
    return pd.DataFrame(legs)


_ERF = np.vectorize(math.erf)


def _phi(z: pd.Series) -> pd.Series:
    """Standard-normal CDF of a z-series → a 0-1 percentile-like score (vectorized)."""
    arr = z.to_numpy(dtype=float)
    out = np.full(arr.shape, np.nan)
    m = np.isfinite(arr)
    out[m] = 0.5 * (1.0 + _ERF(arr[m] / np.sqrt(2.0)))
    return pd.Series(out, index=z.index)


def entry_timing_score(df: pd.DataFrame, gate_uptrend: bool = True) -> pd.Series:
    """0-100 'how good is right now as an entry' (HIGHER = more oversold-in-uptrend).
    Mean of the surviving entry legs' causal z-scores, mapped through Φ. When
    `gate_uptrend`, scores on non-uptrend bars are halved (a dip outside a trend is
    not a validated buy — the trend gate is the risk-control leg)."""
    c = df["close"]
    z = _entry_leg_z(df).mean(axis=1)
    score = 100.0 * _phi(z)
    if gate_uptrend:
        below = c <= sma(c, 200)
        score = score.where(~below.fillna(False), score * 0.5)
    return score


def entry_timing_z(df: pd.DataFrame) -> pd.Series:
    """The raw composite z (uncapped) — the continuous signal for IC/backtests."""
    return _entry_leg_z(df).mean(axis=1)


def exit_extension_score(df: pd.DataFrame) -> pd.Series:
    """0-100 overbought/extension gauge for SELL-OUT timing (HIGHER = more stretched).
    Mirror of the entry blend: short/medium RSI, %b, and distance above the 20/200dma."""
    c = df["close"]
    legs = pd.DataFrame({
        "rsi2": _zscore(wilder_rsi(c, 2), 252),
        "pctb": _zscore(bollinger_pctb(c, 20), 252),
        "rsi14": _zscore(wilder_rsi(c, 14), 252),
        "stretch20": _zscore(c / sma(c, 20) - 1.0, 252),
        "stretch200": _zscore(c / sma(c, 200) - 1.0, 252),
    })
    return 100.0 * _phi(legs.mean(axis=1))


def entry_composite_position(df: pd.DataFrame, h: int = 5, z_thr: float = 1.0) -> pd.Series:
    """Trend-gated entry rule for backtesting the combined engine: go long for `h`
    bars when price is in an uptrend AND the entry composite is at least `z_thr`
    standard deviations oversold. The combination of (validated trend gate) ×
    (validated oversold timing)."""
    c = df["close"]
    uptrend = c > sma(c, 200)
    z = entry_timing_z(df)
    return hold_for((z >= z_thr) & uptrend, h)


def selection_composite(closes: pd.DataFrame, asof, mkt: pd.Series) -> pd.Series:
    """Cross-sectional selection blend of the two FDR-significant XS legs: 12-1
    momentum and residual (beta-adjusted) 12-1 momentum, z-scored and averaged.
    CONTEXT only on a survivorship-biased universe — never sizes alone."""
    import engine.predictive_signals as _ps
    raw = _ps.mom_12_1(closes, asof)
    # residual momentum (inline, mirrors strategy_lab._xs_legs.resid_mom)
    sub = closes.loc[:asof]
    resid = pd.Series(dtype=float)
    if len(sub) >= 252 + 21 + 5 and mkt is not None:
        win = sub.iloc[-(252 + 21):]
        rets = win.pct_change()
        m = mkt.reindex(win.index).pct_change()
        mm = m.iloc[1:-21]
        if len(mm) >= 60 and (mm.var() or 0) > 0:
            mkt_mom = mkt.reindex(win.index).iloc[-22] / mkt.reindex(win.index).iloc[0] - 1.0
            out = {}
            for col in win.columns:
                r = rets[col].iloc[1:-21]
                j = pd.concat([r, mm], axis=1).dropna()
                if len(j) < 60:
                    continue
                beta = j.iloc[:, 0].cov(j.iloc[:, 1]) / (j.iloc[:, 1].var() or np.nan)
                rawmom = win[col].iloc[-22] / win[col].iloc[0] - 1.0
                if np.isfinite(beta) and np.isfinite(rawmom):
                    out[col] = rawmom - beta * mkt_mom
            resid = pd.Series(out)

    def _z(s):
        s = s.dropna()
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd else s * 0.0

    parts = [p for p in (_z(raw), _z(resid)) if len(p)]
    if not parts:
        return pd.Series(dtype=float)
    blend = pd.concat(parts, axis=1).mean(axis=1)
    return blend.dropna()
