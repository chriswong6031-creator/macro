"""Local Projections (Jorda 2005) impulse-response estimator.

PURE MODULE - no I/O, no config, no store reads. Every function takes arrays and
returns arrays; the `__main__` CLI section is the one place that touches argparse,
json and stdout. Matches engine/synthetic_control.py:3-5's pure-module law.

WHAT THIS ESTIMATES
--------------------
For each horizon h = 0..HORIZONS, one OLS:

    y[t+h] - y[t-1]  =  a_h  +  beta_h * shock[t]  +  gamma_h' * controls[t]  +  e_{t+h}

`controls[t]` is LAGS lags of y and of shock, plus any caller-supplied exogenous
columns, ALL dated <= t - EMBARGO. beta_h is the impulse response at horizon h.
No cumulative-sum variant ships in v0: a cumulative IRF re-uses the same
overlapping residuals used here and would need its own, second, multiple-testing
and HAC correction rather than inheriting this one.

THE THREE GUARDS
-----------------
(a) LOOKAHEAD - every RHS column is dated <= t-EMBARGO, the shock sits at t, the
    target at t+h. `lp_slice` is the single definition of that window (mirrors
    engine/synthetic_control.py:107 pre_window_slice) and every fitting path
    routes through it. A horizon whose target runs past the end of the sample
    DROPS that row - never padded, never partial-summed.
(b) NON-INDEPENDENT SAMPLES - targets at horizon h overlap across t (y[t+h] and
    y[t+h+1] share (h-1) periods), so the residual is MA(h) by construction and a
    plain OLS se understates the true one. The coefficient se is a Newey-West
    Bartlett sandwich at truncation lag h+1 (HAC_LAG_RULE), with the effective lag
    clamped to min(lags, n-1) and BOTH `hac_lags` and `hac_lags_requested`
    reported - engine/validation.py:691-694's rule: printing the un-clamped ask is
    how an under-corrected t reads as a fully-corrected one. `_hac_sandwich` uses
    the identical 1/n-normalization-free sandwich and Bartlett weight
    `1 - j/(L+1)` as engine.validation.newey_west_tstat, so on an intercept-only
    design the two agree to 5 decimal places (measured: sandwich se=0.22333829 vs
    helper se=0.22334, both lags=4 on an MA(4) series, n=300). On overlapping LP
    targets that same measurement showed HAC/naive se ~= 1.83 - i.e. the naive OLS
    t on overlapping horizon targets overstates significance by roughly 83%.
(c) MULTIPLE TESTING - two mechanisms, both reported. (1) The horizon PANEL:
    H+1 horizons are H+1 tests, corrected with
    engine.validation.benjamini_hochberg (its monotone walk-up is already
    correct and is reused, never reimplemented); `reject` reads `q`, never `p`.
    (2) A SPECIFICATION SEARCH (choosing among lag lengths / shock definitions /
    samples) must be registered with engine.trial_ledger BEFORE anything is
    estimated - registration at generation, per
    engine/seasonality/event_study.py:1468-1473 ("multiple testing is incurred
    when a candidate is GENERATED, not when one survives to a headline"). Naming
    a `family` that was never registered raises UnregisteredSearchFamily
    (imported lazily, only when `family` is given, so the pure array path never
    pays for event_study's pandas import). `family=None` is legal: effective_n is
    then None and the returned note says the search is unpriced.

RESEARCH-ONLY, NO TRADING AUTHORITY. This module's output is evidence for a human
or a downstream promotion process (qledger is the sole promotion plane per the F10
lane's frozen judgment) - never a live trading signal by itself, and a rejecting
horizon is an ASSOCIATION, not a causal claim, absent an identification argument
the caller supplies out of band.

Nulls are never hidden: `impulse_response` always returns the same shape,
including the `null` block, whether or not anything rejects; every refusal is a
typed abstention (schema ABSTENTION_SCHEMA) with a named `reason`, never a silent
NaN.
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any

import numpy as np

# ---------------------------------------------------------------- pre-registered constants
HORIZONS = 20          # h = 0..20 inclusive (21 regressions)
LAGS = 4               # p lags of y and of shock entering as controls
EMBARGO = 1            # bars between the last admissible control bar and the shock bar
MIN_OBS_PER_H = 60     # usable rows required before a horizon is estimated
FDR_ALPHA = 0.10       # BH level across the horizon panel (matches validation.py:763 default)
CI_LEVEL = 0.95
SCHEMA = "engine.local_projections.irf.v1"
ABSTENTION_SCHEMA = "engine.local_projections.abstention.v1"
HAC_LAG_RULE = "h + 1"  # Newey-West truncation at horizon h; documented, not tunable


# ---------------------------------------------------------------- small pure helpers
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_sided_p(t: float) -> float:
    if t is None or not np.isfinite(t):
        return float("nan")
    return float(2.0 * (1.0 - _norm_cdf(abs(t))))


def _abstain(reason: str, **extra: Any) -> dict:
    """The structured non-answer. A refusal is a result with a name, never a
    silent NaN and never a number that reads like a weak finding."""
    payload = {"schema": ABSTENTION_SCHEMA, "abstained": True, "reason": reason}
    payload.update(extra)
    return payload


# ---------------------------------------------------------------- PIT window
def lp_slice(t: int, h: int, *, lags: int = LAGS, embargo: int = EMBARGO) -> dict:
    """THE single definition of the LP window.

    Returns {'control_lo': t-embargo-lags+1, 'control_hi': t-embargo,
    'shock': t, 'target': t+h}. Raises ValueError if control_hi >= t (the
    embargo gap collapsed) or target <= control_hi (a non-positive horizon
    window). Every other function in this module routes through here - the
    engine/synthetic_control.py:107 pattern."""
    control_hi = t - embargo
    control_lo = t - embargo - lags + 1
    target = t + h
    if control_hi >= t:
        raise ValueError("embargo must be >= 1 so the control block excludes bar t")
    if target <= control_hi:
        raise ValueError("target must fall strictly after the control window")
    return {"control_lo": control_lo, "control_hi": control_hi, "shock": t, "target": target}


def design_matrix(y, shock, *, lags: int = LAGS, embargo: int = EMBARGO,
                   controls=None) -> dict:
    """Pure. -> {'X': np.ndarray (T,k), 'names': list[str], 'valid': np.ndarray[bool] (T,)}

    Column 0 is the intercept, column 1 is shock[t], every remaining column is
    dated <= t-embargo: LAGS lags of y and of shock (nearest lag first), then
    any caller-supplied exogenous columns sampled at bar t-embargo (so an
    exogenous control obeys the same lookahead guard as the own-series lags).
    'valid' is False wherever any RHS cell is non-finite or the control window
    runs off the start of the sample."""
    y = np.asarray(y, dtype=float)
    shock = np.asarray(shock, dtype=float)
    T = len(y)

    ctrl_arr = None
    n_ctrl = 0
    if controls is not None:
        ctrl_arr = np.asarray(controls, dtype=float)
        if ctrl_arr.ndim == 1:
            ctrl_arr = ctrl_arr.reshape(-1, 1)
        n_ctrl = ctrl_arr.shape[1]

    names = ["const", "shock_t"]
    for j in range(1, lags + 1):
        names.append(f"y_lag{j}")
        names.append(f"shock_lag{j}")
    for i in range(n_ctrl):
        names.append(f"ctrl{i}")

    k = len(names)
    X = np.full((T, k), np.nan, dtype=float)
    valid = np.zeros(T, dtype=bool)

    for t in range(T):
        try:
            sl = lp_slice(t, 0, lags=lags, embargo=embargo)
        except ValueError:
            continue
        lo, hi = sl["control_lo"], sl["control_hi"]
        if lo < 0:
            continue
        row = [1.0, shock[t]]
        for idx in range(hi, lo - 1, -1):
            row.append(y[idx])
            row.append(shock[idx])
        if ctrl_arr is not None:
            if hi < len(ctrl_arr):
                row.extend(float(v) for v in ctrl_arr[hi])
            else:
                row.extend([np.nan] * n_ctrl)
        X[t] = row
        valid[t] = bool(np.all(np.isfinite(row)))

    return {"X": X, "names": names, "valid": valid}


# ---------------------------------------------------------------- estimation internals
def _ols(X: np.ndarray, yv: np.ndarray) -> tuple:
    """Plain OLS via least squares. -> (beta, resid, XtX_pinv)."""
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    xtx_pinv = np.linalg.pinv(X.T @ X)
    return beta, resid, xtx_pinv


def _hac_sandwich(X: np.ndarray, resid: np.ndarray, lags: int) -> np.ndarray:
    """Newey-West Bartlett sandwich covariance for OLS coefficients.

    Uses the identical normalization and Bartlett weight `1 - j/(L+1)` as
    engine.validation.newey_west_tstat, so on an intercept-only X the diagonal
    entry reproduces that helper's se to 5 decimal places (see module docstring
    for the measured check; tests/test_local_projections.py pins it)."""
    xtx_pinv = np.linalg.pinv(X.T @ X)
    G = X * resid[:, None]           # T x k, g_t rows
    meat = G.T @ G
    L = max(int(lags), 0)
    n = X.shape[0]
    L = min(L, max(n - 1, 0))
    for j in range(1, L + 1):
        w = 1.0 - j / (L + 1)
        Gj = G[j:].T @ G[:-j]        # sum_t outer(g_t, g_{t-j})
        meat += w * (Gj + Gj.T)
    return xtx_pinv @ meat @ xtx_pinv


def estimate_horizon(y, shock, h: int, *, lags: int = LAGS, embargo: int = EMBARGO,
                      controls=None, min_obs: int = MIN_OBS_PER_H,
                      hac_lags: int | None = None) -> dict:
    """One horizon. hac_lags defaults to h+1 (HAC_LAG_RULE). Returns a full
    result row or an abstention dict (schema ABSTENTION_SCHEMA)."""
    y = np.asarray(y, dtype=float)
    shock = np.asarray(shock, dtype=float)
    T = len(y)

    if not np.isfinite(y).any() or not np.isfinite(shock).any():
        return _abstain("non_finite_input", h=h)

    dm = design_matrix(y, shock, lags=lags, embargo=embargo, controls=controls)
    X_full, valid = dm["X"], dm["valid"]

    # a target is admissible only when t+h is in range and t-1 >= 0
    t_idx = np.arange(T)
    target_ok = (t_idx + h < T) & (t_idx - 1 >= 0)

    if not target_ok.any():
        return _abstain("horizon_exceeds_sample", h=h)

    mask = valid & target_ok
    n = int(mask.sum())
    if n < min_obs:
        return _abstain("insufficient_observations", h=h, n=n)

    shock_used = shock[mask]
    if not np.isfinite(shock_used).all() or float(np.var(shock_used)) <= 1e-18:
        return _abstain("degenerate_shock", h=h, n=n)

    X = X_full[mask]
    n_columns = X.shape[1]
    rank = int(np.linalg.matrix_rank(X))
    if rank < n_columns:
        return _abstain("rank_deficient_design", h=h, n=n)

    yv = y[t_idx[mask] + h] - y[t_idx[mask] - 1]
    if not np.isfinite(yv).all():
        return _abstain("non_finite_input", h=h, n=n)

    beta, resid, xtx_pinv = _ols(X, yv)

    dof = max(n - n_columns, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    se_naive = float(math.sqrt(max(sigma2 * xtx_pinv[1, 1], 0.0)))

    hac_lags_requested = int(hac_lags) if hac_lags is not None else int(h + 1)
    hac_lags_effective = int(min(hac_lags_requested, max(n - 1, 0)))

    V = _hac_sandwich(X, resid, hac_lags_effective)
    se = float(math.sqrt(max(V[1, 1], 0.0)))

    beta_shock = float(beta[1])
    t_stat = beta_shock / se if se > 0 else float("nan")
    p = _two_sided_p(t_stat)
    z = 1.959963984540054  # CI_LEVEL = 0.95 two-sided normal critical value
    hac_inflation = float(se / se_naive) if se_naive > 0 else float("nan")

    return {
        "schema": SCHEMA,
        "h": int(h),
        "beta": beta_shock,
        "se": se,
        "t": float(t_stat),
        "p": float(p),
        "ci_low": float(beta_shock - z * se),
        "ci_high": float(beta_shock + z * se),
        "n": n,
        "hac_lags": hac_lags_effective,
        "hac_lags_requested": hac_lags_requested,
        "se_naive": se_naive,
        "hac_inflation": hac_inflation,
    }


def impulse_response(y, shock, *, horizons: int = HORIZONS, lags: int = LAGS,
                      embargo: int = EMBARGO, controls=None,
                      min_obs: int = MIN_OBS_PER_H, fdr_alpha: float = FDR_ALPHA,
                      ledger=None, family: str | None = None) -> dict:
    """The headline. Raises UnregisteredSearchFamily when `family` is named but
    not present in `ledger.families()` (imported lazily so the pure array path
    never pays for engine.seasonality.event_study's pandas import)."""
    from engine.validation import benjamini_hochberg

    effective_n = None
    if family is not None:
        from engine.seasonality.event_study import (
            UnregisteredSearchFamily,
            family_is_registered,
        )
        if not family_is_registered(ledger, family):
            raise UnregisteredSearchFamily(
                f"search family {family!r} was never registered: call "
                "engine.trial_ledger.TrialLedger.log_grid/log_declared_budget at "
                "GENERATION, before impulse_response is inspected."
            )
        effective_n = int(ledger.effective_n(family))

    y = np.asarray(y, dtype=float)
    shock = np.asarray(shock, dtype=float)

    rows = [
        estimate_horizon(y, shock, h, lags=lags, embargo=embargo, controls=controls,
                          min_obs=min_obs)
        for h in range(horizons + 1)
    ]

    pvals = {str(row["h"]): row["p"] for row in rows if not row.get("abstained")}
    fdr = benjamini_hochberg(pvals, alpha=fdr_alpha)

    inflation_by_h = {
        str(row["h"]): row["hac_inflation"] for row in rows if not row.get("abstained")
    }

    dm = design_matrix(y, shock, lags=lags, embargo=embargo, controls=controls)
    n_by_horizon = {str(row["h"]): row.get("n", 0) for row in rows}
    abstained_horizons = [row["h"] for row in rows if row.get("abstained")]

    rejecting_horizons = sorted(int(h) for h, v in fdr.items() if v["reject"])

    result: dict = {
        "schema": SCHEMA,
        "irf": rows,
        "fdr": fdr,
        "multiple_testing": {
            "n_horizons_tested": horizons + 1,
            "alpha": fdr_alpha,
            "family": family,
            "effective_n": effective_n,
            "note": (
                "q is BH-adjusted across the horizon panel only. effective_n=None "
                "means no specification search was registered, so any search over "
                "lag length, shock definition or sample is UNPRICED - register the "
                "family with engine.trial_ledger before reading a winner."
            ),
        },
        "inference": {
            "se_kind": "newey_west_bartlett",
            "lag_rule": HAC_LAG_RULE,
            "why": (
                "targets at horizon h overlap across t, so the residual is MA(h) "
                "by construction and a plain OLS se understates the true one"
            ),
            "measured_inflation_by_h": inflation_by_h,
        },
        "pit": {
            "embargo": embargo,
            "lags": lags,
            "last_control_bar": "t - %d" % embargo,
            "targets_dropped_at_tail": {str(h): h for h in range(horizons + 1)},
        },
        "diagnostics": {
            "shock_variance": float(np.var(shock)),
            "n_by_horizon": n_by_horizon,
            "abstained_horizons": abstained_horizons,
            "rank": int(np.linalg.matrix_rank(dm["X"][dm["valid"]])) if dm["valid"].any() else 0,
            "n_columns": dm["X"].shape[1],
        },
        "null": {
            "any_horizon_rejects": bool(rejecting_horizons),
            "rejecting_horizons": rejecting_horizons,
        },
    }
    result["null"]["plain_words"] = plain_words(result)
    return result


def plain_words(result: dict) -> str:
    """One sentence, <= 30 words, no jargon."""
    null = result.get("null", {})
    rejecting = null.get("rejecting_horizons") or []
    if rejecting:
        return (
            f"A measurable effect showed up at {len(rejecting)} time-step(s) after "
            "the shock, and it survived correction for testing many time-steps at once."
        )
    return (
        "No time-step after the shock showed an effect that survived correction "
        "for testing many time-steps at once."
    )


def demo_series(*, true_beta: float = 0.010, decay: float = 0.75, n: int = 800,
                 horizons: int = HORIZONS, noise: float = 0.008,
                 seed: int = 11) -> tuple:
    """The known-truth DGP shared by the CLI and the test suite.

    y[t] = sum_{j=0..horizons} psi_j * shock[t-j] + eps[t], psi_j = true_beta * decay**j.
    -> (y, shock, true_irf) where true_irf has length horizons+1."""
    rng = np.random.default_rng(seed)
    shock = rng.standard_normal(n)
    psi = np.array([true_beta * (decay ** j) for j in range(horizons + 1)], dtype=float)
    y_signal = np.convolve(shock, psi)[:n]
    eps = noise * rng.standard_normal(n)
    y = y_signal + eps
    return y, shock, psi


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Projections IRF self-check CLI")
    parser.add_argument("--demo", action="store_true", help="run the synthetic demo DGP")
    parser.add_argument("--json", action="store_true", help="dump the full result as JSON")
    parser.add_argument("--horizons", type=int, default=HORIZONS)
    parser.add_argument("--lags", type=int, default=LAGS)
    parser.add_argument("--true-beta", type=float, default=0.010)
    parser.add_argument("--decay", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args(argv)

    if not args.demo:
        parser.print_help()
        return 2

    y, shock, true_irf = demo_series(
        true_beta=args.true_beta, decay=args.decay, horizons=args.horizons, seed=args.seed
    )
    result = impulse_response(y, shock, horizons=args.horizons, lags=args.lags)

    if args.json:
        print(json.dumps(result))
        return 0 if any(not r.get("abstained") for r in result["irf"]) else 2

    header = f"{'h':>3} {'beta':>9} {'se(HAC)':>9} {'t':>7} {'p':>7} {'q':>7} {'reject':>7} {'n':>5} {'true':>9} {'err':>9}"
    print(header)
    any_estimated = False
    max_abs_err = 0.0
    for row in result["irf"]:
        h = row["h"]
        if row.get("abstained"):
            print(f"{h:>3} ABSTAIN reason={row['reason']}")
            continue
        any_estimated = True
        q = result["fdr"].get(str(h), {}).get("q")
        reject = result["fdr"].get(str(h), {}).get("reject")
        true_h = float(true_irf[h]) if h < len(true_irf) else float("nan")
        err = row["beta"] - true_h
        max_abs_err = max(max_abs_err, abs(err))
        print(f"{h:>3} {row['beta']:>9.5f} {row['se']:>9.5f} {row['t']:>7.3f} "
              f"{row['p']:>7.4f} {q:>7.4f} {str(reject):>7} {row['n']:>5} "
              f"{true_h:>9.5f} {err:>9.5f}")

    print(f"max |beta_h - psi_h| = {max_abs_err:.5f}")
    print(result["null"]["plain_words"])

    if not any_estimated:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
