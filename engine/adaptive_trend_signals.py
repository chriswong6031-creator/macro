"""engine/adaptive_trend_signals.py — KAMA / Efficiency-Ratio and SuperTrend signals.

Display-tier adaptive-trend chart-grammar signals (family 'adaptive_trend' and
'atr_adaptive_trend').  No authority, no buy/sell/stop commands, no composite scores.

Standing constraint: both families carry entry_stack_blocked=True per RUL-33
(KAMA ER — BASEEFF kill; SuperTrend — OSCSPECIES kill).  These signals are
display-tier / confluence inputs only.

Provenance
----------
KAMA:       Kaufman, Perry J. *Smarter Trading*, McGraw-Hill, 1995.
SuperTrend: Olivier Seban; TradingView canonical spec
            https://www.tradingview.com/support/solutions/43000634738-supertrend/

Signals
-------
  kama_cross_up      event  +1  close crosses above KAMA while ER > 0.30
  kama_cross_dn      event  -1  close crosses below KAMA while ER > 0.30
  kama_slope_up      state  +1  KAMA slope positive over 10 bars AND ER > 0.30
  kama_slope_dn      state  -1  KAMA slope negative over 10 bars AND ER > 0.30
  er_efficient       state   0  ER > 0.30 (market is trending efficiently)
  er_choppy          state   0  ER < 0.10 (market is choppy / mean-reverting)
  st_flip_up         event  +1  SuperTrend flips bearish → bullish
  st_flip_dn         event  -1  SuperTrend flips bullish → bearish
  st_bull_state      state  +1  SuperTrend currently in bullish regime
  st_bear_state      state  -1  SuperTrend currently in bearish regime
  st_pullback_hold   event  +1  In bull state ≥ 5 bars, low touches within
                                0.5*ATR10 of the supertrend line then close
                                recovers above it (new pullback-and-hold event)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# KAMA constants
# ---------------------------------------------------------------------------
_KAMA_N: int = 10          # efficiency-ratio lookback
_KAMA_FAST: int = 2        # fast EMA periods
_KAMA_SLOW: int = 30       # slow EMA periods

_ER_EFFICIENT: float = 0.30
_ER_CHOPPY: float = 0.10
_KAMA_SLOPE_WINDOW: int = 10

# ---------------------------------------------------------------------------
# SuperTrend constants
# ---------------------------------------------------------------------------
_ST_ATR_N: int = 10
_ST_MULT: float = 3.0
_ST_PULLBACK_ATR_FRAC: float = 0.5
_ST_PULLBACK_MIN_BULL_BARS: int = 5


# ===========================================================================
# KAMA internals
# ===========================================================================

def _compute_kama(
    close: np.ndarray,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (kama, er) arrays aligned to *close*.

    Seeding: KAMA is NaN for the first n-1 bars; at bar index n-1 (0-based)
    KAMA is seeded with SMA(close, n).  ER is NaN for the first n bars
    (requires close[i-n] for direction and n absolute differences).

    The recurrence is a tight numpy loop (unavoidable — KAMA_t depends on
    KAMA_{t-1}).  No center=True, no future windows.

    fast_sc = 2/(fast+1); slow_sc = 2/(slow+1)
    SC_t = (ER_t * (fast_sc - slow_sc) + slow_sc)^2
    KAMA_t = KAMA_{t-1} + SC_t * (close_t - KAMA_{t-1})
    """
    T = len(close)
    kama = np.full(T, np.nan, dtype=float)
    er = np.full(T, np.nan, dtype=float)

    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)

    if T < n:
        return kama, er

    # Seed at bar n-1 (0-indexed): SMA of the first n closes.
    seed_idx = n - 1
    kama[seed_idx] = np.mean(close[:n])

    for i in range(n, T):
        # Efficiency Ratio over the last n bars
        direction = abs(close[i] - close[i - n])
        noise = np.sum(np.abs(np.diff(close[i - n: i + 1])))
        if noise == 0.0:
            er_i = 0.0
        else:
            er_i = direction / noise
        er[i] = er_i

        sc = (er_i * (fast_sc - slow_sc) + slow_sc) ** 2
        kama[i] = kama[i - 1] + sc * (close[i] - kama[i - 1])

    return kama, er


