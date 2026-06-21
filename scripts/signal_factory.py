"""Signal-factory scorecard — roadmap Phase 4 (breadth honesty).

Leak-free PIT IC test of the NEW fundamental-trend legs (engine.signal_factory) on
the quarterly grid: rank-IC vs forward return per leg → HAC-t → BH-FDR across the
panel → VIF prune → combine the survivors by inverse-correlation shrinkage into a
single decorrelated CONTEXT score, and IC-test that composite too. The whole grid
is logged to the canonical trial ledger so the program-wide multiple-testing N is
honest.

Framing (stamped on every output): this is a falsifiable, decorrelated CONTEXT
score, NOT alpha. On free survivor data even a clean combined IC of ~0.02–0.026
implies a realized IR of only ~0.10–0.22, and cross-name correlation caps the
achievable free-data IR at ~0.3–0.4 regardless. The win is honest, FDR-gated
breadth measurement — confirming which trend legs carry independent information and
retiring the phantom ones — not minting alpha.

Run: .venv/bin/python -m scripts.signal_factory [--quick] [--horizon 63] [--start 2011]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from engine.equity_factors import _closes  # noqa: E402
from engine.signal_factory import LEGS, build_legs, inverse_correlation_weights  # noqa: E402
from engine.validation import benjamini_hochberg, ic_summary, rank_ic, vif  # noqa: E402
from lib import config  # noqa: E402

try:
    from engine.trial_ledger import TrialLedger
except Exception:  # noqa: BLE001 — ledger optional
    TrialLedger = None


def _zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    return (s - mu) / sd if sd and not np.isnan(sd) else s * np.nan


def _quarter_grid(closes, start_year, horizon):
    idx = closes.index
    out = []
    for q in pd.date_range(f"{start_year}-03-31", idx.max(), freq="QE"):
        d = idx[idx <= q]
        if len(d) and idx.get_loc(d[-1]) + horizon < len(idx):
            out.append(d[-1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="last 12 quarters only")
    ap.add_argument("--horizon", type=int, default=63)
    ap.add_argument("--start", type=int, default=2011)
    args = ap.parse_args()

    panel_p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not panel_p.exists():
        print("no fundamentals_panel.parquet — run collectors.edgar fetch_panel")
        return 1
    panel = pd.read_parquet(panel_p)
    closes = _closes("broad")
    if closes.empty:
        print("no close caches — run breadth collectors first")
        return 1
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)

    grid = _quarter_grid(closes, args.start, args.horizon)
    if args.quick:
        grid = grid[-12:]
    if len(grid) < 6:
        print(f"grid too short ({len(grid)})")
        return 1

    per_leg_ic = {lg: [] for lg in LEGS}
    comp_ic_raw = []                              # equal-weight composite (pre-gate, for reference)
    pooled_z = []                                 # stacked cross-sectional z's for VIF / corr
    n_names = []
    for d in grid:
        legs = build_legs(panel, d)
        if legs.empty:
            continue
        fr = fwd.loc[d] if d in fwd.index else None
        if fr is None:
            continue
        z = legs.apply(_zscore)
        common = z.index.intersection(fr.dropna().index)
        if len(common) < 30:
            continue
        n_names.append(len(common))
        for lg in LEGS:
            per_leg_ic[lg].append(rank_ic(z[lg], fr))
        comp_ic_raw.append(rank_ic(z.mean(axis=1), fr))
        pooled_z.append(z.reindex(common))

    ppy = 4
    rows, pvals = {}, {}
    for lg in LEGS:
        s = ic_summary(pd.Series(per_leg_ic[lg]).dropna(), periods_per_year=ppy)
        if s.get("n", 0) >= 6:
            rows[lg] = s
            if s.get("p_hac") is not None:
                pvals[lg] = s["p_hac"]
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for lg, q in fdr.items():
        rows[lg]["q_fdr"] = q["q"]
        rows[lg]["survives_fdr"] = q["reject"]

    pooled = pd.concat(pooled_z, ignore_index=True) if pooled_z else pd.DataFrame(columns=LEGS)
    vifs = vif(pooled) if not pooled.empty else {}
    for lg in rows:
        rows[lg]["vif"] = round(vifs[lg], 2) if lg in vifs else None

    # SURVIVORS: FDR-reject AND positive IC AND VIF<5 (independent, non-redundant edge)
    survivors = [lg for lg in rows
                 if rows[lg].get("survives_fdr") and (rows[lg].get("mean_ic") or 0) > 0
                 and (rows[lg].get("vif") is None or rows[lg]["vif"] < 5)]

    # combine survivors by inverse-correlation shrinkage; IC-test the context score
    weights, comp = {}, None
    if survivors:
        weights = inverse_correlation_weights(pooled[survivors], shrink=0.5)
        cic = []
        for d in grid:
            legs = build_legs(panel, d)
            if legs.empty or d not in fwd.index:
                continue
            z = legs[survivors].apply(_zscore)
            score = sum(weights[lg] * z[lg] for lg in survivors)
            cic.append(rank_ic(score, fwd.loc[d]))
        comp = ic_summary(pd.Series(cic).dropna(), periods_per_year=ppy)

    # honest program-wide N: every leg-horizon pair is a trial, logged to the
    # canonical ledger so the whole program's multiple-testing budget is real.
    n_trials = None
    if TrialLedger is not None:
        try:
            led = TrialLedger()
            led.log_grid([{"leg": lg, "horizon": args.horizon} for lg in LEGS],
                         family="signal_factory")
            if hasattr(led, "families") and hasattr(led, "literal_n"):
                n_trials = sum(led.literal_n(f) for f in led.families())   # program-wide
        except Exception:  # noqa: BLE001
            n_trials = None

    payload = {
        "schema": "signal_factory.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "span": f"{grid[0].date()}..{grid[-1].date()}", "rebalances": len(grid),
        "horizon_d": args.horizon, "median_universe": int(np.median(n_names)) if n_names else 0,
        "legs": rows, "survivors": survivors, "weights": weights,
        "equal_weight_composite_ic": round(float(np.nanmean(comp_ic_raw)), 4) if comp_ic_raw else None,
        "context_score": comp, "n_trials": n_trials,
        "survivorship": "BIASED — survivor-only panel, so these ICs are an OPTIMISTIC bound.",
        "framing": "Falsifiable, decorrelated CONTEXT score — NOT alpha. Free-data realized-IR "
                   "ceiling ~0.3-0.4; a clean combined IC ~0.02-0.026 => IR ~0.10-0.22. The win is "
                   "FDR-gated breadth honesty, not minting alpha.",
    }
    os.makedirs(config.data_dir() / "strategies", exist_ok=True)
    (config.data_dir() / "strategies" / "signal_factory.json").write_text(json.dumps(payload, indent=2, default=str))
    _report(payload)

    print(f"\n=== Signal factory (leak-free PIT) — {payload['span']}, {len(grid)} quarters, "
          f"fwd {args.horizon}d, ~{payload['median_universe']} names ===")
    print(f"{'leg':22} {'meanIC':>8} {'t_HAC':>7} {'qFDR':>7} {'VIF':>6} {'n':>3}")
    for lg in sorted(rows, key=lambda c: -(rows[c].get("mean_ic") or -9)):
        r = rows[lg]
        print(f"{lg:22} {r['mean_ic']:>8.4f} {str(r['t_hac']):>7} {str(r.get('q_fdr','-')):>7} "
              f"{str(r.get('vif','-')):>6} {r['n']:>3}")
    print(f"\nSurvivors (FDR✓ · IC>0 · VIF<5): {survivors or 'NONE'}")
    if comp:
        print(f"Decorrelated context score IC: {comp.get('mean_ic')} (HAC-t {comp.get('t_hac')}, "
              f"IC-IR ann {comp.get('ic_ir_ann')})  weights={ {k: round(v,2) for k,v in weights.items()} }")
    print(">> CONTEXT score, not alpha — free-data IR ceiling ~0.3-0.4.")
    return 0


def _report(p: dict) -> None:
    L = ["# Signal factory — FDR-gated decorrelated breadth (Phase 4)\n",
         f"_{p['generated_utc']}_ · {p['span']} · {p['rebalances']} quarters · fwd {p['horizon_d']}d "
         f"· ~{p['median_universe']} names · leak-free PIT.\n",
         f"> {p['framing']}\n",
         "| leg | mean IC | t_HAC | q_FDR | VIF | n |", "|---|--:|--:|--:|--:|--:|"]
    for lg in sorted(p["legs"], key=lambda c: -(p["legs"][c].get("mean_ic") or -9)):
        r = p["legs"][lg]
        L.append(f"| {lg} | {r['mean_ic']} | {r['t_hac']} | {r.get('q_fdr','—')} "
                 f"| {r.get('vif','—')} | {r['n']} |")
    L += ["", f"**Survivors (FDR✓ · IC>0 · VIF<5):** {', '.join(p['survivors']) or 'NONE'}"]
    if p.get("context_score"):
        c = p["context_score"]
        L.append(f"**Decorrelated context score:** IC {c.get('mean_ic')} · HAC-t {c.get('t_hac')} · "
                 f"IC-IR ann {c.get('ic_ir_ann')} · weights "
                 f"{ {k: round(v,2) for k,v in p['weights'].items()} }")
    L.append(f"\n_{p['survivorship']} Program-wide trial N (ledger): {p.get('n_trials')}._\n")
    os.makedirs("reports", exist_ok=True)
    with open("reports/signal-factory.md", "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
