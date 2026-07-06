"""
P1.3 Batch runner — processes a specified range of trials and saves partial results.
Usage: python3 run_batch.py <start_idx> <end_idx>
  start_idx: 0-based index into TRIAL_GRID (inclusive)
  end_idx: 0-based index into TRIAL_GRID (exclusive)
"""

import sys
import json
import numpy as np
import pandas as pd
import scipy
from scipy import stats
from pathlib import Path

REPO = Path(__file__).parents[4]
REPLAY_PATH = REPO / "data" / "replay" / "replay_boarded.parquet"
OUT_DIR = Path(__file__).parent

N_BOOT = 5000
BH_Q = 0.10
THIN_FLOOR = 25

# ── Trial grid ─────────────────────────────────────────────────────────────────
TRIAL_GRID = [
    ("T01", "F1", "HG", 21, "STOPPED"),
    ("T02", "F1", "HG", 21, "DEAD_MONEY"),
    ("T03", "F1", "HG", 21, "CUSHIONED"),
    ("T04", "F1", "HG", 63, "STOPPED"),
    ("T05", "F1", "HG", 63, "DEAD_MONEY"),
    ("T06", "F1", "HG", 63, "CUSHIONED"),
    ("T07", "F1", "RW", 21, "STOPPED"),
    ("T08", "F1", "RW", 21, "CUSHIONED"),
    ("T09", "F1", "RW", 63, "STOPPED"),
    ("T10", "F1", "RW", 63, "CUSHIONED"),
    ("T11", "F2", "HG", 21, "STOPPED"),
    ("T12", "F2", "HG", 21, "DEAD_MONEY"),
    ("T13", "F2", "HG", 21, "CUSHIONED"),
    ("T14", "F2", "HG", 63, "STOPPED"),
    ("T15", "F2", "HG", 63, "DEAD_MONEY"),
    ("T16", "F2", "HG", 63, "CUSHIONED"),
    ("T17", "F2", "RW", 21, "STOPPED"),
    ("T18", "F2", "RW", 21, "CUSHIONED"),
    ("T19", "F2", "RW", 63, "STOPPED"),
    ("T20", "F2", "RW", 63, "CUSHIONED"),
    ("T21", "F3", "HG", 21, "STOPPED"),
    ("T22", "F3", "HG", 21, "DEAD_MONEY"),
    ("T23", "F3", "HG", 21, "CUSHIONED"),
    ("T24", "F3", "HG", 63, "STOPPED"),
    ("T25", "F3", "HG", 63, "DEAD_MONEY"),
    ("T26", "F3", "HG", 63, "CUSHIONED"),
    ("T27", "F3", "RW", 21, "STOPPED"),
    ("T28", "F3", "RW", 21, "CUSHIONED"),
    ("T29", "F3", "RW", 63, "STOPPED"),
    ("T30", "F3", "RW", 63, "CUSHIONED"),
]

start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
end_idx = int(sys.argv[2]) if len(sys.argv) > 2 else len(TRIAL_GRID)
batch_trials = TRIAL_GRID[start_idx:end_idx]
print(f"Batch {start_idx}:{end_idx} — {len(batch_trials)} trials: {[t[0] for t in batch_trials]}")

# ── Load data ──────────────────────────────────────────────────────────────────
df = pd.read_parquet(REPLAY_PATH)
vg_fires = df[(df['verdict_type'] == 'fire') & (df['verdict_grade'] == True)].copy()

HORIZON_CONFIG = {21: ("fwd_ret_21", "state_8_21"), 63: ("fwd_ret_63", "state_15_126")}

# Build factor columns
vg_fires['F1_pass'] = vg_fires['washout_proximity'].astype(bool)
vg_fires['F2_pass'] = vg_fires['rs_sector_quartile'].isin([2.0, 3.0])
vg_fires['F2_valid'] = vg_fires['rs_sector_quartile'].notna()
vg_fires['F3_pass'] = vg_fires['ext_z'] <= 2.0

# Incumbent rank score normalized
w_min, w_max = vg_fires['weight'].min(), vg_fires['weight'].max()
vg_fires['base_rank'] = (vg_fires['weight'] - w_min) / (w_max - w_min)

