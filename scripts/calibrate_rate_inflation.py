"""Rate & inflation TRANSMISSION calibration — measure the cross-asset pass-through,
and honestly test whether any rate/inflation leg earns a SCORED tier.

The dashboard already SCORES the validated rate/inflation legs that have forward
content (breakeven direction + TIPS-nominal momentum in the inflation axis; real
yields for commodities/BTC; the term-premium-adjusted curve in recession-risk). This
calibrator does two NEW things, both leakage-free:

  1. TRANSMISSION MATRIX (display-only coefficients). For every rate/inflation DRIVER
     (real-rate level & 63d SPEED, nominal-rate speed, breakeven level & change, 5y5y,
     the TP-adjusted curve, the us2y-funds policy gap, the core-PCE-vs-2%-target gap,
     a 3m-vs-12m inflation re-acceleration read, and a market-vs-model expectations
     wedge) measured against the strictly-FORWARD return of every asset class we track
     (broad equities, growth/duration/financial/energy/defensive sectors, gold, oil,
     copper, the dollar, bitcoin, long Treasuries, China). The signed Spearman IC
     (full + both halves) becomes the per-cell headwind/tailwind coefficient + a
     CONFIRMED/DIRECTIONAL/CONTEXT/INVERTED verdict. These FEED the display-only
     transmission engine — never a score.

  2. SCORED-LEG GATE (the honest "attempt"). A curated set of rate/inflation RISK
     drivers (expressed as STRESS, higher = more risk-off) is run through the SAME
     discriminative gate the bond-health legs must pass (calibrate_bonds): IC vs the
     forward 63d S&P drawdown depth, sign-stable in full + both purged halves, |IC|
     meaningful, AND the high-stress tercile's P(>=10% drawdown) beats the base rate
     with a block-bootstrap CI that clears it. Each is ALSO put through the strict
     return-forecast bar (Clark-West / OOS-R2 vs the expanding mean) so we can say,
     honestly, whether it predicts the LEVEL of returns (it usually does not — only
     the left-tail RISK). Only a leg that passes the discriminative gate is PROPOSED
     for a scored MRS/drawdown leg (gated in config, adopted only if it holds on the
     next refresh — the same restraint as bonds). VIF/correlation vs the already-scored
     legs is reported so we never double-count.

No look-ahead: drivers are the causal engine.inputs frame (rolling windows ending at
t, or t-h..t changes); targets are strictly forward (asset over [t+1..t+h], NBER over
[t+1..t+252]). Pure numpy/pandas. Writes data/transmission/calibration.json +
reports/rate-inflation-transmission-calibration.md.

Run: python -m scripts.calibrate_rate_inflation
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
from engine import inputs  # noqa: E402
from engine.rate_inflation_transmission import (build_drivers, DRIVERS_META,  # noqa: E402
                                                ASSETS_META)
from engine.validation import (clark_west, oos_r2,  # noqa: E402
                               purged_folds, fold_robust, vif, top_correlated_pairs)

H = 63                # primary forward horizon (~1 quarter)
DD_WINDOW = 63        # forward equity drawdown window
DD_THRESH = -0.10     # "drawdown" = forward worst return <= this
REC_WINDOW = 252      # forward recession window (~12m)
MIN_OBS = 504         # ~2y of joint obs to be calibratable
IC_STRONG = 0.10      # |full IC| at/above this AND both halves agree -> CONFIRMED
IC_WEAK = 0.04        # below this -> CONTEXT (noise)
ZWIN = 504            # trailing window for level z-scores
SPLIT_DEFAULT = "2015-01-01"

# DRIVERS + ASSETS are defined ONCE in the engine (the single source of truth the live
# transmission leaf and this calibrator share); we derive the labelled asset list here.
DRIVER_LABELS = {k: v[0] for k, v in DRIVERS_META.items()}
ASSETS = [(tkr, en, kind) for tkr, (en, _zh, kind) in ASSETS_META.items()]


def _spear(a: pd.Series, b: pd.Series, min_n: int = 120) -> float:
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(j) < min_n:
        return float("nan")
    return float(j["a"].rank().corr(j["b"].rank()))


def asset_fwd_returns(idx: pd.DatetimeIndex, horizon: int = H) -> pd.DataFrame:
    """Strictly-forward horizon return per asset on the frame index."""
    closes = inputs.yahoo_closes()
    out = pd.DataFrame(index=idx)
    for tkr, _lbl, _kind in ASSETS:
        s = closes.get(tkr)
        if s is None:
            out[tkr] = np.nan
            continue
        s = s[~s.index.duplicated(keep="last")].sort_index()
        s = s.reindex(idx.union(s.index)).ffill().reindex(idx)
        out[tkr] = s.shift(-horizon) / s - 1.0          # return over [t+1..t+h]
    return out


def equity_targets(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward S&P drawdown depth + P(dd>=10%) + 12m NBER (the risk-gate targets)."""
    gspc = store.read("yahoo", "_GSPC")
    spx = (gspc["close"] if gspc is not None else inputs.yahoo_closes().get("SPY"))
    spx = spx[~spx.index.duplicated(keep="last")].sort_index()
    spx = spx.reindex(idx.union(spx.index)).ffill().reindex(idx)
    fwd_worst = spx.rolling(DD_WINDOW).min().shift(-DD_WINDOW) / spx - 1.0
    out = pd.DataFrame(index=idx)
    out["dd_depth"] = (-fwd_worst).clip(lower=0)
    out["dd10"] = (fwd_worst <= DD_THRESH).astype(float).where(fwd_worst.notna())
    rec = store.read("fred", "USRECD")
    if rec is not None:
        r = rec.iloc[:, 0].reindex(idx.union(rec.index)).ffill().reindex(idx)
        out["recession_12m"] = r.rolling(REC_WINDOW).max().shift(-REC_WINDOW)
    return out


