"""engine/momentum_context_signals.py — Multi-horizon momentum, benchmark relative
strength, and BBTrend chart-grammar signals.

Display-tier descriptive signals. No authority, no buy/sell commands, no composite
scores.

Benchmark-relative signals (group B)
-------------------------------------
These signals require a ``bench_close`` argument (a pd.Series of benchmark closing
prices aligned to the same DatetimeIndex as ``df``). When ``bench_close`` is None the
functions return all-zeros gracefully — the catalog build passes the benchmark via
params when available. ``screener_firing`` is set to False for these signals because
they cannot be computed without external input.

BBTrend (group C)
-----------------
Implements John Bollinger's BBTrend oscillator
(https://www.tradingview.com/support/solutions/43000726749-bbtrend/):
  BBTrend = 100 * (|shortLower - longLower| - |shortUpper - longUpper|) / shortMiddle
using BB(20,2) and BB(50,2) on close. Signals are challenger_only=True because they
share the ``volatility_channel`` family with existing Bollinger signals.

Data contract
-------------
Input ``df``: single-ticker OHLCV DataFrame with DatetimeIndex, columns
close / high / low / volume. There is NO 'open' column — never reference it.
Signal functions accept ``(df, **params)`` and return a pd.Series aligned to df.index:
  events  — 0/1 int; 1 only on the completed bar where the event becomes known
  states  — 0/1 int (or 0.0/1.0 float for display scores)
Causality law: rolling ops use trailing windows only (center=False, no future windows).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters (frozen canonical set)
# ---------------------------------------------------------------------------
_MOM_SHORT: int = 63    # ~3-month return window
_MOM_MED: int = 126     # ~6-month return window
_MOM_LONG: int = 252    # ~12-month / 52-week window
_MOM_SKIP: int = 21     # most-recent-month skip for 12-1 momentum

_RS_SHORT: int = 21     # ~1-month RS window
_RS_MED: int = 63       # ~3-month RS window
_RS_LONG: int = 126     # ~6-month RS window for ratio high/low

_BBT_SHORT: int = 20    # short BB period
_BBT_LONG: int = 50     # long BB period
_BBT_K: float = 2.0     # BB standard-deviation multiplier

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _close(df: pd.DataFrame) -> pd.Series:
    return df["close"].astype(float)


def _bb_bands(close: pd.Series, n: int, k: float = _BBT_K
              ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, mid, lower) Bollinger Bands on *close* with period n, multiplier k.

    mid = SMA(close, n); sd = rolling std(ddof=1).
    PIT-clean: trailing windows only.
    """
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=1)
    return mid + k * sd, mid, mid - k * sd


def _cross_above(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1 on bars where *a* crosses strictly above *b* (prior bar was at or below)."""
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a > b) & (a.shift(1) <= b_prev)
    return cond.fillna(False).astype(int)


def _cross_below(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1 on bars where *a* crosses strictly below *b* (prior bar was at or above)."""
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a < b) & (a.shift(1) >= b_prev)
    return cond.fillna(False).astype(int)


# ---------------------------------------------------------------------------
# Group A — Multi-horizon momentum
# (dependency_family='multi_horizon_momentum')
# ---------------------------------------------------------------------------

