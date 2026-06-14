"""Symmetric (Löwdin) factor orthogonalization — stop the composite double-counting.

The equity factor engine builds each factor as a raw cross-sectional z-score and the
composite as their equal-weight mean. But the factors overlap (value & quality both
tilt to the same cheap, profitable names; low-vol & low-beta are near-twins), so an
equal-weight mean OVER-weights whatever shared variance they have — it's not really
combining independent bets (Point 3/4). This decorrelates them.

Löwdin (symmetric) orthogonalization is the right tool here: F_orth = F · C^(-1/2)
where C is the factor correlation matrix. Unlike Gram-Schmidt it has no ordering bias
(no factor is privileged as the "first"); it returns the set of uncorrelated factors
CLOSEST to the originals, so each keeps its identity while the shared variance is
removed. The orthogonal composite is then an honest equal-RISK blend.

Pure numpy (eigendecomposition for C^(-1/2), no scipy). ADDITIVE — a standalone the
factor IC scorecard uses to compare raw vs orthogonalized composite signal quality;
it does not modify the live factor engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.validation import top_correlated_pairs, vif


def _zscore(df: pd.DataFrame) -> pd.DataFrame:
    sd = df.std(ddof=0).replace(0, np.nan)
    return (df - df.mean()) / sd


def _inv_sqrt_corr(C: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    """C^(-1/2) via eigendecomposition, flooring tiny/negative eigenvalues so a
    near-singular (highly collinear) correlation matrix stays invertible."""
    w, V = np.linalg.eigh(C)
    w = np.clip(w, floor, None)
    return V @ np.diag(1.0 / np.sqrt(w)) @ V.T


def orthogonalize(factors: pd.DataFrame) -> pd.DataFrame:
    """Return Löwdin-orthogonalized factors (same shape/columns), re-standardized.
    The transform C^(-1/2) is estimated on complete cases; rows with missing legs are
    mean-imputed (0 in z-space) before applying it, then masked back to NaN where the
    original was fully missing."""
    cols = list(factors.columns)
    if len(cols) < 2:
        return factors.copy()
    Z = _zscore(factors)
    complete = Z.dropna()
    if len(complete) < max(30, 3 * len(cols)):
        return factors.copy()                      # too thin to estimate C reliably
    C = np.corrcoef(complete.values, rowvar=False)
    W = _inv_sqrt_corr(C)
    filled = Z.fillna(0.0)                          # mean-impute missing legs
    orth = pd.DataFrame(filled.values @ W, index=Z.index, columns=cols)
    orth = _zscore(orth)
    orth[Z.isna().all(axis=1)] = np.nan            # rows with no data stay NaN
    return orth


def orthogonal_composite(factors: pd.DataFrame, min_legs: int = 3) -> pd.Series:
    """Equal-weight mean of the ORTHOGONALIZED factors per row (re-z-scored) — the
    decorrelated composite. NaN where fewer than `min_legs` factors are present."""
    orth = orthogonalize(factors)
    avail = factors.notna().sum(axis=1)
    comp = orth.mean(axis=1, skipna=True)
    comp[avail < min_legs] = np.nan
    return _zscore(comp.to_frame("c"))["c"]


def overlap_diagnostics(factors: pd.DataFrame) -> dict:
    """How much the factors are 'one bet': cross-sectional correlation structure,
    VIF (>5 redundant), top correlated pairs, and the redundancy the orthogonalization
    removes (mean |off-diagonal corr| before vs ~0 after)."""
    Z = _zscore(factors).dropna()
    if len(Z) < 30 or Z.shape[1] < 2:
        return {}
    C = Z.corr().values
    n = C.shape[0]
    off = C[~np.eye(n, dtype=bool)]
    orth = orthogonalize(factors).dropna()
    Coff = orth.corr().values[~np.eye(orth.shape[1], dtype=bool)] if len(orth) else np.array([0.0])
    return {
        "mean_abs_corr_raw": round(float(np.mean(np.abs(off))), 3),
        "mean_abs_corr_orth": round(float(np.mean(np.abs(Coff))), 3),
        "vif": vif(Z),
        "top_pairs": top_correlated_pairs(Z, k=6, thresh=0.4),
    }
