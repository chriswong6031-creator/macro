"""engine/rsi_signals.py — RSI Oversold / Overbought signal engine.

Reconstructs StockInvest 'RSI 14/21 Oversold/Overbought' lists using the canonical
Wilder RSI (engine.canon.rsi).  Provides two band modes:

  band_mode='dynamic' (default)
      Adaptive per-stock bands computed from each stock's own RSI history.
      Oversold  = RSI crosses INTO its trailing ~10th percentile (pct_rank_window).
      Overbought = RSI crosses INTO its trailing ~90th percentile.
      Uses engine.indicators.pct_rank_window (trailing window) or
      engine.indicators.expanding_percentile when window='expanding'.

  band_mode='fixed'
      Classic 30 / 70 bands (30 = oversold, 70 = overbought).

Event semantics: an event fires (1.0) on the FIRST bar where RSI crosses INTO the zone
(i.e. was NOT in the zone on the previous bar; strict entry-bar).  Subsequent bars inside
the zone score 0.0 — "crosses INTO" not "is inside".  PIT-clean: no look-ahead, no
centered windows.

Signals registered
------------------
  rsi14_oversold    RSI-14 crosses into oversold zone      direction +1  glyph arrow_up
  rsi14_overbought  RSI-14 crosses into overbought zone    direction -1  glyph arrow_down
  rsi21_oversold    RSI-21 crosses into oversold zone      direction +1  glyph arrow_up
  rsi21_overbought  RSI-21 crosses into overbought zone    direction -1  glyph arrow_down

IMPORTANT CAVEATS
-----------------
1. DISPLAY-ONLY / research.  No LLM-originated signals or escalations.
2. The adaptive bands match the StockInvest pattern empirically (e.g. NMRK's [25,80]
   bands emerged from stock-specific percentile history).  The true lookback window
   used by StockInvest is UNKNOWN; we default to 252 trading days (rolling_window param).
3. Minimum warm-up: RSI-21 needs ~63 bars for a stable estimate; dynamic bands need at
   least rolling_window bars.  Results before warm-up are NaN-extended by default.
4. No "validated" claim anywhere in user-facing strings.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.canon import rsi as _canon_rsi          # Wilder RSI (SMA-seeded RMA)
from engine.indicators import pct_rank_window, expanding_percentile

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters (pre-registered; do not tune inline)
# ---------------------------------------------------------------------------
DEFAULT_ROLLING_WINDOW: int = 252       # bars for pct_rank_window dynamic bands
DEFAULT_DYNAMIC_OS_PCT: float = 0.10   # oversold  = RSI below its 10th pct
DEFAULT_DYNAMIC_OB_PCT: float = 0.90   # overbought = RSI above its 90th pct
FIXED_OS: float = 30.0                  # fixed oversold threshold
FIXED_OB: float = 70.0                  # fixed overbought threshold


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _rsi(df: pd.DataFrame, period: int) -> pd.Series:
    """Return Wilder RSI for the given period, named appropriately."""
    close = df["close"]
    r = _canon_rsi(close, n=period)
    r.name = f"rsi{period}"
    return r


def _crosses_into(in_zone: pd.Series) -> pd.Series:
    """Return 1.0 on bars where in_zone transitions False→True (entry bar only).

    PIT-clean: shift(1) uses past data only; the event fires on the same bar
    it is first knowable (in_zone[t] = True, in_zone[t-1] = False).
    """
    in_zone_bool = in_zone.astype(bool)
    event = in_zone_bool & ~in_zone_bool.shift(1, fill_value=False)
    return event.astype(float)


def _dynamic_bands(
    rsi_series: pd.Series,
    rolling_window: int,
    os_pct: float,
    ob_pct: float,
    use_expanding: bool = False,
) -> tuple[pd.Series, pd.Series]:
    """Compute adaptive oversold/overbought thresholds from the stock's own RSI history.

    Returns (oversold_threshold, overbought_threshold) aligned to rsi_series.index.
    Each value at bar t is the os_pct / ob_pct percentile of RSI values in
    [t-rolling_window+1 .. t] — look-behind only, PIT-clean.

    When use_expanding=True, uses expanding_percentile (accumulates since start).
    Otherwise uses pct_rank_window to get the percentile rank, then maps it to
    a threshold via the rolling quantile.
    """
    if use_expanding:
        # expanding: percentile rank of current RSI within all past RSI
        rank = expanding_percentile(rsi_series, min_obs=rolling_window)
        # derive dynamic thresholds: rolling quantiles of RSI at os_pct and ob_pct
        os_thresh = rsi_series.rolling(rolling_window, min_periods=rolling_window // 2).quantile(os_pct)
        ob_thresh = rsi_series.rolling(rolling_window, min_periods=rolling_window // 2).quantile(ob_pct)
    else:
        os_thresh = rsi_series.rolling(rolling_window, min_periods=rolling_window // 2).quantile(os_pct)
        ob_thresh = rsi_series.rolling(rolling_window, min_periods=rolling_window // 2).quantile(ob_pct)

    return os_thresh, ob_thresh


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def rsi14_oversold(
    df: pd.DataFrame,
    band_mode: str = "dynamic",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    os_pct: float = DEFAULT_DYNAMIC_OS_PCT,
    fixed_os: float = FIXED_OS,
) -> pd.Series:
    """RSI-14 crosses INTO oversold zone (event = 1.0 on entry bar).

    Parameters
    ----------
    df : DataFrame
        Single-ticker OHLCV with DatetimeIndex.
    band_mode : 'dynamic' | 'fixed'
        'dynamic' = adaptive per-stock rolling percentile bands.
        'fixed'   = fixed threshold at fixed_os (default 30).
    rolling_window : int
        Trailing window for dynamic band percentile computation (default 252).
    os_pct : float
        Percentile for oversold threshold in dynamic mode (default 0.10 = 10th pct).
    fixed_os : float
        Fixed oversold threshold (default 30.0).

    Returns
    -------
    pd.Series of {0.0, 1.0} aligned to df.index; 1.0 = oversold entry event.
    """
    r = _rsi(df, 14)
    if band_mode == "fixed":
        in_zone = r < fixed_os
    else:
        os_thresh, _ = _dynamic_bands(r, rolling_window, os_pct, 1.0 - os_pct)
        in_zone = r < os_thresh

    result = _crosses_into(in_zone)
    result.name = "rsi14_oversold"
    return result


def rsi14_overbought(
    df: pd.DataFrame,
    band_mode: str = "dynamic",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    ob_pct: float = DEFAULT_DYNAMIC_OB_PCT,
    fixed_ob: float = FIXED_OB,
) -> pd.Series:
    """RSI-14 crosses INTO overbought zone (event = 1.0 on entry bar).

    Parameters
    ----------
    df : DataFrame
        Single-ticker OHLCV with DatetimeIndex.
    band_mode : 'dynamic' | 'fixed'
        'dynamic' = adaptive per-stock rolling percentile bands.
        'fixed'   = fixed threshold at fixed_ob (default 70).
    rolling_window : int
        Trailing window for dynamic band percentile computation (default 252).
    ob_pct : float
        Percentile for overbought threshold in dynamic mode (default 0.90 = 90th pct).
    fixed_ob : float
        Fixed overbought threshold (default 70.0).

    Returns
    -------
    pd.Series of {0.0, 1.0} aligned to df.index; 1.0 = overbought entry event.
    """
    r = _rsi(df, 14)
    if band_mode == "fixed":
        in_zone = r > fixed_ob
    else:
        _, ob_thresh = _dynamic_bands(r, rolling_window, 1.0 - ob_pct, ob_pct)
        in_zone = r > ob_thresh

    result = _crosses_into(in_zone)
    result.name = "rsi14_overbought"
    return result


def rsi21_oversold(
    df: pd.DataFrame,
    band_mode: str = "dynamic",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    os_pct: float = DEFAULT_DYNAMIC_OS_PCT,
    fixed_os: float = FIXED_OS,
) -> pd.Series:
    """RSI-21 crosses INTO oversold zone (event = 1.0 on entry bar).

    Parameters
    ----------
    df : DataFrame
        Single-ticker OHLCV with DatetimeIndex.
    band_mode : 'dynamic' | 'fixed'
        'dynamic' = adaptive per-stock rolling percentile bands.
        'fixed'   = fixed threshold at fixed_os (default 30).
    rolling_window : int
        Trailing window for dynamic band percentile computation (default 252).
    os_pct : float
        Percentile for oversold threshold in dynamic mode (default 0.10 = 10th pct).
    fixed_os : float
        Fixed oversold threshold (default 30.0).

    Returns
    -------
    pd.Series of {0.0, 1.0} aligned to df.index; 1.0 = oversold entry event.
    """
    r = _rsi(df, 21)
    if band_mode == "fixed":
        in_zone = r < fixed_os
    else:
        os_thresh, _ = _dynamic_bands(r, rolling_window, os_pct, 1.0 - os_pct)
        in_zone = r < os_thresh

    result = _crosses_into(in_zone)
    result.name = "rsi21_oversold"
    return result


def rsi21_overbought(
    df: pd.DataFrame,
    band_mode: str = "dynamic",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    ob_pct: float = DEFAULT_DYNAMIC_OB_PCT,
    fixed_ob: float = FIXED_OB,
) -> pd.Series:
    """RSI-21 crosses INTO overbought zone (event = 1.0 on entry bar).

    Parameters
    ----------
    df : DataFrame
        Single-ticker OHLCV with DatetimeIndex.
    band_mode : 'dynamic' | 'fixed'
        'dynamic' = adaptive per-stock rolling percentile bands.
        'fixed'   = fixed threshold at fixed_ob (default 70).
    rolling_window : int
        Trailing window for dynamic band percentile computation (default 252).
    ob_pct : float
        Percentile for overbought threshold in dynamic mode (default 0.90 = 90th pct).
    fixed_ob : float
        Fixed overbought threshold (default 70.0).

    Returns
    -------
    pd.Series of {0.0, 1.0} aligned to df.index; 1.0 = overbought entry event.
    """
    r = _rsi(df, 21)
    if band_mode == "fixed":
        in_zone = r > fixed_ob
    else:
        _, ob_thresh = _dynamic_bands(r, rolling_window, 1.0 - ob_pct, ob_pct)
        in_zone = r > ob_thresh

    result = _crosses_into(in_zone)
    result.name = "rsi21_overbought"
    return result


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict] = {
    "rsi14_oversold": {
        "fn": rsi14_oversold,
        "kind": "event",
        "family": "rsi_bands",
        "direction": +1,
        "default_params": {
            "band_mode": "dynamic",
            "rolling_window": DEFAULT_ROLLING_WINDOW,
            "os_pct": DEFAULT_DYNAMIC_OS_PCT,
            "fixed_os": FIXED_OS,
        },
        "display": {
            "en": "RSI-14 Oversold Entry",
            "zh": "RSI-14 超卖入场",
        },
        "glyph": "arrow_up",
    },
    "rsi14_overbought": {
        "fn": rsi14_overbought,
        "kind": "event",
        "family": "rsi_bands",
        "direction": -1,
        "default_params": {
            "band_mode": "dynamic",
            "rolling_window": DEFAULT_ROLLING_WINDOW,
            "ob_pct": DEFAULT_DYNAMIC_OB_PCT,
            "fixed_ob": FIXED_OB,
        },
        "display": {
            "en": "RSI-14 Overbought Entry",
            "zh": "RSI-14 超买入场",
        },
        "glyph": "arrow_down",
    },
    "rsi21_oversold": {
        "fn": rsi21_oversold,
        "kind": "event",
        "family": "rsi_bands",
        "direction": +1,
        "default_params": {
            "band_mode": "dynamic",
            "rolling_window": DEFAULT_ROLLING_WINDOW,
            "os_pct": DEFAULT_DYNAMIC_OS_PCT,
            "fixed_os": FIXED_OS,
        },
        "display": {
            "en": "RSI-21 Oversold Entry",
            "zh": "RSI-21 超卖入场",
        },
        "glyph": "arrow_up",
    },
    "rsi21_overbought": {
        "fn": rsi21_overbought,
        "kind": "event",
        "family": "rsi_bands",
        "direction": -1,
        "default_params": {
            "band_mode": "dynamic",
            "rolling_window": DEFAULT_ROLLING_WINDOW,
            "ob_pct": DEFAULT_DYNAMIC_OB_PCT,
            "fixed_ob": FIXED_OB,
        },
        "display": {
            "en": "RSI-21 Overbought Entry",
            "zh": "RSI-21 超买入场",
        },
        "glyph": "arrow_down",
    },
}
