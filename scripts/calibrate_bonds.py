"""Bonds & bond-health calibration (Phase 4) — does the health read actually
forecast trouble?

The dashboard ships a 0-100 bond-HEALTH composite whose weighting is a documented
PRIOR. This calibrator MEASURES, honestly, whether the composite and each of its
legs discriminate FORWARD bad outcomes — so the prior can be confirmed, re-weighted,
or called out. It is DISCRIMINATIVE (not a trading backtest): for each signal,
expressed as STRESS (higher = worse health), we measure the association with two
strictly-forward targets over the full sample and BOTH halves (split at
`bonds.calibration.split_date`):

  • forward 63-day equity drawdown  — depth of the worst S&P move over the next
    quarter, and P(>=10% drawdown). The better-powered target (many events).
  • recession within 12 months      — NBER (USRECD) over the next 252 trading days.
    Thin (2 recessions in the composite's ~2003+ span) — reported, not over-claimed.

Verdicts mirror the house vocabulary (calibrate_forex):
  CONFIRMED   — stress→worse-outcome, same (positive) sign in full + pre + post,
                |IC| meaningful, AND the high-stress tercile beats the base rate.
  DIRECTIONAL — full sample holds but one half is weak.
  CONTEXT     — weak or sign-unstable (the prior over-weights it).
  INVERTED    — robustly predicts the WRONG way (a red flag).

Also: a Brier reliability check on the NY-Fed recession PROBIT (does its stated
probability match the observed recession frequency?), and a composite-vs-best-leg
test (does blending beat just the measured drawdown-risk gauge?).

No look-ahead: signals are the causal engine.bonds frame; targets are strictly
forward (S&P over [t+1..t+63], NBER over [t+1..t+252]). Pure numpy/pandas (no scipy).

Writes data/bonds/calibration.json + reports/bonds-calibration.md.
Run: python -m scripts.calibrate_bonds
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

from lib import config, store  # noqa: E402
from engine import inputs, bonds  # noqa: E402
from engine.validation import brier_reliability, block_bootstrap_ci  # noqa: E402

DD_WINDOW = 63        # forward equity window (~1 quarter)
DD_THRESH = -0.10     # "drawdown" = forward worst return <= this
REC_WINDOW = 252      # forward recession window (~12 months)
MIN_OBS = 504         # a signal needs ~2y of joint obs to be calibratable
IC_STRONG = 0.10      # |full IC| at/above this AND both halves agree -> CONFIRMED
IC_WEAK = 0.05        # below this -> CONTEXT (noise)
SPLIT_DEFAULT = "2013-01-01"   # ~midpoint of the composite's live span

# signals to validate, expressed as STRESS (higher = worse health), with a prior
# weight (the live composite's) so we can emit measured-informed weights.
# keys MATCH the health-composite leg keys (engine.bonds._health_weights reads
# weights_measured by these names), value = (frame column, prior weight, label).
STRESS_LEGS = {
    "recession": ("recession_risk", 1.0, "Recession-risk composite (0-100)"),
    "drawdown": ("drawdown_risk", 1.0, "Drawdown-risk gauge (0-100, already MEASURED)"),
    "credit": ("stress_credit", 0.8, "HY-OAS credit stress (0-100)"),
    "rates_vol": ("stress_rates_vol", 0.6, "MOVE rates-vol stress (0-100)"),
    "plumbing": ("stress_plumbing", 0.4, "SOFR-IORB funding stress (0-100)"),
}
# extra diagnostic signals (not health-composite legs) validated the same way
DIAG = {
    "ny_fed_prob": ("nyfed_prob", "NY-Fed 3m10y recession probit"),
    "neg_ntfs": ("ntfs", "Near-term forward spread (sign-flipped: low = stress)"),
    "hy_oas": ("hy_oas", "High-yield OAS level (%)"),
}


def _spear(a: pd.Series, b: pd.Series) -> float:
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(j) < 60:
        return float("nan")
    return float(j["a"].rank().corr(j["b"].rank()))


def build_targets(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Strictly-forward equity-drawdown + NBER-recession targets on the frame index."""
    gspc = store.read("yahoo", "_GSPC")
    spx = (gspc["close"] if gspc is not None else store.read("yahoo", "SPY")["close"])
    spx = spx.reindex(idx.union(spx.index)).ffill().reindex(idx)
    fwd_min = spx.rolling(DD_WINDOW).min().shift(-DD_WINDOW)        # min over [t+1..t+63]
    fwd_worst = fwd_min / spx - 1.0
    out = pd.DataFrame(index=idx)
    out["dd_depth"] = (-fwd_worst).clip(lower=0)                    # positive depth
    out["dd10"] = (fwd_worst <= DD_THRESH).astype(float).where(fwd_worst.notna())
    out["fwd_ret"] = spx.shift(-DD_WINDOW) / spx - 1.0
    rec = store.read("fred", "USRECD")
    if rec is not None:
        r = rec.iloc[:, 0].reindex(idx.union(rec.index)).ffill().reindex(idx)
        out["recession_12m"] = r.rolling(REC_WINDOW).max().shift(-REC_WINDOW)
    return out


