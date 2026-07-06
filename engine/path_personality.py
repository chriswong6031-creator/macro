"""Pure path-feature library for the stock-personality program.

DISPLAY-ONLY substrate for stock_personality.v1 chart/microstructure axes;
never scores, sizes, or gates; all features are causal (row t uses only
data <= t).

Provides two public APIs:

    features(df, *, as_of=None) -> dict
        Causal snapshot of every feature as of ``as_of`` (default: last row).
        Cheap: only trailing windows ending at ``as_of`` are computed.
        Includes a ``coverage`` sub-dict.

    feature_series(df) -> pd.DataFrame
        Full causal time-series of the same feature keys.  Used by the Phase-0
        retro study (PIT re-attachment).  Strict leak law: value at row t is
        identical whether or not future rows exist in the input.

Input contract
--------------
``df`` must be a pd.DataFrame indexed by an ascending DatetimeIndex.
Columns must be a subset of {open, high, low, close, volume} (lowercase).
``close`` must always be present.  All other columns are optional; features
that require a missing column return None (snapshot) or NaN (series) without
raising.

Reused helpers
--------------
``engine.entry_primitives.bbwp_series``
``engine.entry_primitives.amihud_series``
``engine.entry_primitives.corwin_schultz_spread_series``

These are imported and called without copying their math.  Do not modify
entry_primitives.py from this module.

``gap_hold_events`` in entry_primitives is appendix-locked DORMANT; the gap
math implemented here (gap_share_252, event_gap_contrib_252) is intentionally
independent and simpler — no dormancy-law breach.

Author: stock-personality W1 builder
Lineage: research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md §3.1 Lane B,
         R-SP4, R-SP5
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.entry_primitives import (
    amihud_series,
    bbwp_series,
    corwin_schultz_spread_series,
)

# ---------------------------------------------------------------------------
# Constants — frozen v1 spec window sizes
# ---------------------------------------------------------------------------

_WIN_TREND_20 = 20
_WIN_TREND_60 = 60
_WIN_TREND_126 = 126
_WIN_SLOPE_STABILITY = 126
_WIN_PULLBACK = 252
_WIN_BREAKOUT = 63
_WIN_BREAKOUT_LOOKBACK = 504
_WIN_BREAKOUT_FWD = 10
_WIN_GAP = 252
_WIN_WICK = 126
_WIN_SHOCK_LOOKBACK = 504
_WIN_SHOCK_STD = 63
_WIN_SHOCK_FWD = 10
_WIN_EXTREME_BAR = 252
_WIN_EXTREME_BAR_NORM = 63
_WIN_ADV = 21
_WIN_AMIHUD = 252
_WIN_CS = 252

_SHOCK_MULT = 2.5
_EXTREME_BAR_MULT = 4.0
_MIN_TREND_COVERAGE = 0.8   # fraction of window required
_MIN_BREAKOUTS = 5           # minimum resolved breakouts for rate
_MIN_SHOCKS = 8              # minimum resolved shocks for half-life

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _has_col(df: pd.DataFrame, col: str) -> bool:
    return col in df.columns


def _has_ohlc(df: pd.DataFrame) -> bool:
    return all(_has_col(df, c) for c in ("open", "high", "low", "close"))


def _has_hlc(df: pd.DataFrame) -> bool:
    return all(_has_col(df, c) for c in ("high", "low", "close"))


def _has_volume(df: pd.DataFrame) -> bool:
    return _has_col(df, "volume")


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range: max(H-L, |H-prevC|, |L-prevC|)."""
    pc = close.shift(1)
    return pd.concat([
        high - low,
        (high - pc).abs(),
        (low - pc).abs(),
    ], axis=1).max(axis=1)


# ---------------------------------------------------------------------------
# Feature series implementations (causal, vectorized where possible)
# ---------------------------------------------------------------------------


def _trend_persist_series(close: pd.Series, window: int) -> pd.Series:
    """Lag-1 sign-autocorrelation of daily returns over trailing ``window`` bars.

    At bar t: compute daily log-returns over the trailing ``window`` bars;
    return the sign-autocorrelation (fraction of consecutive-pair sign matches
    minus fraction of mismatches).  NaN if fewer than window * 0.8 valid pairs.

    Range: [-1, 1].  Positive = momentum (returns trend), negative = reversal.
    """
    min_obs = int(window * _MIN_TREND_COVERAGE)

    lr = np.log(close / close.shift(1))

    def _autocorr_sign(arr: np.ndarray) -> float:
        valid = arr[~np.isnan(arr)]
        if len(valid) < min_obs:
            return np.nan
        signs = np.sign(valid)
        # consecutive pairs: (s_t * s_{t-1}) == 1 means same sign
        pairs = signs[1:] * signs[:-1]
        n_pairs = len(pairs)
        if n_pairs == 0:
            return np.nan
        return float(np.sum(pairs) / n_pairs)

    return lr.rolling(window, min_periods=min_obs).apply(_autocorr_sign, raw=True)


