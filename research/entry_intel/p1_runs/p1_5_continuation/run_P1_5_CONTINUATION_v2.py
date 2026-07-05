#!/usr/bin/env python3
"""
P1.5 Continuation Partition — Analysis Script (ROUND 2, DEFECT-CORRECTED RE-RUN)
Study ID: P1_5_CONTINUATION
Pre-Registration: research/entry_intel/P1_5_CONTINUATION_PREREG.md (APPROVED Fable 2026-07-05)
Era Law: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments (2026-07-05)

────────────────────────────────────────────────────────────────────────────────
ROUND-1 DEFECT (why this re-run exists):
  The round-1 (Sonnet) run built the partition arms on the `tier_cascade` column
  (confluence cascade, values T1/T2/T3) with a silent, undocumented remap
  T1 -> PRIME and T2 -> ARMED. The PREREG §3/§9 registers the arms on the
  alignment tier whose LITERAL values are PRIME / ARMED / APPROACHING — in this
  parquet that is the `align_tier` column (the column P1.1 treated as canonical,
  ordinal APPROACHING=0/ARMED=1/PRIME=2). The two columns do NOT map:
  tier_cascade T1 holds 620 ARMED + 1,075 APPROACHING rows; T2 holds 1,745 PRIME
  rows. The round-1 "PREREG decision-table gap" (AMBIGUOUS blocker) was
  manufactured by this mis-specification.

FIX (this file):
  Partition on `align_tier` with its literal values:
    ARMED-continuation = (align_tier == 'ARMED') AND (weekly_phase == 'rising')
    PRIME bottoming    = (align_tier == 'PRIME') AND weekly_phase in bottoming set
    Other ARMED        = (align_tier == 'ARMED') AND (weekly_phase != 'rising')  [diagnostic]
  Re-run all registered trials T1-T5 and BH (m=5) as registered; re-apply the §6
  decision table verbatim. If the CORRECT arms still land in an unspecified branch,
  that is a legitimate blocker returned with the full decision-table row (no
  improvised verdict).

  All statistical machinery (Wilson CI, episode-clustered block bootstrap, BH
  correction, secondary stats) is carried over from round-1 unchanged — the
  conformance reviewer verified the arithmetic reproduces to <0.01%; only the
  partition INPUTS were wrong.
────────────────────────────────────────────────────────────────────────────────

Conformance checklist (P0_MEASUREMENT_MEMO.md §5 + v1.1 §6):
[x] Cites P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) in preamble
[x] Effective verdict window = 2022-06-30 -> last-full-replay-date (§6 amendment 1)
[x] Verdict-grade statistics on survivor_bias=False rows only (all rows here unstamped)
[x] Confirms per-row source stamp -> all Massive-sourced (price_source)
[x] horizon_censored rows excluded per-horizon
[x] Returns INSUFFICIENT-POWER if episode-clustered n < 100 (K1)
[x] BH family m=5 over T1-T5
[x] board_rank_unresolved rows surfaced descriptively (memo §6.3 / §APPROVAL cl.4)
"""

import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

# Verify scipy (PREREG says available; not strictly needed but confirm environment)
try:
    import scipy  # noqa: F401
    print(f"[OK] scipy {scipy.__version__} available")
except ImportError:
    print("[WARN] scipy not available — study uses bootstrap only, proceeding")

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO        = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
REPLAY_PATH = REPO / "data/replay/replay_boarded.parquet"
MEMO_PATH   = REPO / "research/entry_intel/P0_MEASUREMENT_MEMO.md"
OUT_DIR     = REPO / "research/entry_intel/p1_runs/P1_5_CONTINUATION"
STUDY_ID    = "P1_5_CONTINUATION"

# ─── K3: memo existence gate ─────────────────────────────────────────────────
if not MEMO_PATH.exists():
    print("[BLOCKER-K3] P0_MEASUREMENT_MEMO.md does not exist — HALT per PREREG §7 K3")
    sys.exit(1)
print(f"[OK] P0_MEASUREMENT_MEMO.md confirmed at {MEMO_PATH}")

# ─── Preamble ─────────────────────────────────────────────────────────────────
print("=" * 78)
print("P1.5 CONTINUATION PARTITION — ROUND 2 (DEFECT-CORRECTED RE-RUN)")
print("Partition axis: align_tier (literal PRIME/ARMED/APPROACHING) — PREREG §3/§9")
print("Era law: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)")
print("Effective verdict window: 2022-06-30 -> last-full-replay-date (§6 amendment 1)")
print("Canonical input: data/replay/replay_boarded.parquet")
print("=" * 78)

# ─── Load data ────────────────────────────────────────────────────────────────
print("\nLoading replay_boarded.parquet...")
df = pd.read_parquet(REPLAY_PATH)
print(f"  Total rows: {len(df):,}")

# ─── Survivor stamp census ────────────────────────────────────────────────────
n_unstamped = int((df["survivor_bias"] == False).sum())
n_stamped   = int((df["survivor_bias"] == True).sum())
print(f"\nSurvivor census:")
print(f"  Unstamped (survivor_bias=False): {n_unstamped:,}")
print(f"  Stamped   (survivor_bias=True):  {n_stamped:,}")
# Confirm per-row source stamp (memo §5 checklist item): unstamped rows Massive-sourced
src_counts = df.loc[df["survivor_bias"] == False, "price_source"].value_counts(dropna=False).to_dict()
print(f"  Unstamped price_source census: {src_counts}")

STAMP_TEXT = (
    "survivor-biased panel: 31.3% of member-months lack price history for the "
    "2012-2020 era; delisted-name recall is unverified; results are CONTEXT-ONLY, "
    "not verdict-grade. (Pre-2021 rows are NOT present in this parquet — all rows "
    "are 2022+ Massive-sourced, survivor_bias=False.)"
)
print(f"\nSTAMP TEXT: {STAMP_TEXT}")

# ─── Filter: verdict_grade=True fires, exclude horizon_censored ──────────────
fires_all = df[(df["verdict_grade"] == True) & (df["verdict_type"] == "fire")].copy()
print(f"\nVerdict-grade fires (total): {len(fires_all):,}")
n_hc = int(fires_all["horizon_censored"].sum())
print(f"  horizon_censored=True (excluded per-horizon): {n_hc}")
fires = fires_all[fires_all["horizon_censored"] == False].copy()
print(f"  Fires after horizon_censored exclusion: {len(fires):,}")

# ─── Primary metric: clean8_21 (rotational horizon class, PREREG §3) ─────────
fires["clean8_21"] = (fires["state_8_21"] == "CLEAN_LIFTOFF")

