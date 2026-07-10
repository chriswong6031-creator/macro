"""engine/ichimoku_signals.py — Ichimoku Kinko Hyo chart-grammar signal family.

Display-tier descriptive chart-grammar family. No authority, no buy/sell/stop
commands, no composite scores. Routed per
research/DANNYTRADES_INDICATOR_DOCKET_ADJUDICATION_2026-07-10_BY_FABLE.md (DT-R18);
standing constraints DT-R1..R16 in
research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md.

PIT-clean: all cloud components use .shift(displacement) so that the cloud value
at bar t uses only data known at or before bar t.

Signals
-------
  ichimoku_above_cloud      state  +1  close > cloud_top
  ichimoku_below_cloud      state  -1  close < cloud_bot
  ichimoku_tk_cross_up      event  +1  tenkan crosses above kijun
  ichimoku_tk_cross_down    event  -1  tenkan crosses below kijun
  ichimoku_cloud_breakout_up  event  +1  close crosses above cloud_top
  ichimoku_cloud_breakdown    event  -1  close crosses below cloud_bot
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------
DEFAULT_TENKAN: int = 9
DEFAULT_KIJUN: int = 26
DEFAULT_SENKOU_B: int = 52
DEFAULT_DISPLACEMENT: int = 26


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ichimoku_components(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return (close, tenkan, kijun, cloud_top, cloud_bot).

    All cloud spans are displaced forward by `displacement` bars — PIT-clean:
    the cloud value visible at bar t was projected `displacement` bars ago using
    only data that was available at that earlier bar.

    cloud_top and cloud_bot are NaN whenever either span_a or span_b is NaN
    (i.e., during the first kijun+displacement and senkou_b+displacement warm-up
    bars), so signals built on them will not fire during the incomplete-cloud
    window.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    def _midpoint(h: pd.Series, l: pd.Series, n: int) -> pd.Series:
        return (h.rolling(n, min_periods=n).max() + l.rolling(n, min_periods=n).min()) / 2.0

    tk = _midpoint(high, low, tenkan)
    kj = _midpoint(high, low, kijun)

    # Senkou Span A: average of tenkan + kijun, projected forward
    span_a = ((tk + kj) / 2.0).shift(displacement)

    # Senkou Span B: midpoint of n-period high/low, projected forward
    span_b = _midpoint(high, low, senkou_b).shift(displacement)

    # Cloud top/bottom — only defined where BOTH spans are valid.
    # pd.Series.combine(other, func) passes the non-NaN operand when one side is
    # NaN, so max(span_a, NaN) == span_a.  For the ~26-bar window between span_a
    # becoming valid and span_b becoming valid this would produce a degenerate
    # zero-thickness cloud (cloud_top == cloud_bot == span_a).  Gate explicitly
    # so signals do not fire during the incomplete-cloud window.
    both_valid = span_a.notna() & span_b.notna()
    cloud_top = span_a.combine(span_b, max).where(both_valid)
    cloud_bot = span_a.combine(span_b, min).where(both_valid)

    return close, tk, kj, cloud_top, cloud_bot


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def ichimoku_above_cloud(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> pd.Series:
    """State: close is above the cloud top (kumo). Returns {0.0, 1.0}."""
    close, _, _, cloud_top, _ = _ichimoku_components(df, tenkan, kijun, senkou_b, displacement)
    result = (close > cloud_top).astype(float)
    result = result.where(cloud_top.notna(), 0.0)
    result.name = "ichimoku_above_cloud"
    return result


def ichimoku_below_cloud(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> pd.Series:
    """State: close is below the cloud bottom (kumo). Returns {0.0, 1.0}."""
    close, _, _, _, cloud_bot = _ichimoku_components(df, tenkan, kijun, senkou_b, displacement)
    result = (close < cloud_bot).astype(float)
    result = result.where(cloud_bot.notna(), 0.0)
    result.name = "ichimoku_below_cloud"
    return result


def ichimoku_tk_cross_up(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> pd.Series:
    """Event: tenkan crosses above kijun (bullish TK cross). Returns {0.0, 1.0}."""
    _, tk, kj, _, _ = _ichimoku_components(df, tenkan, kijun, senkou_b, displacement)
    fired = ((tk > kj) & (tk.shift(1) <= kj.shift(1))).astype(float)
    fired = fired.where(tk.notna() & kj.notna(), 0.0)
    fired.name = "ichimoku_tk_cross_up"
    return fired


def ichimoku_tk_cross_down(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> pd.Series:
    """Event: tenkan crosses below kijun (bearish TK cross). Returns {0.0, 1.0}."""
    _, tk, kj, _, _ = _ichimoku_components(df, tenkan, kijun, senkou_b, displacement)
    fired = ((tk < kj) & (tk.shift(1) >= kj.shift(1))).astype(float)
    fired = fired.where(tk.notna() & kj.notna(), 0.0)
    fired.name = "ichimoku_tk_cross_down"
    return fired


def ichimoku_cloud_breakout_up(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> pd.Series:
    """Event: close crosses above cloud_top. Returns {0.0, 1.0}."""
    close, _, _, cloud_top, _ = _ichimoku_components(df, tenkan, kijun, senkou_b, displacement)
    fired = ((close > cloud_top) & (close.shift(1) <= cloud_top.shift(1))).astype(float)
    fired = fired.where(cloud_top.notna(), 0.0)
    fired.name = "ichimoku_cloud_breakout_up"
    return fired


def ichimoku_cloud_breakdown(
    df: pd.DataFrame,
    tenkan: int = DEFAULT_TENKAN,
    kijun: int = DEFAULT_KIJUN,
    senkou_b: int = DEFAULT_SENKOU_B,
    displacement: int = DEFAULT_DISPLACEMENT,
) -> pd.Series:
    """Event: close crosses below cloud_bot. Returns {0.0, 1.0}."""
    close, _, _, _, cloud_bot = _ichimoku_components(df, tenkan, kijun, senkou_b, displacement)
    fired = ((close < cloud_bot) & (close.shift(1) >= cloud_bot.shift(1))).astype(float)
    fired = fired.where(cloud_bot.notna(), 0.0)
    fired.name = "ichimoku_cloud_breakdown"
    return fired


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

_DEFAULT_PARAMS: dict[str, Any] = {
    "tenkan": DEFAULT_TENKAN,
    "kijun": DEFAULT_KIJUN,
    "senkou_b": DEFAULT_SENKOU_B,
    "displacement": DEFAULT_DISPLACEMENT,
}

SIGNALS: dict[str, dict[str, Any]] = {
    "ichimoku_above_cloud": {
        "fn": ichimoku_above_cloud,
        "kind": "state",
        "family": "ichimoku",
        "direction": +1,
        "default_params": dict(_DEFAULT_PARAMS),
        "display": {
            "en": "Ichimoku — Price Above Cloud",
            "zh": "一目均衡 — 价格在云层上方",
        },
        "glyph": "arrow_up",
    },
    "ichimoku_below_cloud": {
        "fn": ichimoku_below_cloud,
        "kind": "state",
        "family": "ichimoku",
        "direction": -1,
        "default_params": dict(_DEFAULT_PARAMS),
        "display": {
            "en": "Ichimoku — Price Below Cloud",
            "zh": "一目均衡 — 价格在云层下方",
        },
        "glyph": "arrow_down",
    },
    "ichimoku_tk_cross_up": {
        "fn": ichimoku_tk_cross_up,
        "kind": "event",
        "family": "ichimoku",
        "direction": +1,
        "default_params": dict(_DEFAULT_PARAMS),
        "display": {
            "en": "Ichimoku — Bullish TK Cross (Tenkan crosses above Kijun)",
            "zh": "一目均衡 — 看涨TK交叉（转换线上穿基准线）",
        },
        "glyph": "cross_up",
    },
    "ichimoku_tk_cross_down": {
        "fn": ichimoku_tk_cross_down,
        "kind": "event",
        "family": "ichimoku",
        "direction": -1,
        "default_params": dict(_DEFAULT_PARAMS),
        "display": {
            "en": "Ichimoku — Bearish TK Cross (Tenkan crosses below Kijun)",
            "zh": "一目均衡 — 看跌TK交叉（转换线下穿基准线）",
        },
        "glyph": "cross_down",
    },
    "ichimoku_cloud_breakout_up": {
        "fn": ichimoku_cloud_breakout_up,
        "kind": "event",
        "family": "ichimoku",
        "direction": +1,
        "default_params": dict(_DEFAULT_PARAMS),
        "display": {
            "en": "Ichimoku — Cloud Breakout Up (Price crosses above Kumo)",
            "zh": "一目均衡 — 向上突破云层（价格上穿云顶）",
        },
        "glyph": "arrow_up",
    },
    "ichimoku_cloud_breakdown": {
        "fn": ichimoku_cloud_breakdown,
        "kind": "event",
        "family": "ichimoku",
        "direction": -1,
        "default_params": dict(_DEFAULT_PARAMS),
        "display": {
            "en": "Ichimoku — Cloud Breakdown (Price crosses below Kumo)",
            "zh": "一目均衡 — 向下跌破云层（价格下穿云底）",
        },
        "glyph": "arrow_down",
    },
}
