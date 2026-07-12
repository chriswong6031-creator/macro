"""IRD-R13 velocity grammar — shared helper for intl_bonds + intl_rates + intl_risk
+ contagion.

Single grammar, all callers:
  vel_5d     = (last - last[-6]) * scale
  vel_20d    = (last - last[-21]) * scale
  vel_20d_z  = (current_20d_chg - mean(hist)) / std(hist)
               TRUE z (mean-subtracted) on trailing 2y (504bd) of the 20d-change
               series EXCLUDING the current observation; window_days disclosed.

For yield/OAS series (% units → bp): use scale=100, unit="bp" (or the thin wrapper
velocity_fields_bp).  For ratio / level series: scale=1 (default), unit="raw".

Min-length guards (documented rules):
  vel_5d:    requires >= 6 observations after dropna
  vel_20d:   requires >= 21 observations after dropna
  vel_20d_z: requires >= 40 observations in the change series (chg = s.diff(20).dropna());
             the history window (excluding current) requires >= 20 observations.

Fail-open: returns None for any field where the series is too short or std == 0.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


_TWO_YEARS_BD = 504   # ~2 trading years in business days


def velocity_fields(
    series: pd.Series | None,
    *,
    scale: float = 1.0,
    unit: str = "raw",
) -> dict:
    """Compute IRD-R13 velocity fields for any numeric series.

    Parameters
    ----------
    series:
        A pandas Series indexed by date.  May be daily or monthly
        (forward-filled externally).  None → all fields are None.
    scale:
        Multiplier applied to raw Δ values before storing vel_5d / vel_20d.
        For yield/OAS series in %-point units pass scale=100 (→ basis points).
        Default 1.0 (no scaling).
    unit:
        String label embedded in output keys when scale != 1.0.
        'bp' → keys are vel_5d_bp / vel_20d_bp / vel_20d_z / window_days.
        'raw' → same key names but values are in the raw series units × scale.

    Returns
    -------
    dict with keys:
      vel_5d_bp   : float | None  — 5-business-day Δ × scale
      vel_20d_bp  : float | None  — 20-business-day Δ × scale
      vel_20d_z   : float | None  — vel_20d (unscaled Δ) z-scored on trailing 2y
                                    TRUE z: (chg − mean(hist)) / std(hist),
                                    current obs excluded from the norm window,
                                    window_days disclosed.
      window_days : int | None    — actual trailing window used for z-norm (disclosed)

    Key names are always vel_5d_bp / vel_20d_bp / vel_20d_z / window_days regardless
    of unit label, for backward compatibility with existing callers.
    """
    out: dict = {"vel_5d_bp": None, "vel_20d_bp": None, "vel_20d_z": None, "window_days": None}
    if series is None or series.empty:
        return out

    s = series.dropna()
    n = len(s)

    # 5d velocity (need at least 6 observations)
    if n >= 6:
        v5 = (float(s.iloc[-1]) - float(s.iloc[-6])) * scale
        out["vel_5d_bp"] = _r(v5)

    # 20d velocity (need at least 21 observations)
    if n >= 21:
        v20 = (float(s.iloc[-1]) - float(s.iloc[-21])) * scale
        out["vel_20d_bp"] = _r(v20)
    else:
        return out

    # True z-score of 20d velocity on trailing 2y (or max available, min 40 obs).
    # z = (current_chg - mean(hist)) / std(hist), where hist excludes current obs.
    # Note: diff(20) uses the raw unscaled series; scale only affects vel_5d/vel_20d.
    chg = s.diff(20).dropna()
    if len(chg) < 40:
        return out

    # Exclude the current observation from the normalization window (causal).
    hist = chg.iloc[:-1]
    if len(hist) < 20:
        return out
    window = min(_TWO_YEARS_BD, len(hist))
    w = hist.iloc[-window:]
    mu = float(w.mean())
    sd = float(w.std())
    if sd == 0 or not math.isfinite(sd):
        return out

    # True z (mean-subtracted): if series is trending, mean removes the drift so that
    # a "typical" change relative to recent history reads near 0.
    z = (float(chg.iloc[-1]) - mu) / sd
    if not math.isfinite(z):
        return out

    out["vel_20d_z"] = _r(z, 3)
    out["window_days"] = window
    return out


def velocity_fields_bp(series: pd.Series | None) -> dict:
    """Thin wrapper: velocity_fields with scale=100, unit='bp'.

    For yield/OAS series stored in %-point units (e.g. 4.25 = 4.25%) — outputs
    vel_5d_bp / vel_20d_bp in basis points while vel_20d_z is dimensionless.
    Preserves backward compatibility with intl_bonds / intl_rates callers.
    """
    return velocity_fields(series, scale=100.0, unit="bp")


def _r(v: float, nd: int = 1) -> float | None:
    """Round to nd decimals; return None if non-finite."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else round(f, nd)
    except (TypeError, ValueError):
        return None
