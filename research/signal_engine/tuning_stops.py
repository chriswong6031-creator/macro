"""Entry quality under the OWNER'S ACTUAL risk model — a TIGHT HARD STOP (~-5% or less)
+ discretionary watchlist surfacing — NOT hold-to-opposite-signal.

The prior studies measured the max drawdown of a position HELD to the opposite confluence
signal. That overstates risk for a trader who cuts decisively at <= -5% the moment the entry
thesis breaks, and who supplies their own timing + sector gates. This re-evaluates the SAME
entry signals the RIGHT way for a watchlist / pre-emptive surfacing tool, using a triple-
barrier walk over the daily OHLC from each buy fill:

  * STOPPED   = intrabar low touches entry*(1 - S) within N days  -> a fake, cut at -S
  * else MFE  = max favorable excursion (high/entry - 1) before stop/timeout = the ROOM it gave
  * CLEAN     = not stopped AND MFE >= TARGET  -> got in with room and it ran

A GREAT entry signal under a tight stop => LOW stop-out rate + HIGH MFE + HIGH clean-rate.
This is entry-LOCATION quality, not held-position drawdown. Per-trade loss is capped at -S by
construction, so max-DD is irrelevant here; the risk that matters is the STOP-OUT FREQUENCY.

Run:  python3 research/signal_engine/tuning_stops.py                 # table, S=5%
      python3 research/signal_engine/tuning_stops.py m2d_s3d_early --stop 0.05 --json
"""
from __future__ import annotations

import sys
import glob
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tuning_harness as H   # noqa: E402

N_DAYS = 20      # time barrier (trading days)
TARGET = 0.05    # MFE needed to call an entry "clean" (got room and ran)

VARIANTS = ["base3d", "m2d_s3d", "m2d_s3d_early", "stochlead3d",
            "early_vol", "early_hl", "early_vol_50"]


def evaluate(daily, high, low, cfg, stop, use_filter=False):
    """Per-signal triple-barrier outcomes under a hard -stop. Leak-free: entry = next
    daily close; barriers walk strictly forward over realized OHLC."""
    fr = H.build_signals(daily, cfg, high, low)
    buy = fr["buy"].to_numpy()
    if use_filter:
        buy = H.daily_filter(fr).to_numpy()
    c = daily.to_numpy()
    h = high.to_numpy() if high is not None else c
    lo = low.to_numpy() if low is not None else c
    idx = daily.index
    n = len(c)
    rows = []
    for i in np.where(buy)[0]:
        f = i + 1
        if f >= n or idx[i] < H.SINCE:
            continue
        entry = c[f]
        stop_px = entry * (1 - stop)
        stopped = False
        days = None
        mfe = 0.0
        end = min(f + N_DAYS, n - 1)
        for j in range(f + 1, end + 1):
            mfe = max(mfe, h[j] / entry - 1)
            if lo[j] <= stop_px:
                stopped = True
                days = j - f
                break
        ret_to = c[end] / entry - 1
        rows.append({"stopped": int(stopped), "mfe": mfe,
                     "days_to_stop": days if stopped else N_DAYS,
                     "clean": int((not stopped) and mfe >= TARGET),
                     "ret_timeout": ret_to})
    return rows


def run_panel(variant, stop, tickers=None, use_filter=False):
    cfg = H.VARIANTS[variant]
    files = sorted(glob.glob(str(H.DATA / "*.parquet")))
    if tickers:
        files = [f for f in files if Path(f).stem in set(tickers)]
    per = []
    for fp in files:
        t = Path(fp).stem
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) < 400:
                continue
            hi = df["high"].reindex(daily.index)
            loo = df["low"].reindex(daily.index)
            rows = evaluate(daily, hi, loo, cfg, stop, use_filter)
            if not rows:
                continue
            d = pd.DataFrame(rows)
            per.append({"t": t, "n": len(d),
                        "stop_rate": float(100 * d["stopped"].mean()),
                        "clean_rate": float(100 * d["clean"].mean()),
                        "med_mfe": float(100 * d["mfe"].median()),
                        "mean_mfe": float(100 * d["mfe"].mean())})
        except Exception:
            continue
    return per


def agg(variant, stop, per):
    f = lambda k: float(np.mean([x[k] for x in per])) if per else 0.0
    return {"variant": variant, "stop": stop, "n_names": len(per),
            "avg_signals": round(f("n"), 2),
            "stop_rate": round(f("stop_rate"), 1),     # % of entries faked down to -stop (LOWER better)
            "clean_rate": round(f("clean_rate"), 1),   # % that gave room & ran +TARGET (HIGHER better)
            "med_mfe": round(f("med_mfe"), 2),
            "mean_mfe": round(f("mean_mfe"), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", nargs="?", default="")
    ap.add_argument("--stop", type=float, default=0.05)
    ap.add_argument("--filter", default="off", choices=["on", "off"])
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dump", default="")
    a = ap.parse_args()
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()] or None
    uf = a.filter == "on"
    variants = [a.variant] if a.variant else VARIANTS
    out = []
    for v in variants:
        per = run_panel(v, a.stop, tickers, uf)
        s = agg(v, a.stop, per)
        out.append(s)
        if a.dump:
            Path(a.dump).parent.mkdir(parents=True, exist_ok=True)
            Path(a.dump).write_text(json.dumps({"agg": s, "per_name": per}))
    if a.json:
        print(json.dumps(out[0] if a.variant else out))
        return
    print(f"\n=== entry quality under a -{a.stop*100:.0f}% hard stop (N={N_DAYS}d, target +{TARGET*100:.0f}%), filter={a.filter} ===")
    print(f"{'variant':16s}{'sigs':>6s}{'stop_rate%':>11s}{'clean%':>8s}{'medMFE%':>9s}{'meanMFE%':>10s}")
    for s in out:
        print(f"{s['variant']:16s}{s['avg_signals']:>6.1f}{s['stop_rate']:>11.1f}"
              f"{s['clean_rate']:>8.1f}{s['med_mfe']:>9.2f}{s['mean_mfe']:>10.2f}")


if __name__ == "__main__":
    main()
