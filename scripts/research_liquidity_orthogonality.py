"""ORTHOGONALITY HORSE-RACE for the net-liquidity gate.

Refutation lens: is "liquidity expanding" just "the market is already in an uptrend"
(or "vol is calm") in disguise? If a TRIVIAL price/vol regime explains the same
forward edge, the liquidity gate is not orthogonal and not worth wiring.

Same momentum-long sample + same lagged net-liq as research_liquidity_gate.
Trivial regimes (computed on info a trader had that day, no look-ahead):
  - UPTREND  = SPY close > its 200-day SMA
  - CALMVOL  = VIX close <= its trailing 252-day median

Tests:
  (a) liquidity EXPANDING vs CONTRACTING gap (hit% + avg ret + Welch month/episode)
  (b) trivial UPTREND vs DOWNTREND gap, CALMVOL vs HIVOL gap  (same sample)
  (c) DOUBLE-CONDITION: within UPTREND-only periods, does liquidity STILL separate?
      within CONTRACTING-liq only, does SPX>200dma still separate? (who dominates)
  (d) correlation / cross-tab of the two regime labels (how redundant are they?)
  (e) 2x2 cells: liq-regime x trend-regime mean fwd return (is liq a within-cell effect?)

Honest-N: regimes are market-wide, so a DATE is all-exp or all-con. We aggregate
cross-asset mean fwd return per day and run Welch t with MONTH and EPISODE as the
unit (matches the established finding that asset-day n is inflated).

Usage: .venv/bin/python -m scripts.research_liquidity_orthogonality
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from scripts.research_liquidity_gate import EXP_THR, MOM_LB, START, _col
from scripts.research_trend_gate import (
    ROOT, STEP, asset_class, fwd_return, load_panel,
)

LAG_BD = 3
ROC_4W = 20
H = 21          # forward horizon (repo equity horizon; the headline)
SMA_N = 200     # trivial trend window
VIX_MED_N = 252 # trailing vol-median window


def nl_series(lag: int = LAG_BD) -> pd.Series:
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


def trivial_regimes() -> pd.DataFrame:
    """Daily market-wide trivial regimes, no look-ahead (all trailing)."""
    spy = pd.read_parquet(os.path.join(ROOT, "data/yahoo/SPY.parquet"))["close"].dropna()
    vix = pd.read_parquet(os.path.join(ROOT, "data/yahoo/_VIX.parquet"))["close"].dropna()
    sma = spy.rolling(SMA_N).mean()
    uptrend = (spy > sma)
    vix_med = vix.rolling(VIX_MED_N).median()
    calmvol = (vix <= vix_med)
    out = pd.DataFrame({"uptrend": uptrend, "calmvol": calmvol})
    return out


def base_samples(panel: dict[str, pd.Series], h: int = H) -> pd.DataFrame:
    rows = []
    for name, close in panel.items():
        mom = close.pct_change(MOM_LB)
        fr = fwd_return(close, h)
        wk = np.zeros(len(close), bool); wk[::STEP] = True
        ok = wk & fr.notna() & (mom > 0)
        for dt in close.index[ok]:
            rows.append((name, asset_class(name), dt, float(fr.loc[dt])))
    return pd.DataFrame(rows, columns=["asset", "class", "date", "fwd"])


def _stats(fwd: pd.Series) -> dict:
    if len(fwd) == 0:
        return {}
    return {"n": len(fwd), "hit": round(100 * (fwd > 0).mean(), 1),
            "avg": round(100 * fwd.mean(), 2)}


def _g(label, a, b):
    sa, sb = _stats(a), _stats(b)
    if not sa or not sb:
        print(f"  {label:<34} (thin)"); return (np.nan, np.nan)
    dh = sa["hit"] - sb["hit"]; da = sa["avg"] - sb["avg"]
    print(f"  {label:<34} HI n={sa['n']:>6} hit={sa['hit']:>5}% avg={sa['avg']:>6}%  |  "
          f"LO n={sb['n']:>6} hit={sb['hit']:>5}% avg={sb['avg']:>6}%  |  "
          f"gap hit={dh:+.1f}pp avg={da:+.2f}pp")
    return (dh, da)


def welch(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3 or len(b) < 3:
        return np.nan
    return (a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b))


def honest_welch(s: pd.DataFrame, regcol: str, lab_hi: str, lab_lo: str):
    """Month- and episode-unit Welch t for a binary daily regime in column regcol
    (values must be in {lab_hi, lab_lo, 'neu'/other})."""
    daily = s.groupby("date").agg(fwd=("fwd", "mean"), reg=(regcol, "first"))
    daily["ym"] = daily.index.to_period("M")
    mo = daily.groupby("ym").agg(fwd=("fwd", "mean"),
                                 reg=("reg", lambda x: x.value_counts().idxmax()))
    em, cm = mo["fwd"][mo["reg"] == lab_hi], mo["fwd"][mo["reg"] == lab_lo]
    run = (daily["reg"] != daily["reg"].shift()).cumsum()
    ep = daily.groupby(run).agg(fwd=("fwd", "mean"), reg=("reg", "first"))
    ee, ce = ep["fwd"][ep["reg"] == lab_hi], ep["fwd"][ep["reg"] == lab_lo]
    return (len(em), len(cm), 100 * em.mean(), 100 * cm.mean(), welch(em, cm),
            len(ee), len(ce), 100 * ee.mean(), 100 * ce.mean(), welch(ee, ce))


def main() -> int:
    panel = load_panel()
    s = base_samples(panel, H)
    s = s[s["date"] >= START].copy()

    nl = nl_series(LAG_BD)
    roc4 = nl.diff(ROC_4W)
    triv = trivial_regimes()

    # attach regime labels to each (asset, date) row
    s["roc4"] = s["date"].map(roc4)
    s["uptrend"] = s["date"].map(triv["uptrend"])
    s["calmvol"] = s["date"].map(triv["calmvol"])
    s = s.dropna(subset=["roc4", "uptrend"])
    s["uptrend"] = s["uptrend"].astype(bool)
    s["liq"] = np.where(s["roc4"] >= EXP_THR, "exp",
                        np.where(s["roc4"] <= -EXP_THR, "con", "neu"))

    print(f"\n{'='*100}")
    print(f"ORTHOGONALITY HORSE-RACE  (momentum-long, fwd {H}d, lag {LAG_BD}bd, "
          f"SPY>{SMA_N}dma, VIX<=trailing-{VIX_MED_N}d-median)")
    print(f"sample n={len(s):,}  {s['date'].min().date()}–{s['date'].max().date()}  "
          f"{s['asset'].nunique()} instruments")
    print(f"{'='*100}")

    # ---------- (a) liquidity gap ----------
    print("\n[a] LIQUIDITY gate (expanding vs contracting) on momentum-long")
    la_hit, la_avg = _g("liq EXPANDING vs CONTRACTING",
                        s["fwd"][s["liq"] == "exp"], s["fwd"][s["liq"] == "con"])

    # ---------- (b) trivial regimes, SAME sample ----------
    print("\n[b] TRIVIAL price/vol regimes on the SAME momentum-long sample")
    up_hit, up_avg = _g("SPY>200dma (UP) vs DOWN",
                        s["fwd"][s["uptrend"]], s["fwd"][~s["uptrend"]])
    cv = s.dropna(subset=["calmvol"]).copy()
    cv["calmvol"] = cv["calmvol"].astype(bool)
    cv_hit, cv_avg = _g("VIX calm vs high",
                        cv["fwd"][cv["calmvol"]], cv["fwd"][~cv["calmvol"]])

    # ---------- (d) redundancy: how correlated are the regime labels ----------
    print("\n[d] REGIME REDUNDANCY (daily, are liq-exp and SPY>200dma the same thing?)")
    daily = pd.DataFrame({
        "liq_exp": (roc4 >= EXP_THR),
        "liq_con": (roc4 <= -EXP_THR),
        "uptrend": triv["uptrend"],
        "calmvol": triv["calmvol"],
    }).dropna(subset=["uptrend"])
    daily = daily[daily.index >= START]
    daily = daily.dropna(subset=["liq_exp", "uptrend", "calmvol"])
    for c in ("liq_exp", "liq_con", "uptrend", "calmvol"):
        daily[c] = daily[c].astype(bool)
    phi = daily["liq_exp"].astype(float).corr(daily["uptrend"].astype(float))
    print(f"  phi corr(liq_exp, SPY>200dma)        = {phi:+.3f}")
    print(f"  phi corr(liq_exp, VIX-calm)          = "
          f"{daily['liq_exp'].astype(float).corr(daily['calmvol'].astype(float)):+.3f}")
    print(f"  P(SPY>200dma | liq_exp)              = {daily['uptrend'][daily['liq_exp']].mean():.2%}")
    print(f"  P(SPY>200dma | liq_con)              = {daily['uptrend'][daily['liq_con']].mean():.2%}")
    print(f"  P(liq_exp | SPY>200dma)              = {daily['liq_exp'][daily['uptrend']].mean():.2%}")
    print(f"  P(liq_exp | SPY<200dma)              = {daily['liq_exp'][~daily['uptrend']].mean():.2%}")

    # ---------- (c) DOUBLE-CONDITION ----------
    print("\n[c] DOUBLE-CONDITION: does each regime survive controlling for the other?")
    up = s[s["uptrend"]]
    dn = s[~s["uptrend"]]
    print("  -- WITHIN UPTREND only (SPY>200dma): does liquidity STILL separate? --")
    lu_hit, lu_avg = _g("    liq EXP vs CON | UPTREND",
                        up["fwd"][up["liq"] == "exp"], up["fwd"][up["liq"] == "con"])
    print("  -- WITHIN DOWNTREND only (SPY<200dma): does liquidity STILL separate? --")
    ld_hit, ld_avg = _g("    liq EXP vs CON | DOWNTREND",
                        dn["fwd"][dn["liq"] == "exp"], dn["fwd"][dn["liq"] == "con"])
    print("  -- WITHIN liq-CONTRACTING only: does SPY>200dma STILL separate? --")
    expmask = s["liq"] == "exp"; conmask = s["liq"] == "con"
    tc_hit, tc_avg = _g("    UP vs DOWN | liq CONTRACTING",
                        s["fwd"][conmask & s["uptrend"]], s["fwd"][conmask & ~s["uptrend"]])
    print("  -- WITHIN liq-EXPANDING only: does SPY>200dma STILL separate? --")
    te_hit, te_avg = _g("    UP vs DOWN | liq EXPANDING",
                        s["fwd"][expmask & s["uptrend"]], s["fwd"][expmask & ~s["uptrend"]])

    # ---------- (e) 2x2 cells ----------
    print("\n[e] 2x2 CELLS: mean fwd return (avg%) / hit% / n  by liq x trend")
    print(f"  {'':<14}{'UPTREND':>26}{'DOWNTREND':>26}")
    for liqlab in ("exp", "con"):
        cells = []
        for tr in (True, False):
            d = s["fwd"][(s["liq"] == liqlab) & (s["uptrend"] == tr)]
            st = _stats(d)
            cells.append(f"avg={st.get('avg','-'):>6}% hit={st.get('hit','-'):>5}% n={st.get('n','-'):>5}"
                         if st else "(thin)")
        print(f"  liq {liqlab:<10}{cells[0]:>26}{cells[1]:>26}")

    # ---------- honest-N Welch for each contrast ----------
    print("\n[f] HONEST-N (market-wide regime => month/episode unit) Welch t on avg fwd ret")

    def show(name, tup):
        (nem, ncm, em, cm, tm, nee, nce, ee, ce, te) = tup
        print(f"  {name:<30} MONTH: hi={nem}({em:+.2f}%) lo={ncm}({cm:+.2f}%) t={tm:+.2f}"
              f"   EPISODE: hi={nee}({ee:+.2f}%) lo={nce}({ce:+.2f}%) t={te:+.2f}")

    show("liq exp vs con", honest_welch(s, "liq", "exp", "con"))
    s_up = s.assign(treg=np.where(s["uptrend"], "up", "dn"))
    show("trend up vs dn", honest_welch(s_up, "treg", "up", "dn"))
    s_cv = cv.assign(vreg=np.where(cv["calmvol"], "calm", "hi"))
    show("vol calm vs hi", honest_welch(s_cv, "vreg", "calm", "hi"))
    # liq within uptrend, honest-N
    show("liq exp vs con | UPTREND", honest_welch(up, "liq", "exp", "con"))

    # ---------- VERDICT MATH ----------
    print(f"\n{'='*100}\nVERDICT INPUTS")
    print(f"  (a) liq gap:                 hit {la_hit:+.1f}pp  avg {la_avg:+.2f}pp")
    print(f"  (b) trivial trend gap:       hit {up_hit:+.1f}pp  avg {up_avg:+.2f}pp")
    print(f"  (b) trivial vol gap:         hit {cv_hit:+.1f}pp  avg {cv_avg:+.2f}pp")
    print(f"  (c) liq gap | UPTREND-only:  hit {lu_hit:+.1f}pp  avg {lu_avg:+.2f}pp  <- KEY orthogonality test")
    print(f"  (c) trend gap | liq-CON:     hit {tc_hit:+.1f}pp  avg {tc_avg:+.2f}pp")
    print(f"  redundancy phi(liq,trend) = {phi:+.3f}")
    print(f"{'='*100}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
