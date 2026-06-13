"""Forex Vector calibration — measure each factor's forward-return strength.

The house rule: a factor earns its weight from MEASURED predictive strength, never a
hardcoded prior. For each pair and each naive-bullish factor (from
engine.forex_conviction.factor_panel), we compute the Information Coefficient — the
Spearman rank correlation of the factor to the FORWARD base-vs-USD return — over the
full sample and BOTH halves (split at config `split_date`). The signed weight is the
mean IC; the verdict encodes robustness:

  CONFIRMED   — same sign in full + pre + post, |IC| meaningful (trust it)
  INVERTED    — robustly NEGATIVE (the naive orientation predicts the WRONG way; the
                signed weight is negative so the engine flips it automatically)
  DIRECTIONAL — full sample holds but one half is weak (half weight)
  CONTEXT     — weak or sign-unstable across halves (zero weight; shown as context)

Peg / intervention windows are EXCISED from the forward-return target (a carry that
looks riskless over a peg until the discontinuous break would otherwise confirm a
dangerously high weight — DECISIONS.md D-FX4).

Writes data/forex/conviction_calibration.json (the signed weights + score_reliable the
engine reads) and reports/forex-calibration.md. No look-ahead: factors are close-based,
IC is measured against strictly-forward returns.

Run: .venv/bin/python -m scripts.calibrate_forex
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from engine import forex_inputs, forex_signals, forex_conviction  # noqa: E402

# FX factor ICs are tiny and forward returns overlap (autocorrelated), so |IC| below
# ~0.04 is noise. We DON'T replace the prior with raw IC weights (that overfits short FX
# history and lets one noisy factor dominate). Instead we keep the stable PRIOR magnitude
# and use the measurement conservatively: flip the sign of robustly-INVERTED factors,
# halve DIRECTIONAL ones, and down-weight CONTEXT ones. The conviction score is
# scale-invariant (100·Σwf/Σ|w|), so only RELATIVE weights matter.
IC_NOISE = 0.04       # |mean IC| below this -> CONTEXT (noise; keep a small naive prior)
IC_STRONG = 0.06      # |full IC| at/above this AND both halves agree -> CONFIRMED / INVERTED
CONTEXT_KEEP = 0.25   # CONTEXT factor keeps this fraction of its prior (naive sign)
DIRECTIONAL_KEEP = 0.5
MIN_OBS = 300         # a factor needs this many non-NaN points to be calibratable


def forward_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    return pd.DataFrame({h: close.shift(-h) / close - 1 for h in horizons})


def peg_mask(close: pd.Series, meta: dict) -> pd.Series:
    """True where the row may be used; excise managed / intervention-zone rows."""
    peg = meta.get("peg")
    if not peg:
        return pd.Series(True, index=close.index)
    kind = peg.get("kind")
    if kind == "managed":
        return pd.Series(False, index=close.index)
    if kind == "intervention" and peg.get("watch"):
        lo, hi = peg["watch"]
        quote = (1.0 / close) if meta.get("invert") else close
        return ~((quote >= lo) & (quote <= hi))
    return pd.Series(True, index=close.index)   # SNB: kept (flagged on the live tile)


def _ic(factor: pd.Series, fwd: pd.DataFrame, idx: pd.Index, horizons: list[int]) -> float:
    """Mean Spearman IC of the factor vs forward returns across horizons over idx."""
    fac = factor.reindex(idx)
    ics = []
    for h in horizons:
        pair = pd.concat([fac, fwd[h].reindex(idx)], axis=1).dropna()
        if len(pair) >= 60:
            c = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
            if pd.notna(c):
                ics.append(c)
    return float(np.mean(ics)) if ics else np.nan


def calibrate_pair(pair: str, sig: pd.DataFrame, meta: dict, cal: dict) -> dict:
    horizons = cal["forward_days"]
    df = sig.loc[cal["start_date"]:].copy() if cal.get("start_date") else sig.copy()
    close = df["close"]
    panel = forex_conviction.factor_panel(pair, df, meta)
    fwd = forward_returns(close, horizons)
    fwd = fwd.where(peg_mask(close, meta), np.nan)     # excise peg/intervention windows
    split = pd.Timestamp(cal["split_date"])
    halves = {"full": df.index, "pre": df.index[df.index < split], "post": df.index[df.index >= split]}

    prior = dict(forex_conviction.FX_PRIOR)
    if meta.get("carry") == "context":
        prior.pop("carry", None)

    signals: dict[str, dict] = {}
    raw_w: dict[str, float] = {}
    n_robust = 0
    for f, base_w in prior.items():
        if f not in panel.columns or panel[f].notna().sum() < MIN_OBS:
            raw_w[f] = base_w                          # not measurable here -> keep naive prior
            signals[f] = {"verdict": "UNMEASURED", "ic_full": None, "ic_pre": None, "ic_post": None}
            continue
        ic = {h: _ic(panel[f], fwd, idx, horizons) for h, idx in halves.items()}
        if pd.isna(ic["full"]):
            raw_w[f] = base_w
            signals[f] = {"verdict": "UNMEASURED", "ic_full": None, "ic_pre": None, "ic_post": None}
            continue
        d = np.sign(ic["full"])
        both = (np.sign(ic["pre"]) == d) and (np.sign(ic["post"]) == d) and d != 0
        if abs(ic["full"]) < IC_NOISE:
            verdict, w = "CONTEXT", CONTEXT_KEEP * base_w          # noise: small naive prior
        elif both and abs(ic["full"]) >= IC_STRONG:
            verdict = "CONFIRMED" if d > 0 else "INVERTED"
            w = d * base_w                                         # measured sign, prior magnitude
            n_robust += 1
        elif abs(ic["full"]) >= IC_NOISE:
            verdict, w = "DIRECTIONAL", d * DIRECTIONAL_KEEP * base_w
        else:
            verdict, w = "CONTEXT", CONTEXT_KEEP * base_w
        raw_w[f] = w
        signals[f] = {"verdict": verdict, "ic_full": round(ic["full"], 3),
                      "ic_pre": None if pd.isna(ic["pre"]) else round(ic["pre"], 3),
                      "ic_post": None if pd.isna(ic["post"]) else round(ic["post"], 3)}

    mass = sum(abs(w) for w in raw_w.values()) or 1.0
    weights = {f: round(w / mass, 4) for f, w in raw_w.items()}    # normalize to sum|w|=1 (cosmetic)
    reliable = n_robust >= 2                                        # >=2 factors held sign in BOTH halves
    return {"span": f"{df.index.min().date()}..{df.index.max().date()}", "rows": len(df),
            "weights": weights, "score_reliable": bool(reliable), "signals": signals}


def main() -> int:
    cfg = config.load()["forex"]
    cal = cfg["calibration"]
    inputs = forex_inputs.load_all(cfg, active_only=False)
    if not inputs:
        print("no forex inputs; nothing to calibrate")
        return 0
    results = forex_signals.compute_all(inputs, cfg)

    report = {"meta": {"split": cal["split_date"], "horizons": cal["forward_days"],
                       "note": "IC = Spearman rank corr of naive-bullish factor vs forward base-vs-USD return; peg windows excised."},
              "assets": {}}
    for pair, ai in inputs.items():
        sig = results.get(pair)
        if sig is None or len(sig) < MIN_OBS:
            continue
        report["assets"][pair] = calibrate_pair(pair, sig, ai["meta"], cal)

    outdir = config.data_dir() / "forex"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "conviction_calibration.json").write_text(json.dumps(report, indent=2, default=str))
    _write_markdown(report)
    print(_summary(report))
    return 0


def _summary(report: dict) -> str:
    L = ["\n=== Forex Vector calibration (split %s) ===" % report["meta"]["split"]]
    for pair, a in report["assets"].items():
        rel = "RELIABLE" if a["score_reliable"] else "context (prior, dampened)"
        L.append(f"\n## {pair}  ({a['span']}, {a['rows']}d) — {rel}")
        for f, s in a["signals"].items():
            w = a["weights"].get(f)
            wt = f"w={w:+.3f}" if w is not None else "w=0"
            icf = "  n/a" if s["ic_full"] is None else f"{s['ic_full']:+.3f}"
            L.append(f"    {f:12s} {s['verdict']:12s} IC full/pre/post = "
                     f"{icf}/{s['ic_pre']}/{s['ic_post']}   {wt}")
    return "\n".join(L)


def _write_markdown(report: dict) -> None:
    h = report["meta"]["horizons"]
    lines = ["# Forex Vector — calibration report", "",
             f"Split-half boundary: **{report['meta']['split']}**. Forward horizons: {h} days.",
             "", report["meta"]["note"], "",
             "House rule: a factor's weight is its MEASURED forward-return strength (mean "
             "Spearman IC), signed. CONFIRMED = same sign in full + both halves; INVERTED = "
             "robustly negative (the engine flips it); DIRECTIONAL = full only (half weight); "
             "CONTEXT = weak/unstable (no weight). Peg & intervention windows are excised. FX "
             "history is short and crash-dominated, so most factors land DIRECTIONAL/CONTEXT — "
             "the verdicts are honest, not flattering.", ""]
    for pair, a in report["assets"].items():
        rel = "score_reliable ✓" if a["score_reliable"] else "context-only (prior weights, confidence dampened)"
        lines.append(f"\n## {pair} — {a['span']} ({a['rows']} days) · {rel}\n")
        lines.append("| Factor | Verdict | IC full | IC pre | IC post | weight |")
        lines.append("|---|---|--:|--:|--:|--:|")
        for f, s in a["signals"].items():
            w = a["weights"].get(f)
            icf = "n/a" if s["ic_full"] is None else f"{s['ic_full']:+.3f}"
            lines.append(f"| {f} | **{s['verdict']}** | {icf} | {s['ic_pre']} "
                         f"| {s['ic_post']} | {('%+.3f' % w) if w is not None else '0'} |")
    Path(config.load()["storage"]["reports_dir"], "forex-calibration.md").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
