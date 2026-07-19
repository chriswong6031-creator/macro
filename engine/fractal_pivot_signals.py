"""engine/fractal_pivot_signals.py — Williams Fractals and swing structure signals.

Display-tier causal pivot signals. No authority, no buy/sell commands, no composite
scores. Deterministic standard TA math — no LLM-originated signals, scores, or
escalations.

PIVOT CONFIRMATION CONTRACT
---------------------------
Williams fractal (n=2): bar i is a fractal HIGH iff
    High[i] > max(High[i-2], High[i-1])  AND  High[i] > max(High[i+1], High[i+2])
    (strict inequality on ALL four neighbours; ties break the fractal)

Bar i is a fractal LOW iff
    Low[i] < min(Low[i-2], Low[i-1])  AND  Low[i] < min(Low[i+1], Low[i+2])
    (strict; same tie rule)

CONFIRMATION BAR: the fractal at bar i is KNOWN at close of bar i+2 — the two
right-side bars required for comparison must be completed. Therefore ALL event
series place their fire on bar (i + 2), the confirmation bar. actionable_lag = 2.

CAUSALITY CONTRACT
------------------
Recomputing any signal on df.iloc[:k] reproduces the identical prefix. Classic
repaint trap: confirmed-fractal arrays are built using only forward-shifted
comparisons on the OHLCV array (no look-ahead on price), and the "most recent
confirmed level as of bar t" accumulator uses only bars <= t. The test suite
verifies the truncation-prefix property on both event and state signals.

Columns expected: close, high, low. NO open column used.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

_N: int = 2  # Williams fractal wings (not user-overridable; fixed by definition)


# ---------------------------------------------------------------------------
# Core: build confirmed-pivot boolean arrays (vectorized, causal)
# ---------------------------------------------------------------------------

def _confirmed_fractals(
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (fh_price, fh_conf, fl_price, fl_conf) aligned to df.index.

    fh_conf[t] == True  => bar t is the CONFIRMATION bar of a fractal HIGH
                           (the pivot was at bar t-2; its HIGH price = fh_price[t])
    fl_conf[t] == True  => bar t is the CONFIRMATION bar of a fractal LOW
                           (the pivot was at bar t-2; its LOW price = fl_price[t])

    Vectorized: we shift the high/low arrays rather than looping.  Because we use
    backward shifts for the left wings and forward shifts for the right wings, and
    we interpret the result as placing the event TWO bars after the pivot centre,
    there is no look-ahead relative to the confirmation bar.

    Specifically, at time t (the confirmation bar):
        pivot centre = t - 2
        left wings  = t-4, t-3  (already closed before t)
        right wings = t-1, t    (already closed at/before t)

    So on bar t we have ALL information needed for the decision.
    """
    n = len(df)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    # --- fractal HIGH ---
    # pivot centre c = t-2; left = t-4, t-3; right = t-1, t
    # We express in terms of confirmation bar index t:
    #   left_max[t]  = max(high[t-4], high[t-3])
    #   pivot_h[t]   = high[t-2]
    #   right_max[t] = max(high[t-1], high[t])
    # fractal HIGH confirmed at t iff pivot_h[t] > left_max[t] AND pivot_h[t] > right_max[t]
    pivot_h = np.empty(n); pivot_h[:] = np.nan
    pivot_h[4:] = high[2 : n - 2]         # high at centre (i = t-2)

    left_max_h = np.empty(n); left_max_h[:] = np.nan
    left_max_h[4:] = np.maximum(high[0 : n - 4], high[1 : n - 3])

    right_max_h = np.empty(n); right_max_h[:] = np.nan
    right_max_h[4:] = np.maximum(high[3 : n - 1], high[4 : n])

    fh_conf = np.zeros(n, dtype=bool)
    valid = np.isfinite(pivot_h) & np.isfinite(left_max_h) & np.isfinite(right_max_h)
    fh_conf[valid] = (pivot_h[valid] > left_max_h[valid]) & (pivot_h[valid] > right_max_h[valid])

    fh_price = np.where(fh_conf, pivot_h, np.nan)

    # --- fractal LOW ---
    # same logic using low and reversing the comparison direction
    pivot_l = np.empty(n); pivot_l[:] = np.nan
    pivot_l[4:] = low[2 : n - 2]

    left_min_l = np.empty(n); left_min_l[:] = np.nan
    left_min_l[4:] = np.minimum(low[0 : n - 4], low[1 : n - 3])

    right_min_l = np.empty(n); right_min_l[:] = np.nan
    right_min_l[4:] = np.minimum(low[3 : n - 1], low[4 : n])

    fl_conf = np.zeros(n, dtype=bool)
    fl_conf[valid] = (pivot_l[valid] < left_min_l[valid]) & (pivot_l[valid] < right_min_l[valid])

    fl_price = np.where(fl_conf, pivot_l, np.nan)

    return fh_price, fh_conf, fl_price, fl_conf


