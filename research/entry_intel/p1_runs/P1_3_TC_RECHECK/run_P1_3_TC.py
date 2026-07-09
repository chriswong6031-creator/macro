"""
EI-RC-1 — P1.3 Trials Under Within-Month Demeaning + Month-Block Bootstrap
Re-check family (separate from original m=30 family): T02, T09, T18, T21, T24
DT-R14 calendar-time controls applied.

Source study: research/entry_intel/p1_runs/P1_3/run_P1_3.py
Canonical input: data/replay/replay_boarded.parquet (NEVER part files)
Study date: 2026-07-07

RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.
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

# Allow override via environment variable (for test environments)
_data_root = os.environ.get("MAIN_DATA")
if _data_root:
    REPLAY_PATH = Path(_data_root) / "replay" / "replay_boarded.parquet"
else:
    REPLAY_PATH = REPO / "data" / "replay" / "replay_boarded.parquet"

OUT_DIR = Path(__file__).parent

STUDY_ID = "P1_3_TC_RECHECK"
N_BOOT = 5000          # month-block bootstrap replicates
N_PERM_CA = 2000       # C-A within-month label permutation replicates
SEED = 11              # registered seed for month-block bootstrap
BH_Q = 0.10
THIN_FLOOR = 25

# Date window from original study
DATE_MIN = pd.Timestamp("2022-06-30")
DATE_MAX = pd.Timestamp("2025-12-29")

# Target trials for this re-check
TARGET_TRIALS = ["T02", "T09", "T18", "T21", "T24"]

print("=" * 72)
print(f"EI-RC-1  — {STUDY_ID}")
print("RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.")
print("=" * 72)
print()

# ── 0. Load data (verbatim from run_P1_3.py) ──────────────────────────────────
assert REPLAY_PATH.exists(), f"BLOCKER: replay_boarded.parquet not found at {REPLAY_PATH}"
with open(REPLAY_PATH, "rb") as fh:
    replay_hash = hashlib.md5(fh.read()).hexdigest()
print(f"Replay path: {REPLAY_PATH}")
print(f"Replay MD5:  {replay_hash}")
print(f"scipy version: {scipy.__version__}")
print()

print("Loading replay_boarded.parquet...")
df = pd.read_parquet(REPLAY_PATH)
print(f"  Full shape: {df.shape}")
print()

# ── Column map (verbatim) ──────────────────────────────────────────────────────
COLUMN_MAP = {
    "episode_cluster_id": "episode_id",
    "cohort_washout_proximity": "washout_proximity",
    "rs_vs_sector_quartile": "rs_sector_quartile",
    "fwd_21d": "fwd_ret_21",
    "fwd_63d": "fwd_ret_63",
    "survivor_bias_stamp": "survivor_bias",
}
required = list(COLUMN_MAP.values()) + [
    'ext_z', 'verdict_type', 'verdict_grade',
    'state_8_21', 'state_15_126',
    'signal_date', 'entry_price', 'sector', 'weight',
]
missing = [c for c in required if c not in df.columns]
if missing:
    print(f"BLOCKER: Missing columns: {missing}")
    sys.exit(1)

# ── 1. Build primary population (verbatim from run_P1_3.py §2) ────────────────
fires_all = df[df['verdict_type'] == 'fire'].copy()
vg_fires = fires_all[fires_all['verdict_grade'] == True].copy()

stamped = int(vg_fires['survivor_bias'].sum())
assert stamped == 0, f"UNEXPECTED: {stamped} survivor_bias==True rows"

# Apply the original study's date window filter (per REPRODUCTION GATE spec)
# signal_date may be stored as string; coerce to datetime for comparison
vg_fires['signal_date'] = pd.to_datetime(vg_fires['signal_date'])
vg_fires = vg_fires[
    (vg_fires['signal_date'] >= DATE_MIN) &
    (vg_fires['signal_date'] <= DATE_MAX)
].copy()

era_min = vg_fires['signal_date'].min()
era_max = vg_fires['signal_date'].max()
n_fires_total = len(vg_fires)
n_ep_clusters = vg_fires['episode_id'].nunique()

print("─" * 72)
print("POPULATION CENSUS (date-windowed)")
print("─" * 72)
print(f"  Date window:                   {DATE_MIN.date()} -> {DATE_MAX.date()}")
print(f"  Verdict-grade fires (primary): {n_fires_total:,}")
print(f"  Effective era:                 {era_min} -> {era_max}")
print(f"  Episode clusters (unique):     {n_ep_clusters:,}")
print()

# ── 2. Factor definitions (verbatim from run_P1_3.py §3) ──────────────────────
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
    vg_fires[f'{fx}_rank_before'] = vg_fires.groupby('signal_date')['base_rank'].rank(
        method='first', ascending=True)
    vg_fires[f'{fx}_rank_after'] = vg_fires.groupby('signal_date')[f'{fx}_rw_score'].rank(
        method='first', ascending=True)
    vg_fires[f'{fx}_moved_up'] = vg_fires[f'{fx}_rank_after'] > vg_fires[f'{fx}_rank_before']

# ── 3. Terminal-state rate helper (verbatim) ───────────────────────────────────
def terminal_state_rates(data, state_col):
    n = len(data)
    if n == 0:
        return {"STOPPED": np.nan, "DEAD_MONEY": np.nan,
                "CUSHIONED": np.nan, "CLEAN_LIFTOFF": np.nan, "n": 0}
    vc = data[state_col].value_counts()
    return {
        "STOPPED": vc.get("STOPPED", 0) / n,
        "DEAD_MONEY": vc.get("DEAD_MONEY", 0) / n,
        "CUSHIONED": vc.get("CUSHIONED", 0) / n,
        "CLEAN_LIFTOFF": vc.get("CLEAN_LIFTOFF", 0) / n,
        "n": n,
    }

# ── 4. Both-halves split (verbatim) ───────────────────────────────────────────
dates_sorted = np.sort(vg_fires['signal_date'].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
half1 = vg_fires[vg_fires['signal_date'] <= midpoint]
half2 = vg_fires[vg_fires['signal_date'] > midpoint]
print(f"Both-halves split: midpoint={midpoint} | H1 n={len(half1):,} | H2 n={len(half2):,}")
print()

# ── 5. Trial config (subset of original TRIAL_GRID) ───────────────────────────
HORIZON_CONFIG = {21: ("fwd_ret_21", "state_8_21"), 63: ("fwd_ret_63", "state_15_126")}

# Full trial grid (for context; we only run TARGET_TRIALS)
FULL_TRIAL_GRID = [
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
TRIAL_MAP = {t[0]: t for t in FULL_TRIAL_GRID}

FACTORS_HG = {
    "F1": {"pass_col": "F1_pass", "valid_mask": None},
    "F2": {"pass_col": "F2_pass", "valid_mask": "F2_valid"},
    "F3": {"pass_col": "F3_pass", "valid_mask": None},
}
FACTORS_RW = {"F1": "F1_moved_up", "F2": "F2_moved_up", "F3": "F3_moved_up"}

# ── 6. REPRODUCTION GATE ──────────────────────────────────────────────────────
print("─" * 72)
print("REPRODUCTION GATE: recompute cohort counts + ts_rates for target trials")
print("─" * 72)
print()

# Load original results for comparison
ORIG_RESULTS_PATH = Path(__file__).parents[1] / "P1_3" / "results.json"
assert ORIG_RESULTS_PATH.exists(), f"BLOCKER: original results.json not found at {ORIG_RESULTS_PATH}"
with open(ORIG_RESULTS_PATH) as fh:
    orig = json.load(fh)

repro_failures = []
repro_rows = {}

for tid in TARGET_TRIALS:
    _, factor, mode, horizon, ts_target = TRIAL_MAP[tid]
    fwd_col, state_col = HORIZON_CONFIG[horizon]

    if mode == "HG":
        cfg = FACTORS_HG[factor]
        pass_col = cfg["pass_col"]
        valid_mask_col = cfg.get("valid_mask")
        pop = vg_fires[vg_fires[valid_mask_col]].copy() if valid_mask_col else vg_fires.copy()
        a_mask = (pop[pass_col] == True).values
    else:
        moved_col = FACTORS_RW[factor]
        pop = vg_fires.copy()
        a_mask = (pop[moved_col] == True).values

    group_A = pop[a_mask]
    group_B = pop[~a_mask]
    n_A = len(group_A)
    n_B = len(group_B)
    n_ep_A = group_A['episode_id'].nunique()
    n_ep_B = group_B['episode_id'].nunique()
    ts_A = terminal_state_rates(group_A, state_col)
    ts_B = terminal_state_rates(group_B, state_col)
    ts_rate_A = ts_A.get(ts_target, np.nan)
    ts_rate_B = ts_B.get(ts_target, np.nan)
    delta_pp = (ts_rate_A - ts_rate_B) * 100

    ot = orig["trials"][tid]

    # Check counts within 2% tolerance
    def pct_diff(a, b):
        if b == 0:
            return 0.0 if a == 0 else float('inf')
        return abs(a - b) / abs(b) * 100

    checks = {
        "n_A": (n_A, ot["n_A"], pct_diff(n_A, ot["n_A"])),
        "n_B": (n_B, ot["n_B"], pct_diff(n_B, ot["n_B"])),
        "n_ep_A": (n_ep_A, ot["n_ep_A"], pct_diff(n_ep_A, ot["n_ep_A"])),
        "n_ep_B": (n_ep_B, ot["n_ep_B"], pct_diff(n_ep_B, ot["n_ep_B"])),
        "ts_rate_A": (ts_rate_A, ot["ts_rate_A"], pct_diff(ts_rate_A, ot["ts_rate_A"])),
        "ts_rate_B": (ts_rate_B, ot["ts_rate_B"], pct_diff(ts_rate_B, ot["ts_rate_B"])),
    }

    trial_ok = True
    print(f"  {tid} ({factor} {mode} {horizon}d {ts_target}):")
    for metric, (got, exp, diff) in checks.items():
        status = "OK" if diff <= 2.0 else "DRIFT"
        print(f"    {metric}: got={got} orig={exp} diff={diff:.3f}% [{status}]")
        if status == "DRIFT":
            trial_ok = False
            repro_failures.append(f"{tid}.{metric}: got={got} orig={exp} diff={diff:.2f}%")

    repro_rows[tid] = {
        "pop": pop, "a_mask": a_mask, "group_A": group_A, "group_B": group_B,
        "n_A": n_A, "n_B": n_B, "n_ep_A": n_ep_A, "n_ep_B": n_ep_B,
        "ts_rate_A": ts_rate_A, "ts_rate_B": ts_rate_B,
        "delta_pp": delta_pp, "ts_target": ts_target,
        "factor": factor, "mode": mode, "horizon": horizon,
        "fwd_col": fwd_col, "state_col": state_col,
    }
    print(f"    delta_pp: {delta_pp:+.4f}pp (orig: {ot['delta_pp']:+.4f}pp)")
    print(f"    STATUS: {'OK' if trial_ok else 'DRIFT'}")
    print()

if repro_failures:
    note = "REPRODUCTION GATE FAILED — cohort counts drifted >2%:\n" + "\n".join(repro_failures)
    print(note)
    (OUT_DIR / "WIP_BLOCKED.md").write_text(f"# WIP-BLOCKED\n\n{note}\n")
    sys.exit(1)

print("REPRODUCTION GATE: PASS — all counts within 2% of original")
print()

# ── 7. New primary inference: within-month demeaning + month-block bootstrap ──

def build_episode_table(pop, a_mask):
    """
    Build episode-level table with:
      - episode_id
      - arm (A=True / B=False)
      - outcome (ts binary indicator per ts_target, one value per episode)
      - month (YYYY-MM of episode's first signal_date)
    For ts, we assign the modal terminal state per episode (should be pure by design).
    """
    popdf = pop.copy()
    popdf['_arm_A'] = a_mask
    return popdf


def month_demean_outcomes(pop_df, a_mask, state_col, ts_target):
    """
    Episode-level within-month demeaning.

    Steps:
    1. One row per episode: assign arm, ts_binary, and calendar month from first signal_date.
    2. Compute within-month mean of ts_binary pooled across both arms.
    3. Demean: ts_demeaned = ts_binary - month_mean.
    4. Return episode-level DataFrame with columns:
       episode_id, arm_A, ts_binary, month, month_mean, ts_demeaned
    """
    pdf = pop_df.copy()
    pdf['_arm_A'] = a_mask
    pdf['_ts_binary'] = (pdf[state_col] == ts_target).astype(float)

    # Episode-level aggregation: min signal_date (earliest), arm, ts_binary modal value
    # (within-episode purity asserted in original study; ts_binary is row-level,
    #  but arm is per-episode — we aggregate arm and ts_binary at episode level)
    ep_df = pdf.groupby('episode_id').agg(
        first_signal_date=('signal_date', 'min'),  # min = earliest date in episode
        arm_A=('_arm_A', 'first'),     # per-episode arm (constant by design)
        ts_binary=('_ts_binary', 'mean'),  # mean within episode (should be near 0 or 1)
    ).reset_index()

    # Calendar month
    ep_df['month'] = ep_df['first_signal_date'].dt.to_period('M').dt.to_timestamp()

    # Within-month mean (pooled across both arms)
    month_means = ep_df.groupby('month')['ts_binary'].mean().rename('month_mean')
    ep_df = ep_df.merge(month_means, on='month', how='left')

    # Demeaned outcome
    ep_df['ts_demeaned'] = ep_df['ts_binary'] - ep_df['month_mean']

    return ep_df


def month_block_bootstrap(ep_df, n_boot=N_BOOT, seed=SEED):
    """
    Resample calendar months with replacement; all episodes of a drawn month
    (both arms) move together. Recompute delta_tc per replicate.

    Returns: (delta_tc_obs, boot_deltas, n_months, month_counts)
    """
    months = ep_df['month'].unique()
    n_months = len(months)
    month_to_idx = {m: i for i, m in enumerate(months)}
    ep_df = ep_df.copy()
    ep_df['_midx'] = ep_df['month'].map(month_to_idx)

    # Observed delta_tc
    ep_A = ep_df[ep_df['arm_A']]
    ep_B = ep_df[~ep_df['arm_A']]
    delta_tc_obs = ep_A['ts_demeaned'].mean() - ep_B['ts_demeaned'].mean()

    # Pre-group by month index for fast bootstrap
    # For each month index: arrays of (arm_A, ts_demeaned)
    month_arms = {}
    month_dem = {}
    for midx in range(n_months):
        mask = ep_df['_midx'] == midx
        month_arms[midx] = ep_df.loc[mask, 'arm_A'].values
        month_dem[midx] = ep_df.loc[mask, 'ts_demeaned'].values

    rng = np.random.default_rng(seed)
    boot_deltas = np.empty(n_boot, dtype=float)

    for b in range(n_boot):
        drawn = rng.integers(0, n_months, size=n_months)
        # Concatenate all episodes from drawn months
        all_arms = np.concatenate([month_arms[m] for m in drawn])
        all_dem = np.concatenate([month_dem[m] for m in drawn])

        a_sel = all_arms.astype(bool)
        n_a_b = a_sel.sum()
        n_b_b = (~a_sel).sum()
        if n_a_b == 0 or n_b_b == 0:
            boot_deltas[b] = np.nan
            continue
        boot_deltas[b] = all_dem[a_sel].mean() - all_dem[~a_sel].mean()

    return float(delta_tc_obs), boot_deltas, n_months, months


def compute_tc_stats(delta_tc_obs, boot_deltas, favorable_sign_positive):
    """
    95% CI from percentile method; one-sided p (unfavorable side).
    favorable_sign_positive: True if positive delta is favorable.
    """
    valid = boot_deltas[~np.isnan(boot_deltas)]
    ci_lo = float(np.percentile(valid, 2.5))
    ci_hi = float(np.percentile(valid, 97.5))

    if favorable_sign_positive:
        # Favorable is positive; unfavorable is <= 0
        p_one_sided = float((valid <= 0).mean())
    else:
        # Favorable is negative; unfavorable is >= 0
        p_one_sided = float((valid >= 0).mean())

    return ci_lo, ci_hi, p_one_sided, len(valid)


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


# ── 8. Run main TC inference ───────────────────────────────────────────────────
print("─" * 72)
print(f"TC INFERENCE (n_boot={N_BOOT}, seed={SEED}, BH q={BH_Q}, family m=5)")
print("─" * 72)
print()

tc_results = {}

for tid in TARGET_TRIALS:
    row = repro_rows[tid]
    pop = row['pop']
    a_mask = row['a_mask']
    ts_target = row['ts_target']
    state_col = row['state_col']
    fwd_col = row['fwd_col']
    factor = row['factor']
    mode = row['mode']
    horizon = row['horizon']
    delta_pp_orig = row['delta_pp']

    # Favorable sign: STOPPED/DEAD_MONEY -> negative delta favorable; CUSHIONED -> positive
    if ts_target in ("STOPPED", "DEAD_MONEY"):
        favorable_sign_positive = False
    else:
        favorable_sign_positive = True

    # Build episode table with demeaning
    ep_df = month_demean_outcomes(pop, a_mask, state_col, ts_target)

    # Coverage diagnostics
    n_months = ep_df['month'].nunique()
    monthly_counts = ep_df.groupby(['month', 'arm_A']).size().unstack(fill_value=0)
    # episodes per month per arm
    if True in monthly_counts.columns and False in monthly_counts.columns:
        arm_A_counts = monthly_counts[True]
        arm_B_counts = monthly_counts[False]
        min_A = int(arm_A_counts.min())
        med_A = float(arm_A_counts.median())
        max_A = int(arm_A_counts.max())
        min_B = int(arm_B_counts.min())
        med_B = float(arm_B_counts.median())
        max_B = int(arm_B_counts.max())
    else:
        min_A = med_A = max_A = min_B = med_B = max_B = np.nan

    # Main bootstrap
    delta_tc_obs, boot_deltas, n_months_used, months_arr = month_block_bootstrap(
        ep_df, n_boot=N_BOOT, seed=SEED
    )
    ci_lo, ci_hi, p_onesided, n_valid_boots = compute_tc_stats(
        delta_tc_obs, boot_deltas, favorable_sign_positive
    )
    delta_tc_pp = delta_tc_obs * 100
    ci_lo_pp = ci_lo * 100
    ci_hi_pp = ci_hi * 100

    # Per-half demeaned delta
    half_tc_deltas = []
    for half_data in [half1, half2]:
        if mode == "HG":
            cfg = FACTORS_HG[factor]
            pass_col = cfg["pass_col"]
            valid_mask_col = cfg.get("valid_mask")
            hp = half_data[half_data[valid_mask_col]].copy() if valid_mask_col else half_data.copy()
            ha_mask = (hp[pass_col] == True).values
        else:
            moved_col = FACTORS_RW[factor]
            hp = half_data.copy()
            ha_mask = (hp[moved_col] == True).values

        if ha_mask.sum() == 0 or (~ha_mask).sum() == 0:
            half_tc_deltas.append(np.nan)
            continue

        hep_df = month_demean_outcomes(hp, ha_mask, state_col, ts_target)
        hep_A = hep_df[hep_df['arm_A']]
        hep_B = hep_df[~hep_df['arm_A']]
        if len(hep_A) == 0 or len(hep_B) == 0:
            half_tc_deltas.append(np.nan)
        else:
            half_tc_deltas.append(float((hep_A['ts_demeaned'].mean() - hep_B['ts_demeaned'].mean()) * 100))

    tc_results[tid] = {
        "trial_id": tid,
        "factor": factor, "mode": mode, "horizon": horizon, "ts_target": ts_target,
        "n_A": row['n_A'], "n_B": row['n_B'],
        "n_ep_A": row['n_ep_A'], "n_ep_B": row['n_ep_B'],
        "ts_rate_A": row['ts_rate_A'], "ts_rate_B": row['ts_rate_B'],
        "delta_pp_orig": delta_pp_orig,
        "delta_tc_pp": delta_tc_pp,
        "ci_lo_pp": ci_lo_pp, "ci_hi_pp": ci_hi_pp,
        "p_onesided": p_onesided,
        "favorable_sign_positive": favorable_sign_positive,
        "n_months": n_months_used,
        "n_boots_valid": n_valid_boots,
        "coverage": {
            "n_months": n_months_used,
            "arm_A_min": min_A, "arm_A_median": med_A, "arm_A_max": max_A,
            "arm_B_min": min_B, "arm_B_median": med_B, "arm_B_max": max_B,
        },
        "half1_tc_delta_pp": half_tc_deltas[0],
        "half2_tc_delta_pp": half_tc_deltas[1],
        # BH filled in below
        "bh_adj_p": np.nan,
    }

    print(f"  {tid}: {factor} {mode} {horizon}d {ts_target}")
    print(f"    orig delta_pp = {delta_pp_orig:+.4f}pp")
    print(f"    delta_tc     = {delta_tc_pp:+.4f}pp  95%CI=[{ci_lo_pp:+.4f}, {ci_hi_pp:+.4f}]pp")
    print(f"    p_one_sided  = {p_onesided:.4f}  (fav_sign={'pos' if favorable_sign_positive else 'neg'})")
    print(f"    coverage: {n_months_used} months | arm_A min/med/max={min_A}/{med_A:.1f}/{max_A} | arm_B {min_B}/{med_B:.1f}/{max_B}")
    print(f"    half1_tc={half_tc_deltas[0]:+.4f}pp  half2_tc={half_tc_deltas[1]:+.4f}pp")
    print()

# ── 9. BH-FDR across m=5 re-check family ──────────────────────────────────────
p_vals = [tc_results[tid]['p_onesided'] for tid in TARGET_TRIALS]
bh_adjs = bh_correction(p_vals, q=BH_Q)
for i, tid in enumerate(TARGET_TRIALS):
    tc_results[tid]['bh_adj_p'] = float(bh_adjs[i])

print("─" * 72)
print("BH-FDR across m=5 re-check family (q=0.10) — SEPARATE from original m=30")
print("─" * 72)
for tid in TARGET_TRIALS:
    r = tc_results[tid]
    print(f"  {tid}: p_one_sided={r['p_onesided']:.4f}  BH_adj={r['bh_adj_p']:.4f}")
print()

# ── 10. CALIBRATION CONTROLS ──────────────────────────────────────────────────
print("─" * 72)
print("CALIBRATION CONTROLS")
print("─" * 72)
print()

# C-A: Within-month cross-episode label permutation (DT-R14-matched null)
# Use T02 (the internal positive control) as the test bed
print("C-A: Within-month label permutation null (DT-R14-matched; N_PERM_CA=2000)")
print("     Shuffle arm labels across episodes WITHIN each month; expect null CI covers 0")
print()

t02_row = repro_rows['T02']
t02_ep_df = month_demean_outcomes(t02_row['pop'], t02_row['a_mask'], t02_row['state_col'], t02_row['ts_target'])

ca_rng = np.random.default_rng(777)
ca_deltas = np.empty(N_PERM_CA, dtype=float)

# Pre-group episodes by month for fast permutation
t02_months = t02_ep_df['month'].unique()
month_groups = {m: t02_ep_df[t02_ep_df['month'] == m] for m in t02_months}

for k in range(N_PERM_CA):
    perm_rows = []
    for m, mg in month_groups.items():
        mg2 = mg.copy()
        # Shuffle arm labels within month
        shuffled_arms = ca_rng.permutation(mg2['arm_A'].values)
        mg2 = mg2.copy()
        mg2['arm_A'] = shuffled_arms
        perm_rows.append(mg2)
    perm_df = pd.concat(perm_rows, ignore_index=True)
    ep_A_p = perm_df[perm_df['arm_A']]
    ep_B_p = perm_df[~perm_df['arm_A']]
    if len(ep_A_p) == 0 or len(ep_B_p) == 0:
        ca_deltas[k] = np.nan
        continue
    ca_deltas[k] = float(ep_A_p['ts_demeaned'].mean() - ep_B_p['ts_demeaned'].mean())

ca_valid = ca_deltas[~np.isnan(ca_deltas)]
ca_null_mean = float(ca_valid.mean())
ca_ci_lo = float(np.percentile(ca_valid, 2.5))
ca_ci_hi = float(np.percentile(ca_valid, 97.5))

# What percentile is observed |delta_tc| in the null distribution?
t02_obs_delta = tc_results['T02']['delta_tc_pp'] / 100.0  # back to fraction
obs_abs = abs(t02_obs_delta)
null_abs = np.abs(ca_valid)
ca_pctile = float((null_abs <= obs_abs).mean() * 100)

print(f"  T02 observed |delta_tc| = {obs_abs*100:.4f}pp")
print(f"  Null distribution (within-month perm):  mean={ca_null_mean*100:+.4f}pp  "
      f"95%CI=[{ca_ci_lo*100:+.4f}, {ca_ci_hi*100:+.4f}]pp")
print(f"  Observed |delta_tc| at {ca_pctile:.1f}th percentile of null |delta_tc|")
print(f"  (CI should cover 0 under null — this is a shape diagnostic, not a test)")
print()

ca_summary = {
    "trial_used": "T02",
    "n_perm": N_PERM_CA,
    "null_mean_pp": ca_null_mean * 100,
    "null_ci_lo_pp": ca_ci_lo * 100,
    "null_ci_hi_pp": ca_ci_hi * 100,
    "obs_abs_delta_tc_pp": obs_abs * 100,
    "obs_pctile_in_null": ca_pctile,
}

# C-B: Positive injection — add +2pp to arm A outcomes of T18; confirm CI excludes 0
print("C-B: Positive injection — add +2pp to arm A outcomes of T18; expect CI excludes 0")
print()

t18_row = repro_rows['T18']
t18_state_col = t18_row['state_col']
t18_ts_target = t18_row['ts_target']  # CUSHIONED
t18_a_mask = t18_row['a_mask']

# Build the normal episode-level table for T18, then inject +2pp on arm A episodes
# Working at the EPISODE level (after aggregation) avoids row-level binary clipping issues.
t18_ep_df_base = month_demean_outcomes(t18_row['pop'], t18_a_mask, t18_state_col, t18_ts_target)

# Inject +0.02 to ts_binary on arm A episodes, then recompute month means and demean
t18_ep_df_inj = t18_ep_df_base.copy()
t18_ep_df_inj.loc[t18_ep_df_inj['arm_A'], 'ts_binary'] = (
    t18_ep_df_inj.loc[t18_ep_df_inj['arm_A'], 'ts_binary'] + 0.02
).clip(0, 1)

month_means_inj = t18_ep_df_inj.groupby('month')['ts_binary'].mean().rename('month_mean')
t18_ep_df_inj = t18_ep_df_inj.drop(columns=['month_mean', 'ts_demeaned'])
t18_ep_df_inj = t18_ep_df_inj.merge(month_means_inj, on='month', how='left')
t18_ep_df_inj['ts_demeaned'] = t18_ep_df_inj['ts_binary'] - t18_ep_df_inj['month_mean']

delta_tc_inj, boot_deltas_inj, _, _ = month_block_bootstrap(
    t18_ep_df_inj, n_boot=N_BOOT, seed=SEED
)
ci_lo_inj, ci_hi_inj, p_inj, n_inj_valid = compute_tc_stats(
    delta_tc_inj, boot_deltas_inj, favorable_sign_positive=True  # CUSHIONED = positive
)

cb_detects = (ci_lo_inj > 0) or (ci_hi_inj < 0)  # CI excludes zero

print(f"  Injected +2pp to arm A outcomes of T18 (CUSHIONED)")
print(f"  delta_tc_injected = {delta_tc_inj*100:+.4f}pp")
print(f"  95%CI = [{ci_lo_inj*100:+.4f}, {ci_hi_inj*100:+.4f}]pp")
print(f"  CI excludes 0: {cb_detects}")
print()

cb_summary = {
    "trial_used": "T18",
    "injection_pp": 2.0,
    "delta_tc_injected_pp": delta_tc_inj * 100,
    "ci_lo_pp": ci_lo_inj * 100,
    "ci_hi_pp": ci_hi_inj * 100,
    "p_one_sided": float(p_inj),
    "ci_excludes_zero": bool(cb_detects),
}

calibration_summary = {
    "C_A_within_month_label_perm": ca_summary,
    "C_B_positive_injection": cb_summary,
}

# ── 11. Save results.json ──────────────────────────────────────────────────────
def _clean(v):
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        fv = float(v)
        if np.isnan(fv):
            return None
        return fv
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v

def clean_dict(d):
    return {k: _clean(v) if not isinstance(v, dict) else clean_dict(v)
            for k, v in d.items()}

results_out = {
    "study_id": STUDY_ID,
    "recheck_date": "2026-07-07",
    "source_study": "P1_3",
    "note": "RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.",
    "method": "within-month demeaning + month-block bootstrap (DT-R14 calendar-time controls)",
    "n_boot": N_BOOT,
    "n_perm_ca": N_PERM_CA,
    "seed": SEED,
    "bh_q": BH_Q,
    "bh_family_m": 5,
    "bh_note": "Separate family from original m=30",
    "replay_path": str(REPLAY_PATH),
    "replay_md5": replay_hash,
    "date_window": f"{DATE_MIN.date()} -> {DATE_MAX.date()}",
    "population": {
        "n_fires_verdict_grade": n_fires_total,
        "n_episode_clusters": n_ep_clusters,
        "era_min": str(era_min),
        "era_max": str(era_max),
    },
    "target_trials": TARGET_TRIALS,
    "reproduction_gate": "PASS",
    "trials": {tid: clean_dict(v) for tid, v in tc_results.items()},
    "calibration": calibration_summary,
    "midpoint_split": str(midpoint),
    "n_half1": int(len(half1)),
    "n_half2": int(len(half2)),
}

with open(OUT_DIR / "results.json", "w") as fh:
    json.dump(results_out, fh, indent=2, default=str)
print(f"Saved: {OUT_DIR / 'results.json'}")

# ── 12. Emit summary for RESULTS.md writer ────────────────────────────────────
print()
print("─" * 72)
print("SUMMARY FOR RESULTS.md")
print("─" * 72)
print()
print(f"{'Trial':<6} {'Factor':<7} {'Mode':<4} {'H':<4} {'TS':<12} "
      f"{'Orig_Δ':>8} {'Orig_p':>7} {'Orig_BH':>8} | "
      f"{'TC_Δ':>8} {'95%CI_lo':>9} {'95%CI_hi':>9} {'p_1s':>7} {'BH_tc':>7}")
print("-" * 110)

orig_trials = orig['trials']
for tid in TARGET_TRIALS:
    r = tc_results[tid]
    ot = orig_trials[tid]
    print(f"{tid:<6} {r['factor']:<7} {r['mode']:<4} {r['horizon']:<4} {r['ts_target']:<12} "
          f"{ot['delta_pp']:>+8.2f} {ot['perm_p']:>7.4f} {ot['bh_adj_p']:>8.4f} | "
          f"{r['delta_tc_pp']:>+8.2f} {r['ci_lo_pp']:>+9.2f} {r['ci_hi_pp']:>+9.2f} "
          f"{r['p_onesided']:>7.4f} {r['bh_adj_p']:>7.4f}")

print()
print("Calibration:")
print(f"  C-A null mean={ca_summary['null_mean_pp']:+.4f}pp  "
      f"95%CI=[{ca_summary['null_ci_lo_pp']:+.4f}, {ca_summary['null_ci_hi_pp']:+.4f}]pp  "
      f"obs T02 |delta_tc| at {ca_summary['obs_pctile_in_null']:.1f}th pctile of null")
print(f"  C-B injection: delta_tc={cb_summary['delta_tc_injected_pp']:+.4f}pp  "
      f"CI=[{cb_summary['ci_lo_pp']:+.4f}, {cb_summary['ci_hi_pp']:+.4f}]pp  "
      f"CI_excludes_0={cb_summary['ci_excludes_zero']}")

print()
print("=" * 72)
print("EI-RC-1 RUN COMPLETE")
print("=" * 72)

# ── 13. Write RESULTS.md ──────────────────────────────────────────────────────
md_lines = [
    "**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**",
    "",
    "# EI-RC-1: P1.3 Trials — Within-Month Demeaning + Month-Block Bootstrap",
    "",
    f"Study date: 2026-07-07  |  Source: P1_3 (2026-07-05)  |  n_boot={N_BOOT} seed={SEED}",
    f"Date window: {DATE_MIN.date()} → {DATE_MAX.date()}",
    f"Population: {n_fires_total:,} verdict-grade fires | {n_ep_clusters:,} episode clusters",
    f"BH family: m=5 (this re-check family only; separate from original m=30)",
    "",
    "## Population",
    "",
    f"- Verdict-grade fires: {n_fires_total:,}",
    f"- Episode clusters (unique): {n_ep_clusters:,}",
    f"- Era: {era_min.date()} → {era_max.date()}",
    f"- Both-halves split midpoint: {pd.Timestamp(midpoint).date()} | H1 n={len(half1):,} | H2 n={len(half2):,}",
    "",
    "## Reproduction Gate",
    "",
    "All cohort counts within 2% of original P1_3/results.json. Gate: **PASS**.",
    "",
    "## Primary Results: Side-by-Side",
    "",
    "| Trial | Factor | Mode | H | TS | Orig Δ (pp) | Orig perm_p | Orig BH_adj | TC Δ (pp) | 95% CI lo | 95% CI hi | exact p | BH_tc | H1_tc (pp) | H2_tc (pp) |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
]

for tid in TARGET_TRIALS:
    r = tc_results[tid]
    ot = orig_trials[tid]
    h1 = f"{r['half1_tc_delta_pp']:+.2f}" if r['half1_tc_delta_pp'] is not None else "N/A"
    h2 = f"{r['half2_tc_delta_pp']:+.2f}" if r['half2_tc_delta_pp'] is not None else "N/A"
    md_lines.append(
        f"| {tid} | {r['factor']} | {r['mode']} | {r['horizon']}d | {r['ts_target']} "
        f"| {ot['delta_pp']:+.2f} | {ot['perm_p']:.4f} | {ot['bh_adj_p']:.4f} "
        f"| {r['delta_tc_pp']:+.2f} | {r['ci_lo_pp']:+.2f} | {r['ci_hi_pp']:+.2f} "
        f"| {r['p_onesided']:.4f} | {r['bh_adj_p']:.4f} | {h1} | {h2} |"
    )

md_lines += [
    "",
    "**Interpretation key:** TC Δ = time-controlled delta (within-month demeaned, pp). "
    "95% CI from month-block percentile bootstrap. exact p = one-sided fraction of replicates "
    "on the unfavorable side of zero. BH_tc = BH-adjusted q across m=5 re-check family.",
    "",
    "## Coverage Stamps",
    "",
    "| Trial | N months | Arm A min/med/max ep | Arm B min/med/max ep |",
    "|---|---|---|---|",
]

for tid in TARGET_TRIALS:
    r = tc_results[tid]
    cov = r['coverage']
    arm_a = f"{cov['arm_A_min']}/{cov['arm_A_median']:.1f}/{cov['arm_A_max']}"
    arm_b = f"{cov['arm_B_min']}/{cov['arm_B_median']:.1f}/{cov['arm_B_max']}"
    md_lines.append(f"| {tid} | {cov['n_months']} | {arm_a} | {arm_b} |")

md_lines += [
    "",
    "## Calibration Controls",
    "",
    "### C-A: Within-Month Label Permutation (DT-R14-matched null, N=2000)",
    "",
    f"- Trial used: T02 (internal positive control — large, half-stable effect)",
    f"- Null mean: {ca_summary['null_mean_pp']:+.4f} pp",
    f"- Null 95% CI: [{ca_summary['null_ci_lo_pp']:+.4f}, {ca_summary['null_ci_hi_pp']:+.4f}] pp",
    f"- Observed |delta_tc| at {ca_summary['obs_pctile_in_null']:.1f}th percentile of null |delta_tc|",
    f"- Expected: CI covers 0 (shape diagnostic); observed well above null range if T02 is real.",
    "",
    "### C-B: Positive Injection (+2pp arm A on T18)",
    "",
    f"- Injected +0.02 to arm A episode ts_binary; recomputed month demean + bootstrap",
    f"- delta_tc after injection: {cb_summary['delta_tc_injected_pp']:+.4f} pp",
    f"- 95% CI: [{cb_summary['ci_lo_pp']:+.4f}, {cb_summary['ci_hi_pp']:+.4f}] pp",
    f"- CI excludes 0: **{cb_summary['ci_excludes_zero']}**  (expected: True)",
    "",
    "## Notes",
    "",
    "- Results are purely descriptive re-checks under DT-R14 calendar-time controls.",
    "- The word 'validated' does not appear in this document.",
    "- No verdict from original P1_3 is overturned here. Adjudication is Fable-tier.",
    "- Original perm_p and bh_adj_p are from the m=30 family; BH_tc is from this m=5 re-check family.",
    "- Favorable sign for STOPPED/DEAD_MONEY = negative delta (would-pass arm has fewer bad outcomes);",
    "  for CUSHIONED = positive delta.",
    f"- Replay MD5: {replay_hash}",
]

results_md = "\n".join(md_lines) + "\n"
md_path = OUT_DIR / "RESULTS.md"
md_path.write_text(results_md)
print(f"Saved: {md_path}")

# Store key variables for RESULTS.md writing (imported externally)
_TC_RESULTS = tc_results
_CALIBRATION = calibration_summary
_ORIG_TRIALS = orig_trials
_POPULATION = results_out["population"]
