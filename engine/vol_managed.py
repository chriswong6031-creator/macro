"""Vol-managed (volatility-targeted) position sizing — the most-replicated risk-adjusted
improvement in the equity literature (Moreira-Muir 2017 "Volatility-Managed Portfolios";
Barroso-Santa-Clara 2015 for momentum). Scale a directional exposure INVERSELY to its
forecast volatility so the sleeve carries ~constant risk: size up when vol is low, cut
when vol spikes. Volatility is far more forecastable than returns, so this is a
capital-efficiency / drawdown lever that pays with ZERO new alpha — exactly the kind of
edge that survives on a survivorship-biased universe.

Pure & causal: the scalar at bar t uses only return information through t; the caller
(engine.validation.backtest_core) shifts the position to act at t+1, so there is no
look-ahead. Default cap=1.0 keeps it long/flat (de-risk only, no leverage); raise the
cap to lever the calm-vol periods (the full Moreira-Muir construction).

NOTE: this is the RESEARCH/BACKTEST vol-targeting helper — it returns a causal SERIES so
the strategy lab can backtest a vol-scaled sleeve through backtest_core. The PRODUCTION
sizing engine is `engine.risk_sizing` (two-layer inverse-vol weights + capped vol-target
scalar, the same Moreira-Muir lever, shipped via PR #354). Keep them in sync conceptually;
this module exists for reproducible backtests, not the live build.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_YEAR = 252


def realized_vol(close: pd.Series, span: int = 21) -> pd.Series:
    """Annualized EWMA close-to-close volatility (causal, trailing)."""
    r = close.pct_change()
    return r.ewm(span=span, min_periods=max(5, span // 2)).std(bias=False) * np.sqrt(TRADING_YEAR)


def forecast_vol(close: pd.Series, short: int = 21, long: int = 63, blend: float = 0.6) -> pd.Series:
    """HAR-lite blend of a short- and long-horizon EWMA vol — a robust 1-step vol
    forecast (vol is persistent; blending horizons beats a single window). Trailing, so
    the value at t is known at the close of t."""
    sv = realized_vol(close, short)
    lv = realized_vol(close, long)
    return blend * sv + (1.0 - blend) * lv


def vol_scalar(close: pd.Series, target: float = 0.15, cap: float = 1.0,
               floor: float = 0.0, short: int = 21, long: int = 63) -> pd.Series:
    """Volatility-target scalar s_t = clip(target / forecast_vol_t, floor, cap) ∈ [floor,cap].
    Multiply any directional position by this to hold ~`target` annualized vol. cap=1.0 →
    long/flat de-risking; cap>1 → lever the calm periods."""
    f = forecast_vol(close, short, long).replace(0.0, np.nan)
    s = (target / f).clip(lower=floor, upper=cap)
    return s.fillna(0.0)


def vol_target_position(position: pd.Series, close: pd.Series, target: float = 0.15,
                        cap: float = 1.0, **kw) -> pd.Series:
    """Apply vol-targeting to an existing long/flat (or long/short) position series."""
    return (position.fillna(0.0) * vol_scalar(close, target=target, cap=cap, **kw)).clip(-cap, cap)


def live_scalar(close: pd.Series, target: float = 0.15, cap: float = 1.5) -> float | None:
    """Latest vol-target scalar for the live build (one number per name) — the sizing
    multiplier a desk/Mastermind applies on top of a directional read. cap=1.5 allows a
    modest lever in calm regimes. None if history is too thin."""
    if close is None or len(close.dropna()) < 80:
        return None
    s = vol_scalar(close.dropna(), target=target, cap=cap)
    v = s.iloc[-1] if len(s) else np.nan
    return round(float(v), 3) if np.isfinite(v) else None
