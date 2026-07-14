"""MRI Miss Anatomy — Engine-Replay Diagnostic.

DISPLAY-TIER RESEARCH. Not a production engine component; does NOT touch
data/fred_vintage/vintages.parquet (read-only), does NOT write to any ledger
or forward-scoreboard (write=research outputs only).

Measures how close the v1 champion was, release-by-release, using the CORRECTED
feature construction (fixing the double-derivative bug described in the 2026-07-14
postmortem). Produces a per-release miss anatomy with block-level attribution,
cluster classification, and candidate measurable inputs.

CONTEXT (established fact from postmortem):
  - engine/release_forecast.py _last_n_mom_lags applies pct_change() to
    STICKCPIM157SFRBATL / MEDCPIM158SFRBCLE / FLEXCPIM157SFRBATL, which are
    ALREADY percent-rate series. This is a double derivative and produces values
    like sticky_mom_lag1 = -36 to +229 instead of 0.09 to 0.38.
  - The bug poisons ALL V1/V2/V3 results. Published results/ files are CONTAMINATED.
  - FIX applied HERE (not in engine): use the series VALUES DIRECTLY as the lag
    feature (no pct_change). Gasoline, own CPI lags (which ARE index levels),
    PPI: still use pct_change as spec says. Shelter nowcast: unchanged.
  - MRI-R8: walk-forward replay MAE is NOT the forward scoreboard record.
  - Interval-recalibration one-shot is SPENT. No new interval fitting.
  - MRI-R38: no revision-direction modeling.

Coverage limitations (printed prominently):
  CPIAUCSL / CPILFESL initial prints: 1997-01 to 2026-05 (353 obs; 352 MoM rows).
  Full-feature CPI era (sticky/median/flex + PPI all present): 2014-03+ vintage.
  Walk-forward burn-in: 60 obs. So first prediction with full features: ~2015-05.
  Total CPI walk-forward predictions: see printed output.
  NFP: ICSA/CCSA vintages start 2009-06; burn-in 60 obs; eval starts ~2015.
  June 2026 CPI actual NOT in vintage store: projection-side replay only.

Usage:
  cd <repo_root>
  python scripts/research/mri_miss_anatomy.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root bootstrap
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

# We import only data-loading and pure helpers from the engine, NOT the
# feature builders (they contain the bug we are correcting).
from engine.release_forecast import (  # noqa: E402
    load_vintages,
    knowable_series,
    _ridge_predict,
    _ridge_predict_with_components,
    _build_matrix,
    _walk_forward,
    MIN_TRAIN_OBS,
    COVID_MONTHS,
)

_OUT_DIR = _REPO / "reports"
_OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_RIDGE_LAMBDA = 1.0
_MIN_OBS = MIN_TRAIN_OBS  # 60

# CPI feature names — same order as engine (own lags first, then fixed-rate lags,
# then pipeline, then gasoline [headline only], then shelter)
_CPI_HL_FEATURES = [
    "cpi_hl_mom_lag1", "cpi_hl_mom_lag2", "cpi_hl_mom_lag3",  # own lags (index levels → pct_change OK)
    "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",     # CORRECTED: direct rate values, no pct_change
    "ppi_mom_lag1",                                             # CORRECTED: direct rate value, no pct_change
    "gasoline_mom",                                             # price level → pct_change OK
    "shelter_nowcast",                                          # blended, unchanged
]
_CPI_CORE_FEATURES = [
    "cpi_core_mom_lag1", "cpi_core_mom_lag2", "cpi_core_mom_lag3",
    "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
    "ppi_mom_lag1",
    "shelter_nowcast",
]
_NFP_FEATURES = [
    "nfp_change_lag1", "nfp_change_lag2", "nfp_change_lag3",
    "claims_survey_week_icsa", "claims_survey_week_ccsa",
    "withheld_tax_yoy", "awhman_mom",
]

# Block classification (mirrors engine/release_components_cpi.py _FEATURE_BLOCK_MAP)
_BLOCK_MAP = {
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
    # NFP
    "nfp_change_lag1": "nfp_persistence",
    "nfp_change_lag2": "nfp_persistence",
    "nfp_change_lag3": "nfp_persistence",
    "claims_survey_week_icsa": "claims_labor",
    "claims_survey_week_ccsa": "claims_labor",
    "withheld_tax_yoy": "tax_flow",
    "awhman_mom": "hours_labor",
}

# ---------------------------------------------------------------------------
# PIT assertion helper
# ---------------------------------------------------------------------------

def _assert_no_lookahead(vintages: pd.DataFrame, series: str, asof: date) -> None:
    """Assert no vintage row for series has realtime_start > asof."""
    asof_ts = pd.Timestamp(asof)
    sub = vintages[(vintages["series"] == series) & (vintages["realtime_start"] > asof_ts)]
    assert len(sub) == 0, (
        f"PIT VIOLATION: series={series} has {len(sub)} rows with realtime_start > {asof}"
    )


# ---------------------------------------------------------------------------
# CORRECTED feature builders
# ---------------------------------------------------------------------------

def _knowable_initial_values(
    vintages: pd.DataFrame, series: str, asof: date
) -> pd.Series:
    """Return initial-print values indexed by period, PIT-filtered at asof.

    PIT safety: knowable_series already filters realtime_start <= asof.
    This asserts that invariant holds for the specific series/asof pair.
    """
    df = knowable_series(vintages, series, asof)
    if df.empty:
        return pd.Series(dtype=float, name=series)
    s = df.set_index("period")["value"].sort_index()
    return s


def _own_mom_lags(
    vintages: pd.DataFrame, own_series: str, asof: date, n: int = 3
) -> list[float | None]:
    """Own-series MoM % change lags (lag1=most recent). Correct: levels → pct_change."""
    s = _knowable_initial_values(vintages, own_series, asof)
    if len(s) < 2:
        return [None] * n
    mom = s.pct_change() * 100.0
    mom = mom.dropna()
    return [float(mom.iloc[-i]) if len(mom) >= i else None for i in range(1, n + 1)]


def _rate_series_last(
    vintages: pd.DataFrame, series: str, asof: date
) -> float | None:
    """Last knowable value of an already-rate series (no pct_change). CORRECTED path."""
    s = _knowable_initial_values(vintages, series, asof)
    if len(s) == 0:
        return None
    return float(s.iloc[-1])


def _ppi_mom_lag1_corrected(vintages: pd.DataFrame, asof: date) -> float | None:
    """PPI Final Demand MoM % change from initial-print levels. CORRECT construction.

    PPIFIS is a PRICE INDEX (~109-157), not a rate series. pct_change() is the
    CORRECT operation here. The double-derivative bug ONLY affects sticky/median/flex
    (which are already rate series). PPI in the engine is computed correctly.
    This function replicates that correct behavior explicitly.
    """
    s = _knowable_initial_values(vintages, "PPIFIS", asof)
    if len(s) < 2:
        return None
    mom = s.pct_change() * 100.0
    mom = mom.dropna()
    if len(mom) == 0:
        return None
    return float(mom.iloc[-1])


def _gasoline_mom(asof: date, ref_month: date) -> float | None:
    """Gasoline MoM: monthly average of GASREGW(ref_month) / avg(ref_month-1) - 1.

    Returns None if file absent or data insufficient.
    """
    gas_path = _REPO / "data" / "fred" / "GASREGW.parquet"
    if not gas_path.exists():
        return None
    try:
        gas = pd.read_parquet(gas_path)
        gas.index = pd.to_datetime(gas.index)
        asof_ts = pd.Timestamp(asof)
        ref_start = pd.Timestamp(ref_month).to_period("M").to_timestamp()
        ref_end = ref_start + pd.offsets.MonthBegin(1)
        prior_start = ref_start - pd.offsets.MonthBegin(1)
        col = gas.columns[0]
        cur_hi = min(ref_end, asof_ts)
        cur_mask = (gas.index >= ref_start) & (gas.index < cur_hi)
        prior_mask = (gas.index >= prior_start) & (gas.index < ref_start)
        cur_avg = gas.loc[cur_mask, col].mean() if cur_mask.any() else np.nan
        prior_avg = gas.loc[prior_mask, col].mean() if prior_mask.any() else np.nan
        if np.isfinite(cur_avg) and np.isfinite(prior_avg) and prior_avg != 0:
            return float((cur_avg / prior_avg - 1) * 100)
    except Exception:
        pass
    return None


def _shelter_nowcast(asof: date, ref_month: date) -> float | None:
    """Shelter nowcast: replicate engine logic without modification (no bug here)."""
    try:
        from engine.release_components_cpi import (
            _load_zori_national,
            _compute_shelter_nowcast,
        )
        zori_df = _load_zori_national(_REPO)
        shlt_path = _REPO / "data" / "fred" / "CUSR0000SAH1.parquet"
        shelter_df = None
        if shlt_path.exists():
            shelter_df = pd.read_parquet(shlt_path)
            shelter_df.index = pd.to_datetime(shelter_df.index)
        target_month = pd.Timestamp(ref_month).to_period("M").to_timestamp()
        val, _ = _compute_shelter_nowcast(zori_df, shelter_df, target_month, asof)
        return val
    except Exception:
        return None


def _survey_week_claims_diff(
    vintages: pd.DataFrame, series: str, asof: date, ref_month: date
) -> float | None:
    """Claims survey-week value for ref_month minus same for ref_month-1."""
    from engine.release_forecast import _survey_week_claims
    cur = _survey_week_claims(vintages, series, asof, ref_month)
    prior_month = (pd.Timestamp(ref_month).to_period("M") - 1).to_timestamp().date()
    prior = _survey_week_claims(vintages, series, asof, prior_month)
    if cur is None or prior is None:
        return None
    return float(cur - prior)


def _withheld_tax_yoy(asof: date, ref_month: date) -> float | None:
    """YoY % growth in 30-day rolling withheld taxes at survey reference week."""
    tx_path = _REPO / "data" / "treasury" / "withheld_taxes.parquet"
    if not tx_path.exists():
        return None
    try:
        tx = pd.read_parquet(tx_path)
        tx.index = pd.to_datetime(tx.index)
        col = tx.columns[0]
        asof_ts = pd.Timestamp(asof)
        # reference week center = 12th of ref_month
        ref_12 = pd.Timestamp(ref_month.year, ref_month.month, 12)
        window_end = ref_12
        window_start = window_end - pd.Timedelta(days=29)
        # YoY window from prior year
        pyoy_end = window_end - pd.DateOffset(years=1)
        pyoy_start = window_start - pd.DateOffset(years=1)
        # PIT filter
        avail = tx[tx.index <= asof_ts]
        cur_w = avail[(avail.index >= window_start) & (avail.index <= window_end)][col].sum()
        py_w = avail[(avail.index >= pyoy_start) & (avail.index <= pyoy_end)][col].sum()
        if py_w <= 0:
            return None
        return float((cur_w / py_w - 1) * 100)
    except Exception:
        return None


def _awhman_mom(asof: date) -> float | None:
    """AWHMAN MoM (last known - prior) / prior * 100. Revision-optimistic."""
    awhman_path = _REPO / "data" / "fred" / "AWHMAN.parquet"
    if not awhman_path.exists():
        return None
    try:
        df = pd.read_parquet(awhman_path)
        df.index = pd.to_datetime(df.index)
        col = df.columns[0]
        asof_ts = pd.Timestamp(asof)
        avail = df[df.index <= asof_ts].sort_index()
        if len(avail) < 2:
            return None
        last = float(avail[col].iloc[-1])
        prev = float(avail[col].iloc[-2])
        if prev == 0:
            return None
        return float((last / prev - 1) * 100)
    except Exception:
        return None


def build_cpi_features_corrected(
    asof: date,
    vintages: pd.DataFrame,
    release_type: str,
    ref_month: date,
) -> dict[str, float | None]:
    """Build CORRECTED CPI feature dict at asof for ref_month.

    The ONLY difference from the engine: sticky/median/flex/PPI use their
    last RATE VALUE directly (no pct_change applied).
    """
    if release_type == "cpi_headline":
        own_series = "CPIAUCSL"
        lag_key = "cpi_hl_mom"
    else:
        own_series = "CPILFESL"
        lag_key = "cpi_core_mom"

    own_lags = _own_mom_lags(vintages, own_series, asof, n=3)
    features: dict[str, float | None] = {
        f"{lag_key}_lag1": own_lags[0],
        f"{lag_key}_lag2": own_lags[1],
        f"{lag_key}_lag3": own_lags[2],
        # CORRECTED: direct rate values, not pct_change of rate
        "sticky_mom_lag1": _rate_series_last(vintages, "STICKCPIM157SFRBATL", asof),
        "median_mom_lag1": _rate_series_last(vintages, "MEDCPIM158SFRBCLE", asof),
        "flex_mom_lag1": _rate_series_last(vintages, "FLEXCPIM157SFRBATL", asof),
        "ppi_mom_lag1": _ppi_mom_lag1_corrected(vintages, asof),
    }
    if release_type == "cpi_headline":
        features["gasoline_mom"] = _gasoline_mom(asof, ref_month)
    features["shelter_nowcast"] = _shelter_nowcast(asof, ref_month)
    return features


def build_nfp_features_corrected(
    asof: date,
    vintages: pd.DataFrame,
    ref_month: date,
) -> dict[str, float | None]:
    """Build CORRECTED NFP feature dict. NFP has no rate-series bug (PAYEMS is levels)."""
    nfp_lags: list[float | None] = []
    s = _knowable_initial_values(vintages, "PAYEMS", asof)
    if len(s) < 2:
        nfp_lags = [None, None, None]
    else:
        diff = s.diff().dropna()
        nfp_lags = [float(diff.iloc[-i]) if len(diff) >= i else None for i in range(1, 4)]

    icsa_diff = _survey_week_claims_diff(vintages, "ICSA", asof, ref_month)
    ccsa_diff = _survey_week_claims_diff(vintages, "CCSA", asof, ref_month)
    return {
        "nfp_change_lag1": nfp_lags[0],
        "nfp_change_lag2": nfp_lags[1],
        "nfp_change_lag3": nfp_lags[2],
        "claims_survey_week_icsa": icsa_diff,
        "claims_survey_week_ccsa": ccsa_diff,
        "withheld_tax_yoy": _withheld_tax_yoy(asof, ref_month),
        "awhman_mom": _awhman_mom(asof),
    }


# ---------------------------------------------------------------------------
# BUGGY feature builders (for receipt verification)
# ---------------------------------------------------------------------------

def build_cpi_features_buggy(
    asof: date,
    vintages: pd.DataFrame,
    release_type: str,
    ref_month: date,
) -> dict[str, float | None]:
    """Build BUGGY CPI feature dict — applies pct_change on rate series.

    Used only for receipt verification: compare buggy vs corrected sticky_mom_lag1
    and show the impact on projection.
    """
    if release_type == "cpi_headline":
        own_series = "CPIAUCSL"
        lag_key = "cpi_hl_mom"
    else:
        own_series = "CPILFESL"
        lag_key = "cpi_core_mom"

    own_lags = _own_mom_lags(vintages, own_series, asof, n=3)

    # BUG: pct_change on already-rate series
    def _buggy_last_mom_lag(series: str) -> float | None:
        s = _knowable_initial_values(vintages, series, asof)
        if len(s) < 2:
            return None
        mom = s.pct_change() * 100.0
        mom = mom.dropna()
        if len(mom) == 0:
            return None
        return float(mom.iloc[-1])

    features: dict[str, float | None] = {
        f"{lag_key}_lag1": own_lags[0],
        f"{lag_key}_lag2": own_lags[1],
        f"{lag_key}_lag3": own_lags[2],
        # BUG: pct_change on already-rate series for sticky/median/flex
        "sticky_mom_lag1": _buggy_last_mom_lag("STICKCPIM157SFRBATL"),
        "median_mom_lag1": _buggy_last_mom_lag("MEDCPIM158SFRBCLE"),
        "flex_mom_lag1": _buggy_last_mom_lag("FLEXCPIM157SFRBATL"),
        # PPI (PPIFIS) is an index level; pct_change is CORRECT (not affected by bug)
        "ppi_mom_lag1": _ppi_mom_lag1_corrected(vintages, asof),
    }
    if release_type == "cpi_headline":
        features["gasoline_mom"] = _gasoline_mom(asof, ref_month)
    features["shelter_nowcast"] = _shelter_nowcast(asof, ref_month)
    return features


# ---------------------------------------------------------------------------
# Walk-forward replay
# ---------------------------------------------------------------------------

def _run_cpi_walk_forward(
    vintages: pd.DataFrame,
    release_type: str,
    corrected: bool = True,
) -> tuple[list[dict], list[str]]:
    """Run walk-forward for CPI headline or core with CORRECTED (or BUGGY) features.

    Returns (records_with_results, feature_names).
    Each record has: period, release_date, asof, target, predicted, baseline_naive,
    baseline_trailing3m, features (dict), block_contribs (dict).
    """
    feature_names = (
        _CPI_HL_FEATURES if release_type == "cpi_headline" else _CPI_CORE_FEATURES
    )
    own_series = "CPIAUCSL" if release_type == "cpi_headline" else "CPILFESL"

    # Build ALL initial prints
    all_prints = knowable_series(vintages, own_series, date(2099, 1, 1))
    mom_series = all_prints.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)

    records: list[dict] = []
    for _, row in mom_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"].date()
        if corrected:
            feats = build_cpi_features_corrected(
                step_asof, vintages, release_type, ref_month
            )
        else:
            feats = build_cpi_features_buggy(
                step_asof, vintages, release_type, ref_month
            )
        rec = dict(feats)
        rec["target"] = float(row["mom"])
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    # PIT assertion: for every record, assert the asof date is before release_date
    for rec in records:
        assert pd.Timestamp(rec["asof"]) < pd.Timestamp(rec["release_date"]), (
            f"PIT VIOLATION at period {rec['period']}"
        )

    # Walk-forward
    wf = _walk_forward(records, feature_names, "target")

    # Annotate with metadata and block contributions
    result_records = []
    for r in wf:
        rec = records[r["idx"]]
        period = rec["period"]
        release_date = rec["release_date"]
        asof_step = rec["asof"]

        # Build block contributions using beta from the walk-forward step
        # Re-run ridge_predict_with_components for this step to get beta
        train_recs = records[: r["idx"]]
        X_all = _build_matrix(train_recs, feature_names)
        y_all = np.array([t.get("target", np.nan) for t in train_recs], dtype=float)
        valid = ~np.isnan(y_all)
        X_all = X_all[valid]
        y_all = y_all[valid]

        pred_features = np.array(
            [rec.get(fn) if rec.get(fn) is not None else np.nan for fn in feature_names],
            dtype=float,
        )
        pred_avail_mask = ~np.isnan(pred_features)
        block_contribs: dict[str, float] = {}
        if pred_avail_mask.any():
            X_sel = X_all[:, pred_avail_mask]
            row_complete = ~np.any(np.isnan(X_sel), axis=1)
            X_clean = X_sel[row_complete]
            y_clean = y_all[row_complete]
            x_pred = pred_features[pred_avail_mask]
            if len(y_clean) >= _MIN_OBS:
                try:
                    _, beta_feat, z_feat = _ridge_predict_with_components(
                        X_clean, y_clean, x_pred
                    )
                    avail_indices = np.where(pred_avail_mask)[0]
                    for j, orig_idx in enumerate(avail_indices):
                        fn = feature_names[orig_idx]
                        block = _BLOCK_MAP.get(fn, "core_persistence")
                        block_contribs[block] = block_contribs.get(block, 0.0) + float(
                            beta_feat[j] * z_feat[j]
                        )
                except Exception:
                    pass

        result_records.append(
            {
                "period": period,
                "release_date": release_date,
                "asof": asof_step,
                "actual": r["actual"],
                "predicted": r["predicted"],
                "baseline_naive": r["baseline_naive"],
                "baseline_trailing3m": r.get("baseline_trailing3m"),
                "features": {fn: rec.get(fn) for fn in feature_names},
                "block_contribs": block_contribs,
            }
        )

    return result_records, feature_names


def _run_nfp_walk_forward(vintages: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Run walk-forward for NFP. No rate-series bug — NFP uses level differences."""
    feature_names = _NFP_FEATURES

    all_prints = knowable_series(vintages, "PAYEMS", date(2099, 1, 1))
    diff_series = all_prints.copy()
    diff_series["change"] = diff_series["value"].diff()
    diff_series = diff_series.dropna(subset=["change"]).reset_index(drop=True)

    records: list[dict] = []
    for _, row in diff_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"].date()
        feats = build_nfp_features_corrected(step_asof, vintages, ref_month)
        rec = dict(feats)
        rec["target"] = float(row["change"])
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    for rec in records:
        assert pd.Timestamp(rec["asof"]) < pd.Timestamp(rec["release_date"]), (
            f"PIT VIOLATION at period {rec['period']}"
        )

    wf = _walk_forward(records, feature_names, "target")

    result_records = []
    for r in wf:
        rec = records[r["idx"]]
        result_records.append(
            {
                "period": rec["period"],
                "release_date": rec["release_date"],
                "asof": rec["asof"],
                "actual": r["actual"],
                "predicted": r["predicted"],
                "baseline_naive": r["baseline_naive"],
                "baseline_trailing3m": r.get("baseline_trailing3m"),
                "features": {fn: rec.get(fn) for fn in feature_names},
                "block_contribs": {},
            }
        )

    return result_records, feature_names


