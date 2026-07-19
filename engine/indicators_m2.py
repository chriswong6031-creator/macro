"""engine/indicators_m2.py — VWAP / Anchored VWAP / Volume Profile + POC signals.

DAILY-BAR APPROXIMATION NOTICE
-------------------------------
All computations in this module use typical price TP = (high + low + close) / 3.
This is a daily-bar approximation — NOT intraday-true VWAP.  The repo's OHLCV
store has no intraday data and ``open`` is a prev-close proxy.  Intraday-true
VWAP is undefined without tick or minute-level data; the daily approximation is
the market-convention proxy used in academic and practitioner literature (e.g.
Berkowitz, Logue & Noser 1988).

TIMEFRAME CONTRACT (important — read before editing)
-----------------------------------------------------
The miner calls each signal fn with the OHLCV frame for the leg's timeframe
already resampled: daily bars for a "D" leg.  All M2 families are DAILY-ONLY
legs — they are NOT added to ``engine.tech_confluence.W_FAMILIES``:

- ``vwap_events``:  week_anchored_vwap groups by calendar week INTERNALLY
  (similar to how stoch_rsi_cross_up_2w resamples internally); no W leg.
- ``volume_profile_events``: rolling_poc requires contiguous daily bars to
  maintain a stable price grid; a "weekly of a rolling POC" is meaningless.

Event semantics: an event fires (1.0) only on the FIRST bar of the condition
(entry-bar discipline — condition true now AND NOT true on the prior bar); all
other bars are 0.0.  PIT-clean: no look-ahead, no centered windows.

HONESTY CONTRACT
----------------
Display-only / research.  Deterministic standard TA math — no LLM-originated
signals, scores, or escalations.  No "validated" claim in any user-facing string.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross helpers — NaN-safe, warm-up-safe entry events
# (copied in idiom from engine.momentum_events)
# ---------------------------------------------------------------------------
# A cross fires 1.0 only on the bar where `a` moves strictly above (below) `b`
# AND the PRIOR bar was on the opposite side with VALID (non-NaN) values.
# NaN comparisons are False in pandas, so the shifted-prior term is False during
# indicator warm-up — the first valid indicator bar can NEVER register a phantom
# cross.  `b` may be a scalar threshold or another Series.


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


# ---------------------------------------------------------------------------
# Typical price
# ---------------------------------------------------------------------------

def _tp(df: pd.DataFrame) -> pd.Series:
    """Typical price = (high + low + close) / 3."""
    return (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3.0


# ---------------------------------------------------------------------------
# Pure indicator calculations
# ---------------------------------------------------------------------------

def rolling_vwap(df: pd.DataFrame, *, n: int = 20) -> pd.Series:
    """Rolling VWAP over a trailing window of n daily bars.

    Computes Σ(TP·V) / Σ(V) over the trailing n bars with min_periods=n
    (NaN during warm-up).  Zero total volume in the window → NaN.

    Parameters
    ----------
    df : DataFrame with columns close/high/low/volume and a DatetimeIndex.
    n  : int, trailing window length (default 20).

    Returns
    -------
    pd.Series aligned to df.index, dtype float.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    tp = _tp(df)
    vol = df["volume"].astype(float)
    tpv_sum = (tp * vol).rolling(n, min_periods=n).sum()
    v_sum = vol.rolling(n, min_periods=n).sum()
    result = tpv_sum / v_sum
    # Zero cumulative volume in window → NaN (division by zero is already NaN via pandas)
    result[v_sum == 0] = np.nan
    result.name = "rolling_vwap"
    return result


