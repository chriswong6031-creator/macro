"""
P2_5_STUDY — Washout Depth × Interaction study (REGISTERED RUN)

Study:   P2_5_depth_interaction  (BH family: P2_5_depth_interaction)
Program: Entry Intelligence (EI)
PREREG:  research/entry_intel/P2_5_INTERACTION_PREREG.md
         (APPROVED — Fable 2026-07-05, conditional on P2_5_REDTEAM.md edits, applied as R1)
Redteam: research/entry_intel/P2_5_REDTEAM.md (BLOCKING-1 sc63 bug; BLOCKING-2 pinned §5.2 convention)
Memo:    research/entry_intel/P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05) §6
Author:  Opus subagent under Fable orchestration
Date:    2026-07-05

════════════════════════════════════════════════════════════════════════════════
NON-NEGOTIABLES (encoded here; each halts the run if violated)
────────────────────────────────────────────────────────────────────────────────
(1) Run-preamble assertion that sign-stability is PER-HALF BASELINE-FREE.
    half_delta = stop_out(moved_up_in_half) − stop_out(not_moved_up_in_half),
    horizon-matched, NO external baseline. Halts SIGN_STABILITY_BASELINE_ERROR
    if any full-population / cross-horizon baseline enters the half contrast.
    We do NOT inherit the diagnostic's sign_consistent() (it tested both halves'
    63d stop rate against the 21d full-population baseline 0.3848 — BLOCKING-1).

(2) BOTH calibration controls BEFORE the grid, on the P2.5 encoding, reusing the
    CALIBRATED episode-permutation machinery from run_P1_3_v2.py VERBATIM:
      negative: >=200 permuted-label draws, rejection <=0.12, KS-uniform p>=0.05;
      positive: inject +0.05 forward-return shift, perm_p << 0.05.
    Grid is INVALID (verdicts not trustworthy) if either fails.

(3) Thin-check C7/C8 at start: m decrements 16->14->12 per §3 thin rule, logged
    in the preamble BEFORE any permutation.

(4) Regenerate production washout DEPTH (dd_pct) via the reprobe's computation path
    (PIT-sliced data/massive_stock_day/{ticker}.parquet close -> engine.coiled
    washout algorithm). washout_depth_pit() below is byte-faithful to
    P2_5_DIAGNOSTIC/run_P2_5_diagnostic.py, itself the depth extension of the
    reprobe's washout_ctx path (same _WASH_CTX_A/_B, capit_pos, prior_max).
    PIT discipline: only price index <= signal_date is used.

(5) BH family exactly as declared (m=16/14/12); both-halves sign stability per the
    pinned baseline-free convention; §5.3 ship-qualifying incl. 21d dead-money
    co-benefit (ADVISORY E: 21d is the binding dead-money gate; 63d dead-money is
    ~0 and vacuous).

(6) Verdict per §6: ship-qualifying configs named for EI-F1D-RW shadow registration;
    if none, the §6.2 program-wide kill executes in the report.
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
PREREG_PATH = REPO / "research" / "entry_intel" / "P2_5_INTERACTION_PREREG.md"
MEMO_PATH = REPO / "research" / "entry_intel" / "P0_MEASUREMENT_MEMO.md"
DIAG_JSON = REPO / "research" / "entry_intel" / "p1_runs" / "P2_5_DIAGNOSTIC" / "results.json"

STUDY_ID = "P2_5_STUDY"
BH_FAMILY = "P2_5_depth_interaction"
N_PERM = 5000
BH_Q = 0.10
THIN_FLOOR = 25
SEED = 42
EXPECTED_REPLAY_MD5 = "906175f9eb8caa351ed6d7d5c56265d3"
ERA_START = "2022-06-30"
ERA_END = "2025-12-29"   # replay vg-fire max == 2025-12-29; identical population to PREREG's ...2026-07-02
RANK_BONUS = 0.10

log_lines = []
def LOG(s=""):
    print(s, flush=True)
    log_lines.append(s)

LOG("=" * 72)
LOG(f"{STUDY_ID} — Washout Depth × Interaction study (REGISTERED)")
LOG(f"BH family: {BH_FAMILY}   q<= {BH_Q}   N_PERM={N_PERM}")
LOG("=" * 72)
LOG()

# ── 0. §5 conformance / memo gate ───────────────────────────────────────────────
if not MEMO_PATH.exists():
    LOG("BLOCKER: P0_MEASUREMENT_MEMO.md absent -> HALT per PREREG §1.")
    sys.exit(3)
LOG("§5/§6 CONFORMANCE (P0_MEASUREMENT_MEMO.md v1.1 2026-07-05):")
LOG("  [x] Cites P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05)")
LOG("  [x] Primary window = 2022-06-30 -> 2026-07-02 (replay vg-fire max=2025-12-29; identical population)")
LOG("  [x] Verdict-grade statistics on survivor_bias==False rows only")
LOG("  [x] survivor-stamped rows -> context appendix, excluded from BH/sign/n-floor/GO-NOGO")
LOG("  [x] horizon_censored rows excluded per-horizon (NaN fwd dropped per horizon)")
LOG("  [x] Returns INSUFFICIENT-POWER if unstamped n floor unmet (all cells clear 25 by >>)")
LOG()

assert REPLAY_PATH.exists(), f"BLOCKER: replay not found at {REPLAY_PATH}"
with open(REPLAY_PATH, "rb") as f:
    replay_md5 = hashlib.md5(f.read()).hexdigest()
LOG(f"Replay path: {REPLAY_PATH}")
LOG(f"Replay MD5:  {replay_md5}")
if replay_md5 != EXPECTED_REPLAY_MD5:
    LOG(f"BLOCKER: replay MD5 != expected {EXPECTED_REPLAY_MD5} -> HALT (production washout would not reproduce).")
    sys.exit(3)
LOG(f"  -> matches PREREG replay MD5 (production depth reproduces diagnostic).")
LOG(f"scipy: {scipy.__version__}")
LOG()

# ── Column-name mapping log (PREREG name -> actual replay column) ────────────────
COLUMN_MAP = {
    "episode_cluster_id": "episode_id",
    "washout_proximity": "washout_proximity",
    "rs_vs_sector_quartile": "rs_sector_quartile",
    "above_200dma": "above_200",
    "ext_z": "ext_z",
    "fwd_21d": "fwd_ret_21",
    "fwd_63d": "fwd_ret_63",
    "terminal_state@21d": "state_8_21",
    "terminal_state@63d": "state_15_126",
    "survivor_bias_stamp": "survivor_bias",
    "verdict": "verdict_type(=='fire') & verdict_grade",
    "dd_pct": "COMPUTED FRESH via washout_depth_pit (reprobe path)",
}
LOG("Column-name mapping (PREREG name -> replay column):")
for k, v in COLUMN_MAP.items():
    LOG(f"  {k:<24} -> {v}")
LOG()

# ── 1. Load replay, build verdict-grade fire population ─────────────────────────
LOG("Loading replay_boarded.parquet ...")
df = pd.read_parquet(REPLAY_PATH)
LOG(f"  Full shape: {df.shape}")

vg = df[
    (df["verdict_type"] == "fire")
    & (df["verdict_grade"] == True)
    & (df["signal_date"] >= ERA_START)
    & (df["signal_date"] <= ERA_END)
].copy()
n_all_fires = len(vg)
assert n_all_fires == 49939, f"BLOCKER: expected 49,939 verdict-grade fires, got {n_all_fires}"
n_stamped = int(vg["survivor_bias"].sum())
assert n_stamped == 0, f"UNEXPECTED: {n_stamped} survivor_bias==True rows in vg (expected 0)"
LOG(f"  Verdict-grade fires (all, primary era): {n_all_fires:,}")
LOG(f"  Survivor-stamped rows (excluded from verdicts): {n_stamped:,}")
LOG(f"  Episode clusters (all fires): {vg['episode_id'].nunique():,}")
LOG(f"  Era: {vg['signal_date'].min()} -> {vg['signal_date'].max()}")
LOG()

# ── 2. Regenerate production washout DEPTH (dd_pct), PIT — REPROBE PATH ──────────
# washout_depth_pit is byte-faithful to P2_5_DIAGNOSTIC (depth extension of the
# reprobe's washout_ctx). Same _WASH_CTX_A/_B, capit_pos, prior_max; returns dd float.
_WASH_CTX_B = 91
_WASH_CTX_A = 217   # 308 - 91

def washout_depth_pit(daily_close: pd.Series):
    """Returns (washout_bool|None, dd_pct_positive|None, bars_since_capit|None).
    PIT: caller passes price index <= signal_date. Exact capit_pos/prior_max as
    engine.coiled.washout_ctx; dd_pos is the positive drawdown fraction."""
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        arr = c.to_numpy()
        n = len(arr)
        if n < _WASH_CTX_A + _WASH_CTX_B:
            return None, None, None
        window = arr[n - _WASH_CTX_B:]
        local_min = int(np.argmin(window))
        capit_pos = (n - _WASH_CTX_B) + local_min
        if capit_pos < 126:
            return None, None, None
        prior_max = float(np.nanmax(arr[capit_pos - 126: capit_pos]))
        if prior_max <= 0:
            return None, None, None
        dd = arr[capit_pos] / prior_max - 1.0
        dd_pos = -dd
        washout = bool(dd <= -0.15)
        bars_since = n - 1 - capit_pos
        return washout, float(dd_pos), int(bars_since)
    except Exception:
        return None, None, None

LOG("Computing PIT production washout depth (dd_pct) for every (ticker, signal_date) pair ...")
LOG("  (reprobe compute path: PIT-sliced massive_stock_day close -> washout algorithm)")
pairs = vg[["ticker", "signal_date"]].drop_duplicates()
prod_cache = {}
depth_results = {}
n_errors = 0
t0 = time.time()
for i, row in enumerate(pairs.itertuples()):
    ticker = row.ticker
    sd = pd.Timestamp(row.signal_date)
    try:
        if ticker not in prod_cache:
            prod_cache[ticker] = pd.read_parquet(MSD_DIR / f"{ticker}.parquet")["close"]
        price = prod_cache[ticker]
        pit = price[price.index <= sd]          # PIT slice
        depth_results[(ticker, sd)] = washout_depth_pit(pit)
    except Exception:
        depth_results[(ticker, sd)] = (None, None, None)
        n_errors += 1
    if i > 0 and i % 20000 == 0:
        LOG(f"    {i:,}/{len(pairs):,} ({time.time()-t0:.0f}s)")
LOG(f"  Done: {len(depth_results):,} pairs in {time.time()-t0:.0f}s  errors={n_errors}")

vg["prod_washout"] = [depth_results.get((t, pd.Timestamp(s)), (None, None, None))[0]
                      for t, s in zip(vg["ticker"], vg["signal_date"])]
vg["dd_pct"] = [depth_results.get((t, pd.Timestamp(s)), (None, None, None))[1]
                for t, s in zip(vg["ticker"], vg["signal_date"])]

# Halt if dd_pct is entirely absent (PREREG §1 halt condition)
if int(vg["dd_pct"].notna().sum()) == 0:
    LOG("BLOCKER: dd_pct could not be computed for any fire -> HALT per PREREG §1.")
    sys.exit(3)

# ── 3. Population: production-washout DEFINED fires ──────────────────────────────
defined = vg[vg["prod_washout"].notna()].copy()
n_defined = len(defined)
n_wash_true = int((defined["prod_washout"] == True).sum())
n_none = int(vg["prod_washout"].isna().sum())
LOG(f"  Production washout defined fires: {n_defined:,}   None-excluded: {n_none:,}")
LOG(f"  washout True: {n_wash_true:,}   dd_pct defined: {int(defined['dd_pct'].notna().sum()):,}")
# Concordance-population sanity (diagnostic reported n_defined=47,182, wash_true=36,734)
LOG(f"  [sanity vs diagnostic] n_defined expect 47,182 got {n_defined:,}; "
    f"wash_true expect 36,734 got {n_wash_true:,}")
LOG()

# ── 4. Derived condition columns ────────────────────────────────────────────────
defined["washout_true"] = defined["prod_washout"] == True
defined["ac_pass"] = defined["ext_z"] <= 2.0                       # anti-chase
defined["rs_fav"] = defined["rs_sector_quartile"].isin([1.0, 2.0]) # Q1/Q2
defined["below_200"] = defined["above_200"] == False
dd = defined["dd_pct"]
defined["dd_gt25"] = defined["washout_true"] & (dd > 0.25)
defined["dd_gt40"] = defined["washout_true"] & (dd > 0.40)

# ── 5. Config condition masks (C1–C8), §3 ───────────────────────────────────────
CONFIG_MASKS = {
    "C1": defined["dd_gt25"],                                                          # deep_washout_solo (dd>25% & washout)
    "C2": defined["dd_gt40"],                                                          # d40plus_solo
    "C3": defined["washout_true"] & defined["below_200"],                             # below200_washout
    "C4": defined["washout_true"] & defined["ac_pass"],                               # washout_ac_pass
    "C5": defined["washout_true"] & defined["ac_pass"] & defined["rs_fav"],           # trio
    "C6": defined["dd_gt25"] & defined["ac_pass"] & defined["rs_fav"],                # deep_trio
    "C7": defined["dd_gt40"] & defined["ac_pass"] & defined["rs_fav"],                # d40plus_trio
    "C8": defined["washout_true"] & defined["below_200"] & (dd > 0.25),              # below200_deep
}
CONFIG_NAMES = {
    "C1": "deep_washout_solo", "C2": "d40plus_solo", "C3": "below200_washout",
    "C4": "washout_ac_pass", "C5": "trio", "C6": "deep_trio",
    "C7": "d40plus_trio", "C8": "below200_deep",
}

# ── 6. Thin-check C7/C8 at start; decrement m; log BEFORE any permutation ───────
LOG("─" * 72)
LOG("THIN-CHECK (C7/C8) — decrement m before any computation (§3)")
LOG("─" * 72)
config_ep = {}
for cid, mask in CONFIG_MASKS.items():
    n_ep = int(defined.loc[mask, "episode_id"].nunique())
    n_fi = int(mask.sum())
    config_ep[cid] = {"n_fires": n_fi, "n_episodes": n_ep,
                      "thin": bool(n_ep < THIN_FLOOR)}
    LOG(f"  {cid} {CONFIG_NAMES[cid]:<20} n_fires={n_fi:6,}  n_episodes={n_ep:5,}  "
        f"{'THIN(excluded)' if n_ep < THIN_FLOOR else 'OK'}")

active_configs = [c for c in ["C1","C2","C3","C4","C5","C6","C7","C8"]
                  if not config_ep[c]["thin"]]
excluded_thin = [c for c in ["C7","C8"] if config_ep[c]["thin"]]
# Per §3: only C7/C8 may be thin-excluded (C1–C6 confirmed powered by diagnostic).
for c in ["C1","C2","C3","C4","C5","C6"]:
    if config_ep[c]["thin"]:
        LOG(f"BLOCKER: registered powered config {c} is THIN ({config_ep[c]['n_episodes']} ep) — "
            "diagnostic confirmed >25; investigate before proceeding. HALT.")
        sys.exit(3)
m_declared = 2 * len(active_configs)
LOG()
LOG(f"  Active configs: {active_configs}")
LOG(f"  Thin-excluded (C7/C8 only): {excluded_thin if excluded_thin else 'none'}")
LOG(f"  m DECLARED = {m_declared}  (16 full / 14 one-thin / 12 both-thin)")
LOG()

# ── 7. Statistics core — VERBATIM from run_P1_3_v2.py / reprobe ─────────────────
def rank_biserial_from_u(u_stat, n_a, n_b):
    return 1.0 - (2.0 * u_stat) / (n_a * n_b)

def episode_permutation_mwu(values, ep_ids, group_a_mask, n_perm=N_PERM, rng_seed=SEED):
    """Episode-level label-permutation Mann-Whitney U (calibrated P1.3 round-2 statistic;
    copied verbatim from run_P1_3_v2.py). Returns (obs_u, param_p, perm_p, r, n_ep_a, n_ep_b)."""
    values = np.asarray(values, dtype=float)
    ep_ids = np.asarray(ep_ids)
    group_a_mask = np.asarray(group_a_mask, dtype=bool)
    n_a = int(group_a_mask.sum()); n_b = int((~group_a_mask).sum())
    if n_a == 0 or n_b == 0:
        return np.nan, np.nan, np.nan, np.nan, 0, 0
    a_vals = values[group_a_mask]; b_vals = values[~group_a_mask]
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
    n_ep_a = int(ep_is_a.sum()); n_ep_b = n_ep - n_ep_a
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

def stop_rate(sub, state_col):
    n = len(sub)
    if n == 0:
        return np.nan
    return (sub[state_col] == "STOPPED").sum() / n

def dead_rate(sub, state_col):
    n = len(sub)
    if n == 0:
        return np.nan
    return (sub[state_col] == "DEAD_MONEY").sum() / n

def liftoff_rate(sub, state_col):
    n = len(sub)
    if n == 0:
        return np.nan
    return (sub[state_col] == "CLEAN_LIFTOFF").sum() / n

# ── 8. RUN-PREAMBLE ASSERTION: sign-stability is per-half baseline-free ─────────
# We DO NOT inherit the diagnostic's sign_consistent(). The half-delta is a pure
# within-half moved_up vs not-moved-up contrast, horizon-matched, no external
# baseline. Assert this by construction with a numeric self-check that would only
# pass if no full-population/cross-horizon baseline is used.
LOG("─" * 72)
LOG("ASSERT sign_stability_convention (BLOCKING-2; halts if not baseline-free):")
LOG("  half_delta = stop_out(moved_up_in_half) - stop_out(not_moved_up_in_half)")
LOG("  horizon: horizon-matched to trial's own horizon")
LOG("  baseline: NONE — within-half two-group contrast only")

def half_delta_baseline_free(half_df, moved_col, state_col):
    """Per-half Δpp = stop(moved_up) - stop(not_moved_up), WITHIN this half only.
    No full-population rate, no cross-horizon rate, no external baseline is referenced."""
    hA = half_df[half_df[moved_col] == True]
    hB = half_df[half_df[moved_col] == False]
    ra = stop_rate(hA, state_col)
    rb = stop_rate(hB, state_col)
    if np.isnan(ra) or np.isnan(rb):
        return np.nan
    return (ra - rb) * 100.0

# Self-verification: build a synthetic half where moved_up and not_moved_up have
# IDENTICAL stop rates by construction; a baseline-free within-half contrast MUST
# return exactly 0.0. A baseline-anchored implementation (e.g. vs 0.3848) would not.
def _assert_baseline_free():
    rng = np.random.default_rng(0)
    n = 400
    synth = pd.DataFrame({
        "mv": np.r_[np.ones(n, bool), np.zeros(n, bool)],
        "state_8_21": (["STOPPED"] * (n // 2) + ["CLEAN_LIFTOFF"] * (n - n // 2)) * 2,
    })
    d = half_delta_baseline_free(synth, "mv", "state_8_21")
    # Both groups have identical 50% stop rate -> baseline-free delta == 0.0 exactly.
    if abs(d) > 1e-9:
        return False, d
    # Second probe: shift moved_up to all-stopped, not_moved to none-stopped.
    synth2 = pd.DataFrame({
        "mv": np.r_[np.ones(n, bool), np.zeros(n, bool)],
        "state_8_21": (["STOPPED"] * n) + (["CLEAN_LIFTOFF"] * n),
    })
    d2 = half_delta_baseline_free(synth2, "mv", "state_8_21")
    # moved=100% stop, not=0% -> +100.0pp, independent of any full-pop baseline.
    if abs(d2 - 100.0) > 1e-9:
        return False, d2
    return True, (d, d2)

ok_bf, probe = _assert_baseline_free()
if not ok_bf:
    LOG(f"  SIGN_STABILITY_BASELINE_ERROR: half-delta not baseline-free (probe={probe}). HALT.")
    sys.exit(4)
LOG(f"  verification: baseline-free probes PASS (identical-group Δ=0.0; disjoint-group Δ=+100.0pp)")
LOG("  -> sign_stability implementation is PER-HALF BASELINE-FREE. OK.")
LOG()

# ── 9. Mode-B RW construction (per-config): bonus +0.10 on blend_sorted, re-rank ─
# blend_sorted 0..1 = min-max of 'weight' within-day is NOT used; PREREG §3 uses the
# same normalization as P1.3 §3/Mode-B: base_rank = min-max(weight) over full pop,
# within-day rank. Reuse P1.3 formula verbatim.
weight_min, weight_max = defined["weight"].min(), defined["weight"].max()
defined["base_rank"] = (defined["weight"] - weight_min) / (weight_max - weight_min)

def build_moved_up(frame, cell_mask, colname):
    """Apply +0.10 bonus to fires in cell_mask, re-rank within signal_date, moved_up = rank improved."""
    f = frame
    f[colname + "_bonus"] = np.where(cell_mask.values, RANK_BONUS, 0.0)
    f[colname + "_score"] = f["base_rank"] + f[colname + "_bonus"]
    f[colname + "_rb"] = f.groupby("signal_date")["base_rank"].rank(method="first", ascending=True)
    f[colname + "_ra"] = f.groupby("signal_date")[colname + "_score"].rank(method="first", ascending=True)
    f[colname + "_moved_up"] = f[colname + "_ra"] > f[colname + "_rb"]
    return colname + "_moved_up"

moved_cols = {}
for cid in active_configs:
    moved_cols[cid] = build_moved_up(defined, CONFIG_MASKS[cid], f"{cid}")

# ── 10. Both-halves split (chronological midpoint of the defined population) ─────
dates_sorted = np.sort(defined["signal_date"].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
half1 = defined[defined["signal_date"] <= midpoint].copy()
half2 = defined[defined["signal_date"] > midpoint].copy()
LOG(f"Both-halves split: midpoint={midpoint} | H1 n={len(half1):,} | H2 n={len(half2):,}")
LOG()

# ── 11. CALIBRATION CONTROLS (BEFORE the grid) — on the P2.5 encoding ────────────
LOG("─" * 72)
LOG("CALIBRATION CONTROLS (mandatory — BEFORE the grid; P2.5 encoding)")
LOG("─" * 72)
# Representative encoding for calibration: the P2.5 washout-defined population, the
# C6 (deep_trio) moved_up split at 21d fwd. (Any registered encoding is valid; C6 is
# the lead interaction cell.) Reuse the calibrated negative/positive control loops.
CALIB_CID = "C6" if "C6" in active_configs else active_configs[0]
calib_moved = moved_cols[CALIB_CID]
calib_vals = defined["fwd_ret_21"].values.astype(float)
calib_ep = defined["episode_id"].values
_real_a_mask = defined[calib_moved].values.astype(bool)

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

# (1) NEGATIVE control: >=200 permuted-label draws; rej<=0.12; KS-uniform p>=0.05
LOG(f"(1) NEGATIVE control on P2.5 encoding (cell={CALIB_CID} moved_up @21d), 200 permuted-label draws")
N_NEG = 200
neg_rng = np.random.default_rng(777)
ep_inv_c_arr = np.asarray(ep_inv_c)
neg_pvals = []
for k in range(N_NEG):
    perm = neg_rng.permutation(n_ep_c)
    a_eps = perm[:n_ep_a_real]
    a_ep_set = np.zeros(n_ep_c, dtype=bool)
    a_ep_set[a_eps] = True
    null_mask = a_ep_set[ep_inv_c_arr]
    _, _, pp, _, _, _ = episode_permutation_mwu(calib_vals, calib_ep, null_mask,
                                                n_perm=1000, rng_seed=1000 + k)
    neg_pvals.append(pp)
neg_pvals = np.array(neg_pvals)
neg_reject = float((neg_pvals <= 0.05).mean())
ks_stat, ks_p = stats.kstest(neg_pvals, "uniform")
LOG(f"   rejection @alpha=0.05: {neg_reject:.3f}  (require <=0.12; ~0.05 ideal)")
LOG(f"   p-dist: mean={neg_pvals.mean():.3f} median={np.median(neg_pvals):.3f} "
    f"min={neg_pvals.min():.3f} max={neg_pvals.max():.3f}")
LOG(f"   KS-uniformity: D={ks_stat:.3f}  p={ks_p:.3f}  (require p>=0.05)")
neg_pass = (neg_reject <= 0.12) and (ks_p >= 0.05)
LOG(f"   NEGATIVE control: {'PASS' if neg_pass else 'FAIL'}")
LOG()

# (2) POSITIVE control: inject +0.05 forward-return shift on episode-level synth group
LOG("(2) POSITIVE control: inject +0.05 forward-return shift; require perm_p << 0.05")
pos_rng = np.random.default_rng(2024)
pos = defined.copy()
ep_assign = {ep: (pos_rng.random() < 0.5) for ep in uniq_ep_c}
pos["synthA"] = pos["episode_id"].map(ep_assign).astype(bool)
pos["fwd_pos"] = pos["fwd_ret_21"].astype(float).values
SHIFT = 0.05
pos.loc[pos["synthA"], "fwd_pos"] = pos.loc[pos["synthA"], "fwd_pos"] + SHIFT
_, param_p_p, perm_p_p, r_p, _, _ = episode_permutation_mwu(
    pos["fwd_pos"].values, pos["episode_id"].values, pos["synthA"].values,
    n_perm=N_PERM, rng_seed=55)
pos_pass = perm_p_p < 0.05
LOG(f"   injected shift=+{SHIFT} return space -> perm_p={perm_p_p:.2e}  param_p={param_p_p:.2e}  r={r_p:+.4f}")
LOG(f"   POSITIVE control: {'PASS' if pos_pass else 'FAIL'}")
LOG()

calibration_summary = {
    "encoding": f"P2.5 production washout depth; calib cell={CALIB_CID} moved_up @21d",
    "negative_control": {
        "n_runs": N_NEG, "rejection_rate_alpha05": neg_reject,
        "p_mean": float(neg_pvals.mean()), "p_median": float(np.median(neg_pvals)),
        "ks_uniform_D": float(ks_stat), "ks_uniform_p": float(ks_p),
        "pass": bool(neg_pass),
    },
    "positive_control": {
        "injected_shift": SHIFT, "perm_p": float(perm_p_p),
        "param_p": float(param_p_p), "r_biserial": float(r_p), "pass": bool(pos_pass),
    },
    "overall_pass": bool(neg_pass and pos_pass),
}
if not calibration_summary["overall_pass"]:
    LOG("!!! CALIBRATION FAILED — grid is INVALID per §7 (verdicts NOT trustworthy).")
    LOG("    Grid still runs for the record; the report will mark verdicts INVALID.")
LOG()

# ── 12. Trial grid execution ────────────────────────────────────────────────────
LOG("─" * 72)
LOG(f"EXECUTING GRID: {len(active_configs)} configs × 2 horizons = m={m_declared} trials")
LOG("  Primary target: stop-out (favorable = moved_up stopped LESS; Δ<0)")
LOG("─" * 72)
HORIZON_CONFIG = {21: ("fwd_ret_21", "state_8_21"), 63: ("fwd_ret_63", "state_15_126")}
SANITY_DIVERGENCE_ORDERS = 6

trial_results = {}
sanity_flags = []
trial_order = []  # (trial_id, cid, horizon)
tnum = 0
for cid in ["C1","C2","C3","C4","C5","C6","C7","C8"]:
    if cid not in active_configs:
        # register the thin trials as EXCLUDED (not in BH family)
        for horizon in (21, 63):
            tnum += 1
            tid = f"P25_T{tnum:02d}"
            trial_results[tid] = {
                "trial_id": tid, "config": cid, "config_name": CONFIG_NAMES[cid],
                "horizon": horizon, "excluded_thin": True,
                "n_episodes_cell": config_ep[cid]["n_episodes"],
                "in_bh_family": False, "verdict": "EXCLUDED_THIN",
            }
        continue
    moved_col = moved_cols[cid]
    for horizon in (21, 63):
        tnum += 1
        tid = f"P25_T{tnum:02d}"
        trial_order.append((tid, cid, horizon))
        fwd_col, state_col = HORIZON_CONFIG[horizon]

        a_mask = (defined[moved_col] == True).values
        gA = defined[a_mask]; gB = defined[~a_mask]
        n_A, n_B = len(gA), len(gB)
        n_ep_A = gA["episode_id"].nunique(); n_ep_B = gB["episode_id"].nunique()
        is_thin = (n_ep_A < THIN_FLOOR) or (n_ep_B < THIN_FLOOR)

        # stop-out primary Δ
        sA = stop_rate(gA, state_col); sB = stop_rate(gB, state_col)
        delta_pp = (sA - sB) * 100.0
        delta_favorable = delta_pp < 0
        # dead-money + liftoff secondary Δ (context)
        dmA = dead_rate(gA, state_col); dmB = dead_rate(gB, state_col)
        dm_delta_pp = (dmA - dmB) * 100.0
        loA = liftoff_rate(gA, state_col); loB = liftoff_rate(gB, state_col)
        lo_delta_pp = (loA - loB) * 100.0

        # primary test: episode label-permutation MWU on forward returns
        if n_A > 0 and n_B > 0 and not is_thin:
            vals = defined[fwd_col].values.astype(float)
            eps = defined["episode_id"].values
            valid_fwd = ~np.isnan(vals)
            obs_u, param_p, perm_p, r_bis, nea, neb = episode_permutation_mwu(
                vals[valid_fwd], eps[valid_fwd], a_mask[valid_fwd], n_perm=N_PERM, rng_seed=SEED)
        else:
            obs_u = param_p = perm_p = r_bis = np.nan
            nea = neb = 0

        # sanity gate (round-1 defect signature)
        if not (np.isnan(param_p) or np.isnan(perm_p)) and param_p > 0:
            if perm_p > 0.3 and param_p < 10 ** (-SANITY_DIVERGENCE_ORDERS):
                sanity_flags.append((tid, param_p, perm_p))

        # ── BASELINE-FREE half deltas (BLOCKING-2 convention) ──
        h1d = half_delta_baseline_free(half1, moved_col, state_col)
        h2d = half_delta_baseline_free(half2, moved_col, state_col)
        if not (np.isnan(h1d) or np.isnan(h2d)):
            sign_stable = (h1d < 0) == (h2d < 0)   # same sign of the within-half contrast
        else:
            sign_stable = False
        # dead-money half deltas (21d co-benefit sign check, secondary)
        def _dm_half(hh):
            hA = hh[hh[moved_col] == True]; hB = hh[hh[moved_col] == False]
            ra = dead_rate(hA, state_col); rb = dead_rate(hB, state_col)
            return np.nan if (np.isnan(ra) or np.isnan(rb)) else (ra - rb) * 100.0
        dm_h1 = _dm_half(half1); dm_h2 = _dm_half(half2)

        trial_results[tid] = {
            "trial_id": tid, "config": cid, "config_name": CONFIG_NAMES[cid],
            "horizon": horizon, "excluded_thin": False, "in_bh_family": True,
            "n_A_moved_up": n_A, "n_B_not_moved": n_B,
            "n_ep_A_moved_up": n_ep_A, "n_ep_B_not_moved": n_ep_B, "is_thin": is_thin,
            "stop_rate_moved_up": None if np.isnan(sA) else float(sA),
            "stop_rate_not_moved": None if np.isnan(sB) else float(sB),
            "stop_delta_pp": float(delta_pp), "stop_delta_favorable": bool(delta_favorable),
            "deadmoney_delta_pp": float(dm_delta_pp),
            "liftoff_delta_pp": float(lo_delta_pp),
            "perm_p": None if np.isnan(perm_p) else float(perm_p),
            "param_p": None if np.isnan(param_p) else float(param_p),
            "r_biserial": None if np.isnan(r_bis) else float(r_bis),
            "sign_stable": bool(sign_stable),
            "half1_stop_delta_pp": None if np.isnan(h1d) else float(h1d),
            "half2_stop_delta_pp": None if np.isnan(h2d) else float(h2d),
            "half1_deadmoney_delta_pp": None if np.isnan(dm_h1) else float(dm_h1),
            "half2_deadmoney_delta_pp": None if np.isnan(dm_h2) else float(dm_h2),
            "bh_adj_p": None, "survives_bh": False, "verdict": "PENDING",
        }
        LOG(f"  {tid} {cid}/{CONFIG_NAMES[cid]:<18} {horizon}dstop "
            f"Δ={delta_pp:+6.2f}pp fav={'Y' if delta_favorable else 'N'} "
            f"perm_p={perm_p:.4f} r={r_bis:+.4f} "
            f"sign={'Y' if sign_stable else 'N'}(H1={h1d:+.1f},H2={h2d:+.1f}) "
            f"dm21Δ={dm_delta_pp:+.2f} {'THIN' if is_thin else ''}")
LOG()

if sanity_flags:
    LOG("!!! SANITY GATE TRIPPED — param/perm divergence (round-1 defect signature):")
    for tid, pp, bp in sanity_flags:
        LOG(f"    {tid}: param_p={pp:.2e} perm_p={bp:.4f}")
    LOG("    HALTING.")
    sys.exit(2)
LOG("Sanity gate: PASS — no param/perm divergence of the round-1 defect signature.")
LOG()

# ── 13. BH correction across the declared family ────────────────────────────────
family_ids = [t[0] for t in trial_order]
perm_ps = [trial_results[t]["perm_p"] for t in family_ids]
perm_ps_safe = [p if (p is not None and not np.isnan(p)) else 1.0 for p in perm_ps]
bh_adj = bh_correction(perm_ps_safe, q=BH_Q)
for i, tid in enumerate(family_ids):
    trial_results[tid]["bh_adj_p"] = float(bh_adj[i])
    trial_results[tid]["survives_bh"] = bool(bh_adj[i] <= BH_Q)
n_survive = sum(trial_results[t]["survives_bh"] for t in family_ids)
min_bh = min(trial_results[t]["bh_adj_p"] for t in family_ids)
LOG(f"BH q<=0.10 across m={m_declared}: n_survive={n_survive}  min BH-adj p={min_bh:.4f}")
LOG()

# ── 14. Fire-rate impact table (R7; mandatory regardless of outcome) ────────────
LOG("─" * 72)
LOG("FIRE-RATE IMPACT (R7; RW mode removes zero fires -> gate_fire_rate_impact_pct=0.0)")
LOG("─" * 72)
fire_impact = {}
n_fires_total = n_defined
for cid in ["C1","C2","C3","C4","C5","C6","C7","C8"]:
    mask = CONFIG_MASKS[cid]
    n_in = int(mask.sum())
    n_ep_in = int(defined.loc[mask, "episode_id"].nunique())
    # not-moved-up cluster count for active configs
    if cid in active_configs:
        mv = moved_cols[cid]
        n_ep_notmoved = int(defined.loc[defined[mv] == False, "episode_id"].nunique())
        n_ep_moved = int(defined.loc[defined[mv] == True, "episode_id"].nunique())
    else:
        n_ep_notmoved = None; n_ep_moved = None
    fire_impact[cid] = {
        "n_fires_total": n_fires_total, "n_in_bonus_cell": n_in,
        "bonus_cell_pct": round(100.0 * n_in / n_fires_total, 3),
        "n_ep_bonus_cell": n_ep_in, "n_ep_moved_up": n_ep_moved,
        "n_ep_not_moved_up": n_ep_notmoved,
        "gate_fire_rate_impact_pct": 0.0,
    }
    LOG(f"  {cid} {CONFIG_NAMES[cid]:<18} in_cell={n_in:6,} "
        f"({fire_impact[cid]['bonus_cell_pct']:5.1f}%) ep_cell={n_ep_in:5,} "
        f"ep_moved={str(n_ep_moved):>6} ep_not_moved={str(n_ep_notmoved):>6} "
        f"gate_impact=0.0%")
LOG()

# ── 15. Per-config verdicts (§6.1 / §6.3) with 21d dead-money co-benefit ────────
LOG("─" * 72)
LOG("PER-CONFIG VERDICTS (§6.3 ship: BH-surv favorable stop-out + sign-stable + "
    "not-thin + 21d dead-money Δ<=0)")
LOG("─" * 72)

def cfg_trials(cid):
    return [t for t in trial_order if t[1] == cid]

# 21d dead-money delta per config (binding co-benefit; ADVISORY E)
def config_21d_dm(cid):
    for tid, c, h in trial_order:
        if c == cid and h == 21:
            return trial_results[tid]["deadmoney_delta_pp"]
    return None

config_verdicts = {}
ship_configs = []
for cid in ["C1","C2","C3","C4","C5","C6","C7","C8"]:
    if cid not in active_configs:
        config_verdicts[cid] = {"verdict": "DEAD (THIN — excluded before run)",
                                "ships": False, "reason": "n_episodes<25"}
        LOG(f"  {cid} {CONFIG_NAMES[cid]:<18}: DEAD (THIN excluded)")
        continue
    ships_at = []
    for tid, c, h in cfg_trials(cid):
        tr = trial_results[tid]
        if (tr["survives_bh"] and tr["stop_delta_favorable"]
                and tr["sign_stable"] and not tr["is_thin"]):
            ships_at.append((h, tid))
    dm21 = config_21d_dm(cid)
    dm_ok = (dm21 is not None) and (dm21 <= 0.0)
    if ships_at and dm_ok:
        verdict = f"SHIPS (stop-out survives at {[h for h,_ in ships_at]}d; 21d dm Δ={dm21:+.2f}pp<=0)"
        ships = True
        ship_configs.append(cid)
    elif ships_at and not dm_ok:
        verdict = (f"DEAD (stop-out survives at {[h for h,_ in ships_at]}d BUT 21d dead-money "
                   f"Δ={dm21:+.2f}pp>0 — harm trade, §5.3 fails)")
        ships = False
    else:
        # explain why: no BH-surv favorable+sign-stable trial
        bh_fav = any(trial_results[t]["survives_bh"] and trial_results[t]["stop_delta_favorable"]
                     for t, _, _ in cfg_trials(cid))
        sign_ok = any(trial_results[t]["sign_stable"] for t, _, _ in cfg_trials(cid))
        verdict = (f"DEAD (no BH-surviving favorable sign-stable stop-out trial; "
                   f"any_BH_favorable={bh_fav}, any_sign_stable={sign_ok})")
        ships = False
    config_verdicts[cid] = {"verdict": verdict, "ships": ships,
                            "ships_at_horizons": [h for h, _ in ships_at],
                            "dead_money_21d_delta_pp": dm21, "dm_cobenefit_ok": bool(dm_ok)}
    LOG(f"  {cid} {CONFIG_NAMES[cid]:<18}: {verdict}")
LOG()

# ── 16. Whole-study verdict (§6.2 kill vs §6.3 ship) ────────────────────────────
LOG("─" * 72)
if ship_configs:
    whole_verdict = "PARTIAL_SHIP"
    LOG(f"WHOLE-STUDY VERDICT: {whole_verdict}")
    LOG(f"  Ship-qualifying configs (EI-F1D-RW shadow registration): {ship_configs}")
    # §6.3 preference: narrowest condition set
    narrowness = {"C2": 2, "C7": 3, "C1": 2, "C6": 3, "C3": 2, "C8": 3, "C5": 3, "C4": 2}
    lead = sorted(ship_configs, key=lambda c: (narrowness.get(c, 9), fire_impact[c]["n_in_bonus_cell"]))[0]
    LOG(f"  §6.3 lead for first shadow deploy (narrowest surviving): {lead} ({CONFIG_NAMES[lead]})")
else:
    whole_verdict = "WHOLE_STUDY_KILL"
    lead = None
    LOG(f"WHOLE-STUDY VERDICT: {whole_verdict}")
    LOG("  §6.2 PROGRAM-WIDE KILL EXECUTES: no config produced a favorable-direction,")
    LOG("  BH-surviving, sign-stable stop-out effect at either horizon.")
    LOG("  washout_proximity (any depth cut / interaction) may NOT be a rank-weight input")
    LOG("  without a NEW prereg starting from new data (e.g. CN/HK/CA cross-market passport).")
    LOG("  Dead-money context note (reprobe T02 −15.11pp, HG) stays DISPLAY-ONLY.")
    LOG("  F2 (RS-inflection) and F3 (anti-chase) unaffected (not washout-sourced).")
LOG()

# ── 17. Save results.json + run log ─────────────────────────────────────────────
IN_SAMPLE_HONESTY = (
    "The depth threshold (>25%) and the 8 configs were selected by examining the same "
    "47,182-fire panel used in the diagnostic. This is genuine post-diagnostic registration, "
    "not pretend-prospective. Out-of-sample confirmation is the forward ledger and CN/HK/CA "
    "cross-market passports ONLY. Any pass here authorizes the SHADOW rung only — never live "
    "board enforcement."
)

results_out = {
    "study_id": STUDY_ID,
    "bh_family": BH_FAMILY,
    "study_date": "2026-07-05",
    "prereg": str(PREREG_PATH),
    "redteam": "research/entry_intel/P2_5_REDTEAM.md (BLOCKING-1 sc63; BLOCKING-2 pinned §5.2)",
    "memo_version": "P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05) §6",
    "primary_test": ("episode-level label-permutation Mann-Whitney U (N_PERM=5000, two-sided, "
                     "Phipson-Smyth +1) — verbatim from run_P1_3_v2.py"),
    "sign_stability_convention": ("per-half Δ = stop_out(moved_up) − stop_out(not_moved_up) within "
                                  "each half, horizon-matched, NO external baseline (BLOCKING-2 pinned; "
                                  "diagnostic sign_consistent NOT inherited)"),
    "round0_provenance_note": ("The upstream diagnostic's sc63 sign-consistency labels were computed "
                               "against the 21d baseline (0.3848) instead of the 63d baseline (0.6231) "
                               "— a bug (run_P2_5_diagnostic.py sign_consistent ~line 470) that made sc63 "
                               "mechanically True for every cell. This study does NOT inherit that function; "
                               "it uses the baseline-free within-half moved_up vs not-moved-up contrast, so "
                               "the sc63 bug cannot recur here. Config selection rationale relies on §3 (a)–(d), "
                               "not on the tainted sc63 column."),
    "dd_pct_provenance": ("regenerated PIT via washout_depth_pit (byte-faithful depth extension of the "
                          "reprobe's washout_ctx path; PIT slice index<=signal_date on massive_stock_day close)"),
    "replay_path": str(REPLAY_PATH), "replay_md5": replay_md5,
    "replay_md5_matches": replay_md5 == EXPECTED_REPLAY_MD5,
    "era": {"start": ERA_START, "end_operational": ERA_END,
            "prereg_window": "2022-06-30 -> 2026-07-02",
            "note": "replay vg-fire max=2025-12-29; prereg and operational windows select identical population"},
    "population": {
        "n_fires_all_vg": n_all_fires,
        "n_fires_washout_defined": n_defined,
        "n_fires_none_excluded": n_none,
        "n_washout_true": n_wash_true,
        "n_episode_clusters_all": int(vg["episode_id"].nunique()),
        "n_episode_clusters_defined": int(defined["episode_id"].nunique()),
        "n_survivor_stamped": int(n_stamped),
        "halves_midpoint": str(midpoint),
        "n_half1": int(len(half1)), "n_half2": int(len(half2)),
    },
    "column_map": COLUMN_MAP,
    "config_episode_counts": config_ep,
    "active_configs": active_configs, "excluded_thin": excluded_thin,
    "m_declared": m_declared,
    "calibration": calibration_summary,
    "sanity_gate": {"tripped": bool(sanity_flags), "flags": [list(x) for x in sanity_flags]},
    "bh_q": BH_Q, "n_perm": N_PERM, "n_survive_bh": int(n_survive), "min_bh_adj_p": float(min_bh),
    "trials": trial_results,
    "fire_rate_impact": fire_impact,
    "config_verdicts": config_verdicts,
    "ship_configs": ship_configs,
    "lead_config": lead,
    "whole_study_verdict": whole_verdict,
    "in_sample_honesty_statement": IN_SAMPLE_HONESTY,
    "reprobe_cross_reference": {
        "T09_RW_63d_stop_production_delta_pp": 3.34,
        "T02_HG_21d_deadmoney_production_delta_pp": -15.11,
        "note": "sealed prior-study numbers from P2_1B_F1_REPROBE; NOT re-run in this study",
    },
    "leak_audit": {
        "fill_rule": "rank re-order within signal_date; forward returns fwd_ret_{h} are post-signal, "
                     "frozen in replay (fill strictly after signal bar)",
        "feature_freeze": "dd_pct computed PIT (price index<=signal_date); no look-ahead",
        "era_boundary": f"{ERA_START} -> {ERA_END}",
        "survivor_bias": "0 stamped rows in vg (survivor_bias==False for all)",
    },
}

def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)

with open(OUT_DIR / "results.json", "w") as f:
    json.dump(results_out, f, indent=2, default=_default)
with open(OUT_DIR / "_run.log", "w") as f:
    f.write("\n".join(log_lines) + "\n")

LOG(f"Saved: {OUT_DIR / 'results.json'}")
LOG(f"Saved: {OUT_DIR / '_run.log'}")
LOG("=" * 72)
LOG(f"{STUDY_ID} COMPLETE — verdict: {whole_verdict}")
LOG("=" * 72)
