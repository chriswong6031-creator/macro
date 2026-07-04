"""S7 RS-Repair Phase-0 — per-fire metric computation.

SPEC §5 metrics:
  race stop-out   fill → close −5% before close +5%
  clean15_126     +15% before −5% within 126 td
  clean8_21       +8% before −5% within 21 td
  fwd_ret_20d     day-20 forward return (close[t+21] / fill - 1); None if <20 fwd bars
  mfe_20d         max favorable excursion intraday H/L over close fill, 20d
  mae_20d         max adverse excursion intraday H/L over close fill, 20d
  time_to_fail    bars until stop hit (NaN if no stop-out)
  undercut_60d    fire-date 60d-low broken within 60 td

Fill convention: close at t+1.
Forward windows start AFTER the fill bar (i.e., bar t+2 onward).

Episode clustering: gap > 10 td between consecutive fire dates → new episode.
Episode-block bootstrap: 2,000 draws of episodes with replacement.

TIMING DISCIPLINE: same-bar fill and ffill are the cautionary-tale bugs
in research/bottom_signal_backtest/.  Every fill here uses strict t+1 indexing
on the daily close series.

CONTIGUITY: contiguity_ok() guards against the 2023-02→2025-01 hole in the
massive store and residual per-ticker gaps.  Fires flagged False are excluded
from all strata in analyze.py but kept in the parquet for audit.
"""
from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

STOP_PCT     = -0.05   # -5%
LIFTOFF_PCT  =  0.05   # +5%
CLEAN15_PCT  =  0.15   # +15%
CLEAN8_PCT   =  0.08   # +8%
CLEAN15_BARS = 126
CLEAN8_BARS  =  21
FWD_20       =  20
UNDERCUT_BARS=  60
EPISODE_GAP  =  10     # td gap > this -> new episode


# ──────────────────────────────────────────────────────────────────────────
# Per-fire metrics
# ──────────────────────────────────────────────────────────────────────────

