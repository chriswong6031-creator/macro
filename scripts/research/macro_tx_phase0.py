"""L6-P0 Macro-Transmission Phase-0 study harness.

Frozen numeric authority: research/macro_tx/L6_PHASE0_PREREG.md
Adjudication context:     research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md §7, RUL-C4/C11

Mac-local, off-render, run manually:
    python scripts/research/macro_tx_phase0.py

Outputs:
    research/macro_tx/L6_PHASE0_REPORT.md
    research/macro_tx/l6_phase0_summary.json

House laws obeyed:
    - Per-axis, NEVER fused (Signal Commons R3, RUL-C4a)
    - No per-name output cells (RUL-C4b)
    - No kernel reads/writes (RUL-C4e)
    - No live flags, chips, world_state changes (RUL-C4f)
    - survivorship_biased=True stamped via vintage_stamp (prereg §1)
    - TrialLedger.log_declared_budget(12) BEFORE any outcome is computed (RUL-C11)
    - The word 'validated' does NOT appear in any output
"""
from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.trial_ledger import TrialLedger
from engine.vintage_stamp import vintage_stamp

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = _REPO_ROOT
DATA = ROOT / "data"
RESEARCH_DIR = ROOT / "research" / "macro_tx"
REPORT_PATH = RESEARCH_DIR / "L6_PHASE0_REPORT.md"
SUMMARY_PATH = RESEARCH_DIR / "l6_phase0_summary.json"
SPINE_PATH = DATA / "neuralweb" / "spine_index.parquet"
FRED = DATA / "fred"
GSPC_PATH = DATA / "yahoo" / "_GSPC.parquet"   # S&P 500 index 1927→2026 — primary strata source
SPY_PATH = DATA / "yahoo" / "SPY.parquet"       # fallback if GSPC absent (1993+)
REPLAY_PATH = DATA / "replay" / "replay_boarded.parquet"
BASKETS_PATH = DATA / "baskets" / "membership.json"

# ---------------------------------------------------------------------------
# Study constants (prereg §2 — frozen)
# ---------------------------------------------------------------------------
FAMILY = "macro_tx"
DECLARED_BUDGET = 12          # 4 axes × 3 horizons; RUL-C11
BH_Q = 0.10                   # BH FDR threshold
BLOCK_LEN = 63                # BD block length for circular block bootstrap
N_BOOTSTRAP = 2000            # bootstrap draws
PAD_BD = 5                    # ±5 BD episode padding
TRAILING_WINDOW = 756         # BD window for σ / percentile
HOSTILE_Z = 1.5               # σ threshold for shock axes
PRIMARY_HORIZON = 21          # verdict horizon
DESCRIPTIVE_HORIZONS = [5, 63]
ALL_HORIZONS = [5, 21, 63]
DRAWDOWN_STRATA = [0.0, -0.05, -0.10, -0.20]   # upper bounds (0 = [0,-5%), etc.)
MODERN_CUTOFF = pd.Timestamp("2015-01-01")

# ---------------------------------------------------------------------------
# Axis definitions (prereg §2 — frozen)
# ---------------------------------------------------------------------------
AXES = {
    "A1_rates_shock": {
        "path": FRED / "DGS10.parquet",
        "col": "us10y",
        "lag_bd": 0,
        "kind": "change_shock",
        "change_window": 20,
        "z_floor": HOSTILE_Z,
        "abs_floor": 0.25,      # +25 bp (percentage points, same unit as us10y %)
        "description": "20-BD change >=+1.5σ AND >=+25 bp",
    },
    "A2_usd_shock": {
        "path": FRED / "DTWEXBGS.parquet",
        "col": "broad_dollar",
        "lag_bd": 1,
        "kind": "return_shock",
        "change_window": 20,
        "z_floor": HOSTILE_Z,
        "abs_floor": 0.02,      # +2.0%
        "description": "20-BD return >=+1.5σ AND >=+2.0%",
    },
    "A3_credit_shock": {
        "path": FRED / "BAMLH0A0HYM2.parquet",
        "col": "hy_oas",
        "lag_bd": 1,
        "kind": "change_shock",
        "change_window": 20,
        "z_floor": HOSTILE_Z,
        "abs_floor": 0.50,      # +50 bp
        "description": "20-BD change >=+1.5σ AND >=+50 bp",
    },
    "A4_fin_conditions": {
        "path": FRED / "ANFCI.parquet",
        "col": "anfci",
        "lag_bd": 7,            # calendar days
        "kind": "level_pct",
        "change_window": None,
        "pct_floor": 80.0,      # 80th percentile
        "description": "level >= 80th percentile of trailing 756-BD window",
    },
}

# ---------------------------------------------------------------------------
# Sector basket prefix for sector map
# ---------------------------------------------------------------------------
SECTOR_BASKET_PREFIX = "us_sector_"


# ---------------------------------------------------------------------------
# Helpers: data loading
# ---------------------------------------------------------------------------

def _load_fred(path: Path, col: str) -> pd.Series | None:
    """Load a FRED parquet and return the named column as a Series with DatetimeIndex."""
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if col not in df.columns:
        log.warning("Column %s not found in %s; found: %s", col, path.name, df.columns.tolist())
        return None
    s = df[col].copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_spine_fires() -> pd.DataFrame:
    """Load track_record graded fires at horizons 5, 21, 63."""
    df = pd.read_parquet(SPINE_PATH)
    mask = (
        (df["ledger"] == "track_record")
        & (df["outcome_graded"] == True)
        & (df["horizon"].isin([5.0, 21.0, 63.0]))
    )
    fires = df[mask].copy()
    fires["as_of_dt"] = pd.to_datetime(fires["as_of"])
    fires["horizon_int"] = fires["horizon"].astype(int)
    return fires.reset_index(drop=True)


def _build_sector_map() -> dict[str, str]:
    """Build symbol->sector map from basket membership (current-date, descriptive-only)."""
    if not BASKETS_PATH.exists():
        log.warning("baskets/membership.json not found; sector map unavailable")
        return {}
    with open(BASKETS_PATH) as f:
        mb = json.load(f)
    baskets = mb.get("baskets", {})
    sector_map: dict[str, str] = {}
    for key, val in baskets.items():
        if not key.startswith(SECTOR_BASKET_PREFIX):
            continue
        sector_label = key[len(SECTOR_BASKET_PREFIX):]
        members = val.get("members", [])
        for m in members:
            ticker = m.get("ticker") if isinstance(m, dict) else m
            if ticker and m.get("removed") is None:
                sector_map[ticker] = sector_label
    return sector_map


def _load_index_close(path: Path) -> pd.Series | None:
    """Load a price parquet (GSPC or SPY) and return the close series."""
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close" in df.columns:
        s = df["close"].copy()
    elif "close_price" in df.columns:
        s = df["close_price"].copy()
    else:
        return None
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index)
    return s.sort_index().dropna()


