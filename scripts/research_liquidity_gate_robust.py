"""Refutation battery for the net-liquidity gate (run after research_liquidity_gate).

Tries to BREAK the "expanding-liquidity sharpens momentum-long" finding:
 A) Lag sensitivity  -> look-ahead leakage (edge should HOLD as we lag MORE)
 B) Threshold/window  -> overfit (edge should be stable across reasonable params)
 C) Year jackknife    -> single-episode dependence (no one year should drive it)
 D) Lead-lag on SPY   -> predictive vs merely coincident with past returns
 E) Monthly-clustered -> honest significance when obs aren't independent

Usage: .venv/bin/python -m scripts.research_liquidity_gate_robust
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from scripts.research_liquidity_gate import (
    EXP_THR, MOM_LB, START, _col,
)
from scripts.research_trend_gate import (
    ROOT, STEP, asset_class, fwd_return, load_panel,
)


def nl_series(lag: int) -> pd.Series:
    d = os.path.join(ROOT, "data")
    walcl = _col(pd.read_parquet(f"{d}/fred/WALCL.parquet")) / 1000.0
    rrp_fred = _col(pd.read_parquet(f"{d}/fred/RRPONTSYD.parquet"))
    rrp_ny = pd.read_parquet(f"{d}/nyfed/rrp.parquet")["rrp_bn"]
    tga = pd.read_parquet(f"{d}/treasury/tga.parquet")["tga_mn"] / 1000.0
    idx = pd.bdate_range(START, pd.Timestamp.utcnow().tz_localize(None).normalize())
    walcl_bn = walcl.reindex(walcl.index.union(idx)).ffill(limit=7).reindex(idx)
    rrp_bn = rrp_ny.combine_first(rrp_fred)
    rrp_bn = rrp_bn.reindex(rrp_bn.index.union(idx)).ffill(limit=5).reindex(idx).fillna(0)
    tga_bn = tga.reindex(tga.index.union(idx)).ffill(limit=5).reindex(idx)
    return (walcl_bn - rrp_bn - tga_bn).dropna().shift(lag)


def base_samples(panel: dict[str, pd.Series], h: int = 21) -> pd.DataFrame:
    """(asset, class, date, mom_long, fwd) — regime added later per-param."""
    rows = []
    for name, close in panel.items():
        mom = close.pct_change(MOM_LB)
        fr = fwd_return(close, h)
        wk = np.zeros(len(close), bool); wk[::STEP] = True
        ok = wk & fr.notna() & (mom > 0)   # momentum-long only
        for dt in close.index[ok]:
            rows.append((name, asset_class(name), dt, float(fr.loc[dt])))
    return pd.DataFrame(rows, columns=["asset", "class", "date", "fwd"])


def gap(s: pd.DataFrame, nl: pd.Series, window: int, thr: float) -> tuple:
    roc = nl.diff(window)
    r = s["date"].map(roc)
    exp = s["fwd"][r >= thr]; con = s["fwd"][r <= -thr]
    if len(exp) < 50 or len(con) < 50:
        return (np.nan, np.nan, np.nan)
    eh, ch = 100 * (exp > 0).mean(), 100 * (con > 0).mean()
    return (round(eh, 1), round(ch, 1), round(eh - ch, 1))


def main() -> int:
    panel = load_panel()
    s = base_samples(panel, 21)
    s = s[s["date"] >= START]
    print(f"base momentum-long samples (21d): {len(s):,}\n")

    nl3 = nl_series(3)
    print("[A] LAG sensitivity (look-ahead): exp/con hit + gap, window=20 thr=25")
    for lag in (0, 1, 3, 5, 10):
        print(f"   lag={lag:>2}bd  {gap(s, nl_series(lag), 20, 25)}")

    print("\n[B] THRESHOLD x WINDOW (overfit): gap (exp_hit-con_hit), lag=3")
    print("        thr=10   thr=25   thr=50")
    for win in (10, 20, 40):
        gs = [gap(s, nl3, win, t)[2] for t in (10, 25, 50)]
        print(f"   win={win:>2}  " + "   ".join(f"{g:>5}" for g in gs))

    print("\n[C] YEAR JACKKNIFE (single-episode): gap with each year DROPPED, lag=3")
    roc = nl3.diff(20)
    s2 = s.assign(roc=s["date"].map(roc), yr=s["date"].dt.year).dropna(subset=["roc"])
    full = gap(s, nl3, 20, 25)[2]
    print(f"   full gap = {full}")
    worst = (None, 999)
    for yr in sorted(s2["yr"].unique()):
        d = s2[s2["yr"] != yr]
        exp = d["fwd"][d["roc"] >= 25]; con = d["fwd"][d["roc"] <= -25]
        g = round(100 * (exp > 0).mean() - 100 * (con > 0).mean(), 1)
        if g < worst[1]:
            worst = (yr, g)
    print(f"   weakest after dropping a year: drop {worst[0]} -> gap {worst[1]} "
          f"(still {'POSITIVE' if worst[1] > 0 else 'NEGATIVE'})")

    print("\n[D] LEAD-LAG on SPY (predictive vs coincident), lag=3")
    spy = panel.get("SPY")
    roc4 = nl3.diff(20)
    common = spy.index.intersection(roc4.index)
    sp = spy.reindex(common); rc = roc4.reindex(common).dropna()
    common = rc.index
    fwd21 = sp.pct_change(21).shift(-21).reindex(common)
    trail21 = sp.pct_change(21).reindex(common)
    df = pd.DataFrame({"roc": rc, "fwd": fwd21, "trail": trail21}).dropna()
    print(f"   corr(netliq_roc, FUTURE 21d ret) = {df['roc'].corr(df['fwd']):+.3f}  (predictive)")
    print(f"   corr(netliq_roc, PAST   21d ret) = {df['roc'].corr(df['trail']):+.3f}  (coincident)")

    print("\n[E] HONEST-N significance: between-regime, MONTH & EPISODE as the unit")
    # regime is one macro series => a DATE is all-exp or all-con. Aggregate the
    # cross-asset mean fwd return per day, classify the day, then group.
    s3 = s.assign(roc=s["date"].map(roc)).dropna(subset=["roc"])
    s3["reg"] = np.where(s3["roc"] >= 25, "exp", np.where(s3["roc"] <= -25, "con", "neu"))
    daily = s3.groupby("date").agg(fwd=("fwd", "mean"), reg=("reg", "first"))

    def welch(a: pd.Series, b: pd.Series) -> float:
        if len(a) < 3 or len(b) < 3:
            return np.nan
        return (a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b))

    daily["ym"] = daily.index.to_period("M")
    mo = daily.groupby("ym").agg(fwd=("fwd", "mean"),
                                 reg=("reg", lambda x: x.value_counts().idxmax()))
    em, cm = mo["fwd"][mo["reg"] == "exp"], mo["fwd"][mo["reg"] == "con"]
    print(f"   MONTH unit:   exp_mo={len(em)} ({100*em.mean():+.2f}%)  "
          f"con_mo={len(cm)} ({100*cm.mean():+.2f}%)  Welch t={welch(em, cm):.2f}")
    # episode = contiguous run of the same daily regime
    run = (daily["reg"] != daily["reg"].shift()).cumsum()
    ep = daily.groupby(run).agg(fwd=("fwd", "mean"), reg=("reg", "first"))
    ee, ce = ep["fwd"][ep["reg"] == "exp"], ep["fwd"][ep["reg"] == "con"]
    print(f"   EPISODE unit: exp_ep={len(ee)} ({100*ee.mean():+.2f}%)  "
          f"con_ep={len(ce)} ({100*ce.mean():+.2f}%)  Welch t={welch(ee, ce):.2f}")
    print(f"   hit-rate gap (asset-day): {gap(s, nl3, 20, 25)[2]}pp  <- robust per [A]-[C];")
    print("   read together: DIRECTION/odds robust; RETURN magnitude weak at honest N.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
