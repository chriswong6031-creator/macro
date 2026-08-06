"""Donor-pool synthetic-control counterfactuals for event studies.

PURE MODULE — no I/O, no config, no store reads. Every function takes arrays and
returns arrays. The caller owns loading, calendars and event lists; this file owns
the estimator and nothing else.

WHY THIS EXISTS
---------------
The house event-study harness (scripts/backtest_event_priors.py, engine/index_changes.py)
scores an event by BENCHMARK-ADJUSTED CAR: r_treated - r_SPY, or r_treated - r_sector.
That is a one-donor counterfactual with the weight pinned at 1.0 and never fitted. It is
consistent only if the benchmark actually spans the treated name's factor exposure.
Goldsmith-Pinkham & Lyu (arXiv 2511.15123) is the direct statement of the problem:
factor-model event-study estimates can be inconsistent under misspecification, and the
repair is a REPLICATING PORTFOLIO — a weighted donor pool fitted on pre-event data.

This module builds that estimator. It does not replace the incumbent; it stands beside
it so the two can be scored against the same placebo distribution. An estimator that
moves an answer without shrinking its placebo dispersion has bought nothing.

THE TWO PRE-REGISTERED ESTIMATORS
---------------------------------
`matched_k`  (v0, robust)  top-k eligible donors by pre-window return correlation,
                           screened to a vol-similarity band, EQUAL weight. Zero fitted
                           parameters beyond the selection itself, so there is nothing to
                           overfit; it is the honest floor the fitted estimator must beat.
`sc_nnls`    (classic SC)  non-negative least squares on pre-window returns with weights
                           constrained to the probability simplex (w >= 0, sum w = 1) —
                           the Abadie-Diamond-Hainmueller constraint set. Solved by
                           accelerated projected gradient (FISTA) with an EXACT Euclidean
                           simplex projection. Pure numpy: scipy appears in engine/ only
                           as a soft local import with a numpy fallback (theme_discovery,
                           btc_regime_ledger, intraday_greeks), and the dominant idiom
                           here is explicitly scipy-free (grading.py, trial_ledger.py,
                           factor_orthogonal.py). No new dependency is taken.

No intercept is fitted. On RETURNS (not price levels) the mean is ~0 by construction and
the simplex constraint is what makes the weights interpretable as a portfolio. A fitted
intercept would let the counterfactual drift away from any real tradable basket.

PIT LAW (the part that must not be got wrong)
---------------------------------------------
Weights are fitted ONLY on pre-event data. `pre_window_slice` is the single place the
window is defined, and every fitting path goes through it:

    pre-window = PRE_WINDOW sessions ending at t-EMBARGO-1 inclusive
               = sessions [t-125, t-6] for the defaults (120 sessions, embargo 5)

Nothing at or after t-5 can enter a fit. The embargo is not decoration: for the S&P
index-add family the announcement run-up is the effect being measured, and a pre-window
running up to t-1 would fit the donors to the leak and estimate it away. The test
`test_pit_perturbation_does_not_move_weights` pins this by perturbing the panel at every
session >= t-EMBARGO and asserting the weights are bit-identical.

DONOR-POOL CONSTRUCTION (pre-registered; `eligible_donors`)
-----------------------------------------------------------
A donor is admissible for a treated name at event session t when ALL hold:
  - it is not the treated name itself;
  - it has NO event of its own within +/- EVENT_EXCLUSION sessions of t (a contaminated
    donor imports the treatment into the counterfactual and biases tau toward zero);
  - it has >= MIN_COVERAGE of the pre-window populated (no NaN-stuffed donors);
  - its 20d median dollar volume AT THE PRE-WINDOW END is >= DVOL_FLOOR (a donor nobody
    can trade is not a replicating portfolio, and illiquid returns are mostly noise).
The price floor is the caller's business — the study applies the house $5 universe floor
and discloses it; this module does not invent universe law.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No inference. `effect` returns per-day tau_t and cumulative CARs and stops. Clustering,
HAC, placebo distributions and gates belong to the study script, where they can be
pre-registered against a specific event family. No fused composite of the two estimators
is formed anywhere — they are reported side by side, always separately visible.

Dependencies: numpy only.
"""

