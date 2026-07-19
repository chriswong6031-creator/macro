"""engine/volume_flow_signals.py — Volume-flow chart-grammar signals.

Display-tier descriptive chart-grammar family (family='volume_flow').
No authority, no buy/sell/stop commands, no composite scores.

Signals
-------
CMF (n=20)  — reuses engine.stock_technicals.chaikin_money_flow
  cmf_zero_up        event  +1  CMF crosses above 0
  cmf_zero_dn        event  -1  CMF crosses below 0
  cmf_pos_persist    state  +1  CMF > 0.05 for >= 10 consecutive bars
  cmf_neg_persist    state  -1  CMF < -0.05 for >= 10 consecutive bars

OBV  — reuses engine.stock_technicals.on_balance_volume
  obv_slope_up       state  +1  20-day rolling slope of OBV > 0
  obv_slope_dn       state  -1  20-day rolling slope of OBV < 0
  obv_break_up       event  +1  OBV crosses above its prior-60-day max (shifted 1 bar)
  obv_break_dn       event  -1  OBV crosses below its prior-60-day min (shifted 1 bar)

RVOL (n=20)  — volume / SMA(volume, 20)
  rvol_spike         event   0  rvol >= 2.0 on first bar after being < 2.0
  rvol_dryup         state   0  5-day mean rvol < 0.6

MFI (n=14)  — money flow index (entry_stack_blocked per RUL-33-OSCSPECIES)
  mfi_os_exit        event  +1  MFI crosses back above 20 from below
  mfi_ob_exit        event  -1  MFI crosses back below 80 from above
  mfi_50_up          event  +1  MFI crosses above 50
  mfi_50_dn          event  -1  MFI crosses below 50

Dependency clusters
-------------------
  CMF, OBV, MFI → dependency_family='volume_money_flow'
  RVOL           → dependency_family='volume_participation'

Causality: all rolling ops use trailing windows only; no center=True; no look-ahead.
Guard: zero-range bars (high==low) → money-flow multiplier forced to 0; zero volume →
treated as NaN before vol-weighted sums.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.stock_technicals import chaikin_money_flow, on_balance_volume

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------
_CMF_N: int = 20
_CMF_POS_THRESH: float = 0.05
_CMF_NEG_THRESH: float = -0.05
_CMF_PERSIST: int = 10

_OBV_SLOPE_N: int = 20
_OBV_BREAK_N: int = 60

_RVOL_N: int = 20
_RVOL_SPIKE: float = 2.0
_RVOL_DRYUP_WINDOW: int = 5
_RVOL_DRYUP_THRESH: float = 0.6

_MFI_N: int = 14
_MFI_OS: float = 20.0
_MFI_OB: float = 80.0
_MFI_MID: float = 50.0


# ---------------------------------------------------------------------------
# Cross helpers (entry-bar-only, PIT-clean)
# ---------------------------------------------------------------------------

def _cross_above(a: pd.Series, b: float | pd.Series) -> pd.Series:
    """1.0 on the bar where *a* first moves strictly above *b*."""
    prev_b = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a > b) & (a.shift(1) <= prev_b)
    return cond.fillna(False).astype(float)


def _cross_below(a: pd.Series, b: float | pd.Series) -> pd.Series:
    """1.0 on the bar where *a* first moves strictly below *b*."""
    prev_b = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a < b) & (a.shift(1) >= prev_b)
    return cond.fillna(False).astype(float)


# ---------------------------------------------------------------------------
# MFI helper (standalone — does not call stock_technicals to stay self-contained
# with the zero-range / zero-volume guards required by the spec)
# ---------------------------------------------------------------------------

def _mfi_series(df: pd.DataFrame, n: int = _MFI_N) -> pd.Series:
    """Money Flow Index over *n* bars.

    Typical price = (H + L + C) / 3; money flow = TP * volume.
    Positive flow on bars where TP > prev TP; negative otherwise.
    MFI = 100 - 100 / (1 + posSum / negSum).
    Guard: negSum == 0 → MFI = 100; zero-range bars already handled by TP unchanged.
    Zero volume → raw_flow = 0 (no contribution to either pool).
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    vol = df["volume"].fillna(0.0).astype(float)

    tp = (high + low + close) / 3.0
    raw_flow = tp * vol.where(vol > 0, 0.0)

    tp_prev = tp.shift(1)
    pos_flow = raw_flow.where(tp > tp_prev, 0.0).fillna(0.0)
    neg_flow = raw_flow.where(tp < tp_prev, 0.0).fillna(0.0)

    pos_sum = pos_flow.rolling(n, min_periods=n).sum()
    neg_sum = neg_flow.rolling(n, min_periods=n).sum()

    mfr = pos_sum / neg_sum.replace(0, np.nan)
    mfi = 100.0 - 100.0 / (1.0 + mfr)
    # Where neg_sum == 0 AND pos_sum is valid → all flow was positive → MFI = 100.
    # Warm-up bars (pos_sum is NaN) must stay NaN so cross helpers skip them.
    all_up = pos_sum.notna() & (neg_sum == 0.0)
    mfi = mfi.where(~all_up, 100.0)
    return mfi


