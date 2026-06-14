"""Residual-alpha momentum — Phase 0 honest IC harness (research/RESIDUAL_ALPHA_MOMENTUM.md).

The HARD GATE before any residual-alpha UI: does ranking stocks on their
beta-stripped residual actually predict forward returns BETTER than plain
total-return momentum — on THIS universe, where the existing value/quality/
low-vol composite already fails BH-FDR (SP_VECTOR_VIABILITY.md §3)?

Construction (per stock, causal — betas lagged one day):
    r_i = a + b_m * m + b_s * s~ + e_i
  m   = market return (SPY); s~ = the stock's GICS-sector return ORTHOGONALIZED
  to the market (sector move beyond its market beta). Because s~ ⟂ m, the two
  slopes decouple into univariate rolling betas, so e_i (the residual = "alpha")
  is exact without a 2x2 solve. EW peer-basket sector for the broad panel; SPDR
  sector ETF for the deep-history cross-check.

Candidate signals (cross-sectional, monthly rebalance):
  mom_tot  total return over the formation window (classic, skip last month)
  mom_res  residual sum over the window               (residual momentum amplitude)
  ir_res   residual mean/std over the window          (residual INFORMATION RATIO — headline)
  rev_st   last-`skip`-day return                      (short-term reversal CONTROL — expect IC<0)
  acc_res  recent vs prior residual trend             (acceleration — experimental)
Each is scored raw AND sector-neutral (demeaned within GICS sector). IC = per-date
cross-sectional rank corr vs the forward return; aggregated to mean IC / IC-IR /
Newey-West t / BH-FDR. The headline momentum signals also get a dollar-neutral
top-vs-bottom-quintile net-of-cost backtest with a Deflated Sharpe + bootstrap CI.

Run:
  .venv/bin/python -m scripts.residual_alpha_phase0                 # broad live panel
  .venv/bin/python -m scripts.residual_alpha_phase0 --deep          # + deep-history (SPDR) cross-check
  .venv/bin/python -m scripts.residual_alpha_phase0 --beta-win 252 --form 252 --horizon 63

Writes reports/residual-alpha-phase0.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")   # rolling-beta on truncated history emits benign numpy warnings

from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from engine.validation import (benjamini_hochberg, block_bootstrap_ci,  # noqa: E402
                               deflated_sharpe, dsr_verdict, ic_summary,
                               rank_ic, ret_moments)
from lib import config, store  # noqa: E402

COST_BPS = 5.0   # single-name one-way (spread+impact), charged on quintile turnover

# GICS sector name (constituents.parquet) -> SPDR ETF, for the deep-history panel
SECTOR_ETF = {
    "Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}


def _yahoo_ret(sym: str, index: pd.DatetimeIndex) -> pd.Series | None:
    df = store.read("yahoo", sym)
    if df is None or "close" not in df.columns:
        return None
    return df["close"].pct_change(fill_method=None).reindex(index)


def _closes_deep() -> pd.DataFrame:
    """The one-time deep-history broad matrix (scripts/residual_alpha_fetch.py)."""
    p = config.data_dir() / "breadth" / "_closes_deep.parquet"
    return pd.read_parquet(p).sort_index() if p.exists() else pd.DataFrame()


def _load_membership() -> pd.DataFrame | None:
    """Point-in-time S&P 500 membership intervals (scripts/residual_alpha_pit.py)."""
    p = config.data_dir() / "breadth" / "sp500_pit_membership.parquet"
    if not p.exists():
        return None
    m = pd.read_parquet(p)
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"])
    return m


def _eligible(membership: pd.DataFrame, d) -> set:
    """Tickers that were actual index members on date d (any interval covers d)."""
    d = pd.Timestamp(d)
    mask = (membership["start_date"] <= d) & (
        membership["end_date"].isna() | (membership["end_date"] >= d))
    return set(membership.loc[mask, "ticker"])


def _shrink(beta: pd.DataFrame, w: float) -> pd.DataFrame:
    """Vasicek-lite: w*raw + (1-w)*cross-sectional-mean-that-day. w>=1 → no-op.
    Pulls noisy per-stock betas toward the prior so the residual isn't poisoned by
    a handful of badly-estimated betas (the short-window-beta trap, §5)."""
    if w is None or w >= 1.0:
        return beta
    prior = beta.mean(axis=1)
    return beta.mul(w).add(prior.mul(1.0 - w), axis=0)


def _causal_beta(y, x, win: int, minp: int):
    """Rolling cov(y,x)/var(x), lagged one day (uses only prior-window data)."""
    return (y.rolling(win, min_periods=minp).cov(x)
            .div(x.rolling(win, min_periods=minp).var(), axis=0)).shift(1)


def build_residuals(closes, market, tkr_sector, sector_ret, win, minp, shrink=1.0):
    """Per-stock causal residual e_i = r_i - b_m*m - b_s*s~  (s~ ⟂ m). Betas are
    rolling, lagged 1d, and optionally shrunk toward the cross-section (`shrink`<1)."""
    R = closes.pct_change(fill_method=None)
    m = market.reindex(R.index)
    var_m = m.rolling(win, min_periods=minp).var()
    beta_m = _shrink(R.rolling(win, min_periods=minp).cov(m).div(var_m, axis=0).shift(1), shrink)
    mkt_comp = beta_m.mul(m, axis=0)

    eps = pd.DataFrame(index=R.index, columns=R.columns, dtype=float)
    for sec in sorted(set(tkr_sector.values())):
        cols = [t for t in R.columns if tkr_sector.get(t) == sec]
        if not cols:
            continue
        s_raw = sector_ret(sec, cols, R)            # EW-peer or SPDR sector return
        if s_raw is None:
            continue
        beta_sm = _causal_beta(s_raw, m, win, minp)
        s_orth = s_raw - beta_sm * m                # sector move beyond market
        sub = R[cols]
        beta_s = _shrink(_causal_beta(sub, s_orth, win, minp), shrink)
        eps[cols] = sub - mkt_comp[cols] - beta_s.mul(s_orth, axis=0)
    return R, eps


def signal_matrices(R, eps, form, skip):
    """The five candidate signals as date×ticker matrices."""
    mp = max(form // 2, 20)
    half = max(form // 2, 21)
    return {
        "mom_tot": R.shift(skip).rolling(form, min_periods=mp).sum(),
        "mom_res": eps.shift(skip).rolling(form, min_periods=mp).sum(),
        "ir_res": (eps.shift(skip).rolling(form, min_periods=mp).mean()
                   / eps.shift(skip).rolling(form, min_periods=mp).std()),
        "rev_st": R.rolling(skip, min_periods=max(skip // 2, 5)).sum(),
        "acc_res": (eps.rolling(half, min_periods=mp).mean()
                    - eps.shift(half).rolling(half, min_periods=mp).mean()),
    }


def month_grid(index, warmup, horizon):
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if not len(d):
            continue
        loc = index.get_loc(d[-1])
        if loc >= warmup and loc + horizon < len(index):
            out.append(d[-1])
    return out


def score_panel(closes, market, tkr_sector, sector_ret, *, label, win, minp,
                form, skip, horizon, shrink=1.0, membership=None):
    R, eps = build_residuals(closes, market, tkr_sector, sector_ret, win, minp, shrink)
    sigs = signal_matrices(R, eps, form, skip)
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)
    sec = pd.Series(tkr_sector).reindex(R.columns)

    grid = month_grid(R.index, warmup=win + skip + form, horizon=horizon)
    if len(grid) < 6:
        return {"label": label, "error": f"grid too short ({len(grid)})"}

    cand = list(sigs)                                   # raw + sector-neutral variants
    ic = {c: [] for c in cand} | {f"{c}|SN": [] for c in cand}
    nseries = []
    for d in grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if membership is not None:                      # PIT: only names in the index then
            fr = fr[fr.index.isin(_eligible(membership, d))]
        if len(fr) < 10:
            continue
        nseries.append(int(len(fr)))
        for c in cand:
            if d not in sigs[c].index:
                continue
            s = sigs[c].loc[d]
            if membership is not None:
                s = s[s.index.isin(fr.index)]
            ic[c].append(rank_ic(s, fr))
            sn = s - s.groupby(sec).transform("mean")  # within-sector demeaned
            ic[f"{c}|SN"].append(rank_ic(sn, fr))

    rows, pvals = {}, {}
    for c, series in ic.items():
        summ = ic_summary(pd.Series(series).dropna(), periods_per_year=12)
        if summ.get("n", 0) >= 6:
            rows[c] = summ
            if summ.get("p_hac") is not None:
                pvals[c] = summ["p_hac"]
    for c, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[c]["q_fdr"] = q["q"]
        rows[c]["survives_fdr"] = q["reject"]

    # dollar-neutral top-vs-bottom-quintile backtest for the momentum signals
    ls = {c: quintile_ls(R, sigs[c], grid, horizon, n_trials=len(rows), membership=membership)
          for c in ("mom_tot", "mom_res", "ir_res")}

    return {"label": label, "span": f"{grid[0].date()}..{grid[-1].date()}",
            "rebalances": len(grid), "median_universe": int(np.median(nseries)) if nseries else 0,
            "win": win, "form": form, "skip": skip, "horizon": horizon, "shrink": shrink,
            "ic": rows, "ls": ls}


def quintile_ls(R, sig, grid, horizon, n_trials, membership=None):
    """Long top-quintile / short bottom-quintile, EW, monthly rebalance, net of cost."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        s = sig.loc[d].dropna() if d in sig.index else pd.Series(dtype=float)
        if membership is not None:                       # PIT: only members on date d
            s = s[s.index.isin(_eligible(membership, d))]
        if len(s) < 25:
            continue
        hi, lo = s.quantile(0.8), s.quantile(0.2)
        top, bot = s[s >= hi].index, s[s <= lo].index
        if len(top) and len(bot):
            w.loc[d, top] = 1.0 / len(top)
            w.loc[d, bot] = -1.0 / len(bot)
    w = w.replace(0.0, np.nan).ffill().fillna(0.0)
    pos = w.shift(1)
    # clip daily returns at ±50% — kills garbage ticks in thin/delisted yahoo
    # history that otherwise blow the compounded LS to ±inf (rank-IC is immune).
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


