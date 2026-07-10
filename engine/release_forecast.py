"""Macro Release Intelligence — pre-print projection models for CPI, NFP, and Claims.

LEAF · DISPLAY-ONLY. Imports nothing from the mechanical scoring core
(conditions/regime/run/inputs/equity_alloc) and nothing in the scoring path
imports this module. Every public function returns plain data and NEVER raises
into the build — all IO failures degrade gracefully (missing legs → leg dropped,
recorded in provenance).

SPECIFICATION: research/release_forecast/PREREG_V1.md (frozen 2026-07-07) for V1.
                research/release_forecast/PREREG_V2.md (frozen 2026-07-07) for V2 additions
                (shelter leg, component contributions, confidence_v2).
Anti-mining: two spec attempts per CPI target, both frozen before any results were observed.

PIT LAW: a feature value is usable at decision date D only if its ALFRED
realtime_start <= D. The `knowable_series` function enforces this filter. Non-
vintaged series (AWHMAN, GASREGW, withheld_taxes) are declared per-leg in
provenance as revision_optimistic_legs or unrevised_legs.

Model: Ridge regression (lambda=1.0, closed-form numpy), z-scored features,
expanding-window walk-forward (min 60 obs before first prediction, refit each step).

display_only=True, authority=False on all outputs — never conditions scoring.

numpy / pandas only. No sklearn, statsmodels, or scipy.stats (house law).

Module split (PR-F): CPI feature builders live in engine/release_components_cpi.py;
NFP+Claims builders live in engine/release_components_nfp.py. This file keeps the
public API (project_release, run_walk_forward_full, helpers) and re-exports
build_cpi_features / build_nfp_features for backward compat.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (frozen per PREREG_V1.md)
# ---------------------------------------------------------------------------
RIDGE_LAMBDA = 1.0
MIN_TRAIN_OBS = 60
MIN_QUANTILE_OBS = 24
INLINE_BAND_SIGMA = 0.35
COVID_MONTHS = {(2020, m) for m in range(3, 7)}  # 2020-03 to 2020-06

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_vintages(root: str | Path) -> pd.DataFrame:
    """Load ALFRED vintage parquet from data/fred_vintage/vintages.parquet.

    Returns a DataFrame with columns: series, period, value, realtime_start, realtime_end.
    All datetime columns are datetime64 dtype.
    """
    path = Path(root) / "data" / "fred_vintage" / "vintages.parquet"
    df = pd.read_parquet(path)
    # ensure datetime types
    for col in ("period", "realtime_start", "realtime_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def knowable_series(
    vintages: pd.DataFrame,
    series: str,
    asof: date | pd.Timestamp,
) -> pd.DataFrame:
    """Return initial-print rows for `series` with realtime_start <= asof.

    Returns a DataFrame sorted by period with columns: period, value, realtime_start.
    For each period, only the row with the EARLIEST realtime_start is kept (the
    initial print). This is the PIT-safe "what was first published and knowable at asof."
    """
    asof_ts = pd.Timestamp(asof)
    sub = vintages[
        (vintages["series"] == series) & (vintages["realtime_start"] <= asof_ts)
    ].copy()
    if sub.empty:
        return pd.DataFrame(columns=["period", "value", "realtime_start"])
    # initial print = first realtime_start for each period
    initial = (
        sub.sort_values("realtime_start")
        .groupby("period", as_index=False)
        .first()[["period", "value", "realtime_start"]]
        .sort_values("period")
        .reset_index(drop=True)
    )
    return initial


# ---------------------------------------------------------------------------
# Ridge regression helpers (numpy only)
# ---------------------------------------------------------------------------

def _ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    """Closed-form Ridge: beta = (X'X + lam*I)^{-1} X'y.

    X: (n, p) design matrix (already z-scored, bias column appended by caller).
    y: (n,) target.
    Returns beta: (p,).
    """
    n, p = X.shape
    XtX = X.T @ X
    XtX_reg = XtX + lam * np.eye(p)
    Xty = X.T @ y
    try:
        beta = np.linalg.solve(XtX_reg, Xty)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(XtX_reg, Xty, rcond=None)[0]
    return beta


def _zscore_params(X_train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, std) for each column in X_train (expanding-window normalization)."""
    mean = np.nanmean(X_train, axis=0)
    std = np.nanstd(X_train, axis=0, ddof=1)
    std[std == 0] = 1.0  # constant features: divide by 1 (feature effectively zeroed by z-score)
    return mean, std


def _zscore_apply(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (X - mean) / std


def _ridge_predict(X_train: np.ndarray, y_train: np.ndarray, X_pred: np.ndarray) -> float:
    """Fit ridge on training data, predict single test row. Returns scalar."""
    mean, std = _zscore_params(X_train)
    Xz_train = _zscore_apply(X_train, mean, std)
    # append bias column
    ones_tr = np.ones((Xz_train.shape[0], 1))
    X_aug_tr = np.hstack([Xz_train, ones_tr])
    beta = _ridge_fit(X_aug_tr, y_train)
    # predict
    xz_pred = _zscore_apply(X_pred.reshape(1, -1), mean, std)
    x_aug_pred = np.hstack([xz_pred, np.ones((1, 1))])
    return float(np.dot(x_aug_pred.ravel(), beta.ravel()))


def _ridge_predict_with_components(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_pred: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Fit ridge, predict, and return (point, beta_features, z_features).

    beta_features: coefficients excluding bias (shape: n_features).
    z_features: z-scored prediction features (shape: n_features).
    These are needed for computing component contributions: contrib_pp[i] = beta[i] * z[i].
    """
    mean, std = _zscore_params(X_train)
    Xz_train = _zscore_apply(X_train, mean, std)
    ones_tr = np.ones((Xz_train.shape[0], 1))
    X_aug_tr = np.hstack([Xz_train, ones_tr])
    beta = _ridge_fit(X_aug_tr, y_train)
    xz_pred = _zscore_apply(X_pred.reshape(1, -1), mean, std)
    x_aug_pred = np.hstack([xz_pred, np.ones((1, 1))])
    point = float(np.dot(x_aug_pred.ravel(), beta.ravel()))
    # beta[:-1] are feature coefficients; beta[-1] is bias
    beta_features = beta[:-1]
    z_features = xz_pred.ravel()
    return point, beta_features, z_features


# ---------------------------------------------------------------------------
# Wilson CI (reuse pattern from engine/foresight_grader.py)
# ---------------------------------------------------------------------------

def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score 95% CI for a hit-rate k/n."""
    if not n:
        return None
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


# ---------------------------------------------------------------------------
# Feature builders
# ---------------------------------------------------------------------------

def _mom_from_levels(levels: pd.Series) -> pd.Series:
    """Compute MoM % change from a Series of index levels."""
    return levels.pct_change() * 100.0


def _initial_print_series(
    vintages: pd.DataFrame, series: str, asof: date
) -> pd.DataFrame:
    """Wrapper: knowable initial prints for series at asof."""
    return knowable_series(vintages, series, asof)


def _last_n_mom_lags(
    vintages: pd.DataFrame, series: str, asof: date, n: int = 3
) -> list[float | None]:
    """Return the last n MoM % changes from initial-print series knowable at asof.

    Returns [lag1, lag2, lag3] where lag1 = most recent, lag3 = oldest.
    None for missing values.
    """
    df = knowable_series(vintages, series, asof)
    if len(df) < 2:
        return [None] * n
    levels = df.set_index("period")["value"]
    mom = levels.pct_change() * 100.0
    mom = mom.dropna()
    result = []
    for i in range(1, n + 1):
        if len(mom) >= i:
            result.append(float(mom.iloc[-i]))
        else:
            result.append(None)
    return result


def _last_n_diff_lags(
    vintages: pd.DataFrame, series: str, asof: date, n: int = 3
) -> list[float | None]:
    """Return the last n first-differences (level changes) from initial-print series.

    Used for PAYEMS where the target is thousands-of-jobs change.
    """
    df = knowable_series(vintages, series, asof)
    if len(df) < 2:
        return [None] * n
    levels = df.set_index("period")["value"]
    diff = levels.diff().dropna()
    result = []
    for i in range(1, n + 1):
        if len(diff) >= i:
            result.append(float(diff.iloc[-i]))
        else:
            result.append(None)
    return result


def _survey_week_claims(
    vintages: pd.DataFrame, series: str, asof: date, ref_month: date
) -> float | None:
    """Average initial-print weekly claims over the survey reference week for ref_month.

    Survey reference week = the week (starting Saturday per ICSA/CCSA period convention)
    that CONTAINS the 12th of ref_month.
    """
    df = knowable_series(vintages, series, asof)
    if df.empty:
        return None

    # Find the week containing the 12th of ref_month
    target_12 = pd.Timestamp(ref_month.year, ref_month.month, 12)
    # ICSA/CCSA period = Saturday of the reference week; week spans Sat..Fri
    # The 12th falls in week starting on Saturday <= 12th AND ending on Friday >= 12th
    df["period"] = pd.to_datetime(df["period"])
    # period is Saturday; week is [period, period+6]
    df["week_end"] = df["period"] + pd.Timedelta(days=6)
    mask = (df["period"] <= target_12) & (df["week_end"] >= target_12)
    week_rows = df[mask]
    if week_rows.empty:
        return None
    return float(week_rows["value"].mean())


def build_cpi_features(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    release_type: str = "cpi_headline",
    ref_month: date | pd.Timestamp | None = None,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for CPI prediction at decision date asof.

    Delegates to engine.release_components_cpi — kept here for backward compat.
    V2: adds shelter_nowcast leg (PREREG_V2.md §2, §3).
    release_type: 'cpi_headline' or 'cpi_core'.
    ref_month: the CPI reference month M the target print covers (PREREG_V1.md §2.3
        feature 7 anchors gasoline_mom on M, not on asof's calendar month).
    Returns (features_dict, provenance_dict).
    """
    from engine.release_components_cpi import build_cpi_features as _build_cpi
    return _build_cpi(
        asof, vintages, root,
        release_type=release_type,
        ref_month=ref_month,
        knowable_series_fn=knowable_series,
        last_n_mom_lags_fn=_last_n_mom_lags,
    )


def build_nfp_features(
    asof: date,
    ref_month: date,
    vintages: pd.DataFrame,
    root: Path,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for NFP prediction at decision date asof for ref_month.

    Delegates to engine.release_components_nfp — kept here for backward compat.
    Returns (features_dict, provenance_dict).
    """
    from engine.release_components_nfp import build_nfp_features as _build_nfp
    return _build_nfp(
        asof, ref_month, vintages, root,
        knowable_series_fn=knowable_series,
        survey_week_claims_fn=_survey_week_claims,
    )


# ---------------------------------------------------------------------------
# inputs_hash helper (v2 schema)
# ---------------------------------------------------------------------------

def compute_inputs_hash(features: dict[str, float | None]) -> str:
    """Return sha256 hex of sorted (feature_name, value) pairs actually used.

    'Actually used' = all pairs where value is not None.
    Canonical form: JSON array of [name, value] pairs, sorted by name,
    with float values rounded to 10 decimal places to avoid float repr variance.
    """
    used = sorted(
        (k, round(v, 10) if v is not None else None)
        for k, v in features.items()
        if v is not None
    )
    canonical = json.dumps(used, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_release_id(release: str, period: str, sequence: str = "first") -> str:
    """Build release_id: '<RELEASE_UPPER>:<period>:<sequence>'.

    release: 'cpi_headline' | 'cpi_core' | 'nfp' | 'claims'
    period: 'YYYY-MM' for monthly releases, 'YYYY-MM-DD' for weekly claims
    sequence: always 'first' for v1
    Examples: 'CPI:2026-06:first', 'NFP:2026-07:first', 'CLAIMS:2026-07-11:first'
    """
    label_map = {
        "cpi_headline":    "CPI",
        "cpi_core":        "CPI_CORE",
        "nfp":             "NFP",
        "claims":          "CLAIMS",
        "ahe":             "AHE",
        "awh":             "AWH",
        # MRI-R23: new targets (Round 2a)
        "pce_headline":    "PCE",
        "pce_core":        "PCE_CORE",
        "ppi_finaldemand": "PPI",
        "retail_sales":    "RETAIL",
    }
    label = label_map.get(release, release.upper())
    return f"{label}:{period}:{sequence}"


def make_prediction_id(release_id: str, asof_night: str) -> str:
    """Build prediction_id: '<release_id>:<asof_night>:v1'."""
    return f"{release_id}:{asof_night}:v1"


# ---------------------------------------------------------------------------
# Walk-forward engine
# ---------------------------------------------------------------------------

def _build_matrix(
    rows: list[dict[str, float | None]],
    feature_names: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Convert list-of-feature-dicts to (X, valid_mask) where valid_mask[j]=True
    means feature j has at least one non-null training observation.

    Rows with ANY null in a used feature are dropped from training.
    NaN is used as sentinel for missing values. Columns that are entirely NaN
    in training rows are excluded from the model.
    """
    n = len(rows)
    p = len(feature_names)
    X = np.full((n, p), np.nan)
    for i, row in enumerate(rows):
        for j, fn in enumerate(feature_names):
            v = row.get(fn)
            if v is not None and not np.isnan(v):
                X[i, j] = v
    return X


def _drop_nan_cols(X_train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Remove columns where ANY training row has NaN. Returns (X_clean, col_mask)."""
    # A feature is usable if ALL training rows have a value
    col_mask = ~np.any(np.isnan(X_train), axis=0)
    return X_train[:, col_mask], col_mask


def _walk_forward(
    records: list[dict],
    feature_names: list[str],
    target_key: str,
    min_obs: int = MIN_TRAIN_OBS,
) -> list[dict]:
    """Run expanding-window walk-forward ridge regression.

    records: list of dicts, each with feature_names keys + target_key, sorted by time.
    Returns list of result dicts with keys: idx, predicted, actual, baseline_naive,
    baseline_trailing3m, baseline_ar3, n_train, n_features_used, input_completeness.
    """
    results = []
    for i in range(len(records)):
        if i < min_obs:
            continue
        train_recs = records[:i]
        pred_rec = records[i]
        actual = pred_rec.get(target_key)
        if actual is None or np.isnan(actual):
            continue

        # Build feature matrices
        X_all = _build_matrix(train_recs, feature_names)
        y_all = np.array([r.get(target_key, np.nan) for r in train_recs], dtype=float)

        # Drop rows where target is NaN
        valid_target = ~np.isnan(y_all)
        X_all = X_all[valid_target]
        y_all = y_all[valid_target]

        if len(y_all) < min_obs:
            continue

        # Compute input completeness: fraction of possible features present in prediction row
        pred_features = np.array(
            [pred_rec.get(fn) if pred_rec.get(fn) is not None else np.nan for fn in feature_names],
            dtype=float,
        )
        n_possible = len(feature_names)
        n_present = int(np.sum(~np.isnan(pred_features)))
        input_completeness = n_present / n_possible if n_possible > 0 else 0.0

        # Select columns available in the prediction row
        pred_avail_mask = ~np.isnan(pred_features)
        # For the selected columns, do complete-case training: drop rows with NaN in selected cols
        if pred_avail_mask.any():
            X_sel = X_all[:, pred_avail_mask]
            row_complete = ~np.any(np.isnan(X_sel), axis=1)
            X_clean = X_sel[row_complete]
            y_clean = y_all[row_complete]
            x_pred = pred_features[pred_avail_mask]
            n_features_used = int(pred_avail_mask.sum())
        else:
            X_clean = np.empty((0, 0))
            y_clean = np.empty(0)
            x_pred = np.empty(0)
            n_features_used = 0

        # Baselines
        y_series = y_all.copy()
        naive = float(y_series[-1]) if len(y_series) > 0 else np.nan
        trailing_3m = float(np.mean(y_series[-3:])) if len(y_series) >= 3 else (float(np.mean(y_series)) if len(y_series) > 0 else np.nan)

        # AR3 baseline: ridge on own lags only (first 3 features = own lags by construction)
        ar3_lags_names = set(feature_names[:3])
        ar3_pred_avail = np.array([
            (fn in ar3_lags_names) and not np.isnan(pred_features[j])
            for j, fn in enumerate(feature_names)
        ], dtype=bool)
        if ar3_pred_avail.any():
            X_ar3_sel = X_all[:, ar3_pred_avail]
            ar3_row_complete = ~np.any(np.isnan(X_ar3_sel), axis=1)
            X_ar3 = X_ar3_sel[ar3_row_complete]
            y_ar3 = y_all[ar3_row_complete]
            x_ar3_pred = pred_features[ar3_pred_avail]
            if X_ar3.shape[1] > 0 and len(y_ar3) >= min_obs:
                ar3_pred = _ridge_predict(X_ar3, y_ar3, x_ar3_pred)
            else:
                ar3_pred = naive
        else:
            ar3_pred = naive

        # Ridge main model (complete-case training)
        if n_features_used > 0 and len(y_clean) >= min_obs:
            ridge_pred = _ridge_predict(X_clean, y_clean, x_pred)
        else:
            ridge_pred = naive

        results.append({
            "idx": i,
            "result_pos": len(results),  # ordinal position in results list (0-based)
            "predicted": ridge_pred,
            "actual": float(actual),
            "baseline_naive": naive,
            "baseline_trailing3m": trailing_3m,
            "baseline_ar3": ar3_pred,
            "n_train": len(y_clean) if n_features_used > 0 else len(y_all),
            "n_features_used": n_features_used,
            "input_completeness": input_completeness,
        })

    return results


def _compute_quantiles_volscaled(
    residuals: np.ndarray,
    point: float,
    min_obs: int = MIN_QUANTILE_OBS,
    vol_window: int = 24,
    min_sigma_obs: int = 12,
) -> dict:
    """Vol-scaled residual quantile bands (MRI-R30, PREREG_INTERVAL_RECAL_V1.md).

    Residuals are standardized by a trailing realized-error sigma_t at each walk-forward
    step, quantiles taken on standardized residuals, then re-scaled by sigma_now.
    Points are completely unchanged — only the bands move.

    Parameters
    ----------
    residuals : np.ndarray
        Walk-forward residuals in chronological order (actual - predicted).
        Each element residuals[i] corresponds to walk-forward step i.
    point : float
        The model's point prediction (unchanged by this function).
    min_obs : int
        Minimum standardized residuals required to compute quantiles.
        Below this threshold, falls back to full-history unscaled bands.
    vol_window : int
        Rolling window W for trailing sigma estimation. Frozen at 24 (spec).
    min_sigma_obs : int
        Minimum trailing residuals required to estimate sigma_t for step i.
        If fewer are available, that step is excluded from standardized accumulation.

    Returns
    -------
    dict with keys p10, p25, p50, p75, p90 (or all None if insufficient data).

    Fallback
    --------
    Returns full-history unscaled quantiles (pre-recal behavior) when:
      - Not enough standardized residuals (< min_obs), or
      - sigma_now is 0 or cannot be computed (degenerate).
    """
    n = len(residuals)
    if n < min_obs:
        return {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    # Minimum sigma threshold: below this, sigma is treated as degenerate and the
    # step is excluded (or falls back for sigma_now). Using a small epsilon rather
    # than exact-zero to handle floating-point precision (e.g. np.std of constant
    # array gives ~7e-18 not exactly 0 due to ddof=1 rounding).
    _SIGMA_EPS = 1e-10

    # Build standardized residuals: each r_std_i = r_i / sigma_i
    # sigma_i = std of trailing residuals BEFORE step i (no lookahead)
    r_std_list: list[float] = []
    for i in range(n):
        trailing = residuals[max(0, i - vol_window): i]
        if len(trailing) < min_sigma_obs:
            # Not enough history to estimate sigma at this step — skip
            continue
        sigma_i = float(np.std(trailing, ddof=1))
        if sigma_i < _SIGMA_EPS:
            # Degenerate (constant or near-constant history): skip this step
            continue
        r_std_list.append(float(residuals[i]) / sigma_i)

    r_std = np.array(r_std_list)

    # Compute sigma_now from the last vol_window residuals
    trailing_now = residuals[max(0, n - vol_window):]
    if len(trailing_now) < min_sigma_obs:
        # Not enough trailing residuals for sigma_now — fall back
        return _compute_quantiles_unscaled(residuals, point, min_obs)
    sigma_now = float(np.std(trailing_now, ddof=1))
    if sigma_now < _SIGMA_EPS:
        # Degenerate sigma_now (constant recent history) — fall back to unscaled
        return _compute_quantiles_unscaled(residuals, point, min_obs)

    if len(r_std) < min_obs:
        # Not enough standardized residuals — fall back
        return _compute_quantiles_unscaled(residuals, point, min_obs)

    qs = np.quantile(r_std, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "p10": round(point + float(qs[0]) * sigma_now, 4),
        "p25": round(point + float(qs[1]) * sigma_now, 4),
        "p50": round(point + float(qs[2]) * sigma_now, 4),
        "p75": round(point + float(qs[3]) * sigma_now, 4),
        "p90": round(point + float(qs[4]) * sigma_now, 4),
    }


def _compute_quantiles_unscaled(
    residuals: np.ndarray,
    point: float,
    min_obs: int = MIN_QUANTILE_OBS,
) -> dict:
    """Full-history unscaled quantile bands — pre-recal fallback behavior.

    Preserved for backward compatibility and as the explicit fallback path when
    vol-scaled bands cannot be computed (insufficient history, sigma_now == 0).
    """
    if len(residuals) < min_obs:
        return {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
    qs = np.quantile(residuals, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "p10": round(point + float(qs[0]), 4),
        "p25": round(point + float(qs[1]), 4),
        "p50": round(point + float(qs[2]), 4),
        "p75": round(point + float(qs[3]), 4),
        "p90": round(point + float(qs[4]), 4),
    }


def _compute_quantiles(residuals: np.ndarray, point: float, min_obs: int = MIN_QUANTILE_OBS) -> dict:
    """Return p10/p25/p50/p75/p90 intervals centered on point from residual history.

    MRI-R30: delegates to _compute_quantiles_volscaled (vol-scaled residual quantiles).
    The old unscaled behavior is preserved in _compute_quantiles_unscaled for fallback
    and backward-compatibility in tests.
    """
    return _compute_quantiles_volscaled(residuals, point, min_obs=min_obs)


# ---------------------------------------------------------------------------
# Main projection API
# ---------------------------------------------------------------------------

def project_release(
    release: str,
    asof: date,
    root: str | Path,
    ref_month: date | None = None,
    *,
    period: str | None = None,
    release_date: date | None = None,
) -> dict:
    """Generate a point-in-time projection for a macro release.

    Parameters
    ----------
    release : str
        One of 'cpi_headline', 'cpi_core', 'nfp', 'claims', 'ahe', 'awh'.
        'ahe' and 'awh' are PR-H additions (AHE MoM % and avg weekly hours level).
    asof : date
        Decision date (the day before the target release is published).
    root : str | Path
        Repository root (data/ subdirectories are read from here).
    ref_month : date | None
        Reference month the upcoming print covers (CPI only — anchors the
        gasoline_mom leg per PREREG_V1.md §2.3). None derives it from the last
        knowable initial print. Ignored for NFP, which derives its own.
    period : str | None
        'YYYY-MM' (monthly) or 'YYYY-MM-DD' (weekly claims) for schema v2 IDs.
        If None, derived internally where possible.
    release_date : date | None
        The scheduled release date; used to compute horizon_days for schema v2.
        If None, horizon_days is omitted.

    Returns
    -------
    dict matching the release_forecast.v2 projection block schema.
    display_only=True, authority=False.
    """
    root = Path(root)
    vintages = load_vintages(root)

    if release in ("cpi_headline", "cpi_core"):
        result = _project_cpi(release, asof, vintages, root, ref_month=ref_month)
    elif release == "nfp":
        result = _project_nfp(asof, vintages, root)
    elif release == "claims":
        from engine.release_components_nfp import project_claims
        result = project_claims(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=MIN_QUANTILE_OBS,
        )
    elif release == "ahe":
        # PR-H: AHE MoM % target
        from engine.release_components_nfp import project_ahe
        result = project_ahe(
            asof, vintages,
            knowable_series_fn=knowable_series,
            survey_week_claims_fn=_survey_week_claims,
            ridge_predict_fn=_ridge_predict,
            walk_forward_fn=_walk_forward,
            build_matrix_fn=_build_matrix,
            compute_quantiles_fn=_compute_quantiles,
            wilson_fn=_wilson,
            min_train_obs=MIN_TRAIN_OBS,
            min_quantile_obs=MIN_QUANTILE_OBS,
            inline_band_sigma=INLINE_BAND_SIGMA,
        )
    elif release == "awh":
        # PR-H: avg weekly hours level (persistence-only)
        from engine.release_components_nfp import project_awh
        result = project_awh(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=MIN_QUANTILE_OBS,
        )
    elif release == "pce_headline":
        # MRI-R23: PCE headline (PCEPI MoM SA) — engine/release_targets_v11.py
        from engine.release_targets_v11 import project_pce_headline
        result = project_pce_headline(asof, root, ref_month=ref_month)
    elif release == "pce_core":
        # MRI-R23: PCE core (PCEPILFE MoM SA) — engine/release_targets_v11.py
        from engine.release_targets_v11 import project_pce_core
        result = project_pce_core(asof, root, ref_month=ref_month)
    elif release == "ppi_finaldemand":
        # MRI-R23: PPI Final Demand (PPIFIS MoM SA) — engine/release_targets_v11.py
        from engine.release_targets_v11 import project_ppi_finaldemand
        result = project_ppi_finaldemand(asof, root, ref_month=ref_month)
    elif release == "retail_sales":
        # MRI-R23: retail_sales scaffold — no_data until RSAFS on disk
        from engine.release_targets_v11 import project_retail_sales
        result = project_retail_sales(asof, root, ref_month=ref_month)
    else:
        raise ValueError(
            f"Unknown release type: {release!r}. "
            "Use 'cpi_headline', 'cpi_core', 'nfp', 'claims', 'ahe', 'awh', "
            "'pce_headline', 'pce_core', 'ppi_finaldemand', or 'retail_sales'."
        )

    # Attach schema v2 fields
    result["schema"] = 2
    _period = period
    if _period is None:
        # Best-effort derivation for ID construction
        if release in ("cpi_headline", "cpi_core"):
            own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
            try:
                ip = knowable_series(vintages, own_series, asof)
                if not ip.empty:
                    last_p = pd.Timestamp(ip["period"].iloc[-1])
                    next_p = (last_p.to_period("M") + 1).to_timestamp()
                    _period = f"{next_p.year}-{next_p.month:02d}"
            except Exception:
                pass
        elif release == "nfp":
            _period = f"{asof.year}-{asof.month:02d}"
        elif release in ("pce_headline", "pce_core", "ppi_finaldemand"):
            # Best-effort: derive from last knowable print of the own series
            _own_map = {
                "pce_headline": "PCEPI",
                "pce_core": "PCEPILFE",
                "ppi_finaldemand": "PPIFIS",
            }
            try:
                ip = knowable_series(vintages, _own_map[release], asof)
                if not ip.empty:
                    last_p = pd.Timestamp(ip["period"].iloc[-1])
                    next_p = (last_p.to_period("M") + 1).to_timestamp()
                    _period = f"{next_p.year}-{next_p.month:02d}"
            except Exception:
                pass

    if _period is not None:
        result["release_id"] = make_release_id(release, _period)
        result["prediction_id"] = make_prediction_id(result["release_id"], asof.isoformat())

    if release_date is not None:
        result["horizon_days"] = (release_date - asof).days

    return result


def _project_cpi(
    release: str,
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | None = None,
) -> dict:
    """Internal: CPI projection for a single asof date.

    ref_month: reference month of the upcoming print (from the event calendar);
    None derives it as last-knowable-print month + 1.
    """
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
    lag_key = "cpi_hl_mom" if release == "cpi_headline" else "cpi_core_mom"

    # Feature names (ordered; own 3 lags first per walk-forward contract)
    # V2: shelter_nowcast appended last (PREREG_V2.md §3)
    if release == "cpi_headline":
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1", "gasoline_mom", "shelter_nowcast",
        ]
    else:
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1", "shelter_nowcast",
        ]

    # Build expanding training dataset
    initial_prints = knowable_series(vintages, own_series, asof)
    if len(initial_prints) < 2:
        return _empty_projection(release, asof, "insufficient_data")

    mom_series = initial_prints.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)

    # Build records for walk-forward
    records = []
    for _, row in mom_series.iterrows():
        # asof for building features = the day BEFORE this period's realtime_start
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        feats, _ = build_cpi_features(
            step_asof, vintages, root, release_type=release, ref_month=row["period"]
        )
        rec = dict(feats)
        rec["target"] = row["mom"]
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_projection(release, asof, "insufficient_history")

    # Run walk-forward to build residual history
    wf_results = _walk_forward(records, feature_names, "target")
    if not wf_results:
        return _empty_projection(release, asof, "no_walk_forward_results")

    # Build current features — the upcoming print covers the month after the last
    # knowable initial print (unless the caller pinned it from the event calendar)
    if ref_month is None:
        ref_month = (
            (pd.Timestamp(mom_series["period"].iloc[-1]).to_period("M") + 1)
            .to_timestamp()
            .date()
        )
    feats, prov = build_cpi_features(
        asof, vintages, root, release_type=release, ref_month=ref_month
    )

    # Compute current prediction using all available training data
    train_recs = records  # all knowable at asof
    X_all = _build_matrix(train_recs, feature_names)
    y_all = np.array([r["target"] for r in train_recs], dtype=float)
    valid_target = ~np.isnan(y_all)
    X_all = X_all[valid_target]
    y_all = y_all[valid_target]

    pred_features = np.array(
        [feats.get(fn) if feats.get(fn) is not None else np.nan for fn in feature_names],
        dtype=float,
    )
    n_possible = len(feature_names)
    n_present = int(np.sum(~np.isnan(pred_features)))
    input_completeness = n_present / n_possible if n_possible > 0 else 0.0

    # Complete-case: select features available in pred row, drop training rows with NaN in those cols
    pred_avail_mask = ~np.isnan(pred_features)
    if pred_avail_mask.any():
        X_sel = X_all[:, pred_avail_mask]
        row_complete = ~np.any(np.isnan(X_sel), axis=1)
        X_clean = X_sel[row_complete]
        y_clean = y_all[row_complete]
        x_pred = pred_features[pred_avail_mask]
        n_features_used = int(pred_avail_mask.sum())
    else:
        X_clean = np.empty((0, 0))
        y_clean = np.empty(0)
        x_pred = np.empty(0)
        n_features_used = 0

    # Fit ridge and compute components (V2)
    components = None
    confidence_v2 = None
    confidence_components_v2 = None
    beta_features_out: np.ndarray | None = None
    z_features_out: np.ndarray | None = None

    if n_features_used > 0 and len(y_clean) >= MIN_TRAIN_OBS:
        try:
            point, beta_features_out, z_features_out = _ridge_predict_with_components(
                X_clean, y_clean, x_pred
            )
        except Exception:
            point = _ridge_predict(X_clean, y_clean, x_pred)
    else:
        point = None

    # Component contributions (V2 — PREREG_V2.md §4)
    if point is not None and beta_features_out is not None and z_features_out is not None:
        try:
            from engine.release_components_cpi import compute_components, compute_confidence_v2
            components = compute_components(
                feature_names, beta_features_out, z_features_out,
                pred_avail_mask, release
            )
            confidence_v2, confidence_components_v2 = compute_confidence_v2(
                components, input_completeness
            )
        except Exception as e:
            log.debug("Component computation failed: %s", e)

    # Residual errors: e = actual - predicted
    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])

    quantiles = _compute_quantiles(errors, point if point is not None else 0.0)

    # Confidence score (V1 — unchanged)
    confidence, interval_rank = None, None
    if point is not None and len(errors) >= MIN_QUANTILE_OBS:
        cur_width = (point + np.quantile(errors, 0.90)) - (point + np.quantile(errors, 0.10))
        # Compute expanding widths from wf history (last MIN_QUANTILE_OBS+ steps)
        hist_widths = []
        for k in range(MIN_QUANTILE_OBS, len(wf_results) + 1):
            e_sub = errors[:k]
            w = np.quantile(e_sub, 0.90) - np.quantile(e_sub, 0.10)
            hist_widths.append(w)
        if hist_widths:
            pctile = float(np.mean(np.array(hist_widths) <= cur_width))
            interval_rank = round(1.0 - pctile, 4)
            confidence = round(interval_rank * input_completeness, 4)

    # Baselines
    naive = float(mom_series["mom"].iloc[-1]) if len(mom_series) > 0 else None
    trailing_3m = (
        float(mom_series["mom"].iloc[-3:].mean()) if len(mom_series) >= 3 else naive
    )
    ar3_pred = _compute_ar3(mom_series["mom"].values, feature_names[:3], feats, y_all, X_all, pred_features)

    # Surprise skew
    sigma, tag, sigma_scale_pp = None, None, None
    if point is not None and naive is not None and len(errors) >= MIN_QUANTILE_OBS:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
            sigma_scale_pp = round(err_std, 4)
            sigma = round((point - naive) / err_std, 4)
            if abs(sigma) <= INLINE_BAND_SIGMA:
                tag = "inline"
            elif sigma > INLINE_BAND_SIGMA:
                tag = "hotter"
            else:
                tag = "cooler"

    prov.update({
        "n_train": int(len(y_all)),
        "n_features_used": n_features_used,
    })

    return {
        "release": release,
        "asof": asof.isoformat(),
        "inputs_hash": compute_inputs_hash(feats),
        # input_manifest: the feature values used for this projection (MRI-R26 honesty, rework-2a).
        # Additive metadata — never read back by scoring or interval computation.
        "input_manifest": {k: v for k, v in feats.items()},
        "point": round(point, 4) if point is not None else None,
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "confidence": confidence,
        "confidence_components": {
            "interval_rank": interval_rank,
            "input_completeness": round(input_completeness, 4),
        },
        # V2 additions (PREREG_V2.md §4, §5)
        "components": components,
        "confidence_v2": confidence_v2,
        "confidence_components_v2": confidence_components_v2,
        "input_completeness": round(input_completeness, 4),
        "benchmark_set": {
            "naive_prior": round(naive, 4) if naive is not None else None,
            "trailing_3m": round(trailing_3m, 4) if trailing_3m is not None else None,
            "ar_model": round(ar3_pred, 4) if ar3_pred is not None else None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {
            "sigma": sigma,
            "sigma_scale_pp": sigma_scale_pp,
            "tag": tag,
            "inline_band": INLINE_BAND_SIGMA,
        },
        "pit_provenance": prov,
        "display_only": True,
        "authority": False,
    }


def _compute_ar3(
    y_full: np.ndarray,
    ar3_feat_names: list[str],
    feats: dict,
    y_train: np.ndarray,
    X_train: np.ndarray,
    pred_features: np.ndarray,
) -> float | None:
    """Compute AR3 baseline prediction from own lags."""
    if len(y_train) < 4:
        return None
    # Build AR3 features: lags of y_full
    X_ar3 = np.full((len(y_train), 3), np.nan)
    for i in range(3, len(y_train) + 3):
        row_idx = i - 3
        if row_idx < len(y_train):
            for lag in range(1, 4):
                src_idx = i - lag
                if 0 <= src_idx < len(y_full):
                    X_ar3[row_idx, lag - 1] = y_full[src_idx]

    # Prediction row: last 3 values of y_full
    x_ar3_pred = np.array([y_full[-i] for i in range(1, 4)], dtype=float)
    if np.any(np.isnan(x_ar3_pred)):
        return None

    # Drop rows containing NaN before fitting (mirrors complete-case in _walk_forward)
    row_complete = ~np.any(np.isnan(X_ar3), axis=1)
    X_ar3_clean = X_ar3[row_complete]
    y_ar3_clean = y_train[row_complete]
    if X_ar3_clean.shape[0] < 4 or X_ar3_clean.shape[1] == 0:
        return None

    try:
        pred = _ridge_predict(X_ar3_clean, y_ar3_clean, x_ar3_pred)
        return float(pred) if np.isfinite(pred) else None
    except Exception:
        return None


def _project_nfp(asof: date, vintages: pd.DataFrame, root: Path) -> dict:
    """Internal: NFP projection for a single asof date."""
    feature_names = [
        "nfp_change_lag1", "nfp_change_lag2", "nfp_change_lag3",
        "claims_survey_week_icsa", "claims_survey_week_ccsa",
        "withheld_tax_yoy", "awhman_mom",
        # adp_change reserved for the Track-M challenger (MRI-R21/R27); excluded from champion to keep RESULTS_V2 frozen
    ]

    # All initial PAYEMS prints knowable at asof
    initial_prints = knowable_series(vintages, "PAYEMS", asof)
    if len(initial_prints) < 2:
        return _empty_projection("nfp", asof, "insufficient_data")

    diff_series = initial_prints.copy()
    diff_series["change"] = diff_series["value"].diff()
    diff_series = diff_series.dropna(subset=["change"]).reset_index(drop=True)

    # Build records
    records = []
    for _, row in diff_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"].date()
        try:
            feats, _ = build_nfp_features(step_asof, ref_month, vintages, root)
        except Exception as e:
            log.debug("NFP feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = row["change"]
        rec["period"] = row["period"]  # needed for decomposition BD prior PIT
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_projection("nfp", asof, "insufficient_history")

    wf_results = _walk_forward(records, feature_names, "target")
    if not wf_results:
        return _empty_projection("nfp", asof, "no_walk_forward_results")

    # Current features — target ref_month is the next calendar month after the
    # last knowable PAYEMS initial print (the period being predicted, not asof's
    # own calendar month, which may lag the target by 0-2 months).
    # FIX(M1): use the projection's actual target period, not date(asof.year, asof.month, 1).
    target_ref_month = (
        (pd.Timestamp(initial_prints["period"].iloc[-1]).to_period("M") + 1)
        .to_timestamp()
        .date()
    )
    feats, prov = build_nfp_features(asof, target_ref_month, vintages, root)

    # Current prediction
    train_recs = records
    X_all = _build_matrix(train_recs, feature_names)
    y_all = np.array([r["target"] for r in train_recs], dtype=float)
    valid_target = ~np.isnan(y_all)
    X_all = X_all[valid_target]
    y_all = y_all[valid_target]

    pred_features = np.array(
        [feats.get(fn) if feats.get(fn) is not None else np.nan for fn in feature_names],
        dtype=float,
    )
    n_possible = len(feature_names)
    n_present = int(np.sum(~np.isnan(pred_features)))
    input_completeness = n_present / n_possible if n_possible > 0 else 0.0

    # Complete-case: select features available in pred row, drop training rows with NaN
    pred_avail_mask_nfp = ~np.isnan(pred_features)
    if pred_avail_mask_nfp.any():
        X_sel_nfp = X_all[:, pred_avail_mask_nfp]
        row_complete_nfp = ~np.any(np.isnan(X_sel_nfp), axis=1)
        X_clean = X_sel_nfp[row_complete_nfp]
        y_clean = y_all[row_complete_nfp]
        x_pred = pred_features[pred_avail_mask_nfp]
        n_features_used = int(pred_avail_mask_nfp.sum())
    else:
        X_clean = np.empty((0, 0))
        y_clean = np.empty(0)
        x_pred = np.empty(0)
        n_features_used = 0

    if n_features_used > 0 and len(y_clean) >= MIN_TRAIN_OBS:
        point = _ridge_predict(X_clean, y_clean, x_pred)
    else:
        point = None

    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])
    quantiles = _compute_quantiles(errors, point if point is not None else 0.0)

    confidence, interval_rank = None, None
    if point is not None and len(errors) >= MIN_QUANTILE_OBS:
        cur_width = np.quantile(errors, 0.90) - np.quantile(errors, 0.10)
        hist_widths = []
        for k in range(MIN_QUANTILE_OBS, len(errors) + 1):
            e_sub = errors[:k]
            hist_widths.append(np.quantile(e_sub, 0.90) - np.quantile(e_sub, 0.10))
        if hist_widths:
            pctile = float(np.mean(np.array(hist_widths) <= cur_width))
            interval_rank = round(1.0 - pctile, 4)
            confidence = round(interval_rank * input_completeness, 4)

    # Baselines
    y_changes = diff_series["change"].values
    naive = float(y_changes[-1]) if len(y_changes) > 0 else None
    trailing_3m = float(np.mean(y_changes[-3:])) if len(y_changes) >= 3 else naive
    # AR3 for NFP
    ar3_pred = None
    if len(y_all) >= 4:
        x_ar3_pred = np.array([y_changes[-i] for i in range(1, 4)], dtype=float)
        if not np.any(np.isnan(x_ar3_pred)):
            # Build AR3 training X
            X_ar3 = np.full((len(y_all), 3), np.nan)
            y_change_full = diff_series["change"].values
            for i in range(3, len(y_change_full) + 1):
                ri = i - 3
                if ri < len(y_all):
                    for lag in range(1, 4):
                        si = i - lag - 1
                        if 0 <= si < len(y_change_full):
                            X_ar3[ri, lag - 1] = y_change_full[si]
            # Drop NaN rows before fitting (mirrors complete-case in _walk_forward)
            row_complete_ar3 = ~np.any(np.isnan(X_ar3), axis=1)
            X_ar3_clean = X_ar3[row_complete_ar3]
            y_ar3_clean = y_all[row_complete_ar3]
            try:
                if X_ar3_clean.shape[0] >= 4:
                    pred_raw = _ridge_predict(X_ar3_clean, y_ar3_clean, x_ar3_pred)
                    ar3_pred = float(pred_raw) if np.isfinite(pred_raw) else None
            except Exception:
                ar3_pred = None

    sigma, tag, sigma_scale_pp = None, None, None
    if point is not None and naive is not None and len(errors) >= MIN_QUANTILE_OBS:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
            sigma_scale_pp = round(err_std, 4)
            sigma = round((point - naive) / err_std, 4)
            if abs(sigma) <= INLINE_BAND_SIGMA:
                tag = "inline"
            elif sigma > INLINE_BAND_SIGMA:
                tag = "hotter"
            else:
                tag = "cooler"

    prov.update({
        "n_train": int(len(y_all)),
        "n_features_used": n_features_used,
    })

    # PR-H: NFP decomposition (display-only) per PREREG_NFP_DECOMP_V1.md §2
    # Annotate wf_results with period metadata for birth-death prior PIT calculation
    wf_for_decomp = []
    for r in wf_results:
        meta = records[r["idx"]] if r["idx"] < len(records) else {}
        wf_for_decomp.append({
            "actual": r.get("actual"),
            "predicted": r.get("predicted"),
            "period": meta.get("period"),
            "result_pos": r.get("result_pos"),
        })

    try:
        from engine.release_components_nfp import (
            build_nfp_components,
            compute_nfp_revision_risk,
        )
        components = build_nfp_components(
            point,
            asof,
            target_ref_month,
            vintages,
            wf_for_decomp,
            knowable_series_fn=knowable_series,
        )
        revision_risk = compute_nfp_revision_risk(vintages)
    except Exception as e:
        log.debug("NFP decomposition/revision_risk failed: %s", e)
        components = None
        revision_risk = None

    return {
        "release": "nfp",
        "asof": asof.isoformat(),
        "inputs_hash": compute_inputs_hash(feats),
        # input_manifest: feature values used for this projection (MRI-R26 honesty, rework-2a).
        "input_manifest": {k: v for k, v in feats.items()},
        "point": round(point, 2) if point is not None else None,
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "confidence": confidence,
        "confidence_components": {
            "interval_rank": interval_rank,
            "input_completeness": round(input_completeness, 4),
        },
        "input_completeness": round(input_completeness, 4),
        "benchmark_set": {
            "naive_prior": round(naive, 2) if naive is not None else None,
            "trailing_3m": round(trailing_3m, 2) if trailing_3m is not None else None,
            "ar_model": round(ar3_pred, 2) if ar3_pred is not None else None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {
            "sigma": sigma,
            "sigma_scale_pp": sigma_scale_pp,
            "tag": tag,
            "inline_band": INLINE_BAND_SIGMA,
        },
        "components": components,        # PR-H: private/govt/BD decomposition (display-only)
        "revision_risk": revision_risk,  # PR-H: trailing 24m revision mean/sign (display-only)
        "pit_provenance": prov,
        "display_only": True,
        "authority": False,
    }


def _empty_projection(release: str, asof: date, reason: str) -> dict:
    """Return a null projection dict with display_only=True."""
    return {
        "release": release,
        "asof": asof.isoformat(),
        "point": None,
        "p10": None,
        "p25": None,
        "p50": None,
        "p75": None,
        "p90": None,
        "confidence": None,
        "confidence_components": {"interval_rank": None, "input_completeness": 0.0},
        # V2 additions — null in empty projections
        "components": None,
        "confidence_v2": None,
        "confidence_components_v2": None,
        "input_completeness": 0.0,
        "benchmark_set": {
            "naive_prior": None,
            "trailing_3m": None,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {"sigma": None, "sigma_scale_pp": None, "tag": None, "inline_band": INLINE_BAND_SIGMA},
        "pit_provenance": {
            "revision_optimistic_legs": [],
            "unrevised_legs": [],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
            "reason": reason,
        },
        "display_only": True,
        "authority": False,
    }


# ---------------------------------------------------------------------------
# Walk-forward with full metrics (used by backtest)
# ---------------------------------------------------------------------------

def run_walk_forward_full(
    release: str,
    root: str | Path,
) -> dict:
    """Run the full walk-forward backtest for a release type.

    Returns dict with:
      results: list of per-step dicts
      errors: np.ndarray of actual - predicted
      feature_names: list[str]
      metadata: dict

    release: 'cpi_headline' | 'cpi_core' | 'nfp' | 'claims'
    """
    root = Path(root)
    vintages = load_vintages(root)

    if release in ("cpi_headline", "cpi_core"):
        return _wf_cpi_full(release, vintages, root)
    elif release == "nfp":
        return _wf_nfp_full(vintages, root)
    elif release == "ahe":
        return _wf_ahe_full(vintages)
    elif release == "awh":
        return _wf_awh_full(vintages)
    elif release == "claims":
        return _wf_claims_ic4wsa_full(vintages, root)
    else:
        raise ValueError(f"Unknown release: {release!r}")


def _wf_claims_ic4wsa_full(vintages: pd.DataFrame, root: Path) -> dict:
    """Full walk-forward for claims using the canonical IC4WSA spec.

    Spec (attempt 2 per CLAIMS_BACKTEST.md): for each ICSA initial print (the actual),
    the point prediction is the most recent IC4WSA value knowable one day before that
    ICSA print was published (PIT law). This is the frozen trivial spec shipped in
    engine/release_components_nfp.project_claims.

    Result rows include:
      predicted: IC4WSA value (thousands) used as point — raw IC4WSA / 1 (already k)
      actual:    ICSA initial print (thousands) — raw ICSA / 1000
      baseline_naive:     last ICSA initial print knowable before that week
      baseline_trailing4w: mean of last 4 ICSA initial prints
      baseline_ar3:        AR3 Ridge on ICSA levels in thousands
    """
    # All ICSA initial prints (level in thousands of persons)
    all_icsa = knowable_series(vintages, "ICSA", date(2099, 1, 1))
    all_icsa = all_icsa.sort_values(["period", "realtime_start"]).reset_index(drop=True)
    # Keep only first (initial) print per period to preserve PIT structure.
    # The "initial print" is the first entry for each period in chronological
    # realtime_start order — that is what knowable_series returns.
    all_icsa_initial = all_icsa.drop_duplicates(subset=["period"], keep="first")
    all_icsa_initial = all_icsa_initial.sort_values("realtime_start").reset_index(drop=True)

    # All IC4WSA prints (4-week moving average, raw level in thousands)
    all_ic4wsa = knowable_series(vintages, "IC4WSA", date(2099, 1, 1))
    all_ic4wsa = all_ic4wsa.sort_values(["period", "realtime_start"]).reset_index(drop=True)

    results = []
    for step_idx, icsa_row in all_icsa_initial.iterrows():
        icsa_rt = icsa_row["realtime_start"]
        icsa_period = icsa_row["period"]
        icsa_actual_k = float(icsa_row["value"]) / 1000.0

        # Decision day = one day before the ICSA print was published
        step_asof = (pd.Timestamp(icsa_rt) - pd.Timedelta(days=1)).date()

        # IC4WSA knowable at step_asof: same or prior period, published before icsa_rt
        ic4_avail = all_ic4wsa[
            (all_ic4wsa["period"] <= icsa_period) &
            (all_ic4wsa["realtime_start"] < icsa_rt)
        ]
        if ic4_avail.empty:
            continue  # no IC4WSA prediction available yet — skip this ICSA print
        ic4_pred_k = float(ic4_avail.iloc[-1]["value"]) / 1000.0  # convert to thousands

        # Naive: last ICSA knowable before this print (strictly prior realtime_start)
        icsa_prior = all_icsa_initial[all_icsa_initial["realtime_start"] < icsa_rt]
        naive_k: float | None = (
            float(icsa_prior["value"].iloc[-1]) / 1000.0 if not icsa_prior.empty else None
        )

        # Trailing 4w: mean of last 4 ICSA initial prints strictly before this print
        trailing_4w_k: float | None = None
        if not icsa_prior.empty:
            last4 = icsa_prior["value"].values[-4:]
            trailing_4w_k = float(np.mean(last4)) / 1000.0

        # AR3 Ridge on ICSA levels: fit on all prior ICSA initial prints (thousands)
        ar3_k: float | None = None
        if not icsa_prior.empty and len(icsa_prior) >= 4:
            y_ar = icsa_prior["value"].values / 1000.0
            X_ar3 = np.full((len(y_ar), 3), np.nan)
            for i in range(3, len(y_ar)):
                for lag in range(1, 4):
                    X_ar3[i, lag - 1] = y_ar[i - lag]
            row_ok = ~np.any(np.isnan(X_ar3), axis=1)
            if row_ok.sum() >= 4:
                X_clean_ar = X_ar3[row_ok]
                y_clean_ar = y_ar[row_ok]
                x_pred_ar = np.array([y_ar[-i] for i in range(1, 4)], dtype=float)
                try:
                    lam = 1.0
                    A = X_clean_ar.T @ X_clean_ar + lam * np.eye(3)
                    b_vec = X_clean_ar.T @ y_clean_ar
                    coef = np.linalg.solve(A, b_vec)
                    pred_raw = float(x_pred_ar @ coef)
                    ar3_k = pred_raw if np.isfinite(pred_raw) else None
                except Exception:
                    ar3_k = None

        results.append({
            "result_pos": len(results),
            "idx": int(step_idx),
            "period": icsa_period,
            "release_date": icsa_rt,
            "asof": step_asof,
            "predicted": ic4_pred_k,
            "actual": icsa_actual_k,
            "baseline_naive": naive_k,
            "baseline_trailing4w": trailing_4w_k,
            "baseline_ar3": ar3_k,
        })

    return {
        "results": results,
        "feature_names": ["ic4wsa_as_point"],
        "metadata": {
            "release": "claims",
            "spec": "ic4wsa_point",
            "n_records": len(all_icsa_initial),
        },
    }


def _wf_cpi_full(release: str, vintages: pd.DataFrame, root: Path) -> dict:
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
    lag_key = "cpi_hl_mom" if release == "cpi_headline" else "cpi_core_mom"

    # V2: shelter_nowcast appended last (PREREG_V2.md §3)
    if release == "cpi_headline":
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1", "gasoline_mom", "shelter_nowcast",
        ]
    else:
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1", "shelter_nowcast",
        ]

    # Use ALL vintages knowable at the last available date for building the full sequence
    # But for each step, we use only what was knowable at that step's D
    all_series = knowable_series(vintages, own_series, date(2099, 1, 1))
    mom_series = all_series.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)

    records = []
    for _, row in mom_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        try:
            feats, _ = build_cpi_features(
                step_asof, vintages, root, release_type=release, ref_month=row["period"]
            )
        except Exception as e:
            log.debug("CPI feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = row["mom"]
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    wf_results = _walk_forward(records, feature_names, "target")

    # Annotate with period metadata + shelter presence (M4 fix: direct feature-row check)
    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")
        # shelter_nowcast_present: True when shelter_nowcast was non-null in the feature row
        r["shelter_nowcast_present"] = meta_rec.get("shelter_nowcast") is not None

    return {
        "results": wf_results,
        "feature_names": feature_names,
        "metadata": {"release": release, "n_records": len(records)},
    }


def _wf_nfp_full(vintages: pd.DataFrame, root: Path) -> dict:
    feature_names = [
        "nfp_change_lag1", "nfp_change_lag2", "nfp_change_lag3",
        "claims_survey_week_icsa", "claims_survey_week_ccsa",
        "withheld_tax_yoy", "awhman_mom",
        # adp_change reserved for the Track-M challenger (MRI-R21/R27); excluded from champion to keep RESULTS_V2 frozen
    ]

    all_series = knowable_series(vintages, "PAYEMS", date(2099, 1, 1))
    diff_series = all_series.copy()
    diff_series["change"] = diff_series["value"].diff()
    diff_series = diff_series.dropna(subset=["change"]).reset_index(drop=True)

    records = []
    for _, row in diff_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"].date()
        try:
            feats, _ = build_nfp_features(step_asof, ref_month, vintages, root)
        except Exception as e:
            log.debug("NFP feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = row["change"]
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    wf_results = _walk_forward(records, feature_names, "target")

    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")

    return {
        "results": wf_results,
        "feature_names": feature_names,
        "metadata": {"release": "nfp", "n_records": len(records)},
    }


def _wf_ahe_full(vintages: pd.DataFrame) -> dict:
    """Walk-forward for AHE MoM % target (CES0500000003). PR-H."""
    from engine.release_components_nfp import build_ahe_features

    feature_names = [
        "ahe_mom_lag1", "ahe_mom_lag2", "ahe_mom_lag3",
        "awh_mom_last", "jolts_mom_last", "icsa_level_z",
    ]

    all_series = knowable_series(vintages, "CES0500000003", date(2099, 1, 1))
    if len(all_series) < 2:
        return {"results": [], "feature_names": feature_names,
                "metadata": {"release": "ahe", "n_records": 0}}

    ahe_levels = all_series.copy()
    ahe_levels["mom"] = ahe_levels["value"].pct_change() * 100.0
    ahe_levels = ahe_levels.dropna(subset=["mom"]).reset_index(drop=True)

    records = []
    for _, row in ahe_levels.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month_step = row["period"].date() if hasattr(row["period"], "date") else date(
            pd.Timestamp(row["period"]).year, pd.Timestamp(row["period"]).month, 1
        )
        try:
            feats, _ = build_ahe_features(
                step_asof, ref_month_step, vintages,
                knowable_series_fn=knowable_series,
                survey_week_claims_fn=_survey_week_claims,
            )
        except Exception as e:
            log.debug("AHE feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = float(row["mom"])
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    wf_results = _walk_forward(records, feature_names, "target")

    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")

    return {
        "results": wf_results,
        "feature_names": feature_names,
        "metadata": {"release": "ahe", "n_records": len(records)},
    }


def _wf_awh_full(vintages: pd.DataFrame) -> dict:
    """Walk-forward for AWH level (AWHAETP). Persistence-only. PR-H."""
    all_series = knowable_series(vintages, "AWHAETP", date(2099, 1, 1))
    if len(all_series) < 2:
        return {"results": [], "feature_names": [],
                "metadata": {"release": "awh", "n_records": 0, "persistence_only": True}}

    awh_sorted = all_series.sort_values("period").reset_index(drop=True)
    levels = awh_sorted["value"].values

    # For persistence model: predicted = levels[i-1], actual = levels[i]
    results = []
    for i in range(1, len(awh_sorted)):
        row = awh_sorted.iloc[i]
        prev_val = float(levels[i - 1])
        actual_val = float(levels[i])
        results.append({
            "idx": i,
            "result_pos": i - 1,
            "predicted": prev_val,
            "actual": actual_val,
            "baseline_naive": prev_val,  # model IS naive
            "baseline_trailing3m": float(np.mean(levels[max(0, i - 3):i])),
            "baseline_ar3": prev_val,
            "n_train": i,
            "n_features_used": 1,
            "input_completeness": 1.0,
            "period": row["period"],
            "release_date": row["realtime_start"],
        })

    return {
        "results": results,
        "feature_names": ["last_level"],
        "metadata": {"release": "awh", "n_records": len(awh_sorted), "persistence_only": True},
    }
