"""engine/momentum_events.py — MACD / RSI / Stochastic-RSI cross event signals.

Registers MACD, RSI, and Stochastic-RSI *cross* events into the tech_catalog so the
confluence miner (engine.tech_confluence) can build daily AND weekly legs from them —
and mine confluences such as "weekly MACD cross + weekly Stochastic-RSI cross".

TIMEFRAME CONTRACT (important — read before editing)
----------------------------------------------------
The miner calls each signal fn with the OHLCV frame for the leg's timeframe already
resampled: daily bars for a "D" leg, completed W-FRI weekly bars for a "W" leg. So the
ordinary fns here compute on the frame's own ``close`` and MUST NOT resample again —
otherwise a weekly leg would be resampled twice. Only the explicitly *biweekly* signal
(``stoch_rsi_cross_up_2w``) resamples internally, because it is registered as a daily-only
leg that represents a 2-week structure (see W-eligibility note below).

W-eligibility: families ``macd_events``, ``rsi_events``, ``stoch_events`` are added to
``engine.tech_confluence.W_FAMILIES`` so the miner enumerates their weekly legs. The
biweekly family ``stoch_events_2w`` is deliberately NOT weekly-eligible (a "weekly of a
biweekly" is meaningless); it stays a daily leg whose fn does the 2-week resample.

Event semantics: an event fires (1.0) only on the FIRST bar of the cross (strict entry
bar — condition true now AND not true on the prior bar); every other bar is 0.0. Returns
a float Series aligned to the input frame's index (length == len(df)). PIT-clean: no
look-ahead, no centered windows.

HONESTY CONTRACT
----------------
Display-only / research. Deterministic standard TA math — no LLM-originated signals,
scores, or escalations. No "validated" claim in any user-facing string.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.cycles import macd_parts, stoch_rsi
from engine.technicals import rsi as _rsi

log = logging.getLogger(__name__)

# Stochastic-RSI %D smoothing (SMA of %K); %K comes from cycles.stoch_rsi.
_STOCH_D_SMOOTH: int = 3
# %K must be in the lower band for a bullish stoch cross to count as a *reversal*
# rather than noise near the top. 50 keeps it permissive but non-trivial.
_STOCH_LOWER_BAND: float = 50.0
_RSI_MID: float = 50.0


# ---------------------------------------------------------------------------
# Cross helpers — NaN-safe, warm-up-safe entry events
# ---------------------------------------------------------------------------
# A cross fires 1.0 only on the bar where `a` moves strictly above (below) `b`
# AND the PRIOR bar was on the opposite side with VALID (non-NaN) values. Because
# a comparison against a NaN is False in pandas, the shifted-prior term is False
# during indicator warm-up — so the first valid indicator bar can NEVER register a
# phantom cross just because the indicator was born above/below the line. `b` may
# be a scalar threshold (0, 50) or another Series (%D).


def _prior(x: pd.Series | float) -> pd.Series | float:
    return x.shift(1) if isinstance(x, pd.Series) else x


def _cross_above(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1.0 where *a* crosses strictly above *b* with a valid opposite prior bar."""
    cond = (a > b) & (a.shift(1) <= _prior(b))
    return cond.fillna(False).astype(float)