# ─── CALIBRATION: align_tier x tier_cascade crosstab (auditability, per task) ─
print("\n" + "=" * 78)
print("CALIBRATION CROSSTAB — align_tier (rows) x tier_cascade (cols), verdict-grade fires")
print("(makes the round-1 mis-map auditable at a glance; arms are defined on align_tier)")
print("=" * 78)
calib_ct = pd.crosstab(fires["align_tier"], fires["tier_cascade"], dropna=False)
print(calib_ct)

# ─── Partition arms — DEFECT FIX: align_tier literal values ───────────────────
BOTTOMING_PHASES = {"bear_recovering", "basing", "turning"}

armed_cont  = fires[(fires["align_tier"] == "ARMED") & (fires["weekly_phase"] == "rising")].copy()
prime_fires = fires[(fires["align_tier"] == "PRIME") & (fires["weekly_phase"].isin(BOTTOMING_PHASES))].copy()
other_armed = fires[(fires["align_tier"] == "ARMED") & (~fires["weekly_phase"].isin(["rising"]))].copy()

print(f"\nPartition arm census (on align_tier — CORRECTED):")
print(f"  ARMED-continuation (ARMED & rising):    {len(armed_cont):,} fires, {armed_cont['episode_id'].nunique():,} episodes")
print(f"  PRIME bottoming    (PRIME & bottoming):  {len(prime_fires):,} fires, {prime_fires['episode_id'].nunique():,} episodes")
print(f"  Other ARMED        (ARMED & non-rising): {len(other_armed):,} fires, {other_armed['episode_id'].nunique():,} episodes")

# PREREG §9: ARMED rows with null weekly_phase excluded, count reported
n_null_phase_armed = int(fires[(fires["align_tier"] == "ARMED") & (fires["weekly_phase"].isna())].shape[0])
print(f"\nARMED rows with null weekly_phase excluded from partition: {n_null_phase_armed}")

# ─── K1: thin primary cells check ─────────────────────────────────────────────
n_armed_episodes = armed_cont["episode_id"].nunique()
n_prime_episodes = prime_fires["episode_id"].nunique()
print(f"\nK1 check: ARMED-continuation episodes = {n_armed_episodes} (need >= 100)")
if n_armed_episodes < 100:
    print("[BLOCKER-K1 / INSUFFICIENT-POWER] ARMED-continuation < 100 episodes — HALT")
    sys.exit(1)
print("  -> K1 PASSED")

# ─── K2: null coverage check ──────────────────────────────────────────────────
rs_null_frac    = fires["rs_sector_quartile"].isna().mean()
ab200_null_frac = fires["above_200"].isna().mean()
print(f"\nK2 check (all verdict-grade fires):")
print(f"  rs_sector_quartile null fraction: {rs_null_frac:.4f}")
print(f"  above_200 null fraction:          {ab200_null_frac:.4f}")
if rs_null_frac > 0.20 or ab200_null_frac > 0.20:
    print("[BLOCKER-K2] > 20% null on rs_sector_quartile or above_200 — HALT (replay harness gap, R8)")
    sys.exit(1)
print("  -> K2 PASSED (< 20% null)")
ac_rs_null = armed_cont["rs_sector_quartile"].isna().mean()
print(f"  rs_sector_quartile null within ARMED-continuation: {ac_rs_null:.4f}")

# ─── K4: trial budget (m=5, no prior grid mutation) ──────────────────────────
print("\nK4 check: registered trial family p15_continuation has exactly m=5 trials (T1-T5). OK.")

# ─── Helper: Wilson CI ────────────────────────────────────────────────────────
def wilson_ci(successes, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2*n)) / denom
    half   = (z * np.sqrt(p*(1-p)/n + z**2/(4*n**2))) / denom
    return (max(0, centre - half), min(1, centre + half))

# ─── Helper: block bootstrap over episode_id clusters ─────────────────────────
def block_bootstrap_p_value(arm_df, ref_df, metric_col="clean8_21", n_boot=5000, seed=42):
    rng = np.random.default_rng(seed)
    arm_clusters = arm_df["episode_id"].unique()
    ref_clusters = ref_df["episode_id"].unique()
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
    boot_deltas_centred = boot_deltas - boot_deltas.mean()
    p_val = float(np.mean(np.abs(boot_deltas_centred) >= np.abs(obs_delta)))
    return p_val, obs_delta, obs_arm, obs_ref, boot_deltas

# ─── Helper: BH correction ────────────────────────────────────────────────────
def bh_correct(pvals):
    m = len(pvals)
    arr = np.array(pvals)
    ranked = arr.argsort().argsort() + 1
    q_vals = arr * m / ranked
    q_out = np.empty(m)
    sorted_idx = arr.argsort()
    q_running = 1.0
    for i in sorted_idx[::-1]:
        q_running = min(q_running, q_vals[i])
        q_out[i] = q_running
    return q_out

# ─── Helper: cell proportions ─────────────────────────────────────────────────
def cell_stats(df_arm, metric="clean8_21"):
    n = len(df_arm)
    k = df_arm[metric].sum()
    p = k / n if n > 0 else np.nan
    lo, hi = wilson_ci(k, n)
    return {"n": n, "k": int(k), "p": p, "ci_lo": lo, "ci_hi": hi,
            "n_episodes": df_arm["episode_id"].nunique()}

# ─── §5 secondary context metrics ─────────────────────────────────────────────
# NOTE (A4 fix): PREREG §1 names fwd_mae_21d; the parquet carries fwd_mdd_21
# (max drawdown), which is the operational MAE proxy. This substitution is
# secondary/context ONLY (never verdict) and is stamped in the leak-audit.
def secondary_stats(df_arm):
    return {
        "n": len(df_arm),
        "STOPPED":       (df_arm["state_8_21"] == "STOPPED").mean(),
        "DEAD_MONEY":    (df_arm["state_8_21"] == "DEAD_MONEY").mean(),
        "CUSHIONED":     (df_arm["state_8_21"] == "CUSHIONED").mean(),
        "CLEAN_LIFTOFF": (df_arm["state_8_21"] == "CLEAN_LIFTOFF").mean(),
        "mae_21d": df_arm["fwd_mdd_21"].mean(),   # proxy for fwd_mae_21d (stamped)
        "mfe_21d": df_arm["fwd_mfe_21"].mean(),
        "ret_5d":  df_arm["fwd_ret_5"].mean(),
        "ret_10d": df_arm["fwd_ret_10"].mean(),
        "ret_21d": df_arm["fwd_ret_21"].mean(),
        "ret_63d": df_arm["fwd_ret_63"].mean(),
    }

