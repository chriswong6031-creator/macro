"""engine/cycle_pattern/har.py — Historical Analog Retrieval (HAR) engine.

Pure functions: no I/O, no sklearn/statsmodels/scipy.stats, no random state.
The caller (scripts/run_har1_eval.py) owns all I/O and RNG seeding.

DISTANCE FUNCTION (FROZEN — not fitted to data)
  d(query, analog) = w_traj * L2(trajectory) + w_fp * fingerprint_dist
                   + family_mismatch_penalty * I[family mismatch]

  where:
    trajectory distance = L2 norm of (query_elapsed_grid - analog_elapsed_grid)
      Both grids are the prefix up to elapsed_frac × N_GRID points.
      A query at elapsed fraction f uses the first ceil(f * N_GRID) grid points
      from both query and analog.  Analogs with fewer comparable points than
      the query's elapsed portion are penalized by the `short_analog_penalty`.

    fingerprint distance = L2 on the normalized [fp_quad_*, fp_liq_*,
      fp_vol_pctile] vector.  vol_pctile contributes only if both query and
      analog have non-NaN values; otherwise the vol component is dropped from
      the norm (conservative: fewer dimensions → smaller denominator).

    family_mismatch_penalty: added when query.family != analog.family.
      This is an additive constant, not a flag to exclude — analogs from other
      families are retrievable but ranked lower.

FROZEN WEIGHT CONSTANTS (per preregistration, not tuned):
  W_TRAJ   = 0.70   trajectory weight
  W_FP     = 0.25   macro fingerprint weight
  W_FAM    = 0.15   family-mismatch additive penalty
  The weights sum to > 1.0 intentionally (FP and FAM are separate concerns).

ERA CAP
  max 2 analogs per rolling 24-month window ending at end_date.
  Applied after sorting by distance (keep closest).
  Window: analogs with start_date in [end_date - 24mo, end_date].
  Here end_date is the analog's span end; the 24-month window is
  relative to the analog end_date cluster, not the query date.
  Per DT-R14: k_effective_months is reported as the number of distinct
  calendar months spanned by the retained analogs' end_date values.

WALK-FORWARD DISCIPLINE
  A query at date T may only retrieve analogs whose end_date < T.
  This is enforced by the caller providing a library already filtered
  to end_date < query_date, or by the `cutoff_date` argument.

OUTPUT
  query() returns a dict:
    p10, p25, p50, p75, p90 : remaining-months quantiles of the
      analog-weighted empirical remaining-duration distribution.
    frac_already_turned      : fraction of analogues whose realized_dur_m
      was already exceeded by the query's current age.
    k_effective_months       : number of distinct calendar months in the
      retained analogs' end_date column (DT-R14 honest N).
    n_eras_represented       : number of distinct calendar years in end_date.
    analog_ids               : list of span_id strings (retained analogs).
    analog_distances         : corresponding distances.
    n_candidates             : total eligible analogs before era-cap.
"""
from __future__ import annotations

from math import ceil

import numpy as np
import pandas as pd

# ── FROZEN distance weights (preregistration HAR-1 §18; not fitted) ───────────
W_TRAJ: float = 0.70     # trajectory L2 component weight
W_FP: float = 0.25       # macro fingerprint L2 component weight
W_FAM: float = 0.15      # additive family-mismatch penalty
SHORT_ANALOG_PENALTY: float = 1.0  # added when analog has fewer grid points than query's elapsed portion
ERA_CAP_K: int = 2                  # max analogs per 24-month era window
ERA_WINDOW_M: int = 24              # rolling window length in months
N_GRID: int = 10                    # grid points (0.0, 0.1, …, 0.9)

# Fingerprint columns (order matters for vector construction)
_FP_COLS = [
    "fp_quad_Q1", "fp_quad_Q2", "fp_quad_Q3", "fp_quad_Q4",
    "fp_liq_expanding", "fp_liq_contracting", "fp_liq_neutral",
    "fp_vol_pctile",
]
_TRAJ_COLS = [f"norm_pos_{i}" for i in range(N_GRID)]


