"""engine/formations.py — Chart Formations: Double Bottoms, Double Tops, Bollinger Breakouts.

Reconstructs the StockInvest 'Formations' signal group:
  - double_bottom_short  : Double Bottom confirmed, short-term spacing (<~3 months)
  - double_bottom_long   : Double Bottom confirmed, long-term spacing (<~12 months)
  - double_top_short     : Double Top confirmed, short-term spacing (<~3 months)
  - double_top_long      : Double Top confirmed, long-term spacing (<~12 months)
  - bollinger_breakout_up   : %b crosses above 1.0 (upper band breach)
  - bollinger_breakout_down : %b crosses below 0.0 (lower band breach)

Design notes
------------
Double Bottoms/Tops reuse engine.cycles._pivots (confirmed pivot detection, PIT-clean:
last k bars cannot confirm). A double bottom fires on the bar the SECOND trough is
confirmed — i.e. the bar at index `second_trough + k` (the rightmost bar of the
confirmation window), which is the earliest bar at which the pattern is knowable.
Short-term: second trough confirmed within ~65 trading days (~3 months) of the first.
Long-term: second trough confirmed within ~252 trading days (~12 months) of the first.
Fires are mutually exclusive per pair: long fires only when the pattern does NOT also
qualify as short-term.

Neckline context: the neckline is the highest close between the two troughs (for double
bottom) or the lowest close between the two peaks (for double top). An optional
neckline_ratio filter ensures the two lows are within a tolerance band (default 3%),
matching the classic definition of a "comparable" bottom/top.

Bollinger: reuses engine.strategy_signals.bollinger_pctb (%b). Crossover/under via
engine.canon.crossover / crossunder. Signal fires on the bar where %b crosses the
threshold — PIT-clean by construction.

COMMON CONTRACT: all signals return pd.Series[float] in {0.0, 1.0} on df.index.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.canon import crossover, crossunder
from engine.cycles import _pivots
from engine.strategy_signals import bollinger_pctb

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-registered parameters (do not tune)
# ---------------------------------------------------------------------------

# Pivot half-window: number of bars each side required for a confirmed pivot.
# k=5 (5 bars each side) is the default used in cycles.rsi_divergence.
PIVOT_K: int = 5

# Price tolerance for "comparable" double bottoms/tops: the two extremes must
# be within this fraction of each other.
COMPARABLE_TOL: float = 0.03   # 3%

# Short-term maximum spacing between the two confirmed pivots (in bars).
# ~65 trading days ≈ 3 calendar months.
SHORT_MAX_BARS: int = 65

# Long-term maximum spacing between the two confirmed pivots (in bars).
# ~252 trading days ≈ 12 calendar months.
LONG_MAX_BARS: int = 252

# Minimum spacing between the two pivots (to avoid trivially close re-fires).
MIN_SPACING_BARS: int = 10

# Bollinger %b parameters (default: 20-period, 2-sigma).
BB_N: int = 20
BB_K: float = 2.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _double_bottom_series(
    df: pd.DataFrame,
    k: int = PIVOT_K,
    comparable_tol: float = COMPARABLE_TOL,
    min_spacing: int = MIN_SPACING_BARS,
    max_spacing: int = SHORT_MAX_BARS,
) -> pd.Series:
    """Core double-bottom detector for a given max_spacing window.

    Returns a float Series in {0.0, 1.0}. A 1.0 fires on the confirmation bar
    of the second trough (bar index = second_trough_pivot_index + k).

    PIT contract: _pivots(arr, k, 'low') never uses bar i unless bars i-k..i+k
    are all available. The confirmation bar is index `i + k` — the earliest bar
    at which the second trough is confirmed.
    """
    close = df["close"]
    arr = close.to_numpy()
    n = len(arr)

    low_pivots = _pivots(arr, k, "low")

    fires = pd.Series(0.0, index=close.index)

    # Scan all (p1, p2) pairs (not just adjacent) within the spacing window.
    # Adjacent-only scanning breaks when intermediate flat bars are detected as
    # spurious pivots — scanning all pairs within the window is still O(n^2) in
    # the worst case but practically O(n * window / k) given the pivot density.
    for j in range(len(low_pivots)):
        p2 = low_pivots[j]        # index of second (later) trough

        # Look back through all earlier pivots within the spacing window
        for i in range(j - 1, -1, -1):
            p1 = low_pivots[i]   # index of first (earlier) trough

            spacing = p2 - p1
            if spacing > max_spacing:
                break  # earlier pivots are even further away
            if spacing < min_spacing:
                continue

            # Comparable lows: |low2 - low1| / low1 <= tol
            low1, low2 = arr[p1], arr[p2]
            if low1 <= 0:
                continue
            if abs(low2 - low1) / low1 > comparable_tol:
                continue

            # Neckline context: there must be a local peak between the two troughs
            # (i.e. price rallied between them). The neckline is the max close
            # between p1 and p2.
            mid_max = arr[p1:p2 + 1].max()
            if mid_max <= max(low1, low2):
                # no meaningful peak between the lows — not a double bottom
                continue

            # Confirmation bar: bar index = p2 + k (the last bar of the right-side
            # confirmation window). This is the PIT-clean fire bar.
            confirm_bar = p2 + k
            if confirm_bar >= n:
                continue

            fires.iloc[confirm_bar] = 1.0
            # Once we fire for this p2, don't search further back (one fire per p2)
            break

    return fires


def _double_top_series(
    df: pd.DataFrame,
    k: int = PIVOT_K,
    comparable_tol: float = COMPARABLE_TOL,
    min_spacing: int = MIN_SPACING_BARS,
    max_spacing: int = SHORT_MAX_BARS,
) -> pd.Series:
    """Core double-top detector for a given max_spacing window.

    Mirrors _double_bottom_series but operates on high pivots.
    Returns a float Series in {0.0, 1.0}.
    """
    close = df["close"]
    arr = close.to_numpy()
    n = len(arr)

    high_pivots = _pivots(arr, k, "high")

    fires = pd.Series(0.0, index=close.index)

    # Scan all (p1, p2) pairs within the spacing window (see _double_bottom_series).
    for j in range(len(high_pivots)):
        p2 = high_pivots[j]

        for i in range(j - 1, -1, -1):
            p1 = high_pivots[i]

            spacing = p2 - p1
            if spacing > max_spacing:
                break
            if spacing < min_spacing:
                continue

            high1, high2 = arr[p1], arr[p2]
            if high1 <= 0:
                continue
            if abs(high2 - high1) / high1 > comparable_tol:
                continue

            # Neckline: there must be a local trough between the two peaks.
            mid_min = arr[p1:p2 + 1].min()
            if mid_min >= min(high1, high2):
                continue

            confirm_bar = p2 + k
            if confirm_bar >= n:
                continue

            fires.iloc[confirm_bar] = 1.0
            break  # one fire per p2

    return fires


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def double_bottom_short(
    df: pd.DataFrame,
    k: int = PIVOT_K,
    comparable_tol: float = COMPARABLE_TOL,
    min_spacing: int = MIN_SPACING_BARS,
    max_spacing: int = SHORT_MAX_BARS,
) -> pd.Series:
    """Double Bottom (short-term): two comparable lows within ~65 bars (~3 months).

    Fires on the confirmation bar (second trough + k bars). Returns {0.0, 1.0}.
    """
    s = _double_bottom_series(
        df, k=k, comparable_tol=comparable_tol,
        min_spacing=min_spacing, max_spacing=max_spacing,
    )
    s.name = "double_bottom_short"
    return s


def double_bottom_long(
    df: pd.DataFrame,
    k: int = PIVOT_K,
    comparable_tol: float = COMPARABLE_TOL,
    min_spacing: int = MIN_SPACING_BARS,
    short_max: int = SHORT_MAX_BARS,
    long_max: int = LONG_MAX_BARS,
) -> pd.Series:
    """Double Bottom (long-term): two comparable lows separated by 65–252 bars.

    Fires only when the pattern does NOT qualify as short-term (spacing > short_max).
    Returns {0.0, 1.0}.
    """
    long_fires = _double_bottom_series(
        df, k=k, comparable_tol=comparable_tol,
        min_spacing=short_max + 1, max_spacing=long_max,
    )
    long_fires.name = "double_bottom_long"
    return long_fires


def double_top_short(
    df: pd.DataFrame,
    k: int = PIVOT_K,
    comparable_tol: float = COMPARABLE_TOL,
    min_spacing: int = MIN_SPACING_BARS,
    max_spacing: int = SHORT_MAX_BARS,
) -> pd.Series:
    """Double Top (short-term): two comparable highs within ~65 bars (~3 months).

    Fires on the confirmation bar (second peak + k bars). Returns {0.0, 1.0}.
    """
    s = _double_top_series(
        df, k=k, comparable_tol=comparable_tol,
        min_spacing=min_spacing, max_spacing=max_spacing,
    )
    s.name = "double_top_short"
    return s


def double_top_long(
    df: pd.DataFrame,
    k: int = PIVOT_K,
    comparable_tol: float = COMPARABLE_TOL,
    min_spacing: int = MIN_SPACING_BARS,
    short_max: int = SHORT_MAX_BARS,
    long_max: int = LONG_MAX_BARS,
) -> pd.Series:
    """Double Top (long-term): two comparable highs separated by 65–252 bars.

    Fires only when the pattern does NOT qualify as short-term. Returns {0.0, 1.0}.
    """
    long_fires = _double_top_series(
        df, k=k, comparable_tol=comparable_tol,
        min_spacing=short_max + 1, max_spacing=long_max,
    )
    long_fires.name = "double_top_long"
    return long_fires


def bollinger_breakout_up(
    df: pd.DataFrame,
    n: int = BB_N,
    k: float = BB_K,
) -> pd.Series:
    """%b crosses above 1.0 (close breaches upper Bollinger Band).

    Uses engine.strategy_signals.bollinger_pctb. Fires on the cross bar.
    Returns {0.0, 1.0}.
    """
    close = df["close"]
    pctb = bollinger_pctb(close, n=n, k=k)
    threshold = pd.Series(1.0, index=close.index)
    fired = crossover(pctb, threshold).astype(float)
    fired.name = "bollinger_breakout_up"
    return fired


def bollinger_breakout_down(
    df: pd.DataFrame,
    n: int = BB_N,
    k: float = BB_K,
) -> pd.Series:
    """%b crosses below 0.0 (close breaches lower Bollinger Band).

    Uses engine.strategy_signals.bollinger_pctb. Fires on the cross bar.
    Returns {0.0, 1.0}.
    """
    close = df["close"]
    pctb = bollinger_pctb(close, n=n, k=k)
    threshold = pd.Series(0.0, index=close.index)
    fired = crossunder(pctb, threshold).astype(float)
    fired.name = "bollinger_breakout_down"
    return fired


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict] = {
    "double_bottom_short": {
        "fn": double_bottom_short,
        "kind": "event",
        "family": "formations",
        "direction": +1,
        "default_params": {
            "k": PIVOT_K,
            "comparable_tol": COMPARABLE_TOL,
            "min_spacing": MIN_SPACING_BARS,
            "max_spacing": SHORT_MAX_BARS,
        },
        "display": {
            "en": "Double Bottom (Short-term)",
            "zh": "双底形态（短期）",
        },
        "glyph": "double_bottom",
    },
    "double_bottom_long": {
        "fn": double_bottom_long,
        "kind": "event",
        "family": "formations",
        "direction": +1,
        "default_params": {
            "k": PIVOT_K,
            "comparable_tol": COMPARABLE_TOL,
            "min_spacing": MIN_SPACING_BARS,
            "short_max": SHORT_MAX_BARS,
            "long_max": LONG_MAX_BARS,
        },
        "display": {
            "en": "Double Bottom (Long-term)",
            "zh": "双底形态（长期）",
        },
        "glyph": "double_bottom",
    },
    "double_top_short": {
        "fn": double_top_short,
        "kind": "event",
        "family": "formations",
        "direction": -1,
        "default_params": {
            "k": PIVOT_K,
            "comparable_tol": COMPARABLE_TOL,
            "min_spacing": MIN_SPACING_BARS,
            "max_spacing": SHORT_MAX_BARS,
        },
        "display": {
            "en": "Double Top (Short-term)",
            "zh": "双顶形态（短期）",
        },
        "glyph": "double_top",
    },
    "double_top_long": {
        "fn": double_top_long,
        "kind": "event",
        "family": "formations",
        "direction": -1,
        "default_params": {
            "k": PIVOT_K,
            "comparable_tol": COMPARABLE_TOL,
            "min_spacing": MIN_SPACING_BARS,
            "short_max": SHORT_MAX_BARS,
            "long_max": LONG_MAX_BARS,
        },
        "display": {
            "en": "Double Top (Long-term)",
            "zh": "双顶形态（长期）",
        },
        "glyph": "double_top",
    },
    "bollinger_breakout_up": {
        "fn": bollinger_breakout_up,
        "kind": "event",
        "family": "formations",
        "direction": +1,
        "default_params": {
            "n": BB_N,
            "k": BB_K,
        },
        "display": {
            "en": "Bollinger Breakout Up",
            "zh": "布林带向上突破",
        },
        "glyph": "band",
    },
    "bollinger_breakout_down": {
        "fn": bollinger_breakout_down,
        "kind": "event",
        "family": "formations",
        "direction": -1,
        "default_params": {
            "n": BB_N,
            "k": BB_K,
        },
        "display": {
            "en": "Bollinger Breakout Down",
            "zh": "布林带向下突破",
        },
        "glyph": "band",
    },
}