def week_anchored_vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP within each calendar week, anchored at each week's first session.

    Groups bars by ``df.index.to_period("W-FRI")`` and computes cumulative
    Σ(TP·V) / Σ(V) within each week, resetting at the first session of each
    week.  The first session of a week has VWAP = that bar's TP (if volume > 0).
    Zero cumulative volume within a week → NaN.  Non-DatetimeIndex → all-NaN.

    ASSUMES ascending, deduplicated daily bars (the house store guarantee —
    engine.lab sorts+dedups on load): the groupby-cumsum follows ROW order, so
    a non-monotonic frame would silently produce wrong cumulatives. Callers
    outside the store path must sort_index() first.

    Note: week_anchored_vwap groups by calendar week internally (similar to how
    stoch_rsi_cross_up_2w resamples internally); this signal is registered as a
    daily-only leg and must NOT get a weekly leg in the miner.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(np.nan, index=df.index, name="week_anchored_vwap")

    tp = _tp(df)
    vol = df["volume"].astype(float)
    tpv = tp * vol

    # Group by W-FRI period and compute cumulative sums
    period_labels = df.index.to_period("W-FRI")
    cum_tpv = tpv.groupby(period_labels).cumsum()
    cum_vol = vol.groupby(period_labels).cumsum()

    result = cum_tpv / cum_vol
    result[cum_vol == 0] = np.nan
    result.name = "week_anchored_vwap"
    return result


