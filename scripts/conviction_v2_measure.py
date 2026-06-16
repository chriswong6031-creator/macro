"""Conviction v2 — per-leg forward-return IC measurement (research/STOCK_CONVICTION_V2.md).

Measures every CANDIDATE selection leg on the deep + point-in-time survivorship-aware
S&P 500 panel: mean sector-neutral rank-IC, IC-IR, Newey-West HAC t, BH-FDR q, and the
top-vs-bottom-quintile net L/S Sharpe + Deflated Sharpe. This is the EMPIRICAL decision
that sets the v2 evidence-weights — a leg gets scored weight only if it earns it here.

Reuses the validated plumbing in scripts.residual_alpha_phase0 (deep/PIT loaders, causal
residuals, quintile_ls, month_grid) + engine.predictive_signals (the new price legs) +
engine.validation (rank_ic, ic_summary, BH-FDR, DSR).

Run:  .venv/bin/python -m scripts.conviction_v2_measure --horizon 63 --pit
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import predictive_signals as ps  # noqa: E402
from engine.equity_factors import _names_sectors  # noqa: E402
from engine.validation import (benjamini_hochberg, deflated_sharpe, ic_summary,  # noqa: E402
                                rank_ic, ret_moments)
from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import (_closes_deep, _eligible, _load_membership,  # noqa: E402
                                           _yahoo_ret, build_residuals, ew_peer,
                                           month_grid, quintile_ls, signal_matrices)


def _sn(s: pd.Series, sec: pd.Series) -> pd.Series:
    """Sector-neutral demean (within-GICS), the scale every leg is scored on."""
    return s - s.groupby(sec.reindex(s.index)).transform("mean")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=63)
    ap.add_argument("--win", type=int, default=252)
    ap.add_argument("--form", type=int, default=252)
    ap.add_argument("--skip", type=int, default=21)
    ap.add_argument("--pit", action="store_true", default=True)
    ap.add_argument("--start", type=int, default=1996)
    args = ap.parse_args()

    closes = _closes_deep()
    if closes.empty:
        print("no deep matrix — run scripts.residual_alpha_fetch"); return 1
    membership = _load_membership() if args.pit else None
    if args.pit and membership is None:
        print("no PIT membership — run scripts.residual_alpha_pit"); return 1
    delp = config.data_dir() / "breadth" / "_closes_delisted.parquet"
    if args.pit and delp.exists():
        closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
        closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    if args.start:
        closes = closes.loc[closes.index >= f"{args.start}-01-01"]
    ns = _names_sectors()
    tkr_sector = {t: (ns.get(t, (t, "—"))[1] or "—") for t in closes.columns}
    tkr_sector = {t: (s if s != "—" else "Other") for t, s in tkr_sector.items()}
    sec = pd.Series(tkr_sector)
    spy = _yahoo_ret("SPY", closes.index)
    spy_px = closes.get("SPY")  # for downside_asym market (price series ok)
    if spy_px is None:
        from lib import store
        _s = store.read("yahoo", "SPY"); spy_px = _s["close"].reindex(closes.index) if _s is not None else None

    # residual baseline legs (validated plumbing)
    R, eps = build_residuals(closes, spy, tkr_sector, ew_peer, args.win, max(args.win // 2, 40))
    base = signal_matrices(R, eps, args.form, args.skip)   # ir_res, mom_res, mom_tot, rev_st, acc_res
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)
    grid = month_grid(R.index, warmup=args.win + args.skip + args.form, horizon=args.horizon)
    print(f"[measure] panel {closes.shape} · grid {len(grid)} rebalances "
          f"{grid[0].date()}..{grid[-1].date()} · horizon {args.horizon}d · PIT={args.pit}")

    # candidate legs: matrix-based (baseline) + as-of price legs (the v2 new ones)
    MATRIX_LEGS = {"ir_res": base["ir_res"], "mom_res": base["mom_res"], "mom_tot": base["mom_tot"]}
    ASOF_LEGS = {
        "fip_continuity": lambda d: ps.fip_continuity(closes, d, args.form, args.skip),
        "near_52w_high": lambda d: ps.near_52w_high(closes, d, args.win),
        "max_caution": lambda d: ps.max_caution(closes, d, 21),
        "downside_asym": (lambda d: ps.downside_asym(closes, d, spy_px, args.win)) if spy_px is not None else None,
    }
    ASOF_LEGS = {k: v for k, v in ASOF_LEGS.items() if v is not None}

    ic = {k: [] for k in list(MATRIX_LEGS) + list(ASOF_LEGS)}
    nseries = []
    for d in grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if membership is not None:
            fr = fr[fr.index.isin(_eligible(membership, d))]
        if len(fr) < 25:
            continue
        nseries.append(len(fr))
        for k, mat in MATRIX_LEGS.items():
            if d in mat.index:
                s = mat.loc[d].reindex(fr.index).dropna()
                if len(s) >= 25:
                    ic[k].append(rank_ic(_sn(s, sec), fr.reindex(s.index)))
        for k, fn in ASOF_LEGS.items():
            s = fn(d)
            s = s.reindex(fr.index).dropna()
            if len(s) >= 25:
                ic[k].append(rank_ic(_sn(s, sec), fr.reindex(s.index)))

    rows, pvals = {}, {}
    for k, series in ic.items():
        summ = ic_summary(pd.Series(series).dropna(), periods_per_year=12)
        if summ.get("n", 0) >= 6:
            rows[k] = summ
            if summ.get("p_hac") is not None:
                pvals[k] = summ["p_hac"]
    for k, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[k]["q_fdr"] = q["q"]; rows[k]["survives_fdr"] = q["reject"]

    # quintile L/S net Sharpe + DSR for the matrix legs + a couple of as-of legs built into matrices
    asof_mat = {}
    for k, fn in ASOF_LEGS.items():
        m = pd.DataFrame({d: fn(d) for d in grid}).T
        m.index = pd.to_datetime(m.index)
        asof_mat[k] = m.reindex(R.index).ffill(limit=args.horizon)
    ls = {}
    for k in list(MATRIX_LEGS) + list(ASOF_LEGS):
        sig = MATRIX_LEGS.get(k, asof_mat.get(k))
        try:
            ls[k] = quintile_ls(R, sig, grid, args.horizon, n_trials=len(rows), membership=membership)
        except Exception as e:  # noqa: BLE001
            ls[k] = {"error": str(e)[:60]}

    # print the IC table (sorted by IC-IR)
    print(f"\n  median universe/date: {int(np.median(nseries)) if nseries else 0}")
    print(f"\n  {'leg':16} {'meanIC':>8} {'IC-IR':>7} {'t-HAC':>7} {'p':>7} {'q-FDR':>7} {'FDR?':>5} {'LS-Shrp':>8} {'DSR':>6} {'n':>4}")
    order = sorted(rows, key=lambda k: -(rows[k].get("ic_ir") or -9))
    for k in order:
        r = rows[k]; l = ls.get(k, {})
        print(f"  {k:16} {r.get('mean_ic',0):>8.4f} {r.get('ic_ir',0) or 0:>7.3f} "
              f"{r.get('t_hac',0) or 0:>7.2f} {r.get('p_hac',1) or 1:>7.3f} "
              f"{r.get('q_fdr',1) or 1:>7.3f} {str(r.get('survives_fdr','')):>5} "
              f"{(l.get('sharpe') if isinstance(l,dict) else 0) or 0:>8.2f} "
              f"{(l.get('dsr') if isinstance(l,dict) else 0) or 0:>6.2f} {r.get('n',0):>4}")
    print("\n  (SUE IC ~0.039 / insider ~0.029 measured separately in the deep-PIT factor audit.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
