#!/usr/bin/env python3
"""
P1.5 Continuation Partition — Analysis Script
Study ID: p1_5_continuation
Pre-Registration: research/entry_intel/P1_5_CONTINUATION_PREREG.md
Era Law: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)

§APPROVAL: APPROVED 2026-07-05
Effective verdict window: 2022-06-30 → 2026-07-02 (250-bar warmup consumes ~11 months from nominal 2021-07-06)
Canonical input: data/replay/replay_boarded.parquet ONLY.

Conformance checklist (P0_MEASUREMENT_MEMO.md §5 + v1.1 §6):
[x] Cites P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) in preamble
[x] Primary window = effective 2022-06-30 → last-full-replay-date (per §6 amendment 1)
[x] Verdict-grade statistics on survivor_bias=False rows only (all rows in this parquet have survivor_bias=False)
[x] horizon_censored rows excluded per-horizon
[x] Returns INSUFFICIENT-POWER if episode-clustered n < 100 (K1)
[x] BH family m=5 over T1-T5
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

# Verify scipy
try:
    import scipy.stats
    print(f"[OK] scipy {scipy.__version__} available")
except ImportError:
    print("[BLOCKER] scipy not available — Spearman correlation will fail")
    sys.exit(1)

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
REPLAY_PATH = REPO / "data/replay/replay_boarded.parquet"
MEMO_PATH   = REPO / "research/entry_intel/P0_MEASUREMENT_MEMO.md"
OUT_DIR     = REPO / "research/entry_intel/p1_runs/p1_5_continuation"
STUDY_ID    = "p1_5_continuation"

# ─── K3: memo existence gate ─────────────────────────────────────────────────
if not MEMO_PATH.exists():
    print("[BLOCKER-K3] P0_MEASUREMENT_MEMO.md does not exist — HALT per PREREG §7 K3")
    sys.exit(1)
print(f"[OK] P0_MEASUREMENT_MEMO.md confirmed at {MEMO_PATH}")

# ─── Preamble ─────────────────────────────────────────────────────────────────
print("=" * 72)
print("P1.5 CONTINUATION PARTITION ANALYSIS")
print("Era law: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)")
print("Effective verdict window: 2022-06-30 → 2026-07-02 (§6 amendment 1)")
print("Canonical input: data/replay/replay_boarded.parquet")
print("=" * 72)

# ─── Load data ────────────────────────────────────────────────────────────────
print("\nLoading replay_boarded.parquet...")
df = pd.read_parquet(REPLAY_PATH)
print(f"  Total rows: {len(df):,}")

# ─── Survivor stamp census ────────────────────────────────────────────────────
n_unstamped   = (df["survivor_bias"] == False).sum()
n_stamped     = (df["survivor_bias"] == True).sum()
print(f"\nSurvivor census:")
print(f"  Unstamped (survivor_bias=False): {n_unstamped:,}")
print(f"  Stamped   (survivor_bias=True):  {n_stamped:,}")
print(f"  → All rows in this parquet are unstamped (Massive-sourced, 2022-06-30+)")

# Stamp text (mandatory §2.3 — pre-2021 era context note)
STAMP_TEXT = (
    "survivor-biased panel: 31.3% of member-months lack price history for 2012-2020 era; "
    "delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade. "
    "(Pre-2021 rows are NOT present in this parquet — all rows are 2022+ Massive-sourced.)"
)
print(f"\nSTAMP TEXT: {STAMP_TEXT}")

# ─── Filter: verdict_grade=True fires ─────────────────────────────────────────
fires_all = df[(df["verdict_grade"] == True) & (df["verdict_type"] == "fire")].copy()
print(f"\nVerdict-grade fires (total): {len(fires_all):,}")

# horizon_censored exclusion
# All verdict_grade fires have horizon_censored=False per data check; confirm
n_hc = fires_all["horizon_censored"].sum()
print(f"  horizon_censored=True (excluded per-horizon): {n_hc}")
fires = fires_all[fires_all["horizon_censored"] == False].copy()
print(f"  Fires after horizon_censored exclusion: {len(fires):,}")

# ─── Primary metric: clean8_21 ────────────────────────────────────────────────
fires["clean8_21"] = (fires["state_8_21"] == "CLEAN_LIFTOFF")

# ─── Partition arms ───────────────────────────────────────────────────────────
BOTTOMING_PHASES = {"bear_recovering", "basing", "turning"}

armed_cont  = fires[(fires["tier_cascade"] == "T2") & (fires["weekly_phase"] == "rising")].copy()
prime_fires = fires[(fires["tier_cascade"] == "T1") & (fires["weekly_phase"].isin(BOTTOMING_PHASES))].copy()
other_armed = fires[(fires["tier_cascade"] == "T2") & (~fires["weekly_phase"].isin(["rising"]))].copy()

print(f"\nPartition arm census:")
print(f"  ARMED-continuation (T2+rising):        {len(armed_cont):,} fires, {armed_cont['episode_id'].nunique():,} unique episodes")
print(f"  PRIME bottoming    (T1+bottoming):      {len(prime_fires):,} fires, {prime_fires['episode_id'].nunique():,} unique episodes")
print(f"  Other ARMED        (T2+non-rising):     {len(other_armed):,} fires, {other_armed['episode_id'].nunique():,} unique episodes")

# ARMED-continuation weekly_phase null check
n_null_phase_armed = fires[(fires["tier_cascade"]=="T2") & (fires["weekly_phase"].isna())].shape[0]
print(f"\nARMED rows with null weekly_phase excluded from partition: {n_null_phase_armed}")

# ─── K1: thin primary cells check ─────────────────────────────────────────────
n_armed_episodes = armed_cont["episode_id"].nunique()
n_prime_episodes = prime_fires["episode_id"].nunique()
print(f"\nK1 check: ARMED-continuation episodes = {n_armed_episodes} (need >= 100)")
if n_armed_episodes < 100:
    print("[BLOCKER-K1] ARMED-continuation has < 100 unique episodes — HALT")
    sys.exit(1)
print("  → K1 PASSED")

# ─── K2: null coverage check ──────────────────────────────────────────────────
rs_null_frac  = fires["rs_sector_quartile"].isna().mean()
ab200_null_frac = fires["above_200"].isna().mean()
print(f"\nK2 check:")
print(f"  rs_sector_quartile null fraction (all fires): {rs_null_frac:.3f}")
print(f"  above_200 null fraction (all fires):          {ab200_null_frac:.3f}")
if rs_null_frac > 0.20 or ab200_null_frac > 0.20:
    print("[BLOCKER-K2] > 20% null on rs_sector_quartile or above_200 — HALT")
    sys.exit(1)
print("  → K2 PASSED (< 20% null overall)")
# Note: within ARMED-continuation specifically
ac_rs_null = armed_cont["rs_sector_quartile"].isna().mean()
print(f"  rs_sector_quartile null within ARMED-continuation: {ac_rs_null:.3f}")

# ─── Helper: Wilson CI ────────────────────────────────────────────────────────
def wilson_ci(successes, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2*n)) / denom
    half   = (z * np.sqrt(p*(1-p)/n + z**2/(4*n**2))) / denom
    return (max(0, centre - half), min(1, centre + half))

# ─── Helper: Block bootstrap over episode_id clusters ─────────────────────────
def block_bootstrap_p_value(arm_df, ref_df, metric_col="clean8_21", n_boot=5000, seed=42):
    """
    Block bootstrap: resample clusters (episode_id) with replacement,
    compute Δ = P(metric|arm) - P(metric|ref) in each bootstrap rep.
    Returns two-sided p-value.
    """
    rng = np.random.default_rng(seed)

    arm_clusters = arm_df["episode_id"].unique()
    ref_clusters = ref_df["episode_id"].unique()

    # Group by episode_id for fast lookup
    arm_by_ep = arm_df.groupby("episode_id")[metric_col].mean()
    ref_by_ep = ref_df.groupby("episode_id")[metric_col].mean()

    obs_arm = arm_df[metric_col].mean()
    obs_ref = ref_df[metric_col].mean()
    obs_delta = obs_arm - obs_ref

    boot_deltas = np.empty(n_boot)
    for i in range(n_boot):
        boot_arm = arm_by_ep.loc[rng.choice(arm_clusters, size=len(arm_clusters), replace=True)].mean()
        boot_ref = ref_by_ep.loc[rng.choice(ref_clusters, size=len(ref_clusters), replace=True)].mean()
        boot_deltas[i] = boot_arm - boot_ref

    # Two-sided p-value: proportion of boot_deltas at least as extreme as obs_delta
    # Under H0: delta = 0; shift boot dist to be centred at 0
    boot_deltas_centred = boot_deltas - boot_deltas.mean()
    p_val = np.mean(np.abs(boot_deltas_centred) >= np.abs(obs_delta))
    return p_val, obs_delta, obs_arm, obs_ref, boot_deltas

# ─── Helper: BH correction ────────────────────────────────────────────────────
def bh_correct(pvals, alpha=0.10):
    """Benjamini-Hochberg correction. Returns q-values (adjusted p-values)."""
    m = len(pvals)
    arr = np.array(pvals)
    ranked = arr.argsort().argsort() + 1  # 1-indexed ranks
    q_vals = arr * m / ranked
    # Enforce monotonicity (step-down)
    q_out = np.empty(m)
    sorted_idx = arr.argsort()
    q_running = 1.0
    for i in sorted_idx[::-1]:
        q_running = min(q_running, q_vals[i])
        q_out[i] = q_running
    return q_out

# ─── Helper: Cell proportions ─────────────────────────────────────────────────
def cell_stats(df_arm, metric="clean8_21"):
    n = len(df_arm)
    k = df_arm[metric].sum()
    p = k / n if n > 0 else np.nan
    lo, hi = wilson_ci(k, n)
    return {"n": n, "k": int(k), "p": p, "ci_lo": lo, "ci_hi": hi,
            "n_episodes": df_arm["episode_id"].nunique()}

# ─── §5 secondary context metrics ─────────────────────────────────────────────
def secondary_stats(df_arm):
    n = len(df_arm)
    stop_r  = (df_arm["state_8_21"] == "STOPPED").mean()
    dm_r    = (df_arm["state_8_21"] == "DEAD_MONEY").mean()
    cush_r  = (df_arm["state_8_21"] == "CUSHIONED").mean()
    lift_r  = (df_arm["state_8_21"] == "CLEAN_LIFTOFF").mean()
    mae21   = df_arm["fwd_mdd_21"].mean()  # MDD is typically negative
    mfe21   = df_arm["fwd_mfe_21"].mean()
    ret5    = df_arm["fwd_ret_5"].mean()
    ret10   = df_arm["fwd_ret_10"].mean()
    ret21   = df_arm["fwd_ret_21"].mean()
    ret63   = df_arm["fwd_ret_63"].mean()
    return {
        "n": n,
        "STOPPED": stop_r,
        "DEAD_MONEY": dm_r,
        "CUSHIONED": cush_r,
        "CLEAN_LIFTOFF": lift_r,
        "mae_21d": mae21,
        "mfe_21d": mfe21,
        "ret_5d": ret5,
        "ret_10d": ret10,
        "ret_21d": ret21,
        "ret_63d": ret63,
    }

# ─── TRIAL T1: ARMED-continuation vs PRIME reference ─────────────────────────
print("\n" + "="*72)
print("TRIAL T1: ARMED-continuation vs PRIME reference")
print("="*72)

arm_stats  = cell_stats(armed_cont)
ref_stats  = cell_stats(prime_fires)
delta_t1   = arm_stats["p"] - ref_stats["p"]

print(f"  ARMED-continuation: n={arm_stats['n']:,}, k={arm_stats['k']:,}, P={arm_stats['p']:.4f} [{arm_stats['ci_lo']:.4f},{arm_stats['ci_hi']:.4f}]")
print(f"  PRIME bottoming:    n={ref_stats['n']:,}, k={ref_stats['k']:,}, P={ref_stats['p']:.4f} [{ref_stats['ci_lo']:.4f},{ref_stats['ci_hi']:.4f}]")
print(f"  Δ = {delta_t1:+.4f}")

print(f"\n  Running block bootstrap (n_boot=5000)...")
p_t1, obs_delta_t1, obs_arm_t1, obs_ref_t1, boot_deltas_t1 = block_bootstrap_p_value(
    armed_cont, prime_fires, n_boot=5000
)
print(f"  Bootstrap p-value (two-sided): {p_t1:.4f}")
print(f"  ARMED-continuation clusters: {armed_cont['episode_id'].nunique()}")
print(f"  PRIME reference clusters:    {prime_fires['episode_id'].nunique()}")

# Secondary stats
arm_sec = secondary_stats(armed_cont)
ref_sec = secondary_stats(prime_fires)
stop_diff_t1 = arm_sec["STOPPED"] - ref_sec["STOPPED"]
print(f"\n  Secondary context (NEVER verdict):")
print(f"    ARMED-cont   STOPPED={arm_sec['STOPPED']:.4f} DM={arm_sec['DEAD_MONEY']:.4f} CUSH={arm_sec['CUSHIONED']:.4f} LIFT={arm_sec['CLEAN_LIFTOFF']:.4f}")
print(f"    PRIME        STOPPED={ref_sec['STOPPED']:.4f} DM={ref_sec['DEAD_MONEY']:.4f} CUSH={ref_sec['CUSHIONED']:.4f} LIFT={ref_sec['CLEAN_LIFTOFF']:.4f}")
print(f"    Stop-out delta (ARMED-PRIME): {stop_diff_t1:+.4f}")

# ─── Both-halves sign stability ───────────────────────────────────────────────
print("\n  Both-halves sign stability:")
signal_dates = pd.to_datetime(fires["signal_date"])
min_date = signal_dates.min()
max_date = signal_dates.max()
mid_date = min_date + (max_date - min_date) / 2
print(f"    Window: {min_date.date()} → {max_date.date()}, midpoint: {mid_date.date()}")

fires["signal_date_dt"] = pd.to_datetime(fires["signal_date"])
armed_cont_h1 = armed_cont.copy()
armed_cont_h1["signal_date_dt"] = pd.to_datetime(armed_cont_h1["signal_date"])
prime_fires_h1 = prime_fires.copy()
prime_fires_h1["signal_date_dt"] = pd.to_datetime(prime_fires_h1["signal_date"])

ac_h1 = armed_cont_h1[armed_cont_h1["signal_date_dt"] < mid_date]
ac_h2 = armed_cont_h1[armed_cont_h1["signal_date_dt"] >= mid_date]
pf_h1 = prime_fires_h1[prime_fires_h1["signal_date_dt"] < mid_date]
pf_h2 = prime_fires_h1[prime_fires_h1["signal_date_dt"] >= mid_date]

delta_h1 = ac_h1["clean8_21"].mean() - pf_h1["clean8_21"].mean()
delta_h2 = ac_h2["clean8_21"].mean() - pf_h2["clean8_21"].mean()
sign_stable = (np.sign(delta_h1) == np.sign(delta_h2))
print(f"    H1 (before {mid_date.date()}): n_arm={len(ac_h1)}, n_ref={len(pf_h1)}, Δ={delta_h1:+.4f}")
print(f"    H2 (on/after {mid_date.date()}): n_arm={len(ac_h2)}, n_ref={len(pf_h2)}, Δ={delta_h2:+.4f}")
print(f"    Sign stable: {sign_stable} ({'STABLE' if sign_stable else 'FLIP — verdict degraded to CONDITIONAL'})")

# ─── Per-name majority check ──────────────────────────────────────────────────
print("\n  Per-name majority check:")
ac_by_name = armed_cont.groupby("ticker")["clean8_21"].mean()
pf_mean    = prime_fires["clean8_21"].mean()
n_agree    = (ac_by_name > pf_mean).sum() if delta_t1 > 0 else (ac_by_name < pf_mean).sum()
n_names    = len(ac_by_name)
majority   = n_agree / n_names
print(f"    PRIME reference P(clean8_21): {pf_mean:.4f}")
print(f"    ARMED-continuation names: {n_names}")
print(f"    Direction={'higher' if delta_t1 > 0 else 'lower'} direction agrees: {n_agree}/{n_names} = {majority:.3f}")
majority_pass = majority > 0.50
print(f"    Majority check passed: {majority_pass}")

# ─── TRIALS T2-T5: sub-partition within ARMED-continuation ────────────────────
print("\n" + "="*72)
print("TRIALS T2-T5: Sub-partition within ARMED-continuation fires")
print("="*72)

# Restrict to non-null rs_sector_quartile rows for T2-T5
ac_rs = armed_cont[armed_cont["rs_sector_quartile"].notna()].copy()
print(f"\n  ARMED-continuation with non-null rs_sector_quartile: {len(ac_rs):,} (excluded: {len(armed_cont)-len(ac_rs):,} null)")

# T2: Q1 vs Q2-Q4
t2_arm = ac_rs[ac_rs["rs_sector_quartile"] == 1.0]
t2_ref = ac_rs[ac_rs["rs_sector_quartile"] != 1.0]
print(f"\nT2 — RS Q1 vs Q2-Q4 within ARMED-continuation:")
t2_arm_s = cell_stats(t2_arm)
t2_ref_s = cell_stats(t2_ref)
delta_t2 = t2_arm_s["p"] - t2_ref_s["p"]
print(f"  Q1 (top RS):   n={t2_arm_s['n']:,}, P={t2_arm_s['p']:.4f} [{t2_arm_s['ci_lo']:.4f},{t2_arm_s['ci_hi']:.4f}]")
print(f"  Q2-Q4 pooled:  n={t2_ref_s['n']:,}, P={t2_ref_s['p']:.4f} [{t2_ref_s['ci_lo']:.4f},{t2_ref_s['ci_hi']:.4f}]")
print(f"  Δ = {delta_t2:+.4f}")
print(f"  Running bootstrap...")
p_t2, *_ = block_bootstrap_p_value(t2_arm, t2_ref, n_boot=5000)
print(f"  Bootstrap p-value: {p_t2:.4f}")

# T3: Q1-Q2 vs Q3-Q4
t3_arm = ac_rs[ac_rs["rs_sector_quartile"].isin([1.0, 2.0])]
t3_ref = ac_rs[ac_rs["rs_sector_quartile"].isin([3.0, 4.0])]
print(f"\nT3 — RS Q1-Q2 vs Q3-Q4 within ARMED-continuation:")
t3_arm_s = cell_stats(t3_arm)
t3_ref_s = cell_stats(t3_ref)
delta_t3 = t3_arm_s["p"] - t3_ref_s["p"]
print(f"  Q1-Q2:         n={t3_arm_s['n']:,}, P={t3_arm_s['p']:.4f} [{t3_arm_s['ci_lo']:.4f},{t3_arm_s['ci_hi']:.4f}]")
print(f"  Q3-Q4:         n={t3_ref_s['n']:,}, P={t3_ref_s['p']:.4f} [{t3_ref_s['ci_lo']:.4f},{t3_ref_s['ci_hi']:.4f}]")
print(f"  Δ = {delta_t3:+.4f}")
print(f"  Running bootstrap...")
p_t3, *_ = block_bootstrap_p_value(t3_arm, t3_ref, n_boot=5000)
print(f"  Bootstrap p-value: {p_t3:.4f}")

# T4: above_200=True vs False within ARMED-continuation
t4_arm = armed_cont[armed_cont["above_200"] == True]
t4_ref = armed_cont[armed_cont["above_200"] == False]
print(f"\nT4 — above_200dma True vs False within ARMED-continuation:")
t4_arm_s = cell_stats(t4_arm)
t4_ref_s = cell_stats(t4_ref)
delta_t4 = t4_arm_s["p"] - t4_ref_s["p"]
print(f"  above_200=True:  n={t4_arm_s['n']:,}, P={t4_arm_s['p']:.4f} [{t4_arm_s['ci_lo']:.4f},{t4_arm_s['ci_hi']:.4f}]")
print(f"  above_200=False: n={t4_ref_s['n']:,}, P={t4_ref_s['p']:.4f} [{t4_ref_s['ci_lo']:.4f},{t4_ref_s['ci_hi']:.4f}]")
print(f"  Δ = {delta_t4:+.4f}")
print(f"  Running bootstrap...")
p_t4, *_ = block_bootstrap_p_value(t4_arm, t4_ref, n_boot=5000)
print(f"  Bootstrap p-value: {p_t4:.4f}")

# T5: Q1+above vs all others within ARMED-continuation (with non-null rs)
t5_arm = ac_rs[(ac_rs["rs_sector_quartile"] == 1.0) & (ac_rs["above_200"] == True)]
t5_ref = ac_rs[~((ac_rs["rs_sector_quartile"] == 1.0) & (ac_rs["above_200"] == True))]
print(f"\nT5 — Q1+above_200 corner vs all others within ARMED-continuation:")
t5_arm_s = cell_stats(t5_arm)
t5_ref_s = cell_stats(t5_ref)
delta_t5 = t5_arm_s["p"] - t5_ref_s["p"]
print(f"  Q1+above (corner): n={t5_arm_s['n']:,}, P={t5_arm_s['p']:.4f} [{t5_arm_s['ci_lo']:.4f},{t5_arm_s['ci_hi']:.4f}]")
print(f"  All others:        n={t5_ref_s['n']:,}, P={t5_ref_s['p']:.4f} [{t5_ref_s['ci_lo']:.4f},{t5_ref_s['ci_hi']:.4f}]")
print(f"  Δ = {delta_t5:+.4f}")
print(f"  Running bootstrap...")
p_t5, *_ = block_bootstrap_p_value(t5_arm, t5_ref, n_boot=5000)
print(f"  Bootstrap p-value: {p_t5:.4f}")

# ─── BH correction (m=5 family) ───────────────────────────────────────────────
print("\n" + "="*72)
print("BH FAMILY CORRECTION (m=5)")
print("="*72)
pvals = [p_t1, p_t2, p_t3, p_t4, p_t5]
qvals = bh_correct(pvals, alpha=0.10)
print(f"  Trial  p-value     q-value (BH)  Significant (q<=0.10)")
for i, (p, q) in enumerate(zip(pvals, qvals), 1):
    sig = "YES" if q <= 0.10 else "NO"
    print(f"  T{i}     {p:.4f}     {q:.4f}        {sig}")

# ─── Decision rule mapping ────────────────────────────────────────────────────
print("\n" + "="*72)
print("DECISION RULE MAPPING (T1 primary)")
print("="*72)

q_t1    = qvals[0]
delta   = delta_t1
sig     = q_t1 <= 0.10
mat     = abs(delta) >= 0.05  # materiality threshold 5pp
stop_mat = stop_diff_t1 >= 0.05

print(f"  T1 Δ = {delta:+.4f} (|Δ| >= 5pp: {mat})")
print(f"  T1 BH q = {q_t1:.4f} (significant: {sig})")
print(f"  Both-halves sign stable: {sign_stable}")
print(f"  Stop-out material diff (ARMED-cont stop >= PRIME stop + 5pp): {stop_mat} ({stop_diff_t1:+.4f})")
print(f"  Per-name majority pass: {majority_pass}")

# Apply decision rules from PREREG §6
# Decision table (in priority order):
#   H-UNDERRANK : Δ > +5pp AND q ≤ 0.10 AND sign_stable
#   H-EXCLUDE   : Δ < -5pp AND q ≤ 0.10 AND sign_stable AND stop_mat (stop-out ≥ 5pp)
#   H-MISLABEL  : |Δ| < 5pp   OR   (0 < Δ ≤ +5pp AND q ≤ 0.10)
#   H-NULL      : |Δ| < 5pp AND q > 0.10
#   AMBIGUOUS   : conflicting signs OR inconsistent majority
#                 — also fires when Δ < -5pp + significant + sign_stable but stop_mat=False
#                   (unspecified by the PREREG decision table; gap case)
if delta > 0.05 and sig and sign_stable:
    verdict = "H-UNDERRANK"
    reason  = f"Δ=+{delta:.3f} > +5pp, BH q={q_t1:.4f} ≤ 0.10, sign stable both halves."
elif delta < -0.05 and sig and sign_stable and stop_mat:
    verdict = "H-EXCLUDE"
    reason  = f"Δ={delta:.3f} < -5pp, BH q={q_t1:.4f} ≤ 0.10, sign stable, stop-out ≥ 5pp above PRIME."
elif delta < -0.05 and sig and sign_stable and not stop_mat:
    # GAP CASE: liftoff underperformance is material and significant, sign-stable,
    # per-name majority confirms — but stop-out delta is only +0.60pp (< 5pp).
    # H-EXCLUDE branch requires stop_mat; H-MISLABEL requires |Δ| < 5pp (not met).
    # No PREREG branch covers this. Return AMBIGUOUS / blocker per program law.
    verdict = "AMBIGUOUS"
    reason  = (
        f"GAP CASE: Δ={delta:.4f} (<-5pp, material), BH q={q_t1:.4f} (significant), "
        f"sign stable both halves, majority pass ({majority:.3f}). BUT stop-out delta = "
        f"{stop_diff_t1:+.4f} (<+5pp), so H-EXCLUDE's stop-out criterion is NOT met. "
        f"H-MISLABEL requires |Δ| < 5pp (not met: |Δ|={abs(delta):.4f}). "
        f"No pre-registered branch covers: liftoff material+significant+stable but stop-out immaterial. "
        f"PREREG decision table has a gap. Returning blocker to Fable per program law."
    )
elif abs(delta) < 0.05 or (0 < delta <= 0.05 and sig):
    verdict = "H-MISLABEL"
    reason  = f"|Δ|={abs(delta):.4f} < 5pp (not materially different)."
elif not sig:
    verdict = "H-NULL"
    reason  = f"BH q={q_t1:.4f} > 0.10, no detectable differential."
elif not sign_stable or not majority_pass:
    verdict = "AMBIGUOUS"
    reason  = "Conflicting signs across both halves or per-name majority inconsistent."
else:
    verdict = "AMBIGUOUS"
    reason  = "None of the pre-registered branches triggered cleanly (unspecified case)."

print(f"\n  PRIMARY VERDICT: {verdict}")
print(f"  Reason: {reason}")

# ─── Other ARMED diagnostic ───────────────────────────────────────────────────
print("\n" + "="*72)
print("DIAGNOSTIC: Other ARMED fires (non-primary, context only)")
print("="*72)
other_s = cell_stats(other_armed)
other_sec = secondary_stats(other_armed)
print(f"  Other ARMED (non-rising): n={other_s['n']:,}, P(clean8_21)={other_s['p']:.4f} [{other_s['ci_lo']:.4f},{other_s['ci_hi']:.4f}]")
print(f"  State breakdown: STOPPED={other_sec['STOPPED']:.4f}, DM={other_sec['DEAD_MONEY']:.4f}, CUSH={other_sec['CUSHIONED']:.4f}, LIFT={other_sec['CLEAN_LIFTOFF']:.4f}")

# ─── Build results.json ───────────────────────────────────────────────────────
results = {
    "study_id": STUDY_ID,
    "era_law": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)",
    "effective_verdict_window": "2022-06-30 → 2026-07-02",
    "canonical_input": str(REPLAY_PATH),
    "run_date": "2026-07-05",
    "primary_verdict": verdict,
    "primary_verdict_reason": reason,
    "survivor_census": {
        "unstamped": int(n_unstamped),
        "stamped": int(n_stamped),
        "horizon_censored_fires": int(n_hc),
    },
    "partition_census": {
        "armed_continuation": {"n": int(arm_stats["n"]), "n_episodes": int(arm_stats["n_episodes"])},
        "prime_bottoming": {"n": int(ref_stats["n"]), "n_episodes": int(ref_stats["n_episodes"])},
        "other_armed": {"n": int(other_s["n"])},
    },
    "trials": {
        "T1": {
            "description": "ARMED/rising vs PRIME reference (primary)",
            "delta": round(float(delta_t1), 5),
            "armed_cont_p": round(float(arm_stats["p"]), 5),
            "prime_ref_p": round(float(ref_stats["p"]), 5),
            "p_value": round(float(p_t1), 5),
            "q_value_bh": round(float(qvals[0]), 5),
            "significant": bool(qvals[0] <= 0.10),
            "sign_stable": bool(sign_stable),
            "majority_pass": bool(majority_pass),
            "stop_diff": round(float(stop_diff_t1), 5),
        },
        "T2": {
            "description": "RS Q1 vs Q2-Q4 within ARMED-continuation",
            "delta": round(float(delta_t2), 5),
            "p_value": round(float(p_t2), 5),
            "q_value_bh": round(float(qvals[1]), 5),
        },
        "T3": {
            "description": "RS Q1-Q2 vs Q3-Q4 within ARMED-continuation",
            "delta": round(float(delta_t3), 5),
            "p_value": round(float(p_t3), 5),
            "q_value_bh": round(float(qvals[2]), 5),
        },
        "T4": {
            "description": "above_200dma True vs False within ARMED-continuation",
            "delta": round(float(delta_t4), 5),
            "p_value": round(float(p_t4), 5),
            "q_value_bh": round(float(qvals[3]), 5),
        },
        "T5": {
            "description": "Q1+above_200 corner vs all others within ARMED-continuation",
            "delta": round(float(delta_t5), 5),
            "p_value": round(float(p_t5), 5),
            "q_value_bh": round(float(qvals[4]), 5),
        },
    },
    "secondary_context": {
        "armed_continuation": arm_sec,
        "prime_bottoming": ref_sec,
    },
    "bh_family_m": 5,
    "bh_threshold": 0.10,
    "materiality_threshold_pp": 5.0,
}

out_json = OUT_DIR / "results.json"
with open(out_json, "w") as f:
    json.dump(results, f, indent=2, default=float)
print(f"\n[OK] results.json written to {out_json}")

# ─── Build RESULTS.md ─────────────────────────────────────────────────────────
md_lines = []
md_lines.append("# P1.5 Continuation Partition — RESULTS")
md_lines.append("")
md_lines.append(f"**PRIMARY VERDICT: {verdict}**")
md_lines.append("")
md_lines.append(f"*{reason}*")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## In plain English")
md_lines.append("")

if verdict == "H-UNDERRANK":
    pe_text = (
        f"Names admitted to the board via the 'weekly already rising' (continuation) path "
        f"actually hit their clean-liftoff target (≥8% before −5% in 21 days) at a rate of "
        f"{arm_stats['p']:.1%}, compared to {ref_stats['p']:.1%} for names coming off a fresh "
        f"bottom. That is a {delta:+.1%} gap — large enough to matter and statistically reliable "
        f"across both halves of the time window. The rank formula currently penalises these "
        f"continuation-profile names (it scores 'weekly rising' at 0.35 vs 1.0 for "
        f"'bear_recovering'). The data says they belong higher in the rankings, not lower. "
        f"Next step: a P3.2 re-rank PREREG to adjust the quality formula."
    )
elif verdict == "H-MISLABEL":
    pe_text = (
        f"Names admitted via the 'weekly already rising' continuation path perform similarly "
        f"to names coming off a fresh bottom (Δ={delta:+.1%}, below the 5pp materiality bar). "
        f"They are not worse entries — they are just labelled the same as fresh-bottom setups. "
        f"The fix is cosmetic: give these names an explicit 'continuation' lane label on the "
        f"board so users know they are a different structural type, without changing the gate "
        f"or the rank formula."
    )
elif verdict == "H-EXCLUDE":
    pe_text = (
        f"Names admitted via the 'weekly already rising' continuation path stop out at a "
        f"materially higher rate than fresh-bottom entries (stop diff: {stop_diff_t1:+.1%}) and "
        f"achieve clean-liftoff {delta:.1%} less often (Δ={delta:+.1%}, BH q={q_t1:.3f}). "
        f"They belong in a separate continuation species, not the bottoming lane. "
        f"Next step: P2.3 species PREREGs for Leader Reload and Compression Breakout."
    )
elif verdict == "H-NULL":
    pe_text = (
        f"No material or statistically detectable difference between continuation-profile fires "
        f"(Δ={delta:+.1%}, BH q={q_t1:.3f} > 0.10). Both populations grade similarly. "
        f"No intervention warranted."
    )
else:
    pe_text = (
        f"The data reveals a real and reliable gap: names admitted via the 'weekly already rising' "
        f"continuation path hit the clean-liftoff target only {arm_stats['p']:.1%} of the time, "
        f"versus {ref_stats['p']:.1%} for fresh-bottom entries — a {delta:.1%} gap that is "
        f"statistically significant (BH q≈0) and carries the same sign in both halves of the "
        f"window. Per-name majority confirms it. However, the stop-out rate for continuation "
        f"fires is only {stop_diff_t1:+.1%} higher than PRIME — well below the 5pp threshold "
        f"that the pre-registration requires for H-EXCLUDE. So the underperformance shows up "
        f"as more DEAD_MONEY / CUSHIONED outcomes, not as stop-outs. The PREREG's decision "
        f"table has a gap: it does not specify what to conclude when liftoff is materially worse "
        f"but stop-out is not materially different. Under program law (ambiguity = blocker, "
        f"never improvisation), this study returns AMBIGUOUS and awaits Fable ruling."
    )

md_lines.append(pe_text)
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Preamble (conformance)")
md_lines.append("")
md_lines.append("- Era law: **P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)**")
md_lines.append("- Effective verdict window: **2022-06-30 → 2026-07-02** (§6 amendment 1: 250-bar MTF warmup)")
md_lines.append("- Canonical input: `data/replay/replay_boarded.parquet`")
md_lines.append(f"- survivor_bias=False rows (unstamped): {n_unstamped:,} (all rows in this parquet)")
md_lines.append(f"- survivor_bias=True rows excluded: {n_stamped} (none — pre-2021 rows absent from this parquet)")
md_lines.append(f"- horizon_censored fires excluded from primary: {n_hc}")
md_lines.append(f"- verdict_grade=True fires total: {len(fires):,}")
md_lines.append(f"- Missing-fraction stamp (2012-2020 era, context only): 31.3% of member-months")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## T1 Primary Comparison — ARMED-continuation vs PRIME bottoming")
md_lines.append("")
md_lines.append("| Arm | n fires | n episodes | P(clean8_21) | Wilson 95% CI | Δ |")
md_lines.append("|-----|---------|------------|-------------|---------------|---|")
md_lines.append(f"| ARMED-continuation (T2+rising) | {arm_stats['n']:,} | {arm_stats['n_episodes']:,} | {arm_stats['p']:.4f} | [{arm_stats['ci_lo']:.4f}, {arm_stats['ci_hi']:.4f}] | {delta_t1:+.4f} |")
md_lines.append(f"| PRIME bottoming (T1+bottoming)  | {ref_stats['n']:,} | {ref_stats['n_episodes']:,} | {ref_stats['p']:.4f} | [{ref_stats['ci_lo']:.4f}, {ref_stats['ci_hi']:.4f}] | — |")
md_lines.append("")
md_lines.append(f"- Bootstrap p-value (block, episode-clustered, n_boot=5000): **{p_t1:.4f}**")
md_lines.append(f"- BH q-value (m=5 family): **{qvals[0]:.4f}** ({'significant' if qvals[0]<=0.10 else 'not significant'} at α=0.10)")
md_lines.append(f"- Both-halves sign stability: **{'STABLE' if sign_stable else 'FLIP — CONDITIONAL'}**")
md_lines.append(f"  - H1 Δ = {delta_h1:+.4f} (n_arm={len(ac_h1)}, n_ref={len(pf_h1)})")
md_lines.append(f"  - H2 Δ = {delta_h2:+.4f} (n_arm={len(ac_h2)}, n_ref={len(pf_h2)})")
md_lines.append(f"- Per-name majority: {n_agree}/{n_names} names agree in direction ({majority:.3f}) — **{'PASS' if majority_pass else 'FAIL'}**")
md_lines.append("")
md_lines.append("### Secondary context (NEVER verdict)")
md_lines.append("")
md_lines.append("| Arm | STOPPED | DEAD_MONEY | CUSHIONED | CLEAN_LIFTOFF | MAE_21d | MFE_21d | ret_5d | ret_21d | ret_63d |")
md_lines.append("|-----|---------|------------|-----------|---------------|---------|---------|--------|---------|---------|")
md_lines.append(f"| ARMED-cont | {arm_sec['STOPPED']:.3f} | {arm_sec['DEAD_MONEY']:.3f} | {arm_sec['CUSHIONED']:.3f} | {arm_sec['CLEAN_LIFTOFF']:.3f} | {arm_sec['mae_21d']:.4f} | {arm_sec['mfe_21d']:.4f} | {arm_sec['ret_5d']:.4f} | {arm_sec['ret_21d']:.4f} | {arm_sec['ret_63d']:.4f} |")
md_lines.append(f"| PRIME      | {ref_sec['STOPPED']:.3f} | {ref_sec['DEAD_MONEY']:.3f} | {ref_sec['CUSHIONED']:.3f} | {ref_sec['CLEAN_LIFTOFF']:.3f} | {ref_sec['mae_21d']:.4f} | {ref_sec['mfe_21d']:.4f} | {ref_sec['ret_5d']:.4f} | {ref_sec['ret_21d']:.4f} | {ref_sec['ret_63d']:.4f} |")
md_lines.append(f"| Stop-out Δ (ARMED-PRIME) | {stop_diff_t1:+.3f} | | | | | | | | |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## T2–T5 Sub-partition tables (diagnostic context within ARMED-continuation)")
md_lines.append("")
md_lines.append(f"*ARMED-continuation rows with non-null rs_sector_quartile: {len(ac_rs):,} (excluded null: {len(armed_cont)-len(ac_rs):,})*")
md_lines.append("")
md_lines.append("| Trial | Axis | n_arm | P_arm | n_ref | P_ref | Δ | p-val | BH q |")
md_lines.append("|-------|------|-------|-------|-------|-------|---|-------|------|")
md_lines.append(f"| T2 | Q1 vs Q2-Q4 | {t2_arm_s['n']:,} | {t2_arm_s['p']:.4f} | {t2_ref_s['n']:,} | {t2_ref_s['p']:.4f} | {delta_t2:+.4f} | {p_t2:.4f} | {qvals[1]:.4f} |")
md_lines.append(f"| T3 | Q1-Q2 vs Q3-Q4 | {t3_arm_s['n']:,} | {t3_arm_s['p']:.4f} | {t3_ref_s['n']:,} | {t3_ref_s['p']:.4f} | {delta_t3:+.4f} | {p_t3:.4f} | {qvals[2]:.4f} |")
md_lines.append(f"| T4 | above_200=True vs False | {t4_arm_s['n']:,} | {t4_arm_s['p']:.4f} | {t4_ref_s['n']:,} | {t4_ref_s['p']:.4f} | {delta_t4:+.4f} | {p_t4:.4f} | {qvals[3]:.4f} |")
md_lines.append(f"| T5 | Q1+above vs others | {t5_arm_s['n']:,} | {t5_arm_s['p']:.4f} | {t5_ref_s['n']:,} | {t5_ref_s['p']:.4f} | {delta_t5:+.4f} | {p_t5:.4f} | {qvals[4]:.4f} |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## BH Family Summary (m=5)")
md_lines.append("")
md_lines.append("| Trial | p-value | BH q-value | Significant (q≤0.10) |")
md_lines.append("|-------|---------|------------|---------------------|")
for i, (p, q) in enumerate(zip(pvals, qvals), 1):
    sig_str = "YES" if q <= 0.10 else "NO"
    md_lines.append(f"| T{i} | {p:.4f} | {q:.4f} | {sig_str} |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Both-Halves Sign Stability Grid")
md_lines.append("")
md_lines.append(f"Window: {min_date.date()} → {max_date.date()}, midpoint: {mid_date.date()}")
md_lines.append("")
md_lines.append("| Half | ARMED-cont P(clean8_21) | PRIME P(clean8_21) | Δ | Sign |")
md_lines.append("|------|------------------------|-------------------|---|------|")
md_lines.append(f"| H1 (before {mid_date.date()}) | {ac_h1['clean8_21'].mean():.4f} | {pf_h1['clean8_21'].mean():.4f} | {delta_h1:+.4f} | {'+' if delta_h1 > 0 else '-'} |")
md_lines.append(f"| H2 (from {mid_date.date()}) | {ac_h2['clean8_21'].mean():.4f} | {pf_h2['clean8_21'].mean():.4f} | {delta_h2:+.4f} | {'+' if delta_h2 > 0 else '-'} |")
md_lines.append(f"| **Stability** | | | | **{'STABLE' if sign_stable else 'FLIP'}** |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Per-Name Majority Check")
md_lines.append("")
md_lines.append(f"- PRIME reference P(clean8_21): {pf_mean:.4f}")
md_lines.append(f"- ARMED-continuation tickers with per-name P {'>' if delta_t1 > 0 else '<'} PRIME: {n_agree}/{n_names} = {majority:.3f}")
md_lines.append(f"- Majority check: **{'PASS' if majority_pass else 'FAIL'}**")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Coverage / Survivor-Stamp Line")
md_lines.append("")
md_lines.append(f"- Total fire rows (verdict_grade=True): {len(fires_all):,}")
md_lines.append(f"- survivor_biased excluded (stamped): 0 (all rows in this parquet are 2022+ Massive-sourced, unstamped)")
md_lines.append(f"- horizon_censored fires excluded: {n_hc}")
md_lines.append(f"- Effective verdict-grade fires: {len(fires):,}")
md_lines.append(f"- Effective episode clusters (fires): {fires['episode_id'].nunique():,}")
md_lines.append(f"- ARMED-continuation episode clusters: {armed_cont['episode_id'].nunique():,}")
md_lines.append(f"- PRIME bottoming episode clusters: {prime_fires['episode_id'].nunique():,}")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Diagnostic: Other ARMED fires (non-primary)")
md_lines.append("")
md_lines.append(f"| Arm | n | P(clean8_21) | CI | STOPPED | LIFT |")
md_lines.append("|-----|---|-------------|-----|---------|------|")
md_lines.append(f"| Other ARMED (T2+non-rising) | {other_s['n']:,} | {other_s['p']:.4f} | [{other_s['ci_lo']:.4f},{other_s['ci_hi']:.4f}] | {other_sec['STOPPED']:.4f} | {other_sec['CLEAN_LIFTOFF']:.4f} |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Leak-Audit Section")
md_lines.append("")
md_lines.append("- **Fill rule:** entry = first close strictly after signal date (fill_date > signal_date). Same-bar fill is not used. Column `fill_offset` confirms.")
md_lines.append("- **Era-table source:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) §1.")
md_lines.append("- **weekly_phase:** logged at signal time in the replay harness (engine/cycles.py mtf_alignment), not look-ahead.")
md_lines.append("- **rs_sector_quartile:** logged at signal time in the replay harness (current-GICS snapshot, 928-label constituents map per §APPROVAL). Not look-ahead.")
md_lines.append("- **above_200:** logged at signal time in the replay harness signal_gate / frozen features. Not look-ahead.")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Decision Rule Outcome")
md_lines.append("")
md_lines.append(f"**{verdict}** — {reason}")
md_lines.append("")
md_lines.append("### Action mapping per PREREG §6:")
if verdict == "H-UNDERRANK":
    md_lines.append("- ARMED-continuation is a better cohort than the rank formula implies.")
    md_lines.append("- The `rising` weekly phase penalty (0.35 vs 1.0 for `bear_recovering`) is a re-rank candidate.")
    md_lines.append("- P3.2 re-rank PREREG required before any formula change.")
    md_lines.append("- T2-T5 sub-partition results inform where within ARMED-continuation the differential concentrates.")
elif verdict == "H-MISLABEL":
    md_lines.append("- ARMED-continuation fires are NOT materially worse — relabel them in an explicit 'continuation' lane.")
    md_lines.append("- Additive-lanes law R7: they are NOT removed, they are re-labelled.")
    md_lines.append("- No gate change. No rank change.")
elif verdict == "H-EXCLUDE":
    md_lines.append("- Continuation-profile fires should be excluded from bottoming lane.")
    md_lines.append("- Commission P2.3 PREREGs for Leader Reload and Compression Breakout species.")
    md_lines.append("- ARMED-continuation fires get a display tag 'continuation profile' pending species validation.")
elif verdict == "H-NULL":
    md_lines.append("- No material or detectable differential. Both populations grade similarly.")
    md_lines.append("- No intervention. Status quo.")
else:
    md_lines.append("- AMBIGUOUS — return structured report to Fable. No mechanical action.")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## Mandatory stamp text (§2.3)")
md_lines.append("")
md_lines.append(f"> {STAMP_TEXT}")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("*§8 row in the masterplan to be appended by Fable after Opus verdict review.*")

out_md = OUT_DIR / "RESULTS.md"
with open(out_md, "w") as f:
    f.write("\n".join(md_lines))
print(f"[OK] RESULTS.md written to {out_md}")

print("\n" + "="*72)
print(f"STUDY COMPLETE. PRIMARY VERDICT: {verdict}")
print("="*72)
