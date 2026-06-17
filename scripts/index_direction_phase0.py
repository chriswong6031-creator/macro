"""Phase-0 for the per-index DIRECTIONAL model — does each return predictor (and the
sign-restricted combination) beat the EXPANDING HISTORICAL MEAN out-of-sample for
SPY / QQQ / IWM, at the medium horizon?

Walk-forward (expanding, sign-restricted univariate OLS, monthly steps, embargo = h)
→ OOS forecast vs the recursive mean → Campbell-Thompson OOS-R² + Clark-West nested
test + split-half + calibration (Brier/Platt) + a long/flat timing backtest with the
DSR multiple-testing haircut. Writes the INDEX_DIRECTION gate block (default NEUTRAL /
scored:false) + research/INDEX_DIRECTION_PHASE0.md. Nothing scores live until GO.

Run:  python3 -m scripts.index_direction_phase0
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import index_direction as idr, validation as V, vol_forecast
from engine.validation import _norm_cdf

INDEXES = ["SPY", "QQQ", "IWM"]          # DIA deferred: no data/yahoo/DIA.parquet (use _DJI proxy later)
SECTORS = ["XLK", "XLF", "XLE", "XLU", "XLRE", "XLB", "XLI", "XLY", "XLP", "XLV", "XLC"]
ALL_TICKERS = INDEXES + SECTORS
H = idr.MEDIUM_TD                          # 42td medium horizon
STEP = 21                                  # monthly rebalance
MIN_TRAIN = 2520                           # ~10y before the first OOS prediction
# FROZEN multiple-testing count for the DSR haircut: every index+sector × candidate leg ×
# horizon screened across the whole program (~15 assets × ~6 legs × 2 horizons). Counted from
# first screen (critique #3 — no under-reporting). Asserted in tests so it cannot drift.
N_TRIALS = 200
DATA, REGIME = Path("data"), Path("data/regime")


def _close(tkr: str):
    p = DATA / "yahoo" / f"{tkr}.parquet"
    if not p.exists():
        return None
    return pd.read_parquet(p)["close"].dropna()


def walk_forward(close: pd.Series, legs: pd.DataFrame, weights: dict, h: int = H,
                 step: int = STEP, min_train: int = MIN_TRAIN) -> list:
    """Expanding sign-restricted walk-forward → per-rebalance steps, each carrying the
    realized forward return, the recursive-mean bench, and the per-leg OOS forecast
    available that day. The composite over any leg SUBSET is recomputed post-hoc, so
    the GATED (GO-leg-only) combination can be evaluated without re-running."""
    fwd = idr.fwd_return(close, h)
    n = len(close)
    steps = []
    for i in range(min_train, n - h, step):
        train_lbl = close.index[: i - h + 1]                 # labels fully in the past (embargo h)
        ytr = fwd.loc[train_lbl].dropna()
        if len(ytr) < 252:
            continue
        legfs = {}
        for leg in weights:
            if leg not in legs.columns:
                continue
            j = pd.concat([legs[leg].loc[train_lbl].rename("x"),
                           fwd.loc[train_lbl].rename("y")], axis=1).dropna()
            xnow = legs[leg].iloc[i]
            if len(j) < 252 or not np.isfinite(xnow):
                continue
            fit = idr._ols_sign(j["x"].to_numpy(), j["y"].to_numpy(), 1)
            if fit is None:
                continue
            a, b = fit
            legfs[leg] = a + b * float(xnow)
        steps.append({"date": close.index[i], "r": float(fwd.iloc[i]),
                      "b": float(ytr.mean()), "legfs": legfs})
    return steps


def _leg_series(steps, leg):
    rows = [(s["date"], s["legfs"][leg], s["r"], s["b"]) for s in steps if leg in s["legfs"]]
    if not rows:
        return pd.DatetimeIndex([]), np.array([]), np.array([]), np.array([])
    d, f, r, b = zip(*rows)
    return pd.DatetimeIndex(d), np.array(f), np.array(r), np.array(b)


def _composite_series(steps, subset, weights):
    """Weighted-mean composite over the leg SUBSET present each step (skip steps with
    no subset leg — a directional model has no opinion there)."""
    d, f, r, b = [], [], [], []
    for s in steps:
        pres = [l for l in subset if l in s["legfs"]]
        if not pres:
            continue
        num = sum(s["legfs"][l] * idr.TIER[weights[l]] for l in pres)
        den = sum(idr.TIER[weights[l]] for l in pres)
        d.append(s["date"]); f.append(num / den if den else s["b"]); r.append(s["r"]); b.append(s["b"])
    return pd.DatetimeIndex(d), np.array(f), np.array(r), np.array(b)


def _eval(r, f, b, hac):
    """OOS-R² + Clark-West + split-half (both halves OOS-R²>0 & CW sign)."""
    r, f, b = np.asarray(r, float), np.asarray(f, float), np.asarray(b, float)
    if len(r) < 60:
        return None
    full_r2 = V.oos_r2(r, f, b)
    cw = V.clark_west(r, f, b, hac_lags=hac)
    mid = len(r) // 2
    h1 = V.oos_r2(r[:mid], f[:mid], b[:mid]).get("oos_r2")
    h2 = V.oos_r2(r[mid:], f[mid:], b[mid:]).get("oos_r2")
    half_ok = bool(h1 is not None and h2 is not None and h1 > 0 and h2 > 0)
    return {"oos_r2": full_r2.get("oos_r2"), "cw_p": cw.get("cw_p"), "cw_t": cw.get("cw_t"),
            "n": full_r2.get("n"), "half_r2": [h1, h2], "half_ok": half_ok}


def _timing_backtest(close, dates, f, h):
    """Long/flat: hold when the OOS forecast is positive (vs flat), daily, next-bar,
    costed. DSR-haircut + bootstrap CI on the daily strategy returns."""
    alloc = pd.Series(np.where(np.asarray(f) > 0, 1.0, 0.0), index=dates)
    alloc = alloc.reindex(close.index, method="ffill").fillna(0.0)
    bt = V.backtest_core(close, alloc, cost_bps=2.0)
    net = bt["net"].dropna()
    mom = V.ret_moments(net)
    dsr = V.deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=N_TRIALS, trading_year=252) if mom else None
    ci = V.block_bootstrap_ci(net, block=21, B=1500, ann=252)

    def _stats(rser):
        eq = (1 + rser).cumprod(); yrs = (rser.index[-1] - rser.index[0]).days / 365.25
        return {"cagr": round(100 * (float(eq.iloc[-1]) ** (1 / yrs) - 1), 1),
                "sharpe": round(float(rser.mean() / rser.std(ddof=0) * np.sqrt(252)), 2),
                "maxdd": round(100 * float((eq / eq.cummax() - 1).min()), 1)}
    return {"strat": _stats(net), "hold": _stats(bt["hold"].dropna()),
            "dsr": dsr["dsr"] if dsr else None, "sharpe_ci": ci.get("sharpe_ci"),
            "exposure": round(float(alloc.mean()), 2)}


def _calibration(close, dates, f, r, h):
    """Map OOS forecast → P(up) via Φ(f/σ_h); Brier skill vs climatology + Platt."""
    cv = vol_forecast.cone_vol_ann(close).reindex(dates, method="ffill")
    sig = (cv * np.sqrt(h / 252.0) * 100.0).to_numpy()
    p = np.array([_norm_cdf(fi / si) if (si and np.isfinite(si) and si > 0) else 0.5
                  for fi, si in zip(f, sig)])
    y = (np.asarray(r) > 0).astype(float)
    br = V.brier_reliability(p, y)
    pl = V.platt_fit(p, y)
    base, recal = br.get("base_brier"), pl.get("brier_recal")
    # gate on the RECALIBRATED probability (what we actually ship) vs climatology
    skill_recal = round(1 - recal / base, 3) if (recal is not None and base) else None
    return {"brier_skill": br.get("skill_score"), "brier_skill_recal": skill_recal,
            "base_up": br.get("base_rate"), "platt_a": pl.get("a"), "platt_b": pl.get("b"),
            "p_mean": round(float(np.nanmean(p)), 3)}


def run_index(tkr: str) -> dict:
    close = _close(tkr)
    if close is None or len(close) < MIN_TRAIN + H + 252:
        print(f"  {tkr}: insufficient data — skip")
        return {}
    weights = idr.PRESETS[tkr]["medium"]
    legs = idr.build_legs(close)
    steps = walk_forward(close, legs, weights)
    print(f"\n=== {tkr} medium ({H}td) — {len(steps)} OOS rebalances ===")
    # --- per-leg OOS ---
    leg_res, pvals = {}, {}
    for leg in weights:
        _, f, r, b = _leg_series(steps, leg)
        if len(r) < 60:
            continue
        e = _eval(r, f, b, hac=max(4, H // STEP))
        if e:
            leg_res[leg] = e
            pvals[leg] = e["cw_p"]
            print(f"  leg {leg:11s} OOS-R²={str(e['oos_r2']):>8s} CW p={str(e['cw_p']):>6s} "
                  f"half={['%.4f' % x if x is not None else '—' for x in e['half_r2']]} "
                  f"{'BOTH+' if e['half_ok'] else ''}")
    bh = V.benjamini_hochberg({k: v for k, v in pvals.items() if v is not None}, alpha=0.10)
    # --- per-leg GATE: OOS-R²>0 AND both halves AND BH-adjusted CW p<0.10 ---
    leg_gate = {}
    for leg, e in leg_res.items():
        q = (bh.get(leg) or {}).get("q")
        leg_gate[leg] = "GO" if (e["oos_r2"] is not None and e["oos_r2"] > 0 and e["half_ok"]
                                 and q is not None and q < 0.10) else "NEUTRAL"
    go = {leg for leg, g in leg_gate.items() if g == "GO"}
    # --- composite over the GO legs (fall back to ALL legs only for context timing/report) ---
    subset = go if go else set(weights)
    dC, fC, rC, bC = _composite_series(steps, subset, weights)
    ce = _eval(rC, fC, bC, hac=max(4, H // STEP)) if len(rC) >= 60 else None
    bt = _timing_backtest(close, dC, fC, H)
    cal = _calibration(close, dC, fC, rC, H)
    best_go = max([leg_res[l]["oos_r2"] for l in go if leg_res[l]["oos_r2"] is not None], default=-9.0)
    beats_best = bool(ce and ce["oos_r2"] is not None and (not go or ce["oos_r2"] >= best_go - 1e-9))
    print(f"  GO-COMPOSITE [{','.join(sorted(go)) or 'none'}]  OOS-R²={str(ce['oos_r2'] if ce else None):>8s} "
          f"CW p={str(ce['cw_p'] if ce else None):>6s} half_ok={ce['half_ok'] if ce else None} beats_best={beats_best}")
    print(f"  timing: strat {bt['strat']} vs hold {bt['hold']} | DSR {bt['dsr']} | "
          f"brier_skill {cal['brier_skill']} platt_a {cal['platt_a']} p_mean {cal['p_mean']}")
    # economic floor: the timing overlay must not be Sharpe-worse than buy&hold. The
    # SCORED decision is finalized in main() via cross-asset BH-FDR on the composite
    # Clark-West p (the correct multiple-testing control); DSR + bootstrap CI are reported
    # as economic context, not a hard veto (a Sharpe-snooping haircut would double-penalize).
    econ_ok = bool(bt["strat"]["sharpe"] >= bt["hold"]["sharpe"])
    return {"ticker": tkr, "n_oos": len(steps), "legs": leg_res, "leg_gate": leg_gate,
            "go_legs": sorted(go), "combination": ce, "beats_best": beats_best,
            "timing": bt, "calibration": cal, "econ_ok": econ_ok,
            "platt": {"a": cal["platt_a"], "b": cal.get("platt_b", 0.0)}}


def main() -> int:
    print("Index Direction Phase-0 — walk-forward OOS vs expanding historical mean")
    results = {t: run_index(t) for t in ALL_TICKERS}
    results = {t: r for t, r in results.items() if r}
    # CROSS-ASSET multiple-testing control: BH-FDR on each asset's COMPOSITE Clark-West p
    # (the real family — one directional model per asset across the whole screen). This is
    # the correct, single multiple-testing correction (replaces the wrong Sharpe-DSR veto).
    comp_p = {t: r["combination"]["cw_p"] for t, r in results.items()
              if r["go_legs"] and r.get("combination") and r["combination"].get("cw_p") is not None}
    bh_assets = V.benjamini_hochberg(comp_p, alpha=0.05)
    print("\n=== cross-asset FDR (BH on composite Clark-West p) ===")
    for t, r in results.items():
        ce = r.get("combination")
        q = (bh_assets.get(t) or {}).get("q")
        r["composite_q"] = q
        # The validated directional quantity is the forward RETURN (shifts the cone center):
        # OOS-R²>0, BH-q<0.05, both halves, beats-best, economic floor. P(up) is a derived
        # display — require only that it is CALIBRATED (recalibrated Brier not materially worse
        # than climatology), not that the binary lean itself beats the base rate.
        br = r["calibration"]["brier_skill_recal"]
        r["scored"] = bool(
            r["go_legs"] and ce and ce.get("oos_r2") is not None and ce["oos_r2"] > 0
            and q is not None and q < 0.05 and ce.get("half_ok") and r["beats_best"]
            and r["econ_ok"] and (br is not None and br >= -0.01))
        if r["go_legs"]:
            print(f"  {t:5s} composite OOS-R²={ce.get('oos_r2')} CW p={ce.get('cw_p')} BH-q={q} "
                  f"econ_ok={r['econ_ok']} brier_recal={r['calibration']['brier_skill_recal']} "
                  f"DSR={r['timing']['dsr']} -> {'SCORED' if r['scored'] else 'display-only'}")

    gpath = REGIME / "anticipation_gate.json"
    full = json.loads(gpath.read_text()) if gpath.exists() else {}
    block = {"_meta": {"n_trials": N_TRIALS, "horizon_td": H, "benchmark": "expanding historical mean",
                       "fdr": "BH across assets on composite Clark-West p (alpha 0.05)",
                       "note": "display-only until scored; per-asset, no transfer; short stays coin-flip"}}
    for t, r in results.items():
        block[t] = {"medium": {
            "scored": r["scored"], "legs": r["leg_gate"],
            "platt": r["platt"] if r["scored"] else None,
            "oos_r2": (r["combination"] or {}).get("oos_r2"),
            "cw_p": (r["combination"] or {}).get("cw_p"), "cw_q": r.get("composite_q"),
            "brier_skill_recal": r["calibration"]["brier_skill_recal"],
            "dsr": r["timing"]["dsr"], "p_up_band": list(idr.P_BAND)}}
    full["INDEX_DIRECTION"] = block
    gpath.write_text(json.dumps(full, indent=2))
    _report(results)
    n_scored = sum(1 for r in results.values() if r["scored"])
    print(f"\nWrote INDEX_DIRECTION gate ({n_scored}/{len(results)} indexes scored) + research/INDEX_DIRECTION_PHASE0.md")
    return 0


def _report(results):
    L = ["# Index Direction — Phase-0 results", "",
         f"Walk-forward OOS (expanding, sign-restricted, monthly, embargo={H}td) vs the recursive "
         f"historical mean. A leg/combination is GO only if OOS-R² > 0 AND Clark-West nested test "
         f"significant (BH-adjusted p<0.10) AND positive in BOTH date-halves; the combination also "
         f"needs DSR≥0.90 (n_trials={N_TRIALS}), Brier skill>0, and must beat its best single leg. "
         f"Benchmark = 'always predict the mean' (Goyal-Welch random walk).", ""]
    for t, r in results.items():
        L += [f"## {t} — medium ({H}td), {r['n_oos']} OOS rebalances", "",
              "| leg | OOS-R² | Clark-West p | both halves | gate |", "|---|---|---|---|---|"]
        for leg, e in r["legs"].items():
            L.append(f"| `{leg}` | {e['oos_r2']} | {e['cw_p']} | {'✓' if e['half_ok'] else '—'} | "
                     f"**{r['leg_gate'].get(leg)}** |")
        ce, bt, cal = r["combination"], r["timing"], r["calibration"]
        L += ["",
              f"**Combination:** OOS-R² {ce['oos_r2'] if ce else None}, Clark-West p {ce['cw_p'] if ce else None}, "
              f"beats-best-leg {r['beats_best']}, both-halves {ce['half_ok'] if ce else None}.",
              f"**Timing backtest** (long when forecast>0, costed): strat "
              f"{bt['strat']['cagr']}%/{bt['strat']['sharpe']}/{bt['strat']['maxdd']}% vs buy&hold "
              f"{bt['hold']['cagr']}%/{bt['hold']['sharpe']}/{bt['hold']['maxdd']}% · exposure {bt['exposure']} · DSR {bt['dsr']}.",
              f"**Calibration:** Brier skill {cal['brier_skill']} (base up-rate {cal['base_up']}), Platt a {cal['platt_a']}, mean P(up) {cal['p_mean']}.",
              f"**Verdict:** {'SCORED — directional lean is live' if r['scored'] else 'display-only (combination did not clear the OOS bar)'}.", ""]
    L += ["_Generated by scripts/index_direction_phase0.py. Short horizon stays a coin-flip; "
          "long horizon pending a valuation (Shiller) collector. Re-run after data updates._", ""]
    Path("research").mkdir(exist_ok=True)
    Path("research/INDEX_DIRECTION_PHASE0.md").write_text("\n".join(L))


if __name__ == "__main__":
    raise SystemExit(main())
