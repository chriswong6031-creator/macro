"""MRI — NFP and Claims feature builders (split from engine/release_forecast.py for PR-H parallel work).

LEAF · DISPLAY-ONLY. Pure numpy/pandas only.

All public functions here were previously defined inline in engine/release_forecast.py.
engine/release_forecast.py imports from this module — callers that import from
engine.release_forecast see no change.

Also contains: claims_walk_forward_residuals — the expanding walk-forward residual
series for the claims naive model (IC4WSA → ICSA), used to build quantile bands
for the claims projection.

PR-H additions (PREREG_NFP_DECOMP_V1.md, frozen 2026-07-07):
  - build_nfp_components(): NFP decomposition (private_trend, government_trend,
    birth_death_residual_prior, residual) — display-only, attaches to NFP projection.
  - compute_nfp_revision_risk(): revision-risk field from ALFRED vintages.
  - build_ahe_features(): feature builder for AHE MoM % target (CES0500000003).
  - project_ahe(): ridge projection for AHE MoM %.
  - project_awh(): persistence-only projection for avg weekly hours level.

SPECIFICATION: research/release_forecast/PREREG_V1.md (frozen 2026-07-07).
              research/release_forecast/PREREG_NFP_DECOMP_V1.md (PR-H; frozen 2026-07-07).
Anti-mining: one spec per release type, frozen before any results were observed.

PIT LAW: feature values are usable at decision date D only if their ALFRED
realtime_start <= D.

Claims target: ICSA level for the upcoming Thursday print.
Model: point = last IC4WSA (4-week MA initial print), quantiles from expanding
walk-forward residuals of that rule on the vintages (ICSA vintages 2009→).
Naive = last ICSA initial print. regime_axis = "growth".
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def build_nfp_features(
    asof: date,
    ref_month: date,
    vintages: pd.DataFrame,
    root: Path,
    *,
    # injected to avoid circular import
    knowable_series_fn,
    survey_week_claims_fn,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for NFP prediction at decision date asof for ref_month.

    knowable_series_fn / survey_week_claims_fn: injected from engine.release_forecast.
    Returns (features_dict, provenance_dict).
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        # adp_change: revision_optimistic (ADP does revise its estimates; we lack ALFRED vintages
        # → asof-blind read, same limitation as awhman_mom; acceptable for Track-M challenger).
        "revision_optimistic_legs": ["awhman_mom", "adp_change"],
        # vintaged_legs: ALFRED first-print legs actually used — PAYEMS own lags + survey-week
        # claims. Enumerated here so compute_coverage_flags sees the full declared-leg set
        # (MRI-R26 honesty, rework-2a fix). Claims (ICSA/CCSA) are ALFRED-vintaged weekly.
        "vintaged_legs": [
            "nfp_change_lag1", "nfp_change_lag2", "nfp_change_lag3",
            "claims_survey_week_icsa", "claims_survey_week_ccsa",
        ],
        "unrevised_legs": ["withheld_tax_yoy"],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
        "withheld_tax_start": "2023-02-14",
    }

    # PAYEMS own lags (3 MoM differences in thousands)
    diff_series = knowable_series_fn(vintages, "PAYEMS", asof)
    if len(diff_series) >= 2:
        levels = diff_series.set_index("period")["value"]
        diffs = levels.diff().dropna()
        own_lags = []
        for i in range(1, 4):
            own_lags.append(float(diffs.iloc[-i]) if len(diffs) >= i else None)
    else:
        own_lags = [None, None, None]

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

    icsa_cur = survey_week_claims_fn(vintages, "ICSA", asof, ref_month)
    icsa_prior = survey_week_claims_fn(vintages, "ICSA", asof, prior_month)
    if icsa_cur is not None and icsa_prior is not None:
        features["claims_survey_week_icsa"] = float(icsa_cur - icsa_prior)
    else:
        features["claims_survey_week_icsa"] = None
        absent_legs.append("claims_survey_week_icsa")

    # Claims: CCSA survey-week delta
    ccsa_cur = survey_week_claims_fn(vintages, "CCSA", asof, ref_month)
    ccsa_prior = survey_week_claims_fn(vintages, "CCSA", asof, prior_month)
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
            awhman_monthly = awhman[awhman_col].resample("MS").last()
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

    # ADP contemporaneous same-month change in thousands (revision_optimistic; no ALFRED vintage).
    # Series: ADPMNUSNERSA (ADP Total Nonfarm Private Payroll Employment, SA level in PERSONS,
    # ~132,000,000). Seasonality check (pre-COVID + post-recovery, 2000-2022): calendar-month
    # spread = 120k (thousands), confirming SA (a truly NSA payroll series would swing millions).
    # Alternative SA series ADPNFRPRIVSA returns HTTP 404 on FRED; NPPTTL ends 2022-05 and also
    # shows seasonal distortions from COVID. ADPMNUSNERSA is kept as best available SA proxy.
    # Definition (PREREG_V1 §4.3 "same-month"): contemporaneous adp_change = level[M] - level[M-1].
    # ADP-M releases ~2 days before BLS NFP-M → knowable at the decision date for target month M.
    # Level diff in persons → divide by 1000 for thousands (matches nfp_change_lag* scale).
    # Revision status: revision_optimistic (ADP does revise; we lack ALFRED vintages → asof-blind).
    # This feature is computed-but-unused by the champion (Track-M challenger will select it later).
    # Fail-open if absent.
    adp_path = root / "data" / "fred" / "ADPMNUSNERSA.parquet"
    if adp_path.exists():
        try:
            adp = pd.read_parquet(adp_path)
            adp.index = pd.to_datetime(adp.index)
            adp_col = adp.columns[0]
            adp_monthly = adp[adp_col].resample("MS").last()
            ref_m = pd.Timestamp(ref_month)
            # Contemporaneous: same-month level[M] - level[M-1] (ADP-M knowable at NFP-M date)
            m_0 = ref_m.to_period("M").to_timestamp()
            m_minus_1 = (ref_m.to_period("M") - 1).to_timestamp()
            v0 = adp_monthly.get(m_0)
            v1 = adp_monthly.get(m_minus_1)
            if (v0 is not None and v1 is not None
                    and not np.isnan(float(v0)) and not np.isnan(float(v1))):
                # level diff in persons → divide by 1000 for thousands (matches nfp_change scale)
                features["adp_change"] = float(v0 - v1) / 1000.0
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
# Claims target — weekly ICSA level projection
# ---------------------------------------------------------------------------

def project_claims(
    asof: date,
    vintages: pd.DataFrame,
    *,
    knowable_series_fn,
    min_quantile_obs: int = 24,
) -> dict:
    """Project the upcoming Thursday ICSA print.

    Model (frozen trivial spec):
      point     = last IC4WSA (4-week MA initial print) knowable at asof
      naive     = last ICSA initial print knowable at asof
      quantiles = expanding walk-forward residuals of (IC4WSA → ICSA) rule

    Returns a projection dict with the same key shape as project_release outputs,
    plus claims-specific fields:
      - release: "claims"
      - target: "icsa_level"
      - regime_axis: "growth"
      - point, p10, p25, p50, p75, p90 (level, thousands)
      - naive_prior: last ICSA initial print
      - inputs_used: {"ic4wsa_last": ..., "icsa_last": ...}
    """
    # All initial ICSA prints knowable at asof
    icsa = knowable_series_fn(vintages, "ICSA", asof)
    ic4wsa = knowable_series_fn(vintages, "IC4WSA", asof)

    if icsa.empty or ic4wsa.empty:
        return _empty_claims_projection(asof, "insufficient_data")

    icsa_last = float(icsa["value"].iloc[-1])
    ic4wsa_last = float(ic4wsa["value"].iloc[-1])

    # Walk-forward residuals: for each ICSA observation where we also have an
    # IC4WSA prediction (the IC4WSA published one week earlier than the
    # corresponding ICSA), compute residual = ICSA_actual - IC4WSA_pred.
    # We use a time-aligned merge: for ICSA period T, use the IC4WSA reading
    # with the latest realtime_start <= ICSA's realtime_start - 1 day.
    icsa_sorted = icsa.sort_values("period").reset_index(drop=True)
    ic4wsa_sorted = ic4wsa.sort_values("period").reset_index(drop=True)

    residuals: list[float] = []
    for _, icsa_row in icsa_sorted.iterrows():
        icsa_rt = icsa_row["realtime_start"]
        icsa_period = icsa_row["period"]
        icsa_val = float(icsa_row["value"])

        # IC4WSA with same or prior period, published strictly before this ICSA print
        ic4_avail = ic4wsa_sorted[
            (ic4wsa_sorted["period"] <= icsa_period) &
            (ic4wsa_sorted["realtime_start"] < icsa_rt)
        ]
        if ic4_avail.empty:
            continue
        # Most recent IC4WSA reading
        ic4_pred = float(ic4_avail.iloc[-1]["value"])
        # Residuals in thousands (matching benchmark units)
        residuals.append((icsa_val - ic4_pred) / 1000.0)

    residuals_arr = np.array(residuals, dtype=float)

    # Quantiles: p10/p25/p50/p75/p90 from expanding residuals (all in thousands)
    point = ic4wsa_last / 1000.0  # convert raw persons → thousands to match benchmark_set units
    if len(residuals_arr) >= min_quantile_obs:
        qs = np.quantile(residuals_arr, [0.10, 0.25, 0.50, 0.75, 0.90])
        quantiles = {
            "p10": round(point + qs[0], 3),
            "p25": round(point + qs[1], 3),
            "p50": round(point + qs[2], 3),
            "p75": round(point + qs[3], 3),
            "p90": round(point + qs[4], 3),
        }
    else:
        quantiles = {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    # trailing_4w: mean of last 4 ICSA initial prints (raw level / 1000 for thousands)
    icsa_levels_k = icsa_sorted["value"].values / 1000.0
    if len(icsa_levels_k) >= 4:
        trailing_4w: float | None = round(float(np.mean(icsa_levels_k[-4:])), 2)
    elif len(icsa_levels_k) >= 1:
        trailing_4w = round(float(np.mean(icsa_levels_k)), 2)
    else:
        trailing_4w = None

    # ar_model: AR3 Ridge on ICSA levels in thousands
    ar3_pred: float | None = None
    if len(icsa_levels_k) >= 4:
        y_ar = icsa_levels_k
        X_ar3 = np.full((len(y_ar), 3), np.nan)
        for i in range(3, len(y_ar)):
            for lag in range(1, 4):
                X_ar3[i, lag - 1] = y_ar[i - lag]
        row_ok = ~np.any(np.isnan(X_ar3), axis=1)
        if row_ok.sum() >= 4:
            X_clean_ar = X_ar3[row_ok]
            y_clean_ar = y_ar[row_ok]
            x_pred_ar = np.array([y_ar[-i] for i in range(1, 4)], dtype=float)
            try:
                # Ridge AR3: (X'X + lI)^{-1} X'y
                lam = 1.0
                A = X_clean_ar.T @ X_clean_ar + lam * np.eye(3)
                b = X_clean_ar.T @ y_clean_ar
                coef = np.linalg.solve(A, b)
                pred_raw = float(x_pred_ar @ coef)
                ar3_pred = round(pred_raw, 2) if np.isfinite(pred_raw) else None
            except Exception:
                ar3_pred = None

    return {
        "release": "claims",
        "asof": asof.isoformat(),
        "target": "icsa_level",
        "regime_axis": "growth",
        "point": round(point, 3),  # thousands (ic4wsa_last / 1000.0)
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "n_residuals": len(residuals_arr),
        "benchmark_set": {
            "naive_prior": round(icsa_last / 1000.0, 3),  # thousands
            "trailing_4w": trailing_4w,                    # already in thousands
            "ar_model": ar3_pred,                          # already in thousands
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "inputs_used": {
            "ic4wsa_last_raw": round(ic4wsa_last, 1),  # raw persons (informational)
            "icsa_last_raw": round(icsa_last, 1),       # raw persons (informational)
        },
        "surprise_skew": {"sigma": None, "tag": None},
        "pit_provenance": {
            "revision_optimistic_legs": [],
            "unrevised_legs": [],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
            "note": "frozen trivial spec: IC4WSA point, expanding IC4WSA→ICSA residuals",
        },
        "display_only": True,
        "authority": False,
        "confidence": None,
        "input_completeness": 1.0 if (not icsa.empty and not ic4wsa.empty) else 0.0,
    }


def _empty_claims_projection(asof: date, reason: str) -> dict:
    return {
        "release": "claims",
        "asof": asof.isoformat(),
        "target": "icsa_level",
        "regime_axis": "growth",
        "point": None,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "n_residuals": 0,
        "benchmark_set": {
            "naive_prior": None, "trailing_4w": None,
            "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
        },
        "inputs_used": {},
        "surprise_skew": {"sigma": None, "tag": None},
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
        "confidence": None,
        "input_completeness": 0.0,
    }


# ===========================================================================
# PR-H: NFP Decomposition + Revision Risk + AHE/AWH targets
# SPEC: research/release_forecast/PREREG_NFP_DECOMP_V1.md (frozen 2026-07-07)
# ===========================================================================

def compute_nfp_revision_risk(
    vintages: pd.DataFrame,
    series: str = "PAYEMS",
    trailing_months: int = 24,
) -> dict:
    """Compute NFP revision-risk display field from ALFRED vintages.

    Computes mean and sign-rate of (latest_value - initial_print) over the
    trailing `trailing_months` calendar months of PAYEMS history.

    Returns: {mean_k: float|None, pct_upward: float|None, n_periods: int}
    per PREREG_NFP_DECOMP_V1.md §2.3 (descriptive, no authority).
    """
    sub = vintages[vintages["series"] == series].copy()
    if sub.empty:
        return {"mean_k": None, "pct_upward": None, "n_periods": 0}

    sub["period"] = pd.to_datetime(sub["period"])

    # Initial print for each period: earliest realtime_start
    initial = (
        sub.sort_values("realtime_start")
        .groupby("period", as_index=False)
        .first()[["period", "value"]]
        .rename(columns={"value": "initial"})
    )
    # Latest print for each period: most recent realtime_start
    latest = (
        sub.sort_values("realtime_start")
        .groupby("period", as_index=False)
        .last()[["period", "value"]]
        .rename(columns={"value": "latest"})
    )

    merged = initial.merge(latest, on="period")
    merged = merged.sort_values("period")

    # Trim to trailing_months from the last available period
    if not merged.empty:
        last_period = merged["period"].max()
        cutoff = last_period - pd.DateOffset(months=trailing_months)
        merged = merged[merged["period"] >= cutoff]

    if merged.empty or len(merged) < 3:
        return {"mean_k": None, "pct_upward": None, "n_periods": int(len(merged))}

    revisions = (merged["latest"] - merged["initial"]).values
    mean_k = round(float(np.mean(revisions)), 2)
    pct_upward = round(float(np.mean(revisions > 0)), 4)

    return {
        "mean_k": mean_k,
        "pct_upward": pct_upward,
        "n_periods": len(merged),
    }


def build_nfp_components(
    model_point: float | None,
    asof: date,
    ref_month: date,
    vintages: pd.DataFrame,
    wf_results: list[dict],  # walk-forward result dicts from prior steps
    *,
    knowable_series_fn,
    trailing_share_months: int = 12,
    government_lookback: int = 3,
    birth_death_lookback_years: int = 5,
) -> dict:
    """Build NFP decomposition components per PREREG_NFP_DECOMP_V1.md §2.

    Parameters
    ----------
    model_point : ridge point estimate for total PAYEMS change (thousands)
    asof : decision date
    ref_month : reference month of the upcoming print
    vintages : full ALFRED vintage DataFrame
    wf_results : walk-forward result dicts [{actual, predicted, period, ...}]
                 from ALL prior prediction steps (strictly before this asof);
                 used to compute birth-death residual prior PIT.
    knowable_series_fn : injected from engine.release_forecast
    trailing_share_months : months of history to estimate private share
    government_lookback : months of USGOVT initial-print MoM to average
    birth_death_lookback_years : years of walk-forward history for BD prior

    Returns dict with keys: private_trend, government_trend,
    birth_death_residual_prior, residual, confidence_map, method_notes.
    All None if model_point is None.
    """
    if model_point is None:
        return {
            "private_trend": None,
            "government_trend": None,
            "birth_death_residual_prior": None,
            "residual": None,
            "confidence_map": {},
            "method_notes": {"reason": "model_point_none"},
        }

    method_notes: dict[str, Any] = {}
    absent: list[str] = []

    # --- a. private_trend ---
    # Estimate private share = mean(USPRIV_initial / PAYEMS_initial) over trailing N months
    uspriv = knowable_series_fn(vintages, "USPRIV", asof)
    payems = knowable_series_fn(vintages, "PAYEMS", asof)
    private_trend: float | None = None
    if not uspriv.empty and not payems.empty:
        # Merge on period
        up = uspriv.set_index("period")["value"]
        pe = payems.set_index("period")["value"]
        common = up.index.intersection(pe.index)
        if len(common) >= 3:
            # Use only the trailing N months
            common_sorted = sorted(common)[-trailing_share_months:]
            shares = []
            for p in common_sorted:
                pv = pe[p]
                if pv and pv > 0:
                    shares.append(float(up[p]) / float(pv))
            if shares:
                mean_share = float(np.mean(shares))
                private_trend = round(model_point * mean_share, 2)
                method_notes["private_share"] = round(mean_share, 4)
                method_notes["private_share_n"] = len(shares)
    if private_trend is None:
        absent.append("private_trend")
        private_trend = None

    # --- b. government_trend ---
    usgovt = knowable_series_fn(vintages, "USGOVT", asof)
    government_trend: float | None = None
    if not usgovt.empty:
        govt_levels = usgovt.set_index("period")["value"].sort_index()
        diffs = govt_levels.diff().dropna()
        if len(diffs) >= government_lookback:
            gov_recent = diffs.iloc[-government_lookback:]
            government_trend = round(float(gov_recent.mean()), 2)
            method_notes["govt_lookback_n"] = int(len(gov_recent))
    if government_trend is None:
        absent.append("government_trend")

    # --- c. birth_death_residual_prior ---
    # Use walk-forward history: group residuals by calendar month, take trailing 5-year mean.
    # AMENDMENT A (2026-07-08): COVID window 2020-03..2020-06 excluded from BD prior pool,
    # consistent with the program-wide COVID exclusion (PREREG_NFP_DECOMP_V1.md Amendment A).
    _COVID_EXCL_START = pd.Timestamp("2020-03-01")
    _COVID_EXCL_END = pd.Timestamp("2020-06-01")  # inclusive upper bound (month granularity)
    ref_calendar_month = ref_month.month
    bd_prior: float | None = None
    if wf_results:
        cutoff_year = ref_month.year - birth_death_lookback_years
        month_residuals: list[float] = []
        for r in wf_results:
            p = r.get("period")
            if p is None:
                continue
            period_ts = pd.Timestamp(p)
            # PIT: only use results where period < ref_month (prior history)
            if period_ts >= pd.Timestamp(ref_month):
                continue
            if period_ts.year < cutoff_year:
                continue
            # COVID exclusion: drop 2020-03..2020-06 residuals (Amendment A)
            if _COVID_EXCL_START <= period_ts <= _COVID_EXCL_END:
                continue
            if period_ts.month == ref_calendar_month:
                actual = r.get("actual")
                predicted = r.get("predicted")
                if actual is not None and predicted is not None:
                    try:
                        month_residuals.append(float(actual) - float(predicted))
                    except (TypeError, ValueError):
                        pass
        if month_residuals:
            bd_prior = round(float(np.mean(month_residuals)), 2)
            method_notes["bd_n_months"] = len(month_residuals)
            method_notes["bd_lookback_years"] = birth_death_lookback_years
            method_notes["bd_calendar_month"] = ref_calendar_month
    if bd_prior is None:
        absent.append("birth_death_residual_prior")

    # --- d. residual ---
    parts_sum = sum(
        p for p in [private_trend, government_trend, bd_prior]
        if p is not None
    ) if (private_trend is not None or government_trend is not None or bd_prior is not None) else None
    residual: float | None = None
    if parts_sum is not None:
        residual = round(model_point - parts_sum, 2)

    return {
        "private_trend": private_trend,
        "government_trend": government_trend,
        "birth_death_residual_prior": bd_prior,
        "residual": residual,
        "confidence_map": {
            "private_trend": "proxy",       # ridge prediction mapped through USPRIV share
            "government_trend": "known-ish",  # direct trailing USGOVT initial-print mean
            "birth_death_residual_prior": "residual",  # learned from WF errors by month
            "residual": "residual",
        },
        "absent_parts": absent,
        "method_notes": method_notes,
    }


def compute_bd_prior_12month_profile(
    wf_results: list[dict],
    as_of_year: int,
    lookback_years: int = 5,
) -> dict[int, float | None]:
    """Return the birth-death prior for each calendar month (Jan=1..Dec=12).

    Uses the walk-forward history to compute, for each month M in 1..12,
    the trailing `lookback_years`-year mean of (actual - predicted) restricted
    to walk-forward steps whose period falls in month M.

    Parameters
    ----------
    wf_results : all walk-forward result dicts with {actual, predicted, period}
    as_of_year : the year for which the trailing cutoff is computed (inclusive)
    lookback_years : trailing years to include (cutoff = as_of_year - lookback_years)

    Returns dict {month_int: mean_residual_or_None}
    """
    # AMENDMENT A (2026-07-08): COVID window 2020-03..2020-06 excluded, consistent
    # with program-wide COVID handling (PREREG_NFP_DECOMP_V1.md Amendment A).
    _COVID_EXCL_START = pd.Timestamp("2020-03-01")
    _COVID_EXCL_END = pd.Timestamp("2020-06-01")  # inclusive upper bound
    cutoff_year = as_of_year - lookback_years
    by_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}

    for r in wf_results:
        p = r.get("period")
        if p is None:
            continue
        try:
            period_ts = pd.Timestamp(p)
        except Exception:
            continue
        if period_ts.year < cutoff_year or period_ts.year > as_of_year:
            continue
        # COVID exclusion: drop 2020-03..2020-06 residuals (Amendment A)
        if _COVID_EXCL_START <= period_ts <= _COVID_EXCL_END:
            continue
        actual = r.get("actual")
        predicted = r.get("predicted")
        if actual is None or predicted is None:
            continue
        try:
            resid = float(actual) - float(predicted)
        except (TypeError, ValueError):
            continue
        by_month[period_ts.month].append(resid)

    profile: dict[int, float | None] = {}
    for m in range(1, 13):
        vals = by_month[m]
        profile[m] = round(float(np.mean(vals)), 2) if vals else None

    return profile


# ---------------------------------------------------------------------------
# AHE Feature Builder
# ---------------------------------------------------------------------------

def build_ahe_features(
    asof: date,
    ref_month: date,
    vintages: pd.DataFrame,
    *,
    knowable_series_fn,
    survey_week_claims_fn,
    min_icsa_z_obs: int = 12,
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for AHE MoM % prediction at decision date asof.

    Per PREREG_NFP_DECOMP_V1.md §3.4.

    Returns (features_dict, provenance_dict).
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
        "unrevised_legs": [],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
    }

    # 1-3. AHE own lags (MoM %)
    ahe_df = knowable_series_fn(vintages, "CES0500000003", asof)
    if len(ahe_df) >= 2:
        ahe_levels = ahe_df.set_index("period")["value"].sort_index()
        ahe_mom = ahe_levels.pct_change() * 100.0
        ahe_mom = ahe_mom.dropna()
        lags: list[float | None] = []
        for i in range(1, 4):
            if len(ahe_mom) >= i:
                lags.append(float(ahe_mom.iloc[-i]))
            else:
                lags.append(None)
    else:
        lags = [None, None, None]

    features: dict[str, float | None] = {
        "ahe_mom_lag1": lags[0],
        "ahe_mom_lag2": lags[1],
        "ahe_mom_lag3": lags[2],
    }

    # 4. AWHAETP MoM (last knowable)
    awh_df = knowable_series_fn(vintages, "AWHAETP", asof)
    if len(awh_df) >= 2:
        awh_levels = awh_df.set_index("period")["value"].sort_index()
        awh_diff = awh_levels.diff().dropna()
        if len(awh_diff) >= 1:
            features["awh_mom_last"] = float(awh_diff.iloc[-1])
        else:
            features["awh_mom_last"] = None
            absent_legs.append("awh_mom_last")
    else:
        features["awh_mom_last"] = None
        absent_legs.append("awh_mom_last")

    # 5. JOLTS openings MoM % (last knowable)
    jolts_df = knowable_series_fn(vintages, "JTSJOL", asof)
    if len(jolts_df) >= 2:
        jolts_levels = jolts_df.set_index("period")["value"].sort_index()
        jolts_mom = jolts_levels.pct_change() * 100.0
        jolts_mom = jolts_mom.dropna()
        if len(jolts_mom) >= 1:
            features["jolts_mom_last"] = float(jolts_mom.iloc[-1])
        else:
            features["jolts_mom_last"] = None
            absent_legs.append("jolts_mom_last")
    else:
        features["jolts_mom_last"] = None
        absent_legs.append("jolts_mom_last")

    # 6. ICSA z-score for survey reference week
    icsa_df = knowable_series_fn(vintages, "ICSA", asof)
    if not icsa_df.empty:
        try:
            survey_val = survey_week_claims_fn(vintages, "ICSA", asof, ref_month)
            if survey_val is not None:
                # z-score against trailing 36 initial-print ICSA levels
                icsa_levels_all = icsa_df["value"].values
                if len(icsa_levels_all) >= min_icsa_z_obs:
                    trailing = icsa_levels_all[-36:] if len(icsa_levels_all) >= 36 else icsa_levels_all
                    mu = float(np.mean(trailing))
                    sig = float(np.std(trailing, ddof=1))
                    if sig > 0:
                        features["icsa_level_z"] = round(float((survey_val - mu) / sig), 4)
                    else:
                        features["icsa_level_z"] = 0.0
                else:
                    features["icsa_level_z"] = None
                    absent_legs.append("icsa_level_z")
            else:
                features["icsa_level_z"] = None
                absent_legs.append("icsa_level_z")
        except Exception as e:
            log.debug("ICSA z-score failed: %s", e)
            features["icsa_level_z"] = None
            absent_legs.append("icsa_level_z")
    else:
        features["icsa_level_z"] = None
        absent_legs.append("icsa_level_z")

    prov["absent_legs"] = absent_legs
    return features, prov


# ---------------------------------------------------------------------------
# AHE projection (ridge, same harness as NFP/CPI)
# ---------------------------------------------------------------------------

def project_ahe(
    asof: date,
    vintages: pd.DataFrame,
    *,
    knowable_series_fn,
    survey_week_claims_fn,
    ridge_predict_fn,
    walk_forward_fn,
    build_matrix_fn,
    compute_quantiles_fn,
    wilson_fn,
    min_train_obs: int = 60,
    min_quantile_obs: int = 24,
    inline_band_sigma: float = 0.35,
) -> dict:
    """Project AHE MoM % per PREREG_NFP_DECOMP_V1.md §3.

    Returns a projection dict with same key shape as other project_release outputs.
    release = "ahe", target = "ahe_mom".
    """
    feature_names = [
        "ahe_mom_lag1", "ahe_mom_lag2", "ahe_mom_lag3",
        "awh_mom_last", "jolts_mom_last", "icsa_level_z",
    ]

    # All initial CES0500000003 prints
    initial_prints = knowable_series_fn(vintages, "CES0500000003", asof)
    if len(initial_prints) < 2:
        return _empty_ahe_projection(asof, "insufficient_data")

    ahe_levels = initial_prints.copy()
    ahe_levels["mom"] = ahe_levels["value"].pct_change() * 100.0
    ahe_levels = ahe_levels.dropna(subset=["mom"]).reset_index(drop=True)

    if len(ahe_levels) < min_train_obs + 1:
        return _empty_ahe_projection(asof, "insufficient_history")

    # Build walk-forward records
    records = []
    for _, row in ahe_levels.iterrows():
        step_asof = (row["realtime_start"] - pd.Timedelta(days=1)).date()
        ref_month_step = row["period"].date() if hasattr(row["period"], "date") else date(
            pd.Timestamp(row["period"]).year, pd.Timestamp(row["period"]).month, 1
        )
        try:
            feats, _ = build_ahe_features(
                step_asof, ref_month_step, vintages,
                knowable_series_fn=knowable_series_fn,
                survey_week_claims_fn=survey_week_claims_fn,
            )
        except Exception as e:
            log.debug("AHE feature build failed at %s: %s", step_asof, e)
            feats = {fn: None for fn in feature_names}
        rec = dict(feats)
        rec["target"] = float(row["mom"])
        rec["period"] = row["period"]
        rec["asof"] = step_asof
        records.append(rec)

    # Walk-forward
    wf_results = walk_forward_fn(records, feature_names, "target", min_obs=min_train_obs)
    if not wf_results:
        return _empty_ahe_projection(asof, "no_walk_forward_results")

    # Current prediction
    asof_month = date(asof.year, asof.month, 1)
    feats, prov = build_ahe_features(
        asof, asof_month, vintages,
        knowable_series_fn=knowable_series_fn,
        survey_week_claims_fn=survey_week_claims_fn,
    )

    X_all = build_matrix_fn(records, feature_names)
    y_all = np.array([r["target"] for r in records], dtype=float)
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

    if n_features_used > 0 and len(y_clean) >= min_train_obs:
        point = float(ridge_predict_fn(X_clean, y_clean, x_pred))
    else:
        point = None

    errors = np.array([r["actual"] - r["predicted"] for r in wf_results])
    quantiles = compute_quantiles_fn(errors, point if point is not None else 0.0, min_obs=min_quantile_obs)

    # Baselines
    mom_vals = ahe_levels["mom"].values
    naive = float(mom_vals[-1]) if len(mom_vals) > 0 else None
    trailing_3m = float(np.mean(mom_vals[-3:])) if len(mom_vals) >= 3 else naive

    # Kill-rule determination (descriptive, not enforced live — evaluated in backtest)
    kill_rule_eval: dict = {}
    if len(errors) >= min_train_obs:
        naive_errors = np.array([r["actual"] - r["baseline_naive"] for r in wf_results])
        kill_rule_eval["mae_model"] = round(float(np.mean(np.abs(errors))), 4)
        kill_rule_eval["mae_naive"] = round(float(np.mean(np.abs(naive_errors))), 4)
        kill_rule_eval["model_beats_naive"] = kill_rule_eval["mae_model"] < kill_rule_eval["mae_naive"]

    # Confidence
    confidence, interval_rank = None, None
    if point is not None and len(errors) >= min_quantile_obs:
        cur_width = np.quantile(errors, 0.90) - np.quantile(errors, 0.10)
        hist_widths = []
        for k in range(min_quantile_obs, len(errors) + 1):
            e_sub = errors[:k]
            hist_widths.append(np.quantile(e_sub, 0.90) - np.quantile(e_sub, 0.10))
        if hist_widths:
            pctile = float(np.mean(np.array(hist_widths) <= cur_width))
            interval_rank = round(1.0 - pctile, 4)
            confidence = round(interval_rank * input_completeness, 4)

    # Surprise skew
    sigma, tag = None, None
    if point is not None and naive is not None and len(errors) >= min_quantile_obs:
        err_std = float(np.std(errors, ddof=1))
        if err_std > 0:
            sigma = round((point - naive) / err_std, 4)
            if abs(sigma) <= inline_band_sigma:
                tag = "inline"
            elif sigma > inline_band_sigma:
                tag = "hotter"
            else:
                tag = "cooler"

    prov.update({"n_train": int(len(y_all)), "n_features_used": n_features_used})

    return {
        "release": "ahe",
        "asof": asof.isoformat(),
        "target": "ahe_mom",
        "regime_axis": "growth",
        "spec_attempt": 1,
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
            "ar_model": None,  # AR3 omitted; own-3-lags is feature 1-3 in the model
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {
            "sigma": sigma,
            "tag": tag,
            "inline_band": inline_band_sigma,
        },
        "kill_rule_eval": kill_rule_eval,
        "pit_provenance": prov,
        "display_only": True,
        "authority": False,
    }


def _empty_ahe_projection(asof: date, reason: str) -> dict:
    return {
        "release": "ahe",
        "asof": asof.isoformat(),
        "target": "ahe_mom",
        "regime_axis": "growth",
        "spec_attempt": 1,
        "point": None,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "confidence": None,
        "confidence_components": {"interval_rank": None, "input_completeness": 0.0},
        "input_completeness": 0.0,
        "benchmark_set": {
            "naive_prior": None, "trailing_3m": None,
            "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
        },
        "surprise_skew": {"sigma": None, "tag": None, "inline_band": 0.35},
        "kill_rule_eval": {},
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
# AWH projection (persistence-only per PREREG_NFP_DECOMP_V1.md §4)
# ---------------------------------------------------------------------------

def project_awh(
    asof: date,
    vintages: pd.DataFrame,
    *,
    knowable_series_fn,
    min_quantile_obs: int = 24,
) -> dict:
    """Project avg weekly hours level (persistence-only) per PREREG_NFP_DECOMP_V1.md §4.

    Model IS the naive baseline (last initial-print level). Quantiles from residual history.
    persistence_only=True disclosed explicitly.
    """
    awh_df = knowable_series_fn(vintages, "AWHAETP", asof)
    if awh_df.empty:
        return _empty_awh_projection(asof, "insufficient_data")

    awh_sorted = awh_df.sort_values("period").reset_index(drop=True)
    if len(awh_sorted) < 2:
        return _empty_awh_projection(asof, "insufficient_data")

    # Point = last initial-print level
    point = float(awh_sorted["value"].iloc[-1])
    naive = point  # model IS naive

    # Residuals = actual[t] - level[t-1] for all periods in the vintage
    levels = awh_sorted.set_index("period")["value"]
    residuals_arr = (levels - levels.shift(1)).dropna().values

    # Quantile intervals from residual history
    quantiles: dict = {}
    if len(residuals_arr) >= min_quantile_obs:
        qs = np.quantile(residuals_arr, [0.10, 0.25, 0.50, 0.75, 0.90])
        quantiles = {
            "p10": round(point + qs[0], 2),
            "p25": round(point + qs[1], 2),
            "p50": round(point + qs[2], 2),
            "p75": round(point + qs[3], 2),
            "p90": round(point + qs[4], 2),
        }
    else:
        quantiles = {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    return {
        "release": "awh",
        "asof": asof.isoformat(),
        "target": "awh_level",
        "regime_axis": "growth",
        "spec_attempt": 1,
        "persistence_only": True,
        "persistence_only_note": (
            "Model IS the naive baseline (last initial-print AWHAETP level). "
            "No skill claim. Quantile context only."
        ),
        "point": round(point, 2),
        "p10": quantiles.get("p10"),
        "p25": quantiles.get("p25"),
        "p50": quantiles.get("p50"),
        "p75": quantiles.get("p75"),
        "p90": quantiles.get("p90"),
        "n_residuals": len(residuals_arr),
        "benchmark_set": {
            "naive_prior": round(naive, 2),
            "trailing_3m": None,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "inputs_used": {
            "last_awhaetp_level": round(point, 2),
            "n_history": len(awh_sorted),
        },
        "pit_provenance": {
            "revision_optimistic_legs": [],
            "unrevised_legs": [],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
        },
        "display_only": True,
        "authority": False,
        "confidence": None,
        "input_completeness": 1.0 if not awh_df.empty else 0.0,
    }


def _empty_awh_projection(asof: date, reason: str) -> dict:
    return {
        "release": "awh",
        "asof": asof.isoformat(),
        "target": "awh_level",
        "regime_axis": "growth",
        "spec_attempt": 1,
        "persistence_only": True,
        "persistence_only_note": (
            "Model IS the naive baseline (last initial-print AWHAETP level). "
            "No skill claim. Quantile context only."
        ),
        "point": None,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "n_residuals": 0,
        "benchmark_set": {
            "naive_prior": None, "trailing_3m": None,
            "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
        },
        "inputs_used": {},
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
        "confidence": None,
        "input_completeness": 0.0,
    }