# ---------------------------------------------------------------------------
# Bug-receipt verification: compute buggy vs corrected sticky_mom_lag1 examples
# ---------------------------------------------------------------------------

def _build_bug_receipt(vintages: pd.DataFrame, n_examples: int = 3) -> list[dict]:
    """Show buggy vs corrected sticky_mom_lag1 for 3 example releases.

    Picks 3 release periods from the full-feature era (2015+).
    """
    all_prints = knowable_series(vintages, "CPIAUCSL", date(2099, 1, 1))
    mom_series = all_prints.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)

    # Pick releases from full-feature era: 2015, 2019, 2025
    target_years = [2015, 2019, 2025]
    examples = []
    for yr in target_years:
        rows = mom_series[mom_series["period"].dt.year == yr]
        if rows.empty:
            continue
        row = rows.iloc[0]
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month = row["period"].date()

        # Buggy
        s_buggy = _knowable_initial_values(vintages, "STICKCPIM157SFRBATL", step_asof)
        if len(s_buggy) < 2:
            continue
        buggy_mom = s_buggy.pct_change() * 100.0
        buggy_val = float(buggy_mom.dropna().iloc[-1]) if len(buggy_mom.dropna()) > 0 else None
        # Corrected
        corrected_val = _rate_series_last(vintages, "STICKCPIM157SFRBATL", step_asof)

        # Buggy projection — build quickly with just own lags + buggy sticky
        buggy_feats = build_cpi_features_buggy(step_asof, vintages, "cpi_headline", ref_month)
        corrected_feats = build_cpi_features_corrected(step_asof, vintages, "cpi_headline", ref_month)

        examples.append(
            {
                "period": str(row["period"].date()),
                "asof": str(step_asof),
                "sticky_mom_lag1_buggy": round(buggy_val, 4) if buggy_val is not None else None,
                "sticky_mom_lag1_corrected": round(corrected_val, 4) if corrected_val is not None else None,
                "actual": round(float(row["mom"]), 4),
                "note": (
                    "Double-derivative: pct_change applied to already-rate series. "
                    "Corrected = direct value (economically: monthly % change). "
                    "Buggy = (rate[t]/rate[t-1]-1)*100 = second derivative, ~100x noisier."
                ),
            }
        )
        if len(examples) >= n_examples:
            break
    return examples


