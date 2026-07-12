"""S10 Margin-Inflection Reclaim Phase-0 — per-fire grading + statistics.

Grading:
  terminal_state at clean15_126 (primary) and clean8_21 (context).
  Uses engine.grading.terminal_state with same_bar=False (next-bar fill).

Statistics:
  - Wilson lower bound for proportions (per PREREG)
  - Episode-clustered p-value via block bootstrap over CALENDAR-TIME blocks
    >= 126 trading days (NOT ticker-only — mandatory time-confound control)
  - Effective-n = # distinct 126-day time-episodes with fires
  - BH-FDR via engine.validation.benjamini_hochberg

Terminal states: STOPPED, DEAD_MONEY, CUSHIONED, CLEAN_LIFTOFF (or None=immature)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

# Calendar-time block size for episode clustering (>= liftoff_horizon = 126 td)
# We use 126 TRADING DAYS ≈ 6 calendar months
EPISODE_BLOCK_TD    = 126
N_BOOTSTRAP         = 2000
LIFTOFF_HORIZON_126 = 126
LIFTOFF_HORIZON_21  = 21


# ── Grading ───────────────────────────────────────────────────────────────

def grade_fire(
    fire_date: pd.Timestamp,
    close_series: pd.Series,
) -> dict:
    """Grade one fire at clean15_126 (primary) and clean8_21 (context).

    Uses engine.grading.terminal_state with same_bar=False (next-bar fill,
    §1.2 mandate).

    Returns dict with keys:
      state_126, fill_date_126, fill_px, stopped_126, dead_money_126,
      cushioned_126, liftoff_126, ret_at_read_126,
      state_21, liftoff_21
    """
    from engine import grading as _grading

    result = {
        "state_126": None, "fill_date_126": None, "fill_px": None,
        "stopped_126": None, "dead_money_126": None,
        "cushioned_126": None, "liftoff_126": None, "ret_at_read_126": None,
        "state_21": None, "liftoff_21": None,
    }

    if close_series is None or close_series.empty:
        return result

    # clean15_126 (primary)
    try:
        g126 = _grading.terminal_state(
            close_series, fire_date,
            liftoff_mult=_grading.LIFTOFF_15,
            liftoff_horizon=LIFTOFF_HORIZON_126,
            same_bar=False,
        )
        # state is a string constant ("STOPPED", "DEAD_MONEY", etc.) or None
        s126 = g126.get("state")
        result["state_126"]       = str(s126) if s126 is not None else None
        result["fill_date_126"]   = g126.get("fill_date")
        result["fill_px"]         = g126.get("entry_price")
        result["ret_at_read_126"] = g126.get("ret_at_read")
        if s126 is not None:
            result["stopped_126"]    = int(s126 == "STOPPED")
            result["dead_money_126"] = int(s126 == "DEAD_MONEY")
            result["cushioned_126"]  = int(s126 in ("CUSHIONED", "CLEAN_LIFTOFF"))
            result["liftoff_126"]    = int(s126 == "CLEAN_LIFTOFF")
    except Exception as exc:
        log.debug("grade_fire 126 error: %s", exc)

    # clean8_21 (context)
    try:
        g21 = _grading.terminal_state(
            close_series, fire_date,
            liftoff_mult=1.08,
            liftoff_horizon=LIFTOFF_HORIZON_21,
            same_bar=False,
        )
        s21 = g21.get("state")
        result["state_21"]   = str(s21) if s21 is not None else None
        result["liftoff_21"] = int(s21 == "CLEAN_LIFTOFF") if s21 is not None else None
    except Exception as exc:
        log.debug("grade_fire 21 error: %s", exc)

    return result


def grade_fire_batch(fires_df: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Grade all fires in fires_df using the panel wide price DataFrame.

    fires_df: must have columns ['ticker', 'fire_date'].
    panel: wide DataFrame (DatetimeIndex rows, ticker columns).

    Appends grade columns in-place-copy and returns.
    """
    grade_cols = [
        "state_126", "fill_date_126", "fill_px",
        "stopped_126", "dead_money_126", "cushioned_126", "liftoff_126",
        "ret_at_read_126", "state_21", "liftoff_21",
    ]
    # Initialize
    for col in grade_cols:
        fires_df[col] = None

    rows_out = []
    for idx, row in fires_df.iterrows():
        ticker    = row["ticker"]
        fire_date = pd.Timestamp(row["fire_date"])

        if ticker not in panel.columns:
            rows_out.append(dict(row))
            continue

        close_s = panel[ticker].dropna()
        g = grade_fire(fire_date, close_s)

        r = dict(row)
        r.update(g)
        rows_out.append(r)

    if not rows_out:
        return fires_df

    return pd.DataFrame(rows_out)


# ── Wilson lower bound ────────────────────────────────────────────────────