# ===========================================================================
# KAMA signal functions
# ===========================================================================

def kama_cross_up(
    df: pd.DataFrame,
    *,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
    er_threshold: float = _ER_EFFICIENT,
) -> pd.Series:
    """Event: close crosses above KAMA while ER > er_threshold.

    Fires on the first bar where close > KAMA AND prior bar close <= prior KAMA
    AND current ER > er_threshold.  Returns {0, 1} int.
    """
    close = df["close"].to_numpy(dtype=float)
    kama_arr, er_arr = _compute_kama(close, n=n, fast=fast, slow=slow)

    T = len(close)
    out = np.zeros(T, dtype=int)
    for i in range(1, T):
        if np.isnan(kama_arr[i]) or np.isnan(kama_arr[i - 1]) or np.isnan(er_arr[i]):
            continue
        if (close[i] > kama_arr[i]
                and close[i - 1] <= kama_arr[i - 1]
                and er_arr[i] > er_threshold):
            out[i] = 1

    return pd.Series(out, index=df.index, name="kama_cross_up")


def kama_cross_dn(
    df: pd.DataFrame,
    *,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
    er_threshold: float = _ER_EFFICIENT,
) -> pd.Series:
    """Event: close crosses below KAMA while ER > er_threshold.

    Returns {0, 1} int.
    """
    close = df["close"].to_numpy(dtype=float)
    kama_arr, er_arr = _compute_kama(close, n=n, fast=fast, slow=slow)

    T = len(close)
    out = np.zeros(T, dtype=int)
    for i in range(1, T):
        if np.isnan(kama_arr[i]) or np.isnan(kama_arr[i - 1]) or np.isnan(er_arr[i]):
            continue
        if (close[i] < kama_arr[i]
                and close[i - 1] >= kama_arr[i - 1]
                and er_arr[i] > er_threshold):
            out[i] = 1

    return pd.Series(out, index=df.index, name="kama_cross_dn")


def kama_slope_up(
    df: pd.DataFrame,
    *,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
    er_threshold: float = _ER_EFFICIENT,
    slope_window: int = _KAMA_SLOPE_WINDOW,
) -> pd.Series:
    """State: KAMA is rising over slope_window bars AND ER > er_threshold.

    'Rising' means kama[i] > kama[i - slope_window].  Returns {0, 1} int.
    """
    close = df["close"].to_numpy(dtype=float)
    kama_arr, er_arr = _compute_kama(close, n=n, fast=fast, slow=slow)

    T = len(close)
    out = np.zeros(T, dtype=int)
    for i in range(slope_window, T):
        if (np.isnan(kama_arr[i]) or np.isnan(kama_arr[i - slope_window])
                or np.isnan(er_arr[i])):
            continue
        if kama_arr[i] > kama_arr[i - slope_window] and er_arr[i] > er_threshold:
            out[i] = 1

    return pd.Series(out, index=df.index, name="kama_slope_up")


def kama_slope_dn(
    df: pd.DataFrame,
    *,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
    er_threshold: float = _ER_EFFICIENT,
    slope_window: int = _KAMA_SLOPE_WINDOW,
) -> pd.Series:
    """State: KAMA is falling over slope_window bars AND ER > er_threshold.

    Returns {0, 1} int.
    """
    close = df["close"].to_numpy(dtype=float)
    kama_arr, er_arr = _compute_kama(close, n=n, fast=fast, slow=slow)

    T = len(close)
    out = np.zeros(T, dtype=int)
    for i in range(slope_window, T):
        if (np.isnan(kama_arr[i]) or np.isnan(kama_arr[i - slope_window])
                or np.isnan(er_arr[i])):
            continue
        if kama_arr[i] < kama_arr[i - slope_window] and er_arr[i] > er_threshold:
            out[i] = 1

    return pd.Series(out, index=df.index, name="kama_slope_dn")


def er_efficient(
    df: pd.DataFrame,
    *,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
    er_threshold: float = _ER_EFFICIENT,
) -> pd.Series:
    """State: ER > er_threshold (market trending efficiently).

    Returns {0, 1} int; 0 during warm-up.
    """
    close = df["close"].to_numpy(dtype=float)
    _, er_arr = _compute_kama(close, n=n, fast=fast, slow=slow)

    out = np.where(~np.isnan(er_arr) & (er_arr > er_threshold), 1, 0).astype(int)
    return pd.Series(out, index=df.index, name="er_efficient")