from __future__ import annotations

import math
import warnings

import numpy as np

__all__ = [
    "PRE_WINDOW", "EMBARGO", "EVENT_EXCLUSION", "MIN_COVERAGE", "DVOL_FLOOR",
    "PRESCREEN_M", "MATCHED_K", "VOL_BAND", "CAR_WINDOWS", "METHODS",
    "VOL_BAND_FALLBACKS",
    "pre_window_slice", "eligible_donors", "project_to_simplex",
    "solve_simplex_ls", "solve_simplex_ls_batch", "prescreen_donors",
    "donor_weights", "donor_weights_batch", "counterfactual_path", "effect",
]

# ---------------------------------------------------------------- pre-registered constants
PRE_WINDOW = 120          # sessions used to fit the counterfactual
EMBARGO = 5               # sessions before t that are withheld from the fit
EVENT_EXCLUSION = 21      # a donor with its own event this close is contaminated
MIN_COVERAGE = 0.90       # fraction of the pre-window a donor must actually populate
DVOL_FLOOR = 2_000_000.0  # 20d median dollar volume at the pre-window end
PRESCREEN_M = 50          # donors handed to the fitted solver (top-M by pre-window corr)
MATCHED_K = 20            # donors kept by the equal-weight estimator
VOL_BAND = (0.5, 2.0)     # admissible ratio of donor pre-window vol to treated pre-window vol
CAR_WINDOWS = ((0, 0), (0, 5), (0, 20))
METHODS = ("matched_k", "sc_nnls")


# ---------------------------------------------------------------- PIT window
def pre_window_slice(event_sess: int, *, pre_window: int = PRE_WINDOW,
                     embargo: int = EMBARGO) -> slice:
    """The ONLY definition of the fitting window.

    Returns the slice covering `pre_window` sessions ending `embargo`+1 sessions before
    the event: for the defaults, sessions [t-125, t-6] inclusive. The slice's stop is
    t-embargo, so session t-embargo itself and everything after it is excluded.

    A negative start is the caller's signal that the store does not reach far enough
    back. This function does NOT police that (nor does `eligible_donors`, which never
    sees the slice) — the study's `_attach_sessions` is the single place events without a
    full pre-window are refused.
    """
    stop = int(event_sess) - int(embargo)
    return slice(stop - int(pre_window), stop)


# ---------------------------------------------------------------- donor admission
def eligible_donors(
    *,
    donor_pre: np.ndarray,
    donor_dvol: np.ndarray,
    event_distance: np.ndarray,
    treated_col: int | None = None,
    coverage_min: float = MIN_COVERAGE,
    dvol_floor: float = DVOL_FLOOR,
    exclusion: int = EVENT_EXCLUSION,
) -> np.ndarray:
    """Boolean admission mask over the donor cross-section. Pure; order-preserving.

    donor_pre      (T_pre, N) pre-window returns, NaN where the name has no print.
    donor_dvol     (N,) 20d median dollar volume measured AT THE PRE-WINDOW END (causal).
    event_distance (N,) |sessions| from the event to that donor's own nearest event;
                   np.inf for a donor with no event of its own. Donors strictly inside
                   +/- `exclusion` are refused.
    treated_col    column index of the treated name if it sits in the same matrix.
    """
    donor_pre = np.asarray(donor_pre, dtype=float)
    if donor_pre.ndim != 2:
        raise ValueError("donor_pre must be 2-D (T_pre, N)")
    n_pre, n_donors = donor_pre.shape
    if n_pre <= 0:
        return np.zeros(n_donors, dtype=bool)

    coverage = np.isfinite(donor_pre).sum(axis=0) / float(n_pre)
    ok = coverage >= float(coverage_min)
    ok &= np.asarray(donor_dvol, dtype=float) >= float(dvol_floor)
    ok &= np.asarray(event_distance, dtype=float) > float(exclusion)
    # A donor whose pre-window never moves cannot be standardized or fitted. An all-NaN
    # column is expected here (names that had not listed yet), and nanstd warns on it —
    # suppressed at the source rather than globally, so real numeric warnings elsewhere
    # in the study stay visible.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        sd = np.nanstd(np.where(np.isfinite(donor_pre), donor_pre, np.nan), axis=0)
    ok &= np.isfinite(sd) & (sd > 0.0)
    if treated_col is not None and 0 <= int(treated_col) < n_donors:
        ok[int(treated_col)] = False
    return ok