# --------------------------------------------------------------------------- #
# 1) TRANSMISSION MATRIX — signed IC of each driver vs each asset's forward return
# --------------------------------------------------------------------------- #
def _cell_verdict(ic_full, ic_pre, ic_post) -> str:
    if ic_full is None or np.isnan(ic_full):
        return "UNMEASURED"
    d = np.sign(ic_full)
    both = (np.sign(ic_pre) == d) and (np.sign(ic_post) == d) and d != 0
    half_ok = abs(ic_pre) >= IC_WEAK and abs(ic_post) >= IC_WEAK
    if abs(ic_full) < IC_WEAK:
        return "CONTEXT"
    if both and half_ok and abs(ic_full) >= IC_STRONG:
        return "CONFIRMED"
    if abs(ic_full) >= IC_WEAK and both:
        return "DIRECTIONAL"
    return "CONTEXT"


def transmission_matrix(drivers: pd.DataFrame, fwd: pd.DataFrame,
                        split: pd.Timestamp) -> dict:
    matrix = {}
    for drv in drivers.columns:
        s = drivers[drv]
        row = {}
        for tkr, lbl, kind in ASSETS:
            tgt = fwd[tkr]
            joint = pd.concat([s.rename("s"), tgt.rename("t")], axis=1).dropna()
            if len(joint) < MIN_OBS:
                row[tkr] = {"label": lbl, "kind": kind, "verdict": "UNMEASURED",
                            "n": len(joint)}
                continue
            span = joint.index
            pre = span[span < split]
            pre = pre[:-H] if len(pre) > H else pre        # purge the forward-window leak
            post = span[span >= split]
            ic_f = _spear(s.reindex(span), tgt.reindex(span))
            ic_pre = _spear(s.reindex(pre), tgt.reindex(pre))
            ic_post = _spear(s.reindex(post), tgt.reindex(post))
            row[tkr] = {
                "label": lbl, "kind": kind, "n": int(len(joint)),
                "ic": None if np.isnan(ic_f) else round(ic_f, 3),
                "ic_pre": None if np.isnan(ic_pre) else round(ic_pre, 3),
                "ic_post": None if np.isnan(ic_post) else round(ic_post, 3),
                "verdict": _cell_verdict(ic_f, ic_pre, ic_post),
                "effect": ("tailwind" if (ic_f or 0) > 0 else "headwind") if abs(ic_f or 0) >= IC_WEAK else "neutral",
            }
        matrix[drv] = {"label": DRIVER_LABELS.get(drv, drv), "assets": row}
    return matrix


