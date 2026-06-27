"""DIAGNOSTIC v3 (microscope) — EXIT POLICY on different archetypes.

Same refined-TAKE entries; vary only the EXIT:
  OLD  = oscillator sell (CS) / cut         <- the "sells all the way up, can't rebuy" behavior
  NEW  = structural trailing stop (close < rising 8-bar EMA) / cut   <- let-winners-run

Question: does NEW beat OLD on STEEP GRINDS (JNJ/LLY) by holding the run, while OLD may
win on CHOPPY/high-amplitude names (MCD)? If so, the right exit is ARCHETYPE-DEPENDENT
(validates per-ticker fitting). Last ~3 years of entries.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from confluence import compute_signals
from diagnose_tencent_baba import swing_points, divergence_at
from diagnose_v2 import refined_buy, FAST_SPAN

ROOT = pd.Timestamp  # noqa
import pathlib
DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "stocks"
SINCE = pd.Timestamp("2023-06-01")


def sim(sig, mode, hi, lo):
    c, ef, macd, idx, n = sig["close"], sig["ema_fast"], sig["macd"], sig.index, len(sig)
    pos = 0; ei = None; ep = None
    trades, overridden = [], 0
    for i in range(n - 1):
        if pos == 0:
            if idx[i] < SINCE:
                continue
            if sig["CB"].iloc[i] or sig["revBuy"].iloc[i]:
                dec, _ = refined_buy(i, sig, divergence_at(i, c, macd, hi, lo), n)
                if dec == "TAKE":
                    pos, ei, ep = 1, i, float(c.iloc[i + 1])
        else:
            osc = bool(sig["CS"].iloc[i] or sig["revSell"].iloc[i])
            struct = bool(c.iloc[i] < ef.iloc[i] or sig["revSell"].iloc[i])
            ex = osc if mode == "OLD" else struct
            if mode == "NEW" and bool(sig["CS"].iloc[i]) and not struct:
                overridden += 1
            if ex:
                xp = float(c.iloc[i + 1]); peak = float(c.iloc[ei + 1:i + 2].max())
                trades.append((xp / ep - 1, xp / peak - 1)); pos = 0
    if pos == 1:
        xp = float(c.iloc[-1]); peak = float(c.iloc[ei + 1:].max())
        trades.append((xp / ep - 1, xp / peak - 1))
    if not trades:
        return None
    rets = np.array([t[0] for t in trades])
    comp = np.prod(1 + rets) - 1
    wins = (rets > 0).mean()
    return {"n": len(trades), "comp": 100 * comp, "wr": 100 * wins,
            "giveback": 100 * np.mean([t[1] for t in trades]), "overridden": overridden}


def run(tickers):
    print(f"{'ticker':7s}{'archetype':14s}{'policy':5s}{'trades':>7s}{'WR%':>6s}"
          f"{'captured%':>11s}{'avgGiveback%':>13s}{'oscSellsHeld':>13s}")
    print("-" * 80)
    for t, arch in tickers:
        sig = compute_signals(pd.read_parquet(DATA / f"{t}.parquet")["close"].dropna())
        if sig.empty:
            print(f"{t:7s} thin"); continue
        sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"]).copy()
        sig["ema_fast"] = sig["close"].ewm(span=FAST_SPAN, min_periods=FAST_SPAN).mean()
        hi, lo = swing_points(sig["close"])
        old, new = sim(sig, "OLD", hi, lo), sim(sig, "NEW", hi, lo)
        for label, m in (("OLD", old), ("NEW", new)):
            if not m:
                continue
            od = m["overridden"] if label == "NEW" else 0
            print(f"{t:7s}{arch:14s}{label:5s}{m['n']:>7d}{m['wr']:>6.0f}"
                  f"{m['comp']:>11.0f}{m['giveback']:>13.1f}{od:>13d}")
        print()


if __name__ == "__main__":
    run([("JNJ", "steep-grind"), ("LLY", "steep-grind"),
         ("WMT", "grind"), ("MCD", "choppy/range"), ("NVDA", "high-beta")])
