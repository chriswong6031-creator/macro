"""NFP First→Third Revision-Direction Model — Track R (MRI-R37, W11-D).

LEAF · DISPLAY-ONLY. Returns plain data dicts only. No authority flags, no
signals, no scores. Never touches point/interval/skew in the main NFP projection.

Specification: research/release_forecast/PREREG_NFP_REVISION_V1.md (frozen 2026-07-10).

Model:
  Target: sign(third_print_MoM_change[T] - first_print_MoM_change[T])
  Features: fp_surprise_vs_AR1, sin_month, cos_month, icsa_4m_survey_week_change
  Estimator: ridge(λ=1.0, numpy closed-form) on z-scored features → sign
  Walk-forward: expanding window, MIN_TRAIN_OBS=60, COVID excluded from era stats
  Kill: Wilson LB of walk-forward hit-rate <= majority-class base rate → lean="none"

Data:
  Multi-vintage PAYEMS store (output_type=2):
    data/fred_vintage/payems_all_vintages.parquet
  Fallback when store absent: first→cumulative revision approximation using
    existing output_type=4 vintages.parquet, labeled basis='first_to_cumulative_fallback'.

Pure numpy/pandas only. No sklearn, statsmodels, scipy.stats (house law).
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
# Constants (frozen per PREREG_NFP_REVISION_V1.md)
# ---------------------------------------------------------------------------
RIDGE_LAMBDA = 1.0
MIN_TRAIN_OBS = 60
COVID_MONTHS = {(2020, m) for m in range(3, 7)}   # 2020-03 to 2020-06 inclusive
STRENGTH_THRESHOLD = 0.10   # dead-band: |y_hat| < threshold -> lean="none"
AR1_MIN_OBS = 12            # minimum obs for AR(1) baseline
# Descriptive level-bias annotation constants (§5.2) — sourced from §12.3 MRI-R37
_EXPANSION_CUMULATIVE_REVISION_K = 216    # mean cumulative LEVEL revision during expansions
_CONTRACTION_CUMULATIVE_REVISION_K = -262 # mean cumulative LEVEL revision during contractions

# ---------------------------------------------------------------------------
# Multi-vintage PAYEMS store path helpers
# ---------------------------------------------------------------------------

def _mv_path(root: str | Path) -> Path:
    return Path(root) / "data" / "fred_vintage" / "payems_all_vintages.parquet"


def _initial_vintage_path(root: str | Path) -> Path:
    return Path(root) / "data" / "fred_vintage" / "vintages.parquet"


def load_multi_vintage(root: str | Path) -> tuple[pd.DataFrame, str]:
    """Load PAYEMS vintage store. Returns (df, basis).

    Prefers the multi-vintage (output_type=2) store. Falls back to the
    output_type=4 initial-release store if multi-vintage is absent.

    Returns
    -------
    df : DataFrame with columns period, realtime_start, realtime_end, value
    basis : 'first_to_third' | 'first_to_cumulative_fallback'
    """
    mv = _mv_path(root)
    if mv.exists():
        df = pd.read_parquet(mv)
        for col in ("period", "realtime_start", "realtime_end"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        # Filter to PAYEMS periods only (the file is PAYEMS-only, but be safe)
        return df, "first_to_third"

    iv = _initial_vintage_path(root)
    if iv.exists():
        df = pd.read_parquet(iv)
        for col in ("period", "realtime_start", "realtime_end"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        # Filter to PAYEMS; this store has series column
        if "series" in df.columns:
            df = df[df["series"] == "PAYEMS"].drop(columns=["series"], errors="ignore")
        log.warning(
            "release_revision_model: multi-vintage PAYEMS store absent; "
            "using first_to_cumulative_fallback from output_type=4 store"
        )
        return df, "first_to_cumulative_fallback"

    log.warning("release_revision_model: no PAYEMS vintage store found — returning empty")
    return pd.DataFrame(
        columns=["period", "realtime_start", "realtime_end", "value"]
    ), "first_to_cumulative_fallback"


# ---------------------------------------------------------------------------
# Vintage extraction helpers
# ---------------------------------------------------------------------------

def _first_print_value(df: pd.DataFrame, period: pd.Timestamp) -> float | None:
    """First-published value for a period (earliest realtime_start)."""
    sub = df[df["period"] == period]
    if sub.empty:
        return None
    row = sub.sort_values("realtime_start").iloc[0]
    v = row["value"]
    return float(v) if pd.notna(v) else None


def _nth_print_value(
    df: pd.DataFrame, period: pd.Timestamp, n: int
) -> tuple[float | None, pd.Timestamp | None]:
    """n-th released value for a period (1-indexed by realtime_start order).

    Returns (value, realtime_start) or (None, None).
    """
    sub = df[df["period"] == period].sort_values("realtime_start")
    if len(sub) < n:
        return None, None
    row = sub.iloc[n - 1]
    v = row["value"]
    rt = row["realtime_start"]
    return (float(v) if pd.notna(v) else None), (rt if pd.notna(rt) else None)


def _latest_value(df: pd.DataFrame, period: pd.Timestamp) -> float | None:
    """Latest available value for a period (latest realtime_start)."""
    sub = df[df["period"] == period]
    if sub.empty:
        return None
    row = sub.sort_values("realtime_start").iloc[-1]
    v = row["value"]
    return float(v) if pd.notna(v) else None


def _mom_change(current_val: float | None, prior_val: float | None) -> float | None:
    """PAYEMS MoM change in thousands: current - prior."""
    if current_val is None or prior_val is None:
        return None
    return current_val - prior_val


# ---------------------------------------------------------------------------
# Target construction: first→third revision pairs
# ---------------------------------------------------------------------------

def _value_at_vintage(df: pd.DataFrame, period: pd.Timestamp, rt: pd.Timestamp) -> float | None:
    """Value for `period` as it was known at vintage date `rt`.

    Returns the value from the row whose realtime_start <= rt <= realtime_end.
    If no exact row exists, returns the latest row with realtime_start <= rt.
    """
    sub = df[df["period"] == period].copy()
    if sub.empty:
        return None
    # Rows where the vintage rt falls within [realtime_start, realtime_end]
    if "realtime_end" in sub.columns:
        exact = sub[(sub["realtime_start"] <= rt) & (sub["realtime_end"] >= rt)]
        if not exact.empty:
            v = exact.sort_values("realtime_start").iloc[-1]["value"]
            return float(v) if pd.notna(v) else None
    # Fallback: latest row with realtime_start <= rt
    known = sub[sub["realtime_start"] <= rt]
    if known.empty:
        return None
    v = known.sort_values("realtime_start").iloc[-1]["value"]
    return float(v) if pd.notna(v) else None


def build_revision_target_df(
    df: pd.DataFrame,
    basis: str,
) -> pd.DataFrame:
    """Build the revision-target DataFrame from the PAYEMS vintage store.

    For each period T (monthly since ~1997, where the Employment Situation
    release is captured in ALFRED), computes:
      - first_print_mom: MoM change at first release
        = PAYEMS[T, vint=rt1] - PAYEMS[T-1, vint=rt1]
      - third_print_mom: MoM change at third release (or latest for fallback)
        = PAYEMS[T, vint=rt3] - PAYEMS[T-1, vint=rt3]
      - revision: third_mom - first_mom
      - target: sign(revision)
      - first_release_date: rt1
      - decision_date: rt1 - 1 day

    For 'first_to_third' basis: rt3 = realtime_start of 3rd release of T.
    For 'first_to_cumulative_fallback': rt3 = latest realtime_start for T.

    IMPORTANT: Only includes periods T where T's FIRST release was on or after
    1997-01-01 (when ALFRED coverage begins reliably), i.e., where T is a
    "fresh" release in the archive.

    Returns a DataFrame sorted by first_release_date.
    """
    # Index by (period, realtime_start) for fast lookups
    df_sorted = df.sort_values(["period", "realtime_start"])

    # For each period, collect release dates in order
    release_dates_by_period: dict[pd.Timestamp, list[pd.Timestamp]] = {}
    for period, group in df_sorted.groupby("period"):
        release_dates_by_period[pd.Timestamp(period)] = sorted(
            group["realtime_start"].dropna().tolist()
        )

    # The ALFRED realtime archive starts 1997-01-01; the bulk 1997-01-01 vintage
    # captures all pre-1997 history in one batch (same realtime_start for all early periods).
    # We only include periods where the first release was a GENUINE new release:
    # - The period itself is recent enough to have been captured in real time
    # - The first_release_date is > 1997-01-01 (strictly after the bulk import date)
    # This means the backtest starts from the February 1997 Employment Situation
    # report (released ~1997-03-07) which covered Jan 1997 data.
    archive_start = pd.Timestamp("1997-01-02")  # strictly after bulk-import date

    rows = []
    for period, rt_dates in sorted(release_dates_by_period.items()):
        if not rt_dates:
            continue
        rt1 = rt_dates[0]  # first release date

        # Only include periods first-released WITHIN the archive window
        if rt1 < archive_start:
            continue

        # Need at least 3 releases for first_to_third; at least 1 for fallback
        if basis == "first_to_third" and len(rt_dates) < 3:
            continue

        # Prior period for MoM
        prior_period = period - pd.DateOffset(months=1)
        if prior_period not in release_dates_by_period:
            continue

        # First MoM: value at vintage rt1
        v_T_1st = _value_at_vintage(df, period, rt1)
        v_Tm1_1st = _value_at_vintage(df, prior_period, rt1)
        if v_T_1st is None or v_Tm1_1st is None:
            continue
        first_mom = v_T_1st - v_Tm1_1st

        # Third MoM (or cumulative)
        if basis == "first_to_third":
            rt3 = rt_dates[2]
        else:
            rt3 = rt_dates[-1]

        v_T_3rd = _value_at_vintage(df, period, rt3)
        v_Tm1_3rd = _value_at_vintage(df, prior_period, rt3)
        if v_T_3rd is None or v_Tm1_3rd is None:
            continue
        third_mom = v_T_3rd - v_Tm1_3rd

        revision = third_mom - first_mom
        if abs(revision) < 1e-9:
            target_sign = 0
        else:
            target_sign = 1 if revision > 0 else -1

        rows.append({
            "period": period,
            "first_release_date": rt1,
            "third_release_date": rt3,
            "decision_date": rt1 - pd.Timedelta(days=1),
            "first_print_mom": first_mom,
            "third_print_mom": third_mom,
            "revision": revision,
            "target": target_sign,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "period", "first_release_date", "third_release_date", "decision_date",
            "first_print_mom", "third_print_mom", "revision", "target"
        ])
    return pd.DataFrame(rows).sort_values("first_release_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Ridge helpers (numpy only — same pattern as engine/release_forecast.py)
# ---------------------------------------------------------------------------

def _ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    n, p = X.shape
    XtX_reg = X.T @ X + lam * np.eye(p)
    Xty = X.T @ y
    try:
        beta = np.linalg.solve(XtX_reg, Xty)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(XtX_reg, Xty, rcond=None)[0]
    return beta


def _zscore_train(X_train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = X_train.shape[0] if X_train.ndim > 1 else len(X_train)
    p = X_train.shape[1] if X_train.ndim > 1 else 1
    if n == 0:
        # Empty training set: return neutral mean=0, std=1
        return np.zeros(p), np.ones(p)
    mean = np.nanmean(X_train, axis=0)
    if n < 2:
        # Cannot compute std with ddof=1 and n=1 — return ones
        return mean, np.ones(p)
    std = np.nanstd(X_train, axis=0, ddof=1)
    std[std == 0] = 1.0
    return mean, std


def _ridge_predict_single(
    X_train: np.ndarray, y_train: np.ndarray, x_pred: np.ndarray
) -> float:
    """Fit ridge on training data, return scalar prediction for x_pred (1D)."""
    mean, std = _zscore_train(X_train)
    Xz_tr = (X_train - mean) / std
    x_pred_z = (x_pred - mean) / std
    # Append bias
    Xz_aug = np.hstack([Xz_tr, np.ones((len(Xz_tr), 1))])
    x_aug = np.append(x_pred_z, 1.0)
    beta = _ridge_fit(Xz_aug, y_train)
    return float(np.dot(x_aug, beta))


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score 95% CI for hit-rate k/n."""
    if not n:
        return None
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


