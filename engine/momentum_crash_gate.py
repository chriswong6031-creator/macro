"""Momentum crash gating — cut exposure in the states where momentum breaks, not after.

Momentum's return distribution is not merely volatile, it is LEFT-SKEWED: long stretches
of steady gains punctuated by rare, violent unwinds (Daniel-Moskowitz). Those unwinds are
not random — they cluster in a recognizable state: a market that has already fallen hard,
panic-level volatility, and then a sharp REBOUND in which the beaten-down prior losers
(now high-beta, small, distressed) rocket and the momentum book's short side detonates.
Barroso-Santa-Clara showed that scaling momentum by its own realized volatility removes
most of the crash; Moreira-Muir generalized volatility management across factors.

This module reads six conditions from the build request and turns them into one causal
exposure scalar:

  mom_vol       the momentum sleeve's own realized volatility is rising
  rebound       the market is rebounding abnormally fast (the crash trigger)
  xs_corr       cross-sectional correlations are spiking (everything moves as one)
  loser_run     prior LOSERS are violently outperforming prior winners
  breadth_rev   breadth is reversing upward after a severe drawdown
  extension     the signal is extremely extended from its trend origin

Each condition becomes a STRESS reading in [0,1] via a causal expanding percentile of
its own raw statistic — unit-free, self-calibrating, and comparable across conditions
without hand-set thresholds that would be fitted to whichever crash we last looked at.
`exposure()` maps mean stress to a scalar in [floor, 1].

WHY PERCENTILES, CAREFULLY: an expanding percentile uses only prior observations, so it
is causal, but it is also NOT stationary early in a sample — the first few years rank
against very little history. `min_history` blanks the scalar until enough observations
exist, so an early reading is ABSENT rather than confidently wrong.

Status: research/diagnostic. This gate sizes nothing live. Whether it beats the plain
Barroso-Santa-Clara vol-target baseline (`engine.vol_managed`) is an empirical question
the harness measures — a six-condition gate that does not beat one-line vol-scaling is
a more complicated way to be equally good, and the report says so either way.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CONDITIONS = ("mom_vol", "rebound", "xs_corr", "loser_run", "breadth_rev", "extension")

CONDITION_LABELS = {
    "mom_vol": "Momentum sleeve volatility rising",
    "rebound": "Market rebound speed extreme",
    "xs_corr": "Cross-sectional correlations spiking",
    "loser_run": "Prior losers violently outperforming",
    "breadth_rev": "Breadth reversing up after a drawdown",
    "extension": "Signal extended from trend origin",
}

TRADING_YEAR = 252


def causal_pctile(s: pd.Series, min_history: int = 252) -> pd.Series:
    """Expanding percentile of each observation against its OWN PRIOR history only.

    `.expanding().rank(pct=True)` includes the current point, which is fine (a value
    cannot rank against the future), but the result is blanked until `min_history`
    observations exist so an early, thinly-ranked reading is absent rather than
    presented as a confident extreme."""
    s = pd.to_numeric(s, errors="coerce")
    out = s.expanding(min_periods=2).rank(pct=True)
    out[s.expanding().count() < min_history] = np.nan
    return out


def _drawdown(cum: pd.Series) -> pd.Series:
    return cum / cum.cummax() - 1.0


def _conditional_stress(stat: pd.Series, active: pd.Series, min_history: int) -> pd.Series:
    """Percentile a statistic that is only MEANINGFUL while `active` is true.

    Returns the causal percentile where active, 0.0 where inactive (the state carries
    no stress by construction), and NaN where active but the conditional history is
    still too thin to rank — three distinct answers that a single `fillna(0.0)` would
    flatten into two."""
    pct = causal_pctile(stat.where(active), min_history)
    return pct.where(active, 0.0).where(stat.notna())


def conditions(mom_ret: pd.Series | None = None, *, market_ret: pd.Series | None = None,
               panel_ret: pd.DataFrame | None = None,
               loser_ret: pd.Series | None = None, winner_ret: pd.Series | None = None,
               breadth: pd.Series | None = None, extension: pd.Series | None = None,
               vol_win: int = 63, rebound_win: int = 21, corr_win: int = 63,
               dd_thresh: float = -0.15, min_history: int = 252,
               cond_min_history: int = 60) -> pd.DataFrame:
    """The six stress readings as a causal date x condition frame, each in [0,1].

    Every input is optional: a condition whose input is missing is simply ABSENT from
    the frame (not filled with 0.5), so `exposure()` averages what was actually
    measured. Silently substituting a neutral value would let a gate built on two live
    conditions read as if all six had voted."""
    out: dict[str, pd.Series] = {}

    # 1. the momentum sleeve's own realized vol (Barroso-Santa-Clara's core variable)
    if mom_ret is not None and len(mom_ret.dropna()) > vol_win:
        rv = mom_ret.rolling(vol_win, min_periods=vol_win // 2).std() * np.sqrt(TRADING_YEAR)
        out["mom_vol"] = causal_pctile(rv, min_history)

    if market_ret is not None and len(market_ret.dropna()) > rebound_win:
        cum = (1.0 + market_ret.fillna(0.0)).cumprod()
        dd = _drawdown(cum)
        # 2. rebound speed — the trigger, and only DURING a drawdown state. A fast
        # advance at an all-time high is a bull market, not a bear-market rebound;
        # gating on it would cut exposure in exactly the regime momentum works best.
        speed = market_ret.rolling(rebound_win, min_periods=rebound_win // 2).sum()
        in_dd = dd.rolling(rebound_win, min_periods=1).min() <= dd_thresh
        # OUTSIDE a drawdown the stress is genuinely ZERO (there is no bear-market
        # rebound to fear at an all-time high). INSIDE one with too little drawdown
        # history to rank against, it is UNMEASURABLE and must stay NaN. Collapsing
        # both to 0.0 would report "calm" for "cannot tell" — the fail-open this
        # module exists to avoid. `cond_min_history` counts IN-DRAWDOWN observations
        # only, since that is all these conditional series ever accumulate.
        out["rebound"] = _conditional_stress(speed, in_dd, cond_min_history)

        # 5. breadth reversing UP after a severe drawdown
        if breadth is not None:
            b = pd.to_numeric(breadth, errors="coerce").reindex(market_ret.index)
            out["breadth_rev"] = _conditional_stress(b.diff(rebound_win), in_dd,
                                                     cond_min_history)

    # 3. cross-sectional correlation spike — average pairwise correlation, estimated
    # from the ratio of index variance to mean constituent variance (an O(N) identity)
    # rather than an N^2 correlation matrix per bar.
    if panel_ret is not None and not panel_ret.empty:
        ew = panel_ret.mean(axis=1)
        var_ew = ew.rolling(corr_win, min_periods=corr_win // 2).var()
        mean_var = panel_ret.rolling(corr_win, min_periods=corr_win // 2).var().mean(axis=1)
        n_eff = panel_ret.notna().sum(axis=1).clip(lower=2)
        # var(EW) = mean_var*[1/n + (1-1/n)*rho_bar]  ->  solve for rho_bar
        rho = ((var_ew / mean_var.replace(0, np.nan)) - 1.0 / n_eff) / (1.0 - 1.0 / n_eff)
        out["xs_corr"] = causal_pctile(rho.clip(-1, 1), min_history)

    # 4. prior losers violently outperforming prior winners
    if loser_ret is not None:
        spread = loser_ret - winner_ret if winner_ret is not None else loser_ret
        run = spread.rolling(rebound_win, min_periods=rebound_win // 2).sum()
        out["loser_run"] = causal_pctile(run, min_history)

    # 6. extension of the signal from its trend origin (caller supplies the raw stat,
    # e.g. cross-sectional median ATR distance from engine.trend_quality)
    if extension is not None:
        out["extension"] = causal_pctile(pd.to_numeric(extension, errors="coerce"), min_history)

    if not out:
        log.warning("momentum_crash_gate: no condition had usable inputs")
        return pd.DataFrame()
    return pd.DataFrame(out)


def exposure(cond: pd.DataFrame, *, floor: float = 0.0, cap: float = 1.0,
             min_conditions: int = 2, lag: int = 1) -> pd.Series:
    """Map the stress frame to a tradeable exposure scalar in [floor, cap].

    exposure = clip(1 - mean(stress), floor, cap), then SHIFTED by `lag` bars. The
    shift is the difference between a gate and a backtest artifact: stress at bar t is
    known only at t's close, so the position it implies can only be held from t+1.

    NaN where fewer than `min_conditions` conditions are live — a one-condition gate
    is a vol filter wearing a crash gate's name."""
    if cond is None or cond.empty:
        return pd.Series(dtype=float)
    live = cond.notna().sum(axis=1)
    stress = cond.mean(axis=1, skipna=True)
    out = (1.0 - stress).clip(lower=floor, upper=cap)
    out[live < min_conditions] = np.nan
    return out.shift(lag)


