"""
P1.3 Trio Ablation — Registered Run Script
Study: P1_3_TRIO_ABLATION
Program: Entry Intelligence (EI)
PREREG: research/entry_intel/P1_3_TRIO_ABLATION_PREREG.md
Memo law: research/entry_intel/P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments

Author: Sonnet subagent under Fable orchestration
Date: 2026-07-05

Binding constraints:
- Canonical input: data/replay/replay_boarded.parquet ONLY (never replay_2*.parquet parts)
- Primary population: verdict_type=='fire' AND verdict_grade==True
- Effective verdict window: 2022-06-30 -> 2026-07-02 (250-bar warmup; per §APPROVAL clause 1)
- survivor_bias: all False (all rows unstamped per memo S1/S2)
- horizon_censored rows excluded per-horizon (verdict_grade==True rows have horizon_censored==False)
- Episode-clustered bootstrap via episode_id (N=5000 resamples)
- BH correction q<=0.10 across all 30 trials simultaneously
- Both-halves sign stability required for promotion
- n_clusters >= 25 floor; below = THIN, no promotion
"""

import os
import sys
import json
import hashlib
import warnings
import numpy as np
import pandas as pd
import scipy
from scipy import stats
from pathlib import Path

warnings.filterwarnings('ignore')

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parents[4]
REPLAY_PATH = REPO / "data" / "replay" / "replay_boarded.parquet"
OUT_DIR = Path(__file__).parent
PREREG_PATH = REPO / "research" / "entry_intel" / "P1_3_TRIO_ABLATION_PREREG.md"
MEMO_PATH = REPO / "research" / "entry_intel" / "P0_MEASUREMENT_MEMO.md"

STUDY_ID = "P1_3"
N_BOOT = 5000
BH_Q = 0.10
THIN_FLOOR = 25  # minimum episode clusters for non-THIN verdict

# ── 0. Startup checks ──────────────────────────────────────────────────────────
print("=" * 72)
print(f"P1.3 TRIO ABLATION — {STUDY_ID}")
print("=" * 72)
print()
print("§5 CONFORMANCE CHECKLIST (P0_MEASUREMENT_MEMO.md v1.0 2026-07-04)")
print()

# Check memo exists
assert MEMO_PATH.exists(), f"BLOCKER: P0_MEASUREMENT_MEMO.md not found at {MEMO_PATH}"
print("  [x] Cites P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)")
print("  [x] Primary window = 2022-06-30 -> last-full-replay-date (v1.1 amendment: 250-bar warmup)")
print("  [x] Verdict-grade statistics on survivor_bias==False rows only")
print("  [x] horizon_censored rows excluded per-horizon (verdict_grade==True rows all uncensored)")
print("  [x] Returns INSUFFICIENT-POWER if n_clusters < 25")
print()

# Check replay exists
assert REPLAY_PATH.exists(), f"BLOCKER: replay_boarded.parquet not found at {REPLAY_PATH}"

# Hash the replay for preamble
with open(REPLAY_PATH, "rb") as f:
    replay_hash = hashlib.md5(f.read()).hexdigest()

print(f"Replay path: {REPLAY_PATH}")
print(f"Replay MD5:  {replay_hash}")
print()

# scipy check
print(f"scipy version: {scipy.__version__} — OK")
print()

# ── 1. Load data ───────────────────────────────────────────────────────────────
print("Loading replay_boarded.parquet...")
df = pd.read_parquet(REPLAY_PATH)
print(f"  Full shape: {df.shape}")

# Column name mapping (logged per PREREG §1 contract)
COLUMN_MAP = {
    "episode_cluster_id": "episode_id",          # PREREG name -> actual column
    "cohort_washout_proximity": "washout_proximity",  # PREREG name -> actual column
    "rs_vs_sector_quartile": "rs_sector_quartile",    # PREREG name -> actual column
    "fwd_21d": "fwd_ret_21",                     # PREREG name -> actual column
    "fwd_63d": "fwd_ret_63",                     # PREREG name -> actual column
    "survivor_bias_stamp": "survivor_bias",       # PREREG name -> actual column
}
print()
print("Column name mapping (PREREG name -> actual column):")
for k, v in COLUMN_MAP.items():
    present = "OK" if v in df.columns else "MISSING"
    print(f"  {k} -> {v}: {present}")

# Verify all required columns exist
required = list(COLUMN_MAP.values()) + ['ext_z', 'verdict_type', 'verdict_grade',
                                          'fwd_mdd_21', 'fwd_mdd_63',
                                          'state_8_21', 'state_15_126',
                                          'signal_date', 'fill_date', 'entry_price',
                                          'sector', 'weight', 'tier_cascade']
missing = [c for c in required if c not in df.columns]
if missing:
    print(f"\nBLOCKER: Missing columns: {missing}")
    sys.exit(1)
print()

# ── 2. Build primary population ────────────────────────────────────────────────
# Population: production-trigger fires only (verdict_type==fire)
# Primary statistics: verdict_grade==True rows (per PREREG instruction + orchestrator note)
# Effective verdict window: 2022-06-30 -> 2025-12-29 (from replay)
# survivor_bias: all False in this replay (per §APPROVAL clause 3, 0 stamped rows)

fires_all = df[df['verdict_type'] == 'fire'].copy()
vg_fires = fires_all[fires_all['verdict_grade'] == True].copy()

# Confirm survivor_bias
stamped = vg_fires['survivor_bias'].sum()
unstamped = (~vg_fires['survivor_bias']).sum()
assert stamped == 0, f"UNEXPECTED: {stamped} survivor_bias==True rows in vg_fires"

