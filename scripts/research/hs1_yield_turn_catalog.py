"""HS-1 Yield-turn event catalog (RIC masterplan §5.3 HS-1).

Pre-registered historical study: 3B StochRSI and RSI-MACD cross events on
FRED yield series (DGS2, DGS5, DGS10, DGS20, DGS30, DFII10, T10Y2Y),
1990-01-01 to 2026-06-30 estimation window, with 2024-01-01+ OOS slice printed
descriptively.

Output:
  reports/ric-hs1-yield-turn-catalog.md
  reports/ric_hs1_yield_turn_catalog.json

Usage:
  python3 scripts/research/hs1_yield_turn_catalog.py [--no-perm]
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_FRED = _REPO_ROOT / "data" / "fred"
_YAHOO = _REPO_ROOT / "data" / "yahoo"
_REPORT_OUT = _REPO_ROOT / "reports" / "ric-hs1-yield-turn-catalog.md"
_JSON_OUT = _REPO_ROOT / "reports" / "ric_hs1_yield_turn_catalog.json"

# ---------------------------------------------------------------------------
# Study constants (frozen spec)
# ---------------------------------------------------------------------------
ESTIMATION_START = "1990-01-01"
ESTIMATION_END = "2026-06-30"
OOS_START = "2024-01-01"
DATA_END = "2026-07-10"  # last available bar for grading

# DGS20 structural gap: data absent 1987-01-01 to 1993-09-30 (2466-day gap in parquet).
# Use DGS20 only from this date; fresh indicator warmup required.
DGS20_START = "1993-10-01"

# DGS30 has no confirmed null gap in the parquet (checked: 2002-2006 rows are present).
# The spec mentions a potential 2002-02 to 2006-02 discontinuation; since the data is
# present (no NaN gap detected), we use the full series from 1990 with a notation.
DGS30_START = "1990-01-01"

ERA_SPLITS = {
    "pre_2010": ("1990-01-01", "2009-12-31"),
    "2010_2020": ("2010-01-01", "2020-12-31"),
    "2021_plus": ("2021-01-01", "2026-06-30"),
}

N_PERM = 2000
PERM_SEED = 42

# Minimum events for episode permutation test
MIN_N_FOR_PERM = 8

# Episode definition: events within 21 trading-day span = one episode
EPISODE_GAP_TDAYS = 21

# ---------------------------------------------------------------------------
# Import canon math from engine (per spec: IMPORT, do not re-implement)
# ---------------------------------------------------------------------------
from engine.cycles import stoch_rsi, macd_parts, rsi  # noqa: E402

# ---------------------------------------------------------------------------
# Series roster
# ---------------------------------------------------------------------------
SERIES_MAP = {
    "DGS2":   ("fred", "DGS2.parquet",   "us2y"),
    "DGS5":   ("fred", "DGS5.parquet",   "us5y"),
    "DGS10":  ("fred", "DGS10.parquet",  "us10y"),
    "DGS20":  ("fred", "DGS20.parquet",  "us20y"),
    "DGS30":  ("fred", "DGS30.parquet",  "us30y"),
    "DFII10": ("fred", "DFII10.parquet", "us10y_real"),
    "T10Y2Y": ("fred", "T10Y2Y.parquet", "spread_2s10s"),
}

LONG_END = {"DGS10", "DGS20", "DGS30"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_series(series_id: str) -> pd.Series:
    """Load a FRED yield series, return daily indexed Series named series_id."""
    src, fname, col = SERIES_MAP[series_id]
    path = _FRED / fname
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    s = df[col].sort_index()

    # DGS20: truncate to post-gap start (avoid bridge across the 1987-1993 gap)
    if series_id == "DGS20":
        s = s[s.index >= DGS20_START]

    # Apply estimation window
    s = s[(s.index >= ESTIMATION_START) & (s.index <= DATA_END)]
    s = s.dropna()
    s.name = series_id
    return s


def _load_move() -> pd.Series:
    """Load MOVE index close."""
    path = _YAHOO / "_MOVE.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    s = df["close"].sort_index().dropna()
    s.name = "MOVE"
    return s


# ---------------------------------------------------------------------------
# 3B grid construction (canon idiom: resample('3B').last().dropna())
# ---------------------------------------------------------------------------

def _make_3b_grid(daily_s: pd.Series, series_id: str) -> pd.DataFrame:
    """Build the 3B resampled grid with oscillators.

    Returns DataFrame with columns: close, srsi, hist, cross_up_srsi,
    cross_dn_srsi, cross_up_macd, cross_dn_macd, daily_date (mapped from 3B bars).
    """
    grid = daily_s.resample("3B").last().dropna()
    if len(grid) < 40:
        log.warning("%s: 3B grid too short (%d bars)", series_id, len(grid))
        return pd.DataFrame()

    srsi_s = stoch_rsi(grid)
    mp = macd_parts(grid)
    hist = mp["hist"]

    # Vectorized event detection per spec (mirroring _tf_state logic)
    # stoch bullish cross (out of oversold): srsi[t] >= 20 AND any(srsi[t-3:t] < 20)
    # Window: look back 3 bars (t-3:t exclusive of t)
    srsi_arr = srsi_s.values
    hist_arr = hist.values

    n = len(grid)
    cross_up_srsi = np.zeros(n, dtype=bool)
    cross_dn_srsi = np.zeros(n, dtype=bool)
    cross_up_macd = np.zeros(n, dtype=bool)
    cross_dn_macd = np.zeros(n, dtype=bool)

    # FIX 2 (canon warmup): engine/_tf_state returns {} when len(close) < 40,
    # so canonical event detection emits nothing in the first 39 bars of the grid.
    # Requiring i >= 39 matches canon exactly and eliminates ~11 phantom grid-start
    # events that fired at i=3..38 (warmup zone where oscillators are unreliable).
    for i in range(39, n):
        sv = srsi_arr[i]
        hv = hist_arr[i]
        # skip NaN
        if not np.isfinite(sv) or not np.isfinite(hv):
            continue
        prev_s = srsi_arr[i - 3:i]
        prev_h = hist_arr[i - 3:i]
        # Only consider where prev values are finite
        prev_s_fin = prev_s[np.isfinite(prev_s)]
        prev_h_fin = prev_h[np.isfinite(prev_h)]
        if len(prev_s_fin) == 0 or len(prev_h_fin) == 0:
            continue

        # StochRSI crosses
        if sv >= 20 and (prev_s_fin < 20).any():
            cross_up_srsi[i] = True
        if sv <= 80 and (prev_s_fin > 80).any():
            cross_dn_srsi[i] = True

        # MACD crosses
        if hv > 0 and (prev_h_fin <= 0).any():
            cross_up_macd[i] = True
        if hv < 0 and (prev_h_fin >= 0).any():
            cross_dn_macd[i] = True

    out = pd.DataFrame(
        {
            "close": grid.values,
            "srsi": srsi_arr,
            "hist": hist_arr,
            "cross_up_srsi": cross_up_srsi,
            "cross_dn_srsi": cross_dn_srsi,
            "cross_up_macd": cross_up_macd,
            "cross_dn_macd": cross_dn_macd,
        },
        index=grid.index,
    )
    return out


# ---------------------------------------------------------------------------
# Quality tag (washout_turn for yields, per P4 parenthetical)
# ---------------------------------------------------------------------------

def _quality_annotation(srsi_series: pd.Series, event_idx: int,
                         direction: str) -> tuple[str, float]:
    """Return (quality_tag, depth_value) for a cross event.

    Vocabulary aligned to IHM engine (engine/index_momentum.py) and §3 P4 spec:
      Bull crosses: washout_turn (coming from <=20 zone), standard (other)
      Bear crosses: trap_zone (coming from >=80 overbought zone, mirrors IHM trap_zone
                   concept applied to the overbought extreme), standard (other)

    The IHM engine uses washout_turn/trap_zone/ordinary for index events; for yield
    MACD/stoch cross events we use washout_turn/trap_zone to maintain vocabulary
    consistency with the downstream P4 organ, using 'standard' in place of 'ordinary'
    for the non-extreme bucket.
    """
    look_back = max(0, event_idx - 5)
    window = srsi_series.iloc[look_back:event_idx].dropna()
    if len(window) == 0:
        return "standard", np.nan
    if direction == "bull":
        depth = float(window.min())
        tag = "washout_turn" if depth <= 20 else "standard"
    else:
        depth = float(window.max())
        # 'trap_zone' = bearish cross from overbought (mirrors IHM trap_zone vocabulary)
        tag = "trap_zone" if depth >= 80 else "standard"
    return tag, depth


# ---------------------------------------------------------------------------
# Event extraction from 3B grid
# ---------------------------------------------------------------------------

def _extract_events_from_grid(series_id: str, grid: pd.DataFrame,
                               include_post_estimation: bool = False) -> list[dict]:
    """Extract all four event types from a 3B grid DataFrame.

    By default, only events within [ESTIMATION_START, ESTIMATION_END] are returned.
    If include_post_estimation=True, events up to DATA_END are also included
    (used for the case study display of the §5.4 archetype event).
    """
    if grid.empty:
        return []

    srsi_s = grid["srsi"]
    events = []

    for ec, direction, col_flag in [
        ("stoch_cross_up", "bull", "cross_up_srsi"),
        ("stoch_cross_dn", "bear", "cross_dn_srsi"),
        ("macd_cross_up", "bull", "cross_up_macd"),
        ("macd_cross_dn", "bear", "cross_dn_macd"),
    ]:
        fire_mask = grid[col_flag]

        for i, dt in enumerate(grid.index):
            if not fire_mask.iloc[grid.index.get_loc(dt)]:
                continue
            idx = grid.index.get_loc(dt)
            tag, depth = _quality_annotation(srsi_s, idx, direction)

            # Determine if within estimation window or the extended display window
            in_estimation = (pd.Timestamp(ESTIMATION_START) <= dt <= pd.Timestamp(ESTIMATION_END))
            in_display = include_post_estimation and (dt <= pd.Timestamp(DATA_END))

            if not in_estimation and not in_display:
                continue

            events.append({
                "series":       series_id,
                "event_class":  ec,
                "direction":    direction,
                "date_3b":      dt,  # 3B bar date
                "daily_date":   dt,  # event date = daily date of 3B bar close
                "quality_tag":  tag,
                "srsi_depth":   round(depth, 1) if np.isfinite(depth) else None,
                "srsi_at_cross": round(float(grid["srsi"].iloc[grid.index.get_loc(dt)]), 1)
                    if np.isfinite(float(grid["srsi"].iloc[grid.index.get_loc(dt)])) else None,
                "in_estimation_window": bool(in_estimation),
                "post_estimation": bool(not in_estimation),
            })

    return events


# ---------------------------------------------------------------------------
# 200dma side (causal, on daily series)
# ---------------------------------------------------------------------------

def _add_200dma_side(events: list[dict], daily_series: pd.Series,
                     series_id: str) -> list[dict]:
    """Annotate each event with above/below 200dma as of event date."""
    ma200 = daily_series.rolling(200, min_periods=200).mean()
    for ev in events:
        dt = ev["daily_date"]
        # Use last available daily bar at or before event date
        idx = ma200.index.searchsorted(dt, side="right") - 1
        if idx < 0:
            ev["above_200dma"] = None
            continue
        close_val = daily_series.iloc[idx]
        ma_val = ma200.iloc[idx]
        if np.isfinite(close_val) and np.isfinite(ma_val) and ma_val > 0:
            ev["above_200dma"] = bool(close_val > ma_val)
        else:
            ev["above_200dma"] = None
    return events


# ---------------------------------------------------------------------------
# Forward grading (h21, h63) on daily series
# ---------------------------------------------------------------------------

def _grade_events(events: list[dict], daily_series: pd.Series) -> list[dict]:
    """Add h21/h63 outcome columns.

    Direction hit for bullish event: yield HIGHER at t+h (yield momentum up).
    Move in bp = 100 * (y_{t+h} - y_t).
    MFE/MAE in bp over the horizon (favorable = event direction).
    """
    s = daily_series.dropna()
    dates = s.index

    for ev in events:
        dt = ev["daily_date"]
        # Find the event date's position in daily series
        idx = dates.searchsorted(dt, side="right") - 1
        if idx < 0 or idx >= len(s):
            ev.update({k: None for k in [
                "y0", "y21", "y63",
                "h21_hit", "h63_hit",
                "h21_move_bp", "h63_move_bp",
                "h21_mfe_bp", "h21_mae_bp",
                "h63_mfe_bp", "h63_mae_bp",
                "h21_resolved", "h63_resolved",
            ]})
            continue

        y0 = float(s.iloc[idx])
        ev["y0"] = round(y0, 4)

        direction = ev["direction"]  # "bull" or "bear"

        for h, key in [(21, "h21"), (63, "h63")]:
            end_idx = idx + h
            if end_idx >= len(s):
                ev[f"{key}_hit"] = None
                ev[f"{key}_move_bp"] = None
                ev[f"{key}_mfe_bp"] = None
                ev[f"{key}_mae_bp"] = None
                ev[f"{key}_resolved"] = False
                if key == "h21":
                    ev["y21"] = None
                else:
                    ev["y63"] = None
                continue

            window = s.iloc[idx + 1:end_idx + 1]
            yh = float(s.iloc[end_idx])
            move_bp = round((yh - y0) * 100, 2)

            if key == "h21":
                ev["y21"] = round(yh, 4)
            else:
                ev["y63"] = round(yh, 4)

            ev[f"{key}_move_bp"] = move_bp
            ev[f"{key}_resolved"] = True

            # Direction hit: bull = yield higher (move_bp > 0)
            if direction == "bull":
                ev[f"{key}_hit"] = bool(move_bp > 0)
            else:
                ev[f"{key}_hit"] = bool(move_bp < 0)

            # MFE/MAE (favorable = event direction)
            if len(window) == 0:
                ev[f"{key}_mfe_bp"] = None
                ev[f"{key}_mae_bp"] = None
                continue

            moves = ((window - y0) * 100).values
            if direction == "bull":
                mfe = float(moves.max())   # best favorable = max upward move
                mae = float(moves.min())   # worst = max downward excursion
            else:
                mfe = float((-moves).max())  # best for bear = max downward move
                mae = float((-moves).min())  # worst = max upward excursion (negative for bear)

            ev[f"{key}_mfe_bp"] = round(mfe, 2)
            ev[f"{key}_mae_bp"] = round(mae, 2)

    return events


# ---------------------------------------------------------------------------
# Base rates (unconditional P(yield higher at t+h))
# ---------------------------------------------------------------------------

def _compute_base_rates(
    daily_series: pd.Series,
    era_start: str,
    era_end: str,
    above_200dma: bool | None,
) -> dict:
    """Unconditional P(yield higher at t+h) for a given era and 200dma side.

    Returns dict with h21, h63 base rates and n.

    IMPORTANT: The 200dma is computed on the FULL daily_series (same as
    _add_200dma_side uses for event annotation), then restricted to the era window.
    Warmup days where the 200dma is NaN are EXCLUDED from the denominator (not
    filled to False). This ensures the base-rate stratum is consistent with the
    event-level above/below annotation, preventing the ~14% mislabeling that
    occurs in short eras (e.g., 2021_plus) when the 200dma is recomputed on an
    era-sliced series.
    """
    # Compute 200dma on the FULL series (same definition as event annotation)
    ma200_full = daily_series.rolling(200, min_periods=200).mean()

    # Restrict series to era window
    s = daily_series[
        (daily_series.index >= era_start) & (daily_series.index <= era_end)
    ].dropna()

    if len(s) < 22:
        return {"h21_base": None, "h63_base": None, "n_base": 0}

    # Reindex the full-series 200dma to the era window (preserves full-history warmup)
    ma200 = ma200_full.reindex(s.index)
    # above = True only where both close and 200dma are valid (exclude warmup NaNs)
    above = pd.Series(np.nan, index=s.index, dtype=object)
    valid_ma = ma200.notna()
    above[valid_ma] = (s[valid_ma] > ma200[valid_ma])

    results = {"h21_base": None, "h63_base": None, "n_base": 0}
    for h, key in [(21, "h21"), (63, "h63")]:
        y_fwd = s.shift(-h)
        diff_bp = (y_fwd - s) * 100
        # FIX 1 (base-rate tail bias): unresolved tail days (NaN forward values)
        # must be excluded from the denominator, not counted as "not up".
        # Mirror _grade_events' unresolved-horizon exclusion via a nullable Series.
        direction_up = pd.Series(
            np.where(diff_bp.notna(), diff_bp > 0, np.nan),
            index=s.index,
        )

        if above_200dma is None:
            # All days where 200dma is valid (or, for the None/all-sides stratum, any day)
            mask = pd.Series(True, index=s.index)
        elif above_200dma:
            # Include only days confirmed above (exclude NaN warmup)
            mask = (above == True)  # noqa: E712
        else:
            # Include only days confirmed below (exclude NaN warmup)
            mask = (above == False)  # noqa: E712

        valid = mask & direction_up.notna()
        n_valid = valid.sum()
        if n_valid == 0:
            results[f"{key}_base"] = None
        else:
            results[f"{key}_base"] = round(float(direction_up[valid].mean()), 4)
        results["n_base"] = int(n_valid)

    return results


# ---------------------------------------------------------------------------
# Era split helper
# ---------------------------------------------------------------------------

def _era_of(dt: pd.Timestamp) -> str:
    y = dt.year
    if y < 2010:
        return "pre_2010"
    elif y <= 2020:
        return "2010_2020"
    else:
        return "2021_plus"


# ---------------------------------------------------------------------------
# Within-month episode permutation p-value
# ---------------------------------------------------------------------------

def _perm_p_h21(
    events_df: pd.DataFrame,
    series_id: str,
    event_class: str,
    direction: str,
    daily_series: pd.Series,
    n_perm: int = N_PERM,
    seed: int = PERM_SEED,
) -> float | None:
    """Within-month episode-label permutation p-value (TWO-SIDED) for h21 direction hit.

    This IS the house-law DT-R14 statistic: within-month episode-label permutation
    with episode-first-month blocking (two-sided). The inferential unit is the
    episode, not the individual day.

    Method:
    1. Collapse events into episodes: same-series, same-direction events whose
       consecutive trading-day gap is <=EPISODE_GAP_TDAYS (21 trading days) belong
       to the same episode. An episode is represented by its FIRST event day and
       blocked to the calendar month of that first event.
    2. Observed statistic: mean h21_hit of the first event day across all episodes
       (where h21 is resolved).
    3. Null draw (one permutation): for each calendar month hosting k episodes,
       draw k random trading days WITHOUT replacement from that month's trading days
       in the SAME daily yield series (era-unrestricted; only days where h21 outcome
       is computable — i.e., at least 21 daily bars remain after the day). Score each
       drawn day's h21 direction-hit. Recompute episode-level hit rate over all drawn
       pseudo-episodes. This preserves calendar composition (per-month episode counts)
       and treats the episode as the inferential unit.
    4. Repeat n_perm times to build a null distribution.
    5. Two-sided p = min(1, 2 * min(P(perm >= obs), P(perm <= obs))), with both
       inequalities including ties.

    Sub-rows (era/stratum splits) display None because only the pooled full-window
    construction is tested (as specified in HS-1 §5.3).

    Computed at the FULL-WINDOW (series, event_class, direction) level only,
    for event classes with n_episodes >= MIN_N_FOR_PERM (8).
    """
    sub = events_df[
        (events_df["series"] == series_id)
        & (events_df["event_class"] == event_class)
        & (events_df["direction"] == direction)
        & (events_df["h21_resolved"] == True)  # noqa: E712
        & (events_df["h21_hit"].notna())
    ].copy()

    if len(sub) < MIN_N_FOR_PERM:
        return None

    sub = sub.sort_values("daily_date").reset_index(drop=True)
    sub["daily_date"] = pd.to_datetime(sub["daily_date"])

    # --- Step 1: collapse events into episodes (unit = trading days between consecutive
    # events of the same series+direction; gap > EPISODE_GAP_TDAYS tdays => new episode) ---
    # Build a trading-day calendar from the daily series (business days present in data)
    s = daily_series.dropna()
    tday_set = set(s.index)
    # Precompute sorted tday array for counting
    tday_arr = np.array(sorted(tday_set))

    ep_labels = []
    ep = 0
    prev_dt = None
    prev_tday_idx = None
    for _, row in sub.iterrows():
        dt = row["daily_date"]
        # Find nearest trading day at or before dt in the data
        pos = np.searchsorted(tday_arr, dt, side="right") - 1
        if prev_dt is None:
            ep_labels.append(ep)
        else:
            # Trading-day distance: count tday_arr positions between prev and current
            tdays_gap = pos - prev_tday_idx
            if tdays_gap > EPISODE_GAP_TDAYS:
                ep += 1
            ep_labels.append(ep)
        prev_dt = dt
        prev_tday_idx = pos
    sub["episode"] = ep_labels

    # Use first event of each episode as representative
    ep_reps = sub.groupby("episode").first().reset_index()
    ep_reps["month"] = ep_reps["daily_date"].dt.to_period("M")
    ep_reps["h21_hit"] = ep_reps["h21_hit"].astype(float)

    n_eps = len(ep_reps)
    if n_eps < MIN_N_FOR_PERM:
        return None

    # --- Step 2: observed statistic ---
    obs_stat = float(ep_reps["h21_hit"].mean())

    # --- Step 3: build within-month pool of eligible trading days ---
    # For each month that hosts >=1 episode, collect all trading days in that month
    # for which h21 is computable (at least 21 daily bars remaining after the day).
    # "Era-unrestricted" = use all trading days in the daily series for that month.
    episode_months = ep_reps["month"].unique()
    eps_per_month = ep_reps.groupby("month").size().to_dict()

    # Precompute h21 direction-hit for every day in the series where it is computable
    n_s = len(s)
    s_vals = s.values
    s_idx = s.index

    # For each day i, h21 hit = direction win if outcome at i+21 satisfies direction
    # Only days where i+21 < n_s are eligible
    max_eligible_i = n_s - 22  # i+21 <= n_s - 1 => i <= n_s - 22
    if max_eligible_i < 0:
        return None

    eligible_dates = s_idx[:max_eligible_i + 1]
    eligible_y0 = s_vals[:max_eligible_i + 1]
    eligible_yh = s_vals[21:max_eligible_i + 22]  # y_{i+21}
    if direction == "bull":
        eligible_hits = (eligible_yh > eligible_y0).astype(float)
    else:
        eligible_hits = (eligible_yh < eligible_y0).astype(float)

    # Build month -> (eligible_dates_in_month, eligible_hits_in_month) mapping
    # Only for months that host episodes
    eligible_dates_period = pd.DatetimeIndex(eligible_dates).to_period("M")
    month_to_eligible: dict = {}
    for m in episode_months:
        mask = (eligible_dates_period == m)
        if mask.any():
            month_to_eligible[m] = eligible_hits[mask]

    months_with_pool = [m for m in episode_months if m in month_to_eligible
                        and len(month_to_eligible[m]) >= eps_per_month.get(m, 1)]
    if len(months_with_pool) < 2:
        return None

    # --- Step 4: permutation loop ---
    rng = np.random.default_rng(seed)
    perm_stats = []

    for _ in range(n_perm):
        drawn_hits = []
        for m in months_with_pool:
            pool = month_to_eligible[m]
            k = eps_per_month.get(m, 1)
            # Draw k days WITHOUT replacement; pool guaranteed to have >= k items
            chosen = rng.choice(len(pool), size=k, replace=False)
            drawn_hits.extend(pool[chosen].tolist())
        if drawn_hits:
            perm_stats.append(float(np.mean(drawn_hits)))

    if len(perm_stats) < 100:
        return None

    perm_arr = np.array(perm_stats)
    # Two-sided p (including ties in both tails)
    p_high = float((perm_arr >= obs_stat).mean())
    p_low = float((perm_arr <= obs_stat).mean())
    p_val = float(min(1.0, 2.0 * min(p_high, p_low)))
    return round(p_val, 4)


# ---------------------------------------------------------------------------
# Confluence tag detection
# ---------------------------------------------------------------------------

def _detect_confluence(
    events_by_series: dict[str, list[dict]],
    move_series: pd.Series | None,
    tday_arr: np.ndarray | None = None,
) -> list[dict]:
    """Detect P4 confluence tags across all series.

    long_end_turn: >=2 of {DGS10, DGS20, DGS30} fire a same-direction cross
                   within 5 trading days (any of the 4 event types).
    curve_turn: T10Y2Y cross.
    real_turn: DFII10 cross.
    broad_rates_turn: long_end_turn + MOVE regime agreement
                      (MOVE above its trailing 252-trading-day median = high vol regime;
                      broad_rates_turn = long_end_turn fires in HIGH MOVE regime,
                      operationalized as MOVE > trailing 252d median, computed causally).

    FIX 3 (confluence window): gap measured in TRADING DAYS (positions on tday_arr),
    capped at <= 5, matching the frozen spec "within 5 sessions". The previous
    implementation used 10 calendar-day window (~2x the spec).
    """
    confluence_events = []

    # Collect all long-end events
    long_end_events = []
    for sid in LONG_END:
        for ev in events_by_series.get(sid, []):
            long_end_events.append(ev)

    # Sort by date
    long_end_events_sorted = sorted(long_end_events, key=lambda x: x["daily_date"])

    # MOVE regime: above/below trailing 252-day median (causal)
    move_regime = None
    if move_series is not None:
        roll_med = move_series.rolling(252, min_periods=126).median()
        move_regime = (move_series > roll_med)

    # FIX 3 (confluence window): measure gap in TRADING DAYS using tday_arr positions.
    # Require <= 5 trading-day gap between anchor and any co-firing event.
    # Fallback to <=7 calendar days if tday_arr not provided (should not occur in practice).
    TDAY_WINDOW = 5  # frozen spec: "within 5 sessions"

    def _tday_gap(dt1: pd.Timestamp, dt2: pd.Timestamp) -> int:
        """Number of trading-day positions between dt1 and dt2 (both inclusive)."""
        if tday_arr is None:
            # Fallback: approximate with calendar days (original behaviour)
            return int((dt2 - dt1).days)
        pos1 = int(np.searchsorted(tday_arr, dt1, side="right")) - 1
        pos2 = int(np.searchsorted(tday_arr, dt2, side="right")) - 1
        return pos2 - pos1

    # Build per-date set of which series fired (any direction)
    # Use a sliding window approach
    all_long_end_dates = [ev["daily_date"] for ev in long_end_events_sorted]
    if not all_long_end_dates:
        return []

    seen_confluence = set()  # avoid duplicate anchoring on same day
    for i, anchor_ev in enumerate(long_end_events_sorted):
        anchor_dt = anchor_ev["daily_date"]
        anchor_dir = anchor_ev["direction"]
        anchor_key = (anchor_dt, anchor_dir)

        if anchor_key in seen_confluence:
            continue

        # Collect all long-end events within window, same direction
        # FIX 3: gap measured in trading days, not calendar days
        window_evs = [
            ev for ev in long_end_events_sorted
            if ev["direction"] == anchor_dir
            and anchor_dt <= ev["daily_date"]
            and _tday_gap(anchor_dt, ev["daily_date"]) <= TDAY_WINDOW
        ]

        # Distinct series that fired
        series_fired = set(ev["series"] for ev in window_evs)

        if len(series_fired) >= 2:
            # long_end_turn detected
            # Representative date = earliest in window
            rep_dt = min(ev["daily_date"] for ev in window_evs)

            # MOVE regime at anchor date
            move_high_vol = None
            if move_regime is not None:
                mr_idx = move_regime.index.searchsorted(anchor_dt, side="right") - 1
                if mr_idx >= 0:
                    move_high_vol = bool(move_regime.iloc[mr_idx])

            c_ev = {
                "series": "CONFLUENCE",
                "event_class": "long_end_turn",
                "direction": anchor_dir,
                "daily_date": rep_dt,
                "series_fired": sorted(series_fired),
                "n_series": len(series_fired),
                "move_high_vol": move_high_vol,
                "broad_rates_turn": bool(len(series_fired) >= 2 and move_high_vol is True),
                "quality_tag": "long_end_turn",
                "srsi_depth": None,
                "above_200dma": None,
            }
            confluence_events.append(c_ev)

            # Mark all dates in window as seen
            for ev in window_evs:
                seen_confluence.add((ev["daily_date"], anchor_dir))

    # curve_turn: T10Y2Y cross events
    for ev in events_by_series.get("T10Y2Y", []):
        c_ev = {**ev, "event_class": "curve_turn", "quality_tag": "curve_turn"}
        confluence_events.append(c_ev)

    # real_turn: DFII10 cross events
    for ev in events_by_series.get("DFII10", []):
        c_ev = {**ev, "event_class": "real_turn", "quality_tag": "real_turn"}
        confluence_events.append(c_ev)

    return confluence_events


# ---------------------------------------------------------------------------
# Summary statistics builder
# ---------------------------------------------------------------------------

def _summarize_events(
    events: list[dict],
    daily_series_map: dict[str, pd.Series],
) -> list[dict]:
    """Build summary rows per (series, event_class, direction, era, above_200dma)."""
    if not events:
        return []

    df = pd.DataFrame(events)
    df["daily_date"] = pd.to_datetime(df["daily_date"])
    df["era"] = df["daily_date"].apply(_era_of)
    df["oos"] = df["daily_date"] >= pd.Timestamp(OOS_START)

    rows = []
    for series_id in df["series"].unique():
        daily_s = daily_series_map.get(series_id)

        for ec in df["event_class"].unique():
            sub_ec = df[(df["series"] == series_id) & (df["event_class"] == ec)]
            if sub_ec.empty:
                continue

            direction = sub_ec["direction"].iloc[0]

            # Full window stats
            for era_label, (era_s, era_e) in {**ERA_SPLITS, "full": (ESTIMATION_START, ESTIMATION_END)}.items():
                for above_200 in [True, False, None]:
                    sub = sub_ec[
                        (sub_ec["daily_date"] >= era_s) & (sub_ec["daily_date"] <= era_e)
                    ]
                    if above_200 is not None:
                        sub = sub[sub["above_200dma"] == above_200]

                    sub_res = sub[sub["h21_resolved"] == True]  # noqa: E712
                    n = len(sub)
                    n_res = len(sub_res)
                    if n_res == 0:
                        continue

                    h21_hit = sub_res["h21_hit"].mean() if "h21_hit" in sub_res else None
                    h63_hit = sub_res["h63_hit"].mean() if "h63_hit" in sub_res else None

                    # Base rate
                    base = {}
                    if daily_s is not None:
                        base = _compute_base_rates(
                            daily_s, era_s, era_e, above_200
                        )

                    h21_base = base.get("h21_base")
                    h63_base = base.get("h63_base")

                    row = {
                        "series":         series_id,
                        "event_class":    ec,
                        "direction":      direction,
                        "era":            era_label,
                        "above_200dma":   above_200,
                        "n":              n,
                        "n_resolved_h21": n_res,
                        "h21_hit":        round(float(h21_hit), 4) if h21_hit is not None else None,
                        "h21_base":       h21_base,
                        "h21_excess":     round(float(h21_hit) - float(h21_base), 4)
                                          if (h21_hit is not None and h21_base is not None) else None,
                        "h63_hit":        round(float(h63_hit), 4) if h63_hit is not None else None,
                        "h63_base":       h63_base,
                        "h63_excess":     round(float(h63_hit) - float(h63_base), 4)
                                          if (h63_hit is not None and h63_base is not None) else None,
                        "med_move_bp_h21": round(float(sub_res["h21_move_bp"].median()), 2)
                                           if "h21_move_bp" in sub_res and sub_res["h21_move_bp"].notna().any() else None,
                        "mfe_bp_med":     round(float(sub_res["h21_mfe_bp"].median()), 2)
                                           if "h21_mfe_bp" in sub_res and sub_res["h21_mfe_bp"].notna().any() else None,
                        "mae_bp_med":     round(float(sub_res["h21_mae_bp"].median()), 2)
                                           if "h21_mae_bp" in sub_res and sub_res["h21_mae_bp"].notna().any() else None,
                        "perm_p_h21": None,  # filled later for n>=8 full-window rows only
                    }
                    rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# OOS slice stats
# ---------------------------------------------------------------------------

def _oos_summary(events: list[dict]) -> dict:
    """Count events in OOS slice (2024-01-01+) per series/class/direction."""
    result: dict[str, Any] = {}
    for ev in events:
        dt = ev["daily_date"]
        if dt >= pd.Timestamp(OOS_START):
            key = f"{ev['series']}|{ev['event_class']}|{ev['direction']}"
            result[key] = result.get(key, 0) + 1
    return result


# ---------------------------------------------------------------------------
# Case study: locate ~2026-06-30 DGS10 events
# ---------------------------------------------------------------------------

def _find_case_study_events(events: list[dict]) -> list[dict]:
    """Find events near 2026-06-30 for DGS10, DGS20, DGS30 (§5.4 archetype window).

    Extended to DATA_END to capture the Jul-2026 stoch_cross_up which is the
    actual §5.4 archetype event (DGS10 StochRSI bottomed ~6 on 2026-06-24,
    bullish cross fires at 2026-07-02 3B bar).
    """
    cs_events = []
    window_start = pd.Timestamp("2026-06-01")
    window_end = pd.Timestamp(DATA_END)

    for ev in events:
        if ev["series"] not in ("DGS10", "DGS20", "DGS30"):
            continue
        dt = ev["daily_date"]
        if window_start <= dt <= window_end:
            cs_events.append(ev)

    return cs_events


# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------

def _self_check_event_sanity(events_by_series: dict[str, list[dict]]) -> list[str]:
    """Self-check 1: event count sanity per series/decade."""
    lines = ["### Self-check 1: event counts per series/decade"]
    for sid, evs in sorted(events_by_series.items()):
        df = pd.DataFrame(evs)
        if df.empty:
            lines.append(f"  {sid}: 0 events")
            continue
        df["year"] = pd.to_datetime(df["daily_date"]).dt.year
        df["decade"] = (df["year"] // 10 * 10).astype(str)
        for ec in df["event_class"].unique():
            counts = df[df["event_class"] == ec].groupby("decade").size()
            lines.append(f"  {sid} {ec}: " + ", ".join(f"{d}s={c}" for d, c in counts.items()))
    return lines


def _self_check_random_cross(events_by_series: dict[str, list[dict]],
                              grid_map: dict[str, pd.DataFrame]) -> list[str]:
    """Self-check 2: print srsi values around a random event."""
    lines = ["### Self-check 2: srsi values around a random stoch_cross_up event"]
    rng = np.random.default_rng(99)
    for sid in ["DGS10", "DGS2"]:
        evs = [e for e in events_by_series.get(sid, [])
               if e["event_class"] == "stoch_cross_up"]
        if not evs:
            continue
        choice_idx = int(rng.integers(0, len(evs)))
        ev = evs[choice_idx]
        dt = ev["daily_date"]
        grid = grid_map.get(sid)
        if grid is None or grid.empty:
            continue
        gidx = grid.index.searchsorted(dt, side="right") - 1
        lo = max(0, gidx - 4)
        hi = min(len(grid), gidx + 2)
        snippet = grid["srsi"].iloc[lo:hi]
        lines.append(f"  {sid} event date={dt.date()}")
        lines.append(f"  srsi[-4:+1] = {[round(float(x), 1) for x in snippet.values]}")
        lines.append(f"  cross_up_srsi at event = {bool(grid['cross_up_srsi'].iloc[gidx])}")
        lines.append(f"  quality_tag = {ev['quality_tag']}, srsi_depth = {ev['srsi_depth']}")
        break
    return lines


def _self_check_2022_hike(events_by_series: dict[str, list[dict]]) -> list[str]:
    """Self-check 3: 2022 hiking year - bullish crosses should show positive median bp move."""
    lines = ["### Self-check 3: 2022 hiking-year bullish crosses median move_bp"]
    for sid in ["DGS10", "DGS2"]:
        evs = [e for e in events_by_series.get(sid, [])
               if e["direction"] == "bull"
               and e["daily_date"].year == 2022
               and e.get("h21_move_bp") is not None]
        if not evs:
            lines.append(f"  {sid} 2022: no resolved bullish events")
            continue
        moves = [e["h21_move_bp"] for e in evs if e["h21_move_bp"] is not None]
        med = float(np.median(moves)) if moves else None
        lines.append(f"  {sid} 2022 bullish crosses n={len(evs)}, "
                     f"median h21 move_bp={round(med, 1) if med is not None else 'N/A'}")
        lines.append(f"  (Expected: positive in a hiking year — higher yields follow upward crosses)")
    return lines


def _self_check_dgs20_gap(events_by_series: dict[str, list[dict]]) -> list[str]:
    """Self-check 4: no events before DGS20_START."""
    lines = ["### Self-check 4: DGS20 gap handling — no events before 1993-10-01"]
    evs_20 = events_by_series.get("DGS20", [])
    early = [e for e in evs_20 if e["daily_date"] < pd.Timestamp(DGS20_START)]
    if early:
        lines.append(f"  ERROR: {len(early)} DGS20 events before {DGS20_START}:")
        for e in early[:3]:
            lines.append(f"    {e['daily_date'].date()}")
    else:
        lines.append(f"  PASS: 0 DGS20 events before {DGS20_START}")
    return lines


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report(
    events: list[dict],
    events_by_series: dict[str, list[dict]],
    summary_rows: list[dict],
    grid_map: dict[str, pd.DataFrame],
    confluence_events: list[dict],
    oos_counts: dict,
    daily_series_map: dict[str, pd.Series],
    case_study_events: list[dict],
) -> str:
    lines = []
    lines.append("# HS-1 Yield-Turn Event Catalog")
    lines.append("")
    lines.append("**Spec ref:** RIC masterplan §5.3 HS-1 / §3 P4")
    lines.append(f"**Estimation window:** {ESTIMATION_START} to {ESTIMATION_END}")
    lines.append(f"**OOS slice (descriptive only):** {OOS_START} to {DATA_END}")
    lines.append(f"**Generated:** {date.today().isoformat()}")
    lines.append("")
    lines.append(
        "**Sign discipline note:** A bullish oscillator cross on a YIELD series means "
        "yield-momentum UP (oscillator rising out of oversold). TLT (bond price) "
        "moves INVERSELY: bullish yield cross = bearish for TLT price. "
        "For DGS2/DGS5/DGS10/DGS20/DGS30: every h21/h63 direction-hit column = "
        "'yield higher at t+h' for bullish events. "
        "**Exception — T10Y2Y:** the graded series is the 2s10s SPREAD; a bullish "
        "T10Y2Y cross grades as SPREAD HIGHER (curve steepening), not 'yield higher'. "
        "**Exception — DFII10:** the graded series is the 10Y REAL yield; a bullish "
        "DFII10 cross grades as REAL YIELD HIGHER, which may diverge from nominal "
        "yield direction. Event grading and base rates for these two series both use "
        "the same spread/real column, so internal excess figures are coherent — only "
        "the 'yield higher' label does not apply to T10Y2Y and DFII10 rows."
    )
    lines.append("")
    lines.append(
        "**MOVE regime operationalization:** 'broad_rates_turn' = long_end_turn fires "
        "with MOVE above its trailing 252-trading-day median (causal). This is the "
        "study's operationalization, pending W5 organ freeze where the MOVE regime "
        "definition will be formally ratified."
    )
    lines.append("")

    # --------------- Coverage table ---------------
    lines.append("## Series availability and event counts")
    lines.append("")
    lines.append(f"n = total events in estimation window ({ESTIMATION_START} to {ESTIMATION_END})")
    lines.append("")
    lines.append("| Series | Data start | Data end | n_bars_3B | stoch_up | stoch_dn | macd_up | macd_dn |")
    lines.append("|--------|-----------|---------|-----------|---------|---------|--------|--------|")

    for sid, evs in sorted(events_by_series.items()):
        grid = grid_map.get(sid, pd.DataFrame())
        n_3b = len(grid)
        df_ev = pd.DataFrame(evs)
        su = len(df_ev[df_ev["event_class"] == "stoch_cross_up"]) if not df_ev.empty else 0
        sd = len(df_ev[df_ev["event_class"] == "stoch_cross_dn"]) if not df_ev.empty else 0
        mu = len(df_ev[df_ev["event_class"] == "macd_cross_up"]) if not df_ev.empty else 0
        md = len(df_ev[df_ev["event_class"] == "macd_cross_dn"]) if not df_ev.empty else 0
        ds = daily_series_map.get(sid)
        d_start = ds.index[0].date() if ds is not None and len(ds) else "N/A"
        d_end = ds.index[-1].date() if ds is not None and len(ds) else "N/A"
        lines.append(f"| {sid} | {d_start} | {d_end} | {n_3b} | {su} | {sd} | {mu} | {md} |")

    lines.append("")
    lines.append("**Coverage limitations:**")
    lines.append(f"- DGS20: truncated to {DGS20_START} due to a confirmed 2466-day gap (1987-01-01 to 1993-09-30) in the FRED parquet.")
    lines.append("- DGS30: The FRED parquet for DGS30 shows no NaN gap in the 2002-2006 period (data is present with no null rows, realistically varying values, consistent daily-diff std ~0.048). However, the US Treasury officially discontinued the 30Y constant-maturity yield from 2002-02-19 to 2006-02-09; the FRED values in that window are Treasury's extrapolated long-term-composite 30Y estimate, not a live auctioned 30Y CMT. No gap truncation is applied (no phantom flat-fill events detected, max 16bp jump at the 2006-02-09 reintroduction seam), but crosses in the 2002-02-19 to 2006-02-09 window rest on the extrapolated composite series rather than a live 30Y auction yield.")
    lines.append("- DFII10: available from 2003-01-02 only; pre-2003 events = 0 by construction.")
    lines.append("- T10Y2Y: available from 1976-06-01; estimation window effective from 1990-01-01.")
    lines.append("- Events marked 'unresolved': event date + horizon extends past data end (2026-07-10).")
    lines.append(
        "- **Detection warmup (FIX 2):** The 3B detection loop requires positional index "
        "i >= 39, matching engine/_tf_state which returns {} when len(close) < 40. "
        "This eliminates ~11 phantom grid-start events (DGS20: 3 at 1993-10 restart; "
        "DFII10: 5 at 2003 start; T10Y2Y: 3 at 1990 start) that fired at i=3..38 in "
        "the oscillator warmup zone before indicators are reliable."
    )
    lines.append("")

    # --------------- Era-split hit rate tables ---------------
    lines.append("## Event class base rates and h21/h63 hit rates (era split)")
    lines.append("")
    lines.append(
        "Table shows: h21/h63 direction hit rate (% of resolved events where yield moved "
        "in event direction), base rate (unconditional P(yield higher at t+h) on same side "
        "of 200dma in that era), excess = hit - base. Median bp move at h21. "
        "MFE/MAE = median favorable excursion / median adverse excursion in bp. "
        "n = total events in window; n_res = events with resolved h21 horizon."
    )
    lines.append("")
    lines.append(
        "**200dma base-rate method:** The 200dma is computed on the FULL daily series "
        "(same lookback as event annotation), then restricted to the era window. "
        "Warmup days where the 200dma is NaN are excluded from the denominator — "
        "NOT filled to below-200dma. This prevents the ~6-14 ppt base-rate error "
        "that occurs in short eras (especially 2021_plus, where ~14% of days fall "
        "in the 200dma warmup period) if the 200dma were recomputed on the era-sliced "
        "series with fillna(False)."
    )
    lines.append("")
    lines.append(
        "**perm_p_h21 method note:** The 'perm_p' column IS the house-law DT-R14 "
        "within-month episode-label permutation with episode-first-month blocking "
        "(two-sided). Inferential unit = the episode; each episode contributes the "
        "h21 direction-hit of its FIRST event day. Null draw: for each calendar month "
        "hosting k episodes, draw k random trading days WITHOUT replacement from that "
        "month's eligible trading days of the same daily yield series (era-unrestricted; "
        "only days where h21 is computable), scoring each day's h21 direction-hit in "
        "the event-class direction. The null recomputes the episode hit rate over all "
        "drawn pseudo-episodes, preserving calendar composition (per-month episode "
        "counts). Two-sided p = min(1, 2 * min(P(perm >= obs), P(perm <= obs))), "
        "ties included. n_perm=2000, seed=42. "
        "The column is displayed ONLY for the full-window, all-sides row (era=full, "
        "above_200dma=all); all era- and stratum-specific sub-rows show None because "
        "only the pooled full-window construction is tested. "
        "The p value is descriptive context only — do not declare significance."
    )
    lines.append("")

    # Group by series
    sdf = pd.DataFrame(summary_rows)
    if sdf.empty:
        lines.append("No summary rows computed.")
    else:
        for sid in sorted(sdf["series"].unique()):
            lines.append(f"### {sid}")
            lines.append("")
            sub = sdf[sdf["series"] == sid]

            # Per-series sign semantics note
            if sid == "T10Y2Y":
                lines.append(
                    "_Note: for T10Y2Y, direction-hit = SPREAD HIGHER (2s10s curve steepening), "
                    "not 'yield higher'. The base rate likewise measures P(spread higher at t+h)._"
                )
                lines.append("")
            elif sid == "DFII10":
                lines.append(
                    "_Note: for DFII10, direction-hit = REAL YIELD HIGHER at t+h. "
                    "This may diverge from nominal yield direction._"
                )
                lines.append("")

            for ec in sorted(sub["event_class"].unique()):
                sub_ec = sub[sub["event_class"] == ec]
                direction = sub_ec["direction"].iloc[0]
                lines.append(f"**{ec}** (direction: {direction})")
                lines.append("")
                lines.append("| era | above_200dma | n | n_res | h21_hit | h21_base | h21_excess | h63_hit | h63_base | h63_excess | med_bp_h21 | mfe_med | mae_med | perm_p |")
                lines.append("|-----|-------------|---|-------|---------|---------|-----------|---------|---------|-----------|-----------|--------|--------|--------|")

                for _, row in sub_ec.iterrows():
                    era = row["era"]
                    above = str(row["above_200dma"]) if row["above_200dma"] is not None else "all"
                    n = row["n"]
                    n_res = row["n_resolved_h21"]
                    h21 = f"{row['h21_hit']:.1%}" if row["h21_hit"] is not None else "N/A"
                    h21b = f"{row['h21_base']:.1%}" if row["h21_base"] is not None else "N/A"
                    h21e = f"{row['h21_excess']:+.1%}" if row["h21_excess"] is not None else "N/A"
                    h63 = f"{row['h63_hit']:.1%}" if row["h63_hit"] is not None else "N/A"
                    h63b = f"{row['h63_base']:.1%}" if row["h63_base"] is not None else "N/A"
                    h63e = f"{row['h63_excess']:+.1%}" if row["h63_excess"] is not None else "N/A"
                    med = f"{row['med_move_bp_h21']:.1f}" if row["med_move_bp_h21"] is not None else "N/A"
                    mfe = f"{row['mfe_bp_med']:.1f}" if row["mfe_bp_med"] is not None else "N/A"
                    mae = f"{row['mae_bp_med']:.1f}" if row["mae_bp_med"] is not None else "N/A"
                    # Perm p: only show for full-era, all-sides rows
                    rp_raw = row.get("perm_p_h21")
                    # pd.isna covers both None and np.nan
                    rp_valid = rp_raw is not None and not (isinstance(rp_raw, float) and pd.isna(rp_raw))
                    if rp_valid:
                        pp = f"{rp_raw:.3f}"
                    elif era == "full" and above == "all":
                        pp = "None (n<8)"
                    else:
                        pp = "None (sub-row)"
                    lines.append(
                        f"| {era} | {above} | {n} | {n_res} | {h21} | {h21b} | {h21e} | {h63} | {h63b} | {h63e} | {med} | {mfe} | {mae} | {pp} |"
                    )
                lines.append("")

    # --------------- OOS slice ---------------
    lines.append("## OOS slice (2024-01-01 to data end, descriptive only)")
    lines.append("")
    lines.append("Embargo per RIC-R11: no threshold fitting on this window. Descriptive counts only.")
    lines.append(
        "**Overlap disclosure (FIX 5):** Events in the 2024-01-01 to 2026-06-30 slice are "
        "ALSO included in the full-window and 2021_plus estimation tables above. "
        "This slice is a descriptive print only; it is NOT a statistical holdout. "
        "No threshold was fitted on any sub-window (per RIC-R11), so the overlap "
        "does not constitute data leakage for the base-rate estimates reported here."
    )
    lines.append("")
    lines.append("| series|event_class|direction | n_oos |")
    lines.append("|-------|-----------|---------|-------|")
    for key, cnt in sorted(oos_counts.items()):
        s, ec, d = key.split("|")
        lines.append(f"| {s} | {ec} | {d} | {cnt} |")
    lines.append("")

    # --------------- Confluence events ---------------
    lines.append("## Confluence tag summary")
    lines.append("")
    lines.append(
        "long_end_turn: >=2 of {DGS10, DGS20, DGS30} fire same-direction cross within 5 sessions. "
        "curve_turn: T10Y2Y cross. real_turn: DFII10 cross. "
        "broad_rates_turn: long_end_turn + MOVE above 252d trailing median."
    )
    lines.append("")
    if confluence_events:
        c_df = pd.DataFrame(confluence_events)
        c_df["daily_date"] = pd.to_datetime(c_df["daily_date"])
        lines.append(f"Total long_end_turn events: {len(c_df[c_df['event_class'] == 'long_end_turn'])}")
        lines.append(f"  Bull long_end_turn: {len(c_df[(c_df['event_class']=='long_end_turn') & (c_df['direction']=='bull')])}")
        lines.append(f"  Bear long_end_turn: {len(c_df[(c_df['event_class']=='long_end_turn') & (c_df['direction']=='bear')])}")
        broad = c_df[c_df.get("broad_rates_turn", pd.Series(dtype=bool)) == True] if "broad_rates_turn" in c_df.columns else pd.DataFrame()
        lines.append(f"  broad_rates_turn (long_end_turn + high MOVE regime): {len(broad)}")
        lines.append("")
    else:
        lines.append("No confluence events detected.")
        lines.append("")

    # --------------- Case study ---------------
    lines.append("## Case study: ~2026-06-30 DGS10/DGS20 events (§5.4 archetype)")
    lines.append("")
    lines.append(
        "**Archetype context (§5.4):** DGS10 3B StochRSI bottomed at 6.0 on 2026-06-24, "
        "with yields at the 4.36% low. The bullish stoch_cross_up fired on the 2026-07-02 "
        "3B bar (StochRSI = 20.24, crossing up from sub-20 zone). This event is post-estimation-"
        "window (estimation ends 2026-06-30) so it is presented descriptively as the §5.4 "
        "archetype — not graded into the estimation statistics. DGS20 MACD/RSI confirmed "
        "bearish (downward yield momentum) events in early June as yields fell from overbought; "
        "the long-end turn reversal (bullish yield cross) appears in early July."
    )
    lines.append("")
    if case_study_events:
        lines.append(
            "Events detected in 2026-06-01 to 2026-07-10 window for long-end series "
            "(estimation window ends 2026-06-30; post-estimation events marked as such):"
        )
        lines.append("")
        lines.append("| series | event_class | direction | date | in_estimation | quality_tag | srsi_depth | y0 | h21_hit | h21_move_bp | resolved |")
        lines.append("|--------|------------|---------|------|--------------|------------|-----------|-----|---------|------------|---------|")
        for ev in sorted(case_study_events, key=lambda x: x["daily_date"]):
            y0 = f"{ev.get('y0', 'N/A'):.4f}" if ev.get("y0") is not None else "N/A"
            h21_hit = str(ev.get("h21_hit", "N/A"))
            h21_bp = f"{ev.get('h21_move_bp', 'N/A'):.2f}" if ev.get("h21_move_bp") is not None else "N/A"
            resolved = str(ev.get("h21_resolved", False))
            in_est = str(ev.get("in_estimation_window", True))
            lines.append(
                f"| {ev['series']} | {ev['event_class']} | {ev['direction']} | "
                f"{ev['daily_date'].date()} | {in_est} | {ev.get('quality_tag','N/A')} | "
                f"{ev.get('srsi_depth','N/A')} | {y0} | {h21_hit} | {h21_bp} | {resolved} |"
            )
        lines.append("")
        lines.append(
            "**Historical base-rate context for DGS10 stoch_cross_up (full estimation window, "
            "below 200dma stratum — the typical stratum for a washout bottom turn):**"
        )
        sdf = pd.DataFrame(summary_rows)
        if not sdf.empty:
            dgs10_row = sdf[
                (sdf["series"] == "DGS10")
                & (sdf["event_class"] == "stoch_cross_up")
                & (sdf["era"] == "full")
                & (sdf["above_200dma"] == False)  # noqa: E712
            ]
            if not dgs10_row.empty:
                r = dgs10_row.iloc[0]
                lines.append(
                    f"  n={r['n']}, h21_hit={r['h21_hit']:.1%}, h21_base={r['h21_base']:.1%}, "
                    f"h21_excess={r['h21_excess']:+.1%}, med_bp_h21={r['med_move_bp_h21']:.1f}bp"
                )
            # Also all-sides
            dgs10_all = sdf[
                (sdf["series"] == "DGS10")
                & (sdf["event_class"] == "stoch_cross_up")
                & (sdf["era"] == "full")
                & (sdf["above_200dma"].isna())
            ]
            if not dgs10_all.empty:
                r2 = dgs10_all.iloc[0]
                lines.append(
                    f"  (all 200dma sides combined) n={r2['n']}, h21_hit={r2['h21_hit']:.1%}, "
                    f"h21_base={r2['h21_base']:.1%}, h21_excess={r2['h21_excess']:+.1%}, "
                    f"med_bp_h21={r2['med_move_bp_h21']:.1f}bp"
                )
    else:
        lines.append("No events detected near 2026-06-30 for DGS10/DGS20/DGS30.")
    lines.append("")
    lines.append(
        '**Operator caveat (verbatim):** "we cannot say yields will move higher from every '
        'such bottom — we say the base rate and the cohort map, and we watch."'
    )
    lines.append("")

    # --------------- Self-checks ---------------
    lines.append("## Self-checks")
    lines.append("")
    for check_fn in [
        lambda: _self_check_event_sanity(events_by_series),
        lambda: _self_check_random_cross(events_by_series, grid_map),
        lambda: _self_check_2022_hike(events_by_series),
        lambda: _self_check_dgs20_gap(events_by_series),
    ]:
        for l in check_fn():
            lines.append(l)
        lines.append("")

    lines.append("---")
    lines.append(
        "_This is a display-tier research artifact. All statistics are descriptive base rates, "
        "not claims of predictive validity. Nulls printed, not hidden. No promotion or kill "
        "language. Do not use the word 'validated' in any consumer display._"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON seed builder
# ---------------------------------------------------------------------------

def _build_json(
    summary_rows: list[dict],
    case_study_events: list[dict],
) -> dict:
    provenance = {
        "script": "scripts/research/hs1_yield_turn_catalog.py",
        "spec_ref": "RIC masterplan §5.3 HS-1",
        "estimation_window": f"{ESTIMATION_START} to {ESTIMATION_END}",
        "oos_slice": f"{OOS_START} to {DATA_END}",
        "generated_by": "claude-sonnet-4-6 / HS-1 build agent",
        "generated_date": date.today().isoformat(),
        "note": (
            "Display-tier descriptive base rates. Not gauntleted. "
            "Nulls printed, not hidden. No promotion language."
        ),
    }

    # Filter to useful rows: full era, above_200dma=None (all sides combined)
    def _clean(v: Any) -> Any:
        if isinstance(v, float) and np.isnan(v):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
        return v

    def _row_to_json(row: dict) -> dict:
        return {k: _clean(v) for k, v in row.items()}

    def _row_to_seed(row: dict) -> dict:
        r = _row_to_json(row)
        # Add required spec fields
        r["archetype"] = f"{r['series']}_{r['event_class']}_{r['direction']}"
        # perm_p_h21 is already the correct field name in summary_rows
        r["notes"] = (
            "Display-tier base rate. Not gauntleted. Null = lack of standalone signal, "
            "retained as confluence input per house epistemics. "
            "perm_p_h21 is the house-law DT-R14 within-month episode-label permutation "
            "(two-sided), episode unit = first event day, episode-first-month blocking. "
            "Only populated for full-era, all-sides rows. Descriptive context only — "
            "do not declare significance."
        )
        return r

    seed_rows = [_row_to_seed(r) for r in summary_rows
                 if r["era"] in ("full", "pre_2010", "2010_2020", "2021_plus")]

    # Case study worked example
    cs_json = []
    for ev in case_study_events:
        cs_json.append({
            "archetype": "long_end_turn_june2026",
            "series": ev["series"],
            "event_class": ev["event_class"],
            "direction": ev["direction"],
            "date": str(ev["daily_date"].date()),
            "quality_tag": ev.get("quality_tag"),
            "srsi_depth": ev.get("srsi_depth"),
            "y0": ev.get("y0"),
            "h21_hit": _clean(ev.get("h21_hit")),
            "h21_move_bp": ev.get("h21_move_bp"),
            "h21_resolved": ev.get("h21_resolved", False),
            "operator_caveat": (
                "we cannot say yields will move higher from every such bottom "
                "— we say the base rate and the cohort map, and we watch."
            ),
        })

    return {
        "provenance": provenance,
        "pattern_library": seed_rows,
        "case_study_june2026": cs_json,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(run_perm: bool = True) -> None:
    log.info("HS-1 Yield-turn event catalog — starting")

    # 1. Load daily series
    log.info("Loading yield series...")
    daily_series_map: dict[str, pd.Series] = {}
    for sid in SERIES_MAP:
        try:
            s = _load_series(sid)
            daily_series_map[sid] = s
            log.info("  %s: %d bars (%s to %s)",
                     sid, len(s), s.index[0].date(), s.index[-1].date())
        except Exception as e:
            log.warning("  %s: load failed: %s", sid, e)

    # Load MOVE
    try:
        move_series = _load_move()
        log.info("  MOVE: %d bars", len(move_series))
    except Exception as e:
        log.warning("  MOVE: load failed: %s", e)
        move_series = None

    # 2. Build 3B grids and extract events
    log.info("Building 3B grids and extracting events...")
    events_by_series: dict[str, list[dict]] = {}
    grid_map: dict[str, pd.DataFrame] = {}

    for sid, daily_s in daily_series_map.items():
        log.info("  Processing %s...", sid)
        grid = _make_3b_grid(daily_s, sid)
        grid_map[sid] = grid
        if grid.empty:
            events_by_series[sid] = []
            continue

        # Extract with post-estimation extension for case study (§5.4 archetype Jul-2026 events)
        evs = _extract_events_from_grid(sid, grid, include_post_estimation=True)
        evs = _add_200dma_side(evs, daily_s, sid)
        # Convert date to Timestamp
        for ev in evs:
            ev["daily_date"] = pd.Timestamp(ev["daily_date"])
        # Separate estimation vs post-estimation events
        events_by_series[sid] = [e for e in evs if e.get("in_estimation_window", True)]
        log.info("    %s: %d estimation events extracted (%d total incl. post-estimation)",
                 sid, len(events_by_series[sid]), len(evs))

    # Keep full event list including post-estimation for case study
    all_events_extended: list[dict] = []
    for sid, daily_s in daily_series_map.items():
        grid = grid_map.get(sid, pd.DataFrame())
        if grid.empty:
            continue
        evs = _extract_events_from_grid(sid, grid, include_post_estimation=True)
        evs = _add_200dma_side(evs, daily_s, sid)
        for ev in evs:
            ev["daily_date"] = pd.Timestamp(ev["daily_date"])
        all_events_extended.extend(evs)

    # 3. Grade all events (estimation window only for stats)
    log.info("Grading events (h21/h63)...")
    all_events: list[dict] = []
    for sid, evs in events_by_series.items():
        daily_s = daily_series_map.get(sid)
        if daily_s is None or not evs:
            all_events.extend(evs)
            continue
        graded = _grade_events(evs, daily_s)
        events_by_series[sid] = graded
        all_events.extend(graded)
    log.info("  Total events graded: %d", len(all_events))

    # Grade the extended events list (for case study display)
    log.info("Grading extended events (incl. post-estimation for case study)...")
    graded_extended: list[dict] = []
    extended_by_sid: dict[str, list[dict]] = {}
    for ev in all_events_extended:
        sid = ev["series"]
        if sid not in extended_by_sid:
            extended_by_sid[sid] = []
        extended_by_sid[sid].append(ev)
    for sid, evs in extended_by_sid.items():
        daily_s = daily_series_map.get(sid)
        if daily_s is None or not evs:
            graded_extended.extend(evs)
            continue
        graded_ext = _grade_events(evs, daily_s)
        graded_extended.extend(graded_ext)
    log.info("  Total extended events (incl. post-estimation): %d", len(graded_extended))

    # 4. Confluence tags (estimation window events only)
    log.info("Detecting confluence events...")
    # Use only estimation-window events for confluence
    estimation_events_by_series = {
        sid: [e for e in evs if e.get("in_estimation_window", True)]
        for sid, evs in events_by_series.items()
    }
    # FIX 3: build a unified trading-day calendar from all loaded daily series
    # to pass to _detect_confluence for trading-day gap measurement.
    all_dates: set = set()
    for ds in daily_series_map.values():
        all_dates.update(ds.dropna().index.tolist())
    tday_arr_conf = np.array(sorted(all_dates))
    confluence_events = _detect_confluence(estimation_events_by_series, move_series,
                                           tday_arr=tday_arr_conf)
    log.info("  Confluence events: %d", len(confluence_events))

    # 5. Summary stats (estimation window events only)
    log.info("Computing summary statistics...")
    # Filter to estimation window only
    estimation_events = [e for e in all_events if e.get("in_estimation_window", True)]
    summary_rows = _summarize_events(estimation_events, daily_series_map)
    log.info("  Summary rows: %d", len(summary_rows))

    # 6. Within-month episode-label permutation p (house-law DT-R14, estimation window,
    # full-era rows only). Computed only at (series, event_class, direction) level for
    # classes with n_episodes >= 8. NOT stamped onto era/stratum sub-rows — those display
    # None so the pooled full-window statistic is never displayed against small-n substrata.
    if run_perm:
        log.info("Running within-month episode-label permutation tests (n_perm=%d)...", N_PERM)
        events_df = pd.DataFrame(estimation_events)
        if not events_df.empty:
            computed_perm: dict[tuple, float | None] = {}
            for i, row in enumerate(summary_rows):
                sid = row["series"]
                ec = row["event_class"]
                direction = row["direction"]
                era = row["era"]
                above_200 = row.get("above_200dma")
                # Only compute for full-era, all-sides (above_200dma=None) rows
                if era != "full" or above_200 is not None:
                    continue
                n = row.get("n", 0)
                if n < MIN_N_FOR_PERM:
                    continue
                key = (sid, ec, direction)
                if key not in computed_perm:
                    daily_s = daily_series_map.get(sid)
                    if daily_s is None:
                        computed_perm[key] = None
                        continue
                    p = _perm_p_h21(events_df, sid, ec, direction, daily_s)
                    computed_perm[key] = p
                    log.info("    %s/%s/%s perm_p_h21=%.4f", sid, ec, direction,
                             p if p is not None else float("nan"))

            # Apply p ONLY to the full-era, above_200dma=None rows (where it was computed)
            # Leave all era/stratum sub-rows as None
            for j, r2 in enumerate(summary_rows):
                if r2["era"] == "full" and r2.get("above_200dma") is None:
                    key = (r2["series"], r2["event_class"], r2["direction"])
                    if key in computed_perm:
                        summary_rows[j]["perm_p_h21"] = computed_perm[key]
        log.info("  Episode-label permutation tests done")
    else:
        log.info("  Permutation tests skipped (--no-perm)")

    # 7. OOS counts (from estimation window events only)
    oos_counts = _oos_summary(estimation_events)

    # 8. Case study events (use extended list to capture Jul-2026 stoch_cross_up archetype)
    case_study_events = _find_case_study_events(graded_extended)
    log.info("  Case study events near 2026-06-30 (incl. post-estimation): %d", len(case_study_events))

    # 9. Build and write report
    log.info("Building report...")
    report_text = _build_report(
        all_events, events_by_series, summary_rows, grid_map,
        confluence_events, oos_counts, daily_series_map, case_study_events,
    )
    _REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_OUT.write_text(report_text, encoding="utf-8")
    log.info("Report written: %s", _REPORT_OUT)

    # 10. Build and write JSON
    log.info("Building JSON seed...")
    json_data = _build_json(summary_rows, case_study_events)
    _JSON_OUT.write_text(json.dumps(json_data, indent=2, default=str), encoding="utf-8")
    log.info("JSON written: %s", _JSON_OUT)

    log.info("HS-1 complete.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HS-1 yield-turn event catalog")
    parser.add_argument("--no-perm", action="store_true",
                        help="Skip permutation tests (faster for debugging)")
    args = parser.parse_args()
    main(run_perm=not args.no_perm)
