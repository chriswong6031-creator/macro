"""Phase-0 for the Sector Bottom Radar (engine/sector_bottom.py).

QUESTION. Does the validated per-STOCK Bottom Confidence machinery
(engine.cycles.bottom_confidence) still separate durable bottoms from falling
knives when pointed at a SECTOR INDEX (the 11 SPDR sector ETFs + SMH), and does the
index Fed-put macro gate (engine.dislocation.master_switch_frame) add the same
buyable-vs-knife split at the sector level that research/DISLOCATION_VALIDATION.md
found at the index level?

METHOD (no look-ahead). Walk-forward over each sector ETF, weekly step on a trailing
600-bar window — the exact harness research_bottom_confidence.py / calibrate_ladder
use. State at bar i is computed from close[i-600:i+1] only; outcomes from
close[i+1 : i+1+fwd]. Restricted to the bottoming population (DECLINE / BOTTOM WATCH
/ TURN SIGNALED / FRESH BUY / COUNTERTREND BOUNCE). The macro gate (put-absent) at
bar i is read from a PIT daily Sahm/breakeven series.

HONEST LENS (D43 / BOTTOM_CONFIDENCE.md). Forward drawdown p10 (the tail you sit
through) + "held21" (did the cycle low survive 21 sessions — the cleanest
"was-this-a-bottom" proxy), NOT endpoint return. The robust claim is
SIGN-CONSISTENCY / MONOTONICITY, never magnitudes: 12 sector ETFs are highly
correlated and most bottom together, so the EFFECTIVE number of independent
episodes is far smaller than the raw eval count (reported below as calendar
clusters). Survivorship is minimal here (sector ETFs, not single names) but the
bull-era drift caveat still applies — judge ordering, not absolute return.
"""
from __future__ import annotations

import sys
import warnings
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

import numpy as np
import pandas as pd

from engine.cycles import cycle_state, mtf_snapshot, early_signals, ladder_state, \
    entry_quality, washout, bottom_confidence
from engine import dislocation

WIN, STEP, F1, F2 = 600, 5, 21, 63
BOTTOMING = {"DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY", "COUNTERTREND BOUNCE"}
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB",
           "XLRE", "XLC", "SMH"]
DATA = Path("data")


def _macro_put_absent() -> pd.Series:
    """PIT daily put-absent series via the SHIPPED dislocation.master_switch_frame
    (recession Sahm>=0.50 OR sustained 10y breakeven>=2.5%). Sahm is monthly →
    forward-filled (a month's reading is known from its release, no look-ahead at a
    daily step). Breakeven starts 2003; before then fedput_off=False (matches the
    engine: pre-TIPS, the Fed was not inflation-locked in the 2000/2001 slowdown)."""
    sahm = pd.read_parquet(DATA / "fred" / "SAHMREALTIME.parquet")["sahm"]
    be = pd.read_parquet(DATA / "fred" / "T10YIE.parquet")["breakeven_10y"]
    spy = pd.read_parquet(DATA / "yahoo" / "SPY.parquet")["close"].rename("SPY")
    idx = spy.index
    f = pd.DataFrame(index=idx)
    f["sahm"] = sahm.reindex(idx, method="ffill")
    f["breakeven_10y"] = be.reindex(idx).ffill()
    f["SPY"] = spy
    msf = dislocation.master_switch_frame(f)
    return msf["put_absent"].reindex(idx).fillna(False)


def summ(rows) -> str:
    if len(rows) < 40:
        return f"n={len(rows):5d} (thin)"
    a = np.array(rows)  # cols: ret21, dd21, ret63, dd63, held21
    return (f"n={len(a):5d} | dd_p10_21={100*np.percentile(a[:,1],10):6.2f} "
            f"dd_med21={100*np.median(a[:,1]):6.2f} | held21={100*a[:,4].mean():4.1f}% "
            f"| ret63_mean={100*a[:,2].mean():+5.2f} hit63={100*(a[:,2]>0).mean():4.1f}%")


def _clusters(dates: list[pd.Timestamp], gap_days: int = 63) -> int:
    """Independent-episode count: firings more than `gap_days` apart (pooled across
    sectors) — the honest effective-N for overlapping, correlated windows."""
    if not dates:
        return 0
    ds = sorted(pd.Timestamp(d) for d in dates)
    n, last = 1, ds[0]
    for d in ds[1:]:
        if (d - last).days > gap_days:
            n += 1
            last = d
    return n


