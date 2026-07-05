"""
P2_1B_F1_REPROBE — re-run P1.3's F1 washout trials (T01-T10) with the PRODUCTION
washout signal replacing the replay proxy.

Study:   P2_1B_f1_concordance_reprobe (trials P2_1B_F1_REPROBE_T01-T10)
Program: Entry Intelligence (EI)
PREREG:  research/entry_intel/P2_1B_RANKWEIGHT_PREREG.md §3.3, §8, §11 (APPROVED Fable 2026-07-05)
Memo:    research/entry_intel/P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1
Author:  Opus subagent under Fable orchestration
Date:    2026-07-05

════════════════════════════════════════════════════════════════════════════════
WHY THIS RUN EXISTS
────────────────────────────────────────────────────────────────────────────────
The P2.1b §3.3 concordance gate measured 66.40% (floor 90%) between the replay
proxy (washout_proximity: price ≤ 0.9×200DMA within 21 bars) and the production
COILED washout signal (engine.coiled.washout_ctx: ≥15% drawdown from the 126d
pre-capitulation high within 91 bars). Direction: production_finds_more_washout —
production flags washout on 33.4% of pairs the proxy called False
(proxy_false_prod_true = 15,743 of 47,182 valid pairs). Verdict: REPROBE_REQUIRED.

Per §3.3 the P1.3 F1 trials must be re-run on production COILED values. This script
does exactly that: it recodes F1 on all verdict-grade fires using the PIT production
washout value (state at the fire date using data ≤ fire date), then re-runs the F1
trial battery (T01-T10) with the SAME calibrated episode-permutation machinery from
run_P1_3_v2.py. The negative calibration control runs on the NEW encoding before the
grid (mandatory). BH family = the 10 reprobe trials only.

REUSE PROVENANCE (not reinvented):
- Production washout computation path is copied VERBATIM from
  scripts/p2_1b_concordance_check.py (branch ei/p2-board-stack, commit 4bebc06716):
  for each (ticker, signal_date) load data/massive_stock_day/{ticker}.parquet['close'],
  slice PIT (index <= signal_date), call engine.coiled.washout_ctx(pit) -> bool|None.
  engine/coiled.py on this checkout is byte-identical to 4bebc06716 and the replay MD5
  matches 906175f9eb8caa351ed6d7d5c56265d3, so the production values reproduce the
  concordance computation exactly (36,734 prod_true / 10,448 prod_false / 2,757 prod_none).
- The statistic (episode-level label-permutation Mann-Whitney U, N_PERM=5000, two-sided,
  Phipson-Smyth +1 smoothing) is copied VERBATIM from run_P1_3_v2.py. No new statistic.

VERDICT RULE (from PREREG §3.3 / §8):
  F1 rank-weight promotion proceeds ONLY if the production-value trials reproduce
  BH-surviving, sign-stable favorable effects on the safety-net axes; otherwise F1
  promotion DIES and the P1.3 F1 verdict is re-scoped 'proxy-definition only'.
════════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import time
import hashlib
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parents[4]
sys.path.insert(0, str(REPO))
REPLAY_PATH = REPO / "data" / "replay" / "replay_boarded.parquet"
MSD_DIR = REPO / "data" / "massive_stock_day"
OUT_DIR = Path(__file__).parent
CONCORDANCE_JSON = REPO / "research" / "entry_intel" / "p1_runs" / "P1_3" / "concordance_check.json"
P13_RESULTS = REPO / "research" / "entry_intel" / "p1_runs" / "P1_3" / "results.json"

from engine.coiled import washout_ctx  # noqa: E402  (production washout signal)

STUDY_ID = "P2_1B_F1_REPROBE"
BH_FAMILY = "P2_1B_f1_concordance_reprobe"
N_PERM = 5000
BH_Q = 0.10
THIN_FLOOR = 25
SEED = 42
EXPECTED_REPLAY_MD5 = "906175f9eb8caa351ed6d7d5c56265d3"
P13_ERA_START = "2022-06-30"
P13_ERA_END = "2025-12-29"

# Concordance-gate reference values (from concordance_check.json, commit 4bebc06716)
CONCORDANCE_REF = {
    "concordance_rate": 0.664046,
    "n_valid_pairs": 47182,
    "n_prod_true": 36734,
    "n_prod_false": 10448,
    "n_prod_none": 2757,
    "divergence_direction": "production_finds_more_washout",
}

print("=" * 72)
print(f"{STUDY_ID} — F1 washout reprobe on PRODUCTION COILED values")
print("=" * 72)
print()

# ── 0. Provenance / integrity checks ────────────────────────────────────────────
assert REPLAY_PATH.exists(), f"BLOCKER: replay not found at {REPLAY_PATH}"
with open(REPLAY_PATH, "rb") as f:
    replay_md5 = hashlib.md5(f.read()).hexdigest()
print(f"Replay path: {REPLAY_PATH}")
print(f"Replay MD5:  {replay_md5}")
assert replay_md5 == EXPECTED_REPLAY_MD5, (
    f"BLOCKER: replay MD5 {replay_md5} != expected {EXPECTED_REPLAY_MD5} "
    "(production washout would not reproduce concordance)"
)
print(f"  -> matches concordance artifact MD5 (production values reproduce concordance)")
print(f"scipy version: {scipy.__version__}")
print(f"washout_ctx source: engine.coiled (production S1/COILED machinery)")
print()

# ── 1. Load P1.3 verdict-grade fire population ──────────────────────────────────
print("Loading replay_boarded.parquet ...")
df = pd.read_parquet(REPLAY_PATH)
print(f"  Full shape: {df.shape}")

# Same population filter as run_P1_3_v2.py primary population AND the concordance script.
vg = df[
    (df["verdict_grade"] == True)
    & (df["tier_cascade"].notna())
    & (df["signal_date"] >= P13_ERA_START)
    & (df["signal_date"] <= P13_ERA_END)
].copy()
# Cross-check: identical to verdict_type=='fire' & verdict_grade filter used by P1.3
vg_fire = df[(df["verdict_type"] == "fire") & (df["verdict_grade"] == True)].copy()
assert len(vg) == len(vg_fire) == 49939, (
    f"BLOCKER: population census mismatch: filter={len(vg)}, fire-filter={len(vg_fire)}"
)
assert int(vg["survivor_bias"].sum()) == 0, "UNEXPECTED: survivor_bias==True rows present"

n_fires_total = len(vg)
n_ep_clusters = vg["episode_id"].nunique()
era_min, era_max = vg["signal_date"].min(), vg["signal_date"].max()
n_pairs = vg[["ticker", "signal_date"]].drop_duplicates().shape[0]
print(f"  Verdict-grade fires (primary): {n_fires_total:,}")
print(f"  Unique (ticker,signal_date) pairs: {n_pairs:,}  (1:1 with fires: {n_pairs == n_fires_total})")
print(f"  Episode clusters: {n_ep_clusters:,}")
print(f"  Effective window: {era_min} -> {era_max}")
print()

# ── 2. Production washout (PIT) — VERBATIM concordance computation path ──────────
print("Computing PRODUCTION washout_ctx (PIT-sliced) for every fire pair ...")
print("  (path copied verbatim from scripts/p2_1b_concordance_check.py @ 4bebc06716)")

pairs = vg[["ticker", "signal_date"]].drop_duplicates()
prod_cache = {}   # per-ticker price series cache (avoids re-reading)
results = {}      # (ticker, Timestamp) -> bool | None
n_errors = 0
t0 = time.time()
for i, row in enumerate(pairs.itertuples()):
    ticker = row.ticker
    sd = pd.Timestamp(row.signal_date)
    try:
        if ticker not in prod_cache:
            prod_cache[ticker] = pd.read_parquet(MSD_DIR / f"{ticker}.parquet")["close"]
        price = prod_cache[ticker]
        pit = price[price.index <= sd]
        results[(ticker, sd)] = washout_ctx(pit)
    except Exception:
        results[(ticker, sd)] = None
        n_errors += 1
    if i > 0 and i % 20000 == 0:
        print(f"    {i:,}/{len(pairs):,} ({time.time()-t0:.0f}s)", flush=True)
print(f"  Done: {len(results):,} pairs in {time.time()-t0:.0f}s, errors={n_errors}")

n_prod_true = sum(1 for v in results.values() if v is True)
n_prod_false = sum(1 for v in results.values() if v is False)
n_prod_none = sum(1 for v in results.values() if v is None)
print(f"  Production: True={n_prod_true:,}  False={n_prod_false:,}  None={n_prod_none:,}")

# Map production value onto every fire row
vg["prod_washout_ctx"] = [
    results.get((t, pd.Timestamp(s))) for t, s in zip(vg["ticker"], vg["signal_date"])
]

# ── 2b. Concordance reproduction gate (must reproduce 66.40% before proceeding) ──
valid = vg[vg["washout_proximity"].notna() & vg["prod_washout_ctx"].notna()].copy()
n_valid = len(valid)
agree = valid["washout_proximity"].astype(bool) == valid["prod_washout_ctx"].astype(bool)
concordance = float(agree.mean())
proxy_false_prod_true = int(((valid["washout_proximity"] == False) & (valid["prod_washout_ctx"] == True)).sum())
print()
print("CONCORDANCE REPRODUCTION CHECK (must match concordance_check.json):")
print(f"  n_valid_pairs   = {n_valid:,}   (ref {CONCORDANCE_REF['n_valid_pairs']:,})")
print(f"  concordance     = {concordance:.6f}   (ref {CONCORDANCE_REF['concordance_rate']:.6f})")
print(f"  n_prod_true     = {n_prod_true:,}   (ref {CONCORDANCE_REF['n_prod_true']:,})")
print(f"  proxy_false_prod_true = {proxy_false_prod_true:,}")
concordance_reproduced = (
    n_valid == CONCORDANCE_REF["n_valid_pairs"]
    and abs(concordance - CONCORDANCE_REF["concordance_rate"]) < 1e-4
    and n_prod_true == CONCORDANCE_REF["n_prod_true"]
    and n_prod_false == CONCORDANCE_REF["n_prod_false"]
    and n_prod_none == CONCORDANCE_REF["n_prod_none"]
)
print(f"  REPRODUCED EXACTLY: {concordance_reproduced}")
if not concordance_reproduced:
    print("  !!! WARNING: production values do NOT reproduce the concordance artifact.")
    print("      Reprobe proceeds for the record but transfer provenance is broken.")
print()

# ── 3. F1 ENCODING on PRODUCTION washout (replaces the proxy) ───────────────────
# PRODUCTION-VALUE POPULATION: fires where the production washout is DEFINED
# (prod_washout_ctx not None). None => insufficient PIT history (< 308 bars) — these
# rows have no production washout state, so they cannot enter an F1 production trial.
# The reprobe population is therefore the prod-defined sub-population.
vg["F1_prod_defined"] = vg["prod_washout_ctx"].notna()
pop = vg[vg["F1_prod_defined"]].copy()
n_reprobe_pop = len(pop)
n_reprobe_ep = pop["episode_id"].nunique()
pop["F1_pass"] = pop["prod_washout_ctx"].astype(bool)     # production washout = favorable = group A
wp_true = int(pop["F1_pass"].sum())
wp_false = int((~pop["F1_pass"]).sum())
print("F1 PRODUCTION ENCODING:")
print(f"  Reprobe population (prod washout defined): {n_reprobe_pop:,} fires "
      f"({n_reprobe_pop/n_fires_total*100:.1f}% of {n_fires_total:,}); "
      f"{n_prod_none:,} None-history fires excluded")
print(f"  F1_pass (production washout True):  {wp_true:,}")
print(f"  F1_pass False (not in washout):     {wp_false:,}")
print(f"  Production fire-rate impact if HG-gated: block {wp_false:,}/{n_reprobe_pop:,} "
      f"= {wp_false/n_reprobe_pop*100:.1f}%")
print(f"  (P1.3 proxy fire-rate impact was 54.0% = 26,974/49,939 would-block)")
print()

# ── 3b. Rank-weight F1 bonus encoding (same formula as run_P1_3_v2.py) ───────────
weight_min, weight_max = pop["weight"].min(), pop["weight"].max()
pop["base_rank"] = (pop["weight"] - weight_min) / (weight_max - weight_min)
pop["F1_bonus"] = np.where(pop["F1_pass"], 0.10, 0.0)
pop["F1_rw_score"] = pop["base_rank"] + pop["F1_bonus"]
pop["F1_rank_before"] = pop.groupby("signal_date")["base_rank"].rank(method="first", ascending=True)
pop["F1_rank_after"] = pop.groupby("signal_date")["F1_rw_score"].rank(method="first", ascending=True)
pop["F1_moved_up"] = pop["F1_rank_after"] > pop["F1_rank_before"]

# ── 4. Statistics core — COPIED VERBATIM from run_P1_3_v2.py ─────────────────────

def rank_biserial_from_u(u_stat, n_a, n_b):
    """Rank-biserial r = 1 - 2U/(n_a*n_b). r>0 => group A stochastically larger."""
    return 1.0 - (2.0 * u_stat) / (n_a * n_b)


def episode_permutation_mwu(values, ep_ids, group_a_mask, n_perm=N_PERM, rng_seed=SEED):
    """VALID episode-clustered inference via EPISODE-LEVEL LABEL PERMUTATION.
    (verbatim from run_P1_3_v2.py — the calibrated P1.3 round-2 statistic)"""
    values = np.asarray(values, dtype=float)
    ep_ids = np.asarray(ep_ids)
    group_a_mask = np.asarray(group_a_mask, dtype=bool)

    n_a = int(group_a_mask.sum())
    n_b = int((~group_a_mask).sum())
    if n_a == 0 or n_b == 0:
        return np.nan, np.nan, np.nan, np.nan, 0, 0

    a_vals = values[group_a_mask]
    b_vals = values[~group_a_mask]
    obs_u, param_p = stats.mannwhitneyu(a_vals, b_vals, alternative="two-sided")
    r_bis = rank_biserial_from_u(obs_u, n_a, n_b)
    expected_u = n_a * n_b / 2.0
    obs_dev = abs(obs_u - expected_u)

    uniq_ep, ep_inv = np.unique(ep_ids, return_inverse=True)
    n_ep = len(uniq_ep)
    ep_is_a = np.zeros(n_ep, dtype=bool)
    ep_sizes = np.bincount(ep_inv, minlength=n_ep)
    first_seen = np.full(n_ep, -1, dtype=np.int64)
    for i in range(len(ep_inv)):
        e = ep_inv[i]
        if first_seen[e] == -1:
            first_seen[e] = i
            ep_is_a[e] = group_a_mask[i]
    n_ep_a = int(ep_is_a.sum())
    n_ep_b = n_ep - n_ep_a

    ranks = stats.rankdata(values)
    ep_rank_sum = np.zeros(n_ep, dtype=float)
    np.add.at(ep_rank_sum, ep_inv, ranks)

    rng = np.random.default_rng(rng_seed)
    perm_devs = np.empty(n_perm, dtype=float)
    ep_index = np.arange(n_ep)
    for i in range(n_perm):
        perm = rng.permutation(ep_index)
        a_eps = perm[:n_ep_a]
        rank_sum_a = ep_rank_sum[a_eps].sum()
        n_rows_a = ep_sizes[a_eps].sum()
        n_rows_b = len(values) - n_rows_a
        u_a = rank_sum_a - n_rows_a * (n_rows_a + 1) / 2.0
        exp_u_perm = n_rows_a * n_rows_b / 2.0
        perm_devs[i] = abs(u_a - exp_u_perm)

    perm_p = float((perm_devs >= obs_dev).sum() + 1) / (n_perm + 1)
    return float(obs_u), float(param_p), perm_p, float(r_bis), n_ep_a, n_ep_b


def assert_episode_label_purity(sub, pass_col):
    g = sub.groupby("episode_id")[pass_col].nunique()
    return int((g > 1).sum())


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


# ── 5. MANDATORY negative calibration control ON THE NEW ENCODING ───────────────
print("─" * 72)
print("NEGATIVE CALIBRATION CONTROL (mandatory — on the production-washout encoding)")
print("─" * 72)
# Representative config matching P1.3 calibration: F1 hard-gate at 21d, fwd_ret_21,
# on the reprobe (production-defined) population; episode = cluster; permuted labels.
calib_vals = pop["fwd_ret_21"].values.astype(float)
calib_ep = pop["episode_id"].values
_real_a_mask = pop["F1_pass"].values.astype(bool)

uniq_ep_c, ep_inv_c = np.unique(calib_ep, return_inverse=True)
n_ep_c = len(uniq_ep_c)
ep_is_a_real = np.zeros(n_ep_c, dtype=bool)
_seen = np.full(n_ep_c, -1, dtype=np.int64)
for i in range(len(ep_inv_c)):
    e = ep_inv_c[i]
    if _seen[e] == -1:
        _seen[e] = i
        ep_is_a_real[e] = _real_a_mask[i]
n_ep_a_real = int(ep_is_a_real.sum())

N_NEG = 200  # >= PREREG floor of 100 permuted-label draws
neg_rng = np.random.default_rng(777)
ep_inv_c_arr = np.asarray(ep_inv_c)
neg_pvals = []
for k in range(N_NEG):
    perm = neg_rng.permutation(n_ep_c)
    a_eps = perm[:n_ep_a_real]
    a_ep_set = np.zeros(n_ep_c, dtype=bool)
    a_ep_set[a_eps] = True
    null_mask = a_ep_set[ep_inv_c_arr]
    _, _, pp, _, _, _ = episode_permutation_mwu(
        calib_vals, calib_ep, null_mask, n_perm=1000, rng_seed=1000 + k
    )
    neg_pvals.append(pp)
neg_pvals = np.array(neg_pvals)
neg_reject = float((neg_pvals <= 0.05).mean())
ks_stat, ks_p = stats.kstest(neg_pvals, "uniform")
print(f"  draws: {N_NEG} (>=100 floor)")
print(f"  rejection rate @alpha=0.05: {neg_reject:.3f}  (expect ~0.05)")
print(f"  p-dist: mean={neg_pvals.mean():.3f} median={np.median(neg_pvals):.3f} "
      f"min={neg_pvals.min():.3f} max={neg_pvals.max():.3f}")
print(f"  KS-uniformity: D={ks_stat:.3f}, p={ks_p:.3f}")
neg_pass = (neg_reject <= 0.12) and (ks_p >= 0.01)
print(f"  NEGATIVE control: {'PASS' if neg_pass else 'FAIL'}")
print()

# ── 5b. POSITIVE control (parity with P1.3; confirms instrument fires) ──────────
pos_rng = np.random.default_rng(2024)
pos = pop.copy()
ep_assign = {ep: (pos_rng.random() < 0.5) for ep in uniq_ep_c}
pos["synthA"] = pos["episode_id"].map(ep_assign).astype(bool)
pos["fwd_pos"] = pos["fwd_ret_21"].astype(float).values
SHIFT = 0.05
pos.loc[pos["synthA"], "fwd_pos"] = pos.loc[pos["synthA"], "fwd_pos"] + SHIFT
_, param_p_p, perm_p_p, r_p, _, _ = episode_permutation_mwu(
    pos["fwd_pos"].values, pos["episode_id"].values, pos["synthA"].values, n_perm=N_PERM, rng_seed=55
)
pos_pass = perm_p_p < 0.05
print(f"POSITIVE control (inject +{SHIFT} return shift): perm_p={perm_p_p:.2e} "
      f"param_p={param_p_p:.2e} r={r_p:+.4f} -> {'PASS' if pos_pass else 'FAIL'}")
print()

calibration_summary = {
    "encoding": "production washout_ctx (engine.coiled), reprobe population",
    "negative_control": {
        "n_runs": N_NEG,
        "rejection_rate_alpha05": neg_reject,
        "p_mean": float(neg_pvals.mean()),
        "p_median": float(np.median(neg_pvals)),
        "ks_uniform_D": float(ks_stat),
        "ks_uniform_p": float(ks_p),
        "pass": bool(neg_pass),
    },
    "positive_control": {
        "injected_shift": SHIFT, "perm_p": float(perm_p_p),
        "param_p": float(param_p_p), "r_biserial": float(r_p), "pass": bool(pos_pass),
    },
    "overall_pass": bool(neg_pass and pos_pass),
}
if not calibration_summary["overall_pass"]:
    print("!!! CALIBRATION FAILED on the production encoding — verdicts not trustworthy.")
    print("    (Grid runs for the record; a grid result without calibration is unacceptable.)")
print()

# ── 6. Both-halves split (chronological, on reprobe population) ─────────────────
dates_sorted = np.sort(pop["signal_date"].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
half1 = pop[pop["signal_date"] <= midpoint]
half2 = pop[pop["signal_date"] > midpoint]
print(f"Both-halves split: midpoint={midpoint} | H1 n={len(half1):,} | H2 n={len(half2):,}")
print()

# ── 7. Trial grid — T01-T10 (F1 only), same targets/horizons as P1.3 §3.3 ───────
HORIZON_CONFIG = {21: ("fwd_ret_21", "state_8_21"), 63: ("fwd_ret_63", "state_15_126")}
# Reprobe trial ids map 1:1 to P1.3 F1 trials T01-T10 (identical (mode,horizon,target))
TRIAL_GRID = [
    ("P2_1B_F1_REPROBE_T01", "T01", "HG", 21, "STOPPED"),
    ("P2_1B_F1_REPROBE_T02", "T02", "HG", 21, "DEAD_MONEY"),
    ("P2_1B_F1_REPROBE_T03", "T03", "HG", 21, "CUSHIONED"),
    ("P2_1B_F1_REPROBE_T04", "T04", "HG", 63, "STOPPED"),
    ("P2_1B_F1_REPROBE_T05", "T05", "HG", 63, "DEAD_MONEY"),
    ("P2_1B_F1_REPROBE_T06", "T06", "HG", 63, "CUSHIONED"),
    ("P2_1B_F1_REPROBE_T07", "T07", "RW", 21, "STOPPED"),
    ("P2_1B_F1_REPROBE_T08", "T08", "RW", 21, "CUSHIONED"),
    ("P2_1B_F1_REPROBE_T09", "T09", "RW", 63, "STOPPED"),
    ("P2_1B_F1_REPROBE_T10", "T10", "RW", 63, "CUSHIONED"),
]
assert len(TRIAL_GRID) == 10

# Episode-label purity (production encoding)
purity = {
    "F1_HG_prod": assert_episode_label_purity(pop, "F1_pass"),
    "F1_RW_prod": assert_episode_label_purity(pop, "F1_moved_up"),
}
print("Episode-label purity (production encoding):")
for k, v in purity.items():
    print(f"  {k}: impure episodes = {v}")
print()

print("─" * 72)
print(f"EXECUTING 10 REPROBE TRIALS (episode label-permutation null, N_PERM={N_PERM})")
print("─" * 72)

SANITY_DIVERGENCE_ORDERS = 6
trial_results = {}
sanity_flags = []

for trial_id, p13_id, mode, horizon, ts_target in TRIAL_GRID:
    fwd_col, state_col = HORIZON_CONFIG[horizon]

    if mode == "HG":
        a_mask = (pop["F1_pass"] == True).values
    else:
        a_mask = (pop["F1_moved_up"] == True).values

    group_A = pop[a_mask]
    group_B = pop[~a_mask]
    n_A, n_B = len(group_A), len(group_B)
    n_ep_A = group_A["episode_id"].nunique()
    n_ep_B = group_B["episode_id"].nunique()
    is_thin = (n_ep_A < THIN_FLOOR) or (n_ep_B < THIN_FLOOR)

    ts_A = terminal_state_rates(group_A, state_col)
    ts_B = terminal_state_rates(group_B, state_col)
    delta_pp = (ts_A.get(ts_target, np.nan) - ts_B.get(ts_target, np.nan)) * 100

    if ts_target in ("STOPPED", "DEAD_MONEY"):
        delta_favorable = delta_pp < 0
    else:
        delta_favorable = delta_pp > 0

    if n_A > 0 and n_B > 0 and not is_thin:
        vals = pop[fwd_col].values.astype(float)
        eps = pop["episode_id"].values
        valid_fwd = ~np.isnan(vals)
        obs_u, param_p, perm_p, r_bis, nea, neb = episode_permutation_mwu(
            vals[valid_fwd], eps[valid_fwd], a_mask[valid_fwd], n_perm=N_PERM, rng_seed=SEED
        )
    else:
        obs_u = param_p = perm_p = r_bis = np.nan
        nea = neb = 0

    if not (np.isnan(param_p) or np.isnan(perm_p)) and param_p > 0:
        if perm_p > 0.3 and param_p < 10 ** (-SANITY_DIVERGENCE_ORDERS):
            sanity_flags.append((trial_id, param_p, perm_p))

    half_deltas = []
    for half_data in [half1, half2]:
        if mode == "HG":
            hA = half_data[half_data["F1_pass"] == True]
            hB = half_data[half_data["F1_pass"] == False]
        else:
            hA = half_data[half_data["F1_moved_up"] == True]
            hB = half_data[half_data["F1_moved_up"] == False]
        tsa = terminal_state_rates(hA, state_col)
        tsb = terminal_state_rates(hB, state_col)
        half_deltas.append((tsa.get(ts_target, np.nan) - tsb.get(ts_target, np.nan)) * 100)

    if not any(np.isnan(half_deltas)):
        sign_stable = (half_deltas[0] > 0) == (half_deltas[1] > 0)
    else:
        sign_stable = False

    trial_results[trial_id] = {
        "trial_id": trial_id, "p13_trial": p13_id, "factor": "F1", "mode": mode,
        "horizon": horizon, "ts_target": ts_target,
        "n_A": n_A, "n_B": n_B, "n_ep_A": n_ep_A, "n_ep_B": n_ep_B, "is_thin": is_thin,
        "ts_rate_A": ts_A.get(ts_target, np.nan), "ts_rate_B": ts_B.get(ts_target, np.nan),
        "delta_pp": delta_pp, "delta_favorable": bool(delta_favorable),
        "perm_p": perm_p, "param_p": param_p, "r_biserial": r_bis,
        "sign_stable": bool(sign_stable),
        "half1_delta_pp": half_deltas[0], "half2_delta_pp": half_deltas[1],
        "bh_adj_p": np.nan, "survives_bh": False,
    }
    print(f"  {trial_id} (~{p13_id}): {mode} {horizon}d {ts_target:12s} "
          f"Δ={delta_pp:+7.2f}pp fav={'Y' if delta_favorable else 'N'} "
          f"perm_p={perm_p:.4f} param_p={param_p:.2e} r={r_bis:+.4f} "
          f"sign={'Y' if sign_stable else 'N'} {'THIN' if is_thin else ''}")

print()
if sanity_flags:
    print("!!! SANITY GATE TRIPPED — param_p/perm_p divergence (round-1 defect signature):")
    for tid, pp, bp in sanity_flags:
        print(f"    {tid}: param_p={pp:.2e} perm_p={bp:.4f}")
    print("    HALTING.")
    sys.exit(2)
else:
    print("Sanity gate: PASS — no param/perm divergence of the round-1 defect signature.")
print()

# ── 8. BH correction — family = the 10 reprobe trials only ──────────────────────
all_ids = [t[0] for t in TRIAL_GRID]
perm_ps = [trial_results[tid]["perm_p"] for tid in all_ids]
perm_ps_safe = [p if not np.isnan(p) else 1.0 for p in perm_ps]
bh_adj = bh_correction(perm_ps_safe, q=BH_Q)
for i, tid in enumerate(all_ids):
    trial_results[tid]["bh_adj_p"] = float(bh_adj[i])
    trial_results[tid]["survives_bh"] = bool(bh_adj[i] <= BH_Q)
n_survive = sum(trial_results[t]["survives_bh"] for t in all_ids)
min_bh = min(trial_results[t]["bh_adj_p"] for t in all_ids)
print(f"BH q<=0.10 across m=10 (family={BH_FAMILY}): n_survive={n_survive}, min BH-adj p={min_bh:.4f}")
print()

# ── 9. Fire-rate impact of production washout (HG context) ──────────────────────
fire_impact_prod = {
    "n_fires_reprobe_pop": n_reprobe_pop,
    "n_would_pass": wp_true,
    "n_would_block": wp_false,
    "gate_fire_rate_impact_pct": round(100.0 * wp_false / n_reprobe_pop, 4),
    "n_clusters_would_block": int(pop[pop["F1_pass"] == False]["episode_id"].nunique()),
    "note_vs_proxy": "P1.3 proxy fire-rate impact was 54.0% (26,974/49,939); production finds MORE washout so blocks FEWER (block=not-in-washout).",
}

# ── 10. Reprobe verdict (PREREG §3.3 / §8) ──────────────────────────────────────
# Safety-net axes = stop-out (T04/T09 63d, T01/T07 21d) and dead-money (T02/T05).
# Promotion proceeds ONLY IF production trials reproduce BH-surviving + sign-stable
# FAVORABLE effects on the safety-net axes. The P1.3 ship-qualifying RW trial is T09
# (63d stop-out); HG context is T02 (dead-money) + T04 (63d stop-out).
def survived_favorable(tid):
    tr = trial_results[tid]
    return bool(tr["survives_bh"] and tr["delta_favorable"] and tr["sign_stable"] and not tr["is_thin"])

t02 = trial_results["P2_1B_F1_REPROBE_T02"]   # HG 21d dead-money
t04 = trial_results["P2_1B_F1_REPROBE_T04"]   # HG 63d stop-out
t07 = trial_results["P2_1B_F1_REPROBE_T07"]   # RW 21d stop-out
t09 = trial_results["P2_1B_F1_REPROBE_T09"]   # RW 63d stop-out (ship-qualifying)

# RW ship axis (the mode that ships per P1.3 §6.2 gate-reject) = 63d stop-out (T09)
rw_stop_63_ok = survived_favorable("P2_1B_F1_REPROBE_T09")
# HG safety-net context (dead-money 21d, stop-out 63d)
hg_dm_21_ok = survived_favorable("P2_1B_F1_REPROBE_T02")
hg_stop_63_ok = survived_favorable("P2_1B_F1_REPROBE_T04")

# Promotion decision: the RW mode is the one being promoted (§ scope of P2.1b).
# Reproduce = the ship-qualifying RW safety-net effect (T09 63d stop-out) survives
# BH + sign-stable + favorable on the production encoding.
promotion_survives = rw_stop_63_ok

if promotion_survives:
    reprobe_verdict = "PROMOTION_PROCEEDS"
    verdict_detail = (
        "Production-value F1 RW trials reproduce a BH-surviving, sign-stable, favorable "
        "safety-net effect (T09 63d stop-out). F1 rank-weight promotion proceeds on "
        "production COILED values; the shadow may ship with the production input."
    )
else:
    reprobe_verdict = "PROMOTION_DIES_PROXY_ONLY"
    verdict_detail = (
        "Production-value F1 trials do NOT reproduce a BH-surviving, sign-stable, favorable "
        "effect on the RW safety-net axis (T09 63d stop-out). Per PREREG §3.3, F1 rank-weight "
        "promotion DIES; the P1.3 F1 verdict is re-scoped 'proxy-definition only'."
    )

reprobe_decision = {
    "rw_stop_63_survives_favorable": rw_stop_63_ok,
    "hg_deadmoney_21_survives_favorable": hg_dm_21_ok,
    "hg_stop_63_survives_favorable": hg_stop_63_ok,
    "rw_stop_21_survives_favorable": survived_favorable("P2_1B_F1_REPROBE_T07"),
    "promotion_survives": bool(promotion_survives),
    "verdict": reprobe_verdict,
    "detail": verdict_detail,
}

print("─" * 72)
print("REPROBE VERDICT")
print("─" * 72)
print(f"  RW 63d stop-out (T09) survives favorable: {rw_stop_63_ok}")
print(f"  HG 21d dead-money (T02) survives favorable: {hg_dm_21_ok}")
print(f"  HG 63d stop-out  (T04) survives favorable: {hg_stop_63_ok}")
print(f"  VERDICT: {reprobe_verdict}")
print(f"  {verdict_detail}")
print()

# ── 11. Side-by-side vs P1.3 proxy numbers ──────────────────────────────────────
with open(P13_RESULTS) as f:
    p13 = json.load(f)
p13_trials = p13["trials"]

def _num(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)

side_by_side = {}
for trial_id, p13_id, mode, horizon, ts_target in TRIAL_GRID:
    r = trial_results[trial_id]
    p = p13_trials[p13_id]
    side_by_side[p13_id] = {
        "mode": mode, "horizon": horizon, "ts_target": ts_target,
        "proxy": {
            "delta_pp": _num(p["delta_pp"]), "favorable": p["delta_favorable"],
            "perm_p": _num(p["perm_p"]), "bh_adj_p": _num(p["bh_adj_p"]),
            "survives_bh": p["survives_bh"], "sign_stable": p["sign_stable"],
            "r_biserial": _num(p["r_biserial"]), "n_A": p["n_A"], "n_B": p["n_B"],
        },
        "production": {
            "delta_pp": _num(r["delta_pp"]), "favorable": r["delta_favorable"],
            "perm_p": _num(r["perm_p"]), "bh_adj_p": _num(r["bh_adj_p"]),
            "survives_bh": r["survives_bh"], "sign_stable": r["sign_stable"],
            "r_biserial": _num(r["r_biserial"]), "n_A": r["n_A"], "n_B": r["n_B"],
        },
    }

# ── 12. Save results.json ────────────────────────────────────────────────────────
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
    "bh_family": BH_FAMILY,
    "study_date": "2026-07-05",
    "prereg": "research/entry_intel/P2_1B_RANKWEIGHT_PREREG.md §3.3/§8/§11",
    "memo_version": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments",
    "primary_test": "episode-level label-permutation Mann-Whitney U (N_PERM=5000, two-sided, Phipson-Smyth +1) — verbatim from run_P1_3_v2.py",
    "production_signal": "engine.coiled.washout_ctx (>=15% dd from 126d pre-cap high within 91 bars; PIT-sliced daily close)",
    "production_path_provenance": "scripts/p2_1b_concordance_check.py @ 4bebc06716 (verbatim compute path); engine/coiled.py byte-identical to that commit",
    "replay_path": str(REPLAY_PATH),
    "replay_md5": replay_md5,
    "replay_md5_matches_concordance": replay_md5 == EXPECTED_REPLAY_MD5,
    "concordance_reference": CONCORDANCE_REF,
    "concordance_reproduced_exactly": bool(concordance_reproduced),
    "concordance_reproduction": {
        "n_valid_pairs": n_valid, "concordance_rate": round(concordance, 6),
        "n_prod_true": n_prod_true, "n_prod_false": n_prod_false, "n_prod_none": n_prod_none,
        "proxy_false_prod_true": proxy_false_prod_true,
    },
    "population": {
        "n_fires_verdict_grade": n_fires_total,
        "n_reprobe_population": n_reprobe_pop,
        "n_none_history_excluded": n_prod_none,
        "n_episode_clusters_all": n_ep_clusters,
        "n_episode_clusters_reprobe": n_reprobe_ep,
        "era_min": str(era_min), "era_max": str(era_max),
        "prod_washout_true": wp_true, "prod_washout_false": wp_false,
    },
    "fire_rate_impact_production": fire_impact_prod,
    "calibration": calibration_summary,
    "episode_label_purity": purity,
    "sanity_gate": {"tripped": bool(sanity_flags), "flags": [list(x) for x in sanity_flags]},
    "bh_family_m": 10, "bh_q": BH_Q, "n_perm": N_PERM,
    "n_survive_bh": int(n_survive), "min_bh_adj_p": float(min_bh),
    "midpoint": str(midpoint), "n_half1": int(len(half1)), "n_half2": int(len(half2)),
    "trials": {tid: {k: _clean(v) for k, v in trial_results[tid].items()} for tid in trial_results},
    "side_by_side_vs_p13_proxy": side_by_side,
    "reprobe_decision": reprobe_decision,
}

with open(OUT_DIR / "results.json", "w") as f:
    json.dump(results_out, f, indent=2, default=str)
print(f"Saved: {OUT_DIR / 'results.json'}")
print()
print("=" * 72)
print(f"{STUDY_ID} RUN COMPLETE — verdict: {reprobe_verdict}")
print("=" * 72)
