"""Calibrate the commodity CONVICTION engine — measure, don't assert.

For each commodity it measures, from ~25y of history:
  1. FACTOR WEIGHTS — each naive-bullish factor's forward-return predictive strength
     (Spearman rank corr at 63d & 126d). The weight is SIGNED: sign = the measured
     polarity (so an inverted factor like oil's 12-mo trend gets a negative weight
     automatically), magnitude = |corr| damped by split-half STABILITY (a factor that
     flips sign pre/post-2013 is down-weighted — the honest treatment). Panel-factor
     weights are normalized to leave headroom for the live confirmation factors
     (cycle/mtf/alerts).
  2. CYCLE AMPLITUDE + DURATIONS — picks a per-asset ZigZag amplitude that yields
     ~14 "major" legs over the history, then records the bull/bear leg duration
     distribution (median / p25 / p75) used for the forward time-to-turn estimate.
  3. SCORE THRESHOLDS — bins the historical conviction score (built from the measured
     weights) and records forward returns per bin; sets Strong-Buy/Buy/Sell/Strong-Sell
     thresholds at score quantiles and VERIFIES the buckets are monotone in forward
     return (the honest "does a higher score actually mean higher forward return?").

Writes data/commodity/conviction_calibration.json (consumed by engine.commodity_conviction)
and reports/commodity-conviction.md.

Run: .venv/bin/python -m scripts.research_commodity_conviction
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from engine import commodity_signals, commodity_inputs  # noqa: E402
from engine import commodity_conviction as CC  # noqa: E402

SPLIT = "2013-01-01"          # split-half boundary (matches signal calibration meta)
HORIZONS = (63, 126)          # commodities are slow — judge at 3-6 months
ASSETS = ["gold", "silver", "copper", "oil"]
# total weight mass reserved for the cheap PANEL factors (the rest goes to the live
# confirmation factors cycle/mtf/alerts, added at verdict time).
PANEL_MASS = 0.80
LIVE_WEIGHTS = {"cycle": 0.10, "mtf": 0.06, "alerts": 0.04}
MIN_WEIGHT = 0.02            # floor: below this |weight| a factor is noise -> 0


def _spearman(a: pd.Series, b: pd.Series) -> float:
    m = a.notna() & b.notna()
    if m.sum() < 60:
        return float("nan")
    ra, rb = a[m].rank(), b[m].rank()
    sd = ra.std() * rb.std()
    return float(np.cov(ra, rb)[0, 1] / sd) if sd else float("nan")


def measure_weights(panel: pd.DataFrame, close: pd.Series) -> tuple[dict, dict]:
    """Signed weight per factor = polarity x |predictive strength| x stability."""
    fwd = {h: close.pct_change(h).shift(-h) for h in HORIZONS}
    pre = panel.index < pd.Timestamp(SPLIT)
    post = ~pre
    raw, diag = {}, {}
    for col in panel.columns:
        f = panel[col]
        # blended corr across horizons (126d weighted higher)
        cs = {h: _spearman(f, fwd[h]) for h in HORIZONS}
        blend = np.nanmean([cs[63], cs[126], cs[126]])      # 126d counted twice
        if not np.isfinite(blend):
            continue
        # split-half stability: same sign pre & post?
        c_pre = _spearman(f[pre], fwd[126][pre])
        c_post = _spearman(f[post], fwd[126][post])
        stable = (np.isfinite(c_pre) and np.isfinite(c_post)
                  and np.sign(c_pre) == np.sign(c_post) == np.sign(blend))
        damp = 1.0 if stable else 0.45                       # halve unstable factors
        w = float(blend) * damp
        raw[col] = w
        diag[col] = {"corr_63": round(cs[63], 3) if np.isfinite(cs[63]) else None,
                     "corr_126": round(cs[126], 3) if np.isfinite(cs[126]) else None,
                     "corr_pre": round(c_pre, 3) if np.isfinite(c_pre) else None,
                     "corr_post": round(c_post, 3) if np.isfinite(c_post) else None,
                     "stable": bool(stable), "raw_weight": round(w, 3)}
    # floor tiny weights, then normalize |w| to PANEL_MASS
    raw = {k: v for k, v in raw.items() if abs(v) >= MIN_WEIGHT}
    mass = sum(abs(v) for v in raw.values())
    weights = {k: round(v / mass * PANEL_MASS, 4) for k, v in raw.items()} if mass else {}
    weights.update(LIVE_WEIGHTS)                              # fixed live-factor weights
    return weights, diag


def measure_cycles(close: pd.Series, target_legs: int = 14) -> dict:
    """Pick the ZigZag amplitude giving ~target_legs major legs; record durations."""
    c = close.dropna()
    best = None
    for amp in [0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35, 0.40]:
        legs = CC.cycle_segments(c, amp)
        if not legs:
            continue
        if best is None or abs(len(legs) - target_legs) < abs(best[1] - target_legs):
            best = (amp, len(legs), legs)
    if best is None:
        return {}
    amp, n, legs = best

    def _stats(kind):
        d = [l["days"] for l in legs if l["kind"] == kind]
        a = [abs(l["amp"]) for l in legs if l["kind"] == kind]
        if not d:
            return {}
        return {"n": len(d), "median_d": int(np.median(d)),
                "p25_d": int(np.percentile(d, 25)), "p75_d": int(np.percentile(d, 75)),
                "median_amp_pct": round(100 * float(np.median(a)), 1)}
    return {"min_amp": amp, "n_legs": n, "bull": _stats("bull"), "bear": _stats("bear")}


def score_series(panel: pd.DataFrame, weights: dict) -> pd.Series:
    """Historical panel-only conviction score in [-100,100] (live factors excluded)."""
    cols = [c for c in panel.columns if c in weights]
    if not cols:
        return pd.Series(dtype=float, index=panel.index)
    W = pd.Series({c: weights[c] for c in cols})
    num = (panel[cols] * W).sum(axis=1, min_count=1)
    den = panel[cols].notna().mul(W.abs(), axis=1).sum(axis=1)
    return (100 * num / den.replace(0, np.nan)).clip(-100, 100)


def calibrate_thresholds(score: pd.Series, close: pd.Series) -> tuple[dict, list]:
    """Quantile thresholds + forward-126d returns per resulting action bucket."""
    fwd = close.pct_change(126).shift(-126)
    df = pd.concat([score.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(df) < 200:
        return {}, []
    qs = df["s"].quantile([0.15, 0.40, 0.60, 0.85])
    th = {"strong_sell": round(float(qs[0.15]), 1), "sell": round(float(qs[0.40]), 1),
          "buy": round(float(qs[0.60]), 1), "strong_buy": round(float(qs[0.85]), 1)}
    edges = [(-1e9, th["strong_sell"], "STRONG SELL"), (th["strong_sell"], th["sell"], "SELL"),
             (th["sell"], th["buy"], "HOLD"), (th["buy"], th["strong_buy"], "BUY"),
             (th["strong_buy"], 1e9, "STRONG BUY")]
    bins = []
    for lo, hi, name in edges:
        m = df[(df["s"] >= lo) & (df["s"] < hi)]
        if len(m):
            bins.append({"action": name, "n": int(len(m)),
                         "avg_fwd126_pct": round(100 * float(m["f"].mean()), 2),
                         "hit_pct": round(100 * float((m["f"] > 0).mean()), 1)})
    return th, bins


def main() -> int:
    res = commodity_signals.compute_all()
    inputs = commodity_inputs.load_all()
    drivers = next(iter(inputs.values()))["drivers"]
    extras = CC.load_macro_extras()

    out = {"meta": {"split": SPLIT, "horizons": list(HORIZONS),
                    "panel_mass": PANEL_MASS, "method": "spearman fwd-return, "
                    "split-half stability damped, quantile thresholds"},
           "assets": {}}
    md = ["# Commodity conviction — calibration\n",
          f"Measured forward-return predictive strength per factor (Spearman, 63d & 126d), "
          f"split-half @ {SPLIT}. Weight = polarity x |corr| x stability, normalized to "
          f"{PANEL_MASS} panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; "
          f"buckets verified monotone in forward 126d return.\n"]

    for a in ASSETS:
        sig = res[a]
        panel = CC.factor_panel(a, sig, drivers, extras)
        weights, diag = measure_weights(panel, sig["close"])
        cycles_a = measure_cycles(sig["close"])
        sc = score_series(panel, weights)
        th, bins = calibrate_thresholds(sc, sig["close"])
        mono_vals = [b["avg_fwd126_pct"] for b in bins]
        score_reliable = (len(mono_vals) >= 4
                          and all(mono_vals[i] <= mono_vals[i + 1] + 1.5
                                  for i in range(len(mono_vals) - 1))
                          and (mono_vals[-1] - mono_vals[0]) >= 6.0)
        out["assets"][a] = {"weights": weights, "thresholds": th,
                            "cycle_min_amp": cycles_a.get("min_amp"),
                            "cycle_durations": {"bull": cycles_a.get("bull", {}),
                                                "bear": cycles_a.get("bear", {})},
                            "score_reliable": bool(score_reliable),
                            "diagnostics": diag, "score_bins": bins}
        # --- report ---
        md.append(f"\n## {a.title()}\n")
        md.append("| factor | weight | corr126 | pre | post | stable |")
        md.append("|---|---:|---:|---:|---:|:--:|")
        for k, w in sorted(weights.items(), key=lambda kv: -abs(kv[1])):
            d = diag.get(k, {})
            md.append(f"| {k} | {w:+.3f} | {d.get('corr_126','—')} | {d.get('corr_pre','—')} "
                      f"| {d.get('corr_post','—')} | {'✓' if d.get('stable') else '·'} |")
        cb, cr = cycles_a.get("bull", {}), cycles_a.get("bear", {})
        md.append(f"\nCycle (amp {cycles_a.get('min_amp')}, {cycles_a.get('n_legs')} legs): "
                  f"bull median {cb.get('median_d','?')}d (n={cb.get('n','?')}, "
                  f"{cb.get('median_amp_pct','?')}%); bear median {cr.get('median_d','?')}d "
                  f"(n={cr.get('n','?')}, {cr.get('median_amp_pct','?')}%).")
        md.append("\nScore buckets (forward 126d):")
        md.append("| action | n | avg fwd126% | hit% |")
        md.append("|---|---:|---:|---:|")
        for b in bins:
            md.append(f"| {b['action']} | {b['n']} | {b['avg_fwd126_pct']:+.2f} | {b['hit_pct']} |")
        md.append(f"\nScore reliable (monotone Strong Sell → Strong Buy, spread ≥6%): "
                  f"{'✓ YES' if score_reliable else '✗ NO — weak for this asset, present as context'}")

    dpath = config.data_dir() / "commodity" / "conviction_calibration.json"
    dpath.parent.mkdir(parents=True, exist_ok=True)
    dpath.write_text(json.dumps(out, indent=2, default=str))
    rpath = config.ROOT / "reports" / "commodity-conviction.md"
    rpath.write_text("\n".join(md) + "\n")
    print(f"wrote {dpath}")
    print(f"wrote {rpath}")
    # echo the headline weights
    for a in ASSETS:
        w = out["assets"][a]["weights"]
        top = sorted(w.items(), key=lambda kv: -abs(kv[1]))[:5]
        print(f"  {a:7} top weights: " + ", ".join(f"{k} {v:+.2f}" for k, v in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
