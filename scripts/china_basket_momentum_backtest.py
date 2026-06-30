"""China THEME/NARRATIVE-BASKET MOMENTUM — Phase 0 core.

Hypothesis (owner): in A-share downturns money concentrates into a FEW narrative
baskets (AI-buildout: CPO/算力/液冷/PCB/固态电池) and the BASKET trends even as its
single names rotate. This tests the simplest tradeable form of that intuition:

  "Can we ride the PREVAILING narrative basket?" — each rebalance, rank the 50 THS
  concept baskets by trailing return over lookbacks {5,10,21,63}d; LONG the top-k
  (k=1,2,3) EW; hold {5,10,21}d. Benchmark = EW-all-50-baskets (held the same h).

This is TIME-SERIES rotation across baskets, NOT the dead single-name cross-section
(research/ALLOCATION_CHINA_AUDIT.md killed cross-sectional rank-IC rotation) and NOT
the dead single-name reversal (reports/china-reversal-gated.md #754). It is the
owner's actual, un-tested mechanism.

Substrate (basket_data_feasibility recipe):
  - Membership: data/baskets_china_ths/membership.json — 50 baskets / 731 members,
    point-in-time dated (engine.baskets._ew_level honours [added, removed)).
  - Prices:    data/china_search/closes.parquet — 1492 adj-close tickers,
    2021-06-15 → 2026-06-26 (1220 trading days, ~5y).
  - Benchmark: data/china/510300.SS.parquet (CSI 300) for an absolute anchor.

DATA-WINDOW CAVEAT (load-bearing): the prompt asked for full / 2015+ / 2021+ era
splits, but NO China price history before 2021-06-15 exists in the repo
(closes_deep.parquet is absent; closes.parquet starts 2021). So "full" == "2021+";
we additionally split 2023+ (post-2022-bear recent regime) and report BOTH.
MEMBERSHIP is also a single 2026-06-27 snapshot back-applied => SURVIVORSHIP-BIASED
at the member level (today's basket constituents applied historically). Basket-level
TIME-SERIES rotation is far more robust to this than single-name selection, but it
still inflates absolute levels; the EW-all-baskets benchmark cancels MOST of it
because both the book and the bench draw from the same survivorship-biased universe.

Rigor: leak-free (signal trailing return as-of day d; forward return d->d+h, no
overlap with the signal window), net-of-cost (10/20 bps one-way on basket turnover),
rank-IC of trailing-basket-mom -> fwd-basket-return with Newey-West HAC-t
(engine.validation.rank_ic / ic_summary), annualized Sharpe of the long-k vs the
EW-all benchmark, BH-FDR across the lookback panel. Writes a real printed table.
"""
from __future__ import annotations

import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.baskets import _ew_level                       # noqa: E402
from engine.validation import (                            # noqa: E402
    rank_ic, ic_summary, benjamini_hochberg, block_bootstrap_ci)

ROOT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
CLOSES = ROOT / "data/china_search/closes.parquet"
MEMBERSHIP = ROOT / "data/baskets_china_ths/membership.json"
BENCH = ROOT / "data/china/510300.SS.parquet"

LOOKBACKS = [5, 10, 21, 63]
HOLDS = [5, 10, 21]
KS = [1, 2, 3]
COSTS_BPS = [10.0, 20.0]                                   # one-way, charged on basket turnover
ERAS = {                                                   # (label, start) — full==2021 (no deeper data)
    "full(2021+)": "2021-06-15",
    "2023+":       "2023-01-01",
    "2024+":       "2024-01-01",
}


# --------------------------------------------------------------------------- #
# build the 50-basket daily LEVEL panel (point-in-time membership)
# --------------------------------------------------------------------------- #
def build_basket_panel() -> tuple[pd.DataFrame, pd.Series]:
    closes = pd.read_parquet(CLOSES).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    closes.index = pd.DatetimeIndex(closes.index)
    rets = closes.pct_change(fill_method=None)
    idx = closes.index

    mem = json.load(open(MEMBERSHIP))["baskets"]
    levels = {}
    for bid, b in mem.items():
        lvl = _ew_level(rets, b["members"], idx)
        if lvl.notna().sum() > 252:                        # need >=1y of series
            levels[bid] = lvl
    panel = pd.DataFrame(levels)

    bench = pd.read_parquet(BENCH).sort_index()["close"].reindex(idx).ffill()
    return panel, bench


# --------------------------------------------------------------------------- #
# leak-free rotation backtest
# --------------------------------------------------------------------------- #
def _ann_sharpe(x: pd.Series, ppy: int) -> float:
    x = x.dropna()
    sd = x.std(ddof=1)
    return float(x.mean() / sd * np.sqrt(ppy)) if sd and len(x) > 2 else float("nan")


def _maxdd(x: pd.Series) -> float:
    cum = (1 + x.fillna(0)).cumprod()
    return float((cum / cum.cummax() - 1).min())