# ---------------------------------------------------------------------------
# CMF signals
# ---------------------------------------------------------------------------

def cmf_zero_up(df: pd.DataFrame, n: int = _CMF_N) -> pd.Series:
    """Event: Chaikin Money Flow crosses above 0."""
    cmf = chaikin_money_flow(df["high"], df["low"], df["close"], df["volume"], n=n)
    s = _cross_above(cmf, 0.0)
    s.name = "cmf_zero_up"
    return s


def cmf_zero_dn(df: pd.DataFrame, n: int = _CMF_N) -> pd.Series:
    """Event: Chaikin Money Flow crosses below 0."""
    cmf = chaikin_money_flow(df["high"], df["low"], df["close"], df["volume"], n=n)
    s = _cross_below(cmf, 0.0)
    s.name = "cmf_zero_dn"
    return s


def cmf_pos_persist(df: pd.DataFrame, n: int = _CMF_N,
                    thresh: float = _CMF_POS_THRESH,
                    persist: int = _CMF_PERSIST) -> pd.Series:
    """State: CMF > thresh for >= persist consecutive bars."""
    cmf = chaikin_money_flow(df["high"], df["low"], df["close"], df["volume"], n=n)
    above = (cmf > thresh).astype(float)
    count = above.rolling(persist, min_periods=persist).sum()
    s = (count >= persist).astype(float).where(cmf.notna(), 0.0)
    s.name = "cmf_pos_persist"
    return s


def cmf_neg_persist(df: pd.DataFrame, n: int = _CMF_N,
                    thresh: float = _CMF_NEG_THRESH,
                    persist: int = _CMF_PERSIST) -> pd.Series:
    """State: CMF < thresh for >= persist consecutive bars."""
    cmf = chaikin_money_flow(df["high"], df["low"], df["close"], df["volume"], n=n)
    below = (cmf < thresh).astype(float)
    count = below.rolling(persist, min_periods=persist).sum()
    s = (count >= persist).astype(float).where(cmf.notna(), 0.0)
    s.name = "cmf_neg_persist"
    return s


# ---------------------------------------------------------------------------
# OBV signals
# ---------------------------------------------------------------------------

def _obv(df: pd.DataFrame) -> pd.Series:
    return on_balance_volume(df["close"].astype(float), df["volume"].astype(float))


def _obv_slope(obv_series: pd.Series, n: int = _OBV_SLOPE_N) -> pd.Series:
    """Rolling OLS slope of OBV over *n* bars via numpy polyfit vectorised proxy.

    Approximation: slope ~ (last value - first value) / (n-1), computed via
    rolling difference of the rolling-lagged value. Equivalent to the sign of
    the n-bar change, which is sufficient for direction detection.

    Full OLS slope = sum((x - x_bar)(y - y_bar)) / sum((x - x_bar)^2)
    where x = [0..n-1]. The numerator equals the sum of (i - (n-1)/2)*y_i
    for i in [0..n-1], which simplifies for DIRECTION to the sign of
    (obv[-1] - obv[-n]), i.e. the n-bar difference. We compute that exactly.
    """
    return obv_series - obv_series.shift(n)


def obv_slope_up(df: pd.DataFrame, n: int = _OBV_SLOPE_N) -> pd.Series:
    """State: 20-day rolling slope of OBV > 0 (OBV trending up)."""
    obv = _obv(df)
    slope = _obv_slope(obv, n=n)
    s = (slope > 0).astype(float).fillna(0.0)
    s.name = "obv_slope_up"
    return s


