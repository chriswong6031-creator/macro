"""engine/compression_signals.py — Compression / volatility-range chart-grammar signals.

Display-tier descriptive chart-grammar family. No authority, no buy/sell/stop commands,
no composite scores. Deterministic standard TA math — no LLM-originated signals.

Families
--------
  compression_release  — BB/KC squeeze state + directional release events (A)
  trend_efficiency     — Choppiness Index regime states/onset (B), VHF regime (C)
  breakout_channel     — Donchian channel breakouts, failures, and width expansion (D)
  volatility_range     — NR7 setup state + true-range expansion events (E)

All signal functions take (df, **params) where df has columns
close / high / low / volume and a DatetimeIndex. They return a pd.Series
aligned to df.index: events = 0/1 int (fires on the bar where the event
is FIRST KNOWN — no lookahead), states = 0/1 int (or 0.0/1.0 float).

CAUSALITY LAW: no centered windows, no future references. Rolling ops use
trailing windows only. Warm-up bars = 0 (not NaN) for events; states may
be 0 during warm-up.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.stock_technicals import (
    atr,
    choppiness,
    is_nr7,
    true_range,
    ttm_squeeze,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A. BB/KC Squeeze  (dependency_family='compression_release')
# ---------------------------------------------------------------------------

def squeeze_on(
    df: pd.DataFrame,
    n: int = 20,
    bb_k: float = 2.0,
    kc_k: float = 1.5,
) -> pd.Series:
    """State: Bollinger Band sits inside the Keltner Channel (volatility compressed).

    Delegates entirely to engine.stock_technicals.ttm_squeeze which returns a bool
    Series; we cast to int (0/1) and fill NaN warm-up bars with 0.
    """
    result = ttm_squeeze(df["high"], df["low"], df["close"], n=n, bb_k=bb_k, kc_k=kc_k)
    out = result.fillna(False).astype(int)
    out.name = "squeeze_on"
    return out



def squeeze_fire_up(
    df: pd.DataFrame,
    n: int = 20,
    bb_k: float = 2.0,
    kc_k: float = 1.5,
) -> pd.Series:
    """Event: squeeze releases (squeeze was ON last bar, OFF now) with bullish direction vote.

    Direction vote: close > 20-bar Donchian midpoint of (highest high + lowest low)/2.
    Fires 1 only on the single bar where the release occurs with an upward bias.
    """
    high, low, close = df["high"], df["low"], df["close"]
    sq = ttm_squeeze(high, low, close, n=n, bb_k=bb_k, kc_k=kc_k).fillna(False)
    # Release = was on prev bar, off now
    was_on = sq.shift(1).fillna(False)
    release = (~sq) & was_on

    # Direction vote: close above Donchian midpoint (trailing n bars of high/low)
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    mid = (hh + ll) / 2.0
    bullish = close > mid

    out = (release & bullish).astype(int)
    out.name = "squeeze_fire_up"
    return out


def squeeze_fire_dn(
    df: pd.DataFrame,
    n: int = 20,
    bb_k: float = 2.0,
    kc_k: float = 1.5,
) -> pd.Series:
    """Event: squeeze releases with bearish direction vote (close <= Donchian midpoint)."""
    high, low, close = df["high"], df["low"], df["close"]
    sq = ttm_squeeze(high, low, close, n=n, bb_k=bb_k, kc_k=kc_k).fillna(False)
    was_on = sq.shift(1).fillna(False)
    release = (~sq) & was_on

    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    mid = (hh + ll) / 2.0
    bearish = close <= mid

    out = (release & bearish).astype(int)
    out.name = "squeeze_fire_dn"
    return out


# ---------------------------------------------------------------------------
# B. Choppiness  (dependency_family='trend_efficiency')
# ---------------------------------------------------------------------------

_CHOP_TREND_LEVEL: float = 38.2
_CHOP_RANGE_LEVEL: float = 61.8


def chop_trend_regime(
    df: pd.DataFrame,
    n: int = 14,
    level: float = _CHOP_TREND_LEVEL,
) -> pd.Series:
    """State: Choppiness Index below 38.2 — market is in a trending regime."""
    chop = choppiness(df["high"], df["low"], df["close"], n=n)
    out = (chop < level).fillna(False).astype(int)
    out.name = "chop_trend_regime"
    return out


def chop_range_regime(
    df: pd.DataFrame,
    n: int = 14,
    level: float = _CHOP_RANGE_LEVEL,
) -> pd.Series:
    """State: Choppiness Index above 61.8 — market is in a ranging/choppy regime."""
    chop = choppiness(df["high"], df["low"], df["close"], n=n)
    out = (chop > level).fillna(False).astype(int)
    out.name = "chop_range_regime"
    return out


def chop_trend_onset(
    df: pd.DataFrame,
    n: int = 14,
    level: float = _CHOP_TREND_LEVEL,
) -> pd.Series:
    """Event: Choppiness Index crosses below 38.2 from above (trend onset signal)."""
    chop = choppiness(df["high"], df["low"], df["close"], n=n)
    below = chop < level
    prev_not_below = ~(chop.shift(1) < level)
    # Also require the prior bar was valid (not NaN)
    prev_valid = chop.shift(1).notna()
    out = (below & prev_not_below & prev_valid).fillna(False).astype(int)
    out.name = "chop_trend_onset"
    return out


# ---------------------------------------------------------------------------
# C. VHF  (dependency_family='trend_efficiency', challenger_only=True)
# ---------------------------------------------------------------------------

def _vhf(close: pd.Series, n: int = 28) -> pd.Series:
    """Vertical Horizontal Filter: (max(close,n) - min(close,n)) / sum(|Δclose|, n)."""
    hh = close.rolling(n, min_periods=n).max()
    ll = close.rolling(n, min_periods=n).min()
    delta = close.diff().abs()
    delta_sum = delta.rolling(n, min_periods=n).sum().replace(0, np.nan)
    return (hh - ll) / delta_sum


def vhf_trend_regime(
    df: pd.DataFrame,
    n: int = 28,
    lookback: int = 252,
) -> pd.Series:
    """State: VHF is above its own 252-day rolling median — trending regime dominant."""
    close = df["close"].astype(float)
    v = _vhf(close, n=n)
    median = v.rolling(lookback, min_periods=lookback // 2).median()
    out = (v > median).fillna(False).astype(int)
    out.name = "vhf_trend_regime"
    return out


# ---------------------------------------------------------------------------
# D. Donchian  (dependency_family='breakout_channel')
# ---------------------------------------------------------------------------

def _donchian_bands(
    high: pd.Series, low: pd.Series, n: int = 20
) -> tuple[pd.Series, pd.Series]:
    """Upper and lower Donchian bands, SHIFTED 1 bar (prior completed channel).

    upper = rolling max(high, n).shift(1) — excludes the current bar (PIT-clean breakout).
    lower = rolling min(low, n).shift(1).
    """
    upper = high.rolling(n, min_periods=n).max().shift(1)
    lower = low.rolling(n, min_periods=n).min().shift(1)
    return upper, lower


def donch_break_up(
    df: pd.DataFrame,
    n: int = 20,
) -> pd.Series:
    """Event: close exceeds the prior 20-day high (upside channel breakout)."""
    upper, _ = _donchian_bands(df["high"], df["low"], n=n)
    out = (df["close"] > upper).fillna(False).astype(int)
    out.name = "donch_break_up"
    return out


def donch_break_dn(
    df: pd.DataFrame,
    n: int = 20,
) -> pd.Series:
    """Event: close falls below the prior 20-day low (downside channel breakdown)."""
    _, lower = _donchian_bands(df["high"], df["low"], n=n)
    out = (df["close"] < lower).fillna(False).astype(int)
    out.name = "donch_break_dn"
    return out


def donch_fail_up(
    df: pd.DataFrame,
    n: int = 20,
    fail_window: int = 5,
) -> pd.Series:
    """Event: within 5 bars of a donch_break_up, close falls back below the old upper band.

    The 'old upper band' is the Donchian upper level from the bar where the breakout
    occurred (i.e., the shifted band value at the time of the break). We track the
    most recent break bar and its upper level, then detect when close crosses back below.
    """
    high, low, close = df["high"], df["low"], df["close"]
    upper, _ = _donchian_bands(high, low, n=n)

    # Where a break-up occurred
    break_up = (close > upper).fillna(False)

    # For each bar: find the most recent break-up within the past fail_window bars
    # and the upper level at that time. We track via a vectorized rolling approach:
    # within a rolling window of fail_window bars (inclusive), was there a breakup
    # AND is the current close below the upper band at the break bar?
    # We implement as a numpy loop over bars (recurrence — tracks last break level).
    n_bars = len(close)
    out_arr = np.zeros(n_bars, dtype=int)
    close_arr = close.to_numpy()
    break_arr = break_up.to_numpy()
    upper_arr = upper.to_numpy()

    last_break_idx = -1
    last_break_upper = np.nan

    for i in range(n_bars):
        if break_arr[i]:
            last_break_idx = i
            last_break_upper = upper_arr[i]
        # Fail: within fail_window bars of a break-up, close falls back below old upper
        if (
            last_break_idx >= 0
            and 0 < (i - last_break_idx) <= fail_window
            and not np.isnan(last_break_upper)
            and close_arr[i] < last_break_upper
        ):
            out_arr[i] = 1
            last_break_idx = -1  # consume the fail so it fires once

    out = pd.Series(out_arr, index=df.index, name="donch_fail_up")
    return out


def donch_fail_dn(
    df: pd.DataFrame,
    n: int = 20,
    fail_window: int = 5,
) -> pd.Series:
    """Event: within 5 bars of a donch_break_dn, close recovers above the old lower band."""
    high, low, close = df["high"], df["low"], df["close"]
    _, lower = _donchian_bands(high, low, n=n)

    break_dn = (close < lower).fillna(False)

    n_bars = len(close)
    out_arr = np.zeros(n_bars, dtype=int)
    close_arr = close.to_numpy()
    break_arr = break_dn.to_numpy()
    lower_arr = lower.to_numpy()

    last_break_idx = -1
    last_break_lower = np.nan

    for i in range(n_bars):
        if break_arr[i]:
            last_break_idx = i
            last_break_lower = lower_arr[i]
        if (
            last_break_idx >= 0
            and 0 < (i - last_break_idx) <= fail_window
            and not np.isnan(last_break_lower)
            and close_arr[i] > last_break_lower
        ):
            out_arr[i] = 1
            last_break_idx = -1

    out = pd.Series(out_arr, index=df.index, name="donch_fail_dn")
    return out


def donch_width_expand(
    df: pd.DataFrame,
    n: int = 20,
    lookback: int = 252,
    quintile: float = 0.80,
) -> pd.Series:
    """State: Donchian width / close is in the top quintile of trailing 252-day distribution."""
    upper, lower = _donchian_bands(df["high"], df["low"], n=n)
    close = df["close"].astype(float)
    width_pct = (upper - lower) / close.replace(0, np.nan)
    # Rolling 252-day 80th percentile (top quintile threshold)
    threshold = width_pct.rolling(lookback, min_periods=lookback // 2).quantile(quintile)
    out = (width_pct >= threshold).fillna(False).astype(int)
    out.name = "donch_width_expand"
    return out


# ---------------------------------------------------------------------------
# E. NR7 + Range Expansion  (dependency_family='volatility_range')
# ---------------------------------------------------------------------------

def nr7_setup(
    df: pd.DataFrame,
) -> pd.Series:
    """State: NR7 fired within the last 3 bars (including current bar).

    NR7 = today's range is narrower than each of the prior 6 days' ranges.
    The setup window of 3 bars captures the commonly-cited short-term volatility
    coiling that follows NR7 patterns.
    """
    nr7 = is_nr7(df["high"], df["low"]).fillna(False)
    # Rolling sum over 3 bars (current + 2 prior) >= 1 means NR7 within last 3 bars
    count = nr7.astype(int).rolling(3, min_periods=1).sum()
    out = (count >= 1).astype(int)
    out.name = "nr7_setup"
    return out


def range_expand_up(
    df: pd.DataFrame,
    atr_n: int = 14,
    atr_mult: float = 2.0,
    range_pct: float = 0.75,  # close must be in TOP 25% of bar range
) -> pd.Series:
    """Event: true range > 2×ATR14, close in top 25% of bar range, close > prev close.

    Captures explosive upside expansion bars (thrust up).
    range_pct=0.75 means close >= low + 0.75*(high-low) i.e. top 25% of the bar.
    """
    high, low, close = df["high"], df["low"], df["close"]
    tr = true_range(high, low, close)
    atr14 = atr(high, low, close, n=atr_n)
    bar_range = (high - low).replace(0, np.nan)
    close_pos = (close - low) / bar_range  # 0 = at low, 1 = at high

    expanding = tr > atr_mult * atr14
    top_quarter = close_pos >= range_pct
    up_close = close > close.shift(1)

    out = (expanding & top_quarter & up_close).fillna(False).astype(int)
    out.name = "range_expand_up"
    return out


def range_expand_dn(
    df: pd.DataFrame,
    atr_n: int = 14,
    atr_mult: float = 2.0,
    range_pct: float = 0.25,  # close must be in BOTTOM 25% of bar range
) -> pd.Series:
    """Event: true range > 2×ATR14, close in bottom 25% of bar range, close < prev close.

    Captures explosive downside expansion bars (thrust down).
    range_pct=0.25 means close <= low + 0.25*(high-low) i.e. bottom 25% of the bar.
    """
    high, low, close = df["high"], df["low"], df["close"]
    tr = true_range(high, low, close)
    atr14 = atr(high, low, close, n=atr_n)
    bar_range = (high - low).replace(0, np.nan)
    close_pos = (close - low) / bar_range

    expanding = tr > atr_mult * atr14
    bottom_quarter = close_pos <= range_pct
    dn_close = close < close.shift(1)

    out = (expanding & bottom_quarter & dn_close).fillna(False).astype(int)
    out.name = "range_expand_dn"
    return out


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # ---- A: Squeeze --------------------------------------------------------
    "squeeze_on": {
        "fn": squeeze_on,
        "kind": "state",
        "family": "compression",
        "direction": 0,
        "default_params": {"n": 20, "bb_k": 2.0, "kc_k": 1.5},
        "display": _disp(
            "Volatility Squeeze Active (Bollinger inside Keltner)",
            "波动率压缩中（布林带收敛于肯特纳通道内）",
        ),
        "glyph": "compress",
        # Extended metadata
        "dependency_family": "compression_release",
        "role": "setup",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "John Carter / SimplerTrading TTM Squeeze — https://www.simplertrading.com/",
        "actionable_lag": 0,
    },
    "squeeze_fire_up": {
        "fn": squeeze_fire_up,
        "kind": "event",
        "family": "compression",
        "direction": +1,
        "default_params": {"n": 20, "bb_k": 2.0, "kc_k": 1.5},
        "display": _disp(
            "Squeeze Release — Upside Breakout",
            "压缩释放 — 向上突破",
        ),
        "glyph": "arrow_up",
        "dependency_family": "compression_release",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "John Carter / SimplerTrading TTM Squeeze — https://www.simplertrading.com/",
        "actionable_lag": 0,
    },
    "squeeze_fire_dn": {
        "fn": squeeze_fire_dn,
        "kind": "event",
        "family": "compression",
        "direction": -1,
        "default_params": {"n": 20, "bb_k": 2.0, "kc_k": 1.5},
        "display": _disp(
            "Squeeze Release — Downside Breakout",
            "压缩释放 — 向下突破",
        ),
        "glyph": "arrow_down",
        "dependency_family": "compression_release",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "John Carter / SimplerTrading TTM Squeeze — https://www.simplertrading.com/",
        "actionable_lag": 0,
    },
    # ---- B: Choppiness -----------------------------------------------------
    "chop_trend_regime": {
        "fn": chop_trend_regime,
        "kind": "state",
        "family": "compression",
        "direction": 0,
        "default_params": {"n": 14, "level": 38.2},
        "display": _disp(
            "Trending Market Regime (Choppiness below 38.2)",
            "趋势市场状态（混乱度低于 38.2）",
        ),
        "glyph": "trend",
        "dependency_family": "trend_efficiency",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "E.W. Dreiss Choppiness Index — https://www.investopedia.com/terms/c/choppinessindex.asp",
        "actionable_lag": 0,
    },
    "chop_range_regime": {
        "fn": chop_range_regime,
        "kind": "state",
        "family": "compression",
        "direction": 0,
        "default_params": {"n": 14, "level": 61.8},
        "display": _disp(
            "Ranging Market Regime (Choppiness above 61.8)",
            "震荡市场状态（混乱度高于 61.8）",
        ),
        "glyph": "range",
        "dependency_family": "trend_efficiency",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "E.W. Dreiss Choppiness Index — https://www.investopedia.com/terms/c/choppinessindex.asp",
        "actionable_lag": 0,
    },
    "chop_trend_onset": {
        "fn": chop_trend_onset,
        "kind": "event",
        "family": "compression",
        "direction": 0,
        "default_params": {"n": 14, "level": 38.2},
        "display": _disp(
            "Trend Onset (Choppiness drops below 38.2)",
            "趋势启动信号（混乱度下穿 38.2）",
        ),
        "glyph": "trend_start",
        "dependency_family": "trend_efficiency",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "E.W. Dreiss Choppiness Index — https://www.investopedia.com/terms/c/choppinessindex.asp",
        "actionable_lag": 0,
    },
    # ---- C: VHF ------------------------------------------------------------
    "vhf_trend_regime": {
        "fn": vhf_trend_regime,
        "kind": "state",
        "family": "compression",
        "direction": 0,
        "default_params": {"n": 28, "lookback": 252},
        "display": _disp(
            "Trending Regime by Efficiency (VHF above median)",
            "高效率趋势状态（VHF 高于中位数）",
        ),
        "glyph": "trend",
        "dependency_family": "trend_efficiency",
        "role": "context",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Adam White VHF — https://www.fmlabs.com/reference/default.htm?url=VHF.htm",
        "actionable_lag": 0,
    },
    # ---- D: Donchian -------------------------------------------------------
    "donch_break_up": {
        "fn": donch_break_up,
        "kind": "event",
        "family": "compression",
        "direction": +1,
        "default_params": {"n": 20},
        "display": _disp(
            "Donchian Channel Upside Breakout (20-day high exceeded)",
            "唐奇安通道向上突破（超越 20 日高点）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "breakout_channel",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Richard Donchian channel — https://www.investopedia.com/terms/d/donchianchannel.asp",
        "actionable_lag": 0,
    },
    "donch_break_dn": {
        "fn": donch_break_dn,
        "kind": "event",
        "family": "compression",
        "direction": -1,
        "default_params": {"n": 20},
        "display": _disp(
            "Donchian Channel Downside Breakdown (20-day low breached)",
            "唐奇安通道向下跌破（跌破 20 日低点）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "breakout_channel",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Richard Donchian channel — https://www.investopedia.com/terms/d/donchianchannel.asp",
        "actionable_lag": 0,
    },
    "donch_fail_up": {
        "fn": donch_fail_up,
        "kind": "event",
        "family": "compression",
        "direction": -1,
        "default_params": {"n": 20, "fail_window": 5},
        "display": _disp(
            "Failed Upside Breakout (Price retreats below channel within 5 bars)",
            "向上突破失败（5 根K线内回落至通道下方）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "breakout_channel",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Richard Donchian channel — https://www.investopedia.com/terms/d/donchianchannel.asp",
        "actionable_lag": 0,
    },
    "donch_fail_dn": {
        "fn": donch_fail_dn,
        "kind": "event",
        "family": "compression",
        "direction": +1,
        "default_params": {"n": 20, "fail_window": 5},
        "display": _disp(
            "Failed Downside Breakdown (Price recovers above channel within 5 bars)",
            "向下跌破失败（5 根K线内反弹至通道上方）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "breakout_channel",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Richard Donchian channel — https://www.investopedia.com/terms/d/donchianchannel.asp",
        "actionable_lag": 0,
    },
    "donch_width_expand": {
        "fn": donch_width_expand,
        "kind": "state",
        "family": "compression",
        "direction": 0,
        "default_params": {"n": 20, "lookback": 252, "quintile": 0.80},
        "display": _disp(
            "Wide Channel (Donchian width in top 20% of trailing year)",
            "宽幅通道（唐奇安宽度处于过去一年前 20% 分位）",
        ),
        "glyph": "expand",
        "dependency_family": "breakout_channel",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Richard Donchian channel — https://www.investopedia.com/terms/d/donchianchannel.asp",
        "actionable_lag": 0,
    },
    # ---- E: NR7 + Range Expansion ------------------------------------------
    "nr7_setup": {
        "fn": nr7_setup,
        "kind": "state",
        "family": "compression",
        "direction": 0,
        "default_params": {},
        "display": _disp(
            "NR7 Coiling Pattern Active (Narrowest range in 7 bars, within last 3)",
            "NR7 盘整形态（近 3 根K线内出现 7 日最窄波幅）",
        ),
        "glyph": "compress",
        "dependency_family": "volatility_range",
        "role": "setup",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Toby Crabel NR7 — 'Day Trading with Short-Term Price Patterns' (1990)",
        "actionable_lag": 0,
    },
    "range_expand_up": {
        "fn": range_expand_up,
        "kind": "event",
        "family": "compression",
        "direction": +1,
        "default_params": {"atr_n": 14, "atr_mult": 2.0, "range_pct": 0.75},
        "display": _disp(
            "Upside Range Expansion (True range > 2×ATR, strong close)",
            "向上扩幅（真实波幅超 2 倍 ATR，收盘强势）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "volatility_range",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Linda Raschke / LBR Group range expansion — https://www.lbrgroup.com/",
        "actionable_lag": 0,
    },
    "range_expand_dn": {
        "fn": range_expand_dn,
        "kind": "event",
        "family": "compression",
        "direction": -1,
        "default_params": {"atr_n": 14, "atr_mult": 2.0, "range_pct": 0.25},
        "display": _disp(
            "Downside Range Expansion (True range > 2×ATR, weak close)",
            "向下扩幅（真实波幅超 2 倍 ATR，收盘弱势）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volatility_range",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Linda Raschke / LBR Group range expansion — https://www.lbrgroup.com/",
        "actionable_lag": 0,
    },
}