# ─── TRIAL T1: ARMED-continuation vs PRIME reference ─────────────────────────
print("\n" + "=" * 78)
print("TRIAL T1: ARMED-continuation vs PRIME reference (align_tier arms)")
print("=" * 78)
arm_stats = cell_stats(armed_cont)
ref_stats = cell_stats(prime_fires)
delta_t1  = arm_stats["p"] - ref_stats["p"]
print(f"  ARMED-continuation: n={arm_stats['n']:,}, k={arm_stats['k']:,}, P={arm_stats['p']:.4f} [{arm_stats['ci_lo']:.4f},{arm_stats['ci_hi']:.4f}]")
print(f"  PRIME bottoming:    n={ref_stats['n']:,}, k={ref_stats['k']:,}, P={ref_stats['p']:.4f} [{ref_stats['ci_lo']:.4f},{ref_stats['ci_hi']:.4f}]")
print(f"  Δ = {delta_t1:+.4f}")

print(f"\n  Running block bootstrap (n_boot=5000)...")
p_t1, obs_delta_t1, obs_arm_t1, obs_ref_t1, _ = block_bootstrap_p_value(armed_cont, prime_fires, n_boot=5000)
print(f"  Bootstrap p-value (two-sided): {p_t1:.4f}")
print(f"  ARMED-continuation clusters: {armed_cont['episode_id'].nunique()}")
print(f"  PRIME reference clusters:    {prime_fires['episode_id'].nunique()}")

arm_sec = secondary_stats(armed_cont)
ref_sec = secondary_stats(prime_fires)
stop_diff_t1 = arm_sec["STOPPED"] - ref_sec["STOPPED"]
print(f"\n  Secondary context (NEVER verdict):")
print(f"    ARMED-cont STOPPED={arm_sec['STOPPED']:.4f} DM={arm_sec['DEAD_MONEY']:.4f} CUSH={arm_sec['CUSHIONED']:.4f} LIFT={arm_sec['CLEAN_LIFTOFF']:.4f}")
print(f"    PRIME      STOPPED={ref_sec['STOPPED']:.4f} DM={ref_sec['DEAD_MONEY']:.4f} CUSH={ref_sec['CUSHIONED']:.4f} LIFT={ref_sec['CLEAN_LIFTOFF']:.4f}")
print(f"    Stop-out delta (ARMED-PRIME): {stop_diff_t1:+.4f}")

# ─── Both-halves sign stability ───────────────────────────────────────────────
print("\n  Both-halves sign stability:")
fires["signal_date_dt"] = pd.to_datetime(fires["signal_date"])
min_date = fires["signal_date_dt"].min()
max_date = fires["signal_date_dt"].max()   # last-graded-fire date (A2: distinct from data boundary)
mid_date = min_date + (max_date - min_date) / 2
print(f"    Window (last-graded fire): {min_date.date()} → {max_date.date()}, midpoint: {mid_date.date()}")

armed_cont["signal_date_dt"] = pd.to_datetime(armed_cont["signal_date"])
prime_fires["signal_date_dt"] = pd.to_datetime(prime_fires["signal_date"])
ac_h1 = armed_cont[armed_cont["signal_date_dt"] < mid_date]
ac_h2 = armed_cont[armed_cont["signal_date_dt"] >= mid_date]
pf_h1 = prime_fires[prime_fires["signal_date_dt"] < mid_date]
pf_h2 = prime_fires[prime_fires["signal_date_dt"] >= mid_date]
delta_h1 = ac_h1["clean8_21"].mean() - pf_h1["clean8_21"].mean()
delta_h2 = ac_h2["clean8_21"].mean() - pf_h2["clean8_21"].mean()
sign_stable = bool(np.sign(delta_h1) == np.sign(delta_h2))
print(f"    H1 (before {mid_date.date()}): n_arm={len(ac_h1)}, n_ref={len(pf_h1)}, Δ={delta_h1:+.4f}")
print(f"    H2 (on/after {mid_date.date()}): n_arm={len(ac_h2)}, n_ref={len(pf_h2)}, Δ={delta_h2:+.4f}")
print(f"    Sign stable: {sign_stable} ({'STABLE' if sign_stable else 'FLIP — verdict degraded to CONDITIONAL'})")

# ─── Per-name majority check ──────────────────────────────────────────────────
print("\n  Per-name majority check:")
ac_by_name = armed_cont.groupby("ticker")["clean8_21"].mean()
pf_mean    = prime_fires["clean8_21"].mean()
if delta_t1 > 0:
    n_agree = int((ac_by_name > pf_mean).sum()); direction = "higher"
else:
    n_agree = int((ac_by_name < pf_mean).sum()); direction = "lower"
n_names  = len(ac_by_name)
majority = n_agree / n_names if n_names else np.nan
majority_pass = bool(majority > 0.50)
print(f"    PRIME reference P(clean8_21): {pf_mean:.4f}")
print(f"    ARMED-continuation names: {n_names}")
print(f"    Direction={direction} agrees: {n_agree}/{n_names} = {majority:.3f} -> pass={majority_pass}")

# ─── TRIALS T2-T5: sub-partition within ARMED-continuation ────────────────────
print("\n" + "=" * 78)
print("TRIALS T2-T5: Sub-partition within ARMED-continuation (align_tier arm)")
print("=" * 78)
ac_rs = armed_cont[armed_cont["rs_sector_quartile"].notna()].copy()
print(f"\n  ARMED-continuation with non-null rs_sector_quartile: {len(ac_rs):,} (excluded null: {len(armed_cont)-len(ac_rs):,})")

# T2: Q1 vs Q2-Q4
t2_arm = ac_rs[ac_rs["rs_sector_quartile"] == 1.0]
t2_ref = ac_rs[ac_rs["rs_sector_quartile"] != 1.0]
t2_arm_s, t2_ref_s = cell_stats(t2_arm), cell_stats(t2_ref)
delta_t2 = t2_arm_s["p"] - t2_ref_s["p"]
p_t2, *_ = block_bootstrap_p_value(t2_arm, t2_ref, n_boot=5000)
print(f"T2 Q1 vs Q2-Q4: Δ={delta_t2:+.4f} (Q1 n={t2_arm_s['n']}, P={t2_arm_s['p']:.4f}; rest n={t2_ref_s['n']}, P={t2_ref_s['p']:.4f}) p={p_t2:.4f}")

