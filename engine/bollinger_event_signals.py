"""engine/bollinger_event_signals.py — Bollinger Band event/state chart-grammar signals.

Display-tier descriptive chart-grammar family. No authority, no buy/sell/stop
commands, no composite scores. Routed per research/DANNYTRADES_INDICATOR_DOCKET_
ADJUDICATION_2026-07-10_BY_FABLE.md ruling DT-R18.

These signals use price-vs-band relationships (rejection from the upper band,
reclaim of the lower band, and band-walk states). They do NOT duplicate the
bollinger_breakout_up / bollinger_breakout_down ids already registered in
engine.formations (which use %b crossover logic).

Parameters: mid = SMA(close, 20), sd = rolling_std(close, 20, ddof=1),
upper = mid + 2*sd, lower = mid - 2*sd.

Signals
-------
  bb_upper_rejection   event  -1  high > upper AND close < upper (wick rejection)
  bb_lower_reclaim     event  +1  low < lower AND close > lower (reclaim after wick)
  bb_band_walk_up      state  +1  close > upper on >= 3 of last 5 bars
  bb_band_walk_down    state  -1  close < lower on >= 3 of last 5 bars
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters (pre-registered per DT-R18)
# ---------------------------------------------------------------------------
DEFAULT_BB_N: int = 20
DEFAULT_BB_K: float = 2.0
DEFAULT_WALK_WINDOW: int = 5
DEFAULT_WALK_MIN_BARS: int = 3


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _bb_bands(
    df: pd.DataFrame,
    n: int = DEFAULT_BB_N,
    k: float = DEFAULT_BB_K,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, mid, lower) Bollinger Bands.

    mid = SMA(close, n); sd = rolling std (ddof=1); upper = mid + k*sd; lower = mid - k*sd.
    PIT-clean: rolling trailing windows only.
    """
    close = df["close"]
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=1)
    upper = mid + k * sd
    lower = mid - k * sd
    return upper, mid, lower


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def bb_upper_rejection(
    df: pd.DataFrame,
    n: int = DEFAULT_BB_N,
    k: float = DEFAULT_BB_K,
) -> pd.Series:
    """Event: high exceeds the upper band but close finishes below it (wick rejection).

    Returns {0.0, 1.0} — fires on bars where the high reached above the upper band
    but the close pulled back below it. PIT-clean.
    """
    high = df["high"]
    upper, _, _ = _bb_bands(df, n=n, k=k)
    fired = ((high > upper) & (df["close"] < upper)).astype(float)
    fired = fired.where(upper.notna(), 0.0)
    fired.name = "bb_upper_rejection"
    return fired


def bb_lower_reclaim(
    df: pd.DataFrame,
    n: int = DEFAULT_BB_N,
    k: float = DEFAULT_BB_K,
) -> pd.Series:
    """Event: low dips below the lower band but close finishes above it (lower reclaim).

    Returns {0.0, 1.0} — fires on bars where the low touched below the lower band
    but the close recovered above it. PIT-clean.
    """
    low = df["low"]
    _, _, lower = _bb_bands(df, n=n, k=k)
    fired = ((low < lower) & (df["close"] > lower)).astype(float)
    fired = fired.where(lower.notna(), 0.0)
    fired.name = "bb_lower_reclaim"
    return fired


def bb_band_walk_up(
    df: pd.DataFrame,
    n: int = DEFAULT_BB_N,
    k: float = DEFAULT_BB_K,
    walk_window: int = DEFAULT_WALK_WINDOW,
    walk_min_bars: int = DEFAULT_WALK_MIN_BARS,
) -> pd.Series:
    """State: close is above the upper band on >= 3 of the last 5 bars (band walk up).

    Returns {0.0, 1.0}. PIT-clean: rolling trailing window.
    """
    close = df["close"]
    upper, _, _ = _bb_bands(df, n=n, k=k)
    above = (close > upper).astype(float)
    count = above.rolling(walk_window, min_periods=walk_window).sum()
    result = (count >= walk_min_bars).astype(float)
    result = result.where(upper.notna(), 0.0)
    result.name = "bb_band_walk_up"
    return result


def bb_band_walk_down(
    df: pd.DataFrame,
    n: int = DEFAULT_BB_N,
    k: float = DEFAULT_BB_K,
    walk_window: int = DEFAULT_WALK_WINDOW,
    walk_min_bars: int = DEFAULT_WALK_MIN_BARS,
) -> pd.Series:
    """State: close is below the lower band on >= 3 of the last 5 bars (band walk down).

    Returns {0.0, 1.0}. PIT-clean: rolling trailing window.
    """
    close = df["close"]
    _, _, lower = _bb_bands(df, n=n, k=k)
    below = (close < lower).astype(float)
    count = below.rolling(walk_window, min_periods=walk_window).sum()
    result = (count >= walk_min_bars).astype(float)
    result = result.where(lower.notna(), 0.0)
    result.name = "bb_band_walk_down"
    return result


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    "bb_upper_rejection": {
        "fn": bb_upper_rejection,
        "kind": "event",
        "family": "bollinger_events",
        "direction": -1,
        "default_params": {
            "n": DEFAULT_BB_N,
            "k": DEFAULT_BB_K,
        },
        "display": {
            "en": "Bollinger Upper Band Rejection (Wick above, Close below)",
            "zh": "布林上轨拒绝（上影线穿越，收盘回落）",
        },
        "glyph": "arrow_down",
    },
    "bb_lower_reclaim": {
        "fn": bb_lower_reclaim,
        "kind": "event",
        "family": "bollinger_events",
        "direction": +1,
        "default_params": {
            "n": DEFAULT_BB_N,
            "k": DEFAULT_BB_K,
        },
        "display": {
            "en": "Bollinger Lower Band Reclaim (Wick below, Close above)",
            "zh": "布林下轨收复（下影线触穿，收盘回升）",
        },
        "glyph": "arrow_up",
    },
    "bb_band_walk_up": {
        "fn": bb_band_walk_up,
        "kind": "state",
        "family": "bollinger_events",
        "direction": +1,
        "default_params": {
            "n": DEFAULT_BB_N,
            "k": DEFAULT_BB_K,
            "walk_window": DEFAULT_WALK_WINDOW,
            "walk_min_bars": DEFAULT_WALK_MIN_BARS,
        },
        "display": {
            "en": "Bollinger Band Walk Up (Close above upper band ≥ 3 of last 5 bars)",
            "zh": "布林带向上游走（近5根K线中至少3根收盘高于上轨）",
        },
        "glyph": "band",
    },
    "bb_band_walk_down": {
        "fn": bb_band_walk_down,
        "kind": "state",
        "family": "bollinger_events",
        "direction": -1,
        "default_params": {
            "n": DEFAULT_BB_N,
            "k": DEFAULT_BB_K,
            "walk_window": DEFAULT_WALK_WINDOW,
            "walk_min_bars": DEFAULT_WALK_MIN_BARS,
        },
        "display": {
            "en": "Bollinger Band Walk Down (Close below lower band ≥ 3 of last 5 bars)",
            "zh": "布林带向下游走（近5根K线中至少3根收盘低于下轨）",
        },
        "glyph": "band",
    },
}