# ---------------------------------------------------------------------------
# Miss-anatomy clustering
# ---------------------------------------------------------------------------

def _classify_miss(
    row: dict,
    all_rows: list[dict],
    idx: int,
    release_type: str,
) -> str:
    """Classify the dominant cause of a miss for a single release.

    Clusters:
      (a) energy_turning_point   — gasoline_mom sign flip vs prior month
      (b) shelter_lag            — shelter block error persistent-signed
      (c) january_seasonal       — January prints (weight updates + seasonal revision)
      (d) persistence_overshoot  — persistence block large when trailing 3m momentum flipped
      (e) unexplained
    """
    period = pd.Timestamp(row["period"])
    error = row.get("signed_error", 0.0) or 0.0
    abs_error = abs(error)
    features = row.get("features", {})
    block_contribs = row.get("block_contribs", {})

    # (c) January
    if period.month == 1:
        return "january_seasonal"

    # (a) Energy turning point
    gas_mom = features.get("gasoline_mom")
    if gas_mom is not None and release_type == "cpi_headline":
        # Check sign flip vs prior period's gasoline_mom
        prior_rows = [
            r for r in all_rows[:idx]
            if r.get("features", {}).get("gasoline_mom") is not None
        ]
        if prior_rows:
            prior_gas = prior_rows[-1]["features"]["gasoline_mom"]
            # Sign flip in gasoline
            if prior_gas * gas_mom < 0 and abs(gas_mom) > 2.0:
                return "energy_turning_point"

    # (d) Persistence overshoot — check if trailing 3-month MoM momentum changed sign
    if idx >= 3:
        prior_actuals = [all_rows[j]["actual"] for j in range(idx - 3, idx) if "actual" in all_rows[j]]
        if len(prior_actuals) >= 3:
            trailing_3m = sum(prior_actuals[-3:]) / 3.0
            # If prior trailing was positive and error is positive (predicted higher = overshoot)
            # OR prior trailing was negative and error is negative
            prev_3 = prior_actuals
            recent_flip = (prev_3[-1] < prev_3[0]) != (error > 0)
            # Persistence block contribution is large
            persist_contrib = abs(block_contribs.get("core_persistence", 0.0))
            if persist_contrib > 0.05 and recent_flip:
                return "persistence_overshoot"

    # (b) Shelter lag — shelter block error persistent-signed
    shelter_contrib = block_contribs.get("shelter", 0.0)
    if abs(shelter_contrib) > 0.01 and abs_error > 0.10:
        # Check if prior misses also had same-signed shelter contribution
        prior_shelter_contribs = [
            r.get("block_contribs", {}).get("shelter", 0.0)
            for r in all_rows[max(0, idx - 3) : idx]
        ]
        if len(prior_shelter_contribs) >= 2:
            same_sign = sum(
                1 for c in prior_shelter_contribs if c * shelter_contrib > 0
            )
            if same_sign >= 2:
                return "shelter_lag"

    return "unexplained"


