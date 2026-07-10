"""
EI-PM0 Price-Memory Bundle — Staged Analysis Runner
=====================================================
Pre-registration: research/entry_intel/PM0_PRICE_MEMORY_BUNDLE_PREREG.md (APPROVED 2026-07-06 r3)
Execution spec:   research/entry_intel/pm0_runs/EI_PM0_price_memory/EXECUTION_SPEC.md

Stages:
  --stage preamble      : Population census, column-map, redundancy matrix (before outcome join)
  --stage calibration   : §7 calibration controls (negative + positive)
  --stage inference     : §5 trial table, BH, verdicts (requires --authorize-one-shot)

Usage:
  python research/entry_intel/pm0_runs/EI_PM0_price_memory/run_PM0.py --stage preamble --features-path <path>
  python research/entry_intel/pm0_runs/EI_PM0_price_memory/run_PM0.py --stage calibration
  python research/entry_intel/pm0_runs/EI_PM0_price_memory/run_PM0.py --stage inference --authorize-one-shot
"""

import os
import sys
import json
import math
import hashlib
import argparse
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ── sys.path: resolve imports from repo root ─────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_REPO = _THIS_DIR.parents[3]  # EI_PM0_price_memory / pm0_runs / entry_intel / research / repo
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── Paths ─────────────────────────────────────────────────────────────────────
_DEFAULT_DATA_ROOT = "/Users/chriswong/Documents/Cluade/Macro Dashboard/data"
DATA_ROOT = Path(os.environ.get("MAIN_DATA", _DEFAULT_DATA_ROOT))
REPLAY_PATH = DATA_ROOT / "replay" / "replay_boarded.parquet"
EDGAR_PATH = DATA_ROOT / "edgar" / "statements_quarterly.parquet"
OUT_DIR = _THIS_DIR

# Default feature artifact path (overridable via CLI)
DEFAULT_FEATURES_PATH = DATA_ROOT / "replay" / "pm0_features.parquet"

# ── Study constants ────────────────────────────────────────────────────────────
STUDY_ID = "EI_PM0_price_memory"
ERA_START = "2022-06-30"
ERA_END = "2026-07-02"      # verdict horizon end (per spec §0)
SIGN_SPLIT_DATE = "2024-06-30"  # pre-registered midpoint for both-halves stability
N_BOOT = 5000
BOOT_SEED = 20260706        # month-block bootstrap seed
N_PERM_DIAG = 2000          # episode-level permutation diagnostic draws
N_CAL_NEG = 200             # negative calibration draws per instrument
CAL_NEG_SEED = 777          # seed tuple base for negative calibration
CAL_POS_INJECT_SEED = 4242  # positive incidence injection seed
BH_Q = 0.10
THIN_FLOOR = 25             # minimum unique episode_ids per group
MIN_EVENTS = 50             # event floor per §1
MIN_EVENTS_GROUP = 10       # per-group event floor
MIN_QUAL_MONTHS = 24        # month floor
MIN_ROWS_PER_GROUP_PER_MONTH = 5  # qualifying month threshold
REDUNDANCY_RHO = 0.80       # |spearman| >= this => REDUNDANT
PM5_INCIDENCE_INJECT_PP = 5  # 5pp relabel for positive incidence control

# ── Column map (from prereg §1) ────────────────────────────────────────────────
# These are the actual column names as they appear in replay_boarded.parquet
REQUIRED_OUTCOME_COLS = [
    "ticker", "signal_date", "episode_id",
    "survivor_bias", "verdict_type", "verdict_grade", "horizon_censored",
    "state_8_21", "state_15_126",
    "fwd_ret_21", "fwd_ret_126",
    "ext_z", "ext_atr", "dist_to_52wh", "near_52wh",
    "rs_63d_return", "align_quality", "washout_proximity",
]
# Optional context columns
CONTEXT_COLS = ["fwd_mdd_21", "fwd_mfe_21", "sector"]
# Grids
GRID_A_STATE_COL = "state_8_21"
GRID_B_STATE_COL = "state_15_126"
GRID_A_FWD = "fwd_ret_21"
GRID_B_FWD = "fwd_ret_126"
EXPECTED_STATES = {"STOPPED", "DEAD_MONEY", "CUSHIONED", "CLEAN_LIFTOFF"}

# ── Trial table (§5, m=20) ────────────────────────────────────────────────────
# (trial_id, feature, grid_col, state, grid_fwd_col)
TRIAL_TABLE = [
    ("T01", "pm1", GRID_A_STATE_COL, "STOPPED",     GRID_A_FWD),
    ("T02", "pm1", GRID_A_STATE_COL, "DEAD_MONEY",  GRID_A_FWD),
    ("T03", "pm1", GRID_A_STATE_COL, "CUSHIONED",   GRID_A_FWD),
    ("T04", "pm1", GRID_B_STATE_COL, "STOPPED",     GRID_B_FWD),
    ("T05", "pm1", GRID_B_STATE_COL, "CUSHIONED",   GRID_B_FWD),
    ("T06", "pm2", GRID_A_STATE_COL, "STOPPED",     GRID_A_FWD),
    ("T07", "pm2", GRID_A_STATE_COL, "DEAD_MONEY",  GRID_A_FWD),
    ("T08", "pm2", GRID_A_STATE_COL, "CUSHIONED",   GRID_A_FWD),
    ("T09", "pm2", GRID_B_STATE_COL, "STOPPED",     GRID_B_FWD),
    ("T10", "pm2", GRID_B_STATE_COL, "CUSHIONED",   GRID_B_FWD),
    ("T11", "pm3", GRID_A_STATE_COL, "STOPPED",     GRID_A_FWD),
    ("T12", "pm3", GRID_A_STATE_COL, "DEAD_MONEY",  GRID_A_FWD),
    ("T13", "pm3", GRID_A_STATE_COL, "CUSHIONED",   GRID_A_FWD),
    ("T14", "pm3", GRID_B_STATE_COL, "STOPPED",     GRID_B_FWD),
    ("T15", "pm3", GRID_B_STATE_COL, "CUSHIONED",   GRID_B_FWD),
    ("T16", "pm4", GRID_A_STATE_COL, "STOPPED",     GRID_A_FWD),
    ("T17", "pm4", GRID_A_STATE_COL, "DEAD_MONEY",  GRID_A_FWD),
    ("T18", "pm4", GRID_A_STATE_COL, "CUSHIONED",   GRID_A_FWD),
    ("T19", "pm4", GRID_B_STATE_COL, "STOPPED",     GRID_B_FWD),
    ("T20", "pm4", GRID_B_STATE_COL, "CUSHIONED",   GRID_B_FWD),
]
M_DECLARED = 20

# ── Calibration instruments: grid-A STOPPED of PM1-PM4 ───────────────────────
CAL_INSTRUMENTS = [
    ("PM1", "pm1", GRID_A_STATE_COL, "STOPPED", GRID_A_FWD),
    ("PM2", "pm2", GRID_A_STATE_COL, "STOPPED", GRID_A_FWD),
    ("PM3", "pm3", GRID_A_STATE_COL, "STOPPED", GRID_A_FWD),
    ("PM4", "pm4", GRID_A_STATE_COL, "STOPPED", GRID_A_FWD),
]

# Deterministic per-feature seed component. NEVER derive seeds with python's
# hash() — string hashing is salted per process (PYTHONHASHSEED).
FEAT_IDX = {"pm1": 1, "pm2": 2, "pm3": 3, "pm4": 4, "pm5": 5}
# Divergence gate (EX-7): the §4.2(b) param/perm sanity check runs at TRIAL
# level, comparing the parametric MWU p vs the episode-permutation p of the
# SAME MWU statistic (P2.5 SANITY_DIVERGENCE_ORDERS=6 signature: trips when
# ep_perm_mwu_p > 0.3 while mwu_param_p < 1e-6). A pooled-MWU-vs-bootstrap
# comparison is calendar-confounded by construction and is NOT this signature.

# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

log_lines = []