def _verdict(ic_full, ic_pre, ic_post, hi_edge) -> str:
    """hi_edge = (high-stress-tercile P(dd10)) - base rate. Positive stress IC +
    positive edge + sign-stable = CONFIRMED."""
    if ic_full is None or np.isnan(ic_full):
        return "UNMEASURED"
    d = np.sign(ic_full)
    both = (np.sign(ic_pre) == d) and (np.sign(ic_post) == d) and d != 0
    if ic_full <= -IC_WEAK and both:
        return "INVERTED"          # stress predicts the WRONG way (red flag)
    if abs(ic_full) < IC_WEAK:
        return "CONTEXT"
    if both and ic_full >= IC_STRONG and (hi_edge is None or hi_edge > 0):
        return "CONFIRMED"
    if ic_full >= IC_WEAK:
        return "DIRECTIONAL"
    return "CONTEXT"


def _conditional(sig: pd.Series, tgt: pd.DataFrame) -> dict:
    """Tercile table: P(dd10), P(recession), mean dd-depth per low/mid/high stress
    tercile, plus a block-bootstrap CI on the high-tercile dd10 rate."""
    j = pd.concat([sig.rename("s"), tgt], axis=1).dropna(subset=["s", "dd10"])
    if len(j) < MIN_OBS:
        return {}
    # rank-based terciles (method="first" breaks ties) so a signal that sits at one
    # value most of the time (e.g. plumbing stress = 0) still splits into equal groups
    # — its high tercile just won't discriminate, which is the honest CONTEXT result.
    band = pd.qcut(j["s"].rank(method="first"), 3, labels=["low", "mid", "high"])
    rows = {}
    for b in ("low", "mid", "high"):
        m = band == b
        if m.sum() < 30:
            continue
        rows[b] = {"n": int(m.sum()), "p_dd10": round(float(j.loc[m, "dd10"].mean()), 3),
                   "mean_dd_depth_pct": round(float(j.loc[m, "dd_depth"].mean()) * 100, 1),
                   "p_recession": (round(float(j.loc[m, "recession_12m"].mean()), 3)
                                   if "recession_12m" in j else None)}
    base = round(float(j["dd10"].mean()), 3)
    hi = rows.get("high", {}).get("p_dd10")
    out = {"terciles": rows, "base_p_dd10": base,
           "high_edge_pp": (round((hi - base) * 100, 1) if hi is not None else None)}
    # bootstrap CI on the high-tercile dd10 rate (block = the forward window)
    hi_mask = band == "high"
    if hi_mask.sum() >= 90:
        ci = block_bootstrap_ci(j.loc[hi_mask, "dd10"], block=DD_WINDOW, B=2000, ann=1)
        # reuse the sharpe_ci slot as a generic [p2.5,p50,p97.5] mean via a tiny wrap
        boot = j.loc[hi_mask, "dd10"].to_numpy(float)
        rng = np.random.default_rng(7)
        nb = int(np.ceil(len(boot) / DD_WINDOW))
        means = []
        for _ in range(2000):
            starts = rng.integers(0, len(boot), nb)
            idxs = (starts[:, None] + np.arange(DD_WINDOW)[None, :]).ravel()[:len(boot)] % len(boot)
            means.append(boot[idxs].mean())
        out["high_p_dd10_ci"] = [round(float(np.percentile(means, p)), 3) for p in (2.5, 50, 97.5)]
    return out