def _load_market_close() -> tuple[pd.Series | None, str]:
    """Load S&P 500 close for drawdown stratification.

    Preference order:
      1. data/yahoo/_GSPC.parquet (1927→2026 — covers full fire tape)
      2. data/yahoo/SPY.parquet (1993+ — last-resort fallback; pre-1993 fires default
         to dd_0_5 stratum; count printed at runtime)

    Returns (series, source_label).
    """
    s = _load_index_close(GSPC_PATH)
    if s is not None:
        label = f"data/yahoo/_GSPC.parquet (S&P 500, range {s.index.min().date()} to {s.index.max().date()})"
        return s, label
    s = _load_index_close(SPY_PATH)
    if s is not None:
        label = f"data/yahoo/SPY.parquet (SPY fallback, range {s.index.min().date()} to {s.index.max().date()})"
        return s, label
    return None, "ABSENT — drawdown stratification uses single stratum (P0-DEFER quality)"


# ---------------------------------------------------------------------------
# Axis flag construction
# ---------------------------------------------------------------------------

def _build_business_day_index(series: pd.Series, fires_dt: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Build a business-day calendar spanning the series and fire dates."""
    start = min(series.index.min(), fires_dt.min())
    end = max(series.index.max(), fires_dt.max())
    return pd.bdate_range(start, end)


def _compute_hostile_flags(
    axis_name: str,
    cfg: dict,
    fires_dt: pd.Series,
) -> tuple[pd.Series | None, str, str]:
    """Compute per-business-day hostile flags for one axis.

    Returns (hostile_series, coverage_note, defer_reason).
    hostile_series: DatetimeIndex -> bool, or None if deferred.
    coverage_note: human-readable coverage window.
    defer_reason: empty string if not deferred.
    """
    path = cfg["path"]
    col = cfg["col"]
    kind = cfg["kind"]
    lag_bd = cfg["lag_bd"]
    trailing = TRAILING_WINDOW

    if not path.exists():
        return None, "", f"P0-DEFER(data): {path.name} absent from repo"

    raw = _load_fred(path, col)
    if raw is None:
        return None, "", f"P0-DEFER(data): column '{col}' absent in {path.name}"

    raw = raw.dropna()

    # Build a business-day grid to work on
    bd_index = pd.bdate_range(raw.index.min(), raw.index.max())

    if kind == "level_pct":
        # ANFCI: weekly data; lag = 7 calendar days
        # ffill to business-day grid; then shift by lag_bd calendar days
        s_bd = raw.reindex(raw.index.union(bd_index)).ffill().reindex(bd_index)
        # For calendar-day lag: shift forward by lag_bd calendar days
        s_lagged = s_bd.copy()
        if lag_bd > 0:
            s_lagged.index = s_lagged.index + pd.offsets.Day(lag_bd)
            s_lagged = s_lagged.reindex(bd_index).ffill()
        # Rolling 756-BD window percentile — vectorized via stride tricks
        pct_floor = cfg["pct_floor"]
        trailing_vals = s_lagged.dropna()
        arr = trailing_vals.values.astype(float)
        n_arr = len(arr)
        hostile = pd.Series(False, index=bd_index)
        if n_arr > trailing:
            # Build rolling window using numpy stride tricks for speed
            shape = (n_arr - trailing, trailing)
            strides = (arr.strides[0], arr.strides[0])
            windows = np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)
            # thresholds[i] = 80th pct of arr[i: i+trailing]
            thresholds = np.percentile(windows, pct_floor, axis=1)
            current = arr[trailing:]
            mask = current >= thresholds
            idx_arr = trailing_vals.index
            hostile_idx = idx_arr[trailing:][mask]
            hostile.loc[hostile.index.isin(hostile_idx)] = True
        hostile = hostile.loc[hostile.index >= raw.index.min()]
        cov_start = raw.index.min().date().isoformat()
        cov_end = raw.index.max().date().isoformat()
        coverage_note = f"{cov_start} to {cov_end} (weekly, ffill to BD)"

    else:
        # Change shock or return shock: lag is in business days
        # Reindex to business-day grid, ffill
        s_bd = raw.reindex(raw.index.union(bd_index)).ffill().reindex(bd_index)
        # Apply publication lag (BD shift)
        if lag_bd > 0:
            s_bd = s_bd.shift(lag_bd)

        window = cfg["change_window"]
        if kind == "change_shock":
            changes = s_bd.diff(window)
        elif kind == "return_shock":
            changes = s_bd.pct_change(window)
        else:
            raise ValueError(f"Unknown kind: {kind}")

        # Rolling σ of the change over trailing 756 BD
        roll_std = changes.rolling(trailing, min_periods=trailing // 2).std()

        z_floor = cfg["z_floor"]
        abs_floor = cfg["abs_floor"]
        hostile = (changes >= z_floor * roll_std) & (changes >= abs_floor)
        hostile = hostile.fillna(False)
        hostile = hostile.loc[hostile.index >= raw.index.min()]
        cov_start = raw.index.min().date().isoformat()
        cov_end = raw.index.max().date().isoformat()
        coverage_note = f"{cov_start} to {cov_end}"

    return hostile, coverage_note, ""


# ---------------------------------------------------------------------------
# Episode construction
# ---------------------------------------------------------------------------

def build_episodes(hostile: pd.Series, pad_bd: int = PAD_BD) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Build maximal hostile-run episodes padded ±pad_bd BD, then merge overlaps.

    Args:
        hostile: boolean Series on business-day DatetimeIndex
        pad_bd: padding in business days on each side of a hostile run

    Returns:
        List of (episode_start, episode_end) tuples (sorted, non-overlapping).
    """
    if hostile.empty or not hostile.any():
        return []

    bd_index = pd.bdate_range(hostile.index.min(), hostile.index.max())
    hostile_bd = hostile.reindex(bd_index, fill_value=False)
    bd_arr = bd_index.to_numpy()

    # Find maximal runs of True
    runs: list[tuple[int, int]] = []   # (start_idx, end_idx) inclusive
    in_run = False
    run_start = 0
    for i, v in enumerate(hostile_bd.values):
        if v and not in_run:
            in_run = True
            run_start = i
        elif not v and in_run:
            in_run = False
            runs.append((run_start, i - 1))
    if in_run:
        runs.append((run_start, len(hostile_bd) - 1))

    # Pad ±pad_bd and merge overlapping windows
    padded: list[tuple[int, int]] = []
    n = len(bd_arr)
    for (s, e) in runs:
        ps = max(0, s - pad_bd)
        pe = min(n - 1, e + pad_bd)
        padded.append((ps, pe))

    # Merge overlapping
    merged: list[tuple[int, int]] = []
    for ps, pe in sorted(padded):
        if merged and ps <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], pe))
        else:
            merged.append((ps, pe))

    return [(bd_arr[s].astype("datetime64[D]").astype(pd.Timestamp), bd_arr[e].astype("datetime64[D]").astype(pd.Timestamp)) for s, e in merged]