def anchored_vwap(df: pd.DataFrame, anchor: int | str | pd.Timestamp) -> pd.Series:
    """Cumulative VWAP anchored at a specific bar, inclusive.

    Computes cumulative Σ(TP·V) / Σ(V) from the anchor bar onward (inclusive).
    Values strictly before the anchor bar are NaN.  Zero cumulative volume → NaN.

    Parameters
    ----------
    df     : DataFrame with columns close/high/low/volume and a DatetimeIndex.
    anchor : int (positional index), str, or pd.Timestamp.  str/Timestamp is
             resolved via ``index.searchsorted(ts, side="left")`` — the first
             bar at or after the given timestamp.  Out-of-range → all-NaN.

    Returns
    -------
    pd.Series aligned to df.index, dtype float.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    n = len(df)
    result = pd.Series(np.nan, index=df.index, name="anchored_vwap", dtype=float)

    if n == 0:
        return result

    # Resolve anchor to integer positional index
    if isinstance(anchor, (str, pd.Timestamp)):
        ts = pd.Timestamp(anchor)
        if isinstance(df.index, pd.DatetimeIndex):
            pos = df.index.searchsorted(ts, side="left")
        else:
            return result  # non-datetime index and timestamp anchor → all-NaN
    else:
        pos = int(anchor)

    if pos < 0 or pos >= n:
        return result  # out-of-range

    tp = _tp(df)
    vol = df["volume"].astype(float)
    tpv = tp * vol

    # Cumulative from anchor bar
    cum_tpv = tpv.iloc[pos:].cumsum()
    cum_vol = vol.iloc[pos:].cumsum()
    avwap = cum_tpv / cum_vol
    avwap[cum_vol == 0] = np.nan

    result.iloc[pos:] = avwap.values
    return result


def earnings_proxy_anchor(df: pd.DataFrame, *, lookback: int = 63) -> int | None:
    """Positional index of the max-volume bar within the trailing lookback bars.

    This is an OHLCV-only PROXY for the earnings date (the quarter's top-volume
    session), since the repo has no direct earnings-date data.  The proxy is the
    maximum-volume bar in the trailing window, which often (but not always)
    corresponds to the earnings-driven volume spike.

    Parameters
    ----------
    df       : DataFrame with a volume column.
    lookback : int, number of trailing bars to scan (default 63, ~1 quarter).
               Inclusive of the last bar.

    Returns
    -------
    int positional index of the max-volume bar, or None if len(df) == 0.
    Ties are broken by recency (the most recent max-volume bar is returned).
    """
    if len(df) == 0:
        return None
    # Trailing lookback bars (inclusive of the last bar).
    start = max(0, len(df) - lookback)
    window_vol = df["volume"].astype(float).values[start:]
    # np.argmax returns the FIRST occurrence on ties, but the proxy convention is
    # ties → most recent, so take the LAST index of the max explicitly.
    max_val = window_vol.max()
    rel_idx = int(np.flatnonzero(window_vol == max_val)[-1])
    return start + rel_idx


def volume_profile(
    df: pd.DataFrame, *, window: int = 126, bins: int = 24
) -> dict | None:
    """Volume profile over the last window bars.

    Computes a price histogram weighted by volume (each bar's full volume
    assigned to the bin containing its typical price).

    Parameters
    ----------
    df     : DataFrame with columns high/low/volume and a DatetimeIndex.
    window : int, number of trailing bars to use (all bars if fewer).
    bins   : int, number of price bins (default 24).

    Returns
    -------
    dict with keys:
        poc           : float — midpoint of the max-volume bin (Point of Control)
        va_low        : float — lower outer EDGE of the Value Area
        va_high       : float — upper outer EDGE of the Value Area
        total_volume  : float — total volume in the window
        bin_edges     : list[float] — len bins+1
        bin_volumes   : list[float] — len bins
        window_used   : int — number of bars actually used

    Returns None if fewer than 20 bars available or total volume <= 0.

    Value Area: start at the POC bin, greedily add the adjacent candidate
    (the one just above the current included span vs the one just below) with
    the larger volume — tie → the bin ABOVE — until included volume >= 0.70 × total.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    n = len(df)
    slice_n = min(n, window)
    if slice_n < 20:
        return None

    sl = df.iloc[-slice_n:]
    tp = _tp(sl)
    vol = sl["volume"].astype(float)

    lo = sl["low"].astype(float).min()
    hi = sl["high"].astype(float).max()
    total_vol = float(vol.sum())

    if total_vol <= 0:
        return None

    if lo == hi:
        # Degenerate: all bars at same price → one bin
        # Still need to return a valid structure
        edges = np.linspace(lo, lo + 1e-8, bins + 1)
    else:
        edges = np.linspace(lo, hi, bins + 1)

    # Digitize each bar's TP into bin index [0, bins-1]
    # np.digitize returns 1-based, so subtract 1 and clip to [0, bins-1]
    bin_idx = np.digitize(tp.values, edges) - 1
    bin_idx = np.clip(bin_idx, 0, bins - 1)

    # Volume-weighted histogram.  np.bincount sums the weights in ascending-index
    # order, byte-identical to the equivalent sequential-accumulation loop.
    bin_volumes = np.bincount(bin_idx, weights=vol.values, minlength=bins)

    # POC: max-volume bin; ties → lower-price bin (first occurrence)
    poc_bin = int(np.argmax(bin_volumes))
    poc = float((edges[poc_bin] + edges[poc_bin + 1]) / 2.0)

    # Value Area: greedy expansion from POC bin
    lo_bin = poc_bin
    hi_bin = poc_bin
    included_vol = bin_volumes[poc_bin]
    target = 0.70 * total_vol

    while included_vol < target:
        # Candidate bins: one above current span, one below
        can_above = hi_bin + 1
        can_below = lo_bin - 1
        above_vol = bin_volumes[can_above] if can_above < bins else -1.0
        below_vol = bin_volumes[can_below] if can_below >= 0 else -1.0

        if above_vol < 0 and below_vol < 0:
            break  # no more candidates

        # Tie → prefer ABOVE
        if above_vol >= below_vol:
            hi_bin = can_above
            included_vol += bin_volumes[can_above]
        else:
            lo_bin = can_below
            included_vol += bin_volumes[can_below]

    va_low = float(edges[lo_bin])
    va_high = float(edges[hi_bin + 1])

    return {
        "poc": poc,
        "va_low": va_low,
        "va_high": va_high,
        "total_volume": total_vol,
        "bin_edges": edges.tolist(),
        "bin_volumes": bin_volumes.tolist(),
        "window_used": slice_n,
    }


