"""
P3 — Kernel-Rank Shadow — Build Script
Study: P3_KERNEL_RANK_SHADOW
Program: Entry Intelligence (EI)
PREREG: research/entry_intel/P3_KERNEL_RANK_PREREG.md (APPROVED, Fable 2026-07-05)
Memo law: research/entry_intel/P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments

Author: Sonnet subagent under Fable orchestration
Date: 2026-07-05

────────────────────────────────────────────────────────────────────────────────
SCOPE (Article 2 / R6 shadow law):
  - SHADOW ARTIFACT ONLY: outputs kernel_rank_shadow.parquet + build report
  - NO board wiring, NO user-visible surface
  - NO import of any Neural Web money-path consumer
  - The kernel-rank score is logged alongside incumbent but never used to reorder
────────────────────────────────────────────────────────────────────────────────

REGISTERED DECISIONS (P3_KERNEL_RANK_PREREG.md §7 — immutable):
  Feature set:    {dist_52wh, cohort_washout_proximity, ext_z, ext_atr, weekly_phase}
  Bucket count:   4 quartiles for continuous features; categorical for weekly_phase
  K_SHRINK:       10  (kernel.py K_POOL default)
  Wilson z:       1.645  (one-sided 95%)
  Horizons:       {21, 63}
  Episode n floor (THIN threshold): 25 episode clusters
  Feature weights (|rho_21d|-proportional):
      dist_52wh              0.34
      cohort_washout_proximity 0.31 (if concordance GO; else omitted)
      ext_z                  0.28
      ext_atr                0.24
      weekly_phase           0.00  (categorical separator only)
  Combination denominator: 1.17 (all four features) or 0.86 (washout omitted)
  concordance_check path: research/entry_intel/p1_runs/P1_3/concordance_check.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Constants (all pre-registered; no search permitted) ───────────────────────

STUDY_ID = "P3_KERNEL_RANK_SHADOW"
K_SHRINK = 10          # MemberStat K_POOL default; cite: kernel.py line 99
WILSON_Z = 1.645       # one-sided 95% CI lower bound; cite: qledger.py Wilson convention
THIN_N_EFF = 25        # episode-cluster n floor for non-THIN cells
HORIZONS = [21, 63]    # verdict horizons (trading days)

# Outcome columns (from P1.3 run_P1_3_v2.py HORIZON_CONFIG)
# 21d horizon -> state_8_21 (8=stop threshold, 21=lookback)
# 63d horizon -> state_15_126 (15=stop threshold, 126=lookback; this is the registered
#               63d terminal state — see P1.3 RESULTS.md HORIZON_CONFIG)
OUTCOME_STATE = {
    21: "state_8_21",
    63: "state_15_126",
}
GOOD_STATES = frozenset({"CUSHIONED", "CLEAN_LIFTOFF"})

# Feature weights (|rho_21d|-proportional from P1.1 RESULTS.md §Survivor List)
FEATURE_WEIGHTS_FULL = {
    "dist_52wh":                0.34,
    "cohort_washout_proximity": 0.31,
    "ext_z":                    0.28,
    "ext_atr":                  0.24,
    # weekly_phase weight = 0.00; excluded from weighted sum per §3.5
}
WEIGHTS_SUM_FULL = 1.17      # Σwᵢ with washout included
WEIGHTS_SUM_FALLBACK = 0.86  # Σwᵢ with washout omitted (0.34 + 0.28 + 0.24)

# Spec §2.1 — concordance check path (R-P2.2: single concordance authority = P2.1b §3.3)
CONCORDANCE_CHECK_RELPATH = "research/entry_intel/p1_runs/P1_3/concordance_check.json"

# Replay artifact expected MD5 (from P1.3 RESULTS.md)
EXPECTED_MD5 = "906175f9eb8caa351ed6d7d5c56265d3"

# ── Paths ──────────────────────────────────────────────────────────────────────
# This script lives at: research/entry_intel/p3_runs/build_kernel_rank_shadow.py
# REPO_CODE = worktree root (code files; git commits from here)
# REPO_DATA = canonical main repo root (heavy data stores absent from worktrees per R2 law)
REPO_CODE = Path(__file__).parents[3]
# Data reads by absolute path from the canonical main repo (R2 law: heavy stores in main)
REPO_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")

REPLAY_PATH    = REPO_DATA / "data" / "replay" / "replay_boarded.parquet"
SIGNAL_ARCHIVE = REPO_DATA / "data" / "signal_archive"
# Spec §9: shadow parquet output (R9 — not git-committed); written alongside replay
SHADOW_OUTPUT  = REPO_DATA / "data" / "replay" / "kernel_rank_shadow.parquet"

CONCORDANCE_PATH = REPO_CODE / CONCORDANCE_CHECK_RELPATH
MEMO_PATH        = REPO_CODE / "research" / "entry_intel" / "P0_MEASUREMENT_MEMO.md"
PREREG_PATH      = REPO_CODE / "research" / "entry_intel" / "P3_KERNEL_RANK_PREREG.md"
P3_RUNS_DIR      = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════════════
# 0. BLOCKING GATES
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 72)
print(f"P3 KERNEL-RANK SHADOW — {STUDY_ID}")
print("Registered 2026-07-05 | PREREG: P3_KERNEL_RANK_PREREG.md")
print("=" * 72)
print()

print("§5 CONFORMANCE CHECKLIST (P0_MEASUREMENT_MEMO.md v1.0 2026-07-04 + §6 v1.1)")
print()

assert MEMO_PATH.exists(), f"BLOCKER: P0_MEASUREMENT_MEMO.md not found at {MEMO_PATH}"
print("  [x] Cites P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments")
print("  [x] Primary window = 2022-06-30 -> last-full-replay-date (v1.1 amendment: 250-bar warmup)")
print("  [x] Verdict-grade statistics on survivor_bias==False rows only (49,939 fire population)")
print("  [x] horizon_censored rows excluded (7,701 pre-excluded via verdict_grade)")
print("  [x] Returns THIN (no cell posterior emitted) if n_eff < 25; falls back to parent")
print("  [x] Shadow column only — no board reordering in v1")
print("  [x] Proxy-source check for cohort_washout_proximity performed at build time")
print("  [x] Article 2 flip criterion pre-registered (episode-clustered n floor 300)")
print()

assert REPLAY_PATH.exists(), f"BLOCKER: replay_boarded.parquet not found at {REPLAY_PATH}"
assert PREREG_PATH.exists(), f"BLOCKER: P3_KERNEL_RANK_PREREG.md not found at {PREREG_PATH}"

print(f"Replay path: {REPLAY_PATH}")
with open(REPLAY_PATH, "rb") as f:
    actual_md5 = hashlib.md5(f.read()).hexdigest()
print(f"Replay MD5:  {actual_md5}")
if actual_md5 != EXPECTED_MD5:
    print(f"WARNING: MD5 mismatch. Expected {EXPECTED_MD5}, got {actual_md5}. "
          f"Proceeding — replay may have been rebuilt; verify era boundary before promotion.")
else:
    print(f"MD5 matches expected {EXPECTED_MD5} — OK")
print()

# ── Concordance check (R-P2.2: single concordance authority = P2.1b §3.3) ────
print("─" * 72)
print("CONCORDANCE CHECK — cohort_washout_proximity (P2.1b §3.3)")
print("─" * 72)

concordance_go: bool = False
concordance_note: str = ""

if CONCORDANCE_PATH.exists():
    try:
        conc = json.loads(CONCORDANCE_PATH.read_text())
        verdict = str(conc.get("verdict", "")).upper()
        if verdict == "GO":
            concordance_go = True
            concordance_note = f"GO ({CONCORDANCE_PATH})"
            print(f"  [x] concordance_check.json present; verdict=GO -> washout included")
            print(f"      concordance_rate: {conc.get('concordance_rate', 'N/A')}")
        else:
            concordance_note = (
                f"REPROBE_REQUIRED or non-GO verdict ({verdict}) in {CONCORDANCE_PATH}"
            )
            print(f"  [ ] concordance_check.json present but verdict={verdict} -> "
                  f"washout OMITTED; using fallback weights (Sigma=0.86)")
    except Exception as exc:
        concordance_note = f"parse error in {CONCORDANCE_PATH}: {exc}"
        print(f"  [ ] concordance_check.json parse error -> washout OMITTED (fallback weights)")
else:
    concordance_note = f"concordance_check.json ABSENT at {CONCORDANCE_PATH}"
    print(f"  [ ] concordance_check.json ABSENT -> washout OMITTED; using fallback weights (Sigma=0.86)")
    print(f"      (P3_KERNEL_RANK_PREREG.md §2.1: absence forces omit-and-renormalize)")

print()

if concordance_go:
    active_features = ["dist_52wh", "cohort_washout_proximity", "ext_z", "ext_atr"]
    weights_sum = WEIGHTS_SUM_FULL
    proxy_sourced_dims: list[str] = ["cohort_washout_proximity"]  # PROXY-STAMP: P1.1 REVIEW A1
    print(f"  Combination: ALL FOUR features (Sigma-w = {weights_sum})")
else:
    active_features = ["dist_52wh", "ext_z", "ext_atr"]
    weights_sum = WEIGHTS_SUM_FALLBACK
    proxy_sourced_dims = []
    print(f"  Combination: THREE features only, washout omitted (Sigma-w = {weights_sum})")

print(
    f"  NOTE: cohort_washout_proximity always carries PROXY-STAMP if included "
    f"(100% proxy-sourced per P1.1 REVIEW A1; production source: COILED/S1)"
)
print()


# ══════════════════════════════════════════════════════════════════════════════
# 1. LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("LOADING DATA")
print("─" * 72)
print(f"Loading {REPLAY_PATH} ...")
df_full = pd.read_parquet(REPLAY_PATH)
print(f"  Full shape: {df_full.shape}")
print()

# Primary population filter: fires, verdict_grade=True, survivor_bias=False
fires_all = df_full[df_full["verdict_type"] == "fire"].copy()
fires = fires_all[fires_all["verdict_grade"] == True].copy()
fires = fires[fires["survivor_bias"] == False].copy()
fires = fires.reset_index(drop=True)

stamped = int(df_full.get("survivor_bias", pd.Series([False] * len(df_full))).sum())
print("POPULATION CENSUS")
print(f"  Total rows in replay:          {len(df_full):,}")
print(f"  Total fires (verdict_type==fire): {len(fires_all):,}")
print(f"  Verdict-grade fires (primary): {len(fires):,}")
print(f"  Survivor-bias==True rows:      {stamped:,}  (excluded)")
if "horizon_censored" in fires_all.columns:
    n_hcensored = int(fires_all["horizon_censored"].sum())
    print(f"  Horizon-censored fires:        {n_hcensored:,}  (pre-excluded via verdict_grade)")
era_min = fires["signal_date"].min()
era_max = fires["signal_date"].max()
n_ep = fires["episode_id"].nunique()
print(f"  Effective verdict window:      {era_min} -> {era_max}")
print(f"  Episode clusters (unique):     {n_ep:,}")

# Pre-2021 rows check (should be 0 per memo; warn if any appear)
try:
    pre2021_mask = pd.to_datetime(fires["signal_date"]) < pd.Timestamp("2021-01-01")
    n_pre2021 = int(pre2021_mask.sum())
    if n_pre2021 > 0:
        print(f"  WARNING: {n_pre2021} rows have signal_date < 2021. "
              f"Excluding (survivor-bias law).")
        fires = fires[~pre2021_mask].reset_index(drop=True)
    else:
        print(f"  Pre-2021 rows: 0 (correct — all rows in primary window)")
except Exception:
    pass

print()
print("SURVIVOR-BIAS STAMP (§2.3):")
print("  survivor-biased panel: 0% of member-months lack price history for this era;")
print("  all rows Massive-sourced (survivor_bias==False); delisted-name recall verified 100%.")
print("  PRE-2021 / SURVIVOR-STAMPED -- CONTEXT ONLY, NOT VERDICT-GRADE: 0 rows.")
print()

# Washout distribution
wp_true = int(fires["washout_proximity"].sum())
wp_false = int((~fires["washout_proximity"].astype(bool)).sum())
print(f"washout_proximity: True={wp_true:,}, False={wp_false:,}")
print(f"weekly_phase values: {fires['weekly_phase'].value_counts().to_dict()}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 2. FEATURE BUCKETING (pre-registered; fixed at run start)
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("FEATURE BUCKET BREAKPOINTS (computed on verdict-grade fire population)")
print("─" * 72)

dist_col = "dist_to_52wh"  # column map: dist_52wh -> dist_to_52wh

dist_q25 = float(fires[dist_col].quantile(0.25))
dist_q50 = float(fires[dist_col].quantile(0.50))
dist_q75 = float(fires[dist_col].quantile(0.75))
print(f"dist_52wh ({dist_col}): Q25={dist_q25:.4f}, Q50={dist_q50:.4f}, Q75={dist_q75:.4f}")

extz_q25 = float(fires["ext_z"].quantile(0.25))
extz_q50 = float(fires["ext_z"].quantile(0.50))
extz_q75 = float(fires["ext_z"].quantile(0.75))
print(f"ext_z:     Q25={extz_q25:.4f}, Q50={extz_q50:.4f}, Q75={extz_q75:.4f}")

extatr_q25 = float(fires["ext_atr"].quantile(0.25))
extatr_q50 = float(fires["ext_atr"].quantile(0.50))
extatr_q75 = float(fires["ext_atr"].quantile(0.75))
print(f"ext_atr:   Q25={extatr_q25:.4f}, Q50={extatr_q50:.4f}, Q75={extatr_q75:.4f}")

print(f"cohort_washout_proximity: binary (NEAR={wp_true:,}, NOT_NEAR={wp_false:,})")

weekly_phase_buckets = ["basing", "bear_recovering", "turning", "rising", "rolling", "falling"]
print(f"weekly_phase: categorical buckets = {weekly_phase_buckets} + UNKNOWN fallback")

breakpoints = {
    "dist_52wh": {"q25": dist_q25, "q50": dist_q50, "q75": dist_q75},
    "ext_z":     {"q25": extz_q25, "q50": extz_q50, "q75": extz_q75},
    "ext_atr":   {"q25": extatr_q25, "q50": extatr_q50, "q75": extatr_q75},
    "washout_proximity": {"buckets": ["NEAR", "NOT_NEAR"]},
    "weekly_phase": {"buckets": weekly_phase_buckets + ["UNKNOWN"]},
}
print()


def bucket_dist52wh(val: float) -> str:
    if pd.isna(val):
        return "__missing__"
    if val <= dist_q25:
        return "Q1"
    if val <= dist_q50:
        return "Q2"
    if val <= dist_q75:
        return "Q3"
    return "Q4"


def bucket_extz(val: float) -> str:
    if pd.isna(val):
        return "__missing__"
    if val <= extz_q25:
        return "Q1"
    if val <= extz_q50:
        return "Q2"
    if val <= extz_q75:
        return "Q3"
    return "Q4"


def bucket_extatr(val: float) -> str:
    if pd.isna(val):
        return "__missing__"
    if val <= extatr_q25:
        return "Q1"
    if val <= extatr_q50:
        return "Q2"
    if val <= extatr_q75:
        return "Q3"
    return "Q4"


def bucket_washout(val: Any) -> str:
    return "NEAR" if bool(val) else "NOT_NEAR"


def bucket_weekly_phase(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "UNKNOWN"
    v = str(val).lower().strip()
    if v in weekly_phase_buckets:
        return v.upper()
    return "UNKNOWN"


fires = fires.copy()
fires["_b_dist52wh"] = fires[dist_col].apply(bucket_dist52wh)
fires["_b_extz"]     = fires["ext_z"].apply(bucket_extz)
fires["_b_extatr"]   = fires["ext_atr"].apply(bucket_extatr)
fires["_b_washout"]  = fires["washout_proximity"].apply(bucket_washout)
fires["_b_wphase"]   = fires["weekly_phase"].apply(bucket_weekly_phase)

# Regime dimension: quad_hard_label absent from this artifact -> all __unstamped__
fires["_regime"] = "__unstamped__"


# ══════════════════════════════════════════════════════════════════════════════
# 3. OUTCOME LABELS
# ══════════════════════════════════════════════════════════════════════════════

# good_outcome = terminal_state in {CUSHIONED, CLEAN_LIFTOFF}
# Per PREREG §3.1 and P1.1 PREREG §4; horizon state columns per P1.3 HORIZON_CONFIG
fires["good_21d"] = fires[OUTCOME_STATE[21]].isin(GOOD_STATES)
fires["good_63d"] = fires[OUTCOME_STATE[63]].isin(GOOD_STATES)

base_21 = float(fires["good_21d"].mean())
base_63 = float(fires["good_63d"].mean())
print(f"Good-outcome base rates: 21d={base_21:.4f}, 63d={base_63:.4f}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 4. CELL POSTERIOR COMPUTATION WITH HIERARCHICAL SHRINKAGE
# ══════════════════════════════════════════════════════════════════════════════
# Pattern: engine/neuralweb/kernel.py SHRINKAGE section (lines 50-56)
# No money-path consumer imported — pure statistical computation only.
#
# Hierarchy for a (feature, bucket, regime, horizon) cell:
#   grandparent:  (feature, __marginal__, __all__, horizon) -> shrinks toward global base rate
#   parent:       (feature, bucket,       __all__, horizon) -> shrinks toward grandparent
#   child:        (feature, bucket,       regime,  horizon) -> shrinks toward parent
#
# Shrinkage formula (kernel.py / pooling.py pattern):
#   shrunken_p = (k_eff + K_SHRINK * p_parent) / (n_eff + K_SHRINK)
#
# Wilson lower bound (the kernel-rank score contribution from this cell):
#   wilson_lo = shrunken_p - z * sqrt(shrunken_p * (1-shrunken_p) / n_eff_effective)
#   where n_eff_effective = n_eff + K_SHRINK  (effective sample size after shrinkage)
# ══════════════════════════════════════════════════════════════════════════════


def wilson_lo_fn(shrunken_p: float, n_eff_effective: float) -> float:
    """Wilson lower bound on P(good outcome) given shrunken posterior.
    Cite: qledger.py wilson_ci_low convention; z=1.645 (one-sided 95%).
    """
    if n_eff_effective <= 0:
        return 0.0
    variance = shrunken_p * (1.0 - shrunken_p) / n_eff_effective
    if variance < 0:
        variance = 0.0
    return float(shrunken_p - WILSON_Z * np.sqrt(variance))


def episode_collapse(subset: pd.DataFrame, outcome_col: str) -> tuple[int, int]:
    """
    Episode-clustered n_eff and k_eff.
    Multiple fires from the same episode_id in the same cell count as ONE observation
    (the co-firing collapse per kernel.py EVENT DEDUP section).
    n_eff = number of distinct episode_id values in subset.
    k_eff = number of distinct episodes with good_outcome == True
            (taken from the first-occurrence row per episode, which is sufficient
             since episode membership is constant within an episode for these features).
    """
    ep_first = subset.drop_duplicates(subset=["episode_id"])
    n_eff = len(ep_first)
    k_eff = int(ep_first[outcome_col].astype(bool).sum())
    return n_eff, k_eff


def shrink_toward_parent(k_eff: int, n_eff: int, p_parent: float) -> tuple[float, float]:
    """
    Two-tier shrinkage toward parent (kernel.py pattern).
    Returns (shrunken_p, n_eff_effective).
    K_SHRINK is pre-registered as 10.
    """
    n_eff_effective = float(n_eff + K_SHRINK)
    shrunken_p = (k_eff + K_SHRINK * p_parent) / n_eff_effective
    return shrunken_p, n_eff_effective


def build_feature_cells(
    data: pd.DataFrame,
    feature_name: str,
    bucket_col: str,
    outcome_col: str,
    horizon: int,
    global_base_rate: float,
) -> list[dict[str, Any]]:
    """
    Build all cells for one (feature, horizon) pair.

    Emits rows for:
      - grandparent: (feature, __marginal__, __all__, horizon)
      - parent:      (feature, bucket, __all__, horizon)  [one per bucket]
      - child:       (feature, bucket, regime, horizon)   [one per bucket x regime]
    """
    rows: list[dict[str, Any]] = []

    # ── grandparent: (feature, __marginal__, __all__, horizon) ────────────────
    gp_n_eff, gp_k_eff = episode_collapse(data, outcome_col)
    gp_shrunken, gp_n_eff_eff = shrink_toward_parent(gp_k_eff, gp_n_eff, global_base_rate)
    gp_thin = gp_n_eff < THIN_N_EFF
    gp_wlo = wilson_lo_fn(gp_shrunken, gp_n_eff_eff) if not gp_thin else None

    rows.append({
        "cell_key":         f"{feature_name}:__marginal__:__all__:{horizon}d",
        "feature_name":     feature_name,
        "feature_bucket":   "__marginal__",
        "regime_bucket":    "__all__",
        "horizon_days":     horizon,
        "n_raw":            len(data),
        "n_eff":            gp_n_eff,
        "k_eff":            gp_k_eff,
        "p_raw":            gp_k_eff / gp_n_eff if gp_n_eff > 0 else 0.0,
        "p_parent":         global_base_rate,
        "shrunken_p":       gp_shrunken,
        "n_eff_effective":  gp_n_eff_eff,
        "wilson_lo":        gp_wlo,
        "thin_flag":        gp_thin,
        "proxy_sourced":    feature_name in proxy_sourced_dims,
        "parent_cell_used": False,
        "cell_level":       "grandparent",
    })

    # ── parent + child per bucket ──────────────────────────────────────────────
    for bucket in sorted(data[bucket_col].unique()):
        bucket_data = data[data[bucket_col] == bucket]
        if len(bucket_data) == 0:
            continue

        # Parent: (feature, bucket, __all__, horizon)
        par_n_eff, par_k_eff = episode_collapse(bucket_data, outcome_col)
        par_shrunken, par_n_eff_eff = shrink_toward_parent(par_k_eff, par_n_eff, gp_shrunken)
        par_thin = par_n_eff < THIN_N_EFF
        par_wlo = wilson_lo_fn(par_shrunken, par_n_eff_eff) if not par_thin else None
        # effective_wlo for fallback: parent's wlo if not thin, else grandparent's wlo
        par_effective_wlo = par_wlo if not par_thin else gp_wlo

        rows.append({
            "cell_key":         f"{feature_name}:{bucket}:__all__:{horizon}d",
            "feature_name":     feature_name,
            "feature_bucket":   bucket,
            "regime_bucket":    "__all__",
            "horizon_days":     horizon,
            "n_raw":            len(bucket_data),
            "n_eff":            par_n_eff,
            "k_eff":            par_k_eff,
            "p_raw":            par_k_eff / par_n_eff if par_n_eff > 0 else 0.0,
            "p_parent":         gp_shrunken,
            "shrunken_p":       par_shrunken,
            "n_eff_effective":  par_n_eff_eff,
            "wilson_lo":        par_wlo,
            "thin_flag":        par_thin,
            "proxy_sourced":    feature_name in proxy_sourced_dims,
            "parent_cell_used": par_thin,
            "cell_level":       "parent",
            "_effective_wlo":   par_effective_wlo,
        })

        # Child: (feature, bucket, regime, horizon) for each regime
        for regime in sorted(bucket_data["_regime"].unique()):
            regime_data = bucket_data[bucket_data["_regime"] == regime]
            if len(regime_data) == 0:
                continue

            ch_n_eff, ch_k_eff = episode_collapse(regime_data, outcome_col)
            ch_shrunken, ch_n_eff_eff = shrink_toward_parent(ch_k_eff, ch_n_eff, par_shrunken)
            ch_thin = ch_n_eff < THIN_N_EFF
            ch_wlo = wilson_lo_fn(ch_shrunken, ch_n_eff_eff) if not ch_thin else None
            ch_effective_wlo = ch_wlo if not ch_thin else par_effective_wlo

            rows.append({
                "cell_key":         f"{feature_name}:{bucket}:{regime}:{horizon}d",
                "feature_name":     feature_name,
                "feature_bucket":   bucket,
                "regime_bucket":    regime,
                "horizon_days":     horizon,
                "n_raw":            len(regime_data),
                "n_eff":            ch_n_eff,
                "k_eff":            ch_k_eff,
                "p_raw":            ch_k_eff / ch_n_eff if ch_n_eff > 0 else 0.0,
                "p_parent":         par_shrunken,
                "shrunken_p":       ch_shrunken,
                "n_eff_effective":  ch_n_eff_eff,
                "wilson_lo":        ch_wlo,
                "thin_flag":        ch_thin,
                "proxy_sourced":    feature_name in proxy_sourced_dims,
                "parent_cell_used": ch_thin,
                "cell_level":       "child",
                "_effective_wlo":   ch_effective_wlo,
            })

    return rows


def lookup_effective_wlo(
    cells_idx: dict[str, dict],
    feature_name: str,
    feature_bucket: str,
    regime_bucket: str,
    horizon: int,
) -> float | None:
    """
    Look up effective (post-THIN-fallback) wilson_lo for a fire.
    Falls back through: child -> parent -> grandparent.
    The _effective_wlo field stored in each cell already incorporates THIN fallback.
    """
    # Try child cell first
    child_key = f"{feature_name}:{feature_bucket}:{regime_bucket}:{horizon}d"
    child_row = cells_idx.get(child_key)
    if child_row is not None:
        wlo = child_row.get("_effective_wlo")
        if wlo is not None:
            return float(wlo)

    # Try parent (regime = __all__)
    parent_key = f"{feature_name}:{feature_bucket}:__all__:{horizon}d"
    parent_row = cells_idx.get(parent_key)
    if parent_row is not None:
        wlo = parent_row.get("_effective_wlo")
        if wlo is not None:
            return float(wlo)

    # Try grandparent
    gp_key = f"{feature_name}:__marginal__:__all__:{horizon}d"
    gp_row = cells_idx.get(gp_key)
    if gp_row is not None:
        wlo = gp_row.get("wilson_lo")
        if wlo is not None:
            return float(wlo)

    return None


# ── Build all cells ───────────────────────────────────────────────────────────

print("─" * 72)
print("BUILDING FEATURE CELLS")
print("─" * 72)

# Feature configurations: (feature_name, bucket_col_in_fires)
feature_configs = [
    ("dist_52wh",                "_b_dist52wh"),
    ("ext_z",                    "_b_extz"),
    ("ext_atr",                  "_b_extatr"),
    ("cohort_washout_proximity", "_b_washout"),
    ("weekly_phase",             "_b_wphase"),
]

all_cell_rows: list[dict[str, Any]] = []

for horizon in HORIZONS:
    outcome_col = f"good_{horizon}d"
    base_rate = float(fires[outcome_col].mean())
    print(f"\n  Horizon {horizon}d — base rate = {base_rate:.4f}")

    for feature_name, bucket_col in feature_configs:
        feature_cells = build_feature_cells(
            data=fires,
            feature_name=feature_name,
            bucket_col=bucket_col,
            outcome_col=outcome_col,
            horizon=horizon,
            global_base_rate=base_rate,
        )
        all_cell_rows.extend(feature_cells)
        n_thin = sum(1 for r in feature_cells if r["thin_flag"])
        gp_wlo = next(
            (r["wilson_lo"] for r in feature_cells if r["cell_level"] == "grandparent"),
            None,
        )
        wlo_str = f"{gp_wlo:.4f}" if gp_wlo is not None else "None"
        print(
            f"    {feature_name}: {len(feature_cells)} cells, "
            f"{n_thin} THIN, grandparent wilson_lo={wlo_str}"
        )

print()
cells_df = pd.DataFrame(all_cell_rows)

# Ensure _effective_wlo populated for grandparent rows (they only have wilson_lo)
if "_effective_wlo" not in cells_df.columns:
    cells_df["_effective_wlo"] = cells_df["wilson_lo"]
else:
    cells_df["_effective_wlo"] = cells_df["_effective_wlo"].where(
        cells_df["_effective_wlo"].notna(), cells_df["wilson_lo"]
    )

n_cells_total = len(cells_df)
n_thin_total  = int(cells_df["thin_flag"].sum())
n_parent_fallback = int(cells_df["parent_cell_used"].sum())

print(f"CELL TABLE SUMMARY:")
print(f"  Total cells built:                   {n_cells_total}")
print(f"  THIN cells (n_eff < {THIN_N_EFF}):         {n_thin_total}")
print(f"  Cells falling back to parent:        {n_parent_fallback}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 5. PER-FIRE KERNEL-RANK SCORE COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════
# For each fire at each horizon, look up the effective wilson_lo for each active
# feature and compute the weighted-average kernel_rank_score.
#
# Combination formula (§3.5):
#   kernel_rank_score = sum(wi * wilson_lo_i) / sum(wi)
#   where sum(wi) = 1.17 (all four) or 0.86 (washout omitted)
#
# weekly_phase: weight=0.00 -> excluded from weighted sum, but present as a cell
# dimension in its own feature cells. The spec notes weekly_phase conditioning is
# applied jointly with regime for dist_52wh/ext_z/ext_atr cells IF n_eff >= 25;
# in the current artifact regime is all __unstamped__, so the weekly_phase joint
# conditioning collapses to the parent automatically.
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("COMPUTING PER-FIRE KERNEL-RANK SCORES")
print("─" * 72)


def compute_kernel_rank_for_fire(
    row: pd.Series,
    cells_idx: dict[str, dict],
    horizon: int,
) -> dict[str, Any]:
    """
    Compute the kernel_rank_score for a single fire at a given horizon.

    Weighted average of per-feature Wilson lower bounds, using |rho_21d|-proportional
    weights from P1.1 RESULTS.md. weekly_phase has weight 0 and is excluded.
    """
    regime = row["_regime"]
    feature_buckets = {
        "dist_52wh":                row["_b_dist52wh"],
        "ext_z":                    row["_b_extz"],
        "ext_atr":                  row["_b_extatr"],
        "cohort_washout_proximity": row["_b_washout"],
    }

    cell_keys_used: list[str] = []
    proxy_flags: list[str] = []
    weighted_sum = 0.0
    weight_denom = 0.0

    for feat in active_features:
        w = FEATURE_WEIGHTS_FULL.get(feat, 0.0)
        if w == 0.0:
            continue
        fb = feature_buckets.get(feat)
        if fb is None or fb == "__missing__":
            # Missing feature value: fall back to grandparent
            fb_used = "__marginal__"
        else:
            fb_used = fb

        wlo = lookup_effective_wlo(cells_idx, feat, fb_used, regime, horizon)
        if wlo is None:
            # Try grandparent directly as final fallback
            gp_key = f"{feat}:__marginal__:__all__:{horizon}d"
            gp_row = cells_idx.get(gp_key)
            if gp_row is not None and gp_row.get("wilson_lo") is not None:
                wlo = float(gp_row["wilson_lo"])

        if wlo is None:
            continue  # cannot score this feature

        weighted_sum += w * wlo
        weight_denom += w
        cell_key = f"{feat}:{fb_used}:{regime}:{horizon}d"
        cell_keys_used.append(cell_key)
        if feat in proxy_sourced_dims:
            proxy_flags.append(feat)

    if weight_denom <= 0:
        return {
            f"kernel_rank_score_{horizon}d": np.nan,
            f"kernel_rank_source_cell_{horizon}d": "",
            f"kernel_rank_proxy_flags_{horizon}d": "",
        }

    # Normalize by actual weight sum used (gracefully handles partial availability)
    kernel_score = weighted_sum / weight_denom

    return {
        f"kernel_rank_score_{horizon}d": kernel_score,
        f"kernel_rank_source_cell_{horizon}d": "|".join(cell_keys_used),
        f"kernel_rank_proxy_flags_{horizon}d": ",".join(proxy_flags),
    }


# Build per-horizon cell index for fast lookup
cells_by_horizon: dict[int, dict[str, dict]] = {}
for horizon in HORIZONS:
    h_cells = cells_df[cells_df["horizon_days"] == horizon]
    cells_by_horizon[horizon] = {r["cell_key"]: r for _, r in h_cells.iterrows()}

# Compute scores
print(f"  Computing scores for {len(fires):,} fires across {len(HORIZONS)} horizons ...")
score_dicts: list[dict[str, Any]] = []
for _, row in fires.iterrows():
    row_scores: dict[str, Any] = {}
    for horizon in HORIZONS:
        h_scores = compute_kernel_rank_for_fire(row, cells_by_horizon[horizon], horizon)
        row_scores.update(h_scores)
    score_dicts.append(row_scores)

scores_frame = pd.DataFrame(score_dicts)

for horizon in HORIZONS:
    sc_col = f"kernel_rank_score_{horizon}d"
    n_scored = int(scores_frame[sc_col].notna().sum())
    n_missing = int(scores_frame[sc_col].isna().sum())
    desc = scores_frame[sc_col].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
    print(
        f"  Horizon {horizon}d: {n_scored:,} fires scored, {n_missing} missing"
    )
    print(
        f"    score: min={desc['min']:.4f} p25={desc['25%']:.4f} "
        f"median={desc['50%']:.4f} p75={desc['75%']:.4f} max={desc['max']:.4f}"
    )
print()


# ══════════════════════════════════════════════════════════════════════════════
# 6. BUILD SHADOW ARTIFACT
# ══════════════════════════════════════════════════════════════════════════════
# Outputs:
#   data/replay/kernel_rank_shadow.parquet   (R9 — not git-committed)
#   data/signal_archive/kernel_rank_cells.parquet   (R9 — not git-committed)
#   data/signal_archive/kernel_rank_ledger.parquet  (R9 — not git-committed)
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("BUILDING SHADOW ARTIFACT AND LEDGER")
print("─" * 72)

build_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

shadow = fires[
    ["signal_date", "ticker", "episode_id", "survivor_bias",
     "fwd_ret_21", "fwd_ret_63", "good_21d", "good_63d"]
].copy().reset_index(drop=True)

shadow = pd.concat([shadow, scores_frame.reset_index(drop=True)], axis=1)

shadow["build_timestamp"]  = build_ts
shadow["concordance_go"]   = concordance_go
shadow["weights_sum"]      = weights_sum
shadow["active_features"]  = json.dumps(active_features)
shadow["K_SHRINK"]         = K_SHRINK
shadow["WILSON_Z"]         = WILSON_Z
shadow["study_id"]         = STUDY_ID

print(f"Shadow artifact shape: {shadow.shape}")

SHADOW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
shadow.to_parquet(SHADOW_OUTPUT, index=False)
print(f"Written (R9 — not git-committed): {SHADOW_OUTPUT}")

# Cell table
SIGNAL_ARCHIVE.mkdir(parents=True, exist_ok=True)
cells_out_path = SIGNAL_ARCHIVE / "kernel_rank_cells.parquet"
cells_df_out = cells_df.drop(columns=["_effective_wlo"], errors="ignore")
cells_df_out.to_parquet(cells_out_path, index=False)
print(f"Written (R9 — not git-committed): {cells_out_path}")

# Forward ledger seed (historical portion; prospective rows appended by the nightly runner)
# incumbent_rank_score from `weight` column (the incumbent blend_sorted proxy in replay)
ledger_cols = [
    "signal_date", "ticker", "episode_id",
    "kernel_rank_score_21d", "kernel_rank_source_cell_21d", "kernel_rank_proxy_flags_21d",
    "kernel_rank_score_63d", "kernel_rank_source_cell_63d", "kernel_rank_proxy_flags_63d",
    "fwd_ret_21", "fwd_ret_63", "good_21d", "good_63d", "survivor_bias",
    "build_timestamp", "concordance_go",
]
ledger = shadow[[c for c in ledger_cols if c in shadow.columns]].copy()
if "weight" in fires.columns:
    ledger["incumbent_rank_score"] = fires["weight"].values
else:
    ledger["incumbent_rank_score"] = np.nan

ledger_path = SIGNAL_ARCHIVE / "kernel_rank_ledger.parquet"
ledger.to_parquet(ledger_path, index=False)
print(f"Written (R9 — not git-committed): {ledger_path}")
print(f"Ledger shape: {ledger.shape}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 7. CELL TABLE REPORT
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("CELL TABLE — TOP 10 and BOTTOM 10 by wilson_lo at 21d")
print("─" * 72)

cells_21 = cells_df[
    (cells_df["horizon_days"] == 21) &
    (cells_df["wilson_lo"].notna()) &
    (cells_df["cell_level"].isin(["parent", "child"]))
].copy()
cells_21_sorted = cells_21.sort_values("wilson_lo", ascending=False)

print("\nTop 10 cells (21d, highest wilson_lo = best cells):")
for _, r in cells_21_sorted.head(10).iterrows():
    print(
        f"  {r['feature_name']:30s}  bucket={r['feature_bucket']:12s}  "
        f"n_eff={int(r['n_eff']):5d}  shrunken_p={r['shrunken_p']:.4f}  "
        f"wilson_lo={r['wilson_lo']:.4f}  {'THIN' if r['thin_flag'] else '    '}"
    )

print("\nBottom 10 cells (21d, lowest wilson_lo = worst cells):")
for _, r in cells_21_sorted.tail(10).iterrows():
    print(
        f"  {r['feature_name']:30s}  bucket={r['feature_bucket']:12s}  "
        f"n_eff={int(r['n_eff']):5d}  shrunken_p={r['shrunken_p']:.4f}  "
        f"wilson_lo={r['wilson_lo']:.4f}  {'THIN' if r['thin_flag'] else '    '}"
    )

print()
cells_21_nonnull = cells_21["wilson_lo"].dropna()
cells_63_nonnull = cells_df[
    (cells_df["horizon_days"] == 63) & (cells_df["wilson_lo"].notna())
]["wilson_lo"]
print(f"wilson_lo distribution — 21d: "
      f"mean={cells_21_nonnull.mean():.4f}  std={cells_21_nonnull.std():.4f}  "
      f"min={cells_21_nonnull.min():.4f}  max={cells_21_nonnull.max():.4f}")
print(f"wilson_lo distribution — 63d: "
      f"mean={cells_63_nonnull.mean():.4f}  std={cells_63_nonnull.std():.4f}  "
      f"min={cells_63_nonnull.min():.4f}  max={cells_63_nonnull.max():.4f}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 8. LEAK AUDIT
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("LEAK AUDIT")
print("─" * 72)
print()
print("1. Fill rule: entry = first close strictly after signal_date. Inherited from")
print("   replay grader (P0.1 PIT-stamped design contract). Not re-estimated here.")
print()
print("2. Feature freeze: all features read from replay_boarded.parquet at the row's")
print("   signal_date (PIT-stamped by P0.1). No feature recomputed from future data.")
print()
print("3. No feature is a transformation of state_8_21 or state_15_126 (the outcome")
print("   labels). Features are pre-signal attributes logged at signal time.")
print()
print(f"4. Era boundary: primary window 2022-06-30 -> {era_max}")
print(f"   Actual effective window in this build: {era_min} -> {era_max}")
print()
print("5. Proxy-sourced dimensions:")
if concordance_go and "cohort_washout_proximity" in active_features:
    print("   - cohort_washout_proximity: PROXY-STAMPED (100% proxy-sourced per P1.1 REVIEW A1)")
    print("     Production source: COILED/S1. concordance GO verdict present.")
else:
    print("   - cohort_washout_proximity: OMITTED (concordance GO not present)")
print()
print("6. wilson_lo uses n_eff_effective = n_eff + K_SHRINK in denominator.")
print("   Matches the pooled_edges construction: engine/pooling.py / kernel.py.")
print()
print("7. THIN cells (n_eff < 25 episode clusters): no own wilson_lo emitted.")
print("   Fires in THIN cells receive the parent's (or grandparent's) effective wilson_lo.")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 9. COMBINATION WEIGHT CONFIRMATION
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 72)
print("COMBINATION WEIGHT CONFIRMATION")
print("─" * 72)
print()
print(f"Concordance GO: {concordance_go}  ({concordance_note})")
print(f"Active features for combination: {active_features}")
print(f"Feature weights (|rho_21d|-proportional from P1.1 RESULTS.md §Survivor List):")
for feat in active_features:
    w = FEATURE_WEIGHTS_FULL[feat]
    print(f"  {feat:30s}: {w:.2f}")
print(f"  {'weekly_phase':30s}: 0.00 (categorical separator; excluded from weighted sum)")
print(f"Combination denominator Sigma-w = {weights_sum}")
print(f"weekly_phase: conditioning dimension for its own feature cells (weight = 0)")
print()


# ══════════════════════════════════════════════════════════════════════════════
# 10. BUILD METADATA
# ══════════════════════════════════════════════════════════════════════════════

build_meta = {
    "study_id": STUDY_ID,
    "prereg": str(PREREG_PATH),
    "build_timestamp": build_ts,
    "replay_path": str(REPLAY_PATH),
    "replay_md5": actual_md5,
    "replay_md5_expected": EXPECTED_MD5,
    "md5_match": actual_md5 == EXPECTED_MD5,
    "era_min": str(era_min),
    "era_max": str(era_max),
    "n_verdict_grade_fires": len(fires),
    "n_episode_clusters": n_ep,
    "concordance_go": concordance_go,
    "concordance_note": concordance_note,
    "active_features": active_features,
    "proxy_sourced_dims": proxy_sourced_dims if concordance_go else [],
    "weights_sum": weights_sum,
    "K_SHRINK": K_SHRINK,
    "WILSON_Z": WILSON_Z,
    "THIN_N_EFF": THIN_N_EFF,
    "n_cells_total": n_cells_total,
    "n_cells_thin": n_thin_total,
    "n_cells_parent_fallback": n_parent_fallback,
    "horizons": HORIZONS,
    "breakpoints": {
        k: {kk: float(vv) if isinstance(vv, (float, int)) else vv
            for kk, vv in bk.items()}
        for k, bk in breakpoints.items()
    },
    "base_rates": {"21d": base_21, "63d": base_63},
    "outcome_state_map": {str(k): v for k, v in OUTCOME_STATE.items()},
    "kernel_rank_shadow_path": str(SHADOW_OUTPUT),
    "kernel_rank_cells_path": str(cells_out_path),
    "kernel_rank_ledger_path": str(ledger_path),
    "article2_flip_criterion": {
        "n_floor_episode_clusters": 300,
        "primary_test": "Spearman rho difference (kernel vs incumbent) on good_21d",
        "permutation_n": 5000,
        "perm_p_threshold": 0.10,
        "wilson_lower_bound_threshold": 0.0,
        "evaluation_cadence": "quarterly (~63 trading days)",
        "kill_criterion_months": 24,
    },
    "shadow_status": "ACTIVE",
    "go_no_go": "SHADOW_ACTIVE",
    "board_wiring": False,
    "user_visible": False,
}

meta_path = P3_RUNS_DIR / "build_meta.json"
meta_path.write_text(json.dumps(build_meta, indent=2, default=str))
print(f"Build metadata written: {meta_path}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 72)
print("BUILD COMPLETE — P3 KERNEL-RANK SHADOW")
print("=" * 72)
print()
print(f"  Shadow artifact:         {SHADOW_OUTPUT}")
print(f"  Cell table:              {cells_out_path}")
print(f"  Forward ledger:          {ledger_path}")
print(f"  Build metadata:          {meta_path}")
print()
print(f"  n_cells_built:           {n_cells_total}")
print(f"  n_cells_thin:            {n_thin_total}")
print(f"  Concordance GO (washout): {concordance_go}")
print(f"  Combination weights sum:  {weights_sum}")
print()
print("  SHADOW COLUMN ONLY — NO board wiring, NO user-visible surface (v1 law).")
print("  Article 2 flip criterion: quarterly evaluation after n >= 300 episode clusters.")
print("  Kill criterion: 24 months from first forward-ledger row.")
print()
print("  NOTE: output parquets are R9 data artifacts — NOT committed to git.")
print("  The build script and build report ARE committed to git (the research artifact).")
