"""Block-bootstrap significance test for the net-liquidity gate (autocorr lens).

The headline month-as-unit Welch t=2.83 (exp +2.15% vs con +0.89%) treats months as
iid. But the unit of randomness here is a single daily macro draw shared across all
assets, and forward 21d returns OVERLAP heavily (date t and t+1 share 20/21 of their
window). Both inflate effective N and make a naive t-stat optimistic.

This re-tests the exp-vs-con RETURN gap with a stationary CALENDAR-QUARTER block
bootstrap on the DAILY series (cross-asset-mean momentum-long fwd 21d return + regime
per date). Resampling contiguous quarters preserves the autocorrelation that the
month-as-unit test ignores. We report:
  - the observed gap (daily-aggregated, to match the bootstrap statistic exactly)
  - fraction of resamples where exp>con  (a one-sided bootstrap "p")
  - the bootstrap CI on the gap
  - the same with NON-overlapping (21d-spaced) sampling as a cross-check
  - block-size sensitivity (quarter vs month vs half-year) — bigger block = more honest
  - multiple-testing context: how many param cells in the sweep beat the headline

Usage: .venv/bin/python -m scripts.research_liquidity_gate_blockboot
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research_liquidity_gate import net_liquidity, MOM_LB, EXP_THR, START
from scripts.research_trend_gate import STEP, asset_class, fwd_return, load_panel

ROC_4W = 20
FWD = 21
N_BOOT = 5000
SEED = 12345


def build_daily(panel: dict[str, pd.Series], nl: pd.Series,
                step: int = STEP) -> pd.DataFrame:
    """One row per DATE: cross-asset mean momentum-long fwd-21d return + regime.

    Mirrors research_liquidity_gate_robust.main()[E] exactly: weekly-sampled
    momentum-long asset-days, mean fwd per date, regime from net-liq 4w-RoC.
    """
    roc4 = nl.diff(ROC_4W)
    rows = []
    for name, close in panel.items():
        mom = close.pct_change(MOM_LB)
        fr = fwd_return(close, FWD)
        wk = np.zeros(len(close), bool)
        wk[::step] = True
        ok = wk & fr.notna() & (mom > 0)
        for dt in close.index[ok]:
            rows.append((dt, float(fr.loc[dt])))
    s = pd.DataFrame(rows, columns=["date", "fwd"])
    s = s[s["date"] >= START]
    s["roc"] = s["date"].map(roc4)
    s = s.dropna(subset=["roc"])
    s["reg"] = np.where(s["roc"] >= EXP_THR, "exp",
                        np.where(s["roc"] <= -EXP_THR, "con", "neu"))
    daily = s.groupby("date").agg(fwd=("fwd", "mean"), reg=("reg", "first"))
    daily = daily[daily["reg"] != "neu"].copy()
    daily = daily.sort_index()
    return daily


def gap_of(d: pd.DataFrame) -> float:
    e = d["fwd"][d["reg"] == "exp"]
    c = d["fwd"][d["reg"] == "con"]
    if len(e) < 2 or len(c) < 2:
        return np.nan
    return 100 * (e.mean() - c.mean())


def block_bootstrap(daily: pd.DataFrame, block: str, n_boot: int = N_BOOT,
                    seed: int = SEED) -> tuple:
    """Resample contiguous calendar blocks (with replacement) to length ~= original.

    block in {'Q','M','2Q'} -> calendar quarter / month / half-year contiguous chunks.
    Statistic = exp_mean - con_mean (pp). Returns (frac exp>con, lo, hi, gaps array,
    n_blocks_orig, frac with valid both-regime).
    """
    rng = np.random.default_rng(seed)
    if block == "2Q":
        key = daily.index.to_period("Q")
        # group quarters into pairs by ordinal
        ords = key.astype("int64")
        key = pd.Index((ords // 2), name="blk")
    else:
        key = daily.index.to_period(block)
    daily = daily.assign(_blk=key)
    groups = [g for _, g in daily.groupby("_blk", sort=True)]
    n_blocks = len(groups)
    total_rows = len(daily)

    gaps = []
    n_valid = 0
    for _ in range(n_boot):
        picked = []
        nrows = 0
        # sample blocks with replacement until we cover ~ original row count
        while nrows < total_rows:
            g = groups[rng.integers(n_blocks)]
            picked.append(g)
            nrows += len(g)
        boot = pd.concat(picked, ignore_index=True)
        g = gap_of(boot)
        if not np.isnan(g):
            n_valid += 1
            gaps.append(g)
    gaps = np.array(gaps)
    frac_pos = float((gaps > 0).mean())
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return frac_pos, lo, hi, gaps, n_blocks, n_valid / n_boot


def main() -> int:
    nl = net_liquidity()
    panel = load_panel()
    daily = build_daily(panel, nl)

    n_exp = int((daily["reg"] == "exp").sum())
    n_con = int((daily["reg"] == "con").sum())
    obs_gap = gap_of(daily)
    e = daily["fwd"][daily["reg"] == "exp"]
    c = daily["fwd"][daily["reg"] == "con"]
    print(f"{'='*80}")
    print("BLOCK-BOOTSTRAP significance of exp-vs-con fwd-21d RETURN gap (autocorr lens)")
    print(f"{'='*80}")
    print(f"daily regime-classified dates: {len(daily)}  "
          f"({daily.index.min().date()}–{daily.index.max().date()})")
    print(f"  exp days={n_exp} mean={100*e.mean():+.2f}%   "
          f"con days={n_con} mean={100*c.mean():+.2f}%")
    print(f"  OBSERVED daily-aggregated gap = {obs_gap:+.2f}pp")

    # naive iid t on the daily series (the thing we are correcting)
    def welch(a, b):
        return (a.mean() - b.mean()) / np.sqrt(a.var()/len(a) + b.var()/len(b))
    print(f"  naive daily-as-iid Welch t = {welch(e, c):.2f}  "
          f"(WRONG: ignores overlap+clustering, shown for contrast)")

    # contiguous-run count = honest-ish block count
    run = (daily["reg"] != daily["reg"].shift()).cumsum()
    n_runs = run.nunique()
    print(f"  contiguous regime runs (episodes) = {n_runs}  "
          f"<- true independent-draw scale\n")

    for block, label in (("Q", "calendar QUARTER (primary)"),
                         ("M", "calendar MONTH"),
                         ("2Q", "HALF-YEAR (most conservative)")):
        frac_pos, lo, hi, gaps, nb, valid = block_bootstrap(daily, block)
        p_one = 1 - frac_pos
        print(f"[block = {label}]  n_blocks={nb}")
        print(f"   bootstrap gap: median={np.median(gaps):+.2f}pp  "
              f"mean={gaps.mean():+.2f}pp  95% CI=[{lo:+.2f}, {hi:+.2f}]pp")
        print(f"   P(exp>con) = {frac_pos:.3f}   one-sided p = {p_one:.3f}   "
              f"CI crosses 0: {'YES' if lo < 0 < hi else 'no'}")
        print(f"   (resamples with both regimes present: {valid:.0%})\n")

    # cross-check: non-overlapping daily sampling (every 21st regime date) removes
    # the autocorrelation from window overlap, then quarter-block bootstrap on that.
    print("[cross-check] NON-OVERLAPPING (~21d-spaced) dates, quarter-block bootstrap")
    nonoverlap = daily.iloc[::FWD].copy()
    no_gap = gap_of(nonoverlap)
    ne = int((nonoverlap["reg"] == "exp").sum())
    nc = int((nonoverlap["reg"] == "con").sum())
    fp, lo, hi, gaps, nb, valid = block_bootstrap(nonoverlap, "Q")
    print(f"   non-overlap dates: {len(nonoverlap)} (exp={ne}, con={nc})  "
          f"gap={no_gap:+.2f}pp")
    print(f"   bootstrap gap median={np.median(gaps):+.2f}pp  "
          f"95% CI=[{lo:+.2f}, {hi:+.2f}]pp  P(exp>con)={fp:.3f}\n")

    # multiple-testing context: how many sweep cells beat the headline gap?
    print("[multiple-testing context] return-gap (exp-con mean, pp) across the "
          "param grid that\n   was searched (window x threshold), daily-aggregated, lag=3")
    print("            thr=10    thr=25    thr=50")
    n_cells, n_pos = 0, 0
    for win in (10, 20, 40):
        roc = nl.diff(win)
        cells = []
        for thr in (10, 25, 50):
            d2 = daily.copy()
            # reclassify using this (win,thr) on the same dates
            d2["roc2"] = d2.index.map(roc)
            d2 = d2.dropna(subset=["roc2"])
            d2["reg2"] = np.where(d2["roc2"] >= thr, "exp",
                                  np.where(d2["roc2"] <= -thr, "con", "neu"))
            ee = d2["fwd"][d2["reg2"] == "exp"]
            cc = d2["fwd"][d2["reg2"] == "con"]
            g = 100*(ee.mean()-cc.mean()) if len(ee) >= 5 and len(cc) >= 5 else np.nan
            cells.append(g)
            if not np.isnan(g):
                n_cells += 1
                n_pos += int(g > 0)
        print(f"   win={win:>2}   " + "  ".join(
            f"{g:>+7.2f}" if not np.isnan(g) else "      -" for g in cells))
    print(f"   positive cells: {n_pos}/{n_cells}  "
          f"(sweep was searched -> headline cell is a best-of, discount accordingly)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
