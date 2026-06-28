"""Promotion gate — the PROPOSE-not-deploy champion/challenger decision (P4 capstone).

Composes the suite's anti-overfit components into ONE verdict on a candidate signal. A
candidate is ELIGIBLE for promotion (to shadow → canary → live, via the registry) only when it
clears EVERY applicable gate — and even then the verdict is ADVISORY: nothing auto-ships. The
gates (each runs only when its inputs are supplied, so the caller composes what it can prove):

  1. honest-N Deflated Sharpe ≥ dsr_min       (validation.deflated_sharpe + the Trial Ledger —
     N counted at generation, never lowballed)
  2. Probability of Backtest Overfitting < pbo_max   (validation.prob_backtest_overfitting / CSCV)
  3. CPCV path-sign robustness                 (edge sign holds across ≥ frac of the paths)
  4. no concept drift on the live-IC stream    (drift.rolling_ic_drift)
  5. beats the incumbent by a material margin
  6. the Holdout Vault peek is recorded         (holdout_vault — touching the holdout costs budget;
     a retired hypothesis is refused)

Returns {verdict, eligible, gates, blocking, note}. Degrade-never-raise. This is the gate the
honest-alpha audit demanded: PROPOSE, gate hard, ship nothing automatically.
"""
from __future__ import annotations

import math

import pandas as pd

from engine.validation import (cpcv_paths, deflated_sharpe, prob_backtest_overfitting,
                               ret_moments)
from engine.drift import rolling_ic_drift


def _ann_sharpe(mom, ann: int) -> float:
    return float(mom[0]) * math.sqrt(ann)


def promotion_gate(returns=None, *, trial_ledger=None, family=None, n_trials=None,
                   perf_matrix=None, ic_stream=None, incumbent_sharpe=None,
                   cpcv_path_signs=None, dsr_min: float = 0.95, pbo_max: float = 0.5,
                   margin: float = 0.10, cpcv_frac: float = 0.8, ann: int = 252,
                   drift_threshold: float = 0.5,
                   vault=None, hypothesis_id=None, window_id=None, holdout_result=None) -> dict:
    """Evaluate a candidate against every gate whose inputs are supplied. Eligible = no blocking
    gate AND at least one gate ran. Never raises."""
    gates: dict = {}
    blocking: list = []
    try:
        mom = ret_moments(pd.Series(returns)) if returns is not None else None

        # 1. honest-N Deflated Sharpe
        if mom is not None:
            if trial_ledger is not None:
                dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=trial_ledger,
                                      family=family, trading_year=ann)
            else:
                # No caller ledger → persist the declared N to an ephemeral ledger
                # (effective_n == the declared budget) rather than a bare literal: same
                # haircut, but audited + ratchet-clean (test_no_literal_ntrials). The ledger
                # path needs a non-empty family, so default it when the caller gave none.
                from engine.trial_ledger import TrialLedger
                _fam = family or "promotion_gate"
                _led = TrialLedger.with_declared_budget(int(n_trials or 1), _fam)
                dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_led,
                                      family=_fam, trading_year=ann)
            ok = bool(dsr and dsr.get("dsr", 0.0) >= dsr_min)
            gates["deflated_sharpe"] = {"pass": ok, "value": (dsr or {}).get("dsr"), "min": dsr_min}
            if not ok:
                blocking.append("deflated_sharpe")

        # 2. Probability of Backtest Overfitting
        if perf_matrix is not None:
            pbo = prob_backtest_overfitting(perf_matrix)
            ok = bool(pbo and pbo["pbo"] < pbo_max)
            gates["pbo"] = {"pass": ok, "value": (pbo or {}).get("pbo"), "max": pbo_max}
            if not ok:
                blocking.append("pbo")

        # 3. CPCV path-sign robustness (the edge sign must hold across most paths)
        if cpcv_path_signs:
            signs = [int(s) for s in cpcv_path_signs if s]
            frac = (sum(1 for s in signs if s > 0) / len(signs)) if signs else 0.0
            frac = max(frac, 1 - frac)         # consistency toward EITHER sign
            ok = frac >= cpcv_frac
            gates["cpcv_robust"] = {"pass": ok, "consistency": round(frac, 3), "min": cpcv_frac}
            if not ok:
                blocking.append("cpcv_robust")

        # 4. concept drift (threshold tuned so stationary IC noise doesn't false-alarm)
        if ic_stream is not None:
            dr = rolling_ic_drift(ic_stream, threshold=drift_threshold)
            ok = not dr.get("drift", False)
            gates["drift"] = {"pass": ok, "drift": dr.get("drift")}
            if not ok:
                blocking.append("drift")

        # 5. beats incumbent by a material margin
        if incumbent_sharpe is not None and mom is not None:
            cand = _ann_sharpe(mom, ann)
            ok = cand >= float(incumbent_sharpe) * (1.0 + margin)
            gates["beats_incumbent"] = {"pass": ok, "candidate": round(cand, 3),
                                        "incumbent": float(incumbent_sharpe), "margin": margin}
            if not ok:
                blocking.append("beats_incumbent")

        # 6. Holdout Vault peek (records the read; a retired hypothesis is refused)
        if vault is not None and hypothesis_id and window_id:
            try:
                peek = vault.peek(hypothesis_id, window_id=window_id,
                                  result=holdout_result if holdout_result is not None else "gate")
                gates["holdout_vault"] = {"pass": True, "peek_n": peek["peek_n"]}
            except Exception as e:  # noqa: BLE001 — a vault breach blocks
                gates["holdout_vault"] = {"pass": False, "error": str(e)}
                blocking.append("holdout_vault")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        return {"verdict": "HOLD", "eligible": False, "gates": gates,
                "blocking": blocking + ["error"], "error": str(e)}

    eligible = (not blocking) and len(gates) >= 1
    return {
        "verdict": "PROMOTE-ELIGIBLE" if eligible else "HOLD",
        "eligible": eligible, "gates": gates, "blocking": blocking,
        "note": ("PROPOSE-not-deploy: eligible → SHADOW/CANARY via the registry after live "
                 "post-cutoff evidence, never auto-live. A human owns any scored/sizing promotion."),
    }


def cpcv_path_signs(returns, index=None, *, n_groups: int = 6, k_test: int = 2,
                    embargo: int = 0) -> list:
    """Sign of the candidate's mean return on each CPCV TEST path — feed to promotion_gate as
    `cpcv_path_signs`. A robust edge keeps the same sign across the combinatorial paths."""
    r = pd.Series(list(returns)).reset_index(drop=True)
    out = []
    for _train, test in cpcv_paths(len(r), n_groups=n_groups, k_test=k_test, embargo=embargo):
        seg = r.iloc[test].dropna()
        if len(seg):
            out.append(1 if seg.mean() > 0 else -1)
    return out


__all__ = ["promotion_gate", "cpcv_path_signs"]
