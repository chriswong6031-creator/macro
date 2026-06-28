"""ADVERSARIAL VERIFIER #1 — round 2 stress tests on the defensive dip-buy uplift.

Round 1 found a robust positive uplift (21d ~+1.0pp, 63d ~+1.5pp, bootstrap CI > 0
in 3 of 4 cases). Before conceding, attack the result:

1. TIME-MATCHED null: signals may cluster in good years; compare each signal's fwd
   return to the SAME-MONTH unconditional mean of the same ETF (drift control that
   removes calendar clustering). If the uplift survives month-demeaning, it's not
   'signals happen to land in bull months'.
2. PROPER block bootstrap: resample signal DATES (clusters), unconditional held as a
   fixed baseline — report the one-sided p(uplift<=0).
3. OVERLAP / independence: how clustered are the signal dates? autocorrelation of the
   conditional fwd returns via # distinct dates vs # rows, and a deduped-by-date test.
4. DROP-WORST-ERA: recompute uplift excluding the 2008-15 era (the only negative one)
   AND excluding the best era (21-26) to see if any single era carries it.
5. NON-OVERLAPPING sample: take only signals >=63 trading days apart (per ticker) so
   fwd-63d windows don't overlap — the cleanest iid-ish test.

Run: python3 -m scripts._bt_verify_uplift2
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_verify_uplift import build_panel, DEFENSIVE, HOR, ERAS

RNG = np.random.default_rng(7)


def month_demeaned_uplift(P, cond_mask, h):
    """For each signal, subtract that ETF's same-(year,month) unconditional mean fwd
    return. Mean of the residual = uplift purged of calendar clustering.
    cond_mask is a boolean Series ALIGNED to P (same length/order)."""
    col = f"fwd{h}"
    out = []
    for t in DEFENSIVE:
        sel = (P["ticker"] == t).values
        Pt = P[sel].copy()
        cm = cond_mask.values[sel]
        Pt["ym"] = Pt.index.to_period("M")
        mmean = Pt.groupby("ym")[col].transform("mean")
        resid = (Pt[col] - mmean).values
        out.append(pd.Series(resid)[cm].dropna())
    r = pd.concat(out) * 100
    return round(float(r.mean()), 2), round(float(r.median()), 2), int(len(r))


def block_boot_p(cond, uncond_mean, col, n_boot=10000):
    """One-sided bootstrap: resample conditional by DATE, count fraction of resamples
    with mean <= unconditional baseline. uncond_mean is the fixed null anchor."""
    c = cond[[col]].copy()
    c["date"] = cond.index
    c = c.dropna(subset=[col])
    groups = {d: g[col].values for d, g in c.groupby("date")}
    dates = np.array(list(groups.keys()))
    nd = len(dates)
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.choice(dates, size=nd, replace=True)
        means[b] = np.concatenate([groups[d] for d in pick]).mean()
    p_le = float((means <= uncond_mean).mean())
    return round(float(c[col].mean() * 100), 2), round(uncond_mean * 100, 2), round(p_le, 4)


def non_overlapping(P, cond_mask, h, gap=None):
    """Keep only signals spaced >= gap trading days apart per ticker (default gap=h)
    so fwd windows don't overlap."""
    gap = gap or h
    col = f"fwd{h}"
    rows = []
    for t in DEFENSIVE:
        sel = (P["ticker"] == t).values
        Pt = P[sel]
        cm = cond_mask.values[sel]
        colvals = Pt[col].values
        positions = np.where(cm)[0]
        last = None
        for pos in positions:
            if last is None or (pos - last) >= gap:
                v = colvals[pos]
                if pd.notna(v):
                    rows.append(v)
                last = pos
    r = pd.Series(rows) * 100
    return round(float(r.mean()), 2), round(float(r.median()), 2), int(len(r))


if __name__ == "__main__":
    P = build_panel()
    P = P[P["sma200_ok"]]
    below = P["below200"]
    maskA = (below & P["os_bounce"])
    maskB = (below & P["os_bounce"] & P["reclaim10"])

    print("=" * 100)
    print("[1] CALENDAR-MATCHED UPLIFT — signal fwd return minus SAME-(year,month) ETF mean")
    print("    (removes 'signals cluster in good months'. residual>0 => real timing edge)")
    print("=" * 100)
    for name, m in [("A. os_bounce", maskA), ("B. os_bounce+reclaim", maskB)]:
        line = f"  {name:22s}"
        for h in HOR:
            mu, med, n = month_demeaned_uplift(P, m, h)
            line += f"  {h}d resid mean={mu:>6} med={med:>6} (n={n})"
        print(line)

    print("\n" + "=" * 100)
    print("[2] ONE-SIDED BLOCK BOOTSTRAP — p(resampled conditional mean <= unconditional baseline)")
    print("=" * 100)
    for name, cond in [("A. os_bounce", P[maskA]), ("B. os_bounce+reclaim", P[maskB])]:
        line = f"  {name:22s}"
        for h in HOR:
            ubase = float(P[f"fwd{h}"].dropna().mean())
            cm, um, p = block_boot_p(cond, ubase, f"fwd{h}")
            line += f"  {h}d cond={cm:>5} unc={um:>5} p(<=null)={p}"
        print(line)

    print("\n" + "=" * 100)
    print("[3] SIGNAL CLUSTERING — distinct dates vs rows (cross-sector same-day overlap)")
    print("=" * 100)
    for name, cond in [("A", P[maskA]), ("B", P[maskB])]:
        rows = len(cond)
        dates = cond.index.nunique()
        print(f"  signal {name}: {rows} rows across {dates} distinct dates "
              f"({round(rows/dates,2)} sectors firing per date on avg)")

    print("\n" + "=" * 100)
    print("[4] DROP-AN-ERA — recompute fwd-21d & fwd-63d uplift excluding one era at a time (signal A)")
    print("=" * 100)
    for drop in [None] + [e[0] for e in ERAS]:
        keep = pd.Series(True, index=P.index)
        if drop:
            lo, hi = [e for e in ERAS if e[0] == drop][0][1:]
            keep = ~((P.index >= lo) & (P.index <= hi))
        Pk = P[keep]
        mk = (Pk["below200"] & Pk["os_bounce"])
        line = f"  exclude {str(drop):6s}:"
        for h in [21, 63]:
            ub = 100 * Pk[f"fwd{h}"].dropna().mean()
            cm = Pk[mk]
            cv = 100 * cm[f"fwd{h}"].dropna().mean()
            line += f"  {h}d uplift={cv-ub:>6.2f} (cond_n={len(cm[f'fwd{h}'].dropna())})"
        print(line)

    print("\n" + "=" * 100)
    print("[5] NON-OVERLAPPING signals (>= h trading days apart per ticker) vs unconditional")
    print("=" * 100)
    for name, m in [("A. os_bounce", maskA), ("B. os_bounce+reclaim", maskB)]:
        line = f"  {name:22s}"
        for h in HOR:
            mu, med, n = non_overlapping(P, m, h)
            ub = 100 * P[f"fwd{h}"].dropna().mean()
            line += f"  {h}d cond={mu:>6} (med {med}) uplift={mu-ub:>6.2f} (n={n})"
        print(line)