def assign_episode_arm(fire_dt: pd.Series, episodes: list[tuple[Any, Any]]) -> pd.Series:
    """Assign each fire date to 'hostile' or 'benign' based on episode membership."""
    arm = pd.Series("benign", index=fire_dt.index)
    if not episodes:
        return arm
    # Vectorized: check if each fire date falls in any episode
    fire_ts = pd.to_datetime(fire_dt)
    for ep_start, ep_end in episodes:
        # Normalize episode bounds to Timestamps for comparison
        ep_start_ts = pd.Timestamp(ep_start)
        ep_end_ts = pd.Timestamp(ep_end)
        in_ep = (fire_ts >= ep_start_ts) & (fire_ts <= ep_end_ts)
        arm[in_ep] = "hostile"
    return arm


def count_hostile_episodes_in_window(episodes: list[tuple[Any, Any]],
                                     window_start: pd.Timestamp,
                                     window_end: pd.Timestamp) -> int:
    """Count episodes whose start falls in [window_start, window_end]."""
    return sum(
        1 for s, e in episodes
        if window_start <= pd.Timestamp(s) <= window_end
    )


# ---------------------------------------------------------------------------
# Drawdown stratification
# ---------------------------------------------------------------------------

def _compute_spy_drawdown(spy_close: pd.Series) -> pd.Series:
    """Compute SPY drawdown vs trailing 252-BD high."""
    roll_high = spy_close.rolling(252, min_periods=1).max()
    return (spy_close / roll_high) - 1.0


def assign_drawdown_stratum(fire_dt: pd.Series, spy_dd: pd.Series) -> tuple[pd.Series, int]:
    """Assign each fire date to a drawdown stratum.

    Strata: [0,-5%), [-5%,-10%), [-10%,-20%), <=-20%

    Returns (strata_series, n_defaulted) where n_defaulted is the count of fire
    dates that fell before the index series start and were assigned dd_0_5 by
    default (should be ~0 when using GSPC 1927→2026).
    """
    fire_ts = pd.to_datetime(fire_dt)
    index_start = spy_dd.index.min()
    combined_idx = spy_dd.index.union(fire_ts.drop_duplicates()).drop_duplicates().sort_values()
    spy_dd_reindexed = spy_dd.reindex(combined_idx).ffill().reindex(fire_ts)
    strata = pd.Series("dd_0_5", index=fire_dt.index)
    dd = spy_dd_reindexed.values
    # NaN means no prior index data (fire predates series start) — count as defaulted
    n_defaulted = int(pd.isna(dd).sum())
    # Assign non-NaN values
    valid = ~pd.isna(dd)
    strata[valid & (dd <= -0.20)] = "dd_20plus"
    strata[valid & (dd > -0.20) & (dd <= -0.10)] = "dd_10_20"
    strata[valid & (dd > -0.10) & (dd <= -0.05)] = "dd_5_10"
    # default [0,-5%) = dd_0_5: dd > -0.05 or NaN
    return strata, n_defaulted


STRATA_LABELS = ["dd_0_5", "dd_5_10", "dd_10_20", "dd_20plus"]


# ---------------------------------------------------------------------------
# Stratified delta with harmonic-mean weights
# ---------------------------------------------------------------------------

def stratified_delta(
    df: pd.DataFrame,
    arm_col: str = "arm",
    stratum_col: str = "stratum",
    outcome_col: str = "hit",
) -> dict[str, Any]:
    """Compute stratified delta and per-stratum stats.

    w_s ∝ harmonic mean of arm counts in stratum s.
    Returns dict with 'stratified_delta', 'per_stratum', 'n_hostile', 'n_benign'.
    """
    results: dict[str, dict] = {}
    weights: list[float] = []
    weighted_deltas: list[float] = []

    for s in STRATA_LABELS:
        sub = df[df[stratum_col] == s]
        h = sub[sub[arm_col] == "hostile"][outcome_col].dropna()
        b = sub[sub[arm_col] == "benign"][outcome_col].dropna()
        n_h, n_b = len(h), len(b)
        hit_h = float(h.mean()) if n_h > 0 else np.nan
        hit_b = float(b.mean()) if n_b > 0 else np.nan
        if n_h > 0 and n_b > 0:
            delta = hit_h - hit_b
            hm = 2.0 * n_h * n_b / (n_h + n_b)  # harmonic mean
        else:
            delta = np.nan
            hm = 0.0
        results[s] = {
            "n_hostile": n_h, "n_benign": n_b,
            "hit_hostile": round(hit_h, 4) if not np.isnan(hit_h) else None,
            "hit_benign": round(hit_b, 4) if not np.isnan(hit_b) else None,
            "delta": round(delta, 4) if not np.isnan(delta) else None,
            "harmonic_mean_n": round(hm, 1),
        }
        if hm > 0 and not np.isnan(delta):
            weights.append(hm)
            weighted_deltas.append(delta * hm)

    if weights:
        total_w = sum(weights)
        strat_delta = sum(weighted_deltas) / total_w
    else:
        strat_delta = np.nan

    n_hostile_total = int((df[arm_col] == "hostile").sum())
    n_benign_total = int((df[arm_col] == "benign").sum())

    return {
        "stratified_delta": round(strat_delta, 4) if not np.isnan(strat_delta) else None,
        "per_stratum": results,
        "n_hostile": n_hostile_total,
        "n_benign": n_benign_total,
    }


# ---------------------------------------------------------------------------
# Circular block bootstrap
# ---------------------------------------------------------------------------

