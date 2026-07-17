"""L1 Short-Side — Phase-0/0b Breakdown Event Tape (BD-1 / BD-2 / BD-3 / BD-4 / BD-5 / BD-6).

Authority:
  Phase-0  (BD-1/2/3): research/short_side/BD_PHASE0_PREREG.md  (FROZEN)
  Phase-0b (BD-4/5/6): research/short_side/BD_PHASE0B_PREREG.md (FROZEN)
  Governing: research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md §5.4, RUL-U4, RUL-U3a.
  research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md §4.
  research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md §6.

Outputs (RUL-P10 declared commit path):
  data/research/breakdown_events.parquet  — Mac-local; explicit .gitignore entry.
  data/research/breakdown_events_summary.json — git-committed vintage-stamped summary (v3).

Budget (RUL-U3a — max() floor semantics):
  Phase-0  TrialLedger.log_declared_budget(3, family='short_side') — Phase-0 run (first time).
  Phase-0b TrialLedger.log_declared_budget(3, family='short_side') — this run (max()-basis).
  Both budgets are logged BEFORE the first event-detection loop.
  Outputs print: (a) family literal_n (cumulative distinct configs), (b) max()-basis
  divergence note explaining that declared_budget=3 is per-study BH floor, not a sum.
  Each definition is also logged as a distinct config via log_trial() so literal_n accumulates.

derived_from_surface: bd_phase0_tape (Phase-0b contamination stamp per BD_PHASE0B_PREREG §0).

Phase-0/0b is DESCRIPTIVE ONLY.  No chip, no synapse consumer, no site surface.

Seeding contract (CRITICAL):
  - BD-1/2/3 controls: drawn from the SINGLE global rng=np.random.default_rng(42) passed
    per-ticker in process_ticker(), using ONLY the BD-1/2/3 event pool — identical to a
    Phase-0-only run for the same ticker (same pool, same order, same rng state).
    BD-4/5/6 events do NOT enter this pool.  BD-1/2/3 event rows AND their control draws
    are byte-identical to any Phase-0-only run.
  - BD-4/5/6 controls: each definition uses its OWN declared per-definition seed constant
    (BD4=7891, BD5=13421, BD6=19937), XOR-ed with a ticker hash for per-ticker variation.
    This is a SEPARATE RNG pass that does not advance the global rng state.
  - PRACTICAL CONSEQUENCE: Phase-0 (BD-1/2/3) rows in the output parquet are byte-identical
    to a hypothetical Phase-0-only run — the seeding contract is preserved exactly.
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
from engine.signal_quality import fresh_breach_mask  # noqa: E402

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
# BD-4 thresholds (prereg §1 — S4- Two-Clock Rollover)
# ---------------------------------------------------------------------------
BD4_POS_SHORT_WINDOW  = 63        # pos63: position in 63-bar range
BD4_POS_LONG_WINDOW   = 252       # pos252: position in 252-bar range
BD4_EMA_SHORT_SPAN    = 5         # EMA5 of pos63 → daily_osc
BD4_EMA_LONG_SPAN     = 21        # EMA21 of pos252 → weekly_osc
BD4_ROLLOVER_WINDOW   = 15        # trailing 15 bars for rollover peak
BD4_ROLLOVER_DROP     = 15.0      # osc ≤ peak − 15
BD4_TREND_LOOKBACK    = 5         # (osc_t − osc_{t−5}) < 0 for direction
BD4_EXTENDED_MULT     = 0.88      # close >= 0.88 * rolling 252-bar max
BD4_WARMUP_BARS       = 273       # ≥273 prior bars required (252 pos + EMA21 burn-in)

# ---------------------------------------------------------------------------
# BD-5 thresholds (prereg §2 — S5- Coiled Breakdown)
# ---------------------------------------------------------------------------
BD5_COIL_WINDOW       = 21        # 21-bar range for coil_ratio
BD5_COIL_PCT_WINDOW   = 252       # trailing 252 bars to compute coil percentile
BD5_COIL_PCT_THRESHOLD = 20       # coil_ratio ≤ 20th pctile of its own 252-bar history
BD5_DIST_SUM_WINDOW   = 21        # 21-bar sum of sign_volume
BD5_DIST_ROLL_WINDOW  = 252       # rolling-252 std of the 21-bar-sum series (BD-1 convention)
BD5_DIST_SIGMA        = -0.5      # ≤ −0.5σ below trailing-252-bar mean of the 21-bar-sum
BD5_BREAKDOWN_WINDOW  = 21        # breakdown: close < min(C, trailing 21 bars ending t-1)

# ---------------------------------------------------------------------------
# BD-6 thresholds (prereg §3 — S13- Within-Sector Leader Fade)
# ---------------------------------------------------------------------------
BD6_LEADER_WINDOW     = 126       # 126-bar trailing return for "leader" decile
BD6_FADE_WINDOW       = 21        # rel21 = ticker 21-bar return − sector median
BD6_FADE_STD_WINDOW   = 252       # trailing 252 bars for std(rel21)
BD6_FADE_SIGMA        = -1.0      # rel21 ≤ −1.0 × std(rel21, 252)
BD6_NEAR_HIGHS_MULT   = 0.85      # close ≥ 0.85 × rolling 126-bar max
BD6_MIN_SECTOR_MEMBERS = 8        # sectors with <8 covered members skipped per bar

# ---------------------------------------------------------------------------
# BD-4/5/6 control RNG seeds (independent of the BD-1/2/3 global seed=42)
# ---------------------------------------------------------------------------
BD4_CONTROL_RNG_SEED  = 7891      # chosen to not collide with 42 or 12345
BD5_CONTROL_RNG_SEED  = 13421     # "
BD6_CONTROL_RNG_SEED  = 19937     # "

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
# ticker_sectors.parquet is a GIT-TRACKED artifact (12,980 bytes, committed on this branch).
# It resolves relative to the repo root (_ROOT), NOT the Mac-canonical heavy-data directory
# (CANONICAL_DATA/DATA_DIR), where it is absent.  The --data-root override path applies only
# to Mac-local heavy stores (massive plane, replay); git-tracked artifacts use _ROOT.
TICKER_SECTORS_PATH = _ROOT / "data" / "breadth" / "ticker_sectors.parquet"


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


# ADV note: dollar-volume uses raw_df["close"] * raw_df["volume"] (split-adjusted close ×
# raw volume — approximate since volume is not split-adjusted, but the ratio is
# directionally consistent for the $5M floor check).


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
        # fire_day_close = close at the signal bar (the reference level for failed-reclaim)
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
            return None  # require all 3 ETFs present; partial defensive-bid is undefined
        r = _21d_return(c, date)
        if r is None:
            return None  # require all 3 ETF returns computable
        def_rets.append(r)
    # All 3 required; if any were missing we already returned None above
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

    # Compute ema8 fresh_breach via the canonical fresh_breach_mask() helper in
    # engine.signal_quality (single source of truth: 3B resample, span=8, fresh_breach mask).
    try:
        fresh_breach_3b = fresh_breach_mask(close)
    except Exception as e:
        log.debug("BD-3 fresh_breach_mask failed for %s: %s", ticker, e)
        return events
    if fresh_breach_3b.empty:
        return events

    # Map 3B breach dates back to daily close dates: the 3B bar date is the LAST
    # trading day of that bucket, so we collect those dates directly as a set.
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
# 5b. BD-4: Two-Clock Rollover (Phase-0b prereg §1)
# ===========================================================================

def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average with adjust=False (standard convention)."""
    return series.ewm(span=span, adjust=False).mean()