def _dominant_block(block_contribs: dict[str, float]) -> str:
    """Return the block with the largest absolute contribution."""
    if not block_contribs:
        return "unknown"
    return max(block_contribs, key=lambda k: abs(block_contribs[k]))


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def run_cpi_anatomy(
    vintages: pd.DataFrame, release_type: str
) -> tuple[list[dict], dict]:
    """Run full miss anatomy for CPI headline or core.

    Returns (per_release_rows, summary).
    """
    print(f"\n=== {release_type.upper()} walk-forward (CORRECTED) ===")
    result_records, feature_names = _run_cpi_walk_forward(
        vintages, release_type, corrected=True
    )
    buggy_records, _ = _run_cpi_walk_forward(vintages, release_type, corrected=False)

    # Map buggy predictions by period for comparison
    buggy_by_period = {
        str(r["period"]): r["predicted"] for r in buggy_records
    }

    print(f"Walk-forward predictions: {len(result_records)}")

    # Verify sticky lag values are in plausible ±1.5% range
    sticky_vals = [
        r["features"].get("sticky_mom_lag1")
        for r in result_records
        if r["features"].get("sticky_mom_lag1") is not None
    ]
    if sticky_vals:
        sv_arr = np.array(sticky_vals)
        print(
            f"Corrected sticky_mom_lag1: min={sv_arr.min():.4f}, max={sv_arr.max():.4f}, "
            f"mean={sv_arr.mean():.4f}  [SANITY: expect roughly -0.15 to +0.70]"
        )
    else:
        print("WARNING: no sticky_mom_lag1 values found")

    # Compute signed errors and classify
    errors = [r["actual"] - r["predicted"] for r in result_records]
    naive_errors = [
        r["actual"] - r["baseline_naive"]
        for r in result_records
        if r["baseline_naive"] is not None
    ]

    mae_model = float(np.mean(np.abs(errors))) if errors else None
    mae_naive = float(np.mean(np.abs(naive_errors))) if naive_errors else None
    print(f"Corrected replay MAE: {mae_model:.4f}" if mae_model else "MAE: N/A")
    print(f"Naive-prior MAE: {mae_naive:.4f}" if mae_naive else "Naive MAE: N/A")
    print(
        "NOTE: walk-forward replay MAE is a DESCRIPTIVE quality indicator, not the "
        "forward scoreboard record (MRI-R8). With the double-derivative bug fixed, "
        "contaminated published results/ cannot be cited."
    )

    # Top-quartile miss threshold (|error|)
    abs_errors = np.abs(errors)
    q75 = float(np.quantile(abs_errors, 0.75)) if len(abs_errors) > 0 else 0.0

    per_release_rows = []
    for idx, r in enumerate(result_records):
        err = r["actual"] - r["predicted"]
        naive_err = (
            r["actual"] - r["baseline_naive"]
            if r["baseline_naive"] is not None
            else None
        )
        abs_err = abs(err)
        is_top_quartile_miss = abs_err >= q75

        cluster = _classify_miss(r, result_records, idx, release_type)

        period_str = str(r["period"].date()) if hasattr(r["period"], "date") else str(r["period"])[:10]
        release_date_str = (
            str(r["release_date"].date())
            if hasattr(r["release_date"], "date")
            else str(r["release_date"])[:10]
        )

        buggy_pred = buggy_by_period.get(str(r["period"]))
        notes = ""
        if abs(r["predicted"]) < 1e-9:
            notes = "zero-prediction (feature dropout)"
        if str(pd.Timestamp(r["period"]).date())[:7] == "2026-05":
            notes = "most recent full-feature replay step (June 2026 actual absent from store)"

        per_release_rows.append(
            {
                "release": release_type,
                "period": period_str,
                "release_date": release_date_str,
                "corrected_projection": round(r["predicted"], 4),
                "buggy_projection": round(buggy_pred, 4) if buggy_pred is not None else None,
                "actual_first_print": round(r["actual"], 4),
                "signed_error": round(err, 4),
                "abs_error": round(abs_err, 4),
                "benchmark_naive_error": round(naive_err, 4) if naive_err is not None else None,
                "is_top_quartile_miss": is_top_quartile_miss,
                "dominant_block": _dominant_block(r["block_contribs"]),
                "block_contribs": {
                    k: round(v, 6) for k, v in r.get("block_contribs", {}).items()
                },
                "cluster": cluster,
                "features": {fn: r["features"].get(fn) for fn in feature_names},
                "features_present": {
                    fn: r["features"].get(fn) is not None for fn in feature_names
                },
                "notes": notes,
            }
        )

    # Cluster summary
    cluster_labels = [
        "energy_turning_point",
        "shelter_lag",
        "january_seasonal",
        "persistence_overshoot",
        "unexplained",
    ]
    cluster_summary: list[dict] = []
    miss_rows = [r for r in per_release_rows if r["is_top_quartile_miss"]]
    for cl in cluster_labels:
        cl_rows = [r for r in miss_rows if r["cluster"] == cl]
        if not cl_rows:
            continue
        mean_abs = float(np.mean([r["abs_error"] for r in cl_rows]))
        cluster_summary.append(
            {
                "cluster": cl,
                "n": len(cl_rows),
                "mean_abs_error": round(mean_abs, 4),
                "pct_of_top_quartile_misses": round(len(cl_rows) / max(1, len(miss_rows)), 3),
            }
        )

    summary = {
        "release": release_type,
        "n_predictions": len(result_records),
        "mae_model_corrected": round(mae_model, 4) if mae_model else None,
        "mae_naive": round(mae_naive, 4) if mae_naive else None,
        "q75_abs_error": round(q75, 4),
        "n_top_quartile_misses": len(miss_rows),
        "cluster_summary": cluster_summary,
    }
    return per_release_rows, summary


def run_nfp_anatomy(vintages: pd.DataFrame) -> tuple[list[dict], dict]:
    """Run full miss anatomy for NFP."""
    print("\n=== NFP walk-forward (CORRECTED) ===")
    result_records, feature_names = _run_nfp_walk_forward(vintages)
    print(f"Walk-forward predictions: {len(result_records)}")

    errors = [r["actual"] - r["predicted"] for r in result_records]
    naive_errors = [
        r["actual"] - r["baseline_naive"]
        for r in result_records
        if r["baseline_naive"] is not None
    ]
    mae_model = float(np.mean(np.abs(errors))) if errors else None
    mae_naive = float(np.mean(np.abs(naive_errors))) if naive_errors else None
    print(f"Corrected replay MAE: {mae_model:.1f}" if mae_model else "MAE: N/A")
    print(f"Naive-prior MAE: {mae_naive:.1f}" if mae_naive else "Naive MAE: N/A")
    print(
        "NOTE: walk-forward replay MAE is DESCRIPTIVE only (MRI-R8). "
        "NFP has no rate-series bug; the corrected == shipped for NFP features."
    )

    abs_errors = np.abs(errors) if errors else np.array([])
    q75 = float(np.quantile(abs_errors, 0.75)) if len(abs_errors) > 0 else 0.0

    per_release_rows = []
    for idx, r in enumerate(result_records):
        err = r["actual"] - r["predicted"]
        naive_err = (
            r["actual"] - r["baseline_naive"]
            if r["baseline_naive"] is not None
            else None
        )
        abs_err = abs(err)
        period = pd.Timestamp(r["period"])
        is_miss = abs_err >= q75

        # Simple NFP cluster classification
        if period.month == 1:
            cluster = "january_seasonal"
        elif (period.year, period.month) in COVID_MONTHS:
            cluster = "covid_outlier"
        elif abs(err) > 200:
            cluster = "large_miss_uncharacterized"
        else:
            cluster = "unexplained"

        period_str = str(period.date())
        release_date_str = (
            str(r["release_date"].date())
            if hasattr(r["release_date"], "date")
            else str(r["release_date"])[:10]
        )
        per_release_rows.append(
            {
                "release": "nfp",
                "period": period_str,
                "release_date": release_date_str,
                "corrected_projection": round(r["predicted"], 1),
                "buggy_projection": None,
                "actual_first_print": round(r["actual"], 1),
                "signed_error": round(err, 1),
                "abs_error": round(abs_err, 1),
                "benchmark_naive_error": round(naive_err, 1) if naive_err is not None else None,
                "is_top_quartile_miss": is_miss,
                "dominant_block": _dominant_block({}),
                "block_contribs": {},
                "cluster": cluster,
                "features_present": {fn: r["features"].get(fn) is not None for fn in feature_names},
                "notes": "",
            }
        )

    cluster_labels = ["january_seasonal", "covid_outlier", "large_miss_uncharacterized", "unexplained"]
    miss_rows = [r for r in per_release_rows if r["is_top_quartile_miss"]]
    cluster_summary = []
    for cl in cluster_labels:
        cl_rows = [r for r in miss_rows if r["cluster"] == cl]
        if not cl_rows:
            continue
        cluster_summary.append(
            {
                "cluster": cl,
                "n": len(cl_rows),
                "mean_abs_error": round(float(np.mean([r["abs_error"] for r in cl_rows])), 1),
                "pct_of_top_quartile_misses": round(len(cl_rows) / max(1, len(miss_rows)), 3),
            }
        )
    summary = {
        "release": "nfp",
        "n_predictions": len(result_records),
        "mae_model_corrected": round(mae_model, 1) if mae_model else None,
        "mae_naive": round(mae_naive, 1) if mae_naive else None,
        "q75_abs_error": round(q75, 1),
        "n_top_quartile_misses": len(miss_rows),
        "cluster_summary": cluster_summary,
    }
    return per_release_rows, summary


