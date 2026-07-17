"""scripts/build_conditional_cells.py — W4.4: phase × quad conditional forward-return cells.

Ruling A2: ALL inference via whole-month block bootstrap; no n/h Wilson path.
James-Stein shrinkage toward the phase-pooled mean; cells below n_eff floor collapse to pooled.
Ruling A7: research surface only — output goes to measurement.html, NOT to any trading card.
P-D5-1: every quad-conditioned cell is labeled revision_optimistic=True.

Output: data/cycle_ontology/conditional_cells_<epoch>.json

Usage:
    python scripts/build_conditional_cells.py [--panel PATH] [--out DIR]

Design
------
1. Derive phase_v2 from pos_osc + direction (ZONE_EHI / ZONE_ELO from cycle_ontology).
2. Join h-month forward returns and vol-residualized max-DD from daily price files.
3. For each (family × phase_v2 × quad) cell compute:
     - n_months: count of unique month-end stamps in cell
     - n_raw: row count
     - n_eff: n_raw / h (overlap deflation — used ONLY for James-Stein weight; never as CI input)
     - shrink_weight: James-Stein w_c (tau2 / (tau2 + s2_c/n_eff_c))
     - shrunk_mean: w_c * raw_mean + (1-w_c) * phase_pooled_mean
     - boot_ci: 95% CI on the GAP (shrunk_mean − pooled_mean) via date-block bootstrap
     - collapsed: True if n_months < N_EFF_FLOOR
     - revision_optimistic: True (quad conditioning; P-D5-1)
4. Write JSON artifact.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

# ── path setup ────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from engine.cycle_ontology import ZONE_EHI, ZONE_ELO  # noqa: E402
from engine.grading_stats import block_bootstrap_ci, BOOT_DRAWS, BOOT_SEED  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
PANEL_PATH = os.path.join(_ROOT, "data/hazard/panel_price_c4414dcb.parquet")
YAHOO_DIR = os.path.join(_ROOT, "data/yahoo")
CN_DIR = os.path.join(_ROOT, "data/china_sectors")
OUT_DIR = os.path.join(_ROOT, "data/cycle_ontology")

# Horizons in calendar days (≈ 63 trading days ≈ 3 months; 126 ≈ 6 months)
# We use calendar-day offsets so month-end → month-end is exact
HORIZONS = {
    "63d": 63,   # forward return window in TRADING days
    "126d": 126,
}

PHASES = ["Trough", "Recovery", "Expansion", "Peak", "Downturn"]
QUADS = ["Q1", "Q2", "Q3", "Q4"]
FAMILIES = ["us_sector", "country", "cn_sector"]

# Collapse threshold: a cell with fewer unique month-end stamps than this
# is collapsed to the phase-pooled row.
N_MONTHS_FLOOR = 12  # per D5 §2.3 / W4.4 scope

# James-Stein prior blend constant (same as hazard model age blend, pre-registered)
# n_eff floor below which a cell's own variance estimate is unreliable
N_EFF_SHRINK_FLOOR = 3.0


# ── phase derivation ──────────────────────────────────────────────────────────

def derive_phase(pos_osc: float, direction: str) -> str:
    """Map (pos_osc, direction) → one of the 5 D1 ontology phases.

    Uses ZONE_EHI (68) / ZONE_ELO (32) from cycle_ontology, with direction
    (up-leg = rising) as the disambiguation signal, approximating
    cycle_ontology.classify_phase() §2.1. MTF MACD votes are not available
    in the monthly panel; direction is the causal substitute.

    KNOWN DIVERGENCE (#2697 port): classify_phase now labels high+rising "Peak"
    only with confirmed weekly/3D deceleration (full thrust → "Expansion"); this
    labeler cannot see MTF state, so it keeps the unconditional high+rising →
    "Peak" cut. Training-panel "Peak" cohorts are therefore a superset of live
    phase_v2 "Peak" stamps on the stretched-leader margin. The lattice output is
    display_only, so this is a disclosed approximation, not a promotion input.
    """
    rising = direction == "up"
    if pos_osc >= ZONE_EHI:
        return "Peak" if rising else "Downturn"
    elif pos_osc <= ZONE_ELO:
        return "Recovery" if rising else "Trough"
    elif rising:
        return "Expansion"
    else:
        return "Downturn"


# ── price loader ──────────────────────────────────────────────────────────────

def _load_yahoo(ticker: str) -> pd.Series:
    """Load dividend-adjusted close from data/yahoo/<ticker>.parquet."""
    path = os.path.join(YAHOO_DIR, f"{ticker}.parquet")
    df = pd.read_parquet(path)
    # The multi-level column may be ('close',) or just 'close'
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(0)
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_cn(code: str) -> pd.Series:
    """Load Shenwan sector close from data/china_sectors/<code>.parquet."""
    path = os.path.join(CN_DIR, f"{code}.parquet")
    df = pd.read_parquet(path)
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_price(instrument_id: str, family: str) -> pd.Series:
    if family == "cn_sector":
        return _load_cn(instrument_id)
    return _load_yahoo(instrument_id)


# ── forward return & vol-residualized max-DD ──────────────────────────────────

def _fwd_ret(close: pd.Series, h_td: int) -> pd.Series:
    """h_td-trading-day forward log-return (shifted by h_td bars)."""
    arr = close.to_numpy(float)
    n = len(arr)
    out = np.full(n, np.nan)
    for i in range(n - h_td):
        if arr[i] > 0 and arr[i + h_td] > 0:
            out[i] = math.log(arr[i + h_td] / arr[i])
    return pd.Series(out, index=close.index)


def _fwd_maxdd(close: pd.Series, h_td: int) -> pd.Series:
    """Worst close-to-close drawdown over the next h_td trading days (≤0)."""
    arr = close.to_numpy(float)
    n = len(arr)
    out = np.full(n, np.nan)
    for i in range(n - 1):
        seg = arr[i + 1: i + 1 + h_td]
        if len(seg) > 0 and arr[i] > 0:
            out[i] = float(seg.min() / arr[i] - 1.0)
    return pd.Series(out, index=close.index)


def _trailing_vol(close: pd.Series, window: int = 63) -> pd.Series:
    """Annualized trailing vol from log-returns over the last `window` trading days."""
    log_r = np.log(close / close.shift(1))
    vol = log_r.rolling(window, min_periods=max(window // 2, 10)).std() * math.sqrt(252)
    return vol


def build_price_features(
    instrument_id: str, family: str, horizons: dict[str, int]
) -> pd.DataFrame | None:
    """Compute monthly fwd_ret_Xd and rdd_Xd (vol-residualized max-DD) for one instrument.

    Returns a DataFrame indexed by month-end dates with columns:
        fwd_ret_63d, fwd_maxdd_63d, rdd_63d,
        fwd_ret_126d, fwd_maxdd_126d, rdd_126d
    or None if the price file is missing.
    """
    try:
        close = _load_price(instrument_id, family)
    except (FileNotFoundError, KeyError, Exception):
        return None

    if len(close) < 200:
        return None

    tvol = _trailing_vol(close, 63)

    frames: list[pd.DataFrame] = []
    for label, h_td in horizons.items():
        fr = _fwd_ret(close, h_td)
        mdd = _fwd_maxdd(close, h_td)
        # Vol-residualized max-DD: rdd = fwd_maxdd / trailing_vol
        # Uses the SAME trailing_vol as W4.6 metric: mean_fwd_ret/|dd_p10| was
        # replaced by rdd = fwd_maxdd / trailing_63d_vol (§6.5 item 2).
        # Clamp vol to avoid div-by-zero on illiquid series.
        rdd = mdd / tvol.clip(lower=0.01)

        daily = pd.DataFrame({
            f"fwd_ret_{label}": fr,
            f"fwd_maxdd_{label}": mdd,
            f"rdd_{label}": rdd,
        })
        # Resample to month-end: take the LAST daily value within each month
        # (which is the month-end date itself for month-end stamped panel rows).
        monthly = daily.resample("ME").last()
        frames.append(monthly)

    if not frames:
        return None
    result = pd.concat(frames, axis=1)
    result.index.name = "date"
    return result


# ── James-Stein shrinkage ─────────────────────────────────────────────────────

def james_stein_shrink(
    cells: list[dict],
    raw_mean_key: str = "raw_mean",
    n_eff_key: str = "n_eff",
    within_var_key: str = "within_var",
) -> list[dict]:
    """Apply James-Stein shrinkage toward the phase-pooled mean.

    Estimator (D5 §2.2, method-of-moments):
        m_phase = mean of raw_mean_c across cells (weighted by n_eff)
        s2_c    = within-cell variance of the outcome
        tau2    = max(0, Var_c(m_c) - mean_c(s2_c / n_eff_c))   # between-cell variance
        w_c     = tau2 / (tau2 + s2_c / n_eff_c)                # shrink weight
        shrunk  = w_c * m_c + (1 - w_c) * m_phase

    n_eff = n_raw / h (overlap deflation) is used ONLY here (for the shrinkage
    weight denominator), NEVER as a Wilson CI input. Per ruling A2, CIs come
    from block_bootstrap_ci exclusively.

    Cells with n_eff < N_EFF_SHRINK_FLOOR get w_c = 0 (full shrinkage to pooled).

    Mutates each cell dict in-place to add:
        phase_pooled_mean, shrink_weight, shrunk_mean
    Returns the list for chaining.
    """
    if not cells:
        return cells

    # Weighted phase-pooled mean (weight = n_eff)
    n_effs = np.array([c[n_eff_key] for c in cells], float)
    means = np.array([c[raw_mean_key] for c in cells], float)
    total_n = n_effs.sum()
    if total_n <= 0:
        m_pooled = float(np.mean(means))
    else:
        m_pooled = float(np.dot(n_effs, means) / total_n)

    # Between-cell variance (method of moments)
    within_vars = np.array([c[within_var_key] for c in cells], float)
    # Var_c(m_c) — unbiased across cells
    var_cells = float(np.var(means, ddof=1)) if len(means) > 1 else 0.0
    # mean_c(s2_c / n_eff_c)
    sampling_var_mean = float(np.mean(
        np.where(n_effs > 0, within_vars / np.maximum(n_effs, 1e-6), 0.0)
    ))
    tau2 = max(0.0, var_cells - sampling_var_mean)

    for cell, n_eff, s2 in zip(cells, n_effs, within_vars):
        if n_eff < N_EFF_SHRINK_FLOOR:
            w_c = 0.0  # fully collapsed to pooled
        elif tau2 == 0.0:
            w_c = 0.0  # no between-cell signal → all shrink fully
        else:
            sampling_var_cell = s2 / max(n_eff, 1e-6)
            w_c = tau2 / (tau2 + sampling_var_cell)
        cell["phase_pooled_mean"] = round(m_pooled, 6)
        cell["shrink_weight"] = round(w_c, 4)
        cell["shrunk_mean"] = round(w_c * cell[raw_mean_key] + (1.0 - w_c) * m_pooled, 6)

    return cells


# ── block-bootstrap CI on the cell mean ──────────────────────────────────────

def cell_boot_ci(
    dates: np.ndarray,
    vals: np.ndarray,
    mask: np.ndarray,
    *,
    draws: int = BOOT_DRAWS,
    seed: int = BOOT_SEED,
) -> list[float] | None:
    """95% CI on (cell mean − pooled mean) via whole-month date-block bootstrap.

    Resamples whole month-end dates; same-date rows always move together
    (ruling A2: cross-sectional correlation is handled). Returns [lo, hi] or None.
    """
    return block_bootstrap_ci(dates, vals, mask, draws=draws, seed=seed, stat="mean")


def cell_p10_boot_ci(
    dates: np.ndarray,
    vals: np.ndarray,
    mask: np.ndarray,
    *,
    draws: int = BOOT_DRAWS,
    seed: int = BOOT_SEED,
) -> list[float] | None:
    """95% CI on (cell p10 − pooled p10) for vol-residualized max-DD."""
    return block_bootstrap_ci(dates, vals, mask, draws=draws, seed=seed, stat="p10")


# ── main builder ─────────────────────────────────────────────────────────────

def build_panel_with_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Join the hazard panel with monthly forward returns for each instrument."""
    panel = panel.copy()

    # Derive phase_v2
    panel["phase_v2"] = panel.apply(
        lambda r: derive_phase(r["pos_osc"], r["direction"]), axis=1
    )

    # Collect per-instrument price features, then join to panel
    instruments = panel[["id", "family"]].drop_duplicates()
    price_cache: dict[str, pd.DataFrame | None] = {}

    for _, row in instruments.iterrows():
        iid, fam = row["id"], row["family"]
        key = f"{fam}/{iid}"
        if key not in price_cache:
            price_cache[key] = build_price_features(iid, fam, HORIZONS)

    # Normalize panel date to month-end
    panel["date"] = pd.to_datetime(panel["date"]).dt.to_period("M").dt.to_timestamp("M")

    # Build joined rows
    result_rows: list[dict] = []
    for key, pf in price_cache.items():
        if pf is None:
            continue
        fam, iid = key.split("/", 1)
        sub = panel[(panel["family"] == fam) & (panel["id"] == iid)].copy()
        if sub.empty:
            continue
        sub_joined = sub.set_index("date").join(pf, how="left")
        sub_joined["id"] = iid
        sub_joined["family"] = fam
        result_rows.append(sub_joined.reset_index())

    if not result_rows:
        raise RuntimeError("No instruments produced price features — check data paths.")

    joined = pd.concat(result_rows, ignore_index=True)
    return joined


def compute_cells(joined: pd.DataFrame, outcome: str, h_label: str) -> list[dict]:
    """Compute cells for one (outcome, horizon) pair across all (family, phase, quad).

    outcome: 'fwd_ret' or 'rdd'
    h_label: '63d' or '126d'
    Returns list of cell dicts.
    """
    col = f"{outcome}_{h_label}"
    if col not in joined.columns:
        raise ValueError(f"Column {col} not found in joined panel")

    # Drop censored rows and rows with NaN outcome
    df = joined[joined["censored"] == 0].copy()
    df = df.dropna(subset=[col])

    dates_all = df["date"].astype(str).to_numpy()
    vals_all = df[col].to_numpy(float)

    cells: list[dict] = []

    for family in FAMILIES:
        fam_mask_full = (df["family"] == family).to_numpy(bool)
        for phase in PHASES:
            # Phase-pooled group (all quads in this family×phase)
            phase_mask_full = fam_mask_full & (df["phase_v2"] == phase).to_numpy(bool)
            n_phase_rows = int(phase_mask_full.sum())
            phase_dates = dates_all[phase_mask_full]
            phase_vals = vals_all[phase_mask_full]
            n_phase_months = len(np.unique(phase_dates))
            phase_mean = float(np.mean(phase_vals)) if len(phase_vals) > 0 else np.nan

            # Collect per-quad cells for this (family, phase) group
            quad_cells: list[dict] = []
            for quad in QUADS:
                cell_mask_full = phase_mask_full & (df["quad"] == quad).to_numpy(bool)
                cell_rows = df[cell_mask_full]
                n_rows = int(cell_mask_full.sum())
                cell_dates = dates_all[cell_mask_full]
                cell_vals = vals_all[cell_mask_full]
                n_months = len(np.unique(cell_dates)) if n_rows > 0 else 0

                # h for overlap deflation: 63d ≈ 3m, 126d ≈ 6m
                h_overlap = 3 if h_label == "63d" else 6
                n_eff = n_rows / h_overlap if n_rows > 0 else 0.0

                collapsed = (n_months < N_MONTHS_FLOOR)

                if n_rows > 1 and not collapsed:
                    raw_mean = float(np.mean(cell_vals))
                    raw_p10 = float(np.percentile(cell_vals, 10))
                    within_var = float(np.var(cell_vals, ddof=1))
                    raw_pos_rate = float(np.mean(cell_vals > 0))
                else:
                    raw_mean = phase_mean
                    raw_p10 = float(np.percentile(phase_vals, 10)) if len(phase_vals) > 0 else np.nan
                    within_var = float(np.var(phase_vals, ddof=1)) if len(phase_vals) > 1 else 0.0
                    raw_pos_rate = float(np.mean(phase_vals > 0)) if len(phase_vals) > 0 else np.nan

                # Block-bootstrap CI on gap (cell − pooled), ruling A2.
                # Base population: all rows in this family.
                # Condition mask: rows in this family that are also in this (phase, quad) cell.
                # Resamples whole month-end dates (cross-sectional correlation handled).
                if not collapsed and n_months >= N_MONTHS_FLOOR and len(np.unique(phase_dates)) >= 2:
                    boot_ci = block_bootstrap_ci(
                        dates_all[fam_mask_full],
                        vals_all[fam_mask_full],
                        (df[fam_mask_full]["phase_v2"] == phase).to_numpy(bool) &
                        (df[fam_mask_full]["quad"] == quad).to_numpy(bool),
                        stat="mean"
                    )
                else:
                    boot_ci = None

                quad_cells.append({
                    "family": family,
                    "phase_v2": phase,
                    "quad": quad,
                    "n_rows": n_rows,
                    "n_months": n_months,
                    "n_eff": round(n_eff, 2),
                    "raw_mean": round(raw_mean, 6) if not np.isnan(raw_mean) else None,
                    "raw_p10": round(raw_p10, 6) if not np.isnan(raw_p10) else None,
                    "within_var": round(within_var, 8),
                    "raw_pos_rate": round(raw_pos_rate, 4) if not np.isnan(raw_pos_rate) else None,
                    "boot_ci_95": boot_ci,
                    "collapsed": collapsed,
                    "revision_optimistic": True,  # P-D5-1: quad conditioning uses revision-leaky labels
                    # JS fields will be set after james_stein_shrink
                })

            # Apply James-Stein shrinkage to this family×phase group
            non_collapsed = [c for c in quad_cells if not c["collapsed"]]
            if non_collapsed:
                james_stein_shrink(
                    non_collapsed,
                    raw_mean_key="raw_mean",
                    n_eff_key="n_eff",
                    within_var_key="within_var",
                )
            # Set fields for collapsed cells: use phase-pooled mean, w=0
            for c in quad_cells:
                if c["collapsed"] or "shrunk_mean" not in c:
                    c["phase_pooled_mean"] = round(phase_mean, 6) if not np.isnan(phase_mean) else None
                    c["shrink_weight"] = 0.0
                    c["shrunk_mean"] = round(phase_mean, 6) if not np.isnan(phase_mean) else None

            # Add phase-pooled row for reference
            pooled_cell = {
                "family": family,
                "phase_v2": phase,
                "quad": "pooled",
                "n_rows": n_phase_rows,
                "n_months": n_phase_months,
                "n_eff": round(n_phase_rows / (3 if h_label == "63d" else 6), 2),
                "raw_mean": round(phase_mean, 6) if not np.isnan(phase_mean) else None,
                "raw_p10": round(float(np.percentile(phase_vals, 10)), 6) if len(phase_vals) > 0 else None,
                "within_var": round(float(np.var(phase_vals, ddof=1)), 8) if len(phase_vals) > 1 else 0.0,
                "raw_pos_rate": round(float(np.mean(phase_vals > 0)), 4) if len(phase_vals) > 0 else None,
                "boot_ci_95": None,
                "collapsed": False,
                "revision_optimistic": False,  # phase-only; no quad conditioning
                "phase_pooled_mean": round(phase_mean, 6) if not np.isnan(phase_mean) else None,
                "shrink_weight": 1.0,
                "shrunk_mean": round(phase_mean, 6) if not np.isnan(phase_mean) else None,
            }

            cells.extend(quad_cells)
            cells.append(pooled_cell)

    return cells


def _epoch_tag() -> str:
    """UTC date string for artifact naming."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")


def verdict_ci_excludes_pooled(cells: list[dict]) -> list[dict]:
    """Return cells whose 95% CI on (cell_mean − pooled_mean) excludes 0.

    This is the DL-2 gate question: are there cells that carry a CI
    distinguishing them from the phase-pooled baseline?
    """
    winners: list[dict] = []
    for c in cells:
        if c.get("collapsed") or c.get("quad") == "pooled":
            continue
        ci = c.get("boot_ci_95")
        if ci is None:
            continue
        lo, hi = ci[0], ci[1]
        # CI excludes 0 means both bounds same sign (non-zero gap is reliable)
        if lo > 0 or hi < 0:
            winners.append(c)
    return winners


def main() -> int:
    parser = argparse.ArgumentParser(description="W4.4 conditional cells builder")
    parser.add_argument("--panel", default=PANEL_PATH, help="Path to hazard panel parquet")
    parser.add_argument("--out", default=OUT_DIR, help="Output directory")
    parser.add_argument("--draws", type=int, default=BOOT_DRAWS, help="Bootstrap draws")
    parser.add_argument("--seed", type=int, default=BOOT_SEED, help="Bootstrap seed")
    args = parser.parse_args()

    print(f"[W4.4] Loading panel from {args.panel}")
    panel = pd.read_parquet(args.panel)
    print(f"[W4.4] Panel: {len(panel)} rows, {panel['date'].nunique()} months, "
          f"{panel['id'].nunique()} instruments")

    print("[W4.4] Building forward return features from price files...")
    joined = build_panel_with_returns(panel)
    n_joined = len(joined)
    n_with_ret63 = int(joined["fwd_ret_63d"].notna().sum())
    n_with_ret126 = int(joined["fwd_ret_126d"].notna().sum())
    print(f"[W4.4] Joined panel: {n_joined} rows; "
          f"fwd_ret_63d non-null={n_with_ret63}, fwd_ret_126d non-null={n_with_ret126}")

    epoch = _epoch_tag()
    artifact: dict = {
        "schema": 1,
        "epoch": epoch,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "panel_path": os.path.basename(args.panel),
        "panel_rows": len(panel),
        "joined_rows": n_joined,
        "n_with_fwd_63d": n_with_ret63,
        "n_with_fwd_126d": n_with_ret126,
        "boot_draws": args.draws,
        "boot_seed": args.seed,
        "n_months_floor": N_MONTHS_FLOOR,
        "n_eff_shrink_floor": N_EFF_SHRINK_FLOOR,
        "revision_optimistic_note": (
            "ALL quad-conditioned cells carry revision_optimistic=true (P-D5-1): "
            "regime_history.parquet uses revised macro series with no ALFRED vintages. "
            "Quad-conditioned findings are research-only and carry a systematic upward "
            "bias in measured edge (the quads are 'known' only in hindsight)."
        ),
        "ruling_A7_note": (
            "Research surface only (ruling A7). These cells do NOT drive any trading card, "
            "conviction tilt, or badge. DL-2 (the decision-linkage gate) must pass before "
            "any tilt into sector_central is permitted."
        ),
        "ruling_A2_note": (
            "All CIs from whole-month date-block bootstrap (ruling A2). "
            "n_eff = n/h used ONLY for James-Stein shrinkage weight; "
            "never as Wilson interval input."
        ),
        "cells": {},
    }

    for outcome, outcome_label in [("fwd_ret", "forward_return"), ("rdd", "vol_residualized_maxdd")]:
        artifact["cells"][outcome_label] = {}
        for h_label in HORIZONS:
            print(f"[W4.4] Computing cells: outcome={outcome_label}, h={h_label} ...")
            cells = compute_cells(joined, outcome, h_label)
            artifact["cells"][outcome_label][h_label] = cells
            n_cells = len([c for c in cells if c.get("quad") != "pooled"])
            n_collapsed = sum(1 for c in cells if c.get("collapsed") and c.get("quad") != "pooled")
            n_ci_nonzero = len(verdict_ci_excludes_pooled(cells))
            print(f"[W4.4]   {outcome_label}/{h_label}: {n_cells} cells, "
                  f"{n_collapsed} collapsed, "
                  f"{n_ci_nonzero} with CI excluding pooled mean")

    # Summary verdict
    all_winners: list[dict] = []
    for outcome_label in artifact["cells"]:
        for h_label in artifact["cells"][outcome_label]:
            all_winners.extend(verdict_ci_excludes_pooled(artifact["cells"][outcome_label][h_label]))

    artifact["verdict_summary"] = {
        "n_cells_with_ci_excluding_pooled": len(all_winners),
        "winners": [
            {k: v for k, v in c.items() if k in (
                "family", "phase_v2", "quad", "n_months", "shrunk_mean",
                "phase_pooled_mean", "boot_ci_95", "revision_optimistic"
            )}
            for c in all_winners
        ],
        "honest_expectation": (
            "Per §6.5/§6.6 and ruling A7: most cells expected to be null — "
            "the n/cell is too small after phase×quad×family conditioning. "
            "Zero survivors is a valid publishable verdict."
        ),
    }

    # Write artifact
    out_path = os.path.join(args.out, f"conditional_cells_{epoch}.json")
    os.makedirs(args.out, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False, default=str)
    print(f"[W4.4] Artifact written: {out_path}")

    # Print verdict
    n_winners = len(all_winners)
    print(f"\n[W4.4] VERDICT: {n_winners} cell(s) with CI excluding the phase-pooled mean.")
    if n_winners == 0:
        print("[W4.4] → NULL RESULT — per §6.5, this is valid and publishable.")
        print("[W4.4] → DL-2 gate: cannot pass without at least one cell with CI excluding 0.")
    else:
        print("[W4.4] → WINNERS (all revision_optimistic=True — research surface only):")
        for w in all_winners:
            print(f"  {w['family']} | {w['phase_v2']} | {w['quad']} | "
                  f"shrunk={w.get('shrunk_mean')} CI={w.get('boot_ci_95')}")
        print("[W4.4] → DL-2 requires a further walk-forward conviction backtest before tilt wiring.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
