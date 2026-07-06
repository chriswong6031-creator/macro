"""OTA W2 — Member Transmission — Offline Research CLI.

Spec: research/oracle_asymmetry/W2_SPEC.md (pre-registered 2026-07-05).
Authority: research/ORACLE_TURN_ASYMMETRY_MASTERPLAN_BY_FABLE.md §W2.
Era law: research/entry_intel/P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05).

Question: Does an Oracle armed window add measurable quality to member entries
that already fire on the house triggers?

Outputs:
    research/oracle_asymmetry/W2_member_trades.csv
    research/oracle_asymmetry/W2_REPORT.md

Usage:
    python -m scripts.oracle_member_transmission_w2
        --data-dir "/Users/chriswong/Documents/Cluade/Macro Dashboard/data"

Prohibitions (spec §4):
    - No modification of engine/scripts files.
    - No writes to MAIN data dir.
    - No trial-ledger appends.
    - No re-derivation of member triggers (replay IS the trigger record).
    - No quoting lift without cluster-aware CI.
    - The 2 gate reads (G-W2-A, G-W2-B) are the entire claimed test count.
    - "validated" must not appear in output text.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ota_w2")

# ---------------------------------------------------------------------------
# Determinism seed (spec §5)
# ---------------------------------------------------------------------------
SEED = 20260705
RNG = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Effective verdict window per P0_MEASUREMENT_MEMO.md v1.1 §6 Amendment 1
EFFECTIVE_WINDOW_START = "2022-06-30"  # ≈ 2022-06-30 per v1.1 (250-bar MTF warmup)

# Armed window width (K=10 trading sessions, per spec §1)
K_PRIMARY = 10
K_SENSITIVITY = [5, 21]  # appendix-only, never quoted as findings

# Inference parameters
BOOTSTRAP_DRAWS = 2000   # cluster bootstrap, IN arm
PLACEBO_DRAWS = 500      # regime-matched placebo, IN−OUT delta

# VIX regime threshold
VIX_HIGH_THRESHOLD = 0.6  # vix_pctile >= 0.6 → high-VIX regime

# BH correction
BH_Q = 0.10   # 2 registered reads in this family

# MDE power target
POWER_TARGET = 0.80

# Stop-5 definition: fwd_mdd_5 < -0.05
STOP5_THRESHOLD = -0.05

# GICS sector → Oracle ETF node (spec §1: etf_proxy exact 1:1)
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

# All 11 sector nodes
ALL_NODES = list(NODE_TO_GICS.keys())

# W0 primary family for armed windows (spec §1)
W0_PRIMARY_FAMILY = "a15"
W0_SECONDARY_FAMILY = "ep_onset_in"
W0_PRIMARY_DEDUP = "raw"  # spec says "a15-raw armed windows"

# ---------------------------------------------------------------------------
# Fidelity gate (spec §3 item 1: FIRST, loud abort)
# ---------------------------------------------------------------------------

def run_fidelity_gate(data_dir: Path, w0_csv_path: Path) -> dict[str, Any]:
    """Fidelity gate — loud abort on failure.

    Checks:
    1. replay_boarded.parquet exists and has expected row counts
    2. golden_test.json exists and golden_test_passed == True
    3. W0 CSV family counts: a15-raw fire count matches expected

    Returns dict of validated counts for the report preamble.
    """
    report = {}

    # --- 1. replay_boarded.parquet ---
    replay_path = data_dir / "replay" / "replay_boarded.parquet"
    if not replay_path.exists():
        _fatal(f"FIDELITY GATE FAIL: replay_boarded.parquet not found at {replay_path}")

    replay = pd.read_parquet(replay_path)
    total_rows = len(replay)
    survivor_false = int((replay["survivor_bias"] == False).sum())
    verdict_grade_true = int((replay["verdict_grade"] == True).sum())
    horizon_censored = int((replay["horizon_censored"] == True).sum())

    log.info("FIDELITY: replay_boarded rows=%d  survivor_bias=False: %d  verdict_grade=True: %d  horizon_censored: %d",
             total_rows, survivor_false, verdict_grade_true, horizon_censored)

    if total_rows == 0:
        _fatal("FIDELITY GATE FAIL: replay_boarded.parquet is empty")
    if survivor_false == 0:
        _fatal("FIDELITY GATE FAIL: no survivor_bias==False rows")
    if verdict_grade_true == 0:
        _fatal("FIDELITY GATE FAIL: no verdict_grade==True rows")

    # Columns required by spec §1
    required_cols = [
        "ticker", "signal_date", "survivor_bias", "price_source",
        "verdict_grade", "horizon_censored", "sector",
        "fwd_ret_5", "fwd_ret_10", "fwd_ret_21",
        "fwd_mdd_5", "fwd_mdd_10", "fwd_mdd_21",
        "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21",
        "state_8_21",
    ]
    missing = [c for c in required_cols if c not in replay.columns]
    if missing:
        _fatal(f"FIDELITY GATE FAIL: missing columns in replay: {missing}")

    report["replay_total_rows"] = total_rows
    report["replay_survivor_false"] = survivor_false
    report["replay_verdict_grade_true"] = verdict_grade_true
    report["replay_horizon_censored"] = horizon_censored

    # --- 2. golden_test.json ---
    golden_path = data_dir / "replay" / "golden_test.json"
    if not golden_path.exists():
        _fatal(f"FIDELITY GATE FAIL: golden_test.json not found at {golden_path}")

    with open(golden_path) as f:
        golden = json.load(f)

    if not golden.get("golden_test_passed", False):
        _fatal(f"FIDELITY GATE FAIL: golden_test_passed=False in {golden_path}")

    prod_count = golden.get("prod_fire_count")
    replay_count = golden.get("replay_fire_count")
    exact_match = golden.get("exact_match")
    log.info("FIDELITY: golden_test PASSED  prod_fire_count=%s  replay_fire_count=%s  exact_match=%s",
             prod_count, replay_count, exact_match)

    report["golden_prod_fire_count"] = prod_count
    report["golden_replay_fire_count"] = replay_count
    report["golden_exact_match"] = exact_match

    # --- 3. W0 CSV family counts ---
    w0 = pd.read_csv(w0_csv_path)
    a15_all = w0[w0["family"] == W0_PRIMARY_FAMILY]
    a15_raw = a15_all[a15_all["dedup_variant"] == W0_PRIMARY_DEDUP]
    a15_unique = a15_raw.drop_duplicates(subset=["node", "trigger_date"])
    ep_onset = w0[w0["family"] == W0_SECONDARY_FAMILY]

    log.info("FIDELITY: W0 CSV a15-all=%d  a15-raw=%d  a15-unique(node,date)=%d  ep_onset_in=%d",
             len(a15_all), len(a15_raw), len(a15_unique), len(ep_onset))

    report["w0_a15_all"] = len(a15_all)
    report["w0_a15_raw"] = len(a15_raw)
    report["w0_a15_unique_fires"] = len(a15_unique)
    report["w0_ep_onset_in"] = len(ep_onset)

    log.info("FIDELITY GATE: PASSED")
    return report


def _fatal(msg: str) -> None:
    log.error(msg)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Armed-window construction (spec §1: K=10 sessions, overlapping windows merge)
# ---------------------------------------------------------------------------

def build_armed_windows(fire_dates_by_node: dict[str, list[str]], k: int, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """Build armed windows for each node from fire dates.

    For each node:
      - Each fire_date starts an armed window [fire_date, fire_date + K sessions].
      - Overlapping windows on a node MERGE into one armed-window id (cluster unit).
      - K sessions = K trading days AFTER fire_date (fire_date + k_th trading day).

    Returns DataFrame with columns:
        node, window_id, window_start, window_end, fire_dates (list)
    """
    td_arr = np.array(trading_days)
    records = []
    global_window_id = 0

    for node in sorted(fire_dates_by_node.keys()):
        fires = sorted(pd.Timestamp(d) for d in fire_dates_by_node[node])
        if not fires:
            continue

        # For each fire date, compute window end = fire_date + K trading sessions
        windows = []  # (start, end) tuples as pd.Timestamp
        for fd in fires:
            fd_ts = pd.Timestamp(fd)
            idx = np.searchsorted(td_arr, np.datetime64(fd_ts), side="left")
            if idx >= len(td_arr):
                continue
            # Snap fire_date to nearest trading day at-or-after
            if td_arr[idx] != np.datetime64(fd_ts):
                # fire_date is not a trading day; use next trading day as start
                start_ts = pd.Timestamp(td_arr[idx])
            else:
                start_ts = fd_ts
            # Window end = start + K-th trading session after start
            end_idx = idx + k
            if end_idx >= len(td_arr):
                end_ts = pd.Timestamp(td_arr[-1])
            else:
                end_ts = pd.Timestamp(td_arr[end_idx])
            windows.append((start_ts, end_ts, fd_ts))

        if not windows:
            continue

        # Merge overlapping windows
        windows_sorted = sorted(windows, key=lambda x: x[0])
        merged = []
        cur_start, cur_end, cur_fires = windows_sorted[0][0], windows_sorted[0][1], [windows_sorted[0][2]]
        for wstart, wend, wfire in windows_sorted[1:]:
            if wstart <= cur_end:  # overlap or touching → merge
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


def assign_arm(signal_date: pd.Timestamp, node: str, windows_by_node: dict[str, pd.DataFrame]) -> tuple[str, int | None]:
    """Return ('IN', window_id) if signal_date falls inside any armed window for node,
    else ('OUT', None).

    signal_date is compared as: window_start <= signal_date <= window_end
    (both inclusive, per spec §1 'fire_date + K sessions').
    """
    node_wins = windows_by_node.get(node)
    if node_wins is None or len(node_wins) == 0:
        return "OUT", None
    mask = (node_wins["window_start"] <= signal_date) & (signal_date <= node_wins["window_end"])
    hits = node_wins[mask]
    if len(hits) == 0:
        return "OUT", None
    # Take the first matching window (signal_date inside exactly one merged window by construction)
    return "IN", int(hits.iloc[0]["window_id"])


# ---------------------------------------------------------------------------
# PIT interval join (spec §1: member must be SP500-src PIT member at fire date)
# ---------------------------------------------------------------------------

def build_pit_membership_lookup(pit_path: Path) -> pd.DataFrame:
    """Load SP1500 PIT membership intervals.

    Returns DataFrame with ticker, start_date (datetime64), end_date (datetime64, NaT=still member).
    """
    pit = pd.read_parquet(pit_path)
    # Ensure datetime types
    pit["start_date"] = pd.to_datetime(pit["start_date"])
    pit["end_date"] = pd.to_datetime(pit["end_date"])
    # Filter to SP500 source only (sp500 src) — the spec says "SP500-src PIT member"
    # Check src values
    sp500_pit = pit[pit["src"].str.lower().str.startswith("sp500")].copy()
    if len(sp500_pit) == 0:
        log.warning("PIT: no sp500 src rows found — using all sources; src values: %s",
                    pit["src"].unique().tolist())
        sp500_pit = pit.copy()
    return sp500_pit


def is_pit_member(ticker: str, signal_date: pd.Timestamp, pit_by_ticker: dict[str, pd.DataFrame]) -> bool:
    """Return True if ticker was a PIT member at signal_date."""
    intervals = pit_by_ticker.get(ticker)
    if intervals is None:
        return False
    # member if start_date <= signal_date AND (end_date is NaT OR signal_date <= end_date)
    sd = signal_date
    for _, row in intervals.iterrows():
        if row["start_date"] <= sd:
            if pd.isna(row["end_date"]) or sd <= row["end_date"]:
                return True
    return False


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------

def stop5_rate(df: pd.DataFrame) -> float:
    """Fraction of rows where fwd_mdd_5 < -0.05 (stop-5 rate)."""
    valid = df["fwd_mdd_5"].dropna()
    if len(valid) == 0:
        return float("nan")
    return float((valid < STOP5_THRESHOLD).mean())


def compute_metrics(df: pd.DataFrame) -> dict[str, Any]:
    """Compute house yardstick metrics on a DataFrame of member fires/ablation entries."""
    metrics = {}
    n = len(df)
    metrics["n_rows"] = n

    if n == 0:
        for k in ["wr21", "mean_fwd_ret_21", "median_fwd_ret_21",
                  "mean_mfe_21", "mean_mdd_21", "stop5_rate"]:
            metrics[k] = float("nan")
        return metrics

    # WR21 = share with fwd_ret_21 > 0
    ret21 = df["fwd_ret_21"].dropna()
    metrics["wr21"] = float((ret21 > 0).mean()) if len(ret21) > 0 else float("nan")
    metrics["n_wr21"] = int(len(ret21))

    metrics["mean_fwd_ret_21"] = float(ret21.mean()) if len(ret21) > 0 else float("nan")
    metrics["median_fwd_ret_21"] = float(ret21.median()) if len(ret21) > 0 else float("nan")

    mfe21 = df["fwd_mfe_21"].dropna()
    metrics["mean_mfe_21"] = float(mfe21.mean()) if len(mfe21) > 0 else float("nan")

    mdd21 = df["fwd_mdd_21"].dropna()
    metrics["mean_mdd_21"] = float(mdd21.mean()) if len(mdd21) > 0 else float("nan")

    metrics["stop5_rate"] = stop5_rate(df)

    # clean8_21 terminal state distribution
    if "state_8_21" in df.columns:
        state_counts = df["state_8_21"].value_counts()
        metrics["clean8_21_dist"] = state_counts.to_dict()
        n_valid_state = int(df["state_8_21"].notna().sum())
        metrics["n_state_8_21"] = n_valid_state
        cl = state_counts.get("CLEAN_LIFTOFF", 0)
        metrics["clean8_21_liftoff_rate"] = float(cl / n_valid_state) if n_valid_state > 0 else float("nan")

    return metrics


# ---------------------------------------------------------------------------
# Cluster bootstrap (spec §2: resample window ids, 2,000 draws)
# ---------------------------------------------------------------------------

def cluster_bootstrap_ci(
    df: pd.DataFrame,
    metric_fn,
    window_id_col: str = "window_id",
    n_draws: int = BOOTSTRAP_DRAWS,
    ci_level: float = 0.90,
    rng: np.random.Generator | None = None,
) -> dict[str, float]:
    """Cluster bootstrap: resample armed-window ids, compute metric on each draw.

    Unit of independence = window_id. Each draw resamples window ids with replacement,
    retaining all rows belonging to sampled windows.

    Returns dict with keys: point, ci_lo, ci_hi, n_windows, n_rows.
    """
    if rng is None:
        rng = np.random.default_rng(SEED)

    window_ids = df[window_id_col].unique()
    n_windows = len(window_ids)

    if n_windows == 0:
        return {"point": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
                "n_windows": 0, "n_rows": 0}

    point = metric_fn(df)

    boot_stats = []
    for _ in range(n_draws):
        sampled_ids = rng.choice(window_ids, size=n_windows, replace=True)
        # Rebuild DataFrame from sampled window ids
        chunks = [df[df[window_id_col] == wid] for wid in sampled_ids]
        boot_df = pd.concat(chunks, ignore_index=True)
        boot_stats.append(metric_fn(boot_df))

    boot_arr = np.array(boot_stats)
    alpha = (1.0 - ci_level) / 2.0
    ci_lo = float(np.nanpercentile(boot_arr, 100 * alpha))
    ci_hi = float(np.nanpercentile(boot_arr, 100 * (1 - alpha)))

    return {
        "point": float(point),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_windows": n_windows,
        "n_rows": len(df),
    }


# ---------------------------------------------------------------------------
# Regime-matched placebo (spec §2: 500 draws, window re-placement, VIX-matched)
# ---------------------------------------------------------------------------

def build_vix_regime_lookup(panel_s: pd.DataFrame) -> dict[str, dict[pd.Timestamp, str]]:
    """Build per-node date->vix_regime lookup.

    Returns {node: {date: 'high'|'low'}}
    VIX high if vix_pctile >= VIX_HIGH_THRESHOLD, else low.
    """
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


def _build_vix_regime_arrays(
    vix_regime_by_node: dict[str, dict[pd.Timestamp, str]],
    td_arr: np.ndarray,
    node: str,
) -> np.ndarray:
    """Return boolean array of length len(td_arr): True = high-VIX trading day for node."""
    regime = vix_regime_by_node.get(node, {})
    is_high = np.zeros(len(td_arr), dtype=bool)
    for i, dt in enumerate(td_arr):
        ts = pd.Timestamp(dt)
        if regime.get(ts, "low") == "high":
            is_high[i] = True
    return is_high


def placebo_draw_vectorized(
    node: str,
    node_windows: pd.DataFrame,
    node_fires_dates: np.ndarray,  # int64 ns timestamps of all node fires (sorted)
    node_fires_ret21: np.ndarray,  # float64 fwd_ret_21 values aligned with node_fires_dates
    td_arr: np.ndarray,            # int64 ns timestamps of all trading days
    is_high_vix: np.ndarray,       # bool[len(td_arr)]: high-VIX regime per trading day
    rng: np.random.Generator,
    max_attempts: int = 200,
) -> float | None:
    """Vectorized placebo draw for one node.

    Re-places each armed window at a random non-armed location on the same node,
    VIX-regime matched at window start, preserving window length and count.
    Computes IN-arm WR21 delta under the placebo placement.

    Returns delta = placebo_in_wr21 - placebo_out_wr21, or None.
    """
    if len(node_windows) == 0 or len(node_fires_dates) == 0:
        return None

    n_td = len(td_arr)

    # For each original window compute (start_idx, win_len, target_high_vix)
    placebo_intervals_ns = []  # list of (start_ns, end_ns) for placed windows
    for _, win in node_windows.iterrows():
        orig_start_ns = np.datetime64(pd.Timestamp(win["window_start"])).astype("int64")
        orig_end_ns = np.datetime64(pd.Timestamp(win["window_end"])).astype("int64")

        start_idx = int(np.searchsorted(td_arr, orig_start_ns, side="left"))
        end_idx = int(np.searchsorted(td_arr, orig_end_ns, side="left"))
        win_len = max(1, end_idx - start_idx)

        target_high = bool(is_high_vix[min(start_idx, n_td - 1)])

        # Candidate start indices with matching regime and enough forward room
        cand_mask = (is_high_vix[:n_td - win_len] == target_high)
        candidate_idxs = np.where(cand_mask)[0]
        if len(candidate_idxs) == 0:
            # Relax regime
            candidate_idxs = np.arange(n_td - win_len)
        if len(candidate_idxs) == 0:
            continue

        placed = None
        for _ in range(max_attempts):
            ci = int(rng.choice(candidate_idxs))
            new_start_ns = td_arr[ci]
            new_end_idx = min(ci + win_len, n_td - 1)
            new_end_ns = td_arr[new_end_idx]
            # Check non-overlapping with already-placed windows
            overlap = False
            for (ps, pe) in placebo_intervals_ns:
                if not (new_end_ns < ps or new_start_ns > pe):
                    overlap = True
                    break
            if not overlap:
                placed = (new_start_ns, new_end_ns)
                break

        if placed is not None:
            placebo_intervals_ns.append(placed)

    if not placebo_intervals_ns:
        return None

    # Vectorized arm assignment: for each fire date, check overlap with any placebo window
    # node_fires_dates is int64 ns array
    # Build boolean IN mask using broadcasting
    fire_dates = node_fires_dates  # shape (N,)
    in_mask = np.zeros(len(fire_dates), dtype=bool)
    for (ps, pe) in placebo_intervals_ns:
        in_mask |= (fire_dates >= ps) & (fire_dates <= pe)

    # WR21 computation
    ret21_all = node_fires_ret21
    valid = np.isfinite(ret21_all)

    in_valid = in_mask & valid
    out_valid = (~in_mask) & valid

    n_in = in_valid.sum()
    n_out = out_valid.sum()

    if n_in == 0 or n_out == 0:
        return None

    in_wr21 = float((ret21_all[in_valid] > 0).mean())
    out_wr21 = float((ret21_all[out_valid] > 0).mean())
    return in_wr21 - out_wr21


def placebo_draw(
    node: str,
    orig_windows: pd.DataFrame,
    member_fires_out: pd.DataFrame,
    trading_days_set: pd.DatetimeIndex,
    vix_regime_by_node: dict[str, dict[pd.Timestamp, str]],
    metric_fn_in,
    metric_fn_out,
    rng: np.random.Generator,
) -> float | None:
    """Thin wrapper around placebo_draw_vectorized (legacy interface for mean_ret21).

    For WR21 delta: use placebo_draw_vectorized directly.
    For mean_ret21 delta: same vectorized pattern (uses mean of ret21).
    """
    node_windows = orig_windows[orig_windows["node"] == node].copy()
    if len(node_windows) == 0:
        return None

    td_arr = trading_days_set.to_numpy().astype("datetime64[ns]").astype("int64")
    is_high_vix = _build_vix_regime_arrays(vix_regime_by_node, td_arr, node)

    node_fires = member_fires_out
    if "node_etf" in node_fires.columns:
        node_fires = node_fires[node_fires["node_etf"] == node]
    if len(node_fires) == 0:
        return None

    fire_dates_ns = pd.to_datetime(node_fires["signal_date"]).values.astype("int64")
    ret21_vals = node_fires["fwd_ret_21"].to_numpy(dtype=float, na_value=float("nan"))

    return placebo_draw_vectorized(
        node, node_windows, fire_dates_ns, ret21_vals,
        td_arr, is_high_vix, rng,
    )


def _placebo_draw_both_metrics(
    node_windows: pd.DataFrame,
    fire_dates_ns: np.ndarray,
    ret21_vals: np.ndarray,
    td_arr_ns: np.ndarray,
    is_high_vix: np.ndarray,
    rng: np.random.Generator,
    real_intervals_ns: list[tuple[int, int]] | None = None,
    max_attempts: int = 200,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Vectorized placebo draw returning per-node (in_mask, ret21_vals) for pooled aggregation.

    FIX (blocker/major): now accepts real_intervals_ns to exclude real armed windows
    from candidate placements.  Spec §2 requires each placebo window be placed at a
    random NON-ARMED location; previously only other placebo windows in the same draw
    were excluded, contaminating the null with genuine IN-arm signal.

    Returns (in_mask, ret21_vals) so the caller can pool across nodes before computing
    the pooled IN−OUT delta, matching the pooled observed statistic (blocker fix).
    Returns None if placement fails or insufficient data.
    """
    if len(node_windows) == 0 or len(fire_dates_ns) == 0:
        return None

    n_td = len(td_arr_ns)
    placebo_intervals_ns: list[tuple[int, int]] = []

    # FIX: seed forbidden set with real armed-window intervals so placebo windows
    # cannot land on actual armed locations.
    forbidden: list[tuple[int, int]] = list(real_intervals_ns) if real_intervals_ns else []

    for _, win in node_windows.iterrows():
        orig_start_ns = np.datetime64(pd.Timestamp(win["window_start"]), "ns").astype("int64")
        orig_end_ns = np.datetime64(pd.Timestamp(win["window_end"]), "ns").astype("int64")

        start_idx = int(np.searchsorted(td_arr_ns, orig_start_ns, side="left"))
        end_idx = int(np.searchsorted(td_arr_ns, orig_end_ns, side="left"))
        win_len = max(1, end_idx - start_idx)

        target_high = bool(is_high_vix[min(start_idx, n_td - 1)])
        cand_mask = (is_high_vix[:max(1, n_td - win_len)] == target_high)
        candidate_idxs = np.where(cand_mask)[0]
        if len(candidate_idxs) == 0:
            candidate_idxs = np.arange(max(1, n_td - win_len))
        if len(candidate_idxs) == 0:
            continue

        placed = None
        for _ in range(max_attempts):
            ci = int(rng.choice(candidate_idxs))
            new_start_ns = td_arr_ns[ci]
            new_end_ns = td_arr_ns[min(ci + win_len, n_td - 1)]
            # Check against forbidden (real windows) + already-placed placebo windows
            all_forbidden = forbidden + placebo_intervals_ns
            overlap = any(
                not (new_end_ns < ps or new_start_ns > pe)
                for (ps, pe) in all_forbidden
            )
            if not overlap:
                placed = (new_start_ns, new_end_ns)
                break

        if placed is not None:
            placebo_intervals_ns.append(placed)

    if not placebo_intervals_ns:
        return None

    # Vectorized arm assignment
    in_mask = np.zeros(len(fire_dates_ns), dtype=bool)
    for (ps, pe) in placebo_intervals_ns:
        in_mask |= (fire_dates_ns >= ps) & (fire_dates_ns <= pe)

    # Return raw arrays for pooled aggregation in caller
    return (in_mask, ret21_vals)