def calibrate_signal(name: str, sig: pd.Series, tgt: pd.DataFrame, split: pd.Timestamp,
                     flip: bool = False) -> dict:
    s = (-sig) if flip else sig
    joint = pd.concat([s.rename("s"), tgt["dd_depth"]], axis=1).dropna()
    if len(joint) < MIN_OBS:
        return {"verdict": "UNMEASURED", "n": len(joint)}
    span = joint.index
    pre, post = span[span < split], span[span >= split]
    ic_full = _spear(s.reindex(span), tgt["dd_depth"].reindex(span))
    ic_pre = _spear(s.reindex(pre), tgt["dd_depth"].reindex(pre))
    ic_post = _spear(s.reindex(post), tgt["dd_depth"].reindex(post))
    ic_rec = (_spear(s.reindex(span), tgt["recession_12m"].reindex(span))
              if "recession_12m" in tgt else None)
    cond = _conditional(s, tgt)
    hi_edge = cond.get("high_edge_pp")
    return {
        "desc": None, "span": f"{span.min().date()}..{span.max().date()}", "n": len(joint),
        "ic_dd_full": round(ic_full, 3), "ic_dd_pre": round(ic_pre, 3), "ic_dd_post": round(ic_post, 3),
        "ic_recession": None if ic_rec is None or np.isnan(ic_rec) else round(ic_rec, 3),
        "verdict": _verdict(ic_full, ic_pre, ic_post, hi_edge),
        "conditional": cond,
    }


# measured-informed re-weight: keep the prior magnitude, scale by the verdict
VERDICT_KEEP = {"CONFIRMED": 1.0, "DIRECTIONAL": 0.5, "CONTEXT": 0.25, "INVERTED": 0.0, "UNMEASURED": 1.0}