# Bonuses
vg_fires['F1_bonus'] = np.where(vg_fires['F1_pass'], 0.10, 0.0)
vg_fires['F2_bonus'] = np.where(vg_fires['F2_pass'] & vg_fires['F2_valid'], 0.10, 0.0)
vg_fires['F3_bonus'] = np.maximum(0.0, (2.0 - vg_fires['ext_z']) / 2.0) * 0.10

for fx, bcol in [('F1', 'F1_bonus'), ('F2', 'F2_bonus'), ('F3', 'F3_bonus')]:
    vg_fires[f'{fx}_rw_score'] = vg_fires['base_rank'] + vg_fires[bcol]
    vg_fires[f'{fx}_rank_before'] = vg_fires.groupby('signal_date')['base_rank'].rank(method='first', ascending=True)
    vg_fires[f'{fx}_rank_after'] = vg_fires.groupby('signal_date')[f'{fx}_rw_score'].rank(method='first', ascending=True)
    vg_fires[f'{fx}_moved_up'] = vg_fires[f'{fx}_rank_after'] > vg_fires[f'{fx}_rank_before']

# Both-halves split
dates_sorted = np.sort(vg_fires['signal_date'].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
half1 = vg_fires[vg_fires['signal_date'] <= midpoint]
half2 = vg_fires[vg_fires['signal_date'] > midpoint]

# ── Bootstrap function ─────────────────────────────────────────────────────────
def _u_stat(a, b):
    return float(np.searchsorted(np.sort(b), a, side='left').sum())


def episode_bootstrap_mwu(arr_a, arr_b, ep_a, ep_b, n_boot=N_BOOT, rng_seed=42):
    rng = np.random.default_rng(rng_seed)
    if len(arr_a) == 0 or len(arr_b) == 0:
        return np.nan, np.nan, np.nan, np.nan

    stat_u, param_p = stats.mannwhitneyu(arr_a, arr_b, alternative='two-sided')
    n_a, n_b = len(arr_a), len(arr_b)
    r = 1.0 - (2.0 * stat_u) / (n_a * n_b)

    unique_ep_a, ep_a_idx = np.unique(ep_a, return_inverse=True)
    unique_ep_b, ep_b_idx = np.unique(ep_b, return_inverse=True)
    n_ep_a = len(unique_ep_a)
    n_ep_b = len(unique_ep_b)

    ep_a_row_lists = [np.where(ep_a_idx == k)[0] for k in range(n_ep_a)]
    ep_b_row_lists = [np.where(ep_b_idx == k)[0] for k in range(n_ep_b)]

    obs_u = _u_stat(arr_a, arr_b)
    expected_u = float(n_a) * n_b / 2.0

    boot_us = np.empty(n_boot)
    for i in range(n_boot):
        samp_a = rng.integers(0, n_ep_a, size=n_ep_a)
        samp_b = rng.integers(0, n_ep_b, size=n_ep_b)
        rows_a = np.concatenate([ep_a_row_lists[k] for k in samp_a])
        rows_b = np.concatenate([ep_b_row_lists[k] for k in samp_b])
        boot_a = arr_a[rows_a]
        boot_b = arr_b[rows_b]
        boot_us[i] = _u_stat(boot_a, boot_b) if (len(boot_a) > 0 and len(boot_b) > 0) else obs_u

    obs_dev = abs(obs_u - expected_u)
    boot_p = float((np.abs(boot_us - expected_u) >= obs_dev).mean())
    boot_p = max(boot_p, 1.0 / n_boot)
    return stat_u, param_p, boot_p, r


def terminal_state_rates(data, state_col):
    n = len(data)
    if n == 0:
        return {"STOPPED": np.nan, "DEAD_MONEY": np.nan, "CUSHIONED": np.nan, "CLEAN_LIFTOFF": np.nan, "n": 0}
    vc = data[state_col].value_counts()
    return {s: vc.get(s, 0) / n for s in ("STOPPED", "DEAD_MONEY", "CUSHIONED", "CLEAN_LIFTOFF")} | {"n": n}


# ── Run batch trials ───────────────────────────────────────────────────────────
FACTORS_HG = {
    "F1": {"pass_col": "F1_pass", "valid_mask": None},
    "F2": {"pass_col": "F2_pass", "valid_mask": "F2_valid"},
    "F3": {"pass_col": "F3_pass", "valid_mask": None},
}
FACTORS_RW = {
    "F1": {"moved_up_col": "F1_moved_up"},
    "F2": {"moved_up_col": "F2_moved_up"},
    "F3": {"moved_up_col": "F3_moved_up"},
}

batch_results = {}

for trial_id, factor, mode, horizon, ts_target in batch_trials:
    print(f"  Running {trial_id}: {factor} Mode-{mode} {horizon}d {ts_target}...", flush=True)
    fwd_col, state_col = HORIZON_CONFIG[horizon]

    if mode == "HG":
        cfg = FACTORS_HG[factor]
        valid_mask = cfg.get("valid_mask")
        pop = vg_fires[vg_fires[valid_mask]].copy() if valid_mask else vg_fires.copy()
        grp_A = pop[pop[cfg["pass_col"]] == True]
        grp_B = pop[pop[cfg["pass_col"]] == False]
    else:
        moved_col = FACTORS_RW[factor]["moved_up_col"]
        pop = vg_fires.copy()
        grp_A = pop[pop[moved_col] == True]
        grp_B = pop[pop[moved_col] == False]

    n_A, n_B = len(grp_A), len(grp_B)
    n_ep_A = grp_A['episode_id'].nunique()
    n_ep_B = grp_B['episode_id'].nunique()
    is_thin = n_ep_A < THIN_FLOOR or n_ep_B < THIN_FLOOR

    ts_A = terminal_state_rates(grp_A, state_col)
    ts_B = terminal_state_rates(grp_B, state_col)
    delta_pp = (ts_A.get(ts_target, np.nan) - ts_B.get(ts_target, np.nan)) * 100
    delta_favorable = (delta_pp < 0) if ts_target in ("STOPPED", "DEAD_MONEY") else (delta_pp > 0)

    if n_A > 0 and n_B > 0 and not is_thin:
        u_stat, param_p, boot_p, r_biserial = episode_bootstrap_mwu(
            grp_A[fwd_col].values, grp_B[fwd_col].values,
            grp_A['episode_id'].values, grp_B['episode_id'].values,
        )
    else:
        u_stat, param_p, boot_p, r_biserial = np.nan, np.nan, np.nan, np.nan

    # Both-halves
    half_deltas = []
    for half_data in [half1, half2]:
        if mode == "HG":
            hp = half_data[half_data[cfg.get("valid_mask") or "F1_pass"] != None] if False else half_data
            if valid_mask:
                hp = half_data[half_data[valid_mask]]
            else:
                hp = half_data
            h_A = hp[hp[cfg["pass_col"]] == True]
            h_B = hp[hp[cfg["pass_col"]] == False]
        else:
            moved_col = FACTORS_RW[factor]["moved_up_col"]
            h_A = half_data[half_data[moved_col] == True]
            h_B = half_data[half_data[moved_col] == False]
        ts_hA = terminal_state_rates(h_A, state_col)
        ts_hB = terminal_state_rates(h_B, state_col)
        half_deltas.append((ts_hA.get(ts_target, np.nan) - ts_hB.get(ts_target, np.nan)) * 100)

    sign_stable = bool((half_deltas[0] > 0) == (half_deltas[1] > 0)) if not any(np.isnan(half_deltas)) else False

    batch_results[trial_id] = {
        "trial_id": trial_id, "factor": factor, "mode": mode,
        "horizon": horizon, "ts_target": ts_target,
        "n_A": n_A, "n_B": n_B, "n_ep_A": n_ep_A, "n_ep_B": n_ep_B,
        "is_thin": is_thin,
        "ts_rate_A": float(ts_A.get(ts_target, np.nan)),
        "ts_rate_B": float(ts_B.get(ts_target, np.nan)),
        "delta_pp": float(delta_pp),
        "delta_favorable": bool(delta_favorable),
        "boot_p": float(boot_p) if not np.isnan(boot_p) else None,
        "param_p": float(param_p) if not np.isnan(param_p) else None,
        "r_biserial": float(r_biserial) if not np.isnan(r_biserial) else None,
        "sign_stable": sign_stable,
        "half1_delta_pp": float(half_deltas[0]),
        "half2_delta_pp": float(half_deltas[1]),
    }
    print(f"    -> delta_pp={delta_pp:+.2f}pp, boot_p={boot_p:.4f}", flush=True)

# Save batch partial
out_path = OUT_DIR / f"partial_{start_idx}_{end_idx}.json"
with open(out_path, "w") as f:
    json.dump(batch_results, f, indent=2, default=str)
print(f"Saved: {out_path}")
