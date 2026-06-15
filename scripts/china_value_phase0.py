"""China VALUE factor — Phase 0 validation (akshare PE-TTM, the Tushare fallback).

The intended source was Tushare daily_basic (bulk PE/PB by date), but the supplied token's
account has no interface access (needs ~2000 points), so this uses the keyless akshare
historical PE-TTM panel (data/china_search/pe_ttm.parquet, fetched per-stock from Baidu).

Tests the VALUE premium on A-shares: do CHEAP stocks (high earnings yield = 1/PE) out-earn
EXPENSIVE ones? A-share value is REGIME-DEPENDENT — it was weak/negative through the
pre-2017 small-cap/growth bubble and stronger afterwards — so let the data decide, the
same discipline that killed momentum and validated reversal + low-vol here.

Signal: earnings yield E/P = 1/PE_ttm (PE>0 only; loss-makers PE<=0 dropped — a separate
distress bucket, not "value"). Each month sort into 5 E/P quintiles, long each EW for 21d:
Q1 = highest E/P (CHEAPEST / value) … Q5 = lowest E/P (priciest / growth). The value
premium = Q1 out-returns / out-Sharpes Q5 (+ the market); a positive Q1−Q5 spread Sharpe
is the headline. Cross-sectional and sector-neutral (value within a sector). Forward
returns from the deep close panel. Writes reports/china-value-phase0.md.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from scripts.china_lowvol_phase0 import band_returns, summarize  # noqa: E402  (reuse)

PE = "data/china_search/pe_ttm.parquet"
DEEP = "data/china_search/closes_deep.parquet"
MEMBERS = "data/china_search/members.parquet"
JUNK = "A-share"
# E/P quintiles: Q1 = top 20% earnings yield = CHEAPEST (value); Q5 = priciest (growth)
QUINTILES = [(0.8, 1.0, "Q1 value (cheapest)"), (0.6, 0.8, "Q2"), (0.4, 0.6, "Q3"),
             (0.2, 0.4, "Q4"), (0.0, 0.2, "Q5 growth (priciest)")]


def main() -> int:
    root = config.ROOT
    if not (root / PE).exists():
        print(f"no PE panel — run the akshare fetch first ({PE})")
        return 1
    pe = pd.read_parquet(root / PE).sort_index()
    pe = pe.loc[:, ~pe.columns.duplicated()]
    closes = pd.read_parquet(root / DEEP).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / MEMBERS)
    sector = pd.Series({t: (s if s != JUNK else "—") for t, s in members["sector"].items()})

    common = [t for t in pe.columns if t in closes.columns and sector.get(t, "—") != "—"]
    closes = closes[common]
    sector = sector.reindex(common).fillna("—")
    fwd = closes.pct_change(21, fill_method=None).shift(-21)

    # earnings yield = 1/PE, PE>0 only; align PE (daily, Baidu dates) to the close calendar
    pe_al = pe[common].reindex(closes.index).ffill(limit=10)
    ey = (1.0 / pe_al).where(pe_al > 0)

    idx = closes.index
    grid = [idx[idx <= me][-1] for me in pd.date_range(idx.min(), idx.max(), freq="ME") if len(idx[idx <= me])]
    grid = [d for d in grid if idx.get_loc(d) + 21 < len(idx) and ey.loc[d].notna().sum() >= 50]
    span = f"{grid[0].date()}→{grid[-1].date()}" if grid else "—"
    print(f"[value] {len(common)} names with PE · {len(grid)} rebalances · {span}")
    if len(grid) < 12:
        print("too few rebalances with PE coverage — fetch more PE history"); return 1

    mkt = summarize(band_returns(grid, fwd, ey, sector, 0.0, 1.0))
    panels = {}
    for sn in (False, True):
        key = f"earnings yield (1/PE) · {'sector-neutral' if sn else 'cross-sectional'}"
        rows = {lbl: summarize(band_returns(grid, fwd, ey, sector, lo, hi, sn=sn)) for lo, hi, lbl in QUINTILES}
        q1 = band_returns(grid, fwd, ey, sector, 0.8, 1.0, sn=sn)
        q5 = band_returns(grid, fwd, ey, sector, 0.0, 0.2, sn=sn)
        spread = (q1.reset_index(drop=True) - q5.reset_index(drop=True)).dropna()
        panels[key] = {"rows": rows, "spread": summarize(spread)}
        print(f"  [{key}] Q1-value Sharpe {rows['Q1 value (cheapest)'].get('sharpe')} vs "
              f"Q5-growth {rows['Q5 growth (priciest)'].get('sharpe')} · value−growth spread "
              f"Sharpe {panels[key]['spread'].get('sharpe')}")

    out = root / config.load()["storage"]["reports_dir"] / "china-value-phase0.md"
    out.write_text(render(panels, mkt, common, grid, span))
    print(f"\n[report] {out}\n{verdict(panels, mkt)}")
    return 0


def verdict(panels, mkt):
    best = max(panels.items(), key=lambda kv: (kv[1]["spread"].get("sharpe") or -9))
    q1, sp = best[1]["rows"]["Q1 value (cheapest)"], best[1]["spread"]
    go = (sp.get("sharpe") or 0) > 0.3 and (q1.get("sharpe") or 0) > (mkt.get("sharpe") or 0)
    return (f"[verdict] {'GO — value premium present' if go else 'WEAK/REVIEW'} — best '{best[0]}': "
            f"Q1-value Sharpe {q1.get('sharpe')} vs market {mkt.get('sharpe')}; value−growth spread "
            f"Sharpe {sp.get('sharpe')} (+{sp.get('ann_ret_pct')}%/yr). Value = cheap (high E/P) beats pricey.")


def render(panels, mkt, common, grid, span):
    L = ["# China VALUE factor (earnings yield) — Phase 0", "",
         "*`scripts/china_value_phase0.py` (akshare PE-TTM fallback — Tushare account had no "
         "access). Tests the value premium: each month sort into 5 earnings-yield (1/PE) quintiles, "
         "long each EW 21d. Q1 = cheapest (highest E/P), Q5 = priciest. The premium = Q1 out-returns/"
         f"out-Sharpes Q5 + the market; value−growth = the Q1−Q5 spread. {len(common)} names with PE, "
         f"{len(grid)} monthly rebalances, {span}. Loss-makers (PE<=0) dropped.*", "",
         f"**Market baseline (EW):** ann {mkt.get('ann_ret_pct')}% · Sharpe **{mkt.get('sharpe')}** "
         f"· maxDD {mkt.get('maxdd_pct')}%.", ""]
    for key, p in panels.items():
        L += [f"## {key}", "", "| quintile | ann return | Sharpe | max drawdown | hit | n |",
              "|---|--:|--:|--:|--:|--:|"]
        for lbl in ("Q1 value (cheapest)", "Q2", "Q3", "Q4", "Q5 growth (priciest)"):
            r = p["rows"][lbl]
            L.append(f"| {lbl} | _thin_ |  |  |  |  |" if r.get("error")
                     else f"| {lbl} | {r['ann_ret_pct']}% | {r['sharpe']} | {r['maxdd_pct']}% | {r['hit']} | {r['n']} |")
        s = p["spread"]
        L += ["", f"**value−growth spread (Q1−Q5):** Sharpe **{s.get('sharpe')}** · ann "
              f"{s.get('ann_ret_pct')}% · maxDD {s.get('maxdd_pct')}% · hit {s.get('hit')}.", ""]
    L += ["---", "", "**How to read.** A value premium shows Q1 (cheapest) out-returning Q5 (priciest) "
          "with a positive value−growth spread Sharpe; a MONOTONE return decline Q1→Q5 is the clean "
          "signature. A-share value is regime-dependent (weak pre-2017), so the era in the panel "
          "matters. PE-TTM is point-in-time-ish (Baidu daily); akshare per-stock coverage is partial — "
          "treat a thin panel cautiously. If it validates, the clean rebuild is Tushare daily_basic "
          "(bulk PE/PB/ROE by date) once the account has points.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