# --------------------------------------------------------------------------- #
# 2) SCORED-LEG GATE — risk drivers as STRESS vs forward S&P drawdown (calibrate_bonds
#    discipline) + the strict return-forecast bar (Clark-West / OOS-R2).
# --------------------------------------------------------------------------- #
# (driver, stress_sign, label). stress_sign multiplies the driver so higher = worse
# (tightening / inflation pressure = risk-off). +1 keeps it; -1 flips.
SCORED_CANDIDATES = [
    ("real10y_chg63", +1, "Real-rate SPEED (63d rise) — 'speed breaks equities'"),
    ("real10y", +1, "Real-rate LEVEL (high real yields)"),
    ("corepce_gap", +1, "Core-PCE-vs-target gap (sticky inflation)"),
    ("infl_accel", +1, "Inflation re-acceleration (3m>12m)"),
    ("exp_wedge", +1, "Expectations unanchoring (market>model)"),
    ("curve_tp_adj", -1, "TP-adjusted curve inversion (flip: low=stress)"),
    ("nom10y_chg63", +1, "Nominal-rate SPEED (63d rise)"),
]


def _tercile_edge(stress: pd.Series, eq: pd.DataFrame) -> dict:
    j = pd.concat([stress.rename("s"), eq], axis=1).dropna(subset=["s", "dd10"])
    if len(j) < MIN_OBS:
        return {}
    band = pd.qcut(j["s"].rank(method="first"), 3, labels=["low", "mid", "high"])
    rows = {}
    for b in ("low", "mid", "high"):
        m = band == b
        if m.sum() < 30:
            continue
        rows[b] = {"n": int(m.sum()), "p_dd10": round(float(j.loc[m, "dd10"].mean()), 3),
                   "mean_dd_depth_pct": round(float(j.loc[m, "dd_depth"].mean()) * 100, 1)}
    base = round(float(j["dd10"].mean()), 3)
    hi = rows.get("high", {}).get("p_dd10")
    out = {"terciles": rows, "base_p_dd10": base,
           "high_edge_pp": (round((hi - base) * 100, 1) if hi is not None else None)}
    hi_mask = band == "high"
    if hi_mask.sum() >= 90:
        boot = j.loc[hi_mask, "dd10"].to_numpy(float)
        rng = np.random.default_rng(7)
        nb = int(np.ceil(len(boot) / DD_WINDOW))
        means = []
        for _ in range(2000):
            st = rng.integers(0, len(boot), nb)
            ix = (st[:, None] + np.arange(DD_WINDOW)[None, :]).ravel()[:len(boot)] % len(boot)
            means.append(boot[ix].mean())
        out["high_p_dd10_ci"] = [round(float(np.percentile(means, p)), 3) for p in (2.5, 50, 97.5)]
    return out


def _causal_return_forecast(x: pd.Series, r: pd.Series, horizon: int,
                            win: int = 756, min_p: int = 252) -> pd.Series:
    """Leakage-free return forecast from a single driver via a rolling OLS. At time t
    only the (x_{t-h}, r_{t-h}) pairs are FULLY REALIZED (r_{t-h} spans [t-h+1..t], known
    by t), so we estimate alpha/beta on the h-lagged pair frame's trailing window and
    apply them to the CURRENT x_t. The forecast is therefore in return units and uses no
    information past t — the honest bar for 'does this driver predict the LEVEL of the
    forward return', not just its risk."""
    df = pd.concat([x.rename("x"), r.rename("r")], axis=1)
    lag = df.shift(horizon)                                  # pairs realized by t
    bx = lag["x"].rolling(win, min_periods=min_p)
    cov = bx.cov(lag["r"])
    var = lag["x"].rolling(win, min_periods=min_p).var()
    beta = cov / var.replace(0, np.nan)
    alpha = (lag["r"].rolling(win, min_periods=min_p).mean()
             - beta * lag["x"].rolling(win, min_periods=min_p).mean())
    return alpha + beta * x


def _scored_verdict(ic_f, ic_pre, ic_post, edge, ci, base) -> str:
    """CONFIRMED needs: positive stress IC (sign-stable both halves, |IC|>=0.10) AND
    the high-stress tercile dd10 edge>0 with the bootstrap CI lower bound above base."""
    if ic_f is None or np.isnan(ic_f):
        return "UNMEASURED"
    d = np.sign(ic_f)
    both = (np.sign(ic_pre) == d) and (np.sign(ic_post) == d) and d != 0
    half_ok = abs(ic_pre) >= IC_WEAK and abs(ic_post) >= IC_WEAK
    if ic_f <= -IC_WEAK and both:
        return "INVERTED"
    ci_clears = bool(ci and base is not None and ci[0] > base)
    if (ic_f >= IC_STRONG and both and half_ok and (edge or 0) > 0 and ci_clears):
        return "CONFIRMED (scored-eligible)"
    if ic_f >= IC_WEAK and both:
        return "DIRECTIONAL"
    return "CONTEXT"


