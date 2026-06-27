"""DIAGNOSTIC v4 (microscope) — corrected exit + re-entry, as an ablation.

Policies (same panel, entries since 2023-06):
  OLD     = confluence entry            + oscillator-sell exit      (baseline)
  ATR     = confluence entry            + Chandelier exit (22-ATR x3)
  ATR+PB  = confluence + pullback entry + Chandelier exit

Pullback entry = in a CONFIRMED uptrend (above-200 & weekly-bull & 20-EMA rising),
buy a shallow dip that bounces off the rising 20-EMA (no deep-oversold needed) --
the fix for "can't rebuy in a steep grind" (JNJ).
Chandelier (highest-high-since-entry - 3*ATR) is volatility-scaled, so it widens for
NVDA and tightens for JNJ on its own (principled per-ticker, not hand-tuned).
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

from confluence import compute_signals, rsi
from diagnose_tencent_baba import swing_points, divergence_at
from diagnose_v2 import refined_buy

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "stocks"
SINCE = pd.Timestamp("2023-06-01")
ATR_N, K_CH, EMA_PB = 22, 3.0, 20


def build(ticker):
    df = pd.read_parquet(DATA / f"{ticker}.parquet")
    close = df["close"].dropna()
    sig = compute_signals(close)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"]).copy()
    # 3D OHLC on the SAME bins compute_signals used (3B), aligned to sig.index
    h3 = df["high"].resample("3B").max().reindex(sig.index)
    l3 = df["low"].resample("3B").min().reindex(sig.index)
    c3 = sig["close"]
    tr = pd.concat([h3 - l3, (h3 - c3.shift()).abs(), (l3 - c3.shift()).abs()], axis=1).max(axis=1)
    sig["atr"] = tr.ewm(alpha=1 / ATR_N, min_periods=ATR_N).mean()
    sig["high3"] = h3
    sig["ema20"] = c3.ewm(span=EMA_PB, min_periods=EMA_PB).mean()
    # pullback re-entry: confirmed uptrend + bounce off the rising 20-EMA
    rising = sig["ema20"] > sig["ema20"].shift(2)
    uptrend = sig["above200"] & sig["w_bull"] & rising
    touched = (l3 <= sig["ema20"]) | (l3.shift(1) <= sig["ema20"].shift(1))
    turn_up = (c3 > c3.shift(1)) & (sig["k"] > sig["k"].shift(1))
    sig["pullback"] = (uptrend & touched & turn_up & (c3 > sig["ema20"])).fillna(False)
    return sig


def sim(sig, entry_mode, exit_mode, hi, lo):
    c, idx, n = sig["close"], sig.index, len(sig)
    macd = sig["macd"]
    pos = 0; ei = ep = hh = None
    trades, pb_used = [], 0
    for i in range(n - 1):
        if pos == 0:
            if idx[i] < SINCE:
                continue
            conf = (sig["CB"].iloc[i] or sig["revBuy"].iloc[i]) and \
                refined_buy(i, sig, divergence_at(i, c, macd, hi, lo), n)[0] == "TAKE"
            pb = entry_mode == "pb" and bool(sig["pullback"].iloc[i])
            if conf or pb:
                pos, ei, ep = 1, i, float(c.iloc[i + 1])
                hh = float(sig["high3"].iloc[i + 1])
                if pb and not conf:
                    pb_used += 1
        else:
            hh = max(hh, float(sig["high3"].iloc[i]))
            if exit_mode == "oscillator":
                ex = bool(sig["CS"].iloc[i] or sig["revSell"].iloc[i])
            else:  # chandelier
                stop = hh - K_CH * float(sig["atr"].iloc[i])
                ex = bool(c.iloc[i] < stop or sig["revSell"].iloc[i])
            if ex:
                xp = float(c.iloc[i + 1]); peak = float(c.iloc[ei + 1:i + 2].max())
                trades.append((xp / ep - 1, xp / peak - 1)); pos = 0
    if pos == 1:
        xp = float(c.iloc[-1]); peak = float(c.iloc[ei + 1:].max())
        trades.append((xp / ep - 1, xp / peak - 1))
    if not trades:
        return None
    r = np.array([t[0] for t in trades])
    return {"n": len(trades), "wr": 100 * (r > 0).mean(), "comp": 100 * (np.prod(1 + r) - 1),
            "giveback": 100 * np.mean([t[1] for t in trades]), "pb": pb_used}


def run(tickers):
    print(f"{'ticker':7s}{'archetype':13s}{'policy':9s}{'trades':>7s}{'WR%':>6s}"
          f"{'captured%':>11s}{'giveback%':>11s}{'pbEntries':>10s}")
    print("-" * 74)
    for t, arch in tickers:
        sig = build(t)
        if sig is None:
            print(f"{t:7s} thin"); continue
        hi, lo = swing_points(sig["close"])
        for label, em, xm in (("OLD", "conf", "oscillator"),
                              ("ATR", "conf", "chandelier"),
                              ("ATR+PB", "pb", "chandelier")):
            m = sim(sig, em, xm, hi, lo)
            if m:
                print(f"{t:7s}{arch:13s}{label:9s}{m['n']:>7d}{m['wr']:>6.0f}"
                      f"{m['comp']:>11.0f}{m['giveback']:>11.1f}{m['pb']:>10d}")
        print()


if __name__ == "__main__":
    run([("JNJ", "steep-grind"), ("LLY", "steep-grind"),
         ("WMT", "grind"), ("MCD", "choppy/range"), ("NVDA", "high-beta")])