def _rollover_mask(osc: pd.Series, window: int = BD4_ROLLOVER_WINDOW,
                   drop: float = BD4_ROLLOVER_DROP,
                   trend_lb: int = BD4_TREND_LOOKBACK) -> pd.Series:
    """Boolean mask: rollover(osc) per prereg §1.
    Conditions (all must hold at bar t):
      - max(osc, trailing 15 bars) >= 80
      - osc_t <= that peak - 15
      - (osc_t - osc_{t-5}) < 0  (downward trend over 5 bars)
    """
    roll_peak = osc.rolling(window).max()
    cond_peak_high = roll_peak >= 80.0
    cond_below_peak = osc <= (roll_peak - drop)
    cond_trending_down = (osc - osc.shift(trend_lb)) < 0.0
    return cond_peak_high & cond_below_peak & cond_trending_down


def detect_bd4(ticker: str, close: pd.Series, raw_df: pd.DataFrame | None) -> list[pd.Timestamp]:
    """Detect BD-4 events: Two-Clock Rollover (S4- family).

    BD-4 — S4- Two-Clock Rollover (Phase-0b prereg §1):
      pos63_t   = 100 * (C - min(C,63)) / (max(C,63) - min(C,63)); skip if max==min
      daily_osc = EMA5(pos63)
      pos252_t  = same over 252 bars
      weekly_osc = EMA21(pos252)
      rollover(osc): max(osc,15b) >= 80 AND osc <= peak-15 AND (osc_t - osc_{t-5}) < 0
      extended: C >= 0.88 * rolling 252-bar max
      Warmup floor: >=273 prior bars required (raises ERA-LAW floor for this definition).
      Event: first bar where rollover(daily_osc) AND rollover(weekly_osc) AND extended.

    Returns list of event bar Timestamps (episode collapse applied by caller).
    """
    events: list[pd.Timestamp] = []

    era_mask = close.index >= ERA_START
    if era_mask.sum() == 0:
        return events

    # Compute pos63 (skip bars where max == min)
    roll_max_63  = close.rolling(BD4_POS_SHORT_WINDOW).max()
    roll_min_63  = close.rolling(BD4_POS_SHORT_WINDOW).min()
    hl_range_63  = roll_max_63 - roll_min_63
    pos63        = pd.Series(np.where(hl_range_63 > 0,
                                      100.0 * (close - roll_min_63) / hl_range_63,
                                      np.nan),
                             index=close.index)
    daily_osc    = _ema(pos63.ffill(), BD4_EMA_SHORT_SPAN)

    # Compute pos252
    roll_max_252 = close.rolling(BD4_POS_LONG_WINDOW).max()
    roll_min_252 = close.rolling(BD4_POS_LONG_WINDOW).min()
    hl_range_252 = roll_max_252 - roll_min_252
    pos252       = pd.Series(np.where(hl_range_252 > 0,
                                      100.0 * (close - roll_min_252) / hl_range_252,
                                      np.nan),
                             index=close.index)
    weekly_osc   = _ema(pos252.ffill(), BD4_EMA_LONG_SPAN)

    # Rollover masks
    daily_rollover  = _rollover_mask(daily_osc)
    weekly_rollover = _rollover_mask(weekly_osc)

    # Extended: close >= 0.88 * rolling 252-bar max
    roll_max_252c = close.rolling(BD4_POS_LONG_WINDOW).max()
    extended      = close >= roll_max_252c * BD4_EXTENDED_MULT

    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        # BD-4 warmup floor: >=273 prior bars (raises ERA-LAW floor)
        if i < BD4_WARMUP_BARS:
            continue
        if not bool(daily_rollover.iloc[i]):
            continue
        if not bool(weekly_rollover.iloc[i]):
            continue
        if not bool(extended.iloc[i]):
            continue
        # Liquidity
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue
        events.append(ts)

    return events


# ===========================================================================
# 5c. BD-5: Coiled Breakdown (Phase-0b prereg §2)
# ===========================================================================

def detect_bd5(ticker: str, close: pd.Series, raw_df: pd.DataFrame | None) -> list[pd.Timestamp]:
    """Detect BD-5 events: Coiled Breakdown (S5- family).

    BD-5 — S5- Coiled Breakdown (Phase-0b prereg §2):
      coil_ratio_t = (max(C,21) - min(C,21)) / median(C,21)
      coiled: coil_ratio_{t-1} <= 20th percentile of its own trailing-252-bar distribution at t-1
      sign_volume = volume * ((C-L)-(H-C))/(H-L); H==L → 0
      distribution: 21-bar-sum(sign_volume) <= -0.5σ below trailing-252-bar mean of the
                    21-bar-sum series (σ = rolling-252 std of sv_21; BD-1 convention verbatim)
      breakdown: C_t < min(C, 21 bars ending t-1)
      Event: breakdown bar with coiled and distribution both true at t.

    Returns list of event bar Timestamps.
    """
    events: list[pd.Timestamp] = []

    era_mask = close.index >= ERA_START
    if era_mask.sum() == 0:
        return events

    # coil_ratio
    roll_max_21 = close.rolling(BD5_COIL_WINDOW).max()
    roll_min_21 = close.rolling(BD5_COIL_WINDOW).min()
    roll_med_21 = close.rolling(BD5_COIL_WINDOW).median()
    coil_ratio  = (roll_max_21 - roll_min_21) / roll_med_21.replace(0.0, np.nan)

    # coiled: coil_ratio_t <= 20th percentile of its trailing-252-bar distribution
    # (evaluated at t; we use t-1 for the coiled flag per spec: "coil_ratio_{t-1}")
    coil_pct20  = coil_ratio.rolling(BD5_COIL_PCT_WINDOW).quantile(
        BD5_COIL_PCT_THRESHOLD / 100.0)
    coiled_t    = coil_ratio <= coil_pct20        # at bar t
    coiled_flag = coiled_t.shift(1)               # use coil_ratio_{t-1} per spec

    # sign_volume (BD-1 convention)
    sv = _compute_sign_volume(close, raw_df) if raw_df is not None else None

    # distribution: 21-bar-sum of sign_volume, then rolling-252 std of that sum (BD-1 verbatim)
    if sv is None:
        return events  # can't compute without H/L/V

    sv_21      = sv.rolling(BD5_DIST_SUM_WINDOW).sum()
    sv_21_mean = sv_21.rolling(BD5_DIST_ROLL_WINDOW).mean()
    sv_21_std  = sv_21.rolling(BD5_DIST_ROLL_WINDOW).std()
    dist_flag  = sv_21 <= (sv_21_mean + BD5_DIST_SIGMA * sv_21_std)  # -0.5σ below mean

    # breakdown: C_t < min(C, 21 bars ending t-1)
    # "21 bars ending t-1" = rolling 21-bar min shifted by 1
    roll_min_21_prev = close.rolling(BD5_BREAKDOWN_WINDOW).min().shift(1)
    breakdown_flag   = close < roll_min_21_prev

    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue
        if not bool(breakdown_flag.iloc[i]):
            continue
        if not bool(coiled_flag.iloc[i]):
            continue
        if not bool(dist_flag.iloc[i]):
            continue
        # Liquidity
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue
        events.append(ts)

    return events