def wilson_lower(k: int, n: int, z: float = 1.645) -> float:
    """Wilson score lower bound at z (default 1.645 = 90% one-sided).

    Returns 0.0 when n == 0.
    """
    if n == 0:
        return 0.0
    p = k / n
    denominator = 1 + z * z / n
    center = p + z * z / (2 * n)
    spread = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (center - spread) / denominator)


# ── Calendar-time episode clustering ─────────────────────────────────────

def assign_calendar_episodes(
    fire_dates: pd.Series,
    block_td: int = EPISODE_BLOCK_TD,
) -> pd.Series:
    """Assign an integer episode ID to each fire based on calendar-time blocks.

    Method: divide the full era into non-overlapping 126-trading-day blocks
    anchored at the earliest fire date, assign each fire to the block it falls in.
    This is the mandatory time-confound control — NOT ticker-based.

    Returns a pd.Series of integer episode IDs aligned to fire_dates.
    """
    if len(fire_dates) == 0:
        return pd.Series(dtype=int)

    dates = pd.to_datetime(fire_dates)
    sorted_dates = dates.sort_values()
    epoch = sorted_dates.iloc[0]

    # Build a trading-day calendar over the full era to count td-blocks
    # We approximate: use 252 td/year = 0.3968 td/day
    # Precise block assignment: sort all fire dates, assign block index
    # as floor((days_from_epoch) / (block_td * 1.4))
    # 1.4 = approximate calendar-day to trading-day conversion

    def _block(d: pd.Timestamp) -> int:
        cal_days = max(0, (d - epoch).days)
        return int(cal_days / (block_td * 1.4))  # approx td-block index

    episode_ids = dates.map(_block)
    return episode_ids


def effective_n_episodes(fire_dates: pd.Series,
                         block_td: int = EPISODE_BLOCK_TD) -> int:
    """Count distinct 126-td calendar-time episodes with at least one fire."""
    if len(fire_dates) == 0:
        return 0
    ep = assign_calendar_episodes(fire_dates, block_td)
    return int(ep.nunique())


# ── Block bootstrap for p-value and CI ───────────────────────────────────

def block_bootstrap_pvalue(
    values_s10: np.ndarray,
    values_cmp: np.ndarray,
    episode_s10: np.ndarray,
    episode_cmp: np.ndarray,
    stat_fn,
    n_draws: int = N_BOOTSTRAP,
    rng_seed: int = 42,
) -> dict:
    """Episode-clustered bootstrap p-value for (stat_s10 - stat_cmp) > 0.

    Resamples calendar-time episodes with replacement from the JOINT episode
    set, applies stat_fn to the S10 and comparator fires within each draw,
    then computes the fraction of draws where the observed difference exceeds 0.

    Returns {
      'point_s10': float,
      'point_cmp': float,
      'point_diff': float,
      'p_value': float,
      'ci_lo_90': float,
      'ci_hi_90': float,
      'n_episodes_s10': int,
      'n_episodes_cmp': int,
      'n_episodes_joint': int,
    }
    """
    # Remove NaNs
    v_s10 = np.asarray(values_s10, dtype=float)
    v_cmp = np.asarray(values_cmp, dtype=float)
    e_s10 = np.asarray(episode_s10, dtype=int)
    e_cmp = np.asarray(episode_cmp, dtype=int)

    mask_s10 = ~np.isnan(v_s10)
    mask_cmp = ~np.isnan(v_cmp)
    v_s10, e_s10 = v_s10[mask_s10], e_s10[mask_s10]
    v_cmp, e_cmp = v_cmp[mask_cmp], e_cmp[mask_cmp]

    if len(v_s10) == 0 or len(v_cmp) == 0:
        return {
            "point_s10": np.nan, "point_cmp": np.nan, "point_diff": np.nan,
            "p_value": np.nan, "ci_lo_90": np.nan, "ci_hi_90": np.nan,
            "n_episodes_s10": 0, "n_episodes_cmp": 0, "n_episodes_joint": 0,
        }

    pt_s10 = stat_fn(v_s10)
    pt_cmp = stat_fn(v_cmp)
    pt_diff = pt_s10 - pt_cmp

    # Joint episode space
    all_eps = np.unique(np.concatenate([e_s10, e_cmp]))
    n_eps   = len(all_eps)

    # Index maps for fast lookup
    s10_by_ep: dict[int, np.ndarray] = {}
    cmp_by_ep: dict[int, np.ndarray] = {}
    for ep in all_eps:
        s10_by_ep[ep] = v_s10[e_s10 == ep]
        cmp_by_ep[ep] = v_cmp[e_cmp == ep]

    rng = np.random.default_rng(rng_seed)
    boot_diffs = np.empty(n_draws)

    for b in range(n_draws):
        drawn = rng.choice(all_eps, size=n_eps, replace=True)
        bs10 = np.concatenate([s10_by_ep[ep] for ep in drawn])
        bcmp = np.concatenate([cmp_by_ep[ep] for ep in drawn])
        if len(bs10) == 0 or len(bcmp) == 0:
            boot_diffs[b] = np.nan
            continue
        boot_diffs[b] = stat_fn(bs10) - stat_fn(bcmp)

    boot_diffs = boot_diffs[~np.isnan(boot_diffs)]
    if len(boot_diffs) == 0:
        p_val = np.nan
        ci_lo = ci_hi = np.nan
    else:
        # Two-sided p-value for diff != 0; but we report one-tailed for stop-out reduction
        # p = fraction of boots where diff >= observed (for stop-out: lower is better,
        # so diff < 0 is good; p = fraction of boots where diff <= observed_diff)
        # Convention: p-value = P(bootstrap diff <= observed diff) for stop-out reduction
        p_val = float(np.mean(boot_diffs <= pt_diff))
        ci_lo = float(np.nanquantile(boot_diffs, 0.05))
        ci_hi = float(np.nanquantile(boot_diffs, 0.95))

    return {
        "point_s10":       float(pt_s10),
        "point_cmp":       float(pt_cmp),
        "point_diff":      float(pt_diff),
        "p_value":         float(p_val),
        "ci_lo_90":        ci_lo,
        "ci_hi_90":        ci_hi,
        "n_episodes_s10":  int(len(np.unique(e_s10))),
        "n_episodes_cmp":  int(len(np.unique(e_cmp))),
        "n_episodes_joint": int(n_eps),
    }


