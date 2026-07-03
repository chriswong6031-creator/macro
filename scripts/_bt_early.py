"""Follow-up: backtest the ACTUAL early_signals (anticipatory) fires, split by
whether the overbought/washed gate fired via RSI (genuine) or StochRSI-only
(the saturation-prone arm). Tests whether the early-topping / early-bottoming
notes are false flags. Same no-look-ahead walk-forward as _bt_signals.py."""
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
from engine.cycles import cycle_state, mtf_snapshot, early_signals, ladder_state

WIN, STEP, F1, F2 = 600, 10, 21, 63

def agg(rows):
    if len(rows) < 25: return {"n": len(rows)}
    a = np.array(rows)
    return {"n": len(rows),
        "hit21": round(100*(a[:,0]>0).mean(),1), "mean21": round(100*a[:,0].mean(),2),
        "ddP10_21": round(100*np.percentile(a[:,1],10),2),
        "hit63": round(100*(a[:,2]>0).mean(),1), "mean63": round(100*a[:,2].mean(),2),
        "ddP10_63": round(100*np.percentile(a[:,3],10),2)}

def main():
    b: dict = {}; n_inst=0; n_eval=0
    for fi,f in enumerate(sorted(glob.glob("data/stocks/*.parquet"))):
        try: df=pd.read_parquet(f)
        except Exception: continue
        close=df["close"].dropna(); high=df.get("high")
        if len(close)<WIN+F2+50: continue
        n_inst+=1; cv=close.to_numpy()
        for i in range(WIN,len(close)-F2-1,STEP):
            sub=close.iloc[i-WIN:i+1]; hsub=high.reindex(sub.index) if high is not None else None
            try:
                cyc=cycle_state(sub,hsub,"equity")
                if not cyc: continue
                mtf=mtf_snapshot(sub,"equity"); early=early_signals(sub,cyc,mtf)
            except Exception: continue
            if not early or not early.get("dir"): continue
            n_eval+=1
            d=mtf.get("D",{}); rsi14=d.get("rsi14") or 50; rsi5=d.get("rsi5") or 50; st=d.get("stoch") or 50
            p0=cv[i]
            rec=(cv[i+F1]/p0-1, cv[i+1:i+1+F1].min()/p0-1, cv[i+F2]/p0-1, cv[i+1:i+1+F2].min()/p0-1)
            if early["dir"]=="down":
                # bear early fired. gate = overbought = rsi14>70 OR stoch>88
                arm = "RSI>70 (genuine)" if rsi14>70 else "stoch>88 ONLY (rsi<=70)"
                b.setdefault(f"early-BEAR [{early['tier']}]", []).append(rec)
                b.setdefault(f"early-BEAR via {arm}", []).append(rec)
            elif early["dir"]=="up":
                arm = "rsi5<25 (genuine)" if rsi5<25 else "stoch<12/late ONLY"
                b.setdefault(f"early-BULL [{early['tier']}]", []).append(rec)
                b.setdefault(f"early-BULL via {arm}", []).append(rec)
        if (fi+1)%20==0: print(f"  ...{fi+1} files",flush=True)
    print(f"\n=== {n_inst} stocks, {n_eval} early-signal fires ===\n")
    print("NOTE: bear-early SHOULD precede flat/negative fwd + DEEP drawdown if it's a real")
    print("      topping signal; POSITIVE fwd + shallow dd = false flag.\n")
    for k in sorted(b):
        m=agg(b[k])
        if "hit21" in m:
            print(f"{k}")
            print(f"   n={m['n']:5d} | 21d hit={m['hit21']} mean={m['mean21']:+} ddP10={m['ddP10_21']} | 63d hit={m['hit63']} mean={m['mean63']:+} ddP10={m['ddP10_63']}")
        else:
            print(f"{k}: n={m['n']} (thin)")
    Path("/tmp/bt_early.json").write_text(json.dumps({k:agg(v) for k,v in b.items()},indent=1))
    print("\nwrote /tmp/bt_early.json")

if __name__=="__main__": main()