# ===========================================================================
# 5d. BD-6: Within-Sector Leader Fade (Phase-0b prereg §3)
# Requires a sector-panel pre-pass (cross-sectional context).
# ===========================================================================

# Module-level cache for sector panel pre-pass outputs (populated once per run)
_SECTOR_PANEL_CACHE: dict[str, Any] = {}  # will hold per-date lookups


def build_sector_panel(
    universe_tickers: set[str],
    ticker_sectors: pd.DataFrame,
) -> dict[str, Any]:
    """Sector panel pre-pass for BD-6 (Phase-0b prereg §3).

    Loads universe closes for all tickers with sector assignments, then computes
    per-bar:
      - sector top-decile 126-bar-return cutoffs (one cutoff per sector per date)
      - sector median 21-bar returns (one median per sector per date)
    Sectors with <8 covered members on a bar are skipped (returns {} for that sector/bar).

    Returns a dict with keys:
      'sector_top_decile_126': {date_str -> {sector -> cutoff_return_float}}
      'sector_median_21':      {date_str -> {sector -> median_return_float}}
      'sector_map':            {ticker -> sector}
      'artifact_path':         str
      'as_of':                 str (date of ticker_sectors.parquet generation)
      'n_tickers_covered':     int

    This is expensive (loads many price series); cache the result externally.
    """
    sector_map = ticker_sectors.set_index("ticker")["sector"].to_dict()

    # Only process tickers in both universe and sector map
    covered = sorted(universe_tickers & set(sector_map.keys()))
    log.info("BD-6 sector pre-pass: %d universe tickers, %d sector-covered",
             len(universe_tickers), len(covered))

    if not covered:
        log.warning("BD-6 sector pre-pass: no covered tickers — BD-6 will yield 0 events")
        return {
            "sector_top_decile_126": {},
            "sector_median_21": {},
            "sector_map": sector_map,
            "artifact_path": str(TICKER_SECTORS_PATH),
            "as_of": str(pd.Timestamp.now("UTC").date()),
            "n_tickers_covered": 0,
        }

    # Collect per-ticker close series
    log.info("BD-6: loading close series for %d covered tickers...", len(covered))
    ticker_closes: dict[str, pd.Series] = {}
    for tk in covered:
        c = _read_massive_ticker(tk)
        if c is not None and len(c) > BD6_LEADER_WINDOW + BD6_FADE_STD_WINDOW:
            ticker_closes[tk] = c

    log.info("BD-6: loaded %d close series", len(ticker_closes))

    # Build a common date index (union of all dates in the ERA window)
    all_dates: set[pd.Timestamp] = set()
    for c in ticker_closes.values():
        era_dates = c.index[c.index >= ERA_START]
        all_dates.update(era_dates.tolist())
    all_dates_sorted = sorted(all_dates)

    # Compute per-ticker 126-bar and 21-bar returns on all dates
    # Returns are NaN when insufficient history
    ticker_ret126: dict[str, dict[pd.Timestamp, float]] = {}
    ticker_ret21:  dict[str, dict[pd.Timestamp, float]] = {}
    for tk, c in ticker_closes.items():
        ret126_d: dict[pd.Timestamp, float] = {}
        ret21_d:  dict[pd.Timestamp, float] = {}
        for ts in all_dates_sorted:
            loc = c.index.searchsorted(ts, side="right") - 1
            if loc < 0 or c.index[loc] != ts:
                continue
            if loc >= BD6_LEADER_WINDOW:
                p_now  = float(c.iloc[loc])
                p_prev = float(c.iloc[loc - BD6_LEADER_WINDOW])
                if p_prev > 0 and np.isfinite(p_now) and np.isfinite(p_prev):
                    ret126_d[ts] = p_now / p_prev - 1.0
            if loc >= BD6_FADE_WINDOW:
                p_now  = float(c.iloc[loc])
                p_prev = float(c.iloc[loc - BD6_FADE_WINDOW])
                if p_prev > 0 and np.isfinite(p_now) and np.isfinite(p_prev):
                    ret21_d[ts] = p_now / p_prev - 1.0
        ticker_ret126[tk] = ret126_d
        ticker_ret21[tk]  = ret21_d

    # Compute per-bar, per-sector top-decile cutoff (126-bar) and median (21-bar)
    sector_top_decile_126: dict[str, dict[str, float]] = {}  # date_str -> {sector -> cutoff}
    sector_median_21:      dict[str, dict[str, float]] = {}  # date_str -> {sector -> median}

    # Group tickers by sector
    sector_tickers: dict[str, list[str]] = {}
    for tk in ticker_closes:
        sec = sector_map.get(tk)
        if sec:
            sector_tickers.setdefault(sec, []).append(tk)

    for ts in all_dates_sorted:
        ts_str = str(ts.date())
        sec_decile: dict[str, float] = {}
        sec_med:    dict[str, float] = {}
        for sec, tks in sector_tickers.items():
            r126_vals = [ticker_ret126[tk][ts] for tk in tks if ts in ticker_ret126[tk]]
            r21_vals  = [ticker_ret21[tk][ts]  for tk in tks if ts in ticker_ret21[tk]]
            # Skip sector if <8 covered members (either window)
            if len(r126_vals) >= BD6_MIN_SECTOR_MEMBERS:
                arr = np.array(r126_vals)
                sec_decile[sec] = float(np.percentile(arr, 90))
            if len(r21_vals) >= BD6_MIN_SECTOR_MEMBERS:
                sec_med[sec] = float(np.median(r21_vals))
        sector_top_decile_126[ts_str] = sec_decile
        sector_median_21[ts_str]      = sec_med

    # as_of from the ticker_sectors build stamp (content truth — file mtime is
    # checkout time on CI, #2690 class); mtime stays only as a legacy fallback
    # for stores predating the sidecar.
    try:
        as_of = str(json.loads(
            (TICKER_SECTORS_PATH.parent / "ticker_sectors_meta.json").read_text()
        )["built_asof"])
    except Exception:
        try:
            import os
            mtime = os.path.getmtime(str(TICKER_SECTORS_PATH))
            as_of = str(pd.Timestamp.fromtimestamp(mtime).date())
        except Exception:
            as_of = str(pd.Timestamp.now("UTC").date())

    return {
        "sector_top_decile_126": sector_top_decile_126,
        "sector_median_21":      sector_median_21,
        "sector_map":            sector_map,
        "artifact_path":         str(TICKER_SECTORS_PATH),
        "as_of":                 as_of,
        "n_tickers_covered":     len(ticker_closes),
    }


