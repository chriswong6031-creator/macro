"""PEAD freshness — does SUE get STRONGER when weighted by post-announcement freshness?

SUE is the only cross-sectional leg that survives FDR (audited IC ~0.039 at quarterly
cadence), but the live conviction score pools every name that filed in the last ~7 months
at equal weight — so a surprise from 6 months ago (whose drift has largely played out)
counts the same as one that landed last week. Post-earnings-announcement drift DECAYS over
~60-90 days, so weighting SUE by how RECENTLY the surprise was filed should concentrate the
edge on names still inside the active drift window — and make the score 'early / fast'
(it reacts the moment earnings land, fades as the drift is consumed).

This measures, on the deep + PIT survivorship-clean panel:
  * forward 63d sector-neutral rank-IC of: flat SUE (baseline) vs freshness-DECAY-weighted
    SUE vs SUE restricted to freshly-reported names (<=21d / <=45d / <=90d);
  * the long-only top-decile durability of each (the owner's lens).
If freshness-weighting lifts IC + the long-only profile, it earns a wiring into the engine.

Run:  .venv/bin/python -m scripts.pead_freshness_phase0 --horizon 63 --years 18
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
from engine.validation import rank_ic  # noqa: E402
from lib import config  # noqa: E402
from scripts.conviction_v2_regime import _metrics, long_only_decile  # noqa: E402
from scripts.residual_alpha_phase0 import (  # noqa: E402
    _closes_deep, _eligible, _load_membership, month_grid)

WIN = 252


def _sn(s: pd.Series, sec: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s - s.groupby(sec.reindex(s.index)).transform("mean")


def _latest_asof(panel: pd.DataFrame) -> dict:
    """Per ticker: a sorted np.array of filing as-of dates (for freshness lookup)."""
    out = {}
    for tic, g in panel.groupby("ticker"):
        out[tic] = np.sort(g["asof_date"].values)
    return out


def _freshness_days(asof_by_tic: dict, tickers, d) -> pd.Series:
    """Days since each ticker's most recent filing visible on `d` (NaN if none)."""
    dd = np.datetime64(pd.Timestamp(d), "D")
    out = {}
    for t in tickers:
        arr = asof_by_tic.get(t)
        if arr is None or not len(arr):
            continue
        a = arr.astype("datetime64[D]")
        i = np.searchsorted(a, dd, side="right") - 1
        if i >= 0:
            out[t] = int((dd - a[i]) / np.timedelta64(1, "D"))
    return pd.Series(out, dtype=float)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=63)
    ap.add_argument("--years", type=int, default=18)
    ap.add_argument("--tau", type=float, default=45.0, help="decay half-life (days)")
    args = ap.parse_args()

    closes = _closes_deep()
    membership = _load_membership()
    delp = config.data_dir() / "breadth" / "_closes_delisted.parquet"
    if delp.exists():
        closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
        closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    ns = _names_sectors()
    sec = pd.Series({t: (ns.get(t, (t, "Other"))[1] or "Other") for t in closes.columns})
    R = closes.pct_change(fill_method=None)
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)
    grid = month_grid(R.index, warmup=WIN + 42, horizon=args.horizon)
    if args.years:
        grid = [d for d in grid if d >= R.index.max() - pd.DateOffset(years=args.years)]

    panel = _sue.load_panel()
    if panel is None:
        print("no EPS panel"); return 1
    asof_by_tic = _latest_asof(panel)

    # build, per grid date, the candidate SUE variants as cross-sections
    variants = ("flat", "decay", "fresh<=21", "fresh<=45", "fresh<=90")
    ic = {k: [] for k in variants}
    mats = {k: {} for k in variants}
    fresh_counts = []
    for d in grid:
        sue = _sue.sue_cross_section(panel, d)
        if sue is None or sue.empty:
            continue
        if membership is not None:
            sue = sue[sue.index.isin(_eligible(membership, d))]
        if len(sue) < 25:
            continue
        fr = _freshness_days(asof_by_tic, sue.index, d)
        fr = fr.reindex(sue.index)
        fresh_counts.append(int((fr <= 90).sum()))
        cols = {
            "flat": sue,
            "decay": sue * np.exp(-fr.clip(lower=0) / args.tau),     # PEAD decay weight
            "fresh<=21": sue.where(fr <= 21),
            "fresh<=45": sue.where(fr <= 45),
            "fresh<=90": sue.where(fr <= 90),
        }
        frd = fwd.loc[d] if d in fwd.index else None
        for k, s in cols.items():
            s = s.dropna()
            mats[k][d] = s
            if frd is not None:
                ss = _sn(s, sec)
                fri = frd.reindex(ss.index).dropna()
                ss = ss.reindex(fri.index).dropna()
                if len(ss) >= 25:
                    ic[k].append(rank_ic(ss, fri.reindex(ss.index)))

    print(f"[pead] deep+PIT {closes.shape} · {len(grid)} rebal "
          f"{grid[0].date()}..{grid[-1].date()} · horizon {args.horizon}d · decay τ={args.tau:.0f}d")
    print(f"  median names filed <=90d/date: {int(np.median(fresh_counts)) if fresh_counts else 0}\n")
    print(f"  {'variant':12} {'meanIC':>8} {'IC-IR':>7} {'hit>0':>7} {'n':>5}")
    for k in variants:
        v = pd.Series(ic[k]).dropna()
        if len(v) >= 6:
            ir = v.mean() / v.std() if v.std() else 0.0
            print(f"  {k:12} {v.mean():>+8.4f} {ir:>7.3f} {float((v > 0).mean()):>7.2f} {len(v):>5}")

    print("\n  LONG-ONLY TOP-DECILE (top 10% by the SUE variant, EW, monthly, net 5bps) vs SPY:")
    spy = R.get("SPY")
    if spy is None or spy.dropna().empty:
        from lib import store
        _s = store.read("yahoo", "SPY")
        spy = _s["close"].reindex(closes.index).pct_change() if _s is not None else pd.Series(0.0, index=R.index)
    for k in variants:
        m = pd.DataFrame(mats[k]).T
        if m.empty:
            continue
        m.index = pd.to_datetime(m.index)
        sig = m.reindex(R.index).ffill(limit=args.horizon)
        net = long_only_decile(R, sig, grid, membership).loc[grid[0]:grid[-1]]
        mt = _metrics(net, spy)
        if mt:
            print(f"  {k:12} ann {mt['ann_ret_%']:>5}% · vol {mt['ann_vol_%']:>5}% · "
                  f"Sharpe {mt['sharpe']} · Sortino {mt['sortino']} · maxDD {mt['max_dd_%']:>6}% · "
                  f"excess {mt['excess_vs_spy_%']:>+5}% (SPY {mt['spy_ann_%']}%/DD {mt['spy_dd_%']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
