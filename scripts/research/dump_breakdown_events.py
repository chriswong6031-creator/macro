"""L1 Short-Side — Phase-0 Breakdown Event Tape (BD-1 / BD-2 / BD-3).

Authority: research/short_side/BD_PHASE0_PREREG.md (FROZEN; thresholds/windows are
read from the prereg, not this file).  research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md §4.
research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md §6.

Outputs (RUL-P10 declared commit path):
  data/research/breakdown_events.parquet  — Mac-local; explicit .gitignore entry.
  data/research/breakdown_events_summary.json — git-committed vintage-stamped summary.

TrialLedger.log_declared_budget(3, family='short_side') is logged BEFORE the first
event-detection loop (3 = the three definitions; no threshold search).

Phase-0 is DESCRIPTIVE ONLY.  No chip, no synapse consumer, no site surface.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — follow the canonical pattern from scripts/replay_standout_pipeline.py.
# WORKTREE_ROOT is the repo root (works whether run from main checkout or any worktree).
# CANONICAL_DATA is hardcoded to the Mac-canonical data directory (same pattern).
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]  # WORKTREE_ROOT
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.grading import (  # noqa: E402
    fill_index,
    forward_metrics,
    terminal_state,
    terminal_state_short,
    TerminalState,
    TerminalStateShort,
    SHORT_FAVORABLE_MULT_21,
    SHORT_FAVORABLE_MULT_126,
    SHORT_ADVERSE_MULT,
    LIFTOFF_15,
    LIFTOFF_8,
    LIFTOFF_HORIZON_126,
    LIFTOFF_HORIZON_21,
)
from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.signal_quality import signal_frame  # noqa: E402

# split_adjust from scripts.replay_standout_pipeline (the canonical import per §3.2)
try:
    from scripts.replay_standout_pipeline import split_adjust, MASSIVE_DIR  # noqa: E402
except ImportError:
    from replay_standout_pipeline import split_adjust, MASSIVE_DIR  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ERA LAW window (pre-registered)
# ---------------------------------------------------------------------------
ERA_START = pd.Timestamp("2021-07-06")
ERA_PRIOR_BARS_REQUIRED = 252  # must have >= 252 bars of history before event date

# ---------------------------------------------------------------------------
# Liquidity floors (prereg §2)
# ---------------------------------------------------------------------------
LIQ_MIN_ADV_DOLLAR = 5_000_000  # 21d median dollar volume >= $5M
LIQ_MIN_PRICE = 3.0              # price >= $3

# ---------------------------------------------------------------------------
# BD-1 thresholds (prereg §3)
# ---------------------------------------------------------------------------
BD1_PIN_THRESHOLD = 0.03          # within 3.0% of rolling 63-bar max close
BD1_SWING_W = 5                   # ±5 bars for swing-high detection
BD1_SWING_LEN = 21                # 21-bar swing-high lookback
BD1_PIN_WINDOW = 63               # 63-bar rolling max for "pinned" check
BD1_AD_ZSCORE_FLOOR = 1.0         # ≥1σ below trailing-252-bar mean

# ---------------------------------------------------------------------------
# BD-2 thresholds (prereg §3)
# ---------------------------------------------------------------------------
BD2_STOP_LEVEL = 0.95             # state_8_21 == 'STOPPED': close <= 0.95 * entry
BD2_RALLY_WINDOW = 10             # within 10 bars after stop bar

# ---------------------------------------------------------------------------
# BD-3 thresholds (prereg §3)
# ---------------------------------------------------------------------------
BD3_EXTENDED_MULT = 1.15          # close >= 1.15 * rolling 126-bar min
BD3_DEF_BID_WINDOW = 21           # 21-bar total return for defensive-bid check

# ---------------------------------------------------------------------------
# Grading horizons (prereg §4)
# ---------------------------------------------------------------------------
GRADE_HORIZONS = (21, 63, 126)
SHORT_FAVORABLE_MULTS = {
    21:  SHORT_FAVORABLE_MULT_21,   # 0.92
    63:  SHORT_FAVORABLE_MULT_21,   # 0.92 — prereg specifies @21 and @126; use @21 for the middle
    126: SHORT_FAVORABLE_MULT_126,  # 0.85
}

# ---------------------------------------------------------------------------
# Episode collapse window (prereg §3)
# ---------------------------------------------------------------------------
EPISODE_COLLAPSE_BARS = 21

# ---------------------------------------------------------------------------
# Random control sampling (prereg §4)
# ---------------------------------------------------------------------------
CONTROL_RATIO = 3
CONTROL_RNG_SEED = 42

# ---------------------------------------------------------------------------
# Canonical data paths (hardcoded Mac-canonical, matching replay_standout_pipeline.py
# pattern — these scripts are Mac-local only, never run by CI runners).
# ---------------------------------------------------------------------------
CANONICAL_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
DATA_DIR      = CANONICAL_DATA
RESEARCH_DIR  = DATA_DIR / "research"
REPLAY_BOARDED = DATA_DIR / "replay" / "replay_boarded.parquet"
YAHOO_DIR = DATA_DIR / "yahoo"
EDGAR_DEAD_COV = DATA_DIR / "edgar" / "_dead_name_coverage.json"
OUT_PARQUET = RESEARCH_DIR / "breakdown_events.parquet"
OUT_SUMMARY = RESEARCH_DIR / "breakdown_events_summary.json"


# ===========================================================================
# 1. Universe construction (prereg §2)
# ===========================================================================

def _load_replay_tickers() -> set[str]:
    """Tickers appearing as fires in replay_boarded.parquet."""
    if not REPLAY_BOARDED.exists():
        log.warning("replay_boarded.parquet not found at %s", REPLAY_BOARDED)
        return set()
    df = pd.read_parquet(REPLAY_BOARDED, columns=["ticker"])
    return set(df["ticker"].astype(str).unique())


def _load_board_universe() -> set[str]:
    """Current US board universe from us_standouts.json (if available)."""
    us_standouts = DATA_DIR / "site" / "signals" / "us_standouts.json"
    tickers: set[str] = set()
    if not us_standouts.exists():
        # fallback: breadth constituents
        for cp in (DATA_DIR / "breadth" / "constituents.parquet",
                   DATA_DIR / "midcap_breadth" / "constituents.parquet"):
            if cp.exists():
                try:
                    df = pd.read_parquet(cp, columns=["ticker"])
                    tickers.update(df["ticker"].astype(str).unique())
                except Exception:
                    pass
        return tickers
    try:
        with open(us_standouts) as f:
            d = json.load(f)
        for key in ("buy", "watch", "laggards", "donor"):
            for row in (d.get(key) or []):
                t = row.get("ticker") if isinstance(row, dict) else row
                if isinstance(t, str) and t:
                    tickers.add(t)
    except Exception as e:
        log.warning("board universe load failed: %s", e)
    return tickers


def build_universe() -> set[str]:
    """Union of replay_boarded fire tickers and current board universe (prereg §2)."""
    uni = _load_replay_tickers() | _load_board_universe()
    log.info("universe: %d tickers (replay=%d board=%d)",
             len(uni), len(_load_replay_tickers()), len(_load_board_universe()))
    return uni


# ===========================================================================
# 2. Price loading helpers
# ===========================================================================

def _read_massive_ticker(ticker: str) -> pd.Series | None:
    """Load split-adjusted close for one ticker from massive_stock_day."""
    p = MASSIVE_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        c = df["close"].dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c.index = pd.to_datetime(c.index)
        c = c.sort_index()
        if len(c) < 2:
            return None
        return split_adjust(c)
    except Exception as e:
        log.debug("massive load failed for %s: %s", ticker, e)
        return None


def _read_massive_ohlcv(ticker: str) -> pd.DataFrame | None:
    """Load OHLCV from massive_stock_day (raw, not split-adjusted volumes/prices)."""
    p = MASSIVE_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as e:
        log.debug("massive OHLCV load failed for %s: %s", ticker, e)
        return None


def _liquidity_ok(close: pd.Series, raw_df: pd.DataFrame | None, event_idx: int) -> bool:
    """Check liquidity floor at event bar: 21d median dollar volume >= $5M, price >= $3."""
    price = float(close.iloc[event_idx])
    if price < LIQ_MIN_PRICE:
        return False
    if raw_df is None or "close" not in raw_df.columns or "volume" not in raw_df.columns:
        return True  # degrade gracefully; price floor already checked
    # 21d median dollar volume up to and including event bar
    start = max(0, event_idx - 20)
    sub_raw = raw_df.iloc[start: event_idx + 1]
    dv = sub_raw["close"] * sub_raw["volume"]
    return float(dv.median()) >= LIQ_MIN_DOLLAR_APPROX or float(dv.median()) >= LIQ_MIN_ADV_DOLLAR


# Use the simpler raw volume * raw close for dollar-volume; approximate since we use
# split-adjusted close but raw volume — ratio is directionally consistent for the floor.
LIQ_MIN_DOLLAR_APPROX = LIQ_MIN_ADV_DOLLAR


# ===========================================================================
# 3. BD-1: Distribution under a pinned tape
# ===========================================================================

def _compute_sign_volume(close: pd.Series, raw_df: pd.DataFrame) -> pd.Series | None:
    """per-bar sign_volume = volume × ((C−L)−(H−C))/(H−L); bars with H==L contribute 0."""
    if not {"high", "low", "volume"}.issubset(raw_df.columns):
        return None
    c = close.reindex(raw_df.index)
    h = raw_df["high"]
    lo = raw_df["low"]
    v = raw_df["volume"]
    hl_range = (h - lo).replace(0.0, np.nan)
    sv = v * ((c - lo) - (h - c)) / hl_range
    sv = sv.fillna(0.0)
    return sv.reindex(close.index).fillna(0.0)


def _swing_high_series(s: pd.Series, w: int = BD1_SWING_W) -> pd.Series:
    """Boolean Series: True on bars that are the local maximum over ±w bars."""
    arr = s.to_numpy()
    n = len(arr)
    is_swing = np.zeros(n, dtype=bool)
    for i in range(w, n - w):
        window = arr[i - w: i + w + 1]
        if arr[i] == window.max():
            is_swing[i] = True
    return pd.Series(is_swing, index=s.index)


def detect_bd1(ticker: str, close: pd.Series, raw_df: pd.DataFrame | None) -> list[pd.Timestamp]:
    """Detect BD-1 events: all three conditions first hold simultaneously.

    BD-1 — Distribution under a pinned tape (per-name S1-/S2- family):
      pinned       : close within 3% of rolling 63-bar max close
      lower_high   : most-recent 21-bar swing-high < prior 21-bar swing-high (within 63 bars)
      ad_deterioration: 21-bar sum of sign_volume >= 1σ below its trailing-252-bar mean

    Returns list of event bar Timestamps (first bar all three conditions hold).
    Episode collapse (21-bar window) applied separately in _collapse_episodes().
    """
    events: list[pd.Timestamp] = []

    # Need enough history: ERA_START + ERA_PRIOR_BARS_REQUIRED prior bars
    era_mask = close.index >= ERA_START
    if era_mask.sum() == 0:
        return events

    # Pinned: close within BD1_PIN_THRESHOLD of rolling 63-bar max
    roll_max_63 = close.rolling(BD1_PIN_WINDOW).max()
    pinned = (close >= roll_max_63 * (1.0 - BD1_PIN_THRESHOLD)) & close.notna() & roll_max_63.notna()

    # Swing-high series over close (using close as proxy if no H/L)
    sh = _swing_high_series(close, w=BD1_SWING_W)

    # AD deterioration: needs sign_volume
    sv = None
    if raw_df is not None:
        sv = _compute_sign_volume(close, raw_df)

    if sv is None:
        return events  # can't compute AD without H/L/V; BD-1 requires it

    sv_21 = sv.rolling(21).sum()
    sv_252_mean = sv_21.rolling(252).mean()
    sv_252_std  = sv_21.rolling(252).std()
    # ad_deterioration: rolling 21-bar sum >= 1σ below 252-bar mean
    ad_det = sv_21 <= (sv_252_mean - BD1_ZSCORE_FLOOR * sv_252_std)

    close_arr = close.to_numpy()
    idx = close.index

    # For each bar with ERA coverage + enough history, check all three
    fired_last_bar: int = -1
    for i, ts in enumerate(idx):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue
        if not bool(pinned.iloc[i]):
            continue
        if not bool(ad_det.iloc[i]):
            continue

        # lower_high check: within trailing 63 bars, most-recent 21-bar swing-high
        # is BELOW the prior 21-bar swing-high
        lo_i = max(0, i - BD1_PIN_WINDOW + 1)  # 63 bars lookback
        sh_sub = sh.iloc[lo_i: i + 1]
        sh_dates = sh_sub.index[sh_sub].tolist()
        if len(sh_dates) < 2:
            continue
        # recent = last two swing-highs within the 63-bar window
        recent_sh = sh_dates[-1]
        prior_sh  = sh_dates[-2]
        recent_val = float(close.loc[recent_sh])
        prior_val  = float(close.loc[prior_sh])
        if recent_val >= prior_val:
            continue  # NOT a lower high

        # Liquidity check
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue

        events.append(ts)

    return events


BD1_ZSCORE_FLOOR = BD1_AD_ZSCORE_FLOOR  # 1.0


def _liq_ok_at(close: pd.Series, raw_df: pd.DataFrame, event_idx: int) -> bool:
    """Simplified liquidity gate at event bar index."""
    price = float(close.iloc[event_idx])
    if price < LIQ_MIN_PRICE:
        return False
    if raw_df is None or "volume" not in raw_df.columns:
        return True
    start = max(0, event_idx - 20)
    # raw_df index aligns with close index since they're both from massive
    try:
        raw_sub = raw_df.iloc[start: event_idx + 1]
        dv = raw_sub["close"] * raw_sub["volume"]
        return float(dv.median()) >= LIQ_MIN_ADV_DOLLAR
    except Exception:
        return True


# ===========================================================================
# 4. BD-2: Failed reclaim after a stopped fire
# ===========================================================================

def _load_stopped_fires(ticker: str) -> list[dict]:
    """Load STOPPED state_8_21 rows from replay_boarded for this ticker."""
    if not REPLAY_BOARDED.exists():
        return []
    needed_cols = ["ticker", "signal_date", "entry_price", "state_8_21",
                   "fill_date", "stopped_at_8_21"]
    try:
        df = pd.read_parquet(REPLAY_BOARDED, columns=needed_cols)
        sub = df[(df["ticker"] == ticker) & (df["state_8_21"] == "STOPPED")]
        return sub.to_dict("records")
    except Exception as e:
        log.debug("replay_boarded load for %s failed: %s", ticker, e)
        return []


def detect_bd2(ticker: str, close: pd.Series, raw_df: pd.DataFrame | None) -> list[pd.Timestamp]:
    """Detect BD-2 events: failed reclaim after a STOPPED fire.

    BD-2 — Failed reclaim after a stopped fire (S6-):
      Source: replay_boarded fires with state_8_21 == 'STOPPED'.
      Within 10 bars after the stop bar (first bar where close <= 0.95 * entry):
        - a rally whose highest close remains BELOW the fire-day close
      Event fires on the first down-close after that failed-rally high (the failure bar).

    Returns list of event bar Timestamps (after episode collapse by caller).
    ERA LAW applies: only fires whose signal_date >= ERA_START with >= 252 prior bars.
    """
    events: list[pd.Timestamp] = []
    stopped_fires = _load_stopped_fires(ticker)
    if not stopped_fires:
        return events

    for row in stopped_fires:
        sig_date_str = str(row.get("signal_date", ""))
        entry_price  = row.get("entry_price")
        fill_date_str = str(row.get("fill_date", ""))
        stopped_at_offset = row.get("stopped_at_8_21")

        if not sig_date_str or entry_price is None or stopped_at_offset is None:
            continue

        try:
            sig_ts = pd.Timestamp(sig_date_str)
        except Exception:
            continue

        # ERA LAW: signal must be >= ERA_START with prior bar check
        if sig_ts < ERA_START:
            continue
        sig_loc = close.index.searchsorted(sig_ts)
        if sig_loc < ERA_PRIOR_BARS_REQUIRED:
            continue
        if sig_loc >= len(close.index):
            continue

        # Find fill bar (next bar after signal)
        fill_idx = fill_index(close, sig_ts)
        if fill_idx is None:
            continue

        # The stop bar is fill_idx + stopped_at_offset - 1
        # (stopped_at_8_21 is 1-indexed bars-from-fill)
        stop_offset = int(stopped_at_offset)
        stop_idx = fill_idx + stop_offset  # bar where close <= 0.95 * entry
        if stop_idx >= len(close):
            continue

        stop_ts = close.index[stop_idx]
        fire_close = float(close.iloc[fill_idx - 1]) if fill_idx > 0 else float(entry_price)
        # fire_close = close at the signal bar (the "fire-day close")
        # Use the signal bar close as the reference level
        fire_day_close = float(close.iloc[sig_loc])

        # Within BD2_RALLY_WINDOW bars after stop bar, find highest close
        rally_end_idx = min(stop_idx + BD2_RALLY_WINDOW, len(close) - 1)
        if rally_end_idx <= stop_idx:
            continue
        rally_slice = close.iloc[stop_idx + 1: rally_end_idx + 1]
        if rally_slice.empty:
            continue
        rally_high = float(rally_slice.max())
        rally_high_idx = rally_slice.idxmax()

        # Failed rally: highest close in the window remains BELOW fire-day close
        if rally_high >= fire_day_close:
            continue  # reclaim succeeded; not BD-2

        # Event fires on the first down-close after the rally high
        rally_high_loc = close.index.searchsorted(rally_high_idx)
        for j in range(rally_high_loc + 1, rally_end_idx + 2):
            if j >= len(close):
                break
            if close.iloc[j] < close.iloc[j - 1]:  # down-close
                event_ts = close.index[j]
                # ERA check and liquidity
                if event_ts < ERA_START:
                    break
                if raw_df is not None and not _liq_ok_at(close, raw_df,
                                                          close.index.searchsorted(event_ts)):
                    break
                events.append(event_ts)
                break

    return events


# ===========================================================================
# 5. BD-3: Tail-flag breach with defensive bid
# ===========================================================================

_ETF_CLOSES: dict[str, pd.Series] = {}


def _load_etf_close(ticker: str) -> pd.Series | None:
    """Load yahoo adjusted close for an ETF (XLP/XLU/XLV/SPY)."""
    if ticker in _ETF_CLOSES:
        return _ETF_CLOSES[ticker]
    p = YAHOO_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        c = df["close"].dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c.index = pd.to_datetime(c.index)
        c = c.sort_index()
        _ETF_CLOSES[ticker] = c
        return c
    except Exception:
        return None


def _defensive_bid_on(date: pd.Timestamp) -> bool | None:
    """mean({XLP,XLU,XLV}) 21-bar total return minus SPY 21-bar return > 0 on event date."""
    def_etfs = ["XLP", "XLU", "XLV"]
    spy = _load_etf_close("SPY")
    if spy is None:
        return None

    def _21d_return(series: pd.Series, asof: pd.Timestamp) -> float | None:
        loc = series.index.searchsorted(asof, side="right") - 1
        if loc < 21:
            return None
        p_now  = float(series.iloc[loc])
        p_prev = float(series.iloc[loc - 21])
        if p_prev <= 0 or not np.isfinite(p_prev) or not np.isfinite(p_now):
            return None
        return p_now / p_prev - 1.0

    spy_ret = _21d_return(spy, date)
    if spy_ret is None:
        return None

    def_rets = []
    for etf in def_etfs:
        c = _load_etf_close(etf)
        if c is None:
            continue
        r = _21d_return(c, date)
        if r is not None:
            def_rets.append(r)
    if len(def_rets) < 2:  # need at least 2 of 3
        return None

    return (np.mean(def_rets) - spy_ret) > 0.0


def detect_bd3(ticker: str, close: pd.Series, raw_df: pd.DataFrame | None) -> list[pd.Timestamp]:
    """Detect BD-3 events: tail-flag breach + extended + defensive bid.

    BD-3 — Tail-flag breach with defensive bid (S4--adjacent arming):
      ema8_breach   : fresh breach per canonical engine/signal_quality (3B resample, span=8,
                      fresh_breach mask) — imported, never re-implemented
      extended      : close >= 1.15 * rolling 126-bar min close
      defensive_bid : mean({XLP,XLU,XLV}) 21-bar return > SPY 21-bar return on event day

    Returns list of event bar Timestamps.
    """
    events: list[pd.Timestamp] = []

    # ERA LAW
    era_mask = close.index >= ERA_START
    if era_mask.sum() == 0:
        return events

    # Compute ema8 fresh_breach via signal_quality.signal_frame (3B resample; span=8)
    # signal_frame returns a 3B-resampled DataFrame; we reindex back to daily index
    try:
        sf = signal_frame(close)
    except Exception as e:
        log.debug("BD-3 signal_frame failed for %s: %s", ticker, e)
        return events
    if sf.empty:
        return events

    # fresh_breach in the 3B frame; we need to propagate to daily for event-bar lookup
    # The 3B index is the LAST day of each 3-business-day bucket
    trail_3b = sf["ema_trail"]
    close_3b  = sf["close"]
    below_3b  = close_3b < trail_3b
    prev_below = below_3b.shift(1, fill_value=False)
    rising_into = (trail_3b.shift(1) > trail_3b.shift(3))
    fresh_breach_3b = (below_3b & ~prev_below & rising_into).fillna(False)

    # Map breach 3B bars back to daily close dates by reindexing
    # (the 3B bar's date is the LAST trading day in its bucket)
    # We mark the daily bar that IS the 3B-bar-end date as a breach date
    breach_dates: set[pd.Timestamp] = set(fresh_breach_3b.index[fresh_breach_3b])

    # Extended: close >= 1.15 * rolling 126-bar min
    roll_min_126 = close.rolling(126).min()
    extended = close >= roll_min_126 * BD3_EXTENDED_MULT

    fired_as_ep: int = -1  # last event index for intra-ticker loop
    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue
        if ts not in breach_dates:
            continue
        if not bool(extended.iloc[i]):
            continue

        # Defensive bid
        def_bid = _defensive_bid_on(ts)
        if def_bid is None or not def_bid:
            continue

        # Liquidity
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue

        events.append(ts)

    return events


# ===========================================================================
# 6. Episode collapse (prereg §3)
# ===========================================================================

def _collapse_episodes(events: list[pd.Timestamp],
                        close: pd.Series) -> list[pd.Timestamp]:
    """Within a ticker × definition, events within EPISODE_COLLAPSE_BARS of a prior
    event collapse into that episode (first event wins)."""
    if not events:
        return []
    sorted_events = sorted(set(events))
    collapsed: list[pd.Timestamp] = [sorted_events[0]]
    for ts in sorted_events[1:]:
        last = collapsed[-1]
        # count trading bars between last and ts
        last_loc = close.index.searchsorted(last)
        ts_loc   = close.index.searchsorted(ts)
        if ts_loc - last_loc <= EPISODE_COLLAPSE_BARS:
            continue  # collapse into prior episode
        collapsed.append(ts)
    return collapsed


# ===========================================================================
# 7. Grading (prereg §4): paired two-sided (long + short) + forward excursions
# ===========================================================================

def _grade_event(
    ticker: str,
    event_ts: pd.Timestamp,
    close: pd.Series,
    definition: str,
) -> dict[str, Any]:
    """Grade one event with both long-side and short-side terminal states + forward metrics."""
    row: dict[str, Any] = {
        "ticker":     ticker,
        "definition": definition,
        "event_date": str(event_ts.date()),
        "censored":   False,
    }

    # Fill date = next-bar close
    fi = fill_index(close, event_ts)
    if fi is None:
        row["censored"] = True
        return row

    row["fill_date"] = str(close.index[fi].date())
    row["entry_price"] = float(close.iloc[fi])

    # Long-side terminal states @ both named parameterizations
    for lm, lh, pname in (
        (LIFTOFF_15, LIFTOFF_HORIZON_126, "clean15_126"),
        (LIFTOFF_8,  LIFTOFF_HORIZON_21,  "clean8_21"),
    ):
        ts_long = terminal_state(close, event_ts, liftoff_mult=lm, liftoff_horizon=lh)
        row[f"long_state_{pname}"]  = ts_long["state"]
        row[f"long_stopped_{pname}"] = ts_long["stopped_at_bar"]
        row[f"long_liftoff_{pname}"] = ts_long["liftoff_at_bar"]

    # Short-side terminal states @ two horizons (21 and 126)
    for sh_horiz, sh_fav_mult, sh_label in (
        (21,  SHORT_FAVORABLE_MULT_21,  "short21"),
        (126, SHORT_FAVORABLE_MULT_126, "short126"),
    ):
        ts_short = terminal_state_short(
            close, event_ts,
            adverse_mult=SHORT_ADVERSE_MULT,
            favorable_mult=sh_fav_mult,
            horizon=sh_horiz,
        )
        row[f"short_state_{sh_label}"]         = ts_short["state"]
        row[f"short_adverse_bar_{sh_label}"]   = ts_short["adverse_at_bar"]
        row[f"short_favorable_bar_{sh_label}"] = ts_short["favorable_at_bar"]

    # Forward metrics (excursions) at all GRADE_HORIZONS
    fm = forward_metrics(close, event_ts, horizons=GRADE_HORIZONS)
    for h in GRADE_HORIZONS:
        row[f"fwd_ret_{h}"]  = fm.get(f"fwd_ret_{h}")
        row[f"fwd_mdd_{h}"]  = fm.get(f"fwd_mdd_{h}")
        row[f"fwd_mfe_{h}"]  = fm.get(f"fwd_mfe_{h}")

    # Censoring: if any horizon is None we mark it but keep the row
    if any(row.get(f"fwd_ret_{h}") is None for h in GRADE_HORIZONS):
        row["censored"] = True

    return row


# ===========================================================================
# 8. Control sampling (prereg §4): matched random-bar controls 3:1
# ===========================================================================

def _sample_controls(
    ticker: str,
    close: pd.Series,
    raw_df: pd.DataFrame | None,
    n_events: int,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Sample n_events * CONTROL_RATIO random bars passing liquidity floor from the ERA window."""
    era_close = close[close.index >= ERA_START]
    if len(era_close) < ERA_PRIOR_BARS_REQUIRED:
        return []

    # Eligible bars: within ERA window, enough prior history, pass liquidity
    eligible_idx = []
    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue
        eligible_idx.append(i)

    if not eligible_idx:
        return []

    n_needed = n_events * CONTROL_RATIO
    chosen = rng.choice(eligible_idx,
                        size=min(n_needed, len(eligible_idx)),
                        replace=False)

    rows = []
    for i in chosen:
        ts = close.index[i]
        r = _grade_event(ticker, ts, close, definition="CONTROL")
        r["is_control"] = True
        rows.append(r)
    return rows


