"""Single-name DIRECTIONAL model (v0) — the honest per-stock directional lean.

The index/sector/theme directional brain (engine/index_direction.py) found exactly ONE
robustly-OOS-priced equity directional driver: REAL RATES. This module asks the obvious
follow-on — does that validated macro edge TRANSMIT to single names? — without the
data-mining trap of fitting 1500 independent per-name models.

The design (research/NAME_DIRECTION.md), honesty rules baked in:
- ONE leg per name: its CAUSAL duration exposure to real rates × the SAME validated
  real_rate leg index_direction already uses. No per-name leg search, no kitchen sink.
    dur_i,t      = −beta_i,t   where  beta_i = cov(r_i, Δreal10)/var(Δreal10)  (causal, lagged)
                   (negated so dur>0 = rate-SENSITIVE growth/duration name; dur<0 = inverse,
                    e.g. financials/energy that rise when rates rise)
    signal_i,t   = shrunk(dur_i,t) · rr_leg_t          rr_leg = index_direction real_rate leg
                   (high when real rates have fallen — the validated bullish orientation)
    r̂_i,t        = pooled_slope_h · signal_i,t          ONE slope, fit pooled in Phase-0
    P(up)        = Φ(r̂ / σ_h), Platt-recalibrated, clamped to a TIGHT band
- Vasicek shrinkage of the per-name beta toward the cross-section is MANDATORY (single-name
  rate-beta persistence is only ~0.36): a handful of garbage betas must not poison the lean.
- The lean is GATED by ONE pooled-panel Phase-0 block (NAME_DIRECTION in the gate JSON),
  shared by ALL names — NOT a per-name gate. Default everywhere is the existing coin-flip.
- It moves ONLY the direction center (anticipation.py recenters the cone, WIDTH unchanged);
  it never touches the validated risk cone and is never conflated with the Conviction rank.

This is a validated MACRO-TRANSMISSION overlay, not per-name alpha: the name supplies only an
exposure to an edge validated elsewhere. The honest base case is that it scores nothing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import index_direction as idr, residual_alpha as ra

# FROZEN constants (set BEFORE the Phase-0 gate read — anti-snooping; asserted in tests).
NAME_BETA_WIN = 252        # rolling beta window (1y)
NAME_BETA_MINP = 126       # min points before a beta is estimable
NAME_SHRINK = 0.66         # Vasicek weight on the raw beta (repo default, engine_residual_alpha)
NAME_P_BAND = (0.44, 0.58)  # tighter than the index P_BAND — a single name's macro lean is small
HORIZONS_TD = idr.HORIZONS_TD            # {"medium": 42, "long": 189}


def rate_inputs(spy_close: pd.Series | None = None) -> dict | None:
    """Shared, name-independent inputs (build ONCE, reuse for every name):
      real10  — the real-rate LEVEL (DFII10); per-name Δ + beta are derived from it
      rr_leg  — the EXACT validated index_direction real_rate leg (−z of the 60d real-rate
                change; high = rates have fallen = bullish), on SPY's calendar
    Returns None if the real-rate series or SPY are unavailable (→ everything coin-flips)."""
    from pathlib import Path
    p = Path("data/fred/DFII10.parquet")
    if not p.exists():
        return None
    real10 = pd.read_parquet(p)
    real10 = real10[real10.columns[0]].dropna()
    if real10.empty:
        return None
    if spy_close is None:
        sp = Path("data/yahoo/SPY.parquet")
        if not sp.exists():
            return None
        spy_close = pd.read_parquet(sp)["close"].dropna()
    legs = idr.build_legs(spy_close.astype(float))
    if "real_rate" not in legs.columns:
        return None
    return {"real10": real10, "rr_leg": legs["real_rate"]}


def _name_beta(close: pd.Series, real10: pd.Series, *, win: int = NAME_BETA_WIN,
               minp: int = NAME_BETA_MINP) -> pd.Series:
    """Causal rolling beta of the name's daily return on the DAILY real-rate change
    (lagged one day — prior-window data only). NaN until estimable."""
    r = close.pct_change(fill_method=None)
    d_rr = real10.reindex(close.index).ffill().diff()
    return ra._causal_beta(r, d_rr, win, minp)


def name_signal(close: pd.Series, inputs: dict, *, dur_prior: float = 0.0,
                shrink: float = NAME_SHRINK, win: int = NAME_BETA_WIN,
                minp: int = NAME_BETA_MINP) -> pd.Series:
    """The full per-name signal series (PIT): shrunk duration score × the real_rate leg.
    dur = −beta (positive = rate-sensitive growth/duration); shrunk toward `dur_prior`
    (the cross-sectional mean duration; 0.0 = conservative no-exposure prior when absent);
    multiplied by the validated rr_leg (high = rates fell)."""
    close = close.astype(float)
    dur = -_name_beta(close, inputs["real10"], win=win, minp=minp)
    # scalar Vasicek shrink toward the supplied cross-sectional prior (w·raw + (1−w)·prior)
    w = 1.0 if (shrink is None or shrink >= 1.0) else float(shrink)
    shrunk = dur.mul(w).add((1.0 - w) * float(dur_prior or 0.0))
    rr = inputs["rr_leg"].reindex(close.index).ffill()
    return (shrunk * rr).rename("name_signal")


def _latest_finite(s: pd.Series):
    s = s.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def forecast(close: pd.Series, *, inputs: dict | None, gate: dict | None = None,
             dur_prior: float = 0.0, shrink: float = NAME_SHRINK,
             win: int = NAME_BETA_WIN, minp: int = NAME_BETA_MINP) -> dict:
    """Live per-name directional read, SAME shape as index_direction.forecast so the
    anticipation assembly reuses it verbatim. Returns {} if no inputs / too little
    history. Each horizon is a coin-flip (p_up=0.5, scored=False) unless the shared
    NAME_DIRECTION gate block says that horizon is scored AND the name has a finite
    signal AND a finite pooled slope."""
    close = close.dropna().astype(float)
    if inputs is None or len(close) < 800:
        return {}
    sig_now = _latest_finite(name_signal(close, inputs, dur_prior=dur_prior, shrink=shrink,
                                         win=win, minp=minp))
    g = gate or {}
    horizons = {}
    for hname, h in HORIZONS_TD.items():
        gblock = g.get(hname, {}) or {}
        gate_scored = bool(gblock.get("scored"))
        slope = gblock.get("pooled_slope")
        sh = idr.sigma_h(close, h)
        r_hat, p_up, scored = None, 0.5, False
        if gate_scored and slope is not None and sig_now is not None:
            r_hat = float(slope) * sig_now
            p_up = idr.forecast_to_p_up(r_hat, sh, gblock.get("platt"),
                                        tuple(gblock.get("p_up_band", NAME_P_BAND)))
            scored = True
        horizons[hname] = {
            "r_hat": round(r_hat, 4) if r_hat is not None else None,
            "p_up": round(p_up, 3), "sigma_h": round(sh, 2) if np.isfinite(sh) else None,
            "scored": scored, "used": ["real_rate"] if scored else [], "legs": {},
            "direction": ("up-lean" if p_up > 0.52 else ("down-lean" if p_up < 0.48 else "neutral")),
            "oos_r2": gblock.get("oos_r2") if scored else None,
            "cw_p": gblock.get("cw_p") if scored else None,
        }
    return {"asset": close.name or "?", "horizons": horizons,
            "trust": ("scored macro-transmission overlay (real_rate; not per-name alpha)"
                      if any(h["scored"] for h in horizons.values())
                      else "display-only (real-rate transmission not validated OOS)")}