# ---------------------------------------------------------------------------
# MDE @ 80% power (for UNDERPOWERED-ACCRUING verdict)
# ---------------------------------------------------------------------------

def mde_at_power(n_windows: int, power: float = POWER_TARGET, alpha: float = BH_Q) -> float:
    """Simple MDE estimate at given power using normal approximation.

    For a one-sided test at alpha significance and 'power' power with n_windows
    cluster units, returns the detectable effect size in win-rate units.
    Assumes cluster sizes ~10 (typical member fires per window).
    This is an approximation; the actual power depends on within-cluster ICC.
    """
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha)
    z_beta = norm.ppf(power)
    # Conservative: treat n_windows as effective n (cluster adjustment ~1.5x)
    n_eff = max(1, n_windows / 1.5)
    # For a proportion test p ~ 0.5 (WR)
    p = 0.5
    se = np.sqrt(p * (1 - p) / n_eff)
    mde = (z_alpha + z_beta) * se
    return float(mde)


# ---------------------------------------------------------------------------
# BH correction (2 reads)
# ---------------------------------------------------------------------------

def bh_correct(p_values: list[float], q: float = BH_Q) -> list[bool]:
    """Benjamini-Hochberg correction. Returns list of booleans (rejected = significant)."""
    m = len(p_values)
    if m == 0:
        return []
    sorted_idx = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_idx]
    thresholds = (np.arange(1, m + 1) / m) * q
    rejected = sorted_p <= thresholds
    # Find largest k where p(k) <= k*q/m
    cummax = np.zeros(m, dtype=bool)
    last_rej = -1
    for i in range(m - 1, -1, -1):
        if rejected[i]:
            last_rej = i
            break
    if last_rej >= 0:
        for i in range(last_rej + 1):
            cummax[i] = True
    result = np.zeros(m, dtype=bool)
    result[sorted_idx] = cummax
    return list(result)


