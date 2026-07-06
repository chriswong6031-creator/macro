"""scripts/research/run_disp_gate_1.py — DISP-GATE-1 harness.

RUL-F3.6: Builds the descriptive readout for L3 dispersion regime gate.
Bound by: research/dispersion/L3_PREREG.md (frozen design)
          research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md §6.2
          research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md RUL-F3.6

House laws:
- The word "validated" must NOT appear in any output (CI-enforced epistemics law).
- Nulls are printed, not hidden. DEFER is a valid printed outcome.
- gross_mult_live is and remains 1.0 (HARD CONSTRAINT, RUL-F3.7).
- This is a descriptive-only batch; no verdict gate is evaluated here.
- Off-render-path research compute; never runs in CI build.

Fire population: replay_boarded.parquet verdict_type='fire' AND verdict_grade=True
PIT dispersion: reconstructed expanding-window rolling-21d-mean CSD from the
    breadth/_closes_deep.parquet panel (same universe + tier priority-dedup as
    build_dispersion_regime.py, held fixed at every historical date).
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

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from lib import config  # noqa: E402

log = logging.getLogger("run_disp_gate_1")

# ---------------------------------------------------------------------------
# Constants (frozen per prereg + RUL-F3.6)
# ---------------------------------------------------------------------------
_HI, _LO = 0.66, 0.33          # percentile tercile thresholds — match engine/dispersion.py
_MIN_PRIOR_BARS = 252           # fires excluded if panel has < 252 bars before fire date
_MIN_CLUSTERS_FOR_CI = 25       # arms below this floor: descriptive only, no bootstrap CIs
_N_BOOTSTRAP = 1000             # bootstrap resample count for cluster CIs
_RNG_SEED = 42

# SPY 21d return terciles per prereg: <-5%, -5%..+5%, >+5%
_SPY_T1 = -0.05
_SPY_T2 = 0.05

# Stop5 threshold: drawdown from entry >= 5% at any point in 21d window
_STOP5_THRESH = -0.05
# Dead money threshold: |ret_21d| < 2%
_DEAD_MONEY_THRESH = 0.02

# Output paths
_SUMMARY_OUT = _REPO_ROOT / "data" / "dispersion" / "disp_gate_1_summary.json"
_REPORT_OUT = _REPO_ROOT / "research" / "dispersion" / "DISP_GATE_1_REPORT.md"

# Data paths — main checkout (deep store; gitignored heavy data)
_MAIN_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
_REPLAY_PATH = _MAIN_DATA / "replay" / "replay_boarded.parquet"
_BREADTH_DEEP = _MAIN_DATA / "breadth" / "_closes_deep.parquet"
_MIDCAP_CACHE = _MAIN_DATA / "midcap_breadth" / "_closes_cache.parquet"
_SMALLCAP_CACHE = _MAIN_DATA / "smallcap_breadth" / "_closes_cache.parquet"
_SPY_PATH = _MAIN_DATA / "massive_stock_day" / "SPY.parquet"

# ---------------------------------------------------------------------------
# Cell definition hashes (for registration governor)
# ---------------------------------------------------------------------------

def _cell_hash(state: str, basis: str) -> str:
    """Stable SHA-256 hash of a frozen cell definition dict.

    The cell is uniquely identified by (regime_state, basis, outcome_metrics,
    time_exit_days, stop5_thresh, dead_money_thresh, thresholds).
    This is documented here as the hash method for the registry.
    """
    cell_def = {
        "experiment": "disp_gate_v1",
        "regime_state": state,
        "basis": basis,
        "time_exit_days": 21,
        "stop5_thresh_pct": -5.0,
        "dead_money_thresh_pct": 2.0,
        "hi_pctile": 0.66,
        "lo_pctile": 0.33,
        "min_prior_bars": 252,
        "outcome_metrics": ["stop5", "dead_money"],
        "covariate_split": "SPY_21d_ret_terciles",
        "vol_covariate_split": "SPY_21d_realized_vol_terciles",
    }
    raw = json.dumps(cell_def, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cell_hashes() -> list[str]:
    """Return the 6 cell hashes for the registry (3 states × 2 bases)."""
    hashes = []
    for state in ("lean_in", "neutral", "lean_out"):
        for basis in ("expanding", "trailing_252"):
            hashes.append(_cell_hash(state, basis))
    return sorted(hashes)


# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------

def _load_panel() -> pd.DataFrame:
    """Load and merge the broad-universe close panel.

    Priority order: breadth (deep store) → midcap_breadth cache → smallcap_breadth cache.
    A ticker taken from an earlier tier is NOT re-added from a later one.
    This matches build_dispersion_regime._load_closes() universe construction.

    Uses _closes_deep for breadth (full history 1962→present) and _closes_cache
    for midcap/smallcap (shorter history, from their cache start date).
    """
    frame: pd.DataFrame | None = None

    # Tier 1: breadth deep store (full history)
    if _BREADTH_DEEP.exists():
        d = pd.read_parquet(_BREADTH_DEEP)
        d = d.loc[:, ~d.columns.duplicated()]
        frame = d
        log.info("Loaded breadth deep store: %d dates, %d tickers, range %s..%s",
                 len(d), d.shape[1], d.index.min().date(), d.index.max().date())
    else:
        log.warning("breadth/_closes_deep.parquet not found — panel will be empty")

    # Tier 2: midcap breadth cache
    for cache_path, label in [(_MIDCAP_CACHE, "midcap_breadth"), (_SMALLCAP_CACHE, "smallcap_breadth")]:
        if cache_path.exists():
            try:
                d = pd.read_parquet(cache_path)
                d = d.loc[:, ~d.columns.duplicated()]
                if frame is None:
                    frame = d
                else:
                    new_cols = [c for c in d.columns if c not in frame.columns]
                    if new_cols:
                        frame = frame.join(d[new_cols], how="outer")
                log.info("Merged %s cache: +%d new tickers, range %s..%s",
                         label, len(new_cols) if 'new_cols' in dir() else 0,
                         d.index.min().date(), d.index.max().date())
            except Exception as e:  # noqa: BLE001
                log.warning("%s cache unreadable (%s) — skipped", label, e)

    if frame is None:
        return pd.DataFrame()

    frame = frame.sort_index()
    frame = frame.loc[:, ~frame.columns.duplicated()]
    return frame


def _load_spy_closes() -> pd.Series:
    """Load SPY close series from massive_stock_day store."""
    if not _SPY_PATH.exists():
        log.warning("SPY.parquet not found at %s", _SPY_PATH)
        return pd.Series(dtype=float)
    spy = pd.read_parquet(_SPY_PATH)
    if "close" not in spy.columns:
        log.warning("SPY.parquet has no 'close' column: %s", spy.columns.tolist())
        return pd.Series(dtype=float)
    return spy["close"].sort_index()


# ---------------------------------------------------------------------------
# PIT dispersion reconstruction
# ---------------------------------------------------------------------------

def _assign_regime_pit(
    closes: pd.DataFrame,
    fire_date: pd.Timestamp,
    basis: str = "expanding",
) -> dict | None:
    """Compute dispersion regime for a single fire_date, PIT-correct.

    Returns dict with keys: state, disp_pctile, disp_ppt, n_names_at_date
    or None if insufficient data.

    basis='expanding': matches engine/dispersion.assess() expanding-window pctile.
    basis='trailing_252': sensitivity check using fixed 252-day rolling window.
    """
    # Slice panel up to and including fire_date (PIT: no look-ahead)
    available = closes.loc[:fire_date]
    if available.empty:
        return None

    # Per-date name count at fire_date
    row = available.iloc[-1]
    n_names_at_date = int(row.notna().sum())

    # Require >= min_prior_bars rows before this date (feasibility gate)
    if len(available) < _MIN_PRIOR_BARS:
        return None

    # Compute CSD series (rolling-21d-mean cross-sectional std)
    returns = available.pct_change(fill_method=None)
    csd = returns.std(axis=1)
    hist = csd.rolling(21, min_periods=10).mean()
    h = hist.dropna()

    if len(h) < 60:
        return None

    # Current dispersion = last-21d mean CSD (PIT)
    disp = float(csd.iloc[-21:].mean()) if len(csd) >= 21 else float(csd.mean())
    disp_ppt = round(100 * disp, 2)

    # Percentile basis
    if basis == "expanding":
        # Expanding window: fraction of historical values <= current
        disp_pctile = float((h <= h.iloc[-1]).mean())
    elif basis == "trailing_252":
        # Trailing 252d window
        h_trail = h.iloc[-252:] if len(h) >= 252 else h
        disp_pctile = float((h_trail <= h_trail.iloc[-1]).mean())
    else:
        raise ValueError(f"Unknown basis: {basis!r}")

    # State assignment (thresholds match engine/dispersion.py exactly)
    if disp_pctile >= _HI:
        state = "lean_in"
    elif disp_pctile <= _LO:
        state = "lean_out"
    else:
        state = "neutral"

    return {
        "state": state,
        "disp_pctile": round(disp_pctile, 4),
        "disp_ppt": disp_ppt,
        "n_names_at_date": n_names_at_date,
    }


# ---------------------------------------------------------------------------
# Vectorized PIT reconstruction (efficient batch assignment for all fires)
# ---------------------------------------------------------------------------

def _precompute_regime_series(closes: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Precompute the expanding-window and trailing-252d percentile series for all dates.

    Returns 4 Series (all DatetimeIndex):
        - exp_pctile: expanding-window percentile of rolling-21d-mean CSD
        - trail_pctile: trailing-252d percentile of rolling-21d-mean CSD
        - disp_ppt: rolling-21d-mean CSD in ppt (percent of price)
        - n_names: per-date non-null name count
    All series share the closes DatetimeIndex (NaN where insufficient history).
    """
    returns = closes.pct_change(fill_method=None)
    csd = returns.std(axis=1)
    hist = csd.rolling(21, min_periods=10).mean()

    # Expanding pctile: rank(pct=True) in expanding window
    # pandas expanding().rank(pct=True) gives fraction of values <= current value
    exp_pctile = hist.expanding(min_periods=60).rank(pct=True)

    # Trailing-252d pctile: rolling window rank
    trail_pctile = hist.rolling(252, min_periods=60).rank(pct=True)

    disp_ppt = hist * 100  # in pct-point units

    n_names = closes.notna().sum(axis=1)

    return exp_pctile, trail_pctile, disp_ppt, n_names


