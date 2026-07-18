"""engine/systematic_flows.py — Vol-control and CTA positioning proxies.

MSP W1 data-spine engine.  Pure-pandas deterministic computation from SPX
closes; no LLM, no network.  Full-history backcast at first run (MSP-R9).

PUBLIC API
----------
vc_exposure(closes, aum_bn, target_vol, w_fast, w_slow) -> pd.DataFrame
    Vol-control (volatility-targeting) mechanical-flow proxy.

cta_positioning(closes, windows) -> pd.DataFrame
    Trend-follower (CTA) positioning proxy.

rv_cross_state(rv21, rv63) -> str
    "stress" when rv21 > rv63 (short-term vol elevated vs medium-term), else "calm".

flow_state(flow_5d, deadband) -> str
    "adding" / "pausing" / "cutting" from a 5-day flow change.

agreement(vc_state, cta_state) -> str
    "aligned_adding" / "aligned_cutting" / "paused" / "split".

HOUSE LAWS (MSP)
----------------
* MSP-R3: NO fused numeric composite of VC+CTA in any key or column.
* MSP-R8: deterministic price arithmetic only — no LLM touches any number.
* MSP-R9: compute over the ENTIRE close history passed in.
* Display-tier context only (is_context_only=True, display_only=True).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_TRADING_YEAR = 252

# ---------------------------------------------------------------------------
# Vol-control proxy
# ---------------------------------------------------------------------------

def vc_exposure(
    closes: pd.Series,
    aum_bn: float = 300.0,
    target_vol: float = 0.10,
    w_fast: int = 21,
    w_slow: int = 63,
) -> pd.DataFrame:
    """Vol-control (volatility-targeting) fund exposure proxy.

    Simulates a stylised vol-targeting fund that allocates AUM×min(1, σ_target /
    max(RV21, RV63)) to the equity index, then computes the daily flow implied
    by changes in that allocation.

    Construction
    ------------
    rv21, rv63 : annualised close-to-close realised volatility over 21 and 63
        trading days (same formula as engine/vol_forecast.realized_vol, daily
        units scaled by sqrt(252)).
    alloc_frac : min(1.0, target_vol / max(rv21, rv63)).  Capped at 1 — the
        fund cannot lever beyond 100% of AUM in this model.  Near-zero vol
        rows produce alloc_frac = 1 (fully allocated).
    alloc_bn   : aum_bn × alloc_frac  (billions).
    flow_bn    : alloc_bn.diff()  — positive = adding exposure, negative = cutting.

    Parameters
    ----------
    closes    : pd.Series of SPX (or any index) daily closes.  Entire history is used.
    aum_bn    : representative AUM in billions (default 300 — a stylised mid-size
                vol-targeting fund).  The AUM assumption is printed in Tier-2 context.
    target_vol: annualised vol target (default 0.10 = 10%).
    w_fast    : fast RV window in trading days (default 21 = ~1 month).
    w_slow    : slow RV window in trading days (default 63 = ~3 months).

    Returns
    -------
    pd.DataFrame with columns: rv21, rv63, alloc_frac, alloc_bn, flow_bn.
    Leading NaNs appear until both windows fill.

    Notes
    -----
    This is a REPRESENTATIVE ESTIMATE.  Real vol-targeting managers use
    different AUM assumptions, windows, leverage limits, rebalancing frequencies,
    and slippage models.  The estimate captures the directional mechanical
    pressure, not any specific fund's actual behaviour.  "Managers differ."
    """
    closes = closes.sort_index().astype(float)
    rets = closes.pct_change(fill_method=None)

    # Annualised realised vol (daily units × sqrt(252))
    rv_fast = rets.rolling(w_fast, min_periods=max(2, w_fast // 2)).std(ddof=0) * np.sqrt(_TRADING_YEAR)
    rv_slow = rets.rolling(w_slow, min_periods=max(2, w_slow // 2)).std(ddof=0) * np.sqrt(_TRADING_YEAR)

    # Control allocation: use the higher of the two windows to be conservative
    rv_max = pd.concat([rv_fast, rv_slow], axis=1).max(axis=1)
    # Avoid division by zero (first bar, zero-vol periods)
    rv_max_safe = rv_max.replace(0.0, np.nan)

    alloc_frac = (target_vol / rv_max_safe).clip(upper=1.0)
    alloc_bn = aum_bn * alloc_frac
    flow_bn = alloc_bn.diff()

    return pd.DataFrame({
        "rv21":       rv_fast,
        "rv63":       rv_slow,
        "alloc_frac": alloc_frac,
        "alloc_bn":   alloc_bn,
        "flow_bn":    flow_bn,
    }, index=closes.index)


# ---------------------------------------------------------------------------
# CTA positioning proxy
# ---------------------------------------------------------------------------

def cta_positioning(
    closes: pd.Series,
    windows: tuple[int, ...] = (20, 50, 100, 200),
) -> pd.DataFrame:
    """Trend-follower (CTA / managed-futures) positioning proxy.

    Constructs a vol-normalised trend signal for each lookback window, averages
    them into a single positioning score, and derives a z-score vs a 252-day
    trailing distribution.

    Construction
    ------------
    For each window w:
        trend_w  = (closes / closes.shift(w) − 1)         (total return)
        daily_vol = rolling(21d).std(pct_change)           (short-term daily vol)
        signal_w  = trend_w / (daily_vol × sqrt(w))        (vol-normalised)
        signal_w  = clip(signal_w, −3, +3)                 (bounded)

    cta_score = mean of all signal_w (already bounded by construction).
    cta_z     = (cta_score − rolling_252d_mean) / rolling_252d_std
                (standardised positioning; z > 0 = long-biased vs history).
    cta_flow  = cta_score.diff()  (day-over-day change in positioning).

    Interpretation
    --------------
    * Uptrends  → positive score (all windows bullish → score ~ +1 to +2).
    * Downtrends → negative score.
    * Flat tape  → score near zero (no persistent trend to follow).
    * cta_z > +1: CTAs are positioned long vs their own history — potential
      squeeze fuel on a reversal.

    No lookahead: at each date t, only close[≤t] is used.

    Parameters
    ----------
    closes  : pd.Series of daily closes.
    windows : tuple of lookback windows (default 20, 50, 100, 200 — standard
              CTA trend-following horizons).

    Returns
    -------
    pd.DataFrame with columns: cta_score, cta_z, cta_flow.

    Notes
    -----
    REPRESENTATIVE ESTIMATE.  Real CTA managers weight windows differently,
    use futures instead of spot, apply entry/exit thresholds, and manage
    position limits at the portfolio level.  This proxy captures the direction
    and magnitude of typical trend-following mechanical pressure across horizons
    commonly used in the industry.  "Managers differ."
    """
    closes = closes.sort_index().astype(float)
    rets = closes.pct_change(fill_method=None)

    # Short-term daily vol used for vol-normalisation (21d rolling)
    daily_vol = rets.rolling(21, min_periods=11).std(ddof=0)
    daily_vol_safe = daily_vol.replace(0.0, np.nan)

    signals = []
    for w in windows:
        # Total return over window w
        trend = closes / closes.shift(w) - 1.0
        # Vol-normalise: divide by vol × sqrt(window)
        vn = daily_vol_safe * np.sqrt(w)
        sig = (trend / vn).clip(-3.0, 3.0)
        signals.append(sig)

    cta_score = pd.concat(signals, axis=1).mean(axis=1)

    # Z-score vs trailing 252d (PIT: only history available at each date)
    roll_mean = cta_score.rolling(252, min_periods=63).mean()
    roll_std  = cta_score.rolling(252, min_periods=63).std(ddof=0)
    roll_std_safe = roll_std.replace(0.0, np.nan)
    cta_z = (cta_score - roll_mean) / roll_std_safe

    cta_flow = cta_score.diff()

    return pd.DataFrame({
        "cta_score": cta_score,
        "cta_z":     cta_z,
        "cta_flow":  cta_flow,
    }, index=closes.index)


# ---------------------------------------------------------------------------
# State classifiers
# ---------------------------------------------------------------------------

def rv_cross_state(rv21: float | None, rv63: float | None) -> str:
    """'stress' when short-term vol (rv21) > medium-term vol (rv63), else 'calm'."""
    if rv21 is None or rv63 is None:
        return "unknown"
    try:
        return "stress" if float(rv21) > float(rv63) else "calm"
    except (TypeError, ValueError):
        return "unknown"


def flow_state(flow_5d: float | None, deadband: float = 1.0, *, mode: str = "vc") -> str:
    """Classify 5-day cumulative flow into 'adding' / 'pausing' / 'cutting'.

    Parameters
    ----------
    flow_5d  : 5-day rolling sum of daily flow values.
    deadband : absolute threshold for the 'pausing' band.
               VC mode default = 1.0 (billion USD; |flow_5d_bn| < 1.0 → pausing).
               CTA mode default = 0.02 (dimensionless score units).
    mode     : 'vc' or 'cta' (informational only; deadband is set by the caller).
    """
    if flow_5d is None:
        return "pausing"
    try:
        f = float(flow_5d)
    except (TypeError, ValueError):
        return "pausing"
    if abs(f) < deadband:
        return "pausing"
    return "adding" if f > 0 else "cutting"


def agreement(vc_state: str, cta_state: str) -> str:
    """Categorical agreement between VC and CTA states.

    Rules (strict, per MSP-R3 — no blending):
        both adding   → "aligned_adding"
        both cutting  → "aligned_cutting"
        both pausing  → "paused"
        anything else → "split"
    """
    if vc_state == "adding" and cta_state == "adding":
        return "aligned_adding"
    if vc_state == "cutting" and cta_state == "cutting":
        return "aligned_cutting"
    if vc_state == "pausing" and cta_state == "pausing":
        return "paused"
    return "split"
