"""Small walk-forward backtest of the cycle-ladder signals + indicator configs.

No look-ahead: state at bar i is computed from close[i-600:i+1] ONLY (same
trailing-window method as engine.cycles.calibrate_ladder / signal_age), and the
outcome uses close[i+1 : i+1+fwd]. Honest lens = forward DRAWDOWN (max adverse
excursion) + hit-rate, NOT just mean return (D43: 21d avg return is U-shaped).

Panel = the 110 deep-history stocks in data/stocks (median ~40y each).
"""
from __future__ import annotations
import sys, glob, os, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import warnings, logging
if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
import numpy as np, pandas as pd
from engine.cycles import cycle_state, mtf_snapshot, early_signals, ladder_state

WIN, STEP = 600, 10
F1, F2 = 21, 63

def agg(rows):
    """rows: list of (ret21, dd21, ret63, dd63). Return summary dict."""
    if len(rows) < 30:
        return {"n": len(rows)}
    a = np.array(rows)
    r21, dd21, r63, dd63 = a[:,0], a[:,1], a[:,2], a[:,3]
    return {
        "n": len(rows),
        "hit21": round(100*(r21>0).mean(),1), "mean21": round(100*r21.mean(),2),
        "dd_med21": round(100*np.median(dd21),2), "dd_p10_21": round(100*np.percentile(dd21,10),2),
        "hit63": round(100*(r63>0).mean(),1), "mean63": round(100*r63.mean(),2),
        "dd_p10_63": round(100*np.percentile(dd63,10),2),
    }

def main():
    files = sorted(glob.glob("data/stocks/*.parquet"))
    state_b: dict = {}            # ladder state -> rows
    cfg_b: dict = {}              # sub-config label -> rows
    n_inst = 0
    for fi, f in enumerate(files):
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        close = df["close"].dropna()
        high = df.get("high")
        if len(close) < WIN + F2 + 50:
            continue
        n_inst += 1
        cv = close.to_numpy()
        for i in range(WIN, len(close)-F2-1, STEP):
            sub = close.iloc[i-WIN:i+1]
            hsub = high.reindex(sub.index) if high is not None else None
            try:
                cyc = cycle_state(sub, hsub, "equity")
                if not cyc: continue
                mtf = mtf_snapshot(sub, "equity")
                early = early_signals(sub, cyc, mtf)
                lad = ladder_state(cyc, mtf, early)
            except Exception:
                continue
            if not lad or not lad.get("state"): continue
            p0 = cv[i]
            r21 = cv[i+F1]/p0 - 1; dd21 = cv[i+1:i+1+F1].min()/p0 - 1
            r63 = cv[i+F2]/p0 - 1; dd63 = cv[i+1:i+1+F2].min()/p0 - 1
            rec = (r21, dd21, r63, dd63)
            state_b.setdefault(lad["state"], []).append(rec)

            # ---- sub-config tagging (the fix + siblings) ----
            d = mtf.get("D", {})
            rsi14 = d.get("rsi14") or 50; rsi5 = d.get("rsi5") or 50; st = d.get("stoch") or 50
            late = cyc["dc_phase"] in ("approaching_band","in_band","stretched")
            rising_mid = cyc["above_ma10"] and cyc["ma10_rising"] and not late
            if rising_mid:
                if rsi14 <= 70 and st > 90:
                    cfg_b.setdefault("FIX: mid stoch-only (was TOP WATCH→now RALLY ON)", []).append(rec)
                elif rsi14 > 70:
                    cfg_b.setdefault("mid genuine RSI>70 (still TOP WATCH)", []).append(rec)
                else:
                    cfg_b.setdefault("mid clean RALLY ON (rsi<=70,stoch<=90)", []).append(rec)
            # sibling A: early-bear overbought OR (stoch>88 & rsi<=70) in extended up
            extended = cyc["dc_phase"] in ("mid","approaching_band","in_band","stretched") and cyc["above_ma10"]
            if extended and rsi14 <= 70 and st > 88:
                cfg_b.setdefault("SIBLING-A: extended, stoch>88 only (early-bear gate)", []).append(rec)
            # sibling B: washed stoch-only (stoch<12 & rsi5>=25) — downside mirror
            if st < 12 and rsi5 >= 25:
                cfg_b.setdefault("SIBLING-B: stoch<12 only (washed/bull-early gate)", []).append(rec)
            if rsi5 < 25:
                cfg_b.setdefault("ref: rsi5<25 genuine oversold", []).append(rec)
        if (fi+1) % 15 == 0:
            print(f"  ...{fi+1}/{len(files)} files, {n_inst} usable", flush=True)

    print(f"\n=== PANEL: {n_inst} deep-history stocks, win={WIN} step={STEP} ===\n")
    order = ["FRESH BUY","TURN SIGNALED","RALLY ON","BOTTOM WATCH","TOP WATCH",
             "COUNTERTREND BOUNCE","ROLLING OVER","DECLINE"]
    print("--- PER LADDER STATE (forward outcomes) ---")
    hdr = f"{'state':24s} {'n':>6s} {'hit21':>6s} {'mean21':>7s} {'ddMed21':>8s} {'ddP10_21':>9s} {'hit63':>6s} {'mean63':>7s} {'ddP10_63':>9s}"
    print(hdr)
    for s in order:
        if s in state_b:
            m = agg(state_b[s])
            if "hit21" in m:
                print(f"{s:24s} {m['n']:>6d} {m['hit21']:>6} {m['mean21']:>7} {m['dd_med21']:>8} {m['dd_p10_21']:>9} {m['hit63']:>6} {m['mean63']:>7} {m['dd_p10_63']:>9}")
            else:
                print(f"{s:24s} {m['n']:>6d}  (thin)")
    print("\n--- SUB-CONFIG BUCKETS (fix validation + sibling audit) ---")
    print(hdr.replace('state','config',1))
    for s, rows in cfg_b.items():
        m = agg(rows)
        if "hit21" in m:
            print(f"{s:48s}".rstrip()[:48].ljust(48)[:48])  # label may be long; print on own line
            print(f"  -> n={m['n']} hit21={m['hit21']} mean21={m['mean21']} ddMed21={m['dd_med21']} ddP10_21={m['dd_p10_21']} | hit63={m['hit63']} mean63={m['mean63']} ddP10_63={m['dd_p10_63']}")
        else:
            print(f"{s}\n  -> n={m['n']} (thin)")
    # persist raw for any follow-up
    out = {"states": {k: agg(v) for k,v in state_b.items()},
           "configs": {k: agg(v) for k,v in cfg_b.items()}, "n_inst": n_inst}
    Path("/tmp/bt_signals.json").write_text(json.dumps(out, indent=1))
    print("\nwrote /tmp/bt_signals.json")

if __name__ == "__main__":
    main()
