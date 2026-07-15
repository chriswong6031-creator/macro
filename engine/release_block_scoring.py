"""CPI Bridge Block-Level Scoring (MRI display-tier context-accrual infrastructure).

Computes ACTUAL per-block MoM contributions for scored cpi_bridge shadow rows,
enabling a per-block forward track record of predicted vs actual contribution.

Motivation: the June-2026 CPI cold print post-mortem found ~0.26pp of the bridge's
~0.43pp ex-energy overshoot was core-side disinflation invisible to lag-1 persistence
(see research/release_forecast/FIELD_GUIDE_BRIDGE_FORWARD_PROXIES.md §"Why persistence
fails at turns" and [[cpi-june2026-cold-print-postmortem]]). Block-level accrual is the
measurement substrate needed to evaluate whether a forward-proxy leg improves a specific
block — you cannot know which block is the bottleneck without per-block scored errors.

DISPLAY-TIER ONLY. authority=False. A null in any block never blocks champion scoring,
shadow scoring, the scoreboard, or the nightly.

SA/NSA BASIS NOTES (critical: actual and predicted must be on the same basis):
  energy_gasoline:         mom_est from GASREGW (ratio of monthly-avg $/gal) — NSA.
                           Actual = CUUR0000SAG1 (NSA CPI gasoline). Same NSA basis.
  energy_electricity:      mom_est from APU000072610 (NSA avg price). Actual = same series
                           (APU000072610). Same basis, same series.
  shelter:                 mom_est from CUSR0000SAH1 lag-1 blended with ZORI — SA.
                           Actual = CUSR0000SAH1 (SA). Same SA basis.
  food_at_home:            mom_est from CUSR0000SAF11 prior + WPU01 signal — SA.
                           Actual = CUSR0000SAF11 (SA). Same SA basis.
  core_goods_pipeline:     mom_est from PPIFIS/PPIFES pipeline (ALFRED SA) — SA.
                           Actual = CUSR0000SACL1E (SA, FRED "Commodities Less Food and
                           Energy Commodities", Seasonally Adjusted, 1957–). Same SA basis.
  core_services_ex_shelter: mom_est from CUSR0000SASLE lag-1 — SA.
                             Actual = CUSR0000SASLE (SA). Same SA basis (same series).
  unmodelled_residual (bridge block): no individual series, scored=False.

PIT STRATEGY:
  Prefer data/fred_vintage/vintages.parquet initial-print PIT for any series that appears
  there (currently none of the block official series are vintage-tracked, per the store
  state as of 2026-07-14). All block actual reads fall back to data/fred/<SERIES>.parquet
  (flat latest value), tagged revision_optimistic=True. CPI component revisions are BLS
  seasonal-recalc only (typically ≤0.1pp MoM on monthly), so the flat-store fallback
  introduces negligible look-ahead and is documented per-leg.

  When the vintage store later adds a block's official series, compute_block_actual_mom
  will automatically prefer it (vintage takes precedence in the source-check logic).

Fail-open contract: every function returns None on error, never raises.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component map — official CPI series per block
# Source of truth: data/release_forecast/component_map/cpi_component_map.yml
# This local dict mirrors that file; update if the yml is amended.
# ---------------------------------------------------------------------------

_COMPONENT_MAP: dict[str, dict[str, Any]] = {
    # block_name: {official_cpi_series, basis}
    "energy_gasoline": {
        "official_cpi_series": "CUUR0000SAG1",
        "basis": "nsa",
        "mismatch_note": None,
    },
    "energy_electricity": {
        "official_cpi_series": "APU000072610",
        "basis": "nsa",
        "mismatch_note": None,
    },
    "shelter": {
        "official_cpi_series": "CUSR0000SAH1",
        "basis": "sa",
        "mismatch_note": None,
    },
    "food_at_home": {
        "official_cpi_series": "CUSR0000SAF11",
        "basis": "sa",
        "mismatch_note": None,
    },
    "core_goods_pipeline": {
        # FIX-A: switched from CUUR0000SACL1E (NSA) to CUSR0000SACL1E (SA) so that
        # the SA-pipeline-derived mom_est and the actual are on the same basis.
        "official_cpi_series": "CUSR0000SACL1E",
        "basis": "sa",
        "mismatch_note": None,
    },
    "core_services_ex_shelter": {
        "official_cpi_series": "CUSR0000SASLE",
        "basis": "sa",
        "mismatch_note": None,
    },
    # Residual block — no scoreable official series
    "unmodelled_residual": {
        "official_cpi_series": None,  # bridge residual basket share
        "basis": None,
        "mismatch_note": "Bridge aggregate residual; no single official series. scored=False.",
    },
}


def compute_block_actual_mom(
    root: Path,
    official_cpi_series: str | None,
    period: str,
    asof: date,
) -> tuple[float | None, str, bool]:
    """Return the ACTUAL MoM % for a block's official CPI series for the given period.

    MoM is computed as: 100 * (L_M / L_{M-1} - 1), matching the level-to-MoM
    convention used throughout the bridge.

    Parameters
    ----------
    root : Path
        Repository root.
    official_cpi_series : str or None
        FRED series ID for this block's official CPI sub-index. None → return None.
    period : str
        ISO period string "YYYY-MM" for the target month M.
    asof : date
        Scoring date (the day the scoring sweep runs; typically = release_date or after).

    Returns
    -------
    (actual_mom, actual_source, revision_optimistic)
    actual_mom : float or None — MoM % if computable, else None
    actual_source : str — one of "vintage", "flat", "none"
    revision_optimistic : bool — True when reading from flat store (non-PIT)
    """
    if official_cpi_series is None:
        return None, "none", False

    period_ts = pd.Timestamp(period + "-01")
    prior_ts = period_ts - pd.offsets.MonthBegin(1)

    # --- Path 1: ALFRED vintage store (PIT-safe initial print) ---
    # Preferred when the series is vintage-tracked.
    vintage_path = root / "data" / "fred_vintage" / "vintages.parquet"
    if vintage_path.exists():
        try:
            vdf = pd.read_parquet(vintage_path)
            if official_cpi_series in vdf.get("series", pd.Series(dtype=str)).values:
                vdf["period"] = pd.to_datetime(vdf["period"])
                vdf["realtime_start"] = pd.to_datetime(vdf["realtime_start"])
                asof_ts = pd.Timestamp(asof)

                # Target month M: earliest vintage (initial print)
                mask_m = (
                    (vdf["series"] == official_cpi_series) &
                    (vdf["period"] == period_ts) &
                    (vdf["realtime_start"] <= asof_ts)
                )
                sub_m = vdf[mask_m]

                # Prior month M-1: earliest vintage (initial print)
                mask_prior = (
                    (vdf["series"] == official_cpi_series) &
                    (vdf["period"] == prior_ts) &
                    (vdf["realtime_start"] <= asof_ts)
                )
                sub_prior = vdf[mask_prior]

                if sub_m.empty or sub_prior.empty:
                    # Series is vintage-tracked but period not yet in store
                    log.debug(
                        "block_scoring: %s vintage missing M or M-1 for %s",
                        official_cpi_series, period,
                    )
                else:
                    level_m = float(sub_m.loc[sub_m["realtime_start"].idxmin(), "value"])
                    level_prior = float(sub_prior.loc[sub_prior["realtime_start"].idxmin(), "value"])
                    if level_prior != 0.0 and pd.notna(level_m) and pd.notna(level_prior):
                        mom = round((level_m / level_prior - 1) * 100, 4)
                        return mom, "vintage", False
        except Exception as e:
            log.debug(
                "block_scoring: vintage read failed for %s/%s: %s",
                official_cpi_series, period, e,
            )

    # --- Path 2: Flat store data/fred/<SERIES>.parquet (latest revision) ---
    # Revision_optimistic: CPI component revisions are seasonal-recalc only (small).
    flat_path = root / "data" / "fred" / f"{official_cpi_series}.parquet"
    if not flat_path.exists():
        log.debug(
            "block_scoring: flat parquet absent for %s (period=%s)",
            official_cpi_series, period,
        )
        return None, "none", False

    try:
        df = pd.read_parquet(flat_path)
        df.index = pd.to_datetime(df.index)
        col = df.columns[0]

        # Find M and M-1 levels
        # Monthly series: match by period (year+month)
        m_mask = (df.index.year == period_ts.year) & (df.index.month == period_ts.month)
        prior_mask = (df.index.year == prior_ts.year) & (df.index.month == prior_ts.month)

        m_rows = df[m_mask]
        prior_rows = df[prior_mask]

        if m_rows.empty or prior_rows.empty:
            log.debug(
                "block_scoring: flat %s missing M or M-1 for period=%s",
                official_cpi_series, period,
            )
            return None, "flat", True

        level_m = float(m_rows[col].iloc[-1])
        level_prior = float(prior_rows[col].iloc[-1])

        if level_prior == 0.0 or pd.isna(level_m) or pd.isna(level_prior):
            return None, "flat", True

        mom = round((level_m / level_prior - 1) * 100, 4)
        return mom, "flat", True

    except Exception as e:
        log.debug(
            "block_scoring: flat read failed for %s/%s: %s",
            official_cpi_series, period, e,
        )
        return None, "flat", True


def score_bridge_blocks(
    root: Path | str,
    components: list[dict],
    period: str,
    asof: date,
) -> list[dict]:
    """Score each block in a cpi_bridge components array against its actual CPI series.

    For each block, returns a scored dict with:
        block: str
        weight: float
        predicted_contribution_pp: float  — the row's contribution_pp
        actual_block_mom: float | None
        actual_contribution_pp: float | None  — actual_block_mom * weight/100
        block_error_pp: float | None          — predicted_contribution_pp - actual_contribution_pp
        basis: str | None                     — 'sa', 'nsa', 'nsa_actual', or None
        actual_source: str                    — 'vintage', 'flat', 'none'
        revision_optimistic: bool
        scored: bool                          — False when actual is None
        mismatch_note: str | None             — SA/NSA basis mismatch annotation

    Blocks with actual=None → scored=False, error=None. Never dropped, never crash.

    Parameters
    ----------
    root : Path or str
    components : list of bridge component dicts (from the frozen shadow_projection row)
    period : str  — "YYYY-MM" period string
    asof : date   — scoring date
    """
    root = Path(root)
    results: list[dict] = []

    for comp in components:
        block = comp.get("block", "")
        weight = comp.get("weight", 0.0)
        predicted_contribution_pp = comp.get("contribution_pp")

        block_info = _COMPONENT_MAP.get(block, {})
        official_series = block_info.get("official_cpi_series")
        basis = block_info.get("basis")
        mismatch_note = block_info.get("mismatch_note")

        try:
            actual_block_mom, actual_source, revision_optimistic = compute_block_actual_mom(
                root=root,
                official_cpi_series=official_series,
                period=period,
                asof=asof,
            )
        except Exception as e:
            log.debug("block_scoring: compute_block_actual_mom failed for %s: %s", block, e)
            actual_block_mom = None
            actual_source = "none"
            revision_optimistic = False

        if actual_block_mom is not None and weight is not None:
            actual_contribution_pp: float | None = round(actual_block_mom * weight / 100.0, 6)
        else:
            actual_contribution_pp = None

        if (
            predicted_contribution_pp is not None
            and actual_contribution_pp is not None
        ):
            block_error_pp: float | None = round(
                predicted_contribution_pp - actual_contribution_pp, 6
            )
        else:
            block_error_pp = None

        scored = actual_block_mom is not None

        entry: dict = {
            "block": block,
            "weight": weight,
            "predicted_contribution_pp": predicted_contribution_pp,
            "actual_block_mom": actual_block_mom,
            "actual_contribution_pp": actual_contribution_pp,
            "block_error_pp": block_error_pp,
            "basis": basis,
            "actual_source": actual_source,
            "revision_optimistic": revision_optimistic,
            "scored": scored,
        }
        if mismatch_note:
            entry["mismatch_note"] = mismatch_note

        results.append(entry)

    return results


def aggregate_block_scoreboard(
    scored_rows: list[dict],
) -> dict[str, dict]:
    """Aggregate per-block MAE, n_scored, and mean signed error across scored bridge rows.

    Parameters
    ----------
    scored_rows : list of scored ledger rows (row_type='scored', model='cpi_bridge')
                  that carry a 'block_scores' key.

    Returns
    -------
    dict keyed by block name, each entry:
        n_scored: int
        mae_block_error_pp: float | None
        mean_signed_error_pp: float | None  (positive = bridge over-predicts)
        basis: str | None                   — SA/NSA basis label from the component map
                                              ('sa', 'nsa', or None for residuals). Carried
                                              through from block_scores so any non-SA-
                                              consistent block is visibly labeled rather
                                              than presented as bare skill.
        revision_optimistic: bool           — True when ANY scored row for this block read
                                              from the flat store (non-PIT). False when ALL
                                              reads were PIT vintage.
    Only blocks with n_scored >= 1 appear.
    """
    accum: dict[str, dict[str, Any]] = {}

    for row in scored_rows:
        block_scores = row.get("block_scores")
        if not block_scores:
            continue
        for bs in block_scores:
            if not bs.get("scored", False):
                continue
            err = bs.get("block_error_pp")
            if err is None:
                continue
            block = bs.get("block", "")
            if block not in accum:
                accum[block] = {
                    "abs_errors": [],
                    "signed_errors": [],
                    "basis": bs.get("basis"),
                    "any_revision_optimistic": False,
                }
            accum[block]["abs_errors"].append(abs(err))
            accum[block]["signed_errors"].append(err)
            if bs.get("revision_optimistic", False):
                accum[block]["any_revision_optimistic"] = True

    result: dict[str, dict] = {}
    for block, data in accum.items():
        n = len(data["abs_errors"])
        result[block] = {
            "n_scored": n,
            "mae_block_error_pp": round(sum(data["abs_errors"]) / n, 6) if n > 0 else None,
            "mean_signed_error_pp": (
                round(sum(data["signed_errors"]) / n, 6) if n > 0 else None
            ),
            "basis": data["basis"],
            "revision_optimistic": data["any_revision_optimistic"],
        }

    return result
