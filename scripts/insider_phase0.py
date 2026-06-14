"""Insider-buying factor — Phase 0 honest IC/FDR/DSR harness.

The HARD GATE before insider buying is allowed anywhere near production scoring:
does ranking S&P 1500 stocks on point-in-time insider-buying actually predict
forward returns — on THIS universe, net of cost, after the multiple-testing and
survivorship haircuts the rest of the book is held to (SP_VECTOR_VIABILITY.md,
RESIDUAL_ALPHA_MOMENTUM.md)? The aggregate leaderboard already shipped is a
display gadget; this decides whether the SIGNAL earns a scored leg or stays
context-only.

Signals (engine/insider_factor.build_signals, trailing `--window` months of
FILINGS, causal — a trade enters only once its filing_date has passed):
  buy_usd        gross purchase $                       (size-confounded baseline)
  net_usd        purchase − sale $
  n_buyers       distinct insiders buying  (cluster/breadth — size-robust)
  opp_buy_usd    opportunistic-only purchase $          (Cohen–Malloy–Pomorski)
  opp_buyers     distinct opportunistic insiders buying (the CMP headline)
  role_buy_usd   role-weighted purchase $ (CEO/CFO > director > 10%)
  *_mcap         net/opp/role $ ÷ PIT market cap        (size-normalised)
Each is scored raw AND sector-neutral (demeaned within GICS). IC is the per-date
cross-sectional rank corr vs the forward return — computed over the FULL universe
(buyers-vs-field) and over the ACTIVE subset (does more buying beat less, among
names with any insider trade). Signed signals also get a dollar-neutral top-vs-
bottom-quintile net-of-cost backtest with a Deflated Sharpe + bootstrap CI.

Run:
  .venv/bin/python -m scripts.insider_phase0
  .venv/bin/python -m scripts.insider_phase0 --window 6 --horizon 63 --pit
Writes reports/insider-phase0.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from engine.insider_factor import build_signals, classify_routine, market_cap  # noqa: E402
from engine.validation import (benjamini_hochberg, block_bootstrap_ci,  # noqa: E402
                               deflated_sharpe, dsr_verdict, ic_summary,
                               rank_ic, ret_moments)
from lib import config  # noqa: E402

COST_BPS = 5.0   # single-name one-way (spread+impact), charged on quintile turnover
# Two-sided cross-sections (net sellers at the bottom) → meaningful dollar-neutral L/S.
LS_SIGNALS = ("net_usd", "net_usd_mcap", "opp_buy_usd_mcap", "role_buy_usd_mcap")


def _closes_deep() -> pd.DataFrame:
    """The deep-history broad close matrix (1962→), for a full-power IC read over
    the whole 2006→ insider panel rather than the ~3y live breadth cache."""
    p = config.data_dir() / "breadth" / "_closes_deep.parquet"
    return pd.read_parquet(p).sort_index() if p.exists() else pd.DataFrame()


def _load_panel() -> pd.DataFrame:
    base = config.data_dir() / "sec_insider"
    full = base / "insider_panel.parquet"
    if full.exists():
        return pd.read_parquet(full)
    parts = sorted((base / "panel").glob("*.parquet"))
    if not parts:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    return df.sort_values("filing_date").reset_index(drop=True)


def _load_membership():
    """Prefer the full S&P 1500 PIT membership (large+mid+small, scripts.midsmall_pit)
    so the de-bias test runs where insider buying actually lives; fall back to the
    S&P 500-only membership."""
    base = config.data_dir() / "breadth"
    p = base / "sp1500_pit_membership.parquet"
    if not p.exists():
        p = base / "sp500_pit_membership.parquet"
    if not p.exists():
        return None
    m = pd.read_parquet(p)
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"])
    return m


def _eligible(membership, d) -> set:
    d = pd.Timestamp(d)
    mask = (membership["start_date"] <= d) & (
        membership["end_date"].isna() | (membership["end_date"] >= d))
    return set(membership.loc[mask, "ticker"])


def month_grid(index, horizon):
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if not len(d):
            continue
        loc = index.get_loc(d[-1])
        if loc + horizon < len(index):
            out.append(d[-1])
    return out


def quintile_ls(R, sig, grid, n_trials, membership=None):
    """Long top-quintile / short bottom-quintile, EW, monthly rebalance, net of cost."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        s = sig.loc[d].dropna() if d in sig.index else pd.Series(dtype=float)
        s = s[s != 0.0]                                  # only names with a signal
        if membership is not None:
            s = s[s.index.isin(_eligible(membership, d))]
        if len(s) < 25:
            continue
        hi, lo = s.quantile(0.8), s.quantile(0.2)
        top, bot = s[s >= hi].index, s[s <= lo].index
        if len(top) and len(bot) and hi > lo:
            w.loc[d, top] = 1.0 / len(top)
            w.loc[d, bot] = -1.0 / len(bot)
    w = w.replace(0.0, np.nan).ffill().fillna(0.0)
    pos = w.shift(1)
    gross = (pos * R.clip(-0.5, 0.5)).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    net = (gross - (COST_BPS / 1e4) * turn).loc[grid[0]:]
    net = net[net.index <= grid[-1]]
    mom = ret_moments(net)
    out = {"sharpe": round(float(net.mean() / net.std() * np.sqrt(252)), 2) if net.std() else None,
           "cum_pct": round(float(((1 + net).prod() - 1) * 100), 1),
           "n_days": int(net.notna().sum())}
    if mom:
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=max(n_trials, 1),
                              trading_year=252)
        if dsr:
            out["dsr"] = dsr["dsr"]
            out["verdict"] = dsr_verdict(dsr["dsr"])
    bc = block_bootstrap_ci(net, ann=252)
    if bc:
        out["sharpe_ci"] = bc["sharpe_ci"]
        out["sharpe_gt0_prob"] = bc["sharpe_gt0_prob"]
    return out