def main() -> int:
    bcfg = config.load()["bonds"]
    split = pd.Timestamp((bcfg.get("calibration") or {}).get("split_date", SPLIT_DEFAULT))
    f = inputs.build_features()
    fr = bonds.bonds_frame(f)
    tgt = build_targets(fr.index)
    fr = fr.assign(bond_stress=(100 - fr["health_score"]) if "health_score" in fr else np.nan)

    report = {"meta": {
        "split": str(split.date()), "dd_window_d": DD_WINDOW, "dd_threshold": DD_THRESH,
        "recession_window_d": REC_WINDOW,
        "note": "Discriminative calibration: each signal (as STRESS) vs strictly-forward S&P "
                "drawdown + NBER recession. IC = Spearman(stress, forward dd-depth). CONFIRMED "
                "needs positive sign in full+both halves AND high-tercile dd10 > base. No look-ahead."},
        "signals": {}, "diagnostics": {}}

    # the five health-composite legs + the composite itself
    for key, (col, _w, desc) in STRESS_LEGS.items():
        if col not in fr:
            continue
        r = calibrate_signal(key, fr[col], tgt, split)
        r["desc"] = desc
        report["signals"][key] = r
    if "bond_stress" in fr:
        r = calibrate_signal("composite", fr["bond_stress"], tgt, split)
        r["desc"] = "Bond-stress composite = 100 - health score (the headline)"
        report["signals"]["composite"] = r

    # diagnostic signals (curve probit / NTFS / raw HY OAS)
    for key, (col, desc) in DIAG.items():
        if col not in fr:
            continue
        r = calibrate_signal(key, fr[col], tgt, split, flip=(key == "neg_ntfs"))
        r["desc"] = desc
        report["diagnostics"][key] = r

    # measured-informed weights (keep prior, scale by verdict) for the composite legs
    raw = {}
    for key, (col, w, _d) in STRESS_LEGS.items():
        v = report["signals"].get(key, {}).get("verdict", "UNMEASURED")
        raw[key] = w * VERDICT_KEEP.get(v, 1.0)
    mass = sum(raw.values()) or 1.0
    report["weights_measured"] = {k: round(v / mass, 3) for k, v in raw.items()}
    report["weights_prior"] = {k: STRESS_LEGS[k][1] for k in STRESS_LEGS}

    # composite vs best single leg (does blending beat the best leg?)
    leg_ics = {k: report["signals"][k]["ic_dd_full"] for k in STRESS_LEGS
               if report["signals"].get(k, {}).get("ic_dd_full") is not None}
    comp_ic = report["signals"].get("composite", {}).get("ic_dd_full")
    if leg_ics and comp_ic is not None:
        best_k = max(leg_ics, key=leg_ics.get)
        report["composite_vs_best_leg"] = {
            "composite_ic": comp_ic, "best_leg": best_k, "best_leg_ic": leg_ics[best_k],
            "delta": round(comp_ic - leg_ics[best_k], 3),
            "verdict": ("composite BEATS its best single leg" if comp_ic > leg_ics[best_k] + 0.01
                        else "composite ~= best leg (blend adds little)" if comp_ic >= leg_ics[best_k] - 0.01
                        else f"best single leg ({best_k}) BEATS the composite")}

    # probit reliability: does the NY-Fed recession probability match reality?
    if "nyfed_prob" in fr and "recession_12m" in tgt:
        j = pd.concat([fr["nyfed_prob"].rename("p"), tgt["recession_12m"].rename("y")], axis=1).dropna()
        if len(j) >= 100:
            report["probit_reliability"] = brier_reliability(j["p"].to_numpy(), j["y"].to_numpy(), n_bins=5)

    outdir = config.data_dir() / "bonds"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "calibration.json").write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    _write_markdown(report)
    print(_summary(report))
    return 0


def _summary(r: dict) -> str:
    L = [f"\n=== Bonds calibration (split {r['meta']['split']}; target = forward "
         f"{DD_WINDOW}d S&P drawdown + {REC_WINDOW}d NBER recession) ==="]
    def row(k, s):
        c = s.get("conditional", {})
        edge = c.get("high_edge_pp")
        edge_s = f"hi-tercile dd10 {c.get('terciles', {}).get('high', {}).get('p_dd10')} vs base {c.get('base_p_dd10')} ({'+' if (edge or 0)>=0 else ''}{edge}pp)" if c else "—"
        return (f"  {k:15s} {s.get('verdict','?'):11s} IC dd full/pre/post = "
                f"{s.get('ic_dd_full')}/{s.get('ic_dd_pre')}/{s.get('ic_dd_post')}  "
                f"IC rec {s.get('ic_recession')}  | {edge_s}")
    L.append("\n-- health-composite legs --")
    for k in list(STRESS_LEGS) + ["composite"]:
        if k in r["signals"]:
            L.append(row(k, r["signals"][k]))
    L.append("\n-- diagnostics --")
    for k, s in r.get("diagnostics", {}).items():
        L.append(row(k, s))
    cb = r.get("composite_vs_best_leg")
    if cb:
        L.append(f"\nComposite vs best leg: composite IC {cb['composite_ic']} vs {cb['best_leg']} "
                 f"{cb['best_leg_ic']} (Δ{cb['delta']:+}) => {cb['verdict']}")
    pr = r.get("probit_reliability")
    if pr:
        L.append(f"NY-Fed probit reliability: Brier {pr.get('brier')} vs base {pr.get('base_brier')} "
                 f"(skill {pr.get('skill_score')}); base recession rate {pr.get('base_rate')}")
    L.append("\nMeasured-informed leg weights: " + ", ".join(
        f"{k} {r['weights_measured'][k]}" for k in r["weights_measured"]))
    L.append("(prior: " + ", ".join(f"{k} {r['weights_prior'][k]}" for k in r["weights_prior"]) + ")")
    return "\n".join(L)