def _traj_distance(q_grid: np.ndarray, a_grid: np.ndarray,
                   n_pts: int) -> float:
    """L2 distance on the first n_pts of both normalized trajectories.

    q_grid, a_grid: arrays of length N_GRID (0-100 scale).
    n_pts: number of grid points corresponding to the elapsed portion.
    Returns normalized L2 (divided by n_pts * 100 to keep in [0, ~√n]).
    """
    if n_pts <= 0:
        return 0.0
    diff = q_grid[:n_pts] - a_grid[:n_pts]
    return float(np.sqrt(np.sum(diff ** 2)) / (n_pts * 100.0))


def _fp_distance(q_fp: np.ndarray, a_fp: np.ndarray,
                 mask: np.ndarray) -> float:
    """L2 on the fingerprint vector, restricted to valid (non-NaN) dims.

    mask: boolean array, True where BOTH q and a have non-NaN values.
    """
    if not mask.any():
        return 0.0
    diff = (q_fp - a_fp)[mask]
    return float(np.sqrt(np.sum(diff ** 2)))


def _build_fp_vector(row) -> np.ndarray:
    """Extract fingerprint vector from a library row (Series or dict-like)."""
    vals = []
    for col in _FP_COLS:
        if hasattr(row, "index"):
            v = row[col] if col in row.index else float("nan")
        else:
            v = row.get(col, float("nan"))
        vals.append(float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else float("nan"))
    return np.array(vals, dtype=float)


