"""Bottom-timing confidence backtest. Within the BOTTOMING population (states at
or near a potential low), test whether two things separate V-bounces from
falling knives — i.e. predict SHALLOWER forward drawdown + higher "low held":
  (A) the EXISTING entry_quality long score (is our confidence score real?)
  (B) explicit MULTI-TIMEFRAME confluence: how many of {daily, 3-day, weekly,
      MONTHLY} are turning up together (does adding weekly/monthly help?).
No look-ahead (trailing 600-bar window → forward bars). Honest lens = forward
drawdown p10 + "held" rate (did price hold above the cycle low over the window).
"""
from __future__ import annotations
import sys, glob, json
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
from engine.cycles import (cycle_state, mtf_snapshot, early_signals, ladder_state,
                           entry_quality, regime_state, _tf_state, macd_parts, stoch_rsi)
from engine.technicals import rsi

WIN, STEP, F1, F2 = 600, 10, 21, 63
BOTTOMING = {"DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY", "COUNTERTREND BOUNCE"}

def _turning_up(s: dict) -> bool:
    if not s: return False
    return bool(s.get("macd_cross_up") or s.get("macd_curl_up")
               or s.get("macd_approaching_up") or s.get("stoch_cross_up"))

def _monthly_turnup(close: pd.Series) -> pd.Series:
    """Precompute ONCE per instrument: a month-end-indexed bool of whether the
    MONTHLY bar is 'turning up' (same defn as _turning_up), computed causally so a
    later .asof(date) lookup = the last COMPLETED monthly bar (no look-ahead)."""
    m = close.resample("ME").last().dropna()
    if len(m) < 40:
        return pd.Series(dtype=bool)
    h = macd_parts(m)["hist"]; sr = stoch_rsi(m)
    out = {}
    hv = h.to_numpy(); sv = sr.to_numpy()
    for j in range(3, len(m)):
        if np.isnan(hv[j]) or np.isnan(hv[j-1]) or np.isnan(hv[j-2]): continue
        cross_up = hv[j] > 0 and (hv[j-3:j] <= 0).any()
        curl_up = hv[j] < 0 and hv[j] > hv[j-1] <= hv[j-2]
        rising = hv[j] > hv[j-1] > hv[j-2]
        appr_up = hv[j] < 0 and rising and (hv[j]-hv[j-3])/3 > 0
        st_up = (not np.isnan(sv[j])) and j>=4 and sv[j] >= 20 and (sv[j-3:j] < 20).any()
        out[m.index[j]] = bool(cross_up or curl_up or appr_up or st_up)
    return pd.Series(out)

def summ(rows):
    if len(rows) < 40: return f"n={len(rows):5d} (thin)"
    a = np.array(rows)  # cols: ret21, dd21, ret63, dd63, held21
    return (f"n={len(a):5d} | dd_p10_21={100*np.percentile(a[:,1],10):6.2f} "
            f"dd_med21={100*np.median(a[:,1]):6.2f} | held21={100*a[:,4].mean():4.1f}% "
            f"| ret63_mean={100*a[:,2].mean():+5.2f} hit63={100*(a[:,2]>0).mean():4.1f}%")

def main():
    eq_buckets = {"<0":[], "0-20":[], "20-40":[], "40-60":[], "60+":[]}
    conf_buckets = {0:[],1:[],2:[],3:[],4:[]}
    wk_split = {"weekly up":[], "weekly not":[]}
    mo_split = {"monthly up":[], "monthly not":[]}
    base_all = []
    n_inst = 0
    for fi, f in enumerate(sorted(glob.glob("data/stocks/*.parquet"))):
        try: df = pd.read_parquet(f)
        except Exception: continue
        close = df["close"].dropna(); high = df.get("high")
        if len(close) < WIN+F2+50: continue
        n_inst += 1; cv = close.to_numpy()
        mflags = _monthly_turnup(close)          # precomputed once per instrument
        for i in range(WIN, len(close)-F2-1, STEP):
            sub = close.iloc[i-WIN:i+1]; hsub = high.reindex(sub.index) if high is not None else None
            try:
                cyc = cycle_state(sub, hsub, "equity")
                if not cyc: continue
                mtf = mtf_snapshot(sub, "equity")
                early = early_signals(sub, cyc, mtf)
                lad = ladder_state(cyc, mtf, early)
                if not lad or lad["state"] not in BOTTOMING: continue
                reg = regime_state(cyc, mtf)
                eq = entry_quality(sub, cyc, mtf, early, reg, state=lad["state"])
            except Exception: continue
            # MONTHLY: asof-lookup the precomputed last COMPLETED monthly bar
            mu = mflags.asof(close.index[i]) if len(mflags) else False
            month_up = bool(mu) if pd.notna(mu) else False
            d, t3, w = mtf.get("D",{}), mtf.get("3D",{}), mtf.get("W",{})
            conf = int(_turning_up(d)) + int(_turning_up(t3)) + int(_turning_up(w)) + int(month_up)

            p0 = cv[i]
            ret21 = cv[i+F1]/p0-1; dd21 = cv[i+1:i+1+F1].min()/p0-1
            ret63 = cv[i+F2]/p0-1; dd63 = cv[i+1:i+1+F2].min()/p0-1
            low = cyc.get("cand_price") or cyc.get("dcl_price") or p0
            held21 = float(cv[i+1:i+1+F1].min() >= low)   # cycle low not broken over 21d
            rec = (ret21, dd21, ret63, dd63, held21)
            base_all.append(rec)

            sc = (eq or {}).get("long", 0.0)   # long-side entry quality 0..100
            key = "<0" if sc < 0 else "0-20" if sc<20 else "20-40" if sc<40 else "40-60" if sc<60 else "60+"
            eq_buckets[key].append(rec)
            conf_buckets[min(conf,4)].append(rec)
            (wk_split["weekly up"] if _turning_up(w) else wk_split["weekly not"]).append(rec)
            (mo_split["monthly up"] if month_up else mo_split["monthly not"]).append(rec)
        if (fi+1)%20==0: print(f"  ...{fi+1} files",flush=True)

    print(f"\n=== BOTTOMING population: {n_inst} stocks, {len(base_all)} evals ===")
    print(f"BASELINE (all bottoming): {summ(base_all)}\n")
    print("--- (A) by EXISTING entry_quality LONG score (our confidence score) ---")
    for k in ["<0","0-20","20-40","40-60","60+"]:
        print(f"  eq_long {k:6s}: {summ(eq_buckets[k])}")
    print("\n--- (B) by MULTI-TF CONFLUENCE count {D,3D,W,Monthly} turning up ---")
    for k in [0,1,2,3,4]:
        print(f"  confluence={k}: {summ(conf_buckets[k])}")
    print("\n--- weekly turning up? ---")
    for k in ["weekly up","weekly not"]: print(f"  {k:11s}: {summ(wk_split[k])}")
    print("\n--- monthly turning up? ---")
    for k in ["monthly up","monthly not"]: print(f"  {k:12s}: {summ(mo_split[k])}")
    print("\nINTERP: higher confidence/confluence SHOULD show shallower dd_p10 + higher held% if it works.")

if __name__=="__main__": main()