def compute_fire_metrics(
    fire_date: pd.Timestamp,
    daily_close: pd.Series,
    daily_high: pd.Series | None,
    daily_low: pd.Series | None,
    fire_date_low60: float | None = None,
) -> dict:
    """Compute metrics for one fire event.

    fire_date: the fire bar (t).
    daily_close: full close series for the ticker (P1 massive or P2 stocks).
    daily_high / daily_low: intraday series for MFE/MAE; if None, falls back
                             to close-based bounds.
    fire_date_low60: trailing 60d low as-of fire_date (for undercut_60d);
                     if None, computed here.

    Returns a dict with all SPEC §5 metrics.  'maturity_ok' is True if
    enough forward bars exist for the full window (used for coverage reporting).
    """
    out = {
        "fire_date": fire_date,
        "fill_date": None,
        "fill_px": None,
        "race_stop_out": None,
        "race_liftoff": None,
        "race_censored": False,
        "clean15_126": None,
        "clean8_21": None,
        "fwd_ret_20d": None,
        "mfe_20d": None,
        "mae_20d": None,
        "time_to_fail": None,
        "undercut_60d": None,
        "maturity_ok_race": False,
        "maturity_ok_126": False,
        "maturity_ok_21": False,
    }

    # Locate fire bar (t) position in the daily close index
    pos_t = daily_close.index.searchsorted(fire_date, side="left")
    if pos_t >= len(daily_close):
        return out
    # Ensure exact match (or accept if close enough)
    if daily_close.index[pos_t] != fire_date:
        # fire_date not in index; use the most-recent bar before it
        pos_t = daily_close.index.searchsorted(fire_date, side="right") - 1
        if pos_t < 0:
            return out

    # Fill bar: t+1
    fill_pos = pos_t + 1
    if fill_pos >= len(daily_close):
        return out  # no fill bar available

    fill_date = daily_close.index[fill_pos]
    fill_px   = float(daily_close.iloc[fill_pos])
    out["fill_date"] = fill_date
    out["fill_px"]   = fill_px

    if fill_px <= 0 or np.isnan(fill_px):
        return out

    # Forward window starts at t+2 (after fill bar)
    fwd_start = fill_pos + 1

    # Helper: get forward close / high / low arrays
    def _fwd_close(n: int) -> np.ndarray:
        end = min(fwd_start + n, len(daily_close))
        return daily_close.iloc[fwd_start:end].to_numpy(dtype=float)

    def _fwd_high(n: int) -> np.ndarray:
        if daily_high is not None:
            end = min(fwd_start + n, len(daily_high))
            return daily_high.iloc[fwd_start:end].to_numpy(dtype=float)
        return _fwd_close(n)

    def _fwd_low(n: int) -> np.ndarray:
        if daily_low is not None:
            end = min(fwd_start + n, len(daily_low))
            return daily_low.iloc[fwd_start:end].to_numpy(dtype=float)
        return _fwd_close(n)

    # ---- race stop-out (censoring-honest) ----
    # Over up to 131 forward bars:
    #   stop-first  → race_stop_out=1, race_liftoff=0
    #   liftoff-first → race_stop_out=0, race_liftoff=1
    #   unresolved with >=131 bars observed → 0,0 (mature non-stop)
    #   unresolved with <131 bars observed  → both None, race_censored=True
    RACE_MAX = 131
    c_arr = _fwd_close(RACE_MAX)
    bars_observed = len(c_arr)
    if bars_observed >= 1:
        race_stop = None
        race_lift = None
        resolved = False
        for j, c in enumerate(c_arr):
            ret = c / fill_px - 1.0
            if ret <= STOP_PCT:
                race_stop = 1
                race_lift = 0
                resolved = True
                out["time_to_fail"] = j + 1
                break
            if ret >= LIFTOFF_PCT:
                race_stop = 0
                race_lift = 1
                resolved = True
                break
        if resolved:
            out["maturity_ok_race"] = True
            out["race_stop_out"] = race_stop
            out["race_liftoff"] = race_lift
            out["race_censored"] = False
        elif bars_observed >= RACE_MAX:
            # mature non-stop: observed all 131 bars, neither threshold hit
            out["maturity_ok_race"] = True
            out["race_stop_out"] = 0
            out["race_liftoff"] = 0
            out["race_censored"] = False
        else:
            # panel edge: fewer than RACE_MAX bars exist — censored
            out["maturity_ok_race"] = False
            out["race_stop_out"] = None
            out["race_liftoff"] = None
            out["race_censored"] = True

    # ---- clean15_126 ----
    c126 = _fwd_close(CLEAN15_BARS)
    if len(c126) >= CLEAN15_BARS:
        out["maturity_ok_126"] = True
        cl15 = None
        for j, c in enumerate(c126):
            ret = c / fill_px - 1.0
            if ret >= CLEAN15_PCT:
                cl15 = 1
                break
            if ret <= STOP_PCT:
                cl15 = 0
                break
        out["clean15_126"] = cl15  # None = neither threshold hit

    # ---- clean8_21 ----
    c21 = _fwd_close(CLEAN8_BARS)
    if len(c21) >= CLEAN8_BARS:
        out["maturity_ok_21"] = True
        cl8 = None
        for j, c in enumerate(c21):
            ret = c / fill_px - 1.0
            if ret >= CLEAN8_PCT:
                cl8 = 1
                break
            if ret <= STOP_PCT:
                cl8 = 0
                break
        out["clean8_21"] = cl8

    # ---- fwd_ret_20d: day-20 point forward return ----
    # Defined as close[t+21] / fill_px - 1 (the 20th bar after fill).
    # Only set when at least FWD_20 forward bars exist; no truncated fallback.
    c20 = _fwd_close(FWD_20)
    if len(c20) >= FWD_20:
        out["fwd_ret_20d"] = float(c20[FWD_20 - 1] / fill_px - 1.0)

    # ---- MFE / MAE 20d (intraday H/L over close fill) ----
    # Only set when both h20 and l20 have >= FWD_20 bars (no truncated window).
    h20 = _fwd_high(FWD_20)
    l20 = _fwd_low(FWD_20)
    if len(h20) >= FWD_20 and len(l20) >= FWD_20:
        out["mfe_20d"] = float(np.max(h20) / fill_px - 1.0)
        out["mae_20d"] = float(np.min(l20) / fill_px - 1.0)

    # ---- 60d undercut ----
    # Fire-date 60d low broken within 60 td after fill
    if fire_date_low60 is None:
        # Compute from available data
        start60 = max(0, pos_t - 59)
        fire_low60 = float(daily_close.iloc[start60: pos_t + 1].min())
    else:
        fire_low60 = fire_date_low60

    c60_fwd = _fwd_close(UNDERCUT_BARS)
    if len(c60_fwd) >= UNDERCUT_BARS:
        out["undercut_60d"] = int(float(np.min(c60_fwd)) < fire_low60)

    return out