# ---------------------------------------------------------------- simplex geometry
def project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Exact Euclidean projection onto {w : w >= 0, sum w = 1} (Duchi et al. 2008).

    Vectorized over leading axes: the last axis is the simplex axis, so a (E, M) input
    projects E problems at once. O(M log M) per problem, deterministic, no tuning.
    """
    v = np.asarray(v, dtype=float)
    if v.shape[-1] == 0:
        return v.copy()
    u = np.sort(v, axis=-1)[..., ::-1]
    css = np.cumsum(u, axis=-1)
    idx = np.arange(1, v.shape[-1] + 1, dtype=float)
    cond = (u - (css - 1.0) / idx) > 0
    # rho = index of the LAST True along the simplex axis (always >= 0: cond[...,0] is
    # u0 - (u0 - 1) = 1 > 0, so the first entry is unconditionally True).
    rho = (v.shape[-1] - 1) - np.argmax(cond[..., ::-1], axis=-1)
    theta = (np.take_along_axis(css, rho[..., None], axis=-1) - 1.0) / (rho[..., None] + 1.0)
    return np.maximum(v - theta, 0.0)


def solve_simplex_ls_batch(
    Y: np.ndarray,
    D: np.ndarray,
    *,
    max_iter: int = 600,
    tol: float = 1e-11,
) -> np.ndarray:
    """min_w ||y - D w||^2  s.t.  w >= 0, sum w = 1 — solved for a BATCH of problems.

    Y (E, T) treated pre-window returns; D (E, T, M) donor pre-window returns.
    Returns (E, M) weights on the simplex.

    Accelerated projected gradient (FISTA) with the exact projection above. The problem
    is convex with a compact feasible set, so this converges to the global optimum; the
    batch form exists because the study fits ~10^5 of these (events x placebo draws) and
    a per-problem Python loop would not finish. Gram matrices are precomputed once per
    call, making each iteration an (E, M, M) x (E, M) matvec.

    Deterministic: exact per-problem step 1/L, fixed start at the equal-weight point, no
    randomness anywhere.

    max_iter=600 is not a guess. On realistically-conditioned donor matrices (dominant
    market factor, median Gram condition number ~370, T=120, M=50) 600 iterations sit
    within 5e-9 relative objective of a 20,000-iteration reference, with weights within
    4e-5 — roughly four orders of magnitude tighter than anything the CAR arithmetic
    downstream can resolve. `tol` exits earlier on easier problems.
    """
    Y = np.atleast_2d(np.asarray(Y, dtype=float))
    D = np.asarray(D, dtype=float)
    if D.ndim == 2:
        D = D[None, ...]
    if D.ndim != 3:
        raise ValueError("D must be (E, T, M) or (T, M)")
    n_e, n_t, n_m = D.shape
    if Y.shape != (n_e, n_t):
        raise ValueError(f"Y {Y.shape} does not match D {D.shape}")
    if n_m == 0:
        return np.zeros((n_e, 0))
    if n_m == 1:
        return np.ones((n_e, 1))
    if not (np.isfinite(D).all() and np.isfinite(Y).all()):
        raise ValueError("solve_simplex_ls_batch requires finite inputs; caller must "
                         "drop or impute NaNs before fitting")

    gram = np.matmul(np.swapaxes(D, 1, 2), D)          # (E, M, M)
    dty = np.matmul(np.swapaxes(D, 1, 2), Y[..., None])[..., 0]   # (E, M)

    # Lipschitz constant of grad f(w) = 2 D'(Dw - y) is 2*lambda_max(D'D), computed
    # EXACTLY per problem (batched eigvalsh on the M x M Gram, one O(M^3) call for the
    # whole batch). A cheap global bound like the trace overstates L by the Gram's
    # eigenvalue spread — on returns the market factor dominates, so a trace step would
    # be ~5-10x too small and FISTA would not converge inside max_iter.
    lam = np.linalg.eigvalsh(gram)[:, -1]              # (E,)
    lip = 2.0 * lam
    bad = ~np.isfinite(lip) | (lip <= 0.0)
    if bad.all():
        return np.full((n_e, n_m), 1.0 / n_m)
    step = np.where(bad, 0.0, 1.0 / np.where(bad, 1.0, lip))[:, None]   # (E, 1)

    w = np.full((n_e, n_m), 1.0 / n_m)
    z = w.copy()
    t = 1.0
    for _ in range(int(max_iter)):
        grad = 2.0 * (np.matmul(gram, z[..., None])[..., 0] - dty)
        w_new = project_to_simplex(z - step * grad)
        t_new = 0.5 * (1.0 + math.sqrt(1.0 + 4.0 * t * t))
        z = w_new + ((t - 1.0) / t_new) * (w_new - w)
        shift = float(np.max(np.abs(w_new - w)))
        w, t = w_new, t_new
        if shift < tol:
            break
    return w


def solve_simplex_ls(y: np.ndarray, D: np.ndarray, **kw) -> np.ndarray:
    """Single-problem form of `solve_simplex_ls_batch`. Returns (M,)."""
    return solve_simplex_ls_batch(np.asarray(y, dtype=float)[None, :],
                                  np.asarray(D, dtype=float)[None, ...], **kw)[0]


# ---------------------------------------------------------------- donor screening
def _standardize(x: np.ndarray, axis: int = 0) -> np.ndarray:
    mu = np.mean(x, axis=axis, keepdims=True)
    sd = np.std(x, axis=axis, keepdims=True)
    sd = np.where(sd > 0, sd, np.nan)
    return (x - mu) / sd


#: Incremented whenever the pre-registered vol band admits nothing and `prescreen_donors`
#: falls back to the unbanded pool. A pre-registered screen that silently disengages is a
#: screen the study cannot say it applied — the harness reads and reports this counter.
VOL_BAND_FALLBACKS = np.zeros(1, dtype=np.int64)


def prescreen_donors(
    pre_treated: np.ndarray,
    pre_donors: np.ndarray,
    *,
    m: int = PRESCREEN_M,
    vol_band: tuple[float, float] | None = VOL_BAND,
) -> np.ndarray:
    """Column indices of the top-`m` donors by pre-window return correlation.

    Donors outside `vol_band` x the treated name's own pre-window vol are dropped first:
    a donor ten times as volatile can carry a high correlation and still wreck the
    counterfactual's scale. Ties break by column order, so the result is deterministic.

    Curating the donor pool before fitting is standard synthetic-control practice AND is
    what makes the study tractable (the fitted solver then sees M columns, not ~5,000).
    It is pre-registered here rather than tuned later.
    """
    y = np.asarray(pre_treated, dtype=float)
    D = np.asarray(pre_donors, dtype=float)
    if D.ndim != 2 or D.shape[0] != y.shape[0]:
        raise ValueError("pre_donors must be (T_pre, N) matching pre_treated (T_pre,)")
    n = D.shape[1]
    if n == 0:
        return np.zeros(0, dtype=int)

    keep = np.ones(n, dtype=bool)
    if vol_band is not None:
        vol_t = float(np.std(y))
        vol_d = np.std(D, axis=0)
        if vol_t > 0:
            lo, hi = float(vol_band[0]) * vol_t, float(vol_band[1]) * vol_t
            keep &= (vol_d >= lo) & (vol_d <= hi)
    if not keep.any():                     # band emptied the pool -> fall back to all
        keep = np.ones(n, dtype=bool)
        VOL_BAND_FALLBACKS[0] += 1         # counted, not silent

    zy = _standardize(y[:, None])[:, 0]
    zd = _standardize(D)
    corr = np.full(n, -np.inf)
    valid = keep & np.isfinite(zd).all(axis=0) & bool(np.isfinite(zy).all())
    if valid.any():
        corr[valid] = (zy[:, None] * zd[:, valid]).mean(axis=0)
    corr = np.where(np.isfinite(corr), corr, -np.inf)
    order = np.lexsort((np.arange(n), -corr))   # -corr primary, column index breaks ties
    order = order[np.isfinite(corr[order])]
    return order[: int(m)]


# ---------------------------------------------------------------- weights
def donor_weights(
    pre_treated: np.ndarray,
    pre_donors: np.ndarray,
    method: str = "sc_nnls",
    *,
    k: int = MATCHED_K,
    vol_band: tuple[float, float] | None = VOL_BAND,
    **solver_kw,
) -> np.ndarray:
    """Weights over the donor columns of `pre_donors`, fitted on PRE-EVENT data only.

    pre_treated (T_pre,)    treated name's pre-window returns
    pre_donors  (T_pre, N)  admissible donors' pre-window returns (caller has already
                            applied `eligible_donors`)
    method      'matched_k' equal weight over the top-k by correlation (vol-banded)
                'sc_nnls'   simplex-constrained least squares over the top-PRESCREEN_M

    Returns (N,) weights, non-negative and summing to 1, zero outside the selected set.
    Both branches return a full-width vector so the two estimators are directly
    comparable and `counterfactual_path` never needs to know which produced them.

    EXCEPTION to "summing to 1": when no donor survives the screen — an empty pool, or a
    treated series carrying a NaN, which makes every correlation undefined — the return
    is the ALL-ZERO vector. That is deliberate and fails safe: it propagates a NaN
    counterfactual rather than a confident equal-weight guess over donors that were never
    shown to resemble anything. Callers must treat sum(w)==0 as "no estimate".
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")
    y = np.asarray(pre_treated, dtype=float)
    D = np.asarray(pre_donors, dtype=float)
    if D.ndim != 2 or D.shape[0] != y.shape[0]:
        raise ValueError("pre_donors must be (T_pre, N) matching pre_treated (T_pre,)")
    n = D.shape[1]
    w = np.zeros(n)
    if n == 0:
        return w

    if method == "matched_k":
        sel = prescreen_donors(y, D, m=int(k), vol_band=vol_band)
        if sel.size == 0:
            return w
        w[sel] = 1.0 / float(sel.size)
        return w

    sel = prescreen_donors(y, D, m=PRESCREEN_M, vol_band=vol_band)
    if sel.size == 0:
        return w
    w[sel] = solve_simplex_ls(y, D[:, sel], **solver_kw)
    return w


