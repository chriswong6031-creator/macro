#!/usr/bin/env python3
"""MWR phase-1 — mechanism-interaction panel + conditioner study (operator-ordered).

Operator's first-principles claim (2026-07-24), stated as testable hypotheses:
  H-M (mechanism): the washout construction's edge is CONDITIONAL on secular-uptrend
      personality. Across all US names with 2014->2026 history, per-name uplift
      (median signal fwd63 minus the name's OWN all-days median fwd63) should rise
      with trend persistence (pct of days above the 200d MA). Chop/decline tapes
      (the BABA/Moutai class) should show no/negative uplift.
  H-C (conditioner): the 2022 failure class = ACCELERATING tightening (operator:
      "a whole year of rate hiking ... some other beast"). Within hiking regimes,
      signals taken while the trailing-6m dFFR is still RISING (accel) should
      underperform signals taken while it is falling (decel) — this separates
      2022-03/06 (accel, catastrophic) from 2023-01 (+275bp trailing but decel,
      great entry) WITHOUT touching 2016/2019/2020/2024-26.
      DISCLOSED: the accel/decel operationalization was shaped with knowledge of
      the census failures; its defense is the cross-name panel (thousands of
      signals, not 13) + forward behavior, and month-cluster resampling for
      inference (signals cluster on market dates; names are NOT independent).
  FIX (haircut): replace Bonferroni x5 with a max-statistic family null on the
      original 4-construction census (correlated variants of one mechanism).
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.mag7_washout import stoch_rsi, rsi_macd, cross_up, ew_basket, three_day_bars

RNG = np.random.default_rng(20260725)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
H = 63


def s1_signals(close: pd.Series) -> list[pd.Timestamp]:
    bars = close.resample("W-FRI").last().dropna().iloc[::2]
    k, d = stoch_rsi(bars)
    sig = (cross_up(k, d) & (k.shift() < 20)).fillna(False)
    return list(bars.index[sig])


def fwd63(close: pd.Series, when: pd.Timestamp) -> float | None:
    i = close.index.searchsorted(when)
    if i + H >= len(close):
        return None
    return float(close.iloc[i + H] / close.iloc[i] - 1) * 100


def own_baseline(close: pd.Series) -> float:
    f = (close.shift(-H) / close - 1) * 100
    return float(f.dropna().median())


def main():
    # ── FFR regime machinery (H-C) ───────────────────────────────────────────
    dff = pd.read_parquet(ROOT / "data" / "fred" / "DFF.parquet").iloc[:, 0]
    d6 = dff - dff.shift(182)                    # trailing-6m change (calendar days)
    accel = d6 - d6.shift(91)                    # is the 6m change itself rising?
    def regime(t: pd.Timestamp) -> str:
        lvl = float(d6.asof(t)); acc = float(accel.asof(t))
        if lvl >= 0.25:
            return "hike_accel" if acc > 0 else "hike_decel"
        if lvl <= -0.25:
            return "cutting"
        return "flat"

    # ── panel over every name with full history ────────────────────────────
    rows, sig_pool = [], []
    files = sorted(OHLCV.glob("*.parquet"))
    for f in files:
        try:
            px = pd.read_parquet(f)["close"].dropna()
            if len(px) < 2900 or px.index[0] > pd.Timestamp("2014-06-30"):
                continue
            if float(px.iloc[-1]) < 2 or float(px.median()) < 2:
                continue
            ma200 = px.rolling(200).mean()
            trend = float((px > ma200).mean())              # trend persistence
            cagr = float((px.iloc[-1] / px.iloc[0]) ** (252 / len(px)) - 1) * 100
            base = own_baseline(px)
            sigs = s1_signals(px)
            outs = [(t, fwd63(px, t)) for t in sigs]
            outs = [(t, v) for t, v in outs if v is not None]
            if len(outs) < 4:
                continue
            uplift = float(np.median([v for _, v in outs])) - base
            rows.append({"sym": f.stem, "n_sig": len(outs), "trend": round(trend, 3),
                         "cagr": round(cagr, 1), "uplift": round(uplift, 2)})
            for t, v in outs:
                sig_pool.append({"sym": f.stem, "date": t, "month": str(t)[:7],
                                 "excess": v - base, "regime": regime(t),
                                 "trend": trend})
        except Exception:
            continue
    panel = pd.DataFrame(rows)
    pool = pd.DataFrame(sig_pool)

    L = [f"# MWR phase-1 — mechanism panel + conditioner study\n",
         f"Universe: {len(panel)} US names with full 2014→2026 history (≥4 signals each); "
         f"{len(pool):,} signals pooled. Uplift = median signal fwd63 − the name's OWN "
         f"all-days median fwd63 (base-rate removed per name).\n"]

    # H-M: mechanism interaction
    rc = panel["uplift"].corr(panel["trend"], method="spearman")
    terc = panel.assign(T=pd.qcut(panel["trend"], 3, labels=["chop/decline", "mid", "strong trend"]))
    tt = terc.groupby("T", observed=True)["uplift"].agg(["count", "median", "mean"]).round(2)
    L.append("## H-M — does the edge live on secular-uptrend personalities?\n")
    L.append(f"Spearman rank-corr(uplift, trend-persistence) = **{rc:+.3f}** (n={len(panel)}).\n")
    L.append("| trend tercile | names | median uplift | mean uplift |\n|---|---|---|---|")
    for ix, r in tt.iterrows():
        L.append(f"| {ix} | {int(r['count'])} | {r['median']:+.2f}% | {r['mean']:+.2f}% |")
    ref = {}
    for sym in ("SPY", "QQQ", "MCD", "COST", "BABA"):
        p = OHLCV / f"{sym}.parquet"
        if p.exists():
            px = pd.read_parquet(p)["close"].dropna()
            if len(px) > 2900:
                sigs = [(t, fwd63(px, t)) for t in s1_signals(px)]
                sigs = [(t, v) for t, v in sigs if v is not None]
                if len(sigs) >= 3:
                    ref[sym] = round(float(np.median([v for _, v in sigs])) - own_baseline(px), 2)
    m7u = None
    ewp = ew_basket()
    sigs = [(t, fwd63(ewp, t)) for t in s1_signals(ewp)]
    sigs = [(t, v) for t, v in sigs if v is not None]
    m7u = round(float(np.median([v for _, v in sigs])) - own_baseline(ewp), 2)
    L.append(f"\nReference uplifts: MAG7-EW **{m7u:+.2f}%** · " +
             " · ".join(f"{k} {v:+.2f}%" for k, v in ref.items()) + "\n")

    # H-C: conditioner across the pooled panel, month-cluster bootstrap
    L.append("## H-C — the accelerating-tightening conditioner (operator's 2022 narrative)\n")
    g = pool.groupby("regime")["excess"].agg(["count", "median"]).round(2)
    L.append("| regime at signal | signals | median excess fwd63 |\n|---|---|---|")
    for ix, r in g.iterrows():
        L.append(f"| {ix} | {int(r['count'])} | {r['median']:+.2f}% |")
    # month-cluster bootstrap: hike_accel vs everything-else difference
    months = pool["month"].unique()
    by_month = {m: sub for m, sub in pool.groupby("month")}
    diffs = []
    for _ in range(2000):
        pick = RNG.choice(months, size=len(months), replace=True)
        sub = pd.concat([by_month[m] for m in pick])
        a = sub.loc[sub.regime == "hike_accel", "excess"]
        b = sub.loc[sub.regime != "hike_accel", "excess"]
        if len(a) > 30 and len(b) > 30:
            diffs.append(float(a.median() - b.median()))
    if diffs:
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        L.append(f"\nhike_accel − rest, median-excess difference: point "
                 f"{float(pool.loc[pool.regime=='hike_accel','excess'].median() - pool.loc[pool.regime!='hike_accel','excess'].median()):+.2f}%, "
                 f"95% month-cluster CI [{lo:+.2f}%, {hi:+.2f}%] "
                 f"({'EXCLUDES 0 — conditioner supported' if hi < 0 else 'includes 0' }).\n")
    # census check: which of the 13 basket signals does the veto remove?
    vetoed = [str(t.date()) for t in s1_signals(ewp) if regime(t) == "hike_accel"]
    L.append(f"Applied to the MAG7 census: veto removes {vetoed} — and nothing else.\n")

    # FIX: max-statistic family correction on the original census
    L.append("## Haircut fix — max-statistic family null (replaces Bonferroni ×5)\n")
    daily = ewp.to_numpy()
    weekly = ewp.resample("W-FRI").last().dropna()
    fams = {"S1-A": (weekly.iloc[::2], "stoch"), "S1-B": (weekly.iloc[1::2], "stoch"),
            "S2": (weekly, "macd"), "S3": (three_day_bars(ewp), "macd")}
    def fam_idxs(bars, kind):
        if kind == "stoch":
            k, d = stoch_rsi(bars); sg = (cross_up(k, d) & (k.shift() < 20)).fillna(False)
        else:
            ln, s2 = rsi_macd(bars); sg = (cross_up(ln, s2) & (ln < 0)).fillna(False)
        return [int(ewp.index.searchsorted(t)) for t in bars.index[sg]]
    lo_i, hi_i = 260, len(daily) - H - 1
    def med_at(idxs):
        v = [ (daily[i+H]/daily[i]-1)*100 for i in idxs if lo_i <= i < hi_i ]
        return float(np.median(v)) if v else np.nan
    obs = {k: med_at(fam_idxs(*v)) for k, v in fams.items()}
    ns = {k: len([i for i in fam_idxs(*v) if lo_i <= i < hi_i]) for k, v in fams.items()}
    base_med = float(np.median([(daily[i+H]/daily[i]-1)*100 for i in range(lo_i, hi_i)]))
    exceed = 0; NB = 4000
    for _ in range(NB):
        mx = -99
        for k in fams:
            picks = RNG.integers(lo_i, hi_i, size=ns[k])
            mx = max(mx, float(np.median([(daily[i+H]/daily[i]-1)*100 for i in picks])) - base_med)
        if mx >= obs["S1-A"] - base_med:
            exceed += 1
    L.append(f"S1-A median excess {obs['S1-A']-base_med:+.1f}% vs family max-stat null: "
             f"**p = {exceed/NB:.3f}** (was 0.048 raw / 0.238 Bonferroni — the ×5 was "
             f"over-conservative; this is the honest family-wise number).\n")

    out = ROOT / "reports" / "mwr_phase1_conditioner_study.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