def er_choppy(
    df: pd.DataFrame,
    *,
    n: int = _KAMA_N,
    fast: int = _KAMA_FAST,
    slow: int = _KAMA_SLOW,
    er_choppy_threshold: float = _ER_CHOPPY,
) -> pd.Series:
    """State: ER < er_choppy_threshold (market is choppy / mean-reverting).

    Returns {0, 1} int; 0 during warm-up.
    """
    close = df["close"].to_numpy(dtype=float)
    _, er_arr = _compute_kama(close, n=n, fast=fast, slow=slow)

    out = np.where(~np.isnan(er_arr) & (er_arr < er_choppy_threshold), 1, 0).astype(int)
    return pd.Series(out, index=df.index, name="er_choppy")


# ===========================================================================
# SuperTrend internals
# ===========================================================================

def _wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    """Wilder ATR (RMA / exponential smoothing with alpha = 1/n).

    True range for bar i (i>0) = max(high[i]-low[i], |high[i]-close[i-1]|, |low[i]-close[i-1]|).
    For bar 0: TR = high[0] - low[0].
    Seed: simple mean of first n TRs, then Wilder smoothing from bar n onward.
    Returns array of length T; NaN for bars < n-1.
    """
    T = len(close)
    tr = np.empty(T, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, T):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    atr = np.full(T, np.nan, dtype=float)
    if T < n:
        return atr

    # Seed at bar n-1
    atr[n - 1] = np.mean(tr[:n])
    alpha = 1.0 / n
    for i in range(n, T):
        atr[i] = atr[i - 1] * (1.0 - alpha) + tr[i] * alpha

    return atr


def _compute_supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    n: int = _ST_ATR_N,
    mult: float = _ST_MULT,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (supertrend_line, direction) arrays.

    direction[i] = +1 (bullish) or -1 (bearish).
    supertrend_line[i] is the active band value used as support/resistance.
    Both are NaN for warm-up bars.

    Ratchet rules (per Seban canonical):
      upper_t = basicUpper_t   if (basicUpper_t < upper_{t-1} OR close_{t-1} > upper_{t-1})
                else upper_{t-1}
      lower_t = basicLower_t   if (basicLower_t > lower_{t-1} OR close_{t-1} < lower_{t-1})
                else lower_{t-1}

    Trend flip:
      if direction_{t-1} == -1 and close_t > upper_{t-1}: flip to +1
      if direction_{t-1} == +1 and close_t < lower_{t-1}: flip to -1
    """
    T = len(close)
    atr = _wilder_atr(high, low, close, n)

    st_line = np.full(T, np.nan, dtype=float)
    direction = np.full(T, np.nan, dtype=float)

    upper = np.full(T, np.nan, dtype=float)
    lower = np.full(T, np.nan, dtype=float)

    # Find first valid ATR index
    first_valid = n - 1
    if T <= first_valid:
        return st_line, direction

    # Initialize at first_valid bar
    hl2 = (high[first_valid] + low[first_valid]) / 2.0
    upper[first_valid] = hl2 + mult * atr[first_valid]
    lower[first_valid] = hl2 - mult * atr[first_valid]

    # Seed direction: bullish if close >= midpoint
    direction[first_valid] = +1.0
    st_line[first_valid] = lower[first_valid]

    for i in range(first_valid + 1, T):
        hl2_i = (high[i] + low[i]) / 2.0
        basic_upper = hl2_i + mult * atr[i]
        basic_lower = hl2_i - mult * atr[i]

        # Ratchet upper: only move down (tighten) unless prior close exceeded it
        if basic_upper < upper[i - 1] or close[i - 1] > upper[i - 1]:
            upper[i] = basic_upper
        else:
            upper[i] = upper[i - 1]

        # Ratchet lower: only move up (tighten) unless prior close fell below it
        if basic_lower > lower[i - 1] or close[i - 1] < lower[i - 1]:
            lower[i] = basic_lower
        else:
            lower[i] = lower[i - 1]

        # Determine new direction
        prev_dir = direction[i - 1]
        if prev_dir == -1.0 and close[i] > upper[i - 1]:
            direction[i] = +1.0
        elif prev_dir == +1.0 and close[i] < lower[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = prev_dir

        # Active band = support in bull, resistance in bear
        st_line[i] = lower[i] if direction[i] == +1.0 else upper[i]

    return st_line, direction


# ===========================================================================
# SuperTrend signal functions
# ===========================================================================

def st_flip_up(
    df: pd.DataFrame,
    *,
    n: int = _ST_ATR_N,
    mult: float = _ST_MULT,
) -> pd.Series:
    """Event: SuperTrend flips from bearish to bullish.  Returns {0, 1} int."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    _, direction = _compute_supertrend(high, low, close, n=n, mult=mult)

    T = len(close)
    out = np.zeros(T, dtype=int)
    for i in range(1, T):
        if np.isnan(direction[i]) or np.isnan(direction[i - 1]):
            continue
        if direction[i - 1] == -1.0 and direction[i] == +1.0:
            out[i] = 1

    return pd.Series(out, index=df.index, name="st_flip_up")


