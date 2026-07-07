"""MRI — CPI feature builders (split from engine/release_forecast.py for PR-G parallel work).

LEAF · DISPLAY-ONLY. Pure numpy/pandas only.

All public functions here were previously defined inline in engine/release_forecast.py.
engine/release_forecast.py imports from this module — callers that import from
engine.release_forecast see no change.

SPECIFICATION: research/release_forecast/PREREG_V1.md (frozen 2026-07-07).
Anti-mining: one spec, frozen before any results were observed.

PIT LAW: a feature value is usable at decision date D only if its ALFRED
realtime_start <= D. The `knowable_series` function (engine/release_forecast.py)
enforces this filter.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


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
) -> tuple[dict[str, float | None], dict]:
    """Build feature dict for CPI prediction at decision date asof.

    release_type: 'cpi_headline' or 'cpi_core'.
    ref_month: the CPI reference month M the target print covers (PREREG_V1.md §2.3
        feature 7 anchors gasoline_mom on M, not on asof's calendar month — at the
        decision date asof is already inside M+1). When None, derived as the month
        after the last knowable own-series initial print.
    knowable_series_fn / last_n_mom_lags_fn: injected from engine.release_forecast
        to avoid circular imports (these helpers live there and reference each other).
    Returns (features_dict, provenance_dict).
    features_dict: {feature_name: value_or_None}
    provenance_dict: {revision_optimistic_legs, unrevised_legs, absent_legs, ...}
    """
    absent_legs: list[str] = []
    prov: dict[str, Any] = {
        "revision_optimistic_legs": [],
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

    # Sticky CPI (2014-03+)
    sticky_lags = last_n_mom_lags_fn(vintages, "STICKCPIM157SFRBATL", asof, n=1)
    features["sticky_mom_lag1"] = sticky_lags[0]

    # Median CPI (2014-02+)
    median_lags = last_n_mom_lags_fn(vintages, "MEDCPIM158SFRBCLE", asof, n=1)
    features["median_mom_lag1"] = median_lags[0]

    # Flexible CPI (2014-03+)
    flex_lags = last_n_mom_lags_fn(vintages, "FLEXCPIM157SFRBATL", asof, n=1)
    features["flex_mom_lag1"] = flex_lags[0]

    # PPI Final Demand (2014-03+)
    ppi_lags = last_n_mom_lags_fn(vintages, "PPIFIS", asof, n=1)
    features["ppi_mom_lag1"] = ppi_lags[0]

    # Gasoline (headline only; fail-open if absent)
    if release_type == "cpi_headline":
        prov["unrevised_legs"].append("gasoline_mom")
        gasregw_path = root / "data" / "fred" / "GASREGW.parquet"
        if gasregw_path.exists():
            try:
                gasregw = pd.read_parquet(gasregw_path)
                gasregw.index = pd.to_datetime(gasregw.index)
                asof_ts = pd.Timestamp(asof)
                # Anchor on the reference month M the target print covers — at the
                # decision date asof already sits in the release month M+1, so
                # month(asof) would average the wrong month's weeks.
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

    prov["absent_legs"] = absent_legs
    return features, prov