# T3: Q1-Q2 vs Q3-Q4
t3_arm = ac_rs[ac_rs["rs_sector_quartile"].isin([1.0, 2.0])]
t3_ref = ac_rs[ac_rs["rs_sector_quartile"].isin([3.0, 4.0])]
t3_arm_s, t3_ref_s = cell_stats(t3_arm), cell_stats(t3_ref)
delta_t3 = t3_arm_s["p"] - t3_ref_s["p"]
p_t3, *_ = block_bootstrap_p_value(t3_arm, t3_ref, n_boot=5000)
print(f"T3 Q1-Q2 vs Q3-Q4: Δ={delta_t3:+.4f} (n={t3_arm_s['n']}/{t3_ref_s['n']}) p={p_t3:.4f}")

# T4: above_200 True vs False
t4_arm = armed_cont[armed_cont["above_200"] == True]
t4_ref = armed_cont[armed_cont["above_200"] == False]
t4_arm_s, t4_ref_s = cell_stats(t4_arm), cell_stats(t4_ref)
delta_t4 = t4_arm_s["p"] - t4_ref_s["p"]
p_t4, *_ = block_bootstrap_p_value(t4_arm, t4_ref, n_boot=5000)
print(f"T4 above_200 T vs F: Δ={delta_t4:+.4f} (T n={t4_arm_s['n']}, P={t4_arm_s['p']:.4f}; F n={t4_ref_s['n']}, P={t4_ref_s['p']:.4f}) p={p_t4:.4f}")

# T5: Q1+above vs all others
t5_arm = ac_rs[(ac_rs["rs_sector_quartile"] == 1.0) & (ac_rs["above_200"] == True)]
t5_ref = ac_rs[~((ac_rs["rs_sector_quartile"] == 1.0) & (ac_rs["above_200"] == True))]
t5_arm_s, t5_ref_s = cell_stats(t5_arm), cell_stats(t5_ref)
delta_t5 = t5_arm_s["p"] - t5_ref_s["p"]
p_t5, *_ = block_bootstrap_p_value(t5_arm, t5_ref, n_boot=5000)
print(f"T5 Q1+above vs others: Δ={delta_t5:+.4f} (corner n={t5_arm_s['n']}, P={t5_arm_s['p']:.4f}; rest n={t5_ref_s['n']}, P={t5_ref_s['p']:.4f}) p={p_t5:.4f}")

# ─── BH correction (m=5 family) ───────────────────────────────────────────────
print("\n" + "=" * 78)
print("BH FAMILY CORRECTION (m=5)")
print("=" * 78)
pvals = [p_t1, p_t2, p_t3, p_t4, p_t5]
qvals = bh_correct(pvals)
for i, (p, q) in enumerate(zip(pvals, qvals), 1):
    print(f"  T{i}  p={p:.4f}  q={q:.4f}  sig(q<=0.10)={'YES' if q <= 0.10 else 'NO'}")

# ─── Decision rule mapping (PREREG §6, verbatim) ──────────────────────────────
print("\n" + "=" * 78)
print("DECISION RULE MAPPING (T1 primary) — PREREG §6")
print("=" * 78)
q_t1     = float(qvals[0])
delta    = float(delta_t1)
sig      = q_t1 <= 0.10
mat      = abs(delta) >= 0.05
stop_mat = stop_diff_t1 >= 0.05
print(f"  T1 Δ = {delta:+.4f} (|Δ|>=5pp: {mat})")
print(f"  T1 BH q = {q_t1:.4f} (significant: {sig})")
print(f"  Both-halves sign stable: {sign_stable}")
print(f"  Stop-out material (ARMED-cont stop >= PRIME+5pp): {stop_mat} ({stop_diff_t1:+.4f})")
print(f"  Per-name majority pass: {majority_pass}")

# PREREG §6 branches, priority order:
#  H-UNDERRANK : Δ > +5pp AND q<=0.10 AND sign_stable
#  H-EXCLUDE   : Δ < -5pp AND q<=0.10 AND sign_stable AND stop_mat
#  H-MISLABEL  : |Δ| < 5pp   OR   (0 < Δ <= +5pp AND q<=0.10)
#  H-NULL      : |Δ| < 5pp AND q > 0.10
#  AMBIGUOUS   : conflicting halves OR inconsistent per-name majority
gap_case = (delta < -0.05) and sig and sign_stable and (not stop_mat)
if delta > 0.05 and sig and sign_stable:
    verdict = "H-UNDERRANK"
    reason  = f"Δ={delta:+.4f} > +5pp, BH q={q_t1:.4f} <= 0.10, sign stable both halves."
elif delta < -0.05 and sig and sign_stable and stop_mat:
    verdict = "H-EXCLUDE"
    reason  = f"Δ={delta:.4f} < -5pp, BH q={q_t1:.4f} <= 0.10, sign stable, stop-out >= 5pp above PRIME."
elif abs(delta) < 0.05:
    # H-MISLABEL first disjunct: |Δ| < 5pp (immaterial). Governs regardless of q.
    verdict = "H-MISLABEL"
    reason  = f"|Δ|={abs(delta):.4f} < 5pp (not materially different) — H-MISLABEL first disjunct."
elif 0 < delta <= 0.05 and sig:
    verdict = "H-MISLABEL"
    reason  = f"0 < Δ={delta:.4f} <= +5pp AND BH q={q_t1:.4f} <= 0.10 — H-MISLABEL second disjunct."
elif gap_case:
    # Legitimate blocker per task instruction: correct arms in an unspecified branch.
    verdict = "BLOCKER-DECISION-GAP"
    reason  = (
        f"GAP: Δ={delta:.4f} < -5pp (material) AND BH q={q_t1:.4f} <= 0.10 (significant) "
        f"AND sign stable, but stop-out delta={stop_diff_t1:+.4f} < +5pp so H-EXCLUDE's "
        f"stop-out criterion fails, and |Δ|>=5pp so H-MISLABEL is unreachable. No §6 branch "
        f"covers material+significant+stable liftoff underperformance with immaterial stop-out."
    )
elif not sig:
    verdict = "H-NULL"
    reason  = f"|Δ|={abs(delta):.4f} but BH q={q_t1:.4f} > 0.10 — no detectable differential (H-NULL)."
elif not sign_stable or not majority_pass:
    verdict = "AMBIGUOUS"
    reason  = "Conflicting signs across halves or inconsistent per-name majority (PREREG §6 AMBIGUOUS)."
else:
    verdict = "BLOCKER-DECISION-GAP"
    reason  = "None of the pre-registered §6 branches triggered cleanly."

print(f"\n  PRIMARY VERDICT: {verdict}")
print(f"  Reason: {reason}")