def contiguity_ok(
    index: pd.DatetimeIndex,
    pos_t: int,
    lookback_bars: int = 200,
    fwd_bars: int = 133,
    max_cal_gap_days: int = 21,
) -> bool:
    """Return True iff the price series has no large calendar gaps around pos_t.

    Conditions (all must hold):
      (a) pos_t >= lookback_bars (enough history exists)
      (b) max calendar-day gap between consecutive entries in
          [pos_t - lookback_bars, pos_t] <= max_cal_gap_days
      (c) max calendar-day gap between consecutive entries in
          [pos_t, min(pos_t + fwd_bars, len-1)] <= max_cal_gap_days
          (only over bars that actually exist — shortness is handled by
          maturity flags; this catches within-window gaps)

    Guards against the 2023-02→2025-01 hole in the massive store and
    residual per-ticker gaps.
    """
    n = len(index)
    if pos_t < lookback_bars:
        return False

    # Lookback window
    lb_start = pos_t - lookback_bars
    lb_slice = index[lb_start: pos_t + 1]
    if len(lb_slice) >= 2:
        # unit-safe: index resolution may be ns or us depending on parquet source
        cal_diffs = np.diff(lb_slice.values).astype("timedelta64[s]").astype(np.float64) / 86400.0
        if float(np.max(cal_diffs)) > max_cal_gap_days:
            return False

    # Forward window (only over existing bars)
    fwd_end = min(pos_t + fwd_bars, n - 1)
    fwd_slice = index[pos_t: fwd_end + 1]
    if len(fwd_slice) >= 2:
        cal_diffs = np.diff(fwd_slice.values).astype("timedelta64[s]").astype(np.float64) / 86400.0
        if float(np.max(cal_diffs)) > max_cal_gap_days:
            return False

    return True


def compute_fire_metrics_batch(
    fires: pd.DataFrame,
    ticker_data: dict[str, dict],
) -> pd.DataFrame:
    """Compute metrics for all fires.

    fires: DataFrame with columns ['ticker', 'fire_date', ...].
    ticker_data: {ticker: {'close': pd.Series, 'high': pd.Series|None,
                            'low': pd.Series|None}}.

    Returns fires with metric columns appended.
    """
    rows = []
    for _, row in fires.iterrows():
        ticker = row["ticker"]
        fire_date = pd.Timestamp(row["fire_date"])
        td = ticker_data.get(ticker, {})
        daily_close = td.get("close")
        if daily_close is None or daily_close.empty:
            continue
        daily_high = td.get("high")
        daily_low  = td.get("low")

        metrics = compute_fire_metrics(
            fire_date=fire_date,
            daily_close=daily_close,
            daily_high=daily_high,
            daily_low=daily_low,
        )
        # PATCH 3: compute and attach contiguity_ok (do NOT filter here)
        pos_t = daily_close.index.searchsorted(fire_date, side="left")
        if pos_t < len(daily_close) and daily_close.index[pos_t] != fire_date:
            pos_t = daily_close.index.searchsorted(fire_date, side="right") - 1
        metrics["contiguity_ok"] = contiguity_ok(daily_close.index, pos_t)

        combined = dict(row)
        combined.update(metrics)
        rows.append(combined)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    return result


# ──────────────────────────────────────────────────────────────────────────
# Episode clustering
# ──────────────────────────────────────────────────────────────────────────

