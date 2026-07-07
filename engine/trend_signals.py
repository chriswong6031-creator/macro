"""engine/trend_signals.py — Trend + Performance-Based signals.

Reconstructs the StockInvest 'Performance-Based' and 'Trends' signal families:

  Trend direction (state, +1 / -1)
  ---------------------------------
  trend_rising_short   — short-term uptrend  (slope_z over 63d, R² filter)
  trend_falling_short  — short-term downtrend
  trend_rising_long    — long-term uptrend   (slope_z over 252d, R² filter)
  trend_falling_long   — long-term downtrend

  Event signals
  -------------
  possible_runners — momentum breakout: strong recent return + volume expansion
                     + price near 52-week high (event, fires on detection bar)

  Performance / cross-sectional metrics (state — ranked by caller)
  ----------------------------------------------------------------
  return_1d            — raw 1-day return (metric for top_gainers / top_losers ranking)
  is_strong_move       — boolean flag: |1d return| >= threshold (default 3%)

NOTE: top_gainers / top_losers are CROSS-SECTIONAL RANK signals.  The raw metric
(return_1d) and the is_strong_move flag are exposed per-ticker; the screener / catalog
sorts the universe by return_1d to produce the top-N / bottom-N lists.

PIT contract: every signal at bar t uses only data available at the CLOSE of bar t.
No centered windows, no future shifts.  Event signals fire on the bar they become
knowable.

Signal families & glyphs follow the common SIGNALS registry contract.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hyper-parameters (pre-registered — do not tune without a new pre-reg)
# ---------------------------------------------------------------------------
SHORT_WINDOW: int = 63     # ~3-month slope window
LONG_WINDOW: int = 252     # ~1-year slope window
BASELINE_WINDOW: int = 252 # volatility baseline for slope_z
R2_MIN: float = 0.10       # minimum R² to call a "coherent" trend
SLOPE_Z_THRESH: float = 1.0  # |slope_z| threshold to call rising/falling

# possible_runners
RUNNER_RET_WINDOW: int = 21    # recent return lookback (1 month)
RUNNER_RET_THRESH: float = 0.10  # >= 10% over 21 bars
RUNNER_VOL_WINDOW: int = 21    # volume comparison window
RUNNER_VOL_RATIO: float = 1.5  # current volume >= 1.5× avg
RUNNER_HIGH_PCT: float = 0.05  # price within 5% of 252d high

# 1d strong-move threshold
STRONG_MOVE_THRESH: float = 0.03  # |1d return| >= 3%


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rolling_r2(s: pd.Series, window: int) -> pd.Series:
    """Trailing R² of price series against linear time over `window` bars.

    R² = (corr(y, t))^2 over the window, which equals the fraction of variance
    explained by the trend.  PIT-clean (trailing window only).
    """
    t = np.arange(window, dtype=float)

    def _r2(y: np.ndarray) -> float:
        if np.isnan(y).any():
            return np.nan
        corr = float(np.corrcoef(y, t)[0, 1])
        return corr ** 2

    return s.rolling(window, min_periods=window).apply(_r2, raw=True)


# ---------------------------------------------------------------------------
# Trend direction signals
# ---------------------------------------------------------------------------

def trend_rising_short(df: pd.DataFrame,
                       window: int = SHORT_WINDOW,
                       baseline: int = BASELINE_WINDOW,
                       slope_z_thresh: float = SLOPE_Z_THRESH,
                       r2_min: float = R2_MIN) -> pd.Series:
    """Short-term rising-trend state series.

    State = +1 where:
      - slope_z(close, window, baseline) >= slope_z_thresh  (slope is clearly positive)
      - trailing R² >= r2_min  (trend is coherent, not noisy)
    State = 0 otherwise.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame with a 'close' column.
    window : int
        Slope/trend lookback in trading days (default 63).
    baseline : int
        Volatility baseline window for slope_z (default 252).
    slope_z_thresh : float
        Minimum slope_z score to call a rising trend (default 1.0).
    r2_min : float
        Minimum R² for coherent trend classification (default 0.10).

    Returns
    -------
    pd.Series
        State series in {0.0, 1.0}, named 'trend_rising_short'.
    """
    from engine.indicators import slope_z  # noqa: PLC0415

    close = df["close"]
    sz = slope_z(close, window, baseline)
    r2 = _rolling_r2(close, window)

    state = ((sz >= slope_z_thresh) & (r2 >= r2_min)).astype(float)
    state = state.where(sz.notna() & r2.notna(), other=np.nan)
    state.name = "trend_rising_short"
    return state


def trend_falling_short(df: pd.DataFrame,
                        window: int = SHORT_WINDOW,
                        baseline: int = BASELINE_WINDOW,
                        slope_z_thresh: float = SLOPE_Z_THRESH,
                        r2_min: float = R2_MIN) -> pd.Series:
    """Short-term falling-trend state series.

    State = +1 (direction flag = -1 in catalog) where:
      - slope_z(close, window, baseline) <= -slope_z_thresh
      - trailing R² >= r2_min

    Returns
    -------
    pd.Series
        State series in {0.0, 1.0}, named 'trend_falling_short'.
        Catalog direction = -1 (bearish signal).
    """
    from engine.indicators import slope_z  # noqa: PLC0415

    close = df["close"]
    sz = slope_z(close, window, baseline)
    r2 = _rolling_r2(close, window)

    state = ((sz <= -slope_z_thresh) & (r2 >= r2_min)).astype(float)
    state = state.where(sz.notna() & r2.notna(), other=np.nan)
    state.name = "trend_falling_short"
    return state


def trend_rising_long(df: pd.DataFrame,
                      window: int = LONG_WINDOW,
                      baseline: int = BASELINE_WINDOW,
                      slope_z_thresh: float = SLOPE_Z_THRESH,
                      r2_min: float = R2_MIN) -> pd.Series:
    """Long-term rising-trend state series (252d lookback).

    Same construction as trend_rising_short but with a 252-bar window.

    Returns
    -------
    pd.Series
        State series in {0.0, 1.0}, named 'trend_rising_long'.
    """
    from engine.indicators import slope_z  # noqa: PLC0415

    close = df["close"]
    sz = slope_z(close, window, baseline)
    r2 = _rolling_r2(close, window)

    state = ((sz >= slope_z_thresh) & (r2 >= r2_min)).astype(float)
    state = state.where(sz.notna() & r2.notna(), other=np.nan)
    state.name = "trend_rising_long"
    return state


def trend_falling_long(df: pd.DataFrame,
                       window: int = LONG_WINDOW,
                       baseline: int = BASELINE_WINDOW,
                       slope_z_thresh: float = SLOPE_Z_THRESH,
                       r2_min: float = R2_MIN) -> pd.Series:
    """Long-term falling-trend state series (252d lookback).

    Returns
    -------
    pd.Series
        State series in {0.0, 1.0}, named 'trend_falling_long'.
        Catalog direction = -1 (bearish signal).
    """
    from engine.indicators import slope_z  # noqa: PLC0415

    close = df["close"]
    sz = slope_z(close, window, baseline)
    r2 = _rolling_r2(close, window)

    state = ((sz <= -slope_z_thresh) & (r2 >= r2_min)).astype(float)
    state = state.where(sz.notna() & r2.notna(), other=np.nan)
    state.name = "trend_falling_long"
    return state


# ---------------------------------------------------------------------------
# Momentum breakout event
# ---------------------------------------------------------------------------

def possible_runners(df: pd.DataFrame,
                     ret_window: int = RUNNER_RET_WINDOW,
                     ret_thresh: float = RUNNER_RET_THRESH,
                     vol_window: int = RUNNER_VOL_WINDOW,
                     vol_ratio: float = RUNNER_VOL_RATIO,
                     high_pct: float = RUNNER_HIGH_PCT,
                     high_window: int = 252) -> pd.Series:
    """Possible momentum runner event signal.

    Event fires (1.0) on bar t when ALL of:
      1. Recent return: close[t] / close[t - ret_window] - 1 >= ret_thresh
         (strong recent momentum over ~1 month)
      2. Volume expansion: volume[t] >= vol_ratio × avg_volume[t - vol_window : t-1]
         (current bar volume significantly above recent average)
      3. Near highs: close[t] >= (1 - high_pct) × max(close[t-high_window : t])
         (price within high_pct% of the trailing high_window high)

    All conditions are strictly trailing (no bar t+1 data).  Volume condition
    degrades gracefully: if no volume column, the volume gate is skipped.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame (close required; volume used if present).
    ret_window : int
        Return lookback in trading days for recent momentum (default 21).
    ret_thresh : float
        Minimum return over ret_window to qualify (default 0.10 = 10%).
    vol_window : int
        Volume averaging window (default 21).
    vol_ratio : float
        Minimum ratio of current volume to avg volume (default 1.5).
    high_pct : float
        Maximum distance below trailing high to qualify (default 0.05 = 5%).
    high_window : int
        Lookback for trailing high (default 252 bars).

    Returns
    -------
    pd.Series
        Event series in {0.0, 1.0}, named 'possible_runners'.
    """
    close = df["close"]

    # Gate 1: recent momentum
    past_close = close.shift(ret_window)
    recent_ret = close / past_close.replace(0.0, np.nan) - 1.0
    ret_ok = recent_ret >= ret_thresh

    # Gate 2: volume expansion (skip if no volume)
    if "volume" in df.columns:
        vol = df["volume"]
        # avg volume over [t-vol_window, t-1] — exclude current bar (no look-ahead on
        # the AVERAGE; current bar volume is observed at close, which is knowable at t)
        avg_vol = vol.shift(1).rolling(vol_window, min_periods=max(5, vol_window // 2)).mean()
        vol_ok = vol >= vol_ratio * avg_vol.replace(0.0, np.nan)
    else:
        vol_ok = pd.Series(True, index=close.index)

    # Gate 3: near trailing high (use shift(1) for the max so the current bar's close
    # doesn't trivially satisfy the gate by being the exact max — we include t itself
    # because StockInvest's "near highs" criterion is based on current price vs the
    # recent high, which is observable at close t)
    trailing_high = close.rolling(high_window, min_periods=high_window // 2).max()
    near_high = close >= (1.0 - high_pct) * trailing_high.replace(0.0, np.nan)

    fire = (ret_ok & vol_ok & near_high).astype(float)
    fire = fire.where(recent_ret.notna() & trailing_high.notna(), other=0.0)
    fire.name = "possible_runners"
    return fire


# ---------------------------------------------------------------------------
# Performance / cross-sectional metrics
# ---------------------------------------------------------------------------

def return_1d(df: pd.DataFrame) -> pd.Series:
    """Raw 1-day close-to-close return.

    This is the RAW METRIC used by the screener / catalog to rank the universe
    for top_gainers and top_losers.  The caller sorts by this metric and picks
    the top-N / bottom-N.  Cross-sectional ranking is intentionally left to the
    caller — this function exposes the per-ticker measurement only.

    Returns
    -------
    pd.Series
        1d return series aligned to df.index, named 'return_1d'.
    """
    out = df["close"].pct_change(fill_method=None)
    out.name = "return_1d"
    return out


def is_strong_move(df: pd.DataFrame,
                   thresh: float = STRONG_MOVE_THRESH) -> pd.Series:
    """Boolean flag: |1d return| >= thresh.

    Accompanies return_1d for top_gainers / top_losers filtering.  A value of
    1.0 flags that the day's move is large enough to be a genuine gap/surge
    rather than noise.

    Returns
    -------
    pd.Series
        State series in {0.0, 1.0}, named 'is_strong_move'.
    """
    r = df["close"].pct_change(fill_method=None).abs()
    out = (r >= thresh).astype(float)
    out.name = "is_strong_move"
    return out


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    "trend_rising_short": {
        "fn": trend_rising_short,
        "kind": "state",
        "family": "trend",
        "direction": +1,
        "default_params": {
            "window": SHORT_WINDOW,
            "baseline": BASELINE_WINDOW,
            "slope_z_thresh": SLOPE_Z_THRESH,
            "r2_min": R2_MIN,
        },
        "display": {
            "en": "Short-term Rising Trend",
            "zh": "短期上升趋势",
        },
        "glyph": "arrow_up",
    },
    "trend_falling_short": {
        "fn": trend_falling_short,
        "kind": "state",
        "family": "trend",
        "direction": -1,
        "default_params": {
            "window": SHORT_WINDOW,
            "baseline": BASELINE_WINDOW,
            "slope_z_thresh": SLOPE_Z_THRESH,
            "r2_min": R2_MIN,
        },
        "display": {
            "en": "Short-term Falling Trend",
            "zh": "短期下降趋势",
        },
        "glyph": "arrow_down",
    },
    "trend_rising_long": {
        "fn": trend_rising_long,
        "kind": "state",
        "family": "trend",
        "direction": +1,
        "default_params": {
            "window": LONG_WINDOW,
            "baseline": BASELINE_WINDOW,
            "slope_z_thresh": SLOPE_Z_THRESH,
            "r2_min": R2_MIN,
        },
        "display": {
            "en": "Long-term Rising Trend",
            "zh": "长期上升趋势",
        },
        "glyph": "arrow_up",
    },
    "trend_falling_long": {
        "fn": trend_falling_long,
        "kind": "state",
        "family": "trend",
        "direction": -1,
        "default_params": {
            "window": LONG_WINDOW,
            "baseline": BASELINE_WINDOW,
            "slope_z_thresh": SLOPE_Z_THRESH,
            "r2_min": R2_MIN,
        },
        "display": {
            "en": "Long-term Falling Trend",
            "zh": "长期下降趋势",
        },
        "glyph": "arrow_down",
    },
    "possible_runners": {
        "fn": possible_runners,
        "kind": "event",
        "family": "performance",
        "direction": +1,
        "default_params": {
            "ret_window": RUNNER_RET_WINDOW,
            "ret_thresh": RUNNER_RET_THRESH,
            "vol_window": RUNNER_VOL_WINDOW,
            "vol_ratio": RUNNER_VOL_RATIO,
            "high_pct": RUNNER_HIGH_PCT,
            "high_window": 252,
        },
        "display": {
            "en": "Possible Runner (Momentum Breakout)",
            "zh": "潜在突破股（动量突破）",
        },
        "glyph": "star_gold",
    },
    "return_1d": {
        "fn": return_1d,
        "kind": "state",
        "family": "performance",
        "direction": 0,
        "default_params": {},
        "display": {
            "en": "1-Day Return (cross-sectional rank → top/bottom gainers)",
            "zh": "1日收益率（横截面排名 → 涨跌幅榜）",
        },
        "glyph": "line",
    },
    "is_strong_move": {
        "fn": is_strong_move,
        "kind": "state",
        "family": "performance",
        "direction": 0,
        "default_params": {"thresh": STRONG_MOVE_THRESH},
        "display": {
            "en": "Strong 1-Day Move Flag",
            "zh": "强势单日波动标志",
        },
        "glyph": "circle_green",
    },
}
