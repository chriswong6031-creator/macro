"""ADVERSARIAL VERIFIER #1 — round 4: decompose the uplift + final tail/era checks.

Established so far:
  * vs ALL days: uplift +1.0(21d)/+1.5(63d) pp, but
  * the BELOW-200d regime ITSELF already earns more than all-days (mean-reversion of
    the regime). Decompose: uplift = (regime effect) + (signal-timing effect).
  * permutation within below-200d: signal beats random-below-200d only marginally
    (10d p=0.49 NO, 21d p=0.043, 63d p=0.032).

Round 4:
  1. DECOMPOSE the all-days uplift into regime vs signal-timing components.
  2. ABSOLUTE positivity: is the absolute fwd return reliably >0 (median, p5, hit) —
     the claim is 'positive ABSOLUTE'. Confirm or deny per horizon, incl worst single
     realized outcome (crash risk).
  3. Permutation for signal B (os_bounce+reclaim) too.
  4. Era-by-era: does the within-regime signal uplift hold in each era, or is it 1-2
     eras? (the 08-15 era was negative vs all-days).

Run: python3 -m scripts._bt_verify_uplift4
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_verify_uplift import build_panel, DEFENSIVE, HOR, ERAS

RNG = np.random.default_rng(202)


def perm_within_regime(P, sigcol_mask_fn, h, nperm=4000):
    col = f"fwd{h}"
    per_ticker, real_vals = [], []
    for t in DEFENSIVE:
        Pt = P[(P["ticker"] == t).values]
        below = Pt["below200"].to_numpy(dtype=bool)
        pool = Pt[col].to_numpy(dtype=float)[below]
        issig = sigcol_mask_fn(Pt).to_numpy(dtype=bool)[below]
        ok = ~np.isnan(pool)
        pool, issig = pool[ok], issig[ok]
        per_ticker.append((pool, int(issig.sum())))
        real_vals.append(pool[issig])
    real_mean = float(np.concatenate(real_vals).mean()) * 100
    nm = np.zeros(nperm)
    for p in range(nperm):
        picks = [RNG.choice(pool, size=k, replace=False) for pool, k in per_ticker if 0 < k <= len(pool)]
        nm[p] = np.concatenate(picks).mean() * 100
    return real_mean, float(nm.mean()), float((nm >= real_mean).mean())


if __name__ == "__main__":
    P = build_panel()
    P = P[P["sma200_ok"]]

    print("=" * 100)
    print("[1] DECOMPOSE uplift vs ALL-days = REGIME effect + SIGNAL-TIMING effect (signal A)")
    print("=" * 100)
    for h in HOR:
        col = f"fwd{h}"
        allm = 100 * P[col].dropna().mean()
        below = P[P["below200"].values]
        regm = 100 * below[col].dropna().mean()
        sig = below[below["os_bounce"].to_numpy(dtype=bool)]
        sigm = 100 * sig[col].dropna().mean()
        print(f"  {h}d:  all-days={allm:>6.2f}  below200regime={regm:>6.2f} "
              f"(REGIME effect {regm-allm:>+5.2f})  signal={sigm:>6.2f} "
              f"(SIGNAL-TIMING {sigm-regm:>+5.2f})  | total uplift {sigm-allm:>+5.2f}")

    print("\n" + "=" * 100)
    print("[2] ABSOLUTE positivity of signal-A fwd return (the headline 'positive ABSOLUTE' claim)")
    print("=" * 100)
    below = P[P["below200"].values]
    sig = below[below["os_bounce"].to_numpy(dtype=bool)]
    for h in HOR:
        v = sig[f"fwd{h}"].dropna() * 100
        print(f"  {h}d: n={len(v)} mean={v.mean():>6.2f} median={v.median():>6.2f} "
              f"p5={np.percentile(v,5):>7.2f} p25={np.percentile(v,25):>6.2f} "
              f"hit%={100*(v>0).mean():>4.0f} WORST={v.min():>7.2f}")

    print("\n" + "=" * 100)
    print("[3] PERMUTATION within below-200d regime — signal A vs signal B (4000x)")
    print("=" * 100)
    for name, fn in [("A os_bounce", lambda Pt: Pt["os_bounce"]),
                     ("B os_bounce+reclaim", lambda Pt: (Pt["os_bounce"] & Pt["reclaim10"]))]:
        line = f"  {name:22s}"
        for h in HOR:
            rm, nmean, p = perm_within_regime(P, fn, h)
            star = "*" if p < 0.05 else " "
            line += f"  {h}d real={rm:>5.2f} null={nmean:>5.2f} p={p:.3f}{star}"
        print(line)

    print("\n" + "=" * 100)
    print("[4] ERA-BY-ERA within-regime signal-timing uplift (signal A): signal mean - below200 mean")
    print("=" * 100)
    for h in [21, 63]:
        print(f"  --- {h}d ---")
        col = f"fwd{h}"
        for name, lo, hi in ERAS:
            seg = P[(P.index >= lo) & (P.index <= hi)]
            below = seg[seg["below200"].values]
            if len(below) == 0:
                continue
            regm = 100 * below[col].dropna().mean()
            sig = below[below["os_bounce"].to_numpy(dtype=bool)]
            sn = len(sig[col].dropna())
            sigm = 100 * sig[col].dropna().mean() if sn else float("nan")
            print(f"    {name}: below200regime={regm:>6.2f}  signal={sigm:>6.2f}  "
                  f"timing_uplift={sigm-regm:>+6.2f}  (signal_n={sn})")
