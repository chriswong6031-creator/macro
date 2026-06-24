"""ADVERSARIAL VERIFIER #1 — round 3: resolve the tension.

Round 1/2 contradiction:
  * Raw uplift vs ALL days: clearly +0.8..+1.5pp at 21/63d, survives non-overlap +
    drop-an-era, bootstrap p<0.01.
  * Month-demeaned uplift: collapses to ~0 / slightly negative.

The month-demean is contaminated (the month-mean includes the rebound the signal
catches -> look-ahead-ish drag). So test cleaner, decision-relevant nulls:

NULL-1 (the gate's actual decision): among BELOW-200d days only, does the oversold-
  bounce signal beat a RANDOM below-200d day in the same ETF? The gate forces ALL
  below-200d days to 'wait'; the fix asks 'are signal days better than the average
  thing the gate is suppressing?'. If signal ~ random-below-200d, the signal adds
  nothing over the regime; if signal > random-below-200d, the timing has content.

NULL-2 (pure trailing calendar control, leak-free): compare signal fwd return to the
  ETF's mean fwd return over the TRAILING 252 trading days BEFORE the signal (no
  look-ahead). Residual>0 => signal beats recent drift.

NULL-3: matched permutation — within the below-200d regime, randomly relabel which
  below-200d days are 'signals' (same count per ETF), 2000x, build the null
  distribution of mean fwd return, and locate the real signal mean in it.

Run: python3 -m scripts._bt_verify_uplift3
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_verify_uplift import build_panel, DEFENSIVE, HOR

RNG = np.random.default_rng(101)


if __name__ == "__main__":
    P = build_panel()
    P = P[P["sma200_ok"]]

    print("=" * 100)
    print("NULL-1: signal vs RANDOM BELOW-200d day (the gate's real decision set)")
    print("  below-200d ALL = the universe the gate forces to 'wait'. signal = the proposed buy subset.")
    print("=" * 100)
    for h in HOR:
        below = P[P["below200"].values].reset_index(drop=True)
        sigm = below[below["os_bounce"].values]
        sigmB = below[(below["os_bounce"] & below["reclaim10"]).values]
        allb = 100 * below[f"fwd{h}"].dropna().mean()
        allb_med = 100 * below[f"fwd{h}"].dropna().median()
        sa = 100 * sigm[f"fwd{h}"].dropna().mean()
        sb = 100 * sigmB[f"fwd{h}"].dropna().mean()
        # also: below-200d NON-signal days (the residual the gate would keep suppressing)
        nonsig_mask = ~below["os_bounce"].to_numpy(dtype=bool)
        nonsig = below[nonsig_mask]
        ns = 100 * nonsig[f"fwd{h}"].dropna().mean()
        print(f"  {h}d:  ALL below200 mean={allb:>6.2f} (med {allb_med:>5.2f})  | "
              f"signalA={sa:>6.2f} (uplift_vs_below={sa-allb:>6.2f})  | "
              f"signalB={sb:>6.2f} (uplift={sb-allb:>6.2f})  | "
              f"below-NON-signal={ns:>6.2f}")

    print("\n" + "=" * 100)
    print("NULL-2: TRAILING-252d calendar control (leak-free). resid = signal fwd - ETF's")
    print("  mean fwd over the prior 252 trading days. >0 => signal beats recent drift.")
    print("=" * 100)
    for h in HOR:
        col = f"fwd{h}"
        residsA, residsB = [], []
        for t in DEFENSIVE:
            sel = (P["ticker"] == t).values
            Pt = P[sel]
            fwd = Pt[col]
            trail = fwd.shift(h + 1).rolling(252, min_periods=60).mean()  # shift past the fwd window
            below = Pt["below200"].values
            a = (Pt["os_bounce"].values & below)
            b = (Pt["os_bounce"].values & Pt["reclaim10"].values & below)
            r = (fwd - trail)
            residsA.append(r[a].dropna())
            residsB.append(r[b].dropna())
        ra = pd.concat(residsA) * 100
        rb = pd.concat(residsB) * 100
        print(f"  {h}d:  A resid mean={ra.mean():>6.2f} med={ra.median():>6.2f} (n={len(ra)})  | "
              f"B resid mean={rb.mean():>6.2f} med={rb.median():>6.2f} (n={len(rb)})")

    print("\n" + "=" * 100)
    print("NULL-3: PERMUTATION within below-200d regime (relabel signals randomly, 2000x)")
    print("  p = fraction of permutations whose mean fwd >= real signal mean. <0.05 => real edge.")
    print("=" * 100)
    nperm = 2000
    for h in HOR:
        col = f"fwd{h}"
        real_vals, null_means = [], np.zeros(nperm)
        # per ticker: pool below-200d fwd returns, mark real signal count, permute
        per_ticker = []
        for t in DEFENSIVE:
            sel = (P["ticker"] == t).values
            Pt = P[sel]
            below = Pt["below200"].to_numpy(dtype=bool)
            pool = Pt[col].to_numpy(dtype=float)[below]
            issig = Pt["os_bounce"].to_numpy(dtype=bool)[below]
            # drop NaNs jointly
            ok = ~np.isnan(pool)
            pool, issig = pool[ok], issig[ok]
            per_ticker.append((pool, int(issig.sum())))
            real_vals.append(pool[issig])
        real_mean = float(np.concatenate(real_vals).mean()) * 100
        for p in range(nperm):
            picks = []
            for pool, k in per_ticker:
                if k > 0 and k <= len(pool):
                    picks.append(RNG.choice(pool, size=k, replace=False))
            null_means[p] = np.concatenate(picks).mean() * 100
        pval = float((null_means >= real_mean).mean())
        print(f"  {h}d:  real signalA mean={real_mean:>6.2f}  null mean={null_means.mean():>6.2f} "
              f"sd={null_means.std():>5.2f}  p(perm>=real)={pval:.4f}")
