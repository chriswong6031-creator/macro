"""China QUALITY factor (ROE) — Phase 0 validation (akshare, the Tushare fallback).

Value already FAILED on A-shares (reports/china-value-phase0.md): cheap stocks are value
traps, the priciest out-returned the cheapest. Quality is the OTHER fundamental factor and
a genuinely different mechanism — profitability PERSISTS, and quality often works where
value fails, especially in a growth-favouring market like A-shares 2016-26. So this tests
it before we decide whether the Tushare points are worth buying.

Signal: weighted ROE (加权净资产收益率), the full-year (FY, Dec-31) figure, made
POINT-IN-TIME by lagging availability to Apr-30 of the following year (the A-share annual-
report deadline — no look-ahead). At each month sort into 5 ROE quintiles, long each EW
21d: Q1 = highest ROE (QUALITY) … Q5 = lowest (junk). The quality premium = Q1 out-returns
/ out-Sharpes Q5 + the market; a positive Q1−Q5 spread Sharpe is the headline. Cross-
sectional and sector-neutral. Forward returns from the deep close panel. ROE is rank-based
(percentile), so extreme values don't distort. Writes reports/china-quality-phase0.md.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from scripts.china_lowvol_phase0 import band_returns, summarize  # noqa: E402

ROE = "data/china_search/roe.parquet"
DEEP = "data/china_search/closes_deep.parquet"
MEMBERS = "data/china_search/members.parquet"
JUNK = "A-share"
QUINTILES = [(0.8, 1.0, "Q1 quality (highest ROE)"), (0.6, 0.8, "Q2"), (0.4, 0.6, "Q3"),
             (0.2, 0.4, "Q4"), (0.0, 0.2, "Q5 junk (lowest ROE)")]


def main() -> int:
    root = config.ROOT
    if not (root / ROE).exists():
        print(f"no ROE panel — run the akshare ROE fetch first ({ROE})")
        return 1
    roe = pd.read_parquet(root / ROE).sort_index()
    roe = roe.loc[:, ~roe.columns.duplicated()]
    closes = pd.read_parquet(root / DEEP).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / MEMBERS)
    sector = pd.Series({t: (s if s != JUNK else "—") for t, s in members["sector"].items()})

    common = [t for t in roe.columns if t in closes.columns and sector.get(t, "—") != "—"]
    closes = closes[common]
    sector = sector.reindex(common).fillna("—")
    fwd = closes.pct_change(21, fill_method=None).shift(-21)

    # FY (Dec-31) ROE only, made point-in-time: a fiscal-year figure is public by Apr-30 of
    # the NEXT year (A-share annual-report deadline) → lag availability +4 months, no leak.
    fy = roe[common][roe.index.month == 12].copy()
    fy.index = fy.index + pd.DateOffset(months=4)
    fy = fy[~fy.index.duplicated(keep="last")].sort_index()
    roe_al = fy.reindex(closes.index.union(fy.index)).ffill().reindex(closes.index)

    idx = closes.index
    grid = [idx[idx <= me][-1] for me in pd.date_range(idx.min(), idx.max(), freq="ME") if len(idx[idx <= me])]
    grid = [d for d in grid if idx.get_loc(d) + 21 < len(idx) and roe_al.loc[d].notna().sum() >= 50]
    span = f"{grid[0].date()}→{grid[-1].date()}" if grid else "—"
    print(f"[quality] {len(common)} names with ROE · {len(grid)} rebalances · {span}")
    if len(grid) < 12:
        print("too few rebalances with ROE coverage"); return 1

    mkt = summarize(band_returns(grid, fwd, roe_al, sector, 0.0, 1.0))
    panels = {}
    for sn in (False, True):
        key = f"ROE (weighted, FY) · {'sector-neutral' if sn else 'cross-sectional'}"
        rows = {lbl: summarize(band_returns(grid, fwd, roe_al, sector, lo, hi, sn=sn)) for lo, hi, lbl in QUINTILES}
        q1 = band_returns(grid, fwd, roe_al, sector, 0.8, 1.0, sn=sn)
        q5 = band_returns(grid, fwd, roe_al, sector, 0.0, 0.2, sn=sn)
        spread = (q1.reset_index(drop=True) - q5.reset_index(drop=True)).dropna()
        panels[key] = {"rows": rows, "spread": summarize(spread)}
        print(f"  [{key}] Q1-quality Sharpe {rows['Q1 quality (highest ROE)'].get('sharpe')} vs "
              f"Q5-junk {rows['Q5 junk (lowest ROE)'].get('sharpe')} · quality−junk spread "
              f"Sharpe {panels[key]['spread'].get('sharpe')}")

    out = root / config.load()["storage"]["reports_dir"] / "china-quality-phase0.md"
    out.write_text(render(panels, mkt, common, grid, span))
    print(f"\n[report] {out}\n{verdict(panels, mkt)}")
    return 0


def verdict(panels, mkt):
    best = max(panels.items(), key=lambda kv: (kv[1]["spread"].get("sharpe") or -9))
    q1, sp = best[1]["rows"]["Q1 quality (highest ROE)"], best[1]["spread"]
    go = (sp.get("sharpe") or 0) > 0.3 and (q1.get("sharpe") or 0) > (mkt.get("sharpe") or 0)
    return (f"[verdict] {'GO — quality premium present' if go else 'WEAK/REVIEW'} — best '{best[0]}': "
            f"Q1-quality Sharpe {q1.get('sharpe')} vs market {mkt.get('sharpe')}; quality−junk spread "
            f"Sharpe {sp.get('sharpe')} (+{sp.get('ann_ret_pct')}%/yr). High ROE beats low ROE → "
            f"{'BUY the Tushare points (clean ROE + board)' if go else 'SKIP — fundamentals dont work on A-shares'}.")


def render(panels, mkt, common, grid, span):
    L = ["# China QUALITY factor (ROE) — Phase 0", "",
         "*`scripts/china_quality_phase0.py` (akshare weighted-ROE, FY, point-in-time +4mo lag). "
         "Each month sort into 5 ROE quintiles, long each EW 21d. Q1 = highest ROE (quality), Q5 = "
         "lowest (junk). The premium = Q1 out-returns/out-Sharpes Q5 + the market; quality−junk = the "
         f"Q1−Q5 spread. {len(common)} names with ROE, {len(grid)} monthly rebalances, {span}.*", "",
         f"**Market baseline (EW):** ann {mkt.get('ann_ret_pct')}% · Sharpe **{mkt.get('sharpe')}** "
         f"· maxDD {mkt.get('maxdd_pct')}%.", ""]
    for key, p in panels.items():
        L += [f"## {key}", "", "| quintile | ann return | Sharpe | max drawdown | hit | n |",
              "|---|--:|--:|--:|--:|--:|"]
        for lbl in ("Q1 quality (highest ROE)", "Q2", "Q3", "Q4", "Q5 junk (lowest ROE)"):
            r = p["rows"][lbl]
            L.append(f"| {lbl} | _thin_ |  |  |  |  |" if r.get("error")
                     else f"| {lbl} | {r['ann_ret_pct']}% | {r['sharpe']} | {r['maxdd_pct']}% | {r['hit']} | {r['n']} |")
        s = p["spread"]
        L += ["", f"**quality−junk spread (Q1−Q5):** Sharpe **{s.get('sharpe')}** · ann "
              f"{s.get('ann_ret_pct')}% · maxDD {s.get('maxdd_pct')}% · hit {s.get('hit')}.", ""]
    L += ["---", "", "**How to read.** A quality premium shows Q1 (high ROE) out-returning Q5 (low ROE) "
          "with a positive quality−junk spread Sharpe and a monotone Q1→Q5 decline. Quality is a "
          "different mechanism from value (which failed here): it can work in growth-favouring markets. "
          "FY ROE is lagged +4mo for PIT; akshare coverage is partial. If quality validates, Tushare "
          "daily_basic + fina_indicator (bulk, by date) is the clean production source — worth the points.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
