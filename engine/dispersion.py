"""Cross-sectional DISPERSION & correlation regime — the meta-signal for WHEN stock
selection pays (engine v2, display + a gross dial).

Alpha and achievable information-ratio scale with cross-sectional dispersion (S&P DJI,
Gorman-Sapra-Weigand): when names move together (low dispersion / high pairwise
correlation, a macro-driven tape) stock selection earns little no matter how good the
signal; when they fan out (high dispersion, often high-VIX) selection — and our
reversal/timing legs — pay the most. So this is the dial that sizes SELECTION
conviction (the gross taken on the cross-sectional book), kept DISTINCT from the
market-timing overlay that sizes net/long exposure.

Kept to 2-3 DISCRETE states with fixed thresholds (a continuous fitted curve is the
classic overfit trap). Point-in-time; correlation is the standard EW-var / mean-name-var
approximation (a full pairwise matrix on ~1600 names is unestimable and overfit)."""
from __future__ import annotations

import numpy as np
import pandas as pd

_EIGEN_MIN_NAMES = 20          # minimum names required for eigen block
_EIGEN_MIN_DAYS = 120          # minimum days required for eigen block
_EIGEN_BASIS_DAYS = 252        # fixed trailing window (RUL-ORTH-6)
_EIGEN_COVERAGE_THRESH = 0.80  # per-name non-null fraction threshold
_EIGEN_TOP_PCS = 3             # PCs used for idio_dispersion_share residual

_HI, _LO = 0.66, 0.33          # dispersion-percentile terciles
# SHADOW gross dial — the hand-picked tercile magnitudes. DISPLAY-ONLY per the passport
# rule (US_BOARD_MEASUREMENT.md §Study 3 / audit #20): direction is suggestive and roughly
# monotone (alpha IC negative in low-dispersion, positive in mid/high) but ~8 correlated
# rebalances/bucket forbids any claim, and lean_in=1.20 grosses UP into the high-VIX stress
# the sizing layer is mandated to fade. Until a survivorship-clean selection-IR edge is
# MEASURED, the LIVE gross is clamped to 1.0 and this stays a shadow so a future measured
# promotion is one config change (flip _LIVE_CLAMP off).
_SHADOW_GROSS = {"lean_in": 1.20, "neutral": 1.0, "lean_out": 0.75}
_LIVE_CLAMP = 1.0              # what actually binds sizing while basis=prior/display-only
_LABEL = {"lean_in": ("Selection pays — high dispersion", "选股有效 — 高离散度"),
          "neutral": ("Mixed selection backdrop", "选股环境中性"),
          "lean_out": ("Macro tape — selection muted", "宏观主导 — 选股弱化")}


def _compute_eigen_block(full_returns: pd.DataFrame) -> dict | None:
    """Compute descriptive eigen-concentration fields on the trailing 252-day basis.

    Design authority: research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md
    Ratified: RUL-ORTH-6 (fixed trailing-252d basis ONLY — no expanding-window
    percentile; gross_mult_live = 1.0 unconditionally regardless of findings).
    Status: DISP-EIGEN-1 registered, activation DEFERRED pending DISP-GATE-1
    non-stationarity resolution.

    Returns a dict block or None. Never raises (fully wrapped in try/except).
    The block is DISPLAY-ONLY.
    """
    try:
        # --- 1. Trailing 252-day window (fixed basis, RUL-ORTH-6) ----------
        win = full_returns.tail(_EIGEN_BASIS_DAYS)
        n_days_used = len(win)
        if n_days_used < _EIGEN_MIN_DAYS:
            return None

        # --- 2. Coverage filter: keep names with >= 80% non-null ----------
        coverage = win.notna().mean(axis=0)
        keep = coverage[coverage >= _EIGEN_COVERAGE_THRESH].index.tolist()
        if len(keep) < _EIGEN_MIN_NAMES:
            return None
        win = win[keep].copy()
        n_names = len(keep)

        # --- 3. Standardize: demean, divide by per-name std ---------------
        means = win.mean(axis=0)
        stds = win.std(axis=0)
        # Drop names with zero (or near-zero) std to guard singular matrix
        nonzero_std = stds[stds > 1e-12].index.tolist()
        if len(nonzero_std) < _EIGEN_MIN_NAMES:
            return None
        win = win[nonzero_std]
        means = means[nonzero_std]
        stds = stds[nonzero_std]
        n_names = len(nonzero_std)

        X_std = (win - means) / stds  # shape: (T, N)
        # Fill remaining NaN (any that survived coverage filter) with 0
        X_std = X_std.fillna(0.0).to_numpy(dtype=float)  # (T, N)

        # --- 4. SVD on the T x N standardised matrix ----------------------
        # full_matrices=False → U:(T,K), s:(K,), Vt:(K,N) where K=min(T,N)
        _U, s, _Vt = np.linalg.svd(X_std, full_matrices=False)
        lambdas = s ** 2                       # eigenvalues
        sum_lambda = float(np.sum(lambdas))
        if sum_lambda <= 0:
            return None
        shares = lambdas / sum_lambda

        # --- 5. Fields ----------------------------------------------------
        dominant_equity_pc_share = round(float(shares[0]), 4)

        # Effective number of bets (participation ratio)
        sum_lambda_sq = float(np.sum(lambdas ** 2))
        effective_universe_bets_pr = (
            round(float(sum_lambda ** 2 / sum_lambda_sq), 2)
            if sum_lambda_sq > 0 else None
        )

        # idio_dispersion_share: reconstruct top-3 PCs, compute residual
        # share of recent (last-21d) cross-sectional dispersion
        k = min(_EIGEN_TOP_PCS, len(s))
        # Reconstruct top-k component: U[:, :k] * diag(s[:k]) * Vt[:k, :]
        X_top_k = _U[:, :k] * s[:k] @ _Vt[:k, :]  # (T, N)
        X_resid = X_std - X_top_k                   # (T, N)

        recent_rows = min(21, X_std.shape[0])
        total_csd = np.std(X_std[-recent_rows:], axis=1)        # (recent,)
        resid_csd = np.std(X_resid[-recent_rows:], axis=1)      # (recent,)

        mean_total = float(np.mean(total_csd))
        mean_resid = float(np.mean(resid_csd))

        if mean_total > 0:
            idio_dispersion_share = round(
                float(np.clip(mean_resid / mean_total, 0.0, 1.0)), 4
            )
        else:
            idio_dispersion_share = None

        return {
            "basis": "trailing_252d_fixed",
            "n_names_used": n_names,
            "n_days_used": n_days_used,
            "dominant_equity_pc_share": dominant_equity_pc_share,
            "effective_universe_bets_pr": effective_universe_bets_pr,
            "idio_dispersion_share": idio_dispersion_share,
            "sector_pc_loadings": None,
            "note": (
                "sector map not wired (deferred); "
                "display-only — DISP-EIGEN-1 registered, activation DEFERRED "
                "pending DISP-GATE-1 non-stationarity resolution"
            ),
            "display_only": True,
        }
    except Exception:  # noqa: BLE001
        return None