def _cross_below(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1.0 where *a* crosses strictly below *b* with a valid opposite prior bar."""
    cond = (a < b) & (a.shift(1) >= _prior(b))
    return cond.fillna(False).astype(float)


def _close(df: pd.DataFrame) -> pd.Series:
    return df["close"].astype(float)


# ---------------------------------------------------------------------------
# MACD cross events (compute on the frame's own close — D or W supplied by miner)
# ---------------------------------------------------------------------------

def macd_cross_up(df: pd.DataFrame, **kw) -> pd.Series:
    """MACD line crosses ABOVE its signal line (histogram crosses above zero)."""
    hist = macd_parts(_close(df))["hist"]
    return _cross_above(hist, 0.0)


def macd_cross_dn(df: pd.DataFrame, **kw) -> pd.Series:
    """MACD line crosses BELOW its signal line (histogram crosses below zero)."""
    hist = macd_parts(_close(df))["hist"]
    return _cross_below(hist, 0.0)


# ---------------------------------------------------------------------------
# RSI cross events (RSI crossing the mid-line)
# ---------------------------------------------------------------------------

def rsi_cross_up_50(df: pd.DataFrame, *, n: int = 14, level: float = _RSI_MID, **kw) -> pd.Series:
    """RSI(n) crosses ABOVE the mid-line — a bullish momentum cross."""
    r = _rsi(_close(df), n=n)
    return _cross_above(r, float(level))


def rsi_cross_dn_50(df: pd.DataFrame, *, n: int = 14, level: float = _RSI_MID, **kw) -> pd.Series:
    """RSI(n) crosses BELOW the mid-line — a bearish momentum cross."""
    r = _rsi(_close(df), n=n)
    return _cross_below(r, float(level))


# ---------------------------------------------------------------------------
# Stochastic-RSI cross events (%K crosses %D)
# ---------------------------------------------------------------------------

def _stoch_kd(close: pd.Series, *, n: int = 14, k: int = 3) -> tuple[pd.Series, pd.Series]:
    """(%K, %D) where %K = cycles.stoch_rsi and %D = SMA(%K, _STOCH_D_SMOOTH)."""
    pk = stoch_rsi(close, n=n, k=k)
    pd_ = pk.rolling(_STOCH_D_SMOOTH).mean()
    return pk, pd_


def stoch_rsi_cross_up(
    df: pd.DataFrame, *, n: int = 14, k: int = 3, lower_band: float = _STOCH_LOWER_BAND, **kw
) -> pd.Series:
    """Stochastic-RSI %K crosses ABOVE %D while in the lower band (bullish cross)."""
    pk, pd_ = _stoch_kd(_close(df), n=n, k=k)
    fired = _cross_above(pk, pd_)
    return (fired.astype(bool) & (pk < float(lower_band))).astype(float)


def stoch_rsi_cross_dn(
    df: pd.DataFrame, *, n: int = 14, k: int = 3, upper_band: float | None = None, **kw
) -> pd.Series:
    """Stochastic-RSI %K crosses BELOW %D while in the upper band (bearish cross)."""
    ub = (100.0 - _STOCH_LOWER_BAND) if upper_band is None else float(upper_band)
    pk, pd_ = _stoch_kd(_close(df), n=n, k=k)
    fired = _cross_below(pk, pd_)
    return (fired.astype(bool) & (pk > ub)).astype(float)


# ---------------------------------------------------------------------------
# Biweekly (2-week) Stochastic-RSI cross — daily leg, resamples internally
# ---------------------------------------------------------------------------

def stoch_rsi_cross_up_2w(
    df: pd.DataFrame, *, n: int = 14, k: int = 3,
    lower_band: float = _STOCH_LOWER_BAND, resample: str = "2W-FRI", **kw
) -> pd.Series:
    """2-week Stochastic-RSI bullish cross, mapped back onto the daily index.

    Registered as a DAILY leg (family stoch_events_2w, NOT weekly-eligible), so the
    miner supplies DAILY bars here and this fn resamples to completed 2-week bars,
    detects the %K-over-%D bullish cross on those bars, then places a SINGLE entry fire
    on the first daily bar at/after each completed 2-week cross. A 2W label is >= the
    last daily bar of its bin, so the mapping never leaks an incomplete 2-week bar into
    an earlier daily bar (PIT-clean).
    """
    close = _close(df)
    if not isinstance(df.index, pd.DatetimeIndex):
        # Without a datetime index we cannot resample; return all-zero (safe).
        return pd.Series(0.0, index=df.index)
    bw = close.resample(resample).last().dropna()
    if len(bw) < (n + n + _STOCH_D_SMOOTH):
        return pd.Series(0.0, index=df.index)
    pk, pd_ = _stoch_kd(bw, n=n, k=k)
    fired_bw = (_cross_above(pk, pd_).astype(bool) & (pk < float(lower_band))).astype(float)

    # Place a SINGLE daily entry fire on the first daily bar at/after each completed
    # 2-week cross (NOT ffilled across the whole period) — so the miner's daily event
    # window (event_window_d) governs recency, exactly like other daily legs.
    out = pd.Series(0.0, index=df.index)
    daily_pos = df.index  # DatetimeIndex, ascending
    for ts, v in fired_bw.items():
        if v <= 0:
            continue
        loc = daily_pos.searchsorted(ts, side="left")
        if loc < len(daily_pos):
            out.iloc[loc] = 1.0
    return out


def stoch_rsi_cross_dn_2w(
    df: pd.DataFrame, *, n: int = 14, k: int = 3,
    upper_band: float | None = None, resample: str = "2W-FRI", **kw
) -> pd.Series:
    """2-week Stochastic-RSI bearish cross, mapped back onto the daily index.

    Symmetric counterpart to stoch_rsi_cross_up_2w. Registered as a DAILY leg
    (family stoch_events_2w, NOT weekly-eligible). Fires on the first daily bar
    at/after each completed 2-week %K-below-%D bearish cross while %K is in the
    upper band. PIT-clean.
    """
    ub = (100.0 - _STOCH_LOWER_BAND) if upper_band is None else float(upper_band)
    close = _close(df)
    if not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(0.0, index=df.index)
    bw = close.resample(resample).last().dropna()
    if len(bw) < (n + n + _STOCH_D_SMOOTH):
        return pd.Series(0.0, index=df.index)
    pk, pd_ = _stoch_kd(bw, n=n, k=k)
    fired_bw = (_cross_below(pk, pd_).astype(bool) & (pk > ub)).astype(float)

    out = pd.Series(0.0, index=df.index)
    daily_pos = df.index
    for ts, v in fired_bw.items():
        if v <= 0:
            continue
        loc = daily_pos.searchsorted(ts, side="left")
        if loc < len(daily_pos):
            out.iloc[loc] = 1.0
    return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    "macd_cross_up": {
        "fn": macd_cross_up, "kind": "event", "family": "macd_events", "direction": +1,
        "default_params": {"fast": 12, "slow": 26, "signal": 9},
        "display": _disp("MACD bullish cross", "MACD 金叉"), "glyph": "arrow_up",
    },
    "macd_cross_dn": {
        "fn": macd_cross_dn, "kind": "event", "family": "macd_events", "direction": -1,
        "default_params": {"fast": 12, "slow": 26, "signal": 9},
        "display": _disp("MACD bearish cross", "MACD 死叉"), "glyph": "arrow_down",
    },
    "rsi_cross_up_50": {
        "fn": rsi_cross_up_50, "kind": "event", "family": "rsi_events", "direction": +1,
        "default_params": {"n": 14, "level": 50},
        "display": _disp("RSI crosses above 50", "RSI 上穿 50"), "glyph": "arrow_up",
    },
    "rsi_cross_dn_50": {
        "fn": rsi_cross_dn_50, "kind": "event", "family": "rsi_events", "direction": -1,
        "default_params": {"n": 14, "level": 50},
        "display": _disp("RSI crosses below 50", "RSI 下穿 50"), "glyph": "arrow_down",
    },
    "stoch_rsi_cross_up": {
        "fn": stoch_rsi_cross_up, "kind": "event", "family": "stoch_events", "direction": +1,
        "default_params": {"n": 14, "k": 3, "lower_band": _STOCH_LOWER_BAND},
        "display": _disp("Stochastic-RSI bullish cross", "随机 RSI 金叉"), "glyph": "arrow_up",
    },
    "stoch_rsi_cross_dn": {
        "fn": stoch_rsi_cross_dn, "kind": "event", "family": "stoch_events", "direction": -1,
        "default_params": {"n": 14, "k": 3, "upper_band": 100.0 - _STOCH_LOWER_BAND},
        "display": _disp("Stochastic-RSI bearish cross", "随机 RSI 死叉"), "glyph": "arrow_down",
    },
    "stoch_rsi_cross_up_2w": {
        "fn": stoch_rsi_cross_up_2w, "kind": "event", "family": "stoch_events_2w", "direction": +1,
        "default_params": {"n": 14, "k": 3, "lower_band": _STOCH_LOWER_BAND, "resample": "2W-FRI"},
        "display": _disp("Bi-weekly Stochastic-RSI bullish cross", "双周随机 RSI 金叉"),
        "glyph": "arrow_up",
    },
    "stoch_rsi_cross_dn_2w": {
        "fn": stoch_rsi_cross_dn_2w, "kind": "event", "family": "stoch_events_2w", "direction": -1,
        "default_params": {"n": 14, "k": 3, "upper_band": 100.0 - _STOCH_LOWER_BAND, "resample": "2W-FRI"},
        "display": _disp("Bi-weekly Stochastic-RSI bearish cross", "双周随机 RSI 死叉"),
        "glyph": "arrow_down",
    },
}