def _slope_stability_126_series(close: pd.Series) -> pd.Series:
    """Fraction of 126 trailing bars where the 20d slope has same sign as 126d slope.

    Uses linear regression slope (rolling OLS via numpy polyfit inside apply).
    Causal: at bar t, only data <= t used.

    Both slopes computed on log-close to make slope scale-free.
    """
    log_c = np.log(close.replace(0, np.nan))
    win_long = _WIN_SLOPE_STABILITY   # 126
    win_short = _WIN_TREND_20         # 20

    def _frac_agree(arr: np.ndarray) -> float:
        # arr is the trailing 126 log-close values (raw=True)
        if np.isnan(arr).any():
            return np.nan
        n = len(arr)
        # 126d slope
        x_long = np.arange(n, dtype=float)
        slope_long = np.polyfit(x_long, arr, 1)[0]
        # Roll through 20d windows within arr
        agree = 0
        count = 0
        for end in range(win_short, n + 1):
            seg = arr[end - win_short: end]
            if np.isnan(seg).any():
                continue
            x_s = np.arange(win_short, dtype=float)
            s20 = np.polyfit(x_s, seg, 1)[0]
            agree += int(np.sign(s20) == np.sign(slope_long))
            count += 1
        if count == 0:
            return np.nan
        return float(agree / count)

    return log_c.rolling(win_long, min_periods=win_long).apply(_frac_agree, raw=True)


def _pullback_series(close: pd.Series) -> pd.DataFrame:
    """Pullback median and p90 over trailing 252 bars.

    Drawdown is computed vs the expanding peak within the 252-bar window.
    Trough depths = local minima of the drawdown series below -1%.
    Returns columns: pullback_median_252, pullback_p90_252 (positive fractions).
    NaN if no troughs found.
    """
    win = _WIN_PULLBACK  # 252

    def _pullback_stats(arr: np.ndarray):
        if np.isnan(arr).any():
            return (np.nan, np.nan)
        # expanding peak within window
        peaks = np.maximum.accumulate(arr)
        dd = arr / peaks - 1.0   # <= 0
        # find local minima below -1% threshold
        troughs = []
        n = len(dd)
        for i in range(1, n - 1):
            if dd[i] < -0.01 and dd[i] <= dd[i - 1] and dd[i] <= dd[i + 1]:
                troughs.append(-dd[i])  # store as positive depth
        # also catch edge case: last bar can be a trough
        if n > 1 and dd[-1] < -0.01 and dd[-1] <= dd[-2]:
            troughs.append(-dd[-1])
        if len(troughs) == 0:
            return (np.nan, np.nan)
        troughs_arr = np.array(troughs)
        return (float(np.median(troughs_arr)), float(np.percentile(troughs_arr, 90)))

    # Use rolling apply returning a scalar; compute both stats in one pass
    # by splitting into two series (pandas rolling apply returns one value)
    median_vals = np.full(len(close), np.nan)
    p90_vals = np.full(len(close), np.nan)

    close_vals = close.values.astype(float)
    n_total = len(close_vals)

    for t in range(win - 1, n_total):
        arr = close_vals[t - win + 1: t + 1]
        med, p90 = _pullback_stats(arr)
        median_vals[t] = med
        p90_vals[t] = p90

    return pd.DataFrame(
        {"pullback_median_252": median_vals, "pullback_p90_252": p90_vals},
        index=close.index,
    )


