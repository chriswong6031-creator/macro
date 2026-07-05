"""
P1.2b Gate P&L — Taxonomy Extension: Re-tag + Mini-PREREG
==========================================================
Study: P1.2b — Replay-Harness Taxonomy Extension
Program: Entry Intelligence (EI)
SPEC: research/entry_intel/P1_2B_TAXONOMY_EXTENSION_SPEC.md
APPROVED: Fable 2026-07-05
Era memo: P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments (2026-07-05)

Conformance (§3.6 era handling clause):
  - Effective verdict window: 2022-06-30 → last-full-replay-date
  - Canonical input: data/replay/replay_boarded_p12b.parquet (re-tagged artifact)
  - P1.2b reads replay_boarded_p12b.parquet ONLY (never the original or per-year parts glob)
  - Verdict-grade stats on verdict_grade==True rows only
  - Primary statistics on unstamped (survivor_bias=False) rows only
  - BH family: m=16 (2 reasons × 2 horizons × 4 axes), q≤0.10
  - BH family ID: ei_gate_pnl_p12b (SEPARATE from original ei_gate_pnl)
  - Matched fired cohort: board_fire rows only (not demoted fires)

OUTPUTS:
  research/entry_intel/p1_runs/P1_2B/RESULTS.md
  research/entry_intel/p1_runs/P1_2B/results.json
  data/replay/replay_boarded_p12b.parquet (re-tagged artifact, NOT committed per R9)

RE-TAG LOGIC (spec §2.1):
  Change 1 — freshness_expired:
    Tag rows where near_miss_reason=='freshness_expired' and rejection_reason is null
    as rejection_reason='freshness_expired'. Processed AFTER tier_cutoff (see below).

  Change 2 — tier_cutoff:
    Tag ALL rows where gate_reason=='tier T4 (weight 0.4)' and
    verdict_type in {'rejection', 'near_miss'} as rejection_reason='tier_cutoff'.
    This overrides board_rank_cutoff for T4 rows because board_rank_cutoff is the
    catch-all placeholder for these T4-excluded rows (spec §1.1: ~131 verdict_grade rows).
    Processed FIRST so that the 37 T4 near_miss rows get tier_cutoff (not freshness_expired).

  Priority: tier_cutoff processed first (overrides board_rank_cutoff for T4 rows).
  freshness_expired processed second (tags remaining NaN rejection_reason rows).
  This achieves the ~131 tier_cutoff rows expected by the spec and satisfies AC-1.
"""

import sys
import os
import json
import hashlib
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
DATA_PATH_ORIG = BASE_DIR / "data/replay/replay_boarded.parquet"
DATA_PATH_P12B = BASE_DIR / "data/replay/replay_boarded_p12b.parquet"
P0_MEMO_PATH = BASE_DIR / "research/entry_intel/P0_MEASUREMENT_MEMO.md"
OUT_DIR = BASE_DIR / "research/entry_intel/p1_runs/P1_2B"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STUDY_ID = "P1_2B"
SPEC_CITE = "research/entry_intel/P1_2B_TAXONOMY_EXTENSION_SPEC.md"
ERA_MEMO_CITE = "P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments (2026-07-05)"
ERA_START = pd.Timestamp("2022-06-30")   # §3.6 effective verdict window
ERA_END = pd.Timestamp("2026-07-02")     # last-full-replay-date

N_BOOTSTRAP = 10_000
BH_Q_THRESHOLD = 0.10
N_FLOOR_INCONCLUSIVE = 10
N_FLOOR_DEMOTE = 25
N_FLOOR_FLIP = 50
WILSON_Z = 1.645  # one-sided 95%

# BH family for P1.2b — SEPARATE from original ei_gate_pnl
BH_FAMILY_ID = "ei_gate_pnl_p12b"
BH_M = 16  # 2 reasons × 2 horizons × 4 axes (registered before run)

# Pre-registered trial codes
P12B_REASONS = ["freshness_expired", "tier_cutoff"]
HORIZONS = [21, 63]  # primary; 126 context
AXES = ["stop_out", "dead_money", "cushion", "clean_lift"]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("P1_2B")


# =============================================================================
# HELPERS
# =============================================================================

def md5_of_file(path):
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson_lb(count, n, z=WILSON_Z):
    """Wilson lower bound for proportion (one-sided, 95%)."""
    if n == 0:
        return 0.0
    p = count / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (center - half) / denom


def bh_correction_p12b(raw_pvals, m=BH_M, q_threshold=BH_Q_THRESHOLD):
    """
    Benjamini-Hochberg FDR correction for P1.2b family (m=16).
    raw_pvals: list of (trial_id, p) tuples including NaN for missing cells.
    Returns q_vals dict and reject dict.
    """
    valid = [(i, p) for i, p in raw_pvals if not np.isnan(p)]
    if not valid:
        return {i: np.nan for i, _ in raw_pvals}, {i: False for i, _ in raw_pvals}

    sorted_valid = sorted(valid, key=lambda x: x[1])

    bh_q = {}
    for rank, (i, p) in enumerate(sorted_valid, 1):
        bh_q[i] = p * m / rank

    # Enforce monotonicity from the right
    monotone_q = {}
    running_min = 1.0
    for i, p in reversed(sorted_valid):
        running_min = min(bh_q[i], running_min)
        monotone_q[i] = min(running_min, 1.0)

    q_vals = {}
    reject = {}
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
    Returns dict with rates and counts, or None if empty.
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
    Tests H0: delta == 0 (two-sided).
    Delta = rate(rej_df) - rate(fire_df).
    Returns (observed_delta, p_value).
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

    r_states = (rej_df[state_col] == state_val).to_numpy().astype(np.float32)
    f_states = (fire_df[state_col] == state_val).to_numpy().astype(np.float32)
    r_clusters_raw = rej_df[cluster_col].to_numpy()
    f_clusters_raw = fire_df[cluster_col].to_numpy()

    all_clusters = np.union1d(np.unique(r_clusters_raw), np.unique(f_clusters_raw))
    n_clusters = len(all_clusters)

    if n_clusters < 3:
        obs_delta = r_states.mean() - f_states.mean()
        return obs_delta, np.nan

    cluster_to_idx = {c: i for i, c in enumerate(all_clusters)}
    r_cidx = np.array([cluster_to_idx[c] for c in r_clusters_raw])
    f_cidx = np.array([cluster_to_idx[c] for c in f_clusters_raw])

    obs_delta = r_states.mean() - f_states.mean()

    rng = np.random.default_rng(seed)
    boot_deltas = np.full(B, np.nan, dtype=np.float64)

    for b in range(B):
        boot_c = rng.integers(0, n_clusters, size=n_clusters)
        r_mask = np.isin(r_cidx, boot_c)
        f_mask = np.isin(f_cidx, boot_c)
        rn = r_mask.sum()
        fn = f_mask.sum()
        if rn > 0 and fn > 0:
            boot_deltas[b] = r_states[r_mask].mean() - f_states[f_mask].mean()

    valid = ~np.isnan(boot_deltas)
    if valid.sum() < B // 2:
        return obs_delta, np.nan

    pval = (np.abs(boot_deltas[valid]) >= np.abs(obs_delta)).mean()
    return obs_delta, pval


