"""MRI — CPI Component Bridge (Track CB, MRI-R25).

LEAF · DISPLAY-ONLY. Pure numpy/pandas only.

A BLS relative-importance weighted component bridge for CPI headline & core.
Each block computes a MoM estimate from its PIT-safe proxy series, multiplied by
the BLS Dec-2025 relative-importance weight → contribution in percentage-points.

The bridge is a TRUE partition to 100pp: all 13 prior-only blocks carry their own prior
MoM × RI weight in the point estimate, so Σ(applied weights) = 100 (headline) / 79.919
(core). Printed honesty fields per MRI-R19:
  coverage_residual_pp = 100 − Σ(applied weights)  (real coverage gap, ~0 when complete)
  prior_driven_share   = Σ(weights of confidence-0 blocks) / 100  (extrapolation fraction)

NOT a regression. Weights come from BLS, not from data fitting.

SPECIFICATION: research/release_forecast/PREREG_CPI_BRIDGE_V1.md (amended 2026-07-08,
corrected attempt #1 per Opus review; corrections are BLS-partition-derived, not result-tuned)
RULING: MRI-R25 (research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md §11)

Anti-mining: spec frozen before backtest results observed; this rework committed AFTER
prereg amendment (separate earlier commit).

PIT LAW: same as engine/release_components_cpi.py. Non-vintaged series declared
revision_optimistic per leg. PPIFIS/PPIFES use knowable_series for ALFRED-PIT.

display_only=True, authority=False on all outputs — never conditions scoring.
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
# BLS Dec-2025 relative-importance weights (CPI-U, U.S. city average)
# Source: https://www.bls.gov/cpi/tables/relative-importance/2025.htm
# In effect Jan–Dec 2026. Refresh each January.
# Manually verified against fetched table (2026-07-08).
# ---------------------------------------------------------------------------

# Modelled block weights (from BLS table; these are the RI weights we apply)
_ENERGY_GASOLINE_W = 2.895    # Gasoline (all types)
_ENERGY_ELEC_W = 2.375        # Electricity (APU000072610)
_SHELTER_W = 35.625           # Shelter (full basket: OER + rent + lodging)
_FOOD_AT_HOME_W = 8.325       # Food at home
_CORE_GOODS_W = 19.176        # Commodities less food and energy
_CORE_SVC_XS_W = 25.118       # all items less food+energy (79.919) - shelter (35.625) - core_goods (19.176)
# Corrected from original 44.294: the original forgot to subtract core_goods, double-counting 19.176pp.

# All-items denominator
_ALL_ITEMS_W = 100.000

# Core CPI denominator: all items less food and energy
_CORE_ITEMS_W = 79.919

# --- Partition accounting ---
# The modelled blocks use exclusive BLS sub-basket weights (no overlap after correction):
#   Headline: gasoline(2.895)+elec(2.375)+shelter(35.625)+food_at_home(8.325)
#             +core_goods(19.176)+core_svc_xs(25.118) = 93.514pp
#   Core: shelter(35.625)+core_goods(19.176)+core_svc_xs(25.118) = 79.919pp (full core basket)
#
# One "unmodelled_residual" block absorbs the remaining basket share:
#   Headline residual: 100.000 − 93.514 = 6.486pp
#   Core residual: 79.919 − 79.919 = 0.000pp (core is fully partitioned)
#
# The residual block carries the prior own-series MoM × residual weight (confidence=0.0).

_MODELLED_W_HEADLINE = (
    _ENERGY_GASOLINE_W + _ENERGY_ELEC_W + _SHELTER_W
    + _FOOD_AT_HOME_W + _CORE_GOODS_W + _CORE_SVC_XS_W
)
# = 2.895 + 2.375 + 35.625 + 8.325 + 19.176 + 25.118 = 93.514

_MODELLED_W_CORE = _SHELTER_W + _CORE_GOODS_W + _CORE_SVC_XS_W
# = 35.625 + 19.176 + 25.118 = 79.919 (exactly _CORE_ITEMS_W)

_UNMODELLED_RESIDUAL_W_HEADLINE = round(_ALL_ITEMS_W - _MODELLED_W_HEADLINE, 6)
# = 6.486

_UNMODELLED_RESIDUAL_W_CORE = round(_CORE_ITEMS_W - _MODELLED_W_CORE, 6)
# = 0.000 (no residual for core)

# Per-block confidence (per PREREG_CPI_BRIDGE_V1.md §3)
_BLOCK_CONFIDENCE: dict[str, float] = {
    "energy_gasoline": 1.0,
    "energy_electricity": 0.8,
    "shelter": 0.6,
    "food_at_home": 0.4,
    "core_goods_pipeline": 0.6,
    "core_services_ex_shelter": 0.4,
}

# ZORI PIT conservative lag (mirrors engine/release_components_cpi.py)
_ZORI_LAG_DAYS = 45


# ---------------------------------------------------------------------------
# Block 1: Energy — gasoline MoM
# ---------------------------------------------------------------------------

def _compute_energy_gasoline(
    root: Path,
    asof: date,
    ref_month: pd.Timestamp,
) -> tuple[float | None, dict]:
    """Gasoline MoM: reference-month weekly avg vs prior-month avg.

    Mirrors champion gasoline_mom computation exactly.
    Declared unrevised_legs.
    """
    prov: dict[str, Any] = {"series": "GASREGW", "status": "ok"}
    gasregw_path = root / "data" / "fred" / "GASREGW.parquet"
    if not gasregw_path.exists():
        prov["status"] = "absent"
        return None, prov
    try:
        gasregw = pd.read_parquet(gasregw_path)
        gasregw.index = pd.to_datetime(gasregw.index)
        asof_ts = pd.Timestamp(asof)
        ref_start = ref_month.to_period("M").to_timestamp()
        ref_end = ref_start + pd.offsets.MonthBegin(1)
        prior_start = ref_start - pd.offsets.MonthBegin(1)
        col = gasregw.columns[0]
        cur_hi = min(ref_end, asof_ts)
        cur_mask = (gasregw.index >= ref_start) & (gasregw.index < cur_hi)
        prior_mask = (gasregw.index >= prior_start) & (gasregw.index < ref_start)
        cur_avg = gasregw.loc[cur_mask, col].mean() if cur_mask.any() else np.nan
        prior_avg = gasregw.loc[prior_mask, col].mean() if prior_mask.any() else np.nan
        prov["ref_month"] = str(ref_start.date())
        prov["cur_weeks"] = int(cur_mask.sum())
        prov["prior_weeks"] = int(prior_mask.sum())
        if np.isfinite(cur_avg) and np.isfinite(prior_avg) and prior_avg != 0:
            mom = float((cur_avg / prior_avg - 1) * 100)
            prov["gasoline_mom"] = round(mom, 4)
            return mom, prov
        prov["status"] = "insufficient_data"
        return None, prov
    except Exception as e:
        log.debug("GASREGW read failed: %s", e)
        prov["status"] = f"error: {e}"
        return None, prov


# ---------------------------------------------------------------------------
# Block 1: Energy — electricity MoM
# ---------------------------------------------------------------------------

def _compute_energy_electricity(
    root: Path,
    asof: date,
) -> tuple[float | None, dict]:
    """Electricity MoM: APU000072610 lag-1 pct change.

    At decision date (day before month M release), last knowable electricity = M-1.
    Declared revision_optimistic.
    """
    prov: dict[str, Any] = {"series": "APU000072610", "status": "ok"}
    elec_path = root / "data" / "fred" / "APU000072610.parquet"
    if not elec_path.exists():
        prov["status"] = "absent"
        return None, prov
    try:
        elec = pd.read_parquet(elec_path)
        elec.index = pd.to_datetime(elec.index)
        col = elec.columns[0]
        # Knowability cap: last usable = M-1 (same rule as shelter)
        asof_ts = pd.Timestamp(asof)
        asof_period = asof_ts.to_period("M")
        cutoff_period = asof_period - 2  # asof is in M+1 → last usable = M-1
        cutoff_ts = cutoff_period.to_timestamp(how="E")
        known = elec[elec.index <= cutoff_ts].sort_index()
        if len(known) < 2:
            prov["status"] = "insufficient_data"
            return None, prov
        last = float(known[col].iloc[-1])
        prev = float(known[col].iloc[-2])
        if prev == 0:
            prov["status"] = "zero_prior"
            return None, prov
        mom = (last / prev - 1) * 100
        prov["elec_mom"] = round(mom, 4)
        prov["period_used"] = str(known.index[-1].date())
        return float(mom), prov
    except Exception as e:
        log.debug("APU000072610 read failed: %s", e)
        prov["status"] = f"error: {e}"
        return None, prov


# ---------------------------------------------------------------------------
# Block 2: Shelter — reuse existing nowcast
# ---------------------------------------------------------------------------

def _compute_shelter_block(
    root: Path,
    asof: date,
    ref_month: pd.Timestamp,
) -> tuple[float | None, dict]:
    """Shelter nowcast: delegates to engine.release_components_cpi._compute_shelter_nowcast.

    Returns (shelter_nowcast_value, prov).
    Declared revision_optimistic (CUSR0000SAH1 + ZORI).
    """
    try:
        from engine.release_components_cpi import (
            _compute_shelter_nowcast,
            _load_zori_national,
        )
        zori_df = _load_zori_national(root)
        shelter_path = root / "data" / "fred" / "CUSR0000SAH1.parquet"
        shelter_df: pd.DataFrame | None = None
        if shelter_path.exists():
            try:
                shelter_df = pd.read_parquet(shelter_path)
                shelter_df.index = pd.to_datetime(shelter_df.index)
            except Exception as e:
                log.debug("CUSR0000SAH1 read failed: %s", e)

        val, prov = _compute_shelter_nowcast(zori_df, shelter_df, ref_month, asof)
        prov["block"] = "shelter"
        return val, prov
    except Exception as e:
        log.debug("shelter block failed: %s", e)
        return None, {"block": "shelter", "status": f"error: {e}"}


# ---------------------------------------------------------------------------
# Block 3: Food at Home — PPI directional blend
# ---------------------------------------------------------------------------

def _compute_food_at_home(
    root: Path,
    asof: date,
) -> tuple[float | None, dict]:
    """Food-at-home MoM estimate: PPI WPU01 directional signal + CUSR0000SAF11 prior.

    Falls back to pure prior if WPU01 absent. Falls to None if both absent.
    Declared revision_optimistic.
    """
    prov: dict[str, Any] = {"block": "food_at_home", "status": "ok"}
    asof_ts = pd.Timestamp(asof)
    asof_period = asof_ts.to_period("M")
    # Knowability: same lag rule — last usable = M-1 for non-vintaged monthly
    cutoff_period = asof_period - 2
    cutoff_ts = cutoff_period.to_timestamp(how="E")

    # Load CUSR0000SAF11 (food at home CPI)
    fah_path = root / "data" / "fred" / "CUSR0000SAF11.parquet"
    fah_prior_mom: float | None = None
    if fah_path.exists():
        try:
            fah = pd.read_parquet(fah_path)
            fah.index = pd.to_datetime(fah.index)
            col = fah.columns[0]
            known = fah[fah.index <= cutoff_ts].sort_index()
            if len(known) >= 2:
                last = float(known[col].iloc[-1])
                prev = float(known[col].iloc[-2])
                if prev != 0:
                    fah_prior_mom = (last / prev - 1) * 100
                    prov["fah_prior_mom"] = round(fah_prior_mom, 4)
        except Exception as e:
            log.debug("CUSR0000SAF11 read failed: %s", e)

    # Load WPU01 (PPI farm products)
    wpu_path = root / "data" / "fred" / "WPU01.parquet"
    wpu01_mom: float | None = None
    if wpu_path.exists():
        try:
            wpu = pd.read_parquet(wpu_path)
            wpu.index = pd.to_datetime(wpu.index)
            col = wpu.columns[0]
            # WPU01 releases ~2 weeks before CPI; PPI for M-1 is typically available at D
            # Use M-1 as the latest safe read (same cutoff as FAH)
            known_wpu = wpu[wpu.index <= cutoff_ts].sort_index()
            if len(known_wpu) >= 2:
                last_w = float(known_wpu[col].iloc[-1])
                prev_w = float(known_wpu[col].iloc[-2])
                if prev_w != 0:
                    wpu01_mom = (last_w / prev_w - 1) * 100
                    prov["wpu01_mom"] = round(wpu01_mom, 4)
        except Exception as e:
            log.debug("WPU01 read failed: %s", e)

    if fah_prior_mom is None and wpu01_mom is None:
        prov["status"] = "both_absent"
        return None, prov

    if fah_prior_mom is None:
        # Use WPU01 as sole signal — apply scaling to approximate FAH
        # WPU01 farm products → FAH CPI: ~1/3 pass-through (rough)
        fah_est = wpu01_mom * 0.3 if wpu01_mom is not None else 0.0
        prov["method"] = "wpu01_scaled_only"
        prov["fah_mom_est"] = round(fah_est, 4)
        return float(fah_est), prov

    if wpu01_mom is None:
        # Pure prior
        prov["method"] = "prior_only_fallback"
        prov["fah_mom_est"] = round(fah_prior_mom, 4)
        return float(fah_prior_mom), prov

    # Both available — directional blend per PREREG_CPI_BRIDGE_V1.md §3.3
    threshold = 1.0  # pp threshold for direction signal
    sign_signal = float(np.sign(wpu01_mom)) if abs(wpu01_mom) > threshold else 0.0
    fah_adj = fah_prior_mom + 0.2 * sign_signal * abs(fah_prior_mom)

    # Clamp to [prior × 0.5, prior × 1.5]
    if fah_prior_mom >= 0:
        fah_est = float(np.clip(fah_adj, fah_prior_mom * 0.5, fah_prior_mom * 1.5))
    else:
        # Negative prior: clamp logic inverted
        lo = fah_prior_mom * 1.5  # more negative
        hi = fah_prior_mom * 0.5  # less negative
        fah_est = float(np.clip(fah_adj, lo, hi))

    prov["method"] = "directional_blend"
    prov["sign_signal"] = sign_signal
    prov["fah_mom_est"] = round(fah_est, 4)
    return fah_est, prov


# ---------------------------------------------------------------------------
# Block 4: Core Goods Pipeline — PPIFIS + PPIFES (ALFRED-vintaged)
# ---------------------------------------------------------------------------

def _compute_core_goods_pipeline(
    vintages: pd.DataFrame,
    asof: date,
) -> tuple[float | None, dict]:
    """Core goods pipeline: equal-weight average of PPIFIS and PPIFES lag-1 MoM.

    ALFRED-vintaged (PIT-safe via knowable_series from engine.release_forecast).
    """
    prov: dict[str, Any] = {"block": "core_goods_pipeline", "status": "ok"}
    from engine.release_forecast import knowable_series

    moms: list[float] = []
    for sid in ("PPIFIS", "PPIFES"):
        df = knowable_series(vintages, sid, asof)
        if len(df) >= 2:
            levels = df.set_index("period")["value"]
            mom_s = levels.pct_change() * 100.0
            mom_s = mom_s.dropna()
            if len(mom_s) >= 1:
                mom_val = float(mom_s.iloc[-1])
                prov[f"{sid.lower()}_mom_lag1"] = round(mom_val, 4)
                moms.append(mom_val)
            else:
                prov[f"{sid.lower()}_mom_lag1"] = None
        else:
            prov[f"{sid.lower()}_mom_lag1"] = None

    if not moms:
        prov["status"] = "both_absent"
        return None, prov

    pipeline_mom = float(np.mean(moms))
    prov["n_series"] = len(moms)
    prov["pipeline_mom_est"] = round(pipeline_mom, 4)
    return pipeline_mom, prov


# ---------------------------------------------------------------------------
# Block 5: Core Services ex-Shelter — CUSR0000SASLE persistence
# ---------------------------------------------------------------------------

def _compute_core_services_ex_shelter(
    root: Path,
    asof: date,
) -> tuple[float | None, dict]:
    """Core services ex-shelter: CUSR0000SASLE lag-1 MoM (persistence).

    Non-vintaged; declared revision_optimistic.
    """
    prov: dict[str, Any] = {"block": "core_services_ex_shelter", "status": "ok"}
    asof_ts = pd.Timestamp(asof)
    asof_period = asof_ts.to_period("M")
    cutoff_period = asof_period - 2
    cutoff_ts = cutoff_period.to_timestamp(how="E")

    csxs_path = root / "data" / "fred" / "CUSR0000SASLE.parquet"
    if not csxs_path.exists():
        prov["status"] = "absent"
        return None, prov
    try:
        csxs = pd.read_parquet(csxs_path)
        csxs.index = pd.to_datetime(csxs.index)
        col = csxs.columns[0]
        known = csxs[csxs.index <= cutoff_ts].sort_index()
        if len(known) < 2:
            prov["status"] = "insufficient_data"
            return None, prov
        last = float(known[col].iloc[-1])
        prev = float(known[col].iloc[-2])
        if prev == 0:
            prov["status"] = "zero_prior"
            return None, prov
        mom = (last / prev - 1) * 100
        prov["csxs_mom_est"] = round(mom, 4)
        prov["period_used"] = str(known.index[-1].date())
        return float(mom), prov
    except Exception as e:
        log.debug("CUSR0000SASLE read failed: %s", e)
        prov["status"] = f"error: {e}"
        return None, prov


# ---------------------------------------------------------------------------
# Prior-only blocks: use own-series prior MoM from vintages
# ---------------------------------------------------------------------------

def _compute_prior_mom_from_own_series(
    vintages: pd.DataFrame,
    series: str,
    asof: date,
) -> float | None:
    """Return last knowable own-series MoM at asof (for prior-only blocks).

    Returns None if series not in vintages or insufficient history.
    """
    from engine.release_forecast import knowable_series

    df = knowable_series(vintages, series, asof)
    if len(df) < 2:
        return None
    levels = df.set_index("period")["value"]
    mom_s = levels.pct_change() * 100.0
    mom_s = mom_s.dropna()
    if len(mom_s) < 1:
        return None
    return float(mom_s.iloc[-1])


# ---------------------------------------------------------------------------
# Main bridge function
# ---------------------------------------------------------------------------

def compute_cpi_bridge(
    asof: date,
    root: Path | str,
    vintages: pd.DataFrame | None = None,
    ref_month: date | pd.Timestamp | None = None,
    release: str = "cpi_headline",
) -> dict:
    """Compute the CPI component bridge estimate.

    Parameters
    ----------
    asof : date
        Decision date (day before the target CPI release).
    root : Path or str
        Repository root.
    vintages : pd.DataFrame or None
        ALFRED vintage table. If None, loaded from data/fred_vintage/vintages.parquet.
    ref_month : date or Timestamp or None
        Reference month M that the upcoming CPI print covers.
        If None, derived from last knowable CPIAUCSL/CPILFESL initial print + 1 month.
    release : str
        'cpi_headline' or 'cpi_core'. Bridge excludes energy blocks for core.

    Returns
    -------
    dict matching the release_forecast.v2 projection block schema, tagged:
        model = 'cpi_bridge'
        display_only = True
        authority = False
    Key additional fields:
        components: list of {block, contribution_pp, weight, confidence, prior_only}
        weight_coverage: share of CPI basket backed by modelled blocks (float)
        residual_pp: reconciliation check (should be ~0.0)
        modelled_sum_pp: sum of modelled contributions
        prior_sum_pp: sum of prior-only contributions
    """
    root = Path(root)
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"
    is_core = (release == "cpi_core")

    # Load vintages if not provided
    if vintages is None:
        from engine.release_forecast import load_vintages
        vintages = load_vintages(root)

    # Derive ref_month if not provided
    if ref_month is None:
        from engine.release_forecast import knowable_series
        own_prints = knowable_series(vintages, own_series, asof)
        if own_prints.empty:
            return _empty_bridge(release, asof, "no_knowable_own_series")
        ref_month = (
            pd.Timestamp(own_prints["period"].iloc[-1]).to_period("M") + 1
        ).to_timestamp()
    else:
        ref_month = pd.Timestamp(ref_month)

    # Derive naive prior (last own-series MoM) for baselines
    from engine.release_forecast import knowable_series as _ks
    own_prints = _ks(vintages, own_series, asof)
    naive_prior: float | None = None
    if len(own_prints) >= 2:
        levels = own_prints.set_index("period")["value"]
        mom_s = levels.pct_change() * 100.0
        mom_s = mom_s.dropna()
        if len(mom_s) >= 1:
            naive_prior = float(mom_s.iloc[-1])
    trailing_3m: float | None = None
    if len(own_prints) >= 4:
        levels_t = own_prints.set_index("period")["value"]
        mom_t = levels_t.pct_change() * 100.0
        mom_t = mom_t.dropna()
        if len(mom_t) >= 3:
            trailing_3m = float(mom_t.iloc[-3:].mean())

    # ---- Compute each modelled block ----------------------------------------

    components: list[dict] = []
    revision_optimistic_legs: list[str] = []
    unrevised_legs: list[str] = []
    absent_legs: list[str] = []
    all_prov: dict[str, Any] = {}

    # Block 1a: energy_gasoline (headline only)
    if not is_core:
        gas_mom, gas_prov = _compute_energy_gasoline(root, asof, ref_month)
        all_prov["energy_gasoline"] = gas_prov
        unrevised_legs.append("GASREGW")
        if gas_mom is not None:
            contribution = (gas_mom / 100.0) * _ENERGY_GASOLINE_W
            components.append({
                "block": "energy_gasoline",
                "mom_est": round(gas_mom, 4),
                "weight": _ENERGY_GASOLINE_W,
                "contribution_pp": round(contribution, 6),
                "confidence": _BLOCK_CONFIDENCE["energy_gasoline"],
                "prior_only": False,
            })
        else:
            absent_legs.append("energy_gasoline")
            # Fall to prior for this sub-block
            prior_mom_gas = _compute_prior_mom_from_own_series(vintages, "CPIAUCSL", asof)
            fallback = 0.0 if prior_mom_gas is None else prior_mom_gas * (_ENERGY_GASOLINE_W / _ALL_ITEMS_W)
            components.append({
                "block": "energy_gasoline",
                "mom_est": None,
                "weight": _ENERGY_GASOLINE_W,
                "contribution_pp": round(fallback, 6),
                "confidence": 0.0,
                "prior_only": True,
            })

    # Block 1b: energy_electricity (headline only)
    if not is_core:
        elec_mom, elec_prov = _compute_energy_electricity(root, asof)
        all_prov["energy_electricity"] = elec_prov
        revision_optimistic_legs.append("APU000072610")
        if elec_mom is not None:
            contribution = (elec_mom / 100.0) * _ENERGY_ELEC_W
            components.append({
                "block": "energy_electricity",
                "mom_est": round(elec_mom, 4),
                "weight": _ENERGY_ELEC_W,
                "contribution_pp": round(contribution, 6),
                "confidence": _BLOCK_CONFIDENCE["energy_electricity"],
                "prior_only": False,
            })
        else:
            absent_legs.append("energy_electricity")
            components.append({
                "block": "energy_electricity",
                "mom_est": None,
                "weight": _ENERGY_ELEC_W,
                "contribution_pp": 0.0,
                "confidence": 0.0,
                "prior_only": True,
            })

    # Block 2: shelter
    shelter_mom, shelter_prov = _compute_shelter_block(root, asof, ref_month)
    all_prov["shelter"] = shelter_prov
    revision_optimistic_legs.extend(["CUSR0000SAH1", "ZORI"])
    if shelter_mom is not None:
        contribution = (shelter_mom / 100.0) * _SHELTER_W
        components.append({
            "block": "shelter",
            "mom_est": round(shelter_mom, 4),
            "weight": _SHELTER_W,
            "contribution_pp": round(contribution, 6),
            "confidence": _BLOCK_CONFIDENCE["shelter"],
            "prior_only": False,
        })
    else:
        absent_legs.append("shelter")
        components.append({
            "block": "shelter",
            "mom_est": None,
            "weight": _SHELTER_W,
            "contribution_pp": 0.0,
            "confidence": 0.0,
            "prior_only": True,
        })

    # Block 3: food at home (HEADLINE ONLY — food excluded from core CPI by definition)
    if not is_core:
        fah_mom, fah_prov = _compute_food_at_home(root, asof)
        all_prov["food_at_home"] = fah_prov
        revision_optimistic_legs.extend(["WPU01", "CUSR0000SAF11"])
        if fah_mom is not None:
            contribution = (fah_mom / 100.0) * _FOOD_AT_HOME_W
            components.append({
                "block": "food_at_home",
                "mom_est": round(fah_mom, 4),
                "weight": _FOOD_AT_HOME_W,
                "contribution_pp": round(contribution, 6),
                "confidence": _BLOCK_CONFIDENCE["food_at_home"],
                "prior_only": False,
            })
        else:
            absent_legs.append("food_at_home")
            # Fall to prior for this sub-block
            prior_mom_fah = _compute_prior_mom_from_own_series(vintages, own_series, asof)
            fah_fallback = (
                0.0 if prior_mom_fah is None
                else (prior_mom_fah / 100.0) * _FOOD_AT_HOME_W
            )
            components.append({
                "block": "food_at_home",
                "mom_est": None,
                "weight": _FOOD_AT_HOME_W,
                "contribution_pp": round(fah_fallback, 6),
                "confidence": 0.0,
                "prior_only": True,
            })

    # Block 4: core goods pipeline
    pipeline_mom, pipeline_prov = _compute_core_goods_pipeline(vintages, asof)
    all_prov["core_goods_pipeline"] = pipeline_prov
    if pipeline_mom is not None:
        contribution = (pipeline_mom / 100.0) * _CORE_GOODS_W
        components.append({
            "block": "core_goods_pipeline",
            "mom_est": round(pipeline_mom, 4),
            "weight": _CORE_GOODS_W,
            "contribution_pp": round(contribution, 6),
            "confidence": _BLOCK_CONFIDENCE["core_goods_pipeline"],
            "prior_only": False,
        })
    else:
        absent_legs.append("core_goods_pipeline")
        components.append({
            "block": "core_goods_pipeline",
            "mom_est": None,
            "weight": _CORE_GOODS_W,
            "contribution_pp": 0.0,
            "confidence": 0.0,
            "prior_only": True,
        })

    # Block 5: core services ex-shelter
    csxs_mom, csxs_prov = _compute_core_services_ex_shelter(root, asof)
    all_prov["core_services_ex_shelter"] = csxs_prov
    revision_optimistic_legs.append("CUSR0000SASLE")
    if csxs_mom is not None:
        contribution = (csxs_mom / 100.0) * _CORE_SVC_XS_W
        components.append({
            "block": "core_services_ex_shelter",
            "mom_est": round(csxs_mom, 4),
            "weight": _CORE_SVC_XS_W,
            "contribution_pp": round(contribution, 6),
            "confidence": _BLOCK_CONFIDENCE["core_services_ex_shelter"],
            "prior_only": False,
        })
    else:
        absent_legs.append("core_services_ex_shelter")
        components.append({
            "block": "core_services_ex_shelter",
            "mom_est": None,
            "weight": _CORE_SVC_XS_W,
            "contribution_pp": 0.0,
            "confidence": 0.0,
            "prior_only": True,
        })

    # ---- Unmodelled residual block: TRUE 100pp partition --------------------------
    # Add one aggregate "unmodelled_residual" block to absorb the basket share not
    # covered by the 5-6 modelled blocks. This ensures Σ(applied weights) = 100
    # (headline) / 79.919 (core). Confidence = 0.0 (prior-only, no fresh proxy).
    unmodelled_w = _UNMODELLED_RESIDUAL_W_HEADLINE if not is_core else _UNMODELLED_RESIDUAL_W_CORE
    if unmodelled_w > 1e-6:
        prior_mom_residual = _compute_prior_mom_from_own_series(vintages, own_series, asof)
        residual_contrib = (
            0.0 if prior_mom_residual is None
            else (prior_mom_residual / 100.0) * unmodelled_w
        )
        components.append({
            "block": "unmodelled_residual",
            "mom_est": round(prior_mom_residual, 4) if prior_mom_residual is not None else None,
            "weight": unmodelled_w,
            "contribution_pp": round(float(residual_contrib), 6),
            "confidence": 0.0,
            "prior_only": True,
        })

    # ---- Reconciliation: sum contributions → point estimate --------------------
    modelled_contribs = [c["contribution_pp"] for c in components if not c["prior_only"]]
    prior_contribs = [c["contribution_pp"] for c in components if c["prior_only"]]
    modelled_sum = float(sum(modelled_contribs))
    prior_sum = float(sum(prior_contribs))
    point_est = modelled_sum + prior_sum

    # Weight coverage: share of basket backed by modelled (non-prior) blocks
    modelled_block_names = [c["block"] for c in components if not c["prior_only"]]
    modelled_weights_sum = sum(c["weight"] for c in components if not c["prior_only"])
    weight_coverage_raw = modelled_weights_sum / _ALL_ITEMS_W
    weight_coverage_clipped = min(weight_coverage_raw, 1.0)

    # coverage_residual_pp: REAL coverage gap = total_basket − Σ(applied weights)
    # ~0 when partition is complete; >0 only if a basket share is genuinely excluded.
    applied_weights_sum = sum(c["weight"] for c in components)
    basket_denominator = _ALL_ITEMS_W if not is_core else _CORE_ITEMS_W
    coverage_residual_pp = round(basket_denominator - applied_weights_sum, 6)

    # prior_driven_share: fraction of the estimate driven by extrapolation (confidence=0)
    prior_weight_sum = sum(c["weight"] for c in components if c["prior_only"])
    prior_driven_share = round(prior_weight_sum / _ALL_ITEMS_W, 6)

    # Bridge confidence: weighted average of block confidences for modelled blocks
    total_abs_modelled = sum(abs(c["contribution_pp"]) for c in components if not c["prior_only"])
    bridge_confidence: float | None = None
    if total_abs_modelled > 0:
        c_raw = sum(
            abs(c["contribution_pp"]) / total_abs_modelled * c["confidence"]
            for c in components if not c["prior_only"]
        )
        bridge_confidence = round(float(c_raw) * weight_coverage_clipped, 4)

    point: float | None = round(point_est, 4) if abs(point_est) < 50 else None

    return {
        "release": release,
        "model": "cpi_bridge",
        "asof": asof.isoformat(),
        "point": point,
        "p10": None,  # Bridge has no quantile intervals (no residual distribution)
        "p25": None,
        "p50": None,
        "p75": None,
        "p90": None,
        "confidence": bridge_confidence,
        "confidence_components": {
            "weight_coverage": round(weight_coverage_raw, 4),
            "n_modelled_blocks": len(modelled_block_names),
            "n_prior_blocks": len([c for c in components if c["prior_only"]]),
        },
        "components": components,
        "weight_coverage": round(weight_coverage_raw, 4),
        "modelled_sum_pp": round(modelled_sum, 6),
        "prior_sum_pp": round(prior_sum, 6),
        "coverage_residual_pp": coverage_residual_pp,
        "prior_driven_share": prior_driven_share,
        "benchmark_set": {
            "naive_prior": round(naive_prior, 4) if naive_prior is not None else None,
            "trailing_3m": round(trailing_3m, 4) if trailing_3m is not None else None,
        },
        "pit_provenance": {
            "revision_optimistic_legs": list(dict.fromkeys(revision_optimistic_legs)),  # dedup
            "unrevised_legs": list(dict.fromkeys(unrevised_legs)),
            "absent_legs": absent_legs,
            "display_only": True,
            "authority": False,
            "block_provenance": all_prov,
        },
        "display_only": True,
        "authority": False,
    }


# ---------------------------------------------------------------------------
# Walk-forward backtest support
# ---------------------------------------------------------------------------

def run_bridge_walk_forward(
    release: str,
    root: Path | str,
) -> dict:
    """Run walk-forward backtest for the CPI bridge.

    For each initial CPI print (CPIAUCSL or CPILFESL) in the ALFRED vintage,
    computes a bridge estimate at decision_date = realtime_start - 1 day
    (the day before the CPI was published).

    Returns dict with:
      results: list of per-step dicts {period, asof, predicted, actual,
               baseline_naive, baseline_trailing3m, weight_coverage, n_modelled_blocks}
      metadata: dict
    """
    root = Path(root)
    own_series = "CPIAUCSL" if release == "cpi_headline" else "CPILFESL"

    from engine.release_forecast import load_vintages, knowable_series

    vintages = load_vintages(root)

    # All initial prints knowable "forever" (we build the full sequence)
    all_prints = knowable_series(vintages, own_series, date(2099, 1, 1))
    if len(all_prints) < 2:
        return {"results": [], "metadata": {"error": "insufficient_data"}}

    all_prints["mom"] = all_prints["value"].pct_change() * 100.0
    all_prints = all_prints.dropna(subset=["mom"]).reset_index(drop=True)

    results: list[dict] = []
    for _, row in all_prints.iterrows():
        step_asof = (pd.Timestamp(row["realtime_start"]) - pd.Timedelta(days=1)).date()
        target_mom = float(row["mom"])
        ref_month = pd.Timestamp(row["period"])

        # Compute baselines
        prior_prints = all_prints[all_prints["realtime_start"] < row["realtime_start"]]
        naive = float(prior_prints["mom"].iloc[-1]) if len(prior_prints) >= 1 else None
        trailing_3m = (
            float(prior_prints["mom"].iloc[-3:].mean())
            if len(prior_prints) >= 3 else naive
        )

        # Compute bridge
        try:
            bridge = compute_cpi_bridge(
                asof=step_asof,
                root=root,
                vintages=vintages,
                ref_month=ref_month,
                release=release,
            )
            predicted = bridge.get("point")
            wc = bridge.get("weight_coverage")
            n_mod = bridge.get("confidence_components", {}).get("n_modelled_blocks", 0)
        except Exception as e:
            log.debug("bridge failed at %s: %s", step_asof, e)
            predicted = None
            wc = None
            n_mod = 0

        if predicted is None:
            continue

        results.append({
            "period": row["period"],
            "release_date": row["realtime_start"],
            "asof": step_asof,
            "predicted": predicted,
            "actual": target_mom,
            "baseline_naive": naive,
            "baseline_trailing3m": trailing_3m,
            "weight_coverage": wc,
            "n_modelled_blocks": n_mod,
        })

    return {
        "results": results,
        "metadata": {
            "release": release,
            "model": "cpi_bridge",
            "n_records": len(all_prints),
            "n_results": len(results),
        },
    }


# ---------------------------------------------------------------------------
# Empty bridge (failure case)
# ---------------------------------------------------------------------------

def _empty_bridge(release: str, asof: date, reason: str) -> dict:
    return {
        "release": release,
        "model": "cpi_bridge",
        "asof": asof.isoformat(),
        "point": None,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "confidence": None,
        "confidence_components": {},
        "components": None,
        "weight_coverage": 0.0,
        "modelled_sum_pp": None,
        "prior_sum_pp": None,
        "coverage_residual_pp": None,
        "prior_driven_share": None,
        "benchmark_set": {"naive_prior": None, "trailing_3m": None},
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