def _breakout_rates_series(close: pd.Series) -> pd.DataFrame:
    """Breakout follow-through and failure rates over trailing 504 bars.

    A breakout day b is a day making a new 63d closing high.
    Resolved at t >= b + 10 bars (forward window complete).

    breakout_ft_rate_63: fraction where close[b+10] > close[b].
    failed_breakout_rate_63: fraction where close falls back below close[b]
        (the breakout-day close) within 10 bars.

    NaN if < 5 resolved breakouts within the 504-bar trailing window.
    """
    win_lookback = _WIN_BREAKOUT_LOOKBACK    # 504
    win_high = _WIN_BREAKOUT                 # 63
    fwd = _WIN_BREAKOUT_FWD                  # 10
    min_bk = _MIN_BREAKOUTS

    close_vals = close.values.astype(float)
    n = len(close_vals)

    ft_rates = np.full(n, np.nan)
    fail_rates = np.full(n, np.nan)

    # Precompute 63d rolling high (shift(1) so bar b's breakout level = max of b-63..b-1)
    # A "new 63d high" at bar b means close[b] > max(close[b-63:b])
    rolling_63_prior = pd.Series(close_vals).shift(1).rolling(
        win_high, min_periods=win_high
    ).max().values

    for t in range(win_lookback + fwd, n):
        # The window of available breakout bars: [t - win_lookback, t - fwd]
        # Only breakouts that are at least fwd bars old are "resolved" at t
        window_start = t - win_lookback
        resolved_end = t - fwd  # last fully-resolved breakout bar

        ft_count = 0
        fail_count = 0
        total = 0

        for b in range(window_start, resolved_end + 1):
            if np.isnan(rolling_63_prior[b]):
                continue
            # Is bar b a new 63d high?
            if close_vals[b] <= rolling_63_prior[b]:
                continue
            level = close_vals[b]
            # Resolution: forward closes b+1 .. b+fwd
            if b + fwd >= n:
                continue
            fwd_closes = close_vals[b + 1: b + fwd + 1]
            total += 1
            # Follow-through: close[b+10] > level (close at breakout)
            if fwd_closes[-1] > level:
                ft_count += 1
            # Failed: any close in b+1..b+fwd falls back below level
            if np.any(fwd_closes < level):
                fail_count += 1

        if total >= min_bk:
            ft_rates[t] = ft_count / total
            fail_rates[t] = fail_count / total

    return pd.DataFrame(
        {"breakout_ft_rate_63": ft_rates, "failed_breakout_rate_63": fail_rates},
        index=close.index,
    )


def _gap_share_series(open_: pd.Series, close: pd.Series) -> pd.Series:
    """gap_share_252: sum(|open_t - close_{t-1}|) / sum(|close_t - close_{t-1}|)
    over trailing 252 bars.  Zero denominator returns NaN.

    Note: this ratio can exceed 1.0 when large gap days are followed by intraday
    reversals (gap is large but net close-to-close move is small or opposite).
    Downstream classifier thresholds must not assume values are in [0, 1].
    """
    win = _WIN_GAP
    prev_close = close.shift(1)
    gap_abs = (open_ - prev_close).abs()
    move_abs = close.diff().abs()

    gap_sum = gap_abs.rolling(win, min_periods=win).sum()
    move_sum = move_abs.rolling(win, min_periods=win).sum()

    return (gap_sum / move_sum.replace(0, np.nan)).rename("gap_share_252")


def _event_gap_contrib_series(open_: pd.Series, close: pd.Series) -> pd.Series:
    """event_gap_contrib_252: fraction of total |close_t - close_{t-1}| contributed
    by the 5 largest |gap| days in trailing 252 bars.

    Note: this ratio can exceed 1.0 on days where a large gap reverses intraday
    (gap contributes to numerator but net close-to-close move is small).
    Downstream classifier thresholds must not assume values are in [0, 1].
    """
    win = _WIN_GAP
    prev_close = close.shift(1)
    gap_abs = (open_ - prev_close).abs()
    move_abs = close.diff().abs()

    gap_vals = gap_abs.values.astype(float)
    move_vals = move_abs.values.astype(float)
    n = len(close)
    out = np.full(n, np.nan)

    for t in range(win - 1, n):
        g = gap_vals[t - win + 1: t + 1]
        m = move_vals[t - win + 1: t + 1]
        if np.isnan(g).any() or np.isnan(m).any():
            continue
        total_move = m.sum()
        if total_move == 0:
            continue
        top5 = np.sort(g)[-5:].sum()
        out[t] = top5 / total_move

    return pd.Series(out, index=close.index, name="event_gap_contrib_252")


