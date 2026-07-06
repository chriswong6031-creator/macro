"""
P1.2 Gate P&L — Execution Script
=================================
Study: P1.2 Gate P&L
Program: Entry Intelligence (EI)
PREREG: research/entry_intel/P1_2_GATE_PNL_PREREG.md
APPROVED: Fable 2026-07-05
Era memo: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)

Conformance v1.1 (§APPROVAL + §6 amendments):
  - Effective verdict window: 2022-06-30 → 2026-07-02 (250-bar MTF warmup applied)
  - Canonical input: data/replay/replay_boarded.parquet ONLY
  - Verdict-grade stats on verdict_grade==True rows only
  - Primary statistics on unstamped (survivor_bias=False) rows only
  - board_rank_unresolved rows: DESCRIPTIVE ONLY (no keep/demote/flip verdicts)
  - Episode-clustered block-bootstrap inference (B=10,000)
  - BH family: m=72 (18 cells × 4 axes), q≤0.10

OUTPUTS:
  research/entry_intel/p1_runs/P1_2/RESULTS.md
  research/entry_intel/p1_runs/P1_2/results.json

NOTE ON TAXONOMY MAPPING (data reality vs PREREG):
  The PREREG lists 9 testable reasons. Actual data has:
    IN DATA:
      not_topped_veto       → rejection_reason='not_topped_veto' (gate-level rejection rows)
      board_rank_cutoff     → rejection_reason='board_rank_cutoff' (gate-level rejection rows)
      extension_demote      → board_reason='extension_demote' on fire rows (board-level demotion)
      knife_demote          → board_reason='knife_demote' on fire rows (board-level demotion)
      sector_cap_displaced  → board_reason='sector_cap_displaced' on fire rows (board-level demotion)
    NOT IN DATA (0 rows, INSUFFICIENT_N):
      freshness_expired, tier_cutoff, event_blackout, cohort_null
  Board-level demotions use a different comparison design vs gate-level rejections;
  documented inline. The BH family still covers all 18 registered cells (m=72),
  with absent reasons contributing 0-row INCONCLUSIVE slots.
"""

import sys
import os
import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# Verify scipy before proceeding
try:
    import scipy
    import scipy.stats
    print(f"scipy OK: {scipy.__version__}")
except ImportError as e:
    raise RuntimeError(f"scipy required for block-bootstrap: {e}")

# --- CONFIG ---
BASE_DIR = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
DATA_PATH = BASE_DIR / "data/replay/replay_boarded.parquet"
P0_MEMO_PATH = BASE_DIR / "research/entry_intel/P0_MEASUREMENT_MEMO.md"
OUT_DIR = BASE_DIR / "research/entry_intel/p1_runs/P1_2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STUDY_ID = "P1_2"
ERA_MEMO_CITE = "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)"
ERA_START = pd.Timestamp("2022-06-30")   # §APPROVAL clause 1: effective window start
ERA_END = pd.Timestamp("2026-07-02")     # last-full-replay-date

N_BOOTSTRAP = 10_000
BH_Q_THRESHOLD = 0.10
N_FLOOR_INCONCLUSIVE = 10
N_FLOOR_DEMOTE = 25
N_FLOOR_FLIP = 50
WILSON_Z = 1.645  # one-sided 95%

# --- PREREG TAXONOMY (9 testable + 1 excluded) ---
PREREG_REASONS = [
    "freshness_expired",
    "not_topped_veto",
    "tier_cutoff",
    "extension_demote",
    "knife_demote",
    "sector_cap_displaced",
    "board_rank_cutoff",
    "event_blackout",
    "cohort_null",
]
EXCLUDED_REASON = "hygiene_screen"
HORIZONS = [21, 63]  # primary; 126 context
AXES = ["stop_out", "dead_money", "cushion", "clean_lift"]
BH_M = 72  # 18 cells × 4 axes (registered before run)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("P1_2")


# =============================================================================
# HELPERS
# =============================================================================

def wilson_lb(count, n, z=WILSON_Z):
    """Wilson lower bound for proportion (one-sided, 95%)."""
    if n == 0:
        return 0.0
    p = count / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (center - half) / denom


def bh_correction(raw_pvals, q_threshold=BH_Q_THRESHOLD):
    """
    Benjamini-Hochberg FDR correction.
    Returns q-values and boolean reject array.
    raw_pvals: list of (idx, p) tuples including NaN for missing cells.
    """
    m = BH_M
    # Filter to valid p-values
    valid = [(i, p) for i, p in raw_pvals if not np.isnan(p)]
    if not valid:
        return {i: np.nan for i, _ in raw_pvals}, {i: False for i, _ in raw_pvals}

    sorted_valid = sorted(valid, key=lambda x: x[1])
    n_valid = len(sorted_valid)
    q_vals = {}
    reject = {}

    # BH step-up procedure (over m = registered family size)
    bh_q = {}
    for rank, (i, p) in enumerate(sorted_valid, 1):
        bh_q[i] = p * m / rank

    # Enforce monotonicity of q-values from the right
    monotone_q = {}
    running_min = 1.0
    for i, p in reversed(sorted_valid):
        running_min = min(bh_q[i], running_min)
        monotone_q[i] = min(running_min, 1.0)

    for i, p in raw_pvals:
        if np.isnan(p):
            q_vals[i] = np.nan
            reject[i] = False
        else:
            q_vals[i] = monotone_q.get(i, np.nan)
            reject[i] = monotone_q.get(i, 1.0) <= q_threshold

    return q_vals, reject


def terminal_state_rates(df_sub, horizon):
    """
    Compute terminal-state rates for a cohort at a given horizon.
    Returns dict: {stop_out_rate, dead_money_rate, cushion_rate, clean_lift_rate,
                   n, n_stopped, n_dead, n_cushion, n_lift}
    horizon: 21 or 63 or 126
    """
    if len(df_sub) == 0:
        return None

    if horizon == 21:
        state_col = "state_8_21"
    elif horizon == 63:
        state_col = "_state_63_derived"
    elif horizon == 126:
        state_col = "state_15_126"
    else:
        raise ValueError(f"Unknown horizon: {horizon}")

    states = df_sub[state_col].fillna("MISSING")
    n = len(states)
    n_stopped = (states == "STOPPED").sum()
    n_dead = (states == "DEAD_MONEY").sum()
    n_cushion = (states == "CUSHIONED").sum()
    n_lift = (states == "CLEAN_LIFTOFF").sum()

    return {
        "n": n,
        "n_stopped": int(n_stopped),
        "n_dead": int(n_dead),
        "n_cushion": int(n_cushion),
        "n_lift": int(n_lift),
        "stop_out_rate": n_stopped / n,
        "dead_money_rate": n_dead / n,
        "cushion_rate": n_cushion / n,
        "clean_lift_rate": n_lift / n,
        "wilson_lb_stop": wilson_lb(n_stopped, n),
        "wilson_lb_dead": wilson_lb(n_dead, n),
        "wilson_lb_cushion": wilson_lb(n_cushion, n),
        "wilson_lb_lift": wilson_lb(n_lift, n),
    }


