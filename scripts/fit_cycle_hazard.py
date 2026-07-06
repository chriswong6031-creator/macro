"""W4.2 — Discrete-time logistic cycle-hazard fit vs the family-stratified KM bar.

RESEARCH TRACK (masterplan §4 row W4.2, §6.5 decision-gated). Nothing here touches a
page. The deliverable is a fitted model + an honest verdict against the PRE-REGISTERED
gates (PREREGISTRATION.md §2, HZ-{up,dn}-{1m,3m,6m}). Per §6.5 most cells are expected
to ship PRIOR — that outcome is pre-committed and honest, not a failure.

WHAT THIS DOES
  1. Two discrete-time logistic hazards (Allison person-period form), one per
     direction d ∈ {up→peak, down→trough}:
         λ(t) = sigmoid(β₀ + β·x_t)
     Hand-rolled numpy L2 logistic (NO sklearn / statsmodels / lifelines — house rule,
     D5 §1.9). Mirrors the pure-numpy GD pattern of
     scripts/calibrate_baskets._fit_logistic_signed, unconstrained-sign, shrink-to-0.

  2. Walk-forward by DATE blocks (annual, expanding origin, 6-month embargo). Blocks are
     by DATE, never by instrument (all instruments share dates) — D5 §1.6. Continuous
     features standardized by TRAIN-FOLD mean/sd (stored in the artifact for live use).

  3. Pooled-OOS PAV isotonic calibration per horizon (validation.isotonic_calibration).

  4. THE SKILL GATE, per (direction × horizon 1/3/6m) cell:
         OOS Brier(model) < OOS Brier(family-stratified KM), same compounding,
         with a MONTH-BLOCK bootstrap 90% CI on the paired ΔBrier excluding 0.
     Then BH-FDR at q=0.10 across the 6-cell `hazard` family (PREREGISTRATION §9).
     Failing cells ship the KM prior, badged PRIOR.

  5. Regime-feature sub-gate (A14): each of quad_Q2..Q4 / liq_expanding must clear its
     own coefficient CI (month-block bootstrap) or be DROPPED. quad-conditioned skill is
     labeled *revision-optimistic* (P-D5-1 — macro-quad vintages not wired). A lagged-quad
     (+1m) robustness refit is a gate: sensitivity.quad_lag1_delta_brier < 0.005 or drop.

OUTPUTS
  data/hazard/model_<epoch>.json — coefficients, calibration maps, per-cell verdicts,
                                   feature coef table + CIs, sensitivity block, versioned.

The honesty ledger (research/cycle_masterplan/W42_HAZARD_VERDICT.md) and the
PREREGISTRATION.md results column are written/updated by the caller, not this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.validation import isotonic_calibration, apply_calibration  # noqa: E402

# ── Constants (pre-registered; not tuned) ──────────────────────────────────────
BOOT_DRAWS = 800          # house default (engine.grading_stats.BOOT_DRAWS)
BOOT_SEED = 7             # house default (tests pin this)
FIRST_TEST_YEAR = 2010   # D5 §1.6 walk_forward default
EMBARGO_M = 6            # 6-month embargo between train cutoff and test year
L2 = 1.0                 # D5 §1.6: l2=1.0 on non-intercept, non-age-bucket coefs
ITERS = 600
LR = 0.15
HORIZONS = [1, 3, 6]      # months → y1/y3/y6
DIRECTIONS = ["up", "down"]
FDR_Q = 0.10             # BH-FDR q for the `hazard` family (6 cells)
CI_Z_LO, CI_Z_HI = 5.0, 95.0   # 90% CI percentiles
QUAD_LAG_THRESH = 0.005  # sensitivity.quad_lag1_delta_brier gate

# Continuous features standardized by train-fold mean/sd. Age-bucket dummies, family
# dummies, quad dummies, liq dummy, trend_pass are 0/1 and are NOT standardized and NOT
# L2-shrunk (age buckets exempt per D5 §1.6; the intercept is exempt too).
CONT_FEATURES = ["log_age_ratio", "amp_proxy", "pos_osc_s", "osc_slope_s",
                 "mom_score", "rs_63d", "vol_pctile"]
AGE_DUMMIES = ["age_b1", "age_b2", "age_b3", "age_b4", "age_b5"]
BINARY_FEATURES = ["trend_pass"]
REGIME_FEATURES = ["quad_Q2", "quad_Q3", "quad_Q4", "liq_expanding"]
FAMILY_DUMMIES = ["fam_country", "fam_cn"]

# Full ordered design (reference levels dropped: age_b3≈mid is kept — all 5 buckets kept
# because the panel is dominated by b5; instead us_sector & Q1 & liq!=expanding are the
# reference levels). The intercept absorbs the baseline.
DESIGN = AGE_DUMMIES + ["log_age_ratio", "amp_proxy", "pos_osc_s", "osc_slope_s",
                        "trend_pass", "mom_score", "rs_63d", "vol_pctile"] + \
         REGIME_FEATURES + FAMILY_DUMMIES

# Coefficients that are L2-shrunk (D5 §1.6: NOT the intercept, NOT age buckets)
L2_MASK_EXEMPT = set(AGE_DUMMIES)


# ═══════════════════════════════════════════════════════════════════════════════
# Design-matrix construction
# ═══════════════════════════════════════════════════════════════════════════════

def build_design(panel: pd.DataFrame) -> pd.DataFrame:
    """Add the model design columns to a copy of the panel (PIT-honest — every column
    is already causal at month-end t in the W4.1 panel). Returns the augmented frame."""
    d = panel.copy()
    # Age-bucket dummies from the categorical age_bucket (b_unknown → all zero)
    for b in ["b1", "b2", "b3", "b4", "b5"]:
        d[f"age_{b}"] = (d["age_bucket"] == b).astype(float)
    # Scaled oscillator features (D5 x_t: pos/100, osc_slope/10)
    d["pos_osc_s"] = d["pos_osc"] / 100.0
    d["osc_slope_s"] = d["osc_slope"] / 10.0
    # Regime dummies (Q1 & non-expanding-liq are reference levels)
    d["quad_Q2"] = (d["quad"] == "Q2").astype(float)
    d["quad_Q3"] = (d["quad"] == "Q3").astype(float)
    d["quad_Q4"] = (d["quad"] == "Q4").astype(float)
    d["liq_expanding"] = (d["liquidity"] == "expanding").astype(float)
    # Family dummies (us_sector reference)
    d["fam_country"] = (d["family"] == "country").astype(float)
    d["fam_cn"] = (d["family"] == "cn_sector").astype(float)
    # Continuous fill: median-impute the rare NaNs (rs_63d ~4%, others <0.2%)
    for c in ["log_age_ratio", "amp_proxy", "pos_osc_s", "osc_slope_s",
              "mom_score", "rs_63d", "vol_pctile", "trend_pass"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
            med = d[c].median()
            d[c] = d[c].fillna(med if pd.notna(med) else 0.0)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# Hand-rolled numpy L2 logistic  (mirrors calibrate_baskets._fit_logistic_signed)
# ═══════════════════════════════════════════════════════════════════════════════

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic_l2(X: np.ndarray, y: np.ndarray, l2_mask: np.ndarray,
                    l2: float = L2, iters: int = ITERS, lr: float = LR):
    """Pure-numpy L2 logistic by gradient descent. Shrinks toward 0 (not toward a prior),
    L2 applied only where l2_mask is True (non-intercept, non-age-bucket coefs).

    Returns (w, b): coefficient vector and intercept. No sklearn.
    """
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, p = X.shape
    w = np.zeros(p)
    b = 0.0
    pen = l2 * l2_mask.astype(float)
    for _ in range(iters):
        f = _sigmoid(X @ w + b)
        g = f - y
        w -= lr * (X.T @ g / n + pen * w / n)
        b -= lr * float(g.mean())
    return w, float(b)


def _grad_logistic(X, y, w, b, l2_mask, l2=L2):
    """Analytic gradient of mean NLL + L2 penalty — used by the gradient-check test."""
    n = len(y)
    f = _sigmoid(X @ w + b)
    g = f - y
    gw = X.T @ g / n + l2 * l2_mask.astype(float) * w / n
    gb = float(g.mean())
    return gw, gb


# ═══════════════════════════════════════════════════════════════════════════════
# Family-stratified KM predictor  (the skill bar; compounded like the model)
# ═══════════════════════════════════════════════════════════════════════════════

def _km_horizon_table(panel: pd.DataFrame) -> dict:
    """Family-stratified age-only KM prior, estimated on TRAIN rows, ONE rate per horizon.

    The binding null (PREREG §2, D5 §1.7) is the "age-only Kaplan-Meier hazard,
    family-stratified, compounded the same way". The FAIR compounding for a person-period
    row observed at a fixed age bucket is the *empirical horizon-h event rate* for rows in
    that (family, direction, age_bucket) — i.e. the KM survival integrated to horizon h,
    which is exactly the train-fold mean of y_h in that cell. Compounding a single-bucket
    1-month λ geometrically (1-(1-λ)^h) is WRONG here because an instrument ages into other
    buckets over the horizon, so that strawman inflates the KM Brier above the base rate.
    We therefore predict P(y_h=1 | family, direction, bucket) directly from train.

    Returns {(family, direction, bucket, h): rate}. Empty cells fall back to the
    (family, direction, h) pooled rate, then the global (direction, h) rate.
    """
    tbl: dict = {}
    glob: dict = {}
    for h in HORIZONS:
        for direction, gd in panel.groupby("direction"):
            glob[(direction, h)] = float(gd[f"y{h}"].mean()) if len(gd) else 0.0
    for (fam, direction), grp in panel.groupby(["family", "direction"]):
        for h in HORIZONS:
            pooled = float(grp[f"y{h}"].mean()) if len(grp) else glob[(direction, h)]
            tbl[(fam, direction, "_pooled", h)] = pooled
            for bk in ["b1", "b2", "b3", "b4", "b5"]:
                bk_rows = grp[grp["age_bucket"] == bk]
                tbl[(fam, direction, bk, h)] = float(bk_rows[f"y{h}"].mean()) if len(bk_rows) else pooled
    tbl["_global"] = glob
    return tbl


def km_predict(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Fit the family-stratified KM horizon prior on train, predict P(event ≤ h) on test.

    Returns {h: np.array} — the train-fold empirical horizon-h rate for each test row's
    (family, direction, age_bucket) cell. No geometric compounding artifact; this is the
    correctly-specified family-stratified KM bar the model must beat.
    """
    tbl = _km_horizon_table(train)
    glob = tbl["_global"]
    fams = test["family"].to_numpy()
    dirs = test["direction"].to_numpy()
    bks = test["age_bucket"].to_numpy()
    out = {}
    for h in HORIZONS:
        vals = np.empty(len(test))
        for i in range(len(test)):
            key = (fams[i], dirs[i], bks[i], h)
            if key in tbl:
                vals[i] = tbl[key]
            else:
                vals[i] = tbl.get((fams[i], dirs[i], "_pooled", h),
                                  glob.get((dirs[i], h), 0.0))
        out[h] = np.clip(vals, 1e-6, 1 - 1e-6)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Walk-forward  (annual date blocks, expanding origin, 6-month embargo)