def _split_half_ic(per_date_ic: pd.Series) -> dict:
    """Mean IC in each half of the sample — a cheap stability/era check."""
    s = per_date_ic.dropna()
    if len(s) < 12:
        return {}
    mid = len(s) // 2
    return {"ic_h1": round(float(s.iloc[:mid].mean()), 4),
            "ic_h2": round(float(s.iloc[mid:].mean()), 4)}


def score(panel, closes, tkr_sector, *, window, horizon, membership=None, start_year=0):
    grid = month_grid(closes.index, horizon)
    if start_year:
        grid = [d for d in grid if d.year >= start_year]
    if len(grid) < 12:
        return {"error": f"grid too short ({len(grid)})"}

    closes_me = closes.loc[[d for d in grid if d in closes.index]]
    shares_panel = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    mcap = market_cap(closes_me, shares_panel, grid)

    panel = classify_routine(panel)
    sigs = build_signals(panel, grid, mcap=mcap, k_months=window)

    R = closes.pct_change(fill_method=None)
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)
    sec = pd.Series(tkr_sector).reindex(closes.columns)

    names = list(sigs)
    ic = {c: [] for c in names} | {f"{c}|SN": [] for c in names} | {f"{c}|act": [] for c in names}
    nseries, nactive = [], {c: [] for c in names}
    for d in grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if membership is not None:
            fr = fr[fr.index.isin(_eligible(membership, d))]
        if len(fr) < 10:
            continue
        nseries.append(int(len(fr)))
        for c in names:
            if d not in sigs[c].index:
                continue
            s = sigs[c].loc[d].reindex(fr.index)
            ic[c].append(rank_ic(s.fillna(0.0), fr))
            sn = s.fillna(0.0) - s.fillna(0.0).groupby(sec).transform("mean")
            ic[f"{c}|SN"].append(rank_ic(sn, fr))
            act = s[s != 0.0].dropna()                   # conditional on insider activity
            nactive[c].append(int(len(act)))
            ic[f"{c}|act"].append(rank_ic(act, fr.reindex(act.index)) if len(act) >= 10 else np.nan)

    rows, pvals = {}, {}
    for c, series in ic.items():
        ser = pd.Series(series)
        summ = ic_summary(ser.dropna(), periods_per_year=12)
        if summ.get("n", 0) >= 6:
            summ.update(_split_half_ic(ser))
            base = c.split("|")[0]
            if nactive.get(base):
                summ["med_active"] = int(np.median(nactive[base]))
            rows[c] = summ
            if summ.get("p_hac") is not None:
                pvals[c] = summ["p_hac"]
    for c, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[c]["q_fdr"] = q["q"]
        rows[c]["survives_fdr"] = q["reject"]

    ls = {c: quintile_ls(R, sigs[c], grid, n_trials=len(rows), membership=membership)
          for c in LS_SIGNALS if c in sigs}

    return {"span": f"{grid[0].date()}..{grid[-1].date()}", "rebalances": len(grid),
            "median_universe": int(np.median(nseries)) if nseries else 0,
            "window": window, "horizon": horizon, "ic": rows, "ls": ls}