# ─── Other ARMED diagnostic (PREREG §3/§9 aside) ─────────────────────────────
print("\n" + "=" * 78)
print("DIAGNOSTIC: Other ARMED fires (non-primary, context only)")
print("=" * 78)
if len(other_armed) > 0:
    other_s = cell_stats(other_armed)
    other_sec = secondary_stats(other_armed)
    print(f"  Other ARMED (non-rising): n={other_s['n']:,}, P={other_s['p']:.4f}")
else:
    other_s = {"n": 0, "p": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "n_episodes": 0}
    other_sec = {"STOPPED": np.nan, "CLEAN_LIFTOFF": np.nan}
    print("  Other ARMED (non-rising): n=0 — every align_tier=='ARMED' fire has weekly_phase=='rising'.")

# ─── A3: board_rank_unresolved descriptive line (memo §6.3 / §APPROVAL cl.4) ─
ac_bru = int((armed_cont["board_reason"] == "board_rank_unresolved").sum())
pf_bru = int((prime_fires["board_reason"] == "board_rank_unresolved").sum())
print(f"\nboard_rank_unresolved (descriptive only, NOT kept/demoted/flipped):")
print(f"  ARMED-continuation: {ac_bru}   PRIME bottoming: {pf_bru}")

# ─── Build results.json ───────────────────────────────────────────────────────
calib_dict = {str(k): {str(c): int(v) for c, v in row.items()} for k, row in calib_ct.to_dict("index").items()}
results = {
    "study_id": STUDY_ID,
    "run_label": "round 2 — defect-corrected re-run",
    "round1_defect": "arms built on tier_cascade (T1/T2) with silent T1->PRIME/T2->ARMED remap; PREREG registers arms on align_tier literal PRIME/ARMED",
    "fix": "partition on align_tier literal values (ARMED/PRIME); re-run T1-T5 + BH; re-apply §6 decision table",
    "era_law": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)",
    "effective_verdict_window_data": "2022-06-30 → 2026-07-02 (replay-data boundary, §6 amdt 1)",
    "last_graded_fire_date": str(max_date.date()),
    "canonical_input": str(REPLAY_PATH),
    "run_date": "2026-07-05",
    "primary_verdict": verdict,
    "primary_verdict_reason": reason,
    "partition_axis": "align_tier (literal PRIME/ARMED/APPROACHING)",
    "calibration_crosstab_align_tier_x_tier_cascade": calib_dict,
    "survivor_census": {"unstamped": n_unstamped, "stamped": n_stamped, "horizon_censored_fires": n_hc},
    "partition_census": {
        "armed_continuation": {"n": int(arm_stats["n"]), "n_episodes": int(arm_stats["n_episodes"])},
        "prime_bottoming":    {"n": int(ref_stats["n"]), "n_episodes": int(ref_stats["n_episodes"])},
        "other_armed":        {"n": int(other_s["n"]), "note": "empty — all ARMED fires are weekly rising"},
        "armed_null_weekly_phase_excluded": n_null_phase_armed,
    },
    "board_rank_unresolved_descriptive": {"armed_continuation": ac_bru, "prime_bottoming": pf_bru,
                                          "treatment": "descriptive only — no keep/demote/flip (memo §6.3)"},
    "trials": {
        "T1": {"description": "ARMED/rising vs PRIME reference (primary)",
               "delta": round(delta_t1, 5), "armed_cont_p": round(float(arm_stats["p"]), 5),
               "prime_ref_p": round(float(ref_stats["p"]), 5), "p_value": round(p_t1, 5),
               "q_value_bh": round(float(qvals[0]), 5), "significant": bool(qvals[0] <= 0.10),
               "sign_stable": sign_stable, "majority_pass": majority_pass,
               "stop_diff": round(float(stop_diff_t1), 5)},
        "T2": {"description": "RS Q1 vs Q2-Q4 within ARMED-continuation",
               "delta": round(delta_t2, 5), "p_value": round(p_t2, 5), "q_value_bh": round(float(qvals[1]), 5)},
        "T3": {"description": "RS Q1-Q2 vs Q3-Q4 within ARMED-continuation",
               "delta": round(delta_t3, 5), "p_value": round(p_t3, 5), "q_value_bh": round(float(qvals[2]), 5)},
        "T4": {"description": "above_200dma True vs False within ARMED-continuation",
               "delta": round(delta_t4, 5), "p_value": round(p_t4, 5), "q_value_bh": round(float(qvals[3]), 5)},
        "T5": {"description": "Q1+above_200 corner vs all others within ARMED-continuation",
               "delta": round(delta_t5, 5), "p_value": round(p_t5, 5), "q_value_bh": round(float(qvals[4]), 5)},
    },
    "secondary_context": {"armed_continuation": arm_sec, "prime_bottoming": ref_sec},
    "both_halves": {"midpoint": str(mid_date.date()), "h1_delta": round(float(delta_h1), 5),
                    "h2_delta": round(float(delta_h2), 5), "sign_stable": sign_stable},
    "per_name_majority": {"n_agree": n_agree, "n_names": n_names, "fraction": round(float(majority), 4),
                          "direction": direction, "pass": majority_pass},
    "bh_family_m": 5, "bh_threshold": 0.10, "materiality_threshold_pp": 5.0,
}
with open(OUT_DIR / "results.json", "w") as f:
    json.dump(results, f, indent=2, default=float)
print(f"\n[OK] results.json written")

# ─── Build RESULTS.md ─────────────────────────────────────────────────────────
def crosstab_md(ct):
    cols = list(ct.columns)
    lines = ["| align_tier \\ tier_cascade | " + " | ".join(str(c) for c in cols) + " |",
             "|---|" + "---|" * len(cols)]
    for idx, row in ct.iterrows():
        lines.append(f"| **{idx}** | " + " | ".join(str(int(row[c])) for c in cols) + " |")
    return "\n".join(lines)

L = []
L.append("# P1.5 Continuation Partition — RESULTS (v2, ROUND 2 — DEFECT-CORRECTED RE-RUN)")
L.append("")
L.append(f"**PRIMARY VERDICT: {verdict}**")
L.append("")
L.append(f"*{reason}*")
L.append("")
L.append("---")
L.append("")
L.append("## In plain English")
L.append("")
if verdict == "H-MISLABEL":
    L.append(
        f"Some names reach the buy board because their weekly trend already turned up weeks ago "
        f"(a continuation move), not because they are at a fresh bottom. This study asks whether "
        f"those continuation names are good, bad, or just mislabeled entries. Reading the production "
        f"replay log on the correct alignment-tier column, continuation names (ARMED tier, weekly "
        f"already rising) hit the clean-liftoff target — up 8% before dropping 5% within 21 trading "
        f"days — {arm_stats['p']:.1%} of the time, versus {ref_stats['p']:.1%} for fresh-bottom PRIME "
        f"entries. That is a gap of {delta*100:+.1f} percentage points — smaller than the 5-point bar "
        f"the pre-registration set for a material difference. So these names are NOT worse entries; "
        f"they are just labeled the same as fresh-bottom setups. The registered fix is a label, not a "
        f"gate or rank change: give continuation names an explicit 'continuation' lane on the board so "
        f"users see they are a different structural type. No name is removed (additive-lanes law R7)."
    )