def gate_series(mom_ret: pd.Series, **kw) -> dict:
    """Convenience: conditions + exposure + the gated sleeve, in one call.
    Returns the frame, the scalar, and `mom_ret` scaled by it (NaN scalar -> flat)."""
    floor = kw.pop("floor", 0.0)
    cap = kw.pop("cap", 1.0)
    min_conditions = kw.pop("min_conditions", 2)
    lag = kw.pop("lag", 1)
    cond = conditions(mom_ret, **kw)
    exp = exposure(cond, floor=floor, cap=cap, min_conditions=min_conditions, lag=lag)
    gated = mom_ret * exp.reindex(mom_ret.index).fillna(0.0)
    return {"conditions": cond, "exposure": exp, "gated": gated}


def live_read(cond: pd.DataFrame, exp: pd.Series) -> dict | None:
    """Latest per-condition stress + the resulting scalar, for a status panel.
    None when the gate has not opened yet (insufficient history)."""
    if cond is None or cond.empty or exp is None or exp.empty:
        return None
    last = cond.dropna(how="all")
    if last.empty:
        return None
    row = last.iloc[-1]
    scalar = exp.dropna()
    return {
        "as_of": str(last.index[-1].date()),
        "exposure": round(float(scalar.iloc[-1]), 3) if len(scalar) else None,
        "stress": {c: (round(float(row[c]), 3) if pd.notna(row.get(c)) else None)
                   for c in CONDITIONS if c in row.index},
        "conditions_live": sorted(c for c in CONDITIONS if c in row.index and pd.notna(row[c])),
        "conditions_absent": sorted(c for c in CONDITIONS if c not in row.index or pd.isna(row[c])),
    }
