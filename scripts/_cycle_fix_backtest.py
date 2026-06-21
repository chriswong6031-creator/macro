"""DEV backtest (not a build step): walk the deep-history US names through time,
re-running engine.cycles.analyze() on each expanding window, and measure forward
return + Max Adverse Excursion (MAE) by entry urgency. The claim under test: the
entry verdict predicts entry QUALITY — 'now'/'imminent' entries should have higher
forward return and SHALLOWER MAE than the 'caution' (DON'T CHASE) cohort the
cycle-top fix demotes. MAE is the metric the prior alpha-only Phase-0 never measured.

Usage: python scripts/_cycle_fix_backtest.py [--step N] [--fwd N] [--years Y]
"""
from __future__ import annotations
import sys, argparse, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from lib import config
from engine import cycles

ROOT = Path(__file__).resolve().parent.parent


def deep_names():
    d = config.data_dir() / "stocks"
    out = []
    for p in sorted(d.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if "close" in df and len(df["close"].dropna()) >= 400:
            out.append((p.stem, df["close"].dropna(), df.get("high")))
    return out


def run(step: int, fwd: int, years: int):
    names = deep_names()
    print(f"deep names: {len(names)} | step={step} fwd={fwd} window=last {years}y")
    # accumulate per-urgency: forward returns and MAEs
    buckets = collections.defaultdict(lambda: {"ret": [], "mae": [], "n": 0})
    # also split 'caution' by whether it was an extended_gate DON'T CHASE (the demoted top)
    dont_chase = {"ret": [], "mae": []}
    for t, close, high in names:
        c = close.to_numpy(dtype=float)
        n = len(c)
        start = max(300, n - years * 252)
        for i in range(start, n - fwd, step):
            # truncate to the window cycles actually needs (~260-300 daily + weekly
            # resample); 800 bars is ample and keeps each analyze O(800) not O(11000).
            sub = close.iloc[max(0, i + 1 - 800): i + 1]
            try:
                res = cycles.analyze(sub, high.iloc[: i + 1] if high is not None else None, "equity")
            except Exception:
                continue
            lad = res.get("ladder") or {}
            e = lad.get("entry") or {}
            urg = e.get("urgency")
            if not urg:
                continue
            fwd_px = c[i + 1: i + 1 + fwd]
            if len(fwd_px) < fwd:
                continue
            ret = c[i + fwd] / c[i] - 1.0
            mae = fwd_px.min() / c[i] - 1.0          # worst drawdown over the window (<=0)
            b = buckets[urg]
            b["ret"].append(ret); b["mae"].append(mae); b["n"] += 1
            if e.get("tag") == "DON'T CHASE":
                dont_chase["ret"].append(ret); dont_chase["mae"].append(mae)
    # report
    order = ["now", "imminent", "soon", "hold", "later", "caution", "exit", "avoid"]
    print(f"\n{'urgency':<10} {'n':>6} {'fwd_ret%':>9} {'median%':>8} {'MAE%':>8} {'win%':>6}")
    for u in order:
        b = buckets.get(u)
        if not b or b["n"] < 30:
            continue
        r = np.array(b["ret"]); m = np.array(b["mae"])
        print(f"{u:<10} {b['n']:>6} {100*r.mean():>9.2f} {100*np.median(r):>8.2f} "
              f"{100*m.mean():>8.2f} {100*(r>0).mean():>6.1f}")
    if dont_chase["ret"]:
        r = np.array(dont_chase["ret"]); m = np.array(dont_chase["mae"])
        print(f"\nDON'T CHASE (demoted tops): n={len(r)} fwd_ret={100*r.mean():.2f}% "
              f"median={100*np.median(r):.2f}% MAE={100*m.mean():.2f}% win={100*(r>0).mean():.1f}%")
    # headline contrast
    now, caut = buckets.get("now"), buckets.get("caution")
    if now and caut and now["n"] >= 30 and caut["n"] >= 30:
        nm, cm = np.array(now["mae"]), np.array(caut["mae"])
        nr, cr = np.array(now["ret"]), np.array(caut["ret"])
        print(f"\nHEADLINE  'now' vs 'caution':  fwd_ret {100*nr.mean():+.2f}% vs {100*cr.mean():+.2f}%"
              f"  |  MAE {100*nm.mean():.2f}% vs {100*cm.mean():.2f}%  (shallower MAE = better entry)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=8)
    ap.add_argument("--fwd", type=int, default=10)
    ap.add_argument("--years", type=int, default=6)
    a = ap.parse_args()
    run(a.step, a.fwd, a.years)