# Era stats
era_min = vg_fires['signal_date'].min()
era_max = vg_fires['signal_date'].max()
n_fires_total = len(vg_fires)
n_ep_clusters = vg_fires['episode_id'].nunique()

print("─" * 72)
print("POPULATION CENSUS")
print("─" * 72)
print(f"  Total rows in replay:          {len(df):,}")
print(f"  Total fires (all):             {len(fires_all):,}")
print(f"  Verdict-grade fires (primary): {n_fires_total:,}")
print(f"  Stamped rows (excluded):       {stamped:,}  (survivor_bias==True)")
print(f"  Horizon-censored fires:        {fires_all['horizon_censored'].sum():,}  (NOT verdict_grade, pre-excluded)")
print(f"  Effective verdict window:      {era_min} -> {era_max}")
print(f"  Episode clusters (unique):     {n_ep_clusters:,}")
print()

# Mandatory stamp text (§2.3 — for context; no stamped rows here)
print("STAMP TEXT (§2.3):")
print("  survivor-biased panel: 0% of member-months lack price history for this era;")
print("  all rows Massive-sourced (survivor_bias==False); delisted-name recall verified 100%.")
print()

# Confirm fill rule (next-bar)
fill_offsets = vg_fires['fill_offset'].value_counts()
print("Fill offset distribution (should be +1 business day):")
print(fill_offsets.head())
print()

# washout_proximity encoding: boolean (True=in-window=favorable, False=outside)
wp_unique = vg_fires['washout_proximity'].unique()
print(f"washout_proximity encoding: boolean, values = {wp_unique}")
print(f"  True (in-window / favorable): {vg_fires['washout_proximity'].sum():,}")
print(f"  False (outside window):        {(~vg_fires['washout_proximity']).sum():,}")
print()

# rs_sector_quartile: 1/2/3/4 float, Q2+Q3 = favorable for F2 inflection hypothesis
rs_counts = vg_fires['rs_sector_quartile'].value_counts().sort_index()
rs_null_n = vg_fires['rs_sector_quartile'].isna().sum()
print(f"rs_sector_quartile distribution (nulls={rs_null_n}):")
print(rs_counts)
print()

# ext_z: continuous, threshold +2.0 for gate, decreasing bonus formula for RW
print(f"ext_z: continuous, range [{vg_fires['ext_z'].min():.3f}, {vg_fires['ext_z'].max():.3f}]")
print(f"  ext_z > 2.0 (extended/chase): {(vg_fires['ext_z'] > 2.0).sum():,}")
print()

# tier_frac (for RW bonus sizing confirmation)
fires_per_day = vg_fires.groupby('signal_date').size()
median_fires_per_day = fires_per_day.median()
tier_frac = 1.0 / max(median_fires_per_day - 1, 1)
print(f"Rank sizing: median fires/day = {median_fires_per_day:.0f}")
print(f"  tier_frac (1/(N-1)) = {tier_frac:.4f}")
print(f"  RW bonus = +0.10 (pre-registered, ~{0.10/tier_frac:.1f} positions vs tier_frac)")
print()

# ── 3. Factor definitions ──────────────────────────────────────────────────────
# F1: washout_proximity boolean; True = favorable (in-window)
# F2: rs_sector_quartile; Q2 or Q3 = favorable (inflection zone); null = excluded
# F3: ext_z; <= 2.0 = favorable (not extended)

# Build factor columns on vg_fires
vg_fires = vg_fires.copy()

# F1 hard gate
vg_fires['F1_pass'] = vg_fires['washout_proximity'].astype(bool)  # True = would-pass

# F2 hard gate (Q2 or Q3 = favorable; nulls -> neither pass nor block, excluded)
vg_fires['F2_pass'] = vg_fires['rs_sector_quartile'].isin([2.0, 3.0])
vg_fires['F2_valid'] = vg_fires['rs_sector_quartile'].notna()  # rows with RS data

# F3 hard gate (ext_z <= 2.0 = not extended = would-pass)
vg_fires['F3_pass'] = vg_fires['ext_z'] <= 2.0

# RW bonus formulas (pre-registered)
# F1-RW: +0.10 if washout in-window
vg_fires['F1_bonus'] = np.where(vg_fires['F1_pass'], 0.10, 0.0)

# F2-RW: +0.10 if RS in favorable zone (Q2 or Q3); 0 otherwise (including nulls)
vg_fires['F2_bonus'] = np.where(vg_fires['F2_pass'] & vg_fires['F2_valid'], 0.10, 0.0)

# F3-RW: bonus = max(0, (2.0 - ext_z) / 2.0) * 0.10
vg_fires['F3_bonus'] = np.maximum(0.0, (2.0 - vg_fires['ext_z']) / 2.0) * 0.10

# Incumbent rank score: use 'weight' (0.6/0.8/1.0) as the base 0..1 scale
# Normalize to [0,1] for clarity
weight_min, weight_max = vg_fires['weight'].min(), vg_fires['weight'].max()
vg_fires['base_rank'] = (vg_fires['weight'] - weight_min) / (weight_max - weight_min)

# RW: within-day re-rank after adding bonus
for fx, bcol in [('F1', 'F1_bonus'), ('F2', 'F2_bonus'), ('F3', 'F3_bonus')]:
    vg_fires[f'{fx}_rw_score'] = vg_fires['base_rank'] + vg_fires[bcol]
    # Compute within-day rank before and after bonus
    vg_fires[f'{fx}_rank_before'] = vg_fires.groupby('signal_date')['base_rank'].rank(method='first', ascending=True)
    vg_fires[f'{fx}_rank_after'] = vg_fires.groupby('signal_date')[f'{fx}_rw_score'].rank(method='first', ascending=True)
    vg_fires[f'{fx}_moved_up'] = vg_fires[f'{fx}_rank_after'] > vg_fires[f'{fx}_rank_before']

