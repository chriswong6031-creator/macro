"""DIAGNOSTIC v2 (microscope) — does the REFINED logic pass the 3 criteria?
  (a) still TAKE the July-2025 bottom buy
  (b) BLOCK all four Tencent fakeouts (Jan x2, Mar, Jun)
  (c) exit the Feb-2026 BABA top on a STRUCTURAL trailing stop (not weekly-MACD)

Refined buy  = confluence cross + reclaim-and-hold + bearish-divergence veto
               + (below-200 & weekly-down => require a 200MA reclaim, not a hard gate)
Refined exit = oscillator top -> TRIM; the runner exits on close < rising fast EMA
               (structural trailing stop), which doesn't lag like weekly MACD.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from confluence import compute_signals
from diagnose_tencent_baba import load_tencent, load_baba, swing_points, divergence_at

SINCE = pd.Timestamp("2025-06-15")
FAST_SPAN = 8   # ~24 trading days trailing trend line on the 3D


def refined_buy(i: int, sig: pd.DataFrame, div: str, n: int):
    c, a200 = sig["close"], sig["above200"]
    if div == "bear-div":
        return "BLOCK", "veto: bearish divergence"
    held = (i + 1 < n) and c.iloc[i + 1] > c.iloc[i]          # reclaim-and-hold
    below200 = not bool(a200.iloc[i]); weekly_dn = not bool(sig["w_bull"].iloc[i])
    if below200 and weekly_dn:                                # counter-trend: raise the bar
        reclaim = (i + 2 < n) and (bool(a200.iloc[i + 1]) or bool(a200.iloc[i + 2]))
        if held and reclaim:
            return "TAKE", "reclaimed 200 & held"
        return "BLOCK", "counter-trend, no 200-reclaim/hold"
    return ("TAKE", "held confirmation") if held else ("BLOCK", "failed reclaim-and-hold")


def analyze(name: str, close: pd.Series) -> dict:
    sig = compute_signals(close).dropna(subset=["macd", "sig", "k", "d", "rsi14"]).copy()
    sig["ema_fast"] = sig["close"].ewm(span=FAST_SPAN, min_periods=FAST_SPAN).mean()
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    hi, lo = swing_points(c)

    print(f"\n================ {name} ================")
    print("-- BUYS: old vs refined --")
    print(f"{'date':12s}{'price':>8s}{'vs200':>7s}{'wkly':>6s}{'diverg':>10s}"
          f"{'fwd60':>8s}  refined")
    takes_july = blocks = total_fakeouts = 0
    fakeout_dates = {"2026-01", "2026-03", "2026-06"}  # months of the known fakeouts
    for i in range(n):
        if idx[i] < SINCE:
            continue
        r = sig.iloc[i]
        if not (r["CB"] or r["revBuy"]):
            continue
        div = divergence_at(i, c, macd, hi, lo)
        decision, why = refined_buy(i, sig, div, n)
        f60 = (float(c.iloc[i + 20]) / float(c.iloc[i]) - 1) * 100 if i + 20 < n else np.nan
        f60s = f"{f60:+.1f}%" if not np.isnan(f60) else "  n/a"
        vs = "below" if not r["above200"] else "above"
        wk = "up" if r["w_bull"] else "dn"
        mark = ""
        if not np.isnan(f60):
            good = (decision == "TAKE" and f60 > 0) or (decision == "BLOCK" and f60 < 0)
            mark = "OK" if good else "!!"
        print(f"{str(idx[i].date()):12s}{r['close']:>8.1f}{vs:>7s}{wk:>6s}{div:>10s}"
              f"{f60s:>8s}  {decision:5s} {mark}  ({why})")

    # ---- structural trailing-stop exits ----
    below_fast = (c < sig["ema_fast"])
    cross_dn = below_fast & ~below_fast.shift(1).fillna(False)
    hits = [idx[i] for i in range(n) if idx[i] >= SINCE and cross_dn.iloc[i]]
    print("\n-- structural trailing-stop (close < rising fast EMA) trigger dates --")
    print("   " + ", ".join(str(d.date()) for d in hits))
    return {"sig": sig, "hits": hits}


def runner(name, sig, entry_date, top_date=None):
    """Show the runner: enter at entry_date, exit at first structural stop after."""
    c, ef, idx = sig["close"], sig["ema_fast"], sig.index
    ei = idx.get_indexer([pd.Timestamp(entry_date)], method="nearest")[0]
    ep = float(c.iloc[ei])
    for j in range(ei + 1, len(sig)):
        if c.iloc[j] < ef.iloc[j]:
            xp = float(c.iloc[j])
            peak = float(c.iloc[ei:j + 1].max())
            print(f"  {name}: enter {idx[ei].date()} @{ep:.1f} -> structural exit "
                  f"{idx[j].date()} @{xp:.1f}  = {100*(xp/ep-1):+.1f}%  "
                  f"(peak {peak:.1f}; gave back {100*(xp/peak-1):.1f}% from peak)")
            return
    print(f"  {name}: still held from {idx[ei].date()} (no structural stop hit)")


if __name__ == "__main__":
    t = analyze("TENCENT 0700.HK", load_tencent())
    b = analyze("BABA", load_baba())
    print("\n================ CRITERIA CHECK ================")
    print("(a) July-2025 bottom buy & let-winners-run on the rally:")
    runner("TENCENT", t["sig"], "2025-07-16")
    print("(c) Feb-2026 BABA top — does the structural stop catch it early?")
    runner("BABA(from Feb top)", b["sig"], "2026-02-11")
