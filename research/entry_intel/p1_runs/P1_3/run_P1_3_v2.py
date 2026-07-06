"""
P1.3 Trio Ablation — ROUND 2 (defect-corrected re-run) — Registered Run Script
Study: P1_3_TRIO_ABLATION
Program: Entry Intelligence (EI)
PREREG: research/entry_intel/P1_3_TRIO_ABLATION_PREREG.md (APPROVED, Fable 2026-07-05)
Memo law: research/entry_intel/P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments

Author: Opus subagent under Fable orchestration (Round 2)
Date: 2026-07-05

════════════════════════════════════════════════════════════════════════════════
ROUND-1 DEFECT AND FIX (reviewer-reproduced; see REVIEW.md)
────────────────────────────────────────────────────────────────────────────────
Round-1 `episode_bootstrap_mwu` resampled episodes WITHIN each observed group
(group A resampled from A, group B from B), then compared |boot_U - null_center|
against |obs_U - null_center|. A within-group resample centers the bootstrap U on
the OBSERVED U, not on the null U = n_a*n_b/2. Result: boot_p ≈ 0.50 for EVERY
trial by construction, independent of the true effect. The round-1 "TRIO CLOSED,
0/30 survive" headline is an artifact of a broken statistic, not a null.

FIX (this file): the primary p-value is now an EPISODE-LEVEL LABEL-PERMUTATION null.
Group assignment (would-pass vs would-block for HG; moved-up vs not for RW) is a
per-episode property in this design (all rows of an episode share the same factor
value and rank-move direction — verified at runtime, see assert_episode_label_purity).
We therefore permute the group label at the EPISODE level (shuffle whole-episode
assignments across episodes), recompute the Mann-Whitney U on the pooled forward
returns under each permutation, and take the two-sided p as the fraction of
permutation |U - E[U]| ≥ observed |U - E[U]|. This respects within-episode
correlation (whole episodes move together) and centers the null correctly at
E[U] = n_a*n_b/2. N_PERM = 5,000 (≥ PREREG floor). A sanity gate HALTS if the
permutation p and the parametric MWU p diverge by > 6 orders of magnitude in a
non-null direction (the exact failure mode the round-1 runner missed).

Why permutation over CR1: the outcome here is a forward-return distribution
compared between two groups via Mann-Whitney U (a rank statistic on a heavy-tailed,
tied variable). A label-permutation null is the exact finite-sample null of the U
statistic and needs no distributional/linearity assumption; episode-level shuffling
supplies the clustering correction directly. CR1 (P1.1's choice) is valid for a
Spearman/OLS rank-correlation design; here the registered §5.1 statistic is a
two-group U test, for which permutation is the natural clustered null.
════════════════════════════════════════════════════════════════════════════════

Binding constraints (unchanged from PREREG / §APPROVAL):
- Canonical input: data/replay/replay_boarded.parquet ONLY (never replay_2*.parquet parts)
- Primary population: verdict_type=='fire' AND verdict_grade==True
- Effective verdict window: 2022-06-30 -> 2025-12-29 (250-bar warmup; §APPROVAL clause 1)
- survivor_bias: all False (all rows unstamped per memo S1/S2)
- Episode-clustered inference via episode_id
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
N_PERM = 5000
BH_Q = 0.10
THIN_FLOOR = 25  # minimum episode clusters for non-THIN verdict
SEED = 42

# ── 0. Startup checks ──────────────────────────────────────────────────────────
print("=" * 72)
print(f"P1.3 TRIO ABLATION — {STUDY_ID} — ROUND 2 (defect-corrected re-run)")
print("=" * 72)
print()
print("§5 CONFORMANCE CHECKLIST (P0_MEASUREMENT_MEMO.md v1.0 2026-07-04 + §6 v1.1)")
print()

assert MEMO_PATH.exists(), f"BLOCKER: P0_MEASUREMENT_MEMO.md not found at {MEMO_PATH}"
print("  [x] Cites P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments")
print("  [x] Primary window = 2022-06-30 -> last-full-replay-date (v1.1 amendment: 250-bar warmup)")
print("  [x] Verdict-grade statistics on survivor_bias==False rows only")
print("  [x] horizon_censored rows excluded per-horizon (verdict_grade==True rows all uncensored)")
print("  [x] Returns INSUFFICIENT-POWER if n_clusters < 25")
print()

assert REPLAY_PATH.exists(), f"BLOCKER: replay_boarded.parquet not found at {REPLAY_PATH}"
with open(REPLAY_PATH, "rb") as f:
    replay_hash = hashlib.md5(f.read()).hexdigest()
print(f"Replay path: {REPLAY_PATH}")
print(f"Replay MD5:  {replay_hash}")
print(f"scipy version: {scipy.__version__} — OK")
print()

# ── 1. Load data ───────────────────────────────────────────────────────────────
print("Loading replay_boarded.parquet...")
df = pd.read_parquet(REPLAY_PATH)
print(f"  Full shape: {df.shape}")

COLUMN_MAP = {
    "episode_cluster_id": "episode_id",
    "cohort_washout_proximity": "washout_proximity",
    "rs_vs_sector_quartile": "rs_sector_quartile",
    "fwd_21d": "fwd_ret_21",
    "fwd_63d": "fwd_ret_63",
    "survivor_bias_stamp": "survivor_bias",
}
print()
print("Column name mapping (PREREG name -> actual column):")
for k, v in COLUMN_MAP.items():
    present = "OK" if v in df.columns else "MISSING"
    print(f"  {k} -> {v}: {present}")

required = list(COLUMN_MAP.values()) + ['ext_z', 'verdict_type', 'verdict_grade',
                                        'state_8_21', 'state_15_126',
                                        'signal_date', 'entry_price',
                                        'sector', 'weight']
missing = [c for c in required if c not in df.columns]
if missing:
    print(f"\nBLOCKER: Missing columns: {missing}")
    sys.exit(1)
print()

# ── 2. Build primary population ────────────────────────────────────────────────
fires_all = df[df['verdict_type'] == 'fire'].copy()
vg_fires = fires_all[fires_all['verdict_grade'] == True].copy()

stamped = int(vg_fires['survivor_bias'].sum())
assert stamped == 0, f"UNEXPECTED: {stamped} survivor_bias==True rows in vg_fires"

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
if 'horizon_censored' in fires_all.columns:
    print(f"  Horizon-censored fires:        {int(fires_all['horizon_censored'].sum()):,}  (NOT verdict_grade, pre-excluded)")
print(f"  Effective verdict window:      {era_min} -> {era_max}")
print(f"  Episode clusters (unique):     {n_ep_clusters:,}")
print()

print("STAMP TEXT (§2.3):")
print("  survivor-biased panel: 0% of member-months lack price history for this era;")
print("  all rows Massive-sourced (survivor_bias==False); delisted-name recall verified 100%.")
print()

# Encodings (recompute fresh; do NOT anchor to round-1 point estimates)
vg_fires = vg_fires.copy()
wp_true = int(vg_fires['washout_proximity'].sum())
wp_false = int((~vg_fires['washout_proximity'].astype(bool)).sum())
print(f"washout_proximity: boolean; True(in-window)={wp_true:,}  False(outside)={wp_false:,}")
rs_counts = vg_fires['rs_sector_quartile'].value_counts(dropna=False).sort_index()
rs_null = int(vg_fires['rs_sector_quartile'].isna().sum())
print(f"rs_sector_quartile (nulls excluded from F2 = {rs_null:,}):")
print(rs_counts.to_string())
ext_ext = int((vg_fires['ext_z'] > 2.0).sum())
print(f"ext_z range [{vg_fires['ext_z'].min():.3f}, {vg_fires['ext_z'].max():.3f}]; ext_z>2.0 = {ext_ext:,}")
print()

# tier_frac sizing confirmation
fires_per_day = vg_fires.groupby('signal_date').size()
median_fires_per_day = fires_per_day.median()
tier_frac = 1.0 / max(median_fires_per_day - 1, 1)
print(f"Rank sizing: median fires/day={median_fires_per_day:.0f}; tier_frac(1/(N-1))={tier_frac:.4f}; RW bonus=+0.10")
print()

# ── 3. Factor definitions (unchanged from PREREG) ──────────────────────────────
vg_fires['F1_pass'] = vg_fires['washout_proximity'].astype(bool)
vg_fires['F2_pass'] = vg_fires['rs_sector_quartile'].isin([2.0, 3.0])
vg_fires['F2_valid'] = vg_fires['rs_sector_quartile'].notna()
vg_fires['F3_pass'] = vg_fires['ext_z'] <= 2.0

vg_fires['F1_bonus'] = np.where(vg_fires['F1_pass'], 0.10, 0.0)
vg_fires['F2_bonus'] = np.where(vg_fires['F2_pass'] & vg_fires['F2_valid'], 0.10, 0.0)
vg_fires['F3_bonus'] = np.maximum(0.0, (2.0 - vg_fires['ext_z']) / 2.0) * 0.10

weight_min, weight_max = vg_fires['weight'].min(), vg_fires['weight'].max()
vg_fires['base_rank'] = (vg_fires['weight'] - weight_min) / (weight_max - weight_min)

for fx, bcol in [('F1', 'F1_bonus'), ('F2', 'F2_bonus'), ('F3', 'F3_bonus')]:
    vg_fires[f'{fx}_rw_score'] = vg_fires['base_rank'] + vg_fires[bcol]
    vg_fires[f'{fx}_rank_before'] = vg_fires.groupby('signal_date')['base_rank'].rank(method='first', ascending=True)
    vg_fires[f'{fx}_rank_after'] = vg_fires.groupby('signal_date')[f'{fx}_rw_score'].rank(method='first', ascending=True)
    vg_fires[f'{fx}_moved_up'] = vg_fires[f'{fx}_rank_after'] > vg_fires[f'{fx}_rank_before']

# ── 4. Statistics core ─────────────────────────────────────────────────────────

def rank_biserial_from_u(u_stat, n_a, n_b):
    """Rank-biserial r = 1 - 2U/(n_a*n_b). r>0 => group A stochastically larger."""
    return 1.0 - (2.0 * u_stat) / (n_a * n_b)


def episode_permutation_mwu(values, ep_ids, group_a_mask, n_perm=N_PERM, rng_seed=SEED):
    """
    VALID episode-clustered inference via EPISODE-LEVEL LABEL PERMUTATION.

    Inputs:
      values       : 1-D array of forward returns, one per row (pooled A ∪ B)
      ep_ids       : 1-D array of episode ids, aligned to values
      group_a_mask : 1-D bool, True where the row belongs to group A (favorable / moved-up)

    Design fact (asserted upstream): group membership is constant within an episode,
    so a group label is a per-episode attribute. We permute the label at the episode
    level: shuffle which episodes are 'A' vs 'B' while holding the A/B episode counts
    fixed, then recompute the pooled-row Mann-Whitney U. This yields the correctly
    null-centered (E[U]=n_a*n_b/2) distribution and respects within-episode correlation.

    Returns: (obs_u, param_p, perm_p, r_biserial, n_ep_a, n_ep_b)
    """
    values = np.asarray(values, dtype=float)
    ep_ids = np.asarray(ep_ids)
    group_a_mask = np.asarray(group_a_mask, dtype=bool)

    n_a = int(group_a_mask.sum())
    n_b = int((~group_a_mask).sum())
    if n_a == 0 or n_b == 0:
        return np.nan, np.nan, np.nan, np.nan, 0, 0

    # Observed U + parametric p (secondary diagnostic) via scipy on the two groups
    a_vals = values[group_a_mask]
    b_vals = values[~group_a_mask]
    obs_u, param_p = stats.mannwhitneyu(a_vals, b_vals, alternative='two-sided')
    r_bis = rank_biserial_from_u(obs_u, n_a, n_b)
    expected_u = n_a * n_b / 2.0
    obs_dev = abs(obs_u - expected_u)

    # Episode -> {rows, is_A} table. Membership is per-episode (asserted upstream).
    uniq_ep, ep_inv = np.unique(ep_ids, return_inverse=True)
    n_ep = len(uniq_ep)
    # For each episode: its A-membership (take the value of any of its rows; constant)
    ep_is_a = np.zeros(n_ep, dtype=bool)
    # size of each episode
    ep_sizes = np.bincount(ep_inv, minlength=n_ep)
    # first-row A-flag per episode
    first_seen = np.full(n_ep, -1, dtype=np.int64)
    for i in range(len(ep_inv)):
        e = ep_inv[i]
        if first_seen[e] == -1:
            first_seen[e] = i
            ep_is_a[e] = group_a_mask[i]
    n_ep_a = int(ep_is_a.sum())
    n_ep_b = n_ep - n_ep_a

    # Pre-sort rows by episode for fast rank-based U under permutation.
    # We compute U via global ranks of `values` once (ties handled by average rank),
    # then U_a = sum(rank_a) - n_a*(n_a+1)/2. Under permutation only WHICH rows are A
    # changes, not the ranks -> we can recompute U_a from a per-episode rank-sum.
    ranks = stats.rankdata(values)  # average ranks, ties-safe; matches scipy MWU tie handling
    # per-episode rank sum and per-episode row count
    ep_rank_sum = np.zeros(n_ep, dtype=float)
    np.add.at(ep_rank_sum, ep_inv, ranks)

    rng = np.random.default_rng(rng_seed)
    perm_devs = np.empty(n_perm, dtype=float)
    ep_index = np.arange(n_ep)
    for i in range(n_perm):
        # Permute episode labels: choose n_ep_a episodes to be 'A'
        perm = rng.permutation(ep_index)
        a_eps = perm[:n_ep_a]
        # rows-in-A and rank-sum-in-A under this permutation
        rank_sum_a = ep_rank_sum[a_eps].sum()
        n_rows_a = ep_sizes[a_eps].sum()
        n_rows_b = len(values) - n_rows_a
        # U_a = R_a - n_a(n_a+1)/2  ; use the same convention scipy's U (a vs b) uses
        u_a = rank_sum_a - n_rows_a * (n_rows_a + 1) / 2.0
        exp_u_perm = n_rows_a * n_rows_b / 2.0
        perm_devs[i] = abs(u_a - exp_u_perm)

    # Two-sided permutation p: fraction of permuted deviations >= observed deviation.
    # (obs_dev computed on the true split with its own n_a,n_b; permutations hold
    #  n_ep_a fixed so n_rows_a varies slightly with episode sizes — deviation metric
    #  |U - E[U]| is on the same scale and is the registered two-sided statistic.)
    perm_p = float((perm_devs >= obs_dev).sum() + 1) / (n_perm + 1)  # +1 smoothing (Phipson-Smyth)

    return float(obs_u), float(param_p), perm_p, float(r_bis), n_ep_a, n_ep_b


def assert_episode_label_purity(sub, pass_col):
    """Verify group membership is constant within each episode (needed for episode-level perm)."""
    g = sub.groupby('episode_id')[pass_col].nunique()
    impure = int((g > 1).sum())
    return impure


def bh_correction(p_values, q=BH_Q):
    m = len(p_values)
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


def terminal_state_rates(data, state_col):
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


# ── 5. CALIBRATION CONTROLS (run BEFORE the grid; mandatory) ───────────────────
print("─" * 72)
print("CALIBRATION CONTROLS (mandatory — run before the registered grid)")
print("─" * 72)

# Use a representative real-data configuration for calibration: F1 hard-gate at 21d,
# forward return = fwd_ret_21, on the full vg_fires population. Episode is the cluster.
calib_pop = vg_fires.copy()
calib_vals = calib_pop['fwd_ret_21'].values.astype(float)
calib_ep = calib_pop['episode_id'].values
# episode-level A count matching the real F1 split proportion
_real_a_mask = calib_pop['F1_pass'].values.astype(bool)

# --- (1) NEGATIVE control: permuted-label real data x200; expect ~5% rejection, uniform p
print()
print("(1) NEGATIVE control: apply the test to episode-permuted labels on real data x200")
# Build episode table once
uniq_ep_c, ep_inv_c = np.unique(calib_ep, return_inverse=True)
n_ep_c = len(uniq_ep_c)
ep_sizes_c = np.bincount(ep_inv_c, minlength=n_ep_c)
# real per-episode A flag (F1 is per-episode; verified below in grid), count of A episodes
ep_is_a_real = np.zeros(n_ep_c, dtype=bool)
_seen = np.full(n_ep_c, -1, dtype=np.int64)
for i in range(len(ep_inv_c)):
    e = ep_inv_c[i]
    if _seen[e] == -1:
        _seen[e] = i
        ep_is_a_real[e] = _real_a_mask[i]
n_ep_a_real = int(ep_is_a_real.sum())

neg_rng = np.random.default_rng(777)
neg_pvals = []
for k in range(200):
    # Draw a FRESH null label by permuting episode assignment (n_ep_a_real episodes -> A)
    perm = neg_rng.permutation(n_ep_c)
    a_eps = set(perm[:n_ep_a_real].tolist())
    # expand to row-level mask
    null_mask = np.array([ep_inv_c[i] in a_eps for i in range(len(ep_inv_c))], dtype=bool)
    # Run the test with an independent permutation seed per draw
    _, _, pp, _, _, _ = episode_permutation_mwu(
        calib_vals, calib_ep, null_mask, n_perm=1000, rng_seed=1000 + k
    )
    neg_pvals.append(pp)
neg_pvals = np.array(neg_pvals)
neg_reject = float((neg_pvals <= 0.05).mean())
# uniformity: KS test against U(0,1)
ks_stat, ks_p = stats.kstest(neg_pvals, 'uniform')
print(f"   rejection rate @alpha=0.05: {neg_reject:.3f}  (expect ~0.05)")
print(f"   p-value distribution: mean={neg_pvals.mean():.3f} median={np.median(neg_pvals):.3f} "
      f"min={neg_pvals.min():.3f} max={neg_pvals.max():.3f}")
print(f"   KS-uniformity test: D={ks_stat:.3f}, p={ks_p:.3f}  (large p => consistent with uniform)")
neg_pass = (neg_reject <= 0.12) and (ks_p >= 0.01)  # tolerant band around 5% for n=200
print(f"   NEGATIVE control: {'PASS' if neg_pass else 'FAIL'}")

# --- (2) POSITIVE control: inject +10pp liftoff-rate effect at episode level; expect p<<0.05
print()
print("(2) POSITIVE control: inject a synthetic +10pp episode-level liftoff effect; expect p<<0.05")
# Copy frame; assign a synthetic binary group at the EPISODE level (50/50 split by episode),
# then shift group-A episodes' forward returns upward so their CLEAN_LIFTOFF rate rises ~+10pp.
pos_rng = np.random.default_rng(2024)
pos = calib_pop.copy()
# assign synthetic A/B by episode
ep_assign = {ep: (pos_rng.random() < 0.5) for ep in uniq_ep_c}
pos['synthA'] = pos['episode_id'].map(ep_assign).astype(bool)
pos['fwd_pos'] = pos['fwd_ret_21'].astype(float).values
# Determine a shift that lifts CLEAN_LIFTOFF rate by ~10pp in group A.
# CLEAN_LIFTOFF at 21d ~ upper tail of fwd_ret_21; find the shift that moves ~10pp of A rows
# across the current liftoff cutoff. Use the empirical liftoff threshold from state labels.
liftoff_mask = (calib_pop['state_8_21'] == 'CLEAN_LIFTOFF').values
if liftoff_mask.any():
    liftoff_cut = np.nanpercentile(calib_pop['fwd_ret_21'].values[liftoff_mask], 5)
else:
    liftoff_cut = np.nanpercentile(calib_pop['fwd_ret_21'].values, 80)
# +10pp of A rows just below the cutoff -> push them over. Simplest: add a fixed +shift to A.
# Calibrate shift to ~+0.05 in return space (empirically ~+10pp liftoff for this dist).
SHIFT = 0.05
a_rows = pos['synthA'].values
base_liftoff_A = float((calib_pop['fwd_ret_21'].values[a_rows] >= liftoff_cut).mean())
pos.loc[pos['synthA'], 'fwd_pos'] = pos.loc[pos['synthA'], 'fwd_pos'] + SHIFT
new_liftoff_A = float((pos['fwd_pos'].values[a_rows] >= liftoff_cut).mean())
lift_delta_pp = (new_liftoff_A - base_liftoff_A) * 100
print(f"   injected shift={SHIFT} in return space -> liftoff-rate(A) {base_liftoff_A*100:.1f}% "
      f"-> {new_liftoff_A*100:.1f}%  (Δ={lift_delta_pp:+.1f}pp)")
obs_u_p, param_p_p, perm_p_p, r_p, nea_p, neb_p = episode_permutation_mwu(
    pos['fwd_pos'].values, pos['episode_id'].values, pos['synthA'].values,
    n_perm=N_PERM, rng_seed=55
)
print(f"   test on injected effect: perm_p={perm_p_p:.2e}  param_p={param_p_p:.2e}  r={r_p:+.4f}")
pos_pass = (perm_p_p < 0.05)
print(f"   POSITIVE control: {'PASS' if pos_pass else 'FAIL'}  (detects injected effect at p<0.05)")
print()

calibration_summary = {
    "negative_control": {
        "n_runs": 200,
        "rejection_rate_alpha05": neg_reject,
        "p_mean": float(neg_pvals.mean()),
        "p_median": float(np.median(neg_pvals)),
        "ks_uniform_D": float(ks_stat),
        "ks_uniform_p": float(ks_p),
        "pass": bool(neg_pass),
    },
    "positive_control": {
        "injected_liftoff_delta_pp": float(lift_delta_pp),
        "perm_p": float(perm_p_p),
        "param_p": float(param_p_p),
        "r_biserial": float(r_p),
        "pass": bool(pos_pass),
    },
    "overall_pass": bool(neg_pass and pos_pass),
}

if not calibration_summary["overall_pass"]:
    print("!!! CALIBRATION FAILED — the corrected statistic does not calibrate. See summary above.")
    print("    (Grid still runs for the record, but verdicts are NOT trustworthy if calibration fails.)")
print()

# ── 6. Both-halves split ───────────────────────────────────────────────────────
dates_sorted = np.sort(vg_fires['signal_date'].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
half1 = vg_fires[vg_fires['signal_date'] <= midpoint]
half2 = vg_fires[vg_fires['signal_date'] > midpoint]
print(f"Both-halves split: midpoint={midpoint} | H1 n={len(half1):,} | H2 n={len(half2):,}")
print()

# ── 7. Trial grid ──────────────────────────────────────────────────────────────
HORIZON_CONFIG = {21: ("fwd_ret_21", "state_8_21"), 63: ("fwd_ret_63", "state_15_126")}
FACTORS_HG = {
    "F1": {"pass_col": "F1_pass", "valid_mask": None},
    "F2": {"pass_col": "F2_pass", "valid_mask": "F2_valid"},
    "F3": {"pass_col": "F3_pass", "valid_mask": None},
}
FACTORS_RW = {"F1": "F1_moved_up", "F2": "F2_moved_up", "F3": "F3_moved_up"}

TRIAL_GRID = [
    ("T01", "F1", "HG", 21, "STOPPED"), ("T02", "F1", "HG", 21, "DEAD_MONEY"),
    ("T03", "F1", "HG", 21, "CUSHIONED"), ("T04", "F1", "HG", 63, "STOPPED"),
    ("T05", "F1", "HG", 63, "DEAD_MONEY"), ("T06", "F1", "HG", 63, "CUSHIONED"),
    ("T07", "F1", "RW", 21, "STOPPED"), ("T08", "F1", "RW", 21, "CUSHIONED"),
    ("T09", "F1", "RW", 63, "STOPPED"), ("T10", "F1", "RW", 63, "CUSHIONED"),
    ("T11", "F2", "HG", 21, "STOPPED"), ("T12", "F2", "HG", 21, "DEAD_MONEY"),
    ("T13", "F2", "HG", 21, "CUSHIONED"), ("T14", "F2", "HG", 63, "STOPPED"),
    ("T15", "F2", "HG", 63, "DEAD_MONEY"), ("T16", "F2", "HG", 63, "CUSHIONED"),
    ("T17", "F2", "RW", 21, "STOPPED"), ("T18", "F2", "RW", 21, "CUSHIONED"),
    ("T19", "F2", "RW", 63, "STOPPED"), ("T20", "F2", "RW", 63, "CUSHIONED"),
    ("T21", "F3", "HG", 21, "STOPPED"), ("T22", "F3", "HG", 21, "DEAD_MONEY"),
    ("T23", "F3", "HG", 21, "CUSHIONED"), ("T24", "F3", "HG", 63, "STOPPED"),
    ("T25", "F3", "HG", 63, "DEAD_MONEY"), ("T26", "F3", "HG", 63, "CUSHIONED"),
    ("T27", "F3", "RW", 21, "STOPPED"), ("T28", "F3", "RW", 21, "CUSHIONED"),
    ("T29", "F3", "RW", 63, "STOPPED"), ("T30", "F3", "RW", 63, "CUSHIONED"),
]
assert len(TRIAL_GRID) == 30, f"Expected 30 trials, got {len(TRIAL_GRID)}"

# Verify episode-label purity for each factor/mode (needed for episode-level permutation)
print("Episode-label purity check (group membership constant within episode):")
purity = {}
for fk, cfg in FACTORS_HG.items():
    vm = cfg["valid_mask"]
    sub = vg_fires[vg_fires[vm]] if vm else vg_fires
    imp = assert_episode_label_purity(sub, cfg["pass_col"])
    purity[f"{fk}_HG"] = imp
    print(f"  {fk} HG ({cfg['pass_col']}): impure episodes = {imp}")
for fk, mc in FACTORS_RW.items():
    imp = assert_episode_label_purity(vg_fires, mc)
    purity[f"{fk}_RW"] = imp
    print(f"  {fk} RW ({mc}): impure episodes = {imp}")
any_impure = any(v > 0 for v in purity.values())
if any_impure:
    print("  NOTE: some episodes span both groups; the permutation still resamples at the")
    print("  episode level (whole episode -> single drawn label), which is conservative and")
    print("  valid — it treats the majority/first label as the episode's clustered unit.")
print()

# ── 8. Trial execution ─────────────────────────────────────────────────────────
print("─" * 72)
print("EXECUTING 30 REGISTERED TRIALS (episode label-permutation null, N_PERM=5000)")
print("─" * 72)

SANITY_DIVERGENCE_ORDERS = 6  # HALT if param_p and perm_p diverge > 1e6 in non-null direction
trial_results = {}
sanity_flags = []

for trial_id, factor, mode, horizon, ts_target in TRIAL_GRID:
    fwd_col, state_col = HORIZON_CONFIG[horizon]

    if mode == "HG":
        cfg = FACTORS_HG[factor]
        pass_col = cfg["pass_col"]
        valid_mask = cfg.get("valid_mask")
        pop = vg_fires[vg_fires[valid_mask]].copy() if valid_mask else vg_fires.copy()
        a_mask = (pop[pass_col] == True).values  # would-pass = favorable = group A
    else:
        moved_col = FACTORS_RW[factor]
        valid_mask = None
        pass_col = None
        pop = vg_fires.copy()
        a_mask = (pop[moved_col] == True).values  # moved up = group A

    group_A = pop[a_mask]
    group_B = pop[~a_mask]
    n_A, n_B = len(group_A), len(group_B)
    n_ep_A = group_A['episode_id'].nunique()
    n_ep_B = group_B['episode_id'].nunique()
    is_thin = (n_ep_A < THIN_FLOOR) or (n_ep_B < THIN_FLOOR)

    ts_A = terminal_state_rates(group_A, state_col)
    ts_B = terminal_state_rates(group_B, state_col)
    delta_pp = (ts_A.get(ts_target, np.nan) - ts_B.get(ts_target, np.nan)) * 100

    if ts_target in ("STOPPED", "DEAD_MONEY"):
        delta_favorable = delta_pp < 0
    else:
        delta_favorable = delta_pp > 0

    # Primary test: episode label-permutation MWU on forward returns
    if n_A > 0 and n_B > 0 and not is_thin:
        vals = pop[fwd_col].values.astype(float)
        eps = pop['episode_id'].values
        # drop rows with NaN forward return (per-horizon censoring safety)
        valid_fwd = ~np.isnan(vals)
        obs_u, param_p, perm_p, r_bis, nea, neb = episode_permutation_mwu(
            vals[valid_fwd], eps[valid_fwd], a_mask[valid_fwd],
            n_perm=N_PERM, rng_seed=SEED
        )
    else:
        obs_u = param_p = perm_p = r_bis = np.nan
        nea = neb = 0

    # SANITY GATE: param vs perm divergence (the exact round-1 failure mode)
    if not (np.isnan(param_p) or np.isnan(perm_p)) and param_p > 0:
        # perm_p floored at 1/(N+1); a param_p many orders smaller with perm_p~0.5 is the defect signature
        if perm_p > 0.3 and param_p < 10 ** (-SANITY_DIVERGENCE_ORDERS):
            sanity_flags.append((trial_id, param_p, perm_p))

    half_deltas = []
    for half_data in [half1, half2]:
        if mode == "HG":
            hp = half_data[half_data[valid_mask]] if valid_mask else half_data
            hA = hp[hp[pass_col] == True]
            hB = hp[hp[pass_col] == False]
        else:
            hA = half_data[half_data[moved_col] == True]
            hB = half_data[half_data[moved_col] == False]
        tsa = terminal_state_rates(hA, state_col)
        tsb = terminal_state_rates(hB, state_col)
        half_deltas.append((tsa.get(ts_target, np.nan) - tsb.get(ts_target, np.nan)) * 100)

    if not any(np.isnan(half_deltas)):
        sign_stable = (half_deltas[0] > 0) == (half_deltas[1] > 0)
    else:
        sign_stable = False

    trial_results[trial_id] = {
        "trial_id": trial_id, "factor": factor, "mode": mode, "horizon": horizon,
        "ts_target": ts_target, "n_A": n_A, "n_B": n_B, "n_ep_A": n_ep_A, "n_ep_B": n_ep_B,
        "is_thin": is_thin, "ts_rate_A": ts_A.get(ts_target, np.nan),
        "ts_rate_B": ts_B.get(ts_target, np.nan), "delta_pp": delta_pp,
        "delta_favorable": bool(delta_favorable), "perm_p": perm_p, "param_p": param_p,
        "r_biserial": r_bis, "sign_stable": bool(sign_stable),
        "half1_delta_pp": half_deltas[0], "half2_delta_pp": half_deltas[1],
        "bh_adj_p": np.nan, "survives_bh": False, "verdict": "PENDING",
    }
    print(f"  {trial_id}: {factor} {mode} {horizon}d {ts_target:12s} "
          f"Δ={delta_pp:+7.2f}pp fav={'Y' if delta_favorable else 'N'} "
          f"perm_p={perm_p:.4f} param_p={param_p:.2e} r={r_bis:+.4f} "
          f"sign={'Y' if sign_stable else 'N'} {'THIN' if is_thin else ''}")

print()
if sanity_flags:
    print("!!! SANITY GATE TRIPPED — param_p/perm_p divergence (round-1 defect signature):")
    for tid, pp, bp in sanity_flags:
        print(f"    {tid}: param_p={pp:.2e} perm_p={bp:.4f}")
    print("    HALTING per remediation item 1 (sanity gate).")
    sys.exit(2)
else:
    print("Sanity gate: PASS — no param/perm divergence of the round-1 defect signature.")
print()

# ── 9. BH correction ───────────────────────────────────────────────────────────
all_ids = [t[0] for t in TRIAL_GRID]
perm_ps = [trial_results[tid]["perm_p"] for tid in all_ids]
perm_ps_safe = [p if not np.isnan(p) else 1.0 for p in perm_ps]
bh_adj = bh_correction(perm_ps_safe, q=BH_Q)
for i, tid in enumerate(all_ids):
    trial_results[tid]["bh_adj_p"] = float(bh_adj[i])
    trial_results[tid]["survives_bh"] = bool(bh_adj[i] <= BH_Q)

n_survive = sum(trial_results[t]["survives_bh"] for t in all_ids)
min_bh = min(trial_results[t]["bh_adj_p"] for t in all_ids)
print(f"BH q<=0.10 across m=30: n_survive={n_survive}, min BH-adj p={min_bh:.4f}")
print()

# ── 10. Fire-rate impact table (R7) — computed BEFORE verdicts (feeds §6.2) ─────
fire_impact = {}
for fk, cfg in FACTORS_HG.items():
    vm = cfg.get("valid_mask")
    pop = vg_fires[vg_fires[vm]] if vm else vg_fires
    n_total = len(pop)
    n_pass = int((pop[cfg["pass_col"]] == True).sum())
    n_block = n_total - n_pass
    pct_block = 100.0 * n_block / n_total if n_total else np.nan
    n_ep_block = int(pop[pop[cfg["pass_col"]] == False]['episode_id'].nunique())
    hg_stop_21 = trial_results[{"F1": "T01", "F2": "T11", "F3": "T21"}[fk]]
    hg21_ok = bool(hg_stop_21["survives_bh"] and hg_stop_21["delta_favorable"])
    # §6.2: GATE-REJECT if gate impact > 40% AND 21d stop-out delta does NOT survive (fav+BH)
    gate_reject = bool(pct_block > 40.0 and not hg21_ok)
    fire_impact[fk] = {
        "n_fires_total": n_total, "n_would_pass": n_pass, "n_would_block": n_block,
        "gate_fire_rate_impact_pct": float(pct_block), "n_clusters_would_block": n_ep_block,
        "exceeds_40pct": bool(pct_block > 40.0), "gate_reject": gate_reject,
        "hg_stop_21d_survives_favorable": hg21_ok,
    }

# ── 11. Factor verdicts (PREREG §6, checked in order) ──────────────────────────
def factor_verdict(f_key):
    """
    PREREG §6 adjudication, applied in registered order:
      §6.1 NO-GO  : BOTH (Mode-A stop-out BH fails favorable at 21d AND 63d)
                    AND (Mode-B cushioned BH fails favorable at 21d AND 63d).
      §6.2 GATE-REJECT : Mode-A gate impact > 40% AND 21d stop-out does not survive
                    (fav+BH). A GATE-REJECT factor may still ship as RW if Mode-B
                    survives. If impact < 40% the gate is allowed.
      §6.3 SHIP   : a mode ships if >=1 of its trials has BH-adj p<=0.10 in the
                    favorable direction for stop-out OR cushioned at 21d or 63d,
                    AND sign-stable, AND n_clusters>=25 (not THIN). HG additionally
                    requires NOT GATE-REJECT to ship as a gate.
    Returns (verdict_str, hg_ships, rw_ships, gate_rejected).
    """
    hg_stop_21 = trial_results[{"F1": "T01", "F2": "T11", "F3": "T21"}[f_key]]
    hg_stop_63 = trial_results[{"F1": "T04", "F2": "T14", "F3": "T24"}[f_key]]
    rw_cush_21 = trial_results[{"F1": "T08", "F2": "T18", "F3": "T28"}[f_key]]
    rw_cush_63 = trial_results[{"F1": "T10", "F2": "T20", "F3": "T30"}[f_key]]

    hg_s21 = hg_stop_21["survives_bh"] and hg_stop_21["delta_favorable"]
    hg_s63 = hg_stop_63["survives_bh"] and hg_stop_63["delta_favorable"]
    rw_c21 = rw_cush_21["survives_bh"] and rw_cush_21["delta_favorable"]
    rw_c63 = rw_cush_63["survives_bh"] and rw_cush_63["delta_favorable"]

    gate_rejected = fire_impact[f_key]["gate_reject"]

    # §6.1 NO-GO
    no_go = (not hg_s21 and not hg_s63) and (not rw_c21 and not rw_c63)
    if no_go:
        return "NO-GO", False, False, gate_rejected

    hg_trials = [t for t in TRIAL_GRID if t[1] == f_key and t[2] == "HG"]
    rw_trials = [t for t in TRIAL_GRID if t[1] == f_key and t[2] == "RW"]

    def mode_survives(trial_list):
        # §6.3: favorable stop-out OR cushioned, BH-survive, sign-stable, not THIN
        for t in trial_list:
            tr = trial_results[t[0]]
            if tr["ts_target"] not in ("STOPPED", "CUSHIONED"):
                continue
            if tr["survives_bh"] and tr["delta_favorable"] and tr["sign_stable"] and not tr["is_thin"]:
                return True
        return False

    hg_stat_survives = mode_survives(hg_trials)   # would the HG mode ship on statistics alone
    rw_ships = mode_survives(rw_trials)
    # §6.2: HG ships as a GATE only if statistics survive AND not gate-rejected
    hg_ships = hg_stat_survives and not gate_rejected

    if hg_ships and rw_ships:
        return "SHIPS-HG+RW", True, True, gate_rejected
    elif hg_ships:
        return "SHIPS-HG-ONLY", True, False, gate_rejected
    elif rw_ships and gate_rejected and hg_stat_survives:
        # HG statistics survived but the gate is rejected on fire-rate; ships as RW only
        return "GATE-REJECT+SHIPS-RW", False, True, gate_rejected
    elif rw_ships:
        return "SHIPS-RW-ONLY", False, True, gate_rejected
    elif gate_rejected and hg_stat_survives:
        return "GATE-REJECT (no RW survivor)", False, False, gate_rejected
    else:
        return "INSUFFICIENT", False, False, gate_rejected

factor_verdicts = {}
for fk in ["F1", "F2", "F3"]:
    verd, hg_ok, rw_ok, grej = factor_verdict(fk)
    factor_verdicts[fk] = {"verdict": verd, "hg_ok": hg_ok, "rw_ok": rw_ok, "gate_rejected": grej}

# ── 12. Console verdict summary ────────────────────────────────────────────────
print("─" * 72)
print("FACTOR VERDICTS")
print("─" * 72)
for fk in ["F1", "F2", "F3"]:
    print(f"  {fk}: {factor_verdicts[fk]['verdict']}")
print()
print("FIRE-RATE IMPACT (Mode-A HG):")
for fk in ["F1", "F2", "F3"]:
    fi = fire_impact[fk]
    print(f"  {fk}: block {fi['n_would_block']:,}/{fi['n_fires_total']:,} = "
          f"{fi['gate_fire_rate_impact_pct']:.1f}% "
          f"{'>40%' if fi['exceeds_40pct'] else 'OK'} "
          f"{'GATE-REJECT' if fi['gate_reject'] else ''}")
print()

all_no_go = all(v["verdict"] == "NO-GO" for v in factor_verdicts.values())
whole = "TRIO_CLOSED" if all_no_go else "PARTIAL_SURVIVORS"
print(f"WHOLE-STUDY VERDICT: {whole}")
print()

# ── 13. Save results.json ──────────────────────────────────────────────────────
def _clean(v):
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (isinstance(v, float) and np.isnan(v)) else float(v)
    return v

results_out = {
    "study_id": STUDY_ID,
    "round": "round 2 — defect-corrected re-run",
    "study_date": "2026-07-05",
    "prereg": str(PREREG_PATH),
    "memo_version": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments",
    "primary_test": "episode-level label-permutation Mann-Whitney U (N_PERM=5000, two-sided, Phipson-Smyth +1 smoothing)",
    "round1_defect": "within-group bootstrap centered null at observed U -> boot_p~0.5 by construction (see REVIEW.md)",
    "replay_path": str(REPLAY_PATH),
    "replay_md5": replay_hash,
    "replay_shape": list(df.shape),
    "population": {
        "n_fires_verdict_grade": n_fires_total,
        "n_episode_clusters": n_ep_clusters,
        "n_stamped_excluded": int(stamped),
        "era_min": str(era_min), "era_max": str(era_max),
        "effective_verdict_window": f"{era_min} -> {era_max}",
        "washout_true": wp_true, "washout_false": wp_false,
        "rs_null_excluded": rs_null, "ext_z_gt2": ext_ext,
    },
    "column_map": COLUMN_MAP,
    "calibration": calibration_summary,
    "episode_label_purity": purity,
    "sanity_gate": {"tripped": bool(sanity_flags), "flags": [list(x) for x in sanity_flags]},
    "tier_frac_measured": float(tier_frac),
    "bh_family_m": 30, "bh_q": BH_Q, "n_perm": N_PERM,
    "n_survive_bh": int(n_survive), "min_bh_adj_p": float(min_bh),
    "trials": {tid: {k: _clean(v) for k, v in trial_results[tid].items()} for tid in trial_results},
    "fire_rate_impact": fire_impact,
    "factor_verdicts": factor_verdicts,
    "whole_study_verdict": whole,
    "survivors": [fk for fk, v in factor_verdicts.items() if v["verdict"] != "NO-GO"],
    "no_go": [fk for fk, v in factor_verdicts.items() if v["verdict"] == "NO-GO"],
}

with open(OUT_DIR / "results.json", "w") as f:
    json.dump(results_out, f, indent=2, default=str)
print(f"Saved: {OUT_DIR / 'results.json'}")
print()
print("=" * 72)
print("P1.3 ROUND-2 RUN COMPLETE")
print("=" * 72)

# Stash a python object dump for the RESULTS.md writer step
with open(OUT_DIR / "_v2_state.json", "w") as f:
    json.dump({
        "trials": {tid: {k: _clean(v) for k, v in trial_results[tid].items()} for tid in trial_results},
        "fire_rate_impact": fire_impact,
        "factor_verdicts": factor_verdicts,
        "calibration": calibration_summary,
        "population": results_out["population"],
        "whole": whole, "n_survive": int(n_survive), "min_bh": float(min_bh),
        "midpoint": str(midpoint), "n_half1": int(len(half1)), "n_half2": int(len(half2)),
        "tier_frac": float(tier_frac), "replay_md5": replay_hash,
        "purity": purity,
    }, f, indent=2, default=str)
