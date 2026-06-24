"""Isolate WHICH guard contains the knife tail, and stress the residual.

(1) Marginal contribution: each guard alone vs the stack (does put-present alone
    do the heavy lifting? does slope? does depth ever bind independently?).
(2) The residual deep-cyc tail under full guards: WHEN do the surviving guarded
    deep-cyc entries with bad 63d outcomes occur (which years / regimes)?
(3) Compare against the EXISTING gate's own surfaced state (above-200d stoch_up)
    so we judge the new state RELATIVE to what the engine already shows, not vs zero.
(4) 2008 GFC forensics: list the few guarded entries that survived.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_knife_guard_verify import enrich, put_absent_series, tail_stats, line, DEEP_CYC, DEFENSIVE
from scripts._bt_sector_confluence import _load, SECTORS, BENCH

if __name__ == "__main__":
    pd.set_option("display.width", 320)
    spy = _load(BENCH)
    pa = put_absent_series(spy.index)
    R = pd.concat([enrich(t, spy, pa) for t in SECTORS])
    R["def"] = R["ticker"].isin(DEFENSIVE)
    below = ~R["above200"]
    osb = R["os_bounce"]

    print("=" * 200)
    print("(1) MARGINAL GUARD CONTRIBUTION on DEEP-CYC below-200d stoch_up — each guard ALONE")
    print("    Watch mddp5/mddmin (the knife tail). UNGUARDED 63d mddmin was -56% (the catastrophe).")
    print("=" * 200)
    cyc = R[below & osb & R["ticker"].isin(DEEP_CYC)]
    print(line("UNGUARDED", cyc))
    print(line("depth>-12% only", cyc[cyc["depth200"] > -12]))
    print(line("slope>=0 only", cyc[cyc["sma200_slope"] >= 0]))
    print(line("put-present only", cyc[~cyc["put_absent"]]))
    print(line("reclaim10 only", cyc[cyc["reclaim10"]]))
    print()
    print(line("put-present + slope>=0", cyc[(~cyc["put_absent"]) & (cyc["sma200_slope"] >= 0)]))
    print(line("put-present + depth>-12%", cyc[(~cyc["put_absent"]) & (cyc["depth200"] > -12)]))
    print(line("slope>=0 + depth>-12%", cyc[(cyc["sma200_slope"] >= 0) & (cyc["depth200"] > -12)]))

    print("\n" + "=" * 200)
    print("(2) RESIDUAL TAIL FORENSICS — full-guarded DEEP-CYC entries with the WORST 63d outcomes (which years survive?)")
    print("=" * 200)
    g = cyc[(cyc["depth200"] > -12) & (cyc["sma200_slope"] >= 0) & (~cyc["put_absent"])].copy()
    g = g.dropna(subset=["fwd63"]).sort_values("fwd63")
    cols = ["ticker", "depth200", "sma200_slope", "put_absent", "reclaim10", "fwd21", "fwd63", "mdd63"]
    worst = g[cols].head(12).copy()
    worst.index = worst.index.strftime("%Y-%m-%d")
    for c in ["depth200", "sma200_slope", "fwd21", "fwd63", "mdd63"]:
        worst[c] = (worst[c] * (100 if c in ("fwd21", "fwd63", "mdd63", "depth200") else 1)).round(1)
    print(worst.to_string())
    print(f"\n   guarded deep-cyc by year (n per year):")
    print(g.assign(yr=g.index.year).groupby("yr").size().to_string())

    print("\n" + "=" * 200)
    print("(3) RELATIVE TO WHAT THE ENGINE ALREADY SURFACES — above-200d stoch_up (the gate's own buy-side)")
    print("    The new state only needs to be NO WORSE in tail than what's already shown, while adding coverage.")
    print("=" * 200)
    above = R["above200"]
    print(line("ABOVE-200d stoch_up DEEP-CYC (already surfaced)", R[above & osb & R["ticker"].isin(DEEP_CYC)]))
    print(line("GUARDED below-200d stoch_up DEEP-CYC (proposed)", g))
    print()
    defg = R[below & osb & R["def"] & (R["depth200"] > -12) & (R["sma200_slope"] >= 0) & (~R["put_absent"])]
    print(line("ABOVE-200d stoch_up DEFENSIVE (already surfaced)", R[above & osb & R["def"]]))
    print(line("GUARDED below-200d stoch_up DEFENSIVE (proposed)", defg))

    print("\n" + "=" * 200)
    print("(4) 2008 GFC FORENSICS — every below-200d stoch_up in GFC window, with put_absent + guard flags")
    print("=" * 200)
    gfc = R[below & osb & (R.index >= "2008-01-01") & (R.index <= "2009-06-30")].copy()
    gfc["passes_guard"] = (gfc["depth200"] > -12) & (gfc["sma200_slope"] >= 0) & (~gfc["put_absent"])
    print(f"  total below-200d stoch_up in 2008-01..2009-06: {len(gfc)}")
    print(f"  put_absent flagged: {int(gfc['put_absent'].sum())} ({100*gfc['put_absent'].mean():.0f}%)")
    print(f"  pass FULL guard:    {int(gfc['passes_guard'].sum())} ({100*gfc['passes_guard'].mean():.0f}%)")
    surv = gfc[gfc["passes_guard"]].copy()
    if len(surv):
        sc = surv[["ticker", "depth200", "sma200_slope", "fwd21", "fwd63", "mdd63"]].copy()
        sc.index = sc.index.strftime("%Y-%m-%d")
        for c in ["depth200", "fwd21", "fwd63", "mdd63"]:
            sc[c] = (sc[c] * 100).round(1)
        sc["sma200_slope"] = sc["sma200_slope"].round(2)
        print("  SURVIVORS (passed the guard despite GFC):")
        print(sc.to_string())

    print("\n" + "=" * 200)
    print("(5) WHOLE-HISTORY TAIL: unguarded vs guarded, all sectors — the knife-protection bottom line")
    print("=" * 200)
    allb = R[below & osb]
    allg = R[below & osb & (R["depth200"] > -12) & (R["sma200_slope"] >= 0) & (~R["put_absent"])]
    print(line("UNGUARDED below-200d stoch_up (ALL)", allb))
    print(line("GUARDED   below-200d stoch_up (ALL)", allg))
    # how much coverage do we add vs the gate's allowed set?
    allowed_above = int((R["above200"] & osb).sum())
    print(f"\n  coverage: gate currently surfaces {allowed_above} above-200d stoch_up bars;")
    print(f"            the guarded below-200d state adds {len(allg.dropna(subset=['fwd21']))} more (+{100*len(allg.dropna(subset=['fwd21']))/allowed_above:.0f}%).")