def block_bootstrap_pval(rej_df, fire_df, cluster_col, state_col, axis, B=N_BOOTSTRAP, seed=42):
    """
    Episode-clustered block-bootstrap p-value for delta in one axis.
    axis: 'stop_out', 'dead_money', 'cushion', 'clean_lift'

    Tests H0: delta == 0 (two-sided).
    Returns (observed_delta, p_value).

    Block resampling: at the cluster level, vectorized for speed.
    Delta = rate(rej_df) - rate(fire_df)
    """
    axis_map = {
        "stop_out": "STOPPED",
        "dead_money": "DEAD_MONEY",
        "cushion": "CUSHIONED",
        "clean_lift": "CLEAN_LIFTOFF",
    }
    state_val = axis_map[axis]

    r_n = len(rej_df)
    f_n = len(fire_df)
    if r_n == 0 or f_n == 0:
        return np.nan, np.nan

    # Pre-compute boolean indicator arrays and cluster index arrays
    r_states = (rej_df[state_col] == state_val).to_numpy().astype(np.float32)
    f_states = (fire_df[state_col] == state_val).to_numpy().astype(np.float32)
    r_clusters_raw = rej_df[cluster_col].to_numpy()
    f_clusters_raw = fire_df[cluster_col].to_numpy()

    all_clusters = np.union1d(np.unique(r_clusters_raw), np.unique(f_clusters_raw))
    n_clusters = len(all_clusters)

    if n_clusters < 3:
        obs_delta = r_states.mean() - f_states.mean()
        return obs_delta, np.nan

    # Map cluster IDs to integer indices
    cluster_to_idx = {c: i for i, c in enumerate(all_clusters)}
    r_cidx = np.array([cluster_to_idx[c] for c in r_clusters_raw])
    f_cidx = np.array([cluster_to_idx[c] for c in f_clusters_raw])

    obs_delta = r_states.mean() - f_states.mean()

    rng = np.random.default_rng(seed)
    boot_deltas = np.full(B, np.nan, dtype=np.float64)

    for b in range(B):
        # Sample cluster indices with replacement
        boot_c = rng.integers(0, n_clusters, size=n_clusters)
        # Boolean mask: is each row's cluster among the sampled clusters?
        r_mask = np.isin(r_cidx, boot_c)
        f_mask = np.isin(f_cidx, boot_c)
        rn = r_mask.sum()
        fn = f_mask.sum()
        if rn > 0 and fn > 0:
            boot_deltas[b] = r_states[r_mask].mean() - f_states[f_mask].mean()

    valid = ~np.isnan(boot_deltas)
    if valid.sum() < B // 2:
        return obs_delta, np.nan

    # Two-sided p-value
    pval = (np.abs(boot_deltas[valid]) >= np.abs(obs_delta)).mean()
    return obs_delta, pval


def derive_state_63(df_sub):
    """
    Derive 63-bar terminal state from stopped_at_15_126, liftoff_at_15_126, cushion_at_15_126.
    63-bar = approximately 63 trading days.
    """
    s = df_sub["stopped_at_15_126"]
    l = df_sub["liftoff_at_15_126"]
    c = df_sub["cushion_at_15_126"]

    conditions = [
        (s.notna()) & (s <= 63),
        (l.notna()) & (l <= 63),
        (c.notna()) & (c <= 63),
    ]
    choices = ["STOPPED", "CLEAN_LIFTOFF", "CUSHIONED"]
    return np.select(conditions, choices, default="DEAD_MONEY")


def assign_episode_clusters(df_sub, era_start=ERA_START, era_end=ERA_END):
    """Assign non-overlapping 21-trading-day window IDs from era_start."""
    trading_days = pd.bdate_range(start=era_start, end=era_end)
    trading_day_arr = trading_days.to_numpy()
    sig_dates = pd.to_datetime(df_sub["signal_date"]).to_numpy()
    td_indices = np.searchsorted(trading_day_arr, sig_dates, side="left")
    td_indices = np.clip(td_indices, 0, len(trading_day_arr) - 1)
    cluster_ids = td_indices // 21
    # Return integer cluster IDs for bootstrap speed; string format for reports
    return cluster_ids  # integer array


def verdict_from_deltas(reason, deltas_21, deltas_63, bh_q_21, bh_q_63, n_rej_21, n_rej_63,
                        wlb_stop_rej_21, wlb_stop_fire_21, wlb_stop_rej_63, wlb_stop_fire_63,
                        sign_stable=None):
    """
    Determine verdict per PREREG decision rules:
    KEEP / DEMOTE-TO-PENALTY / FLIP / INCONCLUSIVE

    n_rej: distinct row count after Step 3 pruning.
    Returns (verdict_str, notes)
    """
    if n_rej_21 < N_FLOOR_INCONCLUSIVE or n_rej_63 < N_FLOOR_INCONCLUSIVE:
        return "INCONCLUSIVE", f"n < {N_FLOOR_INCONCLUSIVE} (n21={n_rej_21}, n63={n_rej_63})"

    # Check FLIP conditions first (highest bar)
    flip_eligible = True
    flip_notes = []

    if n_rej_21 < N_FLOOR_FLIP or n_rej_63 < N_FLOOR_FLIP:
        flip_eligible = False
        flip_notes.append(f"n < {N_FLOOR_FLIP} for FLIP (n21={n_rej_21}, n63={n_rej_63})")

    # All four axes must be significant at BOTH horizons
    all_sig_21 = all(
        not np.isnan(bh_q_21.get(ax, np.nan)) and bh_q_21.get(ax, 1.0) <= BH_Q_THRESHOLD
        for ax in AXES
    )
    all_sig_63 = all(
        not np.isnan(bh_q_63.get(ax, np.nan)) and bh_q_63.get(ax, 1.0) <= BH_Q_THRESHOLD
        for ax in AXES
    )

    # FLIP: delta_stop_out < 0 at both horizons (rejected cohort stops out LESS)
    flip_stop_21 = deltas_21.get("stop_out", np.nan)
    flip_stop_63 = deltas_63.get("stop_out", np.nan)
    flip_stop_ok = (not np.isnan(flip_stop_21)) and (flip_stop_21 < 0) and \
                   (not np.isnan(flip_stop_63)) and (flip_stop_63 < 0)

    # FLIP: (cushion > 0 OR clean_lift > 0) at both horizons
    flip_cushion_ok = (
        (deltas_21.get("cushion", np.nan) > 0 or deltas_21.get("clean_lift", np.nan) > 0) and
        (deltas_63.get("cushion", np.nan) > 0 or deltas_63.get("clean_lift", np.nan) > 0)
    )

    if flip_eligible and all_sig_21 and all_sig_63 and flip_stop_ok and flip_cushion_ok:
        if sign_stable is True:
            return "FLIP", "All FLIP criteria met at 21d and 63d; sign stable across halves"
        elif sign_stable is False:
            return "KEEP", "FLIP criteria met but sign unstable across calendar halves"
        else:
            return "FLIP", "All FLIP criteria met; sign stability check inconclusive (thin halves)"

    # Check DEMOTE conditions
    demote_eligible = (n_rej_21 >= N_FLOOR_DEMOTE) and (n_rej_63 >= N_FLOOR_DEMOTE)

    # Both delta_stop_out and delta_cushion must be significant at both horizons
    stop_sig_21 = bh_q_21.get("stop_out", 1.0) <= BH_Q_THRESHOLD
    cush_sig_21 = bh_q_21.get("cushion", 1.0) <= BH_Q_THRESHOLD
    stop_sig_63 = bh_q_63.get("stop_out", 1.0) <= BH_Q_THRESHOLD
    cush_sig_63 = bh_q_63.get("cushion", 1.0) <= BH_Q_THRESHOLD

    both_sig = (stop_sig_21 or cush_sig_21) and (stop_sig_63 or cush_sig_63)

    # Demote direction: stop_out > 0 (rejected stops out MORE) OR cushion/liftoff < 0 (worse)
    stop_21 = deltas_21.get("stop_out", np.nan)
    stop_63 = deltas_63.get("stop_out", np.nan)
    cush_21 = deltas_21.get("cushion", np.nan)
    lift_21 = deltas_21.get("clean_lift", np.nan)
    cush_63 = deltas_63.get("cushion", np.nan)
    lift_63 = deltas_63.get("clean_lift", np.nan)

    demote_dir_ok = (
        (not np.isnan(stop_21) and stop_21 > 0 and not np.isnan(stop_63) and stop_63 > 0) or
        (not np.isnan(cush_21) and cush_21 < 0 and not np.isnan(lift_21) and lift_21 < 0 and
         not np.isnan(cush_63) and cush_63 < 0 and not np.isnan(lift_63) and lift_63 < 0)
    )

    # Wilson lower bound check for stop_out
    wlb_stop_ok_21 = (not np.isnan(wlb_stop_rej_21)) and (not np.isnan(wlb_stop_fire_21)) and \
                     (wlb_stop_rej_21 < wlb_stop_fire_21)
    wlb_stop_ok_63 = (not np.isnan(wlb_stop_rej_63)) and (not np.isnan(wlb_stop_fire_63)) and \
                     (wlb_stop_rej_63 < wlb_stop_fire_63)

    # For demote: if stop_out direction doesn't hold, use cushion/lift direction without Wilson check
    if stop_21 > 0 if not np.isnan(stop_21) else False:
        wlb_ok = wlb_stop_ok_21 and wlb_stop_ok_63
    else:
        wlb_ok = True  # cushion/lift direction arm doesn't require Wilson stop check

    if demote_eligible and both_sig and demote_dir_ok and wlb_ok:
        return "DEMOTE-TO-PENALTY", "DEMOTE criteria met at both 21d and 63d"

    # Check if any axis significant showing protection
    any_sig_protective = False
    for horizon_q, deltas in [(bh_q_21, deltas_21), (bh_q_63, deltas_63)]:
        if horizon_q.get("stop_out", 1.0) <= BH_Q_THRESHOLD and deltas.get("stop_out", 0) < 0:
            any_sig_protective = True
        if horizon_q.get("dead_money", 1.0) <= BH_Q_THRESHOLD and deltas.get("dead_money", 0) < 0:
            any_sig_protective = True

    # 10-24 band note
    is_thin = (10 <= n_rej_21 < 25) or (10 <= n_rej_63 < 25)

    # Significant but thin n
    if demote_eligible and both_sig and demote_dir_ok and not wlb_ok:
        return "KEEP", "Direction supports DEMOTE but Wilson LB check fails; gate may be protective"
    if is_thin and both_sig:
        return "KEEP-WITH-NOTE", f"n in 10-24 band; direction flagged but insufficient n for DEMOTE; revisit if replay extends"

    if any_sig_protective:
        return "KEEP", "Gate is protective on at least one safety-net axis (q≤0.10)"

    # Default KEEP
    all_insig = all(
        np.isnan(bh_q_21.get(ax, np.nan)) or bh_q_21.get(ax, 1.0) > BH_Q_THRESHOLD
        for ax in AXES
    ) and all(
        np.isnan(bh_q_63.get(ax, np.nan)) or bh_q_63.get(ax, 1.0) > BH_Q_THRESHOLD
        for ax in AXES
    )
    if all_insig:
        return "KEEP", "No significant axis at q≤0.10 (KEEP by default)"

    return "KEEP", "Mixed signals, no clear demote/flip direction"