def detect_bd6(
    ticker: str,
    close: pd.Series,
    raw_df: pd.DataFrame | None,
    sector_panel: dict[str, Any],
) -> list[pd.Timestamp]:
    """Detect BD-6 events: Within-Sector Leader Fade (S13- family).

    BD-6 — S13- Within-Sector Leader Fade (Phase-0b prereg §3):
      Requires sector_panel pre-pass output (sector_top_decile_126, sector_median_21).
      leader: ticker's trailing 126-bar return in top decile of sector covered members.
      rel21_t = ticker 21-bar return − sector median 21-bar return.
      fade:   rel21_t <= -1.0 × std(rel21, trailing 252 bars);
              bars where std(rel21, 252) == 0 are skipped (flat-window guard).
      near_highs: C_t >= 0.85 × rolling 126-bar max.
      Event: first bar where leader AND fade AND near_highs hold.

    Returns list of event bar Timestamps.
    """
    events: list[pd.Timestamp] = []

    if not sector_panel or not sector_panel.get("sector_map"):
        return events

    ticker_sector = sector_panel["sector_map"].get(ticker)
    if not ticker_sector:
        return events  # no sector assignment → skip

    sector_top_decile_126 = sector_panel.get("sector_top_decile_126", {})
    sector_median_21      = sector_panel.get("sector_median_21", {})

    era_mask = close.index >= ERA_START
    if era_mask.sum() == 0:
        return events

    # near_highs: C >= 0.85 * rolling 126-bar max
    roll_max_126 = close.rolling(BD6_LEADER_WINDOW).max()
    near_highs   = close >= roll_max_126 * BD6_NEAR_HIGHS_MULT

    # Build rel21 series for this ticker
    # rel21_t = ticker 21-bar return − sector median 21-bar return
    rel21_vals: list[float | None] = []
    rel21_idx:  list[pd.Timestamp] = []
    for i, ts in enumerate(close.index):
        if i < BD6_FADE_WINDOW:
            rel21_vals.append(None)
            rel21_idx.append(ts)
            continue
        ts_str = str(ts.date())
        sec_med = sector_median_21.get(ts_str, {}).get(ticker_sector)
        if sec_med is None:
            rel21_vals.append(None)
        else:
            p_now  = float(close.iloc[i])
            p_prev = float(close.iloc[i - BD6_FADE_WINDOW])
            if p_prev > 0 and np.isfinite(p_now) and np.isfinite(p_prev):
                ticker_ret21 = p_now / p_prev - 1.0
                rel21_vals.append(ticker_ret21 - sec_med)
            else:
                rel21_vals.append(None)
        rel21_idx.append(ts)

    rel21 = pd.Series(rel21_vals, index=rel21_idx, dtype=float)

    # std(rel21, 252) — flat-window guard: skip bars where std == 0
    rel21_std = rel21.rolling(BD6_FADE_STD_WINDOW).std()

    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue

        # near_highs
        if not bool(near_highs.iloc[i]):
            continue

        ts_str = str(ts.date())

        # leader: 126-bar return in top decile of sector
        decile_cutoff = sector_top_decile_126.get(ts_str, {}).get(ticker_sector)
        if decile_cutoff is None:
            continue  # sector has <8 covered members or data missing
        if i < BD6_LEADER_WINDOW:
            continue
        p_now  = float(close.iloc[i])
        p_prev = float(close.iloc[i - BD6_LEADER_WINDOW])
        if p_prev <= 0 or not np.isfinite(p_now) or not np.isfinite(p_prev):
            continue
        ticker_ret126 = p_now / p_prev - 1.0
        if ticker_ret126 < decile_cutoff:
            continue  # not a leader

        # fade: rel21 <= -1.0 * std(rel21, 252)
        rel21_val = rel21.iloc[i]
        std_val   = rel21_std.iloc[i]
        if pd.isna(rel21_val) or pd.isna(std_val):
            continue
        if std_val == 0.0:
            continue  # flat-window guard per prereg §3
        if not (rel21_val <= BD6_FADE_SIGMA * std_val):
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
    event_timestamps: list[pd.Timestamp],
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Sample CONTROL_RATIO random non-event bars per event, stratified by calendar year.

    Each event draws its 3 controls from the same calendar year, same ticker, non-event bars
    passing the same liquidity floor and ERA/prior-bar gates.  This implements the prereg §4
    'uniformly sampled non-event bars' WITHIN the year stratum (year-stratified matching).

    Control block note in summary: year-stratification is the implementation of 'matched'.
    """
    if not event_timestamps:
        return []

    era_close = close[close.index >= ERA_START]
    if len(era_close) < ERA_PRIOR_BARS_REQUIRED:
        return []

    # Build lookup: year -> list of eligible bar indices (non-event, passes gates)
    event_date_set: set[pd.Timestamp] = set(event_timestamps)
    year_eligible: dict[int, list[int]] = {}
    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue
        if ts in event_date_set:
            continue  # non-event bars only
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue
        yr = ts.year
        year_eligible.setdefault(yr, []).append(i)

    rows: list[dict[str, Any]] = []
    for ev_ts in event_timestamps:
        yr = ev_ts.year
        pool = year_eligible.get(yr, [])
        if not pool:
            # Fall back to adjacent years (±1) when pool is empty
            pool = year_eligible.get(yr - 1, []) + year_eligible.get(yr + 1, [])
        if not pool:
            continue
        n_draw = min(CONTROL_RATIO, len(pool))
        chosen = rng.choice(pool, size=n_draw, replace=False)
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
    sector_panel: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Process one ticker: detect all BD-1..BD-6 events, grade, add controls.

    Seeding contract (CRITICAL — preserves BD-1/2/3 byte-identity vs Phase-0-only runs):
      - BD-1/2/3 events are detected exactly as before.
      - BD-1/2/3 controls are drawn from rng (the global seed=42 Generator passed in)
        using ONLY the BD-1/2/3 event pool — the same pool, same order, same rng state
        as a Phase-0-only run for the same ticker.  BD-4/5/6 events do NOT enter this pool.
        This guarantees BD-1/2/3 event rows AND their control draws are byte-identical to
        a Phase-0-only run for every ticker.
      - BD-4/5/6 controls are drawn in a SEPARATE pass, each using the declared
        per-definition seed constants (BD4=7891, BD5=13421, BD6=19937), independent of
        the global rng.  This eliminates cross-contamination of the global rng state.
      - All controls carry definition="CONTROL" and is_control=True.  Downstream code
        (build_summary, overlap) uses the is_control flag, not a per-definition distinction.
    """
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

    # BD-4 (Phase-0b)
    try:
        bd4_raw = detect_bd4(ticker, close, raw_df)
        all_events_by_def["BD-4"] = _collapse_episodes(bd4_raw, close)
    except Exception as e:
        log.debug("BD-4 failed for %s: %s", ticker, e)
        all_events_by_def["BD-4"] = []

    # BD-5 (Phase-0b)
    try:
        bd5_raw = detect_bd5(ticker, close, raw_df)
        all_events_by_def["BD-5"] = _collapse_episodes(bd5_raw, close)
    except Exception as e:
        log.debug("BD-5 failed for %s: %s", ticker, e)
        all_events_by_def["BD-5"] = []

    # BD-6 (Phase-0b) — requires sector_panel
    if sector_panel is not None and sector_panel.get("sector_map"):
        try:
            bd6_raw = detect_bd6(ticker, close, raw_df, sector_panel)
            all_events_by_def["BD-6"] = _collapse_episodes(bd6_raw, close)
        except Exception as e:
            log.debug("BD-6 failed for %s: %s", ticker, e)
            all_events_by_def["BD-6"] = []
    else:
        all_events_by_def["BD-6"] = []

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

    # -----------------------------------------------------------------------
    # Control sampling — TWO SEPARATE PASSES (seeding contract §26-38 above).
    # -----------------------------------------------------------------------

    # PASS 1 — BD-1/2/3 controls: use the global rng (seed=42) with ONLY BD-1/2/3 events.
    # This is identical to the Phase-0-only run for any ticker — same pool, same rng state.
    phase0_event_timestamps: list[pd.Timestamp] = []
    for defn in ("BD-1", "BD-2", "BD-3"):
        phase0_event_timestamps.extend(all_events_by_def.get(defn, []))

    if phase0_event_timestamps:
        ctrl_rows_p0 = _sample_controls(ticker, close, raw_df, phase0_event_timestamps, rng)
        rows.extend(ctrl_rows_p0)

    # PASS 2 — BD-4/5/6 controls: each uses its OWN declared seed (independent of global rng).
    # seed constants: BD4=7891, BD5=13421, BD6=19937 (declared at module level).
    # We use a deterministic sub-seed derived from the declared constant + ticker hash
    # so that different tickers get different draws even with the same per-definition seed,
    # while the global rng state for Phase-0 definitions is entirely unaffected.
    for defn, seed_const in (("BD-4", BD4_CONTROL_RNG_SEED),
                              ("BD-5", BD5_CONTROL_RNG_SEED),
                              ("BD-6", BD6_CONTROL_RNG_SEED)):
        def_events = all_events_by_def.get(defn, [])
        if not def_events:
            continue
        # Per-ticker sub-seed: seed_const XOR (hash of ticker, masked to 31 bits).
        # This makes draws ticker-specific while keeping per-definition seed independence.
        ticker_hash = hash(ticker) & 0x7FFF_FFFF
        per_ticker_seed = seed_const ^ ticker_hash
        def_rng = np.random.default_rng(per_ticker_seed)
        ctrl_rows_def = _sample_controls(ticker, close, raw_df, def_events, def_rng)
        rows.extend(ctrl_rows_def)

    return rows