def _wick_share_series(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """wick_share_126: mean of upper+lower wick fraction of true range over 126 bars.

    wick = (high - max(open,close)) + (min(open,close) - low)
    fraction = wick / (high - low);  NaN where high == low (guard zero range).
    """
    win = _WIN_WICK
    upper_wick = high - pd.concat([open_, close], axis=1).max(axis=1)
    lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low
    total_wick = upper_wick + lower_wick

    bar_range = (high - low).replace(0, np.nan)
    wick_frac = total_wick / bar_range

    return wick_frac.rolling(win, min_periods=win).mean().rename("wick_share_126")


def _reversal_half_life_series(close: pd.Series) -> pd.Series:
    """Reversal half-life: estimate of how quickly post-shock counter-moves decay.

    Method (simple, deterministic):
    1. Identify shock days in trailing 504 bars: |daily return| > 2.5 * trailing-63d
       return std (computed at bar t using data t-63..t-1, i.e. shifted 1).
    2. For each shock day s, compute the cumulative sum of the COUNTER-move over the
       next 10 bars: cum[k] = sum_{j=1..k}(r_{s+j} * -sign(r_s)) for k=1..10.
       Normalized so cum[10] = 1 if fully reversed.
    3. Average the cum paths across all resolved shocks.
    4. Fit y = A*(1 - exp(-k/tau)) to the mean cum path via least squares (log-
       linearized: fit a line to log(1 - cum/cum[-1]) vs k, but fall back to a
       grid search if the normalized path violates monotonicity or bounds).
       half_life = tau * ln(2).
    5. NaN if < 8 resolved shocks or fit is degenerate.

    This estimator is intentionally simple, deterministic, and documented.
    It produces an ordinal ranking signal (shorter half-life = faster reverter),
    not a precision calibration.
    """
    close_vals = close.values.astype(float)
    n = len(close_vals)
    lr = np.log(close_vals[1:] / close_vals[:-1])  # length n-1

    win_lookback = _WIN_SHOCK_LOOKBACK  # 504
    win_std = _WIN_SHOCK_STD            # 63
    fwd = _WIN_SHOCK_FWD               # 10
    min_shocks = _MIN_SHOCKS

    out = np.full(n, np.nan)

    # rolling 63d std of returns (use shift(1): std at bar t uses bars t-63..t-1)
    # We compute this once for efficiency
    lr_series = pd.Series(lr)  # index 0..n-2 correspond to bars 1..n-1 in close
    # std at original bar t (t >= 1) = std of lr[t-win_std..t-1]
    # lr[i] = log(close[i+1]/close[i]), so lr index i corresponds to close bar i+1
    # std at bar t (0-indexed close) uses lr[t-win_std..t-1]
    trailing_std = np.full(n, np.nan)
    for t in range(win_std, n):
        seg = lr[t - win_std: t]
        trailing_std[t] = float(np.std(seg, ddof=1))

    for t in range(win_lookback + fwd, n):
        window_start = t - win_lookback
        resolved_end = t - fwd

        cum_paths = []
        for s in range(window_start + 1, resolved_end + 1):
            # shock check: |lr[s-1]| > 2.5 * trailing_std[s]
            # lr[s-1] = log(close[s]/close[s-1])
            if s >= n or s < 1:
                continue
            shock_ret = lr[s - 1]  # return at bar s (index s-1 in lr)
            std_s = trailing_std[s]
            if np.isnan(std_s) or std_s == 0:
                continue
            if abs(shock_ret) <= _SHOCK_MULT * std_s:
                continue
            # Resolved: s + fwd < n
            if s + fwd >= n:
                continue
            # Counter-move: sign is opposite to shock_ret
            shock_sign = np.sign(shock_ret)
            fwd_rets = lr[s: s + fwd]   # fwd returns after shock bar s
            counter = np.cumsum(-shock_sign * fwd_rets)
            cum_paths.append(counter)

        if len(cum_paths) < min_shocks:
            continue

        mean_path = np.mean(cum_paths, axis=0)  # shape (fwd,)
        # half-life: fit y = tau * k where y = cumulative counter (linear decay approx)
        # More robustly: half-life is where the mean counter-move reaches 50% of its
        # final value via linear interpolation
        final_val = mean_path[-1]
        if final_val <= 0:
            # no net counter-move on average — degenerate
            continue
        half_target = 0.5 * final_val
        # Find k where mean_path first crosses half_target
        hl = np.nan
        ks = np.arange(1, fwd + 1, dtype=float)
        for k_idx in range(len(mean_path)):
            if mean_path[k_idx] >= half_target:
                if k_idx == 0:
                    hl = 0.5  # crosses immediately
                else:
                    # linear interpolation
                    prev = mean_path[k_idx - 1]
                    curr = mean_path[k_idx]
                    frac = (half_target - prev) / (curr - prev)
                    hl = float(k_idx + frac)
                break
        # If never crosses, set hl to fwd (slow reverter)
        if np.isnan(hl):
            hl = float(fwd)
        out[t] = hl

    return pd.Series(out, index=close.index, name="reversal_half_life")


def _extreme_bar_freq_series(
    high: pd.Series, low: pd.Series, close: pd.Series
) -> pd.Series:
    """Fraction of trailing 252 bars with true range > 4x trailing-63d median TR.

    Halt/discontinuity PROXY — actual halt data does not exist; extreme true
    range is used as a proxy (large gaps, circuit-breaker opens, earnings
    blowups etc.).  Requires OHLC.
    """
    win_freq = _WIN_EXTREME_BAR         # 252
    win_norm = _WIN_EXTREME_BAR_NORM    # 63

    tr = _true_range(high, low, close)
    median_63 = tr.rolling(win_norm, min_periods=win_norm).median()
    threshold = _EXTREME_BAR_MULT * median_63

    is_extreme = (tr > threshold).astype(float)
    # zero-out NaN rows in is_extreme (where threshold is NaN)
    is_extreme[threshold.isna()] = np.nan

    return is_extreme.rolling(win_freq, min_periods=win_freq).mean().rename(
        "extreme_bar_freq_252"
    )


def _dollar_adv_series(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Median close * volume over trailing 21 bars."""
    dv = close * volume
    return dv.rolling(_WIN_ADV, min_periods=_WIN_ADV).median().rename("dollar_adv_21d")


# ---------------------------------------------------------------------------
# feature_series: full causal time-series
# ---------------------------------------------------------------------------


def feature_series(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the full causal time-series of all path features.

    Parameters
    ----------
    df:
        pd.DataFrame indexed by ascending DatetimeIndex.  Must contain
        ``close``; all other columns optional.

    Returns
    -------
    pd.DataFrame with the same index as ``df`` and one column per feature
    key.  Missing-column features are all-NaN columns.  Strict leak law:
    value at row t is identical whether or not future rows exist in the input.
    """
    df = df.sort_index()
    close = df["close"].astype(float)

    cols: dict[str, pd.Series | None] = {}

    # ---- trend persistence ----
    cols["trend_persist_20"] = _trend_persist_series(close, _WIN_TREND_20)
    cols["trend_persist_60"] = _trend_persist_series(close, _WIN_TREND_60)
    cols["trend_persist_126"] = _trend_persist_series(close, _WIN_TREND_126)

    # ---- slope stability ----
    cols["slope_stability_126"] = _slope_stability_126_series(close)

    # ---- pullback distribution ----
    pb = _pullback_series(close)
    cols["pullback_median_252"] = pb["pullback_median_252"]
    cols["pullback_p90_252"] = pb["pullback_p90_252"]

    # ---- breakout rates ----
    bk = _breakout_rates_series(close)
    cols["breakout_ft_rate_63"] = bk["breakout_ft_rate_63"]
    cols["failed_breakout_rate_63"] = bk["failed_breakout_rate_63"]

    # ---- gap features (need open) ----
    if _has_col(df, "open"):
        open_ = df["open"].astype(float)
        cols["gap_share_252"] = _gap_share_series(open_, close)
        cols["event_gap_contrib_252"] = _event_gap_contrib_series(open_, close)
    else:
        cols["gap_share_252"] = pd.Series(np.nan, index=df.index)
        cols["event_gap_contrib_252"] = pd.Series(np.nan, index=df.index)

    # ---- wick share (needs OHLC) ----
    if _has_ohlc(df):
        open_ = df["open"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        cols["wick_share_126"] = _wick_share_series(open_, high, low, close)
    else:
        cols["wick_share_126"] = pd.Series(np.nan, index=df.index)

    # ---- reversal half life ----
    cols["reversal_half_life"] = _reversal_half_life_series(close)

    # ---- extreme bar frequency (needs HLC) ----
    if _has_hlc(df):
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        cols["extreme_bar_freq_252"] = _extreme_bar_freq_series(high, low, close)
    else:
        cols["extreme_bar_freq_252"] = pd.Series(np.nan, index=df.index)

    # ---- range compression (BBWP — reuse entry_primitives) ----
    cols["range_compression_pct"] = bbwp_series(close)

    # ---- dollar ADV (needs volume) ----
    if _has_volume(df):
        cols["dollar_adv_21d"] = _dollar_adv_series(close, df["volume"].astype(float))
    else:
        cols["dollar_adv_21d"] = pd.Series(np.nan, index=df.index)

    # ---- Amihud (needs volume — reuse entry_primitives) ----
    if _has_volume(df):
        am = amihud_series(close, df["volume"].astype(float), win=20)
        # 252-bar trailing mean of the 20-bar rolling Amihud
        cols["amihud_252"] = am.rolling(_WIN_AMIHUD, min_periods=_WIN_AMIHUD).mean()
    else:
        cols["amihud_252"] = pd.Series(np.nan, index=df.index)

    # ---- Corwin-Schultz spread (needs HLC — reuse entry_primitives) ----
    if _has_hlc(df):
        cs = corwin_schultz_spread_series(
            df["high"].astype(float), df["low"].astype(float)
        )
        cols["cs_spread_252"] = cs.rolling(_WIN_CS, min_periods=_WIN_CS).mean()
    else:
        cols["cs_spread_252"] = pd.Series(np.nan, index=df.index)

    result = pd.DataFrame(cols, index=df.index)
    return result


# ---------------------------------------------------------------------------
# features: causal snapshot
# ---------------------------------------------------------------------------

_FEATURE_KEYS = [
    "trend_persist_20",
    "trend_persist_60",
    "trend_persist_126",
    "slope_stability_126",
    "pullback_median_252",
    "pullback_p90_252",
    "breakout_ft_rate_63",
    "failed_breakout_rate_63",
    "gap_share_252",
    "event_gap_contrib_252",
    "wick_share_126",
    "reversal_half_life",
    "extreme_bar_freq_252",
    "range_compression_pct",
    "dollar_adv_21d",
    "amihud_252",
    "cs_spread_252",
]


def features(
    df: pd.DataFrame,
    *,
    as_of: Any = None,
) -> dict:
    """Causal snapshot of all path features as of ``as_of``.

    Parameters
    ----------
    df:
        pd.DataFrame indexed by ascending DatetimeIndex.
    as_of:
        Optional date/timestamp.  Data strictly after ``as_of`` is excluded.
        Default: last row.

    Returns
    -------
    dict with keys = _FEATURE_KEYS + "coverage".
    ``coverage`` is a sub-dict: {n_bars, has_ohlc, has_volume, as_of}.
    Features that require a missing column return None.
    """
    df = df.sort_index()

    if as_of is not None:
        as_of_ts = pd.Timestamp(as_of)
        df = df.loc[df.index <= as_of_ts]

    if df.empty:
        result: dict = {k: None for k in _FEATURE_KEYS}
        result["coverage"] = {
            "n_bars": 0,
            "has_ohlc": False,
            "has_volume": _has_volume(df),
            "as_of": None,
        }
        return result

    actual_as_of = df.index[-1]

    # Minimum required length per feature; truncate to avoid computing full
    # history (expensive features like breakout_rates loop over 504 bars).
    # We only need the trailing window for a snapshot.
    #
    # Derivation: the earliest breakout candidate is at bar t-_WIN_BREAKOUT_LOOKBACK.
    # To classify it as a new 63d high we need its prior-high window of _WIN_BREAKOUT
    # bars (rolling_63_prior looks back _WIN_BREAKOUT bars before the candidate).
    # Resolved candidates also need _WIN_BREAKOUT_FWD forward bars.
    # An extra margin of 10 bars guards against off-by-one edge cases.
    max_window = (
        _WIN_BREAKOUT_LOOKBACK + _WIN_BREAKOUT + _WIN_BREAKOUT_FWD + 10
    )  # 504 + 63 + 10 + 10 = 587
    df_tail = df.iloc[-max_window:] if len(df) > max_window else df

    series = feature_series(df_tail)
    last_row = series.iloc[-1]

    result = {}
    for k in _FEATURE_KEYS:
        val = last_row.get(k, np.nan)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            # Check if it's a structural None (missing column) vs numeric NaN
            # For missing-column features: always None; for numeric NaN: None too
            result[k] = None
        else:
            result[k] = float(val)

    result["coverage"] = {
        "n_bars": len(df),
        "has_ohlc": _has_ohlc(df),
        "has_volume": _has_volume(df),
        "as_of": str(actual_as_of.date()) if hasattr(actual_as_of, "date") else str(actual_as_of),
    }

    return result
