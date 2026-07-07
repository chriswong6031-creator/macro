"""Macro Release Intelligence — pre-print projection models for CPI and NFP.

LEAF · DISPLAY-ONLY. Imports nothing from the mechanical scoring core
(conditions/regime/run/inputs/equity_alloc) and nothing in the scoring path
imports this module. Every public function returns plain data and NEVER raises
into the build — all IO failures degrade gracefully (missing legs → leg dropped,
recorded in provenance).

SPECIFICATION: research/release_forecast/PREREG_V1.md (frozen 2026-07-07).
Anti-mining: one spec per release type, frozen before any results were observed.

PIT LAW: a feature value is usable at decision date D only if its ALFRED
realtime_start <= D. The `knowable_series` function enforces this filter. Non-
vintaged series (AWHMAN, GASREGW, withheld_taxes) are declared per-leg in
provenance as revision_optimistic_legs or unrevised_legs.

Model: Ridge regression (lambda=1.0, closed-form numpy), z-scored features,
expanding-window walk-forward (min 60 obs before first prediction, refit each step).

display_only=True, authority=False on all outputs — never conditions scoring.

numpy / pandas only. No sklearn, statsmodels, or scipy.stats (house law).
"""
from __future__ import annotations

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
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for CPI prediction at decision date asof.

    release_type: 'cpi_headline' or 'cpi_core'.
    Returns (features_dict, provenance_dict).
    features_dict: {feature_name: value_or_None}
    provenance_dict: {revision_optimistic_legs, unrevised_legs, absent_legs, ...}
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
        "unrevised_legs": [],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
    }

    # Select own-series based on release type
    if release_type == "cpi_headline":
        own_series = "CPIAUCSL"
        lag_key = "cpi_hl_mom"
    else:
        own_series = "CPILFESL"
        lag_key = "cpi_core_mom"

    # Own lags (3 MoM)
    own_lags = _last_n_mom_lags(vintages, own_series, asof, n=3)
    features: dict[str, float | None] = {
        f"{lag_key}_lag1": own_lags[0],
        f"{lag_key}_lag2": own_lags[1],
        f"{lag_key}_lag3": own_lags[2],
    }

    # Sticky CPI (2014-03+)
    sticky_lags = _last_n_mom_lags(vintages, "STICKCPIM157SFRBATL", asof, n=1)
    features["sticky_mom_lag1"] = sticky_lags[0]

    # Median CPI (2014-02+)
    median_lags = _last_n_mom_lags(vintages, "MEDCPIM158SFRBCLE", asof, n=1)
    features["median_mom_lag1"] = median_lags[0]

    # Flexible CPI (2014-03+)
    flex_lags = _last_n_mom_lags(vintages, "FLEXCPIM157SFRBATL", asof, n=1)
    features["flex_mom_lag1"] = flex_lags[0]

    # PPI Final Demand (2014-03+, lag handled by realtime_start filter automatically)
    ppi_lags = _last_n_mom_lags(vintages, "PPIFIS", asof, n=1)
    features["ppi_mom_lag1"] = ppi_lags[0]

    # Gasoline (headline only; fail-open if absent)
    if release_type == "cpi_headline":
        prov["unrevised_legs"].append("gasoline_mom")
        gasregw_path = root / "data" / "fred" / "GASREGW.parquet"
        if gasregw_path.exists():
            try:
                gasregw = pd.read_parquet(gasregw_path)
                gasregw.index = pd.to_datetime(gasregw.index)
                # Get reference month and prior month weekly averages
                asof_ts = pd.Timestamp(asof)
                cur_month = asof_ts.to_period("M")
                prior_month = (cur_month - 1).to_timestamp()
                cur_month_ts = cur_month.to_timestamp()
                # average gasoline for reference month M (weeks falling in M)
                gasregw_col = gasregw.columns[0]
                cur_m_mask = (gasregw.index >= cur_month_ts) & (gasregw.index < asof_ts)
                prior_m_mask = (gasregw.index >= prior_month) & (gasregw.index < cur_month_ts)
                cur_avg = gasregw.loc[cur_m_mask, gasregw_col].mean() if cur_m_mask.any() else np.nan
                prior_avg = gasregw.loc[prior_m_mask, gasregw_col].mean() if prior_m_mask.any() else np.nan
                if np.isfinite(cur_avg) and np.isfinite(prior_avg) and prior_avg != 0:
                    features["gasoline_mom"] = float((cur_avg / prior_avg - 1) * 100)
                else:
                    features["gasoline_mom"] = None
                    absent_legs.append("gasoline_mom")
            except Exception as e:
                log.debug("GASREGW read failed: %s", e)
                features["gasoline_mom"] = None
                absent_legs.append("gasoline_mom")
        else:
            features["gasoline_mom"] = None
            absent_legs.append("gasoline_mom")
            prov["gasoline_absent"] = True
    else:
        prov["gasoline_absent"] = True  # core excludes gasoline by definition

    prov["absent_legs"] = absent_legs
    return features, prov