def donor_weights_batch(
    pre_treated: np.ndarray,
    pre_donors: np.ndarray,
    method: str = "sc_nnls",
    *,
    k: int = MATCHED_K,
    vol_band: tuple[float, float] | None = VOL_BAND,
    **solver_kw,
) -> np.ndarray:
    """Batched `donor_weights` over E events. Returns (E, N).

    pre_treated (E, T_pre); pre_donors (E, T_pre, N).

    Equivalent to looping `donor_weights` — pinned by
    tests/test_synthetic_control.py::test_donor_weights_batch_matches_the_loop, which
    covers SHORT pools specifically. An earlier version padded short pools with zero
    columns to make the batch rectangular; that silently relaxed sum(w)=1 to sum(w)<=1
    over the real donors (the solver parks mass on the zero column to shrink the
    counterfactual), and renormalizing afterwards rescaled the wrong solution rather than
    solving the constrained one — up to 0.41 absolute weight error and +22% pre-window
    objective on a 3-donor pool. Events are now GROUPED BY ACTUAL POOL WIDTH and each
    width solved at its true dimension.
    """
    Y = np.atleast_2d(np.asarray(pre_treated, dtype=float))
    D = np.asarray(pre_donors, dtype=float)
    if D.ndim == 2:
        D = D[None, ...]
    n_e, n_t, n = D.shape
    if Y.shape != (n_e, n_t):
        raise ValueError(f"pre_treated {Y.shape} does not match pre_donors {D.shape}")
    out = np.zeros((n_e, n))
    if n == 0:
        return out

    width = int(k) if method == "matched_k" else PRESCREEN_M
    sel = np.full((n_e, width), -1, dtype=int)
    for e in range(n_e):
        s = prescreen_donors(Y[e], D[e], m=width, vol_band=vol_band)
        sel[e, : s.size] = s
    ok = sel >= 0

    if method == "matched_k":
        cnt = ok.sum(axis=1).astype(float)
        for e in range(n_e):
            if cnt[e] > 0:
                out[e, sel[e, ok[e]]] = 1.0 / cnt[e]
        return out

    # Group by ACTUAL pool width and solve each group at its true dimension. Padding to a
    # common width would relax the simplex constraint (see docstring).
    widths = ok.sum(axis=1)
    for w_actual in np.unique(widths):
        if w_actual == 0:
            continue
        grp = np.flatnonzero(widths == w_actual)
        Dsel = np.empty((grp.size, n_t, int(w_actual)))
        for gi, e in enumerate(grp):
            Dsel[gi] = D[e][:, sel[e, ok[e]]]
        w_sel = solve_simplex_ls_batch(Y[grp], Dsel, **solver_kw)
        for gi, e in enumerate(grp):
            out[e, sel[e, ok[e]]] = w_sel[gi]
    return out