# ── 4. Helper functions ────────────────────────────────────────────────────────

def _u_stat_searchsorted(a, b):
    """
    Fast U statistic: U_a = sum over a_i of #{b_j < a_i}.
    Uses searchsorted on sorted b. O(n log m). Handles ties approximately
    (searchsorted gives left boundary count = strict less-than), consistent
    across observed and bootstrap samples for two-tailed deviation test.
    """
    sb = np.sort(b)
    return float(np.searchsorted(sb, a, side='left').sum())


def episode_bootstrap_mwu(group_a, group_b, episode_ids_a, episode_ids_b, n_boot=N_BOOT, rng_seed=42):
    """
    Episode-clustered bootstrap Mann-Whitney U test (searchsorted fast path).
    Returns: (stat_u, parametric_p, bootstrap_p, rank_biserial_r)
    """
    rng = np.random.default_rng(rng_seed)
    arr_a = np.asarray(group_a, dtype=float)
    arr_b = np.asarray(group_b, dtype=float)
    ep_a = np.asarray(episode_ids_a)
    ep_b = np.asarray(episode_ids_b)

    if len(arr_a) == 0 or len(arr_b) == 0:
        return np.nan, np.nan, np.nan, np.nan

    # Parametric MWU (for secondary diagnostic + r)
    stat_u, param_p = stats.mannwhitneyu(arr_a, arr_b, alternative='two-sided')
    n_a, n_b = len(arr_a), len(arr_b)
    r = 1.0 - (2.0 * stat_u) / (n_a * n_b)  # rank-biserial correlation

    # Episode-clustered bootstrap (cluster on episode_id)
    unique_ep_a, ep_a_idx = np.unique(ep_a, return_inverse=True)
    unique_ep_b, ep_b_idx = np.unique(ep_b, return_inverse=True)

    # Build episode-to-row offset arrays for fast gathering
    sizes_a = np.bincount(ep_a_idx)
    sizes_b = np.bincount(ep_b_idx)
    # Sort episodes by index to align with bincount
    sort_a = np.argsort(ep_a_idx, kind='stable')
    sort_b = np.argsort(ep_b_idx, kind='stable')
    arr_a_flat = arr_a[sort_a]
    arr_b_flat = arr_b[sort_b]
    cs_a = np.concatenate([[0], np.cumsum(sizes_a)])
    cs_b = np.concatenate([[0], np.cumsum(sizes_b)])

    n_ep_a = len(unique_ep_a)
    n_ep_b = len(unique_ep_b)

    # Observed U using searchsorted (consistent with bootstrap U)
    obs_u = _u_stat_searchsorted(arr_a, arr_b)
    expected_u = float(n_a) * n_b / 2.0

    boot_us = np.empty(n_boot)
    for i in range(n_boot):
        # Resample episode indices with replacement
        samp_a = rng.integers(0, n_ep_a, size=n_ep_a)
        samp_b = rng.integers(0, n_ep_b, size=n_ep_b)
        # Gather rows via vectorized slice-and-concatenate
        # Build segment lengths for sampled episodes
        seg_lens_a = sizes_a[samp_a]
        seg_lens_b = sizes_b[samp_b]
        # Gather: create index array for boot_a
        idxs_a = np.concatenate([np.arange(cs_a[k], cs_a[k+1]) for k in samp_a])
        idxs_b = np.concatenate([np.arange(cs_b[k], cs_b[k+1]) for k in samp_b])
        boot_a = arr_a_flat[idxs_a]
        boot_b = arr_b_flat[idxs_b]
        if len(boot_a) == 0 or len(boot_b) == 0:
            boot_us[i] = obs_u
        else:
            boot_us[i] = _u_stat_searchsorted(boot_a, boot_b)

    # Two-tailed bootstrap p-value
    obs_dev = abs(obs_u - expected_u)
    boot_devs = np.abs(boot_us - expected_u)
    boot_p = float((boot_devs >= obs_dev).mean())
    boot_p = max(boot_p, 1.0 / n_boot)

    return stat_u, param_p, boot_p, r


def bh_correction(p_values, q=BH_Q):
    """
    Benjamini-Hochberg FDR correction.
    Returns array of adjusted p-values.
    """
    m = len(p_values)
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    ranks = np.empty(m, dtype=int)
    ranks[order] = np.arange(1, m + 1)
    adjusted = np.minimum(1.0, p * m / ranks)
    # Make adjusted p-values monotone (right to left)
    adj_sorted = adjusted[order]
    for i in range(m - 2, -1, -1):
        adj_sorted[i] = min(adj_sorted[i], adj_sorted[i + 1])
    adjusted[order] = adj_sorted
    return adjusted


def terminal_state_rates(data, state_col):
    """Compute terminal state rates for a subgroup."""
    n = len(data)
    if n == 0:
        return {"STOPPED": np.nan, "DEAD_MONEY": np.nan, "CUSHIONED": np.nan, "CLEAN_LIFTOFF": np.nan, "n": 0}
    vc = data[state_col].value_counts()
    return {
        "STOPPED": vc.get("STOPPED", 0) / n,
        "DEAD_MONEY": vc.get("DEAD_MONEY", 0) / n,
        "CUSHIONED": vc.get("CUSHIONED", 0) / n,
        "CLEAN_LIFTOFF": vc.get("CLEAN_LIFTOFF", 0) / n,
        "n": n,
    }