def build_nfp_features(
    asof: date,
    ref_month: date,
    vintages: pd.DataFrame,
    root: Path,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for NFP prediction at decision date asof for ref_month.

    Returns (features_dict, provenance_dict).
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": ["awhman_mom"],
        "unrevised_legs": ["withheld_tax_yoy", "adp_change"],  # gasoline_mom_absent removed: gasoline is CPI-only
        "absent_legs": [],
        "display_only": True,
        "authority": False,
        "withheld_tax_start": "2023-02-14",
    }

    # PAYEMS own lags (3 MoM differences in thousands)
    own_lags = _last_n_diff_lags(vintages, "PAYEMS", asof, n=3)
    features: dict[str, float | None] = {
        "nfp_change_lag1": own_lags[0],
        "nfp_change_lag2": own_lags[1],
        "nfp_change_lag3": own_lags[2],
    }

    # Claims: ICSA survey-week delta
    prior_month = (
        date(ref_month.year, ref_month.month, 1) - timedelta(days=1)
    )
    prior_month = date(prior_month.year, prior_month.month, 1)

    icsa_cur = _survey_week_claims(vintages, "ICSA", asof, ref_month)
    icsa_prior = _survey_week_claims(vintages, "ICSA", asof, prior_month)
    if icsa_cur is not None and icsa_prior is not None:
        features["claims_survey_week_icsa"] = float(icsa_cur - icsa_prior)
    else:
        features["claims_survey_week_icsa"] = None
        absent_legs.append("claims_survey_week_icsa")

    # Claims: CCSA survey-week delta
    ccsa_cur = _survey_week_claims(vintages, "CCSA", asof, ref_month)
    ccsa_prior = _survey_week_claims(vintages, "CCSA", asof, prior_month)
    if ccsa_cur is not None and ccsa_prior is not None:
        features["claims_survey_week_ccsa"] = float(ccsa_cur - ccsa_prior)
    else:
        features["claims_survey_week_ccsa"] = None
        absent_legs.append("claims_survey_week_ccsa")

    # Withheld taxes YoY (unrevised; starts 2023-02-14)
    prov["unrevised_legs"] = list(set(prov["unrevised_legs"]) | {"withheld_tax_yoy"})
    tx_path = root / "data" / "treasury" / "withheld_taxes.parquet"
    if tx_path.exists():
        try:
            tx = pd.read_parquet(tx_path)
            tx.index = pd.to_datetime(tx.index)
            tx_col = tx.columns[0]
            # 30-day window ending at the survey reference week (12th)
            ref_12 = pd.Timestamp(ref_month.year, ref_month.month, 12)
            window_start = ref_12 - pd.Timedelta(days=29)
            year_ago_12 = ref_12 - pd.Timedelta(days=365)
            year_ago_start = year_ago_12 - pd.Timedelta(days=29)

            cur_window = tx.loc[window_start:ref_12, tx_col]
            prior_window = tx.loc[year_ago_start:year_ago_12, tx_col]

            cur_sum = cur_window.sum() if len(cur_window) > 0 else np.nan
            prior_sum = prior_window.sum() if len(prior_window) > 0 else np.nan

            if np.isfinite(cur_sum) and np.isfinite(prior_sum) and prior_sum != 0 and cur_sum > 0 and prior_sum > 0:
                features["withheld_tax_yoy"] = float((cur_sum / prior_sum - 1) * 100)
            else:
                features["withheld_tax_yoy"] = None
                absent_legs.append("withheld_tax_yoy")
        except Exception as e:
            log.debug("withheld_taxes read failed: %s", e)
            features["withheld_tax_yoy"] = None
            absent_legs.append("withheld_tax_yoy")
    else:
        features["withheld_tax_yoy"] = None
        absent_legs.append("withheld_tax_yoy")

    # AWHMAN MoM (revision-optimistic; last knowable = month M-1)
    awhman_path = root / "data" / "fred" / "AWHMAN.parquet"
    if awhman_path.exists():
        try:
            awhman = pd.read_parquet(awhman_path)
            awhman.index = pd.to_datetime(awhman.index)
            awhman_col = awhman.columns[0]
            # last knowable = M-1 (AWHMAN releases with NFP)
            awhman_monthly = awhman[awhman_col].resample("MS").last()
            asof_ts = pd.Timestamp(asof)
            # Use data up to 2 months before asof to be safe (M-1 release is with NFP)
            ref_m = pd.Timestamp(ref_month)
            m_minus_1 = (ref_m.to_period("M") - 1).to_timestamp()
            m_minus_2 = (ref_m.to_period("M") - 2).to_timestamp()
            v1 = awhman_monthly.get(m_minus_1)
            v2 = awhman_monthly.get(m_minus_2)
            if v1 is not None and v2 is not None and not np.isnan(v1) and not np.isnan(v2):
                features["awhman_mom"] = float(v1 - v2)
            else:
                features["awhman_mom"] = None
                absent_legs.append("awhman_mom")
        except Exception as e:
            log.debug("AWHMAN read failed: %s", e)
            features["awhman_mom"] = None
            absent_legs.append("awhman_mom")
    else:
        features["awhman_mom"] = None
        absent_legs.append("awhman_mom")

    # ADP (fail-open if absent)
    adp_path = root / "data" / "fred" / "ADPNFRPRIVSA.parquet"
    prov["unrevised_legs"] = list(set(prov["unrevised_legs"]))
    if adp_path.exists():
        try:
            adp = pd.read_parquet(adp_path)
            adp.index = pd.to_datetime(adp.index)
            adp_col = adp.columns[0]
            ref_m = pd.Timestamp(ref_month)
            adp_val = adp[adp_col].get(ref_m)
            if adp_val is not None and not np.isnan(adp_val):
                features["adp_change"] = float(adp_val)
            else:
                features["adp_change"] = None
                absent_legs.append("adp_change")
        except Exception as e:
            log.debug("ADP read failed: %s", e)
            features["adp_change"] = None
            absent_legs.append("adp_change")
    else:
        features["adp_change"] = None
        absent_legs.append("adp_change")

    prov["absent_legs"] = absent_legs
    return features, prov


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