# ===========================================================================
# 10. Cross-definition overlap matrix (prereg §3 + Phase-0b v3 requirement)
# ===========================================================================

def _overlap_matrix(events_df: pd.DataFrame) -> dict[str, Any]:
    """Compute the six-definition cross-definition overlap matrix (events only, not controls).

    Phase-0b adds BD-4/5/6.  The BD-4 x BD-3 overlap share is a REQUIRED output row
    (prereg §1): if >50% of BD-4 episodes overlap BD-3 episodes (±21 bars), the summary
    must carry a redundancy flag.

    Overlap is exact-date-match (same ticker, same event_date string) — note that the
    prereg specifies ±21 bars for the BD-4 x BD-3 check; we report both:
      - exact overlap (same-date)
      - near overlap (within ±21 business days, same ticker)
        Uses np.busday_count (Mon-Fri) as proxy for trading bars; over-inclusive by
        at most ~1 bar (US market holidays not excluded), making the redundancy_flag
        conservative (slightly more likely to trigger).  Prior implementation used
        pd.Timedelta(days=30) which could under-count near-overlaps around US holiday
        clusters by 0-1 bar.

    Returns dict with:
      'matrix':       {def1: {def2: n_exact_overlap}}
      'bd4_x_bd3':    {n_exact, n_near_21, bd4_n, bd3_n, share_exact, share_near,
                       redundancy_flag (bool: near share > 0.5)}
    """
    is_ctrl = events_df.get("is_control", pd.Series(False, index=events_df.index))
    ev = events_df[~is_ctrl.astype(bool)]

    all_defs = ["BD-1", "BD-2", "BD-3", "BD-4", "BD-5", "BD-6"]

    # Build per-definition (ticker, event_date) sets
    def_keys: dict[str, set[str]] = {}
    for d in all_defs:
        sub = ev[ev["definition"] == d]
        if len(sub) > 0 and "ticker" in sub.columns and "event_date" in sub.columns:
            def_keys[d] = set(sub.apply(lambda r: f"{r['ticker']}|{r['event_date']}", axis=1))
        else:
            def_keys[d] = set()

    # Exact-match overlap matrix
    matrix: dict[str, dict[str, int]] = {}
    for d1 in all_defs:
        matrix[d1] = {}
        for d2 in all_defs:
            matrix[d1][d2] = len(def_keys[d1] & def_keys[d2])

    # BD-4 x BD-3 near overlap (±21 bars) — REQUIRED per BD_PHASE0B_PREREG §1
    bd4_n  = len(def_keys["BD-4"])
    bd3_n  = len(def_keys["BD-3"])
    n_exact_bd4_bd3 = matrix["BD-4"]["BD-3"]

    # Build per-ticker sorted event-date lists for ±21-bar check
    def _ticker_dates(d: str) -> dict[str, list[pd.Timestamp]]:
        sub = ev[ev["definition"] == d]
        if len(sub) == 0:
            return {}
        result: dict[str, list[pd.Timestamp]] = {}
        for _, row in sub.iterrows():
            tk  = str(row["ticker"])
            dt  = pd.Timestamp(str(row["event_date"]))
            result.setdefault(tk, []).append(dt)
        for tk in result:
            result[tk].sort()
        return result

    bd4_dates = _ticker_dates("BD-4")
    bd3_dates = _ticker_dates("BD-3")

    # Count BD-4 episodes that have a BD-3 episode within ±21 trading bars (same ticker).
    # We use np.busday_count (Mon-Fri business days) as a proxy for trading bars.
    # Business days over-count by at most ~1 bar vs true trading days (US holidays not
    # excluded), making this slightly conservative (over-inclusive → more redundancy flags).
    # This is anti-conservative compared to the prior pd.Timedelta(days=30) proxy which
    # could under-count near-overlaps by 0-1 bar around US holiday clusters.
    # Corrects finding #1 from W-0B code review (2026-07-06).
    _NEAR_WINDOW_BDAYS = 21  # per BD_PHASE0B_PREREG §1
    n_near = 0
    for tk, d4_list in bd4_dates.items():
        d3_list = bd3_dates.get(tk, [])
        if not d3_list:
            continue
        d3_dates_arr = np.array([d.date() for d in d3_list], dtype="datetime64[D]")
        for d4_ts in d4_list:
            d4_date = np.datetime64(d4_ts.date(), "D")
            # np.busday_count returns signed count; we want abs distance in bdays
            bday_diffs = np.abs(np.busday_count(
                np.minimum(d3_dates_arr, d4_date),
                np.maximum(d3_dates_arr, d4_date),
            ))
            if np.any(bday_diffs <= _NEAR_WINDOW_BDAYS):
                n_near += 1

    share_exact = round(n_exact_bd4_bd3 / bd4_n, 4) if bd4_n > 0 else None
    share_near  = round(n_near / bd4_n, 4)            if bd4_n > 0 else None
    redundancy_flag = (share_near is not None) and (share_near > 0.50)

    bd4_x_bd3 = {
        "n_bd4_episodes": bd4_n,
        "n_bd3_episodes": bd3_n,
        "n_exact_overlap": n_exact_bd4_bd3,
        "n_near_overlap_21bars": n_near,
        "share_exact": share_exact,
        "share_near_21bars": share_near,
        "redundancy_flag": redundancy_flag,
        "redundancy_note": (
            "BD-4 overlaps >50% of BD-3 episodes (±21 bars): treat as BD-3 variant, "
            "not independent species (BD_PHASE0B_PREREG §1 obligation)"
            if redundancy_flag else ""
        ),
    }

    return {
        "matrix": matrix,
        "bd4_x_bd3": bd4_x_bd3,
    }


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
        "universe_as_of":         pd.Timestamp.now("UTC").date().isoformat(),
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
        "generated_utc":          pd.Timestamp.now("UTC").isoformat(),
    }


