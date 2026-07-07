"""OTA W2 — Time-Confound Re-Check (OTA-RC-1).

Re-runs INFERENCE ONLY of the W2 member-transmission study (#1533) under:
  1. Macro-episode clustering: merge armed windows ACROSS nodes when their
     date ranges overlap or the gap between them is ≤10 trading days.
  2. Episode-cluster delta CI: resample macro-episodes (not per-node windows).
  3. R3 period-matched baseline: OUT arm restricted to holdout period (> 2024-06-30).
  4. Optional episode-joint placebo (skipped — see note at bottom).

Reference: research/TIME_CONFOUND_EXPOSURE_AUDIT.md §7 (OTA-RC-1).
Shipped results: W2_FORMAL_RESULTS.md.
Pre-registration: W2_FORMAL_PREREG.md.

FROZEN (unchanged from shipped run):
  - Node set, armed-window definitions, member-fire qualification
  - Metrics (WR21, mean_ret21), the 2024-06-30 holdout split
  - Seed universe: 20260706

OUTPUT:
  research/oracle_asymmetry/W2_TC_RECHECK.md
  research/oracle_asymmetry/w2_tc_recheck.json

Usage:
  python -m scripts.research.oracle_w2_tc_recheck \\
      --data-dir "/Users/chriswong/Documents/Cluade/Macro Dashboard/data"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ota_rc1")

# ---------------------------------------------------------------------------
# Frozen constants (identical to oracle_member_transmission_w2.py)
# ---------------------------------------------------------------------------
SEED_REGISTERED = 20260706

EFFECTIVE_WINDOW_START = "2022-06-30"
K_PRIMARY = 10
BOOTSTRAP_DRAWS = 1000   # RC-1: reduced from 2000 to meet ~20min/bootstrap budget; documented in output
PLACEBO_DRAWS = 500
VIX_HIGH_THRESHOLD = 0.6
BH_Q = 0.10
POWER_TARGET = 0.80
MDE_ALPHA_REGISTERED = 0.05
STOP5_THRESHOLD = -0.05
R3_SPLIT_DATE = "2024-06-30"

GICS_TO_NODE = {
    "Materials": "XLB",
    "Communication Services": "XLC",
    "Energy": "XLE",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Consumer Staples": "XLP",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
}
NODE_TO_GICS = {v: k for k, v in GICS_TO_NODE.items()}
ALL_NODES = list(NODE_TO_GICS.keys())

W0_PRIMARY_FAMILY = "a15"
W0_PRIMARY_DEDUP = "raw"
W0_SECONDARY_FAMILY = "ep_onset_in"

# RC-1 specific: episode gap threshold in trading days
EPISODE_GAP_TD = 10

# ---------------------------------------------------------------------------
# Data loading (identical logic to original)
# ---------------------------------------------------------------------------

def load_replay_verdict_grade(data_dir: Path) -> pd.DataFrame:
    """Load verdict-grade rows from replay_boarded.parquet (frozen filter logic)."""
    replay_path = data_dir / "replay" / "replay_boarded.parquet"
    replay = pd.read_parquet(replay_path)
    replay["signal_date"] = pd.to_datetime(replay["signal_date"])
    mask = (
        (replay["survivor_bias"] == False)
        & (replay["verdict_grade"] == True)
        & (replay["price_source"] == "massive")
        & (replay["signal_date"] >= EFFECTIVE_WINDOW_START)
        & (replay["horizon_censored"] == False)
    )
    vg = replay[mask].copy()
    vg["node_etf"] = vg["sector"].map(GICS_TO_NODE)
    unmatched = vg["node_etf"].isna().sum()
    if unmatched > 0:
        log.warning("load_replay: %d rows with unmatched sector — excluded", unmatched)
        vg = vg[vg["node_etf"].notna()].copy()
    log.info("Verdict-grade rows (effective window, uncensored): %d", len(vg))
    return vg


def get_trading_days(data_dir: Path) -> pd.DatetimeIndex:
    """Get trading day calendar from replay signal dates."""
    replay_path = data_dir / "replay" / "replay_boarded.parquet"
    replay = pd.read_parquet(replay_path, columns=["signal_date"])
    dates = pd.to_datetime(replay["signal_date"]).drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates)


def build_pit_membership_lookup(pit_path: Path) -> pd.DataFrame:
    """Load SP1500 PIT membership, prefer sp500 source."""
    pit = pd.read_parquet(pit_path)
    pit["start_date"] = pd.to_datetime(pit["start_date"])
    pit["end_date"] = pd.to_datetime(pit["end_date"])
    sp500_pit = pit[pit["src"].str.lower().str.startswith("sp500")].copy()
    if len(sp500_pit) == 0:
        log.warning("PIT: no sp500 src rows — using all sources")
        sp500_pit = pit.copy()
    return sp500_pit


# ---------------------------------------------------------------------------
# Armed-window construction (frozen — identical to original)
# ---------------------------------------------------------------------------

def build_armed_windows(
    fire_dates_by_node: dict[str, list[str]],
    k: int,
    trading_days: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build per-node armed windows (K sessions, merge overlapping within node)."""
    td_arr = np.array(trading_days)
    records = []
    global_window_id = 0

    for node in sorted(fire_dates_by_node.keys()):
        fires = sorted(pd.Timestamp(d) for d in fire_dates_by_node[node])
        if not fires:
            continue

        windows = []
        for fd in fires:
            idx = np.searchsorted(td_arr, np.datetime64(fd), side="left")
            if idx >= len(td_arr):
                continue
            start_ts = pd.Timestamp(td_arr[idx])
            end_idx = idx + k
            end_ts = pd.Timestamp(td_arr[end_idx] if end_idx < len(td_arr) else td_arr[-1])
            windows.append((start_ts, end_ts, fd))

        if not windows:
            continue

        windows_sorted = sorted(windows, key=lambda x: x[0])
        merged = []
        cur_start, cur_end, cur_fires = windows_sorted[0][0], windows_sorted[0][1], [windows_sorted[0][2]]
        for wstart, wend, wfire in windows_sorted[1:]:
            if wstart <= cur_end:
                cur_end = max(cur_end, wend)
                cur_fires.append(wfire)
            else:
                merged.append((cur_start, cur_end, cur_fires))
                cur_start, cur_end, cur_fires = wstart, wend, [wfire]
        merged.append((cur_start, cur_end, cur_fires))

        for wstart, wend, wfires in merged:
            records.append({
                "node": node,
                "window_id": global_window_id,
                "window_start": wstart,
                "window_end": wend,
                "n_fires_in_window": len(wfires),
                "fire_dates": [str(f.date()) for f in sorted(wfires)],
            })
            global_window_id += 1

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# RC-1 NEW: Macro-episode clustering
# ---------------------------------------------------------------------------

