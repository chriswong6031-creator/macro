"""Trend QUALITY on the residual path — how a stock got its move, not how big it was.

Two stocks can both be +20% over the formation window: one gapped twice on takeover
chatter, the other accumulated for six months. Residual momentum scores them the same;
these measures separate them. Every measure is computed on the RESIDUAL path from
`engine.residual_momentum` (market/sector/factor already stripped), so "quality" means
quality of the stock-specific trend rather than a repackaged read on the market's.

The nine measures (the build request's list, in its order):

  slope_t        OLS slope of the cumulative residual vs time / its standard error
  pos_days       share of days with a positive residual
  impulse_legs   count of independent advance legs (zig-zag on the residual path)
  max_dd         deepest drawdown of the cumulative residual inside the window
  top3_share     share of the window's TOTAL absolute daily move in its largest 3 days
  ud_vol         upside vs downside volume (volume on up-residual days / down days)
  atr_dist       distance from trend origin in ATR units
  resid_vs_hist  current residual trend vs this name's own longer residual history
  resid_accel    residual momentum acceleration -- SEE THE KILL NOTE BELOW

KILL NOTE (`resid_accel`). Acceleration was PRE-REGISTERED AND KILLED in the Phase-0
work behind research/RESIDUAL_ALPHA_MOMENTUM.md: significantly ANTI-predictive on the
deep 1964-2026 panel (full-history IC -0.012, t -2.7), and dropped from the shipped
engine for that reason. It is implemented here because the request names it and because
a measured null belongs in the open, but it is DIAGNOSTIC ONLY: `QUALITY_MEASURES`
excludes it, so it never enters the composite, and `composite()` will not accept it.
Re-promoting it needs a fresh pre-registered gate, not a re-import.

Sign convention: every measure in `QUALITY_MEASURES` is oriented so HIGHER = better
trend quality, so the composite can be a plain mean of z-scores rather than a table of
remembered signs. Only `top3_share` is negated to get there (`_NEGATED`); `max_dd` is
already oriented, since a shallow drawdown is a larger number than a deep one.

Causality: measures read a trailing window ending at the as-of bar. Nothing here
peeks forward; `tests/test_trend_quality.py` pins that against a shuffled future.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Higher = better, all of them. `resid_accel` is deliberately NOT here (see KILL NOTE).
QUALITY_MEASURES = ("slope_t", "pos_days", "impulse_legs", "max_dd", "top3_share",
                    "ud_vol", "atr_dist", "resid_vs_hist")

DIAGNOSTIC_MEASURES = ("resid_accel",)

MEASURE_LABELS = {
    "slope_t": "Trend t-stat (slope / std error)",
    "pos_days": "Positive residual days",
    "impulse_legs": "Independent impulse legs",
    "max_dd": "Max drawdown in trend (negated)",
    "top3_share": "Top-3-day concentration (negated)",
    "ud_vol": "Upside vs downside volume",
    "atr_dist": "Distance from trend origin (ATR)",
    "resid_vs_hist": "Residual trend vs own history",
    "resid_accel": "Residual acceleration (KILLED — diagnostic only)",
}

# A measure whose "good" direction is inverted before z-scoring, so the composite can
# be a plain mean. Documented here rather than in eight scattered sign flips.
#
# `max_dd` is deliberately NOT here: it is already <= 0 and already oriented, because a
# shallow drawdown (-0.01) is a LARGER number than a deep one (-0.50). Negating it would
# rank the deepest drawdown best — a sign error that still produces a plausible-looking
# composite, which is why tests/test_trend_quality.py pins the ordering directly.
_NEGATED = ("top3_share",)


def _slope_t(y: np.ndarray) -> float:
    """t-statistic of the OLS slope of `y` on time — trend strength scaled by its own
    noise. This is the request's 'regression slope divided by its standard error':
    a steady grinder and a violent zig-zag with the same endpoints score very
    differently, which is the entire point of the battery."""
    n = len(y)
    if n < 10:
        return np.nan
    x = np.arange(n, dtype=float)
    x -= x.mean()
    sxx = float((x * x).sum())
    if sxx <= 0:
        return np.nan
    beta = float((x * (y - y.mean())).sum() / sxx)
    resid = y - y.mean() - beta * x
    dof = n - 2
    if dof <= 0:
        return np.nan
    se2 = float((resid * resid).sum()) / dof / sxx
    if not np.isfinite(se2) or se2 <= 0:
        return np.nan
    return beta / np.sqrt(se2)


def _impulse_legs(path: np.ndarray, thresh: float) -> float:
    """Count INDEPENDENT advance legs in a cumulative path with a zig-zag filter: a new
    leg is only counted once the path has retraced `thresh` from its running peak and
    then advanced `thresh` again. `thresh` is a volatility unit, so the count does not
    silently become 'how volatile is this name'. One clean 6-month advance -> 1; a
    stair-step of four distinct pushes -> 4."""
    if len(path) < 10 or not np.isfinite(thresh) or thresh <= 0:
        return np.nan
    legs, peak, trough, advancing = 0, path[0], path[0], False
    for v in path:
        if advancing:
            peak = max(peak, v)
            if v <= peak - thresh:            # gave back a unit -> leg over
                advancing, trough = False, v
        else:
            trough = min(trough, v)
            if v >= trough + thresh:          # advanced a unit -> new leg
                advancing, peak, legs = True, v, legs + 1
    return float(legs)


def _max_dd(path: np.ndarray) -> float:
    """Deepest peak-to-trough fall of the cumulative residual inside the window
    (<= 0). Negated by the caller so higher = shallower = better."""
    if len(path) < 2:
        return np.nan
    return float((path - np.maximum.accumulate(path)).min())


def _top3_share(eps: np.ndarray) -> float:
    """Share of the window's total ABSOLUTE daily residual movement contributed by its
    three largest days. Denominator is the sum of |daily move|, NOT the net return —
    a net return near zero would otherwise divide a real concentration into nonsense
    (and flip sign on a losing name)."""
    if len(eps) < 5:
        return np.nan
    a = np.abs(eps)
    tot = float(a.sum())
    if tot <= 0:
        return np.nan
    return float(np.sort(a)[-3:].sum() / tot)


def _ud_vol(eps: np.ndarray, vol: np.ndarray) -> float:
    """log ratio of volume on up-residual days to volume on down-residual days.
    Log so that 2x-up and 2x-down are symmetric around 0 instead of squashed into
    [0,1] vs [1,inf)."""
    if len(eps) < 10 or len(vol) != len(eps):
        return np.nan
    up, dn = vol[eps > 0], vol[eps < 0]
    if len(up) < 3 or len(dn) < 3:
        return np.nan
    mu, md = float(np.nanmean(up)), float(np.nanmean(dn))
    if not np.isfinite(mu) or not np.isfinite(md) or mu <= 0 or md <= 0:
        return np.nan
    return float(np.log(mu / md))


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float:
    """Mean true range over the window (Wilder's TR, simple mean)."""
    if len(close) < 2:
        return np.nan
    pc = close[:-1]
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - pc), np.abs(low[1:] - pc)))
    tr = tr[np.isfinite(tr)]
    return float(tr.mean()) if len(tr) else np.nan