def _panel_md(label, res) -> list[str]:
    L = [f"## {label}", ""]
    if res.get("error"):
        return L + [f"_skipped — {res['error']}_", ""]
    L += [f"Span {res['span']} · {res['rebalances']} monthly rebalances · ~{res['median_universe']} "
          f"priced names · trailing {res['window']}-month filing window · forward {res['horizon']}d.",
          "", "| signal | mean IC | IC-IR | t_HAC | p | q_FDR | hit | IC h1→h2 | med_act | n |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    rows = res["ic"]
    for c in sorted(rows, key=lambda c: -(rows[c].get("mean_ic") or -9)):
        r = rows[c]
        h = (f"{r.get('ic_h1')}→{r.get('ic_h2')}" if r.get("ic_h1") is not None else "—")
        L.append(f"| {c} | {r.get('mean_ic')} | {r.get('ic_ir')} | {r.get('t_hac')} "
                 f"| {r.get('p_hac')} | {r.get('q_fdr','—')} | {r.get('hit')} | {h} "
                 f"| {r.get('med_active','—')} | {r.get('n')} |")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", "",
          "Dollar-neutral top-vs-bottom-quintile backtest (net of "
          f"{COST_BPS:.0f}bps one-way; only names with a signal; bottom = net sellers):", "",
          "| signal | net Sharpe | cum % | DSR | verdict | bootstrap Sharpe CI | P(SR>0) |",
          "|---|--:|--:|--:|---|---|--:|"]
    for c, b in res["ls"].items():
        L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr','—')} "
                 f"| {b.get('verdict','—')} | {b.get('sharpe_ci','—')} | {b.get('sharpe_gt0_prob','—')} |")
    return L + [""]