def _assign_regime_from_precomputed(
    exp_pctile: pd.Series,
    trail_pctile: pd.Series,
    disp_ppt: pd.Series,
    n_names: pd.Series,
    fire_dates: pd.DatetimeIndex,
    closes_index: pd.DatetimeIndex,
    min_prior_bars: int = _MIN_PRIOR_BARS,
) -> pd.DataFrame:
    """Batch assign regimes for all fire dates using precomputed series.

    Returns DataFrame with columns:
        state_expanding, disp_pctile_expanding,
        state_trailing_252, disp_pctile_trailing_252,
        disp_ppt, n_names_at_date, n_bars_available, included
    """
    rows = []
    for fd in fire_dates:
        # Count bars available before fire date (feasibility gate)
        n_bars = int((closes_index < fd).sum())
        included = n_bars >= min_prior_bars

        if not included:
            rows.append({
                "n_bars_available": n_bars,
                "included": False,
                "state_expanding": None,
                "disp_pctile_expanding": None,
                "state_trailing_252": None,
                "disp_pctile_trailing_252": None,
                "disp_ppt": None,
                "n_names_at_date": None,
            })
            continue

        # Get the last available date <= fire_date
        avail_dates = closes_index[closes_index <= fd]
        if len(avail_dates) == 0:
            rows.append({
                "n_bars_available": n_bars, "included": False,
                "state_expanding": None, "disp_pctile_expanding": None,
                "state_trailing_252": None, "disp_pctile_trailing_252": None,
                "disp_ppt": None, "n_names_at_date": None,
            })
            continue
        last_date = avail_dates[-1]

        ep = exp_pctile.get(last_date, None)
        tp = trail_pctile.get(last_date, None)
        dp = disp_ppt.get(last_date, None)
        nn = int(n_names.get(last_date, 0))

        def _state(pctile):
            if pctile is None or (isinstance(pctile, float) and np.isnan(pctile)):
                return None
            if pctile >= _HI:
                return "lean_in"
            elif pctile <= _LO:
                return "lean_out"
            else:
                return "neutral"

        ep_val = float(ep) if (ep is not None and not np.isnan(ep)) else None
        tp_val = float(tp) if (tp is not None and not np.isnan(tp)) else None
        dp_val = float(dp) if (dp is not None and not np.isnan(dp)) else None

        rows.append({
            "n_bars_available": n_bars,
            "included": True,
            "state_expanding": _state(ep_val),
            "disp_pctile_expanding": round(ep_val, 4) if ep_val is not None else None,
            "state_trailing_252": _state(tp_val),
            "disp_pctile_trailing_252": round(tp_val, 4) if tp_val is not None else None,
            "disp_ppt": round(dp_val, 2) if dp_val is not None else None,
            "n_names_at_date": nn,
        })

    result = pd.DataFrame(rows, index=fire_dates)
    return result


# ---------------------------------------------------------------------------
# SPY covariate computation
# ---------------------------------------------------------------------------