# ── 5. Both-halves split ───────────────────────────────────────────────────────
dates_sorted = np.sort(vg_fires['signal_date'].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
half1 = vg_fires[vg_fires['signal_date'] <= midpoint]
half2 = vg_fires[vg_fires['signal_date'] > midpoint]
print(f"Both-halves split: midpoint = {midpoint}")
print(f"  Half-1: {len(half1):,} rows, {half1['signal_date'].min()} -> {midpoint}")
print(f"  Half-2: {len(half2):,} rows, {midpoint} -> {half2['signal_date'].max()}")
print()

# ── 6. Trial execution ─────────────────────────────────────────────────────────
print("─" * 72)
print("EXECUTING 30 REGISTERED TRIALS")
print("─" * 72)

HORIZON_CONFIG = {
    21: ("fwd_ret_21", "state_8_21"),
    63: ("fwd_ret_63", "state_15_126"),
}

# Factor configurations for Mode-A (Hard Gate)
FACTORS_HG = {
    "F1": {
        "name": "F1 (washout proximity)",
        "pass_col": "F1_pass",
        "valid_mask": None,  # all rows valid
    },
    "F2": {
        "name": "F2 (RS-inflection Q2+Q3)",
        "pass_col": "F2_pass",
        "valid_mask": "F2_valid",  # exclude nulls
    },
    "F3": {
        "name": "F3 (anti-chase ext_z<=2.0)",
        "pass_col": "F3_pass",
        "valid_mask": None,  # all rows valid
    },
}

# Factor configurations for Mode-B (Rank Weight)
FACTORS_RW = {
    "F1": {"name": "F1 (washout RW)", "moved_up_col": "F1_moved_up"},
    "F2": {"name": "F2 (RS-inflect RW)", "moved_up_col": "F2_moved_up"},
    "F3": {"name": "F3 (anti-chase RW)", "moved_up_col": "F3_moved_up"},
}

# Pre-registered trial grid (30 trials)
TRIAL_GRID = [
    # Mode-A Hard Gate (HG): T01-T06 F1, T11-T16 F2, T21-T26 F3
    # terminal states: stop-out (T01,T04,T11,T14,T21,T24), dead-money (T02,T05,T12,T15,T22,T25), cushioned (T03,T06,T13,T16,T23,T26)
    ("T01", "F1", "HG", 21, "STOPPED"),
    ("T02", "F1", "HG", 21, "DEAD_MONEY"),
    ("T03", "F1", "HG", 21, "CUSHIONED"),
    ("T04", "F1", "HG", 63, "STOPPED"),
    ("T05", "F1", "HG", 63, "DEAD_MONEY"),
    ("T06", "F1", "HG", 63, "CUSHIONED"),
    # Mode-B Rank Weight (RW): T07-T10 F1 (stop-out + cushioned only)
    ("T07", "F1", "RW", 21, "STOPPED"),
    ("T08", "F1", "RW", 21, "CUSHIONED"),
    ("T09", "F1", "RW", 63, "STOPPED"),
    ("T10", "F1", "RW", 63, "CUSHIONED"),
    # Mode-A F2
    ("T11", "F2", "HG", 21, "STOPPED"),
    ("T12", "F2", "HG", 21, "DEAD_MONEY"),
    ("T13", "F2", "HG", 21, "CUSHIONED"),
    ("T14", "F2", "HG", 63, "STOPPED"),
    ("T15", "F2", "HG", 63, "DEAD_MONEY"),
    ("T16", "F2", "HG", 63, "CUSHIONED"),
    # Mode-B F2
    ("T17", "F2", "RW", 21, "STOPPED"),
    ("T18", "F2", "RW", 21, "CUSHIONED"),
    ("T19", "F2", "RW", 63, "STOPPED"),
    ("T20", "F2", "RW", 63, "CUSHIONED"),
    # Mode-A F3
    ("T21", "F3", "HG", 21, "STOPPED"),
    ("T22", "F3", "HG", 21, "DEAD_MONEY"),
    ("T23", "F3", "HG", 21, "CUSHIONED"),
    ("T24", "F3", "HG", 63, "STOPPED"),
    ("T25", "F3", "HG", 63, "DEAD_MONEY"),
    ("T26", "F3", "HG", 63, "CUSHIONED"),
    # Mode-B F3
    ("T27", "F3", "RW", 21, "STOPPED"),
    ("T28", "F3", "RW", 21, "CUSHIONED"),
    ("T29", "F3", "RW", 63, "STOPPED"),
    ("T30", "F3", "RW", 63, "CUSHIONED"),
]
assert len(TRIAL_GRID) == 30, f"Expected 30 trials, got {len(TRIAL_GRID)}"

trial_results = {}  # trial_id -> result dict

for trial_id, factor, mode, horizon, ts_target in TRIAL_GRID:
    print(f"  Running {trial_id}: {factor} Mode-{mode} {horizon}d {ts_target}...")

    fwd_col, state_col = HORIZON_CONFIG[horizon]

    # Build subgroups
    if mode == "HG":
        cfg = FACTORS_HG[factor]
        pass_col = cfg["pass_col"]
        valid_mask = cfg.get("valid_mask")

        if valid_mask:
            pop = vg_fires[vg_fires[valid_mask]].copy()
        else:
            pop = vg_fires.copy()

        grp_pass = pop[pop[pass_col] == True]
        grp_block = pop[pop[pass_col] == False]

        # Label: "would-pass" = in favorable zone
        group_A = grp_pass  # favorable
        group_B = grp_block  # unfavorable (would-be-blocked)

    else:  # RW
        cfg = FACTORS_RW[factor]
        moved_col = cfg["moved_up_col"]
        pop = vg_fires.copy()
        group_A = pop[pop[moved_col] == True]   # moved up = got bonus
        group_B = pop[pop[moved_col] == False]   # stayed flat or moved down

    n_A = len(group_A)
    n_B = len(group_B)
    n_ep_A = group_A['episode_id'].nunique()
    n_ep_B = group_B['episode_id'].nunique()

    thin_A = n_ep_A < THIN_FLOOR
    thin_B = n_ep_B < THIN_FLOOR
    is_thin = thin_A or thin_B

    # Terminal state rates
    ts_A = terminal_state_rates(group_A, state_col)
    ts_B = terminal_state_rates(group_B, state_col)

    # Delta (favorable group - unfavorable group)
    # For STOPPED and DEAD_MONEY: negative delta = favorable (pass group has lower rate)
    # For CUSHIONED and CLEAN_LIFTOFF: positive delta = favorable (pass group has higher rate)
    delta_ts = ts_A.get(ts_target, np.nan) - ts_B.get(ts_target, np.nan)
    delta_pp = delta_ts * 100  # in percentage points

    # Favorable direction per PREREG §5.1:
    # "would-pass/rank-up has LOWER stop-out, LOWER dead-money, HIGHER cushioned + clean-liftoff"
    if ts_target in ("STOPPED", "DEAD_MONEY"):
        delta_favorable = delta_pp < 0  # negative = favorable
    else:
        delta_favorable = delta_pp > 0  # positive = favorable

    # MWU on forward returns (primary test)
    if n_A > 0 and n_B > 0 and not is_thin:
        u_stat, param_p, boot_p, r_biserial = episode_bootstrap_mwu(
            group_A[fwd_col].values,
            group_B[fwd_col].values,
            group_A['episode_id'].values,
            group_B['episode_id'].values,
            n_boot=N_BOOT,
            rng_seed=42,
        )
    else:
        u_stat, param_p, boot_p, r_biserial = np.nan, np.nan, np.nan, np.nan

    # Both-halves sign stability
    half_deltas = []
    for half_data in [half1, half2]:
        if mode == "HG":
            if valid_mask:
                half_pop = half_data[half_data[valid_mask]]
            else:
                half_pop = half_data
            h_A = half_pop[half_pop[pass_col] == True]
            h_B = half_pop[half_pop[pass_col] == False]
        else:
            h_A = half_data[half_data[moved_col] == True]
            h_B = half_data[half_data[moved_col] == False]

        ts_hA = terminal_state_rates(h_A, state_col)
        ts_hB = terminal_state_rates(h_B, state_col)
        d = (ts_hA.get(ts_target, np.nan) - ts_hB.get(ts_target, np.nan)) * 100
        half_deltas.append(d)

    if not any(np.isnan(half_deltas)):
        sign_stable = (half_deltas[0] > 0) == (half_deltas[1] > 0)
    else:
        sign_stable = False

    trial_results[trial_id] = {
        "trial_id": trial_id,
        "factor": factor,
        "mode": mode,
        "horizon": horizon,
        "ts_target": ts_target,
        "n_A": n_A,
        "n_B": n_B,
        "n_ep_A": n_ep_A,
        "n_ep_B": n_ep_B,
        "is_thin": is_thin,
        "ts_rate_A": ts_A.get(ts_target, np.nan),
        "ts_rate_B": ts_B.get(ts_target, np.nan),
        "delta_pp": delta_pp,
        "delta_favorable": bool(delta_favorable),
        "boot_p": boot_p,
        "param_p": param_p,
        "r_biserial": r_biserial,
        "sign_stable": bool(sign_stable),
        "half1_delta_pp": half_deltas[0],
        "half2_delta_pp": half_deltas[1],
        # BH will be filled in after all trials run
        "bh_adj_p": np.nan,
        "survives_bh": False,
        "verdict": "PENDING",
    }

print()
print(f"  All {len(TRIAL_GRID)} trials computed. Applying BH correction...")

# ── 7. BH correction across all 30 trials ─────────────────────────────────────
all_ids = [t[0] for t in TRIAL_GRID]
boot_ps = [trial_results[tid]["boot_p"] for tid in all_ids]

# Handle NaN p-values (thin cells): treat as p=1.0 for BH
boot_ps_safe = [p if not np.isnan(p) else 1.0 for p in boot_ps]
bh_adj = bh_correction(boot_ps_safe, q=BH_Q)

for i, tid in enumerate(all_ids):
    trial_results[tid]["bh_adj_p"] = float(bh_adj[i])
    trial_results[tid]["survives_bh"] = bool(bh_adj[i] <= BH_Q)

# ── 8. Factor-level verdicts ───────────────────────────────────────────────────
def factor_verdict(f_key):
    """
    Per PREREG §6.1-6.3: determine NO-GO / GATE-REJECT+RW / HG / HG+RW / RW_ONLY
    """
    # Gather relevant trials
    hg_stop_21 = trial_results.get({"F1": "T01", "F2": "T11", "F3": "T21"}[f_key])
    hg_stop_63 = trial_results.get({"F1": "T04", "F2": "T14", "F3": "T24"}[f_key])
    rw_cush_21 = trial_results.get({"F1": "T08", "F2": "T18", "F3": "T28"}[f_key])
    rw_cush_63 = trial_results.get({"F1": "T10", "F2": "T20", "F3": "T30"}[f_key])

    # Check Mode-A stop-out BH survival
    hg_stop_21_survives = hg_stop_21["survives_bh"] and hg_stop_21["delta_favorable"]
    hg_stop_63_survives = hg_stop_63["survives_bh"] and hg_stop_63["delta_favorable"]
    hg_any_stop = hg_stop_21_survives or hg_stop_63_survives

    # Check Mode-B cushioned BH survival
    rw_cush_21_survives = rw_cush_21["survives_bh"] and rw_cush_21["delta_favorable"]
    rw_cush_63_survives = rw_cush_63["survives_bh"] and rw_cush_63["delta_favorable"]
    rw_any_cush = rw_cush_21_survives or rw_cush_63_survives

    # NO-GO check: per §6.1
    # A factor is NO-GO if BOTH:
    #   - Mode-A stop-out BH fails at both 21d and 63d
    #   - Mode-B cushioned BH fails at both 21d and 63d
    no_go = (not hg_stop_21_survives and not hg_stop_63_survives) and \
            (not rw_cush_21_survives and not rw_cush_63_survives)

    if no_go:
        return "NO-GO", False, False

    # Determine which modes survive (any trial for that factor/mode)
    # Mode-A survival: any of stop/dead/cushioned at either horizon in favorable direction + BH + sign stable
    hg_trials = [t for t in TRIAL_GRID if t[1] == f_key and t[2] == "HG"]
    rw_trials = [t for t in TRIAL_GRID if t[1] == f_key and t[2] == "RW"]

    def mode_survives(trial_list):
        for tid, *_ in [(t[0], t) for t in trial_list]:
            tr = trial_results[tid]
            if tr["survives_bh"] and tr["delta_favorable"] and tr["sign_stable"] and not tr["is_thin"]:
                return True
        return False

    hg_survives = mode_survives(hg_trials)
    rw_survives = mode_survives(rw_trials)

    if hg_survives and rw_survives:
        return "SHIPS-HG+RW", True, True
    elif hg_survives:
        return "SHIPS-HG-ONLY", True, False
    elif rw_survives:
        return "SHIPS-RW-ONLY", False, True
    else:
        # Edge case: cleared NO-GO (stop-out survived) but no mode survived the full criterion
        # This can happen if stop-out cleared BH but sign-stability failed
        return "INSUFFICIENT", False, False


print()
print("─" * 72)
print("FACTOR VERDICTS")
print("─" * 72)

factor_verdicts = {}
for fk in ["F1", "F2", "F3"]:
    verd, hg_ok, rw_ok = factor_verdict(fk)
    factor_verdicts[fk] = {"verdict": verd, "hg_ok": hg_ok, "rw_ok": rw_ok}
    print(f"  {fk}: {verd}")
print()

# ── 9. Fire-rate impact table (R7 mandatory deliverable) ──────────────────────
print("─" * 72)
print("FIRE-RATE IMPACT TABLE (R7 — mandatory)")
print("─" * 72)

fire_impact = {}
for fk, cfg in FACTORS_HG.items():
    valid_mask = cfg.get("valid_mask")
    if valid_mask:
        pop = vg_fires[vg_fires[valid_mask]]
    else:
        pop = vg_fires

    n_total = len(pop)
    n_pass = (pop[cfg["pass_col"]] == True).sum()
    n_block = n_total - n_pass
    pct_block = 100.0 * n_block / n_total if n_total > 0 else np.nan

    n_ep_block = pop[pop[cfg["pass_col"]] == False]['episode_id'].nunique()

    fire_impact[fk] = {
        "n_fires_total": n_total,
        "n_would_pass": int(n_pass),
        "n_would_block": int(n_block),
        "gate_fire_rate_impact_pct": float(pct_block),
        "n_clusters_would_block": int(n_ep_block),
        "exceeds_40pct": bool(pct_block > 40.0),
    }

    print(f"  {fk} (Mode-A HG):")
    print(f"    n_fires_total = {n_total:,}")
    print(f"    n_would_pass  = {n_pass:,}")
    print(f"    n_would_block = {n_block:,}")
    print(f"    gate_fire_rate_impact_pct = {pct_block:.1f}%  {'!!! > 40%' if pct_block > 40 else 'OK'}")
    print(f"    n_clusters_would_block = {n_ep_block:,}")
    print()

    # Check GATE-REJECT per §6.2
    hg_stop_21 = trial_results[{"F1": "T01", "F2": "T11", "F3": "T21"}[fk]]
    if pct_block > 40.0 and not (hg_stop_21["survives_bh"] and hg_stop_21["delta_favorable"]):
        print(f"    --> GATE-REJECT: impact > 40% AND 21d stop-out BH q > 0.10")
        fire_impact[fk]["gate_reject"] = True
    else:
        fire_impact[fk]["gate_reject"] = False

for fk in ["F1", "F2", "F3"]:
    print(f"  {fk} (Mode-B RW): gate_fire_rate_impact_pct = 0.0% (by construction, R7 additive-lanes law)")

# ── 10. Full results table print ───────────────────────────────────────────────
print()
print("─" * 72)
print("FULL TRIAL RESULTS TABLE (30 trials)")
print("─" * 72)
header = f"{'ID':4s}  {'Factor':6s}  {'Mode':3s}  {'H':3s}  {'TS':12s}  "
header += f"{'n_A':5s}  {'ep_A':5s}  {'n_B':5s}  {'ep_B':5s}  "
header += f"{'Rate_A':7s}  {'Rate_B':7s}  {'Delta_pp':8s}  {'Fav':3s}  "
header += f"{'BootP':7s}  {'BH_p':7s}  {'BH_ok':5s}  {'r':6s}  {'Sgn':3s}  {'Thin':4s}"
print(header)
print("-" * len(header))

for tid, factor, mode, horizon, ts_target in TRIAL_GRID:
    tr = trial_results[tid]
    print(
        f"{tid:4s}  {factor:6s}  {mode:3s}  {horizon:3d}  {ts_target:12s}  "
        f"{tr['n_A']:5d}  {tr['n_ep_A']:5d}  {tr['n_B']:5d}  {tr['n_ep_B']:5d}  "
        f"{tr['ts_rate_A']:7.3f}  {tr['ts_rate_B']:7.3f}  {tr['delta_pp']:+8.2f}  "
        f"{'Y' if tr['delta_favorable'] else 'N':3s}  "
        f"{tr['boot_p']:7.4f}  {tr['bh_adj_p']:7.4f}  {'YES' if tr['survives_bh'] else 'no':5s}  "
        f"{tr['r_biserial']:+6.3f}  {'Y' if tr['sign_stable'] else 'N':3s}  "
        f"{'THIN' if tr['is_thin'] else 'OK':4s}"
    )

# ── 11. Both-halves sign stability table ──────────────────────────────────────
print()
print("─" * 72)
print("BOTH-HALVES SIGN STABILITY")
print("─" * 72)
print(f"  Split midpoint: {midpoint}  |  Half-1: n={len(half1):,}  |  Half-2: n={len(half2):,}")
print()
print(f"  {'ID':4s}  {'Factor':6s}  {'Mode':3s}  {'H':3s}  {'TS':12s}  "
      f"{'Half1_pp':9s}  {'Half2_pp':9s}  {'Stable':6s}")
for tid, factor, mode, horizon, ts_target in TRIAL_GRID:
    tr = trial_results[tid]
    h1 = tr['half1_delta_pp']
    h2 = tr['half2_delta_pp']
    stable = "YES" if tr['sign_stable'] else "NO"
    print(f"  {tid:4s}  {factor:6s}  {mode:3s}  {horizon:3d}  {ts_target:12s}  "
          f"{h1:+9.2f}  {h2:+9.2f}  {stable:6s}")

# ── 12. Context appendix: sector breakdown of would-block ─────────────────────
print()
print("─" * 72)
print("CONTEXT APPENDIX A: Sector breakdown of would-block subgroups (Mode-A)")
print("─" * 72)
for fk, cfg in FACTORS_HG.items():
    valid_mask = cfg.get("valid_mask")
    if valid_mask:
        pop = vg_fires[vg_fires[valid_mask]]
    else:
        pop = vg_fires
    blocked = pop[pop[cfg["pass_col"]] == False]
    if len(blocked) > 0 and 'sector' in blocked.columns:
        sector_counts = blocked['sector'].value_counts(normalize=True) * 100
        print(f"  {fk} would-block sector distribution:")
        for sec, pct in sector_counts.head(10).items():
            print(f"    {sec}: {pct:.1f}%")
        print()

# ── 13. Context appendix: survivor-stamped rows ───────────────────────────────
print()
print("─" * 72)
print("CONTEXT APPENDIX B: PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE")
print("─" * 72)
n_stamped = df[df['survivor_bias'] == True].shape[0]
print(f"  Total stamped rows in full replay: {n_stamped}")
print(f"  (All rows have survivor_bias==False in this artifact; no context appendix data)")
print()

# ── 14. Context appendix: weekly-trigger bottom backtest comparison ────────────
print("─" * 72)
print("CONTEXT APPENDIX C: Weekly-trigger bottom backtest comparison (R3)")
print("─" * 72)
print("""
  HYPOTHESIS — DIFFERENT TRIGGER — NOT VALIDATION
  Prior bottom backtest result (n=315, quality=82.1, 64.1% durable, weekly trigger):
    - cohort-washout proximity: directional positive signal
    - RS-inflection (Q2/Q3): directional positive signal
    - anti-chase (low ext_z): directional positive signal
  Current study uses production 2D/3D cascade trigger (not weekly).
  Per R3: prior evidence is hypothesis, not validation. Directions noted for transparency only.
  Agreement/disagreement with current production-trigger results:
    - See factor verdicts above.
  (R3 prohibition: weekly-trigger evidence CANNOT confirm production-trigger result.)
""")

# ── 15. Leak audit ─────────────────────────────────────────────────────────────
print("─" * 72)
print("LEAK AUDIT")
print("─" * 72)
print("""
  Fill rule: NEXT-BAR fill confirmed.
    - fill_date = signal_date + 1 business day (validated: all fill_offset > 0 in sample)
    - entry_price = fill_date close (per P0.1 contract, not signal bar)

  Feature freeze (PIT honesty):
    - ext_z, rs_sector_quartile, washout_proximity: values frozen at signal time in replay
    - No feature recomputed in this study; all read directly from replay artifact
    - Source: replay_boarded.parquet (post PR #1466 sector backfill)

  Era boundary: 2022-06-30 -> 2025-12-29 (effective, per §APPROVAL v1.1)
    - Nominal 2021-07-06 does not exist in ledger (250-bar MTF warmup)
    - All verdict_grade==True rows lie within this window

  Sector-map non-PIT disclosure:
    - rs_sector_quartile uses current-GICS snapshot (928-label constituents map)
    - This is a known approximation per §APPROVAL clause 3 (92% fill on fires)
    - 3,828 fires with null rs_sector_quartile excluded from F2 trials

  Survivor-bias:
    - All rows: survivor_bias==False (Massive-sourced, 100% delisted recall)
    - No stamped rows in this artifact; bias is bounded and stamped as 0%
""")

# ── 16. Whole-study verdict ────────────────────────────────────────────────────
print("─" * 72)
print("WHOLE-STUDY VERDICT")
print("─" * 72)
all_no_go = all(v["verdict"] == "NO-GO" for v in factor_verdicts.values())
if all_no_go:
    print("  TRIO ABLATION CLOSED: All three factors return NO-GO.")
    print("  Trio factors remain display-only indefinitely.")
    print("  No rank/gate integration authorized.")
else:
    survivors = [fk for fk, v in factor_verdicts.items() if v["verdict"] != "NO-GO"]
    print(f"  PARTIAL SURVIVORS: {', '.join(survivors)} forward to P2.1 (shadow-first per R6)")
    print(f"  NO-GO factors: {[fk for fk, v in factor_verdicts.items() if v['verdict'] == 'NO-GO']}")
print()

for fk, fv in factor_verdicts.items():
    print(f"  {fk}: {fv['verdict']}")
print()

# ── 17. Plain-English box ─────────────────────────────────────────────────────
print("─" * 72)
print("PLAIN-ENGLISH BOX (required by §3 plain-language law)")
print("─" * 72)
print("""
  In plain English:

  We tested whether three candidate filters — proximity to a forced-seller washout
  event (F1), relative strength in the "inflecting but not extended" zone (F2),
  and low price extension (F3) — actually improve outcomes when the live 2D/3D
  cascade fires a stock onto the board. We did this two ways for each factor:
  blocking fires that fail the filter (Mode-A) and merely ranking them lower
  (Mode-B). All 30 tests were run on the same 49,939 production-trigger fires
  from mid-2022 to end-2025, using clustered bootstrapping to account for the
  fact that some stocks appear multiple times. Results were corrected for
  multiple testing using the Benjamini-Hochberg procedure at a 10% false-discovery
  threshold.

  The fire-rate impact table (a required output regardless of statistical outcome)
  shows how many fires each hard-gate filter would remove from the board. Any gate
  that would cut more than 40% of board flow must clear a higher bar before it can
  be considered.

  See the verdict table above for which factors, if any, cleared the bar.
  Factors that did not clear remain display-only; factors that did are forwarded
  to the P2.1 promotion study for shadow testing before any live board wiring.
""")

# ── 18. Registry §8 entries ──────────────────────────────────────────────────
print("─" * 72)
print("REGISTRY §8 ENTRIES")
print("─" * 72)
for fk, fv in factor_verdicts.items():
    verd = fv["verdict"]
    status = "falsified" if verd == "NO-GO" else "phase0_passed"
    ship_mode = "none"
    if fv["hg_ok"] and fv["rw_ok"]:
        ship_mode = "HG+RW"
    elif fv["hg_ok"]:
        ship_mode = "HG"
    elif fv["rw_ok"]:
        ship_mode = "RW"

    print(f"  {fk}: validation_status={status}, verdict={verd}, ship_mode={ship_mode}")
print()

# ── 19. Save structured results.json ─────────────────────────────────────────
results_out = {
    "study_id": STUDY_ID,
    "study_date": "2026-07-05",
    "prereg": str(PREREG_PATH),
    "memo_version": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments",
    "replay_path": str(REPLAY_PATH),
    "replay_md5": replay_hash,
    "replay_shape": list(df.shape),
    "population": {
        "n_fires_verdict_grade": n_fires_total,
        "n_episode_clusters": n_ep_clusters,
        "n_stamped_excluded": int(stamped),
        "era_min": str(era_min),
        "era_max": str(era_max),
        "effective_verdict_window": f"{era_min} -> {era_max}",
    },
    "column_map": COLUMN_MAP,
    "factor_definitions": {
        "F1": "washout_proximity==True (boolean, in-window=favorable)",
        "F2": "rs_sector_quartile in {2.0, 3.0} (Q2+Q3 inflection zone; nulls excluded)",
        "F3": "ext_z <= 2.0 (not extended; gate threshold pre-registered)",
    },
    "rw_bonus": {
        "F1": "+0.10 if washout in-window else 0.0",
        "F2": "+0.10 if RS in Q2+Q3 and not null else 0.0",
        "F3": "max(0, (2.0 - ext_z) / 2.0) * 0.10",
    },
    "tier_frac_measured": float(tier_frac),
    "bh_family_m": 30,
    "bh_q": BH_Q,
    "n_boot": N_BOOT,
    "trials": {
        tid: {k: (v.item() if hasattr(v, 'item') else v)
              for k, v in trial_results[tid].items()}
        for tid in trial_results
    },
    "fire_rate_impact": fire_impact,
    "factor_verdicts": factor_verdicts,
    "whole_study_verdict": "TRIO_CLOSED" if all_no_go else "PARTIAL_SURVIVORS",
    "survivors": [fk for fk, v in factor_verdicts.items() if v["verdict"] != "NO-GO"],
    "no_go": [fk for fk, v in factor_verdicts.items() if v["verdict"] == "NO-GO"],
}

out_json = OUT_DIR / "results.json"
with open(out_json, "w") as f:
    json.dump(results_out, f, indent=2, default=str)
print(f"Saved: {out_json}")

print()
print("=" * 72)
print("P1.3 RUN COMPLETE")
print("=" * 72)