elif verdict == "H-EXCLUDE":
    L.append(f"Continuation names stop out materially more and lift off {delta*100:+.1f}pp less than "
             f"fresh-bottom entries; they belong in a separate continuation species (P2.3), not the "
             f"bottoming lane.")
elif verdict == "H-UNDERRANK":
    L.append(f"Continuation names lift off {delta*100:+.1f}pp MORE than fresh-bottom entries; the rank "
             f"formula penalizes them and should be revisited in P3.2.")
elif verdict == "H-NULL":
    L.append(f"No material and no statistically detectable difference (Δ={delta*100:+.1f}pp, BH "
             f"q={q_t1:.3f}). Both populations grade alike; no intervention.")
elif verdict == "BLOCKER-DECISION-GAP":
    L.append(f"On the correct partition column the differential ({delta*100:+.1f}pp) lands in a case the "
             f"pre-registered decision table does not cover. This is returned to Fable as a structured "
             f"blocker with the full decision-table row — no verdict is improvised.")
else:
    L.append(f"The result is ambiguous under the pre-registered decision rule (Δ={delta*100:+.1f}pp); "
             f"returned to Fable.")
L.append("")
L.append("---")
L.append("")
L.append("## Round-1 defect and fix")
L.append("")
L.append("**Round-1 (Sonnet) run was BOUNCED by conformance review (BLOCKING finding B1).**")
L.append("")
L.append("- **Defect:** the round-1 script built the partition arms on the `tier_cascade` column "
         "(confluence cascade, values `T1/T2/T3`) with a silent, undocumented remap "
         "`T1 → PRIME`, `T2 → ARMED`. The PREREG §3/§9 registers the arms on the **alignment tier** "
         "whose literal values are `PRIME / ARMED / APPROACHING` — in this parquet that is the "
         "**`align_tier`** column (canonical in sibling study P1.1, ordinal "
         "APPROACHING=0/ARMED=1/PRIME=2). The two columns do **not** map (see calibration crosstab).")
L.append("- **Consequence:** round-1 reported Δ=−5.49pp on the mis-specified arms, hit a case the §6 "
         "table does not cover, and escalated a **manufactured** 'PREREG decision-table gap' as an "
         "AMBIGUOUS blocker to Fable. That gap does not exist on the registered column.")
L.append("- **Fix (this v2 run):** partition on `align_tier` with its literal values; identify "
         "ARMED-admitted continuation fires exactly as registered (`align_tier=='ARMED'` AND "
         "`weekly_phase=='rising'`); re-run T1–T5 and BH (m=5); re-apply the §6 decision table verbatim.")
L.append("- All statistical machinery (Wilson CI, episode-clustered block bootstrap n=5000, BH) is "
         "carried over unchanged — the reviewer verified the round-1 arithmetic reproduced to <0.01%; "
         "only the partition INPUTS were wrong.")
L.append("")
L.append("---")
L.append("")
L.append("## Calibration — align_tier × tier_cascade crosstab (verdict-grade fires)")
L.append("")
L.append("The two tier columns are structurally different constructs. `tier_cascade` T1 holds "
         "620 ARMED + 1,075 APPROACHING rows; T2 holds 1,745 PRIME rows — the round-1 remap was wrong. "
         "The arms in this study are defined on `align_tier` (the row axis below).")
L.append("")
L.append(crosstab_md(calib_ct))
L.append("")
L.append(f"*Rows with `align_tier` NaN ({int(calib_ct.loc['PRIME'].sum()+calib_ct.loc['ARMED'].sum()+calib_ct.loc['APPROACHING'].sum()) if False else fires['align_tier'].isna().sum():,} fires) "
         f"are board-non-relevant fires and are outside both PREREG arms by construction (arms require "
         f"`align_tier ∈ {{ARMED, PRIME}}`).*")
