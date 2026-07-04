"""engine.oracle.oscillators — Shared weekly oscillator machinery.

WHY THIS MODULE EXISTS
-----------------------
Both ``engine.oracle.panel`` (the panel builder) and
``scripts.oracle_gauntlet_p8`` (the backtest harness) need identical weekly
StochRSI K/D values and the same washout-active boolean.  This module is the
SINGLE SOURCE of truth so that panel columns and backtest entries are computed
by exactly the same code path — no forked implementations that can drift.

DESIGN RULES
------------
* Oscillators are computed via the FAITHFUL Pine port in
  ``research.signal_engine.confluence.stoch_rsi_kd`` — never a hand-rolled
  variant (see C1 spec §6 ORACLE_COMPOUND_LIBRARY.md).
* Weekly bars are W-FRI right-edge labelled (pandas default). This is
  **leak-free** by construction: the label date is the last trading day IN the
  bar, so bar[label] contains no close dated after ``label``.
* The forward-fill onto daily rows carries only COMPLETED bars: row t sees the
  weekly K/D from the last weekly bar whose label date <= t.  An in-progress
  bar (whose label date is still in the future relative to t) must NEVER
  contribute — that is the failure mode the no-lookahead test guards against.

PUBLIC API
----------
resample_weekly_leakfree(daily_close) -> pd.Series
    W-FRI weekly closes, right-edge labelled.

weekly_stochrsi_kd(daily_close) -> tuple[pd.Series, pd.Series]
    Compute weekly K and D (via faithful port) and forward-fill onto the daily
    index of ``daily_close``.  Row t carries the last COMPLETED weekly bar's
    K/D as of t (the in-progress bar is excluded).

washout_active_series(daily_close) -> pd.Series[bool]
    Registered P8 definition: K < 20 on >= 2 consecutive completed weekly bars
    within the prior 3 bars.  Forward-filled onto the daily index.
    Also nullable (False where K/D not yet available).

BILINGUAL NOTE
--------------
Column names ``stochrsi_w_k`` / ``stochrsi_w_d`` / ``washout_w`` are
display-layer names used downstream; their Chinese equivalents for any UI
surface are provided in the panel manifest, not here (this module is
computation-only).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

# FAITHFUL port — the only permitted source for RSI/StochRSI arithmetic.
# research.signal_engine.confluence is on sys.path via the repo root.
from research.signal_engine.confluence import stoch_rsi_kd as _stoch_rsi_kd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registered constants (frozen — mirror oracle_gauntlet_p8.py; do not retune)
# ---------------------------------------------------------------------------

#: StochRSI-K threshold below which a bar is "in washout".
#: Source: P8 WASHOUT_K_THRESHOLD = 20.0 (frozen 2026-07-04).
WASHOUT_K_THRESHOLD: float = 20.0

#: Minimum consecutive K<20 bars required within the lookback window.
#: Source: P8 WASHOUT_CONSEC_BARS = 2 (frozen 2026-07-04).
WASHOUT_CONSEC_BARS: int = 2

#: Size of the lookback window (in weekly bars) for the washout check.
#: Source: P8 WASHOUT_LOOK_BACK = 3 (frozen 2026-07-04).
WASHOUT_LOOK_BACK: int = 3

# Minimum weekly bars needed before the oscillator warm-up is complete.
# stoch_rsi_kd requires RSI_LEN(14) + STOCH_LEN(14) + SMOOTH_K(3) + SMOOTH_D(3) = ~34 bars
# plus one extra for .shift(1) comparisons.  40 is the P8 minimum.
_MIN_WEEKLY_BARS: int = 40


# ---------------------------------------------------------------------------
# Weekly resample
# ---------------------------------------------------------------------------


def resample_weekly_leakfree(daily_close: pd.Series) -> pd.Series:
    """Resample daily close prices to weekly (W-FRI) bars, leak-free.

    Convention: each bar is labelled with the LAST trading day in that calendar
    week (the Friday close date, or the last trading day if Friday was a
    non-trading day).  Pandas ``resample("W-FRI").last()`` implements this
    directly — the label IS the last date in the bar, so bar[label] contains
    no data dated after ``label`` (right-edge = last day IN the window).

    This is the same function used in ``scripts/oracle_gauntlet_p8.py`` —
    imported from here to ensure identity.

    Truncation invariance: if the daily series is truncated at day t, all
    completed weekly bars (label <= t) are unchanged.  A partial bar (label > t)
    is dropped because ``dropna()`` removes bars with no data.
    """
    return daily_close.resample("W-FRI").last().dropna()


# ---------------------------------------------------------------------------
# Oscillator computation (faithful port wrapper)
# ---------------------------------------------------------------------------


def weekly_stochrsi_kd(
    daily_close: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Compute weekly StochRSI K and D, forward-filled onto the daily index.

    Steps
    -----
    1. Resample daily close to W-FRI weekly bars (``resample_weekly_leakfree``).
    2. Compute K, D via the faithful confluence.py port (``stoch_rsi_kd``).
    3. Forward-fill K and D onto the daily index with the convention:
       row t carries the value from the **last completed** weekly bar whose
       label date <= t.  The in-progress bar for the current (incomplete) week
       is excluded — it has no label date yet and therefore never contributes.

    Implementation detail on the ffill:
       ``wk_k.reindex(daily_close.index, method="ffill")`` aligns weekly labels
       (e.g. 2020-03-06) to the daily index by forward-filling: every daily row
       between the previous weekly bar's label and the next one carries the
       previous label's value.  Because weekly labels are always IN the daily
       index (they are the last trading day of the week), the fill is exact and
       right-edge-respecting.  A weekly bar whose label date > max(daily_close)
       would never appear in the reindex because it has no data to resample.

    Returns
    -------
    k_daily, d_daily : pd.Series
        K and D values on the same daily DatetimeIndex as ``daily_close``.
        NaN before the oscillator warm-up completes.
        Both series are nullable (all-NaN if fewer than _MIN_WEEKLY_BARS bars).
    """
    null_k = pd.Series(np.nan, index=daily_close.index, dtype=float, name="stochrsi_w_k")
    null_d = pd.Series(np.nan, index=daily_close.index, dtype=float, name="stochrsi_w_d")

    if daily_close.empty:
        return null_k, null_d

    wk = resample_weekly_leakfree(daily_close)
    if len(wk) < _MIN_WEEKLY_BARS:
        return null_k, null_d

    try:
        k_wk, d_wk = _stoch_rsi_kd(wk)
    except Exception:  # noqa: BLE001
        log.warning("stoch_rsi_kd failed on node — stochrsi_w columns set to NaN")
        return null_k, null_d

    # Forward-fill weekly K/D onto the daily index.
    # reindex with method="ffill": each daily row gets the value of the most
    # recently COMPLETED weekly bar (label date <= that daily date).
    # Bars whose label date > the last daily date are absent from the daily
    # index entirely, so no future information leaks backward.
    k_daily = k_wk.reindex(daily_close.index, method="ffill")
    d_daily = d_wk.reindex(daily_close.index, method="ffill")

    k_daily.name = "stochrsi_w_k"
    d_daily.name = "stochrsi_w_d"

    return k_daily, d_daily


