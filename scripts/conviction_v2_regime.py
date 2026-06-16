"""Conviction v2 — is the edge real once measured CORRECTLY? (research/STOCK_CONVICTION_V2)

The unconditional dollar-neutral 63d IC test said 'nothing beats baseline'. This probes
the three ways that test may UNDERSTATE the achievable edge:
  1. REGIME-CONDITIONAL IC — factor edges are regime-dependent; unconditional averaging
     washes them out. Split the grid by PIT price-regime (SPY trend, realized-vol, cross-
     sectional dispersion) and measure each leg's IC WITHIN each regime.
  2. LONG-ONLY TOP-DECILE — a long investor holds the top names, never shorts. The short
     side is where momentum L/S bleeds; the long-only top decile can be positive when L/S
     is not. Measure ann return / maxDD / Sortino / hit-rate vs SPY (the durability + return
     of the stock actually purchased — the owner's real objective).
  3. (reported) the same, per regime.

Legs: momentum (residual-alpha IR z, the v1 baseline) and edge (the REAL validated SUE,
engine.sue, sector-neutral z). Deep + PIT survivorship-clean S&P 500 panel.

Run:  .venv/bin/python -m scripts.conviction_v2_regime --years 18
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import sue as _sue  # noqa: E402
from engine.equity_factors import _names_sectors  # noqa: E402
from engine.validation import ic_summary, rank_ic  # noqa: E402
from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import (  # noqa: E402
    _closes_deep, _eligible, _load_membership, _yahoo_ret, build_residuals, ew_peer, month_grid)

WIN, FORM, SKIP, COST = 252, 252, 21, 5.0 / 1e4


def _sn(s: pd.Series, sec: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    g = s.groupby(sec.reindex(s.index))
    return (s - g.transform("mean"))


def _metrics(net: pd.Series, bench: pd.Series) -> dict:
    net = net.dropna()
    if len(net) < 60:
        return {}
    ann = float(net.mean() * 252); vol = float(net.std() * np.sqrt(252))
    cum = (1 + net).cumprod()
    dd = float((cum / cum.cummax() - 1).min() * 100)
    dn = net[net < 0].std() * np.sqrt(252)
    b = bench.reindex(net.index).fillna(0)
    bann = float(b.mean() * 252); bcum = (1 + b).cumprod()
    bdd = float((bcum / bcum.cummax() - 1).min() * 100)
    return {"ann_ret_%": round(ann * 100, 1), "ann_vol_%": round(vol * 100, 1),
            "sharpe": round(ann / vol, 2) if vol else None,
            "sortino": round(ann / float(dn), 2) if dn else None,
            "max_dd_%": round(dd, 1), "excess_vs_spy_%": round((ann - bann) * 100, 1),
            "spy_ann_%": round(bann * 100, 1), "spy_dd_%": round(bdd, 1)}


def long_only_decile(R, sig, grid, membership, frac=0.1, horizon=21):
    """Long the top `frac` by signal each rebalance, EW, monthly, net of cost. Returns the
    daily net return series."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        if d not in sig.index:
            continue
        s = sig.loc[d].dropna()
        if membership is not None:
            s = s[s.index.isin(_eligible(membership, d))]
        if len(s) < 20:
            continue
        top = s[s >= s.quantile(1 - frac)].index
        if len(top):
            w.loc[d, top] = 1.0 / len(top)
    w = w.replace(0.0, np.nan).ffill(limit=horizon).fillna(0.0)
    pos = w.shift(1)
    gross = (pos * R.clip(-0.5, 0.5)).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    return (gross - COST * turn)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=18)
    ap.add_argument("--horizon", type=int, default=63)
    args = ap.parse_args()

    closes = _closes_deep()
    membership = _load_membership()
    delp = config.data_dir() / "breadth" / "_closes_delisted.parquet"
    if delp.exists():
        closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
        closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    ns = _names_sectors()
    tkr_sector = {t: (ns.get(t, (t, "—"))[1] or "Other") for t in closes.columns}
    tkr_sector = {t: (s if s != "—" else "Other") for t, s in tkr_sector.items()}
    sec = pd.Series(tkr_sector)
    spy_px = _yahoo_ret("SPY", closes.index)  # returns (not price) — build needs ret series
    R = closes.pct_change(fill_method=None)
    spy = R.get("SPY")
    if spy is None:
        from lib import store
        s = store.read("yahoo", "SPY"); spy = s["close"].reindex(closes.index).pct_change() if s is not None else spy_px

    # momentum (residual IR z)
    _, eps = build_residuals(closes, spy, tkr_sector, ew_peer, WIN, max(WIN // 2, 40))
    ir = (eps.shift(SKIP).rolling(FORM, min_periods=FORM // 2).mean()
          / eps.shift(SKIP).rolling(FORM, min_periods=FORM // 2).std())
    grid = month_grid(R.index, warmup=WIN + SKIP + FORM, horizon=args.horizon)
    if args.years:
        grid = [d for d in grid if d >= R.index.max() - pd.DateOffset(years=args.years)]

    # real SUE per grid date
    eps_panel = _sue.load_panel()
    sue_by_d = {d: _sue.sue_cross_section(eps_panel, d) for d in grid} if eps_panel is not None else {}

    # PIT price regimes (causal): SPY trend (vs 200dma), realized-vol tercile, dispersion
    spy_close = closes["SPY"] if "SPY" in closes else (1 + spy.fillna(0)).cumprod()
    sma200 = spy_close.rolling(200).mean()
    rvol = spy.rolling(63).std()
    rvol_hi = rvol > rvol.rolling(252, min_periods=120).median()
    disp = R.rolling(21).std().median(axis=1)
    disp_hi = disp > disp.rolling(252, min_periods=120).median()
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)

    legs = {"momentum": ir}
    # edge as a full matrix from the per-date SUE
    if sue_by_d:
        edge = pd.DataFrame({d: sue_by_d[d] for d in grid if sue_by_d[d] is not None and not sue_by_d[d].empty}).T
        edge.index = pd.to_datetime(edge.index)
        legs["edge_SUE"] = edge.reindex(R.index).ffill(limit=args.horizon)

    # ---- composites: the central hypothesis -----------------------------------
    # regime_switch: tilt to momentum in CALM/risk-on tape (SPY>200dma & lo-vol),
    #   tilt to the regime-robust SUE edge in STRESS (down-trend OR hi-vol). This is
    #   the proposed engine upgrade — does conditioning on the dashboard's own regime
    #   beat either leg standalone?  static_blend = the naive 50/50 rank average (the
    #   control: switching must beat a static combo to justify the added machinery).
    # downside-asymmetry (upside-beta minus downside-beta) — the convexity / limited-downside
    # RISK leg. It has ~zero forward-RETURN IC (measured), so it is NOT a return alpha; the
    # hypothesis is that tilting toward limited-downside names CUTS the basket's drawdown (the
    # asymmetry payoff a long owner wants), especially in stress where it matters most.
    from engine import predictive_signals as _ps  # noqa: E402
    asym_mat = None
    try:
        am = {}
        for d in grid:
            s = _ps.downside_asym(closes, d, spy_close, WIN)
            if s is not None and not s.empty:
                am[d] = s
        if am:
            asym_mat = pd.DataFrame(am).T; asym_mat.index = pd.to_datetime(asym_mat.index)
            asym_mat = asym_mat.reindex(R.index).ffill(limit=args.horizon)
            legs["downside_asym"] = asym_mat
    except Exception as e:  # noqa: BLE001
        print(f"  [asym] skipped: {e}")

    # low-volatility (Baker-Bradley-Wurgler) — the robust defensive factor. signal = NEGATIVE
    # trailing 126d realized vol, so the top decile is the LOWEST-vol names. The hypothesis
    # (the proper 'limited downside' lever the downside-asym proxy failed to deliver): a
    # stress-conditional low-vol tilt cuts the regime_switch basket's drawdown.
    rv126 = R.rolling(126, min_periods=80).std()
    lowvol = -rv126
    legs["low_vol"] = lowvol.reindex(R.index).ffill(limit=args.horizon)

    if "edge_SUE" in legs:
        mom, sue = legs["momentum"], legs["edge_SUE"]
        sw, bl, ra, rlv = {}, {}, {}, {}
        for d in grid:
            calm = (bool(spy_close.get(d, np.nan) >= sma200.get(d, np.nan))
                    and not bool(rvol_hi.get(d)))
            src = mom if calm else sue
            if d in src.index:
                sw[d] = src.loc[d]
            if d in mom.index and d in sue.index:
                bl[d] = (mom.loc[d].rank(pct=True) + sue.loc[d].rank(pct=True)) / 2.0
            sr = src.loc[d].rank(pct=True) if d in src.index else None
            # static 25% downside-asym risk-tilt (the convexity control)
            if sr is not None and asym_mat is not None and d in asym_mat.index:
                ra[d] = 0.75 * sr + 0.25 * asym_mat.loc[d].rank(pct=True)
            # low-vol tilt ONLY in stress (defensive when it matters; pure edge in calm)
            if sr is not None and d in lowvol.index:
                lr = lowvol.loc[d].rank(pct=True)
                rlv[d] = sr if calm else (0.6 * sr + 0.4 * lr)
        for name, dd in (("regime_switch", sw), ("static_blend", bl),
                         ("rs_asym_static", ra), ("rs_lowvol_stress", rlv)):
            if dd:
                m = pd.DataFrame(dd).T; m.index = pd.to_datetime(m.index)
                legs[name] = m.reindex(R.index).ffill(limit=args.horizon)

    print(f"[regime] deep+PIT panel {closes.shape} · {len(grid)} rebalances "
          f"{grid[0].date()}..{grid[-1].date()} · horizon {args.horizon}d\n")

    # ---- 1. regime-conditional IC --------------------------------------------
    def regime_label(d):
        up = bool(spy_close.get(d, np.nan) >= sma200.get(d, np.nan))
        return up
    print("  REGIME-CONDITIONAL IC (sector-neutral rank-IC within each price regime):")
    print(f"  {'leg':10} {'overall':>9} {'mkt-UP':>9} {'mkt-DOWN':>9} {'lo-vol':>9} {'hi-vol':>9} {'lo-disp':>9} {'hi-disp':>9}")
    for name, mat in legs.items():
        buckets = {k: [] for k in ("all", "up", "down", "lovol", "hivol", "lodisp", "hidisp")}
        for d in grid:
            if d not in fwd.index or d not in mat.index:
                continue
            fr = fwd.loc[d].dropna()
            if membership is not None:
                fr = fr[fr.index.isin(_eligible(membership, d))]
            s = _sn(mat.loc[d].reindex(fr.index).dropna(), sec)
            if len(s) < 25:
                continue
            ic = rank_ic(s, fr.reindex(s.index))
            buckets["all"].append(ic)
            (buckets["up"] if regime_label(d) else buckets["down"]).append(ic)
            (buckets["hivol"] if bool(rvol_hi.get(d)) else buckets["lovol"]).append(ic)
            (buckets["hidisp"] if bool(disp_hi.get(d)) else buckets["lodisp"]).append(ic)
        m = {k: (np.mean(v) if v else np.nan) for k, v in buckets.items()}
        print(f"  {name:10} {m['all']:>+9.4f} {m['up']:>+9.4f} {m['down']:>+9.4f} "
              f"{m['lovol']:>+9.4f} {m['hivol']:>+9.4f} {m['lodisp']:>+9.4f} {m['hidisp']:>+9.4f}")

    # ---- 2. LONG-ONLY top-decile durability (vs SPY) -------------------------
    print("\n  LONG-ONLY TOP-DECILE (top 10% by signal, EW, monthly, net 5bps) vs SPY buy&hold:")
    for name, mat in legs.items():
        net = long_only_decile(R, mat, grid, membership).loc[grid[0]:grid[-1]]
        mts = _metrics(net, spy)
        if mts:
            print(f"  {name:10} ann {mts['ann_ret_%']:>6}% · vol {mts['ann_vol_%']:>5}% · "
                  f"Sharpe {mts['sharpe']} · Sortino {mts['sortino']} · maxDD {mts['max_dd_%']:>6}% · "
                  f"excess vs SPY {mts['excess_vs_spy_%']:>+5}% (SPY {mts['spy_ann_%']}%/DD {mts['spy_dd_%']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