def rolling_poc(df: pd.DataFrame, *, window: int = 126, bins: int = 24) -> pd.Series:
    """Per-bar POC of the volume profile over the PRIOR window bars.

    For each bar t, computes the POC from bars [t-window, t-1], EXCLUDING bar t
    (PIT-safe for retest events).  NaN while fewer than ``window`` prior bars exist.

    Parameters
    ----------
    df     : DataFrame with columns high/low/volume and a DatetimeIndex.
    window : int, number of prior bars in each window (default 126).
    bins   : int, number of price bins per profile (default 24).

    Returns
    -------
    pd.Series aligned to df.index, dtype float, NaN during warm-up.

    Performance: O(n × window) — one volume-weighted bincount per bar over the
    prior-window slice.  ~30 ms for a 2,500-bar frame.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    n = len(df)
    result = np.full(n, np.nan, dtype=float)

    if n == 0:
        return pd.Series(result, index=df.index, name="rolling_poc")

    tp_arr = _tp(df).values
    vol_arr = df["volume"].astype(float).values
    low_arr = df["low"].astype(float).values
    high_arr = df["high"].astype(float).values

    for t in range(window, n):
        sl_tp = tp_arr[t - window:t]   # prior window, excludes t
        sl_vol = vol_arr[t - window:t]
        sl_lo = low_arr[t - window:t]
        sl_hi = high_arr[t - window:t]

        total_vol = sl_vol.sum()
        if total_vol <= 0:
            continue

        lo = sl_lo.min()
        hi = sl_hi.max()

        if lo == hi:
            # Degenerate: all same price → POC = that price
            result[t] = lo
            continue

        edges = np.linspace(lo, hi, bins + 1)
        bin_idx = np.digitize(sl_tp, edges) - 1
        bin_idx = np.clip(bin_idx, 0, bins - 1)

        # Volume-weighted histogram via bincount (byte-identical to the
        # sequential-accumulation loop, ~2.7× faster on a 2,500-bar frame).
        bin_volumes = np.bincount(bin_idx, weights=sl_vol, minlength=bins)

        poc_bin = int(np.argmax(bin_volumes))
        result[t] = float((edges[poc_bin] + edges[poc_bin + 1]) / 2.0)

    return pd.Series(result, index=df.index, name="rolling_poc")


# ---------------------------------------------------------------------------
# Signal functions — vwap_events family
# ---------------------------------------------------------------------------

def _rolling_anchor_argmax(vol_arr: np.ndarray, lookback: int) -> np.ndarray:
    """For each position t, return the positional index of the max-volume bar
    in the window [max(0, t-lookback+1), t], with ties → most recent.

    O(n) via a monotonic-decreasing deque of candidate indices.  Rightmost-tie
    (most-recent) semantics: when a new bar equals the current running max, older
    equal-valued candidates are evicted so the newer index survives at the front
    — the front of the deque is therefore always the *most recent* max of the
    window.  (A deque that evicts only strictly-smaller candidates keeps the
    LEFTMOST max, which is the wrong tie-break here; this is exercised by the
    tie-dense equivalence test in tests/test_indicators_m2.py.)

    Verified equivalent to a direct O(n·lookback) scan (0 mismatches over
    tie-dense seeded frames, incl. small-integer volumes with dense ties).
    """
    n = len(vol_arr)
    result = np.full(n, -1, dtype=np.intp)
    dq: deque[int] = deque()  # indices, values strictly decreasing front→back
    for t in range(n):
        # Drop indices that have fallen out of the trailing window.
        while dq and dq[0] < t - lookback + 1:
            dq.popleft()
        # Evict every back candidate <= current so the most-recent max wins ties.
        while dq and vol_arr[dq[-1]] <= vol_arr[t]:
            dq.pop()
        dq.append(t)
        result[t] = dq[0]
    return result


def _earnings_proxy_avwap_series(
    df: pd.DataFrame, *, lookback: int = 63, min_anchor_age: int = 5
) -> pd.Series:
    """Per-bar AVWAP from the rolling earnings-proxy anchor (trailing max-volume bar).

    For each bar t: anchor_t = max-volume bar position in the trailing `lookback`
    bars ending at t (ties → most recent); value = cumulative TP·V / V from
    anchor_t through t.

    NaN GAP DISCIPLINE (anchor-jump guard) — the value is NaN unless BOTH:
      - anchor age (t - anchor_t) >= min_anchor_age (a fresh anchor's AVWAP is
        just its own TP — a trivially crossable line), AND
      - the anchor position has been UNCHANGED for at least min_anchor_age
        consecutive bars ending at t.
    The second condition matters when the reigning max-volume bar drops out of
    the window and the anchor jumps BACKWARD to an older bar: the AVWAP series
    is discontinuous at that jump, and a "cross" fired against the pre-jump
    prior-bar value would be an artifact of the anchor change, not of price.
    Opening a min_anchor_age NaN gap on EVERY anchor change means the cross
    helpers' valid-prior-bar guard can never fire through a discontinuity —
    the same warm-up discipline as indicator birth.
    """
    n = len(df)
    tp = _tp(df).values
    vol = df["volume"].astype(float).values
    anchor_pos = _rolling_anchor_argmax(vol, lookback)

    # Float64 prefix sums (length n+1, pv[k]/vsum[k] = sum over bars i < k) turn
    # each anchor→t cumulative VWAP into two O(1) subtractions:
    #   avwap_t = (pv[t+1] - pv[ap]) / (vsum[t+1] - vsum[ap])
    # replacing the per-t O(lookback) slice-and-sum with an O(n) sweep.  Not
    # parity-pinned; verified equivalent to the slice form to < 1e-9 abs.
    pv = np.concatenate(([0.0], np.cumsum(tp * vol)))
    vsum = np.concatenate(([0.0], np.cumsum(vol)))

    avwap_arr = np.full(n, np.nan, dtype=float)
    run = 0  # consecutive bars (ending at t) with an unchanged anchor position
    for t in range(n):
        run = run + 1 if (t > 0 and anchor_pos[t] == anchor_pos[t - 1]) else 1
        ap = anchor_pos[t]
        if (t - ap) < min_anchor_age or run < min_anchor_age:
            continue
        cum_vol = vsum[t + 1] - vsum[ap]
        if cum_vol > 0:
            avwap_arr[t] = (pv[t + 1] - pv[ap]) / cum_vol
    return pd.Series(avwap_arr, index=df.index, name="avwap_earnings_proxy")


def price_reclaims_avwap_earnings(
    df: pd.DataFrame, *, lookback: int = 63, min_anchor_age: int = 5
) -> pd.Series:
    """AVWAP earnings-proxy bullish reclaim event.

    For each bar t:
      - anchor_t = max-volume bar position in trailing lookback bars ending at t
                   (ties → most recent)
      - avwap_t  = cumulative TP·V / V from anchor_t through t
      - Series is NaN where anchor age (t - anchor_t) < min_anchor_age

    Fire: close crosses strictly ABOVE the avwap series with the valid-opposite-
    prior-bar guard (warm-up safe — NaN prior avwap or close → no fire).

    The AVWAP series carries a NaN gap for min_anchor_age bars after EVERY
    anchor change (fresh anchor or backward jump) — see
    _earnings_proxy_avwap_series for the discipline and why.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    avwap = _earnings_proxy_avwap_series(
        df, lookback=lookback, min_anchor_age=min_anchor_age
    )
    close_s = df["close"].astype(float)
    return _cross_above(close_s, avwap)