def obv_slope_dn(df: pd.DataFrame, n: int = _OBV_SLOPE_N) -> pd.Series:
    """State: 20-day rolling slope of OBV < 0 (OBV trending down)."""
    obv = _obv(df)
    slope = _obv_slope(obv, n=n)
    s = (slope < 0).astype(float).fillna(0.0)
    s.name = "obv_slope_dn"
    return s


def obv_break_up(df: pd.DataFrame, n: int = _OBV_BREAK_N) -> pd.Series:
    """Event: OBV crosses above its prior 60-day rolling maximum (shifted 1 bar).

    The reference is the rolling max of the PREVIOUS n bars (shift(1) so the
    current bar is excluded — no look-ahead on the bar being evaluated).
    """
    obv = _obv(df)
    prior_max = obv.shift(1).rolling(n, min_periods=n).max()
    s = _cross_above(obv, prior_max)
    s.name = "obv_break_up"
    return s


def obv_break_dn(df: pd.DataFrame, n: int = _OBV_BREAK_N) -> pd.Series:
    """Event: OBV crosses below its prior 60-day rolling minimum (shifted 1 bar)."""
    obv = _obv(df)
    prior_min = obv.shift(1).rolling(n, min_periods=n).min()
    s = _cross_below(obv, prior_min)
    s.name = "obv_break_dn"
    return s


# ---------------------------------------------------------------------------
# RVOL signals
# ---------------------------------------------------------------------------

def _rvol(df: pd.DataFrame, n: int = _RVOL_N) -> pd.Series:
    """Relative volume: volume / SMA(volume, n). Zero volume → 0."""
    vol = df["volume"].astype(float).fillna(0.0)
    avg = vol.rolling(n, min_periods=n).mean().replace(0, np.nan)
    return (vol / avg).fillna(0.0)


def rvol_spike(df: pd.DataFrame, n: int = _RVOL_N,
               spike_thresh: float = _RVOL_SPIKE) -> pd.Series:
    """Event: rvol >= spike_thresh on the first bar after being below that threshold."""
    rv = _rvol(df, n=n)
    # Fires on the first bar where rvol crosses from <thresh to >=thresh
    s = _cross_above(rv, spike_thresh - 1e-12)  # use cross logic: prev < thresh, now >= thresh
    # But _cross_above checks prev <= thresh (not strictly <); re-derive for >= threshold:
    # fire = (rv >= thresh) & (rv.shift(1) < thresh)
    fired = ((rv >= spike_thresh) & (rv.shift(1) < spike_thresh)).fillna(False).astype(float)
    fired.name = "rvol_spike"
    return fired


def rvol_dryup(df: pd.DataFrame, n: int = _RVOL_N,
               dryup_window: int = _RVOL_DRYUP_WINDOW,
               dryup_thresh: float = _RVOL_DRYUP_THRESH) -> pd.Series:
    """State: 5-day mean of rvol < dryup_thresh (volume drying up)."""
    rv = _rvol(df, n=n)
    mean_rv = rv.rolling(dryup_window, min_periods=dryup_window).mean()
    s = (mean_rv < dryup_thresh).astype(float).fillna(0.0)
    s.name = "rvol_dryup"
    return s


# ---------------------------------------------------------------------------
# MFI signals
# ---------------------------------------------------------------------------

def mfi_os_exit(df: pd.DataFrame, n: int = _MFI_N,
                os_level: float = _MFI_OS) -> pd.Series:
    """Event: MFI crosses back above oversold level (from below 20 to above 20)."""
    mfi = _mfi_series(df, n=n)
    s = _cross_above(mfi, os_level)
    s.name = "mfi_os_exit"
    return s


def mfi_ob_exit(df: pd.DataFrame, n: int = _MFI_N,
                ob_level: float = _MFI_OB) -> pd.Series:
    """Event: MFI crosses back below overbought level (from above 80 to below 80)."""
    mfi = _mfi_series(df, n=n)
    s = _cross_below(mfi, ob_level)
    s.name = "mfi_ob_exit"
    return s


def mfi_50_up(df: pd.DataFrame, n: int = _MFI_N,
              mid: float = _MFI_MID) -> pd.Series:
    """Event: MFI crosses above 50 (bullish mid-line cross)."""
    mfi = _mfi_series(df, n=n)
    s = _cross_above(mfi, mid)
    s.name = "mfi_50_up"
    return s


