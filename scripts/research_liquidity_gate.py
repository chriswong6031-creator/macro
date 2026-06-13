"""RESEARCH PROTOTYPE — does the macro net-liquidity regime sharpen signals?

Tier-1 #3 from the roadmap, and the one the repo's own evidence most supports:
macro_score / liquidity is the only strongly-CONFIRMED factor (BTC macro_score
+48.8%/76% hit; playbook liquidity +1.3-2%/21d at 72-74%). Question: does
conditioning a cross-asset momentum-long signal on the US net-liquidity regime
improve forward accuracy, and does it survive the traps that fool naive tests?

Net liquidity = WALCL/1000 - RRP - TGA/1000 ($bn), the engine's D10 construction.

ANTI-LOOK-AHEAD: WALCL is weekly (Wed) released Thu; RRP/TGA are daily, lagged.
We forward-fill last-known values AND lag the whole series LAG_BD business days, so
every regime read uses only data a trader actually had.

ANTI-SINGLE-EPISODE: the 2020-21 QE blast coincided with the biggest risk rally, so
"liquidity up -> returns up" can be ONE episode cosplaying as an edge. We therefore
report: full sample, split-half, **2020-21 EXCLUDED**, per sub-period, and the count
of distinct regime EPISODES (runs) = the honest effective sample size (a single macro
series gives far fewer independent obs than asset-days suggest).

Judges BOTH forward return (hit/avg) and forward drawdown (D43 lens). Horizons 21d+63d.
NOT wired into engine/UI — prints a verdict to be measured first.

Usage: .venv/bin/python -m scripts.research_liquidity_gate
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from scripts.research_trend_gate import (
    ROOT, STEP, asset_class, fwd_drawdown, fwd_return, load_panel,
)

MOM_LB = 126
LAG_BD = 3            # business-day lag on the liquidity series (release delay + safety)
ROC_4W = 20          # ~4 trading weeks
ROC_13W = 65         # ~1 quarter
EXP_THR = 25.0       # $bn 4w change -> expanding/contracting (config threshold)
START = "2010-01-01"  # net-liq meaningfully available (WALCL+RRP era)


def _col(df: pd.DataFrame) -> pd.Series:
    return df.iloc[:, 0]


def net_liquidity() -> pd.Series:
    """Reconstruct net_liquidity_bn (engine D10), forward-filled and LAGGED."""
    d = os.path.join(ROOT, "data")
    walcl = _col(pd.read_parquet(f"{d}/fred/WALCL.parquet")) / 1000.0      # $mn -> $bn
    rrp_fred = _col(pd.read_parquet(f"{d}/fred/RRPONTSYD.parquet"))        # $bn
    rrp_ny = pd.read_parquet(f"{d}/nyfed/rrp.parquet")["rrp_bn"]
    tga = pd.read_parquet(f"{d}/treasury/tga.parquet")["tga_mn"] / 1000.0  # $mn -> $bn

    idx = pd.bdate_range(START, pd.Timestamp.utcnow().tz_localize(None).normalize())
    walcl_bn = walcl.reindex(walcl.index.union(idx)).ffill(limit=7).reindex(idx)
    rrp_bn = rrp_ny.combine_first(rrp_fred)
    rrp_bn = rrp_bn.reindex(rrp_bn.index.union(idx)).ffill(limit=5).reindex(idx).fillna(0)
    tga_bn = tga.reindex(tga.index.union(idx)).ffill(limit=5).reindex(idx)
    nl = (walcl_bn - rrp_bn - tga_bn).dropna()
    return nl.shift(LAG_BD)   # anti-look-ahead lag


def collect(panel: dict[str, pd.Series], nl: pd.Series) -> pd.DataFrame:
    roc4 = nl.diff(ROC_4W)
    roc13 = nl.diff(ROC_13W)
    rows = []
    for name, close in panel.items():
        mom = close.pct_change(MOM_LB)
        for h in (21, 63):
            fr = fwd_return(close, h)
            fdd = fwd_drawdown(close, h)
            weekly = np.zeros(len(close), dtype=bool)
            weekly[::STEP] = True
            ok = weekly & fr.notna()
            sub = close.index[ok]
            sub = sub[sub.isin(roc4.index)]
            for dt in sub:
                r4 = roc4.get(dt, np.nan)
                if pd.isna(r4):
                    continue
                rows.append((name, asset_class(name), dt, h,
                             bool(mom.get(dt, np.nan) > 0),
                             float(r4), float(roc13.get(dt, np.nan)),
                             float(fr.loc[dt]), float(fdd.loc[dt])))
    return pd.DataFrame(rows, columns=["asset", "class", "date", "h", "mom_long",
                                       "roc4", "roc13", "fwd", "fdd"])


def _stats(d: pd.DataFrame) -> dict:
    if len(d) == 0:
        return {}
    return {"n": len(d), "hit": round(100 * (d["fwd"] > 0).mean(), 1),
            "avg": round(100 * d["fwd"].mean(), 2),
            "dd_med": round(100 * d["fdd"].median(), 2),
            "dd_p10": round(100 * d["fdd"].quantile(0.10), 2)}


def _line(label: str, s: dict) -> str:
    if not s:
        return f"  {label:<28} (no samples)"
    return (f"  {label:<28} n={s['n']:>6}  hit={s['hit']:>5}%  avg={s['avg']:>6}%"
            f"  bad.dip={s['dd_p10']:>7}%")


def _episodes(nl: pd.Series) -> int:
    """Distinct expanding/contracting episodes (runs) = honest effective N."""
    roc4 = nl.diff(ROC_4W)
    cat = pd.cut(roc4, [-1e9, -EXP_THR, EXP_THR, 1e9], labels=["con", "neu", "exp"])
    cat = cat.dropna()
    return int((cat != cat.shift()).sum())


def report(df: pd.DataFrame, nl: pd.Series, h: int) -> None:
    d = df[df["h"] == h].copy()
    print(f"\n{'='*82}\nNET-LIQUIDITY GATE  (fwd {h}d)   episodes(eff.N)~{_episodes(nl)} "
          f"over {d['date'].min().date()}–{d['date'].max().date()}\n{'='*82}")

    d["q4"] = pd.qcut(d["roc4"], 4, labels=["Q1 drain", "Q2", "Q3", "Q4 flood"])
    print("[1] net-liq 4w-RoC quartile -> forward return (ALL weekly samples)")
    for q in ["Q1 drain", "Q2", "Q3", "Q4 flood"]:
        print(_line(str(q), _stats(d[d["q4"] == q])))

    ml = d[d["mom_long"]]
    print("\n[2] As a GATE on momentum-long: expanding vs contracting")
    exp = ml[ml["roc4"] >= EXP_THR]
    con = ml[ml["roc4"] <= -EXP_THR]
    print(_line("momentum-long ALL", _stats(ml)))
    print(_line("  & liq EXPANDING", _stats(exp)))
    print(_line("  & liq CONTRACTING", _stats(con)))

    print("\n[3] Split-half robustness (momentum-long, exp vs con)")
    mid = d["date"].quantile(0.5)
    for lab, m in (("pre " + str(mid.date()), ml["date"] < mid),
                   ("post " + str(mid.date()), ml["date"] >= mid)):
        h2 = ml[m]
        print(f"  -- {lab} (n={len(h2)}) --")
        print(_line("    exp", _stats(h2[h2["roc4"] >= EXP_THR])))
        print(_line("    con", _stats(h2[h2["roc4"] <= -EXP_THR])))

    print("\n[4] *** 2020-2021 QE EXCLUDED *** (the single-episode artifact test)")
    keep = ~ml["date"].between("2020-03-01", "2021-12-31")
    mlx = ml[keep]
    print(_line("momentum-long (ex 20-21)", _stats(mlx)))
    print(_line("  & liq EXPANDING", _stats(mlx[mlx["roc4"] >= EXP_THR])))
    print(_line("  & liq CONTRACTING", _stats(mlx[mlx["roc4"] <= -EXP_THR])))

    print("\n[5] Per sub-period (exposes single-episode dependence; momentum-long)")
    for lo, hi, lab in [("2010", "2015", "2010-14"), ("2015", "2020", "2015-19"),
                        ("2020", "2022", "2020-21 QE"), ("2022", "2027", "2022-26")]:
        p = ml[(ml["date"] >= lo) & (ml["date"] < hi)]
        if len(p) < 80:
            print(f"  {lab}: thin ({len(p)})"); continue
        e, c = p[p["roc4"] >= EXP_THR], p[p["roc4"] <= -EXP_THR]
        print(f"  {lab:10} exp {_stats(e).get('hit','-')}%/{_stats(e).get('avg','-')}%"
              f"  con {_stats(c).get('hit','-')}%/{_stats(c).get('avg','-')}%  (n_exp={len(e)},n_con={len(c)})")

    print("\n[6] By asset class (momentum-long, exp vs con)")
    for cls in ["equity", "crypto", "commodity"]:
        p = ml[ml["class"] == cls]
        if len(p) < 80:
            print(f"  {cls}: thin ({len(p)})"); continue
        print(f"  -- {cls} --")
        print(_line("    exp", _stats(p[p["roc4"] >= EXP_THR])))
        print(_line("    con", _stats(p[p["roc4"] <= -EXP_THR])))


if __name__ == "__main__":
    nl = net_liquidity()
    print(f"net-liquidity series: {nl.dropna().index.min().date()}–{nl.dropna().index.max().date()}"
          f"  (lagged {LAG_BD}bd)  last={nl.dropna().iloc[-1]:.0f}bn")
    panel = load_panel()
    df = collect(panel, nl)
    for h in (21, 63):
        report(df, nl, h)
    print("\nNOTE: a single macro series => effective N ≈ #episodes, NOT #asset-days. "
          "Weight the sub-period + ex-QE rows over the headline n.")