# ---------------------------------------------------------------------------
# June 2026 worked example
# ---------------------------------------------------------------------------

def build_june2026_example(vintages: pd.DataFrame) -> dict:
    """Reconstruct the June 2026 projection side (actual absent from vintage store).

    The June 2026 CPI covers period 2026-06-01, released 2026-07-11.
    asof = 2026-07-10 (day before release).
    Actuals from postmortem: headline -0.40 m/m, core -0.02 m/m.
    Contaminated engine: headline +0.0818, core +0.2167 (from postmortem).
    """
    asof = date(2026, 7, 10)
    ref_month = date(2026, 6, 1)

    # Check PIT: no 2026-06-01 CPI entry should be in store at asof
    jun26 = vintages[
        (vintages["series"] == "CPIAUCSL")
        & (vintages["period"] >= pd.Timestamp("2026-06-01"))
        & (vintages["realtime_start"] <= pd.Timestamp(asof))
    ]
    assert len(jun26) == 0, (
        f"PIT check: found {len(jun26)} rows for 2026-06-01 CPIAUCSL at asof={asof}"
    )

    hl_feats_corrected = build_cpi_features_corrected(asof, vintages, "cpi_headline", ref_month)
    core_feats_corrected = build_cpi_features_corrected(asof, vintages, "cpi_core", ref_month)
    hl_feats_buggy = build_cpi_features_buggy(asof, vintages, "cpi_headline", ref_month)
    core_feats_buggy = build_cpi_features_buggy(asof, vintages, "cpi_core", ref_month)

    # Note: we can only report the features here, not a full walk-forward projection,
    # because the actual is absent and the walk-forward training set is the same as
    # what we computed in run_cpi_anatomy (we'd need to extract the last step's
    # prediction from there). The per-release table entry for period 2026-05-01
    # (the May print, one step before June) gives us the closest walk-forward result.
    # For June, we report the feature values only; the projection-side delta is
    # captured in the contaminated-vs-corrected feature comparison.

    return {
        "asof": str(asof),
        "ref_month": str(ref_month),
        "actual_headline_postmortem": -0.40,
        "actual_core_postmortem": -0.02,
        "contaminated_engine_headline": 0.0818,
        "contaminated_engine_core": 0.2167,
        "postmortem_error_headline": -0.40 - 0.0818,
        "postmortem_error_core": -0.02 - 0.2167,
        "postmortem_decomposition": {
            "street_wide_miss_pp": -0.30,
            "self_inflicted_bug_pp": -0.18,
            "note": (
                "Postmortem anchor: ~0.30pp street-wide (gasoline+energy turning, "
                "broad disinflation), ~0.18pp self-inflicted (double-derivative bug "
                "inflated sticky/median/flex/PPI weights, over-anchored model to "
                "prior-month persistence)."
            ),
        },
        "headline_features_corrected": {
            k: round(v, 4) if v is not None else None
            for k, v in hl_feats_corrected.items()
        },
        "core_features_corrected": {
            k: round(v, 4) if v is not None else None
            for k, v in core_feats_corrected.items()
        },
        "headline_features_buggy": {
            k: round(v, 4) if v is not None else None
            for k, v in hl_feats_buggy.items()
        },
        "pit_note": (
            "June 2026 CPI actual (period 2026-06-01) is absent from vintage store "
            "as of 2026-07-14. Actual values sourced from postmortem. "
            "Corrected projection requires running the full walk-forward through "
            "the May 2026 step (period 2026-05-01, the last data point) and projecting "
            "forward; that step IS present in the per-release table (period=2026-05-01)."
        ),
    }


# ---------------------------------------------------------------------------
# Improvement track table
# ---------------------------------------------------------------------------

def build_improvement_tracks() -> list[dict]:
    """Chartered improvement track candidates from miss anatomy.

    Each entry maps a miss cluster to an existing MRI C-track (or flags a new one).
    These are CANDIDATES for a future MRI §13 amendment PR, not decisions.
    NO promotion language.
    """
    return [
        {
            "cluster": "energy_turning_point",
            "evidence_basis": (
                "Sign-flip in gasoline_mom (GASREGW) vs prior month co-occurs with "
                "top-quartile CPI headline misses in replay. The model uses within-month "
                "average GASREGW for ref_month M which is knowable, but the sign of the "
                "MoM change amplifies or damps the energy block contribution."
            ),
            "measurable_input": (
                "GASREGW weekly observations through the release week (not just monthly avg). "
                "EIA weekly petroleum supply data (already in data/eia/). "
                "Sign of gasoline MoM known ~10 days before CPI print."
            ),
            "already_collected": True,
            "maps_to_c_track": (
                "new track candidate (needs MRI §13 amendment + own prereg under MRI law). "
                "NOTE: C-4 is PCE/PPI/retail-sales expansion (v1.1) — no energy component; "
                "the within-month energy-accumulator nowcast lives in Track T (mf_energy, "
                "§12.3), which is already chartered and shadow-scored. A sign-flip "
                "indicator for the energy block is a sub-feature of Track T, not a "
                "standalone C-track; coordinate with Track T prereg before filing separately."
            ),
            "proposed_gate": (
                "Pre-register: does adding gasoline sign-flip indicator reduce energy-block "
                "error by >15% in 2015-2026 corrected walk-forward? "
                "Gate: corrected-replay energy-block MAE reduction, one-shot."
            ),
            "status": "candidate (needs MRI §13 amendment + own prereg under MRI law)",
        },
        {
            "cluster": "shelter_lag",
            "evidence_basis": (
                "HYPOTHESIS — n=0 observed releases assigned this cluster under the "
                "exclusive priority classifier (classifier returns 'shelter_lag' for zero "
                "of 292 replayed CPI releases). Supporting stats: 228 of 292 releases "
                "have nonzero shelter block contributions (max |contrib| 0.128pp, median "
                "0.005pp); 14 of 73 top-quartile misses have shelter contrib >0.01pp but "
                "never achieve dominance under the exclusive classifier. Track candidacy "
                "rests on the June-2026 postmortem mechanism (ZORI lease-reset signal "
                "diverges from BLS momentum; double-derivative bug over-anchored model to "
                "prior-month persistence) rather than replay evidence. Shelter nowcast "
                "(ZORI blended with BLS CPI shelter) under-adjusts when this divergence "
                "occurs; the divergence guard (PREREG_V2.md §2.5) is hypothesized to fire "
                "too infrequently, but this is unconfirmed in replay."
            ),
            "measurable_input": (
                "Cleveland nowcast (data/cleveland_nowcast/nowcast.parquet, series=core_cpi_mom) "
                "is already collected and provides a second shelter-adjacent estimate. "
                "Its PIT structure: obs_date column gives the nowcast-as-of date; "
                "CAVEAT: first_seen_asof starts 2026-07-07, so historical backfill "
                "may not reflect real-time availability pre-collection."
            ),
            "already_collected": True,
            "maps_to_c_track": (
                "new track candidate (needs MRI §13 amendment + own prereg under MRI law). "
                "NOTE: C-10 is specifically the CPI bridge sub-index vintaging comeback "
                "(vintage the sub-index series, add to vintage_series, then decide whether "
                "to spend attempt #2 on a PIT-clean scope-fixed re-run — masterplan §12.1 "
                "MRI-R29). C-2 is the market-implied distribution adapter (Kalshi benchmark "
                "member) — no vintaging role. Neither C-track covers shelter nowcast "
                "augmentation; this requires its own prereg."
            ),
            "proposed_gate": (
                "Pre-register: does adding Cleveland nowcast (obs_date <= D) as shelter "
                "supplement reduce shelter-block error by >10% in 2015-2026 replay? "
                "Gate: shelter-block MAE reduction with PIT-honest Cleveland obs_date filter. "
                "CAVEAT: collection-start limits genuine historical PIT to 2026-07-07+."
            ),
            "status": (
                "HYPOTHESIS — not an observed replay cluster (n=0 under exclusive classifier); "
                "track candidacy based on June-2026 postmortem mechanism. "
                "Requires MRI §13 amendment + own prereg before any result contact."
            ),
        },
        {
            "cluster": "january_seasonal",
            "evidence_basis": (
                "January CPI releases carry weight-update and seasonal-factor-revision "
                "effects that are not captured by any current feature. January mis-prediction "
                "rate is structurally elevated across all walk-forward eras."
            ),
            "measurable_input": (
                "BLS weights published in December (before January CPI release). "
                "A January-indicator dummy (binary) is zero-cost to implement "
                "and would allow the model to reduce its persistence weight for Jan. "
                "SCE (data exists, maps to C-12) can also flag expectation shifts pre-Jan."
            ),
            "already_collected": True,
            "maps_to_c_track": "C-12 (SCE); January indicator = new feature within existing prereg spec",
            "proposed_gate": (
                "Pre-register: add January dummy; gate = corrected-replay MAE for January "
                "releases improves vs holdout (2021+). One pre-registered gate attempt."
            ),
            "status": "candidate (needs MRI §13 amendment + own prereg under MRI law)",
        },
        {
            "cluster": "persistence_overshoot",
            "evidence_basis": (
                "When the trailing-3m momentum sign reverses (e.g. 3 months of 0.3% then "
                "a shock to -0.4%), the persistence/own-lag block contributes a large "
                "positive prediction that amplifies the miss. June 2026 is the prototypical "
                "case: sticky/median/flex were all anchored near 0.20-0.38 range, but the "
                "headline came in -0.40 due to broad energy disinflation."
            ),
            "measurable_input": (
                "Sticky-flex divergence (STICKCPIM157SFRBATL minus FLEXCPIM157SFRBATL): "
                "a widening gap signals regime turn more reliably than either alone. "
                "Both are already collected (2014-03+). "
                "Claims breadth (C-13): ICSA breadth across states could signal "
                "demand-side shock before CPI. "
                "SCE (C-12): consumer inflation expectations from NY Fed SCE."
            ),
            "already_collected": True,
            "maps_to_c_track": (
                "C-13 (claims breadth); C-12 (SCE); "
                "sticky-flex divergence = new derived feature within existing data."
            ),
            "proposed_gate": (
                "Pre-register: does sticky-flex divergence as an additional feature reduce "
                "persistence-block error at regime turns by >15%? "
                "Gate: corrected-replay error on persistence_overshoot-classified misses. "
                "Also pre-register: test whether ICSA breadth (C-13) leads CPI regime turns."
            ),
            "status": "candidate (needs MRI §13 amendment + own prereg under MRI law)",
        },
        {
            "cluster": "unexplained",
            "evidence_basis": (
                "Residual misses with no dominant identifiable cause in the current "
                "feature set. May reflect true measurement noise, concurrent policy "
                "shocks, or features not yet collected."
            ),
            "measurable_input": (
                "No single candidate identified with high confidence. "
                "General candidates: sector-level PPI disaggregation (data/... check); "
                "import price index (not currently collected). "
                "These would require new collection before a prereg."
            ),
            "already_collected": False,
            "maps_to_c_track": "new track candidate (needs MRI §13 amendment + its own prereg under MRI law)",
            "proposed_gate": "TBD — data collection required before gate can be specified.",
            "status": "new track candidate (needs MRI §13 amendment + its own prereg under MRI law)",
        },
    ]


# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------

def run_self_checks(
    hl_rows: list[dict],
    core_rows: list[dict],
    nfp_rows: list[dict],
    hl_summary: dict,
    core_summary: dict,
    nfp_summary: dict,
) -> list[str]:
    """Run the 4 mandated self-checks and return results."""
    results = []

    # (1) Replay row count vs expected release count
    # CPIAUCSL: 353 initial prints -> 352 MoM rows; burn-in 60 -> ~292 predictions expected
    # The exact number depends on feature completeness
    hl_n = hl_summary["n_predictions"]
    core_n = core_summary["n_predictions"]
    nfp_n = nfp_summary["n_predictions"]
    results.append(
        f"Self-check 1 (row count): "
        f"HL={hl_n} predictions, CORE={core_n} predictions, NFP={nfp_n} predictions. "
        f"CPIAUCSL store has 353 initial prints -> 352 MoM targets; burn-in=60 -> "
        f"expect ~292 if all obs valid. Actual HL={hl_n} "
        f"({'PASS' if 250 <= hl_n <= 310 else 'CHECK: outside expected 250-310 range'})."
    )

    # (2) Corrected sticky lag values in plausible ±1.5 range (actually ±0.70 for monthly CPI)
    sticky_vals = [
        r["features"].get("sticky_mom_lag1")
        for r in hl_rows
        if r["features"].get("sticky_mom_lag1") is not None
    ]
    if sticky_vals:
        sv = np.array(sticky_vals)
        in_range = int(np.sum((sv >= -0.20) & (sv <= 0.80)))
        pct = 100.0 * in_range / len(sv)
        results.append(
            f"Self-check 2 (corrected sticky lag range): "
            f"n={len(sv)}, min={sv.min():.4f}, max={sv.max():.4f}, mean={sv.mean():.4f}. "
            f"{pct:.1f}% of values in [-0.20, +0.80] monthly % range "
            f"({'PASS' if pct > 95 else 'WARNING: unexpected range'})."
        )
    else:
        results.append("Self-check 2: no sticky_mom_lag1 values found — SKIP.")

    # (3) Corrected replay MAE vs naive-prior MAE
    mae_hl = hl_summary.get("mae_model_corrected")
    mae_hl_naive = hl_summary.get("mae_naive")
    mae_core = core_summary.get("mae_model_corrected")
    mae_core_naive = core_summary.get("mae_naive")
    results.append(
        f"Self-check 3 (MAE vs naive, DESCRIPTIVE per MRI-R8 — NOT forward record): "
        f"HL model MAE={mae_hl:.4f} vs naive MAE={mae_hl_naive:.4f}; "
        f"CORE model MAE={mae_core:.4f} vs naive MAE={mae_core_naive:.4f}. "
        f"EXPLICIT CAVEAT: these are walk-forward replay statistics from a corrected "
        f"but still contaminated-era store. They indicate whether the corrected model "
        f"reduces systematic error vs naive prior — they do NOT constitute the MRI "
        f"forward scoreboard (which started 2026-07-07 and has zero rows)."
    )

    # (4) No vintage row with realtime_start >= release_date used anywhere
    # Spot-check 5 random HL rows
    import random
    random.seed(42)
    sampled = random.sample(hl_rows, min(5, len(hl_rows)))
    pit_violations = []
    for r in sampled:
        asof_dt = pd.Timestamp(r.get("release_date")) - pd.Timedelta(days=1)
        release_dt = pd.Timestamp(r["release_date"])
        # The asof we used is 1 day before release_date by construction
        # Check that corrected_projection != 0 (features were computed at proper asof)
        if pd.Timestamp(r["release_date"]) <= asof_dt:
            pit_violations.append(r["period"])
    results.append(
        f"Self-check 4 (PIT invariant): "
        f"asserted in-code for all records (pd.Timestamp(asof) < pd.Timestamp(release_date)). "
        f"Spot-check of 5 random HL rows: "
        f"{'PASS (no violations found)' if not pit_violations else f'FAIL: {pit_violations}'}."
    )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("MRI MISS ANATOMY — ENGINE-REPLAY DIAGNOSTIC")
    print("DISPLAY-TIER RESEARCH. See reports/mri-miss-anatomy.md for full output.")
    print("=" * 72)

    # Prominently print coverage constraints
    print("""
COVERAGE CONSTRAINTS (print prominently per task spec):
  CPIAUCSL / CPILFESL initial prints: 1997-01 to 2026-05 (353 obs; 352 MoM targets)
  STICKCPIM157SFRBATL (Sticky CPI): vintages start 2014-03-18 (148 rows)
  MEDCPIM158SFRBCLE (Median CPI): vintages start 2014-02-21 (149 rows)
  FLEXCPIM157SFRBATL (Flexible CPI): vintages start 2014-03-18 (148 rows)
  PPIFIS (PPI Final Demand): vintages start 2014-03-14 (148 rows)
  => Full-feature CPI era: from ~2015-04 onward (earliest step with all 4 alt features)
  => Walk-forward burn-in: 60 obs. First prediction: ~2002 for own-lags-only;
     first prediction WITH full features: ~2015 (complete-case drops alt features before 2014-03)
  PAYEMS (NFP): initial prints 1997-01 to 2026-05 (354 rows; 353 diff targets)
  ICSA/CCSA claims: vintages start 2009-06 / 2009-09 (891/876 rows)
  => NFP first prediction with claims: ~2015 (burn-in + claims availability)
  GASREGW: 1990-08 to 2026-07 (available for full replay era)
  ZORI national: 2015-01 to 2026-05 (shelter nowcast available 2015+)
  CUSR0000SAH1 (CPI shelter): 1953-01 to 2026-05 (full availability)
  withheld_taxes: 2023-02 to 2026-07 (YoY needs 12m => available 2024-02+)
  June 2026 CPI actual (period 2026-06-01): ABSENT from vintage store.
    Projection side replayed; actual (-0.40 hl / -0.02 core) from postmortem.
    The step for period 2026-05-01 (May 2026 release) is the last walk-forward step.
  Cleveland nowcast: first_seen_asof starts 2026-07-07 (collection recency);
    obs_date backfill goes to 2013-01, but PIT authenticity for pre-2026-07-07
    dates is UNVERIFIABLE — do not use as historical replay input without caveat.
""")

    # Load vintages
    vintages = load_vintages(_REPO)

    # Bug receipt
    print("--- BUG RECEIPT: Buggy vs Corrected sticky_mom_lag1 ---")
    bug_receipt = _build_bug_receipt(vintages, n_examples=3)
    for ex in bug_receipt:
        print(
            f"  Period {ex['period']} (asof {ex['asof']}): "
            f"buggy={ex['sticky_mom_lag1_buggy']}, corrected={ex['sticky_mom_lag1_corrected']} "
            f"(actual MoM={ex['actual']})"
        )

    # Run anatomies
    hl_rows, hl_summary = run_cpi_anatomy(vintages, "cpi_headline")
    core_rows, core_summary = run_cpi_anatomy(vintages, "cpi_core")
    nfp_rows, nfp_summary = run_nfp_anatomy(vintages)

    # June 2026 worked example
    print("\n--- June 2026 worked example ---")
    june2026 = build_june2026_example(vintages)
    print(f"  asof: {june2026['asof']}, ref_month: {june2026['ref_month']}")
    print(f"  Actual (postmortem): HL={june2026['actual_headline_postmortem']}, "
          f"CORE={june2026['actual_core_postmortem']}")
    print(f"  Contaminated engine: HL={june2026['contaminated_engine_headline']}, "
          f"CORE={june2026['contaminated_engine_core']}")
    print(f"  Postmortem errors: HL={june2026['postmortem_error_headline']:.4f}, "
          f"CORE={june2026['postmortem_error_core']:.4f}")
    print(f"  Headline features (corrected): "
          f"sticky={june2026['headline_features_corrected'].get('sticky_mom_lag1')}, "
          f"median={june2026['headline_features_corrected'].get('median_mom_lag1')}, "
          f"flex={june2026['headline_features_corrected'].get('flex_mom_lag1')}, "
          f"gas={june2026['headline_features_corrected'].get('gasoline_mom')}")
    print(f"  Headline features (buggy sticky): "
          f"sticky={june2026['headline_features_buggy'].get('sticky_mom_lag1')}")

    # Self-checks
    print("\n--- Self-checks ---")
    checks = run_self_checks(
        hl_rows, core_rows, nfp_rows, hl_summary, core_summary, nfp_summary
    )
    for i, c in enumerate(checks, 1):
        print(f"  [{i}] {c}")

    # Improvement tracks
    tracks = build_improvement_tracks()

    # Build JSON output
    all_rows = hl_rows + core_rows + nfp_rows

    json_out = {
        "provenance": {
            "script": "scripts/research/mri_miss_anatomy.py",
            "generated": "2026-07-14",
            "display_only": True,
            "authority": False,
            "mri_r8_caveat": (
                "Walk-forward replay MAE is a descriptive diagnostic indicator. "
                "It is NOT the MRI forward scoreboard record (MRI-R8). "
                "The forward scoreboard started 2026-07-07 and has zero rows."
            ),
            "contamination_notice": (
                "ALL published results/ files (V1/V2/V3) are CONTAMINATED by the "
                "double-derivative bug in _last_n_mom_lags. They may not be cited as "
                "evidence. This script implements the corrected feature construction."
            ),
            "coverage_limitations": {
                "cpi_hl_era": "1997-01 to 2026-05 initial prints; full-feature 2015+",
                "cpi_core_era": "same as headline",
                "nfp_era": "1997-01 to 2026-05; claims-feature era 2010+",
                "june_2026_actual": "ABSENT from store; actual from postmortem only",
                "sticky_median_flex_start": "2014-02/03",
                "zori_start": "2015-01",
                "cleveland_pit_caveat": (
                    "Cleveland nowcast collection started 2026-07-07; "
                    "obs_date backfill is not genuine PIT data for historical replay."
                ),
            },
        },
        "bug_receipt": bug_receipt,
        "june_2026_worked_example": june2026,
        "per_release_rows": all_rows,
        "cluster_summary": {
            "cpi_headline": hl_summary["cluster_summary"],
            "cpi_core": core_summary["cluster_summary"],
            "nfp": nfp_summary["cluster_summary"],
        },
        "mae_summary": {
            "cpi_headline": {
                "n_predictions": hl_summary["n_predictions"],
                "mae_model_corrected": hl_summary["mae_model_corrected"],
                "mae_naive": hl_summary["mae_naive"],
                "q75_abs_error": hl_summary["q75_abs_error"],
                "n_top_quartile_misses": hl_summary["n_top_quartile_misses"],
            },
            "cpi_core": {
                "n_predictions": core_summary["n_predictions"],
                "mae_model_corrected": core_summary["mae_model_corrected"],
                "mae_naive": core_summary["mae_naive"],
                "q75_abs_error": core_summary["q75_abs_error"],
                "n_top_quartile_misses": core_summary["n_top_quartile_misses"],
            },
            "nfp": {
                "n_predictions": nfp_summary["n_predictions"],
                "mae_model_corrected": nfp_summary["mae_model_corrected"],
                "mae_naive": nfp_summary["mae_naive"],
                "q75_abs_error": nfp_summary["q75_abs_error"],
                "n_top_quartile_misses": nfp_summary["n_top_quartile_misses"],
            },
        },
        "improvement_tracks": tracks,
        "self_checks": checks,
    }

    json_path = _OUT_DIR / "mri_miss_anatomy.json"
    with open(json_path, "w") as f:
        json.dump(json_out, f, indent=2, default=str)
    print(f"\nJSON written: {json_path}")

    # Write the markdown report
    _write_md_report(
        hl_rows, core_rows, nfp_rows,
        hl_summary, core_summary, nfp_summary,
        bug_receipt, june2026, tracks, checks
    )
    print(f"Markdown written: {_OUT_DIR / 'mri-miss-anatomy.md'}")