def price_loses_avwap_earnings(
    df: pd.DataFrame, *, lookback: int = 63, min_anchor_age: int = 5
) -> pd.Series:
    """AVWAP earnings-proxy bearish loss event.

    Symmetric counterpart to price_reclaims_avwap_earnings (same NaN-gap
    discipline on every anchor change — see _earnings_proxy_avwap_series).
    Fire: close crosses strictly BELOW the AVWAP series.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    avwap = _earnings_proxy_avwap_series(
        df, lookback=lookback, min_anchor_age=min_anchor_age
    )
    close_s = df["close"].astype(float)
    return _cross_below(close_s, avwap)


def price_above_vwap_w(df: pd.DataFrame) -> pd.Series:
    """State: close > week-anchored VWAP.

    1.0 where close > week_anchored_vwap, else 0.0.
    NaN VWAP → 0.0 (treat as not above).

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    avwap = week_anchored_vwap(df)
    close = df["close"].astype(float)
    result = (close > avwap).fillna(False).astype(float)
    result.name = "price_above_vwap_w"
    return result


def price_below_vwap_w(df: pd.DataFrame) -> pd.Series:
    """State: close < week-anchored VWAP.

    1.0 where close < week_anchored_vwap, else 0.0.
    NaN VWAP → 0.0 (treat as not below).

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    avwap = week_anchored_vwap(df)
    close = df["close"].astype(float)
    result = (close < avwap).fillna(False).astype(float)
    result.name = "price_below_vwap_w"
    return result


# ---------------------------------------------------------------------------
# Signal functions — volume_profile_events family
# ---------------------------------------------------------------------------

def poc_retest_hold(
    df: pd.DataFrame, *, window: int = 126, bins: int = 24, tol: float = 0.01
) -> pd.Series:
    """POC retest hold event (bullish: price defends the point of control).

    p = rolling_poc(df, window, bins) — prior-window, PIT-safe (excludes bar t).

    Raw condition C_t:
        (close_{t-1} > p_{t-1})          prior bar was ABOVE POC
        AND (low_t <= p_t * (1 + tol))   current bar touched down to POC ± tol
        AND (close_t > p_t)              current bar closes above POC

    Fire: C_t AND NOT C_{t-1} (entry-bar discipline).  NaN terms → False.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    p = rolling_poc(df, window=window, bins=bins)
    close = df["close"].astype(float)
    low = df["low"].astype(float)

    # Build raw condition with NaN → False
    c_above_prior = (close.shift(1) > p.shift(1)).fillna(False)
    c_touch = (low <= p * (1.0 + tol)).fillna(False)
    c_close_above = (close > p).fillna(False)

    cond = c_above_prior & c_touch & c_close_above
    # Entry-bar discipline: fire only on first bar of condition.
    # Use .astype(bool) before ~ to avoid pandas object-dtype bitwise inversion bug.
    fire = (cond & ~cond.shift(1).fillna(False).astype(bool)).astype(float)
    fire.name = "poc_retest_hold"
    return fire