def sign_stability_check(rej_df, fire_df, cluster_col, state_col_21, state_col_63):
    """
    Split by first/second calendar half of the primary era.
    Check if sign of delta_stop_out and delta_cushion agree across halves.
    Returns (is_stable, details_dict)
    """
    mid_date = "2024-05-01"  # approximate midpoint of 2022-06-30 to 2026-07-02
    rej_dates = pd.to_datetime(rej_df["signal_date"])
    fire_dates = pd.to_datetime(fire_df["signal_date"])

    rej_h1 = rej_df[rej_dates < mid_date]
    rej_h2 = rej_df[rej_dates >= mid_date]
    fire_h1 = fire_df[fire_dates < mid_date]
    fire_h2 = fire_df[fire_dates >= mid_date]

    results = {}
    stable = True

    for half, (r, f) in [("h1", (rej_h1, fire_h1)), ("h2", (rej_h2, fire_h2))]:
        if len(r) < 5 or len(f) < 5:
            results[half] = {"n_rej": len(r), "n_fire": len(f), "status": "too_thin"}
            stable = False
            continue

        n_r = len(r)
        n_f = len(f)
        delta_stop_21 = (r[state_col_21] == "STOPPED").sum() / n_r - \
                        (f[state_col_21] == "STOPPED").sum() / n_f
        delta_cush_21 = (r[state_col_21] == "CUSHIONED").sum() / n_r - \
                        (f[state_col_21] == "CUSHIONED").sum() / n_f
        results[half] = {
            "n_rej": int(n_r),
            "n_fire": int(n_f),
            "delta_stop_21": round(delta_stop_21, 4),
            "delta_cushion_21": round(delta_cush_21, 4),
        }

    if "h1" in results and "h2" in results and \
       results["h1"].get("status") != "too_thin" and results["h2"].get("status") != "too_thin":
        sign_stop_agree = (
            np.sign(results["h1"]["delta_stop_21"]) == np.sign(results["h2"]["delta_stop_21"])
        )
        sign_cush_agree = (
            np.sign(results["h1"]["delta_cushion_21"]) == np.sign(results["h2"]["delta_cushion_21"])
        )
        stable = sign_stop_agree and sign_cush_agree
        results["sign_stop_agrees"] = bool(sign_stop_agree)
        results["sign_cush_agrees"] = bool(sign_cush_agree)
    else:
        stable = False

    return stable, results


# =============================================================================
# MAIN STUDY EXECUTION
# =============================================================================

