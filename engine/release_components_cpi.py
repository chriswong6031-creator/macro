"""MRI — CPI feature builders (split from engine/release_forecast.py for PR-G parallel work).

LEAF · DISPLAY-ONLY. Pure numpy/pandas only.

All public functions here were previously defined inline in engine/release_forecast.py.
engine/release_forecast.py imports from this module — callers that import from
engine.release_forecast see no change.

SPECIFICATION: research/release_forecast/PREREG_V1.md (frozen 2026-07-07) for V1 features.
                research/release_forecast/PREREG_V2.md (frozen 2026-07-07) for V2 additions:
                  shelter stock-adjustment leg, component contributions, confidence_v2.

Anti-mining: two spec attempts, both frozen before results were observed.

PIT LAW: a feature value is usable at decision date D only if its ALFRED
realtime_start <= D. The `knowable_series` function (engine/release_forecast.py)
enforces this filter. Non-vintaged series (CUSR0000SAH1, ZORI) are declared as
revision_optimistic_legs per the PIT law. ZORI uses a conservative +45-day lag.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Block definitions (frozen per PREREG_V2.md §4.1)
# ---------------------------------------------------------------------------
# Maps feature_name -> block_name
_FEATURE_BLOCK_MAP: dict[str, str] = {
    "gasoline_mom": "energy",
    "shelter_nowcast": "shelter",
    "cpi_hl_mom_lag1": "core_persistence",
    "cpi_hl_mom_lag2": "core_persistence",
    "cpi_hl_mom_lag3": "core_persistence",
    "cpi_core_mom_lag1": "core_persistence",
    "cpi_core_mom_lag2": "core_persistence",
    "cpi_core_mom_lag3": "core_persistence",
    "sticky_mom_lag1": "core_persistence",
    "median_mom_lag1": "core_persistence",
    "flex_mom_lag1": "core_persistence",
    "ppi_mom_lag1": "pipeline",
}

# Confidence weights per block (frozen per PREREG_V2.md §4.2)
_BLOCK_CONFIDENCE_WEIGHT: dict[str, float] = {
    "energy": 1.0,       # known — direct price for reference month
    "shelter": 0.6,      # proxy — ZORI leads by ~6m
    "pipeline": 0.6,     # proxy — leading indicator
    "core_persistence": 0.0,  # residual — autocorrelation structure
}

# ZORI PIT conservative lag in days (frozen per PREREG_V2.md §1.1)
_ZORI_LAG_DAYS = 45

# Shelter blending weight k (frozen per PREREG_V2.md §2.4)
_SHELTER_K_BASE = 0.35

# Divergence guard: halve k if divergence > N sigma (frozen per PREREG_V2.md §2.5)
_DIVERGENCE_GUARD_SIGMA = 3.0
_DIVERGENCE_GUARD_WINDOW = 24  # months for rolling std

# ---------------------------------------------------------------------------
# Feature plausibility bounds (FIX 2 — range guard)
# Values outside these ranges indicate data/unit errors and are set to None.
# Bounds are generous enough to cover any real historical reading; they only
# catch pathological magnitudes (e.g. double-differencing a rate series).
# ---------------------------------------------------------------------------
_FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    # CPI/PCE family MoM % — generous ±3 pp covers all post-1980 history
    "cpi_hl_mom_lag1":     (-3.0, 3.0),
    "cpi_hl_mom_lag2":     (-3.0, 3.0),
    "cpi_hl_mom_lag3":     (-3.0, 3.0),
    "cpi_core_mom_lag1":   (-3.0, 3.0),
    "cpi_core_mom_lag2":   (-3.0, 3.0),
    "cpi_core_mom_lag3":   (-3.0, 3.0),
    # Sticky/median/flex monthly-equivalent — covers 2022 peaks with headroom
    # sticky: max 0.681 (2022-09); ±3.0 generous
    # median (monthly-equiv after de-annualization): peak ≈ 0.74%; ±3.0 generous
    # flex: max 3.423 (2022-03); ±5.0 needed to cover that extreme
    "sticky_mom_lag1":     (-3.0, 3.0),
    "median_mom_lag1":     (-3.0, 3.0),
    "flex_mom_lag1":       (-5.0, 5.0),
    # PPI Final Demand MoM — more volatile; ±5 pp covers historical extremes
    "ppi_mom_lag1":        (-5.0, 5.0),
    # Gasoline MoM — 2008-11 crash printed −29.64% (GASREGW monthly avg); ±40 keeps
    # real crisis readings inside the fence with margin
    "gasoline_mom":        (-40.0, 40.0),
    # Shelter nowcast — blend of ZORI+BLS shelter, ±3 pp is generous
    "shelter_nowcast":     (-3.0, 3.0),
    # --- v11 target-family features (engine/release_targets_v11.py builders) ---
    # PCE own-lag MoM % (PCEPI / PCEPILFE first prints). Real extremes in
    # vintages.parquet: PCEPI -1.146 (2008-11) / +0.969 (2008-06); PCEPILFE
    # -0.836 (2001-09) / +1.204 (2001-10). ±3.0 keeps every real crisis reading
    # with >2x headroom while fencing NIPA comprehensive-revision rebase seams
    # (2003-11 / 2009-06 / 2013-06 / 2018-06 / 2023-08 first-print MoM prints
    # -4.4..-10.1 — pct_change across an index re-base, not real inflation).
    "pce_hl_mom_lag1":     (-3.0, 3.0),
    "pce_hl_mom_lag2":     (-3.0, 3.0),
    "pce_hl_mom_lag3":     (-3.0, 3.0),
    "pce_core_mom_lag1":   (-3.0, 3.0),
    "pce_core_mom_lag2":   (-3.0, 3.0),
    "pce_core_mom_lag3":   (-3.0, 3.0),
    # PPI Final Demand / ex-F&E MoM % — same physical series as ppi_mom_lag1
    # above (PPIFIS; vintages from 2014-02, no re-base seams). Extremes:
    # PPIFIS -1.266 (2020-04) / +1.630 (2022-03); PPIFES -0.459 / +1.269.
    # ±5 matches the existing PPI family bound.
    "ppi_hl_mom_lag1":     (-5.0, 5.0),
    "ppi_hl_mom_lag2":     (-5.0, 5.0),
    "ppi_hl_mom_lag3":     (-5.0, 5.0),
    "ppifis_mom_lag1":     (-5.0, 5.0),
    "ppifes_mom_lag1":     (-5.0, 5.0),
}


def _apply_range_guard(
    features: dict[str, float | None],
    legs: dict,
) -> dict[str, float | None]:
    """Apply plausibility bounds to features in-place; tag violations in legs dict.

    For each feature in _FEATURE_BOUNDS: if the value is outside [lo, hi],
    set it to None and record "range_violation" in legs["range_violation_legs"].
    Logs a warning for each violation.

    Returns the mutated features dict.
    """
    violations = legs.setdefault("range_violation_legs", [])
    for feat, (lo, hi) in _FEATURE_BOUNDS.items():
        v = features.get(feat)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not (lo <= fv <= hi):
            log.warning(
                "Range guard: feature %r = %.4f outside [%.1f, %.1f]; "
                "setting to None (plausibility violation).",
                feat, fv, lo, hi,
            )
            features[feat] = None
            violations.append(feat)
    return features


# ---------------------------------------------------------------------------
# ZORI helpers
# ---------------------------------------------------------------------------

def _load_zori_national(root: Path) -> pd.DataFrame | None:
    """Load ZORI national parquet. Returns None if absent."""
    zori_path = root / "data" / "zori" / "national.parquet"
    if not zori_path.exists():
        return None
    try:
        df = pd.read_parquet(zori_path)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        log.debug("ZORI load failed: %s", e)
        return None


def _compute_zori_signal(
    zori_df: pd.DataFrame,
    target_month: pd.Timestamp,
    asof: date,
) -> float | None:
    """Compute ZORI lease-reset signal for target month M.

    Lease-reset window: months M-12 through M-6 (inclusive, 7 calendar months).
    PIT filter: only ZORI rows where date + 45 days <= asof are usable.
    Returns mean ZORI MoM (%) over the window months with PIT-filtered data.
    Returns None if fewer than 3 window months have PIT-filtered data.

    SPEC: PREREG_V2.md §2.2
    """
    asof_ts = pd.Timestamp(asof)
    target_m = target_month.to_period("M")

    # Build window: M-12 through M-6 (7 months)
    window_months = []
    for k in range(6, 13):  # k=6..12 inclusive → M-6..M-12
        window_months.append((target_m - k).to_timestamp(how="E"))  # end-of-month

    # Filter ZORI by PIT lag: date + 45 days <= asof
    pit_mask = zori_df.index + pd.Timedelta(days=_ZORI_LAG_DAYS) <= asof_ts
    zori_pit = zori_df[pit_mask].copy()

    if zori_pit.empty:
        return None

    # Need at least one prior month for each window month to compute MoM
    # Compute MoM on the full PIT-filtered series
    zori_pit_sorted = zori_pit.sort_index()
    zori_col = zori_pit_sorted.columns[0]
    zori_mom = zori_pit_sorted[zori_col].pct_change() * 100.0

    # Collect MoM values for window months
    mom_vals = []
    for wm in window_months:
        # Match by year+month (end-of-month dates may vary by ±1 day)
        wm_ym = (wm.year, wm.month)
        candidates = [
            (idx, val)
            for idx, val in zip(zori_mom.index, zori_mom.values)
            if (idx.year, idx.month) == wm_ym and not np.isnan(val)
        ]
        if candidates:
            mom_vals.append(candidates[0][1])

    if len(mom_vals) < 3:
        return None

    return float(np.mean(mom_vals))


def _get_shelter_mom_last(
    shelter_df: pd.DataFrame,
    asof: date,
) -> tuple[float | None, list[float]]:
    """Get last-knowable CPI shelter MoM at asof, plus history for divergence guard.

    Returns (last_mom, history_list) where history_list is all knowable MoM values
    sorted chronologically (for rolling std computation).

    shelter_df: CUSR0000SAH1 parquet (DatetimeIndex, column 'cpi_shelter').

    KNOWABILITY LAW (B1 fix — restores PREREG_V2.md §2.3 intent):
      CUSR0000SAH1 releases with the CPI on release day for month M.
      At step_asof (the day BEFORE month M's CPI release, which falls in month M+1),
      the last knowable shelter observation is for month M-1.
      In calendar terms: last usable shelter month <= (asof_period - 2 months).
      This mirrors the own-lag convention in run_walk_forward_full where
      the step's 'period' is M and asof is set to the day before M's release date.

    AMENDMENT NOTE (2026-07-07): prior code used `index <= asof_ts` which admitted
      shelter months M and M+1 from the latest-revised parquet — a look-ahead leak
      of up to 2 months beyond what is knowable at decision date. This fix restores
      the frozen PREREG_V2.md §2.3 spec. Bug fix, not a new spec attempt.
    """
    asof_ts = pd.Timestamp(asof)
    col = shelter_df.columns[0]
    # Knowability cap: last usable shelter month is (asof_period - 2).
    # asof is in month M+1 (day before target release); M+1 - 2 = M-1 (the prior release).
    asof_period = asof_ts.to_period("M")
    cutoff_period = asof_period - 2
    cutoff_ts = cutoff_period.to_timestamp(how="E")  # end-of-month for inclusive comparison
    known = shelter_df[shelter_df.index <= cutoff_ts].sort_index()
    if len(known) < 2:
        return None, []
    mom = known[col].pct_change() * 100.0
    mom = mom.dropna()
    if mom.empty:
        return None, []
    history = [float(v) for v in mom.values]
    return float(mom.iloc[-1]), history


def _compute_shelter_nowcast(
    zori_df: pd.DataFrame | None,
    shelter_df: pd.DataFrame | None,
    target_month: pd.Timestamp,
    asof: date,
) -> tuple[float | None, dict]:
    """Compute the shelter_nowcast feature value and provenance.

    Returns (shelter_nowcast_value, shelter_prov_dict).

    SPEC: PREREG_V2.md §2.4, §2.5, §2.6
    """
    prov: dict[str, Any] = {
        "zori_signal": None,
        "cpi_shelter_mom_last": None,
        "shelter_k_applied": None,
        "zori_signal_absent": False,
        "shelter_absent": False,
        "zori_months_used": 0,
        "divergence_guard_triggered": False,
    }

    # Get CPI shelter MoM
    shelter_mom_last: float | None = None
    shelter_history: list[float] = []
    if shelter_df is not None:
        shelter_mom_last, shelter_history = _get_shelter_mom_last(shelter_df, asof)

    prov["cpi_shelter_mom_last"] = shelter_mom_last

    # Get ZORI signal
    zori_signal: float | None = None
    if zori_df is not None:
        # Count usable months for provenance
        asof_ts = pd.Timestamp(asof)
        pit_mask = zori_df.index + pd.Timedelta(days=_ZORI_LAG_DAYS) <= asof_ts
        zori_pit = zori_df[pit_mask]
        target_m = pd.Timestamp(target_month).to_period("M")
        window_months = [(target_m - k).to_timestamp(how="E") for k in range(6, 13)]
        n_usable = 0
        zori_pit_sorted = zori_pit.sort_index()
        if not zori_pit_sorted.empty:
            for wm in window_months:
                wm_ym = (wm.year, wm.month)
                if any((idx.year, idx.month) == wm_ym for idx in zori_pit_sorted.index):
                    n_usable += 1
        prov["zori_months_used"] = n_usable

        zori_signal = _compute_zori_signal(zori_df, pd.Timestamp(target_month), asof)

    prov["zori_signal"] = zori_signal

    # Fallback logic per PREREG_V2.md §2.6
    if zori_signal is None:
        prov["zori_signal_absent"] = True
        if shelter_mom_last is None:
            prov["shelter_absent"] = True
            return None, prov
        # Pure BLS momentum fallback (k=0)
        prov["shelter_k_applied"] = 0.0
        return shelter_mom_last, prov

    if shelter_mom_last is None:
        # Have ZORI but no BLS shelter momentum — use ZORI only (k=1.0 effectively)
        prov["shelter_k_applied"] = 1.0
        prov["shelter_absent"] = False
        return float(zori_signal), prov

    # Both available — blend with divergence guard
    k = _SHELTER_K_BASE

    # Divergence guard: rolling 24m std of cpi_shelter_mom_last
    if len(shelter_history) >= _DIVERGENCE_GUARD_WINDOW:
        sigma_shelter = float(np.std(shelter_history[-_DIVERGENCE_GUARD_WINDOW:], ddof=1))
        if sigma_shelter > 0:
            divergence = abs(zori_signal - shelter_mom_last)
            if divergence > _DIVERGENCE_GUARD_SIGMA * sigma_shelter:
                k = k / 2.0  # halve to 0.175
                prov["divergence_guard_triggered"] = True

    prov["shelter_k_applied"] = round(k, 4)
    nowcast = (1.0 - k) * shelter_mom_last + k * zori_signal
    return float(nowcast), prov


# ---------------------------------------------------------------------------
# Component contribution helpers
# ---------------------------------------------------------------------------

def compute_components(
    feature_names: list[str],
    beta: np.ndarray,
    z_features: np.ndarray,
    avail_mask: np.ndarray,
    release_type: str,
) -> list[dict] | None:
    """Compute per-block component contributions.

    feature_names: all feature names for the model (may include ones not in avail_mask).
    beta: fitted ridge coefficients, shape (n_avail_features + 1,) where last is bias.
    z_features: z-scored feature values for available features, shape (n_avail_features,).
    avail_mask: boolean mask of shape (len(feature_names),) indicating which features are available.
    release_type: 'cpi_headline' or 'cpi_core'.

    Returns list of component dicts per PREREG_V2.md §4.3, or None on failure.

    SPEC: PREREG_V2.md §4.1, §4.3
    """
    try:
        # beta: (n_avail,) — feature coefficients only (bias excluded; returned by _ridge_predict_with_components).
        # contrib_pp[j] = beta[j] * z_features[j]
        n_avail = int(avail_mask.sum())
        if n_avail == 0 or len(beta) < n_avail:
            return None

        beta_feat = beta[:n_avail]
        contrib_pp_avail = beta_feat * z_features  # shape (n_avail,)

        # Map back to original feature positions
        avail_indices = np.where(avail_mask)[0]

        # Aggregate by block
        block_contribs: dict[str, float] = {}
        for j, orig_idx in enumerate(avail_indices):
            fn = feature_names[orig_idx]
            block = _FEATURE_BLOCK_MAP.get(fn, "core_persistence")
            block_contribs[block] = block_contribs.get(block, 0.0) + float(contrib_pp_avail[j])

        if not block_contribs:
            return None

        components = []
        for block_name in ["energy", "shelter", "core_persistence", "pipeline"]:
            if block_name not in block_contribs:
                continue
            if release_type == "cpi_core" and block_name == "energy":
                continue  # gasoline excluded from core
            components.append({
                "name": block_name,
                "contrib_pp": round(float(block_contribs[block_name]), 6),
                "confidence": _BLOCK_CONFIDENCE_WEIGHT[block_name],
            })

        return components if components else None

    except Exception as e:
        log.debug("compute_components failed: %s", e)
        return None


def compute_confidence_v2(
    components: list[dict] | None,
    input_completeness: float,
) -> tuple[float | None, dict | None]:
    """Compute confidence_v2 and confidence_components_v2.

    Returns (confidence_v2, confidence_components_v2_dict).

    SPEC: PREREG_V2.md §4.2
    """
    if not components:
        return None, None

    total_abs = sum(abs(c["contrib_pp"]) for c in components)
    if total_abs == 0.0:
        return 0.0, {
            "w_known": 0.0, "w_proxy": 0.0, "w_residual": 0.0,
            "c_raw": 0.0, "input_completeness": round(input_completeness, 4),
        }

    w_known = 0.0
    w_proxy = 0.0
    w_residual = 0.0
    c_raw = 0.0

    for comp in components:
        w_block = abs(comp["contrib_pp"]) / total_abs
        cw = comp["confidence"]  # 1.0, 0.6, or 0.0
        c_raw += w_block * cw
        if cw == 1.0:
            w_known += w_block
        elif cw == 0.6:
            w_proxy += w_block
        else:
            w_residual += w_block

    confidence_v2 = round(float(c_raw) * input_completeness, 4)

    comps_v2 = {
        "w_known": round(w_known, 4),
        "w_proxy": round(w_proxy, 4),
        "w_residual": round(w_residual, 4),
        "c_raw": round(c_raw, 4),
        "input_completeness": round(input_completeness, 4),
    }

    return confidence_v2, comps_v2


# ---------------------------------------------------------------------------
# Main feature builder
# ---------------------------------------------------------------------------

def build_cpi_features(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    release_type: str = "cpi_headline",
    ref_month: date | pd.Timestamp | None = None,
    *,
    # injected to avoid circular import
    knowable_series_fn,
    last_n_mom_lags_fn,
    last_n_rate_lags_fn,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for CPI prediction at decision date asof.

    V2: adds shelter_nowcast leg (PREREG_V2.md §2, §3).

    release_type: 'cpi_headline' or 'cpi_core'.
    ref_month: the CPI reference month M the target print covers (PREREG_V1.md §2.3
        feature 7 anchors gasoline_mom on M, not on asof's calendar month — at the
        decision date asof is already inside M+1). When None, derived as the month
        after the last knowable own-series initial print.
    knowable_series_fn / last_n_mom_lags_fn / last_n_rate_lags_fn: injected from
        engine.release_forecast to avoid circular imports.
        last_n_rate_lags_fn: used for series already published as % rates
        (sticky/flex monthly %, median annualized %) — no pct_change applied.
    Returns (features_dict, provenance_dict).
    features_dict: {feature_name: value_or_None}
    provenance_dict: {revision_optimistic_legs, unrevised_legs, absent_legs, ...}
    """
    absent_legs: list[str] = []
    # vintaged_legs: ALFRED first-print legs actually used — own lags + sticky/median/flex + PPI.
    # These are the legs that DO have ALFRED vintages and are enumerated here so that
    # compute_coverage_flags sees the full declared-leg set (MRI-R26 honesty, rework-2a fix).
    if release_type == "cpi_headline":
        _vintaged_legs = [
            "cpi_hl_mom_lag1", "cpi_hl_mom_lag2", "cpi_hl_mom_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1",
        ]
    else:
        _vintaged_legs = [
            "cpi_core_mom_lag1", "cpi_core_mom_lag2", "cpi_core_mom_lag3",
            "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
            "ppi_mom_lag1",
        ]
    prov: dict[str, Any] = {
        "revision_optimistic_legs": ["shelter_nowcast"],  # CUSR0000SAH1 + ZORI both revision-optimistic
        "vintaged_legs": _vintaged_legs,
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
    own_lags = last_n_mom_lags_fn(vintages, own_series, asof, n=3)
    features: dict[str, float | None] = {
        f"{lag_key}_lag1": own_lags[0],
        f"{lag_key}_lag2": own_lags[1],
        f"{lag_key}_lag3": own_lags[2],
    }

    # Sticky CPI (2014-03+) — series published as monthly % directly; no pct_change
    sticky_lags = last_n_rate_lags_fn(vintages, "STICKCPIM157SFRBATL", asof, n=1, annualized=False)
    features["sticky_mom_lag1"] = sticky_lags[0]

    # Median CPI (2014-02+) — series published as ANNUALIZED monthly %; de-annualize to monthly-equiv
    median_lags = last_n_rate_lags_fn(vintages, "MEDCPIM158SFRBCLE", asof, n=1, annualized=True)
    features["median_mom_lag1"] = median_lags[0]

    # Flexible CPI (2014-03+) — series published as monthly % directly; no pct_change
    flex_lags = last_n_rate_lags_fn(vintages, "FLEXCPIM157SFRBATL", asof, n=1, annualized=False)
    features["flex_mom_lag1"] = flex_lags[0]

    # PPI Final Demand (2014-03+)
    ppi_lags = last_n_mom_lags_fn(vintages, "PPIFIS", asof, n=1)
    features["ppi_mom_lag1"] = ppi_lags[0]

    # Gasoline (headline only; fail-open if absent) — V1 unchanged
    if release_type == "cpi_headline":
        prov["unrevised_legs"].append("gasoline_mom")
        gasregw_path = root / "data" / "fred" / "GASREGW.parquet"
        if gasregw_path.exists():
            try:
                gasregw = pd.read_parquet(gasregw_path)
                gasregw.index = pd.to_datetime(gasregw.index)
                asof_ts = pd.Timestamp(asof)
                # Anchor on the reference month M the target print covers
                if ref_month is None:
                    own_prints = knowable_series_fn(vintages, own_series, asof)
                    if own_prints.empty:
                        raise ValueError("no knowable prints to derive ref_month")
                    ref_start = (
                        pd.Timestamp(own_prints["period"].iloc[-1]).to_period("M") + 1
                    ).to_timestamp()
                else:
                    ref_start = pd.Timestamp(ref_month).to_period("M").to_timestamp()
                ref_end = ref_start + pd.offsets.MonthBegin(1)
                prior_start = ref_start - pd.offsets.MonthBegin(1)
                gasregw_col = gasregw.columns[0]
                cur_hi = min(ref_end, asof_ts)
                cur_m_mask = (gasregw.index >= ref_start) & (gasregw.index < cur_hi)
                prior_m_mask = (gasregw.index >= prior_start) & (gasregw.index < ref_start)
                cur_avg = gasregw.loc[cur_m_mask, gasregw_col].mean() if cur_m_mask.any() else np.nan
                prior_avg = gasregw.loc[prior_m_mask, gasregw_col].mean() if prior_m_mask.any() else np.nan
                prov["gasoline_ref_month"] = str(ref_start.date())
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

    # Shelter leg — V2 NEW (PREREG_V2.md §2, §3)
    # Load data sources
    zori_df = _load_zori_national(root)
    shelter_path = root / "data" / "fred" / "CUSR0000SAH1.parquet"
    shelter_df: pd.DataFrame | None = None
    if shelter_path.exists():
        try:
            shelter_df = pd.read_parquet(shelter_path)
            shelter_df.index = pd.to_datetime(shelter_df.index)
        except Exception as e:
            log.debug("CUSR0000SAH1 read failed: %s", e)
            shelter_df = None

    # Determine target month for ZORI lease-reset window
    if ref_month is None:
        own_prints = knowable_series_fn(vintages, own_series, asof)
        if not own_prints.empty:
            shelter_target_month = (
                pd.Timestamp(own_prints["period"].iloc[-1]).to_period("M") + 1
            ).to_timestamp()
        else:
            shelter_target_month = pd.Timestamp(asof).to_period("M").to_timestamp()
    else:
        shelter_target_month = pd.Timestamp(ref_month).to_period("M").to_timestamp()

    shelter_nowcast_val, shelter_prov = _compute_shelter_nowcast(
        zori_df, shelter_df, shelter_target_month, asof
    )
    features["shelter_nowcast"] = shelter_nowcast_val
    if shelter_nowcast_val is None:
        absent_legs.append("shelter_nowcast")

    # Merge shelter provenance
    prov["shelter_prov"] = shelter_prov

    prov["absent_legs"] = absent_legs

    # FIX 2: apply plausibility-bound range guard (post-computation fence)
    features = _apply_range_guard(features, prov)

    return features, prov