def scored_gate(drivers: pd.DataFrame, eq: pd.DataFrame, fwd_spy: pd.Series,
                split: pd.Timestamp) -> dict:
    out = {}
    for drv, sgn, lbl in SCORED_CANDIDATES:
        if drv not in drivers:
            continue
        stress = sgn * drivers[drv]
        joint = pd.concat([stress.rename("s"), eq["dd_depth"]], axis=1).dropna()
        if len(joint) < MIN_OBS:
            out[drv] = {"label": lbl, "verdict": "UNMEASURED", "n": len(joint)}
            continue
        span = joint.index
        pre = span[span < split]
        pre = pre[:-H] if len(pre) > H else pre
        post = span[span >= split]
        ic_f = _spear(stress.reindex(span), eq["dd_depth"].reindex(span))
        ic_pre = _spear(stress.reindex(pre), eq["dd_depth"].reindex(pre))
        ic_post = _spear(stress.reindex(post), eq["dd_depth"].reindex(post))
        # purged-CV robustness (5 folds, embargo = forward window)
        folds = purged_folds(span, k=5, embargo=DD_WINDOW)
        fold_signs = [int(np.sign(_spear(stress.reindex(ix), eq["dd_depth"].reindex(ix))))
                      for ix in folds.values() if len(ix) > MIN_OBS // 3]
        cv_robust = fold_robust(int(np.sign(ic_f)), fold_signs, want=1)
        cond = _tercile_edge(stress, eq)
        edge = cond.get("high_edge_pp")
        ci = cond.get("high_p_dd10_ci")
        base = cond.get("base_p_dd10")
        verdict = _scored_verdict(ic_f, ic_pre, ic_post, edge, ci, base)
        # strict return-forecast bar: does the driver predict the LEVEL of fwd SPY
        # return (not just risk)? A LEAKAGE-FREE causal rolling-OLS forecast (return
        # units) is tested vs the causal expanding-mean benchmark via Clark-West (the
        # nested-model test) + Campbell-Thompson OOS-R2. Honest expectation: no return
        # edge, only left-tail risk.
        fcst = _causal_return_forecast(stress, fwd_spy, H)
        rj = pd.concat([fcst.rename("f"), fwd_spy.rename("r")], axis=1).dropna()
        ret_test = {}
        if len(rj) >= 504:
            bench = fwd_spy.shift(H).expanding(min_periods=252).mean().reindex(rj.index)
            ret_test = {"oos_r2": oos_r2(rj["r"].to_numpy(), rj["f"].to_numpy(),
                                         bench=bench.to_numpy()).get("oos_r2"),
                        "clark_west": clark_west(rj["r"].to_numpy(), rj["f"].to_numpy(),
                                                 bench=bench.to_numpy())}
        out[drv] = {
            "label": lbl, "stress_sign": sgn, "n": int(len(joint)),
            "span": f"{span.min().date()}..{span.max().date()}",
            "ic_dd_full": None if np.isnan(ic_f) else round(ic_f, 3),
            "ic_dd_pre": None if np.isnan(ic_pre) else round(ic_pre, 3),
            "ic_dd_post": None if np.isnan(ic_post) else round(ic_post, 3),
            "cv_robust": bool(cv_robust), "conditional": cond,
            "return_forecast_test": ret_test,
            "verdict": verdict,
            "scored_eligible": verdict.startswith("CONFIRMED") and bool(cv_robust),
        }
    return out


# scenario drivers -> the underlying yield/curve series whose 63d CHANGE is the shock.
# Scenarios need CONTEMPORANEOUS co-movement (asset 63d return vs same-window driver
# change), NOT the forward IC above — "if real 10y +50bp this quarter, the asset moves
# X this quarter". Overlapping windows make the SE unreliable but the point beta is a
# fine display estimate; it is caveated as illustrative, regime-dependent, never scored.
SCENARIO_UNDERLYING = {
    "real10y_chg63": "us10y_real",
    "be10y_chg63": "breakeven_10y",
    "nom10y_chg63": "us10y",
    "curve_tp_adj": "curve_tp_adj",
}


def scenario_betas(f: pd.DataFrame) -> dict:
    closes = inputs.yahoo_closes()
    out = {}
    for drv, ucol in SCENARIO_UNDERLYING.items():
        if ucol not in f:
            continue
        dch = f[ucol] - f[ucol].shift(H)                 # contemporaneous 63d change ending at t
        row = {}
        for tkr, _lbl, _kind in ASSETS:
            s = closes.get(tkr)
            if s is None:
                continue
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s = s.reindex(f.index.union(s.index)).ffill().reindex(f.index)
            ret = s / s.shift(H) - 1.0                    # contemporaneous 63d return ending at t
            j = pd.concat([dch.rename("x"), ret.rename("r")], axis=1).dropna()
            if len(j) < MIN_OBS:
                continue
            v = float(j["x"].var())
            if not v:
                continue
            row[tkr] = round(float(j["x"].cov(j["r"]) / v), 4)
        out[drv] = row
    return out


def collinearity(drivers: pd.DataFrame, f: pd.DataFrame) -> dict:
    """VIF + top correlated pairs among the new drivers AND vs the already-scored
    legs (so a 'new' leg that just restates breakeven-direction is caught)."""
    cols = drivers.copy()
    # already-scored / live inflation-axis legs for the redundancy check
    if "breakeven_10y" in f:
        cols["_scored_be10y_chg"] = f["breakeven_10y"] - f["breakeven_10y"].shift(20)
    if "us10y_real" in f and "us10y" in f:
        cols["_scored_tips_nominal"] = (f["us10y"] - f["us10y_real"])
    if "sticky_cpi_3m" in f:
        cols["_scored_sticky_dir"] = f["sticky_cpi_3m"] - f["sticky_cpi_3m"].shift(63)
    sub = cols.dropna()
    return {"vif": vif(sub), "top_pairs": top_correlated_pairs(sub, k=12, thresh=0.6)}


def main() -> int:
    split = pd.Timestamp(((config.load().get("transmission") or {}).get("calibration") or {})
                         .get("split_date", SPLIT_DEFAULT))
    f = inputs.build_features()
    drivers = build_drivers(f)
    fwd = asset_fwd_returns(f.index, H)
    eq = equity_targets(f.index)
    fwd_spy = fwd["SPY"]

    report = {"meta": {
        "horizon_d": H, "dd_window_d": DD_WINDOW, "dd_threshold": DD_THRESH,
        "split": str(split.date()), "ic_strong": IC_STRONG, "ic_weak": IC_WEAK,
        "asof": str(f.index[-1].date()),
        "note": "Transmission = signed Spearman IC(driver_t, asset forward "
                f"{H}d return); display-only coefficients. Scored gate = driver as STRESS "
                f"vs forward {DD_WINDOW}d S&P drawdown (calibrate_bonds discipline) + "
                "purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West "
                "return-forecast bar. No look-ahead."}}
    report["transmission_matrix"] = transmission_matrix(drivers, fwd, split)
    report["scenario_betas"] = scenario_betas(f)
    report["scored_gate"] = scored_gate(drivers, eq, fwd_spy, split)
    report["collinearity"] = collinearity(drivers, f)

    outdir = config.data_dir() / "transmission"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "calibration.json").write_text(
        json.dumps(report, indent=2, default=str, ensure_ascii=False))
    _write_markdown(report)
    print(_summary(report))
    return 0


