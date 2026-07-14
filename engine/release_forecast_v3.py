"""MRI Track M — v3_factor CHALLENGER (PCA top-3 + Ridge, pure numpy).

SPECIFICATION: research/release_forecast/PREREG_V3_FACTOR.md (frozen 2026-07-08).
ANTI-MINING: this module is committed after the prereg and before backtest results.

Model: complete-case feature panel → z-score (expanding window) → PCA top-3 via
np.linalg.svd → ridge(lambda=1.0) on [3 factors + naive anchor + bias].

DISPLAY-ONLY. display_only=True, authority=False on all outputs.
Never conditions scoring, never gates or sizes positions.

Pure numpy/pandas only. No sklearn, statsmodels, or scipy.

CPI features reused from engine.release_components_cpi (same PIT injection as champion).
NFP features reused from engine.release_components_nfp (same PIT injection as champion).
Champion helpers _compute_quantiles, _wilson reused directly from engine.release_forecast.

New legs added by v3 (not in champion):
  CPI: ppi_fes_mom_lag1 (PPIFES), dollar_mom (DTWEXBGS monthly avg)
  NFP: adp_change (already built by champion's NFP builder), dollar_mom (DTWEXBGS)
"""
from __future__ import annotations

import logging
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — same as champion (frozen per PREREG_V3_FACTOR.md)
# ---------------------------------------------------------------------------
RIDGE_LAMBDA = 1.0
MIN_TRAIN_OBS = 60
MIN_QUANTILE_OBS = 24
INLINE_BAND_SIGMA = 0.35
COVID_MONTHS = {(2020, m) for m in range(3, 7)}

# CPI v3 feature name lists (ORDER PRESERVED per prereg §2.1 / §2.2)
_CPI_HL_FEATURES = [
    "cpi_hl_mom_lag1", "cpi_hl_mom_lag2", "cpi_hl_mom_lag3",
    "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
    "ppi_fis_mom_lag1",   # from PPIFIS vintages
    "ppi_fes_mom_lag1",   # NEW v3: from PPIFES (parquet, revision_optimistic)
    "gasoline_mom",       # from GASREGW parquet
    "shelter_nowcast",    # ZORI + CPI shelter blend (champion V2 leg)
    "dollar_mom",         # NEW v3: DTWEXBGS monthly avg MoM (parquet)
]
_CPI_CORE_FEATURES = [
    "cpi_core_mom_lag1", "cpi_core_mom_lag2", "cpi_core_mom_lag3",
    "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
    "ppi_fis_mom_lag1",
    "ppi_fes_mom_lag1",   # NEW v3
    "shelter_nowcast",    # champion V2 leg
    "dollar_mom",         # NEW v3
]
_NFP_FEATURES = [
    "nfp_change_lag1", "nfp_change_lag2", "nfp_change_lag3",
    "claims_survey_week_icsa", "claims_survey_week_ccsa",
    "withheld_tax_yoy", "awhman_mom",
    "adp_change",         # champion already builds this; added here
    "dollar_mom",         # NEW v3
]


# ---------------------------------------------------------------------------
# New feature builders (legs not in champion feature builders)
# ---------------------------------------------------------------------------

def _build_ppifes_mom_lag1(
    asof: date,
    root: Path,
    vintages: pd.DataFrame,
    knowable_series_fn,
) -> float | None:
    """MoM % change in PPIFES (PPI services ex-trade), lag-1 at asof.

    Primary source: ALFRED vintages (available from 2010-04 in vintages.parquet).
    Uses knowable_series_fn for PIT-safe initial-print filter.
    If vintage row unavailable, falls back to parquet read (asof-filtered, revision_optimistic).

    Returns None if no data available at asof.
    """
    # Try vintages first (PIT-safe)
    try:
        df = knowable_series_fn(vintages, "PPIFES", asof)
        if len(df) >= 2:
            levels = df.set_index("period")["value"]
            mom = levels.pct_change() * 100.0
            mom = mom.dropna()
            if len(mom) >= 1:
                return float(mom.iloc[-1])
    except Exception as e:
        log.debug("PPIFES vintage read failed: %s", e)

    # Fallback: direct parquet (revision_optimistic, asof-filtered)
    try:
        path = root / "data" / "fred" / "PPIFES.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index)
            asof_ts = pd.Timestamp(asof)
            df_pit = df[df.index <= asof_ts]
            if len(df_pit) >= 2:
                col = df_pit.columns[0]
                levels = df_pit[col].resample("MS").last().dropna()
                if len(levels) >= 2:
                    mom = levels.pct_change() * 100.0
                    mom = mom.dropna()
                    if len(mom) >= 1:
                        return float(mom.iloc[-1])
    except Exception as e:
        log.debug("PPIFES parquet read failed: %s", e)

    return None