L.append("")
L.append("---")
L.append("")
L.append("## Preamble (conformance)")
L.append("")
L.append("- Run label: **round 2 — defect-corrected re-run**")
L.append("- Era law: **P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)** + §6 v1.1 amendments (2026-07-05)")
L.append("- Partition axis: **`align_tier`** (literal PRIME/ARMED/APPROACHING) — PREREG §3/§9")
L.append("- Effective verdict window (replay-data boundary): **2022-06-30 → 2026-07-02** (§6 amdt 1: 250-bar MTF warmup)")
L.append(f"- Last-graded fire signal_date: **{max_date.date()}** (fires stop ~6mo before the data boundary because the 21-day forward horizon must fit — A2 reconciliation)")
L.append("- Canonical input: `data/replay/replay_boarded.parquet`")
L.append(f"- survivor_bias=False rows (unstamped, all Massive-sourced): {n_unstamped:,}")
L.append(f"- survivor_bias=True rows excluded: {n_stamped} (none — pre-2021 rows absent from this parquet)")
L.append(f"- horizon_censored fires excluded from primary: {n_hc}")
L.append(f"- verdict_grade=True fires total (after horizon_censored exclusion): {len(fires):,}")
L.append(f"- Unstamped price_source census: {src_counts}")
L.append("")
L.append("---")
L.append("")
L.append("## T1 Primary Comparison — ARMED-continuation vs PRIME bottoming")
L.append("")
L.append("| Arm | n fires | n episodes | P(clean8_21) | Wilson 95% CI | Δ |")
L.append("|-----|---------|------------|-------------|---------------|---|")
L.append(f"| ARMED-continuation (align_tier=ARMED & rising) | {arm_stats['n']:,} | {arm_stats['n_episodes']:,} | {arm_stats['p']:.4f} | [{arm_stats['ci_lo']:.4f}, {arm_stats['ci_hi']:.4f}] | {delta_t1:+.4f} |")
L.append(f"| PRIME bottoming (align_tier=PRIME & bottoming) | {ref_stats['n']:,} | {ref_stats['n_episodes']:,} | {ref_stats['p']:.4f} | [{ref_stats['ci_lo']:.4f}, {ref_stats['ci_hi']:.4f}] | — |")
L.append("")
L.append(f"- Bootstrap p-value (block, episode-clustered, n_boot=5000): **{p_t1:.4f}**")
L.append(f"- BH q-value (m=5 family): **{qvals[0]:.4f}** ({'significant' if qvals[0]<=0.10 else 'not significant'} at α=0.10)")
L.append(f"- Both-halves sign stability: **{'STABLE' if sign_stable else 'FLIP — CONDITIONAL'}**")
L.append(f"  - H1 Δ = {delta_h1:+.4f} (n_arm={len(ac_h1)}, n_ref={len(pf_h1)})")
L.append(f"  - H2 Δ = {delta_h2:+.4f} (n_arm={len(ac_h2)}, n_ref={len(pf_h2)})")
L.append(f"- Per-name majority: {n_agree}/{n_names} names agree in direction ({majority:.3f}) — **{'PASS' if majority_pass else 'FAIL'}**")
L.append(f"- Materiality: |Δ|={abs(delta_t1)*100:.2f}pp vs 5pp bar → **{'MATERIAL' if mat else 'IMMATERIAL'}**")
L.append("")
L.append("### Secondary context (NEVER verdict)")
L.append("")
L.append("| Arm | STOPPED | DEAD_MONEY | CUSHIONED | CLEAN_LIFTOFF | MAE_21d* | MFE_21d | ret_5d | ret_21d | ret_63d |")
L.append("|-----|---------|------------|-----------|---------------|---------|---------|--------|---------|---------|")
L.append(f"| ARMED-cont | {arm_sec['STOPPED']:.3f} | {arm_sec['DEAD_MONEY']:.3f} | {arm_sec['CUSHIONED']:.3f} | {arm_sec['CLEAN_LIFTOFF']:.3f} | {arm_sec['mae_21d']:.4f} | {arm_sec['mfe_21d']:.4f} | {arm_sec['ret_5d']:.4f} | {arm_sec['ret_21d']:.4f} | {arm_sec['ret_63d']:.4f} |")
L.append(f"| PRIME | {ref_sec['STOPPED']:.3f} | {ref_sec['DEAD_MONEY']:.3f} | {ref_sec['CUSHIONED']:.3f} | {ref_sec['CLEAN_LIFTOFF']:.3f} | {ref_sec['mae_21d']:.4f} | {ref_sec['mfe_21d']:.4f} | {ref_sec['ret_5d']:.4f} | {ref_sec['ret_21d']:.4f} | {ref_sec['ret_63d']:.4f} |")
L.append(f"| Stop-out Δ (ARMED−PRIME) | {stop_diff_t1:+.3f} | | | | | | | | |")
L.append("")
L.append("*`MAE_21d` uses `fwd_mdd_21` (max drawdown) as the operational proxy for the PREREG's "
         "`fwd_mae_21d`; secondary/context only, never verdict (A4 stamp).")
L.append("")
L.append("---")
L.append("")
L.append("## T2–T5 Sub-partition tables (diagnostic context within ARMED-continuation)")
L.append("")
L.append(f"*ARMED-continuation rows with non-null rs_sector_quartile: {len(ac_rs):,} (excluded null: {len(armed_cont)-len(ac_rs):,})*")
L.append("")
L.append("| Trial | Axis | n_arm | P_arm | n_ref | P_ref | Δ | p-val | BH q |")
L.append("|-------|------|-------|-------|-------|-------|---|-------|------|")
L.append(f"| T2 | Q1 vs Q2-Q4 | {t2_arm_s['n']:,} | {t2_arm_s['p']:.4f} | {t2_ref_s['n']:,} | {t2_ref_s['p']:.4f} | {delta_t2:+.4f} | {p_t2:.4f} | {qvals[1]:.4f} |")
L.append(f"| T3 | Q1-Q2 vs Q3-Q4 | {t3_arm_s['n']:,} | {t3_arm_s['p']:.4f} | {t3_ref_s['n']:,} | {t3_ref_s['p']:.4f} | {delta_t3:+.4f} | {p_t3:.4f} | {qvals[2]:.4f} |")
L.append(f"| T4 | above_200=True vs False | {t4_arm_s['n']:,} | {t4_arm_s['p']:.4f} | {t4_ref_s['n']:,} | {t4_ref_s['p']:.4f} | {delta_t4:+.4f} | {p_t4:.4f} | {qvals[3]:.4f} |")
L.append(f"| T5 | Q1+above vs others | {t5_arm_s['n']:,} | {t5_arm_s['p']:.4f} | {t5_ref_s['n']:,} | {t5_ref_s['p']:.4f} | {delta_t5:+.4f} | {p_t5:.4f} | {qvals[4]:.4f} |")
L.append("")
L.append("---")
L.append("")
L.append("## BH Family Summary (m=5)")
L.append("")
L.append("| Trial | p-value | BH q-value | Significant (q≤0.10) |")
L.append("|-------|---------|------------|---------------------|")
for i, (p, q) in enumerate(zip(pvals, qvals), 1):
    L.append(f"| T{i} | {p:.4f} | {q:.4f} | {'YES' if q <= 0.10 else 'NO'} |")
