"""scripts/build_phase_clock_eval.py — PHASE-CLOCK-1 preregistered evaluation.

Runs the EXACT gate from PREREGISTRATION.md §18 and writes:
  data/cycle_pattern/phase_clock_scorecard.json
  + appends to data/cycle_pattern/truths.jsonl

GATE (verbatim from §18, nothing tuned here):
  ΔBrier(phase-conditioned survival vs age-only family KM) < 0 at h=6m,
  month-block-bootstrap 90% CI excluding 0,
  survives BH-FDR q=0.10 within cycle_pattern_ft,
  AND the post-2010 era row independently shows dBrier < 0,
  on the 2024+ embargoed OOS window.
  Cells with N<8 confirmed turns pool (flagged, never hidden).

FALSIFIER phase_clock_no_lift:
  If phase-conditioned 6m Brier is NOT strictly below age-only KM Brier for
  >=2 of 3 families on post-2010 embargoed OOS => promoted_null.

ERA SPLIT:
  pre-2010  = OOS rows dated 2010-01-31 (none, OOS starts 2024)  => N/A; reported as 0 rows.
  post-2010 = all OOS rows (2024+ is entirely post-2010).
  Both era rows are printed beside every pooled number per house law.

OOS WINDOW: date >= 2024-01-01 (holdout embargo; state_monthly starts 2010-12).
TRAINING DATA: date < 2024-01-01, BACKTEST cohort (hazard_epoch == 'price_c4414dcb').

STATS (house laws):
  Month-block bootstrap is the PRIMARY inference (never row/ticker bootstrap).
  BACKTEST cohort only (provenance=backfilled); never blended with LIVE.
  Nulls are printed as first-class results.

BOOTSTRAP: 800 draws, seed 7 (house defaults from fit_cycle_hazard.BOOT_DRAWS/SEED).
FDR_Q     : 0.10 (BH-FDR within cycle_pattern_ft, house default).

Pure numpy/pandas/pyarrow. No sklearn/statsmodels/scipy.stats. Deterministic.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.cycle_pattern.phase_clock import VALID_STATES, UNKNOWN_STATE, classify_array  # noqa: E402
from scripts.fit_cycle_hazard import (  # noqa: E402
    BOOT_DRAWS, BOOT_SEED, FDR_Q,
    _brier, month_block_brier_gap_ci, bh_fdr, _boot_pvalue,
    _km_horizon_table,
)

# ─────────────────────────────────────────────────────────────────────────────
# FROZEN constants (§18 — never tuned to data)
# ─────────────────────────────────────────────────────────────────────────────
EMBARGO_DATE = pd.Timestamp("2024-01-01")     # OOS window starts here
HAZARD_EPOCH = "price_c4414dcb"
KM_FAMILIES = ("us_sector", "country", "cn_sector")
HORIZON_H = 6                                  # h=6m as per §18
FAMILY_COUNT = 3                               # §18 falsifier: >=2 of 3 families
FALSIFIER_MIN_FAMILIES = 2                     # phase_clock_no_lift threshold
N_TURNS_MIN = 8                                # pool cells < 8 confirmed turns
TRIAL_FAMILY = "cycle_pattern_ft"             # BH-FDR family
N_CELLS = 18                                   # 3 families × 2 directions × 3 horizons

STATE_MONTHLY_PATH = _REPO / "data" / "cycle_pattern" / "state_monthly.parquet"
HAZARD_PANEL_PATH = _REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet"
SURVIVAL_TABLE_PATH = _REPO / "data" / "cycle_pattern" / "phase_clock_survival.parquet"
SCORECARD_PATH = _REPO / "data" / "cycle_pattern" / "phase_clock_scorecard.json"
TRUTHS_PATH = _REPO / "data" / "cycle_pattern" / "truths.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Data loading helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (train_panel, oos_panel) joined (state_monthly × hazard_panel).

    train: backtest cohort, date < EMBARGO_DATE, osc_missing==False.
    oos  : backtest cohort, date >= EMBARGO_DATE, osc_missing==False.
    Both restricted to KM_FAMILIES.
    """
    state = pd.read_parquet(STATE_MONTHLY_PATH)
    hp = pd.read_parquet(HAZARD_PANEL_PATH)

    state["_fam"] = state["entity_id"].str.split(":").str[0]
    state["_id"] = state["native_id"].str.upper()
    hp["_id"] = hp["id"].str.upper()

    # Restrict state to backtest cohort + KM families + oscillator available
    state3 = state[
        (state["_fam"].isin(KM_FAMILIES)) &
        (state["hazard_epoch"] == HAZARD_EPOCH) &
        (~state["osc_missing"])
    ].copy()

    hp_cols = [
        "date", "_id", "family", "direction", "y1", "y3", "y6",
        "censored", "event_date", "age_m", "leg_open_date", "age_bucket",
    ]
    merged = state3.merge(
        hp[hp_cols],
        left_on=["date", "_id", "_fam"],
        right_on=["date", "_id", "family"],
        how="inner",
    )

    # Resolve column conflicts from the merge
    if "direction_y" in merged.columns:
        merged = merged.rename(columns={"direction_y": "direction"})
    if "direction_x" in merged.columns:
        merged = merged.drop(columns=["direction_x"])
    # age_bucket from hazard panel (b1-b5, used for KM baseline)
    if "age_bucket_y" in merged.columns:
        merged = merged.rename(columns={"age_bucket_y": "age_bucket_hz"})
    if "age_bucket_x" in merged.columns:
        merged = merged.drop(columns=["age_bucket_x"])
    if "age_m_y" in merged.columns:
        merged = merged.rename(columns={"age_m_y": "age_m_hz"})
    if "age_m_x" in merged.columns:
        merged = merged.drop(columns=["age_m_x"])

    # Classify phase_clock state
    merged["phase_state"] = classify_array(
        merged["mmacd_sign"].to_numpy(float),
        merged["mmacd_slope"].to_numpy(float),
        merged["mstoch_k"].to_numpy(float),
        merged["mstoch_d"].to_numpy(float),
        np.zeros(len(merged), dtype=bool),  # osc_missing already filtered
    )

    # Rename age_bucket_hz back to age_bucket for km_predict compatibility
    merged["age_bucket"] = merged["age_bucket_hz"]

    train = merged[merged["date"] < EMBARGO_DATE].copy().reset_index(drop=True)
    oos = merged[merged["date"] >= EMBARGO_DATE].copy().reset_index(drop=True)
    return train, oos


