"""PHASE 2 — falsification harness for the CREDIT-DIVERGENCE de-risk leg.

Phase 0 (scripts/exp_credit_roc_gate.py) showed HY-OAS velocity clears the basic
forward-drawdown gate the rate/breakeven family failed, and Phase 0b showed a genuine
from-calm lead. This harness applies the STRICT bar before any leg may be considered
for scoring — the reusable "submit-a-leg" gate the build plan calls for:

  1. forward 63d S&P drawdown-depth IC: full + pre-2015 + post-2015 + >=2020 HOLDOUT
     (sign must be stable across ALL — the trap that killed breakeven velocity).
  2. purged-CV sign robustness (5 folds, embargo = forward window).
  3. overlap-aware high-stress tercile P(>=10% dd) edge + block-bootstrap CI > base.
  4. return-forecast bar (Clark-West / OOS-R2) — must be ~0/negative (de-risk, not alpha).
  5. MULTIPLE-COMPARISON control over the whole credit candidate family:
       - FWER via a circular-ROTATION maxT permutation (preserves autocorrelation AND
         cross-candidate structure; rotating the target is the time-series-correct null);
       - FDR via Benjamini-Hochberg on the per-candidate rotation p-values.
  6. INCREMENTAL IC beyond VIX + real-rate speed (causal residualization) — is credit a
     NEW signal, or just volatility/rate-speed in disguise?
  7. from-CALM conditional edge (market within 3% of 252d high) + block-bootstrap CI —
     the only test that isolates LEAD from coincident-persistence.

A leg is SCORED-ELIGIBLE only if: |IC|>=0.10, sign-stable in full+pre+post+2020,
cv_robust, tercile CI lower bound > base, FWER p<0.05, AND incremental IC beyond
VIX/rate-speed >= 0.04. Display-only otherwise. Writes data/transmission/
credit_divergence.json + reports/credit-divergence-calibration.md.

Run: python -m scripts.calibrate_credit_divergence
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
from engine.validation import (purged_folds, fold_robust, clark_west,  # noqa: E402
                               oos_r2, resid_z, benjamini_hochberg)
from scripts.calibrate_rate_inflation import (  # noqa: E402
    H, DD_WINDOW, MIN_OBS, IC_WEAK, IC_STRONG, _spear, _tercile_edge,
    _causal_return_forecast, equity_targets, asset_fwd_returns)

SPLIT = pd.Timestamp("2015-01-01")
HOLDOUT = pd.Timestamp("2020-01-01")
B_PERM = 3000
ZWIN = 504


def _causal_z(s: pd.Series, win: int = ZWIN, min_p: int = 252) -> pd.Series:
    return (s - s.rolling(win, min_periods=min_p).mean()) / s.rolling(win, min_periods=min_p).std()


def build_candidates(f: pd.DataFrame) -> dict[str, pd.Series]:
    """The credit-stress family (higher = more risk-off). Declared ONCE so the
    multiple-comparison correction covers exactly the set we searched."""
    c: dict[str, pd.Series] = {}
    hy = f["hy_oas"]
    c["hy_oas_chg20"] = hy - hy.shift(20)
    c["hy_oas_chg42"] = hy - hy.shift(42)
    c["hy_oas_chg63"] = hy - hy.shift(63)
    c["hy_oas_z504"] = _causal_z(hy)
    if "ig_oas" in f:
        c["ig_oas_chg63"] = f["ig_oas"] - f["ig_oas"].shift(63)
    return c


def _spear_arr(rx_centered: np.ndarray, normx: float, ry_perm: np.ndarray) -> float:
    yc = ry_perm - ry_perm.mean()
    ny = np.sqrt((yc * yc).sum())
    if normx == 0 or ny == 0:
        return 0.0
    return float((rx_centered * yc).sum() / (normx * ny))


def rotation_maxt(cands: dict, dd: pd.Series, b: int = B_PERM, seed: int = 7) -> dict:
    """FWER-correct each candidate's |IC| vs forward dd via circular rotation of the
    target (preserves autocorr + cross-candidate structure). rank(roll(y))==roll(rank(y))
    so we rotate ranks directly. Returns {name:{ic,p_raw,p_fwer}}."""
    joint = pd.concat([*[s.rename(k) for k, s in cands.items()], dd.rename("_dd")],
                      axis=1).dropna()
    if len(joint) < MIN_OBS:
        return {}
    names = list(cands.keys())
    ry = joint["_dd"].rank().to_numpy()
    n = len(ry)
    rxc, normx, ic_obs = {}, {}, {}
    for k in names:
        rx = joint[k].rank().to_numpy()
        rxc[k] = rx - rx.mean()
        normx[k] = np.sqrt((rxc[k] * rxc[k]).sum())
        ic_obs[k] = _spear_arr(rxc[k], normx[k], ry)
    rng = np.random.default_rng(seed)
    offs = rng.integers(DD_WINDOW, n - DD_WINDOW, size=b)   # avoid near-identity rotations
    ge_raw = {k: 0 for k in names}
    ge_fwer = {k: 0 for k in names}
    for o in offs:
        yp = np.roll(ry, int(o))
        perm = {k: abs(_spear_arr(rxc[k], normx[k], yp)) for k in names}
        mx = max(perm.values())
        for k in names:
            if perm[k] >= abs(ic_obs[k]):
                ge_raw[k] += 1
            if mx >= abs(ic_obs[k]):
                ge_fwer[k] += 1
    return {k: {"ic": round(ic_obs[k], 3),
                "p_raw": round((ge_raw[k] + 1) / (b + 1), 4),
                "p_fwer": round((ge_fwer[k] + 1) / (b + 1), 4)} for k in names}


def incremental_ic(cand: pd.Series, dd: pd.Series, basis: list) -> float:
    """IC of the candidate vs forward dd AFTER causally residualizing out the basis
    (VIX, real-rate speed). >0.04 => genuinely new info beyond vol/rate-speed."""
    z = _causal_z(cand)
    bz = [_causal_z(b) for b in basis]
    resid = resid_z(z, bz, win=ZWIN, min_p=252)
    return _spear(resid, dd)


def _from_calm(cand: pd.Series, dd10: pd.Series, calm: pd.Series, seed: int = 11) -> dict:
    """P(>=10% fwd dd) for the HIGH credit-stress tercile WHEN currently calm (within 3%
    of 252d high), with an overlap-aware block-bootstrap CI on the calm-high subset."""
    j = pd.concat([cand.rename("s"), dd10.rename("d"), calm.rename("c")], axis=1).dropna()
    jc = j[j["c"]]
    if len(jc) < 300:
        return {}
    base_calm = float(jc["d"].mean())
    band = pd.qcut(jc["s"].rank(method="first"), 3, labels=["lo", "mid", "hi"])
    hi = jc.loc[band == "hi", "d"].to_numpy(float)
    lo = float(jc.loc[band == "lo", "d"].mean())
    p_hi = float(hi.mean())
    ci = None
    if len(hi) >= 90:
        rng = np.random.default_rng(seed)
        nb = int(np.ceil(len(hi) / DD_WINDOW))
        ms = []
        for _ in range(3000):
            st = rng.integers(0, len(hi), nb)
            ix = (st[:, None] + np.arange(DD_WINDOW)[None, :]).ravel()[:len(hi)] % len(hi)
            ms.append(hi[ix].mean())
        ci = [round(float(np.percentile(ms, p)), 3) for p in (2.5, 50, 97.5)]
    return {"base_calm": round(base_calm, 3), "calm_low": round(lo, 3),
            "calm_high": round(p_hi, 3), "edge_pp": round((p_hi - base_calm) * 100, 1),
            "n_hi": int(len(hi)), "ci": ci}


def gate_one(name: str, stress: pd.Series, eq: pd.DataFrame, fwd_spy: pd.Series,
             vix: pd.Series, rrspeed: pd.Series) -> dict:
    dd = eq["dd_depth"]
    joint = pd.concat([stress.rename("s"), dd], axis=1).dropna()
    if len(joint) < MIN_OBS:
        return {"name": name, "verdict": "UNMEASURED", "n": len(joint)}
    span = joint.index
    pre = span[span < SPLIT]; pre = pre[:-H] if len(pre) > H else pre
    post = span[span >= SPLIT]
    hold = span[span >= HOLDOUT]
    ic_f = _spear(stress.reindex(span), dd.reindex(span))
    ic_pre = _spear(stress.reindex(pre), dd.reindex(pre))
    ic_post = _spear(stress.reindex(post), dd.reindex(post))
    ic_hold = _spear(stress.reindex(hold), dd.reindex(hold))
    folds = purged_folds(span, k=5, embargo=DD_WINDOW)
    fsigns = [int(np.sign(_spear(stress.reindex(ix), dd.reindex(ix))))
              for ix in folds.values() if len(ix) > MIN_OBS // 3]
    cv = fold_robust(int(np.sign(ic_f)), fsigns, want=1)
    cond = _tercile_edge(stress, eq)
    edge, ci, base = cond.get("high_edge_pp"), cond.get("high_p_dd10_ci"), cond.get("base_p_dd10")
    fcst = _causal_return_forecast(stress, fwd_spy, H)
    rj = pd.concat([fcst.rename("f"), fwd_spy.rename("r")], axis=1).dropna()
    cw_t = oosr2 = None
    if len(rj) >= 504:
        bench = fwd_spy.shift(H).expanding(min_periods=252).mean().reindex(rj.index)
        oosr2 = oos_r2(rj["r"].to_numpy(), rj["f"].to_numpy(), bench=bench.to_numpy()).get("oos_r2")
        cw_t = clark_west(rj["r"].to_numpy(), rj["f"].to_numpy(), bench=bench.to_numpy()).get("cw_t")
    inc = incremental_ic(stress, dd, [vix, rrspeed])
    signs = [np.sign(x) for x in (ic_f, ic_pre, ic_post, ic_hold) if x is not None and not np.isnan(x)]
    sign_stable = len(set(signs)) == 1 and signs and signs[0] > 0
    ci_clears = bool(ci and base is not None and ci[0] > base)
    return {"name": name, "n": int(len(joint)),
            "span": f"{span.min().date()}..{span.max().date()}",
            "ic_full": round(ic_f, 3), "ic_pre": round(ic_pre, 3),
            "ic_post": round(ic_post, 3), "ic_2020plus": round(ic_hold, 3),
            "sign_stable_all": bool(sign_stable), "cv_robust": bool(cv),
            "tercile_edge_pp": edge, "tercile_ci": ci, "base": base, "ci_clears_base": ci_clears,
            "cw_t": (round(cw_t, 2) if cw_t is not None else None),
            "oos_r2": (round(oosr2, 4) if oosr2 is not None else None),
            "incremental_ic_beyond_vix_rrspeed": round(inc, 3)}


def main() -> int:
    f = inputs.build_features()
    eq = equity_targets(f.index)
    fwd_spy = asset_fwd_returns(f.index, H)["SPY"]
    vix = f.get("vix_close", pd.Series(index=f.index, dtype=float))
    rrspeed = f["us10y_real"] - f["us10y_real"].shift(63)

    g = store.read("yahoo", "_GSPC")
    spx = (g["close"] if g is not None else inputs.yahoo_closes().get("SPY"))
    spx = spx[~spx.index.duplicated(keep="last")].sort_index()
    spx = spx.reindex(f.index.union(spx.index)).ffill().reindex(f.index)
    calm = (spx / spx.rolling(252).max() - 1.0) >= -0.03
    fwd_worst = spx.rolling(DD_WINDOW).min().shift(-DD_WINDOW) / spx - 1.0
    dd10 = (fwd_worst <= -0.10).astype(float).where(fwd_worst.notna())

    cands = build_candidates(f)
    gate = {k: gate_one(k, v, eq, fwd_spy, vix, rrspeed) for k, v in cands.items()}
    mt = rotation_maxt(cands, eq["dd_depth"])
    bh = benjamini_hochberg({k: v["p_raw"] for k, v in mt.items()}, alpha=0.05)
    calm_t = {k: _from_calm(v, dd10, calm) for k, v in cands.items()}

    for k in gate:
        gate[k]["perm"] = mt.get(k, {})
        gate[k]["bh"] = bh.get(k, {})
        gate[k]["from_calm"] = calm_t.get(k, {})
        g1 = gate[k]
        g1["scored_eligible"] = bool(
            g1.get("ic_full", 0) >= IC_STRONG and g1.get("sign_stable_all")
            and g1.get("cv_robust") and g1.get("ci_clears_base")
            and (mt.get(k, {}).get("p_fwer", 1) < 0.05)
            and (g1.get("incremental_ic_beyond_vix_rrspeed", 0) >= IC_WEAK))
        # honest tier: passes risk gate but display-only (e.g. fails FWER or incremental)
        g1["risk_gate_pass"] = bool(
            g1.get("ic_full", 0) >= IC_WEAK and g1.get("sign_stable_all")
            and g1.get("cv_robust") and g1.get("ci_clears_base"))

    report = {"meta": {"asof": str(f.index[-1].date()), "horizon_d": H,
                       "dd_window_d": DD_WINDOW, "split": str(SPLIT.date()),
                       "holdout": str(HOLDOUT.date()), "n_candidates": len(cands),
                       "perm_B": B_PERM,
                       "note": "Credit-divergence de-risk leg falsification. Forward 63d "
                       "S&P drawdown bar + FWER (rotation maxT) + FDR (BH) + >=2020 holdout "
                       "+ incremental IC beyond VIX & real-rate speed + from-calm lead test. "
                       "scored_eligible requires ALL; risk_gate_pass is the display tier."},
              "legs": gate}
    outdir = config.data_dir() / "transmission"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "credit_divergence.json").write_text(json.dumps(report, indent=2, default=str))
    _print(report)
    return 0


def _print(r: dict) -> None:
    print(f"\n=== CREDIT-DIVERGENCE PHASE-2 (asof {r['meta']['asof']}, fwd {H}d, "
          f"FWER over {r['meta']['n_candidates']} legs, B={r['meta']['perm_B']}) ===")
    for k, s in r["legs"].items():
        if s.get("verdict") == "UNMEASURED":
            print(f"\n{k}: UNMEASURED"); continue
        p = s.get("perm", {}); fc = s.get("from_calm", {})
        print(f"\n{k}  {'<<< SCORED-ELIGIBLE' if s['scored_eligible'] else ('[risk-gate pass, display-only]' if s['risk_gate_pass'] else '[display-only]')}")
        print(f"  IC dd full/pre/post/2020+ = {s['ic_full']}/{s['ic_pre']}/{s['ic_post']}/{s['ic_2020plus']}  "
              f"sign_stable_all={s['sign_stable_all']} cv={s['cv_robust']}")
        print(f"  tercile edge={s['tercile_edge_pp']}pp ci={s['tercile_ci']} base={s['base']} clears={s['ci_clears_base']}")
        print(f"  perm: IC={p.get('ic')} p_raw={p.get('p_raw')} p_FWER={p.get('p_fwer')}  BH q={s.get('bh',{}).get('q')} reject={s.get('bh',{}).get('reject')}")
        print(f"  return-forecast: CW_t={s['cw_t']} oosR2={s['oos_r2']}  (want ~0/neg = de-risk not alpha)")
        print(f"  incremental IC beyond VIX+rate-speed = {s['incremental_ic_beyond_vix_rrspeed']}  (>=0.04 = new info)")
        if fc:
            print(f"  FROM-CALM lead: base_calm={fc.get('base_calm')} calm_low={fc.get('calm_low')} "
                  f"calm_HIGH={fc.get('calm_high')} edge={fc.get('edge_pp')}pp ci={fc.get('ci')} (n_hi={fc.get('n_hi')})")
    elig = [k for k, s in r["legs"].items() if s.get("scored_eligible")]
    rgp = [k for k, s in r["legs"].items() if s.get("risk_gate_pass") and not s.get("scored_eligible")]
    print(f"\nSCORED-ELIGIBLE: {elig or 'NONE'}")
    print(f"RISK-GATE-PASS (display-only context): {rgp or 'NONE'}")


if __name__ == "__main__":
    sys.exit(main())
