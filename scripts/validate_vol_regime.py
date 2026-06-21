"""scripts/validate_vol_regime.py — the FIREWALL gate for engine/vol_regime.py.

Decides, on 1990+ history we already hold, which index vol-regime legs have EARNED the
right to move money. Writes two artifacts:

  • reports/vol-regime-validation.md   — the human-readable evidence
  • data/vol_regime/gate.json          — the machine gate engine/vol_regime reads; a leg
                                         is `scored: true` ONLY if it clears the bar here.

What "earned" means here is deliberately the HONEST edge, not a fantasy alpha. The
documented, robust thing the index vol surface does is forecast forward REALIZED VOL and
drawdown risk (term structure: Johnson 2017; VRP: Bollerslev-Tauchen-Zhou 2009) — NOT
reliably pick equity direction for alpha. So a leg is gated SCORED for the RISK / SIZING
channel (a subtract-only risk-off nudge + the vol-target scalar) when it:

  (1) predicts forward realized vol with the expected sign (risk-on leg -> LOWER fwd vol),
  (2) at a Newey-West |t| >= the configured bar (overlapping windows -> HAC),
  (3) with that sign STABLE across purged sub-period folds (>= k-1 agree, none flip), and
  (4) the sign SURVIVES excluding the 2008/2020/2022 crisis windows (not 3-event-driven).

The forward-RETURN (equity-timing alpha) leg is ALSO measured — OOS-R2 (Campbell-Thompson)
+ Clark-West vs the expanding-mean benchmark + a long/flat DSR — but held to the higher
Goyal-Welch bar and reported as CONTEXT; it does not by itself open the money gate. This
keeps the regime a subtract-only risk/sizing overlay (matching the MRS + anticipation
doctrine: a drawdown/capital-efficiency lever, not a return-alpha claim).

Run:  python -m scripts.validate_vol_regime  [--write-gate]
Without --write-gate it prints the verdict and writes the report but leaves the gate
closed (display-only) — promotion to scored is a deliberate, reviewed step.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from engine import vol_regime
from engine.validation import (clark_west, deflated_sharpe, newey_west_tstat,
                               oos_r2, purged_folds, ret_moments)
from engine.vol_forecast import realized_vol
from lib import config, store

log = logging.getLogger(__name__)

CRISES = [("2008-08-01", "2009-07-01"), ("2011-07-01", "2011-11-01"),
          ("2020-02-01", "2020-06-01"), ("2022-01-01", "2022-11-01")]
HORIZONS = (21, 63)            # ~1m, ~3m forward windows
NW_T_BAR = 2.5                 # forward-vol HAC |t| bar for the risk/sizing gate
N_FOLDS = 4
# collect-first CONTEXT legs evaluated for evidence but never gating the scored composite
# (history just started — VVIX 2006+; the VX-curve leg is forward-accruing, not yet built).
CANDIDATE_LEGS = ("vvix",)


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def _series(group: str, name: str, col: str = "close") -> pd.Series | None:
    try:
        df = store.read(group, name)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    if col in df.columns:
        s = df[col]
    else:
        s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index().astype(float)


def load_inputs() -> dict:
    vvix = _series("cboe", "vvix", col="vvix")
    if vvix is None:
        vvix = _series("yahoo", "_VVIX")
    return {
        "vix": _series("yahoo", "_VIX"),
        "vix3m": _series("yahoo", "_VIX3M"),
        "vix9d": _series("yahoo", "_VIX9D"),
        "move": _series("yahoo", "_MOVE"),
        "skew": _series("cboe", "skew", col="skew"),
        "spy": _series("yahoo", "SPY"),
        "vvix": vvix,
    }


# --------------------------------------------------------------------------- #
# stats
# --------------------------------------------------------------------------- #
def _spearman(a: pd.Series, b: pd.Series) -> float:
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(j) < 40:
        return float("nan")
    return float(j["a"].rank().corr(j["b"].rank()))


def _nw_t_on_product(sig: pd.Series, fwd: pd.Series, lags: int) -> dict:
    """HAC t-stat on the mean of (z-signal * z-forward) — a time-series IC whose sign is
    the predictive sign and whose |t| is honest under overlapping forward windows."""
    j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 60:
        return {"t": None, "n": len(j), "mean": None}
    zs = (j["s"] - j["s"].mean()) / (j["s"].std(ddof=0) or 1)
    zf = (j["f"] - j["f"].mean()) / (j["f"].std(ddof=0) or 1)
    return newey_west_tstat((zs * zf).to_numpy(), lags=lags)


def _recursive_ols_forecast(g: pd.Series, y: pd.Series, min_n: int = 252) -> pd.Series:
    """Causal expanding univariate OLS forecast of y from g: at each t, betas use only
    pairs strictly before t. Closed-form via running sums (no look-ahead)."""
    j = pd.concat([g.rename("x"), y.rename("y")], axis=1).dropna()
    x, yv = j["x"].to_numpy(), j["y"].to_numpy()
    n = len(j)
    sx = np.cumsum(x); sy = np.cumsum(yv)
    sxx = np.cumsum(x * x); sxy = np.cumsum(x * yv)
    out = np.full(n, np.nan)
    for t in range(min_n, n):
        k = t                                  # use pairs [0, t-1]
        mx, my = sx[k - 1] / k, sy[k - 1] / k
        cov = sxy[k - 1] / k - mx * my
        var = sxx[k - 1] / k - mx * mx
        if var > 1e-12:
            b = cov / var
            out[t] = (my - b * mx) + b * x[t]
    return pd.Series(out, index=j.index)


def _fold_signs(sig: pd.Series, fwd: pd.Series) -> list[int]:
    j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < N_FOLDS * 60:
        return []
    folds = purged_folds(j.index, N_FOLDS, embargo=max(HORIZONS))
    signs = []
    for idx in folds.values():
        sub = j.loc[j.index.intersection(idx)]
        if len(sub) >= 40:
            c = sub["s"].rank().corr(sub["f"].rank())
            signs.append(int(np.sign(c)) if pd.notna(c) else 0)
    return signs


def _mask_crises(index: pd.DatetimeIndex) -> pd.Series:
    keep = pd.Series(True, index=index)
    for lo, hi in CRISES:
        keep &= ~((index >= lo) & (index < hi))
    return keep


# --------------------------------------------------------------------------- #
# per-leg evaluation
# --------------------------------------------------------------------------- #
def evaluate_leg(name: str, leg: pd.Series, spy: pd.Series, frame: pd.DataFrame) -> dict:
    """Evaluate one risk-on-oriented leg (or the composite) against forward vol and
    forward return. Returns the full evidence dict + a scored/sign decision for the
    risk/sizing channel."""
    res = {"name": name, "horizons": {}, "n": int(leg.dropna().shape[0])}
    keep = _mask_crises(leg.index)

    best_vol = None
    for h in HORIZONS:
        # forward realized vol (annualised %, the validatable mechanism)
        fwd_rv = (realized_vol(spy, h).shift(-h) * np.sqrt(252) * 100).reindex(leg.index)
        # forward return
        fwd_ret = spy.pct_change(h, fill_method=None).shift(-h).reindex(leg.index)

        vol_corr = _spearman(leg, fwd_rv)                 # expect NEGATIVE (risk-on -> low vol)
        vol_nw = _nw_t_on_product(leg, fwd_rv, lags=max(2, h // 10))
        ret_corr = _spearman(leg, fwd_ret)                # expect POSITIVE if any timing edge
        ret_nw = _nw_t_on_product(leg, fwd_ret, lags=max(2, h // 10))

        # crisis-excluded vol sign
        vol_corr_xc = _spearman(leg[keep], fwd_rv[keep])
        # subperiod fold signs (forward vol)
        folds_vol = _fold_signs(leg, fwd_rv)

        # OOS-R2 + Clark-West for the RETURN forecast (context alpha bar)
        fc = _recursive_ols_forecast(leg, fwd_ret)
        j = pd.concat([fwd_ret.rename("r"), fc.rename("f")], axis=1).dropna()
        oos = oos_r2(j["r"], j["f"]) if len(j) > 300 else {}
        cw = clark_west(j["r"], j["f"]) if len(j) > 300 else {}

        res["horizons"][h] = {
            "fwd_vol_corr": round(vol_corr, 4) if pd.notna(vol_corr) else None,
            "fwd_vol_t_hac": vol_nw.get("t"), "fwd_vol_n": vol_nw.get("n"),
            "fwd_vol_corr_crisis_excl": round(vol_corr_xc, 4) if pd.notna(vol_corr_xc) else None,
            "fwd_vol_fold_signs": folds_vol,
            "fwd_ret_corr": round(ret_corr, 4) if pd.notna(ret_corr) else None,
            "fwd_ret_t_hac": ret_nw.get("t"),
            "oos_r2": oos.get("oos_r2"), "cw_t": cw.get("cw_t"), "cw_p": cw.get("cw_p"),
        }
        if best_vol is None and h == 21:
            best_vol = res["horizons"][h]

    # ----- decision: risk/sizing gate on the forward-VOL mechanism (21d) -----
    h0 = res["horizons"].get(21, {})
    vol_corr = h0.get("fwd_vol_corr")
    vol_t = h0.get("fwd_vol_t_hac")
    vol_xc = h0.get("fwd_vol_corr_crisis_excl")
    folds = h0.get("fwd_vol_fold_signs") or []
    # risk-on leg should predict LOWER forward vol -> negative corr; sign we want = -1
    want = -1
    sign_ok = vol_corr is not None and np.sign(vol_corr) == want
    t_ok = vol_t is not None and abs(vol_t) >= NW_T_BAR
    crisis_ok = vol_xc is not None and np.sign(vol_xc) == want
    nz = [s for s in folds if s != 0]
    fold_ok = bool(nz) and sum(1 for s in nz if s == want) >= max(1, len(nz) - 1) \
        and all(s != -want for s in nz)
    scored = bool(sign_ok and t_ok and crisis_ok and fold_ok)
    res["decision"] = {
        "scored": scored,
        # sign for the SCORED money channel: the leg is risk-on oriented, so a scored
        # leg carries +1 (higher leg -> more risk-on / lower forward vol). The risk-OFF
        # nudge downstream flips it (subtract-only) — recorded here for the engine.
        "sign": 1 if scored else None,
        "weight": 1.0 if scored else 0.0,
        "basis": "forward-realized-vol predictability (risk/sizing channel)",
        "checks": {"sign_ok": sign_ok, "t_hac_ok": t_ok, "crisis_robust": crisis_ok,
                   "subperiod_sign_stable": fold_ok, "t_hac": vol_t, "bar": NW_T_BAR},
    }
    return res


def long_flat_dsr(composite: pd.Series, spy: pd.Series, n_trials: int) -> dict:
    """A simple risk-managed long/flat backtest: hold equity when the composite is
    risk-on (>=0), flat otherwise. DSR deflates for the variants tried. CONTEXT — the
    return channel, reported not gated."""
    import tempfile
    from engine.validation import backtest_core, block_bootstrap_ci
    from engine.trial_ledger import TrialLedger
    alloc = (composite >= 0).astype(float)
    bt = backtest_core(spy, alloc, cost_bps=1.0)
    net = bt["net"].dropna()
    mom = ret_moments(net)
    if mom is None:
        return {}
    # honest multiple-testing N via the canonical trial ledger (tests/test_no_literal_ntrials)
    _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                       family="vol_regime")
    _led.log_grid([{"trial": i} for i in range(int(n_trials))], family="vol_regime")
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_led, family="vol_regime",
                          trading_year=252)
    boot = block_bootstrap_ci(net, ann=252)
    hold = bt["hold"].dropna()
    hm = ret_moments(hold)
    return {"strat": dsr, "bootstrap": boot,
            "hold_sharpe_ann": round(hm[0] * np.sqrt(252), 2) if hm else None,
            "years": round(bt["years"], 1)}


# --------------------------------------------------------------------------- #
# orchestrate
# --------------------------------------------------------------------------- #
def run(write_gate: bool = False) -> dict:
    cfg = (config.load().get("engine", {}) or {}).get("vol_regime") or {}
    inp = load_inputs()
    missing = [k for k, v in inp.items() if v is None]
    if inp["vix"] is None or inp["spy"] is None:
        log.error("vol_regime validate: missing VIX/SPY — cannot run (%s)", missing)
        return {"status": "no_data", "missing": missing}

    frame = vol_regime.build_frame(inp["vix"], inp["vix3m"], inp["vix9d"], inp["move"],
                                   inp["skew"], inp["spy"], cfg, vvix=inp["vvix"])
    spy = inp["spy"]

    # legs evaluated: the three scored-eligible legs + the composite
    targets = {}
    for k in vol_regime.SCORED_LEGS:
        col = f"leg_{k}"
        if col in frame.columns:
            targets[k] = frame[col]
    if "risk_score" in frame.columns:
        targets["composite"] = frame["risk_score"]

    # CANDIDATE (collect-first) legs: evaluated for EVIDENCE only — they never gate the
    # composite or open the money channel. A candidate enters the scored composite only via a
    # deliberate promotion to vol_regime.SCORED_LEGS (which also re-validates the composite).
    cand_targets = {}
    for k in CANDIDATE_LEGS:
        col = f"leg_{k}"
        if col in frame.columns:
            cand_targets[k] = frame[col]

    # count candidates in the trial family so the composite DSR is deflated honestly
    n_trials = len(targets) + len(cand_targets) + 2   # legs + composite + candidates + long/flat
    evals = {k: evaluate_leg(k, s, spy, frame) for k, s in targets.items()}
    cand_evals = {k: evaluate_leg(k, s, spy, frame) for k, s in cand_targets.items()}
    dsr = long_flat_dsr(frame["risk_score"], spy, n_trials) if "risk_score" in frame else {}

    # gate.json: a leg is scored if its own decision passed AND it is a SCORED_LEG
    gate_legs = {}
    for k in vol_regime.SCORED_LEGS:
        d = (evals.get(k) or {}).get("decision") or {}
        gate_legs[k] = {"scored": bool(d.get("scored")), "sign": d.get("sign"),
                        "weight": d.get("weight", 0.0), "basis": d.get("basis")}
    comp_scored = bool((evals.get("composite") or {}).get("decision", {}).get("scored"))
    # candidates: record whether each WOULD pass the bar (evidence for a future promotion),
    # but always scored=false in the gate — they are display/context until promoted.
    cand_gate = {}
    for k, e in cand_evals.items():
        d = (e or {}).get("decision") or {}
        cand_gate[k] = {"scored": False, "would_pass": bool(d.get("scored")),
                        "n": e.get("n"), "basis": "candidate — not in the scored composite"}
    gate = {
        "asof": str(date.today()),
        "generated": datetime.now(timezone.utc).isoformat(),
        "legs": gate_legs,
        "candidates": cand_gate,
        "composite": {"scored": comp_scored, "horizon_d": 21,
                      "basis": "forward-realized-vol predictability"},
        "note": ("Gate OPEN — at least one leg earned scored status."
                 if (any(v["scored"] for v in gate_legs.values()) and write_gate)
                 else "Gate CLOSED — display-only (run with --write-gate to promote)."),
        "n_trials": n_trials,
    }

    report = _render_report(evals, dsr, gate, missing, cand_evals)
    try:
        rp = config.ROOT / "reports" / "vol-regime-validation.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(report)
        log.info("wrote %s", rp)
    except Exception as e:  # noqa: BLE001
        log.warning("report write failed: %s", e)

    if write_gate:
        gp = config.data_dir() / vol_regime.GATE_PATH
        gp.parent.mkdir(parents=True, exist_ok=True)
        gp.write_text(json.dumps(gate, indent=2))
        log.info("wrote gate %s (scored legs: %s)", gp,
                 [k for k, v in gate_legs.items() if v["scored"]])

    return {"status": "ok", "gate": gate, "evals": evals, "candidates": cand_evals,
            "dsr": dsr, "report": report}


def _f(x, n=3):
    return "—" if x is None else (f"{x:.{n}f}" if isinstance(x, (int, float)) else str(x))


def _leg_row(k: str, e: dict, scored_mark: str) -> str:
    h = e["horizons"].get(21, {})
    return (f"| {k} | {_f(h.get('fwd_vol_corr'))} | {_f(h.get('fwd_vol_t_hac'),2)} | "
            f"{_f(h.get('fwd_vol_corr_crisis_excl'))} | {h.get('fwd_vol_fold_signs')} | "
            f"{_f(h.get('fwd_ret_corr'))} | {_f(h.get('oos_r2'),4)} | {_f(h.get('cw_p'),3)} | "
            f"{scored_mark} |")


def _render_report(evals: dict, dsr: dict, gate: dict, missing: list,
                   cand_evals: dict | None = None) -> str:
    L = ["# Vol-Regime validation\n",
         f"_generated {gate['generated']} · n_trials={gate['n_trials']}_\n",
         "Honest bar: a leg is SCORED (risk/sizing channel) only if its risk-on form "
         "predicts **lower forward realized vol** with HAC |t|≥"
         f"{NW_T_BAR}, a sign stable across purged folds, that survives excluding the "
         "2008/2020/2022 crisis windows. Forward-RETURN (equity alpha) is reported as "
         "context only (OOS-R²/Clark-West vs the expanding mean).\n"]
    if missing:
        L.append(f"> Missing inputs (legs degrade): {', '.join(missing)}\n")
    L.append("## Per-leg evidence\n")
    L.append("| leg | fwd-vol corr (21d) | HAC t | crisis-excl | folds | fwd-ret corr | "
             "OOS-R² | CW p | → SCORED |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for k, e in evals.items():
        d = e.get("decision", {})
        L.append(_leg_row(k, e, "✅" if d.get("scored") else "—"))
    if cand_evals:
        L.append("\n## Candidate legs (collect-first — NOT in the scored composite)\n")
        L.append("These have history but are evaluated for evidence only; promotion into the "
                 "scored composite is a deliberate, reviewed step (so the gated overlay never "
                 "changes silently). `would-pass` = would clear the bar today.\n")
        L.append("| candidate | fwd-vol corr (21d) | HAC t | crisis-excl | folds | fwd-ret corr | "
                 "OOS-R² | CW p | would-pass |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for k, e in cand_evals.items():
            d = e.get("decision", {})
            L.append(_leg_row(k, e, f"⏳ ({e.get('n')} obs)" if d.get("scored") else "—"))
    if dsr.get("strat"):
        s = dsr["strat"]
        L.append("\n## Composite long/flat (context — return channel)\n")
        L.append(f"- Strategy Sharpe {s.get('sr_annual')} (ann) vs buy&hold "
                 f"{dsr.get('hold_sharpe_ann')} over {dsr.get('years')}y; "
                 f"DSR={s.get('dsr')} ({_dsr_word(s.get('dsr'))})")
        if dsr.get("bootstrap"):
            L.append(f"- Block-bootstrap Sharpe 95% CI {dsr['bootstrap'].get('sharpe_ci')}, "
                     f"maxDD CI {dsr['bootstrap'].get('maxdd_ci_pct')}%")
    L.append("\n## Gate decision\n")
    scored = [k for k, v in gate["legs"].items() if v["scored"]]
    L.append(f"- **Scored legs:** {scored or 'none — display-only'}")
    L.append(f"- Composite scored: {gate['composite']['scored']}")
    L.append(f"- {gate['note']}\n")
    L.append("\n_Even when scored, the regime is a SUBTRACT-ONLY risk/sizing overlay "
             "(drawdown + capital-efficiency), never a stand-alone return-alpha selector. "
             "Single-name dealer-gamma is NOT validated here and stays display-only._\n")
    return "\n".join(L)


def _dsr_word(d):
    from engine.validation import dsr_verdict
    return dsr_verdict(d) if d is not None else "n/a"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-gate", action="store_true",
                    help="persist data/vol_regime/gate.json (promote passing legs to scored)")
    args = ap.parse_args()
    r = run(write_gate=args.write_gate)
    if r.get("status") != "ok":
        print(json.dumps(r)); return 1
    print(r["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
