"""MRI Track N — New Release Target Specs: PCE Headline, PCE Core, PPI Final Demand, Retail Sales Scaffold.

LEAF · DISPLAY-ONLY. Pure numpy/pandas only (no sklearn/statsmodels/scipy.stats).

SPECIFICATION: research/release_forecast/PREREG_NEW_TARGETS_V1.md (frozen 2026-07-08)
Governing ruling: MRI-R23 (§11.1 of research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md)

Feature/model specs are frozen (attempt #1 of 2 each). No spec changes after any
backtest results are observed (anti-mining, §6 of masterplan).

This module exposes standalone spec functions for:
  - pce_headline  (PCEPI MoM SA, vintage 2000→)
  - pce_core      (PCEPILFE MoM SA, vintage 2000→)
  - ppi_finaldemand (PPIFIS MoM SA, vintage 2014→, thin history)
  - retail_sales  (RSAFS MoM SA, scaffold-only — no_data until series accrues)

Each function returns the same projection dict schema as the champion (engine/release_forecast.py).

display_only=True, authority=False on all outputs — never conditions scoring.

Round 2 will wire these into engine/release_forecast.py dispatch and
scripts/build_release_forecast.py. This file is NEW-ONLY; it does NOT edit shared files.
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
# Re-use champion constants and PIT machinery
# ---------------------------------------------------------------------------
from engine.release_forecast import (  # noqa: E402
    RIDGE_LAMBDA,
    MIN_TRAIN_OBS,
    MIN_QUANTILE_OBS,
    INLINE_BAND_SIGMA,
    COVID_MONTHS,
    load_vintages,
    knowable_series,
    compute_inputs_hash,
    _walk_forward,
    _compute_quantiles,
    _ridge_predict,
    _build_matrix,
    _wilson,
    _last_n_rate_lags,
)
from engine.release_components_cpi import (  # noqa: E402
    _apply_range_guard,
    _FEATURE_BOUNDS,
)

# ---------------------------------------------------------------------------
# Internal helpers: MoM lags from ALFRED vintages (PIT-safe)
# ---------------------------------------------------------------------------

def _last_n_mom_lags(
    vintages: pd.DataFrame,
    series: str,
    asof: date,
    n: int = 3,
) -> list[float | None]:
    """Return the last n MoM % changes (lag1=most recent) from PIT-filtered initial prints."""
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


def _gasoline_mom(
    root: Path,
    ref_month: date | pd.Timestamp,
    asof: date,
) -> float | None:
    """Reference-month average vs prior-month average MoM for gasoline (GASREGW).

    Replicates the champion implementation in engine/release_components_cpi.py.
    PIT: only weeks with index < asof are knowable (weekly data, not revised).
    ref_month: the target print's reference month (first of month).
    """
    gasregw_path = root / "data" / "fred" / "GASREGW.parquet"
    if not gasregw_path.exists():
        return None
    try:
        gasregw = pd.read_parquet(gasregw_path)
        gasregw.index = pd.to_datetime(gasregw.index)
        asof_ts = pd.Timestamp(asof)
        ref_start = pd.Timestamp(ref_month).to_period("M").to_timestamp()
        ref_end = ref_start + pd.offsets.MonthBegin(1)
        prior_start = ref_start - pd.offsets.MonthBegin(1)
        col = gasregw.columns[0]
        cur_hi = min(ref_end, asof_ts)
        cur_m_mask = (gasregw.index >= ref_start) & (gasregw.index < cur_hi)
        prior_m_mask = (gasregw.index >= prior_start) & (gasregw.index < ref_start)
        cur_avg = gasregw.loc[cur_m_mask, col].mean() if cur_m_mask.any() else np.nan
        prior_avg = gasregw.loc[prior_m_mask, col].mean() if prior_m_mask.any() else np.nan
        if np.isfinite(cur_avg) and np.isfinite(prior_avg) and prior_avg != 0:
            return float((cur_avg / prior_avg - 1) * 100)
        return None
    except Exception as e:
        log.debug("GASREGW read failed: %s", e)
        return None


def _sticky_median_flex_lags_alfred(
    vintages: pd.DataFrame,
    asof: date,
) -> dict[str, float | None]:
    """Read sticky/median/flex CPI MoM lag-1 from ALFRED vintage initial prints (PIT-safe).

    Uses the same `_last_n_mom_lags` / `knowable_series` path as the CPI champion
    (engine/release_components_cpi.py build_cpi_features).  STICKCPIM157SFRBATL,
    MEDCPIM158SFRBCLE, and FLEXCPIM157SFRBATL are present in vintages.parquet from
    2014-02 onward; prior steps return None (same as the old FRED-parquet path).

    PIT fix (Opus review): prior implementation read the latest-revised FRED parquets
    instead of ALFRED first-prints, leaking mild revisions into the walk-forward
    features for steps after 2014-02.
    """
    # Use _last_n_rate_lags (not _last_n_mom_lags) — sticky/flex are monthly %;
    # median is ANNUALIZED monthly % and must be de-annualized.
    sticky_lags = _last_n_rate_lags(vintages, "STICKCPIM157SFRBATL", asof, n=1, annualized=False)
    median_lags = _last_n_rate_lags(vintages, "MEDCPIM158SFRBCLE", asof, n=1, annualized=True)
    flex_lags = _last_n_rate_lags(vintages, "FLEXCPIM157SFRBATL", asof, n=1, annualized=False)
    return {
        "sticky_mom_lag1": sticky_lags[0],
        "median_mom_lag1": median_lags[0],
        "flex_mom_lag1": flex_lags[0],
    }


# ---------------------------------------------------------------------------
# Feature builders (one per target)
# ---------------------------------------------------------------------------

def build_pce_headline_features(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | pd.Timestamp | None = None,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for pce_headline prediction at decision date asof.

    Feature panel (frozen per PREREG_NEW_TARGETS_V1.md §2.1):
      pce_hl_mom_lag1  — own MoM lag 1 (PCEPI, ALFRED-vintaged)
      pce_hl_mom_lag2  — own MoM lag 2
      pce_hl_mom_lag3  — own MoM lag 3
      sticky_mom_lag1  — Sticky CPI MoM lag 1 (ALFRED-vintaged, first-print)
      median_mom_lag1  — Median CPI MoM lag 1 (ALFRED-vintaged, first-print)
      flex_mom_lag1    — Flexible CPI MoM lag 1 (ALFRED-vintaged, first-print)
      ppifis_mom_lag1  — PPI Final Demand MoM lag 1 (PPIFIS, ALFRED-vintaged)
      gasoline_mom     — Gasoline ref-month MoM (GASREGW, unrevised)

    PIT fix (Opus review 2026-07-08): sticky/median/flex now sourced from ALFRED
    vintage initial prints via knowable_series (same path as CPI champion), NOT
    from latest-revised FRED parquets.

    Returns (features_dict, provenance_dict).
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
        "vintaged_legs": ["sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1"],
        "unrevised_legs": ["gasoline_mom"],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
        "pit_note": (
            "sticky/median/flex sourced from ALFRED first-prints via knowable_series "
            "(same path as CPI champion); series available from 2014-02 in vintages.parquet."
        ),
    }

    # Own lags — PCEPI, ALFRED-vintaged, PIT-safe
    own_lags = _last_n_mom_lags(vintages, "PCEPI", asof, n=3)
    features: dict[str, float | None] = {
        "pce_hl_mom_lag1": own_lags[0],
        "pce_hl_mom_lag2": own_lags[1],
        "pce_hl_mom_lag3": own_lags[2],
    }

    # Sticky / median / flex CPI — ALFRED-vintaged, first-print (PIT fix)
    smf = _sticky_median_flex_lags_alfred(vintages, asof)
    features.update(smf)
    for k, v in smf.items():
        if v is None:
            absent_legs.append(k)

    # PPIFIS momentum lag 1 — ALFRED-vintaged
    ppifis_lags = _last_n_mom_lags(vintages, "PPIFIS", asof, n=1)
    features["ppifis_mom_lag1"] = ppifis_lags[0]
    if ppifis_lags[0] is None:
        absent_legs.append("ppifis_mom_lag1")

    # Gasoline MoM — unrevised
    if ref_month is None:
        own_prints = knowable_series(vintages, "PCEPI", asof)
        if not own_prints.empty:
            ref_month = (
                pd.Timestamp(own_prints["period"].iloc[-1]).to_period("M") + 1
            ).to_timestamp().date()
    gas = _gasoline_mom(root, ref_month, asof) if ref_month is not None else None
    features["gasoline_mom"] = gas
    if gas is None:
        absent_legs.append("gasoline_mom")

    prov["absent_legs"] = absent_legs

    # FIX 2: apply plausibility-bound range guard (post-computation fence)
    features = _apply_range_guard(features, prov)

    return features, prov


def build_pce_core_features(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | pd.Timestamp | None = None,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for pce_core prediction at decision date asof.

    Feature panel (frozen per PREREG_NEW_TARGETS_V1.md §2.2):
      pce_core_mom_lag1 — own MoM lag 1 (PCEPILFE, ALFRED-vintaged)
      pce_core_mom_lag2 — own MoM lag 2
      pce_core_mom_lag3 — own MoM lag 3
      sticky_mom_lag1   — Sticky CPI MoM lag 1 (ALFRED-vintaged, first-print)
      median_mom_lag1   — Median CPI MoM lag 1 (ALFRED-vintaged, first-print)
      flex_mom_lag1     — Flexible CPI MoM lag 1 (ALFRED-vintaged, first-print)
      ppifes_mom_lag1   — PPI ex Food & Energy MoM lag 1 (PPIFES, ALFRED-vintaged)

    PIT fix (Opus review 2026-07-08): sticky/median/flex now sourced from ALFRED
    vintage initial prints via knowable_series (same path as CPI champion), NOT
    from latest-revised FRED parquets.

    Returns (features_dict, provenance_dict).
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
        "vintaged_legs": ["sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1"],
        "unrevised_legs": [],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
        "pit_note": (
            "sticky/median/flex sourced from ALFRED first-prints via knowable_series "
            "(same path as CPI champion); series available from 2014-02 in vintages.parquet."
        ),
    }

    # Own lags — PCEPILFE, ALFRED-vintaged, PIT-safe
    own_lags = _last_n_mom_lags(vintages, "PCEPILFE", asof, n=3)
    features: dict[str, float | None] = {
        "pce_core_mom_lag1": own_lags[0],
        "pce_core_mom_lag2": own_lags[1],
        "pce_core_mom_lag3": own_lags[2],
    }

    # Sticky / median / flex CPI — ALFRED-vintaged, first-print (PIT fix)
    smf = _sticky_median_flex_lags_alfred(vintages, asof)
    features.update(smf)
    for k, v in smf.items():
        if v is None:
            absent_legs.append(k)

    # PPIFES momentum lag 1 — ALFRED-vintaged
    ppifes_lags = _last_n_mom_lags(vintages, "PPIFES", asof, n=1)
    features["ppifes_mom_lag1"] = ppifes_lags[0]
    if ppifes_lags[0] is None:
        absent_legs.append("ppifes_mom_lag1")

    prov["absent_legs"] = absent_legs

    # FIX 2: apply plausibility-bound range guard (post-computation fence)
    features = _apply_range_guard(features, prov)

    return features, prov


def build_ppi_finaldemand_features(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | pd.Timestamp | None = None,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for ppi_finaldemand prediction at decision date asof.

    Feature panel (frozen per PREREG_NEW_TARGETS_V1.md §2.3):
      ppi_hl_mom_lag1  — own MoM lag 1 (PPIFIS, ALFRED-vintaged)
      ppi_hl_mom_lag2  — own MoM lag 2
      ppi_hl_mom_lag3  — own MoM lag 3
      gasoline_mom     — Gasoline ref-month MoM (GASREGW, unrevised)
      ppifes_mom_lag1  — PPI ex Food & Energy MoM lag 1 (PPIFES, ALFRED-vintaged)

    THIN-HISTORY CAVEAT: PPIFIS vintages start 2014-02; first prediction ~2019-02.
    Returns (features_dict, provenance_dict).
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
        "unrevised_legs": ["gasoline_mom"],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
        "thin_history_caveat": (
            "PPIFIS vintage history starts 2014-02; first walk-forward prediction ~2019-02; "
            "approximately 90 total and 50-60 2021+ predictions — statistics are informative "
            "but thin-history confidence is reduced."
        ),
    }

    # Own lags — PPIFIS, ALFRED-vintaged, PIT-safe
    own_lags = _last_n_mom_lags(vintages, "PPIFIS", asof, n=3)
    features: dict[str, float | None] = {
        "ppi_hl_mom_lag1": own_lags[0],
        "ppi_hl_mom_lag2": own_lags[1],
        "ppi_hl_mom_lag3": own_lags[2],
    }

    # Gasoline MoM — unrevised
    if ref_month is None:
        own_prints = knowable_series(vintages, "PPIFIS", asof)
        if not own_prints.empty:
            ref_month = (
                pd.Timestamp(own_prints["period"].iloc[-1]).to_period("M") + 1
            ).to_timestamp().date()
    gas = _gasoline_mom(root, ref_month, asof) if ref_month is not None else None
    features["gasoline_mom"] = gas
    if gas is None:
        absent_legs.append("gasoline_mom")

    # PPIFES momentum lag 1 — ALFRED-vintaged
    ppifes_lags = _last_n_mom_lags(vintages, "PPIFES", asof, n=1)
    features["ppifes_mom_lag1"] = ppifes_lags[0]
    if ppifes_lags[0] is None:
        absent_legs.append("ppifes_mom_lag1")

    prov["absent_legs"] = absent_legs

    # FIX 2: apply plausibility-bound range guard (post-computation fence)
    features = _apply_range_guard(features, prov)

    return features, prov


def build_retail_sales_features(
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | pd.Timestamp | None = None,
) -> tuple[dict[str, float | None], dict]:
    """Scaffold-only feature builder for retail_sales.

    RSAFS is absent from disk as of 2026-07-08. Returns empty features + no_data provenance.
    The attempt clock (#1 of 2) does NOT start until RSAFS parquet and release calendar
    entries are on disk (per MRI-R23 / PREREG_NEW_TARGETS_V1.md §1.9).
    """
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
        "unrevised_legs": [],
        "absent_legs": ["rsafs_own_lags", "gasoline_mom", "claims_momentum"],
        "display_only": True,
        "authority": False,
        "reason": "no_data_rsafs_absent",
        "note": (
            "RSAFS data not yet on disk. Attempt clock (#1 of 2) has not started. "
            "Machinery ships so projection emits benchmark_only/no_data until series accrues."
        ),
    }
    # Empty feature dict — no model can run
    features: dict[str, float | None] = {}
    return features, prov


# ---------------------------------------------------------------------------
# Empty projection helper (mirrors champion pattern)
# ---------------------------------------------------------------------------

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
        "surprise_skew": {
            "sigma": None,
            "sigma_scale_pp": None,
            "tag": None,
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


# ---------------------------------------------------------------------------
# Target-side seam guard (mirror of the feature-side range guard)
# ---------------------------------------------------------------------------

#: MoM plausibility fence for the TARGET side, per own-series. Sourced from the
#: same _FEATURE_BOUNDS constants as the feature-side guard so both sides agree
#: on what counts as a plausible first print. Series without an entry (e.g.
#: RSAFS, whose real COVID prints reached ±17%) pass through unguarded.
_TARGET_MOM_BOUNDS: dict[str, tuple[float, float]] = {
    "PCEPI": _FEATURE_BOUNDS["pce_hl_mom_lag1"],
    "PCEPILFE": _FEATURE_BOUNDS["pce_core_mom_lag1"],
    "PPIFIS": _FEATURE_BOUNDS["ppi_hl_mom_lag1"],
}


def _null_seam_mom_targets(mom_series: pd.DataFrame, own_series: str) -> pd.DataFrame:
    """Null MoM values outside the plausibility fence (NIPA re-base seams).

    At a comprehensive-revision vintage the first print of period P is on a new
    index base while P-1's first print is on the old base, so pct_change across
    the seam is a re-base artifact (PCEPI/PCEPILFE print -4.4..-10.1 at periods
    2003-11 / 2009-06 / 2013-06 / 2018-06 / 2023-08), not inflation — the real
    worst PCE MoM is -1.146 (2008-11). The feature side is already fenced by
    _apply_range_guard; this nulls the TARGET side so seam rows drop out of
    training, prediction steps, and walk-forward baselines (all of which skip
    null targets in _walk_forward).

    Returns a copy with out-of-fence "mom" set to NaN; rows are kept so period
    alignment (ref_month derivation, record indexing) is unchanged.
    """
    bounds = _TARGET_MOM_BOUNDS.get(own_series)
    if bounds is None:
        return mom_series
    lo, hi = bounds
    mask = mom_series["mom"].notna() & ~mom_series["mom"].between(lo, hi)
    if not mask.any():
        return mom_series
    seam_periods = [str(pd.Timestamp(p).date()) for p in mom_series.loc[mask, "period"]]
    log.warning(
        "Target seam guard (%s): nulled %d MoM target(s) outside [%.1f, %.1f] "
        "at periods %s (index re-base artifacts, not real prints).",
        own_series, int(mask.sum()), lo, hi, seam_periods,
    )
    out = mom_series.copy()
    out.loc[mask, "mom"] = np.nan
    return out


# ---------------------------------------------------------------------------
# Walk-forward data assembly (per-target)
# ---------------------------------------------------------------------------

def _build_wf_records(
    vintages: pd.DataFrame,
    root: Path,
    own_series: str,
    feature_builder,
) -> list[dict]:
    """Build the list of walk-forward records for a monthly MoM target.

    For each initial ALFRED print of own_series, compute features at step_asof
    (day before that print's realtime_start). Target = MoM % change of that print.
    NIPA re-base seam steps carry target=None (_null_seam_mom_targets); _walk_forward
    excludes them from training rows, prediction steps, and baselines.

    Returns list of dicts suitable for _walk_forward.
    """
    all_series = knowable_series(vintages, own_series, date(2099, 1, 1))
    if len(all_series) < 2:
        return []
    mom_series = all_series.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)
    mom_series = _null_seam_mom_targets(mom_series, own_series)

    records = []
    for _, row in mom_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month_step = row["period"].date() if hasattr(row["period"], "date") else date(
            pd.Timestamp(row["period"]).year, pd.Timestamp(row["period"]).month, 1
        )
        try:
            feats, _ = feature_builder(step_asof, vintages, root, ref_month=ref_month_step)
        except Exception as e:
            log.debug("Feature build failed at %s: %s", step_asof, e)
            feats = {}
        rec = dict(feats)
        rec["target"] = float(row["mom"]) if pd.notna(row["mom"]) else None
        rec["period"] = row["period"]
        rec["release_date"] = row["realtime_start"]
        rec["asof"] = step_asof
        records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Internal projection functions
# ---------------------------------------------------------------------------

def _project_target(
    release: str,
    own_series: str,
    feature_names: list[str],
    feature_builder,
    asof: date,
    vintages: pd.DataFrame,
    root: Path,
    ref_month: date | None,
    prov_extra: dict | None = None,
) -> dict:
    """Generic projection runner for a monthly MoM target.

    Replicates the champion _project_cpi pattern: build records, walk-forward for
    residual history, predict on current features, assemble output dict.
    """
    all_series = knowable_series(vintages, own_series, asof)
    if len(all_series) < 2:
        return _empty_projection(release, asof, "insufficient_data")

    mom_series = all_series.copy()
    mom_series["mom"] = mom_series["value"].pct_change() * 100.0
    mom_series = mom_series.dropna(subset=["mom"]).reset_index(drop=True)
    mom_series = _null_seam_mom_targets(mom_series, own_series)

    # Build records for walk-forward residual history
    records = []
    for _, row in mom_series.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month_step = row["period"].date() if hasattr(row["period"], "date") else date(
            pd.Timestamp(row["period"]).year, pd.Timestamp(row["period"]).month, 1
        )
        try:
            feats, _ = feature_builder(step_asof, vintages, root, ref_month=ref_month_step)
        except Exception as e:
            log.debug("Feature build failed at %s: %s", step_asof, e)
            feats = {}
        rec = dict(feats)
        rec["target"] = float(row["mom"]) if pd.notna(row["mom"]) else None
        records.append(rec)

    if len(records) < MIN_TRAIN_OBS + 1:
        return _empty_projection(release, asof, "insufficient_history")

    wf_results = _walk_forward(records, feature_names, "target")
    if not wf_results:
        return _empty_projection(release, asof, "no_walk_forward_results")

    # Derive ref_month if not supplied
    if ref_month is None:
        ref_month = (
            (pd.Timestamp(mom_series["period"].iloc[-1]).to_period("M") + 1)
            .to_timestamp()
            .date()
        )

    # Build current features
    feats, prov = feature_builder(asof, vintages, root, ref_month=ref_month)
    if prov_extra:
        prov.update(prov_extra)

    # Compute current prediction
    train_recs = records
    X_all = _build_matrix(train_recs, feature_names)
    y_all = np.array([r.get("target", np.nan) for r in train_recs], dtype=float)
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

    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])
    quantiles = _compute_quantiles(errors, point if point is not None else 0.0)

    # Confidence
    confidence, interval_rank = None, None
    if point is not None and len(errors) >= MIN_QUANTILE_OBS:
        cur_width = (point + np.quantile(errors, 0.90)) - (point + np.quantile(errors, 0.10))
        hist_widths = []
        for k in range(MIN_QUANTILE_OBS, len(wf_results) + 1):
            e_sub = errors[:k]
            w = np.quantile(e_sub, 0.90) - np.quantile(e_sub, 0.10)
            hist_widths.append(w)
        if hist_widths:
            pctile = float(np.mean(np.array(hist_widths) <= cur_width))
            interval_rank = round(1.0 - pctile, 4)
            confidence = round(interval_rank * input_completeness, 4)

    # Baselines — computed on seam-guarded moms so naive_prior/trailing_3m never
    # carry a re-base artifact (e.g. asof the day after a comprehensive-revision
    # print, naive falls back to the last real MoM instead of -10.1).
    mom_valid = mom_series["mom"].dropna()
    naive = float(mom_valid.iloc[-1]) if len(mom_valid) > 0 else None
    trailing_3m = (
        float(mom_valid.iloc[-3:].mean()) if len(mom_valid) >= 3 else naive
    )

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
        # input_manifest: feature values used for this projection (MRI-R26 honesty, rework-2a).
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
        "components": None,        # Track N: no block decomposition in attempt #1
        "confidence_v2": None,
        "confidence_components_v2": None,
        "input_completeness": round(input_completeness, 4),
        "benchmark_set": {
            "naive_prior": round(naive, 4) if naive is not None else None,
            "trailing_3m": round(trailing_3m, 4) if trailing_3m is not None else None,
            "ar_model": None,      # AR3 available in backtest; omitted from live projection for simplicity
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


# ---------------------------------------------------------------------------
# Public projection API (one function per target)
# ---------------------------------------------------------------------------

#: Feature names for pce_headline (ordered; own lags first per walk-forward contract)
PCE_HEADLINE_FEATURE_NAMES: list[str] = [
    "pce_hl_mom_lag1", "pce_hl_mom_lag2", "pce_hl_mom_lag3",
    "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
    "ppifis_mom_lag1", "gasoline_mom",
]

#: Feature names for pce_core
PCE_CORE_FEATURE_NAMES: list[str] = [
    "pce_core_mom_lag1", "pce_core_mom_lag2", "pce_core_mom_lag3",
    "sticky_mom_lag1", "median_mom_lag1", "flex_mom_lag1",
    "ppifes_mom_lag1",
]

#: Feature names for ppi_finaldemand
PPI_FINALDEMAND_FEATURE_NAMES: list[str] = [
    "ppi_hl_mom_lag1", "ppi_hl_mom_lag2", "ppi_hl_mom_lag3",
    "gasoline_mom", "ppifes_mom_lag1",
]


def project_pce_headline(
    asof: date,
    root: str | Path,
    ref_month: date | None = None,
) -> dict:
    """Generate a point-in-time projection for PCE headline (PCEPI MoM SA).

    Parameters
    ----------
    asof : date
        Decision date (day before the target release is published).
    root : str | Path
        Repository root.
    ref_month : date | None
        Reference month the upcoming print covers. None derives it from last knowable print.

    Returns
    -------
    dict matching the release_forecast.v2 projection block schema.
    display_only=True, authority=False.
    """
    root = Path(root)
    vintages = load_vintages(root)
    return _project_target(
        release="pce_headline",
        own_series="PCEPI",
        feature_names=PCE_HEADLINE_FEATURE_NAMES,
        feature_builder=build_pce_headline_features,
        asof=asof,
        vintages=vintages,
        root=root,
        ref_month=ref_month,
    )


def project_pce_core(
    asof: date,
    root: str | Path,
    ref_month: date | None = None,
) -> dict:
    """Generate a point-in-time projection for PCE core (PCEPILFE MoM SA).

    Parameters
    ----------
    asof : date
        Decision date.
    root : str | Path
        Repository root.
    ref_month : date | None
        Reference month. None derives it from last knowable print.

    Returns
    -------
    dict matching the release_forecast.v2 projection block schema.
    display_only=True, authority=False.
    """
    root = Path(root)
    vintages = load_vintages(root)
    return _project_target(
        release="pce_core",
        own_series="PCEPILFE",
        feature_names=PCE_CORE_FEATURE_NAMES,
        feature_builder=build_pce_core_features,
        asof=asof,
        vintages=vintages,
        root=root,
        ref_month=ref_month,
    )


def project_ppi_finaldemand(
    asof: date,
    root: str | Path,
    ref_month: date | None = None,
) -> dict:
    """Generate a point-in-time projection for PPI final demand (PPIFIS MoM SA).

    THIN-HISTORY CAVEAT: PPIFIS vintage history starts 2014-02; first walk-forward
    prediction approximately 2019-02. Statistics are informative but thin-history
    confidence is reduced. See PREREG_NEW_TARGETS_V1.md §1.3 and §2.3.

    Parameters
    ----------
    asof : date
        Decision date.
    root : str | Path
        Repository root.
    ref_month : date | None
        Reference month. None derives it from last knowable print.

    Returns
    -------
    dict matching the release_forecast.v2 projection block schema.
    display_only=True, authority=False.
    """
    root = Path(root)
    vintages = load_vintages(root)
    return _project_target(
        release="ppi_finaldemand",
        own_series="PPIFIS",
        feature_names=PPI_FINALDEMAND_FEATURE_NAMES,
        feature_builder=build_ppi_finaldemand_features,
        asof=asof,
        vintages=vintages,
        root=root,
        ref_month=ref_month,
        prov_extra={
            "thin_history_caveat": (
                "PPIFIS vintage history starts 2014-02; first walk-forward prediction "
                "approximately 2019-02. Statistics are informative but thin."
            )
        },
    )


def project_retail_sales(
    asof: date,
    root: str | Path,
    ref_month: date | None = None,
) -> dict:
    """Scaffold-only projection for retail sales (RSAFS MoM SA).

    RSAFS data is absent from disk as of 2026-07-08. Returns a no_data projection.
    The attempt clock (#1 of 2) does NOT start until RSAFS parquet and release calendar
    entries are on disk (per MRI-R23 / PREREG_NEW_TARGETS_V1.md §1.9 and §2.4).

    Returns
    -------
    dict with all null fields and pit_provenance.reason = "no_data_rsafs_absent".
    display_only=True, authority=False.
    """
    result = _empty_projection("retail_sales", asof, "no_data_rsafs_absent")
    result["pit_provenance"]["note"] = (
        "RSAFS data not yet on disk. Attempt clock (#1 of 2) has not started. "
        "Machinery ships so projection emits benchmark_only/no_data until series accrues."
    )
    return result


# ---------------------------------------------------------------------------
# Walk-forward full data assembly (used by backtest)
# ---------------------------------------------------------------------------

def build_wf_pce_headline(
    root: str | Path,
) -> dict:
    """Build full walk-forward records and results for pce_headline backtest.

    Returns dict with keys: results, feature_names, metadata.
    """
    root = Path(root)
    vintages = load_vintages(root)
    records = _build_wf_records(vintages, root, "PCEPI", build_pce_headline_features)
    wf_results = _walk_forward(records, PCE_HEADLINE_FEATURE_NAMES, "target")
    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")
    return {
        "results": wf_results,
        "feature_names": PCE_HEADLINE_FEATURE_NAMES,
        "metadata": {"release": "pce_headline", "n_records": len(records)},
    }


def build_wf_pce_core(
    root: str | Path,
) -> dict:
    """Build full walk-forward records and results for pce_core backtest."""
    root = Path(root)
    vintages = load_vintages(root)
    records = _build_wf_records(vintages, root, "PCEPILFE", build_pce_core_features)
    wf_results = _walk_forward(records, PCE_CORE_FEATURE_NAMES, "target")
    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")
    return {
        "results": wf_results,
        "feature_names": PCE_CORE_FEATURE_NAMES,
        "metadata": {"release": "pce_core", "n_records": len(records)},
    }


def build_wf_ppi_finaldemand(
    root: str | Path,
) -> dict:
    """Build full walk-forward records and results for ppi_finaldemand backtest.

    THIN-HISTORY: first prediction approximately 2019-02 after 60-obs burn-in.
    """
    root = Path(root)
    vintages = load_vintages(root)
    records = _build_wf_records(vintages, root, "PPIFIS", build_ppi_finaldemand_features)
    wf_results = _walk_forward(records, PPI_FINALDEMAND_FEATURE_NAMES, "target")
    for r in wf_results:
        meta_rec = records[r["idx"]]
        r["period"] = meta_rec.get("period")
        r["release_date"] = meta_rec.get("release_date")
    return {
        "results": wf_results,
        "feature_names": PPI_FINALDEMAND_FEATURE_NAMES,
        "metadata": {
            "release": "ppi_finaldemand",
            "n_records": len(records),
            "thin_history": True,
            "thin_history_caveat": (
                "PPIFIS vintage history starts 2014-02; first walk-forward prediction "
                "approximately 2019-02; expect ~90 total and ~50-60 2021+ predictions."
            ),
        },
    }
