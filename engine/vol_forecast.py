"""Volatility forecast — the cone-WIDTH anchor of the Anticipation Engine.

Returns (unlike direction) are near-unforecastable short-horizon, but VOLATILITY is
genuinely forecastable: it is persistent and long-memory (Corsi's HAR-RV; Hawkes
self-excitation). So the cone's WIDTH is the honest, calibratable quantity. This
module produces a point-in-time forward-vol estimate from a multi-scale blend of
trailing realized volatility (daily / weekly / monthly / quarterly) — the HAR
predictor set — without a fitted regression (equal-scale blend; the Phase-0 harness
reports its forward-RV R² so the "HAR-style" claim is measured, not assumed).

All causal: every value at date t uses only close ≤ t. forward_vol_ann is the
REALIZED forward vol — a LABEL for validation only, never an input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HAR_LAGS = (2, 5, 22, 66)


def realized_vol(close: pd.Series, win: int) -> pd.Series:
    """Trailing close-to-close realized vol (daily units) over `win` bars (≥2)."""
    win = max(2, int(win))
    return close.pct_change(fill_method=None).rolling(win, min_periods=min(win, max(2, win // 2))).std(ddof=0)


def har_vol(close: pd.Series, lags=HAR_LAGS) -> pd.Series:
    """Multi-scale realized-vol blend (HAR predictor set), daily units. Equal-weight
    mean of RV over the lag set — captures vol persistence across horizons. Point-in-time."""
    comps = [realized_vol(close, L) for L in lags]
    return pd.concat(comps, axis=1).mean(axis=1)


def cone_vol_ann(close: pd.Series, lags=HAR_LAGS, trading_year: int = 252) -> pd.Series:
    """Annualized point-in-time forward-vol ESTIMATE used to set the cone width.
    A pragmatic HAR-style predictor (no look-ahead)."""
    return har_vol(close, lags) * np.sqrt(trading_year)


def forward_vol_ann(close: pd.Series, horizon: int, trading_year: int = 252) -> pd.Series:
    """REALIZED annualized vol over the FORWARD `horizon` window — the validation
    LABEL the har predictor is scored against. Look-ahead by construction (it is the
    target), so it is NEVER fed to the live engine; the last `horizon` rows are NaN."""
    rv = close.pct_change(fill_method=None).rolling(horizon).std(ddof=0).shift(-horizon)
    return rv * np.sqrt(trading_year)


def vol_regime(close: pd.Series, lookback: int = 252) -> pd.Series:
    """Where current har_vol sits in its own trailing distribution (0..1 percentile).
    A high reading = an elevated-vol regime (wider cone); contrarian only at extremes."""
    hv = har_vol(close)
    return hv.rolling(lookback, min_periods=lookback // 2).rank(pct=True)
