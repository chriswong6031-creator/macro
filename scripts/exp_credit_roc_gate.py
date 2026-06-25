"""PHASE-0 EXPERIMENT — does HY-OAS rate-of-change (the credit canary) earn a SCORED
tier as a forward-drawdown leg? Reuses the EXACT production gate from
scripts.calibrate_rate_inflation so the numbers are directly comparable to
data/transmission/calibration.json. Touches nothing live; prints a table only.

It tests credit-stress velocity candidates (HY/IG OAS rate-of-change at 5/10/20/63d,
acceleration, level) against the same bar every rate/inflation leg faced:
  - signed Spearman IC vs forward 63d S&P drawdown DEPTH (full + both purged halves)
  - purged-CV sign robustness (5 folds, embargo = 63d)
  - high-stress tercile P(>=10% dd) edge over base rate + block-bootstrap CI
  - Clark-West / OOS-R2 return-forecast bar (does it predict the LEVEL of returns)
A leg is scored-eligible ONLY if verdict starts CONFIRMED and cv_robust.

It also (a) reproduces real10y_chg63 as a SANITY CHECK (must match the known
IC 0.139 / edge 7.2pp / CW_t -1.106), and (b) reports correlation of the best credit
leg vs real10y_chg63 / breakeven velocity — the INDEPENDENCE check (is the credit
canary a genuinely different signal from the rate identity, or a restatement?).

Run: python -m scripts.exp_credit_roc_gate
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import inputs  # noqa: E402
from engine.rate_inflation_transmission import build_drivers  # noqa: E402
from engine.validation import (clark_west, oos_r2, purged_folds,  # noqa: E402
                               fold_robust)
from scripts.calibrate_rate_inflation import (  # noqa: E402
    H, DD_WINDOW, MIN_OBS, _spear, _tercile_edge, _causal_return_forecast,
    _scored_verdict, equity_targets, asset_fwd_returns)


def run_gate(name: str, stress: pd.Series, eq: pd.DataFrame, fwd_spy: pd.Series,
             split: pd.Timestamp) -> dict:
    """Replicates scored_gate()'s per-driver computation EXACTLY (stress already signed
    so higher = more risk-off)."""
    joint = pd.concat([stress.rename("s"), eq["dd_depth"]], axis=1).dropna()
    if len(joint) < MIN_OBS:
        return {"name": name, "verdict": "UNMEASURED", "n": len(joint)}
    span = joint.index
    pre = span[span < split]
    pre = pre[:-H] if len(pre) > H else pre
    post = span[span >= split]
    dd = eq["dd_depth"]
    ic_f = _spear(stress.reindex(span), dd.reindex(span))
    ic_pre = _spear(stress.reindex(pre), dd.reindex(pre))
    ic_post = _spear(stress.reindex(post), dd.reindex(post))
    folds = purged_folds(span, k=5, embargo=DD_WINDOW)
    fold_signs = [int(np.sign(_spear(stress.reindex(ix), dd.reindex(ix))))
                  for ix in folds.values() if len(ix) > MIN_OBS // 3]
    cv = fold_robust(int(np.sign(ic_f)), fold_signs, want=1)
    cond = _tercile_edge(stress, eq)
    edge = cond.get("high_edge_pp")
    ci = cond.get("high_p_dd10_ci")
    base = cond.get("base_p_dd10")
    verdict = _scored_verdict(ic_f, ic_pre, ic_post, edge, ci, base)
    fcst = _causal_return_forecast(stress, fwd_spy, H)
    rj = pd.concat([fcst.rename("f"), fwd_spy.rename("r")], axis=1).dropna()
    cw_t = oosr2 = None
    if len(rj) >= 504:
        bench = fwd_spy.shift(H).expanding(min_periods=252).mean().reindex(rj.index)
        oosr2 = oos_r2(rj["r"].to_numpy(), rj["f"].to_numpy(),
                       bench=bench.to_numpy()).get("oos_r2")
        cw_t = clark_west(rj["r"].to_numpy(), rj["f"].to_numpy(),
                          bench=bench.to_numpy()).get("cw_t")
    return {"name": name, "n": int(len(joint)),
            "span": f"{span.min().date()}..{span.max().date()}",
            "ic_f": ic_f, "ic_pre": ic_pre, "ic_post": ic_post, "cv": bool(cv),
            "edge_pp": edge, "ci": ci, "base": base, "cw_t": cw_t, "oos_r2": oosr2,
            "verdict": verdict,
            "eligible": verdict.startswith("CONFIRMED") and bool(cv)}


def main() -> int:
    split = pd.Timestamp("2015-01-01")
    f = inputs.build_features()
    eq = equity_targets(f.index)
    fwd_spy = asset_fwd_returns(f.index, H)["SPY"]

    # --- candidate stress drivers (higher = more risk-off) ---
    cand: dict[str, pd.Series] = {}
    if "hy_oas" in f:
        hy = f["hy_oas"]
        for w in (5, 10, 20, 42, 63):
            cand[f"hy_oas_chg{w}"] = hy - hy.shift(w)          # widening velocity = stress
        cand["hy_oas_accel20"] = (hy - hy.shift(20)) - (hy - hy.shift(20)).shift(20)
        cand["hy_oas_level"] = hy                              # level (raw; Spearman rank)
        cand["hy_oas_z504"] = (hy - hy.rolling(504).mean()) / hy.rolling(504).std()
    if "ig_oas" in f:
        ig = f["ig_oas"]
        cand["ig_oas_chg20"] = ig - ig.shift(20)
        cand["ig_oas_chg63"] = ig - ig.shift(63)
    if "hyg_lqd" in f:                                          # HYG/LQD FALLING = stress
        hl = f["hyg_lqd"]
        cand["hyg_lqd_chg20_inv"] = -(hl / hl.shift(20) - 1.0)
        cand["hyg_lqd_chg63_inv"] = -(hl / hl.shift(63) - 1.0)

    # --- SANITY: reproduce the known rate legs from build_drivers ---
    drv = build_drivers(f)
    sanity = {}
    for k in ("real10y_chg63", "nom10y_chg63", "be10y_chg63"):
        if k in drv:
            sanity[k] = run_gate(k, +1 * drv[k], eq, fwd_spy, split)

    res = {k: run_gate(k, v, eq, fwd_spy, split) for k, v in cand.items()}

    def fmt(r: dict) -> str:
        if r.get("verdict") == "UNMEASURED":
            return f"{r['name']:22s} UNMEASURED (n={r.get('n')})"
        g = lambda x, d=3: ("None" if x is None else (round(x, d) if isinstance(x, float) else x))
        return (f"{r['name']:22s} {r['verdict']:26s} "
                f"IC f/pre/post={g(r['ic_f'])}/{g(r['ic_pre'])}/{g(r['ic_post'])} "
                f"cv={str(r['cv']):5s} edge={r['edge_pp']}pp base={r['base']} "
                f"ci={r['ci']} | CW_t={g(r['cw_t'])} oosR2={g(r['oos_r2'],4)} "
                f"{'<<< SCORED-ELIGIBLE' if r['eligible'] else ''}")

    print(f"\n=== PHASE-0: credit-ROC scored-gate (asof {f.index[-1].date()}, "
          f"fwd {H}d dd, split {split.date()}) ===")
    print(f"  base rate P(>=10% {DD_WINDOW}d dd): {res.get('hy_oas_chg20',{}).get('base')}\n")
    print("-- SANITY (must match calibration.json) --")
    for r in sanity.values():
        print("  " + fmt(r))
    print("\n-- CREDIT-STRESS CANDIDATES --")
    for r in sorted(res.values(), key=lambda x: -(abs(x.get("ic_f") or 0))):
        print("  " + fmt(r))

    # --- INDEPENDENCE: is the best credit leg a different signal from the rate identity? ---
    print("\n-- INDEPENDENCE (Pearson corr of best credit leg vs rate-identity legs) --")
    best = max((r for r in res.values() if r.get("ic_f") is not None),
               key=lambda x: abs(x["ic_f"]), default=None)
    if best:
        bs = cand[best["name"]]
        for k in ("real10y_chg63", "nom10y_chg63", "be10y_chg63"):
            if k in drv:
                c = pd.concat([bs.rename("a"), drv[k].rename("b")], axis=1).dropna()
                cc = float(c["a"].corr(c["b"])) if len(c) > 120 else float("nan")
                print(f"  {best['name']} vs {k:16s}: corr={round(cc,3)}")
    print()
    elig = [r["name"] for r in res.values() if r.get("eligible")]
    print(f"SCORED-ELIGIBLE credit legs: {elig or 'NONE — credit-ROC is display-only too'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