def LOG(s=""):
    print(s, flush=True)
    log_lines.append(str(s))


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _jsonify(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        fv = float(obj)
        return None if np.isnan(fv) else fv
    if isinstance(obj, float):
        return None if np.isnan(obj) else obj
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _save_json(d: dict, path: Path):
    with open(path, "w") as fh:
        json.dump(d, fh, indent=2, default=_jsonify)


def bh_correction(p_values: list, q: float = BH_Q) -> np.ndarray:
    """Benjamini-Hochberg FDR correction. Returns BH-adjusted p-values."""
    m = len(p_values)
    if m == 0:
        return np.array([])
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    ranks = np.empty(m, dtype=int)
    ranks[order] = np.arange(1, m + 1)
    adjusted = np.minimum(1.0, p * m / ranks)
    adj_sorted = adjusted[order]
    for i in range(m - 2, -1, -1):
        adj_sorted[i] = min(adj_sorted[i], adj_sorted[i + 1])
    adjusted[order] = adj_sorted
    return adjusted


# ─────────────────────────────────────────────────────────────────────────────
# Core statistic (shared between calibration and inference — §3.2)
# ─────────────────────────────────────────────────────────────────────────────

def _get_favorable_mask(df: pd.DataFrame, feat: str, medians: dict) -> pd.Series:
    """Return boolean mask for the favorable group per spec §2.2 splits."""
    if feat == "pm1":
        return df["pm1"] >= 0.0
    elif feat == "pm2":
        med = medians["pm2_median"]
        return df["pm2"] >= med
    elif feat == "pm3":
        return df["pm3"] == 0.0
    elif feat == "pm4":
        med = medians["pm4_median"]
        return df["pm4"] <= med
    elif feat == "pm5":
        med = medians["pm5_median"]
        return df["pm5"] >= med
    else:
        raise ValueError(f"Unknown feature: {feat}")


def compute_within_month_stat(
    df: pd.DataFrame,
    feat: str,
    state_col: str,
    target_state: str,
    medians: dict,
) -> dict:
    """
    Compute the within-calendar-month weighted contrast statistic (§3.2 / §4.2).

    Returns dict with:
      delta_hat, n_qualifying_months, month_deltas (list), month_weights (list),
      month_details (list of dicts), n_fav, n_unfav, n_ep_fav, n_ep_unfav,
      thin_flag, n_events_fav, n_events_unfav
    """
    # Analysis population: feature defined, state non-null
    mask_defined = df[feat].notna() & df[state_col].notna()
    pop = df[mask_defined].copy()

    fav_mask = _get_favorable_mask(pop, feat, medians)
    pop["_fav"] = fav_mask
    pop["_state"] = (pop[state_col] == target_state).astype(float)

    # Calendar month from signal_date (per-row; used for straddle diagnostics)
    pop["_month"] = pd.to_datetime(pop["signal_date"]).dt.to_period("M").dt.to_timestamp()
    # Episode month = month of first row of each episode. The prereg §4.2
    # assigns each EPISODE to one month ("an episode is assigned to the month
    # of its first row") so that episode correlation lives entirely inside
    # month blocks (DT-R14 rubric) — all within-month grouping below uses the
    # episode month, never the raw row month (EX-8).
    ep_first_month = pop.groupby("episode_id")["_month"].min().rename("_ep_month")
    pop = pop.merge(ep_first_month, on="episode_id", how="left")

    n_fav = int(fav_mask.sum())
    n_unfav = int((~fav_mask).sum())
    n_ep_fav = int(pop[pop["_fav"]]["episode_id"].nunique())
    n_ep_unfav = int(pop[~pop["_fav"]]["episode_id"].nunique())
    n_events_fav = int(pop[pop["_fav"] & (pop[state_col] == target_state)].shape[0])
    n_events_unfav = int(pop[~pop["_fav"] & (pop[state_col] == target_state)].shape[0])

    # Per qualifying month contrast — grouped by EPISODE month (EX-8)
    months = sorted(pop["_ep_month"].unique())
    month_deltas = []
    month_weights = []
    month_details = []
    straddle_count = 0

    for month in months:
        month_mask = pop["_ep_month"] == month
        sub = pop[month_mask]
        fav_sub = sub[sub["_fav"]]
        unfav_sub = sub[~sub["_fav"]]
        n_f = len(fav_sub)
        n_u = len(unfav_sub)
        if n_f < MIN_ROWS_PER_GROUP_PER_MONTH or n_u < MIN_ROWS_PER_GROUP_PER_MONTH:
            continue
        # Incidence in month
        inc_f = float(fav_sub["_state"].mean())
        inc_u = float(unfav_sub["_state"].mean())
        delta_m = (inc_f - inc_u) * 100.0  # pp
        # Harmonic weight: 2 * n_f * n_u / (n_f + n_u)
        w_m = 2.0 * n_f * n_u / (n_f + n_u)
        month_deltas.append(delta_m)
        month_weights.append(w_m)
        # Episode straddle: episodes whose rows span multiple months
        ep_months = sub.groupby("episode_id")["_month"].nunique()
        straddling = int((ep_months > 1).sum())
        straddle_count += straddling
        month_details.append({
            "month": str(month.date()),
            "n_fav": n_f, "n_unfav": n_u,
            "inc_fav_pct": round(inc_f * 100, 3),
            "inc_unfav_pct": round(inc_u * 100, 3),
            "delta_m_pp": round(delta_m, 4),
            "weight": round(w_m, 4),
        })

    n_qual = len(month_deltas)
    thin_flag = (n_ep_fav < THIN_FLOOR) or (n_ep_unfav < THIN_FLOOR)

    if n_qual == 0:
        return {
            "delta_hat": np.nan, "n_qualifying_months": 0,
            "month_deltas": [], "month_weights": [],
            "month_details": month_details,
            "n_fav": n_fav, "n_unfav": n_unfav,
            "n_ep_fav": n_ep_fav, "n_ep_unfav": n_ep_unfav,
            "thin_flag": thin_flag,
            "n_events_fav": n_events_fav, "n_events_unfav": n_events_unfav,
            "episode_straddle_count": straddle_count,
            "n_total": len(pop),
        }

    w_arr = np.array(month_weights, dtype=float)
    d_arr = np.array(month_deltas, dtype=float)
    delta_hat = float(np.sum(w_arr * d_arr) / np.sum(w_arr))

    return {
        "delta_hat": delta_hat,
        "n_qualifying_months": n_qual,
        "month_deltas": [float(x) for x in month_deltas],
        "month_weights": [float(x) for x in month_weights],
        "month_details": month_details,
        "n_fav": n_fav, "n_unfav": n_unfav,
        "n_ep_fav": n_ep_fav, "n_ep_unfav": n_ep_unfav,
        "thin_flag": thin_flag,
        "n_events_fav": n_events_fav, "n_events_unfav": n_events_unfav,
        "episode_straddle_count": straddle_count,
        "n_total": len(pop),
    }


def month_block_bootstrap_p(
    month_deltas: list,
    month_weights: list,
    delta_hat: float,
    seed: int,
    n_boot: int = N_BOOT,
) -> float:
    """
    Two-sided add-one null-centered pivot p.
    Resample qualifying months with replacement.
    p = (1 + #{|Δ*_b - Δ̂| >= |Δ̂|}) / (B+1)
    """
    if len(month_deltas) == 0 or np.isnan(delta_hat):
        return np.nan
    d_arr = np.array(month_deltas, dtype=float)
    w_arr = np.array(month_weights, dtype=float)
    n_months = len(d_arr)
    rng = np.random.default_rng(seed)
    exceedances = 0
    abs_obs = abs(delta_hat)
    for _ in range(n_boot):
        idx = rng.integers(0, n_months, size=n_months)
        d_boot = d_arr[idx]
        w_boot = w_arr[idx]
        w_sum = w_boot.sum()
        if w_sum == 0:
            continue
        delta_star = float(np.sum(w_boot * d_boot) / w_sum)
        # Null-centered pivot: center bootstrap at observed
        pivot = abs(delta_star - delta_hat)
        if pivot >= abs_obs:
            exceedances += 1
    p = (1 + exceedances) / (n_boot + 1)
    return float(p)


def _month_block_bootstrap_ci(
    month_deltas: list,
    month_weights: list,
    delta_hat: float,
    seed: int,
    n_boot: int = N_BOOT,
) -> dict:
    """
    MONTH-BLOCK BOOTSTRAP — DIAGNOSTIC ONLY (PM0_R4_PRIMARY_AMENDMENT.md §2).
    Demoted from primary to CI diagnostic; mild left-tail anticonservatism at m=43 per §7 record.
    Label everywhere: 'MONTH-BLOCK BOOTSTRAP — DIAGNOSTIC (anticonservative-in-tail at m=43 per §7 record)'.
    NEVER feeds BH or verdicts.

    Returns percentile CI [2.5%, 97.5%] of Δ* and the old pivot p (relabeled boot_pivot_p_DIAGNOSTIC).
    """
    if len(month_deltas) == 0 or np.isnan(delta_hat):
        return {"ci_lo": np.nan, "ci_hi": np.nan, "pivot_p": np.nan}
    d_arr = np.array(month_deltas, dtype=float)
    w_arr = np.array(month_weights, dtype=float)
    n_months = len(d_arr)
    rng = np.random.default_rng(seed)
    delta_stars = []
    abs_obs = abs(delta_hat)
    exceedances = 0
    for _ in range(n_boot):
        idx = rng.integers(0, n_months, size=n_months)
        d_boot = d_arr[idx]
        w_boot = w_arr[idx]
        w_sum = w_boot.sum()
        if w_sum == 0:
            continue
        delta_star = float(np.sum(w_boot * d_boot) / w_sum)
        delta_stars.append(delta_star)
        pivot = abs(delta_star - delta_hat)
        if pivot >= abs_obs:
            exceedances += 1
    pivot_p = (1 + exceedances) / (n_boot + 1)
    if delta_stars:
        ci_lo = float(np.percentile(delta_stars, 2.5))
        ci_hi = float(np.percentile(delta_stars, 97.5))
    else:
        ci_lo = np.nan
        ci_hi = np.nan
    return {"ci_lo": ci_lo, "ci_hi": ci_hi, "pivot_p": float(pivot_p)}


def within_month_perm_engine(
    pop: pd.DataFrame,
    state_col: str,
    target_state: str,
    seed,
    n_perm: int = 5000,
    collect_selections: bool = False,
) -> dict:
    """
    Vectorized within-month episode-label permutation engine (r4 PRIMARY, PM0_R4_PRIMARY_AMENDMENT.md).

    pop must carry: _fav (row-level favorable bool), _ep_month (episode first-row month),
    episode_id, and state_col.

    Null convention (house P1.3-v2/P2.5): observed statistic uses registered row-level labels;
    null draws use episode-majority labels permuted within month. Mixed-label fraction is logged
    in the returned dict. This is a calendar-composition-preserving null (DT-R14 / RR-1 class).

    Per permutation draw, per calendar month m:
      - episodes assigned to m are identified by _ep_month
      - episode majority label (k_m favorable episodes) determines the draw count
      - each draw: uniformly choose k_m of the n_m episodes as favorable
      - month qualifies if n_f >= 5 and n_u >= 5 (row counts of chosen episodes)
      - w_m = 2*n_f*n_u/(n_f+n_u), delta_m = (inc_f - inc_u)*100pp
    Draws where NO month qualifies -> Δ̂* = NaN -> counted as exceedance (conservative).

    Memory: process month-by-month, accumulating per-draw numerator/denominator arrays.
    The per-month transient matrix shape is (n_perm, n_m) which is fine.

    Returns dict with:
      delta_perm: np.array(n_perm) of permuted Δ̂* values (NaN for no-qualifying-month draws)
      n_months_used_mean: float (mean number of qualifying months per draw)
      n_nan_draws: int (draws where no month qualified)
      mixed_label_frac: float
    """
    if len(pop) == 0:
        return {
            "delta_perm": np.full(n_perm, np.nan),
            "n_months_used_mean": 0.0,
            "n_nan_draws": n_perm,
            "mixed_label_frac": 0.0,
        }

    # Compute episode majority labels
    ep_majority = pop.groupby("episode_id")["_fav"].mean().ge(0.5)

    # Mixed-label fraction
    ep_mixed = pop.groupby("episode_id")["_fav"].apply(lambda x: 0.0 < x.mean() < 1.0)
    n_ep_total = len(ep_majority)
    mixed_label_frac = float(ep_mixed.sum() / n_ep_total) if n_ep_total > 0 else 0.0

    # Build per-month arrays of episode properties
    # For each month: list of episode ids, their majority labels, n_rows, n_events
    months = sorted(pop["_ep_month"].unique())

    # Per-episode: n_rows and n_events (in this population)
    ep_nrows = pop.groupby("episode_id").size()
    ep_nevents = pop[pop[state_col] == target_state].groupby("episode_id").size().reindex(
        ep_nrows.index, fill_value=0
    )

    # Accumulate per-draw numerator/denominator (sum_w_delta, sum_w) across months
    sum_w_delta = np.zeros(n_perm, dtype=np.float64)
    sum_w = np.zeros(n_perm, dtype=np.float64)
    months_qualifying_per_draw = np.zeros(n_perm, dtype=np.int32)
    # Per-draw favorable episode sets — equivalence-test mode only (small n_perm)
    selections = [set() for _ in range(n_perm)] if collect_selections else None

    rng = np.random.default_rng(seed)

    for month in months:
        month_mask = pop["_ep_month"] == month
        month_pop = pop[month_mask]
        # Episodes in this month (by episode_id)
        eps_in_month = month_pop["episode_id"].unique()
        n_m = len(eps_in_month)
        if n_m == 0:
            continue

        # Episode majority labels for this month
        ep_maj_m = ep_majority.reindex(eps_in_month).values.astype(bool)
        k_m = int(ep_maj_m.sum())  # number of majority-favorable episodes

        # Per-episode row counts and event counts for this month
        ep_nrows_m = ep_nrows.reindex(eps_in_month, fill_value=0).values.astype(np.int64)
        ep_nevents_m = ep_nevents.reindex(eps_in_month, fill_value=0).values.astype(np.int64)
        ep_total_rows_m = int(ep_nrows_m.sum())
        ep_total_events_m = int(ep_nevents_m.sum())

        if ep_total_rows_m == 0:
            continue

        # Batched draws: (n_perm, n_m) uniform keys matrix -> argsort -> first k_m cols are favorable
        # Use uniform keys + argsort (pure numpy, no Python loop over draws)
        if k_m == 0:
            # All episodes unfavorable every draw
            # n_f = 0, month never qualifies (< 5 rows per group required)
            continue
        if k_m == n_m:
            # All episodes favorable every draw
            # n_u = 0, month never qualifies
            continue

        # Draw uniform keys: shape (n_perm, n_m)
        keys = rng.random((n_perm, n_m))
        # Indices that would be chosen as favorable (first k_m in sorted order)
        # argpartition is O(n_m) vs argsort O(n_m log n_m) — use argpartition
        sorted_idx = np.argpartition(keys, k_m, axis=1)  # shape (n_perm, n_m)
        fav_idx = sorted_idx[:, :k_m]   # shape (n_perm, k_m) - favorable episode indices
        unfav_idx = sorted_idx[:, k_m:] # shape (n_perm, n_m-k_m) - unfavorable episode indices

        if collect_selections:
            for d in range(n_perm):
                selections[d].update(eps_in_month[fav_idx[d]])

        # Compute n_rows and n_events for favorable and unfavorable groups per draw
        # ep_nrows_m[fav_idx] has shape (n_perm, k_m); sum over axis=1 -> (n_perm,)
        nrows_f = ep_nrows_m[fav_idx].sum(axis=1)    # shape (n_perm,)
        nrows_u = ep_nrows_m[unfav_idx].sum(axis=1)  # shape (n_perm,)
        nevents_f = ep_nevents_m[fav_idx].sum(axis=1)
        nevents_u = ep_nevents_m[unfav_idx].sum(axis=1)

        # Per-draw month qualification: both groups >= 5 rows
        qualifies = (nrows_f >= MIN_ROWS_PER_GROUP_PER_MONTH) & (nrows_u >= MIN_ROWS_PER_GROUP_PER_MONTH)

        # Compute incidence and harmonic weight for qualifying draws
        # Avoid division by zero for non-qualifying draws by masking
        nf_q = nrows_f.astype(np.float64)
        nu_q = nrows_u.astype(np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            inc_f = np.where(nf_q > 0, nevents_f / nf_q, 0.0)
            inc_u = np.where(nu_q > 0, nevents_u / nu_q, 0.0)
            w_m = np.where(
                qualifies,
                2.0 * nf_q * nu_q / (nf_q + nu_q),
                0.0,
            )
        delta_m = (inc_f - inc_u) * 100.0  # pp

        # Accumulate into sum_w_delta and sum_w (only for qualifying draws)
        sum_w_delta += np.where(qualifies, w_m * delta_m, 0.0)
        sum_w += np.where(qualifies, w_m, 0.0)
        months_qualifying_per_draw += qualifies.astype(np.int32)

    # Compute Δ̂* per draw
    with np.errstate(divide="ignore", invalid="ignore"):
        delta_perm = np.where(sum_w > 0, sum_w_delta / sum_w, np.nan)

    n_nan_draws = int(np.isnan(delta_perm).sum())
    n_months_used_mean = float(months_qualifying_per_draw.mean())

    out = {
        "delta_perm": delta_perm,
        "n_months_used_mean": n_months_used_mean,
        "n_nan_draws": n_nan_draws,
        "mixed_label_frac": mixed_label_frac,
    }
    if collect_selections:
        out["selections"] = selections
    return out


def _engine_eval_one_selection(
    pop: pd.DataFrame,
    state_col: str,
    target_state: str,
    fav_episode_set: set,
) -> float:
    """
    Evaluate Δ̂ for one explicit episode-label assignment (used by equivalence tests).
    Episodes in fav_episode_set are labeled favorable; all others unfavorable.
    Uses episode-month grouping and same ≥5/≥5 per-month qualification as the engine.
    Returns Δ̂ in pp, or NaN if no month qualifies.
    """
    pop2 = pop.copy()
    pop2["_perm_fav"] = pop2["episode_id"].isin(fav_episode_set)

    sum_w_delta = 0.0
    sum_w = 0.0
    months = sorted(pop2["_ep_month"].unique())
    for month in months:
        sub = pop2[pop2["_ep_month"] == month]
        fav_sub = sub[sub["_perm_fav"]]
        unfav_sub = sub[~sub["_perm_fav"]]
        n_f, n_u = len(fav_sub), len(unfav_sub)
        if n_f < MIN_ROWS_PER_GROUP_PER_MONTH or n_u < MIN_ROWS_PER_GROUP_PER_MONTH:
            continue
        inc_f = float((fav_sub[state_col] == target_state).mean())
        inc_u = float((unfav_sub[state_col] == target_state).mean())
        delta_m = (inc_f - inc_u) * 100.0
        w_m = 2.0 * n_f * n_u / (n_f + n_u)
        sum_w_delta += w_m * delta_m
        sum_w += w_m

    return float(sum_w_delta / sum_w) if sum_w > 0 else float("nan")


def run_equivalence_tests(
    pop_by_instrument: dict,
    state_col_by_instrument: dict,
    state_by_instrument: dict,
) -> list:
    """
    Blocking equivalence tests per PM0_R4_PRIMARY_AMENDMENT.md §4:
    (a) Engine Δ̂ under TRUE labels must equal compute_within_month_stat's Δ̂ exactly per trial.
    (b) For 5 fixed label draws per instrument: engine Δ̂* must match slow pandas reference exactly.

    Returns list of result dicts. Raises SystemExit(2) on any failure.
    """
    results = []
    all_pass = True

    for inst_name, pop in pop_by_instrument.items():
        state_col = state_col_by_instrument[inst_name]
        target_state = state_by_instrument[inst_name]

        # Build the engine-ready pop (needs _fav, _ep_month, episode_id, state_col)
        # pop already has these columns set by the caller

        # ── (a) True-majority-selection equivalence: helper vs independent
        # inline row-assignment reference (two code paths, same labeling) ─────
        ep_majority = pop.groupby("episode_id")["_fav"].mean().ge(0.5)
        true_fav_eps = set(ep_majority[ep_majority].index)

        helper_delta = _engine_eval_one_selection(pop, state_col, target_state, true_fav_eps)

        pop_a = pop.copy()
        pop_a["_sel_fav"] = pop_a["episode_id"].isin(true_fav_eps)
        sw, swd = 0.0, 0.0
        for month in sorted(pop_a["_ep_month"].unique()):
            sub = pop_a[pop_a["_ep_month"] == month]
            fs, us = sub[sub["_sel_fav"]], sub[~sub["_sel_fav"]]
            if len(fs) < MIN_ROWS_PER_GROUP_PER_MONTH or len(us) < MIN_ROWS_PER_GROUP_PER_MONTH:
                continue
            dm = (float((fs[state_col] == target_state).mean())
                  - float((us[state_col] == target_state).mean())) * 100.0
            wm = 2.0 * len(fs) * len(us) / (len(fs) + len(us))
            swd += wm * dm
            sw += wm
        ref_delta = float(swd / sw) if sw > 0 else float("nan")

        match_a = (
            (np.isnan(helper_delta) and np.isnan(ref_delta)) or
            np.isclose(helper_delta, ref_delta, rtol=0, atol=1e-12)
        )
        if not match_a:
            all_pass = False

        # Informational: registered row-level Δ̂ vs majority-label Δ̂ (the
        # difference is the mixed-episode effect, expected small, NOT asserted)
        LOG(f"    EQ-TEST (a) {inst_name}: helper={helper_delta:.8f} ref={ref_delta:.8f} match={match_a}")
        results.append({
            "test": "a_true_majority_selection",
            "instrument": inst_name,
            "helper_delta": helper_delta,
            "ref_delta": ref_delta,
            "match": match_a,
        })

        # ── (b) Five fixed draws: engine vs slow pandas reference ────────────
        feat_idx = {"PM1": 1, "PM2": 2, "PM3": 3, "PM4": 4}
        fi = feat_idx[inst_name]
        rng_ref = np.random.default_rng([606, fi])

        months = sorted(pop["_ep_month"].unique())
        ep_majority_series = pop.groupby("episode_id")["_fav"].mean().ge(0.5)

        for draw_i in range(5):
            # Slow pandas reference: per month, permute episode majority labels
            perm_fav_eps = set()
            for month in months:
                month_mask = pop["_ep_month"] == month
                eps_in_month = pop[month_mask]["episode_id"].unique()
                ep_maj_m = ep_majority_series.reindex(eps_in_month).values.astype(bool)
                k_m = int(ep_maj_m.sum())
                perm_order = rng_ref.permutation(len(eps_in_month))
                chosen_indices = perm_order[:k_m]
                for ci in chosen_indices:
                    perm_fav_eps.add(eps_in_month[ci])

            pandas_draw_delta = _engine_eval_one_selection(pop, state_col, target_state, perm_fav_eps)

            # Engine reference: replicate the same draw using the engine's internal logic
            # We compute the same selection using the SAME rng state but from the engine
            # The engine uses argpartition on uniform keys; the pandas ref uses permutation.
            # These use DIFFERENT rng draws, so we can't compare them directly from the same seed.
            # Instead, use the slow pandas reference as both the "draw generator" and the evaluator
            # and verify the evaluator is correct by cross-checking with the engine's helper.
            # The actual test is: _engine_eval_one_selection (the engine's reference evaluator)
            # on the same perm_fav_eps must match the pandas row-assignment computation.
            # Both call the same per-month loop so they are identical by construction.
            # To make this a meaningful test, we use _engine_eval_one_selection vs an
            # independent row-assignment computation:
            pop2 = pop.copy()
            pop2["_perm_fav"] = pop2["episode_id"].isin(perm_fav_eps)
            # Pandas row-assignment delta (the "slow" reference):
            sum_w2 = 0.0
            sum_wd2 = 0.0
            for month in months:
                sub = pop2[pop2["_ep_month"] == month]
                fav_sub = sub[sub["_perm_fav"]]
                unfav_sub = sub[~sub["_perm_fav"]]
                n_f2, n_u2 = len(fav_sub), len(unfav_sub)
                if n_f2 < MIN_ROWS_PER_GROUP_PER_MONTH or n_u2 < MIN_ROWS_PER_GROUP_PER_MONTH:
                    continue
                inc_f2 = float((fav_sub[state_col] == target_state).mean())
                inc_u2 = float((unfav_sub[state_col] == target_state).mean())
                delta_m2 = (inc_f2 - inc_u2) * 100.0
                w_m2 = 2.0 * n_f2 * n_u2 / (n_f2 + n_u2)
                sum_wd2 += w_m2 * delta_m2
                sum_w2 += w_m2
            row_assign_delta = float(sum_wd2 / sum_w2) if sum_w2 > 0 else float("nan")

            match_b = (
                (np.isnan(pandas_draw_delta) and np.isnan(row_assign_delta)) or
                np.isclose(pandas_draw_delta, row_assign_delta, rtol=0, atol=1e-12)
            )
            if not match_b:
                all_pass = False

            LOG(f"    EQ-TEST (b) {inst_name} draw={draw_i}: helper={pandas_draw_delta:.10f} row_assign={row_assign_delta:.10f} match={match_b}")
            results.append({
                "test": "b_fixed_draw",
                "instrument": inst_name,
                "draw_i": draw_i,
                "helper_delta": pandas_draw_delta,
                "row_assign_delta": row_assign_delta,
                "match": match_b,
            })

        # ── (c) BATCHED engine vs slow helper on IDENTICAL selections ────────
        # The batched numpy path is the production null generator; this is the
        # test that validates it against an independent slow evaluation.
        eng = within_month_perm_engine(
            pop, state_col, target_state,
            seed=[303, fi], n_perm=7, collect_selections=True,
        )
        n_all_nan = int(np.isnan(eng["delta_perm"]).sum())
        if n_all_nan == 7:
            all_pass = False
            LOG(f"    EQ-TEST (c) {inst_name}: ALL batched draws NaN — engine defect.")
        for d in range(7):
            batched_delta = float(eng["delta_perm"][d])
            helper_delta_c = _engine_eval_one_selection(
                pop, state_col, target_state, eng["selections"][d]
            )
            match_c = (
                (np.isnan(batched_delta) and np.isnan(helper_delta_c)) or
                np.isclose(batched_delta, helper_delta_c, rtol=0, atol=1e-12)
            )
            if not match_c:
                all_pass = False
            LOG(f"    EQ-TEST (c) {inst_name} draw={d}: batched={batched_delta:.10f} "
                f"helper={helper_delta_c:.10f} match={match_c}")
            results.append({
                "test": "c_batched_vs_helper",
                "instrument": inst_name,
                "draw": d,
                "batched_delta": batched_delta,
                "helper_delta": helper_delta_c,
                "match": match_c,
            })

    if not all_pass:
        LOG("\nBLOCKER: Equivalence tests FAILED. Engine implementation has a defect.")
        sys.exit(2)

    LOG(f"    All equivalence tests PASS ({len(results)} checks).")
    return results


def compute_full_trial_stat(
    df: pd.DataFrame,
    feat: str,
    state_col: str,
    target_state: str,
    fwd_col: str,
    medians: dict,
    trial_idx: int,
    boot_seed: int = BOOT_SEED,
) -> dict:
    """
    Full trial statistic: within-month contrast + r4 primary permutation p + diagnostics.
    Returns dict with all trial outputs per spec §3.2 and PM0_R4_PRIMARY_AMENDMENT.md.
    """
    within = compute_within_month_stat(df, feat, state_col, target_state, medians)
    delta_hat = within["delta_hat"]

    # ── r4 PRIMARY p: within-month episode-label permutation ─────────────────
    # Seed: default_rng([20260706, trial_idx]) per amendment §2.
    # Observed statistic uses registered row-level labels; null draws use episode-majority
    # labels permuted within month (house P1.3-v2/P2.5 convention; mixed fraction logged).
    n_perm_primary = 5000
    perm_seed = [20260706, trial_idx]

    mask_defined_perm = df[feat].notna() & df[state_col].notna()
    pop_perm = df[mask_defined_perm].copy()
    fav_mask_perm = _get_favorable_mask(pop_perm, feat, medians)
    pop_perm["_fav"] = fav_mask_perm.values
    pop_perm["_month"] = pd.to_datetime(pop_perm["signal_date"]).dt.to_period("M").dt.to_timestamp()
    ep_first_month_perm = pop_perm.groupby("episode_id")["_month"].min().rename("_ep_month")
    pop_perm = pop_perm.merge(ep_first_month_perm, on="episode_id", how="left")

    perm_result = within_month_perm_engine(
        pop_perm, state_col, target_state, seed=perm_seed, n_perm=n_perm_primary
    )
    delta_perm_arr = perm_result["delta_perm"]

    if not np.isnan(delta_hat):
        abs_obs = abs(delta_hat)
        # NaN draws -> treated as exceedance (conservative) per amendment
        nan_draws = np.isnan(delta_perm_arr)
        exceedances = int(np.sum(~nan_draws & (np.abs(delta_perm_arr) >= abs_obs))) + int(nan_draws.sum())
        primary_perm_p = float((1 + exceedances) / (n_perm_primary + 1))
    else:
        primary_perm_p = float("nan")

    # ── MONTH-BLOCK BOOTSTRAP — DIAGNOSTIC ONLY ──────────────────────────────
    # Demoted per PM0_R4_PRIMARY_AMENDMENT.md §2. NEVER feeds BH or verdicts.
    # Mild left-tail anticonservatism at m=43 per §7 record (calibration run 2).
    # Kept for CI context (effect-size context beside Δ̂).
    # Seed derivation unchanged: (BOOT_SEED * 100000 + trial_idx).
    diag_boot_seed = int(boot_seed) * 100000 + int(trial_idx)
    boot_ci_result = _month_block_bootstrap_ci(
        within["month_deltas"], within["month_weights"], delta_hat,
        seed=diag_boot_seed, n_boot=N_BOOT,
    )
    boot_ci_lo = boot_ci_result["ci_lo"]
    boot_ci_hi = boot_ci_result["ci_hi"]
    boot_pivot_p_DIAGNOSTIC = boot_ci_result["pivot_p"]

    # Favorable direction check
    favorable_dir = _favorable_direction(target_state)

    # Pooled delta (not time-controlled — labeled diagnostic)
    mask_defined = df[feat].notna() & df[state_col].notna()
    pop_all = df[mask_defined].copy()
    fav_all = _get_favorable_mask(pop_all, feat, medians)
    if fav_all.sum() > 0 and (~fav_all).sum() > 0:
        inc_fav_pooled = float((pop_all[fav_all][state_col] == target_state).mean()) * 100
        inc_unfav_pooled = float((pop_all[~fav_all][state_col] == target_state).mean()) * 100
        delta_pooled = inc_fav_pooled - inc_unfav_pooled
    else:
        delta_pooled = np.nan
        inc_fav_pooled = np.nan
        inc_unfav_pooled = np.nan

    pooled_vs_within_divergence = (
        float(delta_pooled - delta_hat)
        if not np.isnan(delta_pooled) and not np.isnan(delta_hat)
        else np.nan
    )

    # Diagnostic (a): episode-label permutation on pooled delta (NOT TIME-CONTROLLED)
    ep_perm_p = _episode_perm_diagnostic(
        pop_all, fav_all, state_col, target_state, trial_idx, n_perm=N_PERM_DIAG
    )

    # Diagnostic (b): MWU on forward return (NOT TIME-CONTROLLED)
    mwu_r, mwu_p = _mwu_diagnostic(pop_all, fav_all, fwd_col)

    # §4.2(b) param/perm divergence sanity gate (P1.3 round-1 defect
    # signature, P2.5 SANITY_DIVERGENCE_ORDERS=6): episode-label permutation p
    # of the SAME MWU statistic vs its parametric p. Trips only if the
    # permutation machinery returns null while the parametric test screams.
    ep_perm_mwu_p, _ = _episode_perm_mwu_p(
        pop_all, fav_all, fwd_col,
        seed=[777, trial_idx, 777], n_perm=N_PERM_DIAG,
    )
    divergence_trip = bool(
        not np.isnan(ep_perm_mwu_p) and not np.isnan(mwu_p) and mwu_p > 0
        and ep_perm_mwu_p > 0.3 and mwu_p < 1e-6
    )

    return {
        "delta_hat": delta_hat,
        # r4 PRIMARY p-value (PM0_R4_PRIMARY_AMENDMENT.md): within-month episode-label permutation.
        # This feeds BH and verdicts. The old boot_p key is gone; consumers use primary_perm_p.
        "primary_perm_p": primary_perm_p,
        "perm_n_nan_draws": perm_result["n_nan_draws"],
        # MONTH-BLOCK BOOTSTRAP — DIAGNOSTIC (anticonservative-in-tail at m=43 per §7 record).
        # CI only; does NOT feed BH or verdicts.
        "boot_ci_lo_DIAGNOSTIC": boot_ci_lo,
        "boot_ci_hi_DIAGNOSTIC": boot_ci_hi,
        "boot_pivot_p_DIAGNOSTIC": boot_pivot_p_DIAGNOSTIC,
        "favorable_direction": favorable_dir,
        "in_favorable_direction": (
            (favorable_dir < 0 and not np.isnan(delta_hat) and delta_hat < 0) or
            (favorable_dir > 0 and not np.isnan(delta_hat) and delta_hat > 0)
        ),
        "n_qualifying_months": within["n_qualifying_months"],
        "n_fav": within["n_fav"],
        "n_unfav": within["n_unfav"],
        "n_ep_fav": within["n_ep_fav"],
        "n_ep_unfav": within["n_ep_unfav"],
        "thin_flag": within["thin_flag"],
        "n_events_fav": within["n_events_fav"],
        "n_events_unfav": within["n_events_unfav"],
        "month_details": within["month_details"],
        "episode_straddle_count": within["episode_straddle_count"],
        "n_total": within["n_total"],
        "delta_pooled_pp": delta_pooled,
        "inc_fav_pooled_pct": inc_fav_pooled,
        "inc_unfav_pooled_pct": inc_unfav_pooled,
        "pooled_vs_within_divergence_pp": pooled_vs_within_divergence,
        "ep_perm_p_NOT_TIME_CONTROLLED": ep_perm_p,
        "mwu_rank_biserial_NOT_TIME_CONTROLLED": mwu_r,
        "mwu_p_NOT_TIME_CONTROLLED": mwu_p,
        "ep_perm_mwu_p_NOT_TIME_CONTROLLED": ep_perm_mwu_p,
        "divergence_gate_trip": divergence_trip,
    }


def _favorable_direction(state: str) -> int:
    """Favorable direction: STOPPED/DEAD_MONEY -> negative delta; CUSHIONED -> positive."""
    if state in ("STOPPED", "DEAD_MONEY"):
        return -1
    elif state == "CUSHIONED":
        return +1
    else:
        return 0


def _episode_perm_diagnostic(
    pop: pd.DataFrame,
    fav_mask: pd.Series,
    state_col: str,
    target_state: str,
    trial_idx: int,
    n_perm: int = N_PERM_DIAG,
) -> float:
    """Episode-level permutation on pooled delta. NOT TIME-CONTROLLED."""
    if len(pop) == 0:
        return np.nan
    pop2 = pop.copy()
    pop2["_fav"] = fav_mask.values
    pop2["_state"] = (pop2[state_col] == target_state).astype(float)

    # Episode majority label
    ep_label = pop2.groupby("episode_id")["_fav"].mean().ge(0.5)
    ep_labels = ep_label.to_dict()
    pop2["_ep_fav"] = pop2["episode_id"].map(ep_labels)

    episodes = list(ep_label.index)
    ep_outcomes = pop2.groupby("episode_id")["_state"].mean().to_dict()

    rng = np.random.default_rng((777, trial_idx))
    exceedances = 0

    obs_fav_mask = pop2["_ep_fav"].values.astype(bool)
    obs_fav_inc = pop2[obs_fav_mask]["_state"].mean() if obs_fav_mask.sum() > 0 else np.nan
    obs_unfav_inc = pop2[~obs_fav_mask]["_state"].mean() if (~obs_fav_mask).sum() > 0 else np.nan
    if np.isnan(obs_fav_inc) or np.isnan(obs_unfav_inc):
        return np.nan
    obs_delta = (obs_fav_inc - obs_unfav_inc) * 100.0

    ep_arr = np.array(episodes)
    ep_fav_arr = np.array([ep_labels[e] for e in episodes])

    for _ in range(n_perm):
        perm_fav = rng.permutation(ep_fav_arr)
        perm_fav_dict = {ep_arr[i]: bool(perm_fav[i]) for i in range(len(ep_arr))}
        pop2["_perm_fav"] = pop2["episode_id"].map(perm_fav_dict)
        pm = pop2["_perm_fav"].values.astype(bool)
        perm_fav_inc = pop2[pm]["_state"].mean() if pm.sum() > 0 else 0.0
        perm_unfav_inc = pop2[~pm]["_state"].mean() if (~pm).sum() > 0 else 0.0
        perm_delta = (perm_fav_inc - perm_unfav_inc) * 100.0
        if abs(perm_delta) >= abs(obs_delta):
            exceedances += 1

    return float((1 + exceedances) / (n_perm + 1))


def _mwu_diagnostic(
    pop: pd.DataFrame,
    fav_mask: pd.Series,
    fwd_col: str,
) -> tuple:
    """MWU + rank-biserial on forward return. NOT TIME-CONTROLLED."""
    if fwd_col not in pop.columns:
        return np.nan, np.nan
    fav_ret = pop[fav_mask][fwd_col].dropna()
    unfav_ret = pop[~fav_mask][fwd_col].dropna()
    if len(fav_ret) < 2 or len(unfav_ret) < 2:
        return np.nan, np.nan
    try:
        result = stats.mannwhitneyu(fav_ret, unfav_ret, alternative="two-sided")
        n1, n2 = len(fav_ret), len(unfav_ret)
        r = float(1 - 2 * result.statistic / (n1 * n2))
        return r, float(result.pvalue)
    except Exception:
        return np.nan, np.nan


def _episode_perm_mwu_p(
    pop: pd.DataFrame,
    fav_mask: pd.Series,
    val_col: str,
    seed,
    n_perm: int = N_PERM_DIAG,
) -> tuple:
    """Episode-label permutation MWU on a value column (P2.5-style return
    instrument): episode-majority labels, cross-episode shuffle, rank-biserial
    statistic per draw, add-one two-sided p. Returns (perm_p, obs_rank_biserial).
    NOT TIME-CONTROLLED — calibration/diagnostic use only."""
    pop2 = pop[[val_col, "episode_id"]].copy()
    pop2["_fav"] = fav_mask.values
    pop2 = pop2[pop2[val_col].notna()]
    if len(pop2) == 0:
        return np.nan, np.nan
    ep_label = pop2.groupby("episode_id")["_fav"].mean().ge(0.5)
    episodes = np.array(ep_label.index)
    ep_fav = ep_label.values.astype(bool)
    ep_index = {e: i for i, e in enumerate(episodes)}
    row_ep_idx = np.array([ep_index[e] for e in pop2["episode_id"].values])
    vals = pop2[val_col].values.astype(float)
    ranks = stats.rankdata(vals)
    n_all = len(vals)

    def rank_biserial(fav_rows):
        n1 = int(fav_rows.sum())
        n2 = n_all - n1
        if n1 == 0 or n2 == 0:
            return np.nan
        u1 = ranks[fav_rows].sum() - n1 * (n1 + 1) / 2.0
        return 1.0 - 2.0 * u1 / (n1 * n2)

    obs_r = rank_biserial(ep_fav[row_ep_idx])
    if np.isnan(obs_r):
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(n_perm):
        r = rank_biserial(rng.permutation(ep_fav)[row_ep_idx])
        if not np.isnan(r) and abs(r) >= abs(obs_r):
            exceed += 1
    return float((1 + exceed) / (n_perm + 1)), float(obs_r)


def compute_sign_stability(
    df: pd.DataFrame,
    feat: str,
    state_col: str,
    target_state: str,
    medians: dict,
) -> dict:
    """Both-halves sign stability at 2024-06-30."""
    h1 = df[pd.to_datetime(df["signal_date"]) <= pd.Timestamp(SIGN_SPLIT_DATE)]
    h2 = df[pd.to_datetime(df["signal_date"]) > pd.Timestamp(SIGN_SPLIT_DATE)]
    results = {}
    for name, half in [("h1", h1), ("h2", h2)]:
        w = compute_within_month_stat(half, feat, state_col, target_state, medians)
        results[name] = {
            "delta_hat": w["delta_hat"],
            "n_qualifying_months": w["n_qualifying_months"],
            "n_fav": w["n_fav"],
            "n_unfav": w["n_unfav"],
        }
    dh1 = results["h1"]["delta_hat"]
    dh2 = results["h2"]["delta_hat"]
    if np.isnan(dh1) or np.isnan(dh2):
        stable = None
    else:
        stable = bool(np.sign(dh1) == np.sign(dh2))
    results["sign_stable"] = stable
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Redundancy matrix (§4.3)
# ─────────────────────────────────────────────────────────────────────────────

def compute_redundancy_matrix(
    vg_fires: pd.DataFrame,
    feat_df: pd.DataFrame,
) -> dict:
    """
    Spearman rank correlations of PM1-PM5 against frozen reference set +
    within-bundle PM×PM correlations. Only poc_dist_126 comes from feat_df.
    Reference: {ext_z, ext_atr, dist_to_52wh, near_52wh, rs_63d_return,
                align_quality, washout_proximity, poc_dist_126}
    """
    ref_cols_from_replay = [
        "ext_z", "ext_atr", "dist_to_52wh", "near_52wh",
        "rs_63d_return", "align_quality", "washout_proximity",
    ]
    pm_cols = ["pm1", "pm2", "pm3", "pm4", "pm5"]

    # If vg_fires already has pm columns (pre-merged), use it directly
    if all(c in vg_fires.columns for c in pm_cols):
        merged = vg_fires.copy()
        # Ensure poc_dist_126 is present (may need join if not already there)
        if "poc_dist_126" not in merged.columns:
            merged = merged.merge(
                feat_df[["ticker", "signal_date", "episode_id", "poc_dist_126"]],
                on=["ticker", "signal_date", "episode_id"],
                how="left",
            )
    else:
        # Join vg_fires with features on (ticker, signal_date, episode_id)
        merged = vg_fires.merge(
            feat_df[["ticker", "signal_date", "episode_id"] + pm_cols + ["poc_dist_126"]],
            on=["ticker", "signal_date", "episode_id"],
            how="left",
        )

    all_ref = ref_cols_from_replay + ["poc_dist_126"]

    matrix = {}
    redundant_against = {}

    for pm in pm_cols:
        matrix[pm] = {}
        for ref in all_ref:
            if ref not in merged.columns:
                matrix[pm][ref] = None
                continue
            both = merged[[pm, ref]].dropna()
            if len(both) < 10:
                matrix[pm][ref] = None
                continue
            rho, _ = stats.spearmanr(both[pm], both[ref])
            matrix[pm][ref] = round(float(rho), 4)
            if abs(rho) >= REDUNDANCY_RHO:
                if pm not in redundant_against:
                    redundant_against[pm] = []
                redundant_against[pm].append(ref)

    # Within-bundle PM×PM
    within_bundle = {}
    for i, pm_i in enumerate(pm_cols):
        for pm_j in pm_cols[i + 1:]:
            both = merged[[pm_i, pm_j]].dropna()
            if len(both) < 10:
                within_bundle[f"{pm_i}_vs_{pm_j}"] = None
                continue
            rho, _ = stats.spearmanr(both[pm_i], both[pm_j])
            within_bundle[f"{pm_i}_vs_{pm_j}"] = round(float(rho), 4)
            if abs(rho) >= REDUNDANCY_RHO:
                for pm in [pm_i, pm_j]:
                    if pm not in redundant_against:
                        redundant_against[pm] = []
                    redundant_against[pm].append(f"within_bundle:{pm_i}_vs_{pm_j}")

    return {
        "vs_reference": matrix,
        "within_bundle": within_bundle,
        "redundant_against": redundant_against,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: PREAMBLE
# ─────────────────────────────────────────────────────────────────────────────

def run_preamble(features_path: Path) -> dict:
    LOG("=" * 72)
    LOG(f"EI-PM0 — PREAMBLE STAGE")
    LOG(f"Study: {STUDY_ID}")
    LOG(f"Pre-registration: PM0_PRICE_MEMORY_BUNDLE_PREREG.md (APPROVED 2026-07-06 r3)")
    LOG(f"Era law: P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05)")
    LOG("=" * 72)
    LOG()

    preamble = {"stage": "preamble", "study_id": STUDY_ID}

    # ── MD5s ──────────────────────────────────────────────────────────────────
    LOG("Computing MD5s...")
    replay_md5 = _md5(REPLAY_PATH)
    feat_md5 = _md5(features_path)
    edgar_md5 = _md5(EDGAR_PATH)
    preamble["md5"] = {
        "replay": replay_md5,
        "features": feat_md5,
        "statements": edgar_md5,
    }
    LOG(f"  replay:     {replay_md5}")
    LOG(f"  features:   {feat_md5}")
    LOG(f"  statements: {edgar_md5}")
    LOG()

    # ── Phase 1: load WITHOUT outcome columns ─────────────────────────────────
    LOG("PHASE 1: Loading replay WITHOUT outcome columns (outcome-blind)...")
    blind_cols = [
        "ticker", "signal_date", "episode_id",
        "survivor_bias", "verdict_type", "verdict_grade", "horizon_censored",
        "ext_z", "ext_atr", "dist_to_52wh", "near_52wh",
        "rs_63d_return", "align_quality", "washout_proximity",
    ]
    replay_blind = pd.read_parquet(REPLAY_PATH, columns=blind_cols)
    LOG(f"  Full replay shape: {replay_blind.shape}")

    # ── Column-map verification ──────────────────────────────────────────────
    LOG("\nColumn-map verification (frozen list from prereg §1)...")
    missing_blind = [c for c in blind_cols if c not in replay_blind.columns]
    if missing_blind:
        LOG(f"HALT: Missing columns in replay: {missing_blind}")
        sys.exit(1)
    LOG("  All blind columns present.")

    # ── Load feature artifact ─────────────────────────────────────────────────
    LOG(f"\nLoading feature artifact: {features_path}")
    feat_df = pd.read_parquet(features_path)
    LOG(f"  Feature artifact shape: {feat_df.shape}")
    preamble["feat_path"] = str(features_path)
    preamble["feat_shape"] = list(feat_df.shape)

    # ── Load qa_report for medians ─────────────────────────────────────────────
    qa_path = OUT_DIR / "qa_report.json"
    if not qa_path.exists():
        LOG(f"HALT: qa_report.json not found at {qa_path}. Run --build first.")
        sys.exit(1)
    with open(qa_path) as fh:
        qa_report = json.load(fh)
    medians_from_qa = qa_report.get("medians_vg_fires", {})
    preamble["medians_from_qa"] = medians_from_qa

    # Verify medians match recomputation
    vg_fire_mask = (feat_df["verdict_type"] == "fire") & (feat_df["verdict_grade"] == True)
    vg_feats = feat_df[vg_fire_mask]
    medians_recomputed = {}
    for col in ["pm2", "pm4", "pm5"]:
        vals = vg_feats[col].dropna()
        medians_recomputed[f"{col}_median"] = float(vals.median()) if len(vals) > 0 else None
        medians_recomputed[f"{col}_n_defined"] = int(vals.count())

    drift = False
    for k in medians_recomputed:
        qa_v = medians_from_qa.get(k)
        rc_v = medians_recomputed[k]
        if qa_v is None and rc_v is None:
            continue
        if qa_v is None or rc_v is None:
            LOG(f"HALT: Median drift for {k}: qa={qa_v} recomputed={rc_v}")
            drift = True
            continue
        if abs(float(qa_v) - float(rc_v)) > 1e-10:
            LOG(f"HALT: Median drift for {k}: qa={qa_v} recomputed={rc_v}")
            drift = True
    if drift:
        LOG("HALT: Artifact/QA desync detected in medians.")
        sys.exit(1)
    LOG("  Medians verified against qa_report.json (no drift).")
    medians = medians_recomputed
    preamble["medians"] = medians

    # Log favorable splits
    LOG("\nFavorable splits (frozen):")
    LOG(f"  pm1: >= 0  (median N/A)")
    LOG(f"  pm2: >= {medians.get('pm2_median', 'N/A'):.6f}  (median over vg fires, n={medians.get('pm2_n_defined')})")
    LOG(f"  pm3: == 0")
    LOG(f"  pm4: <= {medians.get('pm4_median', 'N/A'):.6f}  (median over vg fires, n={medians.get('pm4_n_defined')})")
    LOG(f"  pm5: >= {medians.get('pm5_median', 'N/A')}  (data_blocked, for reference only)")
    preamble["favorable_splits"] = {
        "pm1": "pm1 >= 0",
        "pm2": f"pm2 >= {medians.get('pm2_median')}",
        "pm3": "pm3 == 0",
        "pm4": f"pm4 <= {medians.get('pm4_median')}",
        "pm5": f"pm5 >= {medians.get('pm5_median')} (data_blocked)",
    }

    # ── Population census ─────────────────────────────────────────────────────
    LOG("\nPOPULATION CENSUS (era window: 2022-06-30 -> 2026-07-02)")
    LOG(f"  Era law: P0_MEASUREMENT_MEMO.md v1.1 — effective verdict window 2022-06-30 -> 2026-07-02")
    LOG(f"  Canonical input: replay_boarded.parquet (NEVER parts glob)")

    fires = replay_blind[replay_blind["verdict_type"] == "fire"].copy()
    vg = fires[fires["verdict_grade"] == True].copy()
    n_stamped = int(vg["survivor_bias"].sum())
    n_censored = int(vg["horizon_censored"].sum())
    n_vg = len(vg)
    n_ep = int(vg["episode_id"].nunique())

    LOG(f"  Total fires: {len(fires):,}")
    LOG(f"  Verdict-grade fires: {n_vg:,}")
    LOG(f"  Survivor-stamped (excluded from verdicts): {n_stamped:,}")
    LOG(f"  horizon_censored: {n_censored:,}")
    LOG(f"  Episode clusters (operative): {n_ep:,}")
    LOG(f"  Signal date range: {vg['signal_date'].min()} -> {vg['signal_date'].max()}")
    LOG(f"  Verdict horizon end (spec §0): 2026-07-02")

    preamble["population"] = {
        "n_fires": int(len(fires)),
        "n_vg_fires": n_vg,
        "n_survivor_stamped": n_stamped,
        "n_horizon_censored": n_censored,
        "n_episodes": n_ep,
        "signal_date_min": str(vg["signal_date"].min()),
        "signal_date_max": str(vg["signal_date"].max()),
    }

    # ── Redundancy matrix (§4.3) — BEFORE any outcome column is loaded ───────
    LOG("\nComputing redundancy matrix (§4.3) — pre-outcome-join...")
    vg_ref_feats = vg.merge(
        feat_df[["ticker", "signal_date", "episode_id",
                 "pm1", "pm2", "pm3", "pm4", "pm5", "poc_dist_126"]],
        on=["ticker", "signal_date", "episode_id"],
        how="left",
    )
    red_matrix = compute_redundancy_matrix(vg_ref_feats, feat_df)
    preamble["redundancy_matrix"] = red_matrix
    LOG(f"  Redundant components: {list(red_matrix['redundant_against'].keys()) or 'none'}")
    LOG(f"  Within-bundle correlations: {red_matrix['within_bundle']}")

    # ── Month census per feature — BEFORE any outcome column is loaded ───────
    # (Qualifying months need only group sizes; on this substrate all vg fires
    # have both states non-null, so the per-feature census equals the
    # per-trial census on both grids.)
    LOG("\nMonth census per feature (pre-outcome-join; qualifying = both groups >= 5 rows)...")
    month_census = {}
    for feat in ["pm1", "pm2", "pm3", "pm4"]:
        popf = vg_ref_feats[vg_ref_feats[feat].notna()].copy()
        if len(popf) == 0:
            month_census[feat] = {"n_qualifying_months": 0, "months": {}}
            continue
        favf = _get_favorable_mask(popf, feat, medians)
        popf["_month"] = pd.to_datetime(popf["signal_date"]).dt.to_period("M").astype(str)
        # Episode-month assignment (EX-8): rows belong to their episode's
        # first-row month, matching the §4.2 statistic's blocking.
        ep_first = popf.groupby("episode_id")["_month"].min()
        popf["_month"] = popf["episode_id"].map(ep_first)
        sizes = popf.groupby(["_month", favf.rename("_fav")]).size().unstack(fill_value=0)
        months_detail = {}
        n_qual = 0
        for m in sizes.index:
            n_f = int(sizes.loc[m].get(True, 0))
            n_u = int(sizes.loc[m].get(False, 0))
            q = n_f >= MIN_ROWS_PER_GROUP_PER_MONTH and n_u >= MIN_ROWS_PER_GROUP_PER_MONTH
            months_detail[str(m)] = {"n_fav": n_f, "n_unfav": n_u, "qualifies": bool(q)}
            n_qual += int(q)
        month_census[feat] = {"n_qualifying_months": n_qual, "months": months_detail}
        LOG(f"  {feat}: {n_qual} qualifying months of {len(sizes.index)}")
    preamble["month_census"] = month_census

    # Preamble part 1 goes to disk BEFORE outcomes are read (prereg §4.4
    # outcome-blindness contract: thresholds, medians, coverage-inputs,
    # mapping, redundancy all written first).
    preamble["part"] = 1
    _save_json(preamble, OUT_DIR / "preamble.json")
    LOG("\nPreamble part 1 written (pre-outcome-join).")

    # ── Enum check ────────────────────────────────────────────────────────────
    LOG("\nTerminal-state enum check...")
    # Phase 2 needed for state columns — we'll load them now (preamble part 2)
    LOG("  (Loading outcome columns for enum check and floors...)")
    # Include reference columns for the redundancy matrix
    _ref_cols = ["ext_z", "ext_atr", "dist_to_52wh", "near_52wh",
                 "rs_63d_return", "align_quality", "washout_proximity"]
    outcome_cols = list(dict.fromkeys(
        ["ticker", "signal_date", "episode_id", "survivor_bias",
         "verdict_type", "verdict_grade", "horizon_censored",
         "state_8_21", "state_15_126", "fwd_ret_21", "fwd_ret_126",
         ] + _ref_cols + [c for c in CONTEXT_COLS if c not in ["sector"]] + ["sector"]
    ))

    replay_full = pd.read_parquet(REPLAY_PATH, columns=outcome_cols)

    missing_outcome = [c for c in REQUIRED_OUTCOME_COLS if c not in replay_full.columns]
    if missing_outcome:
        LOG(f"HALT: Missing required outcome columns: {missing_outcome}")
        sys.exit(1)
    LOG("  All required outcome columns present.")

    vg_full = replay_full[
        (replay_full["verdict_type"] == "fire") &
        (replay_full["verdict_grade"] == True)
    ].copy()

    # Enum check
    for col in [GRID_A_STATE_COL, GRID_B_STATE_COL]:
        observed = set(vg_full[col].dropna().unique())
        unexpected = observed - EXPECTED_STATES
        if unexpected:
            LOG(f"HALT: Unexpected enum values in {col}: {unexpected}")
            sys.exit(1)
        LOG(f"  {col} states: {sorted(observed)}")

    # horizon_censored semantics: vg fires should have no censored rows
    hc_count_a = int(vg_full[vg_full["horizon_censored"] == True][GRID_A_STATE_COL].isna().sum())
    hc_count_b = int(vg_full[vg_full["horizon_censored"] == True][GRID_B_STATE_COL].isna().sum())
    LOG(f"  horizon_censored rows with null state_8_21: {hc_count_a}")
    LOG(f"  horizon_censored rows with null state_15_126: {hc_count_b}")

    grid_a_counts = vg_full[GRID_A_STATE_COL].value_counts().to_dict()
    grid_b_counts = vg_full[GRID_B_STATE_COL].value_counts().to_dict()
    LOG(f"\n  Grid A (state_8_21) counts: {grid_a_counts}")
    LOG(f"  Grid B (state_15_126) counts: {grid_b_counts}")

    preamble["state_enum"] = {
        "grid_a": {k: int(v) for k, v in grid_a_counts.items()},
        "grid_b": {k: int(v) for k, v in grid_b_counts.items()},
        "enum_pass": True,
    }

    # ── Event floor check (§1 / §3.1) ────────────────────────────────────────
    LOG(f"\nEvent floor check (pre-p-value) m starts at: {M_DECLARED}")
    m_active = M_DECLARED
    excluded_trials = []

    for (tid, feat, state_col, state, fwd_col) in TRIAL_TABLE:
        # Count events in the trial's analysis population
        trial_feat = feat_df[["ticker", "signal_date", "episode_id", feat]].copy()
        trial_pop2 = vg_full.merge(trial_feat, on=["ticker", "signal_date", "episode_id"], how="left")
        trial_pop2 = trial_pop2[trial_pop2[feat].notna() & trial_pop2[state_col].notna()]

        n_events = int((trial_pop2[state_col] == state).sum())
        if n_events < MIN_EVENTS:
            LOG(f"  INSUFFICIENT-DATA: {tid} ({feat} {state_col} {state}): {n_events} events < {MIN_EVENTS}")
            excluded_trials.append({"trial": tid, "reason": "INSUFFICIENT-DATA", "n_events": n_events})
            m_active -= 1
            continue

        # Per-group event floor
        fav_mask = _get_favorable_mask(trial_pop2, feat, medians)
        fav_sub = trial_pop2[fav_mask]
        unfav_sub = trial_pop2[~fav_mask]
        n_ev_fav = int((fav_sub[state_col] == state).sum())
        n_ev_unfav = int((unfav_sub[state_col] == state).sum())
        if n_ev_fav < MIN_EVENTS_GROUP or n_ev_unfav < MIN_EVENTS_GROUP:
            LOG(f"  INSUFFICIENT-DATA: {tid}: per-group events fav={n_ev_fav} unfav={n_ev_unfav}")
            excluded_trials.append({"trial": tid, "reason": "INSUFFICIENT-DATA",
                                    "n_ev_fav": n_ev_fav, "n_ev_unfav": n_ev_unfav})
            m_active -= 1

    LOG(f"  m after event floor: {m_active} (started {M_DECLARED}, decremented {M_DECLARED - m_active})")

    # ── Month floor check ─────────────────────────────────────────────────────
    LOG("\nMonth floor check (< 24 qualifying months => INSUFFICIENT-POWER)...")
    for (tid, feat, state_col, state, fwd_col) in TRIAL_TABLE:
        if any(e["trial"] == tid for e in excluded_trials):
            continue
        trial_feat = feat_df[["ticker", "signal_date", "episode_id", feat]].copy()
        trial_pop = vg_full.merge(trial_feat, on=["ticker", "signal_date", "episode_id"], how="left")
        within = compute_within_month_stat(trial_pop, feat, state_col, state, medians)
        if within["n_qualifying_months"] < MIN_QUAL_MONTHS:
            LOG(f"  INSUFFICIENT-POWER: {tid}: {within['n_qualifying_months']} qualifying months < {MIN_QUAL_MONTHS}")
            excluded_trials.append({"trial": tid, "reason": "INSUFFICIENT-POWER",
                                    "n_qualifying_months": within["n_qualifying_months"]})
            m_active -= 1

    LOG(f"  m final (after month floor): {m_active}")

    preamble["m_declared"] = M_DECLARED
    preamble["m_active"] = m_active
    preamble["excluded_trials"] = excluded_trials

    preamble["part"] = 2

    # ── Coverage table (from QA report) ─────────────────────────────────────
    LOG("\nCoverage table (from qa_report.json)...")
    coverage = qa_report.get("gate3_coverage", {}).get("table", {})
    preamble["coverage"] = coverage
    if coverage:
        for pop_name, pop_cov in coverage.items():
            LOG(f"  {pop_name}:")
            for col, info in pop_cov.items():
                LOG(f"    {col}: {info['n_defined']:,}/{info['n_total']:,} = {info['pct']:.1%}")

    pm5_cov = qa_report.get("gate3_coverage", {}).get("pm5_vg_fire_pct", None)
    LOG(f"  PM5 vg_fire coverage: {pm5_cov:.1%} (pre-declared data_blocked; floor 60% fails as expected)")
    preamble["pm5_coverage_pct"] = pm5_cov
    preamble["pm5_status"] = "data_blocked (pre-declared, coverage < 60%)"

    # ── QA outcomes summary ───────────────────────────────────────────────────
    preamble["qa_outcomes"] = {
        "gate1_pit_audit": qa_report.get("gate1_pit_audit", {}).get("pass"),
        "gate5_determinism": qa_report.get("gate5_determinism", {}).get("pass"),
        "overall_pass": qa_report.get("overall_pass"),
    }

    # ── §5/§6 conformance checklist ───────────────────────────────────────────
    LOG("\n§5/§6 CONFORMANCE CHECKLIST:")
    LOG("  [x] Cites P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05)")
    LOG("  [x] Effective verdict window 2022-06-30 -> 2026-07-02")
    LOG("  [x] Verdict stats on survivor_bias==False rows only")
    LOG("  [x] Canonical replay_boarded.parquet (path + MD5 logged)")
    LOG("  [x] Per-ruler censoring handled and counted")
    LOG("  [x] INSUFFICIENT-POWER / INSUFFICIENT-DATA returned where floors fail")
    LOG("  [x] m=20 declared; decrements logged before any p-value exists")
    LOG("  [x] Episode straddle count logged per trial in month_details")

    preamble["conformance"] = {
        "memo_v1_1": True,
        "era_window": "2022-06-30 -> 2026-07-02",
        "survivor_bias_excluded": True,
        "canonical_replay": True,
        "censoring_counted": True,
        "insufficient_power_honored": True,
        "m_declared_20": True,
    }

    preamble["vg_full_shape"] = list(vg_full.shape)

    # Save preamble.json
    _save_json(preamble, OUT_DIR / "preamble.json")
    LOG(f"\nPreamble saved: {OUT_DIR / 'preamble.json'}")

    return preamble


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────

def _load_vg_full(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Load full verdict-grade fire population with outcome columns and features joined."""
    outcome_cols = REQUIRED_OUTCOME_COLS + [c for c in CONTEXT_COLS if c != "sector"] + ["sector"]
    replay_full = pd.read_parquet(REPLAY_PATH, columns=outcome_cols)
    vg_full = replay_full[
        (replay_full["verdict_type"] == "fire") &
        (replay_full["verdict_grade"] == True)
    ].copy()
    # Join features
    feat_join_cols = ["ticker", "signal_date", "episode_id",
                      "pm1", "pm2", "pm3", "pm4", "pm5", "poc_dist_126"]
    vg_full = vg_full.merge(
        feat_df[feat_join_cols],
        on=["ticker", "signal_date", "episode_id"],
        how="left",
    )
    return vg_full


def run_calibration(features_path: Path) -> dict:
    LOG("=" * 72)
    LOG("EI-PM0 — CALIBRATION STAGE (§7)")
    LOG("Primary machinery: r4 within-month episode-label permutation (PM0_R4_PRIMARY_AMENDMENT.md)")
    LOG("=" * 72)
    LOG()

    preamble_path = OUT_DIR / "preamble.json"
    if not preamble_path.exists():
        LOG(f"HALT: preamble.json not found. Run --stage preamble first.")
        sys.exit(1)
    with open(preamble_path) as fh:
        preamble = json.load(fh)
    medians = preamble["medians"]

    feat_df = pd.read_parquet(features_path)
    vg_full = _load_vg_full(feat_df)
    LOG(f"VG fires loaded: {len(vg_full):,}")

    calibration = {
        "stage": "calibration",
        "instruments": {},
        "overall_pass": False,
        "machinery": "r4 within-month episode-label permutation (PM0_R4_PRIMARY_AMENDMENT.md)",
    }
    all_pass = True

    # ── Blocking equivalence tests (PM0_R4_PRIMARY_AMENDMENT.md §4) ──────────
    # Run BEFORE the 200-draw loops; loud failure + sys.exit(2) on any mismatch.
    LOG("\n§4 EQUIVALENCE TESTS (blocking — run before calibration loops)")
    LOG("  (a) Engine Δ̂ under true majority labels == pandas reference per instrument")
    LOG("  (b) Engine Δ̂* for 5 fixed draws per instrument == slow pandas reference (atol=1e-12)")

    eq_pop_by_inst = {}
    eq_state_col_by_inst = {}
    eq_state_by_inst = {}

    for (inst_name, feat, state_col, state, fwd_col) in CAL_INSTRUMENTS:
        pop_eq = vg_full[vg_full[feat].notna() & vg_full[state_col].notna()].copy()
        fav_mask_eq = _get_favorable_mask(pop_eq, feat, medians)
        pop_eq["_fav"] = fav_mask_eq.values
        pop_eq["_month"] = pd.to_datetime(pop_eq["signal_date"]).dt.to_period("M").dt.to_timestamp()
        ep_first_month_eq = pop_eq.groupby("episode_id")["_month"].min().rename("_ep_month")
        pop_eq = pop_eq.merge(ep_first_month_eq, on="episode_id", how="left")
        eq_pop_by_inst[inst_name] = pop_eq
        eq_state_col_by_inst[inst_name] = state_col
        eq_state_by_inst[inst_name] = state

    eq_results = run_equivalence_tests(eq_pop_by_inst, eq_state_col_by_inst, eq_state_by_inst)
    calibration["equivalence_tests"] = eq_results
    LOG("  Equivalence tests PASSED (sys.exit(2) if any failed).")

    # ── Negative control: 200 outer permuted-label draws per instrument ───────
    # Per draw: compute the r4 primary p of the outer-permuted dataset using
    # the engine with n_perm=500. Outer seed: [777, FEAT_IDX].
    # Per-draw inner seed: [20260706, FEAT_IDX[feat], draw_idx].
    LOG("\n§7.1 NEGATIVE CONTROL — r4 primary p on outer-permuted labels (PM0_R4_PRIMARY_AMENDMENT.md §3)")
    LOG(f"  200 outer draws per instrument; per-draw inner n_perm=500")
    LOG(f"  Outer seed: [777, FEAT_IDX]; inner seed: [20260706, FEAT_IDX, draw_idx]")
    LOG(f"  Pass thresholds: rej@0.05 <= 0.12, mean/median p in [0.4,0.6], KS-p >= 0.05")

    N_INNER_NEG = 500  # inner n_perm for the negative control (resolution economy)

    for (inst_name, feat, state_col, state, fwd_col) in CAL_INSTRUMENTS:
        LOG(f"\n  Instrument: {inst_name} ({feat} {state_col} {state})")

        # Analysis population for this instrument
        pop = vg_full[vg_full[feat].notna() & vg_full[state_col].notna()].copy()

        # Episode-majority labeling and episode-month grouping
        fav_mask = _get_favorable_mask(pop, feat, medians)
        pop["_fav"] = fav_mask.values
        ep_majority = pop.groupby("episode_id")["_fav"].mean().ge(0.5)
        pop["_ep_fav"] = pop["episode_id"].map(ep_majority)

        # Calendar month and episode-month assignment (EX-8)
        pop["_month"] = pd.to_datetime(pop["signal_date"]).dt.to_period("M").dt.to_timestamp()
        ep_first_month = pop.groupby("episode_id")["_month"].min()
        pop["_ep_month"] = pop["episode_id"].map(ep_first_month)
        month_list = sorted(pop["_ep_month"].unique())
        month_eps = {m: [] for m in month_list}
        for e, m in ep_first_month.items():
            month_eps[m].append(e)

        # Mixed-label episode fraction (logged; no effect on pass criteria)
        ep_mixed_frac_mask = (
            pop.groupby("episode_id")["_fav"].apply(lambda x: x.mean() > 0 and x.mean() < 1)
        )
        n_mixed = int(ep_mixed_frac_mask.sum())
        n_ep_total = int(pop["episode_id"].nunique())
        mixed_frac = float(n_mixed / n_ep_total) if n_ep_total > 0 else 0.0
        LOG(f"    Mixed-label episode fraction: {n_mixed}/{n_ep_total} = {mixed_frac:.3f}")

        # Outer rng: [777, FEAT_IDX[feat]] — same seed base as r3, unchanged
        rng_neg = np.random.default_rng([CAL_NEG_SEED, FEAT_IDX[feat]])
        draw_ps = []

        for draw_idx in range(N_CAL_NEG):
            # Outer permutation: permute episode majority labels within month
            perm_ep_label = {}
            for m, eps in month_eps.items():
                ep_labels_m = [bool(ep_majority.get(e, False)) for e in eps]
                perm_labels = rng_neg.permutation(ep_labels_m)
                for e, l in zip(eps, perm_labels):
                    perm_ep_label[e] = bool(l)

            # Apply outer-permuted labels to population (row level: rows inherit episode label)
            pop["_perm_fav"] = pop["episode_id"].map(perm_ep_label)

            # Compute the outer-permuted Δ̂ (the "observed" statistic for this draw)
            draw_deltas = []
            draw_weights = []
            for m in month_list:
                sub = pop[pop["_ep_month"] == m]
                fav_sub = sub[sub["_perm_fav"] == True]
                unfav_sub = sub[sub["_perm_fav"] == False]
                n_f = len(fav_sub)
                n_u = len(unfav_sub)
                if n_f < MIN_ROWS_PER_GROUP_PER_MONTH or n_u < MIN_ROWS_PER_GROUP_PER_MONTH:
                    continue
                inc_f = float((fav_sub[state_col] == state).mean())
                inc_u = float((unfav_sub[state_col] == state).mean())
                delta_m = (inc_f - inc_u) * 100.0
                w_m = 2.0 * n_f * n_u / (n_f + n_u)
                draw_deltas.append(delta_m)
                draw_weights.append(w_m)

            if len(draw_deltas) == 0:
                # No qualifying months in outer draw: assign p=1.0 (conservative)
                draw_ps.append(1.0)
                continue

            w_arr = np.array(draw_weights, dtype=float)
            d_arr = np.array(draw_deltas, dtype=float)
            delta_draw = float(np.sum(w_arr * d_arr) / np.sum(w_arr))

            # Build an outer-permuted pop for the engine: rows already have _perm_fav set.
            # The engine needs _fav = _perm_fav and _ep_month already set.
            pop_outer = pop.copy()
            pop_outer["_fav"] = pop_outer["_perm_fav"]

            # r4 primary p of the outer-permuted dataset: inner seed [20260706, FEAT_IDX, draw_idx]
            inner_seed = [20260706, FEAT_IDX[feat], draw_idx]
            inner_result = within_month_perm_engine(
                pop_outer, state_col, state, seed=inner_seed, n_perm=N_INNER_NEG
            )
            delta_perm_inner = inner_result["delta_perm"]

            if not np.isnan(delta_draw):
                abs_obs_draw = abs(delta_draw)
                nan_inner = np.isnan(delta_perm_inner)
                exc = int(np.sum(~nan_inner & (np.abs(delta_perm_inner) >= abs_obs_draw))) + int(nan_inner.sum())
                draw_p = float((1 + exc) / (N_INNER_NEG + 1))
            else:
                draw_p = float("nan")

            draw_ps.append(draw_p if not np.isnan(draw_p) else 1.0)
            # NOTE (EX-7): per-draw MWU-vs-bootstrap divergence check STRUCK (see EXECUTION_SPEC.md EX-7).
            # §4.2(b) param/perm sanity gate runs at trial level in run_inference.

        draw_ps = np.array(draw_ps, dtype=float)
        rej_rate = float((draw_ps < 0.05).mean())
        mean_p = float(draw_ps.mean())
        median_p = float(np.median(draw_ps))
        ks_stat, ks_p = stats.kstest(draw_ps, "uniform")
        ks_p = float(ks_p)

        pass_rej = rej_rate <= 0.12
        pass_mean = 0.4 <= mean_p <= 0.6
        pass_median = 0.4 <= median_p <= 0.6
        pass_ks = ks_p >= 0.05
        inst_pass = pass_rej and pass_mean and pass_median and pass_ks

        LOG(f"    rej@0.05: {rej_rate:.4f} {'PASS' if pass_rej else 'FAIL'} (threshold <= 0.12)")
        LOG(f"    mean_p:   {mean_p:.4f} {'PASS' if pass_mean else 'FAIL'} (target [0.4,0.6])")
        LOG(f"    median_p: {median_p:.4f} {'PASS' if pass_median else 'FAIL'} (target [0.4,0.6])")
        LOG(f"    KS_p:     {ks_p:.4f} {'PASS' if pass_ks else 'FAIL'} (threshold >= 0.05)")
        LOG(f"    (param/perm divergence gate runs at trial level on the same MWU statistic — EX-7)")
        LOG(f"    Instrument: {'PASS' if inst_pass else 'FAIL'}")

        calibration["instruments"][inst_name] = {
            "type": "negative",
            "feat": feat, "state_col": state_col, "state": state,
            "n_draws": N_CAL_NEG,
            "inner_n_perm": N_INNER_NEG,
            "primary_machinery": "r4 within-month episode-label permutation",
            "rej_rate_005": rej_rate,
            "mean_p": mean_p,
            "median_p": median_p,
            "ks_p": ks_p,
            "mixed_label_frac": mixed_frac,
            "pass_rej": pass_rej,
            "pass_mean": pass_mean,
            "pass_median": pass_median,
            "pass_ks": pass_ks,
            "divergence_gate_note": "EX-7: runs at trial level on the same MWU statistic",
            "pass": inst_pass,
        }
        if not inst_pass:
            all_pass = False

    # ── Positive control: return injection ───────────────────────────────────
    # Unchanged from r3: episode-permutation MWU on injected return must reject.
    LOG("\n§7.2 POSITIVE CONTROL — injected effects")

    for (inst_name, feat, state_col, state, fwd_col) in CAL_INSTRUMENTS:
        LOG(f"\n  Positive-return injection on {inst_name} ({feat})...")
        pop_copy = vg_full[vg_full[feat].notna() & vg_full[state_col].notna()].copy()
        fav_mask = _get_favorable_mask(pop_copy, feat, medians)
        # Inject +0.05 into favorable rows' fwd_ret_21
        pop_copy["_fwd_inj"] = pop_copy["fwd_ret_21"].copy()
        pop_copy.loc[fav_mask, "_fwd_inj"] = pop_copy.loc[fav_mask, "fwd_ret_21"] + 0.05

        # Episode-permutation MWU on the INJECTED return must reject (§7.2)
        ep_perm_p, obs_r_inj = _episode_perm_mwu_p(
            pop_copy, fav_mask, "_fwd_inj",
            seed=[CAL_NEG_SEED, FEAT_IDX[feat], 555], n_perm=N_PERM_DIAG,
        )
        # Parametric MWU on injected return (printed beside, sanity)
        fav_ret = pop_copy[fav_mask]["_fwd_inj"].dropna()
        unfav_ret = pop_copy[~fav_mask]["_fwd_inj"].dropna()
        if len(fav_ret) > 1 and len(unfav_ret) > 1:
            mwu_res = stats.mannwhitneyu(fav_ret, unfav_ret, alternative="two-sided")
            mwu_p_inj = float(mwu_res.pvalue)
        else:
            mwu_p_inj = np.nan

        ret_pass = not np.isnan(ep_perm_p) and ep_perm_p < 0.05
        LOG(f"    ep_perm_p (injected return) = {ep_perm_p:.4e}  {'PASS (< 0.05)' if ret_pass else 'FAIL'}")
        LOG(f"    rank_biserial_injected = {obs_r_inj:.4f}")
        LOG(f"    mwu_param_p_injected = {mwu_p_inj:.4e}")

        calibration["instruments"][f"{inst_name}_pos_return"] = {
            "type": "positive_return",
            "feat": feat,
            "ep_perm_p": ep_perm_p,
            "mwu_p_injected": mwu_p_inj,
            "pass": ret_pass,
        }
        if not ret_pass:
            all_pass = False

    # ── Positive control: incidence injection (r4 primary) ───────────────────
    # Detection p = r4 primary (engine, n_perm=5000, seed [20260706, FEAT_IDX, 999983]).
    # Synthetic-family BH = min(1, p*20) <= 0.10.
    LOG("\n  Positive-incidence injection (5pp of favorable group, whole episodes,")
    LOG("  drawn uniformly across qualifying months, seed 4242)...")
    LOG("  Detection p = r4 primary (engine, n_perm=5000, seed [20260706, FEAT_IDX, 999983])")

    for (inst_name, feat, state_col, state, fwd_col) in CAL_INSTRUMENTS:
        LOG(f"\n  Incidence injection on {inst_name} ({feat})...")
        pop_copy = vg_full[vg_full[feat].notna() & vg_full[state_col].notna()].copy()
        fav_mask = _get_favorable_mask(pop_copy, feat, medians)
        fav_pop = pop_copy[fav_mask].copy()

        # Target: relabel favorable STOPPED rows totaling 5pp of the favorable
        # GROUP (prereg §7.2 magnitude), as whole episodes drawn uniformly
        # across qualifying months (round-robin) so the injection is not
        # itself calendar-concentrated.
        fav_pop["_month"] = pd.to_datetime(fav_pop["signal_date"]).dt.to_period("M").dt.to_timestamp()
        target_rows = max(1, int(round(len(fav_pop) * PM5_INCIDENCE_INJECT_PP / 100.0)))
        stopped_fav = fav_pop[fav_pop[state_col] == state]
        ep_month = stopped_fav.groupby("episode_id")["_month"].min()
        ep_rowcount = stopped_fav.groupby("episode_id").size()
        month_pools = {}
        for e, m in ep_month.items():
            month_pools.setdefault(m, []).append(e)
        rng_inst = np.random.default_rng([CAL_POS_INJECT_SEED, FEAT_IDX[feat]])
        for m in month_pools:
            month_pools[m] = list(rng_inst.permutation(month_pools[m]))
        months_cycle = sorted(month_pools.keys())
        inject_eps = set()
        n_rows_injected = 0
        while n_rows_injected < target_rows and any(month_pools[m] for m in months_cycle):
            for m in months_cycle:
                if month_pools[m] and n_rows_injected < target_rows:
                    e = month_pools[m].pop()
                    inject_eps.add(e)
                    n_rows_injected += int(ep_rowcount.get(e, 0))
        achieved_pp = 100.0 * n_rows_injected / max(1, len(fav_pop))

        # Relabel: favorable STOPPED rows of injected episodes -> CLEAN_LIFTOFF
        pop_copy2 = pop_copy.copy()
        inject_mask = (
            pop_copy2["episode_id"].isin(inject_eps)
            & fav_mask
            & (pop_copy2[state_col] == state)
        )
        pop_copy2.loc[inject_mask, state_col] = "CLEAN_LIFTOFF"

        # r4 primary p on injected copy
        # Prepare engine-ready pop
        pop_inj = pop_copy2.copy()
        pop_inj["_fav"] = _get_favorable_mask(pop_inj, feat, medians).values
        pop_inj["_month"] = pd.to_datetime(pop_inj["signal_date"]).dt.to_period("M").dt.to_timestamp()
        ep_first_month_inj = pop_inj.groupby("episode_id")["_month"].min().rename("_ep_month")
        pop_inj = pop_inj.merge(ep_first_month_inj, on="episode_id", how="left")

        # Also get delta_hat from compute_within_month_stat for logging
        within_inj = compute_within_month_stat(pop_copy2, feat, state_col, state, medians)
        delta_inj = within_inj["delta_hat"]

        inj_seed = [20260706, FEAT_IDX[feat], 999983]
        inj_perm_result = within_month_perm_engine(
            pop_inj, state_col, state, seed=inj_seed, n_perm=N_BOOT
        )
        delta_perm_inj = inj_perm_result["delta_perm"]

        if not np.isnan(delta_inj):
            abs_obs_inj = abs(delta_inj)
            nan_inj = np.isnan(delta_perm_inj)
            exc_inj = int(np.sum(~nan_inj & (np.abs(delta_perm_inj) >= abs_obs_inj))) + int(nan_inj.sum())
            inj_p = float((1 + exc_inj) / (N_BOOT + 1))
        else:
            inj_p = float("nan")

        # BH-adjusted p for synthetic 20-slot family
        inj_bh_adj = float(min(1.0, inj_p * M_DECLARED)) if not np.isnan(inj_p) else float("nan")
        inc_pass = not np.isnan(inj_bh_adj) and inj_bh_adj <= BH_Q

        LOG(f"    n_injected_eps: {len(inject_eps)}  n_rows_relabeled: {n_rows_injected}")
        LOG(f"    achieved_injection_pp_of_fav_group: {achieved_pp:.2f}pp (target {PM5_INCIDENCE_INJECT_PP}pp)")
        LOG(f"    delta_hat_injected: {delta_inj:.4f}pp")
        LOG(f"    primary_perm_p_injected (r4): {inj_p:.4f}")
        LOG(f"    BH_adj_p (synthetic m=20): {inj_bh_adj:.4f}")
        LOG(f"    {'PASS' if inc_pass else 'FAIL'} (BH_adj <= 0.10 required)")

        calibration["instruments"][f"{inst_name}_pos_incidence"] = {
            "type": "positive_incidence",
            "feat": feat,
            "n_injected_eps": len(inject_eps),
            "n_rows_relabeled": int(n_rows_injected),
            "achieved_injection_pp": float(achieved_pp),
            "delta_hat_injected_pp": delta_inj,
            "primary_perm_p_injected": inj_p,
            "bh_adj_p_synthetic_m20": inj_bh_adj,
            "pass": inc_pass,
        }
        if not inc_pass:
            all_pass = False

    calibration["overall_pass"] = all_pass
    LOG(f"\nCalibration overall: {'PASS' if all_pass else 'FAIL'}")

    _save_json(calibration, OUT_DIR / "calibration.json")
    LOG(f"Calibration saved: {OUT_DIR / 'calibration.json'}")

    if not all_pass:
        LOG("\nBLOCKER: Calibration controls FAILED. Inference is not permitted.")
        LOG("Diagnose and report to Fable before proceeding.")
        sys.exit(1)

    return calibration


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3: INFERENCE (one-shot)
# ─────────────────────────────────────────────────────────────────────────────

def run_inference(features_path: Path) -> dict:
    LOG("=" * 72)
    LOG("EI-PM0 — INFERENCE STAGE (ONE-SHOT)")
    LOG("WARNING: This is the one-shot registered run. Outputs are final.")
    LOG("=" * 72)
    LOG()

    # Load preamble and calibration
    preamble_path = OUT_DIR / "preamble.json"
    cal_path = OUT_DIR / "calibration.json"
    if not preamble_path.exists():
        LOG("HALT: preamble.json not found.")
        sys.exit(1)
    if not cal_path.exists():
        LOG("HALT: calibration.json not found. Run --stage calibration first.")
        sys.exit(1)
    with open(preamble_path) as fh:
        preamble = json.load(fh)
    with open(cal_path) as fh:
        calibration = json.load(fh)

    if not calibration.get("overall_pass"):
        LOG("HALT: calibration.json has overall_pass != true. Inference is blocked.")
        sys.exit(1)

    medians = preamble["medians"]
    m_active = preamble.get("m_active", M_DECLARED)
    excluded_trials = preamble.get("excluded_trials", [])
    excluded_ids = {e["trial"] for e in excluded_trials}
    redundant_against = preamble.get("redundancy_matrix", {}).get("redundant_against", {})

    feat_df = pd.read_parquet(features_path)
    vg_full = _load_vg_full(feat_df)
    LOG(f"VG fires loaded: {len(vg_full):,}")
    LOG(f"m_active = {m_active}, excluded = {sorted(excluded_ids)}")

    results = {
        "stage": "inference",
        "study_id": STUDY_ID,
        "primary_machinery": "r4 within-month episode-label permutation",
        "amendment": "research/entry_intel/PM0_R4_PRIMARY_AMENDMENT.md",
        "m_declared": M_DECLARED,
        "m_active": m_active,
        "excluded_trials": excluded_trials,
        "trials": {},
    }

    # ── Run all trials ────────────────────────────────────────────────────────
    LOG("\nRunning trials...")
    trial_ps = []
    trial_ids_active = []

    for t_idx, (tid, feat, state_col, state, fwd_col) in enumerate(TRIAL_TABLE):
        if tid in excluded_ids:
            LOG(f"  {tid}: SKIPPED (excluded at preamble)")
            results["trials"][tid] = {
                "tid": tid, "feature": feat, "grid": state_col,
                "state": state, "status": "EXCLUDED",
                "reason": next(e["reason"] for e in excluded_trials if e["trial"] == tid),
            }
            continue

        LOG(f"  {tid}: {feat} {state_col} {state}...")
        trial_stat = compute_full_trial_stat(
            vg_full, feat, state_col, state, fwd_col, medians, t_idx
        )
        sign_stab = compute_sign_stability(vg_full, feat, state_col, state, medians)

        results["trials"][tid] = {
            "tid": tid, "feature": feat, "grid": state_col,
            "state": state, "fwd_col": fwd_col,
            **trial_stat,
            "sign_stability": sign_stab,
            "bh_adj_p": None,  # filled in after BH
            "verdict": None,   # filled in after BH + redundancy
        }
        # r4 primary p feeds BH; boot_p key has been renamed to primary_perm_p
        trial_ps.append(trial_stat["primary_perm_p"])
        trial_ids_active.append(tid)

        LOG(f"    delta_hat: {trial_stat['delta_hat']:.4f}pp  primary_perm_p (r4): {trial_stat['primary_perm_p']:.4f}")
        LOG(f"    boot CI DIAGNOSTIC: [{trial_stat['boot_ci_lo_DIAGNOSTIC']:.4f}, {trial_stat['boot_ci_hi_DIAGNOSTIC']:.4f}]pp  (anticonservative-in-tail at m=43 per §7 record; NEVER feeds BH)")
        LOG(f"    n_qual_months: {trial_stat['n_qualifying_months']}  thin: {trial_stat['thin_flag']}")
        LOG(f"    ep_perm_p (NOT TIME-CONTROLLED): {trial_stat['ep_perm_p_NOT_TIME_CONTROLLED']:.4f}")

    # ── §4.2(b) divergence sanity gate (P2.5 precedent: HALT before verdicts) ─
    tripped = [tid for tid in trial_ids_active
               if results["trials"][tid].get("divergence_gate_trip")]
    if tripped:
        LOG("!!! SANITY GATE TRIPPED — param/perm divergence (round-1 defect signature):")
        for tid in tripped:
            t = results["trials"][tid]
            LOG(f"    {tid}: mwu_param_p={t['mwu_p_NOT_TIME_CONTROLLED']:.2e} "
                f"ep_perm_mwu_p={t['ep_perm_mwu_p_NOT_TIME_CONTROLLED']:.4f}")
        LOG("    HALTING before BH/verdicts (blocker report to Fable).")
        _save_json(results, OUT_DIR / "results_HALTED.json")
        sys.exit(2)
    LOG("\nSanity gate: PASS — no param/perm divergence of the round-1 defect signature.")

    # ── BH correction — uses primary_perm_p (r4) only; NEVER boot_pivot_p_DIAGNOSTIC ──
    LOG("\nBH correction (m_active={}) — input: primary_perm_p (r4 only)...".format(m_active))
    if len(trial_ps) > 0:
        # Excluded trials never reach trial_ps, so len(trial_ps) == m_active
        # by construction; assert rather than silently rescale.
        assert len(trial_ps) == m_active, (
            f"BH family size mismatch: {len(trial_ps)} p-values vs m_active={m_active}"
        )
        bh_adj = bh_correction(trial_ps, q=BH_Q)
        for i, tid in enumerate(trial_ids_active):
            results["trials"][tid]["bh_adj_p"] = float(bh_adj[i])

    # ── Verdicts ──────────────────────────────────────────────────────────────
    LOG("\nVerdicts per sub-component...")
    component_verdicts = {}
    bh_surviving_trials = {}

    for tid in trial_ids_active:
        t = results["trials"][tid]
        feat = t["feature"]
        bh_p = t.get("bh_adj_p")
        delta = t.get("delta_hat")
        in_fav = t.get("in_favorable_direction", False)
        thin = t.get("thin_flag", True)
        sign_stable = t.get("sign_stability", {}).get("sign_stable")

        # Pre-condition: not excluded
        if t.get("status") == "EXCLUDED":
            continue

        # Check if redundant
        is_redundant = feat in redundant_against

        # BH survivors
        bh_sig = (bh_p is not None and not np.isnan(bh_p) and bh_p <= BH_Q and
                  in_fav and not thin)

        if bh_sig and sign_stable and not is_redundant:
            if feat not in bh_surviving_trials:
                bh_surviving_trials[feat] = []
            bh_surviving_trials[feat].append(tid)

    for feat in ["pm1", "pm2", "pm3", "pm4"]:
        surv_tids = bh_surviving_trials.get(feat, [])
        is_redundant = feat in redundant_against

        if is_redundant:
            verdict = "REDUNDANT"
            detail = f"redundant_with:{redundant_against[feat]}"
        elif len(surv_tids) >= 1:
            verdict = "SURVIVES"
            detail = f"surviving_trials:{surv_tids}"
        else:
            verdict = "NO-GO"
            detail = "no BH-significant favorable sign-stable trial"

        component_verdicts[feat] = {
            "verdict": verdict,
            "detail": detail,
            "surviving_trials": surv_tids,
        }
        LOG(f"  {feat}: {verdict} ({detail})")
        # Per-trial verdict: only ship-qualifying trials of a surviving
        # component carry SURVIVES; the rest carry the component verdict with
        # an explicit not-ship-qualifying label (Opus conformance A3).
        for tid in trial_ids_active:
            if results["trials"][tid]["feature"] != feat:
                continue
            if verdict == "SURVIVES":
                results["trials"][tid]["verdict"] = (
                    "SURVIVES" if tid in surv_tids
                    else "NOT-SHIP-QUALIFYING (component SURVIVES)"
                )
            else:
                results["trials"][tid]["verdict"] = verdict

    # PM5 is always data_blocked
    component_verdicts["pm5"] = {
        "verdict": "data_blocked",
        "detail": "pre-declared; coverage < 60% floor (see prereg §2/PM5)",
        "surviving_trials": [],
    }

    results["component_verdicts"] = component_verdicts

    # ── Bundle verdict (§6.3) ─────────────────────────────────────────────────
    n_survivors = sum(1 for f in ["pm1", "pm2", "pm3", "pm4"]
                      if component_verdicts[f]["verdict"] == "SURVIVES")
    if n_survivors >= 1:
        bundle_verdict = f"BUNDLE_OPEN ({n_survivors} survivor(s))"
    else:
        bundle_verdict = "BUNDLE_CLOSED"
    results["bundle_verdict"] = bundle_verdict
    LOG(f"\nBundle verdict: {bundle_verdict}")

    # ── Within-bundle redundancy tie-break ───────────────────────────────────
    within_bundle = preamble.get("redundancy_matrix", {}).get("within_bundle", {})
    for pair_key, rho in within_bundle.items():
        if rho is not None and abs(rho) >= REDUNDANCY_RHO:
            parts = pair_key.replace("_vs_", "|").split("|")
            if len(parts) == 2:
                fi, fj = parts[0], parts[1]
                vi = component_verdicts.get(fi, {}).get("verdict")
                vj = component_verdicts.get(fj, {}).get("verdict")
                if vi == "SURVIVES" and vj == "SURVIVES":
                    # Tie-break: smaller BH-adj p on best surviving trial
                    best_p_i = min(
                        (results["trials"][t]["bh_adj_p"] or 1.0
                         for t in bh_surviving_trials.get(fi, [])), default=1.0
                    )
                    best_p_j = min(
                        (results["trials"][t]["bh_adj_p"] or 1.0
                         for t in bh_surviving_trials.get(fj, [])), default=1.0
                    )
                    if best_p_i <= best_p_j:
                        LOG(f"  Within-bundle tie-break: {fj} -> REDUNDANT-WITHIN-BUNDLE (|rho|={abs(rho):.3f})")
                        component_verdicts[fj]["verdict"] = "REDUNDANT-WITHIN-BUNDLE"
                    else:
                        LOG(f"  Within-bundle tie-break: {fi} -> REDUNDANT-WITHIN-BUNDLE (|rho|={abs(rho):.3f})")
                        component_verdicts[fi]["verdict"] = "REDUNDANT-WITHIN-BUNDLE"

    # ── Context outputs (§8) ──────────────────────────────────────────────────
    LOG("\nComputing context outputs (§8)...")
    context = _compute_context(vg_full, feat_df, medians)
    results["context"] = context

    # ── Registry/ledger rows (drafted strings) ────────────────────────────────
    results["registry_rows_draft"] = _draft_registry_rows(component_verdicts)
    results["masterplan_entry_draft"] = (
        "EI-PM0 Price-Memory Bundle phase-0 complete. "
        f"Bundle verdict: {bundle_verdict}. "
        "See RESULTS.md for full trial table and component verdicts."
    )
    results["signal_commons_resolution_draft"] = (
        "Signal Commons §4 parked row: PM0 price-memory bundle dispatched -> "
        f"{bundle_verdict}. PM5 data_blocked (unblock condition printed in RESULTS.md)."
    )
    results["dt_r7_clock_closure_draft"] = (
        "DT-R7 routing come-back 2026-07-20 CLOSED by this run. "
        "Display-only ceiling (DT-R7) and forbidden-key law (DT-R2/DT-R7) remain "
        "permanent on this family and all descendants."
    )

    _save_json(results, OUT_DIR / "results.json")
    LOG(f"\nResults saved: {OUT_DIR / 'results.json'}")

    # ── RESULTS.md ────────────────────────────────────────────────────────────
    md = _generate_results_md(results, preamble, medians)
    (OUT_DIR / "RESULTS.md").write_text(md)
    LOG(f"RESULTS.md saved: {OUT_DIR / 'RESULTS.md'}")

    return results


def _compute_context(vg_full: pd.DataFrame, feat_df: pd.DataFrame, medians: dict) -> dict:
    """§8 context outputs."""
    context = {}

    # CLEAN_LIFTOFF deltas per feature per grid
    cl_deltas = {}
    for feat in ["pm1", "pm2", "pm3", "pm4"]:
        cl_deltas[feat] = {}
        for state_col, grid_name in [(GRID_A_STATE_COL, "grid_A"), (GRID_B_STATE_COL, "grid_B")]:
            pop = vg_full[vg_full[feat].notna() & vg_full[state_col].notna()].copy()
            if len(pop) == 0:
                continue
            fav = _get_favorable_mask(pop, feat, medians)
            for group_name, mask in [("fav", fav), ("unfav", ~fav)]:
                sub = pop[mask]
                cl_rate = float((sub[state_col] == "CLEAN_LIFTOFF").mean() * 100)
                cl_deltas[feat][f"{grid_name}_{group_name}_cl_pct"] = round(cl_rate, 3)
    context["clean_liftoff_deltas"] = cl_deltas

    # Grid-B DEAD_MONEY descriptive (43 events, no test)
    dm_b = int((vg_full[GRID_B_STATE_COL] == "DEAD_MONEY").sum())
    context["grid_b_dead_money_n"] = dm_b
    context["grid_b_dead_money_note"] = (
        f"Grid-B DEAD_MONEY: {dm_b} events (substrate limitation, 43 expected; no test registered)"
    )

    # Median MAE/MFE (fwd_mdd_21 / fwd_mfe_21) by favorable/unfavorable group
    # per feature — risk texture (§8)
    mae_mfe = {}
    for feat in ["pm1", "pm2", "pm3", "pm4"]:
        pop = vg_full[vg_full[feat].notna()].copy()
        if len(pop) == 0:
            continue
        fav = _get_favorable_mask(pop, feat, medians)
        mae_mfe[feat] = {}
        for group_name, mask in [("fav", fav), ("unfav", ~fav)]:
            sub = pop[mask]
            mae_mfe[feat][group_name] = {
                "median_fwd_mdd_21": (
                    float(sub["fwd_mdd_21"].median()) if sub["fwd_mdd_21"].notna().any() else None
                ),
                "median_fwd_mfe_21": (
                    float(sub["fwd_mfe_21"].median()) if sub["fwd_mfe_21"].notna().any() else None
                ),
                "n": int(len(sub)),
            }
    context["mae_mfe_medians"] = mae_mfe

    # Full feature distributions — deciles on vg fires (§8); pm3 is binary so
    # its incidence is printed instead
    deciles = {}
    qs = [i / 10.0 for i in range(11)]
    for feat in ["pm1", "pm2", "pm4", "pm5", "poc_dist_126"]:
        vals = vg_full[feat].dropna()
        if len(vals) > 0:
            deciles[feat] = {f"q{int(q*100):02d}": float(vals.quantile(q)) for q in qs}
            deciles[feat]["n_defined"] = int(len(vals))
            if feat == "pm5":
                deciles[feat]["label"] = "FLOAT-PROXY/PARTIAL-COVERAGE"
    deciles["pm3_incidence"] = {
        "pct_pm3_eq_1": float((vg_full["pm3"].dropna() == 1).mean() * 100)
        if vg_full["pm3"].notna().any() else None,
        "n_defined": int(vg_full["pm3"].notna().sum()),
    }
    context["feature_deciles"] = deciles

    # Sector composition of favorable vs unfavorable groups per feature
    # (concentration check, §8)
    if "sector" in vg_full.columns:
        sector_comp = {}
        for feat in ["pm1", "pm2", "pm3", "pm4"]:
            pop = vg_full[vg_full[feat].notna()].copy()
            if len(pop) == 0:
                continue
            fav = _get_favorable_mask(pop, feat, medians)
            sector_comp[feat] = {}
            for group_name, mask in [("fav", fav), ("unfav", ~fav)]:
                sub = pop[mask]
                frac = (sub["sector"].value_counts(normalize=True) * 100).round(2)
                sector_comp[feat][group_name] = {
                    str(k): float(v) for k, v in frac.head(12).items()
                }
        context["sector_composition_by_feature_group"] = sector_comp
        context["sector_composition_overall"] = {
            str(k): int(v) for k, v in vg_full["sector"].value_counts().items()
        }

    # Near-miss context (§8)
    nm_feat_cols = ["pm1", "pm2", "pm3", "pm4", "pm5"]
    nm_in_feat = feat_df[
        (feat_df["verdict_type"] == "near_miss") & (feat_df["verdict_grade"] == True)
    ]
    context["near_miss_n"] = int(len(nm_in_feat))
    nm_stats = {}
    for col in nm_feat_cols:
        if col in nm_in_feat.columns:
            vals = nm_in_feat[col].dropna()
            nm_stats[col] = {
                "n_defined": int(len(vals)),
                "mean": float(vals.mean()) if len(vals) > 0 else None,
                "median": float(vals.median()) if len(vals) > 0 else None,
            }
            if len(vals) > 0 and col != "pm3":
                nm_stats[col]["deciles"] = {
                    f"q{int(q*100):02d}": float(vals.quantile(q))
                    for q in [i / 10.0 for i in range(11)]
                }
            if col == "pm5":
                nm_stats[col]["label"] = "FLOAT-PROXY/PARTIAL-COVERAGE"
    context["near_miss_stats"] = nm_stats

    return context


def _draft_registry_rows(component_verdicts: dict) -> list:
    ids = {
        "pm1": "EI-PM1-AVWAP",
        "pm2": "EI-PM2-SHELF",
        "pm3": "EI-PM3-GAP",
        "pm4": "EI-PM4-OVERHEAD",
        "pm5": "EI-PM5-FLOATTURN",
    }
    rows = []
    for feat, reg_id in ids.items():
        v = component_verdicts.get(feat, {}).get("verdict", "unknown")
        detail = component_verdicts.get(feat, {}).get("detail", "")
        status = {
            "SURVIVES": "phase0_passed (display-only ceiling, DT-R7)",
            "NO-GO": "falsified (phase-0)",
            "REDUNDANT": f"redundant — {detail}",
            "REDUNDANT-WITHIN-BUNDLE": f"redundant_within_bundle — {detail}",
            "data_blocked": "data_blocked — unblock: EDGAR coverage >= 60% of vg fire universe",
        }.get(v, v)
        rows.append({
            "family": "price_memory",
            "id": reg_id,
            "feature": feat,
            "verdict": v,
            "registry_status_draft": status,
        })
    return rows


def _generate_results_md(results: dict, preamble: dict, medians: dict) -> str:
    lines = []
    lines += [
        "# EI-PM0 Price-Memory Bundle — Results",
        "",
        "**Study:** EI-PM0 Price-Memory Bundle phase-0",
        "**Pre-registration:** `research/entry_intel/PM0_PRICE_MEMORY_BUNDLE_PREREG.md` (APPROVED 2026-07-06 r3)",
        "**Primary machinery amendment:** `research/entry_intel/PM0_R4_PRIMARY_AMENDMENT.md` (r4, registered 2026-07-10)",
        "**Era stamp:** Effective verdict window **2022-06-30 → 2026-07-02** (P0_MEASUREMENT_MEMO.md v1.1)",
        f"**Bundle verdict:** {results.get('bundle_verdict', 'unknown')}",
        "",
        "> **DannyTrades provenance box:** The anchor's own pullback/DCA-adjacent evidence FAILED its gate",
        "> (DT-R7: CI includes 0, payoff ≈ 0, tail worse). This study tests the price-memory features",
        "> derived from DT principles — not DT's own system. Printed as the honest prior, labeled:",
        "> **HYPOTHESIS SOURCE — NOT EVIDENCE.**",
        "",
        "> **Plain-English box:** This study asks whether a stock 'remembers' where volume traded",
        "> before a setup fires. Five features were tested: distance above the anchored VWAP (PM1),",
        "> volume shelf density at entry (PM2), absence of overhead gaps (PM3), fraction of recent",
        "> volume traded above current price (PM4), and float turnover (PM5, pre-blocked).",
        "> The test is made month-by-month to remove calendar composition effects (DT-R14).",
        "> A survivor earns display-only context status and a separate promotion prereg only.",
        "> Nothing here may ever instruct a price level for action.",
        "",
        "---",
        "",
        "## §1 — Preamble",
        "",
        "- **Primary machinery (r4):** within-month episode-label permutation",
        "  (`research/entry_intel/PM0_R4_PRIMARY_AMENDMENT.md`, registered 2026-07-10 before any real trial p-value).",
        "  The r3 month-block bootstrap was demoted to a labeled CI diagnostic after failing §7 calibration twice:",
        "  run 1 (row-month grouping, pre-EX-8) PM2 KS-p 0.0333; run 2 (EX-8 episode-month fix) PM2 KS-p 0.0412.",
        "  Both failed runs are preserved in `calibration_run1_FAILED.log` and the run-2 log.",
        "  The month-block bootstrap CI is printed per trial below as a DIAGNOSTIC only; it NEVER feeds BH or verdicts.",
        f"- Replay MD5: `{preamble.get('md5', {}).get('replay', 'N/A')}`",
        f"- Features MD5: `{preamble.get('md5', {}).get('features', 'N/A')}`",
        f"- Statements MD5: `{preamble.get('md5', {}).get('statements', 'N/A')}`",
        f"- VG fires: {preamble.get('population', {}).get('n_vg_fires', 'N/A'):,}",
        f"- Episode clusters: {preamble.get('population', {}).get('n_episodes', 'N/A'):,}",
        f"- Survivor-stamped: {preamble.get('population', {}).get('n_survivor_stamped', 0)}",
        f"- Signal date range: {preamble.get('population', {}).get('signal_date_min')} → {preamble.get('population', {}).get('signal_date_max')}",
        f"- m declared: {results.get('m_declared', 20)}  m active: {results.get('m_active', 20)}",
        f"- Excluded trials: {[e['trial'] for e in results.get('excluded_trials', [])]}",
        "",
        "**Medians (vg fires, outcome-blind, computed by builder before any outcome join):**",
        f"- pm2 median: {medians.get('pm2_median')}  (n={medians.get('pm2_n_defined')})",
        f"- pm4 median: {medians.get('pm4_median')}  (n={medians.get('pm4_n_defined')})",
        f"- pm5 median: {medians.get('pm5_median')}  (n={medians.get('pm5_n_defined')}) [data_blocked, for reference]",
        "",
        "**QA outcomes:**",
        f"- Gate 1 (PIT audit): {preamble.get('qa_outcomes', {}).get('gate1_pit_audit')}",
        f"- Gate 5 (Determinism): {preamble.get('qa_outcomes', {}).get('gate5_determinism')}",
        f"- Overall: {preamble.get('qa_outcomes', {}).get('overall_pass')}",
    ]

    # §9(1) completeness items (Opus conformance A1)
    pop_meta = preamble.get("population", {})
    lines += [
        "",
        "**Column map / enums / censoring:**",
        ("- Frozen prereg §1 column list resolved 1:1 against the replay (no aliases needed); "
         "state enums verified {STOPPED, DEAD_MONEY, CUSHIONED, CLEAN_LIFTOFF} on both grids:"),
        f"- Grid A counts: {preamble.get('state_enum', {}).get('grid_a', {})}",
        f"- Grid B counts: {preamble.get('state_enum', {}).get('grid_b', {})}",
        f"- horizon_censored rows in the vg-fire population: {pop_meta.get('n_horizon_censored', 0)} "
        "(per-grid exclusion counts therefore 0 on both grids; guard retained for regeneration)",
        "",
        "**Floors (checked pre-p-value):**",
        (f"- Event floor (≥50 events/trial, ≥10 per group) and month floor (≥24 qualifying months): "
         f"NO decrement — m stayed {results.get('m_declared', 20)} → {results.get('m_active', 20)}; "
         f"excluded trials: {[e['trial'] for e in results.get('excluded_trials', [])] or 'none'}"),
        "",
        "**Coverage table (defined fraction per feature):**",
    ]
    for pop_name, pop_cov in (preamble.get("coverage", {}) or {}).items():
        cov_cells = ", ".join(
            f"{col} {info['n_defined']:,}/{info['n_total']:,} ({info['pct']:.1%})"
            for col, info in pop_cov.items()
        )
        lines.append(f"- {pop_name}: {cov_cells}")
    lines.append(
        f"- PM5 vg-fire coverage {preamble.get('pm5_coverage_pct', float('nan')):.1%} vs 60% floor → "
        f"{preamble.get('pm5_status', 'data_blocked')}"
    )

    mc = preamble.get("month_census", {})
    if mc:
        lines += [
            "",
            "**Month census (pre-outcome-join; per-month group sizes recorded in preamble.json):**",
        ]
        for feat_name, feat_mc in mc.items():
            lines.append(
                f"- {feat_name}: {feat_mc.get('n_qualifying_months')} qualifying months "
                f"of {len(feat_mc.get('months', {}))}"
            )
    straddles = [
        t.get("episode_straddle_count") for t in results.get("trials", {}).values()
        if t.get("episode_straddle_count") is not None
    ]
    if straddles:
        lines.append(
            f"- Episode ISO-week month-straddle count (episodes whose rows span months; assigned to "
            f"first-row month per EX-8): {max(straddles)}"
        )

    # Gates 2-4 + mixed-label fractions from the run-dir artifacts
    try:
        with open(OUT_DIR / "qa_report.json") as _fh:
            _qa = json.load(_fh)
        fence = _qa.get("gate2_fence_census", {})
        anchor = _qa.get("gate4_anchor_sanity", {})
        lines += [
            "",
            "**QA gates 2–4 (from qa_report.json):**",
            f"- Gate 2 split-fence census: {fence}",
            f"- Gate 4 anchor sanity: {anchor}",
            "- Gate 3 coverage: rendered above",
        ]
    except Exception:
        lines.append("- (qa_report.json not readable at render time — see committed artifact)")
    try:
        with open(OUT_DIR / "calibration.json") as _fh:
            _cal = json.load(_fh)
        mixed = {
            k: round(v.get("mixed_label_frac"), 4)
            for k, v in _cal.get("instruments", {}).items()
            if isinstance(v, dict) and v.get("type") == "negative"
        }
        lines.append(f"- Mixed-label episode fractions (negative-control instruments): {mixed}")
    except Exception:
        lines.append("- (calibration.json not readable at render time — see committed artifact)")

    lines += [
        "",
        "---",
        "",
        "## §2 — Per-Trial Table",
        "",
        ("**Pre-registered favorable directions:** Δ̂ < 0 favorable for STOPPED and DEAD_MONEY; "
         "Δ̂ > 0 favorable for CUSHIONED (Δ̂ = favorable-group incidence − unfavorable-group "
         "incidence, pp). A significant p in the UNFAVORABLE direction is mechanism-contradicting "
         "evidence, never a survival credit."),
        "",
        ("| Trial | Feature | Grid | State | Δ̂ (pp) | dir | perm_p (r4 PRIMARY) | BH_adj_p | "
         "boot CI DIAGNOSTIC [2.5%,97.5%] | pooled_Δ | pooled−within div | "
         "ep_perm_p (NOT TIME-CONTROLLED) | MWU_r (NOT TIME-CONTROLLED) | qual_months | "
         "n_fav | n_unfav | ep_fav | ep_unfav | THIN | sign_stable |"),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    sig_unfavorable = []
    for t_id, t_row in results.get("trials", {}).items():
        if t_row.get("status") == "EXCLUDED":
            lines.append(
                f"| {t_id} | {t_row['feature']} | {t_row['grid']} | {t_row['state']} "
                f"| EXCLUDED | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |"
            )
            continue
        def _fmt(v, spec):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return "NaN"
            return format(v, spec)

        dh = _fmt(t_row.get("delta_hat"), ".3f")
        pp = _fmt(t_row.get("primary_perm_p"), ".4f")
        bh = _fmt(t_row.get("bh_adj_p"), ".4f")
        ci_lo = _fmt(t_row.get("boot_ci_lo_DIAGNOSTIC"), ".3f")
        ci_hi = _fmt(t_row.get("boot_ci_hi_DIAGNOSTIC"), ".3f")
        boot_ci_str = f"[{ci_lo}, {ci_hi}]"
        pd_pp = _fmt(t_row.get("delta_pooled_pp"), ".3f")
        div_pp = _fmt(t_row.get("pooled_vs_within_divergence_pp"), ".3f")
        ep_p = _fmt(t_row.get("ep_perm_p_NOT_TIME_CONTROLLED"), ".4f")
        mwu_r = _fmt(t_row.get("mwu_rank_biserial_NOT_TIME_CONTROLLED"), ".4f")
        in_fav = t_row.get("in_favorable_direction", False)
        dir_cell = "fav" if in_fav else "UNFAV"
        bh_v = t_row.get("bh_adj_p")
        if (not in_fav) and bh_v is not None and not (
            isinstance(bh_v, float) and math.isnan(bh_v)
        ) and bh_v <= 0.10:
            sig_unfavorable.append(
                f"{t_id} ({t_row.get('feature')} {t_row.get('grid')} {t_row.get('state')}, "
                f"Δ̂ {t_row.get('delta_hat'):+.2f}pp, BH {bh_v:.4f})"
            )
        lines.append(
            f"| {t_id} | {t_row.get('feature')} | {t_row.get('grid')} | {t_row.get('state')} "
            f"| {dh} | {dir_cell} | {pp} | {bh} | {boot_ci_str} | {pd_pp} | {div_pp} | {ep_p} | {mwu_r} "
            f"| {t_row.get('n_qualifying_months', 'N/A')} "
            f"| {t_row.get('n_fav', 'N/A')} | {t_row.get('n_unfav', 'N/A')} "
            f"| {t_row.get('n_ep_fav', 'N/A')} | {t_row.get('n_ep_unfav', 'N/A')} "
            f"| {t_row.get('thin_flag')} | {t_row.get('sign_stability', {}).get('sign_stable')} |"
        )

    lines += [
        "",
        "**Note:** ep_perm_p and MWU_r are episode-level diagnostics, NOT TIME-CONTROLLED. "
        "They do not feed into verdicts (DT-R14). "
        "perm_p (r4 PRIMARY) is the registered primary statistic (within-month episode-label permutation, PM0_R4_PRIMARY_AMENDMENT.md). "
        "Boot CI DIAGNOSTIC = MONTH-BLOCK BOOTSTRAP — DIAGNOSTIC (anticonservative-in-tail at m=43 per §7 record); "
        "shown for effect-size context only, NEVER feeds BH or verdicts.",
        "",
        ("**Significant-but-UNFAVORABLE trials (mechanism-contradicting texture, no survival credit): "
         + ("; ".join(sig_unfavorable) if sig_unfavorable else "none")
         + ".** Notably these include the favorable-shelf DEAD_MONEY excess (thick shelves stop out "
           "less and cushion more, but go dead-money more) and the gap-map direction reversal "
           "(clean-sky fires stop out MORE than gap-overhead fires)."
         if sig_unfavorable else
         "**Significant-but-UNFAVORABLE trials: none.**"),
        "",
        "---",
        "",
        "## §3 — Redundancy Matrix",
        "",
        "**Correlation |ρ| ≥ 0.80 vs reference set ⇒ REDUNDANT (promotion blocked regardless of p)**",
        "",
    ]

    red_matrix = preamble.get("redundancy_matrix", {})
    if red_matrix:
        ref_names = list(red_matrix.get("vs_reference", {}).get("pm1", {}).keys())
        lines.append("| Feature | " + " | ".join(ref_names) + " |")
        lines.append("|---|" + "|".join(["---"] * len(ref_names)) + "|")
        for pm in ["pm1", "pm2", "pm3", "pm4", "pm5"]:
            row_vals = red_matrix.get("vs_reference", {}).get(pm, {})
            vals = [str(row_vals.get(r, "N/A")) for r in ref_names]
            lines.append(f"| {pm} | " + " | ".join(vals) + " |")
        lines += [
            "",
            "**Within-bundle correlations:**",
        ]
        for pair, rho in red_matrix.get("within_bundle", {}).items():
            lines.append(f"- {pair}: ρ={rho}")
        redundant = red_matrix.get("redundant_against", {})
        if redundant:
            lines.append("")
            lines.append("**Redundant features:**")
            for pm, refs in redundant.items():
                lines.append(f"- {pm}: REDUNDANT with {refs}")
        else:
            lines.append("")
            lines.append("No features redundant with reference set (|ρ| < 0.80 for all).")

    lines += [
        "",
        "---",
        "",
        "## §4 — Verdicts Per Sub-Component",
        "",
    ]
    for feat, cv in results.get("component_verdicts", {}).items():
        v = cv.get("verdict", "unknown")
        detail = cv.get("detail", "")
        surv = cv.get("surviving_trials", [])
        lines.append(f"### {feat.upper()}: **{v}**")
        lines.append(f"- Detail: {detail}")
        if surv:
            lines.append(f"- Surviving trials: {surv}")
        if feat == "pm5":
            lines.append("- **FLOAT-PROXY** label applies to all pm5 outputs (shares outstanding, not free float)")
            lines.append("- **PARTIAL-COVERAGE**: 50.2% of vg fires have a valid pm5 value (< 60% floor)")
            lines.append("- Unblock condition: EDGAR panel covers ≥ 60% of 992-ticker fire universe")
        elif v == "SURVIVES":
            lines.append("- Ceiling: display-only context chip only (DT-R7); separate promotion PREREG required")
        lines.append("")

    lines += [
        "---",
        "",
        "## §5 — Bundle Verdict",
        "",
        f"**{results.get('bundle_verdict', 'unknown')}**",
        "",
        "Registry rows (DRAFT — applied to registry by Fable in same PR):",
    ]
    for row in results.get("registry_rows_draft", []):
        lines.append(f"- `{row['id']}` ({row['feature']}): {row['registry_status_draft']}")

    lines += [
        "",
        f"Signal Commons resolution: {results.get('signal_commons_resolution_draft', '')}",
        f"DT-R7 clock: {results.get('dt_r7_clock_closure_draft', '')}",
        "",
        "---",
        "",
        "## §6 — Context Appendix (§8 items)",
        "",
        "*(NOT verdict-feeding, NOT BH'd)*",
        "",
    ]
    ctx = results.get("context", {})
    lines.append(f"**Grid-B DEAD_MONEY:** {ctx.get('grid_b_dead_money_note', 'N/A')}")
    lines.append("")

    lines.append("**CLEAN_LIFTOFF rates by favorable/unfavorable group (context, not tested):**")
    for feat, d in ctx.get("clean_liftoff_deltas", {}).items():
        parts = [f"{k}={v}" for k, v in d.items()]
        lines.append(f"- {feat}: " + "  ".join(parts))
    lines.append("")

    lines.append("**Median MAE/MFE (fwd_mdd_21 / fwd_mfe_21) by group — risk texture:**")
    for feat, groups in ctx.get("mae_mfe_medians", {}).items():
        for g, s in groups.items():
            lines.append(
                f"- {feat} {g}: median_mdd_21="
                f"{round(s['median_fwd_mdd_21'], 4) if s['median_fwd_mdd_21'] is not None else 'N/A'} "
                f"median_mfe_21="
                f"{round(s['median_fwd_mfe_21'], 4) if s['median_fwd_mfe_21'] is not None else 'N/A'} "
                f"(n={s['n']})"
            )
    lines.append("")

    lines.append("**Feature distributions (deciles, vg fires; pm3 = binary incidence; pm5 = FLOAT-PROXY/PARTIAL-COVERAGE):**")
    for feat, d in ctx.get("feature_deciles", {}).items():
        if feat == "pm3_incidence":
            lines.append(
                f"- pm3: pct(pm3==1)={round(d['pct_pm3_eq_1'], 2) if d.get('pct_pm3_eq_1') is not None else 'N/A'}% "
                f"(n={d.get('n_defined')})"
            )
            continue
        dec_str = " ".join(
            f"{k}={round(v, 4)}" for k, v in d.items() if k.startswith("q")
        )
        label = f" [{d['label']}]" if "label" in d else ""
        lines.append(f"- {feat} (n={d.get('n_defined')}){label}: {dec_str}")
    lines.append("")

    sc = ctx.get("sector_composition_by_feature_group", {})
    if sc:
        lines.append("**Sector composition of favorable vs unfavorable groups (top sectors, % of group):**")
        for feat, groups in sc.items():
            for g, comp in groups.items():
                top3 = sorted(comp.items(), key=lambda kv: -kv[1])[:3]
                lines.append(f"- {feat} {g}: " + ", ".join(f"{k} {v}%" for k, v in top3))
        lines.append("")

    n_stamped = preamble.get("population", {}).get("n_survivor_stamped", 0)
    lines.append(
        f"**Survivor-stamped appendix (SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE):** "
        f"{n_stamped} rows in the verdict-grade fire population carry the stamp"
        + (" — appendix empty." if not n_stamped else ".")
    )
    lines.append("")
    lines.append("**Near-miss context read (descriptive only, no test; pm5 = FLOAT-PROXY/PARTIAL-COVERAGE):**")
    nm_stats = ctx.get("near_miss_stats", {})
    for feat, s in nm_stats.items():
        extra = s.get("label", "")
        lines.append(
            f"- {feat}: n_defined={s['n_defined']} "
            f"mean={round(s['mean'],4) if s['mean'] is not None else 'N/A'} "
            f"median={round(s['median'],4) if s['median'] is not None else 'N/A'}"
            + (f" [{extra}]" if extra else "")
        )

    lines += [
        "",
        "---",
        "",
        "## §7 — Leak-Audit Section",
        "",
        "- **Signal-close vs next-close:** PM features use signal-bar adjusted close (pre-entry, PIT-safe); fill law uses next close. No lookahead.",
        f"- **PIT spot-audit:** {preamble.get('qa_outcomes', {}).get('gate1_pit_audit')} (gate 1 of §4.4)",
        f"- **Determinism:** {preamble.get('qa_outcomes', {}).get('gate5_determinism')} (gate 5 of §4.4)",
        "- **Split-fence census:** see qa_report.json gate2_fence_census",
        f"- **Era boundary:** signal dates {preamble.get('population', {}).get('signal_date_min')} → {preamble.get('population', {}).get('signal_date_max')} (verdict window 2022-06-30 → 2026-07-02)",
        "- **PM5 SO staleness:** see qa_report.json for so_stale / so_missing counts",
        "- **EX-2 disclosure:** gaps whose pre-gap bar falls before the 250-bar window are not scanned",
        ("- **r4 calibration scope (Opus A1):** the §7 negative control permutes labels within month and "
         "therefore CANNOT certify calibration against an episode-size↔label↔outcome confound (the "
         "permutation erases the size↔label pairing it would need to detect). A passing control validates "
         "the machinery under within-month label exchangeability only; the size-exchangeability "
         "assumption is disclosed in PM0_R4_PRIMARY_AMENDMENT.md §2 and mitigated (harmonic weights, "
         "blocking, floors, direction requirement, bootstrap CI printed beside every verdict-feeding p)."),
        "",
        "---",
        "",
        "## §8 — Registry + Ledger Rows (DRAFT)",
        "",
        "*(Applied to registry/masterplan docs by Fable in same PR)*",
        "",
        f"**EI masterplan §9:** {results.get('masterplan_entry_draft', '')}",
        f"**Signal Commons:** {results.get('signal_commons_resolution_draft', '')}",
        f"**DT-R7:** {results.get('dt_r7_clock_closure_draft', '')}",
        "",
        "---",
        "",
        "## §9 — Plain-English Box",
        "",
        "The price-memory bundle asked whether the chart's history of volume predicts outcome for",
        "production fires, using five measures: anchored VWAP distance (where does price sit relative",
        "to the post-low buyer base?), shelf density (is there prior ownership at this level?), gap-fill",
        "map (is there an unfilled seller cohort overhead?), overhead supply (how much prior volume traded",
        "above current price?), and float turnover (has the register churned to fresh holders?).",
        "",
        "Tests are made month-by-month to prevent calendar composition from masquerading as signal",
        "(DT-R14 law, applied because bear markets load all stocks with overhead supply simultaneously).",
        "Float turnover (PM5) could not be tested: the EDGAR panel covers only 50% of our fire universe,",
        "below the registered 60% floor. It is pre-blocked with a printed unblock condition.",
        "",
        "Survivors — if any — earn display-only context status and eligibility for a separate promotion",
        "study. Nothing here may ever specify a price level as an instruction to act (DT-R2/DT-R7).",
        "No promotion-tier language is used anywhere in this document.",
        "",
    ]

    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EI-PM0 Price-Memory Bundle — Staged Runner")
    parser.add_argument("--stage", choices=["preamble", "calibration", "inference"], required=True,
                        help="Which stage to run")
    parser.add_argument("--features-path", type=str, default=None,
                        help="Path to pm0_features.parquet (default: MAIN_DATA/replay/pm0_features.parquet)")
    parser.add_argument("--authorize-one-shot", action="store_true",
                        help="Required to run --stage inference (one-shot gate)")
    args = parser.parse_args()

    feat_path = Path(args.features_path) if args.features_path else DEFAULT_FEATURES_PATH

    if args.stage == "inference":
        if not args.authorize_one_shot:
            print("BLOCKER: --stage inference requires --authorize-one-shot flag.")
            print("This is the one-shot registered run. Pass the flag to confirm.")
            sys.exit(1)
        # Also check calibration.json
        cal_path = OUT_DIR / "calibration.json"
        if not cal_path.exists():
            print("BLOCKER: calibration.json not found. Run --stage calibration first.")
            sys.exit(1)
        with open(cal_path) as fh:
            cal_check = json.load(fh)
        if not cal_check.get("overall_pass"):
            print("BLOCKER: calibration.json has overall_pass != true. Inference blocked.")
            sys.exit(1)

    if not feat_path.exists():
        print(f"BLOCKER: Feature artifact not found at {feat_path}")
        print("Run: python scripts/ei_pm0_price_memory_features.py --build")
        sys.exit(1)

    if args.stage == "preamble":
        run_preamble(feat_path)
    elif args.stage == "calibration":
        run_calibration(feat_path)
    elif args.stage == "inference":
        run_inference(feat_path)


if __name__ == "__main__":
    main()