def poc_retest_fail(
    df: pd.DataFrame, *, window: int = 126, bins: int = 24, tol: float = 0.01
) -> pd.Series:
    """POC retest fail event (bearish: price rejected at the point of control).

    p = rolling_poc(df, window, bins) — prior-window, PIT-safe (excludes bar t).

    Raw condition C_t:
        (close_{t-1} < p_{t-1})          prior bar was BELOW POC
        AND (high_t >= p_t * (1 - tol))  current bar rallied up to POC ± tol
        AND (close_t < p_t)              current bar closes below POC

    Fire: C_t AND NOT C_{t-1} (entry-bar discipline).  NaN terms → False.

    Note: daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP.
    """
    p = rolling_poc(df, window=window, bins=bins)
    close = df["close"].astype(float)
    high = df["high"].astype(float)

    c_below_prior = (close.shift(1) < p.shift(1)).fillna(False)
    c_touch = (high >= p * (1.0 - tol)).fillna(False)
    c_close_below = (close < p).fillna(False)

    cond = c_below_prior & c_touch & c_close_below
    # Entry-bar discipline: use .astype(bool) before ~ to avoid pandas object-dtype bug.
    fire = (cond & ~cond.shift(1).fillna(False).astype(bool)).astype(float)
    fire.name = "poc_retest_fail"
    return fire


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