# ===========================================================================
# 12. Summary statistics (§6 table)
# ===========================================================================

def _base_rates(sub: pd.DataFrame, col: str, target_val: str) -> float | None:
    valid = sub[col].notna()
    if valid.sum() == 0:
        return None
    return round(float((sub.loc[valid, col] == target_val).mean() * 100), 2)


# ---------------------------------------------------------------------------
# Bootstrap CI95 (episode-clustered, ticker×year clusters — B2)
# ---------------------------------------------------------------------------

_BOOT_N_ITER = 5000
_BOOT_RNG_SEED = 12345  # separate seed from control sampling to avoid entanglement


def _clustered_bootstrap_ci95(
    values: np.ndarray,
    clusters: np.ndarray,
    rng: np.random.Generator,
    n_iter: int = _BOOT_N_ITER,
) -> tuple[float, float] | None:
    """Episode-clustered bootstrap CI95 on mean(values).

    Resample unit = cluster (ticker×year).  Each iteration: draw len(unique_clusters)
    clusters with replacement, concatenate their member values, compute the mean.

    Returns (ci_lo, ci_hi) at the 2.5/97.5 percentiles, or None if < 2 clusters.
    Cluster variable: ticker×year.
    """
    unique_clusters = np.unique(clusters)
    if len(unique_clusters) < 2:
        return None
    cluster_values: dict[Any, list[float]] = {}
    for c, v in zip(clusters, values):
        cluster_values.setdefault(c, []).append(v)

    boot_means = np.empty(n_iter)
    n_clusters = len(unique_clusters)
    for b in range(n_iter):
        drawn = rng.choice(unique_clusters, size=n_clusters, replace=True)
        sample = []
        for c in drawn:
            sample.extend(cluster_values[c])
        boot_means[b] = np.mean(sample)

    return (
        round(float(np.percentile(boot_means, 2.5)), 4),
        round(float(np.percentile(boot_means, 97.5)), 4),
    )


def _paired_within_event_stats(
    ev_d: pd.DataFrame,
    long_param: str,
    short_label: str,
    boot_rng: np.random.Generator,
) -> dict[str, Any] | None:
    """Compute per-event within-pair diff (short_favorable - long_stopped), mean, and CI95.

    Both sides must be matured (non-None state).  Cluster = ticker×year.
    Positive mean = short favorable dominates; negative = long stop dominates.

    Horizon mapping (prereg §4 paired contrast):
      short21 ↔ clean8_21   (21-bar grade)
      short126 ↔ clean15_126 (126-bar grade)
    """
    long_col  = f"long_state_{long_param}"
    short_col = f"short_state_{short_label}"

    if long_col not in ev_d.columns or short_col not in ev_d.columns:
        return None

    # Rows where BOTH sides matured
    matured_mask = ev_d[long_col].notna() & ev_d[short_col].notna()
    sub = ev_d[matured_mask].copy()
    if len(sub) == 0:
        return None

    long_stopped   = (sub[long_col]  == TerminalState.STOPPED).astype(int)
    short_favorable = (sub[short_col] == TerminalStateShort.FAVORABLE_TRIGGERED).astype(int)
    paired_diff = (short_favorable - long_stopped).to_numpy(dtype=float)

    # Cluster label = ticker×year
    tickers = sub["ticker"].astype(str)
    years   = pd.to_datetime(sub["event_date"]).dt.year.astype(str)
    clusters = (tickers + "_" + years).to_numpy()

    mean_diff = round(float(np.mean(paired_diff)), 4)
    ci = _clustered_bootstrap_ci95(paired_diff, clusters, boot_rng)

    return {
        "mean_paired_diff_pp": round(mean_diff * 100, 2),
        "n_matured_both_sides": int(len(sub)),
        "long_stopped_rate_pct": round(float(long_stopped.mean() * 100), 2),
        "short_favorable_rate_pct": round(float(short_favorable.mean() * 100), 2),
        "ci95": (
            [round(ci[0] * 100, 2), round(ci[1] * 100, 2)]
            if ci is not None else None
        ),
        "cluster_var": "ticker_x_year",
        "boot_n_iter": _BOOT_N_ITER,
        "interpretation": (
            "positive = short-favorable dominates long-stopped at this horizon; "
            "negative = long-stopped dominates"
        ),
    }


def _vs_control_stats(
    ev_d: pd.DataFrame,
    ctrl_d: pd.DataFrame,
    long_param: str,
    boot_rng: np.random.Generator,
) -> dict[str, Any] | None:
    """Event stop rate minus control stop rate (between-group quantity) with clustered CI95.

    Events clustered by ticker×year; controls clustered by ticker×year of their control date.
    """
    long_col = f"long_state_{long_param}"
    if long_col not in ev_d.columns:
        return None

    ev_valid   = ev_d[ev_d[long_col].notna()]
    ctrl_valid = ctrl_d[ctrl_d[long_col].notna()] if long_col in ctrl_d.columns else ctrl_d.iloc[0:0]

    ev_stop_rate   = _base_rates(ev_d,   long_col, TerminalState.STOPPED)
    ctrl_stop_rate = _base_rates(ctrl_d, long_col, TerminalState.STOPPED)
    if ev_stop_rate is None or ctrl_stop_rate is None:
        return None

    delta_pp = round(ev_stop_rate - ctrl_stop_rate, 2)

    # Bootstrap on event side (cluster = ticker×year); control is a large uniform pool
    ev_stopped_arr = (ev_valid[long_col] == TerminalState.STOPPED).astype(float).to_numpy()
    ev_tickers     = ev_valid["ticker"].astype(str)
    ev_years       = pd.to_datetime(ev_valid["event_date"]).dt.year.astype(str)
    ev_clusters    = (ev_tickers + "_" + ev_years).to_numpy()
    ci_ev = _clustered_bootstrap_ci95(ev_stopped_arr, ev_clusters, boot_rng)

    ctrl_stopped_arr = (ctrl_valid[long_col] == TerminalState.STOPPED).astype(float).to_numpy() if len(ctrl_valid) > 0 else np.array([])
    # For controls, cluster by ticker×year of the control bar date
    if len(ctrl_valid) > 0 and "event_date" in ctrl_valid.columns:
        ctrl_tickers  = ctrl_valid["ticker"].astype(str)
        ctrl_years    = pd.to_datetime(ctrl_valid["event_date"]).dt.year.astype(str)
        ctrl_clusters = (ctrl_tickers + "_" + ctrl_years).to_numpy()
        ci_ctrl = _clustered_bootstrap_ci95(ctrl_stopped_arr, ctrl_clusters, boot_rng)
    else:
        ci_ctrl = None

    return {
        "event_stop_rate_pct":   ev_stop_rate,
        "control_stop_rate_pct": ctrl_stop_rate,
        "long_stop_vs_control_pp": delta_pp,
        "n_events_matured": int(len(ev_valid)),
        "n_controls_matured": int(len(ctrl_valid)),
        "ci95_event_stop_pct": (
            [round(ci_ev[0] * 100, 2), round(ci_ev[1] * 100, 2)]
            if ci_ev is not None else None
        ),
        "cluster_var": "ticker_x_year",
    }