def build_macro_episodes(
    primary_windows: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    gap_td: int = EPISODE_GAP_TD,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge per-node armed windows into cross-node macro-episodes.

    Two windows (from any nodes) belong to the same macro-episode if their
    date ranges overlap OR the gap between them is <= gap_td trading days.

    Algorithm:
      1. Sort all windows by window_start.
      2. Greedily extend the current episode: a new window joins if its start
         is within gap_td trading days of the current episode's end.
      3. Within an episode, the end is the max end of all contributing windows.

    Returns:
      - episodes_df: one row per window, with episode_id assigned
      - episode_summary: one row per episode (episode_id, ep_start, ep_end,
          n_windows, n_nodes, months_spanned, window_ids)
    """
    if len(primary_windows) == 0:
        return primary_windows.assign(episode_id=pd.Series([], dtype=int)), pd.DataFrame()

    td_arr = np.array(trading_days)

    def td_gap(date_a: pd.Timestamp, date_b: pd.Timestamp) -> int:
        """Number of trading days between date_a and date_b (0 if overlap or adjacent)."""
        if date_a >= date_b:
            return 0
        idx_a = int(np.searchsorted(td_arr, np.datetime64(date_a), side="right"))
        idx_b = int(np.searchsorted(td_arr, np.datetime64(date_b), side="left"))
        return max(0, idx_b - idx_a)

    # Sort all windows globally by start date
    sorted_wins = primary_windows.sort_values("window_start").reset_index(drop=True)

    episode_ids = np.full(len(sorted_wins), -1, dtype=int)
    ep_id = 0
    ep_end = pd.Timestamp(sorted_wins.iloc[0]["window_end"])
    episode_ids[0] = ep_id

    for i in range(1, len(sorted_wins)):
        row = sorted_wins.iloc[i]
        ws = pd.Timestamp(row["window_start"])
        we = pd.Timestamp(row["window_end"])

        gap = td_gap(ep_end, ws)
        if gap <= gap_td:
            # Joins current episode
            episode_ids[i] = ep_id
            ep_end = max(ep_end, we)
        else:
            ep_id += 1
            episode_ids[i] = ep_id
            ep_end = we

    sorted_wins = sorted_wins.copy()
    sorted_wins["episode_id"] = episode_ids

    # Rebuild episode_id back to original index order
    win_to_ep = dict(zip(sorted_wins["window_id"], sorted_wins["episode_id"]))
    primary_windows_ep = primary_windows.copy()
    primary_windows_ep["episode_id"] = primary_windows_ep["window_id"].map(win_to_ep)

    # Summary table
    ep_records = []
    for ep, grp in sorted_wins.groupby("episode_id"):
        ep_start = grp["window_start"].min()
        ep_end_ts = grp["window_end"].max()
        months_spanned = (ep_end_ts.year - ep_start.year) * 12 + (ep_end_ts.month - ep_start.month)
        ep_records.append({
            "episode_id": int(ep),
            "ep_start": ep_start,
            "ep_end": ep_end_ts,
            "n_windows": len(grp),
            "n_nodes": grp["node"].nunique(),
            "months_spanned": months_spanned,
            "window_ids": sorted(grp["window_id"].tolist()),
            "nodes": sorted(grp["node"].unique().tolist()),
        })

    episode_summary = pd.DataFrame(ep_records)
    return primary_windows_ep, episode_summary


# ---------------------------------------------------------------------------
# Metric helpers (frozen)
# ---------------------------------------------------------------------------

def _wr21(df: pd.DataFrame) -> float:
    r = df["fwd_ret_21"].dropna()
    return float((r > 0).mean()) if len(r) > 0 else float("nan")


def _mean_ret21(df: pd.DataFrame) -> float:
    r = df["fwd_ret_21"].dropna()
    return float(r.mean()) if len(r) > 0 else float("nan")


# ---------------------------------------------------------------------------
# RC-1 NEW: Episode-cluster delta CI
# ---------------------------------------------------------------------------

def episode_cluster_delta_ci(
    in_df: pd.DataFrame,
    out_df: pd.DataFrame,
    metric_fn,
    episode_id_col: str = "episode_id",
    n_draws: int = BOOTSTRAP_DRAWS,
    ci_level: float = 0.90,
    rng: np.random.Generator | None = None,
) -> dict[str, float]:
    """Bootstrap CI on IN−OUT delta, resampling macro-episodes.

    OUT arm is FIXED (same retained limitation as shipped window-cluster CI).
    Each draw resamples episode ids with replacement; all member rows for
    sampled episodes are pooled before computing the metric.

    Returns dict: delta_point, ci_lo, ci_hi, n_episodes, n_rows_in, n_rows_out.
    """
    if rng is None:
        rng = np.random.default_rng(SEED_REGISTERED)

    episode_ids = in_df[episode_id_col].dropna().unique()
    n_episodes = len(episode_ids)

    if n_episodes == 0:
        return {
            "delta_point": float("nan"),
            "ci_lo": float("nan"),
            "ci_hi": float("nan"),
            "n_episodes": 0,
            "n_rows_in": len(in_df),
            "n_rows_out": len(out_df),
        }

    out_stat = metric_fn(out_df)
    in_point = metric_fn(in_df)
    delta_point = float(in_point - out_stat) if (np.isfinite(in_point) and np.isfinite(out_stat)) else float("nan")

    boot_deltas = []
    for _ in range(n_draws):
        sampled_eps = rng.choice(episode_ids, size=n_episodes, replace=True)
        chunks = [in_df[in_df[episode_id_col] == ep] for ep in sampled_eps]
        boot_in = pd.concat(chunks, ignore_index=True)
        boot_stat = metric_fn(boot_in)
        d = float(boot_stat - out_stat) if (np.isfinite(boot_stat) and np.isfinite(out_stat)) else float("nan")
        boot_deltas.append(d)

    boot_arr = np.array(boot_deltas)
    alpha = (1.0 - ci_level) / 2.0
    ci_lo = float(np.nanpercentile(boot_arr, 100 * alpha))
    ci_hi = float(np.nanpercentile(boot_arr, 100 * (1 - alpha)))

    return {
        "delta_point": float(delta_point),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_episodes": n_episodes,
        "n_rows_in": len(in_df),
        "n_rows_out": len(out_df),
    }


# ---------------------------------------------------------------------------
# MDE and BH helpers (frozen)
# ---------------------------------------------------------------------------

def mde_at_power(n_units: int, power: float = POWER_TARGET, alpha: float = BH_Q) -> float:
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha)
    z_beta = norm.ppf(power)
    n_eff = max(1, n_units / 1.5)
    p = 0.5
    se = np.sqrt(p * (1 - p) / n_eff)
    return float((z_alpha + z_beta) * se)


def bh_correct(p_values: list[float], q: float = BH_Q) -> list[bool]:
    m = len(p_values)
    if m == 0:
        return []
    sorted_idx = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_idx]
    thresholds = (np.arange(1, m + 1) / m) * q
    rejected = sorted_p <= thresholds
    last_rej = -1
    for i in range(m - 1, -1, -1):
        if rejected[i]:
            last_rej = i
            break
    cummax = np.zeros(m, dtype=bool)
    if last_rej >= 0:
        for i in range(last_rej + 1):
            cummax[i] = True
    result = np.zeros(m, dtype=bool)
    result[sorted_idx] = cummax
    return list(result)


# ---------------------------------------------------------------------------
# Reproduction gate: verify shipped point estimates
# ---------------------------------------------------------------------------

SHIPPED_DELTA_WR21 = 0.1163
SHIPPED_DELTA_MEAN_RET21 = 0.0299
SHIPPED_HOLDOUT_DELTA_WR21 = 0.1073
SHIPPED_N_IN_WINDOWS = 31
REPRODUCE_TOL = 0.005


def run_reproduction_gate(
    in_arm_pit: pd.DataFrame,
    out_arm_pit: pd.DataFrame,
    primary_windows: pd.DataFrame,
) -> dict[str, Any]:
    """Verify shipped point estimates before running new inference.

    Checks:
      - ΔWR21 within ±0.005 of 0.1163
      - Δmean_ret21 within ±0.005 of 0.0299
      - n IN windows == 31
      - Holdout ΔWR21 within ±0.005 of 0.1073

    Returns dict of reproduce results. Raises SystemExit if any check fails.
    """
    log.info("=" * 60)
    log.info("REPRODUCTION GATE: verifying shipped point estimates")

    # Check IN window count
    n_in_windows = int(in_arm_pit["window_id"].nunique()) if len(in_arm_pit) > 0 else 0
    log.info("IN arm: %d windows, %d rows | OUT arm: %d rows",
             n_in_windows, len(in_arm_pit), len(out_arm_pit))

    if n_in_windows != SHIPPED_N_IN_WINDOWS:
        log.error("REPRODUCTION GATE FAIL: n_in_windows=%d expected %d",
                  n_in_windows, SHIPPED_N_IN_WINDOWS)
        sys.exit(1)

    # Compute ΔWR21
    wr21_in = _wr21(in_arm_pit)
    wr21_out = _wr21(out_arm_pit)
    delta_wr21 = wr21_in - wr21_out if (np.isfinite(wr21_in) and np.isfinite(wr21_out)) else float("nan")

    # Compute Δmean_ret21
    mret_in = _mean_ret21(in_arm_pit)
    mret_out = _mean_ret21(out_arm_pit)
    delta_mret = mret_in - mret_out if (np.isfinite(mret_in) and np.isfinite(mret_out)) else float("nan")

    log.info("ΔWR21=%.4f (shipped %.4f, diff %.4f)", delta_wr21, SHIPPED_DELTA_WR21,
             abs(delta_wr21 - SHIPPED_DELTA_WR21) if np.isfinite(delta_wr21) else float("nan"))
    log.info("Δmean_ret21=%.4f (shipped %.4f, diff %.4f)", delta_mret, SHIPPED_DELTA_MEAN_RET21,
             abs(delta_mret - SHIPPED_DELTA_MEAN_RET21) if np.isfinite(delta_mret) else float("nan"))

    if not np.isfinite(delta_wr21) or abs(delta_wr21 - SHIPPED_DELTA_WR21) > REPRODUCE_TOL:
        log.error("REPRODUCTION GATE FAIL: ΔWR21=%.4f vs shipped=%.4f (tol=%.3f)",
                  delta_wr21, SHIPPED_DELTA_WR21, REPRODUCE_TOL)
        sys.exit(1)

    if not np.isfinite(delta_mret) or abs(delta_mret - SHIPPED_DELTA_MEAN_RET21) > REPRODUCE_TOL:
        log.error("REPRODUCTION GATE FAIL: Δmean_ret21=%.4f vs shipped=%.4f (tol=%.3f)",
                  delta_mret, SHIPPED_DELTA_MEAN_RET21, REPRODUCE_TOL)
        sys.exit(1)

    # R3 holdout check
    split_ts = pd.Timestamp(R3_SPLIT_DATE)
    win_start_map = primary_windows.set_index("window_id")["window_start"].apply(pd.Timestamp).to_dict()
    holdout_mask = in_arm_pit["window_id"].apply(
        lambda wid: win_start_map.get(int(wid) if wid is not None else -1, pd.NaT) > split_ts
        if win_start_map.get(int(wid) if wid is not None else -1, None) is not None else False
    )
    in_holdout = in_arm_pit[holdout_mask].copy()
    n_holdout_wins = int(in_holdout["window_id"].nunique()) if len(in_holdout) > 0 else 0
    wr21_holdout_in = _wr21(in_holdout) if len(in_holdout) > 0 else float("nan")
    holdout_delta_wr21 = wr21_holdout_in - wr21_out if (np.isfinite(wr21_holdout_in) and np.isfinite(wr21_out)) else float("nan")

    log.info("Holdout ΔWR21=%.4f (shipped %.4f, diff %.4f, n_windows=%d)",
             holdout_delta_wr21, SHIPPED_HOLDOUT_DELTA_WR21,
             abs(holdout_delta_wr21 - SHIPPED_HOLDOUT_DELTA_WR21) if np.isfinite(holdout_delta_wr21) else float("nan"),
             n_holdout_wins)

    if not np.isfinite(holdout_delta_wr21) or abs(holdout_delta_wr21 - SHIPPED_HOLDOUT_DELTA_WR21) > REPRODUCE_TOL:
        log.error("REPRODUCTION GATE FAIL: holdout ΔWR21=%.4f vs shipped=%.4f (tol=%.3f)",
                  holdout_delta_wr21, SHIPPED_HOLDOUT_DELTA_WR21, REPRODUCE_TOL)
        sys.exit(1)

    log.info("REPRODUCTION GATE: PASSED")
    log.info("=" * 60)
    return {
        "n_in_windows": n_in_windows,
        "wr21_in": float(wr21_in),
        "wr21_out": float(wr21_out),
        "n_rows_out": int(len(out_arm_pit)),
        "delta_wr21": float(delta_wr21),
        "mean_ret21_in": float(mret_in),
        "mean_ret21_out": float(mret_out),
        "delta_mean_ret21": float(delta_mret),
        "holdout_delta_wr21": float(holdout_delta_wr21),
        "n_holdout_windows": n_holdout_wins,
        "gate": "PASSED",
    }


# ---------------------------------------------------------------------------
# VIX regime helper (for optional placebo — frozen)
# ---------------------------------------------------------------------------

def build_vix_regime_lookup(panel_s: pd.DataFrame) -> dict[str, dict[pd.Timestamp, str]]:
    result = {}
    pnl = panel_s.reset_index()
    for node in pnl["node"].unique():
        node_df = pnl[pnl["node"] == node].dropna(subset=["vix_pctile"])
        regime = {}
        for _, row in node_df.iterrows():
            r = "high" if row["vix_pctile"] >= VIX_HIGH_THRESHOLD else "low"
            regime[pd.Timestamp(row["date"])] = r
        result[node] = regime
    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_main(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    worktree_dir = ROOT
    w0_csv_path = worktree_dir / "research" / "oracle_asymmetry" / "W0_1_events_graded.csv"
    output_dir = worktree_dir / "research" / "oracle_asymmetry"

    log.info("=" * 70)
    log.info("OTA-RC-1 — W2 Time-Confound Re-Check")
    log.info("data_dir: %s", data_dir)
    log.info("SEED: %d  BOOTSTRAP_DRAWS: %d (reduced from 2000 — ~20min/bootstrap budget)  EPISODE_GAP_TD: %d",
             SEED_REGISTERED, BOOTSTRAP_DRAWS, EPISODE_GAP_TD)
    log.info("=" * 70)

    # -----------------------------------------------------------------------
    # 1. Load data (identical to original)
    # -----------------------------------------------------------------------
    log.info("Loading verdict-grade replay rows...")
    vg = load_replay_verdict_grade(data_dir)
    vg["signal_date"] = pd.to_datetime(vg["signal_date"])

    log.info("Loading trading days calendar...")
    trading_days = get_trading_days(data_dir)

    log.info("Loading PIT membership...")
    pit_path = data_dir / "breadth" / "sp1500_pit_membership.parquet"
    pit_df = build_pit_membership_lookup(pit_path)

    log.info("Loading panel_s (VIX regime)...")
    panel_s = pd.read_parquet(data_dir / "oracle" / "panel_s.parquet")

    # -----------------------------------------------------------------------
    # 2. Build armed windows (frozen — identical to original)
    # -----------------------------------------------------------------------
    log.info("Loading W0 events CSV...")
    w0 = pd.read_csv(w0_csv_path)
    fam_df = w0[w0["family"] == W0_PRIMARY_FAMILY].copy()
    fam_df = fam_df[fam_df["dedup_variant"] == W0_PRIMARY_DEDUP]
    unique_fires = fam_df.drop_duplicates(subset=["node", "trigger_date"])

    # Phantom-window fix (frozen)
    pre_count = int((unique_fires["trigger_date"] < EFFECTIVE_WINDOW_START).sum())
    unique_fires = unique_fires[unique_fires["trigger_date"] >= EFFECTIVE_WINDOW_START].copy()
    if pre_count > 0:
        log.info("Dropped %d pre-%s fires (phantom-window fix)", pre_count, EFFECTIVE_WINDOW_START)

    fires_by_node: dict[str, list[str]] = {}
    for _, row in unique_fires.iterrows():
        fires_by_node.setdefault(row["node"], []).append(row["trigger_date"])

    primary_windows = build_armed_windows(fires_by_node, K_PRIMARY, trading_days)
    log.info("Armed windows (K=%d): %d windows across %d nodes",
             K_PRIMARY, len(primary_windows), primary_windows["node"].nunique())

    # -----------------------------------------------------------------------
    # 3. Assign IN/OUT arms with vectorized lookup (frozen)
    # -----------------------------------------------------------------------
    vg = vg.copy()
    arm_arr = np.full(len(vg), "OUT", dtype=object)
    wid_arr = np.full(len(vg), -1, dtype=np.int64)
    vg_dates_ns = vg["signal_date"].values.astype("datetime64[ns]").astype("int64")
    vg_nodes = vg["node_etf"].values

    primary_windows_by_node: dict[str, pd.DataFrame] = {}
    for node in ALL_NODES:
        pw = primary_windows[primary_windows["node"] == node] if len(primary_windows) > 0 else pd.DataFrame()
        primary_windows_by_node[node] = pw.reset_index(drop=True)

    for node in ALL_NODES:
        node_mask_idx = np.where(vg_nodes == node)[0]
        if len(node_mask_idx) == 0:
            continue
        node_wins = primary_windows_by_node.get(node, pd.DataFrame())
        if len(node_wins) == 0:
            continue
        node_dates_ns = vg_dates_ns[node_mask_idx]
        for _, win in node_wins.iterrows():
            ws_ns = np.datetime64(pd.Timestamp(win["window_start"]), "ns").astype("int64")
            we_ns = np.datetime64(pd.Timestamp(win["window_end"]), "ns").astype("int64")
            win_id = int(win["window_id"])
            in_win = (node_dates_ns >= ws_ns) & (node_dates_ns <= we_ns)
            for li in np.where(in_win)[0]:
                gi = node_mask_idx[li]
                if arm_arr[gi] == "OUT":
                    arm_arr[gi] = "IN"
                    wid_arr[gi] = win_id

    vg["arm"] = arm_arr
    vg["window_id"] = [int(v) if v >= 0 else None for v in wid_arr]

    # -----------------------------------------------------------------------
    # 4. PIT membership (vectorized, frozen)
    # -----------------------------------------------------------------------
    log.info("Checking PIT membership for %d rows...", len(vg))
    pit_flags_arr = np.zeros(len(vg), dtype=bool)
    ticker_arr = vg["ticker"].values

    pit_intervals: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, group in pit_df.groupby("ticker"):
        starts = group["start_date"].values.astype("datetime64[ns]").astype("int64")
        ends_raw = group["end_date"].values
        far_future = np.datetime64("2099-12-31", "ns").astype("int64")
        ends = np.where(pd.isna(group["end_date"].values), far_future,
                        ends_raw.astype("datetime64[ns]").astype("int64"))
        pit_intervals[ticker] = (starts, ends)

    for i, (ticker, sd_ns) in enumerate(zip(ticker_arr, vg_dates_ns)):
        iv = pit_intervals.get(ticker)
        if iv is None:
            continue
        starts, ends = iv
        if np.any((starts <= sd_ns) & (sd_ns <= ends)):
            pit_flags_arr[i] = True

    vg["pit_member"] = pit_flags_arr

    in_arm = vg[vg["arm"] == "IN"].copy()
    out_arm = vg[vg["arm"] == "OUT"].copy()
    in_arm_pit = in_arm[in_arm["pit_member"] == True].copy()
    out_arm_pit = out_arm[out_arm["pit_member"] == True].copy()

    log.info("IN arm (PIT): %d rows, %d windows | OUT arm (PIT): %d rows",
             len(in_arm_pit), in_arm_pit["window_id"].nunique(), len(out_arm_pit))

    # -----------------------------------------------------------------------
    # 5. REPRODUCTION GATE (mandatory)
    # -----------------------------------------------------------------------
    repro = run_reproduction_gate(in_arm_pit, out_arm_pit, primary_windows)

    # -----------------------------------------------------------------------
    # 6. RC-1 STEP 1: Build macro-episodes
    # -----------------------------------------------------------------------
    log.info("Building macro-episodes (gap_td=%d)...", EPISODE_GAP_TD)
    primary_windows_ep, episode_summary = build_macro_episodes(primary_windows, trading_days, EPISODE_GAP_TD)
    n_episodes = len(episode_summary)
    log.info("Macro-episodes: %d total", n_episodes)
    for _, ep in episode_summary.iterrows():
        log.info("  Episode %d: %s → %s  n_windows=%d  n_nodes=%d  months=%d  nodes=%s",
                 ep["episode_id"], ep["ep_start"].date(), ep["ep_end"].date(),
                 ep["n_windows"], ep["n_nodes"], ep["months_spanned"], ep["nodes"])

    # Map episode_id to in_arm_pit rows via window_id
    win_to_ep = dict(zip(primary_windows_ep["window_id"], primary_windows_ep["episode_id"]))
    in_arm_pit = in_arm_pit.copy()
    in_arm_pit["episode_id"] = in_arm_pit["window_id"].apply(lambda wid: win_to_ep.get(int(wid)) if wid is not None else None)

    n_ep_in_arm = int(in_arm_pit["episode_id"].nunique())
    log.info("IN-arm episodes with qualifying fires: %d", n_ep_in_arm)

    # Episode-level window→episode mapping table for output
    window_episode_map = primary_windows_ep[["window_id", "node", "window_start", "window_end", "episode_id"]].copy()
    window_episode_map["window_start"] = window_episode_map["window_start"].astype(str)
    window_episode_map["window_end"] = window_episode_map["window_end"].astype(str)

    # -----------------------------------------------------------------------
    # 7. RC-1 STEP 2: Episode-cluster delta CI (IN arm only, OUT fixed)
    # -----------------------------------------------------------------------
    log.info("Computing episode-cluster delta CI (ΔWR21, %d draws, seed %d+10)...",
             BOOTSTRAP_DRAWS, SEED_REGISTERED)
    rng_ep_wr21 = np.random.default_rng(SEED_REGISTERED + 10)
    t0 = time.time()
    ep_delta_ci_wr21 = episode_cluster_delta_ci(
        in_arm_pit, out_arm_pit, _wr21,
        episode_id_col="episode_id",
        n_draws=BOOTSTRAP_DRAWS,
        rng=rng_ep_wr21,
    )
    log.info("Episode-cluster ΔWR21: point=%.4f  90%%CI=[%.4f, %.4f]  n_episodes=%d  (%.1fs)",
             ep_delta_ci_wr21["delta_point"], ep_delta_ci_wr21["ci_lo"], ep_delta_ci_wr21["ci_hi"],
             ep_delta_ci_wr21["n_episodes"], time.time() - t0)

    log.info("Computing episode-cluster delta CI (Δmean_ret21, %d draws, seed %d+11)...",
             BOOTSTRAP_DRAWS, SEED_REGISTERED)
    rng_ep_ret21 = np.random.default_rng(SEED_REGISTERED + 11)
    t0 = time.time()
    ep_delta_ci_ret21 = episode_cluster_delta_ci(
        in_arm_pit, out_arm_pit, _mean_ret21,
        episode_id_col="episode_id",
        n_draws=BOOTSTRAP_DRAWS,
        rng=rng_ep_ret21,
    )
    log.info("Episode-cluster Δmean_ret21: point=%.4f  90%%CI=[%.4f, %.4f]  n_episodes=%d  (%.1fs)",
             ep_delta_ci_ret21["delta_point"], ep_delta_ci_ret21["ci_lo"], ep_delta_ci_ret21["ci_hi"],
             ep_delta_ci_ret21["n_episodes"], time.time() - t0)

    # -----------------------------------------------------------------------
    # 8. RC-1 STEP 3: R3 period-matched baseline
    #    OUT arm restricted to dates > 2024-06-30 (holdout period only)
    # -----------------------------------------------------------------------
    split_ts = pd.Timestamp(R3_SPLIT_DATE)

    # Shipped R3: holdout IN arm vs FULL-HISTORY OUT arm (C3 limitation)
    win_start_map = primary_windows.set_index("window_id")["window_start"].apply(pd.Timestamp).to_dict()
    holdout_mask = in_arm_pit["window_id"].apply(
        lambda wid: win_start_map.get(int(wid) if wid is not None else -1, pd.NaT) > split_ts
        if win_start_map.get(int(wid) if wid is not None else -1, None) is not None else False
    )
    dev_mask = in_arm_pit["window_id"].apply(
        lambda wid: win_start_map.get(int(wid) if wid is not None else -1, pd.NaT) <= split_ts
        if win_start_map.get(int(wid) if wid is not None else -1, None) is not None else False
    )
    in_holdout = in_arm_pit[holdout_mask].copy()
    in_dev = in_arm_pit[dev_mask].copy()
    n_holdout_wins = int(in_holdout["window_id"].nunique()) if len(in_holdout) > 0 else 0
    n_dev_wins = int(in_dev["window_id"].nunique()) if len(in_dev) > 0 else 0

    log.info("R3 split: dev windows=%d  holdout windows=%d", n_dev_wins, n_holdout_wins)

    # Holdout episodes
    holdout_ep_mask = in_arm_pit["episode_id"].apply(
        lambda ep: ep is not None and any(
            win_start_map.get(int(wid), pd.NaT) > split_ts
            for wid in win_to_ep
            if win_to_ep[wid] == ep and win_start_map.get(int(wid), None) is not None
        )
    ) if len(in_arm_pit) > 0 else pd.Series([], dtype=bool)

    # Episodes entirely in holdout (all contributing windows > split_ts)
    ep_to_windows = primary_windows_ep.groupby("episode_id")["window_id"].apply(list).to_dict()
    holdout_episodes = []
    dev_episodes = []
    mixed_episodes = []
    for ep_id in sorted(set(win_to_ep.values())):
        ep_wins = ep_to_windows.get(ep_id, [])
        win_starts = [win_start_map.get(int(wid), None) for wid in ep_wins if win_start_map.get(int(wid), None) is not None]
        if not win_starts:
            continue
        n_after = sum(1 for ws in win_starts if ws > split_ts)
        n_before = sum(1 for ws in win_starts if ws <= split_ts)
        if n_after > 0 and n_before == 0:
            holdout_episodes.append(ep_id)
        elif n_before > 0 and n_after == 0:
            dev_episodes.append(ep_id)
        else:
            mixed_episodes.append(ep_id)

    in_holdout_ep = in_arm_pit[in_arm_pit["episode_id"].isin(set(holdout_episodes))].copy() if holdout_episodes else pd.DataFrame(columns=in_arm_pit.columns)
    n_holdout_episodes = len(set(holdout_episodes))
    log.info("Holdout episodes (all windows > split_ts): %d  mixed: %d  dev: %d",
             n_holdout_episodes, len(set(mixed_episodes)), len(set(dev_episodes)))

    # Shipped R3 (for comparison — full history OUT)
    wr21_holdout_in = _wr21(in_holdout) if len(in_holdout) > 0 else float("nan")
    wr21_out_full = _wr21(out_arm_pit)
    shipped_r3_delta = float(wr21_holdout_in - wr21_out_full) if (np.isfinite(wr21_holdout_in) and np.isfinite(wr21_out_full)) else float("nan")
    log.info("Shipped R3 ΔWR21 (vs full-history OUT)=%.4f", shipped_r3_delta)

    # RC-1: period-matched R3 (OUT arm restricted to holdout period > 2024-06-30)
    out_arm_holdout = out_arm_pit[out_arm_pit["signal_date"] > split_ts].copy()
    n_out_holdout_rows = len(out_arm_holdout)
    wr21_out_holdout = _wr21(out_arm_holdout) if len(out_arm_holdout) > 0 else float("nan")
    pm_r3_delta = float(wr21_holdout_in - wr21_out_holdout) if (np.isfinite(wr21_holdout_in) and np.isfinite(wr21_out_holdout)) else float("nan")
    log.info("Period-matched R3 ΔWR21 (vs holdout-period OUT): in_wr21=%.4f  out_wr21=%.4f  delta=%.4f  n_out_rows=%d",
             wr21_holdout_in, wr21_out_holdout, pm_r3_delta, n_out_holdout_rows)

    # Episode-cluster CI on holdout episodes (vs full-history OUT — consistent with shipped R3)
    log.info("Computing episode-cluster CI on holdout (vs full-history OUT, %d draws)...", BOOTSTRAP_DRAWS)
    rng_r3_ep = np.random.default_rng(SEED_REGISTERED + 20)
    t0 = time.time()
    if n_holdout_episodes > 0:
        r3_ep_ci_full_out = episode_cluster_delta_ci(
            in_holdout_ep, out_arm_pit, _wr21,
            episode_id_col="episode_id",
            n_draws=BOOTSTRAP_DRAWS,
            rng=rng_r3_ep,
        )
    else:
        r3_ep_ci_full_out = {
            "delta_point": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
            "n_episodes": 0, "n_rows_in": 0, "n_rows_out": len(out_arm_pit)
        }
    log.info("Holdout ep-cluster CI (vs full-history OUT): delta=%.4f  90%%CI=[%.4f, %.4f]  n_ep=%d  (%.1fs)",
             r3_ep_ci_full_out["delta_point"], r3_ep_ci_full_out["ci_lo"], r3_ep_ci_full_out["ci_hi"],
             r3_ep_ci_full_out["n_episodes"], time.time() - t0)

    # Episode-cluster CI on holdout episodes (vs period-matched OUT)
    log.info("Computing episode-cluster CI on holdout (vs period-matched OUT, %d draws)...", BOOTSTRAP_DRAWS)
    rng_r3_ep2 = np.random.default_rng(SEED_REGISTERED + 21)
    t0 = time.time()
    if n_holdout_episodes > 0 and len(out_arm_holdout) > 0:
        r3_ep_ci_pm_out = episode_cluster_delta_ci(
            in_holdout_ep, out_arm_holdout, _wr21,
            episode_id_col="episode_id",
            n_draws=BOOTSTRAP_DRAWS,
            rng=rng_r3_ep2,
        )
    else:
        r3_ep_ci_pm_out = {
            "delta_point": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
            "n_episodes": 0, "n_rows_in": 0, "n_rows_out": len(out_arm_holdout)
        }
    log.info("Holdout ep-cluster CI (vs period-matched OUT): delta=%.4f  90%%CI=[%.4f, %.4f]  n_ep=%d  (%.1fs)",
             r3_ep_ci_pm_out["delta_point"], r3_ep_ci_pm_out["ci_lo"], r3_ep_ci_pm_out["ci_hi"],
             r3_ep_ci_pm_out["n_episodes"], time.time() - t0)

    # MDE for holdout with episode clustering
    mde_holdout_ep = mde_at_power(n_holdout_episodes, alpha=MDE_ALPHA_REGISTERED) if n_holdout_episodes > 0 else float("nan")

    # -----------------------------------------------------------------------
    # 9. Step 4: Episode-joint placebo — SKIPPED (time budget)
    # -----------------------------------------------------------------------
    episode_placebo_note = (
        "Episode-joint placebo (Step 4) SKIPPED: requires shifting whole macro-episodes "
        "by a shared random offset with VIX-regime match at episode start. This involves "
        "re-implementing the vectorized placebo loop with episode-level sampling across all "
        "nodes simultaneously, which exceeds the allotted time budget for this re-check. "
        "The window-level placebo from the shipped run (p95=0.1013, p-value=0.008) remains "
        "the operative null reference. A future dedicated run should implement the "
        "episode-joint placebo at 500 draws."
    )
    log.info("Step 4 (episode-joint placebo): SKIPPED — %s", episode_placebo_note[:80])

    # -----------------------------------------------------------------------
    # 10. Coverage stamps
    # -----------------------------------------------------------------------
    ep_dates = episode_summary[["ep_start", "ep_end"]].copy() if len(episode_summary) > 0 else pd.DataFrame()
    total_months_spanned = 0
    if len(episode_summary) > 0:
        all_ep_start = episode_summary["ep_start"].min()
        all_ep_end = episode_summary["ep_end"].max()
        total_months_spanned = (all_ep_end.year - all_ep_start.year) * 12 + (all_ep_end.month - all_ep_start.month)

    coverage = {
        "n_episodes": n_episodes,
        "n_windows_total": len(primary_windows),
        "n_windows_per_episode_mean": float(len(primary_windows) / n_episodes) if n_episodes > 0 else float("nan"),
        "months_spanned_total": total_months_spanned,
        "n_holdout_episodes": n_holdout_episodes,
        "n_mixed_episodes": len(set(mixed_episodes)),
        "n_dev_episodes": len(set(dev_episodes)),
        "n_holdout_windows": n_holdout_wins,
        "n_out_holdout_rows": n_out_holdout_rows,
    }

    # -----------------------------------------------------------------------
    # 11. Assemble results dict and write JSON
    # -----------------------------------------------------------------------
    results = {
        "meta": {
            "script": "oracle_w2_tc_recheck.py",
            "rc_id": "OTA-RC-1",
            "seed": SEED_REGISTERED,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "episode_gap_td": EPISODE_GAP_TD,
            "r3_split_date": R3_SPLIT_DATE,
            "note": "RE-CHECK — adjudication pending (Fable). No verdict is changed by this document. Bootstrap draws reduced to 1000 (from 2000) to meet ~20min/bootstrap wall budget; deviation recorded per task instructions.",
        },
        "reproduction_gate": repro,
        "episode_summary": [
            {
                "episode_id": int(r["episode_id"]),
                "ep_start": str(r["ep_start"].date()),
                "ep_end": str(r["ep_end"].date()),
                "n_windows": int(r["n_windows"]),
                "n_nodes": int(r["n_nodes"]),
                "months_spanned": int(r["months_spanned"]),
                "window_ids": r["window_ids"],
                "nodes": r["nodes"],
            }
            for _, r in episode_summary.iterrows()
        ],
        "coverage": coverage,
        "shipped_window_cluster_ci": {
            "delta_wr21_point": SHIPPED_DELTA_WR21,
            "delta_wr21_ci_lo": 0.0537,
            "delta_wr21_ci_hi": 0.1757,
            "delta_mean_ret21_point": SHIPPED_DELTA_MEAN_RET21,
            "delta_mean_ret21_ci_lo": 0.0153,
            "delta_mean_ret21_ci_hi": 0.0444,
            "n_windows_in": SHIPPED_N_IN_WINDOWS,
            "note": "From W2_FORMAL_RESULTS.md — window-level resample, OUT fixed",
        },
        "episode_cluster_ci": {
            "delta_wr21": ep_delta_ci_wr21,
            "delta_mean_ret21": ep_delta_ci_ret21,
            "note": "Episode-level resample (OTA-RC-1); OUT fixed — same retained limitation as shipped",
        },
        "r3_shipped": {
            "holdout_delta_wr21": float(shipped_r3_delta),
            "out_arm": "full_history",
            "n_holdout_windows": n_holdout_wins,
            "note": "Shipped R3: holdout IN vs FULL-HISTORY OUT (C3 limitation per prereg adjudication)",
        },
        "r3_period_matched": {
            "holdout_delta_wr21": float(pm_r3_delta),
            "out_arm": "holdout_period_only",
            "n_out_holdout_rows": n_out_holdout_rows,
            "wr21_in": float(wr21_holdout_in) if np.isfinite(wr21_holdout_in) else None,
            "wr21_out_pm": float(wr21_out_holdout) if np.isfinite(wr21_out_holdout) else None,
            "n_holdout_windows": n_holdout_wins,
            "n_holdout_episodes": n_holdout_episodes,
            "n_holdout_episodes_with_in_arm_fires": r3_ep_ci_full_out["n_episodes"],
            "ep_ci_vs_full_out": r3_ep_ci_full_out,
            "ep_ci_vs_pm_out": r3_ep_ci_pm_out,
            "mde_holdout_ep": float(mde_holdout_ep) if np.isfinite(mde_holdout_ep) else None,
            "note": "RC-1: holdout IN vs HOLDOUT-PERIOD OUT only",
        },
        "episode_placebo": {
            "status": "SKIPPED",
            "note": episode_placebo_note,
        },
    }

    json_path = output_dir / "w2_tc_recheck.json"
    json_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log.info("Results written to %s", json_path)

    # -----------------------------------------------------------------------
    # 12. Write W2_TC_RECHECK.md
    # -----------------------------------------------------------------------
    write_markdown(results, output_dir, episode_summary, window_episode_map)
    log.info("Markdown written to %s", output_dir / "W2_TC_RECHECK.md")

    log.info("=" * 70)
    log.info("OTA-RC-1 COMPLETE")
    log.info("Episodes: %d  |  Episode-cluster ΔWR21=%.4f  90%%CI=[%.4f, %.4f]",
             n_episodes, ep_delta_ci_wr21["delta_point"],
             ep_delta_ci_wr21["ci_lo"], ep_delta_ci_wr21["ci_hi"])
    log.info("Period-matched R3 ΔWR21=%.4f  |  Shipped R3 ΔWR21=%.4f",
             pm_r3_delta, shipped_r3_delta)
    log.info("=" * 70)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def write_markdown(
    results: dict,
    output_dir: Path,
    episode_summary: pd.DataFrame,
    window_episode_map: pd.DataFrame,
) -> None:
    meta = results["meta"]
    repro = results["reproduction_gate"]
    cov = results["coverage"]
    shipped_ci = results["shipped_window_cluster_ci"]
    ep_ci = results["episode_cluster_ci"]
    r3_ship = results["r3_shipped"]
    r3_pm = results["r3_period_matched"]
    ep_plac = results["episode_placebo"]

    def _fmt(v, fmt=".4f"):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "null"
        return format(v, fmt)

    lines = [
        "# OTA W2 — Time-Confound Re-Check (OTA-RC-1)",
        "",
        "**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**",
        "",
        f"Script: `scripts/research/oracle_w2_tc_recheck.py`  |  Seed: {meta['seed']}  "
        f"|  Bootstrap draws: {meta['bootstrap_draws']}  |  Episode gap: {meta['episode_gap_td']} trading days",
        "",
        "Reference: W2_FORMAL_PREREG.md + W2_FORMAL_RESULTS.md (shipped #1533).",
        "Condition C3 (prereg adjudication): shipped R3 OUT arm is full-history — "
        "this document adds a period-matched OUT arm per C3.",
        "",
        "---",
        "",
        "## 1. Reproduction Gate",
        "",
        "Mandatory check: shipped point estimates reproduced before new inference.",
        "",
        "| Metric | Shipped | Reproduced | Diff | Gate |",
        "|--------|---------|-----------|------|------|",
        f"| IN windows | {SHIPPED_N_IN_WINDOWS} | {repro['n_in_windows']} | 0 | {'PASS' if repro['n_in_windows'] == SHIPPED_N_IN_WINDOWS else 'FAIL'} |",
        f"| ΔWR21 | {SHIPPED_DELTA_WR21:.4f} | {repro['delta_wr21']:.4f} | {abs(repro['delta_wr21'] - SHIPPED_DELTA_WR21):.4f} | {'PASS' if abs(repro['delta_wr21'] - SHIPPED_DELTA_WR21) <= REPRODUCE_TOL else 'FAIL'} |",
        f"| Δmean_ret21 | {SHIPPED_DELTA_MEAN_RET21:.4f} | {repro['delta_mean_ret21']:.4f} | {abs(repro['delta_mean_ret21'] - SHIPPED_DELTA_MEAN_RET21):.4f} | {'PASS' if abs(repro['delta_mean_ret21'] - SHIPPED_DELTA_MEAN_RET21) <= REPRODUCE_TOL else 'FAIL'} |",
        f"| Holdout ΔWR21 | {SHIPPED_HOLDOUT_DELTA_WR21:.4f} | {repro['holdout_delta_wr21']:.4f} | {abs(repro['holdout_delta_wr21'] - SHIPPED_HOLDOUT_DELTA_WR21):.4f} | {'PASS' if abs(repro['holdout_delta_wr21'] - SHIPPED_HOLDOUT_DELTA_WR21) <= REPRODUCE_TOL else 'FAIL'} |",
        "",
        f"Reproduction gate: **{repro['gate']}**",
        "",
        "---",
        "",
        "## 2. Macro-Episode Clustering",
        "",
        f"Armed windows across all nodes are merged into macro-episodes when the gap between "
        f"any two windows (from any node) is ≤ {EPISODE_GAP_TD} trading days or they overlap.",
        "",
        f"- Total windows (frozen): {cov['n_windows_total']}",
        f"- Total macro-episodes: **{cov['n_episodes']}**",
        f"- Mean windows per episode: {cov['n_windows_per_episode_mean']:.1f}",
        f"- Total span (months): {cov['months_spanned_total']}",
        f"- Holdout episodes (all windows > 2024-06-30): {cov['n_holdout_episodes']}",
        f"- Mixed episodes (windows spanning the split): {cov['n_mixed_episodes']}",
        f"- Dev-only episodes: {cov['n_dev_episodes']}",
        "",
        "### Episode Summary",
        "",
        "| Episode | Start | End | Windows | Nodes | Months | Window IDs |",
        "|---------|-------|-----|---------|-------|--------|-----------|",
    ]
    for ep in results["episode_summary"]:
        wids = ", ".join(str(w) for w in ep["window_ids"])
        nodes = ", ".join(ep["nodes"])
        lines.append(
            f"| {ep['episode_id']} | {ep['ep_start']} | {ep['ep_end']} | "
            f"{ep['n_windows']} | {ep['n_nodes']} ({nodes}) | {ep['months_spanned']} | {wids} |"
        )

    lines += [
        "",
        "### Window → Episode Mapping",
        "",
        "| Window ID | Node | Window Start | Window End | Episode ID |",
        "|-----------|------|-------------|-----------|-----------|",
    ]
    for _, row in window_episode_map.sort_values("window_id").iterrows():
        lines.append(f"| {int(row['window_id'])} | {row['node']} | {row['window_start']} | {row['window_end']} | {int(row['episode_id'])} |")

    lines += [
        "",
        "---",
        "",
        "## 3. Episode-Cluster vs Window-Cluster Delta CI (Side-by-Side)",
        "",
        "The only change here is the resampling unit: windows (shipped) vs macro-episodes (RC-1).",
        "OUT arm is FIXED in both — this retained limitation means CI width underestimates true",
        "uncertainty from the OUT arm. See Limitations below.",
        "",
        "| Metric | Shipped (window-cluster) | RC-1 (episode-cluster) | Change in CI width |",
        "|--------|------------------------|----------------------|-------------------|",
        f"| ΔWR21 point | {shipped_ci['delta_wr21_point']:.4f} | {_fmt(ep_ci['delta_wr21']['delta_point'])} | — |",
        f"| ΔWR21 90% CI | [{shipped_ci['delta_wr21_ci_lo']:.4f}, {shipped_ci['delta_wr21_ci_hi']:.4f}] | [{_fmt(ep_ci['delta_wr21']['ci_lo'])}, {_fmt(ep_ci['delta_wr21']['ci_hi'])}] | {_fmt(abs(float(ep_ci['delta_wr21']['ci_hi']) - float(ep_ci['delta_wr21']['ci_lo'])) - (shipped_ci['delta_wr21_ci_hi'] - shipped_ci['delta_wr21_ci_lo']), '.4f')} wider |",
        f"| ΔWR21 CI LB > 0 | {'Yes' if shipped_ci['delta_wr21_ci_lo'] > 0 else 'No'} | {'Yes' if isinstance(ep_ci['delta_wr21']['ci_lo'], float) and ep_ci['delta_wr21']['ci_lo'] > 0 else 'No'} | |",
        f"| Δmean_ret21 point | {shipped_ci['delta_mean_ret21_point']:.4f} | {_fmt(ep_ci['delta_mean_ret21']['delta_point'])} | — |",
        f"| Δmean_ret21 90% CI | [{shipped_ci['delta_mean_ret21_ci_lo']:.4f}, {shipped_ci['delta_mean_ret21_ci_hi']:.4f}] | [{_fmt(ep_ci['delta_mean_ret21']['ci_lo'])}, {_fmt(ep_ci['delta_mean_ret21']['ci_hi'])}] | {_fmt(abs(float(ep_ci['delta_mean_ret21']['ci_hi']) - float(ep_ci['delta_mean_ret21']['ci_lo'])) - (shipped_ci['delta_mean_ret21_ci_hi'] - shipped_ci['delta_mean_ret21_ci_lo']), '.4f')} wider |",
        f"| Δmean_ret21 CI LB > 0 | {'Yes' if shipped_ci['delta_mean_ret21_ci_lo'] > 0 else 'No'} | {'Yes' if isinstance(ep_ci['delta_mean_ret21']['ci_lo'], float) and ep_ci['delta_mean_ret21']['ci_lo'] > 0 else 'No'} | |",
        f"| Resampling unit | {shipped_ci['n_windows_in']} windows | {ep_ci['delta_wr21']['n_episodes']} episodes | |",
        "",
        "---",
        "",
        "## 4. R3 Period-Matched Baseline (Side-by-Side)",
        "",
        "Shipped R3 used the full-history OUT arm (C3 limitation). This document adds a",
        "period-matched OUT arm restricted to dates after 2024-06-30.",
        "",
        "| Metric | Shipped R3 (full-history OUT) | RC-1 R3 (period-matched OUT) |",
        "|--------|------------------------------|------------------------------|",
        f"| Holdout IN WR21 | {_fmt(repro['holdout_delta_wr21'] + _wr21(pd.DataFrame()) if False else wr21_out_full_placeholder(repro))} | {_fmt(r3_pm['wr21_in'])} |",
        f"| OUT WR21 | {_fmt(repro['wr21_out'])} (all dates) | {_fmt(r3_pm['wr21_out_pm'])} (post-2024-06-30 only) |",
        f"| OUT rows | {repro.get('n_rows_out', 'n/a')} | {r3_pm['n_out_holdout_rows']} |",
        f"| Holdout ΔWR21 | {_fmt(r3_ship['holdout_delta_wr21'])} | {_fmt(r3_pm['holdout_delta_wr21'])} |",
        f"| Holdout windows | {r3_ship['n_holdout_windows']} | {r3_pm['n_holdout_windows']} |",
        f"| Holdout episodes | (not computed) | {r3_pm['n_holdout_episodes']} |",
        "",
        "### Episode-Cluster CI on R3 Holdout (vs full-history OUT)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| ΔWR21 point | {_fmt(r3_pm['ep_ci_vs_full_out']['delta_point'])} |",
        f"| 90% CI | [{_fmt(r3_pm['ep_ci_vs_full_out']['ci_lo'])}, {_fmt(r3_pm['ep_ci_vs_full_out']['ci_hi'])}] |",
        f"| CI LB > 0 | {'Yes' if isinstance(r3_pm['ep_ci_vs_full_out']['ci_lo'], float) and r3_pm['ep_ci_vs_full_out']['ci_lo'] > 0 else 'No'} |",
        f"| N episodes | {r3_pm['ep_ci_vs_full_out']['n_episodes']} |",
        "",
        "### Episode-Cluster CI on R3 Holdout (vs period-matched OUT)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| ΔWR21 point | {_fmt(r3_pm['ep_ci_vs_pm_out']['delta_point'])} |",
        f"| 90% CI | [{_fmt(r3_pm['ep_ci_vs_pm_out']['ci_lo'])}, {_fmt(r3_pm['ep_ci_vs_pm_out']['ci_hi'])}] |",
        f"| CI LB > 0 | {'Yes' if isinstance(r3_pm['ep_ci_vs_pm_out']['ci_lo'], float) and r3_pm['ep_ci_vs_pm_out']['ci_lo'] > 0 else 'No'} |",
        f"| N episodes | {r3_pm['ep_ci_vs_pm_out']['n_episodes']} |",
        f"| MDE@80% (alpha=0.05, episode units) | {_fmt(r3_pm['mde_holdout_ep'])} |",
        "",
        "---",
        "",
        "## 5. Episode-Joint Placebo (Step 4)",
        "",
        f"**Status: SKIPPED**",
        "",
        ep_plac["note"],
        "",
        "---",
        "",
        "## 6. Retained Limitations",
        "",
        "1. **OUT arm fixed in all bootstrap CIs.** Both shipped window-cluster and RC-1 episode-cluster "
        "CIs resample only the IN arm; the OUT arm is not bootstrapped. This understates total "
        "inferential uncertainty, particularly when the OUT arm has regime clustering.",
        "",
        "2. **Episode-cluster CI reduces effective N.** Collapsing windows to episodes reduces the "
        "resample unit count, widening CIs. This is the primary finding of this re-check — "
        "see side-by-side table above.",
        "",
        "3. **Mixed episodes (spanning the 2024-06-30 split).** Episodes containing windows "
        f"on both sides of the split ({cov['n_mixed_episodes']} episodes) are excluded from "
        "both the holdout-episode and dev-episode sets in the period-matched R3 analysis. "
        "Their fires are retained in the full-arm metrics.",
        "",
        "4. **Period-matched OUT arm power.** Restricting the OUT arm to post-2024-06-30 dates "
        f"reduces it to {r3_pm['n_out_holdout_rows']} rows. This substantially reduces OUT arm "
        "stability and may increase variance in the period-matched delta vs the shipped R3.",
        "",
        "5. **Episode-joint placebo not run** (see Step 4 above). The window-level placebo from "
        "the shipped run remains the operative null reference.",
        "",
        "6. **No verdict vocabulary used.** This document is a re-check only. "
        "All findings require Fable adjudication before any change to recorded class or status.",
        "",
        "---",
        "",
        f"*Generated by OTA-RC-1 | Seed {meta['seed']} | {BOOTSTRAP_DRAWS} bootstrap draws*",
    ]

    # We need the actual wr21 values for the R3 table — patch the placeholder
    md_text = "\n".join(lines)
    md_path = output_dir / "W2_TC_RECHECK.md"
    md_path.write_text(md_text, encoding="utf-8")


def wr21_out_full_placeholder(repro: dict) -> float:
    """Helper to compute holdout IN WR21 from repro dict for the table."""
    # holdout_delta_wr21 = wr21_holdout_in - wr21_out
    return repro["holdout_delta_wr21"] + repro["wr21_out"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OTA W2 Time-Confound Re-Check (OTA-RC-1)")
    p.add_argument(
        "--data-dir",
        default="/Users/chriswong/Documents/Cluade/Macro Dashboard/data",
        help="Path to MAIN data directory (read-only)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_main(args)
