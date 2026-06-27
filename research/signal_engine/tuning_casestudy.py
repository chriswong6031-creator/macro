"""Human-readable case study: show, on a few names, exactly where the lagging 3D
MACD buy (base3d) fires vs the earlier 2D-MACD / anticipation trigger on the SAME
move — concrete proof of 'enter before the breakout, not into it'. Leak-free: raw
signals only, fill = next daily close.

Run:  python3 research/signal_engine/tuning_casestudy.py NVDA AMD AAPL
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tuning_harness as H   # noqa: E402

WIN = 12


def raw_buys(daily, cfg):
    fr = H.build_signals(daily, cfg)
    idx = fr.index
    out = []
    for i in np.where(fr["buy"].to_numpy())[0]:
        f = i + 1
        if f < len(idx) and idx[i] >= H.SINCE:
            out.append((f, idx[f], float(fr["close"].iloc[f])))
    return out


def study(t):
    daily = pd.read_parquet(H.DATA / f"{t}.parquet")["close"].dropna()
    b = raw_buys(daily, H.VARIANTS["base3d"])
    for cand in ("m2d_s3d", "m2d_s3d_early"):
        c = raw_buys(daily, H.VARIANTS[cand])
        cf = np.array([x[0] for x in c])
        print(f"\n## {t}  base3d vs {cand}")
        print(f"{'base buy date':14s}{'base px':>9s}   {'cand date':>12s}{'cand px':>9s}"
              f"{'days earlier':>13s}{'cheaper%':>10s}")
        for fb, db, pb in b:
            if len(cf) == 0:
                continue
            j = int(np.argmin(np.abs(cf - fb)))
            fc, dc, pc = c[j]
            if abs(fc - fb) <= WIN:
                print(f"{str(db.date()):14s}{pb:>9.2f}   {str(dc.date()):>12s}{pc:>9.2f}"
                      f"{fb - fc:>13d}{100*(pb/pc-1):>9.1f}%")


if __name__ == "__main__":
    for t in (sys.argv[1:] or ["NVDA", "AMD", "AAPL"]):
        study(t)
