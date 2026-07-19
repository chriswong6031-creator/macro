"""engine/trend_strength_signals.py — Trend-strength signal family.

Implements four indicator groups as display-tier descriptive signals:
  A) ADX/DMI (Wilder 1978) — directional trend strength and direction crosses
  B) Aroon (Chande 1995) — trend recency via highest/lowest look-back
  C) Vortex (Botes & Siepman 2010) — directional movement via true-range ratios
  D) Elder Ray (Elder 1993) — bull/bear power relative to an EMA

Signal fns take (df, **params) where df is a single-ticker OHLCV DataFrame with
columns close/high/low/volume and DatetimeIndex (or any comparable index). There
is NO 'open' column — never reference it.

Events = 0/1 int (1 only on the completed bar where the condition becomes KNOWN).
States = 0/1 int (or float for direction=0 display scores).
PIT-clean: computed from completed bars only; no center=True; no future windows.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.stock_technicals import adx_dmi, atr

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross helpers (shared with momentum_events idiom)
# ---------------------------------------------------------------------------

def _cross_above(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1.0 where *a* crosses strictly above *b*; requires valid opposite prior bar."""
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a > b) & (a.shift(1) <= b_prev)
    return cond.fillna(False).astype(float)


def _cross_below(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1.0 where *a* crosses strictly below *b*; requires valid opposite prior bar."""
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a < b) & (a.shift(1) >= b_prev)
    return cond.fillna(False).astype(float)


def _rising(s: pd.Series, window: int) -> pd.Series:
    """True where s > s.shift(window) (strictly rising over *window* bars)."""
    return s > s.shift(window)


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


# ===========================================================================
# A) ADX / DMI signals  (dependency_family='directional_trend')
# ===========================================================================

def di_cross_up(df: pd.DataFrame, *, n: int = 14) -> pd.Series:
    """Event: +DI crosses above -DI (bullish directional cross)."""
    _, pdi, mdi = adx_dmi(df["high"], df["low"], df["close"], n=n)
    fired = _cross_above(pdi, mdi)
    fired.name = "di_cross_up"
    return fired.astype(int)


def di_cross_dn(df: pd.DataFrame, *, n: int = 14) -> pd.Series:
    """Event: -DI crosses above +DI (bearish directional cross)."""
    _, pdi, mdi = adx_dmi(df["high"], df["low"], df["close"], n=n)
    fired = _cross_above(mdi, pdi)
    fired.name = "di_cross_dn"
    return fired.astype(int)


def adx_ignite_up(df: pd.DataFrame, *, n: int = 14, threshold: float = 25.0) -> pd.Series:
    """Event: ADX crosses above *threshold* while +DI > -DI (trend ignition, bullish)."""
    adx, pdi, mdi = adx_dmi(df["high"], df["low"], df["close"], n=n)
    cross = _cross_above(adx, threshold)
    fired = (cross.astype(bool) & (pdi > mdi)).astype(float)
    fired.name = "adx_ignite_up"
    return fired.astype(int)


def adx_ignite_dn(df: pd.DataFrame, *, n: int = 14, threshold: float = 25.0) -> pd.Series:
    """Event: ADX crosses above *threshold* while -DI > +DI (trend ignition, bearish)."""
    adx, pdi, mdi = adx_dmi(df["high"], df["low"], df["close"], n=n)
    cross = _cross_above(adx, threshold)
    fired = (cross.astype(bool) & (mdi > pdi)).astype(float)
    fired.name = "adx_ignite_dn"
    return fired.astype(int)


def adx_trending(df: pd.DataFrame, *, n: int = 14, threshold: float = 25.0, rise_bars: int = 5) -> pd.Series:
    """State: ADX >= *threshold* and ADX is rising over the last *rise_bars* bars."""
    adx, _, _ = adx_dmi(df["high"], df["low"], df["close"], n=n)
    state = (adx >= threshold) & _rising(adx, rise_bars)
    result = state.fillna(False).astype(int)
    result.name = "adx_trending"
    return result


def adx_weak(df: pd.DataFrame, *, n: int = 14, weak_threshold: float = 20.0) -> pd.Series:
    """State: ADX < *weak_threshold* (trend absent or fading)."""
    adx, _, _ = adx_dmi(df["high"], df["low"], df["close"], n=n)
    result = (adx < weak_threshold).fillna(False).astype(int)
    result.name = "adx_weak"
    return result


# ===========================================================================
# B) Aroon signals  n=25  (dependency_family='trend_recency')
# ===========================================================================

def _aroon(df: pd.DataFrame, n: int = 25) -> tuple[pd.Series, pd.Series]:
    """Aroon Up/Down for period *n* (Chande 1995).

    AroonUp  = 100 * (n - bars_since_highest_high) / n
    AroonDown = 100 * (n - bars_since_lowest_low)  / n

    Uses a rolling window of length n+1 (includes current bar) to find the
    position of the high/low within the window.  Tie rule: most RECENT bar
    wins ties (argmax/argmin return the FIRST occurrence in the window, so we
    flip and re-flip to prefer the rightmost position).
    """
    high = df["high"].to_numpy(dtype=float)
    low  = df["low"].to_numpy(dtype=float)
    m = len(high)
    au = np.zeros(m)
    ad = np.zeros(m)
    window = n + 1  # lookback including current bar

    for i in range(m):
        if i < n:
            # warm-up: not enough bars; leave 0
            continue
        h_window = high[i - n: i + 1]  # length n+1
        l_window = low[i - n: i + 1]

        # argmax/argmin of reversed array → most recent occurrence wins ties
        rev_h = h_window[::-1]
        rev_l = l_window[::-1]
        bars_since_high = np.argmax(rev_h)   # 0 = current bar
        bars_since_low  = np.argmin(rev_l)

        au[i] = 100.0 * (n - bars_since_high) / n
        ad[i] = 100.0 * (n - bars_since_low)  / n

    idx = df.index
    return pd.Series(au, index=idx), pd.Series(ad, index=idx)


def aroon_cross_up(
    df: pd.DataFrame, *, n: int = 25, min_separation: float = 20.0
) -> pd.Series:
    """Event: Aroon Up crosses above Aroon Down with >= *min_separation* gap at cross bar."""
    au, ad = _aroon(df, n=n)
    cross = _cross_above(au, ad)
    # Require min_separation at the cross bar
    fired = (cross.astype(bool) & ((au - ad) >= min_separation)).astype(float)
    fired.name = "aroon_cross_up"
    return fired.astype(int)


def aroon_cross_dn(
    df: pd.DataFrame, *, n: int = 25, min_separation: float = 20.0
) -> pd.Series:
    """Event: Aroon Down crosses above Aroon Up with >= *min_separation* gap at cross bar."""
    au, ad = _aroon(df, n=n)
    cross = _cross_above(ad, au)
    fired = (cross.astype(bool) & ((ad - au) >= min_separation)).astype(float)
    fired.name = "aroon_cross_dn"
    return fired.astype(int)


def aroon_up_strong(
    df: pd.DataFrame, *, n: int = 25, up_thresh: float = 70.0, dn_thresh: float = 30.0
) -> pd.Series:
    """State: Aroon Up > *up_thresh* and Aroon Down < *dn_thresh* (strong uptrend)."""
    au, ad = _aroon(df, n=n)
    result = ((au > up_thresh) & (ad < dn_thresh)).astype(int)
    result.name = "aroon_up_strong"
    return result


def aroon_dn_strong(
    df: pd.DataFrame, *, n: int = 25, up_thresh: float = 30.0, dn_thresh: float = 70.0
) -> pd.Series:
    """State: Aroon Down > *dn_thresh* and Aroon Up < *up_thresh* (strong downtrend)."""
    au, ad = _aroon(df, n=n)
    result = ((ad > dn_thresh) & (au < up_thresh)).astype(int)
    result.name = "aroon_dn_strong"
    return result


# ===========================================================================
# C) Vortex signals  n=14  (dependency_family='directional_trend')
# ===========================================================================

def _vortex(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series]:
    """Vortex Indicator (Botes & Siepman 2010).

    VM+ = |high - prev_low|
    VM- = |low  - prev_high|
    TR  = Wilder true range
    VI+ = sum(VM+, n) / sum(TR, n)
    VI- = sum(VM-, n) / sum(TR, n)
    """
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    vm_plus  = (high - low.shift(1)).abs()
    vm_minus = (low  - high.shift(1)).abs()

    # True range (no Wilder smoothing — we sum over n bars)
    pc = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - pc).abs(), (low - pc).abs()], axis=1
    ).max(axis=1)

    vi_plus  = vm_plus.rolling(n, min_periods=n).sum() / tr.rolling(n, min_periods=n).sum()
    vi_minus = vm_minus.rolling(n, min_periods=n).sum() / tr.rolling(n, min_periods=n).sum()

    return vi_plus, vi_minus


def vi_cross_up(
    df: pd.DataFrame, *, n: int = 14, min_gap: float = 0.05
) -> pd.Series:
    """Event: VI+ crosses above VI- with |VI+ - VI-| >= *min_gap* at cross bar."""
    vip, vim = _vortex(df, n=n)
    cross = _cross_above(vip, vim)
    fired = (cross.astype(bool) & ((vip - vim) >= min_gap)).astype(float)
    fired.name = "vi_cross_up"
    return fired.astype(int)


def vi_cross_dn(
    df: pd.DataFrame, *, n: int = 14, min_gap: float = 0.05
) -> pd.Series:
    """Event: VI- crosses above VI+ with |VI- - VI+| >= *min_gap* at cross bar."""
    vip, vim = _vortex(df, n=n)
    cross = _cross_above(vim, vip)
    fired = (cross.astype(bool) & ((vim - vip) >= min_gap)).astype(float)
    fired.name = "vi_cross_dn"
    return fired.astype(int)


# ===========================================================================
# D) Elder Ray signals  n=13  (dependency_family='price_pressure')
# ===========================================================================

def _elder_ray(df: pd.DataFrame, *, n: int = 13) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bull Power, Bear Power, and EMA(close, n) for Elder Ray (Elder 1993).

    BullPower = high - EMA(close, n)
    BearPower = low  - EMA(close, n)
    """
    close = df["close"].astype(float)
    ema13 = _ema(close, n)
    bull = df["high"].astype(float) - ema13
    bear = df["low"].astype(float)  - ema13
    return bull, bear, ema13


def elder_bear_flip_up(
    df: pd.DataFrame, *, n: int = 13, slope_bars: int = 5
) -> pd.Series:
    """Event (bullish): canonical Elder buy setup — newly true this bar.

    Fires when ALL of the following are true AND the condition was false on the
    prior bar (entry-bar-only semantics):
      1. BearPower < 0 (bear power negative — bears still in control)
      2. BearPower rising vs prior bar (improving from below)
      3. EMA13 slope over *slope_bars* bars > 0 (trend up)
    """
    bull, bear, ema13 = _elder_ray(df, n=n)
    ema_slope = ema13 - ema13.shift(slope_bars)
    condition = (bear < 0) & (bear > bear.shift(1)) & (ema_slope > 0)
    # entry-bar-only: condition newly true this bar (use int shift to avoid ~bool deprecation)
    cond_int = condition.fillna(False).astype(int)
    fired = ((cond_int == 1) & (cond_int.shift(1, fill_value=0) == 0)).astype(int)
    fired.name = "elder_bear_flip_up"
    return fired


def elder_bull_flip_dn(
    df: pd.DataFrame, *, n: int = 13, slope_bars: int = 5
) -> pd.Series:
    """Event (bearish): canonical Elder sell setup — newly true this bar.

    Fires when ALL of the following are true AND the condition was false on the
    prior bar:
      1. BullPower > 0 (bull power positive — bulls still in control)
      2. BullPower falling vs prior bar (weakening from above)
      3. EMA13 slope over *slope_bars* bars < 0 (trend down)
    """
    bull, bear, ema13 = _elder_ray(df, n=n)
    ema_slope = ema13 - ema13.shift(slope_bars)
    condition = (bull > 0) & (bull < bull.shift(1)) & (ema_slope < 0)
    cond_int = condition.fillna(False).astype(int)
    fired = ((cond_int == 1) & (cond_int.shift(1, fill_value=0) == 0)).astype(int)
    fired.name = "elder_bull_flip_dn"
    return fired


def elder_bulls_dominant(
    df: pd.DataFrame, *, n: int = 13, atr_n: int = 14, bear_atr_floor: float = -0.25
) -> pd.Series:
    """State: BullPower > 0 and BearPower > -0.25 * ATR14 (bulls in command)."""
    bull, bear, _ = _elder_ray(df, n=n)
    atr14 = atr(df["high"], df["low"], df["close"], n=atr_n)
    result = ((bull > 0) & (bear > bear_atr_floor * atr14)).fillna(False).astype(int)
    result.name = "elder_bulls_dominant"
    return result


def elder_bears_dominant(
    df: pd.DataFrame, *, n: int = 13, atr_n: int = 14, bull_atr_floor: float = 0.25
) -> pd.Series:
    """State: BearPower < 0 and BullPower < 0.25 * ATR14 (bears in command)."""
    bull, bear, _ = _elder_ray(df, n=n)
    atr14 = atr(df["high"], df["low"], df["close"], n=atr_n)
    result = ((bear < 0) & (bull < bull_atr_floor * atr14)).fillna(False).astype(int)
    result.name = "elder_bears_dominant"
    return result


# ===========================================================================
# SIGNALS registry
# ===========================================================================

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # --- A) ADX / DMI ---
    "di_cross_up": {
        "fn": di_cross_up,
        "kind": "event",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 14},
        "display": _disp(
            "Directional Indicator Bullish Cross (+DI above -DI)",
            "方向指标金叉（+DI 上穿 -DI）",
        ),
        "glyph": "arrow_up",
        # new metadata keys
        "dependency_family": "directional_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder 1978 / https://www.investopedia.com/terms/a/adx.asp",
        "actionable_lag": 0,
    },
    "di_cross_dn": {
        "fn": di_cross_dn,
        "kind": "event",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 14},
        "display": _disp(
            "Directional Indicator Bearish Cross (-DI above +DI)",
            "方向指标死叉（-DI 上穿 +DI）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "directional_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder 1978 / https://www.investopedia.com/terms/a/adx.asp",
        "actionable_lag": 0,
    },
    "adx_ignite_up": {
        "fn": adx_ignite_up,
        "kind": "event",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 14, "threshold": 25.0},
        "display": _disp(
            "ADX Trend Ignition — Bullish (ADX crosses above 25 while price rising)",
            "ADX 趋势启动（多头）— ADX 上穿 25 且价格上行",
        ),
        "glyph": "arrow_up",
        "dependency_family": "directional_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder 1978 / https://www.investopedia.com/terms/a/adx.asp",
        "actionable_lag": 0,
    },
    "adx_ignite_dn": {
        "fn": adx_ignite_dn,
        "kind": "event",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 14, "threshold": 25.0},
        "display": _disp(
            "ADX Trend Ignition — Bearish (ADX crosses above 25 while price falling)",
            "ADX 趋势启动（空头）— ADX 上穿 25 且价格下行",
        ),
        "glyph": "arrow_down",
        "dependency_family": "directional_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder 1978 / https://www.investopedia.com/terms/a/adx.asp",
        "actionable_lag": 0,
    },
    "adx_trending": {
        "fn": adx_trending,
        "kind": "state",
        "family": "trend_strength",
        "direction": 0,
        "default_params": {"n": 14, "threshold": 25.0, "rise_bars": 5},
        "display": _disp(
            "ADX Trending (ADX ≥ 25 and rising — strong, accelerating trend)",
            "ADX 强势趋势（ADX ≥ 25 且持续上升）",
        ),
        "glyph": "trend",
        "dependency_family": "directional_trend",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder 1978 / https://www.investopedia.com/terms/a/adx.asp",
        "actionable_lag": 0,
    },
    "adx_weak": {
        "fn": adx_weak,
        "kind": "state",
        "family": "trend_strength",
        "direction": 0,
        "default_params": {"n": 14, "weak_threshold": 20.0},
        "display": _disp(
            "ADX Weak Trend (ADX < 20 — market ranging, no directional conviction)",
            "ADX 趋势疲弱（ADX < 20 — 市场震荡，方向不明）",
        ),
        "glyph": "flat",
        "dependency_family": "directional_trend",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder 1978 / https://www.investopedia.com/terms/a/adx.asp",
        "actionable_lag": 0,
    },
    # --- B) Aroon ---
    "aroon_cross_up": {
        "fn": aroon_cross_up,
        "kind": "event",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 25, "min_separation": 20.0},
        "display": _disp(
            "Aroon Bullish Cross (recent highs dominating — uptrend beginning)",
            "Aroon 金叉（近期高点主导，上升趋势启动）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "trend_recency",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Chande 1995 / https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/aroon",
        "actionable_lag": 0,
    },
    "aroon_cross_dn": {
        "fn": aroon_cross_dn,
        "kind": "event",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 25, "min_separation": 20.0},
        "display": _disp(
            "Aroon Bearish Cross (recent lows dominating — downtrend beginning)",
            "Aroon 死叉（近期低点主导，下降趋势启动）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "trend_recency",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Chande 1995 / https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/aroon",
        "actionable_lag": 0,
    },
    "aroon_up_strong": {
        "fn": aroon_up_strong,
        "kind": "state",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 25, "up_thresh": 70.0, "dn_thresh": 30.0},
        "display": _disp(
            "Aroon Strong Uptrend (recent highs near current bar, lows far away)",
            "Aroon 强势上涨（近期高点接近当前，低点遥远）",
        ),
        "glyph": "trend_up",
        "dependency_family": "trend_recency",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Chande 1995 / https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/aroon",
        "actionable_lag": 0,
    },
    "aroon_dn_strong": {
        "fn": aroon_dn_strong,
        "kind": "state",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 25, "up_thresh": 30.0, "dn_thresh": 70.0},
        "display": _disp(
            "Aroon Strong Downtrend (recent lows near current bar, highs far away)",
            "Aroon 强势下跌（近期低点接近当前，高点遥远）",
        ),
        "glyph": "trend_dn",
        "dependency_family": "trend_recency",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Chande 1995 / https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/aroon",
        "actionable_lag": 0,
    },
    # --- C) Vortex ---
    "vi_cross_up": {
        "fn": vi_cross_up,
        "kind": "event",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 14, "min_gap": 0.05},
        "display": _disp(
            "Vortex Bullish Cross (VI+ above VI- with separation — upward momentum)",
            "漩涡指标金叉（VI+ 超过 VI-，间距显著）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "directional_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Botes & Siepman 2010 / https://www.investopedia.com/terms/v/vortex-indicator-vi.asp",
        "actionable_lag": 0,
    },
    "vi_cross_dn": {
        "fn": vi_cross_dn,
        "kind": "event",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 14, "min_gap": 0.05},
        "display": _disp(
            "Vortex Bearish Cross (VI- above VI+ with separation — downward momentum)",
            "漩涡指标死叉（VI- 超过 VI+，间距显著）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "directional_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Botes & Siepman 2010 / https://www.investopedia.com/terms/v/vortex-indicator-vi.asp",
        "actionable_lag": 0,
    },
    # --- D) Elder Ray ---
    "elder_bear_flip_up": {
        "fn": elder_bear_flip_up,
        "kind": "event",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 13, "slope_bars": 5},
        "display": _disp(
            "Elder Ray Bullish Setup (bear power negative but improving, price trend up)",
            "长老射线多头信号（空头力量为负但回升，价格趋势向上）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "price_pressure",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Elder 1993 / https://www.investopedia.com/terms/e/elderray.asp",
        "actionable_lag": 0,
    },
    "elder_bull_flip_dn": {
        "fn": elder_bull_flip_dn,
        "kind": "event",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 13, "slope_bars": 5},
        "display": _disp(
            "Elder Ray Bearish Setup (bull power positive but falling, price trend down)",
            "长老射线空头信号（多头力量为正但回落，价格趋势向下）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "price_pressure",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Elder 1993 / https://www.investopedia.com/terms/e/elderray.asp",
        "actionable_lag": 0,
    },
    "elder_bulls_dominant": {
        "fn": elder_bulls_dominant,
        "kind": "state",
        "family": "trend_strength",
        "direction": +1,
        "default_params": {"n": 13, "atr_n": 14, "bear_atr_floor": -0.25},
        "display": _disp(
            "Elder Ray Bulls Dominant (bull power positive, bear power near zero)",
            "长老射线多头主导（多头力量为正，空头力量接近零）",
        ),
        "glyph": "bull",
        "dependency_family": "price_pressure",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Elder 1993 / https://www.investopedia.com/terms/e/elderray.asp",
        "actionable_lag": 0,
    },
    "elder_bears_dominant": {
        "fn": elder_bears_dominant,
        "kind": "state",
        "family": "trend_strength",
        "direction": -1,
        "default_params": {"n": 13, "atr_n": 14, "bull_atr_floor": 0.25},
        "display": _disp(
            "Elder Ray Bears Dominant (bear power negative, bull power near zero)",
            "长老射线空头主导（空头力量为负，多头力量接近零）",
        ),
        "glyph": "bear",
        "dependency_family": "price_pressure",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Elder 1993 / https://www.investopedia.com/terms/e/elderray.asp",
        "actionable_lag": 0,
    },
}