# ---------------------------------------------------------------------------
# Feature builders
# ---------------------------------------------------------------------------

def _survey_week_icsa(
    vintages: pd.DataFrame,  # output_type=4 initial-print ICSA vintages
    series: str,
    asof: pd.Timestamp,
    ref_month: pd.Timestamp,
) -> float | None:
    """ICSA initial-print for the survey reference week of ref_month.

    Survey reference week = week containing the 12th of ref_month.
    Knowable at asof (realtime_start <= asof).
    """
    sub = vintages[
        (vintages["series"] == series) & (vintages["realtime_start"] <= asof)
    ].copy()
    if sub.empty:
        return None
    # Initial print per period
    sub = (
        sub.sort_values("realtime_start")
        .groupby("period", as_index=False)
        .first()
    )
    sub["period"] = pd.to_datetime(sub["period"])
    target_12 = pd.Timestamp(ref_month.year, ref_month.month, 12)
    # ICSA period = Saturday of the week; week spans Sat..Fri
    sub["week_end"] = sub["period"] + pd.Timedelta(days=6)
    mask = (sub["period"] <= target_12) & (sub["week_end"] >= target_12)
    hit = sub[mask]
    if hit.empty:
        return None
    return float(hit["value"].mean())


def build_revision_features(
    period: pd.Timestamp,
    decision_date: pd.Timestamp,
    first_print_mom: float,
    mv_df: pd.DataFrame,
    init_vintages: pd.DataFrame | None,
) -> dict[str, float | None]:
    """Build feature dict for Track R at a given decision date.

    Parameters
    ----------
    period : reference month T (we are predicting its revision direction)
    decision_date : D = first_release_date(T) - 1 day
    first_print_mom : the first-print MoM change for period T (in thousands)
    mv_df : PAYEMS multi-vintage DataFrame (for AR1 from first-print series)
    init_vintages : output_type=4 vintages DataFrame (for ICSA)
    """
    # --- Feature 2 & 3: sin/cos month of period T ---
    month = period.month
    sin_month = float(np.sin(2 * np.pi * (month - 1) / 12))
    cos_month = float(np.cos(2 * np.pi * (month - 1) / 12))

    # --- Feature 1: fp_surprise_vs_AR1 ---
    # Compute first-print MoM series from multi-vintage store (knowable at D)
    known = mv_df[mv_df["realtime_start"] <= decision_date].copy()
    # Group by period: take the first (earliest) realtime_start = initial print
    first_prints = (
        known.sort_values("realtime_start")
        .groupby("period", as_index=False)
        .first()[["period", "value"]]
        .sort_values("period")
        .reset_index(drop=True)
    )
    first_prints["period"] = pd.to_datetime(first_prints["period"])

    fp_surprise = None
    if len(first_prints) >= 3:
        # Compute MoM changes from first-print levels
        fp_mom = first_prints.set_index("period")["value"].diff().dropna()
        # Exclude periods > D (shouldn't happen but be safe)
        fp_mom = fp_mom[fp_mom.index < decision_date]

        # The "most recent" first-print MoM (period T-1, the last knowable)
        if len(fp_mom) >= 1:
            last_mom = float(fp_mom.iloc[-1])
            # AR(1) forecast: expanding-window ridge on prior MoM values
            if len(fp_mom) >= AR1_MIN_OBS:
                # Use all but last as training, last as "prediction"
                y_ar = fp_mom.values.astype(float)
                # AR(1): X = y[t-1], y = y[t]
                X_ar = y_ar[:-1].reshape(-1, 1)
                y_ar_train = y_ar[1:]
                if len(X_ar) >= AR1_MIN_OBS - 1:
                    ar1_pred = _ridge_predict_single(
                        X_ar, y_ar_train, np.array([y_ar[-2]])
                    )
                    fp_surprise = last_mom - ar1_pred
                else:
                    # Fallback: use expanding mean
                    ar1_pred = float(np.mean(fp_mom.iloc[:-1]))
                    fp_surprise = last_mom - ar1_pred
            else:
                # Too few obs: use expanding mean
                ar1_pred = float(fp_mom.iloc[:-1].mean()) if len(fp_mom) > 1 else 0.0
                fp_surprise = last_mom - ar1_pred

    # --- Feature 4: icsa_4m_survey_week_change ---
    icsa_4m = None
    if init_vintages is not None and "series" in init_vintages.columns:
        icsa_sub = init_vintages[init_vintages["series"] == "ICSA"]
        if not icsa_sub.empty:
            # survey_week_icsa for period T-1
            prior_1 = period - pd.DateOffset(months=1)
            v_t1 = _survey_week_icsa(init_vintages, "ICSA", decision_date, prior_1)
            # survey_week_icsa for period T-5
            prior_5 = period - pd.DateOffset(months=5)
            v_t5 = _survey_week_icsa(init_vintages, "ICSA", decision_date, prior_5)
            if v_t1 is not None and v_t5 is not None:
                icsa_4m = v_t1 - v_t5

    return {
        "fp_surprise_vs_AR1": fp_surprise,
        "sin_month": sin_month,
        "cos_month": cos_month,
        "icsa_4m_survey_week_change": icsa_4m,
    }