def st_flip_dn(
    df: pd.DataFrame,
    *,
    n: int = _ST_ATR_N,
    mult: float = _ST_MULT,
) -> pd.Series:
    """Event: SuperTrend flips from bullish to bearish.  Returns {0, 1} int."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    _, direction = _compute_supertrend(high, low, close, n=n, mult=mult)

    T = len(close)
    out = np.zeros(T, dtype=int)
    for i in range(1, T):
        if np.isnan(direction[i]) or np.isnan(direction[i - 1]):
            continue
        if direction[i - 1] == +1.0 and direction[i] == -1.0:
            out[i] = 1

    return pd.Series(out, index=df.index, name="st_flip_dn")


def st_bull_state(
    df: pd.DataFrame,
    *,
    n: int = _ST_ATR_N,
    mult: float = _ST_MULT,
) -> pd.Series:
    """State: SuperTrend is in bullish regime.  Returns {0, 1} int."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    _, direction = _compute_supertrend(high, low, close, n=n, mult=mult)

    out = np.where(~np.isnan(direction) & (direction == +1.0), 1, 0).astype(int)
    return pd.Series(out, index=df.index, name="st_bull_state")


def st_bear_state(
    df: pd.DataFrame,
    *,
    n: int = _ST_ATR_N,
    mult: float = _ST_MULT,
) -> pd.Series:
    """State: SuperTrend is in bearish regime.  Returns {0, 1} int."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    _, direction = _compute_supertrend(high, low, close, n=n, mult=mult)

    out = np.where(~np.isnan(direction) & (direction == -1.0), 1, 0).astype(int)
    return pd.Series(out, index=df.index, name="st_bear_state")


def st_pullback_hold(
    df: pd.DataFrame,
    *,
    n: int = _ST_ATR_N,
    mult: float = _ST_MULT,
    pullback_atr_frac: float = _ST_PULLBACK_ATR_FRAC,
    min_bull_bars: int = _ST_PULLBACK_MIN_BULL_BARS,
) -> pd.Series:
    """Event: pullback-and-hold in bull state.

    Fires on bar i when ALL of:
      1. direction[i] == +1 (still bullish — no flip)
      2. consecutive bull bars going into bar i >= min_bull_bars
         (bar i-1 was the (min_bull_bars-1)-th or later bull bar)
      3. low[i] <= st_line[i] + pullback_atr_frac * atr[i]   (touched near support)
      4. close[i] > st_line[i]   (closes back above the line)

    Returns {0, 1} int.  PIT-clean: only data at bar i and earlier used.
    """
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    st_line, direction = _compute_supertrend(high, low, close, n=n, mult=mult)
    atr = _wilder_atr(high, low, close, n)

    T = len(close)
    out = np.zeros(T, dtype=int)

    # Count consecutive bull bars up to but not including current bar
    consec_bull = np.zeros(T, dtype=int)
    for i in range(1, T):
        if np.isnan(direction[i - 1]):
            consec_bull[i] = 0
        elif direction[i - 1] == +1.0:
            consec_bull[i] = consec_bull[i - 1] + 1
        else:
            consec_bull[i] = 0

    for i in range(1, T):
        if np.isnan(direction[i]) or np.isnan(st_line[i]) or np.isnan(atr[i]):
            continue
        if direction[i] != +1.0:
            continue
        if consec_bull[i] < min_bull_bars:
            continue
        tolerance = pullback_atr_frac * atr[i]
        if low[i] <= st_line[i] + tolerance and close[i] > st_line[i]:
            out[i] = 1

    return pd.Series(out, index=df.index, name="st_pullback_hold")


# ===========================================================================
# SIGNALS registry
# ===========================================================================

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # ── KAMA / ER ──────────────────────────────────────────────────────────
    "kama_cross_up": {
        "fn": kama_cross_up,
        "kind": "event",
        "family": "adaptive_trend",
        "direction": +1,
        "default_params": {
            "n": _KAMA_N,
            "fast": _KAMA_FAST,
            "slow": _KAMA_SLOW,
            "er_threshold": _ER_EFFICIENT,
        },
        "display": _disp(
            "Price crosses above adaptive moving average in trending market",
            "价格向上穿越自适应均线（趋势市场）",
        ),
        "glyph": "arrow_up",
        # New metadata keys
        "dependency_family": "adaptive_trend",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Kaufman, Perry J. Smarter Trading, McGraw-Hill 1995; "
                      "https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average",
        "actionable_lag": 0,
    },
    "kama_cross_dn": {
        "fn": kama_cross_dn,
        "kind": "event",
        "family": "adaptive_trend",
        "direction": -1,
        "default_params": {
            "n": _KAMA_N,
            "fast": _KAMA_FAST,
            "slow": _KAMA_SLOW,
            "er_threshold": _ER_EFFICIENT,
        },
        "display": _disp(
            "Price crosses below adaptive moving average in trending market",
            "价格向下穿越自适应均线（趋势市场）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "adaptive_trend",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Kaufman, Perry J. Smarter Trading, McGraw-Hill 1995; "
                      "https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average",
        "actionable_lag": 0,
    },
    "kama_slope_up": {
        "fn": kama_slope_up,
        "kind": "state",
        "family": "adaptive_trend",
        "direction": +1,
        "default_params": {
            "n": _KAMA_N,
            "fast": _KAMA_FAST,
            "slow": _KAMA_SLOW,
            "er_threshold": _ER_EFFICIENT,
            "slope_window": _KAMA_SLOPE_WINDOW,
        },
        "display": _disp(
            "Adaptive moving average rising in trending market",
            "自适应均线上行（趋势市场）",
        ),
        "glyph": "trend_up",
        "dependency_family": "adaptive_trend",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Kaufman, Perry J. Smarter Trading, McGraw-Hill 1995; "
                      "https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average",
        "actionable_lag": 0,
    },
    "kama_slope_dn": {
        "fn": kama_slope_dn,
        "kind": "state",
        "family": "adaptive_trend",
        "direction": -1,
        "default_params": {
            "n": _KAMA_N,
            "fast": _KAMA_FAST,
            "slow": _KAMA_SLOW,
            "er_threshold": _ER_EFFICIENT,
            "slope_window": _KAMA_SLOPE_WINDOW,
        },
        "display": _disp(
            "Adaptive moving average falling in trending market",
            "自适应均线下行（趋势市场）",
        ),
        "glyph": "trend_dn",
        "dependency_family": "adaptive_trend",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Kaufman, Perry J. Smarter Trading, McGraw-Hill 1995; "
                      "https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average",
        "actionable_lag": 0,
    },
    "er_efficient": {
        "fn": er_efficient,
        "kind": "state",
        "family": "adaptive_trend",
        "direction": 0,
        "default_params": {
            "n": _KAMA_N,
            "fast": _KAMA_FAST,
            "slow": _KAMA_SLOW,
            "er_threshold": _ER_EFFICIENT,
        },
        "display": _disp(
            "Market moving efficiently — trend-following conditions present",
            "市场高效运行——适合趋势跟踪",
        ),
        "glyph": "signal",
        "dependency_family": "adaptive_trend",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Kaufman, Perry J. Smarter Trading, McGraw-Hill 1995; "
                      "https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average",
        "actionable_lag": 0,
    },
    "er_choppy": {
        "fn": er_choppy,
        "kind": "state",
        "family": "adaptive_trend",
        "direction": 0,
        "default_params": {
            "n": _KAMA_N,
            "fast": _KAMA_FAST,
            "slow": _KAMA_SLOW,
            "er_choppy_threshold": _ER_CHOPPY,
        },
        "display": _disp(
            "Market choppy — trend signals unreliable",
            "市场震荡——趋势信号可靠性低",
        ),
        "glyph": "noise",
        "dependency_family": "adaptive_trend",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Kaufman, Perry J. Smarter Trading, McGraw-Hill 1995; "
                      "https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average",
        "actionable_lag": 0,
    },
    # ── SuperTrend ─────────────────────────────────────────────────────────
    "st_flip_up": {
        "fn": st_flip_up,
        "kind": "event",
        "family": "atr_adaptive_trend",
        "direction": +1,
        "default_params": {
            "n": _ST_ATR_N,
            "mult": _ST_MULT,
        },
        "display": _disp(
            "Trend turns bullish — price breaks above resistance band",
            "趋势转多——价格突破上方阻力带",
        ),
        "glyph": "arrow_up",
        "dependency_family": "atr_adaptive_trend",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Olivier Seban; "
                      "https://www.tradingview.com/support/solutions/43000634738-supertrend/",
        "actionable_lag": 0,
    },
    "st_flip_dn": {
        "fn": st_flip_dn,
        "kind": "event",
        "family": "atr_adaptive_trend",
        "direction": -1,
        "default_params": {
            "n": _ST_ATR_N,
            "mult": _ST_MULT,
        },
        "display": _disp(
            "Trend turns bearish — price breaks below support band",
            "趋势转空——价格跌破下方支撑带",
        ),
        "glyph": "arrow_down",
        "dependency_family": "atr_adaptive_trend",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Olivier Seban; "
                      "https://www.tradingview.com/support/solutions/43000634738-supertrend/",
        "actionable_lag": 0,
    },
    "st_bull_state": {
        "fn": st_bull_state,
        "kind": "state",
        "family": "atr_adaptive_trend",
        "direction": +1,
        "default_params": {
            "n": _ST_ATR_N,
            "mult": _ST_MULT,
        },
        "display": _disp(
            "Price above trend support — bullish regime",
            "价格位于趋势支撑上方——多头格局",
        ),
        "glyph": "bull",
        "dependency_family": "atr_adaptive_trend",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Olivier Seban; "
                      "https://www.tradingview.com/support/solutions/43000634738-supertrend/",
        "actionable_lag": 0,
    },
    "st_bear_state": {
        "fn": st_bear_state,
        "kind": "state",
        "family": "atr_adaptive_trend",
        "direction": -1,
        "default_params": {
            "n": _ST_ATR_N,
            "mult": _ST_MULT,
        },
        "display": _disp(
            "Price below trend resistance — bearish regime",
            "价格位于趋势阻力下方——空头格局",
        ),
        "glyph": "bear",
        "dependency_family": "atr_adaptive_trend",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Olivier Seban; "
                      "https://www.tradingview.com/support/solutions/43000634738-supertrend/",
        "actionable_lag": 0,
    },
    "st_pullback_hold": {
        "fn": st_pullback_hold,
        "kind": "event",
        "family": "atr_adaptive_trend",
        "direction": +1,
        "default_params": {
            "n": _ST_ATR_N,
            "mult": _ST_MULT,
            "pullback_atr_frac": _ST_PULLBACK_ATR_FRAC,
            "min_bull_bars": _ST_PULLBACK_MIN_BULL_BARS,
        },
        "display": _disp(
            "Price pulls back to trend support then recovers — continuation setup",
            "价格回踩趋势支撑后收复——持续形态",
        ),
        "glyph": "pullback",
        "dependency_family": "atr_adaptive_trend",
        "role": "setup",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Olivier Seban; "
                      "https://www.tradingview.com/support/solutions/43000634738-supertrend/",
        "actionable_lag": 0,
    },
}