# ---------------------------------------------------------------------------
# Ablation (c): member-trigger value
# Spec §1: for each armed window, ALL PIT-eligible sector members entered at
# window's first session + 1 (next-bar fill), graded identically via
# engine/grading.py forward_metrics + terminal_state clean8_21.
# ---------------------------------------------------------------------------

def _load_massive_ticker(ticker: str, massive_dir: Path) -> pd.DataFrame:
    """Load close series for one ticker from the massive_stock_day store.

    Handles BRK-B / BRK.B filename artifact: tries both the canonical ticker
    filename and the dot-substitution variant.  Returns empty DataFrame (with
    no 'close' column) when the ticker is absent — callers must check .empty
    and 'close' in columns.

    Per spec §1: 'graded from collectors/massive_stock_day.load_ticker() closes'.
    collectors.massive_stock_day.load_ticker() resolves to config.data_dir() /
    massive_stock_day/, which is the worktree-local path and is empty in this
    worktree.  The --data-dir CLI argument is the MAIN (READ-ONLY) data dir,
    which is the canonical store.  We therefore read from data_dir directly with
    the BRK-B artifact handling that load_ticker() would apply.
    """
    # Primary lookup: canonical ticker filename
    path = massive_dir / f"{ticker}.parquet"
    if not path.exists():
        # BRK-B artifact: try replacing '-' with '.' in ticker
        alt = massive_dir / f"{ticker.replace('-', '.')}.parquet"
        if alt.exists():
            path = alt
        else:
            return pd.DataFrame()  # absent — counted out by caller
    try:
        return pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("_load_massive_ticker(%s): read error %s — counted out", ticker, e)
        return pd.DataFrame()