# ═══════════════════════════════════════════════════════════════════════════════

def walk_forward(panel_d: pd.DataFrame, direction: str,
                 first_test_year: int = FIRST_TEST_YEAR,
                 embargo_m: int = EMBARGO_M,
                 *, design: list[str] | None = None,
                 cont_features: list[str] | None = None,
                 l2_exempt: set[str] | None = None):
    """Expanding-origin annual walk-forward for one direction.

    For each test year Y ≥ first_test_year: fit on rows with date ≤ Dec(Y-1) − embargo,
    predict rows dated within year Y. Blocks are by DATE, never by instrument.

    Returns a DataFrame of pooled OOS predictions with columns
    [date, id, family, direction, test_year, p1_raw, y1, y3, y6, km1, km3, km6],
    plus the list of per-fold fitted (w, b, mu, sd) for the coefficient artifact.

    The optional ``design`` / ``cont_features`` / ``l2_exempt`` keyword args let a
    caller (e.g. the CPI FT feature-trial runner) fit a DIFFERENT feature list under the
    SAME folds without forking any of this function's math — they default to the module
    globals ``DESIGN`` / ``CONT_FEATURES`` / ``L2_MASK_EXEMPT``, so the W4.2 call
    ``walk_forward(panel, "up")`` is byte-for-byte unchanged.
    """
    design = DESIGN if design is None else design
    cont_features = CONT_FEATURES if cont_features is None else cont_features
    l2_exempt = L2_MASK_EXEMPT if l2_exempt is None else l2_exempt
    sub = panel_d[panel_d["direction"] == direction].copy()
    sub = sub.sort_values("date").reset_index(drop=True)
    years = sorted(sub["date"].dt.year.unique())
    last_year = years[-1]

    oos_rows = []
    fold_fits = []
    for Y in range(first_test_year, last_year + 1):
        train_cutoff = pd.Timestamp(year=Y - 1, month=12, day=31) - pd.DateOffset(months=embargo_m)
        train = sub[sub["date"] <= train_cutoff]
        test = sub[sub["date"].dt.year == Y]
        if len(train) < 400 or len(test) == 0:
            continue

        # Standardize continuous features by TRAIN-fold mean/sd (stored)
        mu = train[cont_features].mean()
        sd = train[cont_features].replace(0, np.nan).std(ddof=0).fillna(1.0)
        sd = sd.replace(0, 1.0)

        def _mat(df):
            m = df[design].copy()
            for c in cont_features:
                m[c] = (df[c] - mu[c]) / sd[c]
            return m[design].to_numpy(dtype=float)

        Xtr, ytr = _mat(train), train["y1"].to_numpy(float)
        Xte = _mat(test)
        l2_mask = np.array([c not in l2_exempt for c in design])
        w, b = fit_logistic_l2(Xtr, ytr, l2_mask)

        p1 = _sigmoid(Xte @ w + b)
        km = km_predict(train, test)

        # ── Out-of-fold calibration (LEAK-FREE): fit PAV isotonic per horizon on the
        # fold's TRAIN in-sample predictions (never the OOS labels), apply to test.
        # This is what makes the skill gate honest — a pooled-OOS isotonic fit on the
        # very rows it scores rescues mis-compounded 3m/6m predictions (a calibration
        # artifact). Per-fold train-fit calibration cannot see the eval labels.
        p1_tr = _sigmoid(Xtr @ w + b)
        cal_te = {}
        for h in HORIZONS:
            p_tr_h = 1.0 - (1.0 - np.clip(p1_tr, 1e-6, 1 - 1e-6)) ** h
            p_te_h = 1.0 - (1.0 - np.clip(p1, 1e-6, 1 - 1e-6)) ** h
            iso = isotonic_calibration(p_tr_h, train[f"y{h}"].to_numpy(float))
            cal_te[h] = apply_calibration(iso, p_te_h) if iso else p_te_h

        fold = pd.DataFrame({
            "date": test["date"].to_numpy(),
            "id": test["id"].to_numpy(),
            "family": test["family"].to_numpy(),
            "direction": direction,
            "test_year": Y,
            "p1_raw": p1,
            "y1": test["y1"].to_numpy(float),
            "y3": test["y3"].to_numpy(float),
            "y6": test["y6"].to_numpy(float),
            "km1": km[1], "km3": km[3], "km6": km[6],
            "p1_caloof": cal_te[1], "p3_caloof": cal_te[3], "p6_caloof": cal_te[6],
        })
        oos_rows.append(fold)
        fold_fits.append({
            "test_year": Y, "n_train": int(len(train)), "n_test": int(len(test)),
            "w": {c: round(float(wi), 5) for c, wi in zip(design, w)},
            "b": round(float(b), 5),
            "mu": {c: round(float(mu[c]), 5) for c in cont_features},
            "sd": {c: round(float(sd[c]), 5) for c in cont_features},
        })

    if not oos_rows:
        return pd.DataFrame(), []
    return pd.concat(oos_rows, ignore_index=True), fold_fits


