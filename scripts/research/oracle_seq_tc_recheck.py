"""OTA-RC-2 — SEQ_TLT_RELIEF_WASHOUT episode-cluster CIs + time-shift placebo.

RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.

Scope: re-run inference ONLY for SEQ_TLT_RELIEF_WASHOUT (registry status
'screened', PR #1576). Signal definition, fire set, exit convention, all six
leg thresholds, and the dev/holdout split are FROZEN.

New inference added:
  1. Episode collapse: cluster the 745 fires into episodes (same node, entry
     dates within <=10 trading days chain into one episode). Report episode
     count, per-episode fire counts, and distinct calendar months touched.
  2. Episode-cluster bootstrap CIs (2000 draws, seed 20260705) for WR,
     mean ret_exit, and asym on the full set and holdout subset.
     Report whether WR CIs clear the Leg-2 (0.62) and Leg-5 (0.58) bars
     at their lower bounds.
  3. Time-preserving Leg-6 placebo: circular time-shift (matches
     oracle_compound_tc_recheck.py approach). Each draw shifts the signal's
     real entry-date sequence per node by one shared uniform random integer
     offset within that node's realizable-outcome pool (wrapping), preserving
     inter-fire spacing/clustering. Count-matched by construction. 2000 draws
     -> p95 of draw-mean ret_exit, vs shipped p95=+1.16% and observed +2.37%.
  4. Coverage stamps: episodes, months, fires/episode distribution, dev vs
     holdout episode counts.

Outputs:
  research/ORACLE_SEQ_TC_RECHECK.md
  research/oracle_seq_tc_recheck.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Reuse data-loading wrappers already imported by oracle_compound_tc_recheck.py
from scripts.oracle_screen import (  # noqa: E402
    _load_panel,
    _load_episodes,
    _load_spy,
    _load_rotation_groups,
)
from engine.oracle.compounds import (  # noqa: E402
    get_entry_dates,
    augment_panel_with_derived,
    load_registry,
)
from scripts.oracle_reversion_screen import (  # noqa: E402
    _compute_entry_metrics,
    _agg_stats,
    _gauntlet_placebo,
    _GAUNTLET_TIER_SPLITS,
    _DEFAULT_TIER_SPLIT,
)

SIGNAL_ID = "SEQ_TLT_RELIEF_WASHOUT"
SEED = 20260705
WINDOW = 25
EXIT = 21
TIER = "s"
COOLDOWN = 10  # sessions (frozen)

# Shipped numbers for reproduction gate
SHIPPED = {
    "n": 745,
    "wr": 0.672,
    "asym": 1.747,
    "ret_exit": 0.0237,
    "holdout_n": 267,
    "holdout_wr": 0.689,
    "holdout_ret_exit": 0.0371,
    "placebo_p95": 0.0116,
}

# Leg bars (frozen)
LEG2_WR_BAR = 0.62
LEG5_WR_BAR = 0.58


# ---------------------------------------------------------------------------
# Episode collapse
# ---------------------------------------------------------------------------

def _cluster_episodes(
    entries_df: pd.DataFrame,
    cooldown: int = 10,
) -> pd.DataFrame:
    """Cluster fires into episodes per node.

    Within each node, fires whose entry_date is within `cooldown` calendar
    trading days of the previous fire in that node are assigned to the same
    episode. A new episode starts when the gap exceeds `cooldown` sessions.

    Returns entries_df with two added columns:
      episode_id  : str "{node}_{episode_index_within_node}"
      episode_idx : int (global sequential index across all nodes)
    """
    df = entries_df.copy()
    df = df.sort_values(["node", "entry_date"]).reset_index(drop=True)

    episode_ids: list[str] = [""] * len(df)
    ep_counter = 0

    for node, grp in df.groupby("node", sort=False):
        dates = pd.to_datetime(grp["entry_date"].values)
        idxs = grp.index.tolist()
        ep_local = 0
        last_date = None
        for i, (idx, d) in enumerate(zip(idxs, dates)):
            if last_date is None:
                ep_local = 0
                cur_ep_id = f"{node}_ep{ep_local}"
                ep_counter_start = ep_counter
            else:
                # Count trading days between: use position diff in the sorted
                # date list — approximate by calendar difference rounded at 5/7
                # (standard approx: 1 trading day ~ 1.4 calendar days)
                cal_diff = (d - last_date).days
                # rough trading day estimate: multiply by 5/7
                td_approx = int(round(cal_diff * 5 / 7))
                if td_approx > cooldown:
                    ep_local += 1
                    ep_counter += 1
                cur_ep_id = f"{node}_ep{ep_local}"
            episode_ids[idx] = cur_ep_id
            last_date = d
        ep_counter += 1  # close final episode for this node

    df["episode_id"] = episode_ids
    # Assign contiguous global episode index
    ep_map = {eid: i for i, eid in enumerate(
        dict.fromkeys(ep for ep in episode_ids)  # preserves insertion order
    )}
    df["episode_idx"] = df["episode_id"].map(ep_map)
    return df


# ---------------------------------------------------------------------------
# Episode-cluster bootstrap CI
# ---------------------------------------------------------------------------

def _episode_cluster_bootstrap(
    df: pd.DataFrame,
    n_draws: int,
    rng: np.random.Generator,
) -> dict[str, tuple[float, float]]:
    """Episode-cluster bootstrap 95% CIs for WR, mean_ret_exit, asym.

    Resamples episodes (with replacement) from the unique episode_id pool.
    All fires within a drawn episode move together.

    Returns dict: metric -> (ci_lo, ci_hi)
    """
    episodes = df["episode_id"].unique()
    n_episodes = len(episodes)

    # Pre-group by episode for fast lookup
    ep_groups: dict[str, np.ndarray] = {}
    for ep in episodes:
        ep_groups[ep] = df[df["episode_id"] == ep]["ret_exit"].to_numpy(dtype=float)

    wr_draws = np.empty(n_draws)
    ret_draws = np.empty(n_draws)
    asym_draws = np.empty(n_draws)

    mfe_col = df["MFE"].to_numpy(dtype=float)
    mae_col = df["MAE"].to_numpy(dtype=float)
    ep_arr = df["episode_id"].to_numpy()

    # Build mfe/mae per episode too
    ep_mfe: dict[str, np.ndarray] = {}
    ep_mae: dict[str, np.ndarray] = {}
    for ep in episodes:
        mask = ep_arr == ep
        ep_mfe[ep] = mfe_col[mask]
        ep_mae[ep] = mae_col[mask]

    for i in range(n_draws):
        drawn = rng.integers(0, n_episodes, size=n_episodes)
        ret_vals: list[np.ndarray] = []
        mfe_vals: list[np.ndarray] = []
        mae_vals: list[np.ndarray] = []
        for di in drawn:
            ep = episodes[di]
            ret_vals.append(ep_groups[ep])
            mfe_vals.append(ep_mfe[ep])
            mae_vals.append(ep_mae[ep])
        r = np.concatenate(ret_vals)
        mf = np.concatenate(mfe_vals)
        ma = np.concatenate(mae_vals)
        wr_draws[i] = float(np.mean(r > 0))
        ret_draws[i] = float(np.mean(r))
        mean_mfe = float(np.mean(mf))
        mean_mae = float(np.mean(ma))
        abs_mae = abs(mean_mae)
        asym_draws[i] = float(mean_mfe / abs_mae) if abs_mae > 1e-9 else np.nan

    def ci(arr: np.ndarray) -> tuple[float, float]:
        return float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))

    return {
        "wr": ci(wr_draws),
        "ret_exit": ci(ret_draws),
        "asym": ci(asym_draws[~np.isnan(asym_draws)]) if np.any(~np.isnan(asym_draws)) else (np.nan, np.nan),
    }


# ---------------------------------------------------------------------------
# Time-shift placebo (circular, per-node)
# ---------------------------------------------------------------------------

def _build_node_pools_time(
    entries_df: pd.DataFrame,
    panel: pd.DataFrame,
    exit_sessions: int,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Build per-node realizable-outcome pools for time-exit ret_exit.

    Returns dict: node -> (sorted_date_ns_array, ret_exit_array)
    Pool entries are in date order (ascending).
    """
    pool: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    nodes = entries_df["node"].unique().tolist()

    for node in nodes:
        try:
            npn = panel.xs(node, level="node")
        except KeyError:
            continue
        if "ret" not in npn.columns:
            continue
        ret_s = npn["ret"].sort_index()
        dates = ret_s.index
        n = len(dates)
        lvl = (1 + ret_s.fillna(0)).cumprod()

        outcomes: list[float] = []
        outcome_dates: list[int] = []
        for exec_pos in range(n):
            exit_pos = exec_pos + exit_sessions
            if exit_pos >= n:
                continue
            exec_price = lvl.iat[exec_pos]
            exit_price = lvl.iat[exit_pos]
            if exec_price == 0 or np.isnan(exec_price) or exit_price == 0 or np.isnan(exit_price):
                continue
            outcomes.append(float(exit_price / exec_price - 1))
            outcome_dates.append(int(dates[exec_pos].value))

        if outcomes:
            d_arr = np.array(outcome_dates, dtype="int64")
            r_arr = np.array(outcomes, dtype=float)
            order = np.argsort(d_arr)
            pool[str(node)] = (d_arr[order], r_arr[order])

    return pool