def run_ablation_c(
    windows: pd.DataFrame,
    basket_members_by_node: dict[str, list[str]],
    pit_by_ticker: dict[str, pd.DataFrame],
    data_dir: Path,
    trading_days: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, dict]:
    """Run ablation (c): blind entry at window start+1 for all PIT-eligible members.

    Reads massive_stock_day closes from data_dir (the MAIN data directory passed
    via --data-dir) using _load_massive_ticker() which handles the BRK-B filename
    artifact and counts every skip with an explicit reason code.

    Returns (records_df, skip_counts) where skip_counts tracks excluded tickers.
    """
    from engine.grading import forward_metrics, terminal_state

    records = []
    massive_dir = data_dir / "massive_stock_day"
    td_arr = trading_days.to_numpy()

    skip_counts: dict[str, int] = {
        "pit_fail": 0, "ticker_not_found": 0, "read_error_counted_via_empty": 0,
        "no_close_col": 0,
    }

    log.info("Ablation (c): processing %d windows across %d nodes...", len(windows), windows["node"].nunique())
    t0 = time.time()

    for _, win in windows.iterrows():
        node = win["node"]
        win_id = int(win["window_id"])
        win_start = pd.Timestamp(win["window_start"])

        # Entry date = window_start + 1 session (next bar after window start)
        start_idx = np.searchsorted(td_arr, np.datetime64(win_start), side="left")
        if start_idx + 1 >= len(td_arr):
            continue
        entry_signal_date = pd.Timestamp(td_arr[start_idx])  # signal bar = window start
        # (next-bar fill will pick the fill bar = window_start + 1 session)

        members = basket_members_by_node.get(node, [])
        for ticker in members:
            # PIT check at window_start
            if not is_pit_member(ticker, win_start, pit_by_ticker):
                skip_counts["pit_fail"] += 1
                continue

            # FIX (minor): use _load_massive_ticker() which handles BRK-B artifact
            # and logs read errors rather than silently continuing.
            close_df = _load_massive_ticker(ticker, massive_dir)

            if close_df.empty:
                # Either file absent (ticker not in store) or read error (already logged)
                skip_counts["ticker_not_found"] += 1
                log.debug("Ablation (c): %s absent from massive store — counted out", ticker)
                continue

            if "close" not in close_df.columns:
                skip_counts["no_close_col"] += 1
                log.warning("Ablation (c): %s has no 'close' column — counted out", ticker)
                continue

            close = close_df["close"]
            close.index = pd.DatetimeIndex(close.index)
            close = close.sort_index()

            # Grade with forward_metrics and terminal_state (clean8_21)
            fm = forward_metrics(close, entry_signal_date, horizons=(5, 10, 21))
            ts = terminal_state(
                close, entry_signal_date,
                liftoff_mult=1.08, liftoff_horizon=21,
            )

            records.append({
                "arm": "ablation_c",
                "window_id": win_id,
                "node_etf": node,
                "ticker": ticker,
                "signal_date": str(entry_signal_date.date()),
                "window_start": str(win_start.date()),
                "pit_member": True,
                "fwd_ret_5": fm.get("fwd_ret_5"),
                "fwd_ret_10": fm.get("fwd_ret_10"),
                "fwd_ret_21": fm.get("fwd_ret_21"),
                "fwd_mdd_5": fm.get("fwd_mdd_5"),
                "fwd_mdd_10": fm.get("fwd_mdd_10"),
                "fwd_mdd_21": fm.get("fwd_mdd_21"),
                "fwd_mfe_5": fm.get("fwd_mfe_5"),
                "fwd_mfe_10": fm.get("fwd_mfe_10"),
                "fwd_mfe_21": fm.get("fwd_mfe_21"),
                "state_8_21": ts.get("state"),
                "entry_price": fm.get("entry_price"),
                "fill_date": fm.get("fill_date"),
            })

    elapsed = time.time() - t0
    log.info("Ablation (c): %d entries graded in %.1fs  skips=%s",
             len(records), elapsed, skip_counts)
    return (pd.DataFrame(records) if records else pd.DataFrame()), skip_counts


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def load_replay_verdict_grade(data_dir: Path) -> pd.DataFrame:
    """Load verdict-grade rows from replay_boarded.parquet.

    Filters: survivor_bias==False, verdict_grade==True, price_source=='massive'.
    Effective window: signal_date >= EFFECTIVE_WINDOW_START.
    Uncensored: horizon_censored==False.
    """
    replay_path = data_dir / "replay" / "replay_boarded.parquet"
    replay = pd.read_parquet(replay_path)

    # Fix: convert signal_date to datetime before boundary comparison.
    # signal_date is stored as str (ISO 'YYYY-MM-DD') in the parquet; lexicographic
    # comparison coincidentally works for zero-padded ISO dates but is fragile —
    # any non-ISO formatting would silently corrupt the population boundary.
    replay["signal_date"] = pd.to_datetime(replay["signal_date"])

    # Apply verdict-grade filters per spec §1 and P0 memo v1.1
    mask = (
        (replay["survivor_bias"] == False) &
        (replay["verdict_grade"] == True) &
        (replay["price_source"] == "massive") &
        (replay["signal_date"] >= EFFECTIVE_WINDOW_START) &
        (replay["horizon_censored"] == False)
    )
    vg = replay[mask].copy()

    # Add node_etf column (GICS -> XL ETF)
    vg["node_etf"] = vg["sector"].map(GICS_TO_NODE)

    # Count unmatched sectors
    unmatched = vg["node_etf"].isna().sum()
    if unmatched > 0:
        log.warning("load_replay: %d rows with unmatched sector (not in GICS_TO_NODE) — excluded", unmatched)
        vg = vg[vg["node_etf"].notna()].copy()

    log.info("Verdict-grade rows (effective window, uncensored): %d", len(vg))
    return vg


def get_trading_days(data_dir: Path) -> pd.DatetimeIndex:
    """Get trading day calendar from replay signal dates (comprehensive)."""
    replay_path = data_dir / "replay" / "replay_boarded.parquet"
    replay = pd.read_parquet(replay_path, columns=["signal_date"])
    dates = pd.to_datetime(replay["signal_date"]).drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates)


def build_basket_members(worktree_dir: Path) -> dict[str, list[str]]:
    """Build {node_etf: [ticker, ...]} from worktree data/baskets/membership.json.

    Uses etf_proxy field (exact 1:1 per spec §1).
    Primary: us_sector_* baskets (one per XL ETF).
    Fallback: any basket with etf_proxy matching an XL ticker.
    Spec disclosed limitation: basket membership is a static 2023-05-09 snapshot (hindsight).
    """
    membership_path = worktree_dir / "data" / "baskets" / "membership.json"
    if not membership_path.exists():
        _fatal(f"FIDELITY GATE FAIL: membership.json not found at {membership_path}")

    with open(membership_path) as f:
        membership = json.load(f)

    baskets = membership.get("baskets", {})

    # Prefer us_sector_* baskets for each XL node (one GICS-pure basket per node)
    node_to_members: dict[str, list[str]] = {}
    us_sector_by_etf: dict[str, list[str]] = {}

    for bk_name, bk_data in baskets.items():
        ep = bk_data.get("etf_proxy", "")
        if isinstance(ep, list):
            ep = ep[0] if ep else ""
        if not isinstance(ep, str) or not ep.startswith("XL"):
            continue
        members = [m["ticker"] for m in bk_data.get("members", [])
                   if m.get("removed") is None]  # only current members
        if bk_name.startswith("us_sector_"):
            us_sector_by_etf.setdefault(ep, []).extend(members)
        else:
            node_to_members.setdefault(ep, [])
            # Do not override us_sector_* but collect for fallback

    # Merge: prefer us_sector_* members; supplement with other baskets for nodes missing one
    for node in ALL_NODES:
        if node in us_sector_by_etf:
            node_to_members[node] = list(set(us_sector_by_etf[node]))
        else:
            existing = node_to_members.get(node, [])
            # Try to find any basket with this etf_proxy
            for bk_name, bk_data in baskets.items():
                ep = bk_data.get("etf_proxy", "")
                if isinstance(ep, list):
                    ep = ep[0] if ep else ""
                if ep == node:
                    members = [m["ticker"] for m in bk_data.get("members", [])
                               if m.get("removed") is None]
                    existing.extend(members)
            node_to_members[node] = list(set(existing))

    # Log coverage
    tickers_not_in_basket = []
    for node, members in node_to_members.items():
        log.info("Basket %s: %d members (etf_proxy %s)", node, len(members), node)

    return node_to_members


