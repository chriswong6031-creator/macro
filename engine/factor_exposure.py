"""Per-ticker risk-factor EXPOSURE — what bets is this name (or book) really making?

`engine.equity_factors` ranks names by cross-sectional z-RANK on each style factor
("is it cheap / high-quality?"). That is not the same question as "what macro/style
risks am I actually exposed to?" This module regresses each name's daily returns on
a small set of OBSERVABLE, tradeable factor proxies to recover its EXPOSURE betas:
market, size, momentum, the dollar, semis/AI, crypto. Aggregated over a book it
surfaces the hidden one-way bet — five "different" tickers that are really one
long-semis / short-dollar trade.

This is an EXPOSURE measurement, NOT a return forecast: betas describe risk, they
do not predict alpha (see reports/factor-exposure-sanity.md). Guardrails against
the classic multi-factor overfit trap:
  • a SMALL, fixed, observable factor set (no data-mined factors);
  • every non-market factor ORTHOGONALISED to the market within the window, so a
    beta reads as exposure BEYOND market direction, not double-counted market;
  • causal trailing windows (the snapshot uses only the last `win` days);
  • a VIF check that drops any residually-collinear factor (engine.validation.vif);
  • R² and t-stats carried through, so a noisy fit reads as noisy.

Additive leaf — nothing in the scoring path imports it.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.validation import vif
from lib import config, store

log = logging.getLogger(__name__)

# key -> (store group, series id, column, kind, EN, ZH). 'market' is the base;
# every other factor is orthogonalised to it within the window. kind 'price' →
# pct-change of the close; 'yield' → daily change in the rate level (so a positive
# 'rates' beta = benefits from RISING 10y yields). All keyless price/FRED stores.
FACTORS: dict[str, tuple] = {
    "market":   ("yahoo", "SPY", "close", "price", "Market", "大盘"),
    "size":     ("yahoo", "IWM", "close", "price", "Size (small-cap)", "小盘"),
    "momentum": ("yahoo", "MTUM", "close", "price", "Momentum", "动量"),
    "usd":      ("yahoo", "DX-Y.NYB", "close", "price", "US dollar", "美元"),
    "semis":    ("yahoo", "SMH", "close", "price", "Semis / AI", "半导体/AI"),
    "crypto":   ("yahoo", "BTC-USD", "close", "price", "Crypto", "加密"),
    "oil":      ("yahoo", "CL_F", "close", "price", "Oil", "原油"),
    "rates":    ("fred", "DGS10", "us10y", "yield", "Rates (10y)", "利率(10年)"),
}


def _cfg() -> dict:
    base = {"win": 252, "min_obs": 180, "vif_thresh": 5.0, "sig_t": 2.0,
            "min_history": 300}
    return {**base, **(config.load().get("engine", {}).get("factor_exposure", {}) or {})}


def factor_returns() -> pd.DataFrame:
    """RAW daily returns of the factor proxies (one column per available factor).
    Orthogonalisation to the market happens per-window inside ``exposure`` so it
    uses only that window's data."""
    cols = {}
    for key, (grp, sid, col, kind, *_) in FACTORS.items():
        d = store.read(grp, sid)
        if d is None or col not in getattr(d, "columns", []):
            continue
        s = d[col].astype(float)
        cols[key] = s.diff() if kind == "yield" else s.pct_change(fill_method=None)
    if "market" not in cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).dropna(how="all")


def _orthogonalise(df: pd.DataFrame) -> pd.DataFrame:
    """Residualise every non-market factor on the market (within the given window)."""
    m = df["market"]
    mv = float(m.var())
    out = {"market": m}
    for k in df.columns:
        if k == "market":
            continue
        b = (df[k].cov(m) / mv) if mv > 0 else 0.0
        out[k] = df[k] - b * m
    return pd.DataFrame(out, index=df.index)


def _vif_prune(F: pd.DataFrame, thresh: float) -> pd.DataFrame:
    """Drop the worst residually-collinear NON-market factor until all VIF<=thresh.
    Market is always kept (it is the anchor)."""
    cols = list(F.columns)
    while len(cols) > 2:
        v = vif(F[cols])
        worst, worstv = None, thresh
        for k, val in v.items():
            if k != "market" and val is not None and val > worstv:
                worst, worstv = k, val
        if worst is None:
            break
        cols.remove(worst)
    return F[cols]


def _ols(y: np.ndarray, X: np.ndarray):
    """OLS with a const column already in X. Returns (beta, tstat, r2, resid_std)."""
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    n, k = X.shape
    dof = max(n - k, 1)
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.maximum(np.diag(sigma2 * xtx_inv), 1e-18))
    t = beta / se
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return beta, t, r2, float(np.sqrt(sigma2))