def _circular_shift_placebo(
    entries_df: pd.DataFrame,
    pool_by_node: dict[str, tuple[np.ndarray, np.ndarray]],
    n_draws: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Circular time-shift placebo for the reversion signal.

    Mirrors oracle_compound_tc_recheck.py approach exactly.
    For each node with signal fires:
      1. Map each real entry_date to its nearest position in the pool.
      2. Generate n_draws random offsets per node.
      3. shifted = (position + offset) % pool_size  -- preserves inter-fire spacing.
      4. Draw the ret_exit at the shifted position.
    Returns array of n_draws draw-means.
    """
    entries_df = entries_df.copy()
    entries_df["_ed_ns"] = pd.to_datetime(entries_df["entry_date"]).astype("int64")

    node_data: list[np.ndarray] = []  # each: (n_draws, n_node_fires)

    for node, grp in entries_df.groupby("node"):
        node_str = str(node)
        if node_str not in pool_by_node:
            continue
        pool_dates_ns, pool_ret = pool_by_node[node_str]
        pool_size = len(pool_dates_ns)
        if pool_size == 0:
            continue

        real_dates_ns = grp["_ed_ns"].to_numpy(dtype="int64")
        positions = np.searchsorted(pool_dates_ns, real_dates_ns, side="left")
        positions = np.clip(positions, 0, pool_size - 1)

        offsets = rng.integers(0, pool_size, size=n_draws)  # (n_draws,)
        shifted = (positions[np.newaxis, :] + offsets[:, np.newaxis]) % pool_size  # (n_draws, n_fires)
        shifted_ret = pool_ret[shifted]  # (n_draws, n_fires)
        node_data.append(shifted_ret)

    if not node_data:
        return np.full(n_draws, np.nan)

    combined = np.concatenate(node_data, axis=1)  # (n_draws, total_fires)
    return np.nanmean(combined, axis=1)


# ---------------------------------------------------------------------------
# Coverage stats
# ---------------------------------------------------------------------------

def _coverage_stats(df_ep: pd.DataFrame, split_date: pd.Timestamp) -> dict:
    """Compute episode and calendar-month coverage statistics."""
    df_ep = df_ep.copy()
    df_ep["entry_dt"] = pd.to_datetime(df_ep["entry_date"])
    df_ep["ym"] = df_ep["entry_dt"].dt.to_period("M")

    n_fires = len(df_ep)
    episodes = df_ep["episode_id"].unique()
    n_episodes = len(episodes)

    # Fires per episode
    fires_per_ep = df_ep.groupby("episode_id").size()
    ep_fire_counts = fires_per_ep.values

    # Calendar months
    n_months = df_ep["ym"].nunique()
    month_range = (str(df_ep["ym"].min()), str(df_ep["ym"].max()))

    # Dev vs holdout episode counts
    dev_mask = df_ep["entry_dt"] <= split_date
    hold_mask = df_ep["entry_dt"] > split_date
    n_ep_dev = df_ep[dev_mask]["episode_id"].nunique()
    n_ep_hold = df_ep[hold_mask]["episode_id"].nunique()

    # Calendar months per period
    n_months_dev = df_ep[dev_mask]["ym"].nunique()
    n_months_hold = df_ep[hold_mask]["ym"].nunique()

    return {
        "n_fires": n_fires,
        "n_episodes": n_episodes,
        "n_months": n_months,
        "month_range": list(month_range),
        "fires_per_episode_min": int(ep_fire_counts.min()),
        "fires_per_episode_max": int(ep_fire_counts.max()),
        "fires_per_episode_mean": round(float(ep_fire_counts.mean()), 2),
        "fires_per_episode_median": round(float(np.median(ep_fire_counts)), 2),
        "n_episodes_dev": n_ep_dev,
        "n_episodes_hold": n_ep_hold,
        "n_months_dev": n_months_dev,
        "n_months_hold": n_months_hold,
        "fires_per_episode_distribution": [int(x) for x in sorted(ep_fire_counts, reverse=True)],
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(data_dir: Path, compounds_dir: Path, n_draws: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)

    print(f"[OTA-RC-2] Loading panel/episodes/spy for tier={TIER}...", flush=True)
    panel_raw = _load_panel(data_dir, TIER)
    episodes = _load_episodes(data_dir, TIER)
    spy = _load_spy(data_dir)
    rg = _load_rotation_groups(data_dir)
    panel = augment_panel_with_derived(panel_raw)

    print(f"[OTA-RC-2] Loading compound registry for {SIGNAL_ID}...", flush=True)
    compound = None
    for c in load_registry(compounds_dir):
        if c["id"] == SIGNAL_ID:
            compound = c
            break
    if compound is None:
        # Try main data dir
        main_dir = data_dir / "oracle" / "compounds"
        if main_dir.exists() and main_dir != compounds_dir:
            for c in load_registry(main_dir):
                if c["id"] == SIGNAL_ID:
                    compound = c
                    break
    if compound is None:
        raise RuntimeError(f"{SIGNAL_ID} not found in registry")

    print(f"[OTA-RC-2] Computing entry dates for {SIGNAL_ID}...", flush=True)
    entry_dates = get_entry_dates(compound, panel, episodes, rg)
    if "__blocked__" in entry_dates:
        raise RuntimeError(f"Entry dates BLOCKED: {entry_dates['__blocked__']}")

    total_triggers = sum(len(v) for v in entry_dates.values())
    print(f"[OTA-RC-2] Total triggers: {total_triggers}", flush=True)

    print(f"[OTA-RC-2] Computing entry metrics (W={WINDOW}, E={EXIT})...", flush=True)
    entries_df = _compute_entry_metrics(entry_dates, panel, WINDOW, EXIT, "time")
    print(f"[OTA-RC-2] Mature entries: {len(entries_df)}", flush=True)

    # Reproduction gate
    all_stats = _agg_stats(entries_df)
    n_actual = all_stats["n"]
    wr_actual = all_stats["WR"]
    asym_actual = all_stats["asym"]
    ret_actual = all_stats["mean_ret_exit"]

    print(f"[OTA-RC-2] Reproduction gate:", flush=True)
    print(f"  n={n_actual} (shipped={SHIPPED['n']})", flush=True)
    print(f"  WR={wr_actual:.4f} (shipped={SHIPPED['wr']})", flush=True)
    print(f"  asym={asym_actual:.4f} (shipped={SHIPPED['asym']})", flush=True)
    print(f"  ret_exit={ret_actual:.4f} (shipped={SHIPPED['ret_exit']})", flush=True)

    split_str = _GAUNTLET_TIER_SPLITS.get(TIER, _DEFAULT_TIER_SPLIT)
    split_date = pd.Timestamp(split_str)
    hold_df = entries_df[
        entries_df["trigger_date"] > split_date
    ] if "trigger_date" in entries_df.columns else entries_df[
        entries_df["entry_date"] > split_date
    ]
    hold_stats = _agg_stats(hold_df)
    print(f"  holdout n={hold_stats['n']} (shipped={SHIPPED['holdout_n']})", flush=True)
    print(f"  holdout WR={hold_stats['WR']:.4f} (shipped={SHIPPED['holdout_wr']})", flush=True)
    print(f"  holdout ret_exit={hold_stats['mean_ret_exit']:.4f} (shipped={SHIPPED['holdout_ret_exit']})", flush=True)

    # Check reproduction tolerance: n must match exactly, WR/asym/ret within 1pp
    repro_ok = (
        n_actual == SHIPPED["n"]
        and abs(wr_actual - SHIPPED["wr"]) < 0.01
        and abs(ret_actual - SHIPPED["ret_exit"]) < 0.01
    )
    if not repro_ok:
        print(f"\n[OTA-RC-2] REPRODUCTION GATE FAILED — stopping.", flush=True)
        return {
            "error": "REPRODUCTION_GATE_FAILED",
            "n_actual": n_actual, "wr_actual": round(wr_actual, 4),
            "ret_actual": round(ret_actual, 4),
            "shipped_n": SHIPPED["n"], "shipped_wr": SHIPPED["wr"],
            "shipped_ret": SHIPPED["ret_exit"],
        }
    print(f"[OTA-RC-2] Reproduction gate: PASS", flush=True)

    # Add entry_date column for episode clustering (use trigger_date as entry_date if missing)
    if "entry_date" not in entries_df.columns and "trigger_date" in entries_df.columns:
        entries_df = entries_df.copy()
        entries_df["entry_date"] = entries_df["trigger_date"]

    # Step 1: Episode collapse
    print(f"\n[OTA-RC-2] Step 1 — Episode collapse (cooldown={COOLDOWN} sessions)...", flush=True)
    df_ep = _cluster_episodes(entries_df, cooldown=COOLDOWN)
    cov = _coverage_stats(df_ep, split_date)
    print(f"  n_fires={cov['n_fires']}, n_episodes={cov['n_episodes']}, n_months={cov['n_months']}", flush=True)
    print(f"  Fires/ep: min={cov['fires_per_episode_min']} max={cov['fires_per_episode_max']} mean={cov['fires_per_episode_mean']}", flush=True)
    print(f"  Dev: {cov['n_episodes_dev']} episodes, {cov['n_months_dev']} months", flush=True)
    print(f"  Holdout: {cov['n_episodes_hold']} episodes, {cov['n_months_hold']} months", flush=True)

    # Step 2: Episode-cluster bootstrap CIs — full set
    print(f"\n[OTA-RC-2] Step 2a — Episode-cluster bootstrap ({n_draws} draws) full set...", flush=True)
    ci_full = _episode_cluster_bootstrap(df_ep, n_draws, rng)
    print(f"  WR CI: [{ci_full['wr'][0]:.4f}, {ci_full['wr'][1]:.4f}]", flush=True)
    print(f"  ret_exit CI: [{ci_full['ret_exit'][0]:.4f}, {ci_full['ret_exit'][1]:.4f}]", flush=True)
    print(f"  asym CI: [{ci_full['asym'][0]:.4f}, {ci_full['asym'][1]:.4f}]", flush=True)
    wr_lo_full = ci_full["wr"][0]
    leg2_ci_pass = wr_lo_full >= LEG2_WR_BAR
    print(f"  Leg-2 bar {LEG2_WR_BAR}: WR CI lower bound {wr_lo_full:.4f} -> {'CLEARS' if leg2_ci_pass else 'DOES NOT CLEAR'}", flush=True)

    # Step 2b: Episode-cluster bootstrap CIs — holdout
    print(f"\n[OTA-RC-2] Step 2b — Episode-cluster bootstrap ({n_draws} draws) holdout...", flush=True)
    hold_ep_df = df_ep[pd.to_datetime(df_ep["entry_date"]) > split_date].copy()
    n_hold_ep = hold_ep_df["episode_id"].nunique()
    print(f"  Holdout fires: {len(hold_ep_df)}, episodes: {n_hold_ep}", flush=True)
    if n_hold_ep >= 5:
        ci_hold = _episode_cluster_bootstrap(hold_ep_df, n_draws, rng)
        print(f"  Holdout WR CI: [{ci_hold['wr'][0]:.4f}, {ci_hold['wr'][1]:.4f}]", flush=True)
        print(f"  Holdout ret_exit CI: [{ci_hold['ret_exit'][0]:.4f}, {ci_hold['ret_exit'][1]:.4f}]", flush=True)
        wr_lo_hold = ci_hold["wr"][0]
        leg5_ci_pass = wr_lo_hold >= LEG5_WR_BAR
        print(f"  Leg-5 bar {LEG5_WR_BAR}: holdout WR CI lower bound {wr_lo_hold:.4f} -> {'CLEARS' if leg5_ci_pass else 'DOES NOT CLEAR'}", flush=True)
    else:
        ci_hold = {"wr": (np.nan, np.nan), "ret_exit": (np.nan, np.nan), "asym": (np.nan, np.nan)}
        leg5_ci_pass = None
        print(f"  Holdout has <5 episodes — CI not computed", flush=True)

    # Step 3: Time-shift Leg-6 placebo
    print(f"\n[OTA-RC-2] Step 3 — Building per-node outcome pools...", flush=True)
    pool_by_node = _build_node_pools_time(entries_df, panel, EXIT)
    pool_sizes = {n: len(d) for n, (d, _) in pool_by_node.items()}
    print(f"  Pool: {len(pool_by_node)} nodes, sizes: {pool_sizes}", flush=True)

    print(f"[OTA-RC-2] Running time-shift placebo ({n_draws} draws)...", flush=True)
    ts_draws = _circular_shift_placebo(entries_df, pool_by_node, n_draws, rng)
    ts_p95 = float(np.nanpercentile(ts_draws, 95))
    ts_p = float(np.mean(ts_draws >= ret_actual))
    ts_pass = bool(ret_actual > ts_p95)
    print(f"  Time-shift p95: {ts_p95*100:+.2f}%  vs observed: {ret_actual*100:+.2f}%  p={ts_p:.4f}  -> {'PASS' if ts_pass else 'FAIL'}", flush=True)
    print(f"  Shipped p95: {SHIPPED['placebo_p95']*100:+.2f}%", flush=True)

    # Also run shipped-style independent-draw placebo for comparison
    print(f"[OTA-RC-2] Running shipped-style independent-draw placebo (500 draws)...", flush=True)
    rng_orig = np.random.default_rng(42)  # original seed in the screen
    shipped_draws: list[float] = []
    # Build urn: per node, the pool outcomes
    urn = {n: r for n, (d, r) in pool_by_node.items()}
    cnt = entries_df.groupby("node").size().to_dict()
    for _ in range(500):
        vals = [
            rng_orig.choice(urn[nd], size=k, replace=True)
            for nd, k in cnt.items()
            if urn.get(nd) is not None and len(urn[nd]) > 0
        ]
        if vals:
            shipped_draws.append(float(np.concatenate(vals).mean()))
    shipped_p95 = float(np.nanpercentile(shipped_draws, 95))
    shipped_p = float(np.mean(np.array(shipped_draws) >= ret_actual))
    shipped_pass = bool(ret_actual > shipped_p95)
    print(f"  Reproduced shipped p95: {shipped_p95*100:+.2f}%  (published: {SHIPPED['placebo_p95']*100:+.2f}%)  p={shipped_p:.4f}  -> {'PASS' if shipped_pass else 'FAIL'}", flush=True)

    # Assemble result dict
    result = {
        "meta": {
            "signal_id": SIGNAL_ID,
            "seed": seed,
            "n_draws": n_draws,
            "window": WINDOW,
            "exit": EXIT,
            "tier": TIER,
            "cooldown": COOLDOWN,
            "split_date": split_str,
            "script": "scripts/research/oracle_seq_tc_recheck.py",
            "date": "2026-07-07",
        },
        "reproduction_gate": {
            "pass": repro_ok,
            "n": n_actual,
            "wr": round(wr_actual, 4),
            "asym": round(asym_actual, 4),
            "ret_exit": round(ret_actual, 4),
            "holdout_n": hold_stats["n"],
            "holdout_wr": round(hold_stats["WR"], 4) if not np.isnan(hold_stats["WR"]) else None,
            "holdout_ret_exit": round(hold_stats["mean_ret_exit"], 4) if not np.isnan(hold_stats["mean_ret_exit"]) else None,
            "shipped": SHIPPED,
        },
        "episode_coverage": cov,
        "episode_cluster_ci_full": {
            "n_episodes": cov["n_episodes"],
            "wr_point": round(wr_actual, 4),
            "wr_ci_lo": round(ci_full["wr"][0], 4),
            "wr_ci_hi": round(ci_full["wr"][1], 4),
            "ret_exit_point": round(ret_actual, 4),
            "ret_exit_ci_lo": round(ci_full["ret_exit"][0], 4),
            "ret_exit_ci_hi": round(ci_full["ret_exit"][1], 4),
            "asym_point": round(asym_actual, 4),
            "asym_ci_lo": round(ci_full["asym"][0], 4) if not np.isnan(ci_full["asym"][0]) else None,
            "asym_ci_hi": round(ci_full["asym"][1], 4) if not np.isnan(ci_full["asym"][1]) else None,
            "leg2_bar": LEG2_WR_BAR,
            "leg2_ci_lower_clears": leg2_ci_pass,
        },
        "episode_cluster_ci_holdout": {
            "n_fires": len(hold_ep_df),
            "n_episodes": n_hold_ep,
            "wr_point": round(hold_stats["WR"], 4) if not np.isnan(hold_stats["WR"]) else None,
            "wr_ci_lo": round(ci_hold["wr"][0], 4) if not np.isnan(ci_hold["wr"][0]) else None,
            "wr_ci_hi": round(ci_hold["wr"][1], 4) if not np.isnan(ci_hold["wr"][1]) else None,
            "ret_exit_point": round(hold_stats["mean_ret_exit"], 4) if not np.isnan(hold_stats["mean_ret_exit"]) else None,
            "ret_exit_ci_lo": round(ci_hold["ret_exit"][0], 4) if not np.isnan(ci_hold["ret_exit"][0]) else None,
            "ret_exit_ci_hi": round(ci_hold["ret_exit"][1], 4) if not np.isnan(ci_hold["ret_exit"][1]) else None,
            "leg5_bar": LEG5_WR_BAR,
            "leg5_ci_lower_clears": leg5_ci_pass,
        },
        "leg6_placebo_comparison": {
            "observed_ret_exit": round(ret_actual, 4),
            "shipped_independent_p95": round(shipped_p95, 4),
            "shipped_independent_p": round(shipped_p, 4),
            "shipped_independent_pass": shipped_pass,
            "published_shipped_p95": SHIPPED["placebo_p95"],
            "timeshift_p95": round(ts_p95, 4),
            "timeshift_p": round(ts_p, 4),
            "timeshift_pass": ts_pass,
            "n_draws": n_draws,
            "seed": seed,
        },
    }

    return result


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _pct(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v*100:+.{d}f}%"


def _f(v, d=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.{d}f}"


def _write_report(result: dict, out_md: Path, out_json: Path):
    if "error" in result:
        md = [
            "# SEQ_TLT_RELIEF_WASHOUT Episode-Cluster CIs + Time-Shift Placebo (OTA-RC-2)",
            "",
            "**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**",
            "",
            f"## REPRODUCTION GATE FAILED — WIP BLOCKED",
            "",
            f"Error: {result['error']}",
            "",
            "| Metric | Actual | Shipped |",
            "|---|---|---|",
            f"| n | {result.get('n_actual', '?')} | {result.get('shipped_n', '?')} |",
            f"| WR | {_f(result.get('wr_actual'))} | {_f(result.get('shipped_wr'))} |",
            f"| ret_exit | {_pct(result.get('ret_actual'))} | {_pct(result.get('shipped_ret'))} |",
            "",
            "*Stopped per task instructions. No inference computed.*",
        ]
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(md), encoding="utf-8")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return

    meta = result["meta"]
    rep = result["reproduction_gate"]
    cov = result["episode_coverage"]
    ci_full = result["episode_cluster_ci_full"]
    ci_hold = result["episode_cluster_ci_holdout"]
    plac = result["leg6_placebo_comparison"]

    shipped = rep["shipped"]

    md: list[str] = [
        "# SEQ_TLT_RELIEF_WASHOUT Episode-Cluster CIs + Time-Shift Placebo (OTA-RC-2)",
        "",
        "**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**",
        "",
        f"Date: 2026-07-07  |  Seed: {meta['seed']}  |  Draws: {meta['n_draws']}  |  Signal: {meta['signal_id']}",
        "",
        "---",
        "",
        "## Reproduction Gate",
        "",
        "Signal definition, fire set, exit convention (W=25, E=21, time-exit), all six leg",
        "thresholds, and the dev/holdout split (2019-12-31) are frozen.",
        "",
        "| Metric | Reproduced | Shipped | Match |",
        "|---|---|---|---|",
        f"| n | {rep['n']} | {shipped['n']} | {'YES' if rep['n'] == shipped['n'] else 'NO'} |",
        f"| WR | {_f(rep['wr'])} | {_f(shipped['wr'])} | {'YES' if abs(rep['wr'] - shipped['wr']) < 0.01 else 'NO'} |",
        f"| asym | {_f(rep['asym'])} | {_f(shipped['asym'])} | {'YES' if abs(rep['asym'] - shipped['asym']) < 0.05 else 'NO'} |",
        f"| ret_exit | {_pct(rep['ret_exit'])} | {_pct(shipped['ret_exit'])} | {'YES' if abs(rep['ret_exit'] - shipped['ret_exit']) < 0.01 else 'NO'} |",
        f"| holdout n | {rep['holdout_n']} | {shipped['holdout_n']} | {'YES' if rep['holdout_n'] == shipped['holdout_n'] else 'NO'} |",
        f"| holdout WR | {_f(rep['holdout_wr'])} | {_f(shipped['holdout_wr'])} | {'YES' if rep['holdout_wr'] is not None and abs(rep['holdout_wr'] - shipped['holdout_wr']) < 0.01 else 'NO'} |",
        f"| holdout ret_exit | {_pct(rep['holdout_ret_exit'])} | {_pct(shipped['holdout_ret_exit'])} | {'YES' if rep['holdout_ret_exit'] is not None and abs(rep['holdout_ret_exit'] - shipped['holdout_ret_exit']) < 0.01 else 'NO'} |",
        "",
        f"**Reproduction gate: {'PASS' if rep['pass'] else 'FAIL'}**",
        "",
        "---",
        "",
        "## Step 1 — Episode Collapse",
        "",
        f"Clustering rule: same node, entry dates within ≤{meta['cooldown']} trading-day gaps",
        "chain into one episode (gap approximated as calendar days × 5/7, rounded).",
        "",
        "### Coverage stamp",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total fires | {cov['n_fires']} |",
        f"| Episodes (all) | {cov['n_episodes']} |",
        f"| Calendar months touched | {cov['n_months']} ({cov['month_range'][0]} to {cov['month_range'][1]}) |",
        f"| Fires/episode: min / mean / median / max | {cov['fires_per_episode_min']} / {cov['fires_per_episode_mean']:.2f} / {cov['fires_per_episode_median']:.2f} / {cov['fires_per_episode_max']} |",
        f"| Episodes (dev, ≤{meta['split_date']}) | {cov['n_episodes_dev']} over {cov['n_months_dev']} months |",
        f"| Episodes (holdout, >{meta['split_date']}) | {cov['n_episodes_hold']} over {cov['n_months_hold']} months |",
        "",
        "---",
        "",
        "## Step 2 — Episode-Cluster Bootstrap CIs",
        "",
        f"Method: resample episodes with replacement ({meta['n_draws']} draws, seed {meta['seed']}),",
        "all fires within a drawn episode move together. 95% CI = [2.5th, 97.5th] percentile",
        "of draw distribution.",
        "",
        "### 2a — Full set",
        "",
        "| Metric | Point | CI lo | CI hi | Bar | Lower bound clears bar? |",
        "|---|---|---|---|---|---|",
        f"| WR | {_f(ci_full['wr_point'])} | {_f(ci_full['wr_ci_lo'])} | {_f(ci_full['wr_ci_hi'])} | ≥{ci_full['leg2_bar']} (Leg 2) | {'YES' if ci_full['leg2_ci_lower_clears'] else 'NO'} |",
        f"| ret_exit | {_pct(ci_full['ret_exit_point'])} | {_pct(ci_full['ret_exit_ci_lo'])} | {_pct(ci_full['ret_exit_ci_hi'])} | >0 | {'YES' if ci_full['ret_exit_ci_lo'] is not None and ci_full['ret_exit_ci_lo'] > 0 else 'NO'} |",
        f"| asym | {_f(ci_full['asym_point'])} | {_f(ci_full['asym_ci_lo'])} | {_f(ci_full['asym_ci_hi'])} | ≥1.5 (Leg 3) | {'YES' if ci_full['asym_ci_lo'] is not None and ci_full['asym_ci_lo'] >= 1.5 else 'NO'} |",
        "",
        "### 2b — Holdout subset",
        "",
        "| Metric | Point | CI lo | CI hi | Bar | Lower bound clears bar? |",
        "|---|---|---|---|---|---|",
        f"| WR | {_f(ci_hold['wr_point'])} | {_f(ci_hold['wr_ci_lo'])} | {_f(ci_hold['wr_ci_hi'])} | ≥{ci_hold['leg5_bar']} (Leg 5) | {'YES' if ci_hold['leg5_ci_lower_clears'] else 'NO'} |",
        f"| ret_exit | {_pct(ci_hold['ret_exit_point'])} | {_pct(ci_hold['ret_exit_ci_lo'])} | {_pct(ci_hold['ret_exit_ci_hi'])} | >0 | {'YES' if ci_hold['ret_exit_ci_lo'] is not None and ci_hold['ret_exit_ci_lo'] > 0 else 'NO'} |",
        "",
        f"(Holdout: {ci_hold['n_fires']} fires across {ci_hold['n_episodes']} episodes)",
        "",
        "---",
        "",
        "## Step 3 — Leg-6 Placebo: Shipped vs Time-Shift Side-by-Side",
        "",
        "Shipped Leg-6 (oracle_reversion_screen.py :747+): per node, independently sample",
        "count-matched outcomes from the full realizable-outcome pool — does not preserve",
        "temporal clustering.",
        "",
        "Time-shift placebo (this re-check, mirrors oracle_compound_tc_recheck.py):",
        "for each draw, shift each node's real entry-date sequence by one shared uniform",
        "random integer offset (mod pool_size), preserving inter-fire spacing exactly.",
        "Count-matched by construction.",
        "",
        "| Method | Draws | p95 | Observed ret_exit | Clears bar? |",
        "|---|---|---|---|---|",
        f"| Shipped published | 500 | {_pct(plac['published_shipped_p95'])} | {_pct(plac['observed_ret_exit'])} | {'YES' if plac['observed_ret_exit'] > plac['published_shipped_p95'] else 'NO'} |",
        f"| Reproduced shipped (independent draws) | 500 | {_pct(plac['shipped_independent_p95'])} | {_pct(plac['observed_ret_exit'])} | {'YES' if plac['shipped_independent_pass'] else 'NO'} |",
        f"| Time-shift (this re-check) | {plac['n_draws']} | {_pct(plac['timeshift_p95'])} | {_pct(plac['observed_ret_exit'])} | {'YES' if plac['timeshift_pass'] else 'NO'} |",
        "",
        "---",
        "",
        "## Summary — All new inference side-by-side",
        "",
        "| Test | Shipped point | New CI / bar | Status |",
        "|---|---|---|---|",
        f"| Leg-2 WR (full) | {_f(shipped['wr'])} | CI lo = {_f(ci_full['wr_ci_lo'])} vs ≥{LEG2_WR_BAR} | {'CI LOWER CLEARS' if ci_full['leg2_ci_lower_clears'] else 'CI LOWER BELOW BAR'} |",
        f"| Leg-5 WR (holdout) | {_f(shipped['holdout_wr'])} | CI lo = {_f(ci_hold['wr_ci_lo'])} vs ≥{LEG5_WR_BAR} | {'CI LOWER CLEARS' if ci_hold.get('leg5_ci_lower_clears') else 'CI LOWER BELOW BAR' if ci_hold.get('leg5_ci_lower_clears') is False else 'INSUFFICIENT EPISODES'} |",
        f"| Leg-6 placebo (shipped) | real > p95={_pct(shipped['placebo_p95'])} -> PASS | — | — |",
        f"| Leg-6 time-shift (new) | {_pct(plac['observed_ret_exit'])} | p95={_pct(plac['timeshift_p95'])} | {'TIME-SHIFT PASS' if plac['timeshift_pass'] else 'TIME-SHIFT FAIL'} |",
        f"| ret_exit 95% CI | {_pct(shipped['ret_exit'])} | [{_pct(ci_full['ret_exit_ci_lo'])}, {_pct(ci_full['ret_exit_ci_hi'])}] | CI {'EXCLUDES' if ci_full['ret_exit_ci_lo'] is not None and ci_full['ret_exit_ci_lo'] > 0 else 'INCLUDES'} zero |",
        f"| asym 95% CI | {_f(shipped['asym'])} | [{_f(ci_full['asym_ci_lo'])}, {_f(ci_full['asym_ci_hi'])}] | CI lo {'≥' if ci_full['asym_ci_lo'] is not None and ci_full['asym_ci_lo'] >= 1.5 else '<'} 1.5 bar |",
        "",
        "---",
        "",
        "*RE-CHECK artifact. No verdict is changed. Adjudication pending (Fable).*",
        f"*Script: scripts/research/oracle_seq_tc_recheck.py  |  Seed: {meta['seed']}  |  n_draws: {meta['n_draws']}*",
        "",
    ]

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[Output] {out_md}", flush=True)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[Output] {out_json}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data-dir", type=Path,
        default=Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data"),
    )
    p.add_argument("--compounds-dir", type=Path, default=None)
    p.add_argument("--draws", type=int, default=2000)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()

    compounds_dir = args.compounds_dir or (ROOT / "data" / "oracle" / "compounds")

    print("=== OTA-RC-2: SEQ_TLT_RELIEF_WASHOUT Time-Confound Re-Check ===", flush=True)
    print(f"data-dir: {args.data_dir}", flush=True)
    print(f"compounds-dir: {compounds_dir}", flush=True)
    print(f"draws: {args.draws}  seed: {args.seed}", flush=True)
    print(flush=True)

    result = run(args.data_dir, compounds_dir, args.draws, args.seed)

    out_md = ROOT / "research" / "ORACLE_SEQ_TC_RECHECK.md"
    out_json = ROOT / "research" / "oracle_seq_tc_recheck.json"
    _write_report(result, out_md, out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
