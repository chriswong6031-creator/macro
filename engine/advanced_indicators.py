"""Vectorized FULL-HISTORY boolean series for the advanced cycle-technical
primitives that engine/cycles.py only computes POINTWISE (in `_tf_state`, for the
live as-of bar). These re-use the EXACT same MACD / StochRSI / RSI math
(engine.technicals + engine.cycles) but emit one boolean per date across all of
history, so a backtest can scan for the conditions everywhere — not just today.

LEAK-FREE BY CONSTRUCTION: every condition is a function of the value at t and
strictly-earlier bars (``.shift(1..3)``), and multi-timeframe series resample
then ffill back to daily (a daily date d carries the most-recent completed
higher-timeframe bar at or before d) — so nothing reads the future.

The pointwise definitions these mirror live in engine/cycles.py::_tf_state:
  macd_curl_up  : ``h<0 and h>h[-2]<=h[-3]``  (Aspray histogram trough, pre-cross)
  macd_curl_dn  : ``h>0 and h<h[-2]>=h[-3]``  (histogram peak rollover)
  macd_cross_dn : ``h<0 and any(h[-4:-1]>=0)`` (signal-line bearish cross)
  stoch_cross_up: ``s>=20 and any(s[-4:-1]<20)`` (StochRSI out of oversold)
A regression sanity-check (the last value of each series equals _tf_state's flag)
lives in tests + scripts/defensive_rotation_phase0.py.

DISPLAY/RESEARCH ONLY — this module is pure math; it wires into nothing live.
"""
from __future__ import annotations

import pandas as pd

from engine.cycles import macd_parts, stoch_rsi
from engine.technicals import rsi

# 3 business days — matches engine.cycles CYCLE_PRESETS["equity"]["tf3"].
TF3 = "3B"


def _resample(close: pd.Series, tf: str | None) -> pd.Series:
    c = close.dropna()
    if tf in (None, "D", "daily", "1D"):
        return c
    return c.resample(tf).last().dropna()


def _to_daily(out: pd.Series, daily_index: pd.Index, tf: str | None) -> pd.Series:
    """Map a higher-timeframe boolean back onto the daily index (causal ffill)."""
    if tf in (None, "D", "daily", "1D"):
        return out.reindex(daily_index).fillna(False).astype(bool)
    return out.reindex(daily_index, method="ffill").fillna(False).astype(bool)


def _hist(close: pd.Series, tf: str | None) -> tuple[pd.Series, pd.Series]:
    """(MACD histogram on the chosen timeframe, daily index for re-mapping)."""
    c = _resample(close, tf)
    return macd_parts(c)["hist"], close.dropna().index


def macd_hist_trough_series(close: pd.Series, tf: str | None = "D") -> pd.Series:
    """MACD-histogram trough curling UP while still below zero (the earliest
    pre-cross bottoming flag). Vectorization of _tf_state['macd_curl_up']."""
    h, didx = _hist(close, tf)
    out = (h < 0) & (h > h.shift(1)) & (h.shift(1) <= h.shift(2))
    return _to_daily(out.fillna(False), didx, tf)


def macd_hist_peak_series(close: pd.Series, tf: str | None = "D") -> pd.Series:
    """MACD-histogram peak rolling OVER while still above zero (mirror of the
    trough — the earliest pre-cross topping flag). _tf_state['macd_curl_dn']."""
    h, didx = _hist(close, tf)
    out = (h > 0) & (h < h.shift(1)) & (h.shift(1) >= h.shift(2))
    return _to_daily(out.fillna(False), didx, tf)


def macd_cross_dn_series(close: pd.Series, tf: str | None = "D") -> pd.Series:
    """MACD signal-line BEARISH cross: histogram below zero with a non-negative
    bar in the prior 3. Vectorization of _tf_state['macd_cross_dn']."""
    h, didx = _hist(close, tf)
    out = (h < 0) & ((h.shift(1) >= 0) | (h.shift(2) >= 0) | (h.shift(3) >= 0))
    return _to_daily(out.fillna(False), didx, tf)


def macd_cross_up_series(close: pd.Series, tf: str | None = "D") -> pd.Series:
    """MACD signal-line BULLISH cross (mirror): histogram above zero with a
    non-positive bar in the prior 3."""
    h, didx = _hist(close, tf)
    out = (h > 0) & ((h.shift(1) <= 0) | (h.shift(2) <= 0) | (h.shift(3) <= 0))
    return _to_daily(out.fillna(False), didx, tf)


def stoch_rsi_cross_up_series(close: pd.Series, tf: str | None = "D",
                              line: float = 20.0) -> pd.Series:
    """StochRSI popping back above the oversold line (default 20) — current >=
    line with any of the prior 3 bars below it. _tf_state['stoch_cross_up']."""
    c = _resample(close, tf)
    s = stoch_rsi(c)
    out = (s >= line) & ((s.shift(1) < line) | (s.shift(2) < line) | (s.shift(3) < line))
    return _to_daily(out.fillna(False), close.dropna().index, tf)


def rsi_turning_up_series(close: pd.Series, tf: str | None = "D", n: int = 14,
                          below: float = 50.0) -> pd.Series:
    """RSI turning UP from the lower half: RSI rising vs the prior bar AND still
    below `below` (a bottoming turn, not an overbought thrust)."""
    c = _resample(close, tf)
    r = rsi(c, n)
    out = (r > r.shift(1)) & (r < below)
    return _to_daily(out.fillna(False), close.dropna().index, tf)


def rolling_any(s: pd.Series, window: int) -> pd.Series:
    """True if the boolean `s` fired at any point in the trailing `window` bars
    (inclusive of t). Causal — used to express 'condition occurred within the
    last N days' for co-occurrence triggers."""
    return (s.astype(float).rolling(window, min_periods=1).max() > 0).astype(bool)
