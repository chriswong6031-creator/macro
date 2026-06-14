"""Leak-free factor IC scorecard — the payoff of the point-in-time panel (Phase A).

For each rebalance date on a quarterly grid we rebuild the factor cross-section AS
IT WAS KNOWABLE THEN — engine.equity_factors.compute_factors(asof=date), which
reads the EDGAR point-in-time panel (collectors/edgar.py) and truncates prices to
`asof`, so no factor ever sees a not-yet-filed 10-K. Each factor's z-score is then
rank-correlated with the forward return to get a per-date Information Coefficient,
aggregated to mean IC, IC-IR, a Newey-West (HAC) t-stat (the IC series autocorrelates
when forward windows overlap), and a Benjamini-Hochberg FDR across the factor panel
(many factors screened → control the family false-discovery rate). A VIF read flags
redundant factors. This is the honest answer to "do these factors actually rank
winners?" — and, post point-in-time fix, the spreads are expected to look weaker
than a naive latest-data backtest (that gap IS the look-ahead/survivorship bias
being removed). Judge survivors against ~0 (an AQR/Fama-French-style null).

Run: .venv/bin/python -m scripts.factor_ic_scorecard [--quick] [--horizon 63] [--start 2011]
  --quick : only the last 12 quarters (fast verification); full grid is offline/weekly.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")   # truncated-history beta calc emits benign numpy RuntimeWarnings

from engine.equity_factors import FACTOR_LABELS, _closes, compute_factors  # noqa: E402
from engine.factor_orthogonal import orthogonal_composite, overlap_diagnostics  # noqa: E402
from engine.validation import benjamini_hochberg, ic_summary, rank_ic  # noqa: E402
from lib import config  # noqa: E402

LEG_COLS = list(FACTOR_LABELS)                       # individual factor legs
# composite_orth = Löwdin-decorrelated composite (does removing factor overlap help?)
FACTOR_COLS = LEG_COLS + ["composite", "composite_orth"]


def quarter_grid(closes: pd.DataFrame, start_year: int, horizon: int) -> list:
    """Quarter-end trading dates from start_year, leaving room for the forward
    window (so every rebalance has a realized label)."""
    idx = closes.index
    q_ends = pd.date_range(f"{start_year}-03-31", idx.max(), freq="QE")
    out = []
    for q in q_ends:
        d = idx[idx <= q]
        if len(d) and idx.get_loc(d[-1]) + horizon < len(idx):
            out.append(d[-1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="last 12 quarters only")
    ap.add_argument("--horizon", type=int, default=63, help="forward return window (trading days)")
    ap.add_argument("--start", type=int, default=2011)
    args = ap.parse_args()

    closes = _closes()
    if closes.empty:
        print("no close caches — run breadth collectors first")
        return 1
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)  # forward return per date

    grid = quarter_grid(closes, args.start, args.horizon)
    if args.quick:
        grid = grid[-12:]
    if len(grid) < 6:
        print(f"grid too short ({len(grid)})")
        return 1

    per_date_ic: dict[str, list] = {c: [] for c in FACTOR_COLS}
    n_names: list[int] = []
    last_table = None
    for d in grid:
        fac = compute_factors(asof=d)
        if not fac or not fac.get("table"):
            continue
        t = pd.DataFrame(fac["table"]).set_index("ticker")
        last_table = t
        fr = fwd.loc[d] if d in fwd.index else None
        if fr is None:
            continue
        n_names.append(int(t.index.isin(fr.dropna().index).sum()))
        for c in FACTOR_COLS:
            if c in t.columns:
                per_date_ic[c].append(rank_ic(pd.to_numeric(t[c], errors="coerce"), fr))
        # decorrelated composite: orthogonalize the factor legs present this date
        legs = t[[c for c in LEG_COLS if c in t.columns]].apply(pd.to_numeric, errors="coerce")
        if legs.shape[1] >= 3:
            per_date_ic["composite_orth"].append(rank_ic(orthogonal_composite(legs), fr))

    # aggregate per factor + FDR across the panel
    ppy = 4  # quarterly
    rows, pvals = {}, {}
    for c in FACTOR_COLS:
        ics = pd.Series(per_date_ic[c]).dropna()
        s = ic_summary(ics, periods_per_year=ppy)
        if s.get("n", 0) >= 6:
            rows[c] = s
            if s.get("p_hac") is not None:
                pvals[c] = s["p_hac"]
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for c, q in fdr.items():
        rows[c]["q_fdr"] = q["q"]
        rows[c]["survives_fdr"] = q["reject"]

    coll = {}
    if last_table is not None:
        legs = last_table[[c for c in LEG_COLS if c in last_table.columns]].apply(
            pd.to_numeric, errors="coerce")
        coll = overlap_diagnostics(legs)   # raw vs orthogonalized factor overlap + VIF

    report = {
        "horizon_d": args.horizon, "rebalances": len(grid),
        "span": f"{grid[0].date()}..{grid[-1].date()}",
        "median_universe": int(np.median(n_names)) if n_names else 0,
        "leak_free": True, "factors": rows, "collinearity": coll,
        "note": ("Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly "
                 "cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; "
                 "q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0."),
    }
    outdir = config.data_dir() / "edgar"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "ic_scorecard.json").write_text(json.dumps(report, indent=2, default=str))
    _write_md(report)

    order = sorted(rows, key=lambda c: -(rows[c].get("ic_ir_ann") or -9))
    print(f"\n=== Factor IC scorecard (leak-free) — {report['span']}, {len(grid)} quarterly "
          f"rebalances, fwd {args.horizon}d, ~{report['median_universe']} names ===")
    print(f"{'factor':14s} {'meanIC':>7} {'IC-IR':>6} {'ICIRann':>8} {'t_HAC':>6} {'p':>6} "
          f"{'qFDR':>6} {'hit':>5} {'n':>3}")
    for c in order:
        r = rows[c]
        print(f"{c:14s} {r['mean_ic']:>7.4f} {r['ic_ir']:>6.2f} {r['ic_ir_ann']:>8.2f} "
              f"{str(r['t_hac']):>6} {str(r['p_hac']):>6} {str(r.get('q_fdr','-')):>6} "
              f"{r['hit']:>5.2f} {r['n']:>3}")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    print(f"\nSurvive BH-FDR(10%): {surv or 'NONE'}")
    return 0


def _write_md(report: dict) -> None:
    L = ["# Factor IC scorecard (leak-free, point-in-time)", "",
         f"Span {report['span']} · {report['rebalances']} quarterly rebalances · "
         f"forward {report['horizon_d']}d · ~{report['median_universe']} names · "
         f"point-in-time (no look-ahead).", "",
         "IC = cross-sectional rank correlation of each factor's z-score vs the forward "
         "return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate "
         "the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. Judge "
         "survivors against ~0 — post point-in-time fix the spreads are honestly weaker.", "",
         "| factor | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    rows = report["factors"]
    for c in sorted(rows, key=lambda c: -(rows[c].get("ic_ir_ann") or -9)):
        r = rows[c]
        L.append(f"| {c} | {r['mean_ic']} | {r['ic_ir']} | {r['ic_ir_ann']} | {r['t_hac']} "
                 f"| {r['p_hac']} | {r.get('q_fdr','—')} | {r['hit']} | {r['n']} |")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", ""]
    coll = report.get("collinearity", {})
    if coll.get("top_pairs"):
        L.append("## Factor overlap (latest cross-section)\n")
        L.append(f"`composite_orth` above is the Löwdin-decorrelated composite. Mean "
                 f"|factor corr| **{coll.get('mean_abs_corr_raw')}** raw → "
                 f"**{coll.get('mean_abs_corr_orth')}** orthogonalized (the redundancy removed). "
                 f"VIF>5 = redundant. Most-correlated pairs:")
        for p in coll["top_pairs"]:
            L.append(f"- {p['a']} ↔ {p['b']}: |corr| {p['corr']}")
        hi = {k: v for k, v in coll.get("vif", {}).items() if v and v > 5}
        if hi:
            L.append(f"\nHigh VIF: {hi}")
    L.append(f"\n> {report['note']}")
    Path(config.load()["storage"]["reports_dir"], "factor-ic-scorecard.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