# ---------------------------------------------------------------------------
# Washout-active series
# ---------------------------------------------------------------------------


def washout_active_series(
    daily_close: pd.Series,
) -> pd.Series:
    """Compute the registered washout-active boolean, forward-filled to daily.

    Definition (P8, frozen 2026-07-04 — verbatim):
        washout_w = True if StochRSI-K < 20 on >= 2 consecutive completed
        weekly bars within the prior 3 bars (including the current bar).

    The flag is computed on the weekly index, then forward-filled onto the
    daily index with the same convention as ``weekly_stochrsi_kd``: row t
    carries the last completed weekly bar's washout state.

    Returns
    -------
    pd.Series[float]
        Values 0.0 / 1.0 (stored as float for nullable compatibility).
        NaN where K/D are not yet available.
        Daily index = ``daily_close.index``.
    """
    null_out = pd.Series(np.nan, index=daily_close.index, dtype=float, name="washout_w")

    if daily_close.empty:
        return null_out

    wk = resample_weekly_leakfree(daily_close)
    if len(wk) < _MIN_WEEKLY_BARS:
        return null_out

    try:
        k_wk, _ = _stoch_rsi_kd(wk)
    except Exception:  # noqa: BLE001
        log.warning("stoch_rsi_kd failed — washout_w set to NaN")
        return null_out

    n = len(wk)
    k_arr = k_wk.to_numpy(dtype=float)
    in_washout = np.where(np.isnan(k_arr), False, k_arr < WASHOUT_K_THRESHOLD)

    washout_flag = np.full(n, np.nan)  # NaN until oscillator warm-up

    for i in range(n):
        if np.isnan(k_arr[i]):
            continue  # oscillator not yet warm — leave NaN

        start = max(0, i - WASHOUT_LOOK_BACK + 1)
        window = in_washout[start: i + 1]

        # Count maximum run of consecutive True values in the window
        max_run = 0
        cur_run = 0
        for v in window:
            if v:
                cur_run += 1
                max_run = max(max_run, cur_run)
            else:
                cur_run = 0

        washout_flag[i] = 1.0 if max_run >= WASHOUT_CONSEC_BARS else 0.0

    washout_wk = pd.Series(washout_flag, index=wk.index, dtype=float, name="washout_w")

    # Forward-fill onto daily index (same convention as K/D)
    return washout_wk.reindex(daily_close.index, method="ffill")
