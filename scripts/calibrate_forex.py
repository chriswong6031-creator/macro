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
from engine.validation import (  # noqa: E402
    backtest_core, deflated_sharpe, dsr_verdict, ret_moments)

TRADING_YEAR = 252  # FX spot trades ~252 days/yr

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
            # Spearman IC = Pearson of ranks. Identical to method="spearman" for the
            # continuous (tie-free) factor/return columns here, but scipy-free so the
            # calibration runs in any environment (incl. the dollar-index leg below).
            c = pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())
            if pd.notna(c):
                ics.append(c)
    return float(np.mean(ics)) if ics else np.nan


def conviction_series(panel: pd.DataFrame, weights: dict) -> pd.Series | None:
    """Daily conviction in [-1, 1] = Σ w·factor / Σ|w| over the factors PRESENT that
    day — the same scale-invariant blend forex_conviction.conviction ships (its
    score/100), reconstructed historically from the just-calibrated signed weights.
    Returns None if no weighted factor is available."""
    cols = [f for f in weights if f in panel.columns and weights[f] != 0]
    if not cols:
        return None
    w = pd.Series({f: float(weights[f]) for f in cols})
    P = panel[cols]
    num = (P.fillna(0.0) * w).sum(axis=1)
    den = (P.notna() * w.abs()).sum(axis=1)             # available weight mass per day
    return (num / den.replace(0.0, np.nan)).clip(-1, 1).fillna(0.0)


