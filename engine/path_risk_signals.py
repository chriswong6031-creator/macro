"""engine/path_risk_signals.py — Path-risk and volatility-regime signals.

Display-tier descriptive signals. No authority, no buy/sell/stop commands,
no composite scores.

Families
--------
A) Ulcer Index (downside_path_risk)
   UI = sqrt(mean(PD^2, 14)) where PD_i = 100*(close_i/rollingmax(close,14)_i - 1).
   Source: Martin & McCann (1989).

B) Normalised ATR + Historical Volatility Ratio (volatility_regime)
   nATR = 100 * ATR(14) / close
   HVR  = realized_vol(close, 20) / realized_vol(close, 120)
   Reuses engine.stock_technicals.atr and engine.stock_technicals.realized_vol.

C) Mass Index (volatility_range, challenger_only=True)
   MI = rolling 25-sum of EMA(H-L, 9) / EMA(EMA(H-L, 9), 9).
   Source: Dorsey (1992).
   Signal fires on the bar the "bulge reversal" cross-back occurs (MI rises
   above 27 then falls back below 26.5). Direction-agnostic; needs an
   independent trigger leg.

CAUSALITY LAW
-------------
All rolling operations use trailing windows only (center=False is the pandas
default). Warm-up positions return 0 for events and 0 for states.
Recomputing on any prefix df.iloc[:k] reproduces the identical prefix of the
signal (no future mutation).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.stock_technicals import atr as _atr, realized_vol as _realized_vol

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters (frozen canonical set — do not change without a ruling)
# ---------------------------------------------------------------------------
_UI_N: int = 14          # Ulcer Index window
_UI_TRAIL: int = 252     # trailing percentile window (trading-day years)
_UI_SPIKE_LAG: int = 21  # lookback bars for spike comparison
_UI_RECOV_LAG: int = 21  # lookback bars for recovery condition

_NATR_N: int = 14        # ATR window
_NATR_TRAIL: int = 252   # trailing percentile window

_RV_SHORT: int = 20      # HVR short realized-vol window
_RV_LONG: int = 120      # HVR long realized-vol window
_HVR_COMPRESS: float = 0.75
_HVR_EXPAND: float = 1.25

_MI_EMA: int = 9         # Mass Index EMA period
_MI_SUM: int = 25        # Mass Index summation period
_MI_HIGH: float = 27.0   # bulge threshold
_MI_LOW: float = 26.5    # reversal trigger level


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ema(s: pd.Series, span: int) -> pd.Series:
    """Standard exponential moving average (adjust=False, min_periods=span)."""
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def _trailing_pct(s: pd.Series, window: int, q: float) -> pd.Series:
    """Rolling trailing percentile over *window* bars (inclusive of current bar)."""
    return s.rolling(window, min_periods=window).quantile(q)


def _ulcer_index(close: pd.Series, n: int = _UI_N) -> pd.Series:
    """Ulcer Index: sqrt(mean(PD^2, n)) where PD=100*(close/rollingmax(close,n)-1)."""
    rolling_max = close.rolling(n, min_periods=n).max()
    pd_series = 100.0 * (close / rolling_max.replace(0.0, np.nan) - 1.0)
    pd_sq = pd_series ** 2
    ui = np.sqrt(pd_sq.rolling(n, min_periods=n).mean())
    return ui


# ---------------------------------------------------------------------------
# A) Ulcer Index signals
# ---------------------------------------------------------------------------

def ui_calm(df: pd.DataFrame, n: int = _UI_N, trail: int = _UI_TRAIL) -> pd.Series:
    """State: Ulcer Index is below its trailing 252-day 25th percentile.

    Returns 0/1 integer Series. Low ulcer = drawdown stress is muted.
    During warm-up (fewer than n+trail bars) returns 0.
    """
    close = df["close"].astype(float)
    ui = _ulcer_index(close, n=n)
    pct25 = _trailing_pct(ui, trail, 0.25)
    result = (ui < pct25).astype(int)
    result = result.where(pct25.notna(), 0).astype(int)
    result.name = "ui_calm"
    return result


def ui_stressed(df: pd.DataFrame, n: int = _UI_N, trail: int = _UI_TRAIL) -> pd.Series:
    """State: Ulcer Index is above its trailing 252-day 75th percentile.

    Returns 0/1 integer Series. High ulcer = sustained drawdown stress.
    """
    close = df["close"].astype(float)
    ui = _ulcer_index(close, n=n)
    pct75 = _trailing_pct(ui, trail, 0.75)
    result = (ui > pct75).astype(int)
    result = result.where(pct75.notna(), 0).astype(int)
    result.name = "ui_stressed"
    return result


def ui_spike(
    df: pd.DataFrame,
    n: int = _UI_N,
    trail: int = _UI_TRAIL,
    spike_lag: int = _UI_SPIKE_LAG,
    ui_floor: float = 5.0,
) -> pd.Series:
    """Event: Ulcer Index more than doubles vs its value 21 bars ago AND UI > 5.

    Fires 0/1 on the completed bar where the spike is first knowable.
    """
    close = df["close"].astype(float)
    ui = _ulcer_index(close, n=n)
    ui_lag = ui.shift(spike_lag)
    # doubles = current > 2x lagged value; guard against zero/NaN lag
    doubled = (ui > 2.0 * ui_lag.replace(0.0, np.nan)) & (ui > ui_floor)
    result = doubled.fillna(False).astype(int)
    result.name = "ui_spike"
    return result


def ui_recovery(
    df: pd.DataFrame,
    n: int = _UI_N,
    trail: int = _UI_TRAIL,
    recov_lag: int = _UI_RECOV_LAG,
) -> pd.Series:
    """Event: UI was above its 252d 75th pct within last 21 bars and now crosses below the 252d median.

    Fires 0/1 on the bar of the downward cross below the 252d median,
    provided the stress condition was active within recov_lag bars.
    """
    close = df["close"].astype(float)
    ui = _ulcer_index(close, n=n)
    pct50 = _trailing_pct(ui, trail, 0.50)
    pct75 = _trailing_pct(ui, trail, 0.75)

    # was stressed = UI > 75th pct on that bar
    was_stressed = (ui > pct75).astype(int)
    # rolling OR: any stressed bar in the last recov_lag bars (inclusive)
    recently_stressed = was_stressed.rolling(recov_lag, min_periods=1).max()

    # cross below median: current bar below, previous bar at or above
    cross_below = (ui < pct50) & (ui.shift(1) >= pct50.shift(1))

    result = (recently_stressed.astype(bool) & cross_below).fillna(False).astype(int)
    # zero out during warm-up (before pct50 has enough history)
    result = result.where(pct50.notna() & pct75.notna(), 0).astype(int)
    result.name = "ui_recovery"
    return result


# ---------------------------------------------------------------------------
# B) Normalised ATR + Historical Volatility Ratio signals
# ---------------------------------------------------------------------------

def natr_low(
    df: pd.DataFrame,
    n: int = _NATR_N,
    trail: int = _NATR_TRAIL,
) -> pd.Series:
    """State: Normalised ATR (nATR = 100*ATR(14)/close) is below its 252d 25th pct.

    Low nATR = volatility compression relative to recent history.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    natr = 100.0 * _atr(high, low, close, n=n) / close.replace(0.0, np.nan)
    pct25 = _trailing_pct(natr, trail, 0.25)
    result = (natr < pct25).astype(int)
    result = result.where(pct25.notna(), 0).astype(int)
    result.name = "natr_low"
    return result


