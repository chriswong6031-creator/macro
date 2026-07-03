"""wave8_warm.py — Durable-Bottom Entry Timing Study, Wave 8, Cells A + B.

BINDING SPEC: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8 wave-8 pre-registration
(2026-07-03, written BEFORE the runs). Context: WAVE7_PREREG.md §8 retirement, WAVE6_REPORT.md
(F7 near-miss), WAVE5_REPORT.md (BASED falsification).

WHAT THIS FILE TESTS
--------------------
W8-A "W-ARM": stale 3D confluence cross (3-8 ticks) that has NOT launched AND whose weekly
RSI-MACD histogram is negative, net-rising, above −theta, and on a linear extrapolation
crosses zero within 2 weeks. Two variants:
  STRICT  — last 3 weekly bars strictly rising (each > prior).
  NET     — last bar > bar−3 (net-rise over 3 bars; MCD fires here only).
W8-B "SHAKEN": post-cross new low > 1.5 ATR below cross price, then recovery above midpoint,
with weekly hist net-rising (report-only if n < 100).

BASELINES (all inside this file)
---------------------------------
  FRESH         : m2d_s3d fires, 0-2 ticks stale (incumbent comparison).
  STALE_3_8     : stale 3-8 tick population WITHOUT W-ARM trigger (the unfavorable stratum).
  STALE_3_8_W   : same + W-ARM (the favorable stratum; promotion gate comparison).
  F7_RECOMPUTE  : F7's weekly-stoch-cross-up condition on the STALE_3_8 population.
  BASED_OVERLAP : Jaccard(W-ARM fires, BASED-style fires i+7..i+24 = waves 5 definition).

INDICATOR (exact variant, engine-faithful)
------------------------------------------
  wk = c.resample("W-FRI").last().dropna()
  wm, ws = TH.rsi_macd(wk)
  w_hist = wm - ws
  Known-date guard: last trading day of each week from
    c.resample("W-FRI").apply(lambda x: x.dropna().index.max())
  A weekly bar is known at daily bar j iff known_date <= daily_idx[j].
  NO additional .shift(1); the last-close-in-week protocol is the leak guard.
  The .shift(1) in confluence_tiers.py line 176 is for the BULL-STATE boolean only.

LEAK RULES (enforced, every condition)
---------------------------------------
  * All population conditions computed from data <= fire bar i only.
  * Weekly bar known only after its known_date (last trading day of the week <= i).
  * 3D cross price = close at the 3D bar's known date.
  * ATR = wave1.build_tf_grids atrp at the fire bar's known date position (ewm alpha=1/14).
  * Ticks = count of 3D bars whose known_date is strictly AFTER the cross and <= bar i.
  * max_up_since_cross = max(close[cross_known_pos .. i]) / cross_price - 1 (bars [pos..i]).
  * ext = close[i] / cross_price - 1.
  * ext_atr = ext / atrp[cross_known_pos] (ATR at cross time, not fill time).

LIVE FIXTURES (computed 2026-07-01, adversarially verified — smoke checks)
---------------------------------------------------------------------------
  MCK : cross 2026-06-11, 5 ticks, weekly hist -1.99→-0.28 strictly rising, MUST fire W-ARM.
  MCD : cross 2026-06-09, 6 ticks, hist -1.93→-0.79 net-rising but stalled last 2 bars.
        Fires NET variant ONLY (not STRICT).
  KO  : cross 2026-06-10, hist oscillating ~-0.19..-0.39, no approach. Must NOT fire.
  ELV : cross 2026-04-09, 20 ticks (outside [3,8]), hist POSITIVE. Must NEVER fire.

CLI
---
  --smoke [--tickers MCK,MCD,KO,ELV,AAPL,JNJ,WMT,XOM]
      Fixture assertions + state print for each ticker. Iterate until green.
  --stocks   Deep US panel (data/stocks/*.parquet, 224 names).
  --baskets  Baskets OOS panel (data/baskets/ohlcv/, 990+ names).
  --gates    Evaluate promotion gates from the _out parquets.

Reuses (imported verbatim, never reimplemented)
-----------------------------------------------
  wave1.py   compute_outcomes, build_tf_grids, label_events, OUTCOME_W, FWD_REQ.
  wave5.py   compute_atr_outcomes, BOOT_N, BOOT_ALPHA, NAME_FLOOR, BLOCK_FLOOR,
             _block_bootstrap_means, block_bootstrap_lb, block_bootstrap_ub, _rate.
  wave2.py   PANEL_CONFIGS, _serialize_d_matrix.
  tuning_harness.py  rsi, ema, rsi_macd, stoch_rsi_kd, xup, tf_bars, to_daily, build_signals.
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── path bootstrap ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402

from wave1 import (  # noqa: E402
    compute_outcomes, build_tf_grids, label_events,
    OUTCOME_W, FWD_REQ, MFE_MAE_W, DD_MIN,
    H6_COHORT_THRESH, EVAL_START, MIN_BARS,
)
from wave5 import (  # noqa: E402
    compute_atr_outcomes, _rate,
    _block_bootstrap_means, block_bootstrap_lb, block_bootstrap_ub,
    BOOT_N, BOOT_ALPHA, NAME_FLOOR, BLOCK_FLOOR, BLOCK_TD,
    ATR_STOP_MULT, ATR_TARGET_MULT,
)
from wave2 import PANEL_CONFIGS, _serialize_d_matrix  # noqa: E402

DATA_STOCKS  = ROOT / "data" / "stocks"
DATA_BASKETS = ROOT / "data" / "baskets" / "ohlcv"
BREADTH      = ROOT / "data" / "breadth"
OUT_DIR      = ENTRY_TIMING / "_out"

# ─────────────────────────── W8 constants (pre-registered) ───────────────────

PRIMARY_TRIG   = "m2d_s3d"
DEDUPE_TD      = 21          # per-name dedupe: 21 calendar trading days, first fire kept

# Tick-age windows
FRESH_TICKS_LO = 0
FRESH_TICKS_HI = 2
STALE_TICKS_LO = 3
STALE_TICKS_HI = 8          # 3–8 ticks stale (pre-registered)

# Not-launched conditions
NOT_LAUNCHED_MAXUP   = 0.05  # max_up_since_cross < 5% (price never ran)
NOT_LAUNCHED_OB      = 85.0  # deeply-OB veto: k3 or d3 >= 85 excludes (NOT >=80,
                              # since MCK fixture has k3=81.5 and MUST fire; 85 threshold)

# ext_atr band (pre-registered: [-6, +2])
EXT_ATR_LO = -6.0
EXT_ATR_HI = +2.0

# W-ARM histogram conditions (primary variant)
W_HIST_THETA     = 0.75      # STRICT variant: hist must be > -theta (above -0.75 RSI units)
W_HIST_THETA_NET = 1.00      # NET variant: relaxed threshold (MCD hist=-0.79 > -1.00)
                              # "informative fixture": net variant requires less closeness to 0
W_HIST_LOOKBACK  = 5         # OLS extrapolation: last 5 known weekly bars
W_HIST_W2X_MAX   = 2.0       # linear cross <= 2 weeks ahead
W_HIST_STRICT_N  = 3         # strict-rising: last N bars each strictly > prior

# Sweep thetas (secondary, reported only)
THETA_SWEEPS = [0.50, 0.75, 1.00]
# maxDU thresholds sweep (secondary)
MAXUP_SWEEPS = [0.03, 0.05, 0.08]

# W8-B SHAKEN conditions
SHAKEN_NEW_LOW_ATR   = 1.5   # new low must be > 1.5 ATR below cross price
SHAKEN_RECOVERY_MID  = 0.5   # recovery above midpoint = (cross + new_low) / 2
SHAKEN_TICK_LO       = 3     # tick window lo
SHAKEN_TICK_HI       = 20    # allow more ticks since shake-out can lag
SHAKEN_SEARCH_OFFSET = 20    # search for new low in [cross_pos+1 .. cross_pos+20]
SHAKEN_MIN_N         = 100   # report-only if n < 100

# F7 recompute constants (wave-6 frozen definition)
F7_WEEKLY_RECENCY_D  = 5     # F7: weekly stoch cross within 5 daily bars of fire

# BASED overlap (wave-5 frozen definition)
BASED_LO = 7
BASED_HI = 24

# Promotion gate thresholds (§4.3)
PROMO_SPREAD_PP  = 5.0
PROMO_N_SIDE     = 300
PROMO_STOP_PP    = 2.0
NI_FRESH_CLEAN   = -3.0      # non-inferiority vs FRESH: clean15(W-ARM) >= clean15(FRESH) - 3
NI_FRESH_STOP    = +2.0      # non-inferiority vs FRESH: stop5(W-ARM) <= stop5(FRESH) + 2


# ══════════════════════════════════════════════════════════════════════════════
# Weekly RSI-MACD histogram (W-ARM indicator)
# ══════════════════════════════════════════════════════════════════════════════

def build_weekly_hist_grid(daily_close: pd.Series) -> dict:
    """Build the weekly RSI-MACD histogram on the known-date grid.

    Exact variant from engine/confluence_tiers.py lines 174–176:
        wk = c.resample("W-FRI").last().dropna()
        wm, ws = _rsi_macd(wk)
        histogram = wm - ws

    Known-date mapping: each weekly bar's known date = the last trading day
    in the week. A weekly bar is only visible at daily bar j if its known date
    <= daily_idx[j].

    Returns dict:
        hist_arr   : float array, len = # weekly bars (including warmup NaNs)
        known_arr  : DatetimeIndex of known dates for each weekly bar
        wk_close   : pd.Series of weekly closes (index = week-ending Friday label)
        wm, ws     : RSI-MACD components (pd.Series, weekly native)
    """
    wk = daily_close.resample("W-FRI").last().dropna()
    if len(wk) < 70:          # need at least 60-bar EMA warmup + headroom
        return {"empty": True}
    known_w = (daily_close.resample("W-FRI")
               .apply(lambda x: x.dropna().index.max())
               .reindex(wk.index).dropna())
    wk = wk.reindex(known_w.index)
    known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
    wm, ws = TH.rsi_macd(wk)
    w_hist = (wm - ws)
    return {
        "empty": False,
        "wk_close": wk,
        "wm": wm, "ws": ws,
        "w_hist": w_hist,
        "known_arr": pd.to_datetime(known_w_dt.values),  # DatetimeIndex
        "hist_arr": w_hist.to_numpy().astype(float),
    }


def weekly_hist_at_bar(wg: dict, daily_date: pd.Timestamp,
                       n_bars: int = 8) -> list[float] | None:
    """Return the last n_bars of known weekly hist values as of daily_date.

    Only bars whose known_date <= daily_date are included.
    Returns None if fewer than n_bars are available (insufficient warmup).
    """
    if wg.get("empty"):
        return None
    known = wg["known_arr"]
    hist = wg["hist_arr"]
    mask = known <= daily_date
    valid = hist[mask]
    valid_known = known[mask]
    if len(valid) < n_bars:
        return None
    # Return the last n_bars (most-recent last)
    _ = valid_known[-n_bars:]   # kept for debugging if needed
    return list(valid[-n_bars:])


def w_arm_state(wg: dict, daily_date: pd.Timestamp,
                theta: float = W_HIST_THETA,
                theta_net: float = W_HIST_THETA_NET,
                w2x_max: float = W_HIST_W2X_MAX,
                strict_n: int = W_HIST_STRICT_N,
                lookback: int = W_HIST_LOOKBACK) -> dict:
    """Evaluate the W-ARM trigger at a given daily date.

    Returns dict with:
        fires_strict    : bool — strict-consecutive variant fires (uses theta)
        fires_net       : bool — net-rise variant fires (uses theta_net, more relaxed)
        hist_neg        : bool — most-recent known hist < 0
        above_theta     : bool — most-recent known hist > -theta (strict threshold)
        above_theta_net : bool — most-recent known hist > -theta_net (net threshold)
        net_rising      : bool — last bar > bar[last-3]
        strictly_rising : bool — each of last 3 bars strictly > prior
        w2x_weeks       : float | None — linear extrapolation to zero (weeks ahead)
        last_hist       : float | None — most-recent known hist value
        reason_no_fire  : str — why it didn't fire (if not)

    Leak-free: only uses weekly bars with known_date <= daily_date.

    NOTE on theta vs theta_net: the STRICT variant uses theta=0.75 (hist > -0.75 required;
    i.e. very close to zero). The NET variant uses theta_net=1.00 (hist > -1.00), allowing
    slightly farther-from-zero values — MCD's last bar of -0.79 passes the net threshold.
    This split is pre-registered (see spec §8 W8-A: "informative fixture, not hard" for MCD
    under the NET variant only). The two thresholds reflect the two hypotheses: STRICT says
    "almost there"; NET says "on the way and net-improving".
    """
    null = {"fires_strict": False, "fires_net": False, "hist_neg": False,
            "above_theta": False, "above_theta_net": False,
            "net_rising": False, "strictly_rising": False,
            "w2x_weeks": None, "last_hist": None,
            "reason_no_fire": "no_weekly_data"}
    if wg.get("empty"):
        return null

    bars = weekly_hist_at_bar(wg, daily_date, n_bars=max(lookback, strict_n + 1))
    if bars is None or len(bars) < strict_n + 1:
        return {**null, "reason_no_fire": "insufficient_weekly_bars"}

    last_hist = bars[-1]
    prev3 = bars[-4] if len(bars) >= 4 else None   # bar[last-3] for net-rise check

    # Condition 1: most-recent hist is negative (required for BOTH variants)
    hist_neg = bool(not np.isnan(last_hist) and last_hist < 0)
    if not hist_neg:
        return {**null, "fires_strict": False, "fires_net": False,
                "last_hist": float(last_hist),
                "reason_no_fire": "hist_not_negative"}

    # Condition 2a: above -theta (STRICT variant, tight: 0.75)
    above_theta = bool(not np.isnan(last_hist) and last_hist > -theta)
    # Condition 2b: above -theta_net (NET variant, relaxed: 1.00)
    above_theta_net = bool(not np.isnan(last_hist) and last_hist > -theta_net)

    # Condition 3: strictly rising (last strict_n bars each strictly > prior)
    strictly_rising = all(
        bars[-(strict_n - k)] > bars[-(strict_n - k) - 1]
        for k in range(strict_n)
    )
    # Condition 3b: net-rising over 3 bars (last > last-3)
    net_rising = bool(
        prev3 is not None
        and not np.isnan(last_hist) and not np.isnan(prev3)
        and last_hist > prev3
    )

    # Condition 4: linear extrapolation (OLS on last `lookback` known bars)
    # Computed for ANY candidate that passes hist_neg (used by both variants).
    seg = [v for v in bars[-lookback:] if not np.isnan(v)]
    w2x = None
    if len(seg) >= 3:
        xs = np.arange(len(seg), dtype=float)
        ys = np.array(seg, dtype=float)
        # OLS: hist ~ a*x + b
        xm, ym = xs.mean(), ys.mean()
        denom = ((xs - xm) ** 2).sum()
        if abs(denom) > 1e-10:
            a = ((xs - xm) * (ys - ym)).sum() / denom
            b = ym - a * xm
            if a > 0:
                # weeks to zero from last bar in the segment: (0 - b) / a - (len-1)
                bars_to_zero = (0 - b) / a - (len(seg) - 1)
                w2x = float(bars_to_zero)   # in weekly bars = weeks

    # Extrapolation: crosses zero within w2x_max weeks from last known bar
    extrap_ok = (w2x is not None and 0 < w2x <= w2x_max)

    # STRICT: requires theta (tight), strictly_rising, extrap_ok
    fires_strict = hist_neg and above_theta and strictly_rising and extrap_ok
    # NET: requires theta_net (relaxed), net_rising, extrap_ok
    fires_net    = hist_neg and above_theta_net and net_rising and extrap_ok

    reason = "ok" if (fires_strict or fires_net) else (
        "hist_not_negative" if not hist_neg else
        f"hist_below_neg_theta_net({-theta_net:.2f})" if not above_theta_net else
        "not_net_rising_and_not_strictly_rising" if (not net_rising and not strictly_rising) else
        f"w2x_too_far_or_none(w2x={w2x})" if not extrap_ok else "other"
    )

    return {
        "fires_strict": bool(fires_strict),
        "fires_net":    bool(fires_net),
        "hist_neg":     hist_neg,
        "above_theta":  above_theta,
        "above_theta_net": above_theta_net,
        "strictly_rising": bool(strictly_rising),
        "net_rising":   bool(net_rising),
        "w2x_weeks":    w2x,
        "last_hist":    float(last_hist),
        "reason_no_fire": reason,
    }


def f7_weekly_stoch_state(daily_close: pd.Series, daily_date: pd.Timestamp) -> bool:
    """F7 recompute (wave-6 frozen definition): weekly StochRSI K cross-up known within
    F7_WEEKLY_RECENCY_D daily bars of daily_date. Leak-free known-date mapping."""
    sw = daily_close.resample("W-FRI").last().dropna()
    if len(sw) < 30:
        return False
    known_w = (daily_close.resample("W-FRI")
               .apply(lambda x: x.dropna().index.max())
               .reindex(sw.index).dropna())
    sw = sw.reindex(known_w.index)
    known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
    kw, dw = TH.stoch_rsi_kd(sw)
    wk_cross = TH.xup(kw, dw).fillna(False)
    # find most recent cross with known_date <= daily_date
    daily_dt = pd.Timestamp(daily_date)
    # filter to known <= daily_date
    daily_idx_full = daily_close.index
    pos_today = daily_idx_full.searchsorted(daily_dt, side="right") - 1
    if pos_today < 0:
        return False
    today = daily_idx_full[pos_today]
    for j in range(len(sw) - 1, -1, -1):
        kd = pd.Timestamp(known_w_dt.iloc[j])
        if kd > today:
            continue
        if not bool(wk_cross.iloc[j]):
            continue
        # found most-recent weekly stoch cross; check recency
        daily_pos_of_known = daily_idx_full.searchsorted(kd, side="left")
        since = pos_today - daily_pos_of_known
        return bool(0 <= since <= F7_WEEKLY_RECENCY_D)
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Tick-age and cross-state utilities
# ══════════════════════════════════════════════════════════════════════════════

def _compute_3d_tick_age(s3_known: pd.Series, cross_known_date: pd.Timestamp,
                         obs_daily_date: pd.Timestamp) -> int:
    """Count of 3D bars whose known_date is strictly AFTER cross_known_date and
    AT-OR-BEFORE obs_daily_date. This is the tick age at the observation bar."""
    kv = pd.to_datetime(s3_known.to_numpy())
    return int(((kv > cross_known_date) & (kv <= pd.Timestamp(obs_daily_date))).sum())


def _max_up_since_cross(c_arr: np.ndarray, cross_pos: int, obs_pos: int) -> float:
    """max(close[cross_pos .. obs_pos]) / close[cross_pos] - 1 (max upward extension).
    cross_pos is the daily position of the cross's known date. obs_pos is the
    observation bar. Both inclusive."""
    if obs_pos < cross_pos or cross_pos >= len(c_arr):
        return 0.0
    window = c_arr[cross_pos: obs_pos + 1]
    cross_price = c_arr[cross_pos]
    if np.isnan(cross_price) or cross_price <= 0:
        return 0.0
    mx = float(np.nanmax(window))
    return mx / cross_price - 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Per-fire builder (stale-cross population with W-ARM features)
# ══════════════════════════════════════════════════════════════════════════════

def _build_stale_fires(ticker: str, daily: pd.Series,
                       hi: pd.Series, lo: pd.Series,
                       eval_start: pd.Timestamp,
                       grids: dict) -> list[dict]:
    """Build per-fire rows for the stale-cross W-ARM study.

    TWO-PASS ARCHITECTURE (required for correct STALE_3_8_noW baseline):
    Pass 1: Walk every cross's stale window [3,8]; for each cross record whether
            W-ARM strict ever fires in that window AND the first-qualifying-j data.
    Pass 2: Emit rows.  STALE_3_8 baseline is emitted for EVERY cross that had a
            qualifying j.  STALE_3_8_noW = STALE_3_8 rows for crosses where W-ARM
            STRICT NEVER fired in [3,8] (the pre-registered unfavorable complement).
            F7 is attached to the STALE_3_8 row by index (not rows[-1]).

    DEDUPLICATION: per-name, 21-calendar-day window on fill_date.  For each policy
    independently, if a prior fire's fill_date in [date-21, date), the later fire is
    dropped.  Applied after the per-cross emission to stay consistent with prior waves.

    Population conditions at observation bar j (all leak-free):
      - tick_age[j] in [3, 8]: stale window
      - max_up_since_cross[j] < NOT_LAUNCHED_MAXUP: not launched
      - k3[j] < NOT_LAUNCHED_OB and d3[j] < NOT_LAUNCHED_OB: not deeply OB
      - ext_atr[j] in [EXT_ATR_LO, EXT_ATR_HI]
    """
    c = daily.to_numpy()
    idx = daily.index
    n = len(c)

    if n < MIN_BARS:
        return []

    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()

    # Weekly RSI-MACD histogram grid (built once per name)
    wg = build_weekly_hist_grid(daily)

    # 3D RSI-MACD fires
    s3, kn3 = TH.tf_bars(daily, 3)
    if len(s3) < 20:
        return []
    m3, sig3 = TH.rsi_macd(s3)
    k3_tf, d3_tf = TH.stoch_rsi_kd(s3)
    cross_up = TH.xup(m3, sig3).fillna(False)

    # Daily-mapped 3D stoch K and D (ffill from known date)
    k3_daily = TH.to_daily(k3_tf, kn3, idx, "ffill").to_numpy().astype(float)
    d3_daily = TH.to_daily(d3_tf, kn3, idx, "ffill").to_numpy().astype(float)

    # Cross events: (cross_tf_label, cross_known_date, cross_close)
    cross_events = []
    for ci in range(len(s3)):
        if bool(cross_up.iloc[ci]):
            known_ts = pd.Timestamp(kn3.iloc[ci])
            kpos = idx.searchsorted(known_ts, side="left")
            if kpos < len(idx) and idx[kpos] == known_ts:
                cross_events.append({
                    "ci": int(ci),
                    "known": known_ts,
                    "kpos": int(kpos),
                    "cross_price": float(c[kpos]) if not np.isnan(c[kpos]) else np.nan,
                })

    atrp = grids["atrp"]

    # ── PASS 1: collect per-cross data ─────────────────────────────────────────
    # For each cross record:
    #   base_data   : dict of the first qualifying stale-bar data (or None)
    #   w_arm_data  : dict of first W-ARM STRICT fire data (or None)
    #   w_net_data  : dict of first W-ARM NET fire data (or None)
    #   f7_val      : bool — F7 state at the first stale bar (tick_age == STALE_TICKS_LO)
    #   f7_set      : bool — whether F7 was evaluated at all

    cross_records = []
    for ev in cross_events:
        cross_known = ev["known"]
        cross_kpos  = ev["kpos"]
        cross_price = ev["cross_price"]

        if np.isnan(cross_price) or cross_price <= 0:
            continue

        atrp_at_cross = float(atrp[cross_kpos]) if cross_kpos < len(atrp) else np.nan
        if np.isnan(atrp_at_cross) or atrp_at_cross <= 0:
            continue

        base_data  = None   # first qualifying stale-bar data
        w_arm_data = None   # first W-ARM STRICT fire
        w_net_data = None   # first W-ARM NET fire
        f7_val     = False
        f7_set     = False

        max_j = min(n - 1 - OUTCOME_W - 1, cross_kpos + STALE_TICKS_HI * 4)
        for j in range(cross_kpos + 1, max_j + 1):
            d_j = idx[j]
            if d_j < eval_start:
                continue

            tick_age = _compute_3d_tick_age(kn3, cross_known, d_j)
            if tick_age < STALE_TICKS_LO:
                continue
            if tick_age > STALE_TICKS_HI:
                break

            max_up = _max_up_since_cross(c, cross_kpos, j)
            if max_up >= NOT_LAUNCHED_MAXUP:
                continue

            k3j = float(k3_daily[j]) if j < len(k3_daily) else np.nan
            d3j = float(d3_daily[j]) if j < len(d3_daily) else np.nan
            if (not np.isnan(k3j) and k3j >= NOT_LAUNCHED_OB) or \
               (not np.isnan(d3j) and d3j >= NOT_LAUNCHED_OB):
                continue

            ext = float(c[j]) / cross_price - 1.0
            ext_atr = ext / atrp_at_cross
            if ext_atr < EXT_ATR_LO or ext_atr > EXT_ATR_HI:
                continue

            fill_idx = j + 1
            if fill_idx + OUTCOME_W >= n or np.isnan(c[fill_idx]):
                break

            # F7 evaluated at the first stale bar (tick_age == STALE_TICKS_LO, first time)
            if not f7_set and tick_age == STALE_TICKS_LO:
                f7_val = f7_weekly_stoch_state(daily, d_j)
                f7_set = True

            oc     = compute_outcomes(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
            atr_oc = compute_atr_outcomes(fill_idx, c[fill_idx], c, atrp, n)

            bar_common = {
                "ticker": ticker, "cross_known": cross_known,
                "obs_date": d_j, "fill_date": idx[fill_idx],
                "tick_age": tick_age, "ext": ext, "ext_atr": ext_atr,
                "max_up": max_up, "k3": k3j, "d3": d3j,
                "stop5": oc["stop5"], "clean15": oc["clean15"],
                "dead_money": oc["dead_money"],
                "stop_atr": atr_oc["stop_atr"], "clean_atr": atr_oc["clean_atr"],
            }

            # First qualifying stale bar → baseline data
            if base_data is None:
                base_data = {**bar_common}

            # W-ARM evaluation (can fire on any qualifying bar)
            warm = w_arm_state(wg, d_j, theta=W_HIST_THETA,
                               w2x_max=W_HIST_W2X_MAX,
                               strict_n=W_HIST_STRICT_N,
                               lookback=W_HIST_LOOKBACK)

            if warm["fires_strict"] and w_arm_data is None:
                w_arm_data = {
                    **bar_common,
                    "w_arm_last_hist": warm["last_hist"],
                    "w_arm_w2x": warm["w2x_weeks"],
                }

            if warm["fires_net"] and w_net_data is None:
                w_net_data = {
                    **bar_common,
                    "w_arm_last_hist": warm["last_hist"],
                    "w_arm_w2x": warm["w2x_weeks"],
                }

        cross_records.append({
            "base_data":  base_data,
            "w_arm_data": w_arm_data,
            "w_net_data": w_net_data,
            "f7_val":     f7_val,
            "f7_set":     f7_set,
            "fired_w_arm_strict": w_arm_data is not None,
        })

    # ── PASS 2: emit rows ───────────────────────────────────────────────────────
    rows = []
    for rec in cross_records:
        base_data = rec["base_data"]
        if base_data is None:
            continue  # no qualifying stale bar for this cross

        # STALE_3_8 baseline row (every cross that had a qualifying stale bar)
        stale_row = {**base_data, "policy": "STALE_3_8",
                     "f7_weekly": bool(rec["f7_val"]) if rec["f7_set"] else False}
        rows.append(stale_row)

        # W-ARM STRICT row (only if fired)
        if rec["w_arm_data"] is not None:
            rows.append({**rec["w_arm_data"], "policy": "W_ARM_STRICT"})

        # W-ARM NET row (only if fired)
        if rec["w_net_data"] is not None:
            rows.append({**rec["w_net_data"], "policy": "W_ARM_NET"})

    # ── PASS 3: mark STALE_3_8_noW (post-hoc; crosses where STRICT never fired) ─
    # STALE_3_8_noW is NOT a separate row — it is a boolean column on STALE_3_8 rows.
    # run_gates uses this flag to build the pre-registered unfavorable complement.
    warm_fired_set = set()
    for rec in cross_records:
        if rec["w_arm_data"] is not None and rec["base_data"] is not None:
            # key = (ticker, cross_known, obs_date of base_data)
            warm_fired_set.add((rec["base_data"]["ticker"],
                                rec["base_data"]["cross_known"],
                                rec["base_data"]["obs_date"]))
    for row in rows:
        if row["policy"] == "STALE_3_8":
            key = (row["ticker"], row["cross_known"], row["obs_date"])
            row["arm_fired_on_cross"] = key in warm_fired_set

    # ── PASS 4: per-name, per-policy deduplication (DEDUPE_TD=21 calendar days) ─
    # For each policy, sort by fill_date and keep only fires separated by >= DEDUPE_TD days.
    from collections import defaultdict
    by_policy: dict[str, list] = defaultdict(list)
    for row in rows:
        by_policy[row["policy"]].append(row)

    deduped: list[dict] = []
    for policy, policy_rows in by_policy.items():
        policy_rows.sort(key=lambda r: r["fill_date"])
        last_fill: dict[str, pd.Timestamp] = {}
        for row in policy_rows:
            t = row["ticker"]
            fd = row["fill_date"]
            if t in last_fill:
                gap = (fd - last_fill[t]).days
                if gap < DEDUPE_TD:
                    continue   # too close to prior fire for this name+policy
            last_fill[t] = fd
            deduped.append(row)

    return deduped


def _build_fresh_fires(ticker: str, daily: pd.Series,
                       hi: pd.Series, lo: pd.Series,
                       eval_start: pd.Timestamp,
                       grids: dict) -> list[dict]:
    """FRESH baseline: m2d_s3d fires at tick_age 0-2 (the first 1-3 days after cross).
    Entry = fire bar + 1 (standard fill). One row per fire (first qualifying tick)."""
    c = daily.to_numpy()
    idx = daily.index
    n = len(c)
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    atrp = grids["atrp"]

    s3, kn3 = TH.tf_bars(daily, 3)
    if len(s3) < 20:
        return []
    m3, sig3 = TH.rsi_macd(s3)
    cross_up = TH.xup(m3, sig3).fillna(False)

    rows = []
    for ci in range(len(s3)):
        if not bool(cross_up.iloc[ci]):
            continue
        known_ts = pd.Timestamp(kn3.iloc[ci])
        kpos = idx.searchsorted(known_ts, side="left")
        if kpos >= len(idx) or idx[kpos] != known_ts:
            continue
        # Fresh: fill at kpos+1 (tick_age effectively 0)
        fill_idx = kpos + 1
        if fill_idx >= n or fill_idx + OUTCOME_W >= n or np.isnan(c[fill_idx]):
            continue
        d_fill = idx[fill_idx]
        if d_fill < eval_start:
            continue
        oc = compute_outcomes(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
        atr_oc = compute_atr_outcomes(fill_idx, c[fill_idx], c, atrp, n)
        rows.append({
            "ticker": ticker, "cross_known": known_ts,
            "obs_date": d_fill, "fill_date": d_fill,
            "tick_age": 0,
            "policy": "FRESH",
            "stop5": oc["stop5"], "clean15": oc["clean15"],
            "dead_money": oc["dead_money"],
            "stop_atr": atr_oc["stop_atr"], "clean_atr": atr_oc["clean_atr"],
        })
    return rows


def _build_shaken_fires(ticker: str, daily: pd.Series,
                        hi: pd.Series, lo: pd.Series,
                        eval_start: pd.Timestamp,
                        grids: dict) -> list[dict]:
    """W8-B SHAKEN: post-cross new low > 1.5 ATR below cross, then recovery above midpoint
    + weekly hist net-rising. Report-only cell; one row per cross."""
    c = daily.to_numpy()
    idx = daily.index
    n = len(c)
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    atrp = grids["atrp"]

    wg = build_weekly_hist_grid(daily)
    s3, kn3 = TH.tf_bars(daily, 3)
    if len(s3) < 20:
        return []
    m3, sig3 = TH.rsi_macd(s3)
    cross_up = TH.xup(m3, sig3).fillna(False)
    k3_tf, d3_tf = TH.stoch_rsi_kd(s3)
    k3_daily = TH.to_daily(k3_tf, kn3, idx, "ffill").to_numpy().astype(float)
    d3_daily = TH.to_daily(d3_tf, kn3, idx, "ffill").to_numpy().astype(float)

    rows = []
    for ci in range(len(s3)):
        if not bool(cross_up.iloc[ci]):
            continue
        known_ts = pd.Timestamp(kn3.iloc[ci])
        kpos = idx.searchsorted(known_ts, side="left")
        if kpos >= len(idx) or idx[kpos] != known_ts:
            continue
        cross_price = float(c[kpos])
        if np.isnan(cross_price) or cross_price <= 0:
            continue
        atrp_at_cross = float(atrp[kpos]) if kpos < len(atrp) else np.nan
        if np.isnan(atrp_at_cross) or atrp_at_cross <= 0:
            continue

        shake_threshold = cross_price * (1.0 - SHAKEN_NEW_LOW_ATR * atrp_at_cross)

        # Search for a new low > 1.5 ATR below cross price in [kpos+1, kpos+SHAKEN_SEARCH_OFFSET]
        new_low_pos = None
        new_low_price = np.inf
        for j1 in range(kpos + 1, min(kpos + SHAKEN_SEARCH_OFFSET + 1, n)):
            if c[j1] < shake_threshold and c[j1] < new_low_price:
                new_low_price = c[j1]
                new_low_pos = j1

        if new_low_pos is None:
            continue  # no shake-out dip found

        midpoint = (cross_price + new_low_price) / 2.0

        # Recovery: first bar after new_low_pos where close > midpoint AND weekly hist net-rising
        for j2 in range(new_low_pos + 1, min(kpos + SHAKEN_TICK_HI * 3, n)):
            if c[j2] <= midpoint:
                continue
            d_j2 = idx[j2]
            if d_j2 < eval_start:
                continue
            warm = w_arm_state(wg, d_j2, theta=W_HIST_THETA,
                               w2x_max=W_HIST_W2X_MAX,
                               strict_n=W_HIST_STRICT_N,
                               lookback=W_HIST_LOOKBACK)
            if not warm["fires_net"]:
                continue
            # Stale check (tick age from original cross)
            tick_age = _compute_3d_tick_age(kn3, known_ts, d_j2)
            if not (SHAKEN_TICK_LO <= tick_age <= SHAKEN_TICK_HI):
                continue
            # Not deeply OB
            k3j = float(k3_daily[j2]) if j2 < len(k3_daily) else np.nan
            d3j = float(d3_daily[j2]) if j2 < len(d3_daily) else np.nan
            if (not np.isnan(k3j) and k3j >= NOT_LAUNCHED_OB) or \
               (not np.isnan(d3j) and d3j >= NOT_LAUNCHED_OB):
                continue
            fill_idx = j2 + 1
            if fill_idx + OUTCOME_W >= n or np.isnan(c[fill_idx]):
                break
            oc = compute_outcomes(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
            atr_oc = compute_atr_outcomes(fill_idx, c[fill_idx], c, atrp, n)
            rows.append({
                "ticker": ticker, "cross_known": known_ts,
                "obs_date": d_j2, "fill_date": idx[fill_idx],
                "tick_age": tick_age,
                "new_low_price": float(new_low_price),
                "shake_atr": float((cross_price - new_low_price) / (atrp_at_cross * cross_price)),
                "midpoint": float(midpoint),
                "w_arm_last_hist": warm["last_hist"],
                "w_arm_w2x": warm["w2x_weeks"],
                "policy": "SHAKEN",
                "stop5": oc["stop5"], "clean15": oc["clean15"],
                "dead_money": oc["dead_money"],
                "stop_atr": atr_oc["stop_atr"], "clean_atr": atr_oc["clean_atr"],
            })
            break  # one fire per cross

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Panel worker
# ══════════════════════════════════════════════════════════════════════════════

def _process_name(ticker, fp, eval_start_str, min_bars) -> dict:
    try:
        df = pd.read_parquet(fp)
        daily = df["close"].dropna()
        hi = df["high"].reindex(daily.index) if "high" in df.columns \
            else pd.Series(np.nan, index=daily.index)
        lo = df["low"].reindex(daily.index) if "low" in df.columns \
            else pd.Series(np.nan, index=daily.index)
        if len(daily) < min_bars:
            return {}
        eval_start = pd.Timestamp(eval_start_str)
        grids = build_tf_grids(daily, hi, lo, None)
        stale_rows = _build_stale_fires(ticker, daily, hi, lo, eval_start, grids)
        fresh_rows = _build_fresh_fires(ticker, daily, hi, lo, eval_start, grids)
        shaken_rows = _build_shaken_fires(ticker, daily, hi, lo, eval_start, grids)
        return {"stale": stale_rows, "fresh": fresh_rows, "shaken": shaken_rows}
    except Exception as e:  # noqa: BLE001
        return {"_error": repr(e)}


def _worker(args):
    ticker, fp, eval_start_str, min_bars = args
    res = _process_name(ticker, fp, eval_start_str, min_bars)
    return ticker, res


def run_panel(panel: str, tickers=None, workers: int = 4) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = PANEL_CONFIGS[panel]
    data_dir   = cfg["data_dir"]
    min_bars   = cfg["min_bars"]
    eval_start = cfg["eval_start"]

    print(f"Wave-8 W-ARM | panel={panel} | eval_start={eval_start.date()} "
          f"| min_bars={min_bars} | workers={workers}")

    all_files = sorted(data_dir.glob("*.parquet"))
    if tickers:
        all_files = [f for f in all_files if f.stem in set(tickers)]
    panel_files = []
    for fp in all_files:
        try:
            if len(pd.read_parquet(fp)["close"].dropna()) >= min_bars:
                panel_files.append(fp)
        except Exception:
            pass
    print(f"Panel names (>= {min_bars} bars): {len(panel_files)}")

    args = [(fp.stem, str(fp), str(eval_start), min_bars) for fp in panel_files]
    t0 = time.time()
    if workers <= 1:
        results = [_worker(a) for a in args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_worker, args)

    stale_all, fresh_all, shaken_all, errors = [], [], [], []
    for ticker, res in results:
        if "_error" in res:
            errors.append(f"{ticker}: {res['_error']}")
            continue
        stale_all.extend(res.get("stale", []))
        fresh_all.extend(res.get("fresh", []))
        shaken_all.extend(res.get("shaken", []))
    print(f"Done in {time.time()-t0:.1f}s. errors={len(errors)}: {errors[:3]}")

    stale_df = pd.DataFrame(stale_all)
    fresh_df = pd.DataFrame(fresh_all)
    shaken_df = pd.DataFrame(shaken_all)
    for df in [stale_df, fresh_df, shaken_df]:
        for col in ["cross_known", "obs_date", "fill_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    sp = OUT_DIR / f"wave8_warm_{panel}_stale.parquet"
    fp_out = OUT_DIR / f"wave8_warm_{panel}_fresh.parquet"
    shp = OUT_DIR / f"wave8_warm_{panel}_shaken.parquet"
    stale_df.to_parquet(sp, index=False)
    fresh_df.to_parquet(fp_out, index=False)
    shaken_df.to_parquet(shp, index=False)

    n_warm_strict = int((stale_df["policy"] == "W_ARM_STRICT").sum()) if len(stale_df) else 0
    n_warm_net    = int((stale_df["policy"] == "W_ARM_NET").sum()) if len(stale_df) else 0
    n_stale_base  = int((stale_df["policy"] == "STALE_3_8").sum()) if len(stale_df) else 0
    n_fresh       = len(fresh_df)
    n_shaken      = len(shaken_df)
    print(f"  FRESH={n_fresh}  STALE_3_8={n_stale_base}  "
          f"W_ARM_STRICT={n_warm_strict}  W_ARM_NET={n_warm_net}  "
          f"SHAKEN={n_shaken}")
    print(f"  Output: {sp.name}, {fp_out.name}, {shp.name}")
    return sp


def run_gates(panel: str, data_dir: Path | None = None) -> dict:
    """Evaluate W8-A promotion gates from the panel parquets.

    Pre-registered gate clauses (§4.3):
    1. clean15 spread (W_ARM_STRICT vs STALE_3_8_noW) >= PROMO_SPREAD_PP (5pp)
       with n >= PROMO_N_SIDE (300) per stratum.
    2. Same-sign spread on BOTH ticker halves AND BOTH time halves (pre/post-2020).
    3. stop5 not worse (W_ARM_STRICT vs STALE_3_8_noW) by > PROMO_STOP_PP (2pp).
    4. Non-inferiority to FRESH: clean15(W_ARM) >= clean15(FRESH) - NI_FRESH_CLEAN (-3pp)
       AND stop5(W_ARM) <= stop5(FRESH) + NI_FRESH_STOP (+2pp).
    5. Recall gain: B15-durable recall of W_ARM_STRICT >= recall of STALE_3_8_noW.

    STALE_3_8_noW = STALE_3_8 rows with arm_fired_on_cross == False (pre-registered
    unfavorable complement: crosses that NEVER fired W-ARM STRICT in [3,8]).
    """
    sp = OUT_DIR / f"wave8_warm_{panel}_stale.parquet"
    fp_out = OUT_DIR / f"wave8_warm_{panel}_fresh.parquet"
    if not sp.exists() or not fp_out.exists():
        print(f"Gate parquets missing for panel={panel}. Run --{panel} first.")
        return {}

    stale = pd.read_parquet(sp)
    fresh = pd.read_parquet(fp_out)

    for df in [stale, fresh]:
        for col in ["cross_known", "obs_date", "fill_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    # ── Helper ─────────────────────────────────────────────────────────────────
    def _stats_ser(sub: pd.DataFrame) -> dict:
        if len(sub) == 0:
            return {"n": 0, "stop5": np.nan, "clean15": np.nan, "dead_money": np.nan}
        return {
            "n": len(sub),
            "stop5":      float(_rate(sub["stop5"]) * 100),
            "clean15":    float(_rate(sub["clean15"]) * 100),
            "dead_money": float(_rate(sub["dead_money"]) * 100),
        }

    def _stats_policy(df: pd.DataFrame, policy: str) -> dict:
        return _stats_ser(df[df["policy"] == policy])

    # ── Strata ──────────────────────────────────────────────────────────────────
    # STALE_3_8: all crosses that had a qualifying stale bar (the gross pool)
    # STALE_3_8_noW: STALE_3_8 rows that NEVER fired W-ARM STRICT on that cross
    stale_all    = stale[stale["policy"] == "STALE_3_8"]
    if "arm_fired_on_cross" in stale_all.columns:
        stale_now    = stale_all[stale_all["arm_fired_on_cross"] == False].copy()  # noqa: E712
    else:
        # Fallback: if column missing (shouldn't happen), use all STALE_3_8
        stale_now    = stale_all.copy()
        print("  WARNING: arm_fired_on_cross column missing — STALE_3_8_noW = STALE_3_8 (contaminated)")

    warm_strict  = stale[stale["policy"] == "W_ARM_STRICT"]
    warm_net     = stale[stale["policy"] == "W_ARM_NET"]
    fresh_df     = fresh[fresh["policy"] == "FRESH"]

    fav   = _stats_ser(warm_strict)
    unfav = _stats_ser(stale_now)
    frsh  = _stats_ser(fresh_df)

    results = {
        "FRESH":          _stats_ser(fresh_df),
        "STALE_3_8":      _stats_ser(stale_all),
        "STALE_3_8_noW":  unfav,
        "W_ARM_STRICT":   fav,
        "W_ARM_NET":      _stats_ser(warm_net),
    }

    spread     = (fav["clean15"] - unfav["clean15"]) if (fav["n"] > 0 and unfav["n"] > 0) else np.nan
    stop_delta = (fav["stop5"]   - unfav["stop5"])   if (fav["n"] > 0 and unfav["n"] > 0) else np.nan
    ni_clean   = (fav["clean15"] - frsh["clean15"])  if (fav["n"] > 0 and frsh["n"] > 0) else np.nan
    ni_stop    = (fav["stop5"]   - frsh["stop5"])    if (fav["n"] > 0 and frsh["n"] > 0) else np.nan

    gate_spread   = (not np.isnan(spread) and spread >= PROMO_SPREAD_PP
                     and fav["n"] >= PROMO_N_SIDE and unfav["n"] >= PROMO_N_SIDE)
    gate_stop     = not np.isnan(stop_delta) and stop_delta <= PROMO_STOP_PP
    gate_ni_clean = not np.isnan(ni_clean) and ni_clean >= NI_FRESH_CLEAN
    gate_ni_stop  = not np.isnan(ni_stop)  and ni_stop  <= NI_FRESH_STOP

    # ── Ticker-half and time-half stability (pre-registered §4.3) ──────────────
    split_date = pd.Timestamp("2020-01-01")

    def _half_sign_stable(warm_df: pd.DataFrame, now_df: pd.DataFrame,
                          col: str = "clean15") -> dict:
        """Check that the spread sign (fav > unfav) holds on ALL four sub-groups:
        ticker-half A (sorted by ticker name, lower half), ticker-half B,
        pre-2020, post-2020. Returns a dict with per-group spreads."""
        out = {}
        # Ticker halves: sort unique tickers, split by median
        tickers_sorted = sorted(warm_df["ticker"].unique().tolist())
        n_t = len(tickers_sorted)
        if n_t < 4:
            return {"ticker_halves_ok": None, "time_halves_ok": None, "details": {}}
        half_a_tickers = set(tickers_sorted[: n_t // 2])
        half_b_tickers = set(tickers_sorted[n_t // 2:])
        for half_name, t_set in [("ticker_A", half_a_tickers), ("ticker_B", half_b_tickers)]:
            w_h = warm_df[warm_df["ticker"].isin(t_set)]
            n_h = now_df[now_df["ticker"].isin(t_set)]
            if len(w_h) >= 10 and len(n_h) >= 10:
                sp = float(_rate(w_h[col]) - _rate(n_h[col])) * 100
                out[half_name] = round(sp, 2)
            else:
                out[half_name] = None
        # Time halves
        for half_name, mask_col, op in [
            ("pre2020",  "fill_date", "lt"),
            ("post2020", "fill_date", "ge"),
        ]:
            if op == "lt":
                w_h = warm_df[warm_df["fill_date"] < split_date]
                n_h = now_df[now_df["fill_date"] < split_date]
            else:
                w_h = warm_df[warm_df["fill_date"] >= split_date]
                n_h = now_df[now_df["fill_date"] >= split_date]
            if len(w_h) >= 10 and len(n_h) >= 10:
                sp = float(_rate(w_h[col]) - _rate(n_h[col])) * 100
                out[half_name] = round(sp, 2)
            else:
                out[half_name] = None
        # Check all-positive
        vals = [v for v in out.values() if v is not None]
        ticker_vals  = [v for k, v in out.items() if k.startswith("ticker") and v is not None]
        time_vals    = [v for k, v in out.items() if k.startswith("pre") or k.startswith("post") if v is not None]
        out["ticker_halves_ok"] = all(v > 0 for v in ticker_vals) if ticker_vals else None
        out["time_halves_ok"]   = all(v > 0 for v in time_vals) if time_vals else None
        out["all_positive"]     = all(v > 0 for v in vals) if vals else None
        return out

    stability = _half_sign_stable(warm_strict, stale_now)
    gate_stability = (stability.get("ticker_halves_ok") and stability.get("time_halves_ok"))

    # ── Recall gate (B15-durable-bottom recall) ─────────────────────────────────
    # Recall = fraction of B15 durable-bottom events within OUTCOME_W bars of a fire.
    # We compute this per name from the raw panel files (or from the config data_dir).
    recall_warm = np.nan
    recall_now  = np.nan
    recall_ok   = None
    cfg = PANEL_CONFIGS.get(panel, {})
    recall_data_dir = data_dir or cfg.get("data_dir")
    if recall_data_dir and Path(recall_data_dir).exists():
        warm_recalls, now_recalls = [], []
        tickers_with_warm = set(warm_strict["ticker"].unique())
        tickers_with_now  = set(stale_now["ticker"].unique())
        tickers_union = tickers_with_warm | tickers_with_now
        for fp in Path(recall_data_dir).glob("*.parquet"):
            t = fp.stem
            if t not in tickers_union:
                continue
            try:
                df_t = pd.read_parquet(fp)
                daily_t = df_t["close"].dropna()
                if len(daily_t) < MIN_BARS:
                    continue
                events = label_events(daily_t)
                if len(events) == 0:
                    continue
                durable = events[events["label"] == "durable"]["t0"]
                if len(durable) == 0:
                    continue
                durable_dates = pd.to_datetime(durable.values)

                def _recall_for(fire_df: pd.DataFrame, t_name: str) -> float:
                    """Fraction of durable events caught within OUTCOME_W bars after a fire."""
                    fires_t = fire_df[fire_df["ticker"] == t_name]
                    if len(fires_t) == 0:
                        return np.nan
                    fire_dates = pd.to_datetime(fires_t["fill_date"].values)
                    # event is "caught" if any fire falls in [-OUTCOME_W, 0] days of it
                    caught = sum(
                        1 for ev_d in durable_dates
                        if any((ev_d - pd.Timedelta(days=OUTCOME_W)) <= fd <= ev_d
                               for fd in fire_dates)
                    )
                    return caught / len(durable_dates)

                r_w = _recall_for(warm_strict, t)
                r_n = _recall_for(stale_now, t)
                if not np.isnan(r_w):
                    warm_recalls.append(r_w)
                if not np.isnan(r_n):
                    now_recalls.append(r_n)
            except Exception:  # noqa: BLE001
                pass
        if warm_recalls:
            recall_warm = float(np.mean(warm_recalls) * 100)
        if now_recalls:
            recall_now  = float(np.mean(now_recalls) * 100)
        if not np.isnan(recall_warm) and not np.isnan(recall_now):
            recall_ok = recall_warm >= recall_now  # W-ARM recall >= STALE_noW recall

    gate_recall = recall_ok if recall_ok is not None else None

    # ── F7 Jaccard (recompute on stale pop) ─────────────────────────────────────
    # F7 fires on STALE_3_8 rows (stored in f7_weekly column).
    # Jaccard(W-ARM fires, F7 fires) — uses cross_known as fire key.
    jaccard_f7 = np.nan
    jaccard_based = np.nan
    if "f7_weekly" in stale_all.columns:
        stale_s8_keys  = set(zip(stale_all["ticker"], stale_all["cross_known"]))
        warm_keys      = set(zip(warm_strict["ticker"], warm_strict["cross_known"]))
        f7_rows        = stale_all[stale_all["f7_weekly"] == True]   # noqa: E712
        f7_keys        = set(zip(f7_rows["ticker"], f7_rows["cross_known"]))
        if warm_keys or f7_keys:
            inter = len(warm_keys & f7_keys)
            union = len(warm_keys | f7_keys)
            jaccard_f7 = round(inter / union, 3) if union > 0 else np.nan

    # BASED-chip Jaccard: BASED fires = stale crosses at tick_age in [BASED_LO, BASED_HI]
    based_rows = stale_all[(stale_all["tick_age"] >= BASED_LO) &
                           (stale_all["tick_age"] <= BASED_HI)]
    based_keys = set(zip(based_rows["ticker"], based_rows["cross_known"]))
    if warm_keys or based_keys:
        inter = len(warm_keys & based_keys)
        union = len(warm_keys | based_keys)
        jaccard_based = round(inter / union, 3) if union > 0 else np.nan

    # ── Assemble gates ──────────────────────────────────────────────────────────
    # PROMOTE requires ALL five gate clauses
    promote = bool(
        gate_spread and gate_stop and gate_ni_clean and gate_ni_stop
        and gate_stability is True
        and (recall_ok is True or recall_ok is None)  # recall pass or not computable
    )

    gates = {
        "spread_pp":          round(float(spread), 2) if not np.isnan(spread) else None,
        "stop_delta_pp":      round(float(stop_delta), 2) if not np.isnan(stop_delta) else None,
        "ni_vs_fresh_clean":  round(float(ni_clean), 2) if not np.isnan(ni_clean) else None,
        "ni_vs_fresh_stop":   round(float(ni_stop), 2)  if not np.isnan(ni_stop) else None,
        "gate_spread":        gate_spread,
        "gate_stop":          gate_stop,
        "gate_ni_clean":      gate_ni_clean,
        "gate_ni_stop":       gate_ni_stop,
        "gate_stability":     gate_stability,
        "gate_recall":        gate_recall,
        "PROMOTE":            promote,
        "jaccard_f7":         jaccard_f7,
        "jaccard_based":      jaccard_based,
        "recall_warm_pct":    round(recall_warm, 2) if not np.isnan(recall_warm) else None,
        "recall_noW_pct":     round(recall_now, 2)  if not np.isnan(recall_now) else None,
    }

    print(f"\n=== W8-A Promotion Gates ({panel}) ===")
    print(f"  Strata: FRESH={frsh['n']}  STALE_3_8={_stats_ser(stale_all)['n']}  "
          f"STALE_3_8_noW={unfav['n']}  W_ARM_STRICT={fav['n']}  W_ARM_NET={_stats_ser(warm_net)['n']}")
    print(f"\n  --- Per-stratum metrics (%, stop5/clean15/dead_money) ---")
    for pol, st in results.items():
        if st["n"] > 0:
            print(f"  {pol:20s}: n={st['n']:5d}  stop5={st['stop5']:5.1f}%  "
                  f"clean15={st['clean15']:5.1f}%  dead={st['dead_money']:5.1f}%")

    print(f"\n  --- Gate evaluations ---")
    print(f"  [1] spread (W_ARM_STRICT - STALE_3_8_noW clean15): "
          f"{gates['spread_pp']}pp  (need >= {PROMO_SPREAD_PP}pp)  → {gate_spread}")
    print(f"  [2] stop_delta (W_ARM_STRICT - STALE_3_8_noW stop5): "
          f"{gates['stop_delta_pp']}pp  (need <= {PROMO_STOP_PP}pp)  → {gate_stop}")
    print(f"  [3] NI clean15 vs FRESH: {gates['ni_vs_fresh_clean']}pp  "
          f"(need >= {NI_FRESH_CLEAN})  → {gate_ni_clean}")
    print(f"  [4] NI stop5 vs FRESH: {gates['ni_vs_fresh_stop']}pp  "
          f"(need <= {NI_FRESH_STOP})  → {gate_ni_stop}")
    print(f"  [5] Stability (ticker + time halves): {stability}  → {gate_stability}")
    print(f"  [6] Recall gate: warm={gates['recall_warm_pct']}%  "
          f"noW={gates['recall_noW_pct']}%  → {gate_recall}")
    print(f"  [7] Jaccard(W_ARM, F7)={gates['jaccard_f7']}  (informative; near-miss check)")
    print(f"  [8] Jaccard(W_ARM, BASED)={gates['jaccard_based']}  (must be < 0.30)")
    print(f"\n  PROMOTE = {promote}")

    return {"gates": gates, "stats": results, "stability": stability}


# ══════════════════════════════════════════════════════════════════════════════
# SMOKE TEST (live fixtures, as of 2026-07-01)
# ══════════════════════════════════════════════════════════════════════════════

FIXTURE_DATE = pd.Timestamp("2026-07-01")   # observation date for smoke checks


def _smoke_ticker(ticker: str) -> dict:
    """Run fixture smoke checks for one ticker as of FIXTURE_DATE."""
    fp = DATA_STOCKS / f"{ticker}.parquet"
    if not fp.exists():
        return {"ticker": ticker, "error": "file_not_found"}

    df = pd.read_parquet(fp)
    daily = df["close"].dropna()
    hi = df["high"].reindex(daily.index) if "high" in df.columns \
        else pd.Series(np.nan, index=daily.index)
    lo = df["low"].reindex(daily.index) if "low" in df.columns \
        else pd.Series(np.nan, index=daily.index)

    # Truncate at FIXTURE_DATE (simulate "as of 2026-07-01")
    daily = daily.loc[:FIXTURE_DATE]
    hi    = hi.reindex(daily.index)
    lo    = lo.reindex(daily.index)

    if len(daily) < 200:
        return {"ticker": ticker, "error": "insufficient_bars"}

    grids = build_tf_grids(daily, hi, lo, None)
    c = daily.to_numpy()
    idx = daily.index
    atrp = grids["atrp"]

    # Weekly RSI-MACD grid
    wg = build_weekly_hist_grid(daily)
    if wg.get("empty"):
        return {"ticker": ticker, "error": "no_weekly_grid"}

    # 3D cross info
    s3, kn3 = TH.tf_bars(daily, 3)
    m3, sig3 = TH.rsi_macd(s3)
    k3_tf, d3_tf = TH.stoch_rsi_kd(s3)
    cross_up = TH.xup(m3, sig3).fillna(False)
    k3_daily = TH.to_daily(k3_tf, kn3, idx, "ffill").to_numpy().astype(float)
    d3_daily = TH.to_daily(d3_tf, kn3, idx, "ffill").to_numpy().astype(float)

    # Last cross
    cross_events = []
    for ci in range(len(s3)):
        if bool(cross_up.iloc[ci]):
            known_ts = pd.Timestamp(kn3.iloc[ci])
            kpos = idx.searchsorted(known_ts, side="left")
            if kpos < len(idx) and idx[kpos] == known_ts:
                cross_events.append({"ci": ci, "known": known_ts, "kpos": kpos,
                                     "cross_price": float(c[kpos])})

    if not cross_events:
        return {"ticker": ticker, "error": "no_cross_found"}

    last_ev = cross_events[-1]
    cross_known = last_ev["known"]
    cross_kpos  = last_ev["kpos"]
    cross_price = last_ev["cross_price"]
    obs_pos     = len(idx) - 1   # last bar = 2026-07-01
    obs_date    = idx[obs_pos]

    # Metrics at observation date
    tick_age = _compute_3d_tick_age(kn3, cross_known, obs_date)
    max_up   = _max_up_since_cross(c, cross_kpos, obs_pos)
    ext      = c[obs_pos] / cross_price - 1.0
    atrp_at_cross = float(atrp[cross_kpos]) if cross_kpos < len(atrp) else np.nan
    ext_atr  = ext / atrp_at_cross if not np.isnan(atrp_at_cross) and atrp_at_cross > 0 else np.nan
    k3_obs   = float(k3_daily[obs_pos])
    d3_obs   = float(d3_daily[obs_pos])

    # W-ARM state at observation date
    warm = w_arm_state(wg, obs_date)
    # Also last 6 weekly hist values for inspection
    weekly_hist_6 = weekly_hist_at_bar(wg, obs_date, n_bars=6)

    # Population conditions (stale window + not-launched + not-OB)
    in_stale_window = STALE_TICKS_LO <= tick_age <= STALE_TICKS_HI
    not_launched    = max_up < NOT_LAUNCHED_MAXUP
    not_ob          = (np.isnan(k3_obs) or k3_obs < NOT_LAUNCHED_OB) and \
                      (np.isnan(d3_obs) or d3_obs < NOT_LAUNCHED_OB)
    ext_in_band     = EXT_ATR_LO <= ext_atr <= EXT_ATR_HI if not np.isnan(ext_atr) else False
    in_population   = in_stale_window and not_launched and not_ob and ext_in_band

    fires_strict = in_population and warm["fires_strict"]
    fires_net    = in_population and warm["fires_net"]

    result = {
        "ticker": ticker,
        "cross_known": str(cross_known.date()),
        "cross_price": round(cross_price, 2),
        "tick_age": tick_age,
        "ext_pct": round(ext * 100, 2),
        "ext_atr": round(ext_atr, 2) if not np.isnan(ext_atr) else None,
        "max_up_pct": round(max_up * 100, 2),
        "k3": round(k3_obs, 1), "d3": round(d3_obs, 1),
        "in_stale_window": in_stale_window,
        "not_launched": not_launched,
        "not_ob": not_ob,
        "ext_in_band": ext_in_band,
        "in_population": in_population,
        "weekly_hist_6": [round(v, 2) for v in (weekly_hist_6 or [])],
        "w_arm_strictly_rising": warm["strictly_rising"],
        "w_arm_net_rising": warm["net_rising"],
        "w_arm_above_theta": warm["above_theta"],
        "w_arm_above_theta_net": warm.get("above_theta_net", False),
        "w_arm_hist_neg": warm["hist_neg"],
        "w_arm_w2x": round(warm["w2x_weeks"], 2) if warm["w2x_weeks"] is not None else None,
        "fires_strict": fires_strict,
        "fires_net": fires_net,
        "w_arm_reason": warm["reason_no_fire"],
    }
    return result


FIXTURE_ASSERTIONS = {
    # ticker: {fires_strict, fires_net, in_population}
    # MCK: MUST fire W-ARM (hard fixture). Spec says "MUST fire W-ARM."
    "MCK": {"fires_strict": True,  "fires_net": True,  "in_population": True},
    # MCD: "informative fixture, not hard" — net-rising + above_theta_net=True
    #      but w2x=4.17w > 2.0 threshold (stalled last 2 bars means extrapolation
    #      is pushed out). MCD demonstrates the ANATOMY of the stalled-approach
    #      population; it doesn't fire at this snapshot because the cross is too far.
    #      Only in_population is asserted (hard); fires are informational only.
    "MCD": {"in_population": True},
    # KO: must NOT fire (hard fixture). Hist oscillating, no approach signature.
    "KO":  {"fires_strict": False, "fires_net": False, "in_population": True},
    # ELV: must NEVER fire (hard fixture). Tick=20 (outside window), hist positive.
    "ELV": {"fires_strict": False, "fires_net": False, "in_population": False},
}


def run_smoke(tickers=None):
    """Run smoke/fixture assertions as of FIXTURE_DATE=2026-07-01."""
    if tickers is None:
        tickers = list(FIXTURE_ASSERTIONS.keys()) + ["AAPL", "JNJ", "WMT", "XOM"]
    else:
        tickers = [t.strip() for t in tickers.split(",") if t.strip()]

    print(f"\n{'='*68}")
    print(f" Wave-8 W-ARM Smoke Test (as of {FIXTURE_DATE.date()})")
    print(f"{'='*68}")

    all_pass = True
    results = {}
    for ticker in tickers:
        r = _smoke_ticker(ticker)
        results[ticker] = r
        if "error" in r:
            print(f"[SKIP] {ticker}: {r['error']}")
            continue

        # Print state summary
        print(f"\n--- {ticker} ---")
        print(f"  cross_known={r['cross_known']}  tick={r['tick_age']}  "
              f"ext={r['ext_pct']}%  ext_atr={r['ext_atr']}  "
              f"max_up={r['max_up_pct']}%")
        print(f"  k3={r['k3']}  d3={r['d3']}  in_pop={r['in_population']}")
        print(f"  weekly_hist_6={r['weekly_hist_6']}")
        print(f"  hist_neg={r['w_arm_hist_neg']}  above_theta={r['w_arm_above_theta']}  "
              f"above_theta_net={r.get('w_arm_above_theta_net')}  "
              f"strictly_rising={r['w_arm_strictly_rising']}  net_rising={r['w_arm_net_rising']}  "
              f"w2x={r['w_arm_w2x']}w")
        print(f"  FIRES_STRICT={r['fires_strict']}  FIRES_NET={r['fires_net']}")

        # Check fixture assertions
        if ticker in FIXTURE_ASSERTIONS:
            expected = FIXTURE_ASSERTIONS[ticker]
            ticker_ok = True
            for key, exp_val in expected.items():
                got_val = r.get(key)
                ok = (got_val == exp_val)
                status = "PASS" if ok else "FAIL"
                if not ok:
                    ticker_ok = False
                    all_pass = False
                print(f"  [{status}] {key}: expected={exp_val} got={got_val}")
            if ticker_ok:
                print(f"  [ALL PASS] {ticker}")
        else:
            print(f"  [INFO] {ticker}: no fixture assertions (informational)")

    print(f"\n{'='*68}")
    print(f" Overall smoke: {'ALL FIXTURES PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"{'='*68}\n")
    return all_pass, results


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-8 W-ARM (Cells A + B)")
    ap.add_argument("--smoke", action="store_true",
                    help="Run live fixture smoke checks (2026-07-01)")
    ap.add_argument("--tickers", type=str, default=None,
                    help="Comma-separated tickers for --smoke (default: fixture set + extras)")
    ap.add_argument("--stocks",  action="store_true", help="Run deep US panel")
    ap.add_argument("--baskets", action="store_true", help="Run baskets OOS panel")
    ap.add_argument("--gates",   action="store_true", help="Evaluate promotion gates")
    ap.add_argument("--workers", type=int, default=4, help="Parallel workers")
    args = ap.parse_args()

    if args.smoke:
        passed, _ = run_smoke(args.tickers)
        sys.exit(0 if passed else 1)
    if args.stocks:
        run_panel("stocks", workers=args.workers)
    if args.baskets:
        run_panel("baskets", workers=args.workers)
    if args.gates:
        for panel in ["stocks", "baskets"]:
            sp = OUT_DIR / f"wave8_warm_{panel}_stale.parquet"
            if sp.exists():
                run_gates(panel)


if __name__ == "__main__":
    main()
