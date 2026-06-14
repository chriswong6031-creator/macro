"""Phase-0 for the SUE earnings-momentum factor (research/DATA_SIGNAL_EXPANSION_2026.md).

Mirrors scripts/factor_ic_scorecard but ADDS the SUE leg, so SUE is judged on the
SAME leak-free quarterly grid AND against the SAME Benjamini-Hochberg family as the
existing factor zoo — the team's bar (a factor must survive BH-FDR across the panel,
like the insider factor did and short_interest did not). For each quarter-end:
  - compute the existing factor cross-section point-in-time (compute_factors(asof=d)),
  - compute the SUE cross-section point-in-time (engine.sue, EPS panel filed<=d),
  - rank-correlate each with the forward 63d return.
Aggregates mean IC / IC-IR / Newey-West t / BH-FDR q, plus a SUE quintile long-short
Sharpe for color. Writes data/edgar/sue_phase0.json + reports/sue-phase0.md.

Run: .venv/bin/python -m scripts.validate_sue [--quick] [--horizon 63] [--start 2011]
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
warnings.filterwarnings("ignore")

from engine.equity_factors import FACTOR_LABELS, _closes, compute_factors  # noqa: E402
from engine.sue import load_panel, sue_cross_section  # noqa: E402
from engine.validation import benjamini_hochberg, ic_summary, rank_ic  # noqa: E402
from lib import config  # noqa: E402
from scripts.factor_ic_scorecard import quarter_grid  # noqa: E402

LEGS = list(FACTOR_LABELS) + ["composite", "sue"]


def _quintile_ls(sue: pd.Series, fwd: pd.Series) -> float | None:
    j = pd.concat([sue.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 40:
        return None
    q = pd.qcut(j["s"].rank(method="first"), 5, labels=False)
    top, bot = j["f"][q == 4].mean(), j["f"][q == 0].mean()
    return float(top - bot)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--horizon", type=int, default=63)
    ap.add_argument("--start", type=int, default=2011)
    args = ap.parse_args()

    closes = _closes()
    if closes.empty:
        print("no close caches"); return 1
    panel = load_panel()
    if panel is None:
        print("no eps_quarterly panel — run: python -m collectors.edgar_eps"); return 1
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)
    grid = quarter_grid(closes, args.start, args.horizon)
    if args.quick:
        grid = grid[-16:]
    if len(grid) < 6:
        print(f"grid too short ({len(grid)})"); return 1

    per_ic: dict[str, list] = {c: [] for c in LEGS}
    ls_spreads, n_sue = [], []
    for d in grid:
        fr = fwd.loc[d] if d in fwd.index else None
        if fr is None:
            continue
        fac = compute_factors(asof=d)
        if fac and fac.get("table"):
            t = pd.DataFrame(fac["table"]).set_index("ticker")
            for c in list(FACTOR_LABELS) + ["composite"]:
                if c in t.columns:
                    per_ic[c].append(rank_ic(pd.to_numeric(t[c], errors="coerce"), fr))
        sue = sue_cross_section(panel, d)
        if len(sue) >= 30:
            n_sue.append(int(sue.index.isin(fr.dropna().index).sum()))
            per_ic["sue"].append(rank_ic(sue, fr))
            ls = _quintile_ls(sue, fr)
            if ls is not None:
                ls_spreads.append(ls)

    ppy = 4
    rows, pvals = {}, {}
    for c in LEGS:
        ics = pd.Series(per_ic[c]).dropna()
        s = ic_summary(ics, periods_per_year=ppy)
        if s.get("n", 0) >= 6:
            rows[c] = s
            if s.get("p_hac") is not None:
                pvals[c] = s["p_hac"]
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for c, q in fdr.items():
        rows[c]["q_fdr"] = q["q"]
        rows[c]["survives_fdr"] = q["reject"]

    # SUE quintile long-short Sharpe (quarterly spreads, annualized)
    ls = pd.Series(ls_spreads).dropna()
    ls_sharpe = float(ls.mean() / ls.std() * np.sqrt(ppy)) if len(ls) > 5 and ls.std() else None

    sue = rows.get("sue", {})
    survives = bool(sue.get("survives_fdr"))
    report = {
        "horizon_d": args.horizon, "rebalances": len(grid),
        "span": f"{grid[0].date()}..{grid[-1].date()}",
        "median_sue_universe": int(np.median(n_sue)) if n_sue else 0,
        "sue_ls_quintile_sharpe_ann": None if ls_sharpe is None else round(ls_sharpe, 3),
        "factors": rows,
        "verdict": ("WIRE — SUE survives BH-FDR across the factor family"
                    if survives else
                    "DISPLAY/CONFIRMER-ONLY — SUE does not survive BH-FDR (judge vs the zoo)"),
        "note": ("Point-in-time: EPS panel filed<=asof, prices truncated; IC = quarterly "
                 "cross-sectional rank corr of the factor vs forward return; t_hac=Newey-West; "
                 "q_fdr=Benjamini-Hochberg across ALL legs incl SUE."),
    }
    out = config.data_dir() / "edgar" / "sue_phase0.json"
    out.write_text(json.dumps(report, indent=2, default=str))

    order = sorted(rows, key=lambda c: -(rows[c].get("ic_ir_ann") or -9))
    print(f"\n=== SUE Phase-0 (leak-free) — {report['span']}, {len(grid)} rebalances, "
          f"fwd {args.horizon}d, ~{report['median_sue_universe']} SUE names ===")
    print(f"{'factor':14s} {'meanIC':>7} {'ICIRann':>8} {'t_HAC':>6} {'p':>6} {'qFDR':>6} {'hit':>5} {'n':>3}")
    for c in order:
        r = rows[c]
        mark = "  <-- SUE" if c == "sue" else ""
        print(f"{c:14s} {r['mean_ic']:>7.4f} {r['ic_ir_ann']:>8.2f} {str(r['t_hac']):>6} "
              f"{str(r['p_hac']):>6} {str(r.get('q_fdr','-')):>6} {r['hit']:>5.2f} {r['n']:>3}{mark}")
    print(f"\nSUE quintile L/S Sharpe (ann): {report['sue_ls_quintile_sharpe_ann']}")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    print(f"Survive BH-FDR(10%): {surv or 'NONE'}")
    print("VERDICT:", report["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
