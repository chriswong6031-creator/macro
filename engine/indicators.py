"""Shared transforms for the regime engine. All vectorized over full history —
the backtest and the live signal use exactly the same code path."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_slope(s: pd.Series, window: int) -> pd.Series:
    """OLS slope of the series against time over a trailing window.
    Equivalent to cov(y, t)/var(t) computed in a rolling fashion."""
    t = np.arange(window, dtype=float)
    t_mean = t.mean()
    t_var = ((t - t_mean) ** 2).sum()

    def _slope(y: np.ndarray) -> float:
        if np.isnan(y).any():
            return np.nan
        return float(((t - t_mean) * (y - y.mean())).sum() / t_var)

    return s.rolling(window, min_periods=window).apply(_slope, raw=True)


def slope_z(s: pd.Series, slope_window: int, baseline_window: int,
            use_log: bool = True) -> pd.Series:
    """Direction-of-change signal: t-statistic of the trailing slope_window
    drift against baseline_window volatility —
        z = mean(daily change over slope_window) / (std(daily change over
            baseline_window) / sqrt(slope_window)).
    A steady trend keeps scoring (unlike z-scoring the slope against its own
    recent mean, which decays to zero mid-regime); flat tape scores ~0."""
    base = np.log(s.where(s > 0)) if use_log else s
    chg = base.diff()
    drift = chg.rolling(slope_window, min_periods=slope_window).mean()
    vol = chg.rolling(baseline_window, min_periods=baseline_window // 2).std()
    return drift / (vol.replace(0, np.nan) / np.sqrt(slope_window))


def score_from_z(z: pd.Series, threshold: float) -> pd.Series:
    """Map a z-score to a -1/0/+1 component score (NaN stays NaN)."""
    s = pd.Series(0.0, index=z.index)
    s[z > threshold] = 1.0
    s[z < -threshold] = -1.0
    s[z.isna()] = np.nan
    return s


def basket_index(closes: pd.DataFrame, members: list[str]) -> pd.Series:
    """Equal-weight total-return index of the members present (rebased to 1).
    Uses mean daily return so additions/deletions don't jump the level."""
    cols = [m for m in members if m in closes.columns]
    if not cols:
        return pd.Series(dtype=float)
    rets = closes[cols].pct_change(fill_method=None).mean(axis=1)
    return (1 + rets.fillna(0)).cumprod().where(closes[cols].notna().any(axis=1))


def expanding_percentile(s: pd.Series, min_obs: int = 252) -> pd.Series:
    """Percentile of the latest value within ITS OWN history up to that day
    (no lookahead)."""
    ranked = s.expanding(min_periods=min_obs).rank(pct=True)
    return ranked


def pct_rank_window(s: pd.Series, window: int) -> pd.Series:
    """Percentile of the latest value within a trailing window."""
    return s.rolling(window, min_periods=window // 2).rank(pct=True)