def _summary(r: dict) -> str:
    L = [f"\n=== Rate/inflation transmission (asof {r['meta']['asof']}, fwd {H}d, "
         f"split {r['meta']['split']}) ==="]
    L.append("\n-- SCORED-LEG GATE (vs forward S&P drawdown) --")
    for k, s in r["scored_gate"].items():
        c = s.get("conditional", {})
        edge = c.get("high_edge_pp")
        ci = c.get("high_p_dd10_ci")
        rt = s.get("return_forecast_test", {})
        cw = (rt.get("clark_west") or {}).get("cw_t")
        L.append(f"  {k:15s} {s.get('verdict','?'):26s} IC dd f/pre/post="
                 f"{s.get('ic_dd_full')}/{s.get('ic_dd_pre')}/{s.get('ic_dd_post')} "
                 f"cv={s.get('cv_robust')} edge={edge}pp ci={ci} | CW_t={cw} oosR2={rt.get('oos_r2')}")
    elig = [k for k, s in r["scored_gate"].items() if s.get("scored_eligible")]
    L.append(f"\n  scored-ELIGIBLE: {elig or 'NONE (all display-only)'}")
    L.append("\n-- TRANSMISSION MATRIX (CONFIRMED cells only) --")
    for drv, dd in r["transmission_matrix"].items():
        conf = [(t, c) for t, c in dd["assets"].items() if c.get("verdict") == "CONFIRMED"]
        if not conf:
            continue
        cells = ", ".join(f"{t}:{c['ic']:+}({c['effect'][:4]})" for t, c in
                          sorted(conf, key=lambda x: -abs(x[1]["ic"])))
        L.append(f"  {drv:15s} {cells}")
    vifd = r["collinearity"].get("vif", {})
    hi_vif = {k: v for k, v in vifd.items() if v and v > 5}
    if hi_vif:
        L.append(f"\n  HIGH VIF (>5, redundant): {hi_vif}")
    return "\n".join(L)