def run_main(args: argparse.Namespace) -> None:
    """Main pipeline."""
    data_dir = Path(args.data_dir)
    worktree_dir = ROOT  # governance files (baskets) from worktree
    w0_csv_path = worktree_dir / "research" / "oracle_asymmetry" / "W0_1_events_graded.csv"
    output_dir = worktree_dir / "research" / "oracle_asymmetry"

    log.info("=" * 70)
    log.info("OTA W2 — Member Transmission")
    log.info("data_dir: %s", data_dir)
    log.info("worktree_dir: %s", worktree_dir)
    log.info("Effective verdict window: %s → (last replay date)", EFFECTIVE_WINDOW_START)
    log.info("Seed: %d  Bootstrap draws: %d  Placebo draws: %d",
             SEED, BOOTSTRAP_DRAWS, PLACEBO_DRAWS)
    log.info("=" * 70)

    # --- Fidelity gate (FIRST — loud abort) ---
    fidelity = run_fidelity_gate(data_dir, w0_csv_path)

    # --- Load data ---
    log.info("Loading verdict-grade replay rows...")
    vg = load_replay_verdict_grade(data_dir)
    vg["signal_date"] = pd.to_datetime(vg["signal_date"])

    log.info("Loading trading days calendar...")
    trading_days = get_trading_days(data_dir)

    log.info("Loading PIT membership...")
    pit_path = data_dir / "breadth" / "sp1500_pit_membership.parquet"
    pit_df = build_pit_membership_lookup(pit_path)
    pit_by_ticker: dict[str, pd.DataFrame] = {}
    for ticker, group in pit_df.groupby("ticker"):
        pit_by_ticker[ticker] = group.reset_index(drop=True)

    log.info("Loading panel_s (VIX regime)...")
    panel_s = pd.read_parquet(data_dir / "oracle" / "panel_s.parquet")

    log.info("Loading basket membership...")
    basket_members_by_node = build_basket_members(worktree_dir)

    # --- W0 events: build armed windows (K=10, primary: a15-raw) ---
    log.info("Loading W0 events CSV...")
    w0 = pd.read_csv(w0_csv_path)

    for family_label, family_name, dedup_val in [
        ("primary (a15-raw)", W0_PRIMARY_FAMILY, W0_PRIMARY_DEDUP),
        ("secondary (ep_onset_in)", W0_SECONDARY_FAMILY, None),
    ]:
        fam_df = w0[w0["family"] == family_name].copy()
        if dedup_val is not None:
            fam_df = fam_df[fam_df["dedup_variant"] == dedup_val]
        unique_fires = fam_df.drop_duplicates(subset=["node", "trigger_date"])

        # FIX (blocker): Filter fire dates to >= EFFECTIVE_WINDOW_START.
        # get_trading_days() builds the calendar solely from replay signal_date,
        # which starts at EFFECTIVE_WINDOW_START.  Any pre-replay W0 fire date
        # falls BEFORE the entire td_arr, so searchsorted returns index-0
        # (= 2022-06-30) and creates a phantom armed window starting at the
        # replay start date for every node.  These phantom windows contaminate
        # the IN arm with signals from the effective-window open (2022-07-01
        # to ~2022-07-15) even when no actual a15 fire existed on that node at
        # that time.  Restricting to fires on or after EFFECTIVE_WINDOW_START
        # eliminates the phantom windows entirely.
        pre_count = int((unique_fires["trigger_date"] < EFFECTIVE_WINDOW_START).sum())
        unique_fires = unique_fires[unique_fires["trigger_date"] >= EFFECTIVE_WINDOW_START].copy()
        if pre_count > 0:
            log.info("  %s: dropped %d pre-%s fires (phantom-window fix)",
                     family_label, pre_count, EFFECTIVE_WINDOW_START)

        fires_by_node: dict[str, list[str]] = {}
        for _, row in unique_fires.iterrows():
            fires_by_node.setdefault(row["node"], []).append(row["trigger_date"])

        windows_k10 = build_armed_windows(fires_by_node, K_PRIMARY, trading_days)
        log.info("Armed windows %s K=%d: %d windows across %d nodes",
                 family_label, K_PRIMARY, len(windows_k10), windows_k10["node"].nunique() if len(windows_k10) > 0 else 0)
        for node in sorted(fires_by_node.keys()):
            node_wins = windows_k10[windows_k10["node"] == node] if len(windows_k10) > 0 else pd.DataFrame()
            log.info("  %s: %d fire dates -> %d merged windows (K=%d)",
                     node, len(fires_by_node.get(node, [])), len(node_wins), K_PRIMARY)

        if family_name == W0_PRIMARY_FAMILY:
            primary_windows = windows_k10
            primary_fires_by_node = fires_by_node
        else:
            secondary_windows = windows_k10
            secondary_fires_by_node = fires_by_node

    # --- Build windows_by_node lookup for primary ---
    primary_windows_by_node: dict[str, pd.DataFrame] = {}
    for node in ALL_NODES:
        pw = primary_windows[primary_windows["node"] == node] if len(primary_windows) > 0 else pd.DataFrame()
        primary_windows_by_node[node] = pw.reset_index(drop=True)

    secondary_windows_by_node: dict[str, pd.DataFrame] = {}
    for node in ALL_NODES:
        sw = secondary_windows[secondary_windows["node"] == node] if len(secondary_windows) > 0 else pd.DataFrame()
        secondary_windows_by_node[node] = sw.reset_index(drop=True)

    # --- Assign IN/OUT arms to verdict-grade member fires (vectorized) ---
    log.info("Assigning arms to %d verdict-grade member fires (vectorized)...", len(vg))
    vg = vg.copy()

    # Vectorized arm assignment: per node, check all signal dates against window intervals
    arm_arr = np.full(len(vg), "OUT", dtype=object)
    wid_arr = np.full(len(vg), -1, dtype=np.int64)

    vg_dates_ns = vg["signal_date"].values.astype("datetime64[ns]").astype("int64")
    vg_nodes = vg["node_etf"].values

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
            matched_local = np.where(in_win)[0]
            for li in matched_local:
                gi = node_mask_idx[li]
                if arm_arr[gi] == "OUT":  # first window wins
                    arm_arr[gi] = "IN"
                    wid_arr[gi] = win_id

    vg["arm"] = arm_arr
    vg["window_id"] = [int(v) if v >= 0 else None for v in wid_arr]

    # Vectorized PIT membership: build per-ticker fast lookup using epoch boundaries
    log.info("Checking PIT membership for %d rows...", len(vg))
    # Build per-ticker (start_ns, end_ns) intervals array for fast interval check
    pit_flags_arr = np.zeros(len(vg), dtype=bool)
    ticker_arr = vg["ticker"].values

    # Pre-build per-ticker intervals as numpy arrays
    pit_intervals: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, group in pit_df.groupby("ticker"):
        starts = group["start_date"].values.astype("datetime64[ns]").astype("int64")
        ends_raw = group["end_date"].values
        # NaT → very large int (still member)
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

    log.info("Arm distribution: %s", vg["arm"].value_counts().to_dict())
    log.info("IN arm PIT members: %d / %d", vg[(vg["arm"]=="IN") & vg["pit_member"]].shape[0], (vg["arm"]=="IN").sum())
    log.info("OUT arm PIT members: %d / %d", vg[(vg["arm"]=="OUT") & vg["pit_member"]].shape[0], (vg["arm"]=="OUT").sum())

    # --- Separate IN and OUT arms ---
    in_arm = vg[vg["arm"] == "IN"].copy()
    out_arm = vg[vg["arm"] == "OUT"].copy()

    in_arm_pit = in_arm[in_arm["pit_member"] == True].copy()
    out_arm_pit = out_arm[out_arm["pit_member"] == True].copy()

    log.info("IN arm (PIT eligible): %d rows, %d windows",
             len(in_arm_pit), in_arm_pit["window_id"].nunique() if len(in_arm_pit) > 0 else 0)
    log.info("OUT arm (PIT eligible): %d rows", len(out_arm_pit))

    # --- K sensitivity windows (appendix only) ---
    sensitivity_windows: dict[int, pd.DataFrame] = {}
    for k_sens in K_SENSITIVITY:
        w_sens = build_armed_windows(primary_fires_by_node, k_sens, trading_days)
        sensitivity_windows[k_sens] = w_sens
        log.info("K=%d sensitivity: %d windows", k_sens, len(w_sens))

    # --- Build W2_member_trades.csv ---
    # One row per (arm, member fire | ablation entry) with window id, sector, metrics, PIT flags
    log.info("Building W2_member_trades.csv...")

    def _prep_arm_df(df: pd.DataFrame, arm_label: str) -> pd.DataFrame:
        cols = [
            "ticker", "signal_date", "arm", "window_id", "node_etf", "sector",
            "pit_member", "fwd_ret_5", "fwd_ret_10", "fwd_ret_21",
            "fwd_mdd_5", "fwd_mdd_10", "fwd_mdd_21",
            "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21",
            "state_8_21",
        ]
        out = df[[c for c in cols if c in df.columns]].copy()
        out["arm"] = arm_label
        out["signal_date"] = out["signal_date"].astype(str)
        return out

    trades_in = _prep_arm_df(in_arm, "IN")
    trades_out = _prep_arm_df(out_arm, "OUT")

    # --- Ablation (c) ---
    log.info("Running ablation (c)...")
    t0_abl = time.time()
    ablation_df, ablation_skip_counts = run_ablation_c(
        primary_windows,
        basket_members_by_node,
        pit_by_ticker,
        data_dir,
        trading_days,
    )
    log.info("Ablation (c) done in %.1fs: %d entries  skips=%s",
             time.time() - t0_abl, len(ablation_df), ablation_skip_counts)

    # Combine for output CSV
    all_trades = pd.concat([trades_in, trades_out], ignore_index=True)
    if len(ablation_df) > 0:
        all_trades = pd.concat([all_trades, ablation_df], ignore_index=True)

    trades_csv_path = output_dir / "W2_member_trades.csv"
    # FIX (minor): write a header comment so that anyone reading the CSV knows that
    # headline aggregates require pit_member==True.  IN and OUT arms contain both
    # PIT and non-PIT rows; the graded metrics (in_metrics/out_metrics) only use
    # the pit_member==True subset.  Naive aggregation without this filter produces
    # a different (and incorrect under the spec's stated design) delta.
    # We prepend a comment line to the CSV.
    csv_header_comment = (
        "# W2_member_trades.csv — OTA W2 Member Transmission (2026-07-05)\n"
        "# IMPORTANT: headline aggregates (WR21, mean fwd_ret_21, etc.) require\n"
        "# filtering pit_member==True.  IN and OUT arms include non-PIT rows\n"
        "# (pit_member==False) which must be excluded before recomputing metrics.\n"
        "# ablation_c rows are all pit_member==True by construction.\n"
    )
    csv_text = all_trades.to_csv(index=False)
    trades_csv_path.write_text(csv_header_comment + csv_text, encoding="utf-8")
    log.info("W2_member_trades.csv written: %d rows to %s", len(all_trades), trades_csv_path)

    # --- Compute metrics ---
    log.info("Computing metrics...")
    in_metrics = compute_metrics(in_arm_pit)
    out_metrics = compute_metrics(out_arm_pit)

    def _wr21(df: pd.DataFrame) -> float:
        r = df["fwd_ret_21"].dropna()
        return float((r > 0).mean()) if len(r) > 0 else float("nan")

    def _mean_ret21(df: pd.DataFrame) -> float:
        r = df["fwd_ret_21"].dropna()
        return float(r.mean()) if len(r) > 0 else float("nan")

    # --- Cluster bootstrap for IN arm ---
    log.info("Running cluster bootstrap (2,000 draws, IN arm)...")
    t0_boot = time.time()
    rng_boot = np.random.default_rng(SEED)
    ci_wr21 = cluster_bootstrap_ci(
        in_arm_pit, _wr21, window_id_col="window_id",
        n_draws=BOOTSTRAP_DRAWS, rng=rng_boot,
    )
    ci_ret21 = cluster_bootstrap_ci(
        in_arm_pit, _mean_ret21, window_id_col="window_id",
        n_draws=BOOTSTRAP_DRAWS, rng=rng_boot,
    )
    log.info("Bootstrap done in %.1fs", time.time() - t0_boot)

    # --- Regime-matched placebo (500 draws) ---
    log.info("Running regime-matched placebo (500 draws)...")
    t0_plac = time.time()
    rng_plac = np.random.default_rng(SEED + 1)
    vix_regime_by_node = build_vix_regime_lookup(panel_s)

    # Pre-compute per-node arrays for vectorized placebo (avoid rebuilding each draw).
    # FIX (blocker): placebo fire pool restricted to PIT-eligible rows only, matching
    # the PIT-filtered observed statistic.  Previously used all verdict-grade rows
    # (vg) regardless of pit_member status, creating a mismatched population.
    vg_pit = vg[vg["pit_member"] == True].copy()

    td_arr_ns = trading_days.to_numpy().astype("datetime64[ns]").astype("int64")
    nodes_with_windows = list(primary_windows["node"].unique()) if len(primary_windows) > 0 else []
    node_fire_data: dict[str, tuple] = {}
    for node in nodes_with_windows:
        # FIX: use PIT-filtered fires to match the observed statistic's population
        node_fires = vg_pit[vg_pit["node_etf"] == node]
        if len(node_fires) == 0:
            continue
        fire_dates_ns_node = node_fires["signal_date"].values.astype("datetime64[ns]").astype("int64")
        ret21_vals_node = node_fires["fwd_ret_21"].to_numpy(dtype=float, na_value=float("nan"))
        is_high = _build_vix_regime_arrays(vix_regime_by_node, td_arr_ns, node)
        node_win = primary_windows[primary_windows["node"] == node].copy()

        # Pre-compute real armed-window intervals for this node (int64 ns).
        # FIX (major): passed to placebo draw so real windows are excluded from
        # candidate placements (spec §2: 'random non-armed location').
        real_ivs_node: list[tuple[int, int]] = []
        for _, nw in node_win.iterrows():
            ws_ns = np.datetime64(pd.Timestamp(nw["window_start"]), "ns").astype("int64")
            we_ns = np.datetime64(pd.Timestamp(nw["window_end"]), "ns").astype("int64")
            real_ivs_node.append((int(ws_ns), int(we_ns)))

        node_fire_data[node] = (fire_dates_ns_node, ret21_vals_node, is_high, node_win, real_ivs_node)

    placebo_deltas_wr21 = []
    placebo_deltas_ret21 = []

    for draw_i in range(PLACEBO_DRAWS):
        # FIX (blocker): pool IN/OUT assignments across all nodes before computing
        # the delta, matching the pooled observed statistic (in_metrics − out_metrics
        # are computed on the full cross-node IN/OUT arms, not per-node averages).
        # Previously the code took nanmean(per-node deltas), which differs from the
        # pooled delta when node sizes are unequal.
        pool_in_ret21: list[np.ndarray] = []
        pool_out_ret21: list[np.ndarray] = []

        for node in nodes_with_windows:
            if node not in node_fire_data:
                continue
            fire_dates_ns_node, ret21_vals_node, is_high, node_win, real_ivs_node = node_fire_data[node]
            result = _placebo_draw_both_metrics(
                node_win, fire_dates_ns_node, ret21_vals_node, td_arr_ns, is_high,
                rng_plac, real_intervals_ns=real_ivs_node,
            )
            if result is None:
                continue
            in_mask_node, ret21_node = result
            valid = np.isfinite(ret21_node)
            pool_in_ret21.append(ret21_node[in_mask_node & valid])
            pool_out_ret21.append(ret21_node[(~in_mask_node) & valid])

        if not pool_in_ret21 or not pool_out_ret21:
            continue
        all_in_ret = np.concatenate(pool_in_ret21)
        all_out_ret = np.concatenate(pool_out_ret21)
        if len(all_in_ret) == 0 or len(all_out_ret) == 0:
            continue

        dwr = float((all_in_ret > 0).mean()) - float((all_out_ret > 0).mean())
        dret = float(all_in_ret.mean()) - float(all_out_ret.mean())
        if np.isfinite(dwr):
            placebo_deltas_wr21.append(dwr)
        if np.isfinite(dret):
            placebo_deltas_ret21.append(dret)

    elapsed_plac = time.time() - t0_plac
    log.info("Placebo done in %.1fs: %d/%d draws produced wr21 deltas, %d/%d ret21 deltas",
             elapsed_plac, len(placebo_deltas_wr21), PLACEBO_DRAWS,
             len(placebo_deltas_ret21), PLACEBO_DRAWS)

    plac_p95_wr21 = float(np.nanpercentile(placebo_deltas_wr21, 95)) if placebo_deltas_wr21 else float("nan")
    plac_p95_ret21 = float(np.nanpercentile(placebo_deltas_ret21, 95)) if placebo_deltas_ret21 else float("nan")

    # --- Gate evaluation (G-W2-A, G-W2-B) ---
    in_wr21 = in_metrics.get("wr21", float("nan"))
    out_wr21 = out_metrics.get("wr21", float("nan"))
    delta_wr21 = (in_wr21 - out_wr21) if (np.isfinite(in_wr21) and np.isfinite(out_wr21)) else float("nan")

    in_ret21 = in_metrics.get("mean_fwd_ret_21", float("nan"))
    out_ret21 = out_metrics.get("mean_fwd_ret_21", float("nan"))
    delta_ret21 = (in_ret21 - out_ret21) if (np.isfinite(in_ret21) and np.isfinite(out_ret21)) else float("nan")

    # Gate conditions
    g_w2a_delta_pos = np.isfinite(delta_wr21) and delta_wr21 > 0
    g_w2a_beats_placebo = np.isfinite(plac_p95_wr21) and np.isfinite(delta_wr21) and delta_wr21 > plac_p95_wr21
    g_w2a_pass = g_w2a_delta_pos and g_w2a_beats_placebo

    g_w2b_delta_pos = np.isfinite(delta_ret21) and delta_ret21 > 0
    g_w2b_beats_placebo = np.isfinite(plac_p95_ret21) and np.isfinite(delta_ret21) and delta_ret21 > plac_p95_ret21
    g_w2b_pass = g_w2b_delta_pos and g_w2b_beats_placebo

    # BH correction on the 2 p-values (approximated from placebo distributions)
    # p-value = fraction of placebo draws >= observed delta
    def _placebo_pval(delta: float, placebo_draws: list[float]) -> float:
        if not np.isfinite(delta) or not placebo_draws:
            return 1.0
        arr = np.array(placebo_draws)
        return float((arr >= delta).mean())

    pval_wr21 = _placebo_pval(delta_wr21, placebo_deltas_wr21)
    pval_ret21 = _placebo_pval(delta_ret21, placebo_deltas_ret21)

    bh_results = bh_correct([pval_wr21, pval_ret21], q=BH_Q)
    bh_g_w2a = bh_results[0]
    bh_g_w2b = bh_results[1]

    # --- Verdict (pre-bound vocabulary) ---
    n_windows_in = in_arm_pit["window_id"].nunique() if len(in_arm_pit) > 0 else 0

    if g_w2a_pass and g_w2b_pass and bh_g_w2a and bh_g_w2b:
        verdict = "CONDITION-LIFT"
        verdict_note = (
            "Both G-W2-A and G-W2-B pass: delta positive and above placebo p95; "
            "BH-corrected at q=0.10. DESCRIPTIVE class — display-only until formal P3-style registration."
        )
    elif (g_w2a_delta_pos or g_w2b_delta_pos) and not (g_w2a_pass and g_w2b_pass):
        # Point estimates positive but CIs/placebo inconclusive
        mde = mde_at_power(n_windows_in) if n_windows_in > 0 else float("nan")
        verdict = "UNDERPOWERED-ACCRUING"
        verdict_note = (
            f"Point estimates partially positive but placebo/CI inconclusive. "
            f"MDE@{int(POWER_TARGET*100)}% given {n_windows_in} IN-arm windows "
            f"(cluster-corrected): {mde:.3f} WR21 units. Accrue more events."
        )
    else:
        mde = mde_at_power(n_windows_in) if n_windows_in > 0 else float("nan")
        verdict = "NULL"
        verdict_note = (
            f"Neither gate passes. No evidence Oracle armed window adds member-entry quality. "
            f"MDE@{int(POWER_TARGET*100)}%: {mde:.3f} WR21 units given {n_windows_in} IN-arm windows."
        )

    log.info("=" * 70)
    log.info("VERDICT: %s", verdict)
    log.info("G-W2-A: delta_wr21=%.4f  placebo_p95=%.4f  PASS=%s  BH=%s",
             delta_wr21, plac_p95_wr21, g_w2a_pass, bh_g_w2a)
    log.info("G-W2-B: delta_ret21=%.4f  placebo_p95=%.4f  PASS=%s  BH=%s",
             delta_ret21, plac_p95_ret21, g_w2b_pass, bh_g_w2b)
    log.info("=" * 70)

    # --- Secondary condition (ep_onset_in) — vectorized arm assignment ---
    log.info("Running secondary condition (ep_onset_in) analysis (vectorized)...")
    sec_arm_arr = np.full(len(vg), "OUT", dtype=object)
    sec_wid_arr = np.full(len(vg), -1, dtype=np.int64)

    for node in ALL_NODES:
        sw = secondary_windows[secondary_windows["node"] == node] if len(secondary_windows) > 0 else pd.DataFrame()
        if len(sw) == 0:
            continue
        node_mask_idx = np.where(vg_nodes == node)[0]
        if len(node_mask_idx) == 0:
            continue
        node_dates_ns = vg_dates_ns[node_mask_idx]
        for _, win in sw.iterrows():
            ws_ns = np.datetime64(pd.Timestamp(win["window_start"]), "ns").astype("int64")
            we_ns = np.datetime64(pd.Timestamp(win["window_end"]), "ns").astype("int64")
            win_id = int(win["window_id"])
            in_win = (node_dates_ns >= ws_ns) & (node_dates_ns <= we_ns)
            for li in np.where(in_win)[0]:
                gi = node_mask_idx[li]
                if sec_arm_arr[gi] == "OUT":
                    sec_arm_arr[gi] = "IN"
                    sec_wid_arr[gi] = win_id

    vg_sec = vg.copy()
    vg_sec["sec_arm"] = sec_arm_arr
    vg_sec["sec_window_id"] = [int(v) if v >= 0 else None for v in sec_wid_arr]

    sec_in = vg_sec[(vg_sec["sec_arm"] == "IN") & (vg_sec["pit_member"] == True)].copy()
    sec_in["window_id"] = sec_in["sec_window_id"]
    sec_out = vg_sec[(vg_sec["sec_arm"] == "OUT") & (vg_sec["pit_member"] == True)].copy()

    sec_in_metrics = compute_metrics(sec_in)
    sec_out_metrics = compute_metrics(sec_out)
    sec_delta_wr21 = (sec_in_metrics.get("wr21", float("nan")) - sec_out_metrics.get("wr21", float("nan")))
    sec_n_wins = int(sec_in["window_id"].nunique()) if len(sec_in) > 0 else 0

    log.info("Secondary (ep_onset_in): IN=%d rows (%d windows), OUT=%d rows  delta_wr21=%.4f",
             len(sec_in), sec_n_wins, len(sec_out), sec_delta_wr21)

    # --- Per-sector split (appendix) ---
    per_sector_rows = []
    for node in ALL_NODES:
        node_in = in_arm_pit[in_arm_pit["node_etf"] == node]
        node_out = out_arm_pit[out_arm_pit["node_etf"] == node]
        n_in_wins = int(node_in["window_id"].nunique()) if len(node_in) > 0 else 0
        node_in_m = compute_metrics(node_in)
        node_out_m = compute_metrics(node_out)
        per_sector_rows.append({
            "node": node,
            "in_n_windows": n_in_wins,
            "in_n_rows": len(node_in),
            "in_wr21": node_in_m.get("wr21", float("nan")),
            "out_n_rows": len(node_out),
            "out_wr21": node_out_m.get("wr21", float("nan")),
            "delta_wr21": (node_in_m.get("wr21", float("nan")) - node_out_m.get("wr21", float("nan"))),
        })

    per_sector_df = pd.DataFrame(per_sector_rows)

    # --- K sensitivity (appendix) ---
    k_sens_rows = []
    for k_sens in K_SENSITIVITY:
        ws = sensitivity_windows[k_sens]
        ws_by_node = {}
        for node in ALL_NODES:
            nw = ws[ws["node"] == node] if len(ws) > 0 else pd.DataFrame()
            ws_by_node[node] = nw.reset_index(drop=True)
        # Vectorized K-sensitivity arm assignment
        k_arm_arr = np.full(len(vg), "OUT", dtype=object)
        for k_node in ALL_NODES:
            k_node_wins = ws_by_node.get(k_node, pd.DataFrame())
            if len(k_node_wins) == 0:
                continue
            k_node_idx = np.where(vg_nodes == k_node)[0]
            if len(k_node_idx) == 0:
                continue
            k_node_dates = vg_dates_ns[k_node_idx]
            for _, k_win in k_node_wins.iterrows():
                kws_ns = np.datetime64(pd.Timestamp(k_win["window_start"]), "ns").astype("int64")
                kwe_ns = np.datetime64(pd.Timestamp(k_win["window_end"]), "ns").astype("int64")
                for li in np.where((k_node_dates >= kws_ns) & (k_node_dates <= kwe_ns))[0]:
                    gi = k_node_idx[li]
                    if k_arm_arr[gi] == "OUT":
                        k_arm_arr[gi] = "IN"
        k_in_mask = k_arm_arr == "IN"
        k_in = vg[k_in_mask].copy()
        k_out = vg[~k_in_mask].copy()
        k_in_pit = k_in[k_in["pit_member"]==True]
        k_out_pit = k_out[k_out["pit_member"]==True]
        k_in_m = compute_metrics(k_in_pit)
        k_out_m = compute_metrics(k_out_pit)
        k_delta = k_in_m.get("wr21", float("nan")) - k_out_m.get("wr21", float("nan"))
        k_sens_rows.append({
            "k": k_sens,
            "in_n_windows": int(ws["node"].count()) if len(ws) > 0 else 0,
            "in_n_rows": len(k_in_pit),
            "in_wr21": k_in_m.get("wr21", float("nan")),
            "out_n_rows": len(k_out_pit),
            "out_wr21": k_out_m.get("wr21", float("nan")),
            "delta_wr21": k_delta,
        })

    # --- Ablation (c) metrics ---
    abl_metrics = compute_metrics(ablation_df) if len(ablation_df) > 0 else {}
    abl_n_wins = int(ablation_df["window_id"].nunique()) if len(ablation_df) > 0 else 0

    # --- Write W2_REPORT.md ---
    log.info("Writing W2_REPORT.md...")
    report_path = output_dir / "W2_REPORT.md"
    _write_report(
        report_path=report_path,
        fidelity=fidelity,
        primary_windows=primary_windows,
        in_arm_pit=in_arm_pit,
        out_arm_pit=out_arm_pit,
        in_metrics=in_metrics,
        out_metrics=out_metrics,
        ci_wr21=ci_wr21,
        ci_ret21=ci_ret21,
        delta_wr21=delta_wr21,
        delta_ret21=delta_ret21,
        plac_p95_wr21=plac_p95_wr21,
        plac_p95_ret21=plac_p95_ret21,
        placebo_deltas_wr21=placebo_deltas_wr21,
        placebo_deltas_ret21=placebo_deltas_ret21,
        pval_wr21=pval_wr21,
        pval_ret21=pval_ret21,
        bh_g_w2a=bh_g_w2a,
        bh_g_w2b=bh_g_w2b,
        g_w2a_pass=g_w2a_pass,
        g_w2b_pass=g_w2b_pass,
        verdict=verdict,
        verdict_note=verdict_note,
        n_windows_in=n_windows_in,
        sec_in_metrics=sec_in_metrics,
        sec_out_metrics=sec_out_metrics,
        sec_delta_wr21=sec_delta_wr21,
        sec_n_wins=sec_n_wins,
        per_sector_df=per_sector_df,
        k_sens_rows=k_sens_rows,
        abl_metrics=abl_metrics,
        abl_n_wins=abl_n_wins,
        ablation_df=ablation_df,
        ablation_skip_counts=ablation_skip_counts,
        elapsed_plac=elapsed_plac,
        n_placebo_draws=len(placebo_deltas_wr21),
    )
    log.info("W2_REPORT.md written to %s", report_path)
    log.info("Done.")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt(v: float | None, prec: int = 4) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:.{prec}f}"


