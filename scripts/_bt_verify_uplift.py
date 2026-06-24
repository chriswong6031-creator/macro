"""ADVERSARIAL VERIFIER #1 — refute the 'absolute edge' claim for defensive
below-200d oversold-bounce dip-buys.

Test: is the positive ABSOLUTE forward return from buying a below-200d oversold-and-
turning dip on the DEFENSIVE cohort (XLU,XLP,XLV,XLRE) a REAL EDGE, or is it just
the upward drift you'd get buying ANY day in these ETFs?

Method (all point-in-time, signal read at a bar close, fwd return starts at that close):
  * Conditional = fwd return on below-200d oversold-bounce signal dates.
  * Unconditional = fwd return on ALL trading days for the SAME ETFs (the drift you
    get just being long). This is the honest null: the ETF's own baseline, NOT 0.
  * UPLIFT = conditional - unconditional. Edge requires uplift clearly > 0.
  * Report mean AND median AND 5th-pctile (left tail) for conditional vs unconditional.
  * Bootstrap CI on the mean uplift (block-aware: resample signal DATES, not rows,
    to respect within-date / overlapping-window clustering).
  * Per-era robustness.

Two signal definitions tested:
  A. os_bounce       = StochRSI cross-up over 20 from <20 (the user's literal signal)
  B. os_bounce+reclaim = os_bounce AND price back above its 10-day MA (the 'turning'
     filter the meanrev2 script used to claim ABSOLUTE positivity in all eras)

Run: python3 -m scripts._bt_verify_uplift
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_sector_confluence import _load, _to_3b, _signals_3b, BENCH

DEFENSIVE = ["XLU", "XLP", "XLV", "XLRE"]
HOR = [10, 21, 63]
ERAS = [("99-07", "1999-01-01", "2007-12-31"), ("08-15", "2008-01-01", "2015-12-31"),
        ("16-20", "2016-01-01", "2020-12-31"), ("21-26", "2021-01-01", "2026-12-31")]
RNG = np.random.default_rng(20260623)


def build_panel():
    """For each defensive ETF: every DAILY bar with its forward returns (the
    unconditional universe), plus flags marking which daily bars coincide with a
    3B below-200d oversold-bounce signal (the conditional subset)."""
    frames = []
    for t in DEFENSIVE:
        daily = _load(t)
        if len(daily) < 400:
            continue
        sma200 = daily.rolling(200).mean()
        # 3B signals -> map signal dates to the daily index
        s3 = _to_3b(daily)
        sig = _signals_3b(s3["close"])
        # signal flags on the SIGNAL (3B) dates, mapped to daily index
        os_bounce = sig["stoch_up"].reindex(daily.index).fillna(False)
        macd_up = sig["macd_up"].reindex(daily.index).fillna(False)
        setup_up = sig["setup_up"].reindex(daily.index).fillna(False)
        fresh_up = (os_bounce | macd_up | setup_up)
        below200 = (daily < sma200)
        ma10 = daily.rolling(10).mean()
        reclaim10 = (daily > ma10)

        df = pd.DataFrame(index=daily.index)
        df["ticker"] = t
        df["close"] = daily.values
        df["below200"] = below200.values
        df["os_bounce"] = os_bounce.values
        df["fresh_up"] = fresh_up.values
        df["reclaim10"] = reclaim10.values
        df["sma200_ok"] = sma200.notna().values  # need 200d history for below200 to be valid
        # forward absolute returns from THIS daily close
        for h in HOR:
            df[f"fwd{h}"] = daily.shift(-h).values / daily.values - 1.0
        frames.append(df)
    return pd.concat(frames)


def dist_stats(s: pd.Series) -> dict:
    s = s.dropna() * 100
    if len(s) == 0:
        return {"n": 0}
    return {
        "n": int(len(s)),
        "mean": round(float(s.mean()), 2),
        "median": round(float(s.median()), 2),
        "p5": round(float(np.percentile(s, 5)), 2),
        "p25": round(float(np.percentile(s, 25)), 2),
        "hit%": round(float((s > 0).mean() * 100), 0),
    }


def date_block_bootstrap_uplift(cond: pd.DataFrame, uncond: pd.Series, col: str,
                                n_boot: int = 5000) -> tuple:
    """Bootstrap CI on mean uplift = mean(conditional) - mean(unconditional).
    Conditional is resampled by DATE (cluster) to respect overlapping fwd windows
    and same-day cross-sector clustering. Unconditional mean is the fixed ETF
    baseline (the drift you'd get any day) — we hold it as the null anchor and
    also resample it by date for a symmetric CI.
    """
    c = cond[[col]].copy()
    c["date"] = cond.index
    c = c.dropna(subset=[col])
    u = uncond.dropna()
    # group conditional rows by date
    cdates = c["date"].unique()
    cgroups = {d: g[col].values for d, g in c.groupby("date")}
    base_uncond = float(u.mean())
    boots = np.empty(n_boot)
    nd = len(cdates)
    for b in range(n_boot):
        pick = RNG.choice(cdates, size=nd, replace=True)
        vals = np.concatenate([cgroups[d] for d in pick])
        # resample unconditional too (simple iid over its large n is fine)
        usamp = u.sample(frac=1.0, replace=True, random_state=int(RNG.integers(1e9)))
        boots[b] = vals.mean() - usamp.mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    point = float(c[col].mean()) - base_uncond
    return round(point * 100, 2), round(lo * 100, 2), round(hi * 100, 2)


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    P = build_panel()
    # valid rows = have 200d history
    P = P[P["sma200_ok"]]

    # ---- the two conditional definitions, pooled across the defensive cohort ----
    below = P["below200"]
    condA = P[below & P["os_bounce"]]                       # literal oversold bounce
    condB = P[below & P["os_bounce"] & P["reclaim10"]]      # + turning filter
    condC = P[below & P["fresh_up"] & P["reclaim10"]]       # broad fresh-up + reclaim (meanrev2's claim)
    uncond = P  # unconditional = every daily bar in these 4 ETFs

    print("=" * 108)
    print("DEFENSIVE COHORT (XLU,XLP,XLV,XLRE) — CONDITIONAL vs UNCONDITIONAL forward ABSOLUTE return (%)")
    print("  Unconditional = the drift from buying ANY day in these same ETFs (the honest null).")
    print("=" * 108)
    for h in HOR:
        print(f"\n--- horizon {h}d ---")
        print(f"  {'UNCONDITIONAL (all days)':40s}", dist_stats(uncond[f"fwd{h}"]))
        print(f"  {'A. os_bounce below200':40s}", dist_stats(condA[f"fwd{h}"]))
        print(f"  {'B. os_bounce+reclaim10 below200':40s}", dist_stats(condB[f"fwd{h}"]))
        print(f"  {'C. fresh_up+reclaim10 below200':40s}", dist_stats(condC[f"fwd{h}"]))

    print("\n" + "=" * 108)
    print("UPLIFT = mean(conditional) - mean(unconditional), with date-block bootstrap 95% CI")
    print("  EDGE requires uplift CI clearly ABOVE 0. CI spanning 0 => no edge beyond drift.")
    print("=" * 108)
    for name, cond in [("A. os_bounce", condA), ("B. os_bounce+reclaim10", condB),
                       ("C. fresh_up+reclaim10", condC)]:
        line = f"  {name:26s}"
        for h in HOR:
            pt, lo, hi = date_block_bootstrap_uplift(cond, uncond[f"fwd{h}"], f"fwd{h}")
            sig = "*" if (lo > 0 or hi < 0) else " "
            line += f"  {h}d uplift={pt:>6} [{lo:>6},{hi:>6}]{sig}"
        print(line)

    print("\n" + "=" * 108)
    print("LEFT-TAIL CHECK — is the mean dragged up by fat right tails? p5 = 5th-pctile fwd return")
    print("=" * 108)
    for h in HOR:
        u = dist_stats(uncond[f"fwd{h}"]); a = dist_stats(condA[f"fwd{h}"]); b = dist_stats(condB[f"fwd{h}"])
        print(f"  {h}d:  uncond mean={u['mean']:>6} med={u['median']:>6} p5={u['p5']:>7}  |  "
              f"A mean={a['mean']:>6} med={a['median']:>6} p5={a['p5']:>7}  |  "
              f"B mean={b['mean']:>6} med={b['median']:>6} p5={b['p5']:>7}")

    print("\n" + "=" * 108)
    print("PER-ERA UPLIFT (signal B = os_bounce+reclaim10) — conditional mean vs same-era unconditional mean")
    print("=" * 108)
    for h in [21, 63]:
        print(f"\n--- horizon {h}d ---")
        for name, lo, hi in ERAS:
            useg = uncond[(uncond.index >= lo) & (uncond.index <= hi)][f"fwd{h}"].dropna()
            bseg = condB[(condB.index >= lo) & (condB.index <= hi)][f"fwd{h}"].dropna()
            aseg = condA[(condA.index >= lo) & (condA.index <= hi)][f"fwd{h}"].dropna()
            um = 100 * useg.mean() if len(useg) else float("nan")
            bm = 100 * bseg.mean() if len(bseg) else float("nan")
            am = 100 * aseg.mean() if len(aseg) else float("nan")
            print(f"  {name}: uncond={um:>6.2f} (n={len(useg)})  | "
                  f"A_cond={am:>6.2f} uplift={am-um:>6.2f} (n={len(aseg)})  | "
                  f"B_cond={bm:>6.2f} uplift={bm-um:>6.2f} (n={len(bseg)})")

    print("\n" + "=" * 108)
    print("PER-SECTOR UPLIFT (signal A = os_bounce below200), fwd-21d & fwd-63d")
    print("=" * 108)
    for t in DEFENSIVE:
        Pt = P[P["ticker"] == t]
        ut = Pt
        ct = Pt[Pt["below200"] & Pt["os_bounce"]]
        line = f"  {t:6s}"
        for h in [21, 63]:
            um = 100 * ut[f"fwd{h}"].dropna().mean()
            n = len(ct[f"fwd{h}"].dropna())
            cm = 100 * ct[f"fwd{h}"].dropna().mean() if n else float("nan")
            line += f"  {h}d: uncond={um:>6.2f} cond={cm:>6.2f} uplift={cm-um:>6.2f} (n={n})"
        print(line)