def _write_markdown(r: dict) -> None:
    m = r["meta"]
    L = ["# Rate & inflation transmission — calibration report", "",
         f"As-of **{m['asof']}**. Forward horizon **{m['horizon_d']} days**; split-half "
         f"boundary **{m['split']}**. {m['note']}", "",
         "Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged "
         "halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown "
         "edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign "
         "robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = "
         "weak/unstable; **INVERTED** = predicts the wrong way.", ""]

    L += ["## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?", "",
          "Each driver, expressed as STRESS (higher = more risk-off), vs the forward "
          f"{DD_WINDOW}-day S&P drawdown — the same discriminative bar the bond-health "
          "legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it "
          "predicts the LEVEL of returns; a leg can flag RISK without forecasting return.", "",
          "| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |",
          "|---|---|---|:--:|--:|---|--:|--:|:--:|"]
    for k, s in r["scored_gate"].items():
        c = s.get("conditional", {})
        rt = s.get("return_forecast_test", {})
        cw = (rt.get("clark_west") or {}).get("cw_t")
        ics = f"{s.get('ic_dd_full')}/{s.get('ic_dd_pre')}/{s.get('ic_dd_post')}"
        L.append(f"| {k} ({s.get('label','')}) | **{s.get('verdict','?')}** | {ics} | "
                 f"{s.get('cv_robust')} | {c.get('high_edge_pp')}pp | {c.get('high_p_dd10_ci')} | "
                 f"{cw} | {rt.get('oos_r2')} | {'✅' if s.get('scored_eligible') else '—'} |")
    elig = [k for k, s in r["scored_gate"].items() if s.get("scored_eligible")]
    elig_txt = ", ".join(elig) if elig else "NONE — every rate/inflation leg here is display-only context."
    L += ["", f"**Scored-eligible legs: {elig_txt}** Eligible legs are PROPOSED for a "
          "config-gated MRS/drawdown leg, adopted only if they hold on the next refresh "
          "(the bonds restraint).", ""]

    L += ["## Transmission matrix — per-asset forward pass-through", "",
          "Signed Spearman IC of each rate/inflation driver vs each asset's forward "
          f"{H}-day return. Positive = tailwind, negative = headwind. These are the "
          "DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells "
          "are sign-stable across both halves.", ""]
    # one compact table per driver
    for drv, dd in r["transmission_matrix"].items():
        L += [f"### {drv} — {dd['label']}", "",
              "| asset | IC (full) | pre | post | effect | verdict |", "|---|--:|--:|--:|---|---|"]
        for t, c in sorted(dd["assets"].items(), key=lambda x: -(abs(x[1].get("ic") or 0))):
            L.append(f"| {t} ({c['label']}) | {c.get('ic')} | {c.get('ic_pre')} | "
                     f"{c.get('ic_post')} | {c.get('effect','—')} | {c.get('verdict')} |")
        L.append("")

    col = r["collinearity"]
    L += ["## Collinearity vs already-scored legs", "",
          "VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely "
          "restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in "
          "the inflation axis is caught here and NOT double-counted.", "",
          "| driver | VIF |", "|---|--:|"]
    for k, v in sorted(col.get("vif", {}).items(), key=lambda x: -(x[1] or 0)):
        L.append(f"| {k} | {v} |")
    L += ["", "Top correlated pairs:", ""]
    for p in col.get("top_pairs", []):
        L.append(f"- `{p['a']}` ↔ `{p['b']}`: {p['corr']}")

    Path(config.load()["storage"]["reports_dir"], "rate-inflation-transmission-calibration.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