def _compute_quantiles(residuals: np.ndarray, point: float, min_obs: int = MIN_QUANTILE_OBS) -> dict:
    """Return p10/p25/p50/p75/p90 intervals centered on point from residual history."""
    if len(residuals) < min_obs:
        return {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
    qs = np.quantile(residuals, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "p10": round(point + qs[0], 4),
        "p25": round(point + qs[1], 4),
        "p50": round(point + qs[2], 4),
        "p75": round(point + qs[3], 4),
        "p90": round(point + qs[4], 4),
    }


# ---------------------------------------------------------------------------
# Main projection API
# ---------------------------------------------------------------------------

def project_release(
    release: str,
    asof: date,
    root: str | Path,
) -> dict:
    """Generate a point-in-time projection for a macro release.

    Parameters
    ----------
    release : str
        One of 'cpi_headline', 'cpi_core', 'nfp'.
    asof : date
        Decision date (the day before the target release is published).
    root : str | Path
        Repository root (data/ subdirectories are read from here).

    Returns
    -------
    dict matching the release_forecast.v1 projection block schema defined in PREREG_V1.md.
    display_only=True, authority=False.
    """
    root = Path(root)
    vintages = load_vintages(root)

    if release == "cpi_headline":
        return _project_cpi(release, asof, vintages, root)
    elif release == "cpi_core":
        return _project_cpi(release, asof, vintages, root)
    elif release == "nfp":
        return _project_nfp(asof, vintages, root)
    else:
        raise ValueError(f"Unknown release type: {release!r}. Use 'cpi_headline', 'cpi_core', or 'nfp'.")


def _project_cpi(
    release: str,
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
) -> dict:
    """Internal: CPI projection for a single asof date."""
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
    lag_key = "cpi_hl_mom" if release == "cpi_headline" else "cpi_core_mom"

    # Feature names (ordered; own 3 lags first per walk-forward contract)
    if release == "cpi_headline":
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1", "gasoline_mom",
        ]
    else:
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1",
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
        feats, _ = build_cpi_features(step_asof, vintages, root, release_type=release)
        rec = dict(feats)
        rec["target"] = row["mom"]
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_projection(release, asof, "insufficient_history")

    # Run walk-forward to build residual history
    wf_results = _walk_forward(records, feature_names, "target")
    if not wf_results:
        return _empty_projection(release, asof, "no_walk_forward_results")

    # Build current features
    feats, prov = build_cpi_features(asof, vintages, root, release_type=release)

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

    if n_features_used > 0 and len(y_clean) >= MIN_TRAIN_OBS:
        point = _ridge_predict(X_clean, y_clean, x_pred)
    else:
        point = None

    # Residual errors: e = actual - predicted
    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])

    quantiles = _compute_quantiles(errors, point if point is not None else 0.0)

    # Confidence score
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
    sigma, tag = None, None
    if point is not None and naive is not None and len(errors) >= MIN_QUANTILE_OBS:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
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
        "withheld_tax_yoy", "awhman_mom", "adp_change",
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
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_projection("nfp", asof, "insufficient_history")

    wf_results = _walk_forward(records, feature_names, "target")
    if not wf_results:
        return _empty_projection("nfp", asof, "no_walk_forward_results")

    # Current features
    asof_month = date(asof.year, asof.month, 1)
    feats, prov = build_nfp_features(asof, asof_month, vintages, root)

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

    sigma, tag = None, None
    if point is not None and naive is not None and len(errors) >= MIN_QUANTILE_OBS:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
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
        "release": "nfp",
        "asof": asof.isoformat(),
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
            "tag": tag,
            "inline_band": INLINE_BAND_SIGMA,
        },
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
        "input_completeness": 0.0,
        "benchmark_set": {
            "naive_prior": None,
            "trailing_3m": None,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {"sigma": None, "tag": None, "inline_band": INLINE_BAND_SIGMA},
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

    release: 'cpi_headline' | 'cpi_core' | 'nfp'
    """
    root = Path(root)
    vintages = load_vintages(root)

    if release in ("cpi_headline", "cpi_core"):
        return _wf_cpi_full(release, vintages, root)
    elif release == "nfp":
        return _wf_nfp_full(vintages, root)
    else:
        raise ValueError(f"Unknown release: {release!r}")


def _wf_cpi_full(release: str, vintages: pd.DataFrame, root: Path) -> dict:
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
    lag_key = "cpi_hl_mom" if release == "cpi_headline" else "cpi_core_mom"

    if release == "cpi_headline":
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1", "gasoline_mom",
        ]
    else:
        feature_names = [
            f"{lag_key}_lag1", f"{lag_key}_lag2", f"{lag_key}_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1",
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
            feats, _ = build_cpi_features(step_asof, vintages, root, release_type=release)
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

    # Annotate with period metadata
    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")

    return {
        "results": wf_results,
        "feature_names": feature_names,
        "metadata": {"release": release, "n_records": len(records)},
    }


def _wf_nfp_full(vintages: pd.DataFrame, root: Path) -> dict:
    feature_names = [
        "nfp_change_lag1", "nfp_change_lag2", "nfp_change_lag3",
        "claims_survey_week_icsa", "claims_survey_week_ccsa",
        "withheld_tax_yoy", "awhman_mom", "adp_change",
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
