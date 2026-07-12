"""Winner Autopsy Lab — pure computation core.

Program: Long-Hold Thesis lobe, Winner Autopsy department.
Masterplan: research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
Rulings: WA-R1 (no fused score), WA-R2 (ownership context-only), WA-R3 (vocabulary),
         WA-R4 (estimator laws), WA-R5 (display-only), WA-R6 (LLM boundary),
         WA-R7 (A2 firewall), WA-R8 (hypothesis budget), WA-R9 (ledger law),
         WA-R10 (holdable-winner fence).

All functions are PURE — no file I/O, no argparse. The build script handles I/O.
Everything is display-only (_display_only=True, horizon_role="hold_thesis").
No composite scores (WA-R1). No "validated" claims. Nulls printed honestly.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frozen module constants (Detector D v1 — frozen for census)
# ---------------------------------------------------------------------------
LIQUIDITY_FLOOR_USD: float = 25_000_000.0
EXCESS_21D_PP: float = 20.0
EXCESS_42D_PP: float = 25.0
NEW_HIGH_LOOKBACK: int = 63
DV_Z_FLOOR: float = 1.0
DV_5_60_RATIO: float = 1.5
EPISODE_COOLDOWN: int = 63

# Outcome thresholds
DURABLE_FWD_126_PP: float = 15.0
FAILED_FWD_63_PP: float = -10.0
BLOWOFF_RETRACE: float = 0.50

# Gap period (massive store gap)
GAP_PERIOD_START = pd.Timestamp("2021-10-25")
GAP_PERIOD_END = pd.Timestamp("2025-01-02")

# Watch-state computation: bound to recent bars only (MINOR-8)
WATCH_WINDOW_TD: int = 150

# Schema identifiers
SCHEMA_EPISODES: str = "winner_episodes.v2"
SCHEMA_WATCH: str = "breakaway_watch.v1"

# B1 era cutoff (LHB-R5/WA-R4: hardening-ladder features only for episodes t0 >= this date)
B1_ERA_CUTOFF: pd.Timestamp = pd.Timestamp("2014-01-01")

# B1 item codes: hard events trigger a material transaction (1.01 = entry into agreement,
# 2.01 = acquisition/disposition). We default to 1.01/2.01 only (see extract_b1_events
# docstring). 1.02 = termination of agreement (reverse / deal-break event, used for
# hard_event_reversed outcome column).
B1_HARD_ITEMS: frozenset[str] = frozenset({"1.01", "2.01"})
B1_SOFT_ITEMS: frozenset[str] = frozenset({"7.01", "8.01"})
B1_REVERSAL_ITEM: str = "1.02"

# B2 PIT lag: an annual statement is PIT-visible period_end + 120d (conservative; typical
# 10-K filing window is 60-90d, but 120d covers late filers and avoids look-ahead).
B2_PIT_LAG_DAYS: int = 120

# B4 index change archive start (first _seen date in data/sp_index_changes/changes.parquet)
B4_ARCHIVE_START: pd.Timestamp = pd.Timestamp("2026-06-11")

# GICS sector -> SPDR ETF map (verbatim from scripts/grade_us_board.py lines 111-117)
_GICS_ETF: dict[str, str] = {
    "Energy": "XLE",
    "Information Technology": "XLK",
    "Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Communications": "XLC",
}
BENCH: str = "SPY"

# Required keys for winner_case.v1 schema
_CASE_REQUIRED_KEYS: list[str] = [
    "schema",
    "ticker",
    "case_type",
    "episode_year",
    "run_window",
    "t0_hypothesis",
    "thesis_one_liner",
    "mechanism",
    "stage_map",
    "catalyst_ladder",
    "hazards",
    "false_positive_checks",
    "sources",
]


# ---------------------------------------------------------------------------
# Stamp helper
# ---------------------------------------------------------------------------

def stamp(obj: dict[str, Any]) -> dict[str, Any]:
    """Add display-only metadata keys to an artifact dict in-place. Returns obj."""
    obj["_display_only"] = True
    obj["_horizon_role"] = "hold_thesis"
    obj["_version"] = "v1"
    return obj


# ---------------------------------------------------------------------------
# Return / excess helpers
# ---------------------------------------------------------------------------

def _trailing_return(close: pd.Series, n_td: int) -> pd.Series:
    """N trading-day trailing return as a fraction (not percent)."""
    return close.pct_change(n_td)


def compute_excess(
    close: pd.Series,
    bench_close: pd.Series,
    n_td: int,
) -> pd.Series:
    """Excess return of close vs bench_close over n_td trading days, in pp.

    Both series must share a DatetimeIndex. Aligns on the intersection of dates.
    Returns a Series of excess in percentage points.
    """
    common = close.index.intersection(bench_close.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    c = close.reindex(common)
    b = bench_close.reindex(common)
    r_c = c.pct_change(n_td)
    r_b = b.pct_change(n_td)
    return (r_c - r_b) * 100.0


# ---------------------------------------------------------------------------
# Dollar-volume helpers
# ---------------------------------------------------------------------------

def _dollar_volume_series(close: pd.Series, volume: pd.Series | None) -> pd.Series | None:
    """Compute daily dollar volume = close * volume. Returns None if volume absent."""
    if volume is None or volume.empty:
        return None
    common = close.index.intersection(volume.index)
    if len(common) < 2:
        return None
    return close.reindex(common) * volume.reindex(common)


def _median_dv(dv: pd.Series, n: int) -> pd.Series:
    """Rolling n-day median of dollar_volume. Min_periods = max(1, n//2)."""
    return dv.rolling(n, min_periods=max(1, n // 2)).median()


def _dv_zscore(dv: pd.Series, n: int = 21) -> pd.Series:
    """Z-score of dollar_volume relative to n-day rolling mean/std."""
    roll = dv.rolling(n, min_periods=max(1, n // 2))
    mu = roll.mean()
    sigma = roll.std(ddof=1)
    return (dv - mu) / sigma.replace(0, np.nan)


def _dv_ratio(dv: pd.Series, short: int = 5, long: int = 60) -> pd.Series:
    """Ratio of short-window / long-window rolling mean dollar volume."""
    short_ma = dv.rolling(short, min_periods=1).mean()
    long_ma = dv.rolling(long, min_periods=max(1, long // 2)).mean()
    return short_ma / long_ma.replace(0, np.nan)


# ---------------------------------------------------------------------------
# Detector D — episode detection
# ---------------------------------------------------------------------------

def _resolve_benchmark(ticker: str, sector_of: dict[str, str]) -> tuple[str, bool]:
    """Return (benchmark_etf, benchmark_fallback).

    benchmark_fallback=True means we fell through to SPY because the sector
    was not in _GICS_ETF.
    """
    sector = sector_of.get(ticker)
    if sector:
        etf = _GICS_ETF.get(sector)
        if etf:
            return etf, False
    return BENCH, True


def detect_episodes(
    bars: dict[str, pd.DataFrame],
    bench_closes: dict[str, pd.Series],
    sector_of: dict[str, str],
    today: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Detect breakaway onset episodes for all tickers in bars.

    Parameters
    ----------
    bars:
        {ticker: DataFrame} where each DataFrame has at minimum a 'close' column
        and optionally 'volume', 'high', 'low'. Index must be DatetimeIndex
        (trading days, UTC midnight or date-only).
    bench_closes:
        {benchmark_etf: Series} of benchmark close prices.
    sector_of:
        {ticker: GICS sector name}.
    today:
        If provided, truncate all series to this date (inclusive). Defaults to
        the latest date across all bars.

    Returns
    -------
    DataFrame with one row per (ticker, t0) onset:
        ticker, t0, sector, benchmark, benchmark_fallback,
        excess_21d_pp, excess_42d_pp, new_high_63d,
        dollar_vol_z21, dv_5_60_ratio, liquid,
        price_source, gap_leg_crossed, survivorship_biased
    """
    if today is None and bars:
        today = max(
            df.index.max() for df in bars.values() if not df.empty
        )

    rows: list[dict[str, Any]] = []

    for ticker, df in bars.items():
        if df is None or df.empty or "close" not in df.columns:
            continue

        close = df["close"].dropna().sort_index()
        if today is not None:
            close = close[close.index <= today]
        if len(close) < max(EPISODE_COOLDOWN, NEW_HIGH_LOOKBACK, 63) + 5:
            continue

        # Resolve benchmark
        bench_etf, bench_fallback = _resolve_benchmark(ticker, sector_of)
        bench_s = bench_closes.get(bench_etf)
        if bench_s is None or bench_s.empty:
            # Fall back to SPY
            bench_s = bench_closes.get(BENCH)
            bench_etf = BENCH
            bench_fallback = True

        if bench_s is None or bench_s.empty:
            log.debug("detect_episodes: no bench for %s, skipping", ticker)
            continue

        # Align to common dates
        common = close.index.intersection(bench_s.index)
        if len(common) < 65:
            continue
        c = close.reindex(common)
        b = bench_s.reindex(common)

        # Volume / dollar-volume
        volume: pd.Series | None = None
        if "volume" in df.columns:
            volume = df["volume"].dropna().sort_index()
            if today is not None:
                volume = volume[volume.index <= today]

        dv: pd.Series | None = None
        if volume is not None:
            dv_raw = _dollar_volume_series(close, volume)
            if dv_raw is not None:
                dv = dv_raw.reindex(common)

        # Excess returns (pp)
        exc21 = compute_excess(c, b, 21)
        exc42 = compute_excess(c, b, 42)

        # New-high: close >= max(close, prior 63 td incl today)
        rolling_max63 = c.shift(1).rolling(NEW_HIGH_LOOKBACK, min_periods=NEW_HIGH_LOOKBACK).max()
        # "new high" if today's close >= max of prior 63 (note: masterplan says
        # "max(close, prior 63 trading days)" — we interpret as rolling max of
        # the PREVIOUS 63 td; close today must meet or exceed that max)
        new_high = c >= rolling_max63

        # Liquidity: median 20d dollar volume >= floor
        if dv is not None:
            med_dv_20 = _median_dv(dv, 20)
            liquid = med_dv_20 >= LIQUIDITY_FLOOR_USD
        else:
            liquid = pd.Series(False, index=common)

        # Dollar vol z-score (21d)
        if dv is not None:
            dv_z21 = _dv_zscore(dv, 21)
            dv_ratio = _dv_ratio(dv, 5, 60)
        else:
            dv_z21 = pd.Series(np.nan, index=common)
            dv_ratio = pd.Series(np.nan, index=common)

        # Vol confirm
        vol_confirm = (dv_z21 >= DV_Z_FLOOR) | (dv_ratio >= DV_5_60_RATIO)

        # Relative breakaway condition
        rel_breakaway = (exc21 >= EXCESS_21D_PP) | (exc42 >= EXCESS_42D_PP)

        # Candidate condition (all four)
        candidate = liquid & rel_breakaway & new_high & vol_confirm

        # Convert all to numpy for fast loop (avoids per-iteration pandas indexing overhead)
        candidate_arr = candidate.to_numpy(dtype=bool)
        exc21_arr = exc21.to_numpy(dtype=float)
        exc42_arr = exc42.to_numpy(dtype=float)
        new_high_arr = new_high.to_numpy(dtype=bool)
        dv_z21_arr = dv_z21.to_numpy(dtype=float)
        dv_ratio_arr = dv_ratio.to_numpy(dtype=float)
        liquid_arr = liquid.to_numpy(dtype=bool)

        dates_arr = common.to_numpy()

        # Survivorship note: gap-leg detection
        gap_start = GAP_PERIOD_START
        gap_end = GAP_PERIOD_END

        # Episode detection with 63-td cooldown
        last_episode_idx: int = -EPISODE_COOLDOWN - 1

        for i, dt in enumerate(dates_arr):
            if not candidate_arr[i]:
                continue
            # Cooldown check
            if i - last_episode_idx <= EPISODE_COOLDOWN:
                continue

            # This is a valid onset t0
            t0 = pd.Timestamp(dt)

            # MAJOR-4a: Gap-straddle guard for trailing windows.
            # If the 21-td trailing leg spans >45 calendar days OR the 42-td trailing
            # leg spans >75 calendar days, the excess metrics straddle the data gap
            # and are unreliable — reject this candidate entirely.
            if i >= 21:
                leg21_start = pd.Timestamp(dates_arr[i - 21])
                leg21_calendar_days = (t0 - leg21_start).days
                if leg21_calendar_days > 45:
                    continue  # gap-straddle: reject this onset
            if i >= 42:
                leg42_start = pd.Timestamp(dates_arr[i - 42])
                leg42_calendar_days = (t0 - leg42_start).days
                if leg42_calendar_days > 75:
                    continue  # gap-straddle: reject this onset

            # MAJOR-4b: Extended gap_leg_crossed: True when t0 is in gap OR the
            # trailing 42-td window of t0 intersects [GAP_START, GAP_END].
            gap_leg = (gap_start <= t0 <= gap_end)
            if not gap_leg and i >= 42:
                trail42_start = pd.Timestamp(dates_arr[i - 42])
                # Trailing window [trail42_start, t0] intersects gap if they overlap
                if trail42_start <= gap_end and t0 >= gap_start:
                    gap_leg = True

            exc21_v = exc21_arr[i]
            exc42_v = exc42_arr[i]
            dv_z21_v = dv_z21_arr[i]
            dv_ratio_v = dv_ratio_arr[i]

            row: dict[str, Any] = {
                "ticker": ticker,
                "t0": t0,
                "sector": sector_of.get(ticker, ""),
                "benchmark": bench_etf,
                "benchmark_fallback": bench_fallback,
                "excess_21d_pp": float(exc21_v) if not np.isnan(exc21_v) else None,
                "excess_42d_pp": float(exc42_v) if not np.isnan(exc42_v) else None,
                "new_high_63d": bool(new_high_arr[i]),
                "dollar_vol_z21": float(dv_z21_v) if not np.isnan(dv_z21_v) else None,
                "dv_5_60_ratio": float(dv_ratio_v) if not np.isnan(dv_ratio_v) else None,
                "liquid": bool(liquid_arr[i]),
                "price_source": "",  # set by build script
                "gap_leg_crossed": gap_leg,
                "survivorship_biased": False,  # annotated by build script per dead-name status
            }
            rows.append(row)
            last_episode_idx = i

    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "t0", "sector", "benchmark", "benchmark_fallback",
            "excess_21d_pp", "excess_42d_pp", "new_high_63d",
            "dollar_vol_z21", "dv_5_60_ratio", "liquid",
            "price_source", "gap_leg_crossed", "survivorship_biased",
        ])

    out = pd.DataFrame(rows)
    out["t0"] = pd.to_datetime(out["t0"])
    return out.sort_values(["ticker", "t0"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Outcome labeling
# ---------------------------------------------------------------------------

def label_outcomes(
    close: pd.Series,
    bench: pd.Series,
    t0: pd.Timestamp,
) -> dict[str, Any]:
    """Compute forward outcome labels for an episode onset at t0.

    Parameters
    ----------
    close:
        Ticker close series (DatetimeIndex).
    bench:
        Benchmark close series (DatetimeIndex).
    t0:
        Episode onset date.

    Returns
    -------
    dict with keys:
        fwd_excess_21d_pp, fwd_excess_63d_pp, fwd_excess_126d_pp, fwd_excess_252d_pp
            (float | None — None if horizon unmatured)
        clean_hold (bool | None)
        blow_off (bool | None)
        durable_winner (bool | None)
        failed (bool | None)
        outcome_label: str in {durable_winner, clean_hold, blow_off, failed, unmatured}
    """
    # BLOCKER-1 guard: empty or None inputs
    if close is None or close.empty or bench is None or bench.empty:
        return _empty_outcomes()

    # Align
    common = close.index.intersection(bench.index)
    if len(common) == 0:
        return _empty_outcomes()
    c = close.reindex(common).dropna().sort_index()
    b = bench.reindex(common).dropna().sort_index()

    if c.empty or b.empty:
        return _empty_outcomes()

    # Coerce to DatetimeIndex so >= t0 comparisons work
    if not isinstance(c.index, pd.DatetimeIndex):
        try:
            c.index = pd.to_datetime(c.index)
            b.index = pd.to_datetime(b.index)
        except Exception:  # noqa: BLE001
            return _empty_outcomes()

    # Find t0 position
    if t0 not in c.index:
        # Find nearest available date >= t0
        future_idx = c.index[c.index >= t0]
        if len(future_idx) == 0:
            return _empty_outcomes()
        t0_actual = future_idx[0]
    else:
        t0_actual = t0

    # Verify t0 is within the index range
    if t0_actual > c.index[-1]:
        return _empty_outcomes()

    pos = c.index.get_loc(t0_actual)
    c0 = float(c.iloc[pos])
    b0 = float(b.iloc[pos])

    def _fwd_excess(n_td: int) -> float | None:
        fwd_pos = pos + n_td
        if fwd_pos >= len(c):
            return None
        cn = float(c.iloc[fwd_pos])
        bn = float(b.iloc[fwd_pos])
        if b0 == 0 or c0 == 0:
            return None
        ret_c = (cn / c0 - 1.0) * 100.0
        ret_b = (bn / b0 - 1.0) * 100.0
        return round(ret_c - ret_b, 4)

    fwd21 = _fwd_excess(21)
    fwd63 = _fwd_excess(63)
    fwd126 = _fwd_excess(126)
    fwd252 = _fwd_excess(252)

    # MAJOR-2: maturity guards — these fields must be None unless the FULL forward
    # window is present (not partial).  pos + N < len(c) means bar at pos+N exists.
    full_21td_window = (pos + 21 < len(c))
    full_63td_window = (pos + 63 < len(c))
    full_126td_window = (pos + 126 < len(c))

    # blow_off: None unless full 21-td forward window exists
    blow_off: bool | None = None
    if full_21td_window:
        # Blow-off: >=50% of trailing 21d impulse retraced within 21 td after t0
        # trailing 21d impulse = close[t0] - close[t0 - 21td]
        prior_pos = max(0, pos - 21)
        c_t0m21 = float(c.iloc[prior_pos])
        impulse = c0 - c_t0m21
        if impulse > 0:
            fwd21_close = c.iloc[pos + 1 : pos + 22]
            min_fwd = float(fwd21_close.min())
            retrace = (c0 - min_fwd) / impulse if impulse != 0 else 0.0
            blow_off = retrace >= BLOWOFF_RETRACE

    # clean_hold: None unless full 126-td forward window exists
    # (clean_hold covers the full hold window — a partial window is indeterminate)
    clean_hold: bool | None = None
    if full_126td_window:
        fwd_close = c.iloc[pos + 1 : pos + 127]
        dropped_below = (fwd_close < c0).any()
        if not dropped_below:
            roll_max_at_t0 = float(c.iloc[max(0, pos - NEW_HIGH_LOOKBACK + 1) : pos + 1].max())
            new_high_in_fwd = (fwd_close > roll_max_at_t0).any()
            clean_hold = bool(new_high_in_fwd)
        else:
            clean_hold = False

    # durable_winner: None unless full 126-td forward window exists
    durable_winner: bool | None = None
    if full_126td_window and fwd126 is not None and clean_hold is not None:
        durable_winner = (fwd126 >= DURABLE_FWD_126_PP) and bool(clean_hold)

    # failed: None unless full 63-td forward window exists
    failed: bool | None = None
    if full_63td_window and fwd63 is not None:
        failed = fwd63 <= FAILED_FWD_63_PP

    # outcome_label priority: durable_winner > blow_off > failed > clean_hold > unmatured
    # If fwd_excess_126d is None (window not matured), label must be 'unmatured'
    if fwd126 is None:
        outcome_label = "unmatured"
    elif durable_winner is True:
        outcome_label = "durable_winner"
    elif blow_off is True:
        outcome_label = "blow_off"
    elif failed is True:
        outcome_label = "failed"
    elif clean_hold is True:
        outcome_label = "clean_hold"
    else:
        outcome_label = "unmatured"

    return {
        "fwd_excess_21d_pp": fwd21,
        "fwd_excess_63d_pp": fwd63,
        "fwd_excess_126d_pp": fwd126,
        "fwd_excess_252d_pp": fwd252,
        "clean_hold": clean_hold,
        "blow_off": blow_off,
        "durable_winner": durable_winner,
        "failed": failed,
        "outcome_label": outcome_label,
    }


def _empty_outcomes() -> dict[str, Any]:
    return {
        "fwd_excess_21d_pp": None,
        "fwd_excess_63d_pp": None,
        "fwd_excess_126d_pp": None,
        "fwd_excess_252d_pp": None,
        "clean_hold": None,
        "blow_off": None,
        "durable_winner": None,
        "failed": None,
        "outcome_label": "unmatured",
    }


# ---------------------------------------------------------------------------
# Watch states (live detector evaluated at latest bar)
# ---------------------------------------------------------------------------

_WATCH_STATES = frozenset({
    "breakaway", "emerging", "digestion", "continuation", "failed", "none"
})


def compute_watch_states(
    bars: dict[str, pd.DataFrame],
    bench_closes: dict[str, pd.Series],
    sector_of: dict[str, str],
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Evaluate Detector D at the latest bar per ticker; return watch state rows.

    Detector D is identical to detect_episodes — this is the same function evaluated
    at as_of instead of over history. No composite score (WA-R1).

    States:
        breakaway  — candidate condition met in the last 5 td
        emerging   — rel_breakaway true but not (new_high AND vol_confirm)
        digestion  — post-onset (prior episode in last EPISODE_COOLDOWN td),
                     shallow pullback holding above t0 close
        continuation — post-onset, close within 5% of rolling 63d high
        failed     — post-onset, close dropped below t0 close on volume
        none       — none of the above

    Returns DataFrame with one row per ticker that has any price data:
        ticker, sector, benchmark, benchmark_fallback, state,
        excess_21d_pp, excess_42d_pp, new_high_63d,
        dollar_vol_z21, days_in_state, hazards
    """
    if as_of is None and bars:
        as_of = max(
            df.index.max() for df in bars.values() if not df.empty
        )

    # MINOR-8: bound each ticker's bars to the last WATCH_WINDOW_TD trading days
    # so that detect_episodes only processes recent history for state classification.
    # This keeps nightly cost manageable at 20k-name scale.
    def _trim_to_watch_window(df: pd.DataFrame) -> pd.DataFrame:
        """Return the last WATCH_WINDOW_TD rows of df (close already sorted)."""
        if df is None or df.empty:
            return df
        if as_of is not None:
            df = df[df.index <= as_of]
        if len(df) > WATCH_WINDOW_TD:
            return df.iloc[-WATCH_WINDOW_TD:]
        return df

    watch_bars = {t: _trim_to_watch_window(df) for t, df in bars.items()}

    # Run episode detection over the trimmed window for state classification
    episodes_df = detect_episodes(watch_bars, bench_closes, sector_of, today=as_of)

    rows: list[dict[str, Any]] = []

    for ticker, df in bars.items():
        if df is None or df.empty or "close" not in df.columns:
            continue

        close = df["close"].dropna().sort_index()
        if as_of is not None:
            close = close[close.index <= as_of]
        if len(close) < 25:
            continue

        bench_etf, bench_fallback = _resolve_benchmark(ticker, sector_of)
        bench_s = bench_closes.get(bench_etf)
        if bench_s is None or bench_s.empty:
            bench_s = bench_closes.get(BENCH)
            bench_etf = BENCH
            bench_fallback = True
        if bench_s is None:
            continue

        common = close.index.intersection(bench_s.index)
        if len(common) < 25:
            continue
        c = close.reindex(common)
        b = bench_s.reindex(common)

        volume: pd.Series | None = None
        if "volume" in df.columns:
            vol_raw = df["volume"].dropna().sort_index()
            if as_of is not None:
                vol_raw = vol_raw[vol_raw.index <= as_of]
            volume = vol_raw

        dv: pd.Series | None = None
        if volume is not None:
            dv_raw = _dollar_volume_series(close, volume)
            if dv_raw is not None:
                dv = dv_raw.reindex(common)

        # Latest bar metrics
        exc21_s = compute_excess(c, b, 21)
        exc42_s = compute_excess(c, b, 42)

        rolling_max63 = c.shift(1).rolling(NEW_HIGH_LOOKBACK, min_periods=NEW_HIGH_LOOKBACK).max()
        new_high_s = c >= rolling_max63

        if dv is not None:
            dv_z21_s = _dv_zscore(dv, 21)
            dv_ratio_s = _dv_ratio(dv, 5, 60)
            med_dv_20 = _median_dv(dv, 20)
            liquid_s = med_dv_20 >= LIQUIDITY_FLOOR_USD
        else:
            dv_z21_s = pd.Series(np.nan, index=common)
            dv_ratio_s = pd.Series(np.nan, index=common)
            liquid_s = pd.Series(False, index=common)

        rel_breakaway_s = (exc21_s >= EXCESS_21D_PP) | (exc42_s >= EXCESS_42D_PP)
        vol_confirm_s = (dv_z21_s >= DV_Z_FLOOR) | (dv_ratio_s >= DV_5_60_RATIO)

        # Latest values
        exc21_latest = float(exc21_s.iloc[-1]) if not np.isnan(exc21_s.iloc[-1]) else None
        exc42_latest = float(exc42_s.iloc[-1]) if not np.isnan(exc42_s.iloc[-1]) else None
        new_high_latest = bool(new_high_s.iloc[-1]) if not pd.isna(new_high_s.iloc[-1]) else False
        dv_z21_latest = float(dv_z21_s.iloc[-1]) if not np.isnan(dv_z21_s.iloc[-1]) else None
        rel_break_latest = bool(rel_breakaway_s.iloc[-1]) if not pd.isna(rel_breakaway_s.iloc[-1]) else False
        vol_conf_latest = bool(vol_confirm_s.iloc[-1]) if not pd.isna(vol_confirm_s.iloc[-1]) else False
        liquid_latest = bool(liquid_s.iloc[-1]) if not pd.isna(liquid_s.iloc[-1]) else False

        # Determine state
        # Check if there is a recent episode (within EPISODE_COOLDOWN td)
        ticker_eps = (
            episodes_df[episodes_df["ticker"] == ticker]
            if not episodes_df.empty and "ticker" in episodes_df.columns
            else pd.DataFrame()
        )

        latest_episode_t0: pd.Timestamp | None = None
        t0_close: float | None = None
        if not ticker_eps.empty:
            latest_ep = ticker_eps.sort_values("t0").iloc[-1]
            latest_episode_t0 = pd.Timestamp(latest_ep["t0"])

        # Check how many td since episode t0
        days_in_state: int = 0
        in_cooldown = False
        if latest_episode_t0 is not None and as_of is not None:
            # Count trading days between t0 and as_of in the close index
            td_since = max(0, int((common > latest_episode_t0).sum()))
            if td_since <= EPISODE_COOLDOWN:
                in_cooldown = True
                # Close at t0
                if latest_episode_t0 in c.index:
                    t0_close = float(c.loc[latest_episode_t0])
                days_in_state = td_since

        state: str
        if in_cooldown and latest_episode_t0 is not None:
            # Classify post-onset state
            c_latest = float(c.iloc[-1])
            if t0_close is not None:
                if c_latest < t0_close:
                    state = "failed"
                else:
                    # continuation: within 5% of rolling 63d high
                    roll_max = float(c.iloc[-NEW_HIGH_LOOKBACK:].max()) if len(c) >= NEW_HIGH_LOOKBACK else float(c.max())
                    if c_latest >= 0.95 * roll_max:
                        state = "continuation"
                    else:
                        state = "digestion"
            else:
                state = "digestion"
            # Breakaway: candidate met in last 5 td
            cand_s = liquid_s & rel_breakaway_s & new_high_s & vol_confirm_s
            if cand_s.iloc[-5:].any():
                state = "breakaway"
        else:
            # Not in cooldown — check live detector
            cand_met = liquid_latest and rel_break_latest and new_high_latest and vol_conf_latest
            if cand_met:
                # In the last 5 td?
                cand_s = liquid_s & rel_breakaway_s & new_high_s & vol_confirm_s
                if cand_s.iloc[-5:].any():
                    state = "breakaway"
                    days_in_state = int(cand_s.iloc[-5:].sum())
                else:
                    state = "none"
            elif rel_break_latest:
                state = "emerging"
                days_in_state = 0
            else:
                state = "none"

        # Hazard flags (masterplan vocabulary)
        hazards: list[str] = []
        if exc21_latest is not None and exc21_latest >= 40.0:
            hazards.append("extended_after_vertical_move")
        if new_high_latest and exc21_latest is not None and exc21_latest >= 20.0:
            hazards.append("chase_risk_elevated")

        rows.append({
            "ticker": ticker,
            "sector": sector_of.get(ticker, ""),
            "benchmark": bench_etf,
            "benchmark_fallback": bench_fallback,
            "state": state,
            "excess_21d_pp": exc21_latest,
            "excess_42d_pp": exc42_latest,
            "new_high_63d": new_high_latest,
            "dollar_vol_z21": dv_z21_latest,
            "days_in_state": days_in_state,
            "hazards": hazards,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "sector", "benchmark", "benchmark_fallback", "state",
            "excess_21d_pp", "excess_42d_pp", "new_high_63d",
            "dollar_vol_z21", "days_in_state", "hazards",
        ])

    return pd.DataFrame(rows).sort_values(
        "excess_21d_pp", ascending=False, na_position="last"
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Control sampling
# ---------------------------------------------------------------------------

def sample_controls(
    episode_row: pd.Series,
    bars: dict[str, pd.DataFrame],
    sector_of: dict[str, str],
    pit_membership: pd.DataFrame,
    k: int = 20,
) -> list[str]:
    """Sample control tickers for an episode.

    Same-sector, PIT-active at t0, liquidity floor met, NOT in candidate
    state within ±21 td of t0. Deterministic (sorted by ticker, no RNG).

    Parameters
    ----------
    episode_row:
        Row from episodes_df (must have ticker, t0, sector, benchmark).
    bars:
        Full bars dict.
    sector_of:
        {ticker: sector}.
    pit_membership:
        sp1500_pit_membership DataFrame (cols: ticker, start_date, end_date, src).
    k:
        Max number of controls to return.

    Returns
    -------
    Sorted list of control ticker strings.
    """
    target_ticker = str(episode_row["ticker"])
    t0 = pd.Timestamp(episode_row["t0"])
    target_sector = str(episode_row.get("sector", "") or "")

    # Matched controls require a real sector cohort. An unmapped sector ("")
    # would match every other unmapped ticker — wrong cohort and quadratic at
    # whole-market scale. No sector map -> no controls (n_controls=0, honest).
    if not target_sector or target_sector in ("nan", "None"):
        return []

    # PIT-active at t0: start_date <= t0, end_date >= t0 OR end_date is NaT
    if pit_membership is not None and not pit_membership.empty:
        mask_start = pit_membership["start_date"] <= t0
        end_dates = pit_membership["end_date"]
        mask_end = end_dates.isna() | (end_dates >= t0)
        active = set(
            pit_membership.loc[mask_start & mask_end, "ticker"]
            .astype(str)
            .unique()
        )
    else:
        active = set(bars.keys())

    # Same sector, excluding the episode ticker
    raw_candidates = sorted([
        t for t in active
        if t != target_ticker
        and sector_of.get(t, "") == target_sector
        and t in bars
    ])

    _CONTROL_WINDOW_TD = 21  # ±21 td exclusion window per ruling

    # First pass: compute median DV at t0 for each candidate and apply all filters.
    # MINOR-6: exclude candidates in a candidate (breakaway) state within ±21 td of t0.
    # MINOR-6: sort by closeness of median DV to the target's median DV (not alphabetical).
    # MINOR-7: use searchsorted(t0, side="right") - 1 to stay strictly ≤ t0.

    # Compute target median DV at t0 for closeness ranking
    target_med_dv: float | None = None
    target_df = bars.get(target_ticker)
    if target_df is not None and "close" in target_df.columns and "volume" in target_df.columns:
        tc = target_df["close"].dropna().sort_index()
        tv = target_df["volume"].dropna().sort_index()
        tdv = _dollar_volume_series(tc, tv)
        if tdv is not None:
            # MINOR-7: strictly ≤ t0
            tidx = tdv.index.searchsorted(t0, side="right") - 1
            if 0 <= tidx < len(tdv):
                slice_start = max(0, tidx - 20)
                target_med_dv = float(tdv.iloc[slice_start : tidx + 1].median())

    qualified: list[tuple[float, str]] = []  # (abs_dv_diff, ticker)

    for ticker in raw_candidates:
        df = bars.get(ticker)
        if df is None or df.empty or "close" not in df.columns:
            continue

        close = df["close"].dropna().sort_index()
        if close.empty:
            continue

        # Check ticker was active around t0
        near_t0 = close.index[
            (close.index >= t0 - pd.Timedelta(days=35)) &
            (close.index <= t0 + pd.Timedelta(days=35))
        ]
        if len(near_t0) == 0:
            continue

        # Liquidity check at t0
        volume: pd.Series | None = None
        if "volume" in df.columns:
            volume = df["volume"].dropna().sort_index()
        if volume is None:
            continue

        dv_raw = _dollar_volume_series(close, volume)
        if dv_raw is None:
            continue

        # MINOR-7: use searchsorted(t0, side="right") - 1 to stay strictly ≤ t0
        idx_at_t0 = dv_raw.index.searchsorted(t0, side="right") - 1
        if idx_at_t0 < 0:
            continue

        dv_at_t0 = dv_raw.reindex(close.index)
        med_dv_slice = dv_at_t0.iloc[max(0, idx_at_t0 - 20) : idx_at_t0 + 1]
        if med_dv_slice.empty or med_dv_slice.median() < LIQUIDITY_FLOOR_USD:
            continue

        med_dv_val = float(med_dv_slice.median())

        # MINOR-6: exclude candidates in a breakaway candidate state within ±21 td of t0.
        # Lightweight check: look for any bar in [t0-21td, t0+21td] where the ticker
        # itself would meet the excess thresholds vs a flat benchmark (conservative proxy:
        # just check whether its own 21d return >= 20pp, which is the breakaway entry bar).
        # We avoid running full detect_episodes for speed — use the excess series already
        # available for the ticker's close vs itself shifted.
        in_candidate_state = False
        try:
            # Find bars in ±21 td around t0 on the close index
            close_idx = close.index
            lo_pos = max(0, close_idx.searchsorted(t0 - pd.Timedelta(days=35), side="left"))
            hi_pos = min(len(close_idx), close_idx.searchsorted(t0 + pd.Timedelta(days=35), side="right"))
            window_td_count = min(hi_pos - lo_pos, _CONTROL_WINDOW_TD * 2 + 5)
            if window_td_count >= 22:
                # Check if the 21d return in this window exceeds EXCESS_21D_PP (raw, no bench)
                # This is a conservative proxy — a proper check would compare vs bench.
                window_close = close.iloc[max(0, hi_pos - 22) : hi_pos]
                if len(window_close) >= 22:
                    raw_ret = (float(window_close.iloc[-1]) / float(window_close.iloc[0]) - 1.0) * 100.0
                    if raw_ret >= EXCESS_21D_PP:
                        in_candidate_state = True
        except Exception:  # noqa: BLE001
            pass  # conservative: don't exclude on error

        if in_candidate_state:
            continue

        # Compute DV closeness to target
        dv_diff = abs(med_dv_val - target_med_dv) if target_med_dv is not None else 0.0
        qualified.append((dv_diff, ticker))

    # Sort by DV closeness (ascending diff), then by ticker for determinism within ties
    qualified.sort(key=lambda x: (x[0], x[1]))
    controls = [ticker for _, ticker in qualified[:k]]
    return controls


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features(
    ticker: str,
    t0: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    bench_closes: dict[str, pd.Series] | None = None,
    sector_of: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extract PIT-safe pre-onset price/volume geometry features at t0.

    All features are computed from data available STRICTLY BEFORE t0 (t0 - 1td window).
    Tier-1 historical price/volume family only (v1; WA-R7 firewall for A2 families).

    Returns dict with keys:
        drawdown_from_252d_high_at_t0m21: float | None
            Drawdown from 252d high, computed at t0 - 21 trading days.
        days_below_200dma: int | None
            Number of trading days below 200dma in the 63 td before t0.
        rs_turn_21_63: bool | None
            True if RS (vs benchmark) improved from the -63d to -21d window.
        dv_z21: float | None
            Dollar-volume z-score at t0.
        updown_dollar_vol_ratio: float | None
            Mean DV on up-days / mean DV on down-days over prior 21 td.
        close_location_value_or_None: float | None
            Average CLV over prior 21 td (requires high/low; None if absent).

    TODO (WA-R7 firewall — A2 roster families excluded):
        F1 fundamentals, F2 washout_tf, F3 expect_drift, F4 insider features
        are intentionally omitted for episodes with t0 >= 2024-01-01 until the
        A2 analysis script commits. Do NOT add these without a separate ruling.
    """
    df = bars.get(ticker)
    if df is None or df.empty:
        return _empty_features()

    close = df["close"].dropna().sort_index()
    # Use only data strictly before t0 for PIT safety
    close_pre = close[close.index < t0]
    if len(close_pre) < 25:
        return _empty_features()

    # Volume
    volume: pd.Series | None = None
    if "volume" in df.columns:
        vol = df["volume"].dropna().sort_index()
        volume = vol[vol.index < t0]

    # --- drawdown_from_252d_high_at_t0m21 ---
    # At t0 - 21 td, what was the drawdown from the 252d high?
    drawdown_from_252d: float | None = None
    if len(close_pre) >= 22:
        close_at_t0m21 = close_pre.iloc[-22]
        high_252 = float(close_pre.iloc[max(0, len(close_pre) - 252) : len(close_pre) - 21].max())
        if high_252 > 0:
            drawdown_from_252d = round((close_at_t0m21 / high_252 - 1.0) * 100.0, 4)

    # --- days_below_200dma ---
    days_below_200: int | None = None
    if len(close_pre) >= 200:
        window_63 = close_pre.iloc[-63:]
        # 200dma at each point in the 63d window
        ma200 = close_pre.rolling(200, min_periods=180).mean()
        ma200_63 = ma200.iloc[-63:]
        if not ma200_63.isna().all():
            below = (window_63 < ma200_63).sum()
            days_below_200 = int(below)

    # --- rs_turn_21_63 ---
    rs_turn: bool | None = None
    if bench_closes is not None and sector_of is not None:
        bench_etf, _ = _resolve_benchmark(ticker, sector_of)
        bench_s = bench_closes.get(bench_etf)
        if bench_s is None:
            bench_s = bench_closes.get(BENCH)
        if bench_s is not None:
            common = close_pre.index.intersection(bench_s.index)
            if len(common) >= 65:
                cp = close_pre.reindex(common)
                bp = bench_s.reindex(common)
                exc21 = compute_excess(cp, bp, 21)
                exc63 = compute_excess(cp, bp, 63)
                if len(exc21) >= 1 and len(exc63) >= 1:
                    rs_at_m21 = float(exc21.iloc[-22]) if len(exc21) > 22 else None
                    rs_at_m63 = float(exc63.iloc[-64]) if len(exc63) > 64 else None
                    if rs_at_m21 is not None and rs_at_m63 is not None:
                        rs_turn = bool(rs_at_m21 > rs_at_m63)

    # --- dv_z21 ---
    dv_z21_val: float | None = None
    if volume is not None and len(close_pre) >= 22:
        dv_raw = _dollar_volume_series(close_pre, volume.reindex(close_pre.index))
        if dv_raw is not None and len(dv_raw) >= 22:
            dv_z = _dv_zscore(dv_raw, 21)
            v = dv_z.iloc[-1]
            dv_z21_val = float(v) if not np.isnan(v) else None

    # --- updown_dollar_vol_ratio ---
    updown_ratio: float | None = None
    if volume is not None and len(close_pre) >= 22:
        dv_raw = _dollar_volume_series(close_pre, volume.reindex(close_pre.index))
        if dv_raw is not None:
            dv_21 = dv_raw.iloc[-21:]
            ret_21 = close_pre.iloc[-21:].pct_change()
            up_mask = ret_21 > 0
            down_mask = ret_21 < 0
            up_dv = dv_21[up_mask]
            down_dv = dv_21[down_mask]
            if len(down_dv) > 0 and down_dv.mean() > 0:
                updown_ratio = round(float(up_dv.mean() / down_dv.mean()), 4)

    # --- close_location_value ---
    clv: float | None = None
    if "high" in df.columns and "low" in df.columns:
        high = df["high"].dropna().sort_index()
        low = df["low"].dropna().sort_index()
        high_pre = high[high.index < t0].iloc[-21:]
        low_pre = low[low.index < t0].iloc[-21:]
        close_21 = close_pre.iloc[-21:]
        # Align all three
        idx = close_21.index.intersection(high_pre.index).intersection(low_pre.index)
        if len(idx) >= 5:
            h = high_pre.reindex(idx)
            l_s = low_pre.reindex(idx)
            c_ = close_21.reindex(idx)
            hl_range = h - l_s
            hl_range = hl_range.replace(0, np.nan)
            clv_s = ((c_ - l_s) - (h - c_)) / hl_range
            clv = round(float(clv_s.mean()), 4) if not clv_s.isna().all() else None

    return {
        "drawdown_from_252d_high_at_t0m21": drawdown_from_252d,
        "days_below_200dma": days_below_200,
        "rs_turn_21_63": rs_turn,
        "dv_z21": dv_z21_val,
        "updown_dollar_vol_ratio": updown_ratio,
        "close_location_value_or_None": clv,
        # WA-R7 stubs — do NOT populate until A2 script commits + ruling
        # "f1_fundamentals": None,   # TODO WA-R7: join after A2 freeze
        # "f2_washout_tf": None,     # TODO WA-R7: join after A2 freeze
        # "f3_expect_drift": None,   # TODO WA-R7: join after A2 freeze
        # "f4_insider": None,        # TODO WA-R7: join after A2 freeze
    }


def _empty_features() -> dict[str, Any]:
    return {
        "drawdown_from_252d_high_at_t0m21": None,
        "days_below_200dma": None,
        "rs_turn_21_63": None,
        "dv_z21": None,
        "updown_dollar_vol_ratio": None,
        "close_location_value_or_None": None,
    }


# ---------------------------------------------------------------------------
# B-family feature extraction (B1, B2, B4)
# ---------------------------------------------------------------------------

def _parse_items_list(items_str: str | None) -> list[str]:
    """Parse comma-separated 8-K item codes into a sorted list of strings.

    e.g. "1.01,2.03,8.01" -> ["1.01", "2.03", "8.01"]
    Returns [] if items_str is None or empty.
    """
    if not items_str or not isinstance(items_str, str):
        return []
    return [s.strip() for s in items_str.split(",") if s.strip()]


def extract_b1_hardening_ladder(
    ticker: str,
    t0: pd.Timestamp,
    events_df: pd.DataFrame,
) -> dict[str, Any]:
    """B1 — Hardening-ladder event features from data/edgar/material_8k_events.parquet.

    Era restriction (LHB-R5 / WA-R4): episodes with t0 < 2014-01-01 get all columns
    set to None. This is the earliest date for which 8-K EDGAR submissions-feed
    backfill coverage is considered adequate for event-density comparisons.

    Hard items (B1_HARD_ITEMS): Item 1.01 (entry into agreement) and Item 2.01
    (acquisition/disposition). We intentionally omit Item 2.02 (earnings) because:
    (a) the masterplan's earnings-store mention was conditional on "if cheap"; the
    earnings_8k_dates store does not align cleanly with material_8k_events ticker-keys
    in this worktree; and (b) earnings are already captured separately as a context
    layer via the earnings_8k_dates store. This decision is noted in the column docstring.

    Soft items (B1_SOFT_ITEMS): Item 7.01 (Reg FD) and 8.01 (other events).

    hard_event_reversed (forward-only outcome, NOT a PIT input): an Item 1.02
    (termination of agreement / deal-break) filed within 252 trading-calendar days
    AFTER t0. This is a descriptive forward outcome for display only. 1.02 historical
    coverage is limited to whatever the submissions-feed backfill reached before the
    W2b expansion; we report this via b1_coverage.

    Parameters
    ----------
    ticker:
        Ticker string.
    t0:
        Episode onset date (pd.Timestamp).
    events_df:
        material_8k_events.parquet DataFrame (ALL rows; we filter inside).
        Required columns: ticker, filing_date, items.

    Returns
    -------
    dict with keys:
        hard_event_count_126d  int | None  # era-gated
        soft_event_count_126d  int | None  # era-gated
        soft_then_hard         bool | None # any soft strictly before any hard in [t0-126d, t0)
        days_soft_to_hard      int | None  # days from earliest soft to earliest subsequent hard
        hard_event_reversed    bool | None # Item 1.02 within 252cd after t0 (outcome column)
        b1_coverage            str         # "post_2014_only" | "pre_era_cutoff" | "unavailable"
    """
    _empty: dict[str, Any] = {
        "hard_event_count_126d": None,
        "soft_event_count_126d": None,
        "soft_then_hard": None,
        "days_soft_to_hard": None,
        "hard_event_reversed": None,
        "b1_coverage": "unavailable",
    }

    if events_df is None or events_df.empty:
        return _empty

    required = {"ticker", "filing_date", "items"}
    if not required.issubset(set(events_df.columns)):
        return _empty

    # Era gate
    if t0 < B1_ERA_CUTOFF:
        return {
            "hard_event_count_126d": None,
            "soft_event_count_126d": None,
            "soft_then_hard": None,
            "days_soft_to_hard": None,
            "hard_event_reversed": None,
            "b1_coverage": "pre_era_cutoff",
        }

    # Filter to this ticker
    ticker_mask = events_df["ticker"].astype(str) == str(ticker)
    ev = events_df[ticker_mask].copy()
    if ev.empty:
        return {**_empty, "b1_coverage": "post_2014_only"}

    # Parse filing_date to Timestamp
    try:
        ev["_fd"] = pd.to_datetime(ev["filing_date"], errors="coerce")
    except Exception:  # noqa: BLE001
        return {**_empty, "b1_coverage": "post_2014_only"}

    ev = ev.dropna(subset=["_fd"])
    if ev.empty:
        return {**_empty, "b1_coverage": "post_2014_only"}

    # Pre-onset window: filing_date strictly < t0, within 126 calendar days of t0
    window_start = t0 - pd.Timedelta(days=126)
    pre_mask = (ev["_fd"] < t0) & (ev["_fd"] >= window_start)
    pre_ev = ev[pre_mask].copy()

    # For each row, parse the items list and explode to per-item rows
    def _has_item(items_str: str | None, item_codes: frozenset[str]) -> bool:
        parsed = _parse_items_list(items_str)
        return any(code in item_codes for code in parsed)

    hard_count = 0
    soft_count = 0
    hard_dates: list[pd.Timestamp] = []
    soft_dates: list[pd.Timestamp] = []

    for _, row in pre_ev.iterrows():
        items_str = row.get("items")
        fd = row["_fd"]
        is_hard = _has_item(items_str, B1_HARD_ITEMS)
        is_soft = _has_item(items_str, B1_SOFT_ITEMS)
        if is_hard:
            hard_count += 1
            hard_dates.append(pd.Timestamp(fd))
        if is_soft:
            soft_count += 1
            soft_dates.append(pd.Timestamp(fd))

    # soft_then_hard: any soft strictly before any hard (in the pre-onset window)
    soft_then_hard: bool | None = None
    days_soft_to_hard: int | None = None
    if soft_dates and hard_dates:
        earliest_soft = min(soft_dates)
        earliest_hard_after_soft = min(
            (d for d in hard_dates if d > earliest_soft), default=None
        )
        if earliest_hard_after_soft is not None:
            soft_then_hard = True
            days_soft_to_hard = int((earliest_hard_after_soft - earliest_soft).days)
        else:
            soft_then_hard = False
    elif hard_dates or soft_dates:
        # Only one type present — soft_then_hard is False (no sequence)
        soft_then_hard = False

    # hard_event_reversed: Item 1.02 within 252 calendar days AFTER t0
    # Coverage note: historical 1.02 rows depend on the submissions-feed backfill depth
    # (W2b expansion); early years may have incomplete coverage.
    post_mask = (ev["_fd"] >= t0) & (
        ev["_fd"] <= t0 + pd.Timedelta(days=252)
    )
    post_ev = ev[post_mask]
    # Semantic guard (opus review): "reversed" is only meaningful when a HARD event
    # was actually tracked pre-onset. A post-t0 Item 1.02 with no tracked hard event
    # is not a reversal of anything — emit None (not-applicable), never False/True,
    # so the column cannot conflate "no hard event to reverse" with "held firm".
    hard_event_reversed: bool | None
    if hard_count == 0:
        hard_event_reversed = None
    else:
        hard_event_reversed = False
        for _, row in post_ev.iterrows():
            if B1_REVERSAL_ITEM in _parse_items_list(row.get("items")):
                hard_event_reversed = True
                break

    return {
        "hard_event_count_126d": hard_count,
        "soft_event_count_126d": soft_count,
        "soft_then_hard": soft_then_hard,
        "days_soft_to_hard": days_soft_to_hard,
        "hard_event_reversed": hard_event_reversed,
        "b1_coverage": "post_2014_only",
    }


def extract_b2_self_funding(
    ticker: str,
    t0: pd.Timestamp,
    statements_df: pd.DataFrame,
) -> dict[str, Any]:
    """B2 — Self-funding crossover features from data/edgar/statements.parquet (ANNUAL).

    PIT rule: a statement row is visible at t0 if period_end + 120d <= t0
    (B2_PIT_LAG_DAYS = 120). We take the latest two PIT-visible annual rows
    and check whether both years have cfo > capex AND revenue is growing year-on-year.

    FFB-R8 note: quarterly cfo/capex are ~66% null due to YTD-only tagging on 10-Qs.
    B2 uses annual grain only (data/edgar/statements.parquet, not statements_quarterly).
    Working-capital timing legs are omitted — annual filing does not carry interim
    working-capital granularity.

    WA-R7 firewall: for episodes with t0 >= 2024-01-01, self_funded_at_t0 is a
    fundamental-family (F1/B2) column and MUST NOT be included in any cross-case
    aggregate table until A2 commits. The panel's feature_coverage block MUST split
    non-null counts at the 2024-01-01 boundary.

    Parameters
    ----------
    ticker:
        Ticker string.
    t0:
        Episode onset date (pd.Timestamp).
    statements_df:
        Annual statements.parquet DataFrame (ALL rows; we filter inside).
        Required columns: ticker, period_end, cfo, capex, revenue.

    Returns
    -------
    dict with keys:
        self_funded_at_t0   bool | None  — both latest PIT years: cfo>capex AND rev growing
        b2_cfo_y0           float | None — cfo in the most recent PIT year
        b2_cfo_y1           float | None — cfo in the prior PIT year
        b2_capex_y0         float | None — capex (abs) in the most recent PIT year
        b2_capex_y1         float | None — capex (abs) in the prior PIT year
        b2_revenue_y0       float | None — revenue in the most recent PIT year
        b2_revenue_y1       float | None — revenue in the prior PIT year
        b2_note             str           — coverage / skip reason
    """
    _empty: dict[str, Any] = {
        "self_funded_at_t0": None,
        "b2_cfo_y0": None,
        "b2_cfo_y1": None,
        "b2_capex_y0": None,
        "b2_capex_y1": None,
        "b2_revenue_y0": None,
        "b2_revenue_y1": None,
        "b2_note": "unavailable",
    }

    if statements_df is None or statements_df.empty:
        return _empty

    required = {"ticker", "period_end", "cfo", "capex", "revenue"}
    if not required.issubset(set(statements_df.columns)):
        return _empty

    # Filter to this ticker
    ticker_mask = statements_df["ticker"].astype(str) == str(ticker)
    tk_rows = statements_df[ticker_mask].copy()
    if tk_rows.empty:
        return {**_empty, "b2_note": "no_rows_for_ticker"}

    # Parse period_end to Timestamp (PIT cutoff = period_end + 120d)
    try:
        tk_rows["_pe"] = pd.to_datetime(tk_rows["period_end"], errors="coerce")
    except Exception:  # noqa: BLE001
        return {**_empty, "b2_note": "period_end_parse_error"}

    tk_rows = tk_rows.dropna(subset=["_pe"])
    if tk_rows.empty:
        return {**_empty, "b2_note": "no_valid_period_end"}

    # PIT filter: period_end + B2_PIT_LAG_DAYS <= t0
    pit_cutoff = t0 - pd.Timedelta(days=B2_PIT_LAG_DAYS)
    pit_visible = tk_rows[tk_rows["_pe"] <= pit_cutoff].sort_values("_pe")
    if len(pit_visible) < 2:
        return {**_empty, "b2_note": "fewer_than_2_pit_years"}

    # Take the two most recent PIT-visible rows
    row_y0 = pit_visible.iloc[-1]  # most recent
    row_y1 = pit_visible.iloc[-2]  # prior year

    def _float_or_none(val: Any) -> float | None:
        try:
            v = float(val)
            return v if not (v != v) else None  # NaN check
        except (TypeError, ValueError):
            return None

    cfo_y0 = _float_or_none(row_y0.get("cfo"))
    cfo_y1 = _float_or_none(row_y1.get("cfo"))
    capex_y0 = _float_or_none(row_y0.get("capex"))
    capex_y1 = _float_or_none(row_y1.get("capex"))
    rev_y0 = _float_or_none(row_y0.get("revenue"))
    rev_y1 = _float_or_none(row_y1.get("revenue"))

    # Capex in statements.parquet is negative (cash outflow convention) or positive
    # depending on the source. We use abs() for the cfo>capex comparison so both
    # conventions work. Note this in b2_note.
    capex_y0_abs = abs(capex_y0) if capex_y0 is not None else None
    capex_y1_abs = abs(capex_y1) if capex_y1 is not None else None

    # self_funded_at_t0: both years have cfo > |capex| AND revenue is growing
    self_funded: bool | None = None
    if (
        cfo_y0 is not None and capex_y0_abs is not None
        and cfo_y1 is not None and capex_y1_abs is not None
        and rev_y0 is not None and rev_y1 is not None
    ):
        both_self_funded = (cfo_y0 > capex_y0_abs) and (cfo_y1 > capex_y1_abs)
        rev_growing = rev_y0 > rev_y1
        self_funded = bool(both_self_funded and rev_growing)
    elif cfo_y0 is None or capex_y0_abs is None or rev_y0 is None:
        # Missing data in the most recent year → null
        self_funded = None

    note = "annual_grain_only_capex_abs_convention"

    return {
        "self_funded_at_t0": self_funded,
        "b2_cfo_y0": cfo_y0,
        "b2_cfo_y1": cfo_y1,
        "b2_capex_y0": capex_y0,
        "b2_capex_y1": capex_y1,
        "b2_revenue_y0": rev_y0,
        "b2_revenue_y1": rev_y1,
        "b2_note": note,
    }


def extract_b4_index_provenance(
    ticker: str,
    t0: pd.Timestamp,
    index_changes_df: pd.DataFrame,
) -> dict[str, Any]:
    """B4 — Index provenance (addition/deletion) features.

    Source: data/sp_index_changes/changes.parquet (accruing since 2026-06-11).

    Two forward-only windows (relative to t0):
    - index_announce_within_63d_pre_t0:  bool | None
        An index ADDITION was announced within 63 calendar days BEFORE t0.
        announce_date in [t0 - 63d, t0).
    - index_announce_within_63d_post_t0: bool | None
        An index ADDITION was announced within 63 calendar days AFTER t0.
        announce_date in [t0, t0 + 63d].

    None when t0 predates the archive start (B4_ARCHIVE_START = 2026-06-11):
    almost all current episodes have t0 before the archive, so most rows will be None.

    b4_coverage: "full" | "pre_archive" | "unavailable"

    Parameters
    ----------
    ticker:
        Ticker string.
    t0:
        Episode onset date (pd.Timestamp).
    index_changes_df:
        sp_index_changes/changes.parquet DataFrame (ALL rows; we filter inside).
        Required columns: ticker, action, announce_date.

    Returns
    -------
    dict with keys:
        index_announce_within_63d_pre_t0   bool | None
        index_announce_within_63d_post_t0  bool | None
        b4_coverage                        str
    """
    _empty: dict[str, Any] = {
        "index_announce_within_63d_pre_t0": None,
        "index_announce_within_63d_post_t0": None,
        "b4_coverage": "unavailable",
    }

    if index_changes_df is None or index_changes_df.empty:
        return _empty

    required = {"ticker", "action", "announce_date"}
    if not required.issubset(set(index_changes_df.columns)):
        return _empty

    # Pre-archive: almost all episodes have t0 < B4_ARCHIVE_START
    if t0 < B4_ARCHIVE_START:
        return {
            "index_announce_within_63d_pre_t0": None,
            "index_announce_within_63d_post_t0": None,
            "b4_coverage": "pre_archive",
        }

    # Filter to this ticker and additions only
    ticker_mask = index_changes_df["ticker"].astype(str) == str(ticker)
    action_mask = index_changes_df["action"].astype(str).str.lower() == "addition"
    ev = index_changes_df[ticker_mask & action_mask].copy()

    if ev.empty:
        return {
            "index_announce_within_63d_pre_t0": False,
            "index_announce_within_63d_post_t0": False,
            "b4_coverage": "full",
        }

    try:
        ev["_ad"] = pd.to_datetime(ev["announce_date"], errors="coerce")
    except Exception:  # noqa: BLE001
        return {**_empty, "b4_coverage": "full"}

    ev = ev.dropna(subset=["_ad"])

    # Pre-t0 window: [t0 - 63d, t0)
    pre_start = t0 - pd.Timedelta(days=63)
    pre_mask = (ev["_ad"] >= pre_start) & (ev["_ad"] < t0)
    pre_match = bool(pre_mask.any())

    # Post-t0 window: [t0, t0 + 63d]
    post_end = t0 + pd.Timedelta(days=63)
    post_mask = (ev["_ad"] >= t0) & (ev["_ad"] <= post_end)
    post_match = bool(post_mask.any())

    return {
        "index_announce_within_63d_pre_t0": pre_match,
        "index_announce_within_63d_post_t0": post_match,
        "b4_coverage": "full",
    }


def _empty_b1() -> dict[str, Any]:
    return {
        "hard_event_count_126d": None,
        "soft_event_count_126d": None,
        "soft_then_hard": None,
        "days_soft_to_hard": None,
        "hard_event_reversed": None,
        "b1_coverage": "unavailable",
    }


def _empty_b2() -> dict[str, Any]:
    return {
        "self_funded_at_t0": None,
        "b2_cfo_y0": None,
        "b2_cfo_y1": None,
        "b2_capex_y0": None,
        "b2_capex_y1": None,
        "b2_revenue_y0": None,
        "b2_revenue_y1": None,
        "b2_note": "unavailable",
    }


def _empty_b4() -> dict[str, Any]:
    return {
        "index_announce_within_63d_pre_t0": None,
        "index_announce_within_63d_post_t0": None,
        "b4_coverage": "unavailable",
    }


# ---------------------------------------------------------------------------
# Case file parsing
# ---------------------------------------------------------------------------

def parse_case_file(path: str) -> dict[str, Any]:
    """Parse a winner_case.v1 case file and return the YAML dict.

    Extracts the single fenced ```yaml block from a Markdown file and parses it.
    Validates all required keys from _CASE_REQUIRED_KEYS.

    Parameters
    ----------
    path:
        Absolute or relative path to the .md file.

    Returns
    -------
    dict from yaml.safe_load of the fenced block.

    Raises
    ------
    ValueError:
        If no YAML block found, YAML fails to parse, schema is wrong, or a
        required key is missing.
    """
    import pathlib

    text = pathlib.Path(path).read_text(encoding="utf-8")

    # Find fenced ```yaml ... ``` block (first occurrence)
    pattern = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"parse_case_file: no fenced ```yaml block found in {path}")

    yaml_text = match.group(1)
    try:
        case = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"parse_case_file: YAML parse error in {path}: {exc}") from exc

    if not isinstance(case, dict):
        raise ValueError(f"parse_case_file: YAML block in {path} is not a mapping")

    # Validate schema
    if case.get("schema") != "winner_case.v1":
        raise ValueError(
            f"parse_case_file: expected schema 'winner_case.v1', got {case.get('schema')!r} in {path}"
        )

    # Validate required keys
    missing = [k for k in _CASE_REQUIRED_KEYS if k not in case]
    if missing:
        raise ValueError(
            f"parse_case_file: missing required keys {missing} in {path}"
        )

    return case


# ---------------------------------------------------------------------------
# Case reconciliation
# ---------------------------------------------------------------------------

def reconcile_case(
    case: dict[str, Any],
    episodes_df: pd.DataFrame,
) -> dict[str, Any]:
    """Find the mechanical episode for a case and return reconciliation result.

    Parameters
    ----------
    case:
        Parsed winner_case.v1 dict.
    episodes_df:
        DataFrame from detect_episodes (may be empty).

    Returns
    -------
    dict with keys:
        case_joined: bool
        engine_t0: str (ISO) | None
        reconcile: "matched" | "engine_no_onset" | "t0_gap_days:<N>"
            "matched" — episode t0 within 21 td of the hypothesis.
            "t0_gap_days:<N>" — closest episode found but gap > 21 td.
            "engine_no_onset" — no mechanical episode found for the ticker.
    """
    ticker = str(case["ticker"])
    t0_hyp_str = str(case.get("t0_hypothesis", ""))

    try:
        t0_hyp = pd.Timestamp(t0_hyp_str)
    except Exception:
        return {"case_joined": False, "engine_t0": None, "reconcile": "engine_no_onset"}

    if episodes_df is None or episodes_df.empty:
        return {"case_joined": False, "engine_t0": None, "reconcile": "engine_no_onset"}

    if "ticker" not in episodes_df.columns or "t0" not in episodes_df.columns:
        return {"case_joined": False, "engine_t0": None, "reconcile": "engine_no_onset"}

    ticker_eps = episodes_df[episodes_df["ticker"] == ticker]
    if ticker_eps.empty:
        return {"case_joined": False, "engine_t0": None, "reconcile": "engine_no_onset"}

    ticker_eps = ticker_eps.copy()
    ticker_eps["t0"] = pd.to_datetime(ticker_eps["t0"])

    # Find nearest episode to hypothesis
    diffs = (ticker_eps["t0"] - t0_hyp).abs()
    min_idx = diffs.idxmin()
    nearest_row = ticker_eps.loc[min_idx]
    nearest_t0 = pd.Timestamp(nearest_row["t0"])

    # Compute gap in calendar days (proxy for td)
    gap_cal = abs((nearest_t0 - t0_hyp).days)
    # Approximate 21 td as 29 calendar days
    matched = gap_cal <= 29

    if matched:
        return {
            "case_joined": True,
            "engine_t0": nearest_t0.date().isoformat(),
            "reconcile": "matched",
        }
    else:
        return {
            "case_joined": False,
            "engine_t0": nearest_t0.date().isoformat(),
            "reconcile": f"t0_gap_days:{gap_cal}",
        }