def natr_high(
    df: pd.DataFrame,
    n: int = _NATR_N,
    trail: int = _NATR_TRAIL,
) -> pd.Series:
    """State: Normalised ATR (nATR = 100*ATR(14)/close) is above its 252d 75th pct.

    High nATR = volatility expansion relative to recent history.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    natr = 100.0 * _atr(high, low, close, n=n) / close.replace(0.0, np.nan)
    pct75 = _trailing_pct(natr, trail, 0.75)
    result = (natr > pct75).astype(int)
    result = result.where(pct75.notna(), 0).astype(int)
    result.name = "natr_high"
    return result


def hvr_compress(
    df: pd.DataFrame,
    rv_short: int = _RV_SHORT,
    rv_long: int = _RV_LONG,
    threshold: float = _HVR_COMPRESS,
) -> pd.Series:
    """State: HVR = realized_vol(20) / realized_vol(120) is below 0.75.

    HVR < 0.75 = short-horizon vol well below long-horizon vol (compressed regime).
    """
    close = df["close"].astype(float)
    rv20 = _realized_vol(close, n=rv_short)
    rv120 = _realized_vol(close, n=rv_long)
    hvr = rv20 / rv120.replace(0.0, np.nan)
    result = (hvr < threshold).fillna(False).astype(int)
    result.name = "hvr_compress"
    return result


def hvr_expand_event(
    df: pd.DataFrame,
    rv_short: int = _RV_SHORT,
    rv_long: int = _RV_LONG,
    threshold: float = _HVR_EXPAND,
) -> pd.Series:
    """Event: HVR crosses above 1.25 from below (volatility expansion breakout).

    Fires 0/1 on the first bar where HVR >= 1.25 after being below 1.25.
    """
    close = df["close"].astype(float)
    rv20 = _realized_vol(close, n=rv_short)
    rv120 = _realized_vol(close, n=rv_long)
    hvr = rv20 / rv120.replace(0.0, np.nan)
    above = (hvr >= threshold)
    prev_above = above.shift(1).fillna(False).astype(bool)
    cross = above & ~prev_above
    result = cross.fillna(False).astype(int)
    result.name = "hvr_expand_event"
    return result


# ---------------------------------------------------------------------------
# C) Mass Index signal
# ---------------------------------------------------------------------------

def mass_bulge(
    df: pd.DataFrame,
    ema_n: int = _MI_EMA,
    sum_n: int = _MI_SUM,
    bulge_high: float = _MI_HIGH,
    bulge_low: float = _MI_LOW,
) -> pd.Series:
    """Event: Mass Index bulge reversal — MI rises above 27 then crosses back below 26.5.

    Fires 0/1 on the bar where MI crosses back below 26.5 (the setup bar),
    after having previously crossed above 27. Direction-agnostic: an independent
    trigger leg is needed to determine trade direction.

    MI = rolling(sum_n)-sum of EMA(H-L, ema_n) / EMA(EMA(H-L, ema_n), ema_n).
    Source: Dorsey (1992).
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    hl = high - low
    ema1 = _ema(hl, ema_n)
    ema2 = _ema(ema1, ema_n)
    ratio = ema1 / ema2.replace(0.0, np.nan)
    mi = ratio.rolling(sum_n, min_periods=sum_n).sum()

    # Track whether MI has risen above bulge_high using a forward-compatible stateful scan.
    # We use numpy arrays to avoid iterrows.
    mi_arr = mi.to_numpy(dtype=float)
    n = len(mi_arr)
    fired = np.zeros(n, dtype=int)

    bulge_active = False  # True once MI has crossed above bulge_high

    for i in range(n):
        v = mi_arr[i]
        if np.isnan(v):
            bulge_active = False
            continue
        if v > bulge_high:
            bulge_active = True
        if bulge_active and v < bulge_low:
            fired[i] = 1
            bulge_active = False  # reset: wait for next bulge

    result = pd.Series(fired, index=df.index, dtype=int, name="mass_bulge")
    return result


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # --- A) Ulcer Index ---
    "ui_calm": {
        "fn": ui_calm,
        "kind": "state",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"n": _UI_N, "trail": _UI_TRAIL},
        "display": _disp(
            "Low Drawdown Stress (Ulcer Index below 25th percentile)",
            "回撤压力低（溃疡指数低于25分位）",
        ),
        "glyph": "shield",
        # new metadata keys
        "dependency_family": "downside_path_risk",
        "role": "risk",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Martin & McCann (1989) — https://www.tangotools.com/ui/ui.htm",
        "actionable_lag": 0,
    },
    "ui_stressed": {
        "fn": ui_stressed,
        "kind": "state",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"n": _UI_N, "trail": _UI_TRAIL},
        "display": _disp(
            "Elevated Drawdown Stress (Ulcer Index above 75th percentile)",
            "回撤压力高（溃疡指数高于75分位）",
        ),
        "glyph": "warning",
        "dependency_family": "downside_path_risk",
        "role": "risk",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Martin & McCann (1989) — https://www.tangotools.com/ui/ui.htm",
        "actionable_lag": 0,
    },
    "ui_spike": {
        "fn": ui_spike,
        "kind": "event",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"n": _UI_N, "trail": _UI_TRAIL, "spike_lag": _UI_SPIKE_LAG, "ui_floor": 5.0},
        "display": _disp(
            "Drawdown Stress Spike (Ulcer Index doubles in 21 bars, above 5)",
            "回撤压力骤升（溃疡指数21日内翻倍且超过5）",
        ),
        "glyph": "alert",
        "dependency_family": "downside_path_risk",
        "role": "risk",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Martin & McCann (1989) — https://www.tangotools.com/ui/ui.htm",
        "actionable_lag": 0,
    },
    "ui_recovery": {
        "fn": ui_recovery,
        "kind": "event",
        "family": "path_risk",
        "direction": +1,
        "default_params": {"n": _UI_N, "trail": _UI_TRAIL, "recov_lag": _UI_RECOV_LAG},
        "display": _disp(
            "Drawdown Stress Easing (Ulcer Index crosses below median after stress period)",
            "回撤压力缓和（溃疡指数在压力期后跌破中位数）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "downside_path_risk",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Martin & McCann (1989) — https://www.tangotools.com/ui/ui.htm",
        "actionable_lag": 0,
    },
    # --- B) Normalised ATR + HVR ---
    "natr_low": {
        "fn": natr_low,
        "kind": "state",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"n": _NATR_N, "trail": _NATR_TRAIL},
        "display": _disp(
            "Low Relative Volatility (nATR below 25th percentile)",
            "相对波动率低（标准化ATR低于25分位）",
        ),
        "glyph": "compress",
        "dependency_family": "volatility_regime",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder (1978) ATR normalised — https://school.stockcharts.com/doku.php?id=technical_indicators:average_true_range_atr",
        "actionable_lag": 0,
    },
    "natr_high": {
        "fn": natr_high,
        "kind": "state",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"n": _NATR_N, "trail": _NATR_TRAIL},
        "display": _disp(
            "High Relative Volatility (nATR above 75th percentile)",
            "相对波动率高（标准化ATR高于75分位）",
        ),
        "glyph": "expand",
        "dependency_family": "volatility_regime",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Wilder (1978) ATR normalised — https://school.stockcharts.com/doku.php?id=technical_indicators:average_true_range_atr",
        "actionable_lag": 0,
    },
    "hvr_compress": {
        "fn": hvr_compress,
        "kind": "state",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"rv_short": _RV_SHORT, "rv_long": _RV_LONG, "threshold": _HVR_COMPRESS},
        "display": _disp(
            "Volatility Compression (short-window vol well below long-window vol)",
            "波动率压缩（短期波动率远低于长期波动率）",
        ),
        "glyph": "compress",
        "dependency_family": "volatility_regime",
        "role": "setup",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "HVR ratio — realized vol ratio (short/long window)",
        "actionable_lag": 0,
    },
    "hvr_expand_event": {
        "fn": hvr_expand_event,
        "kind": "event",
        "family": "path_risk",
        "direction": 0,
        "default_params": {"rv_short": _RV_SHORT, "rv_long": _RV_LONG, "threshold": _HVR_EXPAND},
        "display": _disp(
            "Volatility Expansion Breakout (short-window vol crosses above long-window vol)",
            "波动率扩张突破（短期波动率上穿长期波动率）",
        ),
        "glyph": "expand",
        "dependency_family": "volatility_regime",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "HVR ratio — realized vol ratio (short/long window)",
        "actionable_lag": 0,
    },
    # --- C) Mass Index ---
    "mass_bulge": {
        "fn": mass_bulge,
        "kind": "event",
        "family": "path_risk",
        "direction": 0,
        "default_params": {
            "ema_n": _MI_EMA,
            "sum_n": _MI_SUM,
            "bulge_high": _MI_HIGH,
            "bulge_low": _MI_LOW,
        },
        "display": _disp(
            "Mass Index Bulge Reversal (range expansion then contraction setup)",
            "质量指数鼓包回落（区间扩张后回缩信号）",
        ),
        "glyph": "alert",
        "dependency_family": "volatility_range",
        "role": "setup",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Dorsey (1992) — https://school.stockcharts.com/doku.php?id=technical_indicators:mass_index",
        "actionable_lag": 0,
    },
}
