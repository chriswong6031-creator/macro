"""Wikipedia-attention factor — Phase 0 honest IC/FDR/DSR harness.

The HARD GATE before the offshore-attention z is allowed anywhere near production
scoring: does an abnormal Wikimedia-pageviews spike add cross-sectional return-
predictive information INCREMENTALLY over the named incumbents — net of the multiple-
testing and Deflated-Sharpe haircuts the rest of the book is held to? The chip already
ships as DISPLAY-ONLY (research/WIKI_ATTENTION_CHIP_SPEC.md); this decides whether the
SIGNAL ever earns a scored leg. Expected verdict: FAIL → permanent display.

Honest prior (Da-Engelberg-Gao 2011): retail attention precedes SHORT-horizon price
REVERSAL, concentrated in small/illiquid names our liquid universe excludes, and decayed
post-GME. So the 5d IC, if anything, should be NEGATIVE (a fade), not a tradable long.

Incumbents the attention z must beat incrementally:
  * momentum   — a 12-1 cross-sectional momentum proxy from the close matrix (the
                 residual-alpha leg's family); attention-z is orthogonalized against it
                 per date and the IC re-run on the residual.
  * VIX-regime — a TIME-SERIES conditioner: IC recomputed within low/mid/high VIX
                 terciles (does the attention effect survive in calm vs stressed tapes).
  * NDI        — NO per-ticker news-diffusion index exists in this repo (grep-confirmed);
                 stated here and NOT invented. Tested vs momentum + VIX-regime only.

API-window caveat: /per-article serves from 2015-07-01, and the live close matrix is only
~3y deep, so the backtest span is short → limited statistical power / DSR n. The deep
matrix (--deep) extends closes but pageviews still floor at 2015.

Run:
  .venv/bin/python -m scripts.wiki_attention_phase0
  .venv/bin/python -m scripts.wiki_attention_phase0 --deep
Writes reports/wiki-attention-phase0.md. No commit, no site build — pure harness.
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

from engine.attention import causal_z_series, load_panel  # noqa: E402
from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from engine.validation import (benjamini_hochberg, block_bootstrap_ci,  # noqa: E402
                               deflated_sharpe, dsr_verdict, ic_summary,
                               rank_ic, ret_moments)
from lib import config  # noqa: E402

HORIZONS = (5, 21, 63)       # attention is short-horizon — 5d is the key test
COST_BPS = 5.0               # single-name one-way, charged on quintile turnover


def _closes_deep() -> pd.DataFrame:
    p = config.data_dir() / "breadth" / "_closes_deep.parquet"
    return pd.read_parquet(p).sort_index() if p.exists() else pd.DataFrame()


def _vix() -> pd.Series:
    p = config.data_dir() / "yahoo" / "_VIX.parquet"
    if not p.exists():
        return pd.Series(dtype=float)
    v = pd.read_parquet(p)
    col = "close" if "close" in v.columns else v.columns[0]
    return v[col].sort_index()


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


def _split_half_ic(per_date_ic) -> dict:
    s = pd.Series(per_date_ic).dropna()
    if len(s) < 12:
        return {}
    mid = len(s) // 2
    return {"ic_h1": round(float(s.iloc[:mid].mean()), 4),
            "ic_h2": round(float(s.iloc[mid:].mean()), 4)}


def build_z_panel(panel, dates, cfg) -> pd.DataFrame:
    """Wide causal-z panel (trading dates × tickers) from the daily views parquets."""
    cols = {}
    zw, rd = int(cfg.get("z_window", 90)), int(cfg.get("recent_days", 5))
    for tk, df in panel.items():
        if df is None or "views" not in getattr(df, "columns", []):
            continue
        z = causal_z_series(df["views"], z_window=zw, recent_days=rd)
        cols[tk] = z.reindex(dates)
    return pd.DataFrame(cols) if cols else pd.DataFrame(index=dates)


def momentum_panel(closes, lookback=252, gap=21) -> pd.DataFrame:
    """12-1 month total-return momentum proxy (the residual-alpha leg's family)."""
    return closes.shift(gap) / closes.shift(lookback) - 1.0


def _xs_resid(z_row: pd.Series, x_row: pd.Series) -> pd.Series:
    """Cross-sectional OLS residual of z on x (single date), causal by construction."""
    j = pd.concat([z_row.rename("z"), x_row.rename("x")], axis=1).dropna()
    if len(j) < 10 or float(j["x"].var()) == 0:
        return pd.Series(dtype=float)
    b = float(np.cov(j["x"], j["z"])[0, 1] / j["x"].var())
    a = float(j["z"].mean() - b * j["x"].mean())
    return j["z"] - (a + b * j["x"])


def quintile_ls(R, sig, grid, n_trials):
    """Dollar-neutral top-vs-bottom-quintile L/S on a z panel, EW, monthly, net of cost."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        s = sig.loc[d].dropna() if d in sig.index else pd.Series(dtype=float)
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
    out = {"sharpe": round(float(net.mean() / net.std() * np.sqrt(252)), 2) if net.std() else None,
           "cum_pct": round(float(((1 + net).prod() - 1) * 100), 1),
           "n_days": int(net.notna().sum())}
    mom = ret_moments(net)
    if mom:
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=max(n_trials, 1))
        if dsr:
            out["dsr"] = dsr["dsr"]
            out["verdict"] = dsr_verdict(dsr["dsr"])
    bc = block_bootstrap_ci(net, ann=252)
    if bc:
        out["sharpe_ci"] = bc["sharpe_ci"]
        out["sharpe_gt0_prob"] = bc["sharpe_gt0_prob"]
    return out


def score_all(zpanel, closes, mom, vix, tkr_sector):
    """IC rows across {raw, |SN, |resid-mom} × HORIZONS + a VIX-regime breakdown."""
    sec = pd.Series(tkr_sector).reindex(closes.columns)
    rows, pvals, vix_rows, ls = {}, {}, {}, {}
    resid_panels = {}
    spans = {}
    for h in HORIZONS:
        grid = [d for d in month_grid(closes.index, h) if d in zpanel.index]
        if len(grid) < 8:
            continue
        spans[h] = f"{grid[0].date()}..{grid[-1].date()} ({len(grid)} rebal)"
        fwd = closes.pct_change(h, fill_method=None).shift(-h)
        vg = vix.reindex(grid).dropna()
        q1, q2 = (vg.quantile(1 / 3), vg.quantile(2 / 3)) if len(vg) >= 6 else (np.nan, np.nan)
        ic_raw, ic_sn, ic_res = [], [], []
        per_vix = {"low": [], "mid": [], "high": []}
        resid_panel = {}
        for d in grid:
            if d not in fwd.index:
                continue
            fr = fwd.loc[d].dropna()
            if len(fr) < 10:
                continue
            z = zpanel.loc[d].reindex(fr.index)
            ic_raw.append(rank_ic(z, fr))
            zn = z - z.groupby(sec.reindex(fr.index)).transform("mean")
            ic_sn.append(rank_ic(zn, fr))
            m = mom.loc[d].reindex(fr.index) if d in mom.index else pd.Series(dtype=float)
            res = _xs_resid(z, m)
            resid_panel[d] = res
            ic_res.append(rank_ic(res.reindex(fr.index), fr) if len(res) else np.nan)
            if np.isfinite(q1) and d in vix.index:
                vv = float(vix.loc[d])
                b = "low" if vv <= q1 else "high" if vv > q2 else "mid"
                per_vix[b].append(rank_ic(z, fr))
        resid_panels[h] = pd.DataFrame(resid_panel).T if resid_panel else pd.DataFrame()
        for tag, series in (("raw", ic_raw), ("SN", ic_sn), ("resid-mom", ic_res)):
            summ = ic_summary(pd.Series(series).dropna(), periods_per_year=12)
            if summ.get("n", 0) >= 6:
                summ.update(_split_half_ic(series))
                key = f"{h}d:{tag}"
                rows[key] = summ
                if summ.get("p_hac") is not None:
                    pvals[key] = summ["p_hac"]
        for b in ("low", "mid", "high"):
            s = pd.Series(per_vix[b]).dropna()
            if len(s) >= 6:
                vix_rows[f"{h}d:VIX-{b}"] = ic_summary(s, periods_per_year=12)

    for k, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[k]["q_fdr"] = q["q"]
        rows[k]["survives_fdr"] = q["reject"]

    # DSR L/S on the momentum-residual z (the incremental signal), per horizon.
    R = closes.pct_change(fill_method=None)
    n_trials = max(len(rows), 1)
    for h in HORIZONS:
        rp = resid_panels.get(h)
        if rp is None or rp.empty:
            continue
        grid = [d for d in month_grid(closes.index, h) if d in rp.index]
        if len(grid) >= 8:
            ls[f"{h}d:resid-mom"] = quintile_ls(R, rp, grid, n_trials)
    return {"ic": rows, "vix": vix_rows, "ls": ls, "spans": spans}


def render(res, meta) -> str:
    L = ["# Wikipedia-attention factor — Phase 0 IC scorecard", "",
         "*Generated by `scripts/wiki_attention_phase0.py`. The gate: abnormal offshore "
         "(en.wikipedia) pageview attention must rank forward winners INCREMENTALLY over "
         "momentum + within VIX regime, surviving BH-FDR and the Deflated-Sharpe haircut — "
         "or it stays a DISPLAY-ONLY caution chip. Honest prior (Da-Engelberg-Gao): "
         "attention precedes short-horizon REVERSAL, so a negative 5d IC is a fade caution, "
         "not a tradable long. Judge survivors vs ~0.*", "",
         f"Panel: {meta['n_tickers']} tickers with resolved Wikipedia articles · close matrix "
         f"`{meta['universe']}` · pageviews floor 2015-07-01 (short span → limited power). "
         "NDI incumbent: none in-repo (grep-confirmed) → tested vs momentum + VIX-regime only.",
         "",
         "Suffixes: `raw` full universe · `|SN` sector-neutral (within-GICS) · `resid-mom` "
         "the IC of the attention z AFTER cross-sectionally orthogonalizing it against the "
         "12-1 momentum proxy (the incremental test).", "",
         "| signal | mean IC | IC-IR | t_HAC | p | q_FDR | hit | IC h1→h2 | n |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    rows = res["ic"]
    for c in sorted(rows, key=lambda c: (int(c.split("d:")[0]), c)):
        r = rows[c]
        h = f"{r.get('ic_h1')}→{r.get('ic_h2')}" if r.get("ic_h1") is not None else "—"
        L.append(f"| {c} | {r.get('mean_ic')} | {r.get('ic_ir')} | {r.get('t_hac')} "
                 f"| {r.get('p_hac')} | {r.get('q_fdr','—')} | {r.get('hit')} | {h} | {r.get('n')} |")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", ""]

    if res["vix"]:
        L += ["### IC within VIX regime (raw z)", "",
              "| bucket | mean IC | t_HAC | p | hit | n |", "|---|--:|--:|--:|--:|--:|"]
        for c in sorted(res["vix"], key=lambda c: (int(c.split("d:")[0]), c)):
            r = res["vix"][c]
            L.append(f"| {c} | {r.get('mean_ic')} | {r.get('t_hac')} | {r.get('p_hac')} "
                     f"| {r.get('hit')} | {r.get('n')} |")
        L.append("")

    if res["ls"]:
        L += ["### Dollar-neutral top-vs-bottom-quintile L/S on the momentum-residual z",
              f"(net of {COST_BPS:.0f}bps one-way; DSR n_trials = full IC family count)", "",
              "| signal | net Sharpe | cum % | DSR | verdict | bootstrap Sharpe CI | P(SR>0) |",
              "|---|--:|--:|--:|---|---|--:|"]
        for c, b in res["ls"].items():
            L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr','—')} "
                     f"| {b.get('verdict','—')} | {b.get('sharpe_ci','—')} | {b.get('sharpe_gt0_prob','—')} |")
        L.append("")

    L += ["---", "",
          "**How to read.** A positive incremental (`resid-mom`) IC surviving BH-FDR would "
          "be the only result that could promote this past display-only. The prior is it "
          "does NOT: attention is a crowding/extension marker whose return content is a weak, "
          "short-horizon, small-cap reversal our liquid universe and momentum leg already "
          "absorb. A *negative* 5d IC is consistent with the Da-Engelberg-Gao fade and is "
          "still a CAUTION, not a tradable short. Ship as display regardless.",
          "",
          "**Caveats.** (1) Span is short (pageviews from 2015; live closes ~3y) → low DSR "
          "power. (2) Momentum here is a 12-1 proxy computed from closes, not the full "
          "residual-alpha panel (a snapshot on disk), so the incremental test is a lower "
          "bound on what the production momentum leg would absorb. (3) en.wikipedia counts "
          "offshore attention only — the chip carries that caveat for CN/HK names.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true",
                    help="use the deep-history close matrix instead of the ~3y live breadth")
    args = ap.parse_args()

    panel = load_panel()
    if not panel:
        print("no attention panel — run collectors.wiki_pageviews first "
              "(needs profiles.parquet wiki_title populated)")
        return 1
    print(f"[panel] {len(panel)} tickers with daily pageviews")

    closes = _closes_deep() if args.deep else _closes()
    if closes is None or closes.empty:
        print(f"no {'deep' if args.deep else 'live'} close matrix")
        return 1
    cfg = config.load().get("wiki_pageviews", {}) or {}
    zpanel = build_z_panel(panel, closes.index, cfg)
    zpanel = zpanel.dropna(how="all")
    if zpanel.empty:
        print("z panel empty after alignment (insufficient pageview history vs closes)")
        return 1

    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    tkr_sector = {t: (s if s and s != "—" else "Other") for t, s in tkr_sector.items()}
    mom = momentum_panel(closes)
    vix = _vix()

    res = score_all(zpanel, closes, mom, vix, tkr_sector)
    meta = {"n_tickers": int(zpanel.notna().any().sum()),
            "universe": "deep 1962→ (current members)" if args.deep else "live ~3y breadth"}

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "wiki-attention-phase0.md"
    out.write_text(render(res, meta))
    print(f"[report] {out}")
    surv = [c for c in res["ic"] if res["ic"][c].get("survives_fdr")]
    print(f"[verdict] survive BH-FDR(10%): {', '.join(surv) if surv else 'NONE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
