"""Conditional forward-distribution kernel — the math behind the Anticipation
Engine's multi-horizon cone, and the asset-agnostic generalization of the validated
BTC drawdown read in scripts/build_vector.py (_band_of / _fwd_dd / forward_risk).

Instead of hard-wiring risk_index ∈ {0,25,50,75,100}, it conditions ANY state series
on quantile bands and emits, per horizon, the empirical forward RETURN quantiles +
forward DRAWDOWN (avg dip + p05 tail) + P(up). Empirical quantiles cannot cross and
there are zero fitted weights, so there is nothing to overfit; the read degrades to
the marginal when a cell is thin.

POINT-IN-TIME: forward_paths never looks past date t for the FEATURE; the forward
columns are LABELS (future), all-NaN in the last `horizon` rows. For the LIVE engine,
band edges must come from an expanding/rolling estimate of the state distribution
(causal); full-sample edges are acceptable ONLY for the in-sample ordering test in
Phase-0 (the recompute-on-truncated test guards the live path separately).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_Q = (5, 25, 50, 75, 95)


def forward_paths(close: pd.Series, horizon: int) -> pd.DataFrame:
    """Per-date forward outcomes over the next `horizon` trading days (close-based):
      ret = end/now - 1, mae = worst dip (≤0), mfe = best pop (≥0), all in %.
    The last `horizon` rows are NaN (no future) — never look-ahead."""
    c = close.astype(float)
    fwd_end = c.shift(-horizon)
    fwd_min = c.shift(-1).rolling(horizon).min().shift(-(horizon - 1))
    fwd_max = c.shift(-1).rolling(horizon).max().shift(-(horizon - 1))
    return pd.DataFrame({
        "ret": 100.0 * (fwd_end / c - 1.0),
        "mae": 100.0 * (fwd_min / c - 1.0),
        "mfe": 100.0 * (fwd_max / c - 1.0),
    }, index=c.index)


def quantile_edges(s: pd.Series, k: int = 4) -> np.ndarray:
    """k equal-frequency band edges from a state series (deduped)."""
    qs = np.linspace(0.0, 1.0, k + 1)
    e = np.unique(np.nanquantile(s.astype(float).to_numpy(), qs))
    return e


def band_of(x: float, edges: np.ndarray) -> int | None:
    """Right-closed band index for x (first band is closed-left). None if NaN/out."""
    if x is None or not np.isfinite(x) or len(edges) < 2:
        return None
    if x <= edges[0]:
        return 0
    if x > edges[-1]:
        return len(edges) - 2
    for i in range(len(edges) - 1):
        if edges[i] < x <= edges[i + 1]:
            return i
    return None


def conditional_distribution(paths: pd.DataFrame, state: pd.Series, *, lo: float, hi: float,
                             incl_low: bool = False, mask: pd.Series | None = None,
                             qs=DEFAULT_Q, min_n: int = 20) -> dict | None:
    """Empirical forward distribution for the cell {state in (lo, hi]} (or [lo,hi] if
    incl_low). Return quantiles + drawdown (avg dip, p05 tail of mae) + median pop +
    P(up) + n. None if thinner than min_n."""
    st = state.reindex(paths.index)
    ret, mae, mfe = paths["ret"], paths["mae"], paths["mfe"]
    sel = ((st >= lo) if incl_low else (st > lo)) & (st <= hi) & ret.notna()
    if mask is not None:
        sel = sel & mask.reindex(paths.index).fillna(False)
    n = int(sel.sum())
    if n < min_n:
        return None
    r = ret[sel]
    return {
        "n": n,
        "ret_q": {f"p{q}": round(float(r.quantile(q / 100.0)), 2) for q in qs},
        "dd_avg": round(float(mae[sel].mean()), 2),
        "dd_tail": round(float(mae[sel].quantile(0.05)), 2),
        "mfe_med": round(float(mfe[sel].median()), 2),
        "p_up": round(float((r > 0).mean()), 3),
    }


def multi_horizon_cone(close: pd.Series, state: pd.Series, horizons: dict, *, k: int = 4,
                       edges: np.ndarray | None = None, min_n: int = 20,
                       qs=DEFAULT_Q) -> dict:
    """The cone: for the LIVE state band, the conditional forward distribution at each
    horizon in `horizons` ({name: trading_days}). `edges` should be a causal estimate
    for live use; if None, full-sample quantile edges are used (Phase-0 ordering test)."""
    st = state.reindex(close.index)
    if edges is None:
        edges = quantile_edges(st, k)
    sd = st.dropna()
    if not len(sd) or len(edges) < 2:
        return {"edges": list(map(float, edges)) if len(edges) else [], "band": None, "horizons": {}}
    now = float(sd.iloc[-1])
    bi = band_of(now, edges)
    out = {"edges": [round(float(e), 4) for e in edges], "band": bi,
           "now": round(now, 4), "horizons": {}}
    if bi is None:
        return out
    lo, hi = float(edges[bi]), float(edges[bi + 1])
    for name, h in horizons.items():
        d = conditional_distribution(forward_paths(close, h), st, lo=lo, hi=hi,
                                     incl_low=(bi == 0), min_n=min_n, qs=qs)
        out["horizons"][name] = {**(d or {"n": 0}), "horizon": h, "thin": (d is None or d["n"] < 150)}
    return out


def cond_up_prob(close: pd.Series, cell_key: pd.Series, horizon: int, *, alpha: int = 10,
                 min_n: int = 20, floor: float = 0.43, ceil: float = 0.58,
                 marginal: float | None = None) -> tuple[float, int, str]:
    """P(up over `horizon`) conditioned on the live `cell_key` value, empirical-Bayes
    shrunk to the marginal, capped to the empirically-observed reliable band
    [floor, ceil] (NOT a wide [0.30,0.70] — the repo's measured reliable-cell spread
    is ~52-57%). Thin cell → marginal. Generalization of build_vector._cond_up_prob."""
    fwd_up = (close.shift(-horizon) > close).astype(float)
    valid = fwd_up.notna() & cell_key.notna()
    if not valid.any():
        return 0.5, 0, "n/a"
    now = cell_key[valid].iloc[-1] if valid.iloc[-1] else cell_key.dropna().iloc[-1]
    base = float(fwd_up[valid].mean()) if marginal is None else marginal
    cm = valid & (cell_key == now)
    n = int(cm.sum())
    p = (float(fwd_up[cm].sum()) + alpha * base) / (n + alpha) if n > 0 else base
    if n < min_n:
        p = base
    return float(min(max(p, floor), ceil)), n, str(now)


def band_ordering(paths: pd.DataFrame, state: pd.Series, edges: np.ndarray, *,
                  field: str = "mae", mask: pd.Series | None = None, min_n: int = 20) -> list:
    """Per-band conditional mean of `field` (mae/ret/mfe) across all bands — the table
    whose MONOTONICITY the Phase-0 ordering test checks (does worsening state → fatter
    drawdown / lower return, monotonically?)."""
    rows = []
    for i in range(len(edges) - 1):
        d = conditional_distribution(paths, state, lo=float(edges[i]), hi=float(edges[i + 1]),
                                     incl_low=(i == 0), mask=mask, min_n=min_n)
        if d is None:
            rows.append({"band": i, "n": 0, "val": None})
            continue
        val = d["dd_avg"] if field == "mae" else (d["mfe_med"] if field == "mfe"
              else d["ret_q"]["p50"])
        rows.append({"band": i, "n": d["n"], "val": val, "dd_tail": d["dd_tail"], "p_up": d["p_up"]})
    return rows