def _compute_spy_covariates(spy_closes: pd.Series, fire_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Compute SPY 21d return and 21d realized vol for each fire date.

    SPY 21d return: forward-looking SPY return at fire_date (contemporaneous tape backdrop).
    SPY 21d realized vol: backward-looking 21d std of daily returns before fire_date.
    """
    rows = []
    for fd in fire_dates:
        # SPY 21d return starting from fire date (contemporaneous backdrop per prereg)
        # "SPY 21d return at fire_date" = forward return from fire_date to fire_date+21d
        # Note: prereg says "contemporaneous-market-drawdown covariate at fire_date"
        # We use backward-looking 21d SPY return as tape backdrop (what operator saw)
        spy_before = spy_closes.loc[:fd]
        if len(spy_before) < 22:
            rows.append({"spy_ret_21d_back": None, "spy_rvol_21d": None})
            continue
        spy_ret_21d = float((spy_before.iloc[-1] / spy_before.iloc[-22]) - 1) if spy_before.iloc[-22] > 0 else None
        # Realized vol: 21d annualized vol of daily returns prior to fire_date
        spy_daily = spy_before.pct_change().iloc[-22:]
        spy_rvol = float(spy_daily.std() * np.sqrt(252)) if len(spy_daily) >= 5 else None
        rows.append({"spy_ret_21d_back": spy_ret_21d, "spy_rvol_21d": spy_rvol})
    return pd.DataFrame(rows, index=fire_dates)


# ---------------------------------------------------------------------------
# Episode cluster assignment
# ---------------------------------------------------------------------------

def _assign_episode_clusters(fires_df: pd.DataFrame) -> pd.Series:
    """Assign episode cluster IDs using contiguous calendar-time blocks (±30d).

    Matches the frozen prereg (L3_PREREG.md Standing Notes):
    "Bootstrap resamples episode clusters (contiguous blocks within ±30d)"

    Implementation: sort fires by signal_date, then assign a new cluster
    whenever a fire's date is more than 30 calendar days after the earliest
    date in the current block (i.e. fires within 30d of the block's start
    share a cluster ID). This is CROSS-TICKER — two fires from different
    tickers on the same macro-shock date fall in the SAME cluster, correctly
    capturing tape-time correlated outcomes.

    Cluster ID format: BLOCK_<YYYYMMDD> where YYYYMMDD is the start date of
    each contiguous block.

    NOTE: The original implementation used TICKER_YYYY-Www (per-ticker ISO week).
    That deviated from the prereg by (a) giving different cluster IDs to
    different tickers on the same date (missing cross-ticker tape correlation)
    and (b) splitting fires 2-3 days apart across ISO-week boundaries.
    This fix restores the prereg-specified definition.
    Deviation logged here and in the summary for transparency.
    """
    dates = pd.to_datetime(fires_df["signal_date"])
    sorted_dates = dates.sort_values()

    cluster_ids = pd.Series(index=fires_df.index, dtype=str)
    block_start: pd.Timestamp | None = None
    block_label: str = ""
    block_idx: int = 0

    for orig_idx, fd in sorted_dates.items():
        if block_start is None or (fd - block_start).days > 30:
            block_start = fd
            block_label = f"BLOCK_{fd.strftime('%Y%m%d')}"
            block_idx += 1
        cluster_ids[orig_idx] = block_label

    return cluster_ids


# ---------------------------------------------------------------------------
# Outcome computation
# ---------------------------------------------------------------------------

def _compute_outcomes(fires_df: pd.DataFrame) -> pd.DataFrame:
    """Compute stop5 and dead_money at 21d time-exit from replay_boarded columns.

    stop5 = fwd_mdd_21 <= -5% (max drawdown in 21d window >= 5% adverse)
    dead_money = |fwd_ret_21| < 2%
    clean_liftoff (descriptive extra) = fwd_ret_21 >= 5% AND fwd_mfe_21 >= 5%
    """
    df = fires_df.copy()

    # stop5: fwd_mdd_21 is the maximum drawdown (a negative or zero number)
    # if fwd_mdd_21 <= -0.05, the fire drew down >= 5%
    if "fwd_mdd_21" in df.columns:
        df["stop5"] = df["fwd_mdd_21"] <= _STOP5_THRESH
    else:
        log.warning("fwd_mdd_21 not found in replay_boarded — stop5 will be NaN")
        df["stop5"] = np.nan

    # dead_money: |fwd_ret_21| < 2%
    if "fwd_ret_21" in df.columns:
        df["dead_money"] = df["fwd_ret_21"].abs() < _DEAD_MONEY_THRESH
        # clean_liftoff (descriptive only)
        if "fwd_mfe_21" in df.columns:
            df["clean_liftoff"] = (df["fwd_ret_21"] >= 0.05) & (df["fwd_mfe_21"] >= 0.05)
        else:
            df["clean_liftoff"] = df["fwd_ret_21"] >= 0.05
    else:
        log.warning("fwd_ret_21 not found in replay_boarded — dead_money will be NaN")
        df["dead_money"] = np.nan
        df["clean_liftoff"] = np.nan

    return df


# ---------------------------------------------------------------------------
# Bootstrap CIs (episode-clustered)
# ---------------------------------------------------------------------------

def _bootstrap_ci(
    values: np.ndarray,
    cluster_ids: np.ndarray,
    stat: str = "mean",
    n_boot: int = _N_BOOTSTRAP,
    ci: float = 0.90,
    rng: np.random.Generator | None = None,
) -> tuple[float, float]:
    """Episode-clustered bootstrap CI for a proportion/mean.

    Resamples CLUSTERS (not individual rows) to preserve within-cluster correlation.
    Returns (ci_lo, ci_hi) at the given ci level.

    Efficient implementation: precomputes per-cluster means, then resamples those means.
    This is O(n_boot × n_clusters) instead of O(n_boot × n_fires × n_clusters).
    """
    if rng is None:
        rng = np.random.default_rng(_RNG_SEED)
    unique_clusters, inverse = np.unique(cluster_ids, return_inverse=True)
    n_clusters = len(unique_clusters)
    if n_clusters < _MIN_CLUSTERS_FOR_CI:
        return (np.nan, np.nan)

    # Precompute per-cluster means and sizes (the building block for resampling)
    values_float = values.astype(float)
    cluster_means = np.array([
        float(np.nanmean(values_float[inverse == i]))
        for i in range(n_clusters)
    ])
    cluster_sizes = np.array([int(np.sum(inverse == i)) for i in range(n_clusters)])

    # Bootstrap: resample cluster means weighted by cluster size
    # This gives the same result as resampling individual rows within clusters
    # (Central Limit Theorem applies at the cluster level)
    total_size = float(cluster_sizes.sum())
    weights = cluster_sizes / total_size

    boot_stats = []
    for _ in range(n_boot):
        idx = rng.choice(n_clusters, size=n_clusters, replace=True)
        # Weighted mean of resampled cluster means
        boot_val = float(np.average(cluster_means[idx], weights=cluster_sizes[idx]))
        boot_stats.append(boot_val)

    if not boot_stats:
        return (np.nan, np.nan)

    alpha = (1 - ci) / 2
    return (
        float(np.percentile(boot_stats, 100 * alpha)),
        float(np.percentile(boot_stats, 100 * (1 - alpha))),
    )


# ---------------------------------------------------------------------------
# Arm summary
# ---------------------------------------------------------------------------

def _arm_summary(
    df: pd.DataFrame,
    cluster_col: str = "cluster_id",
) -> dict:
    """Compute per-arm statistics for a subset of fires."""
    n = len(df)
    n_clusters = df[cluster_col].nunique() if cluster_col in df.columns else 0

    if n == 0:
        return {
            "n_fires": 0, "n_clusters": 0,
            "stop5_rate": None, "stop5_ci90_lo": None, "stop5_ci90_hi": None,
            "dead_money_rate": None, "dead_money_ci90_lo": None, "dead_money_ci90_hi": None,
            "clean_liftoff_rate": None,
            "mean_ret_21d": None,
            "ci_note": "no fires",
        }

    rng = np.random.default_rng(_RNG_SEED)
    cluster_ids = df[cluster_col].values if cluster_col in df.columns else np.arange(n)

    stop5 = df["stop5"].astype(float).values
    dead_money = df["dead_money"].astype(float).values
    clean_liftoff = df["clean_liftoff"].astype(float).values if "clean_liftoff" in df.columns else np.full(n, np.nan)

    stop5_rate = float(np.nanmean(stop5))
    dead_money_rate = float(np.nanmean(dead_money))
    clean_liftoff_rate = float(np.nanmean(clean_liftoff)) if not np.all(np.isnan(clean_liftoff)) else None
    mean_ret_21d = float(df["fwd_ret_21"].mean()) if "fwd_ret_21" in df.columns else None

    if n_clusters >= _MIN_CLUSTERS_FOR_CI:
        s5_lo, s5_hi = _bootstrap_ci(stop5, cluster_ids, stat="proportion", rng=rng)
        dm_lo, dm_hi = _bootstrap_ci(dead_money, cluster_ids, stat="proportion", rng=rng)
        ci_note = f"episode-clustered bootstrap 90% CI, {n_clusters} clusters"
    else:
        s5_lo, s5_hi = np.nan, np.nan
        dm_lo, dm_hi = np.nan, np.nan
        ci_note = f"sparse — {n_clusters} clusters < {_MIN_CLUSTERS_FOR_CI} floor — descriptive only, no bootstrap CIs"

    return {
        "n_fires": n,
        "n_clusters": n_clusters,
        "stop5_rate": round(stop5_rate, 4),
        "stop5_ci90_lo": round(s5_lo, 4) if not np.isnan(s5_lo) else None,
        "stop5_ci90_hi": round(s5_hi, 4) if not np.isnan(s5_hi) else None,
        "dead_money_rate": round(dead_money_rate, 4),
        "dead_money_ci90_lo": round(dm_lo, 4) if not np.isnan(dm_lo) else None,
        "dead_money_ci90_hi": round(dm_hi, 4) if not np.isnan(dm_hi) else None,
        "clean_liftoff_rate": round(clean_liftoff_rate, 4) if clean_liftoff_rate is not None else None,
        "mean_ret_21d": round(mean_ret_21d, 4) if mean_ret_21d is not None else None,
        "ci_note": ci_note,
    }


# ---------------------------------------------------------------------------
# Covariate split analysis
# ---------------------------------------------------------------------------

def _covariate_splits(df: pd.DataFrame, basis: str) -> dict:
    """Compute stop5/dead_money rates within each SPY 21d return tercile and vol tercile.

    SPY terciles (per prereg): < -5%, -5%..+5%, > +5%
    Vol terciles: low/mid/high realized vol (data-driven tercile boundaries)
    """
    col_state = f"state_{basis}"
    col_spy = "spy_ret_21d_back"
    col_rvol = "spy_rvol_21d"

    # Ensure columns exist
    for c in [col_state, col_spy, col_rvol]:
        if c not in df.columns:
            return {"error": f"column {c!r} not found"}

    states = ["lean_in", "neutral", "lean_out"]
    spy_terciles = [
        ("spy_down", df[col_spy] < _SPY_T1),
        ("spy_flat", (df[col_spy] >= _SPY_T1) & (df[col_spy] <= _SPY_T2)),
        ("spy_up", df[col_spy] > _SPY_T2),
    ]

    # Vol terciles: data-driven boundaries
    rvol_valid = df[col_rvol].dropna()
    if len(rvol_valid) > 10:
        v33, v66 = rvol_valid.quantile(0.33), rvol_valid.quantile(0.66)
        vol_terciles = [
            ("vol_low", df[col_rvol] <= v33),
            ("vol_mid", (df[col_rvol] > v33) & (df[col_rvol] <= v66)),
            ("vol_high", df[col_rvol] > v66),
        ]
        vol_boundaries = {"v33": round(float(v33), 4), "v66": round(float(v66), 4)}
    else:
        vol_terciles = []
        vol_boundaries = {}

    result: dict[str, Any] = {"vol_boundaries": vol_boundaries}

    for spy_name, spy_mask in spy_terciles:
        result[spy_name] = {}
        spy_count = int(spy_mask.sum())
        result[spy_name]["n_in_tercile"] = spy_count
        for state in states:
            arm = df[spy_mask & (df[col_state] == state)]
            n_arm = len(arm)
            if n_arm == 0:
                result[spy_name][state] = {"n": 0, "stop5_rate": None, "dead_money_rate": None}
            else:
                result[spy_name][state] = {
                    "n": n_arm,
                    "stop5_rate": round(float(arm["stop5"].astype(float).mean()), 4),
                    "dead_money_rate": round(float(arm["dead_money"].astype(float).mean()), 4),
                }

    # Vol tercile splits
    result["vol_terciles"] = {}
    for vol_name, vol_mask in vol_terciles:
        result["vol_terciles"][vol_name] = {}
        for state in states:
            arm = df[vol_mask & (df[col_state] == state)]
            n_arm = len(arm)
            if n_arm == 0:
                result["vol_terciles"][vol_name][state] = {"n": 0, "stop5_rate": None, "dead_money_rate": None}
            else:
                result["vol_terciles"][vol_name][state] = {
                    "n": n_arm,
                    "stop5_rate": round(float(arm["stop5"].astype(float).mean()), 4),
                    "dead_money_rate": round(float(arm["dead_money"].astype(float).mean()), 4),
                }

    return result


# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

def run(
    replay_path: Path | None = None,
    panel_override: pd.DataFrame | None = None,
    spy_closes_override: pd.Series | None = None,
    summary_out: Path | None = None,
    report_out: Path | None = None,
    verbose: bool = True,
) -> dict:
    """Run the DISP-GATE-1 harness. Returns the summary dict.

    Parameters
    ----------
    replay_path : path to replay_boarded.parquet (default: main checkout data)
    panel_override : pre-built closes panel (for testing)
    spy_closes_override : pre-built SPY closes (for testing)
    summary_out : output path for summary JSON (None = skip write)
    report_out : output path for report MD (None = skip write)
    verbose : print progress to stdout
    """
    t0 = datetime.now(timezone.utc)

    def _print(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    _print("=" * 70)
    _print("DISP-GATE-1 HARNESS — DESCRIPTIVE-ONLY, NO VERDICT THIS BATCH")
    _print(f"Run timestamp: {t0.isoformat()}")
    _print(f"Bound by: research/dispersion/L3_PREREG.md (frozen)")
    _print(f"gross_mult_live = 1.0 HARD CONSTRAINT (RUL-F3.7, unchanged)")
    _print("=" * 70)

    # -----------------------------------------------------------------------
    # STEP 1: Load closes panel
    # -----------------------------------------------------------------------
    _print("\n[1/7] Loading closes panel...")
    if panel_override is not None:
        closes = panel_override
    else:
        closes = _load_panel()

    if closes.empty:
        _print("FATAL: closes panel is empty — cannot reconstruct dispersion history")
        return {"status": "FATAL", "reason": "empty panel"}

    closes.index = pd.DatetimeIndex(closes.index)
    closes = closes.sort_index()

    panel_earliest = closes.index.min()
    panel_latest = closes.index.max()
    panel_n_dates = len(closes)

    _print(f"  Panel range  : {panel_earliest.date()} .. {panel_latest.date()}")
    _print(f"  Panel dates  : {panel_n_dates:,}")
    _print(f"  Panel tickers: {closes.shape[1]:,}")

    # Per-year date counts (data quality column)
    by_year = pd.DatetimeIndex(closes.index).year.value_counts().sort_index()
    _print("  Per-year date counts (data quality):")
    for yr, cnt in by_year.items():
        _print(f"    {yr}: {cnt} dates")

    # -----------------------------------------------------------------------
    # STEP 2: Load fires
    # -----------------------------------------------------------------------
    _print("\n[2/7] Loading fire population...")
    rp = replay_path or _REPLAY_PATH
    rb = pd.read_parquet(rp)
    fires = rb[(rb["verdict_type"] == "fire") & (rb["verdict_grade"] == True)].copy()
    _print(f"  Total fires (verdict_type=fire AND verdict_grade=True): {len(fires):,}")

    fires["signal_date"] = pd.to_datetime(fires["signal_date"])
    fires = fires.sort_values("signal_date").reset_index(drop=True)
    _print(f"  Fire signal_date range: {fires['signal_date'].min().date()} .. {fires['signal_date'].max().date()}")

    # -----------------------------------------------------------------------
    # FEASIBILITY GATE PRINTS FIRST (RUL-F3.6)
    # -----------------------------------------------------------------------
    _print("\n[3/7] FEASIBILITY GATE — exclusion count BEFORE any statistic")
    _print(f"  Minimum prior panel bars required: {_MIN_PRIOR_BARS}")

    # Determine which fires can be assigned (panel has >= 252 bars BEFORE fire date)
    # Sort closes index for fast lookup
    closes_dates = closes.index  # DatetimeIndex, sorted

    def _bars_before(fd: pd.Timestamp) -> int:
        return int((closes_dates < fd).sum())

    fire_bar_counts = fires["signal_date"].apply(_bars_before)
    included_mask = fire_bar_counts >= _MIN_PRIOR_BARS
    n_excluded = int((~included_mask).sum())
    n_included = int(included_mask.sum())

    _print(f"  Fires with >= {_MIN_PRIOR_BARS} prior panel bars: {n_included:,}")
    _print(f"  Fires EXCLUDED (< {_MIN_PRIOR_BARS} prior bars)  : {n_excluded:,}")

    fires_excluded = fires[~included_mask]
    if n_excluded > 0:
        excl_dates = fires_excluded["signal_date"]
        _print(f"  Excluded fire date range: {excl_dates.min().date()} .. {excl_dates.max().date()}")

    if n_included == 0:
        _print("  RESULT: DEFER — zero fires pass the feasibility gate")
        return {
            "status": "DEFER",
            "reason": "zero fires pass feasibility gate (no panel history >= 252 bars)",
            "panel_earliest": str(panel_earliest.date()),
            "panel_latest": str(panel_latest.date()),
            "n_fires_total": len(fires),
            "n_excluded": n_excluded,
            "n_included": 0,
        }

    fires_ok = fires[included_mask].copy().reset_index(drop=True)

    if n_included < 100:
        _print(f"  WARNING: only {n_included} fires pass feasibility gate — thin cohort")

    # -----------------------------------------------------------------------
    # STEP 4: Compute outcomes
    # -----------------------------------------------------------------------
    _print("\n[4/7] Computing fire outcomes (stop5, dead_money, clean_liftoff)...")
    fires_ok = _compute_outcomes(fires_ok)

    # Episode cluster assignment
    fires_ok["cluster_id"] = _assign_episode_clusters(fires_ok)
    n_clusters_total = fires_ok["cluster_id"].nunique()
    _print(f"  Outcome columns computed for {n_included:,} fires")
    _print(f"  Episode clusters (TICKER_YYYY-Www): {n_clusters_total:,}")
    _print(f"  Overall stop5 rate  : {fires_ok['stop5'].mean():.1%}")
    _print(f"  Overall dead_money rate: {fires_ok['dead_money'].mean():.1%}")

    # -----------------------------------------------------------------------
    # STEP 5: PIT regime reconstruction — both bases (vectorized)
    # -----------------------------------------------------------------------
    _print("\n[5/7] Reconstructing PIT dispersion regimes (vectorized precompute)...")
    import time as _time
    t_regime = _time.perf_counter()

    # Precompute full CSD percentile series for all dates (O(n_dates) not O(n_fires))
    _print("  Precomputing CSD percentile series for full panel...")
    exp_pctile, trail_pctile, disp_ppt_series, n_names_series = _precompute_regime_series(closes)
    _print(f"  Precompute complete ({_time.perf_counter()-t_regime:.1f}s)")

    # Batch assign regimes for all fires at once
    fire_dates_idx = pd.DatetimeIndex(fires_ok["signal_date"])
    t_assign = _time.perf_counter()
    _print(f"  Assigning regimes to {n_included:,} fires...")
    regime_df = _assign_regime_from_precomputed(
        exp_pctile=exp_pctile,
        trail_pctile=trail_pctile,
        disp_ppt=disp_ppt_series,
        n_names=n_names_series,
        fire_dates=fire_dates_idx,
        closes_index=closes.index,
        min_prior_bars=_MIN_PRIOR_BARS,
    )
    _print(f"  Assignment complete ({_time.perf_counter()-t_assign:.1f}s)")

    # Join back (index alignment: fires_ok is reset_index'd, regime_df is fire_dates indexed)
    regime_df.index = fires_ok.index
    fires_ok = pd.concat([fires_ok, regime_df], axis=1)

    _print(f"  Regime assignment complete.")
    # Report per-date name count summary
    n_names_valid = fires_ok["n_names_at_date"].dropna()
    if len(n_names_valid) > 0:
        _print(f"  Median names-at-fire-date: {n_names_valid.median():.0f}")
        _print(f"  Min/Max names-at-fire-date: {n_names_valid.min():.0f} / {n_names_valid.max():.0f}")

    # -----------------------------------------------------------------------
    # STEP 5b: Basis flip rate
    # -----------------------------------------------------------------------
    _print("\n[5b] Basis flip-rate analysis...")
    valid_both = fires_ok.dropna(subset=["state_expanding", "state_trailing_252"])
    n_valid_both = len(valid_both)
    if n_valid_both > 0:
        flips = (valid_both["state_expanding"] != valid_both["state_trailing_252"]).sum()
        flip_rate = float(flips / n_valid_both)
        _print(f"  Fires with both basis assignments: {n_valid_both:,}")
        _print(f"  Basis flip count (different state): {flips:,}")
        _print(f"  Basis flip rate: {flip_rate:.1%}  {'<<< EXCEEDS 15% FLAG' if flip_rate > 0.15 else '(< 15% threshold)'}")
        if flip_rate > 0.15:
            _print("  FLAG: NON-STATIONARITY — flip rate > 15%. Report proceeds descriptively on expanding basis only.")
            flip_flag_triggered = True
        else:
            flip_flag_triggered = False
    else:
        flip_rate = None
        flip_flag_triggered = False
        _print("  Cannot compute flip rate — no fires with both basis assignments")

    # -----------------------------------------------------------------------
    # STEP 6: Load SPY covariates
    # -----------------------------------------------------------------------
    _print("\n[6/7] Computing SPY covariates...")
    if spy_closes_override is not None:
        spy_closes = spy_closes_override
    else:
        spy_closes = _load_spy_closes()

    if not spy_closes.empty:
        spy_closes.index = pd.DatetimeIndex(spy_closes.index)
        spy_cov = _compute_spy_covariates(spy_closes, pd.DatetimeIndex(fires_ok["signal_date"]))
        spy_cov.index = fires_ok.index
        fires_ok = pd.concat([fires_ok, spy_cov], axis=1)
        _print(f"  SPY covariates computed. Spy ret range: {fires_ok['spy_ret_21d_back'].min():.1%} .. {fires_ok['spy_ret_21d_back'].max():.1%}")
        spy_tercile_counts = {
            "spy_down (< -5%)": int((fires_ok["spy_ret_21d_back"] < _SPY_T1).sum()),
            "spy_flat (-5%..+5%)": int(((fires_ok["spy_ret_21d_back"] >= _SPY_T1) & (fires_ok["spy_ret_21d_back"] <= _SPY_T2)).sum()),
            "spy_up (> +5%)": int((fires_ok["spy_ret_21d_back"] > _SPY_T2).sum()),
        }
        _print(f"  SPY tercile distribution: {spy_tercile_counts}")
    else:
        fires_ok["spy_ret_21d_back"] = np.nan
        fires_ok["spy_rvol_21d"] = np.nan
        _print("  WARNING: SPY closes unavailable — covariate splits will be null")

    # -----------------------------------------------------------------------
    # STEP 7: Compute arm summaries for both bases
    # -----------------------------------------------------------------------
    _print("\n[7/7] Computing arm summaries (regime × basis)...")
    states_order = ["lean_in", "neutral", "lean_out"]
    bases = ["expanding", "trailing_252"]

    arm_results: dict[str, Any] = {}

    for basis in bases:
        col_state = f"state_{basis}"
        if col_state not in fires_ok.columns:
            _print(f"  Skipping basis={basis}: no regime column")
            continue
        arm_results[basis] = {}
        _print(f"\n  --- Basis: {basis} ---")
        _print(f"  {'State':<12} {'N fires':>8} {'N clusters':>12} {'stop5':>8} {'dead_money':>12}")
        _print(f"  {'-'*12} {'-'*8} {'-'*12} {'-'*8} {'-'*12}")

        for state in states_order:
            arm_df = fires_ok[fires_ok[col_state] == state].copy()
            summary = _arm_summary(arm_df)
            arm_results[basis][state] = summary
            stop5_str = f"{summary['stop5_rate']:.1%}" if summary['stop5_rate'] is not None else "None"
            dm_str = f"{summary['dead_money_rate']:.1%}" if summary['dead_money_rate'] is not None else "None"
            _print(f"  {state:<12} {summary['n_fires']:>8,} {summary['n_clusters']:>12,} {stop5_str:>8} {dm_str:>12}")
            _print(f"           {summary['ci_note']}")

        # Primary conclusion check (lean_out vs lean_in stop5 gap + >= 5pp magnitude)
        lo_sum = arm_results[basis].get("lean_out", {})
        li_sum = arm_results[basis].get("lean_in", {})
        lo_s5 = lo_sum.get("stop5_rate")
        li_s5 = li_sum.get("stop5_rate")
        if lo_s5 is not None and li_s5 is not None:
            gap_pp = (lo_s5 - li_s5) * 100
            gap_sign_ok = gap_pp > 0
            gap_magnitude_ok = abs(gap_pp) >= 5.0
            _print(f"\n  lean_out vs lean_in stop5 gap: {gap_pp:+.1f}pp  "
                   f"(sign={'DIRECTIONAL (lean_out > lean_in)' if gap_sign_ok else 'REVERSED'}; "
                   f"magnitude={'>=5pp' if gap_magnitude_ok else '<5pp'})")
            arm_results[basis]["_primary_conclusion_check"] = {
                "gap_pp": round(gap_pp, 2),
                "gap_sign_correct": gap_sign_ok,
                "gap_magnitude_ok": gap_magnitude_ok,
            }

    # Covariate splits (descriptive only, not verdict cells)
    _print("\n  Covariate splits (descriptive — SPY backdrop + realized vol):")
    cov_splits: dict[str, Any] = {}
    for basis in bases:
        col_state = f"state_{basis}"
        if col_state in fires_ok.columns:
            # Rename state col temporarily for split function
            temp_df = fires_ok.copy()
            cov_splits[basis] = _covariate_splits(temp_df.rename(columns={col_state: f"state_{basis}"}), basis)

    # -----------------------------------------------------------------------
    # DEFER check — both bases must show directional + >= 5pp gap
    # -----------------------------------------------------------------------
    _print("\n" + "=" * 70)
    defer_reasons = []
    for basis in bases:
        chk = arm_results.get(basis, {}).get("_primary_conclusion_check", {})
        if not chk:
            defer_reasons.append(f"basis={basis}: no primary conclusion (insufficient data)")
        elif not chk.get("gap_sign_correct"):
            defer_reasons.append(f"basis={basis}: gap sign REVERSED (lean_out < lean_in stop5 rate)")
        elif not chk.get("gap_magnitude_ok"):
            defer_reasons.append(f"basis={basis}: gap magnitude < 5pp ({chk.get('gap_pp', '?'):.1f}pp)")

    if flip_flag_triggered:
        defer_reasons.append(f"flip_rate={flip_rate:.1%} > 15% — NON-STATIONARITY flag")

    # Check n-floor for lead arms
    for basis in bases:
        li_n = arm_results.get(basis, {}).get("lean_in", {}).get("n_clusters", 0)
        lo_n = arm_results.get(basis, {}).get("lean_out", {}).get("n_clusters", 0)
        if li_n < _MIN_CLUSTERS_FOR_CI or lo_n < _MIN_CLUSTERS_FOR_CI:
            defer_reasons.append(
                f"basis={basis}: cluster floor not met "
                f"(lean_in={li_n}, lean_out={lo_n}, floor={_MIN_CLUSTERS_FOR_CI})"
            )

    if defer_reasons:
        overall_verdict = "DEFER"
        _print("OVERALL VERDICT: DEFER")
        for r in defer_reasons:
            _print(f"  DEFER reason: {r}")
    else:
        overall_verdict = "DESCRIPTIVE-READOUT-COMPLETE"
        _print("OVERALL VERDICT: DESCRIPTIVE-READOUT-COMPLETE")
        _print("  Primary conclusion on both bases: lean_out fires show higher stop5 rate, gap >= 5pp")
        _print("  NOTE: This is a descriptive-only batch. No promotion gate evaluated.")
        _print("  NOTE: gross_mult_live remains 1.0 (HARD CONSTRAINT, RUL-F3.7)")

    # -----------------------------------------------------------------------
    # Build summary dict
    # -----------------------------------------------------------------------
    t1 = datetime.now(timezone.utc)

    # Survivorship caveat (must appear verbatim per Opus reviewer must-fix item)
    _SURVIVORSHIP_CAVEAT = (
        "PANEL SURVIVORSHIP DISCLOSED: breadth/_closes_deep.parquet is today's surviving "
        "universe backfilled through history. All tickers are currently active (zero "
        "delisted/inactive in last 365d). Per-date non-null name count rises monotonically "
        "from sparse early history to today's full universe. The expanding-window percentile "
        "denominator (CSD history since inception) is therefore computed against a "
        "survivor-biased distribution: surviving stocks carry lower historical idiosyncratic "
        "dispersion (they include no Enron-style blowups, M&A-departed names, or delisted "
        "tickers that blew up cross-sectional variance). This biases the regime percentile "
        "level — surviving-universe CSD is understated at early dates — which may shift "
        "lean_in/lean_out state assignments relative to a full-universe panel. Because all "
        "fires are 2022+ and the panel universe is largest and most stable in recent years, "
        "the bias is lowest in the fire population window. However, the CSD percentile "
        "denominator reaches back to 1962 under the expanding basis and the early-history "
        "survivor-only distribution inflates the denominator, potentially understating the "
        "true percentile rank of recent CSD values. All regime state assignments carry this "
        "caveat. The trailing-252d sensitivity basis (using only 252-day rolling CSD) is "
        "less affected since it avoids the 60-year survivor-only denominator. "
        "NO delisted/inactive correction has been applied. This is a structural limitation "
        "of the panel; results are descriptive and should not be used for formal inference "
        "without a delisted-inclusive universe."
    )

    summary = {
        "exp_id": "disp_gate_v1",
        "run_at": t0.isoformat(),
        "runtime_s": round((t1 - t0).total_seconds(), 1),
        "vintage": t0.strftime("%Y-%m-%dT%H:%MZ"),
        "house_law_note": "gross_mult_live = 1.0 HARD CONSTRAINT (RUL-F3.7). descriptive-only batch.",
        "prereg": "research/dispersion/L3_PREREG.md",
        "verdict_criteria": "descriptive-only",
        "pooled_replay_trial_count": 31,  # 15 exit_grid + 10 wait_grid + 6 disp_gate = 31
        "survivorship_caveat": _SURVIVORSHIP_CAVEAT,
        "clustering_deviation_note": (
            "PREREG DEVIATION CORRECTED (PR-A2 fix): Original build used TICKER_YYYY-Www "
            "per-ticker ISO-week clustering. This deviated from L3_PREREG.md Standing Notes "
            "lines 122-124 which freeze clustering as 'contiguous blocks within ±30d'. "
            "The original scheme (a) gave different cluster IDs to different tickers on the "
            "same macro-shock date (missing cross-ticker tape correlation) and (b) could split "
            "fires 2-3 days apart across an ISO-week boundary. This build uses the prereg-spec "
            "BLOCK_<YYYYMMDD> scheme: fires within 30 calendar days of a block's start share "
            "one cluster ID regardless of ticker. This narrows n_clusters and widens CIs "
            "relative to the original build (fewer, larger clusters = more conservative)."
        ),
        "panel_info": {
            "earliest_date": str(panel_earliest.date()),
            "latest_date": str(panel_latest.date()),
            "n_dates": panel_n_dates,
            "n_tickers": closes.shape[1],
            "per_year_dates": {int(y): int(n) for y, n in by_year.items()},
        },
        "fire_population": {
            "total_fires": len(fires),
            "n_excluded_feasibility": n_excluded,
            "n_included": n_included,
            "n_clusters_total": n_clusters_total,
            "fire_date_range": [
                str(fires["signal_date"].min().date()),
                str(fires["signal_date"].max().date()),
            ],
        },
        "feasibility_gate": {
            "min_prior_bars": _MIN_PRIOR_BARS,
            "n_excluded": n_excluded,
            "exclusion_pct": round(100 * n_excluded / max(len(fires), 1), 1),
        },
        "basis_flip_rate": {
            "flip_rate": round(flip_rate, 4) if flip_rate is not None else None,
            "flip_count": int(flips) if flip_rate is not None else None,
            "n_valid_both": n_valid_both if flip_rate is not None else 0,
            "flag_gt15pct": flip_flag_triggered,
        },
        "arm_results": arm_results,
        "covariate_splits": cov_splits,
        "defer_reasons": defer_reasons,
        "overall_verdict": overall_verdict,
        "cell_hashes": get_cell_hashes(),
    }

    # -----------------------------------------------------------------------
    # Write outputs
    # -----------------------------------------------------------------------
    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(json.dumps(summary, indent=2, default=str))
        _print(f"\nSummary JSON written: {summary_out}")

    if report_out is not None:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_text = _build_report(summary, fires_ok)
        report_out.write_text(report_text)
        _print(f"Report MD written: {report_out}")

    return summary


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report(summary: dict, fires_df: pd.DataFrame) -> str:
    """Build the DISP-GATE-1_REPORT.md (R1 house style)."""
    vintage = summary.get("vintage", "unknown")
    verdict = summary.get("overall_verdict", "UNKNOWN")
    defer_reasons = summary.get("defer_reasons", [])
    arm_results = summary.get("arm_results", {})
    fire_pop = summary.get("fire_population", {})
    panel_info = summary.get("panel_info", {})
    flip_info = summary.get("basis_flip_rate", {})
    cov_splits = summary.get("covariate_splits", {})

    survivorship_caveat = summary.get("survivorship_caveat", "")
    clustering_deviation_note = summary.get("clustering_deviation_note", "")

    lines = [
        "# DISP-GATE-1 — Dispersion Regime Descriptive Readout",
        "",
        f"**Vintage:** {vintage}",
        f"**Bound by:** `research/dispersion/L3_PREREG.md` (frozen design)",
        f"**Status:** {verdict}",
        f"**Framing:** Display-only, fire-tape counterfactual. No held-position ledger exists.",
        f"  All outcomes attach to replay-tape fire events; no live position tracking implied.",
        "",
        "> **HARD CONSTRAINT (RUL-F3.7):** `gross_mult_live` is and remains 1.0 regardless",
        "> of this readout. This study can only enable a display flag; no sizing change is",
        "> authorized by any outcome of this batch.",
        "",
        "---",
        "",
        "## MANDATORY DISCLOSURE: Panel Survivorship",
        "",
        "> **PANEL SURVIVORSHIP (structural limitation):**",
        f"> {survivorship_caveat}",
        "",
        "---",
        "",
        "## MANDATORY DISCLOSURE: Episode-Clustering",
        "",
        "> **CLUSTERING METHOD (prereg compliance):**",
        f"> {clustering_deviation_note}",
        "",
        "---",
        "",
        "## In plain English",
        "",
        "We looked at whether stock-picking fires from our system perform differently",
        "depending on the market's 'dispersion regime' — whether individual stocks are",
        "moving independently (lean_in, good for selection) or all moving together in a",
        "macro-driven tape (lean_out, where selection historically earns little). We",
        "reconstructed what the regime indicator would have shown at the time of each",
        "fire, then measured how often fires ended in a painful drawdown (stop5 = drew",
        "down 5%+ in 21 days) or went nowhere (dead_money = returned less than ±2%).",
        "This is a descriptive readout only — no sizing changes and no promotion gates",
        "are evaluated here.",
        "Note: the panel used to compute historical CSD percentiles is a survivor-only",
        "universe (today's active stocks backfilled). See survivorship disclosure above.",
        "",
        "---",
        "",
        "## 1. Feasibility Gate (printed before any statistic)",
        "",
        f"- Total fires in population: **{fire_pop.get('total_fires', '?'):,}**",
        f"- Fires excluded (< {summary.get('feasibility_gate', {}).get('min_prior_bars', 252)} prior panel bars): **{fire_pop.get('n_excluded_feasibility', '?'):,}** ({summary.get('feasibility_gate', {}).get('exclusion_pct', '?'):.1f}%)",
        f"- Fires included in analysis: **{fire_pop.get('n_included', '?'):,}**",
        f"- Episode clusters (TICKER_YYYY-Www): **{fire_pop.get('n_clusters_total', '?'):,}**",
        "",
        "### Panel coverage",
        "",
        f"- Panel range: {panel_info.get('earliest_date', '?')} .. {panel_info.get('latest_date', '?')}",
        f"- Total panel dates: {panel_info.get('n_dates', '?'):,}",
        f"- Total panel tickers: {panel_info.get('n_tickers', '?'):,}",
        "",
        "Per-year date counts (data-quality column):",
        "",
        "| Year | Trading dates |",
        "|------|--------------|",
    ]
    for yr, n in sorted((panel_info.get("per_year_dates") or {}).items()):
        lines.append(f"| {yr} | {n} |")

    lines += [
        "",
        "---",
        "",
        "## 2. Basis Reconciliation",
        "",
        f"- Flip rate (expanding vs trailing-252): **{flip_info.get('flip_rate', 'N/A')}** "
        f"({flip_info.get('flip_count', '?')} of {flip_info.get('n_valid_both', '?')} fires flip state)",
        f"- 15% NON-STATIONARITY flag triggered: **{flip_info.get('flag_gt15pct', False)}**",
        "",
        "---",
        "",
        "## 3. Arm Summaries",
        "",
        "*Thresholds: lean_in = pctile >= 0.66; lean_out = pctile <= 0.33. Matches `engine/dispersion.py`.*",
        "",
    ]

    for basis, arms in arm_results.items():
        lines.append(f"### Basis: {basis}")
        lines.append("")
        lines.append("| State | N fires | N clusters | stop5 rate | stop5 CI 90% | dead_money rate | dead_money CI 90% | mean ret_21d |")
        lines.append("|-------|---------|-----------|-----------|--------------|----------------|-----------------|-------------|")
        for state in ["lean_in", "neutral", "lean_out"]:
            arm = arms.get(state, {})
            if not arm:
                continue
            n = arm.get("n_fires", 0)
            nc = arm.get("n_clusters", 0)
            s5 = f"{arm['stop5_rate']:.1%}" if arm.get("stop5_rate") is not None else "N/A"
            s5lo = f"{arm['stop5_ci90_lo']:.1%}" if arm.get("stop5_ci90_lo") is not None else "sparse"
            s5hi = f"{arm['stop5_ci90_hi']:.1%}" if arm.get("stop5_ci90_hi") is not None else "sparse"
            dm = f"{arm['dead_money_rate']:.1%}" if arm.get("dead_money_rate") is not None else "N/A"
            dmlo = f"{arm['dead_money_ci90_lo']:.1%}" if arm.get("dead_money_ci90_lo") is not None else "sparse"
            dmhi = f"{arm['dead_money_ci90_hi']:.1%}" if arm.get("dead_money_ci90_hi") is not None else "sparse"
            mr = f"{arm['mean_ret_21d']:.2%}" if arm.get("mean_ret_21d") is not None else "N/A"
            ci_rng = f"[{s5lo}, {s5hi}]" if s5lo != "sparse" else "sparse — descriptive only"
            dm_rng = f"[{dmlo}, {dmhi}]" if dmlo != "sparse" else "sparse — descriptive only"
            lines.append(f"| {state} | {n:,} | {nc:,} | {s5} | {ci_rng} | {dm} | {dm_rng} | {mr} |")

        chk = arms.get("_primary_conclusion_check", {})
        if chk:
            lines.append("")
            gap = chk.get("gap_pp", None)
            sign_ok = chk.get("gap_sign_correct", False)
            mag_ok = chk.get("gap_magnitude_ok", False)
            lines.append(f"**lean_out vs lean_in stop5 gap:** {gap:+.1f}pp  "
                         f"({'directional' if sign_ok else 'reversed'}; {'>=5pp' if mag_ok else '<5pp'})")
        lines.append("")

    lines += [
        "---",
        "",
        "## 4. Covariate Splits (descriptive — not verdict cells)",
        "",
        "*SPY 21d backward return terciles (contemporaneous tape backdrop):*",
        "*   spy_down: SPY_21d < -5% | spy_flat: -5% .. +5% | spy_up: > +5%*",
        "*Realized vol terciles: low/mid/high (data-driven boundaries).*",
        "",
    ]

    for basis, splits in cov_splits.items():
        if not splits or "error" in splits:
            continue
        lines.append(f"### Basis: {basis} — SPY tercile splits")
        lines.append("")
        lines.append("| SPY tercile | N | lean_in stop5 | neutral stop5 | lean_out stop5 |")
        lines.append("|------------|---|--------------|--------------|----------------|")
        for tercile in ["spy_down", "spy_flat", "spy_up"]:
            t = splits.get(tercile, {})
            n_t = t.get("n_in_tercile", 0)
            li = t.get("lean_in", {})
            ne = t.get("neutral", {})
            lo = t.get("lean_out", {})
            li_s5 = f"{li.get('stop5_rate', None):.1%}" if li.get("stop5_rate") is not None else "N/A"
            ne_s5 = f"{ne.get('stop5_rate', None):.1%}" if ne.get("stop5_rate") is not None else "N/A"
            lo_s5 = f"{lo.get('stop5_rate', None):.1%}" if lo.get("stop5_rate") is not None else "N/A"
            lines.append(f"| {tercile} (n={n_t}) | | {li_s5} | {ne_s5} | {lo_s5} |")
        lines.append("")

        vol_splits = splits.get("vol_terciles", {})
        if vol_splits:
            vbounds = splits.get("vol_boundaries", {})
            lines.append(f"### Basis: {basis} — realized vol tercile splits")
            lines.append(f"*(vol boundaries: p33={vbounds.get('v33', '?'):.1%}, p66={vbounds.get('v66', '?'):.1%} annualized)*")
            lines.append("")
            lines.append("| Vol tercile | lean_in stop5 | neutral stop5 | lean_out stop5 |")
            lines.append("|-------------|--------------|--------------|----------------|")
            for vol_name in ["vol_low", "vol_mid", "vol_high"]:
                vt = vol_splits.get(vol_name, {})
                li = vt.get("lean_in", {})
                ne = vt.get("neutral", {})
                lo = vt.get("lean_out", {})
                li_s5 = f"{li.get('stop5_rate', None):.1%}" if li.get("stop5_rate") is not None else "N/A"
                ne_s5 = f"{ne.get('stop5_rate', None):.1%}" if ne.get("stop5_rate") is not None else "N/A"
                lo_s5 = f"{lo.get('stop5_rate', None):.1%}" if lo.get("stop5_rate") is not None else "N/A"
                lines.append(f"| {vol_name} | {li_s5} | {ne_s5} | {lo_s5} |")
            lines.append("")

    # Verdict section
    lines += [
        "---",
        "",
        "## 5. Overall Verdict",
        "",
        f"**{verdict}**",
        "",
    ]
    if defer_reasons:
        lines.append("Defer reasons:")
        for r in defer_reasons:
            lines.append(f"- {r}")
    else:
        lines.append(
            "Primary conclusion on both bases: lean_out fires show higher stop5 rate"
            " with gap >= 5pp. Basis flip rate below 15% threshold."
        )
        lines.append("")
        lines.append(
            "The frozen PASS thresholds in `L3_PREREG.md` are NOT evaluated here — "
            "this is the descriptive readout. A future registered verdict batch would "
            "apply those thresholds on a separate registered run."
        )

    lines += [
        "",
        "---",
        "",
        "## 6. Standing Notes",
        "",
        f"- Cumulative pooled replay trial count: **{summary.get('pooled_replay_trial_count', '?')}** cells declared",
        "  (15 exit_grid_v1 + 10 wait_grid_v1 + 6 disp_gate_v1 = 31)",
        "- TrialLedger max()-basis: 15 (largest single declared budget)",
        "- Both semantics disclosed per §0.5.6 of gap-map adjudication",
        "- This study is display-only per US_BOARD_MEASUREMENT §Study 3",
        "- `gross_mult_live = 1.0` HARD CONSTRAINT (RUL-F3.7)",
        "- Nulls printed, not hidden. DEFER is a valid result.",
        "- Episode-clustered bootstrap CIs where n_clusters >= 25; otherwise sparse note printed.",
        "- **PANEL SURVIVORSHIP:** All CSD percentile assignments carry survivor-only bias.",
        "  See mandatory disclosure at top of report. Trailing-252d sensitivity basis is",
        "  less affected (avoids 60-year survivor-only denominator).",
        "- **CLUSTERING:** Uses prereg-spec contiguous ±30d BLOCK clusters (cross-ticker),",
        "  NOT the original per-ticker ISO-week scheme. CIs are wider (more conservative).",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    summary = run(
        summary_out=_SUMMARY_OUT,
        report_out=_REPORT_OUT,
        verbose=True,
    )
    print("\n[DONE]")
    print(f"  Overall verdict: {summary.get('overall_verdict', '?')}")
    print(f"  N included fires: {summary.get('fire_population', {}).get('n_included', '?'):,}")
    n_defers = len(summary.get("defer_reasons", []))
    if n_defers:
        print(f"  Defer reasons ({n_defers}):")
        for r in summary.get("defer_reasons", []):
            print(f"    - {r}")


if __name__ == "__main__":
    main()
