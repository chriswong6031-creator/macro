"""engine/rank_momentum_signals.py — Rank-based momentum signals.

Two signal families:

  rsi_mean_reversion  — Connors RSI(3,2,100) entry/exit events
  rank_trend          — Spearman rank-correlation trend events/states

HONESTY CONTRACT
----------------
Display-only / research. Deterministic standard TA math — no LLM-originated signals,
scores, or escalations. No "validated" claim in any user-facing string.

CAUSALITY LAW: all computations use trailing windows only (no center=True, no
look-ahead). Events fire only on the completed bar where the condition first becomes
known; recomputing on any truncated prefix reproduces the identical prefix.

---

A) Connors RSI  — CRSI(3,2,100)
   CRSI = (RSI(close,3) + RSI(streak,2) + PercentRank(1d ROC, 100)) / 3

   * RSI uses Wilder's SMA-seeded RMA (engine.canon.rsi — same function the
     confluence cascade rides on).
   * streak: running count of consecutive up closes (+n) or down closes (-n),
     reset to 0 on an unchanged close.
   * PercentRank: % of the past 100 one-day ROCs strictly less than today's
     (window = 100 bars EXCLUDING today; result in [0, 100]).
     Variant: strictly-less-than over a 100-bar look-back excluding today.
   * dependency_family='rsi_mean_reversion' — same cluster as existing RSI
     signals; entry_stack_blocked=True (RUL-33-OSCSPECIES: can never share a
     combo with RSI-family signals).

B) Spearman price-trend  — n=10, signal SMA 3
   rho = Spearman correlation of chronological rank vs price rank over 10 bars,
   scaled to ×100. Implemented with pandas .rank(method='average') (scipy-free).
   Smoothed line = SMA(rho, 3).
   Valcu, TASC Feb 2011. Generic variant — vendor parity unknown; average-rank
   tie handling.
   dependency_family='rank_trend'; entry_stack_blocked=False.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine.canon import rma as _canon_rma
from engine.canon import rsi as _canon_rsi

log = logging.getLogger(__name__)


def _rsi_safe(series: pd.Series, n: int) -> pd.Series:
    """Wilder RSI via canon.rma, handling the dn=0 → RSI=100 edge case.

    canon.rsi uses `dn.replace(0, np.nan)` which produces NaN when all moves
    are upward (dn=0). The correct RSI value in that case is 100.0 (infinite
    RS). This wrapper detects those bars and fills them correctly.
    """
    s = series.astype(float)
    d = s.diff()
    up = _canon_rma(d.clip(lower=0), n)
    dn = _canon_rma((-d).clip(lower=0), n)
    # Where both are defined (not NaN from warm-up):
    both_valid = up.notna() & dn.notna()
    rs = up / dn.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + rs)
    # dn==0 (pure up move after warm-up) → RSI = 100
    result = result.where(~(both_valid & (dn == 0.0)), 100.0)
    # up==0 and dn==0 (flat) → RSI = 50 (undefined; use neutral)
    result = result.where(~(both_valid & (up == 0.0) & (dn == 0.0)), 50.0)
    return result

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Connors RSI defaults
_CRSI_RSI_N: int = 3
_CRSI_STREAK_N: int = 2
_CRSI_PRANK_N: int = 100
_CRSI_OS: float = 10.0   # oversold threshold
_CRSI_OB: float = 90.0   # overbought threshold

# Spearman defaults
_SPRM_N: int = 10          # correlation window
_SPRM_SIG: int = 3         # smoothing SMA
_SPRM_STRONG: float = 80.0 # "strong trend" threshold


# ---------------------------------------------------------------------------
# Internal helpers — Connors RSI components
# ---------------------------------------------------------------------------

def _streak(close: pd.Series) -> pd.Series:
    """Running count of consecutive up (+n) / down (-n) / unchanged (0) closes.

    Positive on a run of higher closes, negative on a run of lower closes,
    reset to 0 on an unchanged close (current close == previous close).
    PIT-clean: computed bar-by-bar via a tight numpy loop (recurrence required).
    """
    vals = close.to_numpy(dtype=float)
    out = np.zeros(len(vals), dtype=float)
    for i in range(1, len(vals)):
        if not np.isfinite(vals[i]) or not np.isfinite(vals[i - 1]):
            out[i] = 0.0
            continue
        diff = vals[i] - vals[i - 1]
        if diff > 0.0:
            out[i] = out[i - 1] + 1.0 if out[i - 1] > 0.0 else 1.0
        elif diff < 0.0:
            out[i] = out[i - 1] - 1.0 if out[i - 1] < 0.0 else -1.0
        else:
            out[i] = 0.0
    return pd.Series(out, index=close.index)


def _percent_rank(roc: pd.Series, n: int) -> pd.Series:
    """Percent rank of today's value vs the past n values (strictly less than).

    PercentRank = (# of past-n values strictly below today's) / n * 100.
    The window is the n COMPLETED prior bars (excludes today) — no look-ahead.
    PIT-clean: rolling trailing window.
    """
    vals = roc.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(n, len(vals)):
        today = vals[i]
        window = vals[i - n: i]   # n bars strictly before today
        if not np.isfinite(today):
            out[i] = np.nan
            continue
        finite_w = window[np.isfinite(window)]
        if len(finite_w) == 0:
            out[i] = np.nan
            continue
        out[i] = float(np.sum(finite_w < today)) / n * 100.0
    return pd.Series(out, index=roc.index)


def _connors_rsi(
    df: pd.DataFrame,
    rsi_n: int = _CRSI_RSI_N,
    streak_n: int = _CRSI_STREAK_N,
    prank_n: int = _CRSI_PRANK_N,
) -> pd.Series:
    """Connors RSI = (RSI(close,3) + RSI(streak,2) + PercentRank(ROC1,100)) / 3.

    Returns a float Series; NaN during warm-up.
    """
    close = df["close"].astype(float)

    # Component 1: RSI(close, 3) — Wilder RSI (NaN-safe wrapper around canon.rma)
    rsi3 = _rsi_safe(close, n=rsi_n)

    # Component 2: RSI(streak, 2)
    sk = _streak(close)
    rsi_streak = _rsi_safe(sk, n=streak_n)

    # Component 3: PercentRank of 1-day ROC over 100 bars
    roc = close.pct_change() * 100.0   # 1-day % return
    prank = _percent_rank(roc, n=prank_n)

    crsi = (rsi3 + rsi_streak + prank) / 3.0
    crsi.name = "connors_rsi"
    return crsi


# ---------------------------------------------------------------------------
# Connors RSI signal functions
# ---------------------------------------------------------------------------

def crsi_os_entry(
    df: pd.DataFrame,
    rsi_n: int = _CRSI_RSI_N,
    streak_n: int = _CRSI_STREAK_N,
    prank_n: int = _CRSI_PRANK_N,
    os_level: float = _CRSI_OS,
) -> pd.Series:
    """Event +1: CRSI crosses below the oversold level (deep oversold arrival).

    Fires on the bar where CRSI first drops below os_level (was >= os_level prior).
    """
    crsi = _connors_rsi(df, rsi_n=rsi_n, streak_n=streak_n, prank_n=prank_n)
    fired = ((crsi < os_level) & (crsi.shift(1) >= os_level)).fillna(False).astype(int)
    fired.name = "crsi_os_entry"
    return fired


def crsi_os_exit(
    df: pd.DataFrame,
    rsi_n: int = _CRSI_RSI_N,
    streak_n: int = _CRSI_STREAK_N,
    prank_n: int = _CRSI_PRANK_N,
    os_level: float = _CRSI_OS,
) -> pd.Series:
    """Event +1: CRSI crosses back above the oversold level from below (oversold exit).

    Fires on the bar where CRSI first climbs back above os_level (was < os_level prior).
    """
    crsi = _connors_rsi(df, rsi_n=rsi_n, streak_n=streak_n, prank_n=prank_n)
    fired = ((crsi > os_level) & (crsi.shift(1) <= os_level)).fillna(False).astype(int)
    fired.name = "crsi_os_exit"
    return fired


def crsi_ob_exit(
    df: pd.DataFrame,
    rsi_n: int = _CRSI_RSI_N,
    streak_n: int = _CRSI_STREAK_N,
    prank_n: int = _CRSI_PRANK_N,
    ob_level: float = _CRSI_OB,
) -> pd.Series:
    """Event -1: CRSI crosses back below the overbought level from above (overbought exit).

    Fires on the bar where CRSI first drops back below ob_level (was > ob_level prior).
    """
    crsi = _connors_rsi(df, rsi_n=rsi_n, streak_n=streak_n, prank_n=prank_n)
    fired = ((crsi < ob_level) & (crsi.shift(1) >= ob_level)).fillna(False).astype(int)
    fired.name = "crsi_ob_exit"
    return fired


# ---------------------------------------------------------------------------
# Internal helpers — Spearman
# ---------------------------------------------------------------------------

def _spearman_n(close: pd.Series, n: int = _SPRM_N) -> pd.Series:
    """Rolling Spearman rank correlation of price-rank vs chronological-rank, ×100.

    Uses pandas .rank(method='average') for tie handling (scipy-free).
    Window = n bars. Result in [-100, +100]; NaN during warm-up.
    """
    vals = close.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    time_ranks = np.arange(1, n + 1, dtype=float)  # fixed: 1..n (chronological)

    for i in range(n - 1, len(vals)):
        window = vals[i - n + 1: i + 1]
        if not np.all(np.isfinite(window)):
            continue
        # price ranks with average tie handling
        s = pd.Series(window)
        price_ranks = s.rank(method="average").to_numpy(dtype=float)
        # Pearson on ranks == Spearman
        tr_mean = time_ranks.mean()
        pr_mean = price_ranks.mean()
        tr_c = time_ranks - tr_mean
        pr_c = price_ranks - pr_mean
        denom = np.sqrt((tr_c ** 2).sum() * (pr_c ** 2).sum())
        if denom == 0.0:
            rho = 0.0
        else:
            rho = float(np.dot(tr_c, pr_c) / denom)
        out[i] = rho * 100.0

    return pd.Series(out, index=close.index)


def _spearman_smoothed(close: pd.Series, n: int = _SPRM_N, sig: int = _SPRM_SIG) -> tuple[pd.Series, pd.Series]:
    """Return (raw_rho, smoothed_rho) where smoothed = SMA(raw, sig)."""
    raw = _spearman_n(close, n=n)
    smoothed = raw.rolling(sig, min_periods=sig).mean()
    return raw, smoothed


# ---------------------------------------------------------------------------
# Spearman signal functions
# ---------------------------------------------------------------------------

def sprm_zero_up(
    df: pd.DataFrame,
    n: int = _SPRM_N,
    sig: int = _SPRM_SIG,
) -> pd.Series:
    """Event +1: smoothed Spearman crosses above zero (bullish rank-trend flip).

    Fires on the bar where the SMA(rho,3) first crosses above 0 from below.
    """
    close = df["close"].astype(float)
    _, smooth = _spearman_smoothed(close, n=n, sig=sig)
    fired = ((smooth > 0.0) & (smooth.shift(1) <= 0.0)).fillna(False).astype(int)
    fired.name = "sprm_zero_up"
    return fired


def sprm_zero_dn(
    df: pd.DataFrame,
    n: int = _SPRM_N,
    sig: int = _SPRM_SIG,
) -> pd.Series:
    """Event -1: smoothed Spearman crosses below zero (bearish rank-trend flip).

    Fires on the bar where the SMA(rho,3) first crosses below 0 from above.
    """
    close = df["close"].astype(float)
    _, smooth = _spearman_smoothed(close, n=n, sig=sig)
    fired = ((smooth < 0.0) & (smooth.shift(1) >= 0.0)).fillna(False).astype(int)
    fired.name = "sprm_zero_dn"
    return fired


def sprm_strong_up(
    df: pd.DataFrame,
    n: int = _SPRM_N,
    strong_level: float = _SPRM_STRONG,
) -> pd.Series:
    """State +1: raw Spearman rho above +strong_level (strong uptrend by rank).

    Returns 1 on each bar where raw rho > strong_level, else 0.
    """
    close = df["close"].astype(float)
    raw, _ = _spearman_smoothed(close, n=n)
    state = (raw > strong_level).fillna(False).astype(int)
    state.name = "sprm_strong_up"
    return state


def sprm_strong_dn(
    df: pd.DataFrame,
    n: int = _SPRM_N,
    strong_level: float = _SPRM_STRONG,
) -> pd.Series:
    """State -1: raw Spearman rho below -strong_level (strong downtrend by rank).

    Returns 1 on each bar where raw rho < -strong_level, else 0.
    """
    close = df["close"].astype(float)
    raw, _ = _spearman_smoothed(close, n=n)
    state = (raw < -strong_level).fillna(False).astype(int)
    state.name = "sprm_strong_dn"
    return state


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


SIGNALS: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------
    # Connors RSI signals (family = rsi_mean_reversion)
    # ------------------------------------------------------------------
    "crsi_os_entry": {
        "fn": crsi_os_entry,
        "kind": "event",
        "family": "rsi_mean_reversion",
        "direction": +1,
        "default_params": {
            "rsi_n": _CRSI_RSI_N,
            "streak_n": _CRSI_STREAK_N,
            "prank_n": _CRSI_PRANK_N,
            "os_level": _CRSI_OS,
        },
        "display": _disp(
            "Connors RSI deep oversold arrival (crosses below 10)",
            "康纳斯RSI深度超卖（跌破10）",
        ),
        "glyph": "arrow_down",
        # New metadata keys
        "dependency_family": "rsi_mean_reversion",
        "role": "setup",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Connors Research; https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/connorsrsi",
        "actionable_lag": 0,
    },
    "crsi_os_exit": {
        "fn": crsi_os_exit,
        "kind": "event",
        "family": "rsi_mean_reversion",
        "direction": +1,
        "default_params": {
            "rsi_n": _CRSI_RSI_N,
            "streak_n": _CRSI_STREAK_N,
            "prank_n": _CRSI_PRANK_N,
            "os_level": _CRSI_OS,
        },
        "display": _disp(
            "Connors RSI oversold exit (crosses back above 10)",
            "康纳斯RSI超卖结束（回升至10上方）",
        ),
        "glyph": "arrow_up",
        # New metadata keys
        "dependency_family": "rsi_mean_reversion",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Connors Research; https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/connorsrsi",
        "actionable_lag": 0,
    },
    "crsi_ob_exit": {
        "fn": crsi_ob_exit,
        "kind": "event",
        "family": "rsi_mean_reversion",
        "direction": -1,
        "default_params": {
            "rsi_n": _CRSI_RSI_N,
            "streak_n": _CRSI_STREAK_N,
            "prank_n": _CRSI_PRANK_N,
            "ob_level": _CRSI_OB,
        },
        "display": _disp(
            "Connors RSI overbought exit (crosses back below 90)",
            "康纳斯RSI超买结束（回落至90下方）",
        ),
        "glyph": "arrow_down",
        # New metadata keys
        "dependency_family": "rsi_mean_reversion",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": False,
        "provenance": "Connors Research; https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/connorsrsi",
        "actionable_lag": 0,
    },
    # ------------------------------------------------------------------
    # Spearman signals (family = rank_trend)
    # ------------------------------------------------------------------
    "sprm_zero_up": {
        "fn": sprm_zero_up,
        "kind": "event",
        "family": "rank_trend",
        "direction": +1,
        "default_params": {
            "n": _SPRM_N,
            "sig": _SPRM_SIG,
        },
        "display": _disp(
            "Spearman trend turns positive (smoothed rank correlation crosses above zero)",
            "斯皮尔曼趋势翻正（平滑排名相关系数上穿零轴）",
        ),
        "glyph": "arrow_up",
        # New metadata keys
        "dependency_family": "rank_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Valcu, TASC Feb 2011; generic variant, vendor parity unknown; average-rank tie handling",
        "actionable_lag": 0,
    },
    "sprm_zero_dn": {
        "fn": sprm_zero_dn,
        "kind": "event",
        "family": "rank_trend",
        "direction": -1,
        "default_params": {
            "n": _SPRM_N,
            "sig": _SPRM_SIG,
        },
        "display": _disp(
            "Spearman trend turns negative (smoothed rank correlation crosses below zero)",
            "斯皮尔曼趋势翻负（平滑排名相关系数下穿零轴）",
        ),
        "glyph": "arrow_down",
        # New metadata keys
        "dependency_family": "rank_trend",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Valcu, TASC Feb 2011; generic variant, vendor parity unknown; average-rank tie handling",
        "actionable_lag": 0,
    },
    "sprm_strong_up": {
        "fn": sprm_strong_up,
        "kind": "state",
        "family": "rank_trend",
        "direction": +1,
        "default_params": {
            "n": _SPRM_N,
            "strong_level": _SPRM_STRONG,
        },
        "display": _disp(
            "Spearman strong uptrend (raw rank correlation above 80)",
            "斯皮尔曼强势上升趋势（原始排名相关系数高于80）",
        ),
        "glyph": "band",
        # New metadata keys
        "dependency_family": "rank_trend",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Valcu, TASC Feb 2011; generic variant, vendor parity unknown; average-rank tie handling",
        "actionable_lag": 0,
    },
    "sprm_strong_dn": {
        "fn": sprm_strong_dn,
        "kind": "state",
        "family": "rank_trend",
        "direction": -1,
        "default_params": {
            "n": _SPRM_N,
            "strong_level": _SPRM_STRONG,
        },
        "display": _disp(
            "Spearman strong downtrend (raw rank correlation below -80)",
            "斯皮尔曼强势下降趋势（原始排名相关系数低于-80）",
        ),
        "glyph": "band",
        # New metadata keys
        "dependency_family": "rank_trend",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": False,
        "provenance": "Valcu, TASC Feb 2011; generic variant, vendor parity unknown; average-rank tie handling",
        "actionable_lag": 0,
    },
}