def render(panels, args) -> str:
    L = ["# Insider-buying factor — Phase 0 IC scorecard", "",
         "*Generated by `scripts/insider_phase0.py`. The gate: point-in-time insider "
         "buying must rank winners (IC>0, survive BH-FDR) net of the multiple-testing "
         "haircut, or it stays a context leaderboard rather than a scored leg. "
         "Filings enter only once public (causal); routine/opportunistic per "
         "Cohen–Malloy–Pomorski. Judge survivors vs ~0.*", "",
         "Suffixes: `|SN` sector-neutral (within-GICS) · `|act` IC among only the names "
         "with insider activity that month (conditional, `med_act` = median such names). "
         "Bare = full universe (buyers-vs-field).", ""]
    for label, res in panels:
        L += _panel_md(label, res)
    L += ["---", "",
          "**How to read.** `opp_buyers`/`n_buyers` (distinct-insider CLUSTERS) and the "
          "`*_mcap` size-normalised dollars are the constructions the literature backs; "
          "`buy_usd` raw is the size-confounded baseline they must beat. A positive `|act` "
          "IC says *more* buying beats *less* among buyers (the conditional edge); a positive "
          "bare IC says buyers beat the field. `opp_*` (opportunistic) should beat the "
          "all-trades version if the Cohen–Malloy–Pomorski split is doing work. "
          "Insider buying is a LONG signal: the L/S short leg is the least-buying / net-selling "
          "names, so read the long tilt as the primary effect and the short as a weak hedge.", "",
          "**Survivorship vs PIT.** The biased panel scores current index members on the "
          "full ~1500-name universe (incl. mid/small); the PIT panel restricts to the actual "
          "S&P 1500 members on each date (+ recovered delistings). Membership coverage RAMPS — "
          "S&P 500 back to 1996, S&P 400 from ~2012, S&P 600 from ~2020 (the free Wikipedia "
          "changes logs go no further) — so the eligible universe grows ~500 (pre-2012, large "
          "only) → ~920 (2012–19, +mid) → ~1500 (2020+, full). Read the PIT panel with "
          "`--start 2012` (mid-cap era) and note the 2020+ sub-window is where small-caps — "
          "insider buying's natural habitat — finally enter the de-biased test.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=6, help="trailing filing window (months)")
    ap.add_argument("--horizon", type=int, default=63, help="forward return window (trading days)")
    ap.add_argument("--start", type=int, default=0, help="drop rebalances before this year")
    ap.add_argument("--deep", action="store_true",
                    help="use the 1962→ deep-history close matrix (full panel power) "
                         "instead of the ~3y live breadth cache")
    ap.add_argument("--pit", action="store_true",
                    help="point-in-time S&P 500 membership de-bias (run scripts.residual_alpha_pit first)")
    args = ap.parse_args()

    panel = _load_panel()
    if panel.empty:
        print("no insider panel — run collectors.sec_insider.backfill_panel first")
        return 1
    print(f"[panel] {len(panel):,} transactions, {panel['ticker'].nunique()} tickers, "
          f"{panel['filing_date'].min().date()}..{panel['filing_date'].max().date()}")

    closes = _closes_deep() if args.deep else _closes()
    if closes.empty:
        print(f"no {'deep' if args.deep else 'live'} close matrix — run "
              f"{'scripts.residual_alpha_fetch' if args.deep else 'breadth collectors'} first")
        return 1
    membership = None
    if args.pit:
        membership = _load_membership()
        if membership is None:
            print("no PIT membership — run scripts.residual_alpha_pit first")
            return 1
        for fn in ("_closes_delisted.parquet", "_closes_delisted_1500.parquet"):
            delp = config.data_dir() / "breadth" / fn
            if delp.exists():
                closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
                closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    tkr_sector = {t: (s if s and s != "—" else "Other") for t, s in tkr_sector.items()}

    universe = "deep 1962→ (current members)" if args.deep else "live ~3y breadth"
    panels = []
    # Always score the full current-member universe (survivorship-biased, full power).
    print(f"[run] {universe}, full universe (survivorship-biased) · "
          f"window {args.window}mo · horizon {args.horizon}d …")
    panels.append((f"{universe} · full universe (survivorship-biased)",
                   score(panel, closes, tkr_sector, window=args.window,
                         horizon=args.horizon, membership=None, start_year=args.start)))
    # And, when asked, the point-in-time de-biased S&P 500 read.
    if args.pit:
        src = sorted(membership["src"].unique()) if "src" in membership.columns else ["sp500"]
        mlabel = ("PIT S&P 1500 membership (large+mid+small; coverage ramps ~500→920→1500 "
                  "as the 400/600 logs begin 2012/2020)" if set(src) >= {"sp400", "sp600"}
                  else "PIT S&P 500 membership (large-cap only)")
        print(f"[run] {universe}, {mlabel} (+delisted recovery) …")
        panels.append((f"{universe} · {mlabel}, survivorship-debiased",
                       score(panel, closes, tkr_sector, window=args.window,
                             horizon=args.horizon, membership=membership, start_year=args.start)))

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "insider-phase0.md"
    out.write_text(render(panels, args))
    print(f"[report] {out}")
    for label, res in panels:
        if not res.get("error"):
            surv = [c for c in res["ic"] if res["ic"][c].get("survives_fdr")]
            print(f"[verdict] {label[:38]:38s} survive BH-FDR(10%): {', '.join(surv) if surv else 'NONE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