def _build_dollar_mom(asof: date, root: Path) -> float | None:
    """MoM % change in the broad dollar (DTWEXBGS), computed as monthly average.

    DTWEXBGS is a daily series. We compute monthly averages then MoM % change.
    PIT: only dates <= asof are used (revision_optimistic — not ALFRED-vintaged).

    Returns the most recent available monthly MoM % change as of asof.
    Returns None if insufficient data.
    """
    try:
        path = root / "data" / "fred" / "DTWEXBGS.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        asof_ts = pd.Timestamp(asof)
        df_pit = df[df.index <= asof_ts]
        if df_pit.empty:
            return None
        col = df_pit.columns[0]
        # Monthly average: resample daily to month-start (business-day mean)
        monthly = df_pit[col].resample("MS").mean().dropna()
        if len(monthly) < 2:
            return None
        mom = monthly.pct_change() * 100.0
        mom = mom.dropna()
        if len(mom) < 1:
            return None
        return float(mom.iloc[-1])
    except Exception as e:
        log.debug("DTWEXBGS dollar_mom read failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# V3 feature builder for CPI (extends champion CPI features with v3 legs)
# ---------------------------------------------------------------------------

def _build_cpi_features_v3(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    release_type: str,
    ref_month: date | pd.Timestamp | None,
    knowable_series_fn,
    last_n_mom_lags_fn,
    last_n_rate_lags_fn,
) -> tuple[dict[str, float | None], dict]:
    """Build v3 CPI feature dict: champion features + ppi_fes_mom_lag1 + dollar_mom.

    Delegates to the champion's build_cpi_features for shared legs, then appends
    the two v3-specific legs. PIT injection pattern identical to champion.

    Returns (features_dict, provenance_dict).
    """
    # Get champion features (own lags + sticky/median/flex/ppi_fis + gasoline + shelter)
    from engine.release_components_cpi import build_cpi_features as _build_cpi_champ
    feats, prov = _build_cpi_champ(
        asof, vintages, root,
        release_type=release_type,
        ref_month=ref_month,
        knowable_series_fn=knowable_series_fn,
        last_n_mom_lags_fn=last_n_mom_lags_fn,
        last_n_rate_lags_fn=last_n_rate_lags_fn,
    )

    # v3 additional leg: PPIFES MoM lag-1
    feats["ppi_fes_mom_lag1"] = _build_ppifes_mom_lag1(
        asof, root, vintages, knowable_series_fn
    )
    if feats["ppi_fes_mom_lag1"] is None:
        prov.setdefault("absent_legs", []).append("ppi_fes_mom_lag1")

    # v3 additional leg: dollar_mom (DTWEXBGS monthly avg MoM)
    feats["dollar_mom"] = _build_dollar_mom(asof, root)
    if feats["dollar_mom"] is None:
        prov.setdefault("absent_legs", []).append("dollar_mom")

    # Mark additional v3 legs as revision_optimistic
    prov.setdefault("revision_optimistic_legs", [])
    for leg in ("ppi_fes_mom_lag1", "dollar_mom"):
        if leg not in prov["revision_optimistic_legs"]:
            prov["revision_optimistic_legs"].append(leg)

    return feats, prov


# ---------------------------------------------------------------------------
# V3 feature builder for NFP (extends champion NFP features with dollar_mom)
# ---------------------------------------------------------------------------

def _build_nfp_features_v3(
    asof: date,
    ref_month: date,
    vintages: pd.DataFrame,
    root: Path,
    knowable_series_fn,
    survey_week_claims_fn,
) -> tuple[dict[str, float | None], dict]:
    """Build v3 NFP feature dict: champion features (incl. adp_change) + dollar_mom.

    Returns (features_dict, provenance_dict).
    """
    from engine.release_components_nfp import build_nfp_features as _build_nfp_champ
    feats, prov = _build_nfp_champ(
        asof, ref_month, vintages, root,
        knowable_series_fn=knowable_series_fn,
        survey_week_claims_fn=survey_week_claims_fn,
    )

    # v3 additional leg: dollar_mom
    feats["dollar_mom"] = _build_dollar_mom(asof, root)
    if feats["dollar_mom"] is None:
        prov.setdefault("absent_legs", []).append("dollar_mom")

    prov.setdefault("revision_optimistic_legs", [])
    if "dollar_mom" not in prov["revision_optimistic_legs"]:
        prov["revision_optimistic_legs"].append("dollar_mom")

    return feats, prov


# ---------------------------------------------------------------------------
# Core v3 model: PCA-Ridge
# ---------------------------------------------------------------------------

def _pca_ridge_fit_predict(
    X_train: np.ndarray,
    y_train: np.ndarray,
    x_pred: np.ndarray,
    n_components: int = 3,
    lam: float = RIDGE_LAMBDA,
) -> float:
    """PCA top-n_components via SVD then ridge on [factors + naive_anchor + bias].

    X_train: (m, p) z-scored training matrix (complete-case, NaN-free).
    y_train: (m,) training targets.
    x_pred: (p,) z-scored prediction row.
    n_components: number of PCA factors (1-3).
    lam: ridge lambda.

    Returns scalar point prediction.
    """
    m, p = X_train.shape
    k = min(n_components, p, m)
    if k == 0:
        # Degenerate: return training mean
        return float(np.mean(y_train)) if len(y_train) > 0 else 0.0

    # SVD of training matrix: X = U * S * Vt
    # Use full_matrices=False for economy SVD
    U, S, Vt = np.linalg.svd(X_train, full_matrices=False)
    # Top-k factor scores for training: F = U[:, :k] * S[:k]  (equivalent to X @ Vt[:k].T)
    F_train = U[:, :k] * S[:k]   # (m, k)
    # Factor score for prediction row
    f_pred = x_pred @ Vt[:k, :].T  # (k,)

    # Naive anchor = first feature (own-lag-1, z-scored) — index 0 by construction
    naive_anchor_train = X_train[:, 0].reshape(-1, 1)  # (m, 1) z-scored lag-1
    naive_anchor_pred = float(x_pred[0])               # scalar

    # Design matrix: [factors | naive_anchor | bias]
    ones_tr = np.ones((m, 1))
    A_train = np.hstack([F_train, naive_anchor_train, ones_tr])  # (m, k+2)
    a_pred = np.append(f_pred, [naive_anchor_pred, 1.0])          # (k+2,)

    # Closed-form ridge: beta = (A'A + lam*I)^{-1} A'y
    AtA = A_train.T @ A_train
    AtA_reg = AtA + lam * np.eye(A_train.shape[1])
    Aty = A_train.T @ y_train
    try:
        beta = np.linalg.solve(AtA_reg, Aty)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(AtA_reg, Aty, rcond=None)[0]

    return float(a_pred @ beta)


# ---------------------------------------------------------------------------
# Walk-forward for v3 (mirrors champion's _walk_forward but uses PCA-Ridge head)
# ---------------------------------------------------------------------------

def _walk_forward_v3(
    records: list[dict],
    feature_names: list[str],
    target_key: str,
    min_obs: int = MIN_TRAIN_OBS,
    n_components: int = 3,
) -> list[dict]:
    """Expanding-window walk-forward with PCA-Ridge model head.

    Same structure as champion's _walk_forward; model head differs.
    Returns list of result dicts with keys: idx, result_pos, predicted, actual,
    baseline_naive, baseline_trailing3m, baseline_ar3, n_train, n_features_used,
    input_completeness.
    """
    results = []
    p = len(feature_names)

    for i in range(len(records)):
        if i < min_obs:
            continue
        train_recs = records[:i]
        pred_rec = records[i]
        actual = pred_rec.get(target_key)
        if actual is None or (isinstance(actual, float) and np.isnan(actual)):
            continue

        # Build full feature matrices
        n_tr = len(train_recs)
        X_all = np.full((n_tr, p), np.nan)
        for ii, rec in enumerate(train_recs):
            for jj, fn in enumerate(feature_names):
                v = rec.get(fn)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    X_all[ii, jj] = v
        y_all = np.array(
            [rec.get(target_key, np.nan) for rec in train_recs], dtype=float
        )

        # Drop rows where target is NaN
        valid_target = ~np.isnan(y_all)
        X_all = X_all[valid_target]
        y_all = y_all[valid_target]

        if len(y_all) < min_obs:
            continue

        # Prediction row features
        pred_features = np.array(
            [pred_rec.get(fn) if pred_rec.get(fn) is not None else np.nan
             for fn in feature_names],
            dtype=float,
        )
        n_present = int(np.sum(~np.isnan(pred_features)))
        input_completeness = n_present / p if p > 0 else 0.0

        # Complete-case: only features available in pred row
        pred_avail_mask = ~np.isnan(pred_features)
        if pred_avail_mask.any():
            X_sel = X_all[:, pred_avail_mask]
            row_complete = ~np.any(np.isnan(X_sel), axis=1)
            X_cc = X_sel[row_complete]
            y_cc = y_all[row_complete]
            x_pred_raw = pred_features[pred_avail_mask]
            n_features_used = int(pred_avail_mask.sum())
        else:
            X_cc = np.empty((0, 0))
            y_cc = np.empty(0)
            x_pred_raw = np.empty(0)
            n_features_used = 0

        # Baselines (use full target history)
        naive = float(y_all[-1]) if len(y_all) > 0 else np.nan
        trailing_3m = (
            float(np.mean(y_all[-3:])) if len(y_all) >= 3
            else (float(np.mean(y_all)) if len(y_all) > 0 else np.nan)
        )

        # AR3 baseline: ridge on own lags only (first 3 feature names)
        ar3_feat_set = set(feature_names[:3])
        ar3_pred_avail = np.array(
            [(fn in ar3_feat_set) and not np.isnan(pred_features[j])
             for j, fn in enumerate(feature_names)],
            dtype=bool,
        )
        ar3_pred = naive  # default
        if ar3_pred_avail.any():
            X_ar3_sel = X_all[:, ar3_pred_avail]
            ar3_row_ok = ~np.any(np.isnan(X_ar3_sel), axis=1)
            X_ar3 = X_ar3_sel[ar3_row_ok]
            y_ar3 = y_all[ar3_row_ok]
            x_ar3_pred = pred_features[ar3_pred_avail]
            if X_ar3.shape[1] > 0 and len(y_ar3) >= min_obs:
                # Simple ridge (no PCA) for AR3 baseline — same as champion
                try:
                    mean_ar3 = np.nanmean(X_ar3, axis=0)
                    std_ar3 = np.nanstd(X_ar3, axis=0, ddof=1)
                    std_ar3[std_ar3 == 0] = 1.0
                    Xz_ar3 = (X_ar3 - mean_ar3) / std_ar3
                    xz_ar3_pred = (x_ar3_pred - mean_ar3) / std_ar3
                    ones_ar3 = np.ones((len(Xz_ar3), 1))
                    Xa_ar3 = np.hstack([Xz_ar3, ones_ar3])
                    xa_pred_ar3 = np.append(xz_ar3_pred, 1.0)
                    AtA_ar3 = Xa_ar3.T @ Xa_ar3 + RIDGE_LAMBDA * np.eye(Xa_ar3.shape[1])
                    Aty_ar3 = Xa_ar3.T @ y_ar3
                    beta_ar3 = np.linalg.solve(AtA_ar3, Aty_ar3)
                    ar3_pred = float(xa_pred_ar3 @ beta_ar3)
                except Exception:
                    ar3_pred = naive

        # Main v3 PCA-Ridge model
        if n_features_used > 0 and len(y_cc) >= min_obs:
            # Z-score using training rows
            mean_k = np.nanmean(X_cc, axis=0)
            std_k = np.nanstd(X_cc, axis=0, ddof=1)
            std_k[std_k == 0] = 1.0
            Z_cc = (X_cc - mean_k) / std_k
            z_pred = (x_pred_raw - mean_k) / std_k
            k = min(n_components, n_features_used, len(y_cc))
            try:
                ridge_pred = _pca_ridge_fit_predict(Z_cc, y_cc, z_pred, n_components=k)
            except Exception as e:
                log.debug("v3 PCA-ridge failed at step %d: %s", i, e)
                ridge_pred = naive
        else:
            ridge_pred = naive

        results.append({
            "idx": i,
            "result_pos": len(results),
            "predicted": ridge_pred,
            "actual": float(actual),
            "baseline_naive": naive,
            "baseline_trailing3m": trailing_3m,
            "baseline_ar3": ar3_pred,
            "n_train": len(y_cc) if n_features_used > 0 else len(y_all),
            "n_features_used": n_features_used,
            "input_completeness": input_completeness,
        })

    return results


# ---------------------------------------------------------------------------
# Full walk-forward runners (used by backtest)
# ---------------------------------------------------------------------------

def run_walk_forward_v3_cpi(
    release: str,
    root: str | Path,
) -> dict:
    """Run v3_factor walk-forward for a CPI target.

    release: 'cpi_headline' | 'cpi_core'
    Returns dict with results, feature_names, metadata.
    """
    from engine.release_forecast import (
        load_vintages,
        knowable_series,
        _last_n_mom_lags,  # private helper — replicated comment per spec
        _last_n_rate_lags,
    )

    root = Path(root)
    vintages = load_vintages(root)

    feature_names = (
        _CPI_HL_FEATURES if release == "cpi_headline" else _CPI_CORE_FEATURES
    )
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"

    all_series = knowable_series(vintages, own_series, date(2099, 1, 1))
    mom_series = all_series.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)

    records = []
    for _, row in mom_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"]
        try:
            feats, _ = _build_cpi_features_v3(
                step_asof, vintages, root,
                release_type=release,
                ref_month=ref_month,
                knowable_series_fn=knowable_series,
                last_n_mom_lags_fn=_last_n_mom_lags,
                last_n_rate_lags_fn=_last_n_rate_lags,
            )
        except Exception as e:
            log.debug("v3 CPI feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = float(row["mom"])
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    wf_results = _walk_forward_v3(records, feature_names, "target")

    for r in wf_results:
        meta = records[r["idx"]]
        r["period"] = meta.get("period")
        r["release_date"] = meta.get("release_date")

    return {
        "results": wf_results,
        "feature_names": feature_names,
        "metadata": {
            "release": release,
            "model": "v3_factor",
            "n_records": len(records),
        },
    }


def run_walk_forward_v3_nfp(root: str | Path) -> dict:
    """Run v3_factor walk-forward for NFP.

    Returns dict with results, feature_names, metadata.
    """
    from engine.release_forecast import (
        load_vintages,
        knowable_series,
        _survey_week_claims,  # private helper — replicated comment per spec
    )

    root = Path(root)
    vintages = load_vintages(root)
    feature_names = _NFP_FEATURES

    all_series = knowable_series(vintages, "PAYEMS", date(2099, 1, 1))
    diff_series = all_series.copy()
    diff_series["change"] = diff_series["value"].diff()
    diff_series = diff_series.dropna(subset=["change"]).reset_index(drop=True)

    records = []
    for _, row in diff_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"].date()
        try:
            feats, _ = _build_nfp_features_v3(
                step_asof, ref_month, vintages, root,
                knowable_series_fn=knowable_series,
                survey_week_claims_fn=_survey_week_claims,
            )
        except Exception as e:
            log.debug("v3 NFP feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = float(row["change"])
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    wf_results = _walk_forward_v3(records, feature_names, "target")

    for r in wf_results:
        meta = records[r["idx"]]
        r["period"] = meta.get("period")
        r["release_date"] = meta.get("release_date")

    return {
        "results": wf_results,
        "feature_names": feature_names,
        "metadata": {
            "release": "nfp",
            "model": "v3_factor",
            "n_records": len(records),
        },
    }


# ---------------------------------------------------------------------------
# Single-date projection API (mirrors champion's project_release)
# ---------------------------------------------------------------------------

def project_release_v3(
    release: str,
    asof: date,
    root: str | Path,
    ref_month: date | None = None,
    *,
    period: str | None = None,
    release_date: date | None = None,
) -> dict:
    """Generate a v3_factor point-in-time projection for a macro release.

    Parameters
    ----------
    release : str
        One of 'cpi_headline', 'cpi_core', 'nfp'.
    asof : date
        Decision date (the day before the target release is published).
    root : str | Path
        Repository root.
    ref_month : date | None
        Reference month (CPI only). None derives from last knowable print.
    period : str | None
        'YYYY-MM' for schema ID construction.
    release_date : date | None
        Scheduled release date for horizon_days.

    Returns dict matching champion schema + model='v3_factor'.
    display_only=True, authority=False.
    """
    from engine.release_forecast import (
        load_vintages,
        knowable_series,
        _last_n_mom_lags,
        _last_n_rate_lags,
        _survey_week_claims,
        _compute_quantiles,
        _wilson,
        make_release_id,
        make_prediction_id,
        compute_inputs_hash,
        MIN_QUANTILE_OBS as _MQO,
    )

    root = Path(root)
    vintages = load_vintages(root)

    if release in ("cpi_headline", "cpi_core"):
        result = _project_cpi_v3(
            release, asof, vintages, root, ref_month=ref_month,
            knowable_series_fn=knowable_series,
            last_n_mom_lags_fn=_last_n_mom_lags,
            last_n_rate_lags_fn=_last_n_rate_lags,
            compute_quantiles_fn=_compute_quantiles,
        )
    elif release == "nfp":
        result = _project_nfp_v3(
            asof, vintages, root,
            knowable_series_fn=knowable_series,
            survey_week_claims_fn=_survey_week_claims,
            compute_quantiles_fn=_compute_quantiles,
        )
    else:
        raise ValueError(
            f"v3_factor supports 'cpi_headline', 'cpi_core', 'nfp'. Got: {release!r}"
        )

    # Schema v2 fields (period + IDs)
    _period = period
    if _period is None:
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

    if _period is not None:
        result["release_id"] = make_release_id(release, _period)
        result["prediction_id"] = make_prediction_id(result["release_id"], asof.isoformat())

    if release_date is not None:
        result["horizon_days"] = (release_date - asof).days

    return result


def _project_cpi_v3(
    release: str,
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | None,
    *,
    knowable_series_fn,
    last_n_mom_lags_fn,
    last_n_rate_lags_fn,
    compute_quantiles_fn,
) -> dict:
    """Internal: v3 CPI projection for a single asof date."""
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
    feature_names = _CPI_HL_FEATURES if release == "cpi_headline" else _CPI_CORE_FEATURES

    all_series = knowable_series_fn(vintages, own_series, asof)
    if len(all_series) < 2:
        return _empty_v3(release, asof, "insufficient_data")

    mom_series = all_series.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)

    # Build records for walk-forward
    records = []
    for _, row in mom_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_m = row["period"]
        try:
            feats, _ = _build_cpi_features_v3(
                step_asof, vintages, root,
                release_type=release,
                ref_month=ref_m,
                knowable_series_fn=knowable_series_fn,
                last_n_mom_lags_fn=last_n_mom_lags_fn,
                last_n_rate_lags_fn=last_n_rate_lags_fn,
            )
        except Exception as e:
            log.debug("v3 CPI feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = float(row["mom"])
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_v3(release, asof, "insufficient_history")

    wf_results = _walk_forward_v3(records, feature_names, "target")
    if not wf_results:
        return _empty_v3(release, asof, "no_walk_forward_results")

    # Current prediction
    if ref_month is None:
        ref_month = (
            (pd.Timestamp(mom_series["period"].iloc[-1]).to_period("M") + 1)
            .to_timestamp()
            .date()
        )
    feats, prov = _build_cpi_features_v3(
        asof, vintages, root,
        release_type=release,
        ref_month=ref_month,
        knowable_series_fn=knowable_series_fn,
        last_n_mom_lags_fn=last_n_mom_lags_fn,
        last_n_rate_lags_fn=last_n_rate_lags_fn,
    )

    # Build design matrices for current prediction
    p = len(feature_names)
    n_tr = len(records)
    X_all = np.full((n_tr, p), np.nan)
    for ii, rec in enumerate(records):
        for jj, fn in enumerate(feature_names):
            v = rec.get(fn)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                X_all[ii, jj] = v
    y_all = np.array([rec["target"] for rec in records], dtype=float)
    valid_target = ~np.isnan(y_all)
    X_all = X_all[valid_target]
    y_all = y_all[valid_target]

    pred_features = np.array(
        [feats.get(fn) if feats.get(fn) is not None else np.nan
         for fn in feature_names],
        dtype=float,
    )
    n_present = int(np.sum(~np.isnan(pred_features)))
    input_completeness = n_present / p if p > 0 else 0.0

    pred_avail_mask = ~np.isnan(pred_features)
    point = None
    if pred_avail_mask.any():
        X_sel = X_all[:, pred_avail_mask]
        row_complete = ~np.any(np.isnan(X_sel), axis=1)
        X_cc = X_sel[row_complete]
        y_cc = y_all[row_complete]
        x_pred_raw = pred_features[pred_avail_mask]
        n_features_used = int(pred_avail_mask.sum())
        if n_features_used > 0 and len(y_cc) >= MIN_TRAIN_OBS:
            mean_k = np.nanmean(X_cc, axis=0)
            std_k = np.nanstd(X_cc, axis=0, ddof=1)
            std_k[std_k == 0] = 1.0
            Z_cc = (X_cc - mean_k) / std_k
            z_pred = (x_pred_raw - mean_k) / std_k
            k = min(3, n_features_used, len(y_cc))
            try:
                point = _pca_ridge_fit_predict(Z_cc, y_cc, z_pred, n_components=k)
            except Exception as e:
                log.debug("v3 CPI final prediction failed: %s", e)

    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])
    quantiles = compute_quantiles_fn(errors, point if point is not None else 0.0)

    naive = float(mom_series["mom"].iloc[-1]) if len(mom_series) > 0 else None
    trailing_3m = (
        float(mom_series["mom"].iloc[-3:].mean()) if len(mom_series) >= 3 else naive
    )

    sigma, tag, sigma_scale_pp = None, None, None
    if point is not None and naive is not None and len(errors) >= MIN_QUANTILE_OBS:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
            sigma_scale_pp = round(err_std, 4)
            sigma = round((point - naive) / err_std, 4)
            tag = (
                "inline" if abs(sigma) <= INLINE_BAND_SIGMA
                else ("hotter" if sigma > INLINE_BAND_SIGMA else "cooler")
            )

    return {
        "release": release,
        "asof": asof.isoformat(),
        "model": "v3_factor",
        "inputs_hash": compute_inputs_hash(feats),
        "point": round(point, 4) if point is not None else None,
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "confidence": None,
        "confidence_components": None,
        "components": None,
        "confidence_v2": None,
        "confidence_components_v2": None,
        "input_completeness": round(input_completeness, 4),
        "n_pca_factors": min(3, n_present) if n_present > 0 else 0,
        "benchmark_set": {
            "naive_prior": round(naive, 4) if naive is not None else None,
            "trailing_3m": round(trailing_3m, 4) if trailing_3m is not None else None,
            "ar_model": None,
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


def _project_nfp_v3(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    *,
    knowable_series_fn,
    survey_week_claims_fn,
    compute_quantiles_fn,
) -> dict:
    """Internal: v3 NFP projection for a single asof date."""
    feature_names = _NFP_FEATURES

    all_series = knowable_series_fn(vintages, "PAYEMS", asof)
    if len(all_series) < 2:
        return _empty_v3("nfp", asof, "insufficient_data")

    diff_series = all_series.copy()
    diff_series["change"] = diff_series["value"].diff()
    diff_series = diff_series.dropna(subset=["change"]).reset_index(drop=True)

    records = []
    for _, row in diff_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month_step = row["period"].date()
        try:
            feats, _ = _build_nfp_features_v3(
                step_asof, ref_month_step, vintages, root,
                knowable_series_fn=knowable_series_fn,
                survey_week_claims_fn=survey_week_claims_fn,
            )
        except Exception as e:
            log.debug("v3 NFP feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = float(row["change"])
        rec["period"] = row["period"]
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_v3("nfp", asof, "insufficient_history")

    wf_results = _walk_forward_v3(records, feature_names, "target")
    if not wf_results:
        return _empty_v3("nfp", asof, "no_walk_forward_results")

    # Current features
    target_ref_month = (
        (pd.Timestamp(all_series["period"].iloc[-1]).to_period("M") + 1)
        .to_timestamp()
        .date()
    )
    feats, prov = _build_nfp_features_v3(
        asof, target_ref_month, vintages, root,
        knowable_series_fn=knowable_series_fn,
        survey_week_claims_fn=survey_week_claims_fn,
    )

    p = len(feature_names)
    n_tr = len(records)
    X_all = np.full((n_tr, p), np.nan)
    for ii, rec in enumerate(records):
        for jj, fn in enumerate(feature_names):
            v = rec.get(fn)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                X_all[ii, jj] = v
    y_all = np.array([rec["target"] for rec in records], dtype=float)
    valid_target = ~np.isnan(y_all)
    X_all = X_all[valid_target]
    y_all = y_all[valid_target]

    pred_features = np.array(
        [feats.get(fn) if feats.get(fn) is not None else np.nan
         for fn in feature_names],
        dtype=float,
    )
    n_present = int(np.sum(~np.isnan(pred_features)))
    input_completeness = n_present / p if p > 0 else 0.0

    pred_avail_mask = ~np.isnan(pred_features)
    point = None
    n_features_used = 0
    if pred_avail_mask.any():
        X_sel = X_all[:, pred_avail_mask]
        row_complete = ~np.any(np.isnan(X_sel), axis=1)
        X_cc = X_sel[row_complete]
        y_cc = y_all[row_complete]
        x_pred_raw = pred_features[pred_avail_mask]
        n_features_used = int(pred_avail_mask.sum())
        if n_features_used > 0 and len(y_cc) >= MIN_TRAIN_OBS:
            mean_k = np.nanmean(X_cc, axis=0)
            std_k = np.nanstd(X_cc, axis=0, ddof=1)
            std_k[std_k == 0] = 1.0
            Z_cc = (X_cc - mean_k) / std_k
            z_pred = (x_pred_raw - mean_k) / std_k
            k = min(3, n_features_used, len(y_cc))
            try:
                point = _pca_ridge_fit_predict(Z_cc, y_cc, z_pred, n_components=k)
            except Exception as e:
                log.debug("v3 NFP final prediction failed: %s", e)

    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])
    quantiles = compute_quantiles_fn(errors, point if point is not None else 0.0)

    y_changes = diff_series["change"].values
    naive = float(y_changes[-1]) if len(y_changes) > 0 else None
    trailing_3m = float(np.mean(y_changes[-3:])) if len(y_changes) >= 3 else naive

    sigma, tag, sigma_scale_pp = None, None, None
    if point is not None and naive is not None and len(errors) >= MIN_QUANTILE_OBS:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
            sigma_scale_pp = round(err_std, 4)
            sigma = round((point - naive) / err_std, 4)
            tag = (
                "inline" if abs(sigma) <= INLINE_BAND_SIGMA
                else ("hotter" if sigma > INLINE_BAND_SIGMA else "cooler")
            )

    return {
        "release": "nfp",
        "asof": asof.isoformat(),
        "model": "v3_factor",
        "inputs_hash": compute_inputs_hash(feats),
        "point": round(point, 2) if point is not None else None,
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "confidence": None,
        "confidence_components": None,
        "input_completeness": round(input_completeness, 4),
        "n_pca_factors": min(3, n_present) if n_present > 0 else 0,
        "benchmark_set": {
            "naive_prior": round(naive, 2) if naive is not None else None,
            "trailing_3m": round(trailing_3m, 2) if trailing_3m is not None else None,
            "ar_model": None,
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


def compute_inputs_hash(features: dict[str, float | None]) -> str:
    """Reuse pattern from champion — SHA256 of sorted non-null feature pairs."""
    import hashlib
    import json
    used = sorted(
        (k, round(v, 10) if v is not None else None)
        for k, v in features.items()
        if v is not None
    )
    canonical = json.dumps(used, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _empty_v3(release: str, asof: date, reason: str) -> dict:
    """Null projection dict for v3_factor."""
    return {
        "release": release,
        "asof": asof.isoformat(),
        "model": "v3_factor",
        "point": None,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "confidence": None,
        "confidence_components": None,
        "input_completeness": 0.0,
        "n_pca_factors": 0,
        "benchmark_set": {
            "naive_prior": None, "trailing_3m": None, "ar_model": None,
            "cleveland_nowcast": None, "market_implied": None,
        },
        "surprise_skew": {
            "sigma": None, "sigma_scale_pp": None, "tag": None,
            "inline_band": INLINE_BAND_SIGMA,
        },
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
