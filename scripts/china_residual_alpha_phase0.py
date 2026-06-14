"""China A-share residual-alpha — Phase 0 honest IC harness.

Mirrors scripts/residual_alpha_phase0.py EXACTLY (same `score_panel`, `quintile_ls`,
and `engine/validation.py` stack — rank-IC, IC-IR, Newey-West HAC t, BH-FDR, Deflated
Sharpe, block-bootstrap CI) but points it at the A-share universe we already store:

    data/china_search/closes.parquet   1211d × 800 top-mcap A-shares (2021-06→2026-06)
    data/china_search/members.parquet  ticker → (name, sector)  [Yahoo sectors, 12 buckets]
    data/china/510300.SS.parquet        CSI300 ETF — the cap-weighted market (SPY analog)

The HARD GATE before any A-share residual-alpha UI (identical to the US Phase 0):
does ranking stocks on their beta-AND-sector-stripped residual momentum predict
forward returns, and beat plain total-return momentum, on THIS universe?

Pre-registered gate (same as research/RESIDUAL_ALPHA_MOMENTUM.md §4):
  GO     residual momentum IC>0, beats mom_tot, directionally durable (and ideally
         the LS DSR is respectable). Ship as a ranking/context leg, framed honestly.
  REFINE directionally right but underpowered / mixed across configs.
  KILL   residual IC ≤ 0, or no better than plain total momentum.

A-share priors worth stating up front (so the result is interpreted honestly):
  • RETAIL-DOMINATED → expect short-horizon (`rev_st`) to be a STRONGER negative
    (reversal) than the US; that is itself a usable entry-timing overlay, not a fail.
  • Only ~5y of history → far less power than the US deep panel; treat a clean modern
    PASS as encouraging, a marginal result as "REFINE / fetch deeper history", never
    as a high-conviction standalone-alpha claim.
  • The 800 names are TOP-MCAP TODAY → survivorship-biased (inflates momentum); a weak
    result is therefore conservative.

Run:
  .venv/bin/python -m scripts.china_residual_alpha_phase0
  .venv/bin/python -m scripts.china_residual_alpha_phase0 --ew-market   # EW-market robustness

Writes reports/china-residual-alpha-phase0.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")  # rolling-beta on truncated history emits benign numpy warnings

from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import COST_BPS, ew_peer, score_panel  # noqa: E402

CLOSES = "data/china_search/closes.parquet"
MEMBERS = "data/china_search/members.parquet"
MARKET_ETF = "data/china/510300.SS.parquet"   # CSI300 ETF — cap-weighted A-share market
JUNK_SECTOR = "A-share"                         # yfinance fallback bucket → route to ignore


def load_china(ew_market: bool):
    root = config.ROOT
    closes = pd.read_parquet(root / CLOSES).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / MEMBERS)
    # ticker → sector; drop the junk 'A-share' fallback so the engine ignores those
    # names (sector '—' is the engine's skip sentinel — keeps the cross-section clean).
    tkr_sector = {t: (s if s != JUNK_SECTOR else "—")
                  for t, s in members["sector"].items()}
    names = {t: str(n) for t, n in members["name"].items()}

    if ew_market:
        market = closes.pct_change(fill_method=None).mean(axis=1)
        mkt_lbl = "EW-mean of universe"
    else:
        csi = pd.read_parquet(root / MARKET_ETF)["close"]
        market = csi.pct_change(fill_method=None).reindex(closes.index)
        mkt_lbl = "CSI300 ETF (510300.SS)"
    return closes, market, tkr_sector, names, mkt_lbl


# Configs to sweep: the 12-1 the US engine ships, a faster 6-1 (A-share cycles run
# hotter), and the 12-1 at a 63d forward horizon. Each is a full IC + LS backtest.
CONFIGS = [
    dict(win=252, form=252, skip=21, horizon=21, tag="12-1 · fwd 21d (durable / ships)"),
    dict(win=126, form=126, skip=21, horizon=21, tag="6-1 · fwd 21d (faster A-share horizon)"),
    dict(win=252, form=252, skip=21, horizon=63, tag="12-1 · fwd 63d"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ew-market", action="store_true",
                    help="use EW-mean-of-universe as the market instead of CSI300 ETF (robustness)")
    ap.add_argument("--shrink", type=float, default=0.66,
                    help="Vasicek-lite beta shrink toward the cross-section (1.0=off)")
    args = ap.parse_args()

    closes, market, tkr_sector, names, mkt_lbl = load_china(args.ew_market)
    n_sec = len({s for s in tkr_sector.values() if s != "—"})
    print(f"[china] {closes.shape[1]} names · {closes.index.min().date()}→{closes.index.max().date()} "
          f"· market = {mkt_lbl} · {n_sec} sectors · shrink {args.shrink}")

    panels = []
    for c in CONFIGS:
        minp = max(c["win"] // 2, 40)
        print(f"  [panel] {c['tag']} …")
        panels.append(score_panel(
            closes, market, tkr_sector, ew_peer,
            label=f"A-share top-{closes.shape[1]} · {mkt_lbl} · EW-peer sector · {c['tag']}",
            win=c["win"], minp=minp, form=c["form"], skip=c["skip"],
            horizon=c["horizon"], shrink=args.shrink))

    report = render(panels, mkt_lbl, args)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "china-residual-alpha-phase0.md"
    out.write_text(report)
    print(f"\n[report] {out}")
    print(verdict_line(panels))
    return 0


def _ic(p, sig):
    return p.get("ic", {}).get(sig, {})


def verdict_line(panels) -> str:
    """One-line GO/REFINE/KILL read. The disposition (mirroring the US leg) is whether
    the *residual* construction is the more TRADABLE winner-picker: residual momentum IC>0
    AND the residual info-ratio long-short out-Sharpes plain total momentum at the ships
    horizon. Also flags the short-frame reversal sign and the acceleration kill."""
    p = panels[0]
    if p.get("error"):
        return f"[verdict] inconclusive — {p['error']}"
    res = _ic(p, "ir_res").get("mean_ic")            # raw residual info-ratio IC
    tot = _ic(p, "mom_tot").get("mean_ic")           # raw total momentum IC
    rev = _ic(p, "rev_st|SN").get("mean_ic")
    acc = _ic(p, "acc_res|SN").get("mean_ic")
    ls_res = (p.get("ls", {}).get("ir_res") or {}).get("sharpe")
    ls_tot = (p.get("ls", {}).get("mom_tot") or {}).get("sharpe")
    if res is None or tot is None:
        return "[verdict] inconclusive — IC unavailable"
    pos = res > 0
    beats_ls = (ls_res is not None and ls_tot is not None and ls_res > ls_tot)
    tag = ("GO (ranking/context leg — residual is the tradable construction)"
           if (pos and beats_ls) else
           "REFINE (momentum positive but residual edge unclear)" if pos else
           "KILL (residual IC ≤ 0)")
    revtag = (f"; rev_st|SN {rev:+.3f}→" + ("REVERSAL overlay" if (rev or 0) < 0 else "continuation")) if rev is not None else ""
    acctag = f"; acc {acc:+.3f}→KILLED" if (acc is not None and acc < 0) else ""
    lstag = f"; LS Sharpe residual {ls_res} vs total {ls_tot}" if ls_res is not None else ""
    return f"[verdict] {tag} — residual IC {res:+.3f} vs total {tot:+.3f}{lstag}{revtag}{acctag}"


def render(panels, mkt_lbl, args) -> str:
    L = ["# China A-share residual-alpha — Phase 0 IC scorecard", "",
         "*Generated by `scripts/china_residual_alpha_phase0.py` — mirrors the validated US "
         "harness (`scripts/residual_alpha_phase0.py`) on the A-share universe "
         "(`data/china_search/`). The gate: sector-neutral residual momentum must rank winners "
         "(IC>0) AND beat plain total-return momentum. Betas are causal (252/126d, lagged 1d, "
         f"shrunk {args.shrink}); each sector basket orthogonalized to the market "
         f"({mkt_lbl}). Judge survivors vs ~0.*", "",
         "**Caveats (read first):** only ~5y of A-share history → low power vs the US deep panel; "
         "the 800-name universe is top-market-cap *today* → survivorship-biased (inflates "
         "momentum, so a weak read is conservative); sectors are yfinance buckets, not GICS; "
         "the retail-dominated tape is expected to make the short frame (`rev_st`) a stronger "
         "*reversal* (negative IC) than the US — a usable entry-timing overlay, not a failure.", ""]
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
                     f"| {r.get('t_hac')} | {r.get('p_hac')} | {r.get('q_fdr', '—')} "
                     f"| {r.get('hit')} | {r.get('n')} |")
        surv = [c for c in rows if rows[c].get("survives_fdr")]
        L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", "",
              f"Top-vs-bottom-quintile dollar-neutral backtest (net of {COST_BPS:.0f}bps one-way):", "",
              "| signal | net Sharpe | cum % | DSR | verdict | bootstrap Sharpe CI | P(SR>0) |",
              "|---|--:|--:|--:|---|---|--:|"]
        for c, b in p["ls"].items():
            L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr', '—')} "
                     f"| {b.get('verdict', '—')} | {b.get('sharpe_ci', '—')} | {b.get('sharpe_gt0_prob', '—')} |")
        L += [""]
    L += ["---", "",
          "**How to read.** `mom_res` (beta-stripped) vs `mom_tot` (plain) is the core test; "
          "`ir_res` is the consistency-scaled (info-ratio) headline; `|SN` = sector-neutral "
          "(within-sector) = the 'winners within a sector' view (the operator's exact framing). "
          "`rev_st` (last-month) is the short frame — a **negative** IC = short-horizon reversal "
          "(a contrarian entry-timing overlay, not a picker); `acc_res` tests acceleration. With "
          "only ~5y the per-config rebalance count is low — corroboration ACROSS the three configs "
          "(and vs the `--ew-market` robustness run) matters more than any single t-stat.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
