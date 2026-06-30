"""China narrative-basket momentum — CONDITIONAL / CONFIRMED variants (Phase 0).

Builds on the established core (THS concept baskets, 5y EW NAV panel). The prior basket
work found: cross-sectional rank-IC ~ 0; the only validated lever is the absolute-trend
gate (drawdown control, no mean edge). This test asks the OWNER'S specific mechanism:

  (a) LOW-BREADTH CONDITIONING — does basket time-series / cross-sectional momentum pay
      MORE when MARKET breadth is low (a downturn), as the owner claims money concentrates
      into a few narrative baskets when the tape is weak?

  (b) BREADTH-CONFIRM FILTER — only ride a basket when its OWN intra-basket member breadth
      (% members above their 200dMA) is ALSO rising/high (money broadening into it), in
      addition to price trend. (Flow tells — 涨停/LHB/moneyflow — are SNAPSHOT-ONLY on disk,
      no usable history; we say so and use the price panel alone for member breadth.)

Honest design — all leak-free, net-of-cost, modern-era split:
  * Panel: EW NAV for the 50 THS concept baskets via engine.baskets._ew_level over
    data/china_search/closes.parquet (PIT dated membership; single-snapshot => survivorship
    in COMPOSITION, far milder on the momentum-ROTATION signal — flagged).
  * Bench: CSI 300 (510300.SS).
  * Market breadth gauge: % of THS-member NAMES above their own 200dMA each day (full-panel,
    NOT the 82-name CSI300 breadth file) — a true A-share-theme-universe breadth read.
  * Member breadth per basket: % of that basket's members above their 200dMA.
  * Rebalance monthly; forward 21d EXCESS over universe-mean (strip market drift) for the
    cross-sectional leg; absolute NAV returns net of cost for the book leg.
  * Cost: 20 bps per side on turnover.

Verdict: does conditioning IMPROVE net Sharpe / drawdown vs unconditional basket momentum?
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import json

from engine.validation import (  # noqa: E402
    block_bootstrap_ci,
    ic_summary,
    paired_delta_ci,
    rank_ic,
)

CLOSES = "data/china_search/closes.parquet"
MEMB = "data/baskets_china_ths/membership.json"
BENCH = "data/china/510300.SS.parquet"
COST_BPS = 20.0  # per side
FWD = 21         # forward holding horizon (1 month)
LB = 252         # 12-1 momentum lookback
SKIP = 21
TOPK = 5


def _ann_sharpe_monthly(x: pd.Series) -> float:
    return float(x.mean() / x.std() * np.sqrt(12)) if x.std() else 0.0


def _maxdd_from_monthly(x: pd.Series) -> float:
    nav = (1.0 + x).cumprod()
    return float((nav / nav.cummax() - 1.0).min())


def build_panel():
    cl = pd.read_parquet(CLOSES).sort_index()
    cl.index = pd.DatetimeIndex(cl.index)
    rets = cl.pct_change()
    memb = json.load(open(MEMB))["baskets"]
    idx = cl.index

    from engine.baskets import _ew_level

    navs = {}
    member_breadth = {}  # % members > 200dMA per basket
    # 200dMA flag per ticker
    ma200 = cl.rolling(200, min_periods=120).mean()
    above = (cl > ma200)
    for bid, bd in memb.items():
        mems = bd["members"]
        lvl = _ew_level(rets, mems, idx)
        if lvl.notna().sum() < 400:
            continue
        navs[bid] = lvl
        present = [m["ticker"] for m in mems if m["ticker"] in cl.columns]
        mb = above[present].mean(axis=1)  # frac of basket members above 200dMA
        member_breadth[bid] = mb
    NAV = pd.DataFrame(navs)
    MB = pd.DataFrame(member_breadth)
    print(f"[panel] {NAV.shape[1]} baskets, {NAV.shape[0]} days "
          f"{NAV.index.min().date()}->{NAV.index.max().date()}")

    # Market breadth gauge: % of ALL THS-member names above 200dMA (theme-universe breadth)
    allmem = sorted({m["ticker"] for bd in memb.values() for m in bd["members"]
                     if m["ticker"] in cl.columns})
    mkt_breadth = above[allmem].mean(axis=1)
    bench = pd.read_parquet(BENCH)["close"].reindex(idx).ffill()
    return NAV, MB, mkt_breadth, bench, cl


def main():
    NAV, MB, mkt_breadth, bench, cl = build_panel()
    idx = NAV.index
    # monthly rebalance dates = last trading day of each month
    mdates = idx.to_series().groupby([idx.year, idx.month]).last().values
    mdates = pd.DatetimeIndex(sorted(mdates))
    mdates = mdates[mdates >= idx.min() + pd.Timedelta(days=LB + 40)]

    # trailing 12-1 momentum + absolute trend gate (NAV > 200dMA) per basket, at each rebal
    navma200 = NAV.rolling(200, min_periods=120).mean()

    rows = []
    ic_pairs = []  # (mom signal vector, fwd excess vector) per date for rank-IC
    book = {"uncond_top": [], "gate_top": [], "lowB_top": [], "highB_top": [],
            "confirm_top": [], "ew_all": []}
    bench_mret = []
    breadth_at = []

    for i in range(len(mdates) - 1):
        t0, t1 = mdates[i], mdates[i + 1]
        if t0 not in idx or t1 not in idx:
            # snap to nearest available
            t0 = idx[idx.get_indexer([t0], method="ffill")[0]]
            t1 = idx[idx.get_indexer([t1], method="ffill")[0]]
        # trailing momentum 12-1 (skip last 21d)
        p_now = NAV.loc[t0]
        loc0 = idx.get_loc(t0)
        if loc0 - LB < 0:
            continue
        p_lb = NAV.iloc[loc0 - LB]
        p_skip = NAV.iloc[loc0 - SKIP]
        mom = (p_skip / p_lb) - 1.0  # 12-1
        # forward 21d basket return (t0 -> t1)
        fwd = (NAV.loc[t1] / NAV.loc[t0]) - 1.0
        valid = mom.notna() & fwd.notna()
        mom, fwd = mom[valid], fwd[valid]
        if len(mom) < 10:
            continue
        # market breadth at decision time
        mb_mkt = float(mkt_breadth.loc[t0])
        breadth_at.append(mb_mkt)
        # gates
        nav_above = (NAV.loc[t0] > navma200.loc[t0]).reindex(mom.index).fillna(False)
        mem_breadth = MB.loc[t0].reindex(mom.index)
        mem_breadth_prev = MB.iloc[max(0, loc0 - 21)].reindex(mom.index)

        # excess fwd (strip universe mean = market drift across baskets)
        fwd_excess = fwd - fwd.mean()
        ic_pairs.append((mom.copy(), fwd_excess.copy(), mb_mkt))

        bench_mret.append(float(bench.loc[t1] / bench.loc[t0] - 1.0))

        # --- books (long-only top-K by momentum, equal weight) ---
        ranked = mom.sort_values(ascending=False)
        topk = ranked.head(TOPK).index
        book["uncond_top"].append(float(fwd[topk].mean()))
        book["ew_all"].append(float(fwd.mean()))

        # gate: top-K among trend-positive
        gpool = ranked[nav_above.reindex(ranked.index).fillna(False)].head(TOPK).index
        book["gate_top"].append(float(fwd[gpool].mean()) if len(gpool) else 0.0)

        # confirm: top-K among trend-positive AND member breadth rising AND breadth>0.5
        confirm_ok = (nav_above.reindex(ranked.index).fillna(False)
                      & (mem_breadth.reindex(ranked.index) > mem_breadth_prev.reindex(ranked.index))
                      & (mem_breadth.reindex(ranked.index) > 0.5))
        cpool = ranked[confirm_ok].head(TOPK).index
        book["confirm_top"].append(float(fwd[cpool].mean()) if len(cpool) else 0.0)

    # ---- breadth-regime conditioning on the cross-section ----
    breadth_arr = np.array([b for _, _, b in ic_pairs])
    med_b = np.median(breadth_arr)
    print(f"\n[breadth] market-breadth (% THS names >200dMA) at rebal: "
          f"min {breadth_arr.min():.2f} med {med_b:.2f} max {breadth_arr.max():.2f}  n={len(breadth_arr)}")

    # rank-IC of momentum -> fwd-excess, overall and split by breadth regime
    ics_all = [rank_ic(m, f) for m, f, _ in ic_pairs]
    ics_low = [rank_ic(m, f) for m, f, b in ic_pairs if b <= med_b]
    ics_high = [rank_ic(m, f) for m, f, b in ic_pairs if b > med_b]

    def _ic_block(name, ics):
        ics = [x for x in ics if np.isfinite(x)]
        s = ic_summary(pd.Series(ics), periods_per_year=12)
        print(f"  {name:14s} mean_IC {s['mean_ic']:+.3f}  t_HAC {s['t_hac']:+.2f}  "
              f"p {s['p_hac']:.3f}  hit {s['hit']:.2f}  n {len(ics)}")
        return s

    print("\n=== CROSS-SECTIONAL rank-IC: 12-1 basket momentum -> fwd-21d EXCESS ===")
    _ic_block("ALL", ics_all)
    _ic_block("LOW breadth", ics_low)
    _ic_block("HIGH breadth", ics_high)

    # ---- monthly book returns vs bench; books in EXCESS over EW-all (market) ----
    bench_mret = pd.Series(bench_mret)
    ew_all = pd.Series(book["ew_all"])
    print("\n=== TOP-5 MOMENTUM BOOK monthly returns (net of cost), EXCESS over EW-all-baskets ===")

    # turnover-based cost: approximate as full TOPK rebalance each month worst case.
    # We compute net by subtracting 2*COST*avg_turnover; use conservative 60% turnover/mo.
    def net_excess(series_key):
        raw = pd.Series(book[series_key])
        ex = raw - ew_all  # strip the all-basket market drift
        # cost: top-5 long-only, ~60% names turn over monthly => 0.6*2*20bps = 24bps/mo
        cost = 0.60 * 2 * (COST_BPS / 1e4)
        return ex - cost

    results = {}
    for key, label in [("uncond_top", "uncond top5"),
                       ("gate_top", "trend-gate top5"),
                       ("confirm_top", "breadth-CONFIRM top5")]:
        nx = net_excess(key)
        sh = _ann_sharpe_monthly(nx)
        dd = _maxdd_from_monthly(nx)
        mean_mo = nx.mean()
        results[key] = nx
        print(f"  {label:22s} mean {mean_mo*100:+.2f}%/mo  Sharpe {sh:+.2f}  "
              f"maxDD {dd*100:+.1f}%  n {len(nx)}")

    # ---- breadth-conditioned book: top5 momentum, split low vs high market breadth ----
    print("\n=== OWNER'S CLAIM: does top-5 momentum pay MORE in LOW-breadth months? ===")
    uncond = pd.Series(book["uncond_top"]) - ew_all
    b_at = pd.Series(breadth_at[:len(uncond)])
    med2 = b_at.median()
    low = uncond[b_at <= med2]
    high = uncond[b_at > med2]
    print(f"  LOW-breadth months  (b<={med2:.2f}, n={len(low)}): "
          f"mean {low.mean()*100:+.2f}%/mo  Sharpe {_ann_sharpe_monthly(low):+.2f}")
    print(f"  HIGH-breadth months (b> {med2:.2f}, n={len(high)}): "
          f"mean {high.mean()*100:+.2f}%/mo  Sharpe {_ann_sharpe_monthly(high):+.2f}")
    diff = low.mean() - high.mean()
    # simple t on diff of means
    from scipy.stats import ttest_ind
    tt = ttest_ind(low.dropna(), high.dropna(), equal_var=False)
    print(f"  LOW - HIGH mean diff {diff*100:+.2f}%/mo  Welch t {tt.statistic:+.2f}  p {tt.pvalue:.3f}")

    # ---- DECISIVE: paired delta Sharpe, confirm/gate vs uncond (on the net-excess monthly book) ----
    print("\n=== PAIRED bootstrap: does conditioning BEAT unconditional top-5 (net)? ===")
    for key, label in [("gate_top", "trend-gate"), ("confirm_top", "breadth-CONFIRM")]:
        pd_ci = paired_delta_ci(results[key], results["uncond_top"], block=6, B=4000, ann=12)
        if pd_ci:
            print(f"  {label:18s} vs uncond  Δsharpe CI {pd_ci['delta_sharpe_ci']}  "
                  f"sharpe_better={pd_ci['sharpe_better']}")
        else:
            print(f"  {label:18s} insufficient n for paired CI")

    # ---- modern-era split (second half) sanity ----
    print("\n=== MODERN-ERA SPLIT (2nd half of window) ===")
    half = len(uncond) // 2
    for key, label in [("uncond_top", "uncond"), ("gate_top", "gate"), ("confirm_top", "confirm")]:
        nx = results[key] if key in results else net_excess(key)
        h2 = nx.iloc[half:]
        print(f"  {label:10s} 2nd-half  mean {h2.mean()*100:+.2f}%/mo  Sharpe {_ann_sharpe_monthly(h2):+.2f}  n {len(h2)}")

    print("\n[flow-confirm note] 涨停/LHB/moneyflow_sector are SNAPSHOT-ONLY on disk "
          "(1 date / ~2wk lossy); NO backtestable history. Member breadth (%>200dMA) from "
          "the price panel is the only confirm filter with usable history — used above.")


if __name__ == "__main__":
    main()