def main():
    put_absent = _macro_put_absent()
    bc_buckets = {"0-20": [], "20-40": [], "40-60": [], "60+": []}
    gate_split = {"put-present": [], "put-absent": []}
    combo = {"bc>=40 & put-present": [], "else": []}
    knife_split = {"knife (deep/falling)": [], "not knife": []}
    base_all = []
    fire_dates: list = []
    per_sector = {}

    for t in SECTORS:
        p = DATA / "yahoo" / f"{t}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        close = df["close"].dropna()
        high = df.get("high")
        if len(close) < WIN + F2 + 50:
            continue
        cv = close.to_numpy()
        s_evals = 0
        for i in range(WIN, len(close) - F2 - 1, STEP):
            sub = close.iloc[i - WIN:i + 1]
            hsub = high.reindex(sub.index) if high is not None else None
            try:
                cyc = cycle_state(sub, hsub, "equity")
                if not cyc:
                    continue
                mtf = mtf_snapshot(sub, "equity")
                early = early_signals(sub, cyc, mtf)
                lad = ladder_state(cyc, mtf, early)
                if not lad or lad["state"] not in BOTTOMING:
                    continue
                eq = entry_quality(sub, cyc, mtf, early, {"regime": lad.get("regime", "neutral")},
                                   state=lad["state"])
                wo = washout(sub, cyc, None)
                bc = bottom_confidence(mtf, eq, lad["state"], wo=wo)
            except Exception:
                continue

            p0 = cv[i]
            ret21 = cv[i + F1] / p0 - 1
            dd21 = cv[i + 1:i + 1 + F1].min() / p0 - 1
            ret63 = cv[i + F2] / p0 - 1
            dd63 = cv[i + 1:i + 1 + F2].min() / p0 - 1
            low = cyc.get("cand_price") or cyc.get("dcl_price") or p0
            held21 = float(cv[i + 1:i + 1 + F1].min() >= low)
            rec = (ret21, dd21, ret63, dd63, held21)
            base_all.append(rec)
            s_evals += 1
            d_i = close.index[i]
            fire_dates.append(d_i)

            score = (bc or {}).get("score")
            if score is not None:
                key = ("0-20" if score < 20 else "20-40" if score < 40
                       else "40-60" if score < 60 else "60+")
                bc_buckets[key].append(rec)

            pa = bool(put_absent.asof(d_i)) if d_i >= put_absent.index[0] else False
            gate_split["put-absent" if pa else "put-present"].append(rec)
            if score is not None and score >= 40 and not pa:
                combo["bc>=40 & put-present"].append(rec)
            else:
                combo["else"].append(rec)

            kl = wo.get("level", "none") if wo else "none"
            (knife_split["knife (deep/falling)"] if kl in ("elevated", "high")
             else knife_split["not knife"]).append(rec)
        per_sector[t] = s_evals

    n_clusters = _clusters(fire_dates)
    print(f"\n=== SECTOR BOTTOMING population: {len(SECTORS)} ETFs, {len(base_all)} evals ===")
    print(f"per-sector evals: " + ", ".join(f"{k}:{v}" for k, v in per_sector.items()))
    print(f"independent calendar clusters (>63d apart, pooled): ~{n_clusters} "
          f"(effective-N — judge ORDERING, not magnitudes)\n")
    print(f"BASELINE (all sector bottoming): {summ(base_all)}\n")

    print("--- (A) by sector-ETF Bottom Confidence band (does the stock score transfer?) ---")
    for k in ["0-20", "20-40", "40-60", "60+"]:
        print(f"  bc {k:6s}: {summ(bc_buckets[k])}")
    print("\n--- (B) by index Fed-put MACRO GATE (does dislocation split sectors too?) ---")
    for k in ["put-present", "put-absent"]:
        print(f"  {k:12s}: {summ(gate_split[k])}")
    print("\n--- (C) combined: high bc AND macro put-present, vs everything else ---")
    for k in ["bc>=40 & put-present", "else"]:
        print(f"  {k:22s}: {summ(combo[k])}")
    print("\n--- (D) washout knife temper (deep-below-200d/falling vs not) ---")
    for k in ["knife (deep/falling)", "not knife"]:
        print(f"  {k:22s}: {summ(knife_split[k])}")
    print("\nINTERP: a real sector bottom score shows MONOTONE shallower dd_p10 + higher")
    print("held21 with rising bc, and put-present shallower than put-absent. Lower")
    print("forward RETURN at higher confidence is expected (durability traded for upside).")


if __name__ == "__main__":
    main()
