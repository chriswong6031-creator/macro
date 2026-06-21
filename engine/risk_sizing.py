"""Risk-based position sizing (engine v2) — the one VALIDATED free-Sharpe lever.

Our own backtests (research/MAGICAL_SIGNALS_ROADMAP.md) confirmed the Moreira-Muir
result: scaling exposure by INVERSE forecasted volatility lifts the book's Sharpe
(SPY 0.64->0.76, equal-weight 1.07->1.22) and compresses the left tail — with ZERO
directional-alpha required. This is a RISK lever, not a return source: it decides HOW
MUCH to own, never WHAT to own (selection stays the conviction score's job).

Two layers (Grinold-Kahn / DeMiguel-Martin-Utrera-Uppal):
  Layer A — per-name inverse-vol weighting so a single high-vol name can't dominate
            book risk (risk-parity approximation; full Ledoit-Wolf cov is overkill here).
  Layer B — a CAPPED (<=1.5) portfolio vol-target scalar that de-grosses in stress.
The load-bearing reconciliation (research): the book de-grosses in high-vol regimes,
but the regime gate may simultaneously rotate the remaining risk toward the signals
that pay there — so `regime_gross` is passed in by the caller, never decided here.

Forecast = HAR multi-scale realized vol (engine.vol_forecast.cone_vol_ann), the
cheapest cost-robust persistent-vol predictor. All point-in-time (close <= as_of).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import vol_forecast

# inverse-vol multiplier clamp: never zero a name, never let a calm name 3x the book
_MULT_LO, _MULT_HI = 0.40, 2.50
_VOL_TARGET_CAP = 1.50          # Layer-B gross scalar cap (uncapped leverage erodes net)
_DEFAULT_TARGET_VOL = 0.22      # annualized book vol budget when no universe ref is given


def forecast_vol_ann(close: pd.Series) -> float | None:
    """Point-in-time annualized forward-vol estimate for one name (HAR), or None."""
    v = vol_forecast.cone_vol_ann(close.dropna())
    v = v.dropna()
    return float(v.iloc[-1]) if len(v) and np.isfinite(v.iloc[-1]) and v.iloc[-1] > 0 else None


def assess(close: pd.Series, *, universe_vol_ann: float | None = None,
           regime_gross: float = 1.0) -> dict | None:
    """Per-name vol-managed sizing read. `universe_vol_ann` = the cross-sectional median
    forecast vol (the risk-parity reference); `regime_gross` = the caller's dispersion/
    regime gross dial. Returns a `size_mult` to multiply the conviction-base size by, plus
    the components, or None when vol isn't computable.

    size_mult = clip(ref_vol / name_vol, .4, 2.5) * regime_gross  — bet LESS on high-vol
    names, MORE on calm ones, scaled by how favourable the regime is for taking risk.
    """
    vol_ann = forecast_vol_ann(close)
    if vol_ann is None:
        return None
    ref = universe_vol_ann or _DEFAULT_TARGET_VOL
    inv_vol_mult = float(np.clip(ref / vol_ann, _MULT_LO, _MULT_HI))
    size_mult = float(np.clip(inv_vol_mult * max(0.0, regime_gross), 0.0, 3.0))
    vp = vol_forecast.vol_regime(close.dropna()).dropna()
    vol_pct = float(vp.iloc[-1]) if len(vp) else None
    return {"vol_ann_pct": round(100 * vol_ann, 1),
            "vol_pct": round(vol_pct, 2) if vol_pct is not None else None,
            "inv_vol_mult": round(inv_vol_mult, 2),
            "regime_gross": round(float(regime_gross), 2),
            "size_mult": round(size_mult, 2)}


# ---- portfolio-level primitives (used by a sizing consumer / the Mastermind bot) ----

def inverse_vol_weights(vols: dict[str, float]) -> dict[str, float]:
    """Normalized inverse-vol weights for a set of names {ticker: vol_ann}. Layer-A
    risk parity: each name contributes ~equally to book risk. Drops non-positive vols."""
    inv = {t: 1.0 / v for t, v in vols.items() if isinstance(v, (int, float)) and v > 0}
    s = sum(inv.values())
    return {t: w / s for t, w in inv.items()} if s > 0 else {}


def vol_target_scalar(book_vol_forecast_ann: float, target_vol_ann: float = _DEFAULT_TARGET_VOL,
                      cap: float = _VOL_TARGET_CAP) -> float:
    """Layer-B gross scalar = target/forecast, CAPPED. <1 de-grosses in stress; the cap
    stops uncapped leverage (which erodes net performance — Barroso-Detzel)."""
    if not book_vol_forecast_ann or book_vol_forecast_ann <= 0:
        return 1.0
    return float(np.clip(target_vol_ann / book_vol_forecast_ann, 0.25, cap))


def book_forecast_vol_ann(weights: dict[str, float], vols: dict[str, float],
                          avg_corr: float = 0.35) -> float:
    """Crude book vol forecast from name vols + an assumed average correlation (a
    full covariance is unestimable/overfit on a large universe; a single avg-corr is
    the robust, shrinkage-equivalent approximation). sigma_book ~ sqrt(corr)*sum(w*sigma)
    for the correlated component + the diversifiable remainder."""
    items = [(weights.get(t, 0.0), vols.get(t)) for t in weights]
    items = [(w, v) for w, v in items if v and v > 0]
    if not items:
        return _DEFAULT_TARGET_VOL
    wv = np.array([w * v for w, v in items])
    common = avg_corr * (wv.sum() ** 2)
    idio = (1 - avg_corr) * (wv ** 2).sum()
    return float(np.sqrt(max(common + idio, 1e-9)))