def rotation_backtest(panel: pd.DataFrame, lb: int, hold: int, k: int,
                      start: str, cost_bps: float) -> dict:
    """Non-overlapping rebalance every `hold` days. At each rebalance day d:
    signal = trailing `lb`-day basket return measured to d (close-to-close, fully
    realized, no peek). Hold the top-k EW for the next `hold` days; the realized
    basket return d->d+hold is the forward payoff. Benchmark = EW of ALL baskets
    over the SAME forward window. Cost charged on book turnover between consecutive
    rebalances (names that rotate out/in pay cost_bps one-way each).
    """
    lvl = panel.loc[start:]
    idx = lvl.index
    # rebalance grid: every `hold` bars, leaving room for trailing lb and forward hold
    starts = list(range(lb, len(idx) - hold, hold))
    if len(starts) < 8:
        return {"n": len(starts), "error": "too few rebalances"}

    ppy = 252.0 / hold
    book_rets, bench_rets, ics = [], [], []
    prev_set: set = set()
    turns = []
    for si in starts:
        d = idx[si]
        d_fwd = idx[si + hold]
        # trailing lb-day return as-of d (signal) — uses ONLY data up to d
        trail = lvl.iloc[si] / lvl.iloc[si - lb] - 1.0
        trail = trail.dropna()
        # forward return d -> d+hold (payoff) — disjoint from the signal window
        fwd = (lvl.iloc[si + hold] / lvl.iloc[si] - 1.0)
        fwd = fwd.reindex(trail.index).dropna()
        trail = trail.reindex(fwd.index)
        if len(trail) < 10:
            continue
        ics.append(rank_ic(trail, fwd))
        sel = list(trail.sort_values(ascending=False).head(k).index)
        gross = float(fwd.reindex(sel).mean())
        cur_set = set(sel)
        # turnover: fraction of the k-name book that changed (one-way), each at cost_bps
        changed = len(cur_set ^ prev_set) / (2.0 * k) if prev_set else 1.0
        cost = changed * (cost_bps / 1e4) * 2.0            # both legs of each swap
        turns.append(changed)
        book_rets.append(gross - cost)
        bench_rets.append(float(fwd.mean()))               # EW-all-baskets, same fwd window
        prev_set = cur_set

    book = pd.Series(book_rets)
    bench = pd.Series(bench_rets)
    if len(book) < 8:
        return {"n": len(book), "error": "too few periods"}
    exc = book - bench
    icsum = ic_summary([c for c in ics if c == c], periods_per_year=int(round(ppy)))
    return {
        "n": int(len(book)),
        "book_mean_pct": round(float(book.mean()) * 100, 3),
        "bench_mean_pct": round(float(bench.mean()) * 100, 3),
        "exc_mean_pct": round(float(exc.mean()) * 100, 3),
        "book_sharpe": round(_ann_sharpe(book, ppy), 2),
        "bench_sharpe": round(_ann_sharpe(bench, ppy), 2),
        "exc_sharpe": round(_ann_sharpe(exc, ppy), 2),
        "book_maxdd_pct": round(_maxdd(book) * 100, 1),
        "exc_hit": round(float((exc > 0).mean()), 3),
        "ic_mean": icsum.get("mean_ic"),
        "ic_t_hac": icsum.get("t_hac"),
        "ic_p_hac": icsum.get("p_hac"),
        "ic_hit": icsum.get("hit"),
        "mean_turnover": round(float(np.mean(turns)), 3),
    }


def main() -> int:
    print("[load] building 50-basket point-in-time level panel …")
    panel, bench = build_basket_panel()
    print(f"[load] panel {panel.shape[1]} baskets x {panel.shape[0]} days, "
          f"{panel.index.min().date()} -> {panel.index.max().date()}")

    rows = []          # full grid for the table
    pvals = {}         # for BH-FDR over the IC panel (one p per lb x hold x era, k pooled)
    for era_lbl, start in ERAS.items():
        for lb in LOOKBACKS:
            for hold in HOLDS:
                for k in KS:
                    for cost in COSTS_BPS:
                        r = rotation_backtest(panel, lb, hold, k, start, cost)
                        r.update(era=era_lbl, lb=lb, hold=hold, k=k, cost=cost)
                        rows.append(r)
                # FDR key: IC is k-invariant; record once per (era,lb,hold) at k=1,cost=10
                base = next((x for x in rows if x.get("era") == era_lbl and x.get("lb") == lb
                             and x.get("hold") == hold and x.get("k") == 1
                             and x.get("cost") == 10.0 and not x.get("error")), None)
                if base and base.get("ic_p_hac") is not None:
                    pvals[f"{era_lbl}|lb{lb}|h{hold}"] = base["ic_p_hac"]

    bh = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    # block-bootstrap CI on the single best net config (full era, by exc_sharpe)
    best = max((r for r in rows if r.get("era") == "full(2021+)" and not r.get("error")
                and r.get("cost") == 20.0),
               key=lambda r: (r.get("exc_sharpe") or -9), default=None)
    boot = {}
    if best:
        # rebuild the best book's excess series for bootstrap
        boot = _bootstrap_best(panel, best)

    print_table(rows, bh, best, boot, panel)
    return 0