def build_summary(events_df: pd.DataFrame, stamp: dict,
                   ledger: "TrialLedger | None" = None) -> dict[str, Any]:
    """Build the §6 table (v3: all six definitions + six-way overlap matrix).

    Per RUL-U3a: prints (a) family literal_n from ledger (all distinct configs logged),
    (b) max()-basis divergence note.
    """
    is_ctrl = events_df.get("is_control", pd.Series(False, index=events_df.index))
    ev   = events_df[~is_ctrl.astype(bool)]
    ctrl = events_df[is_ctrl.astype(bool)]

    boot_rng = np.random.default_rng(_BOOT_RNG_SEED)

    # RUL-U3a: retrieve family literal_n
    literal_n: int | None = None
    if ledger is not None:
        try:
            literal_n = ledger.literal_n(family="short_side")
        except Exception:
            pass

    per_def: dict[str, Any] = {}
    for defn in ["BD-1", "BD-2", "BD-3", "BD-4", "BD-5", "BD-6"]:
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

        # B1: within-event paired contrast (prereg §4 and §6 deliverable)
        # Paired diff per matured event: short_favorable(0/1) - long_stopped(0/1).
        # Horizon mapping: short21 ↔ clean8_21; short126 ↔ clean15_126.
        paired_within: dict[str, Any] = {}
        for long_param, short_label in (("clean8_21", "short21"), ("clean15_126", "short126")):
            stat = _paired_within_event_stats(ev_d, long_param, short_label, boot_rng)
            if stat is not None:
                paired_within[f"{long_param}_x_{short_label}"] = stat

        # B1: vs-control block (renamed from paired_asymmetry_delta) — between-group quantity
        # with clustered CI95
        vs_control: dict[str, Any] = {}
        for pname in ("clean15_126", "clean8_21"):
            stat = _vs_control_stats(ev_d, ctrl_d, pname, boot_rng)
            if stat is not None:
                vs_control[pname] = stat

        per_def[defn] = {
            "n_episodes":    n_episodes,
            "per_year":      per_year,
            "long_states":   long_states,
            "short_states":  short_states,
            "control_baseline_long": ctrl_long_states,
            "paired_within_event":   paired_within,
            "vs_control":            vs_control,
            "control_sampling_note": (
                "year-stratified: each event's controls drawn from same calendar year, "
                "same ticker, non-event bars passing same liquidity floor (prereg §4 matched)"
            ),
            "powering_note": (
                "< 100 episodes: parked as underpowered per prereg §6"
                if n_episodes < 100 else ""
            ),
        }

    # Six-definition overlap matrix (Phase-0b v3 requirement)
    overlap = _overlap_matrix(events_df)

    # Total events
    total_events = sum(d.get("n_episodes", 0) for d in per_def.values())
    total_controls = int(ctrl["definition"].notna().sum()) if len(ctrl) > 0 else 0

    # RUL-U3a budget note
    budget_note = (
        f"declared_budget=3 per study (Phase-0 and Phase-0b each); "
        f"log_declared_budget uses max() semantics (per-family BH floor, not cumulative sum). "
        f"family literal_n (distinct configs logged)={literal_n}. "
        f"Max()-basis divergence: each study's declared_budget=3 is its own BH floor; "
        f"cross-study multiplicity within 'short_side' is NOT captured by declared_budget — "
        f"tolerable because both studies are descriptive/research-only (no DSR, per RUL-U3a)."
    )

    return {
        "schema":               "breakdown_events_summary.v3",
        "vintage":              stamp,
        "trial_family":         "short_side",
        "declared_budget":      3,
        "family_literal_n":     literal_n,
        "budget_semantics_note": budget_note,
        "derived_from_surface": "bd_phase0_tape",
        "per_definition":       per_def,
        "overlap_matrix":       overlap,
        "total_events":         total_events,
        "total_controls":       total_controls,
        "phase":                "phase0_and_phase0b_descriptive_only",
        "note": (
            "Phase-0/0b is DESCRIPTIVE. No chip, no synapse consumer, no site surface, "
            "no promotion criteria applied. Nulls printed, not hidden. "
            "Survivorship_biased=True: names delisted before ERA window may be absent. "
            "BD-6 requires ticker_sectors.parquet (build_sector_map.py output); "
            "if absent, BD-6 events=0 and sector panel is None."
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

    # TRIAL LEDGER: log declared budget BEFORE running (prereg §1, Phase-0b RUL-U3a)
    ledger_path = DATA_DIR / "trial_ledger.jsonl"
    led = TrialLedger(path=ledger_path)

    # Phase-0 budget (may already be logged; idempotent)
    led.log_declared_budget(
        3,
        family="short_side",
        reason="BD Phase-0: 3 definitions (BD-1 distribution-pinned, BD-2 failed-reclaim, BD-3 tail-flag); no threshold search",
    )
    # Phase-0b budget (this run; max() semantics per RUL-U3a — declared_budget=3 is per-study BH floor)
    led.log_declared_budget(
        3,
        family="short_side",
        reason=(
            "BD Phase-0b: 3 definitions (BD-4 two-clock-rollover, BD-5 coiled-breakdown, "
            "BD-6 within-sector-leader-fade); no threshold search; "
            "max()-semantics: this is not additive with Phase-0 declared_budget=3 (RUL-U3a)"
        ),
    )
    # Log each definition as a distinct config so literal_n accumulates honestly (RUL-U3a)
    for defn_cfg in [
        {"study": "phase0",  "definition": "BD-1", "spec": "distribution-pinned"},
        {"study": "phase0",  "definition": "BD-2", "spec": "failed-reclaim"},
        {"study": "phase0",  "definition": "BD-3", "spec": "tail-flag-breach"},
        {"study": "phase0b", "definition": "BD-4", "spec": "two-clock-rollover"},
        {"study": "phase0b", "definition": "BD-5", "spec": "coiled-breakdown"},
        {"study": "phase0b", "definition": "BD-6", "spec": "within-sector-leader-fade"},
    ]:
        led.log_trial(defn_cfg, family="short_side")

    literal_n = led.literal_n(family="short_side")
    log.info(
        "TrialLedger: declared_budget=3 (max()-floor) x2 studies logged; "
        "family='short_side' literal_n=%d (distinct configs); "
        "max()-basis divergence: declared_budget is per-study BH floor, not cumulative sum",
        literal_n,
    )
    print(
        f"\n[RUL-U3a BUDGET LOG] family='short_side' literal_n={literal_n} distinct configs; "
        f"declared_budget=3 per study (Phase-0 + Phase-0b both logged); "
        f"max()-basis semantics: NOT a sum — each declared_budget=3 is a per-study BH floor. "
        f"Cross-study multiplicity within 'short_side' is NOT captured here "
        f"(tolerable: both studies are descriptive/research-only)."
    )

    # Build universe
    if parsed.ticker:
        universe = {parsed.ticker}
    else:
        universe = build_universe()

    if parsed.dry_run:
        universe = set(list(sorted(universe))[:10])
        log.info("DRY RUN: processing %d tickers only", len(universe))

    # BD-6 sector pre-pass (must happen before the per-ticker loop)
    sector_panel: dict[str, Any] | None = None
    if TICKER_SECTORS_PATH.exists():
        try:
            ticker_sectors = pd.read_parquet(TICKER_SECTORS_PATH)
            if "ticker" not in ticker_sectors.columns and ticker_sectors.index.name == "ticker":
                ticker_sectors = ticker_sectors.reset_index()
            if "ticker" in ticker_sectors.columns and "sector" in ticker_sectors.columns:
                log.info("BD-6: ticker_sectors.parquet found (%d rows) — running sector pre-pass",
                         len(ticker_sectors))
                sector_panel = build_sector_panel(universe, ticker_sectors)
                log.info("BD-6 sector pre-pass complete: n_covered=%d, artifact_as_of=%s",
                         sector_panel.get("n_tickers_covered", 0),
                         sector_panel.get("as_of", "?"))
            else:
                log.warning("BD-6: ticker_sectors.parquet missing 'ticker' or 'sector' column "
                            "— BD-6 will yield 0 events")
        except Exception as e:
            log.warning("BD-6 sector pre-pass failed: %s — BD-6 will yield 0 events", e)
    else:
        log.warning(
            "BD-6: ticker_sectors.parquet not found at %s — BD-6 will yield 0 events. "
            "Run scripts/build_sector_map.py first.",
            TICKER_SECTORS_PATH,
        )

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
            rows = process_ticker(ticker, rng, sector_panel=sector_panel)
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

        # Build summary (v3: all six definitions)
        stamp = _make_vintage_stamp(len(universe))
        # Add sector panel stamp to vintage
        if sector_panel is not None:
            stamp["bd6_sector_artifact"] = sector_panel.get("artifact_path", "?")
            stamp["bd6_sector_as_of"]    = sector_panel.get("as_of", "?")
            stamp["bd6_n_tickers_covered"] = sector_panel.get("n_tickers_covered", 0)
        else:
            stamp["bd6_sector_artifact"] = None
            stamp["bd6_sector_as_of"]    = None
            stamp["bd6_n_tickers_covered"] = 0
        summary = build_summary(df, stamp, ledger=led)
        summary["runtime_seconds"] = round(elapsed_total, 1)
        summary["n_tickers_processed"] = len(universe)

        OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
        log.info("Wrote %s", OUT_SUMMARY)

        # Print the §6 table to stdout (all six definitions, v3 schema)
        print("\n=== BD Phase-0/0b Summary Table (v3 — all six definitions) ===")
        for defn, d in summary["per_definition"].items():
            n_ep = d["n_episodes"]
            phase_tag = "Phase-0b" if defn in ("BD-4", "BD-5", "BD-6") else "Phase-0"
            print(f"\n{defn} [{phase_tag}]: {n_ep} episodes")
            print(f"  per_year: {d['per_year']}")
            for pname, ls in d.get("long_states", {}).items():
                print(f"  long[{pname}]: stop={ls.get('stop_rate_pct')}% "
                      f"liftoff={ls.get('liftoff_rate_pct')}% n_matured={ls.get('n_matured')}")
            for sh_label, ss in d.get("short_states", {}).items():
                print(f"  short[{sh_label}]: adverse={ss.get('adverse_rate_pct')}% "
                      f"favorable={ss.get('favorable_rate_pct')}% "
                      f"n_matured={ss.get('n_matured')}")
            for key, pw in d.get("paired_within_event", {}).items():
                ci = pw.get("ci95")
                print(f"  paired_within[{key}]: diff={pw.get('mean_paired_diff_pp')}pp "
                      f"ci95={ci} n={pw.get('n_matured_both_sides')}")
            for pname, vc in d.get("vs_control", {}).items():
                print(f"  vs_control[{pname}]: delta={vc.get('long_stop_vs_control_pp')}pp")
            if d.get("powering_note"):
                print(f"  NOTE: {d['powering_note']}")

        # Six-way overlap matrix summary
        om = summary.get("overlap_matrix", {})
        print(f"\nOverlap matrix (exact-date): {om.get('matrix', {})}")
        bd4x3 = om.get("bd4_x_bd3", {})
        print(f"BD-4 x BD-3 (REQUIRED CHECK): n_bd4={bd4x3.get('n_bd4_episodes')} "
              f"n_near_21bars={bd4x3.get('n_near_overlap_21bars')} "
              f"share_near={bd4x3.get('share_near_21bars')} "
              f"redundancy_flag={bd4x3.get('redundancy_flag')}")
        if bd4x3.get("redundancy_note"):
            print(f"  REDUNDANCY: {bd4x3['redundancy_note']}")

        # BD-6 sector panel note
        if sector_panel is None:
            print("\nBD-6: ticker_sectors.parquet absent — 0 events (run build_sector_map.py first)")
        else:
            print(f"\nBD-6 sector panel: {sector_panel.get('n_tickers_covered')} tickers covered, "
                  f"as_of={sector_panel.get('as_of')}")

        print(f"\n[RUL-U3a] family='short_side' literal_n={summary.get('family_literal_n')} "
              f"(distinct configs); declared_budget=3 per study (max()-floor); "
              f"NOT cumulative — see budget_semantics_note in summary JSON.")
        print(f"Total events: {summary['total_events']}, controls: {summary['total_controls']}")
        print(f"Runtime: {elapsed_total:.1f}s")
    else:
        log.info("DRY RUN: no files written (found %d rows from %d tickers)",
                 len(all_rows), len(tickers_to_process))
        # Still print event counts for dry-run inspection
        ev_rows = [r for r in all_rows if not r.get("is_control")]
        from collections import Counter
        cnt = Counter(r.get("definition") for r in ev_rows)
        print("Dry-run event counts by definition:", dict(cnt))
        if sector_panel is None:
            print("BD-6: ticker_sectors.parquet absent — 0 events")


if __name__ == "__main__":
    main()