_VWAP_PROV = "Berkowitz, Logue & Noser (1988) The Total Cost of Transactions on the NYSE"
_VP_PROV = "Steidlmayer, J.P. (1984) Markets and Market Logic"
_NOTES = "Daily-bar approximation over typical price (H+L+C)/3 — not intraday-true VWAP."

SIGNALS: dict[str, dict[str, Any]] = {
    # ---- vwap_events family ------------------------------------------------
    "price_reclaims_avwap_earnings": {
        "fn": price_reclaims_avwap_earnings,
        "kind": "event",
        "family": "vwap_events",
        "direction": +1,
        "default_params": {"lookback": 63, "min_anchor_age": 5},
        "display": _disp(
            "Price reclaims AVWAP from earnings-proxy anchor (quarter's top-volume session)",
            "价格收复财报代理锚点 AVWAP（季度最大成交量日）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "vwap_anchor",
        "role": "trigger",
        "provenance": _VWAP_PROV,
        "actionable_lag": 0,
        "notes": _NOTES,
    },
    "price_loses_avwap_earnings": {
        "fn": price_loses_avwap_earnings,
        "kind": "event",
        "family": "vwap_events",
        "direction": -1,
        "default_params": {"lookback": 63, "min_anchor_age": 5},
        "display": _disp(
            "Price loses AVWAP from earnings-proxy anchor (quarter's top-volume session)",
            "价格跌破财报代理锚点 AVWAP（季度最大成交量日）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "vwap_anchor",
        "role": "trigger",
        "provenance": _VWAP_PROV,
        "actionable_lag": 0,
        "notes": _NOTES,
    },
    "price_above_vwap_w": {
        "fn": price_above_vwap_w,
        "kind": "state",
        "family": "vwap_events",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "Close above week-anchored VWAP",
            "收盘价高于周锚定 VWAP",
        ),
        "glyph": "arrow_up",
        "dependency_family": "vwap_anchor",
        "role": "context",
        "provenance": _VWAP_PROV,
        "actionable_lag": 0,
        "notes": _NOTES,
    },
    "price_below_vwap_w": {
        "fn": price_below_vwap_w,
        "kind": "state",
        "family": "vwap_events",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "Close below week-anchored VWAP",
            "收盘价低于周锚定 VWAP",
        ),
        "glyph": "arrow_down",
        "dependency_family": "vwap_anchor",
        "role": "context",
        "provenance": _VWAP_PROV,
        "actionable_lag": 0,
        "notes": _NOTES,
    },
    # ---- volume_profile_events family --------------------------------------
    "poc_retest_hold": {
        "fn": poc_retest_hold,
        "kind": "event",
        "family": "volume_profile_events",
        "direction": +1,
        "default_params": {"window": 126, "bins": 24, "tol": 0.01},
        "display": _disp(
            "POC retest holds (price defends the point of control)",
            "POC 回踩守稳（价格守住成交量控制点）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "volume_profile",
        "role": "trigger",
        "provenance": _VP_PROV,
        "actionable_lag": 0,
        "notes": _NOTES,
    },
    "poc_retest_fail": {
        "fn": poc_retest_fail,
        "kind": "event",
        "family": "volume_profile_events",
        "direction": -1,
        "default_params": {"window": 126, "bins": 24, "tol": 0.01},
        "display": _disp(
            "POC retest fails (rejected at the point of control)",
            "POC 回踩失守（价格被成交量控制点拒绝）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "volume_profile",
        "role": "trigger",
        "provenance": _VP_PROV,
        "actionable_lag": 0,
        "notes": _NOTES,
    },
}