def measures(eps: pd.Series, close: pd.Series, *, high: pd.Series | None = None,
             low: pd.Series | None = None, volume: pd.Series | None = None,
             hist_eps: pd.Series | None = None) -> dict:
    """All nine measures for ONE name over ONE trailing window.

    `eps`/`close` are the window slice; `hist_eps` is the LONGER residual history used
    by `resid_vs_hist` (the window itself is excluded inside). Missing optional inputs
    yield NaN for the measures that need them — an absent measure stays absent rather
    than defaulting to a neutral value that would read as a real measurement."""
    e = pd.to_numeric(eps, errors="coerce").dropna()
    if len(e) < 10:
        return {k: np.nan for k in QUALITY_MEASURES + DIAGNOSTIC_MEASURES}
    ev = e.to_numpy(float)
    path = np.cumsum(ev)
    sd = float(np.std(ev))
    out: dict[str, float] = {
        "slope_t": _slope_t(path),
        "pos_days": float((ev > 0).mean()),
        "impulse_legs": _impulse_legs(path, thresh=2.0 * sd * np.sqrt(max(len(ev) // 21, 1))),
        "max_dd": _max_dd(path),
        "top3_share": _top3_share(ev),
        "ud_vol": np.nan,
        "atr_dist": np.nan,
        "resid_vs_hist": np.nan,
        "resid_accel": np.nan,
    }

    if volume is not None:
        v = pd.to_numeric(volume, errors="coerce").reindex(e.index).to_numpy(float)
        out["ud_vol"] = _ud_vol(ev, v)

    # distance from trend ORIGIN (window start) in ATR units — "how extended is it?"
    c = pd.to_numeric(close, errors="coerce").reindex(e.index).dropna()
    if len(c) >= 2 and high is not None and low is not None:
        h = pd.to_numeric(high, errors="coerce").reindex(c.index).to_numpy(float)
        lo_ = pd.to_numeric(low, errors="coerce").reindex(c.index).to_numpy(float)
        atr = _atr(h, lo_, c.to_numpy(float))
        if np.isfinite(atr) and atr > 0:
            out["atr_dist"] = float((c.iloc[-1] - c.iloc[0]) / atr)

    # current residual trend vs this name's OWN longer history (z of window mean)
    if hist_eps is not None:
        hv = pd.to_numeric(hist_eps, errors="coerce").dropna()
        hv = hv[~hv.index.isin(e.index)]          # exclude the window being scored
        if len(hv) >= 60:
            mu, s = float(hv.mean()), float(hv.std())
            if np.isfinite(s) and s > 0:
                out["resid_vs_hist"] = float((float(e.mean()) - mu) / s)

    # DIAGNOSTIC ONLY — killed prior, see the module KILL NOTE.
    if len(ev) >= 40:
        half = len(ev) // 2
        out["resid_accel"] = float(ev[half:].mean() - ev[:half].mean())
    return out


def panel(eps: pd.DataFrame, closes: pd.DataFrame, *, form: int, skip: int = 0,
          highs: pd.DataFrame | None = None, lows: pd.DataFrame | None = None,
          volumes: pd.DataFrame | None = None, hist_mult: int = 3,
          asof=None, min_names: int = 10) -> pd.DataFrame:
    """Trend-quality measures for every name at ONE as-of bar -> DataFrame(ticker x measure).

    The scored window is the same [t-skip-form, t-skip] slice `residual_momentum`
    forms its signal over, so quality describes the SAME trend the momentum score
    ranks — scoring a different window would answer a different question."""
    if eps is None or eps.empty:
        return pd.DataFrame()
    idx = eps.index if asof is None else eps.index[eps.index <= pd.Timestamp(asof)]
    if len(idx) < form + skip + 10:
        log.warning("trend_quality: history too short (%d < %d)", len(idx), form + skip + 10)
        return pd.DataFrame()
    end = len(idx) - skip
    win = idx[max(end - form, 0):end]
    hist = idx[max(end - form * hist_mult, 0):end]

    rows: dict[str, dict] = {}
    for t in eps.columns:
        if t not in closes.columns:
            continue
        rows[t] = measures(
            eps[t].reindex(win), closes[t].reindex(win),
            high=highs[t].reindex(win) if highs is not None and t in highs.columns else None,
            low=lows[t].reindex(win) if lows is not None and t in lows.columns else None,
            volume=volumes[t].reindex(win) if volumes is not None and t in volumes.columns else None,
            hist_eps=eps[t].reindex(hist))
    out = pd.DataFrame(rows).T
    if len(out) < min_names:
        return pd.DataFrame()
    return out


def _z(s: pd.Series, cap: float = 3.0) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)
    mu, sd = s.mean(), s.std()
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.nan, index=s.index)
    return ((s - mu) / sd).clip(-cap, cap)


def composite(tq: pd.DataFrame, *, measures_used: tuple = QUALITY_MEASURES,
              min_measures: int = 4, sectors: pd.Series | None = None) -> pd.Series:
    """Equal-weight mean of the z-scored, sign-aligned quality measures.

    Equal weight ON PURPOSE: fitting weights on the same panel the composite is then
    scored against is how a scorecard grades its own homework. If the harness shows a
    subset carries all the signal, that is a finding to pre-register, not a weight to
    quietly tune here.

    Raises on a diagnostic (killed) measure rather than silently dropping it — a caller
    asking for `resid_accel` in a ranker has made a mistake worth surfacing."""
    bad = [m for m in measures_used if m in DIAGNOSTIC_MEASURES]
    if bad:
        raise ValueError(f"diagnostic-only measure(s) cannot enter the composite: {bad} "
                         "(see engine/trend_quality.py KILL NOTE)")
    cols = [m for m in measures_used if m in tq.columns]
    if not cols:
        return pd.Series(dtype=float)
    z = pd.DataFrame({m: _z(-tq[m] if m in _NEGATED else tq[m]) for m in cols})
    if sectors is not None:                       # sector-neutral variant
        s = sectors.reindex(z.index)
        z = z.sub(z.groupby(s).transform("mean"))
    out = z.mean(axis=1, skipna=True)
    out[z.notna().sum(axis=1) < min_measures] = np.nan
    return out