# ---------------------------------------------------------------------------
# Walk-forward engine for sign-target
# ---------------------------------------------------------------------------

def _build_X(
    feature_rows: list[dict[str, float | None]],
    feature_names: list[str],
) -> np.ndarray:
    """Convert list of feature dicts to numpy matrix. NaN for missing."""
    n = len(feature_rows)
    p = len(feature_names)
    X = np.full((n, p), np.nan)
    for i, row in enumerate(feature_rows):
        for j, fn in enumerate(feature_names):
            v = row.get(fn)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                X[i, j] = v
    return X


def run_revision_walk_forward(
    records: list[dict],
    feature_names: list[str] | None = None,
    min_obs: int = MIN_TRAIN_OBS,
) -> list[dict]:
    """Expanding-window walk-forward for sign classification.

    records: list of dicts sorted by first_release_date. Each has:
        period, first_release_date, target (int: +1/-1/0),
        fp_surprise_vs_AR1, sin_month, cos_month, icsa_4m_survey_week_change.

    PIT-compliance: each record may optionally carry ``label_observable_date``
    (a pd.Timestamp) — the date on which the LABEL for that row became
    observable (i.e., the third-print release date, or the cumulative-fallback
    vintage date).  When present, training at fold i is restricted to rows
    whose label had already landed by pred_rec["decision_date"].  This
    eliminates training-label look-ahead: a row whose third print has not yet
    been published cannot serve as a training example at fold i.

    If ``label_observable_date`` is absent for a row (backward-compat), the
    row is treated as always observable (old behaviour).

    Returns list of result dicts (one per step after min_obs training samples).
    """
    if feature_names is None:
        feature_names = [
            "fp_surprise_vs_AR1", "sin_month", "cos_month", "icsa_4m_survey_week_change"
        ]

    results = []
    for i in range(len(records)):
        if i < min_obs:
            continue
        pred_rec = records[i]
        pred_decision = pred_rec.get("decision_date")

        # PIT filter: only include training rows whose label was observable
        # at pred_rec["decision_date"].  Rows that carry no label_observable_date
        # are included unconditionally (backward-compatible).
        if pred_decision is not None:
            train_recs = [
                r for r in records[:i]
                if (
                    r.get("label_observable_date") is None
                    or r["label_observable_date"] <= pred_decision
                )
            ]
        else:
            train_recs = records[:i]
        actual_target = pred_rec.get("target")
        if actual_target is None:
            continue

        # Build training matrices
        X_all = _build_X(train_recs, feature_names)
        y_all = np.array([r.get("target", np.nan) for r in train_recs], dtype=float)

        # Drop rows where target is NaN or 0 (zero-revision steps excluded from training)
        valid = ~np.isnan(y_all) & (y_all != 0)
        X_all = X_all[valid]
        y_all = y_all[valid]

        if len(y_all) < min_obs:
            continue

        # Build prediction feature vector
        x_pred = np.array(
            [pred_rec.get(fn, np.nan) if pred_rec.get(fn) is not None else np.nan
             for fn in feature_names],
            dtype=float,
        )
        # n_present for completeness
        n_present = int(np.sum(~np.isnan(x_pred)))
        input_completeness = n_present / len(feature_names) if feature_names else 0.0

        # Select feature columns available in prediction row
        pred_avail = ~np.isnan(x_pred)
        # Also drop any training column entirely NaN in avail set
        X_avail = X_all[:, pred_avail]
        x_avail = x_pred[pred_avail]

        # Complete-case training (drop rows with NaN in selected cols)
        row_ok = ~np.any(np.isnan(X_avail), axis=1)
        X_tr = X_avail[row_ok]
        y_tr = y_all[row_ok]

        if len(y_tr) < min_obs or len(X_tr[0]) == 0 if X_tr.ndim > 1 and X_tr.shape[1] == 0 else False:
            continue
        if X_tr.shape[1] == 0:
            continue

        # Fit and predict
        y_hat = _ridge_predict_single(X_tr, y_tr, x_avail)

        # Majority class baseline
        n_pos = int(np.sum(y_tr > 0))
        n_neg = int(np.sum(y_tr < 0))
        majority_sign = 1 if n_pos >= n_neg else -1
        majority_base_rate = max(n_pos, n_neg) / len(y_tr) if len(y_tr) > 0 else 0.5

        # Sign of negative fp_surprise baseline (mechanistic)
        fp_surp = pred_rec.get("fp_surprise_vs_AR1")
        sign_neg_fp = int(np.sign(-fp_surp)) if fp_surp is not None and fp_surp != 0 else 0

        results.append({
            "step": i,
            "period": pred_rec.get("period"),
            "first_release_date": pred_rec.get("first_release_date"),
            "actual_target": int(actual_target),
            "y_hat": float(y_hat),
            "predicted_sign": int(np.sign(y_hat)) if abs(y_hat) >= STRENGTH_THRESHOLD else 0,
            "majority_sign": majority_sign,
            "majority_base_rate": float(majority_base_rate),
            "sign_neg_fp_baseline": sign_neg_fp,
            "n_train": int(len(y_tr)),
            "n_features_used": int(np.sum(pred_avail)),
            "input_completeness": float(input_completeness),
            "is_covid": (
                pred_rec.get("period") is not None
                and (pd.Timestamp(pred_rec["period"]).year == 2020)
                and (pd.Timestamp(pred_rec["period"]).month in range(3, 7))
            ),
        })

    return results


