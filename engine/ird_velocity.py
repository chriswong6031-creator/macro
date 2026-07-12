"""IRD-R13 velocity grammar — shared helper for intl_bonds + intl_rates.

One shared construction everywhere:
  vel_5d_bp   = (last - last[-6]) * 100   (basis-point change over 5 business days)
  vel_20d_bp  = (last - last[-21]) * 100  (basis-point change over 20 business days)
  vel_20d_z   = vel_20d_bp / rolling_std(trailing 2y of the 20d change series)
                z-scored on trailing 2y OR max-available with window_days disclosed

All values are in basis points for yield/OAS series.  The series is assumed to be
in percentage-point units (e.g. 4.25 for 4.25%) so the Δ×100 converts to bp.

Fail-open: returns None for any field where the series is too short.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


_TWO_YEARS_BD = 504   # ~2 trading years in business days


def velocity_fields(series: pd.Series | None) -> dict:
    """Compute IRD-R13 velocity fields for a yield/OAS series (in % units → bp output).

    Parameters
    ----------
    series:
        A pandas Series indexed by date, values in percentage-point units
        (e.g. 4.25 for 4.25%).  May be daily or monthly (forward-filled externally).
        None → all fields are None.

    Returns
    -------
    dict with keys:
      vel_5d_bp   : float | None  — 5-business-day change in basis points
      vel_20d_bp  : float | None  — 20-business-day change in basis points
      vel_20d_z   : float | None  — vel_20d_bp z-scored on trailing 2y (or max-available)
      window_days : int | None    — actual trailing window used for z-norm (disclosed)
    """
    out: dict = {"vel_5d_bp": None, "vel_20d_bp": None, "vel_20d_z": None, "window_days": None}
    if series is None or series.empty:
        return out

    s = series.dropna()
    n = len(s)

    # 5d velocity (need at least 6 observations)
    if n >= 6:
        v5 = (float(s.iloc[-1]) - float(s.iloc[-6])) * 100.0
        out["vel_5d_bp"] = _r(v5)

    # 20d velocity (need at least 21 observations)
    if n >= 21:
        v20 = (float(s.iloc[-1]) - float(s.iloc[-21])) * 100.0
        out["vel_20d_bp"] = _r(v20)
    else:
        return out

    # z-score of 20d velocity on trailing 2y (or max available, min 40 obs)
    chg = s.diff(20).dropna()
    if len(chg) < 40:
        return out

    # Use trailing _TWO_YEARS_BD of the change series, excluding the current value
    hist = chg.iloc[:-1]
    if len(hist) < 20:
        return out
    window = min(_TWO_YEARS_BD, len(hist))
    w = hist.iloc[-window:]
    sd = float(w.std())
    if sd == 0 or not math.isfinite(sd):
        return out

    z = float(chg.iloc[-1]) / sd
    if not math.isfinite(z):
        return out

    out["vel_20d_z"] = _r(z, 3)
    out["window_days"] = window
    return out


def _r(v: float, nd: int = 1) -> float | None:
    """Round to nd decimals; return None if non-finite."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else round(f, nd)
    except (TypeError, ValueError):
        return None