# ═══════════════════════════════════════════════════════════════════════════════
# Compounding + calibration
# ═══════════════════════════════════════════════════════════════════════════════

def compound_model(oos: pd.DataFrame) -> pd.DataFrame:
    """Compound the 1-month raw hazard to 3m/6m: P(≤h) = 1 - (1 - p1)^h. Same form as KM
    (fair comparison). Adds p1_raw already present; p3_raw, p6_raw."""
    d = oos.copy()
    p1 = np.clip(d["p1_raw"].to_numpy(float), 1e-6, 1 - 1e-6)
    d["p3_raw"] = 1.0 - (1.0 - p1) ** 3
    d["p6_raw"] = 1.0 - (1.0 - p1) ** 6
    return d


def calibrate_pooled(oos: pd.DataFrame) -> dict:
    """Fit PAV isotonic per horizon on the POOLED OOS predictions. Returns
    {h: iso_model}. Applies calibration in place, adding p{h}_cal columns."""
    cal_maps = {}
    for h, praw, ycol in [(1, "p1_raw", "y1"), (3, "p3_raw", "y3"), (6, "p6_raw", "y6")]:
        iso = isotonic_calibration(oos[praw].to_numpy(float), oos[ycol].to_numpy(float))
        cal_maps[h] = iso
        if iso:
            oos[f"p{h}_cal"] = apply_calibration(iso, oos[praw].to_numpy(float))
        else:
            oos[f"p{h}_cal"] = oos[praw].to_numpy(float)
    return cal_maps