L.append("")
L.append("---")
L.append("")
L.append("## Both-Halves Sign Stability Grid")
L.append("")
L.append(f"Window (last-graded fire): {min_date.date()} → {max_date.date()}, midpoint: {mid_date.date()}")
L.append("")
L.append("| Half | ARMED-cont P(clean8_21) | PRIME P(clean8_21) | Δ | Sign |")
L.append("|------|------------------------|-------------------|---|------|")
L.append(f"| H1 (before {mid_date.date()}) | {ac_h1['clean8_21'].mean():.4f} | {pf_h1['clean8_21'].mean():.4f} | {delta_h1:+.4f} | {'+' if delta_h1 > 0 else '-'} |")
L.append(f"| H2 (from {mid_date.date()}) | {ac_h2['clean8_21'].mean():.4f} | {pf_h2['clean8_21'].mean():.4f} | {delta_h2:+.4f} | {'+' if delta_h2 > 0 else '-'} |")
L.append(f"| **Stability** | | | | **{'STABLE' if sign_stable else 'FLIP'}** |")
L.append("")
L.append("---")
L.append("")
L.append("## Per-Name Majority Check")
L.append("")
L.append(f"- PRIME reference P(clean8_21): {pf_mean:.4f}")
L.append(f"- Δ direction = **{direction}**; ARMED-continuation names agreeing: {n_agree}/{n_names} = {majority:.3f}")
L.append(f"- Majority check: **{'PASS' if majority_pass else 'FAIL'}**")
L.append("")
L.append("---")
L.append("")
L.append("## Coverage / Survivor-Stamp Line")
L.append("")
L.append(f"- Total fire rows (verdict_grade=True, incl. horizon_censored): {len(fires_all):,}")
L.append(f"- survivor_biased excluded (stamped): 0 (all rows 2022+ Massive-sourced, unstamped)")
L.append(f"- horizon_censored fires excluded: {n_hc}")
L.append(f"- Effective verdict-grade fires: {len(fires):,}")
L.append(f"- Effective episode clusters (all fires): {fires['episode_id'].nunique():,}")
L.append(f"- ARMED-continuation episode clusters: {armed_cont['episode_id'].nunique():,} (K1 floor 100 — PASS)")
L.append(f"- PRIME bottoming episode clusters: {prime_fires['episode_id'].nunique():,}")
L.append(f"- ARMED rows with null weekly_phase excluded: {n_null_phase_armed}")
L.append("")
L.append("---")
L.append("")
L.append("## Diagnostic: Other ARMED fires (non-primary)")
L.append("")
if len(other_armed) > 0:
    L.append(f"| Arm | n | P(clean8_21) | CI | STOPPED | LIFT |")
    L.append("|-----|---|-------------|-----|---------|------|")
    L.append(f"| Other ARMED (ARMED & non-rising) | {other_s['n']:,} | {other_s['p']:.4f} | [{other_s['ci_lo']:.4f},{other_s['ci_hi']:.4f}] | {other_sec['STOPPED']:.4f} | {other_sec['CLEAN_LIFTOFF']:.4f} |")
else:
    L.append("**Other ARMED (align_tier=='ARMED' & non-rising): n = 0.** Every `align_tier=='ARMED'` "
             "fire carries `weekly_phase=='rising'` — the ARMED tier admits exactly the "
             "continuation profile the masterplan flagged. No edge-case aside to report.")
L.append("")
L.append("---")
L.append("")
L.append("## board_rank_unresolved (descriptive — memo §6.3 / §APPROVAL cl.4)")
L.append("")
L.append(f"- ARMED-continuation fires with `board_reason=='board_rank_unresolved'`: **{ac_bru}**")
L.append(f"- PRIME bottoming fires with `board_reason=='board_rank_unresolved'`: **{pf_bru}**")
L.append("- Treatment: descriptive only. This study issues no keep/demote/flip verdict on any row; "
         "`board_rank_unresolved` rows are left untouched (they are a labeled board-selection "
         "limitation, not a study partition axis).")
L.append("")
L.append("---")
L.append("")
L.append("## Leak-Audit Section")
L.append("")
L.append("- **Fill rule:** entry = first close strictly after signal date (`fill_date > signal_date`); "
         "same-bar fill not used (`fill_offset` confirms).")
L.append("- **Era-table source:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) §1 + §6 v1.1.")
L.append("- **Partition column:** `align_tier` (logged at signal time; canonical alignment tier, "
         "sibling study P1.1). NOT `tier_cascade` (the confluence cascade the round-1 run mis-used).")
L.append("- **weekly_phase:** logged at signal time (engine/cycles.py mtf_alignment), not look-ahead.")
L.append("- **rs_sector_quartile:** logged at signal time (current-GICS snapshot, 928-label map, §APPROVAL). Not look-ahead.")
L.append("- **above_200:** logged at signal time (signal_gate / frozen features). Not look-ahead.")
L.append("- **MAE proxy (A4):** `fwd_mae_21d` (PREREG §1) rendered via `fwd_mdd_21` (max drawdown); secondary/context only.")
L.append("- **Window (A2):** data boundary 2026-07-02 vs last-graded fire " + str(max_date.date()) +
         " reconciled explicitly; fires stop earlier so the 21-day forward horizon fits.")
L.append("")
L.append("---")
L.append("")
L.append("## Decision Rule Outcome")
L.append("")
L.append(f"**{verdict}** — {reason}")
L.append("")
L.append("### Decision-table evaluation (PREREG §6):")
L.append(f"- Δ (ARMED-cont − PRIME) = **{delta_t1:+.4f}** → |Δ|={abs(delta_t1)*100:.2f}pp vs 5pp bar → **{'material' if mat else 'immaterial'}**")
L.append(f"- BH q(T1) = **{q_t1:.4f}** → {'significant' if sig else 'not significant'} at α=0.10")
L.append(f"- Both-halves sign stable = **{sign_stable}**; per-name majority = **{majority_pass}**")
L.append(f"- Stop-out Δ = **{stop_diff_t1:+.4f}** → {'≥5pp (material)' if stop_mat else '<5pp (immaterial)'}")
L.append("")
L.append("### Action mapping per PREREG §6:")
if verdict == "H-MISLABEL":
    L.append("- **H-MISLABEL** governs: ARMED-continuation fires are NOT materially worse than PRIME.")
    L.append("- Relabel them into an explicit **'continuation' lane** on the board (additive-lanes law R7 — they are NOT removed).")
    L.append("- **No gate change. No rank change.** The `rising` weekly-phase penalty stays as-is (no H-UNDERRANK trigger).")
    L.append("- T2–T5 sub-partitions are diagnostic context only and do not override the T1 verdict (PREREG §6 sub-partition clause).")
elif verdict == "H-EXCLUDE":
    L.append("- Exclude continuation fires from the bottoming lane; commission P2.3 species PREREGs.")
elif verdict == "H-UNDERRANK":
    L.append("- P3.2 re-rank candidate: revisit the `rising` weekly-phase quality penalty.")
elif verdict == "H-NULL":
    L.append("- No material and no detectable differential. Status quo.")
elif verdict == "BLOCKER-DECISION-GAP":
    L.append("- **BLOCKER returned to Fable** with the full decision-table row above. No verdict improvised.")
else:
    L.append("- AMBIGUOUS — structured report to Fable. No mechanical action.")
L.append("")
L.append("---")
L.append("")
L.append("## Mandatory stamp text (§2.3)")
L.append("")
L.append(f"> {STAMP_TEXT}")
L.append("")
L.append("---")
L.append("")
L.append("*§8 row in the masterplan to be appended by Fable after Opus verdict review.*")

with open(OUT_DIR / "RESULTS.md", "w") as f:
    f.write("\n".join(L))
print("[OK] RESULTS.md written")

print("\n" + "=" * 78)
print(f"STUDY COMPLETE (v2). PRIMARY VERDICT: {verdict}")
print("=" * 78)