def rate_stat(values: np.ndarray) -> float:
    """Mean of non-NaN values (for proportions like stop-out rate, liftoff rate)."""
    v = values[~np.isnan(values)]
    return float(np.mean(v)) if len(v) > 0 else np.nan


# ── Per-name majority ─────────────────────────────────────────────────────

def per_name_majority(fires_s10: pd.DataFrame, fires_cmp: pd.DataFrame,
                      metric_col: str) -> dict:
    """K3 analogue: fraction of names where S10 metric beats comparator.

    For each name that appears in both groups, compare the mean metric_col value.
    Returns fraction of such names where S10 wins.
    """
    common_tickers = set(fires_s10["ticker"]) & set(fires_cmp["ticker"])
    if not common_tickers:
        return {"n_common": 0, "pct_names_s10_wins": np.nan}

    wins = 0
    for t in common_tickers:
        s10_vals = fires_s10.loc[fires_s10["ticker"] == t, metric_col].dropna()
        cmp_vals = fires_cmp.loc[fires_cmp["ticker"] == t, metric_col].dropna()
        if len(s10_vals) == 0 or len(cmp_vals) == 0:
            continue
        if float(s10_vals.mean()) < float(cmp_vals.mean()):  # lower stop-out = better
            wins += 1

    total = len(common_tickers)
    return {
        "n_common": total,
        "pct_names_s10_wins": wins / total if total > 0 else np.nan,
    }


# ── Temporal half stability ────────────────────────────────────────────────

def temporal_half_split(fires_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split fires_df into two equal-count temporal halves by fire_date sort."""
    df = fires_df.sort_values("fire_date").reset_index(drop=True)
    mid = len(df) // 2
    return df.iloc[:mid].copy(), df.iloc[mid:].copy()


# ── Depth balance (K4) ────────────────────────────────────────────────────

def compute_washout_depth(
    fires_df: pd.DataFrame,
    panel: pd.DataFrame,
) -> pd.DataFrame:
    """Compute the capitulation drawdown depth for each fire.

    Depth = trough / prior_126_high - 1 (the washout_ctx drawdown).
    Stratified by quartile for K4.
    """
    depths = []
    for _, row in fires_df.iterrows():
        ticker    = row["ticker"]
        fire_date = pd.Timestamp(row["fire_date"])
        depth     = np.nan

        if ticker in panel.columns:
            close_s = panel[ticker].dropna()
            sliced = close_s[close_s.index <= fire_date]
            arr = sliced.to_numpy()
            n = len(arr)
            if n >= 308:
                # Replicate washout_ctx internal logic: argmin over trailing 91 bars
                window = arr[n - 91:]
                local_min = int(np.argmin(window))
                capit_pos = (n - 91) + local_min
                if capit_pos >= 126:
                    prior_max = float(np.nanmax(arr[capit_pos - 126: capit_pos]))
                    capit_val = float(arr[capit_pos])
                    if prior_max > 0:
                        depth = capit_val / prior_max - 1.0

        depths.append(depth)

    fires_df = fires_df.copy()
    fires_df["washout_depth"] = depths
    return fires_df


# ── Wait cost ─────────────────────────────────────────────────────────────

def compute_wait_days(fires_df: pd.DataFrame) -> pd.DataFrame:
    """Compute arming wait = fire_date - q3_filed (calendar days)."""
    fires_df = fires_df.copy()
    fires_df["wait_days"] = (
        pd.to_datetime(fires_df["fire_date"]) - pd.to_datetime(fires_df["q3_filed"])
    ).dt.days
    return fires_df
