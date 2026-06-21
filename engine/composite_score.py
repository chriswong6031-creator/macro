"""Decorrelated cross-sectional COMPOSITE score (engine v2) — the Fundamental-Law lever.

Our probe measured what theory predicts: weak signals that DON'T correlate stack —
a 50/50 momentum+X blend reached ~1.42x (≈√2 at corr ≈0) the IC of either leg alone
(research/MAGICAL_SIGNALS_ROADMAP.md). So the robust way to raise the selection edge is
NOT a better single signal (none clears the bar standalone) but a clean, sector-neutral,
EQUAL-WEIGHT combination of decorrelated, return-predictive legs.

Construction (the honest zero-tuned baseline the research demands — every fancier weight
scheme must beat THIS out-of-sample, so it is the default):
  per leg: winsorize ±3 MAD -> z-score WITHIN GICS sector (sector-neutral, so a hot
  sector doesn't masquerade as alpha) -> EQUAL-WEIGHT average across the present legs.
Legs are the decorrelated RETURN-predictive set: momentum + value + quality +
profitability + analyst-revisions. DELIBERATELY EXCLUDED: short-term reversal (a
net-of-cost mirage on the non-survivor universe) and low-volatility (a RISK/sizing lever,
handled by engine.risk_sizing, not a raw-return selection signal). A missing leg just
drops out of that name's average — never imputed to neutral.

This is a pure CROSS-SECTIONAL rank tilt: it has edge only in aggregate across the book,
never as a per-name buy/sell verdict (single-name direction is a coin-flip). Emitted as a
transparent context score beside the conviction profile; it is sector-neutral by design.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# the decorrelated, return-predictive legs (NOT reversal, NOT low-vol-as-selection)
DEFAULT_LEGS = ("momentum", "value", "quality", "profitability", "revisions")
_MAD_K = 3.0


def _winsor_z_by_sector(s: pd.Series, sectors: pd.Series) -> pd.Series:
    """Winsorize ±3 MAD then z-score WITHIN each sector (sector-neutral)."""
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for sec, idx in s.groupby(sectors).groups.items():
        v = s.loc[idx].astype(float).dropna()
        if len(v) < 5:
            # too few names in the sector to neutralize — fall back to a plain z
            v = s.loc[idx].astype(float).dropna()
            if len(v) >= 2 and v.std(ddof=0) > 0:
                out.loc[v.index] = (v - v.mean()) / v.std(ddof=0)
            continue
        med = v.median()
        mad = (v - med).abs().median() * 1.4826 or v.std(ddof=0)
        if mad and mad > 0:
            w = v.clip(med - _MAD_K * mad, med + _MAD_K * mad)
            sd = w.std(ddof=0)
            out.loc[w.index] = (w - w.mean()) / sd if sd > 0 else 0.0
    return out


def build(legs: pd.DataFrame, sectors: dict[str, str] | pd.Series, *,
          use_legs=DEFAULT_LEGS, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """`legs` = a [ticker x leg] frame of RAW leg values (any subset of use_legs present).
    Returns a [ticker x {composite, n_legs, <leg>_z...}] frame: each present leg
    sector-neutral-z'd, then equal-weight (or `weights`) averaged into `composite`.
    Equal-weight is the default — lightly-shrunk IC weights can be passed once a rolling
    IC estimate exists, but they must beat equal-weight OOS to be used."""
    if legs is None or legs.empty:
        return pd.DataFrame()
    sec = sectors if isinstance(sectors, pd.Series) else pd.Series(sectors)
    sec = sec.reindex(legs.index).fillna("—")
    present = [l for l in use_legs if l in legs.columns and legs[l].notna().sum() >= 5]
    if not present:
        return pd.DataFrame()
    zcols = {}
    for leg in present:
        zcols[f"{leg}_z"] = _winsor_z_by_sector(legs[leg], sec)
    z = pd.DataFrame(zcols)
    w = None
    if weights:
        w = np.array([weights.get(l, 0.0) for l in present], dtype=float)
        w = w / w.sum() if w.sum() > 0 else None
    if w is None:                                          # equal-weight over PRESENT legs/name
        comp = z.mean(axis=1, skipna=True)
    else:
        zz = z.to_numpy()
        mask = ~np.isnan(zz)
        wmat = np.where(mask, w[None, :], 0.0)
        denom = wmat.sum(axis=1)
        comp = pd.Series(np.where(denom > 0, np.nansum(zz * wmat, axis=1) / denom, np.nan),
                         index=z.index)
    out = z.copy()
    out["composite"] = comp.round(3)
    out["n_legs"] = z.notna().sum(axis=1)
    return out


def leg_correlations(legs: pd.DataFrame, sectors: dict | pd.Series,
                     use_legs=DEFAULT_LEGS) -> pd.DataFrame:
    """Sector-neutral pairwise leg correlations — the decorrelation check (near-0 off
    diagonal = the legs stack; high = redundant / double-counting)."""
    sec = sectors if isinstance(sectors, pd.Series) else pd.Series(sectors)
    sec = sec.reindex(legs.index).fillna("—")
    cols = {l: _winsor_z_by_sector(legs[l], sec)
            for l in use_legs if l in legs.columns and legs[l].notna().sum() >= 5}
    return pd.DataFrame(cols).corr().round(2) if cols else pd.DataFrame()
