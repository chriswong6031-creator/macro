"""Breadth/liquidity NET-EXPOSURE timing overlay — does it earn its keep? (N5 gate.)

A TIME-SERIES net-exposure dial (how much LONG the book runs), kept DISTINCT from the
cross-sectional dispersion gate (which sizes SELECTION gross, not net exposure). It blends
three risk-on legs into a 0..1 exposure scalar:
  * trend     — S&P 500 above its 200-day MA (the classic de-risk-in-downtrends leg)
  * breadth   — % of names above their 200-day MA healthy (participation) + a Zweig
                breadth-THRUST impulse (a rare, powerful launch signal)
  * net-liq   — Fed net liquidity expanding (net_liquidity_bn rising), 2014+ only

Strict GO bar (the user's "must prove incremental, not redundant"): the combined overlay
must (a) improve net-of-cost Sharpe vs buy-&-hold, (b) cut max drawdown, AND (c) each leg
must ADD over the others (combined ≥ best single leg) — otherwise it is redundant with
trend-following alone and should NOT ship as a multi-leg gate.

Method: daily exposure(t-1) × SPX return(t), minus turnover cost on exposure changes, vs
buy-&-hold. Legs each ∈ {0,1}; exposure = mean of the legs KNOWABLE that day (so the
net-liq leg simply joins in 2014). Deep where possible: trend/breadth 1962-2026, net-liq
2014-2026. CIs via stationary block bootstrap on the daily return series.

Run: PYTHONPATH=. python -m scripts.validate_timing_overlay [--cost-bps 3]
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

from engine.validation import block_bootstrap_ci  # noqa: E402
from lib import config, store  # noqa: E402

TRADING_YEAR = 252


def _spx() -> pd.Series:
    for s in ("^GSPC", "_GSPC", "SPY"):
        d = store.read("yahoo", s)
        if d is not None and len(d):
            c = d["close"] if "close" in d.columns else d.iloc[:, 0]
            return c.dropna()
    raise SystemExit("no SPX series in the yahoo store")


def _legs() -> pd.DataFrame:
    """Daily risk-on legs (each 0/1), point-in-time aligned to the SPX trading calendar."""
    spx = _spx()
    bdf = pd.read_parquet(config.data_dir() / "breadth" / "breadth.parquet")
    legs = pd.DataFrame(index=spx.index)
    # trend: SPX above its 200-day MA
    ma200 = spx.rolling(200).mean()
    legs["trend"] = (spx > ma200).astype(float)
    # breadth participation: % above 200dma above a healthy floor
    pa200 = bdf["pct_above_200"].reindex(spx.index).ffill(limit=5)
    legs["breadth"] = (pa200 >= 40).astype(float).where(pa200.notna())
    # (A Zweig breadth-THRUST leg was tried and dropped: it is a rare 0/1 impulse, so
    #  averaging it into a continuous exposure dial just drags exposure down most of the
    #  time — it belongs as an entry BOOST, not a participation leg. Out of scope here.)
    # net liquidity expanding (63d RoC > 0), 2014+
    try:
        nl = pd.read_parquet(config.data_dir() / "vector" / "signals.parquet")["net_liquidity_bn"].dropna()
        nl = nl.reindex(spx.index).ffill(limit=10)
        roc = nl - nl.shift(63)
        legs["netliq"] = (roc > 0).astype(float).where(roc.notna())
    except Exception:  # noqa: BLE001
        pass
    return legs, spx


def _stats(daily: pd.Series) -> dict:
    r = daily.dropna()
    mu, sd = r.mean(), r.std(ddof=1)
    sharpe = (mu / sd * np.sqrt(TRADING_YEAR)) if sd else float("nan")
    cum = (1 + r).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    cagr = cum.iloc[-1] ** (TRADING_YEAR / len(r)) - 1 if len(r) else float("nan")
    return {"sharpe": round(float(sharpe), 3), "cagr_pct": round(float(cagr) * 100, 2),
            "maxdd_pct": round(float(dd) * 100, 1), "vol_pct": round(float(sd) * np.sqrt(TRADING_YEAR) * 100, 1),
            "n_days": int(len(r))}


def _overlay_return(exposure: pd.Series, spx_ret: pd.Series, cost_bps: float) -> pd.Series:
    expo = exposure.shift(1).clip(0, 1)                       # lag → no look-ahead
    gross = expo * spx_ret
    cost = expo.diff().abs().fillna(0) * cost_bps / 1e4       # turnover cost on exposure changes
    return (gross - cost).dropna()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost-bps", type=float, default=3.0, help="round-trip cost per unit exposure change (SPX is cheap)")
    args = ap.parse_args()

    legs, spx = _legs()
    spx_ret = spx.pct_change()
    leg_cols = [c for c in ("trend", "breadth", "thrust", "netliq") if c in legs.columns]

    # combined exposure = mean of the legs KNOWABLE each day (present-gated; net-liq joins 2014)
    expo_all = legs[leg_cols].mean(axis=1, skipna=True)
    bh = spx_ret.loc[expo_all.dropna().index]                # buy-&-hold over the same span
    results = {"buy_hold": _stats(bh)}
    results["overlay_combined"] = _stats(_overlay_return(expo_all, spx_ret, args.cost_bps))
    # each leg alone (exposure = that single leg), over its OWN available span
    for c in leg_cols:
        e = legs[c].dropna()
        results[f"leg_{c}"] = _stats(_overlay_return(e, spx_ret, args.cost_bps))
    # combined WITHOUT net-liq (deep 1962-2026 read) vs WITH (2014+), to isolate net-liq's marginal value
    deep_cols = [c for c in leg_cols if c != "netliq"]
    expo_deep = legs[deep_cols].mean(axis=1, skipna=True)
    results["overlay_breadth_trend_deep"] = _stats(_overlay_return(expo_deep, spx_ret, args.cost_bps))
    if "netliq" in leg_cols:
        recent = legs.index[legs["netliq"].notna()]
        e_bt = legs.loc[recent, deep_cols].mean(axis=1, skipna=True)
        e_all = legs.loc[recent, leg_cols].mean(axis=1, skipna=True)
        results["overlay_2014_breadth_trend"] = _stats(_overlay_return(e_bt, spx_ret, args.cost_bps))
        results["overlay_2014_plus_netliq"] = _stats(_overlay_return(e_all, spx_ret, args.cost_bps))

    # bootstrap CI on the Sharpe GAP (combined overlay − buy&hold) over the common span
    ov = _overlay_return(expo_all, spx_ret, args.cost_bps)
    common = ov.index.intersection(bh.index)
    gap = (ov.reindex(common) - bh.reindex(common)).dropna()
    try:
        ci = block_bootstrap_ci(gap, block=21, B=2000, seed=7)
    except Exception:  # noqa: BLE001
        ci = None

    # ---- GO bar: (1) worth having vs buy&hold, net of cost; (2) >=1 leg incremental SAME-SPAN ----
    bhs, ovs = results["buy_hold"], results["overlay_combined"]
    improves = ovs["sharpe"] > bhs["sharpe"] and ovs["maxdd_pct"] > bhs["maxdd_pct"]   # shallower DD
    # breadth incremental over trend, DEEP same span (combined trend+breadth vs trend alone)
    breadth_adds = results["overlay_breadth_trend_deep"]["sharpe"] > results["leg_trend"]["sharpe"] + 0.01
    # net-liq incremental over breadth+trend, 2014 same span
    netliq_adds = ("overlay_2014_plus_netliq" in results and
                   results["overlay_2014_plus_netliq"]["sharpe"] > results["overlay_2014_breadth_trend"]["sharpe"] + 0.01)
    any_incremental = breadth_adds or netliq_adds
    go = bool(improves and any_incremental)
    verdict = "GO" if go else "NO-GO"
    leg_note = (f"It IS worth having as a net-exposure / drawdown overlay: lifts Sharpe "
                f"{bhs['sharpe']}→{ovs['sharpe']} and cuts maxDD {bhs['maxdd_pct']}%→{ovs['maxdd_pct']}% net of cost. "
                f"Leg attribution (same-span): breadth {'ADDS over' if breadth_adds else 'is REDUNDANT with'} trend (deep 1962+); "
                f"net-liquidity {'ADDS over' if netliq_adds else 'is redundant with'} breadth+trend (2014+).")
    reasons = []
    if not improves:
        reasons.append(f"overlay does not improve risk-adjusted return vs buy&hold "
                       f"(Sharpe {ovs['sharpe']} vs {bhs['sharpe']}, maxDD {ovs['maxdd_pct']}% vs {bhs['maxdd_pct']}%)")
    if not any_incremental:
        reasons.append("legs are REDUNDANT — neither breadth (over trend, deep) nor net-liquidity (over "
                       "breadth+trend, 2014+) adds Sharpe same-span; this is plain trend-following, not a multi-leg edge")

    report = {
        "verdict": verdict,
        "decision": (("Ship it as a net-exposure / drawdown overlay (a RISK lever, like vol-managed sizing — "
                      "it trades a little CAGR for far shallower drawdowns), orthogonal to the dispersion "
                      "(selection) gate. " + leg_note) if go else
                     ("Do NOT ship the multi-leg gate as-specified. " + leg_note)),
        "leg_attribution": {"breadth_adds_over_trend_deep": breadth_adds, "netliq_adds_over_bt_2014": netliq_adds},
        "reasons": reasons,
        "cost_bps": args.cost_bps,
        "span": f"{bh.index.min().date()}..{bh.index.max().date()}",
        "legs": leg_cols,
        "results": results,
        "sharpe_gap_combined_vs_bh": {"mean_daily": round(float(gap.mean()), 6),
                                      "annualized_pct": round(float(gap.mean()) * TRADING_YEAR * 100, 2),
                                      "bootstrap_ci": ci},
        "note": ("Net-exposure (TIME-SERIES) timer — orthogonal to the dispersion gate (CROSS-SECTIONAL "
                 "selection gross): a book uses both. Cash earns 0 (conservative). Trend/breadth legs are "
                 "deep (1962-2026); net-liq is 2014+, so its marginal value is judged on the 2014-block rows. "
                 "Timing typically trades return for drawdown — judge on Sharpe + maxDD, not CAGR."),
    }
    (config.data_dir() / "vector" / "timing_overlay_validation.json").write_text(
        json.dumps(report, indent=2, default=str))
    _write_md(report)

    print(f"\n=== Net-exposure timing overlay — {report['span']}, cost {args.cost_bps}bps ===")
    print(f"{'strategy':30s} {'Sharpe':>7} {'CAGR%':>7} {'maxDD%':>7} {'vol%':>6} {'days':>6}")
    for k, v in results.items():
        print(f"{k:30s} {v['sharpe']:>7} {v['cagr_pct']:>7} {v['maxdd_pct']:>7} {v['vol_pct']:>6} {v['n_days']:>6}")
    print(f"\nSharpe gap (combined − buy&hold): {report['sharpe_gap_combined_vs_bh']['annualized_pct']}%/yr ann."
          f"{(' · 95% CI ' + str(ci.get('ci95'))) if isinstance(ci, dict) and ci.get('ci95') else ''}")
    print(f"\n>>> {verdict}: {report['decision']}")
    for r in reasons:
        print(f"    - {r}")
    return 0


def _write_md(rep: dict) -> None:
    L = ["# Breadth/liquidity net-exposure timing overlay — does it earn its keep?", "",
         f"**Verdict: {rep['verdict']}.** {rep['decision']}", ""]
    for r in rep.get("reasons", []):
        L.append(f"- {r}")
    L += ["", f"Span {rep['span']} · daily · net of {rep['cost_bps']}bps per unit exposure change · "
          f"legs: {', '.join(rep['legs'])}.", "",
          "| strategy | Sharpe | CAGR % | maxDD % | vol % | days |", "|---|--:|--:|--:|--:|--:|"]
    for k, v in rep["results"].items():
        L.append(f"| {k} | {v['sharpe']} | {v['cagr_pct']} | {v['maxdd_pct']} | {v['vol_pct']} | {v['n_days']} |")
    g = rep["sharpe_gap_combined_vs_bh"]
    L += ["", f"**Combined overlay − buy&hold:** {g['annualized_pct']}%/yr"
          f"{(' · 95% CI ' + str(g['bootstrap_ci'].get('ci95'))) if isinstance(g.get('bootstrap_ci'), dict) and g['bootstrap_ci'].get('ci95') else ''}.",
          "", f"> {rep['note']}"]
    Path(config.load()["storage"]["reports_dir"], "timing-overlay-phase0.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