def circular_block_bootstrap(
    df: pd.DataFrame,
    arm_col: str = "arm",
    stratum_col: str = "stratum",
    outcome_col: str = "hit",
    date_col: str = "as_of_dt",
    block_len: int = BLOCK_LEN,
    n_draws: int = N_BOOTSTRAP,
    seed: int = 42,
) -> tuple[float, float]:
    """95% CI on the stratified delta via circular block bootstrap on calendar time.

    True multiplicity-preserving resample: for each draw, we sample n_blocks block-start
    positions WITH REPLACEMENT, build the array of selected date-indices (with repeats
    when a start is drawn twice), and for each row in df we replicate the row by the
    number of times its date-index appears in the selected set.  This preserves the
    total effective sample size ~= N (n_blocks * block_len) rather than sub-sampling
    the ~64% unique-date subset that np.unique() would produce.

    Returns (ci_lo, ci_hi).
    """
    rng = np.random.default_rng(seed)
    dates = np.sort(df[date_col].unique())
    n_dates = len(dates)
    if n_dates < block_len:
        return (np.nan, np.nan)

    # Build integer arrays: one entry per row
    date_to_idx = {d: i for i, d in enumerate(dates)}
    date_idx = df[date_col].map(date_to_idx).values.astype(np.int32)
    is_hostile = (df[arm_col] == "hostile").values.astype(np.int8)
    hit = df[outcome_col].values.astype(float)
    # Stratum: 0=dd_0_5, 1=dd_5_10, 2=dd_10_20, 3=dd_20plus
    stratum_map = {"dd_0_5": 0, "dd_5_10": 1, "dd_10_20": 2, "dd_20plus": 3}
    stratum_idx = df[stratum_col].map(stratum_map).fillna(0).values.astype(np.int8)
    n_strata = len(STRATA_LABELS)

    n_blocks = max(1, int(np.ceil(n_dates / block_len)))
    offsets = np.arange(block_len)

    # Pre-build (n_dates, block_len) circular date-index table: block_table[s, j] = (s+j)%n_dates
    starts_all = np.arange(n_dates)
    block_table = (starts_all[:, None] + offsets[None, :]) % n_dates  # (n_dates, block_len)

    # For each date index d, build a reverse lookup: row_positions[d] = array of row indices
    # This allows fast per-date row accumulation.
    row_positions: list[np.ndarray] = [np.where(date_idx == d)[0].astype(np.int32) for d in range(n_dates)]

    deltas = []
    for _ in range(n_draws):
        # Sample n_blocks block starts WITH REPLACEMENT
        starts = rng.integers(0, n_dates, size=n_blocks)
        # Build date multiplicity vector: how many times each date index is selected
        selected_date_idxs = block_table[starts].ravel()   # length = n_blocks * block_len
        # Count occurrences of each date index (may be > 1 if drawn multiple times)
        date_counts = np.bincount(selected_date_idxs, minlength=n_dates)

        # Expand rows: each row is replicated by date_counts[date_idx[row]]
        row_weights = date_counts[date_idx]   # per-row replication count

        if row_weights.sum() < 20:
            continue

        # Compute stratified delta with row weights
        weighted_deltas_val = 0.0
        total_w = 0.0
        for s in range(n_strata):
            mask_h = (is_hostile == 1) & (stratum_idx == s)
            mask_b = (is_hostile == 0) & (stratum_idx == s)
            w_h = row_weights[mask_h]
            w_b = row_weights[mask_b]
            h_hit_s = hit[mask_h]
            b_hit_s = hit[mask_b]
            n_h_eff = w_h.sum()
            n_b_eff = w_b.sum()
            if n_h_eff < 1 or n_b_eff < 1:
                continue
            mean_h = np.dot(w_h, h_hit_s) / n_h_eff
            mean_b = np.dot(w_b, b_hit_s) / n_b_eff
            hm = 2.0 * n_h_eff * n_b_eff / (n_h_eff + n_b_eff)
            weighted_deltas_val += hm * (mean_h - mean_b)
            total_w += hm

        if total_w > 0:
            deltas.append(weighted_deltas_val / total_w)

    if len(deltas) < 100:
        return (np.nan, np.nan)
    arr = np.array(deltas)
    return (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))


# ---------------------------------------------------------------------------
# BH correction
# ---------------------------------------------------------------------------

def bh_correct(p_values: list[float | None], q: float = BH_Q) -> list[bool]:
    """Benjamini-Hochberg correction. Returns list of booleans (True = reject H0)."""
    n = len(p_values)
    valid = [(i, p) for i, p in enumerate(p_values) if p is not None and not np.isnan(p)]
    rejected = [False] * n
    if not valid:
        return rejected
    valid_sorted = sorted(valid, key=lambda x: x[1])
    for rank, (i, p) in enumerate(valid_sorted, 1):
        if p <= (rank / n) * q:
            rejected[i] = True
        else:
            break  # BH: once we fail, subsequent are also failed
    # Properly apply step-up: all i up to max rejection rank
    max_reject_rank = -1
    for rank, (i, p) in enumerate(valid_sorted, 1):
        if p <= (rank / n) * q:
            max_reject_rank = rank
    for rank, (i, p) in enumerate(valid_sorted, 1):
        if rank <= max_reject_rank:
            rejected[i] = True
    return rejected


def _delta_to_pvalue(delta: float | None, ci_lo: float, ci_hi: float) -> float | None:
    """Approximate p-value from bootstrap CI using normal approximation."""
    if delta is None or np.isnan(delta):
        return None
    if np.isnan(ci_lo) or np.isnan(ci_hi):
        return None
    se_approx = (ci_hi - ci_lo) / (2 * 1.96)
    if se_approx <= 0:
        return None
    z = abs(delta) / se_approx
    from scipy import stats as _st
    return float(2 * _st.norm.sf(z))


# ---------------------------------------------------------------------------
# Per-axis analysis
# ---------------------------------------------------------------------------