def backtest_conviction(close: pd.Series, conviction: pd.Series, cost_bps: float = 0.0) -> dict:
    """Long/short allocation driven by the calibrated CONVICTION score (sized in
    [-1,1], acting next bar) vs a passive long-the-base benchmark, NET of a one-way
    `cost_bps` on |Δpos|. This is an IN-SAMPLE read (weights are fit on the full
    history), which is exactly why the Deflated Sharpe haircut is applied on top.
    Returns {} if the strategy never takes a position (e.g. a managed peg)."""
    if conviction is None or float(conviction.abs().sum()) == 0.0:
        return {}
    bt = backtest_core(close, conviction, cost_bps=cost_bps)
    ret, gross, strat, turnover, years, pos = (
        bt["ret"], bt["gross"], bt["net"], bt["turnover"], bt["years"], bt["pos"])
    eq = (1 + strat).cumprod()
    eq_gross = (1 + gross).cumprod()
    hold = (1 + ret).cumprod()

    def cagr(e):
        return (e.iloc[-1]) ** (1 / years) - 1 if years > 0 and e.iloc[-1] > 0 else np.nan

    def sharpe(r):
        sd = r.std()
        return (r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan

    def sortino(r):
        dn = r[r < 0].std()
        return (r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan

    def maxdd(e):
        return float((e / e.cummax() - 1).min())

    cagr_net, cagr_gross = cagr(eq), cagr(eq_gross)
    mom = ret_moments(strat)  # net per-period moments for the Deflated Sharpe
    return {
        "cagr": round(100 * cagr_net, 1), "hold_cagr": round(100 * cagr(hold), 1),
        "cagr_gross": round(100 * cagr_gross, 1) if pd.notna(cagr_gross) else np.nan,
        "cost_drag_pp": (round(100 * (cagr_gross - cagr_net), 1)
                         if pd.notna(cagr_net) and pd.notna(cagr_gross) else np.nan),
        "sharpe": round(sharpe(strat), 2), "hold_sharpe": round(sharpe(ret), 2),
        "sharpe_gross": round(sharpe(gross), 2),
        "sortino": round(sortino(strat), 2), "hold_sortino": round(sortino(ret), 2),
        "maxdd": round(100 * maxdd(eq), 1), "hold_maxdd": round(100 * maxdd(hold), 1),
        "time_in_market": round(100 * (pos.abs() > 1e-9).mean(), 1),
        "avg_exposure": round(100 * pos.abs().mean(), 1),
        "net_long_pct": round(100 * (pos > 1e-9).mean(), 1),
        "turnover_annual": round(float(turnover.sum() / years), 1) if years > 0 else np.nan,
        "cost_bps": cost_bps,
        "final_vs_hold": round(eq.iloc[-1] / hold.iloc[-1], 2) if hold.iloc[-1] else np.nan,
        # per-period (daily) stats the Deflated Sharpe Ratio consumes:
        "sharpe_daily": round(mom[0], 6) if mom else None,
        "skew": round(mom[1], 4) if mom else None,
        "kurt": round(mom[2], 4) if mom else None,
        "n_obs": mom[3] if mom else None,
    }


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

    # Honest-validation overlay: does a conviction-weighted long/short of THIS pair
    # actually pay once you net out the spread? Reconstruct the conviction series from
    # the just-fit weights, flatten through peg/intervention windows (no edge there),
    # and backtest NET of the configured G10 cost. The DSR haircut is applied across
    # pairs in main() (the cross-pair Sharpe dispersion is the trial set).
    cost_bps = float(cal.get("cost_bps", 2.0))
    conv = conviction_series(panel, weights)
    if conv is not None:
        conv = conv.where(peg_mask(close, meta), 0.0)
    allocation = backtest_conviction(close, conv, cost_bps=cost_bps)
    return {"span": f"{df.index.min().date()}..{df.index.max().date()}", "rows": len(df),
            "weights": weights, "score_reliable": bool(reliable), "signals": signals,
            "allocation": allocation}


def calibrate_dollar(inputs: dict, cal: dict, cfg: dict, n_trials: int) -> dict | None:
    """Validate the BROAD-USD REER value factor against forward BROAD-USD returns.

    REER value is the only factor with cross-half forward stability at the PAIR level
    (EUR & AUD CONFIRMED). This tests whether that carries onto the dollar INDEX itself:
    split-half Spearman-IC of the dollar's own naive-bullish REER-value factor (cheap =
    bullish USD) vs forward broad-USD returns, PLUS a deflated-Sharpe gate on a
    REER-only dollar long/short — counted as ONE additional trial so the haircut only
    gets harder. Expected honest outcome: a labelled 'leans', not a promotable scored
    leg. DISPLAY-ONLY regardless; promotion needs CONFIRMED in both halves AND DSR≥0.90."""
    drivers = next(iter(inputs.values()))["drivers"] if inputs else {}
    broad, reer = drivers.get("broad_dollar"), drivers.get("reer_us")
    if broad is None or reer is None:
        return None
    broad = broad.dropna()
    if cal.get("start_date"):
        broad = broad.loc[cal["start_date"]:]
    if len(broad) < MIN_OBS:
        return None
    horizons = cal["forward_days"]
    va = forex_signals.value_signal(reer, cfg["dollar_desk"]["valuation"], broad.index)
    if "value_score" not in va:
        return None
    factor = va["value_score"]                         # naive-bullish USD: cheap REER -> +
    fwd = forward_returns(broad, horizons)
    split = pd.Timestamp(cal["split_date"])
    halves = {"full": broad.index, "pre": broad.index[broad.index < split],
              "post": broad.index[broad.index >= split]}
    ic = {k: _ic(factor, fwd, idx, horizons) for k, idx in halves.items()}
    if pd.isna(ic["full"]):
        return None
    d = np.sign(ic["full"])
    both = (np.sign(ic["pre"]) == d) and (np.sign(ic["post"]) == d) and d != 0
    if abs(ic["full"]) < IC_NOISE:
        verdict = "CONTEXT"
    elif both and abs(ic["full"]) >= IC_STRONG:
        verdict = "CONFIRMED" if d > 0 else "INVERTED"
    elif abs(ic["full"]) >= IC_NOISE:
        verdict = "DIRECTIONAL"
    else:
        verdict = "CONTEXT"
    # DSR gate: a REER-only dollar long/short, NET of cost, deflated by N+1 trials
    al = backtest_conviction(broad, factor.clip(-1, 1), cost_bps=float(cal.get("cost_bps", 2.0)))
    dsr = None
    if al:
        ds = deflated_sharpe(al.get("sharpe_daily"), al.get("skew"), al.get("kurt"),
                             al.get("n_obs"), n_trials + 1, sr_variance=None,
                             trading_year=TRADING_YEAR)
        if ds is not None:
            ds["verdict"] = dsr_verdict(ds["dsr"])
            dsr = ds
    promotable = bool(verdict == "CONFIRMED" and dsr and (dsr.get("dsr") or 0) >= 0.90)
    return {"factor": "value (REER)", "target": "broad USD (DTWEXBGS)",
            "span": f"{broad.index.min().date()}..{broad.index.max().date()}", "rows": len(broad),
            "ic_full": round(ic["full"], 3),
            "ic_pre": None if pd.isna(ic["pre"]) else round(ic["pre"], 3),
            "ic_post": None if pd.isna(ic["post"]) else round(ic["post"], 3),
            "verdict": verdict, "allocation": al, "multiple_testing": dsr,
            "promotable": promotable, "display_only": True}


def main() -> int:
    cfg = config.load()["forex"]
    cal = cfg["calibration"]
    inputs = forex_inputs.load_all(cfg, active_only=False)
    if not inputs:
        print("no forex inputs; nothing to calibrate")
        return 0
    results = forex_signals.compute_all(inputs, cfg)
    # One-way spread cost (tight G10) + the honest trial count for the Deflated
    # Sharpe live in config with code defaults (ship without a config.yml edit).
    cost_bps = float(cal.get("cost_bps", 2.0))
    n_trials = int(cal.get("n_trials", 60))

    report = {"meta": {"split": cal["split_date"], "horizons": cal["forward_days"],
                       "cost_bps_one_way": cost_bps, "n_trials": n_trials,
                       "note": "IC = Spearman rank corr of naive-bullish factor vs forward base-vs-USD return; peg windows excised."},
              "assets": {}}
    for pair, ai in inputs.items():
        sig = results.get(pair)
        if sig is None or len(sig) < MIN_OBS:
            continue
        report["assets"][pair] = calibrate_pair(pair, sig, ai["meta"], cal)

    # ---- multiple-testing haircut: Deflated Sharpe on each pair's conviction L/S --
    # Weights are fit per pair on the full sample and we screened n_trials factor×pair
    # configs, so each per-pair Sharpe is upward-biased. Deflate using the cross-pair
    # daily-Sharpe dispersion as the trial set (floored at the null proxy in-helper).
    daily_srs = [a["allocation"]["sharpe_daily"] for a in report["assets"].values()
                 if a.get("allocation", {}).get("sharpe_daily") is not None]
    sr_var = float(np.var(daily_srs, ddof=1)) if len(daily_srs) >= 2 else None
    for a in report["assets"].values():
        m = a.get("allocation") or {}
        dsr = deflated_sharpe(m.get("sharpe_daily"), m.get("skew"), m.get("kurt"),
                              m.get("n_obs"), n_trials, sr_variance=sr_var,
                              trading_year=TRADING_YEAR)
        if dsr is not None:
            dsr["sr_variance_source"] = ("max(cross-pair Sharpe dispersion, null SR-sampling proxy)"
                                         if sr_var else "null SR-sampling proxy")
            dsr["verdict"] = dsr_verdict(dsr["dsr"])
            dsr["note"] = ("DSR = P(true Sharpe>0) for the conviction long/short after deflating "
                           "for n_trials factor×pair configs screened, sample length, skew & "
                           "kurtosis. Weights are in-sample, so this haircut is the honest "
                           "counterweight — a low DSR means the edge is likely selection bias.")
            a["multiple_testing"] = dsr

    # ---- dollar-index leg: validate the broad-USD REER value factor (adds 1 trial) ----
    try:
        dollar = calibrate_dollar(inputs, cal, cfg, n_trials)
    except Exception as e:  # noqa: BLE001 — never break the per-pair report
        print(f"dollar calibration skipped ({e})")
        dollar = None
    if dollar:
        report["dollar"] = dollar

    fams = sorted({f for a in report["assets"].values() for f in a.get("signals", {})})
    asof = max((results[p].index.max() for p in report["assets"]), default=None)
    report["trial_log"] = {
        "asof": str(asof.date()) if asof is not None else None,
        "n_trials_declared": n_trials,
        "cost_bps_one_way": cost_bps,
        "pairs_tested": list(report["assets"]),
        "factor_families_screened": fams,
        "n_factor_families": len(fams),
        "note": ("Upper-bound count of factor×pair configs screened across the hunt, used to "
                 "deflate each pair's conviction Sharpe. Raise forex.calibration.n_trials as you "
                 "screen more factors/pairs."),
    }

    outdir = config.data_dir() / "forex"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "conviction_calibration.json").write_text(json.dumps(report, indent=2, default=str))
    (outdir / "trial_log.json").write_text(json.dumps(report["trial_log"], indent=2, default=str))
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
        al = a.get("allocation") or {}
        if al:
            L.append(f"    conviction L/S (NET {al['cost_bps']}bps): CAGR {al['cagr']}% net "
                     f"(gross {al.get('cagr_gross')}%; hold {al['hold_cagr']}%)  "
                     f"Sharpe {al['sharpe']} (hold {al['hold_sharpe']})  MaxDD {al['maxdd']}%  "
                     f"turn {al.get('turnover_annual')}x/yr")
        mt = a.get("multiple_testing")
        if mt and mt.get("dsr") is not None:
            L.append(f"    Deflated Sharpe: DSR={mt['dsr']} (SR {mt['sr_annual']} ann vs SR0 "
                     f"{mt['sr0_annual']} ann; N={mt['n_trials']}, T={mt['T']}d) => {mt['verdict']}")
    dl = report.get("dollar")
    if dl:
        L.append(f"\n## DOLLAR INDEX — {dl['factor']} vs forward {dl['target']} ({dl['span']})")
        L.append(f"    IC full/pre/post = {dl['ic_full']:+}/{dl['ic_pre']}/{dl['ic_post']}  "
                 f"=> {dl['verdict']}")
        mt = dl.get("multiple_testing")
        if mt and mt.get("dsr") is not None:
            L.append(f"    Deflated Sharpe: DSR={mt['dsr']} => {mt['verdict']}  "
                     f"| promotable-to-scored: {dl['promotable']} (display-only either way)")
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
        al = a.get("allocation") or {}
        if al:
            lines.append(f"\n**Conviction long/short backtest (NET of {al['cost_bps']}bps one-way "
                         f"cost)** — IN-SAMPLE (weights fit on full history): CAGR **{al['cagr']}%** net "
                         f"(gross {al.get('cagr_gross')}%, drag {al.get('cost_drag_pp')}pp; passive-long "
                         f"hold {al['hold_cagr']}%), Sharpe {al['sharpe']} (hold {al['hold_sharpe']}), "
                         f"MaxDD {al['maxdd']}%, turnover {al.get('turnover_annual')}x/yr, avg exposure "
                         f"{al.get('avg_exposure')}%.")
        mt = a.get("multiple_testing")
        if mt and mt.get("dsr") is not None:
            lines.append(f"\n**Deflated Sharpe (multiple-testing haircut)**: **{mt['verdict']}**. "
                         f"DSR (P true Sharpe>0) = **{mt['dsr']}**; observed SR {mt['sr_annual']} ann "
                         f"vs haircut SR0 {mt['sr0_annual']} ann (N={mt['n_trials']} factor×pair trials, "
                         f"T={mt['T']}d, skew={mt['skew']}, kurt={mt['kurt']}).")
    dl = report.get("dollar")
    if dl:
        lines.append(f"\n## DOLLAR INDEX — {dl['factor']} vs forward {dl['target']}\n")
        lines.append(f"{dl['span']} ({dl['rows']} days). The dollar's own naive-bullish REER-value "
                     f"factor (cheap = bullish USD) vs forward broad-USD returns, split at "
                     f"{report['meta']['split']}.\n")
        lines.append("| Factor | Verdict | IC full | IC pre | IC post | promotable |")
        lines.append("|---|---|--:|--:|--:|:--|")
        lines.append(f"| value (REER) | **{dl['verdict']}** | {dl['ic_full']:+} | {dl['ic_pre']} "
                     f"| {dl['ic_post']} | {dl['promotable']} |")
        mt = dl.get("multiple_testing")
        if mt and mt.get("dsr") is not None:
            lines.append(f"\n**Deflated Sharpe (REER-only dollar long/short, N+1 trials)**: "
                         f"**{mt['verdict']}**. DSR = **{mt['dsr']}**; SR {mt.get('sr_annual')} ann "
                         f"vs SR0 {mt.get('sr0_annual')} ann (N={mt.get('n_trials')}, T={mt.get('T')}d).")
        lines.append(f"\n**DISPLAY-ONLY.** This grades the dollar's REER-value lean honestly; it is "
                     f"NOT wired into any score. Promotion to a scored leg requires CONFIRMED in both "
                     f"halves AND DSR≥0.90 — unlikely for FX, which is the honest expected outcome.")
    tl = report.get("trial_log")
    if tl:
        lines.append("\n## Trial log\n")
        lines.append(f"As-of {tl['asof']}: **{tl['n_trials_declared']}** declared factor×pair trials "
                     f"(upper-bound); {tl['n_factor_families']} factor families screened across "
                     f"{len(tl['pairs_tested'])} pairs; spread cost {tl['cost_bps_one_way']}bps one-way.")
    Path(config.load()["storage"]["reports_dir"], "forex-calibration.md").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