# ===========================================================================
# 9. Per-ticker processing (resumable)
# ===========================================================================

def process_ticker(
    ticker: str,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Process one ticker: detect all BD-1/BD-2/BD-3 events, grade, add controls."""
    close = _read_massive_ticker(ticker)
    if close is None or len(close) < ERA_PRIOR_BARS_REQUIRED:
        return []

    raw_df = _read_massive_ohlcv(ticker)

    all_events_by_def: dict[str, list[pd.Timestamp]] = {}

    # BD-1
    try:
        bd1_raw = detect_bd1(ticker, close, raw_df)
        all_events_by_def["BD-1"] = _collapse_episodes(bd1_raw, close)
    except Exception as e:
        log.debug("BD-1 failed for %s: %s", ticker, e)
        all_events_by_def["BD-1"] = []

    # BD-2
    try:
        bd2_raw = detect_bd2(ticker, close, raw_df)
        all_events_by_def["BD-2"] = _collapse_episodes(bd2_raw, close)
    except Exception as e:
        log.debug("BD-2 failed for %s: %s", ticker, e)
        all_events_by_def["BD-2"] = []

    # BD-3
    try:
        bd3_raw = detect_bd3(ticker, close, raw_df)
        all_events_by_def["BD-3"] = _collapse_episodes(bd3_raw, close)
    except Exception as e:
        log.debug("BD-3 failed for %s: %s", ticker, e)
        all_events_by_def["BD-3"] = []

    # Build event rows
    rows: list[dict[str, Any]] = []
    total_events = 0
    for defn, event_list in all_events_by_def.items():
        for ev_ts in event_list:
            r = _grade_event(ticker, ev_ts, close, definition=defn)
            r["is_control"] = False
            rows.append(r)
            total_events += 1

    if total_events == 0:
        return rows  # no events, no controls needed

    # Matched controls: 3:1 vs total events across all definitions
    ctrl_rows = _sample_controls(ticker, close, raw_df, total_events, rng)
    rows.extend(ctrl_rows)

    return rows


# ===========================================================================
# 10. Cross-definition overlap matrix (prereg §3)
# ===========================================================================

def _overlap_matrix(events_df: pd.DataFrame) -> dict[str, Any]:
    """Compute the cross-definition overlap matrix (events only, not controls)."""
    ev = events_df[~events_df.get("is_control", pd.Series(False, index=events_df.index))]
    defs = ["BD-1", "BD-2", "BD-3"]
    matrix: dict[str, Any] = {}
    for d1 in defs:
        d1_tickers = set(
            ev[ev["definition"] == d1][["ticker", "event_date"]]
            .apply(lambda r: f"{r.ticker}|{r.event_date}", axis=1)
        )
        matrix[d1] = {}
        for d2 in defs:
            d2_tickers = set(
                ev[ev["definition"] == d2][["ticker", "event_date"]]
                .apply(lambda r: f"{r.ticker}|{r.event_date}", axis=1)
            )
            matrix[d1][d2] = len(d1_tickers & d2_tickers)
    return matrix


# ===========================================================================
# 11. Vintage stamp (inline — engine/vintage_stamp.py absent on this branch)
# TODO: replace with engine.vintage_stamp.vintage_stamp() once PR-1 lands.
# ===========================================================================

def _make_vintage_stamp(n_universe: int) -> dict[str, Any]:
    """8-field vintage stamp per RUL-P4 / program §3.4."""
    dead_name_coverage_pct: float | None = None
    stamp_degraded = False
    try:
        if EDGAR_DEAD_COV.exists():
            cov = json.loads(EDGAR_DEAD_COV.read_text())
            dead_name_coverage_pct = float(cov.get("coverage_frac", 0.0)) * 100.0
    except Exception:
        stamp_degraded = True

    return {
        "price_plane_id":         "massive_stock_day_v2",
        "adjustment_mode":        "split_adjust_price_only",
        "universe_as_of":         pd.Timestamp.utcnow().date().isoformat(),
        "frame":                  "era_law_2021-07-06_plus",
        "survivorship_biased":    True,
        "survivorship_note": (
            "Universe = replay_boarded fire tickers UNION board universe. "
            "Names delisted before ever firing are absent; ERA-LAW window (2021+, "
            "massive plane) bounds the bias for within-window events."
        ),
        "coverage_frac":          round(1.0, 4),
        "dead_name_coverage_pct": dead_name_coverage_pct,
        "era_law_cohort":         "2021-07-06_to_present",
        "n_universe":             n_universe,
        "stamp_degraded":         stamp_degraded,
        "generated_utc":          pd.Timestamp.utcnow().isoformat(),
    }


# ===========================================================================
# 12. Summary statistics (§6 table)
# ===========================================================================

def _base_rates(sub: pd.DataFrame, col: str, target_val: str) -> float | None:
    valid = sub[col].notna()
    if valid.sum() == 0:
        return None
    return round(float((sub.loc[valid, col] == target_val).mean() * 100), 2)


def build_summary(events_df: pd.DataFrame, stamp: dict) -> dict[str, Any]:
    """Build the §6 table and return as a dict for JSON output."""
    ev   = events_df[~events_df.get("is_control", pd.Series(False, index=events_df.index))]
    ctrl = events_df[events_df.get("is_control", pd.Series(False, index=events_df.index))]

    per_def: dict[str, Any] = {}
    for defn in ["BD-1", "BD-2", "BD-3"]:
        ev_d   = ev[ev["definition"] == defn]
        ctrl_d = ctrl[ctrl["definition"] == "CONTROL"]

        n_episodes = len(ev_d)

        # Per-year counts
        if "event_date" in ev_d.columns and n_episodes > 0:
            ev_d = ev_d.copy()
            ev_d["year"] = pd.to_datetime(ev_d["event_date"]).dt.year
            per_year = ev_d.groupby("year").size().to_dict()
        else:
            per_year = {}

        # Long-side terminal state rates
        long_states: dict[str, Any] = {}
        for pname in ("clean15_126", "clean8_21"):
            col = f"long_state_{pname}"
            if col in ev_d.columns:
                long_states[pname] = {
                    "stop_rate_pct":    _base_rates(ev_d, col, TerminalState.STOPPED),
                    "liftoff_rate_pct": _base_rates(ev_d, col, TerminalState.CLEAN_LIFTOFF),
                    "cushion_rate_pct": _base_rates(ev_d, col, TerminalState.CUSHIONED),
                    "dead_rate_pct":    _base_rates(ev_d, col, TerminalState.DEAD_MONEY),
                    "n_matured":        int(ev_d[col].notna().sum()),
                }

        # Short-side terminal state rates
        short_states: dict[str, Any] = {}
        for sh_label in ("short21", "short126"):
            col = f"short_state_{sh_label}"
            if col in ev_d.columns:
                short_states[sh_label] = {
                    "adverse_rate_pct":   _base_rates(ev_d, col, TerminalStateShort.ADVERSE_TRIGGERED),
                    "favorable_rate_pct": _base_rates(ev_d, col, TerminalStateShort.FAVORABLE_TRIGGERED),
                    "unremarkable_rate_pct": _base_rates(ev_d, col, TerminalStateShort.UNREMARKABLE),
                    "n_matured":          int(ev_d[col].notna().sum()),
                }

        # Control baseline
        ctrl_long_states: dict[str, Any] = {}
        for pname in ("clean15_126", "clean8_21"):
            col = f"long_state_{pname}"
            if col in ctrl_d.columns and len(ctrl_d) > 0:
                ctrl_long_states[pname] = {
                    "stop_rate_pct":    _base_rates(ctrl_d, col, TerminalState.STOPPED),
                    "liftoff_rate_pct": _base_rates(ctrl_d, col, TerminalState.CLEAN_LIFTOFF),
                    "n":                int(ctrl_d[col].notna().sum()),
                }

        # Paired asymmetry: simple delta (events - control) on stop rate
        # Full bootstrap CI is Phase-1 work; Phase-0 prints point estimates only.
        asym: dict[str, Any] = {}
        for pname in ("clean15_126", "clean8_21"):
            ev_stop  = long_states.get(pname, {}).get("stop_rate_pct")
            ctrl_stop = ctrl_long_states.get(pname, {}).get("stop_rate_pct")
            if ev_stop is not None and ctrl_stop is not None:
                asym[pname] = {
                    "stop_rate_delta_pp": round(ev_stop - ctrl_stop, 2),
                    "note": (
                        "point estimate only (Phase-0); "
                        "episode-clustered bootstrap CI is Phase-1 work"
                    ),
                }

        per_def[defn] = {
            "n_episodes":    n_episodes,
            "per_year":      per_year,
            "long_states":   long_states,
            "short_states":  short_states,
            "control_baseline_long": ctrl_long_states,
            "paired_asymmetry_delta": asym,
            "powering_note": (
                "< 100 episodes: parked as underpowered per prereg §6"
                if n_episodes < 100 else ""
            ),
        }

    # Overlap matrix
    overlap = _overlap_matrix(events_df)

    # Total events
    total_events = sum(d.get("n_episodes", 0) for d in per_def.values())
    total_controls = int(ctrl["definition"].notna().sum()) if len(ctrl) > 0 else 0

    return {
        "schema":          "breakdown_events_summary.v1",
        "vintage":         stamp,
        "trial_family":    "short_side",
        "declared_budget": 3,
        "per_definition":  per_def,
        "overlap_matrix":  overlap,
        "total_events":    total_events,
        "total_controls":  total_controls,
        "phase":           "phase0_descriptive_only",
        "note": (
            "Phase-0 is DESCRIPTIVE. No chip, no synapse consumer, no site surface, "
            "no promotion criteria applied. Nulls printed, not hidden. "
            "Survivorship_biased=True: names delisted before ERA window may be absent."
        ),
    }


# ===========================================================================
# 13. Main runner
# ===========================================================================

def main(args=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Dump BD Phase-0 breakdown event tape"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Process first 10 tickers only (no writes)")
    parser.add_argument("--ticker", help="Process a single ticker only")
    parser.add_argument("--resume", action="store_true",
                        help="Skip tickers already present in the output parquet")
    parser.add_argument("--verbose", "-v", action="store_true")
    parsed = parser.parse_args(args)

    logging.basicConfig(
        level=logging.DEBUG if parsed.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # TRIAL LEDGER: log declared budget BEFORE running (prereg §1)
    ledger_path = DATA_DIR / "trial_ledger.jsonl"
    led = TrialLedger(path=ledger_path)
    led.log_declared_budget(
        3,
        family="short_side",
        reason="BD Phase-0: 3 definitions (BD-1 distribution-pinned, BD-2 failed-reclaim, BD-3 tail-flag); no threshold search",
    )
    log.info("TrialLedger: declared_budget=3 family='short_side' logged")

    # Build universe
    if parsed.ticker:
        universe = {parsed.ticker}
    else:
        universe = build_universe()

    if parsed.dry_run:
        universe = set(list(sorted(universe))[:10])
        log.info("DRY RUN: processing %d tickers only", len(universe))

    # Resumability: load already-processed tickers from existing parquet
    done_tickers: set[str] = set()
    if parsed.resume and OUT_PARQUET.exists():
        try:
            prev = pd.read_parquet(OUT_PARQUET, columns=["ticker"])
            done_tickers = set(prev["ticker"].unique())
            log.info("Resume: %d tickers already processed", len(done_tickers))
        except Exception:
            pass

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(CONTROL_RNG_SEED)
    all_rows: list[dict[str, Any]] = []

    # Load existing rows if resuming
    if parsed.resume and done_tickers and OUT_PARQUET.exists():
        try:
            prev_df = pd.read_parquet(OUT_PARQUET)
            all_rows = prev_df.to_dict("records")
        except Exception:
            all_rows = []

    tickers_to_process = sorted(universe - done_tickers)
    n = len(tickers_to_process)
    t0 = time.time()

    for i, ticker in enumerate(tickers_to_process, 1):
        if i % 100 == 0 or i == 1:
            elapsed = time.time() - t0
            rate = elapsed / i
            log.info("Progress: %d/%d tickers (%.1fs elapsed, ~%.1fs/ticker)",
                     i, n, elapsed, rate)
        try:
            rows = process_ticker(ticker, rng)
            all_rows.extend(rows)
        except Exception as e:
            log.warning("process_ticker(%s) failed: %s", ticker, e)

    elapsed_total = time.time() - t0
    log.info("Processing complete: %.1fs total, %d rows", elapsed_total, len(all_rows))

    if not all_rows:
        log.warning("No events found; writing empty parquet + summary")

    # Write parquet
    if not parsed.dry_run:
        df = pd.DataFrame(all_rows)
        if len(df) == 0:
            df = pd.DataFrame(columns=["ticker", "definition", "event_date",
                                        "is_control", "censored"])
        df.to_parquet(OUT_PARQUET, index=False)
        log.info("Wrote %s (%d rows)", OUT_PARQUET, len(df))

        # Build summary
        stamp = _make_vintage_stamp(len(universe))
        summary = build_summary(df, stamp)
        summary["runtime_seconds"] = round(elapsed_total, 1)
        summary["n_tickers_processed"] = len(universe)

        OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
        log.info("Wrote %s", OUT_SUMMARY)

        # Print the §6 table to stdout
        print("\n=== BD Phase-0 Summary Table ===")
        for defn, d in summary["per_definition"].items():
            n_ep = d["n_episodes"]
            print(f"\n{defn}: {n_ep} episodes")
            print(f"  per_year: {d['per_year']}")
            for pname, ls in d.get("long_states", {}).items():
                print(f"  long[{pname}]: stop={ls.get('stop_rate_pct')}% "
                      f"liftoff={ls.get('liftoff_rate_pct')}% n_matured={ls.get('n_matured')}")
            for sh_label, ss in d.get("short_states", {}).items():
                print(f"  short[{sh_label}]: adverse={ss.get('adverse_rate_pct')}% "
                      f"favorable={ss.get('favorable_rate_pct')}% "
                      f"n_matured={ss.get('n_matured')}")
            for pname, asym in d.get("paired_asymmetry_delta", {}).items():
                print(f"  asym_delta[{pname}]: stop_delta={asym.get('stop_rate_delta_pp')}pp")
            if d.get("powering_note"):
                print(f"  NOTE: {d['powering_note']}")
        print(f"\nOverlap matrix: {summary['overlap_matrix']}")
        print(f"Total events: {summary['total_events']}, controls: {summary['total_controls']}")
        print(f"Runtime: {elapsed_total:.1f}s")
    else:
        log.info("DRY RUN: no files written (found %d rows from %d tickers)",
                 len(all_rows), len(tickers_to_process))
        # Still print event counts for dry-run inspection
        ev = [r for r in all_rows if not r.get("is_control")]
        from collections import Counter
        cnt = Counter(r.get("definition") for r in ev)
        print("Dry-run event counts by definition:", dict(cnt))


if __name__ == "__main__":
    main()
