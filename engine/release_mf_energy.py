"""MRI Track T — Mixed-Frequency Energy Accumulator headline nowcast (mf_energy v1).

SPECIFICATION: research/release_forecast/PREREG_MF_ENERGY_V1.md (frozen 2026-07-10 before backtest).
ANTI-MINING: committed after prereg and before backtest results are observed.

Target: cpi_headline ONLY (CPIAUCSL MoM % SA, ALFRED initial prints).
Shadow tag: mf_energy.
Attempt: #1 of 1 (no re-spec after results; MRI-R36 §6).

Model:
  Leg 1: reference-month gasoline nowcast from published GASREGW weeks + WTI pass-through
         for remaining weeks (expanding OLS of weekly gasoline changes on weekly WTI changes).
         energy_contrib = gasoline_mom * RI motor-fuel weight * expanding-OLS gamma.
  Leg 2: ex-energy AR(3) + sin/cos seasonals on the derived exenergy series.
  Head:  ridge(lambda=1.0) walk-forward of CPI headline MoM on
         [energy_contrib, exenergy_ar, sin, cos]; MIN_TRAIN_OBS=60.

PIT:
  CPIAUCSL via knowable_series (ALFRED vintages, initial prints).
  GASREGW / DCOILWTICO: unrevised, strict date <= asof filter.
  No look-ahead: WTI beta estimated on weeks strictly BEFORE reference month M.
  CPI RI weights: revision_optimistic (BLS flat file, not ALFRED-vintaged).

DISPLAY-ONLY. display_only=True, authority=False on all outputs.
Never conditions scoring, never gates or sizes positions.

Pure numpy / pandas only. No sklearn, statsmodels, or scipy.stats.

NEW FILES ONLY — no edits to engine/release_forecast.py or any existing producer.
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
# Constants (frozen per PREREG_MF_ENERGY_V1.md)
# ---------------------------------------------------------------------------
RIDGE_LAMBDA = 1.0
MIN_TRAIN_OBS = 60       # minimum training observations for head model
MIN_QUANTILE_OBS = 24    # minimum residual history for quantile bands
INLINE_BAND_SIGMA = 0.35  # ±0.35σ inline band for skew tag
COVID_MONTHS = {(2020, m) for m in range(3, 7)}  # 2020-03..2020-06

# BLS CPI relative-importance weight for gasoline (from cpi_relative_importance_2026.yml)
# Key: gasoline_all_types = 2.895 (out of 100.000 all-items)
GASOLINE_RI_WEIGHT = 2.895

# Feature names for the HEAD model (frozen order)
_HEAD_FEATURES = ["energy_contrib", "exenergy_ar", "sin_term", "cos_term"]

# Feature names for the ex-energy AR(3)+seasonal sub-model (frozen order)
_EXENERGY_AR_FEATURES = ["exenergy_lag1", "exenergy_lag2", "exenergy_lag3", "sin_term", "cos_term"]


# ---------------------------------------------------------------------------
# Ridge regression helpers (numpy only — no sklearn)
# ---------------------------------------------------------------------------

def _ridge_solve(X: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    """Closed-form Ridge: beta = (X'X + lam*I)^{-1} X'y.

    X: (n, p) design matrix with bias column appended by caller.
    y: (n,) targets.
    Returns beta: (p,).
    """
    XtX = X.T @ X
    XtX_reg = XtX + lam * np.eye(XtX.shape[0])
    Xty = X.T @ y
    try:
        beta = np.linalg.solve(XtX_reg, Xty)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(XtX_reg, Xty, rcond=None)[0]
    return beta


def _ols_slope_intercept(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Bivariate OLS: y = b0 + b1*x. Returns (intercept, slope).

    Uses closed-form OLS (not ridge). Used for the WTI pass-through beta and gamma.
    Returns (0.0, 1.0) if insufficient data.
    """
    mask = np.isfinite(x) & np.isfinite(y)
    xm, ym = x[mask], y[mask]
    n = len(xm)
    if n < 3:
        return 0.0, 1.0
    A = np.column_stack([np.ones(n), xm])
    try:
        beta, _, _, _ = np.linalg.lstsq(A, ym, rcond=None)
        return float(beta[0]), float(beta[1])
    except Exception:
        return 0.0, 1.0


def _zscore_params(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, std) for each column (expanding-window normalization)."""
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0, ddof=1)
    std[std == 0] = 1.0  # constant column -> divide by 1 (feature zeroed in z-score)
    return mean, std


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_gasregw(root: Path) -> pd.Series:
    """Load GASREGW weekly gasoline prices as a date-indexed Series.

    Returns a Series with pd.Timestamp index, values in USD/gallon.
    Index is the Monday date of each reporting week.
    """
    path = root / "data" / "fred" / "GASREGW.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    col = df.columns[0]  # gasoline_regular_weekly
    s = df[col].dropna().sort_index()
    return s


def _load_wti(root: Path) -> pd.Series:
    """Load DCOILWTICO daily WTI crude as a date-indexed Series.

    Returns a Series with pd.Timestamp index, values in USD/barrel.
    NaN rows already dropped.
    """
    path = root / "data" / "fred" / "DCOILWTICO.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    col = df.columns[0]  # wti_crude
    s = df[col].dropna().sort_index()
    return s


# ---------------------------------------------------------------------------
# Reference-month gasoline accumulator (Leg 1) — core functions
# ---------------------------------------------------------------------------

def _month_window(ref_month: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (first_day_M, last_day_M) for the reference month."""
    first = ref_month.to_period("M").to_timestamp(how="S")
    last = ref_month.to_period("M").to_timestamp(how="E")
    return first, last


def _all_mondays_in_month(ref_month: pd.Timestamp) -> list[pd.Timestamp]:
    """Return all Monday dates (GASREGW index convention) that fall in calendar month M.

    GASREGW uses Monday-of-week as the index date. A week 'belongs' to month M if
    its Monday index falls in [first_day_M, last_day_M]. This function enumerates all
    such Mondays regardless of whether they have been published yet, enabling the
    remaining-week loop to correctly identify weeks where asof < Monday (i.e., not yet
    published in GASREGW at decision date asof).
    """
    first, last = _month_window(ref_month)
    # Find first Monday >= first day of M (weekday 0 = Monday)
    dow = first.weekday()  # 0=Mon, ..., 6=Sun
    days_to_monday = (7 - dow) % 7  # 0 if already Monday
    current = first + pd.Timedelta(days=days_to_monday)
    mondays: list[pd.Timestamp] = []
    while current <= last:
        mondays.append(current)
        current += pd.Timedelta(days=7)
    return mondays


def _wti_weekly_avg_pit(wti: pd.Series, week_start: pd.Timestamp, asof_ts: pd.Timestamp) -> float | None:
    """Average daily WTI over trading days in [week_start, week_start+6] where date <= asof.

    week_start is the Monday of the week (GASREGW index convention).
    Returns None if no WTI days available in the window at or before asof.
    No lookahead: strict date <= asof_ts.
    """
    week_end = week_start + pd.Timedelta(days=6)
    effective_end = min(week_end, asof_ts)
    mask = (wti.index >= week_start) & (wti.index <= effective_end)
    days = wti[mask]
    if days.empty:
        return None
    return float(days.mean())


def _precompute_wti_weekly_avgs(
    wti: pd.Series,
    week_starts: pd.DatetimeIndex,
) -> dict[pd.Timestamp, float]:
    """Precompute full-week WTI averages (all trading days in the week).

    For historical OLS training (weeks well before asof), we don't need the
    asof filter — just the full weekly average. This is O(n_weeks) instead
    of O(n_weeks * n_training_steps).

    Returns {week_start_ts: avg_wti} for weeks that have any WTI data.
    Weeks with no WTI data are excluded from the dict.
    """
    result: dict[pd.Timestamp, float] = {}
    for ws in week_starts:
        we = ws + pd.Timedelta(days=6)
        mask = (wti.index >= ws) & (wti.index <= we)
        days = wti[mask]
        if not days.empty:
            result[ws] = float(days.mean())
    return result


def _compute_gasoline_nowcast(
    gasregw: pd.Series,
    wti: pd.Series,
    ref_month: pd.Timestamp,
    asof: date,
    _precomp_wti_avgs: dict[pd.Timestamp, float] | None = None,
) -> dict:
    """Compute the reference-month gasoline nowcast and accumulator metadata.

    PIT: only GASREGW weeks with index <= asof and WTI with date <= asof used.
    WTI beta training: weeks strictly BEFORE ref_month (no lookahead).

    Parameters
    ----------
    _precomp_wti_avgs : optional dict {week_start_ts: avg_wti_for_full_week}
        If provided, used for historical training weeks (weeks well before asof,
        where the asof filter is not binding). Skips the per-week WTI loop for
        ~100x speedup in bulk walk-forwards. The asof-sensitive current/future
        week projections still use the real WTI series.

    Returns dict with:
      gasoline_est_M: float | None — estimated avg gasoline price for month M
      gasoline_est_M1: float | None — avg gasoline price for month M-1
      gasoline_mom: float | None — MoM % change
      n_weeks_published: int
      n_weeks_projected: int
      wti_beta_intercept: float
      wti_beta_slope: float
      wti_n_train: int
    """
    asof_ts = pd.Timestamp(asof)
    ref_first, ref_last = _month_window(ref_month)

    # Month M-1 window
    ref_m1 = (ref_month.to_period("M") - 1).to_timestamp(how="S")
    ref_m1_first, ref_m1_last = _month_window(ref_m1)

    # Published weeks in M: only weeks whose Monday index date is in month M AND <= asof.
    # GASREGW only contains published (historical) rows — we use the series for published weeks.
    published_M_mask = (
        (gasregw.index >= ref_first) &
        (gasregw.index <= ref_last) &
        (gasregw.index <= asof_ts)
    )
    published_M = gasregw[published_M_mask]

    # Remaining weeks in M: enumerate all expected Monday dates in month M, then keep
    # only those whose date is strictly AFTER asof (not yet published in GASREGW at asof).
    # FIX: previously this looked in gasregw for rows with index > asof, which was always
    # empty because GASREGW only contains published (historical) data.  We now enumerate
    # all Mondays in month M and retain those that are unpublished at asof.
    all_m_mondays = _all_mondays_in_month(ref_month)
    remaining_week_starts = [m for m in all_m_mondays if m > asof_ts]

    # M-1 average: PIT-filtered to dates <= asof (prevents lookahead when asof falls
    # before the last M-1 week has been published in corner cases).
    m1_weeks = gasregw[
        (gasregw.index >= ref_m1_first) &
        (gasregw.index <= ref_m1_last) &
        (gasregw.index <= asof_ts)  # asof guard on M-1 denominator
    ]
    if m1_weeks.empty:
        # Fallback: last available value strictly before M, within asof constraint
        fallback = gasregw[(gasregw.index < ref_first) & (gasregw.index <= asof_ts)]
        gasoline_est_M1 = float(fallback.iloc[-1]) if not fallback.empty else None
    else:
        gasoline_est_M1 = float(m1_weeks.mean())

    # WTI beta: OLS of weekly gasoline changes on weekly WTI changes
    # Training: all weeks strictly BEFORE ref_month (month index < ref_first), date <= asof
    train_gas = gasregw[(gasregw.index < ref_first) & (gasregw.index <= asof_ts)].sort_index()

    gas_changes, wti_changes = [], []
    prev_gas: float | None = None
    prev_wti_avg: float | None = None

    # Cutoff to determine when asof filter is binding:
    # For weeks ending before (asof - 7 days), all days are before asof → use precomputed.
    asof_ts_minus7 = asof_ts - pd.Timedelta(days=7)

    for idx, gas_val in train_gas.items():
        # Use precomputed avg if week fully before asof window
        if _precomp_wti_avgs is not None and idx < asof_ts_minus7:
            wti_avg = _precomp_wti_avgs.get(idx)
        else:
            wti_avg = _wti_weekly_avg_pit(wti, idx, asof_ts)
        if wti_avg is None:
            prev_gas = None
            prev_wti_avg = None
            continue
        if prev_gas is not None and prev_wti_avg is not None:
            gas_changes.append(float(gas_val) - prev_gas)
            wti_changes.append(wti_avg - prev_wti_avg)
        prev_gas = float(gas_val)
        prev_wti_avg = wti_avg

    wti_n_train = len(gas_changes)
    if wti_n_train >= 3:
        beta_intercept, beta_slope = _ols_slope_intercept(
            np.array(wti_changes), np.array(gas_changes)
        )
    else:
        beta_intercept, beta_slope = 0.0, 1.0

    # Project remaining weeks using WTI delta.
    # remaining_week_starts: Mondays in month M that fall strictly after asof
    # (i.e., not yet published in GASREGW at the decision date).
    #
    # For each remaining week (Monday > asof), the spec calls for:
    #   delta_wti = wti_avg(that_week) - wti_avg(prev_week)
    # However, since Monday > asof, the future week's WTI days are all after asof
    # and therefore unavailable. The correct PIT-consistent approximation:
    #   wti_cur  = avg(WTI days in [week_idx - 7, asof])   — last observable 7-day window
    #   wti_prev = avg(WTI days in [week_idx - 14, week_idx - 8])  — window before that
    # This represents the WTI delta observable RIGHT NOW (at asof) and is the best
    # available pass-through for the unpublished week's price.  Each remaining week
    # uses the same current WTI window (the 7 days leading up to asof), so the first
    # remaining week in M drives the projected price for all subsequent ones
    # (compounded via prev_gas_val which advances after each projection).
    projected_prices: list[float] = []
    for week_idx in remaining_week_starts:
        # 'Current' WTI: WTI days in the 7-day window ending at asof
        # (the most recently observable WTI level, proxy for this remaining week).
        wti_cur_window_start = week_idx - pd.Timedelta(days=7)
        mask_cur = (wti.index >= wti_cur_window_start) & (wti.index <= asof_ts)
        cur_days = wti[mask_cur]
        if cur_days.empty:
            continue
        wti_cur = float(cur_days.mean())

        # 'Prev' WTI: the 7-day window before the current window.
        wti_prev_window_end = wti_cur_window_start - pd.Timedelta(days=1)
        wti_prev_window_start = wti_cur_window_start - pd.Timedelta(days=7)
        mask_prev = (wti.index >= wti_prev_window_start) & (wti.index <= min(wti_prev_window_end, asof_ts))
        prev_days = wti[mask_prev]
        if prev_days.empty:
            continue
        wti_prev = float(prev_days.mean())

        delta_wti = wti_cur - wti_prev
        # Use last known gasoline (within asof) as base for projection
        gas_before = gasregw[(gasregw.index < week_idx) & (gasregw.index <= asof_ts)]
        if gas_before.empty:
            continue
        prev_gas_val = float(gas_before.iloc[-1])
        projected = prev_gas_val + beta_intercept + beta_slope * delta_wti
        projected_prices.append(projected)

    n_published = len(published_M)
    n_projected = len(projected_prices)  # successfully projected weeks (had WTI data)

    all_prices = list(published_M.values) + projected_prices
    if not all_prices:
        return {
            "gasoline_est_M": None,
            "gasoline_est_M1": gasoline_est_M1,
            "gasoline_mom": None,
            "n_weeks_published": n_published,
            "n_weeks_projected": n_projected,
            "wti_beta_intercept": beta_intercept,
            "wti_beta_slope": beta_slope,
            "wti_n_train": wti_n_train,
        }

    gasoline_est_M = float(np.mean(all_prices))
    gasoline_mom: float | None = None
    if gasoline_est_M1 is not None and gasoline_est_M1 != 0.0:
        gasoline_mom = (gasoline_est_M / gasoline_est_M1 - 1.0) * 100.0

    return {
        "gasoline_est_M": gasoline_est_M,
        "gasoline_est_M1": gasoline_est_M1,
        "gasoline_mom": gasoline_mom,
        "n_weeks_published": n_published,
        "n_weeks_projected": n_projected,
        "wti_beta_intercept": beta_intercept,
        "wti_beta_slope": beta_slope,
        "wti_n_train": wti_n_train,
    }


def _compute_wti_beta(
    gasregw: pd.Series,
    wti: pd.Series,
    ref_month: pd.Timestamp,
    asof: date,
) -> tuple[float, float, int]:
    """Return (intercept, slope, n_train) for the WTI pass-through OLS.

    Thin accessor for testing. The full nowcast is in _compute_gasoline_nowcast.
    Training EXCLUDES all weeks in or after ref_month (no-lookahead invariant).
    """
    result = _compute_gasoline_nowcast(gasregw, wti, ref_month, asof)
    return (
        result["wti_beta_intercept"],
        result["wti_beta_slope"],
        result["wti_n_train"],
    )


# ---------------------------------------------------------------------------
# Precomputed gasoline_mom series (for efficient walk-forward)
# ---------------------------------------------------------------------------

def _precompute_gasoline_mom_series(
    gasregw: pd.Series,
    wti: pd.Series,
    cpi_periods: list[pd.Timestamp],
    asof_dates: list[date],
) -> list[float | None]:
    """Precompute gasoline_mom for each (ref_month, asof) pair in one pass.

    This avoids the O(n^2) cost of calling _compute_gasoline_nowcast inside
    _build_mf_features for each step. Each step gets its own asof-filtered gasoline
    nowcast for its reference month.

    Returns list of gasoline_mom values (same length as cpi_periods).
    """
    result = []
    for ref_month, asof in zip(cpi_periods, asof_dates):
        gas = _compute_gasoline_nowcast(gasregw, wti, ref_month, asof)
        result.append(gas["gasoline_mom"])
    return result


def _precompute_nowcast_meta_series(
    gasregw: pd.Series,
    wti: pd.Series,
    cpi_periods: list[pd.Timestamp],
    asof_dates: list[date],
) -> list[dict]:
    """Precompute full gasoline nowcast metadata for each step."""
    result = []
    for ref_month, asof in zip(cpi_periods, asof_dates):
        gas = _compute_gasoline_nowcast(gasregw, wti, ref_month, asof)
        result.append(gas)
    return result


# ---------------------------------------------------------------------------
# Gamma: headline MoM ~ b0 + gamma * gasoline_mom (expanding OLS)
# ---------------------------------------------------------------------------

def _compute_gamma(
    historical_gasoline_mom: list[float | None],
    historical_cpi_mom: list[float | None],
    min_obs: int = 12,
) -> float:
    """Estimate gamma via bivariate OLS: cpi_mom ~ b0 + gamma * gasoline_mom.

    Returns the slope (gamma). Falls back to 1.0 if insufficient data.
    """
    pairs = [
        (g, c) for g, c in zip(historical_gasoline_mom, historical_cpi_mom)
        if g is not None and c is not None and np.isfinite(g) and np.isfinite(c)
    ]
    if len(pairs) < min_obs:
        return 1.0
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    _, slope = _ols_slope_intercept(x, y)
    return slope


# ---------------------------------------------------------------------------
# Ex-energy AR(3)+seasonal sub-model
# ---------------------------------------------------------------------------

def _seasonal_terms(ref_month: pd.Timestamp) -> tuple[float, float]:
    """Compute sin/cos seasonal terms for the reference month."""
    m = ref_month.month
    sin_t = math.sin(2.0 * math.pi * m / 12.0)
    cos_t = math.cos(2.0 * math.pi * m / 12.0)
    return sin_t, cos_t


def _predict_exenergy_ar(
    exenergy_history: list[float],
    ref_month: pd.Timestamp,
    ref_month_history: list[pd.Timestamp] | None = None,
    min_obs: int = 10,
) -> float | None:
    """AR(3) + sin/cos prediction of ex-energy MoM for ref_month.

    exenergy_history: list of historical ex-energy MoM values (training, most-recent last).
    ref_month: the month being predicted (for the sin/cos terms).
    ref_month_history: optional list of reference months for each history element
                       (for accurate seasonal terms in training). If None, derives
                       month by counting back from ref_month.
    Returns None if insufficient history.

    Uses ridge(lambda=1.0) on [exenergy_lag1, exenergy_lag2, exenergy_lag3, sin_term, cos_term].
    """
    n = len(exenergy_history)
    if n < min_obs + 3:
        return None

    sin_t, cos_t = _seasonal_terms(ref_month)

    # Build training matrix
    X_rows = []
    y_rows = []

    for i in range(3, n):
        lag1 = exenergy_history[i - 1]
        lag2 = exenergy_history[i - 2]
        lag3 = exenergy_history[i - 3]
        target = exenergy_history[i]
        if any(v is None or (isinstance(v, float) and not np.isfinite(v))
               for v in [lag1, lag2, lag3, target]):
            continue

        # Seasonal for training month
        if ref_month_history is not None and i < len(ref_month_history):
            train_month = ref_month_history[i]
        else:
            # Derive by counting back from ref_month
            train_month = (ref_month.to_period("M") - (n - 1 - i)).to_timestamp()
        s_tr, c_tr = _seasonal_terms(train_month)
        X_rows.append([float(lag1), float(lag2), float(lag3), s_tr, c_tr])
        y_rows.append(float(target))

    if len(X_rows) < min_obs:
        return None

    X = np.array(X_rows, dtype=float)
    y = np.array(y_rows, dtype=float)

    # Normalize
    mean = np.mean(X, axis=0)
    std = np.std(X, axis=0, ddof=1)
    std[std == 0] = 1.0
    Xz = (X - mean) / std

    # Augment with bias
    ones = np.ones((len(Xz), 1))
    Xa = np.hstack([Xz, ones])

    beta = _ridge_solve(Xa, y)

    # Predict using the last 3 historical values as lags
    last3 = exenergy_history[-3:]
    if any(v is None or (isinstance(v, float) and not np.isfinite(v)) for v in last3):
        return None
    x_pred = np.array([float(last3[2]), float(last3[1]), float(last3[0]), sin_t, cos_t], dtype=float)
    xz_pred = (x_pred - mean) / std
    xa_pred = np.append(xz_pred, 1.0)
    return float(xa_pred @ beta)


# ---------------------------------------------------------------------------
# Walk-forward build: precomputes all features in one pass (efficient)
# ---------------------------------------------------------------------------

def _build_all_records(
    all_prints: pd.DataFrame,
    gasregw: pd.Series,
    wti: pd.Series,
    vintages: pd.DataFrame,
    knowable_series_fn,
    cutoff: str = "T-1",
) -> list[dict]:
    """Build walk-forward records for all historical CPI periods in one efficient pass.

    Precomputes the gasoline_mom series for all periods first, then iterates
    through in order to build gamma and exenergy_history accumulators.

    This avoids the O(n^2) cost of calling _compute_gasoline_nowcast inside
    _build_mf_features for each step.

    all_prints: DataFrame with columns period, value, realtime_start, mom
    cutoff: 'T-1' or 'early'
    """
    n = len(all_prints)
    periods = list(all_prints["period"].apply(pd.Timestamp))
    rt_starts = list(all_prints["realtime_start"].apply(pd.Timestamp))
    moms = list(all_prints["mom"].values)

    # Compute step_asof per cutoff
    if cutoff == "T-1":
        asofs = [(rt - pd.Timedelta(days=1)).date() for rt in rt_starts]
    else:  # early: ~25 days before release
        asofs = [(rt - pd.Timedelta(days=26)).date() for rt in rt_starts]

    # Precompute WTI weekly averages over full gasregw history (speeds OLS loop ~100x).
    # We precompute full-week averages (no asof filter); the asof filter only matters
    # for the last 1-2 weeks in the projection window, which still use real PIT logic.
    log.debug("Precomputing WTI weekly averages for %d GASREGW weeks...", len(gasregw))
    precomp_wti = _precompute_wti_weekly_avgs(wti, gasregw.index)

    # Precompute gasoline_mom for each step (each has its own asof)
    log.debug("Precomputing gasoline_mom for %d steps...", n)
    gas_moms: list[float | None] = []
    gas_meta: list[dict] = []
    for ref_month, asof in zip(periods, asofs):
        gas = _compute_gasoline_nowcast(gasregw, wti, ref_month, asof, _precomp_wti_avgs=precomp_wti)
        gas_moms.append(gas["gasoline_mom"])
        gas_meta.append(gas)

    # Now build records in order, accumulating gamma + exenergy history
    records = []
    cumulative_gas_moms: list[float | None] = []
    cumulative_cpi_moms: list[float | None] = []
    cumulative_exenergy: list[float] = []
    cumulative_periods: list[pd.Timestamp] = []

    for i in range(n):
        ref_month = periods[i]
        asof = asofs[i]
        cpi_mom = moms[i]
        gm = gas_moms[i]
        meta = gas_meta[i]

        sin_t, cos_t = _seasonal_terms(ref_month)

        # Gamma from training history up to (not including) current step
        gamma = _compute_gamma(cumulative_gas_moms, cumulative_cpi_moms)

        # Energy contribution for this step
        energy_contrib: float | None = None
        if gm is not None:
            energy_contrib = gm * (GASOLINE_RI_WEIGHT / 100.0) * gamma

        # Ex-energy AR prediction from history
        exenergy_ar: float | None = _predict_exenergy_ar(
            cumulative_exenergy, ref_month, cumulative_periods
        )

        # Build record
        rec: dict = {
            "energy_contrib": energy_contrib,
            "exenergy_ar": exenergy_ar,
            "sin_term": sin_t,
            "cos_term": cos_t,
            "target": cpi_mom,
            "period": ref_month,
            "release_date": rt_starts[i],
            "asof": asof,
            # Provenance fields for debugging
            "_gasoline_mom": gm,
            "_gamma": gamma,
            "_n_weeks_pub": meta["n_weeks_published"],
            "_n_weeks_proj": meta["n_weeks_projected"],
        }
        records.append(rec)

        # Update accumulators (now that we have processed this step)
        cumulative_gas_moms.append(gm)
        cumulative_cpi_moms.append(cpi_mom)
        cumulative_periods.append(ref_month)

        # Compute ex-energy for accumulation
        if energy_contrib is not None:
            cumulative_exenergy.append(cpi_mom - energy_contrib)
        else:
            # No energy signal: use 0 contribution (gamma fallback keeps ex-energy ≈ CPI)
            ec_fallback = (gm or 0.0) * (GASOLINE_RI_WEIGHT / 100.0) * 1.0
            cumulative_exenergy.append(cpi_mom - ec_fallback)

    return records


# ---------------------------------------------------------------------------
# Walk-forward engine for mf_energy
# ---------------------------------------------------------------------------

def _walk_forward_mf(
    records: list[dict],
    feature_names: list[str],
    target_key: str,
    min_obs: int = MIN_TRAIN_OBS,
) -> list[dict]:
    """Expanding-window walk-forward ridge regression for mf_energy.

    Records: list of dicts with feature_names keys + target_key, sorted by time.
    Returns list of result dicts with keys:
      idx, result_pos, predicted, actual,
      baseline_naive, baseline_expanding_mean, baseline_trailing3m, baseline_ar3,
      n_train, n_features_used, input_completeness.
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

        # Build feature matrix for training
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

        # Prediction features
        pred_features = np.array(
            [pred_rec.get(fn) if pred_rec.get(fn) is not None else np.nan
             for fn in feature_names],
            dtype=float,
        )
        n_present = int(np.sum(~np.isnan(pred_features)))
        input_completeness = n_present / p if p > 0 else 0.0

        # Complete-case: use only features available in prediction row
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

        # Baselines
        naive = float(y_all[-1]) if len(y_all) > 0 else np.nan
        expanding_mean = float(np.mean(y_all)) if len(y_all) > 0 else np.nan
        trailing_3m = (
            float(np.mean(y_all[-3:])) if len(y_all) >= 3
            else (float(np.mean(y_all)) if len(y_all) > 0 else np.nan)
        )

        # AR3 baseline: ridge on first 3 features only (energy_contrib, exenergy_ar ~ lag-like)
        ar3_feat_set = set(feature_names[:min(3, len(feature_names))])
        ar3_avail = np.array(
            [(fn in ar3_feat_set) and not np.isnan(pred_features[j])
             for j, fn in enumerate(feature_names)],
            dtype=bool,
        )
        ar3_pred = naive  # default
        if ar3_avail.any():
            X_ar3_sel = X_all[:, ar3_avail]
            ar3_row_ok = ~np.any(np.isnan(X_ar3_sel), axis=1)
            X_ar3 = X_ar3_sel[ar3_row_ok]
            y_ar3 = y_all[ar3_row_ok]
            x_ar3 = pred_features[ar3_avail]
            if len(y_ar3) >= min_obs:
                try:
                    mean_a3 = np.nanmean(X_ar3, axis=0)
                    std_a3 = np.nanstd(X_ar3, axis=0, ddof=1)
                    std_a3[std_a3 == 0] = 1.0
                    Xz_a3 = (X_ar3 - mean_a3) / std_a3
                    xz_a3_pred = (x_ar3 - mean_a3) / std_a3
                    Xa_a3 = np.hstack([Xz_a3, np.ones((len(Xz_a3), 1))])
                    xa_a3_pred = np.append(xz_a3_pred, 1.0)
                    beta_a3 = _ridge_solve(Xa_a3, y_ar3)
                    ar3_pred = float(xa_a3_pred @ beta_a3)
                except Exception as e:
                    log.debug("AR3 baseline failed at step %d: %s", i, e)
                    ar3_pred = naive

        # Main ridge model (complete-case)
        ridge_pred = naive  # default
        if n_features_used > 0 and len(y_cc) >= min_obs:
            try:
                mean_k = np.nanmean(X_cc, axis=0)
                std_k = np.nanstd(X_cc, axis=0, ddof=1)
                std_k[std_k == 0] = 1.0
                Xz_cc = (X_cc - mean_k) / std_k
                xz_pred = (x_pred_raw - mean_k) / std_k
                Xa_cc = np.hstack([Xz_cc, np.ones((len(Xz_cc), 1))])
                xa_pred = np.append(xz_pred, 1.0)
                beta = _ridge_solve(Xa_cc, y_cc)
                ridge_pred = float(xa_pred @ beta)
            except Exception as e:
                log.debug("Ridge head failed at step %d: %s", i, e)
                ridge_pred = naive

        results.append({
            "idx": i,
            "result_pos": len(results),
            "predicted": ridge_pred,
            "actual": float(actual),
            "baseline_naive": naive,
            "baseline_expanding_mean": expanding_mean,
            "baseline_trailing3m": trailing_3m,
            "baseline_ar3": ar3_pred,
            "n_train": len(y_cc) if n_features_used > 0 else len(y_all),
            "n_features_used": n_features_used,
            "input_completeness": input_completeness,
        })

    return results


def _compute_quantiles_mf(residuals: np.ndarray, point: float, min_obs: int = MIN_QUANTILE_OBS) -> dict:
    """Return p10/p25/p50/p75/p90 from residual history centered on point."""
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
# Full walk-forward runner (used by backtest)
# ---------------------------------------------------------------------------

def run_walk_forward_mf(
    root: str | Path,
    cutoff: str = "T-1",
) -> dict:
    """Run the mf_energy walk-forward backtest.

    Parameters
    ----------
    root : str | Path
        Repository root (data/ subdirectories are read from here).
    cutoff : str
        'T-1': asof = day before release (primary, kill-rule evaluation).
        'early': asof = T-1 - 25 days (descriptive, accumulator does real work).

    Returns
    -------
    dict with:
      results: list[dict] — per-step results
      errors: np.ndarray — actual - predicted
      feature_names: list[str]
      cutoff: str
      metadata: dict
    """
    if cutoff not in ("T-1", "early"):
        raise ValueError(f"cutoff must be 'T-1' or 'early', got: {cutoff!r}")

    root = Path(root)
    from engine.release_forecast import load_vintages, knowable_series

    vintages = load_vintages(root)
    gasregw = _load_gasregw(root)
    wti = _load_wti(root)

    # All CPIAUCSL initial prints (full history, for walk-forward)
    all_prints = knowable_series(vintages, "CPIAUCSL", date(2099, 1, 1))
    if all_prints.empty or len(all_prints) < 2:
        return {
            "results": [], "errors": np.array([]),
            "feature_names": _HEAD_FEATURES,
            "cutoff": cutoff,
            "metadata": {"release": "cpi_headline", "model": "mf_energy",
                         "n_records": 0, "error": "insufficient_cpi_data"},
        }

    all_prints = all_prints.sort_values("period").reset_index(drop=True)
    mom_col = all_prints["value"].pct_change() * 100.0
    all_prints = all_prints.assign(mom=mom_col).dropna(subset=["mom"]).reset_index(drop=True)

    # Build all records in one efficient pass
    records = _build_all_records(all_prints, gasregw, wti, vintages, knowable_series, cutoff=cutoff)

    wf_results = _walk_forward_mf(records, _HEAD_FEATURES, "target")

    # Attach period metadata + n_weeks_projected for accumulator diagnostics
    for r in wf_results:
        meta = records[r["idx"]]
        r["period"] = meta.get("period")
        r["release_date"] = meta.get("release_date")
        r["n_weeks_projected"] = meta.get("_n_weeks_proj", 0)  # per-fold projection count

    errors = np.array(
        [r["actual"] - r["predicted"] for r in wf_results],
        dtype=float,
    )

    return {
        "results": wf_results,
        "errors": errors,
        "feature_names": _HEAD_FEATURES,
        "cutoff": cutoff,
        "metadata": {
            "release": "cpi_headline",
            "model": "mf_energy",
            "n_records": len(records),
            "cutoff": cutoff,
        },
    }


# ---------------------------------------------------------------------------
# Single-date projection API (public interface)
# ---------------------------------------------------------------------------

def _empty_mf(asof: date, cutoff_label: str, reason: str) -> dict:
    """Null projection dict for mf_energy."""
    return {
        "release": "cpi_headline",
        "model": "mf_energy",
        "asof": asof.isoformat(),
        "cutoff_label": cutoff_label,
        "point": None,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "confidence": None,
        "input_completeness": 0.0,
        "benchmark_set": {
            "naive_prior": None,
            "expanding_mean": None,
            "trailing_3m": None,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {
            "sigma": None, "sigma_scale_pp": None, "tag": None,
            "inline_band": INLINE_BAND_SIGMA,
        },
        "mf_energy_components": None,
        "pit_provenance": {
            "revision_optimistic_legs": ["cpi_weights"],
            "unrevised_legs": ["gasoline_weekly", "wti_crude"],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
            "reason": reason,
        },
        "display_only": True,
        "authority": False,
    }


def project_release_mf(
    release: str,
    asof: date,
    root: str | Path,
    ref_month: date | pd.Timestamp | None = None,
    *,
    period: str | None = None,
    cutoff_label: str = "T-1",
) -> dict:
    """Generate an mf_energy point-in-time projection for cpi_headline.

    Parameters
    ----------
    release : str
        Must be 'cpi_headline' (only target supported by Track T).
    asof : date
        Decision date (the day before or earlier relative to release).
    root : str | Path
        Repository root (data/ subdirectories read from here).
    ref_month : date | pd.Timestamp | None
        The CPI reference month M the upcoming print covers. None derives from
        the last knowable CPIAUCSL initial print + 1 month.
    period : str | None
        'YYYY-MM' for schema ID construction. None derives from ref_month.
    cutoff_label : str
        'T-1' (default) or 'early'. Informational tag on the output.

    Returns
    -------
    dict matching the standard projection schema + mf_energy_components.
    display_only=True, authority=False.
    model='mf_energy'.
    """
    if release != "cpi_headline":
        raise ValueError(
            f"project_release_mf supports only 'cpi_headline'. Got: {release!r}"
        )

    root = Path(root)
    from engine.release_forecast import (
        load_vintages,
        knowable_series,
        compute_inputs_hash,
        make_release_id,
        make_prediction_id,
    )

    vintages = load_vintages(root)
    gasregw = _load_gasregw(root)
    wti = _load_wti(root)

    # All knowable CPIAUCSL prints at asof
    cpi_known = knowable_series(vintages, "CPIAUCSL", asof)
    if cpi_known.empty or len(cpi_known) < 2:
        return _empty_mf(asof, cutoff_label, "no_cpi_data")

    cpi_known = cpi_known.sort_values("period").reset_index(drop=True)
    mom_col = cpi_known["value"].pct_change() * 100.0
    cpi_known = cpi_known.assign(mom=mom_col).dropna(subset=["mom"]).reset_index(drop=True)

    if len(cpi_known) < MIN_TRAIN_OBS + 1:
        return _empty_mf(asof, cutoff_label, "insufficient_history")

    # Derive ref_month
    if ref_month is None:
        last_period = pd.Timestamp(cpi_known["period"].iloc[-1])
        ref_month_ts = (last_period.to_period("M") + 1).to_timestamp()
    else:
        ref_month_ts = pd.Timestamp(ref_month)

    # Build all training records up to asof (use asof as step_asof for all)
    # This is the PIT-consistent training set available at decision date asof
    training_prints = cpi_known.copy()  # already filtered to realtime_start <= asof via knowable_series

    # Build records in efficient pass
    records = _build_all_records(
        training_prints, gasregw, wti, vintages, knowable_series, cutoff="T-1"
    )

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_mf(asof, cutoff_label, "insufficient_records")

    # Walk-forward to get residual history
    wf_results = _walk_forward_mf(records, _HEAD_FEATURES, "target")
    if not wf_results:
        return _empty_mf(asof, cutoff_label, "no_walk_forward_results")

    errors_arr = np.array([r["actual"] - r["predicted"] for r in wf_results], dtype=float)

    # Compute current prediction features (for ref_month_ts at asof)
    # Compute gasoline nowcast for the upcoming month
    gas_result = _compute_gasoline_nowcast(gasregw, wti, ref_month_ts, asof)
    gas_mom = gas_result["gasoline_mom"]

    # Gamma: from all training records
    all_gas_moms = [r.get("_gasoline_mom") for r in records]
    all_cpi_moms = [r.get("target") for r in records]
    gamma = _compute_gamma(all_gas_moms, all_cpi_moms)

    energy_contrib: float | None = None
    if gas_mom is not None:
        energy_contrib = gas_mom * (GASOLINE_RI_WEIGHT / 100.0) * gamma

    # Ex-energy history (from all training records)
    exenergy_hist = [r.get("target", 0.0) - (r.get("energy_contrib") or 0.0)
                     for r in records]
    exenergy_ref_months = [r.get("period") for r in records]
    exenergy_ar = _predict_exenergy_ar(exenergy_hist, ref_month_ts, exenergy_ref_months)

    sin_t, cos_t = _seasonal_terms(ref_month_ts)

    feats = {
        "energy_contrib": energy_contrib,
        "exenergy_ar": exenergy_ar,
        "sin_term": sin_t,
        "cos_term": cos_t,
    }

    # Build training matrix from records
    p = len(_HEAD_FEATURES)
    n_tr = len(records)
    X_all = np.full((n_tr, p), np.nan)
    y_all_list = []
    for ii, rec in enumerate(records):
        for jj, fn in enumerate(_HEAD_FEATURES):
            v = rec.get(fn)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                X_all[ii, jj] = v
        y_all_list.append(rec.get("target", np.nan))
    y_all = np.array(y_all_list, dtype=float)
    valid_target = ~np.isnan(y_all)
    X_all = X_all[valid_target]
    y_all = y_all[valid_target]

    feat_vec = np.array(
        [feats.get(fn) if feats.get(fn) is not None else np.nan
         for fn in _HEAD_FEATURES],
        dtype=float,
    )
    n_possible = len(_HEAD_FEATURES)
    n_present_pred = int(np.sum(np.isfinite(feat_vec)))
    input_completeness = n_present_pred / n_possible if n_possible > 0 else 0.0

    pred_avail_mask = np.isfinite(feat_vec)

    point: float | None = None
    if pred_avail_mask.any() and len(y_all) >= MIN_TRAIN_OBS:
        X_sel = X_all[:, pred_avail_mask]
        row_complete = ~np.any(np.isnan(X_sel), axis=1)
        X_cc = X_sel[row_complete]
        y_cc = y_all[row_complete]
        x_pred_raw = feat_vec[pred_avail_mask]

        if len(y_cc) >= MIN_TRAIN_OBS:
            try:
                mean_k = np.nanmean(X_cc, axis=0)
                std_k = np.nanstd(X_cc, axis=0, ddof=1)
                std_k[std_k == 0] = 1.0
                Xz = (X_cc - mean_k) / std_k
                xz_pred = (x_pred_raw - mean_k) / std_k
                Xa = np.hstack([Xz, np.ones((len(Xz), 1))])
                xa_pred = np.append(xz_pred, 1.0)
                beta = _ridge_solve(Xa, y_cc)
                point = round(float(xa_pred @ beta), 4)
            except Exception as e:
                log.warning("mf_energy head model failed: %s", e)

    # Baselines
    naive_prior = float(y_all[-1]) if len(y_all) > 0 else None
    expanding_mean_b = float(np.mean(y_all)) if len(y_all) > 0 else None
    trailing_3m_b = (
        float(np.mean(y_all[-3:])) if len(y_all) >= 3
        else (float(np.mean(y_all)) if len(y_all) > 0 else None)
    )

    # Quantiles from walk-forward residuals
    quantiles = _compute_quantiles_mf(errors_arr, point or 0.0, MIN_QUANTILE_OBS)
    if point is None:
        quantiles = {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    # Confidence
    confidence: float | None = None
    if point is not None and len(errors_arr) >= MIN_QUANTILE_OBS:
        sigma_hist = float(np.std(errors_arr, ddof=1)) if len(errors_arr) > 1 else None
        if sigma_hist and sigma_hist > 0:
            interval_width = (quantiles.get("p90") or 0.0) - (quantiles.get("p10") or 0.0)
            sigma_baseline = 1.645 * sigma_hist * 2
            if sigma_baseline > 0:
                interval_rank = 1.0 - interval_width / sigma_baseline
                confidence = round(max(0.0, min(1.0, interval_rank * input_completeness)), 3)

    # Surprise skew
    sigma_surprise: float | None = None
    skew_tag: str | None = None
    sigma_scale_pp: float | None = None
    benchmark_median = None
    if naive_prior is not None and trailing_3m_b is not None:
        benchmark_median = float(np.median([naive_prior, trailing_3m_b]))
    if point is not None and benchmark_median is not None and len(errors_arr) >= 24:
        sigma_realized = float(np.std(errors_arr[-24:], ddof=1))
        if sigma_realized > 0:
            sigma_surprise = round((point - benchmark_median) / sigma_realized, 3)
            sigma_scale_pp = round(sigma_realized, 4)
            if abs(sigma_surprise) <= INLINE_BAND_SIGMA:
                skew_tag = "inline"
            elif sigma_surprise > INLINE_BAND_SIGMA:
                skew_tag = "hotter"
            else:
                skew_tag = "cooler"

    # IDs
    _period = period or f"{ref_month_ts.year}-{ref_month_ts.month:02d}"
    release_id = make_release_id("cpi_headline", _period)
    prediction_id = make_prediction_id(release_id, asof.isoformat())
    inputs_hash = compute_inputs_hash({k: v for k, v in feats.items() if v is not None})

    mf_components = {
        "gasoline_mom": gas_mom,
        "energy_contrib": energy_contrib,
        "exenergy_ar": exenergy_ar,
        "gasoline_ri_weight": GASOLINE_RI_WEIGHT,
        "gamma": gamma,
        "n_gasoline_weeks_published": gas_result["n_weeks_published"],
        "n_gasoline_weeks_projected": gas_result["n_weeks_projected"],
        "gasoline_wti_beta_slope": gas_result["wti_beta_slope"],
        "gasoline_wti_beta_intercept": gas_result["wti_beta_intercept"],
        "gasoline_wti_n_train": gas_result["wti_n_train"],
    }

    return {
        "release": "cpi_headline",
        "model": "mf_energy",
        "asof": asof.isoformat(),
        "cutoff_label": cutoff_label,
        "point": point,
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "confidence": confidence,
        "input_completeness": round(input_completeness, 3),
        "release_id": release_id,
        "prediction_id": prediction_id,
        "inputs_hash": inputs_hash,
        "benchmark_set": {
            "naive_prior": round(naive_prior, 4) if naive_prior is not None else None,
            "expanding_mean": round(expanding_mean_b, 4) if expanding_mean_b is not None else None,
            "trailing_3m": round(trailing_3m_b, 4) if trailing_3m_b is not None else None,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {
            "sigma": sigma_surprise,
            "sigma_scale_pp": sigma_scale_pp,
            "tag": skew_tag,
            "inline_band": INLINE_BAND_SIGMA,
        },
        "mf_energy_components": mf_components,
        "pit_provenance": {
            "revision_optimistic_legs": ["cpi_weights"],
            "unrevised_legs": ["gasoline_weekly", "wti_crude"],
            "absent_legs": [
                k for k, v in feats.items()
                if v is None or (isinstance(v, float) and not np.isfinite(v))
            ],
            "display_only": True,
            "authority": False,
        },
        "display_only": True,
        "authority": False,
    }
