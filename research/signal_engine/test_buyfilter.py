"""Cross-sectional generalization test of the BUY-SIDE FILTER — the surviving piece.

Filter = reclaim-and-hold + bearish-divergence veto + 200MA-as-bar-raiser (refined_buy).
It was designed on Tencent/BABA (NOT in data/stocks), so all 110 US names are held out.
Same simple oscillator exit for both; we only vary whether the buy is filtered.
Question: does filtering raw confluence buys reduce drawdown / cut losses across names
WITHOUT killing too many trades — and does it hold on names I never looked at?
"""
from __future__ import annotations
import glob, pathlib, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.disable(logging.CRITICAL)

from confluence import compute_signals
from diagnose_tencent_baba import swing_points, divergence_at
from diagnose_v2 import refined_buy

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "stocks"
SINCE = pd.Timestamp("2023-06-01")


def sim(sig, filtered):
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    hi, lo = swing_points(c)
    pos = 0; ep = None; trades = []; eq = 1.0; curve = [1.0]
    for i in range(n - 1):
        if pos == 1:
            eq *= float(c.iloc[i + 1]) / float(c.iloc[i])
        curve.append(eq)
        if pos == 0:
            if idx[i] < SINCE:
                continue
            cand = bool(sig["CB"].iloc[i] or sig["revBuy"].iloc[i])
            if cand and filtered:
                cand = refined_buy(i, sig, divergence_at(i, c, macd, hi, lo), n)[0] == "TAKE"
            if cand:
                pos, ep = 1, float(c.iloc[i + 1])
        elif bool(sig["CS"].iloc[i] or sig["revSell"].iloc[i]):
            trades.append(float(c.iloc[i + 1]) / ep - 1); pos = 0
    eqc = np.array(curve); dd = (eqc / np.maximum.accumulate(eqc) - 1).min()
    r = np.array(trades) if trades else np.array([0.0])
    losses = r[r < 0]
    return {"n": len(trades), "wr": 100 * (r > 0).mean() if trades else 0,
            "dd": 100 * dd, "cap": 100 * (eqc[-1] - 1),
            "avgloss": 100 * losses.mean() if len(losses) else 0.0}


def agg(rows, name):
    f = lambda k, j: np.mean([x[j][k] for x in rows])
    better = np.mean([x[2]["dd"] > x[1]["dd"] for x in rows]) * 100
    print(f"\n{name}: n={len(rows)}")
    print(f"  avg maxDD:   RAW {f('dd',1):6.1f}  ->  FILTERED {f('dd',2):6.1f}   (filter shallower on {better:.0f}% of names)")
    print(f"  avg WR%:     RAW {f('wr',1):6.0f}  ->  FILTERED {f('wr',2):6.0f}")
    print(f"  avg loss%:   RAW {f('avgloss',1):6.1f}  ->  FILTERED {f('avgloss',2):6.1f}")
    print(f"  avg trades:  RAW {f('n',1):6.1f}  ->  FILTERED {f('n',2):6.1f}    avg captured%: RAW {f('cap',1):.0f} -> FILTERED {f('cap',2):.0f}")


if __name__ == "__main__":
    rows = []
    for fp in sorted(glob.glob(str(DATA / "*.parquet"))):
        t = pathlib.Path(fp).stem
        try:
            sig = compute_signals(pd.read_parquet(fp)["close"].dropna())
            if sig.empty:
                continue
            sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
            rows.append((t, sim(sig, False), sim(sig, True)))
        except Exception:
            continue
    agg(rows, "ALL 110 (all held-out: filter was designed on Tencent/BABA)")
    agg([x for x in rows if x[0] not in {"JNJ", "LLY", "WMT", "MCD", "NVDA"}], "STRICT held-out (also excl the 5 exit-cases)")