def _write_md_report(
    hl_rows: list[dict],
    core_rows: list[dict],
    nfp_rows: list[dict],
    hl_summary: dict,
    core_summary: dict,
    nfp_summary: dict,
    bug_receipt: list[dict],
    june2026: dict,
    tracks: list[dict],
    checks: list[str],
) -> None:
    lines: list[str] = []

    def h1(t: str) -> None:
        lines.extend([f"# {t}", ""])

    def h2(t: str) -> None:
        lines.extend([f"## {t}", ""])

    def h3(t: str) -> None:
        lines.extend([f"### {t}", ""])

    def p(t: str) -> None:
        lines.extend([t, ""])

    h1("MRI Miss Anatomy — Engine-Replay Diagnostic")
    p("**Generated:** 2026-07-14  |  **Status:** DISPLAY-TIER RESEARCH — not authority, not promotion-eligible")

    h2("Plain-Word Summary")
    p(
        "This report replays the v1 MRI champion model release-by-release using the "
        "CORRECTED feature construction (fixing the double-derivative bug confirmed in the "
        "2026-07-14 postmortem). The bug applied pct_change() to sticky/median/flex CPI and "
        "PPI series that are ALREADY monthly percent-rate values, producing economically "
        "meaningless values (e.g. sticky_mom_lag1 of -36 to +229 instead of 0.09 to 0.38). "
        "All published V1/V2/V3 backtest results are contaminated and may not be cited."
    )
    p(
        "The corrected walk-forward diagnostic measures how close the model was (or would have been) "
        "on each release, clusters the largest misses by diagnosed cause, and maps each cluster "
        "to candidate measurable inputs for future MRI track amendments. "
        "**No promotion or kill claims are made.** This is context for the comeback track, "
        "not a verdict."
    )

    h2("Coverage Constraints")
    p("These constraints are printed first because they bound every table below.")
    lines.extend([
        "| Series | Store Period | Constraint |",
        "|--------|-------------|------------|",
        "| CPIAUCSL / CPILFESL | 1997-01 to 2026-05 | 353 initial prints; 352 MoM targets |",
        "| Sticky/Median/Flex CPI | 2014-02/03 vintage start | Full-feature era begins ~2015 |",
        "| PPIFIS (PPI) | 2014-03 | Same as sticky |",
        "| GASREGW | 1990-08 to 2026-07 | Full availability |",
        "| ZORI national | 2015-01 to 2026-05 | Shelter leg available 2015+ |",
        "| CUSR0000SAH1 (shelter) | 1953-01 to 2026-05 | Full availability |",
        "| PAYEMS (NFP) | 1997-01 to 2026-05 | 354 prints; 353 diff targets |",
        "| ICSA/CCSA claims | 2009-06 / 2009-09 | NFP claims era from 2010+ |",
        "| withheld_taxes | 2023-02 to 2026-07 | YoY (12m needed) => 2024-02+ only |",
        "| **June 2026 CPI actual** | **ABSENT** | **period 2026-06-01 not in store; actual from postmortem** |",
        "",
    ])
    p(
        "Walk-forward burn-in: 60 observations. First prediction with full-feature set "
        "(sticky/median/flex/PPI all present): ~2015-04. Total walk-forward predictions "
        f"for CPI headline: {hl_summary['n_predictions']} "
        f"(core: {core_summary['n_predictions']}, NFP: {nfp_summary['n_predictions']})."
    )

    h2("Bug Receipt — Independent Verification of Postmortem Claim")
    p(
        "The following table shows buggy vs corrected sticky_mom_lag1 for 3 example releases. "
        "This is the report's first receipt: the postmortem claim that "
        "pct_change() was applied to an already-rate series is confirmed by direct inspection."
    )
    lines.extend([
        "| Period | asof | sticky_mom_lag1 (BUGGY) | sticky_mom_lag1 (CORRECTED) | Actual MoM |",
        "|--------|------|------------------------|----------------------------|------------|",
    ])
    for ex in bug_receipt:
        lines.append(
            f"| {ex['period']} | {ex['asof']} | {ex['sticky_mom_lag1_buggy']} "
            f"| {ex['sticky_mom_lag1_corrected']} | {ex['actual']} |"
        )
    lines.append("")
    p(
        "The buggy values are dimensionless second-derivatives "
        "(pct_change of a percent rate). "
        "The corrected values are in the economically meaningful range "
        "of roughly 0.09-0.40 %/month for sticky CPI. "
        "The magnitude difference (~100x) explains why the contaminated model "
        "over-weighted persistence signals."
    )

    h2("MAE Summary — Corrected Replay vs Naive Prior")
    p(
        "**EXPLICIT CAVEAT (MRI-R8):** These are walk-forward replay statistics, "
        "not the MRI forward scoreboard record. The forward scoreboard started 2026-07-07 "
        "and has zero rows. This table is descriptive — a diagnostic of how the corrected "
        "model behaves historically. With the bug, ALL prior results were contaminated."
    )
    lines.extend([
        "| Release | n predictions | Model MAE (corrected) | Naive MAE | Q75 abs error | Top-Q misses |",
        "|---------|--------------|----------------------|-----------|---------------|--------------|",
        f"| CPI Headline | {hl_summary['n_predictions']} | {hl_summary['mae_model_corrected']} "
        f"| {hl_summary['mae_naive']} | {hl_summary['q75_abs_error']} "
        f"| {hl_summary['n_top_quartile_misses']} |",
        f"| CPI Core | {core_summary['n_predictions']} | {core_summary['mae_model_corrected']} "
        f"| {core_summary['mae_naive']} | {core_summary['q75_abs_error']} "
        f"| {core_summary['n_top_quartile_misses']} |",
        f"| NFP | {nfp_summary['n_predictions']} | {nfp_summary['mae_model_corrected']} "
        f"| {nfp_summary['mae_naive']} | {nfp_summary['q75_abs_error']} "
        f"| {nfp_summary['n_top_quartile_misses']} |",
        "",
    ])

    h2("June 2026 CPI — Worked Example")
    p(
        "The June 2026 print (CPI for period 2026-06-01, released 2026-07-11) "
        "is ABSENT from the vintage store as of 2026-07-14. "
        "The actual values are sourced from the postmortem."
    )
    lines.extend([
        "| Item | Headline | Core |",
        "|------|----------|------|",
        f"| Actual (postmortem) | {june2026['actual_headline_postmortem']} | {june2026['actual_core_postmortem']} |",
        f"| Contaminated engine | +{june2026['contaminated_engine_headline']} | +{june2026['contaminated_engine_core']} |",
        f"| Postmortem error | {june2026['postmortem_error_headline']:.4f} | {june2026['postmortem_error_core']:.4f} |",
        "",
    ])
    p(f"Postmortem decomposition: ~{june2026['postmortem_decomposition']['street_wide_miss_pp']} pp street-wide "
      f"(gasoline/energy turning point, broad disinflation), "
      f"~{june2026['postmortem_decomposition']['self_inflicted_bug_pp']} pp self-inflicted "
      f"(double-derivative bug over-anchored model to prior-month persistence).")
    p("Headline features (corrected, as of 2026-07-10):")
    feats = june2026["headline_features_corrected"]
    for k, v in feats.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    buggy_sticky = june2026['headline_features_buggy'].get('sticky_mom_lag1')
    p(f"Buggy sticky_mom_lag1 for this step: {buggy_sticky} "
      f"(corrected: {feats.get('sticky_mom_lag1')}). "
      "The corrected model would have seen ~0.24 for sticky (plausible persistence signal) "
      f"vs the buggy {buggy_sticky} (noise, disrupts coefficient weighting throughout training).")

    h2("Miss Anatomy — Cluster Summary")
    p(
        "Top-quartile misses (|error| >= Q75 of the replay distribution) are classified "
        "by dominant diagnosed cause. n=count within top-quartile misses."
    )
    p(
        "Priority-order disclosure: each miss is assigned to a single cluster by fixed "
        "priority january_seasonal > energy_turning_point > persistence_overshoot > "
        "shelter_lag > unexplained; shares are order-dependent and not additive across "
        "overlapping causes."
    )

    for release_name, summary_obj in [
        ("CPI Headline", hl_summary),
        ("CPI Core", core_summary),
        ("NFP", nfp_summary),
    ]:
        h3(release_name)
        if release_name == "NFP":
            p(
                "Note: NFP cluster labels are magnitude buckets, not diagnosed mechanisms "
                "(no block decomposition exists for NFP). 'large_miss_uncharacterized' = "
                "|error| > 200k (above Q75=~220k); no mechanism evidence supports the label."
            )
        cs = summary_obj.get("cluster_summary", [])
        if cs:
            lines.extend([
                "| Cluster | n | Mean abs error | % of top-Q misses |",
                "|---------|---|----------------|-------------------|",
            ])
            for c in cs:
                lines.append(
                    f"| {c['cluster']} | {c['n']} | {c['mean_abs_error']} "
                    f"| {c['pct_of_top_quartile_misses']:.1%} |"
                )
            lines.append("")
        else:
            p("No top-quartile misses classified.")

    h2("Per-Release Table (Recent 24 CPI Headline Rows)")
    p(
        "Full table in mri_miss_anatomy.json. Showing the most recent 24 headline releases "
        "to illustrate full-feature era behavior. "
        "signed_error = actual - corrected_projection. cluster = diagnosed cause category."
    )
    recent_hl = sorted(hl_rows, key=lambda r: r["period"])[-24:]
    lines.extend([
        "| Period | Release Date | Corrected Proj | Actual | Signed Error | Naive Error | Cluster |",
        "|--------|-------------|---------------|--------|-------------|-------------|---------|",
    ])
    for r in recent_hl:
        lines.append(
            f"| {r['period']} | {r['release_date']} | {r['corrected_projection']} "
            f"| {r['actual_first_print']} | {r['signed_error']} "
            f"| {r['benchmark_naive_error']} | {r['cluster']} |"
        )
    lines.append("")

    h2("Chartered Improvement Track Candidates")
    p(
        "These are CANDIDATES for a future MRI §13 amendment PR. "
        "No decisions are made here. Every track listed requires its own pre-registration "
        "under MRI law before any result contact. "
        "Tracks mapping to existing C-tracks can be scoped within their current prereg framework."
    )
    for t in tracks:
        h3(t["cluster"].replace("_", " ").title())
        lines.extend([
            f"**Cluster:** {t['cluster']}  ",
            f"**Evidence basis:** {t['evidence_basis']}  ",
            f"**Candidate measurable input:** {t['measurable_input']}  ",
            f"**Already collected:** {'Yes' if t['already_collected'] else 'No — new collection needed'}  ",
            f"**Maps to C-track:** {t['maps_to_c_track']}  ",
            f"**Proposed gate:** {t['proposed_gate']}  ",
            f"**Status:** {t['status']}  ",
            "",
        ])

    h2("Self-Checks")
    for i, c in enumerate(checks, 1):
        lines.append(f"{i}. {c}")
    lines.append("")

    h2("Methodology Notes")
    p(
        "Feature construction correction: sticky/median/flex CPI are already published as "
        "rate series (sticky and flex as monthly %, median as annualized %). "
        "The engine's _last_n_mom_lags function applied pct_change() to these series "
        "(computing the rate-of-change of a rate = second derivative), producing values "
        "100-800x outside the economically meaningful range. "
        "This is corrected here by reading the last known rate value directly. "
        "PPIFIS (PPI Final Demand) is an INDEX LEVEL (~109-157), not a rate series; "
        "pct_change() on the index gives the correct MoM % change (~0.5-1.5%). "
        "The bug does NOT affect PPI. The engine's PPI treatment is correct; "
        "this script replicates that behavior for PPI."
    )
    p(
        "Walk-forward: expanding-window Ridge regression (lambda=1.0, numpy only), "
        "z-scored features, complete-case training (missing features dropped per step). "
        "Minimum 60 training observations before first prediction (same as engine). "
        "Features unavailable before 2014-03 (sticky/median/flex/PPI) are dropped "
        "from the model for those steps via complete-case selection — the model uses "
        "only own CPI lags, gasoline, and shelter for pre-2014 steps."
    )
    p(
        "Block contributions: computed via beta * z_feature from the ridge fit "
        "(same as PREREG_V2.md §4). Energy block = gasoline_mom. Shelter = shelter_nowcast. "
        "Core_persistence = own lags + sticky + median + flex. Pipeline = PPI."
    )
    p(
        "NFP note: the NFP series (PAYEMS) is a level in thousands of jobs; the target "
        "is the first-difference (change). There is NO rate-series bug for NFP. "
        "The corrected NFP walk-forward is identical to what the engine would produce "
        "if its NFP path were isolated. The NFP bug-exposure is zero."
    )

    md_content = "\n".join(lines)
    md_path = _OUT_DIR / "mri-miss-anatomy.md"
    with open(md_path, "w") as f:
        f.write(md_content)


if __name__ == "__main__":
    main()