def _running_last_two(conf: np.ndarray, price: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (prev_price, last_price) arrays: at each bar the last TWO confirmed
    pivot prices seen up to and including that bar.

    Uses a tight numpy loop over the confirmation boolean array.  Required because
    this is a genuine stateful accumulator (tracking the last-two confirmed levels)
    — not a vectorizable windowed reduction.
    """
    n = len(conf)
    prev = np.full(n, np.nan)
    last = np.full(n, np.nan)
    _prev = np.nan
    _last = np.nan
    for t in range(n):
        if conf[t]:
            _prev = _last
            _last = price[t]
        prev[t] = _prev
        last[t] = _last
    return prev, last


def _running_last_one(conf: np.ndarray, price: np.ndarray) -> np.ndarray:
    """Most recent confirmed pivot price as of each bar (causal, accumulator)."""
    n = len(conf)
    out = np.full(n, np.nan)
    _last = np.nan
    for t in range(n):
        if conf[t]:
            _last = price[t]
        out[t] = _last
    return out


def _fire_once_per_level(cross: np.ndarray, level: np.ndarray) -> np.ndarray:
    """Fire event only on the FIRST bar per distinct confirmed level that is crossed.

    cross[t] = True means the raw cross condition is true at bar t.
    level[t] = the fractal level being watched at bar t (advances only on new
               confirmations; may be NaN before the first confirmation).

    We track the last level that generated a fire and suppress repeats.
    """
    n = len(cross)
    out = np.zeros(n, dtype=np.int8)
    _fired_level = np.nan
    for t in range(n):
        if cross[t] and not np.isnan(level[t]) and level[t] != _fired_level:
            out[t] = 1
            _fired_level = level[t]
    return out


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def fractal_low_confirm(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: a fractal low is confirmed on this bar (fires at bar i+2).

    Returns 0/1 int Series aligned to df.index.
    """
    _, _, _, fl_conf = _confirmed_fractals(df)
    return pd.Series(fl_conf.astype(np.int8), index=df.index, name="fractal_low_confirm")


def fractal_high_confirm(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: a fractal high is confirmed on this bar (fires at bar i+2).

    Returns 0/1 int Series aligned to df.index.
    """
    _, fh_conf, _, _ = _confirmed_fractals(df)
    return pd.Series(fh_conf.astype(np.int8), index=df.index, name="fractal_high_confirm")


def swing_uptrend(df: pd.DataFrame, **_params) -> pd.Series:
    """State: price is in a swing uptrend (HH + HL structure).

    1 iff the last two confirmed fractal highs are ascending (HH) AND
    the last two confirmed fractal lows are ascending (HL). Evaluated
    using only fractals confirmed as of each bar (causal).

    Returns 0/1 int Series.
    """
    fh_price, fh_conf, fl_price, fl_conf = _confirmed_fractals(df)

    fh_prev, fh_last = _running_last_two(fh_conf, fh_price)
    fl_prev, fl_last = _running_last_two(fl_conf, fl_price)

    hh = (fh_last > fh_prev) & np.isfinite(fh_prev) & np.isfinite(fh_last)
    hl = (fl_last > fl_prev) & np.isfinite(fl_prev) & np.isfinite(fl_last)
    result = (hh & hl).astype(np.int8)
    return pd.Series(result, index=df.index, name="swing_uptrend")


def swing_downtrend(df: pd.DataFrame, **_params) -> pd.Series:
    """State: price is in a swing downtrend (LL + LH structure).

    1 iff the last two confirmed fractal lows are descending (LL) AND
    the last two confirmed fractal highs are descending (LH). Evaluated
    using only fractals confirmed as of each bar (causal).

    Returns 0/1 int Series.
    """
    fh_price, fh_conf, fl_price, fl_conf = _confirmed_fractals(df)

    fh_prev, fh_last = _running_last_two(fh_conf, fh_price)
    fl_prev, fl_last = _running_last_two(fl_conf, fl_price)

    ll = (fl_last < fl_prev) & np.isfinite(fl_prev) & np.isfinite(fl_last)
    lh = (fh_last < fh_prev) & np.isfinite(fh_prev) & np.isfinite(fh_last)
    result = (ll & lh).astype(np.int8)
    return pd.Series(result, index=df.index, name="swing_downtrend")


def fractal_break_up(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: close crosses above the most recent confirmed fractal HIGH level.

    Fires once per level; a new confirmation resets the level and allows the next
    fire.  Level is known since the confirmation bar (causal, no repaint).

    Returns 0/1 int Series.
    """
    fh_price, fh_conf, _, _ = _confirmed_fractals(df)
    # Most recent confirmed fractal HIGH level as of each bar
    level = _running_last_one(fh_conf, fh_price)
    close = df["close"].to_numpy(dtype=float)
    raw_cross = (close > level) & np.isfinite(level)
    fired = _fire_once_per_level(raw_cross, level)
    return pd.Series(fired.astype(np.int8), index=df.index, name="fractal_break_up")


def fractal_break_dn(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: close crosses below the most recent confirmed fractal LOW level.

    Fires once per level; a new confirmation resets the level and allows the next
    fire.  Level is known since the confirmation bar (causal, no repaint).

    Returns 0/1 int Series.
    """
    _, _, fl_price, fl_conf = _confirmed_fractals(df)
    level = _running_last_one(fl_conf, fl_price)
    close = df["close"].to_numpy(dtype=float)
    raw_cross = (close < level) & np.isfinite(level)
    fired = _fire_once_per_level(raw_cross, level)
    return pd.Series(fired.astype(np.int8), index=df.index, name="fractal_break_dn")


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


_COMMON_META: dict[str, Any] = dict(
    family="fractal_pivots",
    dependency_family="fractal_structure",
    entry_stack_blocked=False,
    challenger_only=False,
    provenance=(
        "Williams, B. — Trading Chaos (1995); "
        "https://www.investopedia.com/terms/f/fractal.asp"
    ),
    actionable_lag=2,
)

SIGNALS: dict[str, dict[str, Any]] = {
    "fractal_low_confirm": {
        "fn": fractal_low_confirm,
        "kind": "event",
        "direction": +1,
        "role": "setup",
        "default_params": {},
        "display": _disp(
            "Fractal Low Confirmed (swing low locked in)",
            "分形低点确认（波段低点锁定）",
        ),
        "glyph": "arrow_up",
        **_COMMON_META,
    },
    "fractal_high_confirm": {
        "fn": fractal_high_confirm,
        "kind": "event",
        "direction": -1,
        "role": "setup",
        "default_params": {},
        "display": _disp(
            "Fractal High Confirmed (swing high locked in)",
            "分形高点确认（波段高点锁定）",
        ),
        "glyph": "arrow_down",
        **_COMMON_META,
    },
    "swing_uptrend": {
        "fn": swing_uptrend,
        "kind": "state",
        "direction": +1,
        "role": "context",
        "default_params": {},
        "display": _disp(
            "Swing Uptrend (higher highs and higher lows)",
            "波段上升趋势（高点高于前高，低点高于前低）",
        ),
        "glyph": "trend_up",
        **_COMMON_META,
    },
    "swing_downtrend": {
        "fn": swing_downtrend,
        "kind": "state",
        "direction": -1,
        "role": "context",
        "default_params": {},
        "display": _disp(
            "Swing Downtrend (lower lows and lower highs)",
            "波段下降趋势（低点低于前低，高点低于前高）",
        ),
        "glyph": "trend_down",
        **_COMMON_META,
    },
    "fractal_break_up": {
        "fn": fractal_break_up,
        "kind": "event",
        "direction": +1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Fractal High Break (close rises above confirmed swing high)",
            "分形高点突破（收盘价上穿已确认波段高点）",
        ),
        "glyph": "breakout_up",
        **_COMMON_META,
    },
    "fractal_break_dn": {
        "fn": fractal_break_dn,
        "kind": "event",
        "direction": -1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Fractal Low Break (close falls below confirmed swing low)",
            "分形低点跌破（收盘价下穿已确认波段低点）",
        ),
        "glyph": "breakout_dn",
        **_COMMON_META,
    },
}
