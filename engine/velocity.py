"""Velocity / acceleration of deterioration — the one genuinely NEW factor axis
of the Anticipation Engine (the user's "velocity of worsening technicals").

It measures the RATE (1st derivative) and ACCELERATION (2nd derivative) at which a
name's technicals/breadth/relative-strength are deteriorating, plus a denoised
momentum impulse and a realized-variance velocity (the only market-applicable
critical-slowing-down early-warning — rising variance, per Guttal 2016; lag-1
autocorrelation is deliberately NOT computed, it doesn't trend before market crashes).

HONESTY GATE (load-bearing): the codebase already TESTED and DROPPED velocity/
acceleration of residual momentum as a CROSS-SECTIONAL RETURN predictor
(engine/residual_alpha.py). So these features are intended to feed the RISK / VOL
(cone-width) side of the forecast ONLY — never P(up) — until/unless a leg earns its
own Phase-0 pass. They are pure, causal, point-in-time transforms (the recompute-on-
truncated == full test must hold). Reuses indicators.slope_z / rolling_slope.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import indicators


def efficiency_ratio(close: pd.Series, n: int = 10) -> pd.Series:
    """Kaufman efficiency ratio over `n` bars: |net change| / Σ|daily change| ∈ [0,1].
    1 = a clean directional move, ~0 = chop. Denoises the momentum impulse so a
    whippy tape doesn't read as a strong acceleration."""
    change = close.diff(n).abs()
    vol = close.diff().abs().rolling(n).sum()
    return (change / vol.replace(0, np.nan)).clip(0.0, 1.0)


def _macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    ef = close.ewm(span=fast, adjust=False).mean()
    es = close.ewm(span=slow, adjust=False).mean()
    macd = ef - es
    return macd - macd.ewm(span=sig, adjust=False).mean()


def _zscore(s: pd.Series, win: int) -> pd.Series:
    m = s.rolling(win, min_periods=max(20, win // 2))
    return (s - m.mean()) / m.std(ddof=0).replace(0, np.nan)


def impulse(close: pd.Series, *, fast: int = 12, slow: int = 26, sig: int = 9,
            er_n: int = 10, z_win: int = 60) -> pd.Series:
    """Price-only momentum impulse = z(MACD histogram) × efficiency-ratio — a
    denoised 2nd-derivative of price (the histogram is already the slope of the MACD
    slope). Port of engine/btc_signals.impulse with the funding/OI legs dropped (no
    equity equivalent). Positive = accelerating up, negative = accelerating down."""
    return _zscore(_macd_hist(close, fast, slow, sig), z_win) * efficiency_ratio(close, er_n)


def velocity_features(close: pd.Series, *, bench: pd.Series | None = None,
                      breadth: pd.Series | None = None, slope_w: int = 20,
                      base_w: int = 60, accel_w: int = 10) -> pd.DataFrame:
    """Per-name deterioration features, all causal/point-in-time:

      trend_vel   t-stat of the trailing slope_w drift (slope_z) — NEGATIVE = the
                  price trend is deteriorating; steady trend keeps scoring.
      trend_accel 2nd derivative = rolling_slope of trend_vel — NEGATIVE & getting
                  more negative = deterioration is ACCELERATING.
      rs_vel      same on relative strength (close/bench) — relative deterioration.
      breadth_vel slope_z of a market breadth series (shared) — participation fading.
      impulse     denoised momentum impulse (above).
      rvar_vel    slope of log rolling realized variance — RISING variance is the
                  market-valid critical-slowing-down early-warning (cone widener).

    Lower (more negative) trend_vel/accel/rs_vel and higher rvar_vel all map to a
    WIDER / more-left-skewed forward cone — the RISK side only.
    """
    out = pd.DataFrame(index=close.index)
    out["trend_vel"] = indicators.slope_z(close, slope_w, base_w, use_log=True)
    out["trend_accel"] = indicators.rolling_slope(out["trend_vel"], accel_w)
    if bench is not None and len(bench):
        rs = close / bench.reindex(close.index).ffill()
        out["rs_vel"] = indicators.slope_z(rs, slope_w, base_w, use_log=True)
    if breadth is not None and len(breadth):
        bser = breadth.reindex(close.index).ffill()
        out["breadth_vel"] = indicators.slope_z(bser, slope_w, base_w, use_log=False)
    out["impulse"] = impulse(close, z_win=base_w)
    rvar = close.pct_change(fill_method=None).pow(2).rolling(slope_w).mean()
    out["rvar_vel"] = indicators.rolling_slope(np.log(rvar.replace(0, np.nan)), accel_w)
    return out


def deterioration_z(feats: pd.DataFrame) -> pd.Series:
    """Single deterioration composite (higher = worse/faster deterioration), built
    only from the RISK-side velocity legs. Sign convention: + means trend down +
    accelerating down + relative weakness + rising variance. Used to CONDITION the
    cone width / tail, never to set direction. Equal-weight of available legs
    (no learned weights — forecast-combination puzzle)."""
    legs = []
    if "trend_vel" in feats:
        legs.append(-feats["trend_vel"])
    if "trend_accel" in feats:
        legs.append(-feats["trend_accel"].pipe(_zscore, 252))
    if "rs_vel" in feats:
        legs.append(-feats["rs_vel"])
    if "rvar_vel" in feats:
        legs.append(feats["rvar_vel"].pipe(_zscore, 252))
    if not legs:
        return pd.Series(index=feats.index, dtype=float)
    return pd.concat(legs, axis=1).mean(axis=1)