# ---------------------------------------------------------------------------
# Hit-rate and kill-rule evaluation
# ---------------------------------------------------------------------------

def evaluate_hit_rate(
    results: list[dict],
    exclude_covid: bool = True,
    exclude_zero_target: bool = True,
) -> dict[str, Any]:
    """Compute walk-forward hit-rate and Wilson CI.

    Majority base rate is computed from the ACTUAL targets in the subset
    (not the per-step training-set majority), consistent with the kill rule:
    majority_base_rate = max(n_up, n_down) / n_total in the non-covid window.

    Returns dict with keys: n, hits, hit_rate, wilson_ci, majority_base_rate,
    kill_triggered.
    """
    subset = results
    if exclude_covid:
        subset = [r for r in subset if not r.get("is_covid", False)]
    if exclude_zero_target:
        subset = [r for r in subset if r.get("actual_target", 0) != 0]
    # Only count steps where model made a directional call (predicted_sign != 0)
    directional = [r for r in subset if r.get("predicted_sign", 0) != 0]

    n = len(directional)
    hits = sum(
        1 for r in directional
        if r.get("predicted_sign") == r.get("actual_target")
    )
    hit_rate = hits / n if n > 0 else None
    wilson = _wilson(hits, n) if n > 0 else None

    # Majority base rate from ACTUAL targets in the evaluated subset
    # (fraction of majority class over all non-covid, non-zero steps)
    n_up = sum(1 for r in subset if r.get("actual_target", 0) > 0)
    n_down = sum(1 for r in subset if r.get("actual_target", 0) < 0)
    n_total = n_up + n_down
    majority_base_rate = max(n_up, n_down) / n_total if n_total > 0 else 0.5

    # Kill rule: Wilson LB <= majority_base_rate
    kill_triggered = True  # default: kill if insufficient data
    if wilson is not None:
        kill_triggered = wilson[0] <= majority_base_rate

    return {
        "n": n,
        "hits": hits,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "wilson_ci": wilson,
        "majority_base_rate": round(majority_base_rate, 4),
        "kill_triggered": kill_triggered,
    }