def cluster_episodes(fire_dates: Sequence[pd.Timestamp],
                     gap: int = EPISODE_GAP) -> list[int]:
    """Greedy episode clustering.

    Assign each fire to an episode ID.  Two consecutive fires in the same
    episode if the trading-day gap <= `gap`.

    Returns a list of integer episode IDs (same length as fire_dates).
    Uses calendar-day sorting; approximate td gap via calendar days / 1.4.
    """
    if not fire_dates:
        return []
    sorted_dates = sorted(fire_dates)
    ids = [0]
    ep = 0
    for i in range(1, len(sorted_dates)):
        cal_gap = (sorted_dates[i] - sorted_dates[i - 1]).days
        td_approx = cal_gap / 1.4  # approx conversion calendar -> trading days
        if td_approx > gap:
            ep += 1
        ids.append(ep)
    # Map back to original order
    order = sorted(range(len(fire_dates)), key=lambda i: fire_dates[i])
    result = [0] * len(fire_dates)
    for rank, orig_pos in enumerate(order):
        result[orig_pos] = ids[rank]
    return result


# ──────────────────────────────────────────────────────────────────────────
# Episode-block bootstrap
# ──────────────────────────────────────────────────────────────────────────

def episode_block_bootstrap(
    values: np.ndarray,
    episode_ids: np.ndarray,
    stat_fn,
    n_draws: int = 2000,
    ci: float = 0.90,
    rng_seed: int = 42,
) -> dict:
    """Bootstrap by resampling episodes with replacement.

    values: 1D array of metric values (e.g., race_stop_out, 0/1).
    episode_ids: 1D array of integer episode IDs (same length as values).
    stat_fn: callable(values_array) -> scalar.
    n_draws: number of bootstrap draws.
    ci: confidence interval level (default 0.90 -> 90%).

    Returns {
        'point': point estimate on original data,
        'ci_lo': lower bound,
        'ci_hi': upper bound,
        'n_episodes': number of unique episodes,
    }
    """
    values = np.asarray(values, dtype=float)
    episode_ids = np.asarray(episode_ids, dtype=int)

    unique_eps = np.unique(episode_ids)
    n_eps = len(unique_eps)

    # Group indices by episode
    ep_groups: dict[int, np.ndarray] = {}
    for ep in unique_eps:
        ep_groups[ep] = np.where(episode_ids == ep)[0]

    point = stat_fn(values)

    rng = np.random.default_rng(rng_seed)
    boot_stats = np.empty(n_draws)
    for b in range(n_draws):
        drawn_eps = rng.choice(unique_eps, size=n_eps, replace=True)
        boot_idx = np.concatenate([ep_groups[e] for e in drawn_eps])
        boot_stats[b] = stat_fn(values[boot_idx])

    alpha = (1 - ci) / 2
    ci_lo = float(np.nanquantile(boot_stats, alpha))
    ci_hi = float(np.nanquantile(boot_stats, 1 - alpha))

    return {
        "point": float(point),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_episodes": n_eps,
        "n_fires": len(values),
        "n_valid": int(np.sum(~np.isnan(values))),
    }


def stop_out_rate(values: np.ndarray) -> float:
    """Fraction of fires that stopped out.

    Pass the race_stop_out column values (1=stopped, 0=not, NaN=censored).
    Mean of == 1 over non-NaN.
    """
    v = values[~np.isnan(values)]
    if len(v) == 0:
        return np.nan
    return float(np.mean(v == 1))


def liftoff_rate(values: np.ndarray) -> float:
    """Fraction of fires that lifted off.

    Pass the race_liftoff column values (1=liftoff, 0=not, NaN=censored).
    Mean of == 1 over non-NaN.
    """
    v = values[~np.isnan(values)]
    if len(v) == 0:
        return np.nan
    return float(np.mean(v == 1))


def clean_rate(values: np.ndarray) -> float:
    """Fraction of fires where clean15_126 or clean8_21 == 1."""
    v = values[~np.isnan(values)]
    if len(v) == 0:
        return np.nan
    return float(np.mean(v == 1))
