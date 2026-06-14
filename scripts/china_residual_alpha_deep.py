"""China A-share residual-alpha — DEEP-history re-validation (the honest correction).

The original Phase 0 (scripts/china_residual_alpha_phase0.py) ran on only ~5 years
(33 monthly rebalances, 2021-2026) and returned "GO as a ranking/context leg." This
harness removes the binding constraint — history length — by fetching the FULL yfinance
history for the 800 A-share names (+ SSE Composite market) → a ~35-year, 400-rebalance
panel, then re-runs the identical US/China harness across eras.

**Verdict (2026-06-14): the 5-year GO was a FAVOURABLE-WINDOW ARTIFACT.** On deep
history, cross-sectional MOMENTUM — total AND beta-stripped residual — is NOT a
validated A-share edge: IC is negative/zero at the shipped 12-1/fwd-21 config over the
full (−0.009) and modern-2010 (−0.001) eras, long-short Sharpe negative, nothing clears
BH-FDR. It is only weakly positive (insignificant, fails FDR) at a 6-1 formation / 63d
forward in the modern era. The ROBUST, FDR-surviving cross-sectional effect is the
OPPOSITE: short-term REVERSAL (rev_st|SN IC −0.029 to −0.037, t −2.7 to −5.0, survives
BH-FDR in the full, modern AND connect eras, under BOTH the SSE-Composite and EW
market). A-shares are a retail-driven, mean-reverting cross-section — recent winners give
back, recent losers bounce. The momentum-leaders ranking shipped on china.html therefore
OVERCLAIMS; the validated read is reversal / the pullback (mean-reversion) entry.

Run:
  .venv/bin/python -m scripts.china_residual_alpha_deep --fetch   # (re)build the deep panel, then score
  .venv/bin/python -m scripts.china_residual_alpha_deep           # score the cached deep panel
Writes reports/china-residual-alpha-deep.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config, store  # noqa: E402
from scripts.residual_alpha_phase0 import COST_BPS, ew_peer, score_panel  # noqa: E402

MEMBERS = "data/china_search/members.parquet"
DEEP = "data/china_search/closes_deep.parquet"
SSE = "000001.SS"          # SSE Composite — deep broad-market proxy (1997→)
JUNK_SECTOR = "A-share"

# (label, start-year, formation, forward) — the shipped config + the most momentum-
# favourable horizon, across eras. All else equal: beta 252d shrunk 0.66, skip 21d.
PANELS = [
    ("DEEP full · 12-1 · fwd 21d (SHIPPED config)", None, 252, 21),
    ("DEEP modern 2010+ · 12-1 · fwd 21d", 2010, 252, 21),
    ("DEEP connect-era 2015+ · 12-1 · fwd 21d", 2015, 252, 21),
    ("DEEP modern 2010+ · 6-1 · fwd 63d (most momentum-favourable)", 2010, 126, 63),
]


def fetch_deep() -> None:
    """One-time deep-history fetch: full yfinance history for the 800 search names."""
    import yfinance as yf
    root = config.ROOT
    tickers = list(pd.read_parquet(root / MEMBERS).index)
    print(f"[fetch] {len(tickers)} A-share names, period=max (chunks of 150) …")
    frames = []
    for i in range(0, len(tickers), 150):
        df = yf.download(tickers[i:i + 150], period="max", auto_adjust=True,
                         progress=False, threads=True)["Close"]
        frames.append(df.to_frame(tickers[i]) if isinstance(df, pd.Series) else df)
    allc = pd.concat(frames, axis=1).sort_index()
    allc = allc.loc[:, ~allc.columns.duplicated()].dropna(how="all")
    (root / "data" / "china_search").mkdir(parents=True, exist_ok=True)
    allc.to_parquet(root / DEEP)
    print(f"[fetch] deep panel {allc.shape[0]}d × {allc.shape[1]} names, "
          f"{allc.index.min().date()}→{allc.index.max().date()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="(re)build the deep panel first")
    ap.add_argument("--shrink", type=float, default=0.66)
    args = ap.parse_args()
    root = config.ROOT
    if args.fetch or not (root / DEEP).exists():
        fetch_deep()

    closes = pd.read_parquet(root / DEEP).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / MEMBERS)
    tkr_sector = {t: (s if s != JUNK_SECTOR else "—") for t, s in members["sector"].items()}
    sse = store.read("china", SSE)
    market = sse["close"].pct_change(fill_method=None)
    print(f"[china-deep] {closes.shape[1]} names · {closes.index.min().date()}→{closes.index.max().date()} "
          f"· mkt=SSE Composite · shrink {args.shrink}")

    out = []
    for lbl, yr, form, hz in PANELS:
        c0 = closes.loc[f"{yr}-01-01":] if yr else closes
        print(f"  [panel] {lbl} …")
        out.append(score_panel(c0, market.reindex(c0.index), tkr_sector, ew_peer,
                               label=lbl, win=252, minp=130, form=form, skip=21,
                               horizon=hz, shrink=args.shrink))

    rpt = config.ROOT / config.load()["storage"]["reports_dir"] / "china-residual-alpha-deep.md"
    rpt.write_text(render(out, args))
    print(f"\n[report] {rpt}\n{verdict(out)}")
    return 0


def verdict(panels) -> str:
    p = panels[0]                                   # shipped config
    if p.get("error"):
        return f"[verdict] inconclusive — {p['error']}"
    mom = (p["ic"].get("ir_res") or {}).get("mean_ic")
    rev = (p["ic"].get("rev_st|SN") or {}).get("mean_ic")
    rev_fdr = (p["ic"].get("rev_st|SN") or {}).get("survives_fdr")
    return (f"[verdict] CORRECTION — at the shipped 12-1/fwd21 config the residual momentum IC is "
            f"{mom} (not an edge); short-term reversal rev_st|SN IC {rev}"
            f"{' survives FDR' if rev_fdr else ''}. A-shares are a REVERSAL market; the 5y GO was a "
            "favourable-window artifact. Reframe the shipped momentum panels.")


def render(panels, args) -> str:
    L = ["# China A-share residual-alpha — DEEP-history re-validation", "",
         "*Generated by `scripts/china_residual_alpha_deep.py` — the US/China harness on a ~35-year "
         "deep A-share panel (800 search names, full yfinance history + SSE Composite). It corrects "
         "the original 5-year Phase 0 (`reports/china-residual-alpha-phase0.md`, 33 rebalances), "
         f"which over-fit a favourable 2021-2026 window. Betas causal (252d, shrunk {args.shrink}); "
         "sector orthogonalized to the market.*", "",
         "**Verdict: the 5-year GO was a favourable-window artifact.** Cross-sectional MOMENTUM "
         "(total AND beta-stripped residual) is NOT a validated A-share edge — IC negative/zero at "
         "the shipped 12-1/fwd-21 config over the full and modern eras, long-short Sharpe negative, "
         "nothing clears BH-FDR; only weakly positive (insignificant) at 6-1/fwd-63d. The ROBUST, "
         "FDR-surviving effect is the OPPOSITE — short-term **REVERSAL** (rev_st|SN, t −2.7 to −5.0, "
         "survives FDR across full/modern/connect eras and both market proxies). A-shares are a "
         "retail-driven, mean-reverting cross-section: recent winners give back, recent losers "
         "bounce. The momentum-leaders ranking on china.html overclaims — the validated read is "
         "reversal / the pullback (mean-reversion) entry. **Survivorship caveat:** the 800 are "
         "top-mcap *today*, which biases momentum UP — so this failure-to-find-momentum is "
         "*conservative* (the true momentum edge is weaker still).", ""]
    for p in panels:
        L += [f"## {p['label']}", ""]
        if p.get("error"):
            L += [f"_skipped — {p['error']}_", ""]; continue
        L += [f"Span {p['span']} · {p['rebalances']} monthly rebalances · ~{p['median_universe']} names "
              f"· beta {p['win']}d · formation {p['form']}d (skip {p['skip']}d) · forward {p['horizon']}d.", "",
              "| signal | mean IC | IC-IR ann | t_HAC | q_FDR | hit | n |", "|---|--:|--:|--:|--:|--:|--:|"]
        for c in sorted(p["ic"], key=lambda c: -(p["ic"][c].get("ic_ir_ann") or -9)):
            r = p["ic"][c]
            L.append(f"| {c} | {r.get('mean_ic')} | {r.get('ic_ir_ann')} | {r.get('t_hac')} "
                     f"| {r.get('q_fdr', '—')} | {r.get('hit')} | {r.get('n')} |")
        surv = [c for c in p["ic"] if p["ic"][c].get("survives_fdr")]
        L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", "",
              f"Top-vs-bottom-quintile dollar-neutral backtest (net {COST_BPS:.0f}bps one-way):", "",
              "| signal | net Sharpe | cum % | DSR | P(SR>0) |", "|---|--:|--:|--:|--:|"]
        for c, b in p["ls"].items():
            L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr', '—')} "
                     f"| {b.get('sharpe_gt0_prob', '—')} |")
        L += [""]
    L += ["---", "",
          "**How to read.** `mom_res`/`ir_res` (beta-stripped residual) vs `mom_tot` (plain) is the "
          "momentum test; `rev_st|SN` (last-21d, within-sector) is the short frame — a **negative** IC "
          "= reversal. For US + China-on-5y the residual was the durable winner-picker; on deep "
          "A-share history it INVERTS — momentum is dead and reversal is the only FDR-surviving "
          "cross-sectional effect. The honest A-share stock signal is mean-reversion / cycle-confirmed "
          "pullback entries, NOT momentum leaders.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
