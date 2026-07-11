"""engine/leader_lifecycle.py — Leader Radar lifecycle state machine (W1).

Pure-function layer; zero I/O, zero LLM.
Program: Leader Radar (research/LEADER_RADAR_MASTERPLAN_BY_FABLE.md)
Rulings: LR-R1 through LR-R15.

All inputs are pre-computed pandas objects or scalar values.
Tri-state Kleene logic reused from engine.flow_leaders idiom: None = missing, not False.
BREAKAWAY/LEADERSHIP state strings come from winner_autopsy.compute_watch_states()
by import in the W2a builder; this module accepts them as plain strings.

Vocabulary fences (LR-R1):
  - "winner" only post-Detector-D (WA-R10)
  - no "sponsorship" (WA-R3)
  - no "money routing" / "capital suction" (TOP3-O2)
  - no "validated" (CI)
  - "extended_leg" / "basing_leg" only (never donor/recipient/routing)

W2a builder contract — apply_hysteresis dual-history columns
--------------------------------------------------------------
The nightly builder (scripts/build_leader_radar.py) persists TWO columns per name in
data/leader_radar/state_history.parquet:

  raw_state       — output of classify() for that session (before hysteresis)
  confirmed_state — output of apply_hysteresis() for that session

On each nightly run the builder:
  1. Calls classify(inp) → raw_state_today
  2. Loads prior rows for the name → raw_state_history, confirmed_state_history
  3. Calls apply_hysteresis(raw_state_today, raw_state_history, confirmed_state_history)
     → confirmed_state_today
  4. Appends (date, raw_state_today, confirmed_state_today) to the parquet

Context lookups inside classify() (state_history arg on LifecycleInputs), days_in_state
anchoring, and eligible_for_refire all consume CONFIRMED state history. Raw history is
consumed ONLY by apply_hysteresis for entry/exit counting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from engine.cycles import _tf_state  # pinned oscillator math; LR-R7

log = logging.getLogger(__name__)


# ── Kleene three-valued logic helpers (mirror of flow_leaders idiom) ──────────

def _and3(*vals: bool | None) -> bool | None:
    """Kleene AND over pre-evaluated bool-or-None operands.

    Returns:
        False  — any operand is False (short-circuits regardless of None)
        True   — all operands are True (none are None)
        None   — at least one operand is None, none are False
    """
    has_none = False
    for v in vals:
        if v is False:
            return False
        if v is None:
            has_none = True
    return None if has_none else True


def _or3(*vals: bool | None) -> bool | None:
    """Kleene OR over pre-evaluated bool-or-None operands.

    Returns:
        True   — any operand is True (short-circuits regardless of None)
        False  — all operands are False (none are None)
        None   — at least one operand is None, none are True
    """
    has_none = False
    for v in vals:
        if v is True:
            return True
        if v is None:
            has_none = True
    return None if has_none else False


def _is_null(v: object) -> bool:
    """True when v is a null sentinel (None, pd.NA, or float NaN)."""
    if v is None:
        return True
    if v is pd.NA:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    return False


# ── Module constants (frozen; change = engine version bump) ──────────────────
# All threshold provenance comments per LR-R2.

# ---- SUPPRESSED thresholds --------------------------------------------------
# dossier-derived: field-guide §III "RS vs. benchmark at or near YTD lows, sustained for 3+ months"
RS_SLOPE_63D_NEGATIVE_MONTHS: int = 3        # months RS-slope < 0 required (63d window, ~3mo)
RS_63D_WINDOW: int = 63
RS_21D_WINDOW: int = 21

# pre-registered-arbitrary (frozen; LR-R2)
SUPPRESSED_DRAWDOWN_PCT: float = 25.0        # % drawdown from 252d high
SUPPRESSED_BELOW_200DMA_MONTHS: int = 12     # alt: months below 200dma
SUPPRESSED_CHEAP_PCTILE: float = 40.0        # cheap_pctile ≤ 40 (null-tolerant)

# ---- QUIET_ACCUMULATION thresholds ------------------------------------------
# pre-registered-arbitrary (LR-R2)
QA_BASE_RANGE_DAYS: int = 60                 # 60d range compression window
QA_BASE_RANGE_WIDTH: float = 25.0           # ≤ 25% price width counts as a base
QA_SUPPRESSED_LOOKBACK_SESSIONS: int = 126  # ~6 months
QA_K_OF_N: int = 2                          # ≥2 of chips required

# dossier-derived: up/down ≥ 1.2 (field guide §III, institutional practice)
UPDOWN_VOL_RATIO_MIN: float = 1.2
UPDOWN_VOL_WINDOW: int = 50

# pre-registered-arbitrary: +3 accum-day margin
ACCUM_OVER_DIST_MARGIN: int = 3
ACCUM_DIST_WINDOW: int = 25
POCKET_PIVOT_LOOKBACK: int = 10             # Kacher-Morales definition

# pre-registered-arbitrary: OBV divergence window
OBV_DIVERGENCE_WINDOW: int = 63

# ---- CATALYST_WINDOW thresholds ---------------------------------------------
# dossier-derived: gap ≥ 5% on ≥ 2× 20d avg volume (standard institutional ignition)
CATALYST_GAP_PCT: float = 5.0
CATALYST_VOL_MULT: float = 2.0
CATALYST_TRIGGER_SESSIONS: int = 10         # ignition within last 10 sessions
QA_RECENCY_SESSIONS: int = 21              # current-or-within-21s QA context

# dossier-derived: RS-leads-price divergence (George-Hwang extended form)
RS_LINE_NH_LOOKBACK: int = 126

# ---- LEADERSHIP / BREAKAWAY thresholds --------------------------------------
# dossier-derived: RS top-decile for ≥ 4 weeks
RS_TOP_DECILE_WEEKS_MIN: int = 4
RS_TOP_DECILE_THRESHOLD: float = 0.90       # 90th pctile rank

# ---- CROWDED thresholds -----------------------------------------------------
# dossier-derived (field-guide §III Stage 6 + external dossier)
CROWDED_EXTENSION_PCT: float = 25.0         # extension vs 50dma ≥ 25%
CROWDED_EXTENSION_OWN_PCTILE: float = 90.0 # or ≥ 90th pctile own history
CROWDED_MONTHLY_RSI: float = 80.0           # monthly RSI ≥ 80
# dossier-derived: 4w return > 2× annualized 13w return (parabolic flag)
PARABOLIC_WEEKS: int = 4
PARABOLIC_REF_WEEKS: int = 13
CROWDED_ANALYST_BUY_PCT: float = 85.0       # analyst buy-share ≥ 85% (finnhub)
# dossier-derived: basket-correlation ≥ 0.75 having risen from < 0.5
CROWDED_CORR_NOW: float = 0.75
CROWDED_CORR_THEN: float = 0.50
CROWDED_K_OF_N: int = 3                     # ≥3 of chips required

# ---- State machine / hysteresis ---------------------------------------------
# pre-registered-arbitrary (LR-R2; frozen)
HYSTERESIS_ENTER_N: int = 2   # consecutive sessions to enter a state
HYSTERESIS_EXIT_N: int = 3    # consecutive sessions failing to exit

# ---- Refire lockout ---------------------------------------------------------
# pre-registered-arbitrary (LR-R8)
REFIRE_LOCKOUT_SESSIONS: int = 21

# ---- Regime thresholds ------------------------------------------------------
# pre-registered-arbitrary (LR-R5; threshold freeze = no tuning on observed cases)
REGIME_NARROW_DISPERSION: float = 0.70
REGIME_NARROW_AVG_CORR: float = 0.15
REGIME_NARROW_PCT_ABOVE_200: float = 55.0  # < 55%
REGIME_THRUST_PCT_ABOVE_200: float = 70.0  # ≥ 70%
REGIME_THRUST_TOP5_SHARE: float = 0.35     # top5 contribution < 0.35

# ---- Rerating watch ---------------------------------------------------------
# pre-registered-arbitrary (LR-R6)
RERATING_REVISION_BREADTH_MIN: float = 0.60   # breadth ≥ 0.6
RERATING_CHEAP_PCTILE: float = 40.0           # cheap_pctile ≤ 40
# Cremers de-escalation window
EARNINGS_WINDOW_DAYS: int = 14

# ---- Extended/basing handoff ------------------------------------------------
# dossier-derived: ≥ 90th pctile extension vs 200d trend (field guide §IV rotation)
EXTENDED_LEG_PCTILE: float = 90.0

# State labels (canonical; never spell out elsewhere — import from here)
STATE_SUPPRESSED = "SUPPRESSED"
STATE_QUIET_ACCUMULATION = "QUIET_ACCUMULATION"
STATE_CATALYST_WINDOW = "CATALYST_WINDOW"
STATE_BREAKAWAY = "BREAKAWAY"
STATE_LEADERSHIP = "LEADERSHIP"
STATE_CROWDED = "CROWDED"
STATE_FAILED = "FAILED"
STATE_NONE = "NONE"

# Precedence cascade (most-advanced-wins; FAILED-override first per LR-R2)
_STATE_PRECEDENCE: list[str] = [
    STATE_FAILED,
    STATE_CROWDED,
    STATE_LEADERSHIP,
    STATE_BREAKAWAY,
    STATE_CATALYST_WINDOW,
    STATE_QUIET_ACCUMULATION,
    STATE_SUPPRESSED,
    STATE_NONE,
]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class LifecycleInputs:
    """All pre-computed inputs for classify().

    All numeric inputs are float | None (None = data missing, not False).
    Tri-state chip inputs are bool | None.
    """
    # --- RS series inputs ---
    close: pd.Series                            # daily close (DatetimeIndex, ascending)
    bench_close: pd.Series                      # benchmark daily close (e.g. SPY)

    # --- Winner Autopsy integration ---
    breakaway_watch_state: str | None = None    # from compute_watch_states(): 'breakaway'/'emerging'/'continuation'/'failed'/'digestion'/'none'

    # --- Fundamental / revision inputs ---
    net_up_30d: float | None = None             # revision: net upgrade count last 30d
    est_chg_30d: float | None = None            # revision: estimate change pct last 30d
    revision_breadth: float | None = None       # breadth of upward revisions (0..1)
    cheap_pctile: float | None = None           # valuation cheap percentile (0=cheap, 100=expensive)
    fwd_pe: float | None = None                 # forward PE
    sector_median_fwd_pe: float | None = None   # sector median forward PE

    # --- Accumulation inputs ---
    # Pre-computed OHLCV; volume optional
    high: pd.Series | None = None
    low: pd.Series | None = None
    volume: pd.Series | None = None

    # --- Crowding / extension inputs ---
    analyst_buy_pct: float | None = None        # analyst buy-share (0..100)
    rr_25d: float | None = None                 # 25-delta risk reversal (options)
    rr_80th_pctile: float | None = None         # own 80th pctile of rr_25d
    basket_corr_now: float | None = None        # basket 60d correlation now
    basket_corr_then: float | None = None       # basket correlation 3m ago

    # --- RS peer data ---
    rs_rank_history: pd.DataFrame | None = None # weekly RS rank history (0..1)
    peer_median_rs_63d: float | None = None     # peer median 63d RS change

    # --- Valuation pctile own 5y history ---
    valuation_pctile_5y: float | None = None    # ≥ 80th = crowding signal

    # --- Insider cluster ---
    insider_cluster: bool | None = None         # ≥2 open-market buys in 90d

    # --- Earnings proximity (de-escalation) ---
    earnings_within_14d: bool | None = None     # earnings within 14 calendar days

    # --- State history (for hysteresis and fire rules) ---
    state_history: list[tuple[date, str]] = field(default_factory=list)
    days_in_state: int | None = None            # passthrough from state_history tracker


@dataclass
class LifecycleAssessment:
    """Output of classify(). One assessment per name per session.

    state: raw state (before hysteresis); apply_hysteresis() for post-hysteresis
    evidence: per-axis chip evidence dict (chip_name -> bool|None)
    n_avail: number of non-null chips going into the K-of-N count (QA/CROWDED)
    days_in_state: passthrough (anchored in state_history by W2a builder)
    de_escalation_chips: dict of de-escalation / crowding-context chips
    """
    state: str
    evidence: dict[str, bool | None]
    n_avail: int
    days_in_state: int | None = None
    de_escalation_chips: dict[str, bool | None] = field(default_factory=dict)


# ── RS-series math (LR-R3) ───────────────────────────────────────────────────

def rs_series(close: pd.Series, bench_close: pd.Series) -> pd.Series:
    """Relative-strength ratio series: close / bench_close, aligned on common dates.

    Args:
        close: stock daily close (DatetimeIndex)
        bench_close: benchmark daily close (e.g. SPY)

    Returns:
        pd.Series of RS ratio on the intersection of dates; empty if no common dates.
    """
    common = close.index.intersection(bench_close.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    c = close.reindex(common)
    b = bench_close.reindex(common)
    b_safe = b.replace(0, np.nan)
    return (c / b_safe).dropna()


def rs_slope(rs: pd.Series, window: int) -> pd.Series:
    """N-day linear slope of the RS series (OLS; positive = RS improving).

    Uses rolling apply with polyfit(deg=1). Min periods = window // 2.
    """
    if len(rs) < max(4, window // 2):
        return pd.Series(dtype=float, index=rs.index)

    def _slope_last(arr: np.ndarray) -> float:
        y = arr[~np.isnan(arr)]
        if len(y) < 4:
            return np.nan
        x = np.arange(len(y))
        # polyfit degree 1; coefficients[0] is slope
        try:
            return float(np.polyfit(x, y, 1)[0])
        except (np.linalg.LinAlgError, ValueError):
            return np.nan

    return rs.rolling(window, min_periods=window // 2).apply(_slope_last, raw=True)


def rs_turn(rs: pd.Series) -> bool | None:
    """RS turn chip: 21d slope > 0 while 63d slope <= 0.

    Tri-state: None if either slope is unavailable.
    """
    if len(rs) < RS_63D_WINDOW // 2:
        return None
    slope_21 = rs_slope(rs, RS_21D_WINDOW)
    slope_63 = rs_slope(rs, RS_63D_WINDOW)
    s21 = slope_21.iloc[-1] if len(slope_21) > 0 else np.nan
    s63 = slope_63.iloc[-1] if len(slope_63) > 0 else np.nan
    if np.isnan(s21) or np.isnan(s63):
        return None
    return bool(s21 > 0 and s63 <= 0)


def rs_line_new_high(
    rs: pd.Series,
    price: pd.Series,
    lookback: int = RS_LINE_NH_LOOKBACK,
) -> bool | None:
    """RS-line new-high flag (leads price): RS at its lookback-period high while price
    is BELOW its own lookback-period high.

    This is the George-Hwang-extended divergence: RS breaks out before price does.
    Tri-state: None when insufficient history.
    """
    if len(rs) < lookback // 2 or len(price) < lookback // 2:
        return None
    rs_clean = rs.dropna()
    price_clean = price.dropna()
    if len(rs_clean) < lookback // 2 or len(price_clean) < lookback // 2:
        return None

    rs_window = rs_clean.iloc[-lookback:]
    price_window = price_clean.iloc[-lookback:]

    rs_max = rs_window.max()
    price_max = price_window.max()
    rs_now = rs_clean.iloc[-1]
    price_now = price_clean.iloc[-1]

    if not (np.isfinite(rs_max) and np.isfinite(price_max)):
        return None
    if rs_max == 0:
        return None

    rs_at_nh = bool(rs_now >= rs_max * 0.999)  # tolerance for float precision
    price_below_nh = bool(price_now < price_max)

    return bool(rs_at_nh and price_below_nh)


def rs_top_decile_weeks(rs_rank_history: pd.DataFrame) -> int | None:
    """Consecutive weeks (from most recent) that RS rank was in the top decile (≥ 0.9).

    Args:
        rs_rank_history: DataFrame with DatetimeIndex and a 'rs_rank' column (0..1),
                         weekly frequency.

    Returns:
        int: consecutive top-decile weeks ending at the latest observation;
        None: insufficient data or column absent.
    """
    if rs_rank_history is None or rs_rank_history.empty:
        return None
    if "rs_rank" not in rs_rank_history.columns:
        return None
    ranks = rs_rank_history["rs_rank"].dropna().sort_index()
    if len(ranks) == 0:
        return None
    count = 0
    for val in reversed(ranks.values):
        if float(val) >= RS_TOP_DECILE_THRESHOLD:
            count += 1
        else:
            break
    return count


def peer_divergence(
    rs_accel_leader: float | None,
    peer_median_rs_63d: float | None,
) -> bool | None:
    """Concentration fingerprint: leader 63d RS-accel > 0 while peer-median RS < 0.

    Tri-state: None when either input is None.
    """
    if _is_null(rs_accel_leader) or _is_null(peer_median_rs_63d):
        return None
    return bool(rs_accel_leader > 0 and peer_median_rs_63d < 0)


# ── Volume / accumulation (LR-R2 §QUIET_ACCUMULATION, LR-R4) ─────────────────

def updown_volume_ratio(ohlcv: pd.DataFrame, window: int = UPDOWN_VOL_WINDOW) -> float | None:
    """Up/down dollar volume ratio over `window` sessions.

    Up day = close >= prior close; down day = close < prior close.
    Requires columns: close, volume. Returns None when insufficient data.
    """
    required = {"close", "volume"}
    if ohlcv is None or not required.issubset(ohlcv.columns):
        return None
    df = ohlcv[["close", "volume"]].dropna().tail(window + 1)
    if len(df) < max(4, window // 4):
        return None
    dv = df["close"] * df["volume"]
    direction = df["close"].diff()
    up_dv = dv.where(direction >= 0, 0.0).sum()
    dn_dv = dv.where(direction < 0, 0.0).sum()
    if dn_dv == 0:
        return None  # degenerate; no down days in window
    return float(up_dv / dn_dv)


def accumulation_distribution_days(
    ohlcv: pd.DataFrame,
    window: int = ACCUM_DIST_WINDOW,
) -> tuple[int, int] | tuple[None, None]:
    """IBD-style accumulation vs distribution day counts over `window` sessions.

    Accumulation day: close > prior close AND volume > prior day's volume.
    Distribution day: close drops ≥ 0.2% AND volume > prior day's volume.

    Returns (n_accum, n_dist) or (None, None) when insufficient data.
    """
    required = {"close", "volume"}
    if ohlcv is None or not required.issubset(ohlcv.columns):
        return None, None
    df = ohlcv[["close", "volume"]].dropna().tail(window + 1)
    if len(df) < max(4, window // 4):
        return None, None
    close_chg = df["close"].pct_change()
    vol_vs_prior = df["volume"] > df["volume"].shift(1)
    n_accum = int(((close_chg > 0) & vol_vs_prior).sum())
    n_dist = int(((close_chg <= -0.002) & vol_vs_prior).sum())
    return n_accum, n_dist


def pocket_pivot(ohlcv: pd.DataFrame) -> bool | None:
    """Pocket pivot detection (Kacher-Morales): up day with volume > max down-day
    volume of the prior 10 sessions.

    Returns True if the most recent session is a pocket pivot, False if not,
    None if insufficient data.
    """
    required = {"close", "volume"}
    if ohlcv is None or not required.issubset(ohlcv.columns):
        return None
    df = ohlcv[["close", "volume"]].dropna()
    if len(df) < POCKET_PIVOT_LOOKBACK + 2:
        return None

    today = df.iloc[-1]
    prior = df.iloc[-(POCKET_PIVOT_LOOKBACK + 1):-1]

    # Today must be an up day
    if df["close"].iloc[-1] <= df["close"].iloc[-2]:
        return False

    # Max volume among prior DOWN days
    prior_close_chg = prior["close"].diff()
    down_days = prior[prior_close_chg < 0]
    if down_days.empty:
        # No prior down days — still valid if volume is meaningful
        # Use overall prior volume as the bar
        max_dn_vol = float(prior["volume"].median())
    else:
        max_dn_vol = float(down_days["volume"].max())

    return bool(float(today["volume"]) > max_dn_vol)


def obv_divergence(
    close: pd.Series,
    volume: pd.Series,
    window: int = OBV_DIVERGENCE_WINDOW,
) -> bool | None:
    """OBV divergence: OBV at window-high while price is BELOW its window-high.

    Tri-state: None when insufficient data.
    """
    if close is None or volume is None:
        return None
    common = close.index.intersection(volume.index)
    if len(common) < window // 2:
        return None
    c = close.reindex(common).dropna()
    v = volume.reindex(common).dropna()
    common2 = c.index.intersection(v.index)
    if len(common2) < window // 2:
        return None
    c = c.reindex(common2)
    v = v.reindex(common2)

    # Compute OBV
    direction = c.diff()
    signed_vol = v.where(direction >= 0, -v)
    obv = signed_vol.fillna(0).cumsum()

    obv_win = obv.iloc[-window:]
    price_win = c.iloc[-window:]
    if len(obv_win) < window // 2:
        return None

    obv_at_nh = bool(obv.iloc[-1] >= obv_win.max() * 0.999)
    price_below_nh = bool(c.iloc[-1] < price_win.max())
    return bool(obv_at_nh and price_below_nh)


# ── Extension / crowding metrics (LR-R2 §CROWDED) ────────────────────────────

def extension_vs_50dma(close: pd.Series) -> float | None:
    """Percent extension of close above 50-day moving average.

    Returns None when insufficient data (< 25 bars).
    """
    if close is None or len(close) < 25:
        return None
    sma50 = close.rolling(50, min_periods=25).mean()
    last_sma = sma50.iloc[-1]
    last_close = close.iloc[-1]
    if not (np.isfinite(last_sma) and np.isfinite(last_close) and last_sma > 0):
        return None
    return float((last_close / last_sma - 1.0) * 100.0)


def extension_pctile_own_history(close: pd.Series, window: int = 252) -> float | None:
    """Percentile of current 50dma extension vs own history over `window` sessions.

    Returns 0..100 or None.
    """
    if close is None or len(close) < 75:
        return None
    ext = close.rolling(50, min_periods=25).apply(
        lambda arr: (arr[-1] / np.nanmean(arr) - 1.0) * 100.0 if len(arr) >= 25 else np.nan,
        raw=True,
    )
    ext_clean = ext.dropna()
    if len(ext_clean) < 20:
        return None
    current = ext_clean.iloc[-1]
    hist = ext_clean.iloc[-window:]
    return float((hist < current).mean() * 100.0)


def monthly_rsi(close: pd.Series, period: int = 14) -> float | None:
    """RSI(14) computed on month-end (ME) resampled close.

    Requires ≥ (period * 2) month-end bars. Returns None on cold-start.
    """
    if close is None or len(close) < 40:
        return None
    from engine.technicals import rsi as _rsi
    monthly = close.resample("ME").last().dropna()
    if len(monthly) < period * 2:
        return None
    r = _rsi(monthly, period)
    last = r.iloc[-1]
    if not np.isfinite(float(last)):
        return None
    return float(round(last, 1))


def parabolic_flag(close: pd.Series) -> bool | None:
    """Parabolic move flag: annualized 4-week return > 2× annualized 13-week return.

    Compares the annualized rates of the 4-week and 13-week windows. Fires when the
    most recent 4-week acceleration is disproportionately faster than the 13-week trend —
    the NVDA/PLTR blow-off signature. Mathematically equivalent to:
        (ret_4w * 13) > (ret_13w * 8)   [simplified from (ret_4w * 52/4) > 2*(ret_13w * 52/13)]

    Provenance: masterplan LR-R2 "4w return > 2× annualized 13w" — interpreted as
    annualized-4w vs annualized-13w comparison (the raw-vs-annualized reading virtually
    never fires due to the 4x amplification of the 13w rate; annualized-vs-annualized
    is the operationally meaningful signal for acceleration detection).

    Resamples to weekly (W-FRI). Tri-state: None when insufficient data.
    """
    if close is None or len(close) < 70:
        return None
    weekly = close.resample("W-FRI").last().dropna()
    if len(weekly) < 14:
        return None
    ret_4w = float(weekly.iloc[-1] / weekly.iloc[-5] - 1.0) if len(weekly) >= 5 else None
    if ret_4w is None or not np.isfinite(ret_4w):
        return None
    ret_13w = float(weekly.iloc[-1] / weekly.iloc[-14] - 1.0)
    if not np.isfinite(ret_13w):
        return None
    # Annualized 4w rate = ret_4w * (52/4) = ret_4w * 13
    # Annualized 13w rate = ret_13w * (52/13) = ret_13w * 4
    # Condition: 4w_ann > 2 * 13w_ann → ret_4w * 13 > 2 * ret_13w * 4 → 13*ret_4w > 8*ret_13w
    return bool(13.0 * ret_4w > 8.0 * ret_13w)


def basket_correlation_rising(
    corr_now: float | None,
    corr_then: float | None,
) -> bool | None:
    """Crowding signal: basket correlation ≥ 0.75 having risen from < 0.5.

    Takes precomputed correlation scalars. Tri-state: None when either is None.
    """
    if _is_null(corr_now) or _is_null(corr_then):
        return None
    return bool(float(corr_now) >= CROWDED_CORR_NOW and float(corr_then) < CROWDED_CORR_THEN)


# ── Radar-local 2D oscillator (LR-R7) ────────────────────────────────────────

def tf_state_2d(daily_close: pd.Series) -> dict:
    """2D timeframe oscillator state using the pinned _tf_state math from engine.cycles.

    Resamples daily close to 2-business-day bars. The derive_2d_ohlcv helper is
    NOT used — its contract forbids signal paths (LR-R7).

    Args:
        daily_close: daily close Series (DatetimeIndex, ascending)

    Returns:
        dict of oscillator state fields (same schema as _tf_state); empty dict on cold-start.
    """
    if daily_close is None or len(daily_close) < 80:
        return {}
    bars_2d = daily_close.resample("2B").last().dropna()
    return _tf_state(bars_2d)


# ── Rerating watch (LR-R6) ───────────────────────────────────────────────────

def rerating_conditions(
    revisions_row: dict[str, Any] | None,
    valuation_row: dict[str, Any] | None,
    earnings_row: dict[str, Any] | None,
) -> dict[str, bool | None]:
    """Per-axis rerating chips for the rerating watch table (LR-R6).

    Args:
        revisions_row: dict with keys: net_up_30d, est_chg_30d, breadth (0..1)
        valuation_row: dict with keys: cheap_pctile (0=cheap), fwd_pe, sector_median_fwd_pe
        earnings_row: dict with keys: days_to_earnings (int)

    Returns:
        dict with keys:
          revision_positive     : bool|None — net_up_30d > 0 AND est_chg_30d > 0 (level, not turn)
          revision_breadth_60   : bool|None — breadth >= 0.6
          multiple_compressed   : bool|None — cheap_pctile <= 40 OR fwd_pe < sector median
          earnings_within_14d   : bool|None — Cremers de-escalation label (context only)
    """
    chips: dict[str, bool | None] = {
        "revision_positive": None,
        "revision_breadth_60": None,
        "multiple_compressed": None,
        "earnings_within_14d": None,
    }

    if revisions_row:
        net = revisions_row.get("net_up_30d")
        chg = revisions_row.get("est_chg_30d")
        if not _is_null(net) and not _is_null(chg):
            chips["revision_positive"] = bool(float(net) > 0 and float(chg) > 0)
        breadth = revisions_row.get("breadth")
        if not _is_null(breadth):
            chips["revision_breadth_60"] = bool(float(breadth) >= RERATING_REVISION_BREADTH_MIN)

    if valuation_row:
        cheap = valuation_row.get("cheap_pctile")
        fwd = valuation_row.get("fwd_pe")
        sector_med = valuation_row.get("sector_median_fwd_pe")
        comp1 = (not _is_null(cheap) and float(cheap) <= RERATING_CHEAP_PCTILE)
        comp2 = (not _is_null(fwd) and not _is_null(sector_med) and float(fwd) < float(sector_med))
        if not _is_null(cheap) or (not _is_null(fwd) and not _is_null(sector_med)):
            chips["multiple_compressed"] = bool(comp1 or comp2)

    if earnings_row:
        dte = earnings_row.get("days_to_earnings")
        if not _is_null(dte):
            chips["earnings_within_14d"] = bool(int(dte) <= EARNINGS_WINDOW_DAYS)

    return chips


# ── Regime classifier (LR-R5) ────────────────────────────────────────────────

def leadership_regime(
    dispersion_pctile: float | None,
    avg_corr: float | None,
    pct_above_200: float | None,
    top5_share_21d: float | None,
    zweig_flag: bool | None,
) -> dict[str, Any]:
    """Leadership regime classifier (display-tier, radar-page-resident; LR-R5).

    All inputs precomputed; tri-state tolerant. Label printed WITH its conditions.

    Args:
        dispersion_pctile: cross-sectional return dispersion percentile (0..100)
        avg_corr: average pairwise correlation (rolling)
        pct_above_200: percent of universe above 200dma (0..100)
        top5_share_21d: top-5 names' share of total universe 21d return (0..1)
        zweig_flag: Zweig breadth thrust fired recently (bool|None)

    Returns:
        dict with keys:
          label        : str — 'narrow_leadership' | 'broad_thrust' | 'mixed'
          chips        : dict of per-axis bool|None chips
          conditions   : str — plain-English conditions that triggered the label
    """
    chips: dict[str, bool | None] = {
        "dispersion_high": None,
        "corr_low": None,
        "pct_above_200_low": None,
        "top5_share_low": None,
        "zweig_thrust": None,
    }

    if not _is_null(dispersion_pctile):
        chips["dispersion_high"] = bool(float(dispersion_pctile) >= REGIME_NARROW_DISPERSION * 100)
    if not _is_null(avg_corr):
        chips["corr_low"] = bool(float(avg_corr) <= REGIME_NARROW_AVG_CORR)
    if not _is_null(pct_above_200):
        chips["pct_above_200_low"] = bool(float(pct_above_200) < REGIME_NARROW_PCT_ABOVE_200)
        chips["pct_above_200_high"] = bool(float(pct_above_200) >= REGIME_THRUST_PCT_ABOVE_200)
    if not _is_null(top5_share_21d):
        chips["top5_share_low"] = bool(float(top5_share_21d) < REGIME_THRUST_TOP5_SHARE)
    if not _is_null(zweig_flag):
        chips["zweig_thrust"] = bool(zweig_flag)

    # Narrow leadership: dispersion >= 70th pctile AND avg_corr <= 0.15 AND pct_above_200 < 55
    narrow_conditions = []
    narrow_met = True
    if chips["dispersion_high"] is True:
        narrow_conditions.append(f"dispersion≥70th")
    elif chips["dispersion_high"] is False:
        narrow_met = False
    if chips["corr_low"] is True:
        narrow_conditions.append(f"avg_corr≤{REGIME_NARROW_AVG_CORR}")
    elif chips["corr_low"] is False:
        narrow_met = False
    if chips["pct_above_200_low"] is True:
        narrow_conditions.append(f"pct_above_200<{REGIME_NARROW_PCT_ABOVE_200}%")
    elif chips["pct_above_200_low"] is False:
        narrow_met = False
    # Only label narrow if all three non-null chips are True
    any_null_narrow = any(
        chips[k] is None for k in ("dispersion_high", "corr_low", "pct_above_200_low")
    )

    # Broad thrust: zweig OR (pct_above_200 >= 70 AND top5_share < 0.35)
    thrust_met = False
    thrust_conditions = []
    if chips["zweig_thrust"] is True:
        thrust_met = True
        thrust_conditions.append("Zweig breadth thrust")
    pct_high = chips.get("pct_above_200_high")
    top5_low = chips["top5_share_low"]
    if pct_high is True and top5_low is True:
        thrust_met = True
        thrust_conditions.append(f"pct_above_200≥{REGIME_THRUST_PCT_ABOVE_200}%+top5_share<{REGIME_THRUST_TOP5_SHARE}")

    # Apply label
    if narrow_met and not any_null_narrow:
        label = "narrow_leadership"
        conditions = " AND ".join(narrow_conditions) if narrow_conditions else "all narrow conditions met"
    elif thrust_met:
        label = "broad_thrust"
        conditions = " OR ".join(thrust_conditions)
    else:
        label = "mixed"
        conditions = "neither narrow_leadership nor broad_thrust conditions fully met"

    return {
        "label": label,
        "chips": chips,
        "conditions": conditions,
    }


# ── State machine helpers ─────────────────────────────────────────────────────

def _k_of_n(chips: dict[str, bool | None], chip_keys: list[str], k: int) -> bool:
    """K-of-N tri-state count: null excluded from BOTH numerator and denominator.

    If n_avail < k: unreachable → returns False (falls through, never fake-qualified).
    """
    n_true = 0
    n_avail = 0
    for key in chip_keys:
        v = chips.get(key)
        if not _is_null(v):
            n_avail += 1
            if v is True:
                n_true += 1
    if n_avail < k:
        return False  # unreachable state: not enough non-null chips
    return n_true >= k


def _suppressed_check(inp: LifecycleInputs, rs: pd.Series) -> tuple[bool | None, dict]:
    """Return (suppressed_bool_or_None, evidence_chips) for SUPPRESSED state."""
    chips: dict[str, bool | None] = {}

    # RS-vs-SPY 63d slope < 0 for ≥ 3 months (≥ ~63 consecutive trading days)
    # We check: 63d slope is negative at the last bar AND has been for ~3 months
    if len(rs) >= RS_63D_WINDOW:
        slope_63_series = rs_slope(rs, RS_63D_WINDOW)
        if len(slope_63_series) >= RS_63D_WINDOW:
            # Check that the slope has been negative for the last ~63 bars
            recent_slopes = slope_63_series.dropna().iloc[-RS_63D_WINDOW:]
            if len(recent_slopes) >= RS_63D_WINDOW // 2:
                chips["rs_slope_negative_3m"] = bool((recent_slopes < 0).all())
            else:
                chips["rs_slope_negative_3m"] = None
        else:
            chips["rs_slope_negative_3m"] = None
    else:
        chips["rs_slope_negative_3m"] = None

    # Drawdown from 252d high ≥ 25%
    close = inp.close
    if len(close) >= 63:
        high_252 = close.rolling(252, min_periods=63).max()
        last_high = high_252.iloc[-1]
        last_close = close.iloc[-1]
        if np.isfinite(float(last_high)) and float(last_high) > 0:
            dd_pct = (float(last_close) / float(last_high) - 1.0) * 100.0
            chips["drawdown_25pct"] = bool(dd_pct <= -SUPPRESSED_DRAWDOWN_PCT)
        else:
            chips["drawdown_25pct"] = None

        # Alt: ≥ 12 months (252td) below 200dma
        sma200 = close.rolling(200, min_periods=100).mean()
        if len(close) >= 252:
            below_200 = (close.iloc[-252:] < sma200.iloc[-252:])
            chips["below_200dma_12m"] = bool(below_200.sum() >= 200)
        else:
            chips["below_200dma_12m"] = None
    else:
        chips["drawdown_25pct"] = None
        chips["below_200dma_12m"] = None

    # Valuation cheap_pctile ≤ 40 (null-tolerant)
    if not _is_null(inp.cheap_pctile):
        chips["cheap_pctile_40"] = bool(float(inp.cheap_pctile) <= SUPPRESSED_CHEAP_PCTILE)
    else:
        chips["cheap_pctile_40"] = None

    # State: RS negative 3m AND (drawdown >= 25% OR below_200dma_12m) AND valuation cheap (null-tolerant)
    rs_neg = chips["rs_slope_negative_3m"]
    dd_check = _or3(chips["drawdown_25pct"], chips["below_200dma_12m"])
    val_check = chips["cheap_pctile_40"]  # null-tolerant: None treated as not-blocking

    if rs_neg is None or dd_check is None:
        state = None
    elif rs_neg is False or dd_check is False:
        state = False
    else:
        # RS negative AND price oversold; valuation is null-tolerant (doesn't block)
        state = True

    return state, chips


def _quiet_accum_check(inp: LifecycleInputs, rs: pd.Series) -> tuple[bool, dict, int]:
    """Return (qa_bool, evidence_chips, n_avail) for QUIET_ACCUMULATION."""
    chips: dict[str, bool | None] = {}

    # Context: SUPPRESSED within last 6 months OR 60d base range compression ≤ 25%
    close = inp.close
    # Base compression: (max - min) / min over last 60 days
    base_context: bool | None = None
    if len(close) >= QA_BASE_RANGE_DAYS // 2:
        win = close.iloc[-QA_BASE_RANGE_DAYS:]
        w_min = win.min()
        w_max = win.max()
        if np.isfinite(float(w_min)) and float(w_min) > 0:
            range_pct = (float(w_max) / float(w_min) - 1.0) * 100.0
            base_context = bool(range_pct <= QA_BASE_RANGE_WIDTH)
    # We also check SUPPRESSED-context (passed in via state_history)
    suppressed_recent = False
    for dt, st in inp.state_history[-QA_SUPPRESSED_LOOKBACK_SESSIONS:]:
        if st == STATE_SUPPRESSED:
            suppressed_recent = True
            break
    chips["context_ok"] = bool(suppressed_recent or (base_context is True))

    # Chip 1: revision_positive (LEVEL: net_up_30d > 0 AND est_chg_30d > 0)
    # Named revision_positive per LR-R2 (level, not 'turn'; renames to revision_turn at Q4-26)
    if not _is_null(inp.net_up_30d) and not _is_null(inp.est_chg_30d):
        chips["revision_positive"] = bool(float(inp.net_up_30d) > 0 and float(inp.est_chg_30d) > 0)
    else:
        chips["revision_positive"] = None

    # Chip 2: rs_turn (21d slope > 0 while 63d slope <= 0)
    chips["rs_turn"] = rs_turn(rs)

    # Chip 3: accum_evidence
    ohlcv = None
    if inp.volume is not None and inp.high is not None:
        # Build OHLCV frame
        ohlcv_parts = {"close": inp.close}
        if inp.volume is not None:
            ohlcv_parts["volume"] = inp.volume
        if inp.high is not None:
            ohlcv_parts["high"] = inp.high
        if inp.low is not None:
            ohlcv_parts["low"] = inp.low
        ohlcv = pd.DataFrame(ohlcv_parts)
    elif inp.volume is not None:
        ohlcv = pd.DataFrame({"close": inp.close, "volume": inp.volume})

    if ohlcv is not None and "volume" in ohlcv.columns:
        ratio = updown_volume_ratio(ohlcv, UPDOWN_VOL_WINDOW)
        n_accum, n_dist = accumulation_distribution_days(ohlcv, ACCUM_DIST_WINDOW)
        pp = pocket_pivot(ohlcv)
        ratio_ok = (ratio is not None and ratio >= UPDOWN_VOL_RATIO_MIN)
        dist_ok = (n_accum is not None and n_dist is not None and
                   n_accum >= n_dist + ACCUM_OVER_DIST_MARGIN)
        pp_ok = (pp is True)
        chips["accum_evidence"] = bool(ratio_ok or dist_ok or pp_ok)
    else:
        chips["accum_evidence"] = None

    # Chip 4: obv_divergence
    if inp.volume is not None:
        chips["obv_divergence"] = obv_divergence(inp.close, inp.volume, OBV_DIVERGENCE_WINDOW)
    else:
        chips["obv_divergence"] = None

    # Chip 5: insider_cluster (altdata context chip)
    chips["insider_cluster"] = inp.insider_cluster

    # K-of-N: ≥2 of 5 chips (excluding context_ok which is a prerequisite, not a chip)
    qa_chip_keys = ["revision_positive", "rs_turn", "accum_evidence", "obv_divergence", "insider_cluster"]
    n_true = 0
    n_avail = 0
    for key in qa_chip_keys:
        v = chips.get(key)
        if not _is_null(v):
            n_avail += 1
            if v is True:
                n_true += 1

    # Context must be True; K-of-N must be met
    if not chips.get("context_ok"):
        qa = False
    elif n_avail < QA_K_OF_N:
        qa = False  # unreachable (insufficient non-null chips)
    else:
        qa = n_true >= QA_K_OF_N

    return qa, chips, n_avail


def _catalyst_window_check(inp: LifecycleInputs, rs: pd.Series) -> tuple[bool, dict]:
    """Return (cw_bool, evidence_chips) for CATALYST_WINDOW."""
    chips: dict[str, bool | None] = {}

    # Context: QUIET_ACCUMULATION current or ≤ 21 sessions ago
    qa_recent = False
    for dt, st in inp.state_history[-(QA_RECENCY_SESSIONS + 1):]:
        if st in (STATE_QUIET_ACCUMULATION, STATE_CATALYST_WINDOW):
            qa_recent = True
            break

    # Also if currently in QA (would be set as context)
    chips["qa_context"] = bool(qa_recent)

    # Ignition triggers (any one of three)
    # 1: Gap ≥ 5% on ≥ 2× 20d volume (need OHLCV)
    gap_trigger: bool | None = None
    close = inp.close
    if inp.volume is not None and len(close) >= 21:
        ohlcv = pd.DataFrame({"close": close, "volume": inp.volume})
        # Check last CATALYST_TRIGGER_SESSIONS sessions for a gap day
        recent = ohlcv.tail(CATALYST_TRIGGER_SESSIONS + 1)
        avg_vol_20 = inp.volume.tail(20).mean() if len(inp.volume) >= 20 else None
        gap_days = 0
        if avg_vol_20 and avg_vol_20 > 0:
            for i in range(1, len(recent)):
                gap_pct = (float(recent["close"].iloc[i]) / float(recent["close"].iloc[i - 1]) - 1.0) * 100.0
                vol_ratio = float(recent["volume"].iloc[i]) / float(avg_vol_20)
                if gap_pct >= CATALYST_GAP_PCT and vol_ratio >= CATALYST_VOL_MULT:
                    gap_days += 1
            gap_trigger = bool(gap_days > 0)

    # 2: breakaway_watch = 'emerging'
    bw_emerging: bool | None = None
    if inp.breakaway_watch_state is not None:
        bw_emerging = bool(inp.breakaway_watch_state == "emerging")

    # 3: RS-line 126d new high while price below its own 126d high
    rs_nh: bool | None = rs_line_new_high(rs, inp.close, RS_LINE_NH_LOOKBACK)

    chips["gap_ignition"] = gap_trigger
    chips["bw_emerging"] = bw_emerging
    chips["rs_line_nh"] = rs_nh

    ignition = _or3(gap_trigger, bw_emerging, rs_nh)

    # CATALYST_WINDOW = context AND ignition
    if not chips.get("qa_context"):
        cw = False
    elif ignition is None:
        cw = False  # no ignition observed
    else:
        cw = bool(ignition)

    return cw, chips


def _crowded_check(inp: LifecycleInputs) -> tuple[bool, dict, int]:
    """Return (crowded_bool, evidence_chips, n_avail) for CROWDED state."""
    chips: dict[str, bool | None] = {}

    # Chip 1: extension vs 50dma ≥ 25% or own-history ≥ 90th pctile
    ext_pct = extension_vs_50dma(inp.close)
    ext_pctile = extension_pctile_own_history(inp.close)
    if ext_pct is not None or ext_pctile is not None:
        e1 = (ext_pct is not None and ext_pct >= CROWDED_EXTENSION_PCT)
        e2 = (ext_pctile is not None and ext_pctile >= CROWDED_EXTENSION_OWN_PCTILE)
        chips["extension_extreme"] = bool(e1 or e2)
    else:
        chips["extension_extreme"] = None

    # Chip 2: monthly RSI ≥ 80
    mrsi = monthly_rsi(inp.close)
    if mrsi is not None:
        chips["monthly_rsi_80"] = bool(mrsi >= CROWDED_MONTHLY_RSI)
    else:
        chips["monthly_rsi_80"] = None

    # Chip 3: parabolic flag
    chips["parabolic"] = parabolic_flag(inp.close)

    # Chip 4: valuation ≥ 80th pctile own 5y history
    if not _is_null(inp.valuation_pctile_5y):
        chips["valuation_extreme"] = bool(float(inp.valuation_pctile_5y) >= 80.0)
    else:
        chips["valuation_extreme"] = None

    # Chip 5: analyst buy-share ≥ 85%
    if not _is_null(inp.analyst_buy_pct):
        chips["analyst_saturated"] = bool(float(inp.analyst_buy_pct) >= CROWDED_ANALYST_BUY_PCT)
    else:
        chips["analyst_saturated"] = None

    # Chip 6: call-skew richness (rr_25d ≥ own 80th pctile where gex present)
    if not _is_null(inp.rr_25d) and not _is_null(inp.rr_80th_pctile):
        chips["call_skew_rich"] = bool(float(inp.rr_25d) >= float(inp.rr_80th_pctile))
    else:
        chips["call_skew_rich"] = None

    # Chip 7: basket correlation ≥ 0.75 having risen from < 0.5
    chips["basket_corr_rising"] = basket_correlation_rising(
        inp.basket_corr_now, inp.basket_corr_then
    )

    crowded_chip_keys = [
        "extension_extreme", "monthly_rsi_80", "parabolic",
        "valuation_extreme", "analyst_saturated", "call_skew_rich",
        "basket_corr_rising",
    ]
    n_true = 0
    n_avail = 0
    for key in crowded_chip_keys:
        v = chips.get(key)
        if not _is_null(v):
            n_avail += 1
            if v is True:
                n_true += 1

    if n_avail < CROWDED_K_OF_N:
        crowded = False
    else:
        crowded = n_true >= CROWDED_K_OF_N

    return crowded, chips, n_avail


# ── State machine: classify() ─────────────────────────────────────────────────

def classify(inp: LifecycleInputs) -> LifecycleAssessment:
    """Classify a name into exactly one lifecycle state.

    Returns the RAW state (before hysteresis). Call apply_hysteresis() separately.
    Implements the frozen precedence cascade per LR-R2:
      FAILED-override > CROWDED > LEADERSHIP > BREAKAWAY > CATALYST_WINDOW
      > QUIET_ACCUMULATION > SUPPRESSED > NONE

    BREAKAWAY/LEADERSHIP state derivation:
      - 'breakaway' (only) from winner_autopsy → BREAKAWAY context
      - 'emerging' from winner_autopsy → CATALYST_WINDOW ignition trigger (bw_emerging chip)
      - 'continuation' with RS top-decile ≥ 4 weeks + concentration chip → LEADERSHIP
      - 'failed' from winner_autopsy → FAILED
    """
    # Pre-compute RS series (used across multiple checks)
    rs = rs_series(inp.close, inp.bench_close)
    all_evidence: dict[str, bool | None] = {}
    n_avail = 0
    de_escalation_chips: dict[str, bool | None] = {}

    # ── 1. FAILED override (highest precedence) ───────────────────────────────
    if inp.breakaway_watch_state == "failed":
        return LifecycleAssessment(
            state=STATE_FAILED,
            evidence={"bw_failed": True},
            n_avail=1,
            days_in_state=inp.days_in_state,
            de_escalation_chips={},
        )

    # ── 2. CROWDED ────────────────────────────────────────────────────────────
    crowded_ok, crowded_chips, crowded_n = _crowded_check(inp)
    all_evidence.update(crowded_chips)

    # ── 3. LEADERSHIP ─────────────────────────────────────────────────────────
    # 'continuation' + RS top-decile ≥ 4 weeks + concentration chip
    leadership_ok = False
    leadership_chips: dict[str, bool | None] = {}
    if inp.breakaway_watch_state == "continuation":
        weeks = rs_top_decile_weeks(inp.rs_rank_history)
        leadership_chips["bw_continuation"] = True
        leadership_chips["rs_top_decile_4w"] = (
            bool(weeks >= RS_TOP_DECILE_WEEKS_MIN) if weeks is not None else None
        )
        # Compute leader RS accel for peer_divergence
        if len(rs) >= RS_63D_WINDOW:
            slope_63 = rs_slope(rs, RS_63D_WINDOW)
            rs_accel = slope_63.iloc[-1] if len(slope_63) > 0 else None
            if isinstance(rs_accel, float) and not np.isfinite(rs_accel):
                rs_accel = None
        else:
            rs_accel = None
        conc = peer_divergence(rs_accel, inp.peer_median_rs_63d)
        leadership_chips["peer_divergence"] = conc
        # Leadership requires: continuation state AND (rs_top_decile ≥ 4w) AND concentration chip
        top_decile_ok = leadership_chips["rs_top_decile_4w"]
        if top_decile_ok is True and conc is True:
            leadership_ok = True
        elif top_decile_ok is True and conc is None:
            # Null concentration chip: null-tolerant per house tri-state law (chip displayed
            # as null on radar row; LEADERSHIP still fires — concentration is bonus context,
            # not a gate). LR-R2 / CLAUDE.md "null never counts as False".
            leadership_ok = True
    all_evidence.update(leadership_chips)

    # ── 4. BREAKAWAY ──────────────────────────────────────────────────────────
    # Only 'breakaway' maps to BREAKAWAY state; 'emerging' is CATALYST_WINDOW ignition
    # only (bw_emerging chip in _catalyst_window_check). LR-R2.
    breakaway_ok = False
    if inp.breakaway_watch_state == "breakaway":
        breakaway_ok = True
        all_evidence["bw_breakaway"] = True
    # Also: continuation without full leadership qualifiers = BREAKAWAY
    if inp.breakaway_watch_state == "continuation" and not leadership_ok:
        breakaway_ok = True
        all_evidence["bw_continuation_pre_leadership"] = True

    # ── 5. CATALYST_WINDOW ───────────────────────────────────────────────────
    cw_ok, cw_chips = _catalyst_window_check(inp, rs)
    all_evidence.update(cw_chips)

    # ── 6. QUIET_ACCUMULATION ────────────────────────────────────────────────
    qa_ok, qa_chips, qa_n = _quiet_accum_check(inp, rs)
    all_evidence.update(qa_chips)

    # ── 7. SUPPRESSED ────────────────────────────────────────────────────────
    suppressed_val, supp_chips = _suppressed_check(inp, rs)
    all_evidence.update(supp_chips)
    suppressed_ok = suppressed_val is True

    # ── De-escalation chips (always computed; printed on page) ────────────────
    if not _is_null(inp.cheap_pctile):
        de_escalation_chips["cheap_pctile_40"] = bool(float(inp.cheap_pctile) <= SUPPRESSED_CHEAP_PCTILE)
    if not _is_null(inp.earnings_within_14d):
        de_escalation_chips["earnings_within_14d"] = bool(inp.earnings_within_14d)

    # ── Precedence cascade — n_avail comes from the WINNING state's own chip set ──
    # This ensures the radar row shows the K-of-N count relevant to the displayed state.
    if crowded_ok:
        final_state = STATE_CROWDED
        n_avail = crowded_n   # crowded_n from _crowded_check
    elif leadership_ok:
        final_state = STATE_LEADERSHIP
        n_avail = 0           # leadership has no K-of-N threshold (threshold-based axes)
    elif breakaway_ok:
        final_state = STATE_BREAKAWAY
        n_avail = 0           # breakaway is a binary WA state flag
    elif cw_ok:
        final_state = STATE_CATALYST_WINDOW
        n_avail = 0           # CW has no K-of-N (context + any ignition trigger)
    elif qa_ok:
        final_state = STATE_QUIET_ACCUMULATION
        n_avail = qa_n        # qa_n from _quiet_accum_check
    elif suppressed_ok:
        final_state = STATE_SUPPRESSED
        n_avail = 0           # suppressed has no K-of-N
    else:
        final_state = STATE_NONE
        n_avail = 0

    return LifecycleAssessment(
        state=final_state,
        evidence=all_evidence,
        n_avail=n_avail,
        days_in_state=inp.days_in_state,
        de_escalation_chips=de_escalation_chips,
    )


# ── Hysteresis (LR-R2) ────────────────────────────────────────────────────────

def apply_hysteresis(
    raw_state_today: str,
    raw_state_history: list[tuple[date, str]],
    confirmed_state_history: list[tuple[date, str]],
    enter_n: int = HYSTERESIS_ENTER_N,
    exit_n: int = HYSTERESIS_EXIT_N,
) -> str:
    """Apply 2-consecutive-to-enter / 3-consecutive-to-exit hysteresis.

    BREAKAWAY/LEADERSHIP/FAILED pass through winner_autopsy semantics (their
    hysteresis is governed by Detector-D, not this function). This function
    applies to the pre-onset states: SUPPRESSED, QUIET_ACCUMULATION,
    CATALYST_WINDOW, CROWDED, NONE.

    The function uses SEPARATE raw and confirmed history lists (W2a builder
    contract — see module docstring). Entry is counted in RAW history; exit is
    counted in RAW history against the current CONFIRMED state. Context lookups
    and days_in_state anchoring in classify() consume CONFIRMED history only.

    Args:
        raw_state_today: the raw state from classify() for today
        raw_state_history: list of (date, raw_state) tuples, newest last.
            Entry requires last (enter_n - 1) raw states == raw_state_today.
        confirmed_state_history: list of (date, confirmed_state) tuples, newest last.
            Used to determine the currently held confirmed state.
            Exit requires exit_n consecutive raw sessions not matching confirmed state.
        enter_n: consecutive raw sessions required to enter a new state (default 2)
        exit_n: consecutive raw sessions required to exit a confirmed state (default 3)

    Returns:
        Post-hysteresis (confirmed) state string.
    """
    # WA states pass through: hysteresis is governed by Detector-D for these
    if raw_state_today in (STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_FAILED):
        return raw_state_today

    # No confirmed history yet — accept raw state directly
    if not confirmed_state_history:
        return raw_state_today

    # Current held (confirmed) state = last entry in confirmed history
    held_state = confirmed_state_history[-1][1]

    # If WA states are currently confirmed, release immediately on any non-WA raw signal
    # (WA exit is governed by winner_autopsy, not this function)
    if held_state in (STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_FAILED):
        return raw_state_today

    if raw_state_today == held_state:
        # Same state: maintain confirmed state
        return held_state

    # raw_state_today != held_state: we need to decide whether to transition.
    #
    # Two regimes:
    # A) held_state == NONE (or the first-ever entry into a real state):
    #    Use ENTRY rule — need enter_n consecutive raw sessions of raw_state_today
    #    (last enter_n-1 raw sessions == raw_state_today, plus today = enter_n total).
    # B) held_state is a real non-NONE state:
    #    Use EXIT rule — need exit_n consecutive non-held raw sessions including today
    #    (last exit_n-1 raw sessions all != held_state, plus today = exit_n total).
    #
    # This prevents the entry check from short-circuiting the exit requirement when
    # you've accumulated only 1-2 prior raw sessions of a new state while still holding
    # a confirmed real state.

    if held_state == STATE_NONE:
        # ── Entry check (from NONE / no prior state) ─────────────────────────
        # Entering raw_state_today requires it appeared in the last (enter_n - 1) raw sessions
        prior_raw = [s for _, s in raw_state_history[-(enter_n - 1):]]
        if len(prior_raw) >= enter_n - 1 and all(s == raw_state_today for s in prior_raw):
            return raw_state_today
        # Entry threshold not met: stay in NONE
        return held_state
    else:
        # ── Exit check (from a real confirmed state) ──────────────────────────
        # Exit held_state when exit_n consecutive raw sessions were all NOT held_state.
        # (today + exit_n-1 prior raw sessions all != held_state)
        if len(raw_state_history) >= exit_n - 1:
            prior_raw_for_exit = [s for _, s in raw_state_history[-(exit_n - 1):]]
            if all(s != held_state for s in prior_raw_for_exit):
                return raw_state_today  # exit threshold met
        # Exit threshold not met: stay in held confirmed state
        return held_state


# ── Fire rules (LR-R8) ───────────────────────────────────────────────────────

def precipice_fire(
    assessment_today: LifecycleAssessment,
    assessment_history: list[LifecycleAssessment],
) -> bool:
    """Precipice fire: entering CATALYST_WINDOW (post-hysteresis) AND
    (revision_positive is True OR rs_line_nh is True).

    The OR-leg keeps revision-uncovered names eligible (LR-R8).
    """
    if assessment_today.state != STATE_CATALYST_WINDOW:
        return False
    # Must be an entry (prior state was not CATALYST_WINDOW)
    if assessment_history and assessment_history[-1].state == STATE_CATALYST_WINDOW:
        return False
    # Check OR-leg
    ev = assessment_today.evidence
    rev_pos = ev.get("revision_positive")
    rs_nh = ev.get("rs_line_nh")
    return bool(rev_pos is True or rs_nh is True)


def onset_fire(
    assessment_today: LifecycleAssessment,
    assessment_history: list[LifecycleAssessment],
) -> bool:
    """Onset fire: entering BREAKAWAY state (Detector-D onset)."""
    if assessment_today.state != STATE_BREAKAWAY:
        return False
    # Must be an entry
    if assessment_history and assessment_history[-1].state == STATE_BREAKAWAY:
        return False
    return True


def eligible_for_refire(
    state_history: list[tuple[date, str]],
    last_fire_date: date | None,
    lockout_sessions: int = REFIRE_LOCKOUT_SESSIONS,
) -> bool:
    """Refire eligibility: lockout = 21 sessions AND full de-escalation to NONE/FAILED.

    Enforcement of the lockout period lives in the W2a builder/pick-lab layer;
    this function exposes the eligibility check as a pure predicate.

    Args:
        state_history: (date, state) pairs, newest last
        last_fire_date: date of last fire (None if never fired)
        lockout_sessions: minimum sessions since last fire (default 21)

    Returns:
        True if eligible to refire, False otherwise.
    """
    if last_fire_date is None:
        return True
    if not state_history:
        return False

    # Count sessions since last fire
    fire_idx = None
    for i, (dt, _) in enumerate(state_history):
        if dt == last_fire_date:
            fire_idx = i
            break
    if fire_idx is None:
        # fire_date not in history; use date comparison
        sessions_since = sum(1 for dt, _ in state_history if dt > last_fire_date)
    else:
        sessions_since = len(state_history) - 1 - fire_idx

    if sessions_since < lockout_sessions:
        return False

    # Require full de-escalation to NONE or FAILED since last fire
    # Use enumerate positions (O(n)) instead of .index() which is O(n²) on a list of tuples
    since_fire = [
        st for pos, (dt, st) in enumerate(state_history)
        if (fire_idx is None and dt > last_fire_date)
        or (fire_idx is not None and pos > fire_idx)
    ]
    return any(s in (STATE_NONE, STATE_FAILED) for s in since_fire)


# ── Handoff watch (LR-R4) ────────────────────────────────────────────────────

def extended_leg(
    basket_ew_close: pd.Series,
    bench_close: pd.Series,
    extension_pctile_threshold: float = EXTENDED_LEG_PCTILE,
) -> bool | None:
    """Extended-leg detector: basket EW return ≥ 90th pctile vs own 200d trend
    AND basket RS 21d rolling over.

    Args:
        basket_ew_close: equal-weight basket close series (DatetimeIndex)
        bench_close: benchmark close (for RS)
        extension_pctile_threshold: percentile threshold (default 90)

    Returns:
        True if extended, False if not, None if insufficient data.
    """
    if basket_ew_close is None or len(basket_ew_close) < 63:
        return None

    # Extension: current price vs 200d trend (own history percentile)
    sma200 = basket_ew_close.rolling(200, min_periods=100).mean()
    # Use pd.isna() + isfinite; numpy floats are never `is None` (dead guard)
    if pd.isna(sma200.iloc[-1]) or not np.isfinite(float(sma200.iloc[-1])):
        return None
    ext_pct = (float(basket_ew_close.iloc[-1]) / float(sma200.iloc[-1]) - 1.0) * 100.0
    # Own history percentile of extension
    ext_series = (basket_ew_close / sma200.replace(0, np.nan) - 1.0) * 100.0
    ext_clean = ext_series.dropna()
    if len(ext_clean) < 50:
        return None
    pctile = float((ext_clean < ext_pct).mean() * 100.0)
    if pctile < extension_pctile_threshold:
        return False

    # RS 21d rolling over (slope of RS turning negative)
    rs = rs_series(basket_ew_close, bench_close)
    if len(rs) < 42:
        return None
    slope_21_series = rs_slope(rs, RS_21D_WINDOW)
    if len(slope_21_series.dropna()) < 2:
        return None
    # "Rolling over" = 21d slope currently negative
    last_slope = slope_21_series.dropna().iloc[-1]
    if not np.isfinite(float(last_slope)):
        return None
    rs_rolling_over = bool(float(last_slope) < 0)

    return bool(pctile >= extension_pctile_threshold and rs_rolling_over)


def basing_leg(
    assessment: LifecycleAssessment,
    d_or_2d_macd_state: dict | None,
) -> bool | None:
    """Basing-leg detector: name in pre-breakaway state with MACD cross/approaching.

    Args:
        assessment: LifecycleAssessment for the candidate name
        d_or_2d_macd_state: dict from _tf_state (D or 2D timeframe)

    Returns:
        True if basing candidate, False if not, None if insufficient data.
    """
    pre_breakaway_states = {STATE_SUPPRESSED, STATE_QUIET_ACCUMULATION, STATE_CATALYST_WINDOW}
    if assessment.state not in pre_breakaway_states:
        return False

    if d_or_2d_macd_state is None or not d_or_2d_macd_state:
        return None

    # MACD cross up or approaching cross up
    macd_signal = bool(
        d_or_2d_macd_state.get("macd_cross_up") or
        d_or_2d_macd_state.get("macd_approaching_up") or
        d_or_2d_macd_state.get("macd_curl_up")
    )
    return macd_signal


def handoff_pairs(
    extended_baskets: dict[str, bool | None],
    candidate_assessments: dict[str, LifecycleAssessment],
    membership: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Generate handoff watch pairs (extended basket × basing candidate).

    Uses VOCABULARY: extended_leg/basing_leg only (never donor/recipient/routing).

    Args:
        extended_baskets: {basket_name: True/False/None} — output of extended_leg()
        candidate_assessments: {ticker: LifecycleAssessment}
        membership: {basket_name: [ticker, ...]} — basket membership

    Returns:
        list of dicts with keys: basket, ticker, basket_state, name_state, evidence
    """
    pairs: list[dict[str, Any]] = []
    for basket, is_ext in extended_baskets.items():
        if not is_ext:
            continue
        members = membership.get(basket, [])
        for ticker in members:
            assessment = candidate_assessments.get(ticker)
            if assessment is None:
                continue
            if assessment.state in (STATE_SUPPRESSED, STATE_QUIET_ACCUMULATION,
                                    STATE_CATALYST_WINDOW):
                pairs.append({
                    "basket": basket,
                    "ticker": ticker,
                    "extended_leg_basket": basket,
                    "basing_leg_ticker": ticker,
                    "name_state": assessment.state,
                    "evidence": assessment.evidence,
                })
    return pairs
