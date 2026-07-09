"""engine/cycle_pattern/phase_clock.py — Monthly phase-clock classifier (PHASE-CLOCK-1).

The operator's monthly-chart eye-rule formalised as the champion baseline: a deterministic
6-state classifier over monthly oscillator readings, with FROZEN thresholds.  The states
map the canonical cycle topology:

  capitulation      — bear momentum + extreme-low stochastic
  basing            — bear momentum + stochastic recovering from extreme-low
  early_expansion   — bull momentum + K > D cross (stoch K < overbought)
  late_expansion    — bull momentum + overbought stochastic
  rolling_over      — bull momentum deteriorating (slope falling) + K < D cross
  early_contraction — bear momentum + slope falling

FROZEN THRESHOLDS (anti-curve-fit guarantee — ESX-RUL-31 + RUL-33-OSCSPECIES):
  STOCH_OVERSOLD = 20    lower bound; never tuned to data
  STOCH_OVERBOUGHT = 80  upper bound; never tuned to data
These are the textbook StochRSI oversold/overbought levels.  Tuning them post-data
would invalidate the PHASE-CLOCK-1 preregistration (PREREGISTRATION.md §18).

CLASSIFICATION RULE (evaluate top-down; first match wins):

  1. capitulation      : mmacd_sign < 0  AND  mstoch_k < STOCH_OVERSOLD
  2. basing            : mmacd_sign < 0  AND  mmacd_slope > 0  AND  mstoch_k >= STOCH_OVERSOLD
  3. early_expansion   : mmacd_sign > 0  AND  mstoch_k < STOCH_OVERBOUGHT  AND  k_gt_d
  4. late_expansion    : mmacd_sign > 0  AND  mstoch_k >= STOCH_OVERBOUGHT
  5. rolling_over      : mmacd_sign > 0  AND  mmacd_slope <= 0  AND  NOT k_gt_d
  6. early_contraction : mmacd_sign < 0  AND  mmacd_slope <= 0

  Fall-through (any bar that did not match any rule above):
    sign > 0  => early_expansion (ambiguous=True)
    sign < 0  => early_contraction (ambiguous=True)
    sign = 0  => early_contraction (ambiguous=True)

  NaN inputs (any required input is NaN) => state='unknown', ambiguous=True.

References:
  ESX-RUL-31: pinned oscillator math, monthly RSI-MACD + StochRSI K/D (14/3/3, 0-100 scale)
  RUL-33-OSCSPECIES: species-tagged oscillator application — monthly bars only
  PREREGISTRATION.md §18: PHASE-CLOCK-1 frozen classifier design
"""
from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# FROZEN THRESHOLDS — do not change without voiding the PHASE-CLOCK-1 gate
# ─────────────────────────────────────────────────────────────────────────────
STOCH_OVERSOLD: float = 20.0     # textbook StochRSI oversold level (ESX-RUL-31)
STOCH_OVERBOUGHT: float = 80.0   # textbook StochRSI overbought level (ESX-RUL-31)

# The 6 valid states + sentinel for NaN/unclassifiable input
VALID_STATES: tuple[str, ...] = (
    "capitulation",
    "basing",
    "early_expansion",
    "late_expansion",
    "rolling_over",
    "early_contraction",
)
UNKNOWN_STATE: str = "unknown"


class PhaseClockResult(NamedTuple):
    state: str        # one of VALID_STATES or UNKNOWN_STATE
    ambiguous: bool   # True when the bar fell through to the sign-only default


