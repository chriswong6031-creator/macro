"""MRI — combined_point v1 forecast-combination layer (MRI-R40).

DISPLAY-ONLY · AUTHORITY=FALSE. Pure arithmetic; no LLM involvement.

Combines tonight's available model points (champion + v3_factor + cpi_bridge +
mf_energy + cleveland) into a single blended forecast using shrunk inverse-MAE
weights with k=3 pool shrinkage.

SPECIFICATION: research/release_forecast/PREREG_COMBINED_POINT_V1.md (frozen 2026-07-14)
AMENDMENT:     research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md, Amendment 2026-07-14
               (MRI-R40)

Formula (§2.3):
  MAE_shrunk_i = ( sum_i |e_i| + k * MAE_pool ) / ( n_i + k ),  k=3 (frozen)
  MAE_pool     = pooled MAE over ALL inputs' scored errors for this release
  w_i          = (1 / MAE_shrunk_i) / sum_j (1 / MAE_shrunk_j)
  combined_point = sum_i w_i * point_i

Cold start: zero scored errors across all inputs → equal weights 1/N.
n_i=0 for input i while others have history → MAE_shrunk_i = MAE_pool (pure prior).
Minimum 2 non-null inputs required; otherwise returns None.

Interval (§2.4):
  Var_w          = sum_i w_i * (point_i − combined_point)^2
  sigma_combined = sqrt(sigma_champion^2 + Var_w)
  p10/p90 = combined_point ∓/± 1.2816 * sigma_combined
  p25/p75 = combined_point ∓/± 0.6745 * sigma_combined
  p50     = combined_point

Anti-mining: k=3 frozen; input list frozen (§2.2 of prereg); quantile multipliers frozen.
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

# Frozen per prereg §2.3 / §6
_K_SHRINKAGE: float = 3.0

# Normal quantile multipliers (frozen per prereg §2.4 / §6)
_Z_P10_P90: float = 1.2816   # ±σ for p10/p90 (Φ⁻¹(0.90))
_Z_P25_P75: float = 0.6745   # ±σ for p25/p75 (Φ⁻¹(0.75))

# Cleveland series map mirrors build_release_forecast._CLEVELAND_SERIES_MAP
_CLEVELAND_SERIES_MAP: dict[str, str] = {
    "cpi_headline": "cpi_mom",
    "cpi_core":     "core_cpi_mom",
}

# Input ids in canonical order per prereg §2.2
_INPUT_IDS = ("champion", "v3_factor", "cpi_bridge", "mf_energy", "cleveland")


# ---------------------------------------------------------------------------
# Core combination formula
# ---------------------------------------------------------------------------

def compute_combined_point(
    inputs: dict[str, float | None],
    scored_errors: dict[str, list[float]],
    sigma_champion: float | None,
) -> dict | None:
    """Compute the combined_v1 forecast from tonight's input points.

    Parameters
    ----------
    inputs : dict[str, float | None]
        Map from input_id to tonight's projected point (None = absent/null).
        Valid input ids: 'champion', 'v3_factor', 'cpi_bridge', 'mf_energy',
        'cleveland'. Any id not in the canonical set is silently ignored.
    scored_errors : dict[str, list[float]]
        Map from input_id to list of SIGNED errors (actual − projection) from
        scored forward-ledger rows. Used to compute MAE per input.
        For 'cleveland', use the signed errors (actual − benchmark_cleveland)
        from champion scored rows.
    sigma_champion : float | None
        Champion sigma_scale_pp (the pp-scale σ from the champion's projection).
        Used in the dispersion interval formula. If None, sigma_combined falls
        back to sqrt(Var_w) only (sigma_champion contribution = 0).

    Returns
    -------
    dict or None
        None when fewer than 2 non-null inputs are available.
        Otherwise a dict with:
          combined_point, p10, p25, p50, p75, p90,
          combined_components (full receipt per prereg §4.1)
    """
    # --- 1. Filter to non-null inputs in canonical order ---
    active_inputs: list[tuple[str, float]] = []
    for iid in _INPUT_IDS:
        if iid not in inputs:
            continue
        val = inputs[iid]
        if val is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fval):
            continue
        active_inputs.append((iid, fval))

    n_active = len(active_inputs)
    if n_active < 2:
        log.debug("combined_v1: fewer than 2 non-null inputs (%d) — returning None", n_active)
        return None

    # --- 2. Compute per-input n_i and individual MAE ---
    # n_i = number of scored rows for input i
    n_by_input: dict[str, int] = {}
    mae_by_input: dict[str, float | None] = {}  # None = no history

    all_abs_errors: list[float] = []
    for iid, _ in active_inputs:
        errs = scored_errors.get(iid, [])
        abs_errs = [abs(float(e)) for e in errs if math.isfinite(float(e))]
        n_by_input[iid] = len(abs_errs)
        mae_by_input[iid] = float(np.mean(abs_errs)) if abs_errs else None
        all_abs_errors.extend(abs_errs)

    # --- 3. MAE_pool: pooled over ALL active inputs' scored errors ---
    mae_pool: float | None = float(np.mean(all_abs_errors)) if all_abs_errors else None

    # --- 4. Cold start detection ---
    # If MAE_pool is None (no scored errors at all), equal weights apply
    is_cold_start = mae_pool is None

    # --- 5. Compute shrunk inverse-MAE weights ---
    weights: dict[str, float] = {}

    if is_cold_start:
        # Equal weights: all MAE_shrunk_i undefined
        eq_w = 1.0 / n_active
        for iid, _ in active_inputs:
            weights[iid] = eq_w
        mae_shrunk_by_input: dict[str, float | None] = {iid: None for iid, _ in active_inputs}
    else:
        assert mae_pool is not None  # guaranteed by is_cold_start=False
        # MAE_shrunk_i = (sum |e_i| + k * MAE_pool) / (n_i + k)
        mae_shrunk_by_input = {}
        inv_mae: dict[str, float] = {}
        for iid, _ in active_inputs:
            ni = n_by_input[iid]
            if ni == 0:
                # n_i=0: MAE_shrunk_i = MAE_pool (pure prior, per prereg §2.3)
                mae_shrunk_i = mae_pool
            else:
                sum_abs = float(np.sum([abs(float(e))
                                        for e in scored_errors.get(iid, [])
                                        if math.isfinite(float(e))]))
                mae_shrunk_i = (sum_abs + _K_SHRINKAGE * mae_pool) / (ni + _K_SHRINKAGE)
            mae_shrunk_by_input[iid] = mae_shrunk_i
            # Guard: mae_shrunk_i should be > 0 (pool > 0 since we have some errors)
            if mae_shrunk_i <= 0:
                log.warning("combined_v1: MAE_shrunk_i=%.6f for %s — using 1e-9", mae_shrunk_i, iid)
                mae_shrunk_i = 1e-9
            inv_mae[iid] = 1.0 / mae_shrunk_i

        total_inv = sum(inv_mae.values())
        if total_inv <= 0:
            log.warning("combined_v1: total inverse-MAE=0 — falling back to equal weights")
            eq_w = 1.0 / n_active
            for iid, _ in active_inputs:
                weights[iid] = eq_w
        else:
            for iid, _ in active_inputs:
                weights[iid] = inv_mae[iid] / total_inv

    # --- 6. Combined point ---
    combined_point = sum(weights[iid] * pt for iid, pt in active_inputs)

    # --- 7. Dispersion interval (prereg §2.4) ---
    # Var_w = sum_i w_i * (point_i − combined_point)^2
    var_w = sum(weights[iid] * (pt - combined_point) ** 2 for iid, pt in active_inputs)

    # §2.5: sigma_champion=None → sigma_champ_sq=0; interval is dispersion-only (sqrt(Var_w)).
    sigma_champ_sq = (float(sigma_champion) ** 2) if (sigma_champion is not None and math.isfinite(float(sigma_champion))) else 0.0
    sigma_combined = math.sqrt(sigma_champ_sq + var_w)

    p50 = combined_point
    p10 = combined_point - _Z_P10_P90 * sigma_combined
    p90 = combined_point + _Z_P10_P90 * sigma_combined
    p25 = combined_point - _Z_P25_P75 * sigma_combined
    p75 = combined_point + _Z_P25_P75 * sigma_combined

    # --- 8. Build the full receipt ---
    combined_components: dict[str, Any] = {
        "inputs_used": [iid for iid, _ in active_inputs],
        "points": {iid: round(pt, 6) for iid, pt in active_inputs},
        "weights": {iid: round(w, 6) for iid, w in weights.items()},
        "n_i": {iid: n_by_input[iid] for iid, _ in active_inputs},
        "MAE_shrunk_i": {
            iid: (round(mae_shrunk_by_input[iid], 6) if mae_shrunk_by_input[iid] is not None else None)
            for iid, _ in active_inputs
        },
        "MAE_pool": round(mae_pool, 6) if mae_pool is not None else None,
        "sigma_champion": round(float(sigma_champion), 6) if (sigma_champion is not None and math.isfinite(float(sigma_champion))) else None,
        "Var_w": round(var_w, 8),
        "sigma_combined": round(sigma_combined, 6),
        "cold_start": is_cold_start,
        "k": _K_SHRINKAGE,
    }

    return {
        "combined_point": round(combined_point, 6),
        "p10": round(p10, 6),
        "p25": round(p25, 6),
        "p50": round(p50, 6),
        "p75": round(p75, 6),
        "p90": round(p90, 6),
        "combined_components": combined_components,
    }


# ---------------------------------------------------------------------------
# Cleveland nowcast reader (PIT-safe)
# ---------------------------------------------------------------------------

def read_cleveland_for_combined(
    root: Path,
    release_type: str,
    period_str: str,
    asof: date,
) -> float | None:
    """Read the Cleveland nowcast for the combined layer, PIT-safe.

    Mirrors the logic in build_release_forecast._read_cleveland_nowcast:
    filter on first_seen_asof <= asof, then take the latest obs_date among
    PIT-eligible rows.

    Only supports cpi_headline (series=cpi_mom) and cpi_core (series=core_cpi_mom).
    Returns None for other release types or if the parquet is absent.
    """
    series = _CLEVELAND_SERIES_MAP.get(release_type)
    if series is None:
        return None

    path = root / "data" / "cleveland_nowcast" / "nowcast.parquet"
    if not path.exists():
        log.debug("cleveland_nowcast parquet absent — returning None")
        return None

    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None

        df["obs_date"] = pd.to_datetime(df["obs_date"])
        df["target_period"] = pd.to_datetime(df["target_period"])
        df["first_seen_asof"] = pd.to_datetime(df["first_seen_asof"])

        target_ts = pd.Timestamp(period_str + "-01")
        asof_ts = pd.Timestamp(asof)

        mask = (
            (df["series"] == series) &
            (df["target_period"] == target_ts) &
            (df["first_seen_asof"] <= asof_ts)
        )
        sub = df[mask]
        if sub.empty:
            return None

        latest_row = sub.loc[sub["obs_date"].idxmax()]
        val = float(latest_row["value"])
        return val if np.isfinite(val) else None

    except Exception as e:
        log.debug("cleveland_nowcast read failed for %s/%s: %s", release_type, period_str, e)
        return None


# ---------------------------------------------------------------------------
# Scored-error extraction helper
# ---------------------------------------------------------------------------

def extract_scored_errors(
    ledger: list[dict],
    release_type: str,
) -> dict[str, list[float]]:
    """Extract per-input signed errors from scored forward-ledger rows.

    For champion (model=None) rows: 'champion' error = actual - frozen_projection_point.
    For shadow rows (model=str): error = actual - frozen_projection_point.
    For cleveland: reads surprise_vs_cleveland from champion scored rows
      (stored as actual − benchmark_cleveland; sign: positive = actual hotter).

    Only rows with row_type='scored' and matching release_type are used.
    Rows with model='combined_v1' are excluded (no circularity).

    Returns dict keyed by input_id → list of signed errors (may be empty lists).
    """
    errors: dict[str, list[float]] = {iid: [] for iid in _INPUT_IDS}

    for row in ledger:
        if row.get("row_type") != "scored":
            continue
        if row.get("release") != release_type:
            continue

        model = row.get("model")

        # Skip combined_v1 scored rows (no circularity)
        if model == "combined_v1":
            continue

        actual = row.get("actual")
        if actual is None:
            continue

        try:
            actual_f = float(actual)
        except (TypeError, ValueError):
            continue

        if model is None:
            # Champion row
            proj_pt = row.get("frozen_projection_point")
            if proj_pt is not None:
                try:
                    err = actual_f - float(proj_pt)
                    if math.isfinite(err):
                        errors["champion"].append(err)
                except (TypeError, ValueError):
                    pass

            # Cleveland error from champion's surprise_vs_cleveland
            # surprise_vs_cleveland = actual − benchmark_cleveland (already a signed error)
            sv_cle = row.get("surprise_vs_cleveland")
            if sv_cle is not None:
                try:
                    sv_f = float(sv_cle)
                    if math.isfinite(sv_f):
                        errors["cleveland"].append(sv_f)
                except (TypeError, ValueError):
                    pass

        elif model in ("v3_factor", "cpi_bridge", "mf_energy"):
            proj_pt = row.get("frozen_projection_point")
            if proj_pt is not None:
                try:
                    err = actual_f - float(proj_pt)
                    if math.isfinite(err):
                        errors[model].append(err)
                except (TypeError, ValueError):
                    pass

    return errors
