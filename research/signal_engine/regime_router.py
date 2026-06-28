"""REGIME ROUTER (rule-based) — routes entry/exit by regime, then tests it on
DRAWDOWN vs the best fixed rule. Built per the regime-router research:

Features (real-time, filtered, no-lookahead, PERCENTILE not absolute thresholds):
  - efficiency = Kaufman Efficiency Ratio(10) + rolling-regression R2(20)  [trend vs chop axis]
  - vol        = ATR%-percentile                                           [blow-off axis]
  - direction  = engine's own above-200 + weekly gates  (no new params; no ADX)
  - events     = bearish divergence (confirmed pivots) + recent-extended   [topping]
Regimes (5): downtrend / topping / grind / orderly / chop, with 2-bar hysteresis.

Routing:  grind -> confluence+pullback entry, Chandelier trail
          orderly -> confluence entry, Chandelier
          chop -> confluence entry (no pullback), oscillator-top exit
          topping -> no entry, oscillator-top exit
          downtrend -> no entry, fast cut

Honest scope: this is the SUGGESTIVE in-sample read with ROUND, un-tuned defaults.
The verdict test (purged + embargoed walk-forward, net of costs) is the next step.
Metric that matters here = max drawdown vs best fixed (research: regime overlays
earn their keep on drawdown, not return).
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

from confluence import compute_signals
from diagnose_tencent_baba import load_tencent, load_baba, swing_points, divergence_at
from diagnose_v2 import refined_buy

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "stocks"
SINCE = pd.Timestamp("2023-06-01")
ATR_N, K_CH, EMA_PB = 22, 3.0, 20
ER_N, R2_N, PCT_W = 10, 20, 100
EFF_HI, EFF_LO, VOL_TOP = 0.60, 0.40, 0.90   # percentile cuts (round, un-tuned)

ROUTE = {
    "grind":     ("conf+pb", "chandelier"),
    "orderly":   ("conf",    "chandelier"),
    "chop":      ("conf",    "oscillator"),
    "topping":   ("none",    "oscillator"),
    "downtrend": ("none",    "fastcut"),
}


def _pctrank(s, w=PCT_W):
    return s.rolling(w, min_periods=40).apply(lambda x: (x <= x[-1]).mean(), raw=True)


def _r2(logc, w=R2_N):
    x = np.arange(w)
    return logc.rolling(w).apply(
        lambda y: (np.corrcoef(x, y)[0, 1] ** 2) if np.std(y) > 0 else 0.0, raw=True)


def build(close, high=None, low=None):
    sig = compute_signals(close)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"]).copy()
    c = sig["close"]
    # --- ATR (true if OHLC, else close-to-close proxy) + Chandelier inputs ---
    if high is not None:
        h3 = high.resample("3B").max().reindex(sig.index)
        l3 = low.resample("3B").min().reindex(sig.index)
        tr = pd.concat([h3 - l3, (h3 - c.shift()).abs(), (l3 - c.shift()).abs()], axis=1).max(axis=1)
        sig["hh_src"] = h3
    else:
        tr = c.diff().abs()                 # proxy when no high/low (Tencent/BABA)
        sig["hh_src"] = c
    sig["atr"] = tr.ewm(alpha=1 / ATR_N, min_periods=ATR_N).mean()
    sig["ema20"] = c.ewm(span=EMA_PB, min_periods=EMA_PB).mean()
    rising = sig["ema20"] > sig["ema20"].shift(2)
    up = sig["above200"] & sig["w_bull"]
    touched = (sig["hh_src"] <= sig["ema20"]) | (sig["hh_src"].shift(1) <= sig["ema20"].shift(1))
    sig["pullback"] = (up & touched & (c > c.shift(1)) & (sig["k"] > sig["k"].shift(1)) & (c > sig["ema20"])).fillna(False)
    # --- regime features ---
    er = (c - c.shift(ER_N)).abs() / c.diff().abs().rolling(ER_N).sum()
    eff = (_pctrank(er) + _pctrank(_r2(np.log(c)))) / 2
    volp = _pctrank(sig["atr"] / c)
    sig["volp"] = volp
    ext = (sig["k"].rolling(8).max() >= 80) | (sig["rsi14"].rolling(8).max() >= 70)
    hi, lo = swing_points(c)
    beardiv = pd.Series([divergence_at(i, c, sig["macd"], hi, lo) == "bear-div" for i in range(len(c))], index=c.index)
    down = (~sig["above200"]) & (~sig["w_bull"])
    # --- raw regime label ---
    raw = []
    for i in range(len(sig)):
        if bool(down.iloc[i]):
            lab = "downtrend"
        elif bool(up.iloc[i]):
            if bool(volp.iloc[i] >= VOL_TOP) and bool(ext.iloc[i]) and bool(beardiv.iloc[i]):
                lab = "topping"
            elif eff.iloc[i] >= EFF_HI:
                lab = "grind"
            elif eff.iloc[i] < EFF_LO:
                lab = "chop"
            else:
                lab = "orderly"
        else:
            lab = "chop"               # mixed (one gate up, one down) = cautious
        raw.append(lab)
    # --- 2-bar hysteresis: switch only after a label repeats twice ---
    sm = [raw[0]]
    for i in range(1, len(raw)):
        sm.append(raw[i] if (raw[i] == raw[i - 1] and raw[i] != sm[-1]) else sm[-1])
    sig["regime"] = sm
    return sig


def sim(sig, policy):
    """policy in {'osc','chand','router'}. Returns equity-curve drawdown + capture."""
    c, idx, n = sig["close"], sig.index, len(sig)
    pos = 0; ei = ep = hh = None
    trades = []; eq = 1.0; curve = [1.0]; pb = 0
    regimes_in_trades = []
    for i in range(n - 1):
        if pos == 1:
            eq *= float(c.iloc[i + 1]) / float(c.iloc[i])
        curve.append(eq)
        reg = sig["regime"].iloc[i]
        if policy == "router":
            emode, xmode = ROUTE[reg]
        else:
            emode, xmode = "conf", ("oscillator" if policy == "osc" else "chandelier")
        if pos == 0:
            if idx[i] < SINCE:
                continue
            conf = (sig["CB"].iloc[i] or sig["revBuy"].iloc[i]) and emode != "none" and \
                refined_buy(i, sig, "", n)[0] == "TAKE"
            pull = emode == "conf+pb" and bool(sig["pullback"].iloc[i])
            if conf or pull:
                pos, ei, ep = 1, i, float(c.iloc[i + 1]); hh = float(sig["hh_src"].iloc[i + 1])
                if pull and not conf:
                    pb += 1
        else:
            hh = max(hh, float(sig["hh_src"].iloc[i]))
            if xmode == "chandelier":
                # vol-modulated trail: tighten the multiple when volatility is high
                # (caps drawdown on high-beta momo; keeps the loose trail on calm grinds)
                k = 1.5 if float(sig["volp"].iloc[i]) >= 0.70 else K_CH
                ex = bool(c.iloc[i] < hh - k * float(sig["atr"].iloc[i]) or sig["revSell"].iloc[i])
            elif xmode == "fastcut":
                ex = True
            else:  # oscillator
                ex = bool(sig["CS"].iloc[i] or sig["revSell"].iloc[i])
            if ex:
                xp = float(c.iloc[i + 1]); trades.append(xp / ep - 1); pos = 0
    eqc = np.array(curve)
    dd = (eqc / np.maximum.accumulate(eqc) - 1).min()
    r = np.array(trades) if trades else np.array([0.0])
    return {"n": len(trades), "wr": 100 * (r > 0).mean() if trades else 0,
            "cap": 100 * (eqc[-1] - 1), "dd": 100 * dd, "pb": pb}


def run(items):
    print(f"{'ticker':8s}{'policy':9s}{'trades':>7s}{'WR%':>6s}{'captured%':>11s}{'maxDD%':>9s}")
    print("-" * 50)
    for name, close, hi, lo in items:
        sig = build(close, hi, lo)
        if sig is None:
            print(f"{name:8s} thin"); continue
        res = {p: sim(sig, p) for p in ("osc", "chand", "router")}
        best_fixed_dd = max(res["osc"]["dd"], res["chand"]["dd"])  # less negative = shallower
        for p, lab in (("osc", "FIX-osc"), ("chand", "FIX-chand"), ("router", "ROUTER")):
            m = res[p]
            star = ""
            if p == "router":
                star = "  <- shallower DD than best fixed" if m["dd"] > best_fixed_dd else "  (DD not improved)"
            print(f"{name:8s}{lab:9s}{m['n']:>7d}{m['wr']:>6.0f}{m['cap']:>11.0f}{m['dd']:>9.1f}{star}")
        print()


if __name__ == "__main__":
    us = [("JNJ", "steep-grind"), ("LLY", "sharp-top"), ("WMT", "grind"),
          ("MCD", "choppy"), ("NVDA", "high-beta")]
    items = []
    for t, _ in us:
        df = pd.read_parquet(DATA / f"{t}.parquet")
        items.append((t, df["close"].dropna(), df["high"], df["low"]))
    items.append(("TENCENT", load_tencent(), None, None))
    items.append(("BABA", load_baba(), None, None))
    run(items)