def analyze_axis(
    axis_name: str,
    cfg: dict,
    fires: pd.DataFrame,
    spy_dd: pd.Series | None,
) -> dict[str, Any]:
    """Run the full per-axis analysis for all three horizons.

    Returns a dict with keys per horizon and coverage metadata.
    """
    result: dict[str, Any] = {
        "axis": axis_name,
        "description": cfg["description"],
        "deferred": False,
        "defer_reason": "",
        "coverage_note": "",
    }

    hostile_flags, coverage_note, defer_reason = _compute_hostile_flags(axis_name, cfg, fires["as_of_dt"])

    if defer_reason:
        result["deferred"] = True
        result["defer_reason"] = defer_reason
        return result

    result["coverage_note"] = coverage_note

    # Build episode list
    episodes = build_episodes(hostile_flags)
    result["episode_count_total"] = len(episodes)

    # Compute midpoint for OOS split — use the AXIS coverage window (not fires range)
    # Per prereg §3: "coverage window splits at its midpoint calendar date"
    series_start = hostile_flags.index.min()
    series_end = hostile_flags.index.max()
    midpoint = series_start + (series_end - series_start) / 2

    result["midpoint_date"] = midpoint.date().isoformat()
    result["oos_half1_end"] = midpoint.date().isoformat()
    result["oos_half2_start"] = (midpoint + pd.Timedelta(days=1)).date().isoformat()

    result["horizons"] = {}

    # Filter fires to axis coverage window (prereg: BENIGN = "within the axis's coverage window")
    fires = fires[(fires["as_of_dt"] >= series_start) & (fires["as_of_dt"] <= series_end)].copy()

    for h in ALL_HORIZONS:
        fires_h = fires[fires["horizon_int"] == h].copy()
        if fires_h.empty:
            result["horizons"][str(h)] = {"status": "P0-DEFER(no_fires)", "n_total": 0}
            continue

        # Assign arm
        fires_h["arm"] = assign_episode_arm(fires_h["as_of_dt"], episodes)

        # Assign drawdown stratum
        if spy_dd is not None:
            strata, n_defaulted = assign_drawdown_stratum(fires_h["as_of_dt"], spy_dd)
            fires_h["stratum"] = strata
            if n_defaulted > 0:
                print(f"    WARNING: {n_defaulted} fire dates predated the index series start "
                      f"and were assigned dd_0_5 stratum by default")
        else:
            fires_h["stratum"] = "dd_0_5"   # fallback: single stratum

        # Hit = outcome_excess > 0
        fires_h["hit"] = (fires_h["outcome_excess"] > 0).astype(float)

        n_hostile = int((fires_h["arm"] == "hostile").sum())
        n_benign = int((fires_h["arm"] == "benign").sum())

        # OOS halves
        half1 = fires_h[fires_h["as_of_dt"] <= midpoint].copy()
        half2 = fires_h[fires_h["as_of_dt"] > midpoint].copy()

        ep_half1 = count_hostile_episodes_in_window(episodes, series_start, midpoint)
        ep_half2 = count_hostile_episodes_in_window(episodes, midpoint, series_end)

        cell_result: dict[str, Any] = {
            "n_hostile": n_hostile,
            "n_benign": n_benign,
            "n_total": len(fires_h),
            "episode_count_half1": ep_half1,
            "episode_count_half2": ep_half2,
        }

        # Floor checks per half
        floor_ok_h1 = (
            (half1["arm"] == "hostile").sum() >= 300
            and (half1["arm"] == "benign").sum() >= 300
            and ep_half1 >= 8
        )
        floor_ok_h2 = (
            (half2["arm"] == "hostile").sum() >= 300
            and (half2["arm"] == "benign").sum() >= 300
            and ep_half2 >= 8
        )

        cell_result["floor_ok_half1"] = bool(floor_ok_h1)
        cell_result["floor_ok_half2"] = bool(floor_ok_h2)
        cell_result["n_hostile_half1"] = int((half1["arm"] == "hostile").sum())
        cell_result["n_benign_half1"] = int((half1["arm"] == "benign").sum())
        cell_result["n_hostile_half2"] = int((half2["arm"] == "hostile").sum())
        cell_result["n_benign_half2"] = int((half2["arm"] == "benign").sum())

        if not floor_ok_h1 or not floor_ok_h2:
            missing = []
            if not floor_ok_h1:
                missing.append(f"half1(ep={ep_half1},h={int((half1['arm']=='hostile').sum())},b={int((half1['arm']=='benign').sum())})")
            if not floor_ok_h2:
                missing.append(f"half2(ep={ep_half2},h={int((half2['arm']=='hostile').sum())},b={int((half2['arm']=='benign').sum())})")
            cell_result["status"] = f"P0-DEFER(floor) — {'; '.join(missing)}"
            cell_result["stratified_delta"] = None
            cell_result["ci_lo"] = None
            cell_result["ci_hi"] = None
            result["horizons"][str(h)] = cell_result
            continue

        # Full sample stratified delta
        full_res = stratified_delta(fires_h)
        cell_result.update({
            "stratified_delta": full_res["stratified_delta"],
            "per_stratum": full_res["per_stratum"],
        })

        # CIs on full sample
        ci_lo, ci_hi = circular_block_bootstrap(fires_h)
        cell_result["ci_lo"] = round(ci_lo, 4) if not np.isnan(ci_lo) else None
        cell_result["ci_hi"] = round(ci_hi, 4) if not np.isnan(ci_hi) else None

        # Half-sample analyses
        for half_label, half_df in [("half1", half1), ("half2", half2)]:
            if len(half_df) < 20:
                cell_result[f"stratified_delta_{half_label}"] = None
                cell_result[f"ci_lo_{half_label}"] = None
                cell_result[f"ci_hi_{half_label}"] = None
                continue
            h_res = stratified_delta(half_df)
            ci_lo_h, ci_hi_h = circular_block_bootstrap(half_df)
            cell_result[f"stratified_delta_{half_label}"] = h_res["stratified_delta"]
            cell_result[f"ci_lo_{half_label}"] = round(ci_lo_h, 4) if not np.isnan(ci_lo_h) else None
            cell_result[f"ci_hi_{half_label}"] = round(ci_hi_h, 4) if not np.isnan(ci_hi_h) else None

        # Modern cohort sensitivity (>=2015)
        fires_modern = fires_h[fires_h["as_of_dt"] >= MODERN_CUTOFF].copy()
        if len(fires_modern) >= 30:
            mod_res = stratified_delta(fires_modern)
            cell_result["modern_cohort_delta"] = mod_res["stratified_delta"]
            cell_result["modern_cohort_n_hostile"] = mod_res["n_hostile"]
            cell_result["modern_cohort_n_benign"] = mod_res["n_benign"]
        else:
            cell_result["modern_cohort_delta"] = None
            cell_result["modern_cohort_n"] = len(fires_modern)

        # Family composition (spine `family` column: buy/sell/cut/rebuy)
        # Descriptive only — the pooled delta may reflect composition mix, not pure transmission.
        if "family" in fires_h.columns:
            fam_comp: dict[str, Any] = {}
            families = sorted(fires_h["family"].dropna().unique().tolist())
            for fam in families:
                fam_df = fires_h[fires_h["family"] == fam]
                n_h_fam = int((fam_df["arm"] == "hostile").sum())
                n_b_fam = int((fam_df["arm"] == "benign").sum())
                n_hostile_arm_total = int((fires_h["arm"] == "hostile").sum())
                n_benign_arm_total = int((fires_h["arm"] == "benign").sum())
                hostile_share = round(n_h_fam / max(1, n_hostile_arm_total), 4)
                benign_share = round(n_b_fam / max(1, n_benign_arm_total), 4)
                # Within-family delta (unstratified — for descriptive family decomposition)
                h_hits = fam_df[fam_df["arm"] == "hostile"]["hit"]
                b_hits = fam_df[fam_df["arm"] == "benign"]["hit"]
                within_delta = None
                if len(h_hits) > 0 and len(b_hits) > 0:
                    within_delta = round(float(h_hits.mean() - b_hits.mean()), 4)
                fam_comp[fam] = {
                    "n_hostile": n_h_fam,
                    "n_benign": n_b_fam,
                    "hostile_share": hostile_share,
                    "benign_share": benign_share,
                    "within_delta": within_delta,
                }
            cell_result["family_composition"] = fam_comp

        result["horizons"][str(h)] = cell_result

    return result


# ---------------------------------------------------------------------------
# BH pass and verdict assignment
# ---------------------------------------------------------------------------

def _ci_excludes_zero(ci_lo, ci_hi) -> bool:
    if ci_lo is None or ci_hi is None:
        return False
    if np.isnan(ci_lo) or np.isnan(ci_hi):
        return False
    return ci_lo > 0 or ci_hi < 0