# ---------------------------------------------------------------------------
# Live inference: compute_revision_lean
# ---------------------------------------------------------------------------

def compute_revision_lean(
    asof: date | pd.Timestamp,
    root: str | Path,
    init_vintages: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute the revision-lean display field for the NFP card.

    Parameters
    ----------
    asof :
        The decision date (day before the upcoming NFP release).
    root :
        Repository root path (for locating data stores).
    init_vintages :
        Optional pre-loaded output_type=4 vintages DataFrame (for ICSA features).
        If None, loads from data/fred_vintage/vintages.parquet.

    Returns
    -------
    dict with keys:
        lean: 'up' | 'down' | 'none'
        strength: float (|y_hat|)
        model_hit_rate_backtest: float | None
        n_backtest: int | None
        basis: 'first_to_third' | 'first_to_cumulative_fallback'
        display_only: True
        authority: False
    """
    root = Path(root)
    asof_ts = pd.Timestamp(asof)

    mv_df, basis = load_multi_vintage(root)
    if mv_df.empty:
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": None,
            "n_backtest": None,
            "basis": basis,
            "display_only": True,
            "authority": False,
        }

    # Load initial-print vintages for ICSA features if not provided
    if init_vintages is None:
        iv_path = _initial_vintage_path(root)
        if iv_path.exists():
            init_vintages = pd.read_parquet(iv_path)
            for col in ("period", "realtime_start", "realtime_end"):
                if col in init_vintages.columns:
                    init_vintages[col] = pd.to_datetime(init_vintages[col], errors="coerce")
        else:
            init_vintages = None

    # Build the revision target DataFrame
    target_df = build_revision_target_df(mv_df, basis)
    if target_df.empty or len(target_df) < MIN_TRAIN_OBS:
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": None,
            "n_backtest": None,
            "basis": basis,
            "display_only": True,
            "authority": False,
        }

    # Build records for walk-forward (only periods with known third print)
    records = []
    for _, row in target_df.iterrows():
        period = pd.Timestamp(row["period"])
        decision_date = pd.Timestamp(row["decision_date"])
        features = build_revision_features(
            period=period,
            decision_date=decision_date,
            first_print_mom=float(row["first_print_mom"]),
            mv_df=mv_df,
            init_vintages=init_vintages,
        )
        # label_observable_date = third_release_date: the date the target
        # (third print MoM) first became observable in ALFRED.
        # Used by run_revision_walk_forward to prevent training-label look-ahead.
        label_obs = row.get("third_release_date")
        rec = {
            "period": period,
            "first_release_date": row["first_release_date"],
            "decision_date": decision_date,
            "label_observable_date": (
                pd.Timestamp(label_obs) if label_obs is not None and pd.notna(label_obs)
                else None
            ),
            "target": int(row["target"]),
            **features,
        }
        records.append(rec)

    # Sort by release date
    records.sort(key=lambda r: r.get("first_release_date", pd.Timestamp.min))

    # Run walk-forward to get backtest stats
    wf_results = run_revision_walk_forward(records)
    eval_stats = evaluate_hit_rate(wf_results, exclude_covid=True)

    # Build live features for current prediction
    # Find the most recent period whose FIRST print is at or before asof
    knowable = mv_df[mv_df["realtime_start"] <= asof_ts]
    if knowable.empty:
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": eval_stats.get("hit_rate"),
            "n_backtest": eval_stats.get("n"),
            "basis": basis,
            "display_only": True,
            "authority": False,
        }

    # Most recent period with a first print knowable at asof
    first_prints_known = (
        knowable.sort_values("realtime_start")
        .groupby("period", as_index=False)
        .first()
    )
    first_prints_known["period"] = pd.to_datetime(first_prints_known["period"])
    most_recent_period = first_prints_known["period"].max()

    # Prior period for MoM
    prior_period = most_recent_period - pd.DateOffset(months=1)
    v_now_row = first_prints_known[first_prints_known["period"] == most_recent_period]
    v_prior_row = first_prints_known[first_prints_known["period"] == prior_period]
    if v_now_row.empty or v_prior_row.empty:
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": eval_stats.get("hit_rate"),
            "n_backtest": eval_stats.get("n"),
            "basis": basis,
            "display_only": True,
            "authority": False,
        }
    first_mom = float(v_now_row.iloc[0]["value"]) - float(v_prior_row.iloc[0]["value"])

    live_features = build_revision_features(
        period=most_recent_period,
        decision_date=asof_ts,
        first_print_mom=first_mom,
        mv_df=mv_df,
        init_vintages=init_vintages,
    )

    # Train on all historical records with known third print (and kill check passed)
    if eval_stats.get("kill_triggered", True):
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": eval_stats.get("hit_rate"),
            "n_backtest": eval_stats.get("n"),
            "basis": basis,
            "display_only": True,
            "authority": False,
        }

    # Train on full set of available records with non-zero target
    feature_names = [
        "fp_surprise_vs_AR1", "sin_month", "cos_month", "icsa_4m_survey_week_change"
    ]
    train_recs = [r for r in records if r.get("target", 0) != 0]
    if len(train_recs) < MIN_TRAIN_OBS:
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": eval_stats.get("hit_rate"),
            "n_backtest": eval_stats.get("n"),
            "basis": basis,
            "display_only": True,
            "authority": False,
        }

    X_tr = _build_X(train_recs, feature_names)
    y_tr = np.array([r["target"] for r in train_recs], dtype=float)
    x_pred = np.array(
        [live_features.get(fn, np.nan) if live_features.get(fn) is not None else np.nan
         for fn in feature_names],
        dtype=float,
    )
    pred_avail = ~np.isnan(x_pred)
    X_avail = X_tr[:, pred_avail]
    x_avail = x_pred[pred_avail]
    row_ok = ~np.any(np.isnan(X_avail), axis=1)
    X_fit = X_avail[row_ok]
    y_fit = y_tr[row_ok]

    if len(X_fit) < MIN_TRAIN_OBS or X_fit.shape[1] == 0:
        return {
            "lean": "none",
            "strength": None,
            "model_hit_rate_backtest": eval_stats.get("hit_rate"),
            "n_backtest": eval_stats.get("n"),
            "basis": basis,
            "display_only": True,
            "authority": False,
        }

    y_hat = _ridge_predict_single(X_fit, y_fit, x_avail)
    strength = abs(y_hat)

    if strength < STRENGTH_THRESHOLD:
        lean = "none"
    elif y_hat > 0:
        lean = "up"
    else:
        lean = "down"

    return {
        "lean": lean,
        "strength": round(float(strength), 4),
        "model_hit_rate_backtest": eval_stats.get("hit_rate"),
        "n_backtest": eval_stats.get("n"),
        "basis": basis,
        "display_only": True,
        "authority": False,
    }


# ---------------------------------------------------------------------------
# Descriptive context (no model)
# ---------------------------------------------------------------------------

def compute_revision_context() -> dict[str, Any]:
    """Return the descriptive LEVEL-bias annotation constants.

    DISPLAY-ONLY — descriptive annotation only. These are cumulative LEVEL
    revision statistics (not MoM-change bias). MoM-change bias is NOT
    significant and must not be implied.

    From MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md §12.3 MRI-R37:
      expansions +216k mean cumulative level revision
      contractions −262k mean cumulative level revision
    """
    return {
        "level_bias_annotation": {
            "expansion_mean_cumulative_revision_k": _EXPANSION_CUMULATIVE_REVISION_K,
            "contraction_mean_cumulative_revision_k": _CONTRACTION_CUMULATIVE_REVISION_K,
            "note": (
                "LEVEL-BIAS ONLY: expansionary NFP prints tend to be cumulatively "
                f"revised up (+{_EXPANSION_CUMULATIVE_REVISION_K}k mean), "
                f"contractions down ({_CONTRACTION_CUMULATIVE_REVISION_K}k). "
                "This is a level-bias in cumulative revisions — MoM-change bias "
                "is NOT significant and must not be implied. "
                "Era-conditional; sourced from "
                "research/release_forecast/PREREG_NFP_REVISION_V1.md."
            ),
            "display_only": True,
            "authority": False,
            "source": "MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md §12.3 MRI-R37",
        }
    }