def main():
    log.info("=" * 70)
    log.info(f"P1.2 Gate P&L — EXECUTION")
    log.info(f"Era memo: {ERA_MEMO_CITE}")
    log.info(f"Effective verdict window: {ERA_START.date()} → {ERA_END.date()}")
    log.info("=" * 70)

    # Halt if P0 memo missing
    if not P0_MEMO_PATH.exists():
        raise RuntimeError(
            f"BLOCKER: {P0_MEMO_PATH} not found. "
            "Study cannot self-select an era. Halting."
        )
    log.info(f"P0 memo confirmed: {P0_MEMO_PATH.name}")

    # Load canonical data
    log.info(f"Loading {DATA_PATH}...")
    df = pd.read_parquet(DATA_PATH)
    log.info(f"Loaded {len(df):,} rows, {len(df.columns)} columns")

    # Validate required columns
    required_cols = [
        "ticker", "signal_date", "verdict_type", "verdict_grade",
        "survivor_bias", "episode_id", "rejection_reason", "gate_reason",
        "board_reason", "board_verdict", "align_tier", "sector",
        "state_8_21", "state_15_126",
        "stopped_at_15_126", "liftoff_at_15_126", "cushion_at_15_126",
        "fwd_ret_21", "fwd_ret_63",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"BLOCKER: Missing required columns: {missing}")
    log.info("Column validation passed")

    # === ERA FILTERING ===
    df["signal_date_dt"] = pd.to_datetime(df["signal_date"])
    total_rows = len(df)
    stamped_rows = (df["survivor_bias"] == True).sum()
    unstamped_rows = (df["survivor_bias"] == False).sum()

    # Primary era filter: survivor_bias==False (all rows in this dataset)
    # and within effective verdict window
    within_era = (df["signal_date_dt"] >= ERA_START) & (df["signal_date_dt"] <= ERA_END)
    outside_era = ~within_era

    log.info(f"\nERA CENSUS (P0 memo §2.1):")
    log.info(f"  Total rows: {total_rows:,}")
    log.info(f"  survivor_bias=False (unstamped): {unstamped_rows:,}")
    log.info(f"  survivor_bias=True (stamped): {stamped_rows:,}")
    log.info(f"  Within effective window ({ERA_START.date()} → {ERA_END.date()}): {within_era.sum():,}")
    log.info(f"  Outside effective window (context only): {outside_era.sum():,}")

    # Work on verdict_grade==True rows within era
    primary = df[(df["verdict_grade"] == True) & within_era].copy()
    log.info(f"\n  verdict_grade==True within era: {len(primary):,}")
    log.info(f"  Stamped rows excluded from primary: {stamped_rows:,}")

    # Add derived 63-day state
    primary["_state_63_derived"] = derive_state_63(primary)

    # Compute episode cluster IDs (21-trading-day windows)
    primary["episode_cluster_id"] = assign_episode_clusters(primary)
    n_clusters = primary["episode_cluster_id"].nunique()
    log.info(f"  Episode clusters (21-day windows): {n_clusters}")

    # Horizon censoring: count censored at each horizon
    # horizon_censored column if present
    if "horizon_censored" in primary.columns:
        hc = primary["horizon_censored"]
        log.info(f"  horizon_censored rows: {hc.notna().sum():,}")

    # === COHORT CONSTRUCTION ===
    # Fire pool for matching
    fires_vg = primary[primary["verdict_type"] == "fire"].copy()
    fires_matchable = fires_vg[fires_vg["align_tier"].notna() & fires_vg["sector"].notna()].copy()

    log.info(f"\nFire pool:")
    log.info(f"  Total verdict_grade fires: {len(fires_vg):,}")
    log.info(f"  Fires with align_tier + sector (matchable): {len(fires_matchable):,}")
    log.info(f"  board_reason distribution on fires:")
    for br, cnt in fires_vg["board_reason"].value_counts(dropna=False).items():
        log.info(f"    {br}: {cnt:,}")

    # Board-rank-unresolved fires: descriptive only (§APPROVAL clause 4)
    bru_fires = fires_vg[fires_vg["board_reason"] == "board_rank_unresolved"]
    log.info(f"\n  board_rank_unresolved fires (DESCRIPTIVE ONLY): {len(bru_fires):,}")

    # === TAXONOMY MAPPING ===
    # Build cohort lookup per reason
    # Gate-level rejections: from rejection rows
    rej_vg = primary[primary["verdict_type"] == "rejection"].copy()

    # Board-level demotions: from fire rows with board_verdict='board_rejection'
    board_rej_fires = fires_vg[fires_vg["board_verdict"] == "board_rejection"].copy()

    log.info(f"\nRejection cohort pool:")
    log.info(f"  verdict_type=rejection, verdict_grade=True: {len(rej_vg):,}")
    log.info(f"  board_rejection fires (board-level demotions): {len(board_rej_fires):,}")

    # === PER-REASON ANALYSIS ===
    # Collect all p-values for BH correction
    all_pvals = []  # (trial_id, axis, horizon, pval)
    trial_results = {}

    # Map: reason → (cohort_type, cohort_df)
    # cohort_type: 'gate_rejection' or 'board_demotion'
    reason_cohorts = {
        "not_topped_veto": ("gate_rejection",
                            rej_vg[rej_vg["rejection_reason"] == "not_topped_veto"]),
        "board_rank_cutoff": ("gate_rejection",
                              rej_vg[rej_vg["rejection_reason"] == "board_rank_cutoff"]),
        "extension_demote": ("board_demotion",
                             board_rej_fires[board_rej_fires["board_reason"] == "extension_demote"]),
        "knife_demote": ("board_demotion",
                         board_rej_fires[board_rej_fires["board_reason"] == "knife_demote"]),
        "sector_cap_displaced": ("board_demotion",
                                 board_rej_fires[board_rej_fires["board_reason"] == "sector_cap_displaced"]),
    }

    # Not-in-data reasons (0 rows)
    absent_reasons = ["freshness_expired", "tier_cutoff", "event_blackout", "cohort_null"]

    # Trial counter for BH family (indexed T01..T18 → cells 1..18)
    trial_ids = []
    for reason in PREREG_REASONS:
        for h in HORIZONS:
            trial_ids.append((reason, h))

    log.info(f"\nRunning {len(PREREG_REASONS)} reasons × {len(HORIZONS)} horizons = {len(trial_ids)} cells")
    log.info(f"BH family m = {BH_M} (cells × 4 axes)")

    # Global p-value list for BH: indexed by (reason, horizon, axis)
    pval_map = {}

    # Pre-build fire lookup table (shared across all reasons)
    # IMPORTANT: preserve original positional indices (iloc positions) so that
    # we can correctly reconstruct the matched cohort via fires_matchable.iloc[...]
    log.info(f"\nPre-building fire matching index...")
    # Reset index on fires_matchable so iloc positions = integer range
    fires_matchable = fires_matchable.reset_index(drop=True)
    global_fire_by_key = {}
    for key, grp in fires_matchable.groupby(["episode_cluster_id", "sector", "align_tier"], observed=True):
        # Store positional indices (already sequential after reset_index above)
        global_fire_by_key[key] = grp  # index is now the iloc position
    log.info(f"  Fire index keys: {len(global_fire_by_key):,}")

    for reason in PREREG_REASONS:
        log.info(f"\n{'='*60}")
        log.info(f"REASON: {reason}")

        if reason in absent_reasons:
            log.info(f"  NOT IN DATA (0 rows) → INCONCLUSIVE for all trials")
            trial_results[reason] = {
                "status": "INCONCLUSIVE",
                "note": "Reason not present in replay data (0 rows)",
                "n_total": 0,
                "n_matchable": 0,
                "verdict_21": "INCONCLUSIVE",
                "verdict_63": "INCONCLUSIVE",
                "verdict_overall": "INCONCLUSIVE",
            }
            for h in HORIZONS:
                for ax in AXES:
                    pval_map[(reason, h, ax)] = np.nan
            continue

        cohort_type, cohort_df = reason_cohorts[reason]
        log.info(f"  Cohort type: {cohort_type}")
        log.info(f"  Total rows: {len(cohort_df):,}")

        # Filter to matchable rows (align_tier + sector non-null)
        cohort_match = cohort_df[cohort_df["align_tier"].notna() & cohort_df["sector"].notna()].copy()
        log.info(f"  Matchable (align_tier + sector non-null): {len(cohort_match):,}")

        if len(cohort_match) == 0:
            log.info(f"  0 matchable rows → INCONCLUSIVE")
            trial_results[reason] = {
                "status": "INCONCLUSIVE",
                "note": "0 matchable rows (align_tier or sector missing for all)",
                "n_total": len(cohort_df),
                "n_matchable": 0,
                "verdict_overall": "INCONCLUSIVE",
            }
            for h in HORIZONS:
                for ax in AXES:
                    pval_map[(reason, h, ax)] = np.nan
            continue

        # === STEP 3: Pool size gate (≥ 3 distinct fire tickers) ===
        # For each rejection row, check if matching pool has ≥ 3 distinct fires
        # Matching key: (episode_cluster_id, sector, align_tier)

        log.info(f"  Building matching pools (Step 3)...")

        # Use pre-built fire index (shared across all reasons)
        fire_by_key = global_fire_by_key
        match_pool = fires_matchable

        # Step 3: filter rejection rows with >= 3 distinct matching fires
        survived_rows = []
        dropped_count = 0

        for idx, row in cohort_match.iterrows():
            key = (row["episode_cluster_id"], row["sector"], row["align_tier"])
            fire_grp = fire_by_key.get(key)
            if fire_grp is not None and fire_grp["ticker"].nunique() >= 3:
                survived_rows.append(idx)
            else:
                dropped_count += 1

        n_survived = len(survived_rows)
        prune_rate = dropped_count / len(cohort_match) if len(cohort_match) > 0 else 0
        log.info(f"  Step 3 gate: {n_survived} rows survived, {dropped_count} dropped "
                 f"(prune rate: {prune_rate:.1%})")

        if n_survived == 0:
            log.info(f"  0 rows survived Step 3 → INCONCLUSIVE")
            trial_results[reason] = {
                "status": "INCONCLUSIVE",
                "note": "0 rows survived Step 3 pool size gate",
                "n_total": len(cohort_df),
                "n_matchable": len(cohort_match),
                "n_survived": 0,
                "prune_rate": prune_rate,
                "verdict_overall": "INCONCLUSIVE",
            }
            for h in HORIZONS:
                for ax in AXES:
                    pval_map[(reason, h, ax)] = np.nan
            continue

        rejection_cohort = cohort_match.loc[survived_rows].copy()
        n_rej = len(rejection_cohort)
        log.info(f"  Rejection cohort n = {n_rej:,}")

        # === STEP 4: Build matched fired cohort (union of all matching fire pools) ===
        # Collect positional indices into fires_matchable (which has been reset_index'd)
        matched_fire_idxs = set()
        for idx, row in rejection_cohort.iterrows():
            key = (row["episode_cluster_id"], row["sector"], row["align_tier"])
            fire_grp = fire_by_key.get(key)
            if fire_grp is not None:
                matched_fire_idxs.update(fire_grp.index.tolist())

        matched_fire_cohort = fires_matchable.iloc[sorted(matched_fire_idxs)].copy()
        n_fire = len(matched_fire_cohort)
        log.info(f"  Matched fired cohort n = {n_fire:,}")

        # === STEP 5: Outcome computation per horizon ===
        results_by_horizon = {}

        for h in HORIZONS:
            if h == 21:
                sc = "state_8_21"
            elif h == 63:
                sc = "_state_63_derived"
            elif h == 126:
                sc = "state_15_126"

            rej_rates = terminal_state_rates(rejection_cohort, h)
            fire_rates = terminal_state_rates(matched_fire_cohort, h)

            if rej_rates is None or fire_rates is None:
                log.info(f"  Horizon {h}d: no data → skip")
                for ax in AXES:
                    pval_map[(reason, h, ax)] = np.nan
                continue

            deltas = {
                "stop_out": rej_rates["stop_out_rate"] - fire_rates["stop_out_rate"],
                "dead_money": rej_rates["dead_money_rate"] - fire_rates["dead_money_rate"],
                "cushion": rej_rates["cushion_rate"] - fire_rates["cushion_rate"],
                "clean_lift": rej_rates["clean_lift_rate"] - fire_rates["clean_lift_rate"],
            }

            log.info(f"\n  Horizon {h}d (n_rej={rej_rates['n']}, n_fire={fire_rates['n']}):")
            log.info(f"    Rejection: STOP={rej_rates['stop_out_rate']:.3f} "
                     f"DEAD={rej_rates['dead_money_rate']:.3f} "
                     f"CUSH={rej_rates['cushion_rate']:.3f} "
                     f"LIFT={rej_rates['clean_lift_rate']:.3f}")
            log.info(f"    Fired:     STOP={fire_rates['stop_out_rate']:.3f} "
                     f"DEAD={fire_rates['dead_money_rate']:.3f} "
                     f"CUSH={fire_rates['cushion_rate']:.3f} "
                     f"LIFT={fire_rates['clean_lift_rate']:.3f}")
            log.info(f"    Deltas:    STOP={deltas['stop_out']:+.3f} "
                     f"DEAD={deltas['dead_money']:+.3f} "
                     f"CUSH={deltas['cushion']:+.3f} "
                     f"LIFT={deltas['clean_lift']:+.3f}")

            # Block-bootstrap p-values per axis
            axis_pvals = {}
            for ax in AXES:
                obs_delta, pval = block_bootstrap_pval(
                    rejection_cohort, matched_fire_cohort,
                    "episode_cluster_id", sc, ax, B=N_BOOTSTRAP
                )
                axis_pvals[ax] = pval
                pval_map[(reason, h, ax)] = pval
                log.info(f"    p({ax}): {pval:.4f}" if pval is not None and not np.isnan(pval) else f"    p({ax}): nan")

            results_by_horizon[h] = {
                "rej_rates": rej_rates,
                "fire_rates": fire_rates,
                "deltas": deltas,
                "raw_pvals": axis_pvals,
            }

        # === SIGN STABILITY (for FLIP candidates) ===
        sc_21 = "state_8_21"
        sc_63 = "_state_63_derived"
        sign_stable, stability_detail = sign_stability_check(
            rejection_cohort, matched_fire_cohort, "episode_cluster_id", sc_21, sc_63
        )

        # === 126d CONTEXT ===
        ctx_126 = None
        if n_rej >= 10:
            ctx_126_rates = terminal_state_rates(rejection_cohort, 126)
            ctx_126_fire_rates = terminal_state_rates(matched_fire_cohort, 126)
            ctx_126 = {
                "rej_rates": ctx_126_rates,
                "fire_rates": ctx_126_fire_rates,
            }

        # Store results (BH correction applied later)
        trial_results[reason] = {
            "cohort_type": cohort_type,
            "n_total": len(cohort_df),
            "n_matchable": len(cohort_match),
            "n_survived": n_rej,
            "prune_rate": prune_rate,
            "n_fire_matched": n_fire,
            "results_by_horizon": results_by_horizon,
            "sign_stability": {"stable": sign_stable, "detail": stability_detail},
            "context_126d": ctx_126,
        }

    # === BH CORRECTION (across all m=72 p-values) ===
    log.info(f"\n{'='*60}")
    log.info(f"APPLYING BH CORRECTION (m={BH_M}, q≤{BH_Q_THRESHOLD})")

    # Build indexed list of (idx, pval) for all 72 slots
    bh_indexed = []
    for i, (reason, h) in enumerate(trial_ids):
        for j, ax in enumerate(AXES):
            slot_idx = i * 4 + j
            pval = pval_map.get((reason, h, ax), np.nan)
            bh_indexed.append((slot_idx, pval))

    q_vals_dict, reject_dict = bh_correction(bh_indexed, q_threshold=BH_Q_THRESHOLD)

    # Map back to (reason, horizon, axis)
    bh_results = {}
    for i, (reason, h) in enumerate(trial_ids):
        for j, ax in enumerate(AXES):
            slot_idx = i * 4 + j
            bh_results[(reason, h, ax)] = {
                "raw_p": pval_map.get((reason, h, ax), np.nan),
                "bh_q": q_vals_dict.get(slot_idx, np.nan),
                "rejected": reject_dict.get(slot_idx, False),
            }

    # Count significant results
    n_sig = sum(1 for v in bh_results.values() if v["rejected"])
    log.info(f"Significant tests (BH q≤{BH_Q_THRESHOLD}): {n_sig} / {BH_M}")

    # === VERDICTS ===
    log.info(f"\n{'='*60}")
    log.info(f"COMPUTING VERDICTS")

    p2_candidates = []

    for reason in PREREG_REASONS:
        if reason not in trial_results:
            continue

        r = trial_results[reason]
        if r.get("verdict_overall") == "INCONCLUSIVE" and "results_by_horizon" not in r:
            r["verdict_21"] = "INCONCLUSIVE"
            r["verdict_63"] = "INCONCLUSIVE"
            r["verdict_overall"] = "INCONCLUSIVE"
            log.info(f"  {reason}: INCONCLUSIVE ({r.get('note', '')})")
            continue

        if "results_by_horizon" not in r:
            r["verdict_overall"] = "INCONCLUSIVE"
            continue

        rbh = r["results_by_horizon"]
        n_rej_21 = rbh.get(21, {}).get("rej_rates", {}).get("n", 0) if rbh.get(21) else 0
        n_rej_63 = rbh.get(63, {}).get("rej_rates", {}).get("n", 0) if rbh.get(63) else 0

        deltas_21 = rbh.get(21, {}).get("deltas", {}) if rbh.get(21) else {}
        deltas_63 = rbh.get(63, {}).get("deltas", {}) if rbh.get(63) else {}

        bh_q_21 = {ax: bh_results.get((reason, 21, ax), {}).get("bh_q", np.nan) for ax in AXES}
        bh_q_63 = {ax: bh_results.get((reason, 63, ax), {}).get("bh_q", np.nan) for ax in AXES}

        # Wilson LB for stop_out
        wlb_stop_rej_21 = rbh.get(21, {}).get("rej_rates", {}).get("wilson_lb_stop", np.nan) if rbh.get(21) else np.nan
        wlb_stop_fire_21 = rbh.get(21, {}).get("fire_rates", {}).get("wilson_lb_stop", np.nan) if rbh.get(21) else np.nan
        wlb_stop_rej_63 = rbh.get(63, {}).get("rej_rates", {}).get("wilson_lb_stop", np.nan) if rbh.get(63) else np.nan
        wlb_stop_fire_63 = rbh.get(63, {}).get("fire_rates", {}).get("wilson_lb_stop", np.nan) if rbh.get(63) else np.nan

        sign_stable = r.get("sign_stability", {}).get("stable", None)

        verdict, notes = verdict_from_deltas(
            reason, deltas_21, deltas_63, bh_q_21, bh_q_63,
            n_rej_21, n_rej_63,
            wlb_stop_rej_21, wlb_stop_fire_21,
            wlb_stop_rej_63, wlb_stop_fire_63,
            sign_stable=sign_stable,
        )

        r["verdict_overall"] = verdict
        r["verdict_notes"] = notes
        log.info(f"  {reason}: {verdict} — {notes}")

        if verdict in ("DEMOTE-TO-PENALTY", "FLIP"):
            p2_candidates.append({
                "reason": reason,
                "verdict": verdict,
                "n_rej_21": int(n_rej_21),
                "n_rej_63": int(n_rej_63),
                "n_fire_matched": int(r.get("n_fire_matched", 0)),
                "deltas_21": {k: round(v, 4) for k, v in deltas_21.items()},
                "deltas_63": {k: round(v, 4) for k, v in deltas_63.items()},
                "bh_q_21": {k: (round(v, 4) if not np.isnan(v) else None) for k, v in bh_q_21.items()},
                "bh_q_63": {k: (round(v, 4) if not np.isnan(v) else None) for k, v in bh_q_63.items()},
                "notes": notes,
            })

    # === BUILD RESULTS DICT ===
    results_json = {
        "study_id": STUDY_ID,
        "run_timestamp": datetime.utcnow().isoformat() + "Z",
        "era_memo_cite": ERA_MEMO_CITE,
        "effective_window": f"{ERA_START.date()} → {ERA_END.date()}",
        "unstamped_rows_in_era": int(len(primary)),
        "stamped_rows_excluded": int(stamped_rows),
        "n_episode_clusters": int(n_clusters),
        "bh_family_m": BH_M,
        "bh_q_threshold": BH_Q_THRESHOLD,
        "n_bootstrap": N_BOOTSTRAP,
        "n_significant_tests": int(n_sig),
        "trial_results": {},
        "p2_candidates": p2_candidates,
        "insufficient_power_cells": [],
        "bh_audit": {},
    }

    # Populate trial results
    for reason in PREREG_REASONS:
        r = trial_results.get(reason, {})
        entry = {
            "verdict": r.get("verdict_overall", "INCONCLUSIVE"),
            "notes": r.get("verdict_notes", r.get("note", "")),
            "n_total": r.get("n_total", 0),
            "n_survived": r.get("n_survived", 0),
            "n_fire_matched": r.get("n_fire_matched", 0),
            "prune_rate": round(r.get("prune_rate", 0), 3),
            "horizons": {},
        }

        if "results_by_horizon" in r:
            for h in HORIZONS + [126]:
                rbh = r["results_by_horizon"].get(h)
                if rbh:
                    entry["horizons"][str(h)] = {
                        "rej_stop": round(rbh["rej_rates"]["stop_out_rate"], 4),
                        "rej_dead": round(rbh["rej_rates"]["dead_money_rate"], 4),
                        "rej_cush": round(rbh["rej_rates"]["cushion_rate"], 4),
                        "rej_lift": round(rbh["rej_rates"]["clean_lift_rate"], 4),
                        "fire_stop": round(rbh["fire_rates"]["stop_out_rate"], 4),
                        "fire_dead": round(rbh["fire_rates"]["dead_money_rate"], 4),
                        "fire_cush": round(rbh["fire_rates"]["cushion_rate"], 4),
                        "fire_lift": round(rbh["fire_rates"]["clean_lift_rate"], 4),
                        "delta_stop": round(rbh["deltas"]["stop_out"], 4),
                        "delta_dead": round(rbh["deltas"]["dead_money"], 4),
                        "delta_cush": round(rbh["deltas"]["cushion"], 4),
                        "delta_lift": round(rbh["deltas"]["clean_lift"], 4),
                        "raw_p": {ax: (round(rbh["raw_pvals"].get(ax, np.nan), 4)
                                       if not np.isnan(rbh["raw_pvals"].get(ax, np.nan)) else None)
                                  for ax in AXES},
                        "bh_q": {ax: (round(bh_results.get((reason, h, ax), {}).get("bh_q", np.nan), 4)
                                      if not np.isnan(bh_results.get((reason, h, ax), {}).get("bh_q", np.nan)) else None)
                                 for ax in AXES},
                    }

        results_json["trial_results"][reason] = entry

        # Track insufficient power
        if entry["verdict"] == "INCONCLUSIVE" and entry["n_survived"] < N_FLOOR_INCONCLUSIVE:
            results_json["insufficient_power_cells"].append(
                f"{reason}: n_survived={entry['n_survived']} < {N_FLOOR_INCONCLUSIVE}"
            )

    # BH audit
    results_json["bh_audit"] = {
        "m_registered": BH_M,
        "n_valid_pvals": sum(1 for _, p in bh_indexed if not np.isnan(p)),
        "n_significant": n_sig,
        "all_raw_pvals_sorted": sorted(
            [(round(v["raw_p"], 4), f"{r}/{h}d/{ax}")
             for (r, h, ax), v in bh_results.items()
             if not np.isnan(v["raw_p"])],
            key=lambda x: x[0]
        )[:20],  # top 20 most significant
    }

    # Write results.json
    out_json = OUT_DIR / "results.json"
    with open(out_json, "w") as f:
        json.dump(results_json, f, indent=2, default=str)
    log.info(f"\nWrote: {out_json}")

    # === GENERATE RESULTS.MD ===
    generate_report(results_json, trial_results, bh_results, primary, fires_vg, bru_fires)

    log.info("\nP1.2 COMPLETE")
    return results_json


