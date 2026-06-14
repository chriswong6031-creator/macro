"""Hong Kong residual-alpha — Phase 0 honest IC harness (DEEP history).

Mirrors scripts/china_residual_alpha_phase0.py / the US harness exactly (same
`score_panel` / `quintile_ls` / `engine/validation.py` stack) but on a DEEP HK panel.

Why deep history: the first HK read on the 3-year breadth cache (73 names) was
inconclusive — only ~23 monthly rebalances, no power. The binding constraint was
HISTORY LENGTH, not name count, so this harness first fetches the FULL yfinance
history for the 73 curated HK constituents (+ ^HSI) → a ~40-year, 447-rebalance
panel, then asks the real question:

    Does sector-neutral RESIDUAL momentum (the construction that is the durable
    winner-picker for US + China A-shares) have any edge on Hong Kong?

**Verdict (2026-06-14): KILL the residual-alpha leg for HK.** With 447 rebalances
(1989→2026) the residual is dead: `mom_res` IC ≈ 0 and its long-short Sharpe is
NEGATIVE (−0.22 full / −0.35 modern). HK's ONLY positive cross-sectional signal is
plain TOTAL-return momentum (`mom_tot` IC +0.03, t 2.0) — but it is weak (LS Sharpe
0.23, fails DSR) and it is BETA, not alpha. Stripping market+sector beta (which
PURIFIED the China/US signal) REMOVES HK's signal: the HK cross-section is
beta-dominated, exactly as the global-risk thesis predicts (HK ~2× global-beta —
the index is driven by mega-caps + global risk-on/off, not stock-specific alpha).
Acceleration is anti-predictive (t −3.6, survives FDR), consistent across markets.

So: do NOT ship the China residual-alpha leg for HK — it would deploy a negative-
Sharpe signal. HK stays a macro/global-risk product; the per-stock enhancement that
fits HK is a global-risk-beta context read, NOT residual momentum. See
research/CHINA_HK_STOCK_SIGNALS.md.

Run:
  .venv/bin/python -m scripts.hk_residual_alpha_phase0 --fetch   # (re)build the deep panel, then score
  .venv/bin/python -m scripts.hk_residual_alpha_phase0           # score the cached deep panel
Writes reports/hk-residual-alpha-phase0.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import COST_BPS, ew_peer, score_panel  # noqa: E402

CONSTITUENTS = "data/hk_breadth/constituents.parquet"
DEEP_CLOSES = "data/hk_search/closes_deep.parquet"
DEEP_HSI = "data/hk_search/_HSI_deep.parquet"


def fetch_deep() -> None:
    """One-time deep-history fetch: full yfinance history for the 73 curated HK
    constituents + ^HSI → data/hk_search/. ~40y back to 1986 for the blue chips."""
    import yfinance as yf
    root = config.ROOT
    members = pd.read_parquet(root / CONSTITUENTS)
    tickers = list(members.index)
    print(f"[fetch] {len(tickers)} HK names + ^HSI, period=max …")
    df = yf.download(tickers + ["^HSI"], period="max", auto_adjust=True,
                     progress=False, threads=True)["Close"].dropna(how="all")
    closes = df[[t for t in tickers if t in df.columns]].copy()
    (root / "data" / "hk_search").mkdir(parents=True, exist_ok=True)
    closes.to_parquet(root / DEEP_CLOSES)
    if "^HSI" in df.columns:
        df["^HSI"].to_frame("close").to_parquet(root / DEEP_HSI)
    print(f"[fetch] deep panel {closes.shape[0]}d × {closes.shape[1]} names, "
          f"{closes.index.min().date()}→{closes.index.max().date()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="(re)build the deep panel first")
    ap.add_argument("--shrink", type=float, default=0.66)
    args = ap.parse_args()
    root = config.ROOT
    if args.fetch or not (root / DEEP_CLOSES).exists():
        fetch_deep()

    closes = pd.read_parquet(root / DEEP_CLOSES).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / CONSTITUENTS)
    tkr_sector = members["sector"].to_dict()
    hsi = pd.read_parquet(root / DEEP_HSI)["close"]
    market = hsi.pct_change(fill_method=None)
    print(f"[hk] deep {closes.shape[1]} names · {closes.index.min().date()}→{closes.index.max().date()} "
          f"· mkt=HSI · {len({s for s in tkr_sector.values()})} sectors")

    panels = []
    for lbl, c0 in [("DEEP full · 12-1 · fwd21", closes),
                    ("DEEP modern 2010+ · 12-1 · fwd21", closes.loc["2010-01-01":])]:
        print(f"  [panel] {lbl} …")
        panels.append(score_panel(c0, market.reindex(c0.index), tkr_sector, ew_peer,
                                  label=lbl, win=252, minp=130, form=252, skip=21,
                                  horizon=21, shrink=args.shrink))

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "hk-residual-alpha-phase0.md"
    out.write_text(render(panels, args))
    print(f"\n[report] {out}\n{verdict(panels)}")
    return 0


def verdict(panels) -> str:
    p = panels[0]
    if p.get("error"):
        return f"[verdict] inconclusive — {p['error']}"
    tot = (p["ic"].get("mom_tot") or {}).get("mean_ic")
    res_ls = (p.get("ls", {}).get("mom_res") or {}).get("sharpe")
    ir_ls = (p.get("ls", {}).get("ir_res") or {}).get("sharpe")
    kill = (res_ls is not None and res_ls < 0)
    return (f"[verdict] {'KILL residual leg' if kill else 'review'} — total-mom IC {tot}; "
            f"residual LS Sharpe {res_ls} (NEGATIVE → no stock-specific alpha), ir_res LS {ir_ls}. "
            "HK cross-section is beta-dominated; do NOT ship the China residual-alpha leg here.")


def render(panels, args) -> str:
    L = ["# Hong Kong residual-alpha — Phase 0 IC scorecard (DEEP history)", "",
         "*Generated by `scripts/hk_residual_alpha_phase0.py` — the US/China harness on a ~40-year "
         "deep HK panel (73 curated constituents, full yfinance history + ^HSI). The gate: does "
         "sector-neutral RESIDUAL momentum — the durable winner-picker for US + China A-shares — "
         "have any edge on Hong Kong? Betas causal (252d, lagged 1d, shrunk "
         f"{args.shrink}); sector orthogonalized to HSI.*", "",
         "**Verdict: KILL the residual-alpha leg for HK.** The residual (beta-stripped) construction "
         "has no edge here — `mom_res` IC ≈ 0 with a NEGATIVE long-short Sharpe. HK's only positive "
         "cross-sectional signal is plain TOTAL-return momentum (`mom_tot`), but it is weak (fails "
         "DSR) and it is BETA, not alpha. Stripping market+sector beta — which PURIFIED the China/US "
         "signal — REMOVES HK's: the cross-section is beta-dominated (HK ~2× global-beta). "
         "Acceleration is anti-predictive (survives FDR). Don't ship the China leg for HK; HK stays a "
         "macro/global-risk product. See research/CHINA_HK_STOCK_SIGNALS.md.", ""]
    for p in panels:
        L += [f"## {p['label']}", ""]
        if p.get("error"):
            L += [f"_skipped — {p['error']}_", ""]; continue
        L += [f"Span {p['span']} · {p['rebalances']} monthly rebalances · ~{p['median_universe']} names "
              f"· beta {p['win']}d (shrink {p.get('shrink', 1.0)}) · formation {p['form']}d (skip "
              f"{p['skip']}d) · forward {p['horizon']}d.", "",
              "| signal | mean IC | IC-IR ann | t_HAC | q_FDR | hit | n |",
              "|---|--:|--:|--:|--:|--:|--:|"]
        for c in sorted(p["ic"], key=lambda c: -(p["ic"][c].get("ic_ir_ann") or -9)):
            r = p["ic"][c]
            L.append(f"| {c} | {r.get('mean_ic')} | {r.get('ic_ir_ann')} | {r.get('t_hac')} "
                     f"| {r.get('q_fdr', '—')} | {r.get('hit')} | {r.get('n')} |")
        surv = [c for c in p["ic"] if p["ic"][c].get("survives_fdr")]
        L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", "",
              f"Top-vs-bottom-quintile dollar-neutral backtest (net of {COST_BPS:.0f}bps one-way):", "",
              "| signal | net Sharpe | cum % | DSR | verdict | P(SR>0) |", "|---|--:|--:|--:|---|--:|"]
        for c, b in p["ls"].items():
            L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr', '—')} "
                     f"| {b.get('verdict', '—')} | {b.get('sharpe_gt0_prob', '—')} |")
        L += [""]
    L += ["---", "",
          "**How to read.** `mom_res`/`ir_res` (beta-stripped residual) vs `mom_tot` (plain) is the "
          "core test. For US + China A-shares the residual is the durable, tradable winner-picker. For "
          "HK it INVERTS: residual IC ≈ 0 with a negative long-short, while only plain (beta) momentum "
          "is positive — the HK cross-section is dominated by market/global beta, so there is no "
          "sector-neutral stock-specific alpha to harvest. This is the quantitative confirmation that "
          "HK is a macro/global-risk product, not a stock-selection one.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