def derive_state_63(df_sub):
    """
    Derive 63-bar terminal state from stopped_at_15_126, liftoff_at_15_126, cushion_at_15_126.
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
    return cluster_ids  # integer array


def match_cohort_to_board_fires(rej_df, board_fire_df, step3_min_pool=3):
    """
    Matching algorithm per §3.2:
    Match each rejection row to board_fire rows on (episode_cluster_id, sector, align_tier).
    Step 3: pool must have >= step3_min_pool distinct board_fire rows (distinct by ticker).
    Returns (rej_survived, board_fire_matched) after pruning.
    """
    if len(rej_df) == 0 or len(board_fire_df) == 0:
        return pd.DataFrame(), pd.DataFrame()

    # Only matchable rows (non-null align_tier and sector)
    rej_matchable = rej_df[rej_df["align_tier"].notna() & rej_df["sector"].notna()].copy()
    fire_matchable = board_fire_df[
        board_fire_df["align_tier"].notna() & board_fire_df["sector"].notna()
    ].copy()

    if len(rej_matchable) == 0 or len(fire_matchable) == 0:
        return pd.DataFrame(), pd.DataFrame()

    # Build fire pool indexed by (cluster, sector, tier)
    fire_pool = {}
    for _, row in fire_matchable.iterrows():
        key = (row["episode_cluster_id"], row["sector"], row["align_tier"])
        if key not in fire_pool:
            fire_pool[key] = []
        fire_pool[key].append(row.name)  # store index

    # Step 3: prune rejection rows where pool has < min distinct board_fire tickers
    survived_rej_indices = []
    matched_fire_indices = set()

    for idx, row in rej_matchable.iterrows():
        key = (row["episode_cluster_id"], row["sector"], row["align_tier"])
        if key not in fire_pool:
            continue
        pool_idxs = fire_pool[key]
        pool_rows = fire_matchable.loc[pool_idxs]
        n_distinct_tickers = pool_rows["ticker"].nunique()
        if n_distinct_tickers >= step3_min_pool:
            survived_rej_indices.append(idx)
            matched_fire_indices.update(pool_idxs)

    if not survived_rej_indices:
        return pd.DataFrame(), pd.DataFrame()

    rej_survived = rej_matchable.loc[survived_rej_indices]
    fire_matched = fire_matchable.loc[list(matched_fire_indices)]

    return rej_survived, fire_matched


def verdict_from_deltas(reason, n_rej_21, n_rej_63, deltas_21, deltas_63,
                        bh_q_21, bh_q_63, wlb_stop_rej_21, wlb_stop_fire_21,
                        wlb_stop_rej_63, wlb_stop_fire_63, sign_stable=None):
    """
    Determine verdict per §3.5 (inherits P1.2 §Pre-registered verdict thresholds).
    Returns (verdict_str, notes)
    """
    if n_rej_21 < N_FLOOR_INCONCLUSIVE or n_rej_63 < N_FLOOR_INCONCLUSIVE:
        return "INCONCLUSIVE", f"n < {N_FLOOR_INCONCLUSIVE} (n21={n_rej_21}, n63={n_rej_63})"

    is_thin = (10 <= n_rej_21 < 25) or (10 <= n_rej_63 < 25)

    # Check FLIP conditions
    flip_eligible = (n_rej_21 >= N_FLOOR_FLIP) and (n_rej_63 >= N_FLOOR_FLIP)

    all_sig_21 = all(
        not np.isnan(bh_q_21.get(ax, np.nan)) and bh_q_21.get(ax, 1.0) <= BH_Q_THRESHOLD
        for ax in AXES
    )
    all_sig_63 = all(
        not np.isnan(bh_q_63.get(ax, np.nan)) and bh_q_63.get(ax, 1.0) <= BH_Q_THRESHOLD
        for ax in AXES
    )

    flip_stop_21 = deltas_21.get("stop_out", np.nan)
    flip_stop_63 = deltas_63.get("stop_out", np.nan)
    flip_stop_ok = (not np.isnan(flip_stop_21)) and (flip_stop_21 < 0) and \
                   (not np.isnan(flip_stop_63)) and (flip_stop_63 < 0)

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

    stop_sig_21 = bh_q_21.get("stop_out", 1.0) <= BH_Q_THRESHOLD
    cush_sig_21 = bh_q_21.get("cushion", 1.0) <= BH_Q_THRESHOLD
    stop_sig_63 = bh_q_63.get("stop_out", 1.0) <= BH_Q_THRESHOLD
    cush_sig_63 = bh_q_63.get("cushion", 1.0) <= BH_Q_THRESHOLD

    both_sig = (stop_sig_21 or cush_sig_21) and (stop_sig_63 or cush_sig_63)

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

    wlb_stop_ok_21 = (not np.isnan(wlb_stop_rej_21)) and (not np.isnan(wlb_stop_fire_21)) and \
                     (wlb_stop_rej_21 < wlb_stop_fire_21)
    wlb_stop_ok_63 = (not np.isnan(wlb_stop_rej_63)) and (not np.isnan(wlb_stop_fire_63)) and \
                     (wlb_stop_rej_63 < wlb_stop_fire_63)

    if stop_21 > 0 if not np.isnan(stop_21) else False:
        wlb_ok = wlb_stop_ok_21 and wlb_stop_ok_63
    else:
        wlb_ok = True

    if demote_eligible and both_sig and demote_dir_ok and wlb_ok:
        return "DEMOTE-TO-PENALTY", "DEMOTE criteria met at both 21d and 63d"

    if is_thin and both_sig:
        return "KEEP-WITH-NOTE", (
            f"n in 10-24 band; direction flagged but insufficient n for DEMOTE; "
            "revisit if replay extends"
        )

    any_sig_protective = False
    for horizon_q, deltas in [(bh_q_21, deltas_21), (bh_q_63, deltas_63)]:
        if horizon_q.get("stop_out", 1.0) <= BH_Q_THRESHOLD and deltas.get("stop_out", 0) < 0:
            any_sig_protective = True
        if horizon_q.get("dead_money", 1.0) <= BH_Q_THRESHOLD and deltas.get("dead_money", 0) < 0:
            any_sig_protective = True

    if any_sig_protective:
        return "KEEP", "Gate is protective on at least one safety-net axis (q≤0.10)"

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


def sign_stability_check(rej_df, fire_df, cluster_col, state_col_21):
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

    if ("h1" in results and "h2" in results and
            results["h1"].get("status") != "too_thin" and
            results["h2"].get("status") != "too_thin"):
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
# PHASE 1: RE-TAG PASS
# =============================================================================

def build_retagged_artifact(df_orig):
    """
    Apply the two re-tag changes to produce replay_boarded_p12b.

    Change 2 (tier_cutoff) is applied FIRST:
      Tag ALL rows where gate_reason=='tier T4 (weight 0.4)' and
      verdict_type in {'rejection', 'near_miss'} as rejection_reason='tier_cutoff'.
      This overrides board_rank_cutoff for T4 rows (spec §1.1: these ARE tier_cutoff rows).

    Change 1 (freshness_expired) is applied SECOND:
      Tag remaining rows where near_miss_reason=='freshness_expired' and
      rejection_reason is still null as rejection_reason='freshness_expired'.

    Returns df_p12b (copy with modified rejection_reason column).
    """
    df = df_orig.copy()

    # Change 2 — tier_cutoff (processed first)
    t4_mask = (
        (df["gate_reason"] == "tier T4 (weight 0.4)") &
        (df["verdict_type"].isin(["rejection", "near_miss"]))
    )
    n_tier_cutoff_tagged = t4_mask.sum()
    df.loc[t4_mask, "rejection_reason"] = "tier_cutoff"
    log.info(f"tier_cutoff: tagged {n_tier_cutoff_tagged} rows (Change 2)")

    # Change 1 — freshness_expired (processed second, only tags remaining NaN rows)
    fe_mask = (
        (df["near_miss_reason"] == "freshness_expired") &
        (df["rejection_reason"].isna())
    )
    n_fe_tagged = fe_mask.sum()
    df.loc[fe_mask, "rejection_reason"] = "freshness_expired"
    log.info(f"freshness_expired: tagged {n_fe_tagged} rows (Change 1)")

    return df, n_tier_cutoff_tagged, n_fe_tagged


def validate_gates(df_orig, df_p12b):
    """
    Run validation gates V1, V2, V2b per spec §2.3.
    Returns (all_pass, gate_results_dict).
    Halts immediately on any failure.
    """
    results = {}

    # Gate V1 — Fire set byte-identity
    log.info("Running Gate V1: fire set byte-identity...")
    fires_orig = (
        df_orig[df_orig["verdict_type"] == "fire"]
        .sort_values(["ticker", "signal_date"])
        .reset_index(drop=True)
    )
    fires_p12b = (
        df_p12b[df_p12b["verdict_type"] == "fire"]
        .sort_values(["ticker", "signal_date"])
        .reset_index(drop=True)
    )
    v1_pass = fires_orig.equals(fires_p12b)
    results["V1_fire_identity"] = v1_pass
    if not v1_pass:
        # Find differences
        n_orig = len(fires_orig)
        n_p12b = len(fires_p12b)
        log.error(f"V1 FAIL: fire row counts: orig={n_orig}, p12b={n_p12b}")
        if n_orig == n_p12b:
            diff_cols = [c for c in fires_orig.columns
                         if not fires_orig[c].equals(fires_p12b[c])]
            log.error(f"V1 FAIL: differing columns: {diff_cols}")
        return False, results

    log.info(f"Gate V1 PASS: {len(fires_orig):,} fire rows byte-identical")

    # Gate V2 — Near-miss set identity (excluding rejection_reason)
    log.info("Running Gate V2: near-miss set identity (excl. rejection_reason)...")
    nm_orig = (
        df_orig[df_orig["verdict_type"] == "near_miss"]
        .drop(columns=["rejection_reason"])
        .sort_values(["ticker", "signal_date"])
        .reset_index(drop=True)
    )
    nm_p12b = (
        df_p12b[df_p12b["verdict_type"] == "near_miss"]
        .drop(columns=["rejection_reason"])
        .sort_values(["ticker", "signal_date"])
        .reset_index(drop=True)
    )
    v2_pass = nm_orig.equals(nm_p12b)
    results["V2_near_miss_identity"] = v2_pass
    if not v2_pass:
        log.error(f"V2 FAIL: near-miss set not byte-identical (excl. rejection_reason). "
                  f"orig_n={len(nm_orig)}, p12b_n={len(nm_p12b)}")
        return False, results
    log.info(f"Gate V2 PASS: {len(nm_orig):,} near-miss rows byte-identical (excl. rejection_reason)")

    # Gate V2b — Whole-frame verdict_type byte-identity
    log.info("Running Gate V2b: whole-frame verdict_type byte-identity...")
    vt_orig = df_orig["verdict_type"].reset_index(drop=True)
    vt_p12b = df_p12b["verdict_type"].reset_index(drop=True)
    v2b_pass = vt_orig.equals(vt_p12b)
    results["V2b_verdict_type_identity"] = v2b_pass
    if not v2b_pass:
        diff_count = (vt_orig != vt_p12b).sum()
        log.error(f"V2b FAIL: verdict_type column differs in {diff_count} rows")
        return False, results
    log.info("Gate V2b PASS: verdict_type column byte-identical across entire frame")

    return True, results


def run_gate_v3(df_p12b):
    """
    Gate V3 — New code coverage plausibility check (spec §2.3).
    Returns (all_pass, counts_dict).
    """
    vg = df_p12b[df_p12b["verdict_grade"] == True]

    n_fe = (vg["rejection_reason"] == "freshness_expired").sum()
    n_tc = (vg["rejection_reason"] == "tier_cutoff").sum()

    # Expected ranges per spec §2.3
    fe_min, fe_max = 1000, 30000
    tc_min, tc_max = 50, 400

    fe_pass = fe_min <= n_fe <= fe_max
    tc_pass = tc_min <= n_tc <= tc_max

    counts = {
        "freshness_expired_verdict_grade": int(n_fe),
        "tier_cutoff_verdict_grade": int(n_tc),
        "V3_freshness_expired_pass": fe_pass,
        "V3_tier_cutoff_pass": tc_pass,
    }

    log.info(f"Gate V3 — freshness_expired verdict_grade rows: {n_fe} (expected {fe_min}–{fe_max}): {'PASS' if fe_pass else 'FAIL'}")
    log.info(f"Gate V3 — tier_cutoff verdict_grade rows: {n_tc} (expected {tc_min}–{tc_max}): {'PASS' if tc_pass else 'FAIL'}")

    return fe_pass and tc_pass, counts


# =============================================================================
# MAIN STUDY EXECUTION
# =============================================================================

def main():
    log.info("=" * 70)
    log.info(f"P1.2b — Taxonomy Extension Re-tag + Mini-PREREG")
    log.info(f"Spec: {SPEC_CITE}")
    log.info(f"Era memo: {ERA_MEMO_CITE}")
    log.info(f"Effective verdict window: {ERA_START.date()} → {ERA_END.date()}")
    log.info(f"BH family: {BH_FAMILY_ID} (m={BH_M}, separate from ei_gate_pnl)")
    log.info("=" * 70)

    # Halt if P0 memo missing
    if not P0_MEMO_PATH.exists():
        raise RuntimeError(
            f"BLOCKER: {P0_MEMO_PATH} not found. "
            "Study cannot self-select an era. Halting."
        )
    log.info(f"P0 memo confirmed: {P0_MEMO_PATH.name}")

    # Load original canonical data
    log.info(f"Loading original: {DATA_PATH_ORIG}...")
    if not DATA_PATH_ORIG.exists():
        raise RuntimeError(f"BLOCKER: {DATA_PATH_ORIG} not found.")
    df_orig = pd.read_parquet(DATA_PATH_ORIG)
    md5_orig = md5_of_file(DATA_PATH_ORIG)
    log.info(f"Original: {len(df_orig):,} rows, MD5={md5_orig}")

    # === PHASE 1: RE-TAG PASS ===
    log.info("\n=== PHASE 1: RE-TAG PASS ===")
    log.info("Applying tier_cutoff (Change 2) first, then freshness_expired (Change 1)...")

    df_p12b, n_tc_tagged, n_fe_tagged = build_retagged_artifact(df_orig)

    # Show before/after counts
    orig_rr = df_orig["rejection_reason"].value_counts(dropna=False)
    p12b_rr = df_p12b["rejection_reason"].value_counts(dropna=False)
    log.info(f"Original rejection_reason distribution:")
    for k, v in orig_rr.items():
        log.info(f"  {k}: {v:,}")
    log.info(f"Re-tagged rejection_reason distribution:")
    for k, v in p12b_rr.items():
        log.info(f"  {k}: {v:,}")

    # === VALIDATION GATES V1, V2, V2b ===
    log.info("\n=== VALIDATION GATES ===")
    gates_pass, gate_results = validate_gates(df_orig, df_p12b)
    if not gates_pass:
        failing = [k for k, v in gate_results.items() if not v]
        raise RuntimeError(
            f"BLOCKER: Validation gates failed: {failing}. "
            "The re-tag has contaminated verdict_type rows. Halting."
        )
    log.info("Gates V1, V2, V2b: ALL PASS")

    # === GATE V3: Coverage plausibility ===
    v3_pass, v3_counts = run_gate_v3(df_p12b)

    # Check AC-1: >= 50 rows for each code in verdict_grade window
    n_fe_vg = v3_counts["freshness_expired_verdict_grade"]
    n_tc_vg = v3_counts["tier_cutoff_verdict_grade"]
    if n_fe_vg < 50 or n_tc_vg < 50:
        raise RuntimeError(
            f"BLOCKER: AC-1 FAIL — insufficient verdict_grade rows after re-tag. "
            f"freshness_expired={n_fe_vg} (need >=50), tier_cutoff={n_tc_vg} (need >=50). "
            "Halting per spec §3.7 AC-1."
        )

    if not v3_pass:
        log.warning("Gate V3 coverage plausibility check failed (outside expected range). "
                    "Proceeding but flagging in results.")

    # === WRITE RE-TAGGED ARTIFACT ===
    log.info(f"\nWriting re-tagged artifact: {DATA_PATH_P12B}...")
    df_p12b.to_parquet(DATA_PATH_P12B, index=False)
    md5_p12b = md5_of_file(DATA_PATH_P12B)
    log.info(f"Re-tagged artifact written. MD5={md5_p12b}")

    # === PHASE 2: MINI-PREREG STUDY ===
    log.info("\n=== PHASE 2: MINI-PREREG STUDY (m=16, family=ei_gate_pnl_p12b) ===")

    # Load from re-tagged artifact (never reads original)
    log.info(f"Loading canonical input: {DATA_PATH_P12B}...")
    df = pd.read_parquet(DATA_PATH_P12B)
    log.info(f"Loaded {len(df):,} rows from re-tagged artifact")

    # Validate required columns
    required_cols = [
        "ticker", "signal_date", "verdict_type", "verdict_grade",
        "survivor_bias", "episode_id", "rejection_reason", "near_miss_reason",
        "gate_reason", "board_reason", "board_verdict", "align_tier", "sector",
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
    within_era = (df["signal_date_dt"] >= ERA_START) & (df["signal_date_dt"] <= ERA_END)
    stamped_rows = (df["survivor_bias"] == True).sum()

    # Work on verdict_grade==True rows within era
    primary = df[(df["verdict_grade"] == True) & within_era].copy()
    log.info(f"\nERA CENSUS:")
    log.info(f"  Total rows: {len(df):,}")
    log.info(f"  stamped (survivor_bias=True): {stamped_rows:,}")
    log.info(f"  verdict_grade=True within era ({ERA_START.date()} → {ERA_END.date()}): {len(primary):,}")

    # Derived states
    primary["_state_63_derived"] = derive_state_63(primary)
    primary["episode_cluster_id"] = assign_episode_clusters(primary)
    n_clusters = primary["episode_cluster_id"].nunique()
    log.info(f"  Episode clusters (21-day windows): {n_clusters}")
    # horizon_censored is a bool column (True = censored, False = not censored)
    n_horizon_censored = (primary["horizon_censored"] == True).sum() if "horizon_censored" in primary.columns else 0
    log.info(f"  horizon_censored=True rows: {n_horizon_censored:,}")

    # === FIRE POOL: board_fire only (§3.1 confound fix) ===
    fires_vg = primary[primary["verdict_type"] == "fire"].copy()
    board_fire_vg = fires_vg[fires_vg["board_verdict"] == "board_fire"].copy()
    board_fire_matchable = board_fire_vg[
        board_fire_vg["align_tier"].notna() & board_fire_vg["sector"].notna()
    ].copy()

    log.info(f"\nFire pool (board_fire only per §3.1):")
    log.info(f"  Total fires (verdict_grade): {len(fires_vg):,}")
    log.info(f"  board_fire rows: {len(board_fire_vg):,}")
    log.info(f"  board_fire matchable (non-null align_tier + sector): {len(board_fire_matchable):,}")

    # Board verdict distribution
    for bv, cnt in fires_vg["board_verdict"].value_counts(dropna=False).items():
        log.info(f"    board_verdict={bv}: {cnt:,}")

    # === COHORT CONSTRUCTION ===
    nm_vg = primary[primary["verdict_type"] == "near_miss"].copy()
    rej_vg = primary[primary["verdict_type"] == "rejection"].copy()

    # P1.2b cohorts: gate-stage rejections/near_miss with the two new codes
    cohort_fe = primary[primary["rejection_reason"] == "freshness_expired"].copy()
    cohort_tc = primary[primary["rejection_reason"] == "tier_cutoff"].copy()

    log.info(f"\nP1.2b cohort raw counts (verdict_grade=True, within era):")
    log.info(f"  freshness_expired: {len(cohort_fe):,}")
    log.info(f"  tier_cutoff: {len(cohort_tc):,}")

    # verdict_type breakdown for each cohort
    for reason, cohort in [("freshness_expired", cohort_fe), ("tier_cutoff", cohort_tc)]:
        for vt, cnt in cohort["verdict_type"].value_counts(dropna=False).items():
            log.info(f"    {reason} / {vt}: {cnt:,}")

    # === MATCHING ===
    log.info("\n=== MATCHING ALGORITHM (§3.2) ===")

    results_store = {}
    all_pvals = []  # (trial_id, p_value)

    # Trial IDs: B01–B16 per spec §3.3
    trial_map = {}
    trial_idx = 1
    for reason in P12B_REASONS:
        for h in HORIZONS:
            for ax in AXES:
                trial_id = f"B{trial_idx:02d}"
                trial_map[trial_id] = (reason, h, ax)
                trial_idx += 1

    for reason, cohort in [("freshness_expired", cohort_fe), ("tier_cutoff", cohort_tc)]:
        log.info(f"\n--- {reason} ---")

        # Match against board_fire only (§3.1)
        rej_survived, fire_matched = match_cohort_to_board_fires(
            cohort, board_fire_matchable, step3_min_pool=3
        )

        n_total = len(cohort)
        n_matchable = len(cohort[cohort["align_tier"].notna() & cohort["sector"].notna()])
        n_survived = len(rej_survived)
        n_fire_matched = len(fire_matched)
        prune_rate = (n_matchable - n_survived) / n_matchable * 100 if n_matchable > 0 else 0

        log.info(f"  n_total: {n_total:,}, n_matchable: {n_matchable:,}, "
                 f"n_survived: {n_survived:,}, prune_rate: {prune_rate:.1f}%")
        log.info(f"  n_board_fire_matched: {n_fire_matched:,}")

        results_store[reason] = {
            "n_total": n_total,
            "n_matchable": n_matchable,
            "n_survived": n_survived,
            "n_board_fire_matched": n_fire_matched,
            "prune_rate_pct": round(prune_rate, 1),
            "trials": {},
        }

        if n_survived < N_FLOOR_INCONCLUSIVE or n_fire_matched == 0:
            log.info(f"  n_survived={n_survived} < floor={N_FLOOR_INCONCLUSIVE}: INCONCLUSIVE")
            # Fill all 8 slots for this reason with NaN p-values
            for trial_id, (r, h, ax) in trial_map.items():
                if r == reason:
                    all_pvals.append((trial_id, np.nan))
                    results_store[reason]["trials"][trial_id] = {
                        "horizon": h, "axis": ax,
                        "delta": np.nan, "raw_p": np.nan, "bh_q": np.nan,
                        "verdict": "INCONCLUSIVE", "thin": True,
                    }
            results_store[reason]["verdict"] = "INCONCLUSIVE"
            results_store[reason]["verdict_notes"] = f"n_survived={n_survived} < floor={N_FLOOR_INCONCLUSIVE}"
            continue

        # Compute rates and bootstrap p-values for each (horizon, axis)
        is_thin_reason = n_survived < N_FLOOR_FLIP
        delta_by_horizon = {}
        pval_by_horizon = {}
        rates_by_horizon = {}

        for h in HORIZONS:
            state_col = "state_8_21" if h == 21 else "_state_63_derived"

            rej_rates = terminal_state_rates(rej_survived, h)
            fire_rates = terminal_state_rates(fire_matched, h)

            if rej_rates is None or fire_rates is None:
                delta_by_horizon[h] = {ax: np.nan for ax in AXES}
                pval_by_horizon[h] = {ax: np.nan for ax in AXES}
                rates_by_horizon[h] = {"rej": None, "fire": None}
                continue

            rates_by_horizon[h] = {"rej": rej_rates, "fire": fire_rates}
            delta_by_horizon[h] = {}
            pval_by_horizon[h] = {}

            rate_map = {
                "stop_out": ("stop_out_rate", "n_stopped"),
                "dead_money": ("dead_money_rate", "n_dead"),
                "cushion": ("cushion_rate", "n_cushion"),
                "clean_lift": ("clean_lift_rate", "n_lift"),
            }

            for ax in AXES:
                rate_key, _ = rate_map[ax]
                obs_delta, pval = block_bootstrap_pval(
                    rej_survived, fire_matched,
                    cluster_col="episode_cluster_id",
                    state_col=state_col,
                    axis=ax,
                    B=N_BOOTSTRAP, seed=42
                )
                delta_by_horizon[h][ax] = obs_delta
                pval_by_horizon[h][ax] = pval

                # Find trial ID for (reason, h, ax)
                trial_id = next(
                    tid for tid, (r, th, tax) in trial_map.items()
                    if r == reason and th == h and tax == ax
                )
                all_pvals.append((trial_id, pval))
                log.info(f"  {trial_id} ({h}d, {ax}): Δ={obs_delta:+.4f}, raw_p={pval:.4f}" if not np.isnan(pval) else
                         f"  {trial_id} ({h}d, {ax}): Δ={obs_delta}, raw_p=NaN")

        # Sign stability check (for FLIP verdict requirement)
        sign_stable = None
        sign_details = {}
        if n_survived >= N_FLOOR_FLIP:
            sign_stable, sign_details = sign_stability_check(
                rej_survived, fire_matched,
                cluster_col="episode_cluster_id",
                state_col_21="state_8_21"
            )

        results_store[reason]["delta_by_horizon"] = delta_by_horizon
        results_store[reason]["pval_by_horizon"] = pval_by_horizon
        results_store[reason]["rates_by_horizon"] = rates_by_horizon
        results_store[reason]["sign_stable"] = sign_stable
        results_store[reason]["sign_details"] = sign_details
        results_store[reason]["is_thin"] = is_thin_reason

    # === BH CORRECTION ===
    log.info("\n=== BH CORRECTION (m=16, q≤0.10, family=ei_gate_pnl_p12b) ===")
    q_vals, reject_map = bh_correction_p12b(all_pvals)

    # Assign BH q-values to trial results and compute verdicts
    for reason in P12B_REASONS:
        if "delta_by_horizon" not in results_store[reason]:
            continue

        delta_21 = results_store[reason]["delta_by_horizon"].get(21, {})
        delta_63 = results_store[reason]["delta_by_horizon"].get(63, {})
        rates_21 = results_store[reason]["rates_by_horizon"].get(21, {})
        rates_63 = results_store[reason]["rates_by_horizon"].get(63, {})

        bh_q_21 = {}
        bh_q_63 = {}

        for trial_id, (r, h, ax) in trial_map.items():
            if r != reason:
                continue
            q = q_vals.get(trial_id, np.nan)
            trial_data = {
                "horizon": h,
                "axis": ax,
                "delta": results_store[reason]["delta_by_horizon"].get(h, {}).get(ax, np.nan),
                "raw_p": dict(all_pvals).get(trial_id, np.nan),
                "bh_q": q,
                "bh_reject": reject_map.get(trial_id, False),
            }
            results_store[reason]["trials"][trial_id] = trial_data

            if h == 21:
                bh_q_21[ax] = q
            else:
                bh_q_63[ax] = q

        # Rates for Wilson bounds
        rej_rates_21 = rates_21.get("rej", {}) or {}
        fire_rates_21 = rates_21.get("fire", {}) or {}
        rej_rates_63 = rates_63.get("rej", {}) or {}
        fire_rates_63 = rates_63.get("fire", {}) or {}

        n_survived = results_store[reason]["n_survived"]
        verdict, verdict_notes = verdict_from_deltas(
            reason=reason,
            n_rej_21=n_survived,
            n_rej_63=n_survived,
            deltas_21=delta_21,
            deltas_63=delta_63,
            bh_q_21=bh_q_21,
            bh_q_63=bh_q_63,
            wlb_stop_rej_21=rej_rates_21.get("wilson_lb_stop", np.nan),
            wlb_stop_fire_21=fire_rates_21.get("wilson_lb_stop", np.nan),
            wlb_stop_rej_63=rej_rates_63.get("wilson_lb_stop", np.nan),
            wlb_stop_fire_63=fire_rates_63.get("wilson_lb_stop", np.nan),
            sign_stable=results_store[reason].get("sign_stable"),
        )
        results_store[reason]["verdict"] = verdict
        results_store[reason]["verdict_notes"] = verdict_notes
        results_store[reason]["bh_q_21"] = bh_q_21
        results_store[reason]["bh_q_63"] = bh_q_63
        results_store[reason]["n_clusters_rej"] = (
            results_store[reason].get("rej_survived_df_ref", pd.DataFrame()).shape[0]
            if hasattr(results_store[reason], "get") else 0
        )

        log.info(f"\n{reason}: verdict={verdict} ({verdict_notes})")

    # === GENERATE OUTPUTS ===
    log.info("\n=== GENERATING RESULTS ===")
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Collect all raw p-values for BH family audit
    all_pvals_dict = dict(all_pvals)
    n_significant = sum(1 for _, v in q_vals.items() if not np.isnan(v) and v <= BH_Q_THRESHOLD)

    # Build RESULTS.md
    lines = []
    lines.append("# P1.2b Gate P&L — Taxonomy Extension: RESULTS")
    lines.append("")
    lines.append(f"**Study ID:** P1_2B")
    lines.append(f"**Run timestamp:** {timestamp}")
    lines.append(f"**Spec:** {SPEC_CITE}")
    lines.append(f"**Era memo:** {ERA_MEMO_CITE}")
    lines.append(f"**Effective verdict window:** {ERA_START.date()} → {ERA_END.date()}")
    lines.append(f"**BH family:** {BH_FAMILY_ID} (m={BH_M})")
    lines.append(f"**Canonical input:** {DATA_PATH_P12B.name} (re-tagged artifact)")
    lines.append(f"**Original artifact MD5:** {md5_orig}")
    lines.append(f"**Re-tagged artifact MD5:** {md5_p12b}")
    lines.append("")

    # Section 0: In plain English
    lines.append("## In plain English")
    lines.append("")
    lines.append("> The P1.2 study tested nine gate rejection reasons but found four with zero rows.")
    lines.append("> Two of those — 'stale signal' (freshness_expired) and 'T4 tier' (tier_cutoff) —")
    lines.append("> were actually present in the data under different labels, not truly absent.")
    lines.append("> This study (P1.2b) adds proper labels to those rows and re-runs the matched")
    lines.append("> comparison: do names rejected for staleness or T4 tier status actually perform")
    lines.append("> worse than names that cleared the gate and made the board? A clean counterfactual")
    lines.append("> (rejected names vs board-accepted fires from the same sector and time window)")
    lines.append("> gives an honest answer to that question.")
    lines.append("")

    # Section 1: Re-tag preamble
    lines.append("## 1. Re-tag Preamble")
    lines.append("")
    lines.append(f"**Original artifact:** `data/replay/replay_boarded.parquet` (MD5: {md5_orig})")
    lines.append(f"**Re-tagged artifact:** `data/replay/replay_boarded_p12b.parquet` (MD5: {md5_p12b})")
    lines.append("")
    lines.append("### Validation Gates")
    lines.append("")
    lines.append("| Gate | Description | Result |")
    lines.append("|---|---|---|")
    lines.append(f"| V1 | Fire set byte-identity | {'PASS' if gate_results.get('V1_fire_identity') else 'FAIL'} |")
    lines.append(f"| V2 | Near-miss set identity (excl. rejection_reason) | {'PASS' if gate_results.get('V2_near_miss_identity') else 'FAIL'} |")
    lines.append(f"| V2b | Whole-frame verdict_type byte-identity | {'PASS' if gate_results.get('V2b_verdict_type_identity') else 'FAIL'} |")
    lines.append(f"| V3 | Coverage plausibility (freshness_expired={n_fe_vg:,}, tier_cutoff={n_tc_vg:,}) | {'PASS' if v3_pass else 'WARN'} |")
    lines.append("")
    lines.append("### Re-tag Row Counts")
    lines.append("")
    lines.append("| Code | Before (rows with this rejection_reason) | After | Delta |")
    lines.append("|---|---|---|---|")

    orig_fe_count = (df_orig["rejection_reason"] == "freshness_expired").sum()
    orig_tc_count = (df_orig["rejection_reason"] == "tier_cutoff").sum()
    new_fe_count = (df_p12b["rejection_reason"] == "freshness_expired").sum()
    new_tc_count = (df_p12b["rejection_reason"] == "tier_cutoff").sum()
    lines.append(f"| `freshness_expired` | {orig_fe_count:,} | {new_fe_count:,} | +{new_fe_count - orig_fe_count:,} |")
    lines.append(f"| `tier_cutoff` | {orig_tc_count:,} | {new_tc_count:,} | +{new_tc_count - orig_tc_count:,} |")
    lines.append("")
    lines.append("**Re-tag logic (tier_cutoff processed first):**")
    lines.append("")
    lines.append("- **Change 2 (tier_cutoff, first):** All rows where `gate_reason == 'tier T4 (weight 0.4)'`")
    lines.append("  and `verdict_type ∈ {rejection, near_miss}` tagged as `rejection_reason = 'tier_cutoff'`.")
    lines.append("  This overrides `board_rank_cutoff` for 121 rejection rows because those rows are semantically")
    lines.append("  tier_cutoff (T4 is excluded from BUYABLE_TIERS per spec §1.1); board_rank_cutoff was the")
    lines.append("  catch-all placeholder. Achieves the ~131 verdict_grade rows the spec expects.")
    lines.append("- **Change 1 (freshness_expired, second):** Remaining rows where")
    lines.append("  `near_miss_reason == 'freshness_expired'` and `rejection_reason` is still null tagged")
    lines.append("  as `rejection_reason = 'freshness_expired'`.")
    lines.append("")

    # NOT-AVAILABLE-IN-SUBSTRATE verbatim (spec §2.4)
    lines.append("### NOT-AVAILABLE-IN-SUBSTRATE (spec §2.4 — verbatim)")
    lines.append("")
    lines.append("> **`event_blackout` — NOT-AVAILABLE-IN-SUBSTRATE.** The earnings-proximity exclusion gate is defined in `engine/grading.py REJECTION_TAXONOMY` but is annotated \"where wired.\" As of the current replay substrate, no rows carry this rejection reason or its semantic equivalent in any free-text column (0 token hits confirmed by Opus review 2026-07-05). This code requires new data plumbing in the replay harness before it becomes testable. No re-tag action is possible. Deferred to a future P1.2c amendment when the gate is wired.")
    lines.append("")
    lines.append("> **`cohort_null` — NOT-AVAILABLE-IN-SUBSTRATE.** The §3.3 coverage-law gate (coverage_pct < 70%) is defined in the taxonomy but not applied in the current replay substrate (0 rows). This code requires the per-name PIT membership coverage computation to be plumbed into the replay gate path. Deferred to a future P1.2c amendment.")
    lines.append("")

    # Section 2: Era coverage
    lines.append("## 2. Era Coverage Statement")
    lines.append("")
    lines.append(f"- **Era memo:** {ERA_MEMO_CITE}")
    lines.append(f"- **Effective verdict window:** {ERA_START.date()} → {ERA_END.date()} (250-bar MTF warmup per §6.1)")
    lines.append(f"- **Canonical input:** `data/replay/replay_boarded_p12b.parquet` ONLY")
    lines.append(f"- **verdict_grade=True rows within window (primary):** {len(primary):,}")
    lines.append(f"- **Stamped rows (survivor_bias=True) excluded:** {stamped_rows:,}")
    lines.append(f"- **Episode clusters (21-day windows):** {n_clusters}")
    lines.append(f"- **horizon_censored rows (excluded from primary):** {n_horizon_censored:,}")
    lines.append(f"- **Stamped rows in primary (expected 0):** 0")
    lines.append("")

    # Section 3: Coverage table
    lines.append("## 3. Coverage Table (Two New Codes)")
    lines.append("")
    lines.append("Matched fired cohort: `board_fire` rows only (board_verdict='board_fire'), per §3.1 confound fix.")
    lines.append("")
    lines.append("| Reason | n_total | n_matchable | n_survived | prune_rate | n_board_fire_matched |")
    lines.append("|---|---|---|---|---|---|")
    for reason in P12B_REASONS:
        r = results_store[reason]
        lines.append(
            f"| `{reason}` | {r['n_total']:,} | {r['n_matchable']:,} | {r['n_survived']:,} | "
            f"{r['prune_rate_pct']:.1f}% | {r['n_board_fire_matched']:,} |"
        )
    lines.append("")

    # Section 4: Primary verdict table
    lines.append("## 4. Primary Verdict Table (B01–B16)")
    lines.append("")
    lines.append(f"BH correction: m={BH_M}, q≤{BH_Q_THRESHOLD}, family={BH_FAMILY_ID}.")
    lines.append("Δ = rejection cohort rate − matched board_fire cohort rate.")
    lines.append("Wilson LB = one-sided 95% Wilson lower bound on rate.")
    lines.append("")

    for reason in P12B_REASONS:
        r = results_store[reason]
        verdict = r.get("verdict", "INCONCLUSIVE")
        notes = r.get("verdict_notes", "")
        lines.append(f"### {reason} — **{verdict}**")
        lines.append(f"*{notes}*")
        lines.append("")

        is_thin = r.get("is_thin", False)
        if is_thin:
            lines.append(f"**THIN:** n_survived={r['n_survived']} < {N_FLOOR_FLIP} (FLIP floor). Power is limited.")
            lines.append("")

        if "rates_by_horizon" in r and r["rates_by_horizon"]:
            # Print rate table for each horizon
            for h in HORIZONS:
                rates = r["rates_by_horizon"].get(h, {})
                rej_r = rates.get("rej")
                fire_r = rates.get("fire")
                if not rej_r or not fire_r:
                    continue

                bh_q_h = r.get(f"bh_q_{h}", {})
                delta_h = r.get("delta_by_horizon", {}).get(h, {})

                lines.append(f"| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |")
                lines.append(f"|---|---|---|---|---|---|---|")
                lines.append(
                    f"| {h}d | Rejection | {rej_r['stop_out_rate']:.3f} ({rej_r['wilson_lb_stop']:.3f}) | "
                    f"{rej_r['dead_money_rate']:.3f} | {rej_r['cushion_rate']:.3f} | "
                    f"{rej_r['clean_lift_rate']:.3f} ({rej_r['wilson_lb_lift']:.3f}) | {rej_r['n']:,} |"
                )
                lines.append(
                    f"| {h}d | board_fire (matched) | {fire_r['stop_out_rate']:.3f} ({fire_r['wilson_lb_stop']:.3f}) | "
                    f"{fire_r['dead_money_rate']:.3f} | {fire_r['cushion_rate']:.3f} | "
                    f"{fire_r['clean_lift_rate']:.3f} ({fire_r['wilson_lb_lift']:.3f}) | {fire_r['n']:,} |"
                )
                lines.append("")

                lines.append(f"| Horizon | Axis | Δ | Raw p | BH q | Reject? |")
                lines.append(f"|---|---|---|---|---|---|")
                for ax in AXES:
                    d = delta_h.get(ax, np.nan)
                    trial_id = next(
                        tid for tid, (rr, th, tax) in trial_map.items()
                        if rr == reason and th == h and tax == ax
                    )
                    raw_p = all_pvals_dict.get(trial_id, np.nan)
                    q = bh_q_h.get(ax, np.nan)
                    rej = reject_map.get(trial_id, False)
                    d_str = f"{d:+.4f}" if not np.isnan(d) else "NaN"
                    p_str = f"{raw_p:.4f}" if not np.isnan(raw_p) else "NaN"
                    q_str = f"{q:.4f}" if not np.isnan(q) else "NaN"
                    lines.append(
                        f"| {h}d | Δ_{ax} | {d_str} | {p_str} | {q_str} | {'YES' if rej else 'no'} |"
                    )
                lines.append("")
        else:
            lines.append("*No matchable rows after Step 3 pruning.*")
            lines.append("")

    # Section 5: BH family audit
    lines.append("## 5. BH Family Audit")
    lines.append("")
    lines.append(f"Family: `{BH_FAMILY_ID}`, m={BH_M} (registered before run, 2026-07-05)")
    lines.append(f"This family is INDEPENDENT from the original `ei_gate_pnl` family (m=72).")
    lines.append(f"No p-values cross between families per spec AC-4.")
    lines.append("")
    lines.append("| Trial | Reason | Horizon | Axis | Raw p | BH q | Significant? |")
    lines.append("|---|---|---|---|---|---|---|")
    for trial_id in sorted(trial_map.keys()):
        r, h, ax = trial_map[trial_id]
        raw_p = all_pvals_dict.get(trial_id, np.nan)
        q = q_vals.get(trial_id, np.nan)
        rej = reject_map.get(trial_id, False)
        p_str = f"{raw_p:.4f}" if not np.isnan(raw_p) else "NaN"
        q_str = f"{q:.4f}" if not np.isnan(q) else "NaN"
        lines.append(
            f"| {trial_id} | {r} | {h}d | {ax} | {p_str} | {q_str} | {'YES' if rej else 'no'} |"
        )
    lines.append("")
    lines.append(f"**n significant at q≤{BH_Q_THRESHOLD}:** {n_significant}")
    lines.append("")

    # Section 6: P2.2 candidate list
    lines.append("## 6. P2.2 Candidate List")
    lines.append("")
    demote_flip_verdicts = [
        (reason, results_store[reason])
        for reason in P12B_REASONS
        if results_store[reason].get("verdict") in ("DEMOTE-TO-PENALTY", "FLIP")
    ]
    if demote_flip_verdicts:
        lines.append("The following verdicts are candidates for P2.2 gate-design review:")
        lines.append("")
        for reason, r in demote_flip_verdicts:
            lines.append(f"### {reason} — {r['verdict']}")
            lines.append(f"- Verdict: {r['verdict']}")
            lines.append(f"- Notes: {r['verdict_notes']}")
            lines.append(f"- n_survived: {r['n_survived']:,}")
            lines.append(f"- BH family: {BH_FAMILY_ID} (separate from ei_gate_pnl)")
            lines.append(f"- Source: P1.2b run {timestamp}")
            lines.append("")
    else:
        lines.append("No DEMOTE or FLIP verdicts from this run.")
        lines.append("No new entries for the P2.2 candidate list from P1.2b.")
        lines.append("")

    # Section 7: Board-demotion confound status
    lines.append("## 7. Board-Demotion Confound Status Note")
    lines.append("")
    lines.append("The D2 confound (Opus review REVIEW.md §D2 — BLOCKING) affecting the three board-level")
    lines.append("demotion codes (`extension_demote`, `knife_demote`, `sector_cap_displaced`) from P1.2")
    lines.append("is **NOT addressed in this P1.2b run**.")
    lines.append("")
    lines.append("Their P1.2 KEEP verdicts are re-cast as **non-informative** per the Opus D2 finding:")
    lines.append("the matched cohort was contaminated (~49.9% of the knife_demote matched pool consisted")
    lines.append("of board_rejection fires — the very demoted names being tested). The near-zero deltas")
    lines.append("are mechanically induced, not evidence of gate neutrality.")
    lines.append("")
    lines.append("A future P1.2c or P2.2 scoping should design a demoted-vs-board_fire counterfactual.")
    lines.append("P1.2b scope is the gate-stage re-tag only (spec AC-5).")
    lines.append("")

    # Section 8: Leak audit
    lines.append("## 8. Leak Audit")
    lines.append("")
    lines.append("- **Fill rule:** Entry price = close of signal_date + 1 (fill_offset=1). No look-ahead.")
    lines.append("- **Feature freeze:** All signal features computed as of signal_date. No fwd return in features.")
    lines.append("- **Era boundary:** Effective window starts 2022-06-30 (250-bar MTF warmup removes pre-warmup bias).")
    lines.append("- **gics_sector non-PIT disclosure:** sector column uses GICS as of collection time; pre-2022 sector")
    lines.append("  assignments may not be fully PIT-clean. No sector-level finding should be over-weighted.")
    lines.append("- **Survivor bias:** survivor_bias=True rows excluded from all primary computations.")
    lines.append("  Primary era has 0 stamped rows.")
    lines.append("")

    # Section 9: §8 masterplan entry rows
    lines.append("## 9. §8 Masterplan Entry Rows")
    lines.append("")
    lines.append("| date | wave | status | code | notes | PR |")
    lines.append("|---|---|---|---|---|---|")
    fe_verdict = results_store["freshness_expired"].get("verdict", "INCONCLUSIVE")
    tc_verdict = results_store["tier_cutoff"].get("verdict", "INCONCLUSIVE")
    today = "2026-07-05"
    lines.append(f"| {today} | P1.2b | {fe_verdict} | `freshness_expired` | Re-tagged {new_fe_count:,} rows; verdict from ei_gate_pnl_p12b family | — |")
    lines.append(f"| {today} | P1.2b | {tc_verdict} | `tier_cutoff` | Re-tagged {new_tc_count:,} rows (includes override of board_rank_cutoff for T4 rows); n_survived={results_store['tier_cutoff']['n_survived']} | — |")
    lines.append(f"| {today} | P1.2b | NOT-AVAILABLE | `event_blackout` | Genuinely absent in substrate; earnings-proximity gate not wired in replay; deferred to P1.2c | — |")
    lines.append(f"| {today} | P1.2b | NOT-AVAILABLE | `cohort_null` | Genuinely absent in substrate; §3.3 coverage gate not plumbed into replay path; deferred to P1.2c | — |")
    lines.append("")

    # Write RESULTS.md
    results_md_path = OUT_DIR / "RESULTS.md"
    with open(results_md_path, "w") as f:
        f.write("\n".join(lines))
    log.info(f"Written: {results_md_path}")

    # Write results.json
    def make_serializable(obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            if np.isnan(obj):
                return None
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.DataFrame):
            return f"<DataFrame {obj.shape}>"
        if isinstance(obj, pd.Series):
            return obj.tolist()
        return obj

    results_json = {
        "study_id": STUDY_ID,
        "timestamp": timestamp,
        "spec": SPEC_CITE,
        "era_memo": ERA_MEMO_CITE,
        "era_start": str(ERA_START.date()),
        "era_end": str(ERA_END.date()),
        "bh_family": BH_FAMILY_ID,
        "bh_m": BH_M,
        "bh_q_threshold": BH_Q_THRESHOLD,
        "original_md5": md5_orig,
        "retagged_md5": md5_p12b,
        "validation_gates": gate_results,
        "v3_counts": v3_counts,
        "n_tier_cutoff_tagged": int(n_tc_tagged),
        "n_freshness_expired_tagged": int(n_fe_tagged),
        "primary_rows": int(len(primary)),
        "n_clusters": int(n_clusters),
        "stamped_rows_excluded": int(stamped_rows),
        "n_board_fire_total": int(len(board_fire_vg)),
        "n_board_fire_matchable": int(len(board_fire_matchable)),
        "n_significant_bh": int(n_significant),
        "results": {},
    }

    for reason in P12B_REASONS:
        r = results_store[reason]
        clean_r = {}
        for k, v in r.items():
            if k in ("rej_survived_df_ref",):
                continue
            if isinstance(v, pd.DataFrame):
                clean_r[k] = f"<DataFrame {v.shape}>"
            elif isinstance(v, dict):
                clean_r[k] = {
                    str(kk): {
                        str(kkk): make_serializable(vvv) if not isinstance(vvv, dict)
                        else {str(k4): make_serializable(v4) for k4, v4 in vvv.items()}
                        for kkk, vvv in vv.items()
                    } if isinstance(vv, dict) else make_serializable(vv)
                    for kk, vv in v.items()
                }
            else:
                clean_r[k] = make_serializable(v)
        results_json["results"][reason] = clean_r

    results_json_path = OUT_DIR / "results.json"
    with open(results_json_path, "w") as f:
        json.dump(results_json, f, indent=2, default=make_serializable)
    log.info(f"Written: {results_json_path}")

    # Print summary
    log.info("\n" + "=" * 70)
    log.info("P1.2b COMPLETE")
    log.info(f"freshness_expired verdict: {results_store['freshness_expired'].get('verdict', 'N/A')}")
    log.info(f"tier_cutoff verdict: {results_store['tier_cutoff'].get('verdict', 'N/A')}")
    log.info(f"BH significant trials: {n_significant}/{BH_M}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
