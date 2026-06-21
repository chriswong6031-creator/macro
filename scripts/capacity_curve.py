"""Capacity / market-impact scorecard — roadmap Phase 3 (pain-point #4).

A flat cost_bps silently flatters high-turnover signals and can't price a $5M
microcap trade vs a $9k mega-cap one. This runs the square-root-impact capacity
model (engine.validation.capacity_curve) over a real price+volume panel: for each
name we build a transparent 12-1 momentum long/flat alloc, then ask "as deployed
AUM rises, where does NET Sharpe fall below buy & hold?" — the honest capacity
number. The point is the MACHINERY + the discrimination (high-ADV names hold orders
of magnitude more than low-ADV ones), not a claim of alpha on the demo rule.

Run: .venv/bin/python -m scripts.capacity_curve [--names 40] [--eta 0.1] [--cost-bps 3]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from engine.validation import capacity_curve, dollar_adv  # noqa: E402
from lib import store  # noqa: E402

AUM_GRID = [1e6, 5e6, 2.5e7, 1e8, 5e8, 2.5e9, 1e10, 5e10]   # $1M .. $50B
FORM, SKIP = 252, 21


def _mom_alloc(close: pd.Series) -> pd.Series:
    """Transparent 12-1 momentum long/flat: hold when the trailing 12m-minus-1m
    return is positive, else flat. A no-edge-claimed demo rule that DOES turn over."""
    mom = close.shift(SKIP) / close.shift(FORM) - 1.0
    return (mom > 0).astype(float)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=40)
    ap.add_argument("--eta", type=float, default=0.1, help="square-root impact coefficient")
    ap.add_argument("--cost-bps", type=float, default=3.0, help="linear spread+fee cost")
    args = ap.parse_args()

    files = sorted(glob.glob("data/stocks/*.parquet"))
    rows, skipped = [], 0
    for f in files:
        t = os.path.splitext(os.path.basename(f))[0]
        df = store.read("stocks", t)
        if df is None or not {"close", "volume"} <= set(df.columns) or len(df) < FORM + 120:
            skipped += 1
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        close, vol = df["close"], df["volume"]
        adv = dollar_adv(close, vol)
        if adv.dropna().empty or adv.median() <= 0:
            skipped += 1
            continue
        cap = capacity_curve(close, _mom_alloc(close), adv, AUM_GRID,
                             cost_bps=args.cost_bps, impact_eta=args.eta)
        rows.append({"ticker": t, "adv_usd_median": float(adv.median()),
                     "buyhold_sharpe": cap["buyhold_sharpe"], "gross_sharpe": cap["gross_sharpe"],
                     "verdict": cap["verdict"], "capacity_usd": cap["capacity_usd"],
                     "curve": cap["curve"]})
        if len(rows) >= args.names:
            break

    # only names with a genuine gross edge (verdict != no_edge) have a real capacity;
    # among those, the smallest finite capacity binds a single-sleeve deployment.
    capped = sorted((r for r in rows if r["verdict"] == "capped"),
                    key=lambda r: r["capacity_usd"])
    rows.sort(key=lambda r: ({"capped": 0, "exceeds_grid": 1, "no_edge": 2}[r["verdict"]],
                             r["capacity_usd"] or 0))
    payload = {
        "schema": "capacity_curve.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": "net = gross - (cost_bps + eta*sigma*sqrt(traded$/ADV$))*turnover",
        "impact_eta": args.eta, "cost_bps": args.cost_bps,
        "demo_signal": "12-1 momentum long/flat (no alpha claimed — turnover vehicle)",
        "n_names": len(rows), "n_skipped": skipped, "aum_grid": AUM_GRID,
        "n_economic": sum(1 for r in rows if r["verdict"] != "no_edge"),
        "binding_capacity_usd": capped[0]["capacity_usd"] if capped else None,
        "names": rows,
    }
    os.makedirs("data/strategies", exist_ok=True)
    with open("data/strategies/capacity_curve.json", "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    _report(payload)

    print(f"[capacity] {len(rows)} names (skipped {skipped}); eta={args.eta} cost={args.cost_bps}bps")
    print(f"{'ticker':8} {'ADV$M':>8} {'gross_SR':>9} {'bh_SR':>7} {'capacity':>14}")
    for r in rows[:14]:
        print(f"{r['ticker']:8} {r['adv_usd_median']/1e6:>8.0f} "
              f"{str(r['gross_sharpe']):>9} {str(r['buyhold_sharpe']):>7} {_cap_label(r):>14}")
    if capped:
        lo = capped[0]
        print(f"\nBinding capacity (smallest with a gross edge): {lo['ticker']} @ "
              f"~${lo['capacity_usd']/1e6:,.0f}M (ADV ${lo['adv_usd_median']/1e6:,.0f}M)")
    print(f"economic (gross SR ≥ buy&hold): {payload['n_economic']}/{len(rows)} "
          "— demo momentum rule, no alpha claimed")
    return 0


def _cap_label(r: dict) -> str:
    if r["verdict"] == "no_edge":
        return "no edge"
    if r["verdict"] == "exceeds_grid":
        return "≥grid max"
    return f"${r['capacity_usd']/1e6:,.0f}M"


def _report(p: dict) -> None:
    L = ["# Capacity / market-impact scorecard\n",
         f"_{p['generated_utc']}_ · {p['n_names']} names · √-impact η={p['impact_eta']}, "
         f"linear {p['cost_bps']}bps · demo signal: {p['demo_signal']}\n",
         f"Model: `{p['model']}`. participation = traded$/ADV$, traded$ = AUM·|Δpos|. "
         "Capacity = largest AUM whose NET Sharpe still beats buy & hold.\n",
         "| ticker | ADV $M | gross SR | buy&hold SR | capacity |",
         "|---|--:|--:|--:|--:|"]
    for r in p["names"][:25]:
        L.append(f"| {r['ticker']} | {r['adv_usd_median']/1e6:,.0f} | {r['gross_sharpe']} "
                 f"| {r['buyhold_sharpe']} | {_cap_label(r)} |")
    L.append(f"\n**Binding capacity:** "
             + (f"~${p['binding_capacity_usd']/1e6:,.0f}M (the lowest-capacity name with a gross "
                "edge caps a single-sleeve deployment)." if p["binding_capacity_usd"]
                else "no name on this set both beats buy & hold gross AND stays capped within the grid.")
             + " 'no edge' = the demo signal doesn't beat buy & hold even costless (not a capacity "
               "limit); '≥grid max' = capacity exceeds the grid. Higher-ADV names hold orders of "
               "magnitude more — the discrimination a flat bps can't make. NOT an alpha claim.\n")
    os.makedirs("reports", exist_ok=True)
    with open("reports/capacity-curve.md", "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