def _write_markdown(r: dict) -> None:
    m = r["meta"]
    L = ["# Bonds & bond-health — calibration report", "",
         f"Split-half boundary **{m['split']}**. Target: forward **{DD_WINDOW}-day** S&P max "
         f"drawdown (and P(>={int(-DD_THRESH*100)}% drawdown)) + **{REC_WINDOW}-day** forward NBER "
         "recession.", "", m["note"], "",
         "Verdicts: **CONFIRMED** = stress→worse outcome, positive sign in full + both halves, "
         "|IC|≥0.10, and the high-stress tercile beats the base drawdown rate; **DIRECTIONAL** = "
         "full only; **CONTEXT** = weak/unstable (the prior over-weights it); **INVERTED** = predicts "
         "the wrong way. The composite's live span is ~2003+ (term-premium-limited), so the "
         "recession target is thin — the drawdown target carries the weight.", ""]

    def table(title, sigs):
        L.append(f"\n## {title}\n")
        L.append("| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |")
        L.append("|---|---|---|--:|---|---|--:|")
        for k, s in sigs.items():
            c = s.get("conditional", {})
            hi = c.get("terciles", {}).get("high", {}).get("p_dd10")
            base = c.get("base_p_dd10")
            edge = c.get("high_edge_pp")
            cell = f"{hi} vs {base} ({'+' if (edge or 0)>=0 else ''}{edge}pp)" if hi is not None else "—"
            ics = f"{s.get('ic_dd_full')}/{s.get('ic_dd_pre')}/{s.get('ic_dd_post')}"
            L.append(f"| {k} ({s.get('desc','')}) | **{s.get('verdict','?')}** | {ics} | "
                     f"{s.get('ic_recession')} | {cell} | {s.get('span','—')} | {s.get('n','—')} |")

    table("Health-composite legs + the composite", {k: r["signals"][k] for k in
          list(STRESS_LEGS) + ["composite"] if k in r["signals"]})
    table("Diagnostic curve signals", r.get("diagnostics", {}))

    cb = r.get("composite_vs_best_leg")
    if cb:
        L += ["", "## Does the blend beat the best single leg?", "",
              f"Composite IC **{cb['composite_ic']}** vs best leg `{cb['best_leg']}` "
              f"**{cb['best_leg_ic']}** (Δ {cb['delta']:+}). **{cb['verdict']}.**"]
    pr = r.get("probit_reliability")
    if pr:
        L += ["", "## NY-Fed recession-probit reliability", "",
              f"Brier **{pr.get('brier')}** vs base-rate climatology {pr.get('base_brier')} "
              f"(skill score {pr.get('skill_score')}; base recession rate {pr.get('base_rate')}). "
              "Reliability curve (predicted vs observed):", "",
              "| prob bin | n | predicted | observed |", "|---|--:|--:|--:|"]
        for b in pr.get("reliability", []):
            L.append(f"| {b['bin']} | {b['n']} | {b['pred']} | {b['obs']} |")

    L += ["", "## Measured-informed leg weights", "",
          "Keep the prior magnitude, scale by the verdict (CONFIRMED 1.0 · DIRECTIONAL 0.5 · "
          "CONTEXT 0.25 · INVERTED 0.0), renormalized:", "",
          "| leg | prior | measured |", "|---|--:|--:|"]
    for k in r["weights_measured"]:
        L.append(f"| {k} | {r['weights_prior'][k]} | {r['weights_measured'][k]} |")
    L += ["", "_If a leg lands CONTEXT, the live composite (a prior) over-weights it; adopt the "
          "measured weights in `config.yml bonds.health.weights` only if they also hold on the next "
          "refresh. The recession/drawdown legs are the measured backbone._"]
    Path(config.load()["storage"]["reports_dir"], "bonds-calibration.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