def _apply_era_cap(
    candidates: pd.DataFrame,
    distances: np.ndarray,
    k: int,
    era_cap: int,
    era_window_m: int,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Apply era-cap: at most `era_cap` analogs per rolling `era_window_m`-month
    window (based on end_date).  Sort by distance ascending; greedily select.

    Returns (filtered_candidates, filtered_distances).
    """
    order = np.argsort(distances)
    sorted_cands = candidates.iloc[order].reset_index(drop=True)
    sorted_dists = distances[order]

    selected_idx: list[int] = []
    # Track end_dates of selected analogs for era-window checking
    selected_end_dates: list[pd.Timestamp] = []

    for i in range(len(sorted_cands)):
        end_d = pd.Timestamp(sorted_cands.iloc[i]["end_date"])
        # Count how many already-selected analogs have end_date in the 24-month
        # window [end_d - 24mo, end_d + 24mo] (rolling symmetric window centered
        # on this analog's end_date — conservative: avoids edge asymmetry)
        window_count = sum(
            1 for s in selected_end_dates
            if abs((end_d - s).days) <= era_window_m * 30.44
        )
        if window_count < era_cap:
            selected_idx.append(i)
            selected_end_dates.append(end_d)
        if len(selected_idx) >= k:
            break

    sel = sorted_cands.iloc[selected_idx].reset_index(drop=True)
    sel_dists = sorted_dists[selected_idx]
    return sel, sel_dists


def query(
    current_age_m: float,
    current_pos_grid: np.ndarray,
    current_family: str,
    current_fp: np.ndarray,
    library: pd.DataFrame,
    *,
    k: int = 6,
    era_cap: int = ERA_CAP_K,
    era_window_m: int = ERA_WINDOW_M,
    cutoff_date: pd.Timestamp | None = None,
) -> dict:
    """Retrieve the k nearest analogs and return the remaining-time distribution.

    Parameters
    ----------
    current_age_m : float
        Age in months of the current (open) half-cycle at query time.
    current_pos_grid : np.ndarray, shape (N_GRID,)
        Normalized pos values at the N_GRID elapsed-fraction grid points,
        for the elapsed portion of the current half-cycle.
    current_family : str
        Family of the queried entity (us_sector / country / cn_sector).
    current_fp : np.ndarray, shape (len(_FP_COLS),)
        Macro fingerprint vector for the current half-cycle.
    library : pd.DataFrame
        The analog library (from build_analog_library.py).
        Walk-forward: caller must pre-filter to rows with end_date < query_date,
        OR pass cutoff_date to have this function filter.
    k : int
        Number of analogs to retrieve.
    era_cap : int
        Max analogs per rolling era window (default 2).
    era_window_m : int
        Rolling era window in months (default 24).
    cutoff_date : pd.Timestamp, optional
        If provided, filter library to end_date < cutoff_date (walk-forward
        discipline).  If None, the caller is responsible for pre-filtering.

    Returns
    -------
    dict with keys:
        p10, p25, p50, p75, p90  : quantiles of remaining months to turn
        frac_already_turned      : fraction of analogs already exceeded by age
        k_effective_months       : distinct calendar months in analogs' end_date
        n_eras_represented       : distinct calendar years in analogs' end_date
        analog_ids               : list[str]
        analog_distances         : list[float]
        n_candidates             : int (eligible before era-cap)
    """
    lib = library.copy()

    # Walk-forward filter
    if cutoff_date is not None:
        lib = lib[pd.to_datetime(lib["end_date"]) < cutoff_date].reset_index(drop=True)

    if len(lib) == 0:
        return _empty_result()

    # Elapsed fraction of the current half-cycle
    # We use the current grid as-is (caller fills to N_GRID)
    # Number of grid points to compare = proportional to min(age_m / estimated_dur, 1)
    # Use a simple heuristic: compare all N_GRID points available
    # (the caller supplies the full grid based on elapsed fraction)
    elapsed_frac = min(1.0, current_age_m / max(
        lib["realized_dur_m"].median(), 1.0))
    n_pts = max(1, ceil(elapsed_frac * N_GRID))

    # Compute distances
    lib_traj = lib[_TRAJ_COLS].values.astype(float)  # (N_lib, N_GRID)
    q_traj = current_pos_grid.astype(float)

    # Trajectory distances
    traj_dists = np.array([
        _traj_distance(q_traj, lib_traj[i], n_pts)
        for i in range(len(lib))
    ])

    # Fingerprint distances
    lib_fp = lib[_FP_COLS].values.astype(float)  # (N_lib, len(_FP_COLS))
    q_fp = current_fp.astype(float)

    fp_dists = np.array([
        _fp_distance(
            q_fp, lib_fp[i],
            mask=~(np.isnan(q_fp) | np.isnan(lib_fp[i])),
        )
        for i in range(len(lib))
    ])

    # Family mismatch penalty
    fam_penalty = np.array([
        W_FAM if str(row["family"]) != current_family else 0.0
        for _, row in lib.iterrows()
    ])

    # Short-analog penalty: when n_rows < n_pts, the analog's elapsed portion
    # is shorter than what we want to compare → penalize
    short_penalty = np.array([
        SHORT_ANALOG_PENALTY if int(row["n_rows"]) < n_pts else 0.0
        for _, row in lib.iterrows()
    ])

    distances = (W_TRAJ * traj_dists + W_FP * fp_dists
                 + fam_penalty + short_penalty)

    n_candidates = int(len(lib))

    # Era-cap application
    sel, sel_dists = _apply_era_cap(lib, distances, k, era_cap, era_window_m)

    if len(sel) == 0:
        return _empty_result()

    # Remaining-time distribution
    remaining_m = sel["realized_dur_m"].values - current_age_m
    # Clamp negatives to 0 (already turned analog)
    remaining_m_clamped = np.maximum(remaining_m, 0.0)

    p10 = float(np.percentile(remaining_m_clamped, 10))
    p25 = float(np.percentile(remaining_m_clamped, 25))
    p50 = float(np.percentile(remaining_m_clamped, 50))
    p75 = float(np.percentile(remaining_m_clamped, 75))
    p90 = float(np.percentile(remaining_m_clamped, 90))

    frac_already_turned = float((remaining_m < 0).sum() / len(remaining_m))

    # DT-R14: k_effective_months = distinct calendar months spanned by analogs' end_dates
    end_dates = pd.to_datetime(sel["end_date"])
    k_eff_months = int(end_dates.dt.to_period("M").nunique())
    n_eras = int(end_dates.dt.year.nunique())

    return {
        "p10": p10,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "p90": p90,
        "frac_already_turned": frac_already_turned,
        "k_effective_months": k_eff_months,
        "n_eras_represented": n_eras,
        "analog_ids": list(sel["span_id"].values),
        "analog_distances": [round(float(d), 6) for d in sel_dists],
        "n_candidates": n_candidates,
    }


def _empty_result() -> dict:
    return {
        "p10": float("nan"),
        "p25": float("nan"),
        "p50": float("nan"),
        "p75": float("nan"),
        "p90": float("nan"),
        "frac_already_turned": float("nan"),
        "k_effective_months": 0,
        "n_eras_represented": 0,
        "analog_ids": [],
        "analog_distances": [],
        "n_candidates": 0,
    }


def crps_normal_approximation(
    p10: float, p25: float, p50: float, p75: float, p90: float,
    realized: float,
) -> float:
    """CRPS for a distribution specified by its quantiles, evaluated at a realized value.

    Uses the 5-point quantile-based CRPS approximation:
      CRPS ≈ mean_{q in {0.1, 0.25, 0.5, 0.75, 0.9}}
               2 * q * (y - F_inv(q)) * I[y >= F_inv(q)]
             + 2*(1-q) * (F_inv(q) - y) * I[y < F_inv(q)]
    This is the pinball (quantile) loss averaged over the quantile grid.
    Returns NaN if any quantile is NaN.
    """
    if any(np.isnan(v) for v in (p10, p25, p50, p75, p90)):
        return float("nan")
    quantiles = np.array([0.10, 0.25, 0.50, 0.75, 0.90])
    forecasts = np.array([p10, p25, p50, p75, p90])
    y = realized
    scores = []
    for q, f in zip(quantiles, forecasts):
        if y >= f:
            scores.append(2 * q * (y - f))
        else:
            scores.append(2 * (1 - q) * (f - y))
    return float(np.mean(scores))


def km_remaining_quantiles(
    age_m: float,
    km_by_month: list[dict],
    quantiles: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90),
) -> dict[str, float]:
    """Compute remaining-time quantiles from a KM by-month table.

    Given current age_m, the KM S(t) gives P(turn > t | turn > age_m).
    The conditional survival is S(t) / S(age_m) for t > age_m.
    We invert to get quantiles of remaining time.

    km_by_month: list of {'age_m': int, 'survival': float, ...}
    Returns dict with keys 'p10', 'p25', 'p50', 'p75', 'p90'.
    """
    # Build (t, S(t)) arrays from the table
    t_arr = np.array([row["age_m"] for row in km_by_month], dtype=float)
    s_arr = np.array([row["survival"] for row in km_by_month], dtype=float)

    # S(age_m): interpolate at current age
    if age_m <= t_arr[0]:
        s_age = 1.0
    elif age_m >= t_arr[-1]:
        s_age = float(s_arr[-1])
    else:
        s_age = float(np.interp(age_m, t_arr, s_arr))

    if s_age <= 0:
        # Already beyond survival support — remaining time ≈ 0
        return {f"p{int(q*100)}": 0.0 for q in quantiles}

    result = {}
    for q in quantiles:
        # Find remaining time r such that P(turn <= age_m + r | turn > age_m) = q
        # => S(age_m + r) = S(age_m) * (1 - q)
        target_s = s_age * (1.0 - q)
        if target_s <= s_arr[-1]:
            # Beyond table: extrapolate flat (last hazard rate)
            r = float(t_arr[-1] - age_m) + 1.0  # conservative: add 1 month
        elif target_s >= s_arr[0]:
            r = 0.0
        else:
            # Interpolate: find t where S(t) = target_s
            t_val = float(np.interp(target_s, s_arr[::-1], t_arr[::-1]))
            r = max(0.0, t_val - age_m)
        result[f"p{int(q*100)}"] = r

    return result


def median_halfcycle_remaining(
    age_m: float,
    family: str,
    direction: str,
    km_baseline: dict,
) -> dict[str, float]:
    """Frozen median-half-cycle projection (null #1).

    Uses the family-stratified KM from km_baseline_price_c4414dcb.json.
    Returns remaining-time quantiles {p10, p25, p50, p75, p90}.
    """
    fam_data = km_baseline.get("families", {}).get(family, {})
    dir_data = fam_data.get(direction, {})
    km_by_month = dir_data.get("km_by_month", [])
    if not km_by_month:
        return {f"p{int(q*100)}": float("nan")
                for q in (0.10, 0.25, 0.50, 0.75, 0.90)}
    return km_remaining_quantiles(age_m, km_by_month)