def assign_verdicts(axis_results: dict[str, dict]) -> dict[str, dict]:
    """Apply BH q=0.10 across 4 primary h21 cells, assign PASS/FAIL/DEFER per axis."""

    # Collect h21 cells
    h21_cells = []
    for axis_name, res in axis_results.items():
        if res.get("deferred"):
            h21_cells.append((axis_name, None))
            continue
        h_res = res.get("horizons", {}).get("21", {})
        status = h_res.get("status", "")
        if "P0-DEFER" in status:
            h21_cells.append((axis_name, None))
        else:
            delta = h_res.get("stratified_delta")
            ci_lo = h_res.get("ci_lo_half1")
            ci_hi = h_res.get("ci_hi_half1")
            ci_lo2 = h_res.get("ci_lo_half2")
            ci_hi2 = h_res.get("ci_hi_half2")
            h21_cells.append((axis_name, {
                "delta": delta,
                "ci_lo_h1": ci_lo, "ci_hi_h1": ci_hi,
                "ci_lo_h2": ci_lo2, "ci_hi_h2": ci_hi2,
            }))

    # Build p-values for BH using FULL-sample CI paired with full-sample delta.
    # (Fix: previously paired full delta with half-sample CI, understating SE.)
    p_values = []
    for axis_name_i, cell in h21_cells:
        if cell is None:
            p_values.append(None)
        else:
            d = cell["delta"]
            # Use the full-sample bootstrap CI (ci_lo / ci_hi stored directly on h21 cell)
            h21_full = axis_results[axis_name_i].get("horizons", {}).get("21", {})
            ci_lo_full = h21_full.get("ci_lo")
            ci_hi_full = h21_full.get("ci_hi")
            p = _delta_to_pvalue(
                d,
                ci_lo_full if ci_lo_full is not None else np.nan,
                ci_hi_full if ci_hi_full is not None else np.nan,
            )
            p_values.append(p)

    bh_rejected = bh_correct(p_values)

    for i, (axis_name, cell) in enumerate(h21_cells):
        res = axis_results[axis_name]
        if cell is None:
            res["verdict_h21"] = "P0-DEFER"
            continue
        d = cell["delta"]
        h1_ok = _ci_excludes_zero(cell.get("ci_lo_h1"), cell.get("ci_hi_h1"))
        h2_ok = _ci_excludes_zero(cell.get("ci_lo_h2"), cell.get("ci_hi_h2"))
        d1 = axis_results[axis_name]["horizons"]["21"].get("stratified_delta_half1")
        d2 = axis_results[axis_name]["horizons"]["21"].get("stratified_delta_half2")
        sign_stable = (d1 is not None and d2 is not None and
                       np.sign(d1) == np.sign(d2) and np.sign(d1) != 0)
        both_halves_ok = h1_ok and h2_ok
        bh_ok = bh_rejected[i]

        if d is None:
            res["verdict_h21"] = "P0-DEFER"
        elif bh_ok and sign_stable and both_halves_ok:
            res["verdict_h21"] = "P0-PASS"
        else:
            reasons = []
            if not bh_ok:
                reasons.append("BH_fail")
            if not sign_stable:
                reasons.append("sign_unstable")
            if not both_halves_ok:
                reasons.append("CI_includes_0_in_a_half")
            res["verdict_h21"] = f"P0-FAIL ({', '.join(reasons)})"

    return axis_results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt(v, digits: int = 4) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def generate_report(
    axis_results: dict[str, dict],
    fires_total: int,
    spy_source: str,
    usd_source: str,
    cumulative_macro_tx_count: int,
    run_date: str,
) -> str:
    lines: list[str] = []
    lines.append("# L6-P0 Macro-Transmission Phase-0 Report")
    lines.append("")
    lines.append(f"**Run date:** {run_date}  ")
    lines.append(f"**Prereg:** research/macro_tx/L6_PHASE0_PREREG.md (frozen 2026-07-06)  ")
    lines.append(f"**Fire tape:** spine_index.parquet track_record, outcome_graded=True, horizons 5/21/63  ")
    lines.append(f"**Verdict horizon:** h21  ")
    lines.append(f"**Cumulative macro_tx trial count:** {cumulative_macro_tx_count}  ")
    lines.append(f"**S&P 500 drawdown source:** {spy_source}  ")
    lines.append(f"**USD series source:** {usd_source}  ")
    lines.append("")

    # In plain English box
    lines.append("---")
    lines.append("")
    lines.append("## In plain English")
    lines.append("")
    lines.append("> **What is being measured:** The outcome metric `hit` equals 1 when the signal "
                 "achieved *any* positive favorable excursion versus the benchmark within 21 sessions "
                 "of firing (i.e., `outcome_excess > 0`). The metric is floored at zero — it is an "
                 "achieved-favorable-excursion indicator, not a signed return or a 'beat the market' "
                 "measure. The base rate across all fires is approximately 88% (roughly 12% of fires "
                 "never achieved any favorable excursion). The delta reported here measures how much "
                 "MORE OFTEN hostile-window fires FAIL to achieve any favorable excursion compared "
                 "to benign-window fires. A negative delta means hostile fires reach favorable "
                 "excursion less often than benign fires.  "
                 "\n>\n> "
                 "**What is being asked:** When a macro condition is hostile at the time a signal "
                 "fires — when rates are rising fast, the dollar is surging, credit spreads are "
                 "blowing out, or financial conditions are tight — does the signal's favorable "
                 "excursion rate change versus normal times? Each macro axis is tested separately "
                 "(never combined). The verdict requires the hostile-vs-benign gap to be stable "
                 "across two time periods AND the bootstrap confidence interval to exclude zero in "
                 "both periods.  "
                 "\n>\n> "
                 "**Family composition caveat:** The spine fires are drawn from four signal families "
                 "(sell, buy, cut, rebuy) in unequal proportions. The hostile arm may have a "
                 "different mix of these families than the benign arm. The pooled stratified delta "
                 "is NOT decomposed for family mix — part of the observed delta may reflect "
                 "composition differences rather than macro transmission. Per-family within-deltas "
                 "are reported descriptively; treat them as hypothesis-generating, not as verdicts.  "
                 "\n>\n> "
                 "Any axis that passes this gate re-opens the question of whether macro conditioning "
                 "should be wired into the signal engine (subject to further approval and a separate "
                 "masterplan). A fail means the gap is not reliably there. Either outcome is "
                 "informative and is printed honestly.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Achieved counts section (printed BEFORE results per prereg §2 law)
    lines.append("## Achieved counts (printed before outcome statistics)")
    lines.append("")
    lines.append(f"Total fires loaded (track_record, graded, h5+h21+h63): {fires_total:,}")
    lines.append("")
    lines.append("| Axis | Coverage window | Total episodes | h21 hostile fires | h21 benign fires | Half1 ep | Half2 ep |")
    lines.append("|---|---|---|---|---|---|---|")

    for axis_name, res in axis_results.items():
        if res.get("deferred"):
            lines.append(f"| {axis_name} | — | — | — | — | — | — |")
            continue
        cov = res.get("coverage_note", "—")
        ep_total = res.get("episode_count_total", 0)
        h21_res = res.get("horizons", {}).get("21", {})
        n_h = h21_res.get("n_hostile", "—")
        n_b = h21_res.get("n_benign", "—")
        ep_h1 = h21_res.get("episode_count_half1", "—")
        ep_h2 = h21_res.get("episode_count_half2", "—")
        lines.append(f"| {axis_name} | {cov} | {ep_total} | {n_h} | {n_b} | {ep_h1} | {ep_h2} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-axis results (all 12 cells)
    lines.append("## Per-axis results (all 12 cells including nulls and defers)")
    lines.append("")

    for axis_name, res in axis_results.items():
        lines.append(f"### {axis_name}")
        lines.append(f"**Description:** {res.get('description', '—')}  ")

        if res.get("deferred"):
            lines.append(f"**Status:** {res.get('defer_reason', 'P0-DEFER')}  ")
            lines.append("")
            continue

        lines.append(f"**Coverage:** {res.get('coverage_note', '—')}  ")
        lines.append(f"**Total episodes:** {res.get('episode_count_total', 0)}  ")
        lines.append(f"**OOS midpoint:** {res.get('midpoint_date', '—')}  ")
        verdict = res.get("verdict_h21", "—")
        lines.append(f"**Verdict (h21):** {verdict}  ")
        lines.append("")

        lines.append("#### Cell table (all 3 horizons)")
        lines.append("")
        lines.append("| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")

        for h in ALL_HORIZONS:
            h_res = res.get("horizons", {}).get(str(h), {})
            if not h_res:
                lines.append(f"| h{h} | — | — | — | — | — | — | — | — | — | — | no data |")
                continue
            status = h_res.get("status", "computed")
            n_h_val = h_res.get("n_hostile", "—")
            n_b_val = h_res.get("n_benign", "—")
            delta = _fmt(h_res.get("stratified_delta"))
            ci_lo = _fmt(h_res.get("ci_lo"))
            ci_hi = _fmt(h_res.get("ci_hi"))
            d_h1 = _fmt(h_res.get("stratified_delta_half1"))
            ci_h1 = f"[{_fmt(h_res.get('ci_lo_half1'))}, {_fmt(h_res.get('ci_hi_half1'))}]"
            d_h2 = _fmt(h_res.get("stratified_delta_half2"))
            ci_h2 = f"[{_fmt(h_res.get('ci_lo_half2'))}, {_fmt(h_res.get('ci_hi_half2'))}]"
            floor_ok = h_res.get("floor_ok_half1", "—") and h_res.get("floor_ok_half2", "—")
            label = "h21(verdict)" if h == 21 else f"h{h}(descriptive)"
            lines.append(f"| {label} | {n_h_val} | {n_b_val} | {delta} | {ci_lo} | {ci_hi} | {d_h1} | {ci_h1} | {d_h2} | {ci_h2} | {floor_ok} | {status} |")

        # Per-stratum table for h21
        h21_res = res.get("horizons", {}).get("21", {})
        if h21_res and "per_stratum" in h21_res:
            lines.append("")
            lines.append("#### Per-stratum table (h21)")
            lines.append("")
            lines.append("| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |")
            lines.append("|---|---|---|---|---|---|---|")
            for s in STRATA_LABELS:
                st = h21_res["per_stratum"].get(s, {})
                lines.append(f"| {s} | {st.get('n_hostile','—')} | {st.get('n_benign','—')} | "
                              f"{_fmt(st.get('hit_hostile'))} | {_fmt(st.get('hit_benign'))} | "
                              f"{_fmt(st.get('delta'))} | {_fmt(st.get('harmonic_mean_n'), 1)} |")

        # Modern cohort sensitivity
        h21_res = res.get("horizons", {}).get("21", {})
        if h21_res and "modern_cohort_delta" in h21_res:
            lines.append("")
            lines.append("#### Modern cohort sensitivity (>=2015, h21)")
            lines.append("")
            mod_delta = _fmt(h21_res.get("modern_cohort_delta"))
            mod_n_h = h21_res.get("modern_cohort_n_hostile", "—")
            mod_n_b = h21_res.get("modern_cohort_n_benign", "—")
            lines.append(f"Modern delta: {mod_delta} (hostile n={mod_n_h}, benign n={mod_n_b})")

        # Family composition table (h21)
        h21_res = res.get("horizons", {}).get("21", {})
        fam_comp = h21_res.get("family_composition") if h21_res else None
        if fam_comp:
            lines.append("")
            lines.append("#### Family composition and within-family deltas (h21, descriptive)")
            lines.append("")
            lines.append("| Family | N hostile | N benign | Hostile share | Benign share | Within-family delta |")
            lines.append("|---|---|---|---|---|---|")
            for fam, fdata in sorted(fam_comp.items()):
                lines.append(
                    f"| {fam} | {fdata.get('n_hostile','—')} | {fdata.get('n_benign','—')} | "
                    f"{_fmt(fdata.get('hostile_share'))} | {_fmt(fdata.get('benign_share'))} | "
                    f"{_fmt(fdata.get('within_delta'))} |"
                )
            lines.append("")
            lines.append(
                "> **Composition caveat:** The hostile and benign arms may have different mixes of "
                "signal families (sell/buy/cut/rebuy). The pooled stratified delta above is not "
                "decomposed for this composition effect — part of the observed delta may reflect "
                "which families fire more often during hostile windows, not pure macro transmission. "
                "Within-family deltas are descriptive only and do not carry verdict status."
            )

        lines.append("")

    # Summary table
    lines.append("---")
    lines.append("")
    lines.append("## Summary: h21 verdict per axis")
    lines.append("")
    lines.append("| Axis | Verdict | Stratified delta | 95% CI | H1 CI excludes 0 | H2 CI excludes 0 |")
    lines.append("|---|---|---|---|---|---|")

    for axis_name, res in axis_results.items():
        verdict = res.get("verdict_h21", "—")
        h21_res = res.get("horizons", {}).get("21", {})
        delta = _fmt(h21_res.get("stratified_delta") if h21_res else None)
        ci_lo_v = h21_res.get("ci_lo") if h21_res else None
        ci_hi_v = h21_res.get("ci_hi") if h21_res else None
        ci_str = f"[{_fmt(ci_lo_v)}, {_fmt(ci_hi_v)}]" if h21_res else "—"
        h1_excl = _ci_excludes_zero(h21_res.get("ci_lo_half1"), h21_res.get("ci_hi_half1")) if h21_res else False
        h2_excl = _ci_excludes_zero(h21_res.get("ci_lo_half2"), h21_res.get("ci_hi_half2")) if h21_res else False
        lines.append(f"| {axis_name} | {verdict} | {delta} | {ci_str} | {h1_excl} | {h2_excl} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Pre-committed branches")
    lines.append("")
    lines.append("- **P0-PASS(axis):** that axis re-opens the L6 charter question at the docket (two-lobe cap + "
                 "separate masterplan+prereg still required; no live flag, chip, world_state key, or per-name "
                 "output ships from this study).")
    lines.append("- **P0-FAIL:** null printed; L6 stays gated; noisy-sector precedent stands as honest ceiling.")
    lines.append("- **P0-DEFER:** floors or data unmet; achieved counts printed above with come-back condition.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Opus stats review required before verdict is acted on. Fable adjudicates. "
                 "This report is a contamination surface: any later prereg on this tape carries "
                 "`derived_from_surface: macro_tx_phase0_v1`.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    run_date = datetime.now(tz=timezone.utc).date().isoformat()
    print(f"\n=== L6-P0 Macro-Transmission Phase-0 ===")
    print(f"Run date: {run_date}")

    # STEP 1: Register budget BEFORE any outcome is computed (RUL-C11)
    led = TrialLedger(family=FAMILY)
    led.log_declared_budget(
        DECLARED_BUDGET,
        family=FAMILY,
        reason="L6-P0: 4 axes × 3 horizons (h21=verdict cells, h5/h63=descriptive but budget-counted per RUL-C11)",
    )
    cumulative_macro_tx = led.effective_n(FAMILY)
    print(f"Registration: TrialLedger budget declared: {DECLARED_BUDGET} for family='{FAMILY}'")
    print(f"Cumulative macro_tx trial count: {cumulative_macro_tx}")

    # STEP 2: Load fires
    print("\nLoading fire tape...")
    fires = _load_spine_fires()
    fires_total = len(fires)
    print(f"  Track_record graded fires (h5+h21+h63): {fires_total:,}")
    print(f"  Date range: {fires['as_of_dt'].min().date()} -> {fires['as_of_dt'].max().date()}")

    # STEP 3: Sector map (descriptive only — no verdict at sector grain in P0)
    print("\nBuilding sector map (descriptive, current-date)...")
    sector_map = _build_sector_map()
    print(f"  Sector map: {len(sector_map)} tickers mapped")
    if sector_map:
        fires["sector"] = fires["symbol"].map(sector_map)
        fires["sector"] = fires["sector"].fillna("unknown")
        sector_coverage = (fires["sector"] != "unknown").mean()
        print(f"  Sector coverage: {sector_coverage:.1%} (declared anachronism — map applied to historical fires)")
    else:
        fires["sector"] = "unknown"

    # STEP 4: S&P 500 close for drawdown stratification (prefer GSPC 1927→2026 over SPY 1993+)
    print("\nLoading S&P 500 close for drawdown stratification...")
    spy_close, spy_source = _load_market_close()
    if spy_close is not None:
        spy_dd = _compute_spy_drawdown(spy_close)
        print(f"  Source: {spy_source}")
    else:
        spy_dd = None
        print(f"  WARNING: {spy_source}")

    # STEP 5: Check USD series
    usd_path = FRED / "DTWEXBGS.parquet"
    if usd_path.exists():
        usd_source = "data/fred/DTWEXBGS.parquet (broad_dollar, FRED)"
        print(f"\nUSD series: {usd_source}")
    else:
        usd_source = "DTWEXBGS ABSENT — A2 will be P0-DEFER(data)"
        print(f"\nUSD series: {usd_source}")

    # STEP 6: Check replay tape
    if REPLAY_PATH.exists():
        print(f"\nSensitivity tape: {REPLAY_PATH} (present)")
    else:
        print(f"\nsensitivity tape absent on this host")

    # STEP 7: Print per-axis coverage BEFORE any outcome statistics
    print("\n--- Per-axis coverage (computed before outcome statistics) ---")
    for axis_name, cfg in AXES.items():
        if cfg["path"].exists():
            raw = _load_fred(cfg["path"], cfg["col"])
            if raw is not None:
                print(f"  {axis_name}: {raw.dropna().index.min().date()} -> {raw.dropna().index.max().date()}")
            else:
                print(f"  {axis_name}: file exists but column '{cfg['col']}' not found")
        else:
            print(f"  {axis_name}: {cfg['path'].name} ABSENT")

    # STEP 8: Run per-axis analysis
    print("\n--- Running per-axis analysis ---")
    axis_results: dict[str, dict] = {}

    for axis_name, cfg in AXES.items():
        print(f"\n  Analyzing {axis_name}...")
        res = analyze_axis(axis_name, cfg, fires, spy_dd)
        axis_results[axis_name] = res

        if res.get("deferred"):
            print(f"    {res['defer_reason']}")
            continue

        print(f"    Coverage: {res['coverage_note']}")
        print(f"    Total episodes: {res.get('episode_count_total', 0)}")

        for h in ALL_HORIZONS:
            h_res = res.get("horizons", {}).get(str(h), {})
            if not h_res:
                print(f"    h{h}: no data")
                continue
            status = h_res.get("status", "computed")
            if "P0-DEFER" in status:
                print(f"    h{h}: {status}")
            else:
                n_h = h_res.get("n_hostile", "?")
                n_b = h_res.get("n_benign", "?")
                delta = h_res.get("stratified_delta")
                print(f"    h{h}: hostile={n_h}, benign={n_b}, strat_delta={_fmt(delta)}")

    # STEP 9: Assign verdicts with BH correction
    print("\n--- Assigning verdicts (BH q=0.10) ---")
    axis_results = assign_verdicts(axis_results)

    for axis_name, res in axis_results.items():
        verdict = res.get("verdict_h21", "—")
        print(f"  {axis_name}: {verdict}")

    # STEP 10: Generate report
    print("\nGenerating report...")
    report_text = generate_report(
        axis_results,
        fires_total=fires_total,
        spy_source=spy_source,
        usd_source=usd_source,
        cumulative_macro_tx_count=cumulative_macro_tx,
        run_date=run_date,
    )

    # Verify 'validated' never appears
    assert "validated" not in report_text.lower(), "VIOLATION: 'validated' found in report text"

    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"  Report written: {REPORT_PATH}")

    # STEP 11: Generate summary JSON with vintage stamp
    stamp = vintage_stamp(
        price_plane_id="spine_index_track_record",
        adjustment_mode="outcome_excess_graded",
        universe_as_of=run_date,
        frame="track_record_historical",
        survivorship_biased=True,   # prereg §1: old eras survivorship-exposed
        coverage_frac=1.0,          # all loaded fires are graded (pre-filtered); no separate coverage fraction meaningful here
        dead_name_coverage_pct=None,
        era_law_cohort="track_record_all_eras",
    )

    summary: dict[str, Any] = {
        "study_id": "macro_tx_phase0_v1",
        "run_date": run_date,
        "prereg": "research/macro_tx/L6_PHASE0_PREREG.md",
        "family": FAMILY,
        "declared_budget": DECLARED_BUDGET,
        "cumulative_macro_tx_trial_count": cumulative_macro_tx,
        "fires_total": fires_total,
        "spy_source": spy_source,
        "usd_source": usd_source,
        "derived_from_surface": None,
        "contamination_surface": "macro_tx_phase0_v1",
        "axes": {},
        "vintage_stamp": stamp,
    }

    for axis_name, res in axis_results.items():
        summary["axes"][axis_name] = {
            "deferred": res.get("deferred", False),
            "defer_reason": res.get("defer_reason", ""),
            "verdict_h21": res.get("verdict_h21", "—"),
            "coverage_note": res.get("coverage_note", ""),
            "episode_count_total": res.get("episode_count_total"),
            "h21_stratified_delta": res.get("horizons", {}).get("21", {}).get("stratified_delta"),
            "h21_ci_lo": res.get("horizons", {}).get("21", {}).get("ci_lo"),
            "h21_ci_hi": res.get("horizons", {}).get("21", {}).get("ci_hi"),
        }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"  Summary JSON written: {SUMMARY_PATH}")

    print("\n=== COMPLETE ===")
    print(f"Cumulative macro_tx trial count: {cumulative_macro_tx}")
    print("\nAxis verdicts (h21):")
    for axis_name, res in axis_results.items():
        print(f"  {axis_name}: {res.get('verdict_h21', '—')}")


if __name__ == "__main__":
    main()
