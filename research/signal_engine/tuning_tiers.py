"""ASSESSMENT of the owner's TIERED confluence cascade (T1 master -> T4 earliest).

The signal is one DOOR in a cascade (sector-cycle engine + the owner's sector/rotation/
leadership read are the other doors), NOT an autonomous algo. So each tier is judged on the
balance the owner cares about: EARLINESS (how many trading days it leads the master
confirmation) vs GARBAGE-RATE (stop-out under a tight -5% hard stop = the unbuyable picks that
cause drawdowns). Faithful RSI-MACD + stoch-of-RSI, leak-free, close-only.

Tiers (strongest/most-confirmed -> earliest/lowest-weight):
  T1 master    : 3D MACD-RSI cross  & 3D StochRSI crossed (recent)              [the keeper]
  T2 early     : 2D MACD-RSI cross  & 3D StochRSI crossed (recent)             [= m2d_s3d]
  T3 earlier   : 2D MACD-RSI PROJECTED<=1-2d & 3D StochRSI already crossed     [= early_now]
  T4 earliest  : 2D MACD-RSI PROJECTED & 2D StochRSI crossed & ABOVE 200MA     [anti-falling-knife]
Confidence modifier (orthogonal): the stoch cross came from DEEP oversold (<20, higher conf)
vs a SHALLOW cross (above 20, lower conf — non-volatile selling that still rebounds).

Run:  python3 research/signal_engine/tuning_tiers.py [--stop 0.05] [--tickers AAPL,NVDA]
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
import tuning_harness as H   # tf_bars, to_daily, rsi_macd, stoch_rsi_kd, xup, since, rsi

CONF_W, OS, BUY_RSI_MAX = 8, 20, 65
EARLY_CROSS_BARS = 1.5       # 2D cross "projected within ~1-2 days"
FWD_K = 20                   # triple-barrier horizon (trading days)
TARGET = 0.05                # +TARGET before -stop = a CLEAN entry
LEAD_WIN = 15                # days to associate an earlier tier with a later master fire
COOLDOWN = 5                 # min trading days between same-tier events (dedupe)
TIERS = ["T1_master", "T2_early", "T3_earlier", "T4_earliest", "T4_no200"]


def _blocks(daily: pd.Series):
    """All leak-free building blocks on the daily grid."""
    di = daily.index
    # 2D MACD-RSI + imminent-cross projection
    sm2, k2known = H.tf_bars(daily, 2)
    m2, s2 = H.rsi_macd(sm2)
    h2 = m2 - s2
    mb2 = H.xup(m2, s2)
    slope2 = h2 - h2.shift(1)
    btc = (-h2 / slope2)
    imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)
    # 3D MACD-RSI
    sm3, k3known = H.tf_bars(daily, 3)
    m3, s3 = H.rsi_macd(sm3)
    mb3 = H.xup(m3, s3)
    # 3D StochRSI (+from-oversold)
    kk3, dd3 = H.stoch_rsi_kd(sm3)
    sb3 = H.xup(kk3, dd3)
    recent3 = H.since(sb3) <= CONF_W
    fromos3 = dd3.rolling(CONF_W).min() < OS
    r14_3 = H.rsi(sm3, 14)
    # 2D StochRSI
    kk2, dd2 = H.stoch_rsi_kd(sm2)
    sb2 = H.xup(kk2, dd2)
    recent2 = H.since(sb2) <= CONF_W
    fromos2 = dd2.rolling(CONF_W).min() < OS
    # weekly confirm + 200MA
    wk = daily.resample("W-FRI").last().dropna()
    wm, ws = H.rsi_macd(wk)
    wbull = (wm >= ws).shift(1)
    ma200 = daily.rolling(200).mean()

    td = lambda s, kn, how="ffill": H.to_daily(s, kn, di, how)
    B = {
        "mb2_evt": td(mb2.fillna(False), k2known, "event"),
        "imm2": td(imm2.fillna(False), k2known).fillna(False),
        "mb3_evt": td(mb3.fillna(False), k3known, "event"),
        "recent3": td(recent3.fillna(False), k3known).fillna(False),
        "fromos3": td(fromos3.fillna(False), k3known).fillna(False),
        "recent2": td(recent2.fillna(False), k2known).fillna(False),
        "fromos2": td(fromos2.fillna(False), k2known).fillna(False),
        "r14_3": td(r14_3, k3known),
        "wbull": wbull.reindex(di, method="ffill").fillna(False).astype(bool),
        "above200": (daily > ma200).fillna(False),
    }
    return B


def _tier_masks(daily: pd.Series, B: dict):
    """Boolean 'tier fires today' per bar, before edge/cooldown dedupe."""
    rsi_ok = (B["r14_3"] < BUY_RSI_MAX).fillna(False)
    confirm = (B["wbull"] | B["fromos3"])           # weekly up OR 3D stoch from oversold
    t1 = (B["mb3_evt"] & B["recent3"] & confirm & rsi_ok)
    t2 = (B["mb2_evt"] & B["recent3"] & confirm & rsi_ok)
    t3 = (B["imm2"] & B["recent3"] & confirm & rsi_ok)
    # T4 uses the 2D stoch gate + a HARD above-200 (anti-falling-knife), so it does not lean
    # on the 3D-from-oversold confirm; weekly OR 2D-from-oversold keeps it from pure noise.
    confirm2 = (B["wbull"] | B["fromos2"])
    t4base = (B["imm2"] & B["recent2"] & confirm2 & rsi_ok)
    t4 = (t4base & B["above200"])                 # the anti-falling-knife gate
    t4_no200 = t4base                             # ABLATION: same tier without the 200MA gate
    return {"T1_master": t1.fillna(False), "T2_early": t2.fillna(False),
            "T3_earlier": t3.fillna(False), "T4_earliest": t4.fillna(False),
            "T4_no200": t4_no200.fillna(False)}


def _events(mask: pd.Series):
    """Rising-edge event bar indices with a cooldown (distinct entries)."""
    idx = np.where((mask & ~mask.shift(1).fillna(False)).to_numpy())[0]
    out = []
    for i in idx:
        if not out or (i - out[-1]) >= COOLDOWN:
            out.append(int(i))
    return out


def _barrier(c, h, lo, f, stop):
    """Triple-barrier from fill bar f: stopped (low<=-stop within FWD_K) else MFE/clean."""
    n = len(c)
    entry = c[f]
    stop_px = entry * (1 - stop)
    end = min(f + FWD_K, n - 1)
    mfe = 0.0
    for j in range(f + 1, end + 1):
        mfe = max(mfe, h[j] / entry - 1)
        if lo[j] <= stop_px:
            return {"stopped": 1, "mfe": mfe, "clean": 0}
    return {"stopped": 0, "mfe": mfe, "clean": int(mfe >= TARGET)}


def assess_name(daily, high, low, stop):
    c = daily.to_numpy()
    h = high.to_numpy() if high is not None else c
    lo = low.to_numpy() if low is not None else c
    idx = daily.index
    n = len(c)
    B = _blocks(daily)
    masks = _tier_masks(daily, B)
    fromos3 = B["fromos3"].to_numpy()
    above200 = B["above200"].to_numpy()
    ev = {t: _events(masks[t]) for t in TIERS}
    t1_fills = [e + 1 for e in ev["T1_master"] if e + 1 < n and idx[e] >= H.SINCE]

    out = {t: [] for t in TIERS}
    extra = {t: 0 for t in TIERS}          # events NOT shadowed by an earlier-or-equal master
    shallow = {"deep": [], "shallow": []}  # T2 split by from-oversold (confidence modifier)
    t4_above = []                          # T4 always above200 by construction; sanity
    for t in TIERS:
        for e in ev[t]:
            f = e + 1
            if f >= n or idx[e] < H.SINCE:
                continue
            r = _barrier(c, h, lo, f, stop)
            r["lead"] = None
            # lead vs the master: nearest LATER T1 fill within LEAD_WIN
            laters = [tf for tf in t1_fills if 0 < (tf - f) <= LEAD_WIN]
            if laters:
                r["lead"] = min(laters) - f
            out[t].append(r)
            if t == "T2_early":
                (shallow["deep"] if bool(fromos3[e]) else shallow["shallow"]).append(r)
    return {"events": out, "shallow": shallow}


def _agg(rows):
    if not rows:
        return {"n": 0}
    st = np.mean([r["stopped"] for r in rows])
    cl = np.mean([r["clean"] for r in rows])
    mfe = np.mean([r["mfe"] for r in rows])
    leads = [r["lead"] for r in rows if r["lead"] is not None]
    return {"n": len(rows), "stop_rate": round(100 * st, 1), "clean_rate": round(100 * cl, 1),
            "mean_mfe": round(100 * mfe, 2),
            "pct_lead_master": round(100 * len(leads) / len(rows), 1),
            "mean_lead_days": round(float(np.mean(leads)), 1) if leads else None}


def run(stop, tickers=None):
    files = sorted(glob.glob(str(H.DATA / "*.parquet")))
    if tickers:
        files = [f for f in files if Path(f).stem in set(tickers)]
    pooled = {t: [] for t in TIERS}
    sh = {"deep": [], "shallow": []}
    for fp in files:
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) < 400:
                continue
            hi = df["high"].reindex(daily.index) if "high" in df else None
            loo = df["low"].reindex(daily.index) if "low" in df else None
            res = assess_name(daily, hi, loo, stop)
            for t in TIERS:
                pooled[t].extend(res["events"][t])
            sh["deep"].extend(res["shallow"]["deep"])
            sh["shallow"].extend(res["shallow"]["shallow"])
        except Exception:
            continue
    return {"stop": stop,
            "tiers": {t: _agg(pooled[t]) for t in TIERS},
            "t2_confidence": {"deep_oversold": _agg(sh["deep"]),
                              "shallow_cross": _agg(sh["shallow"])}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", type=float, default=0.05)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()] or None
    res = run(a.stop, tickers)
    if a.json:
        print(json.dumps(res))
        return
    print(f"\n=== TIERED CASCADE ASSESSMENT  (-{a.stop*100:.0f}% stop, {FWD_K}d, +{TARGET*100:.0f}% target) ===")
    print(f"{'tier':13s}{'events':>8s}{'stop%':>8s}{'clean%':>8s}{'mfe%':>7s}{'%leadMstr':>11s}{'leadDays':>9s}")
    for t in TIERS:
        m = res["tiers"][t]
        if m.get("n"):
            print(f"{t:13s}{m['n']:>8d}{m['stop_rate']:>8.1f}{m['clean_rate']:>8.1f}"
                  f"{m['mean_mfe']:>7.2f}{m['pct_lead_master']:>11.1f}{str(m['mean_lead_days']):>9s}")
    print("\nT2 confidence split (2D-MACD + 3D-stoch):")
    for k, m in res["t2_confidence"].items():
        if m.get("n"):
            print(f"  {k:14s} n={m['n']:>5d}  stop {m['stop_rate']:>5.1f}%  clean {m['clean_rate']:>5.1f}%  mfe {m['mean_mfe']:>5.2f}%")


if __name__ == "__main__":
    main()
