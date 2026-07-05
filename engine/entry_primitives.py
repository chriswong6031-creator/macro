"""Vectorized FULL-HISTORY series primitives for the Entry-Stack Expansion program.

These functions take full OHLCV pd.Series and emit one value per date across
all of history, so a backtest can scan for entry conditions everywhere — not
just today.  They are the series equivalents of the pointwise reads computed
inside engine/stock_technicals.py::snapshot().

LEAK-FREE BY CONSTRUCTION: every output at date t is a function of data at t
and strictly-earlier bars only.  Trailing rolling windows are used throughout;
no centered windows; min_periods is always set so early bars are NaN rather
than silently computed from fewer observations than the window.

The helper functions imported from engine.stock_technicals (bb_bandwidth,
realized_vol, atr, on_balance_volume) and engine.indicators (pct_rank_window,
rolling_slope) are shared with the live snapshot so the series and the
snapshot stay numerically consistent by construction.

DISPLAY/RESEARCH ONLY — this module is pure math; it wires into nothing live.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window, rolling_slope
from engine.stock_technicals import (
    atr,
    bb_bandwidth,
    on_balance_volume,
    realized_vol,
)

# ---------------------------------------------------------------------------
# Volatility-percentile series
# ---------------------------------------------------------------------------

def bbwp_series(
    close: pd.Series,
    n: int = 20,
    k: float = 2.0,
    rank_window: int = 252,
) -> pd.Series:
    """Bollinger Bandwidth Percentile (BBWP) — full-history series, 0-100.

    Percentile rank of the current Bollinger bandwidth within a trailing
    ``rank_window``-bar window.  Mirrors the snapshot ``bbwp`` value computed
    in engine/stock_technicals.py::snapshot() (which takes ``pct_rank_window``
    of ``bb_bandwidth`` and scales by 100).

    Parameters
    ----------
    close:
        Daily close price series (DatetimeIndex).
    n:
        Bollinger-band period (same default as snapshot: 20).
    k:
        Band multiplier (same default as snapshot: 2.0).
    rank_window:
        Trailing window for the percentile rank (same default as snapshot: 252).

    Returns
    -------
    pd.Series of float in [0, 100]; NaN where fewer than ``rank_window // 2``
    observations are available (governed by ``pct_rank_window`` min_periods).
    """
    bbw = bb_bandwidth(close, n=n, k=k)
    return pct_rank_window(bbw, rank_window) * 100.0


def hvp_series(
    close: pd.Series,
    n: int = 20,
    rank_window: int = 252,
) -> pd.Series:
    """Historical Volatility Percentile (HVP) — full-history series, 0-100.

    Percentile rank of the trailing n-bar realized volatility within a
    ``rank_window``-bar window.  Mirrors the snapshot ``hv_pctile`` value in
    engine/stock_technicals.py::snapshot().

    Parameters
    ----------
    close:
        Daily close price series.
    n:
        Realized-vol period (default 20 matching snapshot ``hv20``).
    rank_window:
        Trailing window for the percentile rank (default 252).

    Returns
    -------
    pd.Series of float in [0, 100]; NaN before sufficient history.
    """
    rv = realized_vol(close, n=n)
    return pct_rank_window(rv, rank_window) * 100.0


# ---------------------------------------------------------------------------
# Donchian position series
# ---------------------------------------------------------------------------

def donchian_pos_series(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    n: int = 20,
) -> pd.Series:
    """Donchian-channel position — full-history series, 0..1.

    Vectorized equivalent of the pointwise ``donchian_pos`` in
    engine/stock_technicals.py::snapshot() (lines ~289-294).

    The snapshot reads::

        hh = high.rolling(20, min_periods=20).max()
        ll = low.rolling(20, min_periods=20).min()
        donchian_pos = (close - ll) / (hh - ll)   # guarded against zero range

    This function replicates that exactly over the full history.

    Parameters
    ----------
    close, high, low:
        Aligned daily price series.
    n:
        Donchian channel period (default 20 matching snapshot).

    Returns
    -------
    pd.Series of float in [0, 1]; NaN where fewer than n bars are available
    or where the channel range is zero (high == low throughout the window).
    """
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    rng = (hh - ll).replace(0, np.nan)
    return (close - ll) / rng


# ---------------------------------------------------------------------------
# Relative volume series
# ---------------------------------------------------------------------------

def rel_volume_series(
    volume: pd.Series,
    n: int = 20,
) -> pd.Series:
    """Relative volume — full-history series (ratio, unbounded above 0).

    Volume divided by its trailing n-bar simple moving average.  Mirrors the
    ``rel_volume`` computation in engine/stock_technicals.py::snapshot()::

        vsma = vol.rolling(20, min_periods=10).mean()
        rel_volume = last_vol / last_vsma

    This function emits the ratio for every bar.  Values > 1 mean above-average
    turnover; < 1 means below-average.

    Parameters
    ----------
    volume:
        Daily volume series (should be non-negative).
    n:
        SMA period (default 20).

    Returns
    -------
    pd.Series of float ≥ 0; NaN where fewer than n // 2 observations are
    available or where the SMA is zero.
    """
    vsma = volume.rolling(n, min_periods=n // 2).mean().replace(0, np.nan)
    return volume / vsma


# ---------------------------------------------------------------------------
# OBV slope series
# ---------------------------------------------------------------------------

def obv_slope_series(
    close: pd.Series,
    volume: pd.Series,
    slope_win: int = 20,
) -> pd.Series:
    """OBV (On-Balance Volume) rolling slope — full-history series.

    Applies engine.indicators.rolling_slope over the full OBV series with a
    trailing window of ``slope_win`` bars.  Mirrors the ``obv_slope_up``
    snapshot field (which takes the sign of the last value of this series).

    Parameters
    ----------
    close, volume:
        Aligned daily series.
    slope_win:
        OLS slope window (default 20 matching snapshot).

    Returns
    -------
    pd.Series of float; positive = OBV in a rising trend, negative = falling.
    NaN before ``slope_win`` observations are available.
    """
    obv = on_balance_volume(close, volume)
    return rolling_slope(obv, slope_win)


# ---------------------------------------------------------------------------
# ATR percentile series
# ---------------------------------------------------------------------------

def atr_pct_pctile_series(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 14,
    rank_window: int = 252,
) -> pd.Series:
    """ATR-as-percent-of-price percentile — full-history series, 0-100.

    Computes ATR(n) / close (matching the ``atr_pct`` field in the snapshot)
    then takes the percentile rank within a trailing ``rank_window``-bar window.

    Parameters
    ----------
    high, low, close:
        Aligned daily OHLC series.
    n:
        ATR period (default 14).
    rank_window:
        Trailing window for the percentile rank (default 252).

    Returns
    -------
    pd.Series of float in [0, 100]; NaN before sufficient history.
    """
    a = atr(high, low, close, n=n)
    atr_pct = a / close.replace(0, np.nan)
    return pct_rank_window(atr_pct, rank_window) * 100.0


# ---------------------------------------------------------------------------
# Distance from 52-week high
# ---------------------------------------------------------------------------

def dist_52w_high_series(
    close: pd.Series,
    window: int = 252,
) -> pd.Series:
    """Distance from trailing rolling high — full-history series, values ≤ 0.

    close / rolling_max(window) - 1.

    At a new n-bar high the value is 0.0; below the high it is negative (e.g.
    -0.20 means 20 % below the rolling high).

    Parameters
    ----------
    close:
        Daily close series.
    window:
        Look-back window for the rolling maximum (default 252 ≈ 1 year).

    Returns
    -------
    pd.Series of float in [-1, 0]; NaN before ``window`` observations.
    """
    rolling_max = close.rolling(window, min_periods=window).max()
    return close / rolling_max.replace(0, np.nan) - 1.0


# ---------------------------------------------------------------------------
# Time underwater series
# ---------------------------------------------------------------------------

def time_underwater_series(
    close: pd.Series,
    window: int = 252,
) -> pd.Series:
    """Bars since the trailing ``window``-bar rolling maximum was set — integer ≥ 0.

    At the bar that sets a new rolling high the value is 0; one bar later it
    becomes 1, and so on until a new high is set.  A persistently large value
    means the name has been under its recent peak for a long time.

    Implementation: for each bar t the rolling max is computed over
    [t-window+1, t]; the value is t's positional index minus the positional
    index of the argmax within that window.

    Parameters
    ----------
    close:
        Daily close series.
    window:
        Look-back window (default 252).

    Returns
    -------
    pd.Series of int ≥ 0; NaN before ``window`` observations.
    """
    def _bars_since_max(arr: np.ndarray) -> float:
        if np.isnan(arr).any():
            return np.nan
        return float(len(arr) - 1 - int(np.argmax(arr)))

    return close.rolling(window, min_periods=window).apply(_bars_since_max, raw=True)