def classify(
    mmacd_sign: float,
    mmacd_slope: float,
    mstoch_k: float,
    mstoch_d: float,
) -> PhaseClockResult:
    """Classify one monthly bar into one of 6 phase-clock states.

    Parameters
    ----------
    mmacd_sign  : +1.0 / -1.0 from lake.py (sign of monthly RSI-MACD histogram).
                  0.0 treated as -1.0 for classification (histogram at zero = no bull).
    mmacd_slope : hist[t] − hist[t-1]; rising (>0) or falling (<=0).
    mstoch_k    : monthly StochRSI K, 0–100 scale.
    mstoch_d    : monthly StochRSI D, 0–100 scale (K smoothed by 3 bars).

    Returns
    -------
    PhaseClockResult(state, ambiguous)

    Any NaN input yields state='unknown', ambiguous=True.

    Classification logic (top-down, first match wins):
      1. capitulation      mmacd_sign<0  AND  mstoch_k<20
      2. basing            mmacd_sign<0  AND  mmacd_slope>0  AND  mstoch_k>=20
      3. early_expansion   mmacd_sign>0  AND  mstoch_k<80   AND  (mstoch_k>mstoch_d)
      4. late_expansion    mmacd_sign>0  AND  mstoch_k>=80
      5. rolling_over      mmacd_sign>0  AND  mmacd_slope<=0 AND  (mstoch_k<=mstoch_d)
      6. early_contraction mmacd_sign<0  AND  mmacd_slope<=0
      fall-through: sign>0 => early_expansion(ambiguous); else => early_contraction(ambiguous)

    Thresholds are FROZEN at 20/80 (anti-curve-fit guarantee, ESX-RUL-31).
    """
    # NaN guard — any required input NaN => unknown
    if any(math.isnan(float(x)) for x in (mmacd_sign, mmacd_slope, mstoch_k, mstoch_d)):
        return PhaseClockResult(UNKNOWN_STATE, True)

    sign = float(mmacd_sign)
    slope = float(mmacd_slope)
    k = float(mstoch_k)
    d = float(mstoch_d)
    k_gt_d = k > d

    # ── Rule 1: capitulation — bear momentum + extreme-low stoch ──────────────
    if sign < 0 and k < STOCH_OVERSOLD:
        return PhaseClockResult("capitulation", False)

    # ── Rule 2: basing — bear momentum + rising slope + stoch above oversold ──
    if sign < 0 and slope > 0 and k >= STOCH_OVERSOLD:
        return PhaseClockResult("basing", False)

    # ── Rule 3: early_expansion — bull + below overbought + K > D ─────────────
    if sign > 0 and k < STOCH_OVERBOUGHT and k_gt_d:
        return PhaseClockResult("early_expansion", False)

    # ── Rule 4: late_expansion — bull + overbought stoch ─────────────────────
    if sign > 0 and k >= STOCH_OVERBOUGHT:
        return PhaseClockResult("late_expansion", False)

    # ── Rule 5: rolling_over — bull momentum deteriorating + K <= D ───────────
    if sign > 0 and slope <= 0 and not k_gt_d:
        return PhaseClockResult("rolling_over", False)

    # ── Rule 6: early_contraction — bear momentum + falling slope ────────────
    if sign < 0 and slope <= 0:
        return PhaseClockResult("early_contraction", False)

    # ── Fall-through: ambiguous bars, classified by sign only ─────────────────
    if sign > 0:
        return PhaseClockResult("early_expansion", True)
    return PhaseClockResult("early_contraction", True)


def classify_series(state_df: pd.DataFrame) -> pd.Series:
    """Classify every row of a state_monthly DataFrame slice.

    Input columns required: mmacd_sign, mmacd_slope, mstoch_k, mstoch_d, osc_missing.
    Rows with osc_missing=True receive 'unknown'.

    Returns a pd.Series of str (state labels), same index as state_df.
    """
    states = []
    for _, row in state_df.iterrows():
        if bool(row.get("osc_missing", True)):
            states.append(UNKNOWN_STATE)
        else:
            res = classify(
                float(row["mmacd_sign"]) if not pd.isna(row["mmacd_sign"]) else float("nan"),
                float(row["mmacd_slope"]) if not pd.isna(row["mmacd_slope"]) else float("nan"),
                float(row["mstoch_k"]) if not pd.isna(row["mstoch_k"]) else float("nan"),
                float(row["mstoch_d"]) if not pd.isna(row["mstoch_d"]) else float("nan"),
            )
            states.append(res.state)
    return pd.Series(states, index=state_df.index, dtype="str")


def classify_array(
    mmacd_sign: np.ndarray,
    mmacd_slope: np.ndarray,
    mstoch_k: np.ndarray,
    mstoch_d: np.ndarray,
    osc_missing: np.ndarray | None = None,
) -> np.ndarray:
    """Vectorised classify over numpy arrays; returns array of state strings.

    osc_missing: if provided, rows where True => 'unknown'.
    All arrays must be 1-D with the same length.
    """
    n = len(mmacd_sign)
    states = np.empty(n, dtype=object)
    if osc_missing is None:
        osc_missing = np.zeros(n, dtype=bool)

    for i in range(n):
        if bool(osc_missing[i]):
            states[i] = UNKNOWN_STATE
        else:
            res = classify(
                float(mmacd_sign[i]),
                float(mmacd_slope[i]),
                float(mstoch_k[i]),
                float(mstoch_d[i]),
            )
            states[i] = res.state
    return states
