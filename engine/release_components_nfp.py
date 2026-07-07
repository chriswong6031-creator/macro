"""MRI — NFP and Claims feature builders (split from engine/release_forecast.py for PR-H parallel work).

LEAF · DISPLAY-ONLY. Pure numpy/pandas only.

All public functions here were previously defined inline in engine/release_forecast.py.
engine/release_forecast.py imports from this module — callers that import from
engine.release_forecast see no change.

Also contains: claims_walk_forward_residuals — the expanding walk-forward residual
series for the claims naive model (IC4WSA → ICSA), used to build quantile bands
for the claims projection.

SPECIFICATION: research/release_forecast/PREREG_V1.md (frozen 2026-07-07).
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
        "revision_optimistic_legs": ["awhman_mom"],
        "unrevised_legs": ["withheld_tax_yoy", "adp_change"],
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

    # ADP (fail-open if absent)
    adp_path = root / "data" / "fred" / "ADPNFRPRIVSA.parquet"
    if adp_path.exists():
        try:
            adp = pd.read_parquet(adp_path)
            adp.index = pd.to_datetime(adp.index)
            adp_col = adp.columns[0]
            ref_m = pd.Timestamp(ref_month)
            adp_val = adp[adp_col].get(ref_m)
            if adp_val is not None and not np.isnan(adp_val):
                features["adp_change"] = float(adp_val)
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
        residuals.append(icsa_val - ic4_pred)

    residuals_arr = np.array(residuals, dtype=float)

    # Quantiles: p10/p25/p50/p75/p90 from expanding residuals
    point = ic4wsa_last
    if len(residuals_arr) >= min_quantile_obs:
        qs = np.quantile(residuals_arr, [0.10, 0.25, 0.50, 0.75, 0.90])
        quantiles = {
            "p10": round(point + qs[0], 1),
            "p25": round(point + qs[1], 1),
            "p50": round(point + qs[2], 1),
            "p75": round(point + qs[3], 1),
            "p90": round(point + qs[4], 1),
        }
    else:
        quantiles = {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}

    return {
        "release": "claims",
        "asof": asof.isoformat(),
        "target": "icsa_level",
        "regime_axis": "growth",
        "point": round(point, 1),
        "p10": quantiles["p10"],
        "p25": quantiles["p25"],
        "p50": quantiles["p50"],
        "p75": quantiles["p75"],
        "p90": quantiles["p90"],
        "n_residuals": len(residuals_arr),
        "benchmark_set": {
            "naive_prior": round(icsa_last, 1),
            "trailing_3m": None,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "inputs_used": {
            "ic4wsa_last": round(ic4wsa_last, 1),
            "icsa_last": round(icsa_last, 1),
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
            "naive_prior": None, "trailing_3m": None,
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
