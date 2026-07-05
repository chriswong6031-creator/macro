"""Vectorized FULL-HISTORY series primitives for the Entry-Stack Expansion program.

These functions take full OHLCV pd.Series and emit one value per date across
all of history, so a backtest can scan for entry conditions everywhere — not
just today.  They are the series equivalents of the pointwise reads computed
inside engine/stock_technicals.py::snapshot().

LEAK-FREE BY CONSTRUCTION: every output at date t is a function of data at t
and strictly-earlier bars only.  Trailing rolling windows are used throughout;
no centered windows; min_periods is always set so early bars are NaN rather
than silently computed from fewer observations than the window.

The helper functions imported from engine.stock_technicals (bb_bandwidth,
realized_vol, atr, on_balance_volume) and engine.indicators (pct_rank_window,
rolling_slope) are shared with the live snapshot so the series and the
snapshot stay numerically consistent by construction.

DISPLAY/RESEARCH ONLY — this module is pure math; it wires into nothing live.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window, rolling_slope
from engine.stock_technicals import (
    atr,
    bb_bandwidth,
    on_balance_volume,
    realized_vol,
)

# ---------------------------------------------------------------------------
# Volatility-percentile series
# ---------------------------------------------------------------------------

def bbwp_series(
    close: pd.Series,
    n: int = 20,
    k: float = 2.0,
    rank_window: int = 252,
) -> pd.Series:
    """Bollinger Bandwidth Percentile (BBWP) — full-history series, 0-100.

    Percentile rank of the current Bollinger bandwidth within a trailing
    ``rank_window``-bar window.  Mirrors the snapshot ``bbwp`` value computed
    in engine/stock_technicals.py::snapshot() (which takes ``pct_rank_window``
    of ``bb_bandwidth`` and scales by 100).

    Parameters
    ----------
    close:
        Daily close price series (DatetimeIndex).
    n:
        Bollinger-band period (same default as snapshot: 20).
    k:
        Band multiplier (same default as snapshot: 2.0).
    rank_window:
        Trailing window for the percentile rank (same default as snapshot: 252).

    Returns
    -------
    pd.Series of float in [0, 100]; NaN where fewer than ``rank_window // 2``
    observations are available (governed by ``pct_rank_window`` min_periods).
    """
    bbw = bb_bandwidth(close, n=n, k=k)
    return pct_rank_window(bbw, rank_window) * 100.0


def hvp_series(
    close: pd.Series,
    n: int = 20,
    rank_window: int = 252,
) -> pd.Series:
    """Historical Volatility Percentile (HVP) — full-history series, 0-100.

    Percentile rank of the trailing n-bar realized volatility within a
    ``rank_window``-bar window.  Mirrors the snapshot ``hv_pctile`` value in
    engine/stock_technicals.py::snapshot().

    Parameters
    ----------
    close:
        Daily close price series.
    n:
        Realized-vol period (default 20 matching snapshot ``hv20``).
    rank_window:
        Trailing window for the percentile rank (default 252).

    Returns
    -------
    pd.Series of float in [0, 100]; NaN before sufficient history.
    """
    rv = realized_vol(close, n=n)
    return pct_rank_window(rv, rank_window) * 100.0


# ---------------------------------------------------------------------------
# Donchian position series
# ---------------------------------------------------------------------------

def donchian_pos_series(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    n: int = 20,
) -> pd.Series:
    """Donchian-channel position — full-history series, 0..1.

    Vectorized equivalent of the pointwise ``donchian_pos`` in
    engine/stock_technicals.py::snapshot() (lines ~289-294).

    The snapshot reads::

        hh = high.rolling(20, min_periods=20).max()
        ll = low.rolling(20, min_periods=20).min()
        donchian_pos = (close - ll) / (hh - ll)   # guarded against zero range

    This function replicates that exactly over the full history.

    Parameters
    ----------
    close, high, low:
        Aligned daily price series.
    n:
        Donchian channel period (default 20 matching snapshot).

    Returns
    -------
    pd.Series of float in [0, 1]; NaN where fewer than n bars are available
    or where the channel range is zero (high == low throughout the window).
    """
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    rng = (hh - ll).replace(0, np.nan)
    return (close - ll) / rng


# ---------------------------------------------------------------------------
# Relative volume series
# ---------------------------------------------------------------------------

def rel_volume_series(
    volume: pd.Series,
    n: int = 20,
) -> pd.Series:
    """Relative volume — full-history series (ratio, unbounded above 0).

    Volume divided by its trailing n-bar simple moving average.  Mirrors the
    ``rel_volume`` computation in engine/stock_technicals.py::snapshot()::

        vsma = vol.rolling(20, min_periods=10).mean()
        rel_volume = last_vol / last_vsma

    This function emits the ratio for every bar.  Values > 1 mean above-average
    turnover; < 1 means below-average.

    Parameters
    ----------
    volume:
        Daily volume series (should be non-negative).
    n:
        SMA period (default 20).

    Returns
    -------
    pd.Series of float ≥ 0; NaN where fewer than n // 2 observations are
    available or where the SMA is zero.
    """
    vsma = volume.rolling(n, min_periods=n // 2).mean().replace(0, np.nan)
    return volume / vsma


# ---------------------------------------------------------------------------
# OBV slope series
# ---------------------------------------------------------------------------

def obv_slope_series(
    close: pd.Series,
    volume: pd.Series,
    slope_win: int = 20,
) -> pd.Series:
    """OBV (On-Balance Volume) rolling slope — full-history series.

    Applies engine.indicators.rolling_slope over the full OBV series with a
    trailing window of ``slope_win`` bars.  Mirrors the ``obv_slope_up``
    snapshot field (which takes the sign of the last value of this series).

    Parameters
    ----------
    close, volume:
        Aligned daily series.
    slope_win:
        OLS slope window (default 20 matching snapshot).

    Returns
    -------
    pd.Series of float; positive = OBV in a rising trend, negative = falling.
    NaN before ``slope_win`` observations are available.
    """
    obv = on_balance_volume(close, volume)
    return rolling_slope(obv, slope_win)


# ---------------------------------------------------------------------------
# ATR percentile series
# ---------------------------------------------------------------------------

def atr_pct_pctile_series(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 14,
    rank_window: int = 252,
) -> pd.Series:
    """ATR-as-percent-of-price percentile — full-history series, 0-100.

    Computes ATR(n) / close (matching the ``atr_pct`` field in the snapshot)
    then takes the percentile rank within a trailing ``rank_window``-bar window.

    Parameters
    ----------
    high, low, close:
        Aligned daily OHLC series.
    n:
        ATR period (default 14).
    rank_window:
        Trailing window for the percentile rank (default 252).

    Returns
    -------
    pd.Series of float in [0, 100]; NaN before sufficient history.
    """
    a = atr(high, low, close, n=n)
    atr_pct = a / close.replace(0, np.nan)
    return pct_rank_window(atr_pct, rank_window) * 100.0


# ---------------------------------------------------------------------------
# Distance from 52-week high
# ---------------------------------------------------------------------------

def dist_52w_high_series(
    close: pd.Series,
    window: int = 252,
) -> pd.Series:
    """Distance from trailing rolling high — full-history series, values ≤ 0.

    close / rolling_max(window) - 1.

    At a new n-bar high the value is 0.0; below the high it is negative (e.g.
    -0.20 means 20 % below the rolling high).

    Parameters
    ----------
    close:
        Daily close series.
    window:
        Look-back window for the rolling maximum (default 252 ≈ 1 year).

    Returns
    -------
    pd.Series of float in [-1, 0]; NaN before ``window`` observations.
    """
    rolling_max = close.rolling(window, min_periods=window).max()
    return close / rolling_max.replace(0, np.nan) - 1.0


# ---------------------------------------------------------------------------
# Time underwater series
# ---------------------------------------------------------------------------

def time_underwater_series(
    close: pd.Series,
    window: int = 252,
) -> pd.Series:
    """Bars since the trailing ``window``-bar rolling maximum was set — integer ≥ 0.

    At the bar that sets a new rolling high the value is 0; one bar later it
    becomes 1, and so on until a new high is set.  A persistently large value
    means the name has been under its recent peak for a long time.

    Implementation: for each bar t the rolling max is computed over
    [t-window+1, t]; the value is t's positional index minus the positional
    index of the argmax within that window.

    Parameters
    ----------
    close:
        Daily close series.
    window:
        Look-back window (default 252).

    Returns
    -------
    pd.Series of int ≥ 0; NaN before ``window`` observations.
    """
    def _bars_since_max(arr: np.ndarray) -> float:
        if np.isnan(arr).any():
            return np.nan
        return float(len(arr) - 1 - int(np.argmax(arr)))

    return close.rolling(window, min_periods=window).apply(_bars_since_max, raw=True)


# ---------------------------------------------------------------------------
# Amihud illiquidity series  (Entry-Stack Expansion W0 — F4 / S-LQ)
# ---------------------------------------------------------------------------

def amihud_series(
    close: pd.Series,
    volume: pd.Series,
    win: int = 20,
) -> pd.Series:
    """Amihud (2002) ILLIQ — rolling mean of |pct_change| / (close * volume).

    Units: percent-per-dollar-traded, i.e., the daily price-impact ratio
    multiplied by 1e6 is the conventional "ILLIQ" number; this function returns
    the raw ratio.  It is a *relative, cross-sectional* measure — absolute
    values are not comparable across stocks of different prices and share
    counts; use cross-sectional terciles (trailing-year) to classify the
    liquidity regime of a name (per masterplan F4/S-LQ).

    Each daily ratio = |pct_change(close)| / (close * volume).
    The series is then smoothed with a trailing rolling mean of ``win`` bars.
    Bars where volume is zero or close is zero are NaN.

    Parameters
    ----------
    close:
        Daily close price series.
    volume:
        Daily volume series (share count; must be on the same index).
    win:
        Rolling mean window for smoothing (default 20).

    Returns
    -------
    pd.Series of float ≥ 0; NaN for the first ``win`` bars and wherever
    close or volume is zero.

    References
    ----------
    Amihud, Y. (2002). Illiquidity and stock returns: cross-section and
    time-series effects. *Journal of Financial Markets*, 5(1), 31-56.
    """
    dv = (close * volume).replace(0, np.nan)
    raw = close.pct_change().abs() / dv
    return raw.rolling(win, min_periods=win).mean()


# ---------------------------------------------------------------------------
# Corwin-Schultz high-low spread estimator  (Entry-Stack Expansion W0 — F4)
# ---------------------------------------------------------------------------

def corwin_schultz_spread_series(
    high: pd.Series,
    low: pd.Series,
    smooth_win: int = 1,
) -> pd.Series:
    """Corwin-Schultz (2012) two-day high-low bid-ask spread estimator.

    Implements the published formula precisely:

    Let h_t = ln(H_t / L_t) (single-day log HL ratio).
    Let h_{t,t-1} = ln(max(H_t, H_{t-1}) / min(L_t, L_{t-1})) (two-day span).

    beta_t = h_{t-1}^2 + h_t^2   (sum of squared single-day ratios)
    gamma_t = h_{t,t-1}^2         (squared two-day-span ratio)
    alpha_t = (sqrt(2*beta_t) - sqrt(beta_t)) / (3 - 2*sqrt(2))
              - sqrt(gamma_t / (3 - 2*sqrt(2)))

    Per the paper, negative alpha is floored at 0 before computing the spread.
    spread_t = 2*(exp(alpha_t) - 1) / (1 + exp(alpha_t))

    This is a microstructure spread proxy requiring only daily OHLC; it
    estimates the effective bid-ask spread (as a fraction of mid-price).

    Parameters
    ----------
    high, low:
        Daily high and low price series (aligned, DatetimeIndex).
    smooth_win:
        If > 1, apply a trailing rolling mean of this width to the raw
        spread series.  Default 1 (no smoothing).

    Returns
    -------
    pd.Series of float in [0, 1); NaN at bar 0 (two-day window requires
    the previous bar) and wherever high or low are missing/zero.

    References
    ----------
    Corwin, S. A., & Schultz, P. (2012). A simple way to estimate bid-ask
    spreads from daily high and low prices. *Journal of Finance*, 67(2),
    719-760.
    """
    _k = 3.0 - 2.0 * np.sqrt(2.0)  # (3 - 2*sqrt(2)) ≈ 0.1716

    log_hl = np.log(high / low.replace(0, np.nan))  # h_t

    # beta: sum of h_{t-1}^2 + h_t^2 over consecutive pairs
    beta = log_hl.shift(1) ** 2 + log_hl ** 2

    # gamma: squared two-day-span log HL ratio
    two_day_high = pd.concat([high, high.shift(1)], axis=1).max(axis=1)
    two_day_low = pd.concat([low, low.shift(1)], axis=1).min(axis=1)
    log_hl2 = np.log(two_day_high / two_day_low.replace(0, np.nan))
    gamma = log_hl2 ** 2

    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _k - np.sqrt(gamma / _k)
    alpha = alpha.clip(lower=0.0)  # floor at 0 per paper convention

    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))

    if smooth_win > 1:
        spread = spread.rolling(smooth_win, min_periods=smooth_win).mean()

    return spread


# ---------------------------------------------------------------------------
# Undercut-and-Rally event detector  (Entry-Stack Expansion W0 — F2 / S-UR)
# FROZEN DEFINITION — no builder discretion (masterplan section 3 F2)
# ---------------------------------------------------------------------------

def undercut_rally_events(
    close: pd.Series,
    low: pd.Series | None = None,
    high: pd.Series | None = None,
    n: int = 21,
    k: int = 3,
    atr_n: int = 14,
) -> pd.DataFrame:
    """Undercut-and-Rally (spring reclaim) events — FROZEN DEFINITION.

    Implements the exact definition from masterplan section 3 F2 verbatim.
    DO NOT alter the undercut/depth/reclaim logic without a new masterplan
    ruling — this is a pre-registered frozen spec.

    **Definition (verbatim from masterplan F2):**

    rolling_low = close.shift(1).rolling(N).min()   (strictly prior, no pivot
        lookahead; N ∈ {21, 63}, default 21).

    Undercut condition:
        - When high and low are provided (H/L panel):
          ``low < rolling_low`` on the undercut bar.
        - Close-only panel (no H/L):
          ``close < rolling_low`` on the undercut bar.

    Depth arm (at least one must be satisfied; mode is panel-determined):
        - H/L panel:  undercut_depth = (rolling_low - low_at_undercut_bar)
                      must be >= 1.0 * ATR14 (ATR multiplier frozen at 1.0).
        - Close-only: depth = (rolling_low - close_at_undercut_bar)
                      must be >= 2% of rolling_low.
        Both modes are never mixed; the presence of `low` selects the mode.

    Reclaim:
        close > broken_rolling_low_value on any of the NEXT k bars
        (default k=3), evaluated bar-by-bar.  No same-bar fill: the event
        fires on the RECLAIM BAR, not the undercut bar.

    Episode continuation (emergent, not an explicit dedup rule):
        After a qualifying undercut, the scanner seeks a reclaim on the next k
        bars.  If no reclaim is found within k bars, the episode expires and
        the scanner advances one bar from the original undercut.  Because
        rolling_low = close.shift(1).rolling(N).min() now includes the prior
        sub-level closes, the frozen rolling low is lower, and later re-undercuts
        typically fail the depth gate — so a single flush usually produces at
        most one event.  This is an emergent consequence of the frozen rolling-low
        definition (masterplan F2), not an explicitly enforced dedup rule.

    Parameters
    ----------
    close:
        Daily close price series (DatetimeIndex).
    low:
        Daily low series.  If None, close-only mode is used.
    high:
        Daily high series.  Required for ATR14 in H/L mode; ignored in
        close-only mode.  May be None when ``low`` is None.
    n:
        Rolling lookback window for the prior low (default 21).
    k:
        Maximum bars from undercut bar to reclaim bar (default 3; the reclaim
        bar must occur within the next k bars inclusive; bar k+1 does NOT fire).
    atr_n:
        ATR period (default 14).  Used only in H/L mode.

    Returns
    -------
    pd.DataFrame with the same DatetimeIndex as ``close``, columns:
        event (bool):       True on the reclaim bar.
        undercut_date:      Date of the first qualifying undercut bar in the
                            episode; NaT where event is False.
        broken_level:       rolling_low value at the undercut bar; NaN where
                            event is False.
        depth_frac:         (rolling_low - bar_low_or_close) / rolling_low at
                            the undercut bar; NaN where event is False.
    """
    hl_mode = low is not None
    if hl_mode and high is None:
        raise ValueError(
            "H/L mode requires both low and high (ATR14 depth arm); "
            "pass high, or use close-only mode by omitting low"
        )
    idx = close.index
    n_bars = len(close)

    # --- rolling prior low (strictly prior: shift(1) then rolling) ---
    rolling_low = close.shift(1).rolling(n, min_periods=n).min()

    # --- ATR for H/L mode depth gate ---
    if hl_mode:
        _atr_series = atr(high, low, close, n=atr_n)
    else:
        _atr_series = None

    # Pre-allocate output arrays.
    event_arr = np.zeros(n_bars, dtype=bool)
    undercut_date_arr = [pd.NaT] * n_bars
    broken_level_arr = np.full(n_bars, np.nan)
    depth_frac_arr = np.full(n_bars, np.nan)

    close_vals = close.values.astype(float)
    rl_vals = rolling_low.values.astype(float)
    low_vals = low.values.astype(float) if hl_mode else None
    atr_vals = _atr_series.values.astype(float) if hl_mode else None

    i = 0
    while i < n_bars:
        rl = rl_vals[i]
        if np.isnan(rl):
            i += 1
            continue

        # Check undercut
        if hl_mode:
            undercut = low_vals[i] < rl
        else:
            undercut = close_vals[i] < rl

        if not undercut:
            i += 1
            continue

        # Depth gate
        if hl_mode:
            depth = rl - low_vals[i]
            threshold = atr_vals[i] * 1.0
            valid_depth = (not np.isnan(threshold)) and (depth >= threshold)
            depth_frac = depth / rl if rl != 0 else np.nan
        else:
            depth = rl - close_vals[i]
            threshold = 0.02 * rl
            valid_depth = depth >= threshold
            depth_frac = depth / rl if rl != 0 else np.nan

        if not valid_depth:
            i += 1
            continue

        # Episode opened: record the first qualifying undercut bar
        episode_undercut_idx = i
        broken_lv = rl
        ep_depth_frac = depth_frac
        ep_undercut_date = idx[i]

        # Look for reclaim on the next k bars
        reclaim_found = False
        for j in range(i + 1, min(i + k + 1, n_bars)):
            if close_vals[j] > broken_lv:
                # Event fires on reclaim bar j
                event_arr[j] = True
                undercut_date_arr[j] = ep_undercut_date
                broken_level_arr[j] = broken_lv
                depth_frac_arr[j] = ep_depth_frac
                reclaim_found = True
                # Skip past the reclaim bar to avoid re-processing
                i = j + 1
                break

        if not reclaim_found:
            # No reclaim within k bars — episode expires; advance past undercut
            i = episode_undercut_idx + 1

    return pd.DataFrame(
        {
            "event": event_arr,
            "undercut_date": pd.to_datetime(undercut_date_arr),
            "broken_level": broken_level_arr,
            "depth_frac": depth_frac_arr,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Pocket-pivot events  (DORMANT — appendix-locked, masterplan section 3 D1)
# ---------------------------------------------------------------------------

def pocket_pivot_events(
    close: pd.Series,
    volume: pd.Series,
    base_win: int = 10,
) -> pd.DataFrame:
    """Pocket-pivot volume thrust events.

    **DORMANT — appendix-locked per masterplan section 3 D1.**
    This function is implemented but NOT consumed by any live or study path
    until the esx_appendix family unlocks (after F-tier verdicts, W4 earliest).
    Calling it in production code before unlock is a spec violation.

    A pocket pivot fires on a day when:
    - Volume exceeds the maximum down-day volume over the prior ``base_win`` bars
      (the published Kacher-Morales "pocket pivot" criterion).
    - The close is above the close ``base_win`` bars ago (rudimentary base check).

    Parameters
    ----------
    close:
        Daily close price series.
    volume:
        Daily volume series (aligned).
    base_win:
        Look-back for the max down-day volume reference (default 10).

    Returns
    -------
    pd.DataFrame indexed by date with column ``event`` (bool).
    """
    # Down-day volume: volume on bars where close fell vs prior close
    price_change = close.diff()
    down_vol = volume.where(price_change < 0, other=np.nan)
    max_down_vol = down_vol.rolling(base_win, min_periods=1).max()

    volume_thrust = volume > max_down_vol
    above_base = close > close.shift(base_win)

    event = volume_thrust & above_base

    return pd.DataFrame({"event": event.fillna(False).astype(bool)}, index=close.index)


# ---------------------------------------------------------------------------
# Gap-and-hold events  (DORMANT — appendix-locked, masterplan section 3 D2)
# ---------------------------------------------------------------------------

def gap_hold_events(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    hold_bars: int = 2,
) -> pd.DataFrame:
    """Gap-and-hold (breakaway gap holding ≥ hold_bars closes) events.

    **DORMANT — appendix-locked per masterplan section 3 D2.**
    This function is implemented but NOT consumed by any live or study path
    until the esx_appendix family unlocks (W4 earliest).  Requires ``open``
    series; in the baskets panel this is only available from 2014 onward.
    Ex-dividend caution applies: large gaps may be dividend-driven, not
    breakaway gaps; upstream callers should screen for div-adjusted vs
    raw open if applicable.

    A gap-and-hold fires at the bar that completes hold_bars consecutive
    closes all above the prior day's high (the "gap hold" condition):
    - Gap bar: open > prior high (breakaway gap up).
    - Subsequent hold_bars closes must all remain > prior high of the gap bar.
    The event fires on the bar that completes the hold sequence.

    Parameters
    ----------
    open_:
        Daily open price series.
    high, low, close:
        Aligned OHLC series.
    hold_bars:
        Number of consecutive hold closes required (default 2).

    Returns
    -------
    pd.DataFrame indexed by date with column ``event`` (bool).
    """
    prior_high = high.shift(1)
    gap_up = open_ > prior_high  # gap bar condition

    # For each bar t, check if t was a gap bar and the next hold_bars closes
    # are all above prior_high of the gap bar.  We detect the completed hold.
    event = pd.Series(False, index=close.index)
    gap_level = np.where(gap_up.values, prior_high.values, np.nan)

    close_vals = close.values.astype(float)
    n = len(close_vals)

    for i in range(n):
        lv = gap_level[i]
        if np.isnan(lv):
            continue
        # Check the next hold_bars closes all hold above lv
        end = i + hold_bars
        if end >= n:
            continue
        if all(close_vals[i + d] > lv for d in range(1, hold_bars + 1)):
            event.iloc[i + hold_bars] = True

    return pd.DataFrame({"event": event.astype(bool)}, index=close.index)