# ═══════════════════════════════════════════════════════════════════════════════
# Gate math: paired ΔBrier month-block bootstrap CI + BH-FDR
# ═══════════════════════════════════════════════════════════════════════════════

def _brier(p, y):
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def month_block_brier_gap_ci(dates, brier_km, brier_model, *,
                             draws=BOOT_DRAWS, seed=BOOT_SEED,
                             lo_pct=CI_Z_LO, hi_pct=CI_Z_HI):
    """Month-block bootstrap CI on the paired gap (Brier_KM − Brier_model), so a CI
    entirely ABOVE 0 means the model is strictly better (lower Brier). Resamples whole
    calendar MONTHS with replacement (ruling A2: same-month cross-sectionally correlated
    rows move together). Returns (point, lo, hi) at the requested percentiles.
    """
    months = np.array([pd.Timestamp(x).strftime("%Y-%m") for x in dates])
    uniq = np.unique(months)
    gap_all = brier_km - brier_model
    point = float(np.mean(gap_all))
    if len(uniq) < 2:
        return point, None, None
    by = {m: np.where(months == m)[0] for m in uniq}
    rng = np.random.default_rng(seed)
    gaps = []
    for _ in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[m] for m in pick])
        gaps.append(float(np.mean(gap_all[ridx])))
    lo = float(np.percentile(gaps, lo_pct))
    hi = float(np.percentile(gaps, hi_pct))
    return point, lo, hi