def assess(returns: pd.DataFrame, lookback: int = 252) -> dict | None:
    """`returns` = a wide [dates x names] daily-return panel. Returns the dispersion
    regime + a `gross_mult` for the cross-sectional book, or None when too thin."""
    r = returns.dropna(how="all")
    if len(r) < 60 or r.shape[1] < 20:
        return None
    csd = r.std(axis=1)                                   # cross-sectional dispersion per day
    disp = float(csd.iloc[-21:].mean())                  # recent ~1-month average dispersion
    hist = csd.rolling(21, min_periods=10).mean()
    h = hist.dropna()
    disp_pct = float((h <= h.iloc[-1]).mean()) if len(h) >= 60 else None
    # average pairwise correlation proxy: var(equal-weight return) / mean(single-name var)
    win = r.iloc[-63:]
    ew_var = float(win.mean(axis=1).var())
    mean_var = float(win.var().mean())
    avg_corr = float(np.clip(ew_var / mean_var, 0.0, 1.0)) if mean_var > 0 else None

    if disp_pct is None:
        state = "neutral"
    elif disp_pct >= _HI:
        state = "lean_in"
    elif disp_pct <= _LO:
        state = "lean_out"
    else:
        state = "neutral"
    en, zh = _LABEL[state]
    shadow = _SHADOW_GROSS[state]

    # -----------------------------------------------------------------------
    # Eigen-concentration block (additive, display-only, trailing-252d fixed
    # basis per RUL-ORTH-6). Entire block wrapped in try/except → None.
    # -----------------------------------------------------------------------
    eigen = _compute_eigen_block(r)

    return {"dispersion_pct_pts": round(100 * disp, 2),
            "dispersion_pctile": round(disp_pct, 2) if disp_pct is not None else None,
            "avg_corr": round(avg_corr, 2) if avg_corr is not None else None,
            "state": state,
            # LIVE dial: clamped to display-only (basis: prior). Consumers multiply sizing
            # by this, so it must be 1.0 until a measured selection-IR edge promotes it.
            "gross_mult": _LIVE_CLAMP,
            # SHADOW: the hand-picked tercile magnitude, logged for a future measured promotion.
            "shadow_gross_mult": shadow,
            "passport": {
                "basis": "prior",
                "verdict": "display-only per US_BOARD_MEASUREMENT",
                "validation": {"artifact": "research/US_BOARD_MEASUREMENT.md#study-3",
                               "n": None, "survives": False},
                "note": ("hand-picked terciles, no measured edge on this universe; "
                         "shadow_gross_mult would gross UP into high-VIX stress — clamped "
                         "to 1.0 until a survivorship-clean selection-IR edge is measured"),
            },
            "label": en, "label_zh": zh,
            "eigen": eigen}