# ---------------------------------------------------------------- counterfactual + effect
def counterfactual_path(weights: np.ndarray, donor_returns: np.ndarray) -> np.ndarray:
    """Weighted donor return path — the replicating portfolio's realized return.

    weights (N,) or (E, N); donor_returns (T, N) or (E, T, N). Returns (T,) or (E, T).
    Donor NaNs are treated as zero contribution AND the weights are renormalized over the
    donors that actually printed on that day, so a single halted donor cannot silently
    shrink the whole counterfactual toward zero.
    """
    w = np.asarray(weights, dtype=float)
    R = np.asarray(donor_returns, dtype=float)
    single = (w.ndim == 1)
    if single:
        w = w[None, :]
        R = R[None, ...] if R.ndim == 2 else R
    if R.ndim != 3:
        raise ValueError("donor_returns must be (T, N) or (E, T, N)")
    if w.shape[0] != R.shape[0] or w.shape[1] != R.shape[2]:
        raise ValueError(f"weights {w.shape} do not match donor_returns {R.shape}")

    live = np.isfinite(R)
    filled = np.where(live, R, 0.0)
    num = np.einsum("en,etn->et", w, filled)
    den = np.einsum("en,etn->et", w, live.astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        path = np.where(den > 0, num / den, np.nan)
    return path[0] if single else path


def effect(
    treated_returns: np.ndarray,
    counterfactual: np.ndarray,
    *,
    windows: tuple[tuple[int, int], ...] = CAR_WINDOWS,
) -> dict:
    """Per-day tau_t and cumulative abnormal returns over the pre-registered windows.

    treated_returns / counterfactual are (T,) or (E, T), indexed from the EVENT DAY:
    position 0 is day 0. tau_t = r_treated,t - r_counterfactual,t; CAR[a,b] = sum of tau
    over days a..b inclusive.

    Returns {'tau': ..., 'car': {'0': ..., '0_5': ..., '0_20': ...}}. A window extending
    past the supplied path, or containing a NaN, yields NaN for that window rather than a
    partial sum quietly presented as a full one.
    """
    r = np.asarray(treated_returns, dtype=float)
    c = np.asarray(counterfactual, dtype=float)
    single = (r.ndim == 1)
    if single:
        r, c = r[None, :], c[None, :]
    if r.shape != c.shape:
        raise ValueError(f"treated {r.shape} and counterfactual {c.shape} differ")

    tau = r - c
    n_t = tau.shape[1]
    car: dict[str, np.ndarray | float] = {}
    for a, b in windows:
        key = f"{a}" if a == b else f"{a}_{b}"
        if a < 0 or b >= n_t:
            vals = np.full(tau.shape[0], np.nan)
        else:
            seg = tau[:, a:b + 1]
            vals = np.where(np.isfinite(seg).all(axis=1), np.nansum(seg, axis=1), np.nan)
        car[key] = float(vals[0]) if single else vals
    return {"tau": tau[0] if single else tau, "car": car}