def _mom_returns(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Compute four return series, all trailing, all PIT-clean.

    ret_63  = close / close.shift(63) - 1
    ret_126 = close / close.shift(126) - 1
    ret_252 = close / close.shift(252) - 1
    mom_12_1 = close.shift(21) / close.shift(252) - 1
    """
    ret_63 = close / close.shift(_MOM_SHORT) - 1
    ret_126 = close / close.shift(_MOM_MED) - 1
    ret_252 = close / close.shift(_MOM_LONG) - 1
    mom_12_1 = close.shift(_MOM_SKIP) / close.shift(_MOM_LONG) - 1
    return ret_63, ret_126, ret_252, mom_12_1


def mom121_pos(df: pd.DataFrame, **params) -> pd.Series:
    """State: 12-1 momentum is positive (reversal-purged medium-term uptrend).

    Returns {0, 1}. Warm-up bars are 0.
    """
    close = _close(df)
    _, _, _, m = _mom_returns(close)
    result = (m > 0).astype(int).fillna(0)
    result.name = "mom121_pos"
    return result


def mom121_neg(df: pd.DataFrame, **params) -> pd.Series:
    """State: 12-1 momentum is negative (reversal-purged medium-term downtrend).

    Returns {0, 1}. Warm-up bars are 0.
    """
    close = _close(df)
    _, _, _, m = _mom_returns(close)
    result = (m < 0).astype(int).fillna(0)
    result.name = "mom121_neg"
    return result


def mom_accel_up(df: pd.DataFrame, **params) -> pd.Series:
    """Event: short-term momentum accelerates upward.

    Fires when ret_63 crosses above ret_126 while BOTH are improving versus 21 bars ago
    (ret_63 > ret_63.shift(21) AND ret_126 > ret_126.shift(21)).
    Returns {0, 1}; 1 on the first bar of the cross with the improvement filter.
    """
    close = _close(df)
    ret_63, ret_126, _, _ = _mom_returns(close)

    cross = _cross_above(ret_63, ret_126)
    both_improving = (
        (ret_63 > ret_63.shift(21)) & (ret_126 > ret_126.shift(21))
    ).fillna(False)
    result = (cross.astype(bool) & both_improving).astype(int)
    result.name = "mom_accel_up"
    return result


def mom_decel_dn(df: pd.DataFrame, **params) -> pd.Series:
    """Event: short-term momentum decelerates downward.

    Fires when ret_63 crosses below ret_126 while BOTH are deteriorating versus 21
    bars ago (ret_63 < ret_63.shift(21) AND ret_126 < ret_126.shift(21)).
    Returns {0, 1}; 1 on the first bar of the cross with the deterioration filter.
    """
    close = _close(df)
    ret_63, ret_126, _, _ = _mom_returns(close)

    cross = _cross_below(ret_63, ret_126)
    both_worsening = (
        (ret_63 < ret_63.shift(21)) & (ret_126 < ret_126.shift(21))
    ).fillna(False)
    result = (cross.astype(bool) & both_worsening).astype(int)
    result.name = "mom_decel_dn"
    return result


def high52w_new(df: pd.DataFrame, **params) -> pd.Series:
    """Event: close makes a new 252-day closing high on this bar (first bar only).

    Uses a trailing 252-bar rolling maximum with min_periods=252. Fires 1 only when
    the current close strictly exceeds every prior close in the window (i.e.,
    close > rolling_max of the prior 251 bars). PIT-clean: computes max on
    close.shift(1) so the current bar is excluded from its own lookback.
    """
    close = _close(df)
    # max of the previous 252 bars (not including current bar)
    prior_max = close.shift(1).rolling(_MOM_LONG, min_periods=_MOM_LONG).max()
    fired = (close > prior_max).astype(int)
    fired = fired.where(prior_max.notna(), 0).fillna(0).astype(int)
    fired.name = "high52w_new"
    return fired


def low52w_new(df: pd.DataFrame, **params) -> pd.Series:
    """Event: close makes a new 252-day closing low on this bar (first bar only).

    Mirror of high52w_new. PIT-clean: uses prior 252-bar trailing minimum.
    """
    close = _close(df)
    prior_min = close.shift(1).rolling(_MOM_LONG, min_periods=_MOM_LONG).min()
    fired = (close < prior_min).astype(int)
    fired = fired.where(prior_min.notna(), 0).fillna(0).astype(int)
    fired.name = "low52w_new"
    return fired


# ---------------------------------------------------------------------------
# Group B — Benchmark relative strength
# (dependency_family='benchmark_relative_strength')
# Graceful degrade: returns all-zeros when bench_close is None.
# ---------------------------------------------------------------------------

def _rs_series(close: pd.Series, bench: pd.Series, n: int) -> pd.Series:
    """Log relative strength: log(close/close.shift(n)) - log(bench/bench.shift(n))."""
    log_rs = np.log(close / close.shift(n)) - np.log(bench / bench.shift(n))
    return log_rs


def rs_repair(df: pd.DataFrame, bench_close: pd.Series | None = None, **params) -> pd.Series:
    """Event: 63-bar log RS crosses above zero from below (stock accelerates vs benchmark).

    Returns all-zeros when bench_close is None.
    """
    close = _close(df)
    if bench_close is None:
        return pd.Series(0, index=df.index, name="rs_repair")
    bench = bench_close.astype(float).reindex(df.index)
    rs = _rs_series(close, bench, _RS_MED)
    result = _cross_above(rs, 0.0).rename("rs_repair")
    return result


def rs_deteriorate(df: pd.DataFrame, bench_close: pd.Series | None = None, **params) -> pd.Series:
    """Event: 63-bar log RS crosses below zero from above (stock weakens vs benchmark).

    Returns all-zeros when bench_close is None.
    """
    close = _close(df)
    if bench_close is None:
        return pd.Series(0, index=df.index, name="rs_deteriorate")
    bench = bench_close.astype(float).reindex(df.index)
    rs = _rs_series(close, bench, _RS_MED)
    result = _cross_below(rs, 0.0).rename("rs_deteriorate")
    return result


def rs_new_high(df: pd.DataFrame, bench_close: pd.Series | None = None, **params) -> pd.Series:
    """State: the close/bench ratio makes a new 126-day high.

    Returns all-zeros when bench_close is None.
    """
    close = _close(df)
    if bench_close is None:
        return pd.Series(0, index=df.index, name="rs_new_high")
    bench = bench_close.astype(float).reindex(df.index)
    ratio = close / bench
    prior_max = ratio.shift(1).rolling(_RS_LONG, min_periods=_RS_LONG).max()
    fired = (ratio > prior_max).astype(int)
    fired = fired.where(prior_max.notna(), 0).fillna(0).astype(int)
    fired.name = "rs_new_high"
    return fired


def rs_new_low(df: pd.DataFrame, bench_close: pd.Series | None = None, **params) -> pd.Series:
    """State: the close/bench ratio makes a new 126-day low.

    Returns all-zeros when bench_close is None.
    """
    close = _close(df)
    if bench_close is None:
        return pd.Series(0, index=df.index, name="rs_new_low")
    bench = bench_close.astype(float).reindex(df.index)
    ratio = close / bench
    prior_min = ratio.shift(1).rolling(_RS_LONG, min_periods=_RS_LONG).min()
    fired = (ratio < prior_min).astype(int)
    fired = fired.where(prior_min.notna(), 0).fillna(0).astype(int)
    fired.name = "rs_new_low"
    return fired


# ---------------------------------------------------------------------------
# Group C — BBTrend 20/50
# (dependency_family='volatility_channel', challenger_only=True)
# Reference: John Bollinger, https://www.tradingview.com/support/solutions/43000726749-bbtrend/
# BBTrend = 100 * (|shortLower - longLower| - |shortUpper - longUpper|) / shortMiddle
# ---------------------------------------------------------------------------

def _bbtrend(close: pd.Series, short_n: int = _BBT_SHORT,
             long_n: int = _BBT_LONG, k: float = _BBT_K) -> pd.Series:
    """Compute the BBTrend oscillator on *close* with configurable periods/multiplier."""
    s_upper, s_mid, s_lower = _bb_bands(close, short_n, k)
    l_upper, _l_mid, l_lower = _bb_bands(close, long_n, k)
    bbt = 100.0 * (
        (s_lower - l_lower).abs() - (s_upper - l_upper).abs()
    ) / s_mid
    return bbt


def bbt_zero_up(df: pd.DataFrame, short_n: int = _BBT_SHORT,
                long_n: int = _BBT_LONG, k: float = _BBT_K, **params) -> pd.Series:
    """Event: BBTrend crosses above zero (bullish channel expansion signal).

    Respects short_n, long_n, k from default_params or tech_catalog.compute overrides.
    Returns {0, 1}; 1 on the first completed bar of the cross.
    """
    close = _close(df)
    bbt = _bbtrend(close, short_n=short_n, long_n=long_n, k=k)
    result = _cross_above(bbt, 0.0).rename("bbt_zero_up")
    return result


def bbt_zero_dn(df: pd.DataFrame, short_n: int = _BBT_SHORT,
                long_n: int = _BBT_LONG, k: float = _BBT_K, **params) -> pd.Series:
    """Event: BBTrend crosses below zero (bearish channel expansion signal).

    Respects short_n, long_n, k from default_params or tech_catalog.compute overrides.
    Returns {0, 1}; 1 on the first completed bar of the cross.
    """
    close = _close(df)
    bbt = _bbtrend(close, short_n=short_n, long_n=long_n, k=k)
    result = _cross_below(bbt, 0.0).rename("bbt_zero_dn")
    return result


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # ----- Group A: multi-horizon momentum -----
    "mom121_pos": {
        "fn": mom121_pos,
        "kind": "state",
        "family": "momentum_context",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "12-1 Momentum Positive (medium-term uptrend, reversal-adjusted)",
            "12-1动量为正（中期上升趋势，已剔除短期反转）",
        ),
        "glyph": "trend_up",
        # new metadata keys
        "dependency_family": "multi_horizon_momentum",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Jegadeesh & Titman (1993); standard cross-sectional momentum factor",
        "actionable_lag": 0,
    },
    "mom121_neg": {
        "fn": mom121_neg,
        "kind": "state",
        "family": "momentum_context",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "12-1 Momentum Negative (medium-term downtrend, reversal-adjusted)",
            "12-1动量为负（中期下降趋势，已剔除短期反转）",
        ),
        "glyph": "trend_down",
        "dependency_family": "multi_horizon_momentum",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Jegadeesh & Titman (1993); standard cross-sectional momentum factor",
        "actionable_lag": 0,
    },
    "mom_accel_up": {
        "fn": mom_accel_up,
        "kind": "event",
        "family": "momentum_context",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "Momentum Acceleration Up (3-month crosses above 6-month, both improving)",
            "动量加速向上（3个月回报上穿6个月，双双改善）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Multi-horizon momentum cross; standard factor timing construct",
        "actionable_lag": 0,
    },
    "mom_decel_dn": {
        "fn": mom_decel_dn,
        "kind": "event",
        "family": "momentum_context",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "Momentum Deceleration Down (3-month crosses below 6-month, both weakening)",
            "动量减速向下（3个月回报下穿6个月，双双恶化）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Multi-horizon momentum cross; standard factor timing construct",
        "actionable_lag": 0,
    },
    "high52w_new": {
        "fn": high52w_new,
        "kind": "event",
        "family": "momentum_context",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "New 52-Week Closing High",
            "创52周收盘新高",
        ),
        "glyph": "star_up",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "George & Hwang (2004); 52-week high price momentum",
        "actionable_lag": 0,
    },
    "low52w_new": {
        "fn": low52w_new,
        "kind": "event",
        "family": "momentum_context",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "New 52-Week Closing Low",
            "创52周收盘新低",
        ),
        "glyph": "star_down",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "George & Hwang (2004); 52-week high price momentum",
        "actionable_lag": 0,
    },
    # ----- Group B: benchmark relative strength -----
    "rs_repair": {
        "fn": rs_repair,
        "kind": "event",
        "family": "momentum_context",
        "direction": +1,
        "default_params": {"bench_close": None},
        "display": _disp(
            "Relative Strength Recovery (stock outpaces benchmark over 3 months)",
            "相对强度修复（3个月内股票跑赢基准）",
        ),
        "glyph": "arrow_up",
        "screener_firing": False,
        "dependency_family": "benchmark_relative_strength",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Log-RS cross; standard relative momentum construct",
        "actionable_lag": 0,
    },
    "rs_deteriorate": {
        "fn": rs_deteriorate,
        "kind": "event",
        "family": "momentum_context",
        "direction": -1,
        "default_params": {"bench_close": None},
        "display": _disp(
            "Relative Strength Deterioration (stock falls behind benchmark over 3 months)",
            "相对强度恶化（3个月内股票跑输基准）",
        ),
        "glyph": "arrow_down",
        "screener_firing": False,
        "dependency_family": "benchmark_relative_strength",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Log-RS cross; standard relative momentum construct",
        "actionable_lag": 0,
    },
    "rs_new_high": {
        "fn": rs_new_high,
        "kind": "event",
        "family": "momentum_context",
        "direction": +1,
        "default_params": {"bench_close": None},
        "display": _disp(
            "Relative Strength at 6-Month High (stock/benchmark ratio at new peak)",
            "相对强度创6个月新高（股票/基准比值创新峰）",
        ),
        "glyph": "star_up",
        "screener_firing": False,
        "dependency_family": "benchmark_relative_strength",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "RS ratio rolling high; standard relative momentum construct",
        "actionable_lag": 0,
    },
    "rs_new_low": {
        "fn": rs_new_low,
        "kind": "event",
        "family": "momentum_context",
        "direction": -1,
        "default_params": {"bench_close": None},
        "display": _disp(
            "Relative Strength at 6-Month Low (stock/benchmark ratio at new trough)",
            "相对强度创6个月新低（股票/基准比值创新谷）",
        ),
        "glyph": "star_down",
        "screener_firing": False,
        "dependency_family": "benchmark_relative_strength",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "RS ratio rolling low; standard relative momentum construct",
        "actionable_lag": 0,
    },
    # ----- Group C: BBTrend -----
    "bbt_zero_up": {
        "fn": bbt_zero_up,
        "kind": "event",
        "family": "momentum_context",
        "direction": +1,
        "default_params": {
            "short_n": _BBT_SHORT,
            "long_n": _BBT_LONG,
            "k": _BBT_K,
        },
        "display": _disp(
            "BBTrend Crosses Above Zero (channel expanding in favor of buyers)",
            "BBTrend上穿零轴（通道向多方扩张）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "volatility_channel",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": (
            "John Bollinger, BBTrend indicator; "
            "https://www.tradingview.com/support/solutions/43000726749-bbtrend/"
        ),
        "actionable_lag": 0,
    },
    "bbt_zero_dn": {
        "fn": bbt_zero_dn,
        "kind": "event",
        "family": "momentum_context",
        "direction": -1,
        "default_params": {
            "short_n": _BBT_SHORT,
            "long_n": _BBT_LONG,
            "k": _BBT_K,
        },
        "display": _disp(
            "BBTrend Crosses Below Zero (channel expanding in favor of sellers)",
            "BBTrend下穿零轴（通道向空方扩张）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volatility_channel",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": (
            "John Bollinger, BBTrend indicator; "
            "https://www.tradingview.com/support/solutions/43000726749-bbtrend/"
        ),
        "actionable_lag": 0,
    },
}