# --------------------------------------------------------------------------- #
def ew_peer(sec, cols, R):
    return R[cols].mean(axis=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--beta-win", type=int, default=126, help="rolling beta window (d)")
    ap.add_argument("--form", type=int, default=126, help="formation window (d)")
    ap.add_argument("--skip", type=int, default=21, help="skip-recent window (d)")
    ap.add_argument("--horizon", type=int, default=21, help="forward return window (d)")
    ap.add_argument("--closes", choices=["live", "deep"], default="live",
                    help="'live' 3yr breadth cache, or 'deep' (run scripts.residual_alpha_fetch first)")
    ap.add_argument("--shrink", type=float, default=1.0,
                    help="beta shrinkage weight w toward the cross-section (1.0=off; try 0.66)")
    ap.add_argument("--spdr", action="store_true",
                    help="also run the 110-name deep-history SPDR-sector cross-check")
    ap.add_argument("--start", type=int, default=0,
                    help="drop closes before this year (apples-to-apples era comparison)")
    ap.add_argument("--pit", action="store_true",
                    help="point-in-time S&P 500 membership de-bias (run scripts.residual_alpha_pit first)")
    args = ap.parse_args()
    minp = max(args.beta_win // 2, 40)

    closes = _closes_deep() if args.closes == "deep" else _closes()
    if closes.empty:
        print(f"no {args.closes} close matrix — run "
              f"{'scripts.residual_alpha_fetch' if args.closes == 'deep' else 'breadth collectors'}")
        return 1
    membership = None
    if args.pit:
        membership = _load_membership()
        if membership is None:
            print("no PIT membership — run scripts.residual_alpha_pit first")
            return 1
        delp = config.data_dir() / "breadth" / "_closes_delisted.parquet"
        if delp.exists():                              # fold in the resolvable delisted names
            closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
            closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    if args.start:
        closes = closes.loc[closes.index >= f"{args.start}-01-01"]
    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    if args.pit:                                       # delisted names lack GICS -> 'Other' bucket
        tkr_sector = {t: (s if s != "—" else "Other") for t, s in tkr_sector.items()}
    spy = _yahoo_ret("SPY", closes.index)

    panels = []
    tag = "DEEP-broad" if args.closes == "deep" else "BROAD live"
    pit_lbl = " · PIT membership (survivorship-reduced)" if args.pit else (
        " (survivorship-biased)" if args.closes == "deep" else "")
    print(f"[panel] {tag} universe (EW-peer sector, shrink {args.shrink}"
          f"{', PIT' if args.pit else ''}) …")
    panels.append(score_panel(closes, spy, tkr_sector, ew_peer,
                              label=f"{tag} universe · EW-peer sector" + pit_lbl,
                              win=args.beta_win, minp=minp, form=args.form, skip=args.skip,
                              horizon=args.horizon, shrink=args.shrink, membership=membership))

    if args.spdr:
        print("[panel] deep-history (data/stocks, SPDR sector) …")
        deep = {}
        sdir = config.data_dir() / "stocks"
        for p in sorted(sdir.glob("*.parquet")):
            t = p.stem
            if tkr_sector.get(t) in SECTOR_ETF:
                df = pd.read_parquet(p)
                if "close" in df.columns:
                    deep[t] = df["close"]
        if len(deep) >= 30:
            dcl = pd.DataFrame(deep).sort_index()
            dcl = dcl.loc[dcl.index >= "2002-01-01"]
            dspy = _yahoo_ret("SPY", dcl.index)
            etf_cache = {s: _yahoo_ret(SECTOR_ETF[s], dcl.index) for s in SECTOR_ETF}

            def spdr_sector(sec, cols, R):
                return etf_cache.get(sec)

            panels.append(score_panel(dcl, dspy, tkr_sector, spdr_sector,
                                      label=f"SPDR-check {len(deep)} names · SPDR sector (survivorship-biased)",
                                      win=252, minp=130, form=max(args.form, 252),
                                      skip=args.skip, horizon=args.horizon, shrink=args.shrink))
        else:
            print(f"  [skip] deep panel — only {len(deep)} names with sector + history")

    report = render(panels, args)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "residual-alpha-phase0.md"
    out.write_text(report)
    print(f"\n[report] {out}")
    return 0


def render(panels, args) -> str:
    L = ["# Residual-alpha momentum — Phase 0 IC scorecard", "",
         "*Generated by `scripts/residual_alpha_phase0.py` (research/RESIDUAL_ALPHA_MOMENTUM.md). "
         "The gate: residual momentum must rank winners (IC>0, survive BH-FDR) AND beat plain "
         "total-return momentum. Betas are causal (lagged 1d); sector orthogonalized to market. "
         "Judge survivors vs ~0.*", ""]
    for p in panels:
        L += [f"## {p['label']}", ""]
        if p.get("error"):
            L += [f"_skipped — {p['error']}_", ""]
            continue
        L += [f"Span {p['span']} · {p['rebalances']} monthly rebalances · ~{p['median_universe']} "
              f"names · beta {p['win']}d (shrink {p.get('shrink', 1.0)}) · formation {p['form']}d "
              f"(skip {p['skip']}d) · forward {p['horizon']}d.", "",
              "| signal | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |",
              "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
        rows = p["ic"]
        for c in sorted(rows, key=lambda c: -(rows[c].get("ic_ir_ann") or -9)):
            r = rows[c]
            L.append(f"| {c} | {r.get('mean_ic')} | {r.get('ic_ir')} | {r.get('ic_ir_ann')} "
                     f"| {r.get('t_hac')} | {r.get('p_hac')} | {r.get('q_fdr','—')} "
                     f"| {r.get('hit')} | {r.get('n')} |")
        surv = [c for c in rows if rows[c].get("survives_fdr")]
        L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", "",
              "Top-vs-bottom-quintile dollar-neutral backtest (net of "
              f"{COST_BPS:.0f}bps one-way):", "",
              "| signal | net Sharpe | cum % | DSR | verdict | bootstrap Sharpe CI | P(SR>0) |",
              "|---|--:|--:|--:|---|---|--:|"]
        for c, b in p["ls"].items():
            L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr','—')} "
                     f"| {b.get('verdict','—')} | {b.get('sharpe_ci','—')} | {b.get('sharpe_gt0_prob','—')} |")
        L += [""]
    L += ["---", "",
          "**How to read.** `mom_res` (beta-stripped) vs `mom_tot` (plain) is the core test; "
          "`ir_res` is the consistency-scaled (info-ratio) headline; `|SN` = sector-neutral "
          "(within-GICS) = the 'winners within a sector' view. `rev_st` (last-month) is the "
          "short frame — a **negative** IC means short-horizon reversal (a contrarian timing "
          "overlay, not a picker); `acc_res` tests acceleration. Use `--closes deep` (1962→) for "
          "power and `--start YYYY` for an apples-to-apples era comparison — momentum decays "
          "post-2000, so the era matters. Deep panels are survivorship-biased (current members), "
          "which inflates momentum: a modern-era FAIL is conservative, a full-history PASS optimistic.",
          ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