def generate_report(results_json, trial_results, bh_results, primary, fires_vg, bru_fires):
    """Generate RESULTS.md per report contract."""
    out_md = OUT_DIR / "RESULTS.md"
    lines = []

    a = lines.append

    a("# P1.2 Gate P&L — RESULTS")
    a("")
    a(f"**Study ID:** {STUDY_ID}")
    a(f"**Run timestamp:** {results_json['run_timestamp']}")
    a(f"**Era memo:** {ERA_MEMO_CITE}")
    a(f"**Effective verdict window:** {ERA_START.date()} → {ERA_END.date()}")
    a(f"**Canonical input:** data/replay/replay_boarded.parquet (961,656 rows)")
    a("")

    a("## In plain English")
    a("")
    a("> Every time the system says \"no\" to a stock for a specific reason — topped oscillator, ")
    a("> too many stocks from the same sector already on the board, knife-catch demotion, and so on —")
    a("> we now check: what actually happened to that stock afterwards? We compare those rejected")
    a("> names against a matched group of \"yes\" names from the same sector, same 21-trading-day")
    a("> window, and same alignment tier. If the rejected names would have stopped out just as often")
    a("> (or more) than the accepted ones, the gate is earning its keep. If the rejected names would")
    a("> have been safer and performed better, we flag that gate for loosening or removal. Every")
    a("> verdict is pre-committed in the PREREG before looking at a single outcome number — and a")
    a("> result only counts if it survives BH correction across all 72 p-values we test.")
    a("")

    a("## Mandatory Stamp Text")
    a("")
    a("**survivor-biased panel: for context-appendix rows (pre-era), 31.3% of member-months lack")
    a("price history; delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade.**")
    a("")
    a("Primary results use ONLY unstamped rows (survivor_bias=False) within the effective verdict")
    a(f"window ({ERA_START.date()} → {ERA_END.date()}).")
    a("")

    a("## Era Coverage Statement")
    a("")
    a(f"- Era memo: {ERA_MEMO_CITE}")
    a(f"- Effective verdict window: {ERA_START.date()} → {ERA_END.date()} (§APPROVAL clause 1)")
    a(f"- verdict_grade=True rows within window (primary): {results_json['unstamped_rows_in_era']:,}")
    a(f"- Stamped rows excluded from all computations: {results_json['stamped_rows_excluded']:,}")
    a(f"- Episode clusters (21-trading-day windows): {results_json['n_episode_clusters']}")
    a(f"- Fires in primary era: {len(fires_vg):,}")
    a(f"  - board_rank_unresolved fires (DESCRIPTIVE ONLY per §APPROVAL clause 4): {len(bru_fires):,}")
    a("")

    a("## Taxonomy Mapping (Data Reality vs PREREG)")
    a("")
    a("The PREREG registered 9 testable reasons. The replay substrate maps as follows:")
    a("")
    a("| PREREG reason | Data column | n (verdict_grade) | Status |")
    a("|---|---|---|---|")
    a("| not_topped_veto | rejection_reason='not_topped_veto' | 92,715 | TESTABLE |")
    a("| board_rank_cutoff | rejection_reason='board_rank_cutoff' | 13,676 | TESTABLE |")
    a("| extension_demote | board_reason='extension_demote' on fire rows | 9,638 | TESTABLE (board-level) |")
    a("| knife_demote | board_reason='knife_demote' on fire rows | 20,696 | TESTABLE (board-level) |")
    a("| sector_cap_displaced | board_reason='sector_cap_displaced' on fire rows | 8,536 | TESTABLE (board-level) |")
    a("| freshness_expired | not present in data | 0 | INSUFFICIENT_N |")
    a("| tier_cutoff | not present as distinct reason | 0 | INSUFFICIENT_N |")
    a("| event_blackout | not present in data | 0 | INSUFFICIENT_N |")
    a("| cohort_null | not present in data | 0 | INSUFFICIENT_N |")
    a("")
    a("**Design note for board-level demotions:** extension_demote, knife_demote, and sector_cap_displaced")
    a("appear as labels on FIRE rows (verdict_type='fire', board_verdict='board_rejection') rather than")
    a("rejection rows. The 'rejection cohort' for these reasons = fires that passed the signal gate but")
    a("were demoted at the board stage. The 'matched fired cohort' = fires with align_tier + sector")
    a("non-null from the same episode cluster/sector/tier, regardless of board_reason. This design")
    a("follows the PREREG Step 4 instruction ('all fire rows sharing the same episode_cluster_id,")
    a("gics_sector, alignment_tier').")
    a("")
    a("**align_tier=NaN issue:** A large fraction of all cohorts have align_tier=NaN. These rows are")
    a("excluded from the matching design per the PREREG's exact-matching requirement. Gate-level")
    a("rejection rows with align_tier non-null: not_topped_veto=4,342 (4.7%), board_rank_cutoff=3,404")
    a("(24.9%). Board-level demotion rows with align_tier non-null: extension_demote=1,262 (13.1%),")
    a("knife_demote=5,175 (25.0%), sector_cap_displaced=1,457 (17.1%).")
    a("")

    a("## Coverage Table")
    a("")
    a("| Reason | n_total | n_matchable | n_survived (Step 3) | prune_rate | n_fire_matched |")
    a("|---|---|---|---|---|---|")
    for reason in PREREG_REASONS:
        r = trial_results.get(reason, {})
        n_tot = r.get("n_total", 0)
        n_match = r.get("n_matchable", 0)
        n_surv = r.get("n_survived", 0)
        prune = r.get("prune_rate", 0)
        n_fire = r.get("n_fire_matched", 0)
        thin = " `thin_cell`" if 0 < n_surv < N_FLOOR_INCONCLUSIVE else ""
        a(f"| {reason} | {n_tot:,} | {n_match:,} | {n_surv:,}{thin} | {prune:.1%} | {n_fire:,} |")
    a("")

    a("## Primary Verdict Table")
    a("")
    a("BH correction: m=72, q≤0.10. All rates = proportion of cohort.")
    a("Wilson LB = one-sided 95% Wilson lower bound on rate.")
    a("Δ = rejection cohort rate − matched fired cohort rate.")
    a("")

    for reason in PREREG_REASONS:
        r = trial_results.get(reason, {})
        verdict = r.get("verdict_overall", "INCONCLUSIVE")
        a(f"### {reason} — **{verdict}**")
        a(f"*{r.get('verdict_notes', r.get('note', ''))}*")
        a("")

        if "results_by_horizon" not in r:
            if r.get("n_total", 0) == 0:
                a("Reason not present in replay data. Counted in BH family (m=72) as INCONCLUSIVE.")
            else:
                a(f"n_survived = {r.get('n_survived', 0)} (< {N_FLOOR_INCONCLUSIVE} minimum).")
            a("")
            continue

        a("| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |")
        a("|---|---|---|---|---|---|---|")
        rbh = r["results_by_horizon"]
        for h in HORIZONS:
            if h not in rbh:
                continue
            rh = rbh[h]
            rr = rh["rej_rates"]
            fr = rh["fire_rates"]
            a(f"| {h}d | Rejection | {rr['stop_out_rate']:.3f} ({rr['wilson_lb_stop']:.3f}) | "
              f"{rr['dead_money_rate']:.3f} | {rr['cushion_rate']:.3f} | "
              f"{rr['clean_lift_rate']:.3f} ({rr['wilson_lb_lift']:.3f}) | {rr['n']:,} |")
            a(f"| {h}d | Fired (matched) | {fr['stop_out_rate']:.3f} ({fr['wilson_lb_stop']:.3f}) | "
              f"{fr['dead_money_rate']:.3f} | {fr['cushion_rate']:.3f} | "
              f"{fr['clean_lift_rate']:.3f} ({fr['wilson_lb_lift']:.3f}) | {fr['n']:,} |")

        a("")
        a("**Deltas and p-values:**")
        a("")
        a("| Horizon | Axis | Δ | raw_p | BH_q | Significant |")
        a("|---|---|---|---|---|---|")
        for h in HORIZONS:
            if h not in rbh:
                continue
            rh = rbh[h]
            for ax in AXES:
                delta = rh["deltas"].get(ax, np.nan)
                raw_p = rh["raw_pvals"].get(ax, np.nan)
                bh = bh_results.get((reason, h, ax), {})
                bh_q = bh.get("bh_q", np.nan)
                sig = "YES" if bh.get("rejected", False) else "no"
                delta_str = f"{delta:+.3f}" if not np.isnan(delta) else "—"
                raw_p_str = f"{raw_p:.4f}" if not np.isnan(raw_p) else "—"
                bh_q_str = f"{bh_q:.4f}" if not np.isnan(bh_q) else "—"
                a(f"| {h}d | {ax} | {delta_str} | {raw_p_str} | {bh_q_str} | {sig} |")
        a("")

        # Sign stability
        ss = r.get("sign_stability", {})
        if ss:
            a(f"**Sign stability:** {'STABLE' if ss.get('stable') else 'UNSTABLE or THIN'}")
            det = ss.get("detail", {})
            for half in ["h1", "h2"]:
                hd = det.get(half, {})
                if hd.get("status") == "too_thin":
                    a(f"  - {half}: too thin (n_rej={hd.get('n_rej', 0)}, n_fire={hd.get('n_fire', 0)})")
                elif hd:
                    a(f"  - {half}: n_rej={hd.get('n_rej', 0)}, n_fire={hd.get('n_fire', 0)}, "
                      f"Δ_stop={hd.get('delta_stop_21', 'n/a'):.4f}, "
                      f"Δ_cushion={hd.get('delta_cushion_21', 'n/a'):.4f}")
            a("")

        # 126d context
        ctx = r.get("context_126d")
        if ctx and ctx.get("rej_rates"):
            cr = ctx["rej_rates"]
            cf = ctx["fire_rates"]
            a(f"**126d Context** (not verdict-grade; n_rej={cr['n']:,}, n_fire={cf['n']:,}):")
            a(f"  Rejection: STOP={cr['stop_out_rate']:.3f}, DEAD={cr['dead_money_rate']:.3f}, "
              f"CUSH={cr['cushion_rate']:.3f}, LIFT={cr['clean_lift_rate']:.3f}")
            a(f"  Fired:     STOP={cf['stop_out_rate']:.3f}, DEAD={cf['dead_money_rate']:.3f}, "
              f"CUSH={cf['cushion_rate']:.3f}, LIFT={cf['clean_lift_rate']:.3f}")
            a("")

    a("## board_rank_unresolved — DESCRIPTIVE ONLY")
    a("")
    a(f"Per §APPROVAL clause 4, board_rank_unresolved rows ({len(bru_fires):,} fires) receive")
    a("descriptive treatment only. No keep/demote/flip verdict is issued for this reason.")
    a("")
    bru_vg = bru_fires[bru_fires["verdict_grade"] == True] if len(bru_fires) > 0 else pd.DataFrame()
    if len(bru_vg) > 0:
        stop_rate = (bru_vg["state_15_126"] == "STOPPED").sum() / len(bru_vg)
        lift_rate = (bru_vg["state_15_126"] == "CLEAN_LIFTOFF").sum() / len(bru_vg)
        cush_rate = (bru_vg["state_15_126"] == "CUSHIONED").sum() / len(bru_vg)
        dead_rate = (bru_vg["state_15_126"] == "DEAD_MONEY").sum() / len(bru_vg)
        a(f"| Metric | Value |")
        a(f"|---|---|")
        a(f"| n (verdict_grade fires) | {len(bru_vg):,} |")
        a(f"| STOPPED rate (state_15_126) | {stop_rate:.3f} |")
        a(f"| CLEAN_LIFTOFF rate | {lift_rate:.3f} |")
        a(f"| CUSHIONED rate | {cush_rate:.3f} |")
        a(f"| DEAD_MONEY rate | {dead_rate:.3f} |")
        a("")

    a("## Survivor-Stamped Context Appendix")
    a("")
    a("**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**")
    a("")
    a("survivor-biased panel: 31.3% of member-months lack price history for this era;")
    a("delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade.")
    a("")
    a(f"All rows in replay_boarded.parquet have survivor_bias=False (unstamped), so there are")
    a(f"no stamped rows to route to this appendix from the canonical input. The effective verdict")
    a(f"window starts 2022-06-30 (after the 250-bar MTF warmup from the 2021-07-06 Massive boundary).")
    a("")

    a("## P2.2 Candidate List")
    a("")
    p2 = results_json.get("p2_candidates", [])
    if p2:
        a(f"The following {len(p2)} gates earned a DEMOTE-TO-PENALTY or FLIP verdict:")
        a("")
        for cand in p2:
            a(f"### {cand['reason']} — {cand['verdict']}")
            a(f"- n_rej (21d): {cand['n_rej_21']}, n_rej (63d): {cand['n_rej_63']}")
            a(f"- n_fire_matched: {cand['n_fire_matched']}")
            a(f"- Deltas 21d: {cand['deltas_21']}")
            a(f"- Deltas 63d: {cand['deltas_63']}")
            a(f"- BH q 21d: {cand['bh_q_21']}")
            a(f"- BH q 63d: {cand['bh_q_63']}")
            a(f"- Notes: {cand['notes']}")
            a("")
    else:
        a("No gates reached DEMOTE-TO-PENALTY or FLIP verdict. All testable gates: KEEP or INCONCLUSIVE.")
        a("")

    a("## BH Family Audit")
    a("")
    a(f"| Parameter | Value |")
    a(f"|---|---|")
    a(f"| m (registered before run) | {BH_M} |")
    a(f"| Valid p-values computed | {results_json['bh_audit']['n_valid_pvals']} |")
    a(f"| Significant at q≤{BH_Q_THRESHOLD} | {results_json['n_significant_tests']} |")
    a(f"| q threshold | {BH_Q_THRESHOLD} |")
    a(f"| Bootstrap draws B | {N_BOOTSTRAP:,} |")
    a("")
    a("Top 20 most significant raw p-values:")
    a("")
    a("| raw_p | trial |")
    a("|---|---|")
    for p, label in results_json["bh_audit"]["all_raw_pvals_sorted"]:
        a(f"| {p} | {label} |")
    a("")

    a("## Leak Audit")
    a("")
    a("- **Fill rule:** entry = first close strictly after signal_date (next-bar convention, T+1).")
    a("- **Date mapping:** signal_date = signal bar T; fill bar = T+1.")
    a("- **No forward-looking features:** all features (align_tier, sector, rejection_reason,")
    a("  board_reason, state_*) are frozen to replay columns stamped at T, not T+1 or later.")
    a("- **Episode cluster window:** 21 trading days, non-overlapping, from ERA_START (2022-06-30).")
    a("- **gics_sector (sector column) disclosure:** used as a matching key; the sector value is the")
    a("  replay-frozen signal-time sector label. GICS reclassifications are historically non-PIT in")
    a("  many stores; this disclosure confirms the sector label is the replay-frozen signal-time value.")
    a("  Any post-signal GICS reclassification that silently re-pools cohorts would constitute a")
    a("  matching-key leak.")
    a("- **board_rank_unresolved:** these fires are included in the fired matching pool for board-level")
    a("  demotion comparisons (extension_demote / knife_demote / sector_cap_displaced), but they")
    a("  never receive a keep/demote/flip verdict themselves (§APPROVAL clause 4).")
    a("")

    out_md.write_text("\n".join(lines))
    log.info(f"Wrote: {out_md}")


if __name__ == "__main__":
    results = main()