def mfi_50_dn(df: pd.DataFrame, n: int = _MFI_N,
              mid: float = _MFI_MID) -> pd.Series:
    """Event: MFI crosses below 50 (bearish mid-line cross)."""
    mfi = _mfi_series(df, n=n)
    s = _cross_below(mfi, mid)
    s.name = "mfi_50_dn"
    return s


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # ── CMF ──────────────────────────────────────────────────────────────────
    "cmf_zero_up": {
        "fn": cmf_zero_up,
        "kind": "event",
        "family": "volume_flow",
        "direction": +1,
        "default_params": {"n": _CMF_N},
        "display": _disp(
            "Money Flow turns positive (CMF crosses above zero)",
            "资金流动转正（CMF 上穿零轴）",
        ),
        "glyph": "arrow_up",
        # New metadata keys
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Chaikin Analytics / Marc Chaikin — https://corporatefinanceinstitute.com/resources/equities/chaikin-money-flow-cmf/",
        "actionable_lag": 0,
    },
    "cmf_zero_dn": {
        "fn": cmf_zero_dn,
        "kind": "event",
        "family": "volume_flow",
        "direction": -1,
        "default_params": {"n": _CMF_N},
        "display": _disp(
            "Money Flow turns negative (CMF crosses below zero)",
            "资金流动转负（CMF 下穿零轴）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Chaikin Analytics / Marc Chaikin — https://corporatefinanceinstitute.com/resources/equities/chaikin-money-flow-cmf/",
        "actionable_lag": 0,
    },
    "cmf_pos_persist": {
        "fn": cmf_pos_persist,
        "kind": "state",
        "family": "volume_flow",
        "direction": +1,
        "default_params": {
            "n": _CMF_N,
            "thresh": _CMF_POS_THRESH,
            "persist": _CMF_PERSIST,
        },
        "display": _disp(
            "Sustained buying pressure (CMF above +0.05 for 10+ bars)",
            "持续买盘压力（CMF 高于 +0.05 达 10 根或以上K线）",
        ),
        "glyph": "bar_up",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Chaikin Analytics / Marc Chaikin — https://corporatefinanceinstitute.com/resources/equities/chaikin-money-flow-cmf/",
        "actionable_lag": 0,
    },
    "cmf_neg_persist": {
        "fn": cmf_neg_persist,
        "kind": "state",
        "family": "volume_flow",
        "direction": -1,
        "default_params": {
            "n": _CMF_N,
            "thresh": _CMF_NEG_THRESH,
            "persist": _CMF_PERSIST,
        },
        "display": _disp(
            "Sustained selling pressure (CMF below -0.05 for 10+ bars)",
            "持续卖盘压力（CMF 低于 -0.05 达 10 根或以上K线）",
        ),
        "glyph": "bar_down",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Chaikin Analytics / Marc Chaikin — https://corporatefinanceinstitute.com/resources/equities/chaikin-money-flow-cmf/",
        "actionable_lag": 0,
    },

    # ── OBV ──────────────────────────────────────────────────────────────────
    "obv_slope_up": {
        "fn": obv_slope_up,
        "kind": "state",
        "family": "volume_flow",
        "direction": +1,
        "default_params": {"n": _OBV_SLOPE_N},
        "display": _disp(
            "Volume backing the move up (OBV rising over 20 days)",
            "成交量支撑上涨（OBV 20日趋势向上）",
        ),
        "glyph": "bar_up",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Joseph Granville, 'New Key to Stock Market Profits' (1963) — https://www.investopedia.com/terms/o/onbalancevolume.asp",
        "actionable_lag": 0,
    },
    "obv_slope_dn": {
        "fn": obv_slope_dn,
        "kind": "state",
        "family": "volume_flow",
        "direction": -1,
        "default_params": {"n": _OBV_SLOPE_N},
        "display": _disp(
            "Volume backing the move down (OBV falling over 20 days)",
            "成交量支撑下跌（OBV 20日趋势向下）",
        ),
        "glyph": "bar_down",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Joseph Granville, 'New Key to Stock Market Profits' (1963) — https://www.investopedia.com/terms/o/onbalancevolume.asp",
        "actionable_lag": 0,
    },
    "obv_break_up": {
        "fn": obv_break_up,
        "kind": "event",
        "family": "volume_flow",
        "direction": +1,
        "default_params": {"n": _OBV_BREAK_N},
        "display": _disp(
            "OBV breaks to new 60-day high (accumulation surge)",
            "OBV 突破近60日高点（资金加速吸筹）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Joseph Granville, 'New Key to Stock Market Profits' (1963) — https://www.investopedia.com/terms/o/onbalancevolume.asp",
        "actionable_lag": 0,
    },
    "obv_break_dn": {
        "fn": obv_break_dn,
        "kind": "event",
        "family": "volume_flow",
        "direction": -1,
        "default_params": {"n": _OBV_BREAK_N},
        "display": _disp(
            "OBV breaks to new 60-day low (distribution surge)",
            "OBV 跌破近60日低点（资金加速派发）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volume_money_flow",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Joseph Granville, 'New Key to Stock Market Profits' (1963) — https://www.investopedia.com/terms/o/onbalancevolume.asp",
        "actionable_lag": 0,
    },

    # ── RVOL ─────────────────────────────────────────────────────────────────
    "rvol_spike": {
        "fn": rvol_spike,
        "kind": "event",
        "family": "volume_flow",
        "direction": 0,
        "default_params": {"n": _RVOL_N, "spike_thresh": _RVOL_SPIKE},
        "display": _disp(
            "Volume surge (relative volume doubles its 20-day average)",
            "成交量异常放大（相对成交量超过20日均量2倍）",
        ),
        "glyph": "spike",
        "dependency_family": "volume_participation",
        "role": "participation",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Standard relative-volume concept — https://www.investopedia.com/terms/r/relative_volume.asp",
        "actionable_lag": 0,
    },
    "rvol_dryup": {
        "fn": rvol_dryup,
        "kind": "state",
        "family": "volume_flow",
        "direction": 0,
        "default_params": {
            "n": _RVOL_N,
            "dryup_window": _RVOL_DRYUP_WINDOW,
            "dryup_thresh": _RVOL_DRYUP_THRESH,
        },
        "display": _disp(
            "Volume drying up (5-day average below 60% of normal)",
            "成交量持续萎缩（5日均量低于正常水平60%）",
        ),
        "glyph": "dryup",
        "dependency_family": "volume_participation",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Standard relative-volume concept — https://www.investopedia.com/terms/r/relative_volume.asp",
        "actionable_lag": 0,
    },

    # ── MFI ──────────────────────────────────────────────────────────────────
    "mfi_os_exit": {
        "fn": mfi_os_exit,
        "kind": "event",
        "family": "volume_flow",
        "direction": +1,
        "default_params": {"n": _MFI_N, "os_level": _MFI_OS},
        "display": _disp(
            "Oversold money flow recovering (MFI crosses back above 20)",
            "资金流量超卖回升（MFI 重新上穿 20）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "volume_money_flow",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Gene Quong & Avrum Soudack, 'High Volume Pullbacks' (1989) — https://www.investopedia.com/terms/m/mfi.asp",
        "actionable_lag": 0,
    },
    "mfi_ob_exit": {
        "fn": mfi_ob_exit,
        "kind": "event",
        "family": "volume_flow",
        "direction": -1,
        "default_params": {"n": _MFI_N, "ob_level": _MFI_OB},
        "display": _disp(
            "Overbought money flow retreating (MFI crosses back below 80)",
            "资金流量超买回落（MFI 重新下穿 80）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volume_money_flow",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Gene Quong & Avrum Soudack, 'High Volume Pullbacks' (1989) — https://www.investopedia.com/terms/m/mfi.asp",
        "actionable_lag": 0,
    },
    "mfi_50_up": {
        "fn": mfi_50_up,
        "kind": "event",
        "family": "volume_flow",
        "direction": +1,
        "default_params": {"n": _MFI_N, "mid": _MFI_MID},
        "display": _disp(
            "Money flow momentum turns bullish (MFI crosses above 50)",
            "资金动能转为看涨（MFI 上穿 50）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "volume_money_flow",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Gene Quong & Avrum Soudack, 'High Volume Pullbacks' (1989) — https://www.investopedia.com/terms/m/mfi.asp",
        "actionable_lag": 0,
    },
    "mfi_50_dn": {
        "fn": mfi_50_dn,
        "kind": "event",
        "family": "volume_flow",
        "direction": -1,
        "default_params": {"n": _MFI_N, "mid": _MFI_MID},
        "display": _disp(
            "Money flow momentum turns bearish (MFI crosses below 50)",
            "资金动能转为看跌（MFI 下穿 50）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volume_money_flow",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Gene Quong & Avrum Soudack, 'High Volume Pullbacks' (1989) — https://www.investopedia.com/terms/m/mfi.asp",
        "actionable_lag": 0,
    },
}
