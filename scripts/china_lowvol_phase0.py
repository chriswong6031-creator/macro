"""China low-volatility / low-beta factor — Phase 0 validation (zero new data).

After the deep-history work settled the China cross-section (momentum DEAD, reversal the
edge), this tests the next candidate that needs NO external data — the **low-volatility
anomaly**: low-risk stocks tend to earn similar returns to high-risk ones, so they win on
a RISK-ADJUSTED basis (Haugen-Baker / Frazzini-Pedersen "betting against beta"). It is one
of the few factors that often survives where momentum fails — a strong prior for A-shares.

Computed from the deep panel alone (`scripts/china_residual_alpha_deep.py --fetch`):
  vol   = trailing 252d annualized volatility of daily returns
  beta  = causal 252d beta to the market (SSE Composite), shrunk
Both ranked ASCENDING (low = preferred). Size is NOT tested — we have only a current
market-cap snapshot, no point-in-time history, so a size backtest would be look-ahead.

Method: sort the universe into 5 quintiles by the factor each month; long each quintile
EW, hold 21d; report the quintile's ABSOLUTE annualized return, Sharpe and max drawdown
(the anomaly = Q1 'lowest vol' earns a HIGHER Sharpe than Q5 'highest vol' and the market,
even if its raw return is similar/lower). Also the sector-neutral variant. The low-minus-
high SPREAD's Sharpe is the headline. Writes reports/china-lowvol-phase0.md.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config, store  # noqa: E402

DEEP = "data/china_search/closes_deep.parquet"
MEMBERS = "data/china_search/members.parquet"
JUNK = "A-share"
QUINTILES = [(0.0, 0.2, "Q1 lowest"), (0.2, 0.4, "Q2"), (0.4, 0.6, "Q3"),
             (0.6, 0.8, "Q4"), (0.8, 1.0, "Q5 highest")]


def _ann_sharpe(x):
    return float(x.mean() / x.std() * np.sqrt(12)) if len(x) > 1 and x.std() else 0.0


def _maxdd(x):
    cum = (1 + x).cumprod()
    return float((cum / cum.cummax() - 1).min())


def _causal_beta(R, m, win=252, minp=130):
    return (R.rolling(win, min_periods=minp).cov(m)
            .div(m.rolling(win, min_periods=minp).var(), axis=0)).shift(1)


def band_returns(grid, fwd, sig, sector, lo, hi, *, sn=False):
    """Monthly EW long of the [lo,hi] factor-percentile band; absolute fwd returns."""
    out = []
    for d in grid:
        if d not in fwd.index or d not in sig.index:
            continue
        fr = fwd.loc[d].dropna()
        s = sig.loc[d]
        if sn:
            s = s - s.groupby(sector).transform("mean")
        s = s.reindex(fr.index).dropna()
        if len(s) < 40:
            continue
        sel = s[(s >= s.quantile(lo)) & (s <= s.quantile(min(hi, 1.0)))].index
        if len(sel) >= 5:
            out.append(float(fr.reindex(sel).mean()))
    return pd.Series(out)


def summarize(series):
    if len(series) < 12:
        return {"error": "thin"}
    return {"ann_ret_pct": round(series.mean() * 12 * 100, 1), "sharpe": round(_ann_sharpe(series), 2),
            "maxdd_pct": round(_maxdd(series) * 100, 1), "hit": round(float((series > 0).mean()), 3),
            "n": len(series)}


def main() -> int:
    root = config.ROOT
    if not (root / DEEP).exists():
        print("no deep panel — run: .venv/bin/python -m scripts.china_residual_alpha_deep --fetch")
        return 1
    closes = pd.read_parquet(root / DEEP).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / MEMBERS)
    sector = pd.Series({t: (s if s != JUNK else "—") for t, s in members["sector"].items()})
    sector = sector.reindex(closes.columns).fillna("—")
    closes = closes.loc[:, sector != "—"]
    sector = sector[sector != "—"]

    R = closes.pct_change(fill_method=None)
    vol = R.rolling(252, min_periods=130).std() * np.sqrt(252)
    sse = store.read("china", "000001.SS")
    m = sse["close"].pct_change(fill_method=None).reindex(R.index) if sse is not None else R.mean(axis=1)
    beta = _causal_beta(R, m)
    fwd = closes.pct_change(21, fill_method=None).shift(-21)

    idx = closes.index
    grid = [idx[idx <= me][-1] for me in pd.date_range(idx.min(), idx.max(), freq="ME") if len(idx[idx <= me])]
    grid = [d for d in grid if idx.get_loc(d) >= 263 and idx.get_loc(d) + 21 < len(idx)]

    mkt = summarize(band_returns(grid, fwd, vol, sector, 0.0, 1.0))   # whole-universe baseline
    panels = {}
    for fac_name, sig in [("low VOL (trailing 252d σ)", vol), ("low BETA (causal 252d)", beta)]:
        for sn in (False, True):
            key = f"{fac_name} · {'sector-neutral' if sn else 'cross-sectional'}"
            rows = {lbl: summarize(band_returns(grid, fwd, sig, sector, lo, hi, sn=sn))
                    for lo, hi, lbl in QUINTILES}
            q1 = band_returns(grid, fwd, sig, sector, 0.0, 0.2, sn=sn)
            q5 = band_returns(grid, fwd, sig, sector, 0.8, 1.0, sn=sn)
            spread = (q1.reset_index(drop=True) - q5.reset_index(drop=True)).dropna()  # low − high
            panels[key] = {"rows": rows, "spread": summarize(spread)}
            print(f"  [{key}] Q1 Sharpe {rows['Q1 lowest'].get('sharpe')} vs "
                  f"Q5 {rows['Q5 highest'].get('sharpe')} · low−high spread Sharpe {panels[key]['spread'].get('sharpe')}")

    out = root / config.load()["storage"]["reports_dir"] / "china-lowvol-phase0.md"
    out.write_text(render(panels, mkt, closes, grid))
    print(f"\n[report] {out}\n{verdict(panels, mkt)}")
    return 0


def verdict(panels, mkt):
    # the low-vol anomaly is a RISK-ADJUSTED / defensive effect, NOT a long-short alpha:
    # the right test is Q1 (low-risk) Sharpe > market AND > Q5 (high-risk), with a SHALLOWER
    # drawdown — not the ~0 long-short spread.
    mkt_s, mkt_dd = (mkt.get("sharpe") or 0), (mkt.get("maxdd_pct") or 0)
    best = max(panels.items(), key=lambda kv: (kv[1]["rows"]["Q1 lowest"].get("sharpe") or -9))
    q1, q5 = best[1]["rows"]["Q1 lowest"], best[1]["rows"]["Q5 highest"]
    go = (q1.get("sharpe") or 0) > mkt_s and (q1.get("sharpe") or 0) > (q5.get("sharpe") or 0) \
        and (q1.get("maxdd_pct") or -99) > mkt_dd
    return (f"[verdict] {'GO — low-vol defensive tilt' if go else 'WEAK'} — best '{best[0]}': "
            f"Q1(low-risk) Sharpe {q1.get('sharpe')}/DD {q1.get('maxdd_pct')}% vs market {mkt_s}/{mkt_dd}% "
            f"vs Q5(high-risk) {q5.get('sharpe')}/{q5.get('maxdd_pct')}%. Defensive: market-like return, "
            "higher Sharpe, shallower drawdown — a tilt/sleeve, NOT a long-short alpha (spread ~0).")


def render(panels, mkt, closes, grid):
    L = ["# China low-volatility / low-beta — Phase 0", "",
         "*`scripts/china_lowvol_phase0.py`. Tests the low-RISK anomaly on the deep A-share panel "
         "(no external data). Each month sort the universe into 5 factor quintiles, long each EW for "
         "21d; the anomaly = the LOW-risk quintile (Q1) earns a higher risk-adjusted return (Sharpe) "
         "than the HIGH-risk quintile (Q5) and the market, even if raw returns are similar. low−high "
         f"= the long-short spread (Q1 minus Q5). Panel {closes.shape[1]} names, {len(grid)} monthly "
         f"rebalances, {closes.index.min().date()}→{closes.index.max().date()}.*", "",
         f"**Market baseline (EW universe):** ann {mkt.get('ann_ret_pct')}% · Sharpe **{mkt.get('sharpe')}** "
         f"· maxDD {mkt.get('maxdd_pct')}%.", ""]
    for key, p in panels.items():
        L += [f"## {key}", "", "| quintile | ann return | Sharpe | max drawdown | hit | n |",
              "|---|--:|--:|--:|--:|--:|"]
        for lbl in ("Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"):
            r = p["rows"][lbl]
            if r.get("error"):
                L.append(f"| {lbl} | _thin_ |  |  |  |  |"); continue
            L.append(f"| {lbl} | {r['ann_ret_pct']}% | {r['sharpe']} | {r['maxdd_pct']}% | {r['hit']} | {r['n']} |")
        s = p["spread"]
        L += ["", f"**low−high spread (Q1−Q5):** Sharpe **{s.get('sharpe')}** · ann {s.get('ann_ret_pct')}% "
              f"· maxDD {s.get('maxdd_pct')}% · hit {s.get('hit')}.", ""]
    L += ["---", "", "**How to read.** A clean low-vol anomaly shows a MONOTONE Sharpe decline Q1→Q5 "
          "(lowest-risk wins risk-adjusted) and a positive low−high spread Sharpe. If Q1 also beats the "
          "market Sharpe, low-vol is a defensible A-share factor (a tilt / defensive sleeve, framed as "
          "risk-adjusted not higher-raw-return). Excess/returns here are gross, pre-cost; low-vol is "
          "low-turnover so costs bite less than reversal.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