def bh_fdr(pvalues: list[float], q: float = FDR_Q) -> list[bool]:
    """Benjamini-Hochberg. Returns a boolean 'reject null' per input (order preserved).
    A cell whose CI excludes 0 has a one-sided bootstrap p ≈ fraction of draws ≤ 0; here
    we pass those p-values. BH: sort ascending, largest k with p_(k) ≤ (k/m)·q rejects
    all up to k.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = np.argsort(pvalues)
    thresh = None
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= (rank / m) * q:
            thresh = rank
    out = [False] * m
    if thresh is not None:
        for rank, idx in enumerate(order, start=1):
            if rank <= thresh:
                out[idx] = True
    return out


def _boot_pvalue(dates, brier_km, brier_model, *, draws=BOOT_DRAWS, seed=BOOT_SEED):
    """One-sided bootstrap p-value: P(gap ≤ 0) where gap = Brier_KM − Brier_model.
    Small p ⇒ model reliably better."""
    months = np.array([pd.Timestamp(x).strftime("%Y-%m") for x in dates])
    uniq = np.unique(months)
    gap_all = brier_km - brier_model
    if len(uniq) < 2:
        return 1.0
    by = {m: np.where(months == m)[0] for m in uniq}
    rng = np.random.default_rng(seed)
    n_le0 = 0
    for _ in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[m] for m in pick])
        if float(np.mean(gap_all[ridx])) <= 0:
            n_le0 += 1
    return (n_le0 + 1) / (draws + 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Regime coefficient CI + quad-lag robustness
# ═══════════════════════════════════════════════════════════════════════════════

def regime_coef_cis(panel_d: pd.DataFrame, direction: str, *,
                    draws=200, seed=BOOT_SEED) -> dict:
    """Month-block bootstrap 90% CI on each regime-feature coefficient (fit on the FULL
    in-sample panel for this direction, refit per bootstrap resample of months). A regime
    feature whose CI straddles 0 fails its sub-gate and is flagged for DROP (A14).
    Uses a reduced draw count (coefficient CIs refit a logistic per draw — expensive).
    """
    sub = panel_d[panel_d["direction"] == direction].copy()
    months = sub["date"].dt.strftime("%Y-%m").to_numpy()
    uniq = np.unique(months)
    by = {m: np.where(months == m)[0] for m in uniq}
    l2_mask = np.array([c not in L2_MASK_EXEMPT for c in DESIGN])

    # Standardize on full sample (CI is about coefficient stability, not OOS)
    mu = sub[CONT_FEATURES].mean()
    sd = sub[CONT_FEATURES].replace(0, np.nan).std(ddof=0).fillna(1.0).replace(0, 1.0)

    def _mat(df):
        m = df[DESIGN].copy()
        for c in CONT_FEATURES:
            m[c] = (df[c] - mu[c]) / sd[c]
        return m[DESIGN].to_numpy(float)

    rng = np.random.default_rng(seed)
    coefs = {f: [] for f in REGIME_FEATURES}
    for _ in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[m] for m in pick])
        Xb = _mat(sub.iloc[ridx])
        yb = sub.iloc[ridx]["y1"].to_numpy(float)
        w, _ = fit_logistic_l2(Xb, yb, l2_mask, iters=300)
        wd = dict(zip(DESIGN, w))
        for f in REGIME_FEATURES:
            coefs[f].append(wd[f])
    out = {}
    for f in REGIME_FEATURES:
        arr = np.array(coefs[f])
        lo, hi = float(np.percentile(arr, 5)), float(np.percentile(arr, 95))
        out[f] = {
            "coef": round(float(np.mean(arr)), 5),
            "ci90": [round(lo, 5), round(hi, 5)],
            "clears": bool(lo > 0 or hi < 0),   # CI excludes 0
        }
    return out


def quad_lag_sensitivity(panel_d: pd.DataFrame, direction: str) -> float:
    """Lagged-quad (+1m) robustness: refit with quad dummies shifted forward 1 month per
    instrument (a proxy for using last month's known-vintage quad) and measure the pooled
    in-sample Brier delta vs the contemporaneous-quad fit. Large delta ⇒ macro quad is
    doing revision-optimistic work; drop it. Returns |ΔBrier| (in-sample, 1-month).
    """
    sub = panel_d[panel_d["direction"] == direction].sort_values(["id", "date"]).copy()
    l2_mask = np.array([c not in L2_MASK_EXEMPT for c in DESIGN])
    mu = sub[CONT_FEATURES].mean()
    sd = sub[CONT_FEATURES].replace(0, np.nan).std(ddof=0).fillna(1.0).replace(0, 1.0)

    def _mat(df):
        m = df[DESIGN].copy()
        for c in CONT_FEATURES:
            m[c] = (df[c] - mu[c]) / sd[c]
        return m[DESIGN].to_numpy(float)

    y = sub["y1"].to_numpy(float)
    X0 = _mat(sub)
    w0, b0 = fit_logistic_l2(X0, y, l2_mask)
    br0 = float(np.mean(_brier(_sigmoid(X0 @ w0 + b0), y)))

    lag = sub.copy()
    for q in ["quad_Q2", "quad_Q3", "quad_Q4", "liq_expanding"]:
        lag[q] = lag.groupby("id")[q].shift(1).fillna(0.0)
    X1 = _mat(lag)
    w1, b1 = fit_logistic_l2(X1, y, l2_mask)
    br1 = float(np.mean(_brier(_sigmoid(X1 @ w1 + b1), y)))
    return abs(br1 - br0)


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def run_fit(panel: pd.DataFrame, epoch: str) -> dict:
    panel_d = build_design(panel)
    panel_d["date"] = pd.to_datetime(panel_d["date"])

    ledger = {"up": {}, "down": {}}
    coef_artifact = {"up": {}, "down": {}}
    calib_artifact = {"up": {}, "down": {}}
    sensitivity = {"up": {}, "down": {}}
    cell_pvals = []       # (direction, h, pvalue)

    for direction in DIRECTIONS:
        oos, fold_fits = walk_forward(panel_d, direction)
        if oos.empty:
            for h in HORIZONS:
                ledger[direction][f"{h}m"] = {"pass": False, "reason": "no_oos"}
            continue
        oos = compound_model(oos)
        cal_maps = calibrate_pooled(oos)
        calib_artifact[direction] = {
            str(h): (cal_maps[h] if cal_maps[h] else {}) for h in HORIZONS
        }

        # Final-fold coefficients (the shipped live model = last expanding fold)
        coef_artifact[direction] = fold_fits[-1] if fold_fits else {}

        # Skill gate per horizon: LEAK-FREE out-of-fold calibrated model vs family KM.
        # (p{h}_caloof is calibrated with a per-fold isotonic fit on TRAIN only — the
        # pooled-OOS p{h}_cal is kept ONLY as the shipped live-calibration map, never for
        # the gate. Scoring the gate on p{h}_cal would leak the eval labels through the
        # isotonic and manufacture PASSes; verified this rescues mis-compounded 3m/6m.)
        dates = oos["date"].to_numpy()
        years = pd.to_datetime(oos["date"]).dt.year.to_numpy()
        for h in HORIZONS:
            ycol = f"y{h}"
            pmodel = oos[f"p{h}_caloof"].to_numpy(float)
            pkm = oos[f"km{h}"].to_numpy(float)
            y = oos[ycol].to_numpy(float)
            br_model = float(np.mean(_brier(pmodel, y)))
            br_km = float(np.mean(_brier(pkm, y)))
            gap_arr = _brier(pkm, y) - _brier(pmodel, y)     # >0 = model better
            gap, lo, hi = month_block_brier_gap_ci(dates, _brier(pkm, y), _brier(pmodel, y))
            pval = _boot_pvalue(dates, _brier(pkm, y), _brier(pmodel, y))
            ci_excludes_zero = (lo is not None and lo > 0)
            # Per-year sign stability of the gap (OOS sign-holding, KG-5 spirit)
            yr_means = pd.Series(gap_arr).groupby(years).mean()
            n_pos, n_yr = int((yr_means > 0).sum()), int(len(yr_means))
            cell_pvals.append((direction, h, pval))
            ledger[direction][f"{h}m"] = {
                "brier_model": round(br_model, 5),
                "brier_km": round(br_km, 5),
                "skill_vs_km": round(gap, 5),          # Brier_KM − Brier_model (>0 = model better)
                "ci90": [round(lo, 5) if lo is not None else None,
                         round(hi, 5) if hi is not None else None],
                "boot_pvalue": round(pval, 4),
                "ci_excludes_zero": bool(ci_excludes_zero),
                "years_gap_positive": [n_pos, n_yr],
                "n_oos": int(len(oos)),
                "n_months": int(len(np.unique([pd.Timestamp(x).strftime('%Y-%m') for x in dates]))),
                # 'pass' filled after BH-FDR below
            }

        # Regime coefficient sub-gate (A14)
        sensitivity[direction]["regime_coef_ci"] = regime_coef_cis(panel_d, direction)
        # Quad-lag robustness
        qd = quad_lag_sensitivity(panel_d, direction)
        sensitivity[direction]["quad_lag1_delta_brier"] = round(qd, 5)
        sensitivity[direction]["quad_dropped"] = bool(qd >= QUAD_LAG_THRESH)
        # Which regime features clear their own CI
        dropped = [f for f, v in sensitivity[direction]["regime_coef_ci"].items()
                   if not v["clears"]]
        sensitivity[direction]["regime_features_dropped_for_ci"] = dropped

    # ── BH-FDR across the 6 hazard cells ────────────────────────────────────────
    pvals = [p for (_, _, p) in cell_pvals]
    rejects = bh_fdr(pvals, q=FDR_Q)
    for (direction, h, _), rej in zip(cell_pvals, rejects):
        cell = ledger[direction][f"{h}m"]
        # A cell PASSES only if its CI excludes 0 AND it survives BH-FDR
        cell["survives_bh_fdr"] = bool(rej)
        cell["pass"] = bool(cell.get("ci_excludes_zero", False) and rej)
        cell["verdict"] = "PASS" if cell["pass"] else "PRIOR"

    n_pass = sum(1 for d in DIRECTIONS for h in HORIZONS
                 if ledger[d][f"{h}m"].get("pass"))

    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "turn_def_version": epoch,
        "model": "discrete_time_logistic_hazard_l2_numpy",
        "doc": (
            "W4.2 hazard fit vs family-stratified KM. Per-cell PASS = OOS Brier(model) < "
            "Brier(KM) AND month-block-bootstrap 90% CI on paired ΔBrier excludes 0 AND "
            "survives BH-FDR (q=0.10) across the 6-cell hazard family. Failing cells ship "
            "the KM PRIOR. Quad-conditioned skill is REVISION-OPTIMISTIC (P-D5-1: macro "
            "quad vintages not wired)."
        ),
        "config": {
            "first_test_year": FIRST_TEST_YEAR, "embargo_m": EMBARGO_M,
            "l2": L2, "iters": ITERS, "lr": LR, "boot_draws": BOOT_DRAWS,
            "boot_seed": BOOT_SEED, "fdr_q": FDR_Q, "design": DESIGN,
            "features_dropped_for_absence": ["breadth_div", "breadth_missing", "state_score"],
            "amp_feature": "amp_proxy (shipped W2.5 form; D5 amp_ratio ideal not in panel)",
        },
        "n_cells_pass": int(n_pass),
        "ledger": ledger,
        "coefficients": coef_artifact,
        "calibration": calib_artifact,
        "sensitivity": sensitivity,
        "revision_optimistic": True,
        "revision_optimistic_note": (
            "quad/liquidity regime features are macro-derived with no PIT vintage backfill "
            "(P-D5-1). Any cell whose skill leans on quad coefficients is revision-optimistic "
            "until D6 vintages land."
        ),
    }


def main():
    ap = argparse.ArgumentParser(description="W4.2 cycle-hazard fit")
    ap.add_argument("--panel", default=None, help="panel parquet (auto-detects newest price_ epoch)")
    ap.add_argument("--out-dir", default=str(_REPO / "data/hazard"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if args.panel:
        panel_path = Path(args.panel)
    else:
        cands = sorted(out_dir.glob("panel_price_*.parquet"))
        if not cands:
            cands = sorted(out_dir.glob("panel_*.parquet"))
        if not cands:
            raise SystemExit("no panel parquet found in " + str(out_dir))
        panel_path = cands[-1]
    epoch = panel_path.stem.replace("panel_", "")
    print(f"Fitting on {panel_path.name} (epoch {epoch})")
    panel = pd.read_parquet(panel_path)

    result = run_fit(panel, epoch)
    out_path = out_dir / f"model_{epoch}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Model written: {out_path}")
    print(f"CELLS PASS: {result['n_cells_pass']} / 6")
    for d in DIRECTIONS:
        for h in HORIZONS:
            c = result["ledger"][d].get(f"{h}m", {})
            print(f"  {d}/{h}m: {c.get('verdict','?')}  "
                  f"skill_vs_km={c.get('skill_vs_km')}  ci90={c.get('ci90')}")


if __name__ == "__main__":
    main()