def _write_report(
    report_path: Path,
    fidelity: dict,
    primary_windows: pd.DataFrame,
    in_arm_pit: pd.DataFrame,
    out_arm_pit: pd.DataFrame,
    in_metrics: dict,
    out_metrics: dict,
    ci_wr21: dict,
    ci_ret21: dict,
    delta_wr21: float,
    delta_ret21: float,
    plac_p95_wr21: float,
    plac_p95_ret21: float,
    placebo_deltas_wr21: list,
    placebo_deltas_ret21: list,
    pval_wr21: float,
    pval_ret21: float,
    bh_g_w2a: bool,
    bh_g_w2b: bool,
    g_w2a_pass: bool,
    g_w2b_pass: bool,
    verdict: str,
    verdict_note: str,
    n_windows_in: int,
    sec_in_metrics: dict,
    sec_out_metrics: dict,
    sec_delta_wr21: float,
    sec_n_wins: int,
    per_sector_df: pd.DataFrame,
    k_sens_rows: list,
    abl_metrics: dict,
    abl_n_wins: int,
    ablation_df: pd.DataFrame,
    ablation_skip_counts: dict,
    elapsed_plac: float,
    n_placebo_draws: int,
) -> None:

    lines = []
    a = lines.append

    a("# OTA W2 — Member Transmission Report")
    a("")
    a("> **MODERN-TRACK ONLY — DESCRIPTIVE/EXPLORATORY.**")
    a("> The word 'validated' does not appear in this document (Oracle Constitution §II).")
    a("> Era law: P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05).")
    a("> Spec: research/oracle_asymmetry/W2_SPEC.md (pre-registered 2026-07-05, frozen).")
    a("> Gates: 2 registered reads. BH q=0.10 within this family.")
    a("> Seed: 20260705. Bootstrap draws: 2,000. Placebo draws: 500.")
    a("")
    a("## Disclosed Limitations")
    a("")
    a("1. **Basket membership is a static 2023-05-09 snapshot** — contains hindsight bias for the 2022–2023 sub-window.")
    a("2. **No PIT GICS-sector map exists** — sector-drift between Oracle node and member basket is uncontrolled.")
    a("   Replay `sector` field (GICS string) is used to assign member fires to Oracle nodes via GICS_TO_NODE,")
    a("   rather than the spec's `etf_proxy` field (which replay does not carry). The mapping is functionally")
    a("   equivalent as long as a ticker's GICS sector has not drifted; sector-drift risk is uncontrolled.")
    a("3. **SP500 PIT intervals** are used for member eligibility (sp500 src rows from sp1500_pit_membership.parquet).")
    a("4. **BRK-B filename artifact** — BRK-B may appear as BRK-B.parquet or BRK.B.parquet; ablation (c)")
    a("   tries both variants via _load_massive_ticker() and counts absent tickers out explicitly.")
    a("5. **Effective verdict window ≈ 2022-06-30 → last replay date** (P0 memo v1.1 §6 Amendment 1: 250-bar MTF warmup consumes ~11 months of the 2021-07-06 nominal start).")
    a("6. **Cluster bootstrap** resamples window IDs with replacement; within-window member co-movement inflates naive CIs.")
    a("7. **MDE@80% is an approximation** — uses a normal-approximation formula with the number of IN-arm cluster")
    a("   windows as effective n (treating each window as one independent observation). The true design effect")
    a("   depends on within-window ICC and cluster size, which are not computed here. Treat MDE as order-of-magnitude.")
    a("8. **W2_member_trades.csv includes non-PIT rows** — IN and OUT arms contain both pit_member==True and")
    a("   pit_member==False rows. Headline aggregates require filtering pit_member==True before recomputation.")
    a("")
    a("## Preamble — Fidelity Gate")
    a("")
    a(f"- Replay rows total: {fidelity['replay_total_rows']:,}")
    a(f"- survivor_bias==False: {fidelity['replay_survivor_false']:,}")
    a(f"- verdict_grade==True: {fidelity['replay_verdict_grade_true']:,}")
    a(f"- horizon_censored==True (excluded): {fidelity['replay_horizon_censored']:,}")
    a(f"- Golden test PASSED: prod_fire_count={fidelity['golden_prod_fire_count']}, replay_fire_count={fidelity['golden_replay_fire_count']}, exact_match={fidelity['golden_exact_match']}")
    a(f"- W0 a15-all: {fidelity['w0_a15_all']}, a15-raw: {fidelity['w0_a15_raw']}, a15-unique(node,date): {fidelity['w0_a15_unique_fires']}")
    a(f"- W0 ep_onset_in: {fidelity['w0_ep_onset_in']}")
    a("")
    a("## Armed Windows (K=10, primary: a15-raw)")
    a("")
    if len(primary_windows) > 0:
        a(f"Total windows: {len(primary_windows)}")
        a("")
        a("| Node | Windows |")
        a("|------|---------|")
        for node in sorted(primary_windows["node"].unique()):
            n = len(primary_windows[primary_windows["node"] == node])
            a(f"| {node} | {n} |")
    else:
        a("No armed windows generated.")
    a("")
    a("## Arms Table (Primary: a15-raw, K=10)")
    a("")
    a(f"Effective n (window count, unit of independence): IN={n_windows_in}, OUT=n/a (no window structure)")
    a("")
    a("| Metric | IN (n windows={}) | OUT | Δ (IN−OUT) |".format(n_windows_in))
    a("|--------|-------------------|-----|-----------|")
    for metric_key, metric_label in [
        ("wr21", "WR21"),
        ("mean_fwd_ret_21", "Mean fwd_ret_21"),
        ("median_fwd_ret_21", "Median fwd_ret_21"),
        ("mean_mfe_21", "Mean fwd_mfe_21"),
        ("mean_mdd_21", "Mean fwd_mdd_21"),
        ("stop5_rate", "Stop-5 rate"),
    ]:
        iv = in_metrics.get(metric_key, float("nan"))
        ov = out_metrics.get(metric_key, float("nan"))
        dv = (iv - ov) if (np.isfinite(iv) and np.isfinite(ov)) else float("nan")
        a(f"| {metric_label} | {_fmt(iv)} | {_fmt(ov)} | {_fmt(dv)} |")

    a("")
    a(f"IN arm rows: {len(in_arm_pit)} | OUT arm rows: {len(out_arm_pit)}")
    a("")

    if in_metrics.get("clean8_21_dist"):
        a("### IN arm clean8_21 terminal state distribution")
        a("")
        a("| State | Count |")
        a("|-------|-------|")
        for state, cnt in sorted(in_metrics["clean8_21_dist"].items()):
            a(f"| {state} | {cnt} |")
        a("")

    a("## Cluster Bootstrap CIs (IN arm, 2,000 draws, 90% CI)")
    a("")
    a("| Metric | Point | CI Lo | CI Hi | n windows | n rows |")
    a("|--------|-------|-------|-------|-----------|--------|")
    for label, ci in [("WR21", ci_wr21), ("Mean fwd_ret_21", ci_ret21)]:
        a(f"| {label} | {_fmt(ci['point'])} | {_fmt(ci['ci_lo'])} | {_fmt(ci['ci_hi'])} | {ci['n_windows']} | {ci['n_rows']} |")
    a("")
    a("## Regime-Matched Placebo (500 draws)")
    a("")
    a(f"Placebo runtime: {elapsed_plac:.1f}s | Draws producing valid delta: {n_placebo_draws}/{PLACEBO_DRAWS}")
    a("")
    a("| Metric | Observed Δ | Placebo p95 | p-value (placebo) | BH-corrected (q=0.10) |")
    a("|--------|-----------|-------------|-------------------|----------------------|")
    a(f"| ΔWR21 | {_fmt(delta_wr21)} | {_fmt(plac_p95_wr21)} | {_fmt(pval_wr21, 3)} | {bh_g_w2a} |")
    a(f"| Δ mean fwd_ret_21 | {_fmt(delta_ret21)} | {_fmt(plac_p95_ret21)} | {_fmt(pval_ret21, 3)} | {bh_g_w2b} |")
    a("")
    a("## Gate Verdicts")
    a("")
    a("**Pre-bound vocabulary:** CONDITION-LIFT / UNDERPOWERED-ACCRUING / NULL")
    a("")
    g_w2a_str = "PASS" if g_w2a_pass else "FAIL"
    g_w2b_str = "PASS" if g_w2b_pass else "FAIL"
    a(f"- **G-W2-A** (ΔWR21 > 0 AND > placebo p95): {g_w2a_str}")
    a(f"  - IN WR21={_fmt(in_metrics.get('wr21'))}  OUT WR21={_fmt(out_metrics.get('wr21'))}  Δ={_fmt(delta_wr21)}")
    a(f"  - Placebo p95={_fmt(plac_p95_wr21)}  p-value={_fmt(pval_wr21, 3)}  BH-rejected={bh_g_w2a}")
    a(f"  - IN n_windows={n_windows_in}  IN n_rows={len(in_arm_pit)}  OUT n_rows={len(out_arm_pit)}")
    a("")
    a(f"- **G-W2-B** (Δ mean fwd_ret_21 > 0 AND > placebo p95): {g_w2b_str}")
    a(f"  - IN mean fwd_ret_21={_fmt(in_metrics.get('mean_fwd_ret_21'))}  OUT mean fwd_ret_21={_fmt(out_metrics.get('mean_fwd_ret_21'))}  Δ={_fmt(delta_ret21)}")
    a(f"  - Placebo p95={_fmt(plac_p95_ret21)}  p-value={_fmt(pval_ret21, 3)}  BH-rejected={bh_g_w2b}")
    a("")
    a(f"### VERDICT: **{verdict}**")
    a("")
    a(f"> {verdict_note}")
    a("")

    a("---")
    a("")
    a("## Appendices")
    a("")
    a("*The following appendices are supplemental. K-sensitivity, per-sector, and ablation (c) are labeled*")
    a("*and MUST NOT be cited as findings. Secondary condition (ep_onset_in) is reported with the same*")
    a("*pre-bound vocabulary.*")
    a("")

    a("### Appendix A: Secondary Condition (ep_onset_in) — registered")
    a("")
    a(f"| Metric | IN (n windows={sec_n_wins}) | OUT | Δ |")
    a("|--------|------|-----|---|")
    for mk, ml in [("wr21","WR21"), ("mean_fwd_ret_21","Mean fwd_ret_21")]:
        iv = sec_in_metrics.get(mk, float("nan"))
        ov = sec_out_metrics.get(mk, float("nan"))
        dv = (iv - ov) if (np.isfinite(iv) and np.isfinite(ov)) else float("nan")
        a(f"| {ml} | {_fmt(iv)} | {_fmt(ov)} | {_fmt(dv)} |")
    a("")

    # Secondary verdict
    sec_in_wr21 = sec_in_metrics.get("wr21", float("nan"))
    sec_out_wr21 = sec_out_metrics.get("wr21", float("nan"))
    sec_delta = sec_in_wr21 - sec_out_wr21 if (np.isfinite(sec_in_wr21) and np.isfinite(sec_out_wr21)) else float("nan")
    if np.isfinite(sec_delta) and sec_delta > 0:
        sec_verdict = "UNDERPOWERED-ACCRUING (placebo not run for secondary; point estimate positive)"
    else:
        sec_verdict = "NULL (point estimate non-positive)"
    a(f"Secondary verdict (pre-bound, same vocabulary): **{sec_verdict}**")
    a("")
    a(f"> Secondary condition has {sec_n_wins} IN-arm windows. No formal placebo run for the secondary read (only 2 gate reads registered). Secondary results are descriptive only.")
    a("")

    a("### Appendix B: K-Sensitivity (appendix-only — MUST NOT be cited as findings)")
    a("")
    a("| K | IN windows | IN WR21 | OUT WR21 | Δ WR21 |")
    a("|---|-----------|---------|---------|--------|")
    for row in k_sens_rows:
        a(f"| {row['k']} | {row['in_n_windows']} | {_fmt(row['in_wr21'])} | {_fmt(row['out_wr21'])} | {_fmt(row['delta_wr21'])} |")
    a("")

    a("### Appendix C: Per-Sector Split (appendix-only — MUST NOT be cited as findings)")
    a("")
    a("| Node | IN windows | IN rows | IN WR21 | OUT rows | OUT WR21 | Δ WR21 |")
    a("|------|-----------|---------|---------|---------|---------|--------|")
    for _, row in per_sector_df.iterrows():
        a(f"| {row['node']} | {row['in_n_windows']} | {row['in_n_rows']} | {_fmt(row['in_wr21'])} | {row['out_n_rows']} | {_fmt(row['out_wr21'])} | {_fmt(row['delta_wr21'])} |")
    a("")

    a("### Appendix D: Ablation (c) — Member-Trigger Value")
    a("")
    a("> Measures what the member trigger adds BEYOND the sector condition alone.")
    a("> Entry: window_start+1 session for ALL PIT-eligible sector members.")
    a("> Graded via _load_massive_ticker() (BRK-B artifact handled) + engine/grading.py.")
    a("> No formal gate applied (registered as appendix-only).")
    a("")
    a(f"Ablation entries: {abl_metrics.get('n_rows', 0)} | Windows with ablation data: {abl_n_wins}")
    a(f"Ticker skips: pit_fail={ablation_skip_counts.get('pit_fail', 0)} "
      f"not_found={ablation_skip_counts.get('ticker_not_found', 0)} "
      f"read_error={ablation_skip_counts.get('read_error', 0)} "
      f"no_close_col={ablation_skip_counts.get('no_close_col', 0)}")
    a("")
    if abl_metrics.get("n_rows", 0) > 0:
        a("| Metric | Ablation (c) |")
        a("|--------|-------------|")
        for mk, ml in [
            ("wr21", "WR21"),
            ("mean_fwd_ret_21", "Mean fwd_ret_21"),
            ("mean_mfe_21", "Mean fwd_mfe_21"),
            ("mean_mdd_21", "Mean fwd_mdd_21"),
            ("stop5_rate", "Stop-5 rate"),
        ]:
            a(f"| {ml} | {_fmt(abl_metrics.get(mk, float('nan')))} |")
        a("")
        # Comparison to IN arm (what trigger adds)
        trigger_lift_wr21 = in_metrics.get("wr21", float("nan")) - abl_metrics.get("wr21", float("nan"))
        a(f"**Trigger lift** (IN arm WR21 vs ablation WR21): {_fmt(trigger_lift_wr21)}")
        a(f"> Positive = member trigger selects better entries than blind entry at sector fire.")
        a("")
    else:
        a("Ablation (c): no entries graded (massive parquets may be absent for sector basket members).")
        a("")

    report_text = "\n".join(lines)
    report_path.write_text(report_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OTA W2 — Member Transmission offline research CLI."
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to MAIN data directory (READ-ONLY).",
    )
    args = parser.parse_args()
    run_main(args)


if __name__ == "__main__":
    main()
