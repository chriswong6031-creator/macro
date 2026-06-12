"""Research: which sector-entry conditions actually carried forward excess
return vs SPY, 2000->present. Grid over RS-momentum formation windows, holding
horizons, trend filters, and regime alignment — including a split-half check
(fit nothing; just report both halves so regime-conditional results aren't
sold on in-sample flukes).

Run: .venv/bin/python -m scripts.research_playbook
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.inputs import yahoo_closes  # noqa: E402
from lib import config  # noqa: E402

SPLIT = "2017-01-01"


def stats(vals: pd.Series) -> str:
    v = vals.dropna()
    if len(v) < 40:
        return f"n={len(v)} (too few)"
    return (f"n={len(v):5d}  hit={100 * (v > 0).mean():5.1f}%  "
            f"avg={100 * v.mean():+6.2f}%  med={100 * v.median():+6.2f}%")


def main() -> None:
    closes = yahoo_closes()
    bench = closes["SPY"]
    sectors = [t for t in config.load()["yahoo"]["tickers"]["sectors"]
               if t in closes.columns]
    hist = pd.read_parquet(config.ROOT / "data/regime/regime_history.parquet")
    hist.index = pd.to_datetime(hist.index)
    quad = hist["quad"].reindex(closes.index)
    prefs = config.load()["engine"]["sector_preferences"]

    weekly = pd.Series(False, index=closes.index)
    weekly.iloc[::5] = True

    print("=" * 100)
    for fwd in (21, 63, 126):
        spy_fwd = bench.pct_change(fwd).shift(-fwd)
        for form in (20, 60, 120, 252):
            rows = {"mom>0": [], "mom>0_above200": [], "mom>0_below200": [],
                    "top3_mom": [], "aligned_mom>0": [], "aligned": []}
            # build per-date momentum rank for top3
            rs_all = {t: closes[t] / bench for t in sectors}
            mom_all = pd.DataFrame({t: rs_all[t].pct_change(form) for t in sectors})
            rank = mom_all.rank(axis=1, ascending=False)
            for t in sectors:
                rs = rs_all[t]
                ma = rs.rolling(200).mean()
                mom = mom_all[t]
                fwd_ex = closes[t].pct_change(fwd).shift(-fwd) - spy_fwd
                ok = weekly & fwd_ex.notna()
                aligned = quad.map(lambda q: isinstance(q, str) and t in prefs.get(q, [])).fillna(False)
                rows["mom>0"].append(fwd_ex[(mom > 0) & ok])
                rows["mom>0_above200"].append(fwd_ex[(mom > 0) & (rs > ma) & ok])
                rows["mom>0_below200"].append(fwd_ex[(mom > 0) & (rs <= ma) & ok])
                rows["top3_mom"].append(fwd_ex[(rank[t] <= 3) & ok])
                rows["aligned_mom>0"].append(fwd_ex[aligned & (mom > 0) & ok])
                rows["aligned"].append(fwd_ex[aligned & ok])
            print(f"\n--- formation {form}d momentum, forward {fwd}d excess vs SPY ---")
            for k, parts in rows.items():
                v = pd.concat(parts)
                print(f"  {k:18s} {stats(v)}")

    # --- data-driven quad-conditional sector table, split-half honesty ----------
    print("\n" + "=" * 100)
    print("Per-quad sector forward 63d excess vs SPY — first half vs second half")
    spy63 = bench.pct_change(63).shift(-63)
    for q in ("Q1", "Q2", "Q3", "Q4"):
        print(f"\n[{q}]   {'sector':6s}  {'pre-2017':>22s}  {'post-2017':>22s}")
        for t in sectors:
            fwd_ex = closes[t].pct_change(63).shift(-63) - spy63
            mask = (quad == q) & weekly & fwd_ex.notna()
            a = fwd_ex[mask & (closes.index < SPLIT)]
            b = fwd_ex[mask & (closes.index >= SPLIT)]
            if len(a) > 30 and len(b) > 30:
                print(f"      {t:6s}  n={len(a):4d} avg={100 * a.mean():+6.2f}% "
                      f"hit={100 * (a > 0).mean():4.1f}%   n={len(b):4d} "
                      f"avg={100 * b.mean():+6.2f}% hit={100 * (b > 0).mean():4.1f}%")


if __name__ == "__main__":
    main()