def _bootstrap_best(panel, best):
    lb, hold, k = best["lb"], best["hold"], best["k"]
    start = "2021-06-15"
    lvl = panel.loc[start:]
    idx = lvl.index
    starts = list(range(lb, len(idx) - hold, hold))
    exc = []
    prev_set: set = set()
    for si in starts:
        trail = (lvl.iloc[si] / lvl.iloc[si - lb] - 1.0).dropna()
        fwd = (lvl.iloc[si + hold] / lvl.iloc[si] - 1.0).reindex(trail.index).dropna()
        trail = trail.reindex(fwd.index)
        if len(trail) < 10:
            continue
        sel = list(trail.sort_values(ascending=False).head(k).index)
        gross = float(fwd.reindex(sel).mean())
        changed = len(set(sel) ^ prev_set) / (2.0 * k) if prev_set else 1.0
        cost = changed * (best["cost"] / 1e4) * 2.0
        exc.append((gross - cost) - float(fwd.mean()))
        prev_set = set(sel)
    ppy = int(round(252.0 / hold))
    return block_bootstrap_ci(pd.Series(exc), block=max(3, ppy // 4), B=4000, ann=ppy)


def print_table(rows, bh, best, boot, panel):
    P = print
    P("\n" + "=" * 96)
    P("CHINA THEME-BASKET MOMENTUM — can we ride the PREVAILING narrative basket?")
    P(f"50 THS concept baskets, EW point-in-time membership, {panel.index.min().date()} -> "
      f"{panel.index.max().date()} (~5y; NO deeper China price data exists).")
    P("Long top-k by trailing-lb return vs EW-ALL-50 benchmark. Leak-free, net of cost (bps one-way).")
    P("=" * 96)

    for era in ERAS:
        P(f"\n### ERA {era}")
        P(f"{'lb':>3} {'h':>3} {'k':>2} {'cost':>5} | "
          f"{'bookμ%':>7} {'benchμ%':>8} {'excμ%':>7} | "
          f"{'bookSh':>6} {'excSh':>6} {'bookDD%':>8} {'excHit':>6} | "
          f"{'IC':>6} {'IC_t':>6} {'IC_p':>6} {'turn':>5}")
        P("-" * 96)
        for r in rows:
            if r.get("era") != era or r.get("error"):
                continue
            P(f"{r['lb']:>3} {r['hold']:>3} {r['k']:>2} {int(r['cost']):>4}b | "
              f"{r['book_mean_pct']:>7} {r['bench_mean_pct']:>8} {r['exc_mean_pct']:>7} | "
              f"{r['book_sharpe']:>6} {r['exc_sharpe']:>6} {r['book_maxdd_pct']:>8} {r['exc_hit']:>6} | "
              f"{str(r['ic_mean']):>6} {str(r['ic_t_hac']):>6} {str(r['ic_p_hac']):>6} "
              f"{r['mean_turnover']:>5}")

    P("\n### Rank-IC (trailing-basket-mom -> fwd-basket-return) BH-FDR across lookback x hold x era panel")
    P("(IC is k-invariant; one test per era|lb|hold. reject = survives 10% FDR)")
    if bh:
        for kk in sorted(bh):
            v = bh[kk]
            P(f"  {kk:<22} p={v['p']:.4f}  q={v['q']:.4f}  reject={v['reject']}")
        n_rej = sum(1 for v in bh.values() if v["reject"])
        P(f"  -> {n_rej}/{len(bh)} configs survive Benjamini-Hochberg FDR(10%)")
    else:
        P("  (no p-values)")

    if best:
        P("\n### Best NET config (full era, cost=20bps, by excess Sharpe)")
        P(f"  lb={best['lb']} hold={best['hold']} k={best['k']}: "
          f"book μ={best['book_mean_pct']}%/period bench μ={best['bench_mean_pct']}% "
          f"excess μ={best['exc_mean_pct']}% | bookSharpe={best['book_sharpe']} "
          f"excSharpe={best['exc_sharpe']} bookDD={best['book_maxdd_pct']}% "
          f"excHit={best['exc_hit']} n={best['n']}")
        if boot:
            P(f"  block-bootstrap excess-Sharpe 95% CI: {boot.get('sharpe_ci')} "
              f"(P[Sh>0]={boot.get('sharpe_gt0_prob')}); maxDD CI%={boot.get('maxdd_ci_pct')}")
    P("=" * 96)


if __name__ == "__main__":
    sys.exit(main())