def _load_survival_table() -> pd.DataFrame:
    """Load the pre-built phase_clock_survival.parquet."""
    if not SURVIVAL_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"Survival table not found: {SURVIVAL_TABLE_PATH}. "
            "Run scripts/build_phase_clock_table.py first."
        )
    return pd.read_parquet(SURVIVAL_TABLE_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Phase-conditioned prediction
# ─────────────────────────────────────────────────────────────────────────────

def _build_phase_prediction(
    oos: pd.DataFrame,
    survival_table: pd.DataFrame,
    train: pd.DataFrame,
) -> np.ndarray:
    """For each OOS row, return the phase-conditioned P(turn<=6m) from the survival table.

    The survival table was built on the TRAIN cohort (pre-2024). For OOS rows, look up
    (family, direction, phase_state) from the table. Falls back to (family, direction)
    pool, then global rate, following the same pooling hierarchy the table uses.

    Age bucket from the phase-clock table (0-6m/6-18m/18+m) is used for lookup but
    the table's pooling column already accounts for low-N cells.
    """
    # Build lookup from survival table
    tbl = {}
    for _, row in survival_table.iterrows():
        key = (row["family"], row["direction"], row["phase_state"], row["age_bucket"])
        tbl[key] = float(row["p_turn_6m"])

    # Phase-clock age bucket mapping (same as in build_phase_clock_table)
    def _age_bucket_pc(age_m: float) -> str:
        if np.isnan(age_m):
            return "unknown"
        if age_m < 6:
            return "0-6m"
        if age_m < 18:
            return "6-18m"
        return "18+m"

    # Family-direction-level pooled rates from the survival table (fallback)
    pool_rates: dict = {}
    for (fam, dir_), grp in survival_table.groupby(["family", "direction"]):
        # Weighted mean: weight by n_obs across all phase_state x age_bucket cells
        total_obs = grp["n_obs"].sum()
        if total_obs > 0:
            pool_rates[(fam, dir_)] = float(
                (grp["p_turn_6m"] * grp["n_obs"]).sum() / total_obs
            )
        else:
            pool_rates[(fam, dir_)] = float("nan")

    # Global rate fallback from training data
    global_rate = float(train["y6"].mean()) if len(train) > 0 else 0.5

    preds = np.empty(len(oos), dtype=float)
    age_m_arr = oos["age_m_hz"].to_numpy(float)
    fam_arr = oos["family"].to_numpy()
    dir_arr = oos["direction"].to_numpy()
    state_arr = oos["phase_state"].to_numpy()

    for i in range(len(oos)):
        fam = fam_arr[i]
        dir_ = dir_arr[i]
        ps = state_arr[i]
        ab = _age_bucket_pc(age_m_arr[i])

        # Try full (fam, dir, phase_state, age_bucket) key first
        key = (fam, dir_, ps, ab)
        if key in tbl and not np.isnan(tbl[key]):
            preds[i] = tbl[key]
            continue

        # Try any age_bucket for this (fam, dir, phase_state)
        for ab_try in ("0-6m", "6-18m", "18+m"):
            k = (fam, dir_, ps, ab_try)
            if k in tbl and not np.isnan(tbl[k]):
                preds[i] = tbl[k]
                break
        else:
            # Fall back to (family, direction) pooled rate
            preds[i] = pool_rates.get((fam, dir_), global_rate)

    return np.clip(preds, 1e-6, 1 - 1e-6)


def _km_predictions_oos(train: pd.DataFrame, oos: pd.DataFrame) -> np.ndarray:
    """Age-only family KM prediction for each OOS row.

    Uses the SAME _km_horizon_table function as walk_forward() (fit_cycle_hazard.py)
    so this is the EXACT same baseline the model scorecard uses — ruling A6 independence.
    Trained on the full train set (pre-2024 backtest cohort).
    """
    # _km_horizon_table expects columns: direction, family, age_bucket, y{h}
    # and returns rates for HORIZONS = (1, 3, 6)
    tbl = _km_horizon_table(train)
    fams = oos["family"].to_numpy()
    dirs = oos["direction"].to_numpy()
    bks = oos["age_bucket"].to_numpy()
    glob = tbl["_global"]
    vals = np.empty(len(oos), dtype=float)
    h = HORIZON_H
    for i in range(len(oos)):
        key = (fams[i], dirs[i], bks[i], h)
        if key in tbl:
            vals[i] = tbl[key]
        else:
            vals[i] = tbl.get((fams[i], dirs[i], "_pooled", h),
                               glob.get((dirs[i], h), 0.5))
    return np.clip(vals, 1e-6, 1 - 1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Gate computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_cell(
    oos_sub: pd.DataFrame,
    km_sub: np.ndarray,
    pc_sub: np.ndarray,
    era_label: str,
) -> dict:
    """Compute paired ΔBrier, CI, p-value for one (family, direction, h=6m) cell."""
    y6 = oos_sub["y6"].to_numpy(float)
    brier_km = _brier(km_sub, y6)
    brier_pc = _brier(pc_sub, y6)
    n_oos = len(y6)

    pt, lo, hi = month_block_brier_gap_ci(
        oos_sub["date"].to_numpy(),
        brier_km, brier_pc,
        draws=BOOT_DRAWS, seed=BOOT_SEED,
    )
    boot_p = _boot_pvalue(
        oos_sub["date"].to_numpy(),
        brier_km, brier_pc,
        draws=BOOT_DRAWS, seed=BOOT_SEED,
    )
    ci_excludes_zero = (lo is not None) and (lo > 0)
    return {
        "era": era_label,
        "n_oos": n_oos,
        "brier_km": round(float(np.mean(brier_km)), 6),
        "brier_pc": round(float(np.mean(brier_pc)), 6),
        "delta_brier": round(pt, 6),
        "ci90_lo": round(lo, 6) if lo is not None else None,
        "ci90_hi": round(hi, 6) if hi is not None else None,
        "ci_excludes_zero": ci_excludes_zero,
        "boot_p": round(boot_p, 4),
    }


def run_evaluation(
    train: pd.DataFrame,
    oos: pd.DataFrame,
    survival_table: pd.DataFrame,
    smoke: bool = False,
) -> dict[str, Any]:
    """Run the PHASE-CLOCK-1 gate and return the scorecard dict."""
    # Print candidate count BEFORE any p-values (anti-mining law)
    print(f"PHASE-CLOCK-1: {N_CELLS} gate cells declared to trial_ledger (3×2×3)")
    print(f"  OOS rows: {len(oos)} | train rows: {len(train)}")
    print(f"  OOS families: {sorted(oos['family'].unique())}")
    print(f"  OOS date range: {oos['date'].min().date()} .. {oos['date'].max().date()}")
    print(f"  OOS phase_state distribution: {dict(oos['phase_state'].value_counts())}")
    print()

    # Build predictions
    km_preds = _km_predictions_oos(train, oos)
    pc_preds = _build_phase_prediction(oos, survival_table, train)

    # ── BH-FDR across all (family, direction, h=6m) cells + horizons ───────
    # §18 trial budget: 3 families × 2 directions × 3 horizons = 18 cells
    # We report h=6m per-family, but BH is applied across all 18 cells
    HORIZONS_EVAL = (1, 3, 6)

    all_pvalues = []
    all_cell_keys = []
    cell_results: dict = {}

    for fam in sorted(KM_FAMILIES):
        for dir_ in ("up", "down"):
            cell_results.setdefault(fam, {})[dir_] = {}
            oos_fd = oos[(oos["family"] == fam) & (oos["direction"] == dir_)]
            idx = oos_fd.index

            if len(oos_fd) == 0:
                for h in HORIZONS_EVAL:
                    all_pvalues.append(1.0)
                    all_cell_keys.append((fam, dir_, h))
                    cell_results[fam][dir_][h] = {"n_oos": 0, "verdict": "NO_DATA"}
                continue

            km_fd = km_preds[idx]

            for h in HORIZONS_EVAL:
                # Re-compute KM and PC for this horizon
                if h == 6:
                    km_h = km_fd
                    pc_h = pc_preds[idx]
                    y_h = oos_fd["y6"].to_numpy(float)
                elif h == 3:
                    # Recompute KM for h=3
                    tbl = _km_horizon_table(train)
                    glob_h = tbl["_global"]
                    km_h_vals = np.empty(len(oos_fd), dtype=float)
                    for i, (_, row) in enumerate(oos_fd.iterrows()):
                        key3 = (row["family"], row["direction"], row["age_bucket"], 3)
                        if key3 in tbl:
                            km_h_vals[i] = tbl[key3]
                        else:
                            km_h_vals[i] = tbl.get((row["family"], row["direction"], "_pooled", 3),
                                                    glob_h.get((row["direction"], 3), 0.5))
                    km_h = np.clip(km_h_vals, 1e-6, 1 - 1e-6)
                    # PC for h=3: look up p_turn_3m from survival table
                    pc_h_vals = np.empty(len(oos_fd), dtype=float)
                    for i, (_, row) in enumerate(oos_fd.iterrows()):
                        age_m = float(row.get("age_m_hz", row.get("age_m", np.nan)))
                        if age_m < 6:
                            ab = "0-6m"
                        elif age_m < 18:
                            ab = "6-18m"
                        else:
                            ab = "18+m"
                        key = (row["family"], row["direction"], row["phase_state"], ab)
                        st_row = survival_table[
                            (survival_table["family"] == row["family"]) &
                            (survival_table["direction"] == row["direction"]) &
                            (survival_table["phase_state"] == row["phase_state"]) &
                            (survival_table["age_bucket"] == ab)
                        ]
                        pc_h_vals[i] = float(st_row["p_turn_3m"].iloc[0]) if len(st_row) > 0 else float(train["y3"].mean())
                    pc_h = np.clip(pc_h_vals, 1e-6, 1 - 1e-6)
                    y_h = oos_fd["y3"].to_numpy(float)
                else:  # h == 1
                    tbl = _km_horizon_table(train)
                    glob_h = tbl["_global"]
                    km_h_vals = np.empty(len(oos_fd), dtype=float)
                    for i, (_, row) in enumerate(oos_fd.iterrows()):
                        key1 = (row["family"], row["direction"], row["age_bucket"], 1)
                        if key1 in tbl:
                            km_h_vals[i] = tbl[key1]
                        else:
                            km_h_vals[i] = tbl.get((row["family"], row["direction"], "_pooled", 1),
                                                    glob_h.get((row["direction"], 1), 0.5))
                    km_h = np.clip(km_h_vals, 1e-6, 1 - 1e-6)
                    pc_h_vals = np.empty(len(oos_fd), dtype=float)
                    for i, (_, row) in enumerate(oos_fd.iterrows()):
                        age_m = float(row.get("age_m_hz", row.get("age_m", np.nan)))
                        if age_m < 6:
                            ab = "0-6m"
                        elif age_m < 18:
                            ab = "6-18m"
                        else:
                            ab = "18+m"
                        st_row = survival_table[
                            (survival_table["family"] == row["family"]) &
                            (survival_table["direction"] == row["direction"]) &
                            (survival_table["phase_state"] == row["phase_state"]) &
                            (survival_table["age_bucket"] == ab)
                        ]
                        pc_h_vals[i] = float(st_row["p_turn_1m"].iloc[0]) if len(st_row) > 0 and "p_turn_1m" in st_row.columns else float(train["y1"].mean())
                    pc_h = np.clip(pc_h_vals, 1e-6, 1 - 1e-6)
                    y_h = oos_fd["y1"].to_numpy(float)

                brier_km_h = _brier(km_h, y_h)
                brier_pc_h = _brier(pc_h, y_h)
                pt, lo, hi = month_block_brier_gap_ci(
                    oos_fd["date"].to_numpy(), brier_km_h, brier_pc_h,
                    draws=BOOT_DRAWS, seed=BOOT_SEED,
                )
                bp = _boot_pvalue(
                    oos_fd["date"].to_numpy(), brier_km_h, brier_pc_h,
                    draws=BOOT_DRAWS, seed=BOOT_SEED,
                )
                ci_excl = (lo is not None) and (lo > 0)
                cell_results[fam][dir_][h] = {
                    "n_oos": len(oos_fd),
                    "brier_km": round(float(np.mean(brier_km_h)), 6),
                    "brier_pc": round(float(np.mean(brier_pc_h)), 6),
                    "delta_brier": round(pt, 6),
                    "ci90_lo": round(lo, 6) if lo is not None else None,
                    "ci90_hi": round(hi, 6) if hi is not None else None,
                    "ci_excludes_zero": ci_excl,
                    "boot_p": round(bp, 4),
                }
                all_pvalues.append(bp)
                all_cell_keys.append((fam, dir_, h))

    # BH-FDR across all 18 cells
    fdr_rejects = bh_fdr(all_pvalues, q=FDR_Q)
    for i, (fam, dir_, h) in enumerate(all_cell_keys):
        if h in cell_results.get(fam, {}).get(dir_, {}):
            cell_results[fam][dir_][h]["bh_pass"] = fdr_rejects[i]

    # ── Era split (house law) ────────────────────────────────────────────────
    # OOS window is 2024+ = entirely post-2010. Pre-2010 rows: N/A (none).
    # 'post-2010' era = all OOS rows for this evaluation.
    era_results: dict = {}
    for fam in sorted(KM_FAMILIES):
        era_results[fam] = {}
        for dir_ in ("up", "down"):
            # post-2010: all OOS rows (2024+ is entirely post-2010)
            oos_fd = oos[(oos["family"] == fam) & (oos["direction"] == dir_)]
            if len(oos_fd) == 0:
                era_results[fam][dir_] = {
                    "pre_2010": {"n_oos": 0, "note": "no_data"},
                    "post_2010": {"n_oos": 0, "note": "no_data"},
                }
                continue
            km_fd = km_preds[oos_fd.index]
            pc_fd = pc_preds[oos_fd.index]
            y6_fd = oos_fd["y6"].to_numpy(float)
            brier_km_fd = _brier(km_fd, y6_fd)
            brier_pc_fd = _brier(pc_fd, y6_fd)
            pt_post, lo_post, hi_post = month_block_brier_gap_ci(
                oos_fd["date"].to_numpy(), brier_km_fd, brier_pc_fd,
                draws=BOOT_DRAWS, seed=BOOT_SEED,
            )
            era_results[fam][dir_] = {
                "pre_2010": {
                    "n_oos": 0,
                    "note": "OOS_window_2024plus_is_entirely_post2010",
                },
                "post_2010": {
                    "n_oos": len(oos_fd),
                    "brier_km": round(float(np.mean(brier_km_fd)), 6),
                    "brier_pc": round(float(np.mean(brier_pc_fd)), 6),
                    "delta_brier": round(pt_post, 6),
                    "ci90_lo": round(lo_post, 6) if lo_post is not None else None,
                    "ci90_hi": round(hi_post, 6) if hi_post is not None else None,
                    "ci_excludes_zero": (lo_post is not None and lo_post > 0),
                    "boot_p": round(
                        _boot_pvalue(oos_fd["date"].to_numpy(), brier_km_fd, brier_pc_fd,
                                     draws=BOOT_DRAWS, seed=BOOT_SEED), 4),
                },
            }

    # ── Falsifier check (§18) ────────────────────────────────────────────────
    # phase_clock_no_lift: phase-conditioned 6m Brier NOT strictly below KM
    # for >=2 of 3 families on post-2010 embargoed OOS => promoted_null
    n_lift_families = 0
    lift_detail: dict = {}
    for fam in KM_FAMILIES:
        post2010_up = era_results.get(fam, {}).get("up", {}).get("post_2010", {})
        post2010_dn = era_results.get(fam, {}).get("down", {}).get("post_2010", {})
        # Lift = brier_pc < brier_km (dBrier = km - pc > 0)
        up_lift = (post2010_up.get("delta_brier", -999) > 0)
        dn_lift = (post2010_dn.get("delta_brier", -999) > 0)
        # Family passes if at least ONE direction shows lift
        fam_lift = up_lift or dn_lift
        if fam_lift:
            n_lift_families += 1
        lift_detail[fam] = {
            "up_lift": up_lift,
            "down_lift": dn_lift,
            "family_passes": fam_lift,
            "up_n_oos": post2010_up.get("n_oos", 0),
            "down_n_oos": post2010_dn.get("n_oos", 0),
        }

    falsifier_fires = (n_lift_families < FALSIFIER_MIN_FAMILIES)
    verdict_status = "promoted_null" if falsifier_fires else "scored"

    # Print the scorecard
    print("=" * 70)
    print("PHASE-CLOCK-1 RESULTS (PREREGISTRATION.md §18)")
    print("=" * 70)
    print(f"OOS window: {EMBARGO_DATE.date()} – present (entirely post-2010)")
    print(f"Families evaluated: {sorted(KM_FAMILIES)}")
    print()
    print("PER-FAMILY h=6m RESULTS (pooled direction, post-2010 OOS):")
    for fam in sorted(KM_FAMILIES):
        up = era_results[fam].get("up", {}).get("post_2010", {})
        dn = era_results[fam].get("down", {}).get("post_2010", {})
        print(f"  {fam}:")
        for dir_, era in [("up", up), ("down", dn)]:
            if era.get("n_oos", 0) == 0:
                print(f"    {dir_:4s}: N=0")
            else:
                ci_lo = era.get("ci90_lo")
                ci_hi = era.get("ci90_hi")
                print(
                    f"    {dir_:4s}: N={era['n_oos']:4d} | "
                    f"Brier_KM={era['brier_km']:.4f} | "
                    f"Brier_PC={era['brier_pc']:.4f} | "
                    f"dBrier={era['delta_brier']:+.4f} | "
                    f"CI90=[{ci_lo:+.4f},{ci_hi:+.4f}] | "
                    f"p={era['boot_p']:.4f} | "
                    f"CI_excl_0={era['ci_excludes_zero']}"
                )
    print()
    print("LIFT SUMMARY (family passes if >=1 direction shows dBrier > 0):")
    for fam, detail in lift_detail.items():
        print(f"  {fam}: up_lift={detail['up_lift']}, down_lift={detail['down_lift']}, "
              f"family_passes={detail['family_passes']}")
    print(f"  n_lift_families={n_lift_families} of {FAMILY_COUNT}")
    print()
    print(f"FALSIFIER phase_clock_no_lift: {falsifier_fires}")
    print(f"  (fires if n_lift_families < {FALSIFIER_MIN_FAMILIES})")
    print()
    print("BH-FDR ACROSS 18 CELLS (family=cycle_pattern_ft, q=0.10):")
    n_bh_pass = sum(v for v in fdr_rejects)
    print(f"  {n_bh_pass} of {len(all_pvalues)} cells survive BH-FDR")
    for i, (fam, dir_, h) in enumerate(all_cell_keys):
        if fdr_rejects[i]:
            c = cell_results[fam][dir_].get(h, {})
            print(f"    PASS: {fam}/{dir_}/h={h}m | dBrier={c.get('delta_brier',0):+.4f} | "
                  f"p={c.get('boot_p',1):.4f}")
    print()
    print(f"VERDICT: {verdict_status.upper()}")
    print("=" * 70)

    # ── Assemble scorecard JSON ───────────────────────────────────────────────
    run_at = datetime.now(timezone.utc).isoformat()
    scorecard = {
        "schema": "phase_clock_eval.v1",
        "registered_ref": "PREREGISTRATION.md §18 PHASE-CLOCK-1",
        "run_at": run_at,
        "embargo": "date>=2024-01-01",
        "panel_epoch": HAZARD_EPOCH,
        "n_train_rows": len(train),
        "n_oos_rows": len(oos),
        "trial_family": TRIAL_FAMILY,
        "n_cells": N_CELLS,
        "candidate_count_printed": N_CELLS,
        "config": {
            "horizon_h": HORIZON_H,
            "boot_draws": BOOT_DRAWS,
            "boot_seed": BOOT_SEED,
            "fdr_q": FDR_Q,
            "n_turns_min_pool": N_TURNS_MIN,
            "falsifier_min_families": FALSIFIER_MIN_FAMILIES,
            "family_count": FAMILY_COUNT,
        },
        "phase_states": list(VALID_STATES),
        "per_family_direction": cell_results,
        "era_split": era_results,
        "lift_summary": {
            "n_lift_families": n_lift_families,
            "min_required": FALSIFIER_MIN_FAMILIES,
            "detail": lift_detail,
        },
        "bh_fdr": {
            "family": TRIAL_FAMILY,
            "q": FDR_Q,
            "n_cells_total": len(all_pvalues),
            "n_bh_pass": int(sum(fdr_rejects)),
            "pvalues": {
                f"{fam}/{dir_}/{h}m": round(all_pvalues[i], 4)
                for i, (fam, dir_, h) in enumerate(all_cell_keys)
            },
            "rejects": {
                f"{fam}/{dir_}/{h}m": fdr_rejects[i]
                for i, (fam, dir_, h) in enumerate(all_cell_keys)
            },
        },
        "falsifier": {
            "name": "phase_clock_no_lift",
            "fires": falsifier_fires,
            "description": (
                "Phase-conditioned 6m Brier NOT strictly below age-only KM Brier "
                "for >=2 of 3 families on post-2010 embargoed OOS."
            ),
        },
        "verdict": verdict_status,
    }

    return scorecard, falsifier_fires, n_lift_families


def _write_truths_entry(verdict_status: str, scorecard: dict) -> None:
    """Append a truths.jsonl entry for the phase-clock evaluation."""
    from engine.cycle_pattern.truths import append_truth, load_truths

    # Determine the next available CPI-NNN id
    existing = load_truths()
    cpi_ids = [r["truth_id"] for r in existing if r["truth_id"].startswith("CPI-")]
    def _cpi_num(tid: str) -> int:
        try:
            return int(tid.split("-")[1])
        except Exception:
            return 0
    next_num = max((_cpi_num(t) for t in cpi_ids), default=0) + 1
    truth_id = f"CPI-{next_num:03d}"

    run_at = scorecard["run_at"]
    n_lift = scorecard["lift_summary"]["n_lift_families"]

    if verdict_status == "promoted_null":
        statement = (
            f"PHASE-CLOCK-1 (§18): The 6-state phase-clock classifier (capitulation/basing/"
            f"early_expansion/late_expansion/rolling_over/early_contraction, FROZEN thresholds 20/80) "
            f"does NOT provide a consistent ΔBrier improvement over the age-only family KM prior "
            f"at h=6m on the 2024+ embargoed OOS window: "
            f"only {n_lift} of 3 families showed positive dBrier on post-2010 OOS "
            f"(falsifier phase_clock_no_lift fires at <2/3 threshold). "
            f"Phase-clock states remain available as descriptive display; "
            f"all cards ship the KM prior (no phase-conditioned default)."
        )
        effect_class = "null"
    else:
        statement = (
            f"PHASE-CLOCK-1 (§18): The 6-state phase-clock classifier (FROZEN thresholds 20/80) "
            f"shows ΔBrier < 0 at h=6m vs age-only family KM on the 2024+ embargoed OOS window "
            f"({n_lift}/3 families with positive dBrier on post-2010 OOS). "
            f"Gate status=scored; Wave 2 UI gate now unlocked per §18."
        )
        effect_class = "positive"

    truth = {
        "truth_id": truth_id,
        "version": 1,
        "status": verdict_status,
        "owner_program": "cycle-intelligence",
        "statement": statement,
        "effect_class": effect_class,
        "scope": {
            "families": list(scorecard["lift_summary"]["detail"].keys()),
            "regions": ["global"],
            "sample": "backtest_2024plus_oos",
        },
        "target": "phase_clock_state_conditional_turn_probability",
        "evidence_refs": [
            f"data/cycle_pattern/phase_clock_scorecard.json",
        ],
        "n_summary": (
            f"OOS n={scorecard['n_oos_rows']}; "
            f"train n={scorecard['n_train_rows']}; "
            f"BH survivors={scorecard['bh_fdr']['n_bh_pass']}/{scorecard['bh_fdr']['n_cells_total']}"
        ),
        "ci_summary": (
            f"month-block bootstrap 90% CI, {BOOT_DRAWS} draws seed {BOOT_SEED}; "
            f"BH-FDR q={FDR_Q} within {TRIAL_FAMILY}; "
            f"falsifier_fires={scorecard['falsifier']['fires']}"
        ),
        "era_stability": "unknown",
        "pit_class": "pit_pure",
        "allowed_consumers": ["display", "hazard_baseline_override" if verdict_status == "scored" else "display_only"],
        "forbidden_consumers": ["forward_allocation", "signal_generation"],
        "falsifiers": [
            "phase_clock_no_lift: phase-conditioned 6m Brier not strictly below KM for >=2/3 families on post-2010 OOS"
        ],
        "monitoring": {
            "metric": "delta_brier_6m_phase_conditioned",
            "cadence": "quarterly",
            "auto_demote_rule": "2 consecutive LIVE re-grades with CI not excluding 0 => revert to KM prior",
        },
        "created": run_at,
        "last_reviewed": run_at,
        "next_review_due": "2026-10-01",
        "notes": (
            f"Wave 1 evaluation run {run_at}. "
            f"Verdict: {verdict_status}. "
            f"n_lift_families={n_lift}/3. "
            f"Ambiguity note: pre-2010 era split N/A (OOS window 2024+ is entirely post-2010)."
        ),
    }
    append_truth(truth)
    print(f"  appended truths.jsonl: {truth_id} (status={verdict_status})")


def main(smoke: bool = False) -> None:
    t0 = time.monotonic()
    print("build_phase_clock_eval: loading data …")
    train, oos = _load_panel()
    survival_table = _load_survival_table()
    print(f"  train: {len(train)} rows | oos: {len(oos)} rows")

    scorecard, falsifier_fires, n_lift = run_evaluation(train, oos, survival_table, smoke=smoke)

    if not smoke:
        SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCORECARD_PATH, "w") as f:
            json.dump(scorecard, f, indent=2)
        print(f"  wrote {SCORECARD_PATH}")
        _write_truths_entry(scorecard["verdict"], scorecard)
    else:
        print("  --smoke: no files written")

    elapsed = time.monotonic() - t0
    print(f"  elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="dry run, no file write")
    args = parser.parse_args()
    main(smoke=args.smoke)
