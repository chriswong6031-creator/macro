"""Sector-neutral residual-momentum engine (research/RESIDUAL_ALPHA_MOMENTUM.md).

Phase 0 proved (deep 1962→2026 panel) that the operator's idea works in its
*durable* form: strip each stock's beta to the market AND its sector, and the
residual ("alpha") momentum — ranked WITHIN sector, over a medium horizon — picks
winners better than plain price momentum in the modern era. The two refinements
that DIDN'T survive were dropped: "velocity/acceleration" (anti-predictive) and
trusting the short timeframes as a picker (they are short-term REVERSAL — kept
here only as an entry-timing overlay, not the score).

Honest framing (shipped on the page): this is a modest, crowded, regime-decayed
edge — a ranking/context leg, NOT a standalone alpha engine. Nothing cleared the
strict BH-FDR/DSR bar on the modern era.

Construction (mirrors scripts/residual_alpha_phase0.py, the validated harness):
    r_i = a + b_m·m + b_s·s̃ + e_i      with s̃ = sector(EW-peer) ⟂ market
Because s̃ ⟂ m the two slopes decouple into causal univariate rolling betas
(252d, lagged 1d, Vasicek-lite shrunk). The score is the cross-sectional,
SECTOR-NEUTRAL z of the residual information ratio (mean/std of e over the 12-1
window). The last-month return is a separate reversal/entry overlay.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.equity_factors import _closes, _names_sectors, _winsor_z
from lib import config, store

log = logging.getLogger(__name__)

NOTE = ("Sector-neutral residual momentum: each stock's return with its market AND "
        "sector beta removed, ranked within its GICS sector over a 12-1-month window. "
        "A modest, regime-decayed edge — context, not a buy list.")


def _defaults() -> dict:
    cfg = config.load().get("engine_residual_alpha", {})
    return {"win": int(cfg.get("beta_win", 252)), "form": int(cfg.get("form", 252)),
            "skip": int(cfg.get("skip", 21)), "shrink": float(cfg.get("shrink", 0.66)),
            "top_n": int(cfg.get("top_n", 15)), "min_sector": int(cfg.get("min_sector", 6)),
            "min_names": int(cfg.get("min_names", 20)), "cap": float(cfg.get("winsor_z", 3.0))}


def _shrink(beta: pd.DataFrame, w: float) -> pd.DataFrame:
    """Vasicek-lite: pull each noisy per-stock beta toward the cross-sectional
    mean that day (w*raw + (1-w)*prior). w>=1 → no-op."""
    if w is None or w >= 1.0:
        return beta
    return beta.mul(w).add(beta.mean(axis=1).mul(1.0 - w), axis=0)


def _causal_beta(y, x, win: int, minp: int):
    """Rolling cov(y,x)/var(x), lagged one day (prior-window data only)."""
    return (y.rolling(win, min_periods=minp).cov(x)
            .div(x.rolling(win, min_periods=minp).var(), axis=0)).shift(1)


def residuals(closes: pd.DataFrame, market: pd.Series, tkr_sector: dict,
              win: int, shrink: float) -> pd.DataFrame:
    """Per-stock causal residual e_i = r_i - b_m·m - b_s·s̃  (s̃ ⟂ m)."""
    minp = max(win // 2, 15)
    R = closes.pct_change(fill_method=None)
    m = market.reindex(R.index)
    beta_m = _shrink(R.rolling(win, min_periods=minp).cov(m)
                     .div(m.rolling(win, min_periods=minp).var(), axis=0).shift(1), shrink)
    mkt_comp = beta_m.mul(m, axis=0)

    eps = pd.DataFrame(index=R.index, columns=R.columns, dtype=float)
    for sec in sorted(set(tkr_sector.get(t, "—") for t in R.columns)):
        cols = [t for t in R.columns if tkr_sector.get(t, "—") == sec]
        if not cols:
            continue
        s_raw = R[cols].mean(axis=1)                       # equal-weight peer basket
        beta_sm = _causal_beta(s_raw, m, win, minp)
        s_orth = s_raw - beta_sm * m                       # sector move beyond market
        beta_s = _shrink(_causal_beta(R[cols], s_orth, win, minp), shrink)
        eps[cols] = R[cols] - mkt_comp[cols] - beta_s.mul(s_orth, axis=0)
    return eps


def _entry(alpha: float | None, rev_pctile: float | None) -> str | None:
    """Reversal/entry overlay on top of the alpha rank (NOT the score itself).
    A leader that just spiked (high last-month percentile) is 'extended' — reversal
    risk; a leader on a recent pullback is a constructive entry."""
    if alpha is None or rev_pctile is None:
        return None
    if alpha >= 0.5:
        if rev_pctile >= 80:
            return "extended"      # leader, but ran hot — short-term reversal risk
        if rev_pctile <= 40:
            return "pullback"      # leader on a dip — constructive entry
        return "intact"
    if alpha <= -0.5:
        return "laggard"
    return "neutral"


def _f(x, nd: int = 2):
    return round(float(x), nd) if x is not None and np.isfinite(x) else None


def compute_residual_alpha(closes: pd.DataFrame | None = None,
                           market: pd.Series | None = None,
                           tkr_sector: dict | None = None, *, asof=None,
                           win=None, form=None, skip=None, shrink=None,
                           top_n=None, min_sector=None, min_names=None) -> dict | None:
    """Live cross-sectional sector-neutral residual-momentum read. Inputs are
    injectable for testing; when omitted they load from the live caches. Returns
    a JSON-able dict (overall leaders + per-sector leaders + per-ticker scores) or
    None if data is missing."""
    d_ = _defaults()
    win = d_["win"] if win is None else win
    form = d_["form"] if form is None else form
    skip = d_["skip"] if skip is None else skip
    shrink = d_["shrink"] if shrink is None else shrink
    top_n = d_["top_n"] if top_n is None else top_n
    min_sector = d_["min_sector"] if min_sector is None else min_sector
    min_names = d_["min_names"] if min_names is None else min_names
    cap = d_["cap"]

    if closes is None:
        closes = _closes()
    if closes is None or closes.empty:
        log.warning("residual_alpha: no close matrix")
        return None
    if asof is not None:
        closes = closes.loc[:pd.Timestamp(asof)]
    if market is None:
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns:
            log.warning("residual_alpha: no SPY market series")
            return None
        market = spy["close"].pct_change(fill_method=None)
        if asof is not None:
            market = market.loc[:pd.Timestamp(asof)]
    if tkr_sector is None:
        ns = _names_sectors()
        tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    else:
        ns = {t: (t, tkr_sector.get(t, "—")) for t in closes.columns}

    R = closes.pct_change(fill_method=None)
    eps = residuals(closes, market, tkr_sector, win, shrink)
    mp = max(form // 2, 10)

    # latest-window cross-section (causal: betas already lagged inside residuals())
    e_mean = eps.shift(skip).rolling(form, min_periods=mp).mean().iloc[-1]
    e_std = eps.shift(skip).rolling(form, min_periods=mp).std().iloc[-1]
    resid_ir = e_mean / e_std.replace(0, np.nan)
    total_mom = R.shift(skip).rolling(form, min_periods=mp).sum().iloc[-1] * 100.0
    rev_1m = R.rolling(skip, min_periods=max(skip // 2, 3)).sum().iloc[-1] * 100.0
    # DERIVED IBD-style RS context (subordinate to alpha; never feeds the z headline)
    _ret = lambda n: R.rolling(n, min_periods=max(n // 2, 10)).sum().iloc[-1] * 100.0
    rs_raw = pd.DataFrame({"rs3m": _ret(63), "rs6m": _ret(126), "rs12m": _ret(252)})

    d = pd.DataFrame({"resid_ir": resid_ir, "resid_ann": e_mean * 252 * 100.0,
                      "total_mom": total_mom, "rev_1m": rev_1m})
    d["sector"] = [tkr_sector.get(t, "—") for t in d.index]
    d = d[d["resid_ir"].notna() & (d["sector"] != "—")]
    if len(d) < min_names:
        log.warning("residual_alpha: too few names (%d < %d)", len(d), min_names)
        return None

    # headline score: SECTOR-NEUTRAL z of the residual information ratio
    sn = d["resid_ir"] - d.groupby("sector")["resid_ir"].transform("mean")
    d["alpha"] = _winsor_z(sn, cap)
    d = d[d["alpha"].notna()]
    d["rev_pctile"] = d["rev_1m"].rank(pct=True) * 100.0
    # RS = cross-sectional percentile (1-99). Headline RS ranks total_mom (12-1
    # trailing return, the IBD lens) so it is monotone with it; sub-horizons rank
    # fresh 3/6/12m returns. Derived context — alpha-z stays the headline.
    _p1_99 = lambda s: s.reindex(d.index).rank(pct=True) * 98.0 + 1.0
    d["rs"] = d["total_mom"].rank(pct=True) * 98.0 + 1.0
    d["rs3m"] = _p1_99(rs_raw["rs3m"])
    d["rs6m"] = _p1_99(rs_raw["rs6m"])
    d["rs12m"] = _p1_99(rs_raw["rs12m"])
    d["sector_n"] = d.groupby("sector")["alpha"].transform("count").astype(int)
    d["sector_rank"] = d.groupby("sector")["alpha"].rank(ascending=False).astype(int)

    def rec(t: str) -> dict:
        r = d.loc[t]
        return {"ticker": t, "name": ns.get(t, (t, "—"))[0], "sector": r["sector"],
                "alpha": _f(r["alpha"]), "resid_ann": _f(r["resid_ann"], 1),
                "total_mom": _f(r["total_mom"], 1), "rev_1m": _f(r["rev_1m"], 1),
                "rev_pctile": _f(r["rev_pctile"], 0),
                "sector_rank": int(r["sector_rank"]), "sector_n": int(r["sector_n"]),
                "entry": _entry(_f(r["alpha"]), _f(r["rev_pctile"], 0)),
                "rs": _f(r["rs"], 0), "rs3m": _f(r["rs3m"], 0),
                "rs6m": _f(r["rs6m"], 0), "rs12m": _f(r["rs12m"], 0)}

    by_sector: dict[str, dict] = {}
    for sec, sub in d.groupby("sector"):
        if len(sub) < min_sector:
            continue
        order = sub.sort_values("alpha", ascending=False)
        by_sector[sec] = {"n": int(len(sub)),
                          "leaders": [rec(t) for t in order.head(top_n).index],
                          "laggards": [rec(t) for t in order.tail(min(top_n, 5)).index][::-1]}

    top = [rec(t) for t in d.sort_values("alpha", ascending=False).head(top_n * 2).index]
    per_ticker = {t: {"alpha": _f(d.at[t, "alpha"]), "resid_ann": _f(d.at[t, "resid_ann"], 1),
                      "total_mom": _f(d.at[t, "total_mom"], 1), "rev_1m": _f(d.at[t, "rev_1m"], 1),
                      "rev_pctile": _f(d.at[t, "rev_pctile"], 0),
                      "sector_rank": int(d.at[t, "sector_rank"]),
                      "sector_n": int(d.at[t, "sector_n"]),
                      "entry": _entry(_f(d.at[t, "alpha"]), _f(d.at[t, "rev_pctile"], 0)),
                      "rs": _f(d.at[t, "rs"], 0), "rs3m": _f(d.at[t, "rs3m"], 0),
                      "rs6m": _f(d.at[t, "rs6m"], 0), "rs12m": _f(d.at[t, "rs12m"], 0)}
                  for t in d.index}

    return {"as_of": str(R.index.max().date()), "n": int(len(d)), "note": NOTE,
            "windows": {"beta_win": win, "form": form, "skip": skip, "shrink": shrink},
            "by_sector": by_sector, "top": top, "per_ticker": per_ticker}
