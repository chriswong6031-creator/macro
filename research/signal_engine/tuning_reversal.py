"""FAST-REVERSAL (false-breakout / false-breakdown) detection study.

The engine ALREADY has the owner's anti-shakeout mechanism: cut a long if MACD crosses
bearish within REV_BARS of the buy (the breakout failed), re-buy if MACD crosses bullish
within REV_BARS of the sell (the breakdown failed). It currently runs on the LAGGING 3D
MACD with REV_BARS=3 (= up to 9 trading days). The owner's question: detect the failure on
the FASTER 2D MACD (and/or a tighter window) to cut/re-buy SOONER — dodging the drawdown of
a liquidity-sweep breakdown and catching the rally after a fake sell.

This tests that the CHARTER way: held-out DRAWDOWN (primary) + cut/re-buy QUALITY + the
WHIPSAW cost (the danger: a faster trigger manufactures the head-fakes it means to dodge).
NEVER beat-buy-and-hold. Leak-free: entries = raw base3d CB (no forward-peeking filter),
reversal = backward-looking MACD crosses on the chosen TF, fills at the next daily close.

Run:  python3 research/signal_engine/tuning_reversal.py            # panel table
      python3 research/signal_engine/tuning_reversal.py rev2d_6 --json
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

FWD_K = 20          # forward window (trading days) to judge a cut / re-buy
WHIP = 0.04         # a cut is a "whipsaw" if price is >+4% above the cut FWD_K days later

# (rev_tf bars, window in TRADING DAYS, use_reversal). Window in days makes 2D vs 3D fair:
# the faster TF detects the SAME cross sooner inside the same calendar window.
VARIANTS = {
    "none":       dict(rev_tf=3, win=0,  use=False),   # ablation: CB/CS only, no reversal
    "rev3d_9":    dict(rev_tf=3, win=9,  use=True),     # CURRENT engine (REV_BARS=3 on 3D)
    "rev3d_6":    dict(rev_tf=3, win=6,  use=True),     # tighter 3D (~2 ticks)
    "rev2d_4":    dict(rev_tf=2, win=4,  use=True),     # fast TF, tight window
    "rev2d_6":    dict(rev_tf=2, win=6,  use=True),     # fast TF, ~current window
    "rev2d_9":    dict(rev_tf=2, win=9,  use=True),     # fast TF, wide window
    "rev1d_6":    dict(rev_tf=1, win=6,  use=True),     # fastest TF
    "rev2d_6_cutonly": dict(rev_tf=2, win=6, use=True, side="cut"),    # only the protective cut
    "rev2d_6_rebuyonly": dict(rev_tf=2, win=6, use=True, side="rebuy"),  # only the re-buy
}


def _base_cb_cs(daily):
    """base3d confirmed BUY (CB) and confirmed SELL (CS) as daily-event booleans (leak-free)."""
    cb = H.build_signals(daily, H.VARIANTS["base3d"])["buy"].to_numpy()
    cs = H.common_exit(daily).reindex(daily.index).fillna(False).to_numpy()
    return cb, cs


def _rev_crosses(daily, tf):
    """rev-TF MACD bull/bear crosses, mapped to daily known-date events (leak-free)."""
    s, kn = H.tf_bars(daily, tf)
    macd, sig = H.rsi_macd(s)
    bull = H.to_daily(H.xup(macd, sig).fillna(False), kn, daily.index, "event").to_numpy()
    bear = H.to_daily(H.xdn(macd, sig).fillna(False), kn, daily.index, "event").to_numpy()
    return bull, bear


def simulate(daily, cfg):
    c = daily.to_numpy()
    idx = daily.index
    n = len(c)
    cb, cs = _base_cb_cs(daily)
    bull, bear = _rev_crosses(daily, cfg["rev_tf"])
    use = cfg["use"]
    win = cfg["win"]
    side = cfg.get("side", "both")
    do_cut = use and side in ("both", "cut")
    do_rebuy = use and side in ("both", "rebuy")

    pos = 0
    ep = last_entry = last_exit = None
    trades = []          # (ret, was_reversal_exit)
    cuts = []            # daily idx of each protective cut
    rebuys = []          # daily idx of each re-buy
    eq = 1.0
    curve = [1.0]
    for i in range(n - 1):
        if pos == 1:
            eq *= c[i + 1] / c[i]
        curve.append(eq)
        if pos == 0:
            if idx[i] < H.SINCE:
                # still track last_exit so an early re-buy can reference it
                if cs[i]:
                    last_exit = i
                continue
            rebuy = do_rebuy and bull[i] and (last_exit is not None) and (i - last_exit) <= win
            if cb[i] or rebuy:
                pos, ep, last_entry = 1, c[i + 1], i
                if rebuy and not cb[i]:
                    rebuys.append(i)
        else:
            cut = do_cut and bear[i] and (last_entry is not None) and (i - last_entry) <= win
            if cs[i] or cut:
                trades.append((c[i + 1] / ep - 1, bool(cut and not cs[i])))
                pos, last_exit = 0, i
                if cut and not cs[i]:
                    cuts.append(i)
    if pos == 1:
        trades.append((c[-1] / ep - 1, False))

    eqc = np.array(curve)
    dd = float((eqc / np.maximum.accumulate(eqc) - 1).min())
    r = np.array([t[0] for t in trades]) if trades else np.array([0.0])
    losses = r[r < 0]

    def fwd(ix):
        out = [c[min(j + FWD_K, n - 1)] / c[j] - 1 for j in ix]
        return np.array(out) if out else np.array([])

    cf, rf = fwd(cuts), fwd(rebuys)
    span_yrs = max((idx[-1] - idx[0]).days, 1) / 365.25
    return {
        "n_trades": len(trades), "dd": 100 * dd,
        "wr": 100 * (r > 0).mean() if trades else 0.0,
        "avg_loss": 100 * losses.mean() if len(losses) else 0.0,
        "worst": 100 * r.min() if trades else 0.0,
        "cap": 100 * (eqc[-1] - 1),
        "n_cut": len(cuts), "n_rebuy": len(rebuys),
        "cuts_per_yr": len(cuts) / span_yrs, "rebuys_per_yr": len(rebuys) / span_yrs,
        # cut quality: avg forward return AFTER a cut. NEGATIVE = the cut dodged a further drop.
        "cut_fwd": 100 * cf.mean() if len(cf) else 0.0,
        "cut_whipsaw_pct": 100 * (cf > WHIP).mean() if len(cf) else 0.0,   # price rallied >4% after we cut
        # re-buy quality: avg forward return after re-buying. POSITIVE = caught the rally.
        "rebuy_fwd": 100 * rf.mean() if len(rf) else 0.0,
        "rebuy_good_pct": 100 * (rf > 0).mean() if len(rf) else 0.0,
    }


def run_panel(variant, tickers=None):
    cfg = VARIANTS[variant]
    files = sorted(glob.glob(str(H.DATA / "*.parquet")))
    if tickers:
        files = [f for f in files if Path(f).stem in set(tickers)]
    rows = []
    for fp in files:
        t = Path(fp).stem
        try:
            daily = pd.read_parquet(fp)["close"].dropna()
            if len(daily) < 400:
                continue
            m = simulate(daily, cfg)
            if m["n_trades"]:
                m["t"] = t
                rows.append(m)
        except Exception:
            continue
    return rows


def agg(variant, rows):
    f = lambda k: float(np.mean([r[k] for r in rows])) if rows else 0.0
    return {"variant": variant, "n_names": len(rows),
            **{k: round(f(k), 3) for k in ("dd", "wr", "avg_loss", "worst", "cap",
               "n_trades", "cuts_per_yr", "rebuys_per_yr", "cut_fwd", "cut_whipsaw_pct",
               "rebuy_fwd", "rebuy_good_pct")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", nargs="?", default="")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dump", default="")
    a = ap.parse_args()
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()] or None
    variants = [a.variant] if a.variant else list(VARIANTS)
    out = []
    for v in variants:
        rows = run_panel(v, tickers)
        s = agg(v, rows)
        out.append(s)
        if a.dump:
            Path(a.dump).parent.mkdir(parents=True, exist_ok=True)
            Path(a.dump).write_text(json.dumps({"agg": s, "per_name": rows}))
    if a.json:
        print(json.dumps(out[0] if a.variant else out))
        return
    cols = ("dd", "worst", "avg_loss", "wr", "cap", "n_trades", "cuts_per_yr",
            "cut_fwd", "cut_whipsaw_pct", "rebuys_per_yr", "rebuy_fwd", "rebuy_good_pct")
    print(f"{'variant':18s}" + "".join(f"{k:>11s}" for k in cols))
    for s in out:
        print(f"{s['variant']:18s}" + "".join(f"{s[k]:>11.2f}" for k in cols))


if __name__ == "__main__":
    main()