def exposure(stock_ret: pd.Series, fac_ret: pd.DataFrame, cfg: dict | None = None) -> dict | None:
    """Factor-exposure betas for one name over the trailing window.

    Returns standardised betas (per 1-SD factor move, comparable across factors),
    HAC-free t-stats, R², and each factor's share of explained variance. The
    'dominant' field is the largest non-market exposure — the hidden bet.
    """
    c = cfg or _cfg()
    win, minp = int(c["win"]), int(c["min_obs"])
    df = pd.concat([stock_ret.rename("y"), fac_ret], axis=1).dropna()
    if len(df) < minp:
        return None
    df = df.tail(win)
    y_raw = df["y"]
    F = _orthogonalise(df.drop(columns="y"))
    F = _vif_prune(F, float(c["vif_thresh"]))
    sy = float(y_raw.std())
    if sy <= 0:
        return None
    keys = list(F.columns)
    X = np.column_stack([np.ones(len(df))] + [F[k].values for k in keys])
    beta, t, r2, _ = _ols(y_raw.values, X)

    betas = {}
    for i, k in enumerate(keys, start=1):
        sx = float(F[k].std())
        std_beta = beta[i] * sx / sy                      # per-1-SD, comparable
        betas[k] = {"beta": round(float(std_beta), 2), "raw": round(float(beta[i]), 3),
                    "t": round(float(t[i]), 2),
                    "contrib": round(float(std_beta ** 2), 3),
                    "label": FACTORS[k][4], "label_zh": FACTORS[k][5]}
    nonmkt = {k: v for k, v in betas.items() if k != "market"}
    sig_nonmkt = {k: v for k, v in nonmkt.items() if abs(v["t"]) >= float(c["sig_t"])}
    dominant = max(sig_nonmkt, key=lambda k: abs(sig_nonmkt[k]["beta"]), default=None)
    return {"asof": str(df.index[-1].date()), "n": int(len(df)), "r2": round(r2, 2),
            "market_beta": betas.get("market", {}).get("beta"),
            "betas": betas, "dominant": dominant,
            "dominant_label": FACTORS[dominant][4] if dominant else None,
            "dominant_label_zh": FACTORS[dominant][5] if dominant else None}


def book_exposure(weights: dict[str, float], expo_map: dict[str, dict]) -> dict | None:
    """Weighted-average factor betas across a book → net exposure + the hidden
    one-way bet (the dominant net factor and the share of names that load on it)."""
    rows = [(t, w, expo_map[t]) for t, w in weights.items()
            if t in expo_map and expo_map[t]]
    tot = sum(abs(w) for _, w, _ in rows)
    if not rows or tot <= 0:
        return None
    net: dict[str, float] = {}
    for _, w, e in rows:
        for k, v in e["betas"].items():
            net[k] = net.get(k, 0.0) + (w / tot) * v["beta"]
    nonmkt = {k: v for k, v in net.items() if k != "market"}
    dominant = max(nonmkt, key=lambda k: abs(nonmkt[k]), default=None)
    aligned = 0
    if dominant:
        s = np.sign(net[dominant])
        aligned = sum(1 for _, _, e in rows
                      if dominant in e["betas"] and np.sign(e["betas"][dominant]["beta"]) == s)
    return {"net": {k: round(v, 2) for k, v in net.items()},
            "dominant": dominant,
            "dominant_label": FACTORS[dominant][4] if dominant else None,
            "n_aligned": aligned, "n_total": len(rows),
            # the hidden one-way bet is mostly about ALIGNMENT (a majority of names
            # load the same way on one factor), with a modest residual-tilt floor
            # so a trivial all-large-cap tilt doesn't trip it.
            "concentrated": bool(dominant and aligned >= 0.7 * len(rows)
                                 and abs(net[dominant]) >= 0.25)}


def radar(expo_map: dict[str, dict], top: int = 12, sig_t: float = 2.0,
          exclude: set | None = None) -> dict:
    """For each non-market factor, the names most loaded on it (the pure bets) —
    the exposure analogue of the factor-rank leaderboards on factors.html. The
    factor proxies themselves are excluded so a factor never heads its own board."""
    exclude = exclude or {f[1] for f in FACTORS.values()}
    out: dict[str, list] = {k: [] for k in FACTORS if k != "market"}
    for tkr, e in expo_map.items():
        if not e or tkr in exclude:
            continue
        for k, v in e["betas"].items():
            if k == "market" or abs(v["t"]) < sig_t:
                continue
            out[k].append({"ticker": tkr, "beta": v["beta"], "t": v["t"],
                           "r2": e.get("r2")})
    for k in out:
        out[k].sort(key=lambda r: -abs(r["beta"]))
        out[k] = out[k][:top]
    return out
